"""具名地標與發現 —— 首次抵達某地 → 一次性「發現」(意境文字 + 小獎勵)。

刻意**不走隨機事件引擎**(那是機率抽選、無保證觸發):地標是保證、一次性、以
location_id 為 key 的發現。資料在 `data/landmarks.json`(鏡像 rulers.json 慣例);
一次性守門在 `Character.discovered_landmarks`(新欄,預設 [] → 舊存檔向後相容,
且舊存檔已訪過的節點仍能發現)。獎勵純加性:**不耗時、不戰鬥、絕不致死**。

加地標純改 landmarks.json(零碼)。獎勵刻意只給金幣/物品/聲望 —— **無永久數值/
技能加成**(守反 min-max;有測試鎖死禁用的 reward key)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import inventory


def is_discovered(char: Character, loc_id: str) -> bool:
    return loc_id in char.discovered_landmarks


def discover(state, gamedata: GameData, loc_id: str) -> dict | None:
    """若該地有「尚未發現」的地標 → 記入守門、發一次性獎勵,回傳
    {name, text, reward_lines} 供 UI 呈現;無地標或已發現 → None。"""
    lm = gamedata.landmark_at(loc_id)
    if lm is None:
        return None
    char = state.player
    if loc_id in char.discovered_landmarks:      # 一次性:重訪不重觸
        return None
    char.discovered_landmarks.append(loc_id)

    reward = lm.get("reward", {})
    lines: list[str] = []
    gold = reward.get("gold", 0)
    if gold:
        char.gold += gold
        lines.append(f"金幣 +{gold}")
    for it in reward.get("items", []):
        n = it.get("qty", 1)
        inventory.add_item(char, it["id"], n)
        lines.append(f"獲得 {gamedata.item_name(it['id'])} ×{n}")
    fame = reward.get("fame", 0)
    if fame:
        char.fame += fame
        lines.append(f"聲望 +{fame}")

    return {"name": lm["name"], "text": lm["discover"], "reward_lines": lines}
