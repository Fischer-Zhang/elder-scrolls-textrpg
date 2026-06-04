"""不需要 pytest 的測試執行器:python3 tests/run_all.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import test_combat
import test_creation
import test_equipment
import test_guild_depth
import test_m5
import test_m6
import test_m7
import test_m8
import test_m9
import test_m10
import test_m12
import test_m13
import test_m14
import test_m15
import test_magic
import test_progression
import test_seed
import test_state
import test_weapons
import test_world

if __name__ == "__main__":
    modules = [test_creation, test_progression, test_state, test_combat, test_world, test_seed,
               test_magic, test_m5, test_m6, test_m7, test_m8, test_m9, test_m10, test_m12, test_m13,
               test_m14, test_m15, test_guild_depth, test_equipment, test_weapons]
    for m in modules:
        m.run()
        print(f"✓ {m.__name__}")
    print(f"\n全部通過 ({len(modules)} 個測試模組)")
