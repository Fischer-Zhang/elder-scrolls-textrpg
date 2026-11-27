"""R225 ④ 盜賊賣價與行竊衰減(審查後續;使用者拍板「贓物例外 + 方案 2」)。

守衛:
  A 價格模型
    1 盜賊加成不再抬高買價:加入盜賊公會後,任何物品的買價都不升高(疊滿折扣時還更低);沒有盜賊加成者價格與舊式逐位元組同。
    2 一般貨仍守 R223:賣價(sell / 行情 / 銷贓)< 最低買價 ≤ 買價;fence_clean ≥ sell;黑市買價 > 一般銷贓價;
      含「公會加成 × 滯銷行情(f<1)」(審查反例:f<1 分支原本沒夾限)。
    3 贓物例外:贓物價 ≥ 一般銷贓價、封頂 底價 ×(1.20 + 0.5 × min(溢出, 0.40));議價越高的盜賊贓物收入不再下降(單調不減)。
    4 銷贓報價單一出處 fence_quote:贓物先出、報價 = 實收 = 選單 / 確認句;mark_stolen 只有 crime / housing / party / inventory 呼叫。
  B 行竊衰減
    5 n = 0 逐位元組同舊(機率與 rng 序列);n > 0 得手率 = 舊 × 0.93 ** n;得手與失手都記一次;店家重補貨(含投資落成)歸零;
      各店各記;壞存檔值夾限;期望得手上限 = p0 /(1 − 衰減)。
    6 真流程:行竊選單標籤的得手率 = 實擲機率(含極小機率顯示「<1%」);存讀檔往返。
  C 突變下會紅(衰減 1.0 / 失手不計 / 補貨不歸零 / 贓物不封頂 / 買價地板改回含公會加成 / 報價贓物後出)。
"""
import inspect
import io
import itertools
import math
import pathlib
import re

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

import sim_economy as E
from tesrpg import main as M
from tesrpg.models.character import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import crime, factions, inventory, world

gd = E.gd
STACK = dict(E.MAXED, thieves=E.TOP_THIEF, fighters=E.TOP_FIGHTER, infamy=50, fame=700, blessing=True, pact=True)
_ITEMS = ["ebony_sword", "ruby", "iron_ingot", "healing_potion", "leather_cuirass", "gold_ring", "iron_sword", "filled_grand_soul_gem", "lockpick"]


def _grid():
    for merc, pers, thieves, fighters, infamy, fame, bl, pact in itertools.product(
            (5, 50, 100), (40, 100), (None, E.TOP_THIEF), (None, E.TOP_FIGHTER), (0, 50), (0, 700), (False, True), (False, True)):
        yield E.make_char(merc, pers, thieves=thieves, fighters=fighters, infamy=infamy, fame=fame, blessing=bl, pact=pact)


def _without_thieves(c):
    c2 = Character.from_dict(dict(c.to_dict()))
    c2.factions = {k: v for k, v in c.factions.items() if k != "thieves_guild"}
    return c2


# --- A1 買價不被盜賊加成拖高 ---------------------------------------------------
def test_joining_the_thieves_guild_never_raises_a_buy_price():
    for c in _grid():
        if factions.sell_bonus(c, gd) <= 0:
            continue
        plain = _without_thieves(c)
        for iid in (i for i in _ITEMS if i != "lockpick"):                     # 開鎖器:會員免 ×2 外人加價,是另一項公會福利
            assert world.buy_price(c, gd, iid) == world.buy_price(plain, gd, iid), (iid, c.skills["mercantile"])   # 完全相同(買價與公會加成無關)
            assert world.min_buy_price(c, gd, iid) == world.min_buy_price(plain, gd, iid)
            assert world.base_sell_price(c, gd, iid) == world.base_sell_price(plain, gd, iid)


