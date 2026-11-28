"""R226 抓捕與封店:行竊失手 → 衛兵趕到;賞金 ≥ 300 → 一般商店拒絕服務;廣場「向衛兵自首」就地清賞金。

守衛(對應 R226 使用者拍板的五項):
  A 單一決策點
    1 門檻 = 路途獵殺 tier 2(沿用 ACTIVE_HEAT_THRESHOLDS[1],不新增常數)·高於說退上限與武士放行線;shop_refuses 恰在門檻成立、各省獨立
  B 商店流程(真 action_shop,腳本化 ui)
    2 通緝中進店 = 不開選單、只有拒絕訊息;299 照常進、別省賞金不影響
    3 行竊失手(可見)→ 衛兵盤查 → 入獄 / 繳罰金:賞金清零、背包贓物沒收、這次進店到此為止
    4 說退成功不沒收仍離店;反抗(打贏:賞金 +40 贓物保住 / 死:action_shop 回 "dead")
    5 隱形者:衛兵撲空(不開盤查選單),賞金照加;未達線繼續逛、達線被轟出(隱形擋得住衛兵、擋不住封店)
    6 武士放行(小額賞金一筆勾銷)→ 不被帶離,繼續逛
    7 行竊得手:沒有盤查、照舊繼續
  C 自首動作
    8 無案底 → 提示不開選單;有案底 → 繳金 / 入獄 / 轉身離開(賞金 >120 無說退;沒有反抗);隱形不跳過;城門盤查(gate)逐字同舊
  D 選單接線(真 game_loop)
    9 市集區商店標籤(通緝中標「拒絕服務」)·廣場「自首」只在有賞金時出現且接到 action_surrender
  E 突變下會紅(門檻失效 / 不叫衛兵 / 不被帶離 / 隱形判定壞掉 / 自首被隱形跳過 …)
"""
import io
import json
import pathlib

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.models.character import Character
from tesrpg.systems import brotherhood, court, crime, dialogue, inventory, legacy, spellfx, world

gd = get_gamedata()
LOC = "whiterun"
INVIS = {"kind": "invisibility", "magnitude": 1.0, "expires_at": 10 ** 9}


def _state(bounty=0, gold=500, invisible=False, thane=False, loot=0):
    c = build_character(gd, name="賊", sex="male", race="imperial", birthsign="shadow", class_id="thief")
    c.location_id, c.gold = LOC, gold
    st = GameState(player=c, time=GameTime(), rng=RNG(3))
    prov = crime.province_of(c, gd)
    if bounty:
        c.bounties[prov] = bounty
    if invisible:
        c.spell_effects = [dict(INVIS)]
        assert spellfx.is_invisible(c)
    if thane:
        c.thaneships = [LOC]
        assert court.is_thane_in_province(c, gd, prov)
    if loot:
        inventory.add_item(c, "ruby", loot)
        inventory.mark_stolen(c, "ruby", loot)
    return st, c, prov


class _UI:
    """腳本化 ui:picks 依序回答 ui.menu;其餘一律記錄。menu 沒有可答的 → 回 None(= 返回)。"""

    def __init__(self, picks):
        self.picks, self.menus, self.msgs = list(picks), [], []

    def menu(self, title, options, allow_back=False, **kw):
        self.menus.append((title, [o[0] for o in options], {o[0]: o[1] for o in options}))
        assert len(self.menus) <= 60, "選單被反覆開啟 60 次以上 = 流程空轉(盤查迴圈遇到空選單不得空轉)"
        return self.picks.pop(0) if self.picks else None

    def titles(self):
        return [t for t, _k, _l in self.menus]

    def said(self, needle):
        return any(needle in m for m in self.msgs)


def _run(fn, picks, *a, patches=None, **kw):
    """以腳本化 ui 跑 fn(state, gd);patches = {(物件, 屬性): 值} 暫時替換(結束一律還原)。"""
    script = _UI(picks)
    saved = [(ui, n, getattr(ui, n)) for n in ("menu", "confirm", "ask_int", "message", "show_events", "shop_panel",
                                               "inventory_panel")]
    ui.menu, ui.confirm, ui.ask_int = script.menu, (lambda *x, **k: True), (lambda p, d, lo, hi, **k: d)
    ui.message = lambda text, **k: script.msgs.append(text)
    ui.show_events = ui.shop_panel = ui.inventory_panel = lambda *x, **k: None
    swaps = [(o, n, getattr(o, n), v) for (o, n), v in (patches or {}).items()]
    for o, n, _old, v in swaps:
        setattr(o, n, v)
    try:
        ret = fn(*a, **kw)
    finally:
        for o, n, old, _v in swaps:
            setattr(o, n, old)
        for o, n, old in saved:
            setattr(o, n, old)
    return ret, script


