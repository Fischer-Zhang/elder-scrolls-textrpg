"""八職功能性身份網格 —— 各職一招牌戰術 loop 的測試:
warrior 盾牆(減傷+嘲諷,物理only)/ mage 奧術連鎖(連發增幅·省體·cap)/ thief 諜報偵搜(prep 多來源相加)/
battlemage 共鳴一擊+法力回擊(50/75 兩節點可兼得;夾限內·DoT·單次·回魔)/ archer 獵手偵察(recon floor)/
knight 戰旗(empower 僅同伴·不碰玩家)/ healer 戰地搶救(折扣施治·消耗)/ assassin 致命烙印(開場免疫·follow-up 破甲)。
🔴 紅線:任何機制皆不可使偷襲秒 solo boss(combat 夾限);sim_assassin 另證逐行零位移。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic, mastery

gd = get_gamedata()


def _char(cls="warrior", **skills):
    c = build_character(gd, name="t", sex="male", race="nord", birthsign="warrior", class_id=cls)
    c.skills.update(**skills)
    c.magicka = c.max_magicka = 99999
    c.fatigue = c.max_fatigue = 9999
    c.health = c.max_health = 400
    return c


def _dummy(tid="bandit", hp=99999, armor=10):
    d = combat.spawn_creature(gd, tid, RNG(2))
    d.health = d.max_health = hp
    d.armor_rating = armor
    return d


# --- mage: 奧術連鎖 ----------------------------------------------------
def test_cascade_getters_scale_and_cap_and_neutral():
    c = _char("mage", mysticism=80, destruction=90)
    assert mastery.cascade_power(c, gd) == 0.0 and mastery.cascade_fatigue_factor(c, gd) == 1.0  # 未選=中性
    mastery.choose(c, gd, "mysticism_75", "arcane_cascade")
    # 依層數的確定性加成(避開法力/體力四捨五入)
    c.active_effects[:] = [{"kind": "cascade", "magnitude": 1, "turns": 3}]
    assert abs(mastery.cascade_power(c, gd) - 0.08) < 1e-9
    assert abs(mastery.cascade_fatigue_factor(c, gd) - 0.88) < 1e-9
    c.active_effects[:] = [{"kind": "cascade", "magnitude": 2, "turns": 3}]
    assert abs(mastery.cascade_power(c, gd) - 0.16) < 1e-9
    assert abs(mastery.cascade_fatigue_factor(c, gd) - 0.76) < 1e-9
    # 併入 bump 遞增+cap 面(獨立 setup:另建帶 flames 的 char,走真正 magic.cast 驅動 _cascade_depth,
    # 不重用上段以避開法力/體力四捨五入稀釋 getter 數值斷言)
    c2 = _char("mage", mysticism=80, destruction=80)
    c2.spells = list(c2.spells) + ["flames"]
    mastery.choose(c2, gd, "mysticism_75", "arcane_cascade")
    c2.magicka = c2.max_magicka = 99999          # choose 觸發重算 → 此處補滿
    assert mastery._cascade_depth(c2) == 0
    magic.cast(c2, gd, "flames", RNG(1), target=_dummy())   # 施法 → bump
    assert mastery._cascade_depth(c2) == 1
    for _ in range(4):
        magic.cast(c2, gd, "flames", RNG(1), target=_dummy())
    assert mastery._cascade_depth(c2) == 2        # cap depth 2


# --- battlemage: 共鳴一擊 + 法力回擊 -----------------------------------
def test_resonant_strike_adds_element_dot_single_use():
    c = _char("battlemage", destruction=80, blade=60)
    c.weapon = "steel_sword"
    spell = next(s for s, v in gd.spells.items()
                 if v.get("effect", {}).get("kind") in ("damage", "damage_status") and v["school"] == "destruction")
    c.spells = list(c.spells) + [spell]
    mastery.choose(c, gd, "destruction_50", "resonant_strike")
    c.magicka = c.max_magicka = 99999            # choose 觸發重算 → 補滿
    foe = _dummy()
    base = combat.resolve_attack(c, foe, gd, RNG(5))["damage"]
    magic.cast(c, gd, spell, RNG(1), target=foe)
    assert any(e["kind"] == "resonance" for e in c.active_effects)
    ev = combat.resolve_attack(c, foe, gd, RNG(5))
    assert ev["damage"] > base                                  # 近戰灌入法傷
    assert any(e["kind"] == "dot" for e in foe.active_effects)  # 引燃 DoT
    assert not any(e["kind"] == "resonance" for e in c.active_effects)  # 單次用後移除


def test_resonant_strike_respects_solo_clamp():
    # 🔴 即便 resonance magnitude 巨大,solo boss 開場偷襲仍被夾、不死
    c = _char("battlemage", blade=80); c.weapon = "steel_sword"
    boss = next(t for t in gd.bestiary if gd.bestiary[t].get("solo"))
    sb = combat.spawn_creature(gd, boss, RNG(3))
    c.active_effects.append({"kind": "resonance", "element": "fire", "magnitude": 99999,
                             "dot_magnitude": 4, "dot_turns": 3, "turns": 2})
    ev = combat.resolve_attack(c, sb, gd, RNG(5), sneak_attack=True)
    assert ev["damage"] <= sb.max_health * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO + 1
    assert sb.health > 0


def test_mana_on_hit_restores_magicka_and_neutral():
    c = _char("battlemage", destruction=80, blade=60); c.weapon = "steel_sword"
    assert mastery.mana_on_hit(c, gd) == 0                        # 未選=中性
    mastery.choose(c, gd, "destruction_75", "arcane_battery")
    assert mastery.mana_on_hit(c, gd) == 4
    c.magicka = 10
    combat.resolve_attack(c, _dummy(), gd, RNG(1))
    assert c.magicka > 10                                         # 命中回魔


def test_resonant_rider_applies_resist_once():
    # 修 double-dip:rider 存抗性未折算基底、打擊端折算一次 → 弱火目標淨灌注 ≈ 半數實際法傷
    # (修前存折算後值再×mult → 弱點 2.0 時灌到整份法傷)
    c = _char("battlemage", destruction=80, blade=60); c.weapon = "steel_sword"
    c.spells = list(c.spells) + ["fireball"]
    mastery.choose(c, gd, "destruction_50", "resonant_strike")
    c.magicka = c.max_magicka = 99999
    foe = _dummy(); foe.resist = {"fire": -100}                   # 弱火 → mult 夾頂 2.0
    base = combat.resolve_attack(c, foe, gd, RNG(5))["damage"]
    spell_dmg = magic.cast(c, gd, "fireball", RNG(1), target=foe)["damage"]
    rider = combat.resolve_attack(c, foe, gd, RNG(5))["damage"] - base
    assert abs(rider - spell_dmg * 0.5) <= 3                      # 修前 ≈ spell_dmg(兩倍灌注)


def test_battlemage_can_hold_both_resonance_perks():
    # 共鳴一擊移 50、省魔催動移 75:爆發流+自持流不再互斥,戰法師 50/75 可雙取
    c = _char("battlemage", destruction=80, blade=60); c.weapon = "steel_sword"
    assert mastery.choose(c, gd, "destruction_50", "resonant_strike") is not None
    assert mastery.choose(c, gd, "destruction_75", "arcane_battery") is not None
    assert mastery.resonant_strike(c, gd) is not None
    assert mastery.mana_on_hit(c, gd) == 4
    # 純法師側互換後仍成對:50 凝神聚法 ⇄ 75 省魔催動(各節點皆一法一武)
    m = _char("mage", destruction=80)
    assert mastery.choose(m, gd, "destruction_50", "focused_mind") is not None
    assert mastery.choose(m, gd, "destruction_75", "efficient_destruction") is not None
    assert abs(mastery.spell_cost_factor(m, gd, "destruction") - 0.85) < 1e-9


# --- thief: 諜報偵搜(prep 多來源相加)-------------------------------
# test_subterfuge_prep_bonus_sums_with_scout 已併入 test_mastery.test_scout_prep_and_recon
# (跨模組 D 併:該 into 已驗 prep_bonus 多源相加;此處 subterfuge_intel 來源 pin 由 into agent 落地)


# --- archer: 散兵戰技(里程碑解鎖,取代「裝備弓即免費全給」)----------
def test_bow_technique_unlock():
    c = _char("archer", marksman=80)
    # 未選任何 marksman 里程碑 → 三式皆未解鎖(不再「持弓即免費」)
    assert not mastery.has_bow_technique(c, gd, "skirmish")
    assert not mastery.has_bow_technique(c, gd, "crippling")
    assert not mastery.has_bow_technique(c, gd, "aimed")
    # marksman_50 二選一:散兵走位 vs 牽制射(互斥)
    mastery.choose(c, gd, "marksman_50", "crippling_shot")
    assert mastery.has_bow_technique(c, gd, "crippling")
    assert not mastery.has_bow_technique(c, gd, "skirmish")   # 互斥:選了牽制就拿不到走位
    # marksman_75 二選一:瞄準射(對 疾矢)
    mastery.choose(c, gd, "marksman_75", "aimed_shot")
    assert mastery.has_bow_technique(c, gd, "aimed")


# --- warrior: 盾牆 ---------------------------------------------------
def test_shield_wall_taunt_and_detection():
    c = _char("warrior", block=60)
    assert not combat.has_shield_wall(c)
    c.active_effects.append({"kind": "shield_wall", "mitigation": 0.30, "turns": 99})
    assert combat.has_shield_wall(c)
    assert abs(combat._shield_wall_factor(c) - 0.70) < 1e-9
    ally = combat.spawn_creature(gd, "wolf", RNG(1))
    assert all(combat.pick_player_side_target(c, [ally], RNG(i)) is c for i in range(12))  # 嘲諷鎖坦


def _strong():
    a = combat.spawn_creature(gd, "bandit", RNG(1))
    a.strength = 80
    a.attack = {"name": "x", "damage": 30, "skill": 100}
    return a


def test_shield_wall_mitigation_physical_only():
    target = _char("warrior", block=60); target.max_health = 99999; target.health = 99999
    foe = _strong()
    d_open = combat.resolve_attack(foe, target, gd, RNG(9))["damage"]
    target.active_effects.append({"kind": "shield_wall", "mitigation": 0.30, "turns": 99})
    d_wall = combat.resolve_attack(foe, target, gd, RNG(9))["damage"]
    assert d_wall < d_open                                        # 物理減傷生效
    # 元素攻擊穿透盾牆(不減)
    efoe = _strong(); efoe.attack["element"] = "fire"
    target.active_effects = []
    e_open = combat.resolve_attack(efoe, target, gd, RNG(9))["damage"]
    target.active_effects.append({"kind": "shield_wall", "mitigation": 0.30, "turns": 99})
    e_wall = combat.resolve_attack(efoe, target, gd, RNG(9))["damage"]
    assert e_wall == e_open                                       # 元素不受盾牆影響


# --- knight: 戰旗(empower 僅同伴,不碰玩家)-------------------------
def test_standard_empower_allies_only_not_player():
    # 戰旗複用 empower 路徑:同伴(非玩家)帶 empower 增傷,玩家自身帶 empower 不增傷(紅線守門)
    ally = combat.spawn_creature(gd, "wolf", RNG(1))   # 任一非玩家 Creature 即可
    foe = _dummy(armor=0)
    base = combat.resolve_attack(ally, foe, gd, RNG(4))["damage"]
    ally.active_effects.append({"kind": "empower", "magnitude": 0.25, "turns": 1, "source": "standard"})
    boosted = combat.resolve_attack(ally, foe, gd, RNG(4))["damage"]
    assert boosted > base                                        # 同伴受惠
    # 玩家帶同樣 empower → 不受惠(combat 端 not _is_player 守門)
    p = _char("knight", blade=80); p.weapon = "steel_sword"
    pf = _dummy(armor=0)
    pbase = combat.resolve_attack(p, pf, gd, RNG(4))["damage"]
    p.active_effects.append({"kind": "empower", "magnitude": 0.25, "turns": 1, "source": "standard"})
    pboost = combat.resolve_attack(p, pf, gd, RNG(4))["damage"]
    assert pboost == pbase                                       # 🔴 玩家不受 empower(紅線)


# --- healer: 戰地搶救 ------------------------------------------------
def test_triage_discounts_heal_and_consumes():
    c = _char("healer", restoration=80)
    assert mastery.triage(c, gd) is None
    mastery.choose(c, gd, "restoration_50", "triage")
    c.magicka = c.max_magicka = 99999            # choose 觸發重算 → 補滿
    assert mastery.triage(c, gd) is not None
    ally_spell = next((s for s, v in gd.spells.items() if v.get("target") in ("ally", "allies")), None)
    assert ally_spell, "需要一道盟友指向治療術"
    hurt = combat.spawn_creature(gd, "wolf", RNG(1)); hurt.health = 1
    battle = {"allies": [hurt]}
    full_cost = magic.effective_cost(c, gd, ally_spell)
    c.active_effects.append({"kind": "triage_ready", "turns": 2})
    before = c.magicka
    magic.cast(c, gd, ally_spell, RNG(1), target=hurt, battle=battle)
    spent = before - c.magicka
    assert spent < full_cost                                     # 折扣施法
    assert not any(e["kind"] == "triage_ready" for e in c.active_effects)  # 消耗旗標
    # 第二道恢恢復價
    before2 = c.magicka
    magic.cast(c, gd, ally_spell, RNG(1), target=hurt, battle=battle)
    assert before2 - c.magicka >= full_cost - 1


# --- assassin: 致命烙印 ----------------------------------------------
def test_deathmark_opener_immune_solo_clamp_holds():
    c = _char("assassin", sneak=90, blade=90); c.weapon = "steel_dagger"
    mastery.choose(c, gd, "sneak_50", "deathmark")
    boss = next(t for t in gd.bestiary if gd.bestiary[t].get("solo"))
    sb = combat.spawn_creature(gd, boss, RNG(6))
    sb.active_effects.append({"kind": "deathmark", "turns": 4})   # 已標記
    ev = combat.resolve_attack(c, sb, gd, RNG(2), sneak_attack=True)
    # 🔴 開場偷襲:not sneaking 守門 → 破甲不生效 → solo 夾限仍夾、不死
    assert ev["damage"] <= sb.max_health * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO + 1
    assert sb.health > 0


def test_deathmark_followup_penetrates_armor():
    c = _char("assassin", sneak=90, blade=90); c.weapon = "steel_dagger"
    mastery.choose(c, gd, "sneak_50", "deathmark")
    hi = _dummy("bandit", hp=99999, armor=40)
    nomark = combat.resolve_attack(c, hi, gd, RNG(9))["damage"]    # 非開場(sneak_attack 預設 False)
    hi.active_effects.append({"kind": "deathmark", "turns": 4})
    mark = combat.resolve_attack(c, hi, gd, RNG(9))["damage"]
    assert mark > nomark                                          # follow-up 破甲增傷


# --- 存檔:里程碑選擇往返已由 test_mastery.test_mastery_choices_roundtrip_and_backward_compat 覆蓋(含向後相容)----


# --- 對抗審查回歸防線 ------------------------------------------------
def test_shield_wall_ally_aura_actually_mitigates():
    # 修:_armor_rating 非玩家分支原不吃 active_shield → 護同袍光環曾是死功能
    ally = combat.spawn_creature(gd, "wolf", RNG(1)); ally.health = ally.max_health = 9999; ally.armor_rating = 5
    foe = _strong()
    base = combat.resolve_attack(foe, ally, gd, RNG(8))["damage"]
    ally.active_effects.append({"kind": "shield", "magnitude": 8, "turns": 1, "source": "shield_wall_aura"})
    warded = combat.resolve_attack(foe, ally, gd, RNG(8))["damage"]
    assert warded < base                          # 同伴護甲光環真生效


def test_shield_wall_not_offered_when_fatigue_exhausted():
    # 修:fatigue-0 免費永久重立盾牆 → 改為體力 ≤ upkeep 不可再立(有限防禦資源)
    from tesrpg import main
    from tesrpg.state import GameState, GameTime
    cap = {}
    saved = main.ui.menu
    main.ui.menu = lambda title, opts, allow_back=False: (cap.__setitem__("o", [k for k, *_ in opts]) or "flee")
    try:
        c = _char("warrior", block=60); c.weapon = "steel_sword"; c.equipped["shield"] = "iron_shield"
        st = GameState(player=c, time=GameTime(), rng=RNG(1))
        foe = combat.spawn_creature(gd, "wolf", RNG(1))
        c.fatigue = main.SHIELD_WALL_UPKEEP        # 恰好 = 上繳量 → 不足以維持
        main._choose_combat_action(st, gd, [foe], [])
        assert "wall" not in cap["o"]
        c.fatigue = 50
        main._choose_combat_action(st, gd, [foe], [])
        assert "wall" in cap["o"]
    finally:
        main.ui.menu = saved


def test_triage_flag_preserved_when_cast_fails():
    # 修:旗標原在失敗退費前就消耗 → 治療失敗白費 buff
    c = _char("healer", restoration=80)
    mastery.choose(c, gd, "restoration_50", "triage")
    c.magicka = c.max_magicka = 99999
    ally_spell = next((s for s, v in gd.spells.items() if v.get("target") in ("ally", "allies")), None)
    c.active_effects.append({"kind": "triage_ready", "turns": 2})
    res = magic.cast(c, gd, ally_spell, RNG(1), target=None, battle=None)   # 無戰鬥 → 失敗退費
    assert not res["ok"]
    assert any(e["kind"] == "triage_ready" for e in c.active_effects)       # 旗標保留


def test_deathmark_cooldown_outlasts_mark():
    # 修:cooldown(原 3)< 標記期(4)→ 冷卻形同虛設;改為 cooldown > turns 才有獨立落印鎖
    node = next(n for n in mastery._nodes(gd) if n["id"] == "sneak_50")
    dm = next(o for o in node["options"] if o["opt_id"] == "deathmark")
    assert dm["cooldown"] > dm["turns"]


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_class_identity OK")
