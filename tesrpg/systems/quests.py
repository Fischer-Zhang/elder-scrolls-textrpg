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

# 任務目標/獎勵的「已實作」契約(單一真實來源:_objective_met 與 _complete 必須與此一致)
# purge_dungeon(R111):掃蕩「重踞」的已清地城 —— 判定走 base 快照(接取時記下該地城的
# 重踞時間戳;掃蕩把時間戳嚴格推進未來 → met=時間戳>base),不碰 cleared_dungeons(單調)
# → 可 repeatable 而不觸 R79「clear_dungeon 即時達標=免費金」破口(天然閘=只在重踞期間現身)。
_OBJECTIVE_TYPES = frozenset({"kill", "clear_dungeon", "reach", "collect", "assassinate", "purge_dungeon"})
_REWARD_KEYS = frozenset({
    "gold", "fame", "infamy", "items", "spells", "grant_boon",
    "world_flags", "eradicate_faction", "companion", "bond", "standing",
    "cover_deltas", "clear_cover", "defect",   # R100 雙面間諜:漂移 / 抽身 / 叛變
    "clear_infamy",                            # R107 朝聖贖罪:惡名歸零(KotN 正典·唯一清除途徑)
})
# 可重複委託(repeatable:常態世界脈動聚光款)只准帶「可無限刷的安全純量獎勵」——
# 絕不帶 items/spells/boons/companion(一次性/限定內容),否則可刷取限定法術/誓福/同伴
# → 破壞稀缺性與反 min-max。由 schema 測試把關(test_data_schema)。
# R100 cover_deltas:臥底忠誠/掩護漂移(非物質·僅臥底中生效·grind 即「過雙面人生」的 loop 本身)→ 准。
# R107 clear_infamy:朝聖可重複(再犯罪可再贖),歸零非累積 → 無限刷=無限洗白,代價=跨省長征+試煉 → 准。
# R108 world_flags:寫入本身冪等去重(once-fire,見 _complete)→ repeatable 重複完成不重複發旗 → 准
#(朝聖首完成授「pilgrim_vision」異象旗,開聖物線)。
_REPEATABLE_REWARD_KEYS = frozenset({"gold", "fame", "infamy", "cover_deltas", "clear_infamy", "world_flags"})


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
                     faction: str | None = None, province: str | None = None,
                     day: int | None = None, now: int | None = None) -> list[str]:
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
        if q.get("requires_infamy") and char.infamy < q["requires_infamy"]:   # R101 惡名閘(對稱 requires_fame)
            continue
        # 陣營身分 gate:需為某陣營會員(達指定階)才開放(如教徒頂點 md7 需 mythic_dawn 滿階)。
        rf = q.get("requires_faction")
        if rf and char.factions.get(rf, -1) < q.get("requires_faction_rank", 0):
            continue
        # R100 臥底 gate:潛入任務只在掩護該公會時現身(cover_guild 必等於 requires_cover)。
        rc = q.get("requires_cover")
        if rc and getattr(char, "cover_guild", "") != rc:
            continue
        rl = q.get("requires_loyalty")   # 忠誠閾(結局:抽身 max / 叛變 min)
        if rl:
            lo = getattr(char, "cover_loyalty", 0)
            if "min" in rl and lo < rl["min"]:
                continue
            if "max" in rl and lo > rl["max"]:
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
        if source == "board":
            provs = q.get("provinces")
            if province is not None and provs and province not in provs:
                continue
            # 常態世界脈動:可重複委託只在被 active 脈動「聚光」時現身於告示板(R-pulse)。
            # 需 province + day + 正被聚光,缺一即隱藏(不灰顯;防 province/day 缺漏時 ungated 洩漏)。
            # R111 例外:purge_dungeon 清剿委託的天然閘=目標地城「正被重踞」(掃蕩即消失、
            # 下輪重踞再現)—— 比脈動聚光更強的自然節流,不走 spotlight;需 now(絕對小時)。
            if q.get("repeatable"):
                obj0 = _stages(q)[0]["objective"] if (q.get("stages") or q.get("objective")) else {}
                if obj0.get("type") == "purge_dungeon":
                    from tesrpg.systems import dungeon
                    if province is None or now is None \
                            or not dungeon.is_reinfested(char, gamedata, obj0["dungeon"], now):
                        continue
                else:
                    from tesrpg.systems import worldpulse
                    if province is None or day is None \
                            or qid not in worldpulse.spotlighted_board_quests(char, gamedata, province, day):
                        continue
        out.append(qid)
    return out


def _objective_base(char: Character, obj: dict) -> int:
    """進入一個階段時記下的「基準快照」:kill=當下擊殺數(避免回溯計入既往擊殺);
    purge_dungeon=當下該地城的重踞時間戳(掃蕩會把時間戳嚴格推進未來 → met=戳>base,
    無需時間存取、零新狀態)。其餘型別=0。"""
    if obj["type"] == "kill":
        return char.kill_counts.get(obj["creature"], 0)
    if obj["type"] == "purge_dungeon":
        return int(getattr(char, "dungeon_reinfest_at", {}).get(obj["dungeon"], 0))
    return 0


