"""代理使用帳本 hook 守門(R172):.claude/hooks/ops_ledger.py。

覆蓋:PostToolUse 記帳(只記 metadata)、主對話 vs 子代理(agent_type)、輪界、Stop 提醒「同輪最多一次」、
內部錯誤只軟失敗(exit 0 + 每 session 一次通知)、里程碑窗(提交訊息開頭 R##)、counsel 計數、帳本路徑可替換。

鐵律:所有 hook 呼叫一律走 _run(必設 SLG_OPS_LEDGER 指向暫存帳本),函式層測試走 _ledger_env;
絕不碰真帳本 .claude/ledger/ops.jsonl。git 邊界測試用合成 repo,不讀真 repo 的歷史。
"""

import contextlib
import importlib.util
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOOK = os.path.join(ROOT, ".claude", "hooks", "ops_ledger.py")
F_A = os.path.join(ROOT, "ops.md")          # repo 內的路徑(hook 只記路徑,不讀檔)
F_B = os.path.join(ROOT, "CLAUDE.md")
F_C = os.path.join(ROOT, "handoff.md")
OUTSIDE = os.path.join(tempfile.gettempdir(), "slg_ops_hook_outside", "note.md")   # repo 外
LINE = "代理檢查|Opus:無(O1–O5 皆否)|Haiku:讀而未改 0 檔約 0 行 → 自己讀|counsel 0/2"
_seq = itertools.count(1)


# ── 工具 ──────────────────────────────────────────────────────────────────

def _mod():
    # R175 審查 #3:SLG_OPS_BIGDOC=off 是使用者環境,in-process 測試的結果不得隨它變(否則使用者照文件把它關掉,run_all 閘門就紅)
    os.environ.pop("SLG_OPS_BIGDOC", None)
    spec = importlib.util.spec_from_file_location("ops_ledger_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def _ledger_env(path):
    old = os.environ.get("SLG_OPS_LEDGER")
    os.environ["SLG_OPS_LEDGER"] = path
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("SLG_OPS_LEDGER", None)
        else:
            os.environ["SLG_OPS_LEDGER"] = old


def _run(cmd, payload, ledger, raw=None, env_remove=(), hook=HOOK, env_set=None):
    env = dict(os.environ)
    env["SLG_OPS_LEDGER"] = ledger
    env.pop("SLG_OPS_BIGDOC", None)   # R175 kill switch:預設關閉狀態由各測試明確指定,不被外部環境汙染
    for k in env_remove:
        env.pop(k, None)
    env.update(env_set or {})
    data = raw if raw is not None else json.dumps(payload).encode("utf-8")
    cp = subprocess.run([sys.executable, hook, cmd], input=data, env=env, capture_output=True, timeout=60)
    return cp.returncode, cp.stdout.decode("utf-8"), cp.stderr.decode("utf-8")


def _records(ledger):
    if not os.path.exists(ledger):
        return []
    with open(ledger, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _post(tool, ti, tr=None, sid="s1", pid="p1", tuid=None, agent_type=None):
    p = {"hook_event_name": "PostToolUse", "session_id": sid, "prompt_id": pid, "tool_name": tool,
         "tool_input": ti, "tool_response": {} if tr is None else tr,
         "tool_use_id": tuid or f"tu-{next(_seq)}"}
    if agent_type:
        p["agent_type"] = agent_type
        p["agent_id"] = "agent-1"
    return p


def _read(path, n, **kw):
    return _post("Read", {"file_path": path},
                 {"type": "text", "file": {"filePath": path, "content": "SECRET-BODY", "numLines": n,
                                           "startLine": 1, "totalLines": n}}, **kw)


def _edit(path, **kw):
    return _post("Edit", {"file_path": path, "old_string": "a", "new_string": "b"}, {}, **kw)


def _agent(subagent_type, resolved=None, **kw):
    ti = {"description": "d", "prompt": "PROMPT-BODY"}
    if subagent_type:
        ti["subagent_type"] = subagent_type
    tr = {"status": "async_launched"}
    if resolved:
        tr["resolvedModel"] = resolved
    return _post("Agent", ti, tr, **kw)


def _prompt(sid="s1", pid="p1"):
    return {"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt_id": pid, "prompt": "SECRET-PROMPT"}


def _stop(sid="s1", pid="p1", active=False, msg="完成。"):
    return {"hook_event_name": "Stop", "session_id": sid, "prompt_id": pid,
            "stop_hook_active": active, "last_assistant_message": msg}


def _feed(ledger, cmd_payloads):
    for cmd, payload in cmd_payloads:
        rc, out, err = _run(cmd, payload, ledger)
        assert rc == 0 and out == "", f"{cmd} 應靜默 exit 0:rc={rc} out={out!r} err={err!r}"


def _last_stopcheck(ledger):
    checks = [r for r in _records(ledger) if r["ev"] == "StopCheck"]
    assert checks, "帳本沒有 StopCheck 記錄"
    return checks[-1]


# ── PostToolUse 記帳 ──────────────────────────────────────────────────────

def test_post_read_records_numlines_and_never_content():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        rc, out, err = _run("post", _read(F_A, 143), led)
        assert rc == 0 and out == "", f"成功路徑須靜默:rc={rc} out={out!r} err={err!r}"
        recs = _records(led)
        assert len(recs) == 1, recs
        r = recs[0]
        assert (r["ev"], r["n"], r["tot"], r["path"], r["at"], r["aid"]) == ("Read", 143, 143, F_A, None, None), r
        assert "SECRET-BODY" not in open(led, encoding="utf-8").read(), "帳本不得存檔案內容"
        _run("prompt", _prompt(), led)
        assert "SECRET-PROMPT" not in open(led, encoding="utf-8").read(), "帳本不得存 prompt 文字"


def test_post_subagent_call_keeps_agent_type_and_agent_id():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("post", _read(F_A, 900, agent_type="Explore"), led)
        r = _records(led)[0]
        assert r["at"] == "Explore" and r["aid"] == "agent-1", r


def test_post_agent_records_type_model_and_never_prompt():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("post", _agent("counsel", "claude-opus-5-5"), led)
        _run("post", _agent(None), led)   # 省略 subagent_type = general-purpose
        a, b = _records(led)
        assert (a["ev"], a["st"], a["rmodel"], a["status"]) == ("Agent", "counsel", "claude-opus-5-5", "async_launched"), a
        assert b["st"] == "general-purpose" and b["rmodel"] is None, b
        assert "PROMPT-BODY" not in open(led, encoding="utf-8").read(), "帳本不得存派工 prompt"


def test_post_ignores_unwatched_tools_and_survives_odd_shapes():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("post", _post("Bash", {"command": "ls"}, {"stdout": "x"})),
                    ("post", _post("Glob", {"pattern": "*.md"}, {"filenames": ["a.md"]}))])
        # R175:Bash 會看輸出,但輸出沒有「中文長行」就走快速路徑(不寫、也不讀帳本);Glob 本就不在監看清單
        assert _records(led) == [] and not os.path.exists(led), "一般 Bash / 未監看工具不碰帳本"
        # tool_input 不是物件、tool_response 是字串:不崩、不報錯
        rc, out, err = _run("post", _post("Read", "oops", "plain text response"), led)
        assert rc == 0 and out == "", (rc, out, err)
        r = _records(led)[0]
        assert r["ev"] == "Read" and r["path"] is None and r["n"] == 0, r


# ── Stop 提醒 ─────────────────────────────────────────────────────────────

def test_stop_silent_on_qa_turn():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _read(F_A, 50)), ("stop", _stop())])
        assert _last_stopcheck(led)["result"] == "skip_unqualified"


def test_stop_reminds_once_with_measured_numbers():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _read(F_A, 300)), ("post", _read(F_B, 250)),
                    ("post", _edit(F_C))])
        rc, out, err = _run("stop", _stop(), led)
        assert rc == 0, err
        j = json.loads(out)
        assert j["decision"] == "block", j
        reason = j["reason"]
        for needle in ("讀而未改 2 檔約 550 行", "改檔(repo 內):1 個", "scout 0", "counsel 0", "代理檢查|Opus:", "ops.md §7"):
            assert needle in reason, f"提醒缺 {needle!r}:\n{reason}"
        assert _last_stopcheck(led)["result"] == "remind"
        want_last = "代理檢查|Opus:<無(O1–O5 皆否)或符合的 O 條件>|Haiku:讀而未改 2 檔約 550 行 → <自己讀 / 已派 scout>|counsel 0/2"
        assert reason.splitlines()[-1] == want_last, f"模型要照抄的那行必須帶對數字:\n{reason.splitlines()[-1]}"
        # 續跑後的第二次 Stop(stop_hook_active=true)放行
        rc, out, _ = _run("stop", _stop(active=True), led)
        assert rc == 0 and out == "", out
        # 即使旗標缺失,同一輪也不會再提醒(帳本的 Reminded 標記是第二道保險)
        rc, out, _ = _run("stop", _stop(active=False), led)
        assert rc == 0 and out == "", "同輪最多提醒一次"
        assert len([r for r in _records(led) if r["ev"] == "Reminded"]) == 1


def test_stop_passes_when_check_line_present():
    for msg in ("完成\n\n" + LINE, "完成\n**代理檢查**|Opus:無|Haiku:x|counsel 0/2", "完成\n> 代理檢查|Opus:無"):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "l.jsonl")
            _feed(led, [("prompt", _prompt()), ("post", _edit(F_A)), ("stop", _stop(msg=msg))])
            assert _last_stopcheck(led)["result"] == "has_line", msg
    # 句中提到「代理檢查」不算有這一行
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _edit(F_A))])
        rc, out, _ = _run("stop", _stop(msg="我忘了寫代理檢查這件事"), led)
        assert json.loads(out)["decision"] == "block"


def test_stop_active_flag_passes_and_marks_reminded():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _edit(F_A)), ("stop", _stop(active=True))])
        assert _last_stopcheck(led)["result"] == "skip_active"
        marks = [r for r in _records(led) if r["ev"] == "Reminded"]
        assert len(marks) == 1 and marks[0]["via"] == "active", marks
        _feed(led, [("stop", _stop(active=False))])   # 已記下「本輪已提醒過」→ 不再提醒
        assert _last_stopcheck(led)["result"] == "skip_reminded"


def test_turns_do_not_leak_into_each_other():
    # 三種輪界情境:pid 每輪不同 / pid 跨輪不變(靠 Prompt 標記切) / 無標記但 pid 不同(背景通知觸發的輪)
    for pid1, pid2, with_marker in (("p1", "p2", True), ("p1", "p1", True), ("p1", "p2", False)):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "l.jsonl")
            _feed(led, [("prompt", _prompt(pid=pid1)), ("post", _edit(F_A, pid=pid1)),
                        ("stop", _stop(pid=pid1, msg=LINE))])
            assert _last_stopcheck(led)["result"] == "has_line"
            if with_marker:
                _feed(led, [("prompt", _prompt(pid=pid2))])
            _feed(led, [("post", _read(F_B, 10, pid=pid2)), ("stop", _stop(pid=pid2))])
            chk = _last_stopcheck(led)
            assert chk["result"] == "skip_unqualified" and chk["n_edited"] == 0, (pid1, pid2, with_marker, chk)


