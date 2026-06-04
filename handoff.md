# Handoff — 流亡者 (tesrpg)

上古卷軸風格的**技能驅動沙盒文字 RPG**(終端機,Python + `rich`)。單一英雄:做什麼練什麼、
跨三省探索鑽地城、戰士/法師/盜賊三系玩法,直到陣亡或隱退結算一生傳奇。

> 給接手的 session:這份文件是「立刻能接著做」的地圖。先讀「現況」「怎麼跑」「開發節奏」三節即可上手。

---

## 0. 環境 / 怎麼跑

- **工作目錄**:`/home/fischer/SLG`
- **GitHub**:`git@github.com:Fischer-Zhang/elder-scrolls-textrpg.git`(分支 `main`,SSH 已認證為 Fischer-Zhang)
- **Python 3.12**;`rich` 由**系統套件**提供(`python3-rich`)—— ⚠️ **本機沒有 `pip`、沒有 `pytest`、sudo 需密碼**。
- **執行遊戲**:`python3 -m tesrpg`
- **跑測試**:`python3 tests/run_all.py`(不需 pytest;20 個測試模組,目前**全綠**)
- **編譯檢查**:`python3 -m py_compile tesrpg/**/*.py tesrpg/*.py tests/*.py`
- 存檔在 `~/.tesrpg/save.json`(在 repo 外;測試/煙霧測試後記得 `rm -f ~/.tesrpg/save.json`)

---

## 1. 現況:M1–M16 + 多輪戰鬥/內容強化,全部完成、已上 GitHub

| 里程碑 | 內容 |
|---|---|
| M1 | 角色創建(10 種族 × 13 星座 × 8 職業+自訂)、八屬性、**21 技能 learn-by-doing**、升級選屬性 |
| M2 | 回合制戰鬥、生命/魔力/體力、死亡、休息 |
| M3 | Tamriel 地區圖、旅行耗時、地城、物品/背包/負重/裝備、戰利品 |
| M4 | 六大魔法學派、煉金、附魔、裝備耐久 + Armorer 修理 |
| M5 | 三大公會、任務引擎、犯罪賞金 + 衛兵、NPC 好感對話 |
| M6 | 一生傳奇總結與評分、**冒險/傳奇兩種死亡模式**、內容擴充(晨風省) |
| M7 | **事件引擎**(旅行/休息/探索/抵達的隨機奇遇) |
| M8 | **元素抗性/弱點**(啟用種族+怪物 resist)、狀態效果(DoT/麻痺/再生)、**出生星座每日能力** |
| M9 | **煉金毒藥 + 武器塗毒** |
| M10 | **多階段任務引擎** + 公會精英任務線(可登頂掌門) |
| M11 | 世界地圖 UI + hub 選單分組 |
| M12 | **多敵 + 團隊戰鬥**(召喚物/傭兵同伴) |
| M13 | **AoE 法術**(全體傷害/狀態,逐敵吃抗性) |
| M14 | **護甲附魔**(`armor_fortify`:穿戴強化生命/魔力/體力,`base_max_health` 基底層 + 向後相容遷移) |
| M15 | **升級系統改版**(混合 Skyrim 式:技能 learn-by-doing 餵「等級 XP 池」→ 升級給三選一資源 + 屬性點自由分配;移除 Oblivion 倍率 → 消滅 min-max 與耐力時機陷阱) |
| M16 | **潛行系戰鬥化**:`sneak`→開場偷襲(依潛行加傷、命中下限、戰鬥中可練)、`acrobatics`→閃避(降敵命中、閃避時成長) |
| UI  | 介面改版:強化視覺識別(金色框線/雙線英雄面板)、hub 選單多欄收斂 + 合併重複入口 + 精簡標籤 |

