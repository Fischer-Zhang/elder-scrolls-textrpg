#!/usr/bin/env python3
"""代理使用帳本 hook(R172 第一批 + R175 大文本自讀偵測;設計見 ops.md §13、handoff R172/R175)。

子命令(stdin 皆為 Claude Code hook 的 JSON):
  post    PostToolUse(Read|Edit|Write|Agent|Bash|Grep)與 PostToolUseFailure(Bash):把「做了什麼」記進帳本(只記 metadata)。
          R175:主對話用 Bash/Grep 把大文本(ops.md H2)的內文印進上下文時,累計「中文長行字數」,跨門檻當場提醒;
          Read 大文本只在 Stop 併入統計(Read 本身不當場提醒)
  prompt  UserPromptSubmit:記一筆「新一輪開始」標記(輪界)
  stop    Stop:實作輪(或自讀大文本達門檻)缺「代理檢查」行 / 缺「大文本自讀」欄 → 回 decision=block 並附實測數字,讓模型同輪補一行(同輪最多一次)
  status  給人看的摘要(/sync 用):帳本最後一筆時間、本里程碑 counsel 次數、大文本自讀、最近 StopCheck、錯誤筆數
  wiring  把接線 JSON 印到 stdout,讓使用者自己 redirect 成 .claude/settings.local.json(本腳本絕不寫 settings)

紅線:
- hook 永不阻擋工具、永遠 exit 0。內部錯誤寫帳本 Error 記錄,每個 session 只通知一次;不設 onFailure:"block"。
  R175 的當場提醒只用 additionalContext(給模型)與 systemMessage(給使用者);不用 updatedToolOutput(那等於沒收工具結果)。
- 主對話統計只取 agent_type 為空的記錄:子代理內的 Read/Edit 也會觸發同一組 hook(agent_type 非空)。
  scout 讀大文本是它的本職,當場提醒與 Stop 納入都以 agent_type 為空作閘門。
- 帳本路徑可用環境變數 SLG_OPS_LEDGER 替換(測試必用,不碰真帳本)。預設 <repo>/.claude/ledger/ops.jsonl(已 gitignore)。
- 只記路徑、行數、Agent 的派工標籤(description 前 60 字);不存檔案內容、prompt、工具輸出、指令文字。
  R175 另記:Read/Bash/Grep 輸出的「中文長行字數」與位元組數、命中的大文本檔名、Write/Edit 內容是否提到大文本(只記檔名清單,當 taint 標記)。
- 看不到 Stop 的 last_assistant_message 就無從判斷模型是否已寫「代理檢查」:放行並留 skip_no_msg 記錄(永不擋人)。
- 已知缺口:matcher 不含 SendMessage,續用既有 counsel 不入帳(是否算一次待使用者定,見 ops.md §13)。
  R175 已知缺口:以 Bash heredoc 建的腳本檔不會被 taint;`git add x && python …` 這類以 git 開頭的複合指令會被當 git 豁免;
  輸出被重導到檔案再讀,只有「讀」那一步(若走 Read)才入帳;背景 Bash 的 BashOutput/TaskOutput、MCP 檔案讀取工具不在 matcher;
  用 fold/cut 把大文本切成 ≤40 字短行(或滴漏式小讀)量不到——指標只計「>40 字的中文長行」,Stop 提醒附的 session 累計只顯示、不設門檻。
- 里程碑 = 提交訊息開頭的 R##(R114C 與 R114 是不同里程碑;同 R## 多次提交同一個;無 R## 的提交略過)。
  時間取 author date(%at):rebase / amend / cherry-pick 不改它;只看 main(沒有就退 HEAD)。

只用 stdlib,啟動要快(每個 Read/Edit/Write/Agent/Bash 都會跑一次;一般 Bash 輸出沒有中文長行就不碰帳本)。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 專案經符號連結進入時,Edit/Write 給的是邏輯路徑:兩種根都要認,否則 repo 內改檔會被判在 repo 外(永不提醒)
ROOTS = tuple(dict.fromkeys(str(r) for r in (ROOT, Path(os.path.abspath(__file__)).parents[2])))
ENV_LEDGER = "SLG_OPS_LEDGER"
DEFAULT_LEDGER = ROOT / ".claude" / "ledger" / "ops.jsonl"

MAX_TAIL_BYTES = 4_000_000   # 讀帳本只取尾端(只增不減;輪界與里程碑窗都在尾端)
H1_LINES = 1000              # ops.md H1:讀而不改 > ~1000 行 …
H1_FILES = 5                 # … 或 ≥ 5 檔,應派 scout
IMPL_READ_FILES = 5          # ops.md §7:讀過 ≥ 5 個檔也算實作輪
COUNSEL_CAP = 2              # ops.md §4:每里程碑 counsel 上限
MAIN_REFS = ("main", "HEAD")
GIT_LOG_LIMIT = 400

# ── R175:大文本自讀(ops.md H2 硬規則:主對話不印大文本內文)────────────────────
BIG_DOCS = ("handoff.md", "BESTIARY.md", "bestiary.json", "quests.json", "events.json", "npcs.json", "mastery.json")
BIG_DIRS = ("tesrpg/data",)
PROSE_LINE_MIN = 40       # 只計「長度 > 40 字」的行:對應鐵令「只准數字/ID/行號/布林/≤40 字定位片段」
PROSE_REC_MIN = 40        # 一次輸出的中文長行字數 < 此值就不記帳(一般 Bash 的輸出幾乎都在這以下 → 不碰帳本)
BIGDOC_WARN = 150         # 本輪累計中文長行字數跨過 → 當場 additionalContext(只給模型,不吵使用者)
BIGDOC_ALARM = 600        # 再跨過 → 另發 systemMessage(使用者看得到)
ENV_BIGDOC = "SLG_OPS_BIGDOC"   # 設 off:不當場提醒、Stop 不納入(仍記帳);一鍵關掉誤報
BD_TOKEN = "大文本自讀"   # 「代理檢查」行須含的欄位名
CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
GIT_EXEMPT_SUBS = frozenset({"status", "add", "commit", "push", "rev-list", "branch", "ls-files", "check-ignore"})
GIT_STAT_FLAGS = frozenset({"--stat", "--numstat", "--name-only", "--name-status", "--shortstat"})
GIT_PATCH_FLAGS = frozenset({"-p", "-u", "-c", "--patch", "--cc", "--binary", "--patch-with-stat", "--patch-with-raw"})   # 帶這些會印出檔案內文
GIT_PATCH_PREFIXES = ("--word-diff", "--unified", "-U", "-L")   # 帶值的旗標:-U3、--unified=3、-L1,5:file
GIT_VALUE_OPTS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})   # git 全域選項,後面跟一個值
PATCH_MARK_RE = re.compile(r"(?m)^(?:diff --(?:git|cc|combined) |@@@? -\d)")   # 輸出含 diff/hunk 標頭 = 其實印了差異內文(旗標清單永遠不完整的後盾)
ENV_OFF_VALUES = frozenset({"off", "0", "false", "no"})
PROSE_SCAN_MAX = 2_000_000   # 單次輸出最多掃這麼多字元:病態巨量輸出不吃光記憶體/CPU
CMD_SCAN_MAX = 20_000        # 指令字串最多看這麼多字元(解析前綴用)
LEAD_CD_RE = re.compile(r"[\s(]*cd\s+\S+\s*(?:&&|;|\n)\s*")   # 前綴:cd x && / cd x; / (cd x &&
LEAD_ENV_RE = re.compile(r"\s*(?:[A-Za-z_]\w*=\S*\s+)+")       # 前綴:VAR=val
LEAD_WRAP_RE = re.compile(r"\s*(?:env|command|time|nice)\s+")
GREP_CMD_RE = re.compile(r"(?:(?:\S*/)?(?:egrep|fgrep|grep|rg|ag)|git\s+(?:-\S+\s+)*grep)(?:\s|$)")
LINE_PATH_RE = re.compile(r"^([^\s:]+):(?:\d+:)?")   # grep 多檔/遞迴輸出行首的 path:行號: 前綴
EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")
TAINT_BASENAME_MIN = 6    # taint 以檔名子字串比對時,檔名至少要這麼長(避免 x.py 之類誤命中)
TAINT_SCAN_MAX = 300_000  # 掃 Write/Edit 內容找大文本檔名,最多看這麼多字元


def _cmd(sub: str) -> str:
    # `|| exit 1`:python 找不到腳本時 exit code 是 2,而 Stop hook 的 exit 2 = 擋下結束並把 stderr 餵給模型;
    # 任何啟動失敗必須降為 exit 1(非阻擋、看得見)
    return f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/ops_ledger.py" {sub} || exit 1'


# 接線 JSON 的唯一來源:`wiring` 子命令印它、ops.md §13 附同一份、測試鎖住三方一致。
# PostToolUseFailure:Bash 非零 exit 只走這個事件,payload 無 tool_response、`error` 內含 exit code 與先印出的 stdout/stderr(2026-11 實測)。
# Grep 在 macOS/Linux/WSL 預設不存在(官方文件),列在 matcher 裡無害;Bash 的 grep 輸出走 Bash 的 matcher。
WIRING = {
    "hooks": {
        "PostToolUse": [{"matcher": "Read|Edit|Write|Agent|Bash|Grep",
                         "hooks": [{"type": "command", "command": _cmd("post"), "timeout": 10}]}],
        "PostToolUseFailure": [{"matcher": "Bash",
                                "hooks": [{"type": "command", "command": _cmd("post"), "timeout": 10}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": _cmd("prompt"), "timeout": 10}]}],
        "Stop": [{"hooks": [{"type": "command", "command": _cmd("stop"), "timeout": 10}]}],
    },
    "permissions": {"allow": ["Bash(python3 .claude/hooks/ops_ledger.py status)"]},
}

# 行首容許空白(含全形)與 markdown 前綴。不可用 \s:它含換行,搭 (?m)^ 對連續空白行會二次方回溯
# (10 萬個換行 ≈ 9.5 秒,逼近 hook timeout)
CHECK_LINE_RE = re.compile(r"(?m)^[ \t\u3000\xa0>*_`#\-]*代理檢查")
TOKEN_LINE_RE = re.compile(CHECK_LINE_RE.pattern.replace("代理檢查", re.escape(BD_TOKEN)))   # 另起一行、以「大文本自讀」開頭(行首前綴與 CHECK_LINE_RE 同源)
MILESTONE_RE = re.compile(r"^\s*(R\d+[A-Za-z]?)(?![A-Za-z0-9])")


# ── 帳本 I/O ───────────────────────────────────────────────────────────────

def ledger_path() -> str:
    return os.environ.get(ENV_LEDGER) or str(DEFAULT_LEDGER)


def append_record(rec: dict) -> None:
    """單次 O_APPEND write 一行 JSON:多個 hook 並發也不會交錯成半行。
    檔尾若不是換行(上次寫到一半、被手改過),先補一個換行,免得新記錄黏在殘行後面變成兩筆壞記錄。"""
    path = ledger_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    line = (json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            line = b"\n" + line
        os.write(fd, line)
    finally:
        os.close(fd)


def load_records(path: str | None = None) -> list[dict]:
    """讀帳本尾端 MAX_TAIL_BYTES;壞行(半行、手改壞)直接略過。檔案順序即到達順序。"""
    path = path or ledger_path()
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > MAX_TAIL_BYTES:
                # 被截斷的第一行是壞 JSON,下面解析時自然略過。不要硬丟第一行:截點剛好落在行首時會誤丟一整筆完整記錄
                f.seek(size - MAX_TAIL_BYTES)
            data = f.read()
    except OSError:
        return []
    out = []
    # 只在 \n 斷行,不用 splitlines():它也在 U+2028/U+2029/U+0085 斷行(JSON 不跳脫它們),會把一筆記錄劈成兩段壞 JSON
    for line in data.decode("utf-8", "replace").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            for key in ("path", "tuid"):   # 這兩欄會被當 set/dict 鍵:壞型別(手改、毒記錄)當缺值,別讓一筆壞資料拖垮所有統計
                if not isinstance(rec.get(key), (str, type(None))):
                    rec[key] = None
            out.append(rec)   # R175 的 docs 欄由使用處以 _str_list 防護(壞型別當空)
    return out


# ── 小工具 ─────────────────────────────────────────────────────────────────

def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):   # OverflowError:毒記錄裡的 inf
        return 0


def _float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _str_list(v) -> list[str]:
    """毒記錄防護:只收 list 裡的字串,其餘當空。"""
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def _norm_path(p):
    return os.path.normpath(p) if isinstance(p, str) and p else None


def _in_repo(p: str) -> bool:
    return any(p == r or p.startswith(r + os.sep) for r in ROOTS)


def _rel(p: str) -> str:
    for r in ROOTS:
        if p == r or p.startswith(r + os.sep):
            return os.path.relpath(p, r)
    return p


def _find(obj, key: str, depth: int = 2):
    """在 tool_response 裡找單一純量欄位(最多往下 depth 層);找不到回 None。"""
    if not isinstance(obj, dict):
        return None
    v = obj.get(key)
    if isinstance(v, (str, int, float, bool)):
        return v
    if depth > 0:
        for sub in obj.values():
            if isinstance(sub, dict):
                got = _find(sub, key, depth - 1)
                if got is not None:
                    return got
    return None


def _read_counts(tr) -> tuple[int, int | None]:
    """Read 的 tool_response.file.numLines / totalLines(2026-11 實測);取不到(圖片/PDF)回 (0, None)。"""
    f = tr.get("file") if isinstance(tr, dict) else None
    if not isinstance(f, dict):
        return 0, None
    tot = f.get("totalLines")
    return _int(f.get("numLines")), (_int(tot) if tot is not None else None)


def bigdoc_enabled() -> bool:
    return os.environ.get(ENV_BIGDOC, "").strip().lower() not in ENV_OFF_VALUES


def _cjk_prose(text) -> int:
    """輸出中「長度 > 40、且含中文的行」所含的中文字數:只計自然語句,ASCII 計數/ID/行號/≤40 字定位片段都不算。
    只掃前 PROSE_SCAN_MAX 字元;逐個 finditer 計數,不建整份清單(巨量單行不吃記憶體)。"""
    if not isinstance(text, str):
        return 0
    n = 0
    for line in text[:PROSE_SCAN_MAX].split("\n"):
        if len(line) > PROSE_LINE_MIN:
            n += sum(1 for _ in CJK_RE.finditer(line))
    return n


def _mentions_big(s) -> list[str]:
    """字串(指令/路徑/內容)裡提到哪些大文本:檔名與目錄都算。"""
    if not isinstance(s, str) or not s:
        return []
    return [b for b in BIG_DOCS if b in s] + [d for d in BIG_DIRS if d in s]


def _strip_cmd_prefix(cmd: str) -> str:
    """剝掉指令前綴(cd x && / cd x; / (cd x && / VAR=val / env / command / time),回「真正的第一個命令」那一行。"""
    s = (cmd or "")[:CMD_SCAN_MAX]
    while True:
        m = LEAD_CD_RE.match(s) or LEAD_ENV_RE.match(s) or LEAD_WRAP_RE.match(s)
        if not m:
            return s.split("\n", 1)[0].strip()
        s = s[m.end():]


def _grep_like(cmd: str) -> bool:
    """第一個命令是 grep 家族(含 git grep):輸出行帶 path:行號: 前綴,可逐行歸屬到來源檔。"""
    return bool(GREP_CMD_RE.match(_strip_cmd_prefix(cmd)))


def _line_path(line: str):
    """grep 多檔/遞迴輸出行首的 `path:行號:` 前綴 → 回 path;沒有前綴(單檔 grep、內文行)或前綴只是行號 → None。
    只認「像檔案路徑」的前綴(含 / 或副檔名),免得把內文行首的「R175:」之類誤當路徑。"""
    m = LINE_PATH_RE.match(line)
    if not m:
        return None
    p = m.group(1)   # 純數字(單檔 grep -n 的行號)沒有 / 也沒有副檔名,下面的「像路徑」判斷就會擋掉
    return p if ("/" in p or EXT_RE.search(p)) else None


def _attribute_grep_lines(text: str) -> tuple[str, list[str]]:
    """grep 家族輸出逐行歸屬:前綴指向大文本的行保留(並回報命中的大文本名),指向別的檔的行丟掉,沒有前綴的行保留。
    解決:多檔 grep 其他檔的輸出、搜原始碼裡誰提到 quests.json 的輸出被整條算成自讀(誤報);
    以及 `grep -rn X .` 命中 handoff.md 卻因指令沒寫檔名而不被認出(漏報)。"""
    keep: list[str] = []
    names: list[str] = []
    for line in text.split("\n"):
        p = _line_path(line)
        if p is None:
            keep.append(line)
            continue
        hit = _mentions_big(p)
        if hit:
            keep.append(line)
            names += [h for h in hit if h not in names]
    return "\n".join(keep), names


def _git_exempt(cmd: str) -> bool:
    """git 的非「讀內文」子命令(log/status/add/commit/push…,或帶 --stat 一類旗標的 diff/show)不當自讀。
    log/diff/show 一帶 -p/-c/-U/-L/--patch/--binary/--word-diff 之類就會印出檔案內文,不豁免;
    `git show <rev>:<path>` 印的是檔案本體,--stat 擋不住,也不豁免。呼叫端另以輸出裡的 diff/hunk 標頭當最後防線。
    只看第一個命令(剝掉 cd/環境變數前綴後);已知限制:`git add x && python …` 這種以 git 開頭的複合指令也會被豁免。"""
    toks = _strip_cmd_prefix(cmd).split()
    if len(toks) < 2 or os.path.basename(toks[0]) != "git":
        return False
    i = 1
    while i < len(toks) and toks[i].startswith("-"):   # git -C dir / -c k=v / --git-dir d / --no-pager
        i += 2 if toks[i] in GIT_VALUE_OPTS else 1
    sub = toks[i] if i < len(toks) else ""
    rest = toks[i + 1:]
    patch = any(t in GIT_PATCH_FLAGS or t.startswith(GIT_PATCH_PREFIXES) for t in rest)
    if sub == "log":
        return not patch   # log 預設只印提交標頭;帶 patch 類旗標會把每次提交的差異內文印出來
    if sub in ("diff", "show"):
        if patch or (sub == "show" and any(":" in t and not t.startswith("-") for t in rest)):
            return False
        return any(t.split("=", 1)[0] in GIT_STAT_FLAGS for t in rest)
    return sub in GIT_EXEMPT_SUBS


def _out_text(event: str, tool: str, tr, payload: dict) -> tuple[str, int]:
    """取工具輸出文字與「實際大小」。Bash:stdout+stderr(失敗事件 PostToolUseFailure 改取 error,它內含 exit code 與先印出的輸出);
    Grep:content。大輸出被截斷時(stdout 只剩 3 萬字)用 persistedOutputSize 當實際大小(2026-11 實測)。"""
    text = ""
    size = None
    if event == "PostToolUseFailure":
        err = payload.get("error")
        text = err if isinstance(err, str) else ""
    elif isinstance(tr, dict):
        if tool == "Bash":
            text = "\n".join(p for p in (tr.get("stdout"), tr.get("stderr")) if isinstance(p, str) and p)
        else:
            c = tr.get("content")
            text = c if isinstance(c, str) else ""
        ps = tr.get("persistedOutputSize")
        if isinstance(ps, int) and not isinstance(ps, bool):
            size = ps
    elif isinstance(tr, str):
        text = tr
    return text, (size if size is not None else len(text.encode("utf-8", "replace")))


def tainted_paths(recs: list[dict], sid) -> set[str]:
    """本 session 主對話 Write/Edit 過、且內容提到大文本的檔案路徑(只存路徑,不存內容)。
    之後 Bash 指令引用這些腳本檔(整條路徑或夠長的檔名)就視為在讀大文本——補上「腳本檔化」的繞法。"""
    return {r["path"] for r in recs
            if r.get("sid") == sid and not r.get("at") and r.get("bdm") and isinstance(r.get("path"), str)}


def _is_tainted_ref(paths, subject: str) -> list[str]:
    hit = []
    for p in paths:
        base = os.path.basename(p)
        if p in subject or (len(base) >= TAINT_BASENAME_MIN and base in subject):
            hit.append(p)
    return hit


def session_bigdoc_prose(recs: list[dict], sid) -> int:
    """本 session 主對話自讀大文本的累計中文長行字數(Stop 提醒附上,擋「每輪滴漏」)。"""
    total = 0
    for r in recs:
        if r.get("sid") != sid or r.get("at"):
            continue
        if r.get("ev") == "BigDoc" and r.get("gate") == "doc" and not r.get("ex"):
            total += _int(r.get("prose"))
        elif r.get("ev") == "Read" and r.get("bdp"):
            total += _int(r.get("bdp"))
    return total


def _base(payload: dict) -> dict:
    return {
        "ts": round(time.time(), 3),
        "sid": payload.get("session_id"),
        "pid": payload.get("prompt_id"),
        "at": payload.get("agent_type") or None,   # 子代理內的呼叫才有;主對話為 None
        "aid": payload.get("agent_id") or None,
    }


def is_counsel(rec: dict) -> bool:
    """counsel 派遣:subagent_type=counsel,或實際用到 Opus。
    實際解析的模型(resolvedModel)優先;同步回應沒帶它時,退而看派工時的 model 覆寫(fork 忽略覆寫,不算)。"""
    if rec.get("st") == "counsel":
        return True
    resolved = str(rec.get("rmodel") or "").lower()
    if resolved:
        return "opus" in resolved
    if rec.get("st") == "fork":
        return False
    return "opus" in str(rec.get("model") or "").lower()


# ── 輪界 / 單輪統計 ────────────────────────────────────────────────────────

def turn_records(recs: list[dict], sid, pid) -> list[dict]:
    """本輪記錄 = 同 session、最後一個 Prompt 標記之後;若兩邊都有 prompt_id 則須相同。

    兩道輪界互補:prompt_id 若跨輪不變,標記仍切得開;若無 UserPromptSubmit(例如背景任務通知觸發的輪),
    prompt_id 切得開。用檔案順序而不是時間戳,不怕時鐘跳動。"""
    sess = [r for r in recs if r.get("sid") == sid]
    start = 0
    for i, r in enumerate(sess):
        if r.get("ev") == "Prompt":
            start = i
    turn = sess[start:]
    if pid:
        turn = [r for r in turn if r.get("pid") in (None, pid)]
    return turn


def turn_stats(turn: list[dict]) -> dict:
    """只統計主對話(at 為空)。改檔只算 repo 內(記憶/暫存檔不算);讀而未改 = 本輪讀過但沒改的檔。

    R175 大文本自讀(bd_*):Bash/Grep 的 BigDoc(gate=doc、非 git 豁免)+ Read 大文本的「中文長行字數」。
    同輪有 Edit/Write 同一檔的 Read 另計 bd_prefetch(ops.md H2 例外:即將編輯的那一段),不算違規。
    gate=none(沒提到大文本檔名、卻印出中文長行)只當盲點提示 bd_hint,不計入。"""
    edited: dict[str, int] = {}
    reads: list[tuple[str, int]] = []
    agents: list[dict] = []
    seen: set = set()
    bd_events: list[tuple[int, list]] = []   # (prose, docs):Bash/Grep 命中
    bd_reads: list[tuple[str, int]] = []     # (path, prose):Read 大文本
    bd_hint = 0
    for r in turn:
        if r.get("at"):
            continue
        ev = r.get("ev")
        if ev in ("Edit", "Write"):
            if r.get("in") and r.get("path"):
                edited[r["path"]] = edited.get(r["path"], 0) + 1
        elif ev == "Read":
            if r.get("path"):
                reads.append((r["path"], _int(r.get("n"))))
                if r.get("bdp"):
                    bd_reads.append((r["path"], _int(r.get("bdp"))))
        elif ev == "Agent":
            tuid = r.get("tuid")
            if tuid:
                if tuid in seen:
                    continue
                seen.add(tuid)
            agents.append(r)
        elif ev == "BigDoc":
            if r.get("gate") == "doc" and not r.get("ex"):
                bd_events.append((_int(r.get("prose")), _str_list(r.get("docs"))))
            elif r.get("gate") == "none":
                bd_hint += _int(r.get("prose"))
    read_paths = {p for p, _ in reads}
    ro = [(p, n) for p, n in reads if p not in edited]
    bd_prose = sum(p for p, _ in bd_events)
    bd_docs = {d for _, ds in bd_events for d in ds}
    bd_n = len(bd_events)
    bd_prefetch = 0
    for p, n in bd_reads:
        if p in edited:
            bd_prefetch += n
        else:
            bd_prose += n
            bd_n += 1
            bd_docs.add(os.path.basename(p))
    return {
        "edited": sorted(edited),
        "n_edited": len(edited),
        "read_files": len(read_paths),
        "read_lines": sum(n for _, n in reads),
        "ro_files": len({p for p, _ in ro}),
        "ro_lines": sum(n for _, n in ro),
        "scout": sum(1 for a in agents if a.get("st") == "scout"),
        "counsel": sum(1 for a in agents if is_counsel(a)),
        "other": sum(1 for a in agents if a.get("st") != "scout" and not is_counsel(a)),
        "bd_n": bd_n,
        "bd_prose": bd_prose,
        "bd_docs": sorted(bd_docs),
        "bd_hint": bd_hint,
        "bd_prefetch": bd_prefetch,
        "qualifies": (bool(edited) or len(read_paths) >= IMPL_READ_FILES or bool(agents)
                      or (bd_prose >= BIGDOC_WARN and bigdoc_enabled())),
    }


# ── 里程碑窗(以提交訊息開頭的 R## 界定)──────────────────────────────────

def _git(repo, *args) -> str | None:
    try:
        cp = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if cp.returncode != 0:
        return None
    return cp.stdout.decode("utf-8", "replace")


def milestone_token(subject: str) -> str | None:
    m = MILESTONE_RE.match(subject or "")
    return m.group(1) if m else None


def milestone_window(repo=None) -> dict | None:
    """回 {token, start_ts, boundary, head_ts, head};無 git 歷史回 None。

    token = 最新一個帶 R## 的提交的 R##;start_ts = 往回找到的第一個「R## 不同」的提交的 author time
    (無 R## 的提交略過、不當邊界);全歷史都同一個 R## 時 start_ts=None(= 從頭算)。head_ts = 最新提交的 author time。"""
    out = None
    for ref in MAIN_REFS:
        out = _git(repo or ROOT, "log", ref, "-n", str(GIT_LOG_LIMIT), "--format=%at%x09%h%x09%s", "--")
        if out is not None:
            break
    if out is None:
        return None
    rows = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0].strip().isdigit():
            rows.append((int(parts[0]), parts[1], parts[2]))
    if not rows:
        return None
    win = {"token": None, "start_ts": None, "boundary": None, "head_ts": rows[0][0], "head": rows[0][1]}
    cur = None
    for ts, sha, subj in rows:
        tok = milestone_token(subj)
        if tok is None:
            continue
        if cur is None:
            cur = win["token"] = tok
        elif tok != cur:
            win["start_ts"] = ts
            win["boundary"] = f"{sha} {subj[:40]}"
            break
    return win


def counsel_counts(recs: list[dict], win: dict | None) -> tuple[int, int]:
    """(本里程碑累計, 自最近提交後累計)。只算主對話以 Agent 工具派出的 counsel;tool_use_id 去重。
    邊界未知(無 git)就從頭算。"""
    start = win.get("start_ts") if win else None
    head = win.get("head_ts") if win else None
    seen: set = set()
    k_ms = k_head = 0
    for r in recs:
        if r.get("ev") != "Agent" or r.get("at") or not is_counsel(r):
            continue
        tuid = r.get("tuid")
        if tuid:
            if tuid in seen:
                continue
            seen.add(tuid)
        ts = _float(r.get("ts"))
        if start is None or ts > start:
            k_ms += 1
        if head is None or ts > head:
            k_head += 1
    return k_ms, k_head


# ── 子命令 ─────────────────────────────────────────────────────────────────

SCRIPT_SUFFIXES = (".py", ".sh", ".js", ".mjs", ".ts", ".rb", ".pl")


def _bigdoc_feedback(payload: dict, event: str):
    """本輪 Bash/Grep 自讀大文本的累計中文長行字數剛跨過門檻 → 回要輸出的 JSON(各門檻每輪最多一次);否則 None。
    additionalContext 給模型(不吵使用者);只有跨過 ALARM 才另發 systemMessage 給使用者。"""
    sid, pid = payload.get("session_id"), payload.get("prompt_id")
    turn = turn_records(load_records(), sid, pid)
    hits = [r for r in turn if r.get("ev") == "BigDoc" and r.get("gate") == "doc" and not r.get("ex")
            and not r.get("at") and r.get("via") in ("Bash", "Grep")]
    cum = sum(_int(r.get("prose")) for r in hits)
    marked = {_int(r.get("lvl")) for r in turn if r.get("ev") == "BDWarn"}
    fresh = [lvl for lvl, thr in ((1, BIGDOC_WARN), (2, BIGDOC_ALARM)) if cum >= thr and lvl not in marked]
    if not fresh:
        return None
    nonce = f"{os.getpid()}-{time.time_ns()}"
    for lvl in fresh:
        append_record({**_base(payload), "ev": "BDWarn", "lvl": lvl, "nonce": nonce})
    # 平行的工具呼叫各是獨立行程,可能同時跨過門檻、各自以為自己是第一個:帳本是 O_APPEND,檔案順序即全序,
    # 追加後重讀,每一級只有「最早那筆 BDWarn」的主人負責輸出(審查實測:6 個平行呼叫 × 10 回合,每回合都重複提醒)
    first: dict[int, object] = {}
    for r in turn_records(load_records(), sid, pid):
        if r.get("ev") == "BDWarn":
            first.setdefault(_int(r.get("lvl")), r.get("nonce"))
    fresh = [lvl for lvl in fresh if first.get(lvl) == nonce]
    if not fresh:
        return None
    docs = sorted({d for r in hits for d in _str_list(r.get("docs"))})
    shown = "、".join(docs) if docs else "(經腳本檔)"
    ctx = (f"⚠ [ops-hook] H2:本輪主對話已用 Bash/Grep 把大文本內容印進上下文,約 {cum} 個中文字(長行;涉及 {shown})。"
           "硬規則:大文本(handoff.md/BESTIARY.md/大型 JSON)內文只讀 scout 逐字引文;腳本只輸出數字/ID/行號/≤40 字定位片段。"
           "請改派 scout 取回,勿再自己印。")
    out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}}
    if max(fresh) >= 2:
        out["systemMessage"] = f"ops hook 警示:本輪主對話自讀大文本已達 {cum} 字(警報門檻 {BIGDOC_ALARM}),違反 ops.md H2。"
    return out


