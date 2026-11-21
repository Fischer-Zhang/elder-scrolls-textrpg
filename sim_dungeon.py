"""R194 運動 100 守衛(非測試;手動跑:PYTHONPATH=. python3 sim_dungeon.py [n地城=80] [n牆=100];約 30 秒)

為什麼另寫:sim_assassin / sim_builds / sim_monk 全是「單場」戰鬥,而體力是**跨戰鬥**的資源(無被動回體、地城內不能休息、
離開地城丟整張圖進度)→ 單場 sim 完全看不到體力壓力(R194 評估前曾誤判「體力沒壓力」)。本守衛模擬**整趟地城**:
用真實 dungeons.json 的怪物池與 boss,dungeoncrawl.generate 生成格子,依序打完所有怪格(全清)再打 boss,
生命/體力跨戰鬥攜帶(真實規則),量「抵達 boss % / 通關 % / 抵達時體力 %」,並守終王牆 1v1(達貢真身/達貢)。

構築:sim_builds 的 warrior_1H / monk / assassin(近戰前排與對照;法師的瓶頸是法力/生命、體力不構成限制 → 不入守衛)。運動技能 100。
變體(同一節點 athletics_100 的兩個選項互斥,各自對「同線無 100 階」比):
  open_no100 = 勻息+健步如飛〔marathon;R195 前稱長途健步,逃跑不在本 sim 路徑 → 對結果無影響〕+深息;wind = open_no100 + 二次呼吸(一氣呵成:行動時體力 ≤ 25% → 免耗回合回一次調息量·一場一次)
  slow_no100 = 勻息+節氣+省勁;     kill = slow_no100 + 無盡之軀(殺勢回體:親手擊殺回 3% 最大體力·爪牙不算)
政策:玩家每次行動前呼叫 combat.second_breath_use(與 main.run_battle 共用同一個閘);體力占比 < REST_THETA(15%)時花一回合調息(所有變體一致);
每場戰鬥開頭剝除 second_breath_spent(鏡像 main 入戰處理:地城怪格 preserve_buffs=True,姿態等常駐效果跨場保留)。終王牆 1v1 從體力 0 起手(整趟地城後的最壞情況)。
種子:每格 seed=0..n-1;地城生成 RNG(seed*7+3)、戰鬥 RNG(seed*1009+場次)、怪 RNG(seed*9+1+i)(各變體同種子 → 成對比較)。
守衛(⚠;非自動閘門,改一氣呵成/殺勢回體參數或體力公式後人工看):
  1. 強度過頭:終局地城(匯聚聖所·danger 6)抵達 boss 增益 > +45pp 或通關增益 > +30pp
     (校準 n=300·匯聚聖所·單手劍,抵達/通關增益:殺勢回體 2% +22/+4〔會調息 +15/+1〕、3% +30/+9〔+21/+1〕、5% +38/+18〔+38/+6〕;
      一氣呵成 歸零 +26/+7〔會調息 +0/+0〕、<15% +35/+7〔+23/+2〕、<25% +37/+12〔+28/+4〕;n=80 的雜訊曾高估 1.5–3 倍)
  2. 輸給同線無 100 階:抵達或通關增益 < −15pp(n 小的雜訊約 ±14pp,只抓明顯退化)
  3. 破牆線:達貢真身/達貢 1v1 勝率增益 > +8pp(兩機制結構上不動終王牆:一氣呵成一場一次、殺勢回體 solo 戰只有最後一刀)
  4. 低難度回歸(危險度 5·波伊提亞試煉):通關率不得低於同線無 100 階 −5pp
"""
import json
import statistics as S
import sys
from multiprocessing import Pool

import sim_builds as SB
from tesrpg import formulas
from tesrpg.rng import RNG
from tesrpg.systems import combat, dungeoncrawl, inventory, magic, mastery, stats

gd = SB.gd
SPECS = json.load(open("tesrpg/data/dungeons.json", encoding="utf-8"))

LINES = {
    "open_no100": {"athletics_25": "steady_breath", "athletics_50": "marathon", "athletics_75": "deep_breath"},
    "slow_no100": {"athletics_25": "steady_breath", "athletics_50": "second_wind", "athletics_75": "sparing"},
}
VARIANTS = {   # 名稱 → (路線, 100 階選項|None, 對照的同線無 100 階變體|None)
    "open_no100": ("open_no100", None, None),
    "wind": ("open_no100", "tidal_breath", "open_no100"),
    "slow_no100": ("slow_no100", None, None),
    "kill": ("slow_no100", "frugal", "slow_no100"),
}
BUILDS = ["warrior_1H", "monk", "assassin"]
REST_THETA = 0.15                 # 玩家政策:戰中體力占比 < 15% 就花一回合「調息」(所有變體一致;0 = 從不調息)。
                                   # R194 審查:原版無調息 → 勻息/深息零效果、wind 與「完全不回氣」比而高估;現與合理玩家比。
