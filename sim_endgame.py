"""終局強度:各 build「完全體 + 所有自鍛增益(無戴德拉誓福·無神器)」對 solo boss(尤其三王)勝率。

對標 sim_builds.py,但**放開其刻意排除的自附魔/藥水**(使用者指定:允許所有增益手段,但**不加 Daedric boons**、
亦不借神器=純玩家可自製)。疊加的增益(每個 build 公平同套):
  - 武器:吸血(vampiric)附魔,magnitude 24 = 頂階自鍛(grand soul + myst100)→ 近戰/遠程續戰;法師用法術不換。
  - 護甲:抗火(resist fire)附魔,每件 mag 12(grand soul+myst100)→ 三王皆火系,直接減傷;法師保 archmage 套裝(魔抗+法威)不動。
  - 藥水:治療藥水(heal 50),低於 40% 血時飲用(佔該回合行動、仍挨打=保守模型)。
  - 其餘(淬鍊+6、里程碑)沿用 sim_builds。
跑:PYTHONPATH=. python3 sim_endgame.py
"""
import sim_builds as S
from tesrpg import synth
from tesrpg.systems import inventory, stats
from tesrpg.rng import RNG

gd = S.gd
VAMP_MAG = 24          # 頂階自鍛吸血(enchanting.enchant_magnitude(5,100)=24)
RESIST_SOUL = 5        # grand soul → 抗火每件 mag 12

# 近戰/遠程武器流派 → 吸血續戰;法師走法術不換武器
_VAMP_BUILDS = {"assassin", "archer", "warrior_1H", "warrior_2H", "shield_reflect", "battlemage"}
# 保留套裝 bonus 不重附魔的 build(法師 archmage = 魔抗+法威來源)
_KEEP_ARMOR = {"mage_fire", "mage_frost", "mage_shock"}   # 法系保法袍套裝(魔抗/法威)不重附魔抗火


def buff(c, name):
    # 1) 武器 → 吸血(保留淬鍊+6)
    if name in _VAMP_BUILDS and c.weapon:
        base = c.weapon
        vid = synth.enchant_weapon_status_id(base, "vampiric", VAMP_MAG, 0)
        inventory.add_item(c, vid, 1)
        if name in ("assassin", "archer") and getattr(c, "offhand", None):  # 雙持副手亦吸血(刺客)
            inventory.add_item(c, vid, 1); inventory.equip_offhand(c, gd, vid)
        c.weapon = vid
        c.weapon_temper = {vid: c.weapon_temper.get(base, 6) if hasattr(c, "weapon_temper") else 6}
    # 2) 護甲 → 抗火附魔(法師除外:保 archmage 套裝)
    if name not in _KEEP_ARMOR:
        for slot, iid in list(c.equipped.items()):
            d = gd.item(iid)
            if not d.get("weight_class"):
                continue
            # 還原到 base(shield_reflect 原帶 thorns;三王純火 → thorns 物理反傷無效,抗火嚴格更優)
            base = iid.split("|")[1] if iid.startswith(("encha", "enchj")) else iid
            try:
                rid = synth.enchant_armor_id(base, "resist", "fire", RESIST_SOUL)
                inventory.add_item(c, rid, 1); inventory.equip_armor(c, gd, rid)
            except Exception:
                pass
    # 3) 治療藥水
    inventory.add_item(c, "healing_potion", 99)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def with_potions(act):
    def wrapped(c, boss, rng, st):
        if c.health < c.max_health * 0.40 and inventory.count_item(c, "healing_potion") > 0:
            inventory.use_item(c, gd, "healing_potion")     # 飲藥=該回合行動,仍挨打(保守)
            return
        act(c, boss, rng, st)
    return wrapped


# 法系(mage/battlemage)走法術自療(close_wounds 遠強於 heal 藥水)→ 不套藥水 wrapper(否則浪費施法回合)
_POTION_BUILDS = {"assassin", "archer", "warrior_1H", "warrior_2H", "shield_reflect"}

# 註冊「完全體+增益」版本
EBUILDS = {}
for _n, _mk in list(S.BUILDS.items()):
    EBUILDS[_n] = (lambda mk=_mk, n=_n: buff(mk(), n))
    S.BUILDS[_n + "_e"] = EBUILDS[_n]
    S._POLICY[_n + "_e"] = with_potions(S._POLICY[_n]) if _n in _POTION_BUILDS else S._POLICY[_n]


def winrate(name, boss, n=300):
    return sum(S.fight(name, boss, s) == "win" for s in range(n)) / n


if __name__ == "__main__":
    names = list(S.BUILDS)
    base_names = [n for n in names if not n.endswith("_e")]

    # 增益生效自證
    print("== 增益自證(完全體+增益版的衍生數值)==")
    import tesrpg.formulas as F
    from tesrpg.systems import magic as _m
    for n in base_names:
        c = EBUILDS[n]()
        ench = gd.item(c.weapon).get("enchant") if c.weapon else None
        vf = F.vampiric_fraction(ench) if ench and ench.get("status") == "vampiric" else 0.0
        res = _m.entity_resist(c, gd)
        print(f"  {n:14} HP{c.max_health:4} 吸血{vf:.0%} 抗火{res.get('fire',0)} 魔抗{res.get('magic',0)} potions={inventory.count_item(c,'healing_potion')} weapon={c.weapon}")

    kings = ["ancient_dragon", "mehrunes_dagon_diminished", "mehrunes_dagon"]
    print("\n== 三王勝率:無增益(sim_builds) → 完全體+所有自鍛增益(無誓福/神器)·n=300 ==")
    hdr = "  {:14}".format("BOSS") + "".join(f"{n:>13}" for n in base_names)
    print(hdr)
    for boss in kings:
        hp = gd.bestiary[boss].get("max_health")
        cells = []
        for n in base_names:
            b = winrate(n, boss); e = winrate(n + "_e", boss)
            cells.append(f"{b:>5.0%}→{e:<5.0%}")
        print(f"  {boss[:14]:14}" + "".join(f"{c:>13}" for c in cells))

    # 牆的性質:輸的是「戰死」(survival 不足→可再 buff)還是「逾時」(DPS 不足→buff 無解)
    from collections import Counter
    print("\n== 達貢滿血(720)輸法拆解(增益版·n=300)==")
    for n in ("mage_shock_e", "assassin_e", "archer_e"):
        out = Counter(S.fight(n, "mehrunes_dagon", s) for s in range(300))
        print(f"  {n:14} " + " ".join(f"{k}={round(v/300*100)}%" for k, v in out.items()))
    print("== 古龍(400)各系法師輸法拆解(火被牆 vs 電可贏)==")
    for n in ("mage_fire_e", "mage_shock_e"):
        out = Counter(S.fight(n, "ancient_dragon", s) for s in range(300))
        print(f"  {n:14} " + " ".join(f"{k}={round(v/300*100)}%" for k, v in out.items()))
