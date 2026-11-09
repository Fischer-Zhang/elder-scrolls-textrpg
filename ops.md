# 作業指南:四原則與子代理分工(ops)

> 憲法(紅線、五階段流程)在 `CLAUDE.md`。本檔把四條原則落成可執行的規則:誰做什麼、何時派 Haiku、何時升級 Opus、怎麼省 Opus 的上下文。
> 落地紀錄見 handoff.md R171、R172。改這裡的規則時,同步 CLAUDE.md「協作分工」段與 R171。

## 0. 四原則

1. Opus 5.5 作為顧問,處理重要決策。
2. Haiku 5.5 探索檔案和文件(需讀大量文本的階段)。
3. Sonnet 5.5 引導工作階段並撰寫程式碼。
4. 在不需要 Opus 的任務中節省其上下文。

## 1. 角色分工

| 角色 | 模型 | 做 | 不做 |
|---|---|---|---|
| 主對話 | Sonnet 5.5(使用者層預設) | 引導流程、寫碼、跑測試、審查、提交、彙整各代理的結果 | 設計方向與平衡取捨(一律問使用者) |
| scout | Haiku 5.5(`.claude/agents/scout.md`) | 大量閱讀、檢索、計數、長文摘要;每個要點附 路徑:行號 | 判斷、審查、解讀架構 |
| counsel | Opus 5.5(`.claude/agents/counsel.md`) | 看簡報後給反例、風險、建議、信心 | 拍板、改檔、呼叫其他代理 |
| 使用者 | — | 設計方向、平衡取捨、里程碑拍板 | — |

內建 Explore 不覆寫。它跑主對話模型(Sonnet),讀多少都算 Sonnet 的 token。大量閱讀改派 scout;Explore 只留給「需要理解架構或找根因、而且讀量小」的探索。

## 2. 五階段流程對應

| 階段 | 誰做 |
|---|---|
| 1 評估 | 大量閱讀派 scout(可並行);Sonnet 收結論、做推理 |
| 2 決定方向 | 符合 §4 的 O1–O5 才找 counsel;設計方向與平衡取捨由使用者拍板 |
| 3 實作 | Sonnet |
| 4 驗證 | Sonnet 跑 check.sh;4e 審查見 §9;出現 O3 才找 counsel |
| 5 文件與提交 | Sonnet |

## 3. 何時派 scout(原則 2)

**讀量門檻(H1):** 這一步要讀、但讀完不會改的內容,預估超過約 1,000 行或 5 個檔,就派 scout。1,000 行約等於一個大模組(combat.py 約 1,400 行、magic.py 約 1,160 行)。

**本專案的大文本(H2):** 除非只讀已知的一小段,一律派 scout。(2026-11 量測,數字會漂移,只作量級參考。)
- handoff.md:約 3,000 行,單行很長;讀兩節以上就派。
- 資料大檔:bestiary.json 約 11,400 行、quests.json 約 9,500、events.json 約 2,650、npcs.json 約 1,970、mastery.json 約 1,800。
- BESTIARY.md 約 1,400 行;tests/ 共 134 個模組、約 3 萬行。

**主對話自己讀(H3):**
- 要編輯的檔。必須親讀才改得對,例如 main.py(約 6,500 行)裡的某個函式。
- 已知路徑的一小段。
- 一次 Grep 就能答的問題。

scout 沒有 Bash,讀不了 git 歷史。`git log` 之類由主對話自己跑,輸出小。

**使用規範:**
- 並行上限 3 個。按**問題**切片,不按目錄切。一題一人,每題要能獨立回答。
- 簡報自包含:問題一句、搜尋範圍(路徑或 glob)、答案格式。scout 不會讀 CLAUDE.md,也不會讀本檔。
- 摘要題要明說要幾點;每點附 路徑:行號 與逐字短引文。
- 數量題:scout 回數字與 pattern 後,主對話用 Grep 的計數模式重算一次,才採用。
- `NOT FOUND` 是有效答案,不要逼它猜。
- scout 的結論只當線索。判斷與採納在主對話做。

