"""開局起手任務(每個開局自動接取的 2–3 階段敘事任務線)回歸測試。

涵蓋:每個開局創角即接取其起手任務(且唯一 origin-source);NPC 不發;schema-lint
(source/階段數/objective type/引用 id);無 reach-self、無 collect 起始包物(以「建角即未達標」
一擊驗證);代表性鏈跑到完成且發獎;面板資料結構;存檔往返。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.systems import inventory, quests

WIRED = {"kill", "reach", "collect"}   # 起手任務允許的 objective(刻意禁 clear_dungeon,守 R18)


def _build(gd, oid, is_player=True):
    return build_character(gd, name="T", sex="male", race="nord", birthsign="warrior",
                           class_id="warrior", origin_id=oid, is_player=is_player)


def test_every_origin_grants_its_quest():
    """每個有 quest 欄的開局 → 創角後該任務在 char.quests,且是唯一 origin-source 任務。"""
    gd = get_gamedata()
    for oid, od in gd.origins.items():
        assert "quest" in od, f"{oid} 未配起手任務"
        c = _build(gd, oid)
        qid = od["quest"]
        assert qid in c.quests, f"{oid}: 起手任務未自動接取"
        assert qid not in c.completed_quests
        origin_active = [q for q in c.quests if gd.quests[q].get("source") == "origin"]
        assert origin_active == [qid], f"{oid}: origin 任務不唯一 {origin_active}"


def test_npc_build_gets_no_origin_quest():
    """NPC(is_player=False,如傭兵)創建不發起手任務。"""
    gd = get_gamedata()
    npc = _build(gd, "sellsword", is_player=False)
    assert npc.quests == {}


def test_origin_quest_schema_lint():
    """掃全部 origin 任務:source/階段數/objective type/引用 id 合法,禁 clear_dungeon。"""
    gd = get_gamedata()
    origin_qids = {od["quest"] for od in gd.origins.values() if "quest" in od}
    assert len(origin_qids) >= 24, f"起手任務數異常:{len(origin_qids)}"
    for qid in origin_qids:
        q = gd.quests[qid]
        assert q.get("source") == "origin", f"{qid}: source 非 origin"
        assert q.get("turn_in") == "auto", f"{qid}: turn_in 非 auto"
        assert q.get("name") and q.get("text"), f"{qid}: 缺 name/text"
        stages = q.get("stages") or [{"objective": q["objective"]}]
        assert 1 <= len(stages) <= 3, f"{qid}: 階段數 {len(stages)} 超出 1–3"
        for s in stages:
            o = s["objective"]
            assert o["type"] in WIRED, f"{qid}: objective {o['type']} 不允許(禁地城)"
            if o["type"] == "kill":
                assert o["creature"] in gd.bestiary, f"{qid}: creature {o['creature']}"
                assert o.get("count", 0) >= 1
            elif o["type"] == "reach":
                assert o["location"] in gd.world["locations"], f"{qid}: location {o['location']}"
            elif o["type"] == "collect":
                assert gd.item_or_none(o["item"]) is not None, f"{qid}: item {o['item']}"


def test_no_reach_self_pitfall():
    """任何階段都不得 reach 該開局自身起始地(否則創角即時完成該階段)。"""
    gd = get_gamedata()
    for oid, od in gd.origins.items():
        start = od.get("location", gd.world["start_location"])
        q = gd.quests[od["quest"]]
        for i, s in enumerate(q.get("stages") or [{"objective": q["objective"]}]):
            o = s["objective"]
            if o["type"] == "reach":
                assert o["location"] != start, f"{oid}: 階段{i} reach 自身起始地 {start}"


def test_not_premet_on_creation():
    """建角後起手任務第 0 階段尚未達標(一擊抓 reach-self + collect 起始包物 + kill base)。"""
    gd = get_gamedata()
    for oid, od in gd.origins.items():
        c = _build(gd, oid)
        qid = od["quest"]
        assert not quests.objective_met(c, gd, qid), f"{oid}: 起手任務創角即達標(踩 pitfall)"
        # collect 階段不得被起始包/開局物即時滿足
        for s in (gd.quests[qid].get("stages") or [{"objective": gd.quests[qid]["objective"]}]):
            o = s["objective"]
            if o["type"] == "collect":
                assert inventory.count_item(c, o["item"]) < o["count"], \
                    f"{oid}: collect {o['item']} 已被起始物滿足"


def _drive(c, gd, qid, max_iter=40):
    for _ in range(max_iter):
        if qid in c.completed_quests:
            return
        o, _, _ = quests.current_objective(c, gd, qid)
        if o["type"] == "kill":
            for _ in range(o["count"]):
                quests.record_kill(c, o["creature"])
        elif o["type"] == "reach":
            c.location_id = o["location"]
        elif o["type"] == "collect":
            inventory.add_item(c, o["item"], o["count"])
        quests.check_completion(c, gd)
    raise AssertionError(f"{qid} 未在 {max_iter} 圈內完成")


def test_representative_chains_complete_and_reward():
    """代表性鏈(含 collect / 新開局 / 2 階 / 3 階)跑到完成並發獎。"""
    gd = get_gamedata()
    for oid in ("newcomer", "mage_initiate", "fugitive", "wood_hunter", "ashlander", "wandering_bard"):
        c = _build(gd, oid)
        qid = gd.origins[oid]["quest"]
        gold0, fame0 = c.gold, c.fame
        _drive(c, gd, qid)
        assert qid in c.completed_quests
        rw = gd.quests[qid].get("reward", {})
        assert c.gold == gold0 + rw.get("gold", 0)
        assert c.fame == fame0 + rw.get("fame", 0)


def test_reward_band_modest():
    """起手任務獎勵維持 level-1 級(gold ≤ 90、fame ≤ 5),不蓋過公會/告示板委託。"""
    gd = get_gamedata()
    for od in gd.origins.values():
        rw = gd.quests[od["quest"]].get("reward", {})
        assert rw.get("gold", 0) <= 90 and rw.get("fame", 0) <= 5


def test_quests_view_grouped_and_sheet_origin():
    """面板資料:任務日誌分組(起手任務獨立組 + 階段進度);角色卡帶出身 + 起手任務。"""
    from tesrpg.ui import console as ui
    gd = get_gamedata()
    c = _build(gd, "knight_aspirant")
    qv = ui._quests_view(c, gd)
    titles = [g["title"] for g in qv["groups"]]
    assert any("起手" in t for t in titles), titles
    intro = next(q for g in qv["groups"] for q in g["quests"] if q["name"] == "騎士試煉")
    assert intro["stage"][1] == 3 and intro["stages"][0]["state"] == "cur"
    ov = ui._origins_view(gd)
    assert len(ov["origins"]) == len(gd.origins) and any(o["quest"] for o in ov["origins"])
    sv = ui._sheet_view(c, gd)
    assert sv["origin"] == "騎士見習" and sv["intro_quest"]["name"] == "騎士試煉"


def test_origin_categories_cover_all():
    """兩層開局選單:分類涵蓋全部開局、無重複(漏歸類會掉出選單)。"""
    import tesrpg.main as M
    gd = get_gamedata()
    listed = [o for _, oids in M.ORIGIN_CATEGORIES for o in oids]
    assert len(listed) == len(set(listed)), "開局分類有重複"
    assert set(listed) == set(gd.origins), f"分類未涵蓋全部開局:{set(gd.origins) ^ set(listed)}"


def test_save_roundtrip_preserves_active_origin_quest():
    gd = get_gamedata()
    c = _build(gd, "fugitive")
    qid = gd.origins["fugitive"]["quest"]
    c2 = Character.from_dict(c.to_dict())
    assert qid in c2.quests and c2.quests[qid].get("stage") == c.quests[qid].get("stage")


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_origin_quests 全通過")
