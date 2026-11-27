"""R225 ③ 行情(各省固定偏好 ×1.2 / ×0.9 + 脈動短期行情 ×1.3;只動賣給一般商店的價錢)。

守衛:
  1. 資料:每個有商店的省都有偏好、favored ≠ glutted、類別 id 有效、每件可賣物品至多屬一個類別;
     有 market 的脈動指向有效類別、倍率 > 1、省份存在。
  2. 數值:固定偏好 ×1.2 / ×0.9、脈動 ×1.3、兩者相乘(夏暮 魂石 ×1.56)、同類多筆脈動取最大不疊乘;沒有行情的物品
     與類別 → 逐位元組同 sell_price。
  3. 視窗:脈動行情只在該脈動的聚光視窗內(active_window_days)、只在該省。
  4. 🔴 R223 全域規則:所有脈動同時生效下,賣給商店的價錢 < 這個角色買得到的最低價(跑 sim_economy 的掃描);
     行情 > 1 時不低於基準價、< 1 時不高於基準價、至少 1 金。
  5. 範圍:sell_price / buy_price / min_buy_price / 銷贓價 / 黑市價完全不受行情影響。
  6. 真流程:action_shop 賣貨清單標籤價 == 實收;清單標「行情 ±N%」;進店提示本地行情;賣貨路徑不得再用 world.sell_price。
  7. 介面:脈動廣播附行情一句話(沒有 market 的脈動不附)。
  8. 突變下會紅(倍率 / 拿掉夾限 / 賣貨走回 sell_price / 視窗)。
"""
import inspect
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

import sim_economy as E
from tesrpg import main as M
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import inventory, worldpulse, world

gd = E.gd
_PROVINCES = {l["province"] for l in gd.world["locations"].values() if l.get("merchant_stock")}


def _novice():
    return E.make_char(5, 40)


def _chain(c, iid):
    return world._sell_chain(c, gd, gd.item(iid)["value"])


# --- 1 資料 ------------------------------------------------------------------
def test_market_data_is_well_formed():
    cats, provs = gd.market["categories"], gd.market["provinces"]
    assert set(provs) >= _PROVINCES                                         # 每個有商店的省都有偏好
    for name, p in provs.items():
        assert p["favored"] in cats and p["glutted"] in cats and p["favored"] != p["glutted"], name
        assert p.get("note"), name
    kinds = {d["kind"] for d in gd.items.values()}
    for cid, cat in cats.items():
        assert cat["name"] and (cat.get("kinds") or cat.get("items")), cid
        assert set(cat.get("kinds", ())) <= kinds, cid
        assert all(i in gd.items for i in cat.get("items", ())), cid
    for iid in gd.items:                                                    # 每件物品至多屬一類
        hits = [cid for cid, cat in cats.items() if iid in cat.get("items", ()) or gd.item(iid)["kind"] in cat.get("kinds", ())]
        assert len(hits) <= 1, (iid, hits)
        assert world.item_market_category(gd, iid) == (hits[0] if hits else None)


def test_pulse_markets_are_well_formed():
    cats = gd.market["categories"]
    n = 0
    for pid, p in gd.world_pulse.items():
        m = p.get("market")
        if not m:
            continue
        n += 1
        assert m["category"] in cats and m["mult"] > 1.0 and m.get("note"), pid
        assert p["province"] in {l["province"] for l in gd.world["locations"].values()}, pid
    assert n >= 8                                                           # 內容量底線:多數情境有行情(地下世界 / 走私窗口例外)


