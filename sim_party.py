"""輔助型同伴對 SOLO BOSS 的平衡模擬(R86;非測試·手動跑:PYTHONPATH=. python3 sim_party.py)。

驗證「輔助但不破關」:玩家 build + 輔助同伴 vs solo boss,對比無同伴 baseline。複用 sim_builds 的
build 構築 + per-build policy,額外鏡像 main.run_battle 的**同伴階段**(R86 `companion_support_act`)。

🔴 紅線:① 帶同伴勝率**提升溫和**(不把難 boss 飆到 ~100%)② **無 stalemate**(逾時率≈0·治療不完全
抵銷 boss DPS)③ 仍有真實死亡風險。每回合:玩家行動 → 同伴支援/攻擊 → boss 反擊(偏好玩家 55%)→
回合末意志回魔 + tick_effects(全體)+ clamp。保真度邊界同 sim_builds(無走位/距離)。
"""
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import combat, magic, stats
from tesrpg.rng import RNG
import sim_builds as sb

gd = get_gamedata()


def _boss_target(player, allies, rng):
    """boss 選我方目標:偏好玩家(~55%),其餘打存活同伴(模型化 minion-tank 風險)。"""
    living = [a for a in allies if combat.is_alive(a)]
    if living and rng.chance(0.45):
        return rng.choice(living)
    return player


def fight(build_name, boss_id, companions, seed, max_rounds=80, cast=True):
    """一場:玩家 build + companions(id list)vs solo boss。回 'win'/'dead'/'timeout'。
    cast=False → 同伴只近戰(pre-R86 baseline·用來隔離『施法』本身的邊際效應 vs『多一個身體』)。"""
    c = sb.BUILDS[build_name]()
    boss = combat.spawn_creature(gd, boss_id, RNG(seed * 9 + 1))
    allies = [combat.spawn_companion(gd, cid, RNG(seed * 7 + i + 1)) for i, cid in enumerate(companions)]
    rng = RNG(seed)
    act = sb._POLICY[build_name]
    st = {"opening": True, "vanish": 0, "aimed": build_name == "archer", "skip_boss": False}
    for _ in range(max_rounds):
        if not combat.is_alive(boss):
            return "win"
        if c.health <= 0:
            return "dead"
        c._evade_counter_used = False
        st["skip_boss"] = False
        if not magic.is_incapacitated(c):                      # 玩家行動
            act(c, boss, rng, st)
        if not combat.is_alive(boss):
            return "win"
        for a in allies:                                       # 同伴階段(鏡像 main.py:994 + R86 支援)
            if not combat.is_alive(boss):
                break
            if not combat.is_alive(a) or magic.is_incapacitated(a):
                continue
            a._evade_counter_used = False
            if cast and magic.companion_support_act(a, c, allies, gd) is not None:
                continue                                       # 用本回合支援
            combat.resolve_attack(a, boss, gd, rng, attack=combat.choose_attack(a, rng, boss))
        if not combat.is_alive(boss):
            return "win"
        if not st["skip_boss"]:                                # boss 反擊(偏好玩家)
            tgt = _boss_target(c, allies, rng)
            combat.resolve_attack(boss, tgt, gd, rng, attack=combat.choose_attack(boss, rng, tgt))
        sb._regen(c)                                           # 回合末維護
        magic.tick_effects(c, gd)
        for a in allies:
            if combat.is_alive(a):
                magic.tick_effects(a, gd)
        if combat.is_alive(boss):
            magic.tick_effects(boss, gd)
        stats.clamp_resources(c)
    return "win" if not combat.is_alive(boss) else "timeout"


def rates(build_name, boss_id, companions, n=200, cast=True):
    res = [fight(build_name, boss_id, companions, s, cast=cast) for s in range(n)]
    return (sum(r == "win" for r in res) / n, sum(r == "timeout" for r in res) / n)


