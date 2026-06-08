# Handoff — 流亡者 (tesrpg)

上古卷軸風格的**技能驅動沙盒文字 RPG**(終端機,Python + `rich`)。單一英雄:做什麼練什麼、
跨四省(賽羅迪爾/天際/晨風/黑沼澤,世界已閉合成大環)探索鑽地城、戰士/法師/盜賊三系玩法,直到陣亡或隱退結算一生傳奇。

> 給接手的 session:這份文件是「立刻能接著做」的地圖。先讀「現況」「怎麼跑」「開發節奏」三節即可上手。

---

## 0. 環境 / 怎麼跑

- **工作目錄**:`/home/fischer/SLG`
- **GitHub**:`git@github.com:Fischer-Zhang/elder-scrolls-textrpg.git`(分支 `main`,SSH 已認證為 Fischer-Zhang)
- **Python 3.12**;`rich` 由**系統套件**提供(`python3-rich`)—— ⚠️ **本機沒有 `pip`、沒有 `pytest`、sudo 需密碼**。
- **執行遊戲**:`python3 -m tesrpg`(終端)/ `python3 -m tesrpg.web`(本機 Web 版,瀏覽器開 `http://127.0.0.1:8080`)
- **跑測試**:`python3 tests/run_all.py`(不需 pytest;39 個測試模組,目前**全綠**)
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
- **後續(P2/P3,路線已拍板)**:P2 引入持久 `mastery_*_bonus` 加成層(吸血鬼模式)與更多真權衡戰鬥型(**逐條跑 sim + 非 boss 精英秒殺率覆核**);P3 純改 JSON 補三系密度(優先冷門技 marksman/light_armor,避免 sneak 過載)。

**飾品實戰崩潰修正(對抗審查後順手抓到的既有 bug)**:飾品(amulet/ring,無 `armor_rating` 鍵)戴上後,`inventory.effective_armor_rating`(唯一呼叫端=`combat` 玩家受物理擊時)原以 `["armor_rating"]` 直取 → **戴戒指/項鍊後第一次被物理擊中即 `KeyError` 崩潰**。改 `.get` 略過飾品(計 0 護甲)、`worn_armor_rating` 一併防禦化;補回歸測試(還原 HEAD 版可重現)。commit `a10aaeb`。

**反 min-max 補洞:說服/撬鎖/行竊接上 practice 成本(使用者點名三個零成本刷技能漏洞 → 評估 workflow → 直作 → 對抗審查)**:使用者指出三處名實不符 ——「偷竊沒處罰、開鎖沒代價、可一直說服刷口才」。先跑**評估 workflow**(調查→設計→對抗驗證),確認三者皆 `confirmed_gap`,且挖出共同根因:**遊戲早就替每個技能定好 `practice` 價碼**(`data/skills.json` 每技能 `practice`={xp,fatigue,hours},訓練師 `action_practice` 就按此收費),而行竊/撬鎖/說服是**繞過該價碼的實戰捷徑**(同樣 xp、零時間、零體力)。修法=讓三者統一付各自技能的 practice 成本。
- **核心**:`progression.practice_cost(char, gd, skill_id)→(xp, hours, tired)`(共用「體力不濟 xp 減半」模型:扣體力、回傳 xp/時數/tired;**呼叫端**負責推進時間與 `use_skill`)。`action_practice` 重構為呼叫它(單一真實來源,行為逐位等價)。
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
- **製作系統(Task2)**:第一個泛用「配方加工」系統 —— `data/recipes.json`(`inputs`/`output`/`station`/`skill`)+ `gamedata.recipes` + `systems/crafting.py`(`recipes_for_station`/`can_craft`/`missing_inputs`/`craft`)。`craft` 消耗背包原料 → 產**真實物品**(非合成 id),並付該技能 practice 體力+時間(與其他製作系一致,不另闢零成本造物)。接點:`main.py action_craft`(在鐵匠處 `station="smith"`)+ 市集區「製革加工」入口(`armorer` 服務時)+ dispatch。**MVP 4 配方**:狼皮×2→皮護腕/皮靴、×3→皮盔、×5→皮甲(獵狼→自製皮甲的獵人玩法)。**加配方純改 recipes.json**。
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
- **新 Character 欄**`city_standing`/`thaneships`(dataclass 預設、進 to_dict、向後相容);`ui.court_panel` 加顯示功勳/武士身分。**MVP 內容**:布魯瑪 2 委託(殺6狼+1、清切德納寇+2 → 滿 3 受封;信物精靈劍、侍從盾女)。**加領主委託純改 rulers.json `quests` + quests.json(`source:ruler`+`reward.standing`);加侍從/信物純改 rulers.json**。其餘 20 城委託=內容 TODO(純 JSON)。
- **驗證**:30 測試模組全綠(`test_court` 擴充:委託依序開放+完成累積功勳/武士冊封信物+侍從+冪等/賞金寬待/存檔向後相容)+ 端到端煙霧(經真實 `action_court` 選單:接委託→完成→受封→賞金寬待)+ 對抗審查(修掉自身 2 低severity:功勳無畫面回饋、make_thane 信物非冪等)。

