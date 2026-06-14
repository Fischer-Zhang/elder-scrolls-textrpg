"""坐騎(戰馬/獵馬/法駒)回歸測試。

涵蓋:購買/現乘、旅行加速 + 0.5 下限、鞍袋負重(非資源)、戰技選用閘(類別×武器×騎乘語境)、
衝鋒(更強且**永不走偷襲倍率**)、衝鋒對 solo boss 的夾限、法駒法術增益、馬廄購買扣金、存檔相容。
紅線:衝鋒不碰偷襲路徑(sneak is None)、solo 夾限(MOUNTED_CHARGE_DAMAGE_CAP_RATIO)。
"""

import json

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import combat, inventory, magic, mounts, stats, world


def _char(cls="warrior", race="nord"):
    gd = get_gamedata()
    c = build_character(gd, name="騎", sex="male", race=race, birthsign="warrior", class_id=cls)
    return gd, c


def test_buy_and_active():
    gd, c = _char()
    assert mounts.buy(c, gd, "warhorse") is True
    assert "warhorse" in c.mounts_owned and c.active_mount == "warhorse"
    assert mounts.buy(c, gd, "warhorse") is False     # 重複購買拒絕
    assert mounts.buy(c, gd, "nonexist") is False


def test_travel_speed_and_saddlebag():
    gd, c = _char()
    base_mw = inventory.max_weight(c, gd)
    assert inventory.max_weight(c) == base_mw          # 無 gamedata = 基底(test_world 相容)
    mounts.buy(c, gd, "warhorse")
    assert abs(mounts.travel_factor_bonus(c, gd) - 0.10) < 1e-9
    assert inventory.max_weight(c, gd) == base_mw + 80  # 鞍袋
    c.active_mount = ""                                  # 下馬 → 還原
    assert inventory.max_weight(c, gd) == base_mw
    assert mounts.travel_factor_bonus(c, gd) == 0.0


def test_saddlebag_not_a_resource():
    """鞍袋只動負重上限、不碰三資源(不進 recompute_max_resources、不寫 base)。"""
    gd, c = _char()
    mh, mm, mf = c.max_health, c.max_magicka, c.max_fatigue
    mounts.buy(c, gd, "warhorse")
    stats.recompute_max_resources(c, gd)
    assert (c.max_health, c.max_magicka, c.max_fatigue) == (mh, mm, mf)


def test_travel_integration_mounted_faster():
    gd, ca = _char()
    gd, cb = _char()
    mounts.buy(cb, gd, "warhorse")
    dest = world.travel_options(ca, gd)[0][0]
    ra = world.travel(ca, gd, dest, GameState(player=ca, rng=RNG(1)).time, RNG(1))
    rb = world.travel(cb, gd, dest, GameState(player=cb, rng=RNG(1)).time, RNG(1))
    assert rb["hours"] <= ra["hours"]


def test_travel_floor_respected():
    gd, c = _char()
    c.skills["athletics"] = 100          # 0.6 - 0.18(獵馬) = 0.42 → 夾回 0.5 下限
    mounts.buy(c, gd, "courser")
    dest, base = world.travel_options(c, gd)[0]
    r = world.travel(c, gd, dest, GameState(player=c, rng=RNG(1)).time, RNG(1))
    assert r["hours"] >= max(1, round(base * 0.5))


def test_skill_gating_by_mount_weapon_and_context():
    gd, c = _char()
    inventory.add_item(c, "iron_spear", 1)
    c.weapon = "iron_spear"
    mounts.buy(c, gd, "warhorse")
    assert mounts.can_charge(c, gd, mounted=True) is True
    assert mounts.can_charge(c, gd, mounted=False) is False    # 地城/非騎乘語境
    c.weapon = "hunting_bow"
    assert mounts.can_charge(c, gd, mounted=True) is False      # 弓不可衝鋒
    inventory.add_item(c, "hunting_bow", 1)
    mounts.buy(c, gd, "courser")
    c.active_mount = "courser"
    assert mounts.can_skirmish_ride(c, gd, mounted=True) is True
    assert mounts.can_skirmish_ride(c, gd, mounted=False) is False
    c.weapon = "iron_sword"
    assert mounts.can_skirmish_ride(c, gd, mounted=True) is False  # 騎射須持弓


def test_charge_not_sneak_and_stronger():
    """長槍衝鋒:更強(高倍率)且**永不走偷襲倍率**(守刺客紅線)。"""
    gd, c = _char()
    c.skills["blade"] = 80
    inventory.add_item(c, "steel_spear", 1)
    c.weapon = "steel_spear"
    mounts.buy(c, gd, "warhorse")
    spec = mounts.charge_spec(c, gd)
    n_total = ch_total = 0
    for seed in range(1, 40):
        foe = combat.spawn_creature(gd, "bandit", RNG(seed)); foe.health = foe.max_health = 9999
        ev = combat.resolve_attack(c, foe, gd, RNG(seed))
        foe2 = combat.spawn_creature(gd, "bandit", RNG(seed)); foe2.health = foe2.max_health = 9999
        ec = combat.resolve_attack(c, foe2, gd, RNG(seed), mounted_charge=True, charge_spec=spec)
        assert ec["sneak"] is None                # 衝鋒不是偷襲
        assert ec["damage"] >= ev["damage"]       # 同 seed:衝鋒不弱於普攻
        n_total += ev["damage"]; ch_total += ec["damage"]
    assert ch_total > n_total                      # 整體更強(長槍×高倍率)


