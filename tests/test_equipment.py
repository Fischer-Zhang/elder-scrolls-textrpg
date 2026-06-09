"""裝備擴展 C+A:套組/套裝加成、飾品槽、附魔擴展(技能/屬性/抗性/資源)。"""

import tempfile
from pathlib import Path

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.synth import enchant_jewelry_id
from tesrpg.systems import combat, enchanting, inventory, magic, progression, stats


def _char(race="imperial"):
    gd = get_gamedata()
    c = build_character(gd, name="裝", sex="male", race=race,
                        birthsign="warrior", class_id="warrior")
    return gd, c


def _wear_set(c, gd, material):
    """穿上某材質的 helmet/cuirass/gauntlets/boots 四件,並重算。"""
    bymat = {}
    for iid, d in gd.armor.items():
        if d.get("material") == material:
            bymat[d["slot"]] = iid
    for slot in inventory.SET_SLOTS:
        inventory.add_item(c, bymat[slot], 1)
        inventory.equip_armor(c, gd, bymat[slot])
    stats.recompute_max_resources(c, gd)


# --- C 套組資料完整性 ---------------------------------------------------
def test_every_material_has_full_set():
    gd, _ = _char()
    mats = {d["material"] for d in gd.armor.values() if d.get("material")}
    assert mats >= {"leather", "iron", "steel", "elven", "dwarven", "ebony", "glass"}
    for m in mats:
        slots = {d["slot"] for d in gd.armor.values() if d.get("material") == m}
        assert inventory.SET_SLOTS[0] in slots
        assert all(s in slots for s in inventory.SET_SLOTS), (m, slots)


# --- C 套裝加成 ---------------------------------------------------------
def test_full_set_grants_bonus():
    gd, c = _char()
    base = c.skill("sneak")
    _wear_set(c, gd, "leather")          # 皮革套裝 → 潛行 +15
    assert c.skill("sneak") == base + 15
    assert inventory.active_set_bonus(c, gd)["skill"] == "sneak"


def test_mixed_materials_no_set_bonus():
    gd, c = _char()
    # 穿三件皮革 + 一件鐵 → 非整套
    for slot, iid in [("helmet", "leather_helmet"), ("cuirass", "leather_cuirass"),
                      ("gauntlets", "leather_bracers"), ("boots", "iron_boots")]:
        inventory.add_item(c, iid, 1)
        inventory.equip_armor(c, gd, iid)
    stats.recompute_max_resources(c, gd)
    assert inventory.active_set_bonus(c, gd) is None
    assert c.skill("sneak") == c.base_skill("sneak")


def test_dwarven_set_fortifies_attribute_and_fatigue():
    gd, c = _char()
    base_end = c.attr("endurance")
    base_fat = c.max_fatigue
    _wear_set(c, gd, "dwarven")           # 矮人套裝 → 耐力 +10
    assert c.attr("endurance") == base_end + 10
    assert c.max_fatigue > base_fat       # 耐力流進 max_fatigue
    assert c.base_attr("endurance") == base_end   # base 不被汙染


# --- A 飾品槽 -----------------------------------------------------------
def test_jewelry_fills_ring_then_amulet_slots():
    gd, c = _char()
    inventory.add_item(c, "silver_ring", 2)
    inventory.add_item(c, "silver_amulet", 1)
    assert inventory.equip_jewelry(c, gd, "silver_ring") == "ring1"
    assert inventory.equip_jewelry(c, gd, "silver_ring") == "ring2"
    assert inventory.equip_jewelry(c, gd, "silver_amulet") == "amulet"


def test_jewelry_equipped_does_not_break_armor_rating():
    """回歸:飾品(amulet/ring 無 armor_rating 鍵)戴上後算護甲不得 KeyError。

    effective_armor_rating 的唯一呼叫端是 combat(玩家受物理攻擊時),
    曾因飾品缺鍵而戴戒指實戰即崩;此測試釘死該路徑。
    """
    gd, c = _char()
    for jid in ("silver_ring", "silver_amulet"):
        inventory.add_item(c, jid, 1)
        inventory.equip_jewelry(c, gd, jid)
    # 純飾品:護甲值 0(飾品無護甲值),但絕不可拋例外
    assert inventory.effective_armor_rating(c, gd) == 0.0
    assert inventory.worn_armor_rating(c, gd) == 0
    # 飾品 + 真護甲並存 → 只計真護甲(飾品計 0、不干擾)
    cuir = next(i for i, d in gd.armor.items() if d["slot"] == "cuirass")
    inventory.add_item(c, cuir, 1)
    inventory.equip_armor(c, gd, cuir)
    assert inventory.effective_armor_rating(c, gd) > 0
    # 戴飾品實戰:被物理攻擊計算護甲(combat → effective_armor_rating)不崩
    c.health = c.max_health = 120
    foe = combat.spawn_creature(gd, "giant_rat", RNG(1))
    foe.attack["damage"] = 20
    combat.auto_resolve(c, foe, gd, RNG(3))


