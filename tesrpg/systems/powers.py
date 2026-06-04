"""出生星座的招牌能力(每日一次)。

把 data/birthsigns.json 裡原本只是死資料的 `powers` 接成實際可用的能力:
戰士/法師/竊賊等三大守護星沒有主動能力(只給屬性/魔力);其餘星座各有一招。
冷卻以「遊戲日」為單位(同一天只能用一次)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

# power_id -> 定義。contexts:combat=戰鬥中可用、utility=平時可用、passive=被動(不主動觸發)
POWERS = {
    "heal_self":        {"name": "領主再生", "contexts": ["combat", "utility"],
                         "effect": {"heal": 60}, "desc": "回復 60 點生命。"},
    "mara_blessing":    {"name": "瑪拉祝福", "contexts": ["combat", "utility"],
                         "effect": {"heal": 80, "cure": True}, "desc": "回復 80 點生命並解除身上的持續傷害。"},
    "paralyze_touch":   {"name": "戀人之觸", "contexts": ["combat"],
                         "effect": {"paralyze": 3}, "desc": "使敵人麻痺 3 回合,無法行動。"},
    "serpent_curse":    {"name": "蛇之詛咒", "contexts": ["combat"],
                         "effect": {"poison": {"magnitude": 8, "turns": 4}, "heal": 25},
                         "desc": "對敵人下毒(每回合 8 點,4 回合),並汲取 25 點生命。"},
    "invisibility":     {"name": "陰影遁形", "contexts": ["combat"],
                         "effect": {"escape": True}, "desc": "遁入陰影,必定脫離戰鬥。"},
    "tower_key":        {"name": "塔之鑰", "contexts": ["utility"],
                         "effect": {"unlock_charge": True}, "desc": "下一次撬鎖必定成功。"},
    "spell_absorption": {"name": "巨魔像吸收", "contexts": ["passive"],
                         "effect": {}, "desc": "(被動)有機率將來襲的元素魔法吸收為魔力。"},
    # 吸血鬼專屬(轉化後取代出生星座之力):每日一次的汲血擁抱
    "vampiric_drain":   {"name": "汲血擁抱", "contexts": ["combat"],
                         "effect": {"drain": 40}, "desc": "撕咬汲取敵人 40 點生命為己用。"},
}


def power_id(char: Character, gamedata: GameData) -> str | None:
    if getattr(char, "is_vampire", False):   # 吸血鬼:詛咒之力取代出生星座之力
        return "vampiric_drain"
    powers = gamedata.birthsigns[char.birthsign].get("powers", [])
    pid = powers[0] if powers else None
    return pid if pid in POWERS else None


def power_def(pid: str) -> dict:
    return POWERS[pid]


def _today(state) -> int:
    return state.time.absolute_hours() // 24


def available(char: Character, state, gamedata: GameData, context: str | None = None) -> bool:
    pid = power_id(char, gamedata)
    if not pid:
        return False
    if context is not None and context not in POWERS[pid]["contexts"]:
        return False
    return char.power_last_day.get(pid) != _today(state)


def usable_in(char: Character, state, gamedata: GameData, context: str) -> bool:
    return available(char, state, gamedata, context)


def use(char: Character, state, gamedata: GameData, target=None) -> dict:
    """施展星座能力。回傳 {"messages": [...], "escape": bool}。設置當日冷卻。"""
    pid = power_id(char, gamedata)
    pdef = POWERS[pid]
    eff = pdef["effect"]
    messages: list[str] = []
    escape = False

    if "heal" in eff:
        before = char.health
        char.health = min(char.max_health, char.health + eff["heal"])
        messages.append(f"{pdef['name']}回復了 {int(char.health - before)} 點生命。")
    if eff.get("cure"):
        removed = [e for e in char.active_effects if e["kind"] == "dot"]
        char.active_effects = [e for e in char.active_effects if e["kind"] != "dot"]
        if removed:
            messages.append("身上的持續傷害被淨化了。")
    if "paralyze" in eff and target is not None:
        target.active_effects.append({"kind": "paralyze", "turns": eff["paralyze"]})
        messages.append(f"{target.name}被{pdef['name']}定在原地({eff['paralyze']} 回合)!")
    if "poison" in eff and target is not None:
        p = eff["poison"]
        target.active_effects.append({"kind": "dot", "element": "poison",
                                      "magnitude": p["magnitude"], "turns": p["turns"]})
        messages.append(f"{target.name}中了蛇毒({p['turns']} 回合)。")
    if "drain" in eff and target is not None:
        amount = min(eff["drain"], int(target.health))
        target.health = max(0, target.health - eff["drain"])
        char.health = min(char.max_health, char.health + amount)
        messages.append(f"{pdef['name']}撕咬{target.name},汲取了 {amount} 點生命。")
    if eff.get("escape"):
        escape = True
        messages.append(f"{pdef['name']} —— 你隱入陰影,悄然脫身。")
    if eff.get("unlock_charge"):
        char.tower_key_charge = True
        messages.append(f"{pdef['name']}已蓄勢 —— 下一道鎖將應手而開。")

    char.power_last_day[pid] = _today(state)
    return {"messages": messages, "escape": escape}