def accept_quest(char: Character, gamedata: GameData, quest_id: str, branch: int = 0) -> None:
    char.quests[quest_id] = {"stage": 0, "branch": branch}   # 先記分支,_resolved 才取得到
    obj = _stages(_resolved(char, gamedata, quest_id))[0]["objective"]
    char.quests[quest_id]["base"] = _objective_base(char, obj)
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
    if t == "assassinate":   # R109:暗殺指定具名 NPC(單 `npc` 或多 `npcs`·達標=全部已在 murdered_npcs)
        murdered = getattr(char, "murdered_npcs", [])
        return all(n in murdered for n in _hit_targets(obj))
    if t == "purge_dungeon":   # R111:掃蕩重踞 —— 時間戳被 mark_purged 嚴格推進 → 戳 > 接取時快照
        return int(getattr(char, "dungeon_reinfest_at", {}).get(obj["dungeon"], 0)) > base
    return False


def _hit_targets(obj: dict) -> list:
    """assassinate objective 的目標 NPC 清單(支援單 `npc` 或多 `npcs`)。"""
    return list(obj.get("npcs") or ([obj["npc"]] if obj.get("npc") else []))


def objective_met(char: Character, gamedata: GameData, quest_id: str) -> bool:
    obj, _, _ = current_objective(char, gamedata, quest_id)
    return _objective_met(char, gamedata, obj, char.quests.get(quest_id, {}).get("base", 0))


def _active_assassinate_quests(char: Character, gamedata: GameData):
    """產生 (qid, quest_state, objective) for 每個進行中且當前階段為 assassinate 的任務。"""
    for qid, qstate in char.quests.items():
        if qid not in gamedata.quests:
            continue
        obj, _, _ = current_objective(char, gamedata, qid)
        if obj.get("type") == "assassinate":
            yield qid, qstate, obj


def is_active_hit_target(char: Character, gamedata: GameData, nid: str) -> bool:
    """nid 是否為某進行中暗殺合約的(尚存)目標(R109 B2:接了合約=知道對方是誰 → 揭露潛伏身分)。"""
    for _qid, _qs, obj in _active_assassinate_quests(char, gamedata):
        if nid in _hit_targets(obj):
            return True
    return False


def assassination_sanctioned(char: Character, gamedata: GameData, nid: str) -> bool:
    """nid 是否為某進行中「授權暗殺」任務(`sanctioned:true`,如反間肅清敵諜)的目標。
    授權目標的擊殺=除害無罰(不走謀殺目擊 roll);任務外殺同一人仍是謀殺(受罰)。"""
    for qid, _qs, obj in _active_assassinate_quests(char, gamedata):
        if nid in _hit_targets(obj) and gamedata.quests[qid].get("sanctioned"):
            return True
    return False


def record_hit_day(char: Character, gamedata: GameData, nid: str, today: int) -> None:
    """剛暗殺了 nid:若它屬某進行中 assassinate 任務且仍有同夥存活,戳記首殺日(quest state·
    不新增存檔欄)→ 逾 1 日存活同夥聞訊備戰(hit_target_alerted 讀之)。"""
    murdered = getattr(char, "murdered_npcs", [])
    for qid, qstate, obj in _active_assassinate_quests(char, gamedata):
        tg = _hit_targets(obj)
        if nid in tg and qstate.get("hit_day") is None:
            if any(t not in murdered for t in tg if t != nid):   # 尚有同夥存活
                qstate["hit_day"] = today


def hit_target_alerted(char: Character, gamedata: GameData, nid: str, today: int) -> bool:
    """nid 是否為「同案同夥已死、且逾 1 日」的存活暗殺目標 → 聞訊備戰(改用強化戰鬥模板)。
    使用者拍板:殺第一位後拖過 1 天,另一名會武裝自己。日期戳記於 `_advance`(quest state `hit_day`)。"""
    murdered = getattr(char, "murdered_npcs", [])
    if nid in murdered:
        return False
    for qid, qstate, obj in _active_assassinate_quests(char, gamedata):
        tg = _hit_targets(obj)
        if nid not in tg:
            continue
        hit_day = qstate.get("hit_day")
        partner_dead = any(t in murdered for t in tg if t != nid)
        if partner_dead and hit_day is not None and today - hit_day >= 1:
            return True
    return False


