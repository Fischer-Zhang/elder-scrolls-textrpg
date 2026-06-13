# CLAUDE.md — 流亡者 (tesrpg) 開發憲法

上古卷軸風格的**技能驅動沙盒文字 RPG**(終端機,Python + `rich`;另有瀏覽器 Web 版)。
單一英雄、learn-by-doing(做什麼練什麼)、跨八省探索鑽地城。

> **本檔是給 Claude 的開發憲法**:每次改動都適用的節奏 + 跨領域紅線 + 提交檢查表 + 子系統鐵律「索引」。
> 子系統鐵律**本體**在 [handoff.md](handoff.md) §3(以 `R##` 標號);完整現況清單見 handoff §1;設計理念見 [DESIGN.md](DESIGN.md);玩家「怎麼玩」見 [README.md](README.md)。

## 怎麼跑 / 測試

```bash
python3 -m tesrpg                        # 終端機版
python3 -m tesrpg.web                     # Web 版 → http://127.0.0.1:8080
python3 tests/run_all.py                  # 全綠;模組數見結尾「全部通過 (N 個測試模組)」(別在文件硬寫數字)
bash check.sh                             # ★ 一鍵驗證:編譯 → 全測試 → 條件式 sim(= /check;見下「自動化」)
shopt -s globstar; python3 -m py_compile tesrpg/**/*.py tesrpg/*.py tests/*.py   # 純編譯檢查(完整形;少了 tesrpg/*.py 會漏掉 main/state/formulas 等頂層模組)
PYTHONPATH=. python3 sim_assassin.py      # 平衡回歸模擬(改戰鬥常數後必跑)
```
- Python 3.12;`rich` 由系統套件提供(`python3-rich`)。⚠️ 本機**沒有 pip/pytest**、sudo 需密碼、無 `jq`(寫 hook 要用 `python3` 解析 stdin)。
- 存檔在 `~/.tesrpg/save.json`(repo 外;煙霧測試/實跑後記得清)。

## 開發流程(每個里程碑走完五階段;⚠ 一次只推一個里程碑)

1. **評估**:理解範圍 / 找根因 / 盤點選項(範圍不明就走 plan-mode:Explore→Plan 子代理)。
2. **決定方向**:給選項、讓使用者拍板(功能性 > 數值;不替使用者預設方向)。
3. **實作**(data + systems + main/ui;內容優先純改 JSON)。
4. **驗證**(全綠才算數;一鍵 a–c = `bash check.sh` / `/check`):
   - a. 單元測試 `tests/run_all.py`(新測登錄 run_all,須全綠)
   - b. 平衡模擬:改戰鬥常數跑 `sim_assassin.py`,勝率/回合數不退化
   - c. 無頭煙霧:`Console(file=StringIO())` + 自動選單抓 traceback
   - d. 對抗審查(Workflow):多維 fan-out → 獨立懷疑者**對抗式驗證**,只留能真實重現的
   - e. 覆核+修正:逐一覆核(有誤報、也有「會引入新 bug 的錯誤修法」)→ 補回歸測試 → 重跑全套
