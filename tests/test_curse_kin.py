"""詛咒巢穴與同類(R51)單元測試:巢穴閘、安心進食、密窖/休息、同類招募、免圍捕、
凡人不見同類、內容完整、存檔相容。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import housing, lycanthropy, quests, vampirism


def _state(seed=1, hour=12):
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


def _vampire(gd, c, st):
    c.is_vampire = True
    c.vampire_fed_day = st.time.absolute_hours() // 24
    vampirism.apply_to_character(c, st, gd)
    return c


# --- 巢穴閘 ------------------------------------------------------------
def test_lair_kin_gate():
    from tesrpg import main
    gd, c, st = _state()
    vloc = gd.world["locations"]["bloodmoor_crypt"]
    wloc = gd.world["locations"]["moonhowl_den"]
    assert not main._player_is_lair_kin(c, vloc) and not main._player_is_lair_kin(c, wloc)   # 凡人皆不得入
    _vampire(gd, c, st)
    assert main._player_is_lair_kin(c, vloc) and not main._player_is_lair_kin(c, wloc)        # 吸血鬼只入血族
    gd2, c2, st2 = _state()
    lycanthropy.contract(c2, st2, gd2)
    assert main._player_is_lair_kin(c2, wloc) and not main._player_is_lair_kin(c2, vloc)       # 狼人只入獵群


# --- 安心進食 ----------------------------------------------------------
def test_safe_feed_never_caught():
    gd, c, st = _state(hour=12)                                       # 烈日(平時 0.45 被撞見)
    _vampire(gd, c, st)
    c.vampire_fed_day = st.time.absolute_hours() // 24 - vampirism.STAGE_DAYS * 2   # stage 2
    st.rng.chance = lambda p: True                                    # 強制「被撞見」擲為真
    inf0 = c.infamy
    res = vampirism.feed(st, gd, safe=True)
    assert res["ok"] and res["caught"] is False and c.infamy == inf0  # safe → 必不被撞見、無惡名
    assert vampirism.stage(c, st) == 0                               # 進食壓階
    c.vampire_fed_day = st.time.absolute_hours() // 24 - vampirism.STAGE_DAYS * 2
    assert vampirism.feed(st, gd, safe=False)["caught"] is True       # 對照:非安心 → 同條件被撞見


def test_safe_feed_non_vampire_noop():
    gd, c, st = _state()
    assert vampirism.feed(st, gd, safe=True) == {"ok": False}


# --- 巢穴密窖 + 休息(複用 housing,不需 owns)-------------------------
def test_lair_stash_and_rest():
    from tesrpg.systems import inventory
    gd, c, st = _state()
    _vampire(gd, c, st)
    lair = "bloodmoor_crypt"
    inventory.add_item(c, "ruby", 2)
    assert housing.deposit(c, gd, lair, "ruby", 2)
    assert housing.stash_count(c, lair, "ruby") == 2 and inventory.count_item(c, "ruby") == 0   # 不計負重
    assert housing.withdraw(c, gd, lair, "ruby", 1)
    assert housing.stash_count(c, lair, "ruby") == 1 and inventory.count_item(c, "ruby") == 1
    housing.set_well_rested(c, st.time.absolute_hours())
    assert c.well_rested


# --- 同類招募(複用 party recruit / quests）---------------------------
def _complete_recruit(gd, c, qid, creature, count, lair):
    quests.accept_quest(c, gd, qid)
    for _ in range(count):
        quests.record_kill(c, creature)
    c.location_id = lair
    quests.check_completion(c, gd)


def test_recruit_blood_thrall():
    gd, c, st = _state()
    _vampire(gd, c, st)
    _complete_recruit(gd, c, "recruit_blood_thrall", "vampire_fledgling", 3, "bloodmoor_crypt")
    assert "recruit_blood_thrall" in c.completed_quests
    assert "blood_thrall" in c.companions


def test_recruit_pack_warrior():
    gd, c, st = _state()
    lycanthropy.contract(c, st, gd)
    _complete_recruit(gd, c, "recruit_pack_warrior", "bear", 3, "moonhowl_den")
    assert "recruit_pack_warrior" in c.completed_quests
    assert "pack_warrior" in c.companions


def test_recruit_incomplete_no_companion():
    gd, c, st = _state()
    _vampire(gd, c, st)
    quests.accept_quest(c, gd, "recruit_blood_thrall")
    quests.record_kill(c, "vampire_fledgling")                        # 只殺 1/3
    c.location_id = "bloodmoor_crypt"
    quests.check_completion(c, gd)
    assert "blood_thrall" not in c.companions


# --- 巢穴免圍捕(R50 安全區)------------------------------------------
def test_lair_no_manhunt():
    from tesrpg import main
    from tesrpg.ui import console as ui
    gd, c, st = _state()
    _vampire(gd, c, st)
    c.vampire_fed_day = st.time.absolute_hours() // 24 - vampirism.STAGE_DAYS * 2   # shunned
    c.location_id = "bloodmoor_crypt"                                # 巢穴(wilderness,非城/鎮)
    called = {"b": 0}
    _rb, _msg, _chance = main.run_battle, ui.message, st.rng.chance
    main.run_battle = lambda *a, **k: called.__setitem__("b", called["b"] + 1)
    ui.message = lambda *a, **k: None
    st.rng.chance = lambda p: True
    try:
        res = main._curse_manhunt(st, gd)
    finally:
        main.run_battle, ui.message, st.rng.chance = _rb, _msg, _chance
    assert res is None and called["b"] == 0                          # 巢穴非城鎮 → 不圍捕


def test_mortal_cannot_see_kin_via_generic_talk():
    from tesrpg import main
    gd, c, st = _state()
    c.location_id = "bloodmoor_crypt"
    assert main._living_npcs_at(st, gd) == []                        # 一般攀談不外露巢穴同類


# --- 內容完整 + 存檔 ---------------------------------------------------
def test_content_integrity():
    gd = get_gamedata()
    locs = gd.world["locations"]
    for lid, lair in [("bloodmoor_crypt", "vampire"), ("moonhowl_den", "werewolf")]:
        assert locs[lid].get("lair") == lair
        assert len(locs[lid]["links"]) >= 2                          # R28:非死路
        for d in locs[lid]["links"]:
            assert lid in locs[d]["links"], (lid, d)                 # 雙向
    for nid, qid, cid in [("coven_elder", "recruit_blood_thrall", "blood_thrall"),
                          ("pack_alpha", "recruit_pack_warrior", "pack_warrior")]:
        npc = gd.npcs[nid]
        assert npc["quest"] == qid and npc["location"] in locs
        assert locs[npc["location"]].get("lair")                     # 同類駐於巢穴
        assert gd.quests[qid]["reward"]["companion"] == cid
        comp = gd.companions[cid]
        assert comp.get("recruit_quest") == qid                      # 招募任務雙向對應
        assert 40 <= comp["strength"] <= 65 and comp["max_health"] <= 100 and comp["cost"] == 0   # 在既有同伴帶


def test_save_roundtrip_with_lair_and_kin():
    from tesrpg.systems import inventory
    gd, c, st = _state()
    _vampire(gd, c, st)
    inventory.add_item(c, "ruby", 1)
    housing.deposit(c, gd, "bloodmoor_crypt", "ruby", 1)
    c.companions.append("blood_thrall")
    d = c.to_dict()
    c2 = type(c).from_dict(d)
    assert c2.is_vampire and "blood_thrall" in c2.companions
    assert housing.stash_count(c2, "bloodmoor_crypt", "ruby") == 1
    assert not any("lair" in k for k in d)                           # 巢穴無新存檔欄(走 house_stash)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
