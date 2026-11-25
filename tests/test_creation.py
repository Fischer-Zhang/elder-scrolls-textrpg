"""角色創建的單元測試。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata


def test_build_warrior_nord():
    gd = get_gamedata()
    c = build_character(gd, name="Test", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    # 諾德 STR+10、戰士座 STR+5、戰士偏好 strength +5 → 40+20 = 60
    assert c.attr("strength") == 60
    # 諾德 END+10、戰士座 END+5、戰士偏好 endurance +5 → 60
    assert c.attr("endurance") == 60
    # 主修技能起始 = 5 + 20(主修) + 5(戰鬥專精) + 種族加成
    assert c.is_major_skill("blade")
    assert c.skill("blade") == 5 + 20 + 5 + gd.races["nord"]["skill_bonuses"].get("blade", 0)
    # 衍生數值
    assert c.max_health == formulas.base_max_health(60)
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


def test_favored_attributes_give_creation_bonus():
    """職業偏好屬性創角 +5(正典);非偏好不加。同種族/星座下,只差職業偏好的屬性差 5。"""
    gd = get_gamedata()
    w = build_character(gd, name="W", sex="male", race="imperial", birthsign="lady", class_id="warrior")  # 偏好 str/end
    m = build_character(gd, name="M", sex="male", race="imperial", birthsign="lady", class_id="mage")       # 偏好 int/wil
    b = formulas.FAVORED_ATTR_BONUS
    assert w.attributes["strength"] == m.attributes["strength"] + b
    assert w.attributes["endurance"] == m.attributes["endurance"] + b
    assert m.attributes["intelligence"] == w.attributes["intelligence"] + b
    assert m.attributes["willpower"] == w.attributes["willpower"] + b
    assert w.attributes["agility"] == m.attributes["agility"]   # 非偏好 → 相同


def test_create_character_back_and_review():
    """逐步返回 + 總覽改項:create_character 可退上一步重選,並在總覽逐項改後才確認生成。"""
    from tesrpg import main as M
    from tesrpg.rng import RNG
    from tesrpg.ui import console as ui
    gd = get_gamedata()
    calls = {}
    seqs = {
        "性別": iter(["male", "male"]),
        "種族": iter(["khajiit", "nord", "orsimer"]),   # 初選 → 星座返回後重選 → 總覽改種族
        "出生星座": iter([None, "warrior"]),            # 返回上一步 → 再選
        "開局背景": iter(["⚔ 戰士 · 近戰"]),
        "職業": iter(["warrior"]),
        "確認開局": iter(["race", "confirm"]),          # 總覽改種族一次 → 確認
    }

    def key_of(title):
        return next((k for k in seqs if title.startswith(k)), None)

    def fake_menu(title, options, allow_back=False):
        k = key_of(title)
        calls[k] = calls.get(k, 0) + 1
        return next(seqs[k])

    orig = (ui.confirm, ui.menu, ui.ask_text, ui.origin_picker)
    ui.confirm = lambda *a, **k: False                  # 不走快速開始
    ui.menu = fake_menu
    ui.ask_text = lambda *a, **k: "Hero"
    ui.origin_picker = lambda _gd, _oids: "sellsword"
    try:
        char = M.create_character(gd, RNG(1))
    finally:
        ui.confirm, ui.menu, ui.ask_text, ui.origin_picker = orig

    assert char.race == "orsimer"          # 總覽改種族生效(khajiit→nord→orsimer 最終)
    assert char.birthsign == "warrior"
    assert char.name == "Hero"
    assert char.origin == "sellsword"
    assert calls["種族"] == 3              # 初選 + 星座返回重選 + 總覽改 → 證「逐步返回 + 總覽改」
    assert calls["出生星座"] == 2          # None(返回)+ warrior
    assert calls["確認開局"] == 2          # 改項 + 確認


# --- R208 起手包定位:弓手潛行系 + 職業固定起手武器 -------------------------------

def _mk(gd, race, class_id):
    return build_character(gd, name="T", sex="male", race=race, birthsign="shadow", class_id=class_id)


def test_class_fixed_starting_weapon_ignores_race_ties():
    """職業寫了 starting_weapon 就固定給(刺客/盜賊=匕首·弓手=獵弓·四個純施法=學徒法杖),
    全種族皆然——不再因種族刀劍加成平手而退回鐵劍(R208 前:同分取 blade)。"""
    from tesrpg.systems import inventory
    gd = get_gamedata()
    expect = {"assassin": "iron_dagger", "thief": "iron_dagger", "archer": "hunting_bow",
              "mage": "apprentice_staff", "healer": "apprentice_staff",
              "conjurer": "apprentice_staff", "necromancer": "apprentice_staff"}
    for cid, wid in expect.items():
        assert gd.classes[cid].get("starting_weapon") == wid
        for race in gd.races:
            c = _mk(gd, race, cid)
            assert c.weapon == wid, f"{cid}/{race} 起手武器應為 {wid},實得 {c.weapon}"
            assert inventory.count_item(c, wid) >= 1, f"{cid}/{race} 起手武器應在背包"


def test_starting_weapon_data_valid_and_caster_staff_is_plain():
    """守衛:starting_weapon 必指向存在的武器;凡「無任何武器系主修」的純施法職業一定要寫(否則回到
    『全技能同分 → 鐵劍』);學徒法杖不帶附魔/施法焦點/命中回魔(只改身分,不改起手戰力與施法強度)。"""
    from tesrpg.creation import _is_caster_weapon
    from tesrpg.systems import inventory
    gd = get_gamedata()
    for cid, cdef in gd.classes.items():
        wid = cdef.get("starting_weapon")
        pure_caster = not any(s in cdef["major_skills"] for s in formulas.WEAPON_SKILL_IDS)
        if pure_caster:
            assert wid, f"純施法職業 {cid} 必須指定 starting_weapon"
            assert _is_caster_weapon(gd, wid), f"{cid} 的起手武器應為施法武器"
        if wid:
            assert wid in gd.weapons, f"{cid} 的 starting_weapon {wid} 不存在"
    st = gd.weapons["apprentice_staff"]
    assert st["archetype"] == "staff"
    assert not {"enchant", "spell_focus", "on_hit_self"} & set(st), "學徒法杖須為素杖"
    assert inventory.staff_spell_focus(_mk(gd, "altmer", "mage"), gd) == {}   # 無焦點 → 施法強度不變


def test_archer_is_stealth_spec_core_skills_get_spec_bonus():
    """弓手專精=潛行系(R208):射術/潛行/輕甲 = 5 + 20 主修 + 5 專精 + 種族加成;刀劍(戰鬥系)不再有專精加成。"""
    gd = get_gamedata()
    c = _mk(gd, "imperial", "archer")
    sb = gd.races["imperial"].get("skill_bonuses", {})
    assert gd.classes["archer"]["spec"] == "stealth" and c.specialization == "stealth"
    for sid in ("marksman", "sneak", "light_armor"):
        assert c.skill(sid) == 5 + 20 + 5 + sb.get(sid, 0), sid
    assert c.skill("blade") == 5 + 20 + sb.get("blade", 0)


def test_classes_without_fixed_weapon_keep_skill_rule():
    """沒寫 starting_weapon 的職業(戰士/騎士/戰法師/斥候)與自訂職業維持舊的『最高武器技能』規則。"""
    from tesrpg.creation import _starting_weapon
    gd = get_gamedata()
    for cid in ("warrior", "knight", "battlemage", "scout"):
        assert "starting_weapon" not in gd.classes[cid]
        for race in ("imperial", "nord", "khajiit"):
            c = _mk(gd, race, cid)
            assert c.weapon == _starting_weapon(gd, c.skills), f"{cid}/{race}"
    custom = {"specialization": "magic", "favored_attributes": ["intelligence", "willpower"],
              "major_skills": ["destruction", "restoration", "alteration", "conjuration",
                               "illusion", "mysticism", "alchemy"]}
    c = build_character(gd, name="C", sex="male", race="imperial", birthsign="shadow",
                        class_id="custom", custom_class=custom)
    assert c.weapon == _starting_weapon(gd, c.skills)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_creation OK")