**城戰(Phase 3+4 合併:政治立場 + 選邊 + 攻城戰)(使用者拍板:城為單位、各城主自有立場;Phase 3 直接併進 Phase 4)**:領主區從「能差遣」升到「能征伐」—— 完整的城邦戰爭迴圈。核心在 `systems/politics.py`。
- **城為單位的立場**:21 城各有 `stance`(rulers.json:`imperial` 復辟 / `independent` 獨立 / `neutral` 觀望),依各城主考據指派、**刻意跨省混合**(如天際:獨立溫德赫 + 中立白漫 + 復辟海芬古)。玩家在領主區「宣誓效忠」一個大義(`char.allegiance`)→ `relationship`:同=盟、對立=敵(可攻)、中立=觀望。
- **攻城=混合制(使用者拍板:不同戰鬥方式、盡量運用各種技能)**——兩階段:
  - **① 圍城方略(`SIEGE_OPS`,7 核心)**:技能門檻開放的作戰選項,讓**潛行/社交/工具/魔法系**也有攻城用途:偵查(scout)/夜襲(sneak)/撬側門(security)/勸降(speechcraft)/賄賂(mercantile)/法術轟城(destruction)/召喚襲擾(conjuration)。各耗時間+資源(金/魔/體)、**每役每略限一次**(`char.siege_ops` 持久),成功則 `deplete_garrison` 削守軍;風險型(夜襲/撬門)依技能擲成功。
  - **② 輕量化強攻**:單場 `run_battle`(守軍數 `assault_force(剩餘守軍)` + 守將 boss);勝 → `conquer` 翻轉 `city_faction` + 重新駐軍 + 清 siege_ops + 聲望。守軍削得越少 → 強攻越輕鬆 → 方略與強攻成 build 取捨。
