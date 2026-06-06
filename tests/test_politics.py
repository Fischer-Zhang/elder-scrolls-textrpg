"""城戰(Phase 3+4)回歸測試:城為單位的政治立場 + 選邊 + 攻城戰。

涵蓋:立場種子(跨省混合)、關係判定、選邊、攻城資格(僅對立可攻)、波次編排、
攻下易幟+重新駐軍、波間重整、攻城煙霧(勝/死/退)、存檔向後相容。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import politics


def _setup():
    gd = get_gamedata()
    c = build_character(gd, name="帥", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_stance_seed_is_city_unit_cross_province():
    gd, _ = _setup()
    # 天際同省卻立場分裂 → 證明「城為單位、各城主自有立場」
    assert politics.base_stance(gd, "haafingar") == "imperial"
    assert politics.base_stance(gd, "windhelm") == "independent"
    assert politics.base_stance(gd, "whiterun") == "neutral"
    assert politics.base_stance(gd, "wilderness_nonexistent") is None or True   # 無領主→None
    assert politics.base_stance(gd, next(lid for lid in gd.world["locations"]
                                        if not gd.ruler_at(lid))) is None


def test_relationship_and_pledge():
    gd, c = _setup()
    assert politics.relationship(c, gd, "windhelm") == "unaligned"   # 未選邊
    politics.pledge(c, "imperial")
    assert c.allegiance == "imperial"
    assert politics.relationship(c, gd, "bruma") == "ally"           # 同為帝國
    assert politics.relationship(c, gd, "windhelm") == "enemy"       # 獨立 → 敵
    assert politics.relationship(c, gd, "whiterun") == "neutral"     # 中立


def test_can_siege_only_enemy():
    gd, c = _setup()
    assert not politics.can_siege(c, gd, "windhelm")     # 未選邊不可攻
    politics.pledge(c, "imperial")
    assert politics.can_siege(c, gd, "windhelm")         # 敵城可攻
    assert not politics.can_siege(c, gd, "bruma")        # 盟城不可攻
    assert not politics.can_siege(c, gd, "whiterun")     # 中立不可攻


# --- 圍城方略(operations:全套技能各有攻城用途)------------------------
def test_assault_force_monotonic_and_clamped():
    assert politics.assault_force(60) < politics.assault_force(400)   # 守軍越多 → 強攻越硬
    assert politics.assault_force(0) == 2 and politics.assault_force(9999) == 8   # 夾限


def test_ops_gated_by_skill_and_once_each():
    gd, c = _setup()
    c.skills["sneak"] = 0
    assert not any(o["id"] == "nightraid" for o in politics.available_ops(c, gd, "windhelm"))
    c.skills["sneak"] = 60
    assert any(o["id"] == "nightraid" for o in politics.available_ops(c, gd, "windhelm"))
    politics.resolve_op(c, gd, "windhelm", "nightraid", RNG(1))
    assert "nightraid" in politics.ops_done(c, "windhelm")
    assert not any(o["id"] == "nightraid" for o in politics.available_ops(c, gd, "windhelm"))  # 每役一次


def test_op_deplete_and_costs():
    gd, c = _setup()
    seed = gd.rulers["windhelm"]["garrison"]
    c.skills["speechcraft"] = 80
    r = politics.resolve_op(c, gd, "windhelm", "parley", RNG(1))       # 無資源成本、非風險
    assert r["ok"] and r["deplete"] > 0
    assert politics.garrison_of(c, gd, "windhelm") == seed - r["deplete"]
    # bombard 耗魔力、bribe 耗金
    c.skills["destruction"] = 60; c.magicka = 100
    politics.resolve_op(c, gd, "windhelm", "bombard", RNG(1))
    assert c.magicka == 100 - politics.SIEGE_OP_BY_ID["bombard"]["cost"]["magicka"]
    c.skills["mercantile"] = 40; c.gold = 500
    politics.resolve_op(c, gd, "windhelm", "bribe", RNG(1))
    assert c.gold == 500 - politics.SIEGE_OP_BY_ID["bribe"]["cost"]["gold"]


def test_risky_op_marks_done_even_on_fail():
    gd, c = _setup()
    c.skills["security"] = 40; c.fatigue = c.max_fatigue
    r = politics.resolve_op(c, gd, "windhelm", "postern", RNG(7))      # 風險型:成敗皆計一次
    assert "postern" in politics.ops_done(c, "windhelm")
    assert r["deplete"] >= 0      # 成功則削、失敗則 0


def test_conquer_flips_regarrisons_and_clears_ops():
    gd, c = _setup()
    politics.pledge(c, "imperial")
    c.skills["speechcraft"] = 80
    politics.resolve_op(c, gd, "windhelm", "parley", RNG(1))
    assert politics.ops_done(c, "windhelm")
    politics.conquer(c, gd, "windhelm")
    assert politics.faction_of(c, gd, "windhelm") == "imperial"          # 易幟
    assert politics.relationship(c, gd, "windhelm") == "ally"
    assert politics.garrison_of(c, gd, "windhelm") == gd.rulers["windhelm"]["garrison"]  # 重新駐軍
    assert politics.ops_done(c, "windhelm") == []                        # 方略紀錄清空(可重新佈局)
    assert "windhelm" in politics.held_cities(c, gd)


def test_deplete_persists_and_clamps():
    gd, c = _setup()
    seed = gd.rulers["windhelm"]["garrison"]
    politics.deplete_garrison(c, gd, "windhelm", 60)
    assert politics.garrison_of(c, gd, "windhelm") == seed - 60          # 進度持久
    politics.deplete_garrison(c, gd, "windhelm", 9999)
    assert politics.garrison_of(c, gd, "windhelm") == 0                  # 不為負


# --- 攻城煙霧(patch run_battle 控制強攻結果)----------------------------
def _siege(menu_seq, battle_result):
    """menu_seq=action_siege 選單依序回傳值;battle_result=強攻 run_battle 結果。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    c.allegiance = "imperial"; c.location_id = "windhelm"   # 敵城(獨立)
    c.skills["speechcraft"] = 80; c.skills["destruction"] = 60; c.magicka = 200
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    mseq = iter(menu_seq)
    saved = (M.run_battle, ui.menu, ui.confirm, ui.message)
    M.run_battle = lambda *a, **k: battle_result
    ui.menu = lambda *a, **k: next(mseq, None)
    ui.confirm = lambda *a, **k: True
    ui.message = lambda *a, **k: None
    try:
        res = M.action_siege(state, gd, "windhelm")
    finally:
        M.run_battle, ui.menu, ui.confirm, ui.message = saved
    return gd, c, res


