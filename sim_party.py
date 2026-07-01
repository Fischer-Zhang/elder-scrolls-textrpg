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


# ── R105 召喚師深化:專精召喚(conj100)vs solo boss(召喚物隨召喚主成長 + 坦克嘲諷)───────
_ATRO_BY_ELEM = {"fire": "conjure_flame_atronach", "frost": "conjure_frost_atronach", "shock": "conjure_storm_atronach"}
_SUM_NUKE = ["fireball", "flames"]


def _living_allies(battle):
    return [a for a in battle["allies"] if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)]


def _best_atronach(boss):
    """對 boss 抗性最低的元素 atronach(鏡像 _mage_act 的『選最佳元素』智能;召喚師也會挑對系)。"""
    el = min(("fire", "frost", "shock"),
             key=lambda e: boss.resist.get(e, 0) if hasattr(boss, "resist") else 0)
    return _ATRO_BY_ELEM[el]


def _summoner_act(c, boss, rng, battle, st):
    """召喚師策略:保 1 坦克魔人(嘲諷吸火力)+ 2 隻對系 atronach(玻璃大砲)→ 石肌 → 弱破壞術。"""
    living = _living_allies(battle)
    have_tank = any(a.template_id == "summoned_dremora" for a in living)
    best_atro = _best_atronach(boss)
    best_cre = gd.spells[best_atro]["effect"]["creature"]
    n_atro = sum(1 for a in living if a.template_id == best_cre)
    have_healer = any(a.template_id == "summoned_healer" for a in living)
    if len(living) < 3:
        if not have_tank and magic.can_cast(c, gd, "conjure_dremora"):
            magic.cast(c, gd, "conjure_dremora", rng, battle=battle)
            return
        if not have_healer and magic.can_cast(c, gd, "conjure_healer"):   # R106 支援召喚:1 治療精靈
            magic.cast(c, gd, "conjure_healer", rng, battle=battle)
            return
        if n_atro < 1 and magic.can_cast(c, gd, best_atro):
            magic.cast(c, gd, best_atro, rng, battle=battle)
            return
    if not st.get("buffed") and magic.can_cast(c, gd, "stoneflesh"):
        st["buffed"] = True
        magic.cast(c, gd, "stoneflesh", rng)
        return
    if c.health < c.max_health * 0.4 and magic.can_cast(c, gd, "close_wounds"):
        magic.cast(c, gd, "close_wounds", rng)
        return
    for sid in _SUM_NUKE:                              # 弱破壞術(destruction 25)
        if magic.can_cast(c, gd, sid):
            magic.cast(c, gd, sid, rng, target=boss, enemies=[boss], battle=battle)
            return
    sb._regen(c)                                      # 空藍 → 該回合等回魔


def fight_summoner(boss_id, seed, max_rounds=80):
    c = sb.make_summoner()
    boss = combat.spawn_creature(gd, boss_id, RNG(seed * 9 + 1))
    rng = RNG(seed)
    battle = {"allies": []}
    st = {"buffed": False}
    for _ in range(max_rounds):
        if not combat.is_alive(boss):
            return "win"
        if c.health <= 0:
            return "dead"
        if not magic.is_incapacitated(c):
            _summoner_act(c, boss, rng, battle, st)
        if not combat.is_alive(boss):
            return "win"
        for a in _living_allies(battle):              # 召喚物階段(鏡像 main.py ally phase + R105 嘲諷 + R106 支援施法)
            if not combat.is_alive(boss):
                break
            if magic.is_incapacitated(a):
                continue
            if magic.summon_support_act(a, c, _living_allies(battle), gd) is not None:   # R106 治療精靈施治療
                continue
            a_atk = combat.choose_attack(a, rng, boss)
            if a_atk.get("taunt"):
                a.active_effects.append({"kind": "taunt", "turns": a_atk.get("turns", 3)})
                continue
            combat.resolve_attack(a, boss, gd, rng, attack=a_atk)
        if not combat.is_alive(boss):
            return "win"
        tgt = combat.pick_player_side_target(c, battle["allies"], rng)   # boss 反擊(嘲諷 aggro 生效)
        combat.resolve_attack(boss, tgt, gd, rng, attack=combat.choose_attack(boss, rng, tgt))
        for a in battle["allies"]:                    # 回合末:召喚時效 + tick
            if a.summon_turns is not None:
                a.summon_turns -= 1
        battle["allies"][:] = _living_allies(battle)
        sb._regen(c)
        magic.tick_effects(c, gd)
        for a in battle["allies"]:
            if combat.is_alive(a):
                magic.tick_effects(a, gd)
        if combat.is_alive(boss):
            magic.tick_effects(boss, gd)
        stats.clamp_resources(c)
    return "win" if not combat.is_alive(boss) else "timeout"


def summoner_rates(boss_id, n=200):
    res = [fight_summoner(boss_id, s) for s in range(n)]
    return (sum(r == "win" for r in res) / n, sum(r == "timeout" for r in res) / n)


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

    # ── R105 召喚師深化:專精召喚(conj100)vs solo boss ──────────────────────────
    print("\n== R105 召喚師深化:專精召喚(conj100·其他25·法師裝)vs solo boss(win / 逾時·n=200)==")
    print("🔴 目標:召喚師 ≈ 頂級法師(對照 sim_builds mage:多數 90-96%·終王 dagon 0%)· 無 stalemate · 不 trivialize 終王\n")
    solo = sorted([bid for bid, b in gd.bestiary.items() if b.get("solo")],
                  key=lambda b: gd.bestiary[b].get("max_health", 0))
    sample = solo[:2] + solo[len(solo) // 2 - 1: len(solo) // 2 + 1] + solo[-3:]
    for bid in dict.fromkeys(sample):
        b = gd.bestiary[bid]
        w, t = summoner_rates(bid)
        flag = "  ⚠STALE" if t > 0.05 else ""
        print(f"  {bid:22} (HP {b.get('max_health'):3}·{b.get('attack', {}).get('element', 'phys'):5}) "
              f"win {w:5.0%}  逾時 {t:4.0%}{flag}")