**M16 後續(數輪 ultracode-off 直作,技能健檢 → 三系平衡 → 內容難度)**:
- **運動 athletics 雙用途**:旅行加速(`athletics_travel_factor`)+ 降低戰鬥體力消耗(`fatigue_cost_factor`)——原為死技能。
- **格擋體力成本接上**(`BLOCK_FATIGUE_COST` 原是死常數);**技能健檢**:21 技能現皆有實際機制效果。
- **內容難度 B**:bestiary 加 7 隻高階 elite(`min_level` 6→16、抗性各異 → build 剋制);危險區群戰隨 `danger` 放大;
  **BOSS 級標 `"solo"` 一次只單獨出現**;新終局地城**龍喉巢穴**(elite 房間 + 上古巨龍 boss)+ 新地點**龍喉峰**(晨風,danger 5);
  地城首領支援 `"raw"`(已是 elite 不再被 `spawn_boss` ×1.6 疊加);灰燼墓塚首領升級為 `dremora_lord`。

**擴張玩法(評估後直作:世界拓樸 + 種子)**:
- **世界拓樸改造**:原本 13 地點是一條**走廊**(無環、地城全是 degree-1 盲腸),與 ★★★「開放探索」支柱名實不符。
  純改 `world.json` 加 4 條雙向邊:① 跨省替代路線**凱瓦奇↔龍橋鎮**(繞西境 13 時/danger 1 的「慢但安全」,對照白隘 7 時/danger 2 的「快但險」);
  ② 三條讓地城變「環上節點」的後門(切德納寇↔凱瓦奇、冰風廢墟↔海芬古、灰燼墓塚↔莫拉格瑪)→ 地城可從兩側進出、清完不必原路折返。
  全圖仍連通;終局**龍喉峰**刻意保留 degree-1 高潮死路。**不動邏輯**(`world.travel` 本就讀任意 `links`)。
- **種子開放給玩家(重玩性)**:`rng.make_seed(text)`(空白=隨機但可知整數、純數字直用、文字走 `zlib.crc32` 穩定雜湊);
  新遊戲入口輸入種子 → 創角與遊戲 RNG 同種子 → **同種子+同選擇=同世界同命運**;一生傳奇總結顯示種子(可分享「種子→分數」)。

**公會深度化(評估後直作:修正「公會太扁平」,四層全做)**:原本公會=純稱號(入會零門檻、晉升只靠單一任務、階級無回報、三會互不相干)。
- **L1 入會/晉升技能門檻**(落實 DESIGN §3.7「技能門檻 + 任務」):`factions.json` 加 `gate_skills`(取最高)+ `join_skill` + `rank_skill_req[rank]`;
  `factions.join_block_reason / advance_block_reason` 回傳繁中原因;`quests.available_quests` 對 guild 加技能門檻過濾 → 技能不夠就接不到晉升任務。給職業認同(法師難當戰士會長)。
- **L2 階級福利**(`factions.json` 的 `perk`,隨階級成長夾限 cap):戰士=修理折扣(`repair_discount`,會長免費)、法師=法術折扣(`spell_discount`)、盜賊=銷贓加成(`sell_bonus`,接進 `world.sell_price`);
  接進 `action_repair / action_spell_vendor / action_shop`。晉升另發**俸祿**(`quests.STIPEND_PER_RANK × 新階級`)。
- **L3 對立排他**(`rivals` + `lawful`):戰士⇄盜賊勢不兩立(不可雙修);戰士公會(`lawful`)拒收/不升有未繳賞金者。`can_join` 走 `join_block_reason`。
- **L4 晉升任務敘事分支**(任務引擎支援 `branches`):任務頂層放 `branches:[{label,text,stages,reward}]`(**不放** 頂層 objective/stages);
  `quests._resolved` 依 `char.quests[qid]["branch"]` 套用;接取時 UI 選路線;分支隨階段推進保留。三條壓軸(fg7/mg5/tg5)各有 2 條路線(武力 vs 民心/研究/銷贓)。

**裝備系統擴展(評估後直作:修正「純傷害階梯/無 build 軸」,A/B/C/D 四層全做)**:
- **核心基礎設施**:Character 加 `equip_skill_bonus/equip_attr_bonus/equip_resist`(存檔保留);`skill()/attr()` 疊加裝備加成,新增 `base_skill()/base_attr()` 供「成長/夾限」用(learn-by-doing 與升級**只動 base**,別用疊加值);
  `stats.recompute_equipment`(由 `inventory.equipment_bonuses` 彙整穿戴附魔+套裝)在 `recompute_max_resources` 開頭先跑 → fortify_attribute 流進衍生資源;`magic.entity_resist` 玩家抗性=種族+裝備(加總)。
