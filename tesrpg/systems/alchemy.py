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
# 有害效果(文件用;實際路由見 brew 的字串分支)。優先序:麻痺>懼意>遲緩>衰減>持續傷害。
# 特殊毒型(fear/slow/damage_strength)需里程碑解鎖(R31),否則退回 damage_health DoT。
HARMFUL = {"paralyze", "fear", "slow", "damage_strength", "damage_health"}
POTION_BUFF_BASE_HOURS = 2   # 限時增益藥水基礎時長(× factor 隨煉金/濃縮縮放),見 R30


def _is_buff_kind(k: str) -> bool:
    """限時增益效果 kind(R30;參數內嵌:fattr_<屬性>/fskill_<技能>/resist_<元素>)。
    以 kind 比對的「共有效果」偵測天然要求同參數才算共有(力量藥材 ≠ 敏捷藥材)。"""
    return k.startswith(("fattr_", "fskill_", "resist_"))


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
    sk = char.skill("alchemy")
    unlocked = mastery.poison_unlocks(char, gamedata)        # 里程碑解鎖的特殊毒型(weaken/slow/fear)
    dur_bonus = mastery.poison_duration_bonus(char, gamedata)  # 「劇毒淬煉」毒效延長回合

    def _pct(k):   # 衰毒/遲緩毒百分比:材料量值輕度隨煉金縮放,夾 10..35
        return max(10, min(35, round((eff_a[k] + eff_b[k]) / 2.0 * (0.5 + sk / 200.0))))

    # 有害共通效果 → 毒藥。優先序:麻痺 > 懼意 > 遲緩 > 衰減 > 持續傷害(特殊毒型需里程碑解鎖,
    # 否則因特殊材料皆兼具 damage_health → 自然退回基礎 DoT,材料永不淪為死內容)。
    if "paralyze" in shared:
        turns = max(1, min(3, 1 + sk // 50))
        item_id = synth.poison_id("paralyze", turns)
        result_kind = "poison"
    elif "fear" in shared and "fear" in unlocked:
        turns = max(1, min(2, 1 + sk // 60))
        item_id = synth.poison_id("fear", turns)
        result_kind = "poison"
    elif "slow" in shared and "slow" in unlocked:
        item_id = synth.poison_id("slow", _pct("slow"), 2 + dur_bonus)
        result_kind = "poison"
    elif "damage_strength" in shared and "weaken" in unlocked:
        item_id = synth.poison_id("weaken", _pct("damage_strength"), 2 + dur_bonus)
        result_kind = "poison"
    elif "damage_health" in shared:
        per_turn = max(1, round((eff_a["damage_health"] + eff_b["damage_health"]) / 2.0 * factor))
        item_id = synth.poison_id("dot", per_turn, 3 + dur_bonus)
        result_kind = "poison"
    else:
        # 有益共通效果:限時增益(強化屬性/技能/抗元素)優先於即時回復藥水
        buff_kinds = [k for k in shared if _is_buff_kind(k)]
        restore_kinds = shared & RESTORATIVE
        if buff_kinds:
            kind = max(buff_kinds, key=lambda k: eff_a[k] + eff_b[k])
            magnitude = max(1, round((eff_a[kind] + eff_b[kind]) / 2.0 * factor))
            dur = max(1, round(POTION_BUFF_BASE_HOURS * factor))   # 藥效時長(編入 id),非釀造耗時(hours)
            item_id = synth.brew_buff_id(kind, magnitude, dur)
            result_kind = "buff"
        elif restore_kinds:
            kind = max(restore_kinds, key=lambda k: eff_a[k] + eff_b[k])
            magnitude = max(1, round((eff_a[kind] + eff_b[kind]) / 2.0 * factor))
            item_id = synth.brew_id(kind, magnitude)
            result_kind = "potion"
        else:
            # 防呆:共有效果不屬有害/增益/回復(現有資料不會發生;留給未來新 kind 不致 max() 空集崩潰)
            return {"ok": False, "message": "兩種材料的效果無法調合,化作一灘廢液。",
                    "hours": hours, "tired": tired, "skill_events": events}

    inventory.add_item(char, item_id, 1)
    name = gamedata.item(item_id)["name"]
    verb = ("煉出了一瓶毒藥" if result_kind == "poison"
            else "調出了一瓶增益藥劑" if result_kind == "buff"
            else "調出了一瓶藥水")
    return {"ok": True, "kind": result_kind, "message": f"你{verb}:{name}。",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events}
