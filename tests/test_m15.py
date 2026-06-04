"""M15:升級系統改版(混合 Skyrim 式)的回歸不變量。

鎖死這次改版要消滅的三個結構性缺陷:
  ① 屬性倍率 min-max → 升級每級至多給 LEVELUP_ATTRIBUTE_POINTS 點,與練功序列無關。
  ② 耐力時機陷阱 → max_health 與耐力完全解耦(只由創建基底 + 升級「生命」選擇決定)。
  ③ Luck 死屬性 → 可自由加點(已在 test_progression 覆蓋)。
另含:舊存檔(level_progress→level_xp)遷移、缺新欄位的舊存檔可載入。
"""

import json

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.systems import progression, stats

gd = get_gamedata()


def _ready_warrior():
    c = build_character(gd, name="T", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    for _ in range(400):
        progression.use_skill(c, gd, "blade", 50.0)
        if c.can_level_up():
            return c
    raise AssertionError("未能累積到可升級")


# ① min-max 已死:升級給的屬性點有硬上限,囤積無意義 ----------------------
def test_no_minmax_attribute_points_capped():
    c = _ready_warrior()
    total0 = sum(c.attr(a) for a in formulas.ATTRIBUTES)
    # 試圖一次塞 10 點到單屬性 → 只會套用 LEVELUP_ATTRIBUTE_POINTS 點
    progression.apply_level_up(c, gd, {"strength": 10}, "health")
    total1 = sum(c.attr(a) for a in formulas.ATTRIBUTES)
    assert total1 - total0 == formulas.LEVELUP_ATTRIBUTE_POINTS


def test_no_minmax_spread_also_capped():
    c = _ready_warrior()
    total0 = sum(c.attr(a) for a in formulas.ATTRIBUTES)
    # 分散塞 3+3+3=9 點 → 仍只套用 4 點上限
    progression.apply_level_up(c, gd, {"strength": 3, "agility": 3, "luck": 3}, "fatigue")
    total1 = sum(c.attr(a) for a in formulas.ATTRIBUTES)
    assert total1 - total0 == formulas.LEVELUP_ATTRIBUTE_POINTS


# ② 耐力時機陷阱已死:max_health 與耐力完全解耦 -------------------------
def test_health_decoupled_from_endurance():
    c = build_character(gd, name="T", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    hp0, fat0 = c.max_health, c.max_fatigue
    base0 = c.base_max_health
    # 把耐力拉高 20 → max_health 不動(只影響 max_fatigue 與創建已定的基底)
    c.attributes["endurance"] = c.attr("endurance") + 20
    stats.recompute_max_resources(c, gd)
    assert c.max_health == hp0, "生命上限不應隨耐力改變(時機陷阱已消除)"
    assert c.base_max_health == base0, "base_max_health 不隨耐力變動"
    assert c.max_fatigue == fat0 + 20, "耐力仍計入體力上限"


def test_levelup_endurance_does_not_inflate_base_health():
    c = _ready_warrior()
    base0 = c.base_max_health
    # 升級時把點全投耐力 + 選「魔力」資源 → 生命基底與生命上限都不該因耐力而漲
    hp0 = c.max_health
    progression.apply_level_up(c, gd, {"endurance": 4}, "magicka")
    assert c.base_max_health == base0
    assert c.max_health == hp0, "未選生命 + 只加耐力 → 生命上限不變"


# ③ + 存檔:遷移與向後相容 ----------------------------------------------
def test_legacy_save_level_progress_migrates():
    c = build_character(gd, name="T", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    d = c.to_dict()
    # 模擬「改版前」存檔:有 level_progress 進度、無 level_xp/resource_levels
    d["level_progress"] = 7
    del d["level_xp"]
    del d["resource_levels"]
    old = Character.from_dict(d)
    assert old.level_xp == 0.0 and old.level_progress == 7   # 載入:預設 + 舊欄位
    progression.ensure_level_xp(old)
    assert old.level_xp == 7.0 and old.level_progress == 0   # 遷移:進度不浪費、不重複


def test_legacy_save_without_new_fields_loads_and_recomputes():
    c = build_character(gd, name="T", sex="female", race="breton",
                        birthsign="mage", class_id="mage", rng=None)
    d = c.to_dict()
    del d["level_xp"]
    del d["resource_levels"]
    old = Character.from_dict(json.loads(json.dumps(d)))
    assert old.resource_levels == {} and old.level_xp == 0.0
    stats.recompute_max_resources(old, gd)   # 不崩,且上限合理
    assert old.max_health > 0 and old.max_magicka > 0


# --- 對抗式審查抓到的回歸:載入即遷移、觸頂不吞點 -----------------------
def test_load_migrates_so_levelup_visible_immediately():
    """改版前『已可升級』的存檔,載入當下 can_level_up 就要為 True(升級入口不被隱藏)。"""
    from tesrpg.rng import RNG
    from tesrpg.state import GameState
    c = build_character(gd, name="T", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    d = GameState(player=c, rng=RNG(seed=1), game_mode="adventure").to_dict()
    d["player"]["level_progress"] = 15          # 改版前殘餘進度(>= 門檻 12)
    del d["player"]["level_xp"]
    del d["player"]["resource_levels"]
    loaded = GameState.from_dict(d)
    assert loaded.player.level_xp == 15.0
    assert loaded.player.level_progress == 0
    assert loaded.player.can_level_up(), "載入後升級入口應立即可見,而非等到下次 use_skill"


def test_apply_level_up_capped_attribute_does_not_waste_points():
    """屬性觸頂時,剩餘點數應流給其它屬性,不可憑空吞掉(spent 以實際套用計帳)。"""
    c = _ready_warrior()
    c.attributes["strength"] = 99               # 距上限 1
    agi0 = c.attr("agility")
    total0 = sum(c.attr(a) for a in formulas.ATTRIBUTES)
    progression.apply_level_up(c, gd, {"strength": 3, "agility": 3}, "health")
    total1 = sum(c.attr(a) for a in formulas.ATTRIBUTES)
    assert c.attr("strength") == 100
    assert total1 - total0 == formulas.LEVELUP_ATTRIBUTE_POINTS, "觸頂不應浪費升級點"
    assert c.attr("agility") == agi0 + 3        # 力量只吃 1 點,其餘 3 點流給敏捷


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m15 OK")
