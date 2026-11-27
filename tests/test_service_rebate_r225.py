"""R225 ① 議價溢出折抵服務價(議價超過上限的部分,每 0.1 折服務價 5%,最多 20%)。

守衛:
  1. 零溢出逐位元組同舊價:沒有溢出時,服務價 == 凍結在本檔的舊式(訓練 / 法術 / 房產 / 擴建 / 坐騎 / 雇傭兵 × 公會折扣)。
  2. 數值:溢出 0.20 → −10%、0.40 以上封頂 −20%(紙面方案的量測值);折抵隨溢出單調不減、不超過上限、不為負。
  3. 範圍:折抵只進服務價;買 / 賣 / 銷贓 / 黑市價與議價係數都不因溢出而變(議價仍夾在 1.0)。
  4. 預覽 = 實扣:六個真流程(訓練 / 法術 / 坐騎 / 購房 / 擴建 / 雇傭兵)選單標籤上的價錢 == 實際扣的金幣。
  5. 不適用:旅店過夜費與罰金不吃折抵。
  6. 介面:議價提示列出「溢出 X 折抵服務價 Y%」;有折抵才在選單標題標註。
  7. 突變下會紅(就地突變:折抵率 / 上限 / 漏掉公會折扣 / 溢出算成含上限)。
"""
import io
import re

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

import sim_economy as E
from tesrpg import main as M
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import factions, housing, world

gd = E.gd
_LOC = "bruma"     # 有房產、訓練師、法師公會、旅店

# 溢出由小到大的一組角色(交易 100 + 魅力 40 → 無溢出;+議價節點 → 0.20;魅力 100 + 節點 → 0.40;再加魅惑 → 0.48)
_PROFILES = {
    "none_low": dict(mercantile=5, personality=40),
    "none_mid": dict(mercantile=37, personality=55, fame=150, charm=True),
    "none_high": dict(mercantile=100, personality=40),
    "half": dict(mercantile=100, personality=40, nodes=True),
    "cap": dict(mercantile=100, personality=100, nodes=True),
    "over": dict(mercantile=100, personality=100, nodes=True, charm=True),
}


def _char(name):
    return E.make_char(**_PROFILES[name])


def _old_service(base, guild_discount=0.0):
    """凍結的舊式(R225 之前各扣款點的寫法,逐字抄;只用來對帳)。"""
    return max(1, round(base * (1 - guild_discount)))


# --- 1 零溢出逐位元組同舊價 --------------------------------------------------
def test_no_overflow_equals_frozen_old_prices():
    for name in ("none_low", "none_mid", "none_high"):
        c = _char(name)
        assert world.barter_overflow(c, gd) == 0.0 and world.service_rebate(c, gd) == 0.0
        for base in (1, 7, 20, 156, 800, 1200, 3500, 8000, 12400):
            for disc in (0.0, 0.05, 0.1, 0.15, 0.3):
                assert world.service_price(c, gd, base, disc) == _old_service(base, disc), (name, base, disc)
        for lv in range(5, 100):
            assert world.service_price(c, gd, world.train_cost(lv)) == world.train_cost(lv)
        for s in gd.spells:
            assert world.service_price(c, gd, world.spell_price(gd, s), 0.1) == \
                max(1, round(world.spell_price(gd, s) * (1 - 0.1)))
        assert world.rebate_note(c, gd) == ""


# --- 2 數值 -----------------------------------------------------------------
def test_rebate_golden_values():
    got = {n: (round(world.barter_overflow(_char(n), gd), 4), world.service_rebate(_char(n), gd),
               world.service_price(_char(n), gd, 1000)) for n in _PROFILES}
    assert got["half"] == (0.2, 0.1, 900), got                 # 溢出 0.20 → −10%
    assert got["cap"] == (0.4, 0.2, 800), got                  # 溢出 0.40 → 封頂 −20%
    assert got["over"] == (0.48, 0.2, 800), got                # 全來源疊滿(0.48)仍是 −20%
    assert world.service_price(_char("over"), gd, 12400) == 9920   # 訓練師獨有區段 12,400 金最低 9,920(紙面方案)


def test_rebate_is_bounded_and_monotone():
    last = -1.0
    for name in ("none_low", "none_high", "half", "cap", "over"):
        r = world.service_rebate(_char(name), gd)
        assert 0.0 <= r <= world.SERVICE_REBATE_CAP
        assert r >= last
        last = r
    assert world.SERVICE_REBATE_CAP == 0.20 and world.SERVICE_REBATE_PER_OVERFLOW == 0.5


