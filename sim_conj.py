"""R203 召喚守衛:非亡者召喚物同場名額 + conjuration 里程碑選項(非測試;手動跑:PYTHONPATH=. python3 sim_conj.py [n]
print-only,不自動擋;接進 check.sh:`--sim`,或 git diff 動到 formulas / combat / magic / necromancy / mastery / powers / mastery.json / spells.json 自動跑)。

為什麼有這支(R203 前置發現,2026-11-22):`sim_party._summoner_act` 曾寫死「最多 3 隻」,遊戲規則卻沒有非亡者名額 →
「召喚師打達貢 0%」是**政策的產物**;貪婪 + 地城預召喚下不選 21%、持久召喚 54%。同型舊案:R106C 的 `min(3, cap)` 遮蔽終王牆破口。
本檔的政策**一律引用規則常數**(formulas.SUMMON_FIELD_CAP / necromancy.undead_field_cap),規則被移除或改大時守衛會亮 ⚠。

量什麼(對達貢 720 HP,含 BOSS 爪牙 try_boss_summon、盟友隨機選敵 — 鏡像 main.py ally 階段):
  ① 終王牆:S 召喚師(保守:坦克 + 治療 + 對系 atronach / 激進:全元素 atronach 填滿名額)、N base 死靈師、N 極致死靈師;
     情境:單場 / 地城預召喚(自由行動、不回魔,進格 −1 回合)。
     ⚠ 守衛警示:召喚師 / base 死靈師 勝率 > 5%(牆破了)。極致死靈師只印(使用者拍板「可破牆但難以推疊到極致」)。
  ② 名額規則探針:法力管夠連施 10 道召喚,場上非亡者召喚物不得超過 SUMMON_FIELD_CAP。⚠ 失效即警示。
  ③ conjuration 50 / 75 / 100 各選項 vs 全不選(S 激進、N base;古龍 / 烏瑪利):Δ勝率 pp。
     瞬發契印(75-a)以 `player_phase` 忠實建模:召喚系施法免耗回合 + 召喚物陣亡回補(`combat.quick_seal_*` 與 main 共用)。
  ⑤ 束縛兵刃(R204):握法規則探針(單手盾下巨劍 / 戰斧不可凝、重盾下任何束縛皆不可)+ 束縛騎士(雙手 / 單手版)打達貢 ⚠ > 8%。
  ④ 群戰(R203c / R203d 的主場;單場 BOSS 戰沒有「第一具屍體」):S 激進 / S 保守 / N base × 8 種敵群(含同類會掉到 100% 以下的難組合);
     `fight_pack` 鏡像 main 回合結構,就地起屍走 `necromancy.auto_raise`。
     ⚠ 守衛口徑(R203 評估後改版,使用者 2026-11-22 拍板):裝上選項後的召喚師勝率 > 同敵群「最強同類」(PEERS:戰士 1H/2H、弓手、刺客、盾反;
     sim_builds 標準策略 `solo_pack`)+ 5pp = 強度過頭;選項比不選差 > 8pp = 輸給不選。**不再用「同構築選項 vs 不選 > +25pp」**:起手慢的激進策略
     不選時墊底(難敵群 4%),Δ 天然 +60,但裝上瞬發契印後仍低於戰士 1H / 弓手 / 刺客 —— 內比 Δ 會誤報(同類全 100% 的敵群不能判斷,故含難組合)。
     ⚠ 守衛警示:選項比不選更差 > 8pp(輸給不選)或 > +25pp(強度過頭)。n 小時 ≤ 5pp 視為雜訊。
⚠ 已知保真度邊界:政策是「合理」非「完美」;單場 + 預召喚不等於整趟地城(token 淨額 / 帶進 BOSS 格的軍團規模需 sim_dungeon 整趟模式,後續補)。
"""
import collections
import sys
import time

import sim_builds as sb
import sim_party as sp
from tesrpg import formulas
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, magic, mastery, necromancy, party, stats

