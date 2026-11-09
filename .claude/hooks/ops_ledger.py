#!/usr/bin/env python3
"""代理使用帳本 hook(R172 第一批;設計見 ops.md §13、handoff R172)。

子命令(stdin 皆為 Claude Code hook 的 JSON):
  post    PostToolUse(Read|Edit|Write|Agent):把「做了什麼」記進帳本(只記 metadata,不存檔案內容)
  prompt  UserPromptSubmit:記一筆「新一輪開始」標記(輪界)
  stop    Stop:實作輪缺「代理檢查」行 → 回 decision=block 並附實測數字,讓模型同輪補一行(同輪最多一次)
  status  給人看的摘要(/sync 用):帳本最後一筆時間、本里程碑 counsel 次數、最近 StopCheck、錯誤筆數

紅線:
- hook 永不阻擋工具、永遠 exit 0。內部錯誤寫帳本 Error 記錄,每個 session 只通知一次;不設 onFailure:"block"。
- 主對話統計只取 agent_type 為空的記錄:子代理內的 Read/Edit 也會觸發同一組 hook(agent_type 非空)。
- 帳本路徑可用環境變數 SLG_OPS_LEDGER 替換(測試必用,不碰真帳本)。預設 <repo>/.claude/ledger/ops.jsonl(已 gitignore)。
- 只記路徑、行數、Agent 的派工標籤(description 前 60 字);不存檔案內容、prompt、工具輸出。
- 看不到 Stop 的 last_assistant_message 就無從判斷模型是否已寫「代理檢查」:放行並留 skip_no_msg 記錄(永不擋人)。
- 已知缺口:matcher 不含 SendMessage,續用既有 counsel 不入帳(是否算一次待使用者定,見 ops.md §13)。
- 里程碑 = 提交訊息開頭的 R##(R114C 與 R114 是不同里程碑;同 R## 多次提交同一個;無 R## 的提交略過)。
  時間取 author date(%at):rebase / amend / cherry-pick 不改它;只看 main(沒有就退 HEAD)。

只用 stdlib,啟動要快(每次 Read/Edit/Write/Agent 都會跑一次)。
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

# 行首容許空白(含全形)與 markdown 前綴。不可用 \s:它含換行,搭 (?m)^ 對連續空白行會二次方回溯
# (10 萬個換行 ≈ 9.5 秒,逼近 hook timeout)
CHECK_LINE_RE = re.compile(r"(?m)^[ \t\u3000\xa0>*_`#\-]*代理檢查")
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
            out.append(rec)
    return out


# ── 小工具 ─────────────────────────────────────────────────────────────────

def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


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
    """只統計主對話(at 為空)。改檔只算 repo 內(記憶/暫存檔不算);讀而未改 = 本輪讀過但沒改的檔。"""
    edited: dict[str, int] = {}
    reads: list[tuple[str, int]] = []
    agents: list[dict] = []
    seen: set = set()
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
        elif ev == "Agent":
            tuid = r.get("tuid")
            if tuid:
                if tuid in seen:
                    continue
                seen.add(tuid)
            agents.append(r)
    read_paths = {p for p, _ in reads}
    ro = [(p, n) for p, n in reads if p not in edited]
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
        "qualifies": bool(edited) or len(read_paths) >= IMPL_READ_FILES or bool(agents),
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

def handle_post(payload: dict):
    tool = payload.get("tool_name")
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    tr = payload.get("tool_response")
    rec = _base(payload)
    tuid = payload.get("tool_use_id")
    rec["tuid"] = tuid if isinstance(tuid, str) else None
    if tool == "Read":
        n, tot = _read_counts(tr)
        rec.update(ev="Read", path=_norm_path(ti.get("file_path")), n=n, tot=tot)
    elif tool in ("Edit", "Write"):
        path = _norm_path(ti.get("file_path"))
        rec.update(ev=tool, path=path)
        rec["in"] = bool(path and _in_repo(path))
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


def _fmt_edited(paths: list[str]) -> str:
    rels = [_rel(p) for p in paths]
    shown = "、".join(rels[:6])
    return shown + (f" 等 {len(rels)} 個" if len(rels) > 6 else "")


def build_reason(stats: dict, k_ms: int, k_head: int, win: dict | None) -> str:
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
        f"- 讀而未改:{stats['ro_files']} 檔約 {stats['ro_lines']} 行({h1};只算 Read,不含 Grep/Bash)",
        f"- 本輪派代理:scout {stats['scout']}、counsel {stats['counsel']}、其他 {stats['other']}",
        counsel_line,
        "請依 ops.md §7 在結尾補一行,只補這一行、不要重述前文:",
        f"代理檢查|Opus:<無(O1–O5 皆否)或符合的 O 條件>|Haiku:讀而未改 {stats['ro_files']} 檔約 {stats['ro_lines']} 行"
        f" → <{haiku_choice}>|{counsel_slot}",
    ]
    return "\n".join(lines)


def handle_stop(payload: dict):
    sid, pid = payload.get("session_id"), payload.get("prompt_id")
    recs = load_records()
    turn = turn_records(recs, sid, pid)
    stats = turn_stats(turn)
    already = any(r.get("ev") == "Reminded" for r in turn)
    msg = payload.get("last_assistant_message")
    has_msg = isinstance(msg, str)
    has_line = has_msg and bool(CHECK_LINE_RE.search(msg))
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
    elif has_line:
        result = "has_line"
    else:
        result = "remind"
        win = milestone_window(ROOT)
        k_ms, k_head = counsel_counts(recs, win)
        extra = {"k_ms": k_ms, "k_head": k_head}
        append_record({**base, "ev": "Reminded", "via": "remind"})   # 先記再輸出:輸出後崩潰也不會重複提醒
        out = {"decision": "block", "reason": build_reason(stats, k_ms, k_head, win)}
    append_record({
        **base, "ev": "StopCheck", "result": result, "keys": sorted(payload), "has_msg": has_msg,
        **{k: stats[k] for k in ("n_edited", "ro_files", "ro_lines", "read_files", "scout", "counsel", "other")},
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
    checks = [r for r in recs if r.get("ev") == "StopCheck"][-5:]
    if checks:
        print("最近 StopCheck:")
        for r in checks:
            print(f"  {_fmt_ts(r.get('ts'))} {str(r.get('result')):<16} 改{r.get('n_edited')} "
                  f"讀而未改 {r.get('ro_files')}檔/{r.get('ro_lines')}行 scout {r.get('scout')} counsel {r.get('counsel')}")
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
    handler = HANDLERS.get(cmd)
    if handler is None:
        print(f"用法:ops_ledger.py [{'|'.join([*HANDLERS, 'status'])}]", file=sys.stderr)
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
