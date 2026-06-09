"""M4:法術、煉金、附魔、裝備耐久的測試。"""

from tesrpg import synth
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import alchemy, combat, enchanting, inventory, magic


def _mage():
    gd = get_gamedata()
    return gd, build_character(gd, name="法", sex="female", race="altmer",
                               birthsign="mage", class_id="mage")


# --- 法術 ---------------------------------------------------------------
def test_mage_starts_with_spells_and_costs_scale():
    gd, c = _mage()
    assert "flames" in c.spells and "minor_heal" in c.spells
    base = gd.spells["flames"]["cost"]
    c.skills["destruction"] = 0
    hi = magic.effective_cost(c, gd, "flames")
    c.skills["destruction"] = 100
    lo = magic.effective_cost(c, gd, "flames")
    assert lo < hi <= base


def test_destruction_ignores_armor():
    gd, c = _mage()
    rng = RNG(1)
    crab = combat.spawn_creature(gd, "mudcrab", rng)  # 護甲 12
    hp0 = crab.health
    ev = magic.cast(c, gd, "flames", rng, target=crab)
    assert ev["ok"] and ev["damage"] >= 10 and crab.health == hp0 - ev["damage"]


def test_heal_and_magicka_cost():
    gd, c = _mage()
    c.health = 1
    m0 = c.magicka
    ev = magic.cast(c, gd, "minor_heal", rng=RNG(0))
    assert c.health > 1 and c.magicka < m0


def test_shield_adds_armor_then_expires():
    gd, c = _mage()
    magic.cast(c, gd, "oakflesh", rng=RNG(0))
    assert magic.active_shield(c) > 0
    # 護盾在戰鬥護甲計算中生效
    assert combat._armor_rating(c, gd) >= magic.active_shield(c)
    sp = gd.spells["oakflesh"]["effect"]["turns"]
    for _ in range(sp):
        magic.tick_effects(c)
    assert magic.active_shield(c) == 0


def test_fear_makes_creature_skip():
    gd, c = _mage()
    crab = combat.spawn_creature(gd, "mudcrab", RNG(0))
    magic.cast(c, gd, "fear", rng=RNG(0), target=crab)
    assert magic.is_feared(crab)


def test_soul_trap_gem_tier():
    gd, c = _mage()
    bear = combat.spawn_creature(gd, "bear", RNG(0))   # danger 4
    magic.cast(c, gd, "soul_trap", rng=RNG(0), target=bear)
    assert magic.has_soul_trap(bear)
    assert magic.soul_gem_for(bear) == "filled_greater_soul_gem"


def test_summon_adds_ally():
    gd, c = _mage()
    battle = {"allies": []}
    magic.cast(c, gd, "conjure_familiar", rng=RNG(0), battle=battle)
    assert len(battle["allies"]) == 1
    assert battle["allies"][0].summon_turns is not None     # 召喚物為帶計時的 Creature
    crab = combat.spawn_creature(gd, "mudcrab", RNG(0))
    hp0 = crab.health
    combat.resolve_attack(battle["allies"][0], crab, gd, RNG(1))   # 召喚物攻擊敵人
    assert crab.health <= hp0


# --- 煉金 ---------------------------------------------------------------
def test_brew_shared_effect():
    gd, c = _mage()
    inventory.add_item(c, "wheat", 1)            # heal + restore_fatigue
    inventory.add_item(c, "blue_mountain_flower", 1)  # restore_magicka + heal
    res = alchemy.brew(c, gd, "wheat", "blue_mountain_flower", RNG(0))
    assert res["ok"]
    # 產出 heal 藥水(共通效果)
    d = gd.item(res["item_id"])
    assert d["kind"] == "potion" and d["effect"]["type"] == "heal"
    # 可飲用回血
    c.health = 1
    inventory.use_item(c, gd, res["item_id"])
    assert c.health > 1


