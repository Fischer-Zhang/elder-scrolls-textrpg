"""inventory 系統薄測試:堆疊 qty 數學、負重隨力量、握法旗標(2H/重盾)、雙持、荊棘反傷聚合。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import inventory


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="I", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, c


def test_add_count_remove_stacking_math():
    gd, c = _char()
    base = inventory.count_item(c, "healing_potion")
    inventory.add_item(c, "healing_potion", 3)
    inventory.add_item(c, "healing_potion", 2)             # 同 id 堆成一格、qty 相加
    assert inventory.count_item(c, "healing_potion") == base + 5
    assert inventory.remove_item(c, "healing_potion", 4)
    assert inventory.count_item(c, "healing_potion") == base + 1
    assert not inventory.remove_item(c, "healing_potion", base + 99)   # 不足 → False
    assert inventory.count_item(c, "healing_potion") == base + 1       # 不足不扣


def test_max_weight_scales_with_strength():
    gd, c = _char()
    c.attributes["strength"] = 30
    lo = inventory.max_weight(c, gd)
    c.attributes["strength"] = 80
    hi = inventory.max_weight(c, gd)
    assert hi > lo > 0


def test_two_handed_and_great_shield_flags():
    gd, c = _char()
    assert inventory.is_two_handed(gd, "iron_warhammer")               # 雙手戰錘
    assert not inventory.is_two_handed(gd, "silver_ring")              # 非武器 → False(item_or_none 安全)
    assert not inventory.is_two_handed(gd, None)                       # None 安全
    assert inventory.is_great_shield(gd, "crusaders_ward")             # 雙手重盾
    assert not inventory.is_great_shield(gd, "silver_ring")


def test_is_dual_wielding_false_without_offhand():
    gd, c = _char()
    assert not inventory.is_dual_wielding(c, gd)                       # 無副手 → 不雙持


def test_thorns_reflect_zero_without_thorns_armor():
    gd, c = _char()
    assert inventory.thorns_reflect(c, gd) == 0.0                      # 未穿荊棘附魔 → 0


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_inventory")
