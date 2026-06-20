"""毒劑深化(R31)單元測試:衰毒/遲緩/懼毒新毒型、里程碑功能性解鎖、solo 控制免疫(修 R15 缺口)。

涵蓋:brew 路由(解鎖 vs 未解鎖 fall-back DoT)、synth round-trip、戰鬥施加(weaken/slow/fear)、
**solo BOSS 對塗毒控制(麻痺/懼意)免疫的回歸**、各毒型塗層次數、既有毒藥/麻痺路由不變。
"""

from tesrpg import synth
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import alchemy, combat, inventory, magic, mastery


def _char(alchemy_skill=100):
    gd = get_gamedata()
    c = build_character(gd, name="毒", sex="female", race="bosmer",
                        birthsign="thief", class_id="assassin")
    c.skills["alchemy"] = alchemy_skill
    c.is_player = True
    c.weapon = "steel_sword"
    return gd, c


def _brew(gd, c, a, b):
    inventory.add_item(c, a, 1); inventory.add_item(c, b, 1)
    return alchemy.brew(c, gd, a, b, RNG(0))


# --- 路由:特殊毒型需里程碑解鎖,否則 fall-back 基礎 DoT --------------------
def test_weaken_needs_unlock_else_dot():
    gd, c = _char()
    r = _brew(gd, c, "deathbell", "imp_stool")            # 共有 damage_health + damage_strength
    assert gd.item(r["item_id"])["poison"]["status"] == "dot"   # 未解鎖 → 退回 DoT
    mastery.choose(c, gd, "alchemy_50", "toxin_master")          # 解鎖衰毒
    r2 = _brew(gd, c, "deathbell", "imp_stool")
    assert gd.item(r2["item_id"])["poison"]["status"] == "weaken"


def test_slow_unlock_and_duration_bonus():
    gd, c = _char()
    mastery.choose(c, gd, "alchemy_75", "potent_poison")        # 解鎖遲緩 + 毒效延長 1
    r = _brew(gd, c, "deathbell", "spider_egg")                 # 共有 damage_health + slow
    p = gd.item(r["item_id"])["poison"]
    assert p["status"] == "slow" and p["turns"] == 2 + 1        # 基礎 2 + 延長 1


def test_fear_unlock_requires_alchemy_100():
    gd, c = _char(alchemy_skill=100)
    mastery.choose(c, gd, "alchemy_100", "venom_lord")          # 解鎖懼毒
    r = _brew(gd, c, "deathbell", "vampire_dust")               # 共有 damage_health + fear
    assert gd.item(r["item_id"])["poison"]["status"] == "fear"
    # 未達 alchemy 100 → 節點未達成 → 仍退回 DoT
    gd2, c2 = _char(alchemy_skill=80)
    mastery.choose(c2, gd2, "alchemy_100", "venom_lord")        # 門檻未達,choose 無效/不計
    r2 = _brew(gd2, c2, "deathbell", "vampire_dust")
    assert gd2.item(r2["item_id"])["poison"]["status"] == "dot"


def test_existing_poison_routes_unchanged():
    """回歸 test_m9:既有毒藥路由不因新毒型而變(無解鎖時)。"""
    gd, c = _char(alchemy_skill=60)
    assert gd.item(_brew(gd, c, "nightshade", "deathbell")["item_id"])["poison"]["status"] == "dot"
    assert gd.item(_brew(gd, c, "nightshade", "imp_stool")["item_id"])["poison"]["status"] == "paralyze"


# --- synth round-trip ---------------------------------------------------
def test_synth_roundtrip_new_poisons():
    gd, _ = _char()
    w = gd.item(synth.poison_id("weaken", 25, 3))["poison"]
    assert w == {"status": "weaken", "magnitude": 0.25, "turns": 3}
    s = gd.item(synth.poison_id("slow", 30, 2))["poison"]
    assert s == {"status": "slow", "magnitude": 0.30, "turns": 2}
    f = gd.item(synth.poison_id("fear", 2))["poison"]
    assert f == {"status": "fear", "turns": 2}
    for k, a, b in (("weaken", 25, 3), ("slow", 30, 2), ("fear", 2, 0)):
        assert gd.item_name(synth.poison_id(k, a, b))    # 不應拋例外(coat/背包選單會用)


