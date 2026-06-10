# CLAUDE.md — 流亡者 (tesrpg) 程式庫導覽

上古卷軸風格的**技能驅動沙盒文字 RPG**(終端機,Python + `rich`;另有瀏覽器 Web 版)。
單一英雄、learn-by-doing(做什麼練什麼)、跨七省探索鑽地城。

> 玩家面向的「怎麼玩」見 [README.md](README.md);完整設計見 [DESIGN.md](DESIGN.md);
> **接手開發的詳細現況/開發節奏地圖見 [handoff.md](handoff.md)(先讀它)。**

## 怎麼跑 / 測試

```bash
python3 -m tesrpg                       # 終端機版
python3 -m tesrpg.web                    # Web 版 → http://127.0.0.1:8080
python3 tests/run_all.py                 # 44 測試模組,不需 pytest,須全綠
python3 -m py_compile tesrpg/**/*.py     # 編譯檢查
PYTHONPATH=. python3 sim_assassin.py     # 平衡回歸模擬(改戰鬥常數後必跑)
```
- Python 3.12;`rich` 由系統套件提供(`python3-rich`)。⚠️ 本機**沒有 pip/pytest**、sudo 需密碼。
- 存檔在 `~/.tesrpg/save.json`(repo 外;煙霧測試後記得清)。

## 架構 / 慣例

- **資料驅動**:規則引擎在 `tesrpg/systems/*.py` + `tesrpg/formulas.py`;內容全在 `tesrpg/data/*.json`
  (races/birthsigns/classes/skills/spells/weapons/armor/armor_sets/recipes/bestiary/world/dungeons/
  quests/factions/events/origins/rulers/mastery/landmarks…)。**加一省/一把劍/一隻怪/一個里程碑多半只改 JSON。**
- **語言慣例**:程式碼、變數、資料 key 用**英文**(沿用 TES 原文術語);玩家看到的文字用**繁體中文**。
- **存檔向後相容**:`Character.to_dict/from_dict`(`cls(**d)` + dataclass 預設);新增技能走
  `progression.ensure_all_skills`、新增里程碑欄走 `ensure_mastery_choices`。
- **核心循環**:行動制(在地點選行動 → 推進時/日 → 觸發事件/遭遇);戰鬥是回合制子迴圈。
- **成長/夾限只用 `base_skill()/base_attr()`**;`skill()/attr()` 疊加裝備/吸血鬼/里程碑加成層。
- **開發節奏**(每個功能):實作 → 單元測試(`tests/test_*.py`,登錄 `run_all.py`)→ 平衡模擬 →
  無頭煙霧(`Console(file=StringIO())` + 自動選單)→ 對抗審查 workflow → 覆核修正。
- **平衡紅線**:`sim_assassin.py` 守「偷襲不可秒 solo boss」(`SOLO_SNEAK_DAMAGE_CAP_RATIO`)、
  群體規模反制(>3 敵潛匿大減)等;改戰鬥常數務必重跑。

---

## 現況快照(M0–M16 + 二十餘輪強化,全部完成、已上 GitHub)

依系統分類(里程碑歷程詳見 DESIGN.md / handoff.md):

### 角色與成長
- 10 種族 × 13 星座 × 8 職業/自訂;八屬性 + **23 技能** learn-by-doing;混合 Skyrim 式升級(等級 XP 池 → 三選一資源 + 屬性點)
- **技能里程碑 v2**:全 23 技能各 ≥1 節點,達門檻**二選一**永久銘刻 + 持久 fortify 加成層(反 min-max)
- **八職功能性身份網格**:全 8 職各一招牌戰術 loop(功能性非數值)—— 戰士盾牆(減傷·嘲諷)/法師奧術連鎖/盜賊諜報偵搜/騎士戰旗/戰法師共鳴一擊⇄法力回擊/刺客致命烙印/治療師戰地搶救/弓手獵手偵察(6 mastery 二選一節點 + 2 戰鬥動作;以技能/裝備 gate、零新存檔欄、守刺客紅線)
- **開局背景**(14 種,只給處境不給數值)+ **種子重玩性**;冒險/傳奇兩種死亡模式 + 一生傳奇總結評分

