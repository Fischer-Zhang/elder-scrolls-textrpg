"""R134 BOSS 召喚爪牙:summon 譜 schema + try_boss_summon 單一決策點 + 殺王潰散 +
勝利結算三重排除(戰利品/擒魂/擊殺計數·使用者定案)+ 死靈 token 排除。"""

import io

from rich.console import Console

import tesrpg.ui.console as ui

ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

_TGT_PICK = {"mode": "last"}   # "last"=優先打爪牙(append 在後)· "first"=只打 boss


def _menu(title, options, allow_back=False):
    keys = [k for k, _ in options]
    if "你的回合" in title:
        return "attack"
    if "攻擊哪個目標" in title:
        return keys[-1] if _TGT_PICK["mode"] == "last" else keys[0]
    return keys[0]


ui.menu = _menu

import tesrpg.main as main                            # noqa: E402
from tesrpg.creation import build_character            # noqa: E402
from tesrpg.gamedata import get_gamedata                # noqa: E402
from tesrpg.rng import RNG                               # noqa: E402
from tesrpg.state import GameState, GameTime              # noqa: E402
from tesrpg.systems import combat, inventory, mastery, stats   # noqa: E402

gd = get_gamedata()


# ---------- schema lint ----------
def test_summon_spec_schema():
    """summon 譜:爪牙存在且非 solo;召主是 solo 高危王;wave/cap/cooldown 合法;d4 早期王不配。"""
    n = 0
    for bid, b in gd.bestiary.items():
        spec = b.get("summon")
        if not spec:
            continue
        n += 1
        assert b.get("solo"), f"{bid}:召主須為 solo boss"
        assert b.get("danger", 0) >= 5, f"{bid}:召主須 danger≥5(d4 早期王不配·保逃跑機率)"
        add = gd.bestiary.get(spec["id"])
        assert add is not None, f"{bid}:爪牙 {spec['id']} 不存在"
        assert not add.get("solo"), f"{bid}:爪牙不得為 solo"
        assert 1 <= int(spec.get("wave", 2)) <= int(spec.get("cap", 6)) <= 6, f"{bid}:wave/cap 越界"
        assert int(spec.get("cooldown", 3)) >= 1, f"{bid}:cooldown 須 ≥1"
    assert n >= 18, f"名冊應有 ≥18 王配譜(現 {n})"
    # d4 早期王明確不配(vampire_lord/werewolf_alpha·中期玩家逃跑機率保護)
    for bid in ("vampire_lord", "werewolf_alpha"):
        assert not gd.bestiary[bid].get("summon"), f"{bid}(d4 早期王)不得配召喚"


# ---------- try_boss_summon 單一決策點 ----------
def test_try_boss_summon_wave_flag_and_no_resummon_while_alive():
    boss = combat.spawn_creature(gd, "grave_tyrant", RNG(1))
    enemies = [boss]
    msg = combat.try_boss_summon(boss, enemies, gd, RNG(2))
    assert msg and len(enemies) == 3                      # 召出 2 隻
    assert all(getattr(e, "summoned", False) for e in enemies[1:])
    assert boss._summon_total == 2
    assert combat.try_boss_summon(boss, enemies, gd, RNG(3)) is None   # 爪牙存活 → 不重召


def test_try_boss_summon_cooldown_and_cap():
    boss = combat.spawn_creature(gd, "wish_eaten_sorcerer", RNG(1))    # wave1 / cap2 / cd3
    enemies = [boss]
    assert combat.try_boss_summon(boss, enemies, gd, RNG(2))           # 第一波(total 1)
    enemies[1].health = 0                                              # 殺掉爪牙
    for _ in range(3):                                                 # 冷卻未到 → None
        assert combat.try_boss_summon(boss, enemies, gd, RNG(3)) is None
    assert combat.try_boss_summon(boss, enemies, gd, RNG(4))           # 冷卻到 → 第二波(total 2 = cap)
    for e in enemies[1:]:
        e.health = 0
    for _ in range(6):                                                 # 達總量上限 → 永不再召
        assert combat.try_boss_summon(boss, enemies, gd, RNG(5)) is None
    assert boss._summon_total == 2


