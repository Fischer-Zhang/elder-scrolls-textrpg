"""衍生數值的重算與夾限。

生命上限基底(base_max_health)= 創建耐力×2,不隨耐力逐級長(消除耐力時機陷阱);
魔力/體力上限可由當前屬性直接推得,屬性一變就重算。
有效上限 = 基底/公式 + 升級三選一累積(resource_levels)+ 穿戴護甲 armor_fortify(需 gamedata)。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.models import Character


def ensure_base_health(char: Character) -> None:
    """舊存檔遷移:沒有 base_max_health 欄位(預設 0)時,以現有 max_health 當基底。

    舊存檔從未有過護甲 fortify,故當時的 max_health 即純基底,直接搬過來不會失真。
    必須在任何「加到 base_max_health」之前呼叫(例:升級),以免基底被誤判為 0。
    """
    if char.base_max_health <= 0 < char.max_health:
        char.base_max_health = char.max_health


def recompute_max_resources(char: Character, gamedata=None,
                            restore_full: bool = False) -> None:
    ensure_base_health(char)
    fort: dict[str, int] = {}
    if gamedata is not None:
        from tesrpg.systems import inventory   # 區域 import:避免與 inventory→stats 形成循環
        fort = inventory.armor_fortify_totals(char, gamedata)

    res = char.resource_levels   # 升級三選一累積的資源加成
    char.max_health = char.base_max_health + res.get("health", 0) + fort.get("health", 0)
    char.max_magicka = (formulas.max_magicka(char.attr("intelligence"), char.magicka_bonus)
                        + res.get("magicka", 0) + fort.get("magicka", 0))
    char.max_fatigue = (formulas.max_fatigue(
        char.attr("strength"), char.attr("willpower"),
        char.attr("agility"), char.attr("endurance"),
    ) + res.get("fatigue", 0) + fort.get("fatigue", 0))

    if restore_full:
        char.health = char.max_health
        char.magicka = char.max_magicka
        char.fatigue = char.max_fatigue
    clamp_resources(char)


def clamp_resources(char: Character) -> None:
    char.health = max(0, min(char.health, char.max_health))
    char.magicka = max(0, min(char.magicka, char.max_magicka))
    char.fatigue = max(0, min(char.fatigue, char.max_fatigue))
