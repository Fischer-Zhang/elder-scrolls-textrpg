"""具名地標與發現系統(區域細化)的測試:首次抵達一次性發現 + 獎勵、fire-once、
舊存檔向後相容(新欄 + 已訪節點仍能發現)、資料完整性、禁用永久加成獎勵、legacy 計數。"""

import json

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import inventory, landmarks, legacy

# 取一個帶金幣+物品+聲望的地標當樣本(資料若改,改這裡)
SAMPLE = "thorn_fen"        # gold150 + glass_dagger + fame2


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="行者", sex="male", race="nord",
                        birthsign="steed", class_id="thief")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime(), rng=RNG(7))


def test_discover_fires_and_rewards_exact():
    gd, st = _state(location_id=SAMPLE)
    c = st.player
    lm = gd.landmarks[SAMPLE]; rw = lm["reward"]
    g0, f0 = c.gold, c.fame
    counts0 = {it["id"]: inventory.count_item(c, it["id"]) for it in rw.get("items", [])}
    res = landmarks.discover(st, gd, SAMPLE)
    assert res is not None and res["name"] == lm["name"]
    assert c.gold - g0 == rw.get("gold", 0)
    assert c.fame - f0 == rw.get("fame", 0)
    for it in rw.get("items", []):
        assert inventory.count_item(c, it["id"]) - counts0[it["id"]] == it.get("qty", 1)
    assert SAMPLE in c.discovered_landmarks


def test_fire_once():
    gd, st = _state(location_id=SAMPLE)
    c = st.player
    landmarks.discover(st, gd, SAMPLE)
    g1 = c.gold
    again = landmarks.discover(st, gd, SAMPLE)       # 重訪
    assert again is None
    assert c.gold == g1                              # 不重複發獎


def test_idempotent_across_repeated_hooks():
    # 模擬同地連續三圈 hook(game_loop 每圈呼叫)→ 只發一次
    gd, st = _state(location_id=SAMPLE)
    c = st.player
    fired = [landmarks.discover(st, gd, SAMPLE) for _ in range(3)]
    assert sum(1 for r in fired if r) == 1


def test_no_landmark_returns_none():
    gd, st = _state(location_id="bruma")             # 布魯瑪無地標
    assert gd.landmark_at("bruma") is None
    g0 = st.player.gold
    assert landmarks.discover(st, gd, "bruma") is None
    assert st.player.gold == g0


def test_discover_does_not_kill_or_cost_time():
    gd, st = _state(location_id="hist_grove")
    c = st.player
    h0, t0 = c.health, st.time.absolute_hours()      # absolute_hours 是方法,務必呼叫(否則比較兩個 bound method 恆等)
    res = landmarks.discover(st, gd, "hist_grove")
    assert res is not None and res != "dead"
    assert c.health == h0                            # 純加性,不傷血
    assert st.time.absolute_hours() == t0            # 不耗時


def test_save_roundtrip():
    gd, st = _state(location_id=SAMPLE)
    landmarks.discover(st, gd, SAMPLE)
    loaded = Character.from_dict(json.loads(json.dumps(st.player.to_dict())))
    assert SAMPLE in loaded.discovered_landmarks


def test_old_save_compat_and_visited_node_still_discoverable():
    # 舊存檔缺 discovered_landmarks → 預設 [];且已在 visited_locations 的節點仍能發現
    gd, st = _state(location_id="pale_pass")
    c = st.player
    c.visited_locations = ["bruma", "pale_pass"]      # 模擬舊存檔已訪過地標節點
    d = c.to_dict(); del d["discovered_landmarks"]    # 舊存檔無此欄
    loaded = Character.from_dict(d)
    assert loaded.discovered_landmarks == []          # 預設空(非沿用 visited)
    st.player = loaded
    res = landmarks.discover(st, gd, "pale_pass")      # 仍能發現(關鍵:守門用新欄非 visited)
    assert res is not None
    assert "pale_pass" in loaded.discovered_landmarks


def test_all_landmark_locs_valid():
    gd, _ = _state()
    locs = gd.world["locations"]
    for lid in gd.landmarks:
        assert lid in locs, f"地標 {lid} 不是合法地點"


def test_all_reward_items_exist():
    gd, _ = _state()
    for lid, lm in gd.landmarks.items():
        for it in lm.get("reward", {}).get("items", []):
            assert gd.item(it["id"]) is not None, f"{lid} 獎勵物品 {it['id']} 不存在"
            assert it.get("qty", 1) >= 1


def test_required_fields_present():
    gd, _ = _state()
    for lid, lm in gd.landmarks.items():
        assert lm.get("name"), f"{lid} 缺 name"
        assert lm.get("discover"), f"{lid} 缺 discover"


def test_reward_has_no_permanent_boost_keys():
    # 契約鎖:地標獎勵只能給 gold/items/fame —— 嚴禁永久數值/技能加成(守反 min-max)
    gd, _ = _state()
    allowed = {"gold", "items", "fame"}
    item_allowed = {"id", "qty"}
    for lid, lm in gd.landmarks.items():
        rw = lm.get("reward", {})
        assert set(rw) <= allowed, f"{lid} 獎勵含禁用 key:{set(rw) - allowed}"
        for it in rw.get("items", []):
            assert set(it) <= item_allowed, f"{lid} 物品含禁用 key:{set(it) - item_allowed}"


def test_legacy_counts_and_robust():
    gd, st = _state(location_id="pale_pass")
    c = st.player
    landmarks.discover(st, gd, "pale_pass")
    landmarks.discover(st, gd, "niben_marsh")        # 直接呼叫(不需在該地)
    c.discovered_landmarks.append("bogus_loc")        # 毀損存檔殘留
    res = legacy.compute(st, gd)
    assert res["landmarks_found"] == 2                # 只計合法(bogus 不算)
    assert res["total_landmarks"] == len(gd.landmarks)


def test_score_rewards_exploration():
    gd, st = _state()
    base = legacy.compute(st, gd)["score"]
    landmarks.discover(st, gd, SAMPLE)
    after = legacy.compute(st, gd)["score"]
    assert after > base                              # 發現地標提升傳奇分數


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_landmarks OK")
