"""戰鬥用的怪物/野生敵人。由 data/bestiary.json 模板實例化。

刻意比 Character 簡單:戰鬥只需要少數屬性 + 一種攻擊 + 生命,
不追蹤體力/技能成長(只有玩家會 learn-by-doing)。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Creature:
    template_id: str
    name: str
    strength: int
    agility: int
    speed: int
    max_health: int
    health: float
    armor_rating: int
    attack: dict                       # {"name", "damage", "skill"} —— 後備單招(無 attacks 時用)
    attacks: list = field(default_factory=list)  # 攻擊曲目 [{...attack, "weight"?, "when"?, "cooldown"?}];空=只用 attack
    loot_gold: list = field(default_factory=lambda: [0, 0])
    loot_table: list = field(default_factory=list)   # [{"item","chance"}, ...]
    flavor: str = ""
    danger: int = 1                                  # 用於推導靈魂等級
    resist: dict = field(default_factory=dict)       # {element/"magic"/"poison": 百分比}
    reflect: float = 0.0                             # 物理反傷比例(R117):玩家物理擊中→其完整物理輸出×此回噬玩家(如秩序騎士)
    active_effects: list = field(default_factory=list)  # [{"kind","turns",...}]
    summon_turns: int | None = None                  # 召喚物剩餘回合(None=同伴/非召喚)

    @property
    def is_alive(self) -> bool:
        return self.health > 0