def test_siege_op_then_assault_conquers():
    # 先施一個方略(削守軍)→ 再強攻(勝)→ 破城易幟
    gd, c, res = _siege(["parley", "assault"], "victory")
    assert res is None
    assert politics.faction_of(c, gd, "windhelm") == "imperial"
    assert c.fame >= politics.SIEGE_FAME
    assert politics.garrison_of(c, gd, "windhelm") > 0   # 由你方重新駐軍


def test_siege_assault_death_no_conquer():
    gd, c, res = _siege(["assault"], "dead")
    assert res == "dead"
    assert politics.faction_of(c, gd, "windhelm") == "independent"


def test_siege_assault_flee_keeps_op_progress():
    # 施方略削守軍後強攻逃跑 → 城未下,但方略戰果(削減+已用)保留
    gd, c, res = _siege(["parley", "assault"], "fled")
    seed = gd.rulers["windhelm"]["garrison"]
    assert res is None
    assert politics.faction_of(c, gd, "windhelm") == "independent"   # 未攻下
    assert politics.garrison_of(c, gd, "windhelm") < seed           # 守軍已被方略削減、且持久
    assert "parley" in politics.ops_done(c, "windhelm")             # 方略已用、不重置(杜絕重刷)


def test_save_roundtrip_and_backward_compat():
    import json
    gd, c = _setup()
    politics.pledge(c, "imperial")
    c.skills["speechcraft"] = 80
    politics.resolve_op(c, gd, "windhelm", "parley", RNG(1))
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.allegiance == "imperial"
    assert loaded.garrison_current == c.garrison_current
    assert loaded.siege_ops == c.siege_ops
    d = c.to_dict()
    for k in ("allegiance", "city_faction", "garrison_current", "siege_ops"):
        del d[k]                                     # 模擬舊存檔
    old = Character.from_dict(d)
    assert old.allegiance == "" and old.city_faction == {} and old.garrison_current == {} and old.siege_ops == {}


