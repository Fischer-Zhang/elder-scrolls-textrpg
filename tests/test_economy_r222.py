"""R222 經濟量測 + 議價看得見(零機制:價格一個金幣都不能變)。

緣起:評估經濟系統時發現(1)議價係數與上限在介面上完全看不到,七個加成來源(合計 0.56)大半被上限 1.0 吃掉、
玩家無從得知;(2)金幣流動沒有任何量測工具。R222 只做「看得見」與「量得到」,不改任何價格。

守衛:
  1. 價格不變:重構後的 buy_price / sell_price / 議價係數,與凍結在本檔的舊式逐一相等(格點 × 物品);另附黃金值
     (對帳型測試抓不到共用函式內部漂移,R202 教訓)。
  2. 預覽 = 實價:`world.barter_breakdown` 的係數、來源、倍率都取自價格函式用的同一條鏈;顯示的倍率 × 底價 = 實際價格
     (差距 ≤ 1 金的取整);折扣疊到低於賣價時,顯示的買價倍率跟著地板抬高。
  3. 上限遮蔽看得見:超出上限的量如實列出(wasted)、商店標題標「已達上限」。
  4. 單一出處:銷贓價 / 黑市買價只有 world.fence_sell_price / black_market_price 一份,main.action_fence 不得自帶算式。
  5. 介面:角色卡 view-model 有議價列與分解提示;商店標題帶議價一句話(真流程 action_shop)。
  6. 量測腳本:同店 / 黑市倒掛恆為 0(硬斷言);跨攤位套利為已知現況(R223 修掉後改斷言為 0);物品池不重複;
     任務金幣含執行時生成的領主委託。
  7. 影刃說明的倍率與資料一致(原寫 ×1.5,R70 起實際 ×1.2)。
  8. 上述守衛在突變下會紅(就地突變:改上限 / 改賣價係數 / 銷贓價漏加成 / 分解漏一項 / 拿掉同店地板)。
  9. check.sh 的「動到相關檔就跑 sim」偵測在 pipefail + 有未追蹤新檔時不得漏判(舊寫法會靜默不跑 sim)。
"""
import inspect
import io
import itertools

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

import sim_economy as E
from tesrpg import main as M
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import crime, divines, factions, housing, mastery, party, renown, spellfx, world

gd = E.gd
_ITEMS = ["ebony_sword", "ruby", "lockpick", "healing_potion", "iron_ingot", "daedric_sword", "iron_dagger",
          "leather_cuirass", "wheat", "filled_grand_soul_gem", "gold_ring", "steel_spear"]


# --- 凍結的舊式(R222 之前 world.py 的寫法,逐字抄;只用來對帳,不得改) ----------
def _old_disposition(c):
    base = (c.skill("mercantile") + c.attr("personality") * 0.5) / 150.0
    base += spellfx.charm_barter_bonus(c)
    base += mastery.merchant_bonus(c, gd)
    base += party.passive_capstone_factor(c, gd, "barter")
    return max(0.0, min(1.0, base))


def _old_sell(c, iid):
    base = gd.item(iid)["value"] * (0.3 + _old_disposition(c) * 0.5)
    base *= 1 + factions.sell_bonus(c, gd)
    return max(1, round(base))


def _old_buy(c, iid):
    item = gd.item(iid)
    price = item["value"] * (2.2 - _old_disposition(c))
    if iid == "lockpick" and not factions.is_member(c, "thieves_guild"):
        price *= 2.0
    if "damage" in item or "armor_rating" in item:
        price *= 1 - factions.armory_discount(c, gd)
    price *= renown.price_factor(c)
    price *= divines.buy_price_factor(c)
    price *= 1 - housing.province_discount(c, gd)
    return max(1, round(price), _old_sell(c, iid) + 1)


def _grid():
    for merc, pers, thieves, fighters, infamy, fame, extras in itertools.product(
            (5, 37, 75, 100), (30, 55, 100), (None, E.TOP_THIEF), (None, E.TOP_FIGHTER), (0, 50), (0, 700),
            ((False, False, False, False), (True, True, True, True))):
        blessing, pact, charm, nodes = extras
        yield E.make_char(merc, pers, thieves=thieves, fighters=fighters, infamy=infamy, fame=fame,
                          blessing=blessing, pact=pact, charm=charm, nodes=nodes)


def _prices_match_frozen_reference():
    n = 0
    for c in _grid():
        assert world._disposition_factor(c, gd) == _old_disposition(c)
        for iid in _ITEMS:
            assert world.buy_price(c, gd, iid) == _old_buy(c, iid), (iid, c.skills["mercantile"])
            assert world.sell_price(c, gd, iid) == _old_sell(c, iid), (iid, c.skills["mercantile"])
            n += 1
    return n