def test_brew_no_common_effect_fails():
    gd, c = _mage()
    inventory.add_item(c, "lavender", 1)   # 只有 restore_magicka
    inventory.add_item(c, "garlic", 1)     # 只有 restore_fatigue
    res = alchemy.brew(c, gd, "lavender", "garlic", RNG(0))
    assert not res["ok"]
    assert inventory.count_item(c, "lavender") == 0  # 材料仍被消耗


def test_higher_alchemy_stronger_potion():
    gd, c = _mage()
    c.skills["alchemy"] = 0
    inventory.add_item(c, "wheat", 1); inventory.add_item(c, "charred_skeever_hide", 1)
    low = gd.item(alchemy.brew(c, gd, "wheat", "charred_skeever_hide", RNG(0))["item_id"])["effect"]["magnitude"]
    c.skills["alchemy"] = 100
    inventory.add_item(c, "wheat", 1); inventory.add_item(c, "charred_skeever_hide", 1)
    high = gd.item(alchemy.brew(c, gd, "wheat", "charred_skeever_hide", RNG(0))["item_id"])["effect"]["magnitude"]
    assert high > low


# --- 附魔 ---------------------------------------------------------------
def test_enchant_weapon_adds_element_and_combat_bonus():
    gd, c = _mage()
    inventory.add_item(c, "iron_sword", 1)
    inventory.add_item(c, "filled_common_soul_gem", 1)
    res = enchanting.enchant_weapon(c, gd, "iron_sword", "fire", "filled_common_soul_gem")
    assert res["ok"]
    d = gd.item(res["item_id"])
    assert d["enchant"]["element"] == "fire" and d["enchant"]["magnitude"] >= 1
    # 裝備後戰鬥附帶額外元素傷害(無視護甲)
    c.weapon = res["item_id"]
    c.skills["blade"] = 100
    crab = combat.spawn_creature(gd, "mudcrab", RNG(3))
    base_bonus = d["enchant"]["magnitude"]
    # 多打幾次,命中時傷害應 >= 物理 + 元素附加(至少 > 元素附加)
    hit = False
    for _ in range(30):
        ev = combat.resolve_attack(c, crab, gd, RNG(_ + 1))
        if ev["hit"]:
            hit = True
            assert ev["damage"] >= base_bonus
            break
        crab.health = crab.max_health
    assert hit


# --- 耐久 / 修理 --------------------------------------------------------
def test_weapon_degrades_and_affects_damage():
    gd, c = _mage()
    c.weapon = "iron_sword"
    assert inventory.weapon_damage_mult(c) == 1.0
    c.weapon_condition = 0
    assert inventory.weapon_damage_mult(c) == 0.5


def test_armor_condition_and_repair():
    gd, c = _mage()
    inventory.add_item(c, "iron_cuirass", 1)
    inventory.equip_armor(c, gd, "iron_cuirass")
    c.armor_condition["cuirass"] = 0
    low = inventory.effective_armor_rating(c, gd)
    inventory.repair_all(c, 100.0)
    high = inventory.effective_armor_rating(c, gd)
    assert high > low


def test_synth_roundtrip_via_gamedata():
    gd, _ = _mage()
    bid = synth.brew_id("restore_magicka", 30)
    assert gd.item(bid)["effect"]["type"] == "restore_magicka"
    wid = synth.enchant_weapon_id("steel_sword", "frost", 9)
    assert gd.item(wid)["enchant"]["element"] == "frost" and gd.item(wid)["damage"] == gd.weapons["steel_sword"]["damage"]


# --- 施法接上體力系統(法師三系資源對稱)+ 法袍省體 -----------------------
def _caster(skill=50):
    """滿體力法師,備齊測試用法術。"""
    from tesrpg.systems import stats
    gd, c = _mage()
    c.skills["destruction"] = skill
    for s in ("flames", "fireball", "fire_storm", "minor_heal", "restore_mind"):
        if s not in c.spells:
            c.spells.append(s)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return gd, c


def test_cast_costs_fatigue():
    gd, c = _caster()
    f0 = c.fatigue
    cost = magic.spell_fatigue_cost(c, gd, "flames")
    assert cost >= 1
    magic.cast(c, gd, "flames", RNG(0), target=combat.spawn_creature(gd, "giant_rat", RNG(0)))
    assert c.fatigue == f0 - cost          # 施法確實扣體力


