"""WebBackend — suspends the blocking game loop at the 5 input primitives.

單人/本機:遊戲在背景 thread 跑原本的阻塞 REPL,console.py 的 5 個輸入原語在
web 模式改呼叫 `prompt()`,它把「上一畫面的 HTML + 該輸入的 prompt 規格」推進
`outbound`,然後 block 在 `inbound` 等使用者經 `POST /input` 送回選擇。

設計要點(對抗審查實證的必修項):
- 幀協定:{seq, prompt_id, screen_html, prompt}。`seq` 單調遞增供 SSE 去重;
  `prompt_id` 供 `/input` 比對(防雙擊幽靈作答)。
- `submit()` 在鎖內原子地檢查 awaiting+prompt_id → 消費 → 才 put,杜絕競態。
- `generation` 供 SSE 斷線重連:新連線遞增世代,舊/殭屍 handler 自行退出。
- `last_frame` 供重連即時重送,畫面還原。
"""

from __future__ import annotations

import queue
import threading


class WebBackend:
    def __init__(self) -> None:
        self.inbound: queue.Queue = queue.Queue()
        self.outbound: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self.awaiting = False
        self.prompt_id = 0          # 比對 /input 用(每個 prompt 遞增)
        self.seq = 0                # 幀序號(SSE 去重用,涵蓋 prompt 與 final 幀)
        self.generation = 0         # SSE 連線世代
        self.last_frame: dict | None = None

    # --- 遊戲 thread 端(由 console.py 的輸入原語呼叫)----------------------
    def prompt(self, screen_html: str, spec: dict):
        """送出一幀(畫面 + 輸入規格),阻塞等使用者送回並驗證後回傳。

        回傳型別對齊終端版:menu→key|None、grouped→key、confirm→bool、
        int→int、text→str。
        """
        while True:
            with self._lock:
                self.prompt_id += 1
                self.seq += 1
                pid = self.prompt_id
                frame = {"seq": self.seq, "prompt_id": pid,
                         "screen_html": screen_html, "prompt": spec}
                self.last_frame = frame
                self.awaiting = True
            self.outbound.put(frame)
            value = self.inbound.get()        # 阻塞至 submit() 投遞
            ok, norm = _validate(spec, value)
            if ok:
                with self._lock:
                    self.awaiting = False
                return norm
            # 無效(例如越界整數):重新武裝 + 重送同一幀,讓客戶端再試
            # (迴圈頂端會以同一 spec 重發,prompt_id 會再遞增)

    def flush_final(self, screen_html: str) -> None:
        """遊戲 thread 結束(quit/未捕捉例外)後沖出最後畫面 + end 哨兵。"""
        with self._lock:
            self.seq += 1
            frame = {"seq": self.seq, "prompt_id": -1,
                     "screen_html": screen_html, "prompt": {"type": "end"}}
            self.last_frame = frame
            self.awaiting = False
        self.outbound.put(frame)

    # --- HTTP 端 ----------------------------------------------------------
    def submit(self, prompt_id, value) -> bool:
        """POST /input → 投遞使用者選擇。非 awaiting 或 prompt_id 不符即丟棄
        (防雙擊/亂序幽靈作答)。回傳是否被接受。"""
        with self._lock:
            if not self.awaiting or prompt_id != self.prompt_id:
                return False
            self.awaiting = False     # 原子消費:第二次點擊會落到上面的 not awaiting
        self.inbound.put(value)
        return True

    def new_generation(self) -> int:
        """新的 SSE 連線:遞增世代並回傳,使舊 handler 自退。"""
        with self._lock:
            self.generation += 1
            return self.generation


def _validate(spec: dict, value):
    """回傳 (ok, normalized)。型別對齊終端版回傳。"""
    t = spec.get("type")
    if t == "menu":
        if value is None:
            return (spec.get("allow_back", False), None)
        keys = {o["key"] for o in spec.get("options", [])}
        return (value in keys, value)
    if t == "grouped":
        keys = {o["key"] for g in spec.get("groups", []) for o in g.get("options", [])}
        return (value in keys, value)
    if t == "confirm":
        return (True, bool(value))
    if t == "int":
        try:
            n = int(value)
        except (TypeError, ValueError):
            return (False, None)
        return (spec["lo"] <= n <= spec["hi"], n)
    if t == "text":
        return (True, "" if value is None else str(value))
    return (False, None)
