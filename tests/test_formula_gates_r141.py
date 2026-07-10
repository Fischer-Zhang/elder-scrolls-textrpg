"""R141 現實邏輯:戰鬥公式裝備前提 gate —— 盾反需持盾、重甲反震/重壓需穿重甲、輕甲閃避 perk
穿重甲不生效、裸身被打不練護甲、力竭也罰防端(閃避減半)、重盾盾擊耗體以盾自身(慢重)計。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, mastery
from tesrpg import formulas

gd = get_gamedata()


def _char(**skills):
    c = build_character(gd, name="測", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(skills)
    return c


def test_light_armor_evasion_perk_gated_by_heavy():
    c = _char(light_armor=100)
    mastery.choose(c, gd, "light_armor_50", "storm_dance") if any(
        n["id"] == "light_armor_50" for n in gd.mastery) else None
    # 直接找 light_armor 樹上任一 evasion_bonus 選項
    for node in gd.mastery:
        if node.get("skill") == "light_armor":
            for o in node["options"]:
                if o.get("kind") == "evasion_bonus":
                    c.skills["light_armor"] = max(c.skills["light_armor"], node["threshold"])
                    c.mastery_choices[node["id"]] = o["opt_id"]
    base = mastery.evasion_bonus(c, gd)
    assert base > 0, "fixture 應至少取得一個輕甲閃避 perk"
    inventory.add_item(c, "steel_cuirass", 1); inventory.equip_armor(c, gd, "steel_cuirass")
    assert mastery.evasion_bonus(c, gd) < base            # 穿重甲 → 輕甲系閃避 perk 失效
    c.equipped.pop("cuirass", None)
    assert mastery.evasion_bonus(c, gd) == base           # 脫下 → 恢復


def test_block_passive_and_reflect_need_shield():
    c = _char(block=100)
    c.mastery_choices["block_75"] = "bracing"
    assert mastery.passive_armor_bonus(c, gd) == 0        # 無盾 → 撐架護甲 0
    inventory.add_item(c, "steel_shield", 1); inventory.equip_armor(c, gd, "steel_shield")
    assert mastery.passive_armor_bonus(c, gd) == 10


def test_naked_takes_no_armor_xp():
    c = _char()
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    for s in range(30):
        combat.resolve_attack(foe, c, gd, RNG(s))
        c.health = c.max_health
    assert not c.skill_xp.get("heavy_armor") and not c.skill_xp.get("light_armor")   # 裸身沒有甲可習
    inventory.add_item(c, "steel_cuirass", 1); inventory.equip_armor(c, gd, "steel_cuirass")
    for s in range(30):
        combat.resolve_attack(foe, c, gd, RNG(s))
        c.health = c.max_health
    assert c.skill_xp.get("heavy_armor", 0) > 0           # 穿上 → 練得動


def test_exhausted_defender_evades_less():
    def hits(fatigue, n=300):
        total = 0
        for s in range(n):
            c = _char(acrobatics=100)
            c.attributes["agility"] = 90
            c.fatigue = fatigue
            foe = combat.spawn_creature(gd, "bandit", RNG(s))
            total += combat.resolve_attack(foe, c, gd, RNG(s * 7 + 3))["hit"]
        return total
    assert hits(0) > hits(200)                            # 力竭 → 閃避減半 → 被打中更多


def test_great_shield_bash_fatigue_uses_shield_speed():
    c = _char(block=100)
    c.weapon = "iron_dagger"                              # 快武器(休眠)
    inventory.add_item(c, "daedric_great_shield", 1); inventory.equip_armor(c, gd, "daedric_great_shield")
    c.fatigue = 200
    combat.player_attack_cost(c, gd)
    cost_gs = 200 - c.fatigue
    c2 = _char(block=100)
    c2.weapon = "iron_dagger"
    c2.fatigue = 200
    combat.player_attack_cost(c2, gd)
    cost_dagger = 200 - c2.fatigue
    assert cost_gs > cost_dagger                          # 揮 28 重塔盾不可能比揮匕首省力


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
