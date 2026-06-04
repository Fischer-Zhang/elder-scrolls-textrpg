"""一生傳奇總結與評分。

在角色死亡或隱退時,把這一生的軌跡(等級、最高技能、足跡、公會、任務、
聲望、財富、在世年數)結算成一份總結與「傳奇分數」,給重玩動力。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData

DAYS_PER_YEAR = 360   # 12 月 × 30 天


def survived(state) -> tuple[int, int]:
    """回傳在世(年, 天)。"""
    hours = max(0, state.time.absolute_hours() - state.start_time.absolute_hours())
    days = hours // 24
    return days // DAYS_PER_YEAR, days % DAYS_PER_YEAR


def top_skills(char, gamedata: GameData, n: int = 5) -> list[tuple[str, int]]:
    ranked = sorted(char.skills.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [(gamedata.skill_name(sid), lvl) for sid, lvl in ranked]


def _spec_totals(char, gamedata: GameData) -> dict[str, int]:
    totals = {"combat": 0, "magic": 0, "stealth": 0}
    for sid, lvl in char.skills.items():
        totals[gamedata.skills[sid]["spec"]] += lvl
    return totals


def playstyle(char, gamedata: GameData) -> str:
    t = _spec_totals(char, gamedata)
    hi = max(t, key=t.get)
    spread = max(t.values()) - min(t.values())
    if spread < 30:
        return "通曉百藝的全才冒險者"
    return {"combat": "劍與盾的沙場武者", "magic": "駕馭奧術的法師",
            "stealth": "潛行暗影的盜賊"}[hi]


def compute(state, gamedata: GameData, ending: str = "death") -> dict:
    char = state.player
    years, days = survived(state)

    faction_lines = []
    faction_points = 0
    for fid, rank in char.factions.items():
        ranks = gamedata.factions[fid]["ranks"]
        clamped = min(rank, len(ranks) - 1)        # 夾限,避免毀損存檔讓分數爆量
        faction_lines.append((gamedata.factions[fid]["name"], ranks[clamped]))
        faction_points += (clamped + 1) * 60

    tops = top_skills(char, gamedata)
    top_skill_sum = sum(lvl for _, lvl in tops)
    total_kills = sum(char.kill_counts.values())
    total_locations = len(gamedata.world["locations"])

    score = (
        char.level * 120
        + top_skill_sum * 2
        + len(char.completed_quests) * 50
        + faction_points
        + len(char.cleared_dungeons) * 90
        + len(char.visited_locations) * 20
        + total_kills * 4
        + char.fame * 6
        + int(char.gold * 0.1)
        + years * 30
    )

    return {
        "ending": ending,
        "name": char.name,
        "race": gamedata.races[char.race]["name"],
        "sex": "男" if char.sex == "male" else "女",
        "birthsign": gamedata.birthsigns[char.birthsign]["name"],
        "class": "自訂" if char.class_id == "custom" else gamedata.classes[char.class_id]["name"],
        "level": char.level,
        "years": years, "days": days,
        "top_skills": tops,
        "factions": faction_lines,
        "quests_completed": len(char.completed_quests),
        "dungeons_cleared": len(char.cleared_dungeons),
        "places_visited": len(char.visited_locations),
        "total_locations": total_locations,
        "total_kills": total_kills,
        "fame": char.fame, "infamy": char.infamy,
        "gold": char.gold,
        "bounty": sum(char.bounties.values()),
        "playstyle": playstyle(char, gamedata),
        "score": score,
        "title": title_for(score),
        "seed": state.rng.seed,
    }


def title_for(score: int) -> str:
    if score >= 6000:
        return "載入史冊的不朽者"
    if score >= 3500:
        return "威震 Tamriel 的傳奇"
    if score >= 1800:
        return "聞名一方的英傑"
    if score >= 700:
        return "嶄露頭角的冒險者"
    return "默默無聞的旅人"