def test_stacked_thief_golden_prices():
    c = E.make_char(**STACK)
    got = {i: (world.buy_price(c, gd, i), world.sell_price(c, gd, i), world.fence_sell_price(c, gd, i),
               world.fence_stolen_price(c, gd, i)) for i in ("ebony_sword", "ruby", "iron_ingot")}
    # 買價 = 基準賣價 + 1(軍械庫把武甲的買價壓到地板);賣價 / 一般銷贓價被夾光公會加成;贓物價吃到上限(底價 ×1.20)
    assert got == {"ebony_sword": (577, 576, 576, 864), "ruby": (47, 46, 46, 60), "iron_ingot": (19, 18, 18, 24)}, got
    free = E.make_char(**dict(E.MAXED, thieves=E.TOP_THIEF, infamy=50))      # 沒疊買價折扣:公會加成完整生效(同舊)
    assert (world.buy_price(free, gd, "ebony_sword"), world.sell_price(free, gd, "ebony_sword")) == (899, 778)


# --- A2 一般貨仍守 R223 --------------------------------------------------------
def test_clean_goods_keep_the_global_sell_below_buy_rule():
    n = 0
    for c in _grid():
        for iid in _ITEMS:
            sell, buy, mb = world.sell_price(c, gd, iid), world.buy_price(c, gd, iid), world.min_buy_price(c, gd, iid)
            fence, bm = world.fence_sell_price(c, gd, iid), world.black_market_price(c, gd, iid)
            assert sell < mb <= buy, (iid, sell, mb, buy)
            assert sell <= fence < mb, (iid, sell, fence, mb)
            assert bm > fence and bm >= buy, (iid, bm, fence)
            n += 1
    assert n >= 3000


def test_market_prices_stay_below_the_lowest_buy_price_even_for_guild_bonus_times_glut():
    """審查反例:公會加成 ×1.35 × 滯銷行情 ×0.9 ≈ ×1.215,原 f<1 分支沒夾限,可高於最低買價。"""
    for kw in (STACK, dict(E.MAXED, thieves=E.TOP_THIEF, fame=700, blessing=True, pact=True), dict(E.MAXED, thieves=E.TOP_THIEF)):
        c = E.make_char(**kw)
        for pid in gd.world_pulse:
            c.world_pulse_day[pid] = 0
        for loc in ("whiterun", "bruma", "alinor", "kvatch", "imperial_city"):
            for iid in E.POOL:
                shop = world.shop_sell_price(c, gd, iid, loc, 0)
                f = world.market_factor(c, gd, loc, iid, 0)
                assert 1 <= shop < world.min_buy_price(c, gd, iid), (kw, loc, iid)
                if f < 1.0:
                    assert shop <= world.sell_price(c, gd, iid)
                elif f > 1.0:
                    assert shop >= world.sell_price(c, gd, iid)
                else:
                    assert shop == world.sell_price(c, gd, iid)


# --- A3 贓物例外 ----------------------------------------------------------------
def test_stolen_goods_exception_bounds():
    for kw in (STACK, dict(STACK, nodes=True, charm=True), dict(E.MAXED, thieves=E.TOP_THIEF, infamy=50),
               dict(mercantile=5, personality=40, thieves=E.TOP_THIEF, infamy=50), dict(E.MAXED, infamy=50, fame=700)):
        c = E.make_char(**kw)
        ov = world.barter_overflow(c, gd)
        for iid in E.POOL:
            clean, stolen = world.fence_sell_price(c, gd, iid), world.fence_stolen_price(c, gd, iid)
            ceil_ = int(gd.item(iid)["value"] * (1.20 + 0.5 * min(ov, 0.40)))
            assert world.stolen_ceiling(c, gd, iid) == ceil_
            assert stolen >= clean                                           # 贓物價永不低於一般銷贓價
            assert stolen <= max(clean, ceil_), (iid, stolen, clean, ceil_)  # 贓物溢價封頂(一般價本來就更高時不降)
    c0, c1 = E.make_char(**STACK), E.make_char(**dict(STACK, nodes=True, charm=True))
    assert world.barter_overflow(c0, gd) == 0 and abs(world.barter_overflow(c1, gd) - 0.48) < 1e-9
    assert world.stolen_ceiling(c0, gd, "ebony_sword") == 864 and world.stolen_ceiling(c1, gd, "ebony_sword") == 1007   # ×1.20 / ×1.40(溢出封頂 0.40)
    assert world.fence_stolen_price(c1, gd, "ebony_sword") > world.fence_stolen_price(c0, gd, "ebony_sword")            # 雙高盜賊:溢出有去處


