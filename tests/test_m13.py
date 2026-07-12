"""M13:範圍(AoE)法術 —— 全體傷害 / 全體狀態,逐敵吃抗性。"""

import io

from rich.console import Console

import tesrpg.ui.console as ui

ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)


def _aoe_menu(title, options, allow_back=False):
    keys = [k for k, _ in options]
    if "你的回合" in title:                 # 沒法力時退回攻擊
        return "cast" if "cast" in keys else "attack"
    if "施放哪道法術" in title:
        return "fire_storm" if "fire_storm" in keys else keys[0]
    return keys[0]


ui.menu = _aoe_menu   # D2:戰鬥動作分桶純 web 呈現;此測試無 web backend → _grouped_combat_menu 退回扁平 ui.menu

import tesrpg.main as main                       # noqa: E402
from tesrpg.creation import build_character        # noqa: E402
from tesrpg.gamedata import get_gamedata            # noqa: E402
from tesrpg.rng import RNG                           # noqa: E402
from tesrpg.state import GameState, GameTime          # noqa: E402
from tesrpg.systems import combat, magic, stats       # noqa: E402


def _mage(magicka=999):
    gd = get_gamedata()
    c = build_character(gd, name="法", sex="f", race="breton", birthsign="mage", class_id="mage")
    c.skills["destruction"] = 60
    c.skills["illusion"] = 60
    stats.recompute_max_resources(c, restore_full=True)
    c.magicka = magicka
    return gd, c


# --- AoE 傷害 -----------------------------------------------------------
def test_damage_all_hits_every_enemy_with_resist():
    gd, c = _mage()
    enemies = [combat.spawn_creature(gd, "bandit", RNG(1)),
               combat.spawn_creature(gd, "dremora", RNG(2)),    # 抗火
               combat.spawn_creature(gd, "draugr", RNG(3))]     # 弱火
    hp = [e.health for e in enemies]
    ev = magic.cast(c, gd, "fire_storm", RNG(5), enemies=enemies)
    assert ev["ok"]
    dealt = [h - e.health for h, e in zip(hp, enemies)]
    assert all(d > 0 for d in dealt)              # 全部都被打到
    assert dealt[1] < dealt[0] < dealt[2]         # 抗火 < 一般 < 弱火


def test_aoe_only_living_enemies():
    gd, c = _mage()
    dead = combat.spawn_creature(gd, "wolf", RNG(1))
    dead.health = 0
    alive = combat.spawn_creature(gd, "wolf", RNG(2))
    magic.cast(c, gd, "fire_storm", RNG(0), enemies=[dead, alive])
    assert dead.health == 0 and alive.health < alive.max_health


def test_aoe_refunds_with_no_targets():
    gd, c = _mage()
    m0 = c.magicka
    r = magic.cast(c, gd, "fire_storm", RNG(0), enemies=[])
    assert not r["ok"] and c.magicka == m0


# --- AoE 狀態 -----------------------------------------------------------
def test_status_all_applies_paralyze_and_fear():
    gd, c = _mage()
    enemies = [combat.spawn_creature(gd, "wolf", RNG(i)) for i in range(3)]
    magic.cast(c, gd, "mass_paralysis", RNG(0), enemies=enemies)
    assert all(magic.is_paralyzed(e) for e in enemies)
    # status_all 另一狀態出口:rout 對全體施加 fear(同引擎 kind,不同 status payload)
    enemies2 = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(2)]
    magic.cast(c, gd, "rout", RNG(0), enemies=enemies2)
    assert all(magic.is_feared(e) for e in enemies2)


def test_damage_status_all():
    gd, c = _mage()
    enemies = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(2)]
    hp = [e.health for e in enemies]
    magic.cast(c, gd, "frost_nova", RNG(0), enemies=enemies)
    assert all(e.health < h for h, e in zip(hp, enemies))          # 有傷害
    assert all(any(x["kind"] == "benumb" for x in e.active_effects) for e in enemies)  # 且附凍麻(AoE 控場)


def test_aoe_damage_field_is_actual_loss():
    """回歸審查 [1]:damage 欄位應為實際扣血總和,不計溢殺。"""
    gd, c = _mage()
    enemies = [combat.spawn_creature(gd, "wolf", RNG(1)), combat.spawn_creature(gd, "wolf", RNG(2))]
    for e in enemies:
        e.health = 3                          # 低血,必定溢殺
        e.max_health = 25
    hp_total = sum(e.health for e in enemies)
    ev = magic.cast(c, gd, "fire_storm", RNG(0), enemies=enemies)
    assert ev["damage"] == hp_total           # 6,而非灌水的 ~50


def test_cast_failure_schema_consistent():
    """回歸審查 [2]:失敗回傳也須含 damage/killed(與成功一致)。"""
    gd, c = _mage(magicka=0)
    for r in (magic.cast(c, gd, "flames", RNG(0), target=combat.spawn_creature(gd, "wolf", RNG(0))),
              magic.cast(c, gd, "fire_storm", RNG(0), enemies=[combat.spawn_creature(gd, "wolf", RNG(0))])):
        assert r["ok"] is False
        assert "damage" in r and "killed" in r and "skill_events" in r


def test_aoe_costs_magicka_and_gated():
    gd, c = _mage(magicka=10)
    assert not magic.can_cast(c, gd, "fire_storm")     # 法力不足
    r = magic.cast(c, gd, "fire_storm", RNG(0),
                   enemies=[combat.spawn_creature(gd, "wolf", RNG(0))])
    assert not r["ok"]


# --- run_battle 整合:AoE 清群 -----------------------------------------
def test_aoe_clears_group_in_run_battle():
    ui.menu = _aoe_menu          # 確保用本模組的選單(避免其他測試模組殘留的 patch)
    gd, c = _mage(magicka=999)
    c.max_health = 200
    c.health = 200
    if "fire_storm" not in c.spells:
        c.spells.append("fire_storm")          # 法師公會習得的 AoE
    st = GameState(player=c, rng=RNG(2), time=GameTime())
    enemies = [combat.spawn_creature(gd, "wolf", RNG(i)) for i in range(3)]
    assert main.run_battle(st, gd, enemies) == "victory"
    assert all(not combat.is_alive(e) for e in enemies)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m13 OK")
