"""製作:把原料(獸皮等雜貨)依配方加工成裝備。資料驅動(data/recipes.json)。

配方消耗背包原料 → 產出成品,並付出該技能 practice 的體力+時間(與訓練師/正規練習對齊,
不另闢零成本造物或刷技能途徑)。產出為既有真實物品(非合成 id),按一般物價買賣。
新配方純改 recipes.json;`station` 限定工坊(目前 "smith" = 需鐵匠/製革處;None = 隨地可做)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import inventory, progression


def recipes_for_station(gamedata: GameData, station: str | None) -> list[str]:
    """該工坊可做的配方 id;`station` 為 None 的配方隨地可做。"""
    out = []
    for rid, r in gamedata.recipes.items():
        st = r.get("station")
        if st is None or st == station:
            out.append(rid)
    return out


def missing_inputs(char: Character, gamedata: GameData, recipe_id: str) -> dict:
    """回傳 {item_id: 還缺幾個};空 dict = 材料齊備。"""
    r = gamedata.recipes[recipe_id]
    return {iid: need - inventory.count_item(char, iid)
            for iid, need in r["inputs"].items()
            if inventory.count_item(char, iid) < need}


def can_craft(char: Character, gamedata: GameData, recipe_id: str) -> bool:
    return not missing_inputs(char, gamedata, recipe_id)


def meets_skill_req(char: Character, gamedata: GameData, recipe_id: str) -> bool:
    """配方技能門檻:該 `skill` 等級須達 `skill_req`(無 skill_req=0=無門檻;練 smithing 才解鎖高階配方)。"""
    r = gamedata.recipes[recipe_id]
    req = r.get("skill_req", 0)
    sk = r.get("skill")
    return req <= 0 or (bool(sk) and char.skill(sk) >= req)


def craft(char: Character, gamedata: GameData, recipe_id: str) -> dict:
    """依配方加工。回傳 {ok, message, output?, hours, tired, skill_events}。

    材料不足 → ok False、零成本(不扣料/不耗時)。成功 → 扣料、產出、付技能 practice 成本。
    """
    r = gamedata.recipes[recipe_id]
    if not meets_skill_req(char, gamedata, recipe_id):
        return {"ok": False, "message": f"鍛造技能不足(需 {r.get('skill_req', 0)} 級)。",
                "hours": 0, "tired": False, "skill_events": []}
    if not can_craft(char, gamedata, recipe_id):
        return {"ok": False, "message": "材料不足。", "hours": 0, "tired": False, "skill_events": []}
    for iid, need in r["inputs"].items():
        inventory.remove_item(char, iid, need)
    out_id = r["output"]
    inventory.add_item(char, out_id, r.get("output_qty", 1))
    skill = r.get("skill")
    if skill:
        xp, hours, tired = progression.practice_cost(char, gamedata, skill)
        events = progression.use_skill(char, gamedata, skill, xp)
    else:
        xp, hours, tired, events = 0.0, 0, False, []
    return {"ok": True, "message": f"你加工出了 {gamedata.item_name(out_id)}。",
            "output": out_id, "hours": hours, "tired": tired, "skill_events": events}
