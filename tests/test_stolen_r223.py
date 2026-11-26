"""R223 銷贓與贓物:全域「賣出價 < 買入價」規則 + 贓物標記 + 被捕沒收。

使用者裁決(2026-11-26):偷來的東西一般商店一律不收、只能銷贓(銷贓加成照舊);被衛兵逮到(繳罰金或入獄)沒收身上的贓物;
全域「任何攤位的賣出價都低於任何攤位的買入價」(夾賣出價、不抬買價)。
同款物品分不出哪件是偷的 → 只記件數,而且**各地方各記各的**(背包一個數、倉庫每一疊一個數、同伴身上每槽一個記號):
賣給商店只減持有數,持有數 = 贓物數時就不收;其餘離開背包的情況(用掉、丟掉、加工、銷贓、存倉庫、被沒收)一律**贓物先走**;
存入倉庫贓物先存、取出乾淨的先取。

守衛:
  1. 全域規則:任何角色、任何物品,銷贓價 < 該角色最低買價(`world.min_buy_price`,商誼以名下最好的計)≤ 當地買價;
     一般亡命徒的銷贓價不變(只在會追上買價時才被夾)。
  2. 行竊得手才標記;失手不標。
  3. 一般商店(真流程 action_shop):只列有乾淨件數的堆疊、可賣件數 = 背包 − 背包裡的贓物;賣乾淨的不動記錄;
     全是贓物時講清楚原因;贓物放在倉庫時不影響身上同款正當貨的買賣。
  4. 銷贓(真流程 action_fence):照收,贓物先出。
  5. 倉庫:存入贓物先存、取出乾淨的先取,件數跟著走(守恆、不洗白);真流程 _stash_transfer 的清單與訊息標出贓物。
  6. 同伴裝備:每槽自己記是不是贓物;交出去贓物先走、拿回來 / 換裝 / 離隊 / 載入修復都把記號帶回背包。
  7. 用掉、丟掉、加工:贓物先走;加工成別的東西 = 洗白。
  8. 新入手的不是贓物(含殘留的壞記錄也不會復活到新貨上)。
  9. 被捕沒收(crime.pay_fine / serve_sentence + 真流程 guard_confrontation):只收背包裡的贓物——倉庫與同伴身上的不搜、
     同款的正當貨不動;穿戴中的也收(並重算);付不起罰金 = 沒被捕 = 不沒收;選項上預告的件數 = 實際沒收的件數。
 10. 介面:物品標籤標出贓物。
 11. 存檔:往返保留(含倉庫各疊與同伴各槽)、舊檔缺欄 = 空、R223 第一版格式(全部算在同一個數)自動分配、壞值被清(冪等)。
 12. 以上在就地突變下會紅。
"""
import io
import itertools
import tempfile
from pathlib import Path

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

import sim_economy as E
from tesrpg import main as M
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import crime, housing, inventory, party, world

gd = E.gd
CITY = "imperial_city"


class _Lucky:
    """行竊必得手 / 必失手的假亂數(只用到 chance)。"""

    def __init__(self, ok: bool):
        self.ok = ok

    def chance(self, _p):
        return self.ok


def _thief(**kw):
    """空背包的量測角色(起手包的鐵劍 / 藥水 / 開鎖器清掉,測試才能完全掌握背包內容)。"""
    c = E.make_char(**kw)
    c.inventory, c.weapon, c.equipped = [], "fists", {}
    c.location_id = CITY
    c.gold = 1000
    return c


def _steal(c, item_id, n=1):
    for _ in range(n):
        assert crime.steal_item(c, gd, item_id, _Lucky(True))["ok"]


def _wanted(c, bounty=60):
    c.bounties = {crime.province_of(c, gd): bounty}
    return c


