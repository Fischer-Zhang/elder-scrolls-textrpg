"""地城輔助:撬鎖(安全技能)與開箱取寶。

地城的逐房間推進是互動流程,放在 main.py;這裡提供可測的純規則。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import inventory, loot, mastery, progression


def pick_lock_chance(security_skill: int, lock_level: int) -> float:
    return max(0.05, min(0.95, 0.10 + (security_skill - lock_level) * 0.03))


def effective_pick_lock_chance(char: Character, gamedata: GameData, lock_level: int) -> float:
    """含里程碑「撬鎖名家」下限的實際撬鎖成功率(顯示與擲骰共用,確保一致)。"""
    chance = pick_lock_chance(char.skill("security"), lock_level)
    return max(chance, mastery.lock_floor(char, gamedata))


def pick_lock(char: Character, gamedata: GameData, lock_level: int, rng: RNG) -> dict:
    """嘗試撬鎖一次。無論成敗都鍛鍊安全技能(learn-by-doing)。

    每次「真正擲骰」的嘗試會付出安全 practice 的體力 + 時間成本(時間由呼叫端推進),
    讓撬鎖不再是零代價的無限重試/免費刷 security。
    若角色蓄有「塔之鑰」(塔座能力)充能,則必定成功並消耗之 —— 此招牌仍**免成本、免耗時**。
    回傳含 hours/tired,供呼叫端推進時間與提示。
    """
    chance = effective_pick_lock_chance(char, gamedata, lock_level)
    if char.tower_key_charge:
        char.tower_key_charge = False
        xp = gamedata.skills["security"]["practice"]["xp"]
        skill_events = progression.use_skill(char, gamedata, "security", xp)
        return {"success": True, "chance": 1.0, "tower_key": True,
                "hours": 0, "tired": False, "skill_events": skill_events}
    xp, hours, tired = progression.practice_cost(char, gamedata, "security")
    success = rng.chance(chance)
    skill_events = progression.use_skill(char, gamedata, "security", xp)
    return {"success": success, "chance": chance, "tower_key": False,
            "hours": hours, "tired": tired, "skill_events": skill_events}


def open_container(char: Character, gamedata: GameData, container: dict, rng: RNG) -> dict:
    """開啟(已解鎖的)容器,內容入袋。回傳 {"gold", "items":[(id,qty)]}。"""
    result = loot.resolve_loot(container.get("loot", []), rng)
    char.gold += result["gold"]
    for item_id, qty in result["items"]:
        inventory.add_item(char, item_id, qty)
    return result
