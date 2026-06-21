"""評估:智力→法術威力 由「int100=×1.0(R63 knee=100)」改為「int100=+20%」的影響。
手動跑:PYTHONPATH=. python3 eval_int_potency.py  (非正典探針;不改檔,monkeypatch 量影響)

候選曲線(都讓 int100→+20%):
  linear:    1.0 + int/500          (int100→1.20, int125→1.25, int200→1.40;最簡,仿 str_mult)
  softcap:   1.0 + _soft_cap(int,0,per,cap)  (int100→~1.20 但過 100 漸減,保 R63「過 100 仍漲但收斂」哲學)
量:① 法師/戰法單擊 ② 法師/戰法 vs 全 solo boss 勝率(current vs proposed)。
"""
import sim_builds as S
from tesrpg import formulas
from tesrpg.systems import magic
from tesrpg.rng import RNG

gd = S.gd
_ORIG = formulas.intelligence_spell_potency


def linear(i):
    return 1.0 + i / 500.0


def softcap(i):
    # per/cap 調到 int100≈+0.20、過 100 漸近 +0.30
    return 1.0 + formulas._soft_cap(max(0, i), 0, 0.0024, 0.30)


def two_seg_30(i):
    """新案:0→100 線性到 +30%(slope 0.003),>100 才套 softcap 漸減(slope 0.003 與線性段 C1 連續,
    額外漸近 +0.20 → 總漸近 +50%)。int100=+30%,int138≈+38%,int200≈+44%。"""
    if i <= 100:
        return 1.0 + 0.003 * max(0, i)
    return 1.30 + formulas._soft_cap(i - 100, 0, 0.003, 0.20)


def _spell_single(make, spells):
    """最佳傷害法術單發最高(roll 觸頂)。"""
    best = 0
    for sid in spells:
        for s in range(1000):
            c = make()
            d = S.combat.spawn_creature  # unused
            from tesrpg.models import Creature
            dummy = Creature(template_id=None, name="t", strength=0, agility=0, speed=0,
                             max_health=10**7, health=10**7, armor_rating=0,
                             attack={"damage": 0, "skill": 0}, loot_gold=[0, 0], loot_table=[],
                             flavor="", danger=1, resist={})
            if not magic.can_cast(c, gd, sid):
                continue
            ev = magic.cast(c, gd, sid, RNG(s), target=dummy, enemies=[dummy], battle={"allies": []})
            best = max(best, ev["damage"])
    return best


def winrate(build, boss, n):
    return sum(S.fight(build, boss, s) == "win" for s in range(n)) / n


if __name__ == "__main__":
    solo = sorted([b for b, t in gd.bestiary.items() if t.get("solo")],
                  key=lambda b: gd.bestiary[b].get("max_health", 0))
    casters = {"mage": S._MAGE_DMG, "battlemage": S._BM_DMG}
    N = 160

    variants = {"current(R63)": _ORIG, "+20%linear": linear, "+30%2seg(NEW)": two_seg_30}

    print("== 法師/戰法 最佳傷害法術『單發最高傷害』(無甲無抗假人, roll 觸頂)==")
    print(f"   eff int: mage={S.make_mage().attr('intelligence')} battlemage={S.make_battlemage().attr('intelligence')}")
    for vname, fn in variants.items():
        formulas.intelligence_spell_potency = fn
        row = {b: _spell_single(S.BUILDS[b], sp) for b, sp in casters.items()}
        print(f"   {vname:18} potency(100)={fn(100):.3f}  mage={row['mage']:3}  battlemage={row['battlemage']:3}")
    formulas.intelligence_spell_potency = _ORIG

    print(f"\n== 法師/戰法 vs solo boss 勝率(n={N};只跑這兩個 caster row)==")
    print(f"   {'BOSS(HP·元素)':30}" + "".join(f"{v:>20}" for v in variants))
    base = {}
    for vname, fn in variants.items():
        formulas.intelligence_spell_potency = fn
        base[vname] = {(c, b): winrate(c, b, N) for c in casters for b in solo}
    formulas.intelligence_spell_potency = _ORIG

    for b in solo:
        t = gd.bestiary[b]
        tag = f"{b}({t.get('max_health')}·{t.get('attack',{}).get('element') or 'phys'})"
        cells = []
        for vname in variants:
            cells.append(f"M{base[vname][('mage',b)]:>4.0%} B{base[vname][('battlemage',b)]:>4.0%}")
        print(f"   {tag:30}" + "".join(f"{c:>20}" for c in cells))

    # 彙總:平均勝率
    print("\n== 平均勝率(27 solo boss)==")
    for vname in variants:
        mage_avg = sum(base[vname][('mage', b)] for b in solo) / len(solo)
        bm_avg = sum(base[vname][('battlemage', b)] for b in solo) / len(solo)
        print(f"   {vname:18}  mage {mage_avg:>5.1%}   battlemage {bm_avg:>5.1%}")