def _expect_fail(fn) -> bool:
    try:
        fn()
    except AssertionError:
        return True
    return False


# --- 1 價格不變 -------------------------------------------------------------
def test_prices_equal_frozen_pre_r222_formula_across_grid():
    assert _prices_match_frozen_reference() >= 4000


def test_golden_prices_and_multipliers():
    """黃金值(R222 落地當下的實際輸出):(買, 賣, 銷贓, 黑市買)。"""
    gold = {
        "novice": (dict(mercantile=5, personality=40),
                   {"ebony_sword": (1464, 276, 276, 1464), "ruby": (102, 19, 19, 102), "lockpick": (24, 2, 2, 24)}),
        "maxed": (dict(mercantile=100, personality=100),
                  {"ebony_sword": (864, 576, 576, 864), "ruby": (60, 40, 40, 60), "iron_ingot": (24, 16, 16, 24)}),
        "thief": (dict(mercantile=100, personality=100, thieves=E.TOP_THIEF, infamy=50),
                  {"ebony_sword": (899, 778, 1128, 1129), "ruby": (62, 54, 78, 79), "lockpick": (7, 6, 8, 9)}),
        "stacked": (dict(mercantile=100, personality=100, thieves=E.TOP_THIEF, fighters=E.TOP_FIGHTER,
                         infamy=50, fame=700, blessing=True, pact=True),
                    {"ebony_sword": (779, 778, 1128, 1129), "healing_potion": (44, 43, 62, 63)}),
        "mid": (dict(mercantile=37, personality=55, fame=150, charm=True),
                {"ebony_sword": (1144, 400, 400, 1144), "healing_potion": (64, 22, 22, 64)}),
    }
    for name, (kw, table) in gold.items():
        c = E.make_char(**kw)
        for iid, want in table.items():
            got = (world.buy_price(c, gd, iid), world.sell_price(c, gd, iid),
                   world.fence_sell_price(c, gd, iid), world.black_market_price(c, gd, iid))
            assert got == want, (name, iid, got, want)
    b = world.barter_breakdown(E.make_char(mercantile=37, personality=55, fame=150, charm=True), gd)
    assert (round(b["d"], 6), round(b["buy_goods"], 6), round(b["sell_all"], 6)) == (0.51, 1.5886, 0.555)
    b = world.barter_breakdown(E.make_char(mercantile=5, personality=40), gd)
    assert (round(b["d"], 6), round(b["buy_mult"], 6), round(b["sell_mult"], 6)) == (0.166667, 2.033333, 0.383333)


# --- 2 預覽 = 實價 ----------------------------------------------------------
def test_breakdown_shares_the_price_chain():
    for c in _grid():
        b = world.barter_breakdown(c, gd)
        assert b["d"] == world._disposition_factor(c, gd)
        assert abs(sum(r["value"] for r in b["rows"]) - b["raw"]) < 1e-9          # 各列相加 = 相加總和
        assert b["d"] == max(0.0, min(world.BARTER_CAP, b["raw"]))
        assert abs(b["wasted"] - max(0.0, b["raw"] - world.BARTER_CAP)) < 1e-12
        assert b["buy_mult"] == world.BUY_BASE_MULT - b["d"]
        assert b["sell_mult"] == world.SELL_BASE_MULT + b["d"] * world.SELL_BARTER_MULT
        for iid, key in (("ruby", "buy_goods"), ("gold_ring", "buy_goods"), ("ebony_sword", "buy_gear"),
                         ("leather_cuirass", "buy_gear")):
            v = gd.item(iid)["value"]
            sell = world.sell_price(c, gd, iid)
            assert abs(sell - max(1, round(v * b["sell_all"]))) <= 1, (iid, sell, v * b["sell_all"])
            want_buy = max(1, round(v * b[key]), sell + 1)
            assert abs(world.buy_price(c, gd, iid) - want_buy) <= 1, (iid, key)