def _kills_all(state, gamedata, guards, *a, **k):
    """假的 run_battle:把傳入的衛兵全部打死(health = 0),回 victory —— 殺官重罪只看「打死的」。"""
    for g in guards:
        g.health = 0
    return "victory"


def _always_fail():
    return {(crime, "steal_chance"): lambda *a, **k: 0.0}


def _always_succeed():
    return {(crime, "steal_chance"): lambda *a, **k: 1.0}


def _cheap_item(st, c, limit=100):
    world.ensure_stock(c, gd, LOC, st.time, st.rng)
    return next(i for i in world.in_stock_items(c, gd, LOC) if crime.steal_fine(c, gd, i) <= limit)


def _pricey_item(st, c, floor=250):
    """投資到階 2 才有的高價貨(罰金大)。"""
    c.shop_invest[LOC] = 2
    c.shop_restock_at.pop(LOC, None)
    world.ensure_stock(c, gd, LOC, st.time, st.rng)
    return max(world.in_stock_items(c, gd, LOC), key=lambda i: crime.steal_fine(c, gd, i))


def _steal(iid):
    return f"{M._STEAL_KEY}{iid}"


# --- A 單一決策點 -----------------------------------------------------------------
def test_threshold_is_the_hunter_tier_two_line_and_above_the_small_bounty_outs():
    assert crime.SHOP_REFUSE_BOUNTY == crime.ACTIVE_HEAT_THRESHOLDS[1] == 300
    assert crime.SHOP_REFUSE_BOUNTY > dialogue.TALK_DOWN_MAX and crime.SHOP_REFUSE_BOUNTY > court.THANE_BOUNTY_FORGIVE
    st, c, prov = _state()
    other = next(p for p in gd.world.get("provinces", {}) if p != prov) if isinstance(gd.world.get("provinces"), dict) else "elsewhere"
    for b, want in ((0, False), (299, False), (300, True), (301, True), (9999, True)):
        c.bounties[prov] = b
        assert crime.shop_refuses(c, prov) is want, b
        assert crime.shop_refuses(c, other) is False                       # 各省獨立
    c.bounties[prov] = 300
    crime.clear_bounty(c, prov)
    assert crime.shop_refuses(c, prov) is False


# --- B 商店流程 --------------------------------------------------------------------
def test_wanted_player_is_refused_at_the_shop_door_but_299_and_other_provinces_are_fine():
    st, c, prov = _state(bounty=300)                                         # 寫死 300 / 299:突變會改常數,測試不能跟著動
    ret, script = _run(M.action_shop, ["buy"], st, gd)
    assert ret is None and not script.menus, script.titles()                 # 連選單都沒開
    assert script.said("不做你的生意") and script.said("300"), script.msgs
    st, c, prov = _state(bounty=299)
    ret, script = _run(M.action_shop, [None], st, gd)
    assert script.menus and script.titles()[0].startswith("商店(") and not script.said("不做你的生意")
    st, c, prov = _state()
    c.bounties["__not_this_province__"] = 99999
    ret, script = _run(M.action_shop, [None], st, gd)
    assert script.menus and script.titles()[0].startswith("商店(")


def test_visible_failed_theft_brings_guards_jail_clears_and_confiscates_and_ends_the_visit():
    st, c, prov = _state(loot=2)
    iid = _cheap_item(st, c)
    fine = crime.steal_fine(c, gd, iid)
    t0 = st.time.absolute_hours()
    ret, script = _run(M.action_shop, ["steal", _steal(iid), "jail"], st, gd, patches=_always_fail())
    assert ret is None
    assert script.titles()[1].startswith("行竊哪件") and script.titles()[2] == "如何應對?", script.titles()
    assert len(script.menus) == 3, script.titles()                           # 被帶離:沒有第 4 個(商店主選單)
    assert crime.bounty(c, prov) == 0 and inventory.count_item(c, "ruby") == 0   # 入獄:賞金清零 + 贓物沒收
    assert script.said("衛兵聞聲趕到") and script.said("沒收了贓物")
    assert st.time.absolute_hours() - t0 >= 1 + crime.jail_hours(fine)       # 下手 1 小時 + 刑期
    assert "resist" in script.menus[2][1] and "leave" not in script.menus[2][1]   # 當場被抓:有反抗、沒有「轉身離開」


