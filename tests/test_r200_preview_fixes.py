"""R200「預覽 = 實擲」第三批:預覽修正包 + 內嵌常數收斂。**零機率 / 零戰鬥行為改動**(只動顯示與重構)。

R199 審計清單的 5 項「預覽 ≠ 實擲」與 5 組「同值但各自內嵌」:
  ① 重盾姿態預覽漏 R107 斯丹達爾之佑 +0.10 與總夾 0.60 → 共用 `combat.guard_stance_mitigation`(實擲 `_guard_stance_factor` = 1 − 它)
  ② 角色卡「護甲值」只顯示 穿戴值+淬鍊,戰鬥用 穿戴值×(0.5+技能/100)+被動+淬鍊+護盾術+亡者 → 顯示 = `combat._armor_rating`,分解 `armor_parts`
  ③ 角色卡「負重上限」只讀力量×5,漏羽落術與鞍袋 → 顯示 = `inventory.max_weight`,分解 `max_weight_parts`
  ④ 撬鎖確認只認骷髏鑰匙、不認塔之鑰充能 → `dungeon.lock_key_kind` 單一判定(優先序同 pick_lock)
  ⑤ 充能預覽未夾容量、魂石照耗 → `enchanting.recharge_outcome`(預覽與實際結算共用)
  內嵌常數:客棧過夜費 / 箭雨 60% / 95% 命中上限 / ×1.5 經驗 / 黑市買價;非機率百分比一律四捨五入(`int(x*100)` 少顯示 1%)。
🔴 守衛:重構逐位元組同舊式(在測試裡原樣重寫舊式、格點 `==`);預覽數字 == 真實計算;改常數 → 標籤跟著變;AST 守衛擋截斷取整。
"""
import ast
import copy
import re
from pathlib import Path

from tesrpg import formulas, main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.synth import enchant_weapon_status_id
from tesrpg.systems import (combat, crime, divines, dungeon, enchanting, inventory, lycanthropy, magic, mastery,
                            mounts, necromancy, smithing, spellfx, stats)
import tesrpg.ui.console as ui

gd = get_gamedata()
ROOT = Path(__file__).resolve().parent.parent


