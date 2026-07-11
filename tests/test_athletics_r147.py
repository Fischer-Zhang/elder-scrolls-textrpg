"""R147 運動樹身份化:「調息」續戰(耗一回合換回體·自動解除姿態·主動招牌招式)。
🔴 核心紅線:調息自動解除格擋姿態/盾牆 → 恢復與持姿態互斥 → 防無限姿態(R137/R138 煞車天然守)。"""
import io
from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, mastery, stats
from tesrpg import formulas
import tesrpg.main as main

gd = get_gamedata()


def _char(**skills):
    c = build_character(gd, name="運", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(skills)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


# --- 回復量公式 + rest_bonus SUM ------------------------------------------
def test_rest_fatigue_amount_scales_with_athletics():
    assert formulas.rest_fatigue_amount(0) == formulas.REST_FATIGUE_BASE
    assert formulas.rest_fatigue_amount(100) > formulas.rest_fatigue_amount(0)   # 技能越高回越多


def test_rest_bonus_sum():
    c = _char(athletics=100)
    assert mastery.rest_bonus(c, gd) == 0                        # 未選 → 0
    mastery.choose(c, gd, "athletics_25", "steady_breath")
    mastery.choose(c, gd, "athletics_75", "deep_breath")
    mastery.choose(c, gd, "athletics_100", "tidal_breath")
    assert mastery.rest_bonus(c, gd) == 8 + 12 + 16             # 三節點相加(開源)


def test_rest_bonus_in_whitelist():
    assert "rest_bonus" in mastery._IMPLEMENTED_KINDS


# --- 🔴 調息自動解除姿態(防無限姿態)-------------------------------------
def test_rest_drops_stance_and_wall():
    """🔴 最重要紅線:調息(rest 動作)自動移除格擋姿態/盾牆 → 持姿態不能無限喘息。"""
    c = _char(athletics=100, block=100)
    c.fatigue = 20
    c.active_effects.append({"kind": "guard_stance", "turns": 99})
    c.active_effects.append({"kind": "shield_wall", "mitigation": 0.3, "turns": 99})
    assert combat.has_guard_stance(c) and combat.has_shield_wall(c)
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    foe = combat.spawn_creature(gd, "mudcrab", RNG(1)); foe.health = 9999
    # 直接驅 run_battle 的 rest 動作:patch 選單先 rest 再逃
    calls = {"n": 0}
    def _act(*a, **k):
        calls["n"] += 1
        return {"type": "rest"} if calls["n"] == 1 else {"type": "flee"}
    import tesrpg.main as m
    orig = m._choose_combat_action
    m._choose_combat_action = _act
    try:
        m.run_battle(st, gd, [foe])
    finally:
        m._choose_combat_action = orig
    assert not combat.has_guard_stance(c), "🔴 調息必須解除格擋姿態(防無限姿態)"
    assert not combat.has_shield_wall(c), "🔴 調息必須解除盾牆"
    assert c.fatigue > 20                                        # 回體了


def test_rest_recovers_but_not_over_max():
    c = _char(athletics=100)
    c.fatigue = c.max_fatigue - 5                                # 快滿
    st = GameState(player=c, rng=RNG(2), time=GameTime())
    foe = combat.spawn_creature(gd, "mudcrab", RNG(2)); foe.health = 9999
    calls = {"n": 0}
    def _act(*a, **k):
        calls["n"] += 1
        return {"type": "rest"} if calls["n"] == 1 else {"type": "flee"}
    import tesrpg.main as m
    orig = m._choose_combat_action
    m._choose_combat_action = _act
    try:
        m.run_battle(st, gd, [foe])
    finally:
        m._choose_combat_action = orig
    assert c.fatigue == c.max_fatigue                            # 夾 max·不溢出


# --- fatigue_cost_bonus SUM+cap(R35 防遮蔽)------------------------------
def test_fatigue_cost_bonus_sum_and_cap():
    c = _char(athletics=100)
    mastery.choose(c, gd, "athletics_50", "second_wind")        # 0.10
    mastery.choose(c, gd, "athletics_75", "sparing")            # 0.12
    mastery.choose(c, gd, "athletics_100", "frugal")            # 0.12
    total = mastery.fatigue_cost_bonus(c, gd)
    assert abs(total - min(mastery.FATIGUE_COST_BONUS_CAP, 0.10 + 0.12 + 0.12)) < 1e-9   # 相加夾 cap
    # 單源 = 原值(byte-identical 保護)
    c2 = _char(athletics=75)
    mastery.choose(c2, gd, "athletics_50", "second_wind")
    assert abs(mastery.fatigue_cost_bonus(c2, gd) - 0.10) < 1e-9


# --- opt_id 退 pending(舊存檔遷移)---------------------------------------
def test_old_athletics_opts_retire_to_pending():
    from tesrpg.systems import progression
    c = _char(athletics=100)
    c.mastery_choices = {"athletics_25": "light_step", "athletics_75": "escape_artist",
                         "athletics_100": "windstep"}            # 舊 opt_id(已不存在)
    progression.ensure_mastery_choices(c, gd)                    # 通用防呆清陳舊
    assert "athletics_25" not in c.mastery_choices               # 退 pending·不崩
    assert "athletics_75" not in c.mastery_choices
    assert "athletics_100" not in c.mastery_choices


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