### 戰鬥與魔法
- 回合制**多敵 + 團隊戰鬥**(召喚物/傭兵同伴);**六大學派 + AoE**(召喚/秘術補完至各 7 法術,與毀滅/復原/變換同列;**召喚**=元素元身/魔人 + 束縛兵刃〔法系近戰〕+ 亡者復生〔屍起為盟〕、**秘術**=法術結界〔吸法術傷·吸魔變體〕+ 驅散 + 群體擒魂);元素抗性/弱點、狀態效果、出生星座每日之力
- **三系資源對稱**:施法也耗體力、力竭降法效(`cast_fatigue_*`),**法袍套裝**省體施法(法師的對應裝甲)
- **煉金毒藥 + 武器塗毒**;**潛行刺客系**:偷襲先機、暗殺殘響、雙持、隱遁再襲、戰前偵查;武器流派(潛襲/破甲/速度)

### 世界與探索
- **八省 64 地點 / 25 城**(賽/天/晨/黑沼澤閉合大環 + 漢默法爾/高岩/瓦倫森林/艾爾斯維爾;賽↔艾↔瓦南方大環);旅行/晝夜/危險度
- **生態遭遇**(biome 加權,八生態含 savanna 弱毒)、**省份風味事件**、**具名地標**首發現、各城**考據統治者**;終局 solo BOSS
- **格子地城探索**(`systems/dungeoncrawl.py`):10 地城程序化生成 n×n 格 × m 層,N/S/E/W 移動 + 樓梯下層 + 迷霧小地圖 + 格內怪/寶/陷阱;清末層 boss = 肅清,首領死亡自動解鎖寶藏(原子探索、零新存檔欄)

### 製作與裝備
- **鍛造**(金屬四階 + 頂級魔族/龍鱗/龍祭司,稀有素材困難取得)、**裁縫**、**淬鍊強化**;**附魔**(武器:元素傷害 + 命中觸發吸血/麻痺/再生;護甲:技能/抗性/資源;飾品:技能/屬性/抗性/資源)
- **套裝加成**(同材質四件)、武器流派、飾品槽、法杖、法袍;**具名神器**;裝備耐久 + 修理

### 公會、任務與政治
- **七大公會**:戰士/法師/盜賊 + 黑暗兄弟會 + 神話黎明 + 九神騎士團 + **戰友團**(白漫·狼人血脈歸宿,獸血儀式繫於其內圈)(技能門檻/福利/對立/分支壓軸)
- **多階段任務引擎**;犯罪賞金 + 衛兵 + 謀殺;**吸血鬼化**(力量↔詛咒天平)、**狼人化**(戰友團內圈獸血,獸形變身)、**斯庫瑪/月糖成癮**(亢奮↔戒斷天平,艾爾斯維爾)
- **領主政治 / 城戰**:謁見 → 委託 → 武士冊封;圍城 + 破城 + 收稅 + 招兵買馬;**陣營動態大事件**

### 系統與打磨
- **事件引擎**、**成就系統**、**反 min-max 經濟**(practice 成本)、**Web 版**(原生渲染、可點互動)

## 重要檔案
- 進入點/主迴圈:`tesrpg/main.py`;狀態/存檔:`tesrpg/state.py`;角色:`tesrpg/models/character.py`
- 規則:`tesrpg/formulas.py` + `tesrpg/systems/*.py`(combat/magic/progression/mastery/smithing/vampirism/skooma/politics…)
- UI:`tesrpg/ui/console.py`(rich)+ `tesrpg/web/`(Web)
- 平衡工具:`sim_assassin.py`;設計/交接:`DESIGN.md`、`handoff.md`
