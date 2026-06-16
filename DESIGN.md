# 流亡者 (The Elder Scrolls 風格文字 RPG) — 設計文件

一個上古卷軸世界觀的**單一英雄沙盒角色扮演**文字遊戲。玩家在 Tamriel 大陸創造一個冒險者,
從一無所有開始:**做什麼、就練什麼**(learn-by-doing),自由探索九大省份、鑽地城、打怪、學魔法、
加入公會、闖蕩天下。沒有固定主線逼你走,**你的技能成長軌跡就是你的故事**。

- **平台**:Python 3.11+,終端機 CLI(使用 [`rich`](https://github.com/Textualize/rich) 做角色卡/戰鬥面板/地圖選單/色彩)
- **語言慣例**:程式碼、變數、資料 key 用英文(沿用上古卷軸原文術語,如 `destruction`、`altmer`);玩家看到的文字(地名、對話、UI 標籤)用繁體中文
- **核心循環**:行動制(非即時、非回合=年)。玩家在某地點選擇行動 → 推進時間(時/日)→ 觸發事件/遭遇;戰鬥是獨立的回合制子迴圈

> 取代了原本的「王朝 (CK 風格)」設計。本作是**單一角色的一生冒險**,不是王朝繼承策略。

---

## 1. 設計目標

| 優先 | 支柱 | 為什麼是核心 |
|------|------|--------------|
| ★★★ | **技能驅動成長 (learn-by-doing)** | 上古卷軸的靈魂。你揮劍就練劍術、放火球就練毀滅、撬鎖就練安全。**沒有經驗值池,用什麼成長什麼**。等級由技能成長累積觸發,升級時依「你這段時間練了哪類技能」決定屬性加成 |
| ★★★ | **角色塑造 (種族/星座/職業)** | 種族(Mer/Men/Beast)、出生星座 (Birthsign)、職業(專精+主修技能)決定你的起點與 build 走向;屬性 + 技能 + 衍生數值構成完整角色 |
| ★★★ | **開放探索 Tamriel** | 九大省份 → 地區 → 城鎮/地城/野外的資料驅動世界圖;旅行耗時、晝夜與危險度影響遭遇;鑽地城拿戰利品 |
| ★★☆ | **戰鬥與魔法** | 回合制戰鬥(近戰/遠程/法術)、八大魔法學派、生命/魔力/體力三條資源;這是沙盒裡最常發生的互動 |
| ★☆☆ | **公會/任務/犯罪(內容層)** | 戰士/法師/盜賊/暗殺公會的入會與晉升、任務引擎、犯罪賞金系統。**用輕量資料驅動先做骨架**,後續疊內容 |

**第一個能玩的里程碑**:創一個角色,在野外/地城裡靠「做什麼練什麼」把技能練起來、升級、選屬性。
其餘世界、戰鬥、公會逐層疊加。

---

## 2. 核心資料模型

```
Character                    一個人(玩家與 NPC 共用)
  id, name, race, sex, birthsign, class_id
  attributes: {strength, intelligence, willpower, agility,
               speed, endurance, personality, luck}   # 經典 TES 八屬性,各 0–100
  skills:    {blade, destruction, sneak, ...}          # 各技能 0–100
  skill_xp:  {skill: float}                            # learn-by-doing 進度累加器,滿則 +1 點
  level, level_progress                                # 主修技能升點累積 → 觸發升級
  health, magicka, fatigue                             # 三條資源(當前值)
  # max_health/magicka/fatigue 由屬性衍生,不另存
  gold
  inventory: [ItemInstance], equipped: {weapon, helmet, cuirass, ...}
  spells: [spell_id]
  active_effects: [{effect, magnitude, duration}]      # buff/debuff/中毒/疾病
  location_id
  factions: {faction_id: rank_index}                   # 公會身份與階級
  fame, infamy, bounty                                 # 聲望 / 惡名 / 通緝賞金
  disposition: int                                     # NPC 對玩家好感(NPC 才用)
  is_player: bool                                       # 玩家當前角色(每局唯一)

Race          data/races.json
  id, name, kind(MER/MEN/BEAST)
  attribute_mods, skill_bonuses, powers[](主動)/abilities[](被動)
  resistances{} 例:dunmer 抗火 75%、nord 抗寒
Birthsign     data/birthsigns.json   出生星座
  id, name, passive_effects[] / granted_spells[]   例:戰士、法師、竊賊、學徒、巨魔像…
Class         data/classes.json
  id, name, specialization(COMBAT/MAGIC/STEALTH)
  favored_attributes[2], major_skills[5..7]          # 主修技能 → 計入升級
SkillDef      data/skills.json
  id, name, specialization, governing_attribute       # 主導屬性影響升級加成
  use_xp(各種「使用」動作給多少 xp)
ItemDef       data/items/*.json   (ItemInstance = def_id + condition + enchant + qty)
  id, name, type(WEAPON/ARMOR/POTION/INGREDIENT/BOOK/MISC)
  weapon{damage, speed, reach, skill}  armor{rating, slot, weight_class}
  value, weight, enchantment_id?
Spell         data/spells.json
  id, name, school, magicka_cost, effects[{type, magnitude, area, duration}]
Region/Loc    data/world/*.json
  Region: id, name, province, climate, danger, connected_regions[]
  Location: id, name, type(CITY/TOWN/DUNGEON/WILDERNESS), region_id
            services[](inn/shop/trainer/guild), npc_ids[], encounter_table, areas[](地城房間)
Creature      data/bestiary.json   (怪物/野生 NPC 模板)
  id, name, attributes/skills, attacks[], loot_table, soul_level(供附魔)
Quest         data/quests/*.json
  id, name, giver, faction?, stages[], objectives[], rewards{}
Faction       data/factions.json   公會
  id, name, ranks[], join_req, advancement(各階:技能門檻 + 任務)
```

設計原則:**資料驅動**。種族、星座、技能、物品、法術、世界、怪物、任務全放 `data/` 的 JSON,
程式只負責規則引擎。新增一個省份、一把劍、一隻怪、一個公會,**不必改邏輯**。

---

## 3. 系統設計

### 3.1 技能成長 (Skill Progression) — learn-by-doing,本作靈魂 ★
- **技能成長 = learn-by-doing(不變)**:每次「使用」一個技能就給該技能 `skill_xp`(揮劍命中 → blade、施法成功 → 對應學派、撬開鎖 → security、討價還價 → mercantile…);xp 滿門檻 → 該技能 **+1 點**,門檻**隨技能等級遞增**。
- **升級 = 混合 Skyrim 式(M15 改版)**:每次技能 +1 都餵養「**等級 XP 池** `level_xp`」,**所有技能都計入**(主修 ×1.5,保留職業認同);`level_xp` 達 `levelup_xp_threshold(level)=12+(level-1)` → **可升級**。
- **升級給予**:① 生命/魔力/體力**三選一** +固定值(累積進 `resource_levels`);② **`LEVELUP_ATTRIBUTE_POINTS`(=4)點屬性點自由分配**(含 Luck),**無倍率**。升級回滿三資源。
- **衍生數值**:`max_health = 創建耐力×2 + resource_levels[health]`(**不隨耐力逐級長**)、`max_magicka = 智力×2 + 種族/星座 + resource_levels[magicka]`、`max_fatigue = 力+意+敏+耐 + resource_levels[fatigue]`(均再疊加護甲 fortify)、負重上限 = f(strength)。
- **改版動機**:舊 Oblivion 式(主修觸發升級 + 練功倍率)有兩個量化驗證過的結構缺陷 —— **屬性倍率 min-max**(囤非主修升點換 +5/+5/+5)與**耐力時機陷阱**(早衝耐力多賺終身血)。混合制把「升級觸發 / 屬性成長 / 血量成長」全部解耦點數化,一次消除兩者,並讓 Luck 可投資。
- 訓練師(城鎮服務)可付錢直接練技能(技能升點同樣餵 `level_xp`),作為 learn-by-doing 的補充。

### 3.2 角色塑造與創建 (Character Creation)
- 流程:**姓名/性別 → 種族 → 出生星座 → 職業**
- **種族**(10 種):Altmer/Bosmer/Dunmer(Mer)、Nord/Imperial/Breton/Redguard(Men)、Orsimer(Orc)、Argonian/Khajiit(Beast)。各有屬性修正、技能加成、種族能力(如 Argonian 抗病/水下呼吸、Khajiit 夜視、Breton 抗魔)
- **出生星座**(13 個):戰士/法師/竊賊三大守護星 + 學徒/巨魔像/淑女/駿馬/領主/戀人/陰影/儀式/蛇 等,給被動加成或每日可用法術
- **職業**:預設職業(戰士、法師、盜賊、聖騎士、刺客、巫師…)**或自訂**(選專精 + 2 個偏好屬性 + 5–7 個主修技能)。主修技能=升級計分的技能 → 引導 build
- 起點:玩家以「一個剛抵達 Tamriel 某城的無名冒險者」開局(起始省份見開放問題)

### 3.3 戰鬥 (Combat) — 回合制子迴圈
- 進入戰鬥 → 雙方依 `speed`/`agility` 排行動序;玩家每回合選:**攻擊 / 施法 / 格擋 / 用道具 / 嘗試逃跑**
- **命中**:f(攻擊方武器技能 + agility + 命中加成 − 防守方迴避/格擋 − 疲勞懲罰);**傷害**:f(武器基礎 × strength × 技能 × 隨機),扣護甲減傷(armor rating + 對應 armor 技能)
- **資源**:近戰耗 `fatigue`(疲勞低 → 命中/傷害大降)、法術耗 `magicka`(費用隨學派技能下降)
- **怪物 AI**:簡單啟發式(血低逃跑、優先補/控、近戰逼近)。資料來自 `bestiary.json`
- **死亡**:玩家 health 歸零 = 倒下(依設定:讀檔重來 / 永久死亡結算一生 — 見開放問題);擊殺給戰利品 + 技能 xp

### 3.4 魔法、煉金與附魔 (Magic / Alchemy / Enchant)
- **八大學派**:Destruction、Restoration、Alteration、Illusion、Conjuration、Mysticism、(+ Alchemy、Enchant 作為技能)
- 施法成功率/費用隨學派技能改善;法術效果走統一 `effects` 結構(傷害/治療/變形/召喚/隱身/開鎖…)
- **煉金 (Alchemy)**:採集材料(ingredient)→ 組合 → 依技能與材料共有效果產出藥水;**效果靠試驗/技能逐步揭露**(吃材料試出第一個效果)。產出涵蓋即時回復(回血/魔/體)、**限時增益(強化屬性/技能 + 抗元素;深化 Phase 1 / R30,走獨立 `potion_*` 層)**、與有害毒劑(塗武器,見 M9)
- **附魔 (Enchant)**:用充能靈魂石把效果附到裝備;武器/防具走 condition(耐久)系統,需 Armorer 技能修理

### 3.5 世界與探索 (World & Exploration)
- 世界 = **地區圖(graph)**,非像素地圖:Region 之間 `connected_regions` 連通,旅行耗時(受 speed/坐騎/天氣)
- **時間系統**:TES 曆法(一年 12 月、每日 24 時)。行動推進時/日;**晝夜**影響遭遇與 NPC 作息;**休息**回復資源 + 推進時間(野外休息有風險遭遇)
- **地點類型**:城市/城鎮(服務:旅店、商店、訓練師、公會分部)、地城(多房間 areas、陷阱、上鎖容器、Boss、固定+隨機戰利品)、野外(隨機遭遇表)
- **遭遇**:依地區 `danger`、晝夜、玩家等級抽 `encounter_table`(戰鬥/事件/發現地點)
  - ✅ **生態遭遇表已實作**(細化省分):每地點有 `biome`(heartland/snow/ashland/swamp),野外遭遇依 biome 加權分流(雪原噴霜系/火山噴灰系/沼澤噴蜥蜴鬼火/腹地帝國亡魂+米諾陶),通用怪四海皆有墊底;事件 `trigger.provinces` 與告示板 `provinces` 讓風味/懸賞在地化;NPC `rumor` 指路、在地多階段任務鏈。重數值怪靠 `danger` 門檻擋在和緩起手區外(min_level+danger 雙閘,不數值縮放)。
  - ✅ **各省城市補全**(按 TES 正史):賽羅迪爾(帝都/史金格拉德/切迪納/安維爾…)、天際(白漫/風盔/裂谷/馬卡斯)、晨風(維威克/巴爾莫拉/奧德盧恩)、黑沼澤(赫爾斯壯/黑荊棘)各有多座考據城市,共 36 地點 / 17 城 / 21 城主;城市=danger-0 安全樞紐,跨省=白隘等快線(險)vs 城躍(安全但 ~2.3× 耗時)的取捨。

### 3.6 經濟與物品 (Economy & Inventory)
- **負重 (encumbrance)**:物品有重量,上限由 strength 決定;超重影響移動/戰鬥
- **交易**:買賣價受 Mercantile + Personality + NPC disposition 影響;商店有金幣上限與庫存
- **裝備槽**:武器 + 各防具部位;condition 下降 → 效能降,Armorer 修理
- 戰利品、寶箱、屍體搜刮、偷竊(觸發犯罪)

### 3.7 公會、任務與聲望 (Factions / Quests / Crime) — 內容層,先做骨架
- **公會**:戰士/法師/盜賊/暗殺等,入會有條件,晉升需**技能門檻 + 完成晉升任務**;階級給稱號、薪俸、設施權限
  - ✅ **四會已做**:戰士/法師/盜賊(技能門檻 + 福利/俸祿 + 對立 + 分支壓軸)+ **黑暗兄弟會**(里程碑:不走大廳報名,改「謀殺無辜→血債→夢中招募」入會;6 張暗殺合約沿階級晉升;夜母祝福潛殺加成;五戒/淨化背叛分支;洗白賞金 perk)。
- **任務引擎**:Quest = JSON(stages、objectives、branch、rewards);任務 log 追蹤;支線/公會線/委託
- **犯罪與賞金**:偷竊/襲擊/殺人 → 該地區 `bounty` 上升;衛兵察覺 → 繳清/坐牢/抵抗/逃亡;**沙盒自由的一部分**
  - ✅ **殺人已實作**(隨黑暗兄弟會補上):攀談選單可暗殺城民 → 高額賞金 + 惡名 + 引來兄弟會招募。
- **NPC 與對話**:disposition 系統(Personality + Speechcraft + 種族關係 + 賄賂);對話提供服務、傳聞、任務鉤子

### 3.8 事件引擎 (Event Engine) — 輕量但貫穿
- 事件 = JSON:`{ trigger 條件, weight, 文字, options[{文字, requirements, effects}] }`
- 旅行/休息/進地點時抽符合條件的事件;選項產生效果(改技能 xp / 物品 / 聲望 / 觸發任務或戰鬥)
- 這是把所有系統「講成故事」的載體,也是未來塞劇情/隨機奇遇的擴充點

---

## 4. 專案結構

```
SLG/
├── README.md
├── DESIGN.md                  # 本文件
├── pyproject.toml             # 依賴: rich, (pytest)
├── tesrpg/
│   ├── main.py                # 進入點 + 主行動迴圈
│   ├── rng.py                 # 可重現的 seeded 隨機
│   ├── state.py               # GameState(世界資料 + save/load JSON)
│   ├── creation.py            # 角色創建流程(種族/星座/職業)
│   ├── models/                # character / item / spell / location / creature / quest / faction
│   ├── systems/               # progression(★ learn-by-doing) / combat / magic / alchemy /
│   │                          #   world_time / exploration / economy / crime / faction / events
│   ├── data/                  # races / birthsigns / classes / skills / spells / factions /
│   │                          #   items/*.json / bestiary.json / world/*.json / quests/*.json /
│   │                          #   events/*.json / names.json
│   └── ui/console.py          # rich 渲染(角色卡、戰鬥面板、地圖/旅行選單、物品欄、對話)
└── tests/                     # 技能升點、升級加成、戰鬥結算、負重、存讀檔的單元測試
```

---

## 5. 開發里程碑(垂直切片,每個里程碑都「可玩」)

> **狀態:M0–M6 全部完成且可玩。** 8 個測試模組綠燈;每個里程碑收尾時跑過對抗式審查(workflow)。
> 程式 ~26 模組、資料 17 個 JSON。實作與設計的對照見各里程碑 ✅。

### ✅ M0 — 骨架(可跑)
專案結構、`GameState`、seeded RNG、主行動迴圈、`rich` UI 殼、JSON 存讀檔。
能顯示角色卡、選一個行動推進時間。

### ✅ M1 — 角色 + 技能核心(遊戲的靈魂)★
角色創建(種族/星座/職業)、八屬性、衍生數值;**learn-by-doing 引擎**(用技能 → xp → 升點 → 主修累積 → 升級選屬性)。
即使只在一個練功場反覆做動作,也能完整體驗「做什麼練什麼 → 升級」的成長閉環。

### ✅ M2 — 戰鬥與生存
回合制戰鬥(近戰/遠程/逃跑)、生命/魔力/體力、死亡處理、休息回復、基礎 `bestiary`。
能打怪、靠戰鬥練技能、受傷、恢復。

### ✅ M3 — 世界與探索
地區圖 + 地點 + 旅行耗時、地城房間、遭遇表、戰利品、物品欄與負重。
能在 Tamriel 上旅行、鑽地城、撿裝備。

### ✅ M4 — 魔法與製作
六大學派與法術(毀滅無視護甲、召喚盟友、護盾/恐懼/擒魂)、煉金、附魔、武器/防具 condition 與 Armorer 修理。
能當法師打、煉藥、附魔、修裝。

### ✅ M5 — 公會、任務與犯罪
三大公會入會/晉升、任務引擎(四類目標自動結算)、犯罪賞金、衛兵盤查、disposition 對話。
能接任務、加入公會往上爬、當小偷被通緝。

### ✅ M6 — 打磨與內容
擴充省份(賽羅迪爾 + 天際 + 晨風,12 地點 3 地城)、物品/怪物/法術/任務、公會三階晉升、平衡曲線、
**一生傳奇總結畫面**(走過的地方、最高技能、聲望、公會階級、擊殺 → 傳奇評分與稱號,給重玩動力)。

---

## 6. 第一版範圍界線(避免做太大)
- **無像素地圖、無格子戰鬥** → 地區圖 + 抽象回合戰鬥(無走位)
- **無即時制** → 行動推進時/日
- 宗教(九聖/魔神)、文化先做成「標籤」影響 disposition/事件,不做完整機制
- **單一角色**,無隊伍(召喚物/同伴可後續加);怪物 AI 用簡單啟發式
- 內容廣度先求骨架可玩:**九省份先做 1–2 個省份的少量地點**,其餘靠資料逐步補
- 多人、圖形、音效 → 不在範圍

---

## 7. 開放問題 — 已定案
- **死亡規則** → **兩種模式都做**,開局選擇:**冒險模式**(死亡可讀檔重來)/ **傳奇模式**(roguelike 永久死亡,死後抹除存檔)。兩者死亡/隱退都呈現一生傳奇總結。
- **職業** → **預設 8 種 + 自訂**(選專精 / 2 偏好屬性 / 7 主修技能)。創角問答暫未做。
- **起始省份** → **賽羅迪爾·布魯瑪**開局;已延伸至天際、晨風(可旅行往返)。
- **主線 vs 純沙盒** → **純沙盒**:靠公會線、告示板委託、NPC 委託自行串;暫不做主線。
- **時間顆粒度** → 行動以「**小時**」推進(休息/旅行可跨日),曆法 12 月 × 30 天。
- **技能數量** → 原設計採 **Oblivion 的 21 技能**(7 戰鬥 / 7 魔法 / 7 潛行,對應 7 屬性,Luck 不轄技能);後續經拍板**新增 `scout`(偵查,潛行系)與 `smithing`(鍛造)**,突破原上限以支撐「戰前偵查」與「鍛造」循環 → **現為 23**(當前數以 `len(gamedata.skills)` / `data/skills.json` 為準,別信此處字面)。新增技能需同步 `progression.ensure_all_skills` 做舊存檔遷移。
- **一生評分** → 已實作公式(`systems/legacy.py`):等級 × 120 + 前五技能和 × 2 + 任務 × 50 + 公會階級積點 + 地城 × 90 + 足跡 × 20 + 擊殺 × 4 + 聲望 × 6 + 金幣 × 0.1 + 在世年數 × 30 → 換算稱號。

## 8. 之後可擴充(非當前範圍)
- ✅ ~~事件引擎(3.8)~~ **已於 M7 實作**:`data/events.json`(15 事件)+ `systems/events.py`,在旅行/休息/探索/抵達依情境權重抽事件,選項含技能判定與需求閘門,效果複用既有系統(金幣/物品/技能/聲望/賞金/任務/戰鬥)。
- ✅ **戰鬥戰術縱深(M8)**:元素抗性/弱點(`systems/formulas.resist_multiplier`,種族+怪物 resist)、狀態效果(DoT/麻痺/再生,`magic.tick_effects`)、出生星座每日能力(`systems/powers.py`)。讓元素、種族、星座在戰鬥中真正有差別。
- ✅ **煉金毒藥與武器塗毒(M9)**:有害材料共通效果 → 毒藥(`alchemy.brew` 分流、`synth` 的 `psn|` 物品),`inventory.coat_weapon` 把毒塗上武器,命中即施加 DoT/麻痺狀態(吃毒素抗性)。潛行/煉金流派的戰術回報。
- ✅ **多階段任務 + 公會精英任務線(M10)**:`quests.py` 支援 `stages`(逐階段目標),三大公會補齊晉升任務線一路登頂(會長/首席法師/大師竊賊),壓軸任務為多階段劇情線。
- ✅ **介面打磨(M11)**:資料驅動的 Tamriel 世界地圖(`ui.world_map`,行省樹狀總覽 + 路線耗時)、hub 主選單分組(`ui.grouped_menu`,五大分類連續編號)。
- ✅ **多敵 + 團隊戰鬥(M12)**:`run_battle` 重寫為階段制群戰(玩家+同伴 vs 多敵),`resolve_attack` 通用於所有戰鬥單位;召喚物為真實我方單位、旅店可雇用傭兵同伴(`companions.json`,`Character.companions`)。群戰危險、隊伍是解法。
  - 第一版的「單一角色、無隊伍」範圍界線(第 6 節)至此放寬:加入了同伴/召喚物隊伍。
- ✅ **AoE 法術(M13)**:`magic.cast` 新增 `damage_all`/`status_all`/`damage_status_all`(逐敵吃抗性、狀態各自獨立),群戰中法師清群的解法。
- ✅ **第八省艾爾斯維爾 + 斯庫瑪/月糖成癮(里程碑)**:savanna 弱毒生態軸(首個 poison 弱點省 → 回饋塗毒/煉金刺客)、賽↔艾↔瓦南方大環(純資料);斯庫瑪/月糖 power↔curse 成癮天平(限時亢奮↔成癮戒斷,仿吸血鬼,`systems/skooma.py`;亢奮刻意不碰力量/潛行以守刺客紅線)。詳見 handoff.md §1。
- 更多省份地點、生物、裝備、法術、公會更高階任務線(資料驅動,加 JSON 即可)。
- 同伴/隊伍、坐騎、房產、附魔護甲效果(目前只做武器附魔)、煉金毒劑塗武器。
- 創角問答推職業、主線劇情、宗教(九聖/魔神)完整機制。

