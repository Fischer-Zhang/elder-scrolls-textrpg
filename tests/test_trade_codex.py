"""圖鑑「買賣、議價與行情」(trade_economy)的事實守衛 —— R227 後續(使用者「補」:圖鑑與 README 原本完全沒講議價 / 投資商店 / 行情 / 溢出折抵)。

R60 / R227 文字對帳的教訓:沒有數字守衛的策展文字會悄悄漂移。這個主題的每個數字都從真實常數 / 資料算出來比對,
里程碑名稱必須真的存在於 mastery.json;常數或資料變了、文字沒跟 → 紅燈。
"""
import json
import pathlib
import statistics as S

from tesrpg import formulas
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import divines, housing, renown, world

import sim_economy as E

gd = get_gamedata()
ROOT = pathlib.Path(__file__).resolve().parent.parent


def _topic_text():
    entry = gd.codex["trade_economy"]
    return "\n".join(str(v) for sec in entry["sections"] for v in sec.values())


def _readme():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def _pct(x):
    return f"{round(x * 100)}%"


def test_topic_exists_and_sits_between_crime_and_services_directory():
    e = gd.codex["trade_economy"]
    assert e["title"] == "買賣、議價與行情"
    assert gd.codex["crime_bounty"]["order"] < e["order"] < gd.codex["services_directory"]["order"]


def test_price_formula_numbers_equal_the_real_constants():
    t = _topic_text()
    b = world
    assert f"÷ {int(b.BARTER_SKILL_DIVISOR)}" in t and f"魅力 × {b.BARTER_ATTR_WEIGHT}" in t
    assert f"最高 {b.BARTER_CAP}" in t
    assert f"底價 × ({b.BUY_BASE_MULT} − 議價係數)" in t
    assert f"最低 {b.BUY_BASE_MULT - b.BARTER_CAP:.1f} 倍" in t
    assert f"底價 × ({b.SELL_BASE_MULT} + 議價係數 × {b.SELL_BARTER_MULT})" in t
    assert f"最高 {b.SELL_BASE_MULT + b.BARTER_CAP * b.SELL_BARTER_MULT:.1f} 倍" in t
    # 新手(交易 5 魅力 40)的實際倍率:文字寫「約 2.0 倍 / 約 0.4 倍」
    novice = E.make_char(mercantile=5, personality=40)
    d = world._disposition_factor(novice, gd)
    assert round(b.BUY_BASE_MULT - d, 1) == 2.0 and round(b.SELL_BASE_MULT + d * b.SELL_BARTER_MULT, 1) == 0.4
    assert "新手約 2.0 倍" in t and "新手約 0.4 倍" in t
    # 交易 100 + 魅力 100 真的頂到上限
    maxed = E.make_char(**E.MAXED)
    assert world._disposition_factor(maxed, gd) == b.BARTER_CAP


def test_milestone_names_and_values_exist_in_the_data():
    t = _topic_text()
    opts = {o["name"]: o for n in gd.mastery for o in n["options"]}
    for name in ("議價入門", "精算買賣", "行商人脈", "頂級議價", "八面玲瓏", "口才入門", "魅惑交易", "懾心術"):
        assert name in opts and name in t, name
    node = {n["id"]: [o["name"] for o in n["options"]] for n in gd.mastery}          # 哪些是二選一、哪些自動取得
    assert len(node["mercantile_25"]) == 1 and len(node["speechcraft_25"]) == 1
    assert len(node["mercantile_50"]) == len(node["mercantile_100"]) == len(node["illusion_75"]) == 2
    assert f"魅力 +{opts['八面玲瓏']['attr']['personality']}" in t and f"議價 +{opts['頂級議價']['disposition_bonus']:.2f}" in t
    assert f"議價 +{opts['精算買賣']['disposition_bonus']}" in t
    assert f"補貨量 ×{opts['行商人脈']['restock_mult']}" in t


def test_discount_and_markup_numbers_equal_the_real_constants():
    t = _topic_text()
    assert " / ".join(map(str, renown.FAME_THRESHOLDS)) in t and " / ".join(map(str, renown.INFAMY_SOCIAL_THRESHOLDS)) in t
    assert f"買價 −{_pct(renown.PRICE_FAME_DISCOUNT_PER_TIER)}" in t and f"最多 −{_pct(renown.PRICE_DISCOUNT_CAP)}" in t
    assert f"每階 +{_pct(renown.PRICE_INFAMY_MARKUP_PER_TIER)}" in t and f"最多 +{_pct(renown.PRICE_MARKUP_CAP)}" in t
    blessed = E.make_char(blessing=True)
    assert f"買價 −{_pct(1 - divines.buy_price_factor(blessed))}" in t                # 澤尼薩爾祝福
    assert f"買價 −{_pct(housing.TRADE_PACT_DISCOUNT)}" in t                           # 在地商誼
    assert f"貴 {int(world.LOCKPICK_OUTSIDER_MARKUP)} 倍" in t                         # 開鎖器非會員加價