- **C 套組 + 套裝加成**:`armor.json` 16→34 件(每材質補齊 helmet/cuirass/gauntlets/boots[+盾]),全加 `material` 欄;`armor_sets.json` 同材質整套 4 件→套裝加成。
- **A 飾品槽 + 附魔擴展**:新槽 `amulet/ring1/ring2`(不占重量、無護甲值);`synth` 加 `enchj` + `enchanting.enchant_jewelry` 4 型別(fortify 技能/屬性、抗元素、強化資源);`inventory.equip_jewelry`(戒指雙槽)。
- **B 武器流派**(`weapons.json` 加 `archetype`+`speed`):匕首/弓潛襲加成(`archetype_sneak_bonus`)、鈍器破甲(`archetype_armor_pen` 接 `damage_after_armor`)、速度影響命中(`weapon_speed_hit`)與一擊體力(`weapon_attack_fatigue_factor`,接 `player_attack_cost(player, gamedata)`)。
- **D 法杖**(4 把,`skill=destruction/mysticism` → 隨法師技能成長):元素法杖用靜態 `enchant`(複用武器附魔路徑)、法力法杖用 `on_hit_self` 命中回魔。修正「法師無武器格」(模擬:法師徒手 2%→烈焰法杖 100%)。

**開局背景「不一樣的人生」(評估後直作 MVP,參考 Skyrim「Live Another Life」)**:原本所有人都從布魯瑪、50 金、同一套起始包開局——純沙盒缺「我為何在這」的敘事前提。
- **資料驅動**:新檔 `data/origins.json`(6 個開局),`creation.apply_origin(gamedata, char, origin_id)` 在標準角色建好後**就地疊覆寫**(地點/金幣/追加物品/裝備/法術/會籍/賞金/同伴皆可選,留空=沿用標準起始;未知 id→退回 `newcomer` 無覆寫)。
  **零新增 Character 機制欄位**(只加一個 `origin` 字串供結算顯示,dataclass 預設 `""` 向後相容);所有覆寫目標欄位本就序列化 → **零存檔格式風險**。
- **設計守則**:開局**只給「處境」、不給「數值」**(不動屬性/技能,維持 learn-by-doing 成長軸;有回歸測試把關)。`newcomer`=逐位元等同原本起始(向後相容基準)。
- **6 個開局**:`newcomer`(預設)/`fugitive`(逃犯:荒野+0 金+賽羅迪爾賞金 40,硬開局)/`sellsword`(傭兵:海芬古+鋼劍+同伴)/`mage_initiate`(法師學徒:法師公會會籍繞過 join 門檻+烈焰法杖)/`pilgrim`(晨風朝聖,翻轉探索順序)/`fallen_noble`(250 金+金項鍊,經濟開局)。
  **只授 `mages_guild` 會籍**(無 rivals、非 lawful → 與賞金/對立零衝突);刻意不選會踩 rivals+lawby 的戰士/盜賊公會。無任何開局起在地城/高危節點。
- **接點**:`create_character` 加開局選單、`_quick_character` 隨機抽並顯示、`legacy.compute`+`legacy_screen` 結算多一行「出身」(開局↔結算首尾呼應)。
- **新增/改 JSON 即可加開局**(沿用「資料驅動」慣例);驗證走完整 §4 節奏(21 測試模組全綠 + 無頭煙霧:傭兵實戰/法杖戰鬥/逃犯入城遇衛兵/六開局結算渲染)。

