"""刺客流派強化的單元測試:暗殺殘響/combo、雙持匕首、隱遁再襲、偵查技能。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Creature
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic


def _assassin(sneak=70, blade=50, alchemy=40, weapon="iron_dagger"):
    gd = get_gamedata()
    c = build_character(gd, name="刺", sex="male", race="khajiit",
                        birthsign="shadow", class_id="assassin")
    c.skills["sneak"] = sneak
    c.skills["blade"] = blade
    c.skills["marksman"] = blade
    c.skills["alchemy"] = alchemy
    c.weapon = weapon
    return gd, c


def _dummy(hp=9999, armor=0, agility=40):
    return Creature(template_id="t", name="靶", strength=40, agility=agility, speed=40,
                    max_health=hp, health=hp, armor_rating=armor,
                    attack={"name": "揮擊", "damage": 10, "skill": 50})


def _sneak_until_nonlethal_hit(gd, c, target):
    """擲到一次『偷襲命中但沒殺死』的事件(偷襲命中率高,幾下內必中)。"""
    for i in range(40):
        target.health = target.max_health
        target.active_effects = []
        ev = combat.resolve_attack(c, target, gd, RNG(i), sneak_attack=True)
        if ev["hit"] and not ev["defender_dead"]:
            return ev
    raise AssertionError("偷襲始終沒有命中(命中下限應 >=0.9)")


# --- 暗殺殘響 -----------------------------------------------------------
def test_dagger_sneak_aftermath_staggers_and_bleeds():
    gd, c = _assassin(weapon="iron_dagger")
    target = _dummy()
    ev = _sneak_until_nonlethal_hit(gd, c, target)
    assert ev["aftermath"] and ev["aftermath"]["staggered"]
    assert ev["aftermath"]["bleed"] > 0
    assert magic.is_staggered(target)
    assert any(e["kind"] == "dot" and e.get("element") == "bleed" for e in target.active_effects)


def test_bow_sneak_only_staggers():
    gd, c = _assassin(weapon="hunting_bow")
    target = _dummy()
    ev = _sneak_until_nonlethal_hit(gd, c, target)
    assert ev["aftermath"]["staggered"] and ev["aftermath"]["bleed"] == 0
    assert magic.is_staggered(target)
    assert not any(e.get("element") == "bleed" for e in target.active_effects)


def test_sword_sneak_no_aftermath():
    gd, c = _assassin(weapon="iron_sword")
    target = _dummy()
    ev = _sneak_until_nonlethal_hit(gd, c, target)
    assert ev["aftermath"] is None
    assert not magic.is_staggered(target)


def test_lethal_sneak_applies_no_aftermath():
    gd, c = _assassin(sneak=100, blade=100, weapon="glass_dagger")
    target = _dummy(hp=5)               # 一定被秒
    ev = combat.resolve_attack(c, target, gd, RNG(1), sneak_attack=True)
    assert ev["defender_dead"] and ev["aftermath"] is None


def test_bleed_magnitude_scales_with_sneak_and_alchemy():
    from tesrpg import formulas
    lo = formulas.sneak_bleed_magnitude(0, 0)
    hi = formulas.sneak_bleed_magnitude(100, 80)
    assert hi > lo == formulas.SNEAK_BLEED_BASE


def test_bleed_ticks_unresisted():
    gd, c = _assassin(weapon="iron_dagger")
    target = _dummy(hp=9999)
    _sneak_until_nonlethal_hit(gd, c, target)
    before = target.health
    magic.tick_effects(target, gd)
    assert target.health < before       # 撕裂傷無視一般抗性,確實掉血


def test_staggered_enemy_hits_less_often():
    gd, c = _assassin()
    foe = _dummy(hp=200, agility=50)

    def hit_rate(staggered):
        hits = 0
        for i in range(500):
            c.health = c.max_health
            foe.active_effects = [{"kind": "stagger", "turns": 1}] if staggered else []
            if combat.resolve_attack(foe, c, gd, RNG(i + 1))["hit"]:
                hits += 1
        return hits / 500

    assert hit_rate(True) < hit_rate(False) - 0.15   # 踉蹌顯著降低敵人命中


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_assassin OK")
