"""四中庸職業功能性區分(法術/武技)的單元測試。

涵蓋:戰法師奧術灌注(imbue,sneak-solo 受夾)、治療師援護同伴(+持久)、騎士號令
(empower 同伴、不碰玩家)、弓手散兵(aimed 不吃偷襲、crippling、skirmish)+ 摘要全涵蓋。
"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, party
from tesrpg.ui import console as ui


def _melee(blade=80, strength=80, weapon="steel_sword"):
    gd = get_gamedata()
    c = build_character(gd, name="M", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.skills["blade"] = blade; c.attributes["strength"] = strength; c.weapon = weapon
    c.magicka = 300
    return gd, c


# --- 戰法師:奧術灌注 weapon_imbue ----------------------------------------
def test_imbue_cast_sets_buff_and_adds_element():
    gd, c = _melee()
    c.spells.append("flame_blade")
    res = magic.cast(c, gd, "flame_blade", RNG(1), battle={"allies": []})
    assert res["ok"] and any(e["kind"] == "weapon_imbue" for e in c.active_effects)
    # 灌注 vs 未灌注:同 rng 下灌注傷害更高(對無火抗的 bandit)
    def dmg(imbued, seed):
        _, m = _melee()
        if imbued:
            m.active_effects = [{"kind": "weapon_imbue", "element": "fire", "magnitude": 20, "turns": 5}]
        foe = combat.spawn_creature(gd, "bandit", RNG(seed)); foe.resist = {}
        return combat.resolve_attack(m, foe, gd, RNG(seed))["damage"]
    hi = sum(dmg(True, s) for s in range(40)); lo = sum(dmg(False, s) for s in range(40))
    assert hi > lo                                            # 灌注加元素傷害


def test_imbue_capped_on_sneak_solo_boss():
    gd, c = _melee(blade=100, strength=100)
    c.active_effects = [{"kind": "weapon_imbue", "element": "fire", "magnitude": 40, "turns": 5}]
    boss = combat.spawn_creature(gd, "ancient_dragon", RNG(1))
    cap = boss.max_health * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO
    worst = 0
    for s in range(200):
        combat._set_hp(boss, boss.max_health)
        ev = combat.resolve_attack(c, boss, gd, RNG(s), sneak_attack=True)
        worst = max(worst, ev["damage"])
    assert worst <= cap, (worst, cap)                        # 含灌注仍受 solo 偷襲夾限(紅線)


# --- 治療師:戰地援護(ally-targeting)------------------------------------
def test_ally_heal_in_battle_and_persists():
    gd, c = _melee(); c.spells.append("heal_other"); c.companions.append("sellsword")
    ally = combat.spawn_companion(gd, "sellsword", RNG(1)); ally.health = 10
    res = magic.cast(c, gd, "heal_other", RNG(1), target=ally, battle={"allies": [ally]})
    assert res["ok"] and ally.health > 10                    # 同伴被治癒
    party.record_after_battle(c, gd, [("sellsword", ally)])  # 戰後回寫
    assert c.companion_hp["sellsword"] == int(ally.health)    # 持久(接同伴系統)


def test_ally_spell_needs_battle_and_living_ally():
    gd, c = _melee(); c.spells.append("healing_circle")
    mp0, fp0 = c.magicka, c.fatigue
    assert not magic.cast(c, gd, "heal_other", RNG(1), target=None, battle=None)["ok"]   # 戰外不可
    assert c.magicka == mp0 and c.fatigue == fp0             # 戰外失敗:魔力+體力皆退還
    mp1, fp1 = c.magicka, c.fatigue
    assert not magic.cast(c, gd, "healing_circle", RNG(1), battle={"allies": []})["ok"]   # 無同伴
    assert c.magicka == mp1 and c.fatigue == fp1             # 無同伴失敗:退魔也退體(不對稱資源損失修正)


def test_ally_aoe_heal_and_regen_aura():
    gd, c = _melee(); a1 = combat.spawn_companion(gd, "sellsword", RNG(1)); a1.health = 5
    a2 = combat.spawn_companion(gd, "shieldmaiden", RNG(2)); a2.health = 5
    battle = {"allies": [a1, a2]}
    magic.cast(c, gd, "healing_circle", RNG(1), battle=battle)
    assert a1.health > 5 and a2.health > 5                    # 群療
    magic.cast(c, gd, "regen_aura", RNG(1), battle=battle)
    assert any(e["kind"] == "regen" for e in a1.active_effects)   # 群體再生


# --- 騎士:號令 empower(同伴增傷,不碰玩家)-----------------------------
def test_rally_empowers_allies_not_player():
    gd, c = _melee(); c.spells.append("rally")
    ally = combat.spawn_companion(gd, "sellsword", RNG(1))
    magic.cast(c, gd, "rally", RNG(1), battle={"allies": [ally]})
    assert any(e["kind"] == "empower" for e in ally.active_effects)
    assert not any(e["kind"] == "empower" for e in c.active_effects)   # 玩家不受號令
    # empower 同伴傷害更高(對照無 empower)
    def ally_dmg(emp, seed):
        a = combat.spawn_companion(gd, "sellsword", RNG(99))
        if emp:
            a.active_effects = [{"kind": "empower", "magnitude": 0.25, "turns": 4}]
        foe = combat.spawn_creature(gd, "bandit", RNG(seed)); foe.resist = {}
        return combat.resolve_attack(a, foe, gd, RNG(seed))["damage"]
    assert sum(ally_dmg(True, s) for s in range(40)) > sum(ally_dmg(False, s) for s in range(40))


def test_empower_scales_with_caster_power():
    """號令增傷比照 heal/shield 吃施法 power → illusion 越高、鼓舞越強(對抗審查:補上對稱)。"""
    gd = get_gamedata()
    def emp_mag(illusion):
        _, c = _melee(); c.spells.append("rally"); c.skills["illusion"] = illusion
        ally = combat.spawn_companion(gd, "sellsword", RNG(1))
        magic.cast(c, gd, "rally", RNG(1), battle={"allies": [ally]})
        return next(e["magnitude"] for e in ally.active_effects if e["kind"] == "empower")
    assert emp_mag(150) > emp_mag(0) > 0                      # 高階騎士的號令更強(且恆 >0,不被取整成 0)


def test_empower_aggregates_as_max_not_sum():
    """🔴 平衡:反覆號令不疊乘暴衝 —— combat 以 max 聚合,三道 0.25 等同一道。"""
    gd = get_gamedata()
    def ally_dmg(n_emp, seed):
        a = combat.spawn_companion(gd, "sellsword", RNG(99))
        a.active_effects = [{"kind": "empower", "magnitude": 0.25, "turns": 4} for _ in range(n_emp)]
        foe = combat.spawn_creature(gd, "bandit", RNG(seed)); foe.resist = {}
        return combat.resolve_attack(a, foe, gd, RNG(seed))["damage"]
    one = sum(ally_dmg(1, s) for s in range(40))
    three = sum(ally_dmg(3, s) for s in range(40))
    none = sum(ally_dmg(0, s) for s in range(40))
    assert one > none and three == one                       # 一道有效;三道不超過一道(max 聚合)


def test_new_spells_are_accessible():
    """對抗審查抓到:8 新法術曾誤上架到海芬古而非帝都樞紐 → 確保中央可學 + 不被孤兒化。"""
    gd = get_gamedata()
    new = ("flame_blade", "frost_blade", "storm_blade", "heal_other",
           "healing_circle", "ward_ally", "regen_aura", "rally")
    stocks = {loc: set(d.get("spell_stock", [])) for loc, d in gd.world["locations"].items()}
    assert all(s in stocks["imperial_city"] for s in new)     # 帝都樞紐全備(中央可及)
    for s in new:                                             # 每道至少一處可學(不孤兒)
        assert any(s in stk for stk in stocks.values()), s


def test_empower_never_affects_player_even_if_present():
    """🔴 紅線:empower 即使誤掛在玩家身上也不放大玩家傷害(resolve_attack `not _is_player` 守門)。"""
    gd, c = _melee()
    foe = combat.spawn_creature(gd, "bandit", RNG(1)); foe.resist = {}
    plain = sum(combat.resolve_attack(_melee()[1], combat.spawn_creature(gd, "bandit", RNG(s)), gd, RNG(s))["damage"]
                for s in range(40))
    def with_emp(seed):
        _, m = _melee(); m.active_effects = [{"kind": "empower", "magnitude": 1.0, "turns": 4}]
        return combat.resolve_attack(m, combat.spawn_creature(gd, "bandit", RNG(seed)), gd, RNG(seed))["damage"]
    assert sum(with_emp(s) for s in range(40)) == plain        # 玩家 empower 零效果


# --- 弓手:散兵武技(aimed / crippling)----------------------------------
def test_aimed_shot_stronger_but_capped():
    gd, c = _melee(blade=0, weapon="hunting_bow")
    c.skills["marksman"] = 80
    def shot(aimed, seed):
        _, m = _melee(blade=0, weapon="hunting_bow"); m.skills["marksman"] = 80
        foe = combat.spawn_creature(gd, "bandit", RNG(seed)); foe.health = 999; foe.max_health = 999
        return combat.resolve_attack(m, foe, gd, RNG(seed), aimed=aimed)["damage"]
    assert sum(shot(True, s) for s in range(60)) > sum(shot(False, s) for s in range(60))   # 瞄準射更強
    # sneak-solo 仍受夾(aimed 補傷在夾限之前)
    boss = combat.spawn_creature(gd, "ancient_dragon", RNG(1))
    cap = boss.max_health * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO
    worst = 0
    for s in range(150):
        combat._set_hp(boss, boss.max_health)
        worst = max(worst, combat.resolve_attack(c, boss, gd, RNG(s), sneak_attack=True, aimed=True)["damage"])
    assert worst <= cap


# --- 摘要全涵蓋(無 fallback)--------------------------------------------
def test_all_new_spells_summarised():
    gd = get_gamedata()
    for s in ("flame_blade", "frost_blade", "storm_blade", "heal_other", "healing_circle",
              "ward_ally", "regen_aura", "rally"):
        summ = ui.spell_effect_summary(gd, s)
        assert summ and summ != "效果", (s, summ)


def test_class_signature_spells():
    gd = get_gamedata()
    for cid, sig in (("battlemage", "flame_blade"), ("healer", "heal_other"), ("knight", "rally")):
        c = build_character(gd, name="X", sex="male", race="breton", birthsign="mage", class_id=cid)
        assert sig in c.spells


def run():
    test_imbue_cast_sets_buff_and_adds_element()
    test_imbue_capped_on_sneak_solo_boss()
    test_ally_heal_in_battle_and_persists()
    test_ally_spell_needs_battle_and_living_ally()
    test_ally_aoe_heal_and_regen_aura()
    test_rally_empowers_allies_not_player()
    test_empower_scales_with_caster_power()
    test_empower_aggregates_as_max_not_sum()
    test_new_spells_are_accessible()
    test_empower_never_affects_player_even_if_present()
    test_aimed_shot_stronger_but_capped()
    test_all_new_spells_summarised()
    test_class_signature_spells()


if __name__ == "__main__":
    run()
    print("test_hybrids OK")
