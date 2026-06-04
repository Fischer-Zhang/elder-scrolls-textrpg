"""角色創建:把種族/星座/職業的選擇組裝成一個完整的 Character。

build_character 是純函式(可測試);互動式選單在 ui/ 與 main.py。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import inventory, stats

STARTING_GOLD = 50


def _resolve_class(gamedata: GameData, class_id: str, custom_class: dict | None):
    """回傳 (specialization, favored_attributes, major_skills)。"""
    if class_id == "custom":
        if not custom_class:
            raise ValueError("自訂職業需提供 custom_class")
        return (
            custom_class["specialization"],
            list(custom_class["favored_attributes"]),
            list(custom_class["major_skills"]),
        )
    cls = gamedata.classes[class_id]
    return cls["spec"], list(cls["favored_attributes"]), list(cls["major_skills"])


def build_character(
    gamedata: GameData,
    *,
    name: str,
    sex: str,
    race: str,
    birthsign: str,
    class_id: str,
    custom_class: dict | None = None,
    rng: RNG | None = None,
    is_player: bool = True,
) -> Character:
    race_def = gamedata.races[race]
    sign_def = gamedata.birthsigns[birthsign]
    spec, favored, majors = _resolve_class(gamedata, class_id, custom_class)

    # --- 屬性:基準 + 種族 + 星座 ---------------------------------------
    attributes: dict[str, int] = {}
    for attr in formulas.ATTRIBUTES:
        val = formulas.BASE_ATTRIBUTE
        val += race_def.get("attr_mods", {}).get(attr, 0)
        val += sign_def.get("attr_mods", {}).get(attr, 0)
        attributes[attr] = max(1, min(formulas.ATTRIBUTE_CAP, val))

    magicka_bonus = race_def.get("magicka_bonus", 0) + sign_def.get("magicka_bonus", 0)

    # --- 技能:底值 + 主修 + 專精 + 種族加成 ----------------------------
    skills: dict[str, int] = {}
    for sid, sdef in gamedata.skills.items():
        val = formulas.SKILL_BASE
        if sid in majors:
            val += formulas.SKILL_MAJOR_BONUS
        if sdef["spec"] == spec:
            val += formulas.SKILL_SPEC_BONUS
        val += race_def.get("skill_bonuses", {}).get(sid, 0)
        skills[sid] = max(0, min(formulas.SKILL_CAP, val))

    char = Character(
        id="player" if is_player else name,
        name=name, race=race, sex=sex, birthsign=birthsign, class_id=class_id,
        specialization=spec, favored_attributes=favored, major_skills=majors,
        attributes=attributes,
        skills=skills,
        skill_xp={sid: 0.0 for sid in skills},
        level=1, level_progress=0, level_skillups={},
        magicka_bonus=magicka_bonus,
        gold=STARTING_GOLD,
        is_player=is_player,
    )

    char.location_id = gamedata.world["start_location"]
    char.visited_locations = [char.location_id]
    char.weapon = _starting_weapon(gamedata, skills)
    char.spells = _starting_spells(majors)

    # --- 起始背包 --------------------------------------------------------
    if char.weapon != "fists":
        inventory.add_item(char, char.weapon, 1)
    inventory.add_item(char, "minor_healing_potion", 2)
    inventory.add_item(char, "wheat", 2)
    inventory.add_item(char, "blue_mountain_flower", 2)

    # --- 衍生數值 --------------------------------------------------------
    char.base_max_health = formulas.base_max_health(char.attr("endurance"))
    stats.recompute_max_resources(char, gamedata, restore_full=True)
    return char


# 各武器技能 → 預設起始武器
_WEAPON_FOR_SKILL = {
    "blade": "iron_sword",
    "blunt": "iron_mace",
    "marksman": "hunting_bow",
    "hand_to_hand": "fists",
}


def _starting_weapon(gamedata: GameData, skills: dict[str, int]) -> str:
    """依角色最擅長的武器技能,配發一把起始武器。"""
    best = max(formulas.WEAPON_SKILL_IDS, key=lambda s: skills.get(s, 0))
    return _WEAPON_FOR_SKILL.get(best, "iron_dagger")


# 主修某魔法學派 → 起手該學派的一道入門法術;人人至少會次級治療
_SPELL_FOR_SCHOOL = {
    "destruction": "flames", "restoration": "minor_heal", "alteration": "oakflesh",
    "illusion": "fear", "conjuration": "conjure_familiar", "mysticism": "soul_trap",
}


def _starting_spells(majors: list[str]) -> list[str]:
    spells = []
    for school, spell in _SPELL_FOR_SCHOOL.items():
        if school in majors:
            spells.append(spell)
    if "minor_heal" not in spells:
        spells.append("minor_heal")
    return spells


def random_name(gamedata: GameData, race: str, sex: str, rng: RNG) -> str:
    pool = gamedata.names.get(race, {}).get(sex)
    if not pool:
        return "無名者"
    return rng.choice(pool)