def active_hunt_target(char: Character, gamedata: GameData, loc_id: str) -> str | None:
    """R109 任務條件式狩獵:若玩家有 active `kill` 任務,其目標是**平時不入野遇池的劇情敵**
    (bestiary weight==0),且本地點在該任務的 `provinces`(或任務無省份限制)→ 回該 creature_tid,
    供 world.travel/action_explore 在狩獵時高機率生成之(否則 None → 遭遇邏輯逐位元組不變)。

    決定性:多個符合取排序最前。只認 weight==0 的劇情敵(一般野遇怪本就在池裡不需鉤子)。"""
    prov = None
    locs = (gamedata.world or {}).get("locations", {})
    if loc_id in locs:
        prov = locs[loc_id].get("province")
    hits = []
    for qid in char.quests:
        q = gamedata.quests.get(qid)
        if not q:
            continue
        obj, _, _ = current_objective(char, gamedata, qid)
        if obj.get("type") != "kill":
            continue
        tid = obj.get("creature")
        m = gamedata.bestiary.get(tid, {})
        if m.get("weight", 1) != 0:          # 只認「顯式 weight==0」的劇情敵(與遭遇池預設 1 一致)
            continue
        # R109 狩獵定位(使用者拍板):唯一 villain(墮落祭司等)精確到 `hunt_location`(單一地點);
        # 泛用群獵(反間複數密探)用 `provinces`(整省荒野)。兩者皆須明確指定,否則不獵
        # → 無定位的 faction 合約不會在全八省亂刷。
        hl = q.get("hunt_location")
        if hl is not None:
            if loc_id != hl:
                continue
        else:
            provs = q.get("provinces")
            if not provs or prov not in provs:
                continue
        hits.append(tid)
    return sorted(hits)[0] if hits else None


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
    elif t == "assassinate":   # R109:目標=具名 NPC(顯示名+所在地供指路;多目標逐一列狀態)
        murdered = getattr(char, "murdered_npcs", [])
        parts = []
        locs = (gamedata.world or {}).get("locations", {})
        for nid in _hit_targets(obj):
            npc = gamedata.npcs.get(nid, {})
            loc = gamedata.location(npc["location"])["name"] if npc.get("location") in locs else "?"
            parts.append(f"{npc.get('name', nid)}(在 {loc}){'✔' if nid in murdered else '✘'}")
        body = "暗殺 " + "、".join(parts)
    elif t == "purge_dungeon":   # R111:掃蕩重踞(達標=時間戳已被掃蕩推進,同 _objective_met 口徑;
        # 未接取(告示板預覽)恆 ✘ —— 否則 base 預設 0 而時間戳恆 >0 → 預覽全 ✔,鏡像 kill_progress 的守門)
        base = char.quests.get(quest_id, {}).get("base", 0)
        done = "✔" if (quest_id in char.quests
                       and int(getattr(char, "dungeon_reinfest_at", {}).get(obj["dungeon"], 0)) > base) else "✘"
        body = f"掃蕩重踞的{gamedata.dungeons[obj['dungeon']]['name']} {done}"
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
        char.quests[quest_id] = {"stage": idx + 1, "base": _objective_base(char, nxt),
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
    # R107 朝聖贖罪:惡名歸零(KotN 正典;R84「惡名終身」的刻意例外·使用者拍板)。
    # 下游全隨之歸零:亡命徒階梯/銷贓加價/惡名稱號(crime)、社交冷待(renown)—— 皆純衍生層。
    # 法律賞金 bounties **不清**(朝聖贖罪名、不贖法度;雙軸各走各的)。
    if reward.get("clear_infamy"):
        char.infamy = 0
    # 陣營滅亡(神話黎明被達貢獻祭殆盡):除籍 → 公會任務自動關閉、perk 消失。
    eradicate = reward.get("eradicate_faction")
    if eradicate:
        char.factions.pop(eradicate, None)
    # 世界旗標(劇情記憶 / NPC 反應 / 解鎖判定;once-fire 去重)。
    # new_flags=本次「首次寫入」者(R108:repeatable 任務重複完成不重播旗標敘事,如朝聖異象)。
    new_flags: list = []
    for flag in reward.get("world_flags", []):
        if flag not in char.world_events_fired:
            char.world_events_fired.append(flag)
            new_flags.append(flag)

    # R100 雙面間諜:價值觀漂移(loyalty)/掩護(secrecy)+ 結局狀態變更(資料驅動;僅臥底中生效)。
    cd = reward.get("cover_deltas")
    if cd or reward.get("clear_cover") or reward.get("defect"):
        from tesrpg.systems import undercover
        if cd:
            undercover.apply_cover_deltas(char, loyalty_delta=cd.get("loyalty", 0),
                                          secrecy_delta=cd.get("secrecy", 0))
        if reward.get("defect"):          # 真正叛變:棄 A 入 B(B 變真會籍)
            undercover.defect(char, gamedata)
        elif reward.get("clear_cover"):   # 忠誠抽身:乾淨退出臥底·留在 A
            undercover.clear_cover(char)

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
    # 可重複委託(常態世界脈動聚光款)不進 completed_quests → is_done 恆 False、可再接;
    # 能見度全由脈動聚光 active window 控制(available_quests),不污染 requires_quest 鏈(R-pulse)。
    if not q.get("repeatable"):
        char.completed_quests.append(quest_id)
    return {"type": "completed", "quest_id": quest_id, "name": q["name"],
            "reward": reward, "promoted": promoted, "stipend": stipend,
            "standing_loc": standing_loc, "new_flags": new_flags}
