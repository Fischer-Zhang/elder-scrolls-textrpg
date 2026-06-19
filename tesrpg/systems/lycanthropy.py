"""狼人化 / 獸形(Lycanthropy / Beast Form)—— 吸血鬼的對位機制。

設計反差(刻意與吸血鬼互補,不是複製):
  - 吸血鬼 = 被動的飢渴階級詛咒(永遠在身、陽光/社交懲罰)。
  - 狼人   = **主動的限時「獸形」變身**:主動觸發 → 短時間化為猛獸(爪擊 + 巨量生命/體力/速度),
            但**脫去裝備、不能施法/用物/格擋**;吞噬獵物可續時,變回人形有力竭代價。

循環(仿 TES 戰友團):被狼人咬染「狼人熱」→ 潛伏轉化 → 之後每日可「獸化」一次(走 powers 槽,
複用星座之力管線);獸形中以獸爪戰鬥,擊殺獵物續時;持續時間(`beast_form_until` 絕對小時)過後
自動變回(game_loop 的 update 驅動,鏡像吸血鬼/斯庫瑪的時間鉤子)。

與本作哲學的調和:獸形是**真權衡**而非免費強度 —— 放棄整套裝備/附魔/淬鍊/法術,換取原始野獸之力。
獸形加成走獨立的 `werewolf_*` 層(與裝備/吸血鬼/斯庫瑪加成同模式:`attr()/skill()/抗性` 疊加、
**成長/夾限只用 base_***)。狀態持久存在 Character 上(進存檔),不同於戰鬥內 `active_effects`。

🔴 紅線(偷襲不可一刀秒 solo boss):獸形**必須**放大力量,但結構性免疫於刺客紅線 ——
獸形與潛行互斥(變身會破壞潛行),獸形攻擊一律 `sneak_attack=False`(由 main.run_battle 呼叫端守門);
人形(afflicted 未變身)零屬性加成(只疾病免疫)→ scout 估傷不受狼人身分影響。
combat 一律讀**快取布林 `char.beast_form`**(`resolve_attack` 無 state 參數),由本模組與 `beast_form_until`
保持一致(transform/revert/update/ensure 同步維護)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats

# --- 時程 ---------------------------------------------------------------
INCUBATION_DAYS = 3          # 狼人熱潛伏幾日後轉化
BEAST_DURATION_HOURS = 3     # tier 0 一次獸形的基礎持續(遊戲小時;戰鬥不推進時間 → 一場戰鬥內必不過期)
FEED_EXTEND_HOURS = 2        # 每次吞噬延長的時數
MAX_FEEDS_PER_FORM = 5       # tier 0 每次獸形最多吞噬續時次數(封「無限獸形」farm)
EXHAUST_FATIGUE = 30         # 變回人形的力竭代價(扣體力)
RITUAL_RANK_INDEX = 4        # 戰友團達此階級索引(內圈戰友),獸血儀式才會現身

# --- 獸形加成(刻意只給屬性 + 一筆生命加成;不給技能 → 但保留 skill 層供未來/對稱)----
# strength 放大近戰(獸形不走偷襲故不破紅線);endurance→體力上限;speed/agility→命中/閃避。
BEAST_ATTR = {"strength": 25, "endurance": 40, "speed": 15, "agility": 10}   # = tier 0
BEAST_HEALTH = 80            # tier 0 獸形額外生命上限(脫甲 → 靠巨量血量扛;走 char.werewolf_health_bonus)
BEAST_ARMOR = 4              # 獸形自然護甲(脫去穿戴護甲;野獸厚皮的微薄防護)
BEAST_CLAW = "beast_claws"   # 獸爪自然武器 id(weapons.json;無附魔/淬鍊 → 結構性抑制裝備)

DISEASE_IMMUNE = {"disease": 100}   # 狼人化即疾病(恆有 → 與吸血鬼互斥)

# --- 餵食進程「獸血隨狩獵成長」(由 werewolf_total_feeds 累計推導,零新存檔欄,同 mastery 門檻模式)----
# 越常以獸形吞噬獵物,獸血越濃 → 屬性/生命/獸爪/持續/吞噬上限隨階提升。tier 0 = 上面的 base 常數。
FEED_TIERS = [10, 25, 50, 100]   # 累計吞噬達各門檻 → 升一階(階 0..4)
TIER_NAMES = ["獸血初醒", "壯碩巨狼", "嗜血狂獸", "野性之王", "血月之主"]
_TIER_ATTR = [
    BEAST_ATTR,
    {"strength": 30, "endurance": 48, "speed": 16, "agility": 11},
    {"strength": 34, "endurance": 55, "speed": 18, "agility": 12},
    {"strength": 38, "endurance": 62, "speed": 19, "agility": 13},
    {"strength": 42, "endurance": 70, "speed": 20, "agility": 14},
]
_TIER_HEALTH = [BEAST_HEALTH, 100, 120, 140, 160]
_TIER_CLAW = [0, 1, 2, 3, 4]        # 獸爪額外傷害(加在 beast_claws base 之上;僅獸形)
_TIER_DURATION = [BEAST_DURATION_HOURS, 3, 4, 4, 5]    # 獸形持續(小時)
_TIER_MAXFEEDS = [MAX_FEEDS_PER_FORM, 5, 6, 7, 8]      # 每場吞噬續時上限

# 恫嚇之嚎(達 HOWL_TIER 解鎖的獸形專屬戰技):嚎叫使敵恐懼。耗體力(無新存檔欄),
# 🔴 solo boss 免疫(比照武器麻痺/偷襲夾限的反鎖王紅線,杜絕嚎叫永控 boss)。
HOWL_TIER = 2
HOWL_FATIGUE = 25
HOWL_FEAR_TURNS = 2

HIRCINE_RING = "hircine_ring"   # 獵者之戒(具名神器):穿戴時可隨意變身(繞過每日冷卻)
FULL_MOON_DURATION_BONUS = 2    # 滿月(R50):獸形額外延長時數(月之主宰;只動時程不動戰鬥數值)


def _today(state) -> int:
    return state.time.absolute_hours() // 24


def _now(state) -> int:
    return state.time.absolute_hours()


class _TimeState:
    """ensure 等情境下,以單一 GameTime 餵給只讀 `state.time` 的內部函式的輕量殼。"""

    def __init__(self, time):
        self.time = time


# ======================================================================
# 狀態查詢
# ======================================================================
def is_werewolf(char: Character) -> bool:
    return getattr(char, "is_werewolf", False)


def is_infected(char: Character) -> bool:
    """已染狼人熱、潛伏中(尚未轉化)。"""
    return (not is_werewolf(char)) and getattr(char, "werewolf_infected_day", -1) >= 0


def susceptible(char: Character) -> bool:
    """還能被狼人感染(非狼人、非潛伏中、且非吸血鬼 → 吸血鬼疾病免疫互斥)。"""
    from tesrpg.systems import vampirism
    return (not is_werewolf(char)) and not is_infected(char) and not vampirism.is_vampire(char)


def is_beast(char: Character, state) -> bool:
    """目前是否處於獸形(由計時 `beast_form_until` 推導,供 update/ensure)。"""
    return is_werewolf(char) and state is not None and _now(state) < getattr(char, "beast_form_until", 0)


def can_transform(char: Character, state, gamedata: GameData) -> bool:
    """是否可發動獸化(狼人、未在獸形中、冷卻就緒)。R50:戰鬥或平時(野外/城鎮)皆可。"""
    from tesrpg.systems import powers
    return (is_werewolf(char) and not getattr(char, "beast_form", False)
            and (powers.usable_in(char, state, gamedata, "combat")
                 or powers.usable_in(char, state, gamedata, "utility")))


def effective_duration(char: Character, state, gamedata: GameData) -> int:
    """本次獸形持續時數:獸血階基礎 + 滿月加成(R50) + 獵群「獸血之盛」階級延長(R52,只詛咒者可達)。"""
    from tesrpg.systems import moons, factions
    base = beast_duration(char) + (FULL_MOON_DURATION_BONUS if moons.is_full_moon(state) else 0)
    return base + int(base * factions.beast_vigor(char, gamedata))


def can_offer_ritual(char: Character) -> bool:
    """戰友團內圈是否會向你獻上獸血儀式(已晉內圈戰友、非吸血鬼、尚未狼人化)。"""
    from tesrpg.systems import vampirism
    return (char.factions.get("companions", -1) >= RITUAL_RANK_INDEX
            and not vampirism.is_vampire(char) and not is_werewolf(char))


# ======================================================================
# 餵食進程(由 werewolf_total_feeds 累計推導;零新存檔欄)
# ======================================================================
def tier(char: Character) -> int:
    """獸血階(0..len(FEED_TIERS)):累計吞噬越多越高。"""
    fed = getattr(char, "werewolf_total_feeds", 0)
    return sum(1 for thr in FEED_TIERS if fed >= thr)


def beast_attr(char: Character) -> dict:
    return _TIER_ATTR[tier(char)]


def beast_health(char: Character) -> int:
    return _TIER_HEALTH[tier(char)]


def claw_bonus(char: Character) -> int:
    """獸爪隨階的額外傷害(加在 beast_claws base 之上;combat._weapon_profile 讀)。"""
    return _TIER_CLAW[tier(char)]


def beast_duration(char: Character) -> int:
    return _TIER_DURATION[tier(char)]


def max_feeds(char: Character) -> int:
    return _TIER_MAXFEEDS[tier(char)]


def can_howl(char: Character, state) -> bool:
    """獸形中且獸血階達 HOWL_TIER → 可施恫嚇之嚎。"""
    return is_beast(char, state) and tier(char) >= HOWL_TIER


def has_hircine_ring(char: Character, gamedata: GameData) -> bool:
    """是否穿戴獵者之戒(具名神器,`hircine` 旗標)→ 可隨意變身(繞過每日冷卻)。"""
    return any((gamedata.item_or_none(i) or {}).get("hircine")
               for i in getattr(char, "equipped", {}).values())


def tier_progress(char: Character) -> dict:
    """供 UI:目前階名/累計吞噬/距下一階(已滿階則無 next_*)。"""
    fed = getattr(char, "werewolf_total_feeds", 0)
    t = tier(char)
    out = {"tier": t, "name": TIER_NAMES[t], "feeds": fed}
    if t < len(FEED_TIERS):
        out.update({"next_name": TIER_NAMES[t + 1], "next_threshold": FEED_TIERS[t],
                    "remaining": FEED_TIERS[t] - fed})
    return out


def howl(char: Character, state, gamedata: GameData, enemies) -> dict:
    """恫嚇之嚎:對所有存活敵人施加恐懼(耗體力)。回傳 {ok, affected}。
    🔴 solo boss 由「完全免疫」改機率減免(R44:嚎叫對 boss 偶爾有感,經集中 helper 統一管控)。"""
    from tesrpg.systems import combat, magic
    if char.fatigue < HOWL_FATIGUE:
        return {"ok": False, "affected": 0}
    char.fatigue = max(0, char.fatigue - HOWL_FATIGUE)
    n = 0
    for e in enemies:
        if combat.is_alive(e) and magic.apply_control(e, "fear", gamedata, state.rng,
                                                      turns=HOWL_FEAR_TURNS) == "applied":
            n += 1
    return {"ok": True, "affected": n}


# ======================================================================
# 加成層(獨立層,與裝備/吸血鬼加成同模式)
# ======================================================================
def apply_to_character(char: Character, state, gamedata: GameData) -> None:
    """依現狀(是否狼人 / 是否獸形)重算 `werewolf_*` 層,並重算衍生資源(夾限)。

    - 獸形中:屬性 + 生命加成 + 疾病免疫(力量/耐力流進體力/生命上限)。
    - 人形 afflicted:僅疾病免疫(擋吸血鬼互斥),零屬性加成。
    - 非狼人 / state=None 的 cure 路徑:全清空。
    """
    if is_beast(char, state):
        char.werewolf_attr_bonus = dict(beast_attr(char))     # 隨獸血階成長
        char.werewolf_skill_bonus = {}
        char.werewolf_resist = dict(DISEASE_IMMUNE)
        char.werewolf_health_bonus = beast_health(char)
        char.beast_form = True
    elif is_werewolf(char):
        char.werewolf_attr_bonus = {}
        char.werewolf_skill_bonus = {}
        char.werewolf_resist = dict(DISEASE_IMMUNE)   # 人形仍免疫疾病 → 不會再被吸血鬼感染
        char.werewolf_health_bonus = 0
        char.beast_form = False
    else:
        char.werewolf_attr_bonus = {}
        char.werewolf_skill_bonus = {}
        char.werewolf_resist = {}
        char.werewolf_health_bonus = 0
        char.beast_form = False
        char.beast_form_until = 0
        char.beast_feeds = 0
    stats.recompute_max_resources(char, gamedata)


# ======================================================================
# 感染 → 轉化(每圈 update 驅動)
# ======================================================================
def infect(char: Character, state) -> bool:
    """染上狼人熱(開始潛伏)。已是狼人/潛伏中/吸血鬼 → 無效,回傳 False。"""
    if not susceptible(char):
        return False
    char.werewolf_infected_day = _today(state)
    return True


def contract(char: Character, state, gamedata: GameData) -> bool:
    """直接成為狼人(戰友團儀式 / 開局):略過潛伏。吸血鬼互斥 → 拒絕。回傳是否成功。"""
    from tesrpg.systems import vampirism
    if vampirism.is_vampire(char) or is_werewolf(char):
        return False
    char.is_werewolf = True
    char.werewolf_infected_day = -1
    char.beast_form_until = 0
    char.beast_feeds = 0
    apply_to_character(char, state, gamedata)
    return True


def cure(char: Character, gamedata: GameData) -> None:
    """解除狼人化(獵巫女媒介之儀的收尾):清空狀態、卸除加成、重算。可重複(日後仍可再染)。"""
    char.is_werewolf = False
    char.werewolf_infected_day = -1
    char.beast_form_until = 0
    char.beast_feeds = 0
    apply_to_character(char, None, gamedata)   # 非狼人分支:清空 werewolf_* 並 recompute


def update(state, gamedata: GameData) -> list[dict]:
    """每個主迴圈回合呼叫(掛 game_loop 頂端,vampirism→skooma 之後):
    處理潛伏→轉化、獸形過期→變回、開局狼人初始化。回傳事件清單供 UI。

    事件 kind:`turn`(初次化為狼人)/`revert`(獸形退去 → 力竭)。
    """
    char = state.player
    events: list[dict] = []

    # 潛伏期滿 → 轉化為狼人
    if is_infected(char) and _today(state) - char.werewolf_infected_day >= INCUBATION_DAYS:
        char.is_werewolf = True
        char.werewolf_infected_day = -1
        char.beast_form_until = 0
        char.beast_feeds = 0
        apply_to_character(char, state, gamedata)
        events.append({"kind": "turn"})
        return events

    if is_werewolf(char):
        # 加成層尚未套用(剛轉化/開局即狼人:人形應有疾病免疫)→ 視為待初始化
        stale = "disease" not in char.werewolf_resist
        if getattr(char, "beast_form", False) and not is_beast(char, state):
            # 獸形計時已過 → 變回人形(清層 + 力竭;recompute 夾血上限防溢出)
            revert(char, state, gamedata)
            events.append({"kind": "revert"})
        elif stale:
            apply_to_character(char, state, gamedata)
    return events


# ======================================================================
# 變身 / 吞噬 / 變回
# ======================================================================
def transform(char: Character, state, gamedata: GameData) -> dict:
    """發動獸化:化為獸形一段時間。設冷卻(由 powers.use 記)、補血(填上增幅)。

    回傳 {"messages": [...]}(供 powers.use 串接)。
    """
    char.beast_form_until = _now(state) + effective_duration(char, state, gamedata)   # 隨獸血階 + 滿月 + 獵群階級延長
    char.beast_feeds = 0
    before_max = char.max_health
    apply_to_character(char, state, gamedata)     # 套獸形層 + recompute(生命/體力上限上升)
    gain = max(0, char.max_health - before_max)
    char.health = min(char.max_health, char.health + gain)   # 變身瞬間補上增幅(非半條血)
    stats.clamp_resources(char)
    return {"messages": ["你的骨骼錯裂、皮肉迸張 —— 一頭嗜血的巨狼自你身軀掙脫而出!"
                         "(獸形:利爪撕敵、刀槍難傷,但無法施法、用物或持械。)"]}


def devour(char: Character, state, gamedata: GameData) -> dict:
    """吞噬倒下的獵物:延長獸形 + 回血(每次獸形至多 MAX_FEEDS_PER_FORM 次,封無限獸形)。

    回傳 {"extended": bool, "healed": int}。
    """
    if not is_beast(char, state) or char.beast_feeds >= max_feeds(char):   # 上限隨獸血階提升
        return {"extended": False, "healed": 0}
    char.beast_feeds += 1
    char.werewolf_total_feeds = getattr(char, "werewolf_total_feeds", 0) + 1
    # 吞噬即時滋長獸血:跨階則屬性/生命上限/獸爪同步升級(beast 分支重算),回血亦隨階提升
    apply_to_character(char, state, gamedata)
    char.beast_form_until = max(char.beast_form_until, _now(state)) + FEED_EXTEND_HOURS
    before = char.health
    from tesrpg.systems import factions          # R52:獵群「獸血之盛」隨階強化吞噬回血(只詛咒者可達)
    heal = int(beast_health(char) // 2 * (1 + factions.beast_vigor(char, gamedata)))
    char.health = min(char.max_health, char.health + heal)
    return {"extended": True, "healed": int(char.health - before)}


def revert(char: Character, state, gamedata: GameData) -> None:
    """變回人形:清獸形層 + 力竭代價 + 重算(夾血上限,防生命溢出)。"""
    char.beast_form_until = 0
    char.beast_feeds = 0
    char.beast_form = False
    apply_to_character(char, state, gamedata)     # 人形分支:卸獸形屬性/生命 + recompute → 夾血
    char.fatigue = max(0, char.fatigue - EXHAUST_FATIGUE)


def sync_beast_form(char: Character, state, gamedata: GameData) -> bool:
    """把獸形快取布林與計時器對齊:若時間已在單一動作內推進過 `beast_form_until`(獸形實已過期)
    則就地變回人形。供戰鬥/遭遇進入點呼叫 —— `combat.resolve_attack` 讀快取布林(無 state),而
    `game_loop` 的 update 只在每圈頂端刷新;旅行/休息在『同一動作內』推進時間 + 觸發戰鬥時,
    快取會比計時器慢一拍(對抗審查抓到的脫鉤)→ 此處在進戰前對齊,杜絕以過期獸形作戰。回傳是否剛變回。"""
    if getattr(char, "beast_form", False) and not is_beast(char, state):
        revert(char, state, gamedata)
        return True
    return False


# ======================================================================
# 存檔遷移 + 一生傳奇標籤
# ======================================================================
def ensure_lycanthropy_fields(char: Character, time, gamedata: GameData) -> None:
    """舊存檔遷移(state.from_dict 接線,排在 skooma 之後):補欄(dataclass 預設已處理大半)+
    依當前時間重算 werewolf_* 層 → 載入當下即正確(獸形已過期 → 自動變回人形 + 夾血)。"""
    if getattr(char, "werewolf_attr_bonus", None) is None:
        char.werewolf_attr_bonus = {}
    if getattr(char, "werewolf_skill_bonus", None) is None:
        char.werewolf_skill_bonus = {}
    if getattr(char, "werewolf_resist", None) is None:
        char.werewolf_resist = {}
    st = _TimeState(time)
    if getattr(char, "beast_form", False) and not is_beast(char, st):
        revert(char, st, gamedata)        # 存檔於獸形、載入時已過期 → 變回(夾血 + 力竭)
    else:
        apply_to_character(char, st, gamedata)


def legacy_label(char: Character) -> str | None:
    if is_werewolf(char):
        return "狼人"
    if is_infected(char):
        return "染上狼人熱"
    return None
