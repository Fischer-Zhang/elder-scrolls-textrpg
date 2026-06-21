"""附魔:用充能靈魂石把元素傷害附到武器上。

靈魂石由「擒魂術」在擊殺時取得(見 magic.soul_gem_for)。
附魔威力隨靈魂等級與神秘 (mysticism) 技能提升,並鍛鍊神秘。
產出的是「附魔武器」(見 synth)。
"""

from __future__ import annotations

from tesrpg import formulas, synth
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import inventory, progression

ELEMENTS = ["fire", "frost", "shock"]
FORTIFY_STATS = ["health", "magicka", "fatigue"]   # 護甲附魔可強化的最大資源
RESIST_ELEMENTS = ["fire", "frost", "shock", "poison", "magic"]   # 飾品可抗的元素

# R66:resist 附魔再平衡 —— ① 魂石階非線性(soul^0.7,大魂≈微魂×3.1 而非 ×5)→ 軟化高階堆疊、
# 救活低階魂石經濟;② 魔抗(universal·減火/霜/電)基數低、單元素 = 魔抗×2(魔抗每點覆蓋三系故每件給少)。
# 錨點 = soul-1·mysticism100 的魔抗值(armor 2 / jewelry 3);單元素 = 該魔抗×2。
RESIST_SOUL_EXP = 0.7
RESIST_MAGIC_ANCHOR = {"armor": 2, "jewelry": 3}   # 魔抗 % @ soul1·myst100;單元素 ×2

# 飾品附魔的 4 種型別(供 UI 列表):(kind, 顯示名)
JEWELRY_KINDS = [("skill", "強化技能"), ("attr", "強化屬性"),
                 ("resist", "抗元素"), ("res", "強化最大資源")]
# 護甲附魔型別(刻意不含 attr:屬性 fortify 最強、會疊乘衍生資源,留給飾品 3 槽)
ARMOR_KINDS = [("res", "強化最大資源"), ("skill", "強化技能"), ("resist", "抗元素"), ("thorns", "荊棘反傷")]
# 武器命中觸發附魔型別(供 UI 分家族;見 main.action_enchant)
WEAPON_DOT_KINDS = [("burn", "焚燒(火 · 持續傷)"), ("chill", "凍緩(霜 · 持續傷+減敵)"),
                    ("jolt", "感電(電 · 持續傷+燒魔)")]
WEAPON_ABSORB_KINDS = [("absorb_health", "吸取生命"), ("absorb_magicka", "吸取魔力"),
                       ("absorb_fatigue", "吸取體力")]
WEAPON_TRIGGER_KINDS = [("vampiric", "吸血"), ("regen", "再生"),
                        ("paralyze", "麻痺(充能)"), ("soul_trap", "命中擒魂(充能)")]
WEAPON_STATUS_KINDS = [("vampiric", "吸血"), ("paralyze", "麻痺"), ("regen", "再生")]   # 保留:舊參照

_DOT_STATUSES = ("burn", "chill", "jolt")
_ABSORB_STATUSES = ("absorb_health", "absorb_magicka", "absorb_fatigue")
_CHARGE_STATUSES = ("soul_trap", "paralyze")            # 容量型:魂石→充能電池(mag=容量)
_WEAPON_STATUSES = ("vampiric", "regen") + _CHARGE_STATUSES + _DOT_STATUSES + _ABSORB_STATUSES


def filled_soul_gems(char: Character, gamedata: GameData) -> list[str]:
    return [s["id"] for s in char.inventory if gamedata.item(s["id"]).get("kind") == "soul_gem"]


def chargeable_weapons(char: Character, gamedata: GameData) -> list[str]:
    """背包中「充能型」附魔武器(命中擒魂 / 麻痺,容量 > 0)的去重 id 清單(供靈魂石回充)。"""
    out, seen = [], set()
    for s in char.inventory:
        iid = s["id"]
        if iid in seen:
            continue
        seen.add(iid)
        ench = (gamedata.item_or_none(iid) or {}).get("enchant")
        if (ench and ench.get("kind") == "weapon_status"
                and ench.get("status") in _CHARGE_STATUSES and int(ench.get("magnitude", 0)) > 0):
            out.append(iid)
    return out


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


def _resist_magnitude(slot: str, param: str | None, soul: int, mysticism_skill: int) -> int:
    """R66 resist 附魔量值:魂石 soul^0.7 非線性 + 魔抗/單元素分流。
    魔抗 = round(錨點 × soul^0.7 × (0.5+myst/100)/1.5);單元素(param≠"magic")= 魔抗×2。
    (除以 1.5 使 soul1·myst100 = 錨點;myst75≈×0.83、myst50≈×0.67。)"""
    base = (0.5 + mysticism_skill / 100.0) / 1.5
    magic = max(1, round(RESIST_MAGIC_ANCHOR[slot] * soul ** RESIST_SOUL_EXP * base))
    return magic if param == "magic" else magic * 2


def jewelry_magnitude(kind: str, soul: int, mysticism_skill: int, param: str | None = None) -> int:
    """各型別的附魔強度(屬性最珍貴給最少;抗性走 R66 非線性/分流 _resist_magnitude)。"""
    if kind == "resist":
        return _resist_magnitude("jewelry", param, soul, mysticism_skill)
    base = 0.5 + mysticism_skill / 100.0
    factor = {"skill": 2.0, "attr": 1.2, "res": 3.0}[kind]
    return max(1, round(soul * factor * base))


