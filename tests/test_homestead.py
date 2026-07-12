"""家園基地化(R110)回歸測試。

涵蓋:tier/格位、擴建購買(action 路徑扣款 / 重複拒 / 格位閘 / 未知 id 拒 / 未擁房拒)、
藥草園(購入即冷卻 / 冷卻擋 / value cap / 本城生態池 / **零技能 XP** / 錯過不累積)、
🔴 R88 式全池經濟不變量(預算 6 · 單品 3 · cap 10 → 每池精確最大 ≤ 40 raw value)、
舒適臥房(只延時;既有預設參數呼叫端逐位元組同)、在地商誼(無房恆等 / 本省限定 /
頂配疊加反套利地板)、存檔相容(roundtrip / 舊檔缺欄 / ensure 自癒冪等 / 未知 id 保留
inert)、legacy / 成就承認。
"""

import json

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import achievements, housing, legacy, world


def _char(race="nord"):
    gd = get_gamedata()
    c = build_character(gd, name="居", sex="male", race=race, birthsign="warrior", class_id="warrior")
    return gd, c


# --- tier / 格位 ---------------------------------------------------------
def test_tier_and_slots():
    gd, c = _char()
    assert housing.tier(gd, "bruma") == 1 and housing.slots(gd, "bruma") == 2
    assert housing.tier(gd, "whiterun") == 2 and housing.slots(gd, "whiterun") == 3
    assert housing.tier(gd, "imperial_city") == 3 and housing.slots(gd, "imperial_city") == 4
    assert housing.tier_name(gd, "imperial_city") == "莊園"
    assert housing.tier(gd, "kvatch") == 1          # 無房產地點 → 安全預設


def test_upgrade_purchase_gates():
    gd, c = _char()
    # 未擁房 → 不可購
    assert housing.available_upgrades(c, gd, "bruma") == []
    assert housing.buy_upgrade(c, gd, "bruma", "garden", now=0) is False
    housing.buy(c, gd, "bruma")
    assert set(housing.available_upgrades(c, gd, "bruma")) == set(gd.house_upgrades)
    # 未知 id 拒
    assert housing.buy_upgrade(c, gd, "bruma", "ghost_upgrade", now=0) is False
    # 正常購買 + 重複拒
    assert housing.buy_upgrade(c, gd, "bruma", "garden", now=0) is True
    assert housing.buy_upgrade(c, gd, "bruma", "garden", now=0) is False
    # T1 = 2 格:第二件裝滿後,第三件被格位閘擋
    assert housing.buy_upgrade(c, gd, "bruma", "bedroom", now=0) is True
    assert housing.available_upgrades(c, gd, "bruma") == []
    assert housing.buy_upgrade(c, gd, "bruma", "trade_pact", now=0) is False
    # T3 莊園裝得下全部三件
    housing.buy(c, gd, "imperial_city")
    for uid in gd.house_upgrades:
        assert housing.buy_upgrade(c, gd, "imperial_city", uid, now=0) is True


def test_action_house_upgrade_deducts_gold():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _char(); c.location_id = "bruma"; c.gold = 9000
    housing.buy(c, gd, "bruma")
    state = GameState(player=c, rng=RNG(1))
    menu_seq = ["upgrade", "garden", None, None]    # 房產選單→擴建→選藥草園→退出擴建→退出房產
    saved = (ui.menu, ui.message, ui.confirm)
    ui.message = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True
    ui.menu = lambda *a, **k: menu_seq.pop(0)
    try:
        M.action_house(state, gd)
    finally:
        ui.menu, ui.message, ui.confirm = saved
    price = gd.house_upgrades["garden"]["price"]
    assert housing.has_upgrade(c, gd, "bruma", "garden") and c.gold == 9000 - price
    assert c.house_garden_at["bruma"] == state.time.absolute_hours() + housing.GARDEN_COOLDOWN_HOURS


