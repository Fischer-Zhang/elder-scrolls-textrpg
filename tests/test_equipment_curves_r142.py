"""R142 現實邏輯:裝備材質階梯不反轉 —— 黑檀盾強於矮人盾、玻璃長槍不便宜過弱者、
魔族武器維持同線最重、兩面十字軍盾名字可區分。"""

from tesrpg.gamedata import get_gamedata

gd = get_gamedata()


def test_shield_tier_not_inverted():
    assert gd.item("ebony_shield")["armor_rating"] > gd.item("dwarven_shield")["armor_rating"]
    assert gd.item("ebony_shield")["value"] > gd.item("dwarven_shield")["value"]
    assert gd.item("daedric_shield")["armor_rating"] > gd.item("ebony_shield")["armor_rating"]


def test_spear_value_not_inverted():
    g, e = gd.item("glass_spear"), gd.item("elven_spear")
    assert g["damage"] > e["damage"] and g["value"] > e["value"]   # 嚴格更強者不更便宜


def test_daedric_heaviest_in_line():
    assert gd.item("daedric_war_axe")["weight"] >= gd.item("dwarven_war_axe")["weight"]
    assert gd.item("daedric_bow")["weight"] >= gd.item("ebony_bow")["weight"]


def test_crusader_shields_distinct_names():
    assert gd.item("crusaders_ward")["name"] != gd.item("crusader_shield")["name"]


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
