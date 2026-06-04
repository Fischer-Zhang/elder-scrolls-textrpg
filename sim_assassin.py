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


def assassin(sneak=70, blade=50, alchemy=40, scout=40, weapon="steel_dagger", dual=False):
    c = build_character(gd, name="刺", sex="male", race="khajiit",
                        birthsign="shadow", class_id="assassin")
    c.skills.update(sneak=sneak, blade=blade, alchemy=alchemy, scout=scout)
    c.weapon = weapon
    if dual:
        inventory.add_item(c, weapon, 2)
        inventory.equip_offhand(c, gd, weapon)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def _round(c, foes, rng, opening, used):
    """打一個回合:低血(<45%)且能隱遁就嘗試隱遁,否則攻最低血敵人。回傳新的 opening。"""
    alive = [e for e in foes if combat.is_alive(e)]
    if c.health < c.max_health * 0.45 and combat.can_vanish(c) \
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
