"""坐騎(分三類:戰馬/獵馬/法駒)。

共享被動:旅行加速(world.travel)+ 鞍袋負重(inventory.max_weight)。
類別專屬:
  - 戰馬(warhorse):馱載最大 + 開場「衝鋒」戰技(近戰/長槍)。
  - 獵馬(courser):旅行最快 + 規避路途遭遇 + 開場「騎射」戰技(弓:閃避增益)。
  - 法駒(magesteed):騎乘作戰時法術傷害增益(補法系無主動戰技的缺口)。

戰鬥戰技/法術增益僅在「野外旅途/探索遭遇」生效(進地城/朝堂/攻城自動下馬,呼叫端傳
mounted=False)。紅線:衝鋒**不走 sneak_mult**、受 `MOUNTED_CHARGE_DAMAGE_CAP_RATIO` 夾
(見 combat.resolve_attack)。加坐騎/調平衡純改 `data/mounts.json`。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

# 可發動衝鋒的近戰武器流派(弓/法杖排除 —— 法杖走法駒法術增益)。
MELEE_ARCHETYPES = {"sword", "dagger", "mace", "axe", "hand_to_hand", "spear"}


def _active(char: Character, gamedata: GameData) -> dict | None:
    """現乘坐騎定義(未乘/未知 id 回 None)。"""
    mid = getattr(char, "active_mount", "")
    return gamedata.mount(mid) if mid else None


def owns(char: Character, mount_id: str) -> bool:
    return mount_id in getattr(char, "mounts_owned", [])


def category(char: Character, gamedata: GameData) -> str:
    m = _active(char, gamedata)
    return m.get("category", "") if m else ""


# --- 共享被動(無 mounted 語境之分:旅行/負重隨身)-----------------------
def travel_factor_bonus(char: Character, gamedata: GameData) -> float:
    """旅行耗時係數額外 −bonus(world.travel 夾 floor 0.5);未乘=0。"""
    m = _active(char, gamedata)
    return float(m.get("travel_factor_bonus", 0.0)) if m else 0.0


def saddlebag_bonus(char: Character, gamedata: GameData) -> int:
    """鞍袋提高的負重上限;未乘=0。"""
    m = _active(char, gamedata)
    return int(m.get("saddlebag", 0)) if m else 0


def encounter_evade(char: Character, gamedata: GameData) -> float:
    """獵馬規避路途遭遇的機率折減 [0,1);未乘/無=0。"""
    m = _active(char, gamedata)
    return float(m.get("encounter_evade", 0.0)) if m else 0.0


# --- 戰鬥(僅 mounted=True 的野外遭遇生效)-------------------------------
def spell_bonus_dmg(char: Character, gamedata: GameData, mounted: bool) -> float:
    """法駒騎乘作戰的法術傷害加成(+比例);非騎乘戰/未乘/非法駒=0。"""
    if not mounted:
        return 0.0
    m = _active(char, gamedata)
    return float((m.get("spell_bonus") or {}).get("dmg", 0.0)) if m else 0.0


def can_charge(char: Character, gamedata: GameData, mounted: bool) -> bool:
    """戰馬 + 近戰武器(含長槍)+ 騎乘語境 → 可開場衝鋒。"""
    if not mounted:
        return False
    m = _active(char, gamedata)
    if not m or m.get("category") != "warhorse" or "charge" not in m:
        return False
    wpn = gamedata.item_or_none(char.weapon) or {}
    return wpn.get("archetype") in MELEE_ARCHETYPES and not wpn.get("two_handed")   # 雙手重武器太笨重 → 不能馬背衝鋒


def charge_spec(char: Character, gamedata: GameData) -> dict | None:
    """衝鋒參數 {mult_spear, mount_dmg};無=None。"""
    m = _active(char, gamedata)
    return (m or {}).get("charge")


def can_skirmish_ride(char: Character, gamedata: GameData, mounted: bool) -> bool:
    """獵馬 + 弓 + 騎乘語境 → 可開場騎射(給閃避增益)。"""
    if not mounted:
        return False
    m = _active(char, gamedata)
    if not m or m.get("category") != "courser" or "ride_evasion" not in m:
        return False
    wpn = gamedata.item_or_none(char.weapon) or {}
    return wpn.get("archetype") == "bow"


def ride_evasion_spec(char: Character, gamedata: GameData) -> dict | None:
    """騎射閃避增益參數 {amount, turns};無=None。"""
    m = _active(char, gamedata)
    return (m or {}).get("ride_evasion")


# --- 購買 ---------------------------------------------------------------
def buy(char: Character, gamedata: GameData, mount_id: str) -> bool:
    """購買坐騎(於馬廄;呼叫端已查金幣/服務)。加入名冊並設為現乘。"""
    if not gamedata.mount(mount_id) or owns(char, mount_id):
        return False
    char.mounts_owned.append(mount_id)
    char.active_mount = mount_id
    return True
