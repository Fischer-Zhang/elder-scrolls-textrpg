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
    f0 = c.fatigue
    ev = magic.cast(c, gd, "minor_heal", rng=RNG(0))
    assert c.health > 1 and c.magicka < m0
    assert c.fatigue < f0                     # 戰外施法(battle=None)亦扣體力


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


def test_synth_roundtrip_via_gamedata():
    gd, _ = _mage()
    bid = synth.brew_id("restore_magicka", 30)
    assert gd.item(bid)["effect"]["type"] == "restore_magicka"
    wid = synth.enchant_weapon_id("steel_sword", "frost", 9)
    assert gd.item(wid)["enchant"]["element"] == "frost" and gd.item(wid)["damage"] == gd.weapons["steel_sword"]["damage"]
    # 命中觸發附魔(weapon_status)synth-id roundtrip
    for st in ("vampiric", "paralyze", "regen"):
        d = gd.item(synth.enchant_weapon_status_id("steel_sword", st, 5, 3))
        assert d["enchant"]["kind"] == "weapon_status" and d["enchant"]["status"] == st


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
    # 體力消耗隨魔力成本縮放(大法術 > 小法術)— 唯讀斷言,不耗 fatigue
    assert magic.spell_fatigue_cost(c, gd, "fire_storm") > magic.spell_fatigue_cost(c, gd, "flames")
    # 運動降施法體力消耗(與近戰共用)— 只動 athletics/讀取,不耗 fatigue
    c.skills["athletics"] = 0
    hi = magic.spell_fatigue_cost(c, gd, "fireball")
    c.skills["athletics"] = 100
    lo = magic.spell_fatigue_cost(c, gd, "fireball")
    assert lo < hi
    # 施法確實扣體力 — 另起一個未動過 athletics 的 caster,避開上面 (b) 改過的 athletics 污染 cost
    gd2, c2 = _caster()
    f0 = c2.fatigue
    cost = magic.spell_fatigue_cost(c2, gd2, "flames")
    assert cost >= 1
    magic.cast(c2, gd2, "flames", RNG(0), target=combat.spawn_creature(gd2, "giant_rat", RNG(0)))
    assert c2.fatigue == f0 - cost


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


# --- 武器命中觸發附魔(吸血/麻痺/再生)+ 反鎖王 ---------------------------
def _fighter():
    gd, c = _mage()
    c.skills["blade"] = 70
    return gd, c


def test_weapon_vampiric_heals_on_hit():
    gd, c = _fighter()
    c.weapon = synth.enchant_weapon_status_id("steel_sword", "vampiric", 5, 0)
    c.health = 10
    crab = combat.spawn_creature(gd, "mudcrab", RNG(0)); crab.health = 999; crab.max_health = 999
    healed = False
    for i in range(12):
        ev = combat.resolve_attack(c, crab, gd, RNG(i))
        if ev.get("lifesteal", 0) > 0:
            healed = True
            assert ev["lifesteal"] <= ev["damage"]          # 不超過實際造成傷害
            break
    assert healed and c.health > 10 and c.health <= c.max_health


def test_weapon_regen_self_hot_and_no_stack():
    gd, c = _fighter(); c.skills["blade"] = 100
    c.weapon = synth.enchant_weapon_status_id("steel_sword", "regen", 6, 3)
    crab = combat.spawn_creature(gd, "mudcrab", RNG(0)); crab.health = 999; crab.max_health = 999

    def hit_once(seed):
        for i in range(seed, seed + 40):
            if combat.resolve_attack(c, crab, gd, RNG(i))["hit"]:
                return True
        return False

    assert hit_once(0)
    regens = [e for e in c.active_effects if e.get("source") == "ench_regen"]
    assert len(regens) == 1 and regens[0]["kind"] == "regen"
    assert hit_once(100)                                     # 再命中不疊加
    assert len([e for e in c.active_effects if e.get("source") == "ench_regen"]) == 1
    c.health = 10
    magic.tick_effects(c, gd)                                # regen tick 回血
    assert c.health > 10


