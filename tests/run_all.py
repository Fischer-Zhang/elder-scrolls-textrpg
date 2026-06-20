"""不需要 pytest 的測試執行器:python3 tests/run_all.py

自動探索 tests/test_*.py:每個模組需有可呼叫的 run()(慣例:run() 用
`sorted(globals())` 自動跑該模組所有 test_* 函式)。新增測試模組或測試函式
**無需登錄** —— 根除原「頂部 import 清單 + __main__ modules 清單」雙清單漏同步、
以及「寫了 test_ 卻忘了加進 run()」這兩類靜默漏跑 footgun。
"""

import importlib
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent))   # 專案根:import tesrpg
sys.path.insert(0, str(TESTS_DIR))           # 讓 test_* 模組可被 import_module / 互相 import


def discover() -> list[str]:
    """tests/ 下所有 test_*.py 的模組名(決定性 sorted;m12<m13 等 import-time patch 相對序不變)。"""
    return sorted(p.stem for p in TESTS_DIR.glob("test_*.py") if p.stem != "run_all")


def main() -> None:
    names = discover()
    passed = 0
    for name in names:
        mod = importlib.import_module(name)
        run = getattr(mod, "run", None)
        if not callable(run):
            raise SystemExit(f"✗ {name}:缺少可呼叫的 run()(每個 test_*.py 都須提供)")
        run()
        print(f"✓ {name}")
        passed += 1
    print(f"\n全部通過 ({passed} 個測試模組)")


if __name__ == "__main__":
    main()
