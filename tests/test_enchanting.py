"""enchanting 系統薄測試:附魔強度縮放、充能魂石計數、可附魔過濾(kind+無既有附魔)、附魔武器合成往返。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import enchanting, inventory


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="E", sex="male", race="breton", birthsign="mage", class_id="mage")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, c


def _plain_weapon(gd):
    return next(k for k, v in gd.weapons.items()
                if not v.get("enchant") and not v.get("two_handed") and k != "fists")


def test_enchant_magnitude_monotonic_in_soul_and_mysticism():
    assert enchanting.enchant_magnitude(5, 50) > enchanting.enchant_magnitude(1, 50)   # 魂石階越高越強
    assert enchanting.enchant_magnitude(3, 100) > enchanting.enchant_magnitude(3, 0)    # 秘術越高越強
    assert enchanting.enchant_magnitude(1, 0) >= 1                                       # 至少 1


def test_filled_soul_gems_counts_inventory():
    gd, c = _char()
    assert enchanting.filled_soul_gems(c, gd) == []
    inventory.add_item(c, "filled_petty_soul_gem", 1)
    assert "filled_petty_soul_gem" in enchanting.filled_soul_gems(c, gd)


def test_enchantable_filters_by_kind_and_no_existing_enchant():
    gd, c = _char()
    base_w = _plain_weapon(gd)
    inventory.add_item(c, base_w, 1)
    inventory.add_item(c, "leather_helmet", 1)
    inventory.add_item(c, "silver_ring", 1)
    assert base_w in enchanting.enchantable_weapons(c, gd)
    assert "leather_helmet" in enchanting.enchantable_armor(c, gd)
    assert "silver_ring" in enchanting.enchantable_jewelry(c, gd)
    assert base_w not in enchanting.enchantable_armor(c, gd)            # kind 分流不混


def test_enchant_weapon_roundtrips_to_element_item():
    gd, c = _char()
    c.skills["mysticism"] = 50
    base_w = _plain_weapon(gd)
    inventory.add_item(c, base_w, 1)
    inventory.add_item(c, "filled_petty_soul_gem", 1)
    res = enchanting.enchant_weapon(c, gd, base_w, "fire", "filled_petty_soul_gem")
    assert res["ok"]
    d = gd.item(res["item_id"])                                         # 合成 id 解析回武器
    assert d["enchant"]["kind"] == "weapon_element" and d["enchant"]["element"] == "fire"
    assert inventory.count_item(c, "filled_petty_soul_gem") == 0        # 魂石消耗
    assert inventory.count_item(c, base_w) == 0                         # 原武器消耗(換成附魔版)


def test_enchant_weapon_rejects_bad_element():
    gd, c = _char()
    base_w = _plain_weapon(gd)
    inventory.add_item(c, base_w, 1)
    inventory.add_item(c, "filled_petty_soul_gem", 1)
    res = enchanting.enchant_weapon(c, gd, base_w, "holy", "filled_petty_soul_gem")
    assert not res["ok"]
    assert inventory.count_item(c, base_w) == 1                         # 失敗不消耗


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_enchanting")
