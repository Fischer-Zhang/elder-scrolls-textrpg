"""陣營階段 C:大事件引擎(動態政局)回歸 —— 觸發/易幟/三層/紅線/決定性/玩家驅動。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
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


def test_kvatch_falls_after_days_and_once_fire():
    gd, c = _setup(); politics.pledge(c, "imperial"); st = _state(c)
    assert c.world_faction == {} and c.world_events_fired == []
    assert worldstate.update(st, gd) == []                      # day 0:無事件(防 off-by-one)
    assert politics.faction_of(c, gd, "kvatch") == "imperial"   # 種子=Oblivion 現狀
    st.time.advance(3 * 24)
    evs = worldstate.update(st, gd)
    assert any(e["id"] == "kvatch_falls" for e in evs)          # 危機觸發(解鎖地城/招募/主線)
    assert "kvatch_falls" in c.world_events_fired
    # 神話黎明非世界大戰陣營 → 城池不易幟 daedric;危機由湮滅之門地城/主線弧呈現
    assert c.world_faction == {}
    assert politics.faction_of(c, gd, "kvatch") == "imperial"   # 凱瓦奇立場不變
    assert all(e["id"] != "kvatch_falls" for e in worldstate.update(st, gd))   # once-fire


def test_player_held_city_immune_to_flip():
    # 用 anvil + septim_line_ends(避開 kvatch 的 falls↔liberated 同圈互消);玩家持有的城,事件易幟被 city_faction 蓋過
    gd, c = _setup(); politics.pledge(c, "imperial"); st = _state(c)
    c.world_events_fired.append("oblivion_crisis_ended")        # 分裂事件=湮滅危機後第二幕
    politics.conquer(c, gd, "anvil", now=st.time.absolute_hours())
    st.time.advance(30 * 24); worldstate.update(st, gd)         # septim_line_ends → anvil 易幟 independent
    assert c.world_faction["anvil"] == "independent"           # 底層仍寫入(失城後浮回)
    assert politics.faction_of(c, gd, "anvil") == "imperial"   # 但持有 → city_faction 蓋過 → 免疫
    assert "anvil" in politics.held_tax_cities(c, gd)


def test_red_line_world_faction_not_taxed():
    gd, c = _setup(); st = _state(c)
    c.world_events_fired.append("oblivion_crisis_ended")        # 危機平息 → 分裂事件可觸發
    st.time.advance(60 * 24); worldstate.update(st, gd)         # septim_line_ends(anvil/gideon→independent)
    assert politics.faction_of(c, gd, "anvil") == "independent"
    politics.pledge(c, "independent")
    assert "anvil" not in politics.held_tax_cities(c, gd)       # 🔴 易幟城不入稅基(只認 city_faction)
    assert "gideon" not in politics.held_tax_cities(c, gd)


def test_requires_chain():
    # 新時間軸:湮滅危機平息(oblivion_crisis_ended)→ 賽普汀血脈斷絕 → 邊省獨立(鏈式同圈觸發)
    gd, c = _setup(); st = _state(c)
    c.world_events_fired.append("oblivion_crisis_ended")
    ids = [e["id"] for e in worldstate.update(st, gd)]
    assert "septim_line_ends" in ids and "argonian_accession" in ids  # 鏈式同圈觸發(危機後)
    assert c.world_faction.get("anvil") == "independent"
    # 缺前置(危機未平)→ 分裂不觸發
    gd2, c2 = _setup()
    assert not worldstate._trigger_ok(c2, gd2, {"requires": ["oblivion_crisis_ended"]}, 40, RNG(1))


def test_daedric_unlock_after_kvatch():
    """神話黎明非政治大義:即使凱瓦奇陷落,daedric 也永不出現在可宣誓大義中(走密教公會,非宣誓)。"""
    gd, c = _setup(); st = _state(c)
    assert "daedric" not in politics.pledgeable_causes(c)
    st.time.advance(3 * 24); worldstate.update(st, gd)          # kvatch_falls 觸發
    assert "kvatch_falls" in c.world_events_fired
    assert "daedric" not in politics.pledgeable_causes(c)
    assert set(politics.pledgeable_causes(c)) == {"imperial", "independent", "own"}


def test_kvatch_liberated_player_driven():
    gd, c = _setup(); politics.pledge(c, "imperial"); st = _state(c)
    st.time.advance(3 * 24); worldstate.update(st, gd)         # kvatch_falls 觸發
    assert "kvatch_falls" in c.world_events_fired
    politics.conquer(c, gd, "kvatch", now=st.time.absolute_hours())   # 玩家進駐凱瓦奇
    fame0 = c.fame
    evs = worldstate.update(st, gd)
    assert any(e["id"] == "kvatch_liberated" for e in evs)     # 持有凱瓦奇 → 光復事件 + 聲望
    assert c.fame == fame0 + 30


def test_lost_city_reverts_to_event_state():
    """conquer 不 pop world_faction:玩家失城(叛亂)後,底層事件易幟浮回(回到事件政治現實,非原始種子)。"""
    gd, c = _setup(); politics.pledge(c, "imperial"); st = _state(c)
    c.world_events_fired.append("oblivion_crisis_ended")       # 分裂事件=危機後
    politics.conquer(c, gd, "anvil", now=st.time.absolute_hours())
    st.time.advance(30 * 24); worldstate.update(st, gd)        # world_faction[anvil]=independent(被 city_faction 蓋)
    assert politics.faction_of(c, gd, "anvil") == "imperial"   # 持有時=你的大義
    c.city_faction.pop("anvil")                                # 模擬叛亂失城(tick_tax 會 pop city_faction)
    assert politics.faction_of(c, gd, "anvil") == "independent"  # 浮回事件態(非原始 imperial 種子)


def test_deterministic_replay():
    gd, c1 = _setup(); c1.world_events_fired.append("oblivion_crisis_ended"); st1 = _state(c1); st1.time.advance(60 * 24)
    r1 = [e["id"] for e in worldstate.update(st1, gd)]
    _, c2 = _setup(); c2.world_events_fired.append("oblivion_crisis_ended"); st2 = _state(c2); st2.time.advance(60 * 24)
    r2 = [e["id"] for e in worldstate.update(st2, gd)]
    assert r1 == r2 and c1.world_faction == c2.world_faction


def run():
    test_kvatch_falls_after_days_and_once_fire()
    test_player_held_city_immune_to_flip()
    test_red_line_world_faction_not_taxed()
    test_requires_chain()
    test_daedric_unlock_after_kvatch()
    test_kvatch_liberated_player_driven()
    test_lost_city_reverts_to_event_state()
    test_deterministic_replay()


if __name__ == "__main__":
    run()
    print("test_worldstate 全通過")