def test_overflow_is_exactly_the_part_the_cap_swallowed():
    for name in _PROFILES:
        c = _char(name)
        b = world.barter_breakdown(c, gd)
        assert world.barter_overflow(c, gd) == b["wasted"] == max(0.0, b["raw"] - world.BARTER_CAP)
        assert b["service_rebate"] == world.service_rebate(c, gd)


# --- 3 範圍:只動服務價 ------------------------------------------------------
def test_overflow_does_not_touch_goods_prices_or_the_barter_cap():
    base = E.make_char(100, 100)          # 剛好頂到上限、無溢出
    over = _char("over")                  # 溢出 0.48
    assert world.service_rebate(base, gd) == 0.0 and world.service_rebate(over, gd) > 0
    assert world._disposition_factor(over, gd) == world.BARTER_CAP == world._disposition_factor(base, gd)
    for iid in ("ebony_sword", "ruby", "healing_potion", "iron_ingot", "lockpick"):
        assert world.buy_price(over, gd, iid) == world.buy_price(base, gd, iid)
        assert world.sell_price(over, gd, iid) == world.sell_price(base, gd, iid)
        assert world.fence_sell_price(over, gd, iid) == world.fence_sell_price(base, gd, iid)
        assert world.black_market_price(over, gd, iid) == world.black_market_price(base, gd, iid)


def test_guild_discount_and_rebate_multiply():
    c = _char("cap")      # −20%
    assert world.service_price(c, gd, 1000, 0.10) == round(1000 * 0.9 * 0.8) == 720
    assert world.service_price(c, gd, 20) == 16
    assert world.service_price(c, gd, 1) == 1      # 至少 1 金


# --- 4 預覽 = 實扣(真流程)--------------------------------------------------
class _Script:
    """腳本化選單:依序回傳預先排好的選擇(None = 返回);記下每次選單的標題與選項;確認句一律記下並回 confirm_to。"""

    def __init__(self, picks, confirm_to=True):
        self.picks, self.confirm_to = list(picks), confirm_to
        self.menus, self.confirms = [], []

    def menu(self, title, options, allow_back=False, **kw):
        self.menus.append((title, options))
        return self.picks.pop(0) if self.picks else None

    def confirm(self, prompt, *a, **kw):
        self.confirms.append(prompt)
        return self.confirm_to


def _run(fn, state, script):
    real = (ui.menu, ui.confirm)
    ui.menu, ui.confirm = script.menu, script.confirm
    try:
        fn(state, gd)
    finally:
        ui.menu, ui.confirm = real


def _state(name, loc=_LOC, gold=500000):
    c = _char(name)
    c.location_id = loc
    c.gold = gold
    return GameState(player=c, rng=RNG(seed=1), game_mode="adventure")


def _label(script, key, menu_index=0):
    for opt in script.menus[menu_index][1]:
        if opt[0] == key:
            return opt[1]
    raise AssertionError((key, [o[0] for o in script.menus[menu_index][1]]))


def _price_in(label):
    return int(re.search(r"(\d+) 金", label).group(1))


def test_spell_vendor_label_equals_charge():
    for name in ("none_high", "half", "cap"):
        st = _state(name)
        sid = gd.location(_LOC)["spell_stock"][0]
        script = _Script([sid])
        _run(M.action_spell_vendor, st, script)
        assert sid in st.player.spells
        shown = _price_in(_label(script, sid))
        assert 500000 - st.player.gold == shown == world.service_price(st.player, gd, world.spell_price(gd, sid)), name
        if name != "none_high":
            assert "議價折抵" in script.menus[0][0]
        else:
            assert "議價折抵" not in script.menus[0][0]


def test_trainer_label_equals_charge_and_repeat_prompt_price():
    for name in ("none_high", "half", "cap"):
        st = _state(name)
        c = st.player
        specs = world.trainer_specs(gd, _LOC)
        spec = specs[0]
        sid = world.trainer_skills(gd, _LOC, spec)[0]
        level = c.skill(sid)
        script = _Script([spec, sid] if len(specs) > 1 else [sid], confirm_to=False)
        _run(M.action_trainer, st, script)
        want = world.service_price(c, gd, world.train_cost(level))
        assert _price_in(_label(script, sid, 1 if len(specs) > 1 else 0)) == want == 500000 - c.gold, name
        nxt = world.service_price(c, gd, world.train_cost(c.skill(sid)))
        assert any(f"{nxt} 金" in p for p in script.confirms), (name, script.confirms)   # ↻ 再訓練的價也走同一出處


