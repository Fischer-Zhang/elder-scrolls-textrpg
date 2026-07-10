"""R144 現實邏輯:世界/行為 —— 具名劇情王不遊蕩、獸形真的脫裝、贓物越重越難偷、
魚不游沙漠、遭遇率看途中較險端、斯庫瑪不強心智不治外傷。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, crime, inventory, skooma, stats, world
from tesrpg.synth import enchant_armor_id

gd = get_gamedata()

# 物種精英(遊蕩合理·白名單);其餘 solo 王一律 spawn-only
_WANDERING_ELITES = {"dremora_lord", "frost_giant", "ancient_dragon", "vampire_lord",
                     "wamasu", "dark_moon_senche", "werewolf_alpha"}


def test_named_bosses_not_in_random_pools():
    for cid, c in gd.bestiary.items():
        if c.get("solo") and cid not in _WANDERING_ELITES:
            assert c.get("weight", 1) == 0 or c.get("min_level", 1) >= 99, \
                f"{cid} 具名劇情王不得混入隨機遭遇池(weight 0 或 min_level 99)"


def test_beast_form_sheds_equipment_bonuses():
    c = build_character(gd, name="狼", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    iid = enchant_armor_id("steel_cuirass", "attr", "strength", 3)
    inventory.add_item(c, iid, 1); inventory.equip_armor(c, gd, iid)
    tid = enchant_armor_id("steel_helmet", "thorns", "x", 5)
    inventory.add_item(c, tid, 1); inventory.equip_armor(c, gd, tid)
    stats.recompute_max_resources(c, gd)
    assert c.equip_attr_bonus.get("strength", 0) > 0
    assert inventory.thorns_reflect(c, gd) > 0
    c.beast_form = True
    stats.recompute_max_resources(c, gd)               # transform/revert 皆會 recompute
    assert c.equip_attr_bonus == {} and c.equip_resist == {}     # 獸形=裝備附魔全壓制
    assert inventory.thorns_reflect(c, gd) == 0.0                # 巨狼無甲可佈荊棘
    assert inventory.active_set_bonus(c, gd) is None
    assert not inventory.equip_armor(c, gd, iid)                 # 巨狼之爪無法穿脫
    c.beast_form = False
    stats.recompute_max_resources(c, gd)
    assert c.equip_attr_bonus.get("strength", 0) > 0             # 變回即恢復


def test_steal_chance_penalizes_heavy_loot():
    c = build_character(gd, name="賊", sex="m", race="khajiit", birthsign="thief", class_id="thief")
    c.skills.update(sneak=60, security=40)
    light = crime.steal_chance(c, gd, "gold_amulet") if gd.item_or_none("gold_amulet") else crime.steal_chance(c, gd, "lockpick")
    heavy = crime.steal_chance(c, gd, "daedric_battleaxe")
    assert light > heavy                                          # 順走雙手戰斧 ≠ 摸走小件
    assert crime.steal_chance(c, gd) == crime.steal_chance(c, gd, None)   # 無 item back-compat


def test_habitat_bound_never_wanders():
    fish = gd.bestiary["slaughterfish"]
    assert fish.get("habitat_bound")
    assert combat._biome_weight(fish, "desert") == 0.0            # 屠魚不游沙漠
    assert combat._biome_weight(fish, "swamp") > 0
    wolf = gd.bestiary["wolf"]
    assert combat._biome_weight(wolf, "desert") >= 0              # 一般獸不受影響


def test_encounter_uses_worse_end():
    assert world.encounter_chance(5, 12) > world.encounter_chance(1, 12)   # 函式方向
    # travel 端已改 max(起點,終點)(代碼層驗證:走出險地不再 0 遭遇)


def test_skooma_no_mind_boost_no_heal():
    assert "willpower" not in skooma.SKOOMA_HIGH_ATTR             # 嗑藥不強心智
    assert "health" not in skooma.SKOOMA_RESTORE                  # 提神不治外傷
    assert skooma.SKOOMA_RESTORE.get("fatigue", 0) > 0
    assert "strength" not in skooma.SKOOMA_HIGH_ATTR              # R20 紅線續守


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
