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


def test_relationship_and_pledge():
    gd, c = _setup()
    assert politics.relationship(c, gd, "windhelm") == "unaligned"   # 未選邊
    assert not politics.can_siege(c, gd, "windhelm")                 # 未選邊不可攻(併自 can_siege_only_enemy)
    politics.pledge(c, "imperial")
    assert c.allegiance == "imperial"
    assert politics.relationship(c, gd, "bruma") == "ally"           # 同為帝國
    assert politics.relationship(c, gd, "windhelm") == "enemy"       # 獨立 → 敵
    assert politics.relationship(c, gd, "whiterun") == "neutral"     # 中立
    # can_siege 即 relationship=='enemy' 一行(併自 can_siege_only_enemy)
    assert politics.can_siege(c, gd, "windhelm")         # 敵城可攻
    assert not politics.can_siege(c, gd, "bruma")        # 盟城不可攻
    assert not politics.can_siege(c, gd, "whiterun")     # 中立不可攻
    # 立場種子是城為單位、跨省混合(併自 stance_seed_is_city_unit_cross_province)
    # haafingar 種子與 bruma 同為 imperial,已由上方 bruma→ally 守同立場;windhelm/whiterun
    # 種子已由上方 relationship 隱含覆蓋。唯一邊界:無領主地點 → base_stance 回 None
    assert politics.base_stance(gd, next(lid for lid in gd.world["locations"]
                                        if not gd.ruler_at(lid))) is None
    # independent 視角的對稱回歸(併自 two_cause_relationship_unchanged);pledge 可重複覆寫
    politics.pledge(c, "independent")
    assert politics.relationship(c, gd, "windhelm") == "ally"      # 同獨立
    assert politics.relationship(c, gd, "bruma") == "enemy"        # 帝國城
    assert politics.relationship(c, gd, "whiterun") == "neutral"   # 中立仍觀望
    assert not politics.can_siege(c, gd, "whiterun")


# --- 圍城方略(operations:全套技能各有攻城用途)------------------------
def test_assault_waves_scale_with_garrison():
    assert politics.assault_waves(40) == 1                            # 殘存少 → 一波(守將決戰)
    assert politics.assault_waves(250) > politics.assault_waves(50)   # 守軍越多 → 波數越多(削弱兌現在波數)
    assert politics.assault_waves(0) == 1                             # 至少一波
    assert politics.assault_waves(politics.WAVE_GARRISON) == 1        # 邊界:恰一波當量


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
    # 直接 deplete_garrison 路徑 + 夾 0 不為負(併自 deplete_persists_and_clamps)
    politics.deplete_garrison(c, gd, "windhelm", 9999)
    assert politics.garrison_of(c, gd, "windhelm") == 0


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
    # 強攻陣亡 → 不易幟、立場不變(併自 siege_assault_death_no_conquer)
    gd2, c2, res2 = _siege(["assault"], "dead")
    assert res2 == "dead"
    assert politics.faction_of(c2, gd2, "windhelm") == "independent"


def test_siege_assault_flee_keeps_op_progress():
    # 施方略削守軍後強攻逃跑 → 城未下,但方略戰果(削減+已用)保留
    gd, c, res = _siege(["parley", "assault"], "fled")
    seed = gd.rulers["windhelm"]["garrison"]
    assert res is None
    assert politics.faction_of(c, gd, "windhelm") == "independent"   # 未攻下
    assert politics.garrison_of(c, gd, "windhelm") < seed           # 守軍已被方略削減、且持久
    assert "parley" in politics.ops_done(c, "windhelm")             # 方略已用、不重置(杜絕重刷)


