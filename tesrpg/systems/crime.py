"""犯罪與賞金:行竊、各行省賞金、衛兵盤查。

賞金按「行省 (province)」累計;帶著賞金進城會被衛兵攔下。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import progression, world

JAIL_DAYS_PER_BOUNTY = 0.02   # 每點賞金折算坐牢時數的係數


def province_of(char: Character, gamedata: GameData) -> str:
    return world.current_location(char, gamedata)["province"]


def bounty(char: Character, province: str) -> int:
    return char.bounties.get(province, 0)


def add_bounty(char: Character, province: str, amount: int) -> None:
    char.bounties[province] = char.bounties.get(province, 0) + amount


def clear_bounty(char: Character, province: str) -> None:
    char.bounties[province] = 0


# --- 行竊 ---------------------------------------------------------------
def steal_chance(char: Character, gamedata: GameData) -> float:
    """得手機率:潛行 + 安全為主 + 里程碑「順手牽羊」加成(theft_skill)。夾 [0.05, 0.95]。"""
    from tesrpg.systems import mastery
    base = (0.25 + char.skill("sneak") * 0.005 + char.skill("security") * 0.003
            + mastery.theft_bonus(char, gamedata).get("steal_bonus", 0.0))
    return max(0.05, min(0.95, base))


def steal_item(char: Character, gamedata: GameData, item_id: str, rng: RNG) -> dict:
    """嘗試從商店順手牽羊。回傳 {ok, caught, bounty_added, hours, tired, skill_events}。

    每次嘗試付出潛行 practice 的體力 + 時間成本(由呼叫端推進時間),
    讓行竊不再繞過正規訓練的代價;且**得手才學到手藝**(被抓不給潛行 xp →
    杜絕「故意被抓刷潛行」)。
    """
    from tesrpg.systems import inventory, mastery
    province = province_of(char, gamedata)
    value = gamedata.item(item_id)["value"]
    xp, hours, tired = progression.practice_cost(char, gamedata, "sneak")
    if rng.chance(steal_chance(char, gamedata)):
        inventory.add_item(char, item_id, 1)
        events = progression.use_skill(char, gamedata, "sneak", xp)
        return {"ok": True, "caught": False, "bounty_added": 0,
                "hours": hours, "tired": tired, "skill_events": events}
    bf = mastery.theft_bonus(char, gamedata).get("bounty_factor", 1.0)   # 「順手牽羊」失風賞金減免
    fine = int(round(max(20, value * 2) * bf))
    add_bounty(char, province, fine)
    return {"ok": False, "caught": True, "bounty_added": fine,
            "hours": hours, "tired": tired, "skill_events": []}


# --- 衛兵盤查 -----------------------------------------------------------
def jail_hours(amount: int) -> int:
    return max(6, int(amount * JAIL_DAYS_PER_BOUNTY * 24))


def serve_sentence(char: Character, gamedata: GameData, time) -> dict:
    """入獄服刑:清空當地賞金、推進時間。"""
    province = province_of(char, gamedata)
    amt = bounty(char, province)
    hours = jail_hours(amt)
    time.advance(hours)
    clear_bounty(char, province)
    return {"hours": hours, "cleared": amt}


def pay_fine(char: Character, gamedata: GameData) -> dict:
    province = province_of(char, gamedata)
    amt = bounty(char, province)
    if char.gold < amt:
        return {"ok": False, "owed": amt}
    char.gold -= amt
    clear_bounty(char, province)
    return {"ok": True, "paid": amt}
