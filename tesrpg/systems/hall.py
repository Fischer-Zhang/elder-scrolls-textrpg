"""名人堂 / 往昔英雄(Hall of Fame)—— 跨角色的傳奇留名(純持久化工具·無 ui)。

承 R158 存檔槽位:過去傳奇模式死亡直接抹除槽位(英雄永久消失)、隱退僅存檔、`legacy.compute`
結算後即丟棄——一生功業無跨局的持久回饋。本模組把每個「走完」的角色蒸餾成一筆精簡留名,
持久化到 `~/.tesrpg/hall.json`,主選單可回顧,依傳奇分數排名。

鐵律(對齊 saves.py):
- **純持久化·無 ui·零遊戲迴圈鉤子。** 只在 `end_run` 的「終局」(隱退 / 傳奇模式死亡)被呼叫一次。
- **獨立檔案,零存檔格式變更**(不碰 GameState/Character·不加任何存檔欄)。
- **原子寫**(.tmp + replace·鏡像 GameState.save)——寫入中斷不毀既有名冊。
- **毀損/缺檔安全**:讀不到 → 視為空名冊(絕不崩啟動)。
- `HALL_PATH` 為模組全域(測試可覆寫指向暫存目錄,免污染真實 home;鏡像 saves.SAVES_DIR)。
- **依傳奇分數排名、上限 MAX_ENTRIES 筆**(有界檔案·穩定排序保平手插入序)。
"""
from __future__ import annotations

import json
from pathlib import Path

HALL_PATH = Path.home() / ".tesrpg" / "hall.json"   # 名人堂檔(測試可覆寫)
MAX_ENTRIES = 20                                     # 只留分數最高的 N 筆(有界)

_MODE_CN = {"adventure": "冒險", "legend": "傳奇"}
_ENDING_CN = {"death": "殞落", "retire": "隱退"}


def is_terminal(ending: str, game_mode: str) -> bool:
    """此結局是否「走完一生」(該留名)—— 隱退(任何模式)或傳奇模式陣亡。
    冒險模式陣亡=回上次存檔續命(非終局)→ 不留名,避免重複記錄同一角色。"""
    return ending == "retire" or (ending == "death" and game_mode == "legend")


def entry_from_legacy(legacy: dict, game_mode: str) -> dict:
    """由 legacy.compute 的結算 dict 蒸餾一筆精簡留名(不含即時時間戳 → 決定性、可測)。"""
    feats: list[str] = []
    for name, rank in legacy.get("factions", []) or []:      # 公會頭銜
        feats.append(f"{name}·{rank}")
    for key in ("condition", "lycanthropy", "dominion", "dark_deeds", "comrade"):
        v = legacy.get(key)                                  # 詛咒/血業/功業/羈絆(有則附上)
        if v:
            feats.append(str(v))
    return {
        "name": legacy.get("name", "?"),
        "race": legacy.get("race", ""), "sex": legacy.get("sex", ""),
        "birthsign": legacy.get("birthsign", ""), "class": legacy.get("class", ""),
        "playstyle": legacy.get("playstyle", ""),
        "level": int(legacy.get("level", 1)),
        "years": int(legacy.get("years", 0)), "days": int(legacy.get("days", 0)),
        "score": int(legacy.get("score", 0)),
        "title": legacy.get("title", ""),
        "ending": legacy.get("ending", "death"),
        "mode": game_mode,
        "achievements": len(legacy.get("achievements", []) or []),
        "achievements_total": int(legacy.get("achievements_total", 0)),
        "feats": feats[:5],                                  # 上限 5 條招牌功業
    }


def load_entries() -> list[dict]:
    """讀名人堂(依分數已排序);缺檔/毀損 → 空清單(絕不崩)。"""
    try:
        data = json.loads(HALL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    entries = [e for e in data if isinstance(e, dict)]
    entries.sort(key=_score, reverse=True)   # 穩定:平手保插入序
    return entries[:MAX_ENTRIES]


def _score(e: dict) -> int:
    """排序鍵:防手改/毀損檔的 score:null 或非數值(int(None) 會 TypeError → 視為 0,不崩啟動)。"""
    s = e.get("score", 0)
    return s if isinstance(s, (int, float)) else 0


def has_entries() -> bool:
    return bool(load_entries())


def record(legacy: dict, game_mode: str) -> None:
    """把一筆走完的傳奇蒸餾入名人堂(依分數插入、留 top-N、原子寫)。呼叫端須先確認 `is_terminal`。"""
    entries = load_entries()                       # 已依 _score 排序(毀損 score 安全)
    entries.append(entry_from_legacy(legacy, game_mode))
    entries.sort(key=_score, reverse=True)         # 穩定排序;新筆 score 由 entry_from_legacy 保證 int
    entries = entries[:MAX_ENTRIES]
    _atomic_write(entries)


def _atomic_write(entries: list[dict]) -> None:
    """原子寫(.tmp + replace·鏡像 GameState.save)——中斷不毀既有名冊。失敗不致命(留名非核心)。"""
    try:
        HALL_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = HALL_PATH.with_name(HALL_PATH.name + ".tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(HALL_PATH)
    except OSError:
        pass   # 留名失敗不該擋住結算/主選單流程(名人堂是加值層,非核心存檔)


def mode_cn(mode: str) -> str:
    return _MODE_CN.get(mode, "冒險")


def ending_cn(ending: str) -> str:
    return _ENDING_CN.get(ending, "殞落")
