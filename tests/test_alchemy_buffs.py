"""R90/R91/R92 煉金增益軸補完 —— 餵飽 R30 限時增益藥引擎。
R90:8 新材料(resist 三元素 + 中性 fattr/fskill)。R91:材料加厚至 4 效果 + 9 種安全增益。
R92:依 R30「放開→必過 sim」開**攻擊向 fortify**(力量/blade/blunt/marksman/hand_to_hand/sneak/destruction)
—— sim 證 solo cap 仍夾(秒殺 0%)、精英 oneshot hit-gated 無增、達貢 offense 牆不破(見 sim_assassin
fortify-dosed 場景 + sim_builds destruction 探針)。

🔴 紅線守門(R92 收斂):可釀增益池絕不含 `fskill_smithing` / `fskill_mysticism` —— 兩者皆「**永久逃逸**」
類:喝藥當下做工藝 → 產物**永久留存、藥退仍在**(smithing→過頂 temper 永久武傷;mysticism→過強附魔永久),
連 SOLO_SNEAK cap 都繞不過。其餘攻擊向 fortify(strength/武器/sneak/destruction)為**限時**且 solo 受
絕對 cap 夾 → 已 sim 驗放行(見 sim_assassin fortify-dosed 場景)。
"""

from tesrpg.gamedata import get_gamedata
from tesrpg.creation import build_character
from tesrpg.state import GameState, GameTime
from tesrpg.systems import alchemy, inventory, magic
from tesrpg.rng import RNG

# 🔴 永久逃逸 → 絕不可釀:喝藥做工藝 → 產物永久(限時藥也救不回)。
#   smithing fortify → 過頂 temper 永久武傷;mysticism fortify → 過強附魔永久(enchant_magnitude 讀 mysticism)。
# (其餘攻擊向 fortify〔strength/武器技能/sneak/destruction〕為限時 + solo cap 夾,R92 經 sim 驗放行。)
_FORBIDDEN = {"fskill_smithing", "fskill_mysticism"}


def _reachable_buffs(gd):
    """掃所有材料對·經真實 alchemy.brew 路徑·收集可釀出的增益 kind(brewb|<kind>|…)。"""
    ings = sorted(gd.ingredients)
    reachable = set()
    for i in range(len(ings)):
        for j in range(i + 1, len(ings)):
            c = build_character(gd, name="C", sex="male", race="breton", birthsign="mage", class_id="mage")
            c.skills["alchemy"] = 80
            inventory.add_item(c, ings[i], 1)
            inventory.add_item(c, ings[j], 1)
            r = alchemy.brew(c, gd, ings[i], ings[j], RNG(1))
            if r.get("ok") and r.get("kind") == "buff":
                reachable.add(r["item_id"].split("|")[1])
    return reachable


def test_no_ingredient_carries_a_forbidden_buff_kind():
    """資料不變式:任何材料都不帶禁忌 fortify 效果(目前 = fskill_smithing 永久武傷)。"""
    gd = get_gamedata()
    for iid, d in gd.ingredients.items():
        for e in d["effects"]:
            assert e["kind"] not in _FORBIDDEN, f"{iid} 帶禁忌 buff {e['kind']}(永久武傷·絕不可釀)"


def test_brewable_pool_excludes_permanent_escape_kinds():
    """🔴 紅線:可釀池絕不含「永久逃逸」kind(smithing→永久武傷·mysticism→永久附魔·連 solo cap 都繞不過)。"""
    gd = get_gamedata()
    reachable = _reachable_buffs(gd)
    leaked = reachable & _FORBIDDEN
    assert not leaked, f"可釀池洩漏禁忌增益:{leaked}"


def test_r92_offensive_fortify_is_brewable():
    """R92:攻擊向 fortify(力量/武器技能/潛行/毀滅)經 sim 驗後開放可釀。"""
    gd = get_gamedata()
    reachable = _reachable_buffs(gd)
    want = {"fattr_strength", "fskill_blade", "fskill_blunt", "fskill_marksman",
            "fskill_hand_to_hand", "fskill_sneak", "fskill_destruction"}
    missing = want - reachable
    assert not missing, f"以下 R92 攻擊向 fortify 仍不可釀:{missing}"


def test_new_buff_axis_is_brewable():
    """R90 新增益(各 ≥2 材料共有)真的可釀。"""
    gd = get_gamedata()
    reachable = _reachable_buffs(gd)
    want = {"resist_fire", "resist_frost", "resist_shock",
            "fattr_intelligence", "fattr_personality", "fattr_endurance",
            "fattr_luck", "fskill_restoration"}
    missing = want - reachable
    assert not missing, f"以下新增益仍不可釀:{missing}"


def test_r91_thickened_buff_axis_is_brewable():
    """R91 材料加厚續填的 9 種安全增益皆可釀(各有「只共有它」的一對·防 max-magnitude 遮蔽)。"""
    gd = get_gamedata()
    reachable = _reachable_buffs(gd)
    want = {"fattr_speed", "fskill_mercantile", "fskill_speechcraft", "fskill_security",
            "fskill_athletics", "fskill_block", "fskill_light_armor", "fskill_heavy_armor",
            "fskill_scout"}
    missing = want - reachable
    assert not missing, f"以下 R91 新增益仍不可釀:{missing}"


