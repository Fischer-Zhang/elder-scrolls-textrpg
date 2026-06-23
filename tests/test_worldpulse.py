"""常態世界脈動引擎(R-pulse)回歸:決定性 / 冷卻 / 每日一次 / active window 推導 /
解鎖閘 / 聚光 gate / 存檔遷移。對位 test_worldstate.py 的結構。"""

from types import SimpleNamespace

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import worldpulse, quests


# --- 輕量 fake(隔離真實資料,精準測引擎邏輯)------------------------------

_FAKE_PULSES = {
    "p_sky": {"province": "天際", "weight": 3, "cooldown_days": 12,
              "active_window_days": 8, "min_day": 4, "spotlight_quests": ["c_sky"],
              "news": "天際盜匪猖獗。"},
    "p_cyr": {"province": "賽羅迪爾", "weight": 1, "cooldown_days": 10,
              "active_window_days": 6, "min_day": 4, "requires_event": "flag_x",
              "spotlight_quests": ["c_cyr"], "news": "帝國大道有事。"},
}


def _fake_gd():
    return SimpleNamespace(world_pulse=_FAKE_PULSES)


def _fake_char(events=None):
    return SimpleNamespace(world_pulse_day={}, pulse_eval_day=0,
                           world_events_fired=list(events or []))


def _fake_state(char, day, seed=1):
    # start_time.absolute_hours()=0 → day_index = day(開局後天數);time 推進 day 天
    return SimpleNamespace(player=char, rng=RNG(seed),
                           time=SimpleNamespace(absolute_hours=lambda d=day: d * 24),
                           start_time=SimpleNamespace(absolute_hours=lambda: 0))


# --- _eligible:min_day + requires_event + 冷卻 -----------------------------

def test_eligible_min_day_gate():
    gd, c = _fake_gd(), _fake_char()
    assert worldpulse._eligible(c, gd, 0) == []          # today<min_day 全擋
    assert worldpulse._eligible(c, gd, 3) == []          # min_day=4,day3 仍擋
    assert worldpulse._eligible(c, gd, 5) == ["p_sky"]   # p_cyr 卡 requires_event flag_x


def test_eligible_requires_event_gate():
    gd = _fake_gd()
    assert "p_cyr" not in worldpulse._eligible(_fake_char(), gd, 10)
    assert "p_cyr" in worldpulse._eligible(_fake_char(["flag_x"]), gd, 10)


def test_eligible_cooldown_blocks_then_clears():
    gd, c = _fake_gd(), _fake_char(["flag_x"])
    c.world_pulse_day["p_sky"] = 10                       # 10 日廣播過,cooldown 12
    assert "p_sky" not in worldpulse._eligible(c, gd, 21) # 21-10=11 < 12 仍冷卻
    assert "p_sky" in worldpulse._eligible(c, gd, 22)     # 22-10=12 ≥ 12 解冷卻


# --- active window 推導(純由 world_pulse_day,零額外狀態)------------------

def test_active_window_derivation():
    gd, c = _fake_gd(), _fake_char()
    c.world_pulse_day["p_sky"] = 100                      # window 8
    assert worldpulse.active_pulses(c, gd, 100) == {"p_sky"}    # 當日 active
    assert worldpulse.active_pulses(c, gd, 107) == {"p_sky"}    # 第 7 日仍 active
    assert worldpulse.active_pulses(c, gd, 108) == set()        # 第 8 日視窗閉
    assert worldpulse.active_pulses(c, gd, 99) == set()         # 防呆:陳舊較早日不誤判 active


def test_spotlighted_board_quests_by_province():
    gd, c = _fake_gd(), _fake_char()
    c.world_pulse_day["p_sky"] = 100
    assert worldpulse.spotlighted_board_quests(c, gd, "天際", 103) == {"c_sky"}
    assert worldpulse.spotlighted_board_quests(c, gd, "賽羅迪爾", 103) == set()   # 別省不聚光
    assert worldpulse.spotlighted_board_quests(c, gd, "天際", 110) == set()       # 過期不聚光


