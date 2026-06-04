"""動態(合成)物品:煉金產出的藥水、附魔後的裝備。

這些物品不寫死在 data/,而是用「可解析的 id」即時重建定義,
所以存檔只存 id 即可,讀檔時照樣還原 —— 不需要額外的註冊表。

id 格式(以 '|' 分段):
  brew|<effect_kind>|<magnitude>                         → 自製藥水
  psn|<status_kind>|<a>|<b>                              → 塗抹用毒藥(dot:每回合a傷×b回合;paralyze:a回合)
  enchw|<base_weapon_id>|<element>|<magnitude>           → 附魔武器
  encha|<base_armor_id>|<stat>|<magnitude>               → 附魔護甲
"""

from __future__ import annotations

SEP = "|"

_EFFECT_NAME = {"heal": "治療", "restore_magicka": "魔力", "restore_fatigue": "體力"}
_ELEMENT_NAME = {"fire": "烈焰", "frost": "冰霜", "shock": "雷電"}
_STAT_NAME = {"health": "生命", "magicka": "魔力", "fatigue": "體力"}


def is_synth(item_id: str) -> bool:
    return SEP in item_id


def brew_id(effect_kind: str, magnitude: int) -> str:
    return f"brew{SEP}{effect_kind}{SEP}{magnitude}"


def poison_id(status_kind: str, a: int, b: int = 0) -> str:
    return f"psn{SEP}{status_kind}{SEP}{a}{SEP}{b}"


def enchant_weapon_id(base_weapon: str, element: str, magnitude: int) -> str:
    return f"enchw{SEP}{base_weapon}{SEP}{element}{SEP}{magnitude}"


def enchant_armor_id(base_armor: str, stat: str, magnitude: int) -> str:
    return f"encha{SEP}{base_armor}{SEP}{stat}{SEP}{magnitude}"


def synthesize(item_id: str, gamedata) -> dict:
    """由合成 id 重建物品定義。"""
    parts = item_id.split(SEP)
    tag = parts[0]

    if tag == "brew":
        _, kind, mag = parts
        mag = int(mag)
        name = f"自製{_EFFECT_NAME.get(kind, kind)}藥水（{mag}）"
        return {"name": name, "kind": "potion", "effect": {"type": kind, "magnitude": mag},
                "value": max(5, mag), "weight": 0.5}

    if tag == "psn":
        _, kind, a, b = parts
        a, b = int(a), int(b)
        if kind == "dot":
            status = {"status": "dot", "element": "poison", "magnitude": a, "turns": b}
            name = f"毒藥(每回合 {a} 傷 × {b} 回合)"
            value = max(10, a * b * 3)
        else:  # paralyze
            status = {"status": "paralyze", "turns": a}
            name = f"麻痺毒({a} 回合)"
            value = max(15, a * 40)
        return {"name": name, "kind": "poison", "poison": status, "value": value, "weight": 0.5}

    if tag == "enchw":
        _, base, element, mag = parts
        mag = int(mag)
        base_def = gamedata.weapons[base]
        return {**base_def, "kind": "weapon",
                "name": f"{base_def['name']}（{_ELEMENT_NAME.get(element, element)}附魔 +{mag})",
                "enchant": {"kind": "weapon_element", "element": element, "magnitude": mag},
                "value": base_def["value"] + mag * 25}

    if tag == "encha":
        _, base, stat, mag = parts
        mag = int(mag)
        base_def = gamedata.armor[base]
        return {**base_def, "kind": "armor",
                "name": f"{base_def['name']}（強化{_STAT_NAME.get(stat, stat)} +{mag})",
                "enchant": {"kind": "armor_fortify", "stat": stat, "magnitude": mag},
                "value": base_def["value"] + mag * 15}

    raise KeyError(f"未知的合成物品 id:{item_id}")