def test_sessions_do_not_leak_into_each_other():
    # 必須「交錯」且 pid 相同:順序排列時 B 的 Prompt 標記本來就把 A 切掉,拿掉 sid 過濾也不會變紅(審查以突變證實)
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt(sid="A")), ("prompt", _prompt(sid="B")),
                    ("post", _edit(F_A, sid="A")), ("post", _read(F_B, 5, sid="B")), ("stop", _stop(sid="B"))])
        chk = _last_stopcheck(led)
        assert chk["result"] == "skip_unqualified" and chk["n_edited"] == 0, chk


def test_subagent_activity_never_qualifies_the_main_turn():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        feed = [("prompt", _prompt())]
        feed += [("post", _read(os.path.join(ROOT, f"f{i}.md"), 500, agent_type="Explore")) for i in range(6)]
        feed += [("post", _edit(F_A, agent_type="general-purpose")),
                 ("post", _agent("counsel", "claude-opus-5-5", agent_type="general-purpose")),
                 ("stop", _stop())]
        _feed(led, feed)
        chk = _last_stopcheck(led)
        assert chk["result"] == "skip_unqualified", chk
        assert (chk["read_files"], chk["n_edited"], chk["counsel"]) == (0, 0, 0), chk


def test_edit_outside_repo_does_not_qualify():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _post("Write", {"file_path": OUTSIDE, "content": "x"})),
                    ("stop", _stop())])
        recs = _records(led)
        assert [r for r in recs if r["ev"] == "Write"][0]["in"] is False
        assert _last_stopcheck(led)["result"] == "skip_unqualified", "記憶/暫存檔不算實作"


def test_many_reads_qualify_and_flag_h1():
    paths = [os.path.join(ROOT, n) for n in ("ops.md", "CLAUDE.md", "check.sh", ".gitignore", "DESIGN.md")]
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt())] + [("post", _read(p, 300)) for p in paths[:4]] + [("stop", _stop())])
        assert _last_stopcheck(led)["result"] == "skip_unqualified", "4 檔不構成實作輪"
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt())] + [("post", _read(p, 300)) for p in paths])
        rc, out, _ = _run("stop", _stop(), led)
        reason = json.loads(out)["reason"]
        assert "讀而未改 5 檔約 1500 行" in reason and "已超過 H1 門檻" in reason, reason


def test_read_then_edit_same_file_is_not_read_only():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _read(F_A, 500)), ("post", _edit(F_A))])
        rc, out, _ = _run("stop", _stop(), led)
        assert "讀而未改 0 檔約 0 行" in json.loads(out)["reason"], out


def test_agent_dispatch_counts_and_dedupes_by_tool_use_id():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        dup = _agent("counsel", "claude-opus-5-5", tuid="same")
        _feed(led, [("prompt", _prompt()), ("post", _agent("scout", "claude-haiku-5-5")), ("post", dup), ("post", dup),
                    ("post", _agent("Explore"))])
        rc, out, _ = _run("stop", _stop(), led)
        reason = json.loads(out)["reason"]
        assert "scout 1、counsel 1、其他 1" in reason, reason


def test_is_counsel_prefers_resolved_model_then_override_and_fork_ignores_override():
    mod = _mod()
    yes = [{"st": "counsel"},
           {"st": "general-purpose", "rmodel": "claude-opus-5-5"},
           {"st": "general-purpose", "model": "opus"},                                  # 同步回應沒帶 resolvedModel:看 model 覆寫
           {"st": "counsel", "rmodel": "claude-haiku-5-5"}]                              # counsel 就是 counsel
    no = [{"st": "scout", "rmodel": "claude-haiku-5-5"},
          {"st": "general-purpose", "rmodel": None},
          {"st": "general-purpose", "model": "opus", "rmodel": "claude-sonnet-5-5"},     # 實際模型優先於覆寫
          {"st": "fork", "model": "opus"},                                              # fork 忽略 model 覆寫
          {"st": "general-purpose", "model": None}]
    for rec in yes:
        assert mod.is_counsel(rec), rec
    for rec in no:
        assert not mod.is_counsel(rec), rec


# ── 軟失敗 ────────────────────────────────────────────────────────────────

def test_internal_error_is_soft_and_noticed_once_per_session():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        rc, out, _ = _run("post", None, led, raw=b"{not json")
        assert rc == 0, "hook 內部錯誤必須 exit 0(不擋人)"
        j = json.loads(out)
        assert j["hookSpecificOutput"]["hookEventName"] == "PostToolUse", j
        assert "內部錯誤" in j["hookSpecificOutput"]["additionalContext"] and "systemMessage" in j, j
        rc, out, _ = _run("post", None, led, raw=b"[1, 2]")   # 同一 session(未知)第二次:只記錄、不再通知
        assert rc == 0 and out == "", out
        evs = [r["ev"] for r in _records(led)]
        assert evs.count("Error") == 2 and evs.count("ErrNotice") == 1, evs


def test_internal_error_in_stop_never_blocks():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        rc, out, _ = _run("stop", None, led, raw=b"garbage")
        assert rc == 0, rc
        j = json.loads(out)
        assert "decision" not in j and "systemMessage" in j, f"Stop 的錯誤通知不得是 block:{j}"


def test_unwritable_ledger_is_silent_and_exit_zero():
    with tempfile.TemporaryDirectory() as d:
        blocker = os.path.join(d, "afile")
        open(blocker, "w").close()
        led = os.path.join(blocker, "sub", "l.jsonl")   # 父層是檔案 → makedirs 必失敗
        rc, out, _ = _run("post", _read(F_A, 3), led)
        assert rc == 0 and out == "", (rc, out)
        rc, out, _ = _run("stop", _stop(), led)
        assert rc == 0, rc


def test_unknown_subcommand_is_not_a_hook_error():
    with tempfile.TemporaryDirectory() as d:
        rc, out, err = _run("bogus", {}, os.path.join(d, "l.jsonl"))
        assert rc == 0 and out == "" and "用法" in err, (rc, out, err)


def test_concurrent_appends_stay_intact():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        env = dict(os.environ, SLG_OPS_LEDGER=led)
        procs = []
        for i in range(32):
            p = subprocess.Popen([sys.executable, HOOK, "post"], stdin=subprocess.PIPE, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p.stdin.write(json.dumps(_read(F_A + "x" * 3000 + str(i), i, tuid=f"c{i}")).encode("utf-8"))
            p.stdin.close()
            procs.append(p)
        for p in procs:
            assert p.wait(timeout=60) == 0
            p.stdout.close()
            p.stderr.close()
        with open(led, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        assert len(lines) == 32, f"並發寫入掉行或交錯:{len(lines)}"
        assert {json.loads(ln)["tuid"] for ln in lines} == {f"c{i}" for i in range(32)}


# ── 里程碑窗(合成 git repo)────────────────────────────────────────────────

T0 = 1_700_000_000   # git 只認 ≥9 位數的 raw epoch;各測試用 T0 + 偏移


def _git_commit(d, ts, subject):
    # committer date 刻意設成 author date + 5000:模擬 rebase/amend 後 committer date 變新,邊界仍須取 author date
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_DATE=f"{ts} +0000", GIT_COMMITTER_DATE=f"{ts + 5000} +0000")
    cp = subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                         "commit", "--allow-empty", "-q", "-m", subject], capture_output=True, env=env)
    assert cp.returncode == 0, f"git commit 失敗:{cp.stderr.decode('utf-8', 'replace')}"


def _make_repo(d, commits):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    cp = subprocess.run(["git", "init", "-q", "-b", "main", d], capture_output=True, env=env)
    assert cp.returncode == 0, f"git init 失敗:{cp.stderr.decode('utf-8', 'replace')}"
    for ts, subject in commits:
        _git_commit(d, ts, subject)


def test_milestone_token_parsing():
    mod = _mod()
    cases = {"R171 續2:新增 O5": "R171", "R114C 經濟 QoL": "R114C", "R114D:長途旅行": "R114D", "R170 B2:run_all": "R170",
             "R171續:無空格": "R171", "R160c 服務": "R160c", "文件:CLAUDE.md 瘦身": None, "Revert \"R171\"": None,
             "Release notes": None, "": None}
    for subject, want in cases.items():
        assert mod.milestone_token(subject) == want, (subject, mod.milestone_token(subject), want)


def test_milestone_window_follows_r_prefix_not_commit_count():
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        _make_repo(d, [(T0 + 1000, "R169 a"), (T0 + 2000, "R170 x"), (T0 + 3000, "文件:neutral"),
                       (T0 + 4000, "R171 a"), (T0 + 5000, "R171 續 b"), (T0 + 6000, "R171 續2 c")])
        win = mod.milestone_window(d)
        assert win["token"] == "R171" and win["start_ts"] == T0 + 2000 and win["head_ts"] == T0 + 6000, win
        assert win["boundary"].endswith("R170 x"), win     # 無 R## 的提交不當邊界
        _git_commit(d, T0 + 7000, "R172 first")
        win = mod.milestone_window(d)
        assert win["token"] == "R172" and win["start_ts"] == T0 + 6000, win   # 新 R## 首次提交後,邊界 = 上個 R## 的最後一筆
        _git_commit(d, T0 + 8000, "R172 續")
        assert mod.milestone_window(d)["start_ts"] == T0 + 6000, "同 R## 多次提交算同一里程碑"
        _git_commit(d, T0 + 9000, "chore: 無前綴")
        win = mod.milestone_window(d)
        assert win["token"] == "R172" and win["start_ts"] == T0 + 6000 and win["head_ts"] == T0 + 9000, win


def test_milestone_window_uses_author_date_so_rebase_cannot_reset_it():
    # _git_commit 把 committer date 設成 author date + 5000(模擬 rebase/amend 後 committer date 變新);邊界仍取 author date
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        _make_repo(d, [(T0 + 2000, "R170 x"), (T0 + 4000, "R171 a")])
        win = mod.milestone_window(d)
        assert win["start_ts"] == T0 + 2000 and win["head_ts"] == T0 + 4000, win


def test_milestone_letter_suffix_is_a_separate_milestone():
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        _make_repo(d, [(T0 + 1000, "R160 base"), (T0 + 2000, "R160c 服務標記")])
        win = mod.milestone_window(d)
        assert win["token"] == "R160c" and win["start_ts"] == T0 + 1000, win


def test_milestone_window_edge_cases():
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        _make_repo(d, [(T0 + 1000, "no prefix at all"), (T0 + 2000, "still none")])
        win = mod.milestone_window(d)
        assert win["token"] is None and win["start_ts"] is None and win["head_ts"] == T0 + 2000, win
    with tempfile.TemporaryDirectory() as d:
        _make_repo(d, [(T0 + 1000, "R5 a"), (T0 + 2000, "R5 續")])   # 全歷史同一 R##:從頭算
        win = mod.milestone_window(d)
        assert win["token"] == "R5" and win["start_ts"] is None, win
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["GIT_CEILING_DIRECTORIES"] = os.path.dirname(d)   # 非 repo:不往上找到別人的 .git
        try:
            assert mod.milestone_window(d) is None
        finally:
            if old is None:
                os.environ.pop("GIT_CEILING_DIRECTORIES", None)
            else:
                os.environ["GIT_CEILING_DIRECTORIES"] = old


