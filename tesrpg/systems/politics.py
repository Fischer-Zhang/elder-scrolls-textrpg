"""城戰(Phase 3+4):政治立場 + 選邊 + 攻城戰。城為單位 —— 各城主自有立場。

立場種子在 rulers.json 的 `stance`(imperial 復辟 / independent 獨立 / neutral 觀望),依各城主考據
指派(刻意跨省混合)。玩家擁護一個「大義」(allegiance)後:同立場=盟、對立=可攻、中立=觀望。
攻城=連場 `combat` 群戰波次(其間無休整);攻下 → 該城歸屬翻轉為你的大義。

動態戰況掛 Character(存檔):city_faction(歸屬翻轉)、garrison_current(駐軍),首次存取時由
rulers 種子懶初始化。加城/改立場純改 rulers.json;調攻城規模/獎勵改本檔常數。
"""

from __future__ import annotations

import math

from tesrpg.gamedata import GameData
from tesrpg.models import Character

CAUSES = {"imperial": "帝國復辟派", "independent": "獨立同盟"}   # 玩家可擁護的兩大義
STANCE_LABEL = {"imperial": "帝國復辟派", "independent": "獨立同盟", "neutral": "中立觀望"}
SIEGE_SOLDIER = "city_guard"   # 攻城守軍兵種(複用既有衛兵)
SIEGE_FAME = 30                # 攻下一城的聲望獎勵
# 波間「重整」:每破一波,趁隙退後包紮喘息(非全補)→ 讓連場攻城可承受而非送死。
SIEGE_REGROUP_HEALTH = 0.35
SIEGE_REGROUP_FATIGUE = 0.6
SIEGE_REGROUP_MAGICKA = 0.3


def stance_label(stance: str | None) -> str:
    return STANCE_LABEL.get(stance, stance or "—")


def cause_name(cause: str) -> str:
    return CAUSES.get(cause, cause)


def base_stance(gamedata: GameData, loc_id: str) -> str | None:
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("stance", "neutral") if ruler else None


def base_garrison(gamedata: GameData, loc_id: str) -> int:
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("garrison", 0) if ruler else 0


def faction_of(char: Character, gamedata: GameData, loc_id: str) -> str | None:
    """該城現時歸屬(攻城翻轉後以 city_faction 為準,否則回種子立場)。無領主回 None。"""
    if loc_id in char.city_faction:
        return char.city_faction[loc_id]
    return base_stance(gamedata, loc_id)


def garrison_of(char: Character, gamedata: GameData, loc_id: str) -> int:
    if loc_id in char.garrison_current:
        return char.garrison_current[loc_id]
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("garrison", 0) if ruler else 0


def relationship(char: Character, gamedata: GameData, loc_id: str) -> str:
    """相對玩家 allegiance:none(無領主)/unaligned(未選邊)/ally/neutral/enemy。"""
    fac = faction_of(char, gamedata, loc_id)
    if fac is None:
        return "none"
    if not char.allegiance:
        return "unaligned"
    if fac == char.allegiance:
        return "ally"
    if fac == "neutral":
        return "neutral"
    return "enemy"


REL_LABEL = {"ally": "盟友", "enemy": "敵對", "neutral": "中立", "unaligned": "(你尚未選邊)"}


def pledge(char: Character, cause: str) -> None:
    char.allegiance = cause


def can_siege(char: Character, gamedata: GameData, loc_id: str) -> bool:
    """唯有已選邊、且該城為對立大義者可攻(中立/盟友不可攻)。"""
    return relationship(char, gamedata, loc_id) == "enemy"


def siege_params(base: int) -> tuple[int, int]:
    """依城池「基準駐軍」定出攻城波數與每波守軍數 —— 兩者皆隨駐軍**單調遞增**,
    故守軍越多的城越難攻(帝都 400 是終局王冠)。回傳 (waves, guards_per_wave)。"""
    waves = max(2, min(5, round(base / 90)))
    guards = max(2, min(6, 1 + base // 90))
    return waves, guards


def siege_wave(remaining: int, base: int) -> dict:
    """這一波的編成。攻城是消耗戰:每破一波就**永久**削減守軍(deplete_garrison),
    清掉的波次不重生 —— 杜絕「清波→逃跑→重刷戰利/技能」,也讓玩家可分多次圍攻(進度保留)。
    削到 0 即破城;最後一波(削完守軍者)守將親臨。回傳 {guards, boss, strength}。"""
    waves, guards = siege_params(base)
    chunk = math.ceil(base / waves)
    return {"guards": guards, "boss": remaining <= chunk, "strength": min(chunk, remaining)}


def deplete_garrison(char: Character, gamedata: GameData, loc_id: str, amount: int) -> None:
    """破一波 → 永久削減該城現存駐軍(進度持久化;清掉的守軍不再重生)。"""
    char.garrison_current[loc_id] = max(0, garrison_of(char, gamedata, loc_id) - amount)


def regroup(char: Character) -> None:
    """破一波後趁隙喘息:部分回復生命/體力/魔力(非全補)。"""
    char.health = min(char.max_health, char.health + char.max_health * SIEGE_REGROUP_HEALTH)
    char.fatigue = min(char.max_fatigue, char.fatigue + char.max_fatigue * SIEGE_REGROUP_FATIGUE)
    char.magicka = min(char.max_magicka, char.magicka + char.max_magicka * SIEGE_REGROUP_MAGICKA)


def conquer(char: Character, gamedata: GameData, loc_id: str) -> None:
    """攻下:該城歸屬翻轉為你的大義,並由你方重新駐軍。"""
    char.city_faction[loc_id] = char.allegiance
    ruler = gamedata.ruler_at(loc_id) or {}
    char.garrison_current[loc_id] = ruler.get("garrison", 100)


def held_cities(char: Character, gamedata: GameData) -> list[str]:
    """目前歸屬玩家大義的城(供結算/戰情圖);未選邊則空。"""
    if not char.allegiance:
        return []
    return [lid for lid in gamedata.rulers
            if faction_of(char, gamedata, lid) == char.allegiance]