def test_existing_buffs_still_brewable_no_regression():
    """既有 4 種增益仍可釀(只新增材料·零回歸)。"""
    gd = get_gamedata()
    reachable = _reachable_buffs(gd)
    for k in ("fattr_agility", "fattr_willpower", "fskill_alchemy", "resist_magic"):
        assert k in reachable, f"既有增益 {k} 回歸破損"


def test_resist_fire_potion_applies_combat_functionally():
    """釀 resist_fire 藥 → use → entity_resist fire 上升(引擎真的 fire,補法師對元素 boss)。"""
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="breton", birthsign="mage", class_id="mage")
    c.skills["alchemy"] = 80
    st = GameState(player=c, time=GameTime())
    inventory.add_item(c, "dragons_tongue", 1)
    inventory.add_item(c, "fire_salts", 1)
    r = alchemy.brew(c, gd, "dragons_tongue", "fire_salts", RNG(1))
    assert r["ok"] and r["item_id"].split("|")[1] == "resist_fire"
    before = magic.entity_resist(c, gd).get("fire", 0)
    inventory.use_item(c, gd, r["item_id"], state=st)
    after = magic.entity_resist(c, gd).get("fire", 0)
    assert after > before, f"fire resist 未上升:{before}->{after}"


def test_new_reagents_buyable_in_at_least_two_cities():
    """新材料皆可達(≥2 城 merchant_stock)。"""
    gd = get_gamedata()
    new = ["dragons_tongue", "fire_salts", "frost_mirriam", "snowberries",
           "void_salts", "pearl", "tundra_cotton", "juniper_berries"]
    for iid in new:
        n = sum(1 for l in gd.world["locations"].values() if iid in l.get("merchant_stock", []))
        assert n >= 2, f"{iid} 只在 {n} 城可買(需 ≥2)"


_R94_NEW_KINDS = {"fskill_alteration", "fskill_conjuration", "fskill_illusion",
                  "fskill_acrobatics", "resist_poison", "resist_disease"}


def test_r94_new_buff_axis_is_brewable():
    """R94:補魔法三學派/雜技 fortify 缺口 + resist_poison/disease 新家族,皆可釀。"""
    gd = get_gamedata()
    missing = _R94_NEW_KINDS - _reachable_buffs(gd)
    assert not missing, f"以下 R94 新增益仍不可釀:{missing}"


def _best_tier(gd):
    """每材料在生態池中的最低稀有度(common<uncommon<rare)。"""
    rank = {"common": 0, "uncommon": 1, "rare": 2}
    best = {}
    for pool in gd.ecology["pools"].values():
        for tier, mats in pool.items():
            if isinstance(mats, list):
                for m in mats:
                    if m not in best or rank[tier] < rank[best[m]]:
                        best[m] = tier
    return best


def test_r94_new_kinds_reachable_without_rare():
    """🔴 R94:6 個新可釀 kind 各須有「兩材皆 common/uncommon」的配對(低偵查可湊·rare 純獎勵不 gate)。"""
    gd = get_gamedata()
    best = _best_tier(gd)
    nonrare = lambda m: best.get(m) in ("common", "uncommon")
    ings = sorted(gd.ingredients)
    reach = set()
    for i in range(len(ings)):
        for j in range(i + 1, len(ings)):
            if not (nonrare(ings[i]) and nonrare(ings[j])):
                continue
            c = build_character(gd, name="C", sex="male", race="breton", birthsign="mage", class_id="mage")
            c.skills["alchemy"] = 80
            inventory.add_item(c, ings[i], 1)
            inventory.add_item(c, ings[j], 1)
            r = alchemy.brew(c, gd, ings[i], ings[j], RNG(1))
            if r.get("ok") and r.get("kind") == "buff":
                reach.add(r["item_id"].split("|")[1])
    gated = _R94_NEW_KINDS - reach
    assert not gated, f"以下新 kind 只能靠 rare 材料(被 scout 變相 gate):{gated}"


def test_resist_poison_potion_applies_combat_functionally():
    """釀 resist_poison 藥 → use → entity_resist poison 上升(引擎真的減毒·補低耐角色對毒沼怪)。"""
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="breton", birthsign="mage", class_id="mage")
    c.skills["alchemy"] = 80
    st = GameState(player=c, time=GameTime())
    inventory.add_item(c, "mudcrab_chitin", 1)
    inventory.add_item(c, "slaughterfish_scale", 1)
    r = alchemy.brew(c, gd, "mudcrab_chitin", "slaughterfish_scale", RNG(1))
    assert r["ok"] and r["item_id"].split("|")[1] == "resist_poison"
    before = magic.entity_resist(c, gd).get("poison", 0)
    inventory.use_item(c, gd, r["item_id"], state=st)
    assert magic.entity_resist(c, gd).get("poison", 0) > before


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_alchemy_buffs")
