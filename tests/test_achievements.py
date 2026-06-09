"""成就(Achievements)單元測試。

涵蓋:各 cond.type 判定、初生角色幾乎零達成、出貨 id 合法、未知 type inert、
傳奇結算整合(列出但不加分)、評估器唯讀(零 char 變動)、earned/locked 配對。
"""

import copy

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import achievements, legacy, mastery


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="A", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, c


def _ids(gd, c):
    return {a["id"] for a in achievements.earned(c, gd)}


def test_kills_total_and_kill_boss():
    gd, c = _char()
    assert "first_blood" not in _ids(gd, c)
    c.kill_counts = {"bandit": 50}
    assert "first_blood" in _ids(gd, c) and "slayer" not in _ids(gd, c)
    c.kill_counts = {"bandit": 500}
    assert "slayer" in _ids(gd, c)
    assert "ancient_dragon" in gd.bestiary
    c.kill_counts = {"ancient_dragon": 1}
    assert "dragonslayer" in _ids(gd, c)


def test_progress_counters():
    gd, c = _char()
    c.cleared_dungeons = list(range(10))
    assert "delver" in _ids(gd, c)
    c.completed_quests = list(range(30))
    assert "questmaster" in _ids(gd, c)
    c.level = 20
    assert "veteran_hero" in _ids(gd, c)
    c.gold = 50000
    assert "magnate" in _ids(gd, c)
    c.murders = 10
    assert "bloodprice" in _ids(gd, c)


def test_provinces_and_landmarks():
    gd, c = _char()
    locs = gd.world["locations"]
    by_prov = {}
    for lid, l in locs.items():
        by_prov.setdefault(l["province"], lid)
    c.visited_locations = list(by_prov.values())[:4]
    assert "wayfarer" in _ids(gd, c)
    c.discovered_landmarks = list(gd.landmarks.keys())[:8] + ["bogus_landmark"]   # 毀損 id 不計
    assert "cartographer" in _ids(gd, c)


def test_skill_cap_uses_base_only():
    gd, c = _char()
    for s in ("blade", "block", "heavy_armor"):
        c.skills[s] = 100
    assert "grandmaster_skill" in _ids(gd, c)
    # 裝備疊加不算(只認 base):一項 base 退回 99 即不達 3 項
    c.skills["blade"] = 99
    c.equip_skill_bonus = {"blade": 5}     # 有效 104 但 base 99
    assert "grandmaster_skill" not in _ids(gd, c)


def test_guildmaster_any_and_specific():
    gd, c = _char()
    assert "guildmaster" not in _ids(gd, c)
    c.factions["mages_guild"] = len(gd.factions["mages_guild"]["ranks"]) - 1
    ids = _ids(gd, c)
    assert "guildmaster" in ids and "archmage" in ids and "listener" not in ids
    c.factions["dark_brotherhood"] = len(gd.factions["dark_brotherhood"]["ranks"]) - 1
    assert "listener" in _ids(gd, c)


def test_mastery_count():
    gd, c = _char()
    c.skills.update({"block": 50, "heavy_armor": 75, "destruction": 100, "security": 75})
    # v2:達門檻後須二選一銘刻,milestone_walker 計的是「已選」的里程碑數
    for nid, oid in (("block_50", "shieldwall"), ("heavy_armor_75", "bulwark"),
                     ("destruction_100", "overload"), ("security_75", "master_floor")):
        mastery.choose(c, gd, nid, oid)
    assert "milestone_walker" in _ids(gd, c)


def test_dominion_allegiance_vampire():
    gd, c = _char()
    c.thaneships = ["bruma", "kvatch"]
    assert "thane" in _ids(gd, c)
    c.allegiance = "own"
    assert "self_made_king" in _ids(gd, c)
    c.city_faction = {"bruma": "own", "kvatch": "own", "chorrol": "own"}
    assert "warlord" in _ids(gd, c)
    c.is_vampire = True
    assert "child_of_night" in _ids(gd, c)