def test_action_house_upgrade_failed_buy_no_gold_sink():
    """扣款前 buy_upgrade 回 False → 不靜默沉金(審查 finding:成功才扣款)。patch
    buy_upgrade 模擬 menu-time/buy-time 分歧(正常流程不可達,但防未來新閘)。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _char(); c.location_id = "bruma"; c.gold = 9000
    housing.buy(c, gd, "bruma")
    gold0 = c.gold
    state = GameState(player=c, rng=RNG(1))
    saved = (ui.menu, ui.message, ui.confirm, housing.buy_upgrade)
    ui.message = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True
    seq = ["garden", None]
    ui.menu = lambda *a, **k: seq.pop(0)
    housing.buy_upgrade = lambda *a, **k: False               # 模擬 buy 閘失敗
    try:
        M._house_upgrade_menu(state, gd, "bruma")
    finally:
        ui.menu, ui.message, ui.confirm, housing.buy_upgrade = saved
    assert c.gold == gold0                                    # 未扣款(未成功)


# --- 藥草園 --------------------------------------------------------------
def test_garden_cooldown_value_cap_and_pool():
    gd, c = _char()
    housing.buy(c, gd, "bruma")
    housing.buy_upgrade(c, gd, "bruma", "garden", now=0)
    rng = RNG(7)
    # 購入即進冷卻:不可即刻採收
    assert housing.harvest_garden(c, gd, "bruma", now=0, rng=rng) is None
    # 本城生態池成員 + value cap(多 seed 掃描)
    pool_id = housing.garden_pool_id(gd, "bruma")
    pool = gd.ecology["pools"][pool_id]
    members = {iid for tier in ("common", "uncommon", "rare") for iid in pool.get(tier, [])}
    for seed in range(12):
        c.house_garden_at["bruma"] = 0
        picks = housing.harvest_garden(c, gd, "bruma", now=24, rng=RNG(seed))
        assert picks, "藥草園不可為空(每池皆有 ≤cap 候選)"
        for iid, qty in picks:
            assert iid in members, f"{iid} 不在 {pool_id} 池"
            assert gd.item(iid)["value"] <= housing.GARDEN_VALUE_CAP, iid
            assert 1 <= qty <= 3
    # 冷卻推進 + 錯過不累積(banking 不存在):久未採收仍只能採一次、下次=採收時+冷卻
    assert c.house_garden_at["bruma"] == 24 + housing.GARDEN_COOLDOWN_HOURS
    c.house_garden_at["bruma"] = 24
    assert housing.harvest_garden(c, gd, "bruma", now=1000, rng=rng) is not None
    assert c.house_garden_at["bruma"] == 1000 + housing.GARDEN_COOLDOWN_HOURS
    assert housing.harvest_garden(c, gd, "bruma", now=1000, rng=rng) is None


def test_garden_requires_upgrade_and_gives_zero_xp():
    gd, c = _char()
    housing.buy(c, gd, "gideon")
    assert housing.harvest_garden(c, gd, "gideon", now=100, rng=RNG(1)) is None   # 無藥草園
    housing.buy_upgrade(c, gd, "gideon", "garden", now=0)
    xp_before = dict(c.skill_xp)
    skills_before = dict(c.skills)
    picks = housing.harvest_garden(c, gd, "gideon", now=100, rng=RNG(1))
    assert picks
    # 🔴 零技能 XP(刻意:防每日免費 XP 滴灌;野採事件才練 scout/alchemy)
    assert c.skill_xp == xp_before and c.skills == skills_before


def test_garden_pool_invariant_r88():
    """🔴 R88 式全池經濟不變量:任一生態池在(預算 6 · 單品 3 · value cap 10)下的
    **精確最大** raw value ≤ 40 —— 未來改池/材料資料不會靜默養肥藥草園水龍頭。
    同時守:每個房產城的 biome 池至少 3 個 ≤cap 候選(無空園)。"""
    gd, _ = _char()
    costs = {"common": 1, "uncommon": 3, "rare": 6}
    for pid, pool in gd.ecology["pools"].items():
        items = []
        for tier, cost in costs.items():
            for iid in pool.get(tier, []):
                v = gd.item(iid)["value"]
                if v <= housing.GARDEN_VALUE_CAP:
                    items.append((cost, v))
        best = [0]

        def rec(i, budget, val):
            best[0] = max(best[0], val)
            if i >= len(items):
                return
            cost, v = items[i]
            for n in range(0, 4):                      # 單品上限 3
                if n * cost <= budget:
                    rec(i + 1, budget - n * cost, val + n * v)
        rec(0, housing.GARDEN_BUDGET, 0)
        assert best[0] <= 40, f"{pid} 池藥草園上限 {best[0]} 超過 40 —— 檢查新材料/池改動"
    for lid in gd.houses:
        pool_id = housing.garden_pool_id(gd, lid)
        assert pool_id is not None, f"{lid} 無生態池(藥草園會停用)"
        pool = gd.ecology["pools"][pool_id]
        n_ok = sum(1 for tier in costs for iid in pool.get(tier, [])
                   if gd.item(iid)["value"] <= housing.GARDEN_VALUE_CAP)
        assert n_ok >= 3, f"{lid}({pool_id})≤cap 候選只有 {n_ok} 個,藥草園近乎空園"


# --- 舒適臥房(只延時)---------------------------------------------------
def test_bedroom_extends_duration_only():
    gd, c = _char()
    # 預設參數:既有呼叫端(巢穴/藏身處)逐位元組同
    housing.set_well_rested(c, 100)
    assert c.well_rested_until == 100 + formulas.WELL_RESTED_HOURS
    housing.set_well_rested(c, 100, hours=36)
    assert c.well_rested_until == 136
    housing.buy(c, gd, "bruma")
    assert housing.rest_hours(c, gd, "bruma") == formulas.WELL_RESTED_HOURS   # 無臥房
    housing.buy_upgrade(c, gd, "bruma", "bedroom", now=0)
    assert housing.rest_hours(c, gd, "bruma") == housing.BEDROOM_WELL_RESTED_HOURS
    assert housing.rest_hours(c, gd, "whiterun") == formulas.WELL_RESTED_HOURS  # 他宅無臥房


# --- 在地商誼 ------------------------------------------------------------
def test_trade_pact_discount_scoping():
    gd, c = _char()
    c.location_id = "whiterun"
    p0 = world.buy_price(c, gd, "iron_sword")
    housing.buy(c, gd, "whiterun")
    assert housing.province_discount(c, gd) == 0.0            # 有房無商誼 → 無折扣
    assert world.buy_price(c, gd, "iron_sword") == p0
    housing.buy_upgrade(c, gd, "whiterun", "trade_pact", now=0)
    assert housing.province_discount(c, gd) == housing.TRADE_PACT_DISCOUNT
    assert world.buy_price(c, gd, "iron_sword") <= p0
    c.location_id = "solitude"                                # 同省(天際)另一城 → 也生效
    assert housing.province_discount(c, gd) == housing.TRADE_PACT_DISCOUNT
    c.location_id = "bruma"                                   # 他省(賽羅迪爾)→ 不生效
    assert housing.province_discount(c, gd) == 0.0
    c.location_id = "frost_barrow"                            # 荒野/地城 → 防禦回 0(若無 province)
    assert isinstance(housing.province_discount(c, gd), float)


def test_trade_pact_maxed_stack_floor_holds():
    """頂配疊加(議價滿 + 戰士軍械庫滿階 + 高聲望 + 在地商誼)下,全品項買價恆 > 賣價
    (反套利地板構造性成立;R110 折扣插在地板之前)。"""
    gd, c = _char()
    c.location_id = "whiterun"
    c.skills["mercantile"] = 100
    c.attributes["personality"] = 100
    c.factions["fighters_guild"] = len(gd.factions["fighters_guild"]["ranks"]) - 1
    c.factions["thieves_guild"] = len(gd.factions["thieves_guild"]["ranks"]) - 1   # 抬高賣價側
    c.fame = 1000
    housing.buy(c, gd, "whiterun")
    housing.buy_upgrade(c, gd, "whiterun", "trade_pact", now=0)
    for iid in gd.items:
        assert world.buy_price(c, gd, iid) > world.sell_price(c, gd, iid), iid


# --- 存檔相容 / 遷移 ------------------------------------------------------
def test_save_roundtrip_and_old_save():
    gd, c = _char()
    c.houses_owned = ["bruma"]
    c.house_upgrades = {"bruma": ["garden", "bedroom"]}
    c.house_garden_at = {"bruma": 48}
    d = json.loads(json.dumps(c.to_dict()))
    l = Character.from_dict(d)
    assert l.house_upgrades == {"bruma": ["garden", "bedroom"]}
    assert l.house_garden_at == {"bruma": 48}
    for k in ("house_upgrades", "house_garden_at"):
        del d[k]
    o = Character.from_dict(d)                                # 舊檔缺欄 → dataclass 預設
    assert o.house_upgrades == {} and o.house_garden_at == {}


def test_ensure_housing_fields_self_heal_idempotent():
    gd, c = _char()
    # 壞型別 → 矯正
    c.house_upgrades = "corrupt"
    c.house_garden_at = ["corrupt"]
    housing.ensure_housing_fields(c, now=100)
    assert c.house_upgrades == {} and c.house_garden_at == {}
    # 值型別矯正 + 未來時間戳上夾(治「永遠採不了」的毀損檔;0/過去值=可採本就合法)
    c.house_upgrades = {"bruma": "not_a_list", "vivec": ["garden", 42, "ghost_upgrade", "garden"]}
    c.house_garden_at = {"bruma": 999999, "vivec": "bad", "gideon": 12, "haven": float("inf")}
    housing.ensure_housing_fields(c, now=100)
    assert c.house_upgrades["bruma"] == []
    assert c.house_upgrades["vivec"] == ["garden", "ghost_upgrade"]   # 未知 id 保留 + 去重(審查 finding)
    assert c.house_garden_at["bruma"] == 100 + housing.GARDEN_COOLDOWN_HOURS
    assert "vivec" not in c.house_garden_at and c.house_garden_at["gideon"] == 12
    assert "haven" not in c.house_garden_at              # 🔴 Infinity → OverflowError 亦被剔除(不再崩載入)
    snap = (json.dumps(c.house_upgrades, sort_keys=True), json.dumps(c.house_garden_at, sort_keys=True))
    housing.ensure_housing_fields(c, now=100)                 # 冪等
    assert snap == (json.dumps(c.house_upgrades, sort_keys=True), json.dumps(c.house_garden_at, sort_keys=True))


def test_ensure_heals_corrupt_houses_owned():
    """🔴 R110 起 province_discount 於每次 buy_price 迭代 houses_owned → 毀損成 null/非 list
    會使全商店定價崩;ensure 順手型別自癒(審查 finding)。"""
    gd, c = _char()
    c.houses_owned = None
    housing.ensure_housing_fields(c, now=100)
    assert c.houses_owned == []
    assert housing.province_discount(c, gd) == 0.0           # 不再 TypeError
    c.houses_owned = ["bruma"]                                # 合法值不動
    housing.ensure_housing_fields(c, now=100)
    assert c.houses_owned == ["bruma"]


def test_unknown_upgrade_id_inert_not_blocking():
    """目錄移除的擴建 id:不佔格位、不生效,但保留不刪(不回溯銷毀玩家金幣)。"""
    gd, c = _char()
    housing.buy(c, gd, "bruma")
    c.house_upgrades["bruma"] = ["ghost_upgrade", "garden"]
    assert housing.owned_upgrades(c, gd, "bruma") == ["garden"]
    assert housing.has_upgrade(c, gd, "bruma", "ghost_upgrade") is False
    # ghost 不佔格位:T1 兩格只用了 1 → 還能再購一件
    assert housing.buy_upgrade(c, gd, "bruma", "bedroom", now=0) is True
    assert housing.buy_upgrade(c, gd, "bruma", "trade_pact", now=0) is False   # 格位滿
    assert "ghost_upgrade" in c.house_upgrades["bruma"]        # 仍保留


# --- legacy / 成就承認 ----------------------------------------------------
def test_legacy_scores_homestead():
    gd, c = _char()
    st = GameState(player=c, rng=RNG(1))
    base = legacy.compute(st, gd)["score"]
    assert legacy.compute(st, gd)["homestead"] is None
    c.houses_owned = ["bruma", "whiterun"]
    c.house_upgrades = {"bruma": ["garden"], "whiterun": ["ghost_upgrade"]}   # ghost 不計分
    res = legacy.compute(st, gd)
    assert res["score"] == base + 2 * 60 + 1 * 20
    assert res["homestead"] == "置業 2 處 · 設施 1 件"


def test_houses_count_achievements():
    gd, c = _char()
    earned0 = {a["id"] for a in achievements.earned(c, gd)}
    assert "homeowner" not in earned0 and "estate_lord" not in earned0
    c.houses_owned = ["bruma"]
    assert "homeowner" in {a["id"] for a in achievements.earned(c, gd)}
    c.houses_owned = ["bruma", "whiterun", "gideon", "ghost_town"]            # ghost 不計
    assert "estate_lord" not in {a["id"] for a in achievements.earned(c, gd)}
    c.houses_owned = ["bruma", "whiterun", "gideon", "vivec"]
    assert "estate_lord" in {a["id"] for a in achievements.earned(c, gd)}


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_homestead 全通過")
