"""倉庫結構守衛(R170):把開發流程的約定變成機器守。

每條守衛拆成「回傳違規清單的 helper」+「餵真資料的 test」+「餵假資料的反向 test」,
helper 壞掉時才不會空轉假綠(同 test_redline_base)。
"""

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_tool(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _check_sh_violations(text: str) -> list[str]:
    """check.sh 不得碰玩家存檔:不引用存檔目錄、不刪 $HOME 底下的東西、煙霧只用 mktemp 暫存目錄。"""
    errs = []
    if ".tesrpg" in text:
        errs.append("引用了玩家存檔目錄")
    if 'rm -rf "$HOME' in text or 'rm -f "$HOME' in text:
        errs.append("刪除 $HOME 底下的檔案")
    if "mktemp -d" not in text:
        errs.append("煙霧沒有使用 mktemp 暫存目錄")
    return errs


def test_check_sh_never_touches_player_saves():
    assert _check_sh_violations((ROOT / "check.sh").read_text(encoding="utf-8")) == []


def test_check_sh_guard_catches_fakes():
    for fake in ('SAVE="$HOME/.tesrpg/save.json"; mktemp -d', 'rm -rf "$HOME/saves"; mktemp -d', "echo ok"):
        assert _check_sh_violations(fake), fake


def test_run_all_discovers_real_modules():
    names = _load_tool("tests/run_all.py", "_run_all_guard").discover()
    assert "test_repo_guard" in names and len(names) >= 100, len(names)


def _assert_exits(fn, needle: str) -> None:
    try:
        fn()
    except SystemExit as e:
        assert needle in str(e), e
    else:
        raise AssertionError(f"應中止:{needle}")


def test_run_all_refuses_empty_or_nested_discovery():
    mod = _load_tool("tests/run_all.py", "_run_all_guard")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        mod.TESTS_DIR = root
        _assert_exits(mod.discover, "0 個")
        (root / "test_a.py").write_text("")
        assert mod.discover() == ["test_a"]
        (root / "sub").mkdir()
        (root / "sub" / "test_b.py").write_text("")
        _assert_exits(mod.discover, "子目錄")


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_repo_guard 全通過")
