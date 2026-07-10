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


def test_empower_aggregates_diminishing_not_sum():
    """🔴 平衡(R39):empower 多源**遞減疊加**(降序 1/0.7/0.49…)—— 戰旗+號令可同時生效,
    但三道 0.25 遞減 < 純相加(SUM),防暴衝;單道仍等同舊行為。"""
    gd = get_gamedata()
    def ally_dmg(n_emp, seed):
        a = combat.spawn_companion(gd, "sellsword", RNG(99))
        a.active_effects = [{"kind": "empower", "magnitude": 0.25, "turns": 4} for _ in range(n_emp)]
        foe = combat.spawn_creature(gd, "bandit", RNG(seed)); foe.resist = {}
        return combat.resolve_attack(a, foe, gd, RNG(seed))["damage"]
    none = sum(ally_dmg(0, s) for s in range(40))
    one = sum(ally_dmg(1, s) for s in range(40))
    three = sum(ally_dmg(3, s) for s in range(40))
    assert one > none                                        # 單道有效(×1.25)
    assert three > one                                       # 多源遞減疊加 → 有感(非舊 MAX 的「等同一道」)
    assert (three - none) < (one - none) * 3                 # 但 < SUM(0.7 遞減曲線,防暴衝)


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


def test_volley_damage_factor_and_gating_r136():
    """R136 箭雨:damage_factor 0.6 → 每箭顯著弱於全力一箭(預設 1.0 = 行為不變);
    marksman_75 選 volley_shot → has_bow_technique('volley') 解鎖(與 aimed 真二選一)。"""
    gd, c = _melee(blade=0, weapon="hunting_bow")
    c.skills["marksman"] = 80
    def shot(factor, seed):
        _, m = _melee(blade=0, weapon="hunting_bow"); m.skills["marksman"] = 80
        foe = combat.spawn_creature(gd, "bandit", RNG(seed)); foe.health = 999; foe.max_health = 999
        return combat.resolve_attack(m, foe, gd, RNG(seed), damage_factor=factor)["damage"]
    full = sum(shot(1.0, s) for s in range(80))
    weak = sum(shot(formulas.VOLLEY_DAMAGE_FACTOR, s) for s in range(80))
    assert weak < full * 0.75                                # 0.6 係數確實生效(命中/骰同序 → 直接可比)
    # 解鎖走 bow_technique(75 節點:瞄準 vs 箭雨 真二選一)
    gd2, m2 = _melee(blade=0, weapon="hunting_bow")
    m2.skills["marksman"] = 80
    from tesrpg.systems import mastery as M
    M.choose(m2, gd2, "marksman_75", "volley_shot")
    assert M.has_bow_technique(m2, gd2, "volley") and not M.has_bow_technique(m2, gd2, "aimed")


def test_rapid_shot_extra_shot_param_r136():
    """R136 連珠箭(marksman_100 取代已死的 penetrator):weapon_mod 聚合出 extra_shot 0.2;
    非弓手/未選 → 0(main/sim 依此不擲 rng → 紅線/byte-identity 基石)。"""
    gd, c = _melee(blade=0, weapon="hunting_bow")
    c.skills["marksman"] = 100
    from tesrpg.systems import mastery as M
    assert M.weapon_mod(c, gd, "marksman").get("extra_shot", 0.0) == 0.0   # 未選 → 0
    M.choose(c, gd, "marksman_100", "rapid_shot")
    assert M.weapon_mod(c, gd, "marksman").get("extra_shot") == 0.2
    assert M.weapon_mod(c, gd, "blade").get("extra_shot", 0.0) == 0.0     # target 限 marksman


def test_hunters_eye_exploit_conditional_r136():
    """R136 獵手之眼(marksman_100 另一側取代平淡的 steady_aim):目標帶控場狀態 → 弓傷 +20%;
    無控場 → 無加成;dot 刻意不觸發(附魔/塗毒不可自我點燃);偷襲對 solo 仍受夾。"""
    from tesrpg.systems import mastery as M
    def dmg(status_kind, seed, choose=True):
        gd2, m = _melee(blade=0, weapon="hunting_bow"); m.skills["marksman"] = 100
        if choose:
            M.choose(m, gd2, "marksman_100", "hunters_eye")
        foe = combat.spawn_creature(gd2, "bandit", RNG(seed)); foe.health = 999; foe.max_health = 999
        if status_kind:
            foe.active_effects.append({"kind": status_kind, "magnitude": 0.3, "turns": 2})
        return combat.resolve_attack(m, foe, gd2, RNG(seed))["damage"]
    base = sum(dmg(None, s) for s in range(80))
    exploited = sum(dmg("weaken", s) for s in range(80))
    dotted = sum(dmg("dot", s) for s in range(80))
    assert exploited > base * 1.1                      # 控場中 → 有感加成
    assert dotted == base                              # dot 不觸發(同骰序 → 應相等)
    # 偷襲 + exploit 對 solo 仍受夾(power_bonus 車道在夾前)
    gd3, c = _melee(blade=0, weapon="hunting_bow"); c.skills["marksman"] = 100
    M.choose(c, gd3, "marksman_100", "hunters_eye")
    boss = combat.spawn_creature(gd3, "ancient_dragon", RNG(1))
    boss.active_effects.append({"kind": "weaken", "magnitude": 0.3, "turns": 3})
    cap = boss.max_health * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO
    worst = 0
    for s in range(150):
        combat._set_hp(boss, boss.max_health)
        boss.active_effects[:] = [{"kind": "weaken", "magnitude": 0.3, "turns": 3}]
        worst = max(worst, combat.resolve_attack(c, boss, gd3, RNG(s), sneak_attack=True)["damage"])
    assert worst <= cap


def test_class_signature_spells():
    gd = get_gamedata()
    for cid, sig in (("battlemage", "flame_blade"), ("healer", "heal_other"), ("knight", "rally")):
        c = build_character(gd, name="X", sex="male", race="breton", birthsign="mage", class_id=cid)
        assert sig in c.spells


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_hybrids OK")