def _record_bigdoc_output(payload: dict, tool: str, ti: dict, tr, event: str, base: dict):
    """Bash/Grep 的輸出若含足量「中文長行」就記一筆 BigDoc;一般輸出(測試、git、計數)不碰帳本。
    gate=doc:指令/路徑提到大文本檔名或目錄,或引用了本 session 寫過且內容提到大文本的腳本檔(taint)→ 計入;
    gate=none:沒提到卻印出中文長行 → 只當盲點提示(Stop/status 顯示,不計入、不當場提醒)。"""
    text, size = _out_text(event, tool, tr, payload)
    text = text[:PROSE_SCAN_MAX]
    subject = (str(ti.get("command") or "") if tool == "Bash"
               else " ".join(str(ti.get(k) or "") for k in ("path", "glob")))
    out_docs: list[str] = []
    if tool == "Grep" or (tool == "Bash" and _grep_like(subject)):
        # grep 家族輸出逐行帶 path:行號: 前綴:只計來自大文本的行(多檔 grep 的其他檔、搜原始碼裡誰提到 quests.json 都不算);
        # 反過來 `grep -rn X .` 命中 handoff.md 的行,即使指令沒寫檔名也認得出來(審查實測的漏報)
        text, out_docs = _attribute_grep_lines(text)
    prose = _cjk_prose(text)
    if prose < PROSE_REC_MIN:
        return None
    docs = _mentions_big(subject)
    docs += [d for d in out_docs if d not in docs]
    tainted: list[str] = []
    if not docs:
        tainted = _is_tainted_ref(tainted_paths(load_records(), payload.get("session_id")), subject)
    gate = "doc" if (docs or tainted) else "none"
    exempt = bool(tool == "Bash" and gate == "doc" and _git_exempt(subject))
    if exempt and PATCH_MARK_RE.search(text):
        exempt = False   # 旗標清單永遠不完整:輸出實際含 diff/hunk 標頭就是印了差異內文,照計
    rec = {**base, "ev": "BigDoc", "via": tool, "gate": gate, "prose": prose, "bytes": size}
    for key, val in (("docs", docs), ("taint", bool(tainted)), ("ex", exempt), ("fail", event == "PostToolUseFailure")):
        if val:
            rec[key] = val
    append_record(rec)
    if gate == "doc" and not exempt and bigdoc_enabled():
        return _bigdoc_feedback(payload, event)
    return None