class _Script:
    """把 ui 的輸入原語換成腳本作答,記錄每個選單的選項與所有訊息;離開時還原。"""

    NAMES = ("menu", "ask_int", "confirm", "message", "show_events", "inventory_panel", "shop_panel")

    def __init__(self, answers, ints=()):
        self.answers, self.ints = list(answers), list(ints)
        self.menus, self.prompts, self.msgs = [], [], []

    def __enter__(self):
        self.saved = {n: getattr(ui, n) for n in self.NAMES}
        ui.menu = self._menu
        ui.ask_int = self._ask_int
        ui.confirm = lambda *_a, **_k: True
        ui.message = lambda text, *_a, **_k: self.msgs.append(text)
        ui.show_events = lambda *_a, **_k: None
        ui.inventory_panel = lambda *_a, **_k: None
        ui.shop_panel = lambda *_a, **_k: None
        return self

    def __exit__(self, *_exc):
        for n, fn in self.saved.items():
            setattr(ui, n, fn)

    def _menu(self, title, options, allow_back=False):
        self.menus.append((title, [k for k, _l in options], {k: lbl for k, lbl in options}))
        return self.answers.pop(0)

    def _ask_int(self, prompt, default=None, lo=None, hi=None):
        self.prompts.append((prompt, lo, hi))
        return self.ints.pop(0) if self.ints else default


def _state(c):
    return GameState(player=c, rng=RNG(seed=1), game_mode="adventure")


def _expect_fail(fn) -> bool:
    try:
        fn()
    except AssertionError:
        return True
    return False


# --- 1 全域規則 -------------------------------------------------------------
def _profiles():
    for merc, pers, thieves, fighters, infamy, fame, extras in itertools.product(
            (5, 50, 100), (40, 100), (None, E.TOP_THIEF), (None, E.TOP_FIGHTER), (0, 5, 20, 50), (0, 150, 700),
            ((False, False), (True, True))):
        yield E.make_char(merc, pers, thieves=thieves, fighters=fighters, infamy=infamy, fame=fame,
                          blessing=extras[0], pact=extras[1], nodes=True, charm=extras[0])


def test_no_vendor_pays_what_any_vendor_charges():
    n = 0
    for c in _profiles():
        for iid in E.POOL[::7]:
            shop, fence = world.sell_price(c, gd, iid), world.fence_sell_price(c, gd, iid)
            low, here = world.min_buy_price(c, gd, iid), world.buy_price(c, gd, iid)
            assert shop <= fence < low <= here, (iid, shop, fence, low, here)
            assert world.black_market_price(c, gd, iid) > fence
            n += 1
    assert n > 5000


def test_min_buy_price_uses_the_best_trade_pact_not_the_local_one():
    c = E.make_char(100, 100, infamy=50, fame=700, pact=True)      # 商誼房產在帝都(賽羅迪爾)
    c.location_id = "whiterun"                                     # 人在天際:當地買價沒有商誼折扣
    assert gd.location("whiterun")["province"] != gd.location(E.HOUSE_LOC)["province"]
    here, low, fence = (world.buy_price(c, gd, "ebony_sword"), world.min_buy_price(c, gd, "ebony_sword"),
                        world.fence_sell_price(c, gd, "ebony_sword"))
    assert (here, low, fence) == (795, 755, 754)                   # 在天際銷贓,也不得高過「回帝都買」的價
    c.location_id = E.HOUSE_LOC
    assert world.buy_price(c, gd, "ebony_sword") == 755            # 回到帝都真的買得到 755


def test_ordinary_outlaws_keep_their_fence_bonus():
    """只有銷贓價會追上買價的角色才被夾;一般亡命徒逐值同 R222(銷贓價 = int(賣價 ×(1 + 加價)))。"""
    for kw in (dict(mercantile=5, personality=40, infamy=50), dict(mercantile=50, personality=40, infamy=20),
               dict(mercantile=75, personality=50, thieves=E.TOP_THIEF, infamy=50), dict(mercantile=100, personality=100, infamy=50)):
        c = E.make_char(**kw)
        same = sum(world.fence_sell_price(c, gd, i) == int(world.sell_price(c, gd, i) * (1 + crime.fence_bonus(c)))
                   for i in E.POOL)
        assert same >= len(E.POOL) - 6, (kw, same)                 # 只有極便宜的幾樣因取整被夾 1 金
    c = E.make_char(50, 40, infamy=20)
    assert world.fence_sell_price(c, gd, "ebony_sword") == 499 == int(384 * 1.3)