# --- 2 數值 ------------------------------------------------------------------
def test_fixed_preferences_apply_to_the_right_categories():
    c = _novice()
    assert world.shop_sell_price(c, gd, "iron_sword", "whiterun", 0) == round(_chain(c, "iron_sword") * 1.2)      # 天際 +武器
    assert world.shop_sell_price(c, gd, "iron_ingot", "whiterun", 0) == max(1, round(_chain(c, "iron_ingot") * 0.9))  # 天際 −礦材
    assert world.shop_sell_price(c, gd, "iron_sword", "whiterun", 0) > world.sell_price(c, gd, "iron_sword")
    assert world.shop_sell_price(c, gd, "iron_ingot", "whiterun", 0) <= world.sell_price(c, gd, "iron_ingot")
    for iid in ("leather_cuirass", "healing_potion", "lockpick"):            # 天際沒偏好的類別 / 無類別:逐位元組同基準價
        assert world.shop_sell_price(c, gd, iid, "whiterun", 0) == world.sell_price(c, gd, iid), iid
    assert world.item_market_category(gd, "healing_potion") is None


def test_pulse_markets_stack_with_fixed_and_do_not_stack_with_each_other():
    c = _novice()
    c.world_pulse_day["pulse_summerset_deepstir"] = 0                       # 夏暮:固定偏好魂石 ×1.2 + 行情 ×1.3
    soul = next(i for i in E.POOL if world.item_market_category(gd, i) == "soul")
    assert abs(world.market_factor(c, gd, "alinor", soul, 0) - 1.2 * 1.3) < 1e-12
    assert world.shop_sell_price(c, gd, soul, "alinor", 0) == min(round(_chain(c, soul) * 1.56), world.min_buy_price(c, gd, soul) - 1)
    c2 = _novice()
    c2.world_pulse_day["pulse_cyrodiil_banditry"] = 0                       # 賽羅迪爾:武器 ×1.3(固定偏好是珠寶)
    assert abs(world.market_factor(c2, gd, "bruma", "iron_sword", 0) - 1.3) < 1e-12
    # 同類多筆取最大(借用 gd 暫插三筆假脈動;結束還原)。字典序 aa(1.1) < banditry(1.3) < mm(1.5) < zz(1.2):
    # 最大的夾在中間 → 「先到先得」(得 1.1)與「後者覆蓋」(得 1.2)與「疊乘」都會算錯,只有取最大是 1.5。
    def fake(mult):
        return {"province": "賽羅迪爾", "weight": 0, "cooldown_days": 99, "active_window_days": 8, "min_day": 0,
                "spotlight_quests": [], "news": "x", "market": {"category": "weapon", "mult": mult, "note": "測試"}}
    ids = {"pulse_aa_test": 1.1, "pulse_mm_test": 1.5, "pulse_zz_test": 1.2}
    for pid, mult in ids.items():
        gd.world_pulse[pid] = fake(mult)
    try:
        for pid in ids:
            c2.world_pulse_day[pid] = 0
        assert abs(world.market_factor(c2, gd, "bruma", "iron_sword", 0) - 1.5) < 1e-12
    finally:
        for pid in ids:
            del gd.world_pulse[pid]


def test_market_state_lists_only_categories_with_a_market():
    st = world.market_state(_novice(), gd, "whiterun", 0)
    assert set(st) == {gd.market["provinces"]["天際"]["favored"], gd.market["provinces"]["天際"]["glutted"]}
    assert world.market_line(_novice(), gd, "whiterun", 0).startswith("本地商人收購行情 —— 武器 +20%、礦材皮料 −10%")


# --- 3 視窗 -------------------------------------------------------------------
def test_pulse_market_lives_exactly_as_long_as_its_spotlight_window():
    c = _novice()
    p = gd.world_pulse["pulse_cyrodiil_banditry"]
    win = p["active_window_days"]
    c.world_pulse_day["pulse_cyrodiil_banditry"] = 10
    f = lambda today, loc="bruma": world.market_factor(c, gd, loc, "iron_sword", today)
    assert f(10) == 1.3 and f(10 + win - 1) == 1.3 and f(10 + win) == 1.0     # 視窗內有、視窗滿就沒
    assert f(10, "whiterun") == 1.2                                          # 別的省只有自己的固定偏好
    assert worldpulse.active_markets(c, gd, "賽羅迪爾", 10 + win - 1)["weapon"]["days_left"] == 1
    assert "餘 8 天" in world.market_line(c, gd, "bruma", 10)


