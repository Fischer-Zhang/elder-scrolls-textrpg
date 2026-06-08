"""技能里程碑(Skill Mastery)。

技能練到關鍵門檻(50/75/100)自動解鎖一個里程碑能力 —— 給 learn-by-doing 的
終點一個「身份印記」。守住本作哲學:

- **零選擇自動解鎖**:門檻純由 ``char.base_skill()`` 即時推導 → 零新存檔種子、
  舊存檔載入後達門檻即自動獲得(練到就有);不發 perk point、不二選一(零 min-max 套利)。
- **效果走既有層**:質變/floor/active_effects 為主;真權衡型(boon+同源代價)夾 cap。
- **不碰** 成長漏斗 / 怪物資料 / sneak_mult 夜母鏈 / 資源上限鏈。

新增一條里程碑 = 純改 ``data/mastery.json``(在下列已實作 kind 內);
新增一種 **kind** = 加一個 getter + 一處呼叫端分支(誠實標注:這不是純 JSON)。

kind 白名單(MVP):
- ``block_deflect``    盾陣:格擋時命中懲罰加深(penalty)
- ``bulwark``          壁壘:受物理攻擊額外減傷(factor)+ 攻擊更耗體(attack_fatigue_factor)
- ``overheal_ward``    聖光·溢盾:治療溢出血上限的部分轉臨時護盾(convert/cap_ratio/turns)
- ``spell_overload``   過載:某學派 _power 加成 + 魔耗倍率(school/power_bonus/cost_factor)
- ``lock_floor``       撬鎖名家:撬鎖成功率下限(floor)
- ``guaranteed_persuade`` 辯舌·折服:說服必成(每 NPC 一次,需 char.persuaded_npcs)
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData


# 已實作分派的 kind 白名單(單一真實來源)。不在此集合的 kind 視為「未實作」→
# 完全不顯示/不計分/不播報/無效果(避免 JSON 打錯 kind 時「計分+播報卻零效果」的沉默 foot-gun)。
# 新增一種 kind 時:在此登錄 + 加對應 getter + 一處呼叫端分支(這步不是純改 JSON)。
_IMPLEMENTED_KINDS = {
    "block_deflect", "bulwark", "overheal_ward",
    "spell_overload", "lock_floor", "guaranteed_persuade",
}


def _defs(gamedata: GameData) -> list:
    """已載入且 kind 已實作的里程碑定義(過濾打錯/未實作的 kind)。"""
    return [e for e in (getattr(gamedata, "mastery", []) or [])
            if e.get("kind") in _IMPLEMENTED_KINDS]


def _has(char, threshold_skill: str, threshold: int) -> bool:
    """玩家的 base 技能(不含裝備/吸血鬼疊加)是否達門檻。僅對有 base_skill 的玩家成立。"""
    if not hasattr(char, "base_skill"):   # 怪物/同伴無技能里程碑
        return False
    return char.base_skill(threshold_skill) >= threshold


def _active_by_kind(char, gamedata: GameData, kind: str) -> dict | None:
    """回傳該 kind 中已達門檻的里程碑定義(MVP 每 kind 至多一條);無則 None。"""
    for e in _defs(gamedata):
        if e.get("kind") == kind and _has(char, e["skill"], e["threshold"]):
            return e
    return None


# --- UI / 查詢 -----------------------------------------------------------
def unlocked(char, gamedata: GameData) -> list:
    """玩家目前已解鎖的所有里程碑定義(供結算/角色面板呈現)。"""
    return [e for e in _defs(gamedata) if _has(char, e["skill"], e["threshold"])]


def newly_unlocked(char, gamedata: GameData, skill_id: str, new_level: int) -> list:
    """技能剛升到 new_level 這一級時、恰好跨過門檻的里程碑(供解鎖播報,精確避免重報)。"""
    return [e for e in _defs(gamedata)
            if e.get("skill") == skill_id and e.get("threshold") == new_level]


def next_threshold(char, gamedata: GameData, skill_id: str) -> dict | None:
    """該技能(以 base_skill 計)尚未跨越的下一個里程碑門檻;全已解或無里程碑 → None。

    回傳 {name, threshold, remaining}(remaining = 還差幾級,>=1)。供 UI 提示用,**零副作用**。
    用 _defs(過 _IMPLEMENTED_KINDS 白名單,不宣傳未實作條目);門檻只認 base_skill(鐵律)。
    """
    base = char.base_skill(skill_id) if hasattr(char, "base_skill") else 0
    cands = sorted((e for e in _defs(gamedata)
                    if e.get("skill") == skill_id and e["threshold"] > base),
                   key=lambda e: e["threshold"])
    if not cands:
        return None
    e = cands[0]
    return {"name": e["name"], "threshold": e["threshold"], "remaining": e["threshold"] - base}


# --- 各 kind 的使用點 getter(呼叫端各取一處)---------------------------
def block_hit_penalty(char, gamedata: GameData) -> float:
    """格擋時施加給攻擊者的命中懲罰(預設 BLOCK_HIT_PENALTY;盾陣加深)。"""
    e = _active_by_kind(char, gamedata, "block_deflect")
    return e["penalty"] if e else formulas.BLOCK_HIT_PENALTY


def incoming_physical_factor(char, gamedata: GameData) -> float:
    """壁壘:受物理攻擊的減傷倍率(<1.0 = 更耐打);非物理(元素)不適用。"""
    e = _active_by_kind(char, gamedata, "bulwark")
    return e["factor"] if e else 1.0


def attack_fatigue_factor(char, gamedata: GameData) -> float:
    """壁壘的同源代價:攻擊一擊的體力消耗倍率(>1.0 = 更耗)。"""
    e = _active_by_kind(char, gamedata, "bulwark")
    return e["attack_fatigue_factor"] if e else 1.0


def spell_power_bonus(char, gamedata: GameData, school: str) -> float:
    """過載:對應學派的 _power 額外加成。"""
    e = _active_by_kind(char, gamedata, "spell_overload")
    return e["power_bonus"] if e and e.get("school") == school else 0.0


def spell_cost_factor(char, gamedata: GameData, school: str) -> float:
    """過載的同源代價:對應學派的魔力消耗倍率(>1.0 = 更耗魔)。"""
    e = _active_by_kind(char, gamedata, "spell_overload")
    return e["cost_factor"] if e and e.get("school") == school else 1.0


def lock_floor(char, gamedata: GameData) -> float:
    """撬鎖名家:撬鎖成功率下限(0.0 = 無里程碑)。"""
    e = _active_by_kind(char, gamedata, "lock_floor")
    return e["floor"] if e else 0.0


def overheal_ward(char, gamedata: GameData) -> dict | None:
    """聖光·溢盾:回傳 {convert, cap_ratio, turns} 或 None。"""
    return _active_by_kind(char, gamedata, "overheal_ward")


def can_guaranteed_persuade(char, gamedata: GameData, npc_id: str) -> bool:
    """辯舌·折服:此 NPC 是否可被一次性必定說服(每 NPC 限一次)。"""
    if _active_by_kind(char, gamedata, "guaranteed_persuade") is None:
        return False
    return npc_id not in getattr(char, "persuaded_npcs", [])
