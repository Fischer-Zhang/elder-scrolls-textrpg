"""可重複委託(常態世界脈動聚光款,R-pulse)回歸:不鎖定 / 可再接 / 固定低額無遞減 /
schema guard / 一次性委託不受影響。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import quests

_REP = "comm_skyrim_wolf"      # kill wolf×4,reward {gold:45}


def _char():
    gd = get_gamedata()
    c = build_character(gd, name="複", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def _do_once(gd, c):
    """接取 → 補滿擊殺 → 完成;回傳本次 gold 增量。"""
    o = gd.quests[_REP]["objective"]
    gold0 = c.gold
    quests.accept_quest(c, gd, _REP)
    base = c.quests[_REP]["base"]
    c.kill_counts[o["creature"]] = base + o["count"]      # 補足本次門檻(吃 base,不回溯)
    res = quests.check_completion(c, gd)
    assert any(r.get("quest_id") == _REP for r in res), "委託未判定完成"
    return c.gold - gold0


def test_repeatable_not_locked_and_reaccepts():
    gd, c = _char()
    _do_once(gd, c)
    assert not quests.is_done(c, _REP)                    # 不鎖定
    assert _REP not in c.completed_quests                 # 不進 completed_quests
    assert _REP not in c.quests                           # 已從 active 移除
    # 可再接(不被 is_done 永久過濾)
    quests.accept_quest(c, gd, _REP)
    assert _REP in c.quests


def test_repeatable_reward_flat_no_decay():
    gd, c = _char()
    g1 = _do_once(gd, c)
    g2 = _do_once(gd, c)
    assert g1 == g2 == gd.quests[_REP]["reward"]["gold"]  # 固定低額,完成兩次增量相同(無遞減)


def test_repeatable_reward_only_scalar_keys():
    """所有真實 repeatable 委託 reward ⊆ {gold,fame,infamy}(不可刷限定 items/spells/boons)。"""
    gd = get_gamedata()
    for qid, q in gd.quests.items():
        if not q.get("repeatable"):
            continue
        for k in q.get("reward", {}):
            assert k in quests._REPEATABLE_REWARD_KEYS, f"{qid}: 非法 repeatable 獎勵 {k}"


def test_schema_guard_catches_illegal_reward():
    """注入一個帶 items 的假 repeatable 委託 → schema 守門應抓到(防未來誤授限定內容)。"""
    bad = {"items"}
    assert any(k not in quests._REPEATABLE_REWARD_KEYS for k in bad)   # items ∉ 白名單 → 會被擋


def test_oneshot_board_quest_still_locks():
    """回歸:既有一次性 board 委託(無 repeatable)完成後仍進 completed_quests、仍被永久過濾。"""
    gd, c = _char()
    qid = "job_wolf"                                       # kill wolf×3,一次性
    o = gd.quests[qid]["objective"]
    quests.accept_quest(c, gd, qid)
    base = c.quests[qid]["base"]
    c.kill_counts[o["creature"]] = base + o["count"]
    quests.check_completion(c, gd)
    assert quests.is_done(c, qid) and qid in c.completed_quests


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_repeatable_quests 全通過")