def test_failed_theft_pay_the_fine_and_talk_down_paths():
    st, c, prov = _state(loot=1)
    iid = _cheap_item(st, c)
    fine = crime.steal_fine(c, gd, iid)
    gold0 = c.gold
    ret, script = _run(M.action_shop, ["steal", _steal(iid), "pay"], st, gd, patches=_always_fail())
    assert c.gold == gold0 - fine and crime.bounty(c, prov) == 0 and inventory.count_item(c, "ruby") == 0
    assert len(script.menus) == 3
    # 說退成功:賞金清零,贓物沒收不發生(沒被捕),但仍離開商店
    st, c, prov = _state(loot=1)
    iid = _cheap_item(st, c)
    patches = dict(_always_fail())
    patches[(dialogue, "talk_down_chance")] = lambda *a, **k: 1.0
    ret, script = _run(M.action_shop, ["steal", _steal(iid), "talk"], st, gd, patches=patches)
    assert crime.bounty(c, prov) == 0 and inventory.count_item(c, "ruby") == 1
    assert len(script.menus) == 3 and "talk" in script.menus[2][1]


def test_resisting_the_guards_in_the_shop_keeps_the_loot_and_bounty_and_death_propagates():
    st, c, prov = _state(loot=1)
    iid = _cheap_item(st, c)
    fine = crime.steal_fine(c, gd, iid)
    patches = dict(_always_fail())
    patches[(M, "run_battle")] = _kills_all
    ret, script = _run(M.action_shop, ["steal", _steal(iid), "resist"], st, gd, patches=patches)
    assert ret is None and len(script.menus) == 3
    n = 1 + min(2, fine // 80)                                               # 衛兵數(賞金越高越多)
    assert crime.bounty(c, prov) == fine + 40 + n * 700 and inventory.count_item(c, "ruby") == 1   # 反抗贏:+40 拒捕 + 每名 700 殺官、贓物不沒收、仍被帶離
    st, c, prov = _state()
    iid = _cheap_item(st, c)
    patches[(M, "run_battle")] = lambda *a, **k: "dead"
    ret, script = _run(M.action_shop, ["steal", _steal(iid), "resist"], st, gd, patches=patches)
    assert ret == "dead"


def test_invisible_thief_gets_no_guards_but_the_bounty_line_still_throws_them_out():
    st, c, prov = _state(invisible=True)
    iid = _cheap_item(st, c)
    fine = crime.steal_fine(c, gd, iid)
    ret, script = _run(M.action_shop, ["steal", _steal(iid), None], st, gd, patches=_always_fail())
    assert "如何應對?" not in script.titles(), script.titles()               # 衛兵撲空:不開盤查
    assert script.said("撲了個空") and crime.bounty(c, prov) == fine         # 但賞金照加
    assert script.titles()[-1].startswith("商店(")                           # 未達線:繼續逛(回到商店主選單)
    # 賞金差一點到線 → 這一次失手越線 → 被轟出
    st, c, prov = _state(invisible=True, bounty=crime.SHOP_REFUSE_BOUNTY - 5)
    iid = _cheap_item(st, c, limit=400)
    ret, script = _run(M.action_shop, ["steal", _steal(iid), None], st, gd, patches=_always_fail())
    assert "如何應對?" not in script.titles() and script.said("不做你的生意"), script.msgs
    assert len(script.menus) == 2 and crime.shop_refuses(c, prov)            # 行竊選單後就結束,沒有回商店主選單


def test_a_big_fine_alone_crosses_the_line_for_a_visible_thief_too():
    st, c, prov = _state(bounty=crime.SHOP_REFUSE_BOUNTY - 5)
    iid = _cheap_item(st, c, limit=400)
    ret, script = _run(M.action_shop, ["steal", _steal(iid), "resist"], st, gd,
                       patches={**_always_fail(), (M, "run_battle"): lambda *a, **k: "victory"})
    assert crime.shop_refuses(c, prov)                                       # 反抗贏了賞金仍在線上 → 下次進店照樣被擋
    ret, script = _run(M.action_shop, ["buy"], st, gd)
    assert not script.menus and script.said("不做你的生意")


def test_thane_forgiveness_keeps_the_visit_going():
    st, c, prov = _state(thane=True)
    iid = _cheap_item(st, c, limit=100)
    ret, script = _run(M.action_shop, ["steal", _steal(iid), None], st, gd, patches=_always_fail())
    assert "如何應對?" not in script.titles() and script.said("武士閣下"), script.titles()
    assert crime.bounty(c, prov) == 0                                        # 一筆勾銷
    assert script.titles()[-1].startswith("商店(") and len(script.menus) == 3   # 沒被帶離:回商店主選單


def test_a_successful_theft_is_unchanged():
    st, c, prov = _state()
    iid = _cheap_item(st, c)
    ret, script = _run(M.action_shop, ["steal", _steal(iid), None], st, gd, patches=_always_succeed())
    assert "如何應對?" not in script.titles() and crime.bounty(c, prov) == 0
    assert inventory.stolen_on_person(c, iid) == 1 and script.titles()[-1].startswith("商店(")


# --- C 自首 ------------------------------------------------------------------------
def test_surrender_action_options_and_outcomes():
    st, c, prov = _state()
    ret, script = _run(M.action_surrender, [], st, gd)
    assert ret is None and not script.menus and script.said("沒有案底")
    st, c, prov = _state(bounty=150, loot=1)                                 # >120:沒有說退
    ret, script = _run(M.action_surrender, ["pay"], st, gd)
    keys = script.menus[0][1]
    assert keys == ["pay", "jail", "leave"], keys                            # 沒有反抗
    assert crime.bounty(c, prov) == 0 and c.gold == 500 - 150 and inventory.count_item(c, "ruby") == 0
    st, c, prov = _state(bounty=150, loot=1)
    ret, script = _run(M.action_surrender, ["leave"], st, gd)
    assert ret is None and crime.bounty(c, prov) == 150 and inventory.count_item(c, "ruby") == 1   # 反悔:一切不變
    st, c, prov = _state(bounty=60)                                          # ≤120:可說退
    ret, script = _run(M.action_surrender, ["jail"], st, gd)
    assert script.menus[0][1][0] == "talk" and crime.bounty(c, prov) == 0 and st.time.absolute_hours() >= crime.jail_hours(60)


def test_surrender_is_not_skipped_by_invisibility_but_the_city_gate_still_is():
    st, c, prov = _state(bounty=50, invisible=True)
    ret, script = _run(M.action_surrender, ["pay"], st, gd)
    assert script.menus and crime.bounty(c, prov) == 0                       # 自己走去自首:看得見你
    st, c, prov = _state(bounty=50, invisible=True)
    ret, script = _run(M.guard_confrontation, [], st, gd)
    assert ret is None and not script.menus and crime.bounty(c, prov) == 50  # 城門:隱形溜過(R104 逐字同舊)
    st, c, prov = _state(bounty=50)
    ret, script = _run(M.guard_confrontation, ["pay"], st, gd)
    keys = script.menus[0][1]
    assert "resist" in keys and "leave" not in keys and ret == "confronted"  # 城門:有反抗、沒有轉身離開(同舊)


# --- D 選單接線(真 game_loop)--------------------------------------------------------
class _Stop(Exception):
    pass


def _hub_options(bounty, district, pick=None):
    """跑一圈真 game_loop:首圈進 district,記錄該區子選單的 (keys, labels);pick = 在子選單選的 key。"""
    st, c, prov = _state(bounty=bounty)
    seen = {}
    saved = (ui.grouped_menu, ui.menu, ui.confirm, ui.message, ui.rule, ui.status_line, ui.location_panel, ui.show_events)
    ui.message = ui.rule = ui.status_line = ui.location_panel = ui.show_events = lambda *a, **k: None
    n, answered = [0], [0]

    def _grouped(title, groups, **k):
        n[0] += 1
        if n[0] == 1:
            return district
        raise _Stop()

    def _menu(title, options, allow_back=False, **k):
        keys = [o[0] for o in options]
        if "shop" in keys or "surrender" in keys or "inn_rest" in keys:
            seen["keys"], seen["labels"] = keys, {o[0]: o[1] for o in options}
            answered[0] += 1
            return pick if answered[0] == 1 else None      # 只答第一次:辦完事會「停留該城區」再入子選單,不能每次都答(否則空轉)
        return None
    ui.grouped_menu, ui.menu, ui.confirm = _grouped, _menu, (lambda *a, **k: True)
    onset = M._onset_hinted
    try:
        M.game_loop(st, gd)
    except _Stop:
        pass
    finally:
        (ui.grouped_menu, ui.menu, ui.confirm, ui.message, ui.rule, ui.status_line, ui.location_panel, ui.show_events) = saved
        M._onset_hinted = onset
    return seen, st, c


def test_market_label_and_plaza_surrender_entry_wiring():
    seen, st, c = _hub_options(0, "_market")
    assert seen["labels"]["shop"] == "商店"
    seen, st, c = _hub_options(crime.SHOP_REFUSE_BOUNTY, "_market")
    assert "拒絕服務" in seen["labels"]["shop"] and "shop" in seen["keys"]   # 仍可點(點了才看到拒絕理由),不是憑空消失
    seen, st, c = _hub_options(0, "_plaza")
    assert "surrender" not in seen["keys"]
    seen, st, c = _hub_options(120, "_plaza")
    assert "surrender" in seen["keys"] and "120" in seen["labels"]["surrender"]
    # 選下去 → 真的接到 action_surrender(接線)
    called = []
    real = M.action_surrender
    M.action_surrender = lambda state, gamedata: called.append(1)
    try:
        _hub_options(120, "_plaza", pick="surrender")
    finally:
        M.action_surrender = real
    assert called == [1]


# --- C2 審查補強(R226 對抗審查 F1 / F2 / F3)-----------------------------------------------
FAIL_TALK = {(dialogue, "talk_down_chance"): lambda *a, **k: 0.0}


def test_surrender_talk_cannot_be_retried_by_walking_away_after_a_failure():
    """🔴 F1:說退失敗後「轉身離開」再開一次自首 → talked 歸零 → 可無限重試說退(零金幣、不沒收)。失敗必須強制處置。"""
    st, c, prov = _state(bounty=60, loot=2)
    ret, script = _run(M.action_surrender, ["talk", "pay"], st, gd, patches=FAIL_TALK)
    assert script.menus[0][1] == ["talk", "pay", "jail", "leave"], script.menus[0][1]    # 先說退:此刻還能反悔
    assert script.menus[1][1] == ["pay", "jail"], script.menus[1][1]                      # 失敗後:沒有說退、沒有離開
    assert crime.bounty(c, prov) == 0 and c.gold == 500 - 60 and inventory.count_item(c, "ruby") == 0   # 只能付錢(沒收)
    st, c, prov = _state(bounty=60, loot=2)
    ret, script = _run(M.action_surrender, ["talk", "jail"], st, gd, patches=FAIL_TALK)
    assert script.menus[1][1] == ["pay", "jail"] and crime.bounty(c, prov) == 0 and inventory.count_item(c, "ruby") == 0
    # 一次都沒說退就離開 = 自由進出(沒有代價也沒有好處)
    st, c, prov = _state(bounty=60, loot=2)
    for _ in range(3):
        ret, script = _run(M.action_surrender, ["leave"], st, gd)
        assert script.menus[0][1][-1] == "leave" and crime.bounty(c, prov) == 60 and inventory.count_item(c, "ruby") == 2


def test_failed_talk_removes_the_talk_option_at_the_gate_and_when_caught():
    st, c, prov = _state(bounty=60)
    ret, script = _run(M.guard_confrontation, ["talk", "pay"], st, gd, patches=FAIL_TALK)
    assert script.menus[0][1][0] == "talk" and script.menus[1][1] == ["pay", "jail", "resist"], [m[1] for m in script.menus]
    st, c, prov = _state(bounty=60)
    ret, script = _run(M.guard_confrontation, ["talk", "pay"], st, gd, context="caught", patches=FAIL_TALK)
    assert script.menus[1][1] == ["pay", "jail", "resist"], script.menus[1][1]


def test_an_empty_guard_menu_never_spins_and_a_caught_thief_is_still_taken_out_of_the_shop():
    """F3:選單沒答案(腳本化 / 異常環境)→ 盤查迴圈不空轉;當場被抓沒有「離開」選項,賞金還在就不能當成武士放行繼續逛。"""
    for ctx in ("gate", "caught", "surrender"):
        st, c, prov = _state(bounty=50)
        ret, script = _run(M.guard_confrontation, [], st, gd, context=ctx)
        assert ret is None and len(script.menus) == 1, (ctx, len(script.menus))
    st, c, prov = _state()
    iid = _cheap_item(st, c)
    ret, script = _run(M.action_shop, ["steal", _steal(iid)], st, gd, patches=_always_fail())    # 盤查選單拿到 None
    assert ret is None and len(script.menus) == 3, script.titles()                           # 被帶離:沒有第 4 個(商店主選單)
    assert crime.bounty(c, prov) > 0


def test_game_loop_ends_the_run_when_the_shop_reports_death():
    """F2:`died = action_shop(...)` 的接線(商店內反抗衛兵身亡)—— 少了這個賦值,玩家帶著死亡狀態繼續玩。"""
    st, c, prov = _state()
    ended, answered = [], [0]
    saved = (ui.grouped_menu, ui.menu, ui.confirm, ui.message, ui.rule, ui.status_line, ui.location_panel, ui.show_events,
             M.action_shop, M.end_run, M._onset_hinted)
    ui.message = ui.rule = ui.status_line = ui.location_panel = ui.show_events = lambda *a, **k: None
    calls = [0]

    def _grouped(title, groups, **k):
        calls[0] += 1
        if calls[0] == 1:
            return "_market"
        raise _Stop()                                   # 若沒有結束遊戲,下一圈會回到這裡

    def _menu(title, options, allow_back=False, **k):
        if "shop" in [o[0] for o in options]:
            answered[0] += 1
            return "shop" if answered[0] == 1 else None
        return None
    ui.grouped_menu, ui.menu, ui.confirm = _grouped, _menu, (lambda *a, **k: True)
    M.action_shop = lambda state, gamedata: "dead"
    M.end_run = lambda state, gamedata, reason, *a, **k: ended.append(reason)
    try:
        M.game_loop(st, gd)
    except _Stop:
        pass
    finally:
        (ui.grouped_menu, ui.menu, ui.confirm, ui.message, ui.rule, ui.status_line, ui.location_panel, ui.show_events,
         M.action_shop, M.end_run, M._onset_hinted) = saved
    assert ended == ["death"], ended


# --- C3 殺官重罪(R226 續:每打死一名衛兵 +700 賞金 +2 惡名;不計謀殺數)----------------------------------
def test_killing_guards_in_a_resist_is_a_capital_crime_per_guard_killed():
    # 閘道盤查 / 行竊當場共用同一個反抗分支:賞金 0 → 1 名衛兵
    st, c, prov = _state(bounty=50)
    infamy0 = c.infamy
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): _kills_all})
    assert ret == "confronted"
    assert crime.bounty(c, prov) == 50 + 40 + 1 * 700 and c.infamy == infamy0 + 2          # 1 名:+40 拒捕 +700 殺官、+2 惡名
    assert crime.active_heat(c) == 3 and crime.shop_refuses(c, prov)                       # 直達獵殺 tier 3 並越過封店線
    assert script.said("殺官重罪") and script.said("+700")
    # 賞金 200 → 3 名衛兵:每名各 700
    st, c, prov = _state(bounty=200)
    infamy0 = c.infamy
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): _kills_all})
    assert crime.bounty(c, prov) == 200 + 40 + 3 * 700 and c.infamy == infamy0 + 6
    # 賞金 ≥700:隊長 + 2 衛兵,隊長也只算一名
    st, c, prov = _state(bounty=800)
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): _kills_all})
    assert crime.bounty(c, prov) == 800 + 40 + 3 * 700


