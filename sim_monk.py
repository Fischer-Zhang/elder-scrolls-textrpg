"""R193 徒手 100 守衛(非測試;手動跑:PYTHONPATH=. python3 sim_monk.py [n群戰] [n牆])

為什麼另寫一份:sim_assassin 只量單擊偷襲、sim_builds 是 1v1 王牆;徒手 100 的兩個選項(崩勁釋放/鐵布衫)
都在「持續戰」而非單擊上起作用 → 量「群戰勝率 + 平均回合 + 平均剩餘生命」,並守終王牆(達貢/真身)不被破。

構築:SB.make_monk(h100)(完整徒手樹 25/50/75:失衡·擒拿手·鐵拳;輕甲 + 治療藥水疊,同 sim_builds)。
變體(VARIANTS):none=100 階皆不選(基準線);fist_old=舊 +10% 傷害;relK=崩勁釋放·政策「目標失衡 ≥K 層就釋放」;
  rel_old=崩勁 + 舊 +10%(兼帶);shirt_old=鐵布衫舊 +12 護甲(子提交 2 後改量體力化傷)。
政策只用看得到的資訊(目標失衡層數);K 掃 4/5/6/8 取最佳者當 canonical(sim_builds.RELEASE_AT)。
種子:每格 seed=0..n-1;怪 RNG = seed*9+1+i,戰鬥 RNG = seed。
守衛(⚠;非自動閘門,改徒手/失衡/崩勁參數後人工看):
  1. 群戰輸給皆不選(增益 < -3pp) 2. 強度過頭(> +25pp) 3. 破牆線(達貢/真身 增益 > +5pp)
對照變體 fist_old/rel_old 不是玩家可選組合 → 只印數字、不入旗標(REFERENCE_ONLY);shirt_old 是現存 iron_shirt → 照守衛。
單格 95% 半寬:n=1000 約 ±3pp;差值再乘 1.4,小於此的差距不當訊號(同 sim_reckless)。
"""
import statistics as S
import sys
from multiprocessing import Pool

import sim_builds as SB
from tesrpg import formulas
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, magic, stats

gd = SB.gd
OLD_FIST_POWER = 0.10      # 舊 transcend_fist 的 +10% 徒手傷害(對照用:臨時補回 gd 的選項資料)

# 變體名 → (hand_to_hand_100 選項, 崩勁釋放門檻層數|None, 是否補回舊 +10% 傷害)
VARIANTS = {
    "none":      (None, None, False),
    "fist_old":  ("transcend_fist", None, True),
    # 失衡層數只會是 0/5/8(徒手 100·擒拿手:每擊 +5,滿層 8):門檻 4/5 等價、6/8 等價 → 只掃 5(避開滿層 25% 擊倒清層)與 8
    "rel5":      ("transcend_fist", 5, False),
    "rel8":      ("transcend_fist", 8, False),
    "rel_old":   ("transcend_fist", 5, True),
    "shirt_old": ("iron_shirt", None, False),
}


def _find_opt(opt_id):
    nodes = gd.mastery.values() if isinstance(gd.mastery, dict) else gd.mastery
    for n in nodes:
        for o in n.get("options", []):
            if o.get("opt_id") == opt_id:
                return o
    raise KeyError(opt_id)


def _set_old_power(on):
    """臨時補回/移除舊 +10% 傷害(只在跑那個變體的整場戰鬥期間;子行程各自一份 gd,互不干擾)。"""
    o = _find_opt("transcend_fist")
    if on:
        o["power"] = OLD_FIST_POWER
    else:
        o.pop("power", None)


def act(c, tgt, rng, st):
    """徒手政策:低血喝藥 → 目標失衡達 release_at 就崩勁釋放 → 否則普攻(monk 不用格擋姿態)。"""
    if SB._drink_if_low(c):
        return
    ra = st.get("release_at")
    if ra is not None and magic.offbalance_stacks(tgt) >= ra \
            and combat.release_strike(c, tgt, gd, rng) is not None:
        return
    combat.player_attack_cost(c, gd)
    combat.resolve_attack(c, tgt, gd, rng)