def handle_post(payload: dict):
    tool = payload.get("tool_name")
    event = payload.get("hook_event_name") if isinstance(payload.get("hook_event_name"), str) else "PostToolUse"
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    tr = payload.get("tool_response")
    rec = _base(payload)
    tuid = payload.get("tool_use_id")
    rec["tuid"] = tuid if isinstance(tuid, str) else None
    if tool in ("Bash", "Grep"):
        if rec.get("at"):
            return None   # 子代理(scout 讀大文本是本職)的 Bash/Grep:不記、不提醒
        return _record_bigdoc_output(payload, tool, ti, tr, event, rec)
    if tool == "Read":
        n, tot = _read_counts(tr)
        path = _norm_path(ti.get("file_path"))
        rec.update(ev="Read", path=path, n=n, tot=tot)
        if path and _mentions_big(path):
            f = tr.get("file") if isinstance(tr, dict) else None
            content = f.get("content") if isinstance(f, dict) else None
            bdp = _cjk_prose(content)
            if bdp:
                rec["bdp"] = bdp
                rec["bdb"] = len(content.encode("utf-8", "replace"))
    elif tool in ("Edit", "Write"):
        path = _norm_path(ti.get("file_path"))
        rec.update(ev=tool, path=path)
        rec["in"] = bool(path and _in_repo(path))
        body = ti.get("content") if tool == "Write" else ti.get("new_string")
        # taint:repo 外的腳本檔,內容提到大文本 → 日後 Bash 引用它就算在讀大文本(只記檔名清單,不存內容)
        if (isinstance(body, str) and path and not rec["in"] and path.lower().endswith(SCRIPT_SUFFIXES)):
            m = _mentions_big(body[:TAINT_SCAN_MAX])
            if m:
                rec["bdm"] = m
    elif tool in ("Agent", "Task"):
        rec.update(
            ev="Agent",
            st=ti.get("subagent_type") or "general-purpose",
            model=ti.get("model"),
            rmodel=_find(tr, "resolvedModel"),
            status=_find(tr, "status"),
            bg=bool(ti.get("run_in_background")),
            desc=str(ti.get("description") or "")[:60],
            rkeys=sorted(tr) if isinstance(tr, dict) else None,
        )
    else:
        return None
    append_record(rec)
    return None