def test_spell_fatigue_scales_with_magicka():
    gd, c = _caster()
    assert magic.spell_fatigue_cost(c, gd, "fire_storm") > magic.spell_fatigue_cost(c, gd, "flames")


def test_athletics_lowers_cast_fatigue():
    gd, c = _caster()
    c.skills["athletics"] = 0
    hi = magic.spell_fatigue_cost(c, gd, "fireball")
    c.skills["athletics"] = 100
    lo = magic.spell_fatigue_cost(c, gd, "fireball")
    assert lo < hi                          # 運動降施法體力消耗(與近戰共用)


def test_low_fatigue_reduces_spell_power():
    def dmg(fat):
        gd, c = _caster()
        c.fatigue = fat
        t = combat.spawn_creature(gd, "giant_rat", RNG(5)); t.health = 999; t.max_health = 999
        return magic.cast(c, gd, "fireball", RNG(7), target=t)["damage"]
    assert dmg(999) > dmg(1)                # 力竭 → 法效降(滿體×1.0、空體×0.75)


def test_zero_fatigue_still_casts_no_fizzle():
    gd, c = _caster()
    c.fatigue = 0
    t = combat.spawn_creature(gd, "giant_rat", RNG(1)); t.health = 999
    ev = magic.cast(c, gd, "flames", RNG(1), target=t)
    assert ev["ok"] and ev["damage"] > 0 and c.fatigue == 0   # 0 體力仍施放、夾 0、不失敗


def test_restore_fatigue_spell_net_positive():
    gd, c = _caster()
    c.fatigue = c.max_fatigue - 100
    f0 = c.fatigue
    magic.cast(c, gd, "restore_mind", RNG(0))
    assert c.fatigue > f0                   # 回體力法術扣得少、回得多 → 淨正


def test_out_of_combat_heal_costs_fatigue():
    gd, c = _caster()
    c.health = 1
    f0 = c.fatigue
    magic.cast(c, gd, "minor_heal", RNG(0))   # 戰外施法(battle=None)
    assert c.health > 1 and c.fatigue < f0


def test_low_fatigue_weakens_summon():
    """對抗審查回歸:力竭應一併削弱召喚物 HP(與 heal/shield/damage 同步;滿體則不變)。"""
    def summon_hp(fat):
        gd, c = _caster()
        if "conjure_familiar" not in c.spells:
            c.spells.append("conjure_familiar")
        c.fatigue = fat
        battle = {"allies": []}
        magic.cast(c, gd, "conjure_familiar", RNG(0), battle=battle, enemies=[])
        return battle["allies"][-1].max_health
    assert summon_hp(999) > summon_hp(1)   # 空體召喚物較弱(×0.75)


def test_robe_set_lowers_cast_fatigue():
    gd, c = _caster()
    base = magic.spell_fatigue_cost(c, gd, "fireball")
    # 3 件 archmage → 未成套,無折扣
    for slot, iid in (("helmet", "archmage_hood"), ("cuirass", "archmage_robe"),
                      ("gauntlets", "archmage_gloves")):
        c.equipped[slot] = iid
    assert inventory.cast_fatigue_factor(c, gd) == 1.0
    assert magic.spell_fatigue_cost(c, gd, "fireball") == base
    # 補滿第 4 件 → 套裝折扣生效
    c.equipped["boots"] = "archmage_slippers"
    assert inventory.cast_fatigue_factor(c, gd) == 0.65
    assert magic.spell_fatigue_cost(c, gd, "fireball") < base
    # cloth 折扣較弱(成本高於 archmage)
    gd2, c2 = _caster()
    for slot, iid in (("helmet", "cloth_hood"), ("cuirass", "cloth_robe"),
                      ("gauntlets", "cloth_gloves"), ("boots", "cloth_slippers")):
        c2.equipped[slot] = iid
    assert magic.spell_fatigue_cost(c2, gd2, "fireball") > magic.spell_fatigue_cost(c, gd, "fireball")


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_magic OK")