def _char(**skills):
    c = build_character(gd, name="客", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(skills)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.fatigue = c.max_fatigue
    c.location_id = "bruma"
    return c


def _picks(c, n):
    """把開鎖器數量設成剛好 n(新角色起始裝備自帶一批)。"""
    have = inventory.count_item(c, "lockpick")
    if have > n:
        inventory.remove_item(c, "lockpick", have - n)
    elif n > have:
        inventory.add_item(c, "lockpick", n - have)
    assert inventory.count_item(c, "lockpick") == n
    return c


def _state(c, seed=3):
    return GameState(player=c, time=GameTime(), rng=RNG(seed))


class _ui_patched:
    """暫時換掉 M.ui 的函式(離開時還原;整套測試共用進程,別人殘留的 patch 也一併原樣還原)。"""

    def __init__(self, **fns):
        self.fns, self.saved = fns, {}

    def __enter__(self):
        for k, f in self.fns.items():
            self.saved[k] = getattr(M.ui, k)
            setattr(M.ui, k, f)

    def __exit__(self, *a):
        for k, f in self.saved.items():
            setattr(M.ui, k, f)


class _Captured(Exception):
    def __init__(self, payload):
        super().__init__("captured")
        self.payload = payload


# --- ① 重盾姿態預覽 = 實擲 -------------------------------------------------------
def _old_guard_factor(d, element):
    """R200 前 `_guard_stance_factor` 公式層(前提閘之後)的原樣內嵌式。"""
    m = formulas.GUARD_STANCE_MITIGATION * min(1.0, d.skill("block") / 100.0)
    m += divines.block_bonus(d)
    if element:
        m *= (formulas.GREAT_SHIELD_ELEMENTAL_FACTOR if combat._wields_great_shield(d, gd)
              else formulas.GUARD_STANCE_ELEMENTAL_FACTOR)
    return 1.0 - min(0.60, m)


def _guard_builds(stance=True):
    for shield in ("iron_great_shield", "wooden_shield"):
        for block in (0, 30, 60, 100, 130):                     # 130:技能可因裝備 / 藥水超過 100,min(1.0, …) 夾限必須咬合
            for bless in (None, "stendarr"):
                c = _char(block=block)
                c.equipped["shield"] = shield
                if bless:
                    c.divine_blessing = {"divine": bless, "expires_at": 10 ** 9}
                if stance:
                    c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
                yield shield, block, bless, c


def test_guard_stance_factor_is_bytewise_identical_to_the_pre_r200_inline_formula():
    n = 0
    for shield, block, bless, c in _guard_builds():
        for elem in (None, "fire"):
            assert combat._guard_stance_factor(c, elem, gd) == _old_guard_factor(c, bool(elem)), (shield, block, bless, elem)
            n += 1
    assert n == 40


def test_guard_preview_numbers_equal_the_real_stance_reduction():
    shown, per = set(), {}
    for shield, block, bless, c in _guard_builds():
        phys, elem = ui.guard_stance_numbers(c, gd)
        real_p = 1.0 - combat._guard_stance_factor(c, None, gd)
        real_e = 1.0 - combat._guard_stance_factor(c, "fire", gd)
        assert abs(real_p - combat.guard_stance_mitigation(c, gd, False)) < 1e-12
        assert abs(real_e - combat.guard_stance_mitigation(c, gd, True)) < 1e-12
        assert (phys, elem) == (ui.pct(combat.guard_stance_mitigation(c, gd, False)),
                                ui.pct(combat.guard_stance_mitigation(c, gd, True)))
        assert phys == round(real_p * 100) and elem == round(real_e * 100), (shield, block, bless)
        assert elem <= phys                                                     # R138b 鐵令:元素永遠 ≤ 物理
        per[(shield, block, bless)] = (phys, elem)
        shown.add((phys, elem))
    assert len(shown) >= 8, shown                                              # 非空轉:格擋技能 / 盾種 / 祝福確實反映在數字
    for shield in ("iron_great_shield", "wooden_shield"):
        for block in (30, 60, 100):                                            # 斯丹達爾之佑(+0.10)必須反映在預覽
            assert per[(shield, block, "stendarr")][0] > per[(shield, block, None)][0], (shield, block)
        for bless in (None, "stendarr"):                                       # 格擋技能 > 100 不再增加卸力(min(1.0, 技能/100))
            assert per[(shield, 130, bless)] == per[(shield, 100, bless)], (shield, bless)


def test_guard_stance_factor_gates_stay_in_the_real_function():
    """前提閘留在 `_guard_stance_factor`(沒搬進 guard_stance_mitigation):非玩家 / 沒開姿態 / 力竭 / 獸形 / 搏命還擊 → 1.0。
    (審查:拿掉獸形閘,全套測試都殺不掉。)"""
    def stanced():
        c = _char(block=100)
        c.equipped["shield"] = "iron_great_shield"
        c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
        return c

    assert combat._guard_stance_factor(stanced(), None, gd) < 1.0                # 基準:真的有卸力
    c = stanced()
    c.fatigue = 0
    assert combat._guard_stance_factor(c, None, gd) == 1.0                       # 力竭暫停
    c = stanced()
    c.beast_form = True
    assert combat._guard_stance_factor(c, None, gd) == 1.0                       # 獸形無盾
    c = stanced()
    c.active_effects.append({"kind": "overextended", "turns": 1})
    assert combat._guard_stance_factor(c, None, gd) == 1.0                       # 搏命還擊期間門戶大開
    c = _char(block=100)
    c.equipped["shield"] = "iron_great_shield"
    assert combat._guard_stance_factor(c, None, gd) == 1.0                       # 沒開姿態
    foe = combat.spawn_creature(gd, "wolf", RNG(1))
    assert combat._guard_stance_factor(foe, None, gd) == 1.0                     # 非玩家


def test_guard_preview_applies_the_total_clamp_like_the_real_chain():
    c = _char(block=100)
    c.equipped["shield"] = "iron_great_shield"
    c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
    saved = divines.block_bonus
    divines.block_bonus = lambda ch: 0.50                                      # 0.38 + 0.50 = 0.88 → 夾 0.60
    try:
        assert combat.guard_stance_mitigation(c, gd, False) == 0.60
        assert combat._guard_stance_factor(c, None, gd) == 1.0 - 0.60
        assert ui.guard_stance_numbers(c, gd)[0] == 60
        assert ui.guard_stance_numbers(c, gd)[1] == ui.pct(min(0.60, 0.88 * formulas.GREAT_SHIELD_ELEMENTAL_FACTOR))
    finally:
        divines.block_bonus = saved


def test_guard_option_label_and_weapon_line_show_the_shared_numbers():
    """走真的 _choose_combat_action(攔下送進選單的選項)與 weapon_line:標籤數字 = guard_stance_numbers。"""
    foe = combat.spawn_creature(gd, "wolf", RNG(1))
    for bless in (None, "stendarr"):
        c = _char(block=100)
        c.equipped["shield"] = "iron_great_shield"
        if bless:
            c.divine_blessing = {"divine": bless, "expires_at": 10 ** 9}
        st = _state(c)

        def grab(opts):
            raise _Captured(opts)

        saved = M._grouped_combat_menu
        M._grouped_combat_menu = grab
        try:
            with _ui_patched(combat_status_group=lambda *a, **k: None, message=lambda *a, **k: None):
                try:
                    M._choose_combat_action(st, gd, [foe], [])
                    raise AssertionError("沒有走到動作選單")
                except _Captured as cap:
                    opts = cap.payload
        finally:
            M._grouped_combat_menu = saved
        guard = next(o for o in opts if o[0] == "guard")
        gp, ge = ui.guard_stance_numbers(c, gd)
        bf = formulas.GREAT_SHIELD_BUNKER_FATIGUE
        # R220:會施法者(c.spells 非空)的重盾掩體標籤多一段「架著無法施法」(姿態鎖施法的立架前預警);不會施法者逐字同舊
        lock_chip, lock_note = ("·架著無法施法", " · 架著無法施法") if c.spells else ("", "")
        assert guard[2]["chips"][0]["text"] == f"攻擊變緩·卸力-{gp}%·元素-{ge}%·回氣+{bf}/回{lock_chip}", (bless, guard)   # chip 與 note 分開逐字比對
        assert guard[2]["note"] == f"重盾掩體（攻擊變緩 · 卸力-{gp}% · 元素-{ge}% · 回氣+{bf}/回{lock_note})", (bless, guard)
        line = ui.weapon_line(c, gd)
        assert f"物理-{gp}%" in line and f"元素-{ge}%" in line, (bless, line)
    sd = gd.items["iron_great_shield"]                                           # 盾牌自帶「卸力 N%」也要四捨五入
    had = "mitigation" in sd
    old_m = sd.get("mitigation")
    sd["mitigation"] = 0.29
    try:
        assert "卸力 29%" in ui.weapon_line(c, gd) and "卸力 28%" not in ui.weapon_line(c, gd)
    finally:
        if had:
            sd["mitigation"] = old_m
        else:
            sd.pop("mitigation", None)


def test_guard_mitigation_formula_lives_only_in_combat():
    """原始碼守衛:GUARD_STANCE_MITIGATION 只准在 formulas(定義)與 combat(guard_stance_mitigation)出現 —— UI 不得自己重算。"""
    users = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "tesrpg").rglob("*.py"))
             if "GUARD_STANCE_MITIGATION" in p.read_text(encoding="utf-8")]
    assert users == ["tesrpg/formulas.py", "tesrpg/systems/combat.py"], users


