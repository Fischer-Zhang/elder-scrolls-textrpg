"""戴德拉誓福 —— 戴德拉親王神殿任務的永久回報(R45;systems 層,資料驅動)。

劇情:主角為某位戴德拉親王完成試煉,獲賜一縷永恆之力。
機制:一個通用的**永久獨立疊加層** `boon_*`,模式比照吸血鬼/狼人/斯庫瑪/達貢層 ——
  - 成長/夾限只用 base_attr()/base_skill();此層只疊在 attr()/skill()/entity_resist()/max_magicka 上,**絕不寫回 base**。
  - 與裝備/吸血鬼/狼人/斯庫瑪/達貢層各自獨立相加、互不寫回(R19/R20/R26 同模式)。
  - 可同時持有多位親王的誓福(`char.boons` 為權威 list)→ 四個快取由「持有清單 ∩ boons.json 登錄表」決定性聚合。

達貢誓福(主線慘勝)刻意維持其獨立的 `dagon_*` 層(`systems/dagon_boon.py`)不動,敘事與此通用層分離;
新戴德拉親王誓福一律走此層 + `data/boons.json` 登錄表(由 `reward.grant_boon` 授予,quests._complete 派發)。

校準守則(紅線):每個誓福比照達貢 —— **絕不寫 sneak/任何武器技能**(不餵偷襲倍率)、strength 類 ≤ 達貢 +18,
只加 屬性/抗性/非武器技能/魔力 → solo BOSS 偷襲夾與群體反制不受影響,`sim_assassin` byte-identical。
"""
from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats


def has_boon(char: Character, boon_id: str) -> bool:
    return boon_id in getattr(char, "boons", [])


def apply_to_character(char: Character, gamedata: GameData) -> None:
    """依 `char.boons` 重算 boon_* 四層並重算衍生資源(吃進有效上限)。

    由「持有清單 ∩ boons.json 登錄表」決定性聚合(同 mastery/potion 快取模式);
    未知 boon id 靜默跳過(防呆:陳舊/毀損存檔安全)。冪等,可安全重複呼叫。
    """
    attr: dict[str, int] = {}
    skill: dict[str, int] = {}
    resist: dict[str, int] = {}
    magicka = 0
    spell_power = 0.0
    registry = getattr(gamedata, "boons", {}) or {}
    for bid in getattr(char, "boons", []):
        spec = registry.get(bid)
        if not spec:
            continue   # 未知/陳舊 id → 略過(R03 防禦)
        for k, v in spec.get("attr", {}).items():
            attr[k] = attr.get(k, 0) + v
        for k, v in spec.get("skill", {}).items():
            skill[k] = skill.get(k, 0) + v
        for k, v in spec.get("resist", {}).items():
            resist[k] = resist.get(k, 0) + v
        magicka += spec.get("magicka", 0)
        spell_power += spec.get("spell_power", 0.0)   # R78b 法術威力誓福層(乘進 magic._power)
    char.boon_attr_bonus = attr
    char.boon_skill_bonus = skill
    char.boon_resist = resist
    char.boon_magic_bonus = magicka
    char.boon_spell_power = spell_power
    # attr()/max_magicka 已含 boon_* → 重算讓屬性流進衍生資源、魔力流進 max_magicka。
    stats.recompute_max_resources(char, gamedata)


def grant(char: Character, gamedata: GameData, boon_id: str) -> None:
    """授予某位戴德拉親王的誓福(神殿任務結局)。加入持有清單(去重)並立即生效。"""
    if char.boons is None:
        char.boons = []
    if boon_id not in char.boons:
        char.boons.append(boon_id)
    apply_to_character(char, gamedata)


def ensure_boon_fields(char: Character, gamedata: GameData) -> None:
    """舊存檔遷移:補欄 + 依持有清單重算層(冪等)。"""
    if getattr(char, "boons", None) is None:
        char.boons = []
    for fld in ("boon_attr_bonus", "boon_skill_bonus", "boon_resist"):
        if getattr(char, fld, None) is None:
            setattr(char, fld, {})
    if getattr(char, "boon_magic_bonus", None) is None:
        char.boon_magic_bonus = 0
    if getattr(char, "boon_spell_power", None) is None:
        char.boon_spell_power = 0.0
    apply_to_character(char, gamedata)
