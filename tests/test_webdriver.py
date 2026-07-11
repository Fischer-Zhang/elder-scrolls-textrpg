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
    import tempfile
    from pathlib import Path
    import tesrpg.main as gmain
    from tesrpg.systems import saves

    backend = WebBackend()
    saved = (ui.console, ui._web, ui._hud_state, ui._hud_gamedata, ui._hud_allies)
    ui.use_web_backend(backend, make_recording_console())
    # G:驅動 main() 建新角會寫槽位存檔 → 隔離到暫存目錄,免污染真實 ~/.tesrpg/saves
    from tesrpg.systems import hall
    _tmp = tempfile.TemporaryDirectory()
    _saved_saves = (saves.SAVES_DIR, saves.LEGACY_PATH)
    _saved_hall = hall.HALL_PATH                     # R160:防禦性隔離名人堂(若驅動觸及終局 end_run)
    saves.SAVES_DIR = Path(_tmp.name) / "saves"
    saves.LEGACY_PATH = Path(_tmp.name) / "save.json"
    hall.HALL_PATH = Path(_tmp.name) / "hall.json"
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
        gmain._onset_hinted = None   # daemon thread 停在 game_loop 內(_onset_hinted=set())→ 復位免洩漏到後續模組(R155)
        gmain._active_save = None    # G:main() 建新角設了活槽路徑(指向暫存)→ 復位免洩漏死路徑
        saves.SAVES_DIR, saves.LEGACY_PATH = _saved_saves
        hall.HALL_PATH = _saved_hall
        _tmp.cleanup()
    return steps, reached_game, err.get("tb")


def test_web_entry_boots_into_game_loop():
    steps, reached_game, tb = _drive()
    assert tb is None, f"web 驅動遊戲 thread 出現例外:\n{tb}"
    assert reached_game, f"驅動 {steps} 個 prompt 仍未進入遊戲主迴圈(建角/進入流程可能壞了)"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_webdriver")
