# CLAUDE.md — 流亡者 (tesrpg) 開發憲法

上古卷軸風格的**技能驅動沙盒文字 RPG**(**瀏覽器 Web 版**;Python 後端,`rich` 把畫面渲成 HTML)。
單一英雄、learn-by-doing(做什麼練什麼)、跨八省探索鑽地城。
> ⚠ **本專案已 Web-only**:終端機版(`python3 -m tesrpg`)已移除;`tesrpg/ui/console.py` 現為 Web 的渲染/輸入接層(rich→HTML view-model + `_web_prompt`),5 個輸入原語在無 web backend 時直接 raise。

> **本檔是給 Claude 的開發憲法**:每次改動都適用的節奏 + 跨領域紅線 + 提交檢查表 + 子系統鐵律「索引」。
> 子系統鐵律**本體**在 [handoff.md](handoff.md) §3(以 `R##` 標號);完整現況清單見 handoff §1;設計理念見 [DESIGN.md](DESIGN.md);玩家「怎麼玩」見 [README.md](README.md);**全增益效果目錄(含實際數值/疊加規則,按來源層橫切)見 [BUFFS.md](BUFFS.md)**(改增益常數順手更新);**角色構築縱切盤點(按 build 走完所有層+分支取捨)見 [build.md](build.md)**;**全怪物圖鑑(數據+行為+掉落,由 `tools/gen_bestiary.py` 自動生成)見 [BESTIARY.md](BESTIARY.md)**(改 bestiary 順手重生)。

## 怎麼跑 / 測試

```bash
python3 -m tesrpg.web                     # Web 版(唯一進入點)→ http://127.0.0.1:8080
python3 tests/run_all.py                  # 全綠;模組數見結尾「全部通過 (N 個測試模組)」(別在文件硬寫數字)
python3 tests/browser_ui.py               # Playwright/Chromium 桌面 UI 真瀏覽器回歸
bash check.sh                             # ★ 一鍵驗證:編譯 → 單元/流程 → 真瀏覽器 → 條件式 sim
shopt -s globstar; python3 -m py_compile tesrpg/**/*.py tesrpg/*.py tests/*.py   # 純編譯檢查(完整形;少了 tesrpg/*.py 會漏掉 main/state/formulas 等頂層模組)
PYTHONPATH=. python3 sim_assassin.py      # 平衡回歸模擬(改戰鬥常數後必跑)
```
- Python 3.12;遊戲 runtime 的 `rich` 可由系統套件提供(`python3-rich`);dev 工具走 `.[dev]`。sudo 需密碼、無 `jq`(寫 hook 要用 `python3` 解析 stdin)。
- 真瀏覽器測試是 dev-only:安裝 `.[dev]` 後執行 `python3 -m playwright install --with-deps chromium`;遊戲 runtime 仍只有 `rich`。
- 存檔在 `~/.tesrpg/saves/slotN.json`,名人堂在 `~/.tesrpg/hall.json`(repo 外的真實資料;測試與 `check.sh`,含 `--smoke`,都不碰)。

## 開發流程(每個里程碑走完五階段;⚠ 一次只推一個里程碑)

1. **評估**:理解範圍 / 找根因 / 盤點選項(範圍不明就走 plan-mode:Explore→Plan 子代理)。
2. **決定方向**:給選項、讓使用者拍板(功能性 > 數值;不替使用者預設方向)。
3. **實作**(data + systems + main/ui;內容優先純改 JSON)。
4. **驗證**(全綠才算數;一鍵 a–d = `bash check.sh` / `/check`):
   - a. 單元測試 `tests/run_all.py`(**自動探索** `tests/test_*.py`:新模組/新測試函式皆無需登錄;每模組 `run()` 用 `sorted(globals())` 跑全部 `test_*`;須全綠)
   - b. 真瀏覽器回歸 `tests/browser_ui.py`:Chromium 走正式 `index.html`+HTTP/SSE+`/input`,驗桌面版面/互動/持久化;**不可缺依賴就 skip**
   - c. 平衡模擬:改戰鬥常數跑 `sim_assassin.py`,勝率/回合數不退化
   - d. 無頭煙霧:WebBackend 自動作答驅動 `main()`(或 patch `ui.menu`/`Console(file=StringIO())`)抓 traceback
   - e. 對抗審查:預設單一 Sonnet 審查子代理(worktree 內);多維 fan-out(Workflow)需使用者明說或 ultracode,見 ops.md §9 → 獨立懷疑者**對抗式驗證**,只留能真實重現的
   - f. 覆核+修正:逐一覆核(有誤報、也有「會引入新 bug 的錯誤修法」)→ 補回歸測試 → 重跑全套