def test_higher_barter_thieves_never_earn_less_from_stolen_goods():
    """使用者要的「更高魅力與交易的盜賊更有優勢」:疊了買價折扣的盜賊,議價越高贓物銷贓收入不下降
    (一般貨的銷贓價受價差預算限制,會隨議價升高而擠壓 —— 見 R225 ④ 量測;贓物不受此限)。"""
    last = 0
    for m, p in ((5, 40), (25, 40), (50, 55), (75, 50), (100, 40), (100, 100)):
        c = E.make_char(m, p, thieves=E.TOP_THIEF, infamy=50, fame=700, pact=True, blessing=True)
        total = sum(world.fence_stolen_price(c, gd, i) for i in E.POOL)
        # 容許 1% 的取整誤差:交叉點附近一般銷贓價(如 867)可能比贓物上限(864)高幾金,議價再高一點時回到上限;
        # 舊行為(贓物同受買價折扣夾限)則是下降約 10%(12.2 萬 → 10.9 萬)
        assert total >= last * 0.99, (m, p, total, last)
        last = max(last, total)


# --- A4 銷贓報價 / 贓物來源 ------------------------------------------------------
def _thief_with_loot(stolen=2, clean=3, iid="ebony_sword"):
    c = E.make_char(**STACK)
    c.inventory = []
    inventory.add_item(c, iid, stolen + clean)
    inventory.mark_stolen(c, iid, stolen)
    return c


def test_fence_quote_sells_stolen_units_first_at_the_stolen_price():
    c = _thief_with_loot(2, 3)
    cp, hp = world.fence_sell_price(c, gd, "ebony_sword"), world.fence_stolen_price(c, gd, "ebony_sword")
    assert hp > cp
    for qty, hot in ((1, 1), (2, 2), (3, 2), (5, 2)):
        q = world.fence_quote(c, gd, "ebony_sword", qty)
        assert q["hot"] == hot and q["total"] == hot * hp + (qty - hot) * cp and (q["hot_price"], q["clean_price"]) == (hp, cp)
    clean_only = _thief_with_loot(0, 3)
    assert world.fence_quote(clean_only, gd, "ebony_sword", 3)["total"] == 3 * cp and world.fence_quote(clean_only, gd, "ebony_sword", 3)["hot"] == 0


def test_mark_stolen_is_only_called_by_the_known_sources():
    """贓物只能從行竊得來(counsel:新增任何 mark_stolen 呼叫端都是贓物溢價的漏洞)。"""
    root = pathlib.Path(__file__).resolve().parent.parent / "tesrpg"
    callers = sorted(str(p.relative_to(root)) for p in root.rglob("*.py") if re.search(r"\bmark_stolen\(", p.read_text(encoding="utf-8")))
    assert callers == ["systems/crime.py", "systems/housing.py", "systems/inventory.py", "systems/party.py"], callers


class _Script:
    def __init__(self, picks, qty=1):
        self.picks, self.qty, self.menus, self.confirms, self.msgs = list(picks), qty, [], [], []

    def menu(self, title, options, allow_back=False, **kw):
        self.menus.append((title, options))
        return self.picks.pop(0) if self.picks else None

    def confirm(self, prompt, *a, **kw):
        self.confirms.append(prompt)
        return True

    def ask_int(self, prompt, default, lo, hi, **kw):
        self.prompts = getattr(self, "prompts", []) + [prompt]
        return min(hi, max(lo, self.qty))

    def message(self, text, **kw):
        self.msgs.append(text)


def _drive(fn, state, script):
    real = (ui.menu, ui.confirm, ui.ask_int, ui.message)
    ui.menu, ui.confirm, ui.ask_int, ui.message = script.menu, script.confirm, script.ask_int, script.message
    try:
        fn(state, gd)
    finally:
        ui.menu, ui.confirm, ui.ask_int, ui.message = real


