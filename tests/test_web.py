"""Web 後端 + console seam 測試(不需 pip、不跑瀏覽器、不跑整個 main())。

驗證:5 個輸入原語在 web 模式產生正確 spec 並 round-trip;畫面 HTML 是裸 <span>
片段(code_format 生效、無 <!DOCTYPE);雙擊/亂序 prompt_id 被擋;越界整數重新詢問;
flush_final 出 end 哨兵;generation 遞增。

**鐵律**:測試結束務必還原 ui._web=None / ui.console,以免污染後續測試模組。"""

import importlib
import io
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

from tesrpg.ui import console as ui
from tesrpg.web.backend import WebBackend, _validate


def _rec():
    return Console(record=True, file=io.StringIO(), width=100)


def _restore():
    ui._web = None
    ui.console = Console()


def _drive(backend, call, answer_for):
    """在 thread 跑阻塞的 ui.* 呼叫,讀出 frame、作答、回傳 (frame, 呼叫結果)。"""
    import queue as _q
    box = {}

    def worker():
        try:
            box["v"] = call()
        except BaseException as e:        # noqa: surface worker error to main thread
            box["exc"] = e

    t = threading.Thread(target=worker)
    t.start()
    try:
        frame = backend.outbound.get(timeout=5)
    except _q.Empty:
        t.join(0.5)
        raise AssertionError("輸入原語未送出 frame;worker 例外=%r" % box.get("exc"))
    ans = answer_for(frame["prompt"])
    assert backend.submit(frame["prompt_id"], ans), "submit 被拒"
    t.join(timeout=5)
    if "exc" in box:
        raise box["exc"]
    assert not t.is_alive(), "呼叫未返回(疑似死鎖)"
    return frame, box.get("v")


def test_validate():
    assert _validate({"type": "confirm"}, True) == (True, True)
    assert _validate({"type": "int", "lo": 1, "hi": 24}, 8) == (True, 8)
    assert _validate({"type": "int", "lo": 1, "hi": 24}, 99)[0] is False
    assert _validate({"type": "int", "lo": 1, "hi": 24}, "x")[0] is False
    assert _validate({"type": "text"}, None) == (True, "")
    assert _validate({"type": "menu", "options": [{"key": "a"}], "allow_back": True}, None) == (True, None)
    assert _validate({"type": "menu", "options": [{"key": "a"}], "allow_back": False}, None)[0] is False
    assert _validate({"type": "menu", "options": [{"key": "a"}]}, "a") == (True, "a")
    assert _validate({"type": "menu", "options": [{"key": "a"}]}, "zzz")[0] is False


def test_seam_roundtrip():
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        fr, v = _drive(backend, lambda: ui.menu("選擇", [("k1", "選項一"), ("k2", "選項二")]),
                       lambda s: "k2")
        assert fr["prompt"]["type"] == "menu" and v == "k2"
        assert [o["key"] for o in fr["prompt"]["options"]] == ["k1", "k2"]
        assert fr["prompt"]["title"] == "選擇"

        _, v = _drive(backend, lambda: ui.menu("X", [("k", "l")], allow_back=True), lambda s: None)
        assert v is None      # 返回

        fr, v = _drive(backend,
                       lambda: ui.grouped_menu("要做什麼?", [("冒險", [("travel", "旅行")]), ("空", [])]),
                       lambda s: "travel")
        assert fr["prompt"]["type"] == "grouped" and v == "travel"
        assert len(fr["prompt"]["groups"]) == 1          # 空分組自動略過

        _, v = _drive(backend, lambda: ui.confirm("確定?"), lambda s: True)
        assert v is True
        _, v = _drive(backend, lambda: ui.confirm("確定?"), lambda s: False)
        assert v is False

        _, v = _drive(backend, lambda: ui.ask_int("幾小時?", 8, 1, 24), lambda s: 12)
        assert v == 12
        _, v = _drive(backend, lambda: ui.ask_text("姓名", default="阿"), lambda s: "貝")
        assert v == "貝"
    finally:
        _restore()


def test_blocks_protocol():
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        ui.message("[gold1]測試訊息[/]")                 # 已轉原生 → log block(彩色文字行)
        fr, _ = _drive(backend, lambda: ui.menu("X", [("k", "l")]), lambda s: "k")
        logs = [b["html"] for b in fr["blocks"] if b["kind"] == "log"]
        assert logs and "<span" in logs[0]                       # rich 標記→彩色 span
        assert "<!DOCTYPE" not in logs[0] and "<html" not in logs[0]   # code_format 生效
    finally:
        _restore()


def test_view_block():
    """轉為原生的面板(status)→ 發出 view block(name+data),非 html 截圖。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="dunmer", birthsign="lady", class_id="knight")
    st = GameState(player=c, time=GameTime(), rng=RNG(3))
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__("v", ui.confirm("?")))
        ui.status_line(st)          # 應發 view block,不印 html
        t.start()
        fr = backend.outbound.get(timeout=5)
        views = [b for b in fr["blocks"] if b["kind"] == "view"]
        assert any(b["name"] == "status" for b in views), fr["blocks"]
        sv = next(b["data"] for b in views if b["name"] == "status")
        assert sv["name"] == "測" and len(sv["hp"]) == 2 and "level" in sv
        backend.submit(fr["prompt_id"], True); t.join(timeout=5)
    finally:
        _restore()


def test_double_submit_and_stale():
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__("v", ui.confirm("?")))
        t.start()
        fr = backend.outbound.get(timeout=5)
        pid = fr["prompt_id"]
        assert backend.submit(pid, True) is True
        assert backend.submit(pid, True) is False         # 雙擊被擋
        assert backend.submit(pid + 5, True) is False      # 亂序 pid 被擋
        t.join(timeout=5)
        assert box["v"] is True
    finally:
        _restore()


def test_int_revalidate():
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__("v", ui.ask_int("?", 8, 1, 24)))
        t.start()
        fr1 = backend.outbound.get(timeout=5)
        assert backend.submit(fr1["prompt_id"], 99) is True   # 投遞成功但越界 → 重新詢問
        fr2 = backend.outbound.get(timeout=5)
        assert fr2["prompt_id"] != fr1["prompt_id"]
        assert backend.submit(fr2["prompt_id"], 10) is True
        t.join(timeout=5)
        assert box["v"] == 10
    finally:
        _restore()


def test_flush_final_and_generation():
    backend = WebBackend()
    g1 = backend.new_generation()
    g2 = backend.new_generation()
    assert g2 == g1 + 1
    backend.flush_final("<span>bye</span>")
    fr = backend.outbound.get(timeout=2)
    assert fr["prompt"]["type"] == "end"
    assert any(b["kind"] == "html" and "bye" in b["html"] for b in fr["blocks"])
    assert fr["seq"] > 0


def run():
    # 其他測試模組(test_m12/m13 等)在 import 時就把 ui.menu 換成 stub 並未還原;
    # reload 還原真正的 5 個輸入原語,確保此處測到的是 web seam 而非別人的 stub。
    importlib.reload(ui)
    test_validate()
    test_seam_roundtrip()
    test_blocks_protocol()
    test_view_block()
    test_double_submit_and_stale()
    test_int_revalidate()
    test_flush_final_and_generation()
    _restore()


if __name__ == "__main__":
    run()
    print("✓ test_web")