def test_pure_spec_not_trivially_earned():
    """初生角色雖有起始專精偏向,但未達絕對門檻 → 不該得『純粹流派』。"""
    gd, c = _char()
    assert not ({"purist_warrior", "purist_mage", "purist_thief"} & _ids(gd, c))
    for s in gd.skills_by_spec("combat"):
        c.skills[s] = 100
    for s in list(gd.skills_by_spec("magic")) + list(gd.skills_by_spec("stealth")):
        c.skills[s] = 5
    assert "purist_warrior" in _ids(gd, c)


def test_fresh_character_earns_none():
    gd, c = _char()
    assert achievements.earned(c, gd) == []


def test_shipped_ids_are_legal():
    gd = get_gamedata()
    for a in gd.achievements:
        t = a["cond"]["type"]
        assert t in achievements._IMPLEMENTED_TYPES, f"未實作的 type:{t}"
        assert a.get("id") and a.get("name") and a.get("desc")
        if t == "kill_boss":
            assert a["cond"]["creature"] in gd.bestiary, a["cond"]["creature"]
        if t == "guildmaster":
            assert a["cond"]["faction"] in gd.factions, a["cond"]["faction"]
        if t == "allegiance":
            assert a["cond"]["cause"] in {"imperial", "independent", "daedric", "own"}
        if t == "pure_spec":
            assert a["cond"]["spec"] in {"combat", "magic", "stealth"}
    ids = [a["id"] for a in gd.achievements]
    assert len(ids) == len(set(ids)), "成就 id 重複"


def test_unimplemented_type_is_inert():
    gd, c = _char()
    bogus = {"id": "x", "name": "幻", "desc": "?", "cond": {"type": "not_real"}}
    gd.achievements.append(bogus)
    try:
        assert all(a["id"] != "x" for a in achievements.earned(c, gd))
        assert all(a["id"] != "x" for a in achievements._defs(gd))
    finally:
        gd.achievements.remove(bogus)


def test_evaluator_is_read_only():
    gd, c = _char(level=20, gold=50000, murders=10)
    c.kill_counts = {"ancient_dragon": 1, "bandit": 500}
    c.factions["mages_guild"] = 5
    snapshot = copy.deepcopy(c.to_dict())
    achievements.earned(c, gd)
    achievements.earned_and_locked(c, gd)
    assert c.to_dict() == snapshot


def test_legacy_integration_lists_without_scoring():
    gd, c = _char()
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    base = legacy.compute(st, gd)["score"]
    # murders 是成就條件(血債累累)但**不在 score 公式內** → 達成新成就而 score 不變,
    # 證明成就純表彰、不參與計分(避免雙重計分)。
    c.murders = 10
    out = legacy.compute(st, gd)
    assert "血債累累" in out["achievements"]
    assert out["score"] == base
    assert out["achievements_total"] == len(achievements._defs(gd))
    assert all(isinstance(n, str) for n in out["achievements"])


def test_earned_and_locked_partition():
    gd, c = _char(level=20)
    won, locked = achievements.earned_and_locked(c, gd)
    all_ids = {a["id"] for a in achievements._defs(gd)}
    assert {a["id"] for a in won} | {a["id"] for a in locked} == all_ids
    assert not ({a["id"] for a in won} & {a["id"] for a in locked})


def run():
    test_kills_total_and_kill_boss()
    test_progress_counters()
    test_provinces_and_landmarks()
    test_skill_cap_uses_base_only()
    test_guildmaster_any_and_specific()
    test_mastery_count()
    test_dominion_allegiance_vampire()
    test_pure_spec_not_trivially_earned()
    test_fresh_character_earns_none()
    test_shipped_ids_are_legal()
    test_unimplemented_type_is_inert()
    test_evaluator_is_read_only()
    test_legacy_integration_lists_without_scoring()
    test_earned_and_locked_partition()


if __name__ == "__main__":
    run()
    print("test_achievements 全通過")