# --- 2 行竊 ---------------------------------------------------------------
def test_theft_marks_only_on_success():
    c = _thief()
    assert not crime.steal_item(c, gd, "gold_ring", _Lucky(False))["ok"]
    assert c.stolen == {} and inventory.count_item(c, "gold_ring") == 0
    _steal(c, "gold_ring", 2)
    assert c.stolen == {"gold_ring": 2} and inventory.stolen_on_person(c, "gold_ring") == 2
    inventory.add_item(c, "gold_ring", 1)                          # 另外正當入手一枚
    assert (inventory.count_item(c, "gold_ring"), inventory.stolen_on_person(c, "gold_ring"),
            inventory.clean_count(c, "gold_ring")) == (3, 2, 1)


# --- 3 一般商店 -------------------------------------------------------------
def test_honest_shop_only_takes_clean_units_in_the_real_flow():
    c = _thief()
    _steal(c, "gold_ring", 2)
    _steal(c, "ruby", 1)
    inventory.add_item(c, "gold_ring", 3)                          # 3 枚乾淨的
    inventory.add_item(c, "iron_dagger", 1)
    gold0 = c.gold
    with _Script(["sell", "gold_ring", None, None], ints=[3]) as s:
        M.action_shop(_state(c), gd)
    sell_menu = next(m for m in s.menus if m[0].startswith("賣什麼"))
    assert "ruby" not in sell_menu[1] and "gold_ring" in sell_menu[1] and "iron_dagger" in sell_menu[1]
    assert "其中贓物 ×2" in sell_menu[2]["gold_ring"]
    prompt, lo, hi = s.prompts[0]
    assert (lo, hi) == (1, 3) and "共 3" in prompt and "另有 2 件贓物商人不收" in prompt
    assert inventory.count_item(c, "gold_ring") == 2 and inventory.stolen_on_person(c, "gold_ring") == 2
    assert c.gold > gold0                                           # 賣了 3 枚乾淨的
    assert c.stolen == {"gold_ring": 2, "ruby": 1}                 # 賣商店只減持有數,贓物數不動

    with _Script(["sell", "iron_dagger", None]) as s:              # 再賣掉僅剩的乾淨貨 → 持有數 = 贓物數,商人不收
        M.action_shop(_state(c), gd)
    assert any("剩下的都是贓物,商人不收" in m for m in s.msgs), s.msgs
    assert inventory.count_item(c, "gold_ring") == 2 and inventory.count_item(c, "ruby") == 1

    empty = _thief()
    with _Script(["sell", None]) as s:
        M.action_shop(_state(empty), gd)
    assert any(m == "沒有可賣的東西。" for m in s.msgs)             # 真的沒東西時維持原訊息


def test_stolen_goods_kept_at_home_do_not_taint_the_ones_you_carry():
    """各地方各記各的:贓物藏在倉庫時,身上同款的正當貨照常能賣、被捕也不會被收走。"""
    c = _wanted(_thief())
    c.houses_owned = [CITY]
    _steal(c, "gold_ring", 2)
    assert housing.deposit(c, gd, CITY, "gold_ring", 2)            # 兩枚贓物藏回家
    inventory.add_item(c, "gold_ring", 3)                          # 之後正當入手三枚
    assert (inventory.stolen_on_person(c, "gold_ring"), inventory.clean_count(c, "gold_ring")) == (0, 3)
    with _Script(["sell", "gold_ring", None, None], ints=[2]) as s:
        M.action_shop(_state(c), gd)
    assert "贓物" not in next(m for m in s.menus if m[0].startswith("賣什麼"))[2]["gold_ring"]
    assert inventory.count_item(c, "gold_ring") == 1
    assert crime.pay_fine(c, gd)["confiscated"] == [] and inventory.count_item(c, "gold_ring") == 1
    assert housing.stash_stolen(c, CITY, "gold_ring") == 2         # 家裡那兩枚仍是贓物


# --- 4 銷贓 ---------------------------------------------------------------
def test_fence_takes_stolen_goods_first_in_the_real_flow():
    c = _thief(infamy=20)
    _steal(c, "gold_ring", 2)
    inventory.add_item(c, "gold_ring", 2)
    gold0, price = c.gold, world.fence_sell_price(c, gd, "gold_ring")
    with _Script(["sell", "gold_ring", None, None], ints=[2]) as s:
        M.action_fence(_state(c), gd)
    assert "gold_ring" in next(m for m in s.menus if m[0].startswith("銷什麼"))[1]
    assert c.gold == gold0 + 2 * price
    assert inventory.count_item(c, "gold_ring") == 2 and c.stolen == {}       # 贓物先出:剩下的兩枚是乾淨的
    assert inventory.clean_count(c, "gold_ring") == 2