def enchant_jewelry(char: Character, gamedata: GameData, base_jewelry: str,
                    kind: str, param: str, gem_id: str) -> dict:
    """為飾品附上 強化技能/屬性/抗元素/強化資源。回傳同 enchant_weapon。"""
    if inventory.count_item(char, base_jewelry) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少飾品或靈魂石。", "hours": 0, "tired": False, "skill_events": []}
    if kind not in ("skill", "attr", "resist", "res"):
        return {"ok": False, "message": "未知的附魔型別。", "hours": 0, "tired": False, "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    from tesrpg.systems import mastery
    mag = round(jewelry_magnitude(kind, soul, char.skill("mysticism"), param) * (1 + mastery.enchant_potency(char, gamedata)))

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


def armor_magnitude(kind: str, soul: int, mysticism_skill: int, param: str | None = None) -> int:
    """護甲附魔強度:res 沿用 enchant_magnitude(零位移);skill 略低於飾品(1.5 vs 2.0);
    resist 走 R66 非線性/魔抗分流 _resist_magnitude(armor 錨點低於 jewelry)。"""
    if kind == "res":
        return enchant_magnitude(soul, mysticism_skill)
    if kind == "thorns":   # 荊棘反傷(R42):反傷% = 靈魂石階(1~5),不吃 mysticism/enchant_potency(使用者拍板「1階=1%」)
        return max(1, soul)
    if kind == "resist":
        return _resist_magnitude("armor", param, soul, mysticism_skill)
    base = 0.5 + mysticism_skill / 100.0
    return max(1, round(soul * {"skill": 1.5}[kind] * base))


def enchant_armor(char: Character, gamedata: GameData, base_armor: str,
                  kind: str, param: str, gem_id: str) -> dict:
    """以靈魂石為護甲附上 強化資源/技能/抗元素(res/skill/resist)。回傳同 enchant_weapon。"""
    if inventory.count_item(char, base_armor) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少護甲或靈魂石。", "hours": 0, "tired": False, "skill_events": []}
    if kind not in ("res", "skill", "resist", "thorns"):
        return {"ok": False, "message": "未知的附魔型別。", "hours": 0, "tired": False, "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    from tesrpg.systems import mastery
    if kind == "thorns":   # 荊棘:純靈魂石階%、不吃 enchant_potency
        mag = armor_magnitude(kind, soul, char.skill("mysticism"))
    else:
        mag = round(armor_magnitude(kind, soul, char.skill("mysticism"), param) * (1 + mastery.enchant_potency(char, gamedata)))

    inventory.remove_item(char, base_armor, 1)
    inventory.remove_item(char, gem_id, 1)
    item_id = synth.enchant_armor_id(base_armor, kind, param, mag)
    inventory.add_item(char, item_id, 1)
    xp, hours, tired = progression.practice_cost(char, gamedata, "mysticism")
    events = progression.use_skill(char, gamedata, "mysticism", xp)
    return {"ok": True, "message": f"靈魂石碎裂,{gamedata.item(item_id)['name']} 完成了!",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events}


def weapon_status_magnitude(status: str, soul: int, mysticism_skill: int, pot: float = 1.0) -> tuple[int, int]:
    """各命中觸發附魔的 (magnitude, turns)。
    容量型(soul_trap/paralyze)magnitude = 充能電池容量(魂石→電池);DoT/吸取/吸血/再生 = 效果強度。"""
    base = soul * (0.6 + mysticism_skill / 100.0) * pot
    if status == "paralyze":
        return max(1, round(base * formulas.CHARGE_PER_SOUL)), 1          # 容量;1 回合麻痺、solo 免疫紅線不動
    if status == "soul_trap":
        return max(1, round(base * formulas.CHARGE_PER_SOUL)), formulas.WEAPON_SOULTRAP_TURNS  # 容量
    if status in _DOT_STATUSES:
        return max(1, round(base * formulas.WEAPON_DOT_FACTOR)), formulas.WEAPON_DOT_TURNS
    if status in _ABSORB_STATUSES:
        return max(1, round(base * formulas.WEAPON_ABSORB_FACTOR)), 0
    if status == "regen":
        return max(1, round(base * 1.5)), 3
    return max(1, round(base * 1.5)), 0                                   # vampiric:每擊回血


def enchant_weapon_status(char: Character, gamedata: GameData, base_weapon: str,
                          status: str, gem_id: str) -> dict:
    """以靈魂石為武器附上「命中觸發」效果:元素 DoT(burn/chill/jolt)/吸取(absorb_*)/
    吸血(vampiric)/再生(regen)/麻痺(paralyze)/命中擒魂(soul_trap)。回傳同 enchant_weapon。
    充能型(soul_trap/paralyze)以魂石定電池容量(mag),並初始化 char.enchant_charges。"""
    if inventory.count_item(char, base_weapon) < 1 or inventory.count_item(char, gem_id) < 1:
        return {"ok": False, "message": "缺少武器或靈魂石。", "hours": 0, "tired": False, "skill_events": []}
    if status not in _WEAPON_STATUSES:
        return {"ok": False, "message": "未知的觸發效果。", "hours": 0, "tired": False, "skill_events": []}

    soul = gamedata.item(gem_id).get("soul", 1)
    from tesrpg.systems import mastery
    pot = 1 + mastery.enchant_potency(char, gamedata)
    mag, turns = weapon_status_magnitude(status, soul, char.skill("mysticism"), pot)

    inventory.remove_item(char, base_weapon, 1)
    inventory.remove_item(char, gem_id, 1)
    item_id = synth.enchant_weapon_status_id(base_weapon, status, mag, turns)
    inventory.add_item(char, item_id, 1)
    if status in _CHARGE_STATUSES:                         # 充能型:電池初始化為容量
        char.enchant_charges[item_id] = mag
    xp, hours, tired = progression.practice_cost(char, gamedata, "mysticism")
    events = progression.use_skill(char, gamedata, "mysticism", xp)
    return {"ok": True, "message": f"靈魂石碎裂,{gamedata.item(item_id)['name']} 完成了!",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events}