# --- 塗層次數依毒型 -----------------------------------------------------
def test_coat_charges_per_family():
    gd, c = _char(alchemy_skill=90)
    base = inventory.poison_charges(c) + mastery.poison_charge_bonus(c, gd)
    cases = {synth.poison_id("dot", 8, 3): base,
             synth.poison_id("weaken", 20, 3): base,
             synth.poison_id("slow", 25, 2): max(1, base - 1),
             synth.poison_id("fear", 2): max(1, base // 2 + 1),
             synth.poison_id("paralyze", 2): max(1, base // 2 + 1)}
    for pid, want in cases.items():
        c.weapon = "steel_sword"
        inventory.add_item(c, pid, 1)
        assert inventory.coat_weapon(c, gd, pid)
        assert c.weapon_poison["charges"] == want, (pid, c.weapon_poison["charges"], want)


# --- solo BOSS 控制免疫(修 R15 缺口的回歸) ----------------------------
def _coat_and_hit(gd, c, pid, target, tries=12, seed=0):
    inventory.add_item(c, pid, 1); inventory.coat_weapon(c, gd, pid)
    consumed = False
    for i in range(tries):
        if c.weapon_poison is None:
            consumed = True
            break
        before = c.weapon_poison["charges"]
        combat.resolve_attack(c, target, gd, RNG(seed * tries + i))
        if c.weapon_poison is None or c.weapon_poison["charges"] < before:
            consumed = True
    return consumed


def test_solo_boss_coated_control_reduced():
    """R44 機率減免:塗毒麻痺/懼意對 solo BOSS 由「完全免疫」改機率抵抗(會中也會抗);毒仍接觸即耗。"""
    gd, c = _char(alchemy_skill=100)
    c.skills["blade"] = 100                    # 確保命中(否則 12 retry 內未落毒)
    for pid, kind in ((synth.poison_id("paralyze", 2), "paralyze"),
                      (synth.poison_id("fear", 2), "fear")):
        landed = 0
        for s in range(150):
            boss = combat.spawn_creature(gd, "dremora_lord", RNG(s))
            c.weapon = "steel_sword"; c.weapon_poison = None
            assert _coat_and_hit(gd, c, pid, boss, seed=s + 1), kind    # 接觸即耗(杜絕無限重試泵)
            if any(e["kind"] == kind for e in boss.active_effects):
                landed += 1
        assert 0 < landed < 150, (kind, landed)    # 機率減免:既非永免疫亦非每次


def test_coated_control_lands_on_nonsolo():
    gd, c = _char(alchemy_skill=100)
    for pid, kind in ((synth.poison_id("paralyze", 2), "paralyze"),
                      (synth.poison_id("fear", 2), "fear")):
        wolf = combat.spawn_creature(gd, "wolf", RNG(3))
        c.weapon = "steel_sword"
        _coat_and_hit(gd, c, pid, wolf)
        assert any(e["kind"] == kind for e in wolf.active_effects), kind


# --- 新戰鬥效果:slow / weaken ------------------------------------------
def test_slow_reduces_speed_and_hit():
    gd, c = _char()
    wolf = combat.spawn_creature(gd, "wolf", RNG(5))
    sp0 = combat._speed(wolf)
    wolf.active_effects.append({"kind": "slow", "element": None, "magnitude": 0.3, "turns": 2})
    assert magic.is_slowed(wolf) and abs(magic.slow_factor(wolf) - 0.3) < 1e-9
    assert combat._speed(wolf) < sp0


def test_weaken_poison_applies_in_combat():
    gd, c = _char()
    wolf = combat.spawn_creature(gd, "wolf", RNG(7))
    c.weapon = "steel_sword"
    _coat_and_hit(gd, c, synth.poison_id("weaken", 25, 3), wolf)
    assert any(e["kind"] == "weaken" for e in wolf.active_effects)
    assert magic.weaken_factor(wolf) < 1.0


def test_slow_is_dispellable():
    assert "slow" in magic._DISPELLABLE


def test_debuff_expiry_messages():
    """weaken/slow/fear 退場皆有玩家可見回饋(與麻痺對稱;R31 審查 nit)。"""
    gd, c = _char()
    for kind in ("weaken", "slow", "fear"):
        wolf = combat.spawn_creature(gd, "wolf", RNG(1))
        wolf.active_effects.append({"kind": kind, "element": None, "magnitude": 0.2, "turns": 1})
        msgs = magic.tick_effects(wolf, gd)            # turns 1→0 → 退場
        assert any(m for m in msgs), kind
        assert not any(e["kind"] == kind for e in wolf.active_effects)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_poison_depth")
