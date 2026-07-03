"""戰鬥操作流(R113)回歸測試:↻ 再次 / 目標記憶 / 目標選單可返回。

涵蓋:repeat 選項出現條件(有上次動作 / cast 需仍可施)、repeat 展開(沿用存活目標零選單 /
目標死亡重開目標選單)、目標選單「↻ 上次」標記與 allow_back(返回 → 退回行動選單、
場內狀態 vanish/charm 保留)、無 mem(舊呼叫)零 repeat 完全相容。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import combat
from tesrpg.ui import console as ui

import tesrpg.main as M


def _setup(n_enemies=2, spells=("flames",)):
    gd = get_gamedata()
    c = build_character(gd, name="流", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.spells = list(spells)
    c.magicka = c.max_magicka
    state = GameState(player=c, rng=RNG(3))
    enemies = [combat.spawn_creature(gd, "bandit", state.rng) for _ in range(n_enemies)]
    return gd, state, enemies


def _drive(seq, fn):
    """patch ui.menu/combat_status_group 以 key 序列驅動;回傳 (結果, 每次選單的 (title, keys))。"""
    seen = []
    q = list(seq)
    saved = (ui.menu, ui.combat_status_group)
    ui.combat_status_group = lambda *a, **k: None
    ui.menu = lambda title, options, allow_back=False: (
        seen.append((title, [o[0] for o in options])) or (q.pop(0) if q else "flee"))
    try:
        return fn(), seen
    finally:
        ui.menu, ui.combat_status_group = saved


def test_no_mem_no_repeat_backcompat():
    gd, state, enemies = _setup()
    act, seen = _drive(["attack", "0"],
                       lambda: M._choose_combat_action(state, gd, enemies, []))
    assert act["type"] == "attack" and act["target"] is enemies[0]
    assert "repeat" not in seen[0][1]                       # 無 mem(舊呼叫)→ 無 repeat 選項


def test_repeat_attack_reuses_living_target_without_menu():
    gd, state, enemies = _setup()
    mem = {"last": {"type": "attack"}, "target": enemies[1], "ally": None}
    act, seen = _drive(["repeat"],
                       lambda: M._choose_combat_action(state, gd, enemies, [], mem=mem))
    assert act == {"type": "attack", "target": enemies[1]}
    assert len(seen) == 1                                   # 只出行動選單,零目標選單
    assert seen[0][1][0] == "repeat"                        # ↻ 置頂


def test_repeat_attack_dead_target_reopens_target_menu():
    gd, state, enemies = _setup(n_enemies=3)
    enemies[1].health = 0
    mem = {"last": {"type": "attack"}, "target": enemies[1], "ally": None}
    act, seen = _drive(["repeat", "1"],
                       lambda: M._choose_combat_action(state, gd, enemies, [], mem=mem))
    alive = [e for e in enemies if combat.is_alive(e)]
    assert act["type"] == "attack" and act["target"] is alive[1]
    assert len(seen) == 2                                   # 行動選單 + 目標選單


def test_repeat_cast_gated_on_castable():
    gd, state, enemies = _setup()
    mem = {"last": {"type": "cast", "spell_id": "flames"}, "target": enemies[0], "ally": None}
    state.player.magicka = 0                                # 施不起 → repeat 不提供
    _act, seen = _drive(["flee"],
                        lambda: M._choose_combat_action(state, gd, enemies, [], mem=mem))
    assert "repeat" not in seen[0][1]
    state.player.magicka = state.player.max_magicka         # 回魔 → repeat 回來,展開為 cast
    act, seen = _drive(["repeat"],
                       lambda: M._choose_combat_action(state, gd, enemies, [], mem=mem))
    assert act["type"] == "cast" and act["spell_id"] == "flames" and act["target"] is enemies[0]
    assert len(seen) == 1                                   # 沿用存活目標 → 免法術/目標選單


def test_target_menu_marks_last_and_allows_back():
    gd, state, enemies = _setup()
    mem = {"last": None, "target": enemies[1], "ally": None}
    # 攻擊 → 目標選單(標「上次」)→ 返回(None)→ 退回行動選單 → 逃跑
    act, seen = _drive(["attack", None, "flee"],
                       lambda: M._choose_combat_action(state, gd, enemies, [], mem=mem))
    assert act == {"type": "flee"}
    tgt_menu = seen[1]
    assert tgt_menu[0] == "攻擊哪個目標?"
    # 標記在 label 上 —— 重取一次選單檢查文字
    labels = []
    saved = (ui.menu, ui.combat_status_group)
    ui.combat_status_group = lambda *a, **k: None
    ui.menu = lambda title, options, allow_back=False: (labels.extend(o[1] for o in options) or "0")
    try:
        M._choose_enemy_target(state, gd, enemies, [], last=enemies[1])
    finally:
        ui.menu, ui.combat_status_group = saved
    assert any("上次" in l for l in labels)
    assert sum("上次" in l for l in labels) == 1            # 只標一個


def test_repeat_ally_cast_back_cancels_not_burns_turn():
    """審查 MAJOR:repeat 路徑的援護選單「返回」須取消(_back 遞迴)而非帶 None 施放燒回合。"""
    gd, state, enemies = _setup(spells=("heal_other",))
    a1 = combat.spawn_creature(gd, "wolf", state.rng)
    a2 = combat.spawn_creature(gd, "wolf", state.rng)
    allies = [a1, a2]
    mem = {"last": {"type": "cast", "spell_id": "heal_other"}, "target": None, "ally": None}
    # repeat → 援護選單(2 隻同伴)→ 返回(None)→ 退回行動選單 → 逃跑;絕不可回 cast/None
    act, seen = _drive(["repeat", None, "flee"],
                       lambda: M._choose_combat_action(state, gd, enemies, allies, mem=mem))
    assert act == {"type": "flee"}


def test_repeat_ally_cast_skips_expired_summon():
    """審查 MINOR:cmem['ally'] 指向已離場召喚物(health>0 但不在 allies)→ 不得盲目沿用,
    須重開援護選單。"""
    gd, state, enemies = _setup(spells=("heal_other",))
    gone = combat.spawn_creature(gd, "wolf", state.rng)      # 已過期離場(不在 allies)
    a1 = combat.spawn_creature(gd, "wolf", state.rng)
    a2 = combat.spawn_creature(gd, "wolf", state.rng)
    mem = {"last": {"type": "cast", "spell_id": "heal_other"}, "target": None, "ally": gone}
    act, seen = _drive(["repeat", "1"],
                       lambda: M._choose_combat_action(state, gd, enemies, [a1, a2], mem=mem))
    assert act["type"] == "cast" and act["target"] is a2     # 重開選單選了第二隻,非 gone
    assert len(seen) == 2


def test_repeat_ally_cast_hidden_without_living_ally():
    """審查 MINOR:援護型上次動作 + 無存活同伴 → repeat 不提供(否則置頂一鍵=保證浪費回合)。"""
    gd, state, enemies = _setup(spells=("heal_other",))
    mem = {"last": {"type": "cast", "spell_id": "heal_other"}, "target": None, "ally": None}
    _act, seen = _drive(["flee"],
                        lambda: M._choose_combat_action(state, gd, enemies, [], mem=mem))
    assert "repeat" not in seen[0][1]


def test_repeat_label_names_sole_survivor():
    """審查 NIT:記憶目標已死且僅剩一敵 → 標籤如實顯示自動選中的敵名,非「重選目標」。"""
    gd, state, enemies = _setup(n_enemies=2)
    enemies[0].health = 0
    mem = {"last": {"type": "attack"}, "target": enemies[0], "ally": None}
    label = M._repeat_option(state.player, gd, enemies, [], mem)
    assert enemies[1].name in label and "重選" not in label


def test_back_preserves_battle_flags():
    """目標選單返回 → 遞迴重入時 vanish_used/charm_used 原樣傳遞(每場一次不重置)。"""
    gd, state, enemies = _setup()
    calls = []
    orig = M._choose_combat_action

    def spy(state_, gd_, es, als, vanish_used=0, mounted=False, first_round=False,
            charm_used=False, mem=None):
        calls.append((vanish_used, charm_used))
        return orig(state_, gd_, es, als, vanish_used, mounted, first_round, charm_used, mem)

    M._choose_combat_action = spy
    try:
        act, _seen = _drive(["attack", None, "flee"],
                            lambda: M._choose_combat_action(state, gd, enemies, [],
                                                            vanish_used=2, charm_used=True))
    finally:
        M._choose_combat_action = orig
    assert act == {"type": "flee"}
    assert all(c == (2, True) for c in calls)               # 遞迴各層 flags 不變


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_combat_flow 全通過")
