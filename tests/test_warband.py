"""招兵買馬 階段一回歸測試:資格門檻 / 營地 / 招募 / 攻城整合(大軍壓境 + 實戰援軍)。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import politics, warband


def _setup():
    gd = get_gamedata()
    c = build_character(gd, name="帥", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_warlord_gate():
    gd, c = _setup()
    assert not warband.is_warlord(c, gd)                  # 一介白身
    c.thaneships.append("bruma")                          # 武士 → 領主
    assert warband.is_warlord(c, gd)
    gd, c = _setup(); c.city_faction["windhelm"] = "imperial"   # 征服城 → 領主
    assert warband.is_warlord(c, gd)
    gd, c = _setup()                                      # 公會掌門 → 首領
    fid = next(iter(gd.factions)); c.factions[fid] = len(gd.factions[fid]["ranks"]) - 1
    assert warband.is_guildmaster(c, gd) and warband.is_warlord(c, gd)
    for cause in ("own",):                                # 擴張性大義(自立稱雄,對所有城為敵、無 thane 路)→ 自當可組軍
        gd, c = _setup(); c.allegiance = cause
        assert warband.is_warlord(c, gd), cause
    for cause in ("imperial", "independent"):             # 帝國/獨立有武士晉身之階 → 仍須先成領主
        gd, c = _setup(); c.allegiance = cause
        assert not warband.is_warlord(c, gd), cause


def test_camp_eligibility():
    gd, c = _setup(); c.thaneships.append("bruma")
    wild = next(lid for lid, l in gd.world["locations"].items() if l["type"] == "wilderness")
    city = next(lid for lid, l in gd.world["locations"].items() if l["type"] == "city")
    dgn = next(lid for lid, l in gd.world["locations"].items() if l["type"] == "dungeon")
    assert warband.can_make_camp(c, gd, wild)            # 野外可紮營
    assert not warband.can_make_camp(c, gd, city)        # 城內不行
    assert not warband.can_make_camp(c, gd, dgn)         # 地城未肅清 → 不行
    c.cleared_dungeons.append(gd.location(dgn)["dungeon"])
    assert warband.can_make_camp(c, gd, dgn)             # 肅清後可佔領
    gd, c = _setup()                                      # 非領主 → 哪都不能紮營
    assert not warband.can_make_camp(c, gd, wild)


def test_recruit_caps_and_costs():
    gd, c = _setup(); c.thaneships.append("bruma")
    assert warband.recruit_soldiers(c, 5) == 0           # 無營地不能招
    warband.make_camp(c, "bruma"); c.gold = 1000
    assert warband.recruit_soldiers(c, 5) == 5
    assert c.soldiers == 5 and c.gold == 1000 - 5 * warband.SOLDIER_COST
    c.gold = warband.SOLDIER_COST * 2                     # 金幣上限
    assert warband.recruit_soldiers(c, 10) == 2
    c.gold = 99999; c.soldiers = warband.MAX_SOLDIERS - 1  # 士兵上限
    assert warband.recruit_soldiers(c, 10) == 1 and c.soldiers == warband.MAX_SOLDIERS


def test_save_roundtrip_and_backward_compat():
    import json
    gd, c = _setup(); c.soldiers = 12; c.camp = "bruma"; c.wage_due_at = 123456
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.soldiers == 12 and loaded.camp == "bruma"
    assert loaded.wage_due_at == 123456                  # 折入 wage_due_at 往返
    d = c.to_dict()
    for k in ("soldiers", "camp", "wage_due_at"):
        del d[k]
    old = Character.from_dict(d)
    assert old.soldiers == 0 and old.camp == ""
    assert old.wage_due_at == 0                          # 舊存檔缺欄 → 預設 0


# --- 攻城整合煙霧 -------------------------------------------------------
def _siege(menu_seq, battle_result, soldiers=20):
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    c.allegiance = "imperial"; c.location_id = "windhelm"   # 敵城(獨立)
    c.soldiers = soldiers; c.camp = "bruma"
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    mseq = iter(menu_seq); captured = {}

    def battle(*a, **k):
        captured["companions"] = k.get("companions")
        return battle_result
    saved = (M.run_battle, ui.menu, ui.confirm, ui.message)
    M.run_battle = battle
    ui.menu = lambda *a, **k: next(mseq, None)
    ui.confirm = lambda *a, **k: True
    ui.message = lambda *a, **k: None
    try:
        res = M.action_siege(state, gd, "windhelm")
    finally:
        M.run_battle, ui.menu, ui.confirm, ui.message = saved
    return gd, c, res, captured


def test_army_press_depletes_garrison_once():
    gd, c, res, _ = _siege(["army", None], "victory", soldiers=20)   # 大軍壓境後退出
    seed = gd.rulers["windhelm"]["garrison"]
    assert politics.garrison_of(c, gd, "windhelm") == seed - 20 * warband.ARMY_SOFTEN_PER
    assert "army" in politics.ops_done(c, "windhelm")                # 每役一次(已記)


def test_assault_fields_soldiers_as_allies():
    gd, c, res, cap = _siege(["assault"], "victory", soldiers=20)
    assert res is None and politics.faction_of(c, gd, "windhelm") == "imperial"
    assert cap["companions"].count(warband.SOLDIER_TROOP) == warband.FIELD_CAP   # 6 名士兵上陣


# === 階段二:軍餉 ====================================================
def _state(c):
    return GameState(player=c, rng=RNG(1), game_mode="adventure")


def test_upkeep_grace_then_pay():
    gd, c = _setup(); c.soldiers = 5; c.gold = 1000
    st = _state(c)
    assert warband.tick_upkeep(st) == []                  # 首次有兵 → 一週寬限,不扣
    assert c.gold == 1000 and c.wage_due_at > 0
    assert warband.tick_upkeep(st) == []                  # 未到期 → 不扣
    assert c.gold == 1000
    st.time.advance(warband.WAGE_HOURS)                   # 到期
    evs = warband.tick_upkeep(st)
    assert len(evs) == 1 and evs[0]["kind"] == "paid"
    assert c.gold == 1000 - 5 * warband.WAGE_PER_SOLDIER
    assert c.soldiers == 5


def test_upkeep_desertion_when_broke():
    # 第一段:全付不出 → 半數未領餉者離營
    gd, c = _setup(); c.soldiers = 10; c.gold = 0
    st = _state(c); warband.tick_upkeep(st)               # 寬限
    st.time.advance(warband.WAGE_HOURS)
    evs = warband.tick_upkeep(st)
    assert evs[0]["kind"] == "desert"
    assert evs[0]["deserters"] == 5 and c.soldiers == 5   # max(1,(10+1)//2)=5
    assert c.gold == 0
    # 第二段(折入 partial_pay,需 fresh state):只付得起 3 名 → 部分付餉邊界
    gd, c = _setup(); c.soldiers = 10; c.gold = 3 * warband.WAGE_PER_SOLDIER
    st = _state(c); warband.tick_upkeep(st)
    st.time.advance(warband.WAGE_HOURS)
    evs = warband.tick_upkeep(st)
    assert evs[0]["kind"] == "desert"
    assert c.gold == 0 and evs[0]["deserters"] == 4 and c.soldiers == 6  # unpaid 7 → (7+1)//2=4


def test_upkeep_catches_up_multiple_periods():
    gd, c = _setup(); c.soldiers = 2; c.gold = 1000
    st = _state(c); warband.tick_upkeep(st)
    st.time.advance(warband.WAGE_HOURS * 3)              # 跳過 3 個週期(長途旅行/久候)
    evs = warband.tick_upkeep(st)
    assert len(evs) == 3 and all(e["kind"] == "paid" for e in evs)
    assert c.gold == 1000 - 3 * 2 * warband.WAGE_PER_SOLDIER


# === 階段二:永久傷亡 =================================================
def test_apply_casualties_deducts_roster():
    # 第一段:正常扣減(親衛 + 士兵混合陣亡)
    gd, c = _setup(); c.companions = ["sellsword", "veteran"]; c.soldiers = 6
    loss = warband.apply_casualties(c, gd, ["sellsword", "footman", "footman", "footman"])
    assert loss["soldiers"] == 3 and c.soldiers == 3          # 3 名士兵永久折損
    assert c.companions == ["veteran"]                        # 陣亡親衛移出名冊
    assert gd.companions["sellsword"]["name"] in loss["officers"]
    # 第二段(折入 clamps_and_ignores_unknown,需 fresh state):夾限 ≥0 + 未知 id 略過
    gd, c = _setup(); c.companions = []; c.soldiers = 2
    loss = warband.apply_casualties(c, gd, ["footman", "footman", "footman", "ghost_unit"])
    assert c.soldiers == 0 and loss["soldiers"] == 2         # 回報「實際扣減」(2)而非陣亡計數(3),士兵夾限 ≥0
    assert loss["officers"] == []                            # 不在名冊的 id 略過


def test_wipe_then_rebuild_gets_fresh_grace():
    """傷亡歸零 → 下一圈 tick 重置週期 → 重招得新寬限(對抗審查 [2] 回歸防線;非洗寬限漏洞,
    因無遣散士兵入口且重招成本遠高於週餉)。改動 tick_upkeep 的歸零重置前務必確認本測試仍綠。"""
    gd, c = _setup(); c.soldiers = 5; c.gold = 1000
    st = _state(c)
    warband.tick_upkeep(st)                              # 首次寬限,wage_due_at = now+H
    old_due = c.wage_due_at; assert old_due > 0
    warband.apply_casualties(c, gd, ["footman"] * 5)     # 攻城打光士兵(apply 不自行重置週期)
    assert c.soldiers == 0 and c.wage_due_at == old_due
    assert warband.tick_upkeep(st) == [] and c.wage_due_at == 0   # 下一圈頂端:無兵 → 清週期
    c.soldiers = 3                                       # 重建新軍
    assert warband.tick_upkeep(st) == [] and c.wage_due_at > 0    # 得新寬限,非立即扣餉


def test_run_battle_reports_dead_ally():
    """真實 run_battle:上陣士兵陣亡 → casualties 確實回報其來源 id(非召喚、非倖存者)。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    from tesrpg.systems import combat
    gd, c = _setup(); c.health = 9999; c.max_health = 9999      # 玩家不會死
    st = GameState(player=c, rng=RNG(3), game_mode="adventure")
    enemy = combat.spawn_creature(gd, "bandit", st.rng)
    enemy.max_health = 90; enemy.health = 90                    # 撐得過玩家首擊 → 敵人有機會出手

    real_spawn = combat.spawn_companion
    def weak_spawn(g, cid, rng, **kw):   # 接受同伴系統深化新增的 current_hp/max_health_bonus kwargs
        cre = real_spawn(g, cid, rng); cre.max_health = 1; cre.health = 1; cre.armor_rating = 0
        return cre

    saved = {"spawn": combat.spawn_companion, "pick": combat.pick_player_side_target,
             "choose": M._choose_combat_action, "rq": M._report_quests}
    msgs = {n: getattr(ui, n) for n in ("message", "combat_status_group", "combat_event",
                                        "combat_tick", "loot_report", "show_events")}
    combat.spawn_companion = weak_spawn
    combat.pick_player_side_target = lambda p, allies, rng: (combat.alive_list(allies)[0]
                                                             if combat.alive_list(allies) else p)
    M._choose_combat_action = lambda *a, **k: {"type": "attack", "target": enemy}
    M._report_quests = lambda *a, **k: None
    for n in msgs:
        setattr(ui, n, lambda *a, **k: None)
    fallen: list = []
    try:
        res = M.run_battle(st, gd, [enemy], companions=["footman"], casualties=fallen)
    finally:
        combat.spawn_companion = saved["spawn"]
        combat.pick_player_side_target = saved["pick"]
        M._choose_combat_action = saved["choose"]; M._report_quests = saved["rq"]
        for n, f in msgs.items():
            setattr(ui, n, f)
    assert res == "victory"
    assert fallen == ["footman"]                                # 陣亡士兵被回報、無誤報

    # --- 第二場戰鬥(折入 no_casualties_when_allies_survive):自身 patch 集、獨立 save/restore ---
    # 一般勝利、盟友全存活 → casualties 維持空(無誤報)。
    gd, c = _setup(); c.health = 9999; c.max_health = 9999
    st = GameState(player=c, rng=RNG(1), game_mode="adventure")
    enemy = combat.spawn_creature(gd, "giant_rat", st.rng)      # 弱敵,玩家首回合即清
    saved2 = {"choose": M._choose_combat_action, "rq": M._report_quests}
    msgs2 = {n: getattr(ui, n) for n in ("message", "combat_status_group", "combat_event",
                                         "combat_tick", "loot_report", "show_events")}
    M._choose_combat_action = lambda *a, **k: {"type": "attack", "target": enemy}
    M._report_quests = lambda *a, **k: None
    for n in msgs2:
        setattr(ui, n, lambda *a, **k: None)
    fallen2: list = []
    try:
        res2 = M.run_battle(st, gd, [enemy], companions=["sellsword"], casualties=fallen2)
    finally:
        M._choose_combat_action = saved2["choose"]; M._report_quests = saved2["rq"]
        for n, f in msgs2.items():
            setattr(ui, n, f)
    assert res2 == "victory" and fallen2 == []                  # 盟友存活 → 無折損


