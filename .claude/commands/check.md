---
description: 一鍵驗證鏈(編譯 → 全測試 → 條件式平衡模擬);可加 --sim / --smoke
argument-hint: "[--sim] [--smoke]"
allowed-tools: Bash(bash check.sh:*)
---
跑 `bash check.sh $ARGUMENTS`(對應 CLAUDE.md「提交前檢查表」與「開發節奏」)。

- 任何步驟未過(腳本非零退出)→ 指出是哪一步(py_compile / run_all / sim / smoke)、貼關鍵錯誤行,然後停下等我決定,不要擅自修。
- 若出現 sim 的 `⚠` 旗標 → 摘要那幾行,並提醒這可能踩到刺客平衡紅線(見 handoff §3 R07/R10/R15/R20/R21)。
- 全通過 → 簡短回報「✅ check 全通過」即可。