# --- ② 角色卡護甲值 = 戰鬥實際護甲值 -----------------------------------------------
def _old_armor_rating(a):
    """R200 前 `combat._armor_rating` 玩家分支的原樣內嵌式。"""
    if combat._is_beast(a):
        return lycanthropy.BEAST_ARMOR
    worn = inventory.worn_armor_rating(a, gd)
    wc = inventory.dominant_weight_class(a, gd)
    if worn == 0 or wc is None:
        base = formulas.player_armor_rating(a.skill("heavy_armor"), a.skill("light_armor"))
    else:
        base = formulas.worn_armor_base(worn, a.skill("heavy_armor" if wc == "heavy" else "light_armor"))
    passive = mastery.passive_armor_bonus(a, gd)
    return (base + passive + smithing.armor_temper_bonus(a, gd) + magic.active_shield(a)
            + necromancy.undead_armor_bonus(a))


def _armor_builds():
    sets = {"none": {}, "light": {"helmet": "leather_helmet", "cuirass": "leather_cuirass"},
            "heavy": {"helmet": "iron_helmet", "cuirass": "iron_cuirass"}}
    for name, eq in sets.items():
        for hv, lt in ((0, 0), (40, 70), (100, 100)):
            for temper in (0, 3):
                for ward in (0, 7):
                    c = _char(heavy_armor=hv, light_armor=lt)
                    c.equipped = dict(eq)
                    if temper and eq:
                        c.armor_temper = {next(iter(eq.values())): temper}
                    if ward:
                        c.active_effects.append({"kind": "shield", "magnitude": ward, "turns": 3})
                    yield name, c


def test_combat_armor_rating_is_bytewise_identical_to_the_pre_r200_inline_formula():
    n = 0
    for name, c in _armor_builds():
        assert combat._armor_rating(c, gd) == _old_armor_rating(c), name
        p = combat.armor_parts(c, gd)
        assert p["base"] + p["passive"] + p["temper"] + p["shield"] + p["undead"] == combat._armor_rating(c, gd)
        n += 1
    assert n == 36


def test_sheet_armor_equals_the_combat_value_and_the_tip_decomposes_it():
    differs = 0
    for name, c in _armor_builds():
        total = combat._armor_rating(c, gd)
        assert ui._armor_display(c, gd) == total, name
        old_display = inventory.worn_armor_rating(c, gd) + smithing.armor_temper_bonus(c, gd)   # R200 前角色卡顯示的口徑
        differs += (old_display != total)
        v = ui._sheet_view(c, gd)
        assert v["armor"] == total
        assert v["armor_tip"] == _expected_armor_tip(c, total), (name, v["armor_tip"])          # 逐字比對(不只 in)
        assert ui._armor_tip(c, gd, short=True) == _expected_armor_tip(c, total, short=True)
    assert differs >= 20, differs                                              # 非空轉:舊口徑確實與戰鬥值不同(護甲技能 ≠ 50 時)


def _expected_armor_tip(c, total, short=False):
    """測試端獨立組出的分解字串(格式:穿戴 N → 護甲技能折算 M · 被動護甲 +a · 淬鍊 +b · 護盾 +c · 亡者護甲 +d)。"""
    p = combat.armor_parts(c, gd)
    head = f"穿戴 {p['worn']} → 護甲技能折算 {p['base']}" if p["worn"] else f"未穿甲:技能基礎 {p['base']}"
    parts = [head] + [f"{n} +{p[k]}" for k, n in (("passive", "被動護甲"), ("temper", "淬鍊"), ("shield", "護盾"),
                                                  ("undead", "亡者護甲")) if p[k]]
    body = " · ".join(parts)
    return body if short else f"戰鬥護甲 {total}:{body}"


class _extras:
    """讓被動護甲 / 亡者護甲這兩個夾具恆為 0 的維度非零(舊式與新式都呼叫同名函式,所以對帳仍成立)。"""

    def __enter__(self):
        self._saved = (mastery.passive_armor_bonus, necromancy.undead_armor_bonus)
        mastery.passive_armor_bonus = lambda actor, gamedata: 4
        necromancy.undead_armor_bonus = lambda actor: 6

    def __exit__(self, *a):
        mastery.passive_armor_bonus, necromancy.undead_armor_bonus = self._saved


def test_armor_with_passive_and_undead_layers_matches_the_old_formula_and_the_tip():
    """審查:夾具讓 passive / undead 恆為 0(中性化),分解提示漏掉這兩項、armor_parts 少加都殺不掉。"""
    n = 0
    with _extras():
        for name, c in _armor_builds():
            total = combat._armor_rating(c, gd)
            assert total == _old_armor_rating(c), name
            p = combat.armor_parts(c, gd)
            assert p["passive"] == 4 and p["undead"] == 6
            assert ui._armor_display(c, gd) == total
            tip = ui._armor_tip(c, gd)
            assert tip == _expected_armor_tip(c, total) and "被動護甲 +4" in tip and "亡者護甲 +6" in tip, tip
            n += 1
    assert n == 36


