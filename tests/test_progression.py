"""learn-by-doing 技能成長與升級的單元測試。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import progression


def _fresh_warrior():
    gd = get_gamedata()
    c = build_character(gd, name="T", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_skill_increases_with_xp():
    gd, c = _fresh_warrior()
    start = c.skill("blade")
    need = formulas.skill_threshold(start)
    events = progression.use_skill(c, gd, "blade", need)  # 剛好夠升 1 點
    assert c.skill("blade") == start + 1
    assert any(e["type"] == "skill_up" for e in events)


def test_threshold_grows_with_level():
    assert formulas.skill_threshold(0) < formulas.skill_threshold(50) < formulas.skill_threshold(99)


def test_major_skill_advances_level_progress():
    gd, c = _fresh_warrior()
    assert c.is_major_skill("blade")
    before = c.level_progress
    progression.use_skill(c, gd, "blade", formulas.skill_threshold(c.skill("blade")))
    assert c.level_progress == before + 1


def test_minor_skill_no_level_progress_but_tracks_attr():
    gd, c = _fresh_warrior()
    assert not c.is_major_skill("destruction")  # 戰士無毀滅主修
    before = c.level_progress
    gov = gd.skill_attr("destruction")  # willpower
    progression.use_skill(c, gd, "destruction", formulas.skill_threshold(c.skill("destruction")))
    assert c.level_progress == before          # 非主修不推進升級
    assert c.level_skillups.get(gov, 0) == 1   # 但仍計入屬性升點


def test_level_up_flow_and_attribute_bonus():
    gd, c = _fresh_warrior()
    # 把 blade 灌到升 10 點 → 可升級
    fired_ready = False
    for _ in range(200):
        evs = progression.use_skill(c, gd, "blade", 50.0)
        if any(e["type"] == "level_ready" for e in evs):
            fired_ready = True
        if c.can_level_up():
            break
    assert c.can_level_up() and fired_ready

    # blade 由 strength 主導,本級大量升點 → strength 預覽應 > +1
    preview = progression.preview_levelup(c)
    assert preview["strength"] >= 2

    str_before = c.attr("strength")
    lvl_before = c.level
    summary = progression.apply_level_up(c, gd, ["strength", "endurance", "luck"])
    assert c.level == lvl_before + 1
    assert c.attr("strength") == str_before + summary["attr_gains"]["strength"]
    assert summary["attr_gains"]["strength"] >= 2
    assert "luck" in summary["attr_gains"]            # 幸運至少 +1
    assert c.level_skillups == {}                      # 升級後歸零
    # 升級回滿
    assert c.health == c.max_health and c.fatigue == c.max_fatigue


def test_skill_capped_at_100():
    gd, c = _fresh_warrior()
    c.skills["blade"] = 99
    progression.use_skill(c, gd, "blade", 9999.0)
    assert c.skill("blade") == 100
    assert c.skill_xp["blade"] == 0.0


def run():
    test_skill_increases_with_xp()
    test_threshold_grows_with_level()
    test_major_skill_advances_level_progress()
    test_minor_skill_no_level_progress_but_tracks_attr()
    test_level_up_flow_and_attribute_bonus()
    test_skill_capped_at_100()


if __name__ == "__main__":
    run()
    print("test_progression OK")
