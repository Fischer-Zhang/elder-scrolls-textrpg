"""R197 子提交 (b):體力懲罰標示 + 二次呼吸「可用 / 已用」(戰鬥卡片標籤)。

🔴 核心紅線:
  ① `formulas.hit_chance` 抽出 FATIGUE_HIT_PENALTY / fatigue_hit_penalty 後**逐位元組同舊**
     (對「舊寫死 0.25」的重寫公式在大格點上全等 → sim 不受影響)。
  ② 預覽 = 實擲:標籤的命中數字 = 下一次普通攻擊的**實際**命中損失 —— 用與 resolve_attack 共用的真實命中鏈
     (`combat._hit_chain`:含武器速度 / 里程碑命中 / 踉蹌·遲緩·凍麻 / 0.95 二次夾限);main 先 player_attack_cost 扣體力
     再 resolve_attack 擲命中 → 命中用「出招後」體力比例;法效 = 出招前比例(magic.cast 的 fatigue_before)。
     審查發現:公式層 −N% 會被 0.95 上限吸收(高階近戰 / 弓 / 徒手標籤紅字、實際幾乎無損)→ 改取實際損失;
     端到端守衛 = 以**真實 resolve_attack 的 rng.chance 引數**對帳預覽,跨多種構築。
  ③ 二次呼吸標籤與 second_breath_ready 共用本場已用記帳(second_breath_spent);未選 → 不顯示。
  ④ 只給玩家本人:敵方 / 同伴卡片不帶此類標籤;不受影響的構築(滿體力、未選里程碑)標籤逐位元組同舊;
     純近戰角色不被「法效−N%」洗版(只有會施法者才標法效)。
"""
import copy
import re

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, mastery, stats
import tesrpg.ui.console as ui

gd = get_gamedata()