def test_counsel_counts_milestone_and_since_head():
    mod = _mod()
    win = {"token": "R171", "start_ts": 2000, "head_ts": 6000, "head": "abc1234", "boundary": "x"}

    def ag(ts, st, **kw):
        return {"ev": "Agent", "ts": ts, "st": st, "at": None, "tuid": kw.pop("tuid", f"u{ts}{st}"), **kw}

    recs = [ag(1500, "counsel"),                                   # 邊界前:屬上個里程碑
            ag(2500, "counsel"), ag(2500, "counsel", tuid="u2500counsel"),   # 重複 tuid 只算一次
            ag(2600, "scout"),
            ag(2700, "counsel", at="Explore"),                      # 子代理派的不算
            ag(2800, "general-purpose", rmodel="claude-opus-5-5"),  # 實際用到 Opus 算
            ag(6500, "counsel"),                                    # 最近提交之後
            {"ev": "Read", "ts": 3000, "at": None}]
    assert mod.counsel_counts(recs, win) == (3, 1), mod.counsel_counts(recs, win)
    assert mod.counsel_counts(recs, None) == (4, 4), "邊界未知(無 git)就從頭算(1500、2500、2800、6500)"


# ── 帳本路徑 / status / 文件 ────────────────────────────────────────────────

def test_ledger_path_env_override_and_default_is_repo_local_and_gitignored():
    mod = _mod()
    assert str(mod.DEFAULT_LEDGER) == os.path.join(ROOT, ".claude", "ledger", "ops.jsonl")
    with _ledger_env("/x/y.jsonl"):
        assert mod.ledger_path() == "/x/y.jsonl"
    old = os.environ.pop("SLG_OPS_LEDGER", None)
    try:
        assert mod.ledger_path() == str(mod.DEFAULT_LEDGER)
    finally:
        if old is not None:
            os.environ["SLG_OPS_LEDGER"] = old
    ignored = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read().splitlines()
    assert ".claude/ledger/" in ignored, "帳本目錄必須 gitignore(含機器本地資料,不進版控)"


def test_default_ledger_follows_script_location_not_the_real_repo():
    # 把腳本複製到暫存「專案」下、不設 SLG_OPS_LEDGER:帳本應落在該專案的 .claude/ledger/(證明預設路徑由腳本位置推得)
    with tempfile.TemporaryDirectory() as d:
        hooks = os.path.join(d, ".claude", "hooks")
        os.makedirs(hooks)
        copy = os.path.join(hooks, "ops_ledger.py")
        shutil.copy(HOOK, copy)
        rc, out, err = _run("post", _read(F_A, 7), "unused", env_remove=("SLG_OPS_LEDGER",), hook=copy)
        assert rc == 0 and out == "", (rc, out, err)
        assert os.path.exists(os.path.join(d, ".claude", "ledger", "ops.jsonl")), "預設帳本應在腳本所屬專案下"


def test_status_prints_last_record_counsel_and_errors():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _read(F_A, 9)), ("post", _agent("counsel", "claude-opus-5-5"))])
        rc, out, err = _run("status", None, led, raw=b"")
        assert rc == 0, err
        for needle in ("帳本:" + led, "最後一筆", "counsel(Opus 派遣)", "內部錯誤:0 筆", "子代理內的呼叫"):
            assert needle in out, f"status 缺 {needle!r}:\n{out}"
        empty = os.path.join(d, "none.jsonl")
        rc, out, _ = _run("status", None, empty, raw=b"")
        assert rc == 0 and "空或不存在" in out, out


def test_ops_md_documents_ledger_hook_and_wiring_snippet_is_valid():
    ops = open(os.path.join(ROOT, "ops.md"), encoding="utf-8").read()
    for needle in ("SLG_OPS_LEDGER", "ops_ledger.py", "提交訊息開頭的 R##", "settings.local.json", "agent_type", "stop_hook_active",
                   "skip_no_msg", "SendMessage",
                   # R175:大文本自讀偵測的文件關鍵詞(門檻/關閉開關/失敗事件/產生接線的子命令)
                   "PostToolUseFailure", "SLG_OPS_BIGDOC", "大文本自讀", "ops_ledger.py wiring", "persistedOutputSize"):
        assert needle in ops, f"ops.md 缺 hook 文件關鍵詞:{needle}"
    blocks = re.findall(r"```json\n(.*?)\n```", ops, re.S)
    wiring = [json.loads(b) for b in blocks if '"hooks"' in b]
    assert wiring, "ops.md 須附可複製的 hooks 接線 JSON(也是試跑時放進 settings.local.json 的內容)"
    hooks = wiring[0]["hooks"]
    assert set(hooks) == {"PostToolUse", "PostToolUseFailure", "UserPromptSubmit", "Stop"}, sorted(hooks)
    post = hooks["PostToolUse"][0]
    # Bash/Grep 加進 matcher 是 R175 的偵測面(對應 ops.md H2 硬規則);少了就看不到「Bash 印大文本」
    assert set(post["matcher"].split("|")) == {"Read", "Edit", "Write", "Agent", "Bash", "Grep"}, post["matcher"]
    # 失敗的 Bash(exit≠0)走另一個事件,輸出在 payload 的 error 欄(2026-11 實測);只接 Bash
    assert set(hooks["PostToolUseFailure"][0]["matcher"].split("|")) == {"Bash"}, hooks["PostToolUseFailure"]
    assert wiring[0]["permissions"]["allow"] == ["Bash(python3 .claude/hooks/ops_ledger.py status)"], wiring[0].get("permissions")
    for event, sub in (("PostToolUse", "post"), ("PostToolUseFailure", "post"), ("UserPromptSubmit", "prompt"), ("Stop", "stop")):
        assert len(hooks[event]) == 1 and len(hooks[event][0]["hooks"]) == 1, f"{event} 應各只接一條"
        h = hooks[event][0]["hooks"][0]
        want = f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/ops_ledger.py" {sub} || exit 1'
        # `|| exit 1`:python 找不到腳本時 exit code 是 2,而 Stop hook 的 exit 2 = 擋下結束並把 stderr 餵給模型
        # (腳本被刪/切分支後 settings 仍在 → 可能無限續跑);任何啟動失敗必須降為 exit 1(非阻擋、看得見)
        assert h["type"] == "command" and h["command"] == want, f"接線命令須為 {want!r},實際 {h.get('command')!r}"
        assert "onFailure" not in h, "不設 onFailure:block(使用者拍板:看得見但不擋人)"
    assert os.path.exists(HOOK)

# ── R172 審查後補:修法回歸 + 補上「測試空轉」的缺口 ───────────────────────────

def _stats(**kw):
    base = {"edited": [], "n_edited": 0, "read_files": 0, "read_lines": 0, "ro_files": 0, "ro_lines": 0,
            "scout": 0, "counsel": 0, "other": 0, "qualifies": True}
    base.update(kw)
    return base


def test_build_reason_pins_counsel_slot_and_both_branches():
    mod = _mod()
    win = {"token": "R171", "head": "abc1234"}
    same = mod.build_reason(_stats(), 1, 1, win)
    assert same.splitlines()[-1].endswith("|counsel 1/2"), same
    assert "亦為 1" in same and "以後者為準" not in same and "R171" in same and "abc1234" in same, same
    diff = mod.build_reason(_stats(), 2, 0, win)
    assert diff.splitlines()[-1].endswith("|counsel <2 或 0>/2"), diff
    assert "本里程碑 2/2(R171 起算);自最近提交 abc1234 後 0" in diff and "以後者為準" in diff, diff
    over = mod.build_reason(_stats(ro_files=5, ro_lines=1500), 0, 0, win)
    assert "已超過 H1 門檻" in over and "須寫理由" in over, over
    ok = mod.build_reason(_stats(ro_files=2, ro_lines=550), 0, 0, None)   # 無 git:token/head 顯示 ?
    assert "未超過 H1 門檻" in ok and "須寫理由" not in ok and "(? 起算" in ok, ok


def test_handle_stop_wires_counsel_numbers_into_the_reason():
    mod = _mod()
    win = {"token": "R171", "start_ts": 2000.0, "head_ts": 6000.0, "head": "abc1234", "boundary": "x"}
    with tempfile.TemporaryDirectory() as d, _ledger_env(os.path.join(d, "l.jsonl")):
        mod.milestone_window = lambda repo=None: win     # 合成邊界,不依賴真 repo 歷史
        base = {"sid": "s1", "pid": "p1", "at": None}
        mod.append_record({**base, "ts": 2500, "ev": "Agent", "st": "counsel", "tuid": "a"})   # 本里程碑內、最近提交前
        mod.append_record({**base, "ts": 6500, "ev": "Agent", "st": "counsel", "tuid": "b"})   # 最近提交後
        mod.append_record({**base, "ts": 1500, "ev": "Agent", "st": "counsel", "tuid": "c"})   # 邊界前:上個里程碑
        mod.append_record({**base, "ts": 7000, "ev": "Prompt"})
        mod.append_record({**base, "ts": 7001, "ev": "Edit", "path": F_A, "in": True})
        out = mod.handle_stop({"session_id": "s1", "prompt_id": "p1", "last_assistant_message": "完成"})
        assert out["decision"] == "block", out
        assert out["reason"].splitlines()[-1].endswith("|counsel <2 或 1>/2"), out["reason"]
        assert "counsel 本里程碑 2/2(R171 起算);自最近提交 abc1234 後 1" in out["reason"], out["reason"]


def test_fmt_edited_is_relative_truncated_and_keeps_outside_paths():
    mod = _mod()
    text = mod._fmt_edited([os.path.join(ROOT, f"f{i}.md") for i in range(8)])
    assert text == "f0.md、f1.md、f2.md、f3.md、f4.md、f5.md 等 8 個", text
    assert mod._fmt_edited([OUTSIDE]) == OUTSIDE
    assert mod._fmt_edited([os.path.join(ROOT, "ops.md"), OUTSIDE]) == "ops.md、" + OUTSIDE


def test_status_window_counts_split_main_and_subagent_and_respect_boundary():
    mod = _mod()
    win = {"token": "R9", "start_ts": 2000.0, "head_ts": 9000.0, "head": "abc1234", "boundary": "x"}
    with tempfile.TemporaryDirectory() as d, _ledger_env(os.path.join(d, "l.jsonl")):
        mod.milestone_window = lambda repo=None: win
        for ts, ev, extra in ((1500, "Read", {}),                                  # 邊界前:不計
                              (2500, "Read", {}), (2600, "Read", {}), (2700, "Edit", {}),
                              (2800, "Read", {"at": "Explore"}),                    # 子代理:另列
                              (2900, "Agent", {"st": "scout"})):
            mod.append_record({"ts": ts, "ev": ev, "sid": "s", "at": None, "path": "/p", **extra})
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            assert mod.status() == 0
        finally:
            sys.stdout = old
        assert "主對話 Agent 1、Edit 1、Read 2;子代理內的呼叫 1 筆" in buf.getvalue(), buf.getvalue()


