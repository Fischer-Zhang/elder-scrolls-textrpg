# Handoff — 流亡者 (tesrpg)

上古卷軸風格的**技能驅動沙盒文字 RPG**(終端機,Python + `rich`)。單一英雄:做什麼練什麼、
跨四省(賽羅迪爾/天際/晨風/黑沼澤,世界已閉合成大環)探索鑽地城、戰士/法師/盜賊三系玩法,直到陣亡或隱退結算一生傳奇。

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

**內容量**:10 種族 / 13 星座 / 8 職業 / **22 技能(+偵查 scout)** / **19 武器(4 法杖)** / **34 護甲(7 材質整套)** / 25 法術(5 AoE) /
14 材料 / **4 飾品** / **38 生物(7 高階 elite + 2 吸血鬼 + 5 黑沼澤 + 8 黑兄目標 + 2 heartland;18 隻帶 biome 生態標籤)** / 3 傭兵 / **36 地點(有環圖+生態 biome,世界閉合成大環;各省補全城市 賽8/天9/晨8/黑7/邊4,共 17 城+4 鎮)** / **6 地城** / **41 任務(3 分支壓軸 + 解咒 + 6 黑兄合約 + 10 在地任務含 2 任務鏈)** / **4 公會** / **7 開局背景** / **59 NPC(每城 3 / 每鎮 2,角色多樣、greeting + rumor 指路;8 名掛在地委託)** / **24 事件(含 9 省份限定)** / **吸血鬼化系統** / **黑暗兄弟會系統** / **21 城主(各城自治)**。
程式:**19 個 `systems` 模組**(+vampirism +brotherhood)+ models/ui/synth 等,共約 35 個 `.py` + `sim_assassin.py`(平衡回歸);**22 個 `data/*.json`**(黑兄/細化省分全靠改既有檔,無新增 json);**25 測試模組**(+test_detailing)。

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
│   ├── vampirism    吸血鬼化狀態機(力量↔詛咒;game_loop 每圈 update)
│   ├── brotherhood  黑暗兄弟會(血債招募/合約晉升/夜母祝福/洗白賞金)
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
**純沙盒**(無主線);時間以「小時」推進(12 月×30 天);技能=Oblivion 的 21 套 **+ 自訂第 22 技能 `scout`(偵查)**(刺客大改時經使用者拍板突破原設計);一生評分公式在 `systems/legacy.py`。

---

## 6. 下一步候選(依槓桿排序)

0. **城戰**(城主前置已備,見 §1「各城統治者」+「城市補全」):`rulers.json` 已有 **21 城主** + `garrison` 兵力(各城自治,湮滅期大空位)。城市補全後城戰的可佔領目標大增。下一步可在此資料上長出:城邦歸屬/交戰狀態、攻城玩法(複用 `combat` 群戰)、佔領後換城主/收稅、公會/玩家選邊。政治狀態建議仍寫在 `rulers.json`(或新 `politics.json`)而非 world.json。動手前先評估(沿用前幾輪「評估→直作」節奏)。
1. **內容難度第二階段 / 實機微調**:elite 已上但只在 danger≥4 野外 + 龍喉巢穴/灰燼墓塚出現;可加更多終局區、把 elite 接進更多地城首領池、跑過後微調 elite 數值(魔人領主/巨龍仍偏硬,模擬是 no-heal 下限)。
2. **新省份擴充**(高價值/低風險,純資料):地圖 UI 與群戰都已能撐;加 `world.json` 地點 + `dungeons.json` + `bestiary` 生物 + `rulers.json` 城主即可。
   ⭐ 世界已**閉合成大環**(見 §1「地圖擴展:黑沼澤」——黑沼澤已把賽羅迪爾↔晨風接成環)。再加新省請沿用該模式:**雙向連通、最好再閉一個環**(別接成走廊尾巴);新城/鎮**務必同步加 `rulers.json` 城主**(否則 `test_world` 紅);新地城首領是 elite 就加 `"raw": true`;**新地點記得加 `biome`、主題新怪加 `biomes`**(見 §1「細化省分」,讓生態遭遇分流);新省可加 `trigger.provinces` 風味事件 + `provinces` 在地懸賞。**可候選**:漢默法爾(西部沙漠環,接賽羅迪爾/天際)、高岩、瓦倫森林。
   ✅ **細化省分已做**(見 §1):生態遭遇表(biome)、告示板按省過濾、天際/晨風補密度、四省 NPC/在地任務/風味事件;**再進一步**亦做了 heartland 招牌生態怪、2 條在地任務鏈、NPC rumor 指路/補齊委託。
   後續評估過、可再做(依槓桿):**商店法術分散**(海芬古/黑光城法術重疊、鎮級無法術 → 各省守一學派強制跨省採購;中風險,需保底集 + 鎮級法術選單,見評估)、**具名地標與發現**(`once`+`location_ids` 事件 + 一次性奇景;觸發要改「首次抵達必觸發」而非隨機)、**地區氣候機械效果**(非染病版,低槓桿)。**邊境刻意不補 NPC**(全荒野、無城主模型)。
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
> **NPC 增補**(四省平行補 25 名 NPC → 每城 3/每鎮 2、總 59 名,角色多樣 + rumor 指路;純資料 npcs.json)。
>
> 地圖後續可再加:黑沼澤**起手任務鉤子 / 開局背景**(亞龍人沼澤出身,純改 quests/origins JSON);再開一省(漢默法爾/高岩…)續閉環;贊密爾沉廟可加後門讓它變環上節點。
> 公會後續可再加:更多分支壓軸 / 階級設施權限 / 公會委託告示。(✅ 暗殺者公會=黑暗兄弟會已做,見 §1)
> 黑兄後續可再加:夜母「祕密之死」隨機合約(超出 6 階後的無限委託)/ 違反五戒的懲處(殺同袍→被追殺)/ 聖所升級與密探同伴 / 謀殺後即時衛兵圍捕(目前靠賞金+城門盤查)/ 具名導師(露西恩式)對話包裝。
> 裝備後續可再加:獨特/具名裝備(套裝外的具名神器)、附魔護甲擴展到技能/抗性(目前護甲只 fortify 資源)、武器附魔可帶狀態(吸血/麻痺)、回復型附魔(per-turn regen,目前略過)。
> 開局後續可再加:更多開局(暗殺者/海難倖存者/獸人部族…純改 JSON)、開局附帶**起手任務鉤子**(MVP 刻意未做)、`armor` 起手整套裝(目前開局只給單件飾品/法杖)、開局選單依職業/種族過濾推薦。
> 吸血鬼後續可再加:夜視/魅惑等更多吸血鬼能力、狼人(同套狀態機另一支)、吸血鬼專屬裝備/巢穴、NPC 識破後衛兵敵對(目前只社交封鎖)、解咒任務的具名 NPC/對話包裝(目前梅莉桑德只在子選單文字中現身)。

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
