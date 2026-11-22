"""R202 可見性缺口包(R199 審計 D4):玩家按下去之前看不到的「成功率 / 數量 / 後果」補上。

🔴 原則同 R197 / R199 / R200:玩家看到的數字必須由與實擲共用的**單一出處**算出,預覽不自己重算公式層;
   不動任何機率與結果(零行為改動)。本檔每一組守衛都走「預覽數字 == 真實擲骰 / 真實結算」對帳,並讓中性夾具變非中性
   (行竊失風減免 / 魅惑術、鈍性刑期下限…),避免夾具預設值把某個維度悄悄中和(見記憶 integration-test-vacuity)。

A 波(犯罪):行竊失手賞金(`crime.steal_fine`)+ 監牢刑期(`crime.jail_hours` 已是單一公式,選單補顯示)。
"""
import contextlib
import copy
import io
import re
from pathlib import Path
from unittest import mock

from rich.console import Console

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import crime, mastery, spellfx, stats
import tesrpg.ui.console as ui

gd = get_gamedata()
ROOT = Path(__file__).resolve().parent.parent


def _char(**kw):
    c = build_character(gd, name="客", sex="male", race=kw.get("race", "nord"), birthsign="warrior",
                        class_id=kw.get("class_id", "warrior"))
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.fatigue = c.max_fatigue
    c.gold = 500
    return c


def _state(c=None, seed=7):
    return GameState(player=c or _char(), time=GameTime(), rng=RNG(seed))


@contextlib.contextmanager
def _quiet_ui(menu=None):
    """靜音 console;可選擇把 ui.menu 換成假函式(離開時一律還原)。"""
    saved = (ui.console, ui.menu)
    ui.console = Console(file=io.StringIO(), width=100)
    if menu is not None:
        ui.menu = menu
    try:
        yield
    finally:
        ui.console, ui.menu = saved


class _ForceRNG(RNG):
    """chance(p) 回固定結果(並記錄 p);其餘照常。"""

    def __init__(self, seed=0, result=False):
        super().__init__(seed)
        self.result, self.ps = result, []

    def chance(self, p):
        self.ps.append(p)
        return self.result


