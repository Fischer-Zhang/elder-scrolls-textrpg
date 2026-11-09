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


def _run(cmd, payload, ledger, raw=None, env_remove=(), hook=HOOK):
    env = dict(os.environ)
    env["SLG_OPS_LEDGER"] = ledger
    for k in env_remove:
        env.pop(k, None)
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
        _feed(led, [("post", _post("Bash", {"command": "ls"}, {"stdout": "x"}))])
        assert _records(led) == [], "Bash 不入帳(使用者拍板:第一批只算 Read)"
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
                   "skip_no_msg", "SendMessage"):
        assert needle in ops, f"ops.md 缺 hook 文件關鍵詞:{needle}"
    blocks = re.findall(r"```json\n(.*?)\n```", ops, re.S)
    wiring = [json.loads(b) for b in blocks if '"hooks"' in b]
    assert wiring, "ops.md 須附可複製的 hooks 接線 JSON(也是試跑時放進 settings.local.json 的內容)"
    hooks = wiring[0]["hooks"]
    assert set(hooks) == {"PostToolUse", "UserPromptSubmit", "Stop"}, sorted(hooks)
    post = hooks["PostToolUse"][0]
    assert set(post["matcher"].split("|")) == {"Read", "Edit", "Write", "Agent"}, post["matcher"]
    for event, sub in (("PostToolUse", "post"), ("UserPromptSubmit", "prompt"), ("Stop", "stop")):
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



def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_ops_hook OK")