def test_fleeing_the_fight_leaves_no_kill_penalty_and_murder_count_never_moves():
    st, c, prov = _state(bounty=50)
    infamy0 = c.infamy
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): lambda *a, **k: "fled"})
    assert crime.bounty(c, prov) == 50 + 40 and c.infamy == infamy0                        # 沒打死 = 只有 +40 拒捕
    assert script.said("擊退衛兵") and not script.said("殺官重罪")
    # 打死了:不計「謀殺無辜者」—— 血債招募 / 成就 / 傳奇標籤都讀 murders(使用者問過;計入須另行拍板)
    from tesrpg.systems import brotherhood
    st, c, prov = _state(bounty=50)
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): _kills_all})
    assert c.murders == 0 and not brotherhood.has_blood_debt(c) and not brotherhood.should_recruit(c, gd)
    # 部分打死(打倒一名後逃走):只算打死的那一名
    def _kill_first_then_flee(state, gamedata, guards, *a, **k):
        guards[0].health = 0
        return "fled"
    st, c, prov = _state(bounty=200)                                                       # 3 名衛兵
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): _kill_first_then_flee})
    assert crime.bounty(c, prov) == 200 + 40 + 700


def test_guard_kill_penalty_function_contract():
    st, c, prov = _state()
    infamy0 = c.infamy
    assert crime.guard_kill_penalty(c, prov, 0) == 0 and crime.guard_kill_penalty(c, prov, -2) == 0
    assert crime.bounty(c, prov) == 0 and c.infamy == infamy0
    assert crime.guard_kill_penalty(c, prov, 2) == 1400 and crime.bounty(c, prov) == 1400 and c.infamy == infamy0 + 4
    assert crime.GUARD_KILL_BOUNTY == 700 and crime.GUARD_KILL_BOUNTY > 500                  # 比謀殺平民(500)重;使用者拍板 700


