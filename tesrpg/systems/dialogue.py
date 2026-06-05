"""NPC 對話與好感 (disposition):說服(口才)、賄賂。

好感影響 NPC 是否願意託付任務。說服會 learn-by-doing 鍛鍊口才。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import mastery, progression

BRIBE_COST = 10
PERSUADE_XP = 0.5


def disposition(char: Character, gamedata: GameData, npc_id: str) -> int:
    base = gamedata.npcs[npc_id]["disposition"]
    return max(0, min(100, base + char.npc_disposition.get(npc_id, 0)))


def _adjust(char: Character, npc_id: str, delta: int) -> None:
    char.npc_disposition[npc_id] = char.npc_disposition.get(npc_id, 0) + delta


def persuade(char: Character, gamedata: GameData, npc_id: str, rng: RNG) -> dict:
    """以口才說服。成功提升好感,失敗略降。回傳 {ok, delta, skill_events}。"""
    skill = char.skill("speechcraft")
    events = progression.use_skill(char, gamedata, "speechcraft", PERSUADE_XP)
    # 里程碑「辯舌·折服」:口才大師對每個 NPC 可一次性必定說服(記入 persuaded_npcs)。
    if mastery.can_guaranteed_persuade(char, gamedata, npc_id):
        char.persuaded_npcs.append(npc_id)
        _adjust(char, npc_id, 10)
        return {"ok": True, "delta": 10, "charmed": True, "skill_events": events}
    chance = max(0.1, min(0.9, 0.35 + (skill + char.attr("personality") - 50) * 0.005))
    if rng.chance(chance):
        _adjust(char, npc_id, 10)
        return {"ok": True, "delta": 10, "skill_events": events}
    _adjust(char, npc_id, -5)
    return {"ok": False, "delta": -5, "skill_events": events}


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
