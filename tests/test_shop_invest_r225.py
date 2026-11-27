"""R225 ② 投資商店(付錢永久升級一家店;兩階:擴充貨架 1,000 / 大城貨源 3,000;不給賣價加成)。

守衛:
  1. 階數 0 逐位元組同舊:目錄(全部 229 個地點)與補貨結果(多種子 × 行商人脈倍率)== 凍結在本檔的舊式;擲骰次數不變。
  2. 第 1 階:每樣貨至少 1 件再 ×2(沒有缺貨;擲骰序列與第 0 階同、目錄同);第 2 階:目錄多出高級錠材(城與鎮皆然),
     法師城另有大型 / 黑色空魂石;非法師店不憑空賣空魂石、鎮不憑空多賣一般材料;大城本來就有 → 不變。
  3. 價錢:1,000 → 3,000;吃 ① 的議價折抵;到頂 / 無商店 → None;不夠錢 → 不動任何狀態;升級清掉補貨時點。
  4. 不給賣價加成:投資前後 buy_price / sell_price / fence / 黑市價逐項相同。
  5. 各家各記:升 A 店不影響 B 店;壞存檔值讀取端夾回 0 ~ 2;存讀檔往返;舊存檔缺欄 → 0。
  6. 真流程(action_shop):選單標籤價 == 確認句價 == 實扣;落成即重新補貨(不缺貨 / 有大城貨);標題標店面;到頂後選項消失。
  7. 突變下會紅(補貨倍數 / 擴目錄階數 / 價目 / 第 1 階仍缺貨)。
"""
import io
import random

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

import sim_economy as E
from tesrpg import main as M
from tesrpg.models.character import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import world

gd = E.gd
_MAGE_CITY = "bruma"          # 一般城 + 法師公會
_PLAIN_CITY = "anvil"         # 一般城、無法師公會
_TOWN = "dragon_bridge"       # 鎮(不賣一般材料)
_MAJOR = "imperial_city"      # 大城(本來就賣高級材料 + 大型空魂石)
_ALL_SHOPS = [lid for lid in gd.world["locations"] if world.merchant_catalog(gd, lid)]


# --- 凍結的舊式(R225 之前 world.py 的寫法,逐字抄;只用來對帳,不得改) ----------
def _old_catalog(loc_id):
    loc = gd.location(loc_id)
    catalog = list(loc.get("merchant_stock", []))
    if loc.get("type") == "city":
        extra = list(world._COMMON_MATERIALS) + (list(world._HIGH_MATERIALS) if loc_id in world.MAJOR_CITIES else [])
        catalog += [iid for iid in extra if iid not in catalog]
    if "mages_guild" in loc.get("services", []):
        gems = list(world._EMPTY_GEM_STOCK) + (list(world._EMPTY_GEM_STOCK_MAJOR) if loc_id in world.MAJOR_CITIES else [])
        catalog += [iid for iid in gems if iid not in catalog]
    return catalog


def _old_stock(loc_id, rng, rmult):
    mats = world._crafting_material_ids(gd)

    def _qty(iid):
        q = world._restock_qty(gd.item(iid)["value"], rng, material=iid in mats)
        return 0 if q == 0 else max(1, round(q * rmult))
    return {iid: _qty(iid) for iid in _old_catalog(loc_id)}


def _char(gold=500000, **kw):
    c = E.make_char(**kw) if kw else E.make_char(5, 40)
    c.gold = gold
    return c


def _stocked(c, loc, seed=3):
    c.location_id = loc
    st = GameState(player=c, rng=RNG(seed=seed), game_mode="adventure")
    world.ensure_stock(c, gd, loc, st.time, st.rng)
    return st


# --- 1 階數 0 逐位元組同舊 ---------------------------------------------------
def test_tier_zero_catalog_equals_frozen_old_for_every_location():
    for lid in gd.world["locations"]:
        assert world.merchant_catalog(gd, lid) == _old_catalog(lid) == world.merchant_catalog(gd, lid, 0), lid
        assert world.merchant_catalog(gd, lid, 1) == _old_catalog(lid), lid   # 第 1 階只改補貨量、不改目錄


