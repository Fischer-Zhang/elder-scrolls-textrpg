"""R204 束縛兵刃一致性修正(使用者 2026-11-22 拍板;Fable 構築規劃 + 兩項重現後):
  ① 巨劍 / 斧為雙手形,不能配盾;雙手重盾占雙手 → 任何束縛兵刃都凝不出(原:束縛優先於重盾,重盾 + 束縛巨劍 + 姿態打穿達貢牆 30~32%,同底盤他形 0%)
  ② 揮擊耗體以束縛兵刃自身速度計(原:讀休眠中的裝備武器,同一把束縛巨劍休眠匕首 3.5 / 休眠魔族戰斧 8.2)
  ③ 完美格擋 / 閃身反打的反擊與一般揮擊同屬元素(原:一律當物理去吃物抗)
  ④ 野外備戰可預凝束縛兵刃(原:地城預施可以、備戰不行)
  ⑤ 偷襲倍率維持「會吃」(使用者拍板)—— 守衛:束縛兵刃開場偷襲對所有 solo 首領仍不會一擊秒殺(SOLO_SNEAK 夾限)。
🔴 守衛:預覽 = 實擲(`magic.bound_conflict` 是 cast 與選單共用的單一出處)、衝突施放不耗任何資源、未持盾的束縛路徑逐位元組同舊。
"""
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import formulas, main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, magic, mastery, stats

gd = get_gamedata()
BOUND = ("bound_sword", "bound_mace", "bound_axe", "bound_greatsword")


