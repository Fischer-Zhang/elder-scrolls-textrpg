"""R215 變化系里程碑重設計(使用者 2026-11-25 拍板):
  · alteration_75:瞬發護體(新,取代術法增幅)對 石膚(被動護甲 +20 → +30)
  · alteration_100:元素護膚(新,取代術法精純)對 石膚反擊(不動)

規則:
  瞬發護體 —— 每場戰鬥第一道**自我護盾**(橡木膚 / 石膚 / 鐵膚;庇護術〔同伴〕不算)瞬發:不耗回合、施放後仍可行動;一場一次、不回補;
  元素護膚 —— 作用中護盾值 × 0.3 當作對火 / 霜 / 電的「元素護甲」(同一條護甲曲線),只算護盾本身,乘在元素抗性 × 魔抗之後(第三層)。

🔴 守衛:① 資料(opt_id / kind / 數值;舊 spell_reach / pure_form 退場)② getter(未選 / 非玩家回中性)
③ 公式 `formulas.shield_elemental_multiplier`(R138b:元素減傷恆 < 同盾物理減傷;無盾 / 未選 = 1.0)
④ `magic.shield_elemental_factor` 範圍(只玩家 · 只火霜電 · 需護盾 · 任何來源的護盾同一對待)
⑤ 戰鬥接線(同一擊同種子對照:元素擊少受正確比例;物理 / 毒擊不受影響;未選逐位元組同)
⑥ 瞬發閘門 `combat.quick_ward_ready`(只自我護盾 · 用過即關 · 未選 / 非玩家 False · 一場一次)
⑦ `run_battle` 接線(免費施法不結束回合、第二道護盾耗回合、失敗不耗、每場重置、非資格法術不動)
⑧ 預覽 = 實擲(選單標題 / 標籤 / 角色卡標籤)⑨ 舊存檔:舊 opt_id 被清成 pending、可重選。
"""
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import formulas
from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, mastery, progression, stats

gd = get_gamedata()
SELF_SHIELDS = ("oakflesh", "stoneflesh", "ironflesh")


