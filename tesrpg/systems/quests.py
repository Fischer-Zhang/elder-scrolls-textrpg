"""任務引擎:接取、(多階段)目標追蹤、自動結算獎勵、公會晉升。

目標型別:kill(擊殺 N 隻)、clear_dungeon(肅清地城)、reach(抵達地點)、
collect(持有 N 件物品,結算時消耗)。

任務可為單一目標(`objective`)或多階段任務線(`stages`,每階段一個 objective + 文字)。
單目標任務在內部視為一階段;達標即自動推進/完成並發獎。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import factions, inventory, party

STIPEND_PER_RANK = 40   # 晉升俸祿:每升一階,公會額外發 40×新階級 金


# --- 進度記錄(由戰鬥/探索/旅行 hook 呼叫)-----------------------------
def record_kill(char: Character, creature_tid: str) -> None:
    char.kill_counts[creature_tid] = char.kill_counts.get(creature_tid, 0) + 1


def record_dungeon_clear(char: Character, dungeon_id: str) -> None:
    if dungeon_id not in char.cleared_dungeons:
        char.cleared_dungeons.append(dungeon_id)


# --- 分支(敘事抉擇)----------------------------------------------------
def branches(quest: dict) -> list[dict]:
    """任務的可選路線;無分支則空列表。"""
    return quest.get("branches", [])


def resolved(char: Character, gamedata: GameData, quest_id: str) -> dict:
    """公開存取「套用玩家分支後實際生效」的任務 dict(供 UI/動作讀自訂欄位,如合約的
    escort/clean_bonus)。"""
    return _resolved(char, gamedata, quest_id)


def _resolved(char: Character, gamedata: GameData, quest_id: str) -> dict:
    """套用玩家選定的分支,回傳「實際生效」的任務 dict。

    分支任務的頂層**不放** objective/stages(由分支提供),分支可覆寫
    text/objective/stages/reward;未接取時預設第 0 條分支(供列表預覽)。
    """
    q = gamedata.quests[quest_id]
    brs = branches(q)
    if not brs:
        return q
    idx = max(0, min(char.quests.get(quest_id, {}).get("branch", 0), len(brs) - 1))
    return {**q, **brs[idx]}


# --- 階段存取 -----------------------------------------------------------
def _stages(quest: dict) -> list[dict]:
    """把任務正規化成階段列表;單目標任務 = 一個階段。"""
    if "stages" in quest:
        return quest["stages"]
    return [{"objective": quest["objective"], "text": quest.get("text", "")}]


def _stage_index(char: Character, quest_id: str, total: int) -> int:
    # 夾限至 [0, total-1];max(0,...) 防毀損存檔的負值經 Python 負索引取到錯誤階段
    return max(0, min(char.quests.get(quest_id, {}).get("stage", 0), total - 1))


def current_objective(char: Character, gamedata: GameData, quest_id: str) -> tuple[dict, int, int]:
    """回傳 (當前階段 objective, 階段索引, 階段總數)。"""
    stages = _stages(_resolved(char, gamedata, quest_id))
    idx = _stage_index(char, quest_id, len(stages))
    return stages[idx]["objective"], idx, len(stages)


# --- 接取 ---------------------------------------------------------------
def is_active(char: Character, quest_id: str) -> bool:
    return quest_id in char.quests


def is_done(char: Character, quest_id: str) -> bool:
    return quest_id in char.completed_quests


def available_quests(char: Character, gamedata: GameData, source: str,
                     faction: str | None = None, province: str | None = None) -> list[str]:
    out = []
    for qid, q in gamedata.quests.items():
        if q.get("source") != source or is_active(char, qid) or is_done(char, qid):
            continue
        # 世界事件 gate(向後相容:無此欄=不限):任務在指定大事件觸發後才開放(如主線需 kvatch_falls)。
        if q.get("requires_event") and q["requires_event"] not in char.world_events_fired:
            continue
        # 等級/聲望 gate(向後相容:無此欄=不限;同 requires_event 模式)。讓戴德拉神殿任務後期化(R45)。
        if q.get("requires_level") and char.level < q["requires_level"]:
            continue
        if q.get("requires_fame") and char.fame < q["requires_fame"]:
            continue
        # 陣營身分 gate:需為某陣營會員(達指定階)才開放(如教徒頂點 md7 需 mythic_dawn 滿階)。
        rf = q.get("requires_faction")
        if rf and char.factions.get(rf, -1) < q.get("requires_faction_rank", 0):
            continue
        # 前置任務 gate:需先完成某任務才開放(任務鏈)。
        rq = q.get("requires_quest")
        if rq and rq not in char.completed_quests:
            continue
        # 多前置 gate(複數,全完成才開放):任務鏈匯流,如合體王頂點需三系試煉皆畢(R-arcane)。
        rqs = q.get("requires_quests")
        if rqs and any(r not in char.completed_quests for r in rqs):
            continue
        # 技能門檻 gate(R21:以 base_skill 判定,不含裝備/藥水/詛咒/誓福臨時加成 ——
        # 終極法術試煉須真本事達標,不可靠臨時加成蒙混)。dict {"destruction":75};向後相容(無欄=不限)。
        rs = q.get("requires_skill")
        if rs and any(char.base_skill(s) < v for s, v in rs.items()):
            continue
        if source == "guild":
            if q.get("faction") != faction or faction not in char.factions:
                continue
            if q.get("rank", 0) != char.factions[faction]:   # 只給當前階級的晉升任務
                continue
            # 晉升閘以 advance_block_reason 為單一真實來源(技能門檻 + lawful 通緝者暫停 + 已達頂階):
            # 不可只擋訊息而仍開放任務,否則通緝中的 lawful 會員仍能接任務晉升(審查抓到的既有破口)。
            if factions.advance_block_reason(char, gamedata, faction) is not None:
                continue
        # 告示板委託可帶 provinces 做「在地懸賞」:只在指定行省的告示板出現;
        # 無 provinces 者=全圖通用(向後相容,既有 board 委託照舊到處可接)。
        if source == "board" and province is not None:
            provs = q.get("provinces")
            if provs and province not in provs:
                continue
        out.append(qid)
    return out


def _kill_base(char: Character, obj: dict) -> int:
    """進入一個 kill 階段時,記下當下擊殺數作基準(避免回溯計入既往擊殺)。"""
    return char.kill_counts.get(obj["creature"], 0) if obj["type"] == "kill" else 0


def accept_quest(char: Character, gamedata: GameData, quest_id: str, branch: int = 0) -> None:
    char.quests[quest_id] = {"stage": 0, "branch": branch}   # 先記分支,_resolved 才取得到
    obj = _stages(_resolved(char, gamedata, quest_id))[0]["objective"]
    char.quests[quest_id]["base"] = _kill_base(char, obj)
    # 叛離:接取帶 expel_faction 的任務即背棄該陣營(如接反達貢主線 → 逐出神話黎明,
    # conjure_boon perk 隨 rank=-1 消失)。對非會員無害(已是 -1)。
    expel = gamedata.quests[quest_id].get("expel_faction")
    if expel and char.factions.get(expel, -1) >= 0:
        char.factions[expel] = -1


# --- 目標判定 -----------------------------------------------------------
def _objective_met(char: Character, gamedata: GameData, obj: dict, base: int) -> bool:
    t = obj["type"]
    if t == "kill":
        return char.kill_counts.get(obj["creature"], 0) - base >= obj["count"]
    if t == "clear_dungeon":
        return obj["dungeon"] in char.cleared_dungeons
    if t == "reach":
        return char.location_id == obj["location"]
    if t == "collect":
        return inventory.count_item(char, obj["item"]) >= obj["count"]
    return False


def objective_met(char: Character, gamedata: GameData, quest_id: str) -> bool:
    obj, _, _ = current_objective(char, gamedata, quest_id)
    return _objective_met(char, gamedata, obj, char.quests.get(quest_id, {}).get("base", 0))


def kill_progress(char: Character, gamedata: GameData, quest_id: str) -> tuple[int, int]:
    """當前 kill 階段的進度。未接取則顯示 0(避免告示板誤顯示既往擊殺)。"""
    obj, _, _ = current_objective(char, gamedata, quest_id)
    if quest_id not in char.quests:
        return 0, obj["count"]
    base = char.quests[quest_id].get("base", 0)
    return max(0, char.kill_counts.get(obj["creature"], 0) - base), obj["count"]


def objective_text(char: Character, gamedata: GameData, quest_id: str) -> str:
    obj, idx, total = current_objective(char, gamedata, quest_id)
    t = obj["type"]
    if t == "kill":
        got, need = kill_progress(char, gamedata, quest_id)
        body = f"擊殺 {gamedata.bestiary[obj['creature']]['name']} {got}/{need}"
    elif t == "clear_dungeon":
        done = "✔" if obj["dungeon"] in char.cleared_dungeons else "✘"
        body = f"肅清 {gamedata.dungeons[obj['dungeon']]['name']} {done}"
    elif t == "reach":
        done = "✔" if char.location_id == obj["location"] else "✘"
        body = f"抵達 {gamedata.location(obj['location'])['name']} {done}"
    elif t == "collect":
        have = inventory.count_item(char, obj["item"])
        body = f"取得 {gamedata.item_name(obj['item'])} {have}/{obj['count']}"
    else:
        body = ""
    return f"[{idx + 1}/{total}] {body}" if total > 1 else body


# --- 完成與階段推進 -----------------------------------------------------
def check_completion(char: Character, gamedata: GameData) -> list[dict]:
    """掃描進行中任務,推進已達標階段並結算完成者。

    回傳事件列表,每個事件為:
      {"type": "stage_advanced", "quest_id","name","stage_text","stage_idx","total"}
      {"type": "completed",      "quest_id","name","reward","promoted"}
    """
    events: list[dict] = []
    for qid in list(char.quests.keys()):
        events += _advance(char, gamedata, qid)
    return events


def _advance(char: Character, gamedata: GameData, quest_id: str) -> list[dict]:
    q = _resolved(char, gamedata, quest_id)
    stages = _stages(q)
    events: list[dict] = []

    while quest_id in char.quests:
        idx = max(0, min(char.quests[quest_id].get("stage", 0), len(stages) - 1))
        obj = stages[idx]["objective"]
        if not _objective_met(char, gamedata, obj, char.quests[quest_id].get("base", 0)):
            break
        if obj["type"] == "collect":            # 該階段達標 → 上繳消耗物品
            inventory.remove_item(char, obj["item"], obj["count"])

        if idx + 1 >= len(stages):              # 最後一階段 → 完成整個任務
            events.append(_complete(char, gamedata, quest_id))
            break

        # 推進到下一階段(若為 kill 則重設基準;保留已選分支)
        nxt = stages[idx + 1]["objective"]
        char.quests[quest_id] = {"stage": idx + 1, "base": _kill_base(char, nxt),
                                 "branch": char.quests[quest_id].get("branch", 0)}
        events.append({"type": "stage_advanced", "quest_id": quest_id, "name": q["name"],
                       "stage_text": stages[idx + 1].get("text", ""),
                       "stage_idx": idx + 1, "total": len(stages)})
    return events


def _complete(char: Character, gamedata: GameData, quest_id: str) -> dict:
    q = _resolved(char, gamedata, quest_id)
    reward = q.get("reward", {})
    char.gold += reward.get("gold", 0)
    char.fame = max(0, char.fame + reward.get("fame", 0))   # fame 可負(惡名昭彰的教徒結局),夾 ≥0
    char.infamy += reward.get("infamy", 0)                  # 惡名(教徒結局竊神之力 → 惡名遠播)
    for item_id in reward.get("items", []):
        inventory.add_item(char, item_id, 1)
    # 法術獎勵(R-arcane:奧術試煉授終極法術 → 不再商店販售)。資料驅動、去重,
    # 鏡像 creation.py 開局授法術 / events.learn_spell;char.spells 為純 list 免遷移。
    for sid in reward.get("spells", []):
        if sid not in char.spells:
            char.spells.append(sid)

    # 永久誓福:資料驅動 reward.grant_boon。達貢誓福(主線慘勝)走其獨立 dagon_* 層(敘事專屬,維持不動);
    # 其餘戴德拉親王誓福(R45)走通用 boons 層 + boons.json 登錄表。
    gb = reward.get("grant_boon")
    if gb == "dagon":
        from tesrpg.systems import dagon_boon
        dagon_boon.grant(char, gamedata)
    elif gb and gb in getattr(gamedata, "boons", {}):
        from tesrpg.systems import boons
        boons.grant(char, gamedata, gb)
    # 陣營滅亡(神話黎明被達貢獻祭殆盡):除籍 → 公會任務自動關閉、perk 消失。
    eradicate = reward.get("eradicate_faction")
    if eradicate:
        char.factions.pop(eradicate, None)
    # 世界旗標(劇情記憶 / NPC 反應 / 解鎖判定;once-fire 去重)。
    for flag in reward.get("world_flags", []):
        if flag not in char.world_events_fired:
            char.world_events_fired.append(flag)

    # 同伴角色化:招募任務末段授予具名同伴(資料驅動,鏡像 items)。有空位即入夥;
    # 滿員則僅「解鎖」(由 recruit_quest ∈ completed_quests 推導,稍後可在隊伍選單免費召集)→ 零新存檔欄。
    cid = reward.get("companion")
    if cid and cid in gamedata.companions and cid not in char.companions \
            and len(char.companions) < party.MAX_PARTY:
        char.companions.append(cid)
    # 專屬支線完成 → 該同伴羈絆躍升(忠誠弧的「交心」回報;夾 BOND_MAX)。
    # 🔴 僅對「在隊」或「具名(解散仍保留羈絆)」同伴生效 —— 否則泛用傭兵可「接支線→解散(forget 清羈絆)
    # →隊外完成→寫回 orphan 羈絆→再雇=免費 tier-2 + 加成 HP」(對抗審查確認的破口)。
    for bcid, n in reward.get("bond", {}).items():
        if bcid in gamedata.companions and (bcid in char.companions
                                            or party.keeps_state_on_dismiss(gamedata, bcid)):
            char.companion_bond[bcid] = min(party.BOND_MAX, char.companion_bond.get(bcid, 0) + n)

    # 領主委託(source "ruler"):完成 → 該城功勳 +standing(城 = 其領主目錄含此 qid 者)
    standing_loc = None
    if q.get("source") == "ruler":
        amount = reward.get("standing", 1)
        for loc_id, ruler in gamedata.rulers.items():
            if quest_id in ruler.get("quests", []):
                char.city_standing[loc_id] = char.city_standing.get(loc_id, 0) + amount
                standing_loc = loc_id
                break

    promoted = None
    stipend = 0
    if q.get("faction") and q.get("rank") is not None and q["faction"] in char.factions:
        if char.factions[q["faction"]] == q["rank"]:
            ranks = gamedata.factions[q["faction"]]["ranks"]
            new_rank = min(q["rank"] + 1, len(ranks) - 1)   # 夾限,階級索引不可越界
            char.factions[q["faction"]] = new_rank
            promoted = (q["faction"], ranks[new_rank])
            stipend = STIPEND_PER_RANK * new_rank           # 晉升俸祿(階級越高給越多)
            char.gold += stipend

    char.quests.pop(quest_id, None)
    char.completed_quests.append(quest_id)
    return {"type": "completed", "quest_id": quest_id, "name": q["name"],
            "reward": reward, "promoted": promoted, "stipend": stipend,
            "standing_loc": standing_loc}