def test_armor_parts_decomposes_non_players_like_armor_rating():
    """armor_parts 是公開函式:非玩家(敵人 / 同伴)也回同形分解,與 `_armor_rating` 的非玩家分支一致(不再丟 AttributeError)。"""
    foe = combat.spawn_creature(gd, "wolf", RNG(1))
    for ward in (0, 9):
        if ward:
            foe.active_effects.append({"kind": "shield", "magnitude": ward, "turns": 3})
        p = combat.armor_parts(foe, gd)
        assert p == {"worn": 0, "base": foe.armor_rating, "passive": 0, "temper": 0, "shield": ward, "undead": 0}
        assert p["base"] + p["shield"] == combat._armor_rating(foe, gd)


def test_sheet_armor_beast_form_and_corrupt_equipment_do_not_crash():
    c = _char()
    c.beast_form = True
    assert ui._armor_display(c, gd) == lycanthropy.BEAST_ARMOR and "獸形" in ui._armor_tip(c, gd)
    assert ui._armor_tip(c, gd, short=True) == "獸形脫去穿戴護甲,只剩野獸厚皮"
    c2 = _char()
    c2.equipped = {"helmet": "NONEXISTENT_ITEM"}                               # 毀損存檔:角色卡不可崩(戰鬥路徑本來就會崩)
    assert ui._armor_display(c2, gd) == 0 and ui._armor_tip(c2, gd) == ""
    ui._sheet_view(c2, gd)
    c3 = _char()                                                               # 一件有效 + 一件未知:退回「名目值」(穿戴值 + 淬鍊),不是 0
    c3.equipped = {"cuirass": "iron_cuirass", "helmet": "NONEXISTENT_ITEM"}
    c3.armor_temper = {"iron_cuirass": 2}
    nominal = inventory.worn_armor_rating(c3, gd) + smithing.armor_temper_bonus(c3, gd)
    assert nominal > 0 and ui._armor_display(c3, gd) == nominal
    assert ui._sheet_view(c3, gd)["armor"] == nominal and ui._armor_tip(c3, gd) == ""


def test_equipment_panel_shows_the_combat_armor_with_a_breakdown_line():
    """穿戴與套裝面板:「護甲值」= 戰鬥實際值,總值不再等於各件名目值相加 → 下面補一行分解(web 與 rich 兩路徑)。"""
    c = _char(heavy_armor=100)
    c.equipped = {"helmet": "iron_helmet", "cuirass": "iron_cuirass"}
    c.armor_temper = {"iron_cuirass": 2}
    total = combat._armor_rating(c, gd)
    short = _expected_armor_tip(c, total, short=True)
    rows = {}
    saved = (ui._web, ui._emit_panel)
    ui._web, ui._emit_panel = object(), lambda title, r: rows.setdefault(title, r)
    try:
        ui.sheet_equipment(c, gd)
    finally:
        ui._web, ui._emit_panel = saved
    panel = rows["穿戴與套裝"]
    i = next(k for k, r in enumerate(panel) if r.get("k") == "護甲值")
    assert panel[i]["v"] == str(total)
    assert panel[i + 1] == {"t": "line", "s": f"　{short}", "c": "faint"}, panel[i + 1]
    from io import StringIO
    from rich.console import Console
    saved_c, saved_w = ui.console, ui._web
    ui.console, ui._web = Console(record=True, file=StringIO(), width=140), None
    try:
        ui.sheet_equipment(c, gd)
        out = ui.console.export_text()
    finally:
        ui.console, ui._web = saved_c, saved_w
    assert f"護甲值  {total}" in out and short in out, out[-400:]


# --- ③ 角色卡負重上限 = inventory.max_weight ------------------------------------------
def test_max_weight_is_bytewise_identical_to_the_pre_r200_formula():
    for strength in (20, 50, 100):
        for feather in (False, True):
            for mount in ("", "warhorse"):
                c = _char()
                c.attributes["strength"] = strength
                c.spell_effects = [{"kind": "feather", "magnitude": 1.0, "expires_at": 10 ** 9}] if feather else []
                c.active_mount = mount
                old = (formulas.max_encumbrance(c.attr("strength")) + spellfx.feather_bonus(c)
                       + mounts.saddlebag_bonus(c, gd))
                assert inventory.max_weight(c, gd) == old, (strength, feather, mount)
                p = inventory.max_weight_parts(c, gd)
                assert p["base"] + p["feather"] + p["saddlebag"] == old
                assert inventory.max_weight(c) == p["base"] + p["feather"]            # 無 gamedata:舊行為(不含鞍袋)


def test_sheet_carry_cap_includes_feather_and_saddlebag():
    c = _char()
    base = formulas.max_encumbrance(c.attr("strength"))
    v0 = ui._sheet_view(c, gd)
    assert v0["encumbrance"] == inventory.max_weight(c, gd) == base
    assert v0["encumbrance_tip"] == f"負重上限 {base}:力量 {c.attr('strength')} → {base}"
    c.spell_effects = [{"kind": "feather", "magnitude": 1.0, "expires_at": 10 ** 9}]
    c.active_mount = "warhorse"
    v = ui._sheet_view(c, gd)
    assert v["encumbrance"] == inventory.max_weight(c, gd) > base              # 原本只讀力量×5 → 顯示偏低
    feather, saddle = spellfx.FEATHER_CARRY_BONUS, mounts.saddlebag_bonus(c, gd)
    assert feather > 0 and saddle > 0
    assert v["encumbrance"] == base + feather + saddle
    assert v["encumbrance_tip"] == (f"負重上限 {v['encumbrance']}:力量 {c.attr('strength')} → {base}"
                                    f" · 羽落術 +{feather} · 鞍袋 +{saddle}"), v["encumbrance_tip"]