5. **修改文件 + 提交推送**:同步 `handoff.md`(§1 現況 / §3 鐵律 R##)與必要的 `CLAUDE.md` → **驗證綠即自動 `git commit` & `git push origin main`(本專案慣例,見 handoff §3 R22;不需明說。紅燈則不提交、先修)**。

## 鐵律總則(跨領域紅線,全文)

- **成長/夾限只用 `base_skill()/base_attr()`**;裝備/吸血鬼/斯庫瑪/里程碑加成走獨立疊加層,**絕不寫回 base**。
- **任何改動 `char.equipped`(穿/卸/丟/賣)後必 `stats.recompute_max_resources(char, gamedata)`**(務必帶 gamedata,否則 fortify 視為 0)。
- **改任何戰鬥/施法/刺客/附魔常數 → 必跑 `sim_assassin.py`**,守 `SOLO_SNEAK_DAMAGE_CAP_RATIO`(偷襲不秒 solo boss)、群體規模反制、麻痺 solo boss 免疫等紅線。
- **同源多節點 getter 必聚合**(相加/取最/取後),不得 first-wins 遮蔽。
- **存檔向後相容**:新技能 → `progression.ensure_all_skills`;新里程碑欄 → `ensure_mastery_choices`;新欄位 → dataclass 預設值(`from_dict` 走 `cls(**d)`)。
- **內容優先純改 `data/*.json`**(地點/怪/物品/法術/任務/事件/開局/里程碑),不動邏輯。
- **數量別盲信**:文件中的技能/地點/測試數是快照;有疑義以 `run_all.py` 輸出、`len(gamedata.skills)`、JSON 為準並順手更新。

## 子系統鐵律索引(本體見 handoff §3 `R##`;標籤:`re-sim`=重跑 sim、`recompute`、`migrate`=ensure_*、`save`=存檔相容)

| R## | 一行要旨 | 標籤 |
|---|---|---|
| R01 | 碼/變數/key 英文,玩家文字繁中 | |
| R02 | 新增內容只改 JSON、不動邏輯 | |
| R03 | `to_dict/from_dict` 全欄 + `cls(**d)` 預設 + 防禦夾限;`active_effects` 不入檔 | save |
| R04 | `resolve_attack` 通用任意組合;`clamp_resources` 只玩家側 | |
| R05 | `max_health` 是有效上限;改 equipped 後必 recompute(帶 gamedata) | recompute |
| R06 | `level_xp` 餵升級;`from_dict` 自動 `ensure_level_xp` 別繞過 | migrate |
| R07 | 偷襲 `opening` 條件;副手傷害在 `sneak_mult` 之後;隱遁三道煞車缺一不可 | re-sim |
| R08 | 偵查備戰 `prep_budget`;召喚預載 `battle["allies"]`;prep 在 while 前保 opening | |
| R09 | 運動=旅行加速 + 降戰鬥體力;格擋實扣 `BLOCK_FATIGUE_COST` | |
| R10 | `magic.cast` 玩家專用;扣魔再擷體力;力竭 ×0.75 連 summon HP 也乘 | re-sim |
| R11 | 難度靠 `min_level` + `danger`,**不**縮放怪數值;`solo`/`raw` 旗標 | |
| R12 | 地點帶 `biome`、怪帶 `biomes`;無標籤=通用墊底池 | |
| R13 | `events/quests` 可加 `provinces` 做在地化 | |
| R14 | `fire/frost/shock` 吃 `magic` 抗性;`poison/disease` 不吃 | |
| R15 | 附魔載體 `encha/enchj/enchw/enchws`;`synth` 段數相容;麻痺 solo boss 免疫紅線 | recompute, re-sim |
| R16 | 公會規則在 `factions.py`/資料 `factions.json`;分支任務推進務必保留 `branch` | |
| R17 | AoE 每敵各取**獨立** `make_status_effect` dict(勿共用) | |
| R18 | `apply_origin` **只改處境不動屬性/技能**;別起在地城/`danger≥4` | |
| R19 | `vampirism.update` 每圈頂端;`vampire_*` 獨立層;疾病抗性削感染 | migrate, recompute |
| R20 | `skooma.update` 在 vampirism 後;亢奮**絕不碰 strength/sneak/武傷** | re-sim, migrate |
| R21 | 門檻只認 `base_skill()`;新 kind 三步登錄(`_IMPLEMENTED_KINDS`+getter+呼叫端);溢盾夾總量 cap | re-sim, migrate |
| R23 | 對話條件複用 `events.meets`(無 state 鍵就地加、需 state 走 `meets_dialogue`);hostile=拒談 `topics_for` 回 `[]`;帶持久 effect 話題必標 `once`(`dialogue_done` 去重防零成本刷分);`faction_standing` 互斥+表態一次性 | save |
| R24 | AI 戰爭 `aiwar.update` 在 worldstate 後/tick_tax 前;決定性 `rng`+`sorted`(迭代序不餵 rng);玩家城只削 garrison 不寫 world_faction(三層免疫);改常數必跑 `sim_worldwar`(防雪球**含玩家選邊**、霸權煞車在外交後套) | re-sim, save |

## 自動提交閘門 / 換 session 前檢查表

**提交是自動的**:驗證全綠 → `git commit` & `git push origin main`(本專案慣例,**不需使用者明說**;紅燈則不提交、先修)。推送前先過這道閘(一鍵 `/check` = `bash check.sh`):
- [ ] `python3 tests/run_all.py` 全綠(讀結尾印的模組數,勿信文件數字)
- [ ] 觸戰鬥/施法/刺客/附魔常數 → `PYTHONPATH=. python3 sim_assassin.py`(或 `./check.sh --sim`)
- [ ] 編譯檢查通過(`check.sh` 已含完整 `py_compile`)
- [ ] 若跑過煙霧/實跑 → `rm -f ~/.tesrpg/save.json`(`check.sh --smoke` 會自動清)
- [ ] 改了規則/數量/現況 → 同步 `handoff.md`(§3 鐵律 R## / §1 現況)
- [ ] commit 訊息末加 `Co-Authored-By:` 行 → `git push origin main`

**換 session 前**(= `/sync`):全綠 + sim 穩 + 煙霧通 + 審查確認 bug 修完 + 回歸測試補完 + **handoff.md 已更新本輪里程碑**(且本輪工作已 commit & push)。

## 自動化(`.claude/` 已配置)

- `check.sh` — 單指令驗證鏈(完整 `py_compile` → `run_all.py` 硬閘門 → 偵測到改 `formulas.py`/`combat.py` 或 `--sim` 才跑 sim 並標出 `⚠` 行 → `--smoke` 才跑煙霧並 trap 清存檔)。
- `/check` slash-command = `bash check.sh`;`/sync` = 跑 `check.sh --smoke` + 印換 session 檢查表 + 提示更新 handoff.md。
- `.claude/settings.json` 已預許可唯讀測試/sim/git 指令(減少權限詢問)。`git commit`/`push` **不**預許可(刻意保留可見),但依本專案慣例驗證綠後仍自動執行(見上「自動提交閘門」/ handoff §3 R22)。

## 架構 / 重要檔案

- **資料驅動**:規則引擎在 `tesrpg/systems/*.py` + `tesrpg/formulas.py`;內容全在 `tesrpg/data/*.json`
  (races/birthsigns/classes/skills/spells/weapons/armor/recipes/bestiary/world/dungeons/quests/factions/events/origins/rulers/mastery/landmarks…)。
- **核心循環**:行動制(在地點選行動 → 推進時/日 → 觸發事件/遭遇);戰鬥是回合制子迴圈。
- 進入點/主迴圈:`tesrpg/main.py`;狀態/存檔:`tesrpg/state.py`;角色:`tesrpg/models/character.py`。
- 規則:`tesrpg/formulas.py` + `tesrpg/systems/*.py`(combat/magic/progression/mastery/smithing/vampirism/skooma/politics…)。
- UI:`tesrpg/ui/console.py`(rich)+ `tesrpg/web/`(Web)。平衡工具:`sim_assassin.py`;設計/交接:`DESIGN.md`、`handoff.md`。