def test_tier_zero_restock_equals_frozen_old_and_leaves_rng_in_step():
    for lid in (_MAGE_CITY, _PLAIN_CITY, _TOWN, _MAJOR):
        for seed in (1, 2, 9):
            for rmult in (1.0, 1.5):
                a, b = RNG(seed=seed), RNG(seed=seed)
                mats = world._crafting_material_ids(gd)
                got = {iid: world.shop_qty(world._restock_qty(gd.item(iid)["value"], a, material=iid in mats), 0, rmult)
                       for iid in world.merchant_catalog(gd, lid, 0)}
                assert got == _old_stock(lid, b, rmult), (lid, seed, rmult)
                assert a.randint(0, 10 ** 9) == b.randint(0, 10 ** 9)


def test_ensure_stock_at_tier_zero_matches_old_through_the_real_function():
    for lid in (_MAGE_CITY, _TOWN):
        c = _char()
        st = _stocked(c, lid, seed=5)
        assert c.shop_stock[lid] == _old_stock(lid, RNG(seed=5), 1.0)


# --- 2 各階效果 ---------------------------------------------------------------
def test_shop_qty_table():
    cases = {(0, 0, 1.0): 0, (0, 1, 1.0): 2, (1, 0, 1.0): 1, (1, 1, 1.0): 2, (5, 1, 1.0): 10,
             (3, 1, 1.5): 9, (0, 0, 1.5): 0, (0, 2, 1.0): 2, (2, 0, 1.5): 3}
    for (q, tier, rm), want in cases.items():
        assert world.shop_qty(q, tier, rm) == want, (q, tier, rm)


def test_tier_one_doubles_and_never_runs_out():
    zero_seen = False
    for seed in range(1, 40):
        a, c = _char(), _char()
        c.shop_invest[_MAGE_CITY] = 1
        _stocked(a, _MAGE_CITY, seed)
        _stocked(c, _MAGE_CITY, seed)
        if any(v == 0 for v in a.shop_stock[_MAGE_CITY].values()):
            zero_seen = True
        assert set(c.shop_stock[_MAGE_CITY]) == set(a.shop_stock[_MAGE_CITY])        # 同目錄
        for iid, v in c.shop_stock[_MAGE_CITY].items():
            assert v >= 2 and v % 2 == 0, (seed, iid, v)                          # 至少 1 件再 ×2
            assert v == max(1, a.shop_stock[_MAGE_CITY][iid]) * 2, (seed, iid)     # 與第 0 階同一組擲骰
    assert zero_seen                                                              # 對照組(第 0 階)確實會缺貨 → 本測試不是空轉


def test_tier_two_adds_high_materials_and_major_gems_where_they_belong():
    high, gems = set(world._HIGH_MATERIALS), set(world._EMPTY_GEM_STOCK_MAJOR)
    assert not high & set(world.merchant_catalog(gd, _MAGE_CITY)) and not gems & set(world.merchant_catalog(gd, _MAGE_CITY))
    cat = set(world.merchant_catalog(gd, _MAGE_CITY, 2))
    assert high <= cat and gems <= cat                                  # 法師城:高級錠材 + 大型 / 黑色空魂石
    plain = set(world.merchant_catalog(gd, _PLAIN_CITY, 2))
    assert high <= plain and not gems & plain                           # 非法師城:不憑空賣空魂石
    town0, town2 = set(world.merchant_catalog(gd, _TOWN)), set(world.merchant_catalog(gd, _TOWN, 2))
    assert high <= town2 and not set(world._COMMON_MATERIALS) - town0 & town2   # 鎮:只多高級錠材,不憑空多賣一般材料
    assert town2 - town0 == high
    assert world.merchant_catalog(gd, _MAJOR, 2) == world.merchant_catalog(gd, _MAJOR, 0)   # 大城本來就有 → 不變
    for lid in _ALL_SHOPS:                                              # 目錄只增不減、不重複
        c0, c2 = world.merchant_catalog(gd, lid), world.merchant_catalog(gd, lid, 2)
        assert set(c0) <= set(c2), lid                                              # 只增不減(原資料自帶的重複不管)
        assert len(c2) - len(c0) == len(set(c2) - set(c0)), lid                    # 新增的品項不重複


