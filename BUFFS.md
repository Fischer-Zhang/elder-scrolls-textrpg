# BUFFS.md — 流亡者 (tesrpg) 增益效果總盤點

> **這是一份「參考目錄」**(catalog,非設計憲法):把全遊戲所有增益/減益依來源層整理、附實際數值,方便查閱與平衡盤點。
> **本檔按「來源層橫切」**(所有增益依層羅列);若要「按 build 縱切」(一條構築走完所有層+分支取捨)見 [build.md](build.md)。
> 真實來源(single source of truth)仍是程式碼(`tesrpg/systems/*.py`、`tesrpg/formulas.py`)與資料(`tesrpg/data/*.json`);
> 數值有疑義以程式常數/JSON 為準。鐵律本體見 [handoff.md](handoff.md) §3(R05/R07/R11/R14/R15/R20/R21/R25/R26)、設計理念見 [DESIGN.md](DESIGN.md)。
> 末次盤點:2026-06-16(煉金深化 Phase 1 限時增益藥水 `potion_*` 層〔§⑥/R30〕+ Phase 2 毒劑深化五毒型〔§⑥/R31〕+ Phase 3 效果揭露〔R32,純資訊層、零數值影響〕)。改增益常數後請順手更新本檔。

---

> 全部增益依「來源層」分六大類。標記:🔴=碰戰鬥/偷襲紅線、★=同類唯一/設計重點、▼=減益(懲罰)。
> 疊加術語:**獨立層**=寫入專屬 `*_bonus` 欄、聚合於 `attr()/skill()/entity_resist()` 直接相加、絕不寫回 base;**聚合相加**=同 dict 累加;**取最強**=max/min(防暴衝);**一次性**=即時非持續。

---

## ① 永久身分層(獨立疊加層,聚合於 attr()/skill()/entity_resist();絕不寫回 base)

四層彼此**獨立相加**(達貢非詛咒可與吸血/狼人並存;吸血與狼人因疾病免疫互斥)。

### 吸血鬼(階級隨「未進食天數」動態 0→3;進食歸 T0,每 2 日 +1 階,夾 MAX_STAGE=3)
| 子層 | kind | 數值(T1/T2/T3) | 備註 |
|---|---|---|---|
| `vampire_attr_bonus` | 屬性 | str/speed/willpower 各 +5/+10/+15(stg×5) | T0 不給屬性;str→武傷+max_fatigue |
| `vampire_skill_bonus` | 技能 | sneak/illusion 各 +5/+10/+15 | ★唯一餵 sneak 技能的身分層;加潛行命中/門檻**非**偷襲倍率 |
| `vampire_resist` | 抗性 | disease +100(各階恆有含T0)、frost +10/+20/+30、**fire −10/−20/−30(弱點▼)** | fire/frost 吃 magic 管線(R14);disease 100=免疫(故與狼人互斥) |
| 陽光灼傷▼ | 懲罰 | SUN_DMG=1.5×日照時×階(stg≥1,地城遮蔽) | 戶外懲罰非戰鬥增益 |
| 夜視(R56) | 情境 | 夜間潛近 +0.05×階 / 旅行迴避 +0.04×階(僅夜晚·讀快取 stage) | 陽光的鏡像(日損夜利);非戰鬥數值·折入 stealth approach_bonus |
| 社交魅惑(R56) | 情境 | persuade/talk_down +0.10(任一階·vampire-only) | 逆補階級 shun 社交懲罰·沿用既有夾限 |
| 偽裝(R56) | 功能 | 穿滿 `nightshade` 四件套裝(disguise 旗)→ 城內不被識破圍捕/shun | 非數值;`is_disguised` 覆寫 manhunt/shun/attitude·requires_vampire |

### 狼人(獸血階 tier 0→4,門檻累計吞噬 FEED_TIERS=[10,25,50,100];限獸形中)
| 子層 | kind | 數值(T0→T4) | 備註 |
|---|---|---|---|
| `werewolf_attr_bonus` | 屬性 | str 25→42 / endurance 40→70 / speed 15→20 / agility 10→14 | 🔴str 巨幅放近戰,但**獸形 sneak_attack=False**(結構免疫刺客紅線) |
| `werewolf_health_bonus` | 資源上限 | +80/100/120/140/160(直接加 max_health) | 脫甲後靠血量扛傷;吞噬回血 beast_health//2 |
| BEAST_ARMOR | 減傷 | ★固定 4(不隨 tier 成長) | 刻意微薄;靠血量非護甲 |
| `werewolf_resist` | 抗性 | disease +100(人形也保留) | 人形 afflicted 唯一加成;免疫=不被吸血感染 |
| **結構性權衡** | — | 獸形**脫去整套裝備/附魔/淬鍊/法術/格擋** | 用獸力換掉 equip_* 全部層;revert 力竭 −30 體力 |

> tier≥2 解鎖恫嚇之嚎(HOWL_FATIGUE=25,FEAR 2 回合,solo boss 免疫);獸爪額外傷 _TIER_CLAW=[0,1,2,3,4]。

### 斯庫瑪 / 月糖(限時亢奮;★刻意不碰 strength/sneak/武傷以避刺客紅線)
| 子層 | kind | 數值 | scope |
|---|---|---|---|
| 斯庫瑪亢奮 `skooma_attr_bonus` | 屬性 | speed/agility/willpower 各 +8 | 8h×0.85^成癮,夾 MIN 1h |
| 月糖亢奮(弱) | 屬性 | speed/agility 各 +5(無 willpower) | 4h×0.85^成癮,夾 1h |
| 斯庫瑪回復 | 續航(一次性) | fatigue +80、health +30 | 月糖僅 fatigue +40 |
| 戒斷負屬性▼ | 屬性[負] | str/willpower/agility/endurance 各 −3×step(step1–6,最深 −18) | ★唯一**減** str 的層(懲罰方向,不破紅線) |
| 戒斷負技能▼ | 技能[負] | alchemy −3×step(−3→−18) | 亢奮時清空;只削煉金 |

> 每次用藥 addiction +1(夾 10);成癮≥3 清醒起戒斷;清醒滿 2 日 addiction −1。亢奮 attr 與戒斷 attr 共欄互斥。

