"""資訊可見性(R114·UI/UX 審計 包B)view-model 回歸測試。

涵蓋:限時增益總覽(藥水/幻術/飽滿/祝福 帶剩餘時)、持續狀態旗(病/醉/戒斷/獸形/潛伏)、
blessing_label now-bug 修、角色卡效果清單(含疾病死碼接活)、任務追蹤行、商店負重、
地圖任務/重踞標記、藥草園熟成通知去重、HUD 組裝。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import potion_buff, spellfx, housing, quests, dungeon
import tesrpg.ui.console as ui


def _cs():
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    return gd, c, GameState(player=c, time=GameTime(), rng=RNG(1))


# --- F1 限時增益總覽 ------------------------------------------------------
def test_timed_buffs_lists_all_sources_with_remaining():
    gd, c, st = _cs()
    now = st.time.absolute_hours()
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "strength", 10, hours=5)
    spellfx.apply(c, st, "feather", hours=6)
    housing.set_well_rested(c, now, 24)
    c.divine_blessing = {"divine": "kynareth", "expires_at": now + 12}
    rows = ui._timed_buffs(c, now, gd, include_blessing=True)
    labels = [r["label"] for r in rows]
    assert any("強化力量 +10" in l for l in labels)
    assert any("羽落" in l for l in labels)
    assert any("精神飽滿" in l for l in labels)
    assert any("之佑·餘 12 時" in l for l in labels)     # 祝福 label 內含時數
    strength = next(r for r in rows if "力量" in r["label"])
    assert strength["remain"] == 5
    # 過期不列
    assert not ui._timed_buffs(c, now + 999, gd, include_blessing=True)
    # HUD 版排除祝福(祝福另有專屬 chip)
    assert not any("之佑" in r["label"] for r in ui._timed_buffs(c, now, gd, include_blessing=False))


def test_blessing_badge_now_bug_fixed():
    gd, c, st = _cs()
    now = st.time.absolute_hours()
    c.divine_blessing = {"divine": "mara", "expires_at": now + 8}
    assert "餘 8 時" in ui._blessing_badge(c, now)          # 帶 now → 顯時數(修 F1 半 bug)
    assert "餘" not in ui._blessing_badge(c)                # 不帶 now → 向後相容無時數
    c.divine_blessing = {}
    assert ui._blessing_badge(c, now) is None


# --- F2 持續狀態旗 + 疾病死碼接活 ---------------------------------------
def test_status_flags_mirror_terminal_extras():
    gd, c, st = _cs()
    assert ui._status_flags(c, st, gd) == []               # 乾淨角色無旗
    c.diseases = [{"id": "rockjoint"}, {"id": "ataxia"}]
    c.beast_form = True
    flags = ui._status_flags(c, st, gd)
    assert "🐺 獸形" in flags and "🩹 染病×2" in flags
    # 潛伏期(尚未轉化)
    gd2, c2, st2 = _cs()
    c2.vampire_infected_day = 3
    assert any("潛伏" in f for f in ui._status_flags(c2, st2, gd2))


def test_effect_sheet_lines_include_disease_labels():
    gd, c, st = _cs()
    c.diseases = [{"id": "rockjoint"}]
    lines = ui._effect_sheet_lines(c, st, gd)
    joined = " ".join(t for t, _ in lines)
    assert "🩹" in joined                                   # active_labels 死碼接活(病名+症狀)
    # 空角色 → 單行提示
    gd2, c2, st2 = _cs()
    assert ui._effect_sheet_lines(c2, st2, gd2) == [("目前沒有進行中的效果。", "muted")]


# --- F3 任務追蹤 ----------------------------------------------------------
def test_tracked_lines_and_location_view():
    gd, c, st = _cs()
    c.quests.clear()                                       # 排除開局起手任務,隔離測試
    assert quests.tracked_lines(c, gd) == []
    c.quests["comm_cyrodiil_bandit"] = {"stage": 0, "base": 0}
    lines = quests.tracked_lines(c, gd)
    assert lines and "擊殺" in lines[0]
    c.completed_quests.append("comm_cyrodiil_bandit")
    assert quests.tracked_lines(c, gd) == []               # 已完成不追蹤
    # 毀損 qid 不崩
    c.completed_quests.clear(); c.quests.clear()
    c.quests["ghost_quest_xyz"] = {"stage": 0}
    assert quests.tracked_lines(c, gd) == []
    lv = ui._location_view(c, gd)
    assert "tracked" in lv
    assert ui._location_view(c, gd, brief=True)["tracked"] == []   # 麵包屑不塞任務


# --- F4 商店負重 ----------------------------------------------------------
def test_shop_view_has_weight():
    gd, c, st = _cs()
    sv = ui._shop_view(c, gd, "whiterun", ["iron_sword", "healing_potion"])
    assert isinstance(sv["weight"], float) and sv["max"] > 0 and sv["over"] is False
    # over=True 分支:塞爆背包 → 面板如實回報超載
    from tesrpg.systems import inventory
    while inventory.total_weight(c, gd) <= inventory.max_weight(c, gd):
        inventory.add_item(c, "iron_cuirass", 1)
    assert ui._shop_view(c, gd, "whiterun", ["iron_sword"])["over"] is True


# --- F5 地圖標記 ----------------------------------------------------------
def test_map_view_quest_and_reinfest_flags():
    gd, c, st = _cs()
    c.quests.clear()
    ui._hud_state = st; ui._hud_gamedata = gd; ui._hud_allies = []
    try:
        # 🔴 正向路徑:找一個帶 reach/clear_dungeon 目標的真任務 → 目標地點必入集合 + 節點標 quest
        target_loc, qid = None, None
        for _qid, q in gd.quests.items():
            obj = q.get("objective") or (q.get("stages") or [{}])[0].get("objective") or {}
            if obj.get("type") == "reach" and obj.get("location") in gd.world["locations"]:
                target_loc, qid = obj["location"], _qid
                break
            if obj.get("type") == "clear_dungeon":
                dloc = next((lid for lid, l in gd.world["locations"].items()
                             if l.get("dungeon") == obj.get("dungeon")), None)
                if dloc:
                    target_loc, qid = dloc, _qid
                    break
        assert target_loc, "找不到帶地點目標的任務(測試 fixture 前提)"
        c.quests[qid] = {"stage": 0, "base": 0}
        tset = ui._quest_target_location_set(c, gd)
        assert target_loc in tset                              # 目標地點確實入集合(非空斷言)
        mv = ui._map_view(c, gd)
        nodes = {n["id"]: n for n in mv["grid"]["nodes"]}
        assert all("quest" in n and "reinfested" in n for n in nodes.values())
        if target_loc in nodes:                               # 可見地點才在圖上
            assert nodes[target_loc]["quest"] is True
    finally:
        ui._hud_state = None; ui._hud_gamedata = None; ui._hud_allies = None


# --- F6 藥草園熟成通知 ----------------------------------------------------
def test_garden_ready_notice_dedup():
    gd, c, st = _cs()
    now = st.time.absolute_hours()
    c.location_id = "bruma"
    housing.buy(c, gd, "bruma")
    housing.buy_upgrade(c, gd, "bruma", "garden", now)
    seen = set()
    assert housing.garden_ready_notice(c, gd, now, seen) is None       # 剛購入 → 冷卻中
    ready = now + housing.GARDEN_COOLDOWN_HOURS
    msg = housing.garden_ready_notice(c, gd, ready, seen)
    assert msg and "藥草園" in msg
    assert housing.garden_ready_notice(c, gd, ready, seen) is None      # 同輪去重
    c.location_id = "whiterun"                                          # 不在該城 → 不報
    assert housing.garden_ready_notice(c, gd, ready, set()) is None


# --- HUD 組裝 -------------------------------------------------------------
def test_hud_view_carries_buffs_statuses_encumbered():
    gd, c, st = _cs()
    now = st.time.absolute_hours()
    potion_buff.apply_buff(c, st, gd, "fortify_skill", "blade", 12, hours=4)
    c.diseases = [{"id": "rockjoint"}]
    c.divine_blessing = {"divine": "zenithar", "expires_at": now + 6}
    ui._hud_state = st; ui._hud_gamedata = gd; ui._hud_allies = []
    try:
        h = ui._hud_view()
        assert len(h["buffs"]) == 1 and "強化" in h["buffs"][0]["label"]   # 藥水(祝福另計)
        assert "餘 6 時" in h["blessing"]
        assert any("染病" in s for s in h["statuses"])
        assert h["encumbered"] is False
    finally:
        ui._hud_state = None; ui._hud_gamedata = None; ui._hud_allies = None


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_infohud 全通過")