# --- ④ 撬鎖預覽認「免擲骰的鑰」 ---------------------------------------------------------
def _old_effective_pick_lock_chance(c, lock):
    if dungeon.has_skeleton_key(c, gd):
        return 1.0
    chance = min(0.95, dungeon.pick_lock_chance(c.skill("security"), lock) + formulas.luck_fortune(c.attr("luck")))
    return max(chance, mastery.lock_floor(c, gd))


def test_lock_chance_is_unchanged_except_the_tower_key_now_shows_certain():
    for sec in (0, 30, 80):
        for lock in (1, 40, 90):
            c = _char(security=sec)
            assert dungeon.effective_pick_lock_chance(c, gd, lock) == _old_effective_pick_lock_chance(c, lock)
            c.equipped["ring"] = "skeleton_key"
            assert dungeon.effective_pick_lock_chance(c, gd, lock) == 1.0 == _old_effective_pick_lock_chance(c, lock)
            c.equipped.pop("ring")
            c.tower_key_charge = True
            assert dungeon.effective_pick_lock_chance(c, gd, lock) == 1.0                  # 塔之鑰在身:預覽必定成功
            assert _old_effective_pick_lock_chance(c, lock) < 1.0                          # (舊式只認骷髏鑰匙,會顯示一般機率)
    c = _char()
    assert dungeon.lock_key_kind(c, gd) is None
    c.equipped["ring"] = "skeleton_key"
    assert dungeon.lock_key_kind(c, gd) == "skeleton"
    c.tower_key_charge = True
    assert dungeon.lock_key_kind(c, gd) == "tower"                            # 優先序同 pick_lock:塔之鑰先消耗


class _CountRNG(RNG):
    """記錄 chance 呼叫次數(結果固定成功)。"""

    def __init__(self):
        super().__init__(0)
        self.calls = 0

    def chance(self, p):
        self.calls += 1
        return True


def test_pick_lock_branches_on_lock_key_kind_with_the_same_precedence():
    # 塔之鑰:免擲骰、免開鎖器,用掉蓄勢
    c = _picks(_char(security=0), 0)
    c.tower_key_charge = True
    rng = _CountRNG()
    r = dungeon.pick_lock(c, gd, 90, rng)
    assert r["success"] and r["tower_key"] is True and rng.calls == 0 and c.tower_key_charge is False
    # 骷髏鑰匙:免擲骰、不耗開鎖器、不給 xp
    c = _picks(_char(security=0), 2)
    c.equipped["ring"] = "skeleton_key"
    rng = _CountRNG()
    r = dungeon.pick_lock(c, gd, 90, rng)
    assert r["success"] and r.get("skeleton_key") is True and rng.calls == 0 and inventory.count_item(c, "lockpick") == 2
    assert r["skill_events"] == []
    # 兩把都有:先用塔之鑰,骷髏鑰匙留著(第二次才用)
    c = _picks(_char(security=0), 0)
    c.tower_key_charge = True
    c.equipped["ring"] = "skeleton_key"
    first = dungeon.pick_lock(c, gd, 90, _CountRNG())
    assert first["tower_key"] is True and c.tower_key_charge is False
    second = dungeon.pick_lock(c, gd, 90, _CountRNG())
    assert second.get("skeleton_key") is True and second["tower_key"] is False
    # 無鑰:一般擲骰(耗一根開鎖器)
    c = _picks(_char(security=40), 3)
    rng = _CountRNG()
    r = dungeon.pick_lock(c, gd, 5, rng)
    assert rng.calls >= 1 and r["tower_key"] is False and not r.get("skeleton_key") and inventory.count_item(c, "lockpick") == 2


def _confirm_message(c, lock=5, seed=3):
    """走真的 _resolve_container:回傳確認文字與容器是否開啟。"""
    st = _state(c, seed)
    msgs = []
    gold0 = c.gold
    with _ui_patched(confirm=lambda msg, *a, **k: (msgs.append(msg), True)[1],
                     message=lambda *a, **k: None, show_events=lambda *a, **k: None,
                     loot_report=lambda *a, **k: None):
        M._resolve_container(st, gd, {"locked": lock, "loot": [{"gold": [5, 5]}]}, "箱子")
    return msgs, st, c.gold > gold0


def test_lock_confirm_text_follows_the_real_pick_lock_outcome():
    # 一般:有開鎖器 → 成功率 = effective_pick_lock_chance,開鎖器數量
    c = _picks(_char(security=40), 3)
    expected = ui.pct(dungeon.effective_pick_lock_chance(c, gd, 5))
    msgs, _st, _opened = _confirm_message(copy.deepcopy(c))
    assert f"成功率約 {expected}%" in msgs[0] and "開鎖器 ×3" in msgs[0] and "必定成功" not in msgs[0]
    # 塔之鑰:無開鎖器也必定成功、用掉蓄勢(原本顯示一般機率與「開鎖器 ×0」)
    c = _picks(_char(security=0), 0)
    c.tower_key_charge = True
    msgs, st, opened = _confirm_message(c, lock=90)
    assert "塔之鑰已蓄勢:必定成功" in msgs[0] and "開鎖器" not in msgs[0] and "成功率約" not in msgs[0], msgs[0]
    assert c.tower_key_charge is False and opened, "預覽說必定成功,實際也要開啟並消耗蓄勢"
    # 骷髏鑰匙:必定成功、不耗開鎖器
    c = _picks(_char(security=0), 2)
    c.equipped["ring"] = "skeleton_key"
    msgs, st, opened = _confirm_message(c, lock=90)
    assert "骷髏鑰匙:必定成功" in msgs[0] and "成功率約" not in msgs[0]
    assert opened and inventory.count_item(c, "lockpick") == 2
    # 兩把都有:先塔之鑰(與 pick_lock 同優先序),骷髏鑰匙不受影響
    c = _picks(_char(security=0), 0)
    c.tower_key_charge = True
    c.equipped["ring"] = "skeleton_key"
    msgs, st, opened = _confirm_message(c, lock=90)
    assert "塔之鑰已蓄勢" in msgs[0] and c.tower_key_charge is False and dungeon.has_skeleton_key(c, gd) and opened
    # 無鑰無開鎖器:仍擋下
    c = _picks(_char(), 0)
    msgs, st, opened = _confirm_message(c)
    assert msgs == [] and not opened


