"""裝備擴展 C+A:套組/套裝加成、飾品槽、附魔擴展(技能/屬性/抗性/資源)。"""

import tempfile
from pathlib import Path

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.synth import enchant_jewelry_id
from tesrpg.systems import enchanting, inventory, magic, progression, stats


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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_equipment OK")
