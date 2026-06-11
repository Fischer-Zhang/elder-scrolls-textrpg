---
description: 換 session 前同步儀式:完整驗證 + 檢查表 + 提示更新 handoff.md
allowed-tools: Bash(bash check.sh:*), Bash(git status), Bash(git log:*), Bash(git diff:*)
---
執行「換 session 前同步」(對應 CLAUDE.md 換 session 前檢查表):

1. 跑 `bash check.sh --smoke`(完整驗證:編譯 → 全測試 → 條件式 sim → save/load 煙霧 → 自動清存檔)。**紅燈就停下,先修再說。**
2. 跑 `git status` 與 `git log --oneline -5`,讓我看未提交的工作與近期里程碑。
3. 逐項核對換 session 檢查表,逐條標 ✅/❌:
   - 全部測試全綠
   - sim 穩(無新 `⚠`,或 `⚠` 已人眼確認屬既定強項)
   - 煙霧通過
   - 對抗審查確認的 bug 都修了
   - 回歸測試都補了
   - **handoff.md 已記本輪里程碑**
4. 若 handoff.md 尚未記本輪 → **草擬**一條 §1 里程碑摘要(以及任何該新增/退役的 §3 `R##` 鐵律)給我確認後再寫入。**內容需我判斷,勿擅自大改 handoff。**
5. 全部就緒(全綠 + handoff 已更新)→ 依本專案慣例(R22)**自動 `git commit` & `git push origin main`**;紅燈則停下先修,不提交。
