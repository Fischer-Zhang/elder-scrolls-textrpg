"""雙手重盾:盾擊 profile(忽略手持武器)、被動物理減傷、equip 清副手、crusaders_ward 轉重盾。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory


def _char():
    gd = get_gamedata()
    c = build_character(gd, name="盾", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_great_shield_bash_profile():
    gd, c = _char()
    c.skills["block"] = 80
    inventory.add_item(c, "steel_great_shield", 1)
    inventory.equip_armor(c, gd, "steel_great_shield")
    dmg, skill, sid = combat._weapon_profile(c, gd)
    assert dmg == gd.item("steel_great_shield")["bash_damage"]   # 盾擊用 bash_damage
    assert sid == "block" and skill == c.skill("block")          # 練 block
    assert combat.eff_weapon_id(c, gd) == "steel_great_shield"
    assert combat.effective_weapon_name(c, gd) == "鋼重盾"


def test_great_shield_ignores_held_weapon_enchant():
    """重盾盾擊忽略手持武器(休眠):用 bash 傷,不吃其元素/破甲。"""
    gd, c = _char()
    inventory.add_item(c, "dawnfang", 1)       # 帶火附魔的劍(休眠)
    inventory.equip_weapon(c, gd, "dawnfang")
    inventory.add_item(c, "iron_great_shield", 1)
    inventory.equip_armor(c, gd, "iron_great_shield")
    dmg, _skill, sid = combat._weapon_profile(c, gd)
    assert dmg == gd.item("iron_great_shield")["bash_damage"]    # 用盾擊傷,非 dawnfang
    assert sid == "block"


def test_great_shield_mitigation_factor():
    gd, c = _char()
    assert combat._great_shield_mitigation_factor(c, gd) == 1.0     # 無重盾 → 1.0
    inventory.add_item(c, "daedric_great_shield", 1)
    inventory.equip_armor(c, gd, "daedric_great_shield")
    mit = gd.item("daedric_great_shield")["mitigation"]
    assert abs(combat._great_shield_mitigation_factor(c, gd) - (1.0 - mit)) < 1e-9


def test_great_shield_equip_clears_offhand_and_crusaders_ward():
    gd, c = _char()
    for i in ("iron_dagger", "steel_dagger", "iron_great_shield"):
        inventory.add_item(c, i, 2)
    inventory.equip_weapon(c, gd, "iron_dagger")
    inventory.equip_offhand(c, gd, "steel_dagger")
    inventory.equip_armor(c, gd, "iron_great_shield")
    assert c.offhand == ""                                         # 重盾占雙手 → 清副手
    assert not inventory.is_dual_wielding(c, gd)
    cw = gd.item("crusaders_ward")                                 # crusaders_ward 現為重盾
    assert cw.get("great_shield") and cw.get("two_handed") and cw.get("mitigation", 0) > 0
    assert cw["enchant"]["kind"] == "resist_element"               # 保留魔抗附魔


def test_great_shield_bash_hits_and_is_physical():
    """盾擊命中造成物理傷(走護甲管線)。"""
    gd, c = _char()
    c.skills["block"] = 100
    c.fatigue = c.max_fatigue = 200
    inventory.add_item(c, "steel_great_shield", 1)
    inventory.equip_armor(c, gd, "steel_great_shield")
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.health = foe.max_health = 300
    foe.agility = 1
    ev = combat.resolve_attack(c, foe, gd, RNG(1))
    assert ev["hit"] and ev["damage"] >= 1


def run():
    test_great_shield_bash_profile()
    test_great_shield_ignores_held_weapon_enchant()
    test_great_shield_mitigation_factor()
    test_great_shield_equip_clears_offhand_and_crusaders_ward()
    test_great_shield_bash_hits_and_is_physical()


if __name__ == "__main__":
    run()
    print("test_great_shield OK")
