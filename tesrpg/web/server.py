"""stdlib-only web server + launcher(零 pip 依賴)。

GET /         → 單一靜態頁(index.html)
GET /events   → SSE,串流每一幀 {seq, prompt_id, screen_html, prompt}
POST /input   → {prompt_id, value} → backend.submit

launch():接好 console 的 web backend、起 server thread + 遊戲 thread
(`try: main() finally: flush_final()`),開瀏覽器。
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .backend import WebBackend

WIDTH = 100                          # 固定 record 寬度(走 console.py:91 寬版血條)
_STATIC = os.path.join(os.path.dirname(__file__), "static", "index.html")


def _make_handler(backend: WebBackend, index_html: bytes):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):       # 靜音 access log
            pass

        # --- GET ----------------------------------------------------------
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send_bytes(200, "text/html; charset=utf-8", index_html)
            elif self.path == "/events":
                self._serve_events()
            else:
                self._send_bytes(404, "text/plain; charset=utf-8", b"not found")

        def _serve_events(self):
            gen = backend.new_generation()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                last_sent = -1
                lf = backend.last_frame
                if lf is not None:
                    self._send_frame(lf)
                    last_sent = lf["seq"]
                while backend.generation == gen:
                    try:
                        frame = backend.outbound.get(timeout=1.0)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")   # 心跳兼斷線偵測
                        self.wfile.flush()
                        continue
                    if backend.generation != gen:
                        backend.outbound.put(frame)        # 交回給接手的新連線
                        break
                    if frame["seq"] <= last_sent:
                        continue                            # 去重(重連已先送 last_frame)
                    self._send_frame(frame)
                    last_sent = frame["seq"]
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass                                        # 客戶端離線:靜默退出

        def _send_frame(self, frame: dict):
            payload = json.dumps(frame, ensure_ascii=False).encode("utf-8")
            self.wfile.write(b"data: " + payload + b"\n\n")
            self.wfile.flush()

        # --- POST ---------------------------------------------------------
        def do_POST(self):
            if self.path != "/input":
                self._send_bytes(404, "text/plain; charset=utf-8", b"not found")
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                n = max(0, min(n, 1_000_000))      # 防負值/超大 Content-Length 卡死讀取
                body = self.rfile.read(n) if n else b"{}"
                data = json.loads(body or b"{}")
                if not isinstance(data, dict):     # 非物件 JSON(5/"hi"/null…)→ 當空,回乾淨 409
                    data = {}
                accepted = backend.submit(data.get("prompt_id"), data.get("value"))
            except (ValueError, json.JSONDecodeError):
                accepted = False
            self._send_bytes(200 if accepted else 409,
                             "application/json; charset=utf-8",
                             json.dumps({"accepted": accepted}).encode("utf-8"))

        # --- util ---------------------------------------------------------
        def _send_bytes(self, code: int, ctype: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    return Handler


def make_recording_console(width: int = WIDTH):
    """供 launcher 與無頭測試共用:一個錄製用 Console(輸出丟棄、保留樣式)。"""
    from rich.console import Console
    return Console(record=True, file=open(os.devnull, "w"),
                   width=width, force_terminal=True, color_system="truecolor")


def _run_game(backend: WebBackend):
    """遊戲 thread:跑原本的 main(),結束時把殘餘畫面 + end 哨兵沖出。"""
    from tesrpg.ui import console as ui
    import tesrpg.main as gmain
    try:
        gmain.main()
    except SystemExit:
        pass
    except Exception:
        ui.console.print_exception(show_locals=False)   # 例外渲染進畫面而非凍結
    finally:
        html = ui.console.export_html(inline_styles=True, code_format="{code}", clear=True)
        backend.flush_final(html)


def launch(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    from tesrpg.ui import console as ui
    with open(_STATIC, "rb") as f:
        index_html = f.read()

    backend = WebBackend()
    ui.use_web_backend(backend, make_recording_console())

    httpd = ThreadingHTTPServer((host, port), _make_handler(backend, index_html))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    threading.Thread(target=_run_game, args=(backend,), daemon=True).start()

    url = f"http://{host}:{port}/"
    print(f"流亡者 Web — 開啟 {url} 開始遊玩(Ctrl-C 結束)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n再會,旅人。")
