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
RESIST_ELEMENTS = ["fire", "frost", "shock", "poison", "magic"]   # 飾品可抗的元素

# 飾品附魔的 4 種型別(供 UI 列表):(kind, 顯示名)
JEWELRY_KINDS = [("skill", "強化技能"), ("attr", "強化屬性"),
                 ("resist", "抗元素"), ("res", "強化最大資源")]
# 護甲附魔型別(刻意不含 attr:屬性 fortify 最強、會疊乘衍生資源,留給飾品 3 槽)
ARMOR_KINDS = [("res", "強化最大資源"), ("skill", "強化技能"), ("resist", "抗元素")]
# 武器命中觸發附魔型別
WEAPON_STATUS_KINDS = [("vampiric", "吸血"), ("paralyze", "麻痺"), ("regen", "再生")]


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


def enchantable_jewelry(char: Character, gamedata: GameData) -> list[str]:
    out = []
    for s in char.inventory:
        d = gamedata.item(s["id"])
        if d.get("kind") == "jewelry" and not d.get("enchant"):
            out.append(s["id"])
    return out


def jewelry_magnitude(kind: str, soul: int, mysticism_skill: int) -> int:
    """各型別的附魔強度(屬性最珍貴給最少、抗性以百分比給較多)。"""
    base = 0.5 + mysticism_skill / 100.0
    factor = {"skill": 2.0, "attr": 1.2, "resist": 5.0, "res": 3.0}[kind]
    floor = 2 if kind == "resist" else 1
    return max(floor, round(soul * factor * base))


def enchant_jewelry(char: Character, gamedata: GameData, base_jewelry: str,
                    kind: str, param: str, gem_id: str) -> dict:
    """為飾品附上 強化技能/屬性/抗元素/強化資源。回傳同 enchant_weapon。"""
    if inventory.count_item(char, base_jewelry) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少飾品或靈魂石。", "hours": 0, "tired": False, "skill_events": []}
    if kind not in ("skill", "attr", "resist", "res"):
        return {"ok": False, "message": "未知的附魔型別。", "hours": 0, "tired": False, "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    from tesrpg.systems import mastery
    mag = round(jewelry_magnitude(kind, soul, char.skill("mysticism")) * (1 + mastery.enchant_potency(char, gamedata)))

    inventory.remove_item(char, base_jewelry, 1)
    inventory.remove_item(char, gem_id, 1)
    item_id = synth.enchant_jewelry_id(base_jewelry, kind, param, mag)
    inventory.add_item(char, item_id, 1)
    xp, hours, tired = progression.practice_cost(char, gamedata, "mysticism")
    events = progression.use_skill(char, gamedata, "mysticism", xp)
    return {"ok": True, "message": f"靈魂石碎裂,{gamedata.item(item_id)['name']} 完成了!",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events}


def enchant_weapon(char: Character, gamedata: GameData, base_weapon: str,
                   element: str, gem_id: str) -> dict:
    """以靈魂石為武器附上元素傷害。回傳 {"ok","message","item_id"?,"skill_events"}。"""
    if inventory.count_item(char, base_weapon) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少武器或靈魂石。", "hours": 0, "tired": False, "skill_events": []}
    if element not in ELEMENTS:
        return {"ok": False, "message": "未知的元素。", "hours": 0, "tired": False, "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    from tesrpg.systems import mastery
    mag = round(enchant_magnitude(soul, char.skill("mysticism")) * (1 + mastery.enchant_potency(char, gamedata)))

    inventory.remove_item(char, base_weapon, 1)
    inventory.remove_item(char, gem_id, 1)
    item_id = synth.enchant_weapon_id(base_weapon, element, mag)
    inventory.add_item(char, item_id, 1)
    xp, hours, tired = progression.practice_cost(char, gamedata, "mysticism")
    events = progression.use_skill(char, gamedata, "mysticism", xp)
    return {"ok": True, "message": f"靈魂石碎裂,{gamedata.item(item_id)['name']} 完成了!",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events}


def armor_magnitude(kind: str, soul: int, mysticism_skill: int) -> int:
    """護甲附魔強度:res 沿用 enchant_magnitude(資源附魔數值零位移);skill/resist 用略低於飾品的
    曲線(skill 1.5 vs 飾品 2.0、resist 4.0 vs 5.0)→ 飾品仍是技能 fortify 首選、軟化多件疊加上限。"""
    if kind == "res":
        return enchant_magnitude(soul, mysticism_skill)
    base = 0.5 + mysticism_skill / 100.0
    factor = {"skill": 1.5, "resist": 4.0}[kind]
    floor = 2 if kind == "resist" else 1
    return max(floor, round(soul * factor * base))


def enchant_armor(char: Character, gamedata: GameData, base_armor: str,
                  kind: str, param: str, gem_id: str) -> dict:
    """以靈魂石為護甲附上 強化資源/技能/抗元素(res/skill/resist)。回傳同 enchant_weapon。"""
    if inventory.count_item(char, base_armor) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少護甲或靈魂石。", "hours": 0, "tired": False, "skill_events": []}
    if kind not in ("res", "skill", "resist"):
        return {"ok": False, "message": "未知的附魔型別。", "hours": 0, "tired": False, "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    from tesrpg.systems import mastery
    mag = round(armor_magnitude(kind, soul, char.skill("mysticism")) * (1 + mastery.enchant_potency(char, gamedata)))

    inventory.remove_item(char, base_armor, 1)
    inventory.remove_item(char, gem_id, 1)
    item_id = synth.enchant_armor_id(base_armor, kind, param, mag)
    inventory.add_item(char, item_id, 1)
    xp, hours, tired = progression.practice_cost(char, gamedata, "mysticism")
    events = progression.use_skill(char, gamedata, "mysticism", xp)
    return {"ok": True, "message": f"靈魂石碎裂,{gamedata.item(item_id)['name']} 完成了!",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events}


def enchant_weapon_status(char: Character, gamedata: GameData, base_weapon: str,
                          status: str, gem_id: str) -> dict:
    """以靈魂石為武器附上「命中觸發狀態」:吸血(vampiric)/麻痺(paralyze)/再生(regen)。
    回傳同 enchant_weapon。麻痺數值固定(只看 proc/turns 常數),吸血/再生隨魂石+祕術。"""
    if inventory.count_item(char, base_weapon) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少武器或靈魂石。", "hours": 0, "tired": False, "skill_events": []}
    if status not in ("vampiric", "paralyze", "regen"):
        return {"ok": False, "message": "未知的觸發狀態。", "hours": 0, "tired": False, "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    from tesrpg.systems import mastery
    pot = 1 + mastery.enchant_potency(char, gamedata)
    if status == "paralyze":
        mag, turns = 0, 1                                  # 1 回合(反鎖王);proc 固定常數
    elif status == "regen":
        mag, turns = max(1, round(soul * 1.5 * (0.6 + char.skill("mysticism") / 100.0) * pot)), 3
    else:  # vampiric:每擊回血,turns 不用
        mag, turns = max(1, round(soul * 1.5 * (0.6 + char.skill("mysticism") / 100.0) * pot)), 0

    inventory.remove_item(char, base_weapon, 1)
    inventory.remove_item(char, gem_id, 1)
    item_id = synth.enchant_weapon_status_id(base_weapon, status, mag, turns)
    inventory.add_item(char, item_id, 1)
    xp, hours, tired = progression.practice_cost(char, gamedata, "mysticism")
    events = progression.use_skill(char, gamedata, "mysticism", xp)
    return {"ok": True, "message": f"靈魂石碎裂,{gamedata.item(item_id)['name']} 完成了!",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events}