# === 階段二:親衛複合來源(warlord 將領)==============================
def test_warlord_officer_pool():
    gd, c = _setup()
    pool = warband.recruitable_officers(c, gd)
    assert "veteran" in pool              # warlord 將領可在營地招
    assert "sellsword" not in pool        # 一般傭兵走旅店,不入營地池
    assert "footman" not in pool          # 士兵不算將領
    assert gd.companions["footman"].get("troop") is True          # (折入)士兵兵種旗標 = 排除根因
    assert gd.companions["veteran"].get("warlord") is True        # (折入)將領旗標 = 入池根因(旅店招不到)
    assert warband.officer_cost(gd, "veteran") == 400             # (折入)將領招募成本
    c.companions.append("veteran")
    assert "veteran" not in warband.recruitable_officers(c, gd)   # 已在隊伍 → 不重複


# === 階段二:攻城永久折損煙霧(經 _siege_assault)====================
def test_siege_assault_applies_permanent_losses():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    c.allegiance = "imperial"; c.location_id = "windhelm"
    c.companions = ["sellsword"]; c.soldiers = 6; c.camp = "bruma"
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    c.garrison_current["windhelm"] = politics.WAVE_GARRISON - 10     # 守軍折至一波 → 單場決戰(波次永久折損測試)

    def battle(*a, **k):
        cas = k.get("casualties")
        if cas is not None:
            cas.extend(["sellsword", "footman", "footman"])      # 1 親衛 + 2 士兵陣亡
        return "victory"
    saved = (M.run_battle, ui.menu, ui.confirm, ui.message)
    M.run_battle = battle
    ui.menu = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True
    ui.message = lambda *a, **k: None
    try:
        M._siege_assault(state, gd, "windhelm", "風盔城")
    finally:
        M.run_battle, ui.menu, ui.confirm, ui.message = saved
    assert "sellsword" not in c.companions                        # 親衛永久折損
    assert c.soldiers == 4                                        # 6 - 2 士兵
    assert politics.faction_of(c, gd, "windhelm") == "imperial"   # 仍攻下


def run():
    test_warlord_gate()
    test_camp_eligibility()
    test_recruit_caps_and_costs()
    test_save_roundtrip_and_backward_compat()
    test_army_press_depletes_garrison_once()
    test_assault_fields_soldiers_as_allies()
    test_upkeep_grace_then_pay()
    test_upkeep_desertion_when_broke()
    test_upkeep_catches_up_multiple_periods()
    test_apply_casualties_deducts_roster()
    test_wipe_then_rebuild_gets_fresh_grace()
    test_run_battle_reports_dead_ally()
    test_warlord_officer_pool()
    test_siege_assault_applies_permanent_losses()


if __name__ == "__main__":
    run()
    print("test_warband 全通過")