# --- 5 倉庫 ---------------------------------------------------------------
def _stack(c, item_id):
    return next((dict(s) for s in c.house_stash.get(CITY, []) if s["id"] == item_id), None)


def test_stash_moves_stolen_first_in_and_clean_first_out():
    c = _thief()
    c.houses_owned = [CITY]
    _steal(c, "gold_ring", 3)
    inventory.add_item(c, "gold_ring", 2)                          # 背包 5 枚:3 贓 2 淨
    assert housing.deposit(c, gd, CITY, "gold_ring", 2)            # 存 2:贓物先存
    assert _stack(c, "gold_ring") == {"id": "gold_ring", "qty": 2, "stolen": 2} and c.stolen == {"gold_ring": 1}
    assert housing.deposit(c, gd, CITY, "gold_ring", 2)            # 再存 2:剩下 1 贓 + 1 淨
    assert _stack(c, "gold_ring") == {"id": "gold_ring", "qty": 4, "stolen": 3} and c.stolen == {}
    assert (inventory.count_item(c, "gold_ring"), inventory.clean_count(c, "gold_ring")) == (1, 1)
    assert housing.withdraw(c, gd, CITY, "gold_ring", 1)           # 取 1:乾淨的先取
    assert _stack(c, "gold_ring") == {"id": "gold_ring", "qty": 3, "stolen": 3} and c.stolen == {}
    assert housing.withdraw(c, gd, CITY, "gold_ring", 2)           # 再取 2:只剩贓物可取
    assert _stack(c, "gold_ring") == {"id": "gold_ring", "qty": 1, "stolen": 1} and c.stolen == {"gold_ring": 2}
    assert (inventory.count_item(c, "gold_ring"), inventory.clean_count(c, "gold_ring")) == (4, 2)
    assert housing.withdraw(c, gd, CITY, "gold_ring", 1) and _stack(c, "gold_ring") is None
    assert c.stolen == {"gold_ring": 3}                            # 件數守恆:偷了 3 枚,繞一圈回來還是 3 枚
    inventory.add_item(c, "ruby", 2)
    assert housing.deposit(c, gd, CITY, "ruby", 2) and _stack(c, "ruby") == {"id": "ruby", "qty": 2}   # 乾淨的不帶鍵


def test_stash_menu_shows_stolen_units_and_the_move_rule():
    c = _thief()
    c.houses_owned = [CITY]
    _steal(c, "gold_ring", 2)
    inventory.add_item(c, "gold_ring", 1)
    inventory.add_item(c, "ruby", 1)
    with _Script(["gold_ring", None], ints=[2]) as s:
        M._stash_transfer(_state(c), gd, CITY, deposit=True)
    title, _keys, labels = s.menus[0]
    assert title == "存入哪件?(穿戴/手持中的裝備須先卸下;贓物會先存入)"
    assert labels["gold_ring"].endswith("×3(其中贓物 ×2)") and "贓物" not in labels["ruby"]
    assert any(m == "存入 金戒指 ×2(贓物)。" for m in s.msgs), s.msgs
    with _Script(["gold_ring", None], ints=[2]) as s:
        M._stash_transfer(_state(c), gd, CITY, deposit=False)
    title, _keys, labels = s.menus[0]
    assert title == "取出哪件?(乾淨的先取出)" and labels["gold_ring"].endswith("×2(贓物)")
    assert any(m == "取出 金戒指 ×2(贓物)。" for m in s.msgs), s.msgs

    plain = _thief()
    plain.houses_owned = [CITY]
    inventory.add_item(plain, "ruby", 2)
    with _Script(["ruby", None], ints=[1]) as s:
        M._stash_transfer(_state(plain), gd, CITY, deposit=True)
    assert s.menus[0][0] == "存入哪件?(穿戴/手持中的裝備須先卸下)" and any(m == "存入 紅寶石 ×1。" for m in s.msgs)
    with _Script(["ruby", None]) as s:
        M._stash_transfer(_state(plain), gd, CITY, deposit=False)
    assert s.menus[0][0] == "取出哪件?"                             # 沒有贓物:標題與訊息逐字同舊


