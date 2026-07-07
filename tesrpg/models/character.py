"""角色資料模型。

只存資料 + 純查詢/序列化;成長、戰鬥等規則放在 systems/。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tesrpg import formulas


@dataclass
class Character:
    id: str
    name: str
    race: str
    sex: str                       # "male" / "female"
    birthsign: str
    class_id: str                  # 預設職業 id,自訂則為 "custom"
    origin: str = ""               # 開局背景 id(不一樣的人生);舊存檔缺此欄 → 預設空字串

    # 職業快照(支援自訂職業:直接存在角色上,不依賴 classes.json)
    specialization: str = "combat"
    favored_attributes: list[str] = field(default_factory=list)
    major_skills: list[str] = field(default_factory=list)

    attributes: dict[str, int] = field(default_factory=dict)   # 8 屬性
    skills: dict[str, int] = field(default_factory=dict)       # 21 技能 0–100
    skill_xp: dict[str, float] = field(default_factory=dict)   # learn-by-doing 進度

    level: int = 1
    level_xp: float = 0.0           # 等級經驗池(混合 Skyrim 式:技能成長累積 → 達門檻可升級)
    # 舊系統欄位(已停用):僅保留供舊存檔 cls(**d) 載入;ensure_level_xp 會把進度搬到 level_xp
    level_progress: int = 0
    level_skillups: dict[str, int] = field(default_factory=dict)

    magicka_bonus: int = 0          # 種族+星座的固定魔力加成

    base_max_health: int = 0        # 生命上限基底(創建耐力×2;不含護甲 fortify、不隨耐力逐級長)
    # 升級三選一累積的資源加成 {"health":x,"magicka":y,"fatigue":z}
    resource_levels: dict[str, int] = field(default_factory=dict)
    max_health: int = 0             # 有效生命上限(= base + resource_levels + 護甲 fortify)
    max_magicka: int = 0
    max_fatigue: int = 0
    health: float = 0
    magicka: float = 0
    fatigue: float = 0

    gold: int = 0
    weapon: str = "fists"           # 目前裝備的武器 id(對應 data/weapons.json)
    offhand: str = ""               # 副手武器 id(僅雙持匕首用;"" = 無)
    weapon_poison: dict | None = None        # 武器塗毒 {"status","charges","name"};None=未塗
    enchant_charges: dict = field(default_factory=dict)  # 充能型附魔 {item_id: 剩餘充能};命中擒魂/麻痺用,靈魂石回充(見 systems/enchanting)
    weapon_temper: dict = field(default_factory=dict)    # {weapon_id: 淬鍊級}(永久強化 → +傷害;鍛造)
    armor_temper: dict = field(default_factory=dict)     # {armor_id: 淬鍊級}(永久強化 → +護甲值;鍛造)
    location_id: str = "start"

    # 後續里程碑會用到,先留好欄位讓存檔格式穩定
    inventory: list = field(default_factory=list)
    equipped: dict = field(default_factory=dict)
    spells: list = field(default_factory=list)
    # 穿戴裝備(護甲/飾品附魔 + 套裝)疊進的加成 —— 由 stats.recompute_equipment 重算後寫入,
    # 讓 skill()/attr()/抗性 能在不帶 gamedata 的情況下直接讀(隨裝備變動即時更新)。
    equip_skill_bonus: dict = field(default_factory=dict)   # skill_id -> +點數
    equip_attr_bonus: dict = field(default_factory=dict)    # attr_id -> +點數
    equip_resist: dict = field(default_factory=dict)        # element -> +百分比
    # 吸血鬼化(力量↔詛咒;持久狀態,進存檔)。階級加成走獨立層,與裝備加成同模式:
    # attr()/skill() 疊加、成長/夾限只用 base_*。詳見 systems/vampirism.py。
    is_vampire: bool = False
    vampire_infected_day: int = -1      # 染吸血熱的絕對日(-1=未感染);潛伏滿 INCUBATION 轉化
    vampire_fed_day: int = 0            # 上次進食的絕對日(階級由「距今天數」推導)
    vampire_stage: int = 0             # 目前套用中的階級 0..3(供變化偵測/結算)
    vampire_attr_bonus: dict = field(default_factory=dict)   # attr_id -> +點數(階級加成)
    vampire_skill_bonus: dict = field(default_factory=dict)  # skill_id -> +點數
    vampire_resist: dict = field(default_factory=dict)       # element -> +百分比(含火焰弱點負值)
    # 斯庫瑪/月糖成癮(力量↔詛咒;持久狀態,進存檔)。high 增益 / 戒斷懲罰走獨立 skooma_* 層,
    # 與裝備/吸血鬼加成同模式:attr()/skill() 疊加、成長/夾限只用 base_*。詳見 systems/skooma.py。
    skooma_addiction: int = 0           # 成癮計數(用藥 +1;清醒夠久衰減至 0)
    skooma_high_until: int = 0          # 高潮結束的絕對小時(now < 此值 = 仍 high);0=未 high
    skooma_last_dose_hour: int = -1     # 上次用藥的絕對小時(-1=從未;戒斷強度由「距今」推導)
    skooma_attr_bonus: dict = field(default_factory=dict)    # attr_id -> +點數(high 增益 或 戒斷負值,二擇一)
    skooma_skill_bonus: dict = field(default_factory=dict)   # skill_id -> +點數(僅戒斷負值;high 不碰技能 → 避刺客紅線)
    # 雙面間諜 / 臥底(R100;掩護身分 ↔ 價值觀漂移的天平,持久進存檔)。**零戰鬥面狀態** ——
    # 不寫進 char.factions(保 R96 互斥)、無 *_bonus 層 → combat/formulas 讀值不變、sim byte-identical。
    # 全狀態在 cover_guild=="" 時 no-op。詳見 systems/undercover.py。
    cover_guild: str = ""               # 潛入中的掩護公會 B(""=無臥底·主 no-op 開關)
    cover_true_guild: str = ""          # 派你潛入的真實公會 A(叛變時棄 A 入 B)
    cover_secrecy: int = 0              # 0..100 掩護完整度(每日衰減;歸零/逾期 → 曝光)
    cover_loyalty: int = 0             # −100(忠於 A)..+100(同情 B);價值觀漂移軸(驅動結局)
    cover_last_day: int = 0            # 上次 secrecy 衰減的絕對日水位(ratchet·防重載重複衰減)
    cover_knower: str = ""             # 已識破你的具名 B NPC id(""=無人盯上;殺之滅口 / 逾期曝光)
    cover_knower_deadline: int = 0     # 知情者通風報信的絕對日期限(超過 = 曝光)
    # 限時增益藥水(R30;煉金產出的強化屬性/技能/抗元素藥水,絕對小時到期)。權威來源 = potion_buffs;
    # 三個 *_bonus/resist 是「由 potion_buffs 決定性推導的快取層」(同 skooma/mastery 模式:attr()/skill()/
    # 抗性疊加、成長/夾限只用 base_*、絕不寫 base)。每圈 potion_buff.update 清過期,詳見 systems/potion_buff.py。
    potion_buffs: list = field(default_factory=list)          # [{kind,param,magnitude,expires_at}](權威)
    potion_attr_bonus: dict = field(default_factory=dict)     # attr_id -> +點數(推導快取)
    potion_skill_bonus: dict = field(default_factory=dict)    # skill_id -> +點數(推導快取)
    potion_resist: dict = field(default_factory=dict)         # element -> +百分比(推導快取)

    # 實用/幻術魔法限時自我增益(R104;魅惑/隱形/羽落/偵知,絕對小時到期)。唯一權威、無推導快取:
    # 社交/負重/潛行加成由 spellfx helper on-the-fly 讀;絕不寫 base。詳見 systems/spellfx.py。
    spell_effects: list = field(default_factory=list)         # [{kind,magnitude,expires_at}](權威)
    # 煉金效果逐步揭露(R32):材料效果預設「???」,經嚐試/煉製/技能揭露。ing_id -> [已揭露 kind](JSON list)。
    # 純資訊層,不碰 brew 數學;通用於任何效果 kind(自動涵蓋 R30/R31 新效果)。詳見 systems/alchemy.py。
    known_effects: dict = field(default_factory=dict)
    # 狼人化 / 獸形(Lycanthropy;主動限時變身,吸血鬼的對位)。獸形加成走獨立 werewolf_* 層,
    # 與裝備/吸血鬼加成同模式:attr()/skill()/抗性 疊加、成長/夾限只用 base_*。詳見 systems/lycanthropy.py。
    is_werewolf: bool = False            # 染狼人化(持久身分)
    werewolf_infected_day: int = -1      # 染狼人熱的絕對日(-1=未感染);潛伏滿 INCUBATION 轉化
    beast_form: bool = False             # 獸形「現行」快取布林(combat 讀此,不穿 state;由 lycanthropy 維護)
    beast_form_until: int = 0            # 獸形結束的絕對小時(now < 此值 = 仍獸形)
    beast_feeds: int = 0                 # 本次獸形已吞噬次數(續時上限)
    werewolf_total_feeds: int = 0        # 累計吞噬次數(成就用)
    werewolf_attr_bonus: dict = field(default_factory=dict)   # attr_id -> +點數(獸形)
    werewolf_skill_bonus: dict = field(default_factory=dict)  # skill_id -> +點數(獸形;MVP 空)
    werewolf_resist: dict = field(default_factory=dict)       # element -> +百分比(疾病免疫)
    werewolf_health_bonus: int = 0       # 獸形額外生命上限(走 stats.recompute_max_resources)
    # 達貢之力(湮滅危機教徒結局的慘勝獎賞;竊得達貢殘力的永久增益)。走獨立 dagon_* 層,
    # 與裝備/吸血鬼/狼人加成同模式:attr()/skill()/抗性/魔力 疊加、成長/夾限只用 base_*。詳見 systems/dagon_boon.py。
    dagon_boon: bool = False              # 是否已竊得達貢之力(持久身分;一次性永久)
    dagon_attr_bonus: dict = field(default_factory=dict)    # attr_id -> +點數
    dagon_skill_bonus: dict = field(default_factory=dict)   # skill_id -> +點數(毀滅/咒術)
    dagon_resist: dict = field(default_factory=dict)        # element -> +百分比(烈焰之主 → 火抗)
    dagon_magic_bonus: int = 0           # 額外魔力上限(走 stats.recompute_max_resources)
    # 戴德拉誓福(R45;戴德拉親王神殿任務的永久回報,可同時持有多位親王的誓福 → 後期收集軸)。
    # 達貢誓福(主線慘勝)刻意維持獨立 dagon_* 層不動;此層為通用資料驅動誓福(boons.json 登錄表)。
    # 與裝備/吸血鬼/狼人/達貢層同模式:attr()/skill()/抗性/魔力 疊加、成長/夾限只用 base_*、絕不寫 base。
    # boons 為唯一權威(持有的 boon id);四個 *_bonus/resist 是「由 boons + JSON 決定性推導的快取層」。詳見 systems/boons.py。
    boons: list = field(default_factory=list)                # 持有的誓福 id(權威)
    boon_attr_bonus: dict = field(default_factory=dict)      # attr_id -> +點數(推導快取)
    boon_skill_bonus: dict = field(default_factory=dict)     # skill_id -> +點數(推導快取)
    boon_resist: dict = field(default_factory=dict)          # element -> +百分比(推導快取)
    boon_magic_bonus: int = 0            # 額外魔力上限(走 stats.recompute_max_resources)
    boon_spell_power: float = 0.0        # 法術威力加成(誓福層·乘進 magic._power·推導快取;R78b 大法師通悟)
    # 九神祝福(R107;Skyrim 排他單槽限時祝福 + Oblivion 德行閘)。divine_blessing 為唯一權威
    # ({"divine","expires_at"} 絕對小時;{}=無;單槽 dict → 拜新壇即整包覆蓋);兩個快取由其推導。
    # 與其餘加成層同模式:attr()/entity_resist() 疊加、絕不寫 base。詳見 systems/divines.py。
    divine_blessing: dict = field(default_factory=dict)     # 權威(單槽)
    divine_attr_bonus: dict = field(default_factory=dict)   # attr_id -> +點數(推導快取)
    divine_resist: dict = field(default_factory=dict)       # element -> +百分比(推導快取)
    # 疾病(R53;普通病=被怪傳染的懲罰層,治癒前持續、可惡化/帶 DoT)。與斯庫瑪戒斷負層同模式:
    # diseases 為唯一權威(已染病 id + 染病絕對日);兩個 *_penalty 是「由 diseases + diseases.json 決定性推導的
    # 負值快取」,attr()/skill() 疊加、成長/夾限只用 base_*、絕不寫 base。吸血鬼/狼人疾病免疫天然不染。詳見 systems/diseases.py。
    diseases: list = field(default_factory=list)              # [{"id","day"}](權威;day=染病絕對日,供惡化計時)
    disease_attr_penalty: dict = field(default_factory=dict)  # attr_id  -> 負點數(推導快取)
    disease_skill_penalty: dict = field(default_factory=dict) # skill_id -> 負點數(推導快取)
    factions: dict = field(default_factory=dict)         # faction_id -> 階級索引(已入會)
    # 黑暗兄弟會(里程碑;血債招募 → 合約晉升 → 夜母祝福)。詳見 systems/brotherhood.py。
    # 階級存在 factions["dark_brotherhood"];此處只記入會「前」的狀態機欄位:
    murders: int = 0                # 謀殺無辜者的次數(血債);達門檻 → 夜母遣使招募
    db_invited: bool = False        # 黑暗兄弟會使者是否已現身招募過(避免每次休息重複觸發)
    murdered_npcs: list = field(default_factory=list)     # 已被你滅口的具名 NPC(從可攀談名單消失)
    active_effects: list = field(default_factory=list)
    fame: int = 0
    infamy: int = 0
    bounty: int = 0
    disposition: int = 50

    # 技能里程碑(辯舌·折服):已被「必定說服」折服過的 NPC(每人一次)。
    persuaded_npcs: list = field(default_factory=list)

    # 技能里程碑 v2(達門檻二選一)。choices 為唯一權威來源(玩家選了什麼,永久,進存檔);
    # 三個 *_bonus/resist 是「由 choices + JSON 決定性推導的快取層」(同 equip_* 模式,
    # recompute-on-load,見 stats.recompute_mastery_bonuses),attr()/skill()/抗性疊加、成長/夾限只用 base_*。
    mastery_choices: dict = field(default_factory=dict)       # node_id -> opt_id(權威)
    mastery_skill_bonus: dict = field(default_factory=dict)   # skill_id -> +點數(推導快取)
    mastery_attr_bonus: dict = field(default_factory=dict)    # attr_id  -> +點數(推導快取)
    mastery_resist: dict = field(default_factory=dict)        # element  -> +百分比(推導快取)

    # M5:任務、犯罪、聲望追蹤
    quests: dict = field(default_factory=dict)            # quest_id -> {"progress":...}
    completed_quests: list = field(default_factory=list)
    kill_counts: dict = field(default_factory=dict)       # creature_tid -> 擊殺數
    soul_tokens: int = 0                                   # R106C 死靈經濟:可花用的靈魂 token(打怪+1·戰後回收倖存亡者+1/隻)
    necro_upgrades: dict = field(default_factory=dict)     # R106C 永久死靈升級 upgrade_id -> level(亡者護甲/軍團上限/喚魂精算…)
    cleared_dungeons: list = field(default_factory=list)
    # 地城再滋擾(R111):已清地城的下次「重踞」絕對小時(dungeon_id → hours;缺=不滋擾)。
    # 🔴 cleared_dungeons 恆單調不減(主線門鏈/98 條 clear_dungeon 任務/成就/legacy 皆依賴);
    # 重踞是平行的衍生狀態(dungeon.is_reinfested),絕不從 cleared_dungeons 移除。
    dungeon_reinfest_at: dict = field(default_factory=dict)
    bounties: dict = field(default_factory=dict)          # province -> 賞金
    npc_disposition: dict = field(default_factory=dict)   # npc_id -> 好感

    # M6:一生軌跡(供傳奇總結)
    visited_locations: list = field(default_factory=list)
    discovered_landmarks: list = field(default_factory=list)   # 已觸發首次發現的地標 loc_id(一次性守門)

    # M12:隊伍(雇用的傭兵同伴 template id;戰鬥時為你而戰)
    companions: list = field(default_factory=list)
    # 受封武士時隊伍已滿、暫無法隨行的侍從(領主已賜,於「隊伍」選單有空位時免費召集;不丟棄)。
    pending_companions: list = field(default_factory=list)
    # 同伴系統深化:持久 HP(cid→當前 HP,每戰回寫;0=倒下 benched 須治療)+ 羈絆(cid→點,並肩獲勝累積)。
    # dataclass 預設 {} → 舊存檔向後相容(未記錄者視為滿血/零羈絆)。詳見 systems/party.py。
    companion_hp: dict = field(default_factory=dict)
    companion_bond: dict = field(default_factory=dict)
    # 同伴深化(Tier 2 類玩家):裝上同伴的裝備 {cid:{"weapon":item_id,"armor":item_id}}(物移出背包、只存此槽=戰利品 sink)+
    # 戰術傾向 {cid:build_id}(羈絆階解鎖·永久)。技能為 companions.json 唯讀模板(非存檔欄);充能復用 enchant_charges。
    # dataclass 預設 {} → 舊存檔向後相容;遷移/防呆見 systems/party.py ensure_companion_gear/build。
    companion_gear: dict = field(default_factory=dict)
    companion_build: dict = field(default_factory=dict)

    # M8:出生星座能力(每日一次)冷卻 + 塔之鑰開鎖充能
    power_last_day: dict = field(default_factory=dict)    # power_id -> 上次使用的絕對日
    tower_key_charge: bool = False

    # 商店庫存(Skyrim 式:每商人有限數量 + 定時補貨 + 補貨品項有變化)。詳見 systems/world.py。
    # 舊存檔缺此二欄 → dataclass 預設空 dict;首次造訪該商店即依目錄初始化。
    shop_stock: dict = field(default_factory=dict)        # loc_id -> {item_id: 剩餘數量}
    shop_restock_at: dict = field(default_factory=dict)   # loc_id -> 下次補貨的絕對小時

    # 領主區(宮廷)Phase 2:領主委託功勳 + 武士冊封(Thaneship)。詳見 systems/court.py。
    city_standing: dict = field(default_factory=dict)     # loc_id -> 城邦功勳(完成領主委託累積)
    thaneships: list = field(default_factory=list)        # 已受封武士的 loc_id(享賞金寬待 + 侍從)

    # 城戰(Phase 3+4):政治立場 + 攻城戰況。詳見 systems/politics.py。
    # 城為單位:各城立場種子在 rulers.json `stance`;玩家選 allegiance(大義)後對立城可攻。
    # 動態戰況掛 Character(存檔)、首次存取時由種子懶初始化(同 shop_stock 模式)。
    allegiance: str = ""                                  # 玩家擁護的大義:""=未選 / imperial / independent
    # 外交立場軸(條件式對話樹):cause(imperial/independent/own/daedric)-> 立場分 [-100,100]。
    # 對話選擇累積(討好一方得罪對立方,互斥真權衡);高價值話題受其門檻。dataclass 預設 {} 向後相容。
    faction_standing: dict = field(default_factory=dict)
    # 對話「一次性」話題去重:npc_id -> [已觸發的 once 話題 id](表態/結交等持久 effect 不可重刷)。
    dialogue_done: dict = field(default_factory=dict)
    city_faction: dict = field(default_factory=dict)      # loc_id -> 現時歸屬立場(攻城會翻轉)
    garrison_current: dict = field(default_factory=dict)  # loc_id -> 現存駐軍(圍城方略消耗;佔領後=你的駐軍,叛亂計時會緩降)
    siege_ops: dict = field(default_factory=dict)         # loc_id -> [已施行的圍城方略 id](每役每略一次)
    # 城戰階段三:佔領後收稅(按居民數量)− 駐軍維護費 + 輕量叛亂計時(駐軍緩降,潰散則城叛)。詳見 systems/politics.py。
    tax_due_at: dict = field(default_factory=dict)         # loc_id -> 下次徵稅的絕對小時(僅攻下的城;預設 {} 向後相容)
    stewards: dict = field(default_factory=dict)           # loc_id -> 冊封的總管 companion_id(A3 佔領治理;預設 {} 向後相容)
    # 陣營大事件(動態政局):事件驅動的城邦易幟層 + 已觸發大事件。詳見 systems/worldstate.py(階段 C)。
    world_faction: dict = field(default_factory=dict)      # loc_id -> 大事件易幟的立場(覆蓋種子;玩家征服 city_faction 優先)
    world_events_fired: list = field(default_factory=list) # 已觸發的大事件 id(once-fire + 解鎖判定,如神話黎明)
    # 常態世界脈動(動態新聞層 + 聚光激增可重複委託)。詳見 systems/worldpulse.py。
    world_pulse_day: dict = field(default_factory=dict)     # pulse_id -> 上次廣播的絕對日(脈動冷卻 + 推導聚光 active window)
    pulse_eval_day: int = 0                                 # 本日已評估脈動的絕對日(同日多圈只評一次,防洗版)
    # AI 陣營自走戰爭(worldstate 階段五)。garrison_current 同時承載「非玩家城」現存守軍(aiwar 寫,
    # 在 tick_tax 前跑;tick_tax 只迭代玩家城故不衝突)。詳見 systems/aiwar.py。
    war_tick_at: int = 0                                   # 下次 AI 戰爭結算的絕對小時(0=未開戰,首圈給一週寬限)
    city_threat: dict = field(default_factory=dict)        # 玩家城 loc -> 正圍攻它的敵對陣營(預警/UI;無則不在表)

    # 招兵買馬(城戰的金幣/領袖路線)。親衛/將領=companions(具名);軍隊/士兵=抽象兵員。詳見 systems/warband.py。
    soldiers: int = 0                                     # 麾下士兵數(營地招募;攻城當援軍 + 大軍壓境)
    camp: str = ""                                        # 營地所在 loc_id(野外紮營 / 佔領已清空地城);""=未建
    wage_due_at: int = 0                                  # 下次發軍餉的絕對小時(階段二;0=無兵/未開始計餉)

    # 房產 & 坐騎(家園與後勤;見 systems/housing.py、systems/mounts.py)。皆走 dataclass 預設向後相容。
    houses_owned: list = field(default_factory=list)      # 已購置房產的 loc_id(權威)
    house_stash: dict = field(default_factory=dict)       # loc_id -> [{"id","qty"}](家中倉庫;不計隨身負重)
    house_upgrades: dict = field(default_factory=dict)    # loc_id -> [upgrade_id](已購擴建;權威;R110)
    house_garden_at: dict = field(default_factory=dict)   # loc_id -> 下次可採收的絕對小時(tax_due_at 模式;R110)
    well_rested_until: int = 0                            # 「精神飽滿」到期絕對小時(0=無;最佳休息設;同 skooma_high_until 模式)
    well_rested: bool = False                             # 精神飽滿現行快取(loop 頂端依 until 刷新;use_skill 讀;同 beast_form 模式)
    mounts_owned: list = field(default_factory=list)      # 已擁有的坐騎 id
    active_mount: str = ""                                # 現乘坐騎 id(""=步行;戰技/被動以此 + 是否騎乘語境為閘)

    is_player: bool = False

    # --- 查詢 -------------------------------------------------------------
    def attr(self, key: str) -> int:
        return (self.attributes.get(key, formulas.BASE_ATTRIBUTE)
                + self.equip_attr_bonus.get(key, 0) + self.vampire_attr_bonus.get(key, 0)
                + self.mastery_attr_bonus.get(key, 0) + self.skooma_attr_bonus.get(key, 0)
                + self.werewolf_attr_bonus.get(key, 0) + self.dagon_attr_bonus.get(key, 0)
                + self.boon_attr_bonus.get(key, 0)
                + self.potion_attr_bonus.get(key, 0)
                + self.divine_attr_bonus.get(key, 0)       # R107:九神祝福(單槽限時;空 dict → +0)
                + self.disease_attr_penalty.get(key, 0))   # R53:疾病負層(空 dict → 未染病者 +0)

    def skill(self, key: str) -> int:
        curse = getattr(self, "_dungeon_curse", None)   # R121 念力球反噬:暫態負層(僅地城中設,離場即清,不入檔;None → +0 byte-identical)
        return (self.skills.get(key, 0)
                + self.equip_skill_bonus.get(key, 0) + self.vampire_skill_bonus.get(key, 0)
                + self.mastery_skill_bonus.get(key, 0) + self.skooma_skill_bonus.get(key, 0)
                + self.werewolf_skill_bonus.get(key, 0) + self.dagon_skill_bonus.get(key, 0)
                + self.boon_skill_bonus.get(key, 0)
                + self.potion_skill_bonus.get(key, 0)
                + self.disease_skill_penalty.get(key, 0)   # R53:疾病負層(空 dict → 未染病者 +0)
                + (curse.get(key, 0) if curse else 0))

    def base_attr(self, key: str) -> int:
        """不含裝備加成的原始屬性(供成長/夾限用)。"""
        return self.attributes.get(key, formulas.BASE_ATTRIBUTE)

    def base_skill(self, key: str) -> int:
        return self.skills.get(key, 0)

    def is_major_skill(self, skill_id: str) -> bool:
        return skill_id in self.major_skills

    def can_level_up(self) -> bool:
        return self.level_xp >= formulas.levelup_xp_threshold(self.level)

    # --- 序列化 -----------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "race": self.race, "sex": self.sex,
            "birthsign": self.birthsign, "class_id": self.class_id,
            "origin": self.origin,
            "specialization": self.specialization,
            "favored_attributes": self.favored_attributes,
            "major_skills": self.major_skills,
            "attributes": self.attributes, "skills": self.skills, "skill_xp": self.skill_xp,
            "level": self.level, "level_xp": self.level_xp,
            "level_progress": self.level_progress,
            "level_skillups": self.level_skillups,
            "magicka_bonus": self.magicka_bonus,
            "base_max_health": self.base_max_health,
            "resource_levels": self.resource_levels,
            "max_health": self.max_health, "max_magicka": self.max_magicka,
            "max_fatigue": self.max_fatigue,
            "health": self.health, "magicka": self.magicka, "fatigue": self.fatigue,
            "gold": self.gold, "weapon": self.weapon, "offhand": self.offhand,
            "weapon_poison": self.weapon_poison, "enchant_charges": self.enchant_charges,
            "weapon_temper": self.weapon_temper, "armor_temper": self.armor_temper,
            "location_id": self.location_id,
            "inventory": self.inventory, "equipped": self.equipped, "spells": self.spells,
            "equip_skill_bonus": self.equip_skill_bonus, "equip_attr_bonus": self.equip_attr_bonus,
            "equip_resist": self.equip_resist,
            "is_vampire": self.is_vampire, "vampire_infected_day": self.vampire_infected_day,
            "vampire_fed_day": self.vampire_fed_day, "vampire_stage": self.vampire_stage,
            "vampire_attr_bonus": self.vampire_attr_bonus,
            "vampire_skill_bonus": self.vampire_skill_bonus, "vampire_resist": self.vampire_resist,
            "skooma_addiction": self.skooma_addiction, "skooma_high_until": self.skooma_high_until,
            "skooma_last_dose_hour": self.skooma_last_dose_hour,
            "skooma_attr_bonus": self.skooma_attr_bonus, "skooma_skill_bonus": self.skooma_skill_bonus,
            "cover_guild": self.cover_guild, "cover_true_guild": self.cover_true_guild,
            "cover_secrecy": self.cover_secrecy, "cover_loyalty": self.cover_loyalty,
            "cover_last_day": self.cover_last_day, "cover_knower": self.cover_knower,
            "cover_knower_deadline": self.cover_knower_deadline,
            "potion_buffs": self.potion_buffs, "potion_attr_bonus": self.potion_attr_bonus,
            "potion_skill_bonus": self.potion_skill_bonus, "potion_resist": self.potion_resist,
            "spell_effects": self.spell_effects,
            "known_effects": self.known_effects,
            "is_werewolf": self.is_werewolf, "werewolf_infected_day": self.werewolf_infected_day,
            "beast_form": self.beast_form, "beast_form_until": self.beast_form_until,
            "beast_feeds": self.beast_feeds, "werewolf_total_feeds": self.werewolf_total_feeds,
            "werewolf_attr_bonus": self.werewolf_attr_bonus,
            "werewolf_skill_bonus": self.werewolf_skill_bonus,
            "werewolf_resist": self.werewolf_resist,
            "werewolf_health_bonus": self.werewolf_health_bonus,
            "dagon_boon": self.dagon_boon, "dagon_attr_bonus": self.dagon_attr_bonus,
            "dagon_skill_bonus": self.dagon_skill_bonus, "dagon_resist": self.dagon_resist,
            "dagon_magic_bonus": self.dagon_magic_bonus,
            "boons": self.boons, "boon_attr_bonus": self.boon_attr_bonus,
            "boon_skill_bonus": self.boon_skill_bonus, "boon_resist": self.boon_resist,
            "boon_magic_bonus": self.boon_magic_bonus, "boon_spell_power": self.boon_spell_power,
            "divine_blessing": self.divine_blessing, "divine_attr_bonus": self.divine_attr_bonus,
            "divine_resist": self.divine_resist,
            "diseases": self.diseases, "disease_attr_penalty": self.disease_attr_penalty,
            "disease_skill_penalty": self.disease_skill_penalty,
            "factions": self.factions,
            "murders": self.murders, "db_invited": self.db_invited,
            "murdered_npcs": self.murdered_npcs,
            # active_effects 是「戰鬥內」臨時效果(護盾/中毒/再生),不寫入存檔,
            # 載入時由 dataclass 預設為空 list(避免臨時效果被永久化)。
            "fame": self.fame, "infamy": self.infamy, "bounty": self.bounty,
            "disposition": self.disposition, "is_player": self.is_player,
            "quests": self.quests, "completed_quests": self.completed_quests,
            "kill_counts": self.kill_counts,
            "soul_tokens": self.soul_tokens, "necro_upgrades": self.necro_upgrades,
            "cleared_dungeons": self.cleared_dungeons,
            "dungeon_reinfest_at": self.dungeon_reinfest_at,
            "bounties": self.bounties, "npc_disposition": self.npc_disposition,
            "persuaded_npcs": self.persuaded_npcs,
            "mastery_choices": self.mastery_choices,
            "mastery_skill_bonus": self.mastery_skill_bonus,
            "mastery_attr_bonus": self.mastery_attr_bonus,
            "mastery_resist": self.mastery_resist,
            "visited_locations": self.visited_locations,
            "discovered_landmarks": self.discovered_landmarks,
            "power_last_day": self.power_last_day, "tower_key_charge": self.tower_key_charge,
            "shop_stock": self.shop_stock, "shop_restock_at": self.shop_restock_at,
            "city_standing": self.city_standing, "thaneships": self.thaneships,
            "allegiance": self.allegiance, "faction_standing": self.faction_standing,
            "dialogue_done": self.dialogue_done,
            "city_faction": self.city_faction,
            "garrison_current": self.garrison_current, "siege_ops": self.siege_ops,
            "tax_due_at": self.tax_due_at, "stewards": self.stewards,
            "world_faction": self.world_faction, "world_events_fired": self.world_events_fired,
            "world_pulse_day": self.world_pulse_day, "pulse_eval_day": self.pulse_eval_day,
            "war_tick_at": self.war_tick_at, "city_threat": self.city_threat,
            "soldiers": self.soldiers, "camp": self.camp,
            "wage_due_at": self.wage_due_at,
            "houses_owned": self.houses_owned, "house_stash": self.house_stash,
            "house_upgrades": self.house_upgrades, "house_garden_at": self.house_garden_at,
            "well_rested_until": self.well_rested_until, "well_rested": self.well_rested,
            "mounts_owned": self.mounts_owned, "active_mount": self.active_mount,
            "companions": self.companions, "pending_companions": self.pending_companions,
            "companion_hp": self.companion_hp, "companion_bond": self.companion_bond,
            "companion_gear": self.companion_gear, "companion_build": self.companion_build,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        # 向後相容:耐久/修理系統已移除 → 剝除舊存檔的對應欄位(cls(**d) 不容許多餘 kwargs)
        d.pop("weapon_condition", None)
        d.pop("armor_condition", None)
        # armorer 技能已移除 → 剝掉殘留鍵,免得他處迭代 char.skills 時撞 gamedata.skills KeyError
        for key in ("skills", "skill_xp"):
            val = d.get(key)
            if isinstance(val, dict):
                val.pop("armorer", None)
        if isinstance(d.get("major_skills"), list):   # 舊戰士/弓手主修含 armorer → 一併剝(免死資料回寫存檔)
            d["major_skills"] = [s for s in d["major_skills"] if s != "armorer"]
        return cls(**d)
