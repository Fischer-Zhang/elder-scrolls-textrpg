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
        self.dialogue: dict = _load("dialogue.json")   # 條件式對話樹(問候/話題/模板;見 systems/dialogue.py)
        self.companions: dict = _load("companions.json")
        self.origins: dict = _load("origins.json")   # 開局背景(不一樣的人生)
        self.rulers: dict = _load("rulers.json")     # 各城統治者(湮滅期大空位、各城自治;城戰前置)
        self.houses: dict = {k: v for k, v in _load("houses.json").items()
                             if not k.startswith("_")}   # 可購置房產(key=location_id;見 systems/housing.py)
        _mounts_data: dict = _load("mounts.json")    # 坐騎(分三類)+ 馬廄城 + 長槍販售(見 systems/mounts.py)
        self.mounts: dict = _mounts_data["mounts"]
        self.stable_cities: set = set(_mounts_data.get("stable_cities", []))
        self.stable_spears: list = _mounts_data.get("spear_stock", [])
        self.trainers: dict = {k: v for k, v in _load("trainers.json").items()
                               if not k.startswith("_")}   # 訓練師專精/宗師(key=location_id;全 OPTIONAL,見 systems/world.trainer_*)
        self.mastery: list = _load("mastery.json")   # 技能里程碑(達門檻自動解鎖;見 systems/mastery.py)
        self.recipes: dict = _load("recipes.json")   # 製作配方(獸皮等原料 → 裝備;見 systems/crafting.py)
        self.world_events: dict = _load("world_events.json")   # 陣營大事件時間軸(動態政局;見 systems/worldstate.py)
        self.world_pulse: dict = _load("world_pulse.json")   # 常態世界脈動情境(動態新聞 + 聚光激增可重複委託;見 systems/worldpulse.py)
        self.landmarks: dict = _load("landmarks.json")   # 具名地標(首次抵達一次性發現;見 systems/landmarks.py)
        self.boons: dict = _load("boons.json")   # 戴德拉誓福登錄表(神殿任務永久回報;R45,見 systems/boons.py)
        self.diseases: dict = _load("diseases.json")   # 疾病登錄表(普通病懲罰層;R53,見 systems/diseases.py)
        self.achievements: list = _load("achievements.json")   # 成就(達門檻自動表彰;唯讀推導,見 systems/achievements.py)
        self.codex: dict = _load("codex.json")   # 遊戲內指南/圖鑑(唯讀 how-to 內容;R60,見 main.action_codex/ui.codex_panel)
        self.ecology: dict = _load("alchemical_ecology.json")   # 生態系 → 煉金材料池(野採 forage_pool 抽取;R93,見 systems/events.forage_pool_draw)
        self.necromancy: dict = _load("necromancy.json")   # 永久死靈升級目錄(靈魂 token 買斷;R106C,見 systems/necromancy.buy_upgrade)
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

    def item_or_none(self, item_id: str) -> dict | None:
        """毀損/未知 id 回 None(不拋例外)→ 供顯示/彙整路徑防禦毀損存檔(見 §3)。"""
        try:
            return self.item(item_id)
        except KeyError:
            return None

    def item_name(self, item_id: str) -> str:
        d = self.item_or_none(item_id)   # 經 item() 以支援合成物品;毀損 id 回原字串不崩潰
        return d["name"] if d else item_id

    def location(self, loc_id: str) -> dict:
        return self.world["locations"][loc_id]

    def npcs_at(self, loc_id: str) -> list[str]:
        return [nid for nid, n in self.npcs.items() if n["location"] == loc_id]

    def ruler_at(self, loc_id: str) -> dict | None:
        """該地點的統治者(無則 None;荒野/地城本就無城主)。"""
        return self.rulers.get(loc_id)

    def landmark_at(self, loc_id: str) -> dict | None:
        """該地點的具名地標(無則 None;首次抵達觸發一次性發現)。"""
        return self.landmarks.get(loc_id)

    def house_at(self, loc_id: str) -> dict | None:
        """該地點可購置的房產(無則 None;見 systems/housing.py)。"""
        return self.houses.get(loc_id)

    def mount(self, mount_id: str) -> dict | None:
        """坐騎定義(無/未知 id 回 None;見 systems/mounts.py)。"""
        return self.mounts.get(mount_id)

    def has_stable(self, loc_id: str) -> bool:
        """該城是否有馬廄(售坐騎與長槍)。"""
        return loc_id in self.stable_cities

    def trainer_data(self, loc_id: str) -> dict | None:
        """該城訓練師專精/宗師覆寫(無則 None;見 systems/world.trainer_*)。"""
        return self.trainers.get(loc_id)


# 單一共享實例(資料是唯讀的,全程式共用一份即可)
_INSTANCE: GameData | None = None


def get_gamedata() -> GameData:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = GameData()
        # 程序化補齊領主委託(讓每座有領主的城/鎮都能受封武士);先設 _INSTANCE 再呼叫,
        # 避免 court→quests 等模組於匯入期回呼 get_gamedata 造成遞迴。手寫委託會被保留。
        from tesrpg.systems import court
        court.generate_ruler_commissions(_INSTANCE)
    return _INSTANCE
