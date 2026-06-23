"""常態世界脈動(動態世界新聞層 + 聚光激增可重複委託)。

`worldstate.update`(authored 一次性大政局)之後再廣播一層**常態餘響** —— 各省持續傳來
盜匪猖獗 / 商隊遇襲 / 領主懸賞等在地新聞;部分新聞「聚光」該省的可重複委託一段時間
(active window),期間該委託浮現於告示板,玩家看新聞 → 決定要不要回應 → 去探索完成。

設計(對位 worldstate.py / aiwar.py 的決定性狀態機):
- `update(state, gamedata)` 掛 game_loop 每圈頂端;**每日至多評估一次**(`pulse_eval_day` 哨兵防同日多圈洗版)、
  通過冷卻+解鎖的候選池中**低機率**廣播一筆,回傳 [{"id","news"}] 供 ui 廣播。
- **決定性(R24)**:迭代一律 `sorted(gamedata.world_pulse)`(迭代序不餵 rng);rng 只在「是否廣播」與
  「加權挑選」兩決策點吃 `state.rng`;`active_pulses`/`spotlighted_board_quests` 純推導不碰 rng。
- **聚光 active window 純由 `world_pulse_day` 推導**(today − 上次廣播日 < active_window_days,鏡像 moons.py
  零存檔欄推導)→ 不需 per-委託冷卻欄;脈動 cooldown_days(兩次激增最短間隔)+ active_window_days(激增持續期)
  即唯一冷卻概念。可重複委託**永不進 completed_quests**(quests._complete),能見度全由聚光 gate 控制。
- **不帶傷害/數值 effect**:脈動是引子,獎勵來自玩家去接的委託本身(守反 min-max)。

加脈動純改 `data/world_pulse.json`(province / weight / cooldown_days / active_window_days /
min_day / requires_event / spotlight_quests / news)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData

GLOBAL_CHANCE = 0.5         # 通過冷卻的候選池存在時,本日是否廣播一筆的全域機率(state.rng;防天天有新聞)
DEFAULT_ACTIVE_WINDOW = 7   # 脈動省略 active_window_days 時的預設聚光視窗(天)


def day_index(state) -> int:
    """脈動的「日」基準 = 開局後天數(對齊 worldstate 的 days-since-start;非絕對日)。
    冷卻/active window 是差值與基準無關,但 min_day=開局後第幾天才需此基準才正確(防序章洗版)。
    呼叫端(update / main.action_board)務必都用此 → world_pulse_day 與 gate 同基準。"""
    return max(0, (state.time.absolute_hours() - state.start_time.absolute_hours()) // 24)


def _eligible(char, gamedata: GameData, today: int) -> list[str]:
    """冷卻過 + 解鎖過 + min_day 過的脈動 id;固定 sorted 序(決定性,迭代序不餵 rng)。"""
    out = []
    for pid in sorted(gamedata.world_pulse):
        p = gamedata.world_pulse[pid]
        if today < p.get("min_day", 0):
            continue
        req = p.get("requires_event")
        if req and req not in char.world_events_fired:    # 複用既有解鎖層(唯讀,不寫)
            continue
        last = char.world_pulse_day.get(pid)
        if last is not None and (today - last) < p.get("cooldown_days", DEFAULT_ACTIVE_WINDOW):
            continue                                       # 冷卻未過
        out.append(pid)
    return out


def _pick(pool: list[str], gamedata: GameData, rng) -> str:
    """加權抽一筆(鏡像 events 加權 roll 累加;單次 rng 呼叫,pool 已 sorted)。"""
    weights = [max(0.0, gamedata.world_pulse[pid].get("weight", 1)) for pid in pool]
    total = sum(weights)
    if total <= 0:
        return pool[0]
    r = rng.roll(0.0, total)
    acc = 0.0
    for pid, w in zip(pool, weights):
        acc += w
        if r <= acc:
            return pid
    return pool[-1]


def active_pulses(char, gamedata: GameData, today: int) -> set:
    """純推導:近 active_window_days 內廣播過的脈動 id(零額外狀態欄,同 moons.py 推導模式)。"""
    out = set()
    for pid, last in char.world_pulse_day.items():
        p = gamedata.world_pulse.get(pid)
        if not p:
            continue
        win = p.get("active_window_days", DEFAULT_ACTIVE_WINDOW)
        if 0 <= today - last < win:        # 防呆:0≤ 守時鐘倒退/陳舊日不誤判 active(實際 today 單調 ≥ last)
            out.add(pid)
    return out


def spotlighted_board_quests(char, gamedata: GameData, province: str, today: int) -> set:
    """該省目前 active 脈動所聚光的可重複委託 id 集合(供 quests.available_quests 的 board gate 用)。"""
    out = set()
    for pid in active_pulses(char, gamedata, today):
        p = gamedata.world_pulse[pid]
        if p.get("province") != province:
            continue
        out.update(p.get("spotlight_quests", []))
    return out


def update(state, gamedata: GameData) -> list[dict]:
    """game_loop 每圈頂端結算;回傳 [{"id","news"}] 供 ui 廣播。每日至多一筆、低機率、決定性。"""
    char = state.player
    today = day_index(state)
    if char.pulse_eval_day == today:        # 同日多圈只評估一次(防同地連按洗版)
        return []
    char.pulse_eval_day = today
    pool = _eligible(char, gamedata, today)
    if not pool:
        return []
    if not state.rng.chance(GLOBAL_CHANCE):  # rng 決策點一:是否廣播(決定性)
        return []
    pid = _pick(pool, gamedata, state.rng)   # rng 決策點二:加權挑選(決定性)
    p = gamedata.world_pulse[pid]
    char.world_pulse_day[pid] = today        # 記冷卻起點 + 啟動 active window(供聚光 gate 推導)
    return [{"id": pid, "news": p.get("news", "")}]


def ensure_pulse_fields(char) -> None:
    """存檔相容(冪等):補欄。脈動 active window 全推導,無需重算層。"""
    if getattr(char, "world_pulse_day", None) is None:
        char.world_pulse_day = {}
    # 防呆:清掉值非 int 的毀損鍵(冪等)
    char.world_pulse_day = {k: v for k, v in char.world_pulse_day.items() if isinstance(v, int)}
    if not isinstance(getattr(char, "pulse_eval_day", None), int):
        char.pulse_eval_day = 0