def test_market_numbers_equal_the_real_constants_and_data():
    t = _topic_text()
    assert f"+{_pct(world.MARKET_FAVORED_MULT - 1)}" in t and f"−{_pct(1 - world.MARKET_GLUTTED_MULT)}" in t
    pulses = []

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("market"), dict) and "mult" in o["market"]:
                pulses.append(o["market"]["mult"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(gd.world_pulse)
    assert pulses and set(pulses) == {1.3} and "目前一律 +30%" in t                  # 全部脈動行情都是 ×1.3(不是「通常」)
    windows = set()

    def walk_w(o):
        if isinstance(o, dict):
            if isinstance(o.get("market"), dict):
                windows.add(o.get("active_window_days"))
            for v in o.values():
                walk_w(v)
        elif isinstance(o, list):
            for x in o:
                walk_w(x)
    walk_w(gd.world_pulse)
    assert windows == {8} and "約 8 天" in t, windows                                  # 行情聚光視窗 8 天
    assert "四方傳聞" in t and "節慶" not in t and "戰事" not in t                      # 脈動資料裡沒有節慶 / 戰事類(R227 查證:曾寫錯)
    st_char = E.make_char(**E.MAXED)
    prov_with_pref = next(p for p, v in gd.market["provinces"].items() if v.get("favored"))
    loc = next(lid for lid, d in gd.world["locations"].items() if d.get("province") == prov_with_pref and d.get("merchant_stock"))
    assert world.market_line(st_char, gd, loc, 0).startswith("本地商人收購行情")      # 「進商店時第一行會寫本地行情」


def test_restock_and_investment_numbers_equal_the_real_constants():
    t = _topic_text()
    assert f"每 {world.RESTOCK_HOURS // 24} 天補一次貨" in t
    one, two = world.SHOP_INVEST_TIERS
    assert f"『{one['name']}』{one['price']:,} 金" in t and f"『{two['name']}』{two['price']:,} 金" in t
    assert world.SHOP_INVEST_RESTOCK_MULT == 2 and "補貨量加倍" in t and "至少補兩件" in t
    assert world.SHOP_SUPPLY_TIER == 2                                                # 第二階才擴大目錄
    # 「每樣貨至少補兩件」:第一階 tier 1 最少 2 件
    assert min(world.shop_qty(q, 1, 1.0) for q in range(0, 8)) >= 2


def test_investing_tier_two_adds_nothing_in_the_province_capitals_and_names_match():
    """文字說「各省的省城本來就是大城,在那裡投資第二階不會多出新貨」—— 資料層守住這句話;空魂石用遊戲內名稱。"""
    for city in world.MAJOR_CITIES:
        assert world.merchant_catalog(gd, city, 2) == world.merchant_catalog(gd, city, 0), city
    t = _topic_text()
    assert f"{gd.item_name('empty_grand_soul_gem')}與{gd.item_name('empty_black_soul_gem').split('(')[0]}" in t
    assert "省城本來就是大城" in t


def test_service_rebate_numbers_equal_the_real_constants():
    t = _topic_text()
    per_tenth = world.SERVICE_REBATE_PER_OVERFLOW * 0.1
    assert f"溢出每 0.1 折 {_pct(per_tenth)}" in t
    assert f"最高 −{_pct(world.SERVICE_REBATE_CAP)}" in t
    assert f"溢出 {world.SERVICE_REBATE_CAP / world.SERVICE_REBATE_PER_OVERFLOW:g} 即頂到" in t


def test_readme_trade_bullet_matches_the_constants():
    r = _readme()
    b = world
    assert f"{b.BUY_BASE_MULT} − 議價係數" in r and f"{b.SELL_BASE_MULT} + 議價係數 × {b.SELL_BARTER_MULT}" in r
    assert f"最高 −{_pct(b.SERVICE_REBATE_CAP)}" in r
    one, two = b.SHOP_INVEST_TIERS
    assert f"{one['price']:,} / {two['price']:,} 金" in r
    assert f"+{_pct(b.MARKET_FAVORED_MULT - 1)} / −{_pct(1 - b.MARKET_GLUTTED_MULT)}" in r
    assert "買賣、議價與行情" in r
    assert "四方傳聞" in r and "脈動時另有" not in r                                    # 玩家看到的名稱是「四方傳聞」,不是「脈動」
    assert "偷來的贓物除外" in r                                                        # 贓物是明文例外(fence_stolen_price)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