- **平衡(sim 背書)**:`assault_force` 隨剩餘守軍單調升 —— **小城(g≤120)可強攻硬下;大城(g200-400)須靠方略削弱**(帝都 400 須廣技能佈局才打得下,純戰士只能靠 recon/bribe 微軟化 → 真·全技能里程碑)。調平衡改 `politics.SIEGE_OPS`/`assault_force`。
- **新 Character 欄**`allegiance`/`city_faction`/`garrison_current`(dataclass 預設、進 to_dict、向後相容;動態戰況懶初始化自 rulers 種子)。接點:`action_court` 加宣誓效忠/發動攻城、`court_panel` 顯示立場·關係·現存駐軍、hub 捕捉攻城 `died`。
- **新 Character 欄**`allegiance`/`city_faction`/`garrison_current`/`siege_ops`(皆 dataclass 預設、進 to_dict、向後相容、懶初始化)。
- **防 farm**:圍城方略 once-each(不可重複)、強攻單場(無波次可分段刷)、方略耗資源為淨流出、強攻 fled 不發戰利 → 杜絕重刷(初版波次模型曾被審查抓到「清波→逃→重刷」MAJOR,改混合制後結構性根治)。
- **驗證**:31 測試模組全綠(`test_politics`:立場跨省混合/關係/選邊/僅敵可攻/方略技能門檻+once-each/扣資源/風險型失敗仍計次/強攻單調+夾限/conquer 清 ops/攻城煙霧 方略→強攻 勝-死-逃/存檔向後相容)+ 平衡 sim + 端到端煙霧(經 action_court:宣誓→7 技能方略軟化→強攻破城)+ 對抗審查(無真 bug、farm 已封堵;順手修 gold 夾 0、刪死碼 base_garrison)。
- **後續(藍圖 §6 #0;此里程碑刻意未做)**:佔領後收稅(週期金幣,複用補貨時間鉤子)/ 駐軍隨時間重建 / 自走 AI 陣營戰爭 / 攻下後可安插自己為領主 / 公會與大義綁定 / 武士所在城翻給敵方時 Thane 特權暫停。**加城/改立場純改 rulers.json**。

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
- ✅ **Phase B 已做(四大義 + 中立可攻 + 自立)**:`CAUSES`/`STANCE_LABEL` 加 `daedric`(神話黎明)/`own`(自立稱雄);`EXPANSIONIST_CAUSES={own,daedric}` → `relationship` 對 neutral 回 `enemy`(普世征服,帝國/獨立**逐位元不變**)。`pledgeable_causes`:帝國/獨立/自立隨時可宣誓,**神話黎明須 `kvatch_falls` 大事件後解鎖**;`_pledge_allegiance` 四選 + 各義說明。`legacy.own_realm_title` 自立依持城數開國稱號(割據梟雄/裂土霸主/問鼎雄主/再造一統的新王)。新 Character 欄 `world_faction`/`world_events_fired`(空預設、進 to_dict、向後相容;供 C 用)。**紅線守住**(held_tax_cities 仍只認 city_faction;自立只稅己城)。驗證:32 模組全綠(test_politics +8:四義/中立可攻/**兩大義關係回歸**/解鎖 gating/自立攻城收稅/自立 title/存檔/四選 pledge 煙霧);自審代對抗審查(agent 限額)。
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
- **🚧 Phase D ③+(後續)**:其餘可入會組織(丹莫大族入族/同伴戰友團/三聯神殿/影鱗/刀刃/黑蠕蟲)各自獨立一輪;更多大事件純加 world_events.json。
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

**內容量**:10 種族 / 13 星座 / 8 職業 / **22 技能(+偵查 scout)** / **19 武器(4 法杖)** / **34 護甲(7 材質整套)** / 25 法術(5 AoE) /
**15 材料(全部可野外採集/獵取)** / **4 飾品** / **製作配方系統(4 皮甲配方)** / **61 生物(7 高階 elite + 2 吸血鬼 + 5 黑沼澤 + 5 漢默法爾沙漠〔含矮人百夫長 boss〕 + 5 高岩霧沼〔含海妖岩魔女 boss〕 + 8 黑兄目標 + 7 神話黎明目標 + 6 九神聖戰目標 + 2 heartland;28 隻帶 biome 生態標籤)** / 3 傭兵 / **50 地點(有環圖+生態 biome〔heartland/snow/ashland/swamp/desert/moor〕,世界閉成三大環〔黑沼澤南環 + 漢默法爾西環 + 高岩西北環〕;賽8/天9/晨8/黑7/漢5/高5/邊8,共 21 城+6 鎮)** / **8 地城(每座 ≥1 任務指向,含龍喉峰屠龍 + 沃倫菲爾矮人遺城 + 海妖岩巫窟)** / **62 任務(3 分支壓軸 + 解咒 + 6 黑兄合約 + 6 神話黎明合約 + 6 九神聖戰合約 + 14 在地任務含 2 任務鏈 + 屠龍 + 漢默法爾 3 + 高岩 3)** / **6 公會(+神話黎明/九神騎士團,大事件解鎖)** / **14 開局背景(含戰友團/盜賊公會/阿利克爾/海難/治療者/獸人放逐)** / **74 NPC(每城 3 / 每鎮 2,角色多樣、greeting + rumor 指路;11 名掛在地委託)** / **31 事件(含 14 省份限定;8 野採採集點=七省齊備)** / **吸血鬼化系統** / **黑暗兄弟會系統** / **技能里程碑系統(6 條 MVP,達門檻自動解鎖)** / **27 城主(各城自治)** / **18 具名地標(各省招牌/邊境發現,首次抵達一次性獎勵)**。
程式:**26 個 `systems` 模組**(+vampirism +brotherhood +mastery +crafting +court +politics +warband +landmarks +achievements)+ models/ui/synth 等,共約 41 個 `.py` + `sim_assassin.py`(平衡回歸);**26 個 `data/*.json`**(+mastery.json +recipes.json +landmarks.json +achievements.json;黑兄/細化省分/城戰立場/招兵兵種/漢默法爾/高岩全靠改既有檔);**40 測試模組**(+test_mastery +test_practice_cost +test_shop +test_crafting +test_court +test_politics +test_warband +test_worldstate +test_mythicdawn +test_knights +test_landmarks +test_polish +test_sheet +test_web +test_achievements)。**新增 `tesrpg/web/` 套件(本機 Web 版,純 stdlib、零 pip;`python3 -m tesrpg.web`)**。 / **成就系統(24 條,唯讀推導、結算+即時角色卡)**。

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
- **潛行系戰鬥(M16 + 刺客大改)**:`sneak` 開場偷襲只在 `run_battle` 第一個行動為攻擊且 `opening` 為真時觸發(僅玩家);`acrobatics` 閃避從 `hit_chance` 扣 `dodge_evasion`。**`opening` 現在不再無條件保證**:① 入場由 `offer_battle` 的 `try_stealth_approach` 檢定決定(失敗 → `run_battle(alerted=True)`→opening 起手即 False);② 旅途伏擊 `surprise=True` 幾乎拿不到;③ 隱遁成功會把 `opening` 重新點亮(`opening = vanish_success`,別改回無條件關閉)。
  - **暗殺殘響**:全在 `resolve_attack` 偷襲分支末端(`sneaking and is_alive(defender)`),掛 `stagger`/`bleed(element=bleed)` 到 defender;踉蹌命中減成在 `hit_chance` 後對「被踉蹌的 attacker」扣 `STAGGER_HIT_PENALTY`。調平衡只改 `formulas` 的 `_ARCHETYPE_SNEAK_AFTERMATH`/`SNEAK_BLEED_*`/`STAGGER_HIT_PENALTY`。
  - **雙持**:`offhand` 只存 id;**副手傷害必須在 `sneak_mult 之後`才加(不吃偷襲倍率)**——`resolve_attack` 與 `estimate_sneak_damage` 兩處要一致,否則精英被秒(審查踩過)。同型雙持需 2 把;`remove_item` 跨門檻會清 `offhand`。雙持時 `_choose_combat_action` 不給格擋。
  - **隱遁**:`try_vanish` 成功跳過敵人階段;**三道煞車缺一不可**——`player_vanish_cost` 體力、`vanishes_done` 每次嘗試遞增(非僅成功)、`MAX_VANISHES_PER_BATTLE` 硬上限。少了會變無限風箏無傷清精英(審查踩過 critical)。
  - **入場檢定/偵查**:`stealth_approach_chance` 吃 `inventory.dominant_weight_class`(重甲噪音)+ 夜間(`hour<6 or >=21`)+ `scouted` + `surprise`。`scout` 是第 22 技能;**新增技能務必同步 `progression.ensure_all_skills`**(舊存檔遷移)。
  - **平衡回歸**:改任何刺客常數後跑 `PYTHONPATH=. python3 sim_assassin.py` 對照(救失手/不秒精英/無風箏)。
- **偵查備戰(scout→備戰空間)**:潛近成功(`got_drop`)且未被伏擊時,`formulas.prep_budget(scout)`(20/50/75→1/2/3)算出開戰前可做幾個準備;`run_battle(..., prep_budget=)` 在**第一個交戰回合之前**跑 `_prep_phase`(施增益/召喚/喝藥/塗毒)。**召喚在備戰預載進 `battle["allies"]`** → 開場即在場、不佔首回合(解召喚痛點)。鐵律守住:prep 在 while 迴圈前 → `opening` 偷襲先機保留;buff/summon_turns 從第一回合照 tick(不延長時效、只省一動);同法術每場備戰不可重施;`active_effects` 戰後由 run_battle 出口 clear(prep 在 run_battle 內 → 無撤退洩漏);召喚鎖 `PREP_SUMMON_MIN_SCOUT=50`。已接 offer_battle + 合約暗殺 + 潛殺平民三處 got_drop 路徑;**地城/Boss 直呼 run_battle(prep_budget 預設 0)刻意不給備戰**(無從偵查一頭撞見的敵人)。調整只動 `formulas.PREP_*` 常數。
- **運動 athletics**:`world.travel` 依 `athletics_travel_factor` 縮短耗時並練運動;`combat.player_attack_cost/player_block_cost` 依 `fatigue_cost_factor` 折扣體力。`格擋` 實扣 `BLOCK_FATIGUE_COST`(別再當死常數)。
- **敵人/難度(內容驅動,不做數值縮放)**:難度靠 `min_level` 解鎖更強物種 + 地點 `danger`,**不** scale 怪物數值(刻意,避免 Oblivion 詬病)。bestiary 加 `"solo": true` 的 BOSS 在 `random_encounter_group` 會收斂成單獨一隻;地城 `boss` 加 `"raw": true` 則以原始強度登場(`action_dungeon` 不再 `spawn_boss` ×1.6)。新敵人/地城純改 JSON。
- **生態遭遇表 / biome(細化省分)**:每個 `world` 地點有 `biome`(heartland/snow/ashland/swamp);bestiary 怪可帶 `biomes`(子集)。`combat.random_encounter(_group)` 依當地 biome 用 `_biome_weight` 加權:在地怪 ×`BIOME_MATCH_WEIGHT`(3.0)、他鄉怪 ×`BIOME_MISMATCH_WEIGHT`(0.25)、**無 `biomes` 標籤=通用墊底池(四海皆有,確保池不空)**。`world.travel`/`main.action_explore` 已傳 biome。**新怪要分流就加 `biomes`、新地點要加 `biome`**;調生態強度只動那兩個常數。⚠️ 同一 biome 的「在地低階怪」danger 要與其他 biome 對齊(snow 曾因低階怪全 d3 而早期偏硬,已靠把 d2 的 frostbite_spider 併入 snow 緩解;雪原仍刻意略硬)。
- **省份維度(細化省分)**:`events.json` 事件可加 `trigger.provinces` 做在地風味/在地遭遇(combat 效果指定該省怪);`quests.json` 的 board 委託可加 `provinces` 做在地懸賞(`quests.available_quests(...,province=)` 過濾、`main.action_board` 傳當地省;無 `provinces`=全圖通用)。NPC 委託走 `npcs.json` 的 `quest` + `dialogue.offered_quest`(`source:"npc"`,不進告示板/公會)。**加省份風味純改 JSON**。
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
  **D 治療**:`cure_vampirism` 用 source `vampire_cure`(`available_quests` 只回對應 source → 不漏進告示板/公會);解咒儀式是顯式動作 `action_vampire_cure`(法師公會子選單,`is_vampire` 閘門),用 `vampirism.cure` 收尾並把任務移出 `completed_quests` 以**可重複**;`mages_guild` 服務**不受社交封鎖**(吸血鬼永遠找得到解咒的女巫)。加新解咒媒介純改 quests.json(注意採集物要買得到:大蒜@布魯瑪、毒茄參@晨風)。
- **技能里程碑(Skill Mastery,P1)**:全在 `systems/mastery.py`,資料在 `data/mastery.json`。門檻**只認 `base_skill()`**(裝備/吸血鬼疊加不得觸發,否則污染成長/夾限)。**加同 kind 里程碑純改 JSON;加新 kind 必須**:①登錄 `mastery._IMPLEMENTED_KINDS`(否則該條完全 inert,不顯示/計分/播報)②加對應 getter ③一處呼叫端分支(**這步不是純 JSON**,別在 doc 誇大)。⚠️ 兩個審查踩過的雷:① 走 `active_effects` 的效果(如溢盾)務必**夾「總量」cap 並打 `source` 標記**(別只夾單次→可疊破),且 `run_battle` 已在**入場清 `player.active_effects`**(在 `_prep_phase` 前)杜絕戰外殘留洩漏;② 戰鬥數值型(壁壘/過載)改常數務必重跑 `sim_assassin.py` + auto_resolve 勝率 gate(**過門檻勝率不得下降**)。新欄位只有 `persuaded_npcs`(辯舌·折服;已進 to_dict、舊存檔預設 [])。

---

## 4. 開發節奏(ultracode 開著 → 每個功能都這樣做)

1. **實作**(資料 + systems + main/ui)。
2. **單元測試**:新增 `tests/test_*.py`(用 `assert`,可直接 `python3` 跑;登錄進 `tests/run_all.py`)。
3. **平衡模擬**:Bash 一行式跑 `combat.auto_resolve` / 手寫迴圈,印勝率/回合數。
4. **無頭煙霧測試**:把 `ui.console` 換成 `Console(file=StringIO())`、`ui.menu` 換成自動選擇,實跑 `run_battle`/action,抓 traceback。
5. **對抗式審查(Workflow 工具)**:多維度 fan-out 審查 → 每個發現由獨立懷疑者**對抗式驗證** → 只回報「能真實重現」的 bug。
6. **覆核 + 修正**:**逐一覆核審查結果**(會有誤報、也會有「會引入新 bug 的錯誤修法」—— 已擋下 2 次);套用確認的修正 + 補回歸測試;重跑全套。

> 戰績:十六輪審查累計修掉 **~29 個真 bug**、擋下 **2 個錯誤修法**、自補 1 次審查覆蓋缺口、自抓數個測試基建坑。
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
**純沙盒**(無主線);時間以「小時」推進(12 月×30 天);技能=Oblivion 的 21 套 **+ 自訂第 22 技能 `scout`(偵查)**(刺客大改時經使用者拍板突破原設計);一生評分公式在 `systems/legacy.py`。

---

## 6. 下一步候選(依槓桿排序)

0. **城戰/領主區路線(已立藍圖,Oblivion+Skyrim 參考,逐 Phase 推進)** —— ✅ **Phase 1 已做**(見 §1「領主區 Phase 1」:第 4 城區 `領主區 👑` + 謁見領主,讓 21 城主活起來)。藍圖:
   - ✅ **Phase 2 已做**(見 §1「領主區 Phase 2」):領主委託(source `ruler`)→ `city_standing` → 達 `THANE_STANDING` 受封武士;特權=該省賞金寬待 + 侍從 + 信物。新 Character 欄 `city_standing`/`thaneships`。其餘 20 城委託=內容 TODO(純 JSON)。
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
   ⭐ 世界已**閉合成大環**(見 §1「地圖擴展:黑沼澤」——黑沼澤已把賽羅迪爾↔晨風接成環)。再加新省請沿用該模式:**雙向連通、最好再閉一個環**(別接成走廊尾巴);新城/鎮**務必同步加 `rulers.json` 城主**(否則 `test_world` 紅);新地城首領是 elite 就加 `"raw": true`;**新地點記得加 `biome`、主題新怪加 `biomes`**(見 §1「細化省分」,讓生態遭遇分流);新省可加 `trigger.provinces` 風味事件 + `provinces` 在地懸賞;**新地點記得加 `biome`、主題新怪加 `biomes`,新 biome 要補 `test_detailing` 兩個 valid-biome set**。✅ **漢默法爾已做**(西環/desert/抗火弱霜)、✅ **高岩已做**(§1「高岩 High Rock」西北環/霧沼 moor/**抗魔抗霜弱電**/5 沼怪/海妖岩巫窟)。**剩餘可候選**:瓦倫森林(西南雨林環,接賽羅迪爾/漢默法爾)。
   ✅ **細化省分已做**(見 §1):生態遭遇表(biome)、告示板按省過濾、天際/晨風補密度、四省 NPC/在地任務/風味事件;**再進一步**亦做了 heartland 招牌生態怪、2 條在地任務鏈、NPC rumor 指路/補齊委託。
   後續評估過、可再做(依槓桿):**商店法術分散**(海芬古/黑光城法術重疊、鎮級無法術 → 各省守一學派強制跨省採購;中風險,需保底集 + 鎮級法術選單,見評估)、~~具名地標與發現~~ ✅ **已做**(見 §1「區域細化:具名地標與發現系統」—— 專用 landmarks.json + game_loop hook,首次抵達一次性發現,邊境 4 節點全有)、**地區氣候機械效果**(非染病版,低槓桿)。**邊境刻意不補 NPC**(全荒野、無城主模型 → 已以地標填內容)。
3. **成就系統**(重玩性,種子已開放):`legacy.compute` 已輸出種子;可加一張結算成就表(首殺 boss / 無傷清地城 / 純法師通關…),複用 `kill_counts`/`cleared_dungeons` 等既有計數。每日/分享種子的前置(種子輸入)已完成。
4. **體力對法師仍是死資源**(體力消耗評估的 option B,未做):純施法者戰鬥中不耗也不受罰體力 → 三系資源不對稱。可做「施法耗少量體力」或「低體力降施法成功/威力」。
5. **半成品/微調**:創角問答推職業;護甲附魔可再擴(目前只 fortify 生命/魔力/體力);更多事件/任務。
6. (天花板更高、工程量大)主線劇情、同伴持久 HP/羈絆、坐騎/房產。

> ✅ 已完成(近期):**世界拓樸改造**(走廊→有環圖,§1)、**種子開放給玩家**(原 §6.4 前置)、
> **公會深度化**(§1:門檻 + 福利/俸祿 + 對立 + 分支)、**裝備系統擴展**(§1:套組/套裝 + 飾品/附魔 + 武器流派 + 法杖)、
> **開局背景「不一樣的人生」MVP**(§1:6 開局,資料驅動 `apply_origin`,零存檔風險)、
> **吸血鬼化系統**(§1:A 狀態機 + B 戰鬥身分 + C 陽光/社交詛咒 + D 解咒任務 + E 夜之裔開局,**五層全做**)、
> **地圖擴展「黑沼澤閉合世界大環」**(§1:7 新地點/5 新怪/1 沉廟/2 城主,世界鏈→大環,純資料四檔)、
> **黑暗兄弟會(里程碑)**(§1:血債招募 + 6 合約晉升階梯 + 五戒/淨化分支 + 夜母祝福 + 暗殺者開局;第 4 公會,刺客流派的歸宿)、
> **細化省分**(§1:生態遭遇表 biome + 告示板按省過濾 + 天際/晨風補密度 + 四省 NPC/在地任務/風味事件;活化原本全域共享的 province 維度,地點 20→23)、
> **再進一步細化**(§1:heartland 招牌生態怪 + 2 條在地任務鏈 + NPC rumor 指路/補齊委託;對抗審查修掉 minotaur 危險度)、
> **城市補全**(§1:按 TES 正史補 13 標誌城市 + 21 城主 + 26 NPC,各省 1 城→多城;地點 23→36,城市設計 workflow + 整合 + 對抗審查)、
> **NPC 增補**(四省平行補 25 名 NPC → 每城 3/每鎮 2、總 59 名,角色多樣 + rumor 指路;純資料 npcs.json)、
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
> 地圖後續可再加:黑沼澤**起手任務鉤子 / 開局背景**(亞龍人沼澤出身,純改 quests/origins JSON);再開一省(瓦倫森林…)續閉環(✅ 漢默法爾/高岩已做,西環+西北環);高岩**開局背景**(布雷頓獵巫人/匕落出身,純改 origins JSON);贊密爾沉廟可加後門讓它變環上節點。
> 公會後續可再加:更多分支壓軸 / 階級設施權限 / 公會委託告示。(✅ 暗殺者公會=黑暗兄弟會已做,見 §1)
> 黑兄後續可再加:夜母「祕密之死」隨機合約(超出 6 階後的無限委託)/ 違反五戒的懲處(殺同袍→被追殺)/ 聖所升級與密探同伴 / 謀殺後即時衛兵圍捕(目前靠賞金+城門盤查)/ 具名導師(露西恩式)對話包裝。
> 裝備後續可再加:獨特/具名裝備(套裝外的具名神器)、附魔護甲擴展到技能/抗性(目前護甲只 fortify 資源)、武器附魔可帶狀態(吸血/麻痺)、回復型附魔(per-turn regen,目前略過)。
> 開局後續可再加(✅ 已加 6 個:戰友團/盜賊公會/阿利克爾劍客/海難倖存者/神殿治療者/獸人放逐者,共 14 開局):開局附帶**起手任務鉤子**(MVP 刻意未做)、`armor` 起手整套裝(目前開局只給單件護甲/飾品/法杖)、開局選單依職業/種族過濾推薦。
> 吸血鬼後續可再加:夜視/魅惑等更多吸血鬼能力、狼人(同套狀態機另一支)、吸血鬼專屬裝備/巢穴、NPC 識破後衛兵敵對(目前只社交封鎖)、解咒任務的具名 NPC/對話包裝(目前梅莉桑德只在子選單文字中現身)。
> 技能里程碑後續可再加(**P2/P3,路線已拍板**):P2 持久 `mastery_*_bonus` 加成層(吸血鬼模式)+ 更多真權衡戰鬥型(**逐條 sim 背書 + 非 boss 精英秒殺率覆核**);P3 純改 JSON 補三系密度(優先 marksman/light_armor 等冷門技,避免 sneak 過載);可另評估『達門檻二選一』能動性(引入最佳化空間=支柱級取捨,需使用者拍板)。

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
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`)。
- 本 `handoff.md` **已納入版控**(每完成一輪請順手更新並 commit,讓下個 session 不踩空)。
