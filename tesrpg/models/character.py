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
    factions: dict = field(default_factory=dict)         # faction_id -> 階級索引(已入會)
    active_effects: list = field(default_factory=list)
    fame: int = 0
    infamy: int = 0
    bounty: int = 0
    disposition: int = 50

    # M5:任務、犯罪、聲望追蹤
    quests: dict = field(default_factory=dict)            # quest_id -> {"progress":...}
    completed_quests: list = field(default_factory=list)
    kill_counts: dict = field(default_factory=dict)       # creature_tid -> 擊殺數
    cleared_dungeons: list = field(default_factory=list)
    bounties: dict = field(default_factory=dict)          # province -> 賞金
    npc_disposition: dict = field(default_factory=dict)   # npc_id -> 好感

    # M6:一生軌跡(供傳奇總結)
    visited_locations: list = field(default_factory=list)

    # M12:隊伍(雇用的傭兵同伴 template id;戰鬥時為你而戰)
    companions: list = field(default_factory=list)

    # M8:出生星座能力(每日一次)冷卻 + 塔之鑰開鎖充能
    power_last_day: dict = field(default_factory=dict)    # power_id -> 上次使用的絕對日
    tower_key_charge: bool = False

    is_player: bool = False

    # --- 查詢 -------------------------------------------------------------
    def attr(self, key: str) -> int:
        return (self.attributes.get(key, formulas.BASE_ATTRIBUTE)
                + self.equip_attr_bonus.get(key, 0) + self.vampire_attr_bonus.get(key, 0))

    def skill(self, key: str) -> int:
        return (self.skills.get(key, 0)
                + self.equip_skill_bonus.get(key, 0) + self.vampire_skill_bonus.get(key, 0))

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
            "location_id": self.location_id,
            "inventory": self.inventory, "equipped": self.equipped, "spells": self.spells,
            "equip_skill_bonus": self.equip_skill_bonus, "equip_attr_bonus": self.equip_attr_bonus,
            "equip_resist": self.equip_resist,
            "is_vampire": self.is_vampire, "vampire_infected_day": self.vampire_infected_day,
            "vampire_fed_day": self.vampire_fed_day, "vampire_stage": self.vampire_stage,
            "vampire_attr_bonus": self.vampire_attr_bonus,
            "vampire_skill_bonus": self.vampire_skill_bonus, "vampire_resist": self.vampire_resist,
            "factions": self.factions,
            # active_effects 是「戰鬥內」臨時效果(護盾/中毒/再生),不寫入存檔,
            # 載入時由 dataclass 預設為空 list(避免臨時效果被永久化)。
            "fame": self.fame, "infamy": self.infamy, "bounty": self.bounty,
            "disposition": self.disposition, "is_player": self.is_player,
            "quests": self.quests, "completed_quests": self.completed_quests,
            "kill_counts": self.kill_counts, "cleared_dungeons": self.cleared_dungeons,
            "bounties": self.bounties, "npc_disposition": self.npc_disposition,
            "visited_locations": self.visited_locations,
            "power_last_day": self.power_last_day, "tower_key_charge": self.tower_key_charge,
            "companions": self.companions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        return cls(**d)
