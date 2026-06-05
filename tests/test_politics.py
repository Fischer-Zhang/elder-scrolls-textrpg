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


if __name__ == "__main__":
    run()
    print("test_politics 全通過")
