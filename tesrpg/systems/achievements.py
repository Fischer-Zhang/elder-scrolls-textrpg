"""成就(Achievements):純由角色最終狀態推導的「榮譽印記」。

哲學對齊 systems/mastery.py:
- **唯讀、零新存檔欄、零遊戲迴圈鉤子。** earned(char, gamedata) 由角色最終狀態即時推導
  (如 mastery.unlocked),在傳奇結算畫面與角色卡子檢視通用、結果一致。
- **僅供表彰,不計入傳奇分數**(底層計數本身已計分,避免雙重計分擾動平衡)。
- 資料驅動:新增成就 = 改 data/achievements.json(在已實作 cond.type 內);
  新增一種 cond.type = 加一個分支 + 在 _IMPLEMENTED_TYPES 登錄(這步不是純改 JSON)。
- 未知/未實作的 cond.type → 完全 inert(過濾,絕不顯示/計數)。

評估器鐵律:**零 char 變動**(純讀);缺漏/空欄位安全(初生角色少數或零達成,不崩潰)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.systems import factions, lycanthropy, mastery, politics, vampirism, warband
# 注意:legacy 在 pure_spec 分支內就地 import(legacy 會頂層 import 本模組 → 避免循環)。

# 已實作分派的 cond.type 白名單(單一真實來源)。不在此集合者視為「未實作」→
# 過濾、不顯示、不計數(避免 JSON 打錯 type 時「列出卻永不可達」的沉默 foot-gun)。
_IMPLEMENTED_TYPES = {
    "kill_boss", "kills_total", "dungeons", "quests", "level", "gold",
    "fame", "infamy", "guildmaster_any", "guildmaster", "mastery_count",
    "skill_cap", "landmarks", "provinces", "cities_held", "thanes",
    "vampire", "lycanthropy", "werewolf_feeds", "skooma_addiction", "murders",
    "pure_spec", "allegiance",
}

# pure_spec 判定:主專精「絕對總和」與「領先次高的差距」雙門檻。初生角色因起始職業
# 技能偏向,差距即達 ~150,故須加絕對門檻避免創角即得(=真·純流派 endgame 成就)。
_PURE_SPEC_MIN = 400
_PURE_SPEC_MARGIN = 150


def _defs(gamedata: GameData) -> list:
    """已載入且 cond.type 已實作的成就定義(過濾打錯/未實作的 type)。"""
    return [a for a in (getattr(gamedata, "achievements", []) or [])
            if a.get("cond", {}).get("type") in _IMPLEMENTED_TYPES]


# --- 各 cond.type 的判定(純讀,零 char 變動)---------------------------
def _eval(char, gamedata: GameData, cond: dict) -> bool:
    t = cond["type"]

    if t == "kill_boss":
        return getattr(char, "kill_counts", {}).get(cond["creature"], 0) >= 1
    if t == "kills_total":
        return sum(getattr(char, "kill_counts", {}).values()) >= cond["count"]
    if t == "dungeons":
        return len(getattr(char, "cleared_dungeons", [])) >= cond["count"]
    if t == "quests":
        return len(getattr(char, "completed_quests", [])) >= cond["count"]
    if t == "level":
        return getattr(char, "level", 1) >= cond["level"]
    if t == "gold":
        return getattr(char, "gold", 0) >= cond["amount"]
    if t == "fame":
        return getattr(char, "fame", 0) >= cond["amount"]
    if t == "infamy":
        return getattr(char, "infamy", 0) >= cond["amount"]

    if t == "guildmaster_any":
        return warband.is_guildmaster(char, gamedata)
    if t == "guildmaster":
        fdef = gamedata.factions.get(cond["faction"])
        if not fdef:
            return False
        return factions.rank_index(char, cond["faction"]) >= len(fdef["ranks"]) - 1

    if t == "mastery_count":
        return len(mastery.unlocked(char, gamedata)) >= cond["count"]
    if t == "skill_cap":
        # 達 100 的技能數;讀 char.skills(=base,不含裝備/吸血鬼疊加,對齊里程碑鐵律)
        return sum(1 for v in getattr(char, "skills", {}).values() if v >= 100) >= cond["count"]

    if t == "landmarks":
        found = sum(1 for lid in getattr(char, "discovered_landmarks", [])
                    if lid in gamedata.landmarks)
        return found >= cond["count"]
    if t == "provinces":
        locs = gamedata.world["locations"]
        provs = {locs[lid]["province"] for lid in getattr(char, "visited_locations", [])
                 if lid in locs}
        return len(provs) >= cond["count"]

    if t == "cities_held":
        return len(politics.held_tax_cities(char, gamedata)) >= cond["count"]
    if t == "thanes":
        return len(getattr(char, "thaneships", [])) >= cond["count"]
    if t == "allegiance":
        return getattr(char, "allegiance", "") == cond["cause"]

    if t == "vampire":
        return vampirism.is_vampire(char)
    if t == "lycanthropy":
        return lycanthropy.is_werewolf(char)
    if t == "werewolf_feeds":
        return getattr(char, "werewolf_total_feeds", 0) >= cond["count"]
    if t == "skooma_addiction":
        return getattr(char, "skooma_addiction", 0) >= cond["count"]
    if t == "murders":
        return getattr(char, "murders", 0) >= cond["count"]

    if t == "pure_spec":
        if not hasattr(char, "skills"):
            return False
        from tesrpg.systems import legacy   # 就地 import 避免與 legacy 的循環
        totals = legacy._spec_totals(char, gamedata)
        dom = totals.get(cond["spec"], 0)
        others = max((v for k, v in totals.items() if k != cond["spec"]), default=0)
        return dom >= _PURE_SPEC_MIN and (dom - others) >= _PURE_SPEC_MARGIN

    return False   # 不可達(已過 _IMPLEMENTED_TYPES);防禦性回 False


# --- UI / 查詢 -----------------------------------------------------------
def earned(char, gamedata: GameData) -> list:
    """角色目前已達成的所有成就定義(供結算/角色卡呈現)。純讀、零副作用。"""
    return [a for a in _defs(gamedata) if _eval(char, gamedata, a["cond"])]


def earned_and_locked(char, gamedata: GameData) -> tuple[list, list]:
    """(已達成, 未達成) 兩份定義清單,供角色卡子檢視一次取齊。"""
    defs = _defs(gamedata)
    won = [a for a in defs if _eval(char, gamedata, a["cond"])]
    won_ids = {a["id"] for a in won}
    locked = [a for a in defs if a["id"] not in won_ids]
    return won, locked