## 4. 何時升級 Opus(原則 1)

符合下列任一條,才派 counsel:

- **O1 紅線區的設計取捨:** 改動落在下列區域,而且有兩個以上可行設計要選。已拍板數值的落地、補測試、純重構都不算。
  - re-sim 區:`tesrpg/formulas.py`、`tesrpg/systems/combat.py`(check.sh 會自動跑 sim 的兩檔),加上 `tesrpg/systems/magic.py`、`tesrpg/systems/enchanting.py`。
  - 存檔區:`tesrpg/models/character.py`、`tesrpg/state.py`、`tesrpg/systems/save_migrations.py`、`tesrpg/systems/saves.py`。
- **O2 全專案共用的收斂點:** `magic.apply_control`、`resolve_attack`、`stats.recompute_max_resources`、`ensure_*` 遷移;或一個設計同時跨三個以上 systems 模組。
- **O3 驗證違反預期,自查一輪後仍解釋不了:** 預期 byte-identical 的 sim 出現位移、同一測試修兩次仍紅、真瀏覽器回歸定位不了。
- **O4 推翻既有 R## 鐵律,或審查結論的真偽有爭議:** R39 就出現過審查誤報,審查結論要先驗證再採納。
- **O5 全域機制:** 新增或修改會留下來的 hook、permissions、settings(影響所有後續 session,失效又不易察覺)。當場還原的診斷不算。

**不找 Opus:** 純 JSON 內容(R02)、文件同步、根因明確的單檔 bug、機械重構、寫測試、跑驗證、提交。平衡數值與設計方向直接問使用者,不讓 counsel 代答。

**上限:** 每里程碑 counsel 最多 2 次。里程碑以提交訊息開頭的 R## 界定:同一個 R## 的多次提交(`R171`、`R171 續`、`R171 續2`)算同一個里程碑;字尾字母算不同里程碑(`R114C` ≠ `R114`);沒有 R## 前綴的提交略過。第 3 次要先在對話裡寫一句理由,經使用者同意才呼叫。

## 5. counsel 簡報模板

簡報不超過約 150 行,證據用摘錄,不貼整檔。簡報需要的大量事實,先由 scout 整理好。依序填入:

1. **決策問題**:一句,用問句。
2. **事實與證據**:只寫可驗證的事實,每條附 路徑:行號。
3. **候選方案**:A、B(可加 C),每個寫出代價。**不寫主對話的傾向。**
4. **已排除的方案與理由**。
5. **相關 R## 原文**:最多 3 條,從 CLAUDE.md 或 handoff §3 原樣複製,不改寫。
6. **希望顧問回答的問題**:最多 3 條。

不寫「我的初步結論」,避免顧問被錨定。counsel 的輸出格式已寫在它的 agent 檔裡(最強反例、風險、建議、信心、會改變結論的證據、需拍板的點)。

## 6. 省 Opus 的上下文(原則 4)

- counsel 只吃簡報(§5),不讓 Opus 自己讀大量文本。
- 不開 `/advisor`:伺服器端顧問每次讀整段主對話(實測:輸入就是整段 transcript),成本隨對話增長;Opus 5.5 的建議對 client 加密,無法稽核。
- 主對話只在需要和使用者多輪討論設計時才切到 Opus,最好在新 session 或 `/compact` 之後;定案就切回 Sonnet。切換當下,Opus 要以自己的價格把整段對話重新寫入快取,之後每輪也重讀整段對話。
- 不需要 Opus 的任務(§4「不找 Opus」清單)一律留在 Sonnet。
- 實測一次實質審查(hook 設計,簡報 63 行):Opus 6 輪、輸入(含快取)約 9.3 萬、輸出約 8.8 千 token。counsel 會用 Read 驗證簡報,並逐輪重讀上下文,所以簡報小不等於總量小。要壓低:簡報附足證據、註明哪些事實已驗證不必再讀,並可調低 counsel.md 的 `effort` 或 `maxTurns`。