def test_weapon_paralyze_applies_to_non_solo():
    gd, c = _fighter(); c.skills["blade"] = 90
    c.weapon = synth.enchant_weapon_status_id("steel_sword", "paralyze", 0, 1)
    applied = False
    for i in range(300):
        crab = combat.spawn_creature(gd, "mudcrab", RNG(i))
        combat.resolve_attack(c, crab, gd, RNG(i))
        if magic.is_paralyzed(crab):
            applied = True
            break
    assert applied


def test_weapon_paralyze_reduced_on_solo_boss():
    """R44 機率減免:solo BOSS 對附魔麻痺由「完全免疫」改機率抵抗——會被鎖,但非每次(SOLO_CONTROL_RESIST_CHANCE)。"""
    gd, c = _fighter(); c.skills["blade"] = 100
    c.weapon = synth.enchant_weapon_status_id("steel_sword", "paralyze", 0, 1)
    solo_tid = next(t for t, d in gd.bestiary.items() if d.get("solo"))
    locked = 0
    for i in range(400):
        boss = combat.spawn_creature(gd, solo_tid, RNG(i))
        combat.resolve_attack(c, boss, gd, RNG(i))
        if magic.is_paralyzed(boss):
            locked += 1
    assert 0 < locked < 400, locked        # 既非永鎖(舊免疫)亦非每次(機率減免生效)


def test_spell_control_reduced_on_solo_boss():
    """R44 機率減免:solo BOSS 對法術控場(fear / rout / mass_paralysis)由免疫改機率抵抗(會中也會抗)。"""
    gd, c = _caster()
    c.skills["illusion"] = 100
    for sp in ("fear", "rout", "mass_paralysis"):
        if sp not in c.spells:
            c.spells.append(sp)
    solo_tid = next(t for t, d in gd.bestiary.items() if d.get("solo"))
    for sp in ("fear", "rout", "mass_paralysis"):
        controlled = 0
        for i in range(200):
            boss = combat.spawn_creature(gd, solo_tid, RNG(i)); boss.health = boss.max_health = 99999
            c.magicka = c.max_magicka = 999
            magic.cast(c, gd, sp, RNG(i), target=boss, battle={"allies": []}, enemies=[boss])
            if magic.is_feared(boss) or magic.is_paralyzed(boss):
                controlled += 1
        assert 0 < controlled < 200, (sp, controlled)   # 機率減免:既會中也會抗


# --- 法術學派補完:召喚(束縛兵刃/亡者復生/新召喚)+ 秘術(結界/驅散/群體擒魂)-------
def test_bound_weapon_arms_unarmed_and_bypasses_armor():
    """束縛兵刃:空手法師也能近戰,且走元素分支 → 無視物理護甲。"""
    gd, c = _caster()
    c.spells.append("bound_sword")
    c.weapon = "fists"
    c.skills["conjuration"] = 80
    magic.cast(c, gd, "bound_sword", RNG(0), battle={"allies": []})
    assert any(e["kind"] == "bound_weapon" for e in c.active_effects)
    foe = combat.spawn_creature(gd, "mudcrab", RNG(0))
    foe.health = foe.max_health = 9999
    foe.armor_rating = 80                 # 重甲:純空手物理近乎歸零
    dealt = 0
    for i in range(30):
        ev = combat.resolve_attack(c, foe, gd, RNG(i))
        if ev["hit"]:
            dealt = ev["damage"]
            break
    assert dealt >= 10                    # 束縛兵刃無視 80 護甲 → 顯著傷害


def test_bound_weapon_ignores_weapon_imbue_no_double_dip():
    """束縛兵刃走元素分支,不讀物理分支的 weapon_imbue 加成 → 零雙吃(加不加灌注傷害相同)。"""
    def dmg(with_imbue):
        gd, c = _caster()
        c.spells += ["bound_sword", "flame_blade"]
        c.skills["conjuration"] = 70
        c.skills["alteration"] = 70
        c.weapon = "fists"
        magic.cast(c, gd, "bound_sword", RNG(0), battle={"allies": []})
        if with_imbue:
            magic.cast(c, gd, "flame_blade", RNG(0), battle={"allies": []})
        foe = combat.spawn_creature(gd, "mudcrab", RNG(0))
        foe.health = foe.max_health = 9999
        for i in range(60):
            ev = combat.resolve_attack(c, foe, gd, RNG(1000 + i))
            if ev["hit"]:
                return ev["damage"]
        return None
    assert dmg(False) == dmg(True)        # 灌注對束縛兵刃完全無效(否則雙吃)