def test_charge_solo_boss_capped():
    """衝鋒(尤其長槍×高倍率)對 solo boss 開場一擊不可秒 → 受 MOUNTED_CHARGE_DAMAGE_CAP_RATIO 夾。"""
    gd, c = _char()
    c.skills["blade"] = 100
    c.attributes["strength"] = 100
    inventory.add_item(c, "daedric_spear", 1)
    c.weapon = "daedric_spear"
    mounts.buy(c, gd, "warhorse")
    spec = mounts.charge_spec(c, gd)
    hits = 0
    for seed in range(1, 80):
        boss = combat.spawn_creature(gd, "dremora_lord", RNG(seed))
        boss.max_health = boss.health = 40        # cap = 40 × 0.45 = 18
        ev = combat.resolve_attack(c, boss, gd, RNG(seed), mounted_charge=True, charge_spec=spec)
        if ev["hit"]:
            hits += 1
            assert ev["damage"] <= 40 * formulas.MOUNTED_CHARGE_DAMAGE_CAP_RATIO + 0.5
    assert hits > 0                                # 確有命中,夾限確被驗到


def test_magesteed_spell_bonus():
    gd, c = _char(cls="mage")
    mounts.buy(c, gd, "magesteed")
    assert mounts.spell_bonus_dmg(c, gd, mounted=True) == 0.20
    assert mounts.spell_bonus_dmg(c, gd, mounted=False) == 0.0    # 非騎乘戰=中性
    c.active_mount = ""
    mounts.buy(c, gd, "warhorse"); c.active_mount = "warhorse"
    assert mounts.spell_bonus_dmg(c, gd, mounted=True) == 0.0      # 非法駒=0


def test_magesteed_cast_damage_higher_when_mounted():
    gd, c = _char(cls="mage")
    c.spells = ["flames"]
    c.skills["destruction"] = 60
    mounts.buy(c, gd, "magesteed")
    tot_n = tot_m = 0
    for seed in range(1, 25):
        c.magicka = c.max_magicka = 200; c.fatigue = c.max_fatigue
        foe = combat.spawn_creature(gd, "bear", RNG(seed)); foe.health = foe.max_health = 9999
        rn = magic.cast(c, gd, "flames", RNG(seed), target=foe, mounted=False)
        c.magicka = 200; c.fatigue = c.max_fatigue
        foe2 = combat.spawn_creature(gd, "bear", RNG(seed)); foe2.health = foe2.max_health = 9999
        rm = magic.cast(c, gd, "flames", RNG(seed), target=foe2, mounted=True)
        tot_n += rn["damage"]; tot_m += rm["damage"]
    assert tot_m > tot_n      # 法駒騎乘戰法術增益


def test_action_stable_deducts_gold():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _char(); c.gold = 5000; c.location_id = "bruma"
    state = GameState(player=c, rng=RNG(1))
    seq = iter(["buy:warhorse", None])
    saved = (ui.menu, ui.message)
    ui.menu = lambda *a, **k: next(seq, None)
    ui.message = lambda *a, **k: None
    try:
        M.action_stable(state, gd)
    finally:
        ui.menu, ui.message = saved
    assert "warhorse" in c.mounts_owned and c.gold == 5000 - 2000


def test_save_roundtrip_and_old_save():
    gd, c = _char()
    mounts.buy(c, gd, "warhorse"); mounts.buy(c, gd, "courser")
    d = json.loads(json.dumps(c.to_dict()))
    l = Character.from_dict(d)
    assert l.mounts_owned == c.mounts_owned and l.active_mount == c.active_mount
    for k in ("mounts_owned", "active_mount"):
        del d[k]
    o = Character.from_dict(d)
    assert o.mounts_owned == [] and o.active_mount == ""


def run():
    test_buy_and_active()
    test_travel_speed_and_saddlebag()
    test_saddlebag_not_a_resource()
    test_travel_integration_mounted_faster()
    test_travel_floor_respected()
    test_skill_gating_by_mount_weapon_and_context()
    test_charge_not_sneak_and_stronger()
    test_charge_solo_boss_capped()
    test_magesteed_spell_bonus()
    test_magesteed_cast_damage_higher_when_mounted()
    test_action_stable_deducts_gold()
    test_save_roundtrip_and_old_save()


if __name__ == "__main__":
    run()
    print("test_mounts 全通過")