# --- A 附魔擴展(四型別)------------------------------------------------
def test_fortify_skill_jewelry():
    gd, c = _char()
    rid = enchant_jewelry_id("silver_ring", "skill", "blade", 8)
    inventory.add_item(c, rid, 1)
    base = c.skill("blade")
    inventory.equip_jewelry(c, gd, rid)
    stats.recompute_max_resources(c, gd)
    assert c.skill("blade") == base + 8
    assert c.base_skill("blade") == base        # learn-by-doing 用的 base 不變
    # 卸下 → 加成消失
    inventory.unequip(c, "ring1")
    stats.recompute_max_resources(c, gd)
    assert c.skill("blade") == base


def test_fortify_attribute_jewelry_flows_into_derived():
    gd, c = _char()
    aid = enchant_jewelry_id("silver_amulet", "attr", "intelligence", 10)
    inventory.add_item(c, aid, 1)
    base_int = c.attr("intelligence")
    base_mag = c.max_magicka
    inventory.equip_jewelry(c, gd, aid)
    stats.recompute_max_resources(c, gd)
    assert c.attr("intelligence") == base_int + 10
    assert c.max_magicka > base_mag             # 智力 → max_magicka


def test_resist_jewelry_merges_with_race():
    gd, c = _char()
    rid = enchant_jewelry_id("gold_ring", "resist", "fire", 20)
    inventory.add_item(c, rid, 1)
    inventory.equip_jewelry(c, gd, rid)
    stats.recompute_max_resources(c, gd)
    assert c.equip_resist.get("fire") == 20
    assert magic.entity_resist(c, gd).get("fire", 0) >= 20   # 與種族抗性相加


def test_fortify_resource_jewelry():
    gd, c = _char()
    aid = enchant_jewelry_id("gold_amulet", "res", "health", 25)
    inventory.add_item(c, aid, 1)
    base = c.max_health
    inventory.equip_jewelry(c, gd, aid)
    stats.recompute_max_resources(c, gd)
    assert c.max_health == base + 25


# --- A 附魔流程 + 合成還原 ----------------------------------------------
def test_enchant_jewelry_flow_and_synth_roundtrip():
    gd, c = _char()
    inventory.add_item(c, "silver_ring", 1)
    inventory.add_item(c, "filled_common_soul_gem", 1)   # soul 3
    c.skills["mysticism"] = 50
    res = enchanting.enchant_jewelry(c, gd, "silver_ring", "skill", "destruction", "filled_common_soul_gem")
    assert res["ok"]
    iid = res["item_id"]
    # 存檔只存 id,gamedata.item() 由 synth 重建附魔
    d = gd.item(iid)
    assert d["enchant"]["kind"] == "fortify_skill"
    assert d["enchant"]["skill"] == "destruction"
    assert inventory.count_item(c, "filled_common_soul_gem") == 0   # 靈魂石消耗


# --- 護甲附魔擴展:技能/抗性/資源 + 向後相容 -----------------------------
def test_armor_skill_enchant_aggregates_into_skill():
    from tesrpg.synth import enchant_armor_id
    gd, c = _char()
    aid = enchant_armor_id("iron_cuirass", "skill", "blade", 8)
    base = c.base_skill("blade")
    inventory.add_item(c, aid, 1)
    inventory.equip_armor(c, gd, aid)
    stats.recompute_max_resources(c, gd)
    assert c.skill("blade") == base + 8 and c.base_skill("blade") == base   # 有效值升、base 不動
    inventory.unequip(c, "cuirass")
    stats.recompute_max_resources(c, gd)
    assert c.skill("blade") == base                                         # 卸下回復


def test_armor_resist_enchant_merges_with_race():
    from tesrpg.synth import enchant_armor_id
    gd, c = _char()
    aid = enchant_armor_id("iron_helmet", "resist", "fire", 20)
    inventory.add_item(c, aid, 1)
    inventory.equip_armor(c, gd, aid)
    stats.recompute_max_resources(c, gd)
    assert magic.entity_resist(c, gd).get("fire", 0) >= 20


