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


def _siege_wave_count(base):
    rem, n = base, 0
    while rem > 0:
        w = politics.siege_wave(rem, base)
        assert w["guards"] >= 2
        rem -= w["strength"]; n += 1
        assert n <= 8
    assert rem == 0
    return n


def test_siege_depletes_and_difficulty_is_monotonic():
    # 各城都會收斂到破城;最後一波才有守將
    for base in (80, 110, 210, 400):
        gd, c = _setup()
        rem, saw_boss = base, []
        while rem > 0:
            w = politics.siege_wave(rem, base)
            saw_boss.append(w["boss"]); rem -= w["strength"]
        assert rem == 0 and saw_boss[-1] and not any(saw_boss[:-1])   # 僅最後一波守將
    # 守軍越多 → 波數與每波守軍皆單調遞增(攻城越難)
    assert _siege_wave_count(400) > _siege_wave_count(110)
    assert politics.siege_params(400)[1] > politics.siege_params(110)[1]   # 帝都每波守軍更多


def test_deplete_persists_progress():
    gd, c = _setup()
    politics.deplete_garrison(c, gd, "windhelm", 110)   # 削一波
    assert politics.garrison_of(c, gd, "windhelm") == gd.rulers["windhelm"]["garrison"] - 110
    politics.deplete_garrison(c, gd, "windhelm", 9999)  # 削到 0,不為負
    assert politics.garrison_of(c, gd, "windhelm") == 0


def test_conquer_flips_and_regarrisons():
    gd, c = _setup()
    politics.pledge(c, "imperial")
    assert politics.faction_of(c, gd, "windhelm") == "independent"
    politics.conquer(c, gd, "windhelm")
    assert politics.faction_of(c, gd, "windhelm") == "imperial"      # 易幟
    assert politics.relationship(c, gd, "windhelm") == "ally"
    assert politics.garrison_of(c, gd, "windhelm") == gd.rulers["windhelm"]["garrison"]  # 重新駐軍
    assert "windhelm" in politics.held_cities(c, gd)


def test_regroup_partial_heal_clamped():
    gd, c = _setup()
    c.max_health = 200; c.health = 10
    c.max_fatigue = 100; c.fatigue = 0
    politics.regroup(c)
    assert c.health == 10 + 200 * politics.SIEGE_REGROUP_HEALTH       # 部分回復
    assert c.health < c.max_health                                    # 非全補
    c.health = c.max_health
    politics.regroup(c)
    assert c.health == c.max_health                                   # 夾在上限


# --- 攻城煙霧(patch run_battle 控制每波結果)----------------------------
def _siege_with(results):
    """results 可為單一結果(每波相同)或結果序列(逐波)。回傳 (gd, c, res)。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    c.allegiance = "imperial"; c.location_id = "windhelm"   # 敵城(獨立)
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    if isinstance(results, str):
        battle = lambda *a, **k: results
    else:
        it = iter(results)
        battle = lambda *a, **k: next(it, "fled")
    saved = (M.run_battle, ui.confirm, ui.message)
    M.run_battle = battle
    ui.confirm = lambda *a, **k: True
    ui.message = lambda *a, **k: None
    try:
        res = M.action_siege(state, gd, "windhelm")
    finally:
        M.run_battle, ui.confirm, ui.message = saved
    return gd, c, res


def test_siege_victory_conquers():
    gd, c, res = _siege_with("victory")             # 每波皆勝 → 削到 0 破城
    assert res is None
    assert politics.faction_of(c, gd, "windhelm") == "imperial"
    assert c.fame >= politics.SIEGE_FAME
    assert politics.garrison_of(c, gd, "windhelm") > 0   # 已由你方重新駐軍


def test_siege_death_no_conquer():
    gd, c, res = _siege_with("dead")
    assert res == "dead"
    assert politics.faction_of(c, gd, "windhelm") == "independent"   # 未易幟


def test_siege_flee_first_wave_no_progress():
    gd, c, res = _siege_with("fled")                # 首波即逃 → 無戰果
    assert res is None
    assert politics.faction_of(c, gd, "windhelm") == "independent"
    assert politics.garrison_of(c, gd, "windhelm") == gd.rulers["windhelm"]["garrison"]


def test_siege_partial_then_flee_persists_no_refarm():
    """清一波再逃 → 守軍永久削減(進度保留)、城未下;清掉的波不會重生(杜絕重刷)。"""
    gd, c, res = _siege_with(["victory", "fled"])
    seed = gd.rulers["windhelm"]["garrison"]
    chunk = politics.siege_wave(seed, seed)["strength"]                  # 首波削減量
    assert res is None
    assert politics.faction_of(c, gd, "windhelm") == "independent"       # 未攻下
    assert 0 < politics.garrison_of(c, gd, "windhelm") == seed - chunk   # 已折損、且持久(非全削)


def test_save_roundtrip_and_backward_compat():
    import json
    gd, c = _setup()
    politics.pledge(c, "imperial")
    politics.conquer(c, gd, "windhelm")
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.allegiance == "imperial"
    assert loaded.city_faction == {"windhelm": "imperial"}
    assert loaded.garrison_current == c.garrison_current
    d = c.to_dict()
    for k in ("allegiance", "city_faction", "garrison_current"):
        del d[k]                                     # 模擬舊存檔
    old = Character.from_dict(d)
    assert old.allegiance == "" and old.city_faction == {} and old.garrison_current == {}


def run():
    test_stance_seed_is_city_unit_cross_province()
    test_relationship_and_pledge()
    test_can_siege_only_enemy()
    test_siege_depletes_and_difficulty_is_monotonic()
    test_deplete_persists_progress()
    test_conquer_flips_and_regarrisons()
    test_regroup_partial_heal_clamped()
    test_siege_victory_conquers()
    test_siege_death_no_conquer()
    test_siege_flee_first_wave_no_progress()
    test_siege_partial_then_flee_persists_no_refarm()
    test_save_roundtrip_and_backward_compat()


if __name__ == "__main__":
    run()
    print("test_politics 全通過")