gd = sb.gd
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
NODES = ("conjuration_50", "conjuration_75", "conjuration_100")
WALL_BOSS = "mehrunes_dagon"
EFFECT_BOSSES = ("ancient_dragon", "umaril_the_unfeathered")
WALL_FLAG_PCT = 5.0            # 召喚師 / base 死靈師打達貢 > 5% = 牆破了
WORSE_FLAG_PP = 8.0            # 選項比不選差 > 8pp
OVERPOWER_FLAG_PP = 25.0       # 選項比不選強 > 25pp
flags: list[str] = []


# ── 政策(上限一律引用規則常數)────────────────────────────────────────────────
def act_conservative(c, boss, rng, battle, st):
    """保守:sim_party 原召喚師政策(坦克 + 治療精靈 + 對系 atronach;上限已改引用 SUMMON_FIELD_CAP)。"""
    n0 = len(battle["allies"])
    sp._summoner_act(c, boss, rng, battle, st)
    return "summon" if len(battle["allies"]) > n0 else None


def act_aggressive(c, boss, rng, battle, st):
    """激進:名額內全放對系 atronach(最大輸出);滿額後石肌 / 弱術 / 回魔。名額判定走規則函式,不寫死 3。"""
    if magic.nonundead_summon_count(battle) < formulas.SUMMON_FIELD_CAP:
        best = sp._best_atronach(boss)
        if magic.can_cast(c, gd, best):
            magic.cast(c, gd, best, rng, battle=battle)
            return "summon"
    if c.health < c.max_health * 0.4 and magic.can_cast(c, gd, "close_wounds"):
        magic.cast(c, gd, "close_wounds", rng)
        return None
    if not st.get("buffed") and magic.can_cast(c, gd, "stoneflesh"):
        st["buffed"] = True
        magic.cast(c, gd, "stoneflesh", rng)
        return None
    for sid in ("fireball", "flames"):
        if magic.can_cast(c, gd, sid):
            magic.cast(c, gd, sid, rng, target=boss, enemies=[boss], battle=battle)
            return None
    sb._regen(c)
    return None


def act_necro(c, boss, rng, battle, st):
    n0 = len(battle["allies"])
    sp._necromancer_act(c, boss, rng, battle, st)
    return "summon" if len(battle["allies"]) > n0 else None


# ── 戰鬥(鏡像 main.py:BOSS 爪牙 + 盟友隨機選敵 + 地城預召喚;回合結算走 combat.tick_summons)───────────────
def player_phase(c, boss, rng, battle, st, act):
    """玩家階段(鏡像 main.run_battle 選單階段):政策回 "summon" = 這回合施了召喚系(conjuration 學派)法術;
    R203c 瞬發契印在手(`combat.quick_seal_ready`,與 main 同一個閘)→ 該施法免耗回合,同回合再行動一次。
    未選契印者 quick_seal_ready 恆 False → 與改前逐位元組相同。"""
    r = act(c, boss, rng, battle, st)
    if r == "summon" and combat.quick_seal_ready(c, gd, "conjure_dremora"):
        combat.quick_seal_spend(c)
        act(c, boss, rng, battle, st)