# --- 6 同伴裝備 -------------------------------------------------------------
def test_companion_gear_carries_its_own_flag():
    c = _thief()
    c.companions = ["sellsword"]
    _steal(c, "steel_sword", 1)
    assert party.equip_gear(c, gd, "sellsword", "steel_sword")                # 交給同伴:贓物先走,記號跟到同伴身上
    assert c.stolen == {} and party.gear_stolen(c, "sellsword", "weapon")
    assert c.companion_gear_stolen == {"sellsword": ["weapon"]}
    inventory.add_item(c, "steel_sword", 1)                                   # 之後正當入手一把同款
    assert inventory.clean_count(c, "steel_sword") == 1                       # 身上這把是乾淨的(同伴那把才是贓物)
    assert party.unequip_gear(c, gd, "sellsword", "weapon")                   # 拿回來:贓物記回背包
    assert c.companion_gear_stolen == {} and c.stolen == {"steel_sword": 1}
    assert (inventory.count_item(c, "steel_sword"), inventory.clean_count(c, "steel_sword")) == (2, 1)
    assert party.equip_gear(c, gd, "sellsword", "steel_sword")                # 再交出去:贓物先走
    assert c.stolen == {} and party.gear_stolen(c, "sellsword", "weapon")
    assert inventory.clean_count(c, "steel_sword") == 1
    inventory.add_item(c, "ebony_sword", 1)
    assert party.equip_gear(c, gd, "sellsword", "ebony_sword")                # 換裝:舊的(贓物)退回背包,新的是乾淨的
    assert c.stolen == {"steel_sword": 1} and not party.gear_stolen(c, "sellsword", "weapon")
    assert party.equip_gear(c, gd, "sellsword", "steel_sword")                # 換回去
    assert c.stolen == {} and party.gear_stolen(c, "sellsword", "weapon")
    party.forget(c, "sellsword")                                              # 離隊:裝備與記號一起回背包
    assert c.companion_gear_stolen == {} and c.stolen == {"steel_sword": 1}
    assert inventory.count_item(c, "steel_sword") == 2

    c.companions = ["sellsword"]
    assert party.equip_gear(c, gd, "sellsword", "steel_sword")
    c.companion_gear["sellsword"] = {"armor": "steel_sword"}                  # 槽位不符的壞資料(記號跟著錯位)
    c.companion_gear_stolen = {"sellsword": ["armor"]}
    party.ensure_companion_gear(c, gd)                                        # 載入修復:退回背包,記號跟著回來
    assert c.companion_gear == {} and c.companion_gear_stolen == {} and c.stolen == {"steel_sword": 1}


# --- 7 用掉、丟掉、加工 ------------------------------------------------------
def test_stolen_units_leave_first_and_reworking_launders():
    c = _thief()
    _steal(c, "healing_potion", 2)
    inventory.add_item(c, "healing_potion", 2)
    inventory.remove_item(c, "healing_potion", 1)                  # 喝一瓶:贓物先走
    assert c.stolen == {"healing_potion": 1} and inventory.clean_count(c, "healing_potion") == 2
    inventory.remove_item(c, "healing_potion", 2)                  # 再用兩瓶:剩下的那瓶是乾淨的
    assert c.stolen == {} and inventory.clean_count(c, "healing_potion") == 1
    _steal(c, "iron_dagger", 1)
    inventory.add_item(c, "iron_dagger", 1)
    inventory.remove_item(c, "iron_dagger", 1)                     # 熔毀一把:走的是贓物
    inventory.add_item(c, "iron_ingot", 1)
    assert c.stolen == {} and inventory.clean_count(c, "iron_dagger") == 1 and inventory.clean_count(c, "iron_ingot") == 1


# --- 8 新入手的不是贓物 --------------------------------------------------------
def test_new_units_are_never_stolen():
    c = _thief()
    _steal(c, "gold_ring", 2)
    inventory.remove_item(c, "gold_ring", 2)                       # 丟掉 / 用掉:記錄當場歸零
    assert c.stolen == {}
    inventory.add_item(c, "gold_ring", 2)                          # 之後正當入手兩枚
    assert c.stolen == {} and inventory.clean_count(c, "gold_ring") == 2
    _steal(c, "gold_ring", 1)                                      # 再偷一枚:只有這一枚算贓物
    assert c.stolen == {"gold_ring": 1} and inventory.clean_count(c, "gold_ring") == 2
    c.stolen = {"ruby": 5}                                         # 殘留的壞記錄(身上一顆都沒有)
    assert inventory.stolen_on_person(c, "ruby") == 0
    inventory.add_item(c, "ruby", 2)
    assert "ruby" not in c.stolen and inventory.clean_count(c, "ruby") == 2   # 不會復活到新貨上