def test_fail_soft_notifies_once_per_session_and_names_the_right_event():
    mod = _mod()
    with tempfile.TemporaryDirectory() as d, _ledger_env(os.path.join(d, "l.jsonl")):
        assert mod.fail_soft("post", ValueError("x"), {"session_id": "A"}) is not None
        assert mod.fail_soft("post", ValueError("x"), {"session_id": "A"}) is None
        assert mod.fail_soft("stop", ValueError("y"), {"session_id": "B"}) is not None   # 另一個 session 各通知一次
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        rc, out, _ = _run("prompt", None, led, raw=b"{bad")
        assert rc == 0 and json.loads(out)["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit", out


def test_milestone_window_falls_back_to_head_when_there_is_no_main_branch():
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(["git", "init", "-q", "-b", "trunk", d], check=True, capture_output=True, env=env)
        _git_commit(d, T0 + 1000, "R1 a")
        _git_commit(d, T0 + 2000, "R2 b")
        win = mod.milestone_window(d)
        assert win is not None and win["token"] == "R2" and win["start_ts"] == T0 + 1000, win


def test_load_records_skips_bad_lines_and_only_reads_the_tail_when_huge():
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        good = [json.dumps({"ts": i, "ev": "Read", "path": f"/p{i}"}) for i in range(6)]
        with open(led, "w", encoding="utf-8") as f:
            f.write("\n".join(good[:2] + ["{broken", "", "[1,2]", "null"] + good[2:]) + "\n")
        assert [r["path"] for r in mod.load_records(led)] == [f"/p{i}" for i in range(6)]
        # 超過上限只讀尾端。(a) 截點落在前一行中間:殘段是壞 JSON,自然略過
        mod.MAX_TAIL_BYTES = len(good[5]) + len(good[4]) + 2 + 5
        assert [r["path"] for r in mod.load_records(led)] == ["/p4", "/p5"]
        # (b) 截點剛好在行首:那一行是完整記錄,不可被誤丟(舊版硬丟第一行會只剩 /p5)
        mod.MAX_TAIL_BYTES = len(good[5]) + len(good[4]) + 2
        assert [r["path"] for r in mod.load_records(led)] == ["/p4", "/p5"]


def test_in_repo_rejects_sibling_prefix():
    mod = _mod()
    root = str(mod.ROOT)
    assert mod._in_repo(root) and mod._in_repo(root + "/a/b.md")
    assert not mod._in_repo(root + "2/a.md"), "兄弟目錄(同前綴)不是 repo 內"
    assert not mod._in_repo("/etc/passwd")


def test_edit_through_a_symlinked_project_root_still_counts_as_in_repo():
    # 腳本以 .resolve() 推根;專案若經符號連結進入,Edit 給的是邏輯路徑 → 兩種根都要認,否則永不提醒(審查重現)
    with tempfile.TemporaryDirectory() as d:
        real = os.path.join(d, "real")
        os.makedirs(os.path.join(real, ".claude", "hooks"))
        shutil.copy(HOOK, os.path.join(real, ".claude", "hooks", "ops_ledger.py"))
        link = os.path.join(d, "link")
        os.symlink(real, link)
        led = os.path.join(d, "l.jsonl")
        script = os.path.join(link, ".claude", "hooks", "ops_ledger.py")
        for path in (os.path.join(link, "a.md"), os.path.join(real, "b.md")):
            rc, out, err = _run("post", _edit(path), led, hook=script)
            assert rc == 0 and out == "", (rc, out, err)
        assert [r["in"] for r in _records(led)] == [True, True]


def test_unicode_line_separators_do_not_split_a_record():
    # splitlines() 也在 U+2028/U+2029/U+0085 斷行,而 JSON 不跳脫它們:舊版會把一筆劈成兩段壞 JSON、整筆消失
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        p = _agent("counsel", "claude-opus-5-5")
        p["tool_input"]["description"] = "a\u2028b\u2029c\u0085d"
        _feed(led, [("post", p)])
        with open(led, "rb") as f:
            assert f.read().count(b"\n") == 1
        recs = mod.load_records(led)
        assert len(recs) == 1 and recs[0]["desc"] == "a\u2028b\u2029c\u0085d", recs
        rc, out, _ = _run("status", None, led, raw=b"")
        assert "空或不存在" not in out and "1 筆" in out, out   # 「hook 沒載入」字樣在非空帳本的判讀提示裡也會出現,不能拿來區分


def test_torn_tail_is_repaired_on_the_next_append():
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("post", _read(F_A, 1)), ("post", _read(F_A, 2))])
        with open(led, "rb+") as f:                         # 去掉結尾換行:最後一筆完整,只是沒收尾
            f.seek(-1, os.SEEK_END)
            f.truncate()
        _feed(led, [("post", _read(F_A, 3))])
        assert [r["n"] for r in mod.load_records(led)] == [1, 2, 3]
        with open(led, "ab") as f:                          # 殘行:寫到一半
            f.write(b'{"ts":1,"ev":"Read","pa')
        _feed(led, [("post", _read(F_A, 4))])
        assert [r["n"] for r in mod.load_records(led)] == [1, 2, 3, 4], "殘行只能害到自己,不能吃掉下一筆"
        assert os.stat(led).st_mode & 0o777 == 0o600, "帳本權限應為 0600"


def test_check_line_regex_is_linear_on_blank_lines_and_keeps_its_meaning():
    mod = _mod()
    t = time.time()
    assert mod.CHECK_LINE_RE.search("\n" * 200_000) is None
    assert mod.CHECK_LINE_RE.search(" \t" * 100_000 + "\n" * 50_000) is None
    assert time.time() - t < 3.0, "行首辨識不得對連續空白行二次方回溯(舊式 \\s 版 10 萬換行約 9.5 秒,逼近 hook timeout)"
    cases = (("代理檢查|x", True), ("  代理檢查|x", True), ("\u3000代理檢查|x", True), ("**代理檢查**|x", True),
             ("> 代理檢查", True), ("- 代理檢查", True), ("### 代理檢查", True), ("`代理檢查|x`", True),
             ("前言\n\n代理檢查|x", True), ("我忘了寫代理檢查", False), ("1. 代理檢查", False), ("", False))
    for msg, want in cases:
        assert bool(mod.CHECK_LINE_RE.search(msg)) is want, (msg, want)


def test_poisoned_ledger_records_cannot_break_the_stats():
    # 手改/壞掉的記錄(path、tuid 是 list/dict):舊版 TypeError → 之後永遠不提醒、status 崩潰
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt())])
        with open(led, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": 1, "sid": "s1", "pid": "p1", "ev": "Read", "path": ["x"], "n": 5, "tuid": {"k": 1}}) + "\n")
            f.write(json.dumps({"ts": 2, "sid": "s1", "pid": "p1", "ev": "Agent", "st": "counsel", "tuid": ["a"]}) + "\n")
        _feed(led, [("post", _edit(F_A))])
        rc, out, err = _run("stop", _stop(), led)
        assert rc == 0 and json.loads(out).get("decision") == "block", f"毒記錄不得讓提醒變成內部錯誤:{out}"
        rc, out, err = _run("status", None, led, raw=b"")
        assert rc == 0 and "Traceback" not in err and "帳本:" in out, (rc, err)
        _feed(led, [("post", dict(_agent("counsel", "claude-opus-5-5"), tool_use_id=["z"]))])
        assert _records(led)[-1]["tuid"] is None, "寫入端只收字串 tuid"


def test_stop_without_last_assistant_message_passes_and_status_warns():
    # 看不到最後訊息就無從判斷模型是否已寫那行:放行(不擋人)並在 status 警告,而不是每個實作輪都 block 一次
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _edit(F_A))])
        payload = _stop()
        del payload["last_assistant_message"]
        rc, out, err = _run("stop", payload, led)
        assert rc == 0 and out == "", (out, err)
        chk = _last_stopcheck(led)
        assert chk["result"] == "skip_no_msg" and chk["has_msg"] is False, chk
        payload["last_assistant_message"] = ["not", "a", "string"]          # 非字串同樣當作看不到
        assert _run("stop", payload, led)[1] == ""
        rc, out, _ = _run("status", None, led, raw=b"")
        assert "沒有 last_assistant_message" in out, out


def test_unqualified_turn_is_skipped_before_the_no_msg_check():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _read(F_A, 5))])
        payload = _stop()
        del payload["last_assistant_message"]
        _feed(led, [("stop", payload)])
        assert _last_stopcheck(led)["result"] == "skip_unqualified"



# ── R175:大文本自讀偵測(ops.md H2 硬規則:主對話不印大文本內文)────────────────
# 訊號 = 輸出中「長度 > 40、含中文的行」的中文字數(對應鐵令:只准數字/ID/行號/≤40 字定位片段);
# 本輪累計跨過 WARN(150)當場提醒模型、跨過 ALARM(600)再提醒使用者;只計主對話;git 非讀內文子命令豁免。

def _prose(n):
    """單一長行、n 個中文字:n > 40 時 _cjk_prose 整行計入。"""
    return "測" * n


def _bash(cmd, stdout="", stderr="", sid="s1", pid="p1", agent_type=None, size=None, event="PostToolUse", error=None):
    p = {"hook_event_name": event, "session_id": sid, "prompt_id": pid, "tool_name": "Bash",
         "tool_input": {"command": cmd}, "tool_use_id": f"tu-{next(_seq)}"}
    if event == "PostToolUseFailure":
        p["error"] = error if error is not None else "Exit code 1\n" + stdout   # 2026-11 實測:error 內含 exit code 與先印出的輸出
    else:
        tr = {"stdout": stdout, "stderr": stderr, "interrupted": False, "isImage": False, "noOutputExpected": False}
        if size is not None:
            tr["persistedOutputSize"] = size
        p["tool_response"] = tr
    if agent_type:
        p["agent_type"] = agent_type
        p["agent_id"] = "agent-1"
    return p


def _grep(path, content, sid="s1", pid="p1"):
    return {"hook_event_name": "PostToolUse", "session_id": sid, "prompt_id": pid, "tool_name": "Grep",
            "tool_input": {"pattern": "x", "path": path, "output_mode": "content"},
            "tool_response": {"mode": "content", "numFiles": 0, "filenames": [], "content": content,
                              "numLines": 1, "totalLines": 1},
            "tool_use_id": f"tu-{next(_seq)}"}


def _write(path, content, **kw):
    return _post("Write", {"file_path": path, "content": content}, {}, **kw)


def _read_big(path, content, **kw):
    return _post("Read", {"file_path": path},
                 {"type": "text", "file": {"filePath": path, "content": content, "numLines": 1,
                                           "startLine": 1, "totalLines": 1}}, **kw)


def _bd(led):
    return [r for r in _records(led) if r["ev"] == "BigDoc"]


def test_prose_metric_counts_only_long_cjk_lines():
    mod = _mod()
    assert mod._cjk_prose("") == 0 and mod._cjk_prose(None) == 0
    assert mod._cjk_prose(_prose(40)) == 0, "長度恰 40 的行不算(鐵令:≤40 字定位片段可以)"
    assert mod._cjk_prose(_prose(41)) == 41
    assert mod._cjk_prose("a" * 200) == 0, "純 ASCII 長行(ID 清單、路徑、git 輸出)不算"
    assert mod._cjk_prose("x" * 60 + "測試" + "y" * 5) == 2, "混合長行只計中文字"
    assert mod._cjk_prose(_prose(10) + "\n" + _prose(50) + "\n" + _prose(45)) == 95, "逐行判斷、加總"


def test_mentions_big_covers_names_and_data_dir():
    mod = _mod()
    assert mod._mentions_big("python3 x.py handoff.md BESTIARY.md") == ["handoff.md", "BESTIARY.md"]
    assert mod._mentions_big("cat tesrpg/data/quests.json") == ["quests.json", "tesrpg/data"]
    assert mod._mentions_big("cat tesrpg/data/world.json") == ["tesrpg/data"]
    assert mod._mentions_big("ls") == [] and mod._mentions_big(None) == []


