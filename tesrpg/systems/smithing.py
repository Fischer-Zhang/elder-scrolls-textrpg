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
    # 頂級稀有材質:淬鍊用既有/可掉錠(魔族用黑檀錠、龍鱗用龍鱗、龍祭司布用布匹);
    # 鍛造/裁縫另需稀有素材(魔性之心/龍鱗),見 recipes.json。
    "daedric": "ebony_ingot", "dragonscale": "dragon_scale", "dragonpriest": "bolt_of_cloth",
}


def temper_cap(smithing_skill: int) -> int:
    """淬鍊級上限:每 20 級 +1,最高 TEMPER_MAX。"""
    return min(TEMPER_MAX, max(0, int(smithing_skill) // 20))


def effective_temper_cap(char: Character, gamedata: GameData) -> int:
    """含里程碑「淬火宗師」的淬鍊上限(+cap_bonus,同步抬高 TEMPER_MAX 硬夾,否則滿級時 +1 inert)。"""
    from tesrpg.systems import mastery
    bonus = mastery.temper_cap_bonus(char, gamedata)
    return min(TEMPER_MAX + bonus, max(0, int(char.skill(SKILL)) // 20) + bonus)


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
    cap = effective_temper_cap(char, gamedata)
    if current_temper(char, gamedata, item_id) >= cap:
        return (False, f"鍛造技能尚不足以再強化(目前上限 +{cap})。" if cap < TEMPER_MAX
                else "已達淬鍊上限。")
    ingot = required_ingot(gamedata, item_id)
    if inventory.count_item(char, ingot) <= 0:
        return (False, f"缺少 {gamedata.item_name(ingot)}。")
    return (True, "")


def temper(char: Character, gamedata: GameData, item_id: str, rng=None) -> dict:
    """淬鍊一級。回傳 {ok, message, level?, hours, tired, skill_events, free?}。
    條件不足 → ok False、零成本(不扣料/不耗時)。rng 提供時,里程碑「物盡其用」有機率不耗錠。"""
    ok, reason = can_temper(char, gamedata, item_id)
    if not ok:
        return {"ok": False, "message": reason, "hours": 0, "tired": False, "skill_events": []}
    from tesrpg.systems import mastery
    free = rng is not None and rng.chance(mastery.temper_free_chance(char, gamedata))
    if not free:                                       # 「物盡其用」:有機率不消耗錠
        inventory.remove_item(char, required_ingot(gamedata, item_id), 1)
    store = char.weapon_temper if _is_weapon(gamedata, item_id) else char.armor_temper
    store[item_id] = store.get(item_id, 0) + 1
    xp, hours, tired = progression.practice_cost(char, gamedata, SKILL)
    events = progression.use_skill(char, gamedata, SKILL, xp)
    msg = f"你在鐵砧前反覆鍛打,將 {gamedata.item_name(item_id)} 淬鍊至 +{store[item_id]}。"
    if free:
        msg += "(物盡其用:這次未耗錠)"
    return {"ok": True, "level": store[item_id], "hours": hours, "tired": tired,
            "skill_events": events, "free": free, "message": msg}


# --- 回爐熔解(成品 → 部分材料,有損耗;同時練鍛造)------------------------
RECYCLE_RATIO = 0.5          # 回爐回收比例(其餘為熔解損耗);調平衡只動此常數
# 回爐不回收的稀有 loot-only 素材(維持稀缺:龍鱗只能打龍取得;魔性之心本就不由 required_ingot 產出)
_NON_RECYCLE_INGOTS = {"dragon_scale"}


def meltdown_yield(gamedata: GameData, item_id: str) -> tuple[str, int]:
    """回爐產出 (ingot_id, qty)。確保「有損耗」且熔不出比成品更值錢的材料(杜絕買廉品回爐套錠):
    有鍛造配方 → 反查該錠用量 ×損耗(無條件捨去;單錠成品 → 0);
    無配方 → 成品價值 ≥ 一塊錠才回收 1,否則 0(本就廉於一錠者,熔之無所得)。"""
    ingot = required_ingot(gamedata, item_id)
    if ingot is None:
        return (ingot, 0)
    base = 0
    for r in gamedata.recipes.values():                      # 反查產出此物且用到該錠的配方(防多配方同 output)
        if r.get("output") == item_id and ingot in r.get("inputs", {}):
            base = r["inputs"][ingot]
            break
    if base:
        qty = int(base * RECYCLE_RATIO)
    else:
        item_val = gamedata.item(item_id).get("value", 0)
        ingot_val = gamedata.item(ingot).get("value", 1) or 1
        qty = 1 if item_val >= ingot_val else 0
    return ingot, qty


# 回爐排除的武器流派:弓/弩/法杖非「純金屬可重鑄」之物(與淬鍊一致觀感、對齊 UI 文案)
_NON_MELT_ARCHETYPES = {"bow", "crossbow", "staff"}


def meltable(gamedata: GameData, item_id: str) -> bool:
    """可回爐:武器/護甲、材質有對應錠(非稀材)、value>0、且回爐確有所得(qty>0)。
    排除:附魔成品/具名神器(d['enchant'],不可逆毀——如魔族剃刀、附魔法杖/法袍)、弓·弩·法杖
    (_NON_MELT_ARCHETYPES)、飾品(非 weapon/armor)、龍鱗裝(稀材)、廉於一錠的單品(熔之無得)。"""
    d = gamedata.item_or_none(item_id)
    if not d or d.get("kind") not in ("weapon", "armor") or d.get("value", 0) <= 0:
        return False
    if d.get("enchant") or d.get("archetype") in _NON_MELT_ARCHETYPES:
        return False
    ingot, qty = meltdown_yield(gamedata, item_id)
    return ingot is not None and ingot not in _NON_RECYCLE_INGOTS and qty > 0


def worn_count(char: Character, item_id: str) -> int:
    """該 item_id 當前佔用的穿戴/手持份數(手持 + 副手 + 各護甲/飾品槽)。
    回爐須保留這些份,只熔多餘的(held − worn)→ 同型多件時不必先卸下。"""
    n = 1 if char.weapon == item_id else 0
    if getattr(char, "offhand", "") == item_id:
        n += 1
    n += sum(1 for v in char.equipped.values() if v == item_id)
    return n


def meltdown(char: Character, gamedata: GameData, item_id: str) -> dict:
    """回爐一件成品 → 部分材料(有損耗),並付 smithing practice 成本(同時練鍛造)。
    回傳 {ok, message, ingot?, qty?, hours, tired, skill_events}。
    只熔「多餘」份(held − worn);穿戴/手持中的份受保護(防裝備脫鉤),無多餘者須先卸下。"""
    if not meltable(gamedata, item_id):
        return {"ok": False, "message": "此物品無法回爐。", "hours": 0, "tired": False, "skill_events": []}
    if inventory.count_item(char, item_id) <= 0:
        return {"ok": False, "message": "你沒有這件物品。", "hours": 0, "tired": False, "skill_events": []}
    if inventory.count_item(char, item_id) - worn_count(char, item_id) <= 0:
        return {"ok": False, "message": "這是你穿戴/手持中的唯一一件,請先卸下、或多備一件再回爐。",
                "hours": 0, "tired": False, "skill_events": []}
    ingot, qty = meltdown_yield(gamedata, item_id)
    inventory.remove_item(char, item_id, 1)
    inventory.add_item(char, ingot, qty)
    xp, hours, tired = progression.practice_cost(char, gamedata, SKILL)
    events = progression.use_skill(char, gamedata, SKILL, xp)
    return {"ok": True, "ingot": ingot, "qty": qty, "hours": hours, "tired": tired,
            "skill_events": events,
            "message": f"你將 {gamedata.item_name(item_id)} 回爐熔解,煉回 {gamedata.item_name(ingot)} ×{qty}。"}


# --- 讀取鉤(combat,僅玩家)------------------------------------------------
def weapon_temper_bonus(char: Character, gamedata: GameData) -> int:
    """玩家當前手持武器的淬鍊加傷(0 = 未淬鍊;徒手/未知 id 自動為 0)。
    含鋒銳里程碑 temper_power 倍率 ×(1+power)(smithing 50/100;未選 → 0)。"""
    from tesrpg.systems import mastery
    flat = getattr(char, "weapon_temper", {}).get(char.weapon, 0) * TEMPER_WEAPON_PER
    return int(flat * (1 + mastery.temper_power(char, gamedata)))


def armor_temper_bonus(char: Character, gamedata: GameData) -> int:
    """玩家穿戴中各護甲件的淬鍊加護甲值總和(含鋒銳里程碑 temper_power 倍率)。"""
    from tesrpg.systems import mastery
    worn = set(char.equipped.values())
    flat = sum(lvl for iid, lvl in getattr(char, "armor_temper", {}).items()
               if iid in worn) * TEMPER_ARMOR_PER
    return int(flat * (1 + mastery.temper_power(char, gamedata)))