def test_armor_resource_enchant_uses_armor_fortify_kind():
    """新式 5 段 res 附魔仍走 armor_fortify 鍵 → armor_fortify_totals/max 資源路徑不變。"""
    from tesrpg.synth import enchant_armor_id
    gd, c = _char()
    aid = enchant_armor_id("iron_gauntlets", "res", "health", 25)
    assert gd.item(aid)["enchant"] == {"kind": "armor_fortify", "stat": "health", "magnitude": 25}
    base = c.max_health
    inventory.add_item(c, aid, 1)
    inventory.equip_armor(c, gd, aid)
    stats.recompute_max_resources(c, gd)
    assert inventory.armor_fortify_totals(c, gd).get("health", 0) >= 25
    assert c.max_health == base + 25


def test_legacy_4field_encha_still_synthesizes():
    """舊存檔的 4 段 encha|base|stat|mag 仍正確還原(向後相容鐵律)。"""
    gd, _ = _char()
    d = gd.item("encha|iron_cuirass|health|20")
    assert d["enchant"] == {"kind": "armor_fortify", "stat": "health", "magnitude": 20}


def test_enchant_armor_flow_consumes_gem():
    gd, c = _char()
    inventory.add_item(c, "iron_cuirass", 1)
    inventory.add_item(c, "filled_common_soul_gem", 1)
    c.skills["mysticism"] = 50
    res = enchanting.enchant_armor(c, gd, "iron_cuirass", "skill", "destruction", "filled_common_soul_gem")
    assert res["ok"] and gd.item(res["item_id"])["enchant"]["kind"] == "fortify_skill"
    assert inventory.count_item(c, "filled_common_soul_gem") == 0


def test_save_load_preserves_armor_skill_enchant():
    from tesrpg.synth import enchant_armor_id
    gd, c = _char()
    aid = enchant_armor_id("iron_boots", "skill", "heavy_armor", 7)
    inventory.add_item(c, aid, 1)
    inventory.equip_armor(c, gd, aid)
    stats.recompute_max_resources(c, gd)
    state = GameState(player=c, time=GameTime(), rng=RNG(1))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "save.json"
        state.save(path)
        loaded = GameState.load(path)
    assert loaded.player.skill("heavy_armor") == c.skill("heavy_armor")


# --- 升級不汙染 base(回歸:fortify_attribute 經 char.attr 寫入 base 的雷)---
def test_levelup_with_fortify_attr_does_not_inflate_base():
    gd, c = _char()
    rid = enchant_jewelry_id("silver_ring", "attr", "strength", 10)
    inventory.add_item(c, rid, 1)
    inventory.equip_jewelry(c, gd, rid)
    stats.recompute_max_resources(c, gd)
    base_str = c.base_attr("strength")
    c.level_xp = 9999                                    # 強制可升級
    progression.apply_level_up(c, gd, {"strength": 2}, "health")
    assert c.base_attr("strength") == base_str + 2       # 只加實際點數,非 base+10+2
    assert c.attr("strength") == base_str + 2 + 10       # 有效值仍含飾品加成


# --- 存讀檔保留裝備加成 -------------------------------------------------
def test_save_load_preserves_equip_bonus():
    gd, c = _char()
    rid = enchant_jewelry_id("silver_ring", "skill", "sneak", 12)
    inventory.add_item(c, rid, 1)
    inventory.equip_jewelry(c, gd, rid)
    stats.recompute_max_resources(c, gd)
    state = GameState(player=c, time=GameTime(), rng=RNG(1))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "save.json"
        state.save(path)
        loaded = GameState.load(path)
    assert loaded.player.skill("sneak") == c.skill("sneak")
    assert loaded.player.equip_skill_bonus.get("sneak") == 12


def test_top_tier_set_bonuses():
    """頂級三套裝:魔族 +60 生命(重)/ 龍鱗 +25 火抗(輕)/ 龍祭司 +110 魔力套 + 每件附魔(布)。"""
    gd, c = _char()
    base_h = c.max_health
    _wear_set(c, gd, "daedric")
    assert c.max_health == base_h + 60
    assert inventory.dominant_weight_class(c, gd) == "heavy"
    assert inventory.active_set_bonus(c, gd)["stat"] == "health"

    gd, c = _char()
    base_fire = magic.entity_resist(c, gd).get("fire", 0)
    _wear_set(c, gd, "dragonscale")
    assert magic.entity_resist(c, gd).get("fire", 0) == base_fire + 25
    assert inventory.dominant_weight_class(c, gd) == "light"

    gd, c = _char()
    base_m = c.max_magicka
    _wear_set(c, gd, "dragonpriest")           # 套裝 110 + 四件 magicka 附魔 120
    assert c.max_magicka == base_m + 230


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_equipment OK")