def test_guard_kills_are_recorded_in_their_own_field_not_in_murders():
    """使用者拍板 b:另記「殺官數」(char.guard_kills),不碰 murders(血債招募 / 成就 / 傳奇標籤讀它)。"""
    st, c, prov = _state(bounty=200)                                         # 3 名衛兵
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): _kills_all})
    assert c.guard_kills == 3 and c.murders == 0 and not brotherhood.should_recruit(c, gd)
    st, c, prov = _state(bounty=50)
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): lambda *a, **k: "fled"})
    assert c.guard_kills == 0                                                # 逃走沒打死 = 不計

    def _kill_first_then_flee(state, gamedata, guards, *a, **k):
        guards[0].health = 0
        return "fled"
    st, c, prov = _state(bounty=200)
    ret, script = _run(M.guard_confrontation, ["resist"], st, gd, patches={(M, "run_battle"): _kill_first_then_flee})
    assert c.guard_kills == 1
    # 累計
    st, c, prov = _state()
    crime.guard_kill_penalty(c, prov, 2)
    crime.guard_kill_penalty(c, prov, 1)
    crime.guard_kill_penalty(c, prov, 0)
    assert c.guard_kills == 3 and c.murders == 0


def test_guard_kills_save_round_trip_old_saves_and_bad_values():
    st, c, prov = _state()
    assert Character.from_dict(c.to_dict()).guard_kills == 0
    c.guard_kills = 5
    assert Character.from_dict(c.to_dict()).guard_kills == 5                 # 往返
    d = c.to_dict()
    d.pop("guard_kills")
    assert Character.from_dict(d).guard_kills == 0                           # 舊存檔沒有這欄 → 預設 0
    for bad in (-3, "x", 2.5, None, True, [1]):                              # 壞值一律夾回 0(R03)
        d = c.to_dict()
        d["guard_kills"] = bad
        assert Character.from_dict(d).guard_kills == 0, bad