def test_git_exemption_only_for_non_content_subcommands():
    mod = _mod()
    for ok in ("git log --oneline -- handoff.md", "git status --short", "git add handoff.md && git commit -m x",
               "cd /home/x && git push origin main", "git -C /repo log -3", "git diff --stat HEAD -- handoff.md",
               "git diff --numstat", "git show --stat HEAD", "git rev-list --count HEAD",
               "git -c core.quotepath=off log --oneline", "git log --stat -- handoff.md", "git diff --stat=200 -- x",
               # R175 審查 #10:前綴的各種寫法(分號、子殼、環境變數、env、路徑式 git、換行、帶值的全域選項)
               "cd /x; git log --oneline -3 -- handoff.md", "(cd /x && git log --oneline)", "GIT_PAGER=cat git log --oneline",
               "/usr/bin/git log --oneline", "cd .\ngit log --oneline", "env git log --oneline",
               "git --git-dir .git log --oneline", "git --no-pager log -5", "cd a && cd b && git status",
               "git diff --name-only", "git diff --name-status", "git diff --shortstat",
               "git branch -a", "git ls-files", "git check-ignore -v x", "git commit -m 'x'", "git push"):
        assert mod._git_exempt(ok), ok
    for bad in ("git diff HEAD -- handoff.md", "git show HEAD:handoff.md", "python3 x.py handoff.md",
                "cat handoff.md", "echo git log", "", "git",
                # log/diff/show 帶 -p 之類就印出檔案內文(堵「git log -p 讀 handoff」的繞法)
                "git log -p -- handoff.md", "git log --stat -p", "git log -u -3", "git log --patch",
                "git log --word-diff -- handoff.md", "git diff --stat -p", "git show --stat --patch HEAD",
                "git blame handoff.md", "git grep -n x handoff.md",
                # R175 審查 #6:原旗標清單漏掉的(實測都被豁免而印出整份內文)
                "git log -c -- handoff.md", "git log -L1,3:handoff.md", "git log -U1 -- handoff.md",
                "git log --unified=1 -- handoff.md", "git log --binary -- handoff.md", "git log --cc",
                "git log --patch-with-stat", "git log --patch-with-raw", "git diff --stat -U1 HEAD~1 -- handoff.md",
                "git show --stat HEAD:handoff.md", "git show --stat v1.0:docs/handoff.md",
                "cd /x; cat handoff.md", "cd .\ncat handoff.md", "FOO=1 python3 x.py handoff.md"):
        assert not mod._git_exempt(bad), bad


def test_clean_bash_never_touches_the_ledger():
    # 一般 Bash(測試、git、計數)輸出沒有中文長行 → 快速路徑:不寫、也不讀帳本(每個 Bash 都會啟動一次 hook,成本要壓低)
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        rc, out, err = _run("post", _bash("python3 tests/run_all.py", stdout="✓ test_x\n" * 50), led)
        assert (rc, out) == (0, "") and not os.path.exists(led), (out, err)
        # 短中文行(≤40 字)即使提到大文本也不記帳:鐵令允許 ≤40 字定位片段
        rc, out, _ = _run("post", _bash("grep -n 里程碑 handoff.md", stdout=("測" * 30 + "\n") * 20), led)
        assert (rc, out) == (0, "") and not os.path.exists(led)


def test_bash_big_doc_output_records_metadata_only():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        cmd = "python3 -c \"open('handoff.md'); print('SECRET-CMD')\""
        rc, out, err = _run("post", _bash(cmd, stdout=_prose(100) + "SECRET-OUT"), led)
        assert (rc, out) == (0, ""), (out, err)   # 100 < WARN:只記帳,不提醒
        [r] = _bd(led)
        assert (r["via"], r["gate"], r["docs"], r["prose"], r["at"]) == ("Bash", "doc", ["handoff.md"], 100, None), r
        assert r["bytes"] == 100 * 3 + len("SECRET-OUT"), r
        raw = open(led, encoding="utf-8").read()
        for secret in ("SECRET-CMD", "SECRET-OUT", "測測測"):
            assert secret not in raw, f"帳本不得存指令文字或輸出內容:{secret}"


def test_cumulative_prose_warns_once_per_threshold_and_only_alarm_tells_the_user():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt())])
        outs = []
        for n in (100, 100, 100, 100, 400, 100):   # 累計 100,200,300,400,800,900
            rc, out, err = _run("post", _bash("python3 scan.py handoff.md", stdout=_prose(n)), led)
            assert rc == 0, err
            outs.append(json.loads(out) if out else None)
        assert outs[0] is None, "100 字 < WARN(150):不提醒"
        warn = outs[1]
        assert warn and set(warn) == {"hookSpecificOutput"}, warn   # WARN:只給模型,不發 systemMessage(不吵使用者)
        hs = warn["hookSpecificOutput"]
        assert hs["hookEventName"] == "PostToolUse" and "H2" in hs["additionalContext"], hs
        # 注意:固定模板本身就含「handoff.md/BESTIARY.md」,單查檔名是恆真;要查只有動態段才有的「涉及 …)」
        assert "涉及 handoff.md)" in hs["additionalContext"] and "scout" in hs["additionalContext"], hs
        assert outs[2] is None and outs[3] is None, "同一門檻本輪只提醒一次"
        alarm = outs[4]   # 累計 800 ≥ ALARM(600):另發 systemMessage 給使用者
        assert alarm and "800" in alarm["systemMessage"] and "additionalContext" in alarm["hookSpecificOutput"], alarm
        assert outs[5] is None, "ALARM 本輪也只提醒一次"
        assert sorted(r["lvl"] for r in _records(led) if r["ev"] == "BDWarn") == [1, 2]
        # 新的一輪從零算
        _run("prompt", _prompt(), led)
        assert _run("post", _bash("python3 scan.py handoff.md", stdout=_prose(100)), led)[1] == ""
        assert _run("post", _bash("python3 scan.py handoff.md", stdout=_prose(100)), led)[1] != "", "新一輪重新累計,再度跨過 WARN"


def test_subagent_bash_is_neither_recorded_nor_warned():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        rc, out, _ = _run("post", _bash("cat handoff.md", stdout=_prose(5000), agent_type="Explore"), led)
        assert (rc, out) == (0, "") and not os.path.exists(led), "scout 讀大文本是本職:不記、不提醒"


def test_git_commands_over_a_big_doc_are_exempt_but_git_diff_counts():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led)
        rc, out, _ = _run("post", _bash("git log --oneline -- handoff.md", stdout=_prose(900)), led)
        assert (rc, out) == (0, ""), "git log 豁免:不提醒"
        [r] = _bd(led)
        assert r["ex"] is True and r["gate"] == "doc", r
        rc, out, _ = _run("post", _bash("git diff HEAD -- handoff.md", stdout=_prose(200)), led)
        assert out and "H2" in json.loads(out)["hookSpecificOutput"]["additionalContext"], "git diff 讀內文:計入並提醒"
        mod = _mod()
        stats = mod.turn_stats(mod.turn_records(_records(led), "s1", "p1"))
        assert stats["bd_prose"] == 200 and stats["bd_n"] == 1, stats


def test_taint_links_throwaway_scripts_to_big_docs_but_not_repo_files():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        scratch = os.path.join(d, "scratch", "scan_docs.py")      # repo 外的腳本檔
        _feed(led, [("prompt", _prompt()),
                    ("post", _write(scratch, "import json\nprint(open('handoff.md').read()[:300])\n")),
                    ("post", _write(F_A, "ops.md 提到 handoff.md 與 quests.json")),        # repo 內的文件/程式不 taint
                    ("post", _write(os.path.join(d, "scratch", "notes.txt"), "handoff.md"))])   # 非腳本副檔名不 taint
        writes = [r for r in _records(led) if r["ev"] == "Write"]
        assert [r.get("bdm") for r in writes] == [["handoff.md"], None, None], writes
        rc, out, _ = _run("post", _bash(f"python3 {scratch}", stdout=_prose(200)), led)   # 指令沒提到檔名,但引用 taint 腳本
        [r] = _bd(led)
        assert (r["gate"], r.get("taint"), r.get("docs")) == ("doc", True, None), r
        assert out and "(經腳本檔)" in json.loads(out)["hookSpecificOutput"]["additionalContext"], out
        # 指令用變數拼路徑時,以檔名子字串比對
        _run("post", _bash("SP=/x && python3 $SP/scan_docs.py", stdout=_prose(60)), led)
        assert _bd(led)[-1]["gate"] == "doc" and _bd(led)[-1]["taint"] is True
        # 其他腳本:只當盲點提示
        _run("post", _bash("python3 /tmp/other_script.py", stdout=_prose(60)), led)
        assert _bd(led)[-1]["gate"] == "none"


def test_failure_event_counts_error_text_and_replies_with_the_right_event_name():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        p = _bash("python3 x.py handoff.md", event="PostToolUseFailure", error="Exit code 3\n" + _prose(200))
        rc, out, err = _run("post", p, led)
        assert rc == 0, err
        [r] = _bd(led)
        assert r["fail"] is True and r["gate"] == "doc" and r["prose"] == 200, r
        assert json.loads(out)["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure", out


def test_grep_counts_when_path_mentions_a_big_doc_else_only_a_hint():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("post", _grep(F_C, _prose(100)), led)
        _run("post", _grep(os.path.join(ROOT, "tests"), _prose(100)), led)
        a, b = _bd(led)
        assert (a["via"], a["gate"], a["docs"]) == ("Grep", "doc", ["handoff.md"]), a
        assert (b["via"], b["gate"]) == ("Grep", "none"), b


def test_persisted_output_size_is_the_real_size():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("post", _bash("cat handoff.md", stdout=_prose(30000), size=90_001), led)   # 輸出被截成 3 萬字,實際 9 萬多
        [r] = _bd(led)
        assert r["bytes"] == 90_001 and r["prose"] == 30000, r


def test_big_doc_payload_shapes_never_crash():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        for p in (_post("Bash", {"command": "cat handoff.md"}, "plain string response"),
                  _post("Bash", {"command": "cat handoff.md"}, {"stdout": ["not", "str"], "stderr": None}),
                  _post("Bash", "oops", {"stdout": _prose(100)}),
                  _post("Bash", {"command": 123}, {"stdout": _prose(100), "persistedOutputSize": True}),
                  _post("Grep", {"path": None}, {"content": 5}),
                  _post("Read", {"file_path": F_C}, {"file": {"content": 12345}})):
            rc, out, err = _run("post", p, led)
            assert rc == 0 and "Traceback" not in err, (p["tool_name"], err)
        assert not [r for r in _records(led) if r["ev"] == "Error"], "不得走到軟失敗路徑"


def test_read_of_big_doc_counts_at_stop_but_read_before_edit_is_exempt():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _read_big(F_C, _prose(300)))])
        rc, out, _ = _run("stop", _stop(msg="完成。"), led)
        j = json.loads(out)   # Q&A 輪也納入(自讀達門檻),缺行 → 提醒
        assert j["decision"] == "block" and "大文本自讀" in j["reason"] and "約 300 字" in j["reason"], j
        assert j["reason"].splitlines()[-1].count("|大文本自讀:") == 1, j["reason"].splitlines()[-1]
        assert _last_stopcheck(led)["bd_prose"] == 300
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _read_big(F_C, _prose(300))), ("post", _edit(F_C))])
        rc, out, _ = _run("stop", _stop(msg="完成。"), led)
        j = json.loads(out)   # 有改檔 → 實作輪,缺行 → 提醒;但編輯前自讀(H2 例外)不計入
        assert BD_TOKEN_NEEDLE not in j["reason"].splitlines()[-1], j["reason"]
        assert _last_stopcheck(led)["bd_prose"] == 0