## 7. 每輪代理檢查

有實作的輪次(改過檔、讀過 5 個以上的檔,或派過代理),回覆結尾寫一行:

`代理檢查|Opus:無(O1–O5 皆否)|Haiku:讀而未改 3 檔約 600 行 → 自己讀|counsel 0/2`

- 問答輪不檢查。
- Opus 欄:列出符合的 O 條件,或「無」。
- Haiku 欄:本輪讀而未改的檔數與行數、派了幾次 scout;超過 H1 門檻卻自己讀的,寫出理由。
- counsel 欄:本里程碑已派次數 / 上限 2。
- 數字由 hook 實測(R172,見 §13):實作輪缺這一行時,Stop hook 回報改檔數、讀而未改的檔數與行數、本輪派代理次數、counsel 次數,主對話同輪補上(每輪最多一次)。O1–O5 的判斷仍由主對話寫。
- counsel 欄 hook 給兩個數字:以 R## 界定的本里程碑累計,以及自最近提交後的累計。新里程碑尚未提交時以後者為準;延續舊里程碑時以前者為準。

## 8. 子代理與 git 紅線

- 子代理不得在共享工作樹執行會改 git 狀態的指令:`git stash`、`checkout`、`restore`、`reset --hard`、`clean`。R45 就是審查代理在共享工作樹 stash,險些把資料檔回退後提交。
- 需要隔離時(byte-identical 比對、會寫檔的驗證),用 worktree:`EnterWorktree` 或 `isolation: worktree`。
- scout 與 counsel 唯讀、沒有 Bash,本條對它們天然成立。本條主要約束其他子代理。

## 9. 對抗審查(CLAUDE.md 開發流程 4e)

- **預設**:主對話啟動一個 general-purpose 審查子代理,模型指定 `sonnet`,在 worktree 內依 4e 流程驗證。審查不降成 Haiku。
- **多維 fan-out**(Workflow)只在使用者明說「用 workflow / fan out」或開啟 ultracode 時才跑。Workflow 工具的規定是須使用者明確同意。
- **Workflow 內 agent 指定模型**:偵察用 Haiku,審查與驗證用 Sonnet。語法以 workflow-authoring skill 為準,實作前先查,不照記憶寫。

## 10. 量測與回報

- 每里程碑在 handoff §4 記一行:本輪 scout 次數、counsel 次數、審查模式(單一或 fan-out)。
- 子代理成本以 token 計(各模型的 input、output、cache),不以美元。美元數字是牌價換算,不是帳單。
- 背景啟動(`status: async_launched`)的子代理,PostToolUse 只回 `resolvedModel`,不回 token 數。要量 token,看 `claude -p --output-format json` 的 `modelUsage`。
- 帳本(R172,§13):`.claude/ledger/ops.jsonl` 記 Read/Edit/Write/Agent 呼叫(含子代理內的,以 `agent_type` 區分)。看摘要:`python3 .claude/hooks/ops_ledger.py status`。同上條,`claude -p` / `--agent` 獨立 process 不在內。
- Agent map 只列本 session 以 Agent 工具派出的子代理。`claude -p` 與 `claude --agent` 是獨立 process,不會出現在 map 裡;它們的用量以輸出 JSON 的 `modelUsage` 為準,並記入 handoff §4 的使用紀錄。

## 11. 變更本指南

- 換模型:改 `.claude/agents/*.md` 的 `model` 行,跑 `tests/test_agents.py` 與 §12 的現場驗證。
- 改分工、O1–O5 或 H1–H3:同步 CLAUDE.md「協作分工」段與 handoff R171。
- 改 `.claude/hooks/ops_ledger.py`:跑 `python3 tests/test_ops_hook.py`(含 §13 接線 JSON 的驗證)。改接線(settings*.json 的 hooks 區塊)屬 O5。

