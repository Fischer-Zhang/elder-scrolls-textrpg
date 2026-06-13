"""製作系統 + 煉金材料採集覆蓋 回歸測試。

涵蓋:配方 id 合法性、加工消耗/產出 + practice 成本、材料不足擋下、
以及 Task1 目標 ——「每種煉金材料都有野外取得途徑(野採事件或怪物掉落)」。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import crafting, inventory


def _char():
    gd = get_gamedata()
    c = build_character(gd, name="匠", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    return gd, c


# --- 加工消耗/產出 + practice 成本 ------------------------------------
def test_craft_consumes_inputs_produces_output_and_costs():
    gd, c = _char()
    inventory.add_item(c, "wolf_pelt", 5)
    pdef = gd.skills["smithing"]["practice"]
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    x0 = c.skill_xp.get("smithing", 0.0)
    assert crafting.can_craft(c, gd, "tan_leather_cuirass")
    res = crafting.craft(c, gd, "tan_leather_cuirass")
    assert res["ok"]
    assert inventory.count_item(c, "wolf_pelt") == 0           # 5 張皮全消耗
    assert inventory.count_item(c, "leather_cuirass") == 1     # 產出皮甲
    assert res["hours"] == pdef["hours"] and "tired" in res
    assert c.fatigue == f0 - pdef["fatigue"]                   # 付鍛造 practice 體力
    assert c.skill_xp.get("smithing", 0.0) > x0               # 鍛造練 smithing(併自 test_smithing)


def test_cant_craft_without_materials():
    gd, c = _char()
    assert not crafting.can_craft(c, gd, "tan_leather_bracers")
    assert crafting.missing_inputs(c, gd, "tan_leather_bracers") == {"wolf_pelt": 2}
    f0 = c.fatigue
    res = crafting.craft(c, gd, "tan_leather_bracers")
    assert not res["ok"] and res["hours"] == 0
    assert c.fatigue == f0                                     # 失敗零成本
    assert inventory.count_item(c, "leather_bracers") == 0


def test_recipes_for_station():
    gd, _ = _char()
    smith = crafting.recipes_for_station(gd, "smith")
    assert "tan_leather_cuirass" in smith
    # 非工坊地點(station=None)看不到 smith 限定配方
    assert "tan_leather_cuirass" not in crafting.recipes_for_station(gd, None)


# --- Task1:每種煉金材料都有野外取得途徑 ------------------------------
def _wild_gatherable(gd):
    ings = set(gd.ingredients)
    got = set()
    # 怪物掉落
    for c in gd.bestiary.values():
        for e in (c.get("loot") or []):
            iid = e if isinstance(e, str) else (e.get("item") or e.get("id"))
            if iid in ings:
                got.add(iid)
    # 野採事件(option.effects 與 option.check.success.effects 內的 item 給予)
    def scan_effects(effs):
        for ef in effs or []:
            if ef.get("type") == "item" and ef.get("qty", 0) > 0 and ef.get("item") in ings:
                got.add(ef["item"])
    for ev in gd.events.values():
        for opt in ev.get("options", []):
            scan_effects(opt.get("effects"))
            chk = opt.get("check") or {}
            scan_effects((chk.get("success") or {}).get("effects"))
    return got


def test_all_ingredients_have_wild_source():
    gd, _ = _char()
    ings = set(gd.ingredients)
    got = _wild_gatherable(gd)
    missing = ings - got
    assert not missing, f"仍只能購買、無野外取得途徑的材料:{sorted(missing)}"


def test_bone_meal_is_now_alchemy_ingredient():
    gd, _ = _char()
    assert "bone_meal" in gd.ingredients
    assert gd.item("bone_meal")["kind"] == "ingredient"
    assert gd.ingredients["bone_meal"]["effects"]               # 有煉金效果可調配


# --- 煙霧:在鐵匠處實跑 action_craft ----------------------------------
def test_craft_smoke_at_smith():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _char()
    smith = next(lid for lid, l in gd.world["locations"].items()
                 if "armorer" in l.get("services", []))
    c.location_id = smith
    inventory.add_item(c, "wolf_pelt", 2)
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    saved = (ui.menu, ui.message, ui.show_events)
    seq = iter(["leather", "tan_leather_bracers"])    # 兩層:先選材質系列,再選裝備
    ui.menu = lambda *a, **k: next(seq, None)
    ui.message = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None
    try:
        M.action_craft(state, gd)
    finally:
        ui.menu, ui.message, ui.show_events = saved
    assert inventory.count_item(c, "wolf_pelt") == 0
    assert inventory.count_item(c, "leather_bracers") == 1


def run():
    test_craft_consumes_inputs_produces_output_and_costs()
    test_cant_craft_without_materials()
    test_recipes_for_station()
    test_all_ingredients_have_wild_source()
    test_bone_meal_is_now_alchemy_ingredient()
    test_craft_smoke_at_smith()


if __name__ == "__main__":
    run()
    print("test_crafting 全通過")