def test_bound_weapon_no_stack_on_recast():
    gd, c = _caster()
    c.spells.append("bound_sword")
    magic.cast(c, gd, "bound_sword", RNG(0), battle={"allies": []})
    magic.cast(c, gd, "bound_sword", RNG(0), battle={"allies": []})
    assert len([e for e in c.active_effects if e["kind"] == "bound_weapon"]) == 1


def test_bound_weapon_sneak_still_capped_on_solo_boss():
    """🔴 紅線:束縛兵刃(法系近戰)偷襲 solo boss 仍受 SOLO_SNEAK_DAMAGE_CAP_RATIO 夾限。"""
    from tesrpg import formulas
    gd, c = _caster()
    c.spells.append("bound_sword")
    c.skills["conjuration"] = 100
    c.skills["sneak"] = 100
    magic.cast(c, gd, "bound_sword", RNG(0), battle={"allies": []})
    solo_tid = next(t for t, d in gd.bestiary.items() if d.get("solo"))
    for i in range(60):
        boss = combat.spawn_creature(gd, solo_tid, RNG(i))
        cap = boss.max_health * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO
        ev = combat.resolve_attack(c, boss, gd, RNG(i), sneak_attack=True)
        assert ev["damage"] <= cap + 1          # 偷襲開場單擊永不超夾限


def test_ward_consumes_and_absorbs():
    gd, c = _caster()
    c.skills["mysticism"] = 60
    c.spells.append("ward")
    magic.cast(c, gd, "ward", RNG(0))
    ward = next(e for e in c.active_effects if e["kind"] == "ward")
    mag0 = ward["magnitude"]
    assert mag0 >= 28                          # 40 * power(≥0.7)
    remaining, refund = magic.consume_ward(c, 25)
    assert remaining == 0 and refund == 0       # 25 傷全被吸收、一般結界不回魔
    assert ward["magnitude"] == mag0 - 25


def test_ward_blunts_elemental_hits_in_combat():
    def total_taken(with_ward):
        gd, c = _caster()
        c.skills["mysticism"] = 80
        c.spells.append("greater_ward")
        c.health = c.max_health = 9999
        if with_ward:
            magic.cast(c, gd, "greater_ward", RNG(0))
        troll = combat.spawn_creature(gd, "frost_troll", RNG(0))   # 霜屬性攻擊
        before = c.health
        for i in range(8):
            combat.resolve_attack(troll, c, gd, RNG(2000 + i))
        return before - c.health
    assert total_taken(True) < total_taken(False)   # 結界明顯吸掉一部分元素傷


def test_absorb_ward_refunds_magicka():
    gd, c = _caster()
    c.skills["mysticism"] = 80
    c.spells.append("spell_absorb_ward")
    c.health = c.max_health = 9999
    magic.cast(c, gd, "spell_absorb_ward", RNG(0))
    c.magicka = 0                               # 清空 → 回魔可見
    troll = combat.spawn_creature(gd, "frost_troll", RNG(0))
    gained = False
    for i in range(24):
        m0 = c.magicka
        combat.resolve_attack(troll, c, gd, RNG(3000 + i))
        if c.magicka > m0:
            gained = True
            break
    assert gained                               # 吸魔結界:吸收法術傷 → 回魔


def test_ward_no_stack_on_recast():
    gd, c = _caster()
    c.skills["mysticism"] = 50
    c.spells += ["ward", "greater_ward"]
    magic.cast(c, gd, "ward", RNG(0))
    magic.cast(c, gd, "greater_ward", RNG(0))
    wards = [e for e in c.active_effects if e["kind"] == "ward"]
    assert len(wards) == 1                      # 重施去重 → 不疊無敵(取最新)