def _char(shield=None, weapon=None, **skills):
    c = build_character(gd, name="騎", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(conjuration=100, athletics=50)
    c.skills.update(skills)
    c.attributes.update(strength=100, intelligence=60, willpower=70)
    c.spells = list(BOUND) + ["bound_armor", "flames"]
    if weapon:
        inventory.add_item(c, weapon, 1)
        inventory.equip_weapon(c, gd, weapon)
    if shield:
        inventory.add_item(c, shield, 1)
        assert inventory.equip_armor(c, gd, shield)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = c.max_magicka = 5000
    c.fatigue = c.max_fatigue
    return c


def _bound(c):
    return next((e for e in c.active_effects if e.get("kind") == "bound_weapon" and e.get("turns", 0) > 0), None)


# --- 資料 -------------------------------------------------------------------------------------
def test_spell_data_two_handed_forms_and_own_speed():
    eff = {s: gd.spells[s]["effect"] for s in BOUND}
    assert eff["bound_greatsword"]["two_handed"] is True and eff["bound_axe"]["two_handed"] is True
    assert not eff["bound_sword"].get("two_handed") and not eff["bound_mace"].get("two_handed"), "劍 / 釘錘仍是單手"
    assert eff["bound_greatsword"]["speed"] < formulas.WEAPON_SPEED_DEFAULT and eff["bound_axe"]["speed"] < formulas.WEAPON_SPEED_DEFAULT
    assert "speed" not in eff["bound_sword"] and "speed" not in eff["bound_mace"], "單手形用預設速度(不憑空新增平衡數字)"
    assert "雙手" in ui.spell_effect_summary(gd, "bound_greatsword") and "雙手" not in ui.spell_effect_summary(gd, "bound_sword")
    assert gd.spells["bound_armor"]["effect"]["kind"] == "shield", "束縛甲冑不是武器,不受握法限制"


# --- ① 握法衝突(單一出處)+ 施放 ---------------------------------------------------------------
def test_bound_conflict_matrix_two_handed_vs_any_shield_and_any_bound_vs_great_shield():
    none, plain, great = _char(), _char("daedric_shield"), _char("daedric_great_shield")
    for s in BOUND:
        assert magic.bound_conflict(none, gd, s) is None, s
    assert magic.bound_conflict(plain, gd, "bound_sword") is None and magic.bound_conflict(plain, gd, "bound_mace") is None
    assert magic.bound_conflict(plain, gd, "bound_greatsword") and magic.bound_conflict(plain, gd, "bound_axe")
    for s in BOUND:
        assert "重盾" in (magic.bound_conflict(great, gd, s) or ""), s                   # 重盾下任何束縛兵刃都凝不出
    assert magic.bound_conflict(plain, gd, "bound_armor") is None and magic.bound_conflict(great, gd, "flames") is None
    assert magic.bound_conflict(plain, gd, "no_such_spell") is None


def test_conflicting_cast_is_refused_and_costs_nothing_while_legal_casts_work_as_before():
    for shield, spell, ok in (("daedric_shield", "bound_greatsword", False), ("daedric_shield", "bound_axe", False),
                              ("daedric_shield", "bound_sword", True), ("daedric_shield", "bound_mace", True),
                              ("daedric_great_shield", "bound_sword", False), ("daedric_great_shield", "bound_greatsword", False),
                              (None, "bound_greatsword", True), (None, "bound_axe", True)):
        c = _char(shield)
        m0, f0 = c.magicka, c.fatigue
        res = magic.cast(c, gd, spell, RNG(1), battle={"allies": []})
        assert res["ok"] is ok, (shield, spell, res["message"])
        if ok:
            assert _bound(c) is not None and m0 - c.magicka >= 1
        else:
            assert _bound(c) is None and (c.magicka, c.fatigue) == (m0, f0) and res["skill_events"] == [], "衝突:退魔退體、不練技能、不凝刃"
    c = _char()
    magic.cast(c, gd, "bound_greatsword", RNG(1), battle={"allies": []})
    e = _bound(c)
    assert e["two_handed"] is True and e["speed"] == 0.8 and e["archetype"] == "sword"


def test_equipping_a_shield_is_blocked_while_a_conflicting_bound_weapon_lingers_outside_battle():
    for spell, shield, blocked in (("bound_greatsword", "daedric_shield", True), ("bound_axe", "daedric_shield", True),
                                   ("bound_sword", "daedric_shield", False), ("bound_sword", "daedric_great_shield", True),
                                   ("bound_greatsword", "daedric_great_shield", True)):
        c = _char()
        inventory.add_item(c, shield, 1)
        magic.cast(c, gd, spell, RNG(1), battle={"allies": []})                         # 地城預施的殘留效果
        why = inventory.armor_equip_block(c, gd, shield)
        assert bool(why) is blocked, (spell, shield, why)
        assert inventory.equip_armor(c, gd, shield) is (not blocked)
    c = _char()
    inventory.add_item(c, "daedric_great_shield", 1)
    assert inventory.armor_equip_block(c, gd, "daedric_great_shield") is None, "沒有束縛兵刃 → 裝盾規則不變"


# --- ② 耗體 ------------------------------------------------------------------------------------
def test_swing_fatigue_uses_the_bound_weapons_own_speed_not_the_dormant_equipped_weapon():
    def cost(weapon, spell=None):
        c = _char(weapon=weapon)
        if spell:
            assert magic.cast(c, gd, spell, RNG(1), battle={"allies": []})["ok"]
        return combat.attack_fatigue_cost(c, gd)
    dagger, axe2h = "iron_dagger", "iron_warhammer"
    assert cost(dagger) != cost(axe2h), "前提:沒有束縛時,耗體隨裝備武器速度而異"
    for spell, speed in (("bound_greatsword", 0.8), ("bound_axe", 0.85), ("bound_sword", formulas.WEAPON_SPEED_DEFAULT),
                         ("bound_mace", formulas.WEAPON_SPEED_DEFAULT)):
        a, b = cost(dagger, spell), cost(axe2h, spell)
        c = _char()
        want = (formulas.ATTACK_FATIGUE_COST * formulas.fatigue_cost_factor(c.skill("athletics"))
                * formulas.weapon_attack_fatigue_factor(speed))
        assert abs(a - want) < 1e-9 and abs(b - want) < 1e-9, (spell, a, b, want)   # 與休眠武器無關,只由束縛自身速度決定
    assert cost(dagger, "bound_greatsword") > cost(dagger, "bound_sword"), "巨劍(雙手慢重)比長劍更耗體"
    # 休眠武器的里程碑耗體(如「穿甲箭」draw_fatigue,經 weapon_mod(該武器技能))不該算到束縛揮擊上
    plain_c, bound_c = _char(weapon=dagger), _char(weapon=dagger)
    magic.cast(bound_c, gd, "bound_sword", RNG(1), battle={"allies": []})
    plain_off = combat.attack_fatigue_cost(plain_c, gd)
    want = (formulas.ATTACK_FATIGUE_COST * formulas.fatigue_cost_factor(bound_c.skill("athletics"))
            * formulas.weapon_attack_fatigue_factor(formulas.WEAPON_SPEED_DEFAULT))
    orig = mastery.weapon_mod
    mastery.weapon_mod = lambda c, g, sk: {"fatigue": 5.0} if sk else {}
    try:
        assert abs(combat.attack_fatigue_cost(plain_c, gd) - (plain_off + 5.0)) < 1e-9, "對照:沒有束縛時該里程碑耗體照算"
        assert abs(combat.attack_fatigue_cost(bound_c, gd) - want) < 1e-9, "束縛揮擊不吃休眠武器的里程碑耗體"
    finally:
        mastery.weapon_mod = orig


# --- ③ 反擊抗性分類 ----------------------------------------------------------------------------
def test_counter_resist_kind_follows_the_swing_type_and_perfect_block_counters_use_it():
    plain, bound = _char(), _char()
    magic.cast(bound, gd, "bound_sword", RNG(1), battle={"allies": []})
    assert combat._counter_resist_kind(plain) == "physical" and combat._counter_resist_kind(bound) == "magic"
    seen = {}
    orig_rm, orig_rip = formulas.resist_multiplier, mastery.block_riposte
    for label, who in (("plain", plain), ("bound", bound)):
        foe = combat.spawn_creature(gd, "bandit", RNG(1))
        foe.attack["skill"] = 100
        foe.attack["damage"] = 4
        foe.resist = {"physical": 40, "magic": 10}
        kinds = []
        formulas.resist_multiplier = lambda resist, element, _f=foe, _k=kinds: (_k.append(element) if resist is _f.resist or resist == _f.resist else None) or orig_rm(resist, element)
        mastery.block_riposte = lambda d, g: {"stagger_chance": 1.0, "counter": 0.5}   # 反擊掛在盾擊踉蹌觸發之內(combat 的巢狀結構)
        try:
            for s in range(40):
                who.health = who.max_health
                combat.resolve_attack(foe, who, gd, RNG(s), defender_blocking=True)
        finally:
            formulas.resist_multiplier, mastery.block_riposte = orig_rm, orig_rip
        seen[label] = set(kinds)
    assert "physical" in seen["plain"] and "magic" not in seen["plain"], seen
    assert "magic" in seen["bound"] and "physical" not in seen["bound"], seen


# --- ④ 備戰 / 選單 -----------------------------------------------------------------------------
def test_prep_phase_offers_bound_weapons_and_menus_hide_or_flag_gripping_conflicts():
    c = _char()
    prep = M._prep_buff_spells(c, gd, set())
    assert all(s in prep for s in BOUND) and "bound_armor" in prep, prep               # 野外備戰可預凝束縛兵刃
    assert "bound_sword" not in M._prep_buff_spells(c, gd, {"bound_sword"}), "同一法術每場備戰不可重施"
    plain, great = _char("daedric_shield"), _char("daedric_great_shield")
    assert [s for s in BOUND if s in M._prep_buff_spells(plain, gd, set())] == ["bound_sword", "bound_mace"]
    assert not [s for s in BOUND if s in M._prep_buff_spells(great, gd, set())]
    assert "bound_greatsword" not in M._combat_castable(plain, gd) and "bound_sword" in M._combat_castable(plain, gd)
    assert not [s for s in BOUND if s in M._combat_castable(great, gd)]
    assert "bound_greatsword" in M._combat_castable(c, gd) and "flames" in M._combat_castable(plain, gd), "非束縛法術不受影響"
    assert "需先卸下盾牌" in M._bound_grip_suffix(plain, gd, "bound_greatsword")
    assert M._bound_grip_suffix(plain, gd, "bound_sword") == "" and M._bound_grip_suffix(c, gd, "bound_greatsword") == ""
    for s in BOUND:                                                                    # 標籤與實際施放一一對應(預覽 = 實擲)
        for ch in (c, plain, great):
            c2 = _char("daedric_great_shield" if ch is great else ("daedric_shield" if ch is plain else None))
            assert bool(M._bound_grip_suffix(c2, gd, s)) is (not magic.cast(c2, gd, s, RNG(1), battle={"allies": []})["ok"]), s


# --- ⑤ 偷襲倍率維持「會吃」,solo 夾限仍擋住一擊秒殺 ---------------------------------------------
def test_bound_weapon_still_eats_the_sneak_multiplier_but_never_one_shots_a_solo_boss():
    c = _char(sneak=100)
    c.attributes["luck"] = 100
    assert magic.cast(c, gd, "bound_greatsword", RNG(1), battle={"allies": []})["ok"]

    def hit_dmg(sneak, seed):
        foe = combat.spawn_creature(gd, "bandit", RNG(5))
        foe.health = foe.max_health = 10 ** 6
        foe.resist = {}
        ev = combat.resolve_attack(c, foe, gd, RNG(seed), sneak_attack=sneak)
        return (foe.max_health - foe.health) if ev.get("hit") else 0
    plain = sum(hit_dmg(False, s) for s in range(40))
    sneaky = sum(hit_dmg(True, s) for s in range(40))
    assert sneaky > plain * 1.5, (plain, sneaky)                                         # 使用者拍板:維持「吃」
    solos = [tid for tid, d in gd.bestiary.items() if d.get("solo")]
    assert len(solos) >= 40
    worst = 0.0
    for tid in solos:
        for s in range(25):
            foe = combat.spawn_creature(gd, tid, RNG(s + 1))
            foe.resist = {}                                                              # 最壞:無任何抗性
            hp0 = foe.health
            combat.resolve_attack(c, foe, gd, RNG(s), sneak_attack=True)
            assert combat.is_alive(foe), f"{tid} 被束縛兵刃開場偷襲一擊秒殺(SOLO_SNEAK 夾限失守)"
            worst = max(worst, (hp0 - foe.health) / hp0)
    assert worst <= formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO + 0.01, worst                          # 夾限 40% 最大血;整數血量四捨五入最多多出 ~0.5%


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r204_bound")
