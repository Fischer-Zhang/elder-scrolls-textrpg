"""房產:收納倉庫 + 最佳休息 +「精神飽滿」增益 + 擴建(R110 家園基地化)。

- 收納倉庫(`house_stash`):存物**不計隨身負重**(total_weight 只算 inventory)。存入禁止
  正穿戴/手持的裝備(避免漏 recompute);取出以負重(含鞍袋)為閘。
- 最佳休息:免費全回(回復邏輯在 main.action_house),並設「精神飽滿」期。
- 精神飽滿(`well_rested_until` 權威 + `well_rested` 快取):一段時間技能 xp 加速
  (倍率在 formulas.WELL_RESTED_XP_MULT,由 progression.use_skill 讀快取);不寫 base。
- 擴建(R110):houses.json `tier`(1 小屋/2 宅邸/3 莊園)決定設施格位;目錄在
  data/house_upgrades.json(鏡像 R106C necromancy.json 買斷模式)。**嚴格金幣沉**:
  永不退款、重複購買擋。三設施:
  * 藥草園 `garden` —— 每 GARDEN_COOLDOWN_HOURS 可採收一批本城生態(biome→ecology 池)
    的**尋常**草藥(`GARDEN_VALUE_CAP` 排除 moon_sugar/nirnroot/全 rare = 反印鈔承重界);
    固定預算不吃 scout(自家後院,守 R93/R94 野採的偵查 niche);**零技能 XP**(防每日
    免費 XP 滴灌);無 banking(時間戳,錯過不累積)。
  * 舒適臥房 `bedroom` —— 在家安睡的精神飽滿**時長** 24→BEDROOM_WELL_RESTED_HOURS
    (只時長;倍率 WELL_RESTED_XP_MULT 不動;巢穴/藏身處走預設參數逐位元組同)。
  * 在地商誼 `trade_pact` —— 本省商人買價 ×(1−TRADE_PACT_DISCOUNT)(單向只買價;
    掛在 world.buy_price 反套利地板之前 → 任何疊加都不可能買賣倒掛;省內布林不疊加)。

加房產純改 `data/houses.json`;加擴建=改 `data/house_upgrades.json` + 本檔效果掛點。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import inventory

# --- 擴建常數(R110;平衡值皆使用者拍板,調整先問)-------------------------
SLOTS_BY_TIER = {1: 2, 2: 3, 3: 4}   # T1 三選二取捨;T2/T3 現可全裝,T3 空位=日後目錄擴充預留
TIER_NAMES = {1: "小屋", 2: "宅邸", 3: "莊園"}
GARDEN_COOLDOWN_HOURS = 24           # 每日採收(拍板)
GARDEN_BUDGET = 6                    # 固定預算(刻意不吃 scout)
GARDEN_VALUE_CAP = 10                # 🔴 承重界:只長 value ≤ 10 的尋常材料(珍稀野外才有)
BEDROOM_WELL_RESTED_HOURS = 36       # 臥房精神飽滿時長(基礎 24;只時長不動倍率)
TRADE_PACT_DISCOUNT = 0.05           # 在地商誼買價折扣(單向;省內布林)


def owns(char: Character, loc_id: str) -> bool:
    return loc_id in getattr(char, "houses_owned", [])


def buy(char: Character, gamedata: GameData, loc_id: str) -> bool:
    """購置房產(呼叫端已查金幣/在城)。"""
    if not gamedata.house_at(loc_id) or owns(char, loc_id):
        return False
    char.houses_owned.append(loc_id)
    return True


# --- 擴建(R110)---------------------------------------------------------
def tier(gamedata: GameData, loc_id: str) -> int:
    """房產等級(1 小屋/2 宅邸/3 莊園;缺 tier 或非法值 → 1)。"""
    t = (gamedata.house_at(loc_id) or {}).get("tier", 1)
    return t if t in SLOTS_BY_TIER else 1


def tier_name(gamedata: GameData, loc_id: str) -> str:
    return TIER_NAMES[tier(gamedata, loc_id)]


def slots(gamedata: GameData, loc_id: str) -> int:
    """該房產的設施格位數(由 tier 決定)。"""
    return SLOTS_BY_TIER[tier(gamedata, loc_id)]


def upgrades(char: Character, loc_id: str) -> list:
    """該房產已購擴建 id 原始清單(含可能的陳舊 id;槽位/效果判定用 owned_upgrades/has_upgrade)。"""
    return getattr(char, "house_upgrades", {}).get(loc_id, [])


def owned_upgrades(char: Character, gamedata: GameData, loc_id: str) -> list:
    """已購且仍在目錄中的擴建(未知 id inert:不佔格位、不生效,但**保留不刪** —— 比照
    house_stash 對毀損 id 的寬容,目錄若移除某擴建不回溯銷毀玩家金幣)。"""
    return [u for u in upgrades(char, loc_id) if u in gamedata.house_upgrades]


def has_upgrade(char: Character, gamedata: GameData, loc_id: str, uid: str) -> bool:
    return uid in gamedata.house_upgrades and uid in upgrades(char, loc_id)


def available_upgrades(char: Character, gamedata: GameData, loc_id: str) -> list:
    """尚可添置的擴建 id(未購 + 有空格位);未擁房 → []。"""
    if not owns(char, loc_id):
        return []
    owned = upgrades(char, loc_id)
    if len(owned_upgrades(char, gamedata, loc_id)) >= slots(gamedata, loc_id):
        return []
    return [uid for uid in gamedata.house_upgrades if uid not in owned]


def buy_upgrade(char: Character, gamedata: GameData, loc_id: str, uid: str, now: int) -> bool:
    """添置擴建(呼叫端已查金幣/扣款,鏡像 buy());閘:擁房 + 目錄內 + 未購 + 有空格位。
    購入藥草園即設下次採收時間(now+冷卻)—— 防「買完即刻採收」。"""
    if uid not in available_upgrades(char, gamedata, loc_id):
        return False
    char.house_upgrades.setdefault(loc_id, []).append(uid)
    if uid == "garden":
        char.house_garden_at[loc_id] = now + GARDEN_COOLDOWN_HOURS
    return True


# --- 藥草園(R110)-------------------------------------------------------
def garden_pool_id(gamedata: GameData, loc_id: str) -> str | None:
    """藥草園抽取池 = 房產所在地的 biome 對映生態池(無 biome/無對應池 → None,採收優雅停用)。"""
    biome = (gamedata.world["locations"].get(loc_id) or {}).get("biome")
    return biome if biome in (gamedata.ecology.get("pools") or {}) else None


def garden_wait(char: Character, loc_id: str, now: int) -> int:
    """距下次可採收的小時數(0=可採)。"""
    return max(0, int(getattr(char, "house_garden_at", {}).get(loc_id, 0)) - now)


def garden_ready_notice(char: Character, gamedata: GameData, now: int, seen: set) -> str | None:
    """R114 F6:玩家正身處「自有房產且藥草園已熟」的城 → 一次性提示(session 暫態 seen 去重,
    key=(loc,採收週期)每輪至多一報,比照 R111 reinfest_notices/R55 成就通知)。純讀。"""
    lid = getattr(char, "location_id", "")
    if not owns(char, lid) or not has_upgrade(char, gamedata, lid, "garden"):
        return None
    if garden_wait(char, lid, now) > 0 or garden_pool_id(gamedata, lid) is None:
        return None
    key = (lid, int(getattr(char, "house_garden_at", {}).get(lid, 0)))
    if key in seen:
        return None
    seen.add(key)
    return f"🌿 你在{(gamedata.house_at(lid) or {}).get('name', '家')}的藥草園長成了,可以採收了。"


def harvest_garden(char: Character, gamedata: GameData, loc_id: str, now: int, rng) -> list | None:
    """採收藥草園:無藥草園/未到時/無對應池 → None;否則抽取(固定預算 + value cap)→
    入背包、設下次採收時間,回 [(item_id, qty), ...]。🔴 零技能 XP(刻意;專測鎖)。"""
    if not has_upgrade(char, gamedata, loc_id, "garden"):
        return None
    if garden_wait(char, loc_id, now) > 0:
        return None
    pool_id = garden_pool_id(gamedata, loc_id)
    if pool_id is None:
        return None
    from tesrpg.systems import events   # 區域 import(沿用本專案就地 import 慣例)
    picks = events.forage_pool_draw(char, gamedata, pool_id, rng,
                                    budget=GARDEN_BUDGET, value_cap=GARDEN_VALUE_CAP)
    for iid, qty in picks:
        inventory.add_item(char, iid, qty)
    char.house_garden_at[loc_id] = now + GARDEN_COOLDOWN_HOURS
    return picks


# --- 倉庫(stash) -------------------------------------------------------
def stash(char: Character, loc_id: str) -> list:
    """該房產的倉庫堆疊清單(就地建立)。"""
    return char.house_stash.setdefault(loc_id, [])


def stash_count(char: Character, loc_id: str, item_id: str) -> int:
    return sum(s["qty"] for s in char.house_stash.get(loc_id, []) if s["id"] == item_id)


def is_equipped(char: Character, item_id: str) -> bool:
    """正穿戴/手持(主手/副手/護甲/飾品)→ 不可存入倉庫(免漏 recompute)。"""
    return (char.weapon == item_id or getattr(char, "offhand", "") == item_id
            or item_id in char.equipped.values())


def _stash_add(char: Character, loc_id: str, item_id: str, qty: int) -> None:
    lst = stash(char, loc_id)
    for s in lst:
        if s["id"] == item_id:
            s["qty"] += qty
            return
    lst.append({"id": item_id, "qty": qty})


def _stash_remove(char: Character, loc_id: str, item_id: str, qty: int) -> None:
    lst = char.house_stash.get(loc_id, [])
    for s in lst:
        if s["id"] == item_id:
            s["qty"] -= qty
            if s["qty"] <= 0:
                lst.remove(s)
            return


def deposit(char: Character, gamedata: GameData, loc_id: str, item_id: str, qty: int = 1) -> bool:
    """背包 → 倉庫。禁存正穿戴/手持裝備;背包數量不足則失敗。"""
    if is_equipped(char, item_id):
        return False
    if inventory.count_item(char, item_id) < qty:
        return False
    inventory.remove_item(char, item_id, qty)
    _stash_add(char, loc_id, item_id, qty)
    return True


def withdraw(char: Character, gamedata: GameData, loc_id: str, item_id: str, qty: int = 1) -> bool:
    """倉庫 → 背包(以負重為閘,含鞍袋)。"""
    if stash_count(char, loc_id, item_id) < qty:
        return False
    # 毀損/未知 id(內容被移除的舊存檔)→ 略過負重檢查(無重量),仍可取回背包,不崩潰
    if gamedata.item_or_none(item_id) is not None and not inventory.can_carry(char, gamedata, item_id, qty):
        return False
    _stash_remove(char, loc_id, item_id, qty)
    inventory.add_item(char, item_id, qty)
    return True


# --- 精神飽滿(well-rested)---------------------------------------------
def set_well_rested(char: Character, now: int, hours: int | None = None) -> None:
    """最佳休息後設精神飽滿(再休息=刷新不疊加)。`hours=None` → 預設時長
    (formulas.WELL_RESTED_HOURS)—— 巢穴/藏身處等既有呼叫端逐位元組同(R110)。"""
    char.well_rested_until = now + (formulas.WELL_RESTED_HOURS if hours is None else hours)
    char.well_rested = True


def rest_hours(char: Character, gamedata: GameData, loc_id: str) -> int:
    """在此房產安睡的精神飽滿時長(舒適臥房 → 延時;只時長,倍率不動)。"""
    if has_upgrade(char, gamedata, loc_id, "bedroom"):
        return BEDROOM_WELL_RESTED_HOURS
    return formulas.WELL_RESTED_HOURS


def refresh_well_rested(char: Character, now: int) -> bool:
    """依到期時刷新現行快取(game_loop 頂端呼叫);回傳是否仍精神飽滿。"""
    char.well_rested = getattr(char, "well_rested_until", 0) > now
    return char.well_rested


# --- 在地商誼(R110)------------------------------------------------------
def province_discount(char: Character, gamedata: GameData) -> float:
    """當前所在省有「已購在地商誼」的自有房產 → TRADE_PACT_DISCOUNT,否則 0.0。
    省內布林不疊加;無房/無商誼 → 0.0(buy_price ×1.0 恆等 → 既有物價逐位元組同)。"""
    locs = gamedata.world["locations"]
    here = (locs.get(getattr(char, "location_id", "")) or {}).get("province")
    if not here:
        return 0.0
    for lid in getattr(char, "houses_owned", []):
        if (has_upgrade(char, gamedata, lid, "trade_pact")
                and (locs.get(lid) or {}).get("province") == here):
            return TRADE_PACT_DISCOUNT
    return 0.0


# --- 載入遷移(R110)------------------------------------------------------
def ensure_housing_fields(char: Character, now: int) -> None:
    """冪等自癒兩個 R110 欄位:型別矯正 + **去重**(毀損檔重複 id 會虛佔格位+灌 legacy 分)
    + 採收時間戳上夾(治毀損的未來時間戳;0/過去值=可採本就合法,不在此列)。**未知
    loc/upgrade id 保留不刪**(inert;比照 house_stash 對毀損 id 的寬容 —— 刪除=回溯銷毀
    玩家金幣)。順手型別自癒 `houses_owned`(R110 起 `province_discount` 於每次 buy_price
    迭代它 —— 毀損成 null/非 list 會使全商店定價崩)。"""
    ho = getattr(char, "houses_owned", None)
    if not isinstance(ho, list):
        char.houses_owned = []
    ups = getattr(char, "house_upgrades", None)
    char.house_upgrades = ups if isinstance(ups, dict) else {}
    for lid, lst in list(char.house_upgrades.items()):
        if not isinstance(lst, list):
            char.house_upgrades[lid] = []
        else:   # 去重保序(dict.fromkeys):毀損 ["garden","garden"] → ["garden"]
            char.house_upgrades[lid] = list(dict.fromkeys(u for u in lst if isinstance(u, str)))
    gat = getattr(char, "house_garden_at", None)
    char.house_garden_at = gat if isinstance(gat, dict) else {}
    cap = now + GARDEN_COOLDOWN_HOURS
    for lid, v in list(char.house_garden_at.items()):
        try:   # OverflowError:json.load 接受 Infinity 字面量 → int(inf) 拋之(非 Type/Value)
            char.house_garden_at[lid] = min(int(v), cap)
        except (TypeError, ValueError, OverflowError):
            char.house_garden_at.pop(lid)