# --- ⑤ 充能預覽 = 實際結算 ---------------------------------------------------------------
def test_recharge_outcome_is_the_old_inline_arithmetic():
    wid = enchant_weapon_status_id("steel_sword", "soul_trap", 10, 1)
    cap = enchanting.charge_capacity(gd, wid)
    for cur in (0, 3, 9, 10):
        for gem in ("filled_petty_soul_gem", "filled_common_soul_gem", "filled_grand_soul_gem"):
            c = _char()
            c.enchant_charges[wid] = cur
            o = enchanting.recharge_outcome(c, gd, wid, gem)
            gain = gd.item(gem)["soul"] * formulas.CHARGE_PER_SOUL
            assert o["new"] == min(cap, cur + gain) and o["gain"] == gain and o["cap"] == cap and o["cur"] == cur
            assert o["applied"] == o["new"] - cur and o["wasted"] == gain - o["applied"] and o["wasted"] >= 0


def test_recharge_menu_label_and_the_real_action_agree():
    wid = enchant_weapon_status_id("steel_sword", "soul_trap", 10, 1)
    cap = enchanting.charge_capacity(gd, wid)
    gems = ("filled_petty_soul_gem", "filled_common_soul_gem", "filled_grand_soul_gem")
    saw_waste = saw_clean = False
    for pick in gems:
        c = _char()
        inventory.add_item(c, wid, 1)
        for g in gems:
            inventory.add_item(c, g, 1)
        c.enchant_charges[wid] = 3
        before = enchanting.recharge_outcome(c, gd, wid, pick)
        st = _state(c)
        seen = {}

        def menu(title, opts, allow_back=False, **kw):
            seen.setdefault("n", 0)
            seen["n"] += 1
            if seen["n"] == 1:
                return wid
            seen["labels"] = dict(opts)
            return pick

        said = []
        with _ui_patched(menu=menu, message=lambda text, *a, **k: said.append(text)):
            M.action_recharge_enchant(st, gd)
        tail = f"(溢出 {before['wasted']} 點白耗)"
        assert (tail in said[-1]) == bool(before["wasted"]), said                # 結果訊息:溢出才標白耗、數字 = 預覽
        assert f"充能 {before['new']}/{cap}" in said[-1], said
        for g in gems:                                                          # 每顆的標籤 = 單一出處的實際結算(選單當時的狀態)
            fresh = _fresh_for_label(wid, g)
            o = enchanting.recharge_outcome(fresh, gd, wid, g)
            assert seen["labels"][g] == M._recharge_gem_label(fresh, gd, wid, g)
            assert f"+{o['applied']} 充能" in seen["labels"][g]
            assert ("白耗" in seen["labels"][g]) == bool(o["wasted"])
        assert c.enchant_charges[wid] == before["new"] == min(cap, 3 + before["gain"])
        assert c.enchant_charges[wid] - 3 == before["applied"]
        assert inventory.count_item(c, pick) == 0                               # 魂石照耗(溢出的部分白耗)
        saw_waste |= bool(before["wasted"])
        saw_clean |= not before["wasted"]
    assert saw_waste and saw_clean                                              # 兩種情形都走過(非空轉)


def _fresh_for_label(wid, gem):
    c = _char()
    inventory.add_item(c, wid, 1)
    inventory.add_item(c, gem, 1)
    c.enchant_charges[wid] = 3
    return c


# --- 內嵌常數收斂 ---------------------------------------------------------------------------
def test_inn_fee_and_every_label_share_one_constant():
    saved = M.INN_REST_FEE
    M.INN_REST_FEE = 17
    try:
        c = _char()
        c.gold = 100
        with _ui_patched(message=lambda *a, **k: None):
            M._inn_rest(_state(c), gd)
        assert c.gold == 83                                                      # 扣款走常數
        cap = {}
        with _ui_patched(menu=lambda title, opts, allow_back=False, **kw: (cap.setdefault("o", list(opts)), None)[1],
                         message=lambda *a, **k: None):
            M.action_inn(_state(_char()), gd)
        assert any(k == "rest" and "17 金" in lbl and "10 金" not in lbl for k, lbl in cap["o"]), cap["o"]
    finally:
        M.INN_REST_FEE = saved
    tree = ast.parse((ROOT / "tesrpg" / "main.py").read_text(encoding="utf-8"))
    labels = [n.elts[1] for n in ast.walk(tree) if isinstance(n, ast.Tuple) and len(n.elts) == 2
              and isinstance(n.elts[0], ast.Constant) and n.elts[0].value == "inn_rest"
              and isinstance(n.elts[1], ast.JoinedStr)]
    assert labels, "找不到旅店直達過夜的標籤 → 空轉"                              # 審查:原文字掃描,算式被改成 INN_REST_FEE + 5 也過
    for js in labels:
        fvs = [v for v in js.values if isinstance(v, ast.FormattedValue)]
        assert len(fvs) == 1 and isinstance(fvs[0].value, ast.Name) and fvs[0].value.id == "INN_REST_FEE", ast.dump(js)
        assert not any(isinstance(v, ast.Constant) and "10 金" in str(v.value) for v in js.values)