def handle_prompt(payload: dict):
    rec = _base(payload)
    rec.update(ev="Prompt", keys=sorted(payload))
    append_record(rec)
    return None


def _has_bd_field(msg: str) -> bool:
    """「代理檢查」行內含「大文本自讀」,或另起一行以「大文本自讀」開頭(Stop 補欄提示要求的形式)。
    正文別處提到這個詞不算(審查實測:原本整則訊息任何位置出現都放行)。"""
    if TOKEN_LINE_RE.search(msg):
        return True
    for m in CHECK_LINE_RE.finditer(msg):
        end = msg.find("\n", m.end())
        if BD_TOKEN in msg[m.start(): end if end != -1 else len(msg)]:
            return True
    return False


def _fmt_edited(paths: list[str]) -> str:
    rels = [_rel(p) for p in paths]
    shown = "、".join(rels[:6])
    return shown + (f" 等 {len(rels)} 個" if len(rels) > 6 else "")


def _bd_lines(stats: dict) -> list[str]:
    docs = "、".join(stats.get("bd_docs") or []) or "(經腳本檔)"
    lines = [f"- 大文本自讀(Bash/Grep/Read 印出的中文長行):{stats.get('bd_n', 0)} 次約 {stats.get('bd_prose', 0)} 字(涉及 {docs});"
             f"本 session 累計約 {stats.get('bd_session', 0)} 字。H2 硬規則:主對話不印大文本內文,只讀 scout 引文"]
    if stats.get("bd_prefetch"):
        lines.append(f"- 另有「編輯前自讀」約 {stats['bd_prefetch']} 字(同輪編輯同一檔;H2 例外,不計入)")
    if stats.get("bd_hint", 0) >= BIGDOC_ALARM:
        lines.append(f"- 盲點提示:另有約 {stats['bd_hint']} 字中文長行輸出沒提到大文本檔名(可能經腳本檔/glob/變數);請自查是否也屬自讀")
    return lines


