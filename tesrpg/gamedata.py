"""載入 data/ 下的靜態定義(種族、星座、職業、技能、名字)。

程式邏輯只讀這裡;要新增內容改 JSON 即可,不必動程式。
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


class GameData:
    def __init__(self) -> None:
        self.skills: dict = _load("skills.json")
        self.races: dict = _load("races.json")
        self.birthsigns: dict = _load("birthsigns.json")
        self.classes: dict = _load("classes.json")
        self.names: dict = _load("names.json")
        self.weapons: dict = _load("weapons.json")
        self.armor: dict = _load("armor.json")
        self.armor_sets: dict = _load("armor_sets.json")   # 材質 → 套裝加成
        self.bestiary: dict = _load("bestiary.json")
        self.world: dict = _load("world.json")
        self.dungeons: dict = _load("dungeons.json")
        self.spells: dict = _load("spells.json")
        self.ingredients: dict = _load("ingredients.json")
        self.factions: dict = _load("factions.json")
        self.quests: dict = _load("quests.json")
        self.npcs: dict = _load("npcs.json")
        self.events: dict = _load("events.json")
        self.companions: dict = _load("companions.json")
        self.origins: dict = _load("origins.json")   # 開局背景(不一樣的人生)
        self.rulers: dict = _load("rulers.json")     # 各城統治者(湮滅期大空位、各城自治;城戰前置)
        self.mastery: list = _load("mastery.json")   # 技能里程碑(達門檻自動解鎖;見 systems/mastery.py)
        self.recipes: dict = _load("recipes.json")   # 製作配方(獸皮等原料 → 裝備;見 systems/crafting.py)
        self.world_events: dict = _load("world_events.json")   # 陣營大事件時間軸(動態政局;見 systems/worldstate.py)
        self._misc: dict = _load("items.json")

        # 統一物品索引:武器/護甲/雜項/材料共用一份 {id: {**def, "kind": ...}}
        self.items: dict = {}
        for iid, d in self.weapons.items():
            self.items[iid] = {**d, "kind": "weapon"}
        for iid, d in self.armor.items():
            self.items[iid] = {**d, "kind": "armor"}
        for iid, d in self._misc.items():
            self.items[iid] = dict(d)  # 已自帶 kind
        for iid, d in self.ingredients.items():
            self.items[iid] = {**d, "kind": "ingredient"}

    # --- 便捷查詢 ---------------------------------------------------------
    def skill_name(self, skill_id: str) -> str:
        return self.skills[skill_id]["name"]

    def skill_attr(self, skill_id: str) -> str:
        return self.skills[skill_id]["attr"]

    def skills_by_spec(self, spec: str) -> list[str]:
        return [sid for sid, s in self.skills.items() if s["spec"] == spec]

    def all_skill_ids(self) -> list[str]:
        return list(self.skills.keys())

    def item(self, item_id: str) -> dict:
        from tesrpg import synth
        if synth.is_synth(item_id):
            return synth.synthesize(item_id, self)
        return self.items[item_id]

    def item_name(self, item_id: str) -> str:
        return self.item(item_id)["name"]   # 經 item() 以支援合成物品(藥水/毒藥/附魔)

    def location(self, loc_id: str) -> dict:
        return self.world["locations"][loc_id]

    def npcs_at(self, loc_id: str) -> list[str]:
        return [nid for nid, n in self.npcs.items() if n["location"] == loc_id]

    def ruler_at(self, loc_id: str) -> dict | None:
        """該地點的統治者(無則 None;荒野/地城本就無城主)。"""
        return self.rulers.get(loc_id)


# 單一共享實例(資料是唯讀的,全程式共用一份即可)
_INSTANCE: GameData | None = None


def get_gamedata() -> GameData:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = GameData()
    return _INSTANCE