def fight(variant, enemy_ids, seed, max_rounds=80):
    """多主敵:群戰全滅才勝;solo 王殺王即勝(R134 召喚爪牙隨王潰散)。回 (結果, 回合數, 結束時生命比例)。"""
    h100, release_at, old_power = VARIANTS[variant]
    _set_old_power(old_power)
    c = SB.make_monk(h100)
    inventory.add_item(c, "healing_potion", SB._COMBAT_POTIONS)
    prim = [combat.spawn_creature(gd, t, RNG(seed * 9 + 1 + i)) for i, t in enumerate(enemy_ids)]
    foes = list(prim)
    rng = RNG(seed)
    st = {"opening": True, "vanish": 0, "release_at": release_at}
    rounds = 0
    for rounds in range(1, max_rounds + 1):
        if not any(combat.is_alive(p) for p in prim):
            return "win", rounds - 1, max(0.0, c.health / c.max_health)
        if c.health <= 0:
            return "dead", rounds - 1, 0.0
        alive = [e for e in foes if combat.is_alive(e)]
        st["enemies"] = alive
        tgt = min(alive, key=lambda e: e.health)
        if not magic.is_incapacitated(c):
            act(c, tgt, rng, st)
        if not any(combat.is_alive(p) for p in prim):
            return "win", rounds, max(0.0, c.health / c.max_health)
        for e in prim:
            if combat.is_alive(e) and c.health > 0 and not magic.is_incapacitated(e):
                if combat.try_boss_summon(e, foes, gd, rng) is None:
                    _atk = combat.choose_attack(e, rng, c)
                    _ev = combat.resolve_attack(e, c, gd, rng, attack=_atk)
                    combat.misdirect_redirect(c, e, foes, gd, rng, _ev, _atk)
        for a in foes[len(prim):]:
            if combat.is_alive(a) and c.health > 0 and not magic.is_incapacitated(a):
                _atk = combat.choose_enemy_attack(a, rng, c)
                _ev = combat.resolve_attack(a, c, gd, rng, attack=_atk)
                combat.misdirect_redirect(c, a, foes, gd, rng, _ev, _atk)
        SB._regen(c)
        magic.tick_effects(c, gd)
        for e in foes:
            if combat.is_alive(e):
                magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    won = not any(combat.is_alive(p) for p in prim)
    return ("win" if won else "timeout"), rounds, max(0.0, c.health / c.max_health)


def cell(task):
    label, variant, ids, n = task
    res = [fight(variant, ids, s) for s in range(n)]
    wins = [r for r in res if r[0] == "win"]
    return (label, variant, sum(1 for r in res if r[0] == "win") / n,
            S.mean(r[1] for r in wins) if wins else float("nan"),
            S.mean(r[2] for r in res))


# ---- 守衛 ---------------------------------------------------------------------------------------
DR = lambda k: ["dremora"] * k  # noqa: E731
GROUPS = [("魔人×3", DR(3)), ("魔人×4", DR(4)), ("魔人×5", DR(5)), ("魔人×6", DR(6)),
          ("2山賊+2狼", ["bandit", "bandit", "wolf", "wolf"]), ("4山賊", ["bandit"] * 4),
          ("風暴旋風(solo)", ["avuuma_whirlwind"])]
WALLS = [("達貢", ["mehrunes_dagon"]), ("真身", ["mehrunes_dagon_true"])]
FLAG_LOSE, FLAG_TOO_STRONG, FLAG_WALL = 3.0, 25.0, 5.0
# 只供對照、不是玩家可選的組合(舊數值/兼帶)→ 不入守衛旗標(審查:避免 check.sh --sim 長期被對照變體的抽樣雜訊誤報 ⚠)
REFERENCE_ONLY = {"fist_old", "rel_old"}


def guard(n_group=300, n_wall=300, variants=None):
    variants = variants or list(VARIANTS)
    tasks = [(g, v, ids, n_group) for g, ids in GROUPS for v in variants] + \
            [(g, v, ids, n_wall) for g, ids in WALLS for v in variants]
    with Pool(4) as p:
        out = {(t[0], t[1]): t for t in p.map(cell, tasks)}
    flags = []
    print(f"{'場景':14}" + "".join(f"{v:>15}" for v in variants) + "   ← 勝率% / 平均回合 / 平均剩餘生命%")
    for label in [g for g, _ in GROUPS] + [g for g, _ in WALLS]:
        row = f"{label:14}"
        for v in variants:
            _l, _v, w, rd, hp = out[(label, v)]
            row += f"{w*100:4.0f}/{rd:5.1f}/{hp*100:3.0f}".rjust(15)
        print(row)
    print()
    for v in variants:
        if v == "none":
            continue
        gains_g = [(out[(g, v)][2] - out[(g, "none")][2]) * 100 for g, _ in GROUPS]
        gains_hp = [(out[(g, v)][4] - out[(g, "none")][4]) * 100 for g, _ in GROUPS]
        gains_w = [(out[(g, v)][2] - out[(g, "none")][2]) * 100 for g, _ in WALLS]
        ref = " (僅對照·不入旗標)" if v in REFERENCE_ONLY else ""
        print(f"{v:10} 群戰勝率增益中位 {S.median(gains_g):+5.1f}pp  剩餘生命增益中位 {S.median(gains_hp):+5.1f}pp  終王牆增益 "
              + " ".join(f"{g}{x:+.1f}" for (g, _), x in zip(WALLS, gains_w)) + ref)
        if v in REFERENCE_ONLY:
            continue
        for (g, _), x in zip(GROUPS, gains_g):
            if x < -FLAG_LOSE:
                flags.append(f"⚠輸給皆不選 {v}@{g} {x:+.1f}pp")
            if x > FLAG_TOO_STRONG:
                flags.append(f"⚠強度過頭 {v}@{g} {x:+.1f}pp")
        for (g, _), x in zip(WALLS, gains_w):
            if x > FLAG_WALL:
                flags.append(f"⚠破牆線 {v}@{g} {x:+.1f}pp")
    if flags:                                   # 只有真的有警示才印「⚠ 守衛警示」(check.sh 以此行 grep)
        print("\n⚠ 守衛警示:\n  " + "\n  ".join(flags))
    else:
        print("\n✓ 徒手守衛全過(無輸給皆不選/強度過頭/破牆線)")
    return out


if __name__ == "__main__":
    ng = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    nw = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    guard(ng, nw)
