#!/usr/bin/env bash
# 一鍵驗證鏈 — 流亡者 (tesrpg)。對應 CLAUDE.md「提交前檢查表」/「開發節奏」。
# 用法:
#   bash check.sh            # 編譯 → 全測試;若 git diff 動到戰鬥常數則自動跑平衡模擬
#   bash check.sh --sim      # 強制跑 sim_assassin.py(平衡回歸)
#   bash check.sh --smoke    # 額外跑無頭煙霧(save/load 往返,唯一會寫存檔)→ 結束自動清存檔
#   bash check.sh --sim --smoke
# 非零退出 = 有步驟未過。無 pip/pytest/jq 環境;只靠 python3 + git。
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"          # 切到 repo 根,任何 cwd 都能跑

RUN_SIM=0
RUN_SMOKE=0
for arg in "$@"; do
  case "$arg" in
    --sim)   RUN_SIM=1 ;;
    --smoke) RUN_SMOKE=1 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知參數:$arg(用 -h 看用法)" >&2; exit 2 ;;
  esac
done

SAVE="$HOME/.tesrpg/save.json"
cleanup() { if [ "$RUN_SMOKE" = 1 ]; then rm -f "$SAVE" && echo "🧹 已清存檔 $SAVE"; fi; }
trap cleanup EXIT

step() { echo; echo "▶ $*"; }
fail() { echo "✗ $*"; exit 1; }

# 1) 編譯檢查(完整 glob:含頂層模組 tesrpg/*.py 與 tests/*.py,缺了會漏掉 main/state/formulas)
step "py_compile(完整)"
shopt -s globstar
python3 -m py_compile tesrpg/**/*.py tesrpg/*.py tests/*.py || fail "編譯失敗"
echo "✓ 編譯通過"

# 2) 全測試(硬閘門;模組數由 run_all.py 結尾自報)
step "tests/run_all.py"
PYTHONPATH=. python3 tests/run_all.py || fail "測試未全綠"

# 3) 平衡模擬:--sim,或 git diff(含未暫存)動到 formulas.py / combat.py 就自動跑
if [ "$RUN_SIM" = 0 ] && git diff --name-only HEAD 2>/dev/null \
     | grep -qE 'tesrpg/formulas\.py|tesrpg/systems/combat\.py'; then
  RUN_SIM=1
  echo "ℹ 偵測到 formulas.py / combat.py 變更 → 自動跑平衡模擬"
fi
if [ "$RUN_SIM" = 1 ]; then
  step "sim_assassin.py(平衡回歸 — 守刺客紅線)"
  SIM_OUT="$(PYTHONPATH=. python3 sim_assassin.py)" || fail "sim 執行失敗"
  echo "$SIM_OUT"
  if echo "$SIM_OUT" | grep -q '⚠'; then
    echo; echo "🔴 sim 出現 ⚠ 旗標,務必人眼覆核紅線(sim 為 print-only、不自動擋):"
    echo "$SIM_OUT" | grep '⚠'
  else
    echo "✓ sim 無 ⚠ 旗標"
  fi
fi

# 4) 無頭煙霧(可選;build_character → GameState → save/load 往返,唯一寫存檔的步驟)
if [ "$RUN_SMOKE" = 1 ]; then
  step "無頭煙霧(save/load 往返)"
  PYTHONPATH=. python3 - "$SAVE" <<'PY' || fail "煙霧失敗"
import os, sys
from pathlib import Path
from tesrpg.gamedata import get_gamedata
from tesrpg.creation import build_character
from tesrpg.state import GameState
from tesrpg.rng import RNG

save = Path(sys.argv[1])
save.parent.mkdir(parents=True, exist_ok=True)
gd = get_gamedata()
c = build_character(gd, name="SmokeHero", sex="male", race="imperial",
                    birthsign="warrior", class_id="thief")
state = GameState(player=c, rng=RNG(seed=1), game_mode="adventure")
state.save(save)
back = GameState.load(save)
assert back.player.name == "SmokeHero", "存檔往返:角色名不符"
assert back.player.race == "imperial", "存檔往返:種族不符"
print("✓ 煙霧通過(建角 → 存檔 → 讀檔往返一致)")
PY
fi

echo; echo "✅ check 全通過"