def test_dispel_clears_only_self_debuffs():
    gd, c = _caster()
    c.spells.append("dispel")
    c.active_effects += [
        {"kind": "fear", "turns": 3},
        {"kind": "dot", "element": "poison", "magnitude": 5, "turns": 3},
        {"kind": "weaken", "magnitude": 0.4, "turns": 3},
        {"kind": "shield", "magnitude": 30, "turns": 3},
        {"kind": "ward", "magnitude": 40, "turns": 3},
    ]
    magic.cast(c, gd, "dispel", RNG(0))
    kinds = {e["kind"] for e in c.active_effects}
    assert not ({"fear", "dot", "weaken"} & kinds)   # 不良控場/侵蝕全清
    assert "shield" in kinds and "ward" in kinds     # 增益保留(不誤清)


def test_reanimate_raises_dead_nonsolo_enemy():
    gd, c = _caster()
    c.spells.append("reanimate_corpse")
    foe = combat.spawn_creature(gd, "mudcrab", RNG(0))
    foe.health = 0                              # 屍體
    battle = {"allies": []}
    ev = magic.cast(c, gd, "reanimate_corpse", RNG(0), battle=battle, enemies=[], corpses=[foe])
    assert ev["ok"] and len(battle["allies"]) == 1
    ally = battle["allies"][0]
    assert ally.summon_turns and ally.summon_turns > 0   # 限時盟友
    assert getattr(foe, "_reanimated", False)


def test_reanimate_refuses_empty_solo_and_no_battle_with_refund():
    gd, c = _caster()
    c.spells.append("reanimate_corpse")
    battle = {"allies": []}
    # ① 無屍 → 失敗退費(魔 + 體)
    m0, f0 = c.magicka, c.fatigue
    ev = magic.cast(c, gd, "reanimate_corpse", RNG(0), battle=battle, enemies=[], corpses=[])
    assert not ev["ok"] and c.magicka == m0 and c.fatigue == f0 and not battle["allies"]
    # ② solo boss 屍體 → 拒絕(無 boss 軍團)+ 退費
    solo_tid = next(t for t, d in gd.bestiary.items() if d.get("solo"))
    boss = combat.spawn_creature(gd, solo_tid, RNG(0))
    boss.health = 0
    m1, f1 = c.magicka, c.fatigue
    ev2 = magic.cast(c, gd, "reanimate_corpse", RNG(0), battle=battle, enemies=[], corpses=[boss])
    assert not ev2["ok"] and c.magicka == m1 and c.fatigue == f1 and not battle["allies"]
    # ③ 戰外(battle=None)→ 失敗退費
    m2, f2 = c.magicka, c.fatigue
    ev3 = magic.cast(c, gd, "reanimate_corpse", RNG(0), corpses=[])
    assert not ev3["ok"] and c.magicka == m2 and c.fatigue == f2


def test_reanimate_no_double_raise_same_corpse():
    gd, c = _caster()
    c.spells.append("reanimate_corpse")
    c.magicka = 9999
    foe = combat.spawn_creature(gd, "mudcrab", RNG(0))
    foe.health = 0
    battle = {"allies": []}
    ev1 = magic.cast(c, gd, "reanimate_corpse", RNG(0), battle=battle, enemies=[], corpses=[foe])
    ev2 = magic.cast(c, gd, "reanimate_corpse", RNG(0), battle=battle, enemies=[], corpses=[foe])
    assert ev1["ok"] and not ev2["ok"]          # 同屍不可二次復生
    assert len(battle["allies"]) == 1


