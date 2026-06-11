"""裝備擴展 B+D:武器流派差異化(速度/破甲/潛襲)+ 法師法杖。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat


def _setup():
    gd = get_gamedata()
    p = build_character(gd, name="戰", sex="male", race="orsimer",
                        birthsign="warrior", class_id="warrior")
    return gd, p


# --- B 資料完整性 -------------------------------------------------------
def test_all_weapons_have_archetype_and_speed():
    gd, _ = _setup()
    for wid, w in gd.weapons.items():
        assert "archetype" in w and "speed" in w, wid


# --- B 速度:命中與體力(公式層 + 效果層雙覆蓋) --------------------------
def test_fast_weapon_costs_less_fatigue():
    # 公式層:命中修正(快正慢負)+ 體力係數(慢>快)
    assert formulas.weapon_speed_hit(1.4) > 0 > formulas.weapon_speed_hit(0.75)
    assert formulas.weapon_attack_fatigue_factor(0.75) > formulas.weapon_attack_fatigue_factor(1.4)
    # 效果層:player_attack_cost 慢重武器更耗體力
    gd, p = _setup()
    p.skills["athletics"] = 0
    p.weapon = "iron_dagger"; p.fatigue = p.max_fatigue
    combat.player_attack_cost(p, gd)
    fast = p.max_fatigue - p.fatigue
    p.weapon = "iron_mace"; p.fatigue = p.max_fatigue
    combat.player_attack_cost(p, gd)
    slow = p.max_fatigue - p.fatigue
    assert slow > fast                      # 慢重武器更耗體力


# --- B 鈍器破甲 ---------------------------------------------------------
def test_blunt_penetrates_armor():
    raw, armor = 30.0, 50
    sword = formulas.damage_after_armor(raw, armor, formulas.archetype_armor_pen("sword"))
    blunt = formulas.damage_after_armor(raw, armor, formulas.archetype_armor_pen("blunt"))
    assert blunt > sword                    # 破甲 → 對有甲目標打更多
    assert formulas.archetype_armor_pen("blunt") == 0.30
    assert formulas.archetype_armor_pen("sword") == 0.0


# --- B 匕首/弓 潛襲加成 -------------------------------------------------
def test_dagger_and_bow_sneak_bonus():
    assert formulas.archetype_sneak_bonus("dagger") > 1.0
    assert formulas.archetype_sneak_bonus("bow") > 1.0
    assert formulas.archetype_sneak_bonus("sword") == 1.0
    # 透過 resolve_attack:同潛行技能,匕首偷襲倍率 > 長劍
    gd, p = _setup()
    p.skills["sneak"] = 60
    p.weapon = "iron_dagger"
    foe = combat.spawn_creature(gd, "wolf", RNG(0))
    ev_d = combat.resolve_attack(p, foe, gd, RNG(1), sneak_attack=True)
    p.weapon = "iron_sword"
    foe2 = combat.spawn_creature(gd, "wolf", RNG(0))
    ev_s = combat.resolve_attack(p, foe2, gd, RNG(1), sneak_attack=True)
    assert ev_d["sneak"] > ev_s["sneak"]


# --- D 法杖 -------------------------------------------------------------
def test_staves_are_magic_weapons():
    gd, _ = _setup()
    for sid in ("flame_staff", "frost_staff", "storm_staff", "magicka_staff"):
        w = gd.weapons[sid]
        assert w["archetype"] == "staff"
        assert w["skill"] in ("destruction", "mysticism")
    assert gd.weapons["flame_staff"]["enchant"]["element"] == "fire"


def test_element_staff_adds_elemental_damage():
    """烈焰法杖命中 → 比同物理基礎的法力法杖多打(額外火焰傷害)。"""
    gd, p = _setup()
    p.skills["destruction"] = 80
    p.skills["mysticism"] = 80
    for seed in range(80):
        f1 = combat.spawn_creature(gd, "skeleton", RNG(0))
        f2 = combat.spawn_creature(gd, "skeleton", RNG(0))
        p.weapon = "flame_staff"
        e1 = combat.resolve_attack(p, f1, gd, RNG(seed))
        p.weapon = "magicka_staff"
        e2 = combat.resolve_attack(p, f2, gd, RNG(seed))
        if e1["hit"] and e2["hit"]:
            assert e1["damage"] > e2["damage"]   # 火焰附加傷害
            return
    raise AssertionError("找不到雙命中的種子")


def test_magicka_staff_restores_on_hit():
    gd, p = _setup()
    p.skills["mysticism"] = 80
    p.weapon = "magicka_staff"
    for seed in range(80):
        p.magicka = 0
        foe = combat.spawn_creature(gd, "wolf", RNG(0))
        ev = combat.resolve_attack(p, foe, gd, RNG(seed))
        if ev["hit"]:
            assert ev["self_restored"] == ("magicka", 8)
            assert p.magicka == 8
            return
    raise AssertionError("法力法杖未觸發回魔")


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_weapons OK")
