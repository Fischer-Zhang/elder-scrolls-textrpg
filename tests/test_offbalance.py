"""徒手「失衡 off-balance」warfare(落實 skills.json 招牌「耗損對手體力」死機制):
玩家徒手命中堆疊敵失衡層 → 層數放大後續徒手傷害(疊加提升傷害)+ 門檻踉蹌 / 滿頂罕見真擊倒。
鏡像 R75 conduct 疊層(暫態 active_effects·不入檔);只玩家徒手路徑讀寫 → sim 持匕首 byte-identical。
"""

import tempfile
from pathlib import Path

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, inventory, magic, mastery, progression, stats


def _monk(skill=100, race="khajiit", weapon="fists", grapple=False, armor=None):
    gd = get_gamedata()
    c = build_character(gd, name="僧", sex="m", race=race, birthsign="warrior", class_id="warrior")
    c.skills["hand_to_hand"] = skill
    c.attributes["strength"] = 100
    c.weapon = weapon
    if armor:                                  # R103:輕甲/重甲 gate 測試用
        inventory.add_item(c, armor, 1); inventory.equip_armor(c, gd, armor)
    if grapple:
        mastery.choose(c, gd, "hand_to_hand_50", "grapple")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.fatigue = c.max_fatigue
    return gd, c


def _dummy(gd, tid="bandit"):
    """巨血假人(不會死)→ 可連擊觀察失衡層;bandit 非 solo。"""
    foe = combat.spawn_creature(gd, tid, RNG(1))
    foe.health = foe.max_health = 10 ** 7
    foe.resist = {}
    return foe


# --- 疊層累積:徒手 ✓ / 匕首 ✗(byte-identity 單元守)--------------------
def test_offbalance_accumulates_on_unarmed_hit():
    gd, c = _monk(skill=100)
    foe = _dummy(gd)
    gain = formulas.offbalance_stack_gain(100)        # skill100 → 3/擊
    assert gain == 3
    prev = 0
    for i in range(3):
        combat.resolve_attack(c, foe, gd, RNG(50 + i))
        cur = magic.offbalance_stacks(foe)
        assert cur >= prev                            # 單調不減(夾 cap 前每擊 +gain)
        prev = cur
    assert magic.offbalance_stacks(foe) > 0


def test_offbalance_not_built_by_blade():
    """匕首/blade 路徑永不堆失衡 → sim 持匕首 byte-identical(鏡像 claw 紅線單元守)。"""
    gd, c = _monk(skill=100, weapon="steel_dagger")
    foe = _dummy(gd)
    for i in range(12):
        combat.resolve_attack(c, foe, gd, RNG(i))
    assert magic.offbalance_stacks(foe) == 0


# --- R103 gate:里程碑解鎖(hand_to_hand≥25)+ 未穿重甲 才累積失衡 --------
def test_offbalance_requires_milestone_unlock():
    """未達 25(里程碑未解鎖)→ 完全不累積失衡;達 25 → 解鎖累積。"""
    gd, low = _monk(skill=10)
    assert not mastery.has_offbalance_unlock(low, gd)
    foe = _dummy(gd)
    for i in range(6):
        combat.resolve_attack(low, foe, gd, RNG(i))
    assert magic.offbalance_stacks(foe) == 0
    gd, ok = _monk(skill=25)
    assert mastery.has_offbalance_unlock(ok, gd)
    foe2 = _dummy(gd)
    combat.resolve_attack(ok, foe2, gd, RNG(1))
    assert magic.offbalance_stacks(foe2) > 0


def test_offbalance_blocked_by_heavy_armor():
    """穿任何重甲件 → 不累積失衡;全輕甲 → 照常累積(輕裝武僧身份)。"""
    gd, heavy = _monk(skill=100, armor="iron_cuirass")        # 重甲
    assert inventory.wears_heavy_armor(heavy, gd)
    foe = _dummy(gd)
    for i in range(6):
        combat.resolve_attack(heavy, foe, gd, RNG(i))
    assert magic.offbalance_stacks(foe) == 0
    gd, light = _monk(skill=100, armor="leather_cuirass")     # 輕甲
    assert not inventory.wears_heavy_armor(light, gd)
    foe2 = _dummy(gd)
    combat.resolve_attack(light, foe2, gd, RNG(1))
    assert magic.offbalance_stacks(foe2) > 0