def _items_by_value():
    ids = sorted((i for i in gd.items if gd.item(i).get("value") is not None), key=lambda i: gd.item(i)["value"])
    return ids[0], ids[len(ids) // 2], ids[-1]            # 最便宜(吃 20 金下限)/ 中位 / 最貴


# --- A1 行竊失手賞金 -----------------------------------------------------------
def test_steal_fine_equals_the_real_failure_bounty_across_every_dimension():
    cheap, mid, dear = _items_by_value()
    prov = crime.province_of(_char(), gd)
    variants = {                                            # 讓兩個乘數維度各自非中性(夾具預設會把它們中和成 ×1)
        "neutral": (None, None),
        "perk0.5": (0.5, None),
        "charm0.7": (None, 0.7),
        "both": (0.5, 0.7),
    }
    fines = {}
    for name, (bf, charm) in variants.items():
        with contextlib.ExitStack() as st:
            if bf is not None:
                st.enter_context(mock.patch.object(mastery, "theft_bonus",
                                                   lambda c, g, _bf=bf: {"bounty_factor": _bf, "steal_bonus": 0.0}))
            if charm is not None:
                st.enter_context(mock.patch.object(spellfx, "charm_bounty_factor", lambda c, _f=charm: _f))
            for iid in (cheap, mid, dear):
                char = _char()
                preview = crime.steal_fine(char, gd, iid)
                before = crime.bounty(char, prov)
                r = crime.steal_item(char, gd, iid, _ForceRNG(result=False))          # 強制失手 = 真實擲骰路徑
                assert r["caught"] and not r["ok"]
                assert r["bounty_added"] == preview, (name, iid, r["bounty_added"], preview)
                assert crime.bounty(char, prov) - before == preview, (name, iid)
                fines[(name, iid)] = preview
    assert fines[("neutral", cheap)] == 20, "最便宜的贓物吃 20 金下限"
    assert fines[("neutral", dear)] > fines[("perk0.5", dear)] > fines[("both", dear)] > 0, "乘數維度必須真的非中性"
    assert fines[("neutral", dear)] > fines[("charm0.7", dear)], "魅惑術維度必須真的非中性"


def test_steal_menu_label_shows_the_same_chance_and_fine_as_the_real_roll():
    cheap, mid, dear = _items_by_value()
    char = _char()
    char.skills.update(sneak=60, security=40)
    for iid in (cheap, mid, dear):
        label = M._steal_option_label(char, gd, iid, 2)
        chance_rng, fail_rng = _ForceRNG(result=True), _ForceRNG(result=False)
        crime.steal_item(copy.deepcopy(char), gd, iid, chance_rng)                    # 實擲:擲骰引數 = 得手率
        r = crime.steal_item(copy.deepcopy(char), gd, iid, fail_rng)                  # 實擲:失手 → 賞金增量
        assert f"得手 {ui.pct(chance_rng.ps[0])}%" in label, (iid, label, chance_rng.ps)
        assert f"失手賞金 +{r['bounty_added']}" in label, (iid, label, r["bounty_added"])


# --- A2 監牢刑期 ---------------------------------------------------------------
def test_jail_option_label_hours_equal_the_real_sentence():
    """衛兵盤查的「入獄服刑」選項標出刑期;真走 guard_confrontation(假 ui.menu 選 jail),標籤時數 == 實際推進的時間。"""
    for bounty in (1, 100, 500, 2400):                      # 100 以內吃 6 小時下限;2400 → 1152 小時
        state = _state()
        char = state.player
        prov = crime.province_of(char, gd)
        crime.add_bounty(char, prov, bounty)
        seen = {}

        def fake_menu(title, options, allow_back=False):
            seen["opts"] = dict(options)
            return "jail"

        t0 = state.time.absolute_hours()
        with _quiet_ui(menu=fake_menu):
            M.guard_confrontation(state, gd)
        label = seen["opts"]["jail"]
        shown = int(re.search(r"關 (\d+) 小時", label).group(1))
        spent = state.time.absolute_hours() - t0
        assert shown == spent, (bounty, label, spent)
        assert crime.bounty(char, prov) == 0, "服刑後賞金清空(標籤『賞金一筆勾銷』屬實)"
        assert "賞金一筆勾銷" in label
    short = _state()
    crime.add_bounty(short.player, crime.province_of(short.player, gd), 1)
    long_ = _state()
    crime.add_bounty(long_.player, crime.province_of(long_.player, gd), 2400)
    assert crime.jail_hours(1) == 6 and crime.jail_hours(2400) == 1152, "夾具要同時覆蓋下限與長刑期兩段"


# --- B1 原地休息回復量 ---------------------------------------------------------
def _hurt(c, frac=0.2):
    c.health, c.fatigue, c.magicka = c.max_health * frac, c.max_fatigue * frac, c.max_magicka * frac
    return c


def _rest_run(c, hours):
    """真走 action_rest(假 ask_int 回 hours、略過隨機休息事件);回 (提示文字, 結果訊息, 前, 後)。"""
    state = _state(c)
    seen = {}

    def fake_ask_int(prompt, default, lo, hi):
        seen["prompt"] = prompt
        return hours

    before = (c.fatigue, c.health, c.magicka)
    saved = (ui.ask_int, M.maybe_event)
    ui.ask_int, M.maybe_event = fake_ask_int, (lambda *a, **k: None)
    try:
        with _quiet_ui():
            M.action_rest(state, gd)
            out = ui.console.file.getvalue()
    finally:
        ui.ask_int, M.maybe_event = saved
    return seen["prompt"], out, before, (c.fatigue, c.health, c.magicka)


def _segment(prompt, hours):
    return re.search(rf"{hours} 小時:([^｜)]*)", prompt).group(1).strip()


def test_rest_prompt_estimates_equal_what_resting_really_restores():
    builds = {
        "nord": dict(race="nord", class_id="mage"),
        "argonian_histskin": dict(race="argonian", class_id="mage"),      # R61 亞龍癒膚:生命回復 ×
        "altmer_magicka": dict(race="altmer", class_id="mage"),            # 高貴血脈:法力回復 ×
    }
    gains = {}
    for name, kw in builds.items():
        for hours in (4, 8, 24):
            c = _hurt(_char(**kw))
            c.attributes["willpower"] = 80                                  # 意志「施法續航」非中性(base-40 才中性)
            prompt, text, before, after = _rest_run(c, hours)
            real = " ".join([f"體力+{round(after[0] - before[0])}", f"生命+{round(after[1] - before[1])}",
                             f"法力+{round(after[2] - before[2])}"])
            assert _segment(prompt, hours) == real, (name, hours, prompt, real)
            assert f"({real})" in text, (name, hours, text)                  # 事後訊息報的是同一組實際回復量
            gains[(name, hours)] = after
    assert gains[("nord", 24)][0] >= gains[("nord", 8)][0], "時數越長回得越多(含上限夾限)"


def test_rest_race_and_willpower_dimensions_are_really_non_neutral():
    """上一測的對帳要有意義,三個回復維度(亞龍癒膚 / 高精靈回魔 / 意志續航)必須各自真的改變數字
    (以占最大值的比例比較:各種族最大生命 / 法力不同,不可比絕對值;選 4 小時 + 10% 起點避開上限夾限遮蔽)。"""
    def frac(race, wp=None):
        c = _hurt(_char(race=race, class_id="mage"), 0.1)
        if wp:
            c.attributes["willpower"] = wp
        _, _, _, after = _rest_run(c, 4)
        return after[1] / c.max_health, after[2] / c.max_magicka
    nord, argonian, altmer, nord_wp = frac("nord"), frac("argonian"), frac("altmer"), frac("nord", wp=80)
    assert argonian[0] > nord[0], "亞龍癒膚(R61)維度必須非中性"
    assert altmer[1] > nord[1], "高精靈高貴血脈回魔維度必須非中性"
    assert nord_wp[1] > nord[1], "意志「施法續航」維度必須非中性"


def test_rest_prompt_marks_full_resources_and_hides_magicka_for_the_atronach():
    full = _char(class_id="mage")
    prompt, text, _, _ = _rest_run(full, 8)
    assert "體力滿 生命滿 法力滿" in _segment(prompt, 8) and "體力+0" not in prompt
    hurt = _hurt(_char(class_id="mage"))
    hurt.birthsign = "atronach"
    m0 = hurt.magicka
    prompt, text, before, after = _rest_run(hurt, 8)
    assert "法力" not in prompt and after[2] == m0, "巨魔像座法力不回 → 預估不列法力、實際也不變"
    assert "法力不會自然回復" in text


def test_rest_outcome_is_the_single_source_for_any_hours():
    """不只提示列出的 4/8/24:任意時數,`rest_outcome` 的新值 == 真實休息後的數值(逐位元組,含浮點)。"""
    for hours in (1, 3, 5, 11, 17, 24):
        c = _hurt(_char(race="altmer", class_id="mage"), 0.37)
        predicted = M.rest_outcome(c, gd, hours)
        _, _, _, after = _rest_run(c, hours)
        assert (predicted["fatigue"], predicted["health"], predicted["magicka"]) == after, hours


# --- B2 淬鍊每級威力 -----------------------------------------------------------
_WORN = {"helmet": "leather_helmet", "cuirass": "leather_cuirass", "gauntlets": "leather_bracers",
         "boots": "leather_boots", "shield": "iron_shield"}


def _smith(power):
    """鍛造 100(上限 +5)、持鐵劍、穿 5 件可淬鍊護甲、錠管夠;`temper_power`(鋒銳里程碑倍率)以補丁設成指定值。"""
    from tesrpg.systems import inventory
    c = _char()
    c.skills["smithing"] = 100
    c.weapon = "iron_sword"
    c.equipped = dict(_WORN)
    for ingot in ("iron_ingot", "wolf_pelt"):
        inventory.add_item(c, ingot, 40)
    return c


def test_temper_preview_equals_the_real_combat_bonus_before_and_after_each_real_temper():
    from tesrpg.systems import smithing
    gains_by_power = {}
    for power in (0.0, 0.5, 0.35):
        with mock.patch.object(mastery, "temper_power", lambda c, g, _p=power: _p):
            c = _smith(power)
            weapon_gains, armor_gains = [], []
            for _ in range(5):                                           # 武器:鍛造 100 → 上限 5,逐級真淬
                pv = smithing.temper_preview(c, gd, "iron_sword")
                assert pv["stat"] == "damage" and pv["now"] == smithing.weapon_temper_bonus(c, gd)
                assert smithing.temper(c, gd, "iron_sword")["ok"]
                assert pv["after"] == smithing.weapon_temper_bonus(c, gd), (power, pv)
                weapon_gains.append(pv["after"] - pv["now"])
            for k in range(8):                                           # 護甲:輪流淬不同件;預覽 = 淬後「各件合計」的實際值
                iid = list(_WORN.values())[k % 5]
                pv = smithing.temper_preview(c, gd, iid)
                assert pv["stat"] == "armor" and pv["now"] == smithing.armor_temper_bonus(c, gd)
                assert smithing.temper(c, gd, iid)["ok"]
                assert pv["after"] == smithing.armor_temper_bonus(c, gd), (power, k, pv)
                armor_gains.append(pv["after"] - pv["now"])
            gains_by_power[power] = (weapon_gains, armor_gains)
    assert gains_by_power[0.0] == ([2] * 5, [1] * 8), "temper_power=0:每級固定 +2 傷害 / +1 護甲"
    assert gains_by_power[0.5][0] == [3] * 5, "整數倍率下武器增量固定 +3"
    wg, ag = gains_by_power[0.35]
    assert len(set(wg)) > 1 and len(set(ag)) > 1, "非整數倍率:int 截斷落在總和上 → 每級增量不是常數(預覽不能寫死『每級 +N』)"


def test_temper_menus_show_the_preview_and_cap_through_the_real_actions():
    from tesrpg.systems import smithing
    armorer = next(loc for loc, d in gd.world["locations"].items() if "armorer" in d.get("services", []))
    with mock.patch.object(mastery, "temper_power", lambda c, g: 0.35):
        for runner, name in ((M.action_temper, "鐵匠"), (M._guild_armory_temper, "軍械庫")):
            c = _smith(0.35)
            c.location_id = armorer
            for _ in range(2):                                           # 手持鐵劍淬到 +2;頭盔淬到 +1
                smithing.temper(c, gd, "iron_sword")
            smithing.temper(c, gd, "leather_helmet")
            state = _state(c)
            seen = {}

            def fake_menu(title, options, allow_back=False):
                seen["opts"] = dict(options)
                return None

            with _quiet_ui(menu=fake_menu):
                runner(state, gd)
            wpv = smithing.temper_preview(c, gd, "iron_sword")
            hpv = smithing.temper_preview(c, gd, "leather_helmet")
            assert f"傷害 +{wpv['now']}→+{wpv['after']}" in seen["opts"]["iron_sword"], (name, seen["opts"]["iron_sword"])
            assert f"護甲淬鍊合計 +{hpv['now']}→+{hpv['after']}" in seen["opts"]["leather_helmet"], (name, seen["opts"]["leather_helmet"])
            # 護甲數字是「全身穿戴件淬鍊加成的合計」:每件顯示同一個(審查 F3)→ 文案必須標『合計』
            assert seen["opts"]["leather_cuirass"].count("護甲淬鍊合計") == 1 and "護甲加成" not in seen["opts"]["leather_cuirass"]
            for _ in range(3):                                           # 鐵劍再淬 3 次到上限 +5 → 只列現值、標已達上限
                smithing.temper(c, gd, "iron_sword")
            with _quiet_ui(menu=fake_menu):
                runner(state, gd)
            assert "已達上限" in seen["opts"]["iron_sword"] and "→" not in seen["opts"]["iron_sword"], seen["opts"]["iron_sword"]


# --- B3 換裝對比 ---------------------------------------------------------------
@contextlib.contextmanager
def _capture_panels():
    """web 分支:攔 ui._emit_panel,收集 (title, rows);離開時還原 ui._web / ui._emit_panel。"""
    got = []
    saved = (ui._web, ui._emit_panel)
    ui._web, ui._emit_panel = object(), (lambda title, rows: got.append((title, rows)))
    try:
        yield got
    finally:
        ui._web, ui._emit_panel = saved


def _kv(rows, key):
    return next((r["v"] for r in rows if r.get("t") == "kv" and r["k"] == key), None)


def test_armor_compare_shows_the_combat_armor_the_sheet_will_show_after_really_equipping():
    from tesrpg.systems import combat, inventory
    scenarios = [                                           # (護甲技能, 新件淬鍊級):讓「名目差」與「戰鬥實際差」真的分叉
        (dict(heavy_armor=80, light_armor=5), 0),
        (dict(heavy_armor=5, light_armor=80), 0),
        (dict(heavy_armor=60, light_armor=60), 3),
    ]
    diverged = False
    for skills, temper in scenarios:
        c = _char()
        c.skills.update(skills)
        c.equipped = {"cuirass": "leather_cuirass", "helmet": "leather_helmet"}
        inventory.add_item(c, "iron_cuirass", 1)
        if temper:
            c.armor_temper["iron_cuirass"] = temper
        slot = gd.item("iron_cuirass")["slot"]
        equipped_before = dict(c.equipped)
        before = ui._armor_display(c, gd)
        predicted = ui._armor_after_equip(c, gd, slot, "iron_cuirass")
        assert c.equipped == equipped_before, "預覽不得改動角色本體"
        assert before == combat._armor_rating(c, gd), "『現值』= 戰鬥實際值(角色卡同源)"
        assert inventory.equip_armor(c, gd, "iron_cuirass")
        assert ui._armor_display(c, gd) == predicted == combat._armor_rating(c, gd), (skills, temper)   # 預覽 = 真穿後的實際值
        nominal = gd.item("iron_cuirass")["armor_rating"] - gd.item("leather_cuirass")["armor_rating"]
        diverged = diverged or (predicted - before) != nominal
    assert diverged, "夾具必須讓『名目護甲差』≠『戰鬥護甲差』(否則本測試證明不了名目尺度的誤導)"


def test_compare_panel_rows_carry_the_combat_armor_and_the_tempered_damage():
    from tesrpg.systems import inventory
    c = _char()
    c.skills.update(heavy_armor=80, light_armor=5)
    c.equipped = {"cuirass": "leather_cuirass"}
    inventory.add_item(c, "iron_cuirass", 1)
    before = ui._armor_display(c, gd)
    after = ui._armor_after_equip(c, gd, "cuirass", "iron_cuirass")
    with _capture_panels() as got:
        ui.item_compare_panel(c, gd, "iron_cuirass")
    rows = got[0][1]
    delta = after - before
    assert _kv(rows, "戰鬥護甲") == f"{before} → {after} " + ("(持平)" if delta == 0 else f"({delta:+d})"), _kv(rows, "戰鬥護甲")
    assert _kv(rows, "護甲") is not None, "名目『護甲』列保留(物品自身數值)"
    # 武器:手持鐵劍 +3 淬鍊 vs 未淬鍊的更高傷害武器 —— 名目傷害列說「換上更強」,含淬鍊後可能反而更弱
    low = "iron_sword"
    high = next(i for i, d in gd.weapons.items()
                if d["damage"] > gd.item(low)["damage"] and not inventory.is_two_handed(gd, i) and i != low)
    c.weapon = low
    c.weapon_temper[low] = 3
    inventory.add_item(c, high, 1)
    with _capture_panels() as got:
        ui.item_compare_panel(c, gd, high)
    rows = got[0][1]
    cur_eff = gd.item(low)["damage"] + __import__("tesrpg.systems.smithing", fromlist=["x"]).weapon_temper_bonus(c, gd)
    assert _kv(rows, "含淬鍊傷害").startswith(f"手持 {cur_eff} → 換上 {gd.item(high)['damage']} "), _kv(rows, "含淬鍊傷害")
    assert inventory.equip_weapon(c, gd, high)                          # 真換上後:戰鬥讀取鉤的實際加傷 = 預覽的「換上」值
    from tesrpg.systems import smithing
    assert gd.item(high)["damage"] + smithing.weapon_temper_bonus(c, gd) == int(_kv(rows, "含淬鍊傷害").split("換上 ")[1].split(" ")[0])
    c.weapon_temper.clear()
    inventory.add_item(c, low, 1)                                       # 真流程只會對背包內的物品出對比面板
    with _capture_panels() as got:                                      # 無任何淬鍊差異 → 不列「含淬鍊傷害」(免與名目傷害列重複)
        ui.item_compare_panel(c, gd, low)
    assert _kv(got[0][1], "含淬鍊傷害") is None


# --- B3 補強(R202 審查 F1 / F2)-----------------------------------------------
def _cuirass(material):
    return next(i for i, d in gd.armor.items() if d.get("slot") == "cuirass" and d.get("material") == material)


def test_armor_compare_follows_equipment_skill_bonus_swaps_like_the_real_equip_flow():
    """審查 F1(major):換上 / 卸下「強化重甲 +30」的附魔護甲,真流程在 equip 後會 recompute(equip_skill_bonus 跟著換),
    只換 equipped 的預覽會顯示持平。對帳要走與 `_item_actions` 同一串真流程(equip_armor + recompute_max_resources)。"""
    from tesrpg import synth
    from tesrpg.systems import combat, inventory
    iron, steel = _cuirass("iron"), _cuirass("steel")
    ench = synth.enchant_armor_id(iron, "skill", "heavy_armor", 30)
    for worn, target, must_differ in ((iron, ench, True), (ench, iron, True), (ench, steel, False)):
        c = _char()
        c.skills["heavy_armor"] = 50
        c.equipped = {"cuirass": worn}
        for iid in (worn, target):
            inventory.add_item(c, iid, 1)
        stats.recompute_max_resources(c, gd)                         # 現況:已穿的附魔護甲其技能加成已快取
        snapshot = copy.deepcopy(c.to_dict())
        before = ui._armor_display(c, gd)
        predicted = ui._armor_after_equip(c, gd, "cuirass", target)
        assert c.to_dict() == snapshot and ui._armor_display(c, gd) == before, "預覽不得動到本體(含 equip_* 快取)"
        assert inventory.equip_armor(c, gd, target)
        stats.recompute_max_resources(c, gd)                         # 真流程:穿上後必 recompute
        assert ui._armor_display(c, gd) == predicted == combat._armor_rating(c, gd), (worn, target, before, predicted)
        if must_differ:
            assert predicted != before, "夾具必須讓附魔的技能加成真的改變戰鬥護甲(否則證明不了 F1)"


def test_compare_rows_do_not_promise_numbers_when_the_real_equip_would_be_refused():
    """審查 F2:`equip_armor` / `equip_weapon` 會拒絕的情形(雙手武器 + 盾、獸形、吸血鬼專屬…),新列不得宣稱「戰鬥護甲 A → B」;
    阻擋判定抽成 `armor_equip_block` / `weapon_equip_block` 單一出處,真裝備與預覽共用。"""
    from tesrpg.systems import inventory
    two_hander = next(i for i, d in gd.weapons.items() if inventory.is_two_handed(gd, i))
    vamp_armor = next(i for i, d in gd.armor.items() if d.get("requires_vampire"))
    one_hander = next(i for i, d in gd.weapons.items() if not inventory.is_two_handed(gd, i) and i != "fists")

    def row(c, iid):
        with _capture_panels() as got:
            ui.item_compare_panel(c, gd, iid)
        return got[0][1]

    # ① 雙手武器在手 + 鐵盾
    c = _char()
    inventory.add_item(c, "iron_shield", 1)
    inventory.add_item(c, two_hander, 1)
    assert inventory.equip_weapon(c, gd, two_hander)
    assert inventory.armor_equip_block(c, gd, "iron_shield") == "雙手武器在手,裝不了盾"
    assert _kv(row(c, "iron_shield"), "戰鬥護甲") == "目前無法穿戴(雙手武器在手,裝不了盾)"
    assert inventory.equip_armor(c, gd, "iron_shield") is False
    # ② 獸形:穿脫皆拒
    c = _char()
    inventory.add_item(c, "iron_shield", 1)
    inventory.add_item(c, one_hander, 1)
    c.beast_form = True
    assert "獸形" in _kv(row(c, "iron_shield"), "戰鬥護甲") and "獸形" in _kv(row(c, one_hander), "含淬鍊傷害")
    assert inventory.equip_armor(c, gd, "iron_shield") is False and inventory.equip_weapon(c, gd, one_hander) is False
    # ③ 吸血鬼專屬護甲,非吸血鬼
    c = _char()
    inventory.add_item(c, vamp_armor, 1)
    assert _kv(row(c, vamp_armor), "戰鬥護甲") == "目前無法穿戴(吸血鬼專屬)"
    assert inventory.equip_armor(c, gd, vamp_armor) is False
    # ④ 一致性:可穿 ⟺ 無阻擋原因;可穿時新列才有數字
    c = _char()
    inventory.add_item(c, "iron_shield", 1)
    assert inventory.armor_equip_block(c, gd, "iron_shield") is None
    assert "→" in _kv(row(c, "iron_shield"), "戰鬥護甲")
    assert inventory.equip_armor(c, gd, "iron_shield") is True


# --- 搬出公式的黃金值(審查:預覽 == 實擲共用同一函式 → 函式內部漂移對「對帳型」測試天然隱形,另以文件化常數釘住)-------
def test_moved_formulas_keep_their_documented_constants():
    from tesrpg import formulas
    from tesrpg.systems import enchanting, progression
    # 行竊失手賞金 = max(20, 價值×2) × 順手牽羊 × 魅惑術
    items = [i for i in gd.items if gd.item(i).get("value")]
    dear, cheap = max(items, key=lambda i: gd.item(i)["value"]), min(items, key=lambda i: gd.item(i)["value"])
    c = _char()
    assert crime.steal_fine(c, gd, dear) == gd.item(dear)["value"] * 2
    assert crime.steal_fine(c, gd, cheap) == max(20, gd.item(cheap)["value"] * 2)
    with mock.patch.object(mastery, "theft_bonus", lambda ch, g: {"bounty_factor": 0.5}), \
            mock.patch.object(spellfx, "charm_bounty_factor", lambda ch: 0.7):
        assert crime.steal_fine(c, gd, dear) == int(round(gd.item(dear)["value"] * 2 * 0.5 * 0.7))
    # 原地休息:體力 = 最大 × 時數/8;生命 = 最大 × 時數/24;法力 = 最大 × 時數/12 × 意志續航(base-40 中性 ×1.0)
    c = _hurt(_char(class_id="mage"), 0.2)
    out = M.rest_outcome(c, gd, 4)
    assert abs(out["fatigue"] - (0.2 * c.max_fatigue + c.max_fatigue * 4 / 8)) < 1e-9
    assert abs(out["health"] - (0.2 * c.max_health + c.max_health * 4 / 24)) < 1e-9
    assert formulas.magicka_regen_rest_factor(40) == 1.0
    assert abs(out["magicka"] - (0.2 * c.max_magicka + c.max_magicka * 4 / 12)) < 1e-9
    # 附魔強度報價:四個領域都吃增效(非中性),唯荊棘不吃(R42:反傷% = 魂石階,使用者拍板「1 階 = 1%」)
    gem = _gems()[-1]
    soul = gd.item(gem)["soul"]
    for pot in (0.0, 0.5):
        with mock.patch.object(mastery, "enchant_potency", lambda ch, g, _p=pot: _p):
            c = _char()
            c.skills["mysticism"] = 60
            k = 1 + pot
            assert enchanting.quote_weapon_element(c, gd, gem) == round(enchanting.enchant_magnitude(soul, 60) * k)
            assert enchanting.quote_jewelry(c, gd, "skill", "sneak", gem) == round(enchanting.jewelry_magnitude("skill", soul, 60, "sneak") * k)
            assert enchanting.quote_armor(c, gd, "res", "health", gem) == round(enchanting.armor_magnitude("res", soul, 60) * k)
            assert enchanting.quote_armor(c, gd, "thorns", "", gem) == max(1, soul), "荊棘不吃增效"
            assert enchanting.quote_weapon_status(c, gd, "vampiric", gem) == enchanting.weapon_status_magnitude("vampiric", soul, 60, k)
    with mock.patch.object(mastery, "enchant_potency", lambda ch, g: 0.0):
        base = (enchanting.quote_weapon_element(c, gd, gem), enchanting.quote_jewelry(c, gd, "skill", "sneak", gem),
                enchanting.quote_armor(c, gd, "res", "health", gem), enchanting.quote_weapon_status(c, gd, "burn", gem))
    with mock.patch.object(mastery, "enchant_potency", lambda ch, g: 0.5):
        boosted = (enchanting.quote_weapon_element(c, gd, gem), enchanting.quote_jewelry(c, gd, "skill", "sneak", gem),
                   enchanting.quote_armor(c, gd, "res", "health", gem), enchanting.quote_weapon_status(c, gd, "burn", gem))
    assert all(b > a for a, b in zip((base[0], base[1], base[2], base[3][0]), (boosted[0], boosted[1], boosted[2], boosted[3][0]))), \
        "增效維度對四個領域都必須非中性"
    # 練習報價:體力恰等於成本 → 不算疲憊(< 而非 <=);少 1 → 疲憊且 xp 減半
    pdef = gd.skills["mysticism"]["practice"]
    c = _char()
    c.fatigue = pdef["fatigue"]
    assert progression.practice_quote(c, gd, "mysticism")[2] is False
    c.fatigue = pdef["fatigue"] - 1
    xp, hours, tired, fat = progression.practice_quote(c, gd, "mysticism")
    assert tired is True and xp == pdef["xp"] * 0.5 and hours == pdef["hours"] and fat == pdef["fatigue"]


# --- C 附魔強度與消耗 ----------------------------------------------------------
def _gems():
    gems = sorted((i for i in gd.items if gd.item(i).get("kind") == "soul_gem"), key=lambda i: gd.item(i)["soul"])
    assert len({gd.item(g)["soul"] for g in gems}) >= 3, "夾具要有多階魂石(強度隨魂石階變化)"
    return gems


def _first_item(kind, exclude_enchanted=True):
    return next(i for i in gd.items if gd.item(i).get("kind") == kind and not gd.item(i).get("enchant"))


def _enchant_char(base_id, gem_id, mysticism=60):
    from tesrpg.systems import inventory
    c = _char()
    c.inventory = []
    c.skills["mysticism"] = mysticism
    inventory.add_item(c, base_id, 1)
    inventory.add_item(c, gem_id, 1)
    return c


def test_enchant_preview_label_equals_the_name_of_the_really_enchanted_item():
    """四個領域 × 魂石階 × 神秘技能 × 附魔增效:預覽標籤 == 真實附魔後物品名稱括號內的字(`synth.*_label` 單一出處,
    強度取自與實擲同一個 `enchanting.quote_*`)。"""
    from tesrpg.systems import enchanting
    gems = _gems()
    weapon, armor, jewel = _first_item("weapon"), _first_item("armor"), _first_item("jewelry")
    cases = []                                              # (domain, 基底, kind, param, 真實附魔呼叫)
    for e in enchanting.ELEMENTS:
        cases.append(("weapon_element", weapon, e, "", lambda c, g, e=e: enchanting.enchant_weapon(c, gd, weapon, e, g)))
    for st in enchanting._WEAPON_STATUSES:
        cases.append(("weapon_status", weapon, st, "", lambda c, g, st=st: enchanting.enchant_weapon_status(c, gd, weapon, st, g)))
    for kind, params in (("res", ["health", "magicka", "fatigue"]), ("skill", ["blade", "block"]),
                         ("resist", ["fire", "magic", "physical"]), ("thorns", [""])):
        for p in params:
            cases.append(("armor", armor, kind, p, lambda c, g, k=kind, p=p: enchanting.enchant_armor(c, gd, armor, k, p, g)))
    for kind, params in (("skill", ["sneak"]), ("attr", ["strength"]), ("resist", ["frost", "magic"]), ("res", ["health"])):
        for p in params:
            cases.append(("jewelry", jewel, kind, p, lambda c, g, k=kind, p=p: enchanting.enchant_jewelry(c, gd, jewel, k, p, g)))
    labels = {}
    for pot in (0.0, 0.5):                                  # 附魔增效(里程碑 enchant_potency)維度必須非中性
        with mock.patch.object(mastery, "enchant_potency", lambda c, g, _p=pot: _p):
            for domain, base, kind, param, real in cases:
                for gem in (gems[0], gems[-1]):
                    for myst in (20, 100):
                        c = _enchant_char(base, gem, myst)
                        preview = enchanting.preview_label(c, gd, domain, kind, param, gem)
                        res = real(c, gem)
                        assert res["ok"], (domain, kind, param, res)
                        name = gd.item(res["item_id"])["name"]
                        assert name == f"{gd.item(base)['name']}（{preview})", (domain, kind, param, pot, myst, name, preview)
                        labels[(domain, kind, param, gem, myst, pot)] = preview
    for domain, base, kind, param, _ in cases:
        if kind == "thorns":                                # 荊棘 = 純魂石階%,不吃神秘 / 增效
            continue
        a = labels[(domain, kind, param, gems[0], 20, 0.0)]
        assert a != labels[(domain, kind, param, gems[-1], 20, 0.0)] or kind in ("vampiric", "paralyze", "soul_trap"), (domain, kind, param, "魂石階")
    assert labels[("armor", "res", "health", gems[-1], 20, 0.0)] != labels[("armor", "res", "health", gems[-1], 100, 0.0)], "神秘技能維度非中性"
    assert labels[("armor", "res", "health", gems[-1], 100, 0.0)] != labels[("armor", "res", "health", gems[-1], 100, 0.5)], "增效維度非中性"


def _drive_enchant(c, picks):
    """真走 action_enchant:假 ui.menu 依序回 picks(用盡 → 回 None 離開);回 [(標題, {key: label})]。"""
    from tesrpg.systems import inventory
    seen, it = [], iter(picks)

    def fake_menu(title, options, allow_back=False):
        seen.append((title, dict(options)))
        return next(it, None)

    with _quiet_ui(menu=fake_menu):
        M.action_enchant(_state(c), gd)
    return seen


def test_enchant_menus_show_the_result_label_and_cost_through_the_real_action():
    from tesrpg.systems import enchanting
    gem = _gems()[-1]
    weapon, armor, jewel = _first_item("weapon"), _first_item("armor"), _first_item("jewelry")
    # 武器元素:第 3 個選單(附魔效果?)標題帶消耗;第 4 個(附上哪種元素?)選項帶結果標籤;選完真的附魔
    c = _enchant_char(weapon, gem)
    fatigue0 = c.fatigue
    seen = _drive_enchant(c, [gem, weapon, "element", "frost"])
    assert enchanting.cost_text(_enchant_char(weapon, gem), gd, gem, weapon) in seen[2][0], seen[2][0]
    label = seen[3][1]["frost"]                                       # 選項標籤 = 結果標籤本身(如「冰霜附魔 +N」,不再重複元素名)
    made = [s["id"] for s in c.inventory if gd.item(s["id"]).get("enchant")]
    assert len(made) == 1 and gd.item(made[0])["name"].endswith(f"（{label})") and "→" not in label, (made, label)
    assert fatigue0 - c.fatigue == gd.skills["mysticism"]["practice"]["fatigue"], "消耗文字的『體力 −N』= 實際扣的體力"
    assert f"體力 −{gd.skills['mysticism']['practice']['fatigue']}" in seen[2][0]
    assert f"{gd.skills['mysticism']['practice']['hours']} 小時" in seen[2][0]
    # 武器狀態(DoT)與護甲 / 飾品參數選單:選項 = 結果標籤
    c = _enchant_char(weapon, gem)
    seen = _drive_enchant(c, [gem, weapon, "dot", "burn"])
    assert " → 焚燒(每回合 " in seen[3][1]["burn"]
    c = _enchant_char(armor, gem)
    seen = _drive_enchant(c, [gem, armor, "thorns"])
    assert "→ 荊棘 反傷 +" in seen[2][1]["thorns"] and enchanting.cost_text(c, gd, gem, armor) in seen[2][0]
    c = _enchant_char(jewel, gem)
    seen = _drive_enchant(c, [gem, jewel, "resist", "fire"])
    assert seen[3][1]["fire"].startswith("抗火焰 +") and seen[3][1]["magic"].startswith("抗魔法 +")
    assert [s["id"] for s in c.inventory if gd.item(s["id"]).get("enchant")], "選完真的附魔"
    # 體力不足 → 消耗文字提示 xp 減半,且與實擲 tired 一致
    c = _enchant_char(weapon, gem)
    c.fatigue = 0
    assert "體力不足:神秘練習 xp 減半" in enchanting.cost_text(c, gd, gem, weapon)
    assert enchanting.enchant_weapon(c, gd, weapon, "fire", gem)["tired"] is True


def test_practice_quote_is_pure_and_practice_cost_is_unchanged():
    from tesrpg.systems import progression
    c = _char()
    for fat in (0, 3, 1000):
        c.fatigue = fat
        snapshot = copy.deepcopy(c.__dict__)
        q = progression.practice_quote(c, gd, "mysticism")
        assert c.__dict__ == snapshot, "報價不得改任何狀態"
        c2 = copy.deepcopy(c)
        xp, hours, tired = progression.practice_cost(c2, gd, "mysticism")
        assert (xp, hours, tired) == q[:3] and c2.fatigue == max(0, c.fatigue - q[3])


# --- D 地城機關(陷阱 / 謎題 / 祭壇)---------------------------------------------
def _msgs(fn):
    """在靜音 console 內執行 fn,回傳它印出的文字。"""
    with _quiet_ui():
        fn()
        return ui.console.file.getvalue()


def test_trap_dodge_chance_is_single_source_and_the_messages_report_it():
    builds = [(40, 0, None), (80, 60, None), (30, 100, None), (35, 0, 0.8)]   # (敏捷, 安全, 「機關通曉」保底)
    seen = set()
    for agi, sec, floor in builds:
        for result in (True, False):
            c = _char()
            c.attributes["agility"], c.skills["security"] = agi, sec
            st = _state(c)
            st.rng = _ForceRNG(result=result)
            with contextlib.ExitStack() as stack:
                if floor is not None:
                    stack.enter_context(mock.patch.object(mastery, "trap_floor", lambda ch, g, _f=floor: _f))
                out = _msgs(lambda: M._resolve_trap(st, gd, {"damage": [3, 5]}))
                p = st.rng.ps[0]
                assert p == M._trap_dodge_chance(c, gd), (agi, sec, floor, p)          # 預覽 = 實擲擲骰引數
            assert f"閃避率 {ui.pct(p)}%" in out, (agi, sec, floor, out)
            assert ("及時閃避" in out) == result
            seen.add(round(p, 4))
    assert len(seen) >= 4 and 0.8 in seen, "敏捷 / 安全 / 保底三個維度都必須真的改變數字"
    # 念力術(R121):不擲骰、直接免傷 —— 預覽也要說免傷
    c = _char()
    st = _state(c)
    st.rng = _ForceRNG(result=False)
    with mock.patch.object(spellfx, "is_telekinetic", lambda ch: True):
        _msgs(lambda: M._resolve_trap(st, gd, {"damage": [3, 5]}))
        assert st.rng.ps == [] and "念力:免傷" in M._trap_step_hint(c, gd, {"damage": [3, 5]})


def _mini_grid(kind_at_east):
    """3×3 單層格圖:起點 (0,0) 的東鄰 (1,0) 放指定內容。"""
    n = 3
    cells = [[{"type": "empty"} for _ in range(n)] for _ in range(n)]
    cells[0][1] = kind_at_east
    return {"n": n, "layers": [cells]}


def test_dungeon_move_options_label_only_revealed_unresolved_traps():
    c = _char()
    c.attributes["agility"], c.skills["security"] = 60, 40
    trap = {"type": "trap", "trap": {"damage": [3, 5]}}

    def opts(grid, explored_east, resolved_east):
        explored = [[[False] * 3 for _ in range(3)]]
        resolved = [[[False] * 3 for _ in range(3)]]
        explored[0][0][1], resolved[0][0][1] = explored_east, resolved_east
        return dict(M._dungeon_move_options(c, gd, grid, 0, 0, 0, explored, resolved))

    base = opts(_mini_grid(trap), False, False)["go:e"]                   # 原方位標籤(含箭頭),未揭示時不加任何字
    assert base.startswith("往東") and "機關" not in base, "未揭示:不洩漏"
    pct = ui.pct(M._trap_dodge_chance(c, gd))
    assert opts(_mini_grid(trap), True, False)["go:e"] == f"{base}(^ 機關·閃避 {pct}%·失手 3–5 傷)", "已揭示未結算的陷阱:標閃避率與傷害"
    assert opts(_mini_grid(trap), True, True)["go:e"] == base, "已結算:不標"
    for other in ({"type": "feature", "feature": "puzzle_ward_lock"}, {"type": "monster", "enemies": ["wolf"]},
                  {"type": "container", "container": {}}):
        assert opts(_mini_grid(other), True, False)["go:e"] == base, "只有陷阱標;謎題 / 怪 / 寶箱不洩漏種類或機率"
    assert set(opts(_mini_grid(trap), True, False)) == {"go:e", "go:s"}, "選項集合與順序不變(只改標籤)"


def test_puzzle_chance_is_single_source_and_announced_before_the_roll():
    feat = gd.dungeon_features["puzzle_rusted_mechanism"]
    sid = feat["check"]
    seen = set()
    for agi, skill, diff in ((40, 0, 50), (60, 40, 50), (80, 80, 50), (100, 100, 0), (30, 0, 300)):
        for result in (True, False):
            c = _char()
            c.attributes[gd.skills[sid]["attr"]], c.skills[sid] = agi, skill
            st = _state(c)
            st.rng = _ForceRNG(result=result)
            f = dict(feat, difficulty=diff)
            out = _msgs(lambda: M._resolve_puzzle(st, gd, f))
            p = st.rng.ps[0]
            assert p == M._puzzle_chance(c, gd, f), (agi, skill, diff, p)
            assert f"成功率 {ui.pct(p)}%" in out and f"難度 {diff}" in out, out
            seen.add(round(p, 4))
    assert 0.05 in seen and 0.95 in seen and len(seen) >= 4, "夾限兩端與中間值都要覆蓋(技能 / 屬性 / 難度維度非中性)"


def test_shrine_offers_show_the_buff_and_the_real_price():
    from tesrpg.systems import potion_buff
    shrines = [(fid, f) for fid, f in gd.dungeon_features.items() if isinstance(f, dict) and f.get("kind") == "shrine"]
    assert len(shrines) >= 5
    clamped = False
    for fid, feat in shrines:
        for off in feat["offers"]:
            for base_skill in (5, 80):                       # 5:curse 夾限(只能扣到 0);80:不夾
                c = _char()
                for s in c.skills:
                    c.skills[s] = base_skill
                st = _state(c)
                captured = {}

                def fake_menu(title, options, allow_back=False, _k=off["key"]):
                    captured["opts"] = dict(options)
                    return _k

                hp0 = c.health
                with _quiet_ui(menu=fake_menu):
                    M._resolve_shrine(st, gd, feat)
                label = captured["opts"][off["key"]]
                b = off["buff"]
                assert f"得 {potion_buff.buff_label(b['kind'], b['param'], b['magnitude'], gd)}·{b['hours']} 小時" in label, (fid, label)
                risk = off.get("risk")
                if risk and risk["type"] == "damage":
                    lo, hi = risk["amount"]
                    assert f"代價 損血 {lo}–{hi}" in label and lo <= hp0 - c.health <= hi, (fid, label, hp0 - c.health)
                elif risk and risk["type"] == "curse":
                    pen = -c._dungeon_curse[risk["skill"]]                               # 真實扣掉的量
                    assert f"代價 【{gd.skills[risk['skill']]['name']}】−{pen} 直到離開地城" in label, (fid, label, pen)
                    clamped = clamped or (pen < risk.get("magnitude", 20))
    assert clamped, "夾具必須涵蓋 curse 被技能底值夾住的情形(−5 而非 −20)"


# --- E 資料文字內嵌數字的一致性守衛(R200「未動 / 後續」清單)-----------------------------
def test_codex_numbers_follow_the_constants_they_describe():
    """codex.json 的說明文字內嵌了常數的值,資料文字無法引用常數 → 由本測試看守(改常數會逼你同步改文字)。"""
    from tesrpg import formulas
    codex = (ROOT / "tesrpg" / "data" / "codex.json").read_text(encoding="utf-8")
    g = lambda x: re.escape(f"{x:g}")                                    # 0.7 → "0.7"、2 → "2"
    checks = {
        "重盾 / 一般盾元素卸力係數": rf"係數 {g(formulas.GREAT_SHIELD_ELEMENTAL_FACTOR)}[,,]\s*一般盾 {g(formulas.GUARD_STANCE_ELEMENTAL_FACTOR)}",
        "重盾掩體回氣": rf"\+{g(formulas.GREAT_SHIELD_BUNKER_FATIGUE)} 體力",
        "銷贓加價上限": rf"上限 \+{round(crime.FENCE_BONUS_BY_TIER[-1] * 100)}%",
    }
    for what, pattern in checks.items():
        assert re.search(pattern, codex), f"codex.json 內嵌的『{what}』與常數不一致(應符合 {pattern});改常數請同步改 codex 文字"


def test_major_skill_xp_multiplier_mentions_follow_the_constant():
    from tesrpg import formulas
    needle = f"主修 ×{formulas.MAJOR_SKILL_XP_MULT:g}"
    for rel in ("DESIGN.md", "tesrpg/systems/progression.py"):
        assert needle in (ROOT / rel).read_text(encoding="utf-8"), f"{rel} 的『主修經驗倍率』與 formulas.MAJOR_SKILL_XP_MULT 不一致(應含 {needle!r})"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r202_visibility")
