"""煉金效果逐步揭露(R32:試驗發現系統)單元測試。

材料效果預設「???」,經 (a) 嚐一口 (b) 煉製成功用到 (c) 煉金技能被動 揭露。純資訊層 ——
brew 數學/路由完全不變(僅多一個 learn 回傳鍵 + 呼叫端套用)。涵蓋三揭露源、存檔、舊存檔遷移、防呆。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import alchemy, inventory


def _char(alchemy_skill=0):
    gd = get_gamedata()
    c = build_character(gd, name="探", sex="male", race="breton",
                        birthsign="mage", class_id="mage")
    c.skills["alchemy"] = alchemy_skill
    c.is_player = True
    c.known_effects = {}
    return gd, c


# --- 技能被動揭露 -------------------------------------------------------
def test_auto_reveal_count_scales_with_skill():
    assert [alchemy.auto_reveal_count(_char(s)[1]) for s in (0, 25, 50, 75, 100)] == [1, 2, 3, 4, 5]


def test_passive_reveal_floor_one_full_at_high_skill():
    gd, c = _char(0)
    alchemy.passive_reveal(c, gd, "wheat")               # wheat 有 2 效果
    assert alchemy.known_kinds(c, "wheat") == ["heal"]   # @0 → 揭露 1(JSON 首個)
    gd2, c2 = _char(50)
    alchemy.passive_reveal(c2, gd2, "wheat")
    assert set(alchemy.known_kinds(c2, "wheat")) == {"heal", "restore_fatigue"}   # @50 → 全揭露


# --- 嚐一口 -------------------------------------------------------------
def test_taste_reveals_first_deterministic_and_consumes():
    gd, c = _char(0)
    c.known_effects = {}
    base = inventory.count_item(c, "wheat")
    inventory.add_item(c, "wheat", 2)
    r1 = alchemy.taste(c, gd, "wheat")
    assert r1["revealed"] == "heal"                                  # JSON 首個,非 rng
    assert inventory.count_item(c, "wheat") == base + 1              # 消耗 1 份
    r2 = alchemy.taste(c, gd, "wheat")
    assert r2["revealed"] == "restore_fatigue"
    # 已嚐遍 → 不消耗材料(no-op:ok=False、revealed=None)→ 不浪費
    cnt_before = inventory.count_item(c, "wheat")
    r3 = alchemy.taste(c, gd, "wheat")
    assert r3["revealed"] is None and not r3["ok"]
    assert inventory.count_item(c, "wheat") == cnt_before           # 未消耗


def test_taste_without_ingredient_fails():
    gd, c = _char(0)
    # 清掉起始可能持有的小麥
    while inventory.count_item(c, "wheat") > 0:
        inventory.remove_item(c, "wheat", 1)
    r = alchemy.taste(c, gd, "wheat")
    assert not r["ok"] and r["revealed"] is None


# --- 煉製揭露 + brew 數學不變 ------------------------------------------
def test_brew_success_reveals_shared_and_math_unchanged():
    gd, c = _char(30)
    inventory.add_item(c, "wheat", 1); inventory.add_item(c, "blue_mountain_flower", 1)
    res = alchemy.brew(c, gd, "wheat", "blue_mountain_flower", RNG(0))
    assert res["ok"]
    # learn 列出本次用到的共有效果(heal)
    assert res["learn"]["wheat"] == ["heal"] and res["learn"]["blue_mountain_flower"] == ["heal"]
    # 數學不變:仍產出 heal 藥水
    assert gd.item(res["item_id"])["effect"]["type"] == "heal"


def test_brew_failure_reveals_nothing():
    gd, c = _char(30)
    inventory.add_item(c, "lavender", 1); inventory.add_item(c, "garlic", 1)   # 無共通效果
    res = alchemy.brew(c, gd, "lavender", "garlic", RNG(0))
    assert not res["ok"] and res["learn"] == {}


def test_reveal_only_real_kinds():
    gd, c = _char(0)
    assert not alchemy.reveal(c, gd, "wheat", "fear")    # wheat 沒有 fear → 不揭露
    assert alchemy.reveal(c, gd, "wheat", "heal")        # 真有 → 揭露
    assert not alchemy.reveal(c, gd, "wheat", "heal")    # 已知 → 回 False(非首次)


def test_generic_over_new_effect_kinds():
    """通用於 R30/R31 新效果 kind:嚐 deathbell 揭露其有害特殊 kind。"""
    gd, c = _char(0)
    c.known_effects = {}
    inventory.add_item(c, "deathbell", 1)
    r = alchemy.taste(c, gd, "deathbell")
    assert r["revealed"] in {e["kind"] for e in alchemy.ingredient_effects(gd, "deathbell")}


# --- 存檔相容 -----------------------------------------------------------
def test_save_roundtrip_and_old_save_migration():
    gd, c = _char(0)
    c.known_effects = {"wheat": ["heal"]}
    c2 = Character.from_dict(c.to_dict())
    assert c2.known_effects == {"wheat": ["heal"]}
    # 舊存檔缺欄 → 預設 {}
    d = c.to_dict(); d.pop("known_effects", None)
    c3 = Character.from_dict(d)
    assert c3.known_effects == {}


def test_ensure_prunes_bad_and_stale():
    gd, c = _char(0)
    c.known_effects = {"wheat": ["heal"], "BOGUS_ING": ["x"], "lavender": ["heal"]}  # lavender 無 heal
    alchemy.ensure_known_effects(c, gd)
    assert c.known_effects == {"wheat": ["heal"]}      # 陳舊 ing_id 清除、無效 kind 剔除
    c.known_effects = "garbage"                         # 壞型別
    alchemy.ensure_known_effects(c, gd)
    assert c.known_effects == {}


def run():
    test_auto_reveal_count_scales_with_skill()
    test_passive_reveal_floor_one_full_at_high_skill()
    test_taste_reveals_first_deterministic_and_consumes()
    test_taste_without_ingredient_fails()
    test_brew_success_reveals_shared_and_math_unchanged()
    test_brew_failure_reveals_nothing()
    test_reveal_only_real_kinds()
    test_generic_over_new_effect_kinds()
    test_save_roundtrip_and_old_save_migration()
    test_ensure_prunes_bad_and_stale()


if __name__ == "__main__":
    run()
    print("✓ test_alchemy_discovery")
