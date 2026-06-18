# CLAUDE.md — 流亡者 (tesrpg) 開發憲法

上古卷軸風格的**技能驅動沙盒文字 RPG**(**瀏覽器 Web 版**;Python 後端,`rich` 把畫面渲成 HTML)。
單一英雄、learn-by-doing(做什麼練什麼)、跨八省探索鑽地城。
> ⚠ **本專案已 Web-only**:終端機版(`python3 -m tesrpg`)已移除;`tesrpg/ui/console.py` 現為 Web 的渲染/輸入接層(rich→HTML view-model + `_web_prompt`),5 個輸入原語在無 web backend 時直接 raise。

> **本檔是給 Claude 的開發憲法**:每次改動都適用的節奏 + 跨領域紅線 + 提交檢查表 + 子系統鐵律「索引」。
> 子系統鐵律**本體**在 [handoff.md](handoff.md) §3(以 `R##` 標號);完整現況清單見 handoff §1;設計理念見 [DESIGN.md](DESIGN.md);玩家「怎麼玩」見 [README.md](README.md);**全增益效果目錄(含實際數值/疊加規則,按來源層橫切)見 [BUFFS.md](BUFFS.md)**(改增益常數順手更新);**角色構築縱切盤點(按 build 走完所有層+分支取捨)見 [build.md](build.md)**。

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
| R34 | **技能里程碑深化:冷技能身份化(檔A)**:4 冷戰技補功能 loop(改 9 節點選項,仍 88/22)—— marksman 控場(`weapon_mod` slow〔**必帶 magnitude** 否則 `slow_factor` 硬下標崩 initiative〕+ 傷害線)、block 盾擊宗師(`block_riposte` getter float→dict 聚合 stagger/weaken/counter)、light_armor/acrobatics 閃身反打(**新 kind `on_evade`** R21 三步,閃過敵攻反擊/回體)。**🔴 on_evade 每回合至多一次**(`_evade_counter_used`,回合頂重置)防反制隨敵數線性放大(鏡像 `EVASION_BONUS_CAP`);改 opt_id 走 `ensure_mastery_choices` 退 pending(零存檔欄);動 combat → 跑 `sim_assassin`。**🅑 砍法系無腦選**:alt/myst_50→護盾/結界威力·conj_50→護甲·illusion 50/100→懾心(`fear_on_hit` 單源→聚合夾0.30);**補 `magic.cast` fear/rout/mass_paralysis 對 solo BOSS 免疫**(R31 法術路徑缺口)。**🅒 頂點 apex 化**:6 stat-dump capstone 弱邊升二 apex(passive_armor×3·potion_potency 聚合·新 kind `combat_regen`/`armor_stagger`〔∵玩家不會被控〕);審查修「防守側 stagger turns:1 死時序→2〔含既有 shield_bash〕」+「combat_regen 復活死人→補 is_alive 守」 | re-sim, save |
| R33 | **裝備耐久/修理整套移除**(Skyrim 式;純雜務稅→零決策):刪 `weapon_condition`/`armor_condition`+折損+`_cond_mult`+三修理路徑+`repair_hammer`+`repair_fee`+ mastery `repair_floor`/`combat_repair`;**「armorer」服務(鐵匠站)≠ 技能**——技能 armorer 整條刪(+4 里程碑節點),服務保留(閘 craft/temper/meltdown,不動 world.json/`_SERVICE_CN`);`effective_armor_rating`併入`worn_armor_rating`、`_armor_display`單值;`smithing_50` 換 `thrifty_forge`+`smith_arm`、`forgemaster`→heavy_armor;戰士公會 `repair_discount`→`armory_discount`(`buy_price` 對 `damage`/`armor_rating` 物品折扣,cap 0.35 非免費守不套利);warrior/archer 主修 + nord/orsimer 種族 armorer→smithing/athletics;`from_dict` 剝舊欄+armorer 鍵、`ensure_mastery_choices` 自動剔陳舊選擇;**動 combat → 必跑 `sim_assassin`** | re-sim, save |
| R35 | **技能里程碑深化:去冗餘/修 no-brainer 波次**:4 個二選一弱邊的「死填充/自我重複」純改 `mastery.json`(零新 kind、零新存檔欄、複用既有 kind,仍 88/22)—— acrobatics_100 `deft_roll`(vanish_floor 與 75 tumble 同值被 MAX 遮蔽)→ `wind_step`(`evasion_bonus`,閃避流);light_armor_50/100 `passive_armor` 填充 → `evasion_bonus`(輕甲=閃避非吸收,反擊流 vs 閃避流);scout_50 `skill_fortify` → `threat_read`(`recon_resist_read` 同 mercantile getter)。**🔴 對抗審查自我糾錯**:初版 `whirl_riposte`(on_evade-counter)**換軸重演隱形遮蔽**(被 light_armor storm_dance 0.6 MAX 遮蔽,雜技+輕甲正是最常見閃避 build)→ 審查「改 SUM」**駁回**(破 counter-MAX 防群戰疊加紅線)→ 正解換 SUM-capped `evasion_bonus`。**鐵則:MAX 聚合軸(counter/vanish_floor)上做二選一弱邊極易製隱形 no-brainer → 弱邊優先 SUM-capped 軸(evasion/restamina)。** 改 opt_id 走 `ensure_mastery_choices` 退 pending;動 combat → 跑 `sim_assassin`(綠) | re-sim, save |
| R36 | **security 功能化 + 核心 loop 修復(混合身份:地城入侵+盜賊)**:評估揪出 security 核心 loop 冷(撬鎖只首通、失敗/避陷不給 xp、行竊練 sneak)→ 使用者拍板放寬。**Part1 練功**:`SECURITY_FAIL_XP_FRAC=0.3`,撬鎖失敗也給少量 xp(`dungeon.pick_lock`)、解陷阱避陷 full/觸發 0.3×(`_resolve_trap`,**補 `is_alive` 守:致死不給 xp**=鏡像 combat_regen)。**Part2 寶箱刷新**:CONTAINER 格去 `first_clear` 閘 → 一般寶箱隨機刷新可重撈(=可再生練功);BOSS 首領寶藏維持首通限定。🟡 經濟放寬(逆反「重訪刷寶」),自然閘=開鎖器金幣+時間+游蕩怪。**Part3 perks**:`security_50`→`light_fingers`(**新 kind `theft_skill`**:steal+0.15/賞金×0.5,`crime.steal_chance` 加 gamedata);`security_100`→`thiefs_eye`(**新 kind `dungeon_casing`** 布林:`case_layer` 進層揭全層陷阱/寶箱,UI 靠 console 既有 `^/$` 零工)。`dungeon_casing` 刻意**布林軸**(R35:不落 lock_floor MAX 軸被遮蔽)、與 scout `has_recon_perk` 互補(全層機關 vs 四鄰任意,不揭怪/不發 scout xp)。⚠ **by-design**:theft 掛 security 樹但練 sneak(跨技能盜賊 synergy,使用者已知拍板);零新存檔欄(地城 explored 局部、opt_id 換走 `ensure_mastery_choices`);**security 不碰戰鬥 → 免 sim** | save |
| R37 | **smithing 功能化身份(混合:工匠·省料 vs 鋒銳·淬鍊威力)**:4× temper_cost_free + 2 死填充 → 零身份。**只 1 新 kind `temper_power`**(50+100 sum 聚合);改 50/100 死填充側 → `temper_edge`(0.10)/`temper_mastery`(0.15),25/75 不動(75 = `efficient` 省料 vs `master_temper` cap = 既有健康工匠-vs-鋒銳)。套進 `smithing.weapon/armor_temper_bonus`(**簽名加 gamedata**)= `int(flat×(1+power))`,4 callsite(combat/console)傳 gamedata。**棄案**:野地鐵匠 field_smithing(58 處 armorer 城鎮密度太高 → 邊際無感)、回收 crafting_yield(`int(base*0.5)` floor 吃 factor + craft↔melt 刷 XP 套利)。**R35 軸**:省料(max-float 時序成長線,同 lock_floor 階梯)/ temper_power(float-factor sum)/ cap(int)各獨立。**🔴 必跑 `sim_assassin`**(temper flat 進偷襲倍率前):apex_temper(cap6+power0.25→武器+15)→ solo boss 0%(cap 夾)、精英 oneshot Δ0%、4 敵死亡率隔離邊際 −0.2pp。對抗審查駁 2 誤報(省料時序線非遮蔽、75 cap 是鋒銳側)、補 4 敵群戰隔離測試;Finding(雙持副手淬鍊不套倍率)=既有行為非本輪。零新存檔欄 | re-sim, save |
| R38 | **speechcraft 功能化身份(混合:社交問題解決者 + 戰場號令)**:最冷線(25/50/75 全議價/fortify 影子 mercantile)→ 混合。**2 新 kind `talk_down_lever`/`rally`**,複用 intimidate_floor/skill_fortify/guaranteed_persuade。50 `war_cry`(intimidate_floor 0.30 威嚇喝退)vs `silver_voiced`(skill_fortify 廣抬社交 odds);75 `silver_pardon`(talk_down_lever:衛兵說退賞金上限 120→200+floor)vs `iron_presence`(intimidate_floor 0.45,與 50 取最=lock_floor 式成長線);100 `charm`(guaranteed_persuade)vs `rally`(戰陣號令)。**`rally` 仿騎士戰旗**(main.py `_has_rally`/gate/action/回合末維護,複用 empower 管線零改 combat.py):speechcraft-gate、純耗體 12、empower 固定 0.15(< 戰旗 0.20、MAX 聚合不疊)、**自身零益**(`not _is_player`;單挑死 perk by-design)。`intimidate_floor` `_param`→MAX 聚合;`INTIMIDATABLE` 擴 {bandit,rogue_thief,city_guard}(主要對盜匪);`talk_down_chance` 加 gamedata=None(back-compat)。**社交免 sim**;rally 無 sim 網(solo 刺客無盟友)→ 對標戰旗上界手動論證、sim_assassin byte-identical。對抗審查駁 2 誤報(intimidate MAX=時序成長線非遮蔽、rally 單挑死=by-design 混合)、修 1 誤註;cap+80 由「一次性說退閘」(失敗即 talked=True 無重試)中和。零新存檔欄。**R34–R38 冷線功能化告一段落** | save |
| R39 | **使用者點名兩改:block 盾反 + empower 遞減疊加曲線**:① `block_50` 死填充「盾陣」(block_deflect)→「盾反」(**新 kind `block_reflect`** reflect 0.20/fatigue 6;combat 反震區複用 armor_reflect 路徑,**與重甲反震疊加=32%**〔使用者拍板可疊,自限:反彈隨受傷縮放+體力閘〕)。opt_id 保留 `shieldwall`(內部 id;~10 測試 fixture 沿用)。② empower 多源由 **MAX→降序加權和** `Σ mag×0.7^i`(`formulas.EMPOWER_STACK_RATIO=0.7`,上限≈3.33×最強;戰旗 0.20+號令 0.15=0.305;**單道 byte-identical**),戰旗+號令同時生效、防 SUM 暴衝,順帶修 R38「號令對騎士 redundant」。**🔴 流程教訓**(`ask-before-balance-tradeoffs` 記憶):審查建議「32%→MAX 封 20%」我**一度自行套用**,使用者糾正「平衡取捨必須先問」→ 還原疊加。審查「盾反打遠程」=誤報(bestiary attack 無 ranged 旗標,物理敵攻皆近戰等價)。`sim_assassin` byte-identical(刺客無盾無盟友)。動 combat → re-sim | re-sim |
| R40 | **弓手散兵戰技:由「裝弓即免費」改為 marksman 里程碑解鎖**(使用者點名;里程碑分流身份化,貼 R34–R38)。三式塞進既有二選一(使用者指定映射):`marksman_50` 散兵走位(取代 tracker)vs 牽制射(取代 harrying_shot slow 線)、`marksman_75` 瞄準射(取代 piercing_volley)對 疾矢。**新 kind `bow_technique`**(R21 三步:`_IMPLEMENTED_KINDS`+`has_bow_technique(char,gd,technique)` getter+main.py 呼叫端),option 帶 `technique` 參數;比照 deathmark/rally(戰鬥動作走里程碑)。main.py 把 `archetype=="bow"` 免費閘改成每式各查 `has_bow_technique`;**戰技數學全不動 → sim byte-identical**(sim 直驅 `resolve_attack` 不經選單)。**🔴 skirmish 解鎖依賴**(使用者拍板):散兵走位複用 vanish,**拔掉 `can_vanish`(sneak 25)閘** → 選了 marksman_50 即可用、保留 `vanish_used<vcap` 上限;成功率仍走 `vanish_chance`(sneak+acro 成長/>3 敵陡降/每場 cap)=三道煞車不變,純弓手能用只是成功率低(by-design 跨技能 synergy)。移除 harrying_shot(slow 控場,與牽制射 niche 重疊)/tracker(recon,scout/mercantile 仍供)/piercing_volley(+8%傷)。改 opt_id → `ensure_mastery_choices` 退 pending(零新存檔欄)。marksman 不碰戰鬥常數 → 免 sim(仍跑確認) | save |
| R41 | **雙手武器握法系統 + 鈍器 mace/axe 分流**(使用者點名;三段提交)。① `blunt` archetype 拆 `mace`(控制流·新 `_ARCHETYPE_BUILTIN_STATUS` 命中擊暈 stagger 0.20/1t,守 `not _is_solo`)/`axe`(破甲流·0.30 pen 由 blunt 移此),**skill 全維持 `blunt`**(含 2H 戰錘/戰斧亦算鈍器;mastery 樹不動);1H 戰斧→短斧、daedric_mace 名→魔族釘錘、wuuthrad arch war_axe→axe(全保 id 零存檔破壞)。② **雙手武器**(`two_handed` 旗,戰錘 mace/戰斧 axe 各 5 階 +45~55%傷·wuuthrad 轉 2H):`inventory.is_two_handed`+`equip_weapon` 裝 2H 自動卸盾/副手+`equip_offhand`/`equip_armor`/`is_dual_wielding` 主手 2H 擋+**新 `ensure_grip`**(載入正規化,零新欄);main 抑制格擋/盾牆、mounts 排除衝鋒。③ **雙手重盾**(`great_shield`+`two_handed`+`bash_damage`+`mitigation`,5 階+crusaders_ward 轉重盾):`combat._weapon_profile` 加盾擊分支(bash·block 技·完全取代武器,守同 beast/bound)、`great` 旗 → `archetype=None`、新 `_great_shield_mitigation_factor`(套 `_shield_wall_factor` 後·乘性·僅物理·`not _is_beast`)、`is_great_shield` None-safe;仍可格擋/盾牆。**🔴 三提交每個跑 `sim_assassin` byte-identical**(刺客匕首非 mace/axe、不持 2H/重盾 → 全 no-op);solo 夾/85% 甲夾/麻痺免疫全守。recipes/world/dungeons 補取得(skill_req 守分級、值守無套利)。`run_all` 64 模組(+test_two_handed/test_great_shield) | re-sim, save |
| R42 | **反傷流功能化:反傷吃 raw(解耦護甲)+ 荊棘附魔身份**(使用者點名+逐項拍板參數)。反傷由吃 `dmg_done`(耦合·護甲越高反越少)改吃**「攻方完整物理輸出(連格擋前)」`raw/block_factor`**(解耦護甲/盾牆/重盾/格擋)→ 龜也能反出有意義傷;物理限定 + player-only(直接 `_set_hp` 非遞迴 → 無 A→B→A 環)。三源相加單次結算:重甲反震 0.12→**0.06** + 盾反 0.20/6→**0.10/10體**(力竭不計)+ **新 `thorns` 荊棘護甲附魔**(盔/胸/手/靴/盾各一條·反傷%=靈魂石階×1%·不吃 myst/potency·`inventory.thorns_reflect` 聚合 5 槽 /100)→ max **0.41 of raw**。**🔴 不夾(使用者拍板)**:紅線靠①物理限定(元素 solo boss〔湮滅系全元素〕反傷流完全不反=天然剋星)②盾反體力閘③物理敵 raw 上限小(最強 raw41×0.41=17<物理 boss HP120+→永不一擊反殺)自然守;反傷=反應式非偷襲→不碰 solo cap。touch:mastery.json/combat.py(反傷區)/enchanting+synth(thorns kind)/inventory getter/main UI。`sim_assassin` byte-identical(反傷只防守側·刺客無投入)。**前瞻**:無夾,日後若加高物理 raw 敵(>~300)再評估加夾 | re-sim |

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
