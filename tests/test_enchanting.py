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


def test_resist_magnitude_r66_nonlinear_and_magic_split():
    """R66:resist 附魔 = soul^0.7 非線性 + 魔抗基數低、單元素=魔抗×2。其餘附魔型別不受影響。"""
    A = lambda s, p: enchanting.armor_magnitude("resist", s, 100, p)
    J = lambda s, p: enchanting.jewelry_magnitude("resist", s, 100, p)
    assert A(1, "magic") == 2 and J(1, "magic") == 3                  # 錨點 soul1·myst100
    for s in range(1, 6):                                             # 單元素 = 魔抗×2(逐階)
        assert A(s, "fire") == 2 * A(s, "magic") and J(s, "shock") == 2 * J(s, "magic")
    assert J(5, "magic") == 9 and J(5, "magic") < 5 * J(1, "magic")   # 非線性:大魂 < 微魂×5
    assert all(J(s + 1, "magic") >= J(s, "magic") for s in range(1, 5))  # 單調遞增
    assert enchanting.jewelry_magnitude("skill", 5, 100) == 15        # 其餘型別不變
    assert enchanting.armor_magnitude("res", 5, 100) == enchanting.enchant_magnitude(5, 100)


def test_enchant_magnitude_monotonic_in_soul_and_mysticism():
    assert enchanting.enchant_magnitude(5, 50) > enchanting.enchant_magnitude(1, 50)   # 魂石階越高越強
    assert enchanting.enchant_magnitude(3, 100) > enchanting.enchant_magnitude(3, 0)    # 神秘越高越強
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
