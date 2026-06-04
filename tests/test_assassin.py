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


# --- 雙持匕首 -----------------------------------------------------------
def test_equip_offhand_dagger_rules():
    from tesrpg.systems import inventory
    from tesrpg.models import Character
    gd, c = _assassin(weapon="iron_dagger")
    inventory.add_item(c, "iron_dagger", 1)        # 主手 1 把,需第 2 把才能同型雙持
    assert not inventory.equip_offhand(c, gd, "iron_dagger")   # 只有 1 把 → 不行
    inventory.add_item(c, "iron_dagger", 1)        # 現在共 2 把
    assert inventory.equip_offhand(c, gd, "iron_dagger")
    assert inventory.is_dual_wielding(c, gd)
    # 劍不能當副手
    inventory.add_item(c, "iron_sword", 1)
    assert not inventory.equip_offhand(c, gd, "iron_sword")
    # 存檔往返保留副手
    assert Character.from_dict(c.to_dict()).offhand == "iron_dagger"


def test_dual_wield_needs_dagger_mainhand():
    from tesrpg.systems import inventory
    gd, c = _assassin(weapon="iron_sword")          # 主手是劍
    inventory.add_item(c, "steel_dagger", 1)
    inventory.equip_offhand(c, gd, "steel_dagger")
    assert not inventory.is_dual_wielding(c, gd)     # 主手非匕首 → 雙持不成立
    assert inventory.dual_wield_bonus_damage(c, gd) == 0.0


def test_dual_wield_adds_damage():
    from tesrpg import formulas
    from tesrpg.systems import inventory
    gd, c = _assassin(weapon="steel_dagger", sneak=0)   # 關掉偷襲倍率,純比基礎傷
    target = _dummy(hp=999999, armor=0)

    def avg_hit(n=400):
        tot = 0
        for i in range(n):
            target.health = target.max_health
            ev = combat.resolve_attack(c, target, gd, RNG(i), sneak_attack=False)
            tot += ev["damage"]
        return tot / n

    single = avg_hit()
    inventory.add_item(c, "steel_dagger", 2)
    assert inventory.equip_offhand(c, gd, "steel_dagger")
    assert inventory.dual_wield_bonus_damage(c, gd) == gd.item("steel_dagger")["damage"] * formulas.OFFHAND_DAMAGE_FACTOR
    assert avg_hit() > single * 1.3                  # 雙持顯著增傷


def test_drop_breaks_pair_ends_dualwield():
    from tesrpg.systems import inventory
    gd, c = _assassin(weapon="iron_dagger")
    inventory.add_item(c, "iron_dagger", 2)          # 主手+副手共 2 把
    assert inventory.equip_offhand(c, gd, "iron_dagger")
    assert inventory.is_dual_wielding(c, gd)
    inventory.remove_item(c, "iron_dagger", 1)        # 只剩 1 把
    assert not inventory.is_dual_wielding(c, gd)       # 自動退出雙持
    assert c.offhand == ""                             # 殘留副手已被清除(修正 review minor)


def test_offhand_not_amplified_by_sneak_attack():
    """回歸(review major):副手傷害不吃偷襲倍率 → 滿練雙持仍秒不掉高血精英 frost_troll。"""
    from tesrpg.systems import inventory, stats
    gd = get_gamedata()
    c = build_character(gd, name="x", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
    c.skills.update(sneak=100, blade=100, alchemy=100); c.weapon = "glass_dagger"
    inventory.add_item(c, "glass_dagger", 2); inventory.equip_offhand(c, gd, "glass_dagger")
    stats.recompute_max_resources(c, gd, restore_full=True)
    kills = sum(combat.resolve_attack(c, combat.spawn_creature(gd, "frost_troll", RNG(i + 1)),
                                      gd, RNG(i * 7 + 3), sneak_attack=True)["defender_dead"]
                for i in range(600))
    assert kills / 600 < 0.30, f"雙持偷襲秒殺 frost_troll 率過高:{kills/600:.0%}"


def test_vanish_costs_fatigue():
    gd, c = _assassin()
    c.fatigue = c.max_fatigue
    combat.player_vanish_cost(c)
    assert c.fatigue < c.max_fatigue                   # 隱遁耗體力(壓制無限風箏)


# --- 隱遁再襲 -----------------------------------------------------------
def test_restealth_chance_drops_with_crowd_and_reuse():
    from tesrpg import formulas
    base = formulas.restealth_chance(70, 50, 1, 0)
    assert formulas.restealth_chance(70, 50, 3, 0) < base       # 敵人越多越難
    assert formulas.restealth_chance(70, 50, 1, 2) < base       # 重複用遞減
    assert 0.05 <= formulas.restealth_chance(0, 0, 9, 9) <= 0.90  # 夾限
    assert formulas.restealth_chance(100, 100, 1, 0) > formulas.restealth_chance(20, 0, 1, 0)


def test_can_vanish_needs_sneak_threshold():
    gd, c = _assassin(sneak=5)
    assert not combat.can_vanish(c)            # 非潛行流派沒有隱遁
    c.skills["sneak"] = 40
    assert combat.can_vanish(c)


# --- 偵查技能(第 22 個技能)+ 潛行撤退 ---------------------------------
def test_scout_is_a_real_stealth_skill():
    gd = get_gamedata()
    assert "scout" in gd.skills and gd.skills["scout"]["spec"] == "stealth"
    assert "scout" in gd.skills_by_spec("stealth")
    assert len(gd.skills) == 22                       # 21 → 22


def test_new_character_has_scout_trained_by_use():
    from tesrpg.models import Character
    from tesrpg.systems import progression
    gd, c = _assassin()
    assert "scout" in c.skills                          # 新角色含偵查
    # 舊存檔(缺 scout)仍可載入並靠 use_skill 成長
    d = c.to_dict(); d["skills"].pop("scout", None); d["skill_xp"].pop("scout", None)
    old = Character.from_dict(d)
    assert old.skill("scout") == 0
    before = old.skill("scout")
    for _ in range(200):
        progression.use_skill(old, gd, "scout", 1.0)
    assert old.skill("scout") > before                 # learn-by-doing 對新技能照常運作


def test_estimate_sneak_damage_reflects_build():
    from tesrpg.systems import inventory
    gd, c = _assassin(sneak=80, blade=60, weapon="steel_dagger")
    foe = _dummy(hp=200, armor=10)
    single = combat.estimate_sneak_damage(c, gd, foe)
    inventory.add_item(c, "steel_dagger", 2); inventory.equip_offhand(c, gd, "steel_dagger")
    dual = combat.estimate_sneak_damage(c, gd, foe)
    assert dual > single > 0                           # 雙持估傷更高


def test_stealth_retreat_chance_drops_with_group():
    from tesrpg import formulas
    solo = formulas.stealth_retreat_chance(70, 50, 40, 1)
    pack = formulas.stealth_retreat_chance(70, 50, 40, 4)
    assert pack < solo
    assert 0.10 <= formulas.stealth_retreat_chance(0, 0, 99, 9) <= 0.92


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_assassin OK")