## 12. 現場驗證(改 agent 檔後)

在專案目錄執行 `claude -p`,請主對話委派對應子代理,再檢查輸出 JSON 的 `modelUsage`:

- scout:應出現 `claude-haiku-5-5`,且 input(含 cache)遠小於主對話載入 CLAUDE.md 的量,證明 `omitClaudeMd` 生效。
- counsel:應出現 `claude-opus-5-5`。

這會花少量額度。先取得使用者同意,並設 `--max-budget-usd` 上限。

- 指令尾端加 `< /dev/null`,避免 CLI 等 3 秒 stdin。
- 在本 repo 用 `-p` 時,CLI 會因工作區未受信任而忽略 `.claude/settings.json` 的 `permissions.allow`。這不影響子代理載入。
- 互動 session 中途新增或修改的 agent 檔不會被載入。實測:同一 session 內呼叫新建的 counsel,回 `Agent type 'counsel' not found`。要重開 session 才會載入;`claude -p` 與 `claude --agent <名稱>` 每次都是新 process,馬上可用。
- 在 session 重開前要找 counsel:`claude --agent counsel -p "<簡報>" --max-budget-usd N --output-format json --no-session-persistence < /dev/null`。主執行緒直接以 counsel 的模型、工具與本文執行,不經 Sonnet 轉述;但這是獨立 process,不在 Agent map(見 §10)。

## 13. hook 帳本與「代理檢查」補數字(R172)

PostToolUse 記帳,Stop 補「代理檢查」的實測數字。腳本 `.claude/hooks/ops_ledger.py`(只用 stdlib),測試 `tests/test_ops_hook.py`。

### 運作

| 事件 | 子命令 | 做什麼 |
|---|---|---|
| PostToolUse(`Read\|Edit\|Write\|Agent`) | `post` | 記一筆:路徑、Read 的 `numLines`、Agent 的 `subagent_type`、`model` 覆寫、解析後模型與派工標籤(`description` 前 60 字);不存檔案內容與 prompt |
| UserPromptSubmit | `prompt` | 記「新一輪開始」標記 |
| Stop | `stop` | 實作輪缺「代理檢查」行 → 回 `decision: block` 加實測數字,模型同輪補一行 |

- **主對話與子代理**:子代理內的呼叫也會觸發同一組 hook,`agent_type` 非空(2026-11 實測)。帳本兩者都記,統計只取 `agent_type` 為空的記錄,子代理的讀量不會算到主對話頭上。
- **實作輪**(對應 §7):本輪主對話改過 repo 內的檔(`Edit`/`Write`;記憶檔、暫存檔不算),或讀過 ≥5 個不同檔,或派過代理。問答輪不提醒。
- **一輪**:同 session、最後一個 UserPromptSubmit 標記之後;兩邊都有 `prompt_id` 時須相同。
- **同輪最多提醒一次**:`stop_hook_active` 為真就放行,並在帳本記 `Reminded`;同輪已有 `Reminded` 也放行。模型已寫「代理檢查」行(行首,容許 markdown 前綴)就不提醒。
- **看不到最後訊息就放行**:Stop payload 沒有字串型的 `last_assistant_message` 時,hook 無從判斷模型是否已寫那行,一律放行(StopCheck 記 `skip_no_msg`),`status` 會警告。後備方案是讀 `transcript_path`,試跑確認需要再做。
- **只算 Read**(使用者拍板):Bash、Grep 不算「讀」;`sed -i` 與 Bash 內的改檔量不到。
- **counsel 計數**:`Agent` 的 `subagent_type=counsel`,或實際用到 Opus 者(解析後模型優先;同步回應沒帶時看派工的 `model` 覆寫,`fork` 忽略覆寫);以 `tool_use_id` 去重。里程碑是提交訊息開頭的 R##(§4);時間取 `main` 上的 author date(rebase、amend 不改它),沒有 `main` 就退 HEAD;沒有 git 歷史就從帳本頭算。
- **內部錯誤**:一律 exit 0、不阻擋。寫帳本 `Error` 記錄,每個 session 只通知一次(PostToolUse、UserPromptSubmit 走 `additionalContext` 加 `systemMessage`;Stop 只走 `systemMessage`,不續跑)。不設 `onFailure: block`。
- **啟動失敗**:接線命令尾端是 `|| exit 1`。`python3` 找不到腳本時 exit code 是 2,而 Stop hook 的 exit 2 會擋下結束並把 stderr 餵給模型;腳本被刪、或切到沒有它的分支而 settings 還在時,可能無限續跑。降成 exit 1 就是看得見、不擋人。
- **帳本**:預設 `<repo>/.claude/ledger/ops.jsonl`(gitignore,權限 0600)。只在 `\n` 斷行(U+2028 等不當換行);檔尾被截斷時,下次寫入先補換行,殘行只害到自己;`path`、`tuid` 型別不對的記錄當缺值。環境變數 `SLG_OPS_LEDGER` 可替換路徑,測試一律用它,不碰真帳本。`python3 .claude/hooks/ops_ledger.py status` 印摘要,`/sync` 會跑它:最後一筆的時間要接近本 session 最近一次讀寫,很舊或是空的,就是 hook 沒載入。

