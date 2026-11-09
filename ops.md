# 作業指南:子代理與模型分工(ops)

> 憲法(紅線、五階段流程)在 `CLAUDE.md`。本檔只回答三件事:誰做什麼、何時升級 Opus、子代理的邊界。
> 落地紀錄見 handoff.md R171。改這裡的規則時,同步 CLAUDE.md「協作分工」段與 R171。

## 1. 角色分工

| 角色 | 模型 | 做 | 不做 |
|---|---|---|---|
| 主對話 | Sonnet 5.5(使用者層預設) | 寫碼、跑測試、審查、提交、彙整建議 | 設計方向與平衡取捨(一律問使用者) |
| scout | Haiku 5.5(`.claude/agents/scout.md`) | 純檢索:定義、呼叫點、計數、資料列 | 判斷、審查、解讀架構 |
| counsel | Opus 5.5(`.claude/agents/counsel.md`) | 看簡報後給反例、風險、建議、信心 | 拍板、改檔、呼叫其他代理 |
| 使用者 | — | 設計方向、平衡取捨、里程碑拍板 | — |

內建 Explore 不覆寫。它跑主對話模型(Sonnet),用於需要理解架構或找根因的探索。scout 只做定位與計數。

## 2. 何時用哪一個

| 問題類型 | 用 |
|---|---|
| X 在哪、被誰呼叫、有幾個、某資料在哪一列 | scout |
| 根因是什麼、這段架構怎麼運作 | 內建 Explore(Sonnet) |
| 寫碼、改檔、跑測試、審查、提交 | 主對話(Sonnet) |
| 高風險決策的第二意見(見 §5) | counsel(Opus) |
| 純 JSON 內容、文件同步、機械重構、寫測試、跑 check.sh、提交 | 主對話,不升級 |

## 3. scout 使用規範

- 並行上限 3 個。
- 按**問題**切片,不按目錄切。一題一人,每題要能獨立回答。
- 簡報自包含:問題一句、搜尋範圍(路徑或 glob)、答案格式。scout 不會讀 CLAUDE.md,也不會讀本檔。
- 數量題:scout 回數字與 pattern 後,主對話用 Grep 的計數模式重算一次,才採用。
- `NOT FOUND` 是有效答案,不要逼它猜。
- scout 的結論只當線索。判斷與採納在主對話做。

## 4. counsel 簡報模板

主對話寫給 counsel 的簡報,依序填入:

1. **決策問題**:一句,用問句。
2. **事實與證據**:只寫可驗證的事實,每條附 `路徑:行號`。
3. **候選方案**:A、B(可加 C),每個寫出代價。**不寫主對話的傾向。**
4. **已排除的方案與理由**。
5. **相關 R## 原文**:最多 3 條,從 CLAUDE.md 或 handoff §3 原樣複製,不改寫。
6. **希望顧問回答的問題**:最多 3 條。

不寫「我的初步結論」,避免顧問被錨定。counsel 的輸出格式已寫在它的 agent 檔裡(最強反例、風險、建議、信心、會改變結論的證據、需拍板的點)。

## 5. 升級 Opus 的觸發(草案,可調)

符合下列任一條,才呼叫 counsel:

- 設計跨 3 個以上子系統,或會動 `re-sim` 紅線(戰鬥、施法、刺客、附魔常數)。
- 同一問題修 2 次仍紅。
- 不可逆決策:存檔格式、遷移、刪除玩家可見內容。
- 審查結論的真偽有爭議。R39 就出現過審查建議本身是誤報,所以審查結論要先驗證再採納。

**不升級:** 純 JSON 內容(R02)、文件同步、機械重構、寫測試、跑 check.sh、提交。

**上限:** 每里程碑 counsel 最多 2 次。第 3 次要先在對話裡寫一句理由,經使用者同意才呼叫。

## 6. 子代理與 git 紅線

- 子代理不得在共享工作樹執行會改 git 狀態的指令:`git stash`、`checkout`、`restore`、`reset --hard`、`clean`。R45 就是審查代理在共享工作樹 stash,險些把資料檔回退後提交。
- 需要隔離時(byte-identical 比對、會寫檔的驗證),用 worktree:`EnterWorktree` 或 `isolation: worktree`。
- scout 與 counsel 唯讀、沒有 Bash,本條對它們天然成立。本條主要約束其他子代理。

## 7. 對抗審查(CLAUDE.md 開發流程 4e)

- **預設**:主對話啟動一個 general-purpose 審查子代理,模型指定 `sonnet`,在 worktree 內依 4e 流程驗證。
- **多維 fan-out**(Workflow)只在使用者明說「用 workflow / fan out」或開啟 ultracode 時才跑。Workflow 工具的規定是須使用者明確同意。
- **Workflow 內 agent 指定模型**:偵察用 Haiku,審查與驗證用 Sonnet。語法以 workflow-authoring skill 為準,實作前先查,不照記憶寫。

## 8. 量測與回報

- 每里程碑在 handoff §4 記一行:本輪 scout 次數、counsel 次數、審查模式(單一或 fan-out)。
- 子代理成本以 token 計(各模型的 input、output、cache),不以美元。美元數字是牌價換算,不是帳單。
- 背景啟動(`status: async_launched`)的子代理,PostToolUse 只回 `resolvedModel`,不回 token 數。要量 token,看 `claude -p --output-format json` 的 `modelUsage`。

## 9. 變更本指南

- 換模型:改 `.claude/agents/*.md` 的 `model` 行,跑 `tests/test_agents.py` 與 §10 的現場驗證。
- 改分工或升級觸發:同步 CLAUDE.md「協作分工」段與 handoff R171。

## 10. 現場驗證(改 agent 檔後)

在專案目錄執行 `claude -p`,請主對話委派對應子代理,再檢查輸出 JSON 的 `modelUsage`:

- scout:應出現 `claude-haiku-5-5`,且 input(含 cache)遠小於主對話載入 CLAUDE.md 的量,證明 `omitClaudeMd` 生效。
- counsel:應出現 `claude-opus-5-5`。

這會花少量額度。先取得使用者同意,並設 `--max-budget-usd` 上限。

- 指令尾端加 `< /dev/null`,避免 CLI 等 3 秒 stdin。
- 在本 repo 用 `-p` 時,CLI 會因工作區未受信任而忽略 `.claude/settings.json` 的 `permissions.allow`。這不影響子代理載入。
