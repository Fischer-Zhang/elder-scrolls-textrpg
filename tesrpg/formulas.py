"""集中所有數值規則:屬性基準、衍生數值、技能成長門檻、升級加成。

把公式放一處,平衡時只改這裡。所有函式都是純函式(不改傳入物件)。
"""

from __future__ import annotations

# --- 基準 ---------------------------------------------------------------
BASE_ATTRIBUTE = 40          # 所有屬性的起始基準(再加種族/星座修正)
ATTRIBUTE_CAP = 100
SKILL_CAP = 100
TRAINER_CAP = 75             # 一般訓練師付費指點的上限;招牌城「宗師」對其招牌技可破此線(見 systems/world.trainer_cap)
                            # 76–SKILL_CAP 一律靠 learn-by-doing 或宗師,杜絕「就近一站買滿」(城鎮服務專精化,handoff R29)
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

# 每屬性的機制作用(供升級分配/角色卡顯示,讓玩家知道每點的意義)
ATTRIBUTE_FUNCTION = {
    "strength": "近戰傷害·負重·體力",
    "intelligence": "魔力上限",
    "willpower": "施法續航(回魔)·抗恐懼麻痺·體力",
    "agility": "命中/閃避·體力",
    "speed": "先攻·逃跑·旅行加速",
    "endurance": "生命上限·體力",
    "personality": "說服/好感/喝退",
    "luck": "戰利豐厚·撬鎖/逃跑/事件運氣",
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


# --- 意志 willpower:施法續航 + 精神韌性 / 幸運 luck:天命 -----------------
# 補屬性功能缺口:讓「治理魔法卻無施法價值」的意志、「近乎死屬性」的幸運名實相符。
# 鐵律:所有係數在屬性 = BASE_ATTRIBUTE(40)時回中性值(=改前行為)→ base-40 角色與
# sim_assassin 零位移;唯有投資到 40 以上才生效。刻意不碰玩家近戰傷害 → 與偷襲紅線解耦。
MAGICKA_REGEN_COMBAT_PER = 15     # 每 N 點意志(>40)→ 戰鬥每回合 +1 回魔
MAGICKA_REGEN_COMBAT_CAP = 5
MAGICKA_REGEN_REST_PER = 0.0167   # 休息回魔倍率:每點意志(>40)
MAGICKA_REGEN_REST_CAP = 2.5
MIND_RESIST_PER = 0.0083          # 抗恐懼/麻痺機率:每點意志(>40)
MIND_RESIST_CAP = 0.75
LUCK_LOOT_PER = 0.005             # 戰利掉落/金幣倍率:每點幸運(>40)
LUCK_LOOT_CAP = 1.5
LUCK_FORTUNE_PER = 0.0017         # 命運加性(撬鎖/逃跑/事件):每點幸運(>40)
LUCK_FORTUNE_CAP = 0.20


# --- 中庸職業功能性區分:弓手散兵武技(瞄準射/牽制射)常數 ---------------
# (戰法師 imbue / 治療師援護 / 騎士 empower 的數值走 spells.json 資料;此處僅弓手武技=程式)
AIMED_SHOT_HIT = 0.15          # 瞄準射:命中加成
AIMED_SHOT_PEN = 0.25          # 瞄準射:額外破甲
AIMED_SHOT_POWER = 0.40       # 瞄準射:強擊補傷(不吃偷襲倍率、受 solo 夾限,守紅線)
CRIPPLING_WEAKEN = 0.40       # 牽制射:目標攻擊削弱比例
CRIPPLING_TURNS = 3


def magicka_regen_combat(willpower: int) -> int:
    """戰鬥每回合玩家被動回魔(意志=施法續航):≤40 → 0;隨意志增,夾 CAP。
    僅影響「能放幾發」非單發威力 → 與偷襲紅線解耦。"""
    return max(0, min(MAGICKA_REGEN_COMBAT_CAP, (willpower - BASE_ATTRIBUTE) // MAGICKA_REGEN_COMBAT_PER))


def magicka_regen_rest_factor(willpower: int) -> float:
    """休息回魔速率倍率(意志):40 → 1.0(中性),投資越多回藍越快。"""
    return min(MAGICKA_REGEN_REST_CAP, 1.0 + max(0, willpower - BASE_ATTRIBUTE) * MAGICKA_REGEN_REST_PER)


def mind_resist_chance(willpower: int) -> float:
    """抵抗恐懼/麻痺的機率(意志=精神韌性):40 → 0(中性),投資越多越能抗控。"""
    return max(0.0, min(MIND_RESIST_CAP, (willpower - BASE_ATTRIBUTE) * MIND_RESIST_PER))


def luck_loot_factor(luck: int) -> float:
    """戰利掉落機率/金幣倍率(幸運=天命):40 → 1.0(中性),投資越多戰利越豐。"""
    return max(1.0, min(LUCK_LOOT_CAP, 1.0 + max(0, luck - BASE_ATTRIBUTE) * LUCK_LOOT_PER))


def luck_fortune(luck: int) -> float:
    """命運加性微調(撬鎖/逃跑/事件擲骰):40 → 0(中性),投資越多時來運轉。"""
    return max(0.0, min(LUCK_FORTUNE_CAP, max(0, luck - BASE_ATTRIBUTE) * LUCK_FORTUNE_PER))


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
VANISH_FATIGUE_COST = 18     # 隱遁翻滾耗體力(高;連續隱遁會耗竭 → 後續攻擊命中下降)
# 武器命中觸發附魔(weapon_status)
WEAPON_VAMPIRIC_FRACTION = 0.30   # 吸血:回血 = 造成傷害 × 此比例(夾實傷、夾血上限;每擊觸發故不可大)。武器可用 enchant.magnitude(%)覆寫(如悲傷之刃 50)。
WEAPON_PARALYZE_PROC = 0.10       # 武器麻痺觸發機率(1 回合、不重複套;solo BOSS 免疫 → 反鎖王作弊)
# 武器命中效果擴充(R29-附魔深化):DoT(burn/chill/jolt)+ 元素 rider、命中吸取、充能(soul_trap/paralyze)
WEAPON_DOT_FACTOR = 1.2           # 元素 DoT 每回合傷害係數(低於即時 enchw 的 3.0,因保證多回合)
WEAPON_DOT_TURNS = 3              # 元素 DoT 持續回合(命中刷新取 max)
WEAPON_CHILL_WEAKEN = 0.15        # 霜 DoT「凍緩」rider:敵輸出 ×(1-此值),2 回合
WEAPON_JOLT_MAGICKA = 8           # 電 DoT「感電」rider:每觸發扣目標魔力
WEAPON_JOLT_STAGGER = 0.20        # 電 DoT「感電」rider:踉蹌機率
WEAPON_ABSORB_FACTOR = 1.5        # 命中吸取(生命/魔力/體力)每擊回攻擊者量的係數
WEAPON_ABSORB_SOLO_FACTOR = 0.5   # 吸取生命對 solo BOSS 受夾(杜絕無限回血泵;比照偷襲夾限精神)
CHARGE_PER_SOUL = 5              # 充能電池容量 = round(soul × 此 × (0.6+祕術/100));soul_trap/paralyze 用,魂石等級=電池大小
WEAPON_SOULTRAP_TURNS = 3        # 命中擒魂掛在目標的 soul_trap 效果回合
DOT_STACK_CAP = 3                # 同元素 DoT 在玩家身上的疊加上限(防多次被擊疊毒暴斃;攻擊側不限,法術/塗毒照疊)


def berserk_factor(attacker, magnitude) -> float:
    """嗜血怒擊(維蘇拉德 enchant.kind=berserk):依攻方已損生命比例放大物理傷害,封頂 magnitude%。
    🔴 滿血 → ×1.0(開場偷襲/全血一擊不放大);乘在物理 dmg、於 solo 偷襲/衝鋒夾限之前 → solo boss 仍受夾。"""
    mh = getattr(attacker, "max_health", 0) or 1
    missing = max(0.0, 1.0 - getattr(attacker, "health", mh) / mh)
    return 1.0 + missing * (max(0, magnitude) / 100.0)


def vampiric_fraction(ench: dict | None) -> float:
    """武器吸血回血比例:enchant.magnitude(%)優先(如悲傷之刃 50 → 0.5),缺省回 WEAPON_VAMPIRIC_FRACTION(30%)。"""
    if ench and ench.get("magnitude"):
        return ench["magnitude"] / 100.0
    return WEAPON_VAMPIRIC_FRACTION
COMBAT_HIT_XP = 0.5          # 成功命中 → 武器技能 xp
COMBAT_ARMOR_XP = 0.4        # 被擊中 → 護甲技能 xp
COMBAT_BLOCK_XP = 0.5        # 成功格擋 → 格擋技能 xp
COMBAT_SNEAK_XP = 0.6        # 開場偷襲命中 → 潛行技能 xp(讓 sneak 也能戰鬥中成長)
COMBAT_DODGE_XP = 0.4        # 成功閃避(敵人攻擊落空)→ 雜技技能 xp
DUNGEON_REVEAL_SCOUT_XP = 0.12  # 地城每探明一格(踏入/偵查揭示)→ 偵查技能 xp(被動探索成長,低於 COMBAT 系)

SNEAK_ATTACK_SCALE = 0.03    # 偷襲傷害倍率係數
SNEAK_ATTACK_HIT_FLOOR = 0.90  # 偷襲命中率下限(伏擊不察之敵,極少落空)
DODGE_EVASION_SCALE = 0.0025   # 雜技閃避係數(acrobatics 100 → 敵人命中 −0.25)

# --- 暗殺殘響(偷襲命中但沒秒殺 → alpha strike 仍留下實質後果)------------
STAGGER_HIT_PENALTY = 0.30   # 陣腳大亂的單位攻擊命中減成(命中-0.30,給刺客喘息窗)
SLOW_HIT_PENALTY = 0.15      # 遲緩毒(R31):中毒遲緩單位命中減成(較踉蹌輕,因另降先攻)
SNEAK_BLEED_BASE = 2         # 撕裂傷每回合基礎傷害
SNEAK_BLEED_PER_SNEAK = 25   # 每 25 點潛行 → 撕裂傷 +1
SNEAK_BLEED_PER_ALCHEMY = 40  # 每 40 點煉金 → 撕裂傷 +1(刺客主修,learn-by-doing)
SNEAK_BLEED_TURNS = 3        # 撕裂傷持續回合
# 各武器流派偷襲未殺時的殘響:匕首=踉蹌+撕裂、弓=踉蹌(射倒拖節奏);劍/鈍器無(守住刺客身份)
_ARCHETYPE_SNEAK_AFTERMATH = {"dagger": {"stagger": True, "bleed": True},
                              "bow": {"stagger": True}}


def sneak_aftermath(archetype: str | None) -> dict:
    """該武器流派『偷襲未殺』時施加的殘響效果(無則空 dict)。"""
    return _ARCHETYPE_SNEAK_AFTERMATH.get(archetype, {})


def sneak_bleed_magnitude(sneak_skill: int, alchemy_skill: int) -> int:
    """撕裂傷每回合傷害,隨潛行與煉金成長(技巧驅動而非無腦數值)。"""
    return (SNEAK_BLEED_BASE + sneak_skill // SNEAK_BLEED_PER_SNEAK
            + alchemy_skill // SNEAK_BLEED_PER_ALCHEMY)


def sneak_attack_multiplier(sneak_skill: int) -> float:
    """開場偷襲的傷害倍率:潛行越高,致命一擊越狠(sneak 0→×1.0、50→×2.5、100→×4.0)。"""
    return 1.0 + sneak_skill * SNEAK_ATTACK_SCALE


NIGHT_MOTHER_SNEAK_PER_RANK = 0.03   # 黑暗兄弟會每階對偷襲倍率的加成(夜母祝福)
# solo BOSS 反一刀:對 `solo` 目標,單次偷襲傷害夾在其生命上限的此比例 → 開場一擊絕不致死。
# apex(玻璃雙持+聆聽者+淬鍊+影刃)仍可靠隱遁循環無傷清 boss,但須多刀(守 approved plan
# 「solo boss 仍存活」;精英/小遭遇不受影響,apex 照常秒殺)。調此值或夜母/影刃常數務必重跑 sim_assassin.py。
SOLO_SNEAK_DAMAGE_CAP_RATIO = 0.40

# 坐騎「戰備衝鋒」對 solo BOSS 的反一刀:衝鋒(尤其長槍×高倍率)對 `solo` 目標的單次傷害
# 夾在其生命上限此比例 → 開場衝鋒絕不秒王。鏡像偷襲夾,但**獨立**(衝鋒不走 sneak_mult)。
# 衝鋒只在野外旅途/探索遭遇、且僅開場第一回合可用。調此值或衝鋒倍率務必重跑 sim_assassin.py。
MOUNTED_CHARGE_DAMAGE_CAP_RATIO = 0.45


def night_mother_sneak_bonus(db_rank: int) -> float:
    """夜母祝福:黑暗兄弟會階級越高,潛殺越致命(乘進偷襲倍率)。

    每階 +0.03(聆聽者滿階 ×1.18;新血階 0 不加成)。**solo BOSS 的單擊不死由
    SOLO_SNEAK_DAMAGE_CAP_RATIO 夾(combat.resolve_attack)強制保證**,非靠此倍率溫和;
    精英(非 solo)可被 apex 一擊秒(刻意)。非會員(rank<0)回 1.0。
    """
    return 1.0 + max(0, db_rank) * NIGHT_MOTHER_SNEAK_PER_RANK


# 偷襲倍率的「穿戴重量折扣」:鏗鏘重甲就算偷到、爆發也打折(輕甲對重甲的潛行優勢之二)。
# 門檻 18(方案 B):總重 ≤18 完全不打折 → 法袍/皮甲/玻璃/龍鱗等輕甲全段保護(W≤18),
# 只有重甲(W>18)才隨重量遞減,夾在 [0.45,1.0]。改此值踩偷襲倍率紅線 → 必跑 sim_assassin.py。
# ⚠ 與命中端各自獨立:armor_relief(無聲披掛)只抵命中端噪音,**不抵此倍率折扣**(見 R07/R25)。
SNEAK_MULT_WEIGHT_FLOOR = 18      # 總重 ≤ 此值偷襲倍率不打折
SNEAK_MULT_WEIGHT_PER = 0.012     # 每超出一點重量 → 倍率 ×(1−此值)
SNEAK_MULT_WEIGHT_MIN = 0.45      # 倍率折扣下限(再重也保留 45% 偷襲爆發)


def armor_sneak_mult_factor(armor_weight: float) -> float:
    """穿戴護甲總重 → 偷襲傷害倍率折扣係數(W≤18=×1.0;重甲遞減,夾 [0.45,1.0])。"""
    return min(1.0, max(SNEAK_MULT_WEIGHT_MIN,
                        1.0 - (armor_weight - SNEAK_MULT_WEIGHT_FLOOR) * SNEAK_MULT_WEIGHT_PER))


def dodge_evasion(acrobatics_skill: int) -> float:
    """雜技帶來的閃避量(直接從敵人命中率扣除):acrobatics 40→0.10、100→0.25。"""
    return acrobatics_skill * DODGE_EVASION_SCALE


ATHLETICS_TRAVEL_SCALE = 0.004   # 運動旅行加速係數
ATHLETICS_TRAVEL_XP = 0.5        # 每次旅行 → 運動 xp(讓運動靠移動成長)


def athletics_travel_factor(athletics_skill: int) -> float:
    """運動帶來的旅行耗時倍率(越高越快):運動 0→×1.0、100→×0.6(最多省 40%)。"""
    return max(0.5, 1.0 - athletics_skill * ATHLETICS_TRAVEL_SCALE)


# --- 房產:最佳休息「精神飽滿」增益(learn-by-doing 加速;不寫 base、不碰戰鬥)----------
WELL_RESTED_HOURS = 24            # 在家最佳休息後,精神飽滿持續的遊戲小時
WELL_RESTED_XP_MULT = 1.25        # 精神飽滿期間技能 xp 倍率(progression.use_skill 讀 char.well_rested)


ATHLETICS_FATIGUE_SCALE = 0.004  # 運動降低戰鬥體力消耗的係數


def fatigue_cost_factor(athletics_skill: int) -> float:
    """運動降低戰鬥(攻擊/格擋/施法)體力消耗:運動 0→×1.0、100→×0.6(最多省 40%)。"""
    return max(0.6, 1.0 - athletics_skill * ATHLETICS_FATIGUE_SCALE)


# --- 施法體力(法師三系資源對稱:施法也耗體力、力竭則法效降)---------------
CAST_FATIGUE_BASE = 3              # 固定底耗(低於近戰 6:便宜法術不該比揮劍更累)
CAST_FATIGUE_PER_MAGICKA = 0.15   # 隨有效魔耗線性 → 大法術/過載更累
CAST_FATIGUE_POWER_PENALTY = 0.25 # 力竭法效折減(鏡像近戰命中 −0.25:滿體×1.0、空體×0.75)


def cast_fatigue_power_factor(fatigue_ratio: float) -> float:
    """低體力削弱法效(damage/heal/shield/summon 一致):滿體×1.0、空體×0.75
    (近戰低體力降命中、法術不擲命中,故改削威力 → 跨系統對稱)。"""
    return 1.0 - (1.0 - max(0.0, min(1.0, fatigue_ratio))) * CAST_FATIGUE_POWER_PENALTY


BLOCK_HIT_PENALTY = 0.15        # 對方格擋時攻擊命中率的基礎扣減(里程碑「盾陣」會加深)


def hit_chance(atk_skill: int, atk_agility: int, def_agility: int,
               attacker_fatigue_ratio: float, defender_blocking: bool = False,
               defender_evasion: float = 0.0, block_penalty: float = BLOCK_HIT_PENALTY) -> float:
    """命中率。武器技能為主、敏捷差為輔、低體力受罰、對方格擋/閃避更難打中。

    block_penalty 由呼叫端帶入(預設 BLOCK_HIT_PENALTY;里程碑「盾陣」會傳更深的值)。
    """
    chance = 0.50 + (atk_skill - 25) * 0.006        # 技能 25→0.5、75→0.8、100→0.95
    chance += (atk_agility - def_agility) * 0.004
    chance -= (1.0 - max(0.0, min(1.0, attacker_fatigue_ratio))) * 0.25
    if defender_blocking:
        chance -= block_penalty
    chance -= defender_evasion                       # 雜技閃避(僅玩家防守時)
    return max(0.05, min(0.95, chance))


def attack_damage(weapon_damage: float, weapon_skill: int, strength: int,
                  roll: float, block_factor: float = 1.0) -> float:
    """傷害 = 武器基礎 × 技能倍率 × 力量倍率 × 隨機 × 格擋減傷倍率。

    roll 由呼叫端用 rng.roll(0.85, 1.15) 取得(保持本函式為純函式、可測)。
    block_factor 由呼叫端用 block_damage_factor(防守方格擋技能) 算出(無格擋=1.0)。
    """
    skill_mult = 0.5 + weapon_skill / 100.0         # 0.5 .. 1.5
    str_mult = 0.75 + strength / 160.0              # 40→1.0、100→1.375
    return weapon_damage * skill_mult * str_mult * roll * block_factor


# --- 格擋(隨格擋技能成長:消除「格擋等級空轉」)----------------------------
BLOCK_DAMAGE_FACTOR_LOW = 0.9    # 格擋技能 0   → 傷害僅降到 90%(生手幾乎擋不住)
BLOCK_DAMAGE_FACTOR_HIGH = 0.4   # 格擋技能 100 → 傷害降到 40%(原本寫死的值,現為高技能上限)


def block_damage_factor(block_skill: int) -> float:
    """格擋成功時的傷害倍率:隨格擋技能由 0.9(低)線性降到 0.4(高)。

    過去格擋減傷是寫死 ×0.4 與技能無關 → 格擋等級空轉(技能健檢唯一未過項)。
    現在練格擋會讓格擋真的更有用,與雜技閃避/護甲值隨等級成長一致。
    """
    t = max(0, min(100, block_skill)) / 100.0
    return BLOCK_DAMAGE_FACTOR_LOW + (BLOCK_DAMAGE_FACTOR_HIGH - BLOCK_DAMAGE_FACTOR_LOW) * t


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


OFFHAND_DAMAGE_FACTOR = 0.6   # 雙持時副手匕首傷害折入每一擊的比例(大幅增傷,代價=不能格擋)


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


# --- 隱遁再襲(戰鬥中重新潛入陰影:成功則跳過本回合挨打 + 重置偷襲)---------
VANISH_MIN_SNEAK = 25         # 隱遁解鎖門檻(=潛行 25 里程碑「隱遁之術」;此常數為無 gamedata 時的 fallback,須與該節點門檻一致)
MAX_VANISHES_PER_BATTLE = 3   # 每場最多嘗試隱遁次數(硬上限:隱遁是有限脫離手段,非無限風箏)
RESTEALTH_BASE = 0.55
RESTEALTH_SKILL_SCALE = 0.0035    # (sneak + acrobatics×0.5) × 此係數
RESTEALTH_CROWD_PENALTY = 0.18    # 每多一個存活敵人,隱遁更難
RESTEALTH_REUSE_PENALTY = 0.25    # 同場每用過一次,下次隱遁更難(防無限風箏;里程碑「連環踏影」可免)
RESTEALTH_HORDE_PENALTY = 0.40    # >3 敵:每超出一個額外大減(刺客 apex 的群體規模反制骨幹)


def restealth_chance(sneak: int, acrobatics: int, n_alive: int, used: int,
                     relentless: bool = False, floor: float = 0.0) -> float:
    """隱遁成功率:吃潛行+雜技,敵人越多越難、同場重複用遞減、**>3 敵大減**。夾限 [max(0.05,floor), 0.90]。

    relentless(里程碑「連環踏影」)→ 免除同場重複使用遞減 —— **但僅在面對敵群(>1)時**;
    對『單一強敵(1 對 1)』仍逐次遞減(敵會死咬盯防 → 防 apex 對 solo boss 無限風箏抹平風險)。
    floor(里程碑「踏影/翻滾脫離」)→ 保底下限。"""
    waive_reuse = relentless and n_alive > 1    # 連環踏影只在敵群中免遞減;一對一仍被盯防、再三遁形漸難
    chance = (RESTEALTH_BASE + (sneak + acrobatics * 0.5) * RESTEALTH_SKILL_SCALE
              - max(0, n_alive - 1) * RESTEALTH_CROWD_PENALTY
              - max(0, n_alive - 3) * RESTEALTH_HORDE_PENALTY            # >3 敵:大減(反制 apex 群戰風箏)
              - (0.0 if waive_reuse else max(0, used) * RESTEALTH_REUSE_PENALTY))
    return max(floor, max(0.05, min(0.90, chance)))


# --- 戰前潛行撤退(偵查到不利 → 體面退場;吃潛行+速度,群越大越難)----------
STEALTH_RETREAT_BASE = 0.55
RETREAT_GROUP_PENALTY = 0.10      # 每多一個敵人,撤退更難


def stealth_retreat_chance(sneak: int, speed: int, foe_speed: int, group_size: int) -> float:
    """潛行撤退成功率:吃潛行與速度差,敵群越大越難。夾限 [0.10, 0.92](保留失敗率)。"""
    chance = (STEALTH_RETREAT_BASE + sneak * 0.004 + (speed - foe_speed) * 0.004
              - max(0, group_size - 1) * RETREAT_GROUP_PENALTY)
    return max(0.10, min(0.92, chance))


# --- 入場潛行檢定(接戰時:能否搶到開場偷襲先機)----------------------------
STEALTH_APPROACH_BASE = 0.55
STEALTH_APPROACH_SNEAK = 0.0045       # 每點潛行
STEALTH_APPROACH_PERCEPT = 0.003      # 敵方最高敏捷(警覺)扣減
STEALTH_APPROACH_CROWD = 0.08         # 每多一個敵人(更多眼睛)
STEALTH_APPROACH_HORDE = 0.30         # >3 敵:每超出一個額外大減(群體規模反制 apex)
STEALTH_APPROACH_NIGHT = 0.10         # 夜間(黑暗掩護)
STEALTH_APPROACH_SCOUT = 0.25         # 先成功偵查 → 知道動線(B:偵查解博弈)
STEALTH_APPROACH_SURPRISE = 0.45      # 被伏擊(C:受害者難以反偷襲加害者)
# E:護甲噪音 —— 改依「實際穿戴總重」連續計(鏗鏘重甲難潛、輕量法袍幾乎無礙;里程碑「無聲披掛」relief 可抵消)。
# 取代舊的二元 weight_class 扁平懲罰:同為輕甲,法袍(W5)幾乎無罰、龍鱗(W18)中等;重甲隨重量遞增到封頂。
STEALTH_WEIGHT_FLOOR = 4           # 穿戴總重 ≤ 此值幾乎無噪音(近裸/輕法袍)
STEALTH_WEIGHT_PENALTY_PER = 0.017  # 每超出 floor 一點重量 → 入場潛行機率 −此值
STEALTH_WEIGHT_PENALTY_CAP = 0.75   # 命中端重量懲罰上限(再重也封頂)


def stealth_weight_penalty(armor_weight: float) -> float:
    """穿戴護甲總重 → 入場潛行的命中懲罰(連續;封頂 0.75)。供 stealth_approach_chance 用。"""
    return min(STEALTH_WEIGHT_PENALTY_CAP,
               max(0.0, (armor_weight - STEALTH_WEIGHT_FLOOR) * STEALTH_WEIGHT_PENALTY_PER))


def stealth_approach_chance(sneak: int, foe_agility: int, group_size: int,
                            armor_weight: float, night: bool = False,
                            scouted: bool = False, surprise: bool = False,
                            approach_bonus: float = 0.0, armor_relief: float = 0.0) -> float:
    """接戰時搶到開場偷襲的機率。吃潛行/敵警覺/敵數/**護甲總重噪音**/夜間/偵查/是否被伏擊/**>3 敵大減**。
    夾限 [0.05, 0.97](高潛行可靠、但永不保證;重甲莽夫幾乎偷不到;大群幾乎偷不到)。"""
    armor_pen = stealth_weight_penalty(armor_weight) * (1 - armor_relief)
    chance = (STEALTH_APPROACH_BASE + sneak * STEALTH_APPROACH_SNEAK
              - foe_agility * STEALTH_APPROACH_PERCEPT
              - max(0, group_size - 1) * STEALTH_APPROACH_CROWD
              - max(0, group_size - 3) * STEALTH_APPROACH_HORDE         # >3 敵:大減
              - armor_pen + approach_bonus)
    if night:
        chance += STEALTH_APPROACH_NIGHT
    if scouted:
        chance += STEALTH_APPROACH_SCOUT
    if surprise:
        chance -= STEALTH_APPROACH_SURPRISE
    return max(0.05, min(0.97, chance))


# --- 偵查掙得的開戰前備戰空間(scout → 準備動作數)--------------------------
PREP_SCOUT_T1 = 20        # 偵查達此 → 備戰 1 個動作(對齊 _scout_report 第一道資訊牆)
PREP_SCOUT_T2 = 50        # → 2 個動作(且解鎖「召喚」這類高價值準備)
PREP_SCOUT_T3 = 75        # → 3 個動作(封頂)
PREP_SUMMON_MIN_SCOUT = PREP_SCOUT_T2   # 備戰階段施放召喚的技能門檻(鎖高 scout)


def prep_budget(scout_skill: int) -> int:
    """搶得先機(潛近成功)時,偵查技能換得的開戰前備戰動作數(0/1/2/3)。

    分級門檻沿用偵查揭露的 20/50/75,讓技能高低有質的差異;封頂 3 防無限前載。
    只給「時序主動權」(先做幾個準備),不縮放數值、不送永久強度。"""
    if scout_skill >= PREP_SCOUT_T3:
        return 3
    if scout_skill >= PREP_SCOUT_T2:
        return 2
    if scout_skill >= PREP_SCOUT_T1:
        return 1
    return 0


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
