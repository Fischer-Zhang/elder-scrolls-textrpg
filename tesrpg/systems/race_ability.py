"""種族被動天賦(R61)—— 即時讀 `data/races.json` 的 `passive` 區,零存檔欄、零快取、零遷移。

模式比照星座 `resist`(magic.entity_resist 即時讀)、巨魔像座吸收(combat.py 即時 `birthsign==` 檢查):
**不寫 base、不入存檔、callsite 直接讀**。每個 helper 對「非 Character / 該族無此天賦」回中性值
(0 / 1.0)→ 與既有路徑 byte-identical(sim 刺客為 Khajiit:夜視/利爪在 callsite gated、
回魔/吸魔讀回中性值)。

被動族(其餘戰系種族走 powers.RACIAL_POWERS 主動威能):
  - 虎人 Khajiit:夜視 `night_eye`(夜間潛近加成)+ 利爪 `claw_bonus`(徒手傷害)
  - 亞龍 Argonian:癒膚 `histskin`(休息 HP 回復加成)
  - 高精靈 Altmer:高貴血脈 `magicka_regen`(回魔速率乘數)
  - 布萊頓 Breton:龍皮 `spell_absorb`(來襲元素/魔法被吸收為法力的機率)

🔴 紅線:利爪 `claw_bonus` **只**由 `combat._weapon_profile` 的 hand_to_hand(徒手)側呼叫,
絕不進匕首/blade 路徑、絕不餵偷襲倍率(claw 是徒手平砍傷害,不經 sneak_mult)。
"""
from __future__ import annotations

from tesrpg.gamedata import GameData


def _passive(char, gamedata: GameData) -> dict:
    """讀 char 種族的 `passive` 區;非 Character / 無 race / 無 passive → {}。"""
    race = getattr(char, "race", None)
    if race is None:
        return {}
    return (getattr(gamedata, "races", {}) or {}).get(race, {}).get("passive", {})


def night_eye_bonus(char, gamedata: GameData) -> float:
    """虎人夜視:夜間潛近額外成功率(**呼叫端負責只在夜間套用**,比照吸血鬼 night_vision)。非虎人 → 0。"""
    return _passive(char, gamedata).get("night_eye", 0.0)


def claw_bonus(char, gamedata: GameData) -> int:
    """虎人利爪:徒手(hand_to_hand)平砍傷害加成。🔴 僅由 `_weapon_profile` 的 hand_to_hand 側呼叫。非虎人 → 0。"""
    return _passive(char, gamedata).get("claw_bonus", 0)


def histskin_factor(char, gamedata: GameData) -> float:
    """亞龍癒膚:休息 HP 回復倍率加成(回復量 ×(1+factor))。非亞龍 → 0。"""
    return _passive(char, gamedata).get("histskin", 0.0)


def magicka_regen_factor(char, gamedata: GameData) -> float:
    """高精靈高貴血脈:回魔速率乘數(非高精靈 → 1.0 中性 → byte-identical)。"""
    return _passive(char, gamedata).get("magicka_regen", 1.0)


def dragonskin_chance(char, gamedata: GameData) -> float:
    """布萊頓龍皮:來襲元素/魔法被吸收為法力的機率(比照巨魔像座吸收)。非布萊頓 → 0。"""
    return _passive(char, gamedata).get("spell_absorb", 0.0)