def test_guard_kills_show_on_the_character_card_and_in_the_life_legend():
    # 一生傳奇「血業」:殺官與兄弟會標籤併列;沒殺過 → 沒有殺官字樣
    st, c, prov = _state()
    assert crime.legacy_label(c) is None
    assert "殺官" not in (legacy.compute(st, gd)["dark_deeds"] or "")
    c.guard_kills = 4
    assert crime.legacy_label(c) == "殺官重犯(打死衛兵 4 名)"
    assert "殺官重犯(打死衛兵 4 名)" in legacy.compute(st, gd)["dark_deeds"]
    c.murders = 2
    both = legacy.compute(st, gd)["dark_deeds"]
    assert "殺官重犯(打死衛兵 4 名)" in both and "謀殺 2 人" in both        # 兩個標籤併列,互不覆蓋
    # 角色卡「聲望與通緝」:web 版有一列「殺官」,沒紀錄就沒有;文字版同
    rows_seen = []
    real = (ui._web, ui._emit_panel)
    ui._web, ui._emit_panel = object(), (lambda title, rows: rows_seen.append((title, rows)))
    try:
        ui.sheet_bounty(c, gd)
        c.guard_kills = 0
        ui.sheet_bounty(c, gd)
    finally:
        ui._web, ui._emit_panel = real
    with_kills, without = rows_seen[0][1], rows_seen[1][1]
    assert {"t": "kv", "k": "殺官", "v": "4 名"} in with_kills
    assert not any(r.get("k") == "殺官" for r in without)
    c.guard_kills = 4
    ui.console.file.truncate(0)
    ui.console.file.seek(0)
    ui.sheet_bounty(c, gd)
    assert "殺官 4 名" in ui.console.file.getvalue()