def test_offbalance_ramp_gated_off_in_heavy_armor():
    """重甲時失衡 ramp 不套用(即使敵已被預置失衡層)→ 傷害=無 ramp。"""
    def _measure(armor, seed, seeded):
        gd, c = _monk(skill=100, armor=armor)
        foe = _dummy(gd)
        if seeded:
            magic.add_offbalance(foe, formulas.OFFBALANCE_MAX_STACKS)
        return combat.resolve_attack(c, foe, gd, RNG(seed))["damage"]

    for seed in range(15):
        base = _measure("iron_cuirass", 900 + seed, False)     # 重甲·無 ramp 基準
        ramp = _measure("iron_cuirass", 900 + seed, True)      # 重甲·有預置層 → 仍不吃 ramp
        assert ramp == base
    # 對照:輕甲時預置層確實放大
    light_base = _measure("leather_cuirass", 950, False)
    light_ramp = _measure("leather_cuirass", 950, True)
    assert light_ramp >= light_base and (light_ramp > light_base or light_base == 0)


def test_offbalance_gain_scales_with_skill():
    assert formulas.offbalance_stack_gain(0) == 1
    assert formulas.offbalance_stack_gain(50) == 2
    assert formulas.offbalance_stack_gain(100) == 3
    assert formulas.offbalance_stack_gain(100, 0.6) == 5   # 擒拿手加速:round(3×1.6)


def test_offbalance_caps_at_max():
    gd, c = _monk(skill=100)
    foe = _dummy(gd)
    for i in range(40):
        combat.resolve_attack(c, foe, gd, RNG(i))
        # 滿頂可能機率真擊倒並重置 → 夾在 [0, MAX]
        assert 0 <= magic.offbalance_stacks(foe) <= formulas.OFFBALANCE_MAX_STACKS


def test_offbalance_clears_after_window():
    gd, c = _monk(skill=100)
    foe = _dummy(gd)
    magic.add_offbalance(foe, 5)
    assert magic.offbalance_stacks(foe) == 5
    for _ in range(formulas.OFFBALANCE_TURNS):     # 無新徒手命中 → 窗口耗盡整組清(非逐層遞減)
        magic.tick_effects(foe, gd)
    assert magic.offbalance_stacks(foe) == 0


# --- 傷害 ramp:對已失衡之敵徒手傷害放大(疊加提升傷害)------------------
def test_offbalance_damage_ramp_amplifies_unarmed():
    """同種子下,對已失衡之敵的徒手傷害嚴格大於對新生之敵(ramp 確實流入)。"""
    gd, c = _monk(skill=100)
    diffs = []
    for seed in range(30):
        fresh = _dummy(gd)
        seeded = _dummy(gd)
        magic.add_offbalance(seeded, formulas.OFFBALANCE_MAX_STACKS)   # 滿層 → ×(1+0.04×8)
        base = combat.resolve_attack(c, fresh, gd, RNG(200 + seed))["damage"]
        ramp = combat.resolve_attack(c, seeded, gd, RNG(200 + seed))["damage"]
        if base > 0:
            assert ramp >= base
            diffs.append(ramp - base)
    assert diffs and sum(diffs) > 0                 # 至少整體嚴格放大


def test_offbalance_ramp_not_applied_to_sneak_or_blade():
    """ramp 閘 not sneaking + hand_to_hand → 偷襲擊不吃 ramp、匕首不吃 ramp(守 R61 + solo 偷襲夾)。
    每次量測用新攻方,排除 learn-by-doing(偷襲訓練 sneak)漂移 → 唯一變因=失衡層。"""
    def _measure(weapon, seed, seeded_stacks, sneak):
        gd, c = _monk(skill=100, weapon=weapon)
        foe = _dummy(gd)
        if seeded_stacks:
            magic.add_offbalance(foe, seeded_stacks)
        return combat.resolve_attack(c, foe, gd, RNG(seed), sneak_attack=sneak)["damage"]

    for seed in range(15):                                    # 偷襲:失衡與否的偷襲傷害相同
        base = _measure("fists", 300 + seed, 0, True)
        ramp = _measure("fists", 300 + seed, formulas.OFFBALANCE_MAX_STACKS, True)
        assert ramp == base
    for seed in range(15):                                    # 匕首:ramp 永不套用(skill != hand_to_hand)
        base = _measure("steel_dagger", 400 + seed, 0, False)
        ramp = _measure("steel_dagger", 400 + seed, formulas.OFFBALANCE_MAX_STACKS, False)
        assert ramp == base