def test_siege_assault_runs_multiple_waves():
    """β:守軍多 → 連打多波(run_battle 次數=波數);全勝才破城。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    c.allegiance = "imperial"; c.location_id = "windhelm"
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    waves = politics.assault_waves(politics.garrison_of(c, gd, "windhelm"))
    assert waves >= 3                                   # windhelm 守軍夠多 → 多波
    calls = {"n": 0}

    def battle(*a, **k):
        calls["n"] += 1
        return "victory"
    saved = (M.run_battle, ui.menu, ui.confirm, ui.message)
    M.run_battle = battle
    ui.menu = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True                   # 確認總攻 + 每波續戰
    ui.message = lambda *a, **k: None
    try:
        res = M._siege_assault(state, gd, "windhelm", "風盔城")
    finally:
        M.run_battle, ui.menu, ui.confirm, ui.message = saved
    assert calls["n"] == waves                          # 每波一場群戰
    assert res is None and politics.faction_of(c, gd, "windhelm") == "imperial"   # 全勝破城


def test_siege_assault_retreat_keeps_wave_depletion():
    """β:中途鳴金收兵 → 已破波次的守軍折損持久(改日波數更少),城未下。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    c.allegiance = "imperial"; c.location_id = "windhelm"
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    seed = politics.garrison_of(c, gd, "windhelm")
    confirms = iter([True, False])                      # 確認總攻 → 第一波後鳴金收兵
    saved = (M.run_battle, ui.menu, ui.confirm, ui.message)
    M.run_battle = lambda *a, **k: "victory"
    ui.menu = lambda *a, **k: None
    ui.confirm = lambda *a, **k: next(confirms, False)
    ui.message = lambda *a, **k: None
    try:
        res = M._siege_assault(state, gd, "windhelm", "風盔城")
    finally:
        M.run_battle, ui.menu, ui.confirm, ui.message = saved
    assert res is None
    assert politics.faction_of(c, gd, "windhelm") == "independent"          # 未攻下
    assert politics.garrison_of(c, gd, "windhelm") == seed - politics.WAVE_GARRISON   # 破一波 → 永久折損


def test_save_roundtrip_and_backward_compat():
    import json
    gd, c = _setup()
    politics.pledge(c, "imperial")
    c.skills["speechcraft"] = 80
    politics.resolve_op(c, gd, "windhelm", "parley", RNG(1))
    c.tax_due_at = {"windhelm": 12345}               # 併自 tax_due_at_save_roundtrip
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.allegiance == "imperial"
    assert loaded.garrison_current == c.garrison_current
    assert loaded.siege_ops == c.siege_ops
    assert loaded.tax_due_at == {"windhelm": 12345}
    d = c.to_dict()
    for k in ("allegiance", "city_faction", "garrison_current", "siege_ops", "tax_due_at"):
        del d[k]                                     # 模擬舊存檔
    old = Character.from_dict(d)
    assert old.allegiance == "" and old.city_faction == {} and old.garrison_current == {} and old.siege_ops == {}
    assert old.tax_due_at == {}                       # 舊存檔缺 tax_due_at → 預設 {}


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
    # 領地總覽(併自 territory_overview_helper):剛攻下、未到期、駐軍未變時
    ov = politics.territory_overview(c, gd, "windhelm", now)
    assert ov["loc"] == "windhelm" and ov["countdown"] == politics.TAX_HOURS   # 距下次徵稅
    assert ov["population"] == gd.rulers["windhelm"]["population"]
    assert ov["base"] == gd.rulers["windhelm"]["garrison"] and not ov["unrest"]
    assert ov["net"] == ov["tax"] - ov["maint"]
    assert politics.tick_tax(st, gd) == []                        # 未到期 → 不收
    g0 = politics.garrison_of(c, gd, "windhelm")
    st.time.advance(politics.TAX_HOURS)
    evs = politics.tick_tax(st, gd)
    assert len(evs) == 1 and evs[0]["kind"] == "tax" and not evs[0]["unrest"]
    g_decay = g0 - politics.UNREST_DECAY                          # 先流失
    g_after = min(politics.base_garrison(gd, "windhelm"),         # 安定 → 階段四自動回補
                  g_decay + politics.GARRISON_REGEN_PER)
    assert politics.garrison_of(c, gd, "windhelm") == g_after and evs[0]["garrison"] == g_after
    tax = politics.city_tax(gd, "windhelm")
    maint = round(g_decay * politics.GARRISON_MAINT_PER)          # 維護以「回補前」駐軍計
    assert evs[0]["tax"] == tax and evs[0]["maint"] == maint and evs[0]["net"] == tax - maint
    assert c.gold == max(0, tax - maint)
    # 無紀錄(刪欄)→ countdown None(併自 territory_overview_helper 邊界)
    del c.tax_due_at["windhelm"]
    assert politics.territory_overview(c, gd, "windhelm", now)["countdown"] is None


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
    # 安定城每期淨 −(流失−回補)= −4(階段四自動重建後)
    assert politics.garrison_of(c, gd, "windhelm") == g0 - 3 * (politics.UNREST_DECAY - politics.GARRISON_REGEN_PER)


