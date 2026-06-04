"""戰鬥系統的單元測試。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat


def _warrior():
    gd = get_gamedata()
    c = build_character(gd, name="Conan", sex="male", race="redguard",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_formulas_monotonic():
    # 技能越高命中越高
    assert (formulas.hit_chance(20, 40, 40, 1.0) <
            formulas.hit_chance(80, 40, 40, 1.0))
    # 低體力降低命中
    assert (formulas.hit_chance(50, 40, 40, 0.1) <
            formulas.hit_chance(50, 40, 40, 1.0))
    # 護甲減傷且不為負、至少 1
    assert formulas.damage_after_armor(10, 0) == 10
    assert 1 <= formulas.damage_after_armor(10, 100) < 10
    assert formulas.damage_after_armor(0.1, 0) == 1.0


def test_starter_weapon_assigned():
    gd, c = _warrior()
    wp = gd.weapons[c.weapon]
    # 紅衛戰士擅長刀劍 → 配發劍類
    assert wp["skill"] == "blade"


def test_spawn_and_loot():
    gd, _ = _warrior()
    rng = RNG(1)
    cr = combat.spawn_creature(gd, "wolf", rng)
    assert cr.name == "野狼" and cr.health > 0 and cr.health == cr.max_health


def test_player_beats_weak_creature_and_trains():
    gd, c = _warrior()
    rng = RNG(7)
    wpn_skill = gd.weapons[c.weapon]["skill"]
    skill_before = c.skill(wpn_skill)
    rat = combat.spawn_creature(gd, "giant_rat", rng)
    result = combat.auto_resolve(c, rat, gd, rng)
    assert result["winner"] == "player"
    # 靠戰鬥練了武器技能(learn-by-doing)
    assert c.skill_xp[wpn_skill] > 0 or c.skill(wpn_skill) > skill_before


def test_player_can_die_to_strong_foe():
    gd, c = _warrior()
    # 削弱玩家、放一頭熊 → 應會落敗
    c.health = 12
    c.max_health = 12
    rng = RNG(3)
    bear = combat.spawn_creature(gd, "bear", rng)
    result = combat.auto_resolve(c, bear, gd, rng)
    assert result["winner"] in ("creature", "draw")
    if result["winner"] == "creature":
        assert not combat.is_alive(c)


def test_resolve_attack_applies_damage():
    gd, c = _warrior()
    rng = RNG(0)
    rat = combat.spawn_creature(gd, "giant_rat", rng)
    hp0 = rat.health
    # 強制命中:把玩家武器技能拉高、用多次直到命中
    landed = False
    for _ in range(20):
        ev = combat.resolve_attack(c, rat, gd, rng)
        if ev["hit"]:
            landed = True
            assert ev["damage"] >= 1
            assert rat.health < hp0
            break
    assert landed


def test_sneak_attack_multiplies_damage():
    """開場偷襲依潛行加成傷害,且明顯高於同條件的普通攻擊。"""
    gd, c = _warrior()
    c.skills["sneak"] = 100                      # ×4 倍率,差異明顯
    for seed in range(40):
        # 同 seed → 命中與骰值相同,差別只在偷襲倍率
        foe_n = combat.spawn_creature(gd, "bandit", RNG(seed))
        n = combat.resolve_attack(c, foe_n, gd, RNG(seed))
        foe_s = combat.spawn_creature(gd, "bandit", RNG(seed))
        s = combat.resolve_attack(c, foe_s, gd, RNG(seed), sneak_attack=True)
        if n["hit"] and s["hit"]:
            assert s["sneak"] == formulas.sneak_attack_multiplier(100)
            assert s["damage"] > n["damage"], (n["damage"], s["damage"])
            return
    raise AssertionError("找不到雙方都命中的種子")


def test_sneak_attack_trains_sneak_and_is_player_only():
    """偷襲命中會鍛鍊潛行(戰鬥中成長);怪物不會觸發偷襲。"""
    gd, c = _warrior()
    s0 = c.skill("sneak")
    for i in range(60):
        foe = combat.spawn_creature(gd, "bandit", RNG(i))
        combat.resolve_attack(c, foe, gd, RNG(i), sneak_attack=True)
    assert c.skill("sneak") > s0                 # 潛行在戰鬥中成長
    # 怪物攻擊玩家即使傳 sneak_attack=True 也不應觸發(_is_player 守門)
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    ev = combat.resolve_attack(foe, c, gd, RNG(1), sneak_attack=True)
    assert ev["sneak"] is None


def test_acrobatics_dodge_reduces_hit_chance():
    """雜技閃避降低敵人命中率;閃避量隨技能遞增且不為負。"""
    base = formulas.hit_chance(60, 40, 40, 1.0)
    dodged = formulas.hit_chance(60, 40, 40, 1.0,
                                 defender_evasion=formulas.dodge_evasion(100))
    assert dodged < base
    assert formulas.dodge_evasion(100) > formulas.dodge_evasion(40) > formulas.dodge_evasion(0) == 0


def test_acrobatics_trains_on_dodge():
    """敵人攻擊落空(玩家成功閃避)→ 鍛鍊雜技;且不會因怪物無 skill() 而出錯。"""
    gd, c = _warrior()
    c.skills["acrobatics"] = 50
    a0 = c.skill("acrobatics")
    saw_dodge_event = False
    for i in range(200):
        foe = combat.spawn_creature(gd, "bandit", RNG(i))
        ev = combat.resolve_attack(foe, c, gd, RNG(i))   # 怪物打玩家
        c.health = c.max_health
        if not ev["hit"] and any(e.get("skill") == "acrobatics" for e in ev["skill_events"]):
            saw_dodge_event = True
    assert saw_dodge_event, "成功閃避應鍛鍊雜技"
    assert c.skill("acrobatics") > a0
    # 玩家攻擊怪物:defender 是怪物 → 不套用/不查 acrobatics(不應出錯)
    rat = combat.spawn_creature(gd, "giant_rat", RNG(1))
    combat.resolve_attack(c, rat, gd, RNG(1))


def test_athletics_reduces_combat_fatigue_and_block_costs():
    """運動降低攻擊/格擋體力消耗;格擋現在確實會扣體力(原本是死常數)。"""
    gd, c = _warrior()
    assert formulas.fatigue_cost_factor(0) == 1.0
    assert formulas.fatigue_cost_factor(100) < formulas.fatigue_cost_factor(0)

    def spent(cost_fn, athletics):
        c.skills["athletics"] = athletics
        c.fatigue = c.max_fatigue
        before = c.fatigue
        cost_fn(c)
        return before - c.fatigue

    # 攻擊:運動 0 = 名目;運動高 → 更省
    assert spent(combat.player_attack_cost, 0) == formulas.ATTACK_FATIGUE_COST
    assert spent(combat.player_attack_cost, 100) < formulas.ATTACK_FATIGUE_COST
    # 格擋:現在真的會扣(過去 BLOCK_FATIGUE_COST 未被引用 = 0)
    assert spent(combat.player_block_cost, 0) == formulas.BLOCK_FATIGUE_COST
    assert 0 < spent(combat.player_block_cost, 100) < formulas.BLOCK_FATIGUE_COST


def test_elite_enemies_gated_by_min_level():
    """高階 elite 受 min_level 把關:低等玩家不會遇到,高等玩家在高危區會遇到。"""
    gd, _ = _warrior()
    ELITE = {"frost_troll", "storm_atronach", "daedroth", "lich",
             "dremora_lord", "frost_giant", "ancient_dragon"}
    low = {combat.random_encounter(gd, 3, RNG(s), max_danger=5).template_id for s in range(300)}
    assert not (low & {"dremora_lord", "frost_giant", "ancient_dragon"}), "低等玩家不該遇到高階 elite"
    high = {combat.random_encounter(gd, 16, RNG(s), max_danger=5).template_id for s in range(400)}
    assert high & ELITE, "高等玩家在高危區應能遇到 elite"


def test_group_size_scales_with_danger():
    """危險度越高,遭遇群體平均越大。"""
    gd, _ = _warrior()
    def avg(md, n=300):
        return sum(len(combat.random_encounter_group(gd, 1, RNG(s), max_danger=md))
                   for s in range(n)) / n
    assert avg(5) > avg(3) > avg(1)


def test_boss_elites_appear_solo():
    """BOSS 級(solo)敵人一次只單獨出現,不成群、不與雜兵同場。"""
    gd, _ = _warrior()
    SOLO = {"dremora_lord", "frost_giant", "ancient_dragon"}
    saw = False
    for s in range(800):
        g = combat.random_encounter_group(gd, 16, RNG(s), max_danger=5)
        ids = [e.template_id for e in g]
        if any(i in SOLO for i in ids):
            saw = True
            assert len(g) == 1, f"BOSS 不應與他人同場:{ids}"
    assert saw, "高等危險區應曾遇到 solo BOSS"


def run():
    test_formulas_monotonic()
    test_starter_weapon_assigned()
    test_spawn_and_loot()
    test_player_beats_weak_creature_and_trains()
    test_player_can_die_to_strong_foe()
    test_resolve_attack_applies_damage()
    test_sneak_attack_multiplies_damage()
    test_sneak_attack_trains_sneak_and_is_player_only()
    test_acrobatics_dodge_reduces_hit_chance()
    test_acrobatics_trains_on_dodge()
    test_athletics_reduces_combat_fatigue_and_block_costs()
    test_elite_enemies_gated_by_min_level()
    test_group_size_scales_with_danger()
    test_boss_elites_appear_solo()


if __name__ == "__main__":
    run()
    print("test_combat OK")