def test_real_fence_flow_label_prompt_and_payout_agree():
    for stolen, clean, qty in ((2, 3, 4), (0, 3, 2), (3, 0, 3), (1, 0, 1)):
        c = _thief_with_loot(stolen, clean)
        c.gold = 0
        st = GameState(player=c, rng=RNG(seed=1), game_mode="adventure")
        script = _Script(["sell", "ebony_sword"], qty=qty)
        _drive(M.action_fence, st, script)
        q = world.fence_quote(_thief_with_loot(stolen, clean), gd, "ebony_sword", qty)
        label = next(o[1] for o in script.menus[1][1] if o[0] == "ebony_sword")
        if stolen:
            assert f"贓物 {q['hot_price']} 金(×{stolen})" in label and f"一般 {q['clean_price']} 金" in label, label
        else:
            assert f"銷 {q['clean_price']} 金" in label and "贓物" not in label, label
        assert c.gold == q["total"], (c.gold, q)                                   # 實收 = 報價
        paid = [m for m in script.msgs if "銷出" in m]
        assert paid and f"得 {q['total']} 金" in paid[0] and (f"贓物 {q['hot']} 件" in paid[0]) == bool(q["hot"]), paid


# --- B 行竊衰減 ---------------------------------------------------------------
def _old_steal_chance(c, iid):
    from tesrpg.systems import mastery, spellfx
    base = (0.25 + c.skill("sneak") * 0.005 + c.skill("security") * 0.003
            + mastery.theft_bonus(c, gd).get("steal_bonus", 0.0) + spellfx.charm_steal_bonus(c))
    base -= min(0.35, (gd.item(iid).get("weight", 0) or 0) * 0.015)
    return max(0.05, min(0.95, base))


def _thief_char(sneak=100, security=100, loc="whiterun"):
    c = E.make_char(**STACK)
    c.skills.update(sneak=sneak, security=security)
    c.location_id = loc
    return c


def test_decay_is_identical_to_the_old_chance_when_nothing_was_stolen_yet():
    for sneak, sec in ((5, 5), (40, 30), (60, 50), (100, 100)):
        c = _thief_char(sneak, sec)
        for iid in _ITEMS:
            assert crime.steal_chance(c, gd, iid) == _old_steal_chance(c, iid), (sneak, iid)
        assert crime.steal_chance(c, gd) == crime.steal_chance(c, gd, None)
    # rng 序列:同種子下,新 steal_item 的得手與否 = 舊式「先擲一次 chance」的結果(n = 0)
    for seed in range(60):
        c = _thief_char(60, 50)
        a = crime.steal_item(c, gd, "ruby", RNG(seed=seed))["ok"]
        b = RNG(seed=seed).chance(_old_steal_chance(_thief_char(60, 50), "ruby"))
        assert a == b, seed


class _FixedRng:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def chance(self, p):
        self.calls.append(p)
        return self.outcome


def test_each_attempt_decays_the_next_one_and_failures_count_too():
    g = crime.SHOP_THEFT_DECAY
    for outcome in (True, False):                                            # 得手與失手都記一次
        c = _thief_char()
        p0 = _old_steal_chance(c, "ruby")
        rng = _FixedRng(outcome)
        for n in range(6):
            assert crime.theft_count(c, "whiterun") == n
            assert crime.steal_chance(c, gd, "ruby") == p0 * g ** n if n else crime.steal_chance(c, gd, "ruby") == p0
            crime.steal_item(c, gd, "ruby", rng)
            assert rng.calls[-1] == (p0 * g ** n if n else p0)               # 實擲用的機率 = 預覽的機率(先擲、後記次數)
        assert crime.theft_count(c, "whiterun") == 6 and len(rng.calls) == 6
    c = _thief_char()
    crime.steal_item(c, gd, "ruby", _FixedRng(True))
    c.location_id = "bruma"                                                  # 別的店:各記各的
    assert crime.theft_count(c, "bruma") == 0 and crime.steal_chance(c, gd, "ruby") == _old_steal_chance(c, "ruby")


