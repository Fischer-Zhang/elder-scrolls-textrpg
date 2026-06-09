"""斯庫瑪 / 月糖成癮(Skooma / Moon-Sugar)—— 一條「亢奮 ↔ 成癮詛咒」的動態天平。

循環(仿吸血鬼系統的 power↔curse 設計):

  服用月糖(弱)或斯庫瑪(強)→ 進入限時「亢奮」(`skooma_high_until` 絕對小時前皆 high):
  一段時間內獲得 速度/敏捷/意志 增益(亢奮的反射與耐力)+ 一次性資源回復。每次用藥
  `skooma_addiction` +1,且**耐受性**讓同樣劑量的亢奮越來越短。成癮達門檻後,**清醒時**
  陷入「戒斷」—— 力量/意志/敏捷/耐力負懲罰(隨成癮深度 × 距上次用藥天數遞增),體力上限
  隨之下滑。用藥能立刻解除戒斷又給亢奮,卻使成癮更深 → 長期淨值為負,除非戒掉。

設計與本作哲學的調和:這是**真權衡**而非免費強度 —— 亢奮短、戒斷長且痛;追藥者的時間
加權屬性 ≤ 戒藥者。**亢奮刻意只碰 速度/敏捷/意志 + 資源回復、絕不碰力量/潛行/武器傷害**
→ 從結構上規避刺客「偷襲不可秒 boss/精英」紅線(`attack_damage` 吃 strength,故亢奮不給
strength;sneak 倍率也完全不碰)。`sim_assassin.py` 在亢奮生效下數值應與改前一致。

亢奮增益 / 戒斷懲罰走獨立的 `skooma_*` 層(與裝備/吸血鬼/里程碑加成同模式:`attr()/skill()`
疊加、**成長/夾限只用 base_***)。狀態持久存在 Character 上(進存檔),不同於戰鬥內
`active_effects`(後者不進存檔、入場即清,亢奮絕不可寄生其上,否則入戰即蒸發)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats

# --- 時程與門檻 ---------------------------------------------------------
MOON_SUGAR_HIGH_HOURS = 4     # 月糖(弱):基礎亢奮時長
SKOOMA_HIGH_HOURS = 8         # 斯庫瑪(強):基礎亢奮時長
MIN_HIGH_HOURS = 1            # 耐受縮短後的最低亢奮時長
TOLERANCE_FACTOR = 0.85       # 每點成癮 → 該次亢奮時長 ×(0.85^addiction),最低夾 MIN_HIGH
WITHDRAWAL_THRESHOLD = 3      # 成癮達此值,清醒時起戒斷
MAX_ADDICTION = 10            # 成癮上限(夾限,防爆量)
CLEAN_DECAY_DAYS = 2          # 清醒滿幾日 → 成癮 -1(ride-it-out 戒掉)

# --- 亢奮增益(刻意只給 速度/敏捷/意志 + 資源回復:不碰 strength→不放大武傷/偷襲)----
MOON_SUGAR_HIGH_ATTR = {"speed": 5, "agility": 5}
SKOOMA_HIGH_ATTR = {"speed": 8, "agility": 8, "willpower": 8}
MOON_SUGAR_RESTORE = {"fatigue": 40}
SKOOMA_RESTORE = {"fatigue": 80, "health": 30}

# --- 戒斷懲罰(每階 × 各屬性;step = (成癮-門檻+1)+距上次用藥天數,夾 MAX_STEPS)-----
WITHDRAWAL_ATTR_PER_STEP = {"strength": -3, "willpower": -3, "agility": -3, "endurance": -3}
WITHDRAWAL_SKILL_PER_STEP = {"alchemy": -3}
WITHDRAWAL_MAX_STEPS = 6

NAME_HIGH = "亢奮"
NAME_WITHDRAWAL = "戒斷"

# 解癮任務 id(與 main.action_skooma_cure 共用唯一來源)。自然戒除時須棄置殘留任務,
# 否則「完成採集但不行儀式 → 熬過去戒掉 → 日後再成癮」會免費解癮(對抗審查抓到的漏洞)。
CURE_QUEST_ID = "quest_skooma_cure"


class _TimeState:
    """ensure 等情境下,以單一 GameTime 餵給只讀 `state.time` 的內部函式的輕量殼。"""

    def __init__(self, time):
        self.time = time


def _now(state) -> int:
    return state.time.absolute_hours()


# ======================================================================
# 狀態查詢(全由 (high_until, addiction, last_dose) 三個純量推導)
# ======================================================================
def is_high(char: Character, state) -> bool:
    return state is not None and _now(state) < getattr(char, "skooma_high_until", 0)


def is_addicted(char: Character) -> bool:
    return getattr(char, "skooma_addiction", 0) >= WITHDRAWAL_THRESHOLD


def has_touched_sugar(char: Character) -> bool:
    """曾沾染(成癮>0 或正亢奮)—— 供 legacy 標籤判定。"""
    return getattr(char, "skooma_addiction", 0) > 0 or getattr(char, "skooma_high_until", 0) > 0


def _discard_cure_quest(char: Character) -> None:
    """棄置殘留的淨糖之儀任務(自然戒除時呼叫)→ 日後再成癮須重新賺取,杜絕免費解癮。
    只動任務名冊、不碰解癮儀式(儀式路徑由 action_skooma_cure 自行移除已完成任務)。"""
    q = getattr(char, "quests", None)
    if isinstance(q, dict):
        q.pop(CURE_QUEST_ID, None)
    cq = getattr(char, "completed_quests", None)
    if isinstance(cq, list) and CURE_QUEST_ID in cq:
        cq.remove(CURE_QUEST_ID)


def _days_since_dose(char: Character, state) -> int:
    last = getattr(char, "skooma_last_dose_hour", -1)
    if last < 0:
        return 0
    return max(0, (_now(state) - last) // 24)


def withdrawal_step(char: Character, state) -> int:
    """目前戒斷強度階(0=不在戒斷)。**成癮越深 → 越痛**(由成癮深度推導,夾 MAX_STEPS);
    戒斷只能靠用藥(暫解)或長期清醒讓成癮衰減(ride-it-out)來緩和 → 抽身只會減輕、不會更糟,
    避免「越戒越痛」與衰減 ratchet 互相打架的振盪(見 update 的清醒衰減)。"""
    if state is None or not is_addicted(char) or is_high(char, state):
        return 0
    raw = char.skooma_addiction - WITHDRAWAL_THRESHOLD + 1
    return max(0, min(WITHDRAWAL_MAX_STEPS, raw))


# ======================================================================
# 加成層(獨立層,與裝備加成同模式)
# ======================================================================
def _withdrawal_bonuses(step: int) -> tuple[dict, dict]:
    attr = {k: v * step for k, v in WITHDRAWAL_ATTR_PER_STEP.items() if v * step}
    skill = {k: v * step for k, v in WITHDRAWAL_SKILL_PER_STEP.items() if v * step}
    return attr, skill


def _layer_phase(char: Character) -> str:
    """由目前套用中的 skooma_attr_bonus 形狀反推它代表哪個相位
    (亢奮=正值、戒斷=負值、無=空)→ 供 update 偵測相位轉變。"""
    a = getattr(char, "skooma_attr_bonus", None) or {}
    if not a:
        return "clean"
    return "high" if any(v > 0 for v in a.values()) else "withdrawal"


def _intended_phase(char: Character, state) -> str:
    if is_high(char, state):
        return "high"
    if withdrawal_step(char, state) > 0:
        return "withdrawal"
    return "clean"


def apply_to_character(char: Character, state, gamedata: GameData) -> None:
    """依當前 (時間, 成癮) 重算 skooma_* 層,並重算衍生資源(意志/敏捷 → 體力上限)。

    亢奮中:增益 dict 已由 `dose` 寫入(月糖/斯庫瑪別已決定),保留不動、技能層清空。
    清醒+成癮:套戒斷負值層。其餘:清空。`state=None`(cure 路徑)→ 一律清空。
    """
    if is_high(char, state):
        char.skooma_skill_bonus = {}     # 亢奮不碰技能;attr 增益保留(dose 寫入)
    else:
        step = withdrawal_step(char, state)
        if step > 0:
            char.skooma_attr_bonus, char.skooma_skill_bonus = _withdrawal_bonuses(step)
        else:
            char.skooma_attr_bonus, char.skooma_skill_bonus = {}, {}
    stats.recompute_max_resources(char, gamedata)


# ======================================================================
# 用藥 / 戒除
# ======================================================================
def dose(state, gamedata: GameData, *, strong: bool) -> dict:
    """服用月糖(strong=False)或斯庫瑪(strong=True):進入亢奮、加深成癮、一次性回復資源。

    回傳 {"ok","strong","hours","addiction","restored"}。不主動推進時間(由呼叫端推進)。
    """
    char = state.player
    now = _now(state)
    base = SKOOMA_HIGH_HOURS if strong else MOON_SUGAR_HIGH_HOURS
    dur = max(MIN_HIGH_HOURS, round(base * (TOLERANCE_FACTOR ** char.skooma_addiction)))
    char.skooma_high_until = max(char.skooma_high_until, now) + dur
    char.skooma_last_dose_hour = now
    char.skooma_addiction = min(MAX_ADDICTION, char.skooma_addiction + 1)
    char.skooma_attr_bonus = dict(SKOOMA_HIGH_ATTR if strong else MOON_SUGAR_HIGH_ATTR)
    char.skooma_skill_bonus = {}
    stats.recompute_max_resources(char, gamedata)    # 先讓意志/敏捷增益流進體力上限
    restore = SKOOMA_RESTORE if strong else MOON_SUGAR_RESTORE
    restored: dict[str, int] = {}
    for res, amt in restore.items():
        cur = getattr(char, res)
        new = min(getattr(char, f"max_{res}"), cur + amt)
        setattr(char, res, new)
        restored[res] = int(new - cur)
    return {"ok": True, "strong": strong, "hours": dur,
            "addiction": char.skooma_addiction, "restored": restored}


def cure(char: Character, gamedata: GameData) -> None:
    """淨化解除成癮(神殿淨糖之儀的收尾):歸零成癮/亢奮、清層、重算。可重複(日後可再沾染)。"""
    char.skooma_addiction = 0
    char.skooma_high_until = 0
    char.skooma_last_dose_hour = -1
    apply_to_character(char, None, gamedata)    # state=None → 清層 + recompute


# ======================================================================
# 每圈 update(掛 game_loop 頂端,vampirism.update 之後)
# ======================================================================
def update(state, gamedata: GameData) -> list[dict]:
    """處理亢奮退去、清醒衰減、戒斷階變動;回傳事件清單供 UI 播報。

    事件 kind:`comedown`(亢奮退去)/`withdrawal`(戒斷起或加深,帶 step)/`clean`(脫離戒斷)。
    """
    char = state.player
    events: list[dict] = []
    now = _now(state)

    # 清醒衰減(ride-it-out):每滿 CLEAN_DECAY_DAYS 未用藥 → 成癮 -1;水印 ratchet 防重複計
    if not is_high(char, state) and char.skooma_addiction > 0 and char.skooma_last_dose_hour >= 0:
        days_clean = (now - char.skooma_last_dose_hour) // 24
        steps = days_clean // CLEAN_DECAY_DAYS
        if steps > 0:
            before = char.skooma_addiction
            char.skooma_addiction = max(0, char.skooma_addiction - steps)
            char.skooma_last_dose_hour += steps * CLEAN_DECAY_DAYS * 24   # ≤ now,不會超前
            if before >= WITHDRAWAL_THRESHOLD and char.skooma_addiction < WITHDRAWAL_THRESHOLD:
                events.append({"kind": "clean"})
                _discard_cure_quest(char)    # 自然戒除 → 殘留的淨糖之儀任務作廢(防免費解癮)

    # 相位 / 加成層同步(決定性):相位轉變、或戒斷因衰減而減輕(層強度變動)皆重算
    prev = _layer_phase(char)
    cur = _intended_phase(char, state)
    resync = prev != cur
    if cur == "withdrawal":
        ia, isk = _withdrawal_bonuses(withdrawal_step(char, state))
        resync = resync or char.skooma_attr_bonus != ia or char.skooma_skill_bonus != isk
    if resync:
        apply_to_character(char, state, gamedata)
    if prev == "high" and cur != "high":
        events.append({"kind": "comedown"})
    if prev != "withdrawal" and cur == "withdrawal":     # 僅在戒斷「起始」播報(衰減減輕不播)
        events.append({"kind": "withdrawal", "step": withdrawal_step(char, state)})
    return events


# ======================================================================
# 存檔遷移 + 一生傳奇標籤
# ======================================================================
def ensure_skooma_fields(char: Character, time, gamedata: GameData) -> None:
    """舊存檔遷移(state.from_dict 接線):補欄(dataclass 預設已處理大半)+ 依當前時間
    重算 skooma_* 層 → 載入當下即正確(亢奮已過則轉戒斷/清空;同 mastery 的 recompute-on-load)。"""
    if getattr(char, "skooma_attr_bonus", None) is None:
        char.skooma_attr_bonus = {}
    if getattr(char, "skooma_skill_bonus", None) is None:
        char.skooma_skill_bonus = {}
    apply_to_character(char, _TimeState(time), gamedata)


def legacy_label(char: Character) -> str | None:
    if is_addicted(char):
        return "斯庫瑪成癮者"
    if has_touched_sugar(char):
        return "沾染月糖"
    return None
