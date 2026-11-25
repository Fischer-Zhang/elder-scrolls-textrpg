"""R213 變化系護盾三階(橡木膚 / 石膚 / 鐵膚):低中高階「處處勝過」守衛。

設計準則(使用者):高階不論情境都該勝過中低階。護甲減傷是遞減曲線(護盾值加倍、減傷增加不到一倍),
而耗魔幾乎與護盾值成正比 → R213 前每魔力效率順序**顛倒**(橡木膚 > 石膚 > 鐵膚,30/30 格違反)。
R213 以 S1' 調整:橡木膚 30 / 4 回合 / 19 魔、鐵膚 75 / 6 回合 / 35 魔,**石膚 55 / 5 / 30 不動**(所有 sim 的基準)。
持續回合是對抗遞減曲線的槓桿(價值與回合成正比、不被曲線壓縮);威力極高時(≥2.6)護盾值差距被曲線壓平,
只剩「持續回合比 ≥ 耗魔比」才撐得住階層 → 鐵膚耗魔 ≤ 36(30×6/5)、橡木膚須夠貴。

守衛:
  1. 資料釘死(石膚 / 庇護術 = sim 基準不可動;橡木膚 / 鐵膚 = S1')
  2. 階層守衛:底甲 3–400 × 威力 0.55–3.5 的網格,「每次施放擋下量」與「每魔力效率」皆嚴格遞增(減傷走真實
     `formulas.damage_after_armor` → 護甲公式日後若改,守衛跟著算)+ 自檢:R213 前的舊數值確實違反(守衛非空轉)
  3. 階層單調:護盾值 / 耗魔 / 持續回合隨階遞增
  4. 變化系文字不得宣稱未實作的功能(開鎖):技能描述、練習標籤、變化系里程碑描述
"""
import json
import os

from tesrpg import formulas
from tesrpg.gamedata import get_gamedata

_BASES = (3, 7, 27, 47, 94, 148, 178, 300, 400)          # 布袍法師 → 重甲戰士(≥3:穿了任何衣物)
_POWERS = [round(0.55 + 0.05 * i, 2) for i in range(60)]  # 0.55(低體力起手期)→ 3.5(智力過百 + 套裝 + 里程碑疊滿)

OLD = ((30, 5, 16), (55, 5, 30), (75, 5, 42))              # R213 前 (magnitude, turns, cost):橡 / 石 / 鐵


def _reduction(armor: int) -> float:
    return 1.0 - formulas.damage_after_armor(100.0, armor) / 100.0


def _value(mag: float, turns: int, base: int, power: float) -> float:
    """一次施放擋下的『減傷回合數』:Σ(加盾後減傷 − 原減傷)× 持續回合。"""
    s = round(mag * power)
    return (_reduction(base + s) - _reduction(base)) * turns


def _violations(oak, stone, iron) -> list:
    bad = []
    for b in _BASES:
        for p in _POWERS:
            v = [_value(m, t, b, p) for (m, t, c) in (oak, stone, iron)]
            e = [x / c for x, (m, t, c) in zip(v, (oak, stone, iron))]
            if not (v[0] < v[1] < v[2]):
                bad.append(("每次施放", b, p))
            if not (e[0] < e[1] < e[2]):
                bad.append(("每魔力效率", b, p))
    return bad


def _tiers(gd):
    out = []
    for sid in ("oakflesh", "stoneflesh", "ironflesh"):
        sp = gd.spells[sid]
        out.append((sp["effect"]["magnitude"], sp["effect"]["turns"], sp["cost"]))
    return tuple(out)


def test_shield_tier_data_pinned():
    gd = get_gamedata()
    sp = gd.spells
    assert _tiers(gd) == ((30, 4, 19), (55, 5, 30), (75, 6, 35))
    # 🔴 石膚 / 庇護術是 sim 基準與敵方 / 同伴施放的基準,不可動(動了要先跑 sim)
    assert (sp["stoneflesh"]["effect"], sp["stoneflesh"]["cost"]) == ({"kind": "shield", "magnitude": 55, "turns": 5}, 30)
    assert (sp["ward_ally"]["effect"], sp["ward_ally"]["cost"], sp["ward_ally"]["target"]) == \
        ({"kind": "shield", "magnitude": 40, "turns": 5}, 22, "ally")


def test_higher_tier_wins_per_cast_and_per_mana_everywhere():
    gd = get_gamedata()
    bad = _violations(*_tiers(gd))
    assert not bad, f"階層被破壞(前 5 筆):{bad[:5]}(共 {len(bad)} 格)"


def test_guard_is_not_vacuous_old_values_violated():
    """自檢:R213 前的舊數值在此網格上必違反 → 上面的守衛不是空轉。
    舊數值:『每魔力效率』在每一格都顛倒(橡 > 石 > 鐵);極端威力 + 高底甲時石膚與鐵膚的減傷同撞 85% 上限,
    『每次施放』也打平(新鐵膚 6 回合 > 石膚 5 回合,所以撞頂時仍嚴格勝出)。"""
    bad = _violations(*OLD)
    eff = [x for x in bad if x[0] == "每魔力效率"]
    assert len(eff) == len(_BASES) * len(_POWERS), (len(eff), len(bad))      # 效率:全部格子都違反


def test_tier_parameters_ascend_monotonically():
    gd = get_gamedata()
    (m0, t0, c0), (m1, t1, c1), (m2, t2, c2) = _tiers(gd)
    assert m0 < m1 < m2 and t0 < t1 < t2 and c0 < c1 < c2


def test_alteration_text_does_not_claim_unimplemented_unlock():
    """變化系沒有任何開鎖法術(開鎖屬安全技能)→ 技能描述 / 練習標籤 / 變化系里程碑描述不得宣稱開鎖。"""
    gd = get_gamedata()
    alt = gd.skills["alteration"]
    assert "開鎖" not in alt["desc"] and "開鎖" not in alt["practice"]["label"]
    assert not any(sp["school"] == "alteration" and "unlock" in sp["effect"].get("kind", "") for sp in gd.spells.values())
    path = os.path.join(os.path.dirname(__file__), "..", "tesrpg", "data", "mastery.json")
    data = json.load(open(path, encoding="utf-8"))
    seen = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("school") == "alteration" and "desc" in o:
                seen.append(o["desc"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    assert seen, "應找到變化系里程碑選項"
    assert not [d for d in seen if "開鎖" in d], "變化系里程碑描述不得宣稱開鎖"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_shield_tiers_r213 OK")