def build_reason(stats: dict, k_ms: int, k_head: int, win: dict | None, missing_line: bool = True) -> str:
    need_bd = stats.get("bd_prose", 0) >= BIGDOC_WARN and bigdoc_enabled()
    if not missing_line:
        # 已寫「代理檢查」行、只缺「大文本自讀」欄:只要求補這一欄(與缺行共用同一個 Reminded 預算,同輪最多擋一次)
        return "\n".join([
            "[ops-hook] 本輪主對話自讀了大文本,但你的「代理檢查」行缺「大文本自讀」欄。實測(僅主對話;子代理不計):",
            *_bd_lines(stats),
            "請只補這一行、不要重述前文;節數如實填,非 0 要列出是哪幾節與理由:",
            f"{BD_TOKEN}:<N 節(列出)>",
        ])
    over = stats["ro_lines"] > H1_LINES or stats["ro_files"] >= H1_FILES
    token = (win or {}).get("token") or "?"
    head = (win or {}).get("head") or "?"
    h1 = "已超過 H1 門檻(>1000 行或 ≥5 檔)" if over else "未超過 H1 門檻"
    if k_ms == k_head:
        counsel_line = f"- counsel 本里程碑 {k_ms}/{COUNSEL_CAP}({token} 起算;自最近提交 {head} 後亦為 {k_head})"
        counsel_slot = f"counsel {k_ms}/{COUNSEL_CAP}"
    else:
        counsel_line = (f"- counsel 本里程碑 {k_ms}/{COUNSEL_CAP}({token} 起算);自最近提交 {head} 後 {k_head}。"
                        "新里程碑尚未提交時以後者為準,延續舊里程碑時以前者為準")
        counsel_slot = f"counsel <{k_ms} 或 {k_head}>/{COUNSEL_CAP}"
    haiku_choice = "自己讀(已超過門檻,須寫理由)/ 已派 scout" if over else "自己讀 / 已派 scout"
    lines = [
        "[ops-hook] 本輪是實作輪,回覆尚缺「代理檢查」行。實測(僅主對話;子代理自己的讀寫不計):",
        f"- 改檔(repo 內):{stats['n_edited']} 個" + (f"({_fmt_edited(stats['edited'])})" if stats["edited"] else ""),
        f"- 讀而未改:{stats['ro_files']} 檔約 {stats['ro_lines']} 行({h1};H1 只算 Read 的行數)",
        f"- 本輪派代理:scout {stats['scout']}、counsel {stats['counsel']}、其他 {stats['other']}",
        counsel_line,
    ]
    if need_bd:
        lines += _bd_lines(stats)
    bd_slot = f"|{BD_TOKEN}:<N 節,應為 0;非 0 請列出>" if need_bd else ""
    lines += [
        "請依 ops.md §7 在結尾補一行,只補這一行、不要重述前文:",
        f"代理檢查|Opus:<無(O1–O5 皆否)或符合的 O 條件>|Haiku:讀而未改 {stats['ro_files']} 檔約 {stats['ro_lines']} 行"
        f" → <{haiku_choice}>{bd_slot}|{counsel_slot}",
    ]
    return "\n".join(lines)


