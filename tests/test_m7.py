"""M7:事件引擎 —— 觸發資格、選項閘門、技能判定、效果套用。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import events, inventory


def _state(location="bruma"):
    gd = get_gamedata()
    c = build_character(gd, name="客", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    c.location_id = location
    return gd, c, GameState(player=c, time=GameTime())


# --- 觸發資格 -----------------------------------------------------------
def test_context_gating():
    gd, c, st = _state("imperial_road")    # wilderness
    travel = events.eligible_events(st, gd, "travel")
    assert "highwayman" in travel
    # arrive 事件需城鎮;在荒野不該觸發
    assert "town_crier" not in events.eligible_events(st, gd, "travel")
    assert "town_crier" not in events.eligible_events(st, gd, "arrive")


def test_location_type_gating():
    gd, c, st = _state("bruma")            # city
    assert "town_crier" in events.eligible_events(st, gd, "arrive")
    # 城市休息不該出現「營地襲擊」(限 wilderness/dungeon)
    assert "camp_ambush" not in events.eligible_events(st, gd, "rest")
    st.player.location_id = "pale_pass"    # wilderness
    assert "camp_ambush" in events.eligible_events(st, gd, "rest")


def test_pick_only_eligible():
    gd, c, st = _state("bruma")
    for i in range(50):
        eid = events.pick_event(st, gd, "arrive", RNG(i))
        assert eid is None or gd.location("bruma")["type"] in gd.events[eid]["trigger"].get("location_types", ["city"])


# --- 選項需求閘門 -------------------------------------------------------
def test_option_requirements():
    gd, c, st = _state()
    pay = {"requirements": {"gold_min": 50}}
    c.gold = 10
    assert not events.option_available(c, gd, pay)
    c.gold = 80
    assert events.option_available(c, gd, pay)

    need_item = {"requirements": {"item": "minor_healing_potion"}}
    assert events.option_available(c, gd, need_item)      # 起始就有 2 瓶
    inventory.remove_item(c, "minor_healing_potion", 2)
    assert not events.option_available(c, gd, need_item)

    skillreq = {"requirements": {"skill_min": {"security": 30}}}
    c.skills["security"] = 10
    assert not events.option_available(c, gd, skillreq)
    c.skills["security"] = 40
    assert events.option_available(c, gd, skillreq)


def test_quest_available_requirement():
    gd, c, st = _state()
    opt = {"requirements": {"quest_available": "job_bandit"}}
    assert events.option_available(c, gd, opt)
    c.quests["job_bandit"] = {}
    assert not events.option_available(c, gd, opt)         # 已接,不再提供


# --- 技能判定 -----------------------------------------------------------
def test_check_chance_monotonic():
    gd, c, st = _state()
    chk = {"skill": "speechcraft", "difficulty": 40}
    c.skills["speechcraft"] = 10
    lo = events.check_chance(c, chk)
    c.skills["speechcraft"] = 90
    hi = events.check_chance(c, chk)
    assert 0.1 <= lo < hi <= 0.95


# --- 效果套用 -----------------------------------------------------------
def test_apply_effects_basic():
    gd, c, st = _state()
    c.gold = 100
    res = events.apply_effects(st, gd, [
        {"type": "gold", "amount": -30},
        {"type": "item", "item": "ruby", "qty": 1},
        {"type": "fame", "amount": 5},
        {"type": "skill_xp", "skill": "speechcraft", "amount": 1.0},
    ], RNG(0))
    assert c.gold == 70 and inventory.count_item(c, "ruby") == 1 and c.fame == 5
    assert c.skill_xp.get("speechcraft", 0) > 0
    assert res["combat"] == []


def test_heal_full_and_damage():
    gd, c, st = _state()
    c.health = 1
    events.apply_effects(st, gd, [{"type": "heal", "amount": "full"}], RNG(0))
    assert c.health == c.max_health
    events.apply_effects(st, gd, [{"type": "damage", "amount": 9999}], RNG(0))
    assert c.health == 0                                   # 致死由 main 判定


def test_combat_effect_deferred():
    gd, c, st = _state()
    res = events.apply_effects(st, gd, [{"type": "combat", "creature": "wolf"}], RNG(0))
    assert res["combat"] == ["wolf"]                       # 交給 main 跑 run_battle


def test_start_quest_and_bounty():
    gd, c, st = _state("imperial_road")
    events.apply_effects(st, gd, [{"type": "start_quest", "quest": "job_wolf"}], RNG(0))
    assert "job_wolf" in c.quests
    # 重複 start_quest 不該出錯或重置
    events.apply_effects(st, gd, [{"type": "start_quest", "quest": "job_wolf"}], RNG(0))
    assert "job_wolf" in c.quests
    events.apply_effects(st, gd, [{"type": "bounty", "amount": 50}], RNG(0))
    from tesrpg.systems import crime
    assert crime.bounty(c, "賽羅迪爾") == 50


def test_effect_feedback_messages():
    """回歸(審查):失去物品 / 惡名 也要有 UI 訊息(與獲得/聲望對稱)。"""
    gd, c, st = _state()
    inventory.add_item(c, "ruby", 1)
    res = events.apply_effects(st, gd, [
        {"type": "item", "item": "ruby", "qty": -1},
        {"type": "infamy", "amount": 5},
    ], RNG(0))
    joined = " ".join(res["messages"])
    assert "失去" in joined and "紅寶石" in joined
    assert "惡名" in joined


def test_learn_spell_no_dup():
    gd, c, st = _state()
    c.spells = []
    events.apply_effects(st, gd, [{"type": "learn_spell", "spell": "flames"}], RNG(0))
    events.apply_effects(st, gd, [{"type": "learn_spell", "spell": "flames"}], RNG(0))
    assert c.spells.count("flames") == 1


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m7 OK")