def test_tier_two_stock_really_contains_the_new_goods():
    c = _char()
    c.shop_invest[_MAGE_CITY] = 2
    _stocked(c, _MAGE_CITY, 4)
    for iid in list(world._HIGH_MATERIALS) + list(world._EMPTY_GEM_STOCK_MAJOR):
        assert c.shop_stock[_MAGE_CITY][iid] >= 2, iid
    assert set(world.in_stock_items(c, gd, _MAGE_CITY)) == set(world.merchant_catalog(gd, _MAGE_CITY, 2))


# --- 3 價錢與狀態 ------------------------------------------------------------
def test_prices_follow_the_service_rebate_and_cap_out():
    plain = _char()
    nxt = world.shop_invest_next(plain, gd, _MAGE_CITY)
    assert (nxt["tier"], nxt["price"], nxt["name"]) == (1, 1000, "擴充貨架")
    plain.shop_invest[_MAGE_CITY] = 1
    assert world.shop_invest_next(plain, gd, _MAGE_CITY)["price"] == 3000
    plain.shop_invest[_MAGE_CITY] = 2
    assert world.shop_invest_next(plain, gd, _MAGE_CITY) is None
    half = E.make_char(100, 40, nodes=True)                             # 溢出 0.20 → 服務價 −10%
    assert world.shop_invest_next(half, gd, _MAGE_CITY)["price"] == 900
    half.shop_invest[_MAGE_CITY] = 1
    assert world.shop_invest_next(half, gd, _MAGE_CITY)["price"] == 2700
    cap = E.make_char(100, 100, nodes=True)                             # 封頂 −20%
    assert world.shop_invest_next(cap, gd, _MAGE_CITY)["price"] == 800
    assert world.shop_invest_next(plain, gd, _first_without_shop()) is None


def _first_without_shop():
    return next(l for l in gd.world["locations"] if not world.merchant_catalog(gd, l))


def test_invest_charges_sets_tier_and_clears_restock_clock():
    c = _char(gold=1500)
    _stocked(c, _MAGE_CITY)
    assert _MAGE_CITY in c.shop_restock_at
    assert world.invest_shop(c, gd, _MAGE_CITY) == 1000
    assert c.gold == 500 and world.shop_tier(c, _MAGE_CITY) == 1
    assert _MAGE_CITY not in c.shop_restock_at                          # 落成 = 下次造訪立刻補
    before = (c.gold, dict(c.shop_invest))
    assert world.invest_shop(c, gd, _MAGE_CITY) is None                 # 第 2 階 3,000,錢不夠 → 不動任何狀態
    assert (c.gold, c.shop_invest) == (before[0], before[1])
    c.gold = 10000
    assert world.invest_shop(c, gd, _MAGE_CITY) == 3000 and world.shop_tier(c, _MAGE_CITY) == 2
    assert world.invest_shop(c, gd, _MAGE_CITY) is None and c.gold == 7000   # 到頂不再收錢