def fight(maker, act, boss_id, seed, presummon=0, max_rounds=80):
    c = maker()
    boss = combat.spawn_creature(gd, boss_id, RNG(seed * 9 + 1))
    enemies = [boss]
    rng = RNG(seed)
    battle = {"allies": []}
    st = {"buffed": False}
    for _ in range(presummon):                              # 地城預召喚:自由行動、不回魔;進 BOSS 格 −1 回合
        if act(c, boss, rng, battle, st) != "summon":
            break
    if presummon:
        battle["allies"], _gone = combat.tick_summons(battle["allies"])
    rounds = 0
    for _ in range(max_rounds):
        if not combat.is_alive(boss):
            return "win", rounds, 0
        if c.health <= 0:
            return "dead", rounds, boss.health
        rounds += 1
        if not magic.is_incapacitated(c):
            player_phase(c, boss, rng, battle, st, act)
        if not combat.is_alive(boss):
            return "win", rounds, 0
        alive_e = [e for e in enemies if combat.is_alive(e)]
        for a in sp._living_allies(battle):
            if not combat.is_alive(boss):
                break
            if magic.is_incapacitated(a):
                continue
            if magic.summon_support_act(a, c, sp._living_allies(battle), gd) is not None:
                continue
            tgt = party.ally_target(c, a, [e for e in enemies if combat.is_alive(e)], gd, rng)   # R205 單一決策點
            a_atk = combat.choose_attack(a, rng, tgt)
            if a_atk.get("taunt"):
                a.active_effects.append({"kind": "taunt", "turns": a_atk.get("turns", 3)})
                continue
            combat.resolve_attack(a, tgt, gd, rng, attack=a_atk)
        if not combat.is_alive(boss):
            return "win", rounds, 0
        for e in list(enemies):
            if c.health <= 0:
                break
            if not combat.is_alive(e) or magic.is_incapacitated(e):
                continue
            if combat.try_boss_summon(e, enemies, gd, rng) is not None:
                continue
            tgt = combat.pick_player_side_target(c, battle["allies"], rng)
            combat.resolve_attack(e, tgt, gd, rng, attack=combat.choose_enemy_attack(e, rng, tgt))
        battle["allies"], _gone = combat.tick_summons(battle["allies"])
        combat.quick_seal_recharge(c, gd, _gone)            # R203c:非亡者召喚物陣亡 → 契印重新凝聚(同 main 回合末)
        sb._regen(c)
        magic.tick_effects(c, gd)
        for a in battle["allies"]:
            if combat.is_alive(a):
                magic.tick_effects(a, gd)
        for e in enemies:
            if combat.is_alive(e):
                magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    return ("win" if not combat.is_alive(boss) else "timeout"), rounds, max(0, boss.health)


def rate(maker, act, boss_id, presummon=0, n=None):
    n = n or N
    res = [fight(maker, act, boss_id, s, presummon=presummon) for s in range(n)]
    c = collections.Counter(r[0] for r in res)
    return c["win"] * 100.0 / n, sum(r[1] for r in res) / n, sum(r[2] for r in res) / n


def variant(mk, node=None, opt=None):
    def f():
        c = mk()
        for nid in NODES:
            c.mastery_choices.pop(nid, None)
        if node:
            c.mastery_choices[node] = opt
        stats.recompute_max_resources(c, gd, restore_full=True)
        return c
    return f


def flag(msg):
    flags.append(msg)
    print(f"  ⚠ 守衛警示:{msg}", flush=True)


# ── ① 終王牆 ──────────────────────────────────────────────────────────────────
def wall():
    print(f"== ① 終王牆:對 {WALL_BOSS}(720 HP,含爪牙 / 盟友隨機選敵)  n={N}/格  格式 勝率% | 平均回合 | 王剩餘血 ==", flush=True)
    rows = [("S 召喚師·保守", sb.make_summoner, act_conservative, (0, 20)),
            ("S 召喚師·激進", sb.make_summoner, act_aggressive, (0, 20)),
            ("N base 死靈師", sb.make_necromancer, act_necro, (0, 20)),
            ("N 極致死靈師", sb.make_necromancer_maxed, act_necro, (0, 20))]
    for label, mk, act, pres in rows:
        for p in pres:
            t = time.time()
            win, rnd, left = rate(variant_keep(mk), act, WALL_BOSS, presummon=p)
            print(f"{label:14} {'預召喚' if p else '單場  '}  {win:5.1f}% | {rnd:5.1f} | {left:4.0f}   ({time.time() - t:.0f}s)", flush=True)
            if not label.startswith("N 極致") and win > WALL_FLAG_PCT:
                flag(f"{label}({'預召喚' if p else '單場'})打達貢勝率 {win:.0f}% > {WALL_FLAG_PCT:.0f}% —— 牆破了:檢查 SUMMON_FIELD_CAP 是否被移除 / 政策是否繞過規則")


def variant_keep(mk):
    return mk                                               # 夾具原樣(含其內建的里程碑選擇)


