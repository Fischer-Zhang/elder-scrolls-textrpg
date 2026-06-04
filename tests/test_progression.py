"""技能成長(learn-by-doing)與升級(混合 Skyrim 式)的單元測試。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import progression


def _fresh_warrior():
    gd = get_gamedata()
    c = build_character(gd, name="T", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    return gd, c


# --- 技能成長(learn-by-doing,未改動) ---------------------------------
def test_skill_increases_with_xp():
    gd, c = _fresh_warrior()
    start = c.skill("blade")
    need = formulas.skill_threshold(start)
    events = progression.use_skill(c, gd, "blade", need)  # 剛好夠升 1 點
    assert c.skill("blade") == start + 1
    assert any(e["type"] == "skill_up" for e in events)


def test_threshold_grows_with_level():
    assert formulas.skill_threshold(0) < formulas.skill_threshold(50) < formulas.skill_threshold(99)


def test_skill_capped_at_100():
    gd, c = _fresh_warrior()
    c.skills["blade"] = 99
    progression.use_skill(c, gd, "blade", 9999.0)
    assert c.skill("blade") == 100
    assert c.skill_xp["blade"] == 0.0


# --- 等級 XP 池 ---------------------------------------------------------
def test_every_skillup_feeds_level_xp_major_weighted():
    gd, c = _fresh_warrior()
    assert c.is_major_skill("blade") and not c.is_major_skill("destruction")
    # 主修技能升 1 點 → +MAJOR_SKILL_XP_MULT
    before = c.level_xp
    progression.use_skill(c, gd, "blade", formulas.skill_threshold(c.skill("blade")))
    assert c.level_xp == before + formulas.MAJOR_SKILL_XP_MULT
    # 非主修技能升 1 點 → +1.0(仍計入,無 major-only 套利)
    before = c.level_xp
    progression.use_skill(c, gd, "destruction", formulas.skill_threshold(c.skill("destruction")))
    assert c.level_xp == before + 1.0


def test_can_level_up_at_threshold():
    gd, c = _fresh_warrior()
    assert not c.can_level_up()
    fired_ready = False
    for _ in range(200):
        evs = progression.use_skill(c, gd, "blade", 50.0)
        if any(e["type"] == "level_ready" for e in evs):
            fired_ready = True
        if c.can_level_up():
            break
    assert c.can_level_up() and fired_ready
    assert c.level_xp >= formulas.levelup_xp_threshold(c.level)


# --- 升級給予:屬性點自由分配 + 資源三選一 -----------------------------
def _level_to_ready(gd, c):
    for _ in range(400):
        progression.use_skill(c, gd, "blade", 50.0)
        if c.can_level_up():
            return
    raise AssertionError("未能累積到可升級")


def test_apply_level_up_allocates_attributes_and_resource():
    gd, c = _fresh_warrior()
    _level_to_ready(gd, c)
    str0, end0, luck0 = c.attr("strength"), c.attr("endurance"), c.attr("luck")
    hp0 = c.max_health
    lvl0, xp0 = c.level, c.level_xp
    thresh = formulas.levelup_xp_threshold(lvl0)

    summary = progression.apply_level_up(
        c, gd, {"strength": 2, "endurance": 1, "luck": 1}, "health")

    assert c.level == lvl0 + 1
    assert c.attr("strength") == str0 + 2
    assert c.attr("endurance") == end0 + 1
    assert c.attr("luck") == luck0 + 1          # Luck 不再是死屬性:可自由加點
    assert summary["attr_gains"] == {"strength": 2, "endurance": 1, "luck": 1}
    assert summary["resource_choice"] == "health"
    assert summary["resource_gain"] == formulas.LEVELUP_RESOURCE_GAIN["health"]
    assert c.max_health == hp0 + formulas.LEVELUP_RESOURCE_GAIN["health"]
    assert c.level_xp == xp0 - thresh           # 保留溢出
    assert c.health == c.max_health and c.fatigue == c.max_fatigue   # 升級回滿


def test_resource_choice_magicka_and_fatigue():
    gd, c = _fresh_warrior()
    _level_to_ready(gd, c)
    mp0 = c.max_magicka
    progression.apply_level_up(c, gd, {"intelligence": 4}, "magicka")
    # 魔力上限 = 智力×2 + magicka_bonus + resource_levels[magicka]
    assert c.max_magicka == mp0 + 4 * 2 + formulas.LEVELUP_RESOURCE_GAIN["magicka"]


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_progression OK")
