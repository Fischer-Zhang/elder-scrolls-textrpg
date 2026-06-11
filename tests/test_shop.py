"""商店庫存(Skyrim 式:有限數量 + 定時補貨 + 補貨品項有變化)回歸測試。

守住「買廉價材料 → 煉製 → 高價賣回」的無限金幣套利:供給有限 + 補貨有時間閘
→ 一輪只買得到有限的量,套利被供給與時間掐住。
"""

import json

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import world


def _setup():
    gd = get_gamedata()
    c = build_character(gd, name="商", sex="male", race="imperial",
                        birthsign="warrior", class_id="thief")
    return gd, c, c.location_id   # 起始於布魯瑪(有 merchant_stock)


def test_stock_initializes_finite():
    gd, c, loc = _setup()
    assert world.merchant_catalog(gd, loc)                 # 起始城有商人目錄
    t = GameTime()
    world.ensure_stock(c, gd, loc, t, RNG(1))
    assert loc in c.shop_stock and loc in c.shop_restock_at
    qtys = c.shop_stock[loc]
    assert qtys and all(0 <= q <= 6 for q in qtys.values())     # 有限且在補貨上限內
    assert c.shop_restock_at[loc] == t.absolute_hours() + world.RESTOCK_HOURS


def test_buy_depletes_and_sells_out():
    gd, c, loc = _setup()
    world.ensure_stock(c, gd, loc, GameTime(), RNG(1))
    item = world.in_stock_items(c, gd, loc)[0]
    q0 = world.stock_qty(c, loc, item)
    assert q0 > 0
    world.take_stock(c, loc, item, q0)                     # 全買光
    assert world.stock_qty(c, loc, item) == 0
    assert item not in world.in_stock_items(c, gd, loc)    # 售罄不再上架
    world.take_stock(c, loc, item)                         # 再扣不會變負
    assert world.stock_qty(c, loc, item) == 0


def test_restock_after_timer():
    """雙向時間閘:補貨時點前(R-1 小時)不補貨,到時點後重新有貨並重設下次時點。"""
    gd, c, loc = _setup()
    t = GameTime()
    world.ensure_stock(c, gd, loc, t, RNG(1))
    for it in list(c.shop_stock[loc]):
        world.take_stock(c, loc, it, 999)                  # 全部清空
    assert not world.in_stock_items(c, gd, loc)
    # 閘前:推進到補貨時點前一小時,進店不補貨(全清後仍全空,比只查單一品項更強)
    t.advance(world.RESTOCK_HOURS - 1)
    world.ensure_stock(c, gd, loc, t, RNG(2))              # 走早退分支不觸 rng,種子無關
    assert not world.in_stock_items(c, gd, loc)            # 未到時點 → 仍空
    # 閘後:再 +1(累進共 RESTOCK_HOURS),到補貨時點重新有貨並重設下次時點
    t.advance(1)
    world.ensure_stock(c, gd, loc, t, RNG(7))
    assert world.in_stock_items(c, gd, loc)                # 重新有貨
    assert c.shop_restock_at[loc] == t.absolute_hours() + world.RESTOCK_HOURS


def test_save_roundtrip_and_backward_compat():
    gd, c, loc = _setup()
    world.ensure_stock(c, gd, loc, GameTime(), RNG(1))
    world.take_stock(c, loc, world.in_stock_items(c, gd, loc)[0], 1)
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.shop_stock == c.shop_stock and loaded.shop_restock_at == c.shop_restock_at
    # 舊存檔缺此二欄 → dataclass 預設空 dict,首訪自動初始化、不崩
    d = c.to_dict()
    del d["shop_stock"]; del d["shop_restock_at"]
    old = Character.from_dict(d)
    assert old.shop_stock == {} and old.shop_restock_at == {}
    world.ensure_stock(old, gd, loc, GameTime(), RNG(1))
    assert loc in old.shop_stock


def test_shop_buy_smoke_depletes_stock():
    """煙霧:實跑 action_shop 購買,庫存確實扣減。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c, loc = _setup()
    c.gold = 9999
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    world.ensure_stock(c, gd, loc, state.time, state.rng)
    item = world.in_stock_items(c, gd, loc)[0]
    q0 = world.stock_qty(c, loc, item)
    saved = (ui.menu, ui.message, ui.show_events)
    seq = iter(["buy", item, None])
    ui.menu = lambda *a, **k: next(seq, None)
    ui.message = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None
    try:
        M.action_shop(state, gd)
    finally:
        ui.menu, ui.message, ui.show_events = saved
    assert world.stock_qty(c, loc, item) == q0 - 1


def run():
    test_stock_initializes_finite()
    test_buy_depletes_and_sells_out()
    test_restock_after_timer()
    test_save_roundtrip_and_backward_compat()
    test_shop_buy_smoke_depletes_stock()


if __name__ == "__main__":
    run()
    print("test_shop 全通過")
