# Handoff — 流亡者 (tesrpg)

上古卷軸風格的**技能驅動沙盒文字 RPG**(**瀏覽器 Web 版**;Python 後端,`rich` 把畫面渲成 HTML)。單一英雄:做什麼練什麼、
跨四省(賽羅迪爾/天際/晨風/黑沼澤,世界已閉合成大環)探索鑽地城、戰士/法師/盜賊三系玩法,直到陣亡或隱退結算一生傳奇。
> ⚠ **已 Web-only**:終端機版(`python3 -m tesrpg`)已移除;`tesrpg/ui/console.py` 為 Web 的渲染/輸入接層(`_*_view` view-model + rich→HTML 退路 + `_web_prompt`),5 個輸入原語無 web backend 時直接 raise(測試照舊 patch `ui.*`)。

> 給接手的 session:這份文件是「立刻能接著做」的地圖。先讀「現況」「怎麼跑」「開發節奏」三節即可上手。

---

## 0. 環境 / 怎麼跑

- **工作目錄**:`/home/fischer/SLG`
- **GitHub**:`git@github.com:Fischer-Zhang/elder-scrolls-textrpg.git`(分支 `main`,SSH 已認證為 Fischer-Zhang)
- **Python 3.12**;`rich` 由**系統套件**提供(`python3-rich`)—— ⚠️ **本機沒有 `pip`、沒有 `pytest`、sudo 需密碼**。
- **執行遊戲**:`python3 -m tesrpg.web`(本機 Web 版,瀏覽器開 `http://127.0.0.1:8080`;**唯一進入點 —— 已 Web-only,終端版已移除**)
- **跑測試**:`python3 tests/run_all.py`(不需 pytest;**全綠**;模組數見結尾「全部通過 (N 個測試模組)」,別在文件硬寫數字)/ 一鍵 `bash check.sh`(編譯 → 測試 → 條件式 sim)
- **編譯檢查**:`python3 -m py_compile tesrpg/**/*.py tesrpg/*.py tests/*.py`
- 存檔在 `~/.tesrpg/save.json`(在 repo 外;測試/煙霧測試後記得 `rm -f ~/.tesrpg/save.json`)

---

## 1. 現況:M1–M16 + 多輪戰鬥/內容強化,全部完成、已上 GitHub

> ⚠ **數量為快照,別盲信**:本節的技能/地點/節點/同伴數等為**最後更新時的快照**;有疑義以程式 / JSON / `run_all.py` 輸出為準,並順手更新。技能數 = `len(gamedata.skills)`(`data/skills.json`);測試模組數見 `run_all.py` 結尾 `全部通過 (N 個測試模組)`。

### 系統現況總覽(依系統分類)

#### 角色與成長
- 10 種族 × 13 星座 × 8 職業/自訂;八屬性 + **23 技能** learn-by-doing;混合 Skyrim 式升級(等級 XP 池 → 三選一資源 + 屬性點)
- **技能里程碑 v2 + 完整階梯**:全 23 技能各 **25/50/75/100 四節點(92 節點)**;**25=單一 perk 自動授予**(入門技,複用退化節點)、**50/75/100=達門檻二選一**永久銘刻 + 持久 fortify 加成層(skill/attr/resist)+ 功能槓桿(武器/法術控場、戰場自修、重甲反震、逃命、解陷保底、頂點 capstone…);反 min-max、守刺客紅線(同源多節點 getter 必聚合不遮蔽;repair_floor 類 floor 須高於門檻 base cap)
- **八職功能性身份網格**:全 8 職各一招牌戰術 loop(功能性非數值)—— 戰士盾牆(減傷·嘲諷)/法師奧術連鎖/盜賊諜報偵搜/騎士戰旗/戰法師共鳴一擊+法力回擊(毀滅 50/75 兩節點,可兼得)/刺客致命烙印/治療師戰地搶救/弓手獵手偵察(6 mastery 二選一節點 + 2 戰鬥動作;以技能/裝備 gate、零新存檔欄、守刺客紅線)
- **開局背景**(14 種,只給處境不給數值)+ **種子重玩性**;冒險/傳奇兩種死亡模式 + 一生傳奇總結評分

#### 戰鬥與魔法
- 回合制**多敵 + 團隊戰鬥**(召喚物/傭兵同伴);**同伴角色化**(9 具名同伴:持久 HP/羈絆 + 具名招募任務 + 羈絆階解鎖的專屬支線 + 就地對話 + 完成支線的忠誠弧頂點〔戰術盟友光環/被動非戰鬥槓桿;盟友限定守刺客紅線〕;復用 `companion_bond` 當忠誠軸,零新存檔欄);**六大學派 + AoE**(召喚/秘術補完至各 7 法術,與毀滅/復原/變換同列;**召喚**=元素元身/魔人 + 束縛兵刃〔法系近戰〕+ 亡者復生〔屍起為盟〕、**秘術**=法術結界〔吸法術傷·吸魔變體〕+ 驅散 + 群體擒魂);元素抗性/弱點、狀態效果、出生星座每日之力
- **三系資源對稱**:施法也耗體力、力竭降法效(`cast_fatigue_*`),**法袍套裝**省體施法(法師的對應裝甲)
- **煉金毒藥 + 武器塗毒**;**潛行刺客系**:偷襲先機、暗殺殘響、雙持、**隱遁再襲(潛行 25 里程碑「隱遁之術」;連環踏影對單體仍遞減、反 solo boss 風箏)**、戰前偵查;武器流派(潛襲/破甲/速度)

#### 世界與探索
- **八省 ~168 地點 / 48 城 + 17 鎮 + 70 野區 + 33 地城**(含海爾根 Helgen=白隘北口、賽→天門戶)(每省 5–9 城 + 多個正典分區野區〔黃金海岸/苦岸/裂石郡/收割者三月…〕做城際過場;邊境戍堡為省際接縫)+ **`pos[col,row]` 與 `links` 皆依正典 TES 地理**(頂層 `world["map"]` 40×24);旅行/晝夜/危險度(數字為快照,以 JSON/測試為準)
- **生態遭遇**(biome 加權,八生態含 savanna 弱毒)、**省份風味事件**、**具名地標**首發現、各城**考據統治者**;終局 solo BOSS
- **城鎮服務專精化(R29)**:訓練師依公會/lore 只教部分技能(戰士城練戰鬥/法師城練魔法/盜賊城練潛行)+ 11 招牌城**宗師指點**破一般訓練上限(馬卡斯鍛造/冬堡毀滅/裂谷開鎖…);法師公會**法術學派分省守護**(各省主賣一派深線 + 保底集 9 道,別派進階須跨省採購;`imperial_city` 通才例外)。給戰士/盜賊/法師各一張「該去哪精進/採購」的地圖;功能性差異、零存檔欄位
- **格子地城探索**(`systems/dungeoncrawl.py`):15 地城程序化生成 n×n 格 × m 層,N/S/E/W 移動 + 樓梯下層 + 迷霧小地圖 + 格內怪/寶/陷阱;清末層 boss = 肅清,首領死亡自動解鎖寶藏(原子探索、零新存檔欄)。**視為戰鬥情境**:可一般行動(施法/背包/角色卡)、**預施增益/預召喚召喚物**(行動 1 格 = 1 回合逐回合衰減,經 carry_allies/preserve_buffs 帶進觸發戰鬥)、**偵查 perk 探明四鄰**(每探明新格得少量偵查 xp);持久狀態條一併顯示夥伴/召喚物

#### 製作與裝備
- **鍛造**(金屬四階 + 頂級魔族/龍鱗/龍祭司,稀有素材困難取得)、**裁縫**、**淬鍊強化**、**回爐熔解**(成品→部分材料,有損耗+練鍛造);**附魔**(武器:元素即時傷害 + **元素 DoT〔焚燒/凍緩/感電〕** + **命中吸取〔生命/魔力/體力〕** + 命中觸發吸血/再生 + **充能型麻痺·命中擒魂**;護甲:技能/抗性/資源;飾品:技能/屬性/抗性/資源)+ **靈魂石經濟**(空魂石→擒魂填充、大靈魂石 soul5、黑魂石囚人形魂、武器充能以魂石回充;見 R15/附魔深化)
- **套裝加成**(同材質四件)、武器流派、飾品槽、法杖、法袍;**具名神器**;裝備耐久 + 修理

#### 公會、任務與政治
- **七大公會**:戰士/法師/盜賊 + 黑暗兄弟會 + 神話黎明 + 九神騎士團 + **戰友團**(白漫·狼人血脈歸宿,獸血儀式繫於其內圈)(技能門檻/福利/對立/分支壓軸)
- **多階段任務引擎**;犯罪賞金 + 衛兵 + 謀殺;**吸血鬼化**(力量↔詛咒天平)、**狼人化**(戰友團內圈獸血,獸形變身)、**斯庫瑪/月糖成癮**(亢奮↔戒斷天平,艾爾斯維爾)
- **領主政治 / 城戰**:謁見 → 委託 → 武士冊封;圍城 + 破城 + 收稅 + 招兵買馬;**陣營動態大事件**

#### 系統與打磨
- **事件引擎**、**成就系統**、**反 min-max 經濟**(practice 成本)、**Web 版**(原生渲染、可點互動)

### 里程碑歷程

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
- **格擋體力成本接上**(`BLOCK_FATIGUE_COST` 原是死常數);**技能健檢**:22 技能(含 scout)皆有機制效果 —— ⚠️後續(本 session)健檢復查發現**格擋的「等級」原本空轉**(減傷寫死 ×0.4、全碼無 `skill("block")` 讀取),已修並接上縮放(見下「格擋接上技能縮放 + 技能里程碑」)。
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

**吸血熱 / 吸血鬼化(里程碑級,A+B+C+D+E 五層全做;參考 Skyrim 吸血鬼系統)**:一條「力量↔詛咒」動態天平,**做成真權衡而非免費強度**(守住反 min-max 哲學)。核心全在 `systems/vampirism.py`。
- **A 狀態機**:吸血鬼敵人(`vampire_fledgling`/`vampire_lord`,攻擊帶 `infect`)咬中 → 染「吸血熱」(`disease` 疾病,**受種族疾病抗性削弱**,亞龍人/紅衛人較難中)→ 潛伏 3 日 → **轉化**;之後**階級=距上次進食天數//2**(0..3,越餓越高)。感染擲骰在 `combat.resolve_attack`(回傳 `infected`)、`main.run_battle` 冒泡套用;轉化/升階由 `vampirism.update` 在 **game_loop 每圈頂端**驅動(這是評估時點出的「全域時間鉤子」缺口,以 update 收斂)。
- **B 戰鬥身分**:階級加成走**獨立 `vampire_attr_bonus/skill_bonus/resist` 層**(與裝備加成同模式:`attr()/skill()` 疊加、**成長/夾限只用 base_***)。每階 +力量/速度/意志、+潛行/幻術;抗性:免疫疾病、耐霜成長、**火焰轉弱點(負抗性)**。`powers` 加 `vampiric_drain`(汲血擁抱,轉化後取代出生星座之力)+ `drain` 效果處理。
- **C 詛咒/世界**:`expose_to_sun` —— 階級≥1 白天在**非地城**做戶外動作(travel/explore)灼傷(階級3 整日趕路≈45,**夾限保命不在選單曬死**;休息/地城遮蔽 → **進食或夜行才是出路**);階級≥2 **社交封鎖**(`is_shunned` → game_loop 隱藏商店/旅店/訓練師/攀談)。`action_feed`(城鎮可進食 → 階級歸0+回血,白天易被撞見 → 賞金+惡名)。
- **D 治療任務**(複用任務引擎):`quests.json` 加 `cure_vampirism`(source `vampire_cure` → 不漏進告示板/公會),3 階段 collect 大蒜×4 + collect 毒茄參×3 + kill 吸血鬼貴族×1;`vampirism.cure(char, gd)` 清空狀態並重算(星座之力隨之回歸)。任務「備齊媒介」走引擎自動結算,**最後儀式是顯式動作** `action_vampire_cure`(任一法師公會、僅吸血鬼可見的子選單項):接取→進度→備齊後行儀式解咒。解咒後把任務移出 `completed_quests` → **可重複**(日後再被感染可再求一次)。
- **E 開局綁定**:複用 `origins.json` 加 `nightborn`(夜之裔)開局,`vampire:true` → `creation.apply_origin` 標記、`update` 首回合初始化(build 時無 state)。
- **平衡(已模擬)**:對中階敵勝率 凡人 0.76 → 階級3 0.88(有感不破壞);陽光每日上限≈45。**存檔**:7 新欄位走 dataclass 預設 → 向後相容(有回歸測試);**衍生資源**:`apply_to_character` 末段 `recompute_max_resources` 讓力量/意志加成流進體力上限。
- **驗證**:22 測試模組全綠(新增 `test_vampirism`,15 測試)+ 無頭煙霧(被咬感染→轉化→進食重置→汲血之力→結算渲染→**完整解咒流程**)。

**各城統治者(城戰前置;湮滅期 3E433、皇統斷絕、大空位各城自治)**:純資料 + 一處呈現,為未來「城戰」鋪地基。
- **資料驅動**:新檔 `data/rulers.json`,以 location_id 為 key 的 6 座城主(3 大城布魯瑪/海芬古/黑光城 + 3 城鎮凱瓦奇/龍橋鎮/莫拉格瑪);欄位 `name/title/race/garrison(兵力,城戰前置)/blurb`,有真實 TES 考據(布魯瑪卡薇恩伯爵、凱瓦奇金酒伯爵)。**政治資料與地理(world.json)刻意解耦** → 未來城戰的可變狀態(歸屬/交戰/兵力消長)有乾淨的家。
- **接點**:`gamedata.rulers` + `gamedata.ruler_at(loc_id)`;`ui.location_panel` 進城顯示「👑 統治者:銜·名(大空位·自治)」。**零存檔影響**(唯讀靜態資料,無 Character 欄位)。
- **加城主純改 `rulers.json`**;`test_world` 補資料完整性測試(每座城/鎮都有合法城主、種族合法、key 對應真實地點;荒野/地城無城主)。

**刺客流派大改(評估→使用者拍板五項一起做:殘響+雙持+隱遁+偵查 + 入場檢定;對抗審查修掉 3 真 bug)**:解決「偷襲先攻沒殺死→陷入困境」。先做了**評估 workflow**(理解+模擬+設計面板),再依使用者選擇實作:
- **暗殺殘響/combo**:偷襲命中但沒秒殺 → 依武器流派(`_ARCHETYPE_SNEAK_AFTERMATH`)留**踉蹌**(`magic.is_staggered`,該目標下一擊 `STAGGER_HIT_PENALTY` 命中減成)+ **撕裂傷**(element=`bleed` 無視一般抗性 DoT,強度吃 sneak+alchemy)。匕首吃滿、弓只踉蹌、劍/鈍器無。
- **雙持匕首**:`Character.offhand` 槽(僅匕首);副手傷害 `OFFHAND_DAMAGE_FACTOR=0.6` 折入 —— ⚠️**審查修正:副手作「不吃偷襲倍率的補刀」**(`resolve_attack`/`estimate_sneak_damage` 都在 sneak_mult **之後**才加),否則會被 ×6.4 放大秒精英。代價:雙持不能格擋。
- **隱遁再襲(可失敗)**:戰鬥中花一回合重新潛入(`formulas.restealth_chance`,吃 sneak+acro、敵多/重複用遞減)。成功→跳過本回合敵人階段 + 重置 `opening`。⚠️**審查修正(防無限風箏)**:`player_vanish_cost` 耗體力、`vanishes_done` **每次嘗試**遞增、每場硬上限 `MAX_VANISHES_PER_BATTLE=3`。
- **偵查(第 22 個技能 `scout`,stealth 系)**:⚠️**刻意突破原「21 套 Oblivion 技能」支柱**(使用者要求)。戰前分級揭露敵情(<20 模糊、≥20 血量/危險度、≥50 偷襲估傷、≥75 抗性弱點)、learn-by-doing。`progression.use_skill` 改以 `gamedata.skills` 驗證並自癒缺漏、`GameState.from_dict` 的 `ensure_all_skills` 補舊存檔 → 向後相容。
- **入場潛行檢定(B+C+E)**:接戰時擲 `formulas.stealth_approach_chance`(吃潛行/敵警覺/敵數/**護甲噪音**/夜間/偵查/伏擊)決定有無開場偷襲(複用 `run_battle(alerted=)`)。**修兩不一致**:人人白送偷襲 → 重甲莽夫幾乎偷不到(~8%);旅途伏擊 `surprise=True` → 受害者難反偷襲(~34%)。先偵查 +0.25(偵查解博弈)。
- **平衡(全程模擬 `sim_assassin.py` 保留為回歸工具)**:救得了失手(2強盜 33%→19%)、雙持中階敵秒殺/精英仍擋得住一擊、隱遁無限風箏已消滅(ancient_dragon 仍 ~1% 勝)。`offer_battle` 已是 偵查/潛退/接戰(顯示偷襲先機%)三選一。

**地圖擴展「黑沼澤閉合世界大環」(評估後使用者拍板:閉合大環 + 省分細化;純資料,零邏輯)**:原本三省是 `賽羅迪爾—天際—晨風` 的**開放鏈**(省內已成環,但全域仍是一條線,晨風只能原路折返)。新增**黑沼澤**省,在 TES 地理上同時鄰接賽羅迪爾與晨風 → 接成**世界大環**(`賽羅迪爾→天際→晨風→黑沼澤→回賽羅迪爾`),造出「北線(天際)vs 南線(黑沼澤)」的平行路線抉擇。
- **拓樸(純改 `world.json`,7 新節點)**:邊境野外 `niben_marsh 尼本河沼`(d2,接帝國大道)/`thorn_fen 荊棘沼澤`(d4,接莫拉格瑪);黑沼澤省內 `gideon 吉迪恩`(city d0,trainer+mages_guild+armorer)/`stormhold 石落城`(town d0,thieves_guild,賣玻璃匕首)/`murkmire 幽沼濕地`(d3)/`hist_grove 希斯特聖林`(d3)/`xanmeer 贊密爾沉廟`(dungeon d4,可穿越)。**內部雙環**(吉迪恩-幽沼-石落城-沉廟 主環 + 幽沼-聖林-石落城 內環)。南線比北線**更長更險**(換取整省內容,非通勤捷徑)。只動既有節點兩條邊(`imperial_road+=niben_marsh`、`molag_mar+=thorn_fen`),皆雙向。
- **主題=毒/電/疾病,剋星=火**(操練偏冷的 poison 抗性軸 + 火系 build):`bestiary` 加 5 隻 —— `swamp_lizard`(d2 毒)/`marsh_zombie`(d4 瘟疫毒 DoT)/`will_o_wisp`(d4 電,難命中)/`bog_troll`(d5,**火焰負抗 -50**)/`wamasu 瓦瑪蘇`(min13 雷蜥 **elite solo**,贊密爾首領 `raw`)。沉廟首領寶藏首度產出**玻璃護甲**(`glass_cuirass`,給新省專屬獎勵誘因)。
- **城主**:`rulers.json` 加 `gideon`(帝國總督·奎因圖斯·瓦羅,殘存帝國權威)+ `stormhold`(亞龍人樹語祭司·鱗影-飲霧,希斯特自治)—— 對應湮滅期大空位考據,過 `test_world` 聚落↔城主檢查。
- **驗證**:23 測試模組全綠(`test_world` 加 3 斷言:**黑沼澤閉合大環** BFS 證明南線獨立於北線、贊密爾納入可穿越地城、**新增商店 stock id 合法性**防線);遭遇抽樣(新怪依 danger/min_level 自然生成、入口 niben_marsh 不噴 d4 精英、瓦瑪蘇 solo 不成群);elite 校準(瓦瑪蘇位於魔人領主↔巨龍之間,no-heal 下限同 tier);無頭煙霧(走完整大環 13 跳 + 渲染新地點面板/世界地圖 + 瓦瑪蘇戰)。**加新省純改 `world.json`+`dungeons.json`+`bestiary.json`+`rulers.json` 四檔(零邏輯、零存檔風險)**。

**黑暗兄弟會(里程碑;A+B+C+D+E 五層全做;血債招募 + 合約晉升 + 夜母祝福)**:第 4 公會,DESIGN §3.7 早預留的「暗殺公會」,也是刺客流派大改(潛行/偵查/雙持/隱遁/撕裂)的敘事與晉升歸宿。核心狀態機在 `systems/brotherhood.py`(仿 vampirism)。
- **A 謀殺機制 + 血債招募**:補上 DESIGN §3.7 預留卻缺席的「殺人」沙盒 —— 攀談選單加「🔪 暗殺此人」(`action_murder`:可先靠潛行搶背刺先機 → `run_battle` 對 `townsperson`),得手 → `brotherhood.record_murder`(血債 +1、當地 `MURDER_BOUNTY=500`、惡名 +2、把該 NPC 加進 `char.murdered_npcs` 從世上抹去)。血債在身者**休息入夢時**被使者招募(`action_rest`→`_maybe_db_recruit`),接受即入會(不走大廳 walk-in);婉拒設 `db_invited` 不再每圈騷擾。**戰士公會員(對立)不會被招募**。
- **B 合約晉升階梯**:7 階(新血→…→聆聽者)、6 張合約(`db1`–`db6`),走既有 guild 晉升流(`source:"guild"`、`faction:"dark_brotherhood"`、`rank` 對應階級、`rank_skill_req` 用刺客技能門檻晉升)。合約=`kill` 具名目標(7 隻 `min_level:99` 不會野生刷出的目標 NPC + `townsperson`);**聖所專屬動作 `action_sanctuary`/`action_contract`**:接合約→「執行合約」當場潛入行刺(`try_stealth_approach` 決定先機)→ `run_battle` 記擊殺 → 自動晉升。**無人目擊潛殺加成**(`clean_bonus`):搶到偷襲先機且勝利則額外發賞。`db4` 帶 `escort`(衛兵)示範群戰合約。
- **C 五戒/淨化背叛分支壓軸**:`db6` 用 `branches` 兩條路線(忠誠→清除叛徒 `brotherhood_traitor` / 淨化背叛→刺殺 `dark_speaker`),皆晉升聆聽者;聖所可「重溫五戒」。
- **D 夜母祝福 + 洗白賞金 perk**:祝福=**每階 +0.03 偷襲倍率**(`formulas.night_mother_sneak_bonus`,接 `combat.resolve_attack`/`estimate_sneak_damage` 的 `sneak_mult`)——⚠️**經模擬刻意壓低**:即使聆聽者滿階 ×1.18 + 頂級雙持玻璃匕首,所有 **BOSS(solo)單擊秒殺率仍 ≤1.5%**,守住刺客大改「偷襲不可秒精英」的紅線(改此常數務必重跑 `sim_assassin.py` + 精英秒殺率覆核)。perk=`bounty_launder`(新 kind,階級越高洗白賞金越便宜,接 `action_sanctuary` 一處;與 repair/spell/sell perk 互不干擾)。
- **E 暗殺者開局 + 聖所**:`origins.json` 加 `dark_initiate`(複用 `apply_origin` 的 `faction` 直接授會籍,鋼匕開局);聖所=`world.json` 給布魯瑪/海芬古加 `dark_brotherhood` 服務,**唯入會者**才在 hub 看得到(`action_sanctuary` 入口)。
- **接點/鐵律**:對立雙向(`fighters_guild.rivals` 也補了 `dark_brotherhood`);新 Character 欄位 `murders`/`db_invited`/`murdered_npcs`(dataclass 預設 → 向後相容,有回歸測試);會籍/階級仍存 `factions["dark_brotherhood"]`(與三會同制,自動進 legacy 公會欄);傳奇結算多「血業」欄(`brotherhood.legacy_label`)。**加合約純改 quests.json + bestiary 目標**;調平衡只動 `brotherhood.py`/`formulas.NIGHT_MOTHER_SNEAK_PER_RANK` 常數。
- **驗證**:24 測試模組全綠(新增 `test_brotherhood`,13 測試:謀殺/招募/對立排除/合約階梯/技能門檻/分支壓軸/祝福/洗白/開局/存檔向後相容)+ `sim_assassin` 基線不變 + 精英秒殺率覆核(boss ≤1.5%)+ 無頭煙霧(謀殺→血債招募→聖所接約/執行→晉升→開局→結算 全流程)。

**細化省分(評估→直作:Tier1 純資料活化 + Tier2 兩處小程式;對抗審查修掉 5 處)**:評估發現「問題不在地點數量,而在 province 維度幾乎沒被用」——野外遭遇/告示板/事件三者原本全域共享、完全不分省。本輪把這維度活化,並補足最薄的天際/晨風。
- **Tier2-a 生態遭遇表**:`bestiary` 16 隻怪加 `biomes`(snow/ashland/swamp;giant_rat/wolf/bandit 等通用怪不標 → 四海皆有的後備池);`world` 每地點加 `biome`(賽=heartland/天際=snow/晨風=ashland/黑沼澤=swamp,邊境依鄰接);`combat.random_encounter(_group)` 用 `_biome_weight` 加權(`BIOME_MATCH_WEIGHT=3.0`/`BIOME_MISMATCH_WEIGHT=0.25`),`world.travel` 與 `main.action_explore` 傳入當地 biome。效果:雪原噴骷髏/屍鬼/冰魂、火山噴灰蹦蟲/魔人、沼澤噴蜥蜴/鬼火,**一出城就知道在哪省**,且任何 (biome,level) 池都不會被抽空(通用怪墊底)。**零數值縮放**(只加標籤/權重,不動怪數值)、**零存檔風險**。
- **Tier2-b 告示板按省過濾**:`quests.available_quests` 加 `province` 參數,board 分支用 `q["provinces"]` 過濾(無 `provinces` 者=全圖通用,向後相容);`main.action_board` 傳入當地 province → **在地懸賞**(如 `job_xanmeer` 只在黑沼澤板,不再誤誘新手)。
- **Tier1-a 天際補密度**(最薄省 3→5):`world` 加 `falkreath_wood`(佛克瑞斯林,wilderness d2)+ `lostknife_cave`(迷刀洞窟,dungeon d2,雙向成環)、`dungeons.json` 加迷刀洞窟房間。**晨風補 1 荒野**(`ashland_waste` 灰燼荒原 d2,修原「晨風 0 荒野」缺口 + 讓灰蹦蟲懸賞就近可獵)。
- **Tier1-b 在地 NPC + 任務**:`npcs.json` 4→8(補晨風 verand/dralasa、黑沼澤 lucius/silent_water;jovan 改掛委託)→ **晨風/黑沼澤不再零 NPC**;`quests` 加 7 在地任務(4 NPC 委託 favor_* + 3 在地懸賞 job_*),把零任務的 xanmeer/新 lostknife/在地怪都接上。
- **Tier1-c 省份風味事件**:`events.json` 15→23,用早就支援卻沒人用的 `trigger.provinces` 加 8 個四省限定事件(暴風雪/灰燼風暴/希斯特低語/帝國巡邏 + 在地掠食 ice_wraith/will_o_wisp + 火山/沼澤野採),把全域同文事件換成在地風味。
- **對抗審查修正(5 處)**:① `frostbite_spider`(霜咬)biome swamp→snow(名實相符,且補上雪原缺的低階 d2 怪);② 兩個 predator 事件移除「邊境」(避免冰魂在沼澤觸發);③ `ashland_waste` 補上(灰蹦蟲懸賞就近可獵);④ `job_falkreath` 120→130 金(解除被 job_wolf 嚴格支配);⑤ 天際雪原早期偏硬(lv2 d3 遇敵率 ~55%)為**刻意省份難度區隔**(雪原較險,接在和緩的賽羅迪爾起點之後),已記錄於此。
- **驗證**:25 測試模組全綠(新增 `test_detailing`)+ 生態分流抽樣(各省招牌生態 + 池不空)+ sim_assassin 基線不變 + 無頭煙霧(旅行生態遇遇/告示板過濾/NPC 委託/省份事件/新地城)+ 對抗審查 workflow。**加在地怪純改 biomes、加在地懸賞純改 quests provinces、加省份事件純改 trigger.provinces**。

**再進一步細化(評估 workflow→①②③ 套餐;對抗審查修掉 minotaur 危險度)**:承上輪,活化仍偏弱的面向。
- **① heartland 招牌生態怪**:賽羅迪爾原本是唯一**零專屬生態怪**的省(野外只噴鼠/蟹)。`bestiary` 加 `imperial_ghost`(帝國亡魂,d2/min1,`biomes:heartland`,resist `magic`/`poison`——刻意用 magic 抗**而非 frost**以區隔屍鬼)+ `minotaur`(米諾陶,**d3**/min3);`events` 加 `cyrodiil_ayleid_ruin`(埃雷德殘墟,賽羅迪爾省份事件)。現在帝國大道一出城就見帝國亡魂,有了識別度。
- **② 在地任務鏈**(複用既有 `stages` 引擎,**全新 qid、不改既有 favor_***):`chain_kvatch`(賽羅迪爾,3 階:殺帝國亡魂→抵切德納寇→獵米諾陶)、`chain_molagmar`(晨風,3 階:除灰蹦蟲→偵察墓塚→採灰薯)、`favor_haafingar`(天際,殺冰魂)。把單發委託升級為有起承轉合的省份小劇情;**刻意不收在準終局王**(避免 xanmeer/ashfall 的 min12-13 boss)、不與既有地城清剿任務重複。
- **③ NPC 深度**:`npcs.json` 把 marcus/dralasa/seridia 從純風味改掛任務(鏈/委託)→ **每個有 NPC 的省都至少一條在地委託**;8 NPC 各加 `rumor` 指路欄,`ui.npc_panel` 多印一行傳聞(指向同省地城/野外/奇景)。**race 口吻詞表評估後砍掉**(撞既有手寫 greeting + 需改 npc_panel 簽名,審查判負分)。
- **對抗審查修正**:minotaur 原設 d2(為了能在賽羅迪爾野外刷出),但審查模擬發現**d2 帶 bear 級數值會湧入 danger-1 起手大道(lv3 起佔 ~36% 遭遇)、重演雪原偏硬**。改 **d3**:起手大道(max_danger 2)歸 0、旅行至切德納寇(d2→max3)仍 24% 可遇(任務鏈不受影響)——危險度門檻把重數值怪擋在和緩起點外,正是 biome 系統該有的行為。補 `test_heartland_starter_road_stays_gentle` 守門。
- **驗證**:25 測試模組全綠(`test_detailing` 擴充:heartland 分流/creature biomes 合法/任務鏈多階段/rumor/**獎勵守門**(gold≤320/fame≤15/不給 BIS)/起手區和緩)+ heartland 分流抽樣 + 任務鏈推進煙霧 + rumor 渲染 + sim 基線不變 + 對抗審查 workflow。

**城市補全(評估後使用者拍板「按 TES 正史補全各省城市」;城市設計 workflow → 整合 → 對抗審查)**:原本各省只有 1 城 + 1 鎮。依正史補 **13 座標誌城市**,各配考據城主 + 2 NPC(greeting + rumor)+ 服務 + 商店 + 同省雙向連環。
- **賽羅迪爾**:帝都(攝政奧卡托 altmer)、史金格拉德(吸血鬼伯爵哈希爾多 breton,以「夜不見天日」暗示)、切迪納(丹莫伯爵 + 黑暗兄弟會服務)、安維爾(伯爵夫人昂布拉諾克斯,灰狐失蹤伏筆 + thieves_guild)。
- **天際**:白漫城(領主巴爾古夫 + 戰友團 fighters_guild)、風盔城(烏弗瑞克·風暴斗篷)、裂谷城(萊拉 + thieves_guild)、馬卡斯城(銀血氏族)。
- **晨風**:維威克(神王廟活化身司祭)、巴爾莫拉(哈拉魯家族)、奧德盧恩(雷多然家族)。
- **黑沼澤**:赫爾斯壯(An-Xileel 議長,亞龍人聖地)、黑荊棘(堡壘監獄)。
- **設計 workflow**:四省平行設計(讀既有城當品質範本、只用合法 id)+ 考據/合法性對抗覆核;**整合腳本**把代理的單向 links 補成雙向、丟棄 `ald_ruhn→dragon_lair`(**保龍喉峰 degree-1 終局死路**)、逐一驗證同省/degree≥2/城主齊全。
- **對抗審查覆核**:① 兩條 NPC rumor 地理錯置(切迪納指錯洞窟、赫爾斯壯指錯濕地)→ 已泛化修正;② **城市安全網**(9 座 danger-0 新城 + 既有凱瓦奇↔龍橋鎮 d0 邊 → 可零遭遇城躍跨省)經評估**判為設計權衡保留**:城市本是安全樞紐、危險在探索/地城而非通勤、安全城躍路線代價是時間(賽↔天 城躍 16h vs 白隘快線 7h,2.3×),速度/安全取捨仍在。
- **驗證**:25 測試模組全綠(test_world 全不變式:雙向/連通/環/可穿越地城/**聚落必有城主**/商店 id/世界大環)+ 拓樸統計(36 點/59 邊/24 環)+ 無頭煙霧(13 城面板/城主/26 NPC 傳聞/世界地圖/城際旅行)+ 對抗審查 workflow。**加新城純改 world+rulers+npcs JSON**(務必:type=city/danger=0/加 biome/同省雙向 links/`rulers.json` 配城主,否則 test_world 紅)。

**格擋接上技能縮放 + 技能里程碑 Skill Mastery P1(技能健檢→格擋修死→里程碑系統;評估→直作→對抗審查)**:技能健檢實證 22 技能逐一機制效果,抓到**格擋是唯一「等級空轉」者**(減傷寫死 ×0.4、全碼無 `skill("block")` 讀取)→ 先修:新增 `formulas.block_damage_factor` 讓格擋減傷隨技能 ×0.9(生手)→×0.4(精通)、`attack_damage` 改吃 `block_factor`(commit `9371ce9`)。再評估「里程碑加 perk」(理解+設計面板+對抗審查 workflow),使用者拍板四項:**容許溫和真權衡數值 / 門檻 50·75·100 / 接受 1 新欄位 / 零選擇自動解鎖**(不發 perk point、不二選一,守反 min-max)。
- **核心**:`systems/mastery.py`(門檻純由 `base_skill()` 推導 → **零存檔種子**;`kind` 白名單 `_IMPLEMENTED_KINDS` 分派)+ `data/mastery.json`。效果走既有層(`active_effects` shield / 純函式現算 / 仿 `factions.perk_value` 的 `min(cap,…)`),**不碰** 成長漏斗/怪物數值/`sneak_mult` 夜母鏈/資源上限鏈。
- **6 條 MVP(戰/法/盜 × 50/75/100)**:盾陣(block50 命中懲罰 0.15→0.25)、壁壘(heavy_armor75 物理×0.85減傷 + 攻擊耗體×1.20,真權衡)、聖光·溢盾(restoration75 治療溢出×0.6轉護盾、夾**總量** cap)、過載(destruction100 `_power`+0.2/魔耗×1.3,同源代價)、撬鎖名家(security75 撬鎖下限0.30)、辯舌·折服(speechcraft100 說服必成、每NPC一次,唯一新欄位 `persuaded_npcs`)。
- **接點**:`formulas.hit_chance` 參數化 `block_penalty`;`magic.cast`(過載 `_power`/`effective_cost`、溢盾)、`combat`(壁壘物理減傷 + 攻擊耗體)、`dungeon.effective_pick_lock_chance`、`dialogue.persuade`、`progression._on_skill_increase` 解鎖播報、`ui` 角色卡里程碑面板 + `legacy` 結算「精通」行+計分。
- **對抗審查覆核修掉自身引入 3 問題**:① 溢盾 cap 原只夾單次 → 可戰前連施疊到 2.06×血上限(改夾**總量** + `source:"overheal_ward"` 標記);② `run_battle` 原不在入場清 `active_effects` → 戰外造的盾洩漏進下一場(在 `_prep_phase` **前**加 `player.active_effects.clear()`);③ `kind` 打錯會「加分+播報卻零效果」沉默 foot-gun(白名單過濾)。
- **驗證**:26 測試模組全綠(`test_mastery` 17 測試)+ `sim_assassin` 零位移 + 壁壘/過載**勝率 gate PASS**(過門檻勝率不降)+ 無頭煙霧 + 存檔向後相容。commit `8ccbf56`。
- **後續(P2/P3,路線已拍板)**:P2 引入持久 `mastery_*_bonus` 加成層(吸血鬼模式)與更多真權衡戰鬥型(**逐條跑 sim + 非 boss 精英秒殺率覆核**);P3 純改 JSON 補三系密度(優先冷門技 marksman/light_armor,避免 sneak 過載)。**↓ 已於下節「Skill Mastery v2」全數實作。**

**技能里程碑 v2:達門檻二選一 + 持久加成層 + 全 23 技能密度(里程碑級;P0–P5 五階;評估→直作→對抗審查)**:把 P1 的「6 條·零選擇自動解鎖」升級為**全 23 技能各 ≥1 節點(共 24 節點 / 48 選項)**,每節點**達門檻二選一**(使用者拍板的支柱級改動:重新引入 build 能動性),並補上**持久 fortify 層**。**使用者另拍板「刺客 apex 解禁」**:最終成形刺客**可無傷清小遭遇地城**(`sneak_mult_bonus` 影刃),平衡改靠**群體規模反制**(>3 敵潛匿大減)而非秒殺率上限。
- **資料結構 v2(`data/mastery.json`)**:節點 = `{id:"<skill>_<thr>", skill, threshold, options:[{opt_id,name,kind,<params>,desc}, …]}`;`mastery._nodes` 容忍 legacy flat 列。退化單選項節點 → 直接授予(不打擾)。`unlocked()`/`_defs()` 回**攤平 option**(帶 skill/threshold/node_id),既有 UI/legacy/achievement 消費端零改。
- **存檔模型(`models/character.py` +4 欄)**:`mastery_choices`(node_id→opt_id,**唯一權威、永久、進存檔**)+ `mastery_skill_bonus/attr_bonus/resist`(**recompute-on-load 快取**,同 equip_* 模式;`stats.recompute_mastery_bonuses` 由 choices+JSON 決定性推導)。`attr()/skill()/magic.entity_resist` 疊加第三層;`base_*` 不動(**鐵律:fortify 不回饋門檻**,門檻只認 base_skill)。`to_dict` 涵蓋 4 欄,`from_dict`=`cls(**d)` 自動向後相容。
- **解鎖→二選一流程**:pending = 達門檻(base)∧ 未選 ∧ 有可選 option(**衍生,非儲存佇列**)。`_drain_mastery_choices` 在**升級畫面 + game_loop 回城頂**呈現(**絕不在戰鬥中** → 避 `run_battle` 全域 patch `ui.menu` 汙染);可「稍後再選」延遲。`progression._on_skill_increase` 改發 `mastery_choice_ready` 事件(不再自動授予)。getter 全改 `_chosen_option_by_kind`(只認已選;未選回中性,絕不崩)。
- **舊存檔遷移(政策:留 pending,不自動指派)**:`progression.ensure_mastery_choices`(`state.from_dict` 接線)補欄 + 清陳舊選擇 + 重算 fortify。達門檻舊存檔 → pending(下次回城二選一),getter 中性 → **不崩、不誤效**。
- **內容(36 kind;盡量泛化複用)**:`weapon_mod`(命中/威力/破甲/反作用/耗體/命中附狀態,target=武器技能;**威力以 flat 補傷加在偷襲倍率之後** → 非潛行 +X% 但不放大偷襲)、`spell_mod`(吸收 spell_overload,學派 power/cost/命中附狀態)、`summon_mod`、3 個 `*_fortify`、及一眾針對性 kind(block_riposte/temper_*/repair_floor/potion_potency/enchant_potency/poison_charge/fear_on_hit/regen_on_low/passive_armor/merchant_bonus/restock_bonus/evasion_bonus/vanish_floor/sneak_mult_bonus/vanish_relentless/approach_bonus/armor_sneak_relief/prep_bonus/recon_resist_read/pick_no_break/intimidate_floor)。每新 kind = 白名單 + getter + 一處呼叫端。
- **刺客 apex 平衡(群體反制 + solo boss 夾限)**:`sneak_mult_bonus`(影刃 sneak100,×1.5 偷襲)+ `vanish_relentless`(連環踏影 sneak75,免重複遞減 + 解每場上限)→ 對 ≤3 敵/精英無傷秒殺(刻意)。反制:① `STEALTH_APPROACH_HORDE`/`RESTEALTH_HORDE_PENALTY`(**>3 敵潛匿/隱遁陡降**:潛近 72%→34%→5%、連環隱遁 71%→13%→5% @ 3/4/5 敵;4 敵群戰死亡率 27% vs 小遭遇 ~0%);② **`SOLO_SNEAK_DAMAGE_CAP_RATIO=0.40`**(`solo` 目標偷襲單擊夾在血上限 40% → **絕不一刀秒 boss**;apex 仍可隱遁循環無傷清、只是多刀)。`estimate_sneak_damage` 同步含影刃/weapon_mod + solo 夾限(偵查估傷與實戰一致)。
- **對抗審查覆核(4 確認,逐一修)**:① **最壞 apex 一刀秒 solo boss**(玻璃雙持+聆聽者夜母+淬鍊5+影刃→95%;**部分既有**:temper+夜母本就秒 vampire_lord)→ 使用者拍板「solo boss 須存活」→ 加 `SOLO_SNEAK_DAMAGE_CAP_RATIO` 夾限(5 隻 solo boss 單擊秒殺全 0%);② **sim 覆蓋缺口**(原 apex lambda 漏 DB 階級/玻璃/淬鍊 → 假 0%)→ 補最壞合法 build 對全 solo boss;③ **`vanish_floor`/`merchant_bonus` 多來源只取第一個**(acro 0.10 蓋過 sneak 0.15)→ `_chosen_options_by_kind` 聚合(floor 取 max、議價相加);④ **restock `max(1,…)` 抹掉「擲 0=缺貨」稀缺**(本 diff 引入)→ 保留 0 擲。
- **驗證**:43 測試模組全綠(`test_mastery` ~55 測試:二選一/永久性/pending 衍生/持久層/no-bootstrap/白名單惰性/各 kind getter+實戰/向後相容/>3 反制/**solo boss 反一刀**/多來源聚合)+ `sim_assassin` 擴充(契約① 小遭遇+精英秒殺成立、契約② >3 反制 + solo boss 全存活、非潛行不破)+ 無頭煙霧(apex 選擇→sheet 渲染→實戰勝利→存讀檔)+ 對抗審查 workflow(4 確認全修)。**鐵律**:調 `sneak_mult_bonus`/`SOLO_SNEAK_DAMAGE_CAP_RATIO`/horde 常數務必重跑 sim;新 kind 走白名單+getter+呼叫端、多來源用 `_chosen_options_by_kind` 聚合;新節點(既有 kind)純改 JSON。

**頂級裝備擴展:魔族/龍鱗/龍祭司 三套頂裝 + 全武器頂層 + 具名神器(稀有素材鍛造,困難取得;評估→使用者拍板→直作)**:在現有頂層(重=ebony/輕=glass/布=archmage)之上加一階。評估發現裝甲套裝/鍛造全資料驅動 → **幾乎純 JSON**(唯一程式碼 = `smithing._MATERIAL_INGOT` +3 行讓新材質可淬鍊)。
- **三套頂裝**(`armor.json` 15 件 + `armor_sets.json` 3 條,機制全自動套用):**魔族 Daedric**(重,cuirass AR30,套裝 +60 生命)、**龍鱗 Dragonscale**(輕,cuirass AR24,套裝 +25 火抗)、**龍祭司 Dragonpriest**(布,兜帽 +20 毀滅、其餘三件 magicka 附魔 + 套裝 +110 魔力 → 全套 +200 魔力 + 兜帽 +20 毀滅)。
- **全武器頂層 Daedric**(`weapons.json`,補現有頂層覆蓋稀疏):匕首/劍/錘/斧/弓 5 把(`material:"daedric"` → 可淬鍊)+ `daedric_staff`(毀滅,drop-only)+ **具名神器 `mehrunes_razor` 魔銳茲之刃**(匕首 dmg16 + 電擊附魔 25,ancient_dragon 保證掉)。
- **稀有素材鍛造(TES 正史,困難取得閉環)**:`items.json` 加 `daedra_heart`(魔性之心,value 500)/`dragon_scale`(龍鱗,value 400),**drop-only**(dremora_lord/ancient_dragon `treasure` 保證 + dremora/dragon `loot` 機率)。`recipes.json` 19 配方 skill_req 90、inputs=基礎錠+稀有素材(Σ值≥產出 過 arbitrage;龍鱗走皮料 wolf_pelt 豁免)。`_MATERIAL_INGOT` +3(daedric→ebony_ingot、dragonscale→dragon_scale、dragonpriest→bolt_of_cloth)→ 全可淬鍊。
- **平衡**:新頂武器傷害上升,但既有 `SOLO_SNEAK_DAMAGE_CAP_RATIO=0.40` 仍護 solo boss(含 mehrunes_razor 附魔,夾在 dmg 末端)→ sim 覆核 **solo boss 全 0% 秒殺、精英仍 95%**(力量幻想不變)。頂套生存力刻意強(endgame BIS),套裝單一效果有界。
- **驗證**:43 測試模組全綠(新增 `test_top_tier_set_bonuses`/`test_top_tier_craftable_and_reachable`/**`test_loot_ids_valid`** 補既有掉落 id 守門缺口)+ `sim_assassin`(新武器 + apex 不破 clamp)+ 無頭煙霧(鍛全套→穿戴→套裝加成→淬鍊→裁縫→渲染)。**加新頂裝純改 6 JSON**(`armor`/`armor_sets`/`weapons`/`items`/`recipes`/`dungeons`+`bestiary`);新材質可淬鍊才碰 `_MATERIAL_INGOT`;稀有素材 value 須高到 Σ≥產出。

**法師裝備微調(使用者拍板,純 JSON)**:① **大法師套裝加第二取得途徑** —— `mg4`《奧術研究》(rank 3→晉升大法師)獎勵改為四件大法師套裝(原帝都商店途徑保留);② **學徒套裝**兜帽↔便鞋附魔互換(兜帽→+6 毀滅、便鞋→+10 魔力上限;套裝魔力總額不變);③ **大法師套裝**兜帽↔便鞋附魔互換(兜帽→+10 毀滅、便鞋→+15 魔力上限;全套 +10 毀滅總額不變、只換承載件);④ **龍祭司兜帽** +30 魔力 → **+20 毀滅**(故全套魔力 230→200、改提供毀滅技能加乘)。`test_top_tier_set_bonuses` 龍祭司預期值同步 230→200。

**飾品實戰崩潰修正(對抗審查後順手抓到的既有 bug)**:飾品(amulet/ring,無 `armor_rating` 鍵)戴上後,`inventory.effective_armor_rating`(唯一呼叫端=`combat` 玩家受物理擊時)原以 `["armor_rating"]` 直取 → **戴戒指/項鍊後第一次被物理擊中即 `KeyError` 崩潰**。改 `.get` 略過飾品(計 0 護甲)、`worn_armor_rating` 一併防禦化;補回歸測試(還原 HEAD 版可重現)。commit `a10aaeb`。

**反 min-max 補洞:說服/撬鎖/行竊接上 practice 成本(使用者點名三個零成本刷技能漏洞 → 評估 workflow → 直作 → 對抗審查)**:使用者指出三處名實不符 ——「偷竊沒處罰、開鎖沒代價、可一直說服刷口才」。先跑**評估 workflow**(調查→設計→對抗驗證),確認三者皆 `confirmed_gap`,且挖出共同根因:**遊戲早就替每個技能定好 `practice` 價碼**(`data/skills.json` 每技能 `practice`={xp,fatigue,hours},訓練師 `action_practice` 就按此收費),而行竊/撬鎖/說服是**繞過該價碼的實戰捷徑**(同樣 xp、零時間、零體力)。修法=讓三者統一付各自技能的 practice 成本。
- **核心**:`progression.practice_cost(char, gd, skill_id)→(xp, hours, tired)`(共用「體力不濟 xp 減半」模型:扣體力、回傳 xp/時數/tired;**呼叫端**負責推進時間與 `use_skill`)。`action_practice` 重構為呼叫它(單一真實來源,行為逐位等價)。
- **一次練多小時(使用者要求)**:`action_practice` 選技能後先問時數(`ui.ask_int` 1–24,預設=體力足以全效的小時數=`fatigue//fat_cost`),迴圈跑 N 輪 practice(每輪 1 小時),逐輪扣體力/推進時間/累積 xp,回報含「其中 X 小時體力不濟、成效減半」(沿用 `practice_cost` 的 tired 半額模型,非新經濟);**滿級(`base_skill≥SKILL_CAP`)即收手**,不空耗時間/體力。里程碑二選一仍走 pending(回城迴圈頂 `_drain_mastery_choices` 消化),批次跨門檻不吞。回歸測試 `test_practice_batches_multiple_hours`/`test_practice_stops_at_skill_cap`(`test_practice_cost.py`)。
- **三處系統函式**(簽章不變,皆被測試以位置引數呼叫):`crime.steal_item` 付 sneak practice 成本 + **得手才給潛行 xp**(被抓 `skill_events=[]` → 杜絕「故意被抓刷潛行」);`dungeon.pick_lock` 真實擲骰付 security practice 成本(**塔之鑰仍免體力、免耗時 `hours=0`**,守招牌);`dialogue.persuade` 付 speechcraft practice 成本(**折服必成路徑也付**,非免費必成)。三者回傳加 `hours/tired`。移除 `LOCKPICK_XP`/`PERSUADE_XP` 常數改讀 practice。
- **三處呼叫端**(`main.py`):`action_shop` 行竊 / `_resolve_container` 撬鎖 / `action_talk` 說服 —— 各 `state.time.advance(r["hours"])` + tired 提示。
- **對抗審查覆核(1 confirmed,擋下 1 錯誤修法)**:四個「exploit」發現其實同一根因、驗證者**分裂**。3 個判 `not_a_bug`(理由一致且嚴謹:tired 每次仍付「1 不可逆遊戲小時」、是與訓練師 `action_practice` 完全一致的既定經濟、好感有效值封頂 100;建議的「fatigue=0 擋下動作」會破壞 tired 半額回歸測試、背離訓練師對等、且若寫成 `return(0,0)` 反而**重開零『時間』成本重試洞**)。**採納其結論、擋下該錯誤修法**。1 個判 `isReal/major` 屬實:`_resolve_container` 的 `while True` 是唯一**自動重試**迴圈(最低摩擦刷取)。→ 只加**安全閘門**:撬鎖失敗且已 `tired`(體力耗盡)即**收手退出**(讓體力成為「單場撬鎖次數」的真實上限,非半額無限重試),不動 `practice_cost`、不破任何測試、不開新洞。
- **驗證**:27 測試模組全綠(新增 `test_practice_cost`:11 條,含**反向驗證**——還原舊碼會紅——與**接線煙霧**:三入口真實推進時間、撬鎖耗盡停手)+ `sim_assassin` 零位移(本輪不碰戰鬥)。**鐵律**:這三個動作的 xp/時間/體力**只走 `progression.practice_cost`**;調平衡改 `data/skills.json` 各技能 `practice`(純 JSON);tired→0.5× 是刻意的退化狀態(與訓練師一致),別誤當漏洞去擋。

**反 min-max 補洞 第二輪:製作/維護系也接上 practice 成本(使用者要求「繼續找相同漏洞」→ 全碼搜尋 workflow → 直作 → 對抗審查)**:跑了**全碼 11 領域搜尋 workflow**(枚舉每個 `use_skill` 呼叫端 + 跟著錢走),對照判定基準(零成本零風險/失敗給/無限資源/可逃避/弱敵刷防禦 vs 時間/資源閘的既定 grind)。結果:
- **確認同類漏洞 → 已修**:製作/維護三系與行竊/說服同型(零時間零體力刷技能,只是另外消耗材料)—— `alchemy.brew`(煉金)、`enchanting.enchant_weapon/armor/jewelry`(神秘)、`action_repair` 修理鎚分支(護甲修理)。全部接上各技能 practice 成本(`progression.practice_cost`,xp 改為 practice 率、tired→×0.5、brew 失敗 ×0.5),呼叫端推進時間 + tired 提示。**至此遊戲所有 learn-by-doing 技能用途皆付時間/資源閘**(戰鬥系靠 HP 風險+回合、魔法靠魔力、旅行/說服/行竊/撬鎖/製作靠 practice 體力+時間、商貿靠金幣+物品)。commit 見下。
- **誤報已擋(對抗審查判 not_a_bug)**:wayshrine/黑沼澤希斯特/營火 等「免費治療事件」(時間閘、不練任何技能、被 action_rest 主導)、雲遊學者(其實付 40 金)、付費訓練師(金幣閘)、tired 半額(刻意) —— 皆既定經濟,**勿**去「修」。
- **驗證**:27 模組全綠(`test_practice_cost` 擴至 15 條,加 brew 成功/失敗、enchant、repair 的體力+時間斷言)+ 對抗審查(逐路徑確認無 KeyError、smith 付費修理分支未被誤改、簽章不變)。
- **相異漏洞:煉金套利/無限金幣 → 已修(使用者拍板「Skyrim 式商店庫存」)**:原本商人無限供貨 → 可買廉價材料 `imp_stool`+`canis_root`(共 12 金)→ brew 3 回合麻痺毒(`synth` poison `value=max(15,turns×40)=120`)→ 賣 86 金,**淨賺 +74/次、瞬間無限**。修法=從**供給側**掐死:見下「Skyrim 式商店庫存」。

**Skyrim 式商店庫存(使用者拍板:有限數量 + 定時補貨 + 補貨品項有變化)**:堵煉金套利的根因——商人不再是無限供貨機。
- **核心**(`systems/world.py`):每商品有**有限數量**、`RESTOCK_HOURS=72` 遊戲小時**定時補貨**、補貨量隨價值分級隨機(`_restock_qty`:廉價 1–6、中價 0–3、高價 0–1 → 可能個別缺貨,故「不同次補貨品項有別」)。`ensure_stock`(進店時呼叫,首訪或逾期才補)/`stock_qty`/`take_stock`(買或偷成功才扣)/`in_stock_items`(qty>0 才上架)。
- **存檔**:新增 `Character.shop_stock`(loc→{item:qty})、`shop_restock_at`(loc→絕對小時),dataclass 預設 {} → 向後相容(舊存檔首訪自動初始化);皆進 to_dict。**持久狀態**(與 active_effects 不入檔相反:庫存須跨存讀檔保留)。
- **接點**(`main.py action_shop`):進店先 `ensure_stock`;買/偷改用 `in_stock_items`(顯示 ×數量)、成功後 `take_stock` 扣減、空貨架提示;**賣出維持不變**(賣掉的東西不加回庫存 → 不能賣回再買回)。
- **效果**:全圖單輪麻痺毒材料供給 imp_stool 27/canis_root 13 → **每補貨週期上限 13 瓶**(且需跨城採買、耗時)→ 無限瞬間套利消滅、降為有限的時間閘收入。**加商店物品純改 world.json `merchant_stock`(目錄)**;調補貨量/週期改 `world._restock_qty`/`RESTOCK_HOURS`。
- **驗證**:28 測試模組全綠(新增 `test_shop`:有限/售罄/補貨時機/套利受供給+時間閘/存檔向後相容/購買煙霧扣庫存)+ 對抗審查(存檔相容、邊界不誤扣、決定論不破 test_seed、套利確認被堵)。

**煉金材料採集全覆蓋 + 雜貨加工(製作系統)(使用者要求,純資料 + 一個小系統)**:使用者點出兩個內容缺口 ——「煉金材料只能買?」「狼皮等雜貨有用嗎?」。
- **採集全覆蓋(Task1,純資料)**:原本 15 種煉金材料只有 7 種能在野外採/獵,其餘只能買。補上後**全部 15 種都有野外取得途徑**:`giant_rat` 加掉 `charred_skeever_hide`;`herb_patch`(全圖)+帝王蝶翼、`morrowind_forage`(晨風)+犬根、`blackmarsh_forage`(黑沼澤)+顛茄;新增 `cyrodiil_forage`(賽羅迪爾農田 → 小麥/大蒜/紅蘋果)。野採走 `events.json`(`trigger.contexts:["explore"]` + 可選 `provinces`),**加採集點純改 events.json**。
- **製作系統(Task2)**:第一個泛用「配方加工」系統 —— `data/recipes.json`(`inputs`/`output`/`station`/`skill`)+ `gamedata.recipes` + `systems/crafting.py`(`recipes_for_station`/`recipes_by_material`/`can_craft`/`missing_inputs`/`craft`)。`craft` 消耗背包原料 → 產**真實物品**(非合成 id),並付該技能 practice 體力+時間(與其他製作系一致,不另闢零成本造物)。接點:`main.py action_craft`(在鐵匠處 `station="smith"`)+ 市集區「製革加工」入口(`armorer` 服務時)+ dispatch。**選單兩層**:第一層選材質系列(皮革/鐵/鋼/布/精靈/矮人/玻璃/黑檀/魔族/龍鱗/龍祭司布,順序依 recipes.json = skill_req 由低到高;`recipes_by_material` 依產出物 material 分組,系列中文名在 `crafting.MATERIAL_SERIES_NAME`),點進系列才列該系列裝備(`_craft_series`)。**加配方/系列純改 recipes.json**(新材質補 `MATERIAL_SERIES_NAME`,缺名退回 key)。**MVP 4 配方**:狼皮×2→皮護腕/皮靴、×3→皮盔、×5→皮甲(獵狼→自製皮甲的獵人玩法)。
- **雜貨活化**:`bone_meal`(骨粉)從 `items.json` 雜貨改列 `ingredients.json`(成煉金材料,restore_fatigue 6;**move 非 dup**,因 gamedata 合併 ingredients 最後 merge)；`wolf_pelt` 經製革→皮甲系列。**零新存檔欄位**(配方走背包物品)。
- **平衡**:狼皮不在任何商店(僅獵狼掉落=有限+耗時)→ 製作非無限金幣;皮甲配方多半「賣價低於原料生賣」,皮甲 +9 屬邊際且獵殺/工時閘住;`bone_meal` 為恢復系材料(煉不出毒藥)→ 不餵毒藥套利。
- **驗證**:29 測試模組全綠(新增 `test_crafting`:配方合法性/加工消耗產出+practice 成本/材料不足零成本/station 閘/**15 材料全有野外途徑**/bone_meal 成材料/鐵匠處煙霧)+ 對抗審查(bone_meal 搬移無破壞、events province 過濾、craft 邊界、無新套利/存檔欄位)。

**領主區(宮廷)Phase 1:謁見領主(使用者拍板「以 Oblivion/Skyrim 為參考規劃,預期後續加攻城戰」→ 先做 Phase 1 + 立藍圖)**:讓原本**純顯示**的 `rulers.json`(21 城主)「活起來」—— 第 4 個城區。
- **接點**:城市選單第 4 區 `領主區 👑`(僅 city/town、有領主、非吸血鬼社交封鎖時出現)→ `action_court` 謁見。`ui.court_panel` 顯示考據背景(blurb)、種族、駐軍兵力、時局(大空位·各城自治);`_court_reception` 依 fame/infamy 給 4 級接待語氣(Oblivion 風:無名/揚名/惡名/例行)。
- **零新狀態**(純顯示;謁見不耗時、無交易)。**加領主互動沿用此入口**:Phase 2+ 在 `court` district list / `action_court` 內加選項。
- **驗證**:30 測試模組全綠(新增 `test_court`:接待分級/謁見顯示城主/無領主安全)。
- **藍圖(見 §6「城戰/領主區路線」,已立為正式分層)**:Phase 2 領主委託 + 武士冊封(Thaneship);Phase 3 政治/選邊(`politics.json`);Phase 4 攻城戰(複用 `combat` 群戰)。

**領主區(宮廷)Phase 2:領主委託 + 武士冊封(Thaneship)**:領主從「能謁見」進到「能差遣、能效忠」。
- **領主委託**:走既有任務引擎,`source:"ruler"`(不漏進告示板/公會);`rulers.json` 的 `quests:[...]` 列各領主委託線(依序開放,有進行中則先做完);`quests._complete` 對 ruler 委託**反查領主目錄**把 `reward.standing` 記進 `city_standing[該城]`(完成事件加 `standing_loc`,`_report_quests` 印「城邦功勳 +N」)。
- **武士冊封(Thaneship)**:`systems/court.py` —— `city_standing` 達 `THANE_STANDING(3)` → 受封武士(記 `char.thaneships`)。`make_thane` **冪等**(重複受封不重發信物/侍從,防刷);授**信物**(`rulers.thane_gift`)+ **侍從 housecarl**(`rulers.housecarl`,複用 companions,受 `MAX_PARTY` 限,滿則婉拒)。
- **武士特權**:`guard_confrontation` 開頭 —— 身為**該省**某城武士且賞金 `≤ THANE_BOUNTY_FORGIVE(100)` → 衛兵放行 + 清賞金(大罪 >100 仍追緝;審查評為有界特權、非漏洞:偷竊已耗體力+時間、商店有限)。
- **新 Character 欄**`city_standing`/`thaneships`(dataclass 預設、進 to_dict、向後相容);`ui.court_panel` 加顯示功勳/武士身分。**MVP 內容**:布魯瑪 2 委託(殺6狼+1、清切德納寇+2 → 滿 3 受封;信物精靈劍、侍從盾女)。**加領主委託純改 rulers.json `quests` + quests.json(`source:ruler`+`reward.standing`);加侍從/信物純改 rulers.json**。✅ 其餘城已由 `court.generate_ruler_commissions` 程序化補齊(見 §6 #0「全城武士化」),故 33 城主全可受封;重點城(帝都/白漫/維威克)另有手寫考據委託覆寫。
- **驗證**:30 測試模組全綠(`test_court` 擴充:委託依序開放+完成累積功勳/武士冊封信物+侍從+冪等/賞金寬待/存檔向後相容)+ 端到端煙霧(經真實 `action_court` 選單:接委託→完成→受封→賞金寬待)+ 對抗審查(修掉自身 2 低severity:功勳無畫面回饋、make_thane 信物非冪等)。

**城戰(Phase 3+4 合併:政治立場 + 選邊 + 攻城戰)(使用者拍板:城為單位、各城主自有立場;Phase 3 直接併進 Phase 4)**:領主區從「能差遣」升到「能征伐」—— 完整的城邦戰爭迴圈。核心在 `systems/politics.py`。
- **城為單位的立場**:21 城各有 `stance`(rulers.json:`imperial` 復辟 / `independent` 獨立 / `neutral` 觀望),依各城主考據指派、**刻意跨省混合**(如天際:獨立溫德赫 + 中立白漫 + 復辟海芬古)。玩家在領主區「宣誓效忠」一個大義(`char.allegiance`)→ `relationship`:同=盟、對立=敵(可攻)、中立=觀望。
- **攻城=混合制(使用者拍板:不同戰鬥方式、盡量運用各種技能)**——兩階段:
  - **① 圍城方略(`SIEGE_OPS`,7 核心)**:技能門檻開放的作戰選項,讓**潛行/社交/工具/魔法系**也有攻城用途:偵查(scout)/夜襲(sneak)/撬側門(security)/勸降(speechcraft)/賄賂(mercantile)/法術轟城(destruction)/召喚襲擾(conjuration)。各耗時間+資源(金/魔/體)、**每役每略限一次**(`char.siege_ops` 持久),成功則 `deplete_garrison` 削守軍;風險型(夜襲/撬門)依技能擲成功。
  - **② 輕量化強攻**:單場 `run_battle`(守軍數 `assault_force(剩餘守軍)` + 守將 boss);勝 → `conquer` 翻轉 `city_faction` + 重新駐軍 + 清 siege_ops + 聲望。守軍削得越少 → 強攻越輕鬆 → 方略與強攻成 build 取捨。
- **平衡(sim 背書)**:`assault_force` 隨剩餘守軍單調升 —— **小城(g≤120)可強攻硬下;大城(g200-400)須靠方略削弱**(帝都 400 須廣技能佈局才打得下,純戰士只能靠 recon/bribe 微軟化 → 真·全技能里程碑)。調平衡改 `politics.SIEGE_OPS`/`assault_waves`(⚠ 強攻後改**波次決戰**並移除 `assault_force`,見下『城戰精修:波次強攻 + 佔領治理 + 旗號』)。
- **新 Character 欄**`allegiance`/`city_faction`/`garrison_current`(dataclass 預設、進 to_dict、向後相容;動態戰況懶初始化自 rulers 種子)。接點:`action_court` 加宣誓效忠/發動攻城、`court_panel` 顯示立場·關係·現存駐軍、hub 捕捉攻城 `died`。
- **新 Character 欄**`allegiance`/`city_faction`/`garrison_current`/`siege_ops`(皆 dataclass 預設、進 to_dict、向後相容、懶初始化)。
- **防 farm**:圍城方略 once-each(不可重複)、強攻單場(無波次可分段刷)、方略耗資源為淨流出、強攻 fled 不發戰利 → 杜絕重刷(初版波次模型曾被審查抓到「清波→逃→重刷」MAJOR,改混合制後結構性根治)。
- **驗證**:31 測試模組全綠(`test_politics`:立場跨省混合/關係/選邊/僅敵可攻/方略技能門檻+once-each/扣資源/風險型失敗仍計次/強攻單調+夾限/conquer 清 ops/攻城煙霧 方略→強攻 勝-死-逃/存檔向後相容)+ 平衡 sim + 端到端煙霧(經 action_court:宣誓→7 技能方略軟化→強攻破城)+ 對抗審查(無真 bug、farm 已封堵;順手修 gold 夾 0、刪死碼 base_garrison)。
- **後續(藍圖 §6 #0;此里程碑刻意未做)**:佔領後收稅(週期金幣,複用補貨時間鉤子)/ 駐軍隨時間重建 / 自走 AI 陣營戰爭 / 攻下後可安插自己為領主 / 公會與大義綁定 / 武士所在城翻給敵方時 Thane 特權暫停。**加城/改立場純改 rulers.json**。

**城戰精修:波次強攻(β)+ 佔領治理(A3 自任領主/冊封總管)+ 旗號 token(B1)(使用者拍板 4 點回報 → 評估解法 → β/A3+B1)**:玩家點出四個名實不符 ——「30 兵打贏上百兵城不真實」「守軍削了沒區別」「打下城只能加駐軍」「領主沒變、立場翻了但對話內容沒翻」。根因:強攻被夾在 2–8 敵(`assault_force` clamp),守軍數與戰鬥脫鉤;且 court/對話 token 讀靜態 rulers.json、無一條讀 `city_faction`。
- **β 波次強攻(`_siege_assault` 重寫)**:守軍折算成 `politics.assault_waves(remaining)=ceil(殘存/WAVE_GARRISON=50)` 波(至少 1),**每波一場 `run_battle`**(`WAVE_GUARDS=4` 守兵,**末波加守將 boss**),**波間不恢復**傷勢/體力/魔力(消耗戰)、傷亡每波 `apply_casualties` 永久折損、可鳴金收兵。**每破一波 `deplete_garrison(WAVE_GARRISON)` 永久削守軍** → 中途退兵保留戰果、改日波數更少;削弱(方略/大軍壓境)直接砍波數 → 上百守軍非少數人可硬吞(治 #1#2)。**移除 `assault_force`**。防 farm:每波永久削守軍 → farm 受守軍總量上限封頂(g/50 波即破城)、且永久傷亡為代價,非無限。
- **A3 佔領治理**:攻下的城你即**事實領主** —— `action_court` 對 held 城以 `_governing_ruler` 合成顯示**你(征服者)**或**冊封的總管**為領主、reception 改佔領語氣(取代被推翻的舊領主,治 #4a「領主沒變」)。新增**冊封/召回總管**選單 + `_appoint_steward`:`politics.appoint_steward/recall_steward/steward_of/has_steward`,一名親衛只能坐鎮一城(分派各領地)。總管效果:`effective_unrest_decay = UNREST_DECAY − STEWARD_UNREST_RELIEF(6)` 接進 `tick_tax` → 有總管 decay 4 < regen 6 → **淨 +2 守軍自給**(無總管淨 −4 緩衰);`has_steward` 驗親衛仍在 `companions`(陣亡不殘留加成)。新 Character 欄 `stewards`(dict、預設 {}、進 to_dict、`cls(**d)` 向後相容)。治 #3「只能加駐軍」。
- **B1 征服感知旗號**:`politics.current_banner_label(char,gd,loc)` —— `loc∈city_faction/world_faction → cause_name(該大義)`,否則靜態 `bloc_label`;`dialogue._interp` 的 `{bloc_label}` 改走它 → 獨立派打下布魯瑪後友善問候由「**帝國軍團**記得肯出力的人」變「**獨立同盟**記得…」(治 #4b「立場翻了內容沒翻」)。
- **驗證**:54 測試模組全綠(`test_politics` 改 `assault_force`→`assault_waves` 測試 + 新增波次多波/中途退兵保留折損/總管減叛亂自給/陣亡親衛無加成/旗號征服翻轉/朝堂顯示你或總管為領主;`test_warband` 永久折損測試把守軍折至一波)+ `sim_worldwar` 全綠(改 politics 常數;AI 戰爭收斂/中立緩衝/反攻/選邊不雪球達標)+ 無頭煙霧(征服後朝堂渲染你/總管皆無 traceback)。**調平衡改 `politics.WAVE_GARRISON/WAVE_GUARDS/STEWARD_UNREST_RELIEF`;加治理選項改 `action_court`。**

**招兵買馬 階段一(城戰的金幣/領袖路線,與技能圍城方略互補)(評估定案 → 分階段、先核心)**:讓「有錢有勢的統帥」也能攻城,不只靠個人技能。核心在 `systems/warband.py`。
- **資格門檻 `is_warlord`**:你是**領主**(持武士銜 / 已征服城)或**首領**(任一公會掌門)才能招兵買馬。
- **營地 `camp`**:資格達成後可**野外紮營**(移動)或**佔領已肅清地城**(`loc.type=="dungeon"` 且 `dungeon in cleared_dungeons`)當據點;`action_warband`(hub「人物」群「整軍經武 ⚑」)建營/移營/招募/檢視。
- **兩級軍制**:**親衛/將領**=companions(新增 `ranger` 弓手親衛;旅店招);**軍隊/士兵**=抽象 `char.soldiers`(營地花 `SOLDIER_COST` 招、夾 `MAX_SOLDIERS`)。`footman`(`troop:true`)是士兵上場兵種,**`_hire_mercenary` 過濾 troop 故不可在旅店免費招**。
- **攻城整合**:① **大軍壓境** op(`action_siege`,`soldiers>0` 才出、每役一次記 `siege_ops["army"]`、以 `army_soften`=士兵×3 削守軍 → **非技能的軟化路**);② **實戰援軍**:`_siege_assault` 以 `companions=char.companions+[footman]*fielded_soldiers`(夾 `FIELD_CAP`)讓親衛+士兵一同上陣。
- **平衡(sim 背書)**:純戰士無軍隊只能取小城(G250/400=0%);帶 30 士兵+親衛 → 取中城 100%、帝都可成(~42%)。金幣(招募)+ 領袖門檻 gate,帝都仍須全套投入。
- **新 Character 欄**`soldiers`/`camp`(預設、to_dict、向後相容)。**驗證**:32 測試模組全綠(`test_warband`:門檻/營地/招募夾限/上場+壓境/footman troop/存檔/攻城整合煙霧)+ 平衡 sim + 端到端煙霧(領主→紮營→招募→大軍壓境+援軍破城)+ 對抗審查(無真 bug、footman 無副作用、無新漏洞)。
- ✅ **階段二(已做,見下「招兵買馬 階段二」)**:軍餉(週期金幣沉/付不出逃兵)+ 永久傷亡 + 親衛複合來源(warlord 將領 veteran)。

**招兵買馬 階段二(戰爭的代價:軍餉 + 永久傷亡 + 親衛複合來源)(直接續階段一,堵「士兵=零成本永久常駐戰力」的反 min-max 破口)**:把軍隊從「招一次永久免費」變成**須持續維持、會折損**的資源。核心仍在 `systems/warband.py`。
- **A 軍餉(週期金幣沉)**:`WAGE_HOURS=168`(一週)、`WAGE_PER_SOLDIER=5`;`tick_upkeep(state)` 掛 **game_loop 每圈頂端**(同 `vampirism.update`/商店補貨的時間鉤子,只讀 `absolute_hours` 不推進時間)。新 Character 欄 `wage_due_at`(下次發餉絕對小時;dataclass 預設 0=無兵/未計餉,向後相容、進 to_dict)。邏輯:**首次有兵給一週寬限** → 之後足額付餉扣金(`paid`),**付不出 → 付得起的份額領餉、其餘未領餉者半數離營**(`desert`,`max(1,(unpaid+1)//2)`);**無兵則清週期**(下次招募重新寬限);可一次補結多個跳過的週期(長途旅行/久候)。經濟:招滿 30 兵 1200 金,週餉 150 金(≈招募費 12%/週)→ 須持續收入(攻城收稅尚未做,先靠探索/任務;這也是後續「佔領收稅」的天然動機)。
- **B 永久傷亡**:攻城陣亡的親衛/士兵**不再戰戰滿血復生**。`run_battle` 新增可選 `casualties` out-param(給定 list → 戰後把**陣亡盟友的來源 id** 填入;一般戰鬥不傳 → 同伴照常復生,行為零變更):用 `roster=[(cid,Creature)]` 記下上陣盟友(**召喚物不在 roster**),四個出口(victory/fled/dead)前 `tally_casualties()` 查 `is_alive` 收錄陣亡者。`warband.apply_casualties(char,gd,casualties)→{officers:[名],soldiers:n}`(親衛移出 companions、士兵 soldiers 遞減夾限 ≥0)。`_siege_assault` 傳 `fallen` list → 戰後 `apply_casualties` + 印「此役折損…」(勝/逃皆折損,**死則 game over 不結算**)。
- **C 親衛複合來源(warlord 將領)**:`companions.json` 加 `veteran 老兵隊長`(`warlord:true`,400 金,戰錘 18/skill62);`_hire_mercenary` 旅店池**濾掉 warlord**(`not troop and not warlord`)→ 唯**營地**可招(`warband.recruitable_officers`/`officer_cost`,`action_warband` 加「招募親衛將領」分支,受 `MAX_PARTY=2` 限)。officer 來源從「旅店 + 武士侍從」擴為「旅店 + 侍從 + 營地延攬」。
- **平衡(sim 背書,戰鬥本體未改 → 階段一勝率不變)**:永久傷亡只是「戰後回報誰陣亡」,不改戰鬥難度。折損率 sim(忠實複刻群戰階段順序):小城(守軍≤120 強攻)親衛/士兵幾乎零折損;中城(250)上場兵亡均 ~0.3/6;大城(400 未削弱、強力英雄)親衛亡 ~0.13、士兵亡 ~1.5/6;**全程零全滅**(不會一役賠光整軍 → 不過懲、不勸退)。先以圍城方略削守軍 → 強攻更輕 → 折損更少(備戰=保兵)。軍餉(150 金/週)才是主要持續成本。
- **接點/鐵律**:`casualties` out-param **預設 None → 既有所有 run_battle 呼叫零影響**(只有 `_siege_assault` 傳);永久折損**只在攻城發生**(大軍壓境/圍城方略非戰鬥,不折損);軍餉只對**士兵**(親衛無月俸,但攻城會永久死)。調軍餉/傷亡只動 `warband.py` 常數;加 warlord 將領純改 `companions.json`(`warlord:true`)。
- **驗證**:32 測試模組全綠(`test_warband` 擴至 22 測試:軍餉寬限/足額付/破產逃兵/部分付/無兵清週期/多週期補結/存檔向後相容、永久傷亡名冊扣減+夾限+略過未知 id、**真實 run_battle 回報陣亡兵且無誤報**、**傷亡歸零→重建得新寬限**(對抗審查回歸防線)、warlord 將領池/旗標、`_siege_assault` 永久折損煙霧)+ 折損率/軍餉經濟 sim + `sim_assassin` 基線不變(run_battle 改動不影響戰鬥)+ 無頭煙霧(真實 `action_warband` 招親衛+招兵+軍餉 paid/desert 顯示分支無 traceback)。
- **對抗審查(7 維 fan-out × 每發現 3 視角驗證;13 發現 → 4 確認)**:**3 個確認屬誤報/已結構性免疫**,只 1 個值得修:
  ① CRITICAL「遣散士兵洗軍餉寬限」=**誤報**(全碼無遣散士兵入口;且即使日後加,重招 40/兵 ≫ 週餉 5/兵 → 經濟自殺。驗證者以直接改 `soldiers=0` 重現,非遊戲路徑);
  ② MAJOR「apply_casualties 不重置 wage_due_at → 重建失寬限」=**誤報**(下一圈 `tick_upkeep` 在玩家能重招前已重置;與 ① 互為中和:① 視為漏洞的歸零重置正是 ② 不發生的原因);
  ③ MAJOR「存讀檔累積軍餉債暴扣」=**誤報**(遊戲時間凍結於存檔,讀檔不推進 `absolute_hours`,把現實時間誤當遊戲時間);
  ④ MAJOR「`apply_casualties` 回報陣亡計數而非實際扣減」=**真**(實戰恆等,但傳超量名單會誤報)→ **已修**(回報 `before-after`)+ 更新該測試 + 補 ②③ 的回歸防線測試與 `tick_upkeep` 不變式註解(防未來「修掉」歸零重置反釀回歸)。9 個駁回多為平衡評估/既定設計(veteran 高價=刻意 gate、army_soften 免傷=刻意權衡、死則 game over)。
- ✅ **後續(階段三)已做(見下「城戰階段三」)**:佔領收稅(按居民數量)− 駐軍維護費 + 輕量叛亂計時 + legacy 補回報債。

**城戰階段三:佔領後收稅 + 駐軍維護 + 輕量叛亂(評估 workflow 定案 T0 → 使用者拍板「按居民數量計稅、守軍是支出維護費、純稅+輕量叛亂計時」)**:把城戰從「打下零回報」補成**收支閉環** —— 招兵軍餉是「出」、佔領收稅是「進」。核心在 `systems/politics.py`(鏡像 `warband.tick_upkeep` 時間鉤子)。
- **經濟模型(使用者拍板)**:每座**親手攻下**的城每 `TAX_HOURS`(168/週)結算:**居民稅**(`population×TAX_PER_POP`,人口在 `rulers.json` 21 城考據分級:帝都1000…龍橋鎮150…黑荊棘監獄140)**−** **駐軍維護**(`garrison×GARRISON_MAINT_PER`,「守軍是支出」)→ 淨額入庫。economy sim 背書:精簡持有 3 中城淨收 ≈402/週、養 30 兵(軍餉150)後仍餘 ~252;黑荊棘(守200/民140)滿駐淨虧 −50/週(監獄不產財,刻意)。
- **🔴 紅線(評估的對抗審查預先攔下)**:稅基用 `politics.held_tax_cities`(只認 `city_faction` 中你攻下的城),**嚴禁 `held_cities()`**(含未攻的同立場盟城 → 實測白送 2190+ 金/週)。`held_cities` 註解已標警語。
- **輕量叛亂計時**:占領駐軍每期流失 `UNREST_DECAY`(10);跌破 `UNREST_WARN`(30)→ **民心浮動**(稅收中斷、仍付維護 → 逼你回防);潰散(≤`GARRISON_REVOLT_AT`=0)→ **城邦叛離**(`city_faction`/`garrison_current`/`tax_due_at` 全清、還原原立場、可再攻)。出資 `reinforce_garrison`(4 金/兵、夾原始守軍)回防。無限金幣檢查:帝都完全不回防 39 週後民變失守(累計 14880 後失城,非無限)。最優解=保「精簡駐軍」(剛好過浮動線→最小維護)+ 定期回防。
- **接點**:新 Character 欄 `tax_due_at`(loc→絕對小時,預設 {} 向後相容、進 to_dict);`conquer(...,now=)` 起算徵稅(首期一週寬限,`tick_tax` 對缺漏自癒);`game_loop` 頂端固定 tick 順序 **vampirism → warband.tick_upkeep(出)→ politics.tick_tax(進)**;`action_court` 對你的領地顯示「【你的領地】居民稅/駐軍/維護/淨收/民心」面板(`ui.court_panel` 加 `territory` 參數)+「加強駐軍」選項(`_reinforce_garrison`,耗 2 時)。
- **legacy 補回報債(評估發現:整套城戰+招兵此前在結算零承認)**:`legacy.compute` 加分 —— 攻下的城 ×200、武士 ×80、常備兵 ×3;新增 `dominion_label`(擁護大義·據有 N 城·受封 N 地武士·麾下 N 兵)→ 結算「功業」行(無則省略)。
- **驗證**:32 測試模組全綠(`test_politics` 擴 11 測:21 城人口完整/**紅線只稅 conquered 不稅盟城**/起算週期+收淨額/民心浮動稅斷仍付維護/駐軍衰減造反/多期補結/加強駐軍夾限/存檔向後相容/legacy 功業計分/**legacy 防毀損公會 id**/court 加強駐軍端到端)+ economy sim(收支閉環+無限金幣檢查)+ 無頭煙霧(三種稅收事件顯示 + legacy 渲染)。
- **對抗審查(6 維 fan-out × 每發現 3 視角驗證;19 發現 → 1 確認)**:18 個駁回多為**正向確認**(紅線守住、收支閉環、向後相容自癒、叛亂鏈正常)或既定設計(帝都主動維護 +300/週=刻意的征服回報,gold 非勝利條件;reinforce 夾 base 防虛高)。唯一確認=**既有(非本輪引入)robustness 缺口**:`legacy.compute` 取 `gamedata.factions[fid]` 未防缺 id → 毀損存檔(殘留已移除公會)在結算畫面 `KeyError`。本輪順手修(改 `.get` 跳過,同 factions.py/warband.py 慣例)+ 補回歸測試。**經濟尺度備註**:帝都單城主動維護 +300/週(funds ~2 軍),刻意(最難攻的城=最高回報);要調降改 `politics.GARRISON_MAINT_PER`↑ / `TAX_PER_POP`↓。
- ✅ **後續(階段四)部分已做(見下「城戰階段四」)**:領地全局總覽 + 駐軍自動緩慢重建 + Thane 翻敵特權暫停。**加城/改人口純改 rulers.json;調經濟改 politics 常數。**

**城戰階段四:領地經營完善(規劃 workflow:6 維調查 → Plan agent 設計;使用者拍板做領地經營 QoL 套餐)**:把「持有領地」從雜務變統治體驗,補階段三的經營摩擦。三核心項、**零新存檔欄位**(全讀既有狀態)。
- **領地全局總覽**:hub 人物群「領地總覽 🏰」(僅當 `held_tax_cities` 非空 → 紅線:盟城-only 玩家看不到)→ `action_territory` 一覽所有攻下城(城名/居民/週稅/駐軍cur·base/維護/淨收/民心/下次徵稅倒數),**可遠程加強任一城駐軍**(複用 `_reinforce_garrison`,免逐城跑 court)。新 `politics.territory_overview(char,gd,loc,now)` 純函式(court 面板 + 總覽共用,含 countdown)、`ui.territory_panel`(SIMPLE_HEAD 表)。`action_court` 重構為呼叫同 helper。
- **駐軍自動緩慢重建**:`politics.GARRISON_REGEN_PER=6`,`tick_tax` **僅「安定」分支**(駐軍 > UNREST_WARN)`g=min(base,g+6)`。**鐵律不變式**:① 民心浮動(≤WARN)**不重建** → 叛亂計時零削弱;② **淨 −4/期**(regen 6 < decay 10)→ 無不死免費城;③ 夾 base。維護仍以「回補前駐軍」計。**勿設 ≥10**(會變永久城)。
- **Thane 翻敵特權暫停(可逆)**:`court.is_thane_in_province` 收緊 —— 武士城若 `char.allegiance` 已選 **且** `faction_of(loc)≠allegiance`(翻敵)則該城特權暫停;城再翻回即自動恢復(**不動 thaneships**、零新欄位)。`char.allegiance and …` guard 必要(未選邊 faction_of 回種子立場,沒它會誤判破壞未選邊玩家特權)。`is_thane`(顯示)不變。唯一受惠端 `guard_confrontation`。
- **平衡(economy sim 背書)**:不回防=有界且最終失守(小城 kvatch 21週/dragon_bridge 13週仍會造反;大城刻意很穩=低 grind);保 base 反而淨收較低(維護高)→ 最優=讓駐軍漂移、近浮動才回防,grind 砍約半(正是目的)。大城(帝都~95週才倒)刻意極穩。decay/regen 為**平坦值**(不隨城大小縮放,刻意從簡;大城穩、小鎮亂)。
- **自任領主=刻意延後**(ruler-vs-thane 顯示語意歧義、無經濟迴圈,留待 AI 陣營戰那輪)。
- **驗證**:32 測試模組全綠(test_politics +5:安定 regen 淨−4/**浮動不 regen(關鍵)**/被忽視仍造反/territory_overview/總覽只列攻下城+遠程回防端到端;test_court +4:翻敵暫停/再翻回恢復(可逆)/未選邊照常/衛兵不寬待;另更新 2 既有 tax 測試的 regen 淨流)+ economy sim + 無頭煙霧(總覽渲染/hub gate/重建)。**對抗審查 5 維×3 視角:2 發現→0 真 bug**(皆既定設計/正向確認:maint 以回補前駐軍計=刻意、零新存檔欄位=正向)。唯一細節:`territory_overview` 的「淨收/週」以**當前駐軍**估算,比 tick_tax 實扣(post-decay 駐軍)保守約 2 金,刻意不耦合 decay 時序。
- **🚧 後續(階段五/未做)**:AI 陣營自走戰爭(NPC 互攻/反攻你的領地,活的政治地圖;大型、需 sim)、攻下自任領主、公會與大義綁定。

**陣營系統(規劃定案:正史拼湊 + 大事件驅動動態政局;計畫見 `~/.claude/plans/reactive-soaring-pretzel.md`)**:使用者拍板把「陣營」按 TES 文獻(3E433 湮滅期)拼成全譜並動態化 —— 開局=Oblivion 當下歸屬、後續由**幾個 authored 大事件**觸發城邦易幟;大義擴四極(帝國/獨立/**神話黎明**/**自立稱雄**)+ 中立。分四階 A→B→C-lite→D(MLS=A+B+C-lite)。**非隨機 AI 戰爭**,改 authored 時間軸(走 vampirism/brotherhood 式狀態機)。
- ✅ **Phase A 已做(靜態旗號 bloc,純資料地基)**:`rulers.json` 21 城各加 `bloc`(英文 id)+ `bloc_label`(繁中正史旗號:長老會/風暴斗篷/雷多然家族/An-Xileel 議會…)= 各城 Oblivion 當下歸屬的陣營身分。`politics.city_bloc`/`city_bloc_label` 純查詢;`ui.location_panel`/`court_panel`/`world_map` 顯示「大義·旗號」+ 地圖各城大義標記(帝/獨/中,前瞻含湮/己)。**零機制/零存檔影響**(`relationship`/`faction_of`/`held_tax_cities` 全未動;旗號在 rulers.json 靜態)。驗證:32 模組全綠(`test_world` 加 `test_every_city_has_a_bloc`:每城 bloc 合法+與 stance 並存、非城無旗號)+ 渲染煙霧;agent 額度上限故本階以自審代對抗審查(純資料低風險;B 邏輯/C 引擎將補跑完整審查)。
- ✅ **Phase B 已做(四大義 + 中立可攻 + 自立)**:`CAUSES`/`STANCE_LABEL` 加 `daedric`(神話黎明)/`own`(自立稱雄);`EXPANSIONIST_CAUSES={own,daedric}` → `relationship` 對 neutral 回 `enemy`(普世征服,帝國/獨立**逐位元不變**)。`pledgeable_causes`:帝國/獨立/自立隨時可宣誓,**神話黎明須 `kvatch_falls` 大事件後解鎖**;`_pledge_allegiance` 四選 + 各義說明。`legacy.own_realm_title` 自立依持城數開國稱號(割據梟雄/裂土霸主/問鼎雄主/再造一統的新王)。新 Character 欄 `world_faction`/`world_events_fired`(空預設、進 to_dict、向後相容;供 C 用)。**紅線守住**(held_tax_cities 仍只認 city_faction;自立只稅己城)。驗證:32 模組全綠(test_politics +8:四義/中立可攻/**兩大義關係回歸**/解鎖 gating/自立攻城收稅/自立 title/存檔/四選 pledge 煙霧);自審代對抗審查(agent 限額)。 **⚠ 後續已整個移除 `daedric` 大義(見 R26):現 `CAUSES`/`pledgeable_causes` 僅 imperial/independent/own、`EXPANSIONIST_CAUSES={own}`。**
- ✅ **Phase C-lite 已做(大事件引擎,動態政局核心)**:`systems/worldstate.py`(`update` 掛 game_loop 每圈頂端、vampirism 之後,定點迴圈處理鏈式事件、`sorted(id)`+state.rng 決定性、once-fire)+ `data/world_events.json`(定版 5 事件:`kvatch_falls` d3→daedric+解鎖神話黎明 / `septim_line_ends` d30 requires→anvil+gideon 易幟獨立 / `argonian_accession` d45 / `nord_stirrings` d50 / **`kvatch_liberated` 玩家驅動**:held_includes kvatch→clear_flip+fame)。`gamedata.world_events` 載入。`politics.faction_of` 三層 `city_faction>world_faction>base_stance`(relationship/can_siege 隨易幟變;**held_tax_cities 仍只認 city_faction → 紅線安全**)。effect:faction_flip/clear_flip/fame。**鐵則**:易幟寫 world_faction(玩家持有城被 city_faction 蓋過=免疫);conquer 不 pop world_faction(失城浮回事件態,非種子)。開局=Oblivion 種子(world_faction 空)。驗證:33 模組全綠(新 `test_worldstate` 12 測:觸發/once-fire/三層/玩家免疫/**紅線易幟城不入稅基**/鏈式/解鎖/可攻/玩家光復/失城浮回/補結/決定性/存讀檔)+ 端到端煙霧(時間軸推進易幟、新聞廣播、**存檔中途續跑==不中斷**)。**對抗審查 4 維×3 視角:16 發現→0 真 bug**(全為正向驗證)。
- ✅ **Phase D ① 已做(神話黎明 Mythic Dawn,第 5 公會)**:閉合 C-lite 開出的斷頭線 —— `kvatch_falls` 戰報邀你「投身其麾下」、達貢大義可宣誓,但此前無組織可入。新增可入會的達貢邪教(`factions.json` 加 `mythic_dawn`,鏡像黑兄惡道公會 schema)。
  - **大事件解鎖入會**:`factions.json` 新增**通用 `unlock_event` 欄位**;`factions.join_block_reason` 加通用閘(`unlock_event` 不在 `char.world_events_fired` → 隱於陰影,**非硬編碼 mythic_dawn**,九神騎士團等未來事件解鎖組織可複用)。聖堂=凱瓦奇(正史灘頭,亦 `kvatch_falls` 翻 daedric 的城)。
  - **perk=達貢之佑(新 kind `conjure_boon`)**:`factions.conjure_boon`(複用 `_best_perk`)→ `magic.cast` 召喚分支對 `ally` 放大 `max_health`(×(1+boon),cap 0.6)+ `summon_turns`(+int(boon×3))。**刻意避開傷害階梯**(只強化召喚物耐久/駐留)→ 神話黎明=召喚流(conjuration)build 的歸宿。**只影響會員召喚物**(`sim_assassin` 零位移)。
  - **晉升內容**:`quests.json` 加 md1–md6(`source:guild`,獻祭九神信徒/刀刃密探/黑蠕蟲死靈/聖騎士〔escort〕/大祭司 + md6 兩分支「忠於達貢 vs 奪典自立」)、`bestiary.json` 加 7 具名目標(全 `min_level:99`+`weight:0`,不污染野外/biome)。獎勵用既有高階裝備,**不造新物品**。
  - **接點**:`main.py` 城區服務 `md_hall`(事件後才現身,鏡像 `db_hall`)+ 新 `action_mythic_dawn`(入會 walk-in / 領受+執行獻祭 / 聆聽《魔典》箴言)。**復用通用 `action_contract`**(原黑兄用,本輪去除「兄弟會」品牌字 → faction-neutral);`_active_db_quest` 重構為委派 `_active_faction_quest(faction_id)`。**零新 Character 欄位**(會籍存 `char.factions`、解鎖讀既有 `world_events_fired` → 零存檔遷移)。`legacy.compute` 迭代 `char.factions` 故自動收錄。
  - **驗證**:34 測試模組全綠(新 `test_mythicdawn` 13 測:事件解鎖閘〔通用非硬編碼〕/對立排除雙向/合約階梯晉升/技能門檻/md6 雙分支/目標+escort 存在/`conjure_boon` 隨階+非會員 0/召喚實放大 HP+回合/存檔往返/legacy 收錄)+ `sim_assassin` 零位移 + 無頭煙霧(經真實 `action_mythic_dawn`:hub 閘→入會→md1 執行晉升→md6 分支→legacy 渲染,無 traceback)+ **單代理對抗審查(7 風險維度,0 真 bug**:事件閘無繞過/perk 不洩漏非會員·非召喚·無循環匯入/farm 已封堵/存檔相容/shunned 行為與既有公會一致)。**加合約純改 quests.json + bestiary 目標;加事件解鎖組織純改 factions.json `unlock_event`。**
- ✅ **Phase D ② 已做(九神騎士團 Knights of the Nine,第 6 公會)**:神話黎明的**聖道·lawful 對位**。同一場湮滅危機(`kvatch_falls`)既孕生邪教、亦重組聖團 —— 複用通用 `unlock_event` 框架,**對稱機制**:神話黎明=召喚 build 的家(`conjure_boon`),九神騎士團=**恢復 build 的家**(`restoration_boon`)。
  - **perk=聖光眷顧 `restoration_boon`**(新 kind):`magic.cast` 的 `heal` 分支對治療量 ×(1+boon)(`per_rank 0.07 / cap 0.35`,**刻意比 conjure 0.6 弱**:會與「聖光·溢盾」精通複利,但被 0.5×血上限 cap 夾住)。只對會員、只動 `heal` 分支(藥水/再生/星座之力/`shield`/`restore_fatigue` 不受影響)。
  - **聖堂=安維爾**(正史九聖小修道院);`lawful:true`(拒收/不升通緝者);`rivals=["mythic_dawn","dark_brotherhood"]`(**雙向**補這兩會;**不**與戰士公會對立 → 聖騎士可兼戰士會)。
  - **任務=聖戰合約**(named boss 在聖堂出征):kn1–kn6(`source:guild`,**全無 clean_bonus**、給 fame+gold;kn6 兩分支「鐵血(殺新 `defiled_crusader`)vs 聖戰(殺 `dawn_mentor`,跨陣營討伐神話黎明首領)」)+ 6 具名目標(`min_level:99`/`weight:0`)。獎勵用既有高階裝備(ebony/gold)。
  - **合約大廳泛化**:`action_contract(...,*,stealth=True)` —— 預設(黑兄/神話黎明)逐位元不變;`stealth=False`(聖戰)跳過 `try_stealth_approach`+`clean_bonus`、正面開打(`alerted=True`、`prep_budget=0`)。抽出通用 `_contract_hall`(神話黎明/九神共用);`action_sanctuary`(黑兄,有 launder/tenets)維持原樣。game_loop 加 `kn_hall`(`kvatch_falls` 後現身,鏡像 md_hall)。**零新 Character 欄位**。
  - **對抗審查覆核修掉 1 既有破口(非本輪引入)**:`lawful` 通緝者的**晉升**閘原只擋訊息(`advance_block_reason`)卻未真擋 —— `quests.available_quests` 不查賞金 → 通緝中的 lawful 會員仍被開放任務、可接取晉升(戰士公會也中招)。改 `available_quests` guild 分支以 **`advance_block_reason() is None` 為單一真實來源**(技能門檻+lawful 通緝+頂階一處收斂),通緝中真的接不到任務;`test_knights` 加斷言「通緝→`available_quests==[]`」防回歸,順帶修好戰士公會同病。
  - **驗證**:35 測試模組全綠(新 `test_knights` 16 測:解鎖閘/雙向對立/lawful 真擋晉升/聖戰階梯/分支/`restoration_boon` 隨階+cap+治療放大+溢盾 cap 含複利/無 clean_bonus/存檔/legacy)+ `sim_assassin` 零位移 + **平衡校準**(新 d5 目標 2–7% 落在既有 d5 帶 0–12% 內,tier 一致)+ 無頭煙霧(兩大廳:聖戰無潛行/無 clean_bonus、神話黎明潛行+clean_bonus 經泛化仍完好、雙向對立實機生效)+ **對抗審查 Workflow(6 維 fan-out × 每發現 3 視角驗證,2 發現→1 確認〔已修〕)**。
- **🚧 Phase D ③+(後續)**:其餘可入會組織(丹莫大族入族/三聯神殿/影鱗/刀刃/黑蠕蟲)各自獨立一輪;更多大事件純加 world_events.json。(✅ **戰友團已做** —— 見 §1「戰友團 The Companions」,第 7 公會、白漫·一般公會流、狼人血脈歸宿。)
- **鐵律**:大事件易幟一律寫 `world_faction`(非 city_faction)→ 不污染稅基;玩家已佔城(city_faction)免疫事件易幟;加事件/旗號/大義純改 JSON。**`conjure_boon`/`restoration_boon` 只在各自法術分支、只對會員**;改 perk 數值改 `factions.json` per_rank/cap(純 JSON);新事件解鎖組織加 `unlock_event` 欄(通用,零碼);新合約公會走 `_contract_hall`(`stealth` 旗標分暗殺/聖戰),黑兄聖所自有 launder/tenets 不走此處。**guild 晉升閘以 `advance_block_reason` 為單一真實來源**(別只擋訊息忘了擋 `available_quests`)。

**區域細化:具名地標與發現系統(換出陣營線;§6「具名地標與發現」候選落地)**:前幾輪細化省分後,野外節點仍多是「純通勤」(9 個荒野節點、整個邊境、被 rumor 點名卻無內容的 `falkreath_wood`)。本輪給各區域的招牌/空蕩節點一個**首次抵達一次性「發現」**(意境文字 + 小獎勵),讓「區域」有識別度、值得探索,並為**刻意無 NPC 的邊境**填上內容。
- **專用系統,不走隨機事件引擎**(那是機率抽選):新 `data/landmarks.json`(13 條,key=location_id,鏡像 rulers.json)+ `systems/landmarks.py`(`discover(state,gd,loc_id)→dict|None`:fire-once 守門 + 套金幣/物品/聲望獎勵 + 回 UI;`is_discovered`)。`gamedata.landmarks`/`landmark_at`。
- **守門用新欄 `discovered_landmarks`(非 `visited_locations`)**:`creation` 建角已把起始城塞進 `visited_locations` → 複用它則起始城/舊存檔已訪節點永遠觸發不了。新欄預設 `[]` → **舊存檔向後相容且仍能發現**(有回歸測試)。dataclass 預設 + to_dict,**零存檔風險**。
- **單一 game_loop 頂端 hook**(tick 區後、`location_panel` 前)`_try_discover(player.location_id)` → 統一涵蓋起始城/旅行抵達/任意當前地(含荒野;既有 "arrive" 事件僅城鎮);fire-once 保證不重播。
- **獎勵=一次性、克制、隨 danger 分級**:金幣 + 選用物品(只用既有 id)+ 選用 fame;**無永久數值/技能加成**(守反 min-max,有契約鎖測試)。最高一件僅到既有中階(glass_dagger,壓在 d4 邊境節點)。
- **接點**:`ui.landmark_discovery`(發現面板)、`location_panel`「❖ 已發現」、`world_map` ❖ 標記(避開 ✦=地城,legend 已註)、`legacy` 加「奇景 N/M」探索行 + score(`landmarks_found×30`,∩ 合法 key 防毀損)。13 地標各省主題鮮明(賽=艾雷德/邊境=遺棄前哨·沉船·王座/天=雪塚〔收掉 falkreath rumor〕/晨=矮人齒輪/黑=希斯特),**邊境 4 節點全有**。
- **驗證**:36 測試模組全綠(新 `test_landmarks` 13 測:發現+獎勵精確/fire-once/多 hook 冪等/舊存檔相容+已訪節點仍可發現/loc 與 item id 合法/必填欄/**禁永久加成獎勵契約鎖**/legacy 計數防毀損/不致死不耗時)+ 無頭煙霧(真實 `_try_discover` hook + 三面板渲染 + 起始城奇景)+ **對抗審查 Workflow(5 維 × 每發現 3 視角,6 發現→3 確認,全 minor 全已修**:① 測試 `absolute_hours` 漏括號→比較 bound method 恆等的空斷言〔已改呼叫〕;② `is_discovered` 死碼〔已接進 UI〕;③ world_map ✦ 與地城圖示撞色〔已改 ❖+legend〕)。**加地標純改 `landmarks.json`(零碼)**。

**省份內容補強 pass(非陣營・純資料內容微調;精準 gap map → 三缺口)**:承「具名地標」後續細化省分,補三個明確的低風險純資料缺口,**零新機制/零存檔欄位**,沿用既有引擎。
- **龍喉峰屠龍任務(apex 地城內容)**:`dragon_lair`(晨風 d5,全圖最險)此前是**唯一零任務的地城**。新增晨風「屠龍者 約爾根」NPC(`npcs.json`@molag_mar,`quest:"hunt_dragon"`+greeting+rumor)委託**清剿龍喉峰**(`source:"npc"`、`clear_dungeon`,**非領主/非公會→守非陣營**)。獎勵 gold400/fame25/`filled_greater_soul_gem`(地城本身才掉 BIS,任務不加碼)。
- **法術可及性 + 省份學派風味(純加性 spell_stock)**:實查發現**唯一真破口=黑沼澤整省買不到變化術**(gideon/helstrom 皆無)→ 補 oakflesh/stoneflesh(只增不減);另各省輕量學派風味(vivec 補火系破壞、markarth 補基礎恢復、gideon 補幻術)。至此**四省皆可買齊六系、每系 ≥8 城**;**賽羅迪爾起手六系全可及**。⚠️ 評估時 Explore 一度誤報「幻術僅 3 城」,實查(authoritative dump)幻術其實 9 城 → **以實查校正,只修真破口**(教訓:agent gap 報告要實查覆核)。
- **forage 省份齊備**:`events.json` 加 `skyrim_forage`(天際)+`border_forage`(邊境),只用既有 ingredient → **每個可探索省份都有招牌採集**(此前天際/邊境缺)。
- **守門精煉(唯一非資料改動,經對抗審查重點覆核=正當)**:`hunt_dragon`(清 d5)觸發既有反 min-max 獎勵守門(`test_local_quest_rewards_stay_in_range` 原 npc/board 一律 gold≤320/fame≤15)。守門原 anchor 即「清 d4 地城=320」→ 對 `clear_dungeon` 改**按目標 danger 放寬的 floor-preserving 上限**(`max(320,danger*100)`/`max(15,danger*5)`):**既有委託逐一不變(上限只升不降)**、**no-BIS 鐵則全保留**、cap 綁真實難度信號。對抗審查 5 子維度逐一確認為**正當精煉非弱化**(floor-preserving/no-BIS 仍在/有界/綁 danger/仍能抓過獎)。
- **驗證**:37 測試模組全綠(新 `test_polish`:六系可及不變式/省份無鎖死/起手全系/地城任務全覆蓋/屠龍 NPC+任務/forage 省份齊備/素材合法 + `test_detailing` 守門精煉)+ 無頭煙霧(攀談龍狩→接屠龍→清龍喉峰→發獎、天際 forage)+ `sim_assassin` 零位移(不碰戰鬥)+ **對抗審查 Workflow(4 維×每發現 3 視角,17 發現→0 真 bug**;4「確認」皆正向驗證:破口已閉/屠龍已接通/守門有牙/守門精煉正當)。**加法術舖貨/在地任務/採集純改 JSON**;調獎勵上限改 `test_detailing` 的 danger-scaled cap。

**角色卡升級:充實顯示 + 互動式檢視(使用者問「角色卡只能看?」→ 兩者都要;UI-only,零新遊戲邏輯/零存檔欄位)**:原角色卡純渲染且偏薄(只屬性/技能/資源)。本輪兩件事,全讀既有唯讀存取器。
- **充實 overview**(`ui.character_sheet`,簽章不變 → 創角預覽呼叫端也受惠):加 護甲、非零抗性摘要、聲望/惡名/通緝、公會與階級、進行中效果、吸血鬼階級。
- **互動式檢視**(新 `main.action_character_sheet`,hub「角色卡」改呼叫它;**空/不適用項自動隱藏**):元素抗性表 / 進行中效果 / 公會與階級(+perk)/ 技能里程碑(已解鎖+未解鎖門檻進度)/ 星座之力(就緒)/ 聲望與通緝(分省)/ 穿戴與套裝(套裝名+加成+護甲)/ 吸血鬼狀態 / 技能詳情(選技能→等級/熟練進度/下一里程碑/練習成本)。各為一支 `ui.sheet_*` 唯讀渲染器。
- **唯讀鐵律**:檢視不改 char 狀態、不耗時。**踩到並避開一個雷**:`progression.practice_cost` 會扣體力 → 技能詳情改讀靜態 `skills.json` practice 而非呼叫它(有回歸測試:檢視前後 to_dict/體力/時間不變)。
- **對抗審查 Workflow(4 維×每發現 3 視角,3 發現→2 確認〔皆 minor,已修〕)**:① 套裝加成行名稱永遠空白(`active_set_bonus` 只回 bonus 子物件,名稱在父層)→ 改顯示 `armor_sets[mat]['name']`;② 毀損存檔的未知 item id 在 equipped/offhand/weapon 會 KeyError 崩潰(新 overview 每圈讀 `worn_armor_rating` 放大了此面;faction 路徑有防禦、item 路徑沒有)→ 新增 `gamedata.item_or_none` + `item_name` 回退,並讓 `worn/effective_armor_rating`/`equipment_bonuses`/`active_set_bonus`/`armor_fortify_totals`/`weapon_line` 一律跳過未知 id(**順帶硬化戰鬥/recompute 對毀損存檔**,符合 §3)。1 駁回(`_tr_bonus` 對未知技能鍵 KeyError,經查現實路徑不可達)。
- **驗證**:38 測試模組全綠(新 `test_sheet`:三種角色狀態渲染無 traceback / 唯讀不變式 / 技能詳情不扣體力 / action 走訪全項 / **毀損 id 不崩潰** / 套裝名顯示 / 創角預覽仍渲染)+ 無頭煙霧 + `sim_assassin` 零位移。**加檢視類別純改 `ui.sheet_*` + `action_character_sheet` 分派**(唯讀鐵律:勿呼叫有副作用的函式如 practice_cost)。
- **後續微調(同主題,使用者要求「技能/法術都要看得到作用」)**:① 每技能 `skills.json` 加 `mechanic` 欄(升等實際效果),技能詳情多印「作用」行。② **法術作用**:`ui.spell_effect_summary(gd, spell_id)` 資料驅動把 effect 結構渲成一行(涵蓋全 13 種 effect kind,無泛用後備;apply_status 標明對象 使目標/自身),接進新 `ui.sheet_spellbook`(角色卡「法術書」依學派分組)+ 法術舖/施法/戰鬥施法選單標籤。摘要為**基礎效果、施法者加成(如達貢之佑)不計入**。對抗審查(3 維×3 視角,9 minor→修 4:apply_status 標對象/`int→round`/刪死碼/弱化 docstring 過度宣稱);加 `test_sheet` 斷言(全法術可摘要、無後備、apply_status 對象分明)。**加法術純改 spells.json → 摘要自動涵蓋**。

**Web UI(原生本機單人版;全原生 HTML 渲染 + 可點輸入;`python3 -m tesrpg.web`)**:把終端遊戲搬上瀏覽器。**遊戲規則邏輯零改、戰鬥控制流不重寫**。歷程:評估→「重新評估」8-agent 對抗審查→使用者先拍板 C-lite(rich 截圖)→看了實機截圖後改要「**不用類 CLI**、全部轉原生」→Phase 2 把**每個面板都改成原生 HTML 元件**(無終端框線美術)。
- **核心(新套件 `tesrpg/web/`,純 stdlib、零 pip)**:遊戲在背景 daemon thread 跑原本阻塞 REPL —— 戰鬥巢狀/遞迴 prompt(`run_battle` 逐回合、`_choose_combat_action` 遞迴、`_prep_phase` 預算迴圈)靠 thread 呼叫堆疊自然保住。`console.py` 的 **5 個輸入原語** 在 web 模式攔截 → 經 `inbound`/`outbound` 雙 `queue` round-trip;`WebBackend`(backend.py)+ stdlib `ThreadingHTTPServer`(server.py):`GET /`、SSE `GET /events`、`POST /input`。
- **幀協定 = 有序 `blocks` 串**:`view`(原生:`{name,data}`,客戶端依 name 畫元件)/ `log`(rich 標記→彩色文字行,`_markup_html`)/ `html`(退路,export_html;**正常遊玩已用不到**)。`console.py` 每個渲染函式頂端加 `if _web: _emit_view(name, {…}); return`(同源資料萃成 view-model);輸入轉結構化 spec → 原生按鈕/輸入框 + 數字鍵。
- **全面原生(零 html 退路,實測一輪 0 fallback)**:status/location/sheet/combat(HP+體力條/編號敵人/狀態標)/inventory/map(行省清單)/legacy/guild/quests/npc/court/territory/room/event/discovery/divider/log + **10 個 `sheet_*` 子檢視走通用 `panel` view**。`index.html` 為每種 view 寫原生元件 + CSS(暗色金線卷軸主題、計量條、卡片、chips、RWD `env(safe-area)`)。**CJK 框線對齊問題消失**(不再畫框線)、**手機全友善**(響應式單欄、無橫捲)。
- **骨幹必修(對抗審查實證)**:`export_html` 加 `code_format` 防整份 `<!DOCTYPE>` 洩漏;SSE 斷線重連重送 `last_frame` + generation id 退殭屍 handler;`submit()` 鎖內原子防雙擊幽靈作答;Content-Length 夾限;前端多位數數字鍵/重連保留輸入值/空整數不誤送 0/送出失敗解鎖。launcher `server.py:launch()`(遊戲 thread `try: main() finally: flush_final()`、未捕捉例外渲染進畫面)。
- **服務選單迴圈(UX 修正,動 `main.py`)**:9 個原本「選一次即跳回主畫面」的服務動作(告示板/公會/訓練師/法術舖/煉金/附魔/修理/製作/領主區)改成**迴圈**(每圈重算可選項、返回才離開),與早就迴圈的商店/背包一致 → **可連續選**(入會→立刻接晉升任務、連接多張委託等);攻城仍為終局單次。
- **視覺驗證(用 WSL 直驅 Windows Chrome headless 對靜態快照截圖,Read 圖親眼確認)**:hub/角色卡/戰鬥/世界地圖/傳奇/通用面板,桌面 + 390px 手機皆過。
- **驗證**:39 測試模組全綠(`test_web`:5 原語 round-trip / 雙擊擋 / 越界整數重詢 / flush_final / code_format / view block 斷言;順手修 `test_politics` 固定-mock 無限加強駐軍)+ 無頭 queue 全鏈(create→hub→各 sheet 子檢視→地圖→背包→隱退→**傳奇結算**→quit;**0 html fallback** 證明全原生)+ live HTTP/SSE 煙霧(串流/POST/重連重送/stale→409/惡意非物件 POST→乾淨 409)+ web 模式迴圈實測(公會入會後留在公會)+ **對抗審查 Workflow(C-lite 骨幹,4 維 11 發現→4 low 已修)**。
- **加新面板**:`console.py` 寫 `_xxx_view()` + 函式頂端 guard + `index.html` 加 `renderXxx` 元件並登錄 `VIEWS`;簡單面板可直接用通用 `panel`(rows=kv/head/line)。**終端版完全不受影響**(`_web=None` 惰性)。

**Web UI/UX 評估 → 核心循環互動改善(評估用實機截圖 + 5-lens 對抗審查)**:用 WSL 直驅 Windows Chrome headless 對實機畫面截圖(`/mnt/c/Program Files/Google/Chrome/Application/chrome.exe` + `--headless=new --screenshot`,靜態快照法把 `render(frame)` 注入 index.html)+ 5-lens workflow(35 findings),**對抗驗證剔除截圖工具造成的誤判**(創角/升級選單其實有顯示描述/數值)。使用者選「核心循環互動」批次:
- **常駐生命 HUD**:`console.py` 模組變數 `_hud_state`(`status_line` web 模式改設它後 return、不再發 status 卡)+ `_hud_view()`(讀同一就地變動的 player → 即時值)；`_web_prompt`/`flush_final` 帶 `hud` → `backend.prompt(html,spec,hud)` 放進 `frame.hud`;`index.html` 渲成 masthead 下 `position:sticky` 細條(HP/MP/體力/金/通緝/時間,三條資源獨立成行防手機裁切)。**跨所有子畫面常駐且即時**。
- **通用「可點內容列」**(`wireActionableRows`):view 列帶 `data-key`,若該 key ∈ 當前 prompt 合法選項(含 `extra_keys`)→ 該列可點 submit。**背包**(`_inventory_view` 列加 key=item id;對應到選單按鈕 → 移除重複按鈕、列接管數字鍵)；**出口**(`_location_view` exits 加 `key="go:"+dest`;`grouped_menu(extra_keys=)` 提供合法 key 但不渲染按鈕 → 地點卡出口 chip 直接可點旅行,1 點;`game_loop` 派發 `go:` → 抽出的 `_travel_to`)。
- **升級 CTA**(`grouped_menu(cta_keys=["levelup"])` → 客戶端把該 option 置頂金框 `.opt.cta`、不佔數字鍵)+ **地點麵包屑**(`game_loop` 記 `last_hub_loc`,同地點重複回合 `location_panel(brief=True)` 只發名·類型·危險度+可點出口)+ 手機 2 欄按鈕(grid)+ `min-width:0`/斷字防溢出(批 A 一部分)。
- **驗證**:39 模組全綠(`test_web` 改 `test_hud_and_view_block` 斷言 `frame.hud`;`_restore` 清 `_hud_state`)+ 全鏈無頭驅動(create→hub→背包→隱退→傳奇,12 幀、HUD 跨幀常駐、**0 html fallback**)+ 出口可點旅行實測(imperial_road→bruma)+ 桌面截圖親眼確認(HUD/背包合併/CTA/麵包屑)。**⚠️ headless 限制**:Chrome headless 最小視窗寬鎖 **478px**,**做不出真手機寬(375–414px)** → 手機 2 欄/響應式只能在真機驗(CSS 正確、≤430px 會生效)。
- **roadmap(已於下輪「Web UI/UX 收尾六項」全做)**。

**Web UI/UX 收尾六項(承上輪 roadmap,使用者拍板六項全做;UI-only、零遊戲邏輯/零存檔欄位)**:把上一輪評估剩下的六項一次補齊。Explore×3 定位(combat / sheet+creation / theme+map+legacy)→ Plan×2 設計(驗證邊界:Creature 無 magicka、menu seam ~50 呼叫端、形狀改動消費端唯一)→ 直作 → 對抗審查 workflow(5 維×每發現 3 視角,**0 findings/0 真 bug**)。
- **① 戰鬥玩家魔力條**:`_combatant` 加 `mp`(getattr 後備 → Creature 無魔力得 `[0,0]`,JS 以 `mp[1]` 假值隱藏);`renderCombat` 在血↔體之間插 `魔`(青)行,**僅 `kind==="me"`**(同 fp 模式);複用既有 `.mp .m-fill`。
- **② buff/debuff 標籤分色**:`_status_tags_list` 由 `list[str]` 改回 `[{s,good}]`(**唯一消費端=web 戰鬥**;終端 `_status_tags` 字串版不動);`_BUFF_KINDS={shield,regen}` → 其餘 `_STATUS_TAG` 條目=減益、未知=中性;JS `.ct.buff`(綠)/`.ct.debuff`(紅)/`.ct`(中性洋紅)。順補 `_STATUS_TAG` 缺漏 `stagger:"踉"`。
- **③ 手機右緣裁切收尾**(純 CSS):`.attr/.sk/.cname/.kv` 進 `min-width:0` 允許清單;`.attr .v`/`.sk .lv`/`.cval` 加 `flex:none;white-space:nowrap`(數值不換行不壓縮),名稱 span 加 `min-width:0;overflow-wrap`(讓名稱吸收收縮)→ 戰鬥血量值/角色卡屬性值在 480px 不再裁切。
- **④ 對比微調**(實算後只有 `--faint` 真低於 AA 正文門檻 ~3.4:1;`--muted`/`--gold-dim` 其實 ~5.2:1 已過 → 不動):`--faint #6b6557→#847d6b`(~4.9:1,仍暗於 muted、層級保留),提示/圖例/頁尾/出口副文受惠;`input.field:focus` 焦點環加強(`gold-dim` 邊框 + 較實 shadow)。
- **⑤ 創角 build 數值 chips**:`ui.menu` options 接受 `(key,label)` 或 `(key,label,chips)`(`chips=[{text,tone}]`;web 有才加 `"chips"`、終端串成淡色後綴;`options[n-1][0]` 回傳與 ~50 呼叫端零影響,混長度 tuple 由逐項 `len>2` 守住)。`main.py` 加 `_attr/_race/_sign/_class_chips`(+綠/−紅·真減號、魔力/抗性金、技能青、★偏好金、異能洋紅),接 race/sign/class 三選單(sex/origin/custom 不帶)。JS `mkButton(…,chips)` 渲 `.opt-chips`(chips 無 data-key → 對數字鍵/`wireActionableRows` 惰性);新 CSS `.chip.green`/`.opt-chips`/`.opt .chip`。
- **⑥ 傳奇分段 + 地圖省份進度**:`_legacy_view` `rows`→`sections`(`[{header,items}]`,空段省略:身世/生涯/功績/名望);`renderLegacy` 逐段印 `.sec-title`(複用角色卡區塊樣式)。`_map_view` 每省加 `visited`/`total`(讀既有 `visited_locations`,零新欄位);`renderMap` 省標頭印「已訪 x/n」。
- **驗證**:39 模組全綠(`test_web` 加 chips round-trip + `test_view_model_shapes`:戰鬥 mp 雙元素/狀態標 {s,good} 分色/怪物 mp=[0,0]/傳奇 sections 無頂層 rows/地圖 visited≤total==len(nodes))+ `sim_assassin` 零位移(未碰戰鬥)+ headless 截圖親眼確認(桌面 900px + 手機 480px:魔力條/盾生綠·蝕弱痺紅/chips 換行/傳奇分段/地圖進度/血量值不裁切)+ **對抗審查 0 真 bug**。**加新面板/chips/分段沿用此型樣**。

**Web UI/UX 互動深化(承上輪「下一步」,使用者選互動方向;UI-only、零遊戲邏輯/零存檔欄位)**:顯示層已足,補最缺的「互動」。先實機驗證修正 survey 誤判(背包早已可點=`action_inventory` item-id 選單 + `wireActionableRows`;煉金選單已含效果+數量)→ 鎖定三真缺口。Explore×2(UI 缺口 + gameplay 候選)→ Plan×1 驗證(釘住命脈不變式)→ 直作 → 對抗審查 workflow(4 維×每發現 3 視角,**0 findings**)。
- **① 戰鬥可點敵人指定目標**(主菜):`_combat_view` 給**存活敵人**卡加 `key`=0-based 存活索引(`{**_combatant(e,idx=n),"key":str(n-1)}`;玩家/同伴/陣亡卡不給);`renderCombat` 對帶 key 的卡輸出 `data-key` + `.cbt.foe.tappable` CSS。**命脈不變式**:卡顯 1-based「idx」但 `data-key` 為 0-based(對齊 `_choose_enemy_target` 的 `enumerate(alive)` 鍵)。⚠️**因 `backend.blocks` 每幀清空**,選目標那幀戰鬥卡已不在畫面 → `_choose_enemy_target`(改簽章 `(state,gd,enemies,allies)`)在 web、>1 敵時**重發 `combat_status_group`** 再開選單;`wireActionableRows` 隨即把敵卡接管成可點目標並移除重複按鈕(數字鍵 1/2/3 仍對齊)。單敵自動命中不重發;AoE/self 法術與無目標星座之力本就不選。`allies` 一路穿 `run_battle`→`_choose_combat_action`→`_choose_enemy_target`。
- **② 領地總覽表手機友善**:`renderTerritory` 8 欄表加 **sticky 首欄**(`.tt th/td:first-child{position:sticky;left:0;box-shadow:1px 0 0 line}` + 實心底色)→ 橫捲時城名常駐。純 CSS,markup 不動;評估後不做 card 版面(晚期少見畫面,過度設計)。
- **③ 訓練師顯示里程碑進度**:新唯讀 `mastery.next_threshold(char,gd,sid)→{name,threshold,remaining}|None`(用 `_defs` 過白名單、**以 `base_skill` 計**鐵律、取高於 base 的最低未達門檻;全達/無里程碑→None;**零副作用**)。`action_trainer` 每技能附 mag 色 chip「距 〈名〉還 N 級」(reuse 上輪 menu 3-tuple chips);`mastery` 補進 main.py imports。
- **驗證**:39 模組全綠(`test_web` 加 `test_combat_target_key_parity`〔存活卡 key 0/1 對齊 enumerate(alive)、陣亡無 key〕+ `test_combat_target_reemit_web`〔_drive 驅選目標:該幀重發 combat view、選單鍵對齊卡 key、選 1 回第二隻〕+ `test_view_model_shapes` 擴 key 斷言;`test_mastery` 加 `next_threshold` 走 base/全達→None/無里程碑→None)+ `sim_assassin` 零位移(戰鬥數值未動)+ headless 截圖(選目標幀:敵卡重現+按鈕消失;訓練師 mag chip;領地表)+ **對抗審查 4 維 0 findings**。**加可點內容沿用 `wireActionableRows`+`data-key`;backend.blocks 每幀清空 → 跨 prompt 的可點畫面須重發。**

**Web UI/UX 細節「都做」批(承上輪「下一步」→「再做 UI/UX 細節」→「都做」;UI-only、零遊戲邏輯/零存檔欄位)**:把剩下兩方向一次補齊(6 項)。Explore×2(sheet 子檢視 + 互動流程)→ Plan×2 → 親覆核風險面 → 直作 → 對抗審查 workflow(4 維×每發現 3 視角,**0 findings**)。**先實機修正 survey 兩處誤判**:背包早已可點、煉金選單已含效果+數量(只做真缺口)。模式:`sheet_*`/服務動作的 **web 分支** 由 `_emit_panel` 改 `_emit_view` 或在 `ui.menu` 前 emit 可點面板;終端分支逐位元不變。
- **A·角色卡視覺升級(3 子檢視轉專屬 view)**:① **里程碑卡**(`sheet_masteries`):已解鎖 ✦ 卡 + 未解鎖卡帶 `bar(cur,threshold,"mp")` 進度 +「距門檻還 N 級」(`cur=base_skill`、locked=`mastery._defs` 減 unlocked)。② **抗性色彩量表**(`sheet_resistances`):`{rows:[{name,value}]}` signed −100..+100,`renderResist` 中心 0、正青右/負紅左(width `min(100,abs)/2%`)+ 免疫/弱點字。③ **法術書卡片化**(`sheet_spellbook`):`{schools:[{key,name,spells:[{name,cost,effect}]}]}`,每學派 sec-title(學派色)+ cost chip + effect;空學派略過。
- **B·城鎮互動細節**:④ **攀談成功率+成本**:`dialogue.persuade_chance`(唯讀、單源化既有公式、折服里程碑→1.0);`action_talk` 說服選項改 3-tuple chips「成功率 X%」「耗 N時·體力M」(成本讀**靜態** `skills.json` practice,**勿** 呼叫 `practice_cost`)。⑤ **告示板可點卡**:`_board_view`/`board_panel`(卡 key=qid、name、objective、獎勵 chips 金/聲望/物品);`action_board` 在 `ui.menu` 前 `board_panel` → wireActionableRows 接管+移除重複按鈕(分支選擇維持選單)。⑥ **商店可點面板**:`_shop_view`/`shop_panel`(買貨卡 key=iid、×qty、`buy_price`、afford);買分支 emit `shop_panel`、賣分支複用 `inventory_panel`(key=stack id);行竊維持選單。**已知接受小分歧**:賣場複用背包面板會列出 value-0 不可賣物為惰性列(不被 wire,無害)。
- **驗證**:39 模組全綠(`test_web` 加 `test_sheet_subview_models`〔三子檢視 view 形狀:masteries unlocked/locked·locked 帶 remaining≥1·cur/threshold、resistances 6 列 int、spellbook schools 非空·cost≥0·effect〕+ `test_persuade_chance_readonly`〔唯讀不扣體力·公式一致〕+ `test_board_and_shop_view_shapes`〔board 卡 key==qid、shop 卡 key==iid·afford bool·唯讀〕)+ `sim_assassin` 零位移 + headless 截圖(桌面+480px:里程碑卡/抗性量表/法術書/攀談 chips/告示板卡+按鈕消失/商店面板+按鈕消失)+ **對抗審查 0 findings**。**加 sheet 專屬子檢視沿用此型樣;加可點服務面板=在 `ui.menu` 前 emit view(列 `data-key`=選單 key)。**

**新省份擴充:漢默法爾 Hammerfell(沙漠西環;承「下一步」轉玩法/內容;純資料 + 2 行測試 set)**:沿用黑沼澤配方加第 5 個可探索省。使用者拍板漢默法爾(唯一同時鄰賽羅迪爾金海岸+天際河彎地的省)→ 閉成「**賽↔漢↔天西方平行大環**」(對照黑沼澤閉南環),不淪走廊尾巴。Explore×2(拓樸/test 不變式)→ Plan×2(內容 + id 全驗證)→ 親自覆核全 gating 測試 → 直作 → 對抗審查 workflow(4 維×3 視角,**0 真 bug**)。
- **新 desert biome**(專屬生態,辨識度;唯二非資料改動=`test_detailing.py` 兩個 valid-biome set 各加 `"desert"`;combat `_biome_weight` 對任意 biome 通用)。元素軸=怪物**抗火、弱霜**(剋星=冰霜,操練冷門 frost build,鏡像沼澤毒/電)。
- **7 新節點**(`world.json`):城 森塔 sentinel/赫加西 hegathe、鎮 蓋蘭 gilane(province 漢默法爾,biome desert)、野外 阿利克爾沙漠 alikr_desert(desert)、邊境野外 龍尾山麓 dragontail_foothills(heartland)+布瑞納河谷 brena_valley(snow)、地城 沃倫菲爾 volenfell(desert,Dwemer)。**閉環邊**:anvil/kvatch+=dragontail_foothills、markarth+=brena_valley(雙向對稱)。**省內六學派齊**(sentinel+hegathe spell_stock,test_polish 鐵則)。
- **5 沙漠怪**(`bestiary.json`,biomes:["desert"],抗火弱霜):沙蠍(d2)/沙嘯獸(d3)/拉米亞(d4 電)/矮人蒸汽蜘蛛(d3)/**矮人百夫長(d5 boss,`raw`)**。`volenfell` 地城(`dungeons.json`,4 房+boss,寶藏含 dwarven_cuirass=地城專屬,**任務不給**)。
- **3 城主**(`rulers.json`,redguard,stance independent,bloc 王冠派 crowns/先鋒派 forebears,population+garrison) / **3 任務**(`quests.json`:屠遺城 board d4 gold400/fame20 守 cap、獵沙蠍 board、偵察 npc;沃倫菲爾有任務指向) / **7 NPC**(`npcs.json`,sentinel×3/hegathe×2/gilane×2,greeting+rumor) / **2 事件**(`events.json`:綠洲採集 forage + 沙下掠食 sneak check) / **2 地標**(`landmarks.json`:約凱石碑/黃銅遺珍)。
- **驗證**:39 模組全綠(test_world 雙向/連通/環、test_politics 新城 population/tax、test_polish 六學派齊/volenfell 有任務/forage 齊備、test_detailing biome 含 desert/reward caps 無 BIS)+ `sim_assassin` 零位移 + 無頭煙霧(spawn 5 怪+boss、desert 遭遇分流 371/600 主導且池不空、起手大道無 d3+ 沙漠怪洩漏、board 任務/forage/auto_resolve 無 traceback)+ **對抗審查 4 維 0 真 bug**(全為正向確認/誤報)。**加省純改 world+bestiary+dungeons+rulers+quests+npcs+events+landmarks 八檔;加新 biome 記得補 test_detailing 兩個 valid set。**

**成就系統 Achievements(榮譽印記;承「下一步」§6 最高 CP;唯讀推導、零存檔欄)**:世界內容已極豐,補一張「總驗收 + 重玩目標」清單。Explore×2(條件來源 + 顯示接點)→ Plan×1(內容 + 全 id 驗證)→ 直作 → 對抗審查 workflow(4 維×3 視角,**0 真 bug**)。
- **核心鐵律**:`achievements.earned(char, gamedata)→list` **純由角色最終狀態推導**(如 `mastery.unlocked`)—— **零新存檔欄、零遊戲迴圈鉤子、零 char 變動**;同一評估器在**傳奇結算**與**即時角色卡子檢視**通用、結果一致。**僅供表彰,不計入傳奇分數**(底層計數已計分,避免雙重計分;`legacy.compute` score 公式逐位元不變)。
- **`systems/achievements.py`**:`_IMPLEMENTED_TYPES` 白名單(20 種 cond.type;未實作 type→inert 過濾,鏡像 `mastery._defs`)+ `_eval(char,gd,cond)` 每 type 一分支(全 `getattr(...,default)` 防禦、缺漏/毀損 id 安全)+ `earned`/`earned_and_locked`/`_defs`。⚠️**循環**:`legacy` 頂層 import achievements → achievements 在 `pure_spec` 分支**就地 import legacy** 打破。**`pure_spec` 雙門檻**(`_PURE_SPEC_MIN=400` + 領先 150):初生角色起始職業偏向差距即達 ~150,故須加絕對門檻避免「創角即得」。
- **`data/achievements.json` 24 條**(跨戰鬥/探索/任務/公會/build/領地/暗黑/吸血/財富;難度分布;id 全驗證:kill_boss 怪∈bestiary、guildmaster 公會∈factions、allegiance/spec 合法)。**加成就純改 JSON(在已實作 type 內);加新 type=加分支+登錄白名單**。
- **顯示**:`gamedata.achievements` 載入;`legacy.compute` 回傳 `achievements:[名]`+`achievements_total`;`_legacy_view` 加「成就」section(達成 N/24+✦名;renderLegacy 自動渲,legacy 無 JS 改);`legacy_screen` 終端加成就行;**即時角色卡子檢視** `action_character_sheet` 加「成就」+ `sheet_achievements`(web `_emit_view("achievements",{earned,locked})` + 終端 rich;`index.html` `renderAchievements` 複用 `.mst-*` 卡)。
- **驗證**:**40 模組全綠**(新增 `test_achievements` 14 測:各 type 判定/**初生 earned==[]**/skill_cap 只認 base/guildmaster/pure_spec 不創角即得/**id 合法**/**未知 type inert**/**評估器唯讀**(to_dict 不變)/**傳奇列出但不計分**(murders 達成而 score 不變)/earned∪locked 全且不交)+ `sim_assassin` 零位移 + headless 截圖(傳奇成就段 11/24 + 角色卡成就子檢視 ✦/○,桌面+480px)+ **對抗審查 0 真 bug**(12 發現全正向確認)。

**更多開局背景(承「下一步」純資料 +6;開局 8→14)**:世界擴充後補上缺的「處境」。純改 `data/origins.json`(`creation.apply_origin` 只覆寫處境、不動屬性/技能;選單/快速開局/傳奇出身行**零程式改動**自動涵蓋)。Explore×2(apply_origin 接點 + test 不變式 + valid id 池)→ 直作 → 對抗審查 3 維 **0 findings**。
- **6 新開局**(全 danger-0 起點、起手裝備起始階非 BIS、金幣克制 15–70):`fighters_recruit`(白漫城·授戰士公會·鋼劍皮甲,補戰士公會開局)、`guild_thief`(裂谷城·授盜賊公會·匕首,補盜賊開局)、`alikr_blade`(森塔·用上新漢默法爾省·鋼劍盾)、`shipwreck_survivor`(安維爾·15金硬開局無賞金)、`temple_healer`(史金格拉德·授**heal**——`minor_heal` 人人皆有故避開)、`orc_outcast`(馬卡斯城·戰斧鐵甲)。
- **守則(已守)**:授會籍只挑無 unlock_event 且自洽的公會(mages/thieves/dark_brotherhood/**fighters_guild 單授**皆可;禁 knights_nine/mythic_dawn 需 `kvatch_falls`);`fighters_guild` 雖 lawful 但單授無起手賞金/無對立會籍 → 自洽。起點全 danger-0、所有 id 實查存在。
- **驗證**:40 模組全綠(既有 `test_origins` 自動驗證**全 14 開局**無數值變動/id 合法/穿戴持有/起點安全/存檔往返;新增 `test_new_origins_situational_distinctives` 釘 6 新開局特徵 + 把 3 個帶會籍的納入 roundtrip)+ 逐一建角煙霧(無 traceback、health==max、會籍/裝備/法術/金幣符合)+ `sim_assassin` 零位移 + **對抗審查 3 維 0 findings**。**加開局純改 `origins.json`(在 apply_origin 支援的處境欄內;勿動屬性/技能、勿授 unlock-gated 公會、起點勿 danger≥4)。**

**新省份擴充:高岩 High Rock(西北環 · 霧沼 moor · 電系剋星;承「下一步」轉玩法/內容;純資料八檔 + 2 行測試 set)**:沿用黑沼澤/漢默法爾配方加第 6 個可探索省。使用者拍板高岩(唯一同時鄰天際河彎地〔馬卡斯城〕+ 漢默法爾北境〔赫加西〕的省)→ 閉成「**西北環**」(對照黑沼澤南環、漢默法爾西環,世界第三個閉環),不淪走廊尾巴。Explore×3(拓樸/test 不變式/機制接點)→ plan-mode 核定 → 直作 → 對抗審查 workflow(4 維×每發現 3 視角,**0 真 bug**)。
- **全新元素軸(最重要的 build 鉤子)**:既有五省剋星只用過火(snow/swamp)與霜(ashland/desert)—— **電(shock)從未當過剋星**。高岩怪**抗魔/抗霜、弱電** → 操練全圖最冷門的雷系 destruction build。⚠️鐵律:`formulas.resist_multiplier` 對 shock∈MAGIC_ELEMENTS 會**疊 `magic` 鍵**(r=shock+magic),故「抗魔但弱電」的怪 `shock` 負值須夠負以蓋過 `magic` 正值才真弱電(招牌怪實測電傷係數 1.25–1.5×;有 `test_highrock_signature_creatures_weak_to_shock` 斷言鎖住,移除弱點→係數 0.75→紅)。**新 biome `moor`(霧沼)**:唯二非資料改動=`test_detailing.py` 兩個 valid-biome set 各加 `"moor"` + 新增高岩 flavor 斷言(與 desert 同模式)。
- **拓樸(純改 `world.json`,7 新節點 + 改 markarth/hegathe 各加 1 邊)**:城 匕落 daggerfall/威岩 wayrest、鎮 永恒城 evermore、野外 沃斯加荒沼 wrothgar_moor(d2)、地城 海妖岩巫窟 hag_rock(d4,**≥2 links 可穿越**)、邊境野外 巴薩拉隘 bangkorai_pass(d3,接赫加西)+卡斯特廢村 karthwasten(d2,接馬卡斯城)。**2 條外部邊**(karthwasten↔markarth、bangkorai_pass↔hegathe)→ 高岩位於全域循環(西北環:markarth↔karthwasten↔evermore↔wayrest↔daggerfall↔bangkorai_pass↔hegathe)。省內六學派齊(daggerfall+wayrest spell_stock,含電系破壞線供就地剋當地弱電怪)。
- **5 沼怪**(`bestiary.json`,biomes:["moor"]):沼地女巫(d2 起手怪)/石像鬼(d3 高甲)/鴉妖(d3 高速)/古墓鐵衛(d4 不死)/**海妖岩魔女(d5 boss,`raw`,**frost-immune 0.0×** → 逼用電)**。`hag_rock` 寶藏首度產出 ebony 整甲(`ebony_cuirass`/`ebony_shield`=地城專屬,任務不給)。
- **3 城主**(`rulers.json`,breton,**刻意跨省混合 stance**:匕落 independent/威岩 imperial/永恒 neutral,bloc 各王室) / **3 任務**(`quests.json`:清海妖岩 board d4 gold400/fame20 守 cap、獵女巫 board、刺探 npc) / **7 NPC**(daggerfall×3/wayrest×2/evermore×2,greeting+rumor;宮廷法師 rumor **教電剋弱點**,wayrest_scout 掛 favor_wayrest) / **2 事件**(荒沼採藥 forage + 霧中石影 sneak check) / **3 地標**(巨石巫圈/亞當斯精靈塔殘影〔**邊境節點**〕/魔女遺珍)。
- **驗證**:40 模組全綠(test_world 雙向/連通/環、test_politics 新城 population/tax、test_polish 六系齊/hag_rock 有任務/forage 齊備、test_detailing biome 含 moor/reward caps 無 BIS/**招牌怪實測弱電**/moor 生態分流、test_landmarks id 合法/無永久加成)+ `sim_assassin` 零位移(零戰鬥碼改動)+ 遭遇抽樣(moor 生態主導 57%、wrothgar_moor d2 不洩漏 d3+ 沼怪、boss tier 對齊既有 d5)+ 無頭煙霧(7 新地點面板/世界地圖/城主/NPC 渲染、地標 fire-once、forage/predator/board 按省過濾、海妖岩魔女戰)+ **對抗審查 4 維×3 視角 0 真 bug**(全為正向確認:電鉤完好/無套利/boss tier 正常/弱電斷言為真鎖)。**加省純改 world+bestiary+dungeons+rulers+quests+npcs+events+landmarks 八檔;新 biome 記得補 test_detailing 兩個 valid set。**

**Bug 修復:Web 結束無法重開 + 自立無法招兵買馬(使用者回報 2 bug → 雙 Explore 追因 → 修 → 對抗審查連帶修 2 處)**:
- **① 結束無法重開(重整也沒用)**:web 版 `tesrpg/web/server.py:_run_game` 原只跑 `main()` 一次 —— `main()` 一返回(離開遊戲 / 未捕捉例外)遊戲 thread 即死,前端 `index.html` 卻在 `end` 哨兵時提示「重新整理頁面可再啟一局」,但重整只是重連到已死的 thread → 永遠重開不了。修:`_run_game` 把 `main()` 包進 `while True`(`SystemExit` 才真結束;正常返回/例外 → `flush_final` 出 end 後**重啟一局**,下一輪主選單 prompt 立即覆蓋 end)→ web 永遠可重開。**終端模式零影響**(`_run_game` 為 web-only;`main()` 本就有自己的主選單迴圈,死亡/隱退後原地回主選單)。
- **② 自立無法招兵買馬**:`systems/warband.py:is_warlord` 原 = 武士銜 / 征服城 / 公會掌門;**自立稱雄者(allegiance 屬擴張派)對所有城為敵、無 thane 晉身之階**,又陷「要先征服一城才能組軍、卻要組軍才好攻城」死鎖。修:`is_warlord` 對 `politics.EXPANSIONIST_CAUSES`(={own 自立, daedric 神話黎明})回真 → 舉旗即可招兵(仍受金幣 `SOLDIER_COST` / 軍餉 / 永久傷亡牽制;**稅基紅線 `held_tax_cities` 只認 city_faction,不受影響** → 純加性不破平衡)。區域 import politics 避循環。
- **對抗審查(3 維×每發現 3 視角,4 發現→2 確認,皆連帶修)**:① **常駐 HUD 殘留(3/3)**——Fix① 讓主選單重現後,`console._hud_view` 仍讀前一局(已死角色)的 `_hud_state` → 主選單顯示死者血條/金幣。修:新增 `console.clear_hud()`,在 `main()` 主選單迴圈頂端呼叫(死亡重開 + 離開重啟皆清;終端無副作用)。② **daedric 同僵局(2/3)**——只修 own 會把神話黎明(daedric,亦 enemy-to-all、無 thane 路)留在同一死鎖 → 改用 `EXPANSIONIST_CAUSES` 一併解。(2 駁回:`while True` 熱迴圈誤報 —— `main()` 必先阻塞於主選單 prompt,崩潰前無從空轉。)
- **驗證**:40 模組全綠(`test_warband` 加 own/daedric→warlord、imperial/independent→否;`test_web` 加 `test_web_session_restartable_after_game_over` 驅動兩局證明可重開)+ 直驅 `server._run_game` 迴圈實測(離開→end→重啟主選單;HUD 重開後 `hud=None`)+ `sim_assassin` 零位移(未碰戰鬥)。**鐵律:web 任何「結束」路徑都靠 `_run_game` 迴圈重開;`is_warlord` 的擴張派資格走 `politics.EXPANSIONIST_CAUSES`(加新擴張大義自動涵蓋)。**

**新省份擴充:瓦倫森林 Valenwood(西南環 · 雨林 jungle · 火系剋星;承「下一步」純資料;八檔 + 2 行測試 set)**:第 7 個可探索省,沿用高岩配方。使用者拍板瓦倫森林(西南鄰賽羅迪爾金海岸 + 漢默法爾南岸)→ 閉成「**西南環**」(賽↔瓦↔漢,世界第四個閉環)。Explore 確認拓樸/id → 直作 → 對抗審查 workflow(4 維×每發現 3 視角,**0 真 bug**)。
- **元素軸=敵抗霜/抗毒、弱火(以烈焰焚林)**:刻意避開黑沼澤毒系重疊 —— 不做「毒剋星」(玩家少有毒傷法術),改讓雨林怪**弱火**(樹靈/絞藤/巨蛛 resist frost+poison、weak fire,實測火傷 1.3–1.55×)→ 操練火系 build;**威脅元素=毒**(怪攻擊帶毒 DoT → 須備毒抗/解毒,texture 與火剋星互補)。招牌怪刻意**不帶 magic 鍵**(fire∈MAGIC_ELEMENTS 會疊 magic),弱火乾淨;有 `test_valenwood_signature_creatures_weak_to_fire` 鎖住。**新 biome `jungle`(雨林)**:唯二非資料改動=`test_detailing` 兩個 valid set 各加 `"jungle"` + flavor 斷言。
- **拓樸(純改 `world.json`,7 新節點 + 改 anvil/gilane 各加 1 邊)**:城 法林斯提 falinesti(行走王都)/海文城 haven(海港)、鎮 希凡納 silvenar(綠約聖地)、野外 格拉特巨木林 graht_forest(d2)、地城 絞藤蛛巢 spider_grove(d4,**≥2 links 可穿越**)、邊境野外 斯特里德河谷 strid_vale(d2,接安維爾)+阿比西亞海岸 abecean_coast(d3,接蓋蘭)。**2 條外部邊**(strid_vale↔anvil、abecean_coast↔gilane)→ 位於全域循環(西南環:anvil↔strid_vale↔falinesti↔haven↔abecean_coast↔gilane)。省內六學派齊(falinesti+haven spell_stock,含火系破壞線供就地剋當地弱火怪)。
- **5 雨林怪**:絞殺藤蔓(d2 起手怪)/樹靈 spriggan(d3)/食人巨猿 imga(d3 高速 evasive)/叢林巨蛛(d4 毒)/**遠古樹靈 spriggan_matriarch(d5 boss,`raw`,**火傷 1.55×、毒免、抗霜** → 逼用火)**。`spider_grove` 寶藏首度產出**玻璃整甲**(`glass_cuirass`/`glass_shield`=馬拉凱特綠玉/波斯莫考據,地城專屬、任務不給)。
- **3 城主**(`rulers.json`,bosmer,跨省混合 stance:法林斯提 independent〔卡莫蘭王朝〕/海文 imperial〔海港商閥〕/希凡納 neutral〔綠約之聲〕) / **3 任務**(清絞藤蛛巢 board d4 gold400/fame20 守 cap、獵絞藤 board、探聖林 npc) / **7 NPC**(falinesti×3/haven×2/silvenar×2;綠約獵手 rumor **教火剋弱點**,haven_huntmaster 掛 favor_haven) / **2 事件**(巨木林採集 forage + 林蔭綠影 sneak check) / **3 地標**(艾爾登神木/埃雷德殘塔〔**邊境節點**〕/綠約遺珍)。
- **驗證**:40 模組全綠(test_world 雙向/連通/環、test_politics 新城 population/tax、test_polish 六系齊/spider_grove 有任務/forage 齊備、test_detailing biome 含 jungle/reward caps 無 BIS/招牌怪實測弱火/jungle 生態分流、test_landmarks)+ `sim_assassin` 零位移(零戰鬥碼)+ 遭遇抽樣(jungle 生態主導 53%、graht_forest d2 不洩漏 d3+、boss tier 對齊既有 d5)+ 無頭煙霧(7 面板/世界地圖/城主/NPC/地標 fire-once/事件按省過濾/board)+ **對抗審查 4 維×3 視角 0 真 bug**。**加省純改 world+bestiary+dungeons+rulers+quests+npcs+events+landmarks 八檔;新 biome 記得補 test_detailing 兩個 valid set。**

**拓展物品:法袍(法師布甲)+ 鍛造(新技能 + 金屬鍛造/裁縫 + 淬鍊強化)(使用者拍板:法袍純資料玻璃大砲 / 鍛造為獨立技能 / 加淬鍊)**:補兩缺口——法師無專屬裝備(只能穿戰士護甲/飾品拿魔力)、鍛造極淺(僅 4 條皮甲配方、借用 armorer 技能、無金屬鍛造/無強化)。Explore×3(裝備/附魔/鍛造引擎)→ plan-mode 核定 → 直作 → 對抗審查 workflow(4 維×3 視角,2 確認皆已修)。
- **法袍(純資料)**:`armor.json` 加 8 件布甲(學徒 `cloth` + 大法師 `archmage` 各 helmet/cuirass/gauntlets/boots),`weight_class:light`、armor_rating 0–2,每件靜態 `enchant`(魔力 `armor_fortify` / 法系技能 `fortify_skill`);`armor_sets.json` 加 cloth(magicka +40)/archmage(+70)套裝。**全程零碼**——複用 carrier-agnostic `inventory._apply_enchant`(armor 也吃 `fortify_skill`)+ 既有 4 槽套裝系統。niche=玻璃大砲(全套 +65/+95 魔力、護甲 ~0;對照精靈套裝 +30 魔力+護甲)。**刻意不加施法權衡**(重甲照舊不罰施法,使用者選純資料)。布甲/材料在帝都 Arcane University 有售(大法師袍高價 BIS·gold-gate)。
- **鍛造=第 23 技能**(`skills.json` `smithing`):learn-by-doing,mechanic=「解鎖更高階配方(`skill_req`)+ 淬鍊上限(`smithing//20`)」;**`armorer` 留作修理**(分工:鍛造=創造/強化、護甲修理=維修)。舊存檔走 `progression.ensure_all_skills` 自動補 `smithing=base`(同 scout 第 22 技能加法;`len(gd.skills)` 測試 22→23)。
- **鍛造/裁縫配方**(`recipes.json` 4→21):既有 4 皮甲 `skill` 由 armorer 改 smithing;加金屬鍛造(iron/steel 武器+護甲,inputs=`items.json` 新 `iron_ingot`/`steel_ingot`)+ 裁縫布甲(`bolt_of_cloth`→學徒布袍);`skill_req`(steel 25、裁縫 15)。**反套利**:所有非 wolf_pelt 配方 Σ原料價值 ≥ 產出價值(買料鍛造再賣必虧)+ 材料走有限商店。複用 `crafting.craft()`,加 `meets_skill_req` 一處小改。
- **淬鍊強化**(新 `systems/smithing.py` + 2 存檔欄):鐵匠處耗對應錠 + smithing practice → `weapon_temper`/`armor_temper`(item_id→級)永久 +傷害/+護甲值;cap=`smithing//20`(0–5);讀取鉤 `combat._weapon_profile`(+級×2 傷害)/`_armor_rating`(+級×1 護甲,flat),**僅玩家**(`_is_player`/怪走非玩家分支)、空 dict 加 0;**不計入售價**(無淬→賣套利)、與附魔正交可疊。`action_temper`(市集區「淬鍊強化 ⚒」)。
- **對抗審查 2 確認皆修**:① **淬鍊隨 item_id 殘留**(賣掉後重買同 id 免費續淬)→ 在 `inventory.remove_item` 最後一件離開背包時清掉該 id 淬鍊紀錄;② **大法師套裝無取得途徑**(死內容)→ 補進帝都 merchant_stock。
- **驗證**:41 模組全綠(新增 `test_smithing`:技能/配方合法/反套利/skill_req/布甲魔力+法系技能+套裝/淬鍊 consume+cap+戰鬥加成+僅玩家+不入售價+賣後清淬+存檔/大法師可達;`test_crafting` 改練 smithing;`test_assassin` 22→23)+ `sim_assassin` 零位移(淬鍊鉤對未淬鍊/怪加 0)+ 淬鍊平衡抽樣(cap 5=+10 傷/+5 甲,對 dremora 0.05→0.42 有界)+ 無頭煙霧(鍛造/淬鍊真選單)。**加配方/材料/布甲純改 JSON(守反套利:非 wolf_pelt 配方 Σ原料價值 ≥ 產出);加可淬材質改 `smithing._MATERIAL_INGOT`;調平衡改 smithing 常數/`skill_req`。**

**更高階金屬鍛造(承上輪鍛造;純資料 + 1 行 mapping)**:把鍛造從 iron/steel 補到全金屬階。`items.json` 加 4 高階錠(月長石/矮人金屬/熔煉綠玉/黑檀);`recipes.json` 加 24 條精靈/矮人/玻璃/黑檀鍛造配方(`skill_req` 分級 elven40/dwarven55/glass70/ebony85,inputs=對應錠、outputs=既有裝備);`smithing._MATERIAL_INGOT` 補 4 材質映射 → **全裝備階皆可淬鍊**(補上「最佳裝備無法強化」缺口,原僅 iron/steel/皮/布)。錠在帝都 + 馬卡斯城(矮人石城)有售。反套利:24 條配方 Σ原料價值 ≥ 產出(買料鍛造再賣必虧);平衡:ebony 滿淬(+10 傷)對 apex boss 仍 ~0–3%(cap 5 有界)。配方 21→45。驗證:41 模組全綠(`test_smithing` 加 high-tier 分級/可淬/可取得/e2e、`test_is_temperable` 玻璃改可淬)+ `sim_assassin` 零位移 + 對抗審查 3 維×3 視角 **0 真 bug**。**加更高階鍛造純改 items/recipes JSON + `_MATERIAL_INGOT` 一行。**

**Bug 修復:地城逃跑仍判定完成(逃首領戰可開寶箱、計清剿)**:`main.action_dungeon` 原只擋 `run_battle=='dead'`,`'fled'`(逃跑)落到勝利分支 → 逃離房間仍續探、**逃離首領戰仍開首領寶箱 + `record_dungeon_clear` + 結算任務**。修:房間/首領戰接住 `'fled'` → 提示後退出地城(`return None`),不開箱、不計清剿、不結算。新增 `test_dungeon`(逃首領不清剿/不開寶/不結算、逃房間退出、全勝仍正常清剿;**42 模組全綠**)。**鐵律:凡 `run_battle` 結果驅動「給獎/推進」者,務必同時處理 `'fled'` 與 `'dead'`**(event-combat 在 640 行不給清剿獎勵故不受影響)。

**撬鎖改制:需開鎖器 · 不耗時 · 低體力(使用者要求「開寶箱不耗時、體力消耗降低,但需要開鎖器」)**:把撬鎖的反 min-max 閘從「時間+體力」改為「金幣換的消耗品(開鎖器)」。
- **核心**(`systems/dungeon.py:pick_lock`):撬鎖**需背包有 `lockpick`(開鎖器)**、**不耗時**(hours 恆 0)、僅扣少量體力(`LOCKPICK_FATIGUE=2`;原為 security practice 5 體力 + 1 時)、**成功才給 security xp**。塔之鑰招牌仍免開鎖器/免體力/免耗時。`main._resolve_container`:無開鎖器則提示不開、重試迴圈於開鎖器用盡(`no_pick`)收手。
- **來源**:新 `items.json` `lockpick`(value 6、weight 0);**起始 12 根**(`creation` 起始包,test_origins 只查特定物品數故安全)+ 布魯瑪/帝都/裂谷城有售(weight 0 可囤)。
- **對抗審查抓到並修掉 1 真 major(2/3)**:初版「**僅失敗折斷**」→ 95% 成功者近乎免費刷 security(成功不耗 + 容器跨地城重撬不標已搜)。改為**每次嘗試都耗一根開鎖器(成功也耗)** → 每筆 security xp 都付一根開鎖器(金幣閘),杜絕免費刷。(4 駁回:far-province 無在地賣家=非永久卡死〔世界連通〕、低技能耗鎖=刻意難度、逃犯開局有鎖=既有 append 設計、測試未覆蓋=已補。)
- **驗證**:42 模組全綠(`test_practice_cost` 撬鎖測試改寫:需鎖/不耗時/低體力/**每次耗一根·成功也耗·xp 金幣閘**/失敗折斷不給 xp/迴圈受開鎖器數限;`test_world`/`test_dungeon` 給開鎖器)+ 無頭煙霧(無鎖→不開、有鎖→開且不推進時間)+ 對抗審查 3 維×3 視角(5 發現→1 確認已修)。**鐵律:撬鎖成本走開鎖器消耗(每次嘗試一根)+ 少量體力,絕不重新引入「免費重撬刷 security」;調平衡改 `dungeon.LOCKPICK_FATIGUE`/開鎖器售價;塔之鑰例外保留。**

**口才平衡修正 + 拓展用途(使用者:「口才技能的平衡性評估」→ 評估發現說服被賄賂壓制、用途狹窄 → 核心修正 + 拓展)**:評估結論=口才旗艦機制 persuade(+10/耗體力時間/失敗−5)被 bribe(10 金→+12/即時/免技能)**完全壓制**,非城戰玩家無理由練;技能名裡的「威嚇」幾乎沒實作。
- **核心修正**(`systems/dialogue.py:persuade_delta(skill)=round(6+skill×0.12)`,0→+6/50→+12/100→+18):persuade 成功(及「辯舌·折服」里程碑)好感增益**隨口才成長** → 技能 ≥50 追平/超越 bribe(+12)**且免金幣**;**bribe 不動**(免技能金幣退路)。persuade 仍付 speechcraft practice(反 min-max 不破);`action_talk` 顯示「成功 +N 好感」。
- **拓展①·說服衛兵減賞金**(`dialogue.talk_down_guard` + `main.guard_confrontation`):小額賞金(≤`TALK_DOWN_MAX=120`)可試以口才說退衛兵(成功率吃口才/魅力、賞金越高越難,夾 0.05–0.80);付 speechcraft practice、成功 `crime.clear_bounty`、**失敗該次收回選項**(逼 pay/jail/resist,不可無限重說)。對位武士特權(武士免、非武士靠技能,皆有界)。
- **拓展②·威嚇喝退弱敵**(`dialogue.intimidate`/`can_intimidate`/`INTIMIDATABLE={"bandit"}` + `main.offer_battle`):全為弱人形盜匪時可「威嚇喝退」避戰(成功率吃口才/敵數/夜間);付 practice、成功避戰(**無戰利/擊殺/xp 來自敵 → 非刷取**)、失敗接戰(`alerted=True`)。對位潛行撤退(潛行=溜走、口才=喝退),落實「威嚇」。
- **驗證**:43 模組全綠(新 `test_speechcraft`:delta 分級 + 高技能 > bribe / persuade 仍付 practice / talk-down 小額成功清零·失敗不清·越高越難·付 practice / intimidate 閘〔野獸·不死·boss·混敵不可〕·避戰無戰利·付 practice)+ `sim_assassin` 零位移(intimidate 只多避戰出口、零戰鬥數值改)+ 無頭煙霧(說服顯示 +N、衛兵說退、bandit 有威嚇選項·wolf 無)+ **對抗審查 4 維×3 視角 0 真 bug**(talk-down 清小額賞金經判為合法設計,同 jail/武士特權;失敗即逼 pay/jail/resist 無免費重試)。**零新存檔欄位、零戰鬥數值改動;加可威嚇敵改 `dialogue.INTIMIDATABLE`,調平衡改 `persuade_delta`/`TALK_DOWN_MAX`/`intimidate_chance` 常數;bribe 刻意不動(金幣退路)。**

**斯庫瑪/月糖成癮系統 + 艾爾斯維爾省(里程碑級;新機制仿吸血鬼 + 第八省純資料;評估→直作→對抗審查修 1 真 bug)**:第八省貓人故鄉,與其招牌毒品出口「斯庫瑪/月糖」綁定的 power↔curse 成癮機制。
- **斯庫瑪成癮(`systems/skooma.py`,仿 vampirism 狀態機)**:服月糖(弱)/斯庫瑪(強)→ 限時亢奮(速度/敏捷/意志 +8 + 一次性回復;**刻意不碰力量/潛行/武傷** → 結構性規避刺客秒殺紅線,sneak 估傷亢奮前後不變)→ 每劑 +1 成癮且耐受縮短該次亢奮(`TOLERANCE_FACTOR`)→ 成癮達 `WITHDRAWAL_THRESHOLD=3` 後清醒即戒斷(力量/意志/敏捷/耐力負層,**體力上限隨之下滑**;**強度由成癮深度推導、非距上次用藥** → 與衰減 ratchet 不打架、單調易測)。戒除二途:長期清醒衰減(ride-it-out,`CLEAN_DECAY_DAYS`)或神殿淨糖之儀(`quest_skooma_cure`,複用任務引擎)。
- **存檔/接點**:Character +5 欄(`skooma_addiction/high_until/last_dose_hour/attr_bonus/skill_bonus`,dataclass 預設向後相容、進 to_dict);`attr()/skill()` 疊第三層、`base_*` 不動(鐵律);`skooma.ensure_skooma_fields` 接 `state.from_dict`(載入依當前時間重算層);`skooma.update` 掛 game_loop(在 vampirism 之後);服用走 `_item_actions` 的 dose 動作(推進 1 時、扣物品);`action_skooma_cure`(成癮者於任一城鎮廣場可見,儀式呼 `skooma.cure` 並移出 completed → 可重複)。UI status 標 + `sheet_skooma` + legacy「癮疾」+ 成就 `moon_addict`。**月糖同時是煉金材料**(ingredients.json),斯庫瑪 `kind:"drug"`(items.json)。
- **艾爾斯維爾省(純資料,鏡像瓦倫森林)**:`savanna` biome、**弱毒生態軸**(首個 poison 弱點省 → 回饋塗毒/煉金刺客;poison ∉ MAGIC_ELEMENTS 不疊 magic 鍵,負抗即放大傷害)。7 新節點閉合**南方大環**(`niben_marsh↔topal_bay↔rimmen…senchal↔pellitine_marches↔haven`,獨立於舊 `anvil↔strid_vale` 臂)。瑞門(安納奎那戰族城)/森查爾(佩萊泰恩不夜港,唯一賣 skooma)/托瓦爾(瑪恩聖城)+ 騰瑪林 + 暗月窟(dro-m'Athra 祭壇,boss `dark_moon_senche` solo+raw 掉黑檀劍+斯庫瑪)。3 khajiit 城主、6 弱毒怪、7 NPC、4 任務(含淨糖之儀)、2 風味事件、3 地標。
- **對抗審查(6 維 fan-out × 每發現獨立懷疑者驗證;9 agent)→ 1 確認真 bug**:**免費解癮漏洞**(完成淨糖採集但不行儀式、改以衰減自然戒掉 → 殘留的已完成任務在日後再成癮時免費解癮)。修:`skooma.update` 於「自然戒除(clean 轉變)」時 `_discard_cure_quest` 棄置殘留任務(active+completed)→ 每次成癮須重新賺取;補回歸測試。餘皆 dismiss(含一則過時 docstring 的 nit)。
- **驗證**:44 測試模組全綠(新 `test_skooma` 13 例:亢奮有效非 base / 增益流進體力上限 / 成癮起戒斷 / 越深越痛 / 再用藥解戒斷但加深(耐受)/ ride-it-out 衰減 / cure 清空 / 解咒可重複 / **免費解癮漏洞回歸** / **亢奮不碰力量·潛行(紅線守門)** / 存檔 round-trip / 舊存檔遷移 / legacy;`test_detailing` +2 弱毒/分流;`test_world` +南環)+ `sim_assassin` 紅線不變(solo boss 0% 秒殺)+ **亢奮生效下 sneak 估傷不變** + 無頭煙霧(Elsweyr 面板/暗虎戰/亢奮·成癮·戒斷·解癮/存讀檔)。**加省純改 world/rulers/bestiary/dungeons/npcs/quests/events/landmarks JSON;調成癮平衡只動 skooma.py 常數。**

**法師體力資源對稱化(施法接上體力系統 + 法袍省體;§6 #4 直作 → 對抗審查修 1 minor)**:三系資源原本不對稱 —— 近戰/格擋/隱遁耗體力且低體力降命中,但**施法只耗魔力、從不碰體力**(體力是法師的死資源)。本輪鏡像近戰兩機制接上施法,純規則層、零存檔欄位。
- **施法耗體力**(`magic.spell_fatigue_cost`):`(CAST_FATIGUE_BASE3 + PER_MAGICKA0.15×effective_cost) × fatigue_cost_factor(運動) × 法袍折扣`,最低 1。`cast()` 扣魔力後扣體力(玩家專用 —— 敵人/召喚走 `combat.resolve_attack` 不經此);因基於 `effective_cost`,**過載自動更耗體力**。實測:flames 5 / fireball 7 / fire_storm 9,起手法師(150)約 30 cast 才力竭。
- **低體力降法效**(`formulas.cast_fatigue_power_factor`):力竭時 `_power` ×0.75(滿體×1.0;鏡像近戰低體力降命中的 −0.25,法術不擲命中故改削威力)。對 damage/AoE/heal/shield/**summon** 一致(召喚物 HP 同步;審查抓到 summon 漏接已補)。0 體力**不 fizzle**、體力夾 0(對稱近戰)。
- **法袍省體做進布甲系統**(使用者要求):穿滿整套法袍(cloth/archmage 同材質四件)→ 施法體力消耗打折(armor_sets.json `bonus` 加 `cast_fatigue_factor`:學徒 0.80 / 大法師 0.65;`inventory.cast_fatigue_factor` on-the-fly 讀套裝、零存檔欄位;**只折體力不折魔力**)。法袍成為法師的對應裝甲(戰士重甲、法師法袍)。
- **鐵律/接點**:只動戰鬥消耗與 `_power`,**不碰 base_*/技能門檻/sneak/武器傷害**(刺客 `SOLO_SNEAK_DAMAGE_CAP` 不受影響,sim 零位移);調平衡只動 `formulas.CAST_FATIGUE_*` 常數或 armor_sets 的 `cast_fatigue_factor`。施法與 practice-cost 路徑互斥不雙扣;`restore_mind` 淨 +35。
- **驗證**:44 測試模組全綠(`test_magic` +9 例:扣體力/隨魔耗成長/運動降耗/低體力降法效/0體力不失敗/召喚同步力竭/restore_mind 淨正/戰外耗體/法袍折扣〔3 件無折扣〕)+ `sim_assassin` 紅線零位移 + 起手法師續航微斷言(≥20 cast)+ 無頭煙霧(實戰施法扣體力 + 戰外施法扣體力 + 法袍更省)+ 對抗審查(5 維,1 minor=summon 漏接 power,已補)。

**附魔系統擴展(護甲→技能/抗性 + 武器→命中觸發狀態;§1/裝備後續 直作 → 對抗審查 0 真 bug、1 nit)**:附魔原本只有 武器=元素傷害、護甲=fortify 資源、飾品=skill/attr/resist/res。本輪把附魔做成真 build 引擎,**大量複用既有機制、零存檔欄位**。
- **護甲→技能/抗性**:`synth.encha` 由 4 段擴成 5 段 `encha|base|kind|param|mag`(kind res/skill/resist),`synthesize` **依段數分流**保舊式 4 段向後相容(舊存檔零位移);`res` 刻意保留 `armor_fortify` 鍵(`armor_fortify_totals`/資源路徑不變)、skill/resist 複用飾品同形 dict → `inventory._apply_enchant` 已認得,**零彙整改動**。`enchanting.enchant_armor(kind,param)` 泛化 + `armor_magnitude`(skill factor 1.5 / resist 4.0,**略低於飾品** 2.0/5.0 → 飾品仍是首選載體、軟化多件疊加);**刻意不開放護甲 attr**。鐵律:fortify 只進 `equip_skill_bonus`(`skill()` 讀、`base_skill()` 不讀)→ 絕不污染成長/里程碑門檻。
- **武器→命中觸發狀態**:新 `synth.enchws|base|status|mag|turns`(`enchw` 元素式不動);`enchant_weapon_status`(vampiric/paralyze/regen)。combat `resolve_attack` 傷害結算後加**玩家專屬** `weapon_status` hook:**吸血**=造成傷害 30%(`formulas.WEAPON_VAMPIRIC_FRACTION`,夾實傷+血上限,每擊觸發故壓低)、**再生**=對自身上 regen self-HoT(`source:"ench_regen"` 去重不疊)、**麻痺**=10% proc/1 回合(`WEAPON_PARALYZE_PROC`),🔴 **solo BOSS 完全免疫附魔麻痺**(`_is_solo` gate,比照偷襲秒殺夾限的反鎖王紅線)、已麻痺中不重複套。event 加 `lifesteal` 供敘事。
- **接點**:`main.action_enchant` 護甲加 kind 子選單、武器加 元素/狀態 子選單;`ui.combat_event` 加吸血/麻痺敘事。任何武器 archetype 皆可附(同元素附魔)。命中狀態玩家專屬(敵人走 `attacker.attack` 不碰)。
- **驗證**:44 測試模組全綠(`test_equipment` +6:護甲技能/抗性/資源(仍走 armor_fortify_totals)/舊式 4 段相容/流程消耗魂石/存讀檔;`test_magic` +5:吸血回血夾實傷/再生去重+tick/麻痺對非 solo 生效/**麻痺對 solo boss 400 擊永不生效**/enchws round-trip;`test_m14` 改新簽名)+ `sim_assassin` 紅線零位移 + 無頭煙霧(護甲技能附魔升 skill、吸血劍實戰回血)+ 對抗審查 6 維(0 真 bug,1 nit=麻痺敘事誤標已修)。**加附魔型別純改 synth/enchanting/UI 三點;調平衡只動 `formulas.WEAPON_*` 或 `armor_magnitude` factor。**

**商店/經濟打磨 + 全城武士化(使用者實機回饋逐項修)**:
- **開鎖器=盜賊公會的營生**:從原本散落各城一般商店,改為**只在有 `thieves_guild` 服務的城販售**(8 城/7 省;漢默法爾無公會→靠野外);`world.buy_price` 對非會員加價(`LOCKPICK_OUTSIDER_MARKUP=2.0`,敵對買得到但較貴);**野外可隨機撿到**(強盜掉落 0.35 + 探索事件 `discarded_lockpick`)。`test_world.test_lockpick_is_thieves_guild_good` 守門。
- **商店批量 + 連購**:`action_shop` 買/賣加數量提示(複用 `ui.ask_int`,上限由 庫存·金幣·負重 / 持有量 夾;單件略過);買/賣改**內層迴圈停留在清單**,可連續買賣多樣不同商品,退一層才回模式選單。
- **全城武士化**:見 §6 #0「全城武士化」—— `court.generate_ruler_commissions` 程序化讓 33 城全可受封 + 重點城(帝都/白漫/維威克)手寫考據委託。

**狼人化 / 獸形(里程碑級;吸血鬼的對位機制;評估 pre-mortem→直作→對抗審查修 4 真 bug)**:第二條 power↔curse 天平,但**刻意與吸血鬼互補而非複製** —— 吸血鬼=被動飢渴階級詛咒;狼人=**主動限時「獸形 Beast Form」變身**(化為猛獸:利爪 + 巨量生命/體力/速度,但**脫去整套裝備、無法施法/用物/格擋**;吞噬獵物續時、變回有力竭代價)。兩者**互斥**(皆屬疾病)。核心全在 `systems/lycanthropy.py`(仿 vampirism + skooma 計時)。先跑**設計 pre-mortem workflow**(5 維 41 發現,逐一覆核確認 ~15 真缺口、擋下 1 誤報的錯誤修法),再實作。
- **狀態機**:Character +10 欄(`is_werewolf`/`werewolf_infected_day`/**`beast_form` 快取布林**/`beast_form_until` 計時/`beast_feeds`/`werewolf_total_feeds`/`werewolf_attr/skill/resist`/`werewolf_health_bonus`,dataclass 預設向後相容、進 to_dict)。`attr()/skill()/magic.entity_resist` 疊第 5 層、`base_*` 不動(鐵律)。`update` 掛 game_loop(vampirism→skooma**之後**)驅動 潛伏轉化 / 獸形過期變回(力竭 + 夾血)。**`beast_form` 快取布林**=combat 讀取的單一真實來源(`resolve_attack` 無 state 參數);與 `beast_form_until` 由 transform/revert/update/ensure/**`sync_beast_form`** 同步維護。
- **獸形透過 powers 槽**(復用 `vampiric_drain` 管線):`power_id` 對狼人回 `"beast_form"`(獸形中回 None,不可重變身),`powers.use` 加 `transform` 分派 → 每日一次冷卻;戰鬥選單獸形時只留 爪擊/變回人形/逃跑。**裝備抑制**(讓權衡成真):`resolve_attack` 內 `beast` 分支覆蓋 ~7 處 `attacker.weapon` 讀取(武器/淬鍊/元素附魔/命中狀態附魔/塗毒/耐久/速度/攻擊耗體技能),`_armor_rating` 回自然護甲、`_weapon_profile` 回 `beast_claws`(無附魔/淬鍊);`combat.eff_weapon_id`/`effective_weapon_name` helper;`estimate_sneak_damage` 同步用獸爪流派 + 不吃偷襲倍率。
- **🔴 紅線(偷襲不可秒 solo boss)**:獸形**必須**放大力量(與吸血鬼/斯庫瑪刻意不碰 strength 不同),但結構性免疫 —— 獸形與潛行互斥(咆哮現身),獸形攻擊**永不吃偷襲倍率**:`resolve_attack` 的 `sneaking = sneak_attack and _is_player(attacker) and not beast`(防禦縱深)+ `run_battle` 攻擊端 `opening and not beast_form`。人形 afflicted 零屬性加成(只疾病免疫)→ scout 估傷不受影響。`sim_assassin` 零位移(solo boss 全 0% 秒殺)+ 獸形抽樣:贏正常/中階(2.8–8.5 回合,絕不一刀)、脫甲故無法 solo elite/boss(no-heal sim)= 真權衡。
- **感染雙途 + 解咒 + 開局**:野外狼人敵(`werewolf` d3 / `werewolf_alpha` solo)`attack.infect_kind:"lycanthropy"`,`combat` 回傳 kind、`run_battle` 分派(舊吸血鬼敵無 kind→預設 vampire,向後相容);戰友團內圈(rank≥2)**獸血儀式** `_beast_blood_ritual`;`beast_blooded` 開局。互斥**雙向硬化**:`vampirism.susceptible` 排除狼人、`lycanthropy.contract/susceptible` 排除吸血鬼、儀式/開局設旗前 `not is_vampire`。解咒 `cure_lycanthropy`(source `werewolf_cure`,廣場僅狼人可見、可重複)。devour 續時封 `MAX_FEEDS_PER_FORM`(防無限獸形)。legacy「獸血」行 + 成就(獸血詛咒/月下獵手)+ status 標 + `sheet_lycanthropy` + 獸形入城 shunning。
- **對抗審查(實作後 5 維×每發現獨立懷疑者驗證;7 發現→5 確認 / 2 駁回)**:5 確認皆 major、皆已修 —— ① **獸形快取脫鉤**(旅行/休息在同一動作內推進時間過獸形時效、game_loop update 尚未刷新 → 以過期獸形作戰)→ 加 `sync_beast_form` 於 run_battle/offer_battle 進入點對齊;② `estimate_sneak_damage` 獸形未守門(用裝備武器流派 + 套偷襲倍率,**僅顯示層誤導、實傷不受影響**)→ 用獸爪流派 + `not beast` 守門;③ `player_attack_cost` 武器技能讀 `player.weapon` 而非 `wid`(latent,獸形 hand_to_hand 加 fatigue mod 時才現)→ 改 `wid`;④ 塗毒未加 `not beast` 守門(獸爪不沾毒)→ 補。2 駁回(apply_origin 單次呼叫不會雙旗衝突、`.remove` 已由 `is_done` 守)皆正確。
- **驗證**:**45 測試模組全綠**(新 `test_lycanthropy` 18 測:感染轉化/變身加成有效非 base/變回夾血+力竭/🔴 獸形不偷襲+單擊遠低於 boss 血/人形估傷不變/**獸形估傷不灌水**/**快取脫鉤回歸**/裝備抑制/互斥雙向/infect_kind 向後相容/devour 封頂/powers 槽冷卻/解咒可重複+source 過濾/存讀檔+過期自動變回/legacy+成就/開局)+ `sim_assassin` 零位移 + 無頭煙霧(offer_battle→變身爪擊勝利續時→過期 sync 變回→解咒→存讀檔→legacy)。**鐵律**:combat 讀 `beast_form` 快取布林、進戰前 `sync_beast_form` 對齊;獸形攻擊絕不偷襲(雙重守門,改務必重跑 sim);加狼人敵純改 bestiary(`infect_kind`);調獸形強度只動 `lycanthropy.BEAST_*` 常數。

**狼人深化(承上輪「下一步」;餵食進程 + 恫嚇之嚎 + 獵者之戒;直作 → 對抗審查修 2 真 bug)**:把狼人從「單一強度」做成**有成長弧的 build** —— 主題「獸血隨狩獵成長」。
- **餵食進程(零新存檔欄,由 `werewolf_total_feeds` 累計推導,同 mastery 門檻模式)**:`FEED_TIERS=[10,25,50,100]` → 5 階(獸血初醒→壯碩巨狼→嗜血狂獸→野性之王→血月之主);`beast_attr/beast_health/claw_bonus/beast_duration/max_feeds` 皆**隨階回傳**(階 0 = 原 base 常數,既有測試零位移)。`apply_to_character`/`transform`/`devour`/`combat._weapon_profile` 改呼叫這些 getter。**吞噬即時滋長**:`devour` 跨階即 `apply_to_character` 重算屬性/生命上限(對抗審查抓到:原停留變身時的階 + 回血未隨階 → 已修為 `beast_health(char)//2` 並重算)。
- **恫嚇之嚎(`lycanthropy.howl`)**:達 `HOWL_TIER=2` 解鎖的獸形戰技 —— 使所有存活**非 solo** 敵恐懼(`magic.fear`),耗 `HOWL_FATIGUE=25` 體力(無新存檔欄)。🔴 **solo boss 免疫**(`combat._is_solo` gate,比照武器麻痺/偷襲夾限的反鎖王紅線,杜絕嚎叫永控 boss)。戰鬥選單獸形分支加「恫嚇之嚎」選項 + `run_battle` 加 `howl` 分派。
- **獵者之戒(具名神器 `hircine_ring`)**:`werewolf_alpha` 掉落(chance 0.5;**resale 壓至 250 防農** —— d4 elite 不該印鈔);`hircine:true` 旗標,`lycanthropy.has_hircine_ring` 讀穿戴飾品;`powers.available` 對 `beast_form` **繞過每日冷卻**(穿戴時可隨意變身)→ 唯一觸碰 powers 冷卻的特例。
- **平衡(sim 背書)**:apex 滿階(階 4,獸形 str 142、獸爪 20)單記**非偷襲**爪擊最壞 ~48 ≪ 最小 solo boss 158 血 → 仍多回合不秒;`sim_assassin` 零位移、solo boss 全 0% 秒殺(獸形與偷襲互斥的雙重守門未變)。
- **對抗審查(3 維×每發現獨立懷疑者;2 確認 major 全修、0 駁回)**:① devour 回血用固定 `BEAST_HEALTH//2` 未隨階;② devour 跨階未重算屬性/生命(與 `max_feeds` live-tier 不一致)。**一處修(devour 加 `apply_to_character` + `beast_health(char)//2`)同時解兩者** + 補回歸測試。
- **驗證**:45 測試模組全綠(`test_lycanthropy` 擴至 23 測:階推導/獸爪隨階/嚎叫懼非 solo·solo 免疫·耗體力/獵者之戒繞冷卻/**跨階即時重算+回血隨階回歸**/apex 滿階單擊不秒 boss)+ `sim_assassin` 零位移 + 無頭煙霧(群戰嚎叫→爪擊勝利、戴戒再變身、sheet 階+進度渲染)。**鐵律**:獸血階純由 `werewolf_total_feeds` 推導(零存檔欄);調進程改 `lycanthropy.FEED_TIERS`/`_TIER_*` 表;新 `_TIER_*` 表長度須 = `len(FEED_TIERS)+1`;嚎叫 solo 免疫是反鎖王紅線;獵者之戒是唯一繞 powers 冷卻的特例。

**同伴系統深化(承「下一步」;持久 HP + 負傷 benched + 羈絆;直作 → 對抗審查修 4 防禦缺口)**:補 §7 既有限制「同伴每戰滿血重生、無持久 HP」。核心新模組 `systems/party.py`。
- **持久 HP**:`companion_hp`(cid→當前 HP,Character 新欄,預設 {} 向後相容)每場戰後由 `party.record_after_battle` 回寫;`combat.spawn_companion(…, current_hp=, max_health_bonus=)` 以持久值生成(夾上限)。倒下(HP≤0)→ **負傷 benched**:`party.fieldable` 排除、`run_battle` 不上陣,須**休息/旅店過夜**(`party.heal`/`heal_full`)康復才能再戰。**冒險模式正常戰鬥不永久死亡**(維持 §7 寬容);**攻城仍永久折損**(`warband.apply_casualties` 不變,另 `party.forget` 清持久狀態)。
- **羈絆**:`companion_bond`(cid→點)由 `party.award_victory` 在**並肩獲勝**時 +1(僅存活者);達 `BOND_TIERS=[5,15,30]` 升級(雇傭→同袍→摯友→生死之交),每級 `BOND_HP_PER_TIER=12` 提升該同伴 max_health(更願為信任的領袖死戰)。同伴永遠是盟友,**不碰玩家偷襲紅線**(`sim_assassin` 零位移)。legacy 加「羈絆」行 + 計分(`bond_tier×20`)。
- **接點**:`action_party`(hub 人物群「隊伍 ⚔」,僅有同伴時現)檢視 HP/羈絆/負傷 + 就地解散(`_dismiss_mercenary` 加 `party.forget`);`action_rest`/`action_inn` 一併回復同伴;`ui.party_panel`。**鐵律**:同伴離隊(解散/陣亡)務必 `party.forget` 清 `companion_hp`/`companion_bond`(防殘留羈絆殘影);footman(troop)在 `soldiers` 不在 `companions` → record/award 以 `cid not in char.companions` 略過(**勿**改 `field_ids` 排除 troop,否則攻城無兵可上)。
- **對抗審查(3 維×每發現獨立懷疑者;7 發現→5 確認 / 2 駁回)**:駁回 2 個正向(footman 走防禦檢查=刻意設計;倒下同伴的既得羈絆計入結算=刻意,羈絆是一生情誼)。**4 個防禦缺口已修**:① `current_hp` 未夾下界(毀損存檔負值)→ `max(0,…)`;② `heal` 未消化負值 → 夾 [0,上限];③ `legacy_label` 取 `companions∪companion_bond` 會列殘留羈絆 → 只認 `char.companions`;④ `_party_label`/`party_panel` 直取 `gamedata.companions[cid]` 對毀損存檔 id 會 KeyError → `.get` 退回。
- **驗證**:**46 測試模組全綠**(新 `test_party` 10 測:持久 HP 生成+回寫/倒下 benched+康復/羈絆隨勝累積+加耐久/陣亡不得羈絆/heal_full+forget/攻城 forget/legacy/存讀檔+舊存檔預設/**防禦夾限+殘影回歸**/**毀損 id 不崩**)+ `sim_assassin` 零位移 + 無頭煙霧(實戰 HP 持久 78、羈絆 +1、倒下 benched、康復、legacy 羈絆行)。**鐵律**:同伴 HP/羈絆只走 `party.*`;調平衡改 `party.BOND_TIERS`/`BOND_HP_PER_TIER`/`spawn_companion` 不破玩家戰鬥(allies-only)。

**補屬性功能缺口:意志/幸運 名實相符(承「中庸職業功能性評估」;使用者拍板「功能性區分,非數值加成」;直作 → 對抗審查 0 真 bug)**:功能審計發現八屬性中**意志只給體力(治理三大魔法卻無施法價值)**、**幸運近乎死屬性(只微調隨機事件)**。本輪給兩者**名實相符的機制角色**,讓升級每點都有意義。
- **🔑 鐵律:所有新係數在屬性 = `BASE_ATTRIBUTE`(40)時回中性值**(=改前行為)→ 預設角色與 `sim_assassin`(base 40)**零位移**、平衡基線不動;唯有投資到 40 以上才生效(每點有意義又無平白 power creep)。全部新函式集中 `formulas.py`(`magicka_regen_combat`/`magicka_regen_rest_factor`/`mind_resist_chance`/`luck_loot_factor`/`luck_fortune` + 對應 `*_PER`/`*_CAP` 常數),調平衡只動這些。
- **意志 willpower → 施法續航 + 精神韌性**(法師的續戰/定力,與智力的「魔力池大小」正交):① **戰鬥每回合被動回魔**(`run_battle` 回合末,0 @≤40 → +5/回合 cap,**跳過巨魔像座 atronach**、夾 max_magicka、**僅玩家**);② **休息回魔速率隨意志**(`action_rest` ×factor;旅店為全回復故不動);③ **抗恐懼/麻痺**(`magic.resisted_mind(entity,status,rng)` 玩家專屬、**僅 fear/paralyze**,接 `combat.resolve_attack` 怪物 on_hit→玩家施狀態處)。
- **幸運 luck → 天命(成敗擲骰的隱形之手)**:① **戰利豐厚**(`loot.resolve_loot` 加 `luck_factor`:掉落機率夾 ≤1.0×factor + 金幣×factor;`combat.grant_loot`/`dungeon.open_container` 傳玩家幸運,怪物/中性掉落=1.0);② **時來運轉**(`luck_fortune` 加性微升撬鎖 `effective_pick_lock_chance`、逃跑 `try_flee`、事件 `events.check_chance` 統一口徑)。**刻意不碰玩家近戰傷害/偷襲** → 與 `SOLO_SNEAK_DAMAGE_CAP` 紅線完全解耦。
- **UI**:`formulas.ATTRIBUTE_FUNCTION` 表 + 升級分配選單每屬性後綴「作用」(讓玩家知道每點意義)。**幅度**(投資至 100):戰利 +30%、戰鬥回魔 +4/回合、休息回魔 2×、抗心智 50%、命運 +0.10;均夾 cap。
- **驗證**:**47 測試模組全綠**(新 `test_attributes` 7 測:base-40 中性 + 夾限/戰利倍率進 resolve+grant_loot/撬鎖+逃跑隨幸運/`resisted_mind` 僅玩家僅心智/高意志較不易被恐懼)+ `sim_assassin` **零位移**(solo boss 全 0%)+ 高意志法師戰鬥回魔煙霧(空魔力→戰後回魔、意志40 對照恆 0)。**對抗審查 3 維×每發現獨立懷疑者:0 真 bug**(base-40 中性 + 紅線解耦 + 夾限 + 玩家專屬,結構上無破口)。**鐵律**:零新存檔欄(純讀既有 `attr`);加屬性功能改 `formulas.*_PER/*_CAP`;意志/幸運**永不碰玩家近戰傷害**(守紅線)。

**法術/武技做四中庸職業功能性區分(承「中庸職業功能性評估」;使用者拍板「功能性區分而非數值加成」+「四中庸全做」;直作 → 對抗審查 5 確認全修 + 1 駁回 + 1 既定設計)**:純流(戰士/法師/盜賊)有套裝+里程碑身份,四中庸入遊戲後**機制無別**(只差起手技能)。本輪用**新增法術**(資料驅動,複用 `magic.cast`)+ 弓手**武技**,給四中庸各一個**功能性角色**(能做的事),非數值堆疊。三個小型可複用引擎啟用器:
- **A · 盟友指向(治療師援護 + 騎士號令)**:`spells.json` 新 `target` 值 `ally`/`allies`;`magic.cast` 在 kind 分派前加閘 —— 對同伴施 heal/shield/apply_status/**新 empower**(`_apply_to_allies`),**僅戰鬥**(無 battle / 無存活同伴皆退費並失敗)。**🔗 同伴系統綜效**:戰中治癒同伴 → `battle.allies` Creature `.health` 提高 → 戰後 `party.record_after_battle` 回寫 → **持久**(負傷同伴可被奶回)。**號令 empower**:新狀態 `{kind:empower,magnitude,turns}`,`combat.resolve_attack` 對**帶 empower 的非玩家攻擊者**(同伴)`raw *= (1+emp)` —— `not _is_player` 守門 → **永不碰玩家偷襲紅線**。`main._choose_ally_target` 選同伴穿進 cast。法術:援護術(ally heal)/治療之環(allies heal)/庇護術(ally shield)/生機共鳴(allies regen)/號令(allies empower 0.25)。
- **B · 武器灌注(戰法師奧術灌注)**:新 effect kind `weapon_imbue`(self)→ `char.active_effects` 計時自動退場;`combat.resolve_attack` 玩家近戰(`not beast`)物理分支加總 active imbue 元素傷害,**比照既有附魔、在 solo 偷襲夾限之前** → sneak-solo 自動受夾、不放大,紅線安全。法術:焰/霜/雷刃術(alteration,+8/擊×5 回合)。
- **C · 散兵戰技(弓手,非法術)**:裝弓(`archetype=="bow"` 且非獸形)時 `_choose_combat_action` 加 瞄準射/牽制射/散兵走位 + `run_battle` 分派 —— **瞄準射**(命中↑破甲↑、補傷走 power_bonus 不吃偷襲倍率、額外耗體一次、仍受 solo 夾)/**牽制射**(命中後上 weaken)/**散兵走位**(射後複用 vanish 三道煞車〔體力/次數/上限〕、共用 `vanishes_done` 計數,防無限風箏)。常數在 `formulas.AIMED_*/CRIPPLING_*`。
- **配發/可及**:`creation._starting_spells(majors, class_id)` 給 battlemage/healer/knight 起手簽名法術(焰刃/援護/號令);8 法術上架 imperial_city + haafingar 法師公會(六系仍可及)。`ui.spell_effect_summary` 補 weapon_imbue/empower + 盟友指向摘要。**零新存檔欄**(法術走既有 `char.spells`、buff 走 active_effects)。
- **對抗審查(4 維 × 每發現獨立懷疑者;6 發現→5 確認 / 1 駁回 + 1 既定設計)**:**5 確認全修**:① 援護/AoE 失敗退費只退魔不退體(不對稱資源損失)→ 快照 `fatigue_before`、五條退費路徑連體力一併還原;② empower 未吃施法 power(與 heal/shield 不對稱)→ 比照乘 power(分數型**不取整**,否則 0.25 被 round 成 0);③ **8 新法術誤上架到海芬古而非帝都樞紐**(原意 imperial_city)→ 補上帝都(中央可學,heartland 起手可及);④ empower 可疊乘暴衝(3×rally=1.75×,scaling 後更甚)→ combat 改 **max 聚合**(取最強一道,不加總);⑤(④的回歸防線)。**1 駁回**(正向確認):同伴無法戰中復活刷(倒下即移出 `battle.allies`、heal 閘 `health>0`)。**1 既定設計**:弓手武技無體力預檢 —— 與 attack/block/vanish 通用慣例一致(永遠可出手、體力夾 0),非 bug。
- **驗證**:**48 測試模組全綠**(新 `test_hybrids` 13 測:imbue 加元素+sneak-solo 受夾/援護治癒同伴+戰後持久/失敗**退魔也退體**/群療+生機共鳴/號令增傷同伴**不碰玩家**/**empower 隨施法 power 成長**/**max 聚合不疊乘**/**8 法術中央可學不孤兒**/aimed 較強仍受夾/摘要全涵蓋/簽名法術)+ `sim_assassin` **零位移**(solo boss 全 0%,這些都不在玩家偷襲路徑)+ 無頭整合煙霧(治療師奶同伴 8→70+失敗退費/號令隨技能 0.192<0.425/戰法師 imbue 近戰帶火/帝都上架渲染)。**鐵律**:imbue/aimed 補傷務必落在 solo 夾限**之前**(改務必重跑 sim);empower **只對同伴**、combat 端 `not _is_player` + max 聚合雙保險;新增中庸支援法術純改 `spells.json` + 上架 `world.json` spell_stock(**務必含中央 imperial_city**,否則孤兒、僅遠省可學)。

**戰友團 The Companions(第 7 公會 + 狼人血脈歸宿;使用者拍板「戰友團」方向;plan-mode 核定 → 直作 → 對抗審查)**:把狼人化的「獸血儀式」正本清源 —— 原掛在**戰士公會 rank≥2**(且戰士公會遍佈 12 城 → 到處發狼血,名實不符)。正史中天際的**戰友團**才是狼人(其圈內 Circle 秘密),白漫城 Jorrvaskr 是其聖殿,且白漫的 `fighters_guild` 服務早被風味成「戰友團」。本輪升格為**真正可入會的第七公會**,並把儀式移到戰友團內圈。**幾乎純資料 + 小面 main.py wiring;零新系統模組、零新存檔欄**(會籍存既有 `char.factions`)。
- **A·白漫=戰友團 + 儀式內圈**:`world.json` 白漫 `services` 的 `fighters_guild` → **`companions`**(戰士公會仍在凱瓦奇/帝都/**風盔城**等 11 城,Skyrim 玩家在風盔城仍可入)。`lycanthropy.RITUAL_RANK_INDEX` 2→**4**、`can_offer_ritual` 改讀 `companions`(原 `fighters_guild`);`main.action_guild_hall` 儀式 gate 隨之改 `faction_id=="companions"`。**向後相容鐵律**:儀式移位=內容重置非存檔破壞 —— 舊存檔照常載入(`companions` key 不存在=非會員,到白漫入會晉內圈即可),**已是狼人者不受影響**(無需儀式),**無需 `ensure_*` 遷移鉤**。
- **B·完整獸血弧**(`quests.json` companions1–6,鏡像 `knights_nine`:7 階/6 任務/`advance_block_reason` 單一真實來源/自動進 legacy):初試獵狼→清迷刀洞窟→獵熊榮譽狩獵→**內圈引渡**(多階:殺 3 銀手→`reach whiterun` 受血,完成晉 rank4 內圈戰友→儀式+召集解鎖)→搗毀冰風廢墟銀手殘黨→**companions6 終局二選一**(嗣血·希爾辛狩獵=殺 `werewolf_alpha` / 淨血·格倫魔女=殺 `glenmoril_witch`)。**關鍵設計**:戰士公會走**一般公會流**(`action_guild_hall`,非暗殺 `_contract_hall`)→ kill 目標靠**被動 `kill_counts`** 追蹤 → 故 `silver_hand`(d3)/`glenmoril_witch`(d4)須**野生可遇**(`weight>0`、`biomes:["snow"]`、`min_level` 4/6 gated),**非**合約式 `weight:0` 具名靶(那只在 `_contract_hall` 直生才成立)。两敵掉落 `glenmoril_witch`→蒜/龍葵(呼應解咒媒介)。
- **C·功能性 perk(非數值,呼應同伴深化)**:`factions.json` 新 perk kind **`merc_discount`**(盾袍之誼,per_rank 0.08/cap 0.5)→ `factions.merc_discount` 接 `main._hire_mercenary` 折抵招募費;`companions.json` 加 **`farkas`/`aela`(`circle:true`、cost 0)** 盾袍兄弟 → 內圈戰友(rank≥`COMPANIONS_CIRCLE_RANK=4`)可在聖殿**免費召集**(`_available_shield_siblings`/`_rally_shield_sibling`,受 `MAX_PARTY` 限)。circle 旗標**排除於旅店傭兵池**(`_hire_mercenary` 過濾)**與營地將領池**(`warband.recruitable_officers` 僅 `warlord`,天然排除)。**allies-only → `sim_assassin` 零位移、不碰玩家偷襲/solo-boss 紅線**;持久 HP/羈絆自動走 `party.py`。
- **D·開局正名**:`origins.json` 的 `beast_blooded`(獸血源出戰友團)`fighters_guild:1`→`companions:1`、`fighters_recruit`(名即「戰友團的新血」)`fighters_guild:0`→`companions:0`(皆保留 whiterun);更新 `test_lycanthropy`/`test_origins` 斷言。
- **驗證**:**49 測試模組全綠**(新 `test_companions` 21 測:無解鎖事件技能即入會/低技能擋/lawful:false 通緝可入會兼晉升/rivals 空可兼戰士公會/階梯晉升/技能門檻/內圈引渡多階 kill→reach/終局雙分支/目標+地城合法/**銀手·格倫魔女野生可遇**/儀式移籍 戰士公會不再給·內圈才給·吸血鬼/狼人互斥/`merc_discount` 隨階/盾袍兄弟 circle-only·助手列舉去重·排除旅店池/存檔往返/legacy 收錄)+ `sim_assassin` **零位移**(solo boss 全 0%)+ 無頭煙霧(白漫入會→內圈儀式狼化→召集 farkas→招募折扣 120=200−40%→風盔城仍可入戰士公會→嗣血終局晉先驅)+ 遭遇抽樣(銀手/格倫魔女天際雪原主導、不洩漏和緩起手大道、跨 biome 漏出率 ≤ 既有屍鬼)+ **對抗審查 workflow(5 維 fan-out × 每發現獨立懷疑者驗證,16 agent;11 發現 → 1 確認〔minor,已修〕)**:免費 circle 盾袍兄弟「解散→再召集」原可零成本回滿血/解負傷(`_dismiss_mercenary` 對 cost:0 circle 走 `party.forget` 清持久 HP,再召集無 HP 紀錄=滿血)→ **修為:circle 盾袍兄弟解散時保留持久 HP/羈絆**(雇傭兵照舊 forget,siege 折損 forget 不變),補 2 回歸測試(circle 負傷解散→召集仍負傷 / 雇傭兵仍 forget)。10 駁回皆既定設計/nit(舊存檔照載、儀式移位=刻意摩擦非死路、allies-only 不破紅線)。**鐵律**:戰友團走一般公會流;circle 盾袍兄弟解散**不可 forget**(否則免費回血漏洞);新 kill 目標須 `weight>0` 野生可遇(被動 kill_counts);獸血儀式由 `lycanthropy.RITUAL_RANK_INDEX`(內圈門檻)+ `companions` 會籍 gate;circle 盾袍兄弟 allies-only、排除旅店/營地兩池;**加公會內容多半純改 factions/quests/companions/bestiary JSON**。

**八職功能性身份網格(全 8 職業各一招牌戰術 loop;使用者:評估所有職業→拍板全八職全做;9-agent 審計→2-cluster Plan→直作→20-agent 對抗審查修 7)**:承「四中庸職業功能性區分」。先跑**8 職功能性審計**(9-agent workflow),結論:**身份來自獨特戰術 loop/系統而非技能列**(故 assassin 五支柱最深、warrior/mage/thief「純技能列」與只有 imbue 的 battlemage 最薄)。給每個**玩法軸**一招牌功能性(非數值)機制。**機制以技能/裝備 gate(非硬鎖 class_id)、暫態全存 `active_effects`(不序列化、戰鬥邊界清)、零新存檔欄、永久選擇走 `mastery_choices`、門檻只認 `base_skill`**。
- **6 新 mastery 二選一節點 + getter**(`mastery.py` 白名單 + `mastery.json`):**mage `mysticism_75`「奧術連鎖 cascade」**(連發 +power/−fatigue 遞增、cap depth 2、停手即散;`magic._power` + `spell_fatigue_cost`〔**折扣乘在法袍 cast_fatigue_factor 之後、獨立**〕+ `cast` 尾 `bump_cascade`)/ **battlemage 雙 gish loop**(初版 `destruction_75` 二選一;後續修已互換至 50/75 兩節點可兼得,見下方「後續修」):「共鳴一擊 resonant_strike」(施毀滅傷害術→下一近戰灌半數法傷+元素 DoT,**插 weapon_imbue 同位置、solo 夾限前、單次**)+「法力回擊 mana_on_hit」(近戰命中回魔,純資源)/ **thief `mercantile_75`「諜報偵搜」**(複用既有 `prep_bonus`/`recon_resist_read`;**唯一 code:`mastery.prep_bonus` 改多來源相加**,否則 scout+thief 第二來源被靜默丟棄)/ **archer `marksman_50`「獵手偵察 recon_reveal_floor」**(無 scout 也視同偵查 50,`_scout_report` 取 max)/ **healer `restoration_50`「戰地搶救 triage_heal」**(同伴<30%→武裝→下道治療成本×0.15/體力×0.25,`magic.cast` 覆寫成本非注入行動)/ **assassin `sneak_50`「致命烙印 deathmark」**(標記敵→**後續(非開場)近戰** +0.35 破甲,`combat.py` pen 加 `not sneaking` 守門→開場偷襲永不受惠)。
- **2 戰鬥動作**(`main.py _choose_combat_action` + run_battle 派發 + 回合末維護):**warrior「盾牆」**(持盾+`base_skill block≥50`+體力>upkeep→切換架勢:物理減傷 30%〔僅物理〕+ **嘲諷**〔`pick_player_side_target` 鎖坦〕+ 護同袍護甲光環 + 每回合耗 6 體力,**體力耗盡不可再立**)/ **knight「戰旗」**(`base_skill illusion≥50`→立旗:每回合刷新全隊 `empower`〔複用既有 allies-only 路徑,**永不增玩家傷**〕+ 自身護甲;耗 15 魔 10 體)。
- **不做戰法師套裝**(使用者點出「戰法師可穿重甲施法無懲罰」→ 實查確認本作**無任何 armor→施法懲罰**〔`cast_fatigue_factor` 預設 1.0、僅法袍給減免〕→ 輕甲 battlemage 套裝被重甲完全宰制=陷阱裝)→ 改走裝備無關的 resonant/mana_on_hit 雙 gish loop(穿重甲撐近戰、揮劍補魔續法)。
- **🔴 紅線**:`sim_assassin.py` **逐行 byte-identical**(8 機制皆不在偷襲路徑:wall/standard/triage/tracker/thief=防禦/資訊/盟友;cascade/resonant=施法且 resonant 在夾限內;mana_on_hit 純資源;deathmark `not sneaking` 守門)。sim 以**手選節點**故新節點對它隱形。
- **對抗審查 workflow(6 維 fan-out × 每發現獨立懷疑者,20 agent;14 發現→7 確認,全修)**:① MAJOR 盾牆 fatigue-0 免費永久重立坦(無 fatigue gate)→ 改體力≤upkeep 不可立;② MAJOR 護同袍光環死功能(`_armor_rating` 非玩家分支不吃 `active_shield`)→ 補上(連帶修好既有盟友護盾術同 bug);③ minor triage 旗標在失敗退費前就消耗→延到治療確施才消耗;④ minor deathmark cooldown(3)<標記(4)形同虛設→改 6;⑤ minor 備戰施法預堆 cascade→prep 後清連鎖層;⑥ minor 常駐光環每回合誤報「護盾消散」→ source 標記消音;⑦ nit mana_on_hit 誤報「法杖」敘事→改靜默回魔。補 4 回歸測試。7 駁回皆既定設計/nit。
- **驗證**:**50 測試模組全綠**(新 `test_class_identity` 20 測:cascade getter 縮放/cap/法袍複合·bump、resonant 加元素+DoT+單次+**solo 夾限**、mana_on_hit 回魔、subterfuge **prep 多來源=2**、tracker floor、盾牆嘲諷/減傷物理only/**體力耗盡不可立**/**護同袍光環真減傷**、戰旗 empower 僅同伴**不碰玩家**、triage 折扣+消耗+**失敗保留旗標**、deathmark **開場免疫(solo 夾)**/follow-up 破甲/**cd>mark**、存檔往返)+ `sim_assassin` **byte-identical** + 無頭 run_battle 煙霧(6 戰鬥動作全 victory 無 traceback)。**鐵律**:新職業機制改 `mastery.json`+一 getter+一 combat/magic call-site;玩家近戰補傷務必落 solo 夾限**之前**(resonant);deathmark `not sneaking` 守門;戰鬥動作 gate 用 `base_skill`;改紅線機制(resonant/deathmark)務必重跑 sim。
- **後續修(使用者拍板):毀滅 50/75 互換 —— 省魔催動⇄共鳴一擊對調,戰法師雙 loop 可兼得**:原 `destruction_75` 二選一令爆發流/自持流互斥 → gish 協同不能成環。互換後 **50=共鳴一擊⇄凝神聚法、75=省魔催動⇄法力回擊**(每節點仍一武一法,純法師〔凝神→省魔〕/戰法師〔共鳴→回擊〕身份分叉不變;省魔催動 desc「漸熟→嫻熟」配 75)。**純 JSON 互換零 code**(getter 全以 kind 取用、不綁節點 id);舊存檔靠 `ensure_mastery_choices` 清陳舊選擇 → 該節點退回 pending 重選(同 recon 重設機制,零新欄)。52 測全綠(`test_class_identity` 共鳴一擊改選 50 + 新增「雙取兼得」測試;`test_mastery` 省魔×過載聚合改 75)+ **sim 對 HEAD 基線 byte-identical**(sim 手選節點不含毀滅、常數零變動)+ 無頭煙霧(50/75 彈窗選項對、雙 perk 戰鬥成環、舊檔遷移退 pending)。**對抗審查 workflow(4 維 × 每發現 2 獨立懷疑者,34 agent;15 發現 → 8 確認〔7 為「驗證通過」備案〕+ 5 爭議,裁定修 3**:① handoff Batch 2 歷史段補互換註記;② **舊檔永久喪失路徑**(50=凝神+75=共鳴 → 共鳴被清而 50 已被凝神鎖死,共鳴對該角色永不可得 —— 正打中本次要服務的戰法師)→ 新 `progression.RELOCATED_NODE_GROUPS`:**perk 搬家組任一選擇陳舊 → 整組退 pending** 重選(守選擇權、可重組雙 loop;+回歸測試,全有效組不過度清除);③ **既有 rider 抗性 double-dip 提早曝光**(magic 存「已折算」值、combat 打擊時再 ×mult → 弱點目標最高灌 2 倍「半數法傷」,違 desc 意圖)→ 改存**未折算基底** `damage/mult`,打擊端按打擊目標折算一次,同目標淨值恰半數實際法傷(+弱火 mult 2.0 回歸測試;觸 resonant 紅線機制 → 重跑 sim 仍 byte-identical)。其餘駁回/不動:50-74 舊檔省魔降級窗口=互換固有摩擦(整組退 pending 已給即時 50 新選擇)、「可抵過載」desc 既有小誇大(0.85×1.30=1.105,加 25 入門 0.92 才 1.0166≈中性)。**鐵律**:perk 在節點間搬家時,把新舊節點登進 `RELOCATED_NODE_GROUPS`(只靠陳舊清除會鎖死跨節點搭配);resonance rider 永遠存抗性未折算基底(消耗端會折算)。

**地城改為格子探索區域(程序化 n×n × m 層;使用者:評估地城→拍板程序化生成 / 單場原子探索 / 全 10 改制;另拍板「首領寶箱死亡自動解鎖」;3-agent 探索→2-Plan→直作→對抗審查)**:原 10 地城是「固定 4 房 + boss」線性序列(無格子/分層/分岔/探索抉擇,與 ★★★ 開放探索名實不符)。改為**程序化生成的格子地城**:n×n 格 × m 層、N/S/E/W 移動、樓梯下層、清末層 boss = 肅清。
- **資料模型(`dungeons.json` 10 條改寫為參數化 spec)**:`{name, biome, grid:n, layers:m, danger, monsters:[怪物池], loot:[格內寶箱池], loot_locked:[lo,hi], boss:{enemy, raw?, desc, treasure:{loot}}}`。舊 `rooms` 廢棄。n/m 隨 danger(≤3→4×4×2、≥4→5×5×3);怪物/戰利品池=舊房敵人/寶箱聯集(主題不流失)。
- **生成器(新 `systems/dungeoncrawl.py`)**:`generate(spec, gamedata, rng)→{n,m,layers[z][y][x]=cell,boss}`。cell ∈ entrance/empty/monster/container/trap/stairs/boss;(0,0)=進場/下層到達點;**開放格無內牆 → 全連通 → 樓梯+boss 必可達**(BFS 驗證);密度 怪 0.22/寶 0.15/陷阱 0.08;每非末層 ≥1 樓梯、末層 boss 置遠半邊。helper:neighbors/minimap/reachable_cells/find_cell。
- **探索子迴圈(`main.action_dungeon` 改寫,鏡像 `run_battle` 自足子迴圈)**:標記已探 → 首次進格結算內容(monster→`run_battle`、container→`_resolve_container`〔pick_lock〕、trap→`_resolve_trap`〔敏捷/安全/幸運規避〕、boss→秀 `desc` → `run_battle` 勝 → **寶藏自動解鎖** `dungeon.open_container` + `record_dungeon_clear`)→ 渲染小地圖 + 選單(移動 N/S/E/W、樓梯處下層、離開)。出口:清 boss(record+None)/ 離開·逃跑戰鬥(None,不計清剿)/ 死亡("dead")。**🔴 boss 寶藏死亡自動解鎖(免開鎖器;一般格寶箱仍 pick_lock)。**
- **🟡 反刷寶 first_clear 閘(對抗審查確認的 critical)**:`first_clear = loc["dungeon"] not in cleared_dungeons`。**只有首次肅清才給保證戰利品**(boss 寶藏 + 一般格寶箱);已清地城重訪 → 怪物/陷阱照常(戰鬥 XP/掉落是有風險的正常 grind),但寶箱/寶藏皆「已被搬空」零保證掉落。沿用既有 `cleared_dungeons`(零新存檔欄),堵住「重走→秒 boss→白嫖具名神器」無限刷。
- **UI 雙端(`console.py dungeon_grid` + web `renderDungeonGrid`)**:終端 ASCII 小地圖(@你 ✦首領 ↓樓梯 ◊入口 ·已探 ?未探 · 迷霧)+ web CSS-grid(相鄰格 `data-key=go:DIR` 可點移動,複用 `wireActionableRows`)。
- **🔴 紅線/存檔**:crawl 全程走 `run_battle`(零改)+ boss 仍 `spawn_boss`/raw → `sim_assassin.py` **byte-identical**;**零新存檔欄**(格子/已探/已結算皆子迴圈 local,進場現生、離場即棄;`cleared_dungeons` 不變)。原子探索:重進 = 新格子。
- **驗證**:**50 測試模組全綠**(`test_dungeon` 改寫:多種子生成合法〔連通/樓梯+boss 可達/入口/id〕、衝 boss 勝→肅清+寶藏**免開鎖器自動入袋**、**重訪零保證掉落**、逃 boss/離開/死亡不計清剿、零新存檔欄;`test_m12`/`test_world`/`test_smithing` schema 讀取改怪物/戰利品池;`test_web` 加 dungeon_grid view 形狀)+ `sim_assassin` **byte-identical** + 無頭 crawl 煙霧(10/10 導航至 boss 清空、寶藏免開鎖器入袋、衝 boss 遭遇 2-4 場)+ **對抗審查 workflow(5 維 fan-out × 每發現獨立懷疑者驗證,21 agent;16 發現 → 4 確認,全已修)**:① **critical** boss 寶藏重訪無限刷具名神器(無 first_clear 閘)→ 加 first_clear 閘只首肅給保證戰利品;② **major** 一般格寶箱重訪重生保證掉落(loot 膨脹)→ 同 first_clear 閘堵住;③ **nit** `dungeon_room`/web `renderRoom`/`room` view 改制後死碼 → 刪除、boss `desc` 改接進 boss 戰前秀(不再 vestigial);④ **minor** `test_smithing` 仍掃舊 `dg["rooms"]`(死碼掃空)→ 改掃 `dg["loot"]`。12 駁回皆既定/nit(degenerate n=1 無實際地城用、`reachable_cells` 忽略 z=開放格各層同、紅線+零存檔正向確認、陷阱對衝 boss 路偏弱=設計權衡)。**鐵律**:crawl 走 `run_battle`(紅線零碰);新 cell 型別走 生成器 + crawl 派發 + UI 圖示三點;調平衡改 `dungeoncrawl` 密度常數 / dungeons.json 參數;boss 寶藏死亡自動解鎖、一般格才 pick_lock;**保證戰利品只首肅給(first_clear 閘),重訪零白嫖**。

**法術學派補完:召喚 + 秘術拉到與成熟學派同級(使用者:健檢三路勘查→拍板補完召喚/秘術→拍板完整功能補完;3-agent 探索→Plan→直作→對抗審查)**:八學派中**召喚/秘術是僅有兩個 stub**(各 2 法術、召喚毫無戰術變化、秘術機制脫節),與成熟學派(7-10 法術)名實不符。各補 +5 至 7 法術,且各給**鮮明功能身份**。
- **召喚 → 召喚師**:+3 召喚物(冰/雷元素 + 魔人 capstone,純資料走既有 `summon` dispatch)+ **束縛兵刃**(`bound_weapon`:凝出法系近戰武器、可空手、無視物理護甲、**完全取代裝備武器**)+ **亡者復生**(`reanimate`:把已死非 solo 敵屍喚為限時盟友,復用召喚物生命週期)。
- **秘術 → 元魔法/剋法**:**法術結界**(`ward`:吸收來襲法術/元素傷的可耗盡池 + 吸魔變體回魔)+ **驅散**(`dispel`:淨化自身恐懼/麻痺/侵蝕)+ **群體擒魂**(複用 `status_all` 跑 soul_trap,零新引擎分支)。
- **引擎**:`magic.py` 4 新 cast 分支 + `consume_ward` helper + `cast()` 加 `corpses` 參數(修 sourcing bug:cast site 原只傳存活敵 → 復生看不到屍體);`combat.py` `_weapon_profile` 讀束縛兵刃 + `atk_element` 走元素分支 + 元素防禦路 ward 消耗。`bestiary.json` +3 `summoned_*`。UI `spell_effect_summary` 補 4 新 kind。`world.json` spell_stock 跨省散佈(各新法術 ≥2 城,守 test_polish 全學派/全省/起手省)。新 `test_spell_schema`(schema + 可達性無死內容掃描)。
- **🔴 紅線/存檔**:`sim_assassin.py` **byte-identical**(刺客不施法、新掛鉤皆 gated;束縛兵刃偷襲 solo boss 仍走元素分支受夾限);**零新存檔欄**(束縛兵刃/結界=transient active_effects;`corpse._reanimated` 為 Creature 暫存旗標、永不序列化)。
- **驗證**:**51 測試模組全綠**(`test_magic` +18 功能單測:束縛兵刃空手無視護甲/不雙吃灌注/不疊/偷襲 solo 受夾/不吃裝備毒+附魔+耐久/命中練咒術;結界吸元素傷+消耗/吸魔回魔/不疊無敵;驅散只清自身 debuff;復生起非 solo 屍+拒 solo/空屍/戰外退費對稱+不二次+虛弱化;新召喚吃 summon_mod;群體擒魂標全體 — 新 `test_spell_schema` schema+可達性)+ `sim_assassin` **byte-identical** + 無頭煙霧(買+施每道新法術、戰內外、UI 摘要全渲染)+ **對抗審查 workflow(6 維 fan-out × 每發現獨立懷疑者,22 agent;16 發現 → 1 真缺陷 + 數 nit,全已修)**:**major** 束縛兵刃**只擋到元素分支內的 weapon_imbue/附魔**,卻把裝備武器的**塗毒/命中附魔(吸血/麻痺/再生)/耐久縮放/磨損/副手/法杖回資源**(皆在分支外、僅 `not beast` 把關)漏吃到法系兵刃上 → 修為**比照獸形 `not bound` 全面排除**(束縛兵刃真正完全取代裝備武器)+ 補 2 回歸測試;nit:束縛兵刃命中不練技能→改練咒術;亡者復生滿血復生高 HP 精英→`REANIMATE_HP_FACTOR=0.6` 虛弱化;CLAUDE.md「各≥7」不確→改詞(幻術仍 5)。**鐵律**:加法術純改 `spells.json` + `world.json` spell_stock(守 test_polish);新召喚物純改 `bestiary.json`(`min_level 99`/`weight 0`);新 effect kind 走 cast 分支 +(戰鬥掛鉤)+ UI summary 三點;**新近戰武器型態須比照獸形 `not beast` 在全部裝備武器掛鉤(塗毒/附魔/耐久/副手/wdef)加排除,否則雙吃**。

**地城視為戰鬥情境:一般行動 + 預施/預召喚 + 偵查 + 狀態介面(使用者明列五項 + 拍板「地城視為戰鬥狀態→可預召喚」;3-agent 探索→Plan→直作→對抗審查)**:格子地城原為純導航(不能施法/開包/看卡、無回合經濟與盟友情境)。本輪把地城升為**輕量戰鬥情境**:
- **一般行動**:選單加施法/背包/角色卡(複用 `action_cast_self`/`action_inventory`/`action_character_sheet`)。
- **預施/預召喚**(行動 1 格 = 1 回合):地城持 `battle={"allies":[]}`;`action_cast_self` 加 `battle` 參數 → 放寬為「self-target 非 reanimate」(含**召喚**+各增益),召喚物入 allies。每次移動 tick 玩家增益 + 召喚物 summon_turns/效果(走太遠消散;DoT 可致死→"dead");施法/背包/角色卡為自由行動不耗回合。`run_battle` 加 `carry_allies`(預召喚物 extend 進戰列,不入 roster→不污染持久同伴)+ `preserve_buffs`(跳過進場清效果、只剝 cascade/過期);戰後 `sync_allies` 重濾存活召喚物。**平衡**:魔力+每格衰減+溢盾 cap 三重夾限,有界。
- **偵查揭示**:`mastery.has_recon_perk`(scout 洞察弱點 / marksman 獵手偵察)→ 移動探明四鄰;**每探明一新格** `progression.use_skill("scout", DUNGEON_REVEAL_SCOUT_XP=0.12)`(已探不重複→不可踱步刷)。`dungeon_grid` 加內容圖示(怪!/寶$/陷阱^)+ `resolved` 參數(已結算回 ·)→ 揭示有資訊量。
- **狀態介面**:`status_line(state, gamedata, allies)` + web `_hud_view`/`renderHud` 一併顯示**夥伴(party 持久 HP/負傷)+ 召喚物(HP/回合)**;地城內每輪渲染 HUD。**修施法後敵狀態丟失**(web `renderScreen` 每幀清空重繪):選法術子選單前重發 `combat_status_group`(敵/同伴目標子選單原已重發)→ 整個施法流程都見戰場。
- **🔴 紅線/存檔**:`sim_assassin.py` **byte-identical**(sim 走 `resolve_attack` 非 `run_battle`;`carry_allies`/`preserve_buffs` 預設 None/False;零戰鬥常數改);**零新存檔欄**(crawl battle/allies/summon Creature 皆 transient)。
- **驗證**:**51 測試模組全綠**(`test_dungeon` +一般行動可達/carry_allies+preserve_buffs 帶入/每格 tick 衰減增益/DoT 致死/探明練偵查/預召喚入 allies/召喚物不污染持久同伴;`test_mastery` has_recon_perk;`test_web` 內容圖示+resolved+HUD 夥伴/召喚物,並補登錄漏跑的 `test_dungeon_grid_view_block`)+ `sim_assassin` **byte-identical** + 無頭煙霧(終端狀態條夥伴/召喚物 + dungeon_grid resolved 渲染)+ **對抗審查 workflow(6 維×每發現獨立懷疑者,27 agent;21 發現 → 8 確認全 nit,7 已修)**:① 施法後敵狀態刷新原以「玩家行動後補繪」實作 → 使用者實測 web 出現**重複戰場卡**(每幀清空重繪 → 補繪卡與下一輪卡並存)→ 改為**選法術子選單前重發**(治本、零重複)② cast 選項僅當有可施 self 法術 ③ `_allies_status` 補 summon_turns 守門 ④ 召喚物 DoT/再生 tick 訊息改顯(與玩家對稱)⑤ 出地城重設 HUD(免里程碑彈窗殘留召喚物)⑥ CLAUDE.md 測試數 44→51。保留:dispel 留在地城清單(可清帶入的 DoT)、skooma 服用推時=既定自由行動。**鐵律**:crawl 走 `run_battle`(紅線零碰);新移動行動須 tick(增益/召喚衰減 + DoT 死檢);`carry_allies` 不入 roster(否則污染持久同伴);狀態條/HUD 雙端讀同一 `_party_status`/`_allies_status`。

**技能里程碑廣度 pass(17 薄技能各 +1 功能節點;使用者:技能里程碑廣度→拍板「功能加碼」;2-探索→Plan→直作→對抗審查修系統性遮蔽)**:里程碑分布不均(6 厚技能 2-3 節點、17 薄技能僅 1)。給每薄技能補第二節點(不同門檻層),全 23 技能達 **≥2 節點(47 節點,sneak 仍 3)**。功能加碼:每新節點 ≥1 功能槓桿。
- **13 節點純 JSON 複用功能 kind**(武器控場 weapon_mod / 法術控場 spell_mod / 被動護甲 passive_armor / 偵查揭示 recon_reveal_floor / 議價 merchant_bonus / 修理保底 repair_floor / 閃避 evasion / 塗毒 poison_charge);**attr_fortify 首度啟用**(athletics 耐力 / alchemy 智力 / alteration 意志)。
- **4 新功能 kind**(`mastery.py` getter + 白名單 + 一處呼叫端):`combat_repair`(armorer:戰中/地城每回合自修武甲耐久,`_apply_combat_repair`)、`flee_bonus`(athletics:`try_flee` 加 gamedata 參)、`armor_reflect`(heavy_armor:`resolve_attack` 物理分支反 12% 給攻擊者)、`trap_floor`(security:`_resolve_trap` dodge 保底)。
- **2 getter 微修**:`weapon_mod` 同 target 合併(blade_50+blade_100 不遮蔽);`repair_floor` 取 MAX。
- **🔴 紅線**:無新節點碰 sneak_mult/vanish/approach/匕首 power;`sim_assassin.py` 契約**全守**(solo boss 秒殺 0%、>3 反制、4 敵死亡率 27%/12%;非 byte-identical 但紅線不破)。**零新存檔欄**(走 mastery_choices + fortify 加成層 + 即時讀取)。
- **驗證**:**51 測試模組全綠**(`test_mastery` +12:全 23 技能 ≥2 節點 / 新節點 gating+二選一永久 / 4 新 kind 效果 / weapon_mod 合併 / repair_floor MAX / attr_fortify 流入資源 / **同源遮蔽修正**)+ `sim_assassin` 契約守 + 無頭煙霧(跨門檻→choice→選後存讀檔往返)+ **對抗審查 workflow(6 維×每發現獨立懷疑者,29 agent;23 發現 → 19 確認,皆修)**:**系統性同源遮蔽** —— 廣度 pass 使多 getter 出現「同技能/同學派多節點」,但 `spell_mod`(alteration_50+75 efficient_shield 省魔被遮)、`passive_armor`(2→5 來源)、`poison_charge`(alchemy_50+75)、`evasion`(acro_50+75)仍 first-wins → 玩家永久選的 perk 零效果。**修為全部聚合**(spell power 相加·cost 相乘·on_hit 取後;passive/poison/evasion 相加;recon_floor 取 MAX);另:**illusion_100 paralyzing_gaze 死碼**(spell on_hit 僅傷害法術觸發,幻術無傷害法術)→ 改 `mind_mastery`(走 live spell_cost_factor 省魔);**passive_armor 魔力閘**對物理 stance 不合理 → 改無條件;**armor_reflect 反殺被擒魂敵漏靈魂石** → 敵階段後補 note_trap。**鐵律**:多源 kind 的 getter 必聚合(相加/相乘/取最/取後,鏡像 vanish_floor/merchant_bonus);加既有 kind 節點純改 JSON;新 kind 走 白名單+getter+呼叫端三點;觸武器/反傷/閃避/毒務必 re-sim。

**同伴角色化:具名同伴 + 招募任務 + 專屬支線 + 對話 + 忠誠弧(使用者:下一步→同伴角色化→拍板「陣容兩者都做 + 頂點戰術/被動混合多樣化」;3-探索→plan-mode 核定→直作→對抗審查修 3)**:同伴原是「數值棒」(僅持久 HP/羈絆,除 farkas/aela 一行 blurb 外無人格)。本輪把同伴做成有故事的「人」。**核心架構:複用既有 `companion_bond`(0–60,四階)當忠誠軸,不另立第二數字;零新 Character 存檔欄**(解鎖/弧完成/頂點全由 `completed_quests`/`companion_bond`/`companions` 推導)。
- **引擎(小面集中)**:`quests._complete` 加資料驅動 **`reward.companion`**(招募末段授予具名同伴:有位入夥、滿員則經 `recruit_quest∈completed_quests` 解鎖待召集)+ **`reward.bond`**(專屬支線完成→羈絆躍升,夾 BOND_MAX)。`party.py` 加 `arc_done/arc_offerable/active_capstone/passive_capstone_factor/recruited_named/keeps_state_on_dismiss/loyalty_*`、`MAX_PARTY` 移此為單一真實來源。`main.action_party` 加「**與同伴交談**」(依羈絆階對話 + 達門檻提供專屬支線,走既有 `_accept_and_brief`,source `companion`)+「**召集同伴**」(具名同伴待命 roster,免費受 MAX_PARTY)。`legacy.py` 加忠誠弧計分 + 結算「忠誠」行。
- **忠誠弧頂點(完成專屬支線解鎖,戰術/被動混合多樣化)**:**戰術型=盟友限定光環**(`ally_empower/ally_shield/ally_regen`,在 `run_battle` 構戰列後 + 回合末刷新,**複用戰旗/盾牆同路徑**:empower 有 `combat` 端 `not _is_player` 守門、shield/regen 只套盟友 Creature → **永不碰玩家偷襲/solo boss**)。**被動型=非戰鬥槓桿**(`barter` 接 `world._disposition_factor`、`travel` 接 `world.travel`,夾 `PASSIVE_CAP`,在隊才生效)。7 戰術 / 2 被動。
- **內容(純資料)**:`companions.json` 6 既有同伴角色化(泛用傭兵具名為斯特倫/葛蕾塔/薇拉妮/基蘭 + farkas/aela 深化;各加 4 階對話 + 專屬支線 + 頂點)+ **3 新具名同伴**(德雷拉斯〔晨風丹莫秘法者〕/賈拉卡爾〔艾虎人浪客〕/拉希德〔漢紅衛劍歌者〕,各掛家鄉 NPC + 招募任務)。`npcs.json` +3 家鄉 NPC;`quests.json` +3 招募(source npc,守在地獎勵範圍)+9 專屬支線(source companion,從不洩漏到告示板/公會)。
- **🔴 紅線/存檔**:`sim_assassin.py` 契約守(solo boss 0%、>3 反制不變;頂點皆 allies-only/非戰鬥);**零新存檔欄**(舊存檔照載,狀態推導 + `.get` 防毀損);具名同伴解散保留持久 HP/羈絆(circle 鐵律延伸,堵免費回血洞);無背叛轉敵。
- **驗證**:**52 測試模組全綠**(新 `test_companion_arcs` 19 測:招募授予/滿員待召集/具名解散保留·傭兵 forget/支線羈絆門檻+來源隔離/弧完成躍升+頂點解鎖+夾 BOND_MAX/戰術頂點盟友限定+去重+倒下不發/被動在隊才生效+夾 cap/頂點 kind 白名單/legacy 忠誠/存讀檔零新欄)+ `sim_assassin` 契約守(0%/反制不變)+ 無頭煙霧(招募→升羈絆→交談揭背景→達階接支線→完成→真實 run_battle 盟友光環無 traceback→終端+web UI 渲染→傳奇忠誠行)+ **對抗審查 workflow(5 維×每發現獨立懷疑者,8 agent;3 確認皆修)**:① **major** 泛用傭兵「接支線→解散(forget 清羈絆)→隊外完成→寫回 orphan 羈絆→再雇=免費 tier-2+加成 HP」→ `reward.bond` 改限「在隊或具名(解散保留)」同伴 + 回歸測試;② **minor** ally_shield 頂點每回合刷新,`magic.tick_effects` 誤報「護盾消散了」訊息洪流(白名單漏 `capstone:*`)→ 比照 shield_wall_aura 加白名單;③ **minor** `reward.companion`/`reward.bond` 完成時靜默無回饋(里程碑招牌獎勵看不見)→ `_report_quests` 補「加入隊伍 / 羈絆躍升」報告。**鐵律**:頂點戰術光環走盟友限定(empower `not _is_player` + 只套 ally Creature);新增同伴弧純改 `companions/npcs/quests` JSON(招募 source npc 守獎勵範圍、支線 source companion 天然隔離);具名同伴(circle/recruit_quest)解散不可 forget;`reward.bond` 只給在隊/具名同伴(堵 forget→rehire orphan 洞)。

**隱遁里程碑化 + 1 敵反風箏(使用者:評估隱遁條件→拍板「補 1 敵盲區」+「把隱遁做成潛行 25 里程碑」兩者都做;評估 sim→直作→對抗審查修 1)**:先做**隱遁條件評估**(量化:群體規模反制紅線穩固,唯一盲區是 1 敵 solo boss 被風箏抹平風險 —— apex 極致風箏對多數 boss 勝率 89~99%),使用者據此拍板兩項。
- **隱遁做成潛行 25 里程碑**:新增 `sneak_25` 節點(**系統首個 <50 門檻**),單一 perk「隱遁之術」(kind `vanish_unlock`)**自動授予**(退化節點,不打擾玩家);`combat.can_vanish(player, gamedata)` 改 gate 於 `mastery.has_vanish`(**門檻認 base_skill** → 順帶修掉舊 `skill()` 致 +sneak 附魔可跨門檻的名實不符)。`has_vanish` 走**門檻已達**(非「已選」)→ 零遷移、達標即用;安全點 `_drain_mastery_choices` 退化授予補進 `mastery_choices` 供結算/面板計入 + 播報。`VANISH_MIN_SNEAK` 20→25(無 gamedata 時 fallback)。
- **1 敵反風箏**:`formulas.restealth_chance` 的連環踏影免重複遞減**僅於敵群(>1)生效**;對單一強敵(1 對 1)仍逐次遞減(0.90→0.82→0.58→0.33)→ 敵死咬盯防,apex 不再無限風箏 solo boss。**多敵(n>1)行為與 crowd/horde 反制 byte-identical 不變**。
- **平衡(sim 背書)**:solo boss 極致風箏勝率 89~99% → **76%/75%/85%/43%**(dremora/wamasu/frost_giant/ancient_dragon 恢復真實風險;vampire_lord 仍 96.8% = 最軟 boss 的合理 apex 表現);solo boss 單擊秒殺仍 **0%**、>3 群戰反制不變(紅線雙守)。
- **驗證**:**52 測試模組全綠**(`test_assassin` +隱遁=潛行25里程碑〔base_skill 門檻/附魔不可跨〕+連環踏影對單體仍遞減·敵群免遞減·>3 反制不變+單一 perk 自動授予旗標;`test_mastery` 廣度 `sneak==4`)+ `sim_assassin` 紅線雙守 + solo 風箏 sim + 無頭煙霧(達 25 自動授予「隱遁之術」確立+列入 unlocked+can_vanish)+ **對抗審查 workflow(4 維×每發現獨立懷疑者,8 agent;1 確認皆修)**:**minor** 隱遁之術是系統唯一單一 perk 節點 → 跨門檻播報沿用「可擇一里程碑/二選一」措辭、實則自動授予不彈選單(誤導)→ 事件加 `single` 旗標、`show_events` 改「習得里程碑」措辭、`sheet_masteries` 標「(自動授予)」(3 駁回皆既定設計/非缺陷)。**鐵律**:隱遁門檻走 `mastery.has_vanish`(base_skill);連環踏影只在敵群免遞減(改此務必重跑 solo 風箏 sim + 群戰反制);新增單一 perk 退化節點務必確認播報措辭為「習得」非「二選一」。

**補齊技能里程碑階梯:全 23 技能 25/50/75/100(使用者:盤點里程碑→拍板「補齊節點 · 25 直接賦予 · 其他二選一」;依層分批×3,每批 sim+對抗審查)**:盤點發現結構不對稱(48 節點中只 sneak 有完整階梯、14 技能封頂 75 無頂點、4 技能跳 75、4 魔法學派從 75 起步、22 技能無 25)。把**每技能補成完整 25/50/75/100**(48→**92 節點**),25=單一 perk 自動授予(複用 sneak_25 退化模式)、50/75/100=二選一。**功能為主、複用既有聚合 kind(零 getter 新增,唯 2 個改 max 聚合)**;依層分批:
- **Batch 1(14 個 100 頂點)**:原封頂 75 的技能補 capstone(功能 ⇄ fortify)。對抗審查修 ① armorer_100 repair_floor=100 在 armorer≥100=base cap 已 100 的**死 perk**→改 passive_armor;② 自驗**閃避三源堆疊 0.24 trivialize 群戰**(4 敵死 0.6%)→加 `EVASION_BONUS_CAP=0.15`(4 敵死回 10%);passive_armor 堆疊經減傷公式未 trivialize(免夾)。`temper_cost_free`/`lock_floor` 改 max 聚合防同源遮蔽。legacy per-mastery 40→20(節點近翻倍)。
- **Batch 2(8 個 50/75 補洞)**:blade/blunt/marksman/speechcraft 補 75(weapon_mod 中階/議價);四高階學派 conjuration/destruction/illusion/mysticism 補 50(省魔 spell_mod cost 0.85;**destruction 的省魔後與共鳴一擊互換至 75**,見「八職功能性身份網格」後續修)。對抗審查 0 findings。
- **Batch 3(22 個 25 自動授予)**:sneak 外各技能補 25 入門 perk(weapon/passive_armor/evasion/poison/六學派省魔/議價/偵查/撬鎖/野修…)。對抗審查修 armorer_25 repair_floor=65 同 trap(≥armorer 30 被 base cap 追平)→改 floor 75;scout_25 經 has_recon_perk 解鎖地城探明=功能性(駁回)。
- **🔴 紅線/存檔**:**sneak 已完整→零新 sneak 節點**,刺客 apex 路徑零碰;weapon_mod 餵 sneak 受 solo clamp(絕對)、省魔只動魔耗、閃避夾 0.15;`sim_assassin` 契約全程守(solo 0%、>3 反制不變)。**零新存檔欄**(`mastery_choices` 唯一種子,`ensure_mastery_choices` 自動涵蓋新節點);**25 單一節點排序在前→高階舊存檔載入一次性 burst 自動授予 22 個 25、不崩、不阻斷二選一**(煙霧證)。
- **驗證**:**52 測試模組全綠**(`test_mastery` 廣度改 `all==4`+92 節點+門檻 {25,50,75,100};Batch1/2/3 各補節點存在/無死 perk/同源聚合不遮蔽/25 全單一自動授予/閃避夾限;run() 顯式登錄新測)+ `sim_assassin` 契約守 + burst 自動授予煙霧 + **三批各對抗審查 workflow**(累計 2 確認 minor〔armorer 死 perk ×2 tier〕+ 1 自驗閃避夾限,皆修)。**鐵律**:加既有 kind 節點純改 `mastery.json`;同源多節點 getter 必聚合;repair_floor 類「下限」perk 的 floor 須高於該門檻的 base cap 否則死 perk;25 用單一 option 走自動授予;觸 weapon/sneak/魔法傷害/閃避/毒務必 re-sim。
- **後續修(使用者點出):偵查 recon 里程碑死 perk → 重設**:`recon_reveal_floor`/`recon_resist_read`(「視同偵查 X」「弱點 75→50」)掛在 **scout 技能自己身上是死 perk** —— 要解鎖某 scout 門檻 base scout 本就 ≥ 該門檻,floor 永遠追不上你真正的偵查值。重設 scout 50/75/100 三個死 option 為「情報→戰力」(料敵機先 approach+10% / 臨陣預判 evasion+4% / 先聲奪人 approach+12%);scout_25 保留(真功能=`has_recon_perk` 解鎖地城探明四鄰)、正名「斥候之眼」;`approach_bonus` 改 sum 聚合(sneak+scout 相加,公式自帶夾限+>3 壓制)。**跨技能 recon 借用(marksman 獵手偵察 / mercantile 線人耳目)保留不動 —— 那才是這套 kind 該用的地方**。sim 中性(scout+sneak approach 0.32 群戰死亡率與 baseline 一致、solo 0%、>3 潛近仍陡降)。**新鐵律**:**recon/floor 類「下限/視同」kind 掛在它自己的源技能上會冗餘 —— 要嘛掛別的技能借用、要嘛 floor 須高過該門檻的 base 值**(與 repair_floor 死 perk 同源教訓)。commit `760ad58`。

**外緣省份充實(承「下一步」;6-維評估 workflow → 使用者拍板「純加法」範圍 → 4-省並行授權 workflow → 對抗審查修 8;純資料·零邏輯·零 sim·零存檔風險)**:評估盤點外緣四省(漢默法爾/高岩/瓦倫森林/艾爾斯維爾)**廣度最薄**——各僅 5 地點(核心三省 8-9)、7-8 NPC(核心 16-17),像「複製貼上模板」。本輪純改 5 既有 JSON 補厚:**各省 +1 文化考據新鎮 → 各省 6 地點**(塔瓦綠洲〔劍歌庭·先鋒派〕/坎洛恩〔狼徽公國〕/藤暮樹城〔狂獵獵族〕/白堊糖鎮〔佩萊泰恩糖閥〕,各帶城主+bloc+商店+同省雙向連環)+ **8 領主委託**(各新鎮屠在地怪+清省內地城)+ **8 省份文化事件**(劍歌者/女巫結社/綠盟祭/雙月之舞…)+ **12 NPC**。**評估校正兩處 scanner 表層誤判**:既有外緣城其實早由 `court.generate_ruler_commissions` 自動發委託、events 早有巢狀 `trigger.provinces` 在地化(forage/predator)——故委託/事件本輪是「去單調·加文化深度」而非填空,**真缺口=地點數+NPC 數**(以執行期 `get_gamedata()` 求值校正,勿信表層 grep)。🔴 **新鎮鐵律(court 互動陷阱)**:**手寫 `ruler.quests` 會讓 `generate_ruler_commissions` 跳過該城 → 必自帶 `thane_gift`+`housecarl`,且委託 `reward.standing` 總和 ≥ `THANE_STANDING(3)`**(否則新城不可受封,`test_court` 紅);**additive 砍掉的既有城委託,其 NPC rumor/事件文字不可再廣告**(對抗審查抓到 2 處跨城張冠李戴 + 1 處廣告已砍委託)。**對抗審查 4 維修 8**:clear_dungeon reward 對齊 250、malachite/skooma/glass_cuirass 不上架(守玻璃甲=地城獎勵分層)、2 rumor 領主錯置(樹王/戰族酋長→本城)、1 rumor 廣告已砍委託、獸人名去拉丁混排、blurb 同句式去重。**52 測試模組全綠**(`test_world` 雙向/環/聚落必有城主/stock id、`test_court` 新城可受封、`test_lockpick` 盜賊公會閘)+ 無頭渲染煙霧(4 新鎮面板/委託/12 NPC/8 事件)+ **diff 證明零既有內容改動(只加逗號)**。**加新鎮純改 world+rulers+npcs+quests+events JSON**(type=town/danger=0/同省 biome/雙向 links/城主含 bloc+stance+gift+housecarl+委託 standing≥3)。

**NPC 條件式對話樹 + 外交立場軸(承「下一步」;plan-mode 評估 → 使用者拍板「加外交縱深 +1 欄」→ 直作 → 對抗審查修 6〔2 critical〕)**:評估驗證對話極扁平 —— `action_talk` 攀談任何 NPC 只給固定 4 動詞(quest/persuade/bribe/murder)、greeting/rumor 靜態、**9 個遊戲狀態維度(allegiance/city_bloc/factions/賞金/吸血鬼…)完全沒被對話讀取**。本輪把對話做成「NPC 是有立場的人」:**問候依 attitude 分歧**(friendly/neutral/cold/hostile/vampire_seen)+ **好感/身分分階話題**(本地時局/同袍內幕/表態結交/套話)+ **外交立場軸 `faction_standing`**(對話選擇被記住,討好一方得罪對立方=互斥真權衡;高價值話題受其門檻)。身分後果:看破吸血鬼 → 報官(`crime.add_bounty`)、敵陣營 → 拒談收窄、公會同袍 → 內幕話題;**口才第二用途**=套話 pry(付 practice)。**架構=複用最大化**:條件語法複用 `events.meets`(加無 state 鍵,events 零回歸)+ `dialogue.meets_dialogue` 包裝需 state/ctx 的鍵;NPC 陣營由 `politics.city_bloc/relationship` 推導(37/37 NPC 城皆有領主 → 零資料補洞);分階話題仿同伴 `dialogue[]`+`arc_offerable`;內容三層(全域 fallback 涵蓋全 102 NPC + attitude 模板 + 8 政治關鍵 NPC 手寫深樹,資料在新檔 `dialogue.json`)。Web 零工(對話全走 `ui.menu/message`)。**+2 存檔欄**(`faction_standing` 立場軸 + `dialogue_done` 一次性去重;皆 dataclass 預設、`cls(**d)` 向後相容、無 ensure_)。🔴 **對抗審查 4 維修 6**:① 帶 effects 話題零成本無限重選 → 無限刷 fame/立場(**critical**)→ 加 `once` 旗 + `dialogue_done` 去重 + 移除 intel/insider 的 fame;② pledge 單 NPC 連點推滿 ±100(**critical**)→ 表態一次性(每 NPC 一次,climb 須跨城逐人結交,且每次得罪對立方);③ hostile「拒談」被 extra/deep 旁路(major)→ `topics_for` 在 hostile 直接收窄為空;④ pump 副帶 +2 立場(minor,移除 —— 套話只給情報);⑤ say_by_rel 被 text 蓋死(minor,改 say_by_rel 優先);⑥ web chip tone `magenta`→`mag`。**53 測試模組全綠**(新增 `test_dialogue_tree`,含三漏洞回歸閘 + events.meets 對既有 req 等價)+ 無頭 `action_talk` 煙霧(各身分/陣營分歧 + 三漏洞閉合驗證)。**加 NPC 對話純改 `dialogue.json`**(問候/話題/模板;帶持久 effect 的話題務必標 `once` 防刷)。

**AI 陣營自走戰爭(worldstate 階段五;承「下一步」;plan-mode 評估 → 使用者拍板「全面戰爭含反攻」→ 直作 → sim 校準 → 對抗審查修 6〔1 major〕)**:政治地圖原是「死圖」(只有 5 個 once-fire 大事件、無 AI 迴圈),作者標「階段五/未做」的最大斷頭線。新引擎 `systems/aiwar.py` 掛 game_loop(**worldstate 後、tick_tax 前**),每 `WAR_HOURS`(週)決定性結算:imperial/independent(+`kvatch_falls` 解鎖後 daedric)互吞中立城、互翻彼此城(寫 `world_faction`)+「天下大勢」新聞;**反攻你親手攻下的城**(削 `garrison_current` + `city_threat` 預警 → 既有 `tick_tax` revolt 失守,數週才陷落〔sim 校準 ≥3 週〕、可 `reinforce` 守住,非離線即失);**你的 `allegiance`/`faction_standing` 傾斜戰爭天平**(與對話里程碑綜效:支持帝國→帝國均 23 城 vs 16)。**全程 `state.rng`+`sorted` 決定性**;非玩家城走 world_faction 層 → 玩家城三層優先序**自動免疫**(`test_player_held_city_immune_to_flip` 原樣通過)。**複用最大化**(`politics.faction_of`/`garrison_of`/`deplete_garrison`/`tick_tax` revolt/`base_garrison` + warband 量綱;**不改 politics 行為、不碰 bestiary R11**);城相鄰由 `world.json` links BFS 穿荒野推導(零地圖資料補洞);守方含「同陣營相鄰馳援」(`DEFENSE_RALLY`)→ 天然前線、反雪球。雪球防線:每週翻 ≤1 城 + 霸權煞車(進攻 damp + 其城 vuln,**在外交天平之後套用** → 蓋過選邊防一統)+ 佔領折扣 + 中立 floor。新 `sim_worldwar.py` 校準收斂(baseline 最大占比 65%/選邊 68% <70-75%、3 陣營存活、中立緩衝、決定性、反攻 feels-bad 雙閘、選邊有感)。**+2 存檔欄**(`war_tick_at`/`city_threat`,dataclass 預設向後相容)。🔴 **對抗審查 4 維修 6**:① **玩家選邊雪球一統 89%**(major,sim 原只測無大義 baseline 漏掉)→ 霸權煞車移到外交後套 + 守方霸權 vuln + 提高 `HEGEMONY_CAP` 讓選邊有感但封頂 + sim 補「選邊/daedric 收斂」閘;② `city_threat` 失守殘留 → 每輪 prune;③ `_raider_of` 非城防呆;④ check.sh 未追蹤檔也觸發 war sim;⑤⑥ nit(_ADJ_CACHE 單例/daedric fizzle,留置無害)。**54 測試模組全綠**(新增 `test_aiwar` 14 測,含選邊不雪球/反攻 revolt/決定性回歸閘)+ sim_worldwar 全綠 + 無頭 game_loop 整合煙霧。**調平衡改 aiwar.py 常數(必跑 `sim_worldwar.py`);加城純改 rulers.json**。 **⚠ 後續已移除 daedric 第三陣營(見 R24/R26):aiwar `AGGRESSOR_ORDER` 僅 imperial/independent,危機不再以城池易幟呈現。**

**後續修正(玩家回報 6 項;純修補,零新系統)**:① **領主侍從不再白丟** —— 受封武士時隊伍已滿,侍從進 `pending_companions` 待命池(新 1 欄,向後相容),隊伍選單可日後召集(複用 `party.summonable`)。② **傭兵羈絆/HP 離隊保留** —— `_dismiss_mercenary` 不再 `forget` 泛用傭兵(負傷者再雇仍負傷=防免費回血、羈絆有記憶);差別僅再取得方式(具名免費召集、傭兵付酬金)。③ **daedric 大義打不死** —— aiwar 加「湮滅復現」(`_daedric_resurgence`:kvatch_falls 後控城 < `DAEDRIC_FLOOR=3` 即開湮滅之門吞一城),sim 證 12 局 0 局永久滅亡(原 7 局);收斂仍守(daedric 最大占比 57% <75%)。**⚠ 此「湮滅復現」機制後已隨 daedric 陣營整個移除(見 R24/R26)。**④ **地城內可升級** —— 地城選單 `can_level_up` 時加「★ 升級」(複用 `action_level_up`,無環境依賴)。⑤ **套裝顯示效果+進度** —— 角色卡顯示套裝實際加成(`_describe_set_bonus`:魔力+40、施法省力 20%)+ 未滿四件的「X/4 進度」(`inventory.set_progress`)。⑥ **修理鎚可野外使用** —— 背包 → 修理鎚 → 「用此修理裝備」(`_repair_with_hammer`,城內/野外皆可)。**驗證**:54 測試模組全綠(更新 test_companions 傭兵保留、新增 test_party 待命召集/test_aiwar daedric 復現/test_equipment set_progress)+ sim_worldwar 全綠 + 無頭煙霧。**5a 疊加附魔暫不做**(布甲預附魔維持)。

**房產 & 坐騎(家園與後勤 + 騎乘戰技;承「下一步」;plan-mode 評估 → 使用者拍板「合一里程碑·房產收納+最佳休息·坐騎三類給被動+戰技·三系都提升·長槍可鍛可買」→ 直作 → sim 校準守紅線)**:玩家原是「四處遊蕩、無家、靠雙腿」的英雄。本輪補上經典上古卷軸的安定生活/後勤/騎乘層,合為**一個**里程碑。**房產**(`systems/housing.py` + `data/houses.json` 八省主城各一):① **收納倉庫**(`house_stash`,存物**不計隨身負重** —— `total_weight` 只迭代 inventory,天生豁免;存入禁穿戴/手持〔免漏 recompute〕、取出以負重〔含鞍袋〕為閘、毀損 id 不崩)② **最佳休息**(免費全回)+「**精神飽滿**」增益(`well_rested_until` 權威 + `well_rested` 快取〔game_loop 頂端刷新,同 beast_form 模式〕→ `progression.use_skill` 讀快取乘 `WELL_RESTED_XP_MULT`;**不寫 base**)。**坐騎**(`systems/mounts.py` + `data/mounts.json` 分三類,皆共享旅行加速+鞍袋負重、按類別調校):**戰馬**(馱載最大 + 開場「衝鋒」戰技:長槍=武器傷×高倍率、其他近戰=2 段坐騎踐踏+武器)/**獵馬**(旅行最快+規避遭遇 + 「騎射」戰技:開場閃避增益)/**法駒**(無主動,以較強被動補缺口=騎乘作戰法術增益)。戰技/法術增益**僅野外旅途/探索遭遇生效**(進地城/朝堂/攻城自動下馬;以 `mounted` 旗 + `active_mount` + 武器流派三重閘)。**長槍是新武器系**(新 `archetype="spear"`、用既有 `blade` 技能,跨材質階,馬廄買 + 鍛造;archetype 落回 formulas 安全預設 → **零偷襲加成**)。🔴 **紅線守**:衝鋒**絕不走 `sneak_mult`**(`resolve_attack` 衝鋒首擊 `["sneak"] is None`)、受獨立 `MOUNTED_CHARGE_DAMAGE_CAP_RATIO(0.45)` 夾 → sim 證 solo boss 開場衝鋒 0% 秒殺;鞍袋=負重上限即時算(`max_weight(char, gamedata)`,**非資源、不進 recompute、不寫 base**);法駒法傷接 `magic.cast(mounted=)`(僅騎乘戰、守 R10);騎射閃避走聚合層(`evasion += _ride_evasion`,不遮蔽 acrobatics/mastery)。**56 測試模組全綠**(新增 `test_housing`/`test_mounts`,含倉庫負重豁免/存穿戴擋/衝鋒非偷襲+solo 夾/法駒增益/精神飽滿不寫 base/存檔相容)+ `sim_assassin` 全綠(動 combat/formulas,solo 秒殺率 0% 零退化)+ 無頭整合煙霧(騎乘衝鋒/騎射/法駒施法戰鬥)。**Web 走共用 game loop 文字 fallback**(馬廄/房產/倉庫選單即可用;原生面板可後補)。**加房產純改 houses.json、加坐騎/長槍純改 mounts.json+weapons.json+recipes.json**。

**開局起手任務 + 新開局 + 出身/任務面板(承「下一步」;plan-mode 評估 → 使用者拍板「每開局配 2–3 段起手任務 + 加 ~9 新開局 + 三面板改善」→ 直作;零 sim〔不碰戰鬥常數〕)**:開局原只給起始處境、無「我為何在這」的敘事引導(handoff 早標「起手任務鉤子 MVP 刻意未做」)。本輪補上:① **每個開局配一條 2–3 階段起手任務**(`data/quests.json` 新 `source:"origin"` 24 條;創角時由 `creation.apply_origin` 末端**自動接取**〔`char.is_player` 閘 + 冪等;NPC 不發〕,複用既有任務引擎 kill/reach/collect 自動推進結算)。② **新增 9 種開局**(帝國軍團退伍兵/綠林獵手/商隊護衛/尋墓探寶者/灰民部族子弟/拒誓者女巫/騎士見習/碼頭偷渡者/流浪吟遊詩人;跨省、補職業/處境缺口 → 共 **24 開局**)。③ **三面板改善(終端 + Web 雙渲染)**:新 `origins_panel`(創角前列各開局起始地/金幣/裝備·身分/起手任務)+ 任務日誌**分組**(起手/公會/委託)**＋階段進度**(✔▶· 各階段 done/cur/todo)+ 角色卡**出身欄** + 創角首入「你的去向」提示。🔴 **起手任務授權邊際鐵律(對齊 `quests._objective_met`)**:`reach` 階段**絕不**指向該開局自身起始地(會即時完成)、`collect` **絕不**取起始包既有物(會即時滿足)、第一階段最和緩、**禁 `clear_dungeon`**(R18,新角不入地城);全部以「建角即未達標」測試一擊把關。**57 測試模組全綠**(新增 `test_origin_quests`:逐開局自動接取/NPC 不發/schema-lint/無 reach-self+collect-pitfall/代表性鏈完成發獎/面板資料結構/存檔往返;擴 `test_origins` quest 交叉引用)+ 無頭煙霧。**Web 端**:新 `renderOrigins` + `VIEWS` 註冊、`renderQuests` 改分組+階段、`renderSheet` 補出身列(`tesrpg/web/static/index.html`)。**加開局純改 origins.json;加/改起手任務純改 quests.json**(守授權邊際鐵律)。

**評估修補 2 項(玩家回報:開局選單太長 + 星座 法師<學徒;純修補)**:① **開局選單兩層化 + 一覽即選單** —— 24 種開局單層 + 長 blurb 爆版 → 改 `_choose_origin` 兩層(先選 5 類〔戰士/法師/潛行/血脈/浪人,`main.ORIGIN_CATEGORIES`〕→ `ui.origin_picker(oids)`:**該類一覽面板本身即選擇器**〔web 直接點開局卡 data-key=id,經 `extra_keys`+`wireActionableRows`,僅一顆「返回」鈕、無冗餘按鈕列;終端面板加編號、輸入編號選,0=返回〕);漏歸類者安全網進「浪人」(`test_origin_categories_cover_all` 守涵蓋)。② **星座弱點機制補回(法師<學徒 根因=弱點只是 flavor)** —— 學徒座 note 寫「易受魔法所傷」卻**從未實作**(無 resist 欄、`entity_resist` 也無星座層)→ 學徒(+100 魔力)嚴格碾壓法師(+50)。修:`birthsigns.json` 補 `resist`(學徒 `magic:-50`、領主 `fire:-25`),`magic.entity_resist` 加「**星座抗性層**」(即時讀 `birthsigns[sign].resist` → **免存檔欄、向後相容**)。現學徒=高魔力但火/霜/雷/魔法傷害↑(風險換報酬)、法師=安全牌。**57 測試模組全綠**(新增 `test_magic.test_birthsign_resist_weakness` delta 斷言〔種族基線無關〕、`test_origin_categories_cover_all`)+ `sim_assassin` solo 秒殺率 0% 零退化(sim 建角無 resist 星座 → byte-identical)+ 煙霧通(兩層創角)。**調星座弱點純改 birthsigns.json `resist`;加開局分類改 `ORIGIN_CATEGORIES`**。

**評估修補:出身↔職業接上(玩家回報「出身和職業接不上」;評估 → 使用者拍板「反轉主軸:先出身→再推薦職業 + 武器追加而非取代」→ 直作 → 對抗審查修 3)**:創角原是「先選職業、再選出身」兩個互不知道的步驟,開局選單兩層化後分類(戰士/法師/潛行…)看起來像「再選一次原型」卻與已選職業零連動 → 能組出「法師×戰友團新血」這種身分與本事打架的角色,系統不提示。根因:唯一構想過的接點(handoff 早期「依職業過濾推薦」)從未實作,`_choose_origin` 沒收到 class。**守 R18**(不讓出身碰屬性/技能):① **反轉順序** —— `create_character` 改先 `_choose_origin` → 再 `_choose_class(gamedata, origin_id)`;出身選用 `classes` 欄(推薦職業 id,純 UI)→ 契合職業標 `★推薦`+排前(**不過濾、不強制**),處境型開局留空=適配任意。`_quick_character` 也先抽出身、再從 `classes` 抽職業 → 快速開始不再產不協調角色。② **武器追加而非取代** —— `apply_origin` 對**純施法者**(無武器系主修,`_equips_origin_weapon` 判定)選近戰出身時只把武器追加進背包、不換手(保留依技能起始武器);法杖等施法武器與**有武器主修的混合職(戰法師等)**仍照常換上升級。③ **開局卡帶推薦職業** —— `_origin_card` 加 `classes`(映中文名),終端 `origins_panel` 加「推薦職業」欄、Web `renderOrigins` 加 ★ chip → 選出身當下即見。🔴 **對抗審查 4 維修 3**:battlemage 被 `spec=="magic"` 誤殺丟近戰升級(改判 `major_skills` 含武器技能)、開局卡未露推薦(補)、標題括號全半形不一(修)。**57 測試模組全綠**(`test_origins` 擴:推薦對應釘樁 + 純施法者 vs 混合職武器兩側 + 快速開始一致性 + 開局卡推薦欄)+ 無頭煙霧(300 次快速開始 0 不協調、推薦排序/★/標題)+ 不碰戰鬥常數故零 sim。**加/改推薦純改 `origins.json` `classes` 欄(見 R18)**。

**評估修補:鍛造難鍛鍊 + 材料難取得(玩家回報;評估 workflow 定根因 → 使用者拍板「回爐機制(有損耗)+ 調高材料商店刷新量」→ 直作 → 對抗審查 4 維修 多項)**:評估證實兩根因——① 鍛造是**唯一冒險中零被動成長**的戰鬥系技能(blade 每場戰鬥都漲,鍛造只能在城裡純練 practice/craft/temper);② 高價錠(value>80:moonstone/dwarven/malachite/ebony)`_restock_qty` 每 3 天每城只補 **0–1**,但配方需 2–4 個 → 湊不齊。本輪:
- **回爐熔解**(新 `smithing.meltdown`/`meltable`/`meltdown_yield` + `RECYCLE_RATIO=0.5`;`action_meltdown` 掛 armorer 站點市集「回爐熔解 ♻」):把不需要的武器/護甲熔回部分材料(**有損耗**:有配方→反查該錠用量×0.5 無條件捨去〔單錠成品→0,確保損耗〕;無配方→成品 value≥錠 value 才回收 1),**且同時練鍛造**(付 `practice_cost`)→ 一石二鳥同解兩痛點。🔴 排除:**附魔成品/具名神器**(`d['enchant']`,不可逆毀——魔族剃刀/附魔法杖/法袍)、**弓·弩·法杖**(`_NON_MELT_ARCHETYPES`)、飾品、**龍鱗裝**(`_NON_RECYCLE_INGOTS={dragon_scale}`)、廉於一錠的單品;**手持/副手/穿戴中**須先卸下(防裝備脫鉤)。反套利:回爐材料價值恆 ≤ 成品買價(廉品熔之無得),`daedra_heart`/`dragon_scale` **不由回爐產出**(維持 loot-only)。
- **材料補貨足量**(`world._restock_qty` 加 `material` 分支=`randint(3,8)`;`ensure_stock` 用 `_crafting_material_ids` 判定):鍛造材料(配方輸入,**排除 loot-only `daedra_heart`/`dragon_scale`**)獨立於價值給足量、不缺貨 → 湊得齊一件裝備。**反套利防線不動**:成品仍照價值稀缺(全配方掃描證「買材料→製作→賣成品」恆虧,最高毛利 −20);loot-only 稀材排除於程式(非靠不上架的資料慣例)。
- **對抗審查 4 維**(18 確認多為同源):major=神器 mehrunes_razor 可被回爐毀(→ `enchant` 排除);minor=副手漏守門(→ 納 offhand)、弓/法杖可melt 打臉 UI(→ archetype 排除 + 文案校正)、補貨含 loot-only 稀材(→ 程式排除)。**57 測試模組全綠**(`test_smithing` 加回爐/損耗/反套利/附魔·弓·法杖·副手排除;`test_shop` 加材料足量+稀材不補)+ 無頭煙霧 + 不碰戰鬥常數故零 sim。**調回爐損耗改 `RECYCLE_RATIO`;加可回爐材質沿用 `_MATERIAL_INGOT`;調補貨量改 `_restock_qty`**。

**鍛造紓困 II(玩家再回報:材料只兩城賣 + 鋼套裝無法全鍛;純資料/規則,零 sim)**:承上輪「補貨量」修補,本輪補「地理分布」與「配方缺漏」兩缺口。
- **材料分級供給**(`world.merchant_catalog` 規則注入,使用者拍板「一般材料幾乎每城都有、高級材料只在大城」):每座 `type=city` 自動供應**一般材料** `_COMMON_MATERIALS`(鐵/鋼錠·布匹·狼皮);**大城** `MAJOR_CITIES`(各省首府,每省一座→區域內買得到頂材不必跨圖)另供**高級材料** `_HIGH_MATERIALS`(月長石/矮人/綠玉/黑檀錠)。規則注入(非逐城改 JSON)→ **新城自動涵蓋**;去重保留既有明列。高材城 2→8(每省一座)。**調供給點改 `MAJOR_CITIES`;調分級改 `_COMMON/_HIGH_MATERIALS`**。
- **鋼套裝補全**(`recipes.json` +4):補 `forge_steel_gauntlets/boots/shield/dagger`(req 25、Σ材料值≥產出 守反套利)→ 鋼護甲 5 件全可鍛。**僅鋼套裝是真缺口**;archmage 套(公會獎勵/帝都商店)、daedric_staff(drop-only)、mehrunes_razor(具名神器)刻意不可鍛。
- **驗證**:**57 測試模組全綠**(`test_shop` 加分級供給〔每城有一般材、大城齊高材、每省一座大城〕;`test_smithing` 加鋼套裝全可鍛)+ 端到端購買煙霧(小城買鋼錠/大城買黑檀錠)+ 反套利覆核(全配方最高毛利 −20)+ 無 raw merchant_stock 旁路。**加新城自動得材料;加材質配方純改 recipes.json**。

**淬鍊效果可見(玩家回報「淬鍊的效果看不到」;UI 顯示 bug 修)**:淬鍊真實生效(`combat._weapon_profile`/`_armor_rating` 計入),但**顯示層數字不反映**——`weapon_line` 只列技能等級不列傷害、護甲值走 `inventory.worn_armor_rating`/`effective_armor_rating`(刻意只算名目/耐久、不含淬鍊;戰鬥另在 `combat._armor_rating` 加 flat 淬鍊)→ 淬甲後護甲數字不動,玩家以為沒效。修(純顯示、不動戰鬥/存檔):① `weapon_line` 加「傷害 N」(= 武器基礎傷 + `weapon_temper_bonus`,= 戰鬥基礎傷)+ 保留既有「·淬+N」標(徒手不列傷害);② 新 `console._armor_display`(回 名目/有效,皆加 `armor_temper_bonus`)取代 4 處直接讀 `worn/effective_armor_rating` 的顯示(角色卡/穿戴面板/web 狀態,終端+Web 一致)。**不改** `worn/effective_armor_rating`(戰鬥 base 共用、避免重複計)。**57 測試模組全綠**(`test_smithing` 加 `test_temper_visible_in_display`:淬後武器行傷害+護甲顯示上升且對齊戰鬥加成)+ 煙霧(淬±3 → 傷害 13→19、護甲 15→18)+ 零 sim。**淬鍊顯示經 `weapon_line`/`_armor_display` 單源,改顯示動此二處**。

**修兩 bug:總管離隊 + 神器效果可見(玩家回報;對抗審查修 3 minor + 3 nit)**:
- **BUG1 親衛冊封總管後不離隊**(仍隨行出戰/在隊):`appoint_steward` 只記 `char.stewards[loc]=cid`、未排除出戰。修:① `party.fieldable` 排除 `stationed=set(char.stewards.values())`(+ 倒下 + `cid in gamedata.companions`),`main.run_battle` 預設隊伍改走 `fieldable`、顯式名冊(城戰)也排除 stationed → 坐鎮者不出戰;② `_party_label` 坐鎮者標「（坐鎮〔城〕…)」;③ 軍勢營地親衛列表排除坐鎮者。**保留 steward 於 `char.companions`**(`politics.has_steward` 需 `sid in companions`、可召回;`recall_steward` 後自動回隊)。對抗審查補:解散坐鎮中的總管 `_dismiss_mercenary` 同步 pop `stewards` 殘留(免死 cid 占位)。
- **BUG2 神器/附魔效果看不到**:效果其實有套用(combat 讀武器 `enchant`、`equipment_bonuses` 讀護甲/飾品 `enchant`、`lycanthropy` 讀 `hircine` 旗),但顯示層沒露。修:新 `console._enchant_desc`/`_ench_suffix`(描述 weapon_element/weapon_status/fortify_skill/attr/armor_fortify/resist_element + `hircine` 旗;**synth 自製附魔略過**〔名稱已內嵌效果,免重複〕;**缺鍵全防崩**)→ 於 `weapon_line`(武器附魔)、`sheet_equipment` 每件穿戴(web+終端)、`item_label`(取代籠統「已附魔」)顯示。神器效果一律可見(魔銳茲之刃 `·雷電傷+25`、獵者之戒 `·可隨意獸化`)。
- **驗證**:**57 測試模組全綠**(`test_party` 加總管離隊/召回回隊/解散清指派;`test_sheet` 加 `_enchant_desc`+武器行+背包神器可見)+ 煙霧(冊封→離隊→召回;synth 不重複;缺鍵不崩)+ 零 sim。**改總管出戰判定動 `party.fieldable`;改附魔顯示動 `_enchant_desc`(單源)**。

**內容量**:10 種族 / 13 星座 / 8 職業 / **23 技能(+偵查 scout、+鍛造 smithing)** / **25 武器(4 法杖 + 6 長槍)** / **42 護甲(7 材質整套 + 法師布甲學徒/大法師 2 階 8 件)** / **43 法術(六學派各 ≥5、召喚/秘術補完至各 7;5 AoE + 8 中庸支援 + 束縛兵刃/亡者復生/法術結界/驅散/群體擒魂)** /
**15 煉金材料(全部可野外採集/獵取)+ 7 鍛造材料(鐵/鋼/月長石/矮人/綠玉/黑檀錠 + 布匹)** / **5 飾品(含具名神器獵者之戒)** / **鍛造系統(鍛造技能 + 45 配方〔皮甲/鐵鋼+精靈/矮人/玻璃/黑檀金屬/法袍〕+ skill_req 分級 + 全階裝備淬鍊強化)** / **80 生物(7 高階 elite + 2 吸血鬼 + 2 狼人〔含 alpha solo〕 + 5 黑沼澤 + 5 漢默法爾沙漠〔含矮人百夫長 boss〕 + 5 高岩霧沼〔含海妖岩魔女 boss〕 + 5 瓦倫雨林〔含遠古樹靈 boss〕 + 6 艾爾斯維爾草原弱毒〔含暗月暗虎 solo boss〕 + 8 黑兄目標 + 7 神話黎明目標 + 6 九神聖戰目標 + 2 戰友團〔銀手/格倫魔女,天際野生可遇〕 + 2 heartland + 4 晨風灰原生態〔崖行鳥/阿利特/尼克斯獵犬/卡古地,解晨風委託只能輪替灰蹦蟲〕;45 隻帶 biome 生態標籤)** / **9 具名同伴(角色化:4 具名化傭兵斯特倫/葛蕾塔/薇拉妮/基蘭 + 2 圈內盾袍兄弟法卡斯/艾拉 + 3 招募具名德雷拉斯/賈拉卡爾/拉希德;各有 4 階對話 + 專屬支線 + 忠誠弧頂點)+ footman/veteran(士兵/將領)** / **68 地點(有環圖+生態 biome〔heartland/snow/ashland/swamp/desert/moor/jungle/savanna〕,世界閉成五大環〔黑沼澤南環 + 漢默法爾西環 + 高岩西北環 + 瓦倫森林西南環 + 艾爾斯維爾南環〕;賽8/天9/晨8/黑7/漢6/高6/瓦6/艾6/邊12,共 25 城+12 鎮)** / **15 地城(程序化 n×n × m 層格子探索:移動/分層/樓梯/迷霧/首領死亡自動解鎖寶藏;含湮滅危機 5 座 danger5-6 終局地城)** / **主線弧:湮滅危機(達貢;雙路線/雙結局)** / **任務(3 分支壓軸 + 解咒×3〔血咒/淨糖/獸血〕 + 6 黑兄合約 + 6 神話黎明合約 + 6 九神聖戰合約 + 14 在地任務含 2 任務鏈 + 屠龍 + 漢默法爾 3 + 高岩 3 + 瓦倫 3 + 艾爾斯維爾 3 + 4 新鎮各 2 領主委託 8 + 24 空城在地指路任務 18(npc-source) + 戰友團 6〔含內圈引渡多階 + 嗣血/淨血壓軸〕 + 同伴 3 招募〔德雷拉斯/賈拉卡爾/拉希德〕+ 9 同伴專屬支線〔忠誠弧〕+ 24 開局起手任務線〔每開局一條 2–3 階段,source=origin,創角自動接取〕)** / **7 公會(+神話黎明/九神騎士團 大事件解鎖 + 戰友團〔白漫·一般公會流·狼人血脈歸宿〕)** / **24 開局背景(15 既有 + 帝國軍團退伍兵/綠林獵手/商隊護衛/尋墓探寶者/灰民部族/拒誓者女巫/騎士見習/碼頭偷渡者/流浪吟遊詩人;各帶起手任務 + 創角資訊面板)** / **178 NPC(每座非邊境城/鎮全覆蓋〔城 3 / 鎮 2,無空城〕,角色多樣、greeting + rumor 指路;含 24 空城補滿 71 NPC + ~30 名掛在地委託/指路任務 + 3 招募具名同伴家鄉)** / **44 事件(含 28 省份限定;含艾爾斯維爾糖楓採集/草海掠食 + 外緣四省文化事件〔劍歌者/女巫結社/綠盟祭/雙月之舞〕)** / **吸血鬼化系統** / **狼人化系統(主動限時獸形變身,吸血鬼的對位;與吸血鬼互斥)** / **斯庫瑪成癮系統(亢奮↔戒斷天平)** / **黑暗兄弟會系統** / **技能里程碑系統(全 23 技能各 25/50/75/100 完整階梯、92 節點;25=單一 perk 自動授予、50/75/100=二選一)** / **37 城主(各城自治)** / **24 具名地標(各省招牌/邊境發現,首次抵達一次性獎勵)**。
程式:**34 個 `systems` 模組**(+housing〔房產:倉庫/最佳休息/精神飽滿〕+mounts〔坐騎三類:旅行/鞍袋/衝鋒·騎射·法駒法術〕 +aiwar〔AI 陣營自走戰爭〕 +vampirism +brotherhood +mastery +crafting +court +politics +warband +landmarks +achievements +smithing〔淬鍊強化〕+skooma〔斯庫瑪成癮〕+lycanthropy〔狼人化〕+party〔同伴深化〕+dungeoncrawl〔格子地城生成〕)+ models/ui/synth 等,共約 49 個 `.py` + `sim_assassin.py`/`sim_worldwar.py`(平衡回歸);**29 個 `data/*.json`**(+houses.json〔房產〕+mounts.json〔坐騎+馬廄城+長槍販售〕+mastery.json +recipes.json +landmarks.json +achievements.json +dialogue.json〔條件式對話樹〕;黑兄/細化省分/城戰立場/招兵兵種/漢默法爾/高岩/瓦倫森林/法袍+鍛造材料/**狼人/獵者之戒/戰友團〔第7公會〕/八職功能身份/長槍〔archetype=spear〕**全靠改既有檔);**56 測試模組**(+test_mastery +test_practice_cost +test_shop +test_crafting +test_court +test_politics +test_warband +test_worldstate +test_mythicdawn +test_knights +test_landmarks +test_polish +test_sheet +test_web +test_achievements +test_smithing +test_dungeon +test_speechcraft +test_skooma +test_lycanthropy +test_party +test_attributes +test_hybrids +test_companions +test_class_identity +test_spell_schema +test_companion_arcs +test_dialogue_tree +test_aiwar +test_housing +test_mounts +test_origin_quests)(共 **57 測試模組**)。**新增 `tesrpg/web/` 套件(本機 Web 版,純 stdlib、零 pip;`python3 -m tesrpg.web`)**。 / **成就系統(24 條,唯讀推導、結算+即時角色卡)**。 / **四中庸職業功能性區分(戰法師奧術灌注 / 治療師戰地援護 / 騎士號令 / 弓手散兵武技;純改 `magic.py`+`combat.py`+`spells.json`+`world.json`+`creation.py`,零新系統模組/零新存檔欄)**。 / **八職功能性身份網格(全 8 職各一招牌戰術 loop:mage 奧術連鎖 / battlemage 共鳴一擊+法力回擊〔毀滅 50/75 互換後可兼得〕 / thief 諜報偵搜 / archer 獵手偵察 / warrior 盾牆 / knight 戰旗 / healer 戰地搶救 / assassin 致命烙印;6 mastery 二選一節點 + 2 戰鬥動作;純改 `mastery.py/json`+`magic.py`+`combat.py`+`main.py`,零新系統模組/零新存檔欄;sim byte-identical)**。 / **戰友團(第 7 公會;白漫·一般公會流;獸血儀式由戰士公會移籍至內圈〔`lycanthropy.RITUAL_RANK_INDEX`〕;`merc_discount` perk + circle 盾袍兄弟;純改 factions/world/quests/bestiary/companions/origins JSON + `factions.py`/`lycanthropy.py`/`main.py` 小面 wiring,零新系統模組/零新存檔欄)**。 / **地城格子探索(程序化 n×n × m 層;新 `dungeoncrawl.py` 生成器 + `action_dungeon` 改寫為 crawl 子迴圈 + `dungeon_grid` 雙端渲染;dungeons.json 改參數化 spec;首領死亡自動解鎖寶藏;原子探索零新存檔欄;sim byte-identical)**。 / **法術學派補完(召喚/秘術各補至 7 法術:束縛兵刃〔法系近戰,完全取代裝備武器〕/ 亡者復生 / 法術結界〔吸魔變體〕/ 驅散 / 群體擒魂 + 冰雷元素/魔人召喚;`magic.py` 4 新 effect kind + `combat.py` 束縛兵刃/ward 掛鉤,純改 spells/bestiary/world JSON;零新系統模組/零新存檔欄;sim byte-identical)**。 / **地城視為戰鬥情境(一般行動施法/背包/角色卡 + 預施增益/預召喚召喚物〔行動 1 格=1 回合衰減,`run_battle` carry_allies/preserve_buffs 帶入〕+ 偵查 perk 探明四鄰〔每探明新格練偵查〕+ 狀態條/HUD 顯示夥伴/召喚物 + 施法後敵狀態即時補繪;純改 `main.py`/`console.py`/web + `mastery.has_recon_perk`/`formulas` 常數,零新系統模組/零新存檔欄;sim byte-identical)**。 / **技能里程碑廣度 pass(17 薄技能各 +1 功能節點 → 全 23 技能 ≥2 節點、47 節點;13 純 JSON 複用功能 kind + attr_fortify 首用 + 4 新 kind〔combat_repair/flee_bonus/armor_reflect/trap_floor〕+ weapon_mod 合併/repair_floor MAX;對抗審查修系統性「同源多節點遮蔽」〔spell_mod/passive_armor/poison/evasion getter 全改聚合〕+ illusion 死碼修 + passive_armor 解魔力閘;純改 mastery.json + `mastery.py` getter + 3 處呼叫端,零新系統模組/零新存檔欄;sim 紅線守)**。 / **同伴角色化(具名同伴 + 招募任務 + 專屬支線 + 對話 + 忠誠弧頂點:複用 `companion_bond` 當忠誠軸、`reward.companion`/`reward.bond` 資料驅動授予、`action_party` 交談/召集、戰術頂點走盟友限定光環〔empower `not _is_player`〕、被動頂點走 barter/travel;6 既有同伴角色化 + 3 新招募具名;純改 `party.py`/`quests.py`/`main.py`/`world.py`/`legacy.py`/`console.py` + companions/npcs/quests JSON,零新系統模組/零新存檔欄;sim 紅線守、對抗審查修 orphan 羈絆破口)**。

---

## 2. 架構地圖

```
tesrpg/
├── main.py          進入點 + 主迴圈(hub 分組選單;城鎮服務分 市集/公會/廣場 三區子選單,
│                    新增城鎮服務 → 歸入對應 district list〔market/guilds/plaza〕即可)+ action_* + run_battle
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
│   ├── vampirism    吸血鬼化狀態機(力量↔詛咒;game_loop 每圈 update)
│   ├── brotherhood  黑暗兄弟會(血債招募/合約晉升/夜母祝福/洗白賞金)
│   ├── mastery      技能里程碑(達門檻自動解鎖被動;base_skill 推導 + kind 白名單)
│   ├── loot         resolve_loot(怪物掉落 + 寶箱共用)
│   ├── legacy       一生傳奇總結 + 評分
│   └── events       事件引擎(DESIGN 3.8)
└── ui/console.py    Web 渲染/輸入接層:`_*_view` view-model + rich→HTML 退路 + menu/grouped_menu/輸入(走 `_web_prompt`)
```

---

## 3. 關鍵慣例 — 鐵律規則簿(務必遵守)

> **鐵律規則簿**:以下每條 `R##` 為穩定編號(**append-only、永不重用**;退役改標 `~~R##(已廢)~~`,不重新編號,讓 commit/舊文裡的引用永久有效)。`CLAUDE.md` 只放跨領域紅線 + 本簿的 `R##` 索引(以要旨指向這裡);**規則本體一律以本節為準**,索引只是指標。標籤義務:`[re-sim]` 改動須重跑 `sim_assassin.py`、`[recompute]` 須 `stats.recompute_max_resources`、`[migrate]` 須 `ensure_*` 遷移、`[save-compat]` 須維持存檔向後相容。

**總則(R01–R03)**

### R01 · 語言慣例

- **語言**:程式碼/變數/資料 key 用**英文**(沿用 TES 原文如 `destruction`/`altmer`);玩家看到的文字用**繁體中文**。
### R02 · 資料驅動

- **資料驅動**:新增地點/生物/物品/法術/任務/事件 → **改 JSON 即可,不動邏輯**。

### R03 · 存檔規則 [save-compat]

- **存檔規則**:
  - `Character.to_dict/from_dict` 必須涵蓋每個欄位;`from_dict` 用 `cls(**d)`,靠 dataclass 預設值做**向後相容**(舊存檔缺欄位 → 用預設)。
  - **`active_effects` 不寫入存檔**(戰鬥內臨時效果);合成物品只存 id(synth 重建)。
  - 對毀損/舊存檔**防禦性夾限**(例:`quests._stage_index` 用 `max(0, min(...))`、公會階級夾限、`companions` 過濾未知 id)。
**戰鬥 · 資源 · 升級(R04–R06)**

### R04 · 戰鬥通用 resolve_attack

- **戰鬥**:`combat.resolve_attack` 通用於玩家/同伴/敵人**任意組合**;`clamp_resources` **只對玩家側**呼叫(怪物 hp 由 `_set_hp` 夾限)。

### R05 · 衍生上限 / 護甲 fortify [recompute]

- **衍生上限/護甲 fortify**:`max_health` 是**有效**上限(`base_max_health` 真基底 + 升級 `resource_levels` + 穿戴護甲 `armor_fortify`);
  `stats.recompute_max_resources(char, gamedata, …)` **務必帶 gamedata**(否則 fortify 視為 0,會吃掉加成)。
  **任何改動 `char.equipped` 的路徑(穿/卸/丟棄/出售)之後都要 recompute**;`inventory.remove_item` 會自動卸下但**不**重算(M14 踩過這個雷)。
### R06 · 升級系統(M15) [migrate]

- **升級系統(M15)**:`level_xp` 是升級進度(**所有技能升點都餵**,主修 ×1.5);`level_progress`/`level_skillups` 是停用的舊欄位,只為舊存檔 `cls(**d)` 保留。
  `apply_level_up(char, gd, attribute_points: dict, resource_choice)`。**載入存檔走 `GameState.from_dict` 會自動 `ensure_level_xp` 遷移**(舊 `level_progress`→`level_xp`),別繞過它直接建 Character 否則舊存檔升級入口會被隱藏(審查踩過)。
  `max_health` **不再隨耐力逐級長**(改由升級「生命」三選一);改升級公式只動 `formulas.py` 的 `LEVELUP_*` 常數即可平衡。
**潛行 · 刺客 · 魔法(R07–R10)**

### R07 · 潛行系戰鬥(偷襲 / 隱遁 / 雙持) [re-sim]

- **潛行系戰鬥(M16 + 刺客大改)**:`sneak` 開場偷襲只在 `run_battle` 第一個行動為攻擊且 `opening` 為真時觸發(僅玩家);`acrobatics` 閃避從 `hit_chance` 扣 `dodge_evasion`。**`opening` 現在不再無條件保證**:① 入場由 `offer_battle` 的 `try_stealth_approach` 檢定決定(失敗 → `run_battle(alerted=True)`→opening 起手即 False);② 旅途伏擊 `surprise=True` 幾乎拿不到;③ 隱遁成功會把 `opening` 重新點亮(`opening = vanish_success`,別改回無條件關閉)。
  - **暗殺殘響**:全在 `resolve_attack` 偷襲分支末端(`sneaking and is_alive(defender)`),掛 `stagger`/`bleed(element=bleed)` 到 defender;踉蹌命中減成在 `hit_chance` 後對「被踉蹌的 attacker」扣 `STAGGER_HIT_PENALTY`。調平衡只改 `formulas` 的 `_ARCHETYPE_SNEAK_AFTERMATH`/`SNEAK_BLEED_*`/`STAGGER_HIT_PENALTY`。
  - **雙持**:`offhand` 只存 id;**副手傷害必須在 `sneak_mult 之後`才加(不吃偷襲倍率)**——`resolve_attack` 與 `estimate_sneak_damage` 兩處要一致,否則精英被秒(審查踩過)。同型雙持需 2 把;`remove_item` 跨門檻會清 `offhand`。雙持時 `_choose_combat_action` 不給格擋。
    - **副手附魔生效(以 `OFFHAND_DAMAGE_FACTOR`=0.6 權重疊主手)**:`resolve_attack` 讀 `offhand_ench`,元素/吸血/再生按 ×0.6 疊上、麻痺各自獨立擲一次(binary 不打折,solo boss 仍免疫)。雙持雙吸血 = 0.30+0.30×0.6=**0.48**(回血夾在本擊傷害內)。元素疊在 dmg、**夾限前**(偷襲不放大、solo 受夾)。UI `weapon_line` 顯示「雙持 X(每擊 +N 傷)」讓 ×0.6 補刀可見。
  - **隱遁**:`try_vanish` 成功跳過敵人階段;**三道煞車缺一不可**——`player_vanish_cost` 體力、`vanishes_done` 每次嘗試遞增(非僅成功)、`MAX_VANISHES_PER_BATTLE` 硬上限。少了會變無限風箏無傷清精英(審查踩過 critical)。
  - **入場檢定/偵查**:`stealth_approach_chance` 吃 **`inventory.armor_worn_weight`(連續重量噪音,經 `formulas.stealth_weight_penalty`;取代舊二元 `dominant_weight_class`)** + 夜間(`hour<6 or >=21`)+ `scouted` + `surprise`。`scout` 是第 22 技能;**新增技能務必同步 `progression.ensure_all_skills`**(舊存檔遷移)。
  - **輕甲對重甲的潛行優勢(依實際穿戴總重,雙端)**:① **命中端** `stealth_weight_penalty(W)=clamp((W-4)×0.017,0,0.75)`(法袍 W5 幾乎無罰、龍鱗 W18 中等、重甲遞增到封頂);② **倍率端** `formulas.armor_sneak_mult_factor(W)=clamp(1-(W-18)×0.012,0.45,1.0)`——**門檻 18 以下不打折**(法袍/皮甲/玻璃/龍鱗等輕甲全段 ×1.0),只有重甲(W>18)偷到也爆發打折。在 `resolve_attack` 的 `sneak_mult` 連乘加一項、`estimate_sneak_damage` 同步。`armor_worn_weight` 只計帶 `weight_class` 的甲/盾(飾品/武器不計)。🔴 **`armor_relief`(無聲披掛)只抵命中端噪音、不抵倍率折扣**——兩條路徑互不相抵;倍率端安全只能靠低總重(輕甲)。改 `armor_sneak_mult_factor`/`SNEAK_MULT_WEIGHT_*` 踩偷襲倍率紅線 → **必跑 sim_assassin**。
  - **平衡回歸**:改任何刺客常數後跑 `PYTHONPATH=. python3 sim_assassin.py` 對照(救失手/不秒精英/無風箏)。
### R08 · 偵查備戰(scout → prep)

- **偵查備戰(scout→備戰空間)**:潛近成功(`got_drop`)且未被伏擊時,`formulas.prep_budget(scout)`(20/50/75→1/2/3)算出開戰前可做幾個準備;`run_battle(..., prep_budget=)` 在**第一個交戰回合之前**跑 `_prep_phase`(施增益/召喚/喝藥/塗毒)。**召喚在備戰預載進 `battle["allies"]`** → 開場即在場、不佔首回合(解召喚痛點)。鐵律守住:prep 在 while 迴圈前 → `opening` 偷襲先機保留;buff/summon_turns 從第一回合照 tick(不延長時效、只省一動);同法術每場備戰不可重施;`active_effects` 戰後由 run_battle 出口 clear(prep 在 run_battle 內 → 無撤退洩漏);召喚鎖 `PREP_SUMMON_MIN_SCOUT=50`。已接 offer_battle + 合約暗殺 + 潛殺平民三處 got_drop 路徑;**地城/Boss 直呼 run_battle(prep_budget 預設 0)刻意不給備戰**(無從偵查一頭撞見的敵人)。調整只動 `formulas.PREP_*` 常數。
### R09 · 運動 athletics 雙用途

- **運動 athletics**:`world.travel` 依 `athletics_travel_factor` 縮短耗時並練運動;`combat.player_attack_cost/player_block_cost` 依 `fatigue_cost_factor` 折扣體力。`格擋` 實扣 `BLOCK_FATIGUE_COST`(別再當死常數)。
### R10 · 施法體力(三系對稱) [re-sim]

- **施法體力(三系對稱)**:`magic.cast` **玩家專用**(敵人/召喚走 `combat.resolve_attack` 不經此);扣魔力後**先擷取體力比例再扣 `spell_fatigue_cost`**(本擊不自我削弱),`_power` 乘 `formulas.cast_fatigue_power_factor`(力竭 ×0.75;**summon HP 也要乘**,審查踩過漏接)。0 體力不 fizzle、夾 0。`spell_fatigue_cost` = 底耗+魔耗線性,由 `fatigue_cost_factor(運動)` 與**法袍套裝** `inventory.cast_fatigue_factor` 折扣;**只折體力不折魔力**(`effective_cost` 不動)。調平衡只動 `formulas.CAST_FATIGUE_*` 或 `armor_sets.json` 的 `cast_fatigue_factor`。**改任何施法/體力數值務必重跑 `sim_assassin.py`**(雖玩家施法不碰 sneak/武傷,仍守紅線)。
**世界 · 難度 · 生態(R11–R14)**

### R11 · 敵人 / 難度(不做數值縮放)

- **敵人/難度(內容驅動,不做數值縮放)**:難度靠 `min_level` 解鎖更強物種 + 地點 `danger`,**不** scale 怪物數值(刻意,避免 Oblivion 詬病)。bestiary 加 `"solo": true` 的 BOSS 在 `random_encounter_group` 會收斂成單獨一隻;地城 `boss` 加 `"raw": true` 則以原始強度登場(`action_dungeon` 不再 `spawn_boss` ×1.6)。新敵人/地城純改 JSON。
### R12 · 生態遭遇表 / biome

- **生態遭遇表 / biome(細化省分)**:每個 `world` 地點有 `biome`(heartland/snow/ashland/swamp);bestiary 怪可帶 `biomes`(子集)。`combat.random_encounter(_group)` 依當地 biome 用 `_biome_weight` 加權:在地怪 ×`BIOME_MATCH_WEIGHT`(3.0)、他鄉怪 ×`BIOME_MISMATCH_WEIGHT`(0.25)、**無 `biomes` 標籤=通用墊底池(四海皆有,確保池不空)**。`world.travel`/`main.action_explore` 已傳 biome。**新怪要分流就加 `biomes`、新地點要加 `biome`**;調生態強度只動那兩個常數。⚠️ 同一 biome 的「在地低階怪」danger 要與其他 biome 對齊(snow 曾因低階怪全 d3 而早期偏硬,已靠把 d2 的 frostbite_spider 併入 snow 緩解;雪原仍刻意略硬)。
### R13 · 省份維度

- **省份維度(細化省分)**:`events.json` 事件可加 `trigger.provinces` 做在地風味/在地遭遇(combat 效果指定該省怪);`quests.json` 的 board 委託可加 `provinces` 做在地懸賞(`quests.available_quests(...,province=)` 過濾、`main.action_board` 傳當地省;無 `provinces`=全圖通用)。NPC 委託走 `npcs.json` 的 `quest` + `dialogue.offered_quest`(`source:"npc"`,不進告示板/公會)。**加省份風味純改 JSON**。
### R14 · 元素抗性

- **元素**:`fire/frost/shock` 受 `magic` 總抗性疊加;`poison`/`disease` 不受 `magic` 影響(見 `formulas.MAGIC_ELEMENTS`)。
**裝備 · 公會 · 戰場(R15–R17)**

### R15 · 裝備加成 / 附魔載體 / synth [recompute] [re-sim]

- **裝備加成(穿戴附魔/套裝)**:`skill()/attr()` 已疊加 `equip_*_bonus`,但**成長/夾限務必用 `base_skill()/base_attr()`**(progression 已改;否則飾品加成會被寫進 base 永久殘留)。
  任何改 `char.equipped`(穿/卸/戴/丟/賣)後都要 `stats.recompute_max_resources(char, gamedata)`(其開頭會跑 `recompute_equipment`)。飾品在 `ring1/ring2/amulet` 槽,卸下要用 `_equipped_slot_of` 找真實槽(別用 `d["slot"]`)。
  附魔載體:護甲=`encha`(res→`armor_fortify` 資源 / skill→`fortify_skill` / resist→`resist_element`;**res 務必保留 `armor_fortify` 鍵**否則漏出 `armor_fortify_totals`)、飾品=`enchj` 四型別;武器元素=`enchw`、武器命中狀態=`enchws`(`combat.resolve_attack` 傷害結算後的 `weapon_status` hook、**玩家專屬**)。**`synth` id 改格式務必保段數向後相容**(encha 4↔5 段、enchw/enchws 5 段不動)。**武器麻痺 solo boss 免疫是硬性反鎖王紅線**(`_is_solo` gate,改 proc/turns/免疫務必重跑 sim + 400 擊 boss 免疫測)。調附魔平衡:`formulas.WEAPON_VAMPIRIC_FRACTION`/`WEAPON_PARALYZE_PROC`、`enchanting.armor_magnitude`/`jewelry_magnitude` factor。新套裝/飾品/法杖純改 JSON(`armor_sets.json` / `items.json` / `weapons.json`)。
- 🔴 **`enchws` 命中效果擴充 + 充能(附魔深化 Phase 1)**:status 除 vampiric/regen/paralyze 外新增 **DoT** `burn`/`chill`/`jolt`(掛 `{kind:dot,element}` 經 `magic.tick_effects` 吃抗性 + rider:chill→weaken、jolt→扣魔+stagger)、**吸取** `absorb_health`/`magicka`/`fatigue`(回攻擊者資源;health 對 solo boss `×WEAPON_ABSORB_SOLO_FACTOR` 夾,防回血泵)、**命中擒魂** `soul_trap`(掛 soul_trap 效果,擊殺由既有 `soul_gem_for` 發石)。新 status 數值在 `enchanting.weapon_status_magnitude`、`combat` 命中迴圈分派、`synth._weapon_status_enchant`(DoT 補 element)。**充能型 `soul_trap`/`paralyze`**:id 的 `mag` 欄=**電池容量**(`soul×CHARGE_PER_SOUL×(0.6+祕術/100)`),現有充能存**新欄 `char.enchant_charges{item_id:int}`**(R03:`default_factory=dict`+to_dict;舊檔=空、legacy paralyze `mag=0` 視無限);命中觸發成功扣一格、歸零不再觸發,`action_recharge_enchant` 以魂石回充(`+soul×CHARGE_PER_SOUL` 夾容量)。**改 enchws/充能/DoT/absorb 常數必跑 `sim_assassin` + 400 擊 boss 免疫**(已驗 solo 0% 秒殺、麻痺 solo 免疫不動)。
- 🔴 **靈魂石經濟:空魂石填充 + 大/黑靈魂石(附魔深化 Phase 2)**:擒魂改「擊殺→填手上**空魂石**」(`magic.resolve_soul_capture`,取代直給;`main` victory 呼叫)。`SOUL_GEM_BY_DANGER` 補 `5:grand`、`soul_gem_for` 夾改 `min(5)`。一般怪填**夠裝該階的最小空魂石**→`filled_<靈魂階>`,無則逸散(命中擒魂因此非無限)。**人形/有靈**(`bestiary "sentient":true`,33 隻)凡魂石裝不下 → 需**空黑魂石 + 法術擒魂**(`soul_trap` 效果無 `src:"weapon"`)才囚成 `filled_black`(soul5)並 `+BLACK_SOUL_INFAMY` → **縛魂術對上魂/大靈魂/黑魂/AoE 不可取代**。空魂石由 `world.merchant_catalog` 在**法師城**自動上架(大城另供空大/黑);新物品純改 `items.json`(empty/filled grand/black,kind `soul_gem_empty`/`soul_gem`);零存檔欄。soul5 進附魔威力頂點 → 改魂階/附魔常數必跑 `sim_assassin`(已驗紅線)。
- 🔴 **可調吸血 + berserk(公會神器引入)**:吸血比例可由武器 `enchant.magnitude`(%)覆寫(`formulas.vampiric_fraction`,缺省 `WEAPON_VAMPIRIC_FRACTION` 30%;悲傷之刃 50)。新武器附魔 kind `berserk`(`formulas.berserk_factor`:依攻方**已損生命**比例提傷、封頂 magnitude%;**滿血=×1 → 開場偷襲不放大**、乘在物理 dmg 於 solo 偷襲/衝鋒夾限**之前** → solo 仍受夾;維蘇拉德 magnitude30)。**改 berserk/vampiric 必跑 `sim_assassin`**(已驗 solo boss 0% 秒殺、群戰反制不退化)。
### R16 · 公會(深度化)

- **公會(深度化)**:入會/晉升規則全在 `systems/factions.py`(`join_block_reason`/`advance_block_reason`/perk),資料在 `factions.json`(`gate_skills`/`join_skill`/`rank_skill_req`/`rivals`/`lawful`/`perk`)——**加門檻/福利/對立純改 JSON**。
  晉升技能門檻由 `quests.available_quests`(guild)強制;perk 接在 `world.sell_price` + `action_repair`/`action_spell_vendor`。**分支任務**:頂層放 `branches`(各含自足的 `stages`+`reward`,**勿**再放頂層 objective/stages,否則 `_stages` 會誤取),`char.quests[qid]["branch"]` 存選擇、`_advance` 推進階段時務必**保留 branch**。
- 🔴 **掌門專屬神器(6 持久公會,使用者拍板)**:登頂(完成壓軸晉升任務)必得該會招牌神器 —— 戰士 `valor_blade`(百戰勳刃·regen)/法師 `staff_of_magnus`(馬格努斯之杖·shock26)/盜賊 `skeleton_key`(骷髏鑰匙·完美開鎖)/黑兄 `blade_of_woe`(悲傷之刃·吸血50)/九神 `crusaders_ward`(十字軍聖盾·抗魔30)/戰友團 `wuuthrad`(維蘇拉德·berserk)。神話黎明**排除**(末世密教,獎勵走 md7 達貢之力)。**授予=純改該壓軸 quest 的兩條 branch `reward.items`(必兩 branch 都加,否則某路線拿不到)+ 物品 JSON**;`test_guildmaster_artifacts` 守。骷髏鑰匙=`skeleton_key:true` 旗標(`dungeon.has_skeleton_key` 掃 equipped)→ 撬鎖必成、不耗開鎖器、**刻意不給 security xp**(防免費刷)。
### R17 · AoE / 狀態(獨立 dict)

- **AoE/狀態**:每個敵人各自 `make_status_effect(...)` 取**獨立 dict**(切勿共用同一個 → 會別名汙染計時)。
**開局 · 狀態機 · 里程碑(R18–R21)**

### R18 · 開局背景 origins

- **開局背景(不一樣的人生)**:全在 `creation.apply_origin`(在標準 `build_character` 末段、`base_max_health`/`recompute` **之前**呼叫,故穿上的裝備 fortify 能被收尾 recompute 吃到),資料在 `origins.json`——**加開局純改 JSON**。
  守則:**只覆寫處境(地點/金幣/物品/裝備/法術/會籍/賞金/同伴),不動屬性/技能**(否則破壞 learn-by-doing,有回歸測試擋);授會籍請挑無 rivals/非 lawful 的公會(或自行確保與賞金/對立自洽);**別讓開局起在地城/danger≥4 節點**(Lv1 即死,傳奇模式尤甚)。`origin` 欄位只供結算顯示,舊存檔缺它→預設 `""`。`vampire:true` 開局只標記身分,階級/進食日由 `vampirism.update` 首回合初始化。
- **開局起手任務(敘事動機)**:每開局可帶 `quest` 欄(單一 quest id),`apply_origin` 末端**自動接取**(`char.is_player` 閘 → NPC 傭兵不發;冪等防呆)。任務本體在 `quests.json`(`source:"origin"`,2–3 階段)。🔴 **授權邊際鐵律(對齊 `quests._objective_met`)**:`reach` 階段**絕不**指向該開局自身起始地(`char.location_id==loc` 會即時完成)、`collect` **絕不**取起始包既有物(起始武器/`minor_healing_potion`/`wheat`/`blue_mountain_flower`/`lockpick` + 各開局自帶物 → 會即時滿足)、第一階段最和緩、**禁 `clear_dungeon`**(新角不入地城)。`test_origin_quests` 以「建角即未達標」一擊把關。**加開局純改 origins.json;加起手任務純改 quests.json**。
- **創角/出身/任務面板**:`ui.origins_panel`(創角前列各開局起始處境 + 起手任務 + **推薦職業**)、`quest_log`/`_quests_view`(分組 origin/guild/委託 + 階段 ✔▶· 進度)、`character_sheet`/`_sheet_view`(出身列 + 起手任務)皆**雙渲染**;Web 端 `renderOrigins`+`VIEWS` 註冊、`renderQuests`/`renderSheet` 對應強化(`web/static/index.html`)。
- **出身→職業推薦(接上「身分↔本事」;不踩 R18)**:創角順序為 **先選出身 → 再選職業**(`main.create_character`);出身可帶**選用** `classes` 欄(推薦職業 id 清單,純 UI 排序/標★,**不碰屬性/技能**——守 R18)。`main._choose_class(gamedata, origin_id)` 把契合職業標 `★推薦` 並排最前(**不過濾、不強制,自由組合保留**);處境型開局(`newcomer`/`fugitive`/`pilgrim`/`nightborn`/`shipwreck_survivor`)留空 `classes`=適配任何職業。`_quick_character` 也先抽出身、再從其 `classes` 抽職業(無則全隨機),快速開始不再產出身分與本事打架的角色。`_origin_card` 帶 `classes`(映中文名)讓玩家選出身當下即見推薦。**加/改推薦純改 `origins.json` `classes` 欄**(`test_origin_class_recommendations` 釘關鍵主題對應 + 合法 id)。
- **施法者開局武器「追加而非取代」**:`apply_origin` 的出身 `weapon` 對**純施法者**(無任何武器系主修,如法師/治療師——`_equips_origin_weapon` 判定)只**追加進背包、不換手**(保留依技能配發的起始武器,免得被塞用不上的近戰武器);**施法武器**(法杖,`_is_caster_weapon`:archetype=staff 或武器 skill 屬魔法學派)及**有武器主修的混合職**(戰法師 blade/blunt、戰士/盜賊/弓手…)仍照常換上出身武器升級。🔴 判定靠 `major_skills` 是否含武器技能,**勿**用 `spec=="magic"` 代理(會誤殺戰法師)。`test_caster_origin_weapon_not_force_equipped` 釘純施法者 vs 混合職兩側行為。
### R19 · 吸血鬼化 [migrate] [recompute]

- **吸血鬼化(里程碑)**:狀態機全在 `systems/vampirism.py`,**`vampirism.update(state, gd)` 必須在 game_loop 每圈頂端先呼叫**(驅動轉化/升階/初始化);階級加成走 `vampire_*` 獨立層(**成長/夾限只用 `base_skill()/base_attr()`**,同裝備鐵律);`apply_to_character` 末段會 `recompute_max_resources`(力量/意志加成→體力上限)。
  感染向量:吸血鬼敵人 `attack.infect`(機率)→ `combat.resolve_attack` 回 `infected` → `run_battle` 套 `vampirism.infect`;**疾病抗性削弱感染**(`resist_multiplier(...,"disease")`)。陽光只在 travel/explore 結算(`_maybe_sunburn`,**夾限保命**);`is_shunned`(階級≥2)在 game_loop 隱藏 NPC 商業服務,`action_feed` 解除。**加吸血鬼敵人純改 bestiary**(`infect` + 火焰負抗性);調平衡只動 vampirism.py 常數(`STAGE_*`/`SUN_*`/`FEED_*`)。轉化後**出生星座之力被 `vampiric_drain` 取代**(刻意:詛咒蓋過天賦)。
  **D 治療**:`cure_vampirism` 用 source `vampire_cure`(`available_quests` 只回對應 source → 不漏進告示板/公會);解咒儀式是顯式動作 `action_vampire_cure`(法師公會子選單,`is_vampire` 閘門),用 `vampirism.cure` 收尾並把任務移出 `completed_quests` 以**可重複**;`mages_guild` 服務**不受社交封鎖**(吸血鬼永遠找得到解咒的女巫)。加新解咒媒介純改 quests.json(注意採集物要買得到:大蒜@布魯瑪、毒茄參@晨風)。
### R20 · 斯庫瑪 / 月糖成癮 [re-sim] [migrate]

- **斯庫瑪/月糖成癮(里程碑)**:狀態機全在 `systems/skooma.py`,**`skooma.update(state, gd)` 掛 game_loop 每圈頂端、在 vampirism 之後**(驅動亢奮退去/戒斷/清醒衰減)。亢奮/戒斷走 `skooma_*` 獨立層(**成長/夾限只用 `base_*`**,同裝備鐵律);`apply_to_character` 末段 `recompute_max_resources`。🔴 **紅線**:亢奮**只給速度/敏捷/意志 + 資源回復、絕不碰 strength/sneak/武傷**(`attack_damage` 吃 strength → 碰了會放大偷襲、破 `SOLO_SNEAK_DAMAGE_CAP`;改 `SKOOMA_HIGH_ATTR` 務必重跑 `sim_assassin.py` + 確認亢奮前後 `estimate_sneak_damage` 不變,有 `test_skooma` 守門)。戒斷強度**由成癮深度推導、非距上次用藥**(避免與 ride-it-out 衰減 ratchet 互相打架而振盪)。狀態走 Character 5 欄(持久、進存檔),**絕不寄生 `active_effects`**(後者不入檔、入戰即清 → 亢奮會蒸發)。`skooma.ensure_skooma_fields` 接 `state.from_dict`(載入重算層)。**解癮**:`quest_skooma_cure`(source `skooma_cure`,只經 `action_skooma_cure` 廣場動作賺取/施行,不掛任何 NPC.quest);⚠️ **自然戒除(清醒衰減)時 `skooma.update` 會 `_discard_cure_quest` 棄置殘留任務**(否則完成採集卻不行儀式 → 衰減戒掉 → 日後再成癮免費解癮,審查抓到的漏洞)。調平衡只動 skooma.py 常數(`*_HIGH_*`/`TOLERANCE_FACTOR`/`WITHDRAWAL_*`/`CLEAN_DECAY_DAYS`)。**月糖同時是煉金材料**(ingredients.json,煉金照讀其 effects)、斯庫瑪 `kind:"drug"`(items.json,走 dose 路徑不走 use_item potion 分支)。
### R21 · 技能里程碑 Mastery [re-sim] [migrate]

- **技能里程碑(Skill Mastery,P1)**:全在 `systems/mastery.py`,資料在 `data/mastery.json`。門檻**只認 `base_skill()`**(裝備/吸血鬼疊加不得觸發,否則污染成長/夾限)。**加同 kind 里程碑純改 JSON;加新 kind 必須**:①登錄 `mastery._IMPLEMENTED_KINDS`(否則該條完全 inert,不顯示/計分/播報)②加對應 getter ③一處呼叫端分支(**這步不是純 JSON**,別在 doc 誇大)。⚠️ 兩個審查踩過的雷:① 走 `active_effects` 的效果(如溢盾)務必**夾「總量」cap 並打 `source` 標記**(別只夾單次→可疊破),且 `run_battle` 已在**入場清 `player.active_effects`**(在 `_prep_phase` 前)杜絕戰外殘留洩漏;② 戰鬥數值型(壁壘/過載)改常數務必重跑 `sim_assassin.py` + auto_resolve 勝率 gate(**過門檻勝率不得下降**)。新欄位只有 `persuaded_npcs`(辯舌·折服;已進 to_dict、舊存檔預設 [])。

**流程慣例(R22)**

### R22 · 提交慣例 — 驗證綠 → 自動 commit & push 到 main

- **提交慣例**:每個里程碑走完五階段(評估 → 決定方向 → 實作 → 驗證 → 文件)後,**驗證全綠即自動 `git commit` & `git push origin main`,不需使用者明說**(刻意覆寫 Claude Code「只在使用者明說才提交」的預設;本專案 git 歷史一律直推 `main`、SSH 已認證)。紅燈(任一驗證未過)則**不**提交、先修。commit 訊息用繁中描述本里程碑、末加 `Co-Authored-By:` 行;一次一里程碑 = 一個 commit。

**對話 / NPC 外交(R23)**

### R23 · 條件式對話樹 + 外交立場軸 [save]

- **對話樹**:全在 `systems/dialogue.py`,內容在 `data/dialogue.json`(greetings/attitude_topics/topics/roles/npcs)。**加 NPC 對話純改 JSON**:問候依 `attitude()` 分級(vampire_seen>hostile>cold>friendly>neutral)、話題依 `requires` gate。NPC 陣營/關係由 `politics.city_bloc/relationship(NPC 的 location)` 推導(npcs.json 可選 `faction` 覆寫)。**hostile = 拒談**:`topics_for` 在 hostile 直接回 `[]`(連 extra/deep 一併收窄,只剩 persuade/bribe 回暖;quest 亦由 `att != "hostile"` 擋)。
- **條件引擎共用**:`events.meets` 是唯一條件評估器。**無 state 的新鍵**(allegiance/min_fame/min_infamy/is_member/member_rank_min/faction_standing_min/is_vampire/is_werewolf)直接加進 `meets`(只在 req 出現時判定 → 對既有 events.json 零回歸);**需 state/ctx 的鍵**(min_disposition/npc_relationship/vampire_shunned/bounty_min/partisan + `@npc` 解析)走 `dialogue.meets_dialogue` 包裝,**`events.meets` 簽名不可動**。
- 🔴 **反刷分鐵律(對抗審查踩過的 critical)**:**任何帶持久 effect(faction_standing/fame/item/gold)的話題,`data` 必標 `"once": true`** → `resolve_topic` 經 `char.dialogue_done[npc_id]` 去重(套一次後只敘事、不再套 effects)、`topics_for` 隱藏已表態者。否則對話 while 迴圈可零成本無限重選 → 刷爆 fame/立場。純敘事話題(無持久 effect)才可重複。**套話 `pry` 只給情報 + 練口才(付 practice),不碰外交軸**。
- **外交立場軸 `faction_standing`**(Character 欄,cause→分 [-100,100]):`faction_standing` effect 升該大義、`rival_penalty` 連帶降其餘大義(互斥真權衡);`@npc` 解成該 NPC 的 `city_bloc` 大義(neutral 城不在 `politics.CAUSES` → `partisan` 不過、effect 靜默 no-op)。**表態(pledge/結交)一次性**,climb 須跨城逐人(每次得罪對立方)。
- **存檔**:`faction_standing`/`dialogue_done` 走 dataclass 預設 `{}` + `to_dict` + `from_dict cls(**d)`,**無需 ensure_**(舊存檔自動補空)。dialogue.json 唯讀不入檔。**不破** `test_speechcraft`(persuade/bribe/talk_down/intimidate 既有函式零改動)。

**AI 陣營自走戰爭(R24)**

### R24 · AI 戰爭引擎 aiwar [re-sim] [save]

- **引擎**全在 `systems/aiwar.py`,**`aiwar.update(state, gd)` 掛 game_loop 每圈頂端、在 `worldstate.update` 之後、`warband`/`politics.tick_tax` 之前**(玩家城被圍削守軍須在 tick_tax 結算失守**之前** → 順序不可調)。每 `WAR_HOURS` 一輪、`while` 補結多週。
- 🔴 **決定性**:全程 `state.rng` + 一切「會餵 rng 的」迭代 `sorted`(攻方序走固定 `AGGRESSOR_ORDER`);未排序的 set/dict 迭代**只可餵順序無關聚合**(garrison 求和、集合聯集),**絕不可讓迭代序流到 `rng` 消耗**。改任何選城/結算邏輯後跑同 seed 重播驗一致。
- 🔴 **玩家城紅線**:非玩家城易主只寫 `char.world_faction`;**玩家城(city_faction)絕不寫 world_faction**,只 `deplete_garrison` + 標 `city_threat`,失守靠既有 `tick_tax` revolt 浮回 → 持有期由 faction_of 三層優先序**自動免疫**(`test_player_held_city_immune_to_flip`)。`city_threat` 失守/易主後每輪 prune(防殘留膨脹)。
- 🔴 **改 aiwar.py 任何平衡常數 → 必跑 `sim_worldwar.py`**(check.sh 偵測 aiwar/worldstate/politics 變更〔含未追蹤檔〕自動跑)。守:不雪球一統(<70%,**務必含「玩家選邊」情境** —— 審查踩過 sim 只測 baseline 漏掉選邊 89% 一統)、≥3 陣營存活、中立 `NEUTRAL_FLOOR` 緩衝、反攻 feels-bad(失守 ≥3 週且 `reinforce` 守得住)、選邊有感、決定性。**霸權煞車(damp + 守方 vuln)須在外交天平之後套用**,否則選邊蓋過煞車 → 雪球。
- **複用 + 紅線**:複用 `politics.faction_of/garrison_of/deplete_garrison/base_garrison/tick_tax` 與常數;**不改 politics.py 行為、不碰 bestiary 怪數值(R11)**。相鄰由 `world.json` links BFS 推導。**加陣營/改平衡改 aiwar.py 常數;加城純改 rulers.json**。存檔 `war_tick_at`/`city_threat` 走 dataclass 預設 + `ensure_war_fields`,向後相容。
- 🔴 **神話黎明非世界大戰陣營(已移除)**:aiwar 侵略方僅 `imperial`/`independent`(`AGGRESSOR_ORDER` 兩陣營)。daedric 曾為第三陣營(`_daedric_resurgence`/`DAEDRIC_FLOOR` 韌性層 + 危機期城池易幟 daedric),經使用者拍板**整個移除** —— 神話黎明=末世密教,概念上不該與帝國/獨立/自立並列爭王座;危機改純由湮滅之門地城 + 主線弧 + 新聞呈現,daedric 不在 aiwar 佔城。`test_aggressors_only_imperial_independent` 守(詳見 R26)。

### R25 · 房產 & 坐騎 housing/mounts [re-sim] [recompute] [save]

- **房產**全在 `systems/housing.py` + `data/houses.json`(key=location_id)。倉庫 `house_stash` 存物**不計隨身負重**(靠 `inventory.total_weight` 只迭代 `inventory` 而天生豁免;**勿**把 stash 計入)。**存入倉庫禁正穿戴/手持裝備**(`is_equipped` 擋 → 免漏 `recompute_max_resources`,守 R05);取出以 `inventory.can_carry`(含鞍袋)為閘、毀損 id 走 `item_or_none` 不崩。
- **精神飽滿**:`well_rested_until`(權威·絕對小時)+ `well_rested`(快取布林,**game_loop 頂端 `housing.refresh_well_rested` 刷新**,同 beast_form 模式);`progression.use_skill` 讀快取乘 `formulas.WELL_RESTED_XP_MULT`。**只乘 xp、絕不寫 base 技能/屬性/上限**。再休息=刷新不疊加。
- **坐騎**全在 `systems/mounts.py` + `data/mounts.json`(三類 warhorse/courser/magesteed + `stable_cities` + `spear_stock`)。共享被動:旅行加速(`world.travel` 的 `travel_factor` 第四減項,**夾 floor 0.5 不變**)、**鞍袋負重**(`inventory.max_weight(char, gamedata)` 加一層 —— **負重上限即時算、非資源、不進 `recompute_max_resources`、不寫 base**;`max_weight` 的 `gamedata` 預設 None 維持 test_world 相容)、獵馬規避遭遇(`encounter_chance` 乘 `1-encounter_evade`)。
- 🔴 **坐騎戰技紅線(動 combat/formulas/施法/archetype → 必跑 `sim_assassin.py`)**:衝鋒**絕不走 `sneak_mult`**(`resolve_attack(mounted_charge=True)` 不設 sneaking;驗收衝鋒首擊 `["sneak"] is None`),對 solo boss 受**獨立** `formulas.MOUNTED_CHARGE_DAMAGE_CAP_RATIO` 夾(鏡像偷襲夾、非同一分支)→ 長槍×高倍率開場一擊不秒王(sim 證 0%)。長槍 `archetype="spear"` 刻意**不**在 `_ARCHETYPE_SNEAK_BONUS`/`_ARCHETYPE_ARMOR_PEN` 登錄 → 落回安全預設(零偷襲加成)。
- **戰技/法駒法術增益僅野外騎乘語境生效**:`mounted` 旗只由 `action_explore`/`_travel_to` 經 `offer_battle`→`run_battle` 傳 True(地城/朝堂/攻城直呼 `run_battle` → False=自動下馬);戰技另以 `active_mount` 類別 + 武器流派 + **僅第一回合**為閘(`mounts.can_charge`/`can_skirmish_ride`)。法駒法傷接 `magic.cast(mounted=)` 乘 `power`(僅騎乘戰、守 R10/R14/麻痺 solo 免疫);騎射閃避走**聚合層**(`evasion += _ride_evasion`,不遮蔽 acrobatics/mastery)。
- **長槍可鍛可買**:馬廄(`gamedata.has_stable`)售 `spear_stock` + 三類坐騎;鍛造走 recipes.json(守反套利 `test_smithing`:Σ原料價值 ≥ 產出價值)。新存檔 6 欄(`houses_owned`/`house_stash`/`well_rested_until`/`well_rested`/`mounts_owned`/`active_mount`)全 dataclass 預設 + 進 `to_dict`,**無需 ensure_***。**加房產純改 houses.json;加坐騎/長槍純改 mounts.json+weapons.json+recipes.json。Web 走共用 game loop 文字 fallback(原生面板可後補)。**

### R26 · 湮滅危機主線弧 + 達貢之力 + 戰爭時間軸 [re-sim] [recompute] [save]

- **後期主線(湮滅危機 — 梅魯尼斯·達貢)**:全遊戲第一條主線,**雙路線由陣營身分分流,兩路最後都擊敗達貢**。
  - **任務機制**(`quests.py`,皆通用向後相容):`source:"main"` + `requires_event`(`available_quests` gate,主線需 `kvatch_falls`)+ `requires_faction`(+`_rank`,教徒頂點 `md7` 需 `mythic_dawn` 滿階 6)+ `requires_quest`(任務鏈);`accept_quest` 的 `expel_faction`(接正道 `main_oblivion` → 神話黎明 rank=-1 叛離,`conjure_boon` perk 隨之消失);`_complete` reward 擴充 `grant_boon`/`world_flags`/`eradicate_faction`/`infamy`(`fame` 夾 ≥0)。主線在 `action_board` 露出(`【主線】`標)。
  - **雙結局互斥(零新事件機制)**:正道清 `the_deadlands` 殺**滿血** `mehrunes_dagon` → world_event `dagon_banished`(`kills` milestone);教徒清 `dawn_sanctum` 殺**削弱** `mehrunes_dagon_diminished` → `dawn_undone`。兩個 bestiary 條目(守 R11 不縮放)+ `kills` milestone 完美區分。**🔴 雙結局都 `eradicate_faction:"mythic_dawn"`(神話黎明大義必滅)+ `mythic_dawn_eradicated` 旗標 → `factions.join_block_reason` 擋再入會**。
  - **教徒終局「雙方削弱」**:`dawn_sanctum` 末層 boss 前,`main.py:action_dungeon` 偵測 `loc["dungeon"]=="dawn_sanctum"` → 抽乾玩家 health(夾≥1)/magicka/fatigue 至三分(逆轉法陣反噬)。
- **達貢之力(永久增益層)`systems/dagon_boon.py`**:照吸血鬼/狼人模式的**獨立疊加層**(`dagon_attr_bonus/dagon_skill_bonus/dagon_resist/dagon_magic_bonus` + `dagon_boon` flag)。聚合於 `Character.attr()/skill()`、`magic.entity_resist()`、`stats.recompute_max_resources`(魔力);**絕不寫回 base**(R05 同律)。`state.from_dict` 掛 `ensure_dagon_fields` 遷移。`md7` 完成 `grant()`。校準 +42 屬性/+18 技能/火抗60/魔力25(吸血T3~狼人之間),**刻意不碰 sneak/武傷倍率**(守 R20 精神)→ **加永久屬性層必跑 `sim_assassin`**(已驗 solo 夾限仍 0%)。
- 🔴 **獨立戰爭=湮滅危機後第二幕(時間軸因果)**:`aiwar.update` 與分裂世界事件(`septim_line_ends`/`argonian_accession`/`nord_stirrings`)**全 gate 在 `oblivion_crisis_ended`**(危機未平 → 內戰按兵不動、`war_tick_at` 隨危機結束才起算)。`sim_worldwar`/`test_aiwar` 的 `_mk`/`_state` 已補 `oblivion_crisis_ended` 前提;`test_worldstate` 分裂鏈測試改 gate 在危機。**改 aiwar 必跑 `sim_worldwar`**(R24 不退化)。
- 🔴 **神話黎明非政治大義(已移除 daedric 大義/陣營,使用者拍板)**:`daedric` 曾兼任「可宣誓大義」(`politics.CAUSES`/`pledgeable_causes`/`EXPANSIONIST_CAUSES`)與 aiwar 第三陣營(危機期 kvatch/bravil/leyawiin 易幟 daedric + `_daedric_resurgence` 韌性)。**整個移除**:神話黎明=末世密教,與帝國/獨立/自立的王座之爭**正交** —— 只走**公會入會(阿留斯湖招募)+ 主線弧 + 危機新聞**,玩家**不可宣誓**、城池**不易幟**、aiwar **不佔城**。`world_events` 的 `kvatch_falls`/`deadlands_breach` 去 `faction_flip→daedric`(保留 news + 觸發旗標 → 地城可見/招募/主線照常);`EXPANSIONIST_CAUSES={"own"}`、`AGGRESSOR_ORDER=["imperial","independent"]`。守:`test_daedric_not_a_pledgeable_cause`、`test_aggressors_only_imperial_independent`、`test_daedric_unlock_after_kvatch`(改為「永不可宣誓」)。**改政治大義/aiwar 必跑 `sim_worldwar`**(已驗收斂不破、選邊有感)。
- 新內容純 JSON:5 座 danger5-6 地城(`the_deadlands` 4 層最深)、達貢 2 變體、5 世界事件、**賽羅迪爾補正史九城**(+Bravil/Chorrol/Leyawiin + 3 領主)。回歸見 `test_oblivion.py`。
  - 🔴 **結局神器分流(使用者拍板,各結局獨佔;`test_ending_artifact_split` 守)**:**正道**=`crusaders_aegis`(十字軍護心·火抗50)+ `dawnfang`(黎明之牙·火劍 —— 接 `main_oblivion` reward + `the_deadlands` 寶藏 + `mehrunes_dagon` bestiary 0.5,完整繼承原 razor 的三處槽位);**教徒**=`mysterium_xarxes`(魔典·強化咒術)+ `mehrunes_razor`(魔銳茲之刃·電匕 —— 接 `md7` reward + `dawn_sanctum` 寶藏,沿 mysterium 慣例**不入 bestiary**)+ 達貢之力永久層。`sigil_stone_fragment` 走前三道門寶藏。✅ `mehrunes_razor` 已從 `dragon_lair`(龍喉巢穴)首領寶藏移除 → 換上**專屬龍系神器 `skyburner`(焚天劍·龍骨火劍·傷23/火26/value2000)**,單一來源(僅龍巢首領寶藏、**不入 bestiary → 不可刷、全遊戲唯一**;龍巢無 `until_event` gate 可重入,故神器只放首殺保底的 boss.treasure);razor 現純教徒結局獨佔。神器數 4→5。`test_dragon_lair_unique_trophy` 守。
- 🔴 **湮滅之門逐門可見性**:5 地城帶 `visible` 欄(`world.is_visible` 對 `world_events_fired`/`cleared_dungeons`/`factions` 做 AND);開局全隱、`kvatch_falls` 開第一道、清掉就閉、下一道開、`oblivion_crisis_ended` 全消;dawn_sanctum=`after_faction mythic_dawn`。過濾於 `travel_options`/`_location_view` 出口/`_map_view`(grid/edges/計數);所在地變不可見 → game_loop 頂端 `world.relocate_target`(BFS 最近可見城)拋回。改 `visible` 改 `geo_rebuild.py` 的 VISIBLE。
- 🔴 **神話黎明=遭遇式招募(改回史實)**:服務從 kvatch 移到 **`dawn_sanctum` 神殿**(入會後 `after_faction` 才可見可達);招募點=新野區 **`lake_arrius_caverns` 阿留斯湖洞窟**(切迪納東北)——在當地 `action_explore`(`kvatch_falls` 後、非會員、可入會)有 50% 遇 **2× `mythic_dawn_acolyte`(赤袍信徒,輕量招募者 danger3/HP50/dmg13)**,走 `offer_battle(recruit="mythic_dawn")`:口才 `dialogue.recruit_persuade` 成功 → 確認加入(`factions.join`)→ 神殿解鎖;失敗/婉拒 → 開打。🔴 **招募遭遇務必用輕量 `mythic_dawn_acolyte`,不可用終局 `mythic_apostate`(HP140/danger5/min_level99,dawn_sanctum 守衛)** —— kvatch_falls 第 3 天即可觸發,低階新手在 danger-3 湖畔撞 2 隻終局精英=過強(`test_recruitment_uses_lightweight_acolyte` 守)。線索:`kvatch_falls` news + 切迪納祭司 rumor 指向阿留斯湖。**合約大廳 `_contract_hall` 走入式入會改為 opt-in(只在有傳 `join_prompt` 時提供,如九神騎士團於安維爾正面招募);`action_mythic_dawn` 不傳 join_prompt → 對非會員不開門(神殿服務本就 after_faction-gated、非會員無從抵達,此守門為自我文件化+防未來誤把服務接到非 gated 地點)。🔴 勿替神話黎明重引入走入式入會,招募只走阿留斯湖遭遇。**

### R27 · Web-only(終端版已移除)

- **唯一進入點 `python3 -m tesrpg.web`**;`tesrpg/__main__.py`(終端 `python3 -m tesrpg`)已刪。遊戲在背景 thread 跑原本阻塞的 `main()`(`server._run_game`),`ui.use_web_backend()` 注入 `WebBackend` + 錄製用 Console。
- **`tesrpg/ui/console.py` = Web 的渲染/輸入接層**:渲染函式照舊 `console.print(rich)` → 錄進錄製 Console → `export_html` 成 HTML block(尚未原生化的面板退路),或頂端 `if _web: _emit_view(name, _xxx_view()); return` 發原生 view block。**rich 渲染是 web 的 HTML 後端,不可刪**。
- **5 個輸入原語(`menu/grouped_menu/ask_text/ask_int/confirm`)無 `_web` backend 時直接 `raise RuntimeError`**(終端 stdin 分支已移除)。🔴 **不可重新引入終端 stdin / `IntPrompt`/`Prompt` 互動**。測試照舊 monkeypatch `ui.menu`/`ui.confirm`/`ui.message` 自動作答(整個換掉函式,不觸 backend);需端到端則用 `WebBackend` + `make_recording_console()` 自動驅動 `main()`。
- 加新面板:`console.py` 寫 `_xxx_view()` + 函式頂端 guard + `index.html` 加 `renderXxx` 並登錄 `VIEWS`(見 §「Web UI」)。

### R28 · 世界相對座標 + 拓樸再檢查(全境補完後)

- **每個地點必帶 `pos:[col,row]`**(`world["map"]={cols:40,rows:24}`);座標與 `links` **皆依正典上古卷軸地理**(查 UESP/ESO):各省城市相對位置落在地理 bounding box、省內連線=lore 道路鄰接、跨省只經邊境(真實省界)、旅行時數由格距離推導。`pos` 不入存檔。`test_world` 守:pos 全員存在/界內/唯一 + link 空間局部性(對角線 55%)。
- **拓樸鐵律(`test_world` 守)**:① 除湮滅之門/終局地城白名單(`dragon_lair/kvatch_gate/bravil_gate/the_deadlands/dawn_sanctum`)外,每點 degree≥2;② **跨省連線只經邊境**(邊境節點=省際接縫,**已無歷史直連豁免**;`kvatch↔dragon_bridge`、`leyawiin↔gideon` 已改走 pale_pass/niben_marsh);③ 每真實省的省內子圖連通;④ 城/鎮 danger=0、荒野 1–5、地城≥1、每省有低危(≤2)入口。重排座標/連線後跑 `sim_worldwar`(改動 city 鄰接影響 AI 戰爭)。
- **加新城/鎮**:world.json `type:city/town`+`danger:0` + rulers.json 一筆(`race∈races`、`garrison>0`、`bloc/bloc_label`、`stance∈{imperial,independent,neutral}`);新 bloc 只是字串(politics 動態讀,免登錄)。**加新地城**:dungeons.json 一筆 + quests.json 一條 `clear_dungeon`/`reach` 委託(`test_polish` 守);board 委託金幣≤`max(320,danger*100)`、聲望≤`max(15,danger*5)`(`test_detailing` 守)。新城改變 AI 戰爭盤面 → **大量加城後跑 `sim_worldwar`**(守 R24)。
- **內容生成工具**:`tools/build_expansion.py`+`expand_world.py`(產/併入新地點四檔);`tools/geo_rebuild.py`(**依 UESP lore 重建全圖 pos+links**:省內 GEO 鄰接表 + BORDER_LINKS 省際接縫〔每 seam 只接真正鄰接的兩省門戶城〕+ NEW_REGIONS 分區野區 + 海爾根 town〔賽→天白隘門戶,連 rulers.json〕 + 距離推導時數;auto-fix **只連同省最近**〔杜絕跨 seam 亂湊〕,重發 world.json 單行條目)。改地理改 GEO/BORDER_LINKS 再跑。
- **邊境地圖呈現(Web)**:`renderMap` **不再有「邊境」獨立按鈕**;行省檢視 = 該省節點 + **邊接該省的邊境節點**(出省口;`draw()` 用 `g.edges` 判 `province==="邊境"` 且邊接本省)。邊境節點仍在總覽圖。
- **相對位置地圖(Web)**:`_map_view` 發 `grid:{cols,rows,nodes:[{id,name,pos,type,here,visited,danger,province,svc,...}],edges:[{a,b,h}]}`(`svc`=特色設施〔公會/陣營〕、通用宿商訓鐵板不列;`edges`=無向去重連線+時數)。`index.html` `renderMap` 依 pos 絕對定位 marker 畫**總覽圖**(north 朝上、★所在、危險度上色、SVG 連線=相鄰路徑),頂端行省鈕**純前端放大**該省 bbox(`drawStage`,放大才標連線時長),**點 marker → `.mapinfo` 顯示該地特色設施**;出口靠連線辨認。**滑鼠滾輪縮放(zoom-to-cursor)+ 拖曳平移**(`.mapzoom` transform;pointer capture 無 window listener 洩漏);放大(scale≥2.2)或行省檢視才顯示地名+路徑時長(CSS `.zoomed/.prov` 控制)。已移除冗長明細列表。`test_web` 守 grid 形狀 + edges 合法。

### R29 · 城鎮服務專精化(訓練師專精 + 法師公會法術學派)[functional>numeric]

- **訓練師依公會/lore 只教部分技能**(不再每城教全 23 技):可教範圍 = ① `data/trainers.json` 的 `"skills"` 覆寫(系 id `combat/magic/stealth` 或顯式技能 id)→ ② 否則由該城公會服務推導系(`systems/world._GUILD_SPEC`:mages→magic、fighters/companions/knights_nine→combat、thieves/dark_brotherhood/mythic_dawn→stealth)→ ③ 皆無→全系(無公會的鎮/特例**安全後備=現行行為**)。再 ∪ 招牌 `"master"` 技。純讀靜態世界資料即時推導,**零存檔欄位**。`action_trainer` 由 `world.trainer_specs/trainer_skills` 動態組選單(單系城直接列技能、免空選單)。
- **宗師指點 `master:{skill,cap}`**:招牌城對其招牌技可破一般 `formulas.TRAINER_CAP=75`(`cap≤SKILL_CAP=100`);76–100 一律靠 learn-by-doing 或宗師,杜絕「就近一站買滿」。`world.trainer_cap(gd,loc,sid)` 取值;宗師技必經 union 上架。**`TRAINER_CAP` 是唯一數值旋鈕**(設 100=純選單過濾零數值變動);不動 combat/cast/economy → **不需 `sim_assassin`**。
- **法師公會法術學派分散**(純改 `world.json` `spell_stock`,`action_spell_vendor` 零改):每省指派**守護學派**(天際=destruction/晨風=conjuration/黑沼澤+高岩=restoration/漢默法爾=alteration/瓦倫森林=illusion/艾爾斯維爾=mysticism;**賽羅迪爾=通才例外**,`imperial_city` 售全 43 法術)。每座 mages_guild 城 stock = **保底集 9 道** ∪ 本省守護學派完整線;進階/AoE/別派鎖在主守省 → 跨省採購。**保底集**=`flames/frostbite/sparks/minor_heal/oakflesh/ward/soul_trap/conjure_familiar/fear`(每派入門一道,保純法師任何省可起步)。
- **守門**(`test_world`):`test_trainer_specialization`(每有 trainer 城 ≥1 可教系且非空、非邊境 city 皆可公會推導、trainers.json id 合法、宗師 cap 越界檢查 + 必上架)、`test_spell_school_dispersal`(6 學派各可買、保底集每道在每座法師城、無空 spell_stock 法師城、spell id 合法、**無孤兒 spell_stock**〔無 mages_guild 不可達〕)。加招牌城/守護學派純改 `trainers.json`/`world.json` 並維持上述不變式。

---

## 4. 開發節奏(ultracode 開著 → 每個功能都這樣做)

> 完整五階段流程(評估 → 決定方向 → 實作 → 驗證 → 文件 + 提交)見 `CLAUDE.md`「開發流程」;以下是「驗證」段的細節。**驗證綠後依 R22 自動 `commit` & `push origin main`。**

1. **實作**(資料 + systems + main/ui)。
2. **單元測試**:新增 `tests/test_*.py`(用 `assert`,可直接 `python3` 跑;登錄進 `tests/run_all.py`)。
3. **平衡模擬**:Bash 一行式跑 `combat.auto_resolve` / 手寫迴圈,印勝率/回合數。
4. **無頭煙霧測試**:用 `WebBackend` + `make_recording_console()` 自動作答驅動 `main()`(或直接 patch `ui.menu`/`Console(file=StringIO())`),實跑建角/`run_battle`/action,抓 traceback。
5. **對抗式審查(Workflow 工具)**:多維度 fan-out 審查 → 每個發現由獨立懷疑者**對抗式驗證** → 只回報「能真實重現」的 bug。
6. **覆核 + 修正**:**逐一覆核審查結果**(會有誤報、也會有「會引入新 bug 的錯誤修法」—— 已擋下 2 次);套用確認的修正 + 補回歸測試;重跑全套。

> 戰績:二十二輪審查累計修掉 **~37 個真 bug**(含同伴角色化的 orphan 羈絆破口/護盾消散訊息洪流/招牌獎勵靜默;隱遁里程碑化的單一 perk 播報措辭誤導;補階梯 pass 的 armorer repair_floor 死 perk×2 + 自驗閃避三源 trivialize 群戰加夾限;**使用者點出偵查 recon 里程碑死 perk → 重設為情報→戰力**)、擋下 **2 個錯誤修法**、自補 1 次審查覆蓋缺口、自抓數個測試基建坑。
> 陣營 Phase C-lite 輪:4 維×3 視角,16 發現→0 真 bug(全為正向驗證:紅線/三層/決定性/存檔/玩家免疫/失城浮回皆確認正確)。Phase A/B 因 agent 額度上限以自審代審查(純資料/加性低風險),C-lite 額度恢復後補跑完整對抗審查、零真 bug。
> 城戰階段三輪:6 維 fan-out × 每發現 3 視角驗證,19 發現→1 確認(18 駁回多為正向確認/既定設計)。唯一確認=**既有** robustness 缺口(`legacy.compute` 取 `factions[fid]` 未防缺 id → 毀損存檔結算 KeyError),順手以 `.get` 修 + 回歸測試。評估階段的對抗審查更**預先攔下**設計級紅線(稅基誤用 `held_cities` 會白送 2190+/週)→ 落地即正確。
> 城戰階段四輪(規劃走 plan-mode:Explore×2 調查 → Plan agent 設計 → 核定):5 維 fan-out × 3 視角,**2 發現→0 真 bug**(皆既定設計/正向確認)—— 一次過,印證「先規劃 + 守鐵律」能把缺陷擋在落地前。
> 招兵買馬階段二輪:7 維 fan-out × 每發現 3 視角對抗驗證,13 發現→4 確認;逐一覆核後**判 3 個為誤報**(遣散洗寬限=無此入口且經濟自殺、apply 不重置週期=下一圈已收斂、存讀檔暴扣=遊戲時間凍結於存檔)、**只修 1 個真 bug**(apply_casualties 回報實際扣減而非陣亡計數)+ 補回歸防線。教訓:對抗驗證者可能以「直接改記憶體狀態」重現出非遊戲路徑的偽漏洞 → 覆核務必確認**重現走的是真實遊戲入口**。
> Mastery 輪:對抗審查抓到**自身引入的 3 問題**(溢盾 cap 可疊破到 2.06×血上限 / `active_effects` 戰外洩漏進下一場 / `kind` 白名單沉默失效)+ 順手抓到**既有飾品實戰崩潰**(戴飾品被物理擊 `KeyError`,已補回歸測試)。
> M14 輪:抓到會**寫入存檔的數值回歸** —— 丟棄/出售「穿戴中的 fortify 護甲」未重算,加成永久殘留(出售還倒賺金幣)。
> M15 輪(升級改版):抓到 3 個 —— ①(major)`ensure_level_xp` 未在**載入路徑**觸發 → 可升級的舊存檔升級入口被隱藏;
> ②(minor)`apply_level_up` 屬性點以「請求量」而非「實際套用量」計帳 → 觸頂吞點;③ 三處 UI 文案仍稱「只有主修計入升級」。均已修 + 補回歸測試(且反向驗證測試能抓到)。
> 重點教訓:**互動式 `run_battle` 測試會全域 patch `ui.menu`,模組間會互相汙染**(test_m13 因此踩雷)—— 需要時在測試內自行重設 `ui.menu`。

---

## 5. 設計定案(DESIGN.md §7)

死亡規則=**兩種模式**(冒險可讀檔 / 傳奇 roguelike 永久死亡);職業=8 預設+自訂;起始省=賽羅迪爾·布魯瑪;
**純沙盒**(無主線);時間以「小時」推進(12 月×30 天);技能=Oblivion 的 21 套 **+ 自訂 `scout`(偵查)/`smithing`(鍛造)**(經使用者拍板突破原設計;**現為 23**,以 `len(gamedata.skills)` 為準);一生評分公式在 `systems/legacy.py`。

---

## 6. 下一步候選(依槓桿排序)

0. **城戰/領主區路線(已立藍圖,Oblivion+Skyrim 參考,逐 Phase 推進)** —— ✅ **Phase 1 已做**(見 §1「領主區 Phase 1」:第 4 城區 `領主區 👑` + 謁見領主,讓 21 城主活起來)。藍圖:
   - ✅ **Phase 2 已做**(見 §1「領主區 Phase 2」):領主委託(source `ruler`)→ `city_standing` → 達 `THANE_STANDING` 受封武士;特權=該省賞金寬待 + 侍從 + 信物。新 Character 欄 `city_standing`/`thaneships`。
   - ✅ **全城武士化已做**(使用者:每個城都要能成為武士):`court.generate_ruler_commissions(gamedata)` 於 `get_gamedata` 載入後就地為**每座無手寫委託的有領主城/鎮**程序化生成 2 委託(肅清在地生態怪 +1 / 清剿省內最低危險地城 +2 → 滿 3)+ 預設信物(`_PROVINCE_GIFT`)/侍從(`_HOUSECARLS`),登錄進 `gamedata.quests`;**決定性、冪等、存讀檔穩定**(qid `ruler_auto_<loc>_N` 每次載入重建相同)。手寫委託(`rulers.json` 已有 `quests`)保留並覆寫:**重點城已手寫考據委託**=布魯瑪 + 帝都/白漫/維威克(共 4 城)。**加重點城考據委託純改 rulers.json `quests`+`thane_gift`+`housecarl` + quests.json;調程序化內容改 `court._province_objectives`/`_PROVINCE_GIFT`/`_HOUSECARLS`**。33 城主全可受封(`test_court` 守門)。
     - 🔴 **反「一批解決整省」(使用者回報委託過於重複,如天際全是打蜘蛛+同一地城)**:`_province_objectives` 回傳每省**生態怪清單 + 地城清單**(非單一);`generate_ruler_commissions` 按**省內序位 `i`** 輪替:`cr=creatures[i%nc]`、q2 `dungeon=dlist[i%nd]`,且 q1 **型別輪替**(`i%3`:0=肅清獵殺 / 1=懸賞較兇怪〔`creatures[(nc-1-i//3)%nc]`〕/ 2=採辦藥材)。採集料由新 `court._province_forage(gd)` **掃 events.json 採集事件**(`explore` context + `provinces` + 給 item 的選項)推導 → 無採集事件的省(艾爾斯維爾)該 slot 退回獵殺。效果:打一批怪/清一地城只解到對應那幾城,而非整省;仍各達 `THANE_STANDING`、**決定性冪等**(sorted+穩定 qid)。`test_province_commissions_are_varied` 守(同省 ≥3 q1 標的 / ≥2 地城 / kill+collect 型別)。
   - ✅ **Phase 3+4 已做(合併,混合戰鬥制)**(見 §1「城戰」):**城為單位、各城主自有立場**(rulers.json `stance`,使用者拍板);選邊(`allegiance`)→ 對敵城**圍城方略**(7 個技能門檻作戰選項,潛行/社交/工具/魔法系都有攻城用途,削守軍)+**輕量化強攻**(單場 `combat`)→ 破城翻轉 `city_faction`。平衡 sim 背書(小城可強攻、大城須廣技能佈局)。`systems/politics.py`。
   - **後續(此里程碑刻意未做)**:佔領後收稅(週期金幣)、駐軍隨時間重建、自走 AI 陣營戰爭、攻下可安插自己為領主、公會與大義綁定、武士所在城翻敵時 Thane 特權暫停。
   - **鐵律**:政治可變狀態寫 `politics.json`/Character(預設值向後相容),地理永遠在 world.json;加領主對話/委託/陣營儘量純改 JSON;每 Phase 走完整 §4 節奏。
   - ✅ **招兵買馬 階段一已做**(見 §1「招兵買馬 階段一」):`systems/warband.py` —— 領主/首領門檻 + 營地(野外/佔領清空地城)+ 兩級軍制(親衛 companions / 士兵 soldiers)+ 招募 + 攻城整合(大軍壓境 op + 實戰援軍)。城戰的金幣/領袖路線成立(純戰士帶軍可取城)。
   - ✅ **招兵買馬 階段二已做**(見 §1「招兵買馬 階段二」):軍餉(`tick_upkeep` 週期金幣沉/付不出逃兵)+ 永久傷亡(`run_battle` casualties out-param → `apply_casualties` 名冊扣減,攻城陣亡不復生)+ 親衛複合來源(`warlord:true` 將領 veteran,唯營地可招)。把軍隊從「零成本永久常駐」修成「須維持、會折損」的資源。
   - ✅ **城戰階段三已做**(見 §1「城戰階段三」):佔領收稅(按居民數量)− 駐軍維護費(`politics.tick_tax`,鏡像軍餉鉤子)+ 輕量叛亂計時(駐軍流失→民心浮動稅斷→潰散則城叛,可 `reinforce_garrison` 回防)+ legacy 補回報債(城/武士/兵計分)。收支閉環成立。🔴 紅線:稅基用 `held_tax_cities` 非 `held_cities`。
   - ✅ **城戰階段四已做**(見 §1「城戰階段四」):領地全局總覽(`action_territory`,遠程回防)+ 駐軍自動緩慢重建(`GARRISON_REGEN_PER`,僅安定、淨 −4、不破叛亂)+ Thane 翻敵特權暫停(可逆)。零新存檔欄位。
     **🚧 後續(階段五/未做)**:AI 陣營自走戰爭(活的政治地圖,大型需 sim)+ 攻下自任領主 + 公會與大義綁定。
1. **內容難度第二階段 / 實機微調**:elite 已上但只在 danger≥4 野外 + 龍喉巢穴/灰燼墓塚出現;可加更多終局區、把 elite 接進更多地城首領池、跑過後微調 elite 數值(魔人領主/巨龍仍偏硬,模擬是 no-heal 下限)。
2. **新省份擴充**(高價值/低風險,純資料):地圖 UI 與群戰都已能撐;加 `world.json` 地點 + `dungeons.json` + `bestiary` 生物 + `rulers.json` 城主即可。
   ⭐ 世界已**閉合成大環**(見 §1「地圖擴展:黑沼澤」——黑沼澤已把賽羅迪爾↔晨風接成環)。再加新省請沿用該模式:**雙向連通、最好再閉一個環**(別接成走廊尾巴);新城/鎮**務必同步加 `rulers.json` 城主**(否則 `test_world` 紅);新地城首領是 elite 就加 `"raw": true`;**新地點記得加 `biome`、主題新怪加 `biomes`**(見 §1「細化省分」,讓生態遭遇分流);新省可加 `trigger.provinces` 風味事件 + `provinces` 在地懸賞;**新地點記得加 `biome`、主題新怪加 `biomes`,新 biome 要補 `test_detailing` 兩個 valid-biome set**。✅ **漢默法爾已做**(西環/desert/抗火弱霜)、✅ **高岩已做**(西北環/moor/抗魔抗霜弱電)、✅ **瓦倫森林已做**(§1「瓦倫森林 Valenwood」西南環/雨林 jungle/**抗霜抗毒弱火**/5 雨林怪/絞藤蛛巢/玻璃整甲掉落)。**元素軸**:火剋×3(snow/swamp/瓦倫)、霜剋×2(ashland/desert)、電剋×1(高岩)、✅ **毒剋×1(艾爾斯維爾草原,首個弱毒省 → 回饋塗毒/煉金刺客)**;**剩餘可候選**:落錘外島羣、史科威爾(若再開省,毒/火/霜/電軸均已用,可循「全新機制」路線如斯庫瑪)。✅ **艾爾斯維爾已做**(§1「斯庫瑪/月糖成癮系統 + 艾爾斯維爾省」:savanna 弱毒/南方大環 + 仿吸血鬼的斯庫瑪成癮機制)。
   ✅ **細化省分已做**(見 §1):生態遭遇表(biome)、告示板按省過濾、天際/晨風補密度、四省 NPC/在地任務/風味事件;**再進一步**亦做了 heartland 招牌生態怪、2 條在地任務鏈、NPC rumor 指路/補齊委託。
   後續評估過、可再做(依槓桿):~~**商店法術分散**(海芬古/黑光城法術重疊、鎮級無法術 → 各省守一學派強制跨省採購)~~ ✅ **已做**(見 §1「城鎮服務專精化」/ R29:各省守護學派 + 保底集 9 道 + imperial_city 通才;順手補 6 空法術城、清 rimmen/torval 孤兒)、~~具名地標與發現~~ ✅ **已做**(見 §1「區域細化:具名地標與發現系統」—— 專用 landmarks.json + game_loop hook,首次抵達一次性發現,邊境 4 節點全有)、**地區氣候機械效果**(非染病版,低槓桿)。**邊境刻意不補 NPC**(全荒野、無城主模型 → 已以地標填內容)。
3. **成就系統**(重玩性,種子已開放):`legacy.compute` 已輸出種子;可加一張結算成就表(首殺 boss / 無傷清地城 / 純法師通關…),複用 `kill_counts`/`cleared_dungeons` 等既有計數。每日/分享種子的前置(種子輸入)已完成。
4. ✅ **體力對法師仍是死資源 —— 已做**(見 §1「法師體力資源對稱化」):施法耗體力(`magic.spell_fatigue_cost`)+ 低體力降法效(`formulas.cast_fatigue_power_factor` ×0.75)+ 法袍套裝省體(`cast_fatigue_factor` 0.80/0.65);純規則層、零存檔欄位、刺客紅線零位移。
5. **半成品/微調**:創角問答推職業(DESIGN 標暫未做);更多事件/任務。(✅ 護甲附魔擴到技能/抗性、武器命中觸發 已做,見 §1「附魔系統擴展」。)
   - ✅ **戰法師體驗 —— 已做**(見 §1「八職功能性身份網格」):**法力回擊** + **spellblade 里程碑(共鳴一擊)** 皆已實作,且毀滅 50/75 互換後**可兼得**(雙 gish loop 成環);**戰法師套裝**評估後不做(本作無 armor→施法懲罰,輕甲套裝=陷阱裝)。
6. (天花板更高、工程量大)主線劇情、坐騎/房產。(✅ 同伴持久 HP/羈絆 + **同伴角色化**〔具名招募/專屬支線/對話/忠誠弧頂點〕已做,見 §1)

> ✅ 已完成(近期):**附魔深化(武器命中效果 + 充能 + 靈魂石經濟)**(§1/R15:武器面從「即時元素+吸血/麻痺/再生」拓成有打法差異的命中效果目錄 —— **Phase 1** 元素 DoT〔焚燒/凍緩〔weaken〕/感電〔扣魔+stagger〕〕+ 命中吸取〔生命/魔力/體力,health 對 solo 受夾〕+ **充能模型**〔命中擒魂·麻痺全階可用但每觸發扣一格、魂石=電池容量、`action_recharge_enchant` 回充;新存檔欄 `enchant_charges`〕;**Phase 2** 靈魂石經濟〔擒魂改填手上**空魂石**、大靈魂石 soul5、**黑魂石**囚人形魂〔`bestiary sentient`+空黑魂石+法術擒魂+infamy〕、法師城供空魂石〕→ 縛魂術對上魂/大靈魂/黑魂/AoE 不可取代;**Phase 3 秘術節點刻意未做**〔樹滿+soul_siphon 已放大新效果,使用者拍板〕。擴 `enchws`〔5 段不變·向後相容·玩家專屬〕+ `magic.resolve_soul_capture` + 純資料 items/bestiary;零段數變動、一個存檔欄 R03 相容;**對抗審查(5 維 fan-out + 逐項對抗驗證)修 2 真 bug**〔凍緩/感電 rider 雙持/多擊 weaken·stagger 去重、`resolve_soul_capture` 過期法咒誤判 spell-trap → 加 `turns>0`〕+ **balance 紅線駁回**〔一武器一附魔 → 雙持至多 2 sustain,實際 ≤ 弱 solo boss 傷害;且本作接受 apex 無傷清 solo,紅線是「不秒殺」而非「不可耗血」,sim 0% 秒殺守;vampiric 無 solo 夾為既有 sim 背書設計、不動;absorb_health 已 ×0.5 solo 夾〕;`sim_assassin` 紅線守〔solo 0% 秒殺、麻痺 solo 免疫不動〕、`test_equipment`+5/`test_magic`+6 守)、**城鎮服務專精化**(§1/R29:城鎮差異化第一刀 —— 訓練師依公會/lore 專精〔戰士城戰鬥/法師城魔法/盜賊城潛行;由公會推導零撰寫,單系城免空選單〕+ 11 招牌城**宗師指點**破 `TRAINER_CAP=75`〔馬卡斯鍛造/冬堡毀滅/裂谷開鎖…〕+ 法師公會**法術學派分省守護**〔各省主賣一派 + 保底集 9 道,別派進階跨省採購,imperial_city 通才;順手補 6 空法術城、清 rimmen/torval 孤兒〕;`data/trainers.json` + `world.json spell_stock` + `world.trainer_*`/`action_trainer`;**零存檔欄位、不需 sim**;`test_world` 加 `test_trainer_specialization`/`test_spell_school_dispersal`)、**附魔系統擴展**(§1:護甲→技能/抗性〔encha 5 段+向後相容、複用飾品 kind〕+ 武器→命中觸發 吸血/麻痺/再生〔enchws,solo boss 免疫麻痺反鎖王〕;零存檔欄位、刺客紅線零位移;對抗審查 0 真 bug)、**法師體力資源對稱化**(§1/§6#4:施法耗體力 + 低體力降法效 + 法袍套裝省體;純規則層零存檔、刺客紅線零位移;對抗審查補 summon 漏接)、**斯庫瑪/月糖成癮 + 艾爾斯維爾省(第八省)**(§1:savanna 弱毒生態軸 + 賽↔艾↔瓦南方大環 + 仿吸血鬼的「亢奮↔戒斷」成癮天平〔亢奮不碰力量/潛行以守刺客紅線〕 + 淨糖解癮;對抗審查修「免費解癮」漏洞)、**世界拓樸改造**(走廊→有環圖,§1)、**種子開放給玩家**(原 §6.4 前置)、
> **公會深度化**(§1:門檻 + 福利/俸祿 + 對立 + 分支)、**裝備系統擴展**(§1:套組/套裝 + 飾品/附魔 + 武器流派 + 法杖)、
> **開局背景「不一樣的人生」MVP**(§1:6 開局,資料驅動 `apply_origin`,零存檔風險)、
> **吸血鬼化系統**(§1:A 狀態機 + B 戰鬥身分 + C 陽光/社交詛咒 + D 解咒任務 + E 夜之裔開局,**五層全做**)、
> **地圖擴展「黑沼澤閉合世界大環」**(§1:7 新地點/5 新怪/1 沉廟/2 城主,世界鏈→大環,純資料四檔)、
> **黑暗兄弟會(里程碑)**(§1:血債招募 + 6 合約晉升階梯 + 五戒/淨化分支 + 夜母祝福 + 暗殺者開局;第 4 公會,刺客流派的歸宿)、
> **細化省分**(§1:生態遭遇表 biome + 告示板按省過濾 + 天際/晨風補密度 + 四省 NPC/在地任務/風味事件;活化原本全域共享的 province 維度,地點 20→23)、
> **再進一步細化**(§1:heartland 招牌生態怪 + 2 條在地任務鏈 + NPC rumor 指路/補齊委託;對抗審查修掉 minotaur 危險度)、
> **城市補全**(§1:按 TES 正史補 13 標誌城市 + 21 城主 + 26 NPC,各省 1 城→多城;地點 23→36,城市設計 workflow + 整合 + 對抗審查)、
> **NPC 增補**(四省平行補 25 名 NPC → 每城 3/每鎮 2、總 59 名,角色多樣 + rumor 指路;純資料 npcs.json)、
> **空城補滿 + 晨風生態**(承委託多樣化審計:24 座非邊境城原 0 NPC〔「城市補全」那波只加 world/rulers 未加 npcs〕→ 8 省並行 workflow 補 71 NPC〔城3/鎮2 全覆蓋,rumor 指路在地地城/鄰城/生態怪〕+ 18 條 npc-source 在地指路任務 + 5 城補至標準;另補 4 隻晨風 ashland 正典生態怪〔崖行鳥/阿利特/尼克斯獵犬/卡古地,生態池 1→5〕→ 晨風委託可輪替、野遇多樣。整合後對抗審查:0 空城、0 跨省張冠李戴、目標全合法;`test_detailing` 加覆蓋率+晨風池守門;NPC 102→178)、
> **新城功能補平**(承空城審計:新城有 inn/merchant/task_board 卻缺公會/訓練師/馬廄/房產、商店薄 → 補平功能。**lore 精選補公會**:20 座 guildless type=city 各 +1 契合公會〔fighters+8/mages+6/thieves+6;thieves 9→15、fighters 15→23、mages 19→25;companions 維持白漫獨有、towns 不補〕——加公會=純 `services` 標籤,會籍/任務全域共用零新內容。**+trainer** 補 7 缺城〔各省大城皆可練技〕。**stable/house** 各 +5 新樞紐〔獨孤城/艾爾登根/科林斯/奧西尼姆/塔尼斯〕。**商店補厚**:薄城補省份/公會在地貨〔法師城加魂石/法杖、盜賊城加 lockpick/ruby、戰士城加武具〕。純資料 world/mounts/houses;line-based 改 world.json 保格式;`test_world` 加 `test_city_services_and_shop_integrity` 守〔每 city 有公會+trainer、商品 id 全合法、stable/house 城存在、無重複 service〕;0 無公會城/0 無效 id)、
> **城內分區 + 簡化選單**(城鎮服務拆成 市集區🛒/公會區⚜/廣場🏛 三個可進入子選單,頂層只剩「城區」三入口;群名簡化 製作/人物;野外/地城自動無城區)、
> **偵查→開戰前備戰空間**(潛近成功+未被伏擊時,依偵查技能換得 1/2/3 個備戰動作:施增益/召喚(鎖 scout≥50)/喝藥/塗毒;順解召喚開場佔回合痛點)、
> **格擋接上技能縮放**(技能健檢抓到格擋等級空轉 → `block_damage_factor` ×0.9→×0.4)、
> **技能里程碑 Skill Mastery P1**(§1:6 條被動達門檻 50/75/100 自動解鎖,反 min-max;含對抗審查覆核修正;P2/P3 路線已拍板)、
> **飾品實戰崩潰修正**(§1:戴飾品被物理擊 `KeyError`,既有 bug)、
> **反 min-max 補洞:說服/撬鎖/行竊接上 practice 成本**(§1)、
> **反 min-max 補洞二:煉金/附魔/修理接上 practice 成本**(§1:製作/維護系同型零成本刷技能,全堵)、
> **Skyrim 式商店庫存**(§1:有限數量+定時補貨+補貨變化,堵煉金套利無限金幣)、
> **煉金材料採集全覆蓋 + 製作系統**(§1:15 材料全可野外採/獵;第一個泛用配方加工 recipes.json,獸皮→皮甲)、
> **領主區 Phase 1**(§1:第 4 城區 👑 謁見領主,讓 21 城主活起來;§6 #0 立攻城戰分層藍圖)、
> **領主區 Phase 2**(§1:領主委託 source `ruler` → 城邦功勳 → 武士冊封 Thaneship;特權=該省賞金寬待+侍從+信物;布魯瑪 2 委託為 MVP 範例)、
> **城戰 Phase 3+4 合併(混合戰鬥制)**(§1:城為單位立場 + 宣誓效忠 + **圍城方略 7 技能作戰 + 輕量強攻** → 破城易幟;平衡 sim 背書;對抗審查確認 farm 已結構性根治)、
> **招兵買馬 階段一**(§1:領主/首領門檻 + 營地 + 兩級軍制(親衛/士兵)+ 招募 + 攻城整合(大軍壓境 + 實戰援軍);城戰金幣/領袖路線)、
> **招兵買馬 階段二**(§1:軍餉週期金幣沉/付不出逃兵 + 攻城永久傷亡(run_battle casualties 回報 → 名冊扣減)+ 親衛複合來源(warlord 將領 veteran);把軍隊修成須維持、會折損的資源)、
> **城戰階段三**(§1:佔領後收稅(按居民數量)− 駐軍維護費 + 輕量叛亂計時(駐軍流失/民心浮動/城叛/回防)+ legacy 補城戰回報債;招兵軍餉「出」↔ 佔領收稅「進」收支閉環;🔴 紅線=稅基只認 held_tax_cities;經評估 workflow 定案 T0)、
> **城戰階段四**(§1:領地全局總覽(遠程回防,免逐城進 court)+ 駐軍自動緩慢重建(僅安定、淨 −4/期、不破叛亂計時)+ Thane 翻敵特權暫停(可逆);零新存檔欄位;規劃 workflow 設計、plan-mode 核定)。
>
> 地圖後續可再加:黑沼澤**起手任務鉤子 / 開局背景**(亞龍人沼澤出身,純改 quests/origins JSON);再開一省續閉環(✅ 漢默法爾/高岩/瓦倫森林/艾爾斯維爾已做,西環/西北環/西南環/南環);高岩**開局背景**(布雷頓獵巫人/匕落出身)或瓦倫森林開局(波斯莫綠約獵手/海文海商,純改 origins JSON);贊密爾沉廟可加後門讓它變環上節點。
> 公會後續可再加:更多分支壓軸 / 階級設施權限 / 公會委託告示。(✅ 暗殺者公會=黑暗兄弟會已做、✅ **戰友團〔第 7 公會,白漫·狼人血脈歸宿,獸血儀式移籍內圈〕已做**,見 §1)。Phase D ③+ 其餘可入會組織(丹莫大族/三聯神殿/影鱗/刀刃/黑蠕蟲)仍各自獨立一輪。
> 黑兄後續可再加:夜母「祕密之死」隨機合約(超出 6 階後的無限委託)/ 違反五戒的懲處(殺同袍→被追殺)/ 聖所升級與密探同伴 / 謀殺後即時衛兵圍捕(目前靠賞金+城門盤查)/ 具名導師(露西恩式)對話包裝。
> 裝備後續可再加:獨特/具名裝備(套裝外的具名神器)、~~附魔護甲擴展到技能/抗性~~ ✅ **已做**、~~武器附魔可帶狀態(吸血/麻痺)~~ ✅ **已做**、~~回復型附魔(per-turn regen)~~ ✅ **已做**(見 §1「附魔系統擴展」:護甲 skill/resist + 武器 vampiric/paralyze/regen,solo boss 免疫麻痺)。~~武器附魔帶元素 DoT~~ ✅ **已做**(見 §1/R15「附魔深化」:武器命中 DoT〔焚燒/凍緩/感電,帶 rider〕+ 命中吸取 + 充能型擒魂/麻痺 + 靈魂石經濟〔空魂石填充/大·黑魂石〕,Phase 1+2;**Phase 3 秘術節點刻意未做** —— 秘術樹已滿〔嚴格二選一〕且 soul_siphon 已自動放大新效果)。可再加:**附魔可疊雙效(雙重附魔)**(最高摩擦軸,留待)、秘術里程碑騰位後的附魔專屬節點。
> 開局後續可再加(✅ 已加 6 個:戰友團/盜賊公會/阿利克爾劍客/海難倖存者/神殿治療者/獸人放逐者,共 14 開局):開局附帶**起手任務鉤子**(MVP 刻意未做)、`armor` 起手整套裝(目前開局只給單件護甲/飾品/法杖)、開局選單依職業/種族過濾推薦。
> 吸血鬼後續可再加:夜視/魅惑等更多吸血鬼能力、~~狼人(同套狀態機另一支)~~ ✅ **已做**(見 §1「狼人化 / 獸形」:主動限時獸形變身、與吸血鬼互斥、戰友團獸血儀式 + 野咬感染 + 解咒;對抗審查修 4 真 bug)、吸血鬼專屬裝備/巢穴、NPC 識破後衛兵敵對(目前只社交封鎖)、解咒任務的具名 NPC/對話包裝。
> 狼人後續可再加:~~餵食進程樹~~ ✅ **已做**(§1「狼人深化」:5 階獸血進程)、~~希爾辛神器(獵者之戒)~~ ✅ **已做**、~~howl 咆哮恐懼 power~~ ✅ **已做**(恫嚇之嚎,solo 免疫);**剩餘**:野外主動變身(目前限戰鬥語境)、獸形在城衛兵實戰圍捕(目前 shunning-light)、月相影響變身、狼人專屬巢穴/同類 NPC。
> 技能里程碑後續可再加(**P2/P3,路線已拍板**):P2 持久 `mastery_*_bonus` 加成層(吸血鬼模式)+ 更多真權衡戰鬥型(**逐條 sim 背書 + 非 boss 精英秒殺率覆核**);P3 純改 JSON 補三系密度(優先 marksman/light_armor 等冷門技,避免 sneak 過載);可另評估『達門檻二選一』能動性(引入最佳化空間=支柱級取捨,需使用者拍板)。

> ⚠️ 開新功能務必沿用「§4 開發節奏」:實作 → 測試 → 平衡 → 煙霧 →(ultracode 開時)對抗式審查 → 覆核修正。

---

## 7. 已知限制 / 待留意

- `run_battle` 沒有回合上限(互動式靠玩家逃跑當出口;若要寫純自動模擬請用 `combat.auto_resolve`,它有 `max_rounds`)。
- ✅ **同伴持久 HP/負傷/羈絆 + 角色化已做**(見 §1「同伴系統深化」+「同伴角色化」):HP 跨戰持久、倒下→負傷 benched(休息康復)、並肩獲勝累積羈絆;**具名招募任務 + 羈絆階解鎖的專屬支線 + 就地對話 + 完成支線的忠誠弧頂點(戰術盟友光環/被動非戰鬥槓桿)**。攻城永久死(既有)+ 冒險模式正常戰鬥不永久死(刻意寬容)。**剩餘**:冒險模式以外的永久死選項、坐騎、同伴間互動/吃醋、開局起手同伴任務鉤子。
- `mass_paralysis` 等純 CC 法術單用不會贏(無傷害),是 combo 工具,符合設計。
- 沒有 CI;測試靠手動 `python3 tests/run_all.py`。可考慮加 GitHub Actions 跑它。

---

## 8. Git 狀態

- 已 init(`main`)、`.gitignore` 排除 `__pycache__`/存檔;均已推上 GitHub。近期 commit(新→舊):
  - `04ab28f` 終局內容:龍喉巢穴地城 + elite 接首領 → `cc6686f` 內容難度:elite + 群戰 + BOSS 單獨 →
    `6bd9d6a` 格擋體力 + 運動降耗 → `5ed464a` 運動旅行加速 → `da33db8` M16 潛行系戰鬥化 →
    `6472732` M15 升級改版 → `4678a72` M14 護甲附魔 → `67726c6` UI 改版 → `52cf9ca` 初始。
- 日後更新:`git add -A && git commit -m "..." && git push`(commit 訊息結尾請加
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`)。
- 本 `handoff.md` **已納入版控**(每完成一輪請順手更新並 commit,讓下個 session 不踩空)。
