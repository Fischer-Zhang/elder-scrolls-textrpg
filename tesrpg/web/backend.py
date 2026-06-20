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
        self.blocks: list = []      # 本幀累積的 block(view 原生 / html 退路),於 prompt 時沖出

    # --- 遊戲 thread 端(由 console.py 呼叫)--------------------------------
    def add_block(self, pending_html: str, name: str, data) -> None:
        """轉為原生的渲染函式呼叫此法:先把累積的(未轉換面板)HTML 收成 html block
        以保留交錯順序,再加 view block(客戶端依 name 渲成原生 HTML)。"""
        if pending_html.strip():
            self.blocks.append({"kind": "html", "html": pending_html})
        self.blocks.append({"kind": "view", "name": name, "data": data})

    def add_log(self, pending_html: str, log_html: str) -> None:
        """log/flavor 行:rich 標記轉成的彩色 HTML span,客戶端以無框文字行渲染(非等寬截圖)。"""
        if pending_html.strip():
            self.blocks.append({"kind": "html", "html": pending_html})
        self.blocks.append({"kind": "log", "html": log_html})

    def clear_block(self, pending_html: str = "") -> None:
        """送出一個『清空 #screen』狀態塊(clear kind):前端會 renderScreen→innerHTML 清空但不附任何面板。
        用於離開帶面板的子畫面(如創角開局一覽)後,讓後續純選單畫面不殘留前一面板。"""
        if pending_html.strip():
            self.blocks.append({"kind": "html", "html": pending_html})
        self.blocks.append({"kind": "clear"})

    def prompt(self, trailing_html: str, spec: dict, hud=None):
        """送出一幀(blocks 串 + 輸入規格 + 常駐 HUD),阻塞等使用者送回並驗證後回傳。

        blocks = view(原生)/html(退路) 依序;trailing_html=尚未轉換面板的殘餘;
        hud=跨畫面常駐的即時資源列。回傳型別對齊終端版。
        """
        if trailing_html.strip():
            self.blocks.append({"kind": "html", "html": trailing_html})
        blocks = self.blocks
        self.blocks = []
        resend = False                       # 首送=False;非法輸入後重送同 blocks=True
        while True:                          # 越界整數等:重送同一 blocks(新 seq/pid)
            with self._lock:
                self.prompt_id += 1
                self.seq += 1
                pid = self.prompt_id
                # resend 旗:前端據此「只對重送幀」做內容去重,正常遞進幀(含合法重複敘事)一律照記
                frame = {"seq": self.seq, "prompt_id": pid, "blocks": blocks,
                         "prompt": spec, "hud": hud, "resend": resend}
                self.last_frame = frame
                self.awaiting = True
            self.outbound.put(frame)
            value = self.inbound.get()        # 阻塞至 submit() 投遞
            ok, norm = _validate(spec, value)
            if ok:
                with self._lock:
                    self.awaiting = False
                return norm
            resend = True                     # 下一圈重送同 blocks(新 seq)→ 標記供前端去重

    def flush_final(self, trailing_html: str, hud=None) -> None:
        """遊戲 thread 結束(quit/未捕捉例外)後沖出殘餘 blocks + end 哨兵。"""
        if trailing_html.strip():
            self.blocks.append({"kind": "html", "html": trailing_html})
        blocks = self.blocks
        self.blocks = []
        with self._lock:
            self.seq += 1
            frame = {"seq": self.seq, "prompt_id": -1, "blocks": blocks,
                     "prompt": {"type": "end"}, "hud": hud, "resend": False}
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
        keys |= set(spec.get("extra_keys", []))      # 出口等可點內容列的合法 key
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