# ── R87 敵方支援施法者:玩家 vs 含治療者的敵群(威脅但可破解)─────────────────────
def make_mid_warrior():
    """中階戰士(精靈裝·~60 技能)= 能從容清 trash 的代表性玩家(apex 會無腦輾過 → 量不出治療者效應)。"""
    c = sb.build_character(gd, name="中", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(blade=60, heavy_armor=60, block=55, athletics=50)
    c.attributes.update(strength=70, endurance=75, agility=55)
    c.weapon = "elven_sword"
    sb.inventory.add_item(c, "elven_sword", 1)
    sb._equip_set(c, "elven")
    sb.stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def fight_group(enemy_ids, seed, max_rounds=60, cast=True, focus_healer=True):
    """中階戰士 vs 敵群(含治療者)。回 'win'/'dead'/'timeout'。
    cast=False → 敵方治療者只近戰(隔離『施法』邊際);focus_healer=True → 玩家優先打帶 spells 的怪(破解)。"""
    c = make_mid_warrior()
    enemies = [combat.spawn_creature(gd, eid, RNG(seed * 13 + i + 1)) for i, eid in enumerate(enemy_ids)]
    rng = RNG(seed)

    def alive_en():
        return [e for e in enemies if combat.is_alive(e)]

    def pick():
        living = alive_en()
        if focus_healer:
            healers = [e for e in living if gd.bestiary.get(e.template_id, {}).get("spells")]
            if healers:
                return healers[0]
        return living[0] if living else None

    for _ in range(max_rounds):
        if not alive_en():
            return "win"
        if c.health <= 0:
            return "dead"
        c._evade_counter_used = False
        tgt = pick()                                           # 玩家攻擊選定目標(focus healer = 破解)
        if tgt is not None and not magic.is_incapacitated(c):
            combat.player_attack_cost(c, gd)
            combat.resolve_attack(c, tgt, gd, rng)
        if not alive_en():
            return "win"
        for e in alive_en():                                   # 敵方階段:支援 or 攻擊(鏡像 main.py:1015 + R87)
            if magic.is_incapacitated(e):
                continue
            if cast and magic.enemy_support_act(e, enemies, gd) is not None:
                continue
            combat.resolve_attack(e, c, gd, rng, attack=combat.choose_attack(e, rng, c))
            if c.health <= 0:
                return "dead"
        sb._regen(c)
        magic.tick_effects(c, gd)
        for e in alive_en():
            magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    return "win" if not alive_en() else "timeout"


def group_rates(enemy_ids, n=300, cast=True, focus_healer=True):
    res = [fight_group(enemy_ids, s, cast=cast, focus_healer=focus_healer) for s in range(n)]
    return (sum(r == "win" for r in res) / n, sum(r == "timeout" for r in res) / n,
            sum(r == "dead" for r in res) / n)


if __name__ == "__main__":
    solo = [bid for bid, b in gd.bestiary.items() if b.get("solo")]
    solo.sort(key=lambda b: gd.bestiary[b].get("max_health", 0))
    # 聚焦最硬的 boss(中段 warrior 本就 ~100%·R86 邊際無感);取最硬幾隻看「施法 vs 純近戰」邊際
    hard = solo[-3:]
    scenarios = [
        ("warrior_1H", ["hedge_mage"]),
        ("warrior_1H", ["shieldmaiden"]),
        ("warrior_1H", ["veteran"]),
        ("warrior_1H", ["hedge_mage", "shieldmaiden", "veteran"]),
        ("battlemage", ["hedge_mage"]),
    ]
    print("== R86 輔助同伴平衡:『施法』的邊際效應(勝率·n=200)==")
    print("🔴 紅線:同伴施法 vs 純近戰(同隊伍)差距溫和(不把『多身體』再大幅放大)· 無 stalemate · solo 仍有真實難度\n")
    for bid in hard:
        b = gd.bestiary[bid]
        solo_w, _ = rates("warrior_1H", bid, [])
        bm_solo_w, _ = rates("battlemage", bid, [])
        print(f"-- {bid} (HP {b.get('max_health')}·{b.get('attack', {}).get('element', 'phys')}) "
              f"| 單人 warrior_1H {solo_w:.0%} · battlemage {bm_solo_w:.0%} --")
        for build, comps in scenarios:
            wc, tc = rates(build, bid, comps, cast=True)
            wn, tn = rates(build, bid, comps, cast=False)
            label = f"{build} + {'+'.join(comps)}"
            flag = "  ⚠STALE" if tc > 0.05 else ""
            print(f"  {label:42} 施法 {wc:5.0%}  純近戰 {wn:5.0%}  Δ施法 {wc - wn:+4.0%}{flag}")
        print()

    # ── R87 敵方支援施法者:中階戰士 vs 含治療者的敵群 ──────────────────────────
    print("== R87 敵方支援施法者:中階戰士 vs 含治療者敵群(勝率 / 逾時·n=300)==")
    print("🔴 紅線:① trash 群仍可殺(先點治療者→勝率高·無 stalemate)② 施法 vs 純近戰邊際合理"
          " ③ 不先點治療者會更硬但仍可勝(治療有意義非無敵)\n")
    groups = [
        ["bandit", "moor_witch"],
        ["bandit", "bandit", "moor_witch"],
        ["skeleton", "skeleton", "glenmoril_witch"],
        ["goblin", "goblin", "goblin_shaman"],
    ]
    for g in groups:
        g = [e for e in g if e in gd.bestiary]
        if not g:
            continue
        wF, tF, _ = group_rates(g, cast=True, focus_healer=True)     # 施法 + 先點治療者(破解)
        wN, tN, _ = group_rates(g, cast=True, focus_healer=False)    # 施法 + 隨機目標(不破解)
        wB, tB, _ = group_rates(g, cast=False, focus_healer=False)   # 純近戰 baseline(無敵方施法)
        healer = next(e for e in g if gd.bestiary[e].get("spells"))
        sflag = "  ⚠STALE" if max(tF, tN, tB) > 0.05 else ""
        print(f"-- {'+'.join(g)} (治療者={healer}) --")
        print(f"   施法·先點治療者 win {wF:4.0%}  | 施法·隨機目標 win {wN:4.0%}  | 純近戰 baseline win {wB:4.0%}"
              f"   逾時 {max(tF, tN, tB):3.0%}{sflag}")
