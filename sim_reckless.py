"""R191 搏命連斬(刀劍 100 savage)群戰 / 終王牆守衛(非測試;手動跑:PYTHONPATH=. python3 sim_reckless.py [n群戰] [n牆])。

為什麼需要它:sim_assassin 只量單擊偷襲(對主動戰技是真空),sim_builds 只有 solo 單敵(量不到群戰)。
搏命連斬的價值在精英群、風險在「群戰變太簡單」與「打穿終王牆」→ 這支守這兩件事。設計階段的量測條件在此可重現:
  - 構築 = sim_builds 的完整體 + 完整刀劍樹(blade_25/50/75:練到刀劍 100 必已選;看破要有踉蹌來源才有感)
    + 不利夾具(輕刺客 = sim_assassin P2 同款、中期劍盾戰士)+ 終王牆極端夾具(幻術 100 懾意三節點、吸血附魔武器)。
  - 政策 = 玩家只用看得到的資訊(血/體/敵血量條/敵數/敵是否失能)——判斷在 sim_builds._want_reckless(「熟練」用法)。
  - 種子:每格 seed=0..n-1;怪 RNG(seed*9+1+i)、戰鬥 RNG(seed);各變體同種子成對。
變體:none=沒選 blade_100、prec=看破、savage=搏命連斬(讀 mastery.json 的 reckless 子欄,第二記係數 0.6 / 耗體 30)。

⚠ 守衛(印出即標記;非自動閘門,改戰鬥常數/搏命參數後人工看):
  - 群戰「輸給皆不選」:savage 勝率 < none − 3.0pp(連斬的還擊代價大於收益 → 係數過低或政策失效)。
  - 群戰「強度過頭」:savage > none + 25pp(精英群變得太簡單,動搖 R34 群戰規模反制)。
  - 牆「破線」:savage > max(none, prec) + 5.0pp(R190 同款:終王牆不得被新機制打穿)。
  - 相當性:群戰增益中位數 ÷ 看破牆增益中位數 > 2.0(使用者設計目標「各擅勝場、增益量級相當」≈1.5×,留雜訊餘裕到 2.0)。
單格 95% 半寬:n=1000 約 ±3pp、n=2000 約 ±2pp(差值再 ×1.4)——小於此的差距別當訊號。"""
import statistics as S
import sys
from multiprocessing import Pool

import sim_builds as SB
from tesrpg import formulas
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, magic, mastery, stats

gd = SB.gd
BLADE_TREE = {"blade_25": "blade_basics", "blade_50": "riposte_blade", "blade_75": "blade_flow"}
CHOICE = {"none": None, "prec": "precision", "savage": "savage"}


# ---- 夾具 ---------------------------------------------------------------------------------------
def _fx_fear(c):
    """極端控場堆疊(R189 同款):幻術 100 + 懾意三節點(武器命中施恐懼;solo 王 65% 抵抗)。"""
    c.skills["illusion"] = 100
    c.mastery_choices.update({"illusion_50": "dread_touch", "illusion_75": "cowardice", "illusion_100": "soul_dread"})


def _fx_vamp(c):
    """吸血附魔武器(sim_endgame 同款:magnitude 24,保留淬鍊;刺客雙持副手亦吸血)——sim_builds 刻意排除自附魔,
    此處只用來驗「連斬使命中觸發翻倍」對終王牆的最壞影響。"""
    from tesrpg import synth
    base = c.weapon
    vid = synth.enchant_weapon_status_id(base, "vampiric", 24, 0)
    inventory.add_item(c, vid, 1)
    if getattr(c, "offhand", None):
        inventory.add_item(c, vid, 1)
        inventory.equip_offhand(c, gd, vid)
    c.weapon = vid
    c.weapon_temper = {vid: c.weapon_temper.get(base, 6)}


def _lite_assassin():
    """輕構築刺客(sim_assassin P2 覆核同款:潛行 70、刀劍 100、單持鋼匕首、無藥水)——「剛練滿刀劍」的中期角色。"""
    import sim_assassin as SA
    return SA.assassin(sneak=70, blade=100)