def test_shown_buy_multiplier_follows_the_anti_arbitrage_floor():
    stacked = E.make_char(mercantile=100, personality=100, thieves=E.TOP_THIEF, fighters=E.TOP_FIGHTER,
                          infamy=50, fame=700, blessing=True, pact=True)
    b = ui._barter_shown(stacked, gd)
    assert b["buy_goods"] < b["sell_all"]                       # 折扣疊到比賣價還低(夾具有效性)
    assert b["buy_shown"] == b["sell_all"] and b["gear_shown"] == b["sell_all"]
    assert world.buy_price(stacked, gd, "ruby") == world.sell_price(stacked, gd, "ruby") + 1   # 實價:地板咬住
    assert "買價以賣價為底" in ui._barter_tip(stacked, gd)
    plain = ui._barter_shown(E.make_char(50, 40), gd)
    assert plain["buy_shown"] == plain["buy_goods"] > plain["sell_all"]
    assert "買價以賣價為底" not in ui._barter_tip(E.make_char(50, 40), gd)


# --- 3 上限遮蔽看得見 --------------------------------------------------------
def test_cap_masking_is_reported():
    rich = E.make_char(100, 100, nodes=True, charm=True)
    b = world.barter_breakdown(rich, gd)
    assert b["d"] == world.BARTER_CAP and b["raw"] > 1.4 and b["wasted"] > 0.4
    assert "已達上限" in ui.barter_line(rich, gd)
    assert "超出上限的 0.4" in ui._barter_tip(rich, gd)
    for _nid, _oid, name, value in E.BARTER_NODES:              # 每個已選的議價節點都列在分解裡
        assert any(r["label"] == name and r["value"] == value for r in b["rows"]), name
    assert any(r["key"] == "charm" and r["value"] == spellfx.CHARM_BARTER_BONUS for r in b["rows"])
    poor = E.make_char(5, 40)
    assert "已達上限" not in ui.barter_line(poor, gd) and "超出上限" not in ui._barter_tip(poor, gd)
    assert [r["key"] for r in world.barter_breakdown(poor, gd)["rows"]] == ["mercantile", "personality"]
    exact = world.barter_breakdown(E.make_char(100, 100), gd)   # 剛好頂到:已達上限、但沒有浪費
    assert exact["raw"] == 1.0 and exact["wasted"] == 0.0 and "已達上限" in ui.barter_line(E.make_char(100, 100), gd)


def test_merchant_bonus_sources_sum_to_the_bonus():
    for c in (E.make_char(100, 100, nodes=True), E.make_char(60, 40, nodes=True), E.make_char(5, 40)):
        src = mastery.merchant_bonus_sources(c, gd)
        assert sum(v for _n, v in src) == mastery.merchant_bonus(c, gd)
        assert all(name and v > 0 for name, v in src)
    assert len(mastery.merchant_bonus_sources(E.make_char(60, 40, nodes=True), gd)) == 4   # 交易 25/50 + 口才 25 + 幻術 75
    assert mastery.merchant_bonus_sources(E.make_char(5, 40), gd) == []


# --- 4 單一出處 -------------------------------------------------------------
def test_fence_and_black_market_prices_have_one_source():
    for c in _grid():
        for iid in _ITEMS:
            fence = world.fence_sell_price(c, gd, iid)
            assert fence == int(world.sell_price(c, gd, iid) * (1 + crime.fence_bonus(c)))
            assert world.black_market_price(c, gd, iid) == max(world.buy_price(c, gd, iid), fence + 1)
    src = inspect.getsource(M.action_fence)
    assert "world.fence_sell_price(" in src and "world.black_market_price(" in src
    assert "sell_price(char, gamedata, iid) *" not in src and "fsell(iid) + 1" not in src   # 不得自帶算式


# --- 5 介面 ---------------------------------------------------------------
def test_sheet_view_carries_barter_row_and_tip():
    c = E.make_char(75, 50, thieves=E.TOP_THIEF, fame=150, nodes=True)
    data = ui._sheet_view(c, gd)
    b = ui._barter_shown(c, gd)
    assert data["barter"] == f"買 ×{b['buy_shown']:.2f}　賣 ×{b['sell_all']:.2f}"
    tip = data["barter_tip"]
    assert tip.startswith(f"議價係數 {b['d']:.2f}(上限 1.00):交易 75 +0.50 · 魅力 50 +0.17")
    assert "公會使賣價再 ×1.35" in tip and "聲望、神恩、商誼使買價再 ×0.94" in tip
    assert "買價 = 底價 ×(2.2 − 係數),賣價 = 底價 ×(0.3 + 係數 × 0.5)" in tip
    fighter = E.make_char(50, 40, fighters=E.TOP_FIGHTER)
    assert "武器護甲買 ×" in ui._barter_tip(fighter, gd) and "武器護甲買 ×" not in ui._barter_tip(E.make_char(50, 40), gd)


