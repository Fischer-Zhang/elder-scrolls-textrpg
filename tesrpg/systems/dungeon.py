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
    """含里程碑「撬鎖名家」下限的實際撬鎖成功率(顯示與擲骰共用,確保一致)。
    幸運「時來運轉」微升成功率(base-40 中性 +0)。"""
    from tesrpg import formulas
    chance = min(0.95, pick_lock_chance(char.skill("security"), lock_level)
                 + formulas.luck_fortune(char.attr("luck")))
    return max(chance, mastery.lock_floor(char, gamedata))


LOCKPICK_ITEM = "lockpick"
LOCKPICK_FATIGUE = 2    # 每次撬鎖嘗試的少量體力;主閘改為「開鎖器」(失敗折斷),非時間


def pick_lock(char: Character, gamedata: GameData, lock_level: int, rng: RNG) -> dict:
    """嘗試撬鎖一次。**需要開鎖器,每次嘗試耗一根**(成功=用掉、失敗=折斷),**不耗時**、僅扣少量體力。
    成功才鍛鍊安全技能(learn-by-doing);失敗不給 xp。**每次嘗試都耗一根開鎖器 → security xp 有金幣閘**
    (杜絕高技能者免費重撬同鎖刷 security;開鎖器=這道反 min-max 的成本閘,以金幣換取)。
    「塔之鑰」(塔座能力)充能則必定成功、消耗之 —— 招牌仍免開鎖器/免體力/免耗時。
    回傳含 hours(恆 0)/tired/no_pick(無開鎖器)/broke_pick(本次失敗折斷),供呼叫端提示。
    """
    chance = effective_pick_lock_chance(char, gamedata, lock_level)
    base_xp = gamedata.skills["security"]["practice"]["xp"]
    if char.tower_key_charge:
        char.tower_key_charge = False
        skill_events = progression.use_skill(char, gamedata, "security", base_xp)
        return {"success": True, "chance": 1.0, "tower_key": True, "no_pick": False,
                "broke_pick": False, "hours": 0, "tired": False, "skill_events": skill_events}
    if inventory.count_item(char, LOCKPICK_ITEM) <= 0:            # 沒有開鎖器 → 撬不了
        return {"success": False, "chance": chance, "tower_key": False, "no_pick": True,
                "broke_pick": False, "hours": 0, "tired": False, "skill_events": []}
    tired = char.fatigue < LOCKPICK_FATIGUE
    char.fatigue = max(0, char.fatigue - LOCKPICK_FATIGUE)
    success = rng.chance(chance)
    from tesrpg.systems import mastery
    keep = (not success) and rng.chance(mastery.pick_keep_chance(char, gamedata))   # 「巧手不折」失敗不折
    if not keep:
        inventory.remove_item(char, LOCKPICK_ITEM, 1)           # 每次嘗試耗一根(成功也耗 → xp 的金幣閘)
    skill_events = progression.use_skill(char, gamedata, "security", base_xp) if success else []
    return {"success": success, "chance": chance, "tower_key": False, "no_pick": False,
            "broke_pick": not success and not keep, "hours": 0, "tired": tired, "skill_events": skill_events}


def open_container(char: Character, gamedata: GameData, container: dict, rng: RNG) -> dict:
    """開啟(已解鎖的)容器,內容入袋(幸運「戰利豐厚」加權)。回傳 {"gold", "items":[(id,qty)]}。"""
    from tesrpg import formulas
    result = loot.resolve_loot(container.get("loot", []), rng,
                               formulas.luck_loot_factor(char.attr("luck")))
    char.gold += result["gold"]
    for item_id, qty in result["items"]:
        inventory.add_item(char, item_id, qty)
    return result
