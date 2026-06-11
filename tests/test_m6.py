"""M6:一生傳奇總結、評分、遊戲模式、足跡追蹤的測試。"""

import tempfile
from pathlib import Path

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import factions, legacy


def _state(**time_kw):
    gd = get_gamedata()
    c = build_character(gd, name="英", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    st = GameState(player=c,
                   time=GameTime(year=433, month=1, day=1, hour=8),
                   start_time=GameTime(year=433, month=1, day=1, hour=8))
    return gd, c, st


# --- 在世時間 -----------------------------------------------------------
def test_survived_elapsed():
    gd, c, st = _state()
    st.time = GameTime(year=434, month=1, day=1, hour=8)   # 整整一年(12×30 天)
    years, days = legacy.survived(st)
    assert years == 1 and days == 0
    # 同函式曆法換算另一組輸入(原 test_survived_partial):重設 time 不互相污染
    # (survived 只讀 start_time 與 time)。不足一年:過了 2 月又 10 天 = 70 天。
    st.time = GameTime(year=433, month=3, day=11, hour=8)
    assert legacy.survived(st) == (0, 70)


# --- 創角即記錄起點足跡 ------------------------------------------------
def test_creation_records_start_location():
    gd, c, st = _state()
    assert c.location_id in c.visited_locations and len(c.visited_locations) == 1


# --- 傳奇總結欄位與評分 ------------------------------------------------
def test_compute_fields_and_title():
    gd, c, st = _state()
    s = legacy.compute(st, gd, ending="death")
    for k in ("name", "race", "class", "level", "score", "title", "playstyle",
              "top_skills", "places_visited", "total_locations"):
        assert k in s
    assert s["total_locations"] == len(gd.world["locations"])
    assert legacy.title_for(0) == "默默無聞的旅人"
    assert legacy.title_for(10000) == "載入史冊的不朽者"
    # 分數隨各門檻遞增
    assert legacy.title_for(699) != legacy.title_for(700)
    # playstyle 判定(原 test_playstyle_detection):置於 compute 之後僅為語意乾淨。
    # 法系 spec 聚合最高且 spread>=30 → magic 分支(回傳含子字串『法師』)。
    for k in c.skills:
        c.skills[k] = 5
    for k in ("destruction", "restoration", "alteration"):
        c.skills[k] = 80
    assert "法師" in legacy.playstyle(c, gd)


def test_score_monotonic_with_achievements():
    gd, c, st = _state()
    base = legacy.compute(st, gd)["score"]
    c.level = 10
    c.completed_quests = ["fg1", "fg2", "job_wolf"]
    c.cleared_dungeons = ["cedernoc_cave", "ashfall_barrow"]
    c.visited_locations = list(gd.world["locations"].keys())
    c.fame = 50
    c.gold = 2000
    factions.join(c, "fighters_guild"); c.factions["fighters_guild"] = 3
    richer = legacy.compute(st, gd)["score"]
    assert richer > base + 1000


# --- 遊戲模式 + start_time 存讀檔 --------------------------------------
def test_game_mode_and_start_time_roundtrip():
    gd, c, st = _state()
    st.game_mode = GameState.LEGEND
    st.time = GameTime(year=433, month=5, day=2, hour=12)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        st.save(p)
        lo = GameState.load(p)
    assert lo.game_mode == GameState.LEGEND
    assert lo.start_time.to_dict() == st.start_time.to_dict()
    assert lo.time.to_dict() == st.time.to_dict()
    assert lo.player.visited_locations == c.visited_locations


def test_legacy_save_version_back_compat():
    """舊版(無 start_time/game_mode)存檔仍能載入,且在世時間以紀元起點起算(回歸審查 [4])。"""
    gd, c, st = _state()
    st.time = GameTime(year=433, month=6, day=15, hour=12)   # 已玩一段時間
    d = st.to_dict()
    del d["start_time"]; del d["game_mode"]
    lo = GameState.from_dict(d)
    assert lo.game_mode == "adventure"
    assert lo.start_time.to_dict() == GameTime().to_dict()   # 預設回紀元起點,而非當前時間
    assert lo.start_time.to_dict() != lo.time.to_dict()
    assert legacy.survived(lo) != (0, 0)                      # 在世時間正確反映經過


def test_score_faction_rank_clamped():
    """回歸審查 [1]:毀損的越界階級不可灌爆傳奇分數。"""
    gd, c, st = _state()
    factions.join(c, "fighters_guild")
    top = len(gd.factions["fighters_guild"]["ranks"]) - 1
    c.factions["fighters_guild"] = top
    s_top = legacy.compute(st, gd)["score"]
    c.factions["fighters_guild"] = 999
    assert legacy.compute(st, gd)["score"] == s_top          # 夾限,不灌爆


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m6 OK")