def test_shop_title_shows_barter_line_in_the_real_flow():
    c = E.make_char(100, 100, nodes=True)
    c.location_id = "imperial_city"
    state = GameState(player=c, rng=RNG(seed=1), game_mode="adventure")
    titles = []
    real_menu = ui.menu
    ui.menu = lambda title, options, allow_back=False: (titles.append(title), None)[1]
    try:
        M.action_shop(state, gd)
    finally:
        ui.menu = real_menu
    assert titles and titles[0].startswith(f"商店(你有 {c.gold} 金幣 · 議價 1.00 已達上限:買 ×1.20、賣 ×0.80)")
    assert ui.barter_line(c, gd) in titles[0]


# --- 6 量測腳本 -------------------------------------------------------------
def test_scanner_hard_invariants_and_known_cross_vendor_hole():
    assert len(E.POOL) == len(set(E.POOL)) and all(gd.item(i)["value"] > 0 for i in E.POOL)
    rows = E.arbitrage_scan()
    assert len(rows) == len(E.PROFILES)
    for r in rows:
        assert r["same_shop"] == 0, r        # 同店買價恆 > 賣價(world.buy_price 的反套利鐵則)
        assert r["black_market"] == 0, r     # 黑市買價恆 > 銷贓價(R84)
        assert r["profit"] <= r["cross"] <= len(E.POOL)
    by = {r["label"]: r for r in rows}
    assert by["議價滿"]["cross"] == 0 and by["新手(交易 5·魅力 40)"]["cross"] == 0
    # 已知現況(handoff R110 記為既有):議價滿 + 盜賊公會頂階 + 惡名 50 時,商店買、銷贓賣有賺。
    # R223 加上全域「賣出價 < 買入價」規則後,把下面兩行改成 == 0。
    assert by["議價滿 + 盜賊公會頂階 + 惡名 50"]["profit"] > 150
    assert by["議價滿 + 惡名 50 + 聲望 700"]["profit"] > 100


def test_income_and_sink_measurements_run_on_real_data():
    inc = E.dungeon_income(seeds=2)
    assert len(inc) == len(gd.dungeons)
    gold, value = sum(g for _d, g, _v in inc.values()), sum(v for _d, _g, v in inc.values())
    assert 60_000 < gold < 140_000 and 200_000 < value < 450_000, (gold, value)   # 量級守衛(非平衡線)
    once, _rep = E.quest_gold()
    assert once["ruler"][0] > 100            # 含執行時生成的領主委託(只讀 quests.json 會漏掉)
    marks, total, level = E.buy_levels()
    assert marks[5] < marks[10] < marks[20] and total > 300_000 and level > 30
    assert E.train_total(5, 75) == sum(max(20, 8 * lv) for lv in range(5, 75))
    sk = E.sinks()
    assert sk["houses"] == sum(h["price"] for h in gd.houses.values()) and sk["masters"] == 12
    assert len(E.barter_sources()) == len(E.BARTER_NODES) + 2
    for merc, pers, d, buy, sell in E.barter_table():
        c = E.make_char(merc, pers)
        assert abs(world.buy_price(c, gd, "ruby") - round(50 * buy)) <= 1
        assert abs(world.sell_price(c, gd, "ruby") - round(50 * sell)) <= 1


# --- 7 影刃說明 -------------------------------------------------------------
def test_shadowblade_description_states_the_real_multiplier():
    opt = next(o for n in gd.mastery for o in n["options"] if o["opt_id"] == "shadowblade")
    assert f"×{1 + opt['mult_bonus']:g}" in opt["desc"], opt["desc"]      # 資料 0.2 → 說明須寫 ×1.2
    assert "×1.5" not in opt["desc"]


