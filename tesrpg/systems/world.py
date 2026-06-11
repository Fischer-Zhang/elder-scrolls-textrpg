"""世界地圖、旅行、商店與訓練師的規則。

地圖是「地點圖」:每個地點有若干通往他處的連結(各帶旅行時數)。
旅行會推進時間,並可能在途中觸發遭遇。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import combat, progression


# --- 地點 / 旅行 --------------------------------------------------------
def current_location(char: Character, gamedata: GameData) -> dict:
    return gamedata.location(char.location_id)


def travel_options(char: Character, gamedata: GameData) -> list[tuple[str, int]]:
    """回傳 [(目的地 id, 旅行時數), ...]。"""
    loc = current_location(char, gamedata)
    return list(loc.get("links", {}).items())


def encounter_chance(dest_danger: int, hour: int) -> float:
    if dest_danger <= 0:
        return 0.0
    chance = dest_danger * 0.18
    if hour < 6 or hour >= 21:        # 夜間更危險
        chance += 0.10
    return min(0.85, chance)


def travel(char: Character, gamedata: GameData, dest_id: str, time, rng: RNG) -> dict:
    """執行旅行:依運動加速耗時、推進時間、移動、鍛鍊運動。

    回傳 {"foe":遭遇 Creature 或 None, "hours":實際耗時, "base_hours":名目耗時,
          "skill_events":運動升點事件}。遭遇尚未開打 —— 由上層決定接戰/逃避。
    """
    from tesrpg.systems import mastery, party
    links = current_location(char, gamedata).get("links", {})
    base_hours = links[dest_id]
    travel_factor = max(0.5, formulas.athletics_travel_factor(char.skill("athletics"))
                        - mastery.travel_factor_bonus(char, gamedata)
                        - party.passive_capstone_factor(char, gamedata, "travel"))   # 「長途健步」+ 同伴「識途」忠誠頂點,夾 floor 0.5
    hours = max(1, round(base_hours * travel_factor))
    dest = gamedata.location(dest_id)

    foe = None
    if rng.chance(encounter_chance(dest.get("danger", 0), time.hour)):
        foe = combat.random_encounter(gamedata, char.level, rng,
                                      max_danger=dest.get("danger", 1) + 1,
                                      biome=dest.get("biome"))

    time.advance(hours)
    char.location_id = dest_id
    skill_events = progression.use_skill(char, gamedata, "athletics", formulas.ATHLETICS_TRAVEL_XP)
    return {"foe": foe, "hours": hours, "base_hours": base_hours, "skill_events": skill_events}


# --- 商店定價(受 交易 + 魅力 影響)-----------------------------------
def _disposition_factor(char: Character, gamedata: GameData | None = None) -> float:
    base = (char.skill("mercantile") + char.attr("personality") * 0.5) / 150.0
    if gamedata is not None:                       # 里程碑「精算買賣/魅惑交易」議價加成 + 同伴忠誠頂點
        from tesrpg.systems import mastery, party
        base += mastery.merchant_bonus(char, gamedata)
        base += party.passive_capstone_factor(char, gamedata, "barter")   # 同伴「人脈/巧手」忠誠頂點:議價
    return max(0.0, min(1.0, base))


LOCKPICK_OUTSIDER_MARKUP = 2.0   # 開鎖器是盜賊公會的營生:非會員(含敵對)買得到但被坑這麼多倍


def buy_price(char: Character, gamedata: GameData, item_id: str) -> int:
    from tesrpg.systems import factions
    value = gamedata.item(item_id)["value"]
    price = value * (2.2 - _disposition_factor(char, gamedata))
    # 開鎖器只在有盜賊公會的城販售;會員按常價,外人/敵對加價(仍買得到,但較貴)
    if item_id == "lockpick" and not factions.is_member(char, "thieves_guild"):
        price *= LOCKPICK_OUTSIDER_MARKUP
    return max(1, round(price))


def sell_price(char: Character, gamedata: GameData, item_id: str) -> int:
    from tesrpg.systems import factions
    value = gamedata.item(item_id)["value"]
    base = value * (0.3 + _disposition_factor(char, gamedata) * 0.5)
    base *= 1 + factions.sell_bonus(char, gamedata)   # 盜賊公會銷贓加成(階級越高越多)
    return max(1, round(base))


# --- 商店庫存(Skyrim 式:每商人有限數量 + 定時補貨 + 補貨品項有變化)------
# 商人不再是「無限供貨機」:每件商品有有限數量,定時補貨且每次補的量(乃至有無)會變動。
# 這從「供給側」掐住了「買廉價材料 → 煉製 → 高價賣回」的無限金幣套利:一輪只買得到有限的量。
RESTOCK_HOURS = 72        # 商人每約 3 天補一次貨


def _restock_qty(value: int, rng: RNG) -> int:
    """依物品價值分級給補貨量,帶隨機變化(可能為 0 → 不同次補貨的品項有別)。"""
    if value <= 10:               # 廉價消耗品/煉金材料
        return rng.randint(1, 6)
    if value <= 80:               # 中價:藥水、基礎裝備、配件
        return rng.randint(0, 3)
    return rng.randint(0, 1)      # 高價裝備:時常缺貨


def merchant_catalog(gamedata: GameData, loc_id: str) -> list[str]:
    """該地商人「可能販售」的完整品項目錄(world.json 的 merchant_stock)。"""
    return gamedata.location(loc_id).get("merchant_stock", [])


def ensure_stock(char: Character, gamedata: GameData, loc_id: str, time, rng: RNG) -> None:
    """首次造訪或已過補貨時點 → 依目錄重抽當前庫存(數量隨機、可能個別缺貨)。"""
    if not merchant_catalog(gamedata, loc_id):
        return
    now = time.absolute_hours()
    if loc_id in char.shop_restock_at and now < char.shop_restock_at[loc_id]:
        return
    from tesrpg.systems import mastery
    rmult = mastery.restock_mult(char, gamedata)                # 「行商人脈」補貨量倍率

    def _qty(iid):
        q = _restock_qty(gamedata.item(iid)["value"], rng)
        return 0 if q == 0 else max(1, round(q * rmult))        # 保留「擲 0 = 缺貨」的稀缺性(反套利)
    char.shop_stock[loc_id] = {iid: _qty(iid) for iid in merchant_catalog(gamedata, loc_id)}
    char.shop_restock_at[loc_id] = now + RESTOCK_HOURS


def stock_qty(char: Character, loc_id: str, item_id: str) -> int:
    return char.shop_stock.get(loc_id, {}).get(item_id, 0)


def take_stock(char: Character, loc_id: str, item_id: str, n: int = 1) -> None:
    """買走/偷走後扣減庫存(夾在 0)。"""
    cur = char.shop_stock.get(loc_id)
    if cur and item_id in cur:
        cur[item_id] = max(0, cur[item_id] - n)


def in_stock_items(char: Character, gamedata: GameData, loc_id: str) -> list[str]:
    """目錄中目前仍有貨(數量>0)的品項,維持目錄原順序。"""
    return [iid for iid in merchant_catalog(gamedata, loc_id) if stock_qty(char, loc_id, iid) > 0]


# --- 訓練師 -------------------------------------------------------------
def train_cost(skill_level: int) -> int:
    return max(20, skill_level * 8)


# --- 法師公會 -----------------------------------------------------------
def spell_price(gamedata: GameData, spell_id: str) -> int:
    return max(25, gamedata.spells[spell_id]["cost"] * 12)


# --- 鐵匠修理 -----------------------------------------------------------
def repair_fee() -> int:
    return 15