BD_TOKEN_NEEDLE = "大文本自讀"


def test_stop_token_flow_shares_one_reminder_budget():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led)
        _run("post", _bash("cat handoff.md", stdout=_prose(200)), led)   # 會當場提醒;這裡只要它入帳
        # 有「代理檢查」行但缺「大文本自讀」欄 → 提醒一次(只要求補欄)
        rc, out, _ = _run("stop", _stop(msg="完成。\n" + LINE), led)
        j = json.loads(out)
        assert j["decision"] == "block" and "缺「大文本自讀」欄" in j["reason"], j
        assert j["reason"].splitlines()[-1].startswith("大文本自讀:"), j["reason"]
        chk = _last_stopcheck(led)
        assert chk["result"] == "remind" and chk["why"] == "token", chk
        # 同輪再 Stop 與續跑(stop_hook_active)都放行:兩種缺漏共用同一個 Reminded 預算。
        # 順序有意義:先「同輪再 Stop」——若 remind 沒寫 Reminded,這裡就會再擋一次;
        # 若先測 active,它會順手補寫 Reminded 而掩蓋這個缺口(變異測試抓到過)。
        assert _run("stop", _stop(msg="完成。\n" + LINE), led)[1] == ""
        assert _last_stopcheck(led)["result"] == "skip_reminded"
        assert _run("stop", _stop(active=True, msg="完成。\n" + LINE), led)[1] == ""
        assert len([r for r in _records(led) if r["ev"] == "Reminded"]) == 1
    with tempfile.TemporaryDirectory() as d:   # 新的一輪:行與欄都有 → 放行
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led)
        _run("post", _bash("cat handoff.md", stdout=_prose(200)), led)
        rc, out, _ = _run("stop", _stop(msg="完成。\n" + LINE + "\n大文本自讀:0 節"), led)
        assert out == "" and _last_stopcheck(led)["result"] == "has_line"


def test_kill_switch_keeps_the_ledger_but_silences_feedback_and_stop():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        off = {"SLG_OPS_BIGDOC": "off"}
        _run("prompt", _prompt(), led, env_set=off)
        rc, out, _ = _run("post", _bash("cat handoff.md", stdout=_prose(900)), led, env_set=off)
        assert (rc, out) == (0, "") and len(_bd(led)) == 1, "關閉後仍記帳、但不提醒"
        rc, out, _ = _run("stop", _stop(msg="完成。"), led, env_set=off)
        assert out == "" and _last_stopcheck(led)["result"] == "skip_unqualified", "Q&A 輪不因自讀而納入"
        rc, out, _ = _run("status", None, led, raw=b"", env_set=off)
        assert "已停用" in out, out


def test_status_reports_bigdoc_totals():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led)
        _run("post", _bash("cat handoff.md", stdout=_prose(200)), led)
        _run("post", _read_big(F_C, _prose(50)), led)
        _run("post", _bash("python3 other.py", stdout=_prose(70)), led)   # 沒提到檔名 → 盲點提示
        rc, out, err = _run("status", None, led, raw=b"")
        assert rc == 0, err
        line = [ln for ln in out.splitlines() if ln.startswith("大文本自讀")]
        assert line, out
        for needle in ("Bash/Grep 約 200 字", "Read 約 50 字", "盲點提示", "約 70 字"):
            assert needle in line[0], f"status 缺 {needle!r}:{line[0]}"


def test_build_reason_bigdoc_variants_and_baseline_unchanged():
    mod = _mod()
    win = {"token": "R175", "head": "abc1234"}
    assert "大文本自讀" not in mod.build_reason(_stats(), 0, 0, win), "未達門檻:提醒與模板一字不動(舊測試釘死最後一行)"
    bd = mod.build_reason(_stats(bd_prose=200, bd_n=2, bd_docs=["handoff.md", "quests.json"], bd_session=450,
                                 bd_prefetch=80, bd_hint=700), 0, 0, win)
    assert "2 次約 200 字(涉及 handoff.md、quests.json);本 session 累計約 450 字" in bd, bd
    assert "編輯前自讀」約 80 字" in bd and "盲點提示:另有約 700 字" in bd, bd
    assert bd.splitlines()[-1].endswith("|大文本自讀:<N 節,應為 0;非 0 請列出>|counsel 0/2"), bd
    tok = mod.build_reason(_stats(bd_prose=200, bd_n=1, bd_docs=["handoff.md"], bd_session=200), 0, 0, win,
                           missing_line=False)
    assert "缺「大文本自讀」欄" in tok and tok.splitlines()[-1].startswith("大文本自讀:"), tok
    assert "大文本自讀" not in mod.build_reason(_stats(bd_prose=149), 0, 0, win), "149 < WARN(150):不納入"


def test_session_bigdoc_prose_sums_main_conversation_only():
    mod = _mod()
    me = {"sid": "s1", "at": None}
    recs = [
        {**me, "ev": "BigDoc", "gate": "doc", "prose": 100},                       # 計入
        {**me, "ev": "BigDoc", "gate": "doc", "prose": 70, "ex": True},            # git 豁免:不計
        {**me, "ev": "BigDoc", "gate": "none", "prose": 55},                       # 盲點提示:不計
        {**me, "ev": "Read", "bdp": 30},                                           # Read 大文本:計入
        {**me, "ev": "Read"},                                                      # 一般 Read:不計
        {"sid": "s1", "at": "scout", "ev": "BigDoc", "gate": "doc", "prose": 999},  # 子代理:不計
        {"sid": "s2", "at": None, "ev": "BigDoc", "gate": "doc", "prose": 999},    # 別的 session:不計
        {**me, "ev": "BigDoc", "gate": "doc", "prose": "垃圾"},                     # 毒化欄位:當 0,不崩潰
    ]
    assert mod.session_bigdoc_prose(recs, "s1") == 130
    # 端到端:跨輪累計進 Stop 提醒(擋「每輪滴漏」)
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(pid="p1"), led)
        _run("post", _bash("cat handoff.md", stdout=_prose(100), pid="p1"), led)
        _run("post", _read_big(F_C, _prose(80), pid="p1"), led)
        _run("prompt", _prompt(pid="p2"), led)
        _run("post", _bash("cat handoff.md", stdout=_prose(200), pid="p2"), led)
        j = json.loads(_run("stop", _stop(pid="p2", msg="完成。"), led)[1])
        assert "本 session 累計約 380 字" in j["reason"], j["reason"]


def test_taint_ref_matching_rules():
    mod = _mod()
    assert mod._is_tainted_ref({"/t/scan_docs.py"}, "python3 /t/scan_docs.py") == ["/t/scan_docs.py"], "整條路徑"
    assert mod._is_tainted_ref({"/t/scan_docs.py"}, "cd /x && python3 ./scan_docs.py") == ["/t/scan_docs.py"], "夠長的檔名"
    assert mod._is_tainted_ref({"/t/x.py"}, "python3 /elsewhere/x.py") == [], "檔名太短(< 6 字)不以子字串比對,免得 x.py 之類誤命中"
    assert mod._is_tainted_ref({"/t/x.py"}, "python3 /t/x.py") == ["/t/x.py"], "但整條路徑相同仍算"
    assert mod._is_tainted_ref(set(), "python3 whatever.py") == []


def test_wiring_subcommand_equals_constant_and_ops_md_snippet():
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        rc, out, err = _run("wiring", None, led, raw=b"")
        assert rc == 0 and not os.path.exists(led), err   # 只印到 stdout,不寫任何檔
        assert json.loads(out) == mod.WIRING
    ops = open(os.path.join(ROOT, "ops.md"), encoding="utf-8").read()
    blocks = [json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", ops, re.S) if '"hooks"' in b]
    assert blocks and blocks[0] == mod.WIRING, "ops.md §13 的接線 JSON 須與腳本內 WIRING 一致"
    local = os.path.join(ROOT, ".claude", "settings.local.json")
    if os.path.exists(local):   # 使用者已接線時,WIRING 的每一條都須在(允許另有其他 hook):舊版接線漂移會在這裡紅燈,提醒重跑 wiring
        have = json.load(open(local, encoding="utf-8")).get("hooks") or {}
        for event, entries in mod.WIRING["hooks"].items():
            for ent in entries:
                assert ent in (have.get(event) or []), f"settings.local.json 缺 {event} 接線(或與 WIRING 不一致):重跑 `ops_ledger.py wiring`"


# ── R175 審查後補:修法回歸 + 變異測試抓到的「測試空轉」缺口 ─────────────────────────────
# 審查代理對 hook 做了 135 個單點變異,68 個存活;下面把有意義的存活變異逐一補成會紅的測試。

def _after(posts, sid="s1"):
    """新帳本 → prompt → 依序餵 posts(每個 (指令, stdout));回 (最後一個 post 的輸出 dict 或 None, 全部帳本記錄)。"""
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(sid=sid), led)
        out = ""
        for cmd, stdout in posts:
            rc, out, err = _run("post", _bash(cmd, stdout=stdout, sid=sid), led)
            assert rc == 0, err
        return (json.loads(out) if out else None), _records(led)


def test_mod_isolates_the_bigdoc_kill_switch_from_the_environment():
    # 審查 #3:使用者照 ops.md 把 SLG_OPS_BIGDOC 設成 off,in-process 測試不得跟著變(否則 run_all 閘門紅)
    old = os.environ.get("SLG_OPS_BIGDOC")
    os.environ["SLG_OPS_BIGDOC"] = "off"
    try:
        assert _mod().bigdoc_enabled() is True
    finally:
        os.environ.pop("SLG_OPS_BIGDOC", None)
        if old is not None:
            os.environ["SLG_OPS_BIGDOC"] = old


def test_kill_switch_accepts_common_off_spellings():
    mod = _mod()
    try:
        for v, want in (("off", False), (" OFF ", False), ("0", False), ("false", False), ("No", False),
                        ("", True), ("on", True), ("1", True), ("yes", True)):
            os.environ["SLG_OPS_BIGDOC"] = v
            assert mod.bigdoc_enabled() is want, v
    finally:
        os.environ.pop("SLG_OPS_BIGDOC", None)


def test_line_path_and_grep_like_helpers():
    mod = _mod()
    for line, want in (("ops.md:12:內文", "ops.md"), ("./tesrpg/data/world.json:3:x", "./tesrpg/data/world.json"),
                       ("tesrpg/x.py:7:y", "tesrpg/x.py"), ("handoff.md:9", "handoff.md"),
                       ("2891:內文", None), ("R175:內文", None), ("- ops.md:內文", None),
                       ("https://x.y/z:abc", None), ("", None), ("沒有前綴的內文行", None)):
        assert mod._line_path(line) == want, line
    for cmd, want in (("grep -rn x .", True), ("cd /x && grep -n x f", True), ("LC_ALL=C grep x f", True), ("rg -n x", True),
                      ("git grep -n x -- f", True), ("/usr/bin/grep x f", True), ("(cd /x && grep x f)", True),
                      ("cat f | grep x", False), ("python3 grep.py", False), ("egrepx y", False), ("git log", False), ("", False)):
        assert mod._grep_like(cmd) is want, cmd