def test_expected_successes_per_window_have_a_hard_ceiling():
    """失手也計次 → 不論賞金能不能規避,期望得手數 ≤ p0 /(1 − 衰減)(只計得手的話,失手不痛不癢的小偷可無限重試)。"""
    g = crime.SHOP_THEFT_DECAY
    c = _thief_char()
    p0 = crime.steal_chance(c, gd, "ruby")
    total = 0.0
    for n in range(3000):
        c.shop_thefts["whiterun"] = n
        total += crime.steal_chance(c, gd, "ruby")
    assert total <= p0 / (1 - g) + 1e-9 and total > 0.99 * p0 / (1 - g)
    assert p0 / (1 - g) < 14                                                 # 滿級小偷單一貨品:期望得手 ≤ 14 件


def test_theft_count_resets_when_the_shop_restocks_and_is_per_shop():
    c = _thief_char()
    st = GameState(player=c, rng=RNG(seed=1), game_mode="adventure")
    world.ensure_stock(c, gd, "whiterun", st.time, st.rng)
    world.ensure_stock(c, gd, "bruma", st.time, st.rng)
    c.shop_thefts.update(whiterun=5, bruma=3)
    world.ensure_stock(c, gd, "whiterun", st.time, st.rng)                   # 還沒到補貨時點 → 不歸零
    assert c.shop_thefts == {"whiterun": 5, "bruma": 3}
    st.time.advance(world.RESTOCK_HOURS + 1)
    world.ensure_stock(c, gd, "whiterun", st.time, st.rng)                   # 真的重補 → 只有該店歸零
    assert c.shop_thefts == {"bruma": 3}
    c.gold = 10 ** 6
    world.invest_shop(c, gd, "bruma")                                        # 投資落成清補貨時點 → 重補 → 歸零
    world.ensure_stock(c, gd, "bruma", st.time, st.rng)
    assert c.shop_thefts == {}


def test_bad_saved_theft_counts_are_clamped():
    c = _thief_char()
    for raw, want in ((3, 3), (0, 0), (-4, 0), (10 ** 9, crime.THEFT_COUNT_MAX), ("2", 2), ("x", 0), (None, 0), (2.9, 2),
                      ([], 0), (float("inf"), 0), (float("-inf"), 0), (float("nan"), 0), (True, 1)):
        c.shop_thefts = {"whiterun": raw}
        assert crime.theft_count(c, "whiterun") == want, raw
        assert 0 <= crime.steal_chance(c, gd, "ruby") <= 0.95
    c.shop_thefts = "junk"
    assert crime.theft_count(c, "whiterun") == 0 and crime.steal_chance(c, gd, "ruby") == _old_steal_chance(c, "ruby")


def test_save_round_trip_and_old_saves():
    c = _thief_char()
    c.shop_thefts = {"whiterun": 4}
    d = c.to_dict()
    assert d["shop_thefts"] == {"whiterun": 4} and Character.from_dict(dict(d)).shop_thefts == {"whiterun": 4}
    old = dict(d)
    old.pop("shop_thefts")
    assert Character.from_dict(old).shop_thefts == {}
    bad = dict(d)
    bad["shop_thefts"] = ["junk"]
    assert Character.from_dict(bad).shop_thefts == {}


