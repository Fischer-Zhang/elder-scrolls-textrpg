"""補屬性功能缺口(意志 / 幸運 名實相符)的單元測試。

鐵律:所有係數在屬性 = BASE_ATTRIBUTE(40)時回中性值(=改前行為)。
"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, dungeon, loot, magic


def _char(willpower=40, luck=40):
    gd = get_gamedata()
    c = build_character(gd, name="A", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    c.attributes["willpower"] = willpower
    c.attributes["luck"] = luck
    return gd, c


# --- base-40 中性 + 縮放 + 夾限 -----------------------------------------
def test_factors_neutral_at_base():
    b = formulas.BASE_ATTRIBUTE
    # 中性端(base-40)
    assert formulas.magicka_regen_combat(b) == 0
    assert formulas.magicka_regen_rest_factor(b) == 1.0
    assert formulas.mind_resist_chance(b) == 0.0
    assert formulas.luck_loot_factor(b) == 1.0
    assert formulas.luck_fortune(b) == 0.0
    # 縮放端(>base):投資越多越強,但嚴格低於 asymptote(R63 漸進);combat 回魔仍整數硬頂
    assert formulas.magicka_regen_combat(100) > 0
    assert formulas.magicka_regen_rest_factor(100) > 1.0
    assert 0 < formulas.mind_resist_chance(100) < formulas.MIND_RESIST_ASYMPTOTE
    assert 1.0 < formulas.luck_loot_factor(100) < formulas.LUCK_LOOT_ASYMPTOTE
    assert 0 < formulas.luck_fortune(100) < formulas.LUCK_FORTUNE_ASYMPTOTE
    # 漸進端(超大值):趨近 asymptote 但永不抵達(R63);唯 combat 回魔仍 == 硬整數頂
    assert formulas.magicka_regen_combat(999) == formulas.MAGICKA_REGEN_COMBAT_CAP
    assert (formulas.MIND_RESIST_ASYMPTOTE - 0.01
            < formulas.mind_resist_chance(999) < formulas.MIND_RESIST_ASYMPTOTE)
    assert (formulas.LUCK_LOOT_ASYMPTOTE - 0.01
            < formulas.luck_loot_factor(999) < formulas.LUCK_LOOT_ASYMPTOTE)
    assert (formulas.LUCK_FORTUNE_ASYMPTOTE - 0.01
            < formulas.luck_fortune(999) < formulas.LUCK_FORTUNE_ASYMPTOTE)
    # 「過 200 仍有意義」:200 嚴格優於剛過拐點,且 250>200(邊際非零)
    assert formulas.mind_resist_chance(200) > formulas.mind_resist_chance(140)
    assert formulas.luck_loot_factor(250) > formulas.luck_loot_factor(200)
    assert formulas.luck_fortune(250) > formulas.luck_fortune(200)


# --- 幸運進戰鬥(R116):傷害骰下界抬升 + 瓦巴賈克回火化險(皆 base-40 中性 → byte-identical)---
def test_luck_damage_floor_r116():
    b = formulas.BASE_ATTRIBUTE
    assert formulas.luck_damage_floor(b) == 0.0 and formulas.luck_damage_floor(b - 10) == 0.0   # ≤40 中性 → rng 序不變
    assert 0 < formulas.luck_damage_floor(100) < formulas.LUCK_DAMAGE_FLOOR_ASYMPTOTE            # >40 抬升、嚴格 <上限
    assert (formulas.LUCK_DAMAGE_FLOOR_ASYMPTOTE - 0.01
            < formulas.luck_damage_floor(999) <= formulas.LUCK_DAMAGE_FLOOR_ASYMPTOTE)           # 漸近上限
    assert formulas.luck_damage_floor(250) > formulas.luck_damage_floor(200)                     # 過 200 仍有邊際
    # 🔴 上界永不動:下界至多 0.85+0.10=0.95 < HI 1.15 → 恆留變異、不抬單擊天花板(精英秒殺門檻不變)
    assert formulas.DAMAGE_ROLL_LO + formulas.luck_damage_floor(999) < formulas.DAMAGE_ROLL_HI


def test_luck_wabbajack_save_r116():
    b = formulas.BASE_ATTRIBUTE
    assert formulas.luck_wabbajack_save(b) == 0.0 and formulas.luck_wabbajack_save(b - 10) == 0.0  # ≤40 中性(byte-identical)
    assert 0 < formulas.luck_wabbajack_save(100) < formulas.LUCK_WAB_SAVE_ASYMPTOTE
    assert (formulas.LUCK_WAB_SAVE_ASYMPTOTE - 0.02
            < formulas.luck_wabbajack_save(999) <= formulas.LUCK_WAB_SAVE_ASYMPTOTE)              # 漸近 0.40
    assert formulas.luck_wabbajack_save(250) > formulas.luck_wabbajack_save(150)


# --- 幸運:戰利豐厚 -----------------------------------------------------
def test_luck_loot_factor_in_resolve():
    # 高倍率:低機率必掉 + 金幣放大(確定性)
    r = loot.resolve_loot([{"gold": [10, 10]}, {"item": "gold_ring", "chance": 0.5}], RNG(1), luck_factor=2.0)
    assert r["gold"] == 20                              # 10 × 2.0
    assert ("gold_ring", 1) in r["items"]              # 0.5 × 2.0 → 1.0 → 必掉
    # 零機率排除側(併自 test_world.test_loot_resolver):即使倍率放大,chance 0.0 仍濾掉
    assert ("ruby", 1) not in loot.resolve_loot(
        [{"item": "ruby", "chance": 0.0}], RNG(1), luck_factor=2.0)["items"]
    # 中性 1.0:不放大(怪物中性掉落不變)
    assert loot.resolve_loot([{"gold": [10, 10]}], RNG(1), luck_factor=1.0)["gold"] == 10


def test_grant_loot_uses_player_luck():
    gd, c = _char(luck=100)
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.loot_gold = [100, 100]; foe.loot_table = []
    res = combat.grant_loot(c, foe, gd, RNG(1))
    assert res["gold"] > 100                            # 幸運放大金幣(100×factor>100)


# --- 幸運:時來運轉(撬鎖/逃跑) ----------------------------------------
def test_luck_fortune_lockpick_and_flee():
    gd, lo = _char(luck=40)
    _, hi = _char(luck=100)
    assert (dungeon.effective_pick_lock_chance(hi, gd, 50)
            > dungeon.effective_pick_lock_chance(lo, gd, 50))   # 高幸運撬鎖率更高
    # 逃跑率:統計上高幸運更易逃
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    flee_lo = sum(1 for s in range(300) if combat.try_flee(_char(luck=40)[1], foe, RNG(s)))
    flee_hi = sum(1 for s in range(300) if combat.try_flee(_char(luck=100)[1], foe, RNG(s)))
    assert flee_hi > flee_lo


# --- 意志:精神韌性(抗恐懼/麻痺) ------------------------------------
def test_mind_resist_helper():
    gd, base = _char(willpower=40)
    _, tough = _char(willpower=100)
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    assert not magic.resisted_mind(base, "fear", RNG(1))       # base-40 → 抗性 0,永不抗
    assert not magic.resisted_mind(tough, "dot", RNG(1))       # 非心智狀態 → 不抗
    assert not magic.resisted_mind(foe, "fear", RNG(1))        # 非玩家(怪物)→ 不抗
    resists = sum(1 for s in range(300) if magic.resisted_mind(tough, "paralyze", RNG(s)))
    assert resists > 0                                          # 高意志統計上會抗一部分


def test_combat_fear_resisted_by_willpower():
    gd, _ = _char()
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.strength = 80; foe.agility = 80                        # 提高命中率,確保多數攻擊命中
    foe.attack = {"name": "懾魂", "damage": 1, "skill": 90,
                  "on_hit": {"status": "fear", "element": None, "magnitude": 0, "turns": 2, "chance": 1.0}}
    base_feared = tough_feared = 0
    for s in range(120):
        b = _char(willpower=40)[1]
        combat.resolve_attack(foe, b, gd, RNG(s))
        base_feared += magic.is_feared(b)
        t = _char(willpower=100)[1]
        combat.resolve_attack(foe, t, gd, RNG(s))
        tough_feared += magic.is_feared(t)
    assert base_feared > tough_feared                          # 高意志較不易被控場


# --- R63 第二段效果:閾以下中性,過閾漸近(過 200 仍漲)----------------------
def test_second_stage_neutral_below_knee():
    f = formulas
    assert f.intelligence_spell_potency(50) == 1.0 and f.intelligence_spell_potency(40) == 1.0   # R67:智力 knee 降至 50
    assert f.willpower_cost_factor(115) == 1.0 and f.willpower_cost_factor(40) == 1.0
    assert f.agility_evasion(30) == 0.0 and f.agility_evasion(20) == 0.0        # R132:敏捷通用反射門檻 30 以下中性
    assert f.speed_extra_action_chance(100) == 0.0 and f.speed_extra_action_chance(50) == 0.0


def test_second_stage_scales_and_caps():
    f = formulas
    # R67 智力:漸近上限 = +30%(int100 線性峰)+ >100 額外 cap;過 200 仍漲、永不抵達
    int_asymptote = 1.0 + f.INTELLIGENCE_POTENCY_AT_CAP + f.INTELLIGENCE_POTENCY_OVER_CAP
    assert 1.0 < f.intelligence_spell_potency(200) < int_asymptote
    assert f.intelligence_spell_potency(300) > f.intelligence_spell_potency(200)


def test_intelligence_potency_r67_curve():
    """R67:智力法術威力 —— ≤50 中性 / 50→100 線性至 +30% / >100 softcap 漸近(總 +45%)。"""
    f = formulas
    assert f.intelligence_spell_potency(50) == 1.0                      # knee 下中性
    assert abs(f.intelligence_spell_potency(75) - 1.15) < 1e-9          # 中點:+15%
    assert abs(f.intelligence_spell_potency(100) - 1.30) < 1e-9         # int100 = +30%(線性峰)
    assert f.intelligence_spell_potency(100) < f.intelligence_spell_potency(138) < f.intelligence_spell_potency(200)  # >100 仍漲
    asy = 1.0 + f.INTELLIGENCE_POTENCY_AT_CAP + f.INTELLIGENCE_POTENCY_OVER_CAP
    assert f.intelligence_spell_potency(10_000) < asy + 1e-6            # 漸近不破 +45%
    assert 1.0 - f.WILLPOWER_COST_CAP < f.willpower_cost_factor(200) < 1.0
    assert f.willpower_cost_factor(300) < f.willpower_cost_factor(200)
    assert 0 < f.agility_evasion(200) < f.AGILITY_EVASION_CAP
    assert f.agility_evasion(300) > f.agility_evasion(200)
    assert 0 < f.speed_extra_action_chance(200) <= f.SPEED_EXTRA_ACTION_CAP
    assert f.speed_extra_action_chance(300) > f.speed_extra_action_chance(200)


def test_endurance_health_couples_and_diminishes():
    f = formulas
    assert f.endurance_health(50) == 50 * f.ENDURANCE_HEALTH_PER        # ≤cap == 舊 base_max_health
    assert f.endurance_health(100) == f.base_max_health(100)            # 拐點對齊(逐位元組)
    assert f.endurance_health(200) > f.endurance_health(100)            # 過 cap 仍長
    assert f.endurance_health(300) > f.endurance_health(200)            # 無上限
    # 過 cap 為遞減(同 50 點跨距,over 區增量 < 線性 ×2 區)
    assert (f.endurance_health(200) - f.endurance_health(150)) < (f.endurance_health(100) - f.endurance_health(50))


def test_willpower_magic_resist_r65():
    f = formulas
    assert f.willpower_magic_resist(40) == 0 and f.willpower_magic_resist(30) == 0   # 中性 ≤40(sim 不位移)
    assert 0 < f.willpower_magic_resist(100) < f.WILLPOWER_MAGIC_RESIST_CAP          # 投資見效、未封頂
    assert f.willpower_magic_resist(200) > f.willpower_magic_resist(100)             # 過 200 仍漲
    assert f.willpower_magic_resist(9999) <= f.WILLPOWER_MAGIC_RESIST_CAP            # 漸近不超 cap
    # entity_resist 聚合意志魔抗(R14:減 fire/frost/shock)
    gd, c = _char(willpower=100)
    assert magic.entity_resist(c, gd).get("magic", 0) >= f.willpower_magic_resist(100)


def test_intelligence_raises_power_and_willpower_lowers_cost():
    gd = get_gamedata()
    c = build_character(gd, name="M", sex="male", race="altmer", birthsign="mage", class_id="mage")
    sid = next(iter(gd.spells))
    school = gd.spells[sid]["school"]
    c.attributes["intelligence"] = 40
    p_lo = magic._power(c, gd, school)
    c.attributes["intelligence"] = 200
    assert magic._power(c, gd, school) > p_lo                            # 智力 → 法術威力(過 100)
    c.attributes["willpower"] = 40
    cost_lo = magic.effective_cost(c, gd, sid)
    c.attributes["willpower"] = 250
    cost_hi = magic.effective_cost(c, gd, sid)
    assert 1 <= cost_hi <= cost_lo                                       # 意志 → 省魔(過 115);max(1) 地板防免費


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_attributes OK")
