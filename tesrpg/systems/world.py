"""世界地圖、旅行、商店與訓練師的規則。

地圖是「地點圖」:每個地點有若干通往他處的連結(各帶旅行時數)。
旅行會推進時間,並可能在途中觸發遭遇。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import combat, progression


# --- 地點 / 旅行 --------------------------------------------------------
def current_location(char: Character, gamedata: GameData) -> dict:
    return gamedata.location(char.location_id)


def travel_options(char: Character, gamedata: GameData) -> list[tuple[str, int]]:
    """回傳 [(目的地 id, 旅行時數), ...]。"""
    loc = current_location(char, gamedata)
    return list(loc.get("links", {}).items())


def encounter_chance(dest_danger: int, hour: int) -> float:
    if dest_danger <= 0:
        return 0.0
    chance = dest_danger * 0.18
    if hour < 6 or hour >= 21:        # 夜間更危險
        chance += 0.10
    return min(0.85, chance)


def travel(char: Character, gamedata: GameData, dest_id: str, time, rng: RNG) -> dict:
    """執行旅行:依運動加速耗時、推進時間、移動、鍛鍊運動。

    回傳 {"foe":遭遇 Creature 或 None, "hours":實際耗時, "base_hours":名目耗時,
          "skill_events":運動升點事件}。遭遇尚未開打 —— 由上層決定接戰/逃避。
    """
    links = current_location(char, gamedata).get("links", {})
    base_hours = links[dest_id]
    hours = max(1, round(base_hours * formulas.athletics_travel_factor(char.skill("athletics"))))
    dest = gamedata.location(dest_id)

    foe = None
    if rng.chance(encounter_chance(dest.get("danger", 0), time.hour)):
        foe = combat.random_encounter(gamedata, char.level, rng,
                                      max_danger=dest.get("danger", 1) + 1,
                                      biome=dest.get("biome"))

    time.advance(hours)
    char.location_id = dest_id
    skill_events = progression.use_skill(char, gamedata, "athletics", formulas.ATHLETICS_TRAVEL_XP)
    return {"foe": foe, "hours": hours, "base_hours": base_hours, "skill_events": skill_events}


# --- 商店定價(受 交易 + 魅力 影響)-----------------------------------
def _disposition_factor(char: Character) -> float:
    return max(0.0, min(1.0, (char.skill("mercantile") + char.attr("personality") * 0.5) / 150.0))


def buy_price(char: Character, gamedata: GameData, item_id: str) -> int:
    value = gamedata.item(item_id)["value"]
    return max(1, round(value * (2.2 - _disposition_factor(char))))


def sell_price(char: Character, gamedata: GameData, item_id: str) -> int:
    from tesrpg.systems import factions
    value = gamedata.item(item_id)["value"]
    base = value * (0.3 + _disposition_factor(char) * 0.5)
    base *= 1 + factions.sell_bonus(char, gamedata)   # 盜賊公會銷贓加成(階級越高越多)
    return max(1, round(base))


# --- 訓練師 -------------------------------------------------------------
def train_cost(skill_level: int) -> int:
    return max(20, skill_level * 8)


# --- 法師公會 -----------------------------------------------------------
def spell_price(gamedata: GameData, spell_id: str) -> int:
    return max(25, gamedata.spells[spell_id]["cost"] * 12)


# --- 鐵匠修理 -----------------------------------------------------------
def repair_fee() -> int:
    return 15
