"""刺客流派平衡回歸模擬(非測試;手動跑:PYTHONPATH=. python3 sim_assassin.py)。

量化「偷襲先攻沒殺死 → 困境」的改善幅度與是否過強。改了 formulas 的刺客常數
(SNEAK_BLEED_*/STAGGER_HIT_PENALTY/OFFHAND_DAMAGE_FACTOR/RESTEALTH_*/
STEALTH_RETREAT_*)後重跑,對照下列指標確認:
  - 失手後群戰死亡率明顯下降(殘響/隱遁救得了失手)
  - 三敵硬闖仍偏致命(難度靠內容,沒被無腦碾壓)
  - 高血/高甲精英仍擋得住一擊(雙持沒讓偷襲萬能)
"""
from tesrpg.gamedata import get_gamedata
from tesrpg.creation import build_character
from tesrpg.systems import combat, magic, stats, inventory
from tesrpg.rng import RNG

gd = get_gamedata()


def assassin(sneak=70, blade=50, alchemy=40, scout=40, weapon="steel_dagger", dual=False,
             mastery_choices=None, **extra_skills):
    c = build_character(gd, name="刺", sex="male", race="khajiit",
                        birthsign="shadow", class_id="assassin")
    c.skills.update(sneak=sneak, blade=blade, alchemy=alchemy, scout=scout, **extra_skills)
    c.weapon = weapon
    if dual:
        inventory.add_item(c, weapon, 2)
        inventory.equip_offhand(c, gd, weapon)
    if mastery_choices:                        # {node_id: opt_id};須先把 base skill 設到門檻
        from tesrpg.systems import mastery
        for nid, oid in mastery_choices.items():
            mastery.choose(c, gd, nid, oid)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def _round(c, foes, rng, opening, used):
    """打一個回合:低血(<45%)且能隱遁就嘗試隱遁,否則攻最低血敵人。回傳新的 opening。"""
    alive = [e for e in foes if combat.is_alive(e)]
    if c.health < c.max_health * 0.45 and combat.can_vanish(c, gd) \
            and combat.try_vanish(c, len(alive), used[0], rng):
        used[0] += 1
        return True                          # 隱遁成功:敵人撲空、重置偷襲
    tgt = min(alive, key=lambda e: e.health)
    combat.resolve_attack(c, tgt, gd, rng, sneak_attack=opening)
    for e in foes:
        if combat.is_alive(e) and c.health > 0 and not magic.is_incapacitated(e):
            combat.resolve_attack(e, c, gd, rng)
    return False


def fight(maker, enemy_ids, seed):
    c = maker()
    foes = [combat.spawn_creature(gd, t, RNG(seed * 9 + i)) for i, t in enumerate(enemy_ids)]
    rng = RNG(seed)
    opening, used = True, [0]
    for _ in range(50):
        if not any(combat.is_alive(e) for e in foes):
            return "win"
        if c.health <= 0:
            return "dead"
        opening = _round(c, foes, rng, opening, used)
        magic.tick_effects(c, gd)
        for e in foes:
            if combat.is_alive(e):
                magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    return "win" if not any(combat.is_alive(e) for e in foes) else "timeout"


def rate(maker, ids, outcome="dead", n=2000):
    return sum(fight(maker, ids, s) == outcome for s in range(n)) / n


def oneshot(maker, tid, n=2500):
    k = 0
    for i in range(n):
        ev = combat.resolve_attack(maker(), combat.spawn_creature(gd, tid, RNG(i + 1)),
                                   gd, RNG(i * 7 + 3), sneak_attack=True)
        k += ev["defender_dead"]
    return k / n