# --- 4 R223 全域規則 -----------------------------------------------------------
def test_market_never_breaks_the_global_sell_below_buy_rule():
    for label, bad, example in E.market_scan():
        assert bad == 0, (label, bad, example)


def test_direction_of_market_prices():
    for kw in (dict(mercantile=5, personality=40), dict(mercantile=100, personality=100),
               dict(mercantile=100, personality=100, thieves=E.TOP_THIEF, infamy=50)):
        c = E.make_char(**kw)
        for pid in gd.world_pulse:
            c.world_pulse_day[pid] = 0
        for lid in ("whiterun", "bruma", "alinor", "kvatch"):
            for iid in E.POOL:
                shop, base = world.shop_sell_price(c, gd, iid, lid, 0), world.sell_price(c, gd, iid)
                f = world.market_factor(c, gd, lid, iid, 0)
                assert shop >= 1
                if f > 1.0:
                    assert base <= shop < world.min_buy_price(c, gd, iid), (lid, iid)
                elif f < 1.0:
                    assert shop <= base, (lid, iid)
                else:
                    assert shop == base


def test_capped_rows_are_tagged_with_the_real_change():
    c = E.make_char(100, 100, thieves=E.TOP_THIEF, fighters=E.TOP_FIGHTER, infamy=50, fame=700, blessing=True, pact=True)
    assert world.shop_sell_price(c, gd, "iron_sword", "whiterun", 0) == world.sell_price(c, gd, "iron_sword")   # 已頂到上限:沒有加成
    assert "已頂到買價上限" in world.market_tag(c, gd, "iron_sword", "whiterun", 0)
    assert world.market_tag(_novice(), gd, "iron_sword", "whiterun", 0) == "行情 +20%"
    assert world.market_tag(_novice(), gd, "iron_ingot", "whiterun", 0) == "行情 −10%"
    assert world.market_tag(_novice(), gd, "healing_potion", "whiterun", 0) == ""


# --- 5 範圍 -------------------------------------------------------------------
def test_market_changes_no_other_price():
    ids = ("iron_sword", "ebony_sword", "ruby", "iron_ingot", "healing_potion", "filled_grand_soul_gem", "leather_cuirass")
    for kw in (dict(mercantile=5, personality=40), dict(mercantile=100, personality=100, thieves=E.TOP_THIEF, infamy=50)):
        quiet, busy = E.make_char(**kw), E.make_char(**kw)
        for pid in gd.world_pulse:
            busy.world_pulse_day[pid] = 0
        for iid in ids:
            f = lambda c: (world.sell_price(c, gd, iid), world.buy_price(c, gd, iid), world.min_buy_price(c, gd, iid),
                           world.fence_sell_price(c, gd, iid), world.black_market_price(c, gd, iid))
            assert f(quiet) == f(busy), iid                                 # 脈動行情不動任何「基準」價


# --- 6 真流程 -----------------------------------------------------------------
def _sell_flow(loc, iid, pulse=None):
    c = _novice()
    c.location_id = loc
    c.gold = 0
    c.inventory = [stack for stack in c.inventory if stack["id"] != iid]       # 起手裝備可能已有同款 → 清掉,只留一件好走單件分支
    inventory.add_item(c, iid, 1)
    if pulse:
        c.world_pulse_day[pulse] = 0
    st = GameState(player=c, rng=RNG(seed=1), game_mode="adventure")
    menus, msgs = [], []
    picks = ["sell", iid]
    real = (ui.menu, ui.confirm, ui.message, ui.inventory_panel, ui.shop_panel)
    ui.menu = lambda title, options, allow_back=False, **kw: (menus.append((title, options)), picks.pop(0) if picks else None)[1]
    ui.confirm = lambda *a, **kw: True
    ui.message = lambda text, **kw: msgs.append(text)
    ui.inventory_panel = ui.shop_panel = lambda *a, **kw: None
    try:
        M.action_shop(st, gd)
    finally:
        ui.menu, ui.confirm, ui.message, ui.inventory_panel, ui.shop_panel = real
    return c, menus, msgs


