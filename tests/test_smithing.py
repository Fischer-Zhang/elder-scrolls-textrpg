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


# --- 淬鍊強化 ----------------------------------------------------------
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


# --- 回爐熔解(成品 → 部分材料,有損耗 + 同時練鍛造)----------------------
def test_meltdown_recycles_with_loss_and_trains():
    gd, c = _char()
    c.weapon = "fists"                                       # 確保待回爐物非手持
    ing, qty = smithing.meltdown_yield(gd, "steel_sword")
    rec = next(r for r in gd.recipes.values() if r["output"] == "steel_sword")
    assert ing == "steel_ingot"
    assert qty == int(rec["inputs"]["steel_ingot"] * smithing.RECYCLE_RATIO)
    assert qty < rec["inputs"]["steel_ingot"]               # 確有損耗(2 → 1)
    inventory.add_item(c, "steel_sword", 1)
    before = inventory.count_item(c, "steel_ingot")
    xp0, lvl0 = c.skill_xp["smithing"], c.base_skill("smithing")
    res = smithing.meltdown(c, gd, "steel_sword")
    assert res["ok"]
    assert inventory.count_item(c, "steel_sword") == 0               # 成品銷毀
    assert inventory.count_item(c, "steel_ingot") == before + qty    # 煉回材料
    assert c.skill_xp["smithing"] > xp0 or c.base_skill("smithing") > lvl0  # 同時練鍛造


def test_meltdown_no_recipe_uses_material_fallback():
    gd, c = _char()
    assert smithing.meltable(gd, "steel_gauntlets")                  # 無配方但 material=steel
    assert smithing.meltdown_yield(gd, "steel_gauntlets") == ("steel_ingot", 1)


def test_meltdown_excludes_non_metal_rare_and_equipped():
    gd, c = _char()
    assert not smithing.meltable(gd, "flame_staff")     # 法杖:無對應錠
    assert not smithing.meltable(gd, "fists")           # 徒手 value 0
    if gd.item_or_none("gold_amulet"):
        assert not smithing.meltable(gd, "gold_amulet")  # 飾品不可回爐
    # 龍鱗裝:required_ingot=dragon_scale(稀材)→ 不可回爐,維持稀缺
    for iid, d in gd.items.items():
        if d.get("kind") in ("weapon", "armor") and smithing._material_of(gd, iid) == "dragonscale":
            assert not smithing.meltable(gd, iid), iid
    # 附魔成品/具名神器不可回爐(不可逆毀)+ 弓/法杖(非純金屬重鑄)
    assert not smithing.meltable(gd, "mehrunes_razor")  # 具名神器(帶 enchant)
    assert not smithing.meltable(gd, "daedric_staff")   # 法杖(enchant + staff)
    assert not smithing.meltable(gd, "elven_bow")       # 弓(archetype 排除)
    assert not smithing.meltable(gd, "archmage_robe")   # 附魔法袍
    # 所有附魔成品一律不可回爐
    for iid, d in gd.items.items():
        if d.get("kind") in ("weapon", "armor") and d.get("enchant"):
            assert not smithing.meltable(gd, iid), f"{iid} 附魔成品不該可回爐"
    # 手持武器不可回爐(防裝備脫鉤)
    assert not smithing.meltdown(c, gd, c.weapon)["ok"]
    # 雙持副手亦不可回爐(防裝備脫鉤)
    inventory.add_item(c, "glass_dagger", 1)
    c.offhand = "glass_dagger"
    assert not smithing.meltdown(c, gd, "glass_dagger")["ok"]


def test_meltdown_no_arbitrage_on_cheap_singletons():
    """反套利:廉於一錠或單錠成品(買來回爐可套錠者)回爐無所得 → 不可回爐。"""
    gd, c = _char()
    for iid in ("iron_dagger", "iron_gauntlets", "steel_dagger"):
        assert not smithing.meltable(gd, iid), f"{iid} 不該可回爐(會套錠)"
        assert smithing.meltdown_yield(gd, iid)[1] == 0
    # 全商店在售且可回爐者:回爐材料價值不得 ≥ 買價(杜絕買廉品回爐套錠)
    for_sale = {it for l in gd.world["locations"].values() for it in l.get("merchant_stock", [])}
    for iid in for_sale:
        if not smithing.meltable(gd, iid):
            continue
        ingot, qty = smithing.meltdown_yield(gd, iid)
        from tesrpg.systems import world
        assert world.buy_price(c, gd, ingot) * qty <= world.buy_price(c, gd, iid), \
            f"{iid} 回爐套錠:材料買價高於成品買價"


def test_temper_visible_in_display():
    """淬鍊效果要在 UI 看得到:武器行傷害數字 + 護甲值 隨淬鍊上升(對齊戰鬥加成)。"""
    from tesrpg.ui import console as ui
    gd, c = _char()
    c.skills["smithing"] = 100                       # 解淬鍊上限
    inventory.add_item(c, "steel_sword", 1); inventory.equip_weapon(c, gd, "steel_sword")
    inventory.add_item(c, "steel_cuirass", 1); inventory.equip_armor(c, gd, "steel_cuirass")
    inventory.add_item(c, "steel_ingot", 10)
    base_dmg = gd.item("steel_sword")["damage"]
    arm0 = ui._armor_display(c, gd)[0]
    smithing.temper(c, gd, "steel_sword"); smithing.temper(c, gd, "steel_cuirass")
    assert smithing.weapon_temper_bonus(c) > 0 and smithing.armor_temper_bonus(c) > 0
    # 武器行顯示含淬鍊的有效傷害(= 戰鬥基礎傷害)
    assert f"傷害 {base_dmg + smithing.weapon_temper_bonus(c)}" in ui.weapon_line(c, gd)
    # 護甲顯示值上升正好等於淬鍊加成
    assert ui._armor_display(c, gd)[0] == arm0 + smithing.armor_temper_bonus(c)


def test_steel_set_fully_craftable():
    """鋼套裝(含護手/靴/盾)+ 鋼匕首皆可鍛造(補回缺漏配方);鐵套裝對照仍完整。"""
    gd = get_gamedata()
    craftable = {r["output"] for r in gd.recipes.values()}
    for iid in ("steel_helmet", "steel_cuirass", "steel_gauntlets", "steel_boots",
                "steel_shield", "steel_sword", "steel_mace", "steel_dagger"):
        assert iid in craftable, f"{iid} 應可鍛造"
    # 全 5 件鋼護甲套裝都可鍛
    steel_armor = [iid for iid, d in gd.items.items()
                   if d.get("kind") == "armor" and smithing._material_of(gd, iid) == "steel"]
    assert all(iid in craftable for iid in steel_armor), \
        f"鋼套裝仍有缺:{[i for i in steel_armor if i not in craftable]}"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_smithing OK")
