"""戰利品結算:怪物掉落、寶箱內容,共用同一套 loot 條目格式。

loot 條目可為:
  - "iron_sword"                      保證掉落該物品
  - {"item": "iron_sword", "chance": 0.25}   機率掉落
  - {"gold": [lo, hi]}                掉落隨機金幣
回傳 {"items": [(item_id, qty), ...], "gold": int}
"""

from __future__ import annotations

from tesrpg.rng import RNG


def resolve_loot(entries: list, rng: RNG) -> dict:
    items: list[tuple[str, int]] = []
    gold = 0
    for e in entries or []:
        if isinstance(e, str):
            items.append((e, 1))
        elif "gold" in e:
            lo, hi = e["gold"]
            gold += rng.randint(lo, hi) if hi >= lo else 0
        elif "item" in e:
            if rng.chance(e.get("chance", 1.0)):
                items.append((e["item"], e.get("qty", 1)))
    return {"items": items, "gold": gold}


def creature_loot(creature, rng: RNG) -> dict:
    """怪物掉落 = loot_gold 範圍 + loot 機率表。"""
    lo, hi = creature.loot_gold
    entries: list = [{"gold": [lo, hi]}]
    entries += getattr(creature, "loot_table", None) or []
    return resolve_loot(entries, rng)
