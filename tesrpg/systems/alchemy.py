"""煉金:把兩種材料的共通效果調成藥水或毒藥。

共通效果若是「恢復類」(回血/回魔/回體)→ 飲用藥水;
若是「有害類」(毒傷/麻痺)→ 塗抹用毒藥(可塗在武器上,見 inventory.coat_weapon)。
技能越高 → 成品越強。learn-by-doing 鍛鍊煉金。產出為合成物品(見 synth)。
"""

from __future__ import annotations

from tesrpg import synth
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import inventory, progression

BREW_FAIL_FACTOR = 0.5   # 沒煉成(無共通效果)只學到一半的 practice 成效

RESTORATIVE = {"heal", "restore_magicka", "restore_fatigue"}
HARMFUL = {"paralyze", "damage_health"}      # 麻痺優先於毒傷


def ingredient_effects(gamedata: GameData, ing_id: str) -> list[dict]:
    return gamedata.ingredients[ing_id]["effects"]


def brew(char: Character, gamedata: GameData, ing_a: str, ing_b: str, rng: RNG) -> dict:
    """調配 ing_a + ing_b。回傳 {"ok","message","item_id"?,"hours","tired","skill_events"}。

    每次調配付出煉金 practice 的體力 + 時間成本(時間由呼叫端推進),與訓練師/正規練習對齊,
    讓「在煉金台調藥」不再是零時間零體力的免費刷煉金捷徑。
    """
    if ing_a == ing_b or inventory.count_item(char, ing_a) < 1 or inventory.count_item(char, ing_b) < 1:
        return {"ok": False, "message": "材料不足或重複。", "hours": 0, "tired": False, "skill_events": []}

    eff_a = {e["kind"]: e["magnitude"] for e in ingredient_effects(gamedata, ing_a)}
    eff_b = {e["kind"]: e["magnitude"] for e in ingredient_effects(gamedata, ing_b)}
    shared = set(eff_a) & set(eff_b)

    # 無論成敗都消耗材料(煉金的材料代價)+ 付出 practice 的體力/時間
    inventory.remove_item(char, ing_a, 1)
    inventory.remove_item(char, ing_b, 1)
    xp, hours, tired = progression.practice_cost(char, gamedata, "alchemy")

    if not shared:
        events = progression.use_skill(char, gamedata, "alchemy", xp * BREW_FAIL_FACTOR)
        return {"ok": False, "message": "兩種材料沒有共通效果,化作一灘廢液。",
                "hours": hours, "tired": tired, "skill_events": events}

    from tesrpg.systems import mastery
    factor = (0.6 + char.skill("alchemy") / 100.0) * (1 + mastery.potion_potency(char, gamedata))  # 「濃縮萃取」
    events = progression.use_skill(char, gamedata, "alchemy", xp)

    # 有害共通效果 → 毒藥(麻痺優先,其次毒傷);否則 → 恢復藥水
    if "paralyze" in shared:
        turns = max(1, min(3, 1 + char.skill("alchemy") // 50))
        item_id = synth.poison_id("paralyze", turns)
        result_kind = "poison"
    elif "damage_health" in shared:
        per_turn = max(1, round((eff_a["damage_health"] + eff_b["damage_health"]) / 2.0 * factor))
        item_id = synth.poison_id("dot", per_turn, 3)
        result_kind = "poison"
    else:
        kind = max(shared & RESTORATIVE, key=lambda k: eff_a[k] + eff_b[k])
        magnitude = max(1, round((eff_a[kind] + eff_b[kind]) / 2.0 * factor))
        item_id = synth.brew_id(kind, magnitude)
        result_kind = "potion"

    inventory.add_item(char, item_id, 1)
    name = gamedata.item(item_id)["name"]
    verb = "煉出了一瓶毒藥" if result_kind == "poison" else "調出了一瓶藥水"
    return {"ok": True, "kind": result_kind, "message": f"你{verb}:{name}。",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events}
