"""R220 姿態鎖施法(使用者 2026-11-26 拍板 B·只鎖雙手重盾姿態;R138 龜殼施法者量測)。

緣起:重盾姿態中施法完全免稅,卻同時拿到物理卸力 38% / 元素卸力 26.6% / 每回合回體 +2。量測(sim_builds 夾具 + 群戰):
姿態專屬優勢集中在「沒堆節點的基本龜殼」(魔人×8 62% vs 持盾不立姿態 24%)與融合大法師(+13pp);姿態中法術威力 ×0.75(方案 A)幾乎無效
(輸出本來有餘裕,限制它的是生存)。鎖施法(方案 B)把姿態專屬優勢收回去;720 達貢四條件全 0%(終王牆原本就守住)。

規則:持**雙手重盾**且立著格擋姿態 → 雙手占滿,結不了印;要施法須先收起姿態(收架本身耗一回合)。
  🔴 範圍:輕盾姿態 / 無姿態 / 獸形 / 非玩家不受影響;**不依 fatigue>0 閘**(姿態旗標還在就是還架著)。

守衛:
  1. `combat.casting_locked` 只在「玩家 + 姿態 + 雙手重盾 + 非獸形」成立;各個相鄰情形(輕盾姿態 / 無姿態 / 無盾 / 獸形 / 非玩家 / 力竭)的邊界
  2. `magic.cast` 的閘:對**全部法術**,鎖定中一律失敗、不耗魔 / 體 / 靈魂 / 任何效果、敵人不受傷;收起姿態後同一道法術照常施放
  3. 戰鬥選單:「施法」仍列出但標「鎖定」,選了只告知原因、不耗回合、不開法術子選單;未鎖定時標籤逐字同舊;「↻ 再施」鎖定中不提供
  4. 立架前可見代價:會施法者的重盾掩體選項標「架著無法施法」,不會施法者逐字同舊
"""
import contextlib
import copy
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import combat, inventory, magic, stats

gd = get_gamedata()
GREAT, LIGHT = "daedric_great_shield", "iron_shield"


def _caster(shield=GREAT, stance=True, cls="mage"):
    c = build_character(gd, name="鎖", sex="male", race="altmer", birthsign="mage", class_id=cls)
    c.skills.update(destruction=100, restoration=100, alteration=100, mysticism=100, conjuration=100, block=100)
    c.spells = list(gd.spells)
    if shield:
        inventory.add_item(c, shield, 1)
        inventory.equip_armor(c, gd, shield)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = c.max_magicka = 99999
    c.fatigue = c.max_fatigue
    c.active_effects.clear()
    if stance:
        c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
    return c


def _foe(i=1):
    return combat.spawn_creature(gd, "bandit", RNG(i))


# ---------------------------------------------------------------- 1. 規則邊界
def test_lock_only_for_player_in_stance_with_a_great_shield():
    assert combat.casting_locked(_caster(), gd) is True
    assert not combat.casting_locked(_caster(stance=False), gd), "無姿態不鎖"
    assert not combat.casting_locked(_caster(shield=LIGHT), gd), "輕盾姿態不鎖(只鎖雙手重盾)"
    assert not combat.casting_locked(_caster(shield=None), gd), "無盾不鎖"
    c = _caster(); c.beast_form = True
    assert not combat.casting_locked(c, gd), "獸形本就不能施法,不重複判定"
    assert not combat.casting_locked(_foe(), gd), "非玩家(敵人 / 召喚物)不受影響"
    c = _caster(); c.fatigue = 0
    assert combat.casting_locked(c, gd), "力竭只暫停卸力 / 稅,不等於收了架 → 仍鎖(不依 fatigue>0 閘)"
    c = _caster(); c.active_effects.clear()
    assert not combat.casting_locked(c, gd), "收起姿態 → 解鎖"
    assert magic.stance_cast_conflict(_caster(), gd) and magic.stance_cast_conflict(_caster(stance=False), gd) is None


# ---------------------------------------------------------------- 2. magic.cast 的閘
def test_every_spell_is_refused_while_locked_without_any_cost_or_effect():
    base = _caster()
    why = magic.stance_cast_conflict(base, gd)
    assert len(gd.spells) >= 60
    for sid in gd.spells:
        c = copy.deepcopy(base); foe = _foe(); dead = _foe(2); dead.health = 0
        before = (c.magicka, c.fatigue, c.health, list(c.active_effects), getattr(c, "soul_tokens", 0), foe.health, list(c.spells))
        r = magic.cast(c, gd, sid, RNG(3), target=foe, battle={"allies": []}, enemies=[foe], corpses=[foe, dead])
        assert r["ok"] is False and r["message"] == why, (sid, r)
        after = (c.magicka, c.fatigue, c.health, list(c.active_effects), getattr(c, "soul_tokens", 0), foe.health, list(c.spells))
        assert after == before, f"{sid}:鎖定中被拒絕卻改了狀態 {before} -> {after}"
        assert r["damage"] == 0 and r["killed"] is False and r["skill_events"] == []


