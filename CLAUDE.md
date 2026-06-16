# CLAUDE.md — 流亡者 (tesrpg) 開發憲法

上古卷軸風格的**技能驅動沙盒文字 RPG**(**瀏覽器 Web 版**;Python 後端,`rich` 把畫面渲成 HTML)。
單一英雄、learn-by-doing(做什麼練什麼)、跨八省探索鑽地城。
> ⚠ **本專案已 Web-only**:終端機版(`python3 -m tesrpg`)已移除;`tesrpg/ui/console.py` 現為 Web 的渲染/輸入接層(rich→HTML view-model + `_web_prompt`),5 個輸入原語在無 web backend 時直接 raise。

> **本檔是給 Claude 的開發憲法**:每次改動都適用的節奏 + 跨領域紅線 + 提交檢查表 + 子系統鐵律「索引」。
> 子系統鐵律**本體**在 [handoff.md](handoff.md) §3(以 `R##` 標號);完整現況清單見 handoff §1;設計理念見 [DESIGN.md](DESIGN.md);玩家「怎麼玩」見 [README.md](README.md);**全增益效果目錄(含實際數值/疊加規則)見 [BUFFS.md](BUFFS.md)**(改增益常數順手更新)。

## 怎麼跑 / 測試

```bash
python3 -m tesrpg.web                     # Web 版(唯一進入點)→ http://127.0.0.1:8080
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
   - c. 無頭煙霧:WebBackend 自動作答驅動 `main()`(或 patch `ui.menu`/`Console(file=StringIO())`)抓 traceback
   - d. 對抗審查(Workflow):多維 fan-out → 獨立懷疑者**對抗式驗證**,只留能真實重現的
   - e. 覆核+修正:逐一覆核(有誤報、也有「會引入新 bug 的錯誤修法」)→ 補回歸測試 → 重跑全套
5. **修改文件 + 提交推送**:同步 `handoff.md`(§1 現況 / §3 鐵律 R##)與必要的 `CLAUDE.md` → **驗證綠即自動 `git commit` & `git push origin main`(本專案慣例,見 handoff §3 R22;不需明說。紅燈則不提交、先修)**。

## 鐵律總則(跨領域紅線,全文)

- **成長/夾限只用 `base_skill()/base_attr()`**;裝備/吸血鬼/斯庫瑪/狼人/里程碑/**達貢之力**加成走獨立疊加層,**絕不寫回 base**。
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
| R18 | `apply_origin` **只改處境不動屬性/技能**;別起在地城/`danger≥4`;開局 `quest` 欄自動接起手任務(`is_player` 閘);起手任務 `reach` 不指自身起始地、`collect` 不取起始包物、禁 `clear_dungeon` | |
| R19 | `vampirism.update` 每圈頂端;`vampire_*` 獨立層;疾病抗性削感染 | migrate, recompute |
| R20 | `skooma.update` 在 vampirism 後;亢奮**絕不碰 strength/sneak/武傷** | re-sim, migrate |
| R21 | 門檻只認 `base_skill()`;新 kind 三步登錄(`_IMPLEMENTED_KINDS`+getter+呼叫端);溢盾夾總量 cap | re-sim, migrate |
| R23 | 對話條件複用 `events.meets`(無 state 鍵就地加、需 state 走 `meets_dialogue`);hostile=拒談 `topics_for` 回 `[]`;帶持久 effect 話題必標 `once`(`dialogue_done` 去重防零成本刷分);`faction_standing` 互斥+表態一次性 | save |
| R24 | AI 戰爭 `aiwar.update` 在 worldstate 後/tick_tax 前;決定性 `rng`+`sorted`(迭代序不餵 rng);玩家城只削 garrison 不寫 world_faction(三層免疫);改常數必跑 `sim_worldwar`(防雪球**含玩家選邊**、霸權煞車在外交後套) | re-sim, save |
| R25 | 房產 `house_stash` 不計負重(存穿戴擋免漏 recompute);精神飽滿 `well_rested` 快取只乘 xp 不寫 base;坐騎鞍袋走 `max_weight(char,gd)` 非資源不 recompute;衝鋒不走 `sneak_mult`、受獨立 `MOUNTED_CHARGE_DAMAGE_CAP_RATIO` 夾;戰技僅 `mounted` 旗(野外)+ 第一回合;spear archetype 落安全預設 → 改 combat/formulas 必跑 `sim_assassin` | re-sim, recompute, save |
| R26 | 湮滅危機主線=`source:"main"` + `requires_event`/`requires_faction` gate(`available_quests`)+ `expel_faction` 叛離(`accept_quest`);雙結局都打達貢(滿血 `the_deadlands` vs 削弱 `dawn_sanctum`),用 `kills` milestone 互斥、都 `eradicate_faction` 神話黎明(`<fac>_eradicated` 旗標擋再入會);達貢之力=永久獨立層 `dagon_boon.py`(照吸血鬼);**獨立戰爭=危機後第二幕**(`aiwar`+分裂事件 gate 在 `oblivion_crisis_ended`)→ 改 aiwar 必跑 `sim_worldwar`、加永久屬性層/solo boss 必跑 `sim_assassin` | re-sim, recompute, save |
| R27 | **Web-only**:唯一進入點 `python3 -m tesrpg.web`(終端 `__main__.py` 已刪);`console.py` 是 web 渲染/輸入接層(rich→HTML 退路**不可刪**+ `_xxx_view` 原生 view);5 輸入原語無 backend 即 `raise`,**不可重引入終端 stdin/`IntPrompt`**;測試 patch `ui.*` 或用 `WebBackend` 驅動 | |
| R28 | `pos` 座標與 `links` 連線**皆依正典 TES 地理**(UESP;`world["map"]`40×24,省內 lore 鄰接、跨省**只**經邊境、時數由格距離推導,不入檔);無非預期死路、省內子圖連通、危險度分級(`test_world` 守);加城→rulers+跑 `sim_worldwar`,加地城→dungeons+`clear_dungeon` 委託(`test_polish`/`test_detailing` 守);重建工具 `tools/geo_rebuild.py`(GEO/BORDER_LINKS) | re-sim, save |
| R29 | 城鎮服務專精化:訓練師可教技 = `trainers.json`「skills」覆寫→公會推導系(`world._GUILD_SPEC`)→全技後備,再 ∪ 招牌「master」技;宗師破 `TRAINER_CAP=75`(`≤SKILL_CAP`)、`TRAINER_CAP` 唯一數值旋鈕、不動戰鬥**免 sim**;法師公會法術**每省守一學派 + 保底集 9 道**(純改 `world.json spell_stock`,`imperial_city` 通才,無孤兒);零存檔欄位(`test_world` 守) | |
| R30 | 煉金限時增益藥水:`brew` 出強化屬性/技能/抗元素**限時**藥(`synth brewb`);效果 kind **參數內嵌**(`fattr_*`/`fskill_*`/`resist_*`)→ 共有偵測天然要求同參數;走獨立 `potion_*` 層(`potion_buffs` 權威 + 快取,聚合 attr/skill/entity_resist、**絕不寫 base**),`potion_buff.update` 掛 game_loop(skooma 後)、`ensure_potion_fields` 接載入剔過期;疊加**同(kind,param)取最強+取較晚到期非相加**;`use_item` 加 `state`;可釀池**排除 strength+武器技能 → 免 sim**(放開則必跑 `sim_assassin`) | recompute, save |
| R31 | 毒劑深化:五毒型(DoT/麻痺基礎 + **衰毒 weaken**·**遲緩 slow**〔唯一新 combat kind:降 `_speed`+命中〕·**懼毒 fear**);**修塗毒命中路徑 solo 控制免疫缺口**(paralyze/fear 守 `_is_solo`+去重、charge 接觸即耗);brew 優先序 麻痺>懼>遲>衰>DoT,特殊毒型需 `mastery.poison_unlocks` 解鎖否則退回 DoT(特殊材料皆兼具 damage_health);里程碑 `poison_unlock` kind(R21 三步,**保留 opt_id** toxin_master/potent_poison/venom_lord 改功能解鎖);塗層次數依毒型(控制半量);無新存檔欄 → **改 combat/formulas/alchemy 必跑 `sim_assassin`** | re-sim, save |
| R32 | 煉金效果逐步揭露:材料效果預設 `???`,三源揭露(嚐一口 `taste` 決定性消耗 / 煉製成功 `brew` 回 `learn` 鍵由呼叫端 `reveal` / 技能被動 `passive_reveal` 揭露前 `1+base_skill//25` 個);**純資訊層、brew 數學不變**;通用於任何 kind(自動涵蓋 R30/R31);`known_effects`(ing→[kind])存檔欄 + `ensure_known_effects` 防呆/清陳舊;UI 走 `ui.menu/message`(R27 安全);無戰鬥改動 → 免 sim | save |
| R33 | **裝備耐久/修理整套移除**(Skyrim 式;純雜務稅→零決策):刪 `weapon_condition`/`armor_condition`+折損+`_cond_mult`+三修理路徑+`repair_hammer`+`repair_fee`+ mastery `repair_floor`/`combat_repair`;**「armorer」服務(鐵匠站)≠ 技能**——技能 armorer 整條刪(+4 里程碑節點),服務保留(閘 craft/temper/meltdown,不動 world.json/`_SERVICE_CN`);`effective_armor_rating`併入`worn_armor_rating`、`_armor_display`單值;`smithing_50` 換 `thrifty_forge`+`smith_arm`、`forgemaster`→heavy_armor;戰士公會 `repair_discount`→`armory_discount`(`buy_price` 對 `damage`/`armor_rating` 物品折扣,cap 0.35 非免費守不套利);warrior/archer 主修 + nord/orsimer 種族 armorer→smithing/athletics;`from_dict` 剝舊欄+armorer 鍵、`ensure_mastery_choices` 自動剔陳舊選擇;**動 combat → 必跑 `sim_assassin`** | re-sim, save |

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
- UI:**Web-only** —— `tesrpg/web/`(stdlib HTTP+SSE 後端 + `static/index.html` 前端)+ `tesrpg/ui/console.py`(渲染/輸入接層:`_*_view` view-model + rich→HTML 退路 + `_web_prompt`)。平衡工具:`sim_assassin.py`;設計/交接:`DESIGN.md`、`handoff.md`。