def handle_stop(payload: dict):
    sid, pid = payload.get("session_id"), payload.get("prompt_id")
    recs = load_records()
    turn = turn_records(recs, sid, pid)
    stats = turn_stats(turn)
    stats["bd_session"] = session_bigdoc_prose(recs, sid)
    already = any(r.get("ev") == "Reminded" for r in turn)
    msg = payload.get("last_assistant_message")
    has_msg = isinstance(msg, str)
    has_line = has_msg and bool(CHECK_LINE_RE.search(msg))
    # R175:自讀大文本達門檻時,「代理檢查」行還須含「大文本自讀」欄;兩種缺漏共用同一個 Reminded 預算(同輪最多擋一次)
    need_token = stats["bd_prose"] >= BIGDOC_WARN and bigdoc_enabled()
    has_token = has_msg and _has_bd_field(msg)
    base = _base(payload)
    out = None
    extra: dict = {}
    if payload.get("stop_hook_active"):
        # 已被 Stop hook 續跑過一輪:一律放行,並記下「本輪已提醒過」(同輪最多補一次的第二道保險)
        result = "skip_active"
        if not already:
            append_record({**base, "ev": "Reminded", "via": "active"})
    elif already:
        result = "skip_reminded"
    elif not stats["qualifies"]:
        result = "skip_unqualified"
    elif not has_msg:
        # 看不到最後一則訊息,就無從判斷模型是否已寫:放行(永不擋人),留紀錄,status 會警告(後備:讀 transcript_path)
        result = "skip_no_msg"
    elif has_line and (has_token or not need_token):
        result = "has_line"
    else:
        result = "remind"
        win = milestone_window(ROOT)
        k_ms, k_head = counsel_counts(recs, win)
        extra = {"k_ms": k_ms, "k_head": k_head}
        if has_line:
            extra["why"] = "token"   # 已有「代理檢查」行,只缺「大文本自讀」欄
        append_record({**base, "ev": "Reminded", "via": "remind"})   # 先記再輸出:輸出後崩潰也不會重複提醒
        out = {"decision": "block", "reason": build_reason(stats, k_ms, k_head, win, missing_line=not has_line)}
    append_record({
        **base, "ev": "StopCheck", "result": result, "keys": sorted(payload), "has_msg": has_msg,
        **{k: stats[k] for k in ("n_edited", "ro_files", "ro_lines", "read_files", "scout", "counsel", "other")},
        "bd_n": stats["bd_n"], "bd_prose": stats["bd_prose"],
        **extra,
    })
    return out