**吸血熱 / 吸血鬼化(里程碑級,A+B+C+E 四層;參考 Skyrim「不一樣的人生」之外再加吸血鬼系統)**:一條「力量↔詛咒」動態天平,**做成真權衡而非免費強度**(守住反 min-max 哲學)。核心全在 `systems/vampirism.py`。
- **A 狀態機**:吸血鬼敵人(`vampire_fledgling`/`vampire_lord`,攻擊帶 `infect`)咬中 → 染「吸血熱」(`disease` 疾病,**受種族疾病抗性削弱**,亞龍人/紅衛人較難中)→ 潛伏 3 日 → **轉化**;之後**階級=距上次進食天數//2**(0..3,越餓越高)。感染擲骰在 `combat.resolve_attack`(回傳 `infected`)、`main.run_battle` 冒泡套用;轉化/升階由 `vampirism.update` 在 **game_loop 每圈頂端**驅動(這是評估時點出的「全域時間鉤子」缺口,以 update 收斂)。
- **B 戰鬥身分**:階級加成走**獨立 `vampire_attr_bonus/skill_bonus/resist` 層**(與裝備加成同模式:`attr()/skill()` 疊加、**成長/夾限只用 base_***)。每階 +力量/速度/意志、+潛行/幻術;抗性:免疫疾病、耐霜成長、**火焰轉弱點(負抗性)**。`powers` 加 `vampiric_drain`(汲血擁抱,轉化後取代出生星座之力)+ `drain` 效果處理。
- **C 詛咒/世界**:`expose_to_sun` —— 階級≥1 白天在**非地城**做戶外動作(travel/explore)灼傷(階級3 整日趕路≈45,**夾限保命不在選單曬死**;休息/地城遮蔽 → **進食或夜行才是出路**);階級≥2 **社交封鎖**(`is_shunned` → game_loop 隱藏商店/旅店/訓練師/攀談)。`action_feed`(城鎮可進食 → 階級歸0+回血,白天易被撞見 → 賞金+惡名)。
- **E 開局綁定**:複用 `origins.json` 加 `nightborn`(夜之裔)開局,`vampire:true` → `creation.apply_origin` 標記、`update` 首回合初始化(build 時無 state)。
- **平衡(已模擬)**:對中階敵勝率 凡人 0.76 → 階級3 0.88(有感不破壞);陽光每日上限≈45。**存檔**:7 新欄位走 dataclass 預設 → 向後相容(有回歸測試);**衍生資源**:`apply_to_character` 末段 `recompute_max_resources` 讓力量/意志加成流進體力上限。
- **驗證**:22 測試模組全綠(新增 `test_vampirism`,13 測試)+ 無頭煙霧(被咬感染→轉化→進食重置→汲血之力→結算渲染)。

**內容量**:10 種族 / 13 星座 / 8 職業 / 21 技能 / **19 武器(4 法杖)** / **34 護甲(7 材質整套)** / 25 法術(5 AoE) /
14 材料 / **4 飾品** / **23 生物(含 7 高階 elite + 2 吸血鬼)** / 3 傭兵 / **13 地點(有環圖)** / **4 地城** / 24 任務(含 3 分支壓軸) / **3 公會(有門檻/福利/對立/分支)** / **6 開局背景(含吸血鬼)** / 4 NPC / 15 事件 / **吸血鬼化系統**。
程式:**18 個 `systems` 模組**(+vampirism)+ models/ui/synth 等,共約 34 個 `.py`;**21 個 `data/*.json`**;**22 測試模組**。

---

## 2. 架構地圖

