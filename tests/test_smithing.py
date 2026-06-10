"""鍛造系統測試:鍛造技能(第 23 技能)/ 金屬鍛造 + 裁縫配方 + skill_req 門檻 /
法師布甲(魔力 + 法系技能 + 套裝)/ 淬鍊強化(consume/cap/戰鬥加成/不入售價/存檔)。"""

import json

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import combat, crafting, inventory, smithing, stats, world


def _char():
    gd = get_gamedata()
    c = build_character(gd, name="鍛", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    c.fatigue = c.max_fatigue
    return gd, c


# --- 鍛造是一項技能 ----------------------------------------------------
def test_smithing_is_a_skill():
    gd = get_gamedata()
    assert "smithing" in gd.skills and len(gd.skills) == 23
    assert gd.skills["smithing"]["practice"]["xp"] > 0
    for rid, r in gd.recipes.items():                      # 所有配方(含皮甲)皆練 smithing,非 armorer
        assert r.get("skill") == "smithing", rid


# --- 配方合法性 + 反套利 ----------------------------------------------
def test_recipe_ids_valid():
    gd = get_gamedata()
    for rid, r in gd.recipes.items():
        for iid in r["inputs"]:
            assert gd.item_or_none(iid), f"{rid}: 原料 {iid} 不存在"
        assert gd.item_or_none(r["output"]), f"{rid}: 產出 {r['output']} 不存在"
        assert r.get("station") in (None, "smith")
        assert r.get("skill") in gd.skills


def test_no_arbitrage_on_buyable_recipes():
    """可買材料的配方:Σ原料價值 ≥ 產出價值 → 不能買料鍛造再賣牟利。
    wolf_pelt(掉落限定)的皮甲配方刻意豁免;其餘金屬/布料配方須守此鐵則。"""
    gd = get_gamedata()
    for rid, r in gd.recipes.items():
        if "wolf_pelt" in r["inputs"]:
            continue
        iv = sum(gd.item(i)["value"] * n for i, n in r["inputs"].items())
        ov = gd.item(r["output"])["value"]
        assert iv >= ov, f"{rid}: 套利破口 Σ原料 {iv} < 產出 {ov}"


# --- 鍛造消耗/產出/付 practice -----------------------------------------
def test_forge_consumes_produces_and_trains_smithing():
    gd, c = _char()
    inventory.add_item(c, "iron_ingot", 2)
    x0 = c.skill_xp.get("smithing", 0.0)
    f0 = c.fatigue
    res = crafting.craft(c, gd, "forge_iron_sword")
    assert res["ok"]
    assert inventory.count_item(c, "iron_ingot") == 0      # 2 錠全消耗
    assert inventory.count_item(c, "iron_sword") == 1       # 產出鐵劍
    assert c.skill_xp.get("smithing", 0.0) > x0             # 練到鍛造
    assert c.fatigue < f0 and res["hours"] >= 1             # 付體力 + 時間


# --- skill_req 門檻 ----------------------------------------------------
def test_skill_req_gate():
    gd, c = _char()
    inventory.add_item(c, "steel_ingot", 3)
    assert gd.recipes["forge_steel_sword"]["skill_req"] == 25
    assert not crafting.meets_skill_req(c, gd, "forge_steel_sword")   # 鍛造 0 → 擋
    r = crafting.craft(c, gd, "forge_steel_sword")
    assert not r["ok"] and "鍛造" in r["message"]
    assert inventory.count_item(c, "steel_ingot") == 3               # 擋下:零消耗
    c.skills["smithing"] = 25
    assert crafting.meets_skill_req(c, gd, "forge_steel_sword")
    assert crafting.craft(c, gd, "forge_steel_sword")["ok"]
    # 無 skill_req 的配方一律可做(向後相容)
    assert crafting.meets_skill_req(c, gd, "forge_iron_dagger")


# --- 法師布甲 ----------------------------------------------------------
def test_mage_robe_fortifies_magicka_and_skill():
    gd = get_gamedata()
    c = build_character(gd, name="法", sex="male", race="altmer", birthsign="mage", class_id="mage")
    base_mag, base_alt = c.max_magicka, c.base_skill("alteration")
    c.equipped["cuirass"] = "cloth_robe"        # armor_fortify magicka +15
    c.equipped["gauntlets"] = "cloth_gloves"    # fortify_skill alteration +6
    stats.recompute_max_resources(c, gd)        # 觸發 recompute_equipment → equip_skill_bonus
    assert c.max_magicka == base_mag + 15
    assert c.skill("alteration") == base_alt + 6
    assert c.base_skill("alteration") == base_alt           # 加成不寫進 base(成長/夾限用 base)


def test_cloth_set_glass_cannon():
    gd = get_gamedata()
    c = build_character(gd, name="法", sex="male", race="altmer", birthsign="mage", class_id="mage")
    base = c.max_magicka
    for slot, iid in [("helmet", "cloth_hood"), ("cuirass", "cloth_robe"),
                      ("gauntlets", "cloth_gloves"), ("boots", "cloth_slippers")]:
        c.equipped[slot] = iid
    assert inventory.active_set_bonus(c, gd)["stat"] == "magicka"   # 四件同材質 → 套裝加成
    stats.recompute_max_resources(c, gd)
    assert c.max_magicka == base + 25 + 40                 # 件件魔力(10+15)+ 套裝 40
    assert inventory.worn_armor_rating(c, gd) <= 1         # 玻璃大砲:近乎零護甲


# --- 淬鍊強化 ----------------------------------------------------------
def test_temper_cap_scales_with_smithing():
    assert smithing.temper_cap(0) == 0
    assert smithing.temper_cap(40) == 2
    assert smithing.temper_cap(100) == 5
    assert smithing.temper_cap(999) == smithing.TEMPER_MAX


def test_temper_consumes_caps_and_boosts_combat():
    gd, c = _char()
    c.skills["smithing"] = 40                  # cap 2
    c.weapon = "iron_sword"
    inventory.add_item(c, "iron_sword", 1)
    inventory.add_item(c, "iron_ingot", 5)
    base_dmg = combat._weapon_profile(c, gd)[0]
    t = smithing.temper(c, gd, "iron_sword")
    assert t["ok"] and t["level"] == 1
    assert inventory.count_item(c, "iron_ingot") == 4       # 扣 1 錠
    assert combat._weapon_profile(c, gd)[0] == base_dmg + smithing.TEMPER_WEAPON_PER
    smithing.temper(c, gd, "iron_sword")                    # +2 → 達 cap
    assert c.weapon_temper["iron_sword"] == 2
    assert not smithing.can_temper(c, gd, "iron_sword")[0]  # cap 2 達頂 → 擋
    # 護甲淬鍊 → 護甲值升
    c.equipped["cuirass"] = "iron_cuirass"
    inventory.add_item(c, "iron_cuirass", 1)
    ar0 = combat._armor_rating(c, gd)
    smithing.temper(c, gd, "iron_cuirass")
    assert combat._armor_rating(c, gd) == ar0 + smithing.TEMPER_ARMOR_PER


def test_temper_only_player_creature_unaffected():
    gd = get_gamedata()
    wolf = combat.spawn_creature(gd, "wolf", RNG(1))
    assert combat._armor_rating(wolf, gd) == wolf.armor_rating   # 怪走非玩家分支,讀取鉤不套用


def test_is_temperable():
    gd = get_gamedata()
    for w in ("iron_sword", "cloth_robe", "elven_sword", "dwarven_mace", "glass_dagger", "ebony_sword"):
        assert smithing.is_temperable(gd, w), w               # iron/steel/皮/布/精靈/矮人/玻璃/黑檀皆可淬
    assert not smithing.is_temperable(gd, "gold_ring")        # 飾品不可淬
    assert not smithing.is_temperable(gd, "flame_staff")      # 法杖(flame 無對應錠)不可淬


def test_temper_not_in_sell_price():
    gd, c = _char()
    c.skills["smithing"] = 100
    c.weapon = "iron_sword"
    inventory.add_item(c, "iron_sword", 1)
    inventory.add_item(c, "iron_ingot", 3)
    p0 = world.sell_price(c, gd, "iron_sword")
    smithing.temper(c, gd, "iron_sword")
    assert world.sell_price(c, gd, "iron_sword") == p0       # 淬鍊不入售價 → 無「淬→賣」套利


# --- 存檔 --------------------------------------------------------------
def test_save_roundtrip_and_old_save_compat():
    gd, c = _char()
    c.skills["smithing"] = 60
    c.weapon = "iron_sword"
    inventory.add_item(c, "iron_sword", 1)
    inventory.add_item(c, "iron_ingot", 1)
    smithing.temper(c, gd, "iron_sword")
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.weapon_temper == c.weapon_temper and loaded.skills["smithing"] == 60
    d = c.to_dict()                                          # 模擬舊存檔缺 temper 欄
    del d["weapon_temper"]
    del d["armor_temper"]
    old = Character.from_dict(d)
    assert old.weapon_temper == {} and old.armor_temper == {}


def test_high_tier_metal_smithing():
    """更高階金屬鍛造:elven/dwarven/glass/ebony 配方按 skill_req 分級 + 對應錠 + 可淬鍊 + 可取得。"""
    gd = get_gamedata()
    reqs = {"elven": 40, "dwarven": 55, "glass": 70, "ebony": 85}
    ingots = {"elven": "moonstone_ingot", "dwarven": "dwarven_ingot",
              "glass": "malachite_ingot", "ebony": "ebony_ingot"}
    for rid, r in gd.recipes.items():
        tier = r["output"].split("_")[0]
        if tier in reqs and rid.startswith("forge_"):
            assert r.get("skill_req") == reqs[tier], rid       # 分級門檻
    for mat, ingot in ingots.items():                          # 高階材質可淬鍊、對應錠正確
        assert smithing._MATERIAL_INGOT.get(mat) == ingot
    sold = set()                                               # 四種高階錠皆有取得途徑
    for loc in gd.world["locations"].values():
        sold |= set(loc.get("merchant_stock", []))
    for ingot in ingots.values():
        assert ingot in sold, f"{ingot} 無取得途徑"
    # 端到端:給 ebony 技能 + 錠 → 鍛造 ebony_sword;技能不足則擋
    c = build_character(gd, name="鍛", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    inventory.add_item(c, "ebony_ingot", 4)
    assert not crafting.craft(c, gd, "forge_ebony_sword")["ok"]   # 鍛造 0 < 85 → 擋
    c.skills["smithing"] = 85
    assert crafting.craft(c, gd, "forge_ebony_sword")["ok"]
    assert inventory.count_item(c, "ebony_sword") == 1


def test_temper_cleared_when_item_leaves_inventory():
    """賣/丟掉最後一件 → 清掉該 id 淬鍊(對抗審查確認:杜絕「賣後重買免費續淬」exploit)。"""
    gd, c = _char()
    c.skills["smithing"] = 60
    c.weapon = "iron_sword"
    inventory.add_item(c, "iron_sword", 1)
    inventory.add_item(c, "iron_ingot", 1)
    smithing.temper(c, gd, "iron_sword")
    assert c.weapon_temper.get("iron_sword") == 1
    inventory.remove_item(c, "iron_sword", 1)              # 賣/丟最後一件
    assert "iron_sword" not in c.weapon_temper             # 淬鍊投資隨之失去
    inventory.add_item(c, "iron_sword", 1)                 # 重新取得一把
    assert smithing.current_temper(c, gd, "iron_sword") == 0   # 從 +0 起,非免費續淬


def test_archmage_set_is_reachable():
    """對抗審查確認:大法師套裝四件須有取得途徑(否則 archmage 套裝加成=死內容)。"""
    gd = get_gamedata()
    sold = set()
    for loc in gd.world["locations"].values():
        sold |= set(loc.get("merchant_stock", []))
    for did, dg in gd.dungeons.items():
        sold |= {x for x in dg.get("loot", []) if isinstance(x, str)}          # 格內寶箱戰利品池
        sold |= {x for x in dg.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)}
    for piece in ("archmage_hood", "archmage_robe", "archmage_gloves", "archmage_slippers"):
        assert piece in sold, f"{piece} 無任何取得途徑(死內容)"


def test_top_tier_craftable_and_reachable():
    """頂級三材質:forge/tailor 配方 skill_req 90、_MATERIAL_INGOT 對應、稀有素材有掉落途徑、端到端可鍛。"""
    gd = get_gamedata()
    for mat, ingot in (("daedric", "ebony_ingot"), ("dragonscale", "dragon_scale"),
                       ("dragonpriest", "bolt_of_cloth")):
        assert smithing._MATERIAL_INGOT.get(mat) == ingot
    for prefix in ("forge_daedric_", "forge_dragonscale_", "tailor_dragonpriest_"):
        recs = [r for rid, r in gd.recipes.items() if rid.startswith(prefix)]
        assert recs and all(r.get("skill_req") == 90 for r in recs), prefix
    # 稀有素材(daedra_heart/dragon_scale)有取得途徑(boss treasure/loot 掃描)
    drop = set()
    for dg in gd.dungeons.values():
        drop |= {x for x in dg.get("loot", []) if isinstance(x, str)}          # 格內寶箱戰利品池
        drop |= {x for x in dg.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)}
    for cr in gd.bestiary.values():
        drop |= {e["item"] for e in cr.get("loot", []) if isinstance(e, dict) and "item" in e}
    for mat in ("daedra_heart", "dragon_scale"):
        assert mat in drop, f"{mat} 無取得途徑(死內容)"
    # 端到端:smithing 90 + 材料 → 鍛 daedric_sword(技能不足擋、足夠過、稀有素材消耗)
    c = build_character(gd, name="鍛", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    inventory.add_item(c, "ebony_ingot", 2)
    inventory.add_item(c, "daedra_heart", 1)
    assert not crafting.craft(c, gd, "forge_daedric_sword")["ok"]   # 0 < 90 → 擋
    c.skills["smithing"] = 90
    assert crafting.craft(c, gd, "forge_daedric_sword")["ok"]
    assert inventory.count_item(c, "daedric_sword") == 1
    assert inventory.count_item(c, "daedra_heart") == 0             # 稀有素材消耗
    assert smithing.is_temperable(gd, "daedric_sword")             # 頂裝可淬鍊


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_smithing OK")