def fail_soft(cmd: str, exc: Exception, payload) -> dict | None:
    """內部錯誤:寫 Error 記錄;每個 session 只通知一次。回要輸出的 JSON,或 None(已通知過 / 連帳本都寫不了)。"""
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    err = f"{type(exc).__name__}: {exc}"[:300]
    try:
        noticed = any(r.get("ev") == "ErrNotice" and r.get("sid") == sid for r in load_records())
        append_record({"ts": round(time.time(), 3), "ev": "Error", "cmd": cmd, "sid": sid, "err": err})
        if noticed:
            return None
        append_record({"ts": round(time.time(), 3), "ev": "ErrNotice", "sid": sid})
    except Exception:
        return None
    text = (f"ops hook({cmd})內部錯誤,本 session 只提示這一次:{err}。已記入 {ledger_path()}"
            "(python3 .claude/hooks/ops_ledger.py status 可看);hook 不會阻擋任何操作。")
    out: dict = {"systemMessage": text}
    event = {"post": "PostToolUse", "prompt": "UserPromptSubmit"}.get(cmd)
    if cmd == "post" and isinstance(payload, dict) and payload.get("hook_event_name") == "PostToolUseFailure":
        event = "PostToolUseFailure"   # 失敗的 Bash 走這個事件:回覆的 hookEventName 須與觸發事件一致
    if event:
        out["hookSpecificOutput"] = {"hookEventName": event, "additionalContext": text}
    return out


