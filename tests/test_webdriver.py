"""Web-only 進入路徑的無頭回歸煙霧(終端版移除後)。

用 `WebBackend` + `make_recording_console()` 自動作答驅動真正的 `main()` 遊戲迴圈,
確認:建角流程全程不碰已移除的終端 stdin 分支、無例外,並順利進入遊戲主迴圈。
驅動在背景 daemon thread;偵測到遊戲主迴圈選單即停手(讓 thread 停在該 prompt 的
`inbound.get()`),再還原 `ui` 模組全域,避免污染其他測試模組(它們依賴 `_web is None`)。
"""

import queue
import threading
import traceback

from tesrpg.ui import console as ui
from tesrpg.web.backend import WebBackend
from tesrpg.web.server import make_recording_console

_GAME_KEYS = ("travel", "explore", "rest", "practice")   # 遊戲主迴圈才有的行動 key


def _pick(spec: dict):
    """對任一 prompt 規格給一個合法答案(偏好快速開始以最快進入遊戲)。"""
    ty = spec.get("type")
    if ty == "menu":
        opts = spec.get("options", [])
        for o in opts:
            if any(s in o["key"] for s in ("quick", "qs", "start")):
                return o["key"]
        return opts[0]["key"] if opts else None
    if ty == "grouped":
        for g in spec.get("groups", []):
            if g.get("options"):
                return g["options"][0]["key"]
        ek = spec.get("extra_keys", [])
        return ek[0] if ek else None
    if ty == "confirm":
        return True
    if ty == "int":
        return spec.get("default", spec.get("lo", 0))
    if ty == "text":
        return "WebDriver"
    return None


def _drive(max_prompts: int = 150, frame_timeout: float = 5.0):
    import tesrpg.main as gmain

    backend = WebBackend()
    saved = (ui.console, ui._web, ui._hud_state, ui._hud_gamedata, ui._hud_allies)
    ui.use_web_backend(backend, make_recording_console())
    err: dict = {}

    def _run():
        try:
            gmain.main()
        except SystemExit:
            pass
        except Exception:
            err["tb"] = traceback.format_exc()

    threading.Thread(target=_run, daemon=True).start()
    steps = 0
    reached_game = False
    try:
        while steps < max_prompts:
            try:
                frame = backend.outbound.get(timeout=frame_timeout)
            except queue.Empty:
                break
            spec = frame.get("prompt", {})
            if spec.get("type") == "end":
                break
            if spec.get("type") in ("menu", "grouped"):
                keys = [o["key"] for o in spec.get("options", [])] + \
                       [o["key"] for g in spec.get("groups", []) for o in g.get("options", [])]
                if any(k in _GAME_KEYS for k in keys):
                    reached_game = True
                    break                      # 不作答 → 遊戲 thread 停在此 prompt,可安全還原全域
            backend.submit(frame["prompt_id"], _pick(spec))
            steps += 1
            if err.get("tb"):
                break
    finally:
        ui.console, ui._web, ui._hud_state, ui._hud_gamedata, ui._hud_allies = saved
    return steps, reached_game, err.get("tb")


def test_web_entry_boots_into_game_loop():
    steps, reached_game, tb = _drive()
    assert tb is None, f"web 驅動遊戲 thread 出現例外:\n{tb}"
    assert reached_game, f"驅動 {steps} 個 prompt 仍未進入遊戲主迴圈(建角/進入流程可能壞了)"


def run():
    test_web_entry_boots_into_game_loop()


if __name__ == "__main__":
    run()
    print("✓ test_webdriver")
