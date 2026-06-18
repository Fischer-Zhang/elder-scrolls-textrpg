"""戰鬥系統的單元測試。"""

from collections import Counter

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
    # —— 吸收自 test_player_can_die_to_strong_foe(auto_resolve 敗北面)——
    # 用獨立角色實例 + 獨立 RNG,避免削血污染上方勝利+練功斷言
    _, c2 = _warrior()
    c2.health = c2.max_health = 12       # 削弱玩家、放一頭熊 → 應會落敗
    bear = combat.spawn_creature(gd, "bear", RNG(3))
    res = combat.auto_resolve(c2, bear, gd, RNG(3))
    assert res["winner"] in ("creature", "draw")
    if res["winner"] == "creature":
        assert not combat.is_alive(c2)


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


def test_block_skill_actually_read_in_combat():
    """格擋減傷的公式端點 + 效果端點合一驗證(公式層+效果層同機制)。

    公式層:block_damage_factor 隨格擋技能單調遞減、端點與夾限固定。
    效果層:同一 seed → 命中與傷害骰一致(格擋不影響命中),唯一變因是格擋技能。
    """
    # —— 吸收自 test_block_damage_factor_scales_with_skill(純公式端點)——
    assert formulas.block_damage_factor(0) == 0.9
    assert formulas.block_damage_factor(100) == 0.4
    assert (formulas.block_damage_factor(0) >
            formulas.block_damage_factor(50) >
            formulas.block_damage_factor(100))
    assert formulas.block_damage_factor(-10) == 0.9
    assert formulas.block_damage_factor(150) == 0.4
    gd, c = _warrior()
    foe = combat.spawn_creature(gd, "giant_rat", RNG(1))
    foe.attack["damage"] = 60     # 放大傷害 → 捨入後仍顯出技能差
    foe.attack["skill"] = 100

    def blocked_damage(block_skill, seed):
        c.skills["block"] = block_skill
        c.health = c.max_health
        before = c.health
        combat.resolve_attack(foe, c, gd, RNG(seed), defender_blocking=True)
        return before - c.health

    compared = 0
    for seed in range(50):
        low, high = blocked_damage(5, seed), blocked_damage(100, seed)
        if low > 0 and high > 0:          # 兩次都命中才可比較
            assert high < low, f"高格擋應更會擋:seed={seed} high={high} low={low}"
            compared += 1
    assert compared >= 5, "命中樣本不足,無法證明格擋縮放"


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
    """危險度越高,遭遇群體平均越大;且低危險度群體 ≤3 且以單體為主。"""
    gd, _ = _warrior()
    def avg(md, n=300):
        return sum(len(combat.random_encounter_group(gd, 1, RNG(s), max_danger=md))
                   for s in range(n)) / n
    assert avg(5) > avg(3) > avg(1)
    # —— 吸收自 test_m12.test_encounter_group_sizes ——
    # danger=3 時群體 ⊆{1,2,3}(≤3 上限,>3 敵潛匿壓制紅線相依的規模假設)
    # 且單體佔多數(分布形狀 pin)
    sizes = Counter(len(combat.random_encounter_group(gd, 3, RNG(i))) for i in range(300))
    assert set(sizes) <= {1, 2, 3} and sizes[1] > sizes[3]


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


def test_berserk_factor():
    """嗜血怒擊(維蘇拉德):滿血 ×1.0(開場偷襲不放大)、依已損生命線性提傷、封頂 magnitude%。"""
    gd, c = _warrior()
    c.max_health = 100
    c.health = 100
    assert formulas.berserk_factor(c, 30) == 1.0                  # 滿血不放大 → solo 偷襲安全
    c.health = 50
    assert abs(formulas.berserk_factor(c, 30) - 1.15) < 1e-9      # 半血 +15%
    c.health = 1
    assert formulas.berserk_factor(c, 30) <= 1.30 + 1e-9          # 瀕死封頂 +30%


def test_vampiric_fraction():
    """吸血比例:武器 enchant.magnitude(%)優先(悲傷之刃 50),缺省回 30%(向後相容)。"""
    assert formulas.vampiric_fraction({"magnitude": 50}) == 0.5
    assert formulas.vampiric_fraction({"status": "vampiric"}) == formulas.WEAPON_VAMPIRIC_FRACTION
    assert formulas.vampiric_fraction(None) == formulas.WEAPON_VAMPIRIC_FRACTION


