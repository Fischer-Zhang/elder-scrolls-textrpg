"""R201:畫面殘留(舊幀)面板列不得接管之後選單的同 key 選項(R199 D5「選單 key 相撞掃描」收尾)。

R199 審查 major:前端 `wireActionableRows` 讓畫面上帶 data-key 的面板列「接管」key 相同的選單選項(移除選項按鈕、標籤消失)。
純敘事 / 純選單幀不重畫 #screen → 殘留的舊面板仍在 → 行竊選單用裸物品 id 當 key 時,「得手 N%」整個被殘留買貨面板蓋掉
(當時只對行竊加 `steal:` 命名空間,其餘「未掃」)。

R201 掃描結果(出處:掃描當下的一次性動態掃描 + grep / 讀碼;入庫的只有下方守衛):
  ① 動態:tests/_stale_scan.py 以真 WebBackend 驅動真 game_loop 做覆蓋導向隨機走訪。掃描當下以一次性參數跑 30 趟 × 600 提示
     (11 職業 × 10 種族輪替,未入庫);入庫守衛固定為 8 趟 × 500 提示、固定種子。→ 除已修的行竊外沒有任何殘留相撞;
     唯一的殘留類別是地城方位格 go:*(導航列,不移除按鈕,設計上跨幀有效)。
  ② 靜態:`ui.menu(` 在 tesrpg/ 內共 134 處呼叫、全在 main.py(grep 可重現);帶 data-key 列的面板只有 inventory / shop /
     board / location / combat / dungeon_grid / origins;game_loop 每圈頂端無條件重畫 location_panel,殘留面板活不過一個
     action 函式(inventory / shop / board 各自的後續選單 key 都不與其列相撞)→ 現況零相撞。
  → 結構性防線:前端只接管「本幀重畫」的列(go:* 例外)。未來新增裸 id 選單即使撞 key,也不會被殘留面板蓋掉。

🔴 本檔守衛:
  1. 掃描器鏡像(Screen)對 FRESH / STALE / 導航列 / 清屏的分類(合成幀,不靠隨機覆蓋);next_frame 對「遊戲結束 / 卡住」的分辨
  2. 掃描器的欄位表 ROW_FIELDS ↔ index.html 的 VIEWS / data-key 來源逐一對帳(含「JS 動態建構 data-key」盲區守衛)
  3. 動態掃描:無殘留相撞(排除 go:*)+ 非空轉(FRESH 事件涵蓋 location / inventory / shop / combat / dungeon_grid)。
     角色死亡(走訪提早結束)是正常收尾,不算失敗:只要求總提示數夠多 + 無例外 + 無卡住
  4. 前端規則的原始碼哨兵(真行為由 tests/browser_ui.py 的 Chromium 回歸驗證)
子進程跑動態掃描:整套測試共用同一進程,既有模組(如 test_m13)會把 ui.menu 換成假函式且不還原(見 R199 同款說明)。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import _stale_scan as scan   # noqa: E402

INDEX_HTML = ROOT / "tesrpg" / "web" / "static" / "index.html"


def _menu(*keys, extra=()):
    return {"type": "menu", "title": "t", "options": [{"key": k, "label": k} for k in keys], "extra_keys": list(extra)}


def _view(name, data):
    return {"kind": "view", "name": name, "data": data}


def test_screen_mirror_classifies_fresh_stale_navigation_and_clear():
    s = scan.Screen()
    inv = _view("inventory", {"items": [{"key": "iron_sword"}, {"key": "healing_potion"}]})
    # 同幀面板 + 同幀選單 → FRESH(設計意圖:列接管選項)
    kind, hit, views = s.feed([inv], _menu("iron_sword", "healing_potion", "back"))
    assert (kind, hit, views) == ("FRESH", ["healing_potion", "iron_sword"], ("inventory",))
    # 純敘事幀(只有 log 塊)+ 同 key 選單 → STALE(R199 bug 的成因)
    kind, hit, views = s.feed([{"kind": "log", "html": "x"}], _menu("iron_sword", "steal:iron_sword"))
    assert (kind, hit, views) == ("STALE", ["iron_sword"], ("inventory",))
    # 命名空間不同(steal:iron_sword)→ 不相撞
    assert s.feed([], _menu("steal:iron_sword", "steal:healing_potion")) is None
    # extra_keys 也算(前端把 extra_keys 視為合法 key)
    assert s.feed([], _menu("x", extra=("healing_potion",)))[1] == ["healing_potion"]
    # clear 塊 → #screen 清空 → 之後選單不再相撞
    assert s.feed([{"kind": "clear"}], _menu("iron_sword")) is None
    assert s.feed([], _menu("iron_sword")) is None
    # 導航列:地城方位格(move 欄)→ 殘留仍歸 STALE,但 key 全是 go:*(測試 3 以此排除)
    grid = _view("dungeon_grid", {"rows": [[{"move": "go:n"}, {"move": None}, {"move": "go:e"}]]})
    assert s.feed([grid], _menu("go:n", "go:e", "leave"))[0] == "FRESH"
    kind, hit, views = s.feed([], _menu("go:n", "go:e", "leave"))
    assert kind == "STALE" and hit == ["go:e", "go:n"] and views == ("dungeon_grid",)
    # 非選單 prompt(int / confirm / text)沒有選項 → 不相撞
    assert s.feed([inv], {"type": "int", "lo": 1, "hi": 3}) is None


def test_scanner_row_fields_match_every_front_end_data_key_source():
    """ROW_FIELDS ↔ index.html:凡 renderXxx 會輸出 data-key 的 view,都得在掃描器欄位表裡且欄位名相符;反之亦然。"""
    html = INDEX_HTML.read_text(encoding="utf-8")
    views_block = re.search(r"const VIEWS = \{(.*?)\};", html, re.S).group(1)
    fn_of_view = dict(re.findall(r"(\w+):\s*(render\w+)", views_block))
    assert len(fn_of_view) >= 20, "解析 VIEWS 表失敗(結構變了?)"
    starts = [(m.group(1), m.start()) for m in re.finditer(r"^  function (render\w+)\(", html, re.M)]
    body_of = {}
    for i, (name, pos) in enumerate(starts):
        body_of[name] = html[pos:(starts[i + 1][1] if i + 1 < len(starts) else len(html))]
    fields = {}
    for view, fn in fn_of_view.items():
        body = body_of.get(fn, "")
        if "data-key=" in body:
            fields[view] = set(re.findall(r'data-key="\$\{esc\(\w+\.(\w+)\)\}"', body))
    assert fields, "前端沒找到任何 data-key 來源?(解析失敗)"
    assert set(fields) == set(scan.ROW_FIELDS), (
        "前端帶 data-key 的 view 與掃描器 ROW_FIELDS 不一致(新面板要補進 tests/_stale_scan.py 的 ROW_FIELDS,"
        f"否則掃描有盲區):前端={sorted(fields)} 掃描器={sorted(scan.ROW_FIELDS)}")
    for view, fs in fields.items():
        assert fs == {scan.ROW_FIELDS[view]}, (view, fs, scan.ROW_FIELDS[view])
    # 盲區守衛(R201 審查 nit):上面只看得見樣板字串裡的 data-key="${esc(x.field)}";若改由 JS 動態建構
    # (setAttribute / dataset),對帳會悄悄漏掉 → 直接擋下,逼你把新來源補進掃描器。
    assert not re.search(r"""setAttribute\(\s*["']data-key["']""", html), "data-key 改由 setAttribute 建構:掃描器看不到,請補 ROW_FIELDS 並更新對帳"
    assert not re.search(r"\.dataset\.key\s*=", html), "data-key 改由 dataset.key 建構:掃描器看不到,請補 ROW_FIELDS 並更新對帳"


class _FakeThread:
    def __init__(self, alive):
        self._alive = alive

    def is_alive(self):
        return self._alive


class _FakeBackend:
    def __init__(self, frames=()):
        import queue
        self.outbound = queue.Queue()
        for f in frames:
            self.outbound.put(f)


def test_next_frame_tells_game_over_from_a_hang():
    """R201 審查 minor:角色死亡 → game_loop 正常 return、遊戲 thread 結束,不會再有幀。舊掃描器把這當 timeout(且空等 8 秒)。"""
    frame = {"prompt": {"type": "menu"}}
    assert scan.next_frame(_FakeBackend([frame]), _FakeThread(True)) is frame           # 有幀就回幀
    assert scan.next_frame(_FakeBackend([frame]), _FakeThread(False)) is frame          # thread 已結束但還有殘幀 → 先吐出
    assert scan.next_frame(_FakeBackend(), _FakeThread(False)) == "over"                # 結束且無幀 = 正常收尾
    assert scan.next_frame(_FakeBackend(), _FakeThread(True), limit=0.5) == "timeout"   # 還活著卻沒幀 = 卡住


def _run_scan(walks=8, prompts=500, seed0=100):
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, HOME=home, PYTHONHASHSEED="0")        # HOME 隔離:絕不碰真實 ~/.tesrpg
        out = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "_stale_scan.py"), "--json",
             "--walks", str(walks), "--prompts", str(prompts), "--seed0", str(seed0)],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=240)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_no_stale_panel_row_collides_with_a_later_menu_option():
    res = _run_scan()
    for w in res["walks"]:
        assert w["exception"] is None, (w["seed"], (w["exception"] or "")[-600:])
        # over = 遊戲 thread 正常結束(角色死亡等,屬正常收尾);timeout = thread 還活著卻無新幀 = 卡住
        assert w["end"] in ("cap", "over", "end"), ("走訪卡住或例外 → 掃描不完整", w)
    total = sum(w["prompts"] for w in res["walks"])
    assert total >= 2000, ("走訪總提示數過少(多趟提早死亡?)→ 掃描空轉;可調大 walks 或換 seed0", total,
                           [(w["seed"], w["prompts"], w["end"]) for w in res["walks"]])
    # 殘留相撞只允許導航列 go:*(地城方位格);任何非導航 key 相撞 = 選項標籤會被殘留面板蓋掉
    bad = [e for e in res["events"] if e["kind"] == "STALE" and e["other"]]
    assert not bad, f"殘留面板列接管了選單選項(R199 同類 bug):{bad}"
    # 非空轉:掃描真的看到了各種面板的「同幀接管」(證明鏡像與走訪有在運作)
    fresh_views = {v for e in res["events"] if e["kind"] == "FRESH" for v in e["views"]}
    need = {"location", "inventory", "shop", "combat", "dungeon_grid"}
    assert need <= fresh_views, (f"掃描沒覆蓋到 {sorted(need - fresh_views)}(走訪覆蓋退化,或面板輸出變了;"
                                 "可調大 walks / prompts 或換 seed0)")


def test_front_end_wires_only_rows_drawn_this_frame_source_sentinel():
    """前端規則哨兵:wireActionableRows 吃 redrawn 參數(= 本幀帶 view/html/clear 狀態塊);僅 redrawn 或 go:* 列可被接管。
    (參數刻意不叫 fresh:render() 內已有日誌用的 `fresh`,語意不同。)
    真行為(殘留列不接管 / 導航列例外)由 tests/browser_ui.py 的 Chromium 回歸驗。"""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert re.search(r"function wireActionableRows\(\s*spec\s*,\s*redrawn\s*\)", html)
    assert re.search(r"wireActionableRows\(\s*frame\.prompt\s*,\s*stateBlocks\.length\s*>\s*0\s*\)", html)
    assert re.search(r'\(\s*redrawn\s*\|\|\s*k\.indexOf\("go:"\)\s*===\s*0\s*\)', html)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r201_stale_rows")
