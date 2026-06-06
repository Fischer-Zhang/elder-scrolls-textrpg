"""一生傳奇總結與評分。

在角色死亡或隱退時,把這一生的軌跡(等級、最高技能、足跡、公會、任務、
聲望、財富、在世年數)結算成一份總結與「傳奇分數」,給重玩動力。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.systems import brotherhood, mastery, politics, vampirism

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
        fdef = gamedata.factions.get(fid)          # 防禦化:毀損/已移除的公會 id → 跳過(別讓結算 KeyError)
        if not fdef:
            continue
        ranks = fdef["ranks"]
        clamped = min(rank, len(ranks) - 1)        # 夾限,避免毀損存檔讓分數爆量
        faction_lines.append((fdef["name"], ranks[clamped]))
        faction_points += (clamped + 1) * 60

    tops = top_skills(char, gamedata)
    top_skill_sum = sum(lvl for _, lvl in tops)
    total_kills = sum(char.kill_counts.values())
    total_locations = len(gamedata.world["locations"])
    masteries = [e["name"] for e in mastery.unlocked(char, gamedata)]
    # 具名地標:只計仍合法的 loc_id(防毀損存檔殘留已移除地標)
    landmarks_found = sum(1 for lid in char.discovered_landmarks if lid in gamedata.landmarks)
    total_landmarks = len(gamedata.landmarks)

    # 城戰 / 招兵的功業(此前在結算裡零承認):親手攻下的城、武士冊封、麾下軍隊
    cities_held = len(politics.held_tax_cities(char, gamedata))
    thanes = len(char.thaneships)

    score = (
        char.level * 120
        + top_skill_sum * 2
        + len(char.completed_quests) * 50
        + faction_points
        + len(char.cleared_dungeons) * 90
        + len(char.visited_locations) * 20
        + landmarks_found * 30        # 探索者:每尋得一處具名地標
        + total_kills * 4
        + char.fame * 6
        + int(char.gold * 0.1)
        + years * 30
        + len(masteries) * 40        # 技能精通的印記:每解鎖一個里程碑
        + cities_held * 200          # 征服功業:每座親手攻下且仍在手的城
        + thanes * 80                # 武士冊封:每座受封的城
        + char.soldiers * 3          # 麾下常備軍
    )

    return {
        "ending": ending,
        "name": char.name,
        "race": gamedata.races[char.race]["name"],
        "sex": "男" if char.sex == "male" else "女",
        "birthsign": gamedata.birthsigns[char.birthsign]["name"],
        "class": "自訂" if char.class_id == "custom" else gamedata.classes[char.class_id]["name"],
        # 開局背景:舊存檔/已移除的 id → None(結算畫面省略此行)
        "origin": gamedata.origins.get(char.origin, {}).get("name"),
        "masteries": masteries,                       # 解鎖的技能里程碑(身份印記)
        "condition": vampirism.legacy_label(char),   # 吸血鬼身分(否則 None)
        "dark_deeds": brotherhood.legacy_label(char, gamedata),   # 黑暗兄弟會/謀殺事蹟(否則 None)
        "dominion": dominion_label(char, gamedata, cities_held, thanes),  # 領地/統帥功業(否則 None)
        "level": char.level,
        "years": years, "days": days,
        "top_skills": tops,
        "factions": faction_lines,
        "quests_completed": len(char.completed_quests),
        "dungeons_cleared": len(char.cleared_dungeons),
        "places_visited": len(char.visited_locations),
        "total_locations": total_locations,
        "landmarks_found": landmarks_found,
        "total_landmarks": total_landmarks,
        "total_kills": total_kills,
        "fame": char.fame, "infamy": char.infamy,
        "gold": char.gold,
        "bounty": sum(char.bounties.values()),
        "playstyle": playstyle(char, gamedata),
        "score": score,
        "title": title_for(score),
        "seed": state.rng.seed,
    }


_OWN_REALM_TITLES = [(10, "再造一統的新王"), (6, "問鼎天下的雄主"),
                     (3, "裂土封疆的霸主"), (1, "割據一方的梟雄")]


def own_realm_title(cities_held: int) -> str:
    """自立稱雄者依持城數的開國稱號。"""
    for thr, title in _OWN_REALM_TITLES:
        if cities_held >= thr:
            return title
    return "舉旗自立者"


def dominion_label(char, gamedata: GameData, cities_held: int, thanes: int) -> str | None:
    """城戰/招兵的功業總結(攻下的城 / 武士 / 大義 / 常備軍);無則 None(結算省略此行)。"""
    if not (cities_held or thanes or char.soldiers or char.allegiance):
        return None
    parts = []
    if char.allegiance == "own":
        parts.append(own_realm_title(cities_held))        # 自立稱雄:依持城數的開國稱號
    elif char.allegiance:
        parts.append(f"擁護{politics.cause_name(char.allegiance)}")
    if cities_held:
        parts.append(f"據有 {cities_held} 城")
    if thanes:
        parts.append(f"受封 {thanes} 地武士")
    if char.soldiers:
        parts.append(f"麾下 {char.soldiers} 兵")
    return " · ".join(parts)


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