def test_grep_output_is_attributed_per_line_to_its_source_file():
    # 審查 #1:多檔 grep 只有一部分來自大文本、搜原始碼裡誰提到 quests.json 的輸出,都不該整條算自讀(實測 631 字誤報成 ALARM)
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        ops_lines = "\n".join(f"ops.md:{i}:" + "測" * 60 for i in range(1, 6))        # 300 字,來自非大文本
        ho_lines = "\n".join(f"handoff.md:{i}:" + "測" * 30 for i in range(1, 3))       # 2 × 30 = 60 字,來自大文本
        rc, out, _ = _run("post", _bash("grep -n R175 ops.md CLAUDE.md handoff.md", stdout=ops_lines + "\n" + ho_lines), led)
        [r] = _bd(led)
        assert (r["prose"], r["docs"], out) == (60, ["handoff.md"], ""), (r, out)
    with tempfile.TemporaryDirectory() as d:   # 搜原始碼:大文本名只是搜尋樣式,輸出來自別的檔 → 完全不入帳
        led = os.path.join(d, "l.jsonl")
        src = "\n".join(f"tesrpg/x{i}.py:{i}:    # 讀取 quests.json 之後" + "測" * 45 for i in range(1, 5))
        rc, out, _ = _run("post", _bash('grep -rn "quests.json" tesrpg tests --include=*.py', stdout=src), led)
        assert (rc, out) == (0, "") and not os.path.exists(led)
    with tempfile.TemporaryDirectory() as d:   # 漏報修補:遞迴 grep 命中 handoff.md,指令沒寫檔名也認得出來
        led = os.path.join(d, "l.jsonl")
        body = "\n".join(f"./handoff.md:{i}:" + "測" * 80 for i in range(1, 4))     # 240 字
        rc, out, _ = _run("post", _bash('grep -rn "R175" .', stdout=body), led)
        [r] = _bd(led)
        assert (r["gate"], r["docs"], r["prose"]) == ("doc", ["handoff.md"], 240), r
        assert out and "H2" in json.loads(out)["hookSpecificOutput"]["additionalContext"], out
    with tempfile.TemporaryDirectory() as d:   # 單檔 grep -n:前綴只是行號 → 整行照計(主要用法不能被歸屬邏輯吃掉)
        led = os.path.join(d, "l.jsonl")
        _run("post", _bash("grep -n R175 handoff.md", stdout="\n".join(f"{i}:" + "測" * 60 for i in range(100, 103))), led)
        assert [r["prose"] for r in _bd(led)] == [180]
    with tempfile.TemporaryDirectory() as d:   # 非 grep 指令(cat):內文行恰好以「xxx.md:」開頭也照計,不做歸屬
        led = os.path.join(d, "l.jsonl")
        _run("post", _bash("cat handoff.md", stdout="ops.md:" + "測" * 80), led)
        assert [r["prose"] for r in _bd(led)] == [80]
    with tempfile.TemporaryDirectory() as d:   # Grep 工具同理
        led = os.path.join(d, "l.jsonl")
        content = "tesrpg/a.py:3:" + "測" * 80 + "\ntesrpg/data/quests.json:9:" + "測" * 70
        _run("post", _grep(os.path.join(ROOT, "tesrpg"), content), led)
        [r] = _bd(led)
        assert (r["via"], r["prose"], r["gate"]) == ("Grep", 70, "doc"), r


def test_every_patch_flag_defeats_the_git_exemption_and_every_stat_flag_keeps_it():
    mod = _mod()
    for flag in sorted(mod.GIT_PATCH_FLAGS) + [p + "1" for p in mod.GIT_PATCH_PREFIXES]:
        for sub in ("log", "diff --stat", "show --stat"):
            assert not mod._git_exempt(f"git {sub} {flag} -- handoff.md"), (sub, flag)
    for flag in sorted(mod.GIT_STAT_FLAGS):
        for sub in ("diff", "show"):
            assert mod._git_exempt(f"git {sub} {flag} -- handoff.md"), (sub, flag)
    for sub in sorted(mod.GIT_EXEMPT_SUBS):
        assert mod._git_exempt(f"git {sub} x"), sub


def test_exempt_git_command_is_counted_when_the_output_shows_diff_headers():
    # 審查 #6:旗標清單永遠不完整(實測 log -c/-L/-U 印出數萬字卻被豁免)→ 輸出含 diff/hunk 標頭就是印了差異內文,豁免作廢
    cases = {"hunk": "@@ -1,3 +1,4 @@\n" + _prose(80),
             "git": "diff --git a/handoff.md b/handoff.md\n" + _prose(80),
             "combined": "diff --cc handoff.md\n@@@ -1,2 -1,2 +1,3 @@@\n" + _prose(80)}
    for name, body in cases.items():
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "l.jsonl")
            _run("post", _bash("git log --oneline -S foo -- handoff.md", stdout=body), led)
            [r] = _bd(led)
            assert r.get("ex") is None and r["gate"] == "doc" and r["prose"] == 80, (name, r)
    with tempfile.TemporaryDirectory() as d:   # 沒有標頭的普通 git log 輸出仍豁免
        led = os.path.join(d, "l.jsonl")
        _run("post", _bash("git log --oneline -- handoff.md", stdout=_prose(80)), led)
        assert _bd(led)[0]["ex"] is True


def test_exempt_records_never_feed_live_warnings():
    # 審查 #5:豁免記錄混進累計 → 一次 git log 就讓之後的小讀觸發 ALARM
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led)
        _run("post", _bash("git log --oneline -- handoff.md", stdout=_prose(900)), led)   # 豁免:不累計
        rc, out, _ = _run("post", _bash("python3 scan.py handoff.md", stdout=_prose(100)), led)
        assert out == "", "累計只有 100 < 150:不提醒"
        assert not [r for r in _records(led) if r["ev"] == "BDWarn"]


def test_parallel_threshold_crossing_emits_each_level_once():
    # 審查 #7:平行工具呼叫是獨立行程,load→算→append 非原子(實測 6 個平行 × 10 回合,每回合重複提醒);
    # 修法:追加後重讀,每一級只有「檔案順序最早的那筆 BDWarn」的主人輸出。這裡用「搶先追加」確定性模擬競爭。
    mod = _mod()
    base = {"sid": "s1", "pid": "p1", "at": None}
    payload = {"session_id": "s1", "prompt_id": "p1"}

    def run_case(raced_levels):
        with tempfile.TemporaryDirectory() as d, _ledger_env(os.path.join(d, "l.jsonl")):
            mod.append_record({**base, "ts": 1.0, "ev": "Prompt"})
            mod.append_record({**base, "ts": 2.0, "ev": "BigDoc", "via": "Bash", "gate": "doc", "prose": 700, "docs": ["handoff.md"]})
            real = mod.append_record

            def racing(rec):
                if rec.get("ev") == "BDWarn" and rec.get("lvl") in raced_levels:
                    real({**base, "ts": 3.0, "ev": "BDWarn", "lvl": rec["lvl"], "nonce": "other-proc"})   # 別的行程搶先追加同級 BDWarn
                real(rec)
            mod.append_record = racing
            try:
                return mod._bigdoc_feedback(payload, "PostToolUse")
            finally:
                mod.append_record = real

    out = run_case(set())
    assert out and "700" in out["systemMessage"] and "additionalContext" in out["hookSpecificOutput"], out
    out = run_case({1})
    assert out and "systemMessage" in out, "WARN 被搶先:只剩 ALARM 由我輸出"
    out = run_case({2})
    assert out and "systemMessage" not in out and "additionalContext" in out["hookSpecificOutput"], "ALARM 被搶先:只剩 WARN 由我輸出"
    assert run_case({1, 2}) is None, "兩級都被搶先:我什麼都不輸出"


def test_one_call_crossing_both_thresholds_records_both_levels_once():
    out, recs = _after([("python3 s.py handoff.md", _prose(700))])
    assert out and "systemMessage" in out, out
    assert sorted(r["lvl"] for r in recs if r["ev"] == "BDWarn") == [1, 2]
    out2, recs2 = _after([("python3 s.py handoff.md", _prose(700)), ("python3 s.py handoff.md", _prose(50))])
    assert out2 is None, "兩級都已提醒過:之後的小讀不再重發 WARN(審查:只記最高級的變異存活)"


def test_threshold_boundaries_are_inclusive():
    # PROSE_REC_MIN:prose 39 不記、40 記(長行要 >40 字,用 ASCII 補長)
    _, recs = _after([("cat handoff.md", "測" * 39 + "x" * 5)])
    assert not [r for r in recs if r["ev"] == "BigDoc"]
    _, recs = _after([("cat handoff.md", "測" * 40 + "x")])
    assert [r["prose"] for r in recs if r["ev"] == "BigDoc"] == [40]
    out, _ = _after([("python3 s.py handoff.md", _prose(149))])
    assert out is None, "149 < WARN"
    out, _ = _after([("python3 s.py handoff.md", _prose(150))])
    assert out and "systemMessage" not in out, "150 = WARN(含),不到 ALARM"
    out, _ = _after([("python3 s.py handoff.md", _prose(100)), ("python3 s.py handoff.md", _prose(499))])
    assert out and "systemMessage" not in out, "累計 599:只有 WARN"
    out, _ = _after([("python3 s.py handoff.md", _prose(100)), ("python3 s.py handoff.md", _prose(500))])
    assert out and "systemMessage" in out, "累計 600 = ALARM(含)"
    for n, want in ((149, False), (150, True)):   # Stop 納入門檻同為 150(含)
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "l.jsonl")
            _feed(led, [("prompt", _prompt()), ("post", _read_big(F_C, _prose(n)))])
            assert bool(_run("stop", _stop(msg="完成。"), led)[1]) is want, n


def test_only_doc_gated_main_conversation_output_counts_at_stop():
    # 審查 #5:盲點提示(gate=none)、git 豁免、非大文本 Read、子代理,都不得算進 Stop 的自讀量
    mod = _mod()
    me = {"sid": "s1", "pid": "p1", "at": None}
    turn = [{**me, "ev": "BigDoc", "via": "Bash", "gate": "none", "prose": 500},
            {**me, "ev": "BigDoc", "via": "Bash", "gate": "doc", "prose": 400, "ex": True, "docs": ["handoff.md"]},
            {**me, "ev": "Read", "path": os.path.join(ROOT, "tests", "x.py"), "n": 9},
            {"sid": "s1", "pid": "p1", "at": "scout", "ev": "BigDoc", "via": "Bash", "gate": "doc", "prose": 900, "docs": ["handoff.md"]},
            {**me, "ev": "BigDoc", "via": "Bash", "gate": "doc", "prose": 70, "docs": ["BESTIARY.md"]}]
    st = mod.turn_stats(turn)
    assert (st["bd_prose"], st["bd_n"], st["bd_docs"], st["bd_hint"], st["qualifies"]) == (70, 1, ["BESTIARY.md"], 500, False), st


def test_bash_and_grep_outputs_are_parsed_in_every_shape():
    # 審查 #5:stderr、純字串回應、Grep 的 glob、Grep 納入累計,拿掉任一個都沒測試紅
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("post", _bash("python3 scan.py handoff.md", stdout="", stderr=_prose(60)), led)
        assert _bd(led)[-1]["prose"] == 60, "只有 stderr 有內文"
        _run("post", _post("Bash", {"command": "cat handoff.md"}, _prose(70)), led)
        assert _bd(led)[-1]["prose"] == 70, "tool_response 是純字串"
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        p = _grep(os.path.join(ROOT, "tests"), _prose(100))
        p["tool_input"]["glob"] = "handoff.md"   # 大文本名只出現在 glob 欄
        _run("prompt", _prompt(), led)
        _run("post", p, led)
        assert (_bd(led)[-1]["via"], _bd(led)[-1]["gate"]) == ("Grep", "doc")
        rc, out, _ = _run("post", _bash("python3 s.py handoff.md", stdout=_prose(60)), led)
        assert out and "H2" in json.loads(out)["hookSpecificOutput"]["additionalContext"], "Grep 的 100 + Bash 的 60 = 160 ≥ 150:Grep 要計入累計"


