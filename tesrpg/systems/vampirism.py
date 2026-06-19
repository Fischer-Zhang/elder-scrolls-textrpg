"""吸血熱 / 吸血鬼化(Vampirism)—— 一條「力量 ↔ 詛咒」的動態天平。

循環(仿 TES):被吸血鬼咬 → 染上「吸血熱」(疾病,受種族疾病抗性削弱)→ 潛伏
3 日未治 → **轉化**為吸血鬼 → 之後**越久不進食階級越高**:屬性/技能加成與吸血
能力越強,但**陽光灼傷、火焰弱點、世人越排斥**也越重。**進食**重置回最低階(最弱
但能融入社會)。

設計與本作哲學的調和:這是**真權衡**而非免費強度 —— 階級高=戰力強但晝伏難行、
寸步難商;進食=回歸正常但放棄高階加成。階級加成走獨立的 `vampire_*_bonus` 層
(與裝備加成同模式:`attr()/skill()` 疊加、**成長/夾限只用 base_***)。

狀態存在 Character 上(持久、進存檔),不同於戰鬥內 `active_effects`。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats

# --- 時程 ---------------------------------------------------------------
INCUBATION_DAYS = 3        # 吸血熱潛伏幾日後轉化
STAGE_DAYS = 2             # 每隔幾日未進食升一階
MAX_STAGE = 3             # 階級 0..3(進食後 0,饑餓至 3)
SHUN_STAGE = 2            # 達此階級世人拒絕往來(需進食才能經商)
SUN_STAGE_MIN = 1        # 達此階級起,白天在戶外會被陽光灼傷

STAGE_NAMES = ["初擁", "饑渴", "嗜血", "夜主"]   # 階級 0..3 的稱呼

# --- 階級加成(每階線性疊加;階級 0 不給屬性/技能加成,只保有疾病免疫)-----
STAGE_ATTR = {"strength": 5, "speed": 5, "willpower": 5}   # ×階級
STAGE_SKILL = {"sneak": 5, "illusion": 5}                  # ×階級

# --- 陽光與進食 ---------------------------------------------------------
SUN_DMG_PER_HOUR_PER_STAGE = 1.5    # 每「日照小時 × 階級」的灼傷
FEED_HEAL = 50                       # 進食回復的生命
FEED_BOUNTY = 60                     # 進食被撞見時的賞金
SUN_HOUR_START, SUN_HOUR_END = 8, 18   # 烈日時段 [8,18)

# --- R50 識破圍捕 / 月相連動 --------------------------------------------
SHUN_DETECT_BASE = 0.25         # 高階(shunned)吸血鬼在城被識破→衛兵圍捕的基礎機率(每次抵城擲一次)
SHUN_DETECT_PER_STAGE = 0.15    # 每超過 SHUN_STAGE 一階 +識破機率
FULL_MOON_DETECT_BONUS = 0.15   # 滿月亮夜曝獠牙 → 更易被識破
DETECT_CHANCE_CAP = 0.70        # 識破機率上限(進食壓階即可規避,非必中)
NEW_MOON_STEALTH_BONUS = 0.10   # 新月暗夜助獵 → 進食更難被撞見


def _today(state) -> int:
    return state.time.absolute_hours() // 24


def _is_sun_hour(hour: int) -> bool:
    return SUN_HOUR_START <= (hour % 24) < SUN_HOUR_END


# ======================================================================
# 狀態查詢
# ======================================================================
def is_vampire(char: Character) -> bool:
    return getattr(char, "is_vampire", False)


def is_infected(char: Character) -> bool:
    """已染吸血熱、潛伏中(尚未轉化)。"""
    return (not is_vampire(char)) and getattr(char, "vampire_infected_day", -1) >= 0


def susceptible(char: Character) -> bool:
    """還能被感染(非吸血鬼、也尚未潛伏、且非狼人 → 狼人疾病免疫,與吸血鬼互斥)。"""
    return ((not is_vampire(char)) and not is_infected(char)
            and not getattr(char, "is_werewolf", False))


def stage(char: Character, state) -> int:
    """目前階級:進食後 0,每 STAGE_DAYS 日未進食 +1,夾限 MAX_STAGE。"""
    if not is_vampire(char):
        return 0
    fed = char.vampire_fed_day
    if fed <= 0:        # 尚未初始化(開局即吸血鬼/異常存檔)→ 視為剛進食
        return 0
    return max(0, min(MAX_STAGE, (_today(state) - fed) // STAGE_DAYS))


def is_shunned(char: Character, state) -> bool:
    return is_vampire(char) and stage(char, state) >= SHUN_STAGE


def detection_chance(char: Character, state) -> float:
    """R50:高階吸血鬼在城被世人識破 → 引衛兵圍捕的機率(每次抵城/城內擲)。
    非 shunned(階級 < SHUN_STAGE)= 0;階級越高、滿月越易被識破。進食壓階即可規避。"""
    if not is_shunned(char, state):
        return 0.0
    from tesrpg.systems import moons
    p = SHUN_DETECT_BASE + SHUN_DETECT_PER_STAGE * (stage(char, state) - SHUN_STAGE)
    if moons.is_full_moon(state):
        p += FULL_MOON_DETECT_BONUS
    return min(DETECT_CHANCE_CAP, p)


# ======================================================================
# 階級加成(獨立層,與裝備加成同模式)
# ======================================================================
def _bonuses(stg: int) -> tuple[dict, dict, dict]:
    attr = {k: v * stg for k, v in STAGE_ATTR.items() if v * stg}
    skill = {k: v * stg for k, v in STAGE_SKILL.items() if v * stg}
    # 抗性:各階皆免疫疾病;耐霜隨階成長、抗火隨階轉為弱點(負值=傷害放大)
    resist = {"disease": 100}
    if stg:
        resist["frost"] = 10 * stg
        resist["fire"] = -10 * stg
    return attr, skill, resist


def apply_to_character(char: Character, state, gamedata: GameData) -> None:
    """重算吸血鬼階級加成寫入 `vampire_*` 層,並重算衍生資源(吃進有效上限)。

    非吸血鬼則清空所有吸血鬼加成。必在轉化/進食/階級變動後呼叫。
    """
    if not is_vampire(char):
        char.vampire_attr_bonus = {}
        char.vampire_skill_bonus = {}
        char.vampire_resist = {}
        char.vampire_stage = 0
    else:
        stg = stage(char, state)
        a, s, r = _bonuses(stg)
        char.vampire_attr_bonus = a
        char.vampire_skill_bonus = s
        char.vampire_resist = r
        char.vampire_stage = stg
    # attr() 已含 vampire_attr_bonus → 重算讓 力量/意志 加成流進 max_fatigue 等
    stats.recompute_max_resources(char, gamedata)


# ======================================================================
# 感染 → 轉化(每圈 update 驅動)
# ======================================================================
def infect(char: Character, state) -> bool:
    """染上吸血熱(開始潛伏)。已是吸血鬼或已潛伏 → 無效,回傳 False。"""
    if not susceptible(char):
        return False
    char.vampire_infected_day = _today(state)
    return True


def cure(char: Character, gamedata: GameData) -> None:
    """解除吸血鬼化(D 治療任務的儀式收尾):清空所有狀態、卸除階級加成、重算資源。

    治癒後玩家恢復凡人之身(出生星座之力也隨之回歸);日後仍可再被感染。
    """
    char.is_vampire = False
    char.vampire_infected_day = -1
    char.vampire_fed_day = 0
    apply_to_character(char, None, gamedata)   # 非吸血鬼分支:清空 vampire_* 並 recompute


def update(state, gamedata: GameData) -> list[dict]:
    """每個主迴圈回合呼叫:處理潛伏→轉化、初始化 fed_day、同步階級加成。

    回傳事件清單 [{"kind": "turn"|"stage", ...}] 供 UI 呈現(無事件則空)。
    """
    char = state.player
    events: list[dict] = []

    # 潛伏期滿 → 轉化
    if is_infected(char) and _today(state) - char.vampire_infected_day >= INCUBATION_DAYS:
        char.is_vampire = True
        char.vampire_infected_day = -1
        char.vampire_fed_day = _today(state)   # 轉化當下視同剛進食(階級 0)
        apply_to_character(char, state, gamedata)
        events.append({"kind": "turn"})
        return events

    if is_vampire(char):
        if char.vampire_fed_day <= 0:          # 開局即吸血鬼 / 異常存檔:初始化進食日
            char.vampire_fed_day = _today(state)
        new_stage = stage(char, state)
        # 加成尚未套用(剛轉化/開局即吸血鬼:各階皆應有疾病免疫)→ 視為待更新
        stale = "disease" not in char.vampire_resist
        if new_stage != char.vampire_stage or stale:
            rising = new_stage > char.vampire_stage
            apply_to_character(char, state, gamedata)
            if new_stage != 0 and rising:      # 階級 0、或非上升(進食回落)不另外播報
                events.append({"kind": "stage", "stage": new_stage, "rising": True})
    return events


# ======================================================================
# 進食(重置階級)與陽光灼傷
# ======================================================================
def feed(state, gamedata: GameData, safe: bool = False) -> dict:
    """吸食活人 → 階級歸 0、回復生命;可能被撞見(白天機率高)→ 賞金 + 惡名。

    R51:`safe=True`(巢穴安心進食)→ 同類供血、不被撞見(略過 caught 擲與賞金)。
    回傳 {"ok", "healed", "caught", "bounty", "province"}。
    """
    char = state.player
    if not is_vampire(char):
        return {"ok": False}
    from tesrpg.systems import crime   # 區域 import 避免循環

    char.vampire_fed_day = _today(state)
    apply_to_character(char, state, gamedata)        # 階級→0,重算上限
    before = char.health
    char.health = min(char.max_health, char.health + FEED_HEAL)
    healed = int(char.health - before)

    province = crime.province_of(char, gamedata)
    if safe:                                         # R51:巢穴同類供血 → 必不被撞見
        caught = False
    else:
        hour = state.time.hour
        caught_chance = 0.45 if _is_sun_hour(hour) else 0.12
        from tesrpg.systems import moons
        if moons.is_new_moon(state):                 # R50:新月暗夜助獵 → 更難被撞見
            caught_chance = max(0.0, caught_chance - NEW_MOON_STEALTH_BONUS)
        caught = state.rng.chance(caught_chance)
        if caught:
            crime.add_bounty(char, province, FEED_BOUNTY)
            char.infamy += 1
    state.time.advance(1)
    return {"ok": True, "healed": healed, "caught": caught,
            "bounty": FEED_BOUNTY, "province": province}


def expose_to_sun(state, gamedata: GameData, hours: int) -> int:
    """戶外活動 `hours` 小時的陽光灼傷(階級越高越痛);夾限保留至少 1 點生命
    (避免在選單數值運算中暴斃,死亡只應來自戰鬥)。回傳實際灼傷量。"""
    char = state.player
    if not is_vampire(char):
        return 0
    stg = stage(char, state)
    if stg < SUN_STAGE_MIN:
        return 0
    from tesrpg.systems import world   # 區域 import 避免循環
    if world.current_location(char, gamedata).get("type") == "dungeon":
        return 0                                  # 地城/洞窟遮蔽日光
    end = state.time.absolute_hours()
    sun_hours = sum(1 for h in range(end - hours, end) if _is_sun_hour(h))
    if sun_hours <= 0:
        return 0
    dmg = sun_hours * stg * SUN_DMG_PER_HOUR_PER_STAGE
    dmg = min(dmg, max(0.0, char.health - 1))     # 不在選單中曬死
    char.health -= dmg
    return int(round(dmg))


# ======================================================================
# 一生傳奇:吸血鬼身分標籤
# ======================================================================
def legacy_label(char: Character) -> str | None:
    if is_vampire(char):
        return f"{STAGE_NAMES[min(MAX_STAGE, max(0, char.vampire_stage))]}吸血鬼"
    if is_infected(char):
        return "染上吸血熱"
    return None