def test_new_summons_spawn_and_lasting_summon_mastery():
    from tesrpg.systems import mastery
    gd, c = _caster()
    # 基礎召喚:conjure_familiar 在 _caster() setup 下可施放,召出帶計時的盟友且能攻擊敵人
    c.spells.append("conjure_familiar")
    fam_battle = {"allies": []}
    fam_ev = magic.cast(c, gd, "conjure_familiar", RNG(0), battle=fam_battle)
    assert fam_ev["ok"] and len(fam_battle["allies"]) == 1
    assert fam_battle["allies"][0].summon_turns is not None   # 召喚物為帶計時的 Creature
    fam_crab = combat.spawn_creature(gd, "mudcrab", RNG(0))
    fam_hp0 = fam_crab.health
    combat.resolve_attack(fam_battle["allies"][0], fam_crab, gd, RNG(1))   # 召喚物攻擊敵人
    assert fam_crab.health <= fam_hp0
    c.spells += ["conjure_frost_atronach", "conjure_storm_atronach", "conjure_dremora"]
    c.skills["conjuration"] = 100
    for sid in ("conjure_frost_atronach", "conjure_storm_atronach", "conjure_dremora"):
        battle = {"allies": []}
        ev = magic.cast(c, gd, sid, RNG(0), battle=battle, enemies=[])
        assert ev["ok"] and len(battle["allies"]) == 1 and battle["allies"][0].name
    # R106C 持久召喚里程碑 → 召喚物多駐留 1 回合(取代舊雙重召喚)
    base = {"allies": []}
    magic.cast(c, gd, "conjure_storm_atronach", RNG(0), battle=base, enemies=[])
    base_turns = base["allies"][0].summon_turns
    mastery.choose(c, gd, "conjuration_100", "lasting_summon")
    battle = {"allies": []}
    magic.cast(c, gd, "conjure_storm_atronach", RNG(0), battle=battle, enemies=[])
    assert len(battle["allies"]) == 1
    assert battle["allies"][0].summon_turns == base_turns + 1


def test_mass_soul_trap_marks_all_living_enemies():
    gd, c = _caster()
    c.spells.append("mass_soul_trap")
    foes = [combat.spawn_creature(gd, "mudcrab", RNG(i)) for i in range(3)]
    ev = magic.cast(c, gd, "mass_soul_trap", RNG(0), enemies=foes)
    assert ev["ok"] and all(magic.has_soul_trap(f) for f in foes)


def test_bound_weapon_ignores_equipped_weapon_riders():
    """對抗審查 major 修正:束縛兵刃完全取代裝備武器 → 不吃裝備武器的塗毒/命中附魔。"""
    gd, c = _caster()
    c.spells.append("bound_sword")
    c.skills["conjuration"] = 80
    c.weapon = synth.enchant_weapon_status_id("steel_sword", "vampiric", 5, 0)   # 吸血附魔
    c.weapon_poison = {"name": "劇毒", "charges": 3,
                       "status": {"status": "dot", "element": "poison", "magnitude": 6, "turns": 3}}
    c.health = 10
    magic.cast(c, gd, "bound_sword", RNG(0), battle={"allies": []})
    foe = combat.spawn_creature(gd, "mudcrab", RNG(0))
    foe.health = foe.max_health = 9999
    for i in range(20):
        if combat.resolve_attack(c, foe, gd, RNG(i))["hit"]:
            break
    assert c.weapon_poison["charges"] == 3                          # 塗毒未被消耗
    assert not any(e.get("element") == "poison" for e in foe.active_effects)   # 敵未中裝備毒
    assert c.health == 10                                           # 裝備吸血附魔未觸發


def test_bound_weapon_trains_conjuration_on_hit():
    """learn-by-doing 一致性:束縛兵刃命中鍛鍊咒術。"""
    from tesrpg.systems import progression
    gd, c = _caster()
    c.spells.append("bound_sword")
    c.skills["conjuration"] = 40
    c.weapon = "fists"
    magic.cast(c, gd, "bound_sword", RNG(0), battle={"allies": []})   # 施法在 patch 前 → 不計入
    foe = combat.spawn_creature(gd, "mudcrab", RNG(0))
    foe.health = foe.max_health = 9999
    calls = []
    orig = progression.use_skill
    progression.use_skill = lambda ch, g, sk, xp, *a, **k: (calls.append(sk), orig(ch, g, sk, xp, *a, **k))[1]
    try:
        for i in range(40):
            if combat.resolve_attack(c, foe, gd, RNG(i))["hit"]:
                break
    finally:
        progression.use_skill = orig
    assert "conjuration" in calls


