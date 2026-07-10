# build.md — 流亡者 (tesrpg) 角色構築縱切盤點

> **這是「按 build 縱切」的參考視圖**:挑一條構築(刺客 / 弓手 …),從根到頂走過它能疊的**所有**增益層。
> 與 [BUFFS.md](BUFFS.md) **互補** —— BUFFS.md 按「**來源層橫切**」(全遊戲增益依層羅列),本檔按「**build 縱切**」(一條構築走完所有層、含分支取捨)。
> Single source of truth 仍是程式碼(`tesrpg/formulas.py`、`tesrpg/systems/*.py`)與資料(`tesrpg/data/*.json`);**數值有疑義以常數 / JSON / `run_all.py` 為準並順手更新本檔**。
> 紅線本體見 [handoff.md](handoff.md) §3(R07/R11/R15/R20/R21/R25)、增益總目錄見 [BUFFS.md](BUFFS.md)、設計理念見 [DESIGN.md](DESIGN.md)。
> 末次盤點:2026-06-18(潛行刺客 / 潛行弓手 / 純法師 / 純戰士四條縱切;**R41 雙手握法系統後**)。四段經多代理對抗審查核對(gather→verify→draft→critic)。**⚠ R41 變更**:鈍器 archetype 分流(釘錘 mace=控制 stagger / 斧 axe=破甲 0.30)、新增雙手武器(戰錘/戰斧·極攻)與雙手重盾(盾擊+被動減傷·極防)兩種握法、維蘇拉德轉 2H 戰斧(現吃破甲)、十字軍聖盾轉重盾——**舊版「本作無雙手機制」之審查結論已由 R41 取代**(現有 `two_handed`/`great_shield` 旗 + 三閘)。其餘核對:護甲淬鍊 int(Σ) ≈+30、skill_mult 不夾上限、可釀池僅 resist_magic、soul_trap 非 solo 免疫。

---

## 0. 通用骨架(所有物理 build 共用的三件事)

### 0a · 傷害公式(`formulas.attack_damage`)
```
傷害 = 武器基礎傷 × (0.5 + 武器技能/100) × (0.75 + strength/160) × roll(0.85~1.15) × 格擋減傷
```
- 武器技能 100 → ×1.5;strength 100 → ×1.375、+18(達貢)→ ×1.49。
- 命中(`formulas.hit_chance`):`0.50 + (武器技能−25)×0.006 + (agility−敵agi)×0.004 − 體力罰`,再 + 武速(快武器)/ 里程碑 hit / 瞄準射。
- 護甲減傷(`damage_after_armor`):遞減、最多擋 85%、`armor_pen` 先無視一比例護甲。

### 0b · 偷襲倍率鏈(潛行流核心;`combat.py` resolve_attack,**相乘**)
```
偷襲倍率 = (1 + sneak×0.03) × archetype_sneak_bonus × night_mother × (1 + 影刃0.5) × 護甲折扣
```
| 因子 | 值 | 來源 |
|---|---|---|
| `sneak_attack_multiplier` | sneak 50→×2.5、100→**×4.0**(`SNEAK_ATTACK_SCALE=0.03`) | 潛行技能 |
| `archetype_sneak_bonus` | **匕首 ×1.6**、**弓 ×1.3**、其餘 ×1.0 | 武器原型 |
| `night_mother` | ×(1+0.03×db階),聆聽者滿階 **×1.18** | 黑暗兄弟會 |
| 影刃 `sneak_mult_bonus` | ×(1+0.5)=**×1.5** | sneak_100 里程碑 |
| 護甲折扣 | 總重 ≤18 → **×1.0**;>18(重甲)→ 夾 [0.45,1.0] | ★穿輕甲才不打折 |

### 0c · 三道煞車(`sim_assassin.py` 守的紅線,任何疊滿都打不破)
1. **`SOLO_SNEAK_DAMAGE_CAP_RATIO=0.40`** — solo boss 開場單擊夾在其生命上限 40%(偷襲秒不掉王);
2. **群體規模反制** — >3 敵潛匿 / 隱遁機率陡降(`RESTEALTH_HORDE_PENALTY=0.40`);
3. **麻痺 / 懼毒對 solo boss 全路徑免疫**(R15/R31;防反鎖王)。
> 「加在 dmg、於 solo 夾**之前**」的層(元素附魔 / 武器流派 power / 塗毒 DoT)→ 偷襲**不放大**、solo 仍受夾。

---

## ① 潛行刺客(匕首 · 近戰爆發)

> 全遊戲**最高偷襲乘子**(匕首 ×1.6 + 雙持)+ 黑兄夜母;代價=近戰要潛近貼身、雙持不能格擋、最脆。`sim_assassin.py` 即以此 build 校準。

### 根:吃哪些數值
匕首用 **blade** 技能、archetype **dagger**(speed 1.4~1.5 → 命中 +、耗體低)。
**五圍序:sneak ≫ blade > strength ≈ agility > speed / endurance**。雙持副手匕首傷 ×`OFFHAND_DAMAGE_FACTOR=0.6` 折入每一擊。

