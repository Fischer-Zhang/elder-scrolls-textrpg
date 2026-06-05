"""招兵買馬(城戰的金幣/領袖路線):親衛(將領=companions)+ 軍隊(士兵)+ 營地。階段一。

士兵門檻:你是「領主」(持武士銜 / 已征服城)或「首領」(任一公會掌門),且已建立營地
(野外紮營 / 佔領已清空地城)。士兵在攻城當**實戰援軍**(少數上場)+ 解鎖**大軍壓境**削守軍方略。
階段二再加軍餉 / 永久傷亡 / 逃兵。加兵種純改 companions.json(`troop:true` 者不在旅店招、僅供點兵)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

SOLDIER_TROOP = "footman"     # 士兵在 run_battle 出場用的兵種模板(companions.json,troop:true)
SOLDIER_COST = 40             # 每名士兵招募金
MAX_SOLDIERS = 30             # 士兵上限
FIELD_CAP = 6                 # 攻城時實際上場的士兵數上限(其餘戰力以大軍壓境體現)
ARMY_SOFTEN_PER = 3           # 大軍壓境:每名士兵削守軍量


def is_guildmaster(char: Character, gamedata: GameData) -> bool:
    for fid, rank in char.factions.items():
        ranks = gamedata.factions.get(fid, {}).get("ranks", [])
        if ranks and rank >= len(ranks) - 1:
            return True
    return False


def is_warlord(char: Character, gamedata: GameData) -> bool:
    """有資格招募軍隊:領主(持武士銜 / 已征服城)或首領(任一公會掌門)。"""
    return bool(char.thaneships) or bool(char.city_faction) or is_guildmaster(char, gamedata)


def has_camp(char: Character) -> bool:
    return bool(char.camp)


def can_make_camp(char: Character, gamedata: GameData, loc_id: str) -> bool:
    """須為領主/首領,且當地可紮營:野外紮營 或 佔領已清空地城。"""
    if not is_warlord(char, gamedata):
        return False
    loc = gamedata.location(loc_id)
    if loc["type"] == "wilderness":
        return True
    return loc["type"] == "dungeon" and loc.get("dungeon") in char.cleared_dungeons


def make_camp(char: Character, loc_id: str) -> None:
    char.camp = loc_id


def recruit_soldiers(char: Character, n: int) -> int:
    """在營地招募 n 名士兵(夾士兵上限與金幣、扣金)。回傳實際招募數。"""
    if not has_camp(char):
        return 0
    n = max(0, min(n, MAX_SOLDIERS - char.soldiers, char.gold // SOLDIER_COST))
    char.gold -= n * SOLDIER_COST
    char.soldiers += n
    return n


def fielded_soldiers(char: Character) -> int:
    """攻城時實際上場的士兵數(其餘戰力以大軍壓境體現)。"""
    return min(char.soldiers, FIELD_CAP)


def army_soften(char: Character) -> int:
    """大軍壓境削守軍量(以士兵總數計)。"""
    return char.soldiers * ARMY_SOFTEN_PER