# === 階段四:駐軍自動緩慢重建 ===
def test_garrison_regen_on_stable_city():
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 0
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    c.garrison_current["windhelm"] = 200          # 遠高於 UNREST_WARN → 安定
    st.time.advance(politics.TAX_HOURS)
    e = politics.tick_tax(st, gd)[0]
    assert not e["unrest"]
    assert politics.garrison_of(c, gd, "windhelm") == 200 - politics.UNREST_DECAY + politics.GARRISON_REGEN_PER  # 淨 −4
    assert politics.garrison_of(c, gd, "windhelm") <= politics.base_garrison(gd, "windhelm")        # 永不超 base


def test_steward_relieves_unrest_and_stabilizes():
    """A3 冊封總管:減叛亂流失,令安定城自給(decay 4 < regen 6 → 淨 +2,守軍回升至 base)。"""
    gd, c = _setup(); politics.pledge(c, "imperial")
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    c.companions = ["sellsword"]
    assert politics.effective_unrest_decay(c, "windhelm") == politics.UNREST_DECAY     # 未冊封 → 全額流失
    politics.appoint_steward(c, "windhelm", "sellsword")
    assert politics.has_steward(c, "windhelm")
    assert politics.effective_unrest_decay(c, "windhelm") == politics.UNREST_DECAY - politics.STEWARD_UNREST_RELIEF
    c.garrison_current["windhelm"] = 200          # 安定城
    st.time.advance(politics.TAX_HOURS)
    politics.tick_tax(st, gd)
    # 有總管:淨 = −(decay−relief)+regen = −4+6 = +2(回升);無總管同場景為 −4
    assert politics.garrison_of(c, gd, "windhelm") == 200 - politics.effective_unrest_decay(c, "windhelm") + politics.GARRISON_REGEN_PER


def test_steward_dead_companion_no_relief():
    """陣亡/不在列的親衛不殘留治理加成(has_steward 須驗仍在 companions)。"""
    gd, c = _setup(); politics.pledge(c, "imperial")
    c.companions = ["sellsword"]; politics.appoint_steward(c, "windhelm", "sellsword")
    c.companions = []                              # 親衛陣亡/離隊
    assert not politics.has_steward(c, "windhelm")
    assert politics.effective_unrest_decay(c, "windhelm") == politics.UNREST_DECAY


def test_current_banner_label_flips_on_conquest():
    """B1:征服後旗號 token 反映新歸屬(修補『立場翻、對話內容沒翻』)。"""
    gd, c = _setup(); politics.pledge(c, "independent")
    before = politics.current_banner_label(c, gd, "bruma")
    assert before == politics.city_bloc_label(gd, "bruma")          # 未攻 → 靜態原旗號
    politics.conquer(c, gd, "bruma", now=0)
    assert politics.current_banner_label(c, gd, "bruma") == politics.cause_name("independent")   # 攻下 → 你的大義
    assert before != politics.current_banner_label(c, gd, "bruma")


def test_court_shows_conqueror_as_ruler():
    """4a:佔領城朝堂顯示你(或冊封的總管)為領主、旗號為你的大義 —— 取代被推翻的舊領主。"""
    import tesrpg.main as M
    gd, c = _setup(); politics.pledge(c, "independent"); c.name = "征服者王"
    base = gd.ruler_at("bruma")
    politics.conquer(c, gd, "bruma", now=0)
    ruler, reception = M._governing_ruler(_state(c), gd, "bruma", base)
    assert ruler["name"] == "征服者王" and ruler["name"] != base["name"]            # 你即領主(非舊領主)
    assert ruler["bloc_label"] == politics.cause_name("independent")               # 旗號=你的大義
    c.companions = ["sellsword"]; politics.appoint_steward(c, "bruma", "sellsword")
    ruler2, _r = M._governing_ruler(_state(c), gd, "bruma", base)
    assert ruler2["title"] == "總管"                                               # 改由總管坐鎮顯示
    assert ruler2["name"] == gd.companions.get("sellsword", {}).get("name", "sellsword")