### A · 通用加成(任何刺客都疊 · 全獨立相加)
| 層 | 內容 | 備註 |
|---|---|---|
| **身分:吸血鬼 T3** | ★**sneak+15**·**illusion+15**(唯一餵 sneak 的身分層)、str/speed/will+15、frost+30 | fire−30 弱點可被達貢 fire+60 抵成淨+30 |
| **身分:達貢之力** | str+18(放匕首基礎傷)、magicka+25、fire+60 | ★純永久無懲罰,與吸血並存 |
| **身分:斯庫瑪/月糖** | 斯庫瑪 speed/agility/**willpower**+8;月糖 speed/agility+5 | ★**不碰 sneak/str/武傷**(R20)→ 只命中/閃避/先攻 |
| ~~狼人~~ | ✗ 獸形脫整套裝備 + `sneak_attack=False` | 刺客不適用 |
| **裝備:雙匕首附魔** | 元素傷 +17~24(grand soul·myst50→100,無視物理甲、夾前;靈魂虹吸後 ~29)/ DoT / vampiric 回血(雙持 0.48)/ paralyze·soul_trap | **paralyze** solo 免疫;**soul_trap 對 solo 照常**(僅去重+充能) |
| **裝備:fortify 飾品(3 槽)** | `fortify_skill` blade ≈12(myst75)~15(myst100·grand soul,靈魂虹吸後 ~18)、agility +5~7、resource +12~19 | 餵 skill()/attr() 不回門檻(R21) |
| **裝備:★輕甲套裝** | 皮革→**sneak+15** / 玻璃→**acrobatics+15** | 且 W≤18 偷襲折扣 ×1.0 不打折 |
| **裝備:淬鍊** | 主匕 +10 傷(基礎上限;smithing 鋒銳 apex `temper_power` → +15) | ⚠ 雙持**副手淬鍊不套偷襲倍率**(R37 Finding,既有行為) |
| **裝備:神器** | 悲傷之刃(vampiric 50%)、魔銳茲之刃(shock+25)、骷髏鑰匙(security+20·撬鎖必成) | 悲傷之刃 `blade_of_woe`=黑兄掌門 |
| **種族/星座** | 紅衛(刃+10·力耐+10)、虎人(敏+10·潛行/徒手+)、亞龍(速+10·敏+5·★毒免疫)、暗精靈(速+10·火抗75);竊賊座 / **陰影座**(每日必脫戰)/ 蛇座(每日對敵毒) | |
| **★塗毒(R31 五型)** | ★★★ 偷襲+毒一起爆;武器塗**單一毒層**(主副手共用一份·命中即耗一格,非各塗),charges=poison_charges+里程碑 | 麻痺/懼 solo 免疫,主打群兵 |
| **限時藥水** | fortify **agility**、resist_magic(★無火/霜/雷抗藥) | ⚠ blade 等武器技能藥**無材料可釀**;可釀池僅 `fattr_agility`/`fattr_willpower`/`resist_magic`/`fskill_alchemy` |
| **公會/通用** | ★黑暗兄弟會(夜母 ×1.18·洗白賞金);blade_25 +2%命中、sneak_25 隱遁、scout 備戰 prep、精神飽滿 xp×1.25 | |

### B · 分支加成(二選一互斥)
**sneak 樹(命脈,純刺客全取左)**
| 階 | A(刺客向) | B |
|---|---|---|
| 50 | ★**致命烙印**(pen+0.35·**僅 follow-up**·`not sneaking` 閘·turns4·cd6·最終 pen 夾0.85) | 扒竊(mercantile+10) |
| 75 | **連環踏影**(隱遁免重複遞減→打王循環) | 無聲潛近(approach+0.10) |
| 100 | ★**影刃**(偷襲 ×1.5) | 踏影(vanish_floor 0.15) |

**blade 樹**
| 階 | A | B |
|---|---|---|
| 50 | 還擊架式(stagger 25%) | 鋒刃輕靈(命中+5%) |
| 75 | 劍勢如虹(傷+8%) | 輕劍捷影(agility+4) |
| 100 | 鋒芒畢露(命中+5%) | 迅捷連斬(傷+12%,自損 recoil+5%) |

**副軸流派(選一條當骨幹)**
- **純爆發**:影刃+夜母聆聽者+雙持 glass/daedric+魔銳茲之刃+塗毒+迅捷連斬 → 非 solo 精英開場秒殺。
- **隱遁循環打王**:連環踏影+踏影 → 隱遁重開偷襲,**無傷多刀**繞 40% 夾。
- **機動閃避**:輕甲/雜技 evasion(★硬夾 `EVASION_BONUS_CAP=0.15`)+ on_evade 反擊,扛貼身。
- **毒控群戰**:塗毒麻痺/懼/遲緩 + deathmark 清雜兵。

### C · 完全體疊滿 + 天花板
**亞龍/暗精靈 · 吸血 T3(或達貢)· 雙持 daedric+魔銳茲 · sneak100 影刃 · 黑兄聆聽者 · 輕甲玻璃套 · 塗毒**:
```
開場偷襲乘子 ≈ ×4.0(sneak100) × 1.6(匕首) × 1.18(聆聽者) × 1.5(影刃) × 1.0(輕甲) ≈ ×11.3
```
再疊夾前加法層(元素 ~24~29〔grand soul + 滿祕術靈魂虹吸〕 / blade power +12~20% / 塗毒 DoT / 副手 ×0.6)。🔴 但 solo boss 開場單擊**永遠夾 40%** → 打王靠隱遁循環多刀(見上 0c)。

---

## ② 潛行弓手(弓 · 遠程穩定)

> 安全、可風箏、穩定輸出;上限略低於刺客(弓 ×1.3 < 匕首 ×1.6、無雙持、無弓神器),但不必貼身。R40 後弓的散兵戰技改由 marksman 里程碑解鎖。

### 根:吃哪些數值
弓用 **marksman** 技能、archetype **bow**(★弓傷靠 marksman+strength,agility 只進命中)。
**五圍序:marksman > sneak > strength ≈ agility > speed / endurance**。

### A · 通用加成(任何弓手都疊)
| 層 | 內容 | 備註 |
|---|---|---|
| **身分:達貢之力** | str+18(放弓基礎傷)、fire+60、magicka+25 | ★弓手首選永久層、無懲罰 |
| **身分:吸血鬼 T3** | sneak+15(+illusion+15)、str/speed/will+15、frost+30 | 火−30 可被達貢抵 |
| **身分:斯庫瑪/月糖** | 斯庫瑪 speed/agility/willpower+8;月糖 speed/agility+5 | ★不碰 sneak/str/武傷 → 只命中/閃避/先攻 |
| ~~狼人~~ | ✗ 脫裝備、無偷襲 | 弓手不適用 |
| **裝備:弓附魔** | 元素傷火/霜/雷 +17~24(grand soul·myst50→100,無視物理甲、夾前;靈魂虹吸後 ~29)/ DoT / vampiric | **paralyze** solo 免疫;**soul_trap 對 solo 照常**(僅去重+充能);弓無 berserk(維蘇拉德 R41 為 2H 戰斧·archetype axe) |
| **裝備:fortify 飾品** | `fortify_skill` marksman ≈12~15、agility +5~7、resource +12~19 | 餵 skill()/attr() 不回門檻(R21) |
| **裝備:★輕甲套裝** | 皮革→**sneak+15** / 玻璃→**acrobatics+15** | 不破潛行 |
| **裝備:淬鍊** | 弓 +10 傷(基礎上限;smithing apex `temper_power` → +15) | |
| ⚠ **神器** | **全遊戲無專屬弓神器**(神器皆 sword/dagger/axe/staff/shield/amulet) | 靠自附魔元素弓 + fortify marksman 飾品補 |
| **種族/星座** | ★**木精靈**(弓+10·敏/速+10·疾毒抗75);紅衛/暗精靈;竊賊座 / 駿馬座 / **陰影座** / 蛇座 | |
| **★塗毒(R31)** | ★★ 箭上毒命中即觸發,配遠程+偷襲極強;麻痺/懼 solo 免疫 | |
| **限時藥水** | fortify **agility**、resist_magic(無元素抗藥) | ⚠ marksman 無材料可釀;可釀池僅 `fattr_agility`/`fattr_willpower`/`resist_magic`/`fskill_alchemy` |
| **坐騎/通用** | ★**獵馬**(騎射閃避0.15×3·規避遭遇0.35);marksman_25 +2%命中、sneak_25 隱遁、scout 備戰 prep、精神飽滿 | |

### B · 分支加成(二選一互斥)
**marksman 樹(R40 身份分流)**
| 階 | A | B |
|---|---|---|
| 25 | 弓術入門(+2% 命中,**單選**) | — |
| 50 | **散兵走位**(射後遁走·風箏) | **牽制射**(weaken 0.40/3t·控場) |
| 75 | **箭雨**(齊射全體 60% 傷害·倍耗體·永不偷襲·R136) | **瞄準射**(蓄力:命中+15/破甲+25/補傷+40%,額外耗體) |
| 100 | **獵手之眼**(對受控目標〔衰/踉/緩/凍麻/懼/麻痺〕弓傷+20%·R136) | **連珠箭**(命中後 20% 追加一箭·普通擊·R136) |
> 50/75 四格**全是主動戰技**(散兵/牽制/箭雨/瞄準·R40+R136);100 = 條件精準(獵手之眼:壓制→處決)vs 無條件手速(連珠箭)。舊 疾矢/穩準狠/穿甲箭 已於 R136 汰換(穿甲被 R127 pen-免疫終局廢)。

**副軸流派(選一條當骨幹)**
- **潛行刺客弓(爆發)**:sneak 致命烙印+影刃 + 夜母 + 吸血 sneak+15 + 瞄準射(75)+ 連珠箭(100)→ 精英開場秒殺+追射。
- **機動風箏弓**:散兵走位(50)+ 輕甲/雜技 evasion(夾 0.15)+ 獵馬騎射。
- **控場弓**:牽制射(50)+ 塗毒(遲緩/衰)疊控(打群兵)。
- **壓制射手(R136)**:牽制射(weaken 0.40 常駐)+ 獵手之眼(受控+20%)+ 瞄準射 → 「先壓制、再處決」;群戰改箭雨清場。

### C · 完全體疊滿 + 天花板
**木精靈 · 達貢化身 · 潛行刺客弓 · sneak100 影刃 · 黑兄聆聽者 · 元素弓 · 塗毒**:
```
開場偷襲乘子 ≈ ×4.0(sneak100) × 1.3(弓) × 1.18(聆聽者) × 1.5(影刃) × 1.0(輕甲) ≈ ×9.2
```
🔴 同三道煞車鎖死:solo boss 開場夾 40%、>3 敵反制、麻痺免疫 → 打王靠隱遁循環多箭。

---

## ③ 純法師(施法 · 六系)

> 與潛行流**完全不同的天花板邏輯**:法師傷害**不走偷襲倍率鏈**(不觸 `SOLO_SNEAK_DAMAGE_CAP_RATIO`),而是受 **magicka 池容量**(智力決定)、**控制法術對 solo boss 全免疫**、與**力竭法效折減**三道天花板所限。「畢業」靠把六系技能買到上限 + 疊魔力池 + 法袍省體續航。`狼人不相容`(獸形脫整套裝備、無法施法,與法師核心衝突)。

### 根:吃哪些數值
法師五圍:**magicka 池=智力**(`formulas.max_magicka(int, magicka_bonus) = int×2 + magicka_bonus`,`formulas.py:58-60`;遊戲生效上限再加升級 res + 裝備 fortify + 達貢層,`stats.py:75-77`)**+ R63 智力第二段=法術威力**(`intelligence_spell_potency`:int>100 漸近 +25%·乘進 `magic._power`);**回魔/抗控/施法續航=意志**(戰鬥每回合回魔〔整數頂 5〕、休息回魔倍率〔R63 漸近 3.2〕、抗恐懼/麻痺〔R63 漸近 0.90〕)**+ R63 意志第二段=省魔**(`willpower_cost_factor`:wil>115 漸近 −15%·乘進 `effective_cost`·`max(1)` 地板);**法術威力基底 / 魔耗=各「學派技能」**(六系各自獨立)。**R63:智力/意志高屬性過 200 仍漸進有意義(趨近永不抵達)。**
**五圍序:intelligence(魔力池)≈ 學派技能 > willpower(回魔/抗控)> endurance/speed**。

施法**威力鏈**(`magic._power`,`magic.py:46-49`,**相加**入括號再整體相乘):
```
power = (0.7 + 學派技能/150 + Σspell_power_bonus(同學派,SUM) + cascade_power) × cast_fatigue_power_factor [× 騎乘加成]
```
- 學派技能 100 → +0.667;範圍約 ×0.7~×1.37。`heal` 另乘 `(1+restoration_boon)` 公會層;`shield/ward/summon HP/imbue` 皆乘同 power。
- 里程碑加成是 **`spell_power_bonus`**(`mastery.py:268-270`,同學派多節點 **SUM 相加、不取最**),**加進**括號內(非相乘);跨學派不互通(getter 以 school 過濾)。

施法**成本鏈**(`magic.effective_cost`,`magic.py:37-43`,技能折扣 ×**相乘**里程碑倍率):
```
effective_cost = base × (1 − min(0.4, 學派技能/250)) × Π spell_cost_factor(同學派)
```
- 技能折扣最多省 40%;`spell_cost_factor`(`mastery.py:273-279`)同學派多 cost_factor **連乘**(`f *= o["cost_factor"]`)。⚠ **法袍不參與魔耗鏈**——法袍只折「施法體力」(`spell_fatigue_cost` 的 `cast_fatigue_factor`,`magic.py:60`)、只抬魔力上限,**不**乘魔耗。

### A · 通用加成(任何法師都疊)
| 層 | 內容 | 備註 |
|---|---|---|
| **核心數值** | 智力↑→魔力池(×2)+R63 法術威力;意志↑→回魔三條(`magicka_regen_combat`/`rest_factor`/`mind_resist`)+R63 省魔(>115)+**R65 魔抗**(過40漸近+25·減火/霜/雷);學派技能↑→威力 +、魔耗 − | 種族/星座加 int/will 直接吃滿;★**R65 大法師套裝 magic抗+25** |
| **身分:達貢之力** | ★純永久無懲罰:magicka+25(`dagon_magic_bonus` 獨立疊加層)、str+18、fire+60 | 法師首選永久層,與吸血並存 |
| **身分:吸血鬼 T3** | str/speed/will+15(★will+15 吃滿回魔三條)、frost+30 | fire−30 弱點可被達貢 fire+60 抵成淨 +30 |
| ~~狼人~~ | ✗ **不相容**:獸形脫整套裝備 + 無法施法 | 法師絕不取 |
| **裝備:法袍套裝**(四件同材質,盾不計) | 學徒布袍 magicka+40·施法省體 ×0.80 / 大法師 magicka+70·★施法省體 ×0.65 / 龍祭司 ★magicka+110(全遊戲最高·但**無施法折扣**) | `armor_sets.json:9-10,13`;法袍互斥、佔胸頭手腳四槽 |
| **裝備:法袍件附魔** | 胸/靴 `armor_fortify magicka`(學徒 +15/+10、大法師 +25/+15、龍祭司 +40/+25);兜帽/手套 `fortify_skill destruction/alteration`(學徒 +6、大法師 +10、龍祭司毀滅兜帽 +20) | `armor.json:307-331`;改 equipped 後必 recompute(R05) |
| **裝備:自附魔飾品(3 槽)** | `fortify_resource magicka`(soul5·myst100 ≈ 22)、`fortify_attribute int/will`(★僅飾品可附 ≈ 9)、`fortify_skill 學派`(≈ 15)、`resist`(**R66**:大魂飾單元素 ≈ 22%·魔抗 ≈ 11%·soul^0.7 非線性) | `enchanting.py`;餵 skill()/attr() 不回門檻(R21) |
| **裝備:神器(法杖)** | 魔典·哲思之卷(amulet)conj+15;馬格努斯之杖(法師公會掌門)、法力法杖(命中回魔 +8,`on_hit_self`)、元素法杖 | ⚠ 法杖 `weapon_element` 是**近戰命中元素傷**,非 spell power;本遊戲**無裝備直接加 spell power 的物品**(只能經 fortify_skill 抬學派技能間接放大) |
| **裝備:十字軍神器** | 護心(fire+50%·胸甲槽→排斥法袍套裝)、聖盾(magic+30%·盾槽不計套裝→可與法袍並存) | `armor.json:332-333` |
| **星座(建檔一次性·互斥)** | ★巨魔像 magicka+150+法術吸收(▼代價見下)/ 學徒 magicka+100(▼magic 抗−50)/ 法師 int+5·magicka+50(★無痛)/ 領主·儀式(每日自療 power) | `birthsigns.json` |
| **種族(建檔寫 base)** | ★阿爾特默 int/will+10·magicka+100·六系 skill_bonuses(dest+10·alt/conj/illu/myst/鍊+5,最強通才;▼str/end−10)/ 布萊頓 int/will+10·magicka+50·★magic 抗+25(R65 下修)/ 丹莫 dest+10·★fire+75 | `races.json` `skill_bonuses` |
| **法師公會 / 精神飽滿** | 法師公會 `spell_discount`(折**買法書價** cap 0.45,非魔耗)+ 每省守一學派·保底 9 道法書(廣度);精神飽滿各學派練功 xp×1.25 | `factions.py:145`;經濟/廣度層,非數值 buff |
| **消耗品:回復** | `restore_magicka`(商店 minor +25 / 自釀,夾 max_magicka)、`restore_fatigue`(回體續航);可釀池 ×`potion_potency`(煉金 75/100 ≤+0.35)放大 | `items.json`/`alchemy.py:184-188` |
| **消耗品:限時增益** | ⚠ 智力/魔法學派強化藥**無材料可釀**(`ingredients.json` 無 `fattr_intelligence`/`fskill_<學派>`);法師可釀僅 `fattr_willpower`(回魔/抗控)、`resist_magic`、`fattr_agility`;走獨立 `potion_*` 層(R30,同 kind 取最強+取較晚到期非相加) | `alchemy.py:176-183`;可釀範圍純由材料資料決定、無 code 白名單 |
| **消耗品:自我增益法術** | 變化護盾 oak/stone/ironflesh(armor_rating 30/55/75×power,擋物理)、秘術結界 ward/greater/spell_absorb(吸法術·可耗盡)、奧術灌注 flame/frost/storm_blade(近戰元素傷)、束縛兵刃、再生 HoT、凝神回體 | `magic.py:221-254`;active_effects ★不入存檔(R03) |

### B · 分支加成(六系里程碑二選一互斥;25 系列為單選自動授予=通用基底)
> 每系 25 門檻 = 單選 `*_basics`(全 `cost_factor 0.92`,省魔 8%,通用基底);50/75/100 為**二選一互斥**,同系常須在「省魔(cost 0.85)vs 增幅(power_bonus)vs 被動護甲」間取捨。

**destruction 樹(純輸出)**
| 階 | A | B |
|---|---|---|
| 50 | 凝神聚法(int+4·抬魔池) | 共鳴一擊(戰法師:傷害咒後下一近戰灌半法傷+DoT,`magic.py:188-197`) |
| 75 | 省魔催動(毀滅 cost ×0.85) | 法力回擊(近戰命中回魔 +4) |
| 100 | ★過載(power +0.20·**▼cost ×1.30**·連帶更耗體) | 衝擊餘波(命中 35% 踉蹌·**solo 免疫**) |

**alteration 樹(護盾/戰法師之刃)**
| 階 | A | B |
|---|---|---|
| 50 | 變化術法效力(power +0.10) | 省魔護持(cost ×0.85) |
| 75 | 術法增幅(power +0.15) | 石膚(被動護甲 +20) |
| 100 | 術法精純(power +0.15·與 75 相加) | 魔皮(被動護甲 +14·與石膚相加) |

**restoration 樹(治療輔助)**
| 階 | A | B |
|---|---|---|
| 50 | 戰地搶救(同伴 <30% 治療近乎免費) | 潔淨之軀(疾病抗 +30) |
| 75 | 聖光·溢盾(超治轉臨時護盾·夾自家 ≤max_health×0.5) | 不屈祝禱(<25% 觸 regen 4×3) |
| 100 | 聖療登峰(治療 power +0.20) | 生生不息(每回合自癒 8·is_alive 守不復活死人) |

**conjuration 樹(召喚流)**
| 階 | A | B |
|---|---|---|
| 50 | 省魔召喚(cost ×0.85) | 護體召喚初窺(被動護甲 +8) |
| 75 | 護體召喚(被動護甲 +15) | 召喚精研(召喚技能 +8→召喚物更強+省魔) |
| 100 | 雙重召喚(多召 1 隻·HP×0.6) | 束縛兵刃(召喚物 HP+25%·多駐 1 回合) |

**illusion 樹(控場·懾心)**
| 階 | A | B |
|---|---|---|
| 50 | 省魔幻術(cost ×0.85) | 懾意初窺(命中 10% 施懼·**solo 免疫**) |
| 75 | 魅惑交易(議價 +0.12) | 懾心術(命中 20% 施懼) |
| 100 | 操心駕輕(cost ×0.85) | 懾魂奪魄(命中 15%·三源 chance SUM 夾 0.30) |

**mysticism 樹(結界·法師心流·附魔)**
| 階 | A | B |
|---|---|---|
| 50 | 省魔秘法(cost ×0.85) | 結界凝練(結界吸收 power +0.10) |
| 75 | ★奧術連鎖(連發 +8% power·−12% 體/層·疊 2 層) | 奧術專精(秘術法術威力 +15%·強化傷害/結界〔R119〕) |
| 100 | 靈魂虹吸(★附魔強度 ×1.20·放大全自附魔) | ★秘蝕(破抗·傷害法術命中削目標魔抗 −3/層·夾 −15·輔助全傷害魔法〔R120〕) |

**副軸流派(選一條當骨幹)**
- **純輸出毀滅**:阿爾特默/丹莫 + dest 全取(凝神聚法→省魔催動→過載 power+0.20)+ 元素弱點種族/星座 + 力竭管控(滿體才打滿威力)。
- **召喚流**:conj 精研+雙重召喚/束縛兵刃 + 達貢之佑(神話黎明會員 summon HP×(1+0.1×階 cap 0.6))+ 護體召喚自護;前排靠召喚物,法師遠抽。
- **戰法師武器灌注**:alteration 灌注 flame/frost/storm_blade + 共鳴一擊(dest_50)+ 法力回擊回魔;近戰每擊吃元素傷(★加在 solo 夾**之前**、偷襲不放大)。
- **治療輔助**:resto 戰地搶救+溢盾/生生不息 + 聖光眷顧(九神騎士團 heal×(1+0.07×階 cap 0.35))+ 結界硬扛;隊友/召喚物續航。
- **控場幻術·秘術結界**:illusion 懾心/懾魂(命中施懼)+ 秘術 ward/spell_absorb 吸法術 + 奧術連鎖連發增幅;⚠ 懼/麻痺對 solo boss **全免疫**,控場只對群兵有效。

### C · 完全體疊滿 + 天花板
**阿爾特默 · 巨魔像座 · 大法師法袍套(magicka+70·施法 ×0.65)· 達貢之力 · 六系里程碑各取一支**:
```
魔力池 ≈ int×2 + 250(altmer+100 + 巨魔像+150) + 法袍/附魔 fortify + 達貢+25
施法威力(滿體)≈ 0.7 + 100/150 + Σpower_bonus(同學派) + cascade(≤+0.16)  ← 各學派各自吃自系增幅
施法成本 ≈ base ×(1−0.4)× Π cost_factor(如 dest_basics 0.92 × efficient 0.85 = 0.782)
施法體力 ≈ … × 0.65(法袍)× cascade_fatigue(≤−24%)   ← 法袍只折體力、不折魔耗
```
🔴 **三道天花板(與刺客/弓手紅線「不同源」)**：
1. **控制法術對 solo boss 全路徑免疫**(`magic.py:258,307`,`_is_solo` 守 fear/rout/mass_paralysis;impact stagger 同免疫)→ 對單體 BOSS **只能靠傷害 + weaken 削弱 + 護盾/結界硬扛**,不能反鎖王(同 R31/R34 紅線,但路徑在法術側)。
2. **magicka 池硬限**:傷害**不走偷襲倍率**(不觸 `SOLO_SNEAK_DAMAGE_CAP_RATIO` 40% 夾),但每道法術扣魔→池見底即啞火;★巨魔像 `atronach` **▼代價:魔力不自然回復**(休息與戰鬥兩條回魔路徑皆 gate 掉,`main.py:267,906`)→ 只能靠法術吸收 / 喝藥補魔;想保回魔則改學徒(▼magic 抗−50)或法師/布萊頓座。
3. **力竭法效折減**(`cast_fatigue_power_factor`,`formulas.py:288-294`):滿體 ×1.0、空體 ×0.75,統一削 damage/heal/shield/ward/imbue/summon HP → 法師需先回體才打滿威力。

→ **法師上限不靠「乘子爆發」而靠「池深 + 續航 + 廣譜威力」**;與潛行流共享「打 solo boss 畢業也鎖死」的結論,但鎖的是**控制免疫 + 魔力池**,而非偷襲 40% 夾。

---

## ④ 純戰士(重甲近戰 · 刀劍/鈍器/盾反)

> 與潛行流**天花板邏輯完全不同**:戰士近戰**不走偷襲倍率鏈**(`sneak_mult` 只在 `sneaking` 分支套用,`combat.py`),故對 solo boss **不觸 `SOLO_SNEAK_DAMAGE_CAP_RATIO=0.40` 開場一擊夾**。代價=沒有「一刀爆發」軟天花板可繞,輸出受 **85% 護甲遞減** + **體力經濟**兩道機制所限;靠**持續輸出 + 坦度**而非偷襲秒殺。`狼人換層不相容`(獸形脫整套重甲/盾/附魔/淬鍊/格擋,以野獸血量換掉所有裝備坦度)。

### 根:吃哪些數值
戰士五圍核心:**strength**(`str_mult = 0.75 + strength/160`,放近戰基礎傷;另抬負重、體力上限)、**endurance**(血量基底 `endurance×2` + 體力上限)。技能:**blade 或 blunt**(`skill_mult = 0.5 + 武器技能/100`,0→×0.5、100→×1.5,並抬命中門檻)、**block**(格擋減傷 `block_damage_factor` 0→×0.9、100→×0.4 + 命中懲罰)、**heavy_armor**(放大穿戴護甲值 `worn × (0.5 + heavy_armor/100)`)。
完整傷害鏈(`formulas.attack_damage:317-326`):
```
傷害 = 武器基礎傷 × (0.5 + 武器技能/100) × (0.75 + strength/160) × roll(0.85~1.15) × 格擋減傷
```
- strength 100 → ×1.375、+18(達貢)→ ×1.49;武器技能 100 → ×1.5(base;fortify_skill 可推過,見 §C 非對稱夾限)。
- 命中(`hit_chance:301-314`):`0.50 + (武器技能−25)×0.006 + (agility−敵agi)×0.004 − 體力罰 − 格擋罰`,再 + 武速修正(快武器 +、鈍器 speed 0.75 → −0.025)。
- **體力上限** = str+willpower+agility+endurance(`formulas.py:63-64`);戰士 str/end 雙高 → 體力池天然厚,撐連續攻擊/格擋/盾牆。

**五圍序:strength ≈ 武器技能 > endurance > heavy_armor ≈ block > agility/willpower**。

> 🔴 **天花板與潛行流不同**:① 戰士非潛行 → 攻擊 `sneaking=False`,**不乘偷襲倍率、不觸 40% 開場夾**(`combat.py:479` 該夾只在 `sneaking and _is_solo` 觸發);也不走衝鋒夾。對 solo boss **無單擊軟上限**。② 實際天花板純由 **護甲遞減(最多擋 85%,`damage_after_armor:344-351`,至少 1 傷)** 與 **體力經濟(盾牆 6/回合、格擋 4/次、盾反 6/次、壁壘攻擊耗體 ×1.2)** 構成——力竭即攻防雙弱。

### A · 通用加成(任何戰士都疊 · 全獨立相加)
| 層 | 內容 | 備註 |
|---|---|---|
| **核心數值** | strength↑→近戰基礎傷(`str_mult`)+ 負重 + 體力;endurance↑→血量 + 體力;武器技能↑→傷害 + 命中;heavy_armor↑→放大護甲值;block↑→格擋減傷(0.9→0.4)。皆走 base 成長,里程碑/裝備另疊獨立層 | `attr()/skill()` 八層全 SUM(`character.py:209-221`),無 MAX 遮蔽 |
| **身分:達貢之力** | ★str+18(放近戰基礎傷)·will+12·end+12·fire+60·magicka+25·destruction+10·conjuration+8(後三項法系殘力,純戰士不取用) | ★純永久無懲罰、無 upkeep,**戰士最划算的永久層**(`dagon_boon.py:16-19`);與吸血並存 |
| **身分:吸血鬼(階級3「夜主」MAX_STAGE)** | str/speed/will**+15**(★str+15 放近戰傷·每階 +5)·frost+30·disease 免疫·sneak/illusion+15(對戰士無益) | ⚠ **三重代價**:fire−30 弱點(`vampirism.py:90-91`)·日照灼傷 1.5/小時/階(階3=4.5/h)·階級≥2 被商家拒往(需進食);轉化後出生星座每日之力被 `vampiric_drain` 取代(領主座自療失效) |
| ~~狼人~~ | ✗ **換層非加層**:獸形 str 25→42·血+80→160·獸甲固定 4,但**脫去整套重甲/盾/附魔/淬鍊/格擋/塗毒**(`lycanthropy.py:201-206`,`combat.py:208-210`) | 對「重甲盾反 bruiser」結構衝突;與吸血互斥(disease 免疫) |
| **身分:斯庫瑪/月糖** | 斯庫瑪 speed/agility/willpower+8;月糖 speed/agility+5 | ⚠ **絕不碰 strength/sneak/武傷**(R20)→ 對戰士近戰**傷害零增益**,只命中/閃避/先攻 |
| **裝備:重甲套裝**(四件同材質 helmet/cuirass/gauntlets/boots,**盾不計**) | 鐵 health+15 / 鋼 health+25 / ★魔族 health+60(最高生命套)/ 矮人 endurance+10(唯一給屬性)/ 黑檀 magic 抗+15% / 龍鱗 fire 抗+25% | `armor_sets.json`;盾在 `ARMOR_SLOTS` 非 `SET_SLOTS`(`inventory.py:19`)→ 可掛神器盾不破套 |
| **裝備:護甲本體** | 穿戴件 `worn × (0.5 + heavy_armor/100)`;最高材質單件:魔族胸甲 30·盔 17·護手 12·靴 13·魔族盾 15;十字軍護心 32(火抗+50%)。重甲滿級 → worn 乘子 ×1.5 | `armor.json`;`combat.py:204-221 _armor_rating` |
| **裝備:武器淬鍊** | 主手武器 +2 傷/級;基礎上限 `min(5, smithing//20)` → +10;含鋒銳里程碑 `temper_power` ×(1+0.25)、淬火宗師 cap+1 → apex **+15 傷** | ⚠ 雙持**副手淬鍊不套倍率**(既有行為);加進 weapon_damage 吃進全攻擊鏈 |
| **裝備:護甲淬鍊** | 穿戴各甲件淬鍊**等級總和** ×(1+temper_power),**一次取整**:`int(Σlvl × (1+power))`;apex(cap6·power0.25·4 件)= int(24×1.25)=**+30 護甲值**(非逐件取整相加) | `smithing.py:178-184`;卸下不計 |
| **裝備:★fortify str/技能 附魔(僅飾品,3 槽 amulet+ring1+ring2)** | ★**fortify_attribute strength 唯一靠飾品**(soul5·myst100 ≈ +9/件);`fortify_skill` blade/blunt/block/heavy_armor ≈ +15/件;`fortify_resource health` ≈ +22/件;`resist` **R66**:單元素 ≈ +22%/件·魔抗 ≈ +11%/件(soul^0.7 非線性) | **護甲刻意排除 attr**(`enchanting.py:22-23` ARMOR_KINDS·僅飾品 jewelry_magnitude 89-94 才有 attr);餵 skill()/attr() 不回門檻(R21);★**無藥可釀**(見下) |
| **裝備:護甲件附魔** | 護甲版 factor 較低:`fortify_skill` +11/件、`resist` +30%/件、`fortify_resource` health +24/件;武器可附 `weapon_element` fire/frost/shock ≈ +24(無視物理甲、吃元素抗、加在傷害) | 改 equipped 後必 recompute(R05) |
| **種族(建檔寫 base)** | 諾德 str/end+10·blade+5·**blunt+10**·heavy_armor+5·block+5·frost 抗 50 / 獸人 str/end+10·will+5·blunt+10·**heavy_armor+10(全種族最高)**·block+5·magic 抗 25(★重甲鈍器向最佳) / 紅衛 str/end+10·agi+5·**blade+10**·blunt+5·heavy_armor+5·疾/毒抗 75(刀劍向最佳);帝國人 blade/blunt/heavy_armor+5·per+10(均衡) | `races.json`;技能起始與屬性皆併 base,非獨立層;block 起始諾德=獸人=+5(非獸人獨高) |
| **星座(建檔寫 base)** | ★**戰士座** str+5·end+5(無代價,純戰士最佳)/ 領主座 end+5+每日自療 60(▼火抗−25)/ 淑女座 per+10·end+5 | `birthsigns.json` |
| **陣營** | ⚠ **皆非直接戰力**:戰士公會 `armory_discount`(買武/甲 cap 0.35)·戰友團 `merc_discount`(雇傭兵 cap 0.5)·九神騎士團 `restoration_boon`(治療縮放)→ 經濟/治療層,**對輸出/減傷零加成** | `factions.json:11,156,185`;戰力來自種族/星座/里程碑/裝備層 |
| **里程碑:被動護甲**(多源 SUM,無 MAX 遮蔽) | heavy_armor_25 重甲入門+6 · heavy_armor_100 銅皮鐵骨+18 · block_25 持盾入門+5 · block_75 撐架穩步+10 · block_100 銅牆鐵壁+12;另跨樹石膚等 | `mastery.py:297-300` SUM 相加進 armor_rating;**總減傷仍夾 85% 硬頂、不趨近免疫** |
| **里程碑:重甲減傷/反控** | heavy_armor_75 **壁壘**(物理 ×0.85·▼代價攻擊耗體 ×1.2)vs 巍然不動(magic 抗+10);heavy_armor_50 **重甲反震**(反彈 12%·無耗體)vs 百戰不染(disease+25);heavy_armor_100 銅皮鐵骨(+18)vs **重壓**(被擊 22% 震開·stagger turns 2) | `mastery.json:46/278/387/389`;壁壘僅物理、元素穿透 |
| **戰鬥動作:盾牆架勢**(非里程碑) | 立陣:物理受傷 **×0.70**(`SHIELD_WALL_MITIGATION=0.30`,僅物理、元素穿透)+ **嘲諷**(鎖敵火力到坦);門檻=持盾 + base block≥50;每回合上繳 6 體力(歸 0 落陣) | `main.py:1727-1730`;`combat.py:286-290,445,98`;與壁壘/盾反獨立疊乘 |
| **里程碑:屬性 fortify** | enduring(athletics_75 end+5)·mighty_arm(blunt_75 str+4·屬鈍器分支取捨)·swift_blade(blade_75 agi+4·屬刀劍取捨) | 走 mastery_attr 層 SUM,絕不寫回 base |
| **里程碑:續航 apex** | 生生不息(restoration_100 每回合自癒 8·is_alive 守不復活)·不屈祝禱(restoration_75 血<25% regen 4×3)·不竭之軀(athletics_50 攻擊耗體 ×0.90) | 跨職可取的續航層 |
| **消耗品** | restore_health(即時回血)·restore_fatigue(★回體力=直接餵盾牆/格擋/盾反的體力經濟,可釀材料最多)·`potion_potency`(煉金 75/100 ≤+0.35)放大藥效 | `alchemy.py:184-188`;**體力是戰士主要防禦資源天花板** |
| **同伴增傷光環(★對 solo 戰士零自益)** | rally 戰陣號令(+0.15)·騎士戰旗 empower(0.20×illusion power);多源遞減疊加 `Σ mag×0.7^i`(`EMPOWER_STACK_RATIO=0.7`) | ⚠ `combat.py:395 not _is_player` 守門 → **只增益同伴**,純 solo bruiser by-design 無自益;僅戰旗 STANDARD_SELF_ARMOR+6 對自身有效(需 illusion≥50) |
| ⚠ **限時藥水** | ★戰士幾乎無傷害增益:可釀 buff 池僅 `fattr_agility`/`fattr_willpower`/`resist_magic`/`fskill_alchemy` | ⚠ **無 fattr_strength/endurance、無 fskill_blade/blunt/block/heavy_armor 材料**(R30 排除 str+武器技能,本輪另確認 end 同無)→ 戰士最核心屬性皆釀不出;唯 `resist_magic`(整體魔法抗·涵蓋火/霜/電三系)限時可釀,無單一元素/毒/疾抗 |
| **精神飽滿 well_rested** | 技能 xp ×1.25(24 遊戲時內) | ⚠ 只乘 xp、不碰 base、不影響戰鬥數值 → 純練功加速、非戰力 |

### B · 分支加成(三條分開 · 同階二選一互斥)

**① 刀劍(blade 樹 · archetype sword/spear · 純命中+傷害線,無內建破甲)**
| 階 | A(傷/控) | B |
|---|---|---|
| 25 | 持劍入門(命中+2%·單選自動授予) | — |
| 50 | 還擊架式(命中 25% 機率 stagger 敵 1 回) | 鋒刃輕靈(命中+5%) |
| 75 | 劍勢如虹(傷+8%) | 輕劍捷影(agility+4·持久層) |
| 100 | 鋒芒畢露(命中+5%) | 迅捷連斬(傷+12%·▼自損 recoil 5%·不致死) |
> 刀劍 archetype **無破甲**(`archetype_armor_pen('sword')=0.0`)。speed 因武器而異:sword 多 1.0(命中中性)、dawnfang 1.1(+0.01 命中)、daedric_spear 0.9(−0.01·spear 走 blade 技能但 archetype=spear)。傷害線最高 +0.20(blade_flow 0.08 + savage 0.12·同 target 多節點 weapon_mod **相加**)。
> **sword 神器**:valor_blade 百戰勳刃(dmg22·regen 3/3 自 HoT·★戰士公會掌門武器)、dawnfang 黎明之牙(dmg24·fire+28·湮滅主線·全遊戲最高元素之一)、skyburner 焚天劍(dmg23·fire+26·龍喉巢穴)、daedric_sword 魔族長劍(dmg22·純物理)。spear 亦走 blade 技能:魔族長槍 dmg24(與黎明之牙並列最高近戰本體傷·純物理)。

**② 鈍器(blunt 樹 · 釘錘 mace=控制 / 斧 axe=破甲;1H 或 2H 握法 · R41)**
| 階 | A(破甲/控) | B |
|---|---|---|
| 25 | 持錘入門(破甲 pen+0.03·單選自動授予) | — |
| 50 | 碎骨重擊(命中 25% 機率 weaken 敵 10%/2 回) | 沉勁揮擊(傷+10%·▼self recoil 4%) |
| 75 | 碎骨之力(破甲 pen+0.08) | 巨力臂(strength+4·放近戰傷/負重/體力) |
| 100 | 破甲重錘(破甲 pen+0.15) | 震盪一擊(命中 30% 機率 weaken 敵 15%/1 回) |
> ★**archetype 分流(R41)**:`axe`(短斧/戰斧)= 破甲流 `archetype_armor_pen=0.30`(`formulas.py:356`)→ 對高甲穩定,milestone 破甲可疊 0.30+0.03+0.08+0.15=**0.56**(夾 0.85);`mace`(釘錘/戰錘)= 控制流 **內建命中 20% 擊暈 stagger**(`_ARCHETYPE_BUILTIN_STATUS`·`not _is_solo` 免疫)、無破甲。**skill 皆 `blunt`**(一條鈍器線涵蓋全部錘斧;tree 破甲 perks 利好斧、weaken perks 利好錘)。
> **1H 鈍器**:釘錘 iron 11/steel 15/dwarven 18/daedric 23(控制·spd 0.75);短斧 iron 12/steel 13/dwarven 16/daedric 22(破甲·略快 spd 0.75~0.85)。
> **2H 鈍器(極攻握法·`two_handed` → 放棄盾/副手/格擋)**:戰錘 warhammer(mace·控制)iron 16…daedric 34;戰斧 battleaxe(axe·破甲)iron 15…daedric 32;傷比同階 1H **+45~55%**、速更慢(0.55~0.65)、最耗體。
> ⚠ **維蘇拉德 wuuthrad**(R41 轉 **2H 戰斧**·dmg32·archetype **axe**·enchant **berserk** mag30):berserk 依攻方已損生命比例提傷封頂 +30%(滿血 ×1.0·瀕死 ×1.30·乘物理於 solo 夾前·全遊戲僅此一把);現 archetype=axe → **破甲 0.30 + berserk 兼得**(舊 war_axe 不吃破甲已修)。**但轉 2H 後不可帶盾**(放棄盾反)→ 純 2H 極攻 berserk 流。戰友團掌門武器。

**③ 盾反(block 樹 · 反制/坦度)**
| 階 | A(反制) | B(堆護甲) |
|---|---|---|
| 25 | — | 持盾入門(passive_armor +5·單選自動授予) |
| 50 | ★**盾反**(`block_reflect` reflect 0.10·耗體 10·R42) | 盾擊踉蹌(`block_riposte` shield_bash stagger 0.35) |
| 75 | 盾擊破勢(stagger 0.35 + weaken 0.15/2 回) | 撐架穩步(passive_armor +10) |
| 100 | 盾威·完美格擋(stagger 0.40 + counter 0.5·回敬武器基礎傷 ×0.5) | 銅牆鐵壁(passive_armor +12) |
> ★**反傷流(R42:吃 raw、解耦護甲)**:受物理近戰擊中 → 反彈**「攻方完整物理輸出(連格擋前)= `raw/block_factor`」** × 比例(`combat.py` 反傷區)。**舊制吃 `dmg_done`(護甲越高反越少·反協同);R42 解耦** → 龜也反得動。三源相加:重甲反震 **0.06**(被動) + 盾反 **0.10**(耗體 10·力竭不計) + **荊棘附魔 `thorns`**(盔/胸/手/靴/盾各一條·反傷%=靈魂石階 ×1%·max 5 件 25%) → **max 0.41 of raw**。物理限定(元素穿透不反)、player-only(直接扣血非遞迴·無 A→B→A 環)、**不夾**。
> 🔴 **反傷流剋星=元素敵**:反傷物理限定 → **元素 solo boss(湮滅系 dremora_lord/古龍/達貢 全元素)反傷流完全不反**(掃 bestiary:86 敵 45 元素)→ 反傷是**「對物理敵」build**,終局元素 boss 得靠武器/盾擊另解。物理敵 raw 上限小(最強 41×0.41=17)→ 永不一擊反殺,故不夾。
> **盾擊踉蹌 block_riposte**(`mastery.py:618-629`,跨 50/75/100 stagger/weaken/counter 各 **MAX 聚合**·不相加;turns:2 修死時序)與盾反 reflect **同 block_50 二選一**:選盾反就拿不到 shield_bash 的 stagger,但 75/100 仍可補 block_riposte。
> **盾牆可搭**:盾不計四件套(`SET_SLOTS`)→ 1H 盾/十字軍聖盾/重盾皆不破重甲套;配黑檀套 magic 抗逼近免疫。
> ★**雙手重盾(R41 極防握法·`great_shield`)**:占雙手·無武器·普攻走**盾擊**(`bash_damage`·練 block·純物理·無破甲/附魔/塗毒)、護甲高於 1H 盾(AR 12~26)+ **被動物理減傷 `mitigation` 5~8%**(`combat._great_shield_mitigation_factor` 套盾牆後·乘性·僅物理·獸形不套)。**仍可格擋/盾牆**(它是盾),只是無副手、手持武器戰中休眠。十字軍聖盾 `crusaders_ward` 轉重盾(AR16→24·+mit/bash·保魔抗+30%)。減傷疊盾牆/壁壘 → 極致反震坦,但 85% 護甲夾不破。
> ⚠ **握法互斥(R41)**:雙手武器/雙手重盾各占雙手 → 與盾反(`block_reflect` 需 1H 盾)互斥。盾反流走 **1H 武器 + 1H 盾**(reflect 0.06+0.10+荊棘);雙手重盾走 **盾擊 + 被動減傷**(無盾反,但荊棘可附其護甲/重盾);二者不可兼得。真正同階互斥仍是里程碑二選一(block_50 盾反 vs 盾擊踉蹌)。

### C · 完全體疊滿 + 天花板
**獸人(str/end+10·heavy_armor+10·blunt+10)· 戰士座(str/end+5)· 魔族重甲套(health+60)+ 魔族盾 · 達貢之力(str+18)· blade/blunt/heavy_armor/block 四系里程碑各取一支**:
```
近戰基礎傷乘子(技能 base 100 + 飾品 fortify_skill ~+15 → 有效 115,attack skill_mult 不夾上限 → ≈1.65)
              × str_mult(0.75 + 118/160 ≈ 1.49) ≈ ×2.46
護甲值疊滿 = (四件套 + 盾的 armor_rating 總和〔含魔族盾 15〕)×(0.5+heavy/100)  ← 盾值也吃重甲乘子
              + passive_armor 多源 + 護甲淬鍊 int(Σlvl×1.25)≈+30  ← 乘子之後平加 → damage_after_armor 遞減
反傷(R42·吃 raw 解耦)= 重甲 0.06 + 盾反 0.10 + 荊棘 5 槽 0.25 = max 0.41 × 攻方完整物理輸出(物理限定·不夾)
```
> ⚠ **非對稱夾限**:進攻 `skill_mult = 0.5 + 武器技能/100` **不夾上限**(`formulas.py:324`,fortify_skill 可推過 1.5);但防守 `block_damage_factor` 對 block 技能**夾 100**(`formulas.py:340`)→ 自己擋的減傷不因 fortify_skill 超 100 而更強。
🔴 **紅線（與刺客/弓手「不同源」）**：
1. **85% 護甲硬夾**(`damage_after_armor:350` `reduction = min(0.85, eff/(eff+100))`)→ passive_armor/淬鍊/套裝堆滿亦至少造成 1 傷,**永不趨近免疫**;反過來戰士自己再硬也擋不滿 85%。
2. **體力經濟**=戰士主要天花板:盾牆 6/回合上繳、格擋 4/次、盾反 6/次、壁壘攻擊耗體 ×1.2 → 力竭即攻防雙弱(restore_fatigue 藥/運動省體是續航命脈)。
3. **不靠偷襲爆發、靠持續輸出 + 坦度**:戰士攻擊 `sneaking=False` → **不觸 40% 開場夾**,對 solo boss **無單擊軟上限**(可正面長線磨),但也沒有「一刀繞夾」的爆發捷徑——天花板是 DPS × 護甲遞減 × 體力續航。
4. **狼人換層取捨**:獸形 str 42/血+160 看似誘人,但脫掉整套重甲/盾/附魔/淬鍊/格擋/盾牆 → 對重甲盾反 bruiser 是**放棄全部裝備坦度換野獸血量**,結構衝突;且 tier≥2 恫嚇之嚎對 solo boss 免疫。
5. **吸血代價(四重)**:階級3 fire−30(需達貢 fire+60 抵成淨 +30)+ 日照灼傷 1.5/h/階 + 階級≥2 被商家拒往(需進食)+ 出生星座每日之力被 `vampiric_drain` 取代(領主座自療失效)→ 對前排長線磨的 bruiser 是持續負擔。

→ **戰士上限不靠「乘子爆發」而靠「持續 DPS + 護甲遞減扛 + 體力續航」**;與潛行流共享「打 solo boss 也得長線磨」的結論,但鎖的是**護甲 85% 夾 + 體力經濟**,而非偷襲 40% 夾。

---

## ⑤ 刺客 vs 弓手 對照(同為潛行流)

| | 潛行刺客(匕首) | 潛行弓手(弓) |
|---|---|---|
| 偷襲 archetype | ★**×1.6**(全遊戲最高) | ×1.3 |
| 增傷手段 | 雙持副手 ×0.6 + 塗毒(主副手共享單層) | 單發 + 塗毒 + 瞄準射蓄力 |
| 距離/風險 | 近戰、要潛近貼身、不能格擋、最脆 | 遠程、安全、可風箏 |
| 公會/神器 | ★黑暗兄弟會掌門武器(悲傷之刃 `blade_of_woe` / 魔銳茲之刃) | 黑兄亦可入(gate 含 marksman·夜母 ×1.18 對弓生效)、**無弓專屬神器** |
| 開場偷襲乘子(疊滿) | ≈ ×11.3 | ≈ ×9.2 |
| 紅線 | **同源**:solo boss 40% 夾 / >3 敵反制 / 麻痺免疫 | 同左 |

→ **刺客上限更高但更脆更吃站位;弓手安全穩定、上限略低。** 兩者天花板同由三道煞車鎖死,畢業也秒不掉 solo boss。

---

## 附 · 其他原型骨架(待補)

本檔目前縱切了四條(潛行刺客 / 潛行弓手 / 純法師 / 純戰士)。其餘原型骨架(指針,待後續補):
- **戰法師**(武器灌注+共鳴一擊)、**騎士**(戰旗 empower)、**召喚流**等 —— 見 BUFFS.md §③④ 對應 perk + build.md ③ 法師副軸流派。
> 補新原型時:**先看根(吃哪些數值)→ 通用層 → 分支二選一 → 完全體+紅線**,與上方四條同格式。
