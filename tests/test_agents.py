"""子代理分工守門(R171):scout / counsel 的 frontmatter 結構、唯讀屬性、模型 class、omitClaudeMd,
以及 ops.md 與 CLAUDE.md「協作分工」段落存在。純檔案檢查,不呼叫模型。

為什麼守:scout / counsel 沒有 Bash、Write、Edit,「唯讀」完全靠工具白名單保證(本里程碑不做 hook 守衛);
omitClaudeMd 是 scout 便宜的關鍵(不載入 CLAUDE.md 量測差約 10 倍 token)。這兩點被改掉不會有任何報錯,所以用測試鎖住。"""

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENTS_DIR = os.path.join(ROOT, ".claude", "agents")
ROLES = ("scout", "counsel")
BUILTIN_AGENT_NAMES = {"Explore", "Plan", "general-purpose", "claude", "statusline-setup", "claude-code-guide"}
ALLOWED_MODELS = {"claude-haiku-5-5", "claude-opus-5-5", "haiku", "opus", "sonnet", "fable", "inherit"}
READ_ONLY_TOOLS = {"Read", "Grep", "Glob"}


def _split_list(value):
    return {x.strip() for x in value.split(",") if x.strip()}


def _frontmatter(name):
    path = os.path.join(AGENTS_DIR, name + ".md")
    assert os.path.exists(path), f"缺少子代理檔 {path}"
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{name}.md 缺 frontmatter(須以 --- 開頭並以 --- 結束)"
    fields = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        key, sep, val = line.partition(":")
        assert sep, f"{name}.md frontmatter 行格式錯誤:{line!r}"
        fields[key.strip()] = val.strip()
    return fields


def test_agent_frontmatter_required_fields():
    for name in ROLES:
        fm = _frontmatter(name)
        assert fm.get("name") == name, f"{name}.md 的 name 欄須與檔名一致,實際 {fm.get('name')!r}"
        assert name not in BUILTIN_AGENT_NAMES, f"{name} 與內建子代理同名"
        assert fm.get("description"), f"{name} 缺 description"
        assert fm.get("model") in ALLOWED_MODELS, f"{name} model={fm.get('model')!r} 不在允許集合"
        turns = int(fm.get("maxTurns", "0"))
        assert 1 <= turns <= 20, f"{name} maxTurns={turns} 須在 1..20"


def test_omit_claude_md_stays_on():
    # 不載入 CLAUDE.md 是 scout 便宜的關鍵;counsel 也靠簡報自包含,不吃 CLAUDE.md
    for name in ROLES:
        assert _frontmatter(name).get("omitClaudeMd") == "true", f"{name} 須維持 omitClaudeMd: true"


def test_scout_and_counsel_are_read_only():
    for name in ROLES:
        fm = _frontmatter(name)
        tools = _split_list(fm.get("tools", ""))
        assert tools and tools <= READ_ONLY_TOOLS, f"{name} tools={sorted(tools)} 超出唯讀集合 {sorted(READ_ONLY_TOOLS)}"
        denied = _split_list(fm.get("disallowedTools", ""))
        for forbidden in ("Bash", "Write", "Edit", "Agent"):
            assert forbidden in denied, f"{name} 的 disallowedTools 缺 {forbidden}(雙保險)"


def test_model_class_matches_role():
    assert "haiku" in _frontmatter("scout")["model"], "scout 應為 Haiku 級"
    assert "opus" in _frontmatter("counsel")["model"], "counsel 應為 Opus 級"


def test_ops_guide_and_claude_section_present():
    ops_path = os.path.join(ROOT, "ops.md")
    assert os.path.exists(ops_path), "缺作業指南 ops.md"
    ops = open(ops_path, encoding="utf-8").read()
    for needle in ("共享工作樹", "每里程碑", "簡報模板", "升級 Opus", "scout", "counsel"):
        assert needle in ops, f"ops.md 缺關鍵段落或詞:{needle}"
    claude = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    assert "## 協作分工" in claude, "CLAUDE.md 缺『協作分工』段"
    assert "ops.md" in claude, "CLAUDE.md 須指向 ops.md"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_agents OK")