# --- 9 被捕沒收 -------------------------------------------------------------
def test_arrest_confiscates_only_the_stolen_units_carried():
    c = _wanted(_thief())
    c.houses_owned = [CITY]
    _steal(c, "gold_ring", 3)
    _steal(c, "ruby", 1)
    inventory.add_item(c, "gold_ring", 1)                          # 背包:金戒指 3 贓 1 淨、紅寶石 1 贓
    assert housing.deposit(c, gd, CITY, "gold_ring", 2)            # 兩枚贓物藏在家裡
    assert inventory.stolen_on_person_list(c) == [("gold_ring", 1), ("ruby", 1)]
    r = crime.pay_fine(c, gd)
    assert r["ok"] and r["confiscated"] == [("gold_ring", 1), ("ruby", 1)]
    assert inventory.count_item(c, "gold_ring") == 1 and inventory.clean_count(c, "gold_ring") == 1   # 正當的那枚沒被收
    assert inventory.count_item(c, "ruby") == 0 and c.stolen == {}
    assert housing.stash_stolen(c, CITY, "gold_ring") == 2         # 家裡的沒被搜到
    assert housing.withdraw(c, gd, CITY, "gold_ring", 2) and inventory.stolen_on_person(c, "gold_ring") == 2

    broke = _wanted(_thief(), bounty=5000)
    _steal(broke, "ruby", 1)
    r = crime.pay_fine(broke, gd)
    assert not r["ok"] and "confiscated" not in r and inventory.count_item(broke, "ruby") == 1   # 付不起 = 沒被捕

    jailed = _wanted(_thief())
    _steal(jailed, "ruby", 2)
    r = crime.serve_sentence(jailed, gd, _state(jailed).time)
    assert r["confiscated"] == [("ruby", 2)] and jailed.stolen == {} and inventory.count_item(jailed, "ruby") == 0

    clean = _wanted(_thief())
    inventory.add_item(clean, "ruby", 2)
    assert crime.pay_fine(clean, gd)["confiscated"] == [] and inventory.count_item(clean, "ruby") == 2

    held = _wanted(_thief())
    held.companions = ["sellsword"]
    _steal(held, "steel_sword", 1)
    assert party.equip_gear(held, gd, "sellsword", "steel_sword")
    assert crime.pay_fine(held, gd)["confiscated"] == []                                         # 同伴身上的不搜
    assert held.companion_gear_stolen == {"sellsword": ["weapon"]} and held.companion_gear["sellsword"]["weapon"] == "steel_sword"


def test_confiscating_worn_gear_unequips_and_recomputes():
    c = _wanted(_thief())
    _steal(c, "steel_sword", 1)
    assert inventory.equip_weapon(c, gd, "steel_sword") and c.weapon == "steel_sword"
    assert crime.pay_fine(c, gd)["confiscated"] == [("steel_sword", 1)]
    assert c.weapon == "fists" and inventory.count_item(c, "steel_sword") == 0


def test_guard_menu_announces_exactly_what_gets_confiscated():
    c = _wanted(_thief(), bounty=500)                              # 500 > 可說退上限 → 選單沒有「說服」
    _steal(c, "gold_ring", 2)
    _steal(c, "ruby", 1)
    inventory.add_item(c, "ruby", 1)                               # 身上 2 顆紅寶石、其中 1 顆是贓物
    with _Script(["pay"]) as s:
        assert M.guard_confrontation(_state(c), gd) == "confronted"
    labels = s.menus[0][2]
    assert "身上 3 件贓物會被沒收" in labels["pay"] and "身上 3 件贓物會被沒收" in labels["jail"]
    assert "贓物" not in labels["resist"]
    assert any("沒收了贓物:金戒指 ×2、紅寶石。" in m for m in s.msgs), s.msgs
    assert inventory.count_item(c, "ruby") == 1 and inventory.count_item(c, "gold_ring") == 0 and c.stolen == {}

    honest = _wanted(_thief(), bounty=500)
    with _Script(["jail"]) as s:
        M.guard_confrontation(_state(honest), gd)
    assert "贓物" not in s.menus[0][2]["pay"] and not any("沒收" in m for m in s.msgs)   # 沒贓物:標籤與訊息同舊