def _char(breath=False, spells=False):
    c = build_character(gd, name="運", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    if breath:
        c.skills["athletics"] = 100
        mastery.choose(c, gd, "athletics_100", "tidal_breath")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 5000
    c.fatigue = c.max_fatigue
    c.spells = ["flames"] if spells else []
    return c


def _foe(name="wolf"):
    return combat.spawn_creature(gd, name, RNG(1))


def _set_swing_ratio(c, ratio):
    """讓「出招後」的體力比例 = ratio(出招前 = ratio × max + 一擊耗量)。"""
    cost = combat.attack_fatigue_cost(c, gd)
    c.fatigue = ratio * c.max_fatigue + cost
    return cost


class _RecRNG(RNG):
    """記錄所有 chance(p) 的 p;結果固定。"""

    def __init__(self, seed=0, result=True):
        super().__init__(seed)
        self.ps, self.result = [], result

    def chance(self, p):
        self.ps.append(p)
        return self.result


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


# --- ② 預覽 = 實擲(端到端:對真實 resolve_attack 的擲骰引數)-------------------
def _build(weapon="iron_sword", skills=None, agility=None, milestones=None, great_shield=None, spells=False):
    c = build_character(gd, name="運", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(skills or {})
    if agility:
        c.attributes["agility"] = agility
    if great_shield:
        inventory.add_item(c, great_shield, 1)
        assert inventory.equip_armor(c, gd, great_shield)
    else:
        inventory.add_item(c, weapon, 1)
        assert inventory.equip_weapon(c, gd, weapon)
    for node, opt in (milestones or {}).items():
        assert mastery.choose(c, gd, node, opt) is not False
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 5000
    c.spells = ["flames"] if spells else []
    return c


def _real_chance(c, enemy):
    """真實流程:先 player_attack_cost 扣體力,再 resolve_attack 擲命中 → 取第一個 rng.chance 的引數(= 實際命中率)。"""
    pc, ec = copy.deepcopy(c), copy.deepcopy(enemy)
    combat.player_attack_cost(pc, gd)
    rng = _RecRNG(result=False)
    combat.resolve_attack(pc, ec, gd, rng)
    return rng.ps[0]


_BUILDS = {
    "劍士(未飽和)": lambda: _build("iron_sword", {"blade": 40}),
    "劍士 100 + 敏捷 + 精準里程碑(飽和)": lambda: _build("steel_sword", {"blade": 100}, agility=95, milestones={"blade_100": "precision"}),
    "刺客匕首(快武器)": lambda: _build("iron_dagger", {"blade": 80}, agility=70),
    "弓手": lambda: _build("hunting_bow", {"marksman": 100}, agility=90),
    "重鈍器(慢武器)": lambda: _build("iron_warhammer", {"blunt": 60}),
    "武僧徒手": lambda: _build("fists", {"hand_to_hand": 100}, agility=85),
    "雙手重盾(盾擊·武器休眠)": lambda: _build(great_shield="iron_great_shield", skills={"block": 70}),
    "法師持杖": lambda: _build("flame_staff", {"destruction": 90}, spells=True),
}


def _status_variants(c):
    out = {"無狀態": c}
    for kind, eff in (("踉蹌", {"kind": "stagger", "turns": 2}), ("遲緩", {"kind": "slow", "turns": 2, "magnitude": 0.3}),
                      ("凍麻", {"kind": "benumb", "turns": 2, "magnitude": 0.2})):
        v = copy.deepcopy(c)
        v.active_effects.append(dict(eff))
        out[kind] = v
    beast = copy.deepcopy(c)
    beast.beast_form = True                                    # 獸形:獸爪戰鬥(略過裝備武器)
    out["獸形"] = beast
    bound = copy.deepcopy(c)
    bound.skills["conjuration"] = 60
    bound.active_effects.append({"kind": "bound_weapon", "turns": 5, "magnitude": 12})   # 束縛兵刃:取代裝備武器
    out["束縛兵刃"] = bound
    return out


def test_plain_attack_hit_preview_equals_the_chance_really_rolled():
    n, saturated, unsaturated = 0, 0, 0
    for label, make in _BUILDS.items():
        base = make()
        for status, c in _status_variants(base).items():
            for enemy_name in ("wolf", "bandit"):
                enemy = _foe(enemy_name)
                for ratio in (1.0, 0.8, 0.5, 0.25, 0.0):
                    cost = _set_swing_ratio(c, ratio)
                    swing = max(0.0, c.fatigue - cost) / c.max_fatigue
                    preview = combat.plain_attack_hit_chance(c, enemy, gd, swing)
                    real = _real_chance(c, enemy)
                    assert preview == real, (label, status, enemy_name, ratio, preview, real)   # 逐位元組:同一條鏈
                    n += 1
                full = combat.plain_attack_hit_chance(c, enemy, gd, 1.0)
                low = combat.plain_attack_hit_chance(c, enemy, gd, 0.3)
                saturated += (full - low) < 1e-9
                unsaturated += (full - low) > 0.05
    assert n == len(_BUILDS) * 6 * 2 * 5
    assert saturated >= 5 and unsaturated >= 30, (saturated, unsaturated)     # 兩類都真的出現,否則此測試空轉
    # 型態分支真的被走到(不是全落在一般武器路徑)
    sw = _BUILDS["雙手重盾(盾擊·武器休眠)"]()
    assert combat._swing_context(sw, gd)[2] is True
    assert combat._swing_context(_status_variants(_BUILDS["劍士(未飽和)"]())["獸形"], gd)[0] is True
    assert combat._swing_context(_status_variants(_BUILDS["劍士(未飽和)"]())["束縛兵刃"], gd)[1] is not None


def _old_inline_chain(attacker, defender, wpn_skill, speed, wmod, fr, blocking, evasion, block_pen, aimed, sneaking):
    """R197 前寫在 resolve_attack 內的最終命中鏈,原樣重寫(含運算順序)—— 供與共用的 _hit_chain 逐位元組比對。"""
    from tesrpg.systems import magic
    chance = formulas.hit_chance(wpn_skill, combat._agility(attacker), combat._agility(defender),
                                 fr, blocking, defender_evasion=evasion, block_penalty=block_pen)
    if combat._is_player(attacker):
        chance = max(0.05, min(0.95, chance + formulas.weapon_speed_hit(speed)))
    if wmod.get("hit"):
        chance = max(0.05, min(0.95, chance + wmod["hit"]))
    if aimed:
        chance = max(0.05, min(0.95, chance + formulas.AIMED_SHOT_HIT))
    if magic.is_staggered(attacker):
        chance = max(0.05, chance - formulas.STAGGER_HIT_PENALTY)
    if magic.is_slowed(attacker):
        chance = max(0.05, chance - formulas.slow_hit_penalty(magic.slow_factor(attacker)))
    if (benumb := magic.benumb_hit_penalty(attacker)):
        chance = max(0.05, chance - benumb)
    if sneaking:
        chance = max(chance, formulas.SNEAK_ATTACK_HIT_FLOOR)
    return chance


def test_hit_chain_is_bytewise_identical_to_the_pre_r197_inline_chain():
    n = 0
    for label, make in _BUILDS.items():
        for status, c in _status_variants(make()).items():
            beast, bound, great = combat._swing_context(c, gd)
            _d, wpn_skill, skill_id = combat._weapon_profile(c, gd, None)
            wmod = mastery.weapon_mod(c, gd, skill_id)
            speed = combat._swing_speed(combat._swing_wdef(c, gd, beast, bound, great))
            for enemy_name in ("wolf", "bandit"):
                enemy = _foe(enemy_name)
                for fr in (0.0, 0.3, 0.7, 1.0):
                    for blocking in (False, True):
                        for aimed in (False, True):
                            for sneaking in (False, True):
                                new = combat._hit_chain(c, enemy, wpn_skill, speed, wmod, fr, blocking, 0.1, 0.15, aimed, sneaking)
                                old = _old_inline_chain(c, enemy, wpn_skill, speed, wmod, fr, blocking, 0.1, 0.15, aimed, sneaking)
                                assert new == old, (label, status, enemy_name, fr, blocking, aimed, sneaking)
                                n += 1
    assert n == len(_BUILDS) * 6 * 2 * 4 * 2 * 2 * 2
    # 怪物當攻擊者(玩家防守端)也走同一條鏈:無武器速度 / 里程碑段
    foe, hero = _foe("bandit"), _BUILDS["劍士(未飽和)"]()
    for fr in (1.0, 0.5):
        assert combat._hit_chain(foe, hero, 40, 1.0, {}, fr, False, 0.2, 0.15) == _old_inline_chain(foe, hero, 40, 1.0, {}, fr, False, 0.2, 0.15, False, False)


def test_fatigue_view_hit_is_the_real_loss_not_the_nominal_formula():
    foe = _foe("bandit")
    # 飽和構築:命中本就頂著 0.95 → 公式上 −N% 但實際無損 → 非力竭時完全不出標籤(非施法者)
    sat = _BUILDS["劍士 100 + 敏捷 + 精準里程碑(飽和)"]()
    _set_swing_ratio(sat, 0.4)
    assert formulas.fatigue_hit_penalty(0.4) > 0.14                        # 名目折減確實很大…
    assert combat.fatigue_penalty_view(sat, gd, [foe]) is None             # …但實際無損 → 不亮警告
    assert combat.fatigue_penalty_view(sat, gd) is not None                # (無敵人 → 退回名目值;僅供 gamedata/敵人缺席時)
    # 力竭:仍要標(閃避減半、姿態暫停、盾牆落下),但不謊稱命中損失
    sat.fatigue = 0
    v = combat.fatigue_penalty_view(sat, gd, [foe])
    assert v["exhausted"] is True and v["hit"] < 0.01 and v["hit_nominal"] == formulas.FATIGUE_HIT_PENALTY and v["caster"] is False
    # 未飽和構築:實際損失 ≈ 名目折減
    low = _BUILDS["劍士(未飽和)"]()
    _set_swing_ratio(low, 0.4)
    v = combat.fatigue_penalty_view(low, gd, [foe])
    assert v is not None and abs(v["hit"] - v["hit_nominal"]) < 0.03 and v["hit"] >= 0.12
    # 實際損失 = 真實命中鏈對「滿體力 vs 出招後」的差(對在場敵人取最大)
    assert v["hit"] == max(combat.plain_attack_hit_chance(low, e, gd, 1.0) - combat.plain_attack_hit_chance(low, e, gd, 0.4)
                           for e in [foe])
    # 無在場敵人(都倒了)→ 退回名目值,不崩
    foe.health = 0
    assert combat.fatigue_penalty_view(low, gd, [foe])["hit"] == v["hit_nominal"]


# --- ② 標籤用的純讀 view:邊界 / 玩家限定 -------------------------------------
def test_fatigue_penalty_view_threshold_and_player_only():
    c = _char(spells=True)
    assert combat.fatigue_penalty_view(c, gd) is None                      # 滿體力:出招後 ≈ −0.8 個百分點 < 5% → 不標
    _set_swing_ratio(c, 0.81)
    assert combat.fatigue_penalty_view(c, gd) is None                      # 4.75% < 5% 門檻
    _set_swing_ratio(c, 0.79)
    v = combat.fatigue_penalty_view(c, gd)
    assert v is not None and v["exhausted"] is False and 0.05 <= v["hit"] < 0.06
    assert combat.fatigue_penalty_view(_foe(), gd) is None                 # 非玩家(敵人恆無體力懲罰)
    c.fatigue = 0
    v = combat.fatigue_penalty_view(c, gd)
    assert v["exhausted"] is True and v["hit"] == formulas.FATIGUE_HIT_PENALTY and abs(v["power"] - 0.25) < 1e-12
    c.max_fatigue = 0
    assert combat.fatigue_penalty_view(c, gd) is None                      # 無體力池 → 不標(防除以零)


def test_power_part_exists_only_for_spell_casters():
    caster, fighter = _char(spells=True), _char(spells=False)
    for c in (caster, fighter):
        _set_swing_ratio(c, 0.3)
    vc, vf = combat.fatigue_penalty_view(caster, gd), combat.fatigue_penalty_view(fighter, gd)
    assert vc["caster"] is True and abs(vc["power"] - formulas.fatigue_power_penalty(caster.fatigue / caster.max_fatigue)) < 1e-12
    assert vf["caster"] is False and vf["power"] == 0.0
    # 法效折減單獨就能讓施法者出標籤(命中實際無損的飽和施法者)
    sat = _BUILDS["劍士 100 + 敏捷 + 精準里程碑(飽和)"]()
    sat.spells = ["flames"]
    _set_swing_ratio(sat, 0.4)
    v = combat.fatigue_penalty_view(sat, gd, [_foe("bandit")])
    assert v is not None and v["hit"] < 0.01 and v["power"] >= 0.14


def test_view_power_equals_what_magic_cast_really_uses():
    c = _char(spells=True)
    for ratio in (0.1, 0.4, 0.6, 0.79):
        _set_swing_ratio(c, ratio)
        v = combat.fatigue_penalty_view(c, gd)
        assert v["power"] == formulas.fatigue_power_penalty(c.fatigue / c.max_fatigue), ratio   # 出招前比例(fatigue_before)
        assert abs(v["power"] - (1.0 - formulas.cast_fatigue_power_factor(c.fatigue / c.max_fatigue))) < 1e-12


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
    foe = _foe("bandit")
    c = _BUILDS["劍士(未飽和)"]()
    c.spells = ["flames"]                                                  # 會施法 → 標籤同時帶命中與法效
    _set_swing_ratio(c, 0.6)
    v = combat.fatigue_penalty_view(c, gd, [foe])
    [t] = _fatigue_tags(_view(c, enemies=[foe])["me"]["tags"])
    assert t["s"] == f"體力不足 命中−{ui.pct(v['hit'])}% 法效−{ui.pct(v['power'])}%"
    assert re.fullmatch(r"體力不足 命中−\d+% 法效−\d+%", t["s"])
    assert t["good"] is None                                               # < 15%:中性色
    assert "個百分點" in t["tip"] and "出招後" in t["tip"] and "出招前" in t["tip"] and "95% 命中上限" in t["tip"]
    assert "閃避減半" not in t["tip"] and "體力恢復後消失" in t["tip"]
    _set_swing_ratio(c, 0.3)                                               # ≥ 15% → 紅
    [t] = _fatigue_tags(_view(c, enemies=[foe])["me"]["tags"])
    assert t["good"] is False and t["s"].startswith("體力不足")
    c.fatigue = 0                                                          # 力竭
    [t] = _fatigue_tags(_view(c, enemies=[foe])["me"]["tags"])
    assert t["s"].startswith("力竭") and t["good"] is False
    assert "閃避減半" in t["tip"] and "盾牆會落下" in t["tip"] and "盾牆暫停" not in t["tip"]   # 審查:盾牆是「落下須重立」非「暫停」


def test_combat_card_tag_for_saturated_fighter_says_so_instead_of_warning():
    foe = _foe("bandit")
    c = _BUILDS["劍士 100 + 敏捷 + 精準里程碑(飽和)"]()
    c.spells = ["flames"]                                                  # 讓標籤因「法效」出現,才能檢視命中那一段的說明
    _set_swing_ratio(c, 0.4)
    [t] = _fatigue_tags(_view(c, enemies=[foe])["me"]["tags"])
    assert "命中" not in t["s"] and t["s"].startswith("體力不足 法效−")        # 不亮「命中−N%」
    assert "頂著上限" in t["tip"] and "幾乎無損" in t["tip"]
    # 純近戰飽和角色:非力竭 → 完全沒有體力標籤;力竭 → 只有「力竭」二字(不含謊稱的百分比)
    f = _BUILDS["劍士 100 + 敏捷 + 精準里程碑(飽和)"]()
    _set_swing_ratio(f, 0.4)
    assert _fatigue_tags(_view(f, enemies=[foe])["me"]["tags"]) == []
    f.fatigue = 0
    [t] = _fatigue_tags(_view(f, enemies=[foe])["me"]["tags"])
    assert t["s"] == "力竭" and "閃避減半" in t["tip"]


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
    c = _char(breath=True, spells=True)
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
