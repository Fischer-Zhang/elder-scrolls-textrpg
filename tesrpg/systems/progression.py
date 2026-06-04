"""learn-by-doing 技能成長與升級 —— 本作的核心系統。

流程:
  使用技能 → 累積該技能 xp → 滿門檻則 +1 點
         → 記錄該技能主導屬性的「本級升點數」(供升級時換算屬性加成)
         → 若是主修技能,計入 level_progress
  level_progress 達 10 → 可升級 → 玩家挑 3 個屬性 → 依本級升點數決定加成幅度
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats


def use_skill(char: Character, gamedata: GameData, skill_id: str, xp: float) -> list[dict]:
    """對某技能灌注 xp,結算升點。回傳事件列表(供 UI 呈現)。

    事件型別:
      {"type": "skill_up", "skill": id, "level": 新等級}
      {"type": "level_ready"}                      # 本次首度達到可升級
    """
    events: list[dict] = []
    if skill_id not in char.skills:
        return events

    could_level_before = char.can_level_up()
    char.skill_xp[skill_id] = char.skill_xp.get(skill_id, 0.0) + xp

    # 可能一次灌注跨過多個門檻
    while char.skills[skill_id] < formulas.SKILL_CAP:
        need = formulas.skill_threshold(char.skills[skill_id])
        if char.skill_xp[skill_id] < need:
            break
        char.skill_xp[skill_id] -= need
        char.skills[skill_id] += 1
        _on_skill_increase(char, gamedata, skill_id, events)

    if char.skills[skill_id] >= formulas.SKILL_CAP:
        char.skill_xp[skill_id] = 0.0  # 滿級不再累積

    if char.can_level_up() and not could_level_before:
        events.append({"type": "level_ready"})
    return events


def _on_skill_increase(char: Character, gamedata: GameData, skill_id: str, events: list[dict]) -> None:
    gov_attr = gamedata.skill_attr(skill_id)
    char.level_skillups[gov_attr] = char.level_skillups.get(gov_attr, 0) + 1
    if char.is_major_skill(skill_id):
        char.level_progress += 1
    events.append({"type": "skill_up", "skill": skill_id, "level": char.skills[skill_id]})


def preview_levelup(char: Character) -> dict[str, int]:
    """預覽:若現在升級,各屬性可獲得的加成幅度 (+1..+5)。

    供升級畫面顯示,讓玩家看到「練得勤的屬性漲得多」。
    """
    return {
        attr: formulas.attribute_bonus_from_skillups(char.level_skillups.get(attr, 0))
        for attr in formulas.ATTRIBUTES
    }


def apply_level_up(char: Character, gamedata: GameData, chosen_attributes: list[str]) -> dict:
    """套用升級:提升所選屬性、提高生命上限、回滿資源。

    回傳結算摘要供 UI 呈現。chosen_attributes 最多取前 3 個有效屬性。
    """
    if not char.can_level_up():
        raise ValueError("尚未滿足升級條件")

    bonuses = preview_levelup(char)
    chosen = []
    for attr in chosen_attributes:
        if attr in formulas.ATTRIBUTES and attr not in chosen:
            chosen.append(attr)
        if len(chosen) >= formulas.LEVELUP_ATTRIBUTES_CHOSEN:
            break

    attr_gains: dict[str, int] = {}
    for attr in chosen:
        gain = bonuses[attr]
        new_val = min(formulas.ATTRIBUTE_CAP, char.attr(attr) + gain)
        applied = new_val - char.attr(attr)
        char.attributes[attr] = new_val
        if applied:
            attr_gains[attr] = applied

    char.level += 1
    hp_gain = formulas.health_gain_on_levelup(char.attr("endurance"))
    char.max_health += hp_gain

    char.level_progress -= formulas.LEVELUP_MAJOR_SKILLUPS  # 保留溢出
    char.level_skillups = {}

    stats.recompute_max_resources(char, restore_full=True)  # 升級回滿三資源

    return {
        "level": char.level,
        "attr_gains": attr_gains,
        "hp_gain": hp_gain,
        "can_level_again": char.can_level_up(),
    }