def test_mace_builtin_stagger_and_solo_immune():
    """釘錘控制流:命中機率擊暈一般敵;solo boss 對控制免疫(R31 一致);斧無內建擊暈(只破甲)。"""
    gd, c = _warrior()
    c.skills["blunt"] = 100
    c.fatigue = c.max_fatigue = 400
    c.weapon = "steel_mace"
    # 一般敵:多次命中後至少一次觸發釘錘擊暈
    staggered = False
    for s in range(80):
        foe = combat.spawn_creature(gd, "bandit", RNG(s))
        foe.agility = 1; foe.health = foe.max_health = 600
        combat.resolve_attack(c, foe, gd, RNG(s))
        if any(e.get("kind") == "stagger" for e in foe.active_effects):
            staggered = True
            break
    assert staggered
    # solo boss:釘錘擊暈永不生效(控制免疫紅線)
    for s in range(120):
        boss = combat.spawn_creature(gd, "ancient_dragon", RNG(s))
        boss.agility = 1
        combat.resolve_attack(c, boss, gd, RNG(s))
        assert not any(e.get("kind") == "stagger" for e in boss.active_effects)
    # 斧:走破甲,無內建擊暈
    c.weapon = "steel_war_axe"
    for s in range(80):
        foe = combat.spawn_creature(gd, "bandit", RNG(s))
        foe.agility = 1; foe.health = foe.max_health = 600
        combat.resolve_attack(c, foe, gd, RNG(s))
        assert not any(e.get("kind") == "stagger" for e in foe.active_effects)


def test_reflect_r42_raw_decoupled_thorns_redlines():
    """R42 反傷流:荊棘聚合 5 槽、吃 raw(解耦護甲:高甲龜反傷仍是 raw 級而非 dmg_done 級)、元素不反、不一擊反殺。"""
    import tesrpg.synth as synth
    from tesrpg.systems import inventory, stats
    gd, c = _warrior()
    c.skills["heavy_armor"] = 100
    c.skills["block"] = 100
    c.health = c.max_health = 99999
    c.fatigue = c.max_fatigue = 9999
    # 全套魔族重甲(高減傷·小 dmg_done)+ 5 件大靈魂荊棘 → 總反傷 0.06+0.10+0.25 = 0.41
    for slot, base in (("helmet", "daedric_helmet"), ("cuirass", "daedric_cuirass"),
                       ("gauntlets", "daedric_gauntlets"), ("boots", "daedric_boots"), ("shield", "daedric_shield")):
        tid = synth.enchant_armor_id(base, "thorns", "", 5)
        inventory.add_item(c, tid, 1)
        inventory.equip_armor(c, gd, tid)
    stats.recompute_max_resources(c, gd)
    c.mastery_choices = {"heavy_armor_50": "armor_reflect", "block_50": "shieldwall"}
    assert abs(inventory.thorns_reflect(c, gd) - 0.25) < 1e-9          # 5 件聚合 = 25%

    def refl(foe_id, seed):
        foe = combat.spawn_creature(gd, foe_id, RNG(seed))
        foe.health = foe.max_health = 99999
        b = foe.health
        c.fatigue = 9999
        ev = combat.resolve_attack(foe, c, gd, RNG(seed))             # 敵打玩家 → 玩家反傷
        return b - foe.health, ev["damage"]

    # 解耦證明:高甲龜 dmg_done 被護甲壓小,但反傷仍 = raw×0.41(raw 級)→ 最大反傷 ≥12
    #   (若錯吃 dmg_done,反傷 = 0.41×小dmg_done,最大只 ~6 → 永遠到不了 12)
    reflects = [refl("werewolf_alpha", s)[0] for s in range(40)]
    assert max(reflects) >= 12
    # 紅線:元素敵攻(古龍)完全不反
    assert all(refl("ancient_dragon", s)[0] == 0 for s in range(15))
    # 紅線:不一擊反殺(0.41×raw〔max~17〕遠小於任何物理 boss HP)
    assert max(reflects) < 30


def run():
    test_formulas_monotonic()
    test_berserk_factor()
    test_vampiric_fraction()
    test_mace_builtin_stagger_and_solo_immune()
    test_reflect_r42_raw_decoupled_thorns_redlines()
    test_starter_weapon_assigned()
    test_player_beats_weak_creature_and_trains()
    test_sneak_attack_multiplies_damage()
    test_sneak_attack_trains_sneak_and_is_player_only()
    test_acrobatics_dodge_reduces_hit_chance()
    test_acrobatics_trains_on_dodge()
    test_athletics_reduces_combat_fatigue_and_block_costs()
    test_block_skill_actually_read_in_combat()
    test_elite_enemies_gated_by_min_level()
    test_group_size_scales_with_danger()
    test_boss_elites_appear_solo()


if __name__ == "__main__":
    run()
    print("test_combat OK")