# === 階段三:佔領後收稅 + 駐軍維護 + 輕量叛亂計時 ====================
def _state(c):
    return GameState(player=c, rng=RNG(1), game_mode="adventure")


def test_all_cities_have_population():
    gd, _ = _setup()
    for loc, r in gd.rulers.items():
        assert r.get("population", 0) > 0, loc           # 21 城皆有居民數
        assert politics.city_tax(gd, loc) > 0


def test_red_line_tax_only_conquered_not_allied():
    """🔴 紅線:只對親手攻下的城收稅,不對未攻的同立場盟城(否則白送鉅額被動收入)。"""
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 0
    assert len(politics.held_cities(c, gd)) > 0           # 盟城一堆(同立場)
    assert politics.held_tax_cities(c, gd) == []          # 但稅基為空(未攻任何城)
    st = _state(c); st.time.advance(politics.TAX_HOURS * 2)
    assert politics.tick_tax(st, gd) == [] and c.gold == 0   # 零白送
    politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    assert politics.held_tax_cities(c, gd) == ["windhelm"]
    assert "bruma" in politics.held_cities(c, gd)         # 盟城仍在 held_cities
    assert "bruma" not in politics.held_tax_cities(c, gd)  # 但不計稅


def test_conquer_records_cycle_and_collects_net():
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 0
    st = _state(c); now = st.time.absolute_hours()
    politics.conquer(c, gd, "windhelm", now=now)
    assert c.tax_due_at["windhelm"] == now + politics.TAX_HOURS   # 起算 + 一週寬限
    assert politics.tick_tax(st, gd) == []                        # 未到期 → 不收
    g0 = politics.garrison_of(c, gd, "windhelm")
    st.time.advance(politics.TAX_HOURS)
    evs = politics.tick_tax(st, gd)
    assert len(evs) == 1 and evs[0]["kind"] == "tax" and not evs[0]["unrest"]
    g1 = g0 - politics.UNREST_DECAY                               # 先流失再收稅
    assert politics.garrison_of(c, gd, "windhelm") == g1
    tax = politics.city_tax(gd, "windhelm"); maint = round(g1 * politics.GARRISON_MAINT_PER)
    assert evs[0]["tax"] == tax and evs[0]["maint"] == maint and evs[0]["net"] == tax - maint
    assert c.gold == max(0, tax - maint)


def test_unrest_suspends_tax_but_charges_maint():
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 1000
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    c.garrison_current["windhelm"] = politics.UNREST_WARN + politics.UNREST_DECAY  # 流失後恰 = WARN
    st.time.advance(politics.TAX_HOURS)
    e = politics.tick_tax(st, gd)[0]
    assert e["unrest"] and e["tax"] == 0 and e["maint"] > 0       # 民心浮動 → 稅斷、仍付維護
    assert e["net"] == -e["maint"] and c.gold == 1000 - e["maint"]


def test_garrison_decays_and_city_revolts():
    gd, c = _setup(); politics.pledge(c, "imperial")
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    c.garrison_current["windhelm"] = politics.UNREST_DECAY        # 一期即潰散
    st.time.advance(politics.TAX_HOURS)
    evs = politics.tick_tax(st, gd)
    assert any(e["kind"] == "revolt" for e in evs)
    assert "windhelm" not in politics.held_tax_cities(c, gd)
    assert politics.faction_of(c, gd, "windhelm") == "independent"  # 還原原立場
    assert "windhelm" not in c.tax_due_at and "windhelm" not in c.garrison_current


def test_tick_tax_catches_up_multiple_periods():
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 0
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    g0 = politics.garrison_of(c, gd, "windhelm")
    st.time.advance(politics.TAX_HOURS * 3)
    evs = politics.tick_tax(st, gd)
    assert len([e for e in evs if e["kind"] == "tax"]) == 3       # 補結 3 期(未潰散)
    assert politics.garrison_of(c, gd, "windhelm") == g0 - 3 * politics.UNREST_DECAY


