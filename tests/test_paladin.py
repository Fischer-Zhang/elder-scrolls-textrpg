"""R122 聖騎士(恢復系功能化):聖光反死靈(Phase A)+ 聖化領域守護(Phase B)回歸測試。

🔴 紅線:聖光只在玩家施法(magic.cast·holy 旗標)時生效;聖光控場只落不死系(走 apply_control R44);
聖化領域減傷 gated _is_player(defender);皆不碰非 holy/非玩家路徑 → sim_assassin byte-identical(另由 worktree 驗)。
"""
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic, mastery, stats


def _paladin(restoration=100, **skills):
    gd = get_gamedata()
    c = build_character(gd, name="P", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills["restoration"] = restoration
    for k, v in skills.items():
        c.skills[k] = v
    c.attributes.update(intelligence=100, willpower=100)
    c.spells = ["holy_bolt", "sun_flare", "turn_undead", "consecration"]
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = 9999
    return gd, c


# --- Phase A:聖光剋不死 -------------------------------------------------
def test_is_undead_reads_bestiary_flag():
    gd = get_gamedata()
    assert magic._is_undead(combat.spawn_creature(gd, "skeleton", RNG(1)), gd)
    assert magic._is_undead(combat.spawn_creature(gd, "vampire_lord", RNG(1)), gd)
    # 活人死靈術士不是不死系
    assert not magic._is_undead(combat.spawn_creature(gd, "necromancer_acolyte", RNG(1)), gd)
    # 一般活物不是不死系
    assert not magic._is_undead(combat.spawn_creature(gd, "wolf", RNG(1)), gd)


def test_holy_damage_doubles_vs_undead():
    """聖光對不死系傷害 ≈ 對等生者的 HOLY_UNDEAD_MULT 倍(同抗性下)。"""
    import tesrpg.formulas as F
    gd, c = _paladin()
    # 造兩個抗性相同(0 魔抗)的目標:一不死一活人。用 spawn 後手動對齊 resist 與血量以隔離倍率。
    undead = combat.spawn_creature(gd, "skeleton", RNG(3))
    living = combat.spawn_creature(gd, "wolf", RNG(3))
    for t in (undead, living):
        t.resist = {}
        t.health = t.max_health = 9999
    du = _holy_hit(gd, _paladin()[1], undead)
    dl = _holy_hit(gd, _paladin()[1], living)
    assert du > dl
    assert abs(du / dl - F.HOLY_UNDEAD_MULT) < 0.25   # roll 抖動內


def _holy_hit(gd, caster, target):
    before = target.health
    magic.cast(caster, gd, "holy_bolt", RNG(5), target=target, enemies=[target])
    return before - target.health


def test_turn_undead_only_repels_undead():
    """驅散亡者:對活人群無效(不施恐懼),對不死系走 apply_control。"""
    gd, c = _paladin()
    wolves = [combat.spawn_creature(gd, "wolf", RNG(i)) for i in range(3)]
    magic.cast(c, gd, "turn_undead", RNG(1), enemies=wolves)
    assert not any(magic.is_feared(w) for w in wolves)     # 活人永不被聖光驅散
    # 對一般(非 solo)不死系:恐懼確實施加
    c2 = _paladin()[1]
    skels = [combat.spawn_creature(gd, "skeleton", RNG(i)) for i in range(3)]
    magic.cast(c2, gd, "turn_undead", RNG(1), enemies=skels)
    assert any(magic.is_feared(s) for s in skels)


def test_sun_flare_fear_rider_gated_to_undead():
    gd, c = _paladin()
    wolf = combat.spawn_creature(gd, "wolf", RNG(2)); wolf.health = wolf.max_health = 9999
    magic.cast(c, gd, "sun_flare", RNG(2), target=wolf, enemies=[wolf])
    assert not magic.is_feared(wolf)   # 活人吃聖光傷害但不被驅散


# --- Phase B:聖化領域守護 ----------------------------------------------
def test_consecration_reduces_incoming_damage():
    gd, c = _paladin()
    foe = combat.spawn_creature(gd, "skeleton", RNG(9))
    c.max_health = 500; c.health = 500
    # 未施聖化:記一擊傷害
    d0 = _take_hit(gd, foe, _fresh_paladin(gd), seed=11)
    # 施聖化(0.20 減傷)後同一擊
    p = _fresh_paladin(gd)
    magic.cast(p, gd, "consecration", RNG(1))
    assert any(e.get("kind") == "consecration" for e in p.active_effects)
    d1 = _take_hit(gd, foe, p, seed=11)
    assert d1 < d0


def _fresh_paladin(gd):
    _, c = _paladin()
    c.max_health = 500; c.health = 500
    return c


def _take_hit(gd, foe, defender, seed):
    before = defender.health
    combat.resolve_attack(foe, defender, gd, RNG(seed), attack=combat.choose_attack(foe, RNG(seed), defender))
    return before - defender.health


def test_consecration_factor_gated_to_player():
    """_consecration_factor 對非玩家恆 1.0(sim byte-identical 的地基)。"""
    gd = get_gamedata()
    cre = combat.spawn_creature(gd, "skeleton", RNG(1))
    cre.active_effects.append({"kind": "consecration", "magnitude": 0.5, "turns": 3})
    assert combat._consecration_factor(cre) == 1.0     # 怪即使掛了聖化也不減傷


def test_sacred_bulwark_boosts_consecration_magnitude():
    gd, c = _paladin(restoration=100)
    assert mastery.consecration_bonus(c, gd) == 0.0
    mastery.choose(c, gd, "restoration_75", "sacred_bulwark")
    magic.cast(c, gd, "consecration", RNG(1))
    e = next(x for x in c.active_effects if x.get("kind") == "consecration")
    assert abs(e["magnitude"] - 0.30) < 1e-9   # 0.20 + 0.10 里程碑


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_paladin OK")