```
tesrpg/
├── main.py          進入點 + 主迴圈(hub 分組選單)+ 所有 action_* 處理器 + run_battle(群戰)
├── rng.py           可重現 seeded RNG(serialize 進存檔)
├── formulas.py      所有數值規則:屬性/衍生值/技能門檻/升級加成/命中/傷害/護甲/resist_multiplier
├── gamedata.py      載入 data/*.json;統一物品索引;item()/item_name() 會處理合成 id;location()/npcs_at()
├── synth.py         合成(動態)物品:brew|藥水、psn|毒藥、enchw|附魔武器、encha|附魔護甲
│                    —— id 自帶定義,存檔只存 id 就能還原(無需註冊表)
├── state.py         GameTime(3E 曆,absolute_hours)、GameState(player/time/start_time/game_mode/rng)+ 存讀檔
├── creation.py      build_character(純函式)+ 起始武器/法術/背包/同伴
├── models/          character.py(Character dataclass + to_dict/from_dict)
│                    creature.py(敵人/同伴/召喚共用;summon_turns/resist/active_effects)
├── systems/
│   ├── progression  learn-by-doing 升點 + 升級(★核心)
│   ├── stats        衍生數值重算/夾限
│   ├── combat       resolve_attack(★所有戰鬥單位組合通用)、spawn_*、random_encounter(_group)、
│   │                pick_player_side_target、try_flee、grant_loot、auto_resolve(會 tick 效果)
│   ├── magic        cast(含 AoE)、tick_effects(DoT/再生,吃抗性)、make_status_effect(正規化)、
│   │                is_feared/is_paralyzed/is_incapacitated、soul_gem_for、_fail
│   ├── alchemy      brew → 共通效果分流成「藥水」或「毒藥」
│   ├── enchanting   靈魂石 → 武器元素附魔
│   ├── inventory    堆疊/負重/裝備/耐久/coat_weapon(塗毒)/use_item
│   ├── world        旅行/遭遇機率/商店定價/訓練師/法術價
│   ├── dungeon      pick_lock(安全技能+塔之鑰)/open_container
│   ├── crime        賞金(按行省)/行竊/衛兵
│   ├── quests       ★多階段任務引擎、available/accept/check_completion、record_kill/dungeon_clear
│   ├── factions     入會/階級
│   ├── dialogue     NPC 好感/說服/賄賂
│   ├── powers       出生星座每日能力
│   ├── loot         resolve_loot(怪物掉落 + 寶箱共用)
│   ├── legacy       一生傳奇總結 + 評分
│   └── events       事件引擎(DESIGN 3.8)
└── ui/console.py    所有 rich 渲染 + menu / grouped_menu / 輸入
```

---

## 3. 關鍵慣例(務必遵守)

- **語言**:程式碼/變數/資料 key 用**英文**(沿用 TES 原文如 `destruction`/`altmer`);玩家看到的文字用**繁體中文**。
- **資料驅動**:新增地點/生物/物品/法術/任務/事件 → **改 JSON 即可,不動邏輯**。
- **存檔規則**:
  - `Character.to_dict/from_dict` 必須涵蓋每個欄位;`from_dict` 用 `cls(**d)`,靠 dataclass 預設值做**向後相容**(舊存檔缺欄位 → 用預設)。
  - **`active_effects` 不寫入存檔**(戰鬥內臨時效果);合成物品只存 id(synth 重建)。
  - 對毀損/舊存檔**防禦性夾限**(例:`quests._stage_index` 用 `max(0, min(...))`、公會階級夾限、`companions` 過濾未知 id)。
- **戰鬥**:`combat.resolve_attack` 通用於玩家/同伴/敵人**任意組合**;`clamp_resources` **只對玩家側**呼叫(怪物 hp 由 `_set_hp` 夾限)。
- **衍生上限/護甲 fortify**:`max_health` 是**有效**上限(`base_max_health` 真基底 + 升級 `resource_levels` + 穿戴護甲 `armor_fortify`);
  `stats.recompute_max_resources(char, gamedata, …)` **務必帶 gamedata**(否則 fortify 視為 0,會吃掉加成)。
  **任何改動 `char.equipped` 的路徑(穿/卸/丟棄/出售)之後都要 recompute**;`inventory.remove_item` 會自動卸下但**不**重算(M14 踩過這個雷)。
- **升級系統(M15)**:`level_xp` 是升級進度(**所有技能升點都餵**,主修 ×1.5);`level_progress`/`level_skillups` 是停用的舊欄位,只為舊存檔 `cls(**d)` 保留。
  `apply_level_up(char, gd, attribute_points: dict, resource_choice)`。**載入存檔走 `GameState.from_dict` 會自動 `ensure_level_xp` 遷移**(舊 `level_progress`→`level_xp`),別繞過它直接建 Character 否則舊存檔升級入口會被隱藏(審查踩過)。
  `max_health` **不再隨耐力逐級長**(改由升級「生命」三選一);改升級公式只動 `formulas.py` 的 `LEVELUP_*` 常數即可平衡。
