"""公會:入會、階級查詢。晉升由 quests 完成公會任務時觸發。"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character


def is_member(char: Character, faction_id: str) -> bool:
    return faction_id in char.factions


def rank_index(char: Character, faction_id: str) -> int:
    return char.factions.get(faction_id, -1)


def rank_name(char: Character, gamedata: GameData, faction_id: str) -> str:
    idx = rank_index(char, faction_id)
    if idx < 0:
        return "非會員"
    ranks = gamedata.factions[faction_id]["ranks"]
    return ranks[min(idx, len(ranks) - 1)]


def can_join(char: Character, gamedata: GameData, faction_id: str) -> bool:
    if is_member(char, faction_id):
        return False
    req = gamedata.factions[faction_id].get("join_req", {}).get("skill")
    if req:
        skill, val = req
        return char.skill(skill) >= val
    return True


def join(char: Character, faction_id: str) -> None:
    if faction_id not in char.factions:
        char.factions[faction_id] = 0      # 入會即最低階