HARD = "convergence_sanctum"      # danger 6:體力才看得出差別的終局地城
EASY = "boethiah_proving"         # danger 5:回歸守衛(任何變體都不該讓通關率變差)
WALLS = [("達貢真身", "mehrunes_dagon_true"), ("達貢", "mehrunes_dagon")]
FLAG_REACH_STRONG, FLAG_CLEAR_STRONG, FLAG_LOSE, FLAG_WALL, FLAG_EASY = 45.0, 30.0, 15.0, 8.0, 5.0


def make(build, variant):
    line, h100, _ref = VARIANTS[variant]
    c = SB.BUILDS[build]()
    c.skills["athletics"] = 100
    for node, opt in LINES[line].items():
        mastery.choose(c, gd, node, opt)
    if h100:
        mastery.choose(c, gd, "athletics_100", h100)
    if build in SB._MELEE_POT_BUILDS:
        inventory.add_item(c, "healing_potion", SB._COMBAT_POTIONS)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.fatigue = c.max_fatigue
    return c


def fight(c, build, foes_in, seed, max_rounds=80):
    """沿用 sim_builds.fight 的回合結構,但角色外部傳入(整趟地城連戰)。foes_in:怪物 id 或已生成的生物。回 結果字串。"""
    prim = [(t if not isinstance(t, str) else combat.spawn_creature(gd, t, RNG(seed * 9 + 1 + i)))
            for i, t in enumerate(foes_in)]
    foes = list(prim)
    rng = RNG(seed)
    act = SB._POLICY[build]
    st = {"opening": True, "vanish": 0, "aimed": build == "archer", "skip_boss": False,
          "use_stance": build in SB._STANCE_BUILDS}
    # 鏡像 main 入戰處理:地城怪格走 run_battle(preserve_buffs=True)→ 只剝戰內累積記帳(含一氣呵成已用標記),
    # 格擋姿態等常駐效果跨場保留(真實規則;審查曾誤以為 main 每場全清)。
    c.active_effects[:] = [e for e in c.active_effects if e.get("kind") != "second_breath_spent"]
    for _ in range(max_rounds):
        if not any(combat.is_alive(p) for p in prim):
            return "win"
        if c.health <= 0:
            return "dead"
        st["skip_boss"] = False
        alive = [e for e in foes if combat.is_alive(e)]
        st["enemies"] = alive
        tgt = min(alive, key=lambda e: e.health)
        if not magic.is_incapacitated(c):
            combat.second_breath_use(c, gd)          # R194 一氣呵成(與 main 共用閘;未選 → 0·零 rng)
            if REST_THETA and c.fatigue < REST_THETA * c.max_fatigue:
                # 調息(耗一回合·自動解除姿態;與 main.run_battle 的 rest 動作同式)
                c.active_effects[:] = [e for e in c.active_effects if e.get("kind") not in ("guard_stance", "shield_wall")]
                c.fatigue = min(c.max_fatigue, c.fatigue + formulas.rest_fatigue_amount(c.skill("athletics"))
                                + mastery.rest_bonus(c, gd))
            else:
                act(c, tgt, rng, st)
        if not any(combat.is_alive(p) for p in prim):
            return "win"
        for e in prim:
            if combat.is_alive(e) and c.health > 0 and not magic.is_incapacitated(e) and not st["skip_boss"]:
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
    return "win" if not any(combat.is_alive(p) for p in prim) else "timeout"


def spawn_boss(spec, rng):
    b = spec["boss"]
    return combat.spawn_creature(gd, b["enemy"], rng) if b.get("raw") else combat.spawn_boss(gd, b["enemy"], rng)


def one_run(build, dkey, variant, seed):
    spec = SPECS[dkey]
    grid = dungeoncrawl.generate(spec, gd, RNG(seed * 7 + 3))
    mobs = [cell["enemies"] for layer in grid["layers"] for row in layer for cell in row
            if cell["type"] == dungeoncrawl.MONSTER]
    c = make(build, variant)
    maxf = c.max_fatigue
    for i, ids in enumerate(mobs):
        if fight(c, build, ids, seed * 1009 + i) != "win" or c.health <= 0:
            return (False, False, None)
    arrive = c.fatigue / maxf
    won = fight(c, build, [spawn_boss(spec, RNG(seed * 13 + 5))], seed * 1009 + 999, max_rounds=120) == "win"
    return (True, won, arrive)