### 達貢之力(★四層中唯一純永久、無動態/無懲罰;md7 結局 grant)
| 子層 | kind | 數值 | 備註 |
|---|---|---|---|
| `dagon_attr_bonus` | 屬性 | str +18、willpower +12、endurance +12(合計 +42) | 🔴str +18 放近戰基礎傷(非偷襲倍率);校準介於吸血 T3 與狼人 T4 |
| `dagon_skill_bonus` | 技能 | destruction +10、conjuration +8 | 助毀滅/咒術;不碰 sneak |
| `dagon_resist` | 抗性 | fire +60 | ★可抵銷吸血 T3 火弱點(−30→淨 +30,全層相加非取最) |
| `dagon_magic_bonus` | 資源上限 | magicka +25(直接加 max_magicka) | 獨立於 intelligence 衍生 |

### 死靈師永久升級(R106C;靈魂 token 買斷·`char.necro_upgrades`·**每種費用皆漸增曲線**·解鎖走 conjuration 25 里程碑 has_soul_economy·取代省魔)
| 子層 | kind | 數值 | 費用曲線 | 備註 |
|---|---|---|---|---|
| 亡者生命 undead_health | 真·亡者 max HP | +6/級·夾 NECRO_HEALTH_CAP=**30**(平坦) | [10,20,40,80,160] | magic.cast 召/復生真·亡者時平坦加值(疊亡者統御後);base 骷髏 32 HP → 極致 62 |
| 亡者護甲 undead_armor | 減傷(護甲值) | +2/級·夾 NECRO_ARMOR_CAP=**10** | [10,20,40,80,160] | ★**唯一走 combat._armor_rating 而非 attr()** 的永久獨立層(同 passive_armor 相加·絕不寫 base·非資源不 recompute);offense-neutral |
| 亡者軍團 undead_cap | 軍團上限 | 同場真·亡者上限 +1/級(base 3·max +2→5) | [100,**500**] | **破牆主槓桿**(base 3 守 dagon 0%·擴到 5 極致 40% 破);magic.cast 讀 undead_field_cap |
| 喚魂精算 grave_thrift | token 折減 | 真·亡者召喚 token −1/級(**可降至 0**·max 2) | [100,300] | 讀 necromancy.spend_cost(raise_thrall 3→1 仍≥1·復生1/奴役2 可免費) |

**真·亡者分軸縮放**(非升級·使用者拍板 技能→生命·法術威力→攻擊):
- **生命** `necromancy.undead_conj_scale`:乘 `FLOOR 0.4 → 封頂 1.25`(線性隨 **base_skill(conjuration)**/100·初始更弱)。
- **攻擊** `necromancy.undead_attack_scale`:乘 `智力威力 × (法袍套裝 + 法杖焦點 + 誓福威力)`·**刻意不含 conjuration 技能**·夾 `UNDEAD_ATK_SCALE_CAP=2.0`(布衣 int100 ≈1.30·大法師袍 ≈1.49)。
- 再疊亡者統御(HP+30%/傷+20%)+ 亡者生命平坦加值。**極致投入(滿升級+滿法師裝+conj100)可 ~67% 磨穿終王牆 = 極致付出的真實回報**(R63·使用者拍板);base/新手仍守 ~0%。

---

## ② 裝備層(附魔/套裝/淬鍊/神器)

### 附魔(soul=魂等級、mysticism=祕法技能;mag×(1+enchant_potency),potency 來自里程碑「靈魂虹吸」預設0)
| 附魔 | kind | factor / 公式(例:soul4·myst50→myst100) | 載體 | 疊加 |
|---|---|---|---|---|
| fortify_skill | 技能 | 飾品×2.0→8→12;護甲×1.5→6→9 | enchj/encha | 聚合相加→skills;餵 char.skill() 不回門檻(R21) |
| fortify_attribute | 屬性 | ★僅飾品×1.2→5→7 | enchj | 聚合相加;護甲刻意排除 attr |
| fortify_resource | 資源上限 | 飾品×3.0→12→18;護甲版 armor_fortify→13→19 | enchj/encha | 護甲版額外經 armor_fortify_totals 餵 recompute;進有效上限(R05) |
| resist_element | 抗性 | **R66 soul^0.7 非線性**·大魂飾 單元素~18/魔抗~9(護甲 12/6)·**魔抗=單元素÷2**(每點覆蓋火/霜/電);myst75 ×0.83·myst50 ×0.67·+potency ×1.2 | enchj/encha | 附魔聚合相加(equip_resist);**R131 最終元素傷害=元素層×魔抗層〔`(1−元素抗/100)×(1−magic/100)`·相乘不相加→疊過100不再歸零〕**;**單層**100%=完全免疫,負值=弱點放大(最高2×) |
| resist **physical**(R127) | 抗性 | 護甲之外的乘性物理減傷·**pen 完全無法穿透**(抗性層非護甲層)。走**魔抗低階不 ×2**(物理已有護甲·保守):大魂 甲6/飾9;藥 brew(troll_fat/bear_claw/bone_meal)~16;誓福 sundered_arcanist 10 | enchj/encha·潛時藥·boon | 聚合相加,但**玩家側夾 `PLAYER_PHYSICAL_RESIST_CAP=25`**(守 R71 群戰風險;boss〔真身 60〕不夾) |
| weapon_element | 傷害 | ×3.0→13→19;fire/frost/shock | enchw | 🔴**無視物理護甲**、吃元素抗;加在偷襲夾限**之前** |
| weapon vampiric | 續航回復 | ★傷害×0.30 回血(雙持 0.48);**enchant.magnitude(%)可覆寫**(悲傷之刃 50);命中必觸發 | enchws | 主+副(×0.6)累計一次回血;夾本擊 dmg 內 |
| weapon paralyze | 控場(★充能) | proc 10%、turns=1;**mag=充能容量**=round(soul×5×(0.6+myst/100))→ soul4·myst50≈22 | enchws | 🔴**solo boss 免疫**(R15);觸發扣一格、歸零不觸發;舊式 mag=0=legacy 無限 |
| weapon regen | 續航回復 | ×1.5→7、turns=3 HoT(副手×0.6) | enchws | source 去重(主手優先,命中刷新不疊) |
| weapon DoT(burn/chill/jolt) | 持續傷+異常 | 每回合×1.2→5→8(fire/frost/shock);turns=3、吃元素抗;rider:chill→weaken15%·2t、jolt→扣魔8+stagger20% | enchws | 掛 dot 經 tick_effects;命中刷新取 max(免疊爆);與 enchw 即時並存 |
| weapon absorb(health/magicka/fatigue) | 吸取續航 | 命中回攻擊者×1.5→7→10;absorb_health 另扣目標(**solo boss ×0.5 夾**) | enchws | 玩家專屬;夾資源上限;health 杜絕無限回血泵 |
| weapon soul_trap | 集魂(★充能) | 命中掛 soul_trap(turns3);**mag=充能容量**(同 paralyze 公式) | enchws | 已擒不重複;歸零不觸發;src=weapon(人形/黑魂專屬法術)；發魂走填充循環 |
| weapon berserk | 傷害 | ★依攻方**已損生命**比例提傷,封頂 magnitude%(維蘇拉德 30);**滿血=×1**(開場偷襲不放大) | enchw(berserk) | 乘物理 dmg、在 solo 偷襲/衝鋒夾限**之前** → solo 受夾 |

