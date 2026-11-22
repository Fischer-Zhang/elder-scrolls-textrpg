"""R201 殘留面板接管掃描器(測試支援模組;檔名帶底線 → 不被 run_all 自動探索)。

要防的 bug(R199 審查 major):前端 `wireActionableRows` 會讓畫面上帶 data-key 的面板列「接管」key 相同的選單選項
(移除選項按鈕、標籤消失)。畫面上殘留的**舊幀**面板(純敘事 / 純選單幀不重畫 #screen)與新選單內容無關 →
行竊選單用裸物品 id 當 key 時,每件的「得手 N%」整個被殘留買貨面板蓋掉。

本模組用**真 WebBackend 驅動真 `game_loop`**,以覆蓋導向隨機走訪(固定種子 → 可重現),逐幀記錄
「#screen 上的列 key ∩ 當前 prompt 選項 key」,並依該列是否來自**本幀**分兩類:
  FRESH  同幀面板 + 同幀選單(設計意圖:背包 / 商店 / 戰鬥 / 地點卡 / 告示板列接管同幀選單)
  STALE  畫面上殘留的舊幀面板列(R199 bug 的成因;R201 前端已不接管,見 index.html wireActionableRows)

前端語意(index.html render / renderScreen):幀內帶 view / html / clear 狀態塊 → #screen 整個重畫成這些塊;
否則保留前畫面。列 key 的來源欄位對照各 renderXxx 的 data-key(ROW_FIELDS)。

用法(請在子進程跑,HOME 隔離):
    HOME=$(mktemp -d) PYTHONHASHSEED=0 python3 tests/_stale_scan.py [--walks N] [--prompts M] [--seed0 S] [--json]
"""
from __future__ import annotations