def test_regen_blocked_under_unrest():
    """關鍵不變式:民心浮動(駐軍 ≤ WARN)時不自動重建 → 叛亂計時零削弱。"""
    gd, c = _setup(); politics.pledge(c, "imperial")
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    c.garrison_current["windhelm"] = politics.UNREST_WARN + politics.UNREST_DECAY   # 流失後恰 = WARN
    st.time.advance(politics.TAX_HOURS)
    e = politics.tick_tax(st, gd)[0]
    assert e["unrest"]
    assert politics.garrison_of(c, gd, "windhelm") == politics.UNREST_WARN          # 停在 WARN,未 +regen
    # 被忽視的城進浮動帶後放任數週仍一路衰減到造反(併自 neglected_city_revolts_despite_regen)
    # 重設駐軍續用同一 conquer 場景;tax_due_at 已被上一期 tick 推進(上期未潰故未清),
    # advance*6 補結多期觸發 revolt
    c.garrison_current["windhelm"] = politics.UNREST_WARN + 5     # 一旦進浮動帶就不再重建
    st.time.advance(politics.TAX_HOURS * 6)                       # 放任數週
    evs = politics.tick_tax(st, gd)
    assert any(e["kind"] == "revolt" for e in evs)
    assert "windhelm" not in politics.held_tax_cities(c, gd)