def test_reanimate_hp_is_weakened():
    """對抗審查收斂:亡者復生為虛弱亡魂(REANIMATE_HP_FACTOR)→ 不滿血復生高 HP 精英。"""
    gd, c = _caster()
    c.spells.append("reanimate_corpse")
    from tesrpg.systems import stats
    stats.recompute_max_resources(c, gd, restore_full=True)
    foe = combat.spawn_creature(gd, "bear", RNG(0))
    foe.health = 0
    base = gd.bestiary["bear"]["max_health"]
    battle = {"allies": []}
    ev = magic.cast(c, gd, "reanimate_corpse", RNG(0), battle=battle, enemies=[], corpses=[foe])
    assert ev["ok"]
    assert battle["allies"][0].max_health < base    # 虛弱化(<原 HP),非滿血


def test_birthsign_resist_weakness():
    """出生星座弱點機制:學徒座 +魔力但受魔法/元素傷害↑(法師<學徒 修復);法師座無弱點;領主座對火脆弱。"""
    from tesrpg import formulas
    gd = get_gamedata()

    def mk(sign):
        return build_character(gd, name="x", sex="male", race="nord", birthsign=sign, class_id="mage")

    def mult(c, e):
        return formulas.resist_multiplier(magic.entity_resist(c, gd), e)

    mage, app, lord, warrior = mk("mage"), mk("apprentice"), mk("lord"), mk("warrior")
    # 學徒對魔法及三元素「皆比法師更易受傷」(delta 與種族基線無關:學徒在 magic 上多 -50)
    for e in ("magic", "fire", "frost", "shock"):
        assert mult(app, e) > mult(mage, e), f"學徒 {e} 未比法師脆弱"
    # 法師座本身無弱點(與無星座加成的戰士同抗性)
    assert mult(mage, "magic") == mult(warrior, "magic")
    # 領主座對火比無弱點者脆弱(flavor 終於有機制)
    assert mult(lord, "fire") > mult(warrior, "fire")
    # 風險換報酬:學徒魔力上限明顯高於法師(否則「法師<學徒」又回來了)
    assert app.max_magicka > mage.max_magicka


def _trapped(gd, tid, src="spell"):
    """生一隻已死、帶 soul_trap 效果的怪(src=weapon 標記武器擒魂)。"""
    c = combat.spawn_creature(gd, tid, RNG(1))
    eff = {"kind": "soul_trap", "turns": 3}
    if src == "weapon":
        eff["src"] = "weapon"
    c.active_effects = [eff]
    return c


def test_soul_capture_fills_smallest_sufficient_empty_gem():
    """擒魂填充:一般怪填『夠裝該階的最小空魂石』,填成的是『靈魂階』而非空石階。"""
    gd, c = _mage()
    inventory.add_item(c, "empty_petty_soul_gem", 1)      # cap1,裝不下 danger2
    inventory.add_item(c, "empty_common_soul_gem", 1)     # cap3,最小夠裝
    magic.resolve_soul_capture(c, _trapped(gd, "wolf"), gd)   # wolf danger 2
    assert inventory.count_item(c, "filled_lesser_soul_gem") == 1   # 靈魂階=2
    assert inventory.count_item(c, "empty_common_soul_gem") == 0    # 用掉 common
    assert inventory.count_item(c, "empty_petty_soul_gem") == 1     # petty 裝不下、留著


def test_soul_capture_grand_tier_from_danger5():
    """danger5 頂級魂可填空大魂石(soul5);解除舊有 min(4) 夾。"""
    gd, c = _mage()
    inventory.add_item(c, "empty_grand_soul_gem", 1)
    magic.resolve_soul_capture(c, _trapped(gd, "dremora_lord"), gd)   # danger 5,非 sentient
    assert inventory.count_item(c, "filled_grand_soul_gem") == 1


