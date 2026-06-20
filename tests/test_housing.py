"""房產(收納倉庫 + 最佳休息 + 精神飽滿)回歸測試。

涵蓋:置產扣金/在城閘、倉庫存取 + **不計隨身負重**、存入禁穿戴/手持、取出以負重為閘、
毀損 id 不崩、精神飽滿(設/刷新/過期 + xp 倍率 + **不寫 base**)、存檔相容。
"""

import json

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import housing, inventory, progression


def _char(race="nord"):
    gd = get_gamedata()
    c = build_character(gd, name="居", sex="male", race=race, birthsign="warrior", class_id="warrior")
    return gd, c


def test_buy_ownership():
    gd, c = _char()
    assert housing.owns(c, "bruma") is False
    assert housing.buy(c, gd, "bruma") is True
    assert housing.owns(c, "bruma") is True
    assert housing.buy(c, gd, "bruma") is False        # 重複置產拒絕
    assert housing.buy(c, gd, "kvatch") is False        # 無房產的城拒絕


def test_action_house_buy_deducts_gold():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _char(); c.location_id = "bruma"; c.gold = 9000
    state = GameState(player=c, rng=RNG(1))
    saved = (ui.menu, ui.message, ui.confirm)
    ui.message = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True
    ui.menu = lambda *a, **k: None
    try:
        M.action_house(state, gd)
    finally:
        ui.menu, ui.message, ui.confirm = saved
    price = gd.house_at("bruma")["price"]
    assert housing.owns(c, "bruma") and c.gold == 9000 - price


def test_stash_weight_exempt_roundtrip():
    gd, c = _char(); c.location_id = "bruma"; housing.buy(c, gd, "bruma")
    inventory.add_item(c, "iron_cuirass", 1)
    w0 = inventory.total_weight(c, gd)
    assert housing.deposit(c, gd, "bruma", "iron_cuirass", 1) is True
    assert inventory.total_weight(c, gd) < w0                       # 倉庫不計負重
    assert housing.stash_count(c, "bruma", "iron_cuirass") == 1
    assert inventory.count_item(c, "iron_cuirass") == 0
    assert housing.withdraw(c, gd, "bruma", "iron_cuirass", 1) is True
    assert inventory.count_item(c, "iron_cuirass") == 1
    assert housing.stash_count(c, "bruma", "iron_cuirass") == 0


def test_deposit_equipped_blocked():
    gd, c = _char(); c.location_id = "bruma"; housing.buy(c, gd, "bruma")
    inventory.add_item(c, "iron_cuirass", 1); inventory.equip_armor(c, gd, "iron_cuirass")
    assert housing.deposit(c, gd, "bruma", "iron_cuirass", 1) is False   # 穿戴中不可存(免漏 recompute)
    inventory.add_item(c, "iron_sword", 1); c.weapon = "iron_sword"
    assert housing.deposit(c, gd, "bruma", "iron_sword", 1) is False     # 手持中不可存


def test_withdraw_gated_by_weight():
    gd, c = _char()
    c.attributes["strength"] = 10                       # 負重上限 = 50
    c.location_id = "bruma"; housing.buy(c, gd, "bruma")
    inventory.add_item(c, "iron_cuirass", 1)
    assert housing.deposit(c, gd, "bruma", "iron_cuirass", 1)
    w_item = gd.item("iron_cuirass")["weight"]
    inventory.add_item(c, "steel_mace", 1)
    while inventory.total_weight(c, gd) + w_item <= inventory.max_weight(c, gd):
        inventory.add_item(c, "steel_mace", 1)          # 背包塞到取回會超重
    assert housing.withdraw(c, gd, "bruma", "iron_cuirass", 1) is False
    assert housing.stash_count(c, "bruma", "iron_cuirass") == 1   # 取出失敗 → 仍在倉庫


def test_stash_broken_id_safe():
    gd, c = _char(); c.location_id = "bruma"; housing.buy(c, gd, "bruma")
    c.house_stash["bruma"] = [{"id": "ghost_item_xyz", "qty": 1}]
    assert gd.item_name("ghost_item_xyz") == "ghost_item_xyz"     # 列示用 item_name → 不崩
    assert housing.stash_count(c, "bruma", "ghost_item_xyz") == 1
    assert housing.withdraw(c, gd, "bruma", "ghost_item_xyz", 1) is True  # 毀損 id 仍可取回不崩


def test_well_rested_lifecycle():
    gd, c = _char()
    housing.set_well_rested(c, 100)
    assert c.well_rested_until == 100 + formulas.WELL_RESTED_HOURS and c.well_rested is True
    assert housing.refresh_well_rested(c, 100 + formulas.WELL_RESTED_HOURS - 1) is True
    assert housing.refresh_well_rested(c, 100 + formulas.WELL_RESTED_HOURS) is False   # 過期
    assert c.well_rested is False
    housing.set_well_rested(c, 500)                      # 再休息=刷新不疊加
    assert c.well_rested_until == 500 + formulas.WELL_RESTED_HOURS


def test_well_rested_xp_multiplier_and_no_base_write():
    gd, c1 = _char(); gd, c2 = _char()
    c2.well_rested = True
    base1, base2 = c1.base_skill("blade"), c2.base_skill("blade")
    progression.use_skill(c1, gd, "blade", 0.5)
    progression.use_skill(c2, gd, "blade", 0.5)
    assert c2.skill_xp["blade"] > c1.skill_xp["blade"]              # 精神飽滿 xp 較多
    assert c1.base_skill("blade") == base1 and c2.base_skill("blade") == base2  # 不寫 base


def test_save_roundtrip_and_old_save():
    gd, c = _char()
    c.houses_owned = ["bruma"]
    c.house_stash = {"bruma": [{"id": "iron_sword", "qty": 2}]}
    c.well_rested_until = 50; c.well_rested = True
    d = json.loads(json.dumps(c.to_dict()))
    l = Character.from_dict(d)
    assert l.houses_owned == ["bruma"] and l.house_stash["bruma"][0]["qty"] == 2
    assert l.well_rested_until == 50 and l.well_rested is True
    for k in ("houses_owned", "house_stash", "well_rested_until", "well_rested"):
        del d[k]
    o = Character.from_dict(d)
    assert o.houses_owned == [] and o.house_stash == {} and o.well_rested_until == 0 and o.well_rested is False


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_housing 全通過")