# --- 8 突變:守衛真的會紅 ------------------------------------------------------
def test_guards_bite_under_in_process_mutations():
    saved = world.BARTER_CAP
    world.BARTER_CAP = 0.9                                       # 突變 1:上限改掉
    try:
        assert _expect_fail(_prices_match_frozen_reference)
    finally:
        world.BARTER_CAP = saved
    saved = world.SELL_BARTER_MULT
    world.SELL_BARTER_MULT = 0.6                                 # 突變 2:賣價係數改掉
    try:
        assert _expect_fail(_prices_match_frozen_reference)
        assert _expect_fail(test_golden_prices_and_multipliers)
    finally:
        world.SELL_BARTER_MULT = saved
    real = world.fence_sell_price
    world.fence_sell_price = lambda c, g, i: world.sell_price(c, g, i)   # 突變 3:銷贓價漏掉加成
    try:
        assert _expect_fail(test_fence_and_black_market_prices_have_one_source)
        assert _expect_fail(test_golden_prices_and_multipliers)
        assert _expect_fail(test_scanner_hard_invariants_and_known_cross_vendor_hole)   # 掃描器看不到已知漏洞 = 空轉
    finally:
        world.fence_sell_price = real
    real = mastery.merchant_bonus_sources
    mastery.merchant_bonus_sources = lambda c, g: real(c, g)[1:]          # 突變 4:分解漏列一個來源
    try:
        assert _expect_fail(test_breakdown_shares_the_price_chain)
        assert _expect_fail(test_cap_masking_is_reported)
    finally:
        mastery.merchant_bonus_sources = real
    real = world.buy_price
    world.buy_price = lambda c, g, i: max(1, round(world._buy_chain(c, g, i, g.item(i))))   # 突變 5:拿掉同店地板
    try:
        assert _expect_fail(test_scanner_hard_invariants_and_known_cross_vendor_hole)
        assert _expect_fail(test_shown_buy_multiplier_follows_the_anti_arbitrage_floor)
    finally:
        world.buy_price = real
    assert _prices_match_frozen_reference() >= 4000              # 還原後仍綠(突變沒有殘留)


# --- 9 工具鏈:check.sh 的「動到相關檔就跑 sim」偵測 ---------------------------
def test_check_sh_change_detection_survives_pipefail_with_untracked_files():
    """R222 發現:check.sh 舊寫法 `{ git diff; git ls-files; } | grep -qE …` 在 `set -o pipefail` 下,只要有未追蹤新檔
    而且前段就命中,grep -q 先關管線 → 後段 git 寫入收到 SIGPIPE(141)→ 整條管線算失敗 → 被當成「沒動到相關檔」,
    sim 靜默不跑(本里程碑自己就中了:改了 world.py + 新增兩個檔,sim_conj / sim_economy 都沒跑)。
    修法:清單先收進變數,用 here-string 比對。本測試在暫存 git 倉庫裡重演該情境,直接執行 check.sh 裡那兩行。"""
    import pathlib
    import subprocess
    import tempfile

    text = (pathlib.Path(__file__).resolve().parent.parent / "check.sh").read_text(encoding="utf-8")
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    piped = [ln for ln in code if "| grep -q" in ln]            # 含 -q / -qE;判斷 ⚠ 的那幾行同理(輸出超過管線緩衝就會漏判)
    assert not piped, f"check.sh 又出現「管線接 grep -q」(pipefail 下會靜默漏判):{piped}"
    lines = [ln for ln in text.splitlines() if ln.startswith('CHANGED="$(') or ln.startswith("changed_matches() {")]
    assert len(lines) == 2, lines
    assert text.count("changed_matches '") >= 4          # 四段條件式 sim(刺客 / 召喚 / AI 戰爭 / 經濟)都走它

    with tempfile.TemporaryDirectory() as d:
        def git(*args):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                           cwd=d, check=True, capture_output=True, text=True)
        git("init", "-q")
        src = pathlib.Path(d, "tesrpg", "systems")
        src.mkdir(parents=True)
        (src / "world.py").write_text("a\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "init")
        (src / "world.py").write_text("b\n", encoding="utf-8")          # 已追蹤檔有改動(排在清單最前面)
        for i in range(300):                                            # 大量未追蹤新檔(排在清單後段)
            pathlib.Path(d, f"new_{i:03d}.txt").write_text("x", encoding="utf-8")

        fixed = ("set -uo pipefail\n" + "\n".join(lines)
                 + "\nchanged_matches 'tesrpg/systems/world\\.py' && echo HIT"
                 + "\nchanged_matches 'new_299\\.txt' && echo HIT_UNTRACKED"
                 + "\nchanged_matches 'no_such_file' || echo MISS\n")
        out = subprocess.run(["bash", "-c", fixed], cwd=d, capture_output=True, text=True)
        assert out.stdout.split() == ["HIT", "HIT_UNTRACKED", "MISS"], (out.stdout, out.stderr)

        old = ("set -uo pipefail\n{ git diff --name-only HEAD; git ls-files --others --exclude-standard; } 2>/dev/null"
               " | grep -qE 'tesrpg/systems/world\\.py' && echo HIT || echo SKIPPED\n")
        seen = {subprocess.run(["bash", "-c", old], cwd=d, capture_output=True, text=True).stdout.strip()
                for _ in range(5)}
        assert "SKIPPED" in seen, f"舊寫法在此情境下應會漏判(夾具要有鑑別力):{seen}"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_economy_r222 OK")