def test_black_soul_requires_black_gem_and_spell():
    """人形/有靈魂:白魂石裝不下;唯『空黑魂石 + 法術擒魂』才囚成黑魂石並 +infamy;武器擒魂逸散。"""
    gd, c = _mage()
    # 武器擒魂 → 逸散(法術專屬)
    inventory.add_item(c, "empty_black_soul_gem", 1)
    magic.resolve_soul_capture(c, _trapped(gd, "bandit", src="weapon"), gd)
    assert inventory.count_item(c, "filled_black_soul_gem") == 0
    assert inventory.count_item(c, "empty_black_soul_gem") == 1
    # 法術擒魂 + 空黑魂石 → 成黑魂石 + 惡名
    inf0 = c.infamy
    magic.resolve_soul_capture(c, _trapped(gd, "bandit", src="spell"), gd)
    assert inventory.count_item(c, "filled_black_soul_gem") == 1
    assert c.infamy == inf0 + magic.BLACK_SOUL_INFAMY


def test_soul_capture_escapes_without_empty_gem():
    """無合適空魂石 → 魂逸散(命中擒魂因此非無限,受空魂石庫存所限)。"""
    gd, c = _mage()
    msg = magic.resolve_soul_capture(c, _trapped(gd, "wolf"), gd)
    assert "逸散" in msg
    assert not any(k.startswith("filled_") for k in
                   [s["id"] for s in c.inventory])


def test_player_incoming_dot_stack_capped_offense_unchanged():
    """多次擊打疊毒防暴斃:怪物 on_hit DoT 在玩家身上按元素封頂 DOT_STACK_CAP;玩家攻擊側 DoT 不限(仍疊)。"""
    from tesrpg import formulas
    gd, p = _mage()
    p.max_health = p.health = 99999
    foe = combat.spawn_creature(gd, "frostbite_spider", RNG(1))   # poison on_hit、50% proc
    foe.attack["skill"] = 500                                     # 保證命中
    for s in range(20):
        combat.resolve_attack(foe, p, gd, RNG(s * 7 + 3))
    pdots = [e for e in p.active_effects if e["kind"] == "dot" and e["element"] == "poison"]
    assert 0 < len(pdots) <= formulas.DOT_STACK_CAP, f"玩家毒疊了 {len(pdots)} 層(應 1..{formulas.DOT_STACK_CAP})"
    # 攻擊側不變:玩家對敵施 DoT 仍可疊加
    e = combat.spawn_creature(gd, "bandit", RNG(1))
    for _ in range(4):
        e.active_effects.append(magic.make_status_effect(
            {"status": "dot", "element": "fire", "magnitude": 6, "turns": 3}))
    assert len([x for x in e.active_effects if x["kind"] == "dot"]) == 4


def test_expired_spell_trap_does_not_enable_black_capture():
    """對抗審查:過期法術擒魂(turns=0)不算 spell-trapped → 武器擒魂的人形怪不應被當黑魂捕獲。"""
    gd, c = _mage()
    inventory.add_item(c, "empty_black_soul_gem", 1)
    foe = combat.spawn_creature(gd, "bandit", RNG(1))                    # sentient
    foe.active_effects = [{"kind": "soul_trap", "turns": 0},                 # 過期法咒
                          {"kind": "soul_trap", "turns": 3, "src": "weapon"}]  # 活的武器擒魂
    magic.resolve_soul_capture(c, foe, gd)
    assert inventory.count_item(c, "filled_black_soul_gem") == 0         # 不被黑魂捕獲
    assert inventory.count_item(c, "empty_black_soul_gem") == 1          # 黑魂石未消耗


def test_mage_cities_stock_empty_soul_gems():
    """法師城供空魂石(填充燃料);大城另供空大/黑魂石。"""
    gd, _ = _mage()
    from tesrpg.systems import world
    assert "empty_petty_soul_gem" in world.merchant_catalog(gd, "bruma")        # mages_guild
    assert "empty_black_soul_gem" in world.merchant_catalog(gd, "imperial_city")  # major
    assert "empty_petty_soul_gem" not in world.merchant_catalog(gd, "anvil")    # 無 mages_guild(盜賊城)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_magic OK")
