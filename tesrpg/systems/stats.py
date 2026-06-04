"""衍生數值的重算與夾限。

生命上限是「累積」的(創建時設定、升級時累加),所以不在這裡重算;
魔力/體力上限可由當前屬性直接推得,屬性一變就重算。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.models import Character


def recompute_max_resources(char: Character, restore_full: bool = False) -> None:
    char.max_magicka = formulas.max_magicka(char.attr("intelligence"), char.magicka_bonus)
    char.max_fatigue = formulas.max_fatigue(
        char.attr("strength"), char.attr("willpower"),
        char.attr("agility"), char.attr("endurance"),
    )
    if restore_full:
        char.health = char.max_health
        char.magicka = char.max_magicka
        char.fatigue = char.max_fatigue
    clamp_resources(char)


def clamp_resources(char: Character) -> None:
    char.health = max(0, min(char.health, char.max_health))
    char.magicka = max(0, min(char.magicka, char.max_magicka))
    char.fatigue = max(0, min(char.fatigue, char.max_fatigue))
