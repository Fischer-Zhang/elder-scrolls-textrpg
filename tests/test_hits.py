"""R109 Phase A 引擎:暗殺 objective / 任務條件式狩獵生成 / 謀殺目擊制。

涵蓋:assassinate 目標判定 + 文字;active_hunt_target(省份配對/僅 weight-0 劇情敵/決定性/
無任務→None 保 byte-identical);murder_witness_chance(城>鎮>野·潛行/夜遞減·夾限);
record_murder witnessed vs 潛殺乾淨(賞金/惡名僅目擊時加·血債恆計)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import brotherhood, crime, quests


def _st(seed=1):
    gd = get_gamedata()
    c = build_character(gd, name="H", sex="male", race="imperial", birthsign="thief",
                        class_id="assassin")
    c.is_player = True
    c.level = 10
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=12))
    return gd, c, st


def _wild_in(gd, province):
    return [l for l, v in gd.world["locations"].items()
            if v.get("province") == province and v.get("type") == "wilderness"][0]


def _first(gd, loc_type):
    return [l for l, v in gd.world["locations"].items() if v.get("type") == loc_type][0]


# --- assassinate objective --------------------------------------------------
def test_assassinate_objective_met_by_murdered_npcs():
    gd, c, st = _st()
    obj = {"type": "assassinate", "npc": "olfina"}
    assert not quests._objective_met(c, gd, obj, 0)
    c.murdered_npcs.append("olfina")
    assert quests._objective_met(c, gd, obj, 0)


# --- active_hunt_target -----------------------------------------------------
def test_hunt_target_matches_province_only():
    gd, c, st = _st()
    quests.accept_quest(c, gd, "cint_skyrim_spies")   # provinces=天際·kill rogue_thief(weight0)
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "天際")) == "rogue_thief"
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "賽羅迪爾")) is None   # 不符省 → 不獵


def test_hunt_target_none_without_quest_is_byte_safe():
    gd, c, st = _st()
    # 無任何 kill 任務 → 恆 None(world.travel 據此走原路徑·byte-identical 前提)
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "天際")) is None


def test_hunt_target_ignores_normal_pool_creatures():
    gd, c, st = _st()
    # comm_ 委託目標是野遇池怪(weight>0)→ 不走狩獵鉤子(池裡本就抽得到)
    quests.accept_quest(c, gd, "comm_skyrim_wolf")   # kill wolf(weight>0)
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "天際")) is None


def test_hunt_hook_can_spawn_target_on_travel():
    from tesrpg.systems import world
    gd, c, st = _st()
    quests.accept_quest(c, gd, "cint_skyrim_spies")
    # 找一條「終點在天際、危險度>0」的旅行邊,多 seed 跑 travel,應能撞見 rogue_thief
    src = None
    for lid, v in gd.world["locations"].items():
        if v.get("province") == "天際":
            for dst in v.get("links", {}):
                d = gd.world["locations"][dst]
                if d.get("province") == "天際" and d.get("type") == "wilderness" and d.get("danger", 0) > 0:
                    src, dest = lid, dst
                    break
        if src:
            break
    assert src, "找不到天際野外旅行邊"
    seen = False
    for seed in range(40):
        c.location_id = src
        c.fatigue = c.max_fatigue
        r = world.travel(c, gd, dest, GameTime(hour=12), RNG(seed))
        foe = r["foe"]
        if foe is not None and getattr(foe, "template_id", None) == "rogue_thief":
            seen = True
            break
    assert seen, "狩獵鉤子未能在天際野外生成 rogue_thief"


# --- 謀殺目擊制 -------------------------------------------------------------
def test_witness_chance_by_guard_density_and_stealth():
    gd, c, st = _st()
    c.skills["sneak"] = 0
    c.location_id = _first(gd, "city")
    city_day = crime.murder_witness_chance(c, gd, night=False)
    c.location_id = _first(gd, "town")
    town_day = crime.murder_witness_chance(c, gd, night=False)
    wild = _wild_in(gd, "賽羅迪爾")
    c.location_id = wild
    wild_day = crime.murder_witness_chance(c, gd, night=False)
    assert city_day > town_day > wild_day             # 城守密度:大城>小鎮>野外
    # 潛行 + 夜色顯著降低目擊率
    c.location_id = _first(gd, "city")
    c.skills["sneak"] = 100
    assert crime.murder_witness_chance(c, gd, night=True) < city_day
    # 夾限
    assert crime.MURDER_WITNESS_FLOOR <= crime.murder_witness_chance(c, gd, night=True) <= crime.MURDER_WITNESS_CEIL


def test_record_murder_witnessed_vs_clean():
    gd, c, st = _st()
    c.location_id = _first(gd, "city")
    prov = crime.province_of(c, gd)
    # 目擊 → 賞金+惡名(既有行為·預設 witnessed=True)
    r = brotherhood.record_murder(st, gd, "olfina", witnessed=True)
    assert r["bounty"] == brotherhood.MURDER_BOUNTY and crime.bounty(c, prov) == brotherhood.MURDER_BOUNTY
    assert c.infamy == brotherhood.MURDER_INFAMY and "olfina" in c.murdered_npcs and c.murders == 1
    # 潛殺乾淨 → 血債照計、NPC 照除,但零賞金/零惡名
    inf0, b0 = c.infamy, crime.bounty(c, prov)
    r2 = brotherhood.record_murder(st, gd, "brand", witnessed=False)
    assert r2["bounty"] == 0 and crime.bounty(c, prov) == b0 and c.infamy == inf0
    assert "brand" in c.murdered_npcs and c.murders == 2


# --- Phase B:置放 NPC 暗殺 / 多目標 / 授權 / 聞訊備戰 --------------------------
def test_multi_target_assassinate_completes_when_all_dead():
    gd, c, st = _st()
    quests.accept_quest(c, gd, "cintlead_markarth")   # assassinate [cint_mark_a, cint_mark_b]
    obj, _, _ = quests.current_objective(c, gd, "cintlead_markarth")
    assert obj["type"] == "assassinate" and len(obj["npcs"]) == 2
    c.murdered_npcs.append("cint_mark_a")
    assert not quests._objective_met(c, gd, obj, 0)      # 只殺一名 → 未完成
    c.murdered_npcs.append("cint_mark_b")
    assert quests._objective_met(c, gd, obj, 0)          # 全殺 → 完成


def test_sanctioned_only_for_counterintel():
    gd, c, st = _st()
    quests.accept_quest(c, gd, "cintlead_markarth")      # 反間=授權
    quests.accept_quest(c, gd, "infamy_dirty_job")       # 黑名=謀殺(非授權)
    assert quests.assassination_sanctioned(c, gd, "cint_mark_a") is True
    assert quests.assassination_sanctioned(c, gd, "hit_dirty_a") is False
    # 無 active 任務 → 非授權(任務外殺同一人仍是謀殺)
    c.quests.clear()
    assert quests.assassination_sanctioned(c, gd, "cint_mark_a") is False


def test_survivor_alerted_after_one_day():
    gd, c, st = _st()
    quests.accept_quest(c, gd, "cintlead_markarth")
    # 殺第一名 + 戳記首殺日
    c.murdered_npcs.append("cint_mark_a")
    quests.record_hit_day(c, gd, "cint_mark_a", today=10)
    assert not quests.hit_target_alerted(c, gd, "cint_mark_b", today=10)   # 當天 → 尚未備戰
    assert quests.hit_target_alerted(c, gd, "cint_mark_b", today=11)       # 逾 1 日 → 聞訊備戰
    assert gd.bestiary["cint_mark_b" and "blade_agent_alerted"]["max_health"] > \
        gd.bestiary["blade_agent"]["max_health"]                          # 強化模板更硬


def test_action_murder_sanctioned_no_penalty(monkey=None):
    """授權暗殺(反間目標)戰後零賞金 + 抹去 NPC + 任務完成(stub run_battle 隔離戰鬥 RNG)。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c, st = _st()
    ui.message = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True
    ui.rule = lambda *a, **k: None
    orig_rb, orig_sa = M.run_battle, M.combat.try_stealth_approach
    M.run_battle = lambda *a, **k: "victory"
    M.combat.try_stealth_approach = lambda *a, **k: True
    try:
        c.location_id = "markarth"
        quests.accept_quest(c, gd, "cintlead_markarth")
        M.action_murder(st, gd, "cint_mark_a")
        assert crime.bounty(c, "天際") == 0 and c.infamy == 0    # 授權除敵諜 → 零賞金/零惡名
        assert "cint_mark_a" in c.murdered_npcs
        assert quests.record_hit_day.__name__            # 已戳記(同夥存活)
        assert c.quests["cintlead_markarth"].get("hit_day") is not None
        M.action_murder(st, gd, "cint_mark_b")           # 殺第二名 → 任務完成
        assert "cintlead_markarth" not in c.quests and "cintlead_markarth" in c.completed_quests
        assert crime.bounty(c, "天際") == 0               # 全程授權 → 仍零賞金
    finally:
        M.run_battle, M.combat.try_stealth_approach = orig_rb, orig_sa
    importlib_reload_ui()


