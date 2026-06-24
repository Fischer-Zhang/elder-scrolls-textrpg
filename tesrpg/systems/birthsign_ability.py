"""出生星座被動天賦 —— 即時讀 `data/birthsigns.json` 的 `passive` 區,零存檔欄、零快取、零遷移。

模式比照種族被動 `race_ability.py`(R61)與星座 `resist`(magic.entity_resist 即時讀):
**不寫 base、不入存檔、callsite 直接讀**。每個 helper 對「非 Character / 該星座無此天賦」
回中性值(0)→ 與既有路徑 byte-identical(sim 刺客為陰影座:竊賊/駿馬被動讀回 0)。

被動星座(三大守護星裡偏「持續身份」的兩座;戰士/法師/淑女走 powers.POWERS 主動威能):
  - 竊賊座 thief:巧手 `stealth_aptitude`(潛行系 spec 技能 learn-by-doing 加速)
  - 駿馬座 steed:疾行 `swift_travel`(長途旅行耗時降低,比照運動/坐騎/同伴識途)
"""
from __future__ import annotations

from tesrpg.gamedata import GameData


def _passive(char, gamedata: GameData) -> dict:
    """讀 char 星座的 `passive` 區;非 Character / 無 birthsign / 無 passive → {}。"""
    sign = getattr(char, "birthsign", None)
    if sign is None:
        return {}
    return (getattr(gamedata, "birthsigns", {}) or {}).get(sign, {}).get("passive", {})


def stealth_aptitude(char, gamedata: GameData) -> float:
    """竊賊座巧手:潛行系(skill spec=='stealth')技能額外 XP 倍率加成
    (`progression.use_skill` 讀 → xp ×(1+此值))。非竊賊座 → 0。"""
    return _passive(char, gamedata).get("stealth_aptitude", 0.0)


def travel_factor_bonus(char, gamedata: GameData) -> float:
    """駿馬座疾行:旅行耗時係數的額外減量(`world.travel` 減項,比照運動/坐騎,夾 floor 0.5)。
    非駿馬座 → 0。"""
    return _passive(char, gamedata).get("swift_travel", 0.0)
