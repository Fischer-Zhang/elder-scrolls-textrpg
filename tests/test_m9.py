"""M9:煉金毒藥與武器塗毒。"""

import tempfile
from pathlib import Path

from tesrpg import synth
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import alchemy, combat, inventory, magic


def _char():
    gd = get_gamedata()
    c = build_character(gd, name="毒", sex="female", race="bosmer",
                        birthsign="thief", class_id="assassin")
    c.skills["alchemy"] = 60
    return gd, c


# --- 煉金分流:毒藥 vs 藥水 --------------------------------------------
def test_brew_damage_poison():
    gd, c = _char()
    inventory.add_item(c, "nightshade", 1)
    inventory.add_item(c, "deathbell", 1)        # 共通 damage_health
    r = alchemy.brew(c, gd, "nightshade", "deathbell", RNG(0))
    assert r["ok"] and r["kind"] == "poison"
    d = gd.item(r["item_id"])
    assert d["kind"] == "poison" and d["poison"]["status"] == "dot"


def test_brew_paralyze_priority():
    gd, c = _char()
    inventory.add_item(c, "nightshade", 1)
    inventory.add_item(c, "imp_stool", 1)        # 共通 damage_health 與 paralyze → 麻痺優先
    r = alchemy.brew(c, gd, "nightshade", "imp_stool", RNG(0))
    assert gd.item(r["item_id"])["poison"]["status"] == "paralyze"


def test_brew_restorative_still_potion():
    gd, c = _char()
    inventory.add_item(c, "wheat", 1)
    inventory.add_item(c, "blue_mountain_flower", 1)   # 共通 heal
    r = alchemy.brew(c, gd, "wheat", "blue_mountain_flower", RNG(0))
    assert r["kind"] == "potion" and gd.item(r["item_id"])["kind"] == "potion"


def test_alchemy_skill_scales_poison():
    gd, c = _char()
    c.skills["alchemy"] = 0
    inventory.add_item(c, "nightshade", 1); inventory.add_item(c, "deathbell", 1)
    low = gd.item(alchemy.brew(c, gd, "nightshade", "deathbell", RNG(0))["item_id"])["poison"]["magnitude"]
    c.skills["alchemy"] = 100
    inventory.add_item(c, "nightshade", 1); inventory.add_item(c, "deathbell", 1)
    high = gd.item(alchemy.brew(c, gd, "nightshade", "deathbell", RNG(0))["item_id"])["poison"]["magnitude"]
    assert high > low


# --- 塗毒 ---------------------------------------------------------------
def test_item_name_handles_synth_ids():
    """回歸:item_name 須支援合成 id(毒藥/藥水/附魔),否則 coat 選單會 KeyError。"""
    gd, _ = _char()
    assert "毒藥" in gd.item_name(synth.poison_id("dot", 10, 3))
    assert "麻痺" in gd.item_name(synth.poison_id("paralyze", 2))
    assert gd.item_name(synth.brew_id("heal", 30))            # 不應拋例外


def test_coat_weapon_and_charges():
    gd, c = _char()
    pid = synth.poison_id("dot", 8, 3)
    inventory.add_item(c, pid, 1)
    c.weapon = "fists"
    assert not inventory.coat_weapon(c, gd, pid)         # 徒手不可塗
    c.weapon = "steel_sword"
    assert inventory.coat_weapon(c, gd, pid)
    assert c.weapon_poison["charges"] == inventory.poison_charges(c)
    assert inventory.count_item(c, pid) == 0             # 毒藥被消耗


def test_poison_charges_scale_with_alchemy():
    gd, c = _char()
    c.skills["alchemy"] = 0
    lo = inventory.poison_charges(c)
    c.skills["alchemy"] = 90
    assert inventory.poison_charges(c) > lo


# --- 戰鬥:塗毒命中 -----------------------------------------------------
def test_poison_applies_on_hit_and_depletes():
    gd, c = _char()
    c.skills["blade"] = 80
    c.attributes["strength"] = 80
    c.weapon = "steel_sword"
    c.weapon_poison = {"status": {"status": "dot", "element": "poison", "magnitude": 6, "turns": 3},
                       "charges": 1, "name": "毒藥"}
    foe = combat.spawn_creature(gd, "wolf", RNG(3))
    applied = False
    for i in range(20):
        ev = combat.resolve_attack(c, foe, gd, RNG(i))
        if ev.get("poison_applied"):
            applied = True
            break
    assert applied
    assert c.weapon_poison is None                       # 最後一層用完即清
    assert any(e["kind"] == "dot" for e in foe.active_effects)


def test_poison_respects_resist():
    gd, c = _char()
    c.skills["blade"] = 90; c.attributes["strength"] = 80; c.weapon = "steel_sword"
    skel = combat.spawn_creature(gd, "skeleton", RNG(1))   # poison 抗性 100
    c.weapon_poison = {"status": {"status": "dot", "element": "poison", "magnitude": 8, "turns": 3},
                       "charges": 5, "name": "毒藥"}
    for i in range(15):
        if combat.resolve_attack(c, skel, gd, RNG(i)).get("poison_applied"):
            break
    h0 = skel.health
    magic.tick_effects(skel, gd)
    assert skel.health == h0                              # 免疫毒素 → DoT 0


# --- 存讀檔 -------------------------------------------------------------
def test_weapon_poison_persists():
    gd, c = _char()
    c.weapon = "steel_sword"
    c.weapon_poison = {"status": {"status": "dot", "element": "poison", "magnitude": 6, "turns": 3},
                       "charges": 2, "name": "毒藥"}
    st = GameState(player=c, time=GameTime())
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        st.save(p)
        lo = GameState.load(p)
    assert lo.player.weapon_poison == c.weapon_poison     # 塗毒狀態跨存檔保留


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m9 OK")
