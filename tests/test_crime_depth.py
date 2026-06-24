"""R84 犯罪/通緝深化 —— 威脅側:賞金獵人路途追殺 + 新怪 schema。

(回報側 refuge/fence/contracts 測試於 Phase 2 併入本檔。)
"""

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.state import GameState, GameTime
from tesrpg.systems import magic


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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_crime_depth")
