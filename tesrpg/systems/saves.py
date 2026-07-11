"""存檔槽位 / 多角色(G)—— 由單一 save.json 升級為多槽位角色名冊(純持久化工具·無 ui)。

模型:`~/.tesrpg/saves/slotN.json`(N=1..MAX_SLOTS)每槽一角色;主選單列名冊(繼續 / 新角色 /
刪除),新角色進**空槽不覆蓋**既有。存讀檔格式**完全不變**(仍 `GameState.save/load` 同一 JSON)——
本模組只管「哪個檔在哪個槽」與輕量名冊 meta;時間戳用檔案 mtime(**零存檔格式變更**)。

向後相容:舊單一 `~/.tesrpg/save.json` 於首次啟動搬成 `slot1.json`(`migrate_legacy`),既有玩家的
存檔自動成為槽位 1。SAVES_DIR 為模組全域(測試可覆寫指向暫存目錄,免污染真實 home)。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path.home() / ".tesrpg"
SAVES_DIR = _ROOT / "saves"              # 槽位存檔目錄(測試可覆寫)
LEGACY_PATH = _ROOT / "save.json"        # 舊單一存檔(遷移來源)
MAX_SLOTS = 8

_MODE_CN = {"adventure": "冒險", "legend": "傳奇"}
_SLOT_RE = re.compile(r"slot(\d+)\.json$")


def slot_path(n: int) -> Path:
    return SAVES_DIR / f"slot{n}.json"


def migrate_legacy() -> None:
    """一次性遷移:舊 `save.json` → `saves/slot1.json`(僅當 slot1 尚不存在)。冪等·安全·不致命。"""
    if not (LEGACY_PATH.exists() and not slot_path(1).exists()):
        return
    try:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)   # mkdir 亦納入 try:權限/非目錄佔位失敗不崩啟動
        LEGACY_PATH.replace(slot_path(1))              # 同檔案系統 → 原子搬移
    except OSError:
        try:                                           # 跨檔案系統(EXDEV)等 → 複製後刪,仍讓舊角進名冊
            import shutil
            shutil.copy2(LEGACY_PATH, slot_path(1))
            LEGACY_PATH.unlink(missing_ok=True)
        except OSError:
            pass                                       # 仍失敗:舊檔留著(不進名冊但不遺失·下次啟動再試)


def used_slots() -> list[int]:
    """現有槽位編號(遞增)。目錄不存在 → 空。"""
    if not SAVES_DIR.exists():
        return []
    ns = []
    for p in SAVES_DIR.iterdir():
        m = _SLOT_RE.search(p.name)
        if m and p.is_file():
            ns.append(int(m.group(1)))
    return sorted(ns)


def next_free_slot() -> int | None:
    """最小未使用槽位(1..MAX_SLOTS);全滿回 None。"""
    used = set(used_slots())
    for n in range(1, MAX_SLOTS + 1):
        if n not in used:
            return n
    return None


def slot_meta(n: int, gamedata) -> dict | None:
    """輕量讀取一槽的名冊資訊(不建完整 GameState):name/level/province/mode/day/mtime。
    毀損/不可讀 → 回帶 `corrupt:True` 的佔位(仍可在名冊顯示並讓玩家刪除)。不存在 → None。"""
    p = slot_path(n)
    if not p.exists():
        return None
    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = 0.0
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        pl = d.get("player", {}) or {}
        loc = pl.get("location_id")
        prov = (gamedata.world["locations"].get(loc, {}) or {}).get("province", "?") if loc else "?"
        return {"slot": n, "name": pl.get("name", "?"), "level": int(pl.get("level", 1)),
                "province": prov, "mode": d.get("game_mode", "adventure"),
                "mode_cn": _MODE_CN.get(d.get("game_mode", "adventure"), "冒險"),
                "day": (d.get("time") or {}).get("day"), "mtime": mtime, "corrupt": False}
    except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
        return {"slot": n, "name": "(毀損存檔)", "level": 0, "province": "", "mode": "",
                "mode_cn": "", "day": None, "mtime": mtime, "corrupt": True}


def roster(gamedata) -> list[dict]:
    """名冊:每個現有槽位的 meta(按槽位序)。"""
    return [m for n in used_slots() if (m := slot_meta(n, gamedata)) is not None]


def delete_slot(n: int) -> None:
    slot_path(n).unlink(missing_ok=True)