def importlib_reload_ui():
    import importlib
    from tesrpg.ui import console as ui
    importlib.reload(ui)


def test_converted_oneshots_target_placed_npcs():
    gd = get_gamedata()
    oneshots = ["cintlead_markarth", "cintlead_sentinel", "cintlead_anvil", "cintlead_vivec",
                "cintlead_gideon", "ucov_fighters_extract", "ucov_fighters_defect",
                "ucov_knights_extract", "ucov_knights_defect", "infamy_dirty_job"]
    for qid in oneshots:
        obj = gd.quests[qid]["objective"]
        assert obj["type"] == "assassinate", qid
        for nid in obj["npcs"]:
            npc = gd.npcs.get(nid)
            assert npc and npc.get("combat_template"), (qid, nid)
            assert npc["combat_template"] + "_alerted" in gd.bestiary or \
                npc.get("combat_template_alerted") in gd.bestiary, (qid, nid)
    # 反間=授權、地下/臥底=非授權
    assert gd.quests["cintlead_markarth"].get("sanctioned") is True
    assert not gd.quests["infamy_dirty_job"].get("sanctioned")
    assert not gd.quests["ucov_fighters_extract"].get("sanctioned")


def test_db_contract_is_field_assassination_witness_gated_and_promotes():
    """R109 Phase C:DB 合約改城內置放 NPC 暗殺(非 sanctioned=走目擊制)+ 大廳不出擊只指路 +
    完成仍晉升。stub run_battle 隔離戰鬥。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    from tesrpg.systems import brotherhood, factions
    gd, c, st = _st()
    c.skills.update(sneak=80, blade=60)
    factions.join(c, brotherhood.FACTION)
    quests.accept_quest(c, gd, "db1")
    obj, _, _ = quests.current_objective(c, gd, "db1")
    assert obj["type"] == "assassinate" and obj["npcs"] == ["db_greedy"]
    assert not quests.assassination_sanctioned(c, gd, "db_greedy")     # DB=反派謀殺·走目擊(非授權)
    # 大廳:進行中 assassinate → 回指路 hint、不提供 execute
    hint = M._contract_hint(st, gd, "db1")           # 鐵律:大廳不出擊·只指路
    assert hint and "奧崔斯" in hint
    # 前往目標城市暗殺 → 完成 + 晉升
    ui.message = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True
    ui.rule = lambda *a, **k: None
    orig_rb, orig_sa = M.run_battle, M.combat.try_stealth_approach
    M.run_battle = lambda *a, **k: "victory"
    M.combat.try_stealth_approach = lambda *a, **k: True
    try:
        c.location_id = gd.npcs["db_greedy"]["location"]
        M.action_murder(st, gd, "db_greedy")
        assert "db_greedy" in c.murdered_npcs
        assert "db1" in c.completed_quests and brotherhood.rank(c) == 1
    finally:
        M.run_battle, M.combat.try_stealth_approach = orig_rb, orig_sa
    importlib_reload_ui()


def test_converted_faction_contracts_target_placed_npcs():
    gd = get_gamedata()
    checks = {"db1": "db_greedy", "db2": "db_thief", "db4": "db_knight", "db5": "db_champion",
              "md1": "md_faithful", "md2": "md_blade", "md4": "md_paladin", "md5": "md_highpriest"}
    for qid, nid in checks.items():
        obj = gd.quests[qid]["objective"]
        assert obj["type"] == "assassinate" and obj["npcs"] == [nid], qid
        assert gd.npcs[nid]["combat_template"] in gd.bestiary
        assert not gd.quests[qid].get("sanctioned")      # DB/神話黎明=目擊制,非授權
    # db3/md3 怪物目標保留 kill(大廳出擊/野遇)
    assert gd.quests["db3"]["objective"]["type"] == "kill"
    assert gd.quests["md3"]["objective"]["type"] == "kill"
    # db6/md6 分支目標皆 assassinate 置放 NPC
    for qid in ("db6", "md6"):
        for b in gd.quests[qid]["branches"]:
            assert b["objective"]["type"] == "assassinate"


# --- 對抗審查修正回歸(R109 review)--------------------------------------------
def test_hunt_hook_requires_location_spec():
    """狩獵鉤子只在任務有 hunt_location 或 provinces 時觸發·且精確定位:
    kn2(hunt_location=jerall_mountains)只在該地點刷、他處不刷;weight>0 目標(fg1 wolf)永不走鉤子。"""
    gd, c, st = _st()
    quests.accept_quest(c, gd, "kn2")   # kill necromancer_acolyte(weight0·hunt_location 傑拉山脈)
    assert gd.quests["kn2"].get("hunt_location") == "jerall_mountains"
    assert quests.active_hunt_target(c, gd, "jerall_mountains") == "necromancer_acolyte"  # 只在該地點
    for other in ("imperial_road", "gold_coast", _wild_in(gd, "天際")):
        assert quests.active_hunt_target(c, gd, other) is None                            # 他處不刷
    c.quests.clear()
    quests.accept_quest(c, gd, "fg1")   # kill wolf(weight>0·野遇池)→ 不走狩獵鉤子
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "天際")) is None


def test_db3_md3_precise_hunt_location_not_hall_execute():
    """使用者拍板:唯一 villain(db3/md3)精確到 hunt_location(非整省),大廳不出擊只指路(鐵律)。"""
    import tesrpg.main as M
    gd, c, st = _st()
    assert gd.quests["db3"].get("hunt_location") == "colovian_highlands"
    assert gd.quests["md3"].get("hunt_location") == "ashland_waste"
    assert not gd.quests["db3"].get("provinces")   # 不再整省
    quests.accept_quest(c, gd, "db3")
    assert quests.active_hunt_target(c, gd, "colovian_highlands") == "reclusive_mage"   # 只在該地點
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "賽羅迪爾")) is None            # 同省其他地點不獵
    hint = M._contract_hint(st, gd, "db3")
    assert hint and "科洛溫高地" in hint             # 大廳指路到精確地點·不出擊


def test_clean_bonus_removed_from_converted_contracts():
    """審查修正:轉 assassinate / 野外狩獵的 DB/神話黎明合約不再帶死 clean_bonus(舊路徑不發放)。"""
    gd = get_gamedata()
    for qid in ("db1", "db2", "db4", "db5", "md1", "md2", "md4", "md5", "db3", "md3"):
        assert "clean_bonus" not in gd.quests[qid], qid
        for b in gd.quests[qid].get("branches", []):
            assert "clean_bonus" not in b, qid


def test_premurder_allowed_completes_and_promotes():
    """使用者拍板:預先謀殺算數(不軍鎖階梯)。先殺 db_greedy → 接 db1 → 完成 + 晉升。"""
    from tesrpg.systems import brotherhood, factions
    gd, c, st = _st()
    c.skills.update(sneak=80, blade=60)
    factions.join(c, brotherhood.FACTION)
    c.murdered_npcs.append("db_greedy")            # 接取前已了結目標
    quests.accept_quest(c, gd, "db1")
    evs = quests.check_completion(c, gd)
    assert any(e["type"] == "completed" and e.get("promoted") for e in evs)
    assert brotherhood.rank(c) == 1                # 允許 → 晉升(不軍鎖)


def run():
    try:
        for name in sorted(globals()):
            if name.startswith("test_"):
                globals()[name]()
                print(f"  ✓ {name}")
    finally:
        importlib_reload_ui()   # 還原被 patch 的 ui 原語,避免污染後續測試模組
