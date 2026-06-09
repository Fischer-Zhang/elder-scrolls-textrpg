"""NPC 對話與好感 (disposition):說服(口才)、賄賂。

好感影響 NPC 是否願意託付任務。說服會 learn-by-doing 鍛鍊口才。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import mastery, progression

BRIBE_COST = 10
TALK_DOWN_MAX = 120          # 可「說服衛兵」的最高賞金(大罪說不過去;對齊武士 ~100 量級)
INTIMIDATE_DIFFICULTY = 40   # 威嚇喝退基準難度(對齊 events.json 既有威嚇 DC40)
INTIMIDATABLE = {"bandit"}   # 可威嚇喝退的弱人形敵(盜匪;不死/魔人/野獸/boss/具名目標皆不可)


def persuade_delta(skill: int) -> int:
    """說服成功的好感增益,隨口才成長(0→+6、50→+12、100→+18)→ 高口才勝過 bribe(+12)且免金幣。"""
    return round(6 + skill * 0.12)


def disposition(char: Character, gamedata: GameData, npc_id: str) -> int:
    base = gamedata.npcs[npc_id]["disposition"]
    return max(0, min(100, base + char.npc_disposition.get(npc_id, 0)))


def _adjust(char: Character, npc_id: str, delta: int) -> None:
    char.npc_disposition[npc_id] = char.npc_disposition.get(npc_id, 0) + delta


def persuade_chance(char: Character, gamedata: GameData, npc_id: str) -> float:
    """說服成功率(唯讀,供 UI 預示;與 persuade 公式單一來源)。折服里程碑 → 1.0。"""
    if mastery.can_guaranteed_persuade(char, gamedata, npc_id):
        return 1.0
    skill = char.skill("speechcraft")
    return max(0.1, min(0.9, 0.35 + (skill + char.attr("personality") - 50) * 0.005))


def persuade(char: Character, gamedata: GameData, npc_id: str, rng: RNG) -> dict:
    """以口才說服。成功提升好感,失敗略降。回傳 {ok, delta, hours, tired, skill_events}。

    每次說服付出口才 practice 的體力 + 時間成本(時間由呼叫端推進),與酒館練說服
    對齊,讓「對話磨嘴皮」不再是零代價的免費刷口才/刷好感(折服里程碑路徑同樣付費)。
    """
    skill = char.skill("speechcraft")
    delta = persuade_delta(skill)
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    events = progression.use_skill(char, gamedata, "speechcraft", xp)
    # 里程碑「辯舌·折服」:口才大師對每個 NPC 可一次性必定說服(記入 persuaded_npcs)。
    if mastery.can_guaranteed_persuade(char, gamedata, npc_id):
        char.persuaded_npcs.append(npc_id)
        _adjust(char, npc_id, delta)
        return {"ok": True, "delta": delta, "charmed": True,
                "hours": hours, "tired": tired, "skill_events": events}
    chance = max(0.1, min(0.9, 0.35 + (skill + char.attr("personality") - 50) * 0.005))
    if rng.chance(chance):
        _adjust(char, npc_id, delta)
        return {"ok": True, "delta": delta, "hours": hours, "tired": tired, "skill_events": events}
    _adjust(char, npc_id, -5)
    return {"ok": False, "delta": -5, "hours": hours, "tired": tired, "skill_events": events}


def bribe(char: Character, gamedata: GameData, npc_id: str) -> dict:
    if char.gold < BRIBE_COST:
        return {"ok": False, "message": "金幣不足。"}
    char.gold -= BRIBE_COST
    _adjust(char, npc_id, 12)
    return {"ok": True, "message": f"你塞了 {BRIBE_COST} 金,對方臉色和緩了些。"}


def offered_quest(char: Character, gamedata: GameData, npc_id: str) -> str | None:
    """好感足夠且任務未完成/未接 → 回傳該 NPC 可給的任務 id。"""
    npc = gamedata.npcs[npc_id]
    qid = npc.get("quest")
    if not qid:
        return None
    if qid in char.quests or qid in char.completed_quests:
        return None
    if disposition(char, gamedata, npc_id) < npc.get("quest_disposition", 60):
        return None
    return qid


# --- 拓展用途①:說服衛兵減免賞金(犯罪/社交;對位武士特權,走技能)----------
def talk_down_chance(char: Character, bounty: int) -> float:
    """以口才說退衛兵的成功率:吃口才+魅力,賞金越高越難。夾 0.05–0.80。"""
    return max(0.05, min(0.80,
               0.10 + (char.skill("speechcraft") + char.attr("personality") - 50) * 0.005 - bounty * 0.002))


def talk_down_guard(char: Character, gamedata: GameData, province: str, rng: RNG) -> dict:
    """以口才說退攔路衛兵(僅小額賞金,呼叫端負責 TALK_DOWN_MAX 門檻)。
    付 speechcraft practice(體力+時間)→ 非免費刷;成功 → 清該省賞金,失敗 → 賞金不動。"""
    from tesrpg.systems import crime
    b = crime.bounty(char, province)
    chance = talk_down_chance(char, b)
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    events = progression.use_skill(char, gamedata, "speechcraft", xp)
    ok = rng.chance(chance)
    if ok:
        crime.clear_bounty(char, province)
    return {"ok": ok, "chance": chance, "hours": hours, "tired": tired, "skill_events": events}


# --- 拓展用途②:威嚇喝退弱人形敵(遭遇/避戰;對位潛行撤退)-------------------
def can_intimidate(gamedata: GameData, enemies) -> bool:
    """全部敵人皆屬可威嚇的弱人形(盜匪類)→ 才可威嚇喝退。"""
    return bool(enemies) and all(getattr(e, "template_id", None) in INTIMIDATABLE for e in enemies)


def intimidate_chance(char: Character, enemies, night: bool) -> float:
    """威嚇喝退成功率:吃口才,敵越多越難、夜間略難。夾 0.05–0.90(仿 events 既有威嚇檢定)。"""
    chance = 0.5 + (char.skill("speechcraft") - INTIMIDATE_DIFFICULTY) / 100.0 - (len(enemies) - 1) * 0.15
    if night:
        chance -= 0.10
    return max(0.05, min(0.90, chance))


def intimidate(char: Character, gamedata: GameData, enemies, night: bool, rng: RNG) -> dict:
    """威嚇喝退弱人形敵(避戰)。付 speechcraft practice(體力+時間)→ 練口才但非免費刷;
    成功 → 敵退去(呼叫端避戰、**不給任何戰利/擊殺/xp 來自敵人**),失敗 → 接戰(警覺)。"""
    chance = intimidate_chance(char, enemies, night)
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    events = progression.use_skill(char, gamedata, "speechcraft", xp)
    return {"ok": rng.chance(chance), "chance": chance,
            "hours": hours, "tired": tired, "skill_events": events}
