"""M12:多敵戰鬥 + 團隊戰鬥(傭兵同伴 / 召喚物)。

run_battle 是互動式的,故此處先把 UI 換成無輸出 + 自動選「攻擊最前目標」。
"""

import io

from rich.console import Console

import tesrpg.ui.console as ui

ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)


def _auto_menu(title, options, allow_back=False):
    if "你的回合" in title:
        return "attack"
    return options[0][0]      # 目標/法術等一律選第一個


ui.menu = _auto_menu

import tesrpg.main as main          # noqa: E402  (UI 須先 patch)
from tesrpg.creation import build_character   # noqa: E402
from tesrpg.gamedata import get_gamedata      # noqa: E402
from tesrpg.rng import RNG                     # noqa: E402
from tesrpg.state import GameState, GameTime   # noqa: E402
from tesrpg.systems import combat              # noqa: E402


def _strong(party=None):
    gd = get_gamedata()
    c = build_character(gd, name="H", sex="m", race="redguard", birthsign="warrior", class_id="warrior")
    c.skills["blade"] = 90
    c.attributes["strength"] = 95
    c.max_health = 400
    c.health = 400
    c.max_fatigue = 500
    c.fatigue = 500
    c.weapon = "steel_sword"
    if party:
        c.companions = party
    return gd, c


def _state(c, seed=1):
    return GameState(player=c, rng=RNG(seed), time=GameTime())


# --- 群體生成 -----------------------------------------------------------
def test_spawn_companion_is_creature_ally():
    gd = get_gamedata()
    a = combat.spawn_companion(gd, "sellsword", RNG(0))
    assert a.health == a.max_health > 0 and a.summon_turns is None
    assert a.attack["damage"] > 0


def test_pick_player_side_target():
    gd, c = _strong()
    ally = combat.spawn_companion(gd, "shieldmaiden", RNG(0))
    seen = set()
    for i in range(50):
        seen.add(combat.pick_player_side_target(c, [ally], RNG(i)) is c)
    assert seen == {True, False}            # 有時打玩家、有時打同伴
    # 無存活同伴 → 一定打玩家
    ally.health = 0
    assert combat.pick_player_side_target(c, [ally], RNG(0)) is c


# --- 多敵戰鬥 -----------------------------------------------------------
def test_group_victory_loots_and_records_all():
    gd, c = _strong()
    st = _state(c, 2)
    enemies = [combat.spawn_creature(gd, "bandit", RNG(1)),
               combat.spawn_creature(gd, "wolf", RNG(2)),
               combat.spawn_creature(gd, "giant_rat", RNG(3))]
    assert main.run_battle(st, gd, enemies) == "victory"
    assert all(not combat.is_alive(e) for e in enemies)
    assert c.kill_counts.get("bandit") == 1 and c.kill_counts.get("wolf") == 1
    assert c.kill_counts.get("giant_rat") == 1


def test_single_enemy_still_works():
    gd, c = _strong()
    st = _state(c, 1)
    assert main.run_battle(st, gd, combat.spawn_creature(gd, "giant_rat", RNG(1))) == "victory"


def test_player_dies_to_overwhelming_group():
    gd = get_gamedata()
    c = build_character(gd, name="W", sex="m", race="breton", birthsign="mage", class_id="mage")
    c.max_health = 10
    c.health = 10
    c.weapon = "iron_dagger"
    st = _state(c, 7)
    enemies = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(3)]
    assert main.run_battle(st, gd, enemies) == "dead"


# --- 團隊 ---------------------------------------------------------------
def test_companion_party_survives_and_persists():
    gd, c = _strong(["sellsword", "shieldmaiden"])
    st = _state(c, 3)
    enemies = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(3)]
    assert main.run_battle(st, gd, enemies) == "victory"
    assert c.companions == ["sellsword", "shieldmaiden"]      # 同伴留在隊伍


def test_unknown_companion_id_skipped_not_crash():
    """回歸審查 [2]:存檔殘留的、已不存在的同伴 id 不該讓戰鬥崩潰。"""
    gd, c = _strong(["sellsword", "ghost_that_was_removed"])
    st = _state(c, 1)
    assert main.run_battle(st, gd, combat.spawn_creature(gd, "giant_rat", RNG(1))) == "victory"


def test_hire_dismiss():
    gd, c = _strong()
    c.gold = 1000
    q = ["hire", "sellsword", "hire", "shieldmaiden", None]
    ui.menu = lambda title, options, allow_back=False: q.pop(0)
    try:
        main.action_inn(_state(c), gd)
        assert c.companions == ["sellsword", "shieldmaiden"] and c.gold == 1000 - 200 - 240
        q2 = ["dismiss", "sellsword", None]
        ui.menu = lambda title, options, allow_back=False: q2.pop(0)
        main.action_inn(_state(c), gd)
        assert c.companions == ["shieldmaiden"]
    finally:
        ui.menu = _auto_menu


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m12 OK")