def test_kill_switch_also_silences_the_stop_token_in_implementation_rounds():
    off = {"SLG_OPS_BIGDOC": "off"}
    with tempfile.TemporaryDirectory() as d:   # 實作輪 + 自讀 ≥150:off 時,提醒內不得出現自讀段落
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led, env_set=off)
        _run("post", _bash("cat handoff.md", stdout=_prose(300)), led, env_set=off)
        _run("post", _edit(F_A), led, env_set=off)
        j = json.loads(_run("stop", _stop(msg="完成。"), led, env_set=off)[1])
        assert "大文本自讀" not in j["reason"] and j["reason"].splitlines()[-1].count("|") == 3, j["reason"]
    with tempfile.TemporaryDirectory() as d:   # 已有「代理檢查」行但沒有自讀欄:off 時放行
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led, env_set=off)
        _run("post", _bash("cat handoff.md", stdout=_prose(300)), led, env_set=off)
        _run("post", _edit(F_A), led, env_set=off)
        assert _run("stop", _stop(msg="完成。\n" + LINE), led, env_set=off)[1] == ""
        assert _last_stopcheck(led)["result"] == "has_line"


def test_blind_spot_hint_shows_up_in_the_stop_reason():
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led)
        _run("post", _bash("python3 other.py", stdout=_prose(700)), led)       # 沒提到大文本名 → 盲點提示
        _run("post", _bash("cat handoff.md", stdout=_prose(200)), led)          # 計入
        j = json.loads(_run("stop", _stop(msg="完成。"), led)[1])
        assert "盲點提示:另有約 700 字" in j["reason"], j["reason"]


def test_taint_scope_edges():
    # 審查 #5:repo 內的腳本不 taint;Edit(new_string)也 taint;別的 session、子代理寫的不影響主對話
    mod = _mod()
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        scratch = os.path.join(d, "scratch")
        _feed(led, [("prompt", _prompt()),
                    ("post", _write(os.path.join(ROOT, "tools", "scan_docs_tmp.py"), "open('handoff.md')")),
                    ("post", _post("Edit", {"file_path": os.path.join(scratch, "edit_scan.py"), "old_string": "a",
                                            "new_string": "print(open('quests.json').read())"}, {})),
                    ("post", _write(os.path.join(scratch, "other_sid_scan.py"), "open('handoff.md')", sid="s2")),
                    ("post", _write(os.path.join(scratch, "sub_scan.py"), "open('handoff.md')", agent_type="scout"))])
        assert mod.tainted_paths(mod.load_records(led), "s1") == {os.path.join(scratch, "edit_scan.py")}


def test_blind_spot_outputs_never_feed_live_warnings():
    # 審查 #5:gate=none(沒提到大文本檔名)的輸出只當盲點提示,不得混進當場提醒的累計
    out, recs = _after([("python3 other.py", _prose(900)), ("python3 s.py handoff.md", _prose(100))])
    assert out is None, "累計只算 gate=doc 的 100 < 150"
    assert not [r for r in recs if r["ev"] == "BDWarn"]


def test_read_of_a_non_big_file_never_counts_as_self_read():
    # 審查 #5:只有路徑提到大文本的 Read 才算;一般檔案的長中文行(程式碼註解、說明文件)不算
    with tempfile.TemporaryDirectory() as d:
        led = os.path.join(d, "l.jsonl")
        _feed(led, [("prompt", _prompt()), ("post", _read_big(F_A, _prose(400)))])
        assert "bdp" not in [r for r in _records(led) if r["ev"] == "Read"][0]
        assert _run("stop", _stop(msg="完成。"), led)[1] == ""
        assert _last_stopcheck(led)["bd_prose"] == 0


def test_stop_token_requirement_boundary_in_implementation_rounds():
    # 實作輪(改了 CLAUDE.md;讀的 handoff 沒改 → 不是編輯前自讀):自讀 149 放行、150(含)要求自讀欄
    for n, want_block in ((149, False), (150, True)):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "l.jsonl")
            _feed(led, [("prompt", _prompt()), ("post", _read_big(F_C, _prose(n))), ("post", _edit(F_B))])
            out = _run("stop", _stop(msg="完成。\n" + LINE), led)[1]
            assert bool(out) is want_block, (n, out)
            if want_block:
                assert "缺「大文本自讀」欄" in json.loads(out)["reason"], out


def test_every_big_doc_name_and_dir_is_detected():
    mod = _mod()
    for name in mod.BIG_DOCS:
        assert mod._mentions_big(f"cat docs/{name}")[0] == name, name
    for d_ in mod.BIG_DIRS:
        assert d_ in mod._mentions_big(f"ls {d_}/world.json"), d_


def test_prose_scan_is_capped_and_memory_flat():
    mod = _mod()
    assert mod._cjk_prose("測" * (mod.PROSE_SCAN_MAX + 100)) == mod.PROSE_SCAN_MAX


def test_bd_field_must_be_in_the_check_line_or_on_its_own_line():
    # 審查 #8c:原本整則訊息任何位置提到「大文本自讀」都放行;文件說要在「代理檢查」行(或補欄提示要求的獨立行)
    mod = _mod()
    assert mod._has_bd_field("代理檢查|Opus:無|大文本自讀:0 節|counsel 0/2")
    assert mod._has_bd_field(LINE + "\n大文本自讀:1 節(H3 編輯前)")
    assert mod._has_bd_field(LINE + "\n- 大文本自讀:1 節") and mod._has_bd_field(LINE + "\n**大文本自讀**:1 節")
    assert not mod._has_bd_field(LINE + "\n另外正文提到大文本自讀這個詞,但沒有欄位。")
    assert not mod._has_bd_field("") and not mod._has_bd_field("沒有任何東西")
    with tempfile.TemporaryDirectory() as d:   # 端到端:正文提到、沒有欄位 → 仍擋(同輪一次)
        led = os.path.join(d, "l.jsonl")
        _run("prompt", _prompt(), led)
        _run("post", _bash("cat handoff.md", stdout=_prose(200)), led)
        j = json.loads(_run("stop", _stop(msg=LINE + "\n另外正文提到大文本自讀這個詞,但沒有欄位。"), led)[1])
        assert j["decision"] == "block" and "缺「大文本自讀」欄" in j["reason"], j


def test_token_line_regex_is_linear_on_blank_lines():
    mod = _mod()
    t0 = time.time()
    assert mod.TOKEN_LINE_RE.search("\n" * 200_000) is None
    assert mod.TOKEN_LINE_RE.search(" \t" * 100_000 + "\n" * 50_000) is None
    assert mod._has_bd_field("x\n" * 100_000) is False
    assert time.time() - t0 < 3.0, "行首辨識不得對連續空白行二次方回溯"
    assert mod.TOKEN_LINE_RE.search("  **大文本自讀**:0") and not mod.TOKEN_LINE_RE.search("前言大文本自讀")


def test_fail_soft_names_the_failure_event():
    # 審查 #11:失敗的 Bash 走 PostToolUseFailure,內部錯誤通知的 hookEventName 須與觸發事件一致
    mod = _mod()
    for event in ("PostToolUseFailure", "PostToolUse"):
        with tempfile.TemporaryDirectory() as d, _ledger_env(os.path.join(d, "l.jsonl")):
            out = mod.fail_soft("post", RuntimeError("boom"), {"session_id": "s9", "hook_event_name": event})
            assert out["hookSpecificOutput"]["hookEventName"] == event, (event, out)


def test_poisoned_bigdoc_fields_never_break_stats_or_hooks():
    # 審查 #12:docs 非 list、prose/bdp/lvl 是 inf → TypeError/OverflowError,連 R172 的實作輪提醒一起靜默失效
    mod = _mod()
    assert mod._int(float("inf")) == 0 and mod._float(10 ** 400) == 0.0 and mod._int(float("nan")) == 0
    assert mod._str_list(True) == [] and mod._str_list([1, "a", None, "b"]) == ["a", "b"]
    for rec in ({"ev": "BigDoc", "gate": "doc", "prose": float("inf"), "docs": True},
                {"ev": "BigDoc", "gate": "doc", "prose": 50, "docs": [1, "a", None]},
                {"ev": "Read", "path": F_C, "bdp": float("inf"), "n": float("inf")},
                {"ev": "BDWarn", "lvl": float("inf")}):
        poisoned = {**rec, "sid": "s", "at": None}
        mod.turn_stats([poisoned])
        mod.session_bigdoc_prose([poisoned], "s")
    with tempfile.TemporaryDirectory() as d:   # 端到端:帳本被毒記錄汙染後 post/stop/status 仍乾淨
        led = os.path.join(d, "l.jsonl")
        me = {"sid": "s1", "pid": "p1", "at": None}
        with open(led, "w", encoding="utf-8") as f:
            for rec in ({"ts": 1, "ev": "Prompt"},
                        {"ts": 2, "ev": "BigDoc", "via": "Bash", "gate": "doc", "prose": 500, "docs": True},
                        {"ts": 3, "ev": "BigDoc", "via": "Bash", "gate": "doc", "prose": float("inf"), "docs": [[]]},
                        {"ts": 4, "ev": "BDWarn", "lvl": float("inf")}):
                f.write(json.dumps({**me, **rec}) + "\n")
        for cmd, payload in (("post", _bash("cat handoff.md", stdout=_prose(100))), ("stop", _stop(msg="完成。")), ("status", None)):
            rc, out, err = _run(cmd, payload, led, raw=b"" if payload is None else None)
            assert rc == 0 and "Traceback" not in err, (cmd, err)
        assert not [r for r in _records(led) if r["ev"] == "Error"], "毒記錄不得走到內部錯誤路徑"


def test_ops_md_constants_match_the_hook():
    # 審查 #5(11/11 文件變異存活):把 ops.md 裡的門檻、清單、旗標、開關改掉,測試仍綠 → 文件與程式漂移時要紅燈
    mod = _mod()
    ops = open(os.path.join(ROOT, "ops.md"), encoding="utf-8").read()
    sec = ops.split("### 大文本自讀偵測(R175)", 1)[1].split("### 接線", 1)[0]
    needles = [str(mod.BIGDOC_WARN), str(mod.BIGDOC_ALARM), f"> {mod.PROSE_LINE_MIN} 字", f"≥{mod.TAINT_BASENAME_MIN} 字",
               mod.ENV_BIGDOC, mod.BD_TOKEN, "log", *mod.BIG_DOCS, *mod.BIG_DIRS, *sorted(mod.GIT_EXEMPT_SUBS),
               *sorted(mod.GIT_STAT_FLAGS), *sorted(mod.GIT_PATCH_FLAGS), *mod.GIT_PATCH_PREFIXES, *sorted(mod.ENV_OFF_VALUES)]
    missing = [n for n in needles if n not in sec]
    assert not missing, f"ops.md §13「大文本自讀偵測」缺 {missing}(hook 常數已改但文件沒跟上?)"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_ops_hook OK")
