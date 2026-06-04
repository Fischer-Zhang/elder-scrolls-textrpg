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
    base = 0.5 + (char.skill(check["skill"]) - check["difficulty"]) / 100.0
    base += (char.attr("luck") - 40) * 0.002
    return max(0.1, min(0.95, base))


def resolve_check(char: Character, check: dict, rng: RNG) -> bool:
    return rng.chance(check_chance(char, check))


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

    stats.clamp_resources(char)
    return {"messages": messages, "combat": combat_foes}
