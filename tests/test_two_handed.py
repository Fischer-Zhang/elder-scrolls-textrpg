"""雙手武器握法:equip 自動卸裝/閘、ensure_grip 遷移、2H 傷 premium、維蘇拉德轉 2H。"""

import tesrpg.formulas as formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import inventory, stats


def _char():
    gd = get_gamedata()
    c = build_character(gd, name="雙", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_two_handed_auto_doffs_shield_and_offhand():
    gd, c = _char()
    for iid in ("iron_shield", "iron_dagger", "steel_dagger"):
        inventory.add_item(c, iid, 2)
    inventory.equip_armor(c, gd, "iron_shield")
    inventory.equip_weapon(c, gd, "iron_dagger")
    inventory.equip_offhand(c, gd, "steel_dagger")
    assert c.equipped.get("shield") == "iron_shield" and c.offhand == "steel_dagger"
    # 裝雙手戰錘 → 自動卸盾與副手
    inventory.add_item(c, "steel_warhammer", 1)
    assert inventory.equip_weapon(c, gd, "steel_warhammer")
    assert c.weapon == "steel_warhammer"
    assert c.offhand == "" and c.equipped.get("shield") is None


def test_two_handed_bars_offhand_and_shield():
    gd, c = _char()
    for iid in ("steel_battleaxe", "iron_shield", "steel_dagger"):
        inventory.add_item(c, iid, 1)
    inventory.equip_weapon(c, gd, "steel_battleaxe")
    assert not inventory.equip_offhand(c, gd, "steel_dagger")   # 主手 2H → 無副手槽
    assert not inventory.equip_armor(c, gd, "iron_shield")      # 主手 2H → 不能裝盾
    assert c.offhand == "" and c.equipped.get("shield") is None
    assert not inventory.is_dual_wielding(c, gd)


def test_ensure_grip_normalizes_stale_save():
    gd, c = _char()
    # 模擬舊存檔:2H 武器 + 殘留盾 + 副手(equip 閘出現前並存)
    inventory.add_item(c, "wuuthrad", 1)
    c.weapon = "wuuthrad"
    c.equipped["shield"] = "iron_shield"
    c.offhand = "steel_dagger"
    inventory.ensure_grip(c, gd)
    assert c.offhand == "" and c.equipped.get("shield") is None


def test_two_handed_damage_premium():
    gd, _ = _char()
    assert gd.item("steel_warhammer")["damage"] > gd.item("steel_mace")["damage"]
    assert gd.item("daedric_battleaxe")["damage"] > gd.item("daedric_war_axe")["damage"]
    assert gd.item("steel_warhammer").get("two_handed") is True
    assert gd.item("daedric_battleaxe").get("two_handed") is True
    assert inventory.is_two_handed(gd, "iron_warhammer") and not inventory.is_two_handed(gd, "iron_mace")


def test_wuuthrad_is_two_handed_axe():
    gd, _ = _char()
    w = gd.item("wuuthrad")
    assert w.get("two_handed") is True and w["archetype"] == "axe"
    assert formulas.archetype_armor_pen("axe") == 0.30   # 維蘇拉德現吃斧破甲
    assert w["enchant"]["kind"] == "berserk"


def test_two_handed_none_safe_and_recompute_clears_ghost():
    """對抗審查 GRIP-1/2:is_two_handed None-safe(舊存檔 weapon:null 載入不崩);
    2H 自動卸盾後**必 recompute**沖掉盾的 fortify/resist 幽靈值(R05;main.py equip_w 分支已補)。"""
    gd, c = _char()
    assert inventory.is_two_handed(gd, None) is False         # None-safe
    c.weapon = None
    inventory.ensure_grip(c, gd)                              # 不得拋例外(載入路徑)
    # 幽靈值回歸:帶魔抗附魔的盾(crusaders_ward magic+30)→ 裝 2H 自動卸盾
    gd, c = _char()
    for i in ("crusaders_ward", "steel_warhammer"):
        inventory.add_item(c, i, 1)
    inventory.equip_armor(c, gd, "crusaders_ward")
    stats.recompute_max_resources(c, gd)
    assert c.equip_resist.get("magic") == 30
    inventory.equip_weapon(c, gd, "steel_warhammer")          # 2H → 自動卸盾(equipped 變動)
    assert c.equipped.get("shield") is None
    assert c.equip_resist.get("magic") == 30                  # 🔴 未 recompute → 幽靈值仍在
    stats.recompute_max_resources(c, gd)                      # R05:卸盾後必 recompute
    assert not c.equip_resist.get("magic")                   # 幽靈值已沖掉


def run():
    test_two_handed_auto_doffs_shield_and_offhand()
    test_two_handed_none_safe_and_recompute_clears_ghost()
    test_two_handed_bars_offhand_and_shield()
    test_ensure_grip_normalizes_stale_save()
    test_two_handed_damage_premium()
    test_wuuthrad_is_two_handed_axe()


if __name__ == "__main__":
    run()
    print("test_two_handed OK")