# --- 4 不給賣價加成 -----------------------------------------------------------
def test_investment_does_not_change_any_price():
    for kw in (dict(mercantile=5, personality=40), dict(mercantile=100, personality=100, nodes=True, thieves=E.TOP_THIEF, infamy=50)):
        c = E.make_char(**kw)
        ids = ("ebony_sword", "ruby", "healing_potion", "iron_ingot", "lockpick", "ebony_ingot")
        before = {i: (world.buy_price(c, gd, i), world.sell_price(c, gd, i), world.fence_sell_price(c, gd, i),
                      world.black_market_price(c, gd, i), world.min_buy_price(c, gd, i)) for i in ids}
        c.shop_invest.update({_MAGE_CITY: 2, _TOWN: 1})
        after = {i: (world.buy_price(c, gd, i), world.sell_price(c, gd, i), world.fence_sell_price(c, gd, i),
                     world.black_market_price(c, gd, i), world.min_buy_price(c, gd, i)) for i in ids}
        assert before == after


# --- 5 各家各記 / 存檔 -------------------------------------------------------
def test_each_shop_keeps_its_own_tier():
    c = _char()
    world.invest_shop(c, gd, _MAGE_CITY)
    assert world.shop_tier(c, _MAGE_CITY) == 1 and world.shop_tier(c, _TOWN) == 0 and world.shop_tier(c, _PLAIN_CITY) == 0
    assert world.merchant_catalog(gd, _TOWN, world.shop_tier(c, _TOWN)) == _old_catalog(_TOWN)


def test_bad_saved_values_are_clamped_on_read():
    c = _char()
    inf, nan = float("inf"), float("nan")
    for raw, want in ((2, 2), (1, 1), (0, 0), (-3, 0), (99, 2), ("2", 2), ("x", 0), (None, 0), (1.9, 1), ([], 0),
                      (inf, 0), (-inf, 0), (nan, 0)):                       # 手改存檔的 Infinity / NaN(int() 會丟 OverflowError / ValueError)
        c.shop_invest = {_MAGE_CITY: raw}
        assert world.shop_tier(c, _MAGE_CITY) == want, raw


def test_save_round_trip_and_old_saves_without_the_field():
    c = _char()
    c.shop_invest = {_MAGE_CITY: 2, _TOWN: 1}
    d = c.to_dict()
    assert d["shop_invest"] == {_MAGE_CITY: 2, _TOWN: 1}
    again = Character.from_dict(dict(d))
    assert again.shop_invest == {_MAGE_CITY: 2, _TOWN: 1}
    old = dict(d)
    old.pop("shop_invest")
    assert Character.from_dict(old).shop_invest == {}                   # 舊存檔缺欄 → 無投資
    bad = dict(d)
    bad["shop_invest"] = ["junk"]
    assert Character.from_dict(bad).shop_invest == {}                   # 壞型別 → 無投資


def test_tier_descriptions_match_the_real_restock_numbers():
    """玩家看到的說明不得與實際補貨量不符(R225 審查:原寫「至少一件」,實際 max(1,q)×2 = 至少兩件)。"""
    floor = world.shop_qty(0, 1, 1.0)
    assert floor == 2 == max(1, 0) * world.SHOP_INVEST_RESTOCK_MULT
    assert "至少補兩件" in world.SHOP_INVEST_TIERS[0]["desc"] and "加倍" in world.SHOP_INVEST_TIERS[0]["desc"]
    assert "一件" not in world.SHOP_INVEST_TIERS[0]["desc"]


# --- 6 真流程 -----------------------------------------------------------------
class _Script:
    def __init__(self, picks, confirm_to=True):
        self.picks, self.confirm_to = list(picks), confirm_to
        self.menus, self.confirms = [], []

    def menu(self, title, options, allow_back=False, **kw):
        self.menus.append((title, options))
        return self.picks.pop(0) if self.picks else None

    def confirm(self, prompt, *a, **kw):
        self.confirms.append(prompt)
        return self.confirm_to


def _shop(state, picks, confirm_to=True):
    script = _Script(picks, confirm_to)
    real = (ui.menu, ui.confirm)
    ui.menu, ui.confirm = script.menu, script.confirm
    try:
        M.action_shop(state, gd)
    finally:
        ui.menu, ui.confirm = real
    return script