def test_same_spells_cast_normally_once_the_stance_is_dropped_and_for_unlocked_neighbours():
    # (束縛兵刃不列:R204 本來就規定持雙手重盾時凝不出來,與姿態無關)
    for sid, kw in (("flames", {"target": "foe"}), ("heal", {}), ("stoneflesh", {}), ("bound_armor", {}), ("ward", {})):
        for label, c in (("收起姿態", _caster(stance=False)), ("輕盾姿態", _caster(shield=LIGHT))):
            foe = _foe()
            r = magic.cast(c, gd, sid, RNG(3), target=foe if kw else None, battle={"allies": []}, enemies=[foe])
            assert r["ok"] is True, (sid, label, r["message"])
    c = _caster()
    assert magic.cast(c, gd, "heal", RNG(3), battle={"allies": []})["ok"] is False
    c.active_effects[:] = [e for e in c.active_effects if e.get("kind") != "guard_stance"]     # 收架(等同戰鬥選單的「收起格擋姿態」)
    assert magic.cast(c, gd, "heal", RNG(3), battle={"allies": []})["ok"] is True


# ---------------------------------------------------------------- 3. 戰鬥選單
@contextlib.contextmanager
def _menus(script):
    """patch ui.menu / combat_status_group / message:記錄每次選單的 (title, options) 與訊息;依 script 依序作答。"""
    seen, msgs, q = [], [], list(script)
    saved = (ui.menu, ui.combat_status_group, ui.message)
    ui.combat_status_group = lambda *a, **k: None
    ui.menu = lambda title, options, allow_back=False: (seen.append((title, list(options))) or (q.pop(0) if q else "flee"))
    ui.message = lambda text, style=None, **k: msgs.append(text)
    try:
        yield seen, msgs
    finally:
        ui.menu, ui.combat_status_group, ui.message = saved


def _state(c):
    return GameState(player=c, rng=RNG(3))


def _opt(options, key):
    return next((o for o in options if o[0] == key), None)


def test_combat_menu_marks_cast_locked_and_choosing_it_costs_no_turn_and_opens_no_spell_menu():
    c = _caster(); foes = [_foe(), _foe(2)]
    with _menus(["cast", "flee"]) as (seen, msgs):
        act = M._choose_combat_action(_state(c), gd, foes, [], mem=None)
    assert act == {"type": "flee"}, "鎖定中選施法 → 退回行動選單(不耗回合),下一次才選到逃跑"
    assert len(seen) == 2, "只有兩次行動選單、沒有開法術子選單"
    assert all(t != "施放哪道法術?" and not t.startswith("施放哪道法術") for t, _o in seen)
    assert _opt(seen[0][1], "cast")[1] == "施法（鎖定 · 先收起格擋姿態)"
    assert msgs and magic.stance_cast_conflict(c, gd) in msgs, msgs
    # 鎖定時「收起格擋姿態」仍在(解鎖路徑可見)
    assert _opt(seen[0][1], "guard") and "收起格擋姿態" in _opt(seen[0][1], "guard")[1]


def test_unlocked_menu_label_is_byte_identical_and_spell_menu_opens():
    for c in (_caster(stance=False), _caster(shield=LIGHT), _caster(shield=None, stance=False)):
        foes = [_foe(), _foe(2)]
        with _menus(["cast", None]) as (seen, msgs):
            M._choose_combat_action(_state(c), gd, foes, [], mem=None)
        assert _opt(seen[0][1], "cast")[1] == "施法", "未鎖定 → 標籤逐字同舊"
        assert seen[1][0].startswith("施放哪道法術"), "選施法 → 開法術子選單"


def test_repeat_cast_is_not_offered_while_locked_but_is_when_unlocked():
    mem = {"last": {"type": "cast", "spell_id": "heal"}, "target": None, "ally": None}
    assert M._repeat_option(_caster(), gd, [_foe()], [], mem) is None, "鎖定中不給 ↻ 再施(否則置頂一鍵 = 保證失敗)"
    assert "↻ 再施" in M._repeat_option(_caster(stance=False), gd, [_foe()], [], mem)
    assert "↻ 再施" in M._repeat_option(_caster(shield=LIGHT), gd, [_foe()], [], mem)
    assert M._repeat_option(_caster(), gd, [_foe()], [], {"last": {"type": "attack"}, "target": None, "ally": None}).startswith("↻ 再攻"), \
        "鎖施法不影響 ↻ 再攻"


# ---------------------------------------------------------------- 4. 立架前可見代價
def test_great_shield_stance_option_warns_casters_only():
    def guard_label(c):
        with _menus(["flee"]) as (seen, _m):
            M._choose_combat_action(_state(c), gd, [_foe(), _foe(2)], [], mem=None)
        return _opt(seen[0][1], "guard")[1]
    caster = guard_label(_caster(stance=False))
    assert caster.startswith("重盾掩體（") and caster.endswith("· 架著無法施法)"), caster
    warrior = _caster(stance=False, cls="warrior"); warrior.spells = []
    plain = guard_label(warrior)
    assert plain.startswith("重盾掩體（") and "無法施法" not in plain and plain.endswith("/回)"), plain
    light = guard_label(_caster(shield=LIGHT, stance=False))
    assert light == "格擋姿態（攻擊變緩 · 舉盾卸力減傷)", light


def test_new_labels_split_into_chips_losslessly():
    for lbl in ("施法（鎖定 · 先收起格擋姿態)", "重盾掩體（攻擊變緩 · 卸力-38% · 元素-26% · 回氣+2/回 · 架著無法施法)"):
        verb, chips, note = M._split_combat_label(lbl)
        assert verb and note == lbl
        for seg in lbl[lbl.index("（") + 1:-1].replace("，", "·").split("·"):
            assert "".join(seg.split()) in chips[0]["text"], (lbl, seg)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_stance_lock_r220 OK")
