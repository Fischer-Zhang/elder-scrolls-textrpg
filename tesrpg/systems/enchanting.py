"""附魔:用充能靈魂石把元素傷害附到武器上。

靈魂石由「擒魂術」在擊殺時取得(見 magic.soul_gem_for)。
附魔威力隨靈魂等級與神秘 (mysticism) 技能提升,並鍛鍊神秘。
產出的是「附魔武器」(見 synth)。
"""

from __future__ import annotations

from tesrpg import synth
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import inventory, progression

ELEMENTS = ["fire", "frost", "shock"]
FORTIFY_STATS = ["health", "magicka", "fatigue"]   # 護甲附魔可強化的最大資源
ENCHANT_XP = 1.0


def filled_soul_gems(char: Character, gamedata: GameData) -> list[str]:
    return [s["id"] for s in char.inventory if gamedata.item(s["id"]).get("kind") == "soul_gem"]


def enchantable_weapons(char: Character, gamedata: GameData) -> list[str]:
    out = []
    for s in char.inventory:
        d = gamedata.item(s["id"])
        if d.get("kind") == "weapon" and not d.get("enchant"):
            out.append(s["id"])
    return out


def enchantable_armor(char: Character, gamedata: GameData) -> list[str]:
    out = []
    for s in char.inventory:
        d = gamedata.item(s["id"])
        if d.get("kind") == "armor" and not d.get("enchant"):
            out.append(s["id"])
    return out


def enchant_magnitude(soul: int, mysticism_skill: int) -> int:
    return max(1, round(soul * 3 * (0.6 + mysticism_skill / 100.0)))


def enchant_weapon(char: Character, gamedata: GameData, base_weapon: str,
                   element: str, gem_id: str) -> dict:
    """以靈魂石為武器附上元素傷害。回傳 {"ok","message","item_id"?,"skill_events"}。"""
    if inventory.count_item(char, base_weapon) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少武器或靈魂石。", "skill_events": []}
    if element not in ELEMENTS:
        return {"ok": False, "message": "未知的元素。", "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    mag = enchant_magnitude(soul, char.skill("mysticism"))

    inventory.remove_item(char, base_weapon, 1)
    inventory.remove_item(char, gem_id, 1)
    item_id = synth.enchant_weapon_id(base_weapon, element, mag)
    inventory.add_item(char, item_id, 1)
    events = progression.use_skill(char, gamedata, "mysticism", ENCHANT_XP)
    return {"ok": True, "message": f"靈魂石碎裂,{gamedata.item(item_id)['name']} 完成了!",
            "item_id": item_id, "skill_events": events}


def enchant_armor(char: Character, gamedata: GameData, base_armor: str,
                  stat: str, gem_id: str) -> dict:
    """以靈魂石為護甲附上「穿戴時強化最大資源」。回傳同 enchant_weapon。"""
    if inventory.count_item(char, base_armor) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少護甲或靈魂石。", "skill_events": []}
    if stat not in FORTIFY_STATS:
        return {"ok": False, "message": "未知的強化項。", "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    mag = enchant_magnitude(soul, char.skill("mysticism"))

    inventory.remove_item(char, base_armor, 1)
    inventory.remove_item(char, gem_id, 1)
    item_id = synth.enchant_armor_id(base_armor, stat, mag)
    inventory.add_item(char, item_id, 1)
    events = progression.use_skill(char, gamedata, "mysticism", ENCHANT_XP)
    return {"ok": True, "message": f"靈魂石碎裂,{gamedata.item(item_id)['name']} 完成了!",
            "item_id": item_id, "skill_events": events}
