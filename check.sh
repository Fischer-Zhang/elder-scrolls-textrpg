#!/usr/bin/env bash
# 一鍵驗證鏈 — 流亡者 (tesrpg)。對應 CLAUDE.md「自動提交閘門」。
# 用法:
#   bash check.sh            # 編譯 → 全測試;若 git diff 動到戰鬥常數則自動跑平衡模擬
#   bash check.sh --sim      # 強制跑 sim_assassin.py + sim_reckless.py + sim_monk.py + sim_dungeon.py + sim_flee.py + sim_conj.py + sim_economy.py(平衡回歸)
#   bash check.sh --smoke    # 額外跑無頭煙霧(save/load 往返,只寫暫存目錄,不碰玩家存檔)
#   bash check.sh --sim --smoke
# 非零退出 = 有步驟未過。需要 python3 + git;真瀏覽器回歸另需 Playwright dev 依賴。
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

SMOKE_DIR=""
cleanup() { if [ -n "$SMOKE_DIR" ]; then rm -rf "$SMOKE_DIR"; fi; }
trap cleanup EXIT

step() { echo; echo "▶ $*"; }
fail() { echo "✗ $*"; exit 1; }

# 1) 編譯檢查(完整 glob:含頂層模組 tesrpg/*.py 與 tests/*.py,缺了會漏掉 main/state/formulas)
step "py_compile(完整)"
shopt -s globstar
python3 -m py_compile tesrpg/**/*.py tesrpg/*.py tests/*.py .claude/hooks/*.py || fail "編譯失敗"
echo "✓ 編譯通過"

# 2) 全測試(硬閘門;模組數由 run_all.py 結尾自報)
step "tests/run_all.py"
PYTHONPATH=. python3 tests/run_all.py || fail "測試未全綠"

# 2b) 真瀏覽器回歸:正式 index.html + HTTP/SSE + Chromium,驗桌面版面與互動。
# Playwright/Chromium 是 dev 依賴;缺少時硬失敗並由 tests/browser_ui.py 印安裝指令,不可靜默 skip。
step "Playwright 桌面瀏覽器回歸"
PYTHONPATH=. python3 tests/browser_ui.py || fail "真瀏覽器回歸失敗"

# 變更檔清單(已追蹤的改動 + 未追蹤的新檔),先收進變數再比對。
# 🔴 不要寫成「{ git diff; git ls-files; } | grep -q」:grep -q 一命中就關管線,後面那個 git 指令寫入時收到 SIGPIPE(141),
#    在 pipefail 下整條管線算失敗 → 明明動到相關檔卻靜默不跑 sim(只要有未追蹤新檔就必現;R222 發現並修)。
CHANGED="$( { git diff --name-only HEAD; git ls-files --others --exclude-standard; } 2>/dev/null || true )"
changed_matches() { grep -qE "$1" <<<"$CHANGED"; }

# 3) 平衡模擬:--sim,或 git diff(含未暫存)動到 formulas.py / combat.py 就自動跑
if [ "$RUN_SIM" = 0 ] && changed_matches 'tesrpg/formulas\.py|tesrpg/systems/combat\.py'; then
  RUN_SIM=1
  echo "ℹ 偵測到 formulas.py / combat.py 變更 → 自動跑平衡模擬"
fi
if [ "$RUN_SIM" = 1 ]; then
  step "sim_assassin.py(平衡回歸 — 守刺客紅線)"
  SIM_OUT="$(PYTHONPATH=. python3 sim_assassin.py)" || fail "sim 執行失敗"
  echo "$SIM_OUT"
  if grep -q '⚠' <<<"$SIM_OUT"; then
    echo; echo "🔴 sim 出現 ⚠ 旗標,務必人眼覆核紅線(sim 為 print-only、不自動擋):"
    echo "$SIM_OUT" | grep '⚠'
  else
    echo "✓ sim 無 ⚠ 旗標"
  fi
  step "sim_reckless.py(R191 搏命連斬群戰/終王牆守衛;約 3 分鐘)"
  RK_OUT="$(PYTHONPATH=. python3 sim_reckless.py)" || fail "sim_reckless 執行失敗"
  echo "$RK_OUT"
  if grep -q '⚠ 守衛警示' <<<"$RK_OUT"; then
    echo; echo "🔴 搏命連斬守衛出現 ⚠(輸給皆不選/強度過頭/破牆線/相當性),務必人眼覆核(print-only、不自動擋):"
    echo "$RK_OUT" | grep '⚠'
  else
    echo "✓ 搏命連斬守衛全過"
  fi
  step "sim_monk.py(R193 徒手 100 崩勁釋放/鐵布衫群戰與終王牆守衛;約 1 分鐘)"
  MK_OUT="$(PYTHONPATH=. python3 sim_monk.py)" || fail "sim_monk 執行失敗"
  echo "$MK_OUT"
  if grep -q '⚠ 守衛警示' <<<"$MK_OUT"; then
    echo; echo "🔴 徒手守衛出現 ⚠(輸給皆不選/強度過頭/破牆線),務必人眼覆核(print-only、不自動擋):"
    echo "$MK_OUT" | grep '⚠'
  else
    echo "✓ 徒手守衛全過"
  fi
  step "sim_dungeon.py(R194 運動 100 一氣呵成/殺勢回體:整趟地城全清+boss 與終王牆守衛;約 30 秒)"
  DG_OUT="$(PYTHONPATH=. python3 sim_dungeon.py)" || fail "sim_dungeon 執行失敗"
  echo "$DG_OUT"
  if grep -q '⚠ 守衛警示' <<<"$DG_OUT"; then
    echo; echo "🔴 運動 100 守衛出現 ⚠(強度過頭/輸給同線無100階/破牆線/低難度回歸),務必人眼覆核(print-only、不自動擋):"
    echo "$DG_OUT" | grep '⚠'
  else
    echo "✓ 運動 100 守衛全過"
  fi
  step "sim_flee.py(R195 運動 50 健步如飛脫身加成:整趟地城最後一搏逃跑政策,量 死亡/逃走/通關 與節氣對照;約 1 分鐘)"
  FL_OUT="$(PYTHONPATH=. python3 sim_flee.py)" || fail "sim_flee 執行失敗"
  echo "$FL_OUT"
  if grep -q '⚠ 守衛警示' <<<"$FL_OUT"; then
    echo; echo "🔴 脫身守衛出現 ⚠(強度過頭/夾限失效/沒效果/反向 no-brainer),務必人眼覆核(print-only、不自動擋):"
    echo "$FL_OUT" | grep '⚠'
  else
    echo "✓ 脫身守衛全過"
  fi
fi

# 3a) 召喚守衛(R203):--sim,或 git diff 動到召喚相關檔就自動跑(sim_party 原不在 check.sh → 守衛只能手動跑、政策還曾遮住規則缺口)
RUN_CONJ_SIM=$RUN_SIM
if [ "$RUN_CONJ_SIM" = 0 ] && changed_matches 'tesrpg/formulas\.py|tesrpg/systems/(combat|magic|necromancy|mastery|powers)\.py|tesrpg/data/(mastery|spells)\.json|sim_conj\.py|sim_party\.py'; then
  RUN_CONJ_SIM=1
  echo "ℹ 偵測到召喚相關檔變更 → 自動跑召喚守衛 sim_conj.py"
fi
if [ "$RUN_CONJ_SIM" = 1 ]; then
  step "sim_conj.py(R203 召喚守衛:非亡者同場名額規則探針 + 終王牆〔召喚師 / 死靈師打達貢,含爪牙·預召喚〕+ conjuration 選項 vs 不選;約 1–2 分鐘)"
  CJ_OUT="$(PYTHONPATH=. python3 sim_conj.py)" || fail "sim_conj 執行失敗"
  echo "$CJ_OUT"
  if grep -q '⚠ 守衛警示' <<<"$CJ_OUT"; then
    echo; echo "🔴 召喚守衛出現 ⚠(牆破了/名額規則失效/選項輸給不選/強度過頭),務必人眼覆核(print-only、不自動擋):"
    echo "$CJ_OUT" | grep '⚠ 守衛警示'
  else
    echo "✓ 召喚守衛全過"
  fi
fi

# 3b) AI 戰爭收斂模擬:--sim,或 git diff 動到 aiwar.py / worldstate.py / politics.py 就自動跑
RUN_WAR_SIM=$RUN_SIM
if [ "$RUN_WAR_SIM" = 0 ] && changed_matches 'tesrpg/systems/(aiwar|worldstate|politics)\.py'; then
  RUN_WAR_SIM=1
  echo "ℹ 偵測到 aiwar/worldstate/politics 變更 → 自動跑 AI 戰爭收斂模擬"
fi
if [ "$RUN_WAR_SIM" = 1 ]; then
  step "sim_worldwar.py(AI 戰爭收斂 — 防雪球/反攻 feels-bad/選邊有感)"
  WAR_OUT="$(PYTHONPATH=. python3 sim_worldwar.py)" || fail "sim_worldwar 執行失敗"
  echo "$WAR_OUT"
  if grep -q '⚠' <<<"$WAR_OUT"; then
    echo; echo "🔴 AI 戰爭 sim 出現 ⚠ 旗標,務必人眼覆核平衡(print-only、不自動擋):"
    echo "$WAR_OUT" | grep '⚠'
  else
    echo "✓ AI 戰爭 sim 無 ⚠ 旗標"
  fi
fi

# 3c) 經濟量測(R222):--sim,或 git diff 動到價格 / 折扣 / 銷贓 / 配方 / 物品底價相關檔就自動跑(不到 1 秒)
RUN_ECON_SIM=$RUN_SIM
if [ "$RUN_ECON_SIM" = 0 ] && changed_matches 'tesrpg/systems/(world|crime|factions|renown|divines|housing|party|spellfx|mastery|progression|loot|dungeoncrawl)\.py|tesrpg/data/(weapons|armor|items|ingredients|recipes|factions|mastery|dungeons|bestiary|quests|houses|house_upgrades|mounts|spells|skills|trainers|world|companions)\.json|sim_economy\.py'; then
  RUN_ECON_SIM=1
  echo "ℹ 偵測到經濟相關檔變更 → 自動跑經濟量測 sim_economy.py"
fi
if [ "$RUN_ECON_SIM" = 1 ]; then
  step "sim_economy.py(R222 經濟量測:議價倍率 / 套利掃描 / 收入 / 去處 / 配方轉賣)"
  EC_OUT="$(PYTHONPATH=. python3 sim_economy.py)" || fail "sim_economy 執行失敗"
  echo "$EC_OUT"
  if grep -q '⚠ 守衛警示' <<<"$EC_OUT"; then
    echo; echo "🔴 經濟守衛出現 ⚠(同店 / 黑市 / 跨攤位倒掛或配方轉賣),務必人眼覆核(print-only、不自動擋):"
    echo "$EC_OUT" | grep '⚠'
  else
    echo "✓ 經濟守衛全過"
  fi
fi

# 4) 無頭煙霧(可選;build_character → GameState → save/load 往返,只寫暫存目錄,不碰玩家存檔)
if [ "$RUN_SMOKE" = 1 ]; then
  step "無頭煙霧(save/load 往返,暫存目錄)"
  SMOKE_DIR="$(mktemp -d)" || fail "無法建立暫存目錄"
  PYTHONPATH=. python3 - "$SMOKE_DIR/save.json" <<'PY' || fail "煙霧失敗"
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