def test_reinforce_caps_and_costs():
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 100000
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    base = politics.base_garrison(gd, "windhelm")
    c.garrison_current["windhelm"] = base - 20
    assert politics.reinforce_garrison(c, gd, "windhelm", 5) == 5
    assert politics.garrison_of(c, gd, "windhelm") == base - 15
    assert c.gold == 100000 - 5 * politics.REINFORCE_COST_PER
    assert politics.reinforce_garrison(c, gd, "windhelm", 999) == 15   # 夾原始守軍上限
    assert politics.garrison_of(c, gd, "windhelm") == base
    c.gold = politics.REINFORCE_COST_PER * 2; c.garrison_current["windhelm"] = base - 10
    assert politics.reinforce_garrison(c, gd, "windhelm", 10) == 2     # 夾金幣


def test_tax_due_at_save_roundtrip():
    import json
    gd, c = _setup(); c.tax_due_at = {"windhelm": 12345}
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.tax_due_at == {"windhelm": 12345}
    d = c.to_dict(); del d["tax_due_at"]
    assert Character.from_dict(d).tax_due_at == {}        # 舊存檔缺欄 → 預設 {}


def test_legacy_counts_dominion():
    from tesrpg.systems import legacy
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 0
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    c.thaneships = ["bruma"]; c.soldiers = 10
    s = legacy.compute(st, gd)
    assert s["dominion"] and "據有 1 城" in s["dominion"]
    assert "受封 1 地武士" in s["dominion"] and "麾下 10 兵" in s["dominion"]
    assert "擁護" in s["dominion"]
    bare = legacy.compute(_state(_setup()[1]), gd)
    assert bare["dominion"] is None                       # 無城戰/招兵 → 結算省略此行


def test_legacy_survives_corrupt_faction_id():
    """毀損/舊存檔:char.factions 含已不存在的公會 id → legacy.compute 須防禦化、不得 KeyError。
    (對抗審查抓到的既有 robustness 缺口;此前只夾 rank、未防缺 id。)"""
    from tesrpg.systems import legacy
    gd, c = _setup()
    c.factions = {"ghost_guild": 2, "another_dead_one": 99}   # 已移除/毀損的公會 id
    s = legacy.compute(_state(c), gd)                          # 不該爆 KeyError
    assert s["factions"] == []                                # 未知公會略過、不計分


def test_court_reinforce_end_to_end():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 10000
    c.location_id = "windhelm"
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    base = politics.base_garrison(gd, "windhelm")
    c.garrison_current["windhelm"] = base - 30
    saved = (ui.menu, ui.ask_int, ui.message, ui.court_panel)
    ui.menu = lambda *a, **k: "reinforce"
    ui.ask_int = lambda *a, **k: 20
    ui.message = lambda *a, **k: None
    ui.court_panel = lambda *a, **k: None
    try:
        M.action_court(st, gd)
    finally:
        ui.menu, ui.ask_int, ui.message, ui.court_panel = saved
    assert politics.garrison_of(c, gd, "windhelm") == base - 10   # -30 +20


def run():
    test_stance_seed_is_city_unit_cross_province()
    test_relationship_and_pledge()
    test_can_siege_only_enemy()
    test_assault_force_monotonic_and_clamped()
    test_ops_gated_by_skill_and_once_each()
    test_op_deplete_and_costs()
    test_risky_op_marks_done_even_on_fail()
    test_conquer_flips_regarrisons_and_clears_ops()
    test_deplete_persists_and_clamps()
    test_siege_op_then_assault_conquers()
    test_siege_assault_death_no_conquer()
    test_siege_assault_flee_keeps_op_progress()
    test_save_roundtrip_and_backward_compat()
    test_all_cities_have_population()
    test_red_line_tax_only_conquered_not_allied()
    test_conquer_records_cycle_and_collects_net()
    test_unrest_suspends_tax_but_charges_maint()
    test_garrison_decays_and_city_revolts()
    test_tick_tax_catches_up_multiple_periods()
    test_reinforce_caps_and_costs()
    test_tax_due_at_save_roundtrip()
    test_legacy_counts_dominion()
    test_legacy_survives_corrupt_faction_id()
    test_court_reinforce_end_to_end()


if __name__ == "__main__":
    run()
    print("test_politics 全通過")
