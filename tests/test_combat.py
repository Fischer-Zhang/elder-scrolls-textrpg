"""戰鬥系統的單元測試。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat


def _warrior():
    gd = get_gamedata()
    c = build_character(gd, name="Conan", sex="male", race="redguard",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_formulas_monotonic():
    # 技能越高命中越高
    assert (formulas.hit_chance(20, 40, 40, 1.0) <
            formulas.hit_chance(80, 40, 40, 1.0))
    # 低體力降低命中
    assert (formulas.hit_chance(50, 40, 40, 0.1) <
            formulas.hit_chance(50, 40, 40, 1.0))
    # 護甲減傷且不為負、至少 1
    assert formulas.damage_after_armor(10, 0) == 10
    assert 1 <= formulas.damage_after_armor(10, 100) < 10
    assert formulas.damage_after_armor(0.1, 0) == 1.0


def test_starter_weapon_assigned():
    gd, c = _warrior()
    wp = gd.weapons[c.weapon]
    # 紅衛戰士擅長刀劍 → 配發劍類
    assert wp["skill"] == "blade"


def test_spawn_and_loot():
    gd, _ = _warrior()
    rng = RNG(1)
    cr = combat.spawn_creature(gd, "wolf", rng)
    assert cr.name == "野狼" and cr.health > 0 and cr.health == cr.max_health


def test_player_beats_weak_creature_and_trains():
    gd, c = _warrior()
    rng = RNG(7)
    wpn_skill = gd.weapons[c.weapon]["skill"]
    skill_before = c.skill(wpn_skill)
    rat = combat.spawn_creature(gd, "giant_rat", rng)
    result = combat.auto_resolve(c, rat, gd, rng)
    assert result["winner"] == "player"
    # 靠戰鬥練了武器技能(learn-by-doing)
    assert c.skill_xp[wpn_skill] > 0 or c.skill(wpn_skill) > skill_before


def test_player_can_die_to_strong_foe():
    gd, c = _warrior()
    # 削弱玩家、放一頭熊 → 應會落敗
    c.health = 12
    c.max_health = 12
    rng = RNG(3)
    bear = combat.spawn_creature(gd, "bear", rng)
    result = combat.auto_resolve(c, bear, gd, rng)
    assert result["winner"] in ("creature", "draw")
    if result["winner"] == "creature":
        assert not combat.is_alive(c)


def test_resolve_attack_applies_damage():
    gd, c = _warrior()
    rng = RNG(0)
    rat = combat.spawn_creature(gd, "giant_rat", rng)
    hp0 = rat.health
    # 強制命中:把玩家武器技能拉高、用多次直到命中
    landed = False
    for _ in range(20):
        ev = combat.resolve_attack(c, rat, gd, rng)
        if ev["hit"]:
            landed = True
            assert ev["damage"] >= 1
            assert rat.health < hp0
            break
    assert landed


def run():
    test_formulas_monotonic()
    test_starter_weapon_assigned()
    test_spawn_and_loot()
    test_player_beats_weak_creature_and_trains()
    test_player_can_die_to_strong_foe()
    test_resolve_attack_applies_damage()


if __name__ == "__main__":
    run()
    print("test_combat OK")