# --- 兩段 payoff:門檻踉蹌(軟控)/ 滿頂罕見真擊倒(硬控)----------------
def test_offbalance_threshold_triggers_stagger():
    gd, c = _monk(skill=100)
    foe = combat.spawn_creature(gd, "wolf", RNG(2))
    foe.health = foe.max_health = 10 ** 7
    staggered = False
    for i in range(6):
        combat.resolve_attack(c, foe, gd, RNG(60 + i))
        if any(e["kind"] == "stagger" and e.get("source") == "offbalance" and e["turns"] > 0
               for e in foe.active_effects):
            staggered = True
            break
    assert staggered


def test_offbalance_full_cap_can_knockdown_nonsolo():
    """滿頂時(非 solo)真擊倒(paralyze)可機率觸發 → 至少一次出現(機率 KNOCKDOWN_CHANCE)。"""
    gd, c = _monk(skill=100)
    seen_paralyze = False
    for trial in range(60):
        foe = _dummy(gd, "wolf")
        magic.add_offbalance(foe, formulas.OFFBALANCE_MAX_STACKS)   # 預置滿層
        combat.resolve_attack(c, foe, gd, RNG(700 + trial))
        if any(e["kind"] == "paralyze" and e["turns"] > 0 for e in foe.active_effects):
            seen_paralyze = True
            break
    assert seen_paralyze


def test_offbalance_knockdown_solo_probabilistic():
    """滿頂真擊倒對 solo BOSS 走 apply_control → 機率抵抗(既非永鎖亦非永免)。"""
    gd, c = _monk(skill=100)
    boss_id = "mehrunes_dagon"
    applied, n = 0, 600
    for s in range(n):
        boss = combat.spawn_creature(gd, boss_id, RNG(s))
        boss.health = boss.max_health = 10 ** 7
        magic.add_offbalance(boss, formulas.OFFBALANCE_MAX_STACKS)
        combat.resolve_attack(c, boss, gd, RNG(800 + s))
        if any(e["kind"] == "paralyze" and e["turns"] > 0 for e in boss.active_effects):
            applied += 1
    rate = applied / n
    # 期望 ≈ KNOCKDOWN_CHANCE × (1 - SOLO_CONTROL_RESIST_CHANCE)，介於 0 與 1(非永鎖)
    expect = formulas.OFFBALANCE_KNOCKDOWN_CHANCE * (1 - formulas.SOLO_CONTROL_RESIST_CHANCE)
    assert 0 < rate < 0.5
    assert abs(rate - expect) < 0.06


# --- 里程碑「擒拿手」失衡加速 + 對非徒手中性 -----------------------------
def test_grapple_poise_rate_in_weapon_mod():
    gd, c = _monk(skill=100, grapple=True)
    wm = mastery.weapon_mod(c, gd, "hand_to_hand")
    assert abs(wm.get("poise_rate", 0.0) - 0.6) < 1e-9
    # 對非徒手武器技能中性(target 不符)
    assert mastery.weapon_mod(c, gd, "blade").get("poise_rate", 0.0) == 0.0


def test_grapple_accelerates_offbalance():
    """擒拿手:同樣命中數下,失衡層數嚴格多於無擒拿手(加速確實流入)。"""
    gd_a, plain = _monk(skill=100, grapple=False)
    gd_b, grap = _monk(skill=100, grapple=True)
    foe_a = _dummy(gd_a); foe_b = _dummy(gd_b)
    combat.resolve_attack(plain, foe_a, gd_a, RNG(10))
    combat.resolve_attack(grap, foe_b, gd_b, RNG(10))
    assert magic.offbalance_stacks(foe_b) > magic.offbalance_stacks(foe_a)


# --- 存檔:失衡層暫態不入檔 + 舊存檔 grappler 遷移退 pending ------------
def test_offbalance_not_persisted():
    gd, c = _monk(skill=100)
    c.active_effects = [{"kind": "offbalance", "stacks": 6, "turns": 3}]
    st = GameState(player=c, time=GameTime())
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        st.save(p)
        lo = GameState.load(p)
    assert lo.player.active_effects == []


def test_grappler_choice_retired_on_load():
    """opt_id grappler→grapple 改名 → 舊存檔選 grappler 自動退 pending(守選擇權·無新存檔欄)。"""
    gd, c = _monk(skill=100)
    c.mastery_choices = {"hand_to_hand_50": "grappler"}     # 舊存檔陳舊選擇
    progression.ensure_mastery_choices(c, gd)
    assert "hand_to_hand_50" not in c.mastery_choices       # 退 pending
    assert c.mastery_skill_bonus.get("hand_to_hand", 0) == 0  # 舊 +8 快取不再產出


def run():
    for name in sorted(globals()):
        if name.startswith("test_"):
            globals()[name]()
