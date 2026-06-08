"""鍛造·淬鍊強化:在鐵匠處消耗對應材質的錠,把武器/護甲永久強化一級。

與附魔正交、可疊;淬鍊級上限隨 `smithing` 技能(每 20 級 +1,最高 5);每級付 smithing
practice 的體力 + 時間 + 一塊對應材質的錠 → 非無限、非套利(淬鍊不計入售價)。
讀取鉤(僅對玩家):`combat._weapon_profile`(武器傷害 +`weapon_temper_bonus`)、
`combat._armor_rating`(護甲值 +`armor_temper_bonus`)。淬鍊不隨耐久折損(永久鍛強化)。
調平衡只動本檔常數;加可淬材質純改 `_MATERIAL_INGOT`(補對應錠)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import inventory, progression

SKILL = "smithing"
TEMPER_WEAPON_PER = 2     # 每淬鍊級 +2 武器傷害
TEMPER_ARMOR_PER = 1      # 每淬鍊級 +1 護甲值
TEMPER_MAX = 5            # 硬上限(亦受 smithing//20 夾)

# 材質 → 所需錠(可淬鍊材質皆須有對應錠;加新可淬材質純改此表 + items.json 補錠)
_MATERIAL_INGOT = {
    "iron": "iron_ingot", "steel": "steel_ingot", "leather": "wolf_pelt",
    "cloth": "bolt_of_cloth", "archmage": "bolt_of_cloth",
    "elven": "moonstone_ingot", "dwarven": "dwarven_ingot",
    "glass": "malachite_ingot", "ebony": "ebony_ingot",
}


def temper_cap(smithing_skill: int) -> int:
    """淬鍊級上限:每 20 級 +1,最高 TEMPER_MAX。"""
    return min(TEMPER_MAX, max(0, int(smithing_skill) // 20))


def _material_of(gamedata: GameData, item_id: str) -> str | None:
    """物品材質:護甲讀 `material` 欄;武器無 material → 由 id 前綴推(iron_sword→iron)。"""
    d = gamedata.item_or_none(item_id)
    if not d:
        return None
    return d.get("material") or item_id.split("_")[0]


def required_ingot(gamedata: GameData, item_id: str) -> str | None:
    """淬鍊該物品所需的錠 id;不可淬鍊(材質無對應錠)→ None。"""
    return _MATERIAL_INGOT.get(_material_of(gamedata, item_id))


def _is_weapon(gamedata: GameData, item_id: str) -> bool:
    return (gamedata.item_or_none(item_id) or {}).get("kind") == "weapon"


def current_temper(char: Character, gamedata: GameData, item_id: str) -> int:
    store = char.weapon_temper if _is_weapon(gamedata, item_id) else char.armor_temper
    return store.get(item_id, 0)


def is_temperable(gamedata: GameData, item_id: str) -> bool:
    d = gamedata.item_or_none(item_id)
    return bool(d) and d.get("kind") in ("weapon", "armor") and required_ingot(gamedata, item_id) is not None


def can_temper(char: Character, gamedata: GameData, item_id: str) -> tuple[bool, str]:
    if not is_temperable(gamedata, item_id):
        return (False, "此物品無法淬鍊。")
    cap = temper_cap(char.skill(SKILL))
    if current_temper(char, gamedata, item_id) >= cap:
        return (False, f"鍛造技能尚不足以再強化(目前上限 +{cap})。" if cap < TEMPER_MAX
                else "已達淬鍊上限。")
    ingot = required_ingot(gamedata, item_id)
    if inventory.count_item(char, ingot) <= 0:
        return (False, f"缺少 {gamedata.item_name(ingot)}。")
    return (True, "")


def temper(char: Character, gamedata: GameData, item_id: str) -> dict:
    """淬鍊一級。回傳 {ok, message, level?, hours, tired, skill_events}。
    條件不足 → ok False、零成本(不扣料/不耗時)。"""
    ok, reason = can_temper(char, gamedata, item_id)
    if not ok:
        return {"ok": False, "message": reason, "hours": 0, "tired": False, "skill_events": []}
    inventory.remove_item(char, required_ingot(gamedata, item_id), 1)
    store = char.weapon_temper if _is_weapon(gamedata, item_id) else char.armor_temper
    store[item_id] = store.get(item_id, 0) + 1
    xp, hours, tired = progression.practice_cost(char, gamedata, SKILL)
    events = progression.use_skill(char, gamedata, SKILL, xp)
    return {"ok": True, "level": store[item_id], "hours": hours, "tired": tired,
            "skill_events": events,
            "message": f"你在鐵砧前反覆鍛打,將 {gamedata.item_name(item_id)} 淬鍊至 +{store[item_id]}。"}


# --- 讀取鉤(combat,僅玩家)------------------------------------------------
def weapon_temper_bonus(char: Character) -> int:
    """玩家當前手持武器的淬鍊加傷(0 = 未淬鍊;徒手/未知 id 自動為 0)。"""
    return getattr(char, "weapon_temper", {}).get(char.weapon, 0) * TEMPER_WEAPON_PER


def armor_temper_bonus(char: Character) -> int:
    """玩家穿戴中各護甲件的淬鍊加護甲值總和。"""
    worn = set(char.equipped.values())
    return sum(lvl for iid, lvl in getattr(char, "armor_temper", {}).items()
               if iid in worn) * TEMPER_ARMOR_PER
