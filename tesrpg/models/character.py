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
    weapon_condition: float = 100.0          # 武器耐久 0–100(影響傷害)
    armor_condition: dict = field(default_factory=dict)  # {slot: 耐久 0–100}
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
    cleared_dungeons: list = field(default_factory=list)
    bounties: dict = field(default_factory=dict)          # province -> 賞金
    npc_disposition: dict = field(default_factory=dict)   # npc_id -> 好感

    # M6:一生軌跡(供傳奇總結)
    visited_locations: list = field(default_factory=list)
    discovered_landmarks: list = field(default_factory=list)   # 已觸發首次發現的地標 loc_id(一次性守門)

    # M12:隊伍(雇用的傭兵同伴 template id;戰鬥時為你而戰)
    companions: list = field(default_factory=list)

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
    city_faction: dict = field(default_factory=dict)      # loc_id -> 現時歸屬立場(攻城會翻轉)
    garrison_current: dict = field(default_factory=dict)  # loc_id -> 現存駐軍(圍城方略消耗;佔領後=你的駐軍,叛亂計時會緩降)
    siege_ops: dict = field(default_factory=dict)         # loc_id -> [已施行的圍城方略 id](每役每略一次)
    # 城戰階段三:佔領後收稅(按居民數量)− 駐軍維護費 + 輕量叛亂計時(駐軍緩降,潰散則城叛)。詳見 systems/politics.py。
    tax_due_at: dict = field(default_factory=dict)         # loc_id -> 下次徵稅的絕對小時(僅攻下的城;預設 {} 向後相容)
    # 陣營大事件(動態政局):事件驅動的城邦易幟層 + 已觸發大事件。詳見 systems/worldstate.py(階段 C)。
    world_faction: dict = field(default_factory=dict)      # loc_id -> 大事件易幟的立場(覆蓋種子;玩家征服 city_faction 優先)
    world_events_fired: list = field(default_factory=list) # 已觸發的大事件 id(once-fire + 解鎖判定,如神話黎明)

    # 招兵買馬(城戰的金幣/領袖路線)。親衛/將領=companions(具名);軍隊/士兵=抽象兵員。詳見 systems/warband.py。
    soldiers: int = 0                                     # 麾下士兵數(營地招募;攻城當援軍 + 大軍壓境)
    camp: str = ""                                        # 營地所在 loc_id(野外紮營 / 佔領已清空地城);""=未建
    wage_due_at: int = 0                                  # 下次發軍餉的絕對小時(階段二;0=無兵/未開始計餉)

    is_player: bool = False

    # --- 查詢 -------------------------------------------------------------
    def attr(self, key: str) -> int:
        return (self.attributes.get(key, formulas.BASE_ATTRIBUTE)
                + self.equip_attr_bonus.get(key, 0) + self.vampire_attr_bonus.get(key, 0)
                + self.mastery_attr_bonus.get(key, 0) + self.skooma_attr_bonus.get(key, 0)
                + self.werewolf_attr_bonus.get(key, 0))

    def skill(self, key: str) -> int:
        return (self.skills.get(key, 0)
                + self.equip_skill_bonus.get(key, 0) + self.vampire_skill_bonus.get(key, 0)
                + self.mastery_skill_bonus.get(key, 0) + self.skooma_skill_bonus.get(key, 0)
                + self.werewolf_skill_bonus.get(key, 0))

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
            "weapon_poison": self.weapon_poison,
            "weapon_condition": self.weapon_condition, "armor_condition": self.armor_condition,
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
            "is_werewolf": self.is_werewolf, "werewolf_infected_day": self.werewolf_infected_day,
            "beast_form": self.beast_form, "beast_form_until": self.beast_form_until,
            "beast_feeds": self.beast_feeds, "werewolf_total_feeds": self.werewolf_total_feeds,
            "werewolf_attr_bonus": self.werewolf_attr_bonus,
            "werewolf_skill_bonus": self.werewolf_skill_bonus,
            "werewolf_resist": self.werewolf_resist,
            "werewolf_health_bonus": self.werewolf_health_bonus,
            "factions": self.factions,
            "murders": self.murders, "db_invited": self.db_invited,
            "murdered_npcs": self.murdered_npcs,
            # active_effects 是「戰鬥內」臨時效果(護盾/中毒/再生),不寫入存檔,
            # 載入時由 dataclass 預設為空 list(避免臨時效果被永久化)。
            "fame": self.fame, "infamy": self.infamy, "bounty": self.bounty,
            "disposition": self.disposition, "is_player": self.is_player,
            "quests": self.quests, "completed_quests": self.completed_quests,
            "kill_counts": self.kill_counts, "cleared_dungeons": self.cleared_dungeons,
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
            "allegiance": self.allegiance, "city_faction": self.city_faction,
            "garrison_current": self.garrison_current, "siege_ops": self.siege_ops,
            "tax_due_at": self.tax_due_at,
            "world_faction": self.world_faction, "world_events_fired": self.world_events_fired,
            "soldiers": self.soldiers, "camp": self.camp,
            "wage_due_at": self.wage_due_at,
            "companions": self.companions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        return cls(**d)