- **潛行系戰鬥(M16)**:`sneak` 開場偷襲只在 `run_battle` 第一個行動為攻擊時觸發(`resolve_attack(..., sneak_attack=True)`,僅玩家);`acrobatics` 閃避在 `_is_player(defender)` 時從 `hit_chance` 扣 `dodge_evasion`。兩者皆在戰鬥中成長。`marksman`/`light_armor` 本就有用(弓/護甲)。
- **運動 athletics**:`world.travel` 依 `athletics_travel_factor` 縮短耗時並練運動;`combat.player_attack_cost/player_block_cost` 依 `fatigue_cost_factor` 折扣體力。`格擋` 實扣 `BLOCK_FATIGUE_COST`(別再當死常數)。
- **敵人/難度(內容驅動,不做數值縮放)**:難度靠 `min_level` 解鎖更強物種 + 地點 `danger`,**不** scale 怪物數值(刻意,避免 Oblivion 詬病)。bestiary 加 `"solo": true` 的 BOSS 在 `random_encounter_group` 會收斂成單獨一隻;地城 `boss` 加 `"raw": true` 則以原始強度登場(`action_dungeon` 不再 `spawn_boss` ×1.6)。新敵人/地城純改 JSON。
- **元素**:`fire/frost/shock` 受 `magic` 總抗性疊加;`poison`/`disease` 不受 `magic` 影響(見 `formulas.MAGIC_ELEMENTS`)。
- **裝備加成(穿戴附魔/套裝)**:`skill()/attr()` 已疊加 `equip_*_bonus`,但**成長/夾限務必用 `base_skill()/base_attr()`**(progression 已改;否則飾品加成會被寫進 base 永久殘留)。
  任何改 `char.equipped`(穿/卸/戴/丟/賣)後都要 `stats.recompute_max_resources(char, gamedata)`(其開頭會跑 `recompute_equipment`)。飾品在 `ring1/ring2/amulet` 槽,卸下要用 `_equipped_slot_of` 找真實槽(別用 `d["slot"]`)。
  附魔載體:護甲=`armor_fortify`(資源)、飾品=`enchj` 四型別;**武器/法杖附魔走 `gamedata.item(weapon).get("enchant")`**(靜態武器也可帶 `enchant`,法杖即如此)。新套裝/飾品/法杖純改 JSON(`armor_sets.json` / `items.json` / `weapons.json`)。
- **公會(深度化)**:入會/晉升規則全在 `systems/factions.py`(`join_block_reason`/`advance_block_reason`/perk),資料在 `factions.json`(`gate_skills`/`join_skill`/`rank_skill_req`/`rivals`/`lawful`/`perk`)——**加門檻/福利/對立純改 JSON**。
  晉升技能門檻由 `quests.available_quests`(guild)強制;perk 接在 `world.sell_price` + `action_repair`/`action_spell_vendor`。**分支任務**:頂層放 `branches`(各含自足的 `stages`+`reward`,**勿**再放頂層 objective/stages,否則 `_stages` 會誤取),`char.quests[qid]["branch"]` 存選擇、`_advance` 推進階段時務必**保留 branch**。
- **AoE/狀態**:每個敵人各自 `make_status_effect(...)` 取**獨立 dict**(切勿共用同一個 → 會別名汙染計時)。
- **開局背景(不一樣的人生)**:全在 `creation.apply_origin`(在標準 `build_character` 末段、`base_max_health`/`recompute` **之前**呼叫,故穿上的裝備 fortify 能被收尾 recompute 吃到),資料在 `origins.json`——**加開局純改 JSON**。
  守則:**只覆寫處境(地點/金幣/物品/裝備/法術/會籍/賞金/同伴),不動屬性/技能**(否則破壞 learn-by-doing,有回歸測試擋);授會籍請挑無 rivals/非 lawful 的公會(或自行確保與賞金/對立自洽);**別讓開局起在地城/danger≥4 節點**(Lv1 即死,傳奇模式尤甚)。`origin` 欄位只供結算顯示,舊存檔缺它→預設 `""`。`vampire:true` 開局只標記身分,階級/進食日由 `vampirism.update` 首回合初始化。