def test_action_territory_lists_only_conquered_and_reinforces():
    """🔴 紅線 + 端到端:總覽只列攻下城(非盟城),且可遠程加強駐軍。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup(); politics.pledge(c, "imperial"); c.gold = 10000
    c.location_id = "bruma"                                   # 人在別處 → 證明遠程回防
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    base = politics.base_garrison(gd, "windhelm")
    c.garrison_current["windhelm"] = base - 30
    captured = {}
    saved = (ui.territory_panel, ui.menu, ui.ask_int, ui.message)
    ui.territory_panel = lambda rows, gamedata, gold: captured.update(rows=rows)
    mseq = iter(["windhelm", None])                          # 選 windhelm 加強 → 再返回
    ui.menu = lambda *a, **k: next(mseq, None)
    ui.ask_int = lambda *a, **k: 20
    ui.message = lambda *a, **k: None
    try:
        M.action_territory(st, gd)
    finally:
        ui.territory_panel, ui.menu, ui.ask_int, ui.message = saved
    locs = [r["loc"] for r in captured["rows"]]
    assert locs == ["windhelm"]                              # 只列攻下城,盟城(bruma 等)不列
    assert politics.garrison_of(c, gd, "windhelm") == base - 10   # 遠程加強 +20


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
    # 自立稱號階梯(併自 legacy_own_realm_title):純函式邊界 + own 持 3 城的霸主階
    assert legacy.own_realm_title(1) == "割據一方的梟雄"
    assert legacy.own_realm_title(10) == "再造一統的新王"
    c2 = _setup()[1]; politics.pledge(c2, "own"); st2 = _state(c2)
    for loc in ("windhelm", "riften", "markarth"):
        politics.conquer(c2, gd, loc, now=st2.time.absolute_hours())
    assert "裂土封疆的霸主" in legacy.compute(st2, gd)["dominion"]   # 持 3 own 城 → 霸主階


def test_legacy_survives_corrupt_faction_id():
    """毀損/舊存檔:char.factions 含已不存在的公會 id → legacy.compute 須防禦化、不得 KeyError。
    (對抗審查抓到的既有 robustness 缺口;此前只夾 rank、未防缺 id。)"""
    from tesrpg.systems import legacy
    gd, c = _setup()
    c.factions = {"ghost_guild": 2, "another_dead_one": 99}   # 已移除/毀損的公會 id
    s = legacy.compute(_state(c), gd)                          # 不該爆 KeyError
    assert s["factions"] == []                                # 未知公會略過、不計分


# === 陣營階段 B:四大義 + 中立可攻 + 自立 ===
def test_expansionist_causes_attack_neutral():
    gd, c = _setup()
    politics.pledge(c, "imperial")
    assert politics.relationship(c, gd, "whiterun") == "neutral"   # 帝國對中立=觀望(回歸,不變)
    assert not politics.can_siege(c, gd, "whiterun")
    politics.pledge(c, "own")
    assert politics.relationship(c, gd, "whiterun") == "enemy"     # 自立視中立為可吞
    assert politics.can_siege(c, gd, "whiterun")
    assert politics.relationship(c, gd, "bruma") == "enemy"        # 自立對帝國城亦=敵


def test_own_conquer_taxes_red_line():
    gd, c = _setup(); politics.pledge(c, "own")
    st = _state(c); politics.conquer(c, gd, "windhelm", now=st.time.absolute_hours())
    assert c.city_faction["windhelm"] == "own" and politics.faction_of(c, gd, "windhelm") == "own"
    assert "windhelm" in politics.held_tax_cities(c, gd)          # 自立的城可收稅(只認 city_faction)


def test_world_fields_save_roundtrip():
    import json
    gd, c = _setup()
    c.world_faction = {"kvatch": "independent"}; c.world_events_fired = ["kvatch_falls"]
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.world_faction == {"kvatch": "independent"} and loaded.world_events_fired == ["kvatch_falls"]
    d = c.to_dict(); del d["world_faction"]; del d["world_events_fired"]
    old = Character.from_dict(d)
    assert old.world_faction == {} and old.world_events_fired == []   # 舊存檔缺欄 → 預設


def test_pledge_menu_four_choice_smoke():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    captured = {}
    saved = (ui.menu, ui.message)
    def fake_menu(title, opts, **k):
        captured["opts"] = [o[0] for o in opts]
        return "own"
    ui.menu = fake_menu
    ui.message = lambda *a, **k: None
    try:
        M._pledge_allegiance(GameState(player=c, rng=RNG(1), game_mode="adventure"), gd)
    finally:
        ui.menu, ui.message = saved
    assert captured["opts"] == ["imperial", "independent", "own"]   # 三大義(daedric 已非政治大義)
    assert c.allegiance == "own"


def test_daedric_not_a_pledgeable_cause():
    """神話黎明=末世密教,已自政治大義體系移除:不在 CAUSES/EXPANSIONIST、永不可宣誓(危機前後皆然)。"""
    gd, c = _setup()
    assert "daedric" not in politics.CAUSES
    assert "daedric" not in politics.EXPANSIONIST_CAUSES
    assert "daedric" not in politics.pledgeable_causes(c)
    c.world_events_fired.append("kvatch_falls")
    assert "daedric" not in politics.pledgeable_causes(c)
    assert set(politics.pledgeable_causes(c)) == {"imperial", "independent", "own"}


def run():
    test_relationship_and_pledge()
    test_assault_waves_scale_with_garrison()
    test_ops_gated_by_skill_and_once_each()
    test_op_deplete_and_costs()
    test_risky_op_marks_done_even_on_fail()
    test_conquer_flips_regarrisons_and_clears_ops()
    test_siege_op_then_assault_conquers()
    test_siege_assault_flee_keeps_op_progress()
    test_siege_assault_runs_multiple_waves()
    test_siege_assault_retreat_keeps_wave_depletion()
    test_save_roundtrip_and_backward_compat()
    test_steward_relieves_unrest_and_stabilizes()
    test_steward_dead_companion_no_relief()
    test_current_banner_label_flips_on_conquest()
    test_court_shows_conqueror_as_ruler()
    test_all_cities_have_population()
    test_red_line_tax_only_conquered_not_allied()
    test_conquer_records_cycle_and_collects_net()
    test_unrest_suspends_tax_but_charges_maint()
    test_garrison_decays_and_city_revolts()
    test_tick_tax_catches_up_multiple_periods()
    test_garrison_regen_on_stable_city()
    test_regen_blocked_under_unrest()
    test_action_territory_lists_only_conquered_and_reinforces()
    test_reinforce_caps_and_costs()
    test_legacy_counts_dominion()
    test_legacy_survives_corrupt_faction_id()
    test_expansionist_causes_attack_neutral()
    test_own_conquer_taxes_red_line()
    test_world_fields_save_roundtrip()
    test_pledge_menu_four_choice_smoke()
    test_daedric_not_a_pledgeable_cause()


if __name__ == "__main__":
    run()
    print("test_politics 全通過")