def _mid_warrior():
    """中期劍盾戰士:刀劍 100 但其餘中段(重甲/格擋 60、鋼甲鋼盾、精靈劍;藥水 3 瓶)。"""
    from tesrpg.creation import build_character
    c = build_character(gd, name="中", sex="male", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(blade=100, heavy_armor=60, block=60, athletics=40, acrobatics=30)
    c.attributes.update(strength=80, endurance=70, agility=50)
    c.weapon = "elven_sword"
    inventory.add_item(c, "elven_sword", 1)
    for slot in ("helmet", "cuirass", "gauntlets", "boots", "shield"):
        inventory.add_item(c, f"steel_{slot}", 1)
        inventory.equip_armor(c, gd, f"steel_{slot}")
    for nid, oid in {"heavy_armor_50": "armor_reflect", "block_50": "shield_bash"}.items():
        mastery.choose(c, gd, nid, oid)
    return c


# 名稱 → (政策用的基底構築, 額外修飾 fx 或 None, 自訂 maker 或 None, 藥水瓶數或 None=依 sim_builds)
FIXTURES = {
    "warrior_1H+fear": ("warrior_1H", _fx_fear, None, None),
    "assassin+fear": ("assassin", _fx_fear, None, None),
    "warrior_1H+vamp": ("warrior_1H", _fx_vamp, None, None),
    "assassin+vamp": ("assassin", _fx_vamp, None, None),
    "lite_assassin": ("assassin", None, _lite_assassin, 0),
    "mid_warrior": ("warrior_1H", None, _mid_warrior, 3),
}


def _base(build):
    return FIXTURES[build][0] if build in FIXTURES else build


def make(build, variant):
    base, fx, maker, _p = FIXTURES.get(build, (build, None, None, None))
    c = maker() if maker else SB.BUILDS[base]()
    c.mastery_choices.update(BLADE_TREE)
    ch = CHOICE[variant]
    if ch is None:
        c.mastery_choices.pop("blade_100", None)
    else:
        c.mastery_choices["blade_100"] = ch
    if fx:
        fx(c)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


# ---- 群戰政策(sim_builds 的 solo 政策 + 敵數感知的隱遁;攻擊一律經 strike → 搏命連斬『熟練』判斷)----------
def strike(c, tgt, rng, st, sneak=False, df=1.0):
    """一個攻擊動作:普通攻擊,或搏命連斬(判斷在 SB._want_reckless)。偷襲先機在手時恆走普通攻擊(連斬不吃偷襲倍率)。"""
    if not sneak and SB._reckless_swing(c, tgt, rng, st, damage_mult=df):
        return None
    combat.player_attack_cost(c, gd)
    return combat.resolve_attack(c, tgt, gd, rng, sneak_attack=sneak, damage_factor=df() if callable(df) else df)


def act_assassin(c, tgt, rng, st):
    if SB._drink_if_low(c):
        return
    if c.health < c.max_health * 0.45 and combat.can_vanish(c, gd) \
            and combat.try_vanish(c, len(st["enemies"]), st["vanish"], rng, gd):
        st["vanish"] += 1
        combat.player_vanish_cost(c)
        st["opening"] = True
        return
    op = st["opening"]
    st["opening"] = False
    strike(c, tgt, rng, st, sneak=op)


def act_warrior(c, tgt, rng, st):
    if SB._drink_if_low(c):
        return
    if st.get("use_stance") and not combat.has_guard_stance(c):
        c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
        return
    strike(c, tgt, rng, st, df=lambda: formulas.GUARD_STANCE_DAMAGE_TAX if combat.has_guard_stance(c) and c.fatigue > 0 else 1.0)


def act_paladin(c, tgt, rng, st):
    if not any(e.get("kind") == "consecration" and e.get("turns", 0) > 0 for e in c.active_effects) \
            and magic.can_cast(c, gd, "consecration"):
        magic.cast(c, gd, "consecration", rng)
        return
    if c.health < c.max_health * 0.35:
        for h in ("close_wounds", "heal"):
            if magic.can_cast(c, gd, h):
                magic.cast(c, gd, h, rng)
                return
    if magic._is_undead(tgt, gd):
        el = st["enemies"]
        if magic.can_cast(c, gd, "dawn_judgment"):
            magic.cast(c, gd, "dawn_judgment", rng, enemies=el, battle={"allies": []})
            return
        for s in ("close_wounds", "heal", "minor_heal"):
            if magic.can_cast(c, gd, s):
                magic.cast(c, gd, s, rng, target=tgt, enemies=el)
                return
    strike(c, tgt, rng, st)


def act_battlemage(c, tgt, rng, st):
    if c.health < c.max_health * 0.35 and magic.can_cast(c, gd, "close_wounds"):
        magic.cast(c, gd, "close_wounds", rng)
        return
    pf = (0.7 + c.skill("destruction") / 150.0) * formulas.intelligence_spell_potency(c.attr("intelligence"))
    best, best_dmg = None, 0.0
    for sid in SB._BM_DMG:
        if not magic.can_cast(c, gd, sid):
            continue
        eff = gd.spells[sid]["effect"]
        d = eff.get("magnitude", 0) * pf * (1 - (getattr(tgt, "resist", None) or {}).get(eff.get("element"), 0) / 100.0)
        if d > best_dmg:
            best, best_dmg = sid, d
    if best and best_dmg >= 45:
        magic.cast(c, gd, best, rng, target=tgt, enemies=[tgt], battle={"allies": []})
        return
    strike(c, tgt, rng, st)


POLICY = {"assassin": act_assassin, "warrior_1H": act_warrior, "paladin": act_paladin, "battlemage": act_battlemage}


def fight(build, variant, enemy_ids, seed, max_rounds=80):
    """多主敵:群戰全滅才勝;solo 王殺王即勝(BOSS 召喚爪牙隨王潰散,R134)。回 'win'/'dead'/'timeout'。"""
    c = make(build, variant)
    pots = FIXTURES[build][3] if build in FIXTURES else None
    base = _base(build)
    if pots is None:
        pots = SB._COMBAT_POTIONS if base in SB._MELEE_POT_BUILDS else 0
    if pots:
        inventory.add_item(c, "healing_potion", pots)
    prim = [combat.spawn_creature(gd, t, RNG(seed * 9 + 1 + i)) for i, t in enumerate(enemy_ids)]
    foes = list(prim)
    rng = RNG(seed)
    st = {"opening": True, "vanish": 0, "use_stance": base in SB._STANCE_BUILDS}
    act = POLICY[base]
    for _ in range(max_rounds):
        if not any(combat.is_alive(p) for p in prim):
            return "win"
        if c.health <= 0:
            return "dead"
        alive = [e for e in foes if combat.is_alive(e)]
        st["enemies"] = alive
        tgt = min(alive, key=lambda e: e.health)
        if not magic.is_incapacitated(c):
            act(c, tgt, rng, st)
        if not any(combat.is_alive(p) for p in prim):
            return "win"
        for e in prim:                                   # 主敵:有召喚譜者先判召喚(耗掉該回合攻擊)
            if combat.is_alive(e) and c.health > 0 and not magic.is_incapacitated(e):
                if combat.try_boss_summon(e, foes, gd, rng) is None:
                    _atk = combat.choose_attack(e, rng, c)
                    _ev = combat.resolve_attack(e, c, gd, rng, attack=_atk)
                    combat.misdirect_redirect(c, e, foes, gd, rng, _ev, _atk)
        for a in foes[len(prim):]:                       # 召喚爪牙(同回合即參戰)
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
    return "win" if not any(combat.is_alive(p) for p in prim) else "timeout"


def cell(task):
    label, build, variant, enemy_ids, n = task
    w = sum(fight(build, variant, enemy_ids, s) == "win" for s in range(n))
    return (label, build, variant, w / n)


# ---- 守衛 ---------------------------------------------------------------------------------------
DR = lambda k: ["dremora"] * k  # noqa: E731
GROUPS = [   # 搏命連斬的地盤:精英群 / 中期群戰
    ("魔人×8", "assassin", DR(8)), ("魔人×8", "warrior_1H", DR(8)), ("魔人×5", "paladin", DR(5)),
    ("2山賊+2狼", "lite_assassin", ["bandit", "bandit", "wolf", "wolf"]), ("4山賊", "lite_assassin", ["bandit"] * 4),
    ("魔人×3", "mid_warrior", DR(3)),
]
_DAG, _TRUE = ["mehrunes_dagon"], ["mehrunes_dagon_true"]
WALLS = [(g, b, ids) for b in ("warrior_1H", "assassin", "warrior_1H+fear", "assassin+fear", "warrior_1H+vamp", "assassin+vamp")
         for g, ids in (("達貢", _DAG), ("真身", _TRUE))] + [("真身", "battlemage", _TRUE)]
FLAG_LOSE, FLAG_TOO_STRONG, FLAG_WALL, FLAG_PARITY = 3.0, 25.0, 5.0, 2.0


def guard(n_group=1000, n_wall=2000):
    tasks = [(f"G|{g}", b, v, ids, n_group) for g, b, ids in GROUPS for v in CHOICE] + \
            [(f"W|{g}", b, v, ids, n_wall) for g, b, ids in WALLS for v in CHOICE]
    with Pool(16) as p:
        res = p.map(cell, tasks, chunksize=1)
    t = {}
    for label, b, v, w in res:
        t[(label, b)] = t.get((label, b), {})
        t[(label, b)][v] = w * 100
    flags = []
    gain_g, gain_w = [], []
    print(f"== 群戰(搏命連斬的地盤;n={n_group};勝率%,括號=相對『皆不選』pp)==")
    for (label, b), d in t.items():
        if label.startswith("G|"):
            sv, no, pr = d["savage"], d["none"], d["prec"]
            gain_g.append(sv - no)
            f = ""
            if sv - no < -FLAG_LOSE:
                f = " ⚠輸給皆不選"
            elif sv - no > FLAG_TOO_STRONG:
                f = " ⚠強度過頭"
            if f:
                flags.append(f"群戰 {label[2:]}·{b}{f}")
            print(f"  {label[2:]:10} {b:14} 無 {no:5.1f}  看破 {pr:5.1f}({pr - no:+5.1f})  搏命 {sv:5.1f}({sv - no:+5.1f}){f}")
    print(f"\n== 終王牆(看破的地盤;n={n_wall};勝率%)==")
    for (label, b), d in t.items():
        if label.startswith("W|"):
            sv, no, pr = d["savage"], d["none"], d["prec"]
            gain_w.append(pr - no)
            f = ""
            if sv - max(no, pr) > FLAG_WALL:
                f = " ⚠破牆線"
                flags.append(f"牆 {label[2:]}·{b}{f}")
            print(f"  {label[2:]:6} {b:16} 無 {no:5.1f}  看破 {pr:5.1f}({pr - no:+5.1f})  搏命 {sv:5.1f}({sv - no:+5.1f}){f}")
    mg, mw = S.median(gain_g), S.median(gain_w)
    ratio = mg / mw if mw > 0.05 else float("inf")
    f = " ⚠增益量級不相當" if ratio > FLAG_PARITY else ""
    if f:
        flags.append(f"相當性 {ratio:.2f}×{f}")
    print(f"\n== 相當性:搏命群戰增益中位 {mg:+.1f}pp ÷ 看破牆增益中位 {mw:+.1f}pp = {ratio:.2f}×"
          f"(設計目標 ≈1.5×,⚠ 門檻 {FLAG_PARITY}×){f}")
    print("\n" + ("⚠ 守衛警示:" + "; ".join(flags) if flags else "✓ 守衛全過(無 ⚠)"))


if __name__ == "__main__":
    guard(int(sys.argv[1]) if len(sys.argv) > 1 else 1000, int(sys.argv[2]) if len(sys.argv) > 2 else 2000)
