"""經濟 QoL 批次(R114C·UI/UX 審計 包C)回歸測試。

涵蓋:賣貨預設全部 + 高價單件確認、倉庫全部存入/取出、旅店直達過夜、煉金再煉一鍋、
訓練師連買、練習再練上次(session 捷徑)、丟棄/回爐高價確認閘。
純互動流(零平衡/零存檔),以 patched ui 驅動。
"""

import io
import json

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import housing, inventory, world
import tesrpg.ui.console as ui
import tesrpg.main as M


def _cs():
    gd = get_gamedata()
    c = build_character(gd, name="賈", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    return gd, c, GameState(player=c, time=GameTime(), rng=RNG(1))


def _patch(menu_seq=None, confirm=True, ask_int_returns_default=True):
    """patch ui.menu(序列)/confirm/ask_int/message/show_events;回 (restore, seen_menu_titles)。"""
    saved = (ui.menu, ui.confirm, ui.ask_int, ui.message, ui.show_events, ui.inventory_panel,
             ui.shop_panel)
    seq = iter(menu_seq or [])
    seen = []

    def _menu(title, options, allow_back=False):
        seen.append((title, [o[0] for o in options]))
        return next(seq, None)
    ui.menu = _menu
    ui.confirm = (lambda *a, **k: confirm) if not callable(confirm) else confirm
    ui.ask_int = (lambda prompt, default, lo, hi: default) if ask_int_returns_default \
        else (lambda prompt, default, lo, hi: lo)
    ui.message = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None
    ui.inventory_panel = lambda *a, **k: None
    ui.shop_panel = lambda *a, **k: None

    def restore():
        (ui.menu, ui.confirm, ui.ask_int, ui.message, ui.show_events, ui.inventory_panel,
         ui.shop_panel) = saved
    return restore, seen


# --- 賣貨預設全部 + 高價單件確認 -----------------------------------------
def test_sell_defaults_to_all():
    gd, c, st = _cs()
    c.location_id = "whiterun"
    world.ensure_stock(c, gd, "whiterun", st.time, st.rng)
    inventory.add_item(c, "iron_dagger", 5)                # 低價雜貨堆
    gold0 = c.gold
    restore, _ = _patch(menu_seq=["sell", "iron_dagger", None, None], ask_int_returns_default=True)
    try:
        M.action_shop(st, gd)                              # ask_int 回 default(=owned)→ 全賣
    finally:
        restore()
    assert inventory.count_item(c, "iron_dagger") == 0     # 預設全部售出
    assert c.gold > gold0


def test_sell_single_high_value_confirm_declined_keeps_item():
    gd, c, st = _cs()
    c.location_id = "whiterun"
    world.ensure_stock(c, gd, "whiterun", st.time, st.rng)
    # 找一件 value≥門檻的單品(精品武器)
    hv = next(iid for iid in gd.items
              if gd.items[iid].get("value", 0) >= M.SELL_CONFIRM_VALUE and gd.items[iid].get("kind") == "weapon")
    inventory.add_item(c, hv, 1)
    restore, _ = _patch(menu_seq=["sell", hv, None, None], confirm=False)   # 拒絕確認
    try:
        M.action_shop(st, gd)
    finally:
        restore()
    assert inventory.count_item(c, hv) == 1                # 拒絕 → 精品仍在


# --- 倉庫全部存入/取出 ---------------------------------------------------
def test_stash_deposit_all():
    gd, c, st = _cs()
    c.location_id = "bruma"
    housing.buy(c, gd, "bruma")
    inventory.add_item(c, "iron_dagger", 3)
    inventory.add_item(c, "bone_meal", 2)
    restore, _ = _patch(menu_seq=["__all__", None])
    try:
        M._stash_transfer(st, gd, "bruma", deposit=True)
    finally:
        restore()
    assert inventory.count_item(c, "iron_dagger") == 0 and inventory.count_item(c, "bone_meal") == 0
    assert housing.stash_count(c, "bruma", "iron_dagger") == 3
    # 全部取出(以負重為閘;此處輕物 → 全回)
    restore, _ = _patch(menu_seq=["__all__", None])
    try:
        M._stash_transfer(st, gd, "bruma", deposit=False)
    finally:
        restore()
    assert inventory.count_item(c, "iron_dagger") == 3


# --- 旅店直達過夜 ---------------------------------------------------------
def test_inn_rest_direct():
    gd, c, st = _cs()
    c.gold = 100; c.health = 1; c.magicka = 0; c.fatigue = 0
    t0 = st.time.absolute_hours()
    restore, _ = _patch()
    try:
        M._inn_rest(st, gd)
    finally:
        restore()
    assert c.gold == 90 and c.health == c.max_health
    assert st.time.absolute_hours() == t0 + 8
    # 錢不夠 → 不回復不扣款
    c.gold = 5; c.health = 1
    restore, _ = _patch()
    try:
        M._inn_rest(st, gd)
    finally:
        restore()
    assert c.gold == 5 and c.health == 1


# --- 煉金再煉一鍋 ---------------------------------------------------------
def _mark_all_known(c, gd, iid):
    c.known_effects.setdefault(iid, [])
    for e in gd.items[iid].get("effects", []):
        if e["kind"] not in c.known_effects[iid]:
            c.known_effects[iid].append(e["kind"])


def test_alchemy_repeat_brew():
    gd, c, st = _cs()
    c.inventory = [s for s in c.inventory if gd.items[s["id"]].get("kind") != "ingredient"]   # 清起始材料(免 taste 模式選單)
    a, b = "garlic", "bone_meal"
    for iid in (a, b):
        inventory.add_item(c, iid, 3)
        _mark_all_known(c, gd, iid)                        # 全效果已知 → 無 taste 分支、無模式選單
    # 選 a、選 b、(再煉迴圈)、外層再問首材料 → None 離開
    confirms = iter([True, True, False])
    restore, _ = _patch(menu_seq=[a, b, None], confirm=lambda *x, **k: next(confirms, False))
    try:
        M.action_alchemy(st, gd)
    finally:
        restore()
    # 初鍋 + 連煉直到材料耗盡(每鍋各耗 a、b 一份;3 份 → 3 鍋 → 皆歸 0)
    assert inventory.count_item(c, a) == 0 and inventory.count_item(c, b) == 0


# --- 訓練師連買 -----------------------------------------------------------
def test_trainer_repeat_buy():
    gd, c, st = _cs()
    loc = next(lid for lid in gd.world["locations"]
               if "trainer" in gd.world["locations"][lid].get("services", []))
    c.location_id = loc
    c.gold = 100000
    spec = world.trainer_specs(gd, loc)[0]
    sid = world.trainer_skills(gd, loc, spec)[0]
    c.skills[sid] = 10
    lvl0 = c.skill(sid)
    # 單系城:menu 回 sid;多系城:先回 spec 再 sid。confirm 連買 3 次後停。
    confirms = iter([True, True, True, False])
    seq = ([sid] if len(world.trainer_specs(gd, loc)) == 1 else [spec, sid]) + [None]
    restore, _ = _patch(menu_seq=seq, confirm=lambda *x, **k: next(confirms, False))
    try:
        M.action_trainer(st, gd)
    finally:
        restore()
    assert c.skill(sid) >= lvl0 + 2                        # 初訓 +1 + 連買數次


# --- 練習再練上次(session 捷徑)----------------------------------------
def test_practice_remembers_last_skill():
    gd, c, st = _cs()
    saved_last = M._last_practice_skill
    M._last_practice_skill = None
    try:
        # 第一次:類別→技能→時數(1 小時);記住 blade
        restore, seen = _patch(menu_seq=["combat", "blade"], ask_int_returns_default=False)
        try:
            M.action_practice(st, gd)
        finally:
            restore()
        assert M._last_practice_skill == "blade"
        # 第二次:應先出「再練上次」捷徑選單
        restore, seen = _patch(menu_seq=["__last__"], ask_int_returns_default=False)
        try:
            M.action_practice(st, gd)
        finally:
            restore()
        assert any("要練什麼?" == t for t, _ in seen)      # 出現一鍵捷徑選單
        assert any("__last__" in keys for _, keys in seen)
    finally:
        M._last_practice_skill = saved_last                # 還原 module global(即使斷言失敗也不污染他測)


def test_sell_high_value_stack_defaults_to_one():
    """審查 NIT:高價品堆疊預設賣 1(防 Enter 誤傾銷精品堆);雜貨仍預設全部。"""
    gd, c, st = _cs()
    c.location_id = "whiterun"
    world.ensure_stock(c, gd, "whiterun", st.time, st.rng)
    hv = next(iid for iid in gd.items
              if gd.items[iid].get("value", 0) >= M.SELL_CONFIRM_VALUE and gd.items[iid].get("kind") == "ingredient")
    inventory.add_item(c, hv, 3)
    seen_defaults = []
    saved = (ui.menu, ui.ask_int, ui.message, ui.inventory_panel)
    seq = iter(["sell", hv, None, None])
    ui.menu = lambda title, options, allow_back=False: next(seq, None)
    ui.ask_int = lambda prompt, default, lo, hi: (seen_defaults.append(default) or 1)   # 賣 1
    ui.message = ui.inventory_panel = lambda *a, **k: None
    try:
        M.action_shop(st, gd)
    finally:
        (ui.menu, ui.ask_int, ui.message, ui.inventory_panel) = saved
    assert seen_defaults and seen_defaults[0] == 1         # 高價堆疊 → 預設 1(非 3)
    assert inventory.count_item(c, hv) == 2


# --- 丟棄高價確認閘 -------------------------------------------------------
def test_drop_high_value_confirm_declined_keeps_item():
    gd, c, st = _cs()
    hv = next(iid for iid in gd.items
              if gd.items[iid].get("value", 0) >= M.DESTROY_CONFIRM_VALUE and gd.items[iid].get("kind") == "weapon")
    inventory.add_item(c, hv, 1)
    restore, _ = _patch(menu_seq=["drop"], confirm=False)   # 動作選單選丟棄 → 確認時拒絕
    try:
        M._item_actions(st, gd, hv)
    finally:
        restore()
    assert inventory.count_item(c, hv) == 1                 # 拒絕 → 高價品仍在
    # 同意 → 丟棄
    restore, _ = _patch(menu_seq=["drop"], confirm=True)
    try:
        M._item_actions(st, gd, hv)
    finally:
        restore()
    assert inventory.count_item(c, hv) == 0


def test_drop_low_value_no_confirm_needed():
    gd, c, st = _cs()
    lv = next(iid for iid in gd.items
              if 0 < gd.items[iid].get("value", 0) < M.DESTROY_CONFIRM_VALUE and gd.items[iid].get("kind") == "weapon")
    inventory.add_item(c, lv, 1)
    # confirm 若被呼叫就爆(RuntimeError)→ 低價品不該彈確認
    def _boom(*a, **k):
        raise AssertionError("低價品丟棄不應彈確認")
    restore, _ = _patch(menu_seq=["drop"], confirm=_boom)
    try:
        M._item_actions(st, gd, lv)
    finally:
        restore()
    assert inventory.count_item(c, lv) == 0


# --- 城區停留連逛(結構改動:_stay_district)------------------------------
class _Stop(Exception):
    pass


def test_district_stay_reenters_without_hub():
    """🔴 城區服務辦完 → 下圈直接回該區子選單(免回 hub);驗證不 trap、grouped_menu 不被重呼。"""
    gd, c, st = _cs()
    c.location_id = "whiterun"; c.gold = 500
    grouped_calls = [0]
    plaza_calls = [0]
    saved = (ui.grouped_menu, ui.menu, ui.confirm, ui.message, ui.rule, ui.status_line,
             ui.location_panel, ui.show_events)
    ui.message = ui.rule = ui.status_line = ui.location_panel = ui.show_events = lambda *a, **k: None

    def _grouped(title, groups, **k):
        grouped_calls[0] += 1
        if grouped_calls[0] == 1:
            return "_plaza"                               # 首圈:進廣場
        raise _Stop()                                     # 第二次被呼叫=stay 失敗(或收尾)→ 停

    def _menu(title, options, allow_back=False):
        keys = [o[0] for o in options]
        if "inn_rest" in keys:                            # 廣場子選單
            plaza_calls[0] += 1
            return "inn_rest" if plaza_calls[0] == 1 else None   # 首入=過夜;再入(stay)=返回→回 hub
        return None
    ui.grouped_menu = _grouped
    ui.menu = _menu
    ui.confirm = lambda *a, **k: True
    reached = {}
    _saved_onset = M._onset_hinted   # game_loop 直呼會 arm _onset_hinted;還原免洩漏到後續模組(R155)
    try:
        M.game_loop(st, gd)
    except _Stop:
        reached["stop"] = True
    finally:
        (ui.grouped_menu, ui.menu, ui.confirm, ui.message, ui.rule, ui.status_line,
         ui.location_panel, ui.show_events) = saved
        M._onset_hinted = _saved_onset
    # 廣場子選單被進入兩次(首次過夜 + stay 再入才返回),而 grouped_menu 於這兩圈間「不」被重呼
    assert plaza_calls[0] == 2, f"stay 應讓廣場子選單再入一次(實際 {plaza_calls[0]})"
    assert reached.get("stop"), "返回後應回 hub(grouped_menu 再被呼叫→_Stop)"
    assert c.gold == 490                                  # 只過夜一次(stay 再入是返回,不重複過夜)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_econ_qol 全通過")
