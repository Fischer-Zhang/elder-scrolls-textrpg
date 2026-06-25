"""事件引擎(DESIGN 3.8):資料驅動的隨機遭遇 / 奇遇。

事件在特定情境(travel / rest / explore / arrive)按權重抽出,呈現給玩家一段
文字與數個選項。選項可帶「需求」(金幣/技能/物品/任務狀態)決定是否可選,
可帶「技能判定」分出成敗分支,效果則複用既有系統(金幣/物品/技能 xp/聲望/
賞金/任務/戰鬥)。

純規則放這裡;戰鬥與互動呈現由 main 處理(combat 類效果以「延遲動作」回傳)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import crime, inventory, progression, stats

# 各情境「會不會發生事件」的基礎機率(由 main 的 maybe_event 使用)
CONTEXT_CHANCE = {"travel": 0.35, "rest": 0.25, "explore": 0.50, "arrive": 0.20}


# --- 需求判定(同時用於事件觸發的 require 與選項的 requirements)---------
def meets(char: Character, gamedata: GameData, req: dict | None) -> bool:
    if not req:
        return True
    if char.gold < req.get("gold_min", 0):
        return False
    for s, v in req.get("skill_min", {}).items():
        if char.skill(s) < v:
            return False
    for a, v in req.get("attr_min", {}).items():
        if char.attr(a) < v:
            return False
    if "item" in req and inventory.count_item(char, req["item"]) < req.get("item_qty", 1):
        return False
    if "faction" in req and req["faction"] not in char.factions:
        return False
    qa = req.get("quest_available")
    if qa and (qa in char.quests or qa in char.completed_quests):
        return False
    # --- 對話樹共用的無 state 條件(events.json 現況不用 → 對既有事件零影響)---
    if "allegiance" in req and char.allegiance != req["allegiance"]:
        return False
    if char.fame < req.get("min_fame", 0):
        return False
    if char.infamy < req.get("min_infamy", 0):
        return False
    if "is_member" in req and req["is_member"] not in char.factions:
        return False
    for fid, r in req.get("member_rank_min", {}).items():
        if char.factions.get(fid, -1) < r:
            return False
    for cause, v in req.get("faction_standing_min", {}).items():
        if getattr(char, "faction_standing", {}).get(cause, 0) < v:
            return False
    if req.get("is_vampire") and not char.is_vampire:
        return False
    if req.get("is_werewolf") and not char.is_werewolf:
        return False
    return True


def option_available(char: Character, gamedata: GameData, option: dict) -> bool:
    return meets(char, gamedata, option.get("requirements"))


# --- 觸發資格 -----------------------------------------------------------
def _trigger_ok(event: dict, state, gamedata: GameData, context: str) -> bool:
    trig = event.get("trigger", {})
    if context not in trig.get("contexts", []):
        return False
    char = state.player
    if char.level < trig.get("min_level", 1):
        return False
    if "max_level" in trig and char.level > trig["max_level"]:
        return False
    loc = gamedata.location(char.location_id)
    if "location_types" in trig and loc["type"] not in trig["location_types"]:
        return False
    if "provinces" in trig and loc["province"] not in trig["provinces"]:
        return False
    return meets(char, gamedata, trig.get("require"))


def eligible_events(state, gamedata: GameData, context: str) -> list[str]:
    return [eid for eid, e in gamedata.events.items() if _trigger_ok(e, state, gamedata, context)]


def pick_event(state, gamedata: GameData, context: str, rng: RNG) -> str | None:
    pool = eligible_events(state, gamedata, context)
    if not pool:
        return None
    weights = [gamedata.events[eid].get("weight", 1) for eid in pool]
    total = sum(weights)
    r = rng.roll(0, total)
    acc = 0.0
    for eid, w in zip(pool, weights):
        acc += w
        if r <= acc:
            return eid
    return pool[-1]


# --- 技能判定 -----------------------------------------------------------
def check_chance(char: Character, check: dict) -> float:
    from tesrpg import formulas
    base = 0.5 + (char.skill(check["skill"]) - check["difficulty"]) / 100.0
    base += formulas.luck_fortune(char.attr("luck"))   # 幸運「時來運轉」(與撬鎖/逃跑統一口徑)
    return max(0.1, min(0.95, base))


def resolve_check(char: Character, check: dict, rng: RNG) -> bool:
    return rng.chance(check_chance(char, check))


# --- 野採:生態系材料池「定值預算」抽取(R94·稀有度功能化)----------------------
# 採集動作 / 物品 / 數量解耦,且稀有度真有意義:偵查(scout)決定一個「浮動預算」
# (點數),稀有材料每件成本更高(tier 成本 common1/uncommon3/rare6)。在預算內反覆
# 加權抽、扣成本,直到買不起 → 「偵查高 → 大量低稀有 OR 少量高稀有」自然湧現。
# 預算帶 jitter(浮動制)→ 低偵查仍有「非常小機會」湊到一個 rare(預算偶爾擦邊買得起)。
# 決定性走傳入的 rng(存檔可重現);不碰 combat/formulas → sim byte-identical。
_FORAGE_BASE_BUDGET = 4          # 基礎預算點數(scout 0 的底·對標舊 cap 4)
_FORAGE_BUDGET_PER_SCOUT = 8     # 每 N 點偵查 +1 預算
_FORAGE_BUDGET_JITTER = 2        # 浮動幅度(rng.randint(0,J)·讓低偵查偶爾擦邊買得起 rare)
_FORAGE_TIER_COST = {"common": 1, "uncommon": 3, "rare": 6}   # 每件成本(稀有更貴=「定值分配」本體)
_FORAGE_MAX_QTY_PER_ITEM = 3     # 單一材料一趟最多幾件(防預算全砸同一 common)
_FORAGE_TIER_WEIGHTS = {"common": 4, "uncommon": 2, "rare": 1}   # 抽中傾向(常見>少見>稀有)


def _weighted_pick(weighted: list, rng: RNG):
    """從 [(item, weight), ...] 依權重抽一個(決定性:整數累積 + rng.randint)。"""
    total = sum(w for _, w in weighted)
    r = rng.randint(1, total)
    acc = 0
    for item, w in weighted:
        acc += w
        if r <= acc:
            return item
    return weighted[-1][0]


def _forage_budget(scout: int, rng: RNG) -> int:
    """偵查 → 浮動預算點數(jitter 讓低偵查偶爾擦邊買得起一個 rare)。"""
    return _FORAGE_BASE_BUDGET + scout // _FORAGE_BUDGET_PER_SCOUT + rng.randint(0, _FORAGE_BUDGET_JITTER)


def forage_pool_draw(char: Character, gamedata: GameData, pool_id: str, rng: RNG) -> list:
    """生態系材料池「定值預算」抽取:偵查決定浮動預算,稀有材料每件成本高;在預算內加權
    反覆抽、扣成本 → 大量低稀有 OR 少量高稀有自然湧現。回傳 [(item_id, qty), ...]。"""
    pool = (gamedata.ecology.get("pools", {}) or {}).get(pool_id, {})
    # 候選 = {item_id: (weight, cost)};_ 前綴鍵(_name/_doc)非 list → 跳過
    cand: dict = {iid: (_FORAGE_TIER_WEIGHTS[tier], _FORAGE_TIER_COST[tier])
                  for tier in _FORAGE_TIER_WEIGHTS for iid in pool.get(tier, [])}
    if not cand:
        return []
    budget = _forage_budget(int(char.skill("scout")), rng)
    got: dict = {}
    spent = 0
    # 防呆迴圈上限 = 該池理論最大產出(每材料各 cap 件)+1 → 絕不靜默截斷,純終止保險
    for _ in range(len(cand) * _FORAGE_MAX_QTY_PER_ITEM + 1):
        affordable = [(iid, w) for iid, (w, c) in cand.items()
                      if c <= budget - spent and got.get(iid, 0) < _FORAGE_MAX_QTY_PER_ITEM]
        if not affordable:
            break
        iid = _weighted_pick(affordable, rng)
        got[iid] = got.get(iid, 0) + 1
        spent += cand[iid][1]
    return sorted(got.items())


# --- 效果套用(combat 類延遲回傳給 main)--------------------------------
def apply_effects(state, gamedata: GameData, effects: list, rng: RNG) -> dict:
    char = state.player
    messages: list[str] = []
    combat_foes: list[str] = []

    for ef in effects or []:
        t = ef["type"]
        if t == "gold":
            char.gold = max(0, char.gold + ef["amount"])
            messages.append(f"金幣 {'+' if ef['amount'] >= 0 else ''}{ef['amount']}")
        elif t == "item":
            qty = ef.get("qty", 1)
            if qty >= 0:
                inventory.add_item(char, ef["item"], qty)
                messages.append(f"獲得 {gamedata.item_name(ef['item'])} ×{qty}")
            else:
                inventory.remove_item(char, ef["item"], -qty)
                messages.append(f"失去 {gamedata.item_name(ef['item'])} ×{-qty}")
        elif t == "skill_xp":
            progression.use_skill(char, gamedata, ef["skill"], ef["amount"])
        elif t == "heal":
            char.health = char.max_health if ef["amount"] == "full" else min(char.max_health, char.health + ef["amount"])
        elif t == "restore_magicka":
            char.magicka = char.max_magicka if ef["amount"] == "full" else min(char.max_magicka, char.magicka + ef["amount"])
        elif t == "restore_fatigue":
            char.fatigue = char.max_fatigue if ef["amount"] == "full" else min(char.max_fatigue, char.fatigue + ef["amount"])
        elif t == "damage":
            char.health = max(0, char.health - ef["amount"])
            messages.append(f"你受了 {ef['amount']} 點傷害")
        elif t == "fame":
            char.fame += ef["amount"]
            messages.append(f"聲望 +{ef['amount']}")
        elif t == "infamy":
            char.infamy += ef["amount"]
            messages.append(f"惡名 +{ef['amount']}")
        elif t == "bounty":
            crime.add_bounty(char, crime.province_of(char, gamedata), ef["amount"])
            messages.append(f"賞金 +{ef['amount']}")
        elif t == "start_quest":
            if ef["quest"] not in char.quests and ef["quest"] not in char.completed_quests:
                from tesrpg.systems import quests
                quests.accept_quest(char, gamedata, ef["quest"])
                messages.append(f"接下任務:{gamedata.quests[ef['quest']]['name']}")
        elif t == "learn_spell":
            if ef["spell"] not in char.spells:
                char.spells.append(ef["spell"])
                messages.append(f"習得法術:{gamedata.spells[ef['spell']]['name']}")
        elif t == "combat":
            combat_foes.append(ef["creature"])
        elif t == "message":
            messages.append(ef["text"])
        elif t == "forage_pool":
            picks = forage_pool_draw(char, gamedata, ef["pool"], rng)
            if picks:
                for iid, qty in picks:
                    inventory.add_item(char, iid, qty)
                    messages.append(f"採得 {gamedata.item_name(iid)} ×{qty}")
                # learn-by-doing:採集練偵查、辨識練煉金(空手不練)
                progression.use_skill(char, gamedata, "scout", ef.get("scout_xp", 0.4))
                progression.use_skill(char, gamedata, "alchemy", ef.get("alchemy_xp", 0.5))
            else:
                messages.append("這一帶幾乎沒有可採的材料。")

    stats.clamp_resources(char)
    return {"messages": messages, "combat": combat_foes}