# --- F 玩家看得到的文字 ----------------------------------------------------------------
def test_player_facing_text_matches_the_constant_and_the_rules():
    root = pathlib.Path(__file__).resolve().parent.parent
    codex = json.dumps(json.load(open(root / "tesrpg" / "data" / "codex.json", encoding="utf-8")), ensure_ascii=False)
    readme = (root / "README.md").read_text(encoding="utf-8")
    needle = f"賞金達 {crime.SHOP_REFUSE_BOUNTY}"
    assert needle in codex and needle in readme, needle                   # 常數改了文字沒改 → 紅燈
    for must in ("向衛兵自首", "銷贓、黑市、旅店、訓練不受影響", "隱形時衛兵撲個空"):
        assert must in codex, must
    assert f"每打死一名衛兵 +{crime.GUARD_KILL_BOUNTY} 賞金" in codex and f"每名 +{crime.GUARD_KILL_BOUNTY} 賞金" in readme   # 殺官重罪數字


# --- E 突變 -----------------------------------------------------------------------
def _swap(obj, name, value, probes):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        for probe in probes:
            probe()
    except AssertionError:                    # 只認斷言失敗(吞任何例外會讓突變被意外錯誤「抓到」,不是守衛真的有咬)
        return False
    finally:
        setattr(obj, name, old)
    return True


