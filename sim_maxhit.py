"""各 build「非潛行狀態」單擊最高傷害(burst ceiling)探針。手動跑:PYTHONPATH=. python3 sim_maxhit.py

沿用 sim_builds 的「完全體」build(同樣排除戴德拉誓福 + 自附魔)。量的是「非偷襲(sneak_attack=False)
下,一個攻擊動作能打出的最高單擊傷害」——非潛行 → 無 SOLO_SNEAK 夾(該夾只在 sneaking 時觸發)。

方法:對「無防禦假人」(armor 0 / resist {})逐 seed 跑單一動作,取 dmg_done 最大值(roll 上界 → 爬到天花板)。
  - 體力只影響命中率不影響傷害量(attack_damage 不讀 fatigue);只要命中即取傷害,故每 build 滿體即可。
  - 近戰/弓:combat.resolve_attack(sneak_attack=False);弓另量 aimed=True(瞄準射蓄力強擊=弓手真正的單發爆發)。
  - 法系:magic.cast 各傷害法術取最高(本批 build 皆未選奧術連鎖 cascade → 不另計)。
  - 種族爆發:獸人 orc_berserk(+0.20 self_empower 3 回合)對 orsimer build 另量一欄(非潛行可用的真實增幅)。

附帶:也對「重甲假人」(armor 150)量一次 → 看物理 vs 元素在有甲目標上的實戰落差。
"""
import sim_builds as S
from tesrpg.systems import combat, magic
from tesrpg.models import Creature
from tesrpg.rng import RNG

gd = S.gd


def _dummy(armor=0, resist=None, hp=10**7):
    return Creature(template_id=None, name="假人", strength=0, agility=0, speed=0,
                    max_health=hp, health=hp, armor_rating=armor, attack={"damage": 0, "skill": 0},
                    loot_gold=[0, 0], loot_table=[], flavor="", danger=1, resist=dict(resist or {}))


def _apply_berserk(c):
    c.active_effects.append({"kind": "berserk_buff", "magnitude": 0.20, "turns": 3})


def max_weapon_hit(make, seeds, armor=0, aimed=False, berserk=False):
    best = 0
    for s in range(seeds):
        c = make()
        if berserk:
            _apply_berserk(c)
        d = _dummy(armor=armor)
        ev = combat.resolve_attack(c, d, gd, RNG(s), sneak_attack=False, aimed=aimed)
        best = max(best, ev["damage"])
    return best


def max_spell_hit(make, spells, seeds, armor=0, resist=None):
    """對每個傷害法術取單發最高傷害(無偷襲概念;法術走元素抗性,無甲假人 → 全額)。"""
    best, best_sid = 0, None
    for sid in spells:
        for s in range(seeds):
            c = make()
            d = _dummy(armor=armor, resist=resist)
            if not magic.can_cast(c, gd, sid):
                continue
            ev = magic.cast(c, gd, sid, RNG(s), target=d, enemies=[d], battle={"allies": []})
            if ev["damage"] > best:
                best, best_sid = ev["damage"], sid
    return best, best_sid


WEAPON_BUILDS = ["assassin", "archer", "warrior_1H", "warrior_2H", "shield_reflect", "battlemage"]
ORC_BUILDS = {"warrior_1H", "warrior_2H", "shield_reflect"}
SPELL_BUILDS = {"mage": S._MAGE_DMG, "battlemage": S._BM_DMG}


if __name__ == "__main__":
    N = 4000
    print(f"== 非潛行單擊最高傷害(完全體·無偷襲·max over {N} seeds)==")
    print("   排除戴德拉誓福 + 自附魔(同 sim_builds);體力不影響傷害量只影響命中。\n")

    # --- 各 build 衍生數值速覽 ---
    for name, mk in S.BUILDS.items():
        c = mk()
        wn = combat.effective_weapon_name(c, gd)
        print(f"  {name:14} str{c.attr('strength'):3} agi{c.attr('agility'):3} int{c.attr('intelligence'):3}  武器={wn}")
    print()

    rows = []
    for name in S.BUILDS:
        mk = S.BUILDS[name]
        no_def = arm = berserk = aimed = None
        sp_info = ""
        if name in WEAPON_BUILDS:
            no_def = max_weapon_hit(mk, N, armor=0)
            arm = max_weapon_hit(mk, N, armor=150)
            if name == "archer":
                aimed = max_weapon_hit(mk, N // 2, armor=0, aimed=True)
            if name in ORC_BUILDS:
                berserk = max_weapon_hit(mk, N, armor=0, berserk=True)
        if name in SPELL_BUILDS:
            spd, sid = max_spell_hit(mk, SPELL_BUILDS[name], N // 4, armor=0, resist=None)
            # 法系對無甲假人也吃 0 抗 → no_def 取「武器 vs 法術」較大者
            if name == "mage":
                no_def = spd
            else:
                no_def = max(no_def or 0, spd)
            sp_info = f"  [最佳法術={sid} 單發={spd}]"
        rows.append((name, no_def, arm, aimed, berserk, sp_info))

    print(f"  {'build':14}{'無甲假人':>9}{'重甲150':>9}{'瞄準射':>8}{'+獸人狂暴':>10}   備註")
    for name, no_def, arm, aimed, berserk, sp_info in rows:
        f = lambda v: (f"{v:>8}" if v is not None else f"{'—':>8}")
        print(f"  {name:14}{f(no_def):>9}{f(arm):>9}{f(aimed):>8}{f(berserk):>10}{sp_info}")