if __name__ == "__main__":
    mid = lambda: assassin()
    mid_dual = lambda: assassin(dual=True)

    print("== 偷襲一擊秒殺率(中階 sneak70)單持 vs 雙持 ==")
    for t in ["bandit", "skeleton", "vampire_fledgling", "dremora", "frost_troll"]:
        single = oneshot(lambda: assassin(), t)
        twin = oneshot(lambda: assassin(dual=True), t)
        print(f"  {t:18} 單持 {single:5.1%}   雙持 {twin:5.1%}")

    print("\n== 群戰死亡率(含殘響/隱遁/低血自動隱遁策略)==")
    for name, ids in [("1 bandit", ["bandit"]), ("2 bandit", ["bandit", "bandit"]),
                      ("2 bandit+wolf", ["bandit", "bandit", "wolf"]),
                      ("1 vampire_fledgling", ["vampire_fledgling"])]:
        print(f"  {name:20} 單持 {rate(mid, ids):6.1%}   雙持 {rate(mid_dual, ids):6.1%}")

    # P2 里程碑:非潛行 weapon_mod 在偷襲倍率「之前」套 → 對精英秒殺率衝擊應極小
    print("\n== P2 里程碑覆核:blade 迅捷連斬(power+0.12,以 flat 補傷加在偷襲倍率之後)==")
    apex_blade = lambda: assassin(sneak=70, blade=100,
                                  mastery_choices={"blade_100": "savage"})
    for t in ["dremora", "frost_troll"]:
        base = oneshot(lambda: assassin(blade=100), t)
        mod = oneshot(apex_blade, t)
        flag = " ⚠破1.5%" if mod > 0.015 else ""
        print(f"  {t:18} 無里程碑 {base:5.1%} → 迅捷連斬 {mod:5.1%}{flag}")

    # P4 刺客 apex:影刃(sneak_mult ×1.5)→ 對小遭遇可無傷清場(刻意);反制=「>3 敵潛匿大減 + 隱遁耗體」
    import tesrpg.systems.combat as C

    def apex_max(temper=5):
        """最壞情形『可達成』apex:玻璃匕首雙持 + 黑兄聆聽者(夜母×1.18)+ 淬鍊 +5 + 影刃。
        對 solo boss 的單擊秒殺率即『solo boss 仍存活』契約的真實檢驗(覆核審查抓到的 sim 覆蓋缺口)。"""
        c = assassin(sneak=100, blade=100, alchemy=60, scout=100, weapon="glass_dagger", dual=True,
                     smithing=100, acrobatics=100, mastery_choices={"sneak_100": "shadowblade"})
        c.factions["dark_brotherhood"] = 6              # 聆聽者(夜母祝福滿階 ×1.18)
        c.weapon_temper = {"glass_dagger": temper}      # smithing 100 的合法淬鍊上限
        return c

    print("\n== P4 apex 覆核(契約①):影刃 sneak100 雙持 → 小遭遇/精英秒殺(力量幻想成立)==")
    base100 = lambda: assassin(sneak=100, dual=True)
    apex = lambda: assassin(sneak=100, blade=100, alchemy=60, scout=75, dual=True,
                            mastery_choices={"sneak_100": "shadowblade"})
    for t in ["bandit", "skeleton", "dremora", "frost_troll"]:
        print(f"  {t:16} 無里程碑 {oneshot(base100, t):5.1%} → 影刃 {oneshot(apex, t):5.1%}")

    print("\n== solo BOSS 單擊秒殺率(最壞 apex:玻璃雙持 + 聆聽者 + 淬鍊5 + 影刃)==")
    print("   紅線:approved plan『solo boss 仍存活』→ SOLO_SNEAK_DAMAGE_CAP_RATIO 夾限應使其全為 0%:")
    for t in ["dremora_lord", "vampire_lord", "wamasu", "frost_giant", "ancient_dragon",
              "mehrunes_dagon", "mehrunes_dagon_diminished"]:
        hp = gd.bestiary[t].get("max_health", "?")
        rate_max = oneshot(apex_max, t)
        flag = " ⚠破紅線(應為 0%)" if rate_max > 0.0 else " ✓存活"
        print(f"  {t:16} (HP {hp})  最壞 apex 秒殺 {rate_max:5.1%}{flag}")

    print("\n== R37 鋒銳覆核:temper_power apex(全鋒銳 50/75/100 → cap6+power0.25 → 武器淬鍊 +15 vs apex_max +10)==")
    def apex_temper():
        """R37 最壞鋒銳:apex_max + smithing 全鋒銳側(temper_edge 0.10 + master_temper cap6 + temper_mastery 0.15)。
        武器淬鍊 flat = 6×2×1.25 = 15(較 apex_max temper5 的 +10 更高)→ 驗 temper_power 不破 solo cap/精英 oneshot。"""
        c = apex_max(temper=6)
        c.mastery_choices.update({"smithing_50": "temper_edge", "smithing_75": "master_temper",
                                  "smithing_100": "temper_mastery"})
        return c
    for t in ["dremora_lord", "ancient_dragon", "mehrunes_dagon"]:   # ① solo boss 仍須 0%(cap 保護 flat 加傷)
        srate = oneshot(apex_temper, t)
        flag = " ⚠破紅線(應為 0%)" if srate > 0.0 else " ✓存活"
        print(f"  solo {t:16} temper_power apex 秒殺 {srate:5.1%}{flag}")
    for t in ["dremora", "frost_troll"]:                             # ② 精英 oneshot 增幅 < 2%(temper flat 偷襲放大唯一風險點)
        base = oneshot(apex_max, t)
        mod = oneshot(apex_temper, t)
        flag = " ⚠破2%" if (mod - base) > 0.02 else ""
        print(f"  精英 {t:18} apex_max {base:5.1%} → temper_power {mod:5.1%}(Δ{mod - base:+.1%}){flag}")
    # ③ 群戰死亡率(對抗審查補):隔離 temper_power 邊際效應 —— 同淬鍊6 build,有/無 power。
    #    註:tempered glass_dagger apex 本就把 4-bandit 死亡率壓到 ~0.4%(既有 tempering+裝備,**非本輪引入**;
    #    舊 26.2% 紅線量的是「無淬鍊」apex,非真實最壞)。此處只驗 temper_power 的邊際不再壓垮。
    dr_notemper = rate(lambda: apex_max(temper=6), ['bandit'] * 4)   # 淬鍊6,factor 0
    dr_power = rate(apex_temper, ['bandit'] * 4)                     # 淬鍊6 + temper_power 0.25
    flag = " ⚠temper_power 邊際壓垮(>10pp)" if (dr_notemper - dr_power) > 0.10 else ""
    print(f"  4 bandit 死亡率(淬鍊6)  無power {dr_notemper:.1%} → +temper_power {dr_power:.1%}(Δ{dr_power - dr_notemper:+.1%}){flag}")

    print("\n== P4 反制覆核(契約②):群體規模 → 潛近/隱遁機率陡降(>3 敵大減)==")
    relent = lambda: assassin(sneak=100, acrobatics=100, dual=True,
                              mastery_choices={"sneak_75": "relentless_shadow"})
    for n in (1, 2, 3, 4, 5):
        a = apex()
        foes = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(n)]
        appr = C.stealth_approach_chance(a, foes, gd)
        van = C.vanish_chance(relent(), n, 2, gd)   # 連環踏影(免遞減)在 n 敵、已用 2 次
        print(f"  {n} 敵:潛近 {appr:5.1%}   連環踏影隱遁(used=2) {van:5.1%}")

    print("\n== P4 反制覆核(契約②):4 敵群戰死亡率(apex 仍須承受真實風險)==")
    print(f"  4 bandit       apex 死亡率 {rate(apex, ['bandit'] * 4):5.1%}")
    print(f"  2 bandit+2wolf apex 死亡率 {rate(apex, ['bandit', 'bandit', 'wolf', 'wolf']):5.1%}")
