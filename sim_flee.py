"""R195 運動 50「健步如飛」脫身加成守衛(非測試;手動跑:PYTHONPATH=. python3 sim_flee.py [n=150];約 1 分鐘)

為什麼另寫:sim_assassin / sim_builds / sim_dungeon 的玩家政策**從不逃跑**(R147 記載「flee 不在 sim 路徑」),脫身加成
(`mastery.escape_bonus` → `combat.flee_probability`)在既有 sim 完全無數據。R147 當年正因「75 escape_artist 軟 no-brainer」
移除舊逃跑加成,而當時從未量過 —— 本守衛補上這個盲區:沿用 sim_dungeon 的整趟地城框架(真實怪物池/生成/boss、生命體力
跨場攜帶),加入「最後一搏」逃跑政策,量「健步如飛 vs 節氣」對 死亡 / 逃走 / 通關 的影響。

政策:玩家回合開頭 HP 比 < FLEE_HP(15%)→ 嘗試逃跑(機率 = 真實 `combat.flee_probability`,含里程碑加成;成功 = 整趟
結束且存活〔現行規則:逃出地城丟整張圖〕,失敗 = 吃掉這一回合)。逃跑用獨立亂數流(嘗試次數不擾動戰鬥主流 → 各變體同種子
配對)。變體(均走真實 mastery.choose,運動 100):base(只有 25 勻息)/ esc(+50 健步如飛)/ sw(+50 節氣)。
fight2 鏡像 sim_dungeon.fight 的回合結構(改該函式時須同步)。

校準(R195·n=300·HP<15%·運動 100;danger 6 匯聚聖所,施法系/聖騎士另看 danger 4 灰燼塚):
  脫身死亡Δ:單手 −5.0、雙手 −6.0、盾反 −6.7、聖騎士 −8.3、戰法師 −9.3、法師 −10.7/−10.0、秘術師 −11.0(±2.5~3.5);
            武僧 −0.3、刺客 0、弓手 0(**戰中逃跑**率已貼 0.91~0.95 → 加成被緩肩/夾限吞掉 = 依原型分流)。
  ⚠ 本守衛只量戰中逃跑:潛行撤退(offer_battle)不在 sim 路徑。撤退端低潛行者(含武僧,speed 80/sneak 10 對 2 敵 0.65→0.80)
    仍全額 +15pp,潛行 100 的刺客/弓手貼 0.92 無感(R195 審查實測;守衛 2「夾限失效」因此只約束逃跑端)。
  節氣死亡Δ與通關Δ:全部落在雜訊內(|Δ| ≤ 5±5)。運動 50、HP<10% 兩組敏感度同樣態。
守衛(⚠;非自動閘門,改脫身加成/逃跑公式/節氣後人工看):
  1. 強度過頭:任一原型脫身讓死亡下降 > 18pp(校準最大 ≈ −11;n=150 單格 95% 半寬約 ±5pp,太貼門檻會誤報)。
  2. 夾限失效:快手(武僧/刺客/弓手)脫身死亡Δ 絕對值 > 3pp(校準 ≈ 0;非 0 = 緩肩/夾限/公式變了)。
  3. 沒效果:慢手原型(單手/雙手/盾反/聖騎士/戰法師/法師/秘術師)中,脫身死亡Δ > −2pp 者過半 → 選項成死選項。
  4. 反向 no-brainer:任一慢手原型 節氣死亡Δ 比脫身低 8pp 以上(節氣壓過脫身 → 脫身成死選項)。
"""
import math
import statistics as S
import sys
from multiprocessing import Pool

import sim_builds as SB
import sim_dungeon as SD
from tesrpg import formulas
from tesrpg.rng import RNG
from tesrpg.systems import combat, dungeoncrawl, magic, mastery, stats

gd = SD.gd
FLEE_HP = 0.15
HARD = SD.HARD                    # convergence_sanctum:danger 6(近戰會見底的終局地城)
MID = "ashfall_barrow"            # danger 4:施法系/聖騎士也走得進去的中階地城
SLOW = ["warrior_1H", "warrior_2H", "shield_reflect", "paladin", "battlemage", "mage_shock", "mage_fire", "arcanist"]
FAST = ["monk", "assassin", "archer"]
MID_BUILDS = ["paladin", "battlemage", "mage_shock", "mage_fire", "arcanist"]
FLAG_STRONG, FLAG_CAPPED, FLAG_DEAD_OPT, FLAG_INVERSE = 18.0, 3.0, 2.0, 8.0

SD.LINES["flee_base"] = {"athletics_25": "steady_breath"}
SD.LINES["flee_esc"] = {"athletics_25": "steady_breath", "athletics_50": "marathon"}       # 健步如飛
SD.LINES["flee_sw"] = {"athletics_25": "steady_breath", "athletics_50": "second_wind"}    # 節氣
VAR = {"base": "flee_base", "esc": "flee_esc", "sw": "flee_sw"}
for _v in VAR.values():
    SD.VARIANTS[_v] = (_v, None, None)


class Fled(Exception):
    pass