import argparse
import collections
import json
import queue
import random
import re
import sys
import tempfile
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 前端各 renderXxx 實際輸出 data-key 的資料欄位(index.html:地點出口 e.key / 戰場卡 c.key / 背包·商店列 it.key /
# 告示板委託卡 q.key / 地城格 c.move / 開局一覽 o.id)。新增「帶 data-key 的面板」時這裡要補,否則本掃描看不到它
# (tests/test_r201_stale_rows.py 有對帳測試:此表 ↔ index.html 的 VIEWS / data-key 逐一相符)。
ROW_FIELDS = {"location": "key", "combat": "key", "inventory": "key", "shop": "key",
              "board": "key", "dungeon_grid": "move", "origins": "id"}
# 隨機走訪避開會結束 / 刪除的選項(存檔與名人堂已隔離到暫存目錄,仍避免走訪過早結束)
AVOID_KEYS = ("quit", "retire", "delete", "del:")


def _collect(obj, field: str, out: set) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == field and isinstance(v, str) and v:
                out.add(v)
            else:
                _collect(v, field, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, field, out)


def frame_rows(blocks: list) -> dict:
    """這一組狀態塊在 #screen 上會長出的列 key → {view 名}。"""
    rows: dict = {}
    for b in blocks:
        if b["kind"] == "view" and b["name"] in ROW_FIELDS:
            keys: set = set()
            _collect(b["data"], ROW_FIELDS[b["name"]], keys)
            for k in keys:
                rows.setdefault(k, set()).add(b["name"])
    return rows


class Screen:
    """前端 #screen 的伺服端鏡像(只追蹤「帶 data-key 的列」)。"""

    def __init__(self) -> None:
        self.rows: dict = {}

    def feed(self, blocks: list, spec: dict):
        """餵入一幀。回 None(沒有任何列 key 與選項相撞)或 (kind, hit, views):
        kind=FRESH(列來自本幀)/ STALE(殘留的舊幀列);hit=相撞的 key(排序);views=那些列所屬的 view 名。"""
        state_blocks = [b for b in blocks if b["kind"] in ("view", "html", "clear")]
        fresh = bool(state_blocks)
        if fresh:                                          # 前端 renderScreen:有狀態塊 → #screen 整個重畫
            self.rows = frame_rows(state_blocks)
        keys, extra = prompt_keys(spec)
        hit = sorted(k for k in set(keys) | set(extra) if k in self.rows)
        if not hit:
            return None
        return ("FRESH" if fresh else "STALE", hit, tuple(sorted({v for k in hit for v in self.rows[k]})))


def prompt_keys(spec: dict) -> tuple[list, list]:
    """(選項 key 清單, extra_keys 清單);非選單 prompt 回空。"""
    t = spec.get("type")
    if t == "menu":
        opts = spec.get("options", [])
    elif t == "grouped":
        opts = [o for g in spec.get("groups", []) for o in g.get("options", [])]
    else:
        return [], []
    return ([o["key"] for o in opts if isinstance(o.get("key"), str)],
            [k for k in spec.get("extra_keys", []) if isinstance(k, str)])


def _choose(spec: dict, rng: random.Random, seen: collections.Counter, title: str):
    """覆蓋導向:同一選單少試過的選項權重高;偶爾返回 / 點 extra_keys(地點出口等可點列)。"""
    t = spec.get("type")
    if t in ("menu", "grouped"):
        keys, extra = prompt_keys(spec)
        pool = [k for k in keys if not any(s in k for s in AVOID_KEYS)]
        back_ok = bool(spec.get("allow_back"))
        r = rng.random()
        if back_ok and r < 0.18:
            return None
        if extra and r < 0.25:
            return rng.choice(extra)
        if not pool:
            return None if back_ok else (keys[0] if keys else (extra[0] if extra else None))
        k = rng.choices(pool, [1.0 / (1 + seen[(title, k)]) ** 2 for k in pool])[0]
        seen[(title, k)] += 1
        return k
    if t == "confirm":
        return rng.random() < 0.6
    if t == "int":
        lo, hi = spec.get("lo", 0), spec.get("hi", 0)
        return rng.choice([lo, hi, min(hi, lo + 1), spec.get("default", lo)]) if hi >= lo else lo
    if t == "text":
        return "掃描者"
    return None


def _make_state(gd, seed: int, class_id: str, race: str, start: str):
    from tesrpg.creation import build_character
    from tesrpg.rng import RNG
    from tesrpg.state import GameState, GameTime
    from tesrpg.systems import inventory, stats

    rng = random.Random(seed)
    c = build_character(gd, name=f"掃描{seed}", sex="male", race=race, birthsign="warrior", class_id=class_id)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.gold = 30000
    by_type: dict = collections.defaultdict(list)
    for iid in gd.items:                                   # 每種類型塞幾件 → 背包 / 賣貨 / 附魔 / 煉金選單都有料
        by_type[str(gd.item(iid).get("type", "?"))].append(iid)
    for ids in by_type.values():
        for iid in rng.sample(ids, min(4, len(ids))):
            inventory.add_item(c, iid, rng.choice((1, 1, 2, 3)))
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.fatigue = c.max_fatigue
    c.location_id = start
    return GameState(player=c, time=GameTime(), rng=RNG(seed))


def _heal(st) -> None:
    c = st.player
    for cur, mx in (("health", "max_health"), ("fatigue", "max_fatigue"), ("magicka", "max_magicka")):
        if hasattr(c, cur) and hasattr(c, mx):
            setattr(c, cur, getattr(c, mx))


def next_frame(backend, thread, limit: float = 8.0):
    """等下一幀。回幀 dict;遊戲 thread 已結束且無殘幀 → "over"(角色死亡等正常收尾,不是卡死);
    thread 還活著卻逾時 → "timeout"(真的卡住)。"""
    waited = 0.0
    while waited < limit:
        try:
            return backend.outbound.get(timeout=0.2)
        except queue.Empty:
            waited += 0.2
            if not thread.is_alive():
                try:
                    return backend.outbound.get_nowait()   # thread 結束前最後一刻才放進去的幀
                except queue.Empty:
                    return "over"
    return "timeout"


def walk(gd, seed: int, class_id: str, race: str, start: str, max_prompts: int, agg: dict) -> dict:
    """驅動一趟隨機走訪;把相撞事件累加進 agg;回傳該趟摘要。"""
    from tesrpg import main as game_main
    from tesrpg.systems import hall, saves
    from tesrpg.ui import console as ui
    from tesrpg.web.backend import WebBackend
    from tesrpg.web.server import make_recording_console

    rng = random.Random(seed * 7919 + 13)
    backend = WebBackend()
    ui.use_web_backend(backend, make_recording_console())
    tmp = tempfile.TemporaryDirectory()                    # 存檔 / 名人堂隔離(R160 同款);不碰 ~/.tesrpg
    saves.SAVES_DIR = Path(tmp.name) / "saves"
    saves.LEGACY_PATH = Path(tmp.name) / "save.json"
    hall.HALL_PATH = Path(tmp.name) / "hall.json"
    game_main._onset_hinted = None
    game_main._active_save = None
    st = _make_state(gd, seed, class_id, race, start)
    err: dict = {}

    def run() -> None:
        try:
            game_main.game_loop(st, gd)
        except SystemExit:
            pass
        except BaseException:
            err["tb"] = traceback.format_exc()

    game = threading.Thread(target=run, daemon=True)
    game.start()
    screen = Screen()
    seen: collections.Counter = collections.Counter()
    steps, why = 0, "cap"
    while True:
        fr = next_frame(backend, game)
        if err.get("tb"):
            why = "exception"
            break
        if isinstance(fr, str):                            # "over" = 遊戲 thread 正常結束(角色死亡等)/ "timeout" = 卡住
            why = fr
            break
        spec = fr.get("prompt", {})
        if spec.get("type") == "end":
            why = "end"
            break
        if steps >= max_prompts:                           # 到上限就**不作答**:遊戲 thread 永遠停在此 prompt 的 inbound.get(),
            break                                          # 下一趟換掉全域 ui._web 後它也不會闖進新 backend(R201 審查推測項)
        title = re.sub(r"\d+", "N", str(spec.get("title", "")))[:40]
        obs = screen.feed(fr.get("blocks", []), spec)
        if obs:
            kind, hit, views = obs
            other = [k for k in hit if not k.startswith("go:")]             # go:* = 導航列(地點出口 / 地城方位格)
            rec = agg.setdefault((kind, views, title), {"n": 0, "keys": hit[:4], "other": []})
            rec["n"] += 1
            rec["other"] = sorted(set(rec["other"]) | set(other))[:4]       # 非導航列相撞 = 真正會蓋掉選項標籤的
        ans = _choose(spec, rng, seen, title)
        _heal(st)
        backend.submit(fr["prompt_id"], ans)
        steps += 1
    tmp.cleanup()
    return {"seed": seed, "class": class_id, "race": race, "start": start, "prompts": steps, "end": why,
            "exception": err.get("tb")}


def scan(walks: int = 8, max_prompts: int = 500, seed0: int = 100) -> dict:
    from tesrpg.gamedata import get_gamedata
    from tesrpg.systems import world

    gd = get_gamedata()
    classes, races = list(gd.classes), list(gd.races)
    cities = [loc for loc in gd.world["locations"] if world.merchant_catalog(gd, loc)]
    dungeons = [loc for loc, d in gd.world["locations"].items() if d.get("type") == "dungeon"]
    agg: dict = {}
    runs = []
    for i in range(walks):
        pool = cities if i % 2 == 0 else dungeons          # 單數趟從地城起走 → 地城格 / 戰鬥 / 地城選單
        start = pool[(seed0 + i) % len(pool)]
        runs.append(walk(gd, seed0 + i, classes[i % len(classes)], races[i % len(races)], start, max_prompts, agg))
    events = [{"kind": k, "views": list(v), "title": t, **rec} for (k, v, t), rec in sorted(agg.items())]
    return {"walks": runs, "events": events}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--walks", type=int, default=8)
    ap.add_argument("--prompts", type=int, default=500)
    ap.add_argument("--seed0", type=int, default=100)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = scan(a.walks, a.prompts, a.seed0)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return
    for w in res["walks"]:
        print(f"walk seed={w['seed']} {w['class']}/{w['race']} @{w['start']}: {w['prompts']} prompts, end={w['end']}")
    print("\n=== 面板列 ∩ 選單選項(FRESH=同幀接管·設計意圖 / STALE=殘留舊幀)===")
    for e in sorted(res["events"], key=lambda e: (e["kind"], -e["n"])):
        print(f"{e['kind']:5} views={','.join(e['views']):22} n={e['n']:4} "
              f"prompt={e['title']!r} keys={e['keys']} non_nav={e['other']}")
    for w in res["walks"]:
        if w["exception"]:
            print(f"\n!!! exception seed={w['seed']}\n{w['exception'][-1500:]}")


if __name__ == "__main__":
    main()
