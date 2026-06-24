"""R84 犯罪/通緝深化 —— 威脅側:賞金獵人路途追殺 + 新怪 schema。

(回報側 refuge/fence/contracts 測試於 Phase 2 併入本檔。)
"""

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.state import GameState, GameTime
from tesrpg.systems import crime, magic


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="imperial", birthsign="thief", class_id="thief")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime())


def test_ambush_gated_by_active_heat_and_tier_count():
    gd, st = _state()
    calls = []
    orig = main.offer_battle
    main.offer_battle = lambda s, g, enemies, **k: calls.append(list(enemies)) or None
    try:
        st.player.bounties = {}                         # heat 0 → 不攔
        assert main._bounty_hunter_ambush(st, gd) is None
        assert calls == []
        st.player.bounties = {"天際": 400}              # heat 2 → 2 名 mercenary_tracker
        main._bounty_hunter_ambush(st, gd)
        assert len(calls) == 1 and len(calls[0]) == 2
        assert all(e.template_id == "mercenary_tracker" for e in calls[0])
        calls.clear()
        st.player.bounties = {"天際": 800}              # heat 3 → 3 名 master_hunter
        main._bounty_hunter_ambush(st, gd)
        assert len(calls[0]) == 3 and all(e.template_id == "master_hunter" for e in calls[0])
    finally:
        main.offer_battle = orig


def test_ambush_does_not_mutate_bounty_or_infamy():
    """自衛 → 不加賞金/惡名(保『付清即冷卻路途』的可清契約)。"""
    gd, st = _state(infamy=10)
    st.player.bounties = {"天際": 800}
    before_inf, before_b = st.player.infamy, dict(st.player.bounties)
    orig = main.offer_battle
    main.offer_battle = lambda *a, **k: None
    try:
        main._bounty_hunter_ambush(st, gd)
    finally:
        main.offer_battle = orig
    assert st.player.infamy == before_inf
    assert st.player.bounties == before_b


def test_bounty_hunter_creatures_schema_spawn_only():
    gd = get_gamedata()
    legal_status = {"dot"} | set(magic._CONTROL_KINDS)
    for tid in ("bounty_hunter", "mercenary_tracker", "master_hunter", "city_captain"):
        c = gd.bestiary[tid]
        assert c.get("sentient") is True
        assert c["min_level"] == 99 and c["weight"] == 0   # spawn-only:不進 random 池(與 sim 隔離)
        assert not c.get("solo")                            # 群體型(不得 collapse 單王)
        for ln in c.get("loot", []):
            assert gd.item_or_none(ln["item"]), (tid, ln["item"])
        for atk in c.get("attacks", []):
            oh = atk.get("on_hit")
            if oh:
                assert oh["status"] in legal_status, (tid, oh["status"])


def test_tier_template_mapping():
    assert main._BOUNTY_HUNT_TIER == {1: "bounty_hunter", 2: "mercenary_tracker", 3: "master_hunter"}


# --- 回報側:藏身處 / 銷贓 / 地下委託 -----------------------------------------
def test_refuges_are_safe_zones():
    gd = get_gamedata()
    refuges = [k for k, d in gd.world["locations"].items() if d.get("refuge")]
    assert len(refuges) >= 3
    for r in refuges:
        d = gd.location(r)
        assert d["danger"] == 1 and d["type"] == "wilderness"   # danger1·荒野 → guard/manhunt 天然不觸發
        assert d["type"] not in ("city", "town")
        assert not d.get("services")                            # 無 city service(銷贓走 action_fence)


def test_black_market_items_exist_and_no_arbitrage():
    """黑市每件:買價恆 > 銷贓價(防套利地板),且 id 合法。"""
    gd = get_gamedata()
    from tesrpg.creation import build_character
    from tesrpg.systems import world
    c = build_character(gd, name="x", sex="male", race="imperial", birthsign="thief", class_id="thief")
    c.infamy = 200                                              # 頂階 fence_bonus(最大加價下測地板)
    for iid in main._BLACK_MARKET:
        assert gd.item_or_none(iid), iid
        fsell = int(world.sell_price(c, gd, iid) * (1 + crime.fence_bonus(c)))
        buy = max(world.buy_price(c, gd, iid), fsell + 1)
        assert buy > fsell, (iid, buy, fsell)                  # 買來回銷必虧


def test_underworld_contracts_schema():
    """ucomm_* 地下委託:repeatable·source board·reward ⊆ {gold,infamy}·gold 在正規委託區間·無 fame。"""
    gd = get_gamedata()
    ucomm = {k: v for k, v in gd.quests.items() if k.startswith("ucomm_")}
    assert len(ucomm) >= 6
    for k, q in ucomm.items():
        assert q.get("repeatable") and q.get("source") == "board", k
        assert set(q["reward"]) <= {"gold", "infamy"}, (k, q["reward"])   # 無 fame(這是犯罪)
        assert 40 <= q["reward"]["gold"] <= 110, (k, q["reward"]["gold"])  # 守正規委託區間(防經濟外溢)
        assert q["objective"]["type"] == "kill"                # 純擊殺(不可 clear_dungeon 免費刷)
        assert q.get("provinces")                              # 在地化(由藏身處所在省定可見性)


def test_underworld_contracts_spotlighted_by_pulse():
    """每條 ucomm_* 都被某地下脈動聚光(否則永不可見=孤兒)。"""
    gd = get_gamedata()
    spotlit = {sq for p in gd.world_pulse.values() for sq in p.get("spotlight_quests", [])}
    for k in gd.quests:
        if k.startswith("ucomm_"):
            assert k in spotlit, f"{k} 未被任何脈動聚光"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_crime_depth")