def test_real_flow_sell_label_equals_credit_and_is_tagged():
    c, menus, msgs = _sell_flow("whiterun", "iron_sword")
    label = next(o[1] for o in menus[1][1] if o[0] == "iron_sword")
    want = world.shop_sell_price(_novice(), gd, "iron_sword", "whiterun", 0)
    assert f"售 {want} 金" in label and "(行情 +20%)" in label, label
    assert c.gold == want and want > world.sell_price(_novice(), gd, "iron_sword")
    assert any("本地商人收購行情" in m and "武器 +20%" in m for m in msgs), msgs   # 進店提示
    c2, menus2, _ = _sell_flow("bruma", "iron_sword", pulse="pulse_cyrodiil_banditry")
    label2 = next(o[1] for o in menus2[1][1] if o[0] == "iron_sword")
    pc = _novice()
    pc.world_pulse_day["pulse_cyrodiil_banditry"] = 0
    want2 = world.shop_sell_price(pc, gd, "iron_sword", "bruma", 0)
    assert "(行情 +30%)" in label2 and f"售 {want2} 金" in label2 and c2.gold == want2, label2
    # 無行情的貨:標籤沒有行情字樣、實收 = 基準價
    c3, menus3, _ = _sell_flow("whiterun", "healing_potion")
    label3 = next(o[1] for o in menus3[1][1] if o[0] == "healing_potion")
    assert "行情" not in label3 and c3.gold == world.sell_price(_novice(), gd, "healing_potion")


def test_shop_sell_path_does_not_use_the_base_sell_price():
    src = inspect.getsource(M.action_shop)
    assert "world.sell_price(" not in src                                    # 賣貨一律走 shop_sell_price(預覽 = 實收)
    assert src.count("world.shop_sell_price(") >= 3


# --- 7 介面 -------------------------------------------------------------------
def test_pulse_broadcast_carries_the_market_sentence():
    s = world.pulse_market_news(gd, "pulse_cyrodiil_banditry")
    assert "賽羅迪爾" in s and "武器" in s and "+30%" in s and "8 天" in s
    assert world.pulse_market_news(gd, "pulse_cyrodiil_underworld") == ""
    assert world.pulse_market_news(gd, "pulse_elsweyr_smuggle") == ""


# --- 8 突變 -------------------------------------------------------------------
def _survives(attr, value, probes):
    old = getattr(world, attr)
    setattr(world, attr, value)
    try:
        for probe in probes:
            probe()
    except AssertionError:
        return False
    finally:
        setattr(world, attr, old)
    return True


def test_guards_fail_under_mutation():
    assert not _survives("MARKET_FAVORED_MULT", 1.5, (test_fixed_preferences_apply_to_the_right_categories,))
    assert not _survives("MARKET_GLUTTED_MULT", 0.5, (test_fixed_preferences_apply_to_the_right_categories,))
    def _uncapped(char, gamedata, iid, loc, today):                          # 拿掉全域規則的夾限(掃描的買價下限維持原樣)
        f = world.market_factor(char, gamedata, loc, iid, today)
        base = world.sell_price(char, gamedata, iid)
        return base if f == 1.0 else max(1, round(world._sell_chain(char, gamedata, gamedata.item(iid)["value"]) * f))
    assert not _survives("shop_sell_price", _uncapped, (test_market_never_breaks_the_global_sell_below_buy_rule,
                                                        test_direction_of_market_prices))
    assert not _survives("shop_sell_price", lambda char, gamedata, iid, loc, today: world.sell_price(char, gamedata, iid),
                         (test_real_flow_sell_label_equals_credit_and_is_tagged,))                     # 賣貨沒吃行情
    real = worldpulse.active_pulses
    worldpulse.active_pulses = lambda char, gamedata, today: set(char.world_pulse_day)    # 視窗永不過期
    try:
        try:
            test_pulse_market_lives_exactly_as_long_as_its_spotlight_window()
            survived = True
        except AssertionError:
            survived = False
    finally:
        worldpulse.active_pulses = real
    assert not survived


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_market_r225 OK")