def _volley_option_note(factor):
    c = _char(marksman=100)
    inventory.add_item(c, "hunting_bow", 1)
    assert inventory.equip_weapon(c, gd, "hunting_bow")
    c.mastery_choices["marksman_75"] = "volley_shot"
    assert mastery.has_bow_technique(c, gd, "volley")
    foes = [combat.spawn_creature(gd, "wolf", RNG(i)) for i in (1, 2)]
    saved_f, saved_m = formulas.VOLLEY_DAMAGE_FACTOR, M._grouped_combat_menu
    formulas.VOLLEY_DAMAGE_FACTOR = factor

    def grab(opts):
        raise _Captured(opts)

    M._grouped_combat_menu = grab
    try:
        with _ui_patched(combat_status_group=lambda *a, **k: None, message=lambda *a, **k: None):
            try:
                M._choose_combat_action(_state(c), gd, foes, [])
            except _Captured as cap:
                opt = next(o for o in cap.payload if o[0] == "volley")
                return opt[2]["chips"][0]["text"] + opt[2].get("note", "")
    finally:
        formulas.VOLLEY_DAMAGE_FACTOR, M._grouped_combat_menu = saved_f, saved_m
    raise AssertionError("沒有走到動作選單")


def test_volley_label_follows_the_damage_factor_constant():
    assert f"{ui.pct(formulas.VOLLEY_DAMAGE_FACTOR)}%" in _volley_option_note(formulas.VOLLEY_DAMAGE_FACTOR)
    text = _volley_option_note(0.5)
    assert "50%" in text and "60%" not in text, text


def test_volley_milestone_description_matches_the_constant():
    """資料文字(mastery.json)也是一份內嵌的 60%:改常數時這條測試會逼你同步改文字。"""
    import json
    data = json.load(open(ROOT / "tesrpg" / "data" / "mastery.json", encoding="utf-8"))
    nodes = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    opt = next(o for n in nodes for o in n["options"] if o.get("opt_id") == "volley_shot" and n["id"] == "marksman_75")
    assert f"{ui.pct(formulas.VOLLEY_DAMAGE_FACTOR)}%" in opt["desc"], opt["desc"]


def test_codex_hit_ceiling_text_matches_the_constant():
    """資料文字(codex.json 的戰鬥說明)也內嵌一份「N% 命中上限」:改常數時這條測試會逼你同步改文字。"""
    raw = (ROOT / "tesrpg" / "data" / "codex.json").read_text(encoding="utf-8")
    assert f"{ui.pct(formulas.HIT_CHANCE_CEIL)}% 命中上限" in raw


def test_player_hit_chain_ceiling_follows_the_constant():
    """審查 m1:命中鏈的二次夾限(武器速度 / 里程碑命中 / 瞄準射)原本寫死 0.95,與 HIT_CHANCE_CEIL 脫鉤 →
    提示會寫「99% 命中上限」而實際鏈仍夾 0.95。改引用常數後,三道夾限都跟著常數走。"""
    c = _char(blade=100)
    c.attributes["agility"] = 100
    foe = combat.spawn_creature(gd, "wolf", RNG(1))
    foe.agility = 40
    chain = lambda **kw: combat._hit_chain(c, foe, 100, 1.0, kw.get("wmod", {}), 1.0, False, 0.0,
                                           formulas.BLOCK_HIT_PENALTY, aimed=kw.get("aimed", False))
    variants = {"base": {}, "milestone": {"wmod": {"hit": 0.5}}, "aimed": {"aimed": True}}
    assert {k: chain(**v) for k, v in variants.items()} == {k: formulas.HIT_CHANCE_CEIL for k in variants}
    saved = formulas.HIT_CHANCE_CEIL
    formulas.HIT_CHANCE_CEIL = 0.99
    try:
        assert {k: chain(**v) for k, v in variants.items()} == {k: 0.99 for k in variants}
    finally:
        formulas.HIT_CHANCE_CEIL = saved


def test_hit_ceiling_tip_follows_the_constant():
    from tests import test_r197_fatigue_breath as R
    foe = R._foe("bandit")
    c = R._BUILDS["劍士(未飽和)"]()
    R._set_swing_ratio(c, 0.6)
    saved = formulas.HIT_CHANCE_CEIL
    formulas.HIT_CHANCE_CEIL = 0.99
    try:
        [t] = R._fatigue_tags(R._view(c, enemies=[foe])["me"]["tags"])
    finally:
        formulas.HIT_CHANCE_CEIL = saved
    assert "99% 命中上限" in t["tip"] and "95%" not in t["tip"], t["tip"]


def test_major_skill_xp_legend_follows_the_constant():
    """技能頁「✦ 主修技能(升點給 ×N 等級經驗)」三處說明皆取自常數。"""
    src = (ROOT / "tesrpg" / "ui" / "console.py").read_text(encoding="utf-8")
    assert "×1.5" not in src and src.count("MAJOR_SKILL_XP_MULT") >= 3
    saved = formulas.MAJOR_SKILL_XP_MULT
    formulas.MAJOR_SKILL_XP_MULT = 2.0
    try:
        from io import StringIO
        from rich.console import Console
        c = _char()
        saved_console, saved_web = ui.console, ui._web
        ui.console, ui._web = Console(record=True, file=StringIO(), width=120), None
        try:
            ui.skill_table(c, gd)
            out = ui.console.export_text()
        finally:
            ui.console, ui._web = saved_console, saved_web
    finally:
        formulas.MAJOR_SKILL_XP_MULT = saved
    assert "×2 等級經驗" in out and "×1.5" not in out, out[-300:]


