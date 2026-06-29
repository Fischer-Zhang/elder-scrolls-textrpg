"""玩家雙面間諜(臥底 / double agent)—— 一條「掩護身分 ↔ 價值觀漂移」的動態天平(R100)。

循環(仿斯庫瑪/吸血鬼的 power↔curse 設計,但**零戰鬥面狀態**):

  真實公會 A(你是會員)派你潛入其宿敵公會 B → `infiltrate` 設 `cover_guild=B`:
  B 的 NPC 認你為自己人(dialogue._guild_attitude)、B 不再敵視你(factions.faction_hostility),
  但你**不真入 B**(cover_guild 絕不寫進 char.factions → R96 互斥不變式不破、B 戰鬥 perk 自動為 0)。

  **價值觀漂移(cover_loyalty −100..+100)**:為 A 做事(破壞/情報)→ loyalty 往 A(負)、secrecy 降(冒險);
  為 B 證明忠誠 → loyalty 往 B(正)、secrecy 升(看起來忠誠)。要藏好就得替 B 賣力 → 漸生同情 = 價值觀衝突。
  跨閾解鎖三結局:忠誠抽身(loyalty≤0)/ 真正叛變(loyalty≥+60·真入 B 棄 A)/ 曝光失敗。

  **secrecy + 殺知情者**:secrecy 每日衰減;低 secrecy → 某現有具名 B NPC「起疑」(cover_knower + 期限)。
  你得趕去**限時決鬥**滅口(KNOWER_DUEL_ROUNDS 回合內擊殺);逾回合脫逃 / 逾期未殺 → 情報送達 → 曝光。

設計與哲學調和:**零 `*_attr/skill_bonus`/`*_resist`**(不碰 attr()/skill())→ combat/formulas 讀值不變;
所有狀態在 `cover_guild==""` 時全 no-op → `sim_assassin` byte-identical(刺客永不臥底)。
平衡(secrecy/loyalty/識破機率)非戰鬥 → by-design + 煙霧(同 R50 manhunt 立場,非 sim 量)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

# --- 門檻與旋鈕(by-design·煙霧調) ------------------------------------
SECRECY_START = 100            # 入局起始掩護完整度
SECRECY_DAILY_DECAY = 6        # 每日 secrecy 衰減(passive·約 16 日見底)
SILENCE_SECRECY_FLOOR = 50     # 殺知情者滅口成功後 secrecy 回升至此地板
EXPOSURE_DETECT_CAP = 0.55     # secrecy=0 時的每日識破機率上限(仿 vampirism.detection_chance)
KNOWER_GRACE_DAYS = 3          # 知情者起疑 → 通風報信的寬限日(限時追殺視窗)
KNOWER_DUEL_ROUNDS = 3         # 限時決鬥:N 回合內未擊殺知情者 → 脫逃曝光

LOYALTY_MIN = -100            # 忠於真實公會 A
LOYALTY_MAX = 100             # 同情掩護公會 B
LOYALTY_DEFECT = 60          # ≥ 此值 + secrecy>DEFECT_MIN_SECRECY → 解鎖真正叛變
LOYALTY_EXTRACT = 0          # ≤ 此值 → 解鎖忠誠抽身
DEFECT_MIN_SECRECY = 30      # 叛變需掩護尚存(否則只能曝光/抽身)

SILENCE_INFAMY = 1           # 殺人滅口的惡名代價(諜報無賞金,惟此 infamy)

# 入局:真實公會 A(犯罪公會)→ 派你潛入其非犯罪宿敵 B。核心三對(R100)。
INFILTRATE_PAIRS = {"thieves_guild": "fighters_guild",
                    "dark_brotherhood": "fighters_guild",
                    "mythic_dawn": "knights_nine"}
INFILTRATE_RANK = 2          # 真實公會須達此階(rank_index)才獲派潛入任務


class _TimeState:
    """ensure 等情境下,以單一 GameTime 餵給只讀 `state.time` 的內部殼(仿 skooma._TimeState)。"""

    def __init__(self, time):
        self.time = time


def _day(state) -> int:
    return state.time.absolute_hours() // 24


# ======================================================================
# 狀態查詢(全由 7 個純量推導·零戰鬥面狀態)
# ======================================================================
def on_mission(char: Character) -> bool:
    return bool(getattr(char, "cover_guild", ""))


def has_knower(char: Character) -> bool:
    return bool(getattr(char, "cover_knower", ""))


def secrecy(char: Character) -> int:
    return getattr(char, "cover_secrecy", 0)


def loyalty(char: Character) -> int:
    return getattr(char, "cover_loyalty", 0)


def detection_chance(char: Character) -> float:
    """secrecy 越低 → 每日被某 B NPC 識破的機率越高(secrecy=100→0·secrecy=0→CAP)。"""
    return max(0.0, EXPOSURE_DETECT_CAP * (1.0 - secrecy(char) / 100.0))


def extraction_unlocked(char: Character) -> bool:
    return on_mission(char) and loyalty(char) <= LOYALTY_EXTRACT


def defection_unlocked(char: Character) -> bool:
    return on_mission(char) and loyalty(char) >= LOYALTY_DEFECT and secrecy(char) > DEFECT_MIN_SECRECY


def cover_blown_flag(true_guild: str, cover_guild: str) -> str:
    return f"cover_blown_{true_guild}_{cover_guild}"


def can_infiltrate(char: Character, gamedata: GameData, true_guild: str) -> bool:
    """A 公會可否現在派你潛入其宿敵 B:會員達階 + 目前未在臥底 + 該對未曾曝光(永久死局)。"""
    from tesrpg.systems import factions
    b = INFILTRATE_PAIRS.get(true_guild)
    if not b or on_mission(char):
        return False
    if factions.rank_index(char, true_guild) < INFILTRATE_RANK:
        return False
    return cover_blown_flag(true_guild, b) not in getattr(char, "world_events_fired", [])


def hall_has_business(char: Character, gamedata: GameData, true_guild: str) -> bool:
    """A 大廳是否該顯示「間諜事務」入口:可入局,或已在為此 A 執行的臥底任務中。"""
    return can_infiltrate(char, gamedata, true_guild) or \
        (on_mission(char) and getattr(char, "cover_true_guild", "") == true_guild)


# ======================================================================
# 入局 / 漂移 / 結局狀態變更
# ======================================================================
def infiltrate(char: Character, state, gamedata: GameData, *, true_guild: str, cover_guild: str) -> None:
    """接下 A 的潛入任務 → 進入臥底狀態(掩護 B·真身 A)。閘由呼叫端(任務)把關。"""
    char.cover_true_guild = true_guild
    char.cover_guild = cover_guild
    char.cover_secrecy = SECRECY_START
    char.cover_loyalty = 0
    char.cover_last_day = _day(state)
    char.cover_knower = ""
    char.cover_knower_deadline = 0


def apply_cover_deltas(char: Character, *, loyalty_delta: int = 0, secrecy_delta: int = 0) -> None:
    """任務完成時套用忠誠/掩護漂移(quests._complete 的 cover_deltas 鍵)。僅臥底中生效。"""
    if not on_mission(char):
        return
    if loyalty_delta:
        char.cover_loyalty = max(LOYALTY_MIN, min(LOYALTY_MAX, char.cover_loyalty + loyalty_delta))
    if secrecy_delta:
        char.cover_secrecy = max(0, min(100, char.cover_secrecy + secrecy_delta))


def assign_knower(char: Character, state, nid: str) -> None:
    """某 B NPC 起疑 → 設為知情者 + 限時追殺視窗(deadline = 今日 + KNOWER_GRACE_DAYS)。"""
    char.cover_knower = nid
    char.cover_knower_deadline = _day(state) + KNOWER_GRACE_DAYS


def silence_knower(char: Character) -> None:
    """限時決鬥滅口成功:掩護保住 —— secrecy 回地板、清知情者、惡名加身(殺人代價)。"""
    char.cover_secrecy = max(char.cover_secrecy, SILENCE_SECRECY_FLOOR)
    char.cover_knower = ""
    char.cover_knower_deadline = 0
    char.infamy = getattr(char, "infamy", 0) + SILENCE_INFAMY


def expose(char: Character) -> dict:
    """掩護曝光(secrecy 歸零 / 逾期 / 決鬥脫逃):清臥底狀態 + 記永久死局旗標。
    清掉 cover_guild 後,因你仍在 A(B 宿敵)→ faction_hostility(B) 自動恢復敵視(R96·零額外碼)。"""
    flag = cover_blown_flag(char.cover_true_guild, char.cover_guild)
    ev = {"kind": "exposed", "cover_guild": char.cover_guild, "true_guild": char.cover_true_guild, "flag": flag}
    wf = getattr(char, "world_events_fired", None)
    if isinstance(wf, list) and flag not in wf:
        wf.append(flag)
    _clear(char)
    return ev


def clear_cover(char: Character) -> None:
    """忠誠抽身收尾(extract 結局):乾淨退出臥底·留在 A·不記死局旗標。"""
    _clear(char)


def defect(char: Character, gamedata: GameData) -> dict:
    """真正叛變(turncoat 結局):棄 A、真入 B(B 變真會籍 rank0)、結束掩護。
    factions 變更在此單點(仿 quests eradicate/join);誓福/惡名由任務 reward 另給。"""
    from tesrpg.systems import factions
    a = char.cover_true_guild
    b = char.cover_guild
    char.factions.pop(a, None)          # 棄真實公會 A
    factions.join(char, b)              # B 由掩護轉真會籍(rank 0)
    ev = {"kind": "defected", "from": a, "to": b}
    _clear(char)
    return ev


def _clear(char: Character) -> None:
    char.cover_guild = ""
    char.cover_true_guild = ""
    char.cover_secrecy = 0
    char.cover_loyalty = 0
    char.cover_last_day = 0
    char.cover_knower = ""
    char.cover_knower_deadline = 0


# ======================================================================
# 知情者選定(現有具名 B NPC·優先可達省·排除已滅口者)
# ======================================================================
def pick_knower(char: Character, gamedata: GameData, *, province: str | None = None) -> str | None:
    """從掩護公會 B 的現有具名 NPC 中選一名「起疑者」:優先玩家所在省(保可達),
    否則任一未被你滅口(murdered)的 B NPC。無可用者 → None(退回 secrecy-0 直接曝光)。"""
    b = getattr(char, "cover_guild", "")
    if not b:
        return None
    murdered = set(getattr(char, "murdered_npcs", []) or [])
    pool = [nid for nid, npc in gamedata.npcs.items()
            if npc.get("guild") == b and nid not in murdered]
    if not pool:
        return None
    if province is not None:
        local = [nid for nid in pool
                 if gamedata.location(gamedata.npcs[nid]["location"]).get("province") == province]
        if local:
            pool = local
    return sorted(pool)[0]              # 決定性(避免 rng;同省則取序最前)


# ======================================================================
# 每圈 update(掛 game_loop·skooma.update 之後·決定性:衰減 + 逾期/歸零曝光)
# ======================================================================
def update(state, gamedata: GameData) -> list[dict]:
    """臥底每日維護(決定性·不擲 rng → rng 識破在 main._undercover_detection)。

    事件 kind:`exposed`(掩護曝光)。secrecy 衰減走 cover_last_day 水印 ratchet(防重載重複)。
    """
    char = state.player
    if not on_mission(char):
        return []
    events: list[dict] = []
    today = _day(state)
    days = today - getattr(char, "cover_last_day", today)
    if days > 0:
        char.cover_secrecy = max(0, char.cover_secrecy - days * SECRECY_DAILY_DECAY)
        char.cover_last_day = today
    # 知情者通風報信(逾期未滅口)→ 曝光
    if has_knower(char) and today > getattr(char, "cover_knower_deadline", 0):
        events.append(expose(char))
        return events
    # secrecy 歸零 → 直接曝光(知情者路徑的保底)
    if char.cover_secrecy <= 0:
        events.append(expose(char))
    return events


# ======================================================================
# 存檔遷移 + 一生傳奇標籤
# ======================================================================
def ensure_cover_fields(char: Character, time, gamedata: GameData) -> None:
    """舊存檔遷移(save_migrations 接線):補欄(dataclass 預設已處理大半)+ 夾限/水印自癒。
    無戰鬥面快取層 → 不需 recompute(與 skooma/vampirism 不同·刻意零戰鬥狀態)。"""
    for fld, dflt in (("cover_guild", ""), ("cover_true_guild", ""), ("cover_secrecy", 0),
                      ("cover_loyalty", 0), ("cover_last_day", 0),
                      ("cover_knower", ""), ("cover_knower_deadline", 0)):
        if getattr(char, fld, None) is None:
            setattr(char, fld, dflt)
    if on_mission(char):
        char.cover_secrecy = max(0, min(100, char.cover_secrecy))
        char.cover_loyalty = max(LOYALTY_MIN, min(LOYALTY_MAX, char.cover_loyalty))
        if char.cover_last_day <= 0:        # 補水印 → 載入當下不暴衝衰減
            char.cover_last_day = time.absolute_hours() // 24


def legacy_label(char: Character) -> str | None:
    return "雙面間諜" if on_mission(char) else None
