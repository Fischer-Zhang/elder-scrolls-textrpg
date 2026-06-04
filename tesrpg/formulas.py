"""集中所有數值規則:屬性基準、衍生數值、技能成長門檻、升級加成。

把公式放一處,平衡時只改這裡。所有函式都是純函式(不改傳入物件)。
"""

from __future__ import annotations

# --- 基準 ---------------------------------------------------------------
BASE_ATTRIBUTE = 40          # 所有屬性的起始基準(再加種族/星座修正)
ATTRIBUTE_CAP = 100
SKILL_CAP = 100
SKILL_BASE = 5               # 角色創建時每個技能的底值
SKILL_MAJOR_BONUS = 20       # 主修技能額外起始值(→ 25)
SKILL_SPEC_BONUS = 5         # 與職業專精同類的技能額外起始值

# --- 升級(混合 Skyrim 式:技能成長餵養等級 XP 池) ---------------------
LEVELUP_XP_BASE = 12         # Lv1→2 所需等級經驗
LEVELUP_XP_STEP = 1          # 每級遞增的門檻(平緩曲線,避免高等過於肝)
MAJOR_SKILL_XP_MULT = 1.5    # 主修技能升點給的等級經驗倍率(保留職業認同)
LEVELUP_ATTRIBUTE_POINTS = 4  # 每級可自由分配的屬性點(無倍率)
LEVELUP_RESOURCE_GAIN = {"health": 14, "magicka": 12, "fatigue": 12}  # 升級三選一各自加量

ATTRIBUTES = [
    "strength", "intelligence", "willpower", "agility",
    "speed", "endurance", "personality", "luck",
]

ATTRIBUTE_NAMES = {
    "strength": "力量", "intelligence": "智力", "willpower": "意志",
    "agility": "敏捷", "speed": "速度", "endurance": "耐力",
    "personality": "魅力", "luck": "幸運",
}

SPEC_NAMES = {"combat": "戰鬥", "magic": "魔法", "stealth": "潛行"}


# --- 衍生數值 -----------------------------------------------------------
def base_max_health(endurance: int) -> int:
    """創建時的生命上限基底(耐力×2)。之後生命只由升級時的「生命」選擇成長,
    不再隨耐力逐級長 —— 消除「早衝耐力」的時機陷阱。"""
    return endurance * 2


def max_magicka(intelligence: int, magicka_bonus: int) -> int:
    """魔力上限 = 智力×2 + 種族/星座固定加成。"""
    return intelligence * 2 + magicka_bonus


def max_fatigue(strength: int, willpower: int, agility: int, endurance: int) -> int:
    return strength + willpower + agility + endurance


def max_encumbrance(strength: int) -> int:
    """負重上限(物品重量總和不可超過)。"""
    return strength * 5


# --- 技能成長 (learn-by-doing) -----------------------------------------
def skill_threshold(skill_level: int) -> float:
    """從 skill_level 升到 skill_level+1 所需累積的 xp。

    隨技能等級線性遞增 → 越高越難練,呈現上古卷軸的成長曲線。
    skill 0→1 需 1.0;skill 50→51 需 5.0;skill 99→100 需 ~8.92。
    """
    return 1.0 + skill_level * 0.08


# --- 等級 XP 池 ---------------------------------------------------------
def levelup_xp_for_skillup(skill_level: int, is_major: bool) -> float:
    """一次技能 +1 餵給「等級 XP 池」的量。所有技能都計入(無 major-only 套利);
    主修技能 ×MAJOR_SKILL_XP_MULT 以保留職業認同。"""
    return MAJOR_SKILL_XP_MULT if is_major else 1.0


def levelup_xp_threshold(level: int) -> float:
    """從 level 升到 level+1 所需的等級經驗(隨等級遞增)。"""
    return LEVELUP_XP_BASE + (level - 1) * LEVELUP_XP_STEP


# --- 戰鬥 ---------------------------------------------------------------
WEAPON_SKILL_IDS = ["blade", "blunt", "marksman", "hand_to_hand"]
ARMOR_SKILL_IDS = ["heavy_armor", "light_armor"]

ATTACK_FATIGUE_COST = 6      # 每次近戰攻擊消耗體力
BLOCK_FATIGUE_COST = 4
COMBAT_HIT_XP = 0.5          # 成功命中 → 武器技能 xp
COMBAT_ARMOR_XP = 0.4        # 被擊中 → 護甲技能 xp
COMBAT_BLOCK_XP = 0.5        # 成功格擋 → 格擋技能 xp
COMBAT_SNEAK_XP = 0.6        # 開場偷襲命中 → 潛行技能 xp(讓 sneak 也能戰鬥中成長)
COMBAT_DODGE_XP = 0.4        # 成功閃避(敵人攻擊落空)→ 雜技技能 xp

SNEAK_ATTACK_SCALE = 0.03    # 偷襲傷害倍率係數
SNEAK_ATTACK_HIT_FLOOR = 0.90  # 偷襲命中率下限(伏擊不察之敵,極少落空)
DODGE_EVASION_SCALE = 0.0025   # 雜技閃避係數(acrobatics 100 → 敵人命中 −0.25)


def sneak_attack_multiplier(sneak_skill: int) -> float:
    """開場偷襲的傷害倍率:潛行越高,致命一擊越狠(sneak 0→×1.0、50→×2.5、100→×4.0)。"""
    return 1.0 + sneak_skill * SNEAK_ATTACK_SCALE


