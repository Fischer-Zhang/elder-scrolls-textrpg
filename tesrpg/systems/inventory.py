"""背包與裝備:物品堆疊、負重、裝備武器/護甲、使用藥水。

約定:
  - char.inventory = [{"id": item_id, "qty": n}, ...](堆疊)
  - char.equipped  = {slot: item_id}  穿戴中的護甲(item 仍留在 inventory,只是被標記為穿戴)
  - char.weapon    = item_id          手持武器('fists' 為內建,不在 inventory 內)
  負重計入所有 inventory 堆疊(含穿戴中的護甲);徒手不計重。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats

ARMOR_SLOTS = ["helmet", "cuirass", "gauntlets", "boots", "shield"]


# --- 增減 ---------------------------------------------------------------
def add_item(char: Character, item_id: str, qty: int = 1) -> None:
    for stack in char.inventory:
        if stack["id"] == item_id:
            stack["qty"] += qty
            return
    char.inventory.append({"id": item_id, "qty": qty})


def count_item(char: Character, item_id: str) -> int:
    return sum(s["qty"] for s in char.inventory if s["id"] == item_id)


def remove_item(char: Character, item_id: str, qty: int = 1) -> bool:
    for stack in char.inventory:
        if stack["id"] == item_id:
            if stack["qty"] < qty:
                return False
            stack["qty"] -= qty
            if stack["qty"] <= 0:
                char.inventory.remove(stack)
                # 移除最後一件 → 一併卸下
                if char.weapon == item_id:
                    char.weapon = "fists"
                for slot, wid in list(char.equipped.items()):
                    if wid == item_id:
                        del char.equipped[slot]
            return True
    return False


# --- 負重 ---------------------------------------------------------------
def total_weight(char: Character, gamedata: GameData) -> float:
    return sum(gamedata.item(s["id"])["weight"] * s["qty"] for s in char.inventory)


def max_weight(char: Character) -> int:
    return formulas.max_encumbrance(char.attr("strength"))


def can_carry(char: Character, gamedata: GameData, item_id: str, qty: int = 1) -> bool:
    added = gamedata.item(item_id)["weight"] * qty
    return total_weight(char, gamedata) + added <= max_weight(char)


def is_overencumbered(char: Character, gamedata: GameData) -> bool:
    return total_weight(char, gamedata) > max_weight(char)


# --- 裝備 ---------------------------------------------------------------
def equip_weapon(char: Character, gamedata: GameData, item_id: str) -> bool:
    if gamedata.item(item_id).get("kind") != "weapon":
        return False
    if count_item(char, item_id) <= 0:
        return False
    char.weapon = item_id
    return True


def equip_armor(char: Character, gamedata: GameData, item_id: str) -> bool:
    d = gamedata.item(item_id)
    if d.get("kind") != "armor" or count_item(char, item_id) <= 0:
        return False
    char.equipped[d["slot"]] = item_id
    return True


def unequip(char: Character, slot: str) -> None:
    char.equipped.pop(slot, None)


# --- 武器塗毒 -----------------------------------------------------------
def poison_charges(char: Character) -> int:
    """塗一次毒能附著的攻擊次數(隨煉金技能提升)。"""
    return max(1, 1 + char.skill("alchemy") // 30)


def coat_weapon(char: Character, gamedata: GameData, poison_id: str) -> bool:
    """把一瓶毒藥塗到手持武器上(徒手不可塗)。成功回傳 True。"""
    d = gamedata.item(poison_id)
    if d.get("kind") != "poison" or count_item(char, poison_id) <= 0 or char.weapon == "fists":
        return False
    char.weapon_poison = {"status": d["poison"], "charges": poison_charges(char), "name": d["name"]}
    remove_item(char, poison_id, 1)
    return True


def worn_armor_rating(char: Character, gamedata: GameData) -> int:
    """穿戴護甲的名目護甲值(不含耐久折損,供 UI 顯示)。"""
    return sum(gamedata.item(i)["armor_rating"] for i in char.equipped.values())


# --- 耐久 (condition) ---------------------------------------------------
def _cond_mult(condition: float) -> float:
    """耐久 → 效能倍率(100→1.0、0→0.5)。"""
    return 0.5 + 0.5 * max(0.0, min(100.0, condition)) / 100.0


def weapon_damage_mult(char: Character) -> float:
    return _cond_mult(char.weapon_condition)


def effective_armor_rating(char: Character, gamedata: GameData) -> float:
    """計入各部位耐久折損後的實際護甲值。"""
    total = 0.0
    for slot, iid in char.equipped.items():
        cond = char.armor_condition.get(slot, 100.0)
        total += gamedata.item(iid)["armor_rating"] * _cond_mult(cond)
    return total


def degrade_weapon(char: Character, amount: float = 1.0) -> None:
    if char.weapon != "fists":
        char.weapon_condition = max(0.0, char.weapon_condition - amount)


def degrade_random_armor(char: Character, rng, amount: float = 1.5) -> None:
    if not char.equipped:
        return
    slot = rng.choice(list(char.equipped.keys()))
    cur = char.armor_condition.get(slot, 100.0)
    char.armor_condition[slot] = max(0.0, cur - amount)


def repairable_cap(armorer_skill: int) -> float:
    """Armorer 技能決定能修到幾成(技能 100 才能修到 100%)。"""
    return min(100.0, 50.0 + armorer_skill * 0.5)


def repair_all(char: Character, cap: float = 100.0) -> None:
    if char.weapon != "fists":
        char.weapon_condition = max(char.weapon_condition, cap)
    for slot in char.equipped:
        char.armor_condition[slot] = max(char.armor_condition.get(slot, 100.0), cap)


def dominant_weight_class(char: Character, gamedata: GameData) -> str | None:
    """穿戴中以重甲還是輕甲為主?無護甲回傳 None。"""
    counts = {"heavy": 0, "light": 0}
    for i in char.equipped.values():
        wc = gamedata.item(i).get("weight_class")
        if wc in counts:
            counts[wc] += 1
    if counts["heavy"] == counts["light"] == 0:
        return None
    return "heavy" if counts["heavy"] >= counts["light"] else "light"


# --- 使用 ---------------------------------------------------------------
def use_item(char: Character, gamedata: GameData, item_id: str) -> str | None:
    """使用消耗品(目前:藥水)。回傳給玩家的訊息,不可用回傳 None。"""
    d = gamedata.item(item_id)
    if d.get("kind") != "potion" or count_item(char, item_id) <= 0:
        return None
    eff = d["effect"]
    if eff["type"] == "heal":
        before = char.health
        char.health = min(char.max_health, char.health + eff["magnitude"])
        gained = int(char.health - before)
        msg = f"飲下{d['name']},回復 {gained} 點生命。"
    elif eff["type"] == "restore_magicka":
        before = char.magicka
        char.magicka = min(char.max_magicka, char.magicka + eff["magnitude"])
        gained = int(char.magicka - before)
        msg = f"飲下{d['name']},回復 {gained} 點魔力。"
    elif eff["type"] == "restore_fatigue":
        before = char.fatigue
        char.fatigue = min(char.max_fatigue, char.fatigue + eff["magnitude"])
        gained = int(char.fatigue - before)
        msg = f"飲下{d['name']},回復 {gained} 點體力。"
    else:
        return None
    remove_item(char, item_id, 1)
    stats.clamp_resources(char)
    return msg