# ── status(給人看)─────────────────────────────────────────────────────────

def _fmt_ts(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_float(ts)))


def _fmt_age(sec: float) -> str:
    sec = max(0, int(sec))
    for unit, size in (("天", 86400), ("小時", 3600), ("分鐘", 60)):
        if sec >= size:
            return f"{sec // size} {unit}"
    return f"{sec} 秒"


def status() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # LC_ALL=C 且 UTF-8 模式被關時,中文輸出不致崩潰
    except (AttributeError, ValueError):
        pass
    path = ledger_path()
    recs = load_records(path)
    print(f"帳本:{path}")
    if not recs:
        print("  空或不存在 — 若本 session 已做過讀寫,代表 hook 沒載入(檢查 .claude/settings*.json 的 hooks 區塊)")
    else:
        last = recs[-1]
        trunc = f"(檔案超過 {MAX_TAIL_BYTES // 1000} KB,只讀尾端)" if os.path.getsize(path) > MAX_TAIL_BYTES else ""
        print(f"  {len(recs)} 筆{trunc};最後一筆:{_fmt_ts(last.get('ts'))}"
              f"({_fmt_age(time.time() - _float(last.get('ts')))}前,ev={last.get('ev')})")
        print("  判讀:本 session 剛做過 Read/Edit/Write/Agent 但最後一筆很舊 → hook 沒載入")
    win = milestone_window(ROOT)
    if win is None:
        print("里程碑:無 git 歷史,counsel 從帳本頭算")
    else:
        bound = win["boundary"] or "(歷史起點)"
        print(f"里程碑:{win['token'] or '(最近提交無 R## 前綴)'};邊界 {bound};最近提交 {win['head']}")
    k_ms, k_head = counsel_counts(recs, win)
    print(f"counsel(Opus 派遣):本里程碑 {k_ms}/{COUNSEL_CAP};自最近提交後 {k_head}")
    start = win["start_ts"] if win and win["start_ts"] is not None else 0
    window = [r for r in recs if _float(r.get("ts")) > start]
    main_n: dict[str, int] = {}
    sub_n = 0
    for r in window:
        if r.get("ev") in ("Read", "Edit", "Write", "Agent"):
            if r.get("at"):
                sub_n += 1
            else:
                main_n[r["ev"]] = main_n.get(r["ev"], 0) + 1
    shown = "、".join(f"{k} {v}" for k, v in sorted(main_n.items())) or "無"
    print(f"本里程碑窗內:主對話 {shown};子代理內的呼叫 {sub_n} 筆(不計入主對話)")
    main_win = [r for r in window if not r.get("at")]
    bd_doc = sum(_int(r.get("prose")) for r in main_win
                 if r.get("ev") == "BigDoc" and r.get("gate") == "doc" and not r.get("ex"))
    bd_rd = sum(_int(r.get("bdp")) for r in main_win if r.get("ev") == "Read" and r.get("bdp"))
    bd_hint = sum(_int(r.get("prose")) for r in main_win if r.get("ev") == "BigDoc" and r.get("gate") == "none")
    warns = sum(1 for r in main_win if r.get("ev") == "BDWarn")
    print(f"大文本自讀(主對話,ops.md H2):Bash/Grep 約 {bd_doc} 字 + Read 約 {bd_rd} 字(中文長行;應為 0,僅編輯前自讀可例外);"
          f"盲點提示(沒提到檔名卻印中文長行)約 {bd_hint} 字;當場提醒 {warns} 次"
          + ("" if bigdoc_enabled() else f"【{ENV_BIGDOC}=off:提醒與 Stop 納入已停用】"))
    checks = [r for r in recs if r.get("ev") == "StopCheck"][-5:]
    if checks:
        print("最近 StopCheck:")
        for r in checks:
            print(f"  {_fmt_ts(r.get('ts'))} {str(r.get('result')):<16} 改{r.get('n_edited')} "
                  f"讀而未改 {r.get('ro_files')}檔/{r.get('ro_lines')}行 scout {r.get('scout')} counsel {r.get('counsel')}"
                  f" 大文本自讀 {_int(r.get('bd_prose'))}字")
        blind = sum(1 for r in checks if r.get("result") == "skip_no_msg")
        if blind:
            print(f"  ⚠ 最近 {len(checks)} 次 Stop 有 {blind} 次沒有 last_assistant_message → 這些輪的提醒實際停用"
                  "(後備方案:讀 transcript_path,見 ops.md §13)")
    errs = [r for r in recs if r.get("ev") == "Error"]
    print(f"內部錯誤:{len(errs)} 筆" + (f";最後:{_fmt_ts(errs[-1].get('ts'))} {errs[-1].get('err')}" if errs else ""))
    return 0


# ── 進入點 ─────────────────────────────────────────────────────────────────

HANDLERS = {"post": handle_post, "prompt": handle_prompt, "stop": handle_stop}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "status":
        return status()
    if cmd == "wiring":
        # 只印到 stdout,絕不寫 settings:讓使用者自己 `… wiring > .claude/settings.local.json`(會整檔覆寫,已有其他設定請手動合併)
        sys.stdout.write(json.dumps(WIRING, ensure_ascii=True, indent=2) + "\n")
        return 0
    handler = HANDLERS.get(cmd)
    if handler is None:
        print(f"用法:ops_ledger.py [{'|'.join([*HANDLERS, 'status', 'wiring'])}]", file=sys.stderr)
        return 0   # 設定打錯字也不要變成 hook 錯誤擋人
    payload = None
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("hook payload 不是 JSON 物件")
        out = handler(payload)
    except Exception as exc:  # noqa: BLE001 — hook 必須吞掉一切,永不擋人
        out = fail_soft(cmd, exc, payload)
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=True) + "\n")   # ASCII 跳脫:不依賴 hook 環境的 locale
    return 0


if __name__ == "__main__":
    sys.exit(main())