def _fence_buy(infamy, cheap_market=False, gold=500):
    """走真的 action_fence「購入」流程:回傳 (角色, 選單選項 [(iid, 標籤)], 選了哪件, 實際扣款)。
    cheap_market=True → 把一般買價壓到 1 金,讓「max(買價, 銷贓價+1)」的防套利地板真的咬合(現行資料下它不會自然咬合)。"""
    from tesrpg.systems import world
    c = _char()
    c.gold = gold
    c.infamy = infamy
    st = _state(c)
    seen = {"n": 0}

    def menu(title, opts, allow_back=False, **kw):
        seen["n"] += 1
        if seen["n"] == 1:
            return "buy"
        if seen["n"] == 2:
            seen["opts"] = list(opts)
            seen["pick"] = opts[0][0]
            return seen["pick"]
        return None

    saved = world.buy_price
    if cheap_market:
        world.buy_price = lambda char, gamedata, iid: 1
    try:
        with _ui_patched(menu=menu, message=lambda *a, **k: None, show_events=lambda *a, **k: None):
            M.action_fence(st, gd)
    finally:
        world.buy_price = saved
    return c, seen["opts"], seen["pick"], gold - c.gold


def test_black_market_label_price_equals_the_charged_price_and_keeps_the_arbitrage_floor():
    price_of = lambda lbl: int(re.search(r"— (\d+) 金", lbl).group(1))
    for infamy, cheap in ((0, False), (100, False), (100, True)):
        c, opts, pick, spent = _fence_buy(infamy, cheap)
        assert len(opts) >= 3
        assert spent == price_of(dict(opts)[pick]), (infamy, cheap, spent, dict(opts)[pick])    # 標籤價 = 實際扣款
        for iid, lbl in opts:                                                      # 防套利地板:每件買價恆 > 銷贓價
            assert price_of(lbl) > int(world_sell(c, iid) * (1 + crime.fence_bonus(c))), (infamy, cheap, iid)
    c, opts, pick, spent = _fence_buy(100, True)                                   # 地板真的咬合的情境(非空轉)
    assert crime.fence_bonus(c) == max(crime.FENCE_BONUS_BY_TIER)
    assert all(price_of(lbl) > 1 for _i, lbl in opts), "買價被壓到 1 金時,地板必須把價格抬回銷贓價以上"


def world_sell(c, iid):
    from tesrpg.systems import world
    return world.sell_price(c, gd, iid)


# --- 非機率百分比:一律四捨五入(AST 守衛)------------------------------------------------
def _truncating_percents(source: str) -> list:
    """回傳 source 內所有「截斷取整的 ×100 顯示」[(行號, 該行)]:`int(...)` / `floor(...)`(含 math.floor)的引數樹內任何位置出現
    `<expr> * 100`、`(…×100) // n`、`'%d' % (…×100)`;被 `round(...)` 包住的不算。呼叫跨多行時,`trunc-ok` 標記看整個行範圍
    (例:進度百分比刻意截斷,未滿不顯示 100%)。"""
    lines = source.splitlines()
    is100 = lambda n: isinstance(n, ast.Constant) and n.value in (100, 100.0)

    def mult100(n):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "round":
            return False                                                       # 四捨五入包住 → 不是截斷
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult) and (is100(n.left) or is100(n.right)):
            return True
        return any(mult100(ch) for ch in ast.iter_child_nodes(n))

    bad = []
    for n in ast.walk(ast.parse(source)):
        hit = False
        if isinstance(n, ast.Call) and len(n.args) == 1:
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            hit = name in ("int", "floor") and mult100(n.args[0])
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.FloorDiv):
            hit = mult100(n.left)
        elif (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) and isinstance(n.left, ast.Constant)
              and isinstance(n.left.value, str) and "%d" in n.left.value):
            hit = mult100(n.right)
        if hit and not any("trunc-ok" in ln for ln in lines[n.lineno - 1:getattr(n, "end_lineno", n.lineno)]):
            bad.append((n.lineno, lines[n.lineno - 1].strip()[:80]))
    return bad


def test_no_truncating_percent_display_remains():
    """`int(x * 100)` 會因浮點誤差少顯示 1%(0.58 * 100 = 57.99…、0.29 → 28):顯示百分比一律四捨五入(ui.pct / round)。
    掃 tesrpg/ 與 tools/(審查:bestiary 產生器有 3 處潛伏)。"""
    assert int(0.29 * 100) == 28 and round(0.29 * 100) == 29                      # 問題真實存在
    files = sorted((ROOT / "tesrpg").rglob("*.py")) + sorted((ROOT / "tools").glob("*.py"))
    assert len(files) > 50
    for p in files:
        bad = _truncating_percents(p.read_text(encoding="utf-8"))
        assert not bad, (p.relative_to(ROOT).as_posix(), bad)
    for src in ("x = int(p * 100)", "x = int(_m * 0.7 * 100)", "x = int(100 * d)", "x = int(a * 100.0)",
                "f'{int(m * 100)}%'", "x = int(a * 100 / b)", "x = int(100 * a / b)", "x = int(x * 100 // 1)",
                "x = (x * 100) // 1", "x = math.floor(x * 100)", "x = floor(x * 100)", "x = '%d' % (x * 100)",
                "x = int(x * 100 - 1e-9)"):
        assert _truncating_percents(src), f"守衛抓不到:{src!r}"
    for src in ("x = int(round(p * 100))", "x = round(p * 100)", "x = int(cur / need * 100)  # trunc-ok:進度",
                "x = int(\n    cur / need * 100)  # trunc-ok:跨行", "x = int(p * 10)", "x = int(round(a * 100 / b))"):
        assert not _truncating_percents(src), src


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