def test_stable_label_equals_charge():
    for name in ("none_high", "half", "cap"):
        st = _state(name)
        script = _Script(["buy:warhorse"])
        _run(M.action_stable, st, script)
        want = world.service_price(st.player, gd, gd.mount("warhorse")["price"])
        assert _price_in(_label(script, "buy:warhorse")) == want == 500000 - st.player.gold, name


def test_house_purchase_and_upgrade_prompts_equal_charge():
    for name in ("none_high", "half", "cap"):
        st = _state(name)
        c = st.player
        h = gd.house_at(_LOC)
        script = _Script([])
        _run(M.action_house, st, script)
        want = world.service_price(c, gd, h["price"])
        assert housing.owns(c, _LOC) and 500000 - c.gold == want, name
        assert f"以 {want} 金購置" in script.confirms[0]
        gold = c.gold
        script = _Script(["upgrade", "garden"])
        _run(M.action_house, st, script)
        u = gd.house_upgrades["garden"]
        uw = world.service_price(c, gd, u["price"])
        up_menu = [m for m in script.menus if m[0].startswith("添置哪項設施")][0]
        assert _price_in(dict((o[0], o[1]) for o in up_menu[1])["garden"]) == uw == gold - c.gold, name
        assert any(f"以 {uw} 金添置" in p for p in script.confirms)


def test_mercenary_label_equals_charge_with_guild_discount():
    for name in ("none_high", "half", "cap"):
        st = _state(name)
        c = st.player
        cid = next(k for k, v in gd.companions.items()
                   if not (v.get("troop") or v.get("warlord") or v.get("circle") or v.get("recruit_quest")))
        script = _Script([cid])
        _run(M._hire_mercenary, st, script)
        disc = factions.merc_discount(c, gd)
        want = world.service_price(c, gd, gd.companions[cid]["cost"], disc)
        assert cid in c.companions and 500000 - c.gold == want, name
        assert _price_in(_label(script, cid)) == want, name


# --- 5 不適用 ---------------------------------------------------------------
def test_inn_fee_is_not_discounted():
    st = _state("over", gold=1000)
    M._inn_rest(st, gd)
    assert st.player.gold == 1000 - M.INN_REST_FEE


# --- 6 介面 -----------------------------------------------------------------
def test_barter_tip_explains_the_overflow_conversion():
    tip = ui._barter_tip(_char("half"), gd)
    assert "折抵服務價 −10%" in tip and "無效" not in tip, tip
    assert "折抵服務價" not in ui._barter_tip(_char("none_high"), gd)
    assert world.rebate_note(_char("half"), gd) == "議價折抵 −10%" and world.rebate_note(_char("cap"), gd) == "議價折抵 −20%"


# --- 7 突變 -----------------------------------------------------------------
def _mutation_survives(attr, value, probe):
    old = getattr(world, attr)
    setattr(world, attr, value)
    try:
        probe()
    except AssertionError:
        return False
    finally:
        setattr(world, attr, old)
    return True


def test_guards_fail_under_mutation():
    assert not _mutation_survives("SERVICE_REBATE_PER_OVERFLOW", 0.25, test_rebate_golden_values)
    assert not _mutation_survives("SERVICE_REBATE_CAP", 0.30, test_rebate_golden_values)
    assert not _mutation_survives("SERVICE_REBATE_CAP", 0.30, test_rebate_is_bounded_and_monotone)
    assert not _mutation_survives("SERVICE_REBATE_PER_OVERFLOW", 0.0, test_rebate_golden_values)
    real = world.service_price
    world.service_price = lambda char, gamedata, base, guild_discount=0.0: max(1, round(base * (1 - world.service_rebate(char, gamedata))))
    try:   # 漏掉公會折扣
        try:
            test_guild_discount_and_rebate_multiply()
            survived = True
        except AssertionError:
            survived = False
    finally:
        world.service_price = real
    assert not survived


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_service_rebate_r225 OK")