def dungeon_cell(task):
    build, dkey, variant, n = task
    rs = [one_run(build, dkey, variant, s) for s in range(n)]
    reached = [r for r in rs if r[0]]
    return (build, dkey, variant, len(reached) / n * 100, sum(1 for r in reached if r[1]) / n * 100,
            (S.mean(r[2] for r in reached) * 100) if reached else float("nan"))


def wall_cell(task):
    build, variant, boss, n = task
    wins = 0
    for s in range(n):
        c = make(build, variant)
        c.fatigue = 0              # 終王牆從「整趟地城後體力見底」起手(最壞情況·一氣呵成立即觸發;原滿體力起手測不到)
        wins += fight(c, build, [boss], s, max_rounds=150) == "win"
    return (build, variant, boss, wins / n * 100)


def guard(n_dungeon=80, n_wall=100):
    dtasks = [(b, d, v, n_dungeon if d == HARD else max(12, n_dungeon // 3))
              for b in BUILDS for d in (HARD, EASY) for v in VARIANTS]
    wtasks = [(b, v, boss, n_wall) for b in BUILDS for v in VARIANTS for _lbl, boss in WALLS]
    with Pool(4) as pool:
        dres = {(r[0], r[1], r[2]): r for r in pool.map(dungeon_cell, dtasks)}
        wres = {(r[0], r[1], r[2]): r[3] for r in pool.map(wall_cell, wtasks)}
    flags = []
    names = list(VARIANTS)
    for b in BUILDS:
        for d in (HARD, EASY):
            sp = SPECS[d]
            print(f"\n== {b} @ {d}(danger{sp['danger']} boss={sp['boss']['enemy']}·全清+boss·生命/體力跨場攜帶) ==")
            print(f"{'變體':12}{'抵達boss%':>10}{'通關%':>8}{'抵達時體力%':>12}")
            for v in names:
                _b, _d, _v, reach, clear, fat = dres[(b, d, v)]
                print(f"{v:12}{reach:10.0f}{clear:8.0f}{fat:12.0f}")
            for v in ("wind", "kill"):
                ref = VARIANTS[v][2]
                dr, dc = dres[(b, d, v)][3] - dres[(b, d, ref)][3], dres[(b, d, v)][4] - dres[(b, d, ref)][4]
                if d == HARD:
                    if dr > FLAG_REACH_STRONG or dc > FLAG_CLEAR_STRONG:
                        flags.append(f"⚠強度過頭 {v}@{b}/{d} 抵達{dr:+.0f}pp 通關{dc:+.0f}pp")
                    if dr < -FLAG_LOSE or dc < -FLAG_LOSE:
                        flags.append(f"⚠輸給同線無100階 {v}@{b}/{d} 抵達{dr:+.0f}pp 通關{dc:+.0f}pp")
                elif dc < -FLAG_EASY:
                    flags.append(f"⚠低難度回歸 {v}@{b}/{d} 通關{dc:+.0f}pp")
    print("\n== 終王牆 1v1 勝率%(各變體;增益 = 對同線無 100 階) ==")
    print(f"{'構築':12}{'變體':12}" + "".join(f"{lbl:>10}" for lbl, _ in WALLS))
    for b in BUILDS:
        for v in names:
            print(f"{b:12}{v:12}" + "".join(f"{wres[(b, v, boss)]:10.0f}" for _lbl, boss in WALLS))
        for v in ("wind", "kill"):
            ref = VARIANTS[v][2]
            for lbl, boss in WALLS:
                g = wres[(b, v, boss)] - wres[(b, ref, boss)]
                if g > FLAG_WALL:
                    flags.append(f"⚠破牆線 {v}@{b}/{lbl} {g:+.0f}pp")
    if flags:                                    # 只有真的有警示才印「⚠ 守衛警示」(check.sh 以此行 grep)
        print("\n⚠ 守衛警示:\n  " + "\n  ".join(flags))
    else:
        print("\n✓ 運動 100 守衛全過(無強度過頭/輸給同線無100階/破牆線/低難度回歸)")
    return dres, wres


if __name__ == "__main__":
    nd = int(sys.argv[1]) if len(sys.argv) > 1 else 80     # n 太小(<60)雜訊會讓「強度過頭」誤報(單格 95% 半寬 n=40 約 ±15pp)
    nw = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    guard(nd, nw)
