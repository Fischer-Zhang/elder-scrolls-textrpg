"""M10:多階段任務線 + 公會精英階登頂。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import factions, inventory, quests


def _char():
    gd = get_gamedata()
    return gd, build_character(gd, name="俠", sex="male", race="nord",
                               birthsign="warrior", class_id="warrior")


def _satisfy_current_stage(c, gd, qid):
    """讓當前階段達標(依目標型別灌入對應進度)。"""
    obj, _, _ = quests.current_objective(c, gd, qid)
    t = obj["type"]
    if t == "kill":
        for _ in range(obj["count"]):
            quests.record_kill(c, obj["creature"])
    elif t == "clear_dungeon":
        quests.record_dungeon_clear(c, obj["dungeon"])
    elif t == "reach":
        c.location_id = obj["location"]
    elif t == "collect":
        inventory.add_item(c, obj["item"], obj["count"])


def _complete_quest(c, gd, qid):
    quests.accept_quest(c, gd, qid)
    for _ in range(30):
        _satisfy_current_stage(c, gd, qid)
        quests.check_completion(c, gd)
        if qid in c.completed_quests:
            return
    raise AssertionError(f"未能完成 {qid}")


# --- 多階段機制 ---------------------------------------------------------
def test_multistage_advances_stage_by_stage():
    gd, c = _char()
    factions.join(c, "fighters_guild")
    c.factions["fighters_guild"] = 5            # fg6 需 rank 5(雙階段:骷髏→熊)
    quests.accept_quest(c, gd, "fg6")
    assert quests.current_objective(c, gd, "fg6")[1] == 0     # 階段 0
    # 滿足第一階段(殺骷髏)→ 推進,尚未完成
    for _ in range(3):
        quests.record_kill(c, "skeleton")
    evs = quests.check_completion(c, gd)
    assert any(e["type"] == "stage_advanced" for e in evs)
    assert "fg6" in c.quests and quests.current_objective(c, gd, "fg6")[1] == 1
    assert not any(e["type"] == "completed" for e in evs)
    # 第二階段(殺熊)→ 完成 + 晉升
    for _ in range(2):
        quests.record_kill(c, "bear")
    evs = quests.check_completion(c, gd)
    assert any(e["type"] == "completed" for e in evs)
    assert factions.rank_index(c, "fighters_guild") == 6


def test_kill_base_resnapshots_per_stage():
    """進入新 kill 階段前的擊殺不可計入該階段。"""
    gd, c = _char()
    c.factions["fighters_guild"] = 5
    quests.accept_quest(c, gd, "fg6")
    # 在第一階段時就先殺了一堆熊(下一階段的目標)
    for _ in range(5):
        quests.record_kill(c, "bear")
    for _ in range(3):
        quests.record_kill(c, "skeleton")
    quests.check_completion(c, gd)               # 推進到熊階段(此時 base 記為 5)
    assert quests.current_objective(c, gd, "fg6")[0]["type"] == "kill"
    got, need = quests.kill_progress(c, gd, "fg6")
    assert got == 0 and need == 2                 # 既往 5 隻不算,須重新殺 2 隻
    for _ in range(2):
        quests.record_kill(c, "bear")
    quests.check_completion(c, gd)
    assert "fg6" in c.completed_quests


def test_multistage_collect_consumes_each_stage():
    gd, c = _char()
    c.factions["thieves_guild"] = 3
    quests.accept_quest(c, gd, "tg4")            # 階段1 collect ruby x3 → 階段2 reach blacklight
    inventory.add_item(c, "ruby", 3)
    quests.check_completion(c, gd)
    assert inventory.count_item(c, "ruby") == 0  # 第一階段上繳消耗
    assert quests.current_objective(c, gd, "tg4")[0]["type"] == "reach"
    c.location_id = "blacklight"
    quests.check_completion(c, gd)
    assert "tg4" in c.completed_quests


def test_objective_text_shows_stage_indicator():
    gd, c = _char()
    c.factions["fighters_guild"] = 6
    quests.accept_quest(c, gd, "fg7")            # 三階段
    assert quests.objective_text(c, gd, "fg7").startswith("[1/3]")


# --- 全公會登頂 ---------------------------------------------------------
def test_full_guild_ascension_to_master():
    gd, c = _char()
    for fid in ("fighters_guild", "mages_guild", "thieves_guild"):
        factions.join(c, fid)
        ranks = gd.factions[fid]["ranks"]
        rank_quests = gd.factions[fid]["rank_quests"]
        for i, qid in enumerate(rank_quests):
            assert quests.available_quests(c, gd, "guild", fid) == [qid], (fid, i)
            _complete_quest(c, gd, qid)
            assert factions.rank_index(c, fid) == i + 1
        # 登頂:已達最高階,無更多晉升任務
        assert factions.rank_index(c, fid) == len(rank_quests)
        assert quests.available_quests(c, gd, "guild", fid) == []
        assert factions.rank_name(c, gd, fid) == ranks[len(rank_quests)]


def test_negative_stage_clamped():
    """回歸(審查):毀損存檔的負 stage 不可經 Python 負索引取到末階段。"""
    gd, c = _char()
    c.factions["fighters_guild"] = 5
    quests.accept_quest(c, gd, "fg6")
    c.quests["fg6"]["stage"] = -1
    obj, idx, total = quests.current_objective(c, gd, "fg6")
    assert idx == 0                                  # 夾限至第一階段,而非 stages[-1]
    assert obj == gd.quests["fg6"]["stages"][0]["objective"]


def test_single_objective_quests_still_work():
    """單目標任務(無 stages)仍正常運作。"""
    gd, c = _char()
    quests.accept_quest(c, gd, "job_wolf")       # kill wolf x3
    for _ in range(3):
        quests.record_kill(c, "wolf")
    evs = quests.check_completion(c, gd)
    assert any(e["type"] == "completed" and e["quest_id"] == "job_wolf" for e in evs)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m10 OK")
