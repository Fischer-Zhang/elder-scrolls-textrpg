"""陣營階段 C:大事件引擎(動態政局)回歸 —— 觸發/易幟/三層/紅線/決定性/玩家驅動。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import politics, worldstate


def _setup():
    gd = get_gamedata()
    c = build_character(gd, name="帥", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def _state(c):
    return GameState(player=c, rng=RNG(1), game_mode="adventure")


def test_open_state_is_oblivion_seed():
    gd, c = _setup(); st = _state(c)
    assert c.world_faction == {} and c.world_events_fired == []
    assert worldstate.update(st, gd) == []                      # day 0:無事件
    assert politics.faction_of(c, gd, "kvatch") == "imperial"   # 種子=Oblivion 現狀


def test_kvatch_falls_after_days_and_once_fire():
    gd, c = _setup(); st = _state(c)
    st.time.advance(3 * 24)
    evs = worldstate.update(st, gd)
    assert any(e["id"] == "kvatch_falls" for e in evs)
    assert c.world_faction["kvatch"] == "daedric"
    assert politics.faction_of(c, gd, "kvatch") == "daedric"    # 三層:world_faction 透出
    assert "kvatch_falls" in c.world_events_fired
    assert all(e["id"] != "kvatch_falls" for e in worldstate.update(st, gd))   # once-fire


def test_player_held_city_immune_to_flip():
    # 用 anvil + septim_line_ends(避開 kvatch 的 falls↔liberated 同圈互消);玩家持有的城,事件易幟被 city_faction 蓋過
    gd, c = _setup(); politics.pledge(c, "imperial"); st = _state(c)
    politics.conquer(c, gd, "anvil", now=st.time.absolute_hours())
    st.time.advance(30 * 24); worldstate.update(st, gd)         # septim_line_ends → anvil 易幟 independent
    assert c.world_faction["anvil"] == "independent"           # 底層仍寫入(失城後浮回)
    assert politics.faction_of(c, gd, "anvil") == "imperial"   # 但持有 → city_faction 蓋過 → 免疫
    assert "anvil" in politics.held_tax_cities(c, gd)


def test_red_line_world_faction_not_taxed():
    gd, c = _setup(); st = _state(c)
    st.time.advance(60 * 24); worldstate.update(st, gd)         # 跑過時間事件(anvil/gideon→independent)
    assert politics.faction_of(c, gd, "anvil") == "independent"
    politics.pledge(c, "independent")
    assert "anvil" not in politics.held_tax_cities(c, gd)       # 🔴 易幟城不入稅基(只認 city_faction)
    assert "gideon" not in politics.held_tax_cities(c, gd)


def test_requires_chain():
    gd, c = _setup(); st = _state(c)
    st.time.advance(30 * 24)
    ids = [e["id"] for e in worldstate.update(st, gd)]
    assert "kvatch_falls" in ids and "septim_line_ends" in ids  # 鏈式同圈觸發(定點迴圈)
    assert c.world_faction.get("anvil") == "independent"
    # 缺前置 → 不觸發
    gd2, c2 = _setup()
    assert not worldstate._trigger_ok(c2, gd2, {"days_min": 30, "requires": ["kvatch_falls"]}, 40, RNG(1))


def test_daedric_unlock_after_kvatch():
    gd, c = _setup(); st = _state(c)
    assert "daedric" not in politics.pledgeable_causes(c)
    st.time.advance(3 * 24); worldstate.update(st, gd)
    assert "daedric" in politics.pledgeable_causes(c)           # 凱瓦奇陷落後解鎖神話黎明


def test_flip_makes_city_siegeable():
    gd, c = _setup(); politics.pledge(c, "imperial"); st = _state(c)
    assert not politics.can_siege(c, gd, "kvatch")             # 種子 imperial=盟,不可攻
    st.time.advance(3 * 24); worldstate.update(st, gd)         # → daedric
    assert politics.relationship(c, gd, "kvatch") == "enemy" and politics.can_siege(c, gd, "kvatch")


def test_kvatch_liberated_player_driven():
    gd, c = _setup(); politics.pledge(c, "imperial"); st = _state(c)
    st.time.advance(3 * 24); worldstate.update(st, gd)         # kvatch → daedric
    assert c.world_faction["kvatch"] == "daedric"
    politics.conquer(c, gd, "kvatch", now=st.time.absolute_hours())   # 玩家光復
    fame0 = c.fame
    evs = worldstate.update(st, gd)
    assert any(e["id"] == "kvatch_liberated" for e in evs)
    assert "kvatch" not in c.world_faction                     # clear_flip 撤除 daedric 底層
    assert c.fame == fame0 + 30


def test_lost_city_reverts_to_event_state():
    """conquer 不 pop world_faction:玩家失城(叛亂)後,底層事件易幟浮回(回到事件政治現實,非原始種子)。"""
    gd, c = _setup(); politics.pledge(c, "imperial"); st = _state(c)
    politics.conquer(c, gd, "anvil", now=st.time.absolute_hours())
    st.time.advance(30 * 24); worldstate.update(st, gd)        # world_faction[anvil]=independent(被 city_faction 蓋)
    assert politics.faction_of(c, gd, "anvil") == "imperial"   # 持有時=你的大義
    c.city_faction.pop("anvil")                                # 模擬叛亂失城(tick_tax 會 pop city_faction)
    assert politics.faction_of(c, gd, "anvil") == "independent"  # 浮回事件態(非原始 imperial 種子)


def test_catchup_multiple_events_one_call():
    gd, c = _setup(); st = _state(c); st.time.advance(55 * 24)
    ids = {e["id"] for e in worldstate.update(st, gd)}
    assert ids == {"kvatch_falls", "septim_line_ends", "argonian_accession", "nord_stirrings"}


def test_deterministic_replay():
    gd, c1 = _setup(); st1 = _state(c1); st1.time.advance(60 * 24)
    r1 = [e["id"] for e in worldstate.update(st1, gd)]
    _, c2 = _setup(); st2 = _state(c2); st2.time.advance(60 * 24)
    r2 = [e["id"] for e in worldstate.update(st2, gd)]
    assert r1 == r2 and c1.world_faction == c2.world_faction


def test_save_roundtrip_fired_and_world_faction():
    import json
    gd, c = _setup(); st = _state(c); st.time.advance(30 * 24); worldstate.update(st, gd)
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.world_events_fired == c.world_events_fired
    assert loaded.world_faction == c.world_faction


def run():
    test_open_state_is_oblivion_seed()
    test_kvatch_falls_after_days_and_once_fire()
    test_player_held_city_immune_to_flip()
    test_red_line_world_faction_not_taxed()
    test_requires_chain()
    test_daedric_unlock_after_kvatch()
    test_flip_makes_city_siegeable()
    test_kvatch_liberated_player_driven()
    test_lost_city_reverts_to_event_state()
    test_catchup_multiple_events_one_call()
    test_deterministic_replay()
    test_save_roundtrip_fired_and_world_faction()


if __name__ == "__main__":
    run()
    print("test_worldstate 全通過")