> **充能型(soul_trap/paralyze)**:魂石等級=電池容量(編碼進 id mag 欄);現存充能在 `char.enchant_charges{item_id:int}`(存檔欄),`action_recharge_enchant` 以魂石回充(+soul×5,夾容量)。其餘武器效果無充能(魂石已決定威力)。
> **靈魂石階**:微1/次2/普3/上4/**大5**(danger5);**黑魂石**(soul5)囚人形/有靈魂(需空黑魂石+法術擒魂,+infamy)。擒魂填手上**空魂石**(夠裝最小階),無則逸散。
> 餵 char.skill()/char.attr() 而非 base → 絕不回饋成長門檻;改 equipped 後必 recompute_max_resources(帶 gamedata)。

### 護甲套裝(穿滿同材質 4 件 helmet/cuirass/gauntlets/boots,盾不計;★一次性整套,聚合進對應 dict)
| 套裝 | kind | 數值 |
|---|---|---|
| 皮革 leather | 技能 | sneak +15 |
| 玻璃 glass | 技能 | acrobatics +15 |
| 矮人 dwarven | 屬性 | ★唯一給屬性的套裝:endurance +10 |
| 鐵 iron / 鋼 steel | 資源上限 | health +15 / +25 |
| 精靈 elven | 資源上限 | magicka +30 |
| 魔族 daedric | 資源上限 | ★最高生命套:health +60 |
| 龍祭司 dragonpriest | 資源上限 | ★最高魔力套:magicka +110 |
| 黑檀 ebony | 抗性 | magic +15%(通用,同削 fire/frost/shock) |
| 龍鱗 dragonscale | 抗性 | fire +25% |
| 學徒布袍 cloth | 資源上限+施法折扣 | magicka +40;★cast_fatigue_factor=0.80 |
| 大法師 archmage | 資源上限+施法折扣 | magicka +70;cast_fatigue_factor=0.65 |

### 淬鍊(★獨立永久層,綁 item_id,永久不衰減;僅玩家;改 combat/formulas 必跑 sim R25)
| 淬鍊 | kind | 數值 | 上限 |
|---|---|---|---|
| 武器淬鍊 | 傷害 | +2 傷/級,滿 +10 | min(5, smithing//20) + 里程碑「淬火宗師」+1 |
| 護甲淬鍊 | 減傷(護甲值) | +1 護甲/級/件,穿戴件加總 | 同上;卸下不計 |

### 神器(固定資料附魔,單件不觸發套裝)
| 神器 | kind | 數值 |
|---|---|---|
| 十字軍護心 crusaders_aegis | 抗性+護甲 | resist fire +50%、armor 32(heavy cuirass);配 magic 抗逼近免疫 |
| 黎明之牙 dawnfang | 傷害 | weapon_element fire +28(★全遊戲最高之一,無視護甲);本體 dmg24 sword |
| 魔銳茲之刃 mehrunes_razor | 傷害 | weapon_element shock +25;dmg16 dagger speed1.5(偷襲流主力,可雙持) |
| 魔典·哲思之卷 mysterium_xarxes | 技能 | conjuration +15(amulet) |
| 焚天劍 skyburner | 傷害 | weapon_element fire +26;dmg23 sword(龍喉巢穴專屬,單一來源不可刷) |
| 百戰勳刃 valor_blade | 傷害+續航 | regen 3×3 HoT;dmg22 sword(★戰士公會掌門) |
| 馬格努斯之杖 staff_of_magnus | 傷害 | weapon_element shock +26;dmg11 staff(★法師公會掌門) |
| 骷髏鑰匙 skeleton_key | 技能+效用 | security +20 + 撬鎖必成/不耗開鎖器(amulet;★**Nocturnal 暮光聖陵**神器,竊鑰分支;R47 換手自盜賊公會) |
| 灰狐面具 gray_fox_mask | 效用(R47) | `talk_down_cap`:衛兵說退**賞金上限 +120**(120→240,疊 silver_pardon 320)+ 成功率下限 0.25(helmet;★**盜賊公會掌門**·提高可協商罰金) |
| 悲傷之刃 blade_of_woe | 續航 | vampiric 吸血 50%;dmg16 dagger(★黑暗兄弟會掌門) |
| 十字軍聖盾 crusaders_ward | 抗性 | resist magic +30%;armor 16(heavy shield;★九神騎士團掌門) |
| 維蘇拉德 wuuthrad | 傷害 | berserk 最高 +30%(依已損生命);dmg23 war_axe(★戰友團掌門) |
| 瓦巴賈克 wabbajack | 混沌(R46) | weapon_status `"wabbajack"`:命中**隨機六效果**〔元素爆發 solo 夾0.5 / 隨機控場走 `apply_control` / 回自身資源 / weaken0.20 / 回火自傷 max(1) / 回火治敵〕·回火 16% 自平衡(永不嚴格最優)·**玩家不可鍛造**·dmg10 staff(★瘋神謝歐格拉斯神器) |
| 秩序之劍 sword_of_jyggalag | 秩序(R48) | enchant `order`:**移除傷害變異**(傷害 roll 永遠取最大 `DAMAGE_ROLL_HI`=1.15·≈平均 +15% + 零隨機)·**反 Wabbajack**·always-max 在 solo 偷襲夾之前+sword 偷襲×1.0→永不秒殺 solo·dmg26 1H sword(★秩序之主賈格拉格神器) |

---

## ③ 里程碑 perk(已選 chosen_fortify_options;絕不寫回 base,只認 base_skill 判門檻 R21)

### 永久 fortify 層(stats.recompute_mastery_bonuses,在 recompute_max_resources 內先跑;聚合相加)
| 層 | kind | 代表數值 |
|---|---|---|
| skill_fortify | 技能 | +6~+10(*_75多+8、*_100 +10) |
| attr_fortify | 屬性 | +4~+6(*_100如 iron_body str+5、tireless speed+6) |
| resist_fortify | 抗性 | magic +10~+15、disease +25~+30 |
| passive_armor | 減傷 | 多源相加 4~20(石膚20、銅皮鐵骨18、鐵布衫12…;總減傷夾 85% 硬頂+遞減,不趨近免疫)〔R118:變化魔皮14→shield_recoil·R120:靈光護壁 spectral_aegis→arcane_erosion 秘蝕(破抗 debuff·非護甲)〕 |

### 偷襲/刺客鏈(🔴詳見第④紅線小節)
| perk | kind | 數值 | 疊加 |
|---|---|---|---|
| 影刃·暗殺宗師 | 偷襲倍率 | mult_bonus 0.50→×1.5 | 🔴乘進 sneak_mult 鏈 |
| 致命烙印 deathmark | 破甲+耗體 | pen +0.35、fatigue15、turns4、cd6 | 🔴僅 follow-up(`not sneaking` 閘);最終 pen 夾0.85 |
| approach_bonus | 偷襲機率 | 各 0.10/0.10/0.12(相加最高0.22) | 只動搶開場頻率,夾[0.05,0.97] |
| 武器流派 weapon_mod | 傷害/命中/破甲 | power(偷襲前套)blade0.12+0.08、徒手0.15+0.10(R103:25 節點 fist_basics +0.05 已移除→改授 offbalance_unlock);hit/pen/recoil/fatigue/poise_rate(擒拿手0.6 加速徒手失衡)/on_hit | 🔴power 偷襲倍率**之前**算但不吃倍率;同 target 相加、on_hit 取最後;poise_rate 僅 hand_to_hand 命中時讀 |
| 徒手失衡 ramp offbalance | 徒手傷害遞增(敵側暫態·鏡像 conduct R75) | 每層 +4%·夾 OFFBALANCE_MAX_STACKS=8(+32%);徒手命中 +1+skill//50 層(×(1+poise_rate))·窗口 3 回合·**不入存檔 R03** | 🔴只玩家徒手(`wpn_skill_id=="hand_to_hand"·not beast`)讀寫·ramp 閘 `not sneaking`(不放大偷襲);門檻4踉蹌·滿頂8 機率0.25 真擊倒(走 apply_control·solo 機率抵抗)+重置;**R103 gated:須 hand_to_hand≥25 解鎖(offbalance_unlock 自動授予)且未穿重甲(`inventory.wears_heavy_armor`)→ 重甲/未解鎖完全不累積** |
| 秘蝕 erosion(破抗)| 削目標通用魔抗(敵側暫態·鏡像 conduct R75·削抗非增傷) | 每層 −EROSION_RESIST_PER_STACK=3 點 magic 抗·夾 EROSION_MAX_STACKS=5(−15)·**R121 湮識命中該敵 → 升 EROSION_DEEP_MAX_STACKS=10(−30·本場單敵·`_deep_erosion` 暫態旗標)**·floored≥0(只蝕既有抗性不製造弱點);傷害法術命中 +1 層·窗口 EROSION_TURNS=3·**不入存檔 R03** | 🔴僅 `mastery.has_arcane_erosion`(mysticism_100 秘蝕頂點)持有者的**任何傷害法術**施加+受益;因火/冰/雷亦吃 magic 抗 → **輔助所有傷害魔法**(非僅秘術 magic 系);`{**resist}` 複製不 mutate boss·非頂點者短路→sim byte-identical;達貢 fire85 恆牆·−15/−30 削抗不破 720 offense 牆(sim 全 0-1%) |
| 念力球反噬 _dungeon_curse(R121)| 隨機大減一項**非秘術**技能(玩家側暫態·地城限) | −_ORB_CURSE=40(夾≥0·優先有點數技能·不重複);`orbs:true` 地城每層一顆念力球·念力術破之免患·未破離層/決戰即反噬·**不入存檔·離場即清+進場重置** | 🔴 skill() 讀暫態負層(None→+0 byte-identical);念力術破球免患·靈視/靈識揭球位置;唯秘術試煉 soul_sanctum 有;唯一呼叫端清防滲出 |
| armor_sneak_relief | 潛行 | relief 1.0(全免護甲噪音懲罰) | 單源;不放大倍率 |

### 法師/施法(🔴改施法常數 R10/R14 須跑 sim)
| perk | kind | 數值 |
|---|---|---|
| 過載/各省魔/凝練 spell_mod+overload | 傷害/續航/護盾 | power+:destruction0.20/alteration0.15+0.10/restoration0.20+0.10〔divine_grace+holy_zeal·R122〕/mysticism0.10+0.15(相加,吃 _power → 傷害·護盾·結界·聖光);cost:0.92/0.85/過載1.30(相乘);impact stagger0.35 |
| 聖騎士反死靈 smite/radiant(R123·恢復) | 傷害/專精 | **治療傷害不死**:minor_heal/heal/close_wounds〔smite_undead〕指向不死敵造傷=回復量×`HEAL_SMITE_FACTOR`=0.5×威力(element magic·吃 magic 抗);**對活物零傷害**(恢復系對活人零遠程輸出→靠近戰)。驅散亡者(turn_undead·holy 控場只對不死)。終極 **破曉之光**(radiant·治全隊 heal55×威力 + 灼燒全體不死 mag38×威力·經聖光試煉取得) |
| 聖化領域 consecration(R122·恢復) | 減傷守護 | 自身限時光環·來襲傷害(物理+元素)×(1−mag)·mag 0.20(+聖化壁壘 sacred_bulwark 0.10=0.30)·turns3·gated 玩家·刷新非疊加 |
| 奧術連鎖 cascade | 傷害/續航 | power+8%/層、省體×(1−0.12/層,夾≥0.4)、max_depth2(最高+16%/省24%);停手即散 |
| 共鳴一擊 resonance | 傷害 | 🔴transfer0.5(下一近戰灌半數法力作元素傷)+dot4×3;加在 solo 夾限之前 |
| 法力回擊 mana_on_hit | 資源回復 | 近戰命中 +4 魔力 |
| 雙重/束縛召喚 summon_mod | 召喚 | twin:extra1隻×0.6血;bound_blade:hp+0.25/turn+1 |
| 戰地搶救 triage | 資源折扣 | 同伴<30%時下道治療 魔×0.15/體×0.25 |
| 靈魂虹吸 enchant_potency | 增幅 | 🔴附魔強度×1.2(製作乘子,R15) |
| 濃縮/萬靈藥 potion_potency | 增幅 | 藥水/毒效 ×1.20~1.35(濃縮0.20+萬靈藥0.15 相加;只放大 DoT/buff/回復,不碰控制毒) |

### 防禦/續航/控場
| perk | kind | 數值 |
|---|---|---|
| 壁壘 bulwark | 減傷+代價 | 受物理×0.85、攻擊耗體×1.20(真權衡;僅物理,元素穿透) |
| 不屈祝禱 steadfast | 續航回復 | 血<25%→regen4×3(共12) |
| 溢盾 overheal_ward | 減傷 | 溢治60%轉盾、cap=生命×0.5、turns4(R21夾cap) |
| 反傷流(R42:armor_reflect / block_reflect / **thorns 荊棘附魔**) | 反傷 | 受物理近戰擊中 → 反彈**「攻方完整物理輸出(連格擋前)= raw/block_factor」**(★R42 解耦護甲/盾牆/重盾/格擋,龜也反得動)× 比例:重甲反震 0.06(被動)+ 盾反 0.10(耗體 10·力竭不計)+ 荊棘附魔(盔/胸/手/靴/盾·1%/靈魂階·max 25%)→ max **0.41 of raw**。物理限定(元素穿透不反=反傷流剋星)、player-only(無環)、**不夾**(物理敵 raw 上限小 → 永不一擊反殺) |
| 重壓 armor_stagger | 防守控場 | 受近戰物理擊中 22% 震開攻擊者(stagger turns:2 → 撐過回合末 tick,對敵下次出手生效) |
| 石膚反擊 shield_recoil(變化 100·R118) | 防守控場 | **作用中護膚盾**(`magic.active_shield>0`·橡木/石/鐵膚)時受近戰物理擊中 30% 震開攻方(stagger·`apply_control` 非遞迴);把被動 flesh 接上主動反噬。搭負重(敵 −20% 命中·見法術)=「物理操縱防禦控者」 |
| 雙手重盾被動減傷 great_shield mitigation(R41) | 減傷 | 裝雙手重盾(`great_shield`)→ 受物理 ×(1−mitigation)(iron→daedric 5~8%·crusaders_ward 10%);套 `_shield_wall_factor` **後**乘性疊加、僅物理、獸形不套;重盾占雙手·普攻走盾擊(`bash_damage`·練 block) |
| 生生不息 combat_regen | 續航 | 戰鬥中每回合末自癒 8(is_alive 守 → 不復活本回合被擊殺者) |
| 身輕如燕 evasion_bonus | 命中(扣敵命中) | 多源相加 0.02~0.05,★硬夾 EVASION_BONUS_CAP=0.15 |
| 盾陣/盾擊踉蹌 | 減傷/控場 | block_hit_penalty0.25;riposte stagger0.35 |
| 懾意/懾心術/懾魂 fear_on_hit | 控場 | illusion 50/75/100:命中懼意,chance 相加夾30%、turns 取最(最長3);出手觸發(每回合一次);**solo BOSS 免疫** |
| 不竭之軀 fatigue_cost_bonus | 續航 | 攻擊耗體×0.90 |

### 經濟/探索/社交(非戰鬥;多源取最高或相加)
塗毒次數 poison_charge_bonus(相加最高+5)、議價 merchant_bonus(相加0.03~0.12)、補貨×1.5、撬鎖下限 0.50(取最高)、巧手不折0.50、機關下限0.30、威嚇下限0.40、必定說服(每NPC一次)、淬火宗師+1、淬鍊省料0.50、野修下限90、戰場鐵匠(每回合自修武/甲各+2)、逃命+0.15、旅速−0.10、偵查門檻75→50/scout_floor50。

---

## ④ 戰鬥內臨時 / 法術(active_effects;★不入存檔 R03)

### 自我增益
| 效果 | kind | 數值 | 疊加 |
|---|---|---|---|
| 再生 HoT(renewal/regen_aura/ench_regen/steadfast) | 續航回復 | renewal +10×4、aura +8×4(全同伴)、steadfast 4×3 | 各一條可同掛;ench_regen/steadfast 各 source 去重;tick 為 flat 不乘 power |
| 變化護盾(oak/stone/iron-flesh、ward_ally) | 減傷 | round(mag×power):30/55/75、ward_ally40;turns5 | ★聚合相加進 armor_rating;**只擋物理** |
| 溢盾 overheal_ward | 減傷 | 溢治60%轉盾,夾生命×0.5,turns4 | source去重夾cap |
| 秘術結界 ward/greater/absorb | 抗性吸收池 | 40/90/70(absorb0.5回魔);turns5 可耗盡池 | 重施去重;**只吃法術/元素傷** |
| 奧術灌注(flame/frost/storm_blade) | 傷害 | round(8×power)元素傷/命中;turns5 | 🔴多元素並掛逐一加;加在 solo 夾限**之前**;獸形/束縛不吃 |
| 共鳴一擊 resonance | 傷害 | 半數實際法傷+引燃dot;turns2 | 🔴重施去重;偷襲不放大、solo受夾 |
| 束縛兵刃 bound_weapon | 武器替換 | 基礎傷14(magic),不乘power;turns6 | 重施去重;取代裝備(不吃淬鍊/附魔/塗毒/副手) |
| 召喚 summon(R105 成長)| 召喚物 HP+傷害 | **scale=min(SUMMON_POWER_CAP=2.0, _power(conjuration)×(1+boon))×力竭**;HP=基礎×0.85~1.15×scale×(1+hp_bonus)·傷害 raw×`summon_power`(=scale) | 🔴R105:召喚物**隨召喚主 conjuration 技能/法術威力/智力成長**(推翻舊「不吃_power」)·初始弱靠 bestiary 基礎·CAP 防暴衝·傷害走 resolve_attack **不吃玩家偷襲**·角色定位(魔人/魔靈伴坦克·火冰雷法師玻璃大砲)+ 元素 on_hit(火 dot/冰 benumb/雷 stagger)+ 坦克嘲諷(TAUNT_AGGRO 0.6);加入 battle["allies"](R08)|
| 復生 reanimate | 召喚物 HP | 基礎×0.85~1.15×(1+boon)×(1+hp_bonus)×力竭×0.6 | 🔴**不設 summon_power**(傷害不縮放·刻意·R106 Phase C「亡者統御」里程碑才吃成長);喚敵屍為限時盟 |
| 召喚角色擴展(R106 Phase A)| 召喚物行為 | healer 施 heal_other(power 0.8)·terror on_hit fear/weaken·束縛兵刃 archetype | 支援召喚 `summoned_healer` 走 `magic.summon_support_act`(讀 bestiary spells·pool 含玩家·門檻 0.55/冷卻 2)治療全隊;控場召喚 `summoned_terror` on_hit(fear/weaken·apply_control solo/去重);**束縛兵刃 archetype 差異化**(bound active_effect `archetype`:釘錘 stagger·巨劍 mag20·斧 pen 對元素略過·甲=shield60);皆 innate·不吃玩家偷襲 |
| 凝神 restore_fatigue | 資源(瞬時) | +40體力,不乘power |
| 奧術連鎖 cascade / 戰地搶救 triage / 法力回擊 | 見③ | — | 戰鬥邊界清空 |
| **同伴戰力(Tier 2 類玩家)** | 生成時導出 | 傷=`attack_damage(裝備傷+flat淬鍊, 同伴武器技能≤80, 同伴力量)`·甲=`worn_armor_base(裝備甲, 同伴護甲技能)`+flat淬鍊 | 🔴走**共用玩家公式**·生成時烘焙進 Creature(非新戰鬥軸);無裝→模板數(byte-identical)·武器傷不設天花板(技能≤80 為紅線閘·守單同伴孤立牆)·**附魔完全比照玩家**(`_gear_weapon_item` 派發·charges 共用玩家池);裝上裝備移出背包(sink) |
| **同伴戰術傾向**(功能性·非數值)| 目標/仇恨 | bulwark→自施 taunt(吸火)·skirmisher→集火最低血敵·vanguard→隨機 | 羈絆階解鎖·永久(`companion_build`)·**零新戰鬥數值**(複用既有 taunt/目標選擇)·召喚物不適用 |

### 永久/隨階級(公會福利,取最強 _best_perk)
| 福利 | kind | 數值 |
|---|---|---|
| 達貢之佑 conjure_boon | 召喚增益 | HP×(1+per_rank0.1×階,cap0.6)+駐留 |
| 聖光眷顧 restoration_boon | 續航回復 | 治療×(1+0.07×階,cap0.35),乘在溢盾前 |

### 全域施法調變
| 效果 | kind | 數值 |
|---|---|---|
| 力竭法效折減 cast_fatigue_power_factor | 傷害/續航/減傷 | 1.0−(1−fatigue_ratio)×0.25:滿體×1.0、空體×0.75;乘進 _power(damage/heal/shield/ward/imbue/empower/summon HP 一致削) |

---

## ⑤ 其餘永久層:星座 / 種族 / 陣營經濟 / 坐騎 / 精神飽滿

### 出生星座(建檔加屬性,夾[1,CAP];★power 每日一次走 power_last_day)
| 星座 | 加成 |
|---|---|
| 戰士 | str+5 耐+5 ‖ 法師 int+5 magicka+50 ‖ 竊賊 敏+5 速+5 幸+5 ‖ 淑女 魅+10 耐+5 ‖ 駿馬 速+10 |
| 領主 | 耐+5、**火抗−25▼**、每日 heal 60 ‖ 學徒 int+5 magicka+100、**magic抗−50▼** ‖ 巨魔像 magicka+150、被動 spell_absorption(魔力不自然回復▼) |
| 儀式 | 魅+5、每日 heal80+清dot ‖ 戀人 敏+10、每日麻痺3回(solo免疫) ‖ 陰影 每日必定脫戰 ‖ 塔 幸+5、每日下次撬鎖必成 ‖ 蛇 每日對敵毒8×4+汲25HP |

### 種族(屬性/技能/抗性各自相加;★argonian 毒抗100=免疫)
高精靈(int/will+10、magicka+100、毀滅+10…、疾抗75)、木精靈(敏/速+10、弓+10、疾/毒抗75)、暗精靈(速+10、毀滅+10、火抗75)、諾德(力/耐+10、鈍+10、霜抗50)、帝國(魅+10、辯/商+10)、布萊頓(int/will+10、復原+10、magicka+50、magic抗25〔R65 下修〕)、紅衛(力/耐+10、刃+10、疾/毒抗75)、獸人(力/耐+10、鈍/重甲+10、magic抗25)、亞龍(速+10、安全+10、★毒抗100/疾抗75)、虎人(敏+10、徒手+10)。

### 陣營經濟 perk(取最強同類,非會員=0,隨階級成長)
戰士團軍械庫折扣(買武器/護甲 0.05/階,cap0.35)、法師團法術折扣(0.08,cap0.45)、盜賊團銷贓(0.07,cap0.4)、黑暗兄弟會洗白賞金(0.12,cap0.7)、戰友團傭兵折扣(0.08,cap0.5)。

### 坐騎(乘騎中被動;★衝鋒不走 sneak_mult)
| 效果 | 數值 |
|---|---|
| 旅速 | 戰馬+0.10/獵馬+0.18/法駒+0.12 ‖ 鞍袋負重 戰馬+80/獵馬+30/法駒+40(非資源不recompute R25) |
| 獵馬規避遭遇 0.35、開場騎射閃避0.15×3(獵馬+弓) | 法駒法術傷+20%(騎乘作戰) |
| 戰馬衝鋒踐踏 | mult_spear2.2、mount_dmg14;★不走sneak_mult,solo受MOUNTED_CHARGE_CAP0.45夾;改必跑sim(R25) |

### 精神飽滿 well_rested
技能 xp×1.25,持續24遊戲時(★R110:在有「舒適臥房」擴建的自家安睡→36時;**只延時長不動倍率**,巢穴/藏身處仍24);★只乘xp不寫base(R25),再休息=刷新不疊。

### 在地商誼 trade_pact(R110 房產擴建)
本省商人**買價**×0.95(省內布林不疊加;賣價不碰;插反套利地板前→恆不倒掛);藥草園=材料供給非增益(value cap 10·零XP)。

---

## ⑥ 藥水 / 消耗品(一次性,夾各自 max;★限時增益例外,見表末)

| 物品 | kind | 數值 |
|---|---|---|
| 治療藥水(固定) | 續航回復 | minor 25 / 普 50 |
| 魔力藥水(固定) | 續航回復 | minor 25 |
| 自製藥水 brew(煉金) | 續航回復 | round((eff_a+eff_b)/2×factor);factor=(0.6+煉金/100)×(1+potion_potency);kind∈heal/restore_magicka/★restore_fatigue(僅煉金可得) |
| ★限時增益藥水 brewb(煉金·R30) | **限時**強化(獨立層,非一次性) | 量=round((eff_a+eff_b)/2×factor),時長=round(2×factor) 小時;走獨立 `potion_attr_bonus/potion_skill_bonus/potion_resist` 層(聚合於 attr()/skill()/entity_resist(),**絕不寫 base**);kind:強化屬性 `fattr_*`/強化技能 `fskill_*`/抗元素 `resist_*`;**疊加=同(kind,param)取最強+取較晚到期,非相加**;**可釀池排除 strength+武器技能**(結構避刺客紅線,免 sim);每圈 `potion_buff.update` 清過期 |
| ★實用/幻術魔法限時自我增益 `char.spell_effects`(R104·**戰鬥外**) | **限時**社交/潛行/探索(獨立層·**無推導快取**·helper on-the-fly·絕不寫 base) | `魅惑 charm`(6h·說服/套話+0.12·化解衛兵/賞金+0.10·議價+0.08·偷竊得手+0.10 且失風賞金×0.7)/`隱形 invisibility`(3h·**入戰重獲偷襲先機**〔首擊仍受 SOLO_SNEAK 夾·**不秒 solo**〕·旅途遭遇×0.4·繞城門盤查/圍捕·**入戰即破**)/`羽落 feather`(6h·負重+50)/`偵知 detect_life`(6h·下場遭遇揭敵情+scouted·消耗)。疊加=同 kind 取較晚到期;每圈 `spellfx.update` 清過期。**旋鈕**:`spellfx.CHARM_*/INVIS_ENCOUNTER_FACTOR/FEATHER_CARRY_BONUS`(改必先問使用者) |
| ★九神祝福 `char.divine_blessing`(R107·**排他單槽限時**·非藥水=祭壇祈禱) | **限時**單神祝福(獨立層·attr/resist 走推導快取·功能面 getter on-the-fly·絕不寫 base) | **同時只能持有一位神的祝福,拜新壇即整包覆蓋**(單槽 dict 結構性保證);時長 `divines.BLESSING_HOURS=48`;祈禱附帶淨疾(diseases.purify);**德行閘**=惡名不高於名聲且本省無賞金,否則拒賜福。九神:阿卡托什 速度+10/蒂貝拉 個性+10/朱利安諾斯 智力+10/塔洛斯 力量+10(皆 `divine_attr_bonus`·recompute 資源)·阿爾凱 疾病抗+30(`divine_resist`)·凱娜瑞絲 旅行減項−0.10(travel 鏈·floor 0.5)·瑪拉 cast 治療+15%(與騎士團 restoration_boon 相加)·斯丹達爾 格擋姿態卸力+0.10(R137 遷入 `_guard_stance_factor`·原掛手動格擋已移除·總夾 0.60)·澤尼薩爾 買價×0.90(只買價·反套利地板恆守)。每圈 `divines.update` 清過期。**旋鈕**:`divines.BLESSINGS/BLESSING_HOURS/BLOCK_FLOOR`(改必先問使用者;塔洛斯力量有 R92 sim 先例·sim fixture 空槽 → byte-identical)。**R115 神之選民深線**:各神祭壇另接一條**永久誓福**試煉(專屬 d5 boss+地城·結局授永久誓福·走通用 `boon_*` 層〔非限時·比照戴德拉誓福〕·**依各神神格按原典賜加成、守 R45 紅線無 sneak/武器技**)—— 阿卡托什「時龍之契」end+10/will+6/魔抗+15/magicka+20·塔洛斯「人皇之佑」str+10/end+6/heavy_armor+10/魔抗+10·阿爾凱「輪迴之佑」end+10/will+6/restoration+10/抗疫+25·朱利安諾斯「睿智之佑」int+10/will+6/mysticism+10/魔抗+10/magicka+20·斯丹達爾「慈憫之佑」end+10/will+6/block+8/restoration+8/魔抗+10·澤尼薩爾「豐饒之佑」per+8/luck+8/mercantile+12/魔抗+10·凱娜瑞絲「天穹之佑」agi+10/speed+6/athletics+10/電抗+15·瑪拉「慈愛之佑」per+10/will+6/restoration+12/魔抗+10·蒂貝拉「美之佑」per+10/will+6/speechcraft+8/illusion+8/魔抗+10 |
| ★安撫 calm(R104·illusion·戰鬥控場·非上表增益層) | 敵方失能(走 `is_incapacitated`) | 走 `magic.apply_control("calm")`(敵 active_effects{kind:calm,turns})·**成功率 `formulas.calm_chance` 隨敵數非線性遞減**(1敵85%→4敵21%·CALM_*)·**solo boss 完全免疫**(非機率)·去重防延長·全敵 calm→「從容離去」免檢定脫戰 |
| 塗毒/毒藥(▼對敵) | 傷害/控場 | **五型**(R31):dot per_turn×(3+延長) / 麻痺 clamp(1+煉金//50,1..3) / **衰毒 weaken**(敵攻勢−10..35%) / **遲緩 slow**(先攻+命中−10..35%) / **懼毒 fear**(短暫失能 1..2 回);特殊毒型需里程碑解鎖(`poison_unlock`),否則退回 DoT;塗層 charges=poison_charges+里程碑,控制型(麻痺/懼)半量、遲緩−1;**麻痺/懼毒對 solo BOSS 免疫** |

---

## 🔴 餵進偷襲倍率 / 碰戰鬥紅線的增益(專節)

### sneak_mult 鏈(combat.py:352-357,**相乘**)
`base = sneak_attack_multiplier(sneak) × archetype_sneak_bonus × night_mother × (1+影刃0.50) × armor_sneak_mult_factor`

| 來源 | 數值 | 性質 |
|---|---|---|
| 武器流派 archetype_sneak_bonus | 匕首×1.6、弓×1.3、其餘×1.0 | 乘進鏈 |
| 夜母祝福 night_mother | ×(1+0.03×db_rank),聆聽者×1.18 | 乘進鏈 |
| 影刃·暗殺宗師 mult_bonus | ×1.5 | 乘進鏈核心(消費於 combat.py:355/738) |

### 三道煞車(缺一不可,守 R07/R15)
1. **>3 敵潛匿大減** — 群體規模反制;
2. **隱遁耗體** — vanish 須花一回合且受強敵死咬遞減;
3. **SOLO_SNEAK_DAMAGE_CAP_RATIO=0.40** — solo boss 開場單擊夾生命上限 40%(防偷襲秒王)。

### 「加在 dmg、於 solo 夾限之前」的元素/破甲(偷襲**不放大**、solo 受夾)
weapon_element 附魔、奧術灌注 weapon_imbue、共鳴一擊 resonance、武器流派 power(偷襲倍率**之前**算但不吃倍率)、deathmark 破甲(僅 follow-up,`not sneaking` 閘 → 開場永不受惠,最終 pen 夾0.85)。

### 結構性免疫紅線
- **獸形 sneak_attack=False**(main.run_battle 守門)→ 狼人 +str 巨幅近戰不碰偷襲倍率;
- **斯庫瑪/月糖/達貢之力**刻意不碰 strength/sneak/武傷倍率(R20)——但 str 仍經 attack_damage 放近戰**基礎傷**(與吸血同性質,非偷襲倍率);
- **麻痺 + 懼毒**(武器附魔/法術/塗毒):solo boss 完全免疫(R15/R31,防反鎖王;R31 補上塗毒命中路徑原缺的 solo gate);
- approach_bonus/prep_bonus 只動「搶開場頻率」,不放大倍率。

> 改任一上述常數 → **必跑 `PYTHONPATH=. python3 sim_assassin.py`**(守偷襲不秒 solo boss、群體反制、麻痺免疫紅線)。

---

## ▼ 減益小節(debuff;增益的鏡像)

### 對敵 debuff(戰鬥內臨時)
| debuff | kind | 數值 | 聚合 |
|---|---|---|---|
| 挫志 weaken(demoralize/衝擊餘波) | 削敵傷害 | demoralize ×0.6(4回);只乘怪 | 取最強(min,夾≥0.1),可dispel |
| 陣腳大亂 stagger | 降敵命中 | −0.30 命中(impact 35%觸發;**釘錘/戰錘 archetype 命中 20% 內建**·R41·`_ARCHETYPE_BUILTIN_STATUS`·solo boss 免疫) | binary,覆寫turns,可dispel |
| 持續傷 dot(ignite/poison_cloud/frost_nova/bleed) | 持續傷 | ignite 8+6×3、poison_cloud 6×4、frost_nova 16+4×2、bleed×3 | 各一條獨立;AoE每敵獨立dict(R17) |
| 麻痺 paralyze(mass/附魔) | 失能 | 群麻2回、附魔1回;is_incapacitated | 🔴solo免疫(R15);AoE獨立dict |
| 恐懼 fear(fear/rout/懾心) | 失能 | 2回不敢進攻 | 玩家可意志抵抗;可dispel;**solo BOSS 全路徑免疫(R31:法術/塗毒/里程碑)** |
| 擒魂 soul_trap(單/群) | 標記 | 4回;擊殺給對應充能靈魂石 | 不在 _DISPELLABLE |

### 對玩家自身懲罰(身分/星座代價)
吸血鬼火弱點(−10/階)、陽光灼傷、學徒座 magic−50、領主座 火−25、巨魔像魔力不回、斯庫瑪戒斷(屬性 −18/煉金 −18)、壁壘攻擊耗體×1.20、過載 cost×1.30、武器流派 recoil 自損、瞄準射蓄力/箭雨齊射 雙倍攻擊耗體。

---

## 🎓 畢業角色「疊滿」概覽(可同時掛多少永久層)

一個達貢化身(非吸血/狼人,純永久路線)畢業時的**永久增益層帳**:

| 層 | 屬性 | 技能 | 抗性 | 資源上限 |
|---|---|---|---|---|
| **達貢之力** | str+18 will+12 end+12 | dest+10 conj+8 | fire+60 | magicka+25 |
| **里程碑 fortify** | +4~+6/屬性(如 str+5) | +6~+10/技能 | magic+10~15、disease+25~30 | (經 attr 衍生) |
| **里程碑 passive_armor** | — | — | — | 護甲值 +4~20(多源相加) |
| **裝備附魔(飾品3槽+護甲)** | attr+5~7 | skill+8~12 | element+20~30%/件 | health/magicka+12~19 |
| **護甲套裝(1套)** | (dwarven end+10) | (leather/glass+15) | (ebony/dragonscale) | health+60/magicka+110 |
| **淬鍊** | — | — | — | 武+10傷、甲+5/件護甲值 |
| **種族(如布萊頓)** | int/will+10 | restoration+10 | magic+25(R65) | magicka+50 |
| **星座(如法師座)** | int+5 | — | — | magicka+50 |
| **陣營/坐騎/精神飽滿** | — | — | — | 旅速/負重/xp×1.25/經濟折扣 |

**全部獨立相加**(各層寫專屬 `*_bonus`,聚合於 attr()/skill()/entity_resist()/recompute_max_resources,**絕不寫回 base**)。

**若改走吸血/狼人路線**(與達貢可並存,彼此互斥於吸血↔狼人):
- 吸血 T3 再疊 str/speed/will+15、sneak/illusion+15、frost+30(但 fire−30 弱點,可被達貢 fire+60 抵成淨+30);
- 狼人變身則**整套裝備層被換成獸力**(str+42/血+160/獸甲4)——是換層不是加層。

**偷襲倍率上限**仍由三道煞車鎖死:無論疊多少元素/破甲/基礎傷,solo boss 開場單擊**永遠夾在生命上限 40%**,>3 敵潛匿大減,麻痺對 solo 免疫——畢業也打不破。
