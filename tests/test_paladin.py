"""R123 聖騎士(恢復系反死靈):治療傷害不死(smite)+ 破曉之光(radiant 終極)+ 聖化領域守護(consecration)。

設計:恢復系 = 生命能量 —— 療活物、焚亡者。治療法術(smite_undead)指向不死敵造傷,對活物零傷害
(恢復系對活人零遠程輸出)。turn_undead 驅散不死·consecration 守護。
🔴 紅線:smite/radiant 只傷不死;皆玩家施法(magic.cast);combat.py 未碰 → sim_assassin byte-identical。
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
    c.spells = ["minor_heal", "heal", "close_wounds", "turn_undead", "consecration", "dawn_judgment"]
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = 9999
    return gd, c


def test_is_undead_reads_bestiary_flag():
    gd = get_gamedata()
    assert magic._is_undead(combat.spawn_creature(gd, "skeleton", RNG(1)), gd)
    assert magic._is_undead(combat.spawn_creature(gd, "vampire_lord", RNG(1)), gd)
    assert not magic._is_undead(combat.spawn_creature(gd, "necromancer_acolyte", RNG(1)), gd)   # 活人死靈師
    assert not magic._is_undead(combat.spawn_creature(gd, "wolf", RNG(1)), gd)


# --- 治療傷害不死(smite)-------------------------------------------------
def test_heal_smite_damages_undead():
    gd, c = _paladin()
    undead = combat.spawn_creature(gd, "skeleton", RNG(3)); undead.resist = {}; undead.health = undead.max_health = 9999
    before = undead.health
    res = magic.cast(c, gd, "close_wounds", RNG(5), target=undead, enemies=[undead])
    dealt = before - undead.health
    assert dealt > 0 and res["damage"] == dealt            # 治療指向不死 → 造傷
    # 幅度 ≈ heal_mag(95) × HEAL_SMITE_FACTOR(0.5) × power(無抗)
    import tesrpg.formulas as F
    p = magic._power(_paladin()[1], gd, "restoration")
    assert abs(dealt - 95 * F.HEAL_SMITE_FACTOR * p) < 8    # roll 無(smite 不擲 roll)→ 精確


def test_heal_self_still_heals_when_no_target():
    gd, c = _paladin()
    c.health = 10
    res = magic.cast(c, gd, "heal", RNG(1))                 # target=None → 自療(非造傷)
    assert c.health > 10 and res.get("damage", 0) == 0


def test_heal_never_damages_living():
    # smite gate 走 _is_undead → 對活物即使被指定也零傷害(targeting 亦只讓 smite 指向不死;此處直接驗 magic.cast 閘)
    gd, c = _paladin()
    wolf = combat.spawn_creature(gd, "wolf", RNG(2)); wolf.health = wolf.max_health = 500
    before = wolf.health
    magic.cast(c, gd, "close_wounds", RNG(2), target=wolf, enemies=[wolf])
    assert wolf.health == before                           # 活物不受治療之傷(反而不會被 smite)


def test_turn_undead_only_repels_undead():
    gd, c = _paladin()
    wolves = [combat.spawn_creature(gd, "wolf", RNG(i)) for i in range(3)]
    magic.cast(c, gd, "turn_undead", RNG(1), enemies=wolves)
    assert not any(magic.is_feared(w) for w in wolves)     # 活人不被聖光驅散
    skels = [combat.spawn_creature(gd, "skeleton", RNG(i)) for i in range(3)]
    magic.cast(_paladin()[1], gd, "turn_undead", RNG(1), enemies=skels)
    assert any(magic.is_feared(s) for s in skels)


# --- 破曉之光(radiant 終極)---------------------------------------------
def test_radiant_dawn_heals_allies_and_smites_undead():
    gd, c = _paladin()
    c.health = 50
    skel = combat.spawn_creature(gd, "skeleton", RNG(4)); skel.resist = {}; skel.health = skel.max_health = 9999
    wolf = combat.spawn_creature(gd, "wolf", RNG(4)); wolf.health = wolf.max_health = 9999
    ub, wb = skel.health, wolf.health
    res = magic.cast(c, gd, "dawn_judgment", RNG(1), enemies=[skel, wolf], battle={"allies": []})
    assert c.health > 50                                   # 治療自身
    assert skel.health < ub                                # 灼燒不死
    assert wolf.health == wb                               # 活物毫髮無傷
    assert res["damage"] == (ub - skel.health)


# --- 聖化領域守護(Phase B·不變)---------------------------------------
def test_consecration_reduces_incoming_damage():
    gd, c = _paladin()
    foe = combat.spawn_creature(gd, "skeleton", RNG(9))
    def take(consecrate, seed):
        _, p = _paladin(); p.max_health = 500; p.health = 500
        if consecrate:
            magic.cast(p, gd, "consecration", RNG(1))
            assert any(e.get("kind") == "consecration" for e in p.active_effects)
        b = p.health
        combat.resolve_attack(foe, p, gd, RNG(seed), attack=combat.choose_attack(foe, RNG(seed), p))
        return b - p.health
    assert take(True, 11) < take(False, 11)


def test_consecration_factor_gated_to_player():
    gd = get_gamedata()
    cre = combat.spawn_creature(gd, "skeleton", RNG(1))
    cre.active_effects.append({"kind": "consecration", "magnitude": 0.5, "turns": 3})
    assert combat._consecration_factor(cre) == 1.0         # 怪掛聖化也不減傷(byte-identical 地基)


def test_sacred_bulwark_boosts_consecration_magnitude():
    gd, c = _paladin(restoration=100)
    assert mastery.consecration_bonus(c, gd) == 0.0
    mastery.choose(c, gd, "restoration_75", "sacred_bulwark")
    magic.cast(c, gd, "consecration", RNG(1))
    e = next(x for x in c.active_effects if x.get("kind") == "consecration")
    assert abs(e["magnitude"] - 0.30) < 1e-9


# --- 破曉試煉(不變·終極獎勵 id 仍 dawn_judgment)------------------------
def test_deathless_king_is_undead_and_high_hp():
    gd = get_gamedata()
    b = gd.bestiary["deathless_king"]
    assert b.get("undead") is True and b.get("solo") is True and b["max_health"] >= 300
    for atk in b.get("attacks", []):
        oh = atk.get("on_hit", {})
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1) <= 0.30 and oh.get("turns", 1) <= 1


def test_dawn_trial_gated_by_restoration_75_and_level():
    from tesrpg.systems import quests
    gd = get_gamedata()

    def holy_avail(resto, level):
        c = build_character(gd, name="P", sex="male", race="altmer", birthsign="mage", class_id="mage")
        c.skills["restoration"] = resto; c.level = level
        return [q for q in quests.available_quests(c, gd, "holy") if gd.quests[q].get("holy_site") == "dawn"]

    assert "trial_dawn" in holy_avail(75, 18)
    assert holy_avail(74, 18) == []
    assert holy_avail(75, 17) == []


def test_dawn_trial_rewards_ultimate_only_via_trial():
    from tesrpg.systems import quests
    gd = get_gamedata()
    for loc in gd.world["locations"].values():
        assert "dawn_judgment" not in loc.get("spell_stock", [])   # 破曉之光唯試煉獎勵
    assert gd.quests["trial_dawn"]["reward"]["spells"] == ["dawn_judgment"]
    c = build_character(gd, name="P", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills["restoration"] = 75; c.level = 18
    quests.accept_quest(c, gd, "trial_dawn", 0)
    c.quests["trial_dawn"] = len(gd.quests["trial_dawn"]["stages"])
    quests._complete(c, gd, "trial_dawn")
    assert "dawn_judgment" in c.spells


def test_repeat_smite_preserves_undead_target():
    # R123 審查修:↻ 再施 上次的 smite 治療 → 續灼同一不死(而非退化成自療)
    from tesrpg import main as M
    from tesrpg.ui import console as ui
    from tesrpg.state import GameState
    gd, c = _paladin()
    c.spells = ["close_wounds"]
    st = GameState(player=c)
    orig_menu = ui.menu
    ui.menu = lambda title, opts, **k: "repeat"
    try:
        skel = combat.spawn_creature(gd, "skeleton", RNG(1)); skel.health = skel.max_health = 200
        mem = {"last": {"type": "cast", "spell_id": "close_wounds", "target": skel}, "target": skel}
        act = M._choose_combat_action(st, gd, [skel], [], mem=mem)
        assert act["type"] == "cast" and act["target"] is skel   # 續灼同一不死,非 target=None 自療
    finally:
        ui.menu = orig_menu


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_paladin OK")