def dodge_evasion(acrobatics_skill: int) -> float:
    """雜技帶來的閃避量(直接從敵人命中率扣除):acrobatics 40→0.10、100→0.25。"""
    return acrobatics_skill * DODGE_EVASION_SCALE


ATHLETICS_TRAVEL_SCALE = 0.004   # 運動旅行加速係數
ATHLETICS_TRAVEL_XP = 0.5        # 每次旅行 → 運動 xp(讓運動靠移動成長)


def athletics_travel_factor(athletics_skill: int) -> float:
    """運動帶來的旅行耗時倍率(越高越快):運動 0→×1.0、100→×0.6(最多省 40%)。"""
    return max(0.5, 1.0 - athletics_skill * ATHLETICS_TRAVEL_SCALE)


ATHLETICS_FATIGUE_SCALE = 0.004  # 運動降低戰鬥體力消耗的係數


def fatigue_cost_factor(athletics_skill: int) -> float:
    """運動降低戰鬥(攻擊/格擋)體力消耗:運動 0→×1.0、100→×0.6(最多省 40%)。"""
    return max(0.6, 1.0 - athletics_skill * ATHLETICS_FATIGUE_SCALE)


def hit_chance(atk_skill: int, atk_agility: int, def_agility: int,
               attacker_fatigue_ratio: float, defender_blocking: bool = False,
               defender_evasion: float = 0.0) -> float:
    """命中率。武器技能為主、敏捷差為輔、低體力受罰、對方格擋/閃避更難打中。"""
    chance = 0.50 + (atk_skill - 25) * 0.006        # 技能 25→0.5、75→0.8、100→0.95
    chance += (atk_agility - def_agility) * 0.004
    chance -= (1.0 - max(0.0, min(1.0, attacker_fatigue_ratio))) * 0.25
    if defender_blocking:
        chance -= 0.15
    chance -= defender_evasion                       # 雜技閃避(僅玩家防守時)
    return max(0.05, min(0.95, chance))


def attack_damage(weapon_damage: float, weapon_skill: int, strength: int,
                  roll: float, defender_blocking: bool = False) -> float:
    """傷害 = 武器基礎 × 技能倍率 × 力量倍率 × 隨機;對方格擋大幅減傷。

    roll 由呼叫端用 rng.roll(0.85, 1.15) 取得(保持本函式為純函式、可測)。
    """
    skill_mult = 0.5 + weapon_skill / 100.0         # 0.5 .. 1.5
    str_mult = 0.75 + strength / 160.0              # 40→1.0、100→1.375
    dmg = weapon_damage * skill_mult * str_mult * roll
    if defender_blocking:
        dmg *= 0.4
    return dmg


def damage_after_armor(damage: float, armor_rating: int, armor_pen: float = 0.0) -> float:
    """護甲減傷:遞減收益,最多擋 85%,至少造成 1 點。

    armor_pen(0..1):破甲 —— 視同對方護甲先被無視掉這個比例(鈍器專長)。
    """
    eff = armor_rating * max(0.0, 1.0 - armor_pen)
    reduction = min(0.85, eff / (eff + 100.0))
    return max(1.0, damage * (1.0 - reduction))


# --- 武器流派(B:讓武器選擇是 build 而非純傷害數字)--------------------
WEAPON_SPEED_DEFAULT = 1.0
_ARCHETYPE_ARMOR_PEN = {"blunt": 0.30}          # 鈍器破甲:無視 30% 護甲
_ARCHETYPE_SNEAK_BONUS = {"dagger": 1.6, "bow": 1.3}   # 潛襲倍率額外加成(刺客/獵手)


def weapon_speed_hit(speed: float) -> float:
    """武器速度對命中的修正:快武器多揮幾下→更易命中,慢武器較難。"""
    return (speed - WEAPON_SPEED_DEFAULT) * 0.10


def weapon_attack_fatigue_factor(speed: float) -> float:
    """一擊的體力消耗倍率:慢重武器更耗、輕快武器更省(2 - speed,夾限)。"""
    return max(0.5, min(1.6, 2.0 - speed))


def archetype_armor_pen(archetype: str | None) -> float:
    return _ARCHETYPE_ARMOR_PEN.get(archetype, 0.0)


def archetype_sneak_bonus(archetype: str | None) -> float:
    return _ARCHETYPE_SNEAK_BONUS.get(archetype, 1.0)


def player_armor_rating(heavy_armor_skill: int, light_armor_skill: int) -> int:
    """M2:玩家尚無護甲物品,以護甲技能近似「受訓練的承受與卸力」。"""
    return max(heavy_armor_skill, light_armor_skill) // 4


def flee_chance(player_speed: int, player_agility: int, foe_speed: int) -> float:
    chance = 0.45 + (player_speed + player_agility * 0.5 - foe_speed) * 0.006
    return max(0.10, min(0.90, chance))


# --- 抗性與元素 ---------------------------------------------------------
MAGIC_ELEMENTS = ("fire", "frost", "shock")   # 受「magic」總抗性影響的學派元素


def resist_multiplier(resist: dict, element: str) -> float:
    """元素傷害的傷害係數。

    元素抗性 + (若為魔法元素)通用 magic 抗性 → 越高傷害越低;
    負值代表弱點(傷害放大)。範圍夾限在 [0, 2.0](可完全免疫到雙倍弱點)。
    """
    r = (resist or {}).get(element, 0)
    if element in MAGIC_ELEMENTS:
        r += (resist or {}).get("magic", 0)
    return max(0.0, min(2.0, 1.0 - r / 100.0))