# --- 10 介面 --------------------------------------------------------------
def test_item_label_marks_stolen_units():
    c = _thief()
    inventory.add_item(c, "ruby", 2)
    assert "贓物" not in ui._plain(ui.item_label(gd, c, "ruby", 2))
    _steal(c, "ruby", 1)
    assert ui._plain(ui.item_label(gd, c, "ruby", 3)).endswith("(其中贓物 ×1)")
    _steal(c, "gold_ring", 1)
    assert ui._plain(ui.item_label(gd, c, "gold_ring", 1)).endswith("(贓物)")
    labels = {it["key"]: it["label"] for it in ui._inventory_view(c, gd)["items"]}
    assert labels["gold_ring"].endswith("(贓物)") and "其中贓物 ×1" in labels["ruby"]


# --- 11 存檔 --------------------------------------------------------------
def test_save_roundtrip_old_saves_migration_and_sanitising():
    c = _thief()
    c.houses_owned = [CITY]
    _steal(c, "gold_ring", 2)
    housing.deposit(c, gd, CITY, "gold_ring", 1)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "save.json"
        _state(c).save(path)
        back = GameState.load(path).player
    assert back.stolen == {"gold_ring": 1} and housing.stash_stolen(back, CITY, "gold_ring") == 1

    geared = _thief()
    geared.companions = ["sellsword"]
    _steal(geared, "steel_sword", 1)
    assert party.equip_gear(geared, gd, "sellsword", "steel_sword")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "save.json"
        _state(geared).save(path)
        back = GameState.load(path).player
    assert back.companion_gear_stolen == {"sellsword": ["weapon"]} and back.stolen == {}
    assert party.unequip_gear(back, gd, "sellsword", "weapon") and back.stolen == {"steel_sword": 1}

    old = c.to_dict()
    old.pop("stolen")
    old.pop("companion_gear_stolen")
    old["house_stash"] = {CITY: [{"id": "gold_ring", "qty": 1}]}
    fresh = Character.from_dict(old)
    inventory.ensure_stolen(fresh, gd)
    assert fresh.stolen == {} and housing.stash_stolen(fresh, CITY, "gold_ring") == 0   # 舊檔缺欄 = 都是乾淨的

    v1 = _thief()                                                  # R223 第一版格式:一個數把倉庫裡的也算進去
    v1.houses_owned = [CITY]
    inventory.add_item(v1, "gold_ring", 1)
    v1.house_stash = {CITY: [{"id": "gold_ring", "qty": 3}]}
    v1.companions = ["sellsword"]
    v1.companion_gear = {"sellsword": {"weapon": "steel_sword"}}
    v1.stolen = {"gold_ring": 3, "steel_sword": 1}
    for _ in range(2):                                             # 第二次 = 冪等
        inventory.ensure_stolen(v1, gd)
        assert v1.stolen == {"gold_ring": 1} and housing.stash_stolen(v1, CITY, "gold_ring") == 2   # 超出背包的分配給倉庫
        assert v1.companion_gear_stolen == {"sellsword": ["weapon"]}                                 # 再給同伴身上同款的槽

    bad = _thief()
    inventory.add_item(bad, "gold_ring", 2)
    bad.house_stash = {CITY: [{"id": "ruby", "qty": 2, "stolen": 7}, {"id": "wheat", "qty": 1, "stolen": "x"},
                              {"id": "iron_dagger", "qty": 1, "stolen": 0}]}
    bad.stolen = {"gold_ring": 9, "wheat": -1, "iron_dagger": True, 7: 2, "ebony_sword": "x"}
    bad.companion_gear = {"sellsword": {"weapon": "steel_sword"}}
    bad.companion_gear_stolen = {"sellsword": ["weapon", "weapon", "armor", 3], "ghost": ["weapon"], "x": "weapon"}
    inventory.ensure_stolen(bad, gd)
    assert bad.stolen == {"gold_ring": 2}                          # 夾到背包件數;壞值清掉
    assert bad.companion_gear_stolen == {"sellsword": ["weapon"]}  # 只留確實有裝備的槽
    assert bad.house_stash[CITY] == [{"id": "ruby", "qty": 2, "stolen": 2}, {"id": "wheat", "qty": 1},
                                     {"id": "iron_dagger", "qty": 1}]
    bad.stolen = ["garbage"]
    inventory.ensure_stolen(bad, gd)
    assert bad.stolen == {}