def test_guards_fail_under_mutation():
    entry = (test_wanted_player_is_refused_at_the_shop_door_but_299_and_other_provinces_are_fine,)
    assert not _swap(crime, "shop_refuses", lambda char, province: False, entry + (test_threshold_is_the_hunter_tier_two_line_and_above_the_small_bounty_outs,))
    assert not _swap(crime, "SHOP_REFUSE_BOUNTY", 10 ** 9, entry)
    assert not _swap(crime, "SHOP_REFUSE_BOUNTY", 1, (test_surrender_action_options_and_outcomes, test_wanted_player_is_refused_at_the_shop_door_but_299_and_other_provinces_are_fine))
    flow = (test_visible_failed_theft_brings_guards_jail_clears_and_confiscates_and_ends_the_visit,
            test_failed_theft_pay_the_fine_and_talk_down_paths)
    assert not _swap(M, "_shop_theft_aftermath", lambda state, gamedata: None, flow)                      # 不叫衛兵
    real_aftermath = M._shop_theft_aftermath
    assert not _swap(M, "_shop_theft_aftermath", lambda state, gamedata: (None if real_aftermath(state, gamedata) == "leave" else None), flow)   # 叫了但不被帶離

    def _no_refuse_branch(state, gamedata):                  # 隱形者撲空後直接放行:少了「賞金達線被轟出」的兜底
        if spellfx.is_invisible(state.player):
            ui.message("你隱著身形 —— 衛兵循聲趕來,卻只撲了個空。", style="grey70")
            return None
        return real_aftermath(state, gamedata)
    assert not _swap(M, "_shop_theft_aftermath", _no_refuse_branch,
                     (test_invisible_thief_gets_no_guards_but_the_bounty_line_still_throws_them_out,))   # 沒有封店兜底
    # 隱形判定壞掉(永遠看得見)→ 隱形者吃到盤查
    assert not _swap(spellfx, "is_invisible", lambda char: False, (test_invisible_thief_gets_no_guards_but_the_bounty_line_still_throws_them_out,))
    # 武士放行失效
    assert not _swap(court, "is_thane_in_province", lambda *a, **k: False, (test_thane_forgiveness_keeps_the_visit_going,))
    # 自首被隱形跳過(把 surrender 當 gate 叫)
    real_gc = M.guard_confrontation
    assert not _swap(M, "guard_confrontation", lambda state, gamedata, context="gate": real_gc(state, gamedata, "gate"),
                     (test_surrender_is_not_skipped_by_invisibility_but_the_city_gate_still_is,))
    # 自首帶了反抗 / 沒有離開選項
    assert not _swap(M, "guard_confrontation", lambda state, gamedata, context="gate": real_gc(state, gamedata, "caught" if context == "surrender" else context),
                     (test_surrender_action_options_and_outcomes,))
    assert not _swap(crime, "SHOP_REFUSE_BOUNTY", 301, (test_player_facing_text_matches_the_constant_and_the_rules,))   # 文字與常數脫鉤
    kill = (test_killing_guards_in_a_resist_is_a_capital_crime_per_guard_killed,
            test_fleeing_the_fight_leaves_no_kill_penalty_and_murder_count_never_moves)
    assert not _swap(crime, "GUARD_KILL_BOUNTY", 40, kill)                                   # 殺官罰金被調回 +40
    assert not _swap(crime, "GUARD_KILL_BOUNTY", 701, (test_player_facing_text_matches_the_constant_and_the_rules,))
    assert not _swap(crime, "guard_kill_penalty", lambda char, province, killed: 0, kill)    # 完全不罰
    real_pen = crime.guard_kill_penalty

    def _counts_murders(char, province, killed):             # 偷偷把衛兵算成「謀殺無辜者」→ 血債招募被誤觸
        char.murders += killed
        return real_pen(char, province, killed)
    assert not _swap(crime, "guard_kill_penalty", _counts_murders, (test_fleeing_the_fight_leaves_no_kill_penalty_and_murder_count_never_moves,))

    def _forgets_kills(char, province, killed):               # 罰了賞金卻不記殺官數
        n0 = char.guard_kills
        amount = real_pen(char, province, killed)
        char.guard_kills = n0
        return amount
    assert not _swap(crime, "guard_kill_penalty", _forgets_kills, (test_guard_kills_are_recorded_in_their_own_field_not_in_murders,))
    assert not _swap(crime, "legacy_label", lambda char: None, (test_guard_kills_show_on_the_character_card_and_in_the_life_legend,))
    # 「逃走也算殺人 / 沒打死也計」是 main.py 的計數錯誤,函式層突變碰不到 → 以磁碟突變驗證(見 handoff R226 續)
    # 失手後沒加賞金(steal_item 改壞)
    real_steal = crime.steal_item

    def _no_bounty(char, gamedata, item_id, rng):
        before = dict(char.bounties)
        r = real_steal(char, gamedata, item_id, rng)
        char.bounties = before
        return r
    assert not _swap(crime, "steal_item", _no_bounty, (test_invisible_thief_gets_no_guards_but_the_bounty_line_still_throws_them_out,))


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
