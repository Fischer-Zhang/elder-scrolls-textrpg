"""地城再滋擾(R111)回歸測試。

涵蓋:🔴 cleared_dungeons 恆單調(重踞絕不移除)、時間戳生命週期(首通排程/到期重踞/
掃蕩推進)、effective_spec 變體疊加、軍營互動(駐守豁免滋擾 + 重踞中禁紮營)、
purge_dungeon objective(base 快照達標/不可即時達標/repeatable 不入 completed)、
告示板天然閘(重踞才現身/now 缺漏隱藏/掃蕩即消失)、傳聞去重、存檔 roundtrip +
ensure 自癒(含 Infinity→OverflowError,R110 教訓)+ 舊檔回填冪等。
"""

import json

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.systems import dungeon, quests, warband

D = "cedernoc_cave"          # 參與滋擾的 d2 泛用地城(賽羅迪爾)
PROV = "賽羅迪爾"
QID = f"dcomm_{D}"
CYC = dungeon.REINFEST_CYCLE_HOURS


def _char():
    gd = get_gamedata()
    c = build_character(gd, name="掃", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    return gd, c


def _cleared(c, gd, now=0):
    """模擬首通:record_dungeon_clear + mark_purged(action_dungeon 首通後的排程)。"""
    quests.record_dungeon_clear(c, D)
    dungeon.mark_purged(c, gd, D, now)


# --- 生命週期 -------------------------------------------------------------
def test_lifecycle_and_monotonic_cleared():
    gd, c = _char()
    assert dungeon.is_reinfested(c, gd, D, now=10**6) is False      # 未清 → 永不重踞
    _cleared(c, gd, now=0)
    assert c.dungeon_reinfest_at[D] == CYC
    assert dungeon.is_reinfested(c, gd, D, now=CYC - 1) is False    # 未到期
    assert dungeon.is_reinfested(c, gd, D, now=CYC) is True         # 到期重踞
    assert dungeon.is_reinfested(c, gd, D, now=CYC + 10 * CYC) is True   # 持續到掃蕩為止(不自行消退)
    dungeon.mark_purged(c, gd, D, now=CYC + 5)                      # 掃蕩 → 嚴格推進
    assert c.dungeon_reinfest_at[D] == CYC + 5 + CYC
    assert dungeon.is_reinfested(c, gd, D, now=CYC + 6) is False
    assert D in c.cleared_dungeons                                  # 🔴 單調:重踞/掃蕩全程不動 cleared
    # 無 reinfest 區塊的特殊地城:mark_purged no-op、永不重踞
    quests.record_dungeon_clear(c, "kvatch_gate")
    dungeon.mark_purged(c, gd, "kvatch_gate", now=0)
    assert "kvatch_gate" not in c.dungeon_reinfest_at
    assert dungeon.is_reinfested(c, gd, "kvatch_gate", now=10**7) is False


def test_effective_spec_swaps_only_battle_fields():
    gd, c = _char()
    orig = gd.dungeons[D]
    assert dungeon.effective_spec(gd, D, infested=False) is orig    # 未重踞 → 原 spec 原物件
    eff = dungeon.effective_spec(gd, D, infested=True)
    rb = orig["reinfest"]
    assert eff["monsters"] == rb["monsters"] and eff["boss"] == rb["boss"]
    assert eff["boss"]["enemy"] != orig["boss"]["enemy"]            # 換血
    for key in ("name", "danger", "grid", "layers", "loot_locked"):
        assert eff[key] == orig[key]                                # 其餘不動


def test_camp_blocks_reinfest_and_reinfest_blocks_camp(monkeypatch=None):
    gd, c = _char()
    _cleared(c, gd, now=0)
    lid = dungeon.dungeon_location_id(gd, D)
    # 駐軍豁免:軍營在此 → 不滋擾
    c.camp = lid
    assert dungeon.is_reinfested(c, gd, D, now=CYC + 1) is False
    c.camp = ""
    assert dungeon.is_reinfested(c, gd, D, now=CYC + 1) is True
    # 重踞中禁紮營(now 閘;防「接清剿委託→紮營免戰完成」);None=向後相容跳過
    saved = warband.is_warlord
    warband.is_warlord = lambda *a, **k: True
    try:
        assert warband.can_make_camp(c, gd, lid, now=CYC + 1) is False
        assert warband.can_make_camp(c, gd, lid) is True            # 舊簽名(無 now)不受影響
        dungeon.mark_purged(c, gd, D, now=CYC + 1)
        assert warband.can_make_camp(c, gd, lid, now=CYC + 2) is True
    finally:
        warband.is_warlord = saved


# --- purge_dungeon objective ----------------------------------------------
def test_purge_objective_base_snapshot():
    gd, c = _char()
    _cleared(c, gd, now=0)
    now = CYC + 1                                                    # 重踞中接取
    assert dungeon.is_reinfested(c, gd, D, now)
    quests.accept_quest(c, gd, QID)
    assert c.quests[QID]["base"] == c.dungeon_reinfest_at[D]         # base=接取時的時間戳
    assert quests.objective_met(c, gd, QID) is False                 # 🔴 不可即時達標
    dungeon.mark_purged(c, gd, D, now)                               # 掃蕩(時間戳嚴格推進)
    assert quests.objective_met(c, gd, QID) is True
    gold0 = c.gold
    events = quests.check_completion(c, gd)
    assert any(e["type"] == "completed" and e["quest_id"] == QID for e in events)
    assert c.gold == gold0 + gd.quests[QID]["reward"]["gold"]
    assert QID not in c.completed_quests                             # repeatable 不入 completed(可再接)
    assert QID not in c.quests
    # objective_text 不崩且含地城名
    quests.accept_quest(c, gd, QID)
    assert gd.dungeons[D]["name"] in quests.objective_text(c, gd, QID)


def test_board_preview_not_prematurely_done():
    """告示板預覽(未接取)不得顯示 ✔ —— base 預設 0 而時間戳恆 >0,無守門會全 ✔(審查 finding)。"""
    gd, c = _char()
    _cleared(c, gd, now=0)
    assert "✘" in quests.objective_text(c, gd, QID)          # 未接取 → 恆 ✘
    quests.accept_quest(c, gd, QID)
    assert "✘" in quests.objective_text(c, gd, QID)          # 已接未掃 → ✘
    dungeon.mark_purged(c, gd, D, now=CYC + 1)
    assert "✔" in quests.objective_text(c, gd, QID)          # 掃蕩 → ✔
    del c.quests[QID]


def test_boss_kill_always_reschedules():
    """任何 boss 擊殺皆推進時間戳(審查 finding:計時器爬行中到期 → 殺完原 boss 一出門即刻重踞
    的怪異觀感;main.py 已改無條件 mark_purged,此處鎖 mark_purged 對「未到期」也推進的語意)。"""
    gd, c = _char()
    _cleared(c, gd, now=0)
    dungeon.mark_purged(c, gd, D, now=100)                   # 未到期(100 < CYC)也推進
    assert c.dungeon_reinfest_at[D] == 100 + CYC


def test_board_gating_by_infestation():
    gd, c = _char()
    kw = dict(province=PROV, day=0)
    # 未清 → 不重踞 → 不現身(即使給 now)
    assert QID not in quests.available_quests(c, gd, "board", now=10**6, **kw)
    _cleared(c, gd, now=0)
    assert QID not in quests.available_quests(c, gd, "board", now=CYC - 1, **kw)   # 未到期
    assert QID in quests.available_quests(c, gd, "board", now=CYC + 1, **kw)       # 重踞 → 現身
    assert QID not in quests.available_quests(c, gd, "board", province=PROV, day=0)  # now 缺漏 → 隱藏(防洩漏)
    assert QID not in quests.available_quests(c, gd, "board", province="天際", day=0, now=CYC + 1)  # 省不符
    dungeon.mark_purged(c, gd, D, now=CYC + 1)
    assert QID not in quests.available_quests(c, gd, "board", now=CYC + 2, **kw)   # 掃蕩即消失


# --- 傳聞 / 存檔 -----------------------------------------------------------
def test_reinfest_notices_dedup_and_province():
    gd, c = _char()
    _cleared(c, gd, now=0)
    lid = dungeon.dungeon_location_id(gd, D)
    c.location_id = lid                                              # 人在賽羅迪爾
    seen: set = set()
    msgs = dungeon.reinfest_notices(c, gd, now=CYC + 1, seen=seen)
    assert msgs and gd.dungeons[D]["name"] in msgs[0]
    assert dungeon.reinfest_notices(c, gd, now=CYC + 2, seen=seen) == []   # 同輪去重
    dungeon.mark_purged(c, gd, D, now=CYC + 2)                       # 下一輪 → 新 key → 再報一次
    msgs2 = dungeon.reinfest_notices(c, gd, now=CYC + 2 + CYC, seen=seen)
    assert msgs2
    c.location_id = "whiterun"                                       # 他省 → 不報
    dungeon.mark_purged(c, gd, D, now=3 * CYC + 10)
    assert dungeon.reinfest_notices(c, gd, now=4 * CYC + 20, seen=set()) == []


def test_save_roundtrip_and_ensure_self_heal():
    gd, c = _char()
    c.cleared_dungeons = [D]
    c.dungeon_reinfest_at = {D: 48}
    d = json.loads(json.dumps(c.to_dict()))
    l = Character.from_dict(d)
    assert l.dungeon_reinfest_at == {D: 48}
    del d["dungeon_reinfest_at"]
    o = Character.from_dict(d)                                       # 舊檔缺欄 → 預設
    assert o.dungeon_reinfest_at == {}
    # ensure:舊檔回填(已清+參與滋擾+缺時間戳 → 一輪後滋擾;溫和升級不即刻全面重踞)
    dungeon.ensure_reinfest_fields(o, gd, now=100)
    assert o.dungeon_reinfest_at[D] == 100 + CYC
    # 型別/毀損自癒:非 dict → {};Infinity → OverflowError 剔除(R110 教訓);未來戳上夾;未知 id 保留
    c2 = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    c2.dungeon_reinfest_at = "corrupt"
    dungeon.ensure_reinfest_fields(c2, gd, now=100)
    assert c2.dungeon_reinfest_at == {D: 100 + CYC}                  # 矯正後回填
    c2.dungeon_reinfest_at = {D: float("inf"), "ghost_dungeon": 10**9, "kvatch_gate": 7,
                              "frostwind_ruin": float("nan"), "lostknife_cave": "bad"}
    dungeon.ensure_reinfest_fields(c2, gd, now=100)
    assert c2.dungeon_reinfest_at[D] == 100 + CYC                    # inf → OverflowError 剔除 → 回填
    assert c2.dungeon_reinfest_at["ghost_dungeon"] == 100 + CYC      # 🔴 未來戳上夾(且未知 id 保留 inert 非剔除)
    assert "frostwind_ruin" not in c2.dungeon_reinfest_at or \
        c2.dungeon_reinfest_at["frostwind_ruin"] == 100 + CYC        # NaN → ValueError 剔除(→ 已清才回填;未清不回填)
    assert "lostknife_cave" not in c2.dungeon_reinfest_at            # 字串值剔除(未清 → 不回填)
    snap = json.dumps(c2.dungeon_reinfest_at, sort_keys=True)
    dungeon.ensure_reinfest_fields(c2, gd, now=100)                  # 冪等
    assert snap == json.dumps(c2.dungeon_reinfest_at, sort_keys=True)
    # 進行中委託的 base 快照隨存檔往返(quest state 本就入檔)
    c3 = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    dungeon.mark_purged(c3, gd, D, now=0)
    quests.accept_quest(c3, gd, QID)
    b0 = c3.quests[QID]["base"]
    c4 = Character.from_dict(json.loads(json.dumps(c3.to_dict())))
    assert c4.quests[QID]["base"] == b0


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_reinfest 全通過")