# --- B6 真流程 ------------------------------------------------------------------
def test_real_steal_flow_label_equals_the_real_chance_and_shows_the_wariness():
    c = _thief_char()
    c.gold = 10
    st = GameState(player=c, rng=RNG(seed=7), game_mode="adventure")
    world.ensure_stock(c, gd, "whiterun", st.time, st.rng)
    iid = next(i for i in world.in_stock_items(c, gd, "whiterun") if gd.item(i)["value"] > 5)
    c.shop_stock["whiterun"][iid] = 50                                       # 庫存足夠,不會因為偷空而少了選單列
    script = _Script([])
    real = (ui.menu, ui.message)
    ui.menu, ui.message = script.menu, script.message
    try:
        for _ in range(12):                                                  # 一次行竊後會回到商店主選單 → 逐次送入「行竊 → 這件 → 離開」
            script.picks = ["steal", f"{M._STEAL_KEY}{iid}", None]
            M.action_shop(st, gd)
    finally:
        ui.menu, ui.message = real
    labels = []
    for title, options in script.menus:
        for key, label, *_ in options:
            if key == f"{M._STEAL_KEY}{iid}":
                labels.append(label)
    shown = [re.search(r"得手 (<1|\d+)%", lb).group(1) for lb in labels]
    assert len(shown) >= 5
    nums = [int(x) if x != "<1" else 0 for x in shown]
    assert nums == sorted(nums, reverse=True) and nums[0] > nums[-1]         # 每次下手後標籤的得手率下降
    titles = [t for t, _o in script.menus if t.startswith("行竊哪件")]
    assert "店家已有戒心" not in titles[0] and any("店家已有戒心" in t for t in titles[1:])
    assert crime.theft_count(c, "whiterun") == len(labels)
    # 極小機率顯示「<1%」而不是「0%」
    c.shop_thefts["whiterun"] = 80
    assert 0 < crime.steal_chance(c, gd, iid) < 0.005 and "得手 <1%" in M._steal_option_label(c, gd, iid, 1)
    c.shop_thefts["whiterun"] = 0
    assert f"得手 {ui.pct(crime.steal_chance(c, gd, iid))}%" in M._steal_option_label(c, gd, iid, 1)


# --- C 突變 ---------------------------------------------------------------------
def _swap(obj, name, value, probes):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        for probe in probes:
            probe()
    except Exception:                                  # 斷言失敗或除以零等:守衛有咬到(突變沒有被悄悄吞掉)
        return False
    finally:
        setattr(obj, name, old)
    return True


def test_guards_fail_under_mutation():
    assert not _swap(crime, "SHOP_THEFT_DECAY", 1.0, (test_each_attempt_decays_the_next_one_and_failures_count_too,
                                                      test_expected_successes_per_window_have_a_hard_ceiling))
    assert not _swap(world, "STOLEN_CEIL_BASE", 1.6, (test_stolen_goods_exception_bounds, test_stacked_thief_golden_prices))
    assert not _swap(world, "STOLEN_CEIL_PER_OVERFLOW", 0.0, (test_stolen_goods_exception_bounds,))
    # 失手不計次
    real = crime.steal_item

    def _no_fail_count(char, gamedata, item_id, rng):
        before = dict(char.shop_thefts)
        r = real(char, gamedata, item_id, rng)
        if not r["ok"]:
            char.shop_thefts = before
        return r
    assert not _swap(crime, "steal_item", _no_fail_count, (test_each_attempt_decays_the_next_one_and_failures_count_too,))
    # 買價地板改回含公會加成的名目賣價(舊行為:盜賊頂階抬高買價)
    old_floor = world.base_sell_price
    assert not _swap(world, "base_sell_price", lambda char, gamedata, iid: world.nominal_sell_price(char, gamedata, iid),
                     (test_joining_the_thieves_guild_never_raises_a_buy_price, test_stacked_thief_golden_prices))
    assert world.base_sell_price is old_floor
    # 報價:贓物後出
    real_quote = world.fence_quote

    def _clean_first(char, gamedata, iid, qty):
        q = real_quote(char, gamedata, iid, qty)
        hot = max(0, min(qty - (inventory.count_item(char, iid) - inventory.stolen_on_person(char, iid)), q["hot"]))
        return dict(q, hot=hot, total=hot * q["hot_price"] + (qty - hot) * q["clean_price"])
    assert not _swap(world, "fence_quote", _clean_first, (test_fence_quote_sells_stolen_units_first_at_the_stolen_price,))
    # 補貨不歸零
    real_ensure = world.ensure_stock

    def _no_reset(char, gamedata, loc_id, time, rng):
        keep = dict(char.shop_thefts)
        real_ensure(char, gamedata, loc_id, time, rng)
        char.shop_thefts = keep
    assert not _swap(world, "ensure_stock", _no_reset, (test_theft_count_resets_when_the_shop_restocks_and_is_per_shop,))


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_thief_r225 OK")
