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
    origin_id: str | None = None,
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

    # --- 開局背景(不一樣的人生):在標準起始之上做資料驅動覆寫 ----------
    apply_origin(gamedata, char, origin_id)

    # --- 衍生數值 --------------------------------------------------------
    # base_max_health 只看耐力(開局不動屬性);recompute 收尾,讓開局換上的護甲/飾品
    # fortify 流進有效上限,並補滿三資源。
    char.base_max_health = formulas.base_max_health(char.attr("endurance"))
    stats.recompute_max_resources(char, gamedata, restore_full=True)
    return char


def apply_origin(gamedata: GameData, char: Character, origin_id: str | None) -> None:
    """把一個「開局背景」的資料覆寫疊到已建好的標準角色上(就地修改)。

    只給「處境」差異(地點/金幣/裝備/公會/賞金/同伴),不給屬性/技能點——
    刻意維持「練什麼成長什麼」的成長軸,避免重蹈 min-max。所有欄位皆可選,
    留空即沿用標準起始;未知 id 視為「布魯瑪新移民」(無覆寫)以防毀損存檔。
    """
    char.origin = origin_id or "newcomer"
    odef = gamedata.origins.get(char.origin)
    if not odef:
        char.origin = "newcomer"
        return

    if "location" in odef:
        char.location_id = odef["location"]
        char.visited_locations = [char.location_id]
    if "gold" in odef:
        char.gold = int(odef["gold"])

    # 背包:在標準起始包之上「追加」(不取代)
    for entry in odef.get("items", []):
        item_id, qty = entry[0], (entry[1] if len(entry) > 1 else 1)
        inventory.add_item(char, item_id, qty)

    # 武器:加進背包並裝備(取代依技能配發的起始武器,含法杖)
    weapon_id = odef.get("weapon")
    if weapon_id:
        inventory.add_item(char, weapon_id, 1)
        inventory.equip_weapon(char, gamedata, weapon_id)

    # 護甲/飾品:加進背包並穿戴(recompute 由 build_character 收尾統一處理)
    for item_id in odef.get("equip", []):
        inventory.add_item(char, item_id, 1)
        kind = gamedata.item(item_id).get("kind")
        if kind == "armor":
            inventory.equip_armor(char, gamedata, item_id)
        elif kind == "jewelry":
            inventory.equip_jewelry(char, gamedata, item_id)

    # 額外法術(疊加,不重覆)
    for spell_id in odef.get("spells", []):
        if spell_id not in char.spells:
            char.spells.append(spell_id)

    # 公會起始會籍:rank 為階級索引(繞過 join_skill 門檻;作者需自行確保不與賞金/對立矛盾)
    for fid, rank in odef.get("faction", {}).items():
        char.factions[fid] = int(rank)

    # 起始賞金:key 為行省顯示名(對齊 crime/world 的 province),value 為賞金額
    for province, amount in odef.get("bounty", {}).items():
        char.bounties[province] = char.bounties.get(province, 0) + int(amount)

    # 起始同伴:傭兵 template id(忽略未知者,向後相容)
    for cid in odef.get("companions", []):
        if cid in gamedata.companions and cid not in char.companions:
            char.companions.append(cid)

    # 開局即吸血鬼(夜之裔):只標記身分;階級加成/進食日由 vampirism.update 在
    # 進入主迴圈第一回合初始化(build_character 此時沒有 state/時間)。
    if odef.get("vampire"):
        char.is_vampire = True


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
