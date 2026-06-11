"""角色創建的單元測試。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata


def test_build_warrior_nord():
    gd = get_gamedata()
    c = build_character(gd, name="Test", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    # 諾德 STR+10、戰士座 STR+5 → 40+15 = 55
    assert c.attr("strength") == 55
    # 諾德 END+10、戰士座 END+5 → 55
    assert c.attr("endurance") == 55
    # 主修技能起始 = 5 + 20(主修) + 5(戰鬥專精) + 種族加成
    assert c.is_major_skill("blade")
    assert c.skill("blade") == 5 + 20 + 5 + gd.races["nord"]["skill_bonuses"].get("blade", 0)
    # 衍生數值
    assert c.max_health == formulas.base_max_health(55)
    assert c.max_fatigue == c.attr("strength") + c.attr("willpower") + c.attr("agility") + c.attr("endurance")
    assert c.health == c.max_health and c.fatigue == c.max_fatigue


def test_magicka_bonus_altmer_mage_sign():
    gd = get_gamedata()
    c = build_character(gd, name="M", sex="female", race="altmer",
                        birthsign="mage", class_id="mage")
    # altmer +100、法師座 +50 → magicka_bonus 150
    assert c.magicka_bonus == 150
    assert c.max_magicka == c.attr("intelligence") * 2 + 150


def test_custom_class():
    gd = get_gamedata()
    custom = {"specialization": "stealth",
              "favored_attributes": ["agility", "speed"],
              "major_skills": ["sneak", "security", "marksman", "blade",
                               "light_armor", "acrobatics", "alchemy"]}
    c = build_character(gd, name="C", sex="male", race="khajiit",
                        birthsign="thief", class_id="custom", custom_class=custom)
    assert c.specialization == "stealth"
    assert c.is_major_skill("sneak")
    assert not c.is_major_skill("destruction")


def run():
    test_build_warrior_nord()
    test_magicka_bonus_altmer_mage_sign()
    test_custom_class()


if __name__ == "__main__":
    run()
    print("test_creation OK")