### 接線(試跑放 `.claude/settings.local.json`,已 gitignore)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|Edit|Write|Agent",
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/ops_ledger.py\" post || exit 1", "timeout": 10 }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/ops_ledger.py\" prompt || exit 1", "timeout": 10 }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/ops_ledger.py\" stop || exit 1", "timeout": 10 }
        ]
      }
    ]
  }
}
```

要在 `/sync` 與日常免詢問地看摘要,另在同一檔加 `"permissions": {"allow": ["Bash(python3 .claude/hooks/ops_ledger.py status)"]}`。

### 試跑,再升格到 settings.json

- 試跑期放 `settings.local.json`,只影響本機。每個實作輪檢查:StopCheck 的數字和你的印象一致(改檔數、讀而未改行數、counsel 次數)、`Error` 為 0、提醒確實只補一次。
- 試跑要順手確認的未驗證項:(a) `prompt_id` 跨輪、`/compact` 後是否改變;(b) Stop 事件的 payload 有沒有 `prompt_id` 和 `last_assistant_message`(StopCheck 已記 `keys`、`has_msg`;沒有後者時提醒整套停用,`status` 會警告);(c) `decision: block` 在互動 session(VS Code)的實際表現。
- 數字正確後,把同一份 JSON 搬進 `.claude/settings.json`(O5:全域機制,影響所有後續 session),並補一條測試,斷言 settings.json 的接線與本節 JSON 一致。

### 已知限制

- Bash、Grep 不計入讀量;`sed -i` 改檔量不到。
- `claude -p`、`claude --agent counsel` 是獨立 process,不經 Agent 工具,不在帳本(§10)。新 session 載入 agent 檔後,走 Agent 工具即可。
- 帳本只讀尾端 4 MB。
- `SendMessage` 續用既有 counsel 子代理(又一輪 Opus)不入帳:matcher 不含它。是否算一次 counsel 待使用者定;若算,第二批把 `SendMessage` 加進 matcher 並記收件者(須先實測 PostToolUse 對這個延遲載入的工具是否觸發)。
- 兩個同時的 Stop 行程(check-then-act 無鎖)只有在重複接線時才會雙雙提醒;第二次 Stop 有 `stop_hook_active`,不成迴圈。
- repo 外的改檔(含 `~/.claude/settings.json`)不算實作輪。
- 第二批(未做):counsel 第 3 次先問、切 Opus 提醒。須先用 `-p` 實測相關事件是否存在,以及 auto 模式下 `ask` 的行為。