def _mage(n75="quick_ward", n100="elemental_ward", alteration=100):
    c = build_character(gd, name="護", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills.update(alteration=alteration, destruction=60, restoration=60)
    c.attributes.update(intelligence=100, willpower=100)
    c.spells = ["oakflesh", "stoneflesh", "ironflesh", "ward_ally", "flame_blade", "heal", "fireball"]
    if n75:
        c.mastery_choices["alteration_75"] = n75
    if n100:
        c.mastery_choices["alteration_100"] = n100
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = c.max_magicka = 5000
    c.fatigue = c.max_fatigue
    c.health = c.max_health = 5000
    return c


def _shield(c, mag=112, source="spell_shield"):
    c.active_effects.append({"kind": "shield", "magnitude": mag, "turns": 5, "source": source})


# --- ① 資料 -------------------------------------------------------------------------------
def test_node_data_pairs_and_old_options_are_gone():
    n75 = next(n for n in gd.mastery if n["id"] == "alteration_75")
    o75 = {o["opt_id"]: o for o in n75["options"]}
    assert set(o75) == {"stoneflesh", "quick_ward"}, "術法增幅(spell_reach)已退場"
    assert o75["stoneflesh"]["kind"] == "passive_armor" and o75["stoneflesh"]["armor_bonus"] == 30   # +20 → +30(與瞬發對位)
    assert o75["quick_ward"]["name"] == "瞬發護體" and o75["quick_ward"]["kind"] == "quick_ward"
    n100 = next(n for n in gd.mastery if n["id"] == "alteration_100")
    o100 = {o["opt_id"]: o for o in n100["options"]}
    assert set(o100) == {"elemental_ward", "warding_recoil"}, "術法精純(pure_form)已退場"
    assert o100["elemental_ward"]["name"] == "元素護膚" and o100["elemental_ward"]["kind"] == "shield_elemental"
    assert abs(o100["elemental_ward"]["factor"] - 0.3) < 1e-9
    assert o100["warding_recoil"]["kind"] == "shield_recoil" and abs(o100["warding_recoil"]["chance"] - 0.3) < 1e-9   # 不動
    # 通則:100 階逐選項都要有改變行為的機制(純數值 spell_mod 不算)
    assert all(o["kind"] != "spell_mod" for o in n100["options"])
    # 兩個新 kind 已登錄(未登錄 → 完全不顯示 / 不可選 / 無效果)
    assert {"quick_ward", "shield_elemental"} <= mastery._IMPLEMENTED_KINDS


# --- ② getter -----------------------------------------------------------------------------
def test_getters_only_when_selected_and_player_only():
    c = _mage()
    assert mastery.quick_ward(c, gd) is True and abs(mastery.shield_elemental(c, gd) - 0.3) < 1e-9
    none = _mage(None, None)
    assert mastery.quick_ward(none, gd) is False and mastery.shield_elemental(none, gd) == 0.0
    other = _mage("stoneflesh", "warding_recoil")                     # 選了對側 → 兩者皆無
    assert mastery.quick_ward(other, gd) is False and mastery.shield_elemental(other, gd) == 0.0
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    assert mastery.quick_ward(foe, gd) is False and mastery.shield_elemental(foe, gd) == 0.0
    low = _mage(alteration=60)                                         # 未達門檻 → 選擇不生效
    assert mastery.quick_ward(low, gd) is False and mastery.shield_elemental(low, gd) == 0.0


# --- ③ 公式 -------------------------------------------------------------------------------
def test_formula_values_neutral_cases_and_r138b_guard():
    f = formulas.shield_elemental_multiplier
    assert f(0, 0.3) == 1.0 and f(-5, 0.3) == 1.0 and f(112, 0.0) == 1.0 and f(112, -1) == 1.0   # 無盾 / 未選 = 中性(零浮點差)
    assert abs((1 - f(112, 0.3)) - 0.2515) < 5e-4          # 石膚(後期威力)= 33.6/133.6 ≈ 25.2%
    assert abs((1 - f(153, 0.3)) - 0.3146) < 5e-4          # 鐵膚 = 45.9/145.9 ≈ 31.5%
    assert abs((1 - f(153, 0.3)) - 0.3 * 153 / (0.3 * 153 + 100)) < 1e-12   # 與設計式 k·s/(k·s+100) 逐位對上
    prev = 1.0
    for s in range(1, 501):
        m = f(s, 0.3)
        assert m < prev + 1e-15, "護盾越厚減傷越多(單調)"
        assert 1 - m < s / (s + 100.0), f"R138b:同一道盾的元素減傷必須小於其物理減傷 s={s}"
        prev = m


# --- ④ 範圍 -------------------------------------------------------------------------------
def test_factor_scope_player_only_fire_frost_shock_only_needs_a_shield_any_source():
    c = _mage()
    for el in ("fire", "frost", "shock", "poison", "disease", "magic", "physical", None):
        assert magic.shield_elemental_factor(c, gd, el) == 1.0, f"無盾:{el}"
    _shield(c)
    want = formulas.shield_elemental_multiplier(112, 0.3)
    for el in ("fire", "frost", "shock"):
        assert magic.shield_elemental_factor(c, gd, el) == want, el
    for el in ("poison", "disease", "magic", "physical", None):
        assert magic.shield_elemental_factor(c, gd, el) == 1.0, f"範圍外:{el}"
    c2 = _mage()
    _shield(c2, 112, source="overheal_ward")                           # R190:任何來源的護盾同一對待(與護甲端同源)
    assert magic.shield_elemental_factor(c2, gd, "fire") == want
    c3 = _mage(None, None)
    _shield(c3)
    assert magic.shield_elemental_factor(c3, gd, "fire") == 1.0, "未選 → 恆 1.0"
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.active_effects.append({"kind": "shield", "magnitude": 500, "turns": 5})
    assert magic.shield_elemental_factor(foe, gd, "fire") == 1.0, "怪物不讀"


# --- ⑤ 戰鬥接線 ---------------------------------------------------------------------------
def _strike(player, element, seed_from=0):
    """同一個怪、同一組種子打玩家一擊,回傳第一個命中的 (傷害, 種子);呼叫端用同種子對照不同玩家 → rng 消耗一致。"""
    atk = {"name": "測試擊", "damage": 400, "skill": 100}
    if element:
        atk["element"] = element
    for seed in range(seed_from, seed_from + 200):
        p = player()
        foe = combat.spawn_creature(gd, "bandit", RNG(1))
        ev = combat.resolve_attack(foe, p, gd, RNG(seed), attack=atk)
        if ev["hit"]:
            return ev["damage"], seed
    raise AssertionError("200 個種子都沒命中?")


def test_elemental_strike_is_reduced_by_exactly_the_layer_physical_and_poison_are_not():
    def with_node():
        c = _mage(); _shield(c); return c

    def shield_only():                                                 # 同樣的盾,但沒選元素護膚(對側 石膚反擊)
        c = _mage(None, "warding_recoil"); _shield(c); return c

    def no_shield():
        return _mage()

    layer = formulas.shield_elemental_multiplier(112, 0.3)
    for el in ("fire", "frost", "shock"):
        d_node, seed = _strike(with_node, el)
        d_ctrl = _strike(shield_only, el, seed_from=seed)[0]
        assert abs(d_node - d_ctrl * layer) <= 1, f"{el}:{d_node} vs {d_ctrl}×{layer:.4f}"
        assert d_node < d_ctrl
        assert _strike(no_shield, el, seed_from=seed)[0] == d_ctrl, "沒盾:選了元素護膚也不減(對照 = 沒選的盾)"
    for el in ("poison", None):                                        # 毒 / 物理:元素護膚不碰
        d_node, seed = _strike(with_node, el)
        assert _strike(shield_only, el, seed_from=seed)[0] == d_node, f"{el} 不應被元素層影響"


def test_layer_stacks_multiplicatively_after_resist_not_added_to_it():
    """第三層乘在抗性 × 魔抗之後:加了魔抗後,元素護膚省下的『比例』不變(乘性),不是加性疊進抗性層。"""
    def build(resist):
        def f():
            c = _mage(); _shield(c); c.equip_resist["magic"] = resist; return c
        return f

    def ctrl(resist):
        def f():
            c = _mage(None, "warding_recoil"); _shield(c); c.equip_resist["magic"] = resist; return c
        return f

    layer = formulas.shield_elemental_multiplier(112, 0.3)
    for resist in (0, 30):
        d_node, seed = _strike(build(resist), "fire")
        d_ctrl = _strike(ctrl(resist), "fire", seed_from=seed)[0]
        assert abs(d_node / d_ctrl - layer) < 0.02, (resist, d_node, d_ctrl)


# --- ⑥ 瞬發閘門 ---------------------------------------------------------------------------
def test_gate_only_self_shield_spells_once_per_battle_and_not_for_others():
    c = _mage()
    for sid in SELF_SHIELDS:
        assert combat.is_self_shield_spell(gd, sid) and combat.quick_ward_ready(c, gd, sid), sid
    for sid in ("ward_ally", "flame_blade", "heal", "fireball", "bound_armor", "no_such_spell"):       # 同伴護盾 / 元素刃 / 治療 / 傷害法術 / 召喚系自我護盾(束縛護甲)都不算
        assert not combat.is_self_shield_spell(gd, sid) and not combat.quick_ward_ready(c, gd, sid), sid
    assert combat.quick_ward_status(c, gd) == "available"
    combat.quick_ward_spend(c)
    combat.quick_ward_spend(c)                                          # 重複記帳不疊
    assert sum(e.get("kind") == combat.QUICK_WARD_SPENT for e in c.active_effects) == 1
    assert combat.quick_ward_status(c, gd) == "spent" and not any(combat.quick_ward_ready(c, gd, s) for s in SELF_SHIELDS)
    for other in (_mage(None, None), _mage("stoneflesh", "warding_recoil")):
        assert not combat.quick_ward_ready(other, gd, "stoneflesh") and combat.quick_ward_status(other, gd) is None
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    assert not combat.quick_ward_ready(foe, gd, "stoneflesh") and combat.quick_ward_status(foe, gd) is None
    assert combat.QUICK_WARD_SPENT in combat.BATTLE_LOCAL_KINDS and combat.QUICK_SEAL_SPENT in combat.BATTLE_LOCAL_KINDS


def test_instant_ward_is_alteration_only_a_conjuration_self_shield_does_not_qualify():
    """審查補洞(R216):文件宣稱瞬發護體「僅變化系」,但負向清單原本沒有召喚系的自我護盾(束縛護甲 bound_armor)——
    拿掉 is_self_shield_spell 的學派檢查,舊測試仍全綠(突變存活)。現釘死:束縛護甲不是瞬發護體的資格,也不動免費額度。"""
    sp = gd.spells["bound_armor"]
    assert sp["school"] == "conjuration" and sp["target"] == "self" and (sp.get("effect") or {}).get("kind") == "shield", \
        "前提:束縛護甲確實是自我護盾(否則這條守衛沒意義)"
    c = _mage()
    c.spells.append("bound_armor")
    assert not combat.is_self_shield_spell(gd, "bound_armor")
    assert not combat.quick_ward_ready(c, gd, "bound_armor")
    assert combat.quick_ward_status(c, gd) == "available", "施放束縛護甲前後都不動免費額度"


def test_seal_and_ward_bookkeeping_are_independent():
    c = _mage()
    c.mastery_choices["conjuration_75"] = "conj_efficiency"
    c.skills["conjuration"] = 100
    combat.quick_seal_spend(c)
    assert combat.quick_ward_status(c, gd) == "available", "用掉契印不動護體記帳"
    combat.quick_ward_spend(c)
    assert combat.quick_seal_status(c, gd) == "spent" and combat.quick_ward_status(c, gd) == "spent"


# --- ⑦ run_battle 接線 --------------------------------------------------------------------
def _foe(hp=10 ** 6):
    f = combat.spawn_creature(gd, "bandit", RNG(1))
    f.health = f.max_health = hp
    f.resist = {}
    f.active_effects.append({"kind": "paralyze", "turns": 10 ** 6})   # 打不死也不出手 → 走向完全由腳本決定
    return f


def _drive(c, script, foe=None, **kw):
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    foe = foe if foe is not None else _foe()
    ticks = [0]
    snaps = []
    queue = list(script)
    orig_choose, orig_tick = M._choose_combat_action, combat.tick_summons

    def counting_tick(allies):
        ticks[0] += 1
        return orig_tick(allies)

    def chooser(state, gamedata, enemies, allies, *a, **k):
        snap = {"ticks": ticks[0], "status": combat.quick_ward_status(c, gd), "mana": c.magicka,
                "shield": magic.active_shield(c)}
        snaps.append(snap)
        step = queue.pop(0) if queue else {"type": "leave"}
        return step(snap) if callable(step) else step

    M._choose_combat_action, combat.tick_summons = chooser, counting_tick
    try:
        res = M.run_battle(st, gd, [foe], **kw)
    finally:
        M._choose_combat_action, combat.tick_summons = orig_choose, orig_tick
    return snaps, res


def test_first_self_shield_is_free_second_costs_the_turn():
    c = _mage()
    snaps, _ = _drive(c, [{"type": "cast", "spell_id": "stoneflesh"},          # 免費:不結束回合
                          {"type": "cast", "spell_id": "ironflesh"},           # 第二道:一般施法,耗回合
                          {"type": "leave"}])
    assert [s["ticks"] for s in snaps] == [0, 0, 1], snaps
    assert [s["status"] for s in snaps] == ["available", "spent", "spent"]
    assert snaps[0]["shield"] == 0 and snaps[1]["shield"] > 0, "免費那道真的上了盾"
    assert snaps[2]["shield"] > snaps[1]["shield"] * 0.9, "鐵膚取代石膚(單槽 R211,不疊加)"
    assert snaps[1]["mana"] < snaps[0]["mana"], "瞬發不免魔力"


def test_unselected_pays_the_turn_for_every_shield_as_before():
    for n75 in (None, "stoneflesh"):
        c = _mage(n75, None)
        snaps, _ = _drive(c, [{"type": "cast", "spell_id": "stoneflesh"}, {"type": "leave"}])
        assert [s["ticks"] for s in snaps] == [0, 1], n75
        assert [s["status"] for s in snaps] == [None, None]
        assert snaps[1]["shield"] > 0


def test_non_eligible_casts_never_touch_the_free_cast():
    c = _mage()
    foe = _foe()
    snaps, _ = _drive(c, [{"type": "cast", "spell_id": "heal"},
                          {"type": "cast", "spell_id": "flame_blade"},
                          {"type": "cast", "spell_id": "fireball", "target": foe},
                          {"type": "leave"}], foe=foe)
    assert [s["status"] for s in snaps] == ["available"] * 4 and [s["ticks"] for s in snaps] == [0, 1, 2, 3]


def test_failed_cast_burns_neither_the_free_cast_nor_the_turn_and_a_later_success_is_free():
    c = _mage()

    def broke_then_rich(snap):
        c.magicka = 0                                                           # 付不起 → 施法失敗
        return {"type": "cast", "spell_id": "ironflesh"}

    def restore_then_cast(snap):
        c.magicka = 5000
        return {"type": "cast", "spell_id": "stoneflesh"}

    snaps, _ = _drive(c, [broke_then_rich, restore_then_cast, {"type": "leave"}])
    assert [s["status"] for s in snaps] == ["available", "available", "spent"], "失敗不耗"
    assert [s["ticks"] for s in snaps] == [0, 0, 0], "失敗與其後的成功免費施法都沒結束回合"
    assert snaps[2]["shield"] > 0


def test_retry_cap_safety_valve_after_repeated_failures():
    from tesrpg.main import QUICK_SEAL_RETRY_CAP
    c = _mage()
    c.magicka = 0
    script = [{"type": "cast", "spell_id": "stoneflesh"}] * (QUICK_SEAL_RETRY_CAP + 1) + [{"type": "leave"}]
    snaps, _ = _drive(c, script)
    assert [s["ticks"] for s in snaps] == [0] * (QUICK_SEAL_RETRY_CAP + 1) + [1], "連續失敗達上限後照一般施法結算(防空轉)"


def test_every_battle_starts_with_a_fresh_free_cast_including_dungeon_fights_that_preserve_buffs():
    c = _mage()
    _drive(c, [{"type": "cast", "spell_id": "stoneflesh"}, {"type": "leave"}])
    snaps, _ = _drive(c, [{"type": "leave"}])
    assert snaps[0]["status"] == "available"
    c2 = _mage()
    c2.active_effects.append({"kind": combat.QUICK_WARD_SPENT, "turns": combat.PERSISTENT_TURNS})   # 上一場地城戰鬥殘留
    snaps2, _ = _drive(c2, [{"type": "leave"}], preserve_buffs=True)
    assert snaps2[0]["status"] == "available", "preserve_buffs 入戰剝除本場記帳 → 地城每場都是新的一次"


# --- ⑧ 預覽 = 實擲 ------------------------------------------------------------------------
def _spell_menu(c):
    seen = {}
    orig = ui.menu

    def fake(title, options, allow_back=False):
        if "施放哪道法術" in title:
            seen["title"], seen["options"] = title, list(options)
            return options[0][0]
        return "cast"

    ui.menu = fake
    try:
        st = GameState(player=c, rng=RNG(3), time=GameTime())
        M._choose_combat_action(st, gd, [_foe()], [])
    finally:
        ui.menu = orig
    return seen


def test_cast_menu_title_labels_and_card_tag_preview_exactly_what_the_cast_will_do():
    c = _mage()
    seen = _spell_menu(c)
    assert "瞬發護體:可用" in seen["title"] and "瞬發契印" not in seen["title"]
    labels = dict(seen["options"])
    for sid in labels:                                                          # 標籤與實際閘門一一對應
        assert ("瞬發(不耗回合)" in labels[sid]) == combat.quick_ward_ready(c, gd, sid), sid
    assert any("瞬發(不耗回合)" in labels[s] for s in SELF_SHIELDS if s in labels)
    assert "瞬發" not in labels["ward_ally"] and "瞬發" not in labels["heal"]
    tag = next(t for t in ui._player_state_tags(c, gd) if t["s"].startswith("瞬發護體"))
    assert tag["s"] == "瞬發護體 可用" and tag["good"] is True and "護盾" in tag["tip"]
    combat.quick_ward_spend(c)
    seen2 = _spell_menu(c)
    assert "瞬發護體:已用" in seen2["title"] and not any("瞬發(不耗回合)" in v for _k, v in seen2["options"])
    tag2 = next(t for t in ui._player_state_tags(c, gd) if t["s"].startswith("瞬發護體"))
    assert tag2["s"] == "瞬發護體 已用" and tag2["good"] is None
    assert ui._status_tags_list(c) == [] and ui._status_tags(c) == "", "本場已用記帳是隱藏標籤"
    seen3 = _spell_menu(_mage(None, None))
    assert seen3["title"] == "施放哪道法術?" and not any("瞬發" in v for _k, v in seen3["options"]), "未選者選單逐字不變"
    assert not any(t["s"].startswith("瞬發護體") for t in ui._player_state_tags(_mage(None, None), gd))


# --- ⑨ 舊存檔 -----------------------------------------------------------------------------
def test_old_saves_with_retired_option_ids_are_cleared_to_pending_and_can_repick():
    c = _mage(None, None)
    c.mastery_choices.update({"alteration_75": "spell_reach", "alteration_100": "pure_form", "alteration_50": "shield_focus"})
    progression.ensure_mastery_choices(c, gd)
    assert "alteration_75" not in c.mastery_choices and "alteration_100" not in c.mastery_choices, "舊 opt_id 清成 pending"
    assert c.mastery_choices.get("alteration_50") == "shield_focus", "其他節點的選擇不動"
    pending = {n["id"] for n in mastery.pending_choices(c, gd)}
    assert {"alteration_75", "alteration_100"} <= pending
    assert mastery.choose(c, gd, "alteration_75", "quick_ward") and mastery.choose(c, gd, "alteration_100", "elemental_ward")
    assert mastery.quick_ward(c, gd) and abs(mastery.shield_elemental(c, gd) - 0.3) < 1e-9
    assert mastery.spell_power_bonus(c, gd, "alteration") == 0.10, "威力加成只剩 50 的 +10%(75 / 100 的 +15% 已退場)"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r215_alteration_nodes")