def test_try_boss_summon_none_for_non_summoner():
    wolf = combat.spawn_creature(gd, "wolf", RNG(1))
    enemies = [wolf]
    assert combat.try_boss_summon(wolf, enemies, gd, RNG(2)) is None
    assert len(enemies) == 1


# ---------- 嘲諷招 fallback(玩家召喚模板被敵方使用)----------
def test_choose_enemy_attack_never_returns_taunt():
    """summoned_dremora 帶 R105 嘲諷招(無 damage 鍵)→ 敵方選招必退回基礎單招,絕不回無傷害招。"""
    for s in range(60):
        cre = combat.spawn_creature(gd, "summoned_dremora", RNG(s))
        atk = combat.choose_enemy_attack(cre, RNG(s * 7 + 1), None)
        assert atk and not atk.get("taunt") and "damage" in atk


# ---------- 殺王=爪牙潰散 ----------
def test_scatter_orphan_summons_unit():
    boss = combat.spawn_creature(gd, "grave_tyrant", RNG(1))
    enemies = [boss]
    combat.try_boss_summon(boss, enemies, gd, RNG(2))
    boss.health = 0                                       # 召主死
    assert combat.scatter_orphan_summons(enemies, gd) is True
    assert all(not getattr(e, "summoned", False) for e in enemies)     # 存活爪牙已移除
    assert combat.scatter_orphan_summons(enemies, gd) is False         # 冪等:無爪牙 → False


# ---------- run_battle 整合:三重排除 + token 排除 ----------
def _warrior():
    c = build_character(gd, name="戰", sex="m", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(blade=100, heavy_armor=100, conjuration=25)
    c.attributes.update(strength=100, endurance=100)
    c.weapon = "daedric_sword"
    inventory.add_item(c, "daedric_sword", 1)
    mastery.choose(c, gd, "conjuration_25", "death_attunement")   # 開死靈經濟 → 驗 token 排除
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def test_run_battle_summon_triple_exclusion():
    """玩家親手殺掉召喚爪牙 → 不計擊殺、無戰利品、不積 token;召主照常結算。"""
    _TGT_PICK["mode"] = "last"                            # 優先打(後 append 的)爪牙
    c = _warrior()
    st = GameState(player=c, rng=RNG(7), time=GameTime())
    boss = combat.spawn_creature(gd, "grave_tyrant", RNG(1))
    enemies = [boss]
    looted = []
    orig_loot = combat.grant_loot
    combat.grant_loot = lambda p, e, g, r: (looted.append(e.template_id), orig_loot(p, e, g, r))[1]
    try:
        assert main.run_battle(st, gd, enemies) == "victory"
    finally:
        combat.grant_loot = orig_loot
    assert boss._summon_total >= 2                        # 戰鬥中確實召了
    assert any(getattr(e, "summoned", False) and not combat.is_alive(e)
               for e in enemies)                          # 玩家「確實親手殺過」爪牙(防斷言空洞化·審查建議)
    assert c.kill_counts.get("skeleton", 0) == 0          # 擊殺計數排除
    assert c.kill_counts.get("grave_tyrant", 0) == 1      # 召主照常計
    assert looted == ["grave_tyrant"]                     # 戰利品排除:只結算召主
    assert c.soul_tokens == 1                             # 死靈 token:只計召主(爪牙排除)


def test_run_battle_scatter_on_boss_death():
    """只打 boss(不理爪牙)→ 殺王後存活爪牙潰散,勝利;爪牙全程零結算。"""
    _TGT_PICK["mode"] = "first"                           # 永遠打第一個(= boss)
    c = _warrior()
    st = GameState(player=c, rng=RNG(11), time=GameTime())
    boss = combat.spawn_creature(gd, "grave_tyrant", RNG(2))
    enemies = [boss]
    assert main.run_battle(st, gd, enemies) == "victory"
    assert boss._summon_total >= 2
    assert all(not getattr(e, "summoned", False) for e in enemies)     # 潰散者已自清單移除
    assert c.kill_counts.get("skeleton", 0) == 0
    assert c.soul_tokens == 1


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
