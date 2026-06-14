"""房產:收納倉庫 + 最佳休息 +「精神飽滿」增益。

- 收納倉庫(`house_stash`):存物**不計隨身負重**(total_weight 只算 inventory)。存入禁止
  正穿戴/手持的裝備(避免漏 recompute);取出以負重(含鞍袋)為閘。
- 最佳休息:免費全回(回復邏輯在 main.action_rest_home),並設「精神飽滿」期。
- 精神飽滿(`well_rested_until` 權威 + `well_rested` 快取):一段時間技能 xp 加速
  (倍率在 formulas.WELL_RESTED_XP_MULT,由 progression.use_skill 讀快取);不寫 base。

加房產純改 `data/houses.json`。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import inventory


def owns(char: Character, loc_id: str) -> bool:
    return loc_id in getattr(char, "houses_owned", [])


def buy(char: Character, gamedata: GameData, loc_id: str) -> bool:
    """購置房產(呼叫端已查金幣/在城)。"""
    if not gamedata.house_at(loc_id) or owns(char, loc_id):
        return False
    char.houses_owned.append(loc_id)
    return True


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
def set_well_rested(char: Character, now: int) -> None:
    """最佳休息後設精神飽滿(再休息=刷新不疊加)。"""
    char.well_rested_until = now + formulas.WELL_RESTED_HOURS
    char.well_rested = True


def refresh_well_rested(char: Character, now: int) -> bool:
    """依到期時刷新現行快取(game_loop 頂端呼叫);回傳是否仍精神飽滿。"""
    char.well_rested = getattr(char, "well_rested_until", 0) > now
    return char.well_rested