def _invest_label(script, idx=0):
    return next(o[1] for o in script.menus[idx][1] if o[0] == "invest")


def test_real_flow_label_confirm_and_charge_agree_and_restock_is_immediate():
    for kw, price1, price2 in ((dict(mercantile=5, personality=40), 1000, 3000),
                               (dict(mercantile=100, personality=40, nodes=True), 900, 2700)):
        c = E.make_char(**kw)
        c.gold = 500000
        st = _stocked(c, _MAGE_CITY)
        script = _shop(st, ["invest", "invest"])
        assert f"({price1} 金)" in _invest_label(script, 0), _invest_label(script, 0)
        assert f"({price2} 金)" in _invest_label(script, 1), _invest_label(script, 1)     # 升完立刻換成下一階
        assert f"以 {price1} 金投資「擴充貨架」" in script.confirms[0] and f"以 {price2} 金投資「大城貨源」" in script.confirms[1]
        assert 500000 - c.gold == price1 + price2 and world.shop_tier(c, _MAGE_CITY) == 2
        assert all(v >= 2 for v in c.shop_stock[_MAGE_CITY].values())                    # 落成即補:不缺貨
        assert c.shop_stock[_MAGE_CITY]["ebony_ingot"] >= 2                              # 大城貨已上架
        assert "店面:大城貨源" in script.menus[-1][0]                                   # 標題標店面
        assert "invest" not in [o[0] for o in script.menus[-1][1]]                       # 到頂後選項消失


def test_real_flow_declined_or_poor_changes_nothing():
    c = _char(gold=5000)
    st = _stocked(c, _MAGE_CITY)
    stock = dict(c.shop_stock[_MAGE_CITY])
    script = _shop(st, ["invest"], confirm_to=False)
    assert c.gold == 5000 and world.shop_tier(c, _MAGE_CITY) == 0 and c.shop_stock[_MAGE_CITY] == stock
    assert "店面" not in script.menus[0][0]
    poor = _char(gold=999)
    st2 = _stocked(poor, _MAGE_CITY)
    script = _shop(st2, ["invest"])
    assert poor.gold == 999 and world.shop_tier(poor, _MAGE_CITY) == 0 and not script.confirms


def test_shop_without_merchant_never_offers_investment():
    lid = _first_without_shop()
    assert world.shop_invest_next(_char(), gd, lid) is None


# --- 7 突變 -------------------------------------------------------------------
def _mutation_survives(attr, value, probes):
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
    every = (test_tier_one_doubles_and_never_runs_out, test_shop_qty_table)
    assert not _mutation_survives("SHOP_INVEST_RESTOCK_MULT", 1, every)
    assert not _mutation_survives("SHOP_INVEST_RESTOCK_MULT", 3, every)
    assert not _mutation_survives("SHOP_SUPPLY_TIER", 3, (test_tier_two_adds_high_materials_and_major_gems_where_they_belong,))
    assert not _mutation_survives("SHOP_SUPPLY_TIER", 1, (test_tier_two_adds_high_materials_and_major_gems_where_they_belong,
                                                          test_tier_zero_catalog_equals_frozen_old_for_every_location))
    tiers = world.SHOP_INVEST_TIERS
    assert not _mutation_survives("SHOP_INVEST_TIERS", ({**tiers[0], "price": 1500}, tiers[1]), (test_prices_follow_the_service_rebate_and_cap_out,))
    assert not _mutation_survives("SHOP_INVEST_TIERS", (tiers[0], {**tiers[1], "price": 2000}), (test_invest_charges_sets_tier_and_clears_restock_clock,))
    real = world.shop_qty
    world.shop_qty = lambda q, tier, rmult: real(q, 0, rmult)         # 第 1 階仍缺貨
    try:
        try:
            test_tier_one_doubles_and_never_runs_out()
            survived = True
        except AssertionError:
            survived = False
    finally:
        world.shop_qty = real
    assert not survived


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_shop_invest_r225 OK")
