"""名聲/惡名 → 活的社交+經濟聲望軸(R101)。

fame(英雄 renown)/infamy(社交畏懼)純衍生地驅動:NPC 態度位移、商人買價、聲望稱號。
**零存檔欄**(全讀 char.fame/infamy)。

🔴 不重複 crime 的惡名→亡命系統(R84:outlaw_standing/notoriety_title/bounty/衛兵/亡命) ——
此處惡名只補「社交面」(平民冷待 + 買價加價),與通緝/衛兵正交;惡名稱號仍用 crime.notoriety_title,
本模組只新增**名聲**稱號。
🔴 tier-0(fame<首階 ∧ infamy<首階)嚴格 no-op:attitude_shift 零位移、price_factor=1.0
→ 既有 NPC 態度/物價/測試/sim 逐位元組同(關鍵相容性)。
"""

from __future__ import annotations

from tesrpg.models import Character

# fame → 名聲(renown)階 0..4 + 稱號(仿 crime._NOTORIETY_TITLES 階梯)
FAME_THRESHOLDS = (50, 150, 350, 700)
RENOWN_TITLES = ("", "嶄露頭角", "聲名遠播", "名動天下", "傳奇英雄")
# infamy → 社交畏懼階 0..3(刻意異於 crime.OUTLAW_THRESHOLDS;此為社交面,非亡命身份)
INFAMY_SOCIAL_THRESHOLDS = (20, 60, 150)

# 態度位移只在「civil」階梯內 —— hostile/comrade/vampire_seen 不受聲望左右
_CIVIL_LADDER = ("cold", "neutral", "friendly")

# 商人買價:每名聲階折扣 / 每惡名社交階加價(各夾 cap;by-design 旋鈕)
PRICE_FAME_DISCOUNT_PER_TIER = 0.03
PRICE_INFAMY_MARKUP_PER_TIER = 0.04
PRICE_DISCOUNT_CAP = 0.12
PRICE_MARKUP_CAP = 0.12


def renown_tier(char: Character) -> int:
    v = getattr(char, "fame", 0)
    return sum(1 for thr in FAME_THRESHOLDS if v >= thr)


def renown_title(char: Character) -> str:
    """名聲稱號(由 renown tier;tier0 → 空字串)。與 crime.notoriety_title 並列。"""
    return RENOWN_TITLES[renown_tier(char)]


def notoriety_social_tier(char: Character) -> int:
    v = getattr(char, "infamy", 0)
    return sum(1 for thr in INFAMY_SOCIAL_THRESHOLDS if v >= thr)


def attitude_shift(char: Character, base: str) -> str:
    """聲望位移 base 態度:civil 階梯內 `+renown_tier − notoriety_social_tier`,夾 [cold, friendly]。
    base ∉ civil(hostile/comrade/vampire_seen)→ 原樣返回(聲望不憑空造敵意/同袍);
    淨 delta=0(含 tier 全 0)→ 原樣返回(no-op·守 byte-identical)。"""
    if base not in _CIVIL_LADDER:
        return base
    delta = renown_tier(char) - notoriety_social_tier(char)
    if delta == 0:
        return base
    idx = _CIVIL_LADDER.index(base) + delta
    idx = max(0, min(len(_CIVIL_LADDER) - 1, idx))
    return _CIVIL_LADDER[idx]


def price_factor(char: Character) -> float:
    """商人**買價**乘數:名聲折扣 − 惡名加價。tier-0 → 1.0(no-op);只動 buy_price(賣價不碰,免 faucet)。"""
    disc = min(PRICE_DISCOUNT_CAP, renown_tier(char) * PRICE_FAME_DISCOUNT_PER_TIER)
    markup = min(PRICE_MARKUP_CAP, notoriety_social_tier(char) * PRICE_INFAMY_MARKUP_PER_TIER)
    return 1.0 - disc + markup