- **吸血鬼化(里程碑)**:狀態機全在 `systems/vampirism.py`,**`vampirism.update(state, gd)` 必須在 game_loop 每圈頂端先呼叫**(驅動轉化/升階/初始化);階級加成走 `vampire_*` 獨立層(**成長/夾限只用 `base_skill()/base_attr()`**,同裝備鐵律);`apply_to_character` 末段會 `recompute_max_resources`(力量/意志加成→體力上限)。
  感染向量:吸血鬼敵人 `attack.infect`(機率)→ `combat.resolve_attack` 回 `infected` → `run_battle` 套 `vampirism.infect`;**疾病抗性削弱感染**(`resist_multiplier(...,"disease")`)。陽光只在 travel/explore 結算(`_maybe_sunburn`,**夾限保命**);`is_shunned`(階級≥2)在 game_loop 隱藏 NPC 商業服務,`action_feed` 解除。**加吸血鬼敵人純改 bestiary**(`infect` + 火焰負抗性);調平衡只動 vampirism.py 常數(`STAGE_*`/`SUN_*`/`FEED_*`)。轉化後**出生星座之力被 `vampiric_drain` 取代**(刻意:詛咒蓋過天賦)。

---

## 4. 開發節奏(ultracode 開著 → 每個功能都這樣做)

1. **實作**(資料 + systems + main/ui)。
2. **單元測試**:新增 `tests/test_*.py`(用 `assert`,可直接 `python3` 跑;登錄進 `tests/run_all.py`)。
3. **平衡模擬**:Bash 一行式跑 `combat.auto_resolve` / 手寫迴圈,印勝率/回合數。
4. **無頭煙霧測試**:把 `ui.console` 換成 `Console(file=StringIO())`、`ui.menu` 換成自動選擇,實跑 `run_battle`/action,抓 traceback。
5. **對抗式審查(Workflow 工具)**:多維度 fan-out 審查 → 每個發現由獨立懷疑者**對抗式驗證** → 只回報「能真實重現」的 bug。
6. **覆核 + 修正**:**逐一覆核審查結果**(會有誤報、也會有「會引入新 bug 的錯誤修法」—— 已擋下 2 次);套用確認的修正 + 補回歸測試;重跑全套。

> 戰績:十二輪審查累計修掉 **~23 個真 bug**、擋下 **2 個錯誤修法**、自補 1 次審查覆蓋缺口、自抓數個測試基建坑。
> M14 輪:抓到會**寫入存檔的數值回歸** —— 丟棄/出售「穿戴中的 fortify 護甲」未重算,加成永久殘留(出售還倒賺金幣)。
> M15 輪(升級改版):抓到 3 個 —— ①(major)`ensure_level_xp` 未在**載入路徑**觸發 → 可升級的舊存檔升級入口被隱藏;
> ②(minor)`apply_level_up` 屬性點以「請求量」而非「實際套用量」計帳 → 觸頂吞點;③ 三處 UI 文案仍稱「只有主修計入升級」。均已修 + 補回歸測試(且反向驗證測試能抓到)。
> 重點教訓:**互動式 `run_battle` 測試會全域 patch `ui.menu`,模組間會互相汙染**(test_m13 因此踩雷)—— 需要時在測試內自行重設 `ui.menu`。

---

## 5. 設計定案(DESIGN.md §7)

死亡規則=**兩種模式**(冒險可讀檔 / 傳奇 roguelike 永久死亡);職業=8 預設+自訂;起始省=賽羅迪爾·布魯瑪;
**純沙盒**(無主線);時間以「小時」推進(12 月×30 天);技能=Oblivion 的 21 套;一生評分公式在 `systems/legacy.py`。

---

## 6. 下一步候選(依槓桿排序)

1. **內容難度第二階段 / 實機微調**:elite 已上但只在 danger≥4 野外 + 龍喉巢穴/灰燼墓塚出現;可加更多終局區、把 elite 接進更多地城首領池、跑過後微調 elite 數值(魔人領主/巨龍仍偏硬,模擬是 no-heal 下限)。
2. **新省份擴充**(高價值/低風險,純資料):地圖 UI 與群戰都已能撐;加 `world.json` 地點 + `dungeons.json` + `bestiary` 生物即可。
   ⭐ 世界已是**有環圖**(見 §1「擴張玩法」),新省份請**雙向連通成環**(別再接成走廊尾巴);可順手把現有地城後門模式複用到新地城。