# --- 12 突變 --------------------------------------------------------------
def test_guards_bite_under_in_process_mutations():
    def swap(mod, name, repl, *victims):
        real = getattr(mod, name)
        setattr(mod, name, repl(real) if getattr(repl, "wraps", False) else repl)
        try:
            for v in victims:
                assert _expect_fail(v), f"突變 {mod.__name__}.{name} 沒被 {v.__name__} 抓到"
        finally:
            setattr(mod, name, real)

    def wrapper(fn):
        fn.wraps = True
        return fn

    swap(inventory, "mark_stolen", lambda *_a, **_k: None,                      # 1 得手不標記
         test_theft_marks_only_on_success, test_honest_shop_only_takes_clean_units_in_the_real_flow)
    swap(inventory, "clean_count", inventory.count_item,                        # 2 商店照收贓物
         test_honest_shop_only_takes_clean_units_in_the_real_flow)
    swap(inventory, "remove_item",                                              # 3 賣商店也當成贓物先走(clean 被忽略)
         wrapper(lambda real: lambda c, i, q=1, keep_temper=False, **_k: real(c, i, q, keep_temper)),
         test_honest_shop_only_takes_clean_units_in_the_real_flow)
    swap(inventory, "remove_item",                                              # 4 離開背包不扣記錄(乾淨的先走)
         wrapper(lambda real: lambda c, i, q=1, keep_temper=False, **_k: real(c, i, q, keep_temper, clean=True)),
         test_fence_takes_stolen_goods_first_in_the_real_flow, test_stolen_units_leave_first_and_reworking_launders)

    def no_clamp(real):                                                         # 5 新入手不清壞記錄(壞記錄套到新貨上)
        def add(c, i, q=1):
            before = c.stolen.get(i)
            real(c, i, q)
            if before is not None:
                c.stolen[i] = before
        return add
    swap(inventory, "add_item", wrapper(no_clamp), test_new_units_are_never_stolen)
    swap(party, "_set_gear_stolen", lambda *_a, **_k: None,                     # 6 交給同伴不帶記號(交出去就洗白)
         test_companion_gear_carries_its_own_flag)
    swap(inventory, "confiscate_stolen", lambda *_a, **_k: [],                  # 7 被捕不沒收
         test_arrest_confiscates_only_the_stolen_units_carried, test_guard_menu_announces_exactly_what_gets_confiscated)
    swap(party, "_return_gear",                                                 # 8 從同伴拿回來不記回背包(拿回來就洗白)
         lambda c, cid, slot, iid: inventory.add_item(c, iid, 1),
         test_companion_gear_carries_its_own_flag)
    swap(housing, "_stash_remove",                                              # 9 取出時贓物先取
         wrapper(lambda real: lambda c, loc, i, q: (lambda hot: (real(c, loc, i, q), min(q, hot))[1])(
             housing.stash_stolen(c, loc, i))),
         test_stash_moves_stolen_first_in_and_clean_first_out)
    swap(housing, "_stash_add",                                                 # 10 存入時不帶件數(存進去就洗白)
         wrapper(lambda real: lambda c, loc, i, q, stolen=0: real(c, loc, i, q)),
         test_stash_moves_stolen_first_in_and_clean_first_out, test_stolen_goods_kept_at_home_do_not_taint_the_ones_you_carry)
    swap(world, "min_buy_price", world.buy_price,                               # 11 最低買價只看當地(忽略別省的商誼)
         test_min_buy_price_uses_the_best_trade_pact_not_the_local_one)
    swap(world, "fence_sell_price",                                             # 12 拿掉全域夾限
         lambda c, g, i: int(world.sell_price(c, g, i) * (1 + crime.fence_bonus(c))),
         test_no_vendor_pays_what_any_vendor_charges)
    test_theft_marks_only_on_success()                                          # 還原後仍綠
    test_stash_moves_stolen_first_in_and_clean_first_out()
    test_no_vendor_pays_what_any_vendor_charges()


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_stolen_r223 OK")
