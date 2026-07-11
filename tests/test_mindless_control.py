"""R140 現實邏輯:心智控場(恐懼/安撫/馭獸)對無心智者無效 —— 白骨/傀儡/機關/元素嚇不動也安撫不了;
聖光驅散(divine)旁路照常斥退不死;物理性控場(踉蹌/麻痺/遲緩)不受影響。"""

from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic, powers

gd = get_gamedata()


def test_fear_and_calm_blocked_on_mindless():
    for cid in ("skeleton", "gargoyle", "dwarven_centurion", "storm_atronach", "knight_of_order"):
        e = combat.spawn_creature(gd, cid, RNG(1))
        assert magic.apply_control(e, "fear", gd, RNG(2)) == "resisted", cid
        assert magic.apply_control(e, "calm", gd, RNG(3)) == "resisted", cid
        assert magic.apply_control(e, "frenzied", gd, RNG(4)) == "resisted", cid   # R152 狂亂=心智控場,劫持不了無心智者
        assert not e.active_effects, cid


def test_physical_control_still_lands_on_mindless():
    e = combat.spawn_creature(gd, "skeleton", RNG(1))
    assert magic.apply_control(e, "stagger", gd, RNG(2)) == "applied"     # 震得動骨架
    assert magic.apply_control(e, "slow", gd, RNG(3), magnitude=0.3) == "applied"
    e2 = combat.spawn_creature(gd, "gargoyle", RNG(1))
    assert magic.apply_control(e2, "paralyze", gd, RNG(4)) == "applied"   # 物理性禁錮非心智


def test_minded_creatures_still_fearable():
    for cid in ("wolf", "bandit", "draugr", "lich", "imperial_ghost"):
        e = combat.spawn_creature(gd, cid, RNG(1))
        results = {magic.apply_control(combat.spawn_creature(gd, cid, RNG(s)), "fear", gd, RNG(s * 7))
                   for s in range(12)}
        assert "applied" in results, cid    # 有心智者仍可懼(solo/機率抗性另計)


def test_turn_undead_divine_bypass():
    e = combat.spawn_creature(gd, "skeleton", RNG(1))
    assert magic.apply_control(e, "fear", gd, RNG(2)) == "resisted"                 # 一般恐懼嚇不動白骨
    assert magic.apply_control(e, "fear", gd, RNG(2), divine=True) == "applied"     # 聖光驅散照樣斥退
    assert any(x.get("kind") == "fear" for x in e.active_effects)


def test_command_beast_excludes_constructs_and_undead():
    wolf = combat.spawn_creature(gd, "wolf", RNG(1))
    spider = combat.spawn_creature(gd, "dwarven_spider", RNG(2))
    skel = combat.spawn_creature(gd, "skeleton", RNG(3))
    assert powers._control_class_ok(wolf, gd, "beast")
    assert not powers._control_class_ok(spider, gd, "beast")    # 蒸汽傀儡聽不懂森林語
    assert not powers._control_class_ok(skel, gd, "beast")      # 白骨非野獸
    bandit = combat.spawn_creature(gd, "bandit", RNG(4))
    assert powers._control_class_ok(bandit, gd, "humanoid")     # 人形閘不變


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