# ── ② 名額規則探針 ─────────────────────────────────────────────────────────────
def probe():
    c = sb.make_summoner()
    c.max_magicka = c.magicka = 9999
    battle = {"allies": []}
    sids = ["conjure_dremora", "conjure_healer", "conjure_flame_atronach", "conjure_frost_atronach"]
    for i in range(10):
        magic.cast(c, gd, sids[i % 4], RNG(i), battle=battle)
    n = magic.nonundead_summon_count(battle)
    print(f"\n== ② 名額規則探針:連施 10 道召喚 → 場上非亡者召喚物 {n} 隻(規則上限 {formulas.SUMMON_FIELD_CAP}) ==", flush=True)
    if n > formulas.SUMMON_FIELD_CAP:
        flag(f"名額規則失效:場上 {n} 隻 > SUMMON_FIELD_CAP={formulas.SUMMON_FIELD_CAP}")


# ── ③ 各選項 vs 全不選 ─────────────────────────────────────────────────────────
def conj_options():
    opts = [(n["id"], o["opt_id"]) for n in gd.mastery if n.get("skill") == "conjuration" and n["id"] in NODES
            for o in n["options"]]
    print(f"\n== ③ conjuration 選項 vs 全不選(n={max(60, N * 4 // 5)}/格)  格式 Δ勝率pp(對 {' / '.join(b[:8] for b in EFFECT_BOSSES)}) ==", flush=True)
    n_eff = max(60, N * 4 // 5)
    for label, mk, act in (("S 召喚師·激進", sb.make_summoner, act_aggressive), ("N base 死靈師", sb.make_necromancer, act_necro)):
        base = [rate(variant(mk), act, b, n=n_eff)[0] for b in EFFECT_BOSSES]
        print(f"{label:14} 不選 基準勝率: " + " / ".join(f"{x:4.0f}%" for x in base), flush=True)
        for node, opt in opts:
            vals = [rate(variant(mk, node, opt), act, b, n=n_eff)[0] for b in EFFECT_BOSSES]
            deltas = [v - b for v, b in zip(vals, base)]
            print(f"   {node[-3:]} {opt:16} " + " / ".join(f"{d:+5.1f}" for d in deltas), flush=True)
            for b, d in zip(EFFECT_BOSSES, deltas):
                if d < -WORSE_FLAG_PP:
                    flag(f"{label} 選 {opt} 比不選差 {d:+.0f}pp(對 {b})—— 輸給不選")
                elif d > OVERPOWER_FLAG_PP:
                    flag(f"{label} 選 {opt} 強 {d:+.0f}pp(對 {b})—— 強度過頭")


# ── ④ 群戰(R203c 瞬發契印 / R203d 就地起屍的主場:單場 BOSS 戰看不到「第一具屍體」與「召喚物陣亡回補」)────────────────
# 敵群含「同類也會掉到 100% 以下」的難組合(6×魔人 / 4×魔靈 / 3魔人+3風暴亞)—— 否則同類全 100%,「是否超過同類」成了空判斷。
PACKS = (("4×魔人", ("dremora",) * 4), ("5×魔人", ("dremora",) * 5), ("4×巨魔", ("bog_troll",) * 4),
         ("3魔人+2風暴亞", ("dremora",) * 3 + ("storm_atronach",) * 2), ("6×魔人", ("dremora",) * 6),
         ("4×魔靈", ("daedroth",) * 4), ("3魔人+3風暴亞", ("dremora",) * 3 + ("storm_atronach",) * 3),
         ("5×屍鬼(可起屍)", ("draugr",) * 5))
# 同類參照 = sim_builds 的完整構築(其標準策略);守衛口徑 = 召喚師(含選項)勝率 vs 同敵群「最強同類」的絕對值,不再看「同構築選項 vs 不選」的內比 Δ
# (R203 評估:起手慢的激進策略不選時墊底,Δ 天然 +60,但裝上後仍低於戰士 1H / 弓手 / 刺客 —— 內比 Δ 會誤報)。
PEERS = ("warrior_1H", "warrior_2H", "archer", "assassin", "shield_reflect")
PEER_MARGIN_PP = 5.0      # 召喚師(含選項)勝率 > 同敵群最強同類 + 5pp = 強度過頭


def solo_pack(name, ids, seed, max_rounds=80):
    """同類構築單挑敵群(鏡像 sim_builds.fight:標準策略 + 戰中用藥;敵人全體攻擊玩家;無召喚物)。回 'win' / 'dead' / 'timeout'。"""
    c = sb.BUILDS[name]()
    if name in sb._MELEE_POT_BUILDS:
        inventory.add_item(c, "healing_potion", sb._COMBAT_POTIONS)
    foes = [combat.spawn_creature(gd, e, RNG(seed * 13 + i + 1)) for i, e in enumerate(ids)]
    rng = RNG(seed)
    act = sb._POLICY[name]
    st = {"opening": True, "vanish": 0, "aimed": name == "archer", "skip_boss": False, "use_stance": name in sb._STANCE_BUILDS}
    for _ in range(max_rounds):
        alive = [e for e in foes if combat.is_alive(e)]
        if not alive:
            return "win"
        if c.health <= 0:
            return "dead"
        st["skip_boss"] = False
        st["enemies"] = alive
        tgt = min(alive, key=lambda e: e.health)
        if not magic.is_incapacitated(c):
            act(c, tgt, rng, st)
        if not [e for e in foes if combat.is_alive(e)]:
            return "win"
        if not st["skip_boss"] and c.health > 0:
            for e in [e for e in foes if combat.is_alive(e)]:
                if magic.is_incapacitated(e):
                    continue
                atk = combat.choose_enemy_attack(e, rng, c)
                ev = combat.resolve_attack(e, c, gd, rng, attack=atk)
                combat.misdirect_redirect(c, e, foes, gd, rng, ev, atk)
        sb._regen(c)
        magic.tick_effects(c, gd)
        for e in foes:
            if combat.is_alive(e):
                magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    return "win" if not [e for e in foes if combat.is_alive(e)] else "timeout"


def fight_pack(maker, act, enemy_ids, seed, max_rounds=60):
    """玩家 + 召喚物 vs 一群非首領敵人(鏡像 main.run_battle:玩家階段〔含瞬發契印〕→ 盟友 → 敵人 → 回合末就地起屍 → 召喚物計時 + 契印回補)。
    回 (結果, 回合數, 玩家剩血比例)。就地起屍 / 瞬發契印共用 main 的同一批函式(necromancy.auto_raise / combat.quick_seal_*)。"""
    c = maker()
    enemies = [combat.spawn_creature(gd, eid, RNG(seed * 13 + i + 1)) for i, eid in enumerate(enemy_ids)]
    rng = RNG(seed)
    battle = {"allies": []}
    st = {"buffed": False}
    rounds = 0

    def alive_en():
        return [e for e in enemies if combat.is_alive(e)]

    for _ in range(max_rounds):
        if not alive_en():
            return "win", rounds, max(0.0, c.health / c.max_health)
        if c.health <= 0:
            return "dead", rounds, 0.0
        rounds += 1
        if not magic.is_incapacitated(c):
            player_phase(c, alive_en()[0], rng, battle, st, act)
        if not alive_en():
            return "win", rounds, max(0.0, c.health / c.max_health)
        for a in sp._living_allies(battle):
            if not alive_en():
                break
            if magic.is_incapacitated(a):
                continue
            if magic.summon_support_act(a, c, sp._living_allies(battle), gd) is not None:
                continue
            tgt = party.ally_target(c, a, alive_en(), gd, rng)   # R205 單一決策點
            a_atk = combat.choose_attack(a, rng, tgt)
            if a_atk.get("taunt"):
                a.active_effects.append({"kind": "taunt", "turns": a_atk.get("turns", 3)})
                continue
            combat.resolve_attack(a, tgt, gd, rng, attack=a_atk)
        for e in alive_en():
            if c.health <= 0:
                break
            if magic.is_incapacitated(e):
                continue
            tgt = combat.pick_player_side_target(c, battle["allies"], rng)
            combat.resolve_attack(e, tgt, gd, rng, attack=combat.choose_enemy_attack(e, rng, tgt))
        necromancy.auto_raise(c, gd, rng, battle, enemies)             # R203d:回合末、召喚物計時之前(未選 → 零 rng 略過)
        battle["allies"], _gone = combat.tick_summons(battle["allies"])
        combat.quick_seal_recharge(c, gd, _gone)                       # R203c
        sb._regen(c)
        magic.tick_effects(c, gd)
        for a in battle["allies"]:
            if combat.is_alive(a):
                magic.tick_effects(a, gd)
        for e in enemies:
            if combat.is_alive(e):
                magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    return ("win" if not alive_en() else "timeout"), rounds, max(0.0, c.health / c.max_health)


def pack():
    n_eff = max(60, N * 4 // 5)
    print(f"\n== ④ 群戰:召喚師(各 75 / 100 選項 vs 不選)對照同類最強者(n={n_eff}/格;勝率%;Δ = 對『不選』)  ==", flush=True)
    print(f"   守衛口徑:裝上選項後的召喚師勝率 > 同敵群最強同類 + {PEER_MARGIN_PP:.0f}pp = ⚠ 強度過頭(內比 Δ 只列參考);選項比不選差 > {WORSE_FLAG_PP:.0f}pp = ⚠", flush=True)
    rows = (("不選", None, None), ("75 瞬發契印", "conjuration_75", "conj_efficiency"),
            ("75 就地起屍", "conjuration_75", "soul_harvest"), ("100 亡者統御", "conjuration_100", "undead_dominion"))
    builds = (("S 激進", sb.make_summoner, act_aggressive), ("S 保守", sb.make_summoner, act_conservative), ("N base", sb.make_necromancer, act_necro))
    for plabel, ids in PACKS:
        peers = {pn: sum(solo_pack(pn, ids, sd) == "win" for sd in range(n_eff)) * 100.0 / n_eff for pn in PEERS if pn in sb.BUILDS}
        best_name, best = max(peers.items(), key=lambda kv: kv[1])
        print(f"{plabel:14} 最強同類 {best_name} {best:3.0f}%  (" + " ".join(f"{k}{v:.0f}" for k, v in peers.items()) + ")", flush=True)
        for label, mk, act in builds:
            cells, base_win = [], None
            for name, node, opt in rows:
                res = [fight_pack(variant(mk, node, opt), act, ids, sd) for sd in range(n_eff)]
                win = sum(r[0] == "win" for r in res) * 100.0 / n_eff
                if base_win is None:
                    base_win = win
                    cells.append(f"{name} {win:3.0f}%")
                    continue
                d = win - base_win
                cells.append(f"{name} {win:3.0f}%(Δ{d:+.0f})")
                if d < -WORSE_FLAG_PP:
                    flag(f"{label} 群戰({plabel})選 {name} 比不選差 {d:+.0f}pp —— 輸給不選")
                if win > best + PEER_MARGIN_PP and d > 0:
                    flag(f"{label} 群戰({plabel})選 {name} 勝率 {win:.0f}% 超過最強同類 {best_name} {best:.0f}% +{PEER_MARGIN_PP:.0f}pp —— 強度過頭")
            print(f"   {label:7}| " + " | ".join(cells), flush=True)


# ── ⑤ 束縛兵刃(R204):握法規則探針 + 束縛騎士打達貢牆 ────────────────────────────────────────────
BOUND_WALL_FLAG_PCT = 8.0     # 束縛騎士(獸人底盤)打達貢 > 8% = 牆破了(R204 前:重盾 + 束縛巨劍 + 姿態 30~32%,同底盤他形 0%)


def bound_guard():
    print("\n== ⑤ 束縛兵刃:握法規則探針 + 束縛騎士打達貢牆 ==", flush=True)
    c = sb.BUILDS["bound_knight_1h"]()                       # 持單手盾
    c.spells = list(c.spells) + ["bound_greatsword", "bound_axe", "bound_mace"]
    shield_ok = {sid: magic.bound_conflict(c, gd, sid) is None for sid in ("bound_sword", "bound_mace", "bound_greatsword", "bound_axe")}
    if not (shield_ok["bound_sword"] and shield_ok["bound_mace"] and not shield_ok["bound_greatsword"] and not shield_ok["bound_axe"]):
        flag(f"握法規則失效:持單手盾時 單手形 / 雙手形 可凝 = {shield_ok}(應為 劍·釘錘 可、巨劍·戰斧 不可)")
    g = sb.BUILDS["bound_knight"]()
    inventory.add_item(g, "daedric_great_shield", 1)
    inventory.equip_armor(g, gd, "daedric_great_shield")
    g.spells = list(g.spells) + ["bound_sword", "bound_mace", "bound_axe"]
    great_ok = [sid for sid in ("bound_sword", "bound_mace", "bound_greatsword", "bound_axe") if magic.bound_conflict(g, gd, sid) is None]
    if great_ok:
        flag(f"握法規則失效:持雙手重盾時仍凝得出束縛兵刃 {great_ok}(重盾 + 束縛巨劍 + 姿態曾打穿達貢牆)")
    print(f"   握法探針:單手盾下可凝 {[k for k, v in shield_ok.items() if v]};雙手重盾下可凝 {great_ok or '無'}", flush=True)
    n_eff = max(40, N * 4 // 5)
    # 規則禁止的組合(重盾 + 束縛巨劍 + 姿態):cast 應被拒 → 永不凝刃 → 應 ≈ 0%;握法**沒被強制執行**時它是 ~12%(獸人底盤)>> 門檻
    # (R204 審查:只測謂詞 / 合法夾具的探針對「強制失效」空轉,故真的模擬這個違規組合)
    def _gs_probe():
        c = sb.BUILDS["bound_knight_1h"]()                   # 格擋 100 + 完美格擋 + 姿態底盤(重盾「掩體」優勢才發揮;原 R204 前打穿牆的組合)
        c.equipped.pop("shield", None)
        c.spells = ["bound_greatsword"] + [x for x in c.spells if x != "bound_sword"]
        inventory.add_item(c, "daedric_great_shield", 1)
        inventory.equip_armor(c, gd, "daedric_great_shield")
        return sb._apply_realistic("bound_knight_1h", c)
    sb.BUILDS["_bound_gs_probe"] = _gs_probe
    sb._POLICY["_bound_gs_probe"] = sb._bound_knight_act
    sb._STANCE_BUILDS.add("_bound_gs_probe")
    sb._MELEE_POT_BUILDS.add("_bound_gs_probe")
    try:
        for nm in ("bound_knight", "bound_knight_1h", "_bound_gs_probe"):
            w = sum(sb.fight(nm, WALL_BOSS, sd) == "win" for sd in range(n_eff)) * 100.0 / n_eff
            label = "重盾+巨劍+姿態(違規組合)" if nm == "_bound_gs_probe" else nm
            print(f"   {label:22} 打達貢 {w:5.1f}%(n={n_eff})", flush=True)
            if w > BOUND_WALL_FLAG_PCT:
                flag(f"{label} 打達貢勝率 {w:.0f}% > {BOUND_WALL_FLAG_PCT:.0f}% —— 牆破了:檢查束縛兵刃握法規則是否被強制執行 / 反擊抗性分類")
    finally:
        for reg in (sb.BUILDS, sb._POLICY):
            reg.pop("_bound_gs_probe", None)
        sb._STANCE_BUILDS.discard("_bound_gs_probe")
        sb._MELEE_POT_BUILDS.discard("_bound_gs_probe")


if __name__ == "__main__":
    wall()
    probe()
    conj_options()
    pack()
    bound_guard()
    print("\n⚠ 已知保真度邊界:政策是「合理」非「完美」;單場 + 預召喚不等於整趟地城(token 淨額、帶進 BOSS 格的軍團規模需 sim_dungeon 整趟模式)。", flush=True)
    print("✓ sim_conj 無警示" if not flags else f"⚠ sim_conj 共 {len(flags)} 項守衛警示(見上;print-only,務必人眼覆核)", flush=True)
