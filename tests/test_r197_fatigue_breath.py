"""R197 子提交 (b):體力懲罰標示 + 二次呼吸「可用 / 已用」(戰鬥卡片標籤)。

🔴 核心紅線:
  ① `formulas.hit_chance` 抽出 FATIGUE_HIT_PENALTY / fatigue_hit_penalty 後**逐位元組同舊**
     (對「舊寫死 0.25」的重寫公式在大格點上全等 → sim 不受影響)。
  ② 標籤數字 = 真正會用的式子(預覽 = 實擲):命中 = 下一次普通攻擊 —— main 先 player_attack_cost 扣體力、
     再 resolve_attack 擲命中,所以用「出招後」的體力比例;法效 = 出招前的體力比例(magic.cast 的 fatigue_before)。
  ③ 二次呼吸標籤與 second_breath_ready 共用本場已用記帳(second_breath_spent);未選 → 不顯示。
  ④ 只給玩家本人:敵方 / 同伴卡片不帶此類標籤;不受影響的構築(滿體力、未選里程碑)標籤逐位元組同舊。
"""
import copy
import re

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, mastery, stats
import tesrpg.ui.console as ui

gd = get_gamedata()


def _char(breath=False):
    c = build_character(gd, name="運", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    if breath:
        c.skills["athletics"] = 100
        mastery.choose(c, gd, "athletics_100", "tidal_breath")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 5000
    c.fatigue = c.max_fatigue
    return c


def _foe(name="wolf"):
    return combat.spawn_creature(gd, name, RNG(1))


def _set_swing_ratio(c, ratio):
    """讓「出招後」的體力比例 = ratio(出招前 = ratio × max + 一擊耗量)。"""
    cost = combat.attack_fatigue_cost(c, gd)
    c.fatigue = ratio * c.max_fatigue + cost
    return cost


# --- ① 公式逐位元組同舊 ---------------------------------------------------
def _old_hit_chance(atk_skill, atk_agility, def_agility, fr, blocking=False, evasion=0.0,
                    block_penalty=formulas.BLOCK_HIT_PENALTY):
    """R197 前的 formulas.hit_chance(體力懲罰寫死 0.25)—— 原樣重寫,供逐位元組比對。"""
    chance = 0.50 + (atk_skill - 25) * 0.006
    chance += (atk_agility - def_agility) * 0.004
    chance -= (1.0 - max(0.0, min(1.0, fr))) * 0.25
    if blocking:
        chance -= block_penalty
    chance -= min(formulas.EVASION_TOTAL_CAP, evasion)
    return max(formulas.HIT_CHANCE_FLOOR, min(formulas.HIT_CHANCE_CEIL, chance))


def test_hit_chance_is_bytewise_identical_to_the_pre_r197_formula():
    n = 0
    for skill in (0, 25, 50, 75, 100):
        for d_agi in (-40, 0, 40):
            for fr in (-0.5, 0.0, 0.2, 0.37, 0.5, 0.8, 1.0, 1.5):
                for blocking in (False, True):
                    for evasion in (0.0, 0.1, 0.5):
                        new = formulas.hit_chance(skill, 40 + d_agi, 40, fr, blocking, evasion)
                        assert new == _old_hit_chance(skill, 40 + d_agi, 40, fr, blocking, evasion), (skill, d_agi, fr)
                        n += 1
    assert n == 5 * 3 * 8 * 2 * 3
    assert formulas.FATIGUE_HIT_PENALTY == 0.25                           # 值不變(改值 = 動戰鬥常數,須先問使用者 + 重跑 sim)


def test_penalty_functions_describe_the_real_formulas():
    base = formulas.hit_chance(50, 40, 40, 1.0)                           # 0.65:不碰上下夾
    for r in (0.0, 0.1, 0.25, 0.5, 0.73, 0.99, 1.0):
        assert abs((base - formulas.hit_chance(50, 40, 40, r)) - formulas.fatigue_hit_penalty(r)) < 1e-12, r
        assert abs(formulas.fatigue_power_penalty(r) - (1.0 - formulas.cast_fatigue_power_factor(r))) < 1e-12, r
    assert formulas.fatigue_hit_penalty(1.0) == 0.0 and formulas.fatigue_hit_penalty(0.0) == 0.25
    assert formulas.fatigue_hit_penalty(-3.0) == 0.25 and formulas.fatigue_hit_penalty(9.0) == 0.0      # 夾 [0,1]
    assert abs(formulas.fatigue_power_penalty(0.0) - formulas.CAST_FATIGUE_POWER_PENALTY) < 1e-12


# --- ② 標籤用的純讀 view:邊界 / 玩家限定 / 預覽 = 實擲 ----------------------
def test_fatigue_penalty_view_threshold_and_player_only():
    c = _char()
    assert combat.fatigue_penalty_view(c, gd) is None                      # 滿體力:出招後 ≈ −0.8 個百分點 < 5% → 不標
    _set_swing_ratio(c, 0.81)
    assert combat.fatigue_penalty_view(c, gd) is None                      # 命中折減 4.75% < 5% 門檻
    _set_swing_ratio(c, 0.79)
    v = combat.fatigue_penalty_view(c, gd)
    assert v is not None and v["exhausted"] is False and 0.05 <= v["hit"] < 0.06
    assert combat.fatigue_penalty_view(_foe(), gd) is None                 # 非玩家(敵人恆無體力懲罰)
    c.fatigue = 0
    v = combat.fatigue_penalty_view(c, gd)
    assert v["exhausted"] is True and v["hit"] == formulas.FATIGUE_HIT_PENALTY and abs(v["power"] - 0.25) < 1e-12
    c.max_fatigue = 0
    assert combat.fatigue_penalty_view(c, gd) is None                      # 無體力池 → 不標(防除以零)


def test_view_numbers_equal_what_the_real_flow_uses():
    c = _char()
    for ratio in (0.1, 0.4, 0.6, 0.79):
        _set_swing_ratio(c, ratio)
        v = combat.fatigue_penalty_view(c, gd)
        # 命中:實際流程 = 先 player_attack_cost 扣體力,再用 _fatigue_ratio 擲命中
        probe = copy.deepcopy(c)
        combat.player_attack_cost(probe, gd)
        assert v["hit"] == formulas.fatigue_hit_penalty(combat._fatigue_ratio(probe)), ratio
        # 法效:實際流程 = magic.cast 以「出招前」比例 fatigue_before / max_fatigue
        assert v["power"] == formulas.fatigue_power_penalty(c.fatigue / c.max_fatigue), ratio
    # 兩個數字確實取不同比例(出招前 vs 出招後):命中折減 ≥ 法效折減,且低體力時差異可見
    _set_swing_ratio(c, 0.3)
    v = combat.fatigue_penalty_view(c, gd)
    assert v["hit"] > v["power"]


# --- ③ 二次呼吸狀態 -------------------------------------------------------
def test_second_breath_status_follows_the_real_spent_marker():
    assert combat.second_breath_status(_char(breath=False), gd) is None   # 未選里程碑 → 不顯示
    assert combat.second_breath_status(_foe(), gd) is None                # 非玩家
    c = _char(breath=True)
    assert combat.second_breath_status(c, gd) == "available"               # 本場尚未動用(與目前體力無關)
    c.fatigue = 0.1 * c.max_fatigue                                        # ≤ 25%:觸發條件成立
    assert combat.second_breath_ready(c, gd) is True
    assert combat.second_breath_use(c, gd) > 0
    assert combat.second_breath_status(c, gd) == "spent" and combat.second_breath_ready(c, gd) is False
    c.active_effects.clear()                                               # 入戰 / 離戰整包清 → 下一場重新可用
    assert combat.second_breath_status(c, gd) == "available"


# --- ④ 戰鬥卡片 view-model ------------------------------------------------
def _view(player, enemies=None, allies=None, hud_gd=gd):
    saved = ui._hud_gamedata
    ui._hud_gamedata = hud_gd
    try:
        return ui._combat_view(player, allies or [], enemies or [_foe()])
    finally:
        ui._hud_gamedata = saved


def _fatigue_tags(tags):
    return [t for t in tags if t["s"].startswith(("體力不足", "力竭"))]


def test_combat_card_tags_fatigue_penalty_with_numbers_matching_the_view():
    c = _char()
    _set_swing_ratio(c, 0.6)
    v = combat.fatigue_penalty_view(c, gd)
    me = _view(c)["me"]
    [t] = _fatigue_tags(me["tags"])
    assert t["s"] == f"體力不足 命中−{ui.pct(v['hit'])}% 法效−{ui.pct(v['power'])}%"
    assert re.fullmatch(r"體力不足 命中−\d+% 法效−\d+%", t["s"])
    assert t["good"] is None                                               # 10% < 15%:中性色
    assert "個百分點" in t["tip"] and "出招後" in t["tip"] and "出招前" in t["tip"] and "閃避減半" not in t["tip"]
    _set_swing_ratio(c, 0.3)                                               # ≥ 15% → 紅
    [t] = _fatigue_tags(_view(c)["me"]["tags"])
    assert t["good"] is False and t["s"].startswith("體力不足")
    c.fatigue = 0                                                          # 力竭
    [t] = _fatigue_tags(_view(c)["me"]["tags"])
    assert t["s"] == "力竭 命中−25% 法效−25%" and t["good"] is False and "閃避減半" in t["tip"]


def test_combat_card_second_breath_tag_states():
    c = _char(breath=True)
    def breath_tags():
        return [t for t in _view(c)["me"]["tags"] if t["s"].startswith("二次呼吸")]
    [t] = breath_tags()
    assert t["s"] == "二次呼吸 可用" and t["good"] is True and "25%" in t["tip"]
    c.fatigue = 0.1 * c.max_fatigue
    combat.second_breath_use(c, gd)
    [t] = breath_tags()
    assert t["s"] == "二次呼吸 已用" and t["good"] is None
    # 沒有 gamedata(HUD 尚未接上)→ 不顯示二次呼吸、也不崩
    assert [t for t in _view(c, hud_gd=None)["me"]["tags"] if t["s"].startswith("二次呼吸")] == []


def test_tags_only_for_the_player_and_unaffected_builds_are_unchanged():
    c = _char(breath=True)
    c.fatigue = 0
    ally, foe = _foe("wolf"), _foe("bandit")
    view = _view(c, enemies=[foe], allies=[ally])
    assert not _fatigue_tags(view["allies"][0]["tags"]) and not _fatigue_tags(view["enemies"][0]["tags"])
    assert not [t for t in view["allies"][0]["tags"] + view["enemies"][0]["tags"] if t["s"].startswith("二次呼吸")]
    # 不受影響的構築(滿體力 + 未選里程碑):標籤與 R197 前逐位元組同(只有既有狀態標籤)
    plain = _char()
    assert _view(plain)["me"]["tags"] == ui._combatant(plain)["tags"]
    assert all(set(t) <= {"s", "good"} for t in _view(plain)["me"]["tags"])


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