3. **成就系統**(重玩性,種子已開放):`legacy.compute` 已輸出種子;可加一張結算成就表(首殺 boss / 無傷清地城 / 純法師通關…),複用 `kill_counts`/`cleared_dungeons` 等既有計數。每日/分享種子的前置(種子輸入)已完成。
4. **體力對法師仍是死資源**(體力消耗評估的 option B,未做):純施法者戰鬥中不耗也不受罰體力 → 三系資源不對稱。可做「施法耗少量體力」或「低體力降施法成功/威力」。
5. **半成品/微調**:創角問答推職業;護甲附魔可再擴(目前只 fortify 生命/魔力/體力);更多事件/任務。
6. (天花板更高、工程量大)主線劇情、同伴持久 HP/羈絆、坐騎/房產。

> ✅ 已完成(近期):**世界拓樸改造**(走廊→有環圖,§1)、**種子開放給玩家**(原 §6.4 前置)、
> **公會深度化**(§1:門檻 + 福利/俸祿 + 對立 + 分支)、**裝備系統擴展**(§1:套組/套裝 + 飾品/附魔 + 武器流派 + 法杖)、
> **開局背景「不一樣的人生」MVP**(§1:6 開局,資料驅動 `apply_origin`,零存檔風險)、
> **吸血鬼化系統**(§1:A 狀態機 + B 戰鬥身分 + C 陽光/社交詛咒 + E 夜之裔開局;**D 治療任務刻意延後**)。
>
> 公會後續可再加:更多分支壓軸 / 階級設施權限 / 公會委託告示 / 暗殺者公會(第 4 會)。
> 裝備後續可再加:獨特/具名裝備(套裝外的具名神器)、附魔護甲擴展到技能/抗性(目前護甲只 fortify 資源)、武器附魔可帶狀態(吸血/麻痺)、回復型附魔(per-turn regen,目前略過)。
> 開局後續可再加:更多開局(暗殺者/海難倖存者/獸人部族…純改 JSON)、開局附帶**起手任務鉤子**(MVP 刻意未做)、`armor` 起手整套裝(目前開局只給單件飾品/法杖)、開局選單依職業/種族過濾推薦。
> 吸血鬼後續可再加:**D 治療任務**(複用任務引擎解詛咒)、夜視/魅惑等更多吸血鬼能力、狼人(同套狀態機另一支)、吸血鬼專屬裝備/巢穴、NPC 識破後衛兵敵對(目前只社交封鎖)。

> ⚠️ 開新功能務必沿用「§4 開發節奏」:實作 → 測試 → 平衡 → 煙霧 →(ultracode 開時)對抗式審查 → 覆核修正。

---

## 7. 已知限制 / 待留意

- `run_battle` 沒有回合上限(互動式靠玩家逃跑當出口;若要寫純自動模擬請用 `combat.auto_resolve`,它有 `max_rounds`)。
- 同伴每戰滿血重生、戰中被擊倒下場仍會回隊(無持久 HP/永久死亡)—— 刻意從簡。
- `mass_paralysis` 等純 CC 法術單用不會贏(無傷害),是 combo 工具,符合設計。
- 沒有 CI;測試靠手動 `python3 tests/run_all.py`。可考慮加 GitHub Actions 跑它。

---

## 8. Git 狀態

- 已 init(`main`)、`.gitignore` 排除 `__pycache__`/存檔;均已推上 GitHub。近期 commit(新→舊):
  - `04ab28f` 終局內容:龍喉巢穴地城 + elite 接首領 → `cc6686f` 內容難度:elite + 群戰 + BOSS 單獨 →
    `6bd9d6a` 格擋體力 + 運動降耗 → `5ed464a` 運動旅行加速 → `da33db8` M16 潛行系戰鬥化 →
    `6472732` M15 升級改版 → `4678a72` M14 護甲附魔 → `67726c6` UI 改版 → `52cf9ca` 初始。
- 日後更新:`git add -A && git commit -m "..." && git push`(commit 訊息結尾請加
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`)。
- 本 `handoff.md` **已納入版控**(每完成一輪請順手更新並 commit,讓下個 session 不踩空)。
