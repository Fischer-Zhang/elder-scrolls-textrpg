"""R214 法術威力的屬性依學派:威力曲線(R67:≤50 中性 → 100 = +30%)不變,但吃哪個屬性由 skills.json 該技能的 `attr` 決定。

分配(使用者拍板):毀滅 / 召喚 = 智力、恢復 / 變化 / 神秘 = 意志、幻術 = 魅力。
原本 R67 把所有學派的威力都寫死吃智力 → 智力同時管魔力池與全部威力(平方級成長);改後施法者須在智力 / 意志之間分配,
法師(智力)與治療師(意志)自然分化。`attr` 成為單一來源:毀滅(原意志)與神秘(原智力)兩處不一致的資料已一併修正。

守衛:
  1. 分配釘死(六學派 attr)+ `magic.power_attribute` 讀它
  2. `_power` 真的跟著學派的屬性走:只拉高該學派的屬性 → 威力 ×1.30;拉高別的屬性 → 不動(R214 前舊規則:全看智力)
  3. ≤50 中性(起手期不受影響)
  4. 戰法師偏好 力量 / 意志(起手法術全是意志系)
  5. 六學派 `mechanic` 文字須點名威力屬性(文字與資料同步)
"""
from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import magic

_EXPECT = {"destruction": "intelligence", "restoration": "willpower", "alteration": "willpower",
           "illusion": "personality", "conjuration": "intelligence", "mysticism": "willpower"}
_CN = {"intelligence": "智力", "willpower": "意志", "personality": "魅力"}
_ATTRS = ("intelligence", "willpower", "personality")


def _mage(gd, **attrs):
    c = build_character(gd, name="M", sex="male", race="imperial", birthsign="shadow", class_id="mage")
    for a in _ATTRS:
        c.attributes[a] = attrs.get(a, 40)
    for s in _EXPECT:
        c.skills[s] = 60                      # 技能同為 60:差異只來自屬性
    return c


def test_power_attribute_mapping_pinned():
    gd = get_gamedata()
    for school, attr in _EXPECT.items():
        assert gd.skills[school]["attr"] == attr, school
        assert magic.power_attribute(gd, school) == attr, school
    assert magic.power_attribute(None, "restoration") == "intelligence"      # gamedata 缺 → 舊行為


def test_power_follows_the_schools_own_attribute():
    gd = get_gamedata()
    ratio = formulas.intelligence_spell_potency(100) / formulas.intelligence_spell_potency(40)   # 1.30
    for school, attr in _EXPECT.items():
        base = magic._power(_mage(gd), gd, school)
        mine = magic._power(_mage(gd, **{attr: 100}), gd, school)
        assert abs(mine / base - ratio) < 1e-9, f"{school} 應吃 {attr}:{mine / base:.3f}"
        for other in _ATTRS:
            if other != attr:                                                  # 拉高別的屬性 → 威力不動
                assert magic._power(_mage(gd, **{other: 100}), gd, school) == base, f"{school} 不該吃 {other}"


def test_old_rule_intelligence_no_longer_boosts_will_schools():
    gd = get_gamedata()
    c = _mage(gd, intelligence=100, willpower=40)
    base = 0.7 + 60 / 150.0
    for school in ("restoration", "alteration", "mysticism"):
        assert abs(magic._power(c, gd, school) - base) < 1e-9, f"{school} 不該再被智力放大"
    for school in ("destruction", "conjuration"):
        assert abs(magic._power(c, gd, school) - base * 1.30) < 1e-9, school
    c = _mage(gd, intelligence=40, willpower=100)
    assert abs(magic._power(c, gd, "restoration") - base * 1.30) < 1e-9
    assert abs(magic._power(c, gd, "destruction") - base) < 1e-9                  # 意志不放大毀滅


def test_neutral_at_or_below_50_so_early_game_is_unchanged():
    gd = get_gamedata()
    c = _mage(gd, intelligence=50, willpower=50, personality=50)
    for school in _EXPECT:
        assert abs(magic._power(c, gd, school) - (0.7 + 60 / 150.0)) < 1e-9, school


def test_battlemage_favors_strength_willpower():
    gd = get_gamedata()
    assert gd.classes["battlemage"]["favored_attributes"] == ["strength", "willpower"]
    bm = build_character(gd, name="B", sex="male", race="imperial", birthsign="shadow", class_id="battlemage")
    wr = build_character(gd, name="W", sex="male", race="imperial", birthsign="shadow", class_id="warrior")   # 偏好力量 / 耐力
    assert bm.attributes["intelligence"] == wr.attributes["intelligence"]               # 智力不再有偏好加值
    assert bm.attributes["willpower"] == wr.attributes["willpower"] + formulas.FAVORED_ATTR_BONUS
    # 起手法術全是意志系(焰刃術 / 橡木膚 / 次級治療 / 凝神)→ 與偏好意志對齊
    assert {gd.spells[s]["school"] for s in bm.spells} <= {"alteration", "restoration", "mysticism"}


def test_skill_mechanic_text_names_the_power_attribute():
    gd = get_gamedata()
    for school, attr in _EXPECT.items():
        assert _CN[attr] in gd.skills[school]["mechanic"], f"{school} 的機制說明須點名威力屬性 {_CN[attr]}"


def test_level_up_attribute_text_names_the_schools_whose_power_it_drives():
    """審查補洞(R216):升級配點選單(formulas.ATTRIBUTE_FUNCTION)原本看不到「智力 vs 意志」的法術威力取捨(R214 只改了
    學派說明與 codex)。文字須點名「威力吃該屬性的學派」——學派清單由 _EXPECT(= skills.json attr)導出,不另寫死;
    非施法屬性不得混進「法術威力」。"""
    gd = get_gamedata()
    for attr in _ATTRS:
        text = formulas.ATTRIBUTE_FUNCTION[attr]
        assert "法術威力" in text, attr
        for school in (s for s, a in _EXPECT.items() if a == attr):
            assert gd.skills[school]["name"] in text, f"{attr} 的配點說明須點名 {gd.skills[school]['name']}"
    for attr in ("strength", "agility", "speed", "endurance", "luck"):
        assert "法術威力" not in formulas.ATTRIBUTE_FUNCTION[attr], attr


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_spell_power_attr_r214 OK")