5. **修改文件 + 提交推送**:同步 `handoff.md`(§1 現況 / §3 鐵律 R##)與必要的 `CLAUDE.md` → **驗證綠即自動 `git commit` & `git push origin main`(本專案慣例,見 handoff §3 R22;不需明說。紅燈則不提交、先修)**。

## 鐵律總則(跨領域紅線,全文)

- **現實邏輯優先於平衡**(R138b 使用者鐵令):機制的字面數值關係不得違反物理/主題直覺(如盾防元素>防物理、布甲>鐵甲、火燒治癒);**即使端到端數學能自圓、平衡實測更好看,違反直覺的設計一律推翻或先問使用者**——平衡在現實邏輯的框架內調,不得反過來(先例:重盾元素卸力恆≤物理,知情接受 gauntlet 100→0% 回落;同族:R45/R115 誓福按原典)。
- **成長/夾限只用 `base_skill()/base_attr()`**;裝備/吸血鬼/斯庫瑪/狼人/里程碑/**達貢之力**加成走獨立疊加層,**絕不寫回 base**。
- **任何改動 `char.equipped`(穿/卸/丟/賣)後必 `stats.recompute_max_resources(char, gamedata)`**(務必帶 gamedata,否則 fortify 視為 0)。
- **改任何戰鬥/施法/刺客/附魔常數 → 必跑 `sim_assassin.py`**,守 `SOLO_SNEAK_DAMAGE_CAP_RATIO`(偷襲不秒 solo boss)、群體規模反制、**fear/paralyze solo boss 機率減免**(`SOLO_CONTROL_RESIST_CHANCE`;R44 改為機率抵抗,非完全免疫)等紅線。
- **所有控場(fear/paralyze/stagger/slow/weaken)施加一律走 `magic.apply_control`**(R44 單一決策點:硬控去重 + 玩家 willpower/solo BOSS 機率抵抗 + 軟控照施);**絕不**就地 `active_effects.append({"kind":控場})`。
- **同源多節點 getter 必聚合**(相加/取最/取後),不得 first-wins 遮蔽。
- **存檔向後相容**:新技能 → `progression.ensure_all_skills`;新里程碑欄 → `ensure_mastery_choices`;新欄位 → dataclass 預設值(`from_dict` 走 `cls(**d)`)。
- **內容優先純改 `data/*.json`**(地點/怪/物品/法術/任務/事件/開局/里程碑),不動邏輯。
- **數量別盲信**:文件中的技能/地點/測試數是快照;有疑義以 `run_all.py` 輸出、`len(gamedata.skills)`、JSON 為準並順手更新。

## 協作分工(四原則;細則見 ops.md)

| 角色 | 做 | 不做 |
|---|---|---|
| 主對話(Sonnet) | 引導流程、寫碼、測試、審查、提交、彙整各代理結果 | 設計方向與平衡取捨(問使用者) |
| scout(Haiku,`.claude/agents/scout.md`) | 大量閱讀(讀而不改 >~1000 行或 ≥5 檔)、檢索、摘要;附 路徑:行號 | 判斷、審查、解讀架構 |
| counsel(Opus,`.claude/agents/counsel.md`) | 紅線區設計取捨、全專案收斂點、驗證反常、推翻鐵律時,給反例/風險/建議 | 拍板、改檔 |

- 🔴 Opus 只給建議、不拍板;counsel 每里程碑至多 2 次、簡報 ≤150 行、不開 `/advisor`;有實作的輪次結尾寫一行「代理檢查」。
- 🔴 scout 並行 ≤3、按問題切;子代理不得在共享工作樹改 git 狀態(stash/checkout/restore/reset --hard/clean),需隔離用 worktree。

## 子系統鐵律索引(本體見 handoff §3 `R##`;標籤:`re-sim`=重跑 sim、`recompute`、`migrate`=ensure_*、`save`=存檔相容)

> 每列是**索引摘要**(函式/檔案/紅線重點)。完整條文在 handoff.md §3 `### R##`;瘦身前全表見 git `7ec6d2c:CLAUDE.md`。**新增 R## 時:handoff §3 寫本體、此表加一列 ≤120 字摘要,兩處一起改。**

| R## | 一行要旨 | 標籤 |
|---|---|---|
| R01 | 碼/變數/key 英文,玩家文字繁中 |  |
| R02 | 新增內容只改 JSON、不動邏輯 |  |
| R03 | to_dict/from_dict 全欄 + cls(d) 預設 + 防禦夾限 | save |
| R04 | resolve_attack 通用任意組合 |  |
| R05 | max_health 是有效上限 | recompute |
| R06 | level_xp 餵升級 | migrate |
| R07 | 偷襲 opening 條件 | re-sim |
| R08 | 偵查備戰 prep_budget |  |
| R09 | 運動=旅行加速 + 降戰鬥體力 |  |
| R10 | magic.cast 玩家專用 | re-sim |
| R11 | 難度靠 min_level + danger,不縮放怪數值 |  |
| R12 | 地點帶 biome、怪帶 biomes |  |
| R13 | events/quests 可加 provinces 做在地化 |  |
| R14 | fire/frost/shock 吃 magic 抗性 |  |
| R15 | 附魔載體 encha/enchj/enchw/enchws | recompute, re-sim |
| R16 | 公會規則在 factions.py/資料 factions.json |  |
| R17 | AoE 每敵各取獨立 make_status_effect dict(勿共用) |  |
| R18 | apply_origin 只改處境不動屬性/技能 |  |
| R19 | vampirism.update 每圈頂端 | migrate, recompute |
| R20 | skooma.update 在 vampirism 後 | re-sim, migrate |
| R21 | 門檻只認 base_skill() | re-sim, migrate |
| R23 | 對話條件複用 events.meets(無 state 鍵就地加、需 state 走 meets_dialogue) | save |
| R24 | AI 戰爭 aiwar.update 在 worldstate 後/tick_tax 前 | re-sim, save |
| R25 | 房產 house_stash 不計負重(存穿戴擋免漏 recompute) | re-sim, recompute, save |
| R26 | 湮滅危機主線=source:"main" + requires_event/requires_faction gate(avai… | re-sim, recompute, save |
| R27 | Web-only |  |
| R28 | pos 座標與 links 連線皆依正典 TES 地理(UESP | re-sim, save |
| R29 | 城鎮服務專精化:訓練師可教技 = trainers.json「skills」覆寫→公會推導系(world._GUILD_SPEC… |  |
| R30 | 煉金限時增益藥水:brew 出強化屬性/技能/抗元素限時藥(synth brewb) | recompute, save |
| R31 | 毒劑深化:五毒型(DoT/麻痺基礎 + 衰毒 weaken·遲緩 slow〔唯一新 combat kind:降 _speed+命… | re-sim, save |
| R32 | 煉金效果逐步揭露:材料效果預設 ???,三源揭露(嚐一口 taste 決定性消耗 / 煉製成功 brew 回 learn 鍵由呼… | save |
| R34 | 技能里程碑深化:冷技能身份化(檔A)；🔴 on_evade 每回合至多一次(_evade_counter_used,回合頂重置)防反制隨敵… | re-sim, save |
| R33 | 裝備耐久/修理整套移除 | re-sim, save |
| R35 | 技能里程碑深化:去冗餘/修 no-brainer 波次；🔴 對抗審查自我糾錯:初版 whirl_riposte(on_evade-counter)換軸重演隱… | re-sim, save |
| R36 | security 功能化 + 核心 loop 修復(混合身份:地城入侵+盜賊) | save |
| R37 | smithing 功能化身份(混合:工匠·省料 vs 鋒銳·淬鍊威力)；🔴 必跑 sim_assassin(temper flat 進偷襲倍率前):apex_temper(… | re-sim, save |
| R38 | speechcraft 功能化身份(混合:社交問題解決者 + 戰場號令) | save |
| R39 | 使用者點名兩改:block 盾反 + empower 遞減疊加曲線；🔴 流程教訓(ask-before-balance-tradeoffs 記憶):審查建議「32%→M… | re-sim |
| R40 | 弓手散兵戰技:由「裝弓即免費」改為 marksman 里程碑解鎖；🔴 skirmish 解鎖依賴(使用者拍板):散兵走位複用 vanish,拔掉 can_vanish… | save |
| R41 | 雙手武器握法系統 + 鈍器 mace/axe 分流；🔴 三提交每個跑 sim_assassin byte-identical(刺客匕首非 mace/ax… | re-sim, save |
| R42 | 反傷流功能化:反傷吃 raw(解耦護甲)+ 荊棘附魔身份；🔴 不夾(使用者拍板):紅線靠①物理限定(元素 solo boss〔湮滅系全元素〕反傷流完全不反=天… | re-sim |
| R43 | 怪物攻擊多樣化:多攻擊模式曲目 + on_hit 控場放寬(全控)；🔴 雙軌防禦:on_hit 在 if hit: 內→落空連控帶傷全免(閃躲第一道·通用) | re-sim, save |
| R44 | BOSS 控場「機率減免」+ 控場施加集中化(收斂 stagger 不一致)；🔴 改 R31/R15「solo 完全免疫」→ 機率減免(更新 5 舊免疫測試為機率模型 + 新 t… | re-sim, save |
| R45 | 後期內容:戴德拉誓福引擎 + 神殿任務(首位親王 阿祖拉)；🔴 誓福不碰 sneak/武傷·strength≤達貢 → sim_assassin byte-id… | recompute, save |
| R47 | 灰狐面具 talk_down_cap + 盜賊神器換手(使用者點名:盜賊公會神器改灰狐面具〔提高可協商罰金〕·骷髏鑰改 Noct…；🔴 back-compat 無源回 {} | save |
| R48 | 秩序之劍 order 附魔:移除傷害變異(第十五位親王 Jyggalag 神器·反 Wabbajack)；🔴 byte-identical:非 order 武器走原 rng.roll(同值·同一次抽)→ r… | re-sim |
| R46 | Wabbajack 命中隨機混沌效果(瘋神謝歐格拉斯神器·第一個 R45「需新機制」親王)；🔴 紅線靠「複用 helper + 直接賦值非遞迴」:爆發非偷襲傷·staff 零 sneak·so… | re-sim |
| R49 | 戴德拉神殿線 末位親王 Hermaeus Mora(禁忌真知)+ Oghma 無限祕典三徑機制(17 親王神殿線全集)；🔴 byte-identical:未碰 combat/formulas·誓福 fixtures bo… | recompute, save |
| R50 | 血月詛咒深化:吸血鬼/狼人(月相 + 主動獸性 + 識破圍捕)；🔴 平衡:滿月只給可用性/時程·圍捕用既有 city_guard → byte-identical | re-sim, save |
| R51 | 詛咒巢穴與同類:吸血鬼隱穴 + 狼人巢穴(安全區·同類 NPC·招募 kin)；🔴 安全區:巢穴非城/鎮 → _curse_manhunt 天然不觸發(零改 R50) | re-sim, save |
| R52 | 血族階級政治 + 巢穴升級:吸血鬼血族 / 狼人獵群階級梯；🔴 sim byte-identical(perk 只詛咒模組讀·刺客永不入會·隔離 worktre… | re-sim, save |
| R53 | 疾病系統 + 統一治癒(含吸血/狼人潛伏期解除)；🔴 sim byte-identical(動 combat/character 仍隔離 worktr… | re-sim, save |
| R54 | 疾病可釀:煉金療疾藥水(R53 收尾)；🔴 零回歸:cure_disease 只在 3 材料·現有測試無任一「雙療疾」配對→既有 buff/… | re-sim, save |
| R55 | 成就/重玩性:首達通知 + 後期成就(複用 accessor·零存檔欄)；🔴 零存檔欄·不碰 combat→sim_assassin byte-identical(隔離 wo… | save |
| R56 | 吸血鬼能力深化:夜視 + 魅惑(戰鬥+社交)+ 偽裝暗影套裝 | re-sim, recompute, save |
| R57 | 血族/獵群任務線深化 + 夜影套裝改高階 capstone | re-sim, save |
| R58 | Web 故事日誌:敘事 log 區持久化(分區捲動)；🔴 鐵律:狀態快照走 view block(替換)·敘事/旁白走 log block(入日誌)·絕不… |  |
| R59 | 角色卡里程碑頁面 redesign:扁平 154 卡 → 系統/技能折疊手風琴 + 配對卡 + 三態；🔴 改顯示動 _masteries_view+renderMasteries+.msk-* CSS |  |
| R60 | 遊戲內指南/圖鑑(codex):深沙盒 how-to 入口；🔴 加/改分類純改 data/codex.json(R02·section h/p/kv/li·id… |  |
| R61 | 種族深化:戰系主動威能(第二威能槽)+ 其餘被動天賦(混合身份)；🔴 絕不進匕首/blade·不餵偷襲)、亞龍 histskin(rest HP×1.5)、高精靈 m… | re-sim |
| R62 | 職業深化:偏好屬性功能化(創角 +5)+ 專精跑時加速(同系技能 +20% XP)；🔴 平衡(非 byte-identical·必跑 sim):刺客偏好 speed/agility +… | re-sim |
| R63 | 屬性深化:讓每個屬性過 200 仍有意義(漸進曲線 + 第二段效果)；🔴 hit_chance 完全不動(刺客 agi55 撞 0.95 舊夾·改它即破 byte-ide… | re-sim, recompute, save |
| R64 | 升級資源精簡:移除三選一資源 + 屬性點 4→5(資源全屬性驅動)；🔴 存檔相容:char.resource_levels 欄位保留、stats.recompute_m… | save |
| R65 | 魔抗再分配:意志 + 大法師套裝給魔抗 + 布萊頓魔抗下修；🔴 sim_assassin byte-identical(刺客 khajiit wp30→0 魔抗… | re-sim, recompute |
| R71 | 隱遁不再無敵:純再潛行(無防禦)+ 命中地板 5%→3%；🔴 sim_assassin 全綠:solo 偷襲秒殺 0%·R63 追擊 0%(vanish/fl… | re-sim |
| R72 | 無聲披掛也免「偷襲傷害」護甲折扣(對稱命中端 + 修 R70 過時註解)；🔴 sim_assassin BYTE-IDENTICAL(隔離 worktree vs HEAD … | re-sim |
| R73 | 冰系法術補控場:凍麻 benumb(純減命中軟控)；🔴 sim_assassin BYTE-IDENTICAL(隔離 worktree·碰 combat… | re-sim |
| R74 | 冰系高級法術 + 三系終極法術(純 JSON 內容)；🔴 sim_assassin BYTE-IDENTICAL(純資料改·刺客不施法) | re-sim |
| R75 | 電系識別:感電易傷 conduct(疊層放大電傷)+ 電傷降火/冰中間；🔴 sim_assassin BYTE-IDENTICAL(magic.cast only·刺客不施… | re-sim |
| R76 | 法術 DoT/HoT 吃法術威力(一致性修復)；🔴 sim_assassin BYTE-IDENTICAL(magic.cast only·刺客不施… | re-sim |
| R77 | 法杖施法焦點(spell focus:持杖強化施法,非只 OOM 近戰棒)；🔴 sim_assassin BYTE-IDENTICAL(刺客不施法/持匕首非杖→getter 回… | re-sim |
| R78 | 終極法術改任務取得 + 三系完全體大法師 + 合體王頂點(R-arcane)；🔴 sim_assassin BYTE-IDENTICAL〔未碰 combat/formulas·刺… | re-sim, save |
| R114D | 長途旅行:BFS 沿路自動趕路(UI/UX 審計 包D·收尾)；🔴 rng 等同手動逐跳(route 零 rng·每跳 world.travel 抽同序→byte-… |  |
| R115 | 九神深線:神之選民試煉 + 永久神性誓福(首位 阿卡托什·R45 引擎複用)；🔴 使用者鐵令:加成一律按原典神格設計·破 R45 紅線僅通知由使用者定奪·不擅作更換〔記憶 [[b… | save-safe |
| R116 | 幸運功能化:傷害骰下界抬升 + 瓦巴賈克回火化險(天命影響數值浮動與隨機效果)；🔴 上界 HI=1.15 永不動(不抬單擊天花板/精英秒殺門檻·骰在偷襲倍率+solo 夾前 → s… | re-sim |
| R117 | 敵方反傷:秩序騎士「灰潮的反噬」(物理反傷·懲罰爆發/秒殺)；🔴 直接扣血非遞迴(不觸發玩家自身 thorns → 無環)·reflect==0 短路 → byt… | re-sim |
| R118 | 變化系功能化:負重控場線 + 破盾反震(石膚反擊)；🔴 校準 ≤0.3 恆等舊 flat 0.15→既有 slow byte-identical·唯負重… | re-sim |
| R126 | 戰鬥中喝藥:回合制用藥(近戰/潛行終獲中場續戰)；🔴 sim 驗(sim_builds 加用藥 fidelity·近戰 fixture 帶 8 治療·… | re-sim, save-safe |
| R127 | 物理抗性正規化 + 達貢真身(秘術對決·pen-免疫物理牆)；🔴 玩家 cap 使用者拍板中等 25%(知情:apex 潛行滿物抗 4-bandit 死亡 60%… | re-sim, save |
| R128 | 全怪物物理抗性:按適合程度填入 41 怪；🔴 sim_assassin BYTE-IDENTICAL(意外):assassin 對 tough… | re-sim, content |
| R129 | 同伴深化:同伴變「類玩家角色」(屬性+技能+裝備驅動戰力)+ 裝備槽戰利品 sink + 戰術傾向；🔴 sim_assassin BYTE-IDENTICAL(隔離 worktree diff HEA… | re-sim, save |
| R130 | 同伴收尾:血僕/同窩戰士專屬支線+忠誠頂點(補齊平齊)+ fortify_skill 護甲平價；🔴 紅線發現(擴 sim 守衛揪出·[[byte-identical-vacuous-for-new… | re-sim, content |
| R131 | 元素抗性算法改分兩段(元素層×魔抗層):修「元素+魔抗疊過100歸零」硬牆 → 元素法師可通關；🔴 終王牆守:solo 元素法師 vs 達貢/dagon_true=0%(秘術師 solo dago… | re-sim |
| R132 | 閃避來源重構:雜技+敏捷雙主軸「單一投入遞減」+ 敏捷通用反射(接受更耐打·放寬 R71)；🔴 硬紅線守:solo 一擊秒殺全 0%·R63 追擊 0%(閃避與偷襲傷正交) | re-sim |
| R133 | 達貢三形物理抗性階梯 70/50/30(「物理不獨大」終王)；🔴 紅線:偷襲秒殺全 0%(cap 主導·物抗只讓偷襲傷更小) | re-sim, content |
| R134 | BOSS 召喚爪牙:18 王名冊 + 殺王潰散 + 爪牙三重排除(戰利品/擒魂/擊殺計數)；🔴 平衡:名冊王勝率維持 | re-sim, save-safe, content |
| R135 | 召喚爪牙擴充:增援變體 5 王 + 瘋神隨機爪牙表 + BESTIARY【召喚】tag(+重大裁決:配爪牙王=帶隊向)；🔴 重大發現+裁決:名冊王多為試煉/進度王·質量閘原只驗完全體 | re-sim, content |
| R136 | 弓手里程碑重造:75 箭雨(AoE)+ 100 雙側救活(連珠箭/獵手之眼)；🔴 永不吃偷襲倍率(呼叫端硬寫 sneak=False) | re-sim |
| R161 | 玩家文字用語一致性大掃除:同概念異詞正規化(承使用者「全面檢查 one-off wording bug·我來決定如何改」)；🔴 純顯示字串+skills.json name·零存檔·combat/formulas 用英文 i… | save-safe |
| R162 | 戰鬥動作選單瘦身:內容寬 + 無表頭收一片 + 風味備註 hover / 決策數字 chip；🔴 唯一改 index.html·零 Python·零 combat/formulas/存檔 → s… |  |
| R163 | Playwright 真瀏覽器桌面 UI 回歸硬閘門 | test-only |
| R164 | 桌面戰鬥動作選單可用性 + 首屏密度；🔴 未碰 combat/formulas/存檔 | save-safe |
| R166 | Web 互動可靠性與精準無障礙；🔴 HTTP 200 不解鎖 | save-safe |
| R167 | 本回合/故事日誌可讀性:戰果鏡入本回合(方向2)+ 戰鬥動作分類收斂(方向1)；🔴 未碰 combat/formulas/magic 數學·零存檔欄 → sim byte-iden… | save-safe |
| R168 | 任務日誌分桶重造:3→6 桶(source 顯式查表)+ 完成數措辭；🔴 加新 source 必登錄查表(test 攔) | save-safe |
| R169 | 修 R164 回歸:角色卡戰鬥技能欄散版(裸 .combat 選擇器洩漏)；🔴 view 專屬 CSS 選擇器須錨 view root(.card.combat)·勿用裸語義 … |  |
| R160c | 服務可發現性 III:世界地圖服務標記/篩選(公會徽 + 篩選高亮 + 最近 X 導航)；🔴 純前端(唯一改 index.html renderMap)·零後端/存檔/combat·payl… |  |
| R160b | 服務可發現性 II:馬廄/房產進反查通道 + 地點卡就地易讀性(城鎮專精現場可見)；🔴 純 UI/唯讀衍生·零存檔欄·未碰 combat/formulas/magic → sim by… |  |
| R160 | 名人堂 / 往昔英雄 + 成就補完(誓福按來源 / 試煉 boss / 忠誠弧 · 修 curse-rank 回歸)；🔴 純 UI/持久化·零存檔格式變更(hall.json 獨立檔·不加 Character/Game… | save-safe |
| R159 | 服務可發現性:城鎮服務/宗師目錄(codex)+ 修 R153 地圖公會大廳遮蔽回歸；🔴 純 UI/唯讀衍生·零存檔欄·未碰 combat/formulas/magic → sim by… |  |
| R158 | 存檔槽位 / 多角色:角色名冊主選單 + 遷移 + 原子寫 + 隱退存檔；🔴 存讀檔格式完全不變(R03)·不加任何存檔欄·from_dict 忽略未知鍵·sim byte-… | save-safe |
| R157 | 設定面板:字級 / 深色主題變體 / 減動態 / 操作說明；🔴 純前端·唯一改 index.html·零 Python·client-only localSto… |  |
| R156 | 戰鬥/日誌可讀性:戰鬥流水帳與敘事分離 + 選單分桶 + 屍體/本回合收束；🔴 sim byte-identical(呈現層·sim 走自有 _round·solo 秒殺 0.… |  |
| R155 | 新手清晰度批次:預設職業機制說明 + 創角衍生數值預覽 + 系統開場指路 + 種族/星座圖鑑；🔴 sim byte-identical(未碰戰鬥·首戰指路 rng 前 gated ui.mess… |  |
| R154 | 角色卡資訊補完:誓福/疾病/附魔充能/魂 token review + 修 renown 死視圖；🔴 sim byte-identical(未碰戰鬥·solo 秒殺 0.0%)·零新存檔欄·R27 … |  |
| R153 | 互動世界地圖:面板內點擊旅行 + 我的位置聚焦 + 手機縮放/滾動陷阱修復；🔴 未碰 combat/formulas/magic → sim_assassin BYTE-IDE… |  |
| R152 | 幻術「狂亂」frenzy:借刀殺人的攻擊向控場(illusion 招牌未交付)；🔴 守 rng.choice([]) IndexError)·非狂亂走既有 pick_player_… | re-sim |
| R151 | 地城 FEATURE 內容擴充:模板 6→26 + 鋪進 26 座泛用地城(依 biome 分味·依 danger 分 loot…；🔴 加特色格純改 dungeon_features.json(shrine 守安全池)+dungeo… | content |
| R150 | 修 R129 同伴戰術傾向:消費端 build-id 誤比對(招牌功能死機制)+ 游擊先點治療者；🔴 byte-identical:未碰 combat/formulas·sim 不設 compani… | save-safe |
| R149 | 元素刃三術招牌狀態:焰刃引燃/霜刃凍麻/雷刃踉蹌；🔴 rider 非 burst→不碰 solo 偷襲夾(專測 imbue 單擊夾 10<<410)/… | re-sim |
| R148 | 血族↔獵群宿仇接進 R96 敵意引擎(選邊詛咒血脈的世界後果)；🔴 加公會宿仇純改 factions.json rivals(對稱雙向) | content |
| R147 | 運動樹身份化:「調息」續戰(耗一回合換回體·主動招牌招式)；🔴 自動解除 guard_stance/shield_wall(不能持盾喘息=防無限姿態關鍵閘)·耗… | re-sim |
| R146 | 地城互動深化:第三種互動格 FEATURE(祭壇/碑文/機關)；🔴 shrine 安全池(fortify_attribute 排除 strength/fortify… | content |
| R145 | 現實邏輯審計批次 7(群 4·方案 C):板甲擋不住凝視·荊棘反彈不了弩矢；🔴 新怪:凝視/咒標 magic·投射標 ranged·戰吼=物理 | re-sim, content |
| R144 | 現實邏輯審計批次 6:世界/行為邏輯(達貢不在路上散步·巨狼真的沒穿甲)；🔴 solo 具名王必 weight:0(白名單 guard) | re-sim, content |
| R143 | 現實邏輯審計批次 5:煉金材料主題重指派(火鹽不再教你格擋)；🔴 改材料效果必跑全配對 brew-diff | content |
| R142 | 現實邏輯審計批次 4:裝備數據曲線(材質階梯不反轉) | content |
| R141 | 現實邏輯審計批次 3:戰鬥公式裝備前提 gate(裸身沒有可反震的厚甲)；🔴 護甲/持盾系 perk 一律走 _armor_tree_active | re-sim |
| R140 | 現實邏輯審計批次 2:心智控場豁免(嚇不動白骨與傀儡)；🔴 fear/calm 永不作用 mindless(單點閘·divine 唯一旁路) | re-sim, content |
| R139 | 現實邏輯審計批次 1:毒/元素抗性 rubric(無血肉之軀不可被下毒)；🔴 加不死/構造/元素怪必配毒抗(guard 自動把關) | re-sim, content |
| R138 | 重盾「掩體」:元素卸力係數 + 掩體回氣(重盾防禦端補償·遊戲內可見)+ R138b 元素次序鐵令；🔴 必<攻擊成本(test 鎖)·刻意不 gate fatigue>0(力竭喘息=脫困)③可見性:選… | re-sim |
| R137 | w1H/2H 分流:「格擋姿態」取代整回合格擋動作(續戰特化 vs 爆發特化)；🔴 姿態三件套 fatigue>0 閘整組 | re-sim |
| R125 | UI/UX 打磨批次:導航/自動趕路 + 戰鬥可讀性 + 新手清晰(Theme 1+3+4)；🔴 導航走 _quest_target_location_set+broaden long-trav… | save-safe |
| R124 | 試煉指引:門檻觸發提示 + NPC 流言指向 + codex 索引(三層·純衍生)；🔴 零 combat/formulas/magic → sim 天然不受影響·零新存檔欄(sessi… | save-safe |
| R123 | 恢復系反死靈改制:治療傷害不死(取代 R122 聖光攻擊線)；🔴 只對不死·對活物治療零傷害 → 恢復系對活人零遠程輸出(靠近戰) | re-sim, save-safe |
| R122 | 恢復系功能化:聖騎士(反死靈聖光 + 守護庇佑)完整弧 — Phase A:聖光反死靈核心；🔴 sim_assassin BYTE-IDENTICAL(隔離 HEAD worktree 空 d… | re-sim, save-safe |
| R121 | 秘術終極試煉:非戰鬥實用法術 + 念力球解謎 + 湮識(魔法核彈 + 加深秘蝕)；🔴 sim_builds 守達貢牆:arcanist(含湮識+深蝕)1% vs mehrunes_d… | re-sim |
| R120 | 秘術頂點功能化:秘蝕(arcane erosion)—— 破抗輔助頂點(削魔抗·輔助所有傷害魔法)；🔴 不 mutate boss·proof 證 dagon 施法後 resist 仍 50)計傷+a… | re-sim |
| R119 | 秘術功能化:非元素魔法傷害法術線(consistency 破抗身份)+ 里程碑支撐；🔴 sim_builds 新 make_arcanist:達貢 720 offense 牆守(arc… | re-sim |
| R114C | 經濟 QoL 批次:賣貨/倉庫/連煉/連訓/直達旅店/城區連逛(UI/UX 審計 包C)；🔴 城區連逛(唯一結構改動):game_loop _stay_district——城區服務辦完且 n… |  |
| R114 | 資訊可見性:限時增益總覽 + HUD 狀態補齊 + 任務追蹤(UI/UX 審計 包B)；🔴 增益/狀態走 _timed_buffs/_status_flags 單一資料源 |  |
| R113 | 戰鬥/地城操作流:↻ 再次 + 目標記憶 + 方向鍵(UI/UX 審計 包A)；🔴 cmem 絕不入檔 | re-sim |
| R112 | 故事日誌雙區化:上「本回合」+ 下「順時序歷史」；🔴 改日誌呈現動 render/appendJournal/journalZones/#log CS… |  |
| R111 | 地城再滋擾:重踞變體 + 清剿委託(地城重返迴圈)；🔴 第一鐵律:cleared_dungeons 恆單調不減(主線門鏈 after/until_cle… | re-sim, save |
| R110 | 家園基地化:房產 tier + 擴建(藥草園/臥房/商誼)+ legacy/成就承認；🔴 空候選 early-return 恆在 rng 消耗前)·固定預算 6 不吃 scout(守 R… | save |
| R109 | 劇情敵 NPC 化:野外狩獵 + 城內暗殺 + 謀殺目擊制(鐵律廢大廳出擊)；🔴 鐵律:action_contract(大廳出擊生成)整個移除·合約目標一律在世界裡·大廳只 _c… | re-sim, save |
| R108 | 九神騎士團聖物戒律:十字軍聖物 + Umaril 弧(KotN 正典)；🔴 sim byte-identical(隔離 worktree·sim 裝備非 requires_… | re-sim, save |
| R107 | 九神信仰:單槽限時祝福 + 德行閘 + 朝聖贖罪；🔴 repeatable 首階不可 reach〕→9 reach+2 kill 試煉→帝都):新 r… | re-sim, save |
| R106 | 召喚師深化 II:角色擴展 + 里程碑重設計 + 施法/指揮/死靈(分階段·承 R105·使用者拍板全包大里程碑·分階段子提交)；🔴 sim_assassin BYTE-IDENTICAL(刺客不召喚/不束縛·隔離 worktre… | re-sim, save |
| R105 | 召喚師深化:召喚物角色定位 + 各自行動模式 + 元素被動 + 隨召喚主成長(冷系統審計 → 使用者逐步拍板)；🔴 無嘲諷者短路不擲 rng) | re-sim, save |
| R104 | 實用/幻術魔法軸:讓魔法首次在戰鬥外有意義(魅惑/隱形/安撫/羽落/偵知)(冷系統審計 workflow → 使用者拍板方向 +…；🔴 隱形偷襲首擊仍受 SOLO_SNEAK 夾(不秒 solo·專測)·calm solo 免疫·絕… | re-sim, save |
| R103 | 徒手失衡 gated:里程碑解鎖(hand_to_hand 25)+ 輕裝武僧(不穿重甲)(承 R102·使用者點名)；🔴 byte-identical(helper 只在 hand_to_hand gate 內呼叫·w… | re-sim, save |
| R102 | 徒手技能深化:失衡(off-balance)疊層 → 徒手傷害遞增 + 兩段擊倒(使用者三拍板:方向=體力/失衡戰·機制=疊加多…；🔴 byte-identical(三 hook 全閘 hand_to_hand·sim 持匕首永不入… | re-sim, save |
| R101 | 名聲/惡名變活的社交軸(承 R100 後換叢集·使用者拍板:位移態度 + 社交+經濟)；🔴 守住:零新存檔欄·sim byte-identical(不碰 combat/formulas·s… | save |
| R100 | 玩家雙面間諜系統:臥底生涯(掩護↔價值觀漂移·殺知情者滅口·真叛變)(承 R96–R99·使用者選完整 Option C)；🔴 零戰鬥面狀態(無 *_bonus·不碰 attr/skill)+ cover_guild 絕不寫… | re-sim, save |
| R99 | 公會諜報層:臥底揭發 + 招募內線 + 反間任務 + 大廳反間服務(承 R96–R98·使用者點名三項)；🔴 cint_ 加入 action_board 排除(只走大廳·不上公開告示板) | save |
| R98 | 犯罪公會服務層:已揭露犯罪同志的會員專屬服務(承 R97·使用者拍板)；🔴 可見性閘:comrade 態度由兩路徑(犯罪 secret_guild 揭露+會員 / 公開 g… | save |
| R97 | 公會社交網:隱蔽犯罪身分 + 同會相認 + 調查揭露 + 臥底(承 R96·使用者連續拍板擴展)；🔴 零新存檔欄·衍生 char.factions/npc_disposition/dialogue_… | re-sim, save |
| R96 | 公會宿敵生態 Phase 1:派系敵意 + 對立後果(衍生·零存檔欄)(評估「派系生態活化」→ 9 公會原是孤立任務階梯 sil…；🔴 通用 NPC-公會內容規則(使用者點名通用·非限定某城):guild-標 NPC 只攜帶公會相關… | re-sim, save |
| R95 | 煉金材料正典化:生物部位移 creature loot + 2 新怪 + 野採池重建(承 R94·使用者點名「依正典重調所有材料…；🔴 brew effects 零改(只移取得端)→ 確定性 brew-diff 既有 528 對零位… | re-sim, save |
| R94 | 野採稀有度功能化:偵查定值預算 + 原料擴展(承 R93·使用者點名「依稀有度·偵查越高採稀有度越高數量越多·定值分配」+ 擴展…；🔴 brew 邏輯零改(只 ADD 材料)→ 確定性 brew-diff 證既有 528 對零位移·… | re-sim, save |
| R93 | 野外採集解耦:生態系材料池隨機抽取(動作/物品/數量三者解耦·偵查成長)(承使用者「評估」野採是否固定組合/毒藥幾型 → 拍板解…；🔴 平衡(brew 邏輯零改·只動取得端):對抗審查 3 維·9 agent·6 發現 0 defe… | save |
| R92 | 攻擊向 fortify 藥開放(力量/武器技能/潛行/毀滅)—— 依 R30「放開→必過 sim」(使用者點名「難道不該有強化力…；🔴 7 新材料與既有 26 材料零共有(全 FAIL)→ 確定性 brew-outcome diff… | re-sim, save |
| R91 | 煉金材料加厚 + 安全增益池續填(承 R90·使用者點名「先解決煉金深度」)；🔴 smithing 入紅線守門(fortify_smithing→抬 temper cap→永久過… | save |
| R90 | 煉金增益軸補完:餵飽 R30 限時增益藥引擎(純資料·8 新材料)；🔴 紅線(只靠資料缺席守·新增測試鎖死):可釀增益池絕不含 fattr_strength / fsk… | save |
| R89 | 戰士/法師公會功能化:rank-gated 招牌動詞(承 R88·完成核心公會冷階級梯三部曲)；🔴 否則 can_temper 的「缺錠」檢查會擋掉公會免費淬鍊·實作時抓到的真 bug〕·受 ef… | save |
| R88 | 斯庫瑪走私生意:整併入盜賊公會(高階解鎖·月糖精煉 sink + 跨省走私委託)；🔴 反印鈔機(設計階兩位審計獨立抓 BLOCKER→修):不加寬銷贓售價(thieves sell_… | save |
| R87 | 敵方支援施法者:敵陣治療/護盾 AI(對稱 R86)；🔴 sim 發現:敵方 rally 反效果(施法者換掉自身 ~13 攻擊·換到的 power-sca… | re-sim |
| R86 | 同伴戰鬥施法:輔助型同伴在戰鬥中各施其職(角色感知支援)；🔴 不碰 player-only 的 magic.cast):新 companion_support… | re-sim |
| R85 | 湮滅危機尾聲:英雄/叛徒的餘暉(依結局分流的傳奇收尾·純 JSON)；🔴 守 R45 紅線:無 strength/sneak/武器技能 | save |
| R84 | 犯罪/通緝系統深化:賞金獵人路途追殺(威脅)+ 亡命徒地下世界(回報)·雙軸通緝身份；🔴 防套利地板 buy=max(buy_price,fence_sell+1)>sell 比照 R3… | save |
| R83 | 出生星座深化:5 個冷星座補主動威能 + 被動天賦(完成 R61 明列「星座留後續」)；🔴 by-design 有界 note:戰士座+獸人/紅衛兩個獨立每日威能各加一道 berserk_… | re-sim, save |
| R82 | 套話/秘密 功能化(修死功能 + 撬出可行動情報)；🔴 揪出更深的死 bug:秘密存於 dialogue.json 的 npcs[id].secret … | save |
| R81 | NPC 社交叢集復活:role 身份化 + 流言線索(混合)+ 好感回報；🔴 sim_assassin BYTE-IDENTICAL(隔離 worktree vs HEAD … | save |
| R80 | 任務生態活化:委託多樣化/在地化 + NPC 一次性任務(城鎮 + 野外)；🔴 sim_assassin BYTE-IDENTICAL(隔離 worktree vs HEAD … | save |
| R79 | 常態世界脈動:動態世界新聞層 + 聚光激增可重複委託(治後期任務泉枯竭)；🔴 sim_assassin BYTE-IDENTICAL(隔離 worktree vs HEAD … | save |
| R70 | 偷襲倍率全面重構:基倍效益遞減 + 各因子下修；🔴 sim_assassin 全綠:solo 偷襲秒殺 0% ✓(降倍率更安全)·R63 追擊 0%… | re-sim |
| R69 | 反風箏:閃避效益遞減(全域)+ vanish 不躲 solo BOSS；🔴 sim_assassin 全綠:solo 偷襲秒殺 0%(evasion/vanish 不碰偷襲… | re-sim |
| R68 | 法袍三階套裝再平衡:新增「法術威力」set-bonus 機制 + 魔抗分級；🔴 sim_assassin byte-identical(刺客穿皮甲非法袍·永不施法→_power… | re-sim |
| R67 | 智力法術威力大改:int100=+30%(50→100 線性)+ >100 才 softcap(總漸近 +45%)；🔴 sim_assassin byte-identical(虎人 int≤50 且永不施法→公式零呼… | re-sim |
| R66 | resist 附魔再平衡:soul^0.7 非線性 + 魔抗/單元素分流(承魔抗免疫評估)；🔴 sim_assassin byte-identical(刺客無 resist 附魔·隔離 wor… | save |
| R171 | 四原則分工:scout(Haiku 唯讀檢索/長文摘要)/ counsel(Opus 唯讀顧問,紅線區設計取捨才找,每里程碑 ≤2)+ 作業指南 ops.md;共享工作樹禁改 git 狀態 | |

## 自動提交閘門 / 換 session 前檢查表

**提交是自動的**:驗證全綠 → `git commit` & `git push origin main`(本專案慣例,**不需使用者明說**;紅燈則不提交、先修)。推送前先過這道閘(一鍵 `/check` = `bash check.sh`):
- [ ] `python3 tests/run_all.py` 全綠(讀結尾印的模組數,勿信文件數字)
- [ ] `python3 tests/browser_ui.py` 真 Chromium 桌面 UI 回歸全綠(不可 skip)
- [ ] 觸戰鬥/施法/刺客/附魔常數 → `PYTHONPATH=. python3 sim_assassin.py`(或 `./check.sh --sim`)
- [ ] 編譯檢查通過(`check.sh` 已含完整 `py_compile`)
- [ ] `~/.tesrpg/` 是真實存檔:`check.sh`(含 `--smoke`)不碰,也不要用腳本清
- [ ] 改了規則/數量/現況 → 同步 `handoff.md`(§3 鐵律 R## / §1 現況)
- [ ] commit 訊息末加 `Co-Authored-By:` 行 → `git push origin main`

**換 session 前**(= `/sync`):全綠 + sim 穩 + 煙霧通 + 審查確認 bug 修完 + 回歸測試補完 + **handoff.md 已更新本輪里程碑**(且本輪工作已 commit & push)。

## 自動化(`.claude/` 已配置)

- `check.sh` — 單指令驗證鏈(完整 `py_compile` → `run_all.py` → Playwright/Chromium 桌面 UI 硬閘門 → 偵測到改 `formulas.py`/`combat.py` 或 `--sim` 才跑 sim 並標出 `⚠` 行 → `--smoke` 才跑煙霧,只寫暫存目錄,不碰玩家存檔)。
- `/check` slash-command = `bash check.sh`;`/sync` = 跑 `check.sh --smoke` + 印換 session 檢查表 + 提示更新 handoff.md。
- `.claude/settings.json` 已預許可唯讀測試/sim/git 指令(減少權限詢問)。`git commit`/`push` **不**預許可(刻意保留可見),但依本專案慣例驗證綠後仍自動執行(見上「自動提交閘門」/ handoff §3 R22)。

## 架構 / 重要檔案

- **資料驅動**:規則引擎在 `tesrpg/systems/*.py` + `tesrpg/formulas.py`;內容全在 `tesrpg/data/*.json`
  (races/birthsigns/classes/skills/spells/weapons/armor/recipes/bestiary/world/dungeons/quests/factions/events/origins/rulers/mastery/landmarks…)。
- **核心循環**:行動制(在地點選行動 → 推進時/日 → 觸發事件/遭遇);戰鬥是回合制子迴圈。
- 進入點/主迴圈:`tesrpg/main.py`;狀態/存檔:`tesrpg/state.py`;角色:`tesrpg/models/character.py`。
- 規則:`tesrpg/formulas.py` + `tesrpg/systems/*.py`(combat/magic/progression/mastery/smithing/vampirism/skooma/politics…)。
- UI:**Web-only** —— `tesrpg/web/`(stdlib HTTP+SSE 後端 + `static/index.html` 前端)+ `tesrpg/ui/console.py`(渲染/輸入接層:`_*_view` view-model + rich→HTML 退路 + `_web_prompt`)。平衡工具:`sim_assassin.py`;設計/交接:`DESIGN.md`、`handoff.md`。