def fight2(c, build, foes_in, seed, max_rounds=80):
    """鏡像 sim_dungeon.fight,於玩家回合開頭插入最後一搏逃跑(機率 = 真實 combat.flee_probability)。"""
    prim = [(t if not isinstance(t, str) else combat.spawn_creature(gd, t, RNG(seed * 9 + 1 + i)))
            for i, t in enumerate(foes_in)]
    foes = list(prim)
    rng = RNG(seed)
    frng = RNG(seed * 77 + 5)                    # 獨立亂數流:逃跑嘗試次數不擾動戰鬥主流
    act = SB._POLICY[build]
    st = {"opening": True, "vanish": 0, "aimed": build == "archer", "skip_boss": False,
          "use_stance": build in SB._STANCE_BUILDS}
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
            combat.second_breath_use(c, gd)              # 與 main.run_battle 同:每回合選單前先判一氣呵成(未選 → 0·零 rng)
            if c.health < FLEE_HP * c.max_health:
                foe = max(alive, key=lambda e: e.speed)                  # 同 main.run_battle 的逃跑對象
                if frng.chance(combat.flee_probability(c, foe, gd)):
                    raise Fled()
                # 逃跑失敗:吃掉這一回合(不行動)
            else:
                if SD.REST_THETA and c.fatigue < SD.REST_THETA * c.max_fatigue:
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


def one_run(build, dkey, variant, seed):
    """回 'clear' / 'dead' / 'fled' / 'timeout'。"""
    spec = SD.SPECS[dkey]
    grid = dungeoncrawl.generate(spec, gd, RNG(seed * 7 + 3))
    mobs = [cell["enemies"] for layer in grid["layers"] for row in layer for cell in row
            if cell["type"] == dungeoncrawl.MONSTER]
    c = SD.make(build, variant)
    try:
        for i, ids in enumerate(mobs):
            r = fight2(c, build, ids, seed * 1009 + i)
            if r != "win" or c.health <= 0:
                return "dead" if (r == "dead" or c.health <= 0) else "timeout"
        r = fight2(c, build, [SD.spawn_boss(spec, RNG(seed * 13 + 5))], seed * 1009 + 999, max_rounds=120)
        if r == "win":
            return "clear"
        return "dead" if (r == "dead" or c.health <= 0) else "timeout"
    except Fled:
        return "fled"


N = int(sys.argv[1]) if len(sys.argv) > 1 else 150


def cell_task(task):
    build, dkey, vname = task
    return (build, dkey, vname, [one_run(build, dkey, VAR[vname], s) for s in range(N)])


def pdiff(res, build, dkey, a, b, status):
    xs = [(1 if x == status else 0) - (1 if y == status else 0) for x, y in zip(res[(build, dkey, a)], res[(build, dkey, b)])]
    m = S.mean(xs)
    se = S.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0
    return m * 100, 1.96 * se * 100


def rate(res, build, dkey, v, status):
    return S.mean(1 if r == status else 0 for r in res[(build, dkey, v)]) * 100


def guard():
    cells = [(b, HARD) for b in SLOW + FAST] + [(b, MID) for b in MID_BUILDS]
    tasks = [(b, d, v) for b, d in cells for v in VAR]
    res = {}
    with Pool(6) as pool:
        for b, d, v, out in pool.imap_unordered(cell_task, tasks):
            res[(b, d, v)] = out
    print(f"== 脫身加成守衛(HP<{FLEE_HP:.0%} 最後一搏·運動 100·n={N};Δ = 對同種子 base 的配對差 pp ±95% 半寬) ==")
    print(f"{'構築@副本':26}{'基準死/逃%':>12}{'脫身 死亡Δ':>16}{'節氣 死亡Δ':>16}{'節氣 通關Δ':>16}")
    stat = {}
    for b, d in cells:
        ed, eh = pdiff(res, b, d, "esc", "base", "dead")
        sd, sh = pdiff(res, b, d, "sw", "base", "dead")
        sc, sch = pdiff(res, b, d, "sw", "base", "clear")
        stat[(b, d)] = (ed, sd)
        print(f"{b + '@' + d[:6]:26}{rate(res, b, d, 'base', 'dead'):>6.0f}/{rate(res, b, d, 'base', 'fled'):<5.0f}"
              f"{ed:>+9.1f}±{eh:<5.1f}{sd:>+9.1f}±{sh:<5.1f}{sc:>+9.1f}±{sch:<5.1f}")
    flags = []
    for b, d in cells:
        ed, sd = stat[(b, d)]
        if ed < -FLAG_STRONG:
            flags.append(f"⚠強度過頭 {b}@{d} 脫身死亡Δ {ed:+.1f}pp")
        if b in FAST and abs(ed) > FLAG_CAPPED:
            flags.append(f"⚠夾限失效 {b}@{d} 快手脫身死亡Δ {ed:+.1f}pp(應≈0)")
        if b in SLOW and d == HARD and sd < ed - FLAG_INVERSE:
            flags.append(f"⚠反向 no-brainer {b}@{d} 節氣 {sd:+.1f} 比脫身 {ed:+.1f} 低 ≥{FLAG_INVERSE:.0f}pp")
    dead_opt = [b for b in SLOW if stat[(b, HARD)][0] > -FLAG_DEAD_OPT]
    if len(dead_opt) > len(SLOW) / 2:
        flags.append(f"⚠沒效果 慢手原型 {len(dead_opt)}/{len(SLOW)} 脫身死亡Δ > −{FLAG_DEAD_OPT:.0f}pp:{','.join(dead_opt)}")
    if flags:                                    # 只有真的有警示才印「⚠ 守衛警示」(check.sh 以此行 grep)
        print("\n⚠ 守衛警示:\n  " + "\n  ".join(flags))
    else:
        print("\n✓ 脫身守衛全過(無強度過頭/夾限失效/沒效果/反向 no-brainer)")
    return res


if __name__ == "__main__":
    guard()
