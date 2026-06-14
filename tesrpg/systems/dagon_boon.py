"""達貢之力 —— 湮滅危機「神話黎明教徒結局」的慘勝獎賞(systems 層)。

劇情:達貢獻祭全教徒以現世,主角逆轉法陣自保、擊敗削弱的達貢,竊得湮滅之君的一縷殘力。
機制:一個全新的**永久獨立疊加層** `dagon_*`,模式比照吸血鬼/狼人/斯庫瑪層 ——
  - 成長/夾限只用 base_attr()/base_skill();此層只疊在 attr()/skill()/entity_resist()/max_magicka 上,**絕不寫回 base**。
  - 與吸血鬼/狼人/斯庫瑪層各自獨立相加、互不寫回(R19/R20 同模式)。
  - 一次性永久(無 upkeep、不退):由主線任務 `md7` 完成時 `grant()`。
校準:介於吸血鬼 T3(+45 attr/+30 skill)與狼人 T4 之間;達貢=毀滅/烈焰/野心 →
  力量/意志/耐力 + 毀滅/咒術 + 火抗 + 魔力。**刻意不碰 sneak/武傷倍率**(守 R20 精神,避刺客紅線)。
"""
from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats

# 達貢之力的永久加成(竊得湮滅之君殘力)。
DAGON_ATTR = {"strength": 18, "willpower": 12, "endurance": 12}   # 野心/意志/堅韌(+42)
DAGON_SKILL = {"destruction": 10, "conjuration": 8}               # 湮滅之君的領域:毀滅 + 咒術
DAGON_RESIST = {"fire": 60}                                       # 烈焰之主 → 近乎耐火(非全免)
DAGON_MAGICKA = 25                                               # 永久魔力上限


def has_boon(char: Character) -> bool:
    return bool(getattr(char, "dagon_boon", False))


def apply_to_character(char: Character, gamedata: GameData) -> None:
    """依 `char.dagon_boon` flag 重算 dagon_* 層並重算衍生資源(吃進有效上限)。

    未持有則清空所有 dagon 加成(冪等;可安全重複呼叫)。
    """
    if has_boon(char):
        char.dagon_attr_bonus = dict(DAGON_ATTR)
        char.dagon_skill_bonus = dict(DAGON_SKILL)
        char.dagon_resist = dict(DAGON_RESIST)
        char.dagon_magic_bonus = DAGON_MAGICKA
    else:
        char.dagon_attr_bonus = {}
        char.dagon_skill_bonus = {}
        char.dagon_resist = {}
        char.dagon_magic_bonus = 0
    # attr() 已含 dagon_attr_bonus → 重算讓 力量/意志/耐力 流進 max_fatigue、魔力流進 max_magicka
    stats.recompute_max_resources(char, gamedata)


def grant(char: Character, gamedata: GameData) -> None:
    """竊得達貢之力(主線 md7 結局)。設定永久 flag 並立即生效。"""
    char.dagon_boon = True
    apply_to_character(char, gamedata)


def ensure_dagon_fields(char: Character, gamedata: GameData) -> None:
    """舊存檔遷移:補欄 + 依 flag 重算層(冪等)。"""
    if getattr(char, "dagon_boon", None) is None:
        char.dagon_boon = False
    for fld in ("dagon_attr_bonus", "dagon_skill_bonus", "dagon_resist"):
        if getattr(char, fld, None) is None:
            setattr(char, fld, {})
    if getattr(char, "dagon_magic_bonus", None) is None:
        char.dagon_magic_bonus = 0
    apply_to_character(char, gamedata)