def test_pick_deterministic_and_in_pool():
    gd = _fake_gd()
    pool = ["p_cyr", "p_sky"]
    a = worldpulse._pick(pool, gd, RNG(7))
    b = worldpulse._pick(pool, gd, RNG(7))
    assert a == b and a in pool                            # 同 seed 同結果、必在 pool


# --- update:每日一次哨兵 + 廣播設欄 -----------------------------------------

def test_update_one_eval_per_day():
    gd, c = _fake_gd(), _fake_char(["flag_x"])
    st = _fake_state(c, day=10)
    worldpulse.update(st, gd)                              # 首次評估(不論是否廣播)
    assert c.pulse_eval_day == 10
    # 同日再評估:哨兵早退,回 []
    assert worldpulse.update(st, gd) == []


def test_update_broadcast_sets_pulse_day():
    gd = _fake_gd()
    # 掃 seed 找一個會廣播的(GLOBAL_CHANCE 0.5);斷言廣播必 stamp world_pulse_day
    for seed in range(1, 30):
        c = _fake_char(["flag_x"]); st = _fake_state(c, day=10, seed=seed)
        news = worldpulse.update(st, gd)
        if news:
            pid = news[0]["id"]
            assert c.world_pulse_day.get(pid) == 10
            assert pid in worldpulse.active_pulses(c, gd, 10)
            return
    raise AssertionError("30 個 seed 內無任何脈動廣播(GLOBAL_CHANCE 機率異常?)")


# --- 真實資料整合:決定性 + 聚光委託出現於告示板 ----------------------------

def _real():
    gd = get_gamedata()
    c = build_character(gd, name="脈", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_real_deterministic_replay():
    gd, c1 = _real()
    st1 = GameState(player=c1, rng=RNG(5), game_mode="adventure"); st1.time.advance(20 * 24)
    r1 = [e["id"] for e in worldpulse.update(st1, gd)]
    _, c2 = _real()
    st2 = GameState(player=c2, rng=RNG(5), game_mode="adventure"); st2.time.advance(20 * 24)
    r2 = [e["id"] for e in worldpulse.update(st2, gd)]
    assert r1 == r2 and c1.world_pulse_day == c2.world_pulse_day


def test_real_spotlight_surfaces_commission():
    gd, c = _real()
    today = 1000
    # 模擬天際脈動正激增 → comm_skyrim_wolf 應現於天際告示板,別省不現,過窗消失
    c.world_pulse_day["pulse_skyrim_wolves"] = today
    av = quests.available_quests(c, gd, "board", province="天際", day=today)
    assert "comm_skyrim_wolf" in av
    av_cyr = quests.available_quests(c, gd, "board", province="賽羅迪爾", day=today)
    assert "comm_skyrim_wolf" not in av_cyr
    # 過 active window(8)後消失
    av_late = quests.available_quests(c, gd, "board", province="天際", day=today + 8)
    assert "comm_skyrim_wolf" not in av_late
    # day=None(舊呼叫端)保守隱藏所有 repeatable
    av_none = quests.available_quests(c, gd, "board", province="天際", day=None)
    assert not [q for q in av_none if gd.quests[q].get("repeatable")]


def test_no_heavy_effect_in_pulses():
    """脈動是引子不是數值來源:不可帶 faction_flip/combat/gold 等重 effect(守反 min-max)。"""
    gd = get_gamedata()
    for pid, p in gd.world_pulse.items():
        eff = p.get("effect")
        if eff:
            assert eff.get("type") in {"fame"}, f"{pid}: 脈動禁帶重 effect {eff.get('type')}"


# --- 存檔遷移 ----------------------------------------------------------------

def test_ensure_pulse_fields_idempotent():
    c = SimpleNamespace()                                  # 完全缺欄(舊存檔)
    worldpulse.ensure_pulse_fields(c)
    assert c.world_pulse_day == {} and c.pulse_eval_day == 0
    c.world_pulse_day = {"p": 5, "bad": "x"}               # 毀損值
    worldpulse.ensure_pulse_fields(c)
    assert c.world_pulse_day == {"p": 5}                   # 清掉非 int
    worldpulse.ensure_pulse_fields(c)                      # 再跑冪等
    assert c.world_pulse_day == {"p": 5}


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_worldpulse 全通過")
