"""R227 前置量測(R226 收尾·非測試;手動跑:PYTHONPATH=. python3 sim_arrest.py [n_run=60] [n_fight=300] [dungeon_seeds=3];print-only·不接 check.sh·約 3~6 分鐘)

為什麼另寫:R226 的抓捕 / 封店 / 殺官決策,靠的是一批放在 session 暫存目錄的臨時腳本;日後要重現數字、或改了行竊 / 抓捕 / 封店參數後要重量,得有固定工具。
同時補完 R226 留下的兩個缺口:「行竊每點擊收入 vs 其他賺錢途徑」與「訓練收入減支出時間序列」(R222 / R224 待量測)。
三段全走真實函式(world.ensure_stock / crime.steal_chance / crime.steal_item / crime.guard_kill_penalty / dialogue / dungeoncrawl.generate /
loot.resolve_loot / world.train_cost / progression),唯一抽象是「點擊成本」(見 CLICK)與「衛兵戰勝負用同構築實測勝率表抽樣」。

1 抓捕情境(R226 現行規則;A1)——長時間「算點擊」模型:固定點擊預算 B,下手 / 等補貨 / 盤查 / 存倉 / 清賞金各算點擊;補貨與戒心重置走真實
  world.ensure_stock;策略參數(每次進店最多下手 k 次、手上贓物達多少才存倉庫)每格掃最佳。指標 = 預算內累積贓物底價 / 實際使用點擊(金/點擊)。
  制度:now = R226 之前(失手只加賞金)· A = 失手衛兵來抓、選入獄 · AL = 失手衛兵來抓、選拔劍反抗(只有頂級構築打得過;每打死一名 +40 拒捕 +700 殺官,
  賞金達封店線就得就地自首清掉)· L = 隱形者(衛兵撲空,只靠封店;就地自首清賞金)。R226 現行 = 該構築 A / AL 取較佳者。
  ⚠ 已知限制:點擊成本為估值(含「對小偷有利」敏感度);中階 / 新手夾具為自訂;賞金獵人攔路與逃跑沒建模;存倉假設該城有房(全遊戲 72 家店只有 16 座城能買房);
  每場衛兵戰後假設完整治療(時間免費)。
2 行竊 vs 其他途徑(A2)——每點擊收入並列:行竊(R226 現行 / 之前)、地城全清(用真實生成器取格數與戰利品、用真實戰鬥取回合數;點擊 = 移動 + 開箱 + 戰鬥回合,
  移動給樂觀 / 悲觀兩個估計)、配方轉賣上界。底價與「實得」(行竊贓物走銷贓 ×1.2~1.4、地城戰利品賣商店 ×0.38~0.80)並列。
4 金幣換實力 vs 親自玩(A3',使用者判準:同點擊預算下金幣路徑比親自玩更快 = 過度)——用真實戰鬥量親自玩的每點擊技能經驗,餵真實 progression;
  對照純賺錢買訓練、玩 + 賺錢買訓練;並算臨界收入。
3 訓練收入減支出(A3)——依危險度由低到高累積收入(金幣 + 戰利品實得)vs 純靠訓練能買到的角色等級 vs 自然等級;並列全部一次性去處的總價。

基準(R227 前置·2026-11-28·n=60):見 handoff §3 R226 續與 §6。
"""
import os
import statistics as S
import sys
from multiprocessing import Pool

import sim_assassin as SA
import sim_builds as SB
import sim_dungeon as SD
import sim_economy as E
from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.rng import RNG
from tesrpg.systems import combat, crime, dialogue, dungeoncrawl, inventory, loot, magic, stats, world

gd = E.gd
N_RUN = int(sys.argv[1]) if len(sys.argv) > 1 else 60
N_FIGHT = int(sys.argv[2]) if len(sys.argv) > 2 else 300
D_SEEDS = int(sys.argv[3]) if len(sys.argv) > 3 else 3
NPROC = min(18, os.cpu_count() or 4)
LOCS = ("whiterun", "bruma")
B = 400                                                   # 點擊預算
KS = (2, 3, 5, 8, 13, 40)                                 # 每次進店最多下手次數
DEP = (None, 0, 150, 400, 1000)                           # 存倉庫門檻(手上贓物底價 ≥ 此值才存;None = 不存)
CLICK = dict(steal=1, wait=2, confront=3, fight=5, deposit=3, clear_town=3)
CLICK_LENIENT = dict(steal=1, wait=1, confront=2, fight=3, deposit=2, clear_town=2)   # 敏感度:全部壓到對小偷最有利
STACK_ARGS = dict(E.MAXED, thieves=E.TOP_THIEF, fighters=E.TOP_FIGHTER, infamy=50, fame=700, blessing=True, pact=True)
THIEF = {"top": (100, 100, 60, True), "mid": (60, 50, 30, False), "novice": (25, 15, 15, False)}   # 潛行 / 安全 / 口才 / 疊滿折扣


class Clock:
    def __init__(self, h):
        self.h = h

    def absolute_hours(self):
        return self.h


# ---------------------------------------------------------------- 夾具
def make_mid_fighter():
    c = build_character(gd, name="中", sex="male", race="imperial", birthsign="shadow", class_id="thief")
    c.skills.update(sneak=60, blade=45, light_armor=45, security=50, acrobatics=25, speechcraft=30)
    c.attributes.update(agility=55, speed=50, endurance=45, strength=45)
    c.weapon = "steel_dagger"
    inventory.add_item(c, "steel_dagger", 1)
    SB._equip_set(c, "leather")
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def make_novice_fighter():
    c = build_character(gd, name="新", sex="male", race="imperial", birthsign="shadow", class_id="thief")
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


FIGHTERS = {"top": SB.BUILDS["assassin"], "mid": make_mid_fighter, "novice": make_novice_fighter}
GUARD_CFG = {"g1": ["city_guard"], "g2": ["city_guard"] * 2, "g3": ["city_guard"] * 3,
             "cap3": ["city_captain", "city_guard", "city_guard"]}


def thief_char(arch, loc, tier):
    sn, se, sp, stack = THIEF[arch]
    c = E.make_char(**(STACK_ARGS if stack else dict(mercantile=5, personality=40)))
    c.skills.update(sneak=sn, security=se, speechcraft=sp)
    c.location_id = loc
    if tier:
        c.shop_invest[loc] = tier
    return c


def guard_cfg_for(bounty):
    """與 main.guard_confrontation 的反抗分支同式:衛兵數 1 + min(2, 賞金 // 80);賞金 ≥ 獵殺 tier 3 → 一名換隊長。"""
    if bounty >= crime.ACTIVE_HEAT_THRESHOLDS[-1]:
        return "cap3"
    return f"g{1 + min(2, bounty // 80)}"


def guard_fight(arch, cfg, seed):
    c = FIGHTERS[arch]()
    foes = [combat.spawn_creature(gd, t, RNG(seed * 9 + i)) for i, t in enumerate(GUARD_CFG[cfg])]
    rng = RNG(seed)
    opening, used = False, [0]                           # 盤查不是伏擊
    for _ in range(80):
        if not any(combat.is_alive(e) for e in foes):
            return "win"
        if c.health <= 0:
            return "dead"
        opening = SA._round(c, foes, rng, opening, used, False)
        magic.tick_effects(c, gd)
        for e in foes:
            if combat.is_alive(e):
                magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    return "win" if not any(combat.is_alive(e) for e in foes) else "timeout"


def _fight_job(args):
    arch, cfg = args
    res = [guard_fight(arch, cfg, s) for s in range(N_FIGHT)]
    return (arch, cfg), res.count("win") / len(res)


WIN: dict = {}            # (構築, 衛兵配置) → 勝率(timeout 視為輸)


# ---------------------------------------------------------------- 1 長時間模型
def long_run(job):
    arch, loc, tier, seed, kind, k, dep, clicks_cfg = job
    c = thief_char(arch, loc, tier)
    prov = crime.province_of(c, gd)
    rng = RNG(seed)
    cat = world.merchant_catalog(gd, loc, tier)
    vals = {i: gd.item(i)["value"] for i in cat}
    p0 = {i: crime.steal_chance(c, gd, i) for i in cat}
    clock, clicks, pocket, stash, lost, dead, arrests, locks = 0, 0, 0, 0, 0, False, 0, 0
    conf_kind = kind in ("A", "AL", "L")
    lam = 1.0 if (conf_kind and dep is None) else (0.5 if conf_kind else 0.0)   # 失手會丟背包贓物的程度(影響挑貨;有存倉習慣者折半)

    def clear_bounty():
        nonlocal pocket, lost, clock
        b = crime.bounty(c, prov)
        lost += pocket
        pocket = 0
        crime.clear_bounty(c, prov)
        clock += max(6, int(b * crime.JAIL_DAYS_PER_BOUNTY * 24))

    while clicks < B and not dead:
        visit = 0
        while visit < k and clicks < B and not dead:
            world.ensure_stock(c, gd, loc, Clock(clock), rng)
            stock = c.shop_stock[loc]
            n = crime.theft_count(c, loc)
            best, bg = None, 0.0
            for i, q in stock.items():
                if q <= 0:
                    continue
                p = p0[i] * crime.SHOP_THEFT_DECAY ** n
                g = p * vals[i] - lam * (1 - p) * pocket
                if best is None or g > bg:
                    best, bg = i, g
            if best is None or bg <= 0:
                break
            r = crime.steal_item(c, gd, best, rng)
            clicks += clicks_cfg["steal"]
            clock += 1
            visit += 1
            if r["ok"]:
                stock[best] -= 1
                pocket += vals[best]
                if dep is not None and pocket >= dep:
                    clicks += clicks_cfg["deposit"]
                    stash += pocket
                    pocket = 0
                continue
            if kind == "now":
                continue
            if kind in ("A", "AL"):
                clicks += clicks_cfg["confront"]
                if kind == "A":
                    arrests += 1
                    clear_bounty()
                    continue
                clicks += clicks_cfg["fight"]                                      # 拔劍反抗
                cfg = guard_cfg_for(crime.bounty(c, prov))
                if rng.chance(WIN[(arch, cfg)]):
                    crime.add_bounty(c, prov, 40)                                  # 拒捕
                    crime.guard_kill_penalty(c, prov, len(GUARD_CFG[cfg]))         # 殺官(真實函式)
                else:
                    dead = True
                    break
            if kind in ("L", "AL") and crime.shop_refuses(c, prov):                # 封店:就地自首清賞金
                locks += 1
                clicks += clicks_cfg["clear_town"]
                clear_bounty()
        if clicks >= B or dead:
            break
        clicks += clicks_cfg["wait"]
        clock = max(clock, c.shop_restock_at.get(loc, clock))
    return pocket + stash, min(clicks, B + 12), dead, lost, arrests, locks


def eval_regime(pool, arch, tier, kind, clicks_cfg):
    best = None
    for dep in (DEP if kind in ("A", "AL", "L") else (None,)):
        for k in KS:
            jobs = [(arch, loc, tier, s, kind, k, dep, clicks_cfg) for loc in LOCS for s in range(N_RUN)]
            rs = pool.map(long_run, jobs, chunksize=8)
            gpc = S.mean(r[0] / r[1] for r in rs)
            if best is None or gpc > best[0]:
                best = (gpc, k, dep, S.mean(r[2] for r in rs), S.mean(r[3] for r in rs), S.mean(r[4] for r in rs),
                        S.mean(r[5] for r in rs), S.mean(r[0] for r in rs))
    return best


THEFT: dict = {}          # (構築, 階, 制度) → 最佳 gold/click


def section1(pool):
    print("== 1 抓捕情境(R226 現行規則;金/點擊 = 預算 %d 點擊內累積贓物底價 / 實際點擊;取最佳 k / 存倉門檻)==" % B)
    print(f"點擊成本:{CLICK};封店線 {crime.SHOP_REFUSE_BOUNTY};殺官 +{crime.GUARD_KILL_BOUNTY}/名")
    print(f"{'構築·階':10}{'制度':8}{'金/點擊':>8}{'vs之前':>8}{'k':>4}{'存倉門檻':>8}{'死亡':>6}{'丟失贓物':>9}{'被捕':>6}{'封店':>6}")
    for arch in ("top", "mid", "novice"):
        for tier in (0, 2):
            base = None
            kinds = ["now", "A"] + (["AL", "L"] if arch == "top" else [])
            for kind in kinds:
                gpc, k, dep, dead, lost, arrests, locks, _gold = eval_regime(pool, arch, tier, kind, CLICK)
                THEFT[(arch, tier, kind)] = gpc
                base = base or gpc
                label = {"now": "R226之前", "A": "入獄", "AL": "反抗", "L": "隱形"}[kind]
                print(f"{arch + ' 階' + str(tier):10}{label:8}{gpc:>8.1f}{gpc / base - 1:>+8.0%}{k:>4}{'-' if dep is None else dep:>8}"
                      f"{dead:>6.0%}{lost:>9.0f}{arrests:>6.1f}{locks:>6.1f}")
            now = THEFT[(arch, tier, "now")]
            cur = max(THEFT[(arch, tier, kd)] for kd in ("A", "AL") if (arch, tier, kd) in THEFT)
            THEFT[(arch, tier, "current")] = cur
            print(f"{'':10}{'→現行':8}{cur:>8.1f}{cur / now - 1:>+8.0%}   (A / AL 取較佳者)")
        print()
    # 敏感度:點擊成本全部壓到對小偷最有利
    print(f"敏感度(點擊成本對小偷最有利 {CLICK_LENIENT};頂級構築):")
    for tier in (0, 2):
        now = eval_regime(pool, "top", tier, "now", CLICK_LENIENT)[0]
        cur = max(eval_regime(pool, "top", tier, kd, CLICK_LENIENT)[0] for kd in ("A", "AL"))
        THEFT[("top", tier, "lenient")] = cur
        print(f"  top 階{tier}:之前 {now:.1f} → 現行最佳 {cur:.1f}({cur / now - 1:+.0%})")


# ---------------------------------------------------------------- 2 行竊 vs 其他途徑
def _rounds_job(task):
    """一座地城(一組種子)全清的點擊估計:格數取自真實生成器,戰鬥回合取自真實戰鬥(sim_dungeon.fight;每場新角色·不帶血)。"""
    dkey, seed = task
    spec = SD.SPECS[dkey]
    grid = dungeoncrawl.generate(spec, gd, RNG(1000 + seed))
    rounds = [0]
    real_tick = magic.tick_effects
    holder = {}

    def _counted(ch, gdata, *a, **k):                       # 每回合結尾對玩家 tick 一次 → 數玩家的回合
        if ch is holder.get("player"):
            rounds[0] += 1
        return real_tick(ch, gdata, *a, **k)
    magic.tick_effects = _counted
    try:
        monsters = [cell["enemies"] for layer in grid["layers"] for row in layer for cell in row
                    if cell["type"] == dungeoncrawl.MONSTER]
        containers = sum(1 for layer in grid["layers"] for row in layer for cell in row if cell["type"] == dungeoncrawl.CONTAINER)
        interesting = sum(1 for layer in grid["layers"] for row in layer for cell in row
                          if cell["type"] in (dungeoncrawl.MONSTER, dungeoncrawl.CONTAINER, dungeoncrawl.BOSS))
        reach = sum(len(dungeoncrawl.reachable_cells(grid, z)) for z in range(len(grid["layers"])))
        died = False
        for i, ids in enumerate(monsters):
            c = SD.make("assassin", "open_no100")
            holder["player"] = c
            res = SD.fight(c, "assassin", ids, seed * 1009 + i)
            died = died or res == "dead"
        c = SD.make("assassin", "open_no100")
        holder["player"] = c
        SD.fight(c, "assassin", [SD.spawn_boss(spec, RNG(seed * 13 + 5))], seed * 1009 + 999, max_rounds=120)
    finally:
        magic.tick_effects = real_tick
    moves_opt = interesting + max(0, len(grid["layers"]) - 1)         # 只走到有東西的格(樂觀)
    moves_pess = 2 * max(0, reach - 1) + max(0, len(grid["layers"]) - 1)   # 全圖來回走一遍(悲觀)
    return dkey, rounds[0], moves_opt, moves_pess, containers, died


def sell_ratio(profile):
    """賣給商店的實得 / 底價(該角色對可賣物品的平均;真實 world.sell_price)。"""
    c = E.make_char(**profile)
    vs = [(world.sell_price(c, gd, i), gd.item(i)["value"]) for i in E.POOL]
    return sum(a for a, _ in vs) / sum(b for _, b in vs)


def fence_ratio(arch="top"):
    """贓物銷贓實得 / 底價(依該構築的議價與惡名、依架上期望量加權;真實 world.fence_stolen_price)。
    頂級小偷(議價滿 + 公會頂階 + 惡名 50)≈ ×1.2;低議價、無惡名者拿不到(贓物價 = 名目賣價 ×(1 + 惡名加價),夾在上限以下)。"""
    c = thief_char(arch, "whiterun", 0)
    num = den = 0.0
    for lid in E.SHOP_LOCS:
        for i in world.merchant_catalog(gd, lid, 2):
            q = E.expected_restock(i, 2)
            num += q * world.fence_stolen_price(c, gd, i)
            den += q * gd.item(i)["value"]
    return num / den


def section2(pool):
    print("\n== 2 行竊 vs 其他途徑(金/點擊;底價 = 不含賣出折扣,實得 = 含)==")
    lo, hi = sell_ratio(dict(mercantile=5, personality=40)), sell_ratio(E.MAXED)
    frs = {a: fence_ratio(a) for a in THIEF}
    fr = frs["top"]
    print(f"換現比:戰利品賣商店 ×{lo:.2f}(新手議價)~ ×{hi:.2f}(議價滿);贓物銷贓 頂級 ×{frs['top']:.2f} · 中階 ×{frs['mid']:.2f} · 新手 ×{frs['novice']:.2f}")
    inc = E.dungeon_income()
    tasks = [(dk, s) for dk in SD.SPECS for s in range(D_SEEDS)]
    rows = pool.map(_rounds_job, tasks, chunksize=2)
    by = {}
    for dk, rounds, mo, mp, cont, died in rows:
        by.setdefault(dk, []).append((rounds, mo, mp, cont))
    per = {}
    for dk, xs in by.items():
        rounds = S.mean(x[0] for x in xs)
        cont = S.mean(x[3] for x in xs)
        opt = S.mean(x[1] for x in xs) + rounds + cont
        pess = S.mean(x[2] for x in xs) + rounds + cont
        danger, gold, val = inc[dk]
        per[dk] = (danger, gold, val, opt, pess, rounds, S.mean(x[1] for x in xs), S.mean(x[2] for x in xs), cont)
    print(f"\n地城全清(每座 {D_SEEDS} 組種子;點擊 = 移動 + 開箱 + 戰鬥回合;刺客完全體,每場新角色):")
    print(f"{'危險度':>6}{'座數':>5}{'金幣':>8}{'戰利品底價':>11}{'點擊(樂/悲)':>14}{'底價 金/點擊(悲~樂)':>22}{'實得 金/點擊(悲·新手~樂·議價滿)':>34}")
    dung_pc = {}
    for danger in sorted({v[0] for v in per.values()}):
        xs = [v for v in per.values() if v[0] == danger]
        g, v, o, p = (S.mean(x[i] for x in xs) for i in (1, 2, 3, 4))
        base_o, base_p = (g + v) / o, (g + v) / p
        real_lo = (g + v * lo) / p
        real_hi = (g + v * hi) / o
        dung_pc[danger] = (base_p, base_o, real_lo, real_hi)
        print(f"{danger:>6}{len(xs):>5}{g:>8.0f}{v:>11.0f}{o:>7.0f}/{p:<6.0f}{base_p:>10.1f} ~ {base_o:<8.1f}{real_lo:>14.1f} ~ {real_hi:<10.1f}")
    tot_g = sum(v[1] for v in per.values())
    tot_v = sum(v[2] for v in per.values())
    tot_o = sum(v[3] for v in per.values())
    tot_p = sum(v[4] for v in per.values())
    print(f"{'全部':>6}{len(per):>5}{tot_g:>8.0f}{tot_v:>11.0f}{tot_o:>7.0f}/{tot_p:<6.0f}{(tot_g + tot_v) / tot_p:>10.1f} ~ {(tot_g + tot_v) / tot_o:<8.1f}"
          f"{(tot_g + tot_v * lo) / tot_p:>14.1f} ~ {(tot_g + tot_v * hi) / tot_o:<10.1f}")
    print("\n行竊(R226 現行最佳 vs 之前;底價 / 贓物銷贓實得 = 底價 × 銷贓比):")
    print(f"{'構築·階':10}{'之前 底價':>10}{'現行 底價':>10}{'現行 實得':>10}{'現行/之前':>10}")
    for arch in ("top", "mid", "novice"):
        for tier in (0, 2):
            now, cur = THEFT[(arch, tier, "now")], THEFT[(arch, tier, "current")]
            print(f"{arch + ' 階' + str(tier):10}{now:>10.1f}{cur:>10.1f}{cur * frs[arch]:>10.1f}{cur / now:>10.0%}")
    prof = max((x[5] for x in E.recipe_resale()), default=0)
    print(f"\n配方轉賣上界:每城每次補貨最多 {prof:.0f} 金,每次至少 3 點擊(買 / 做 / 賣)→ ≤ {prof / 3:.1f} 金/點擊(另每件花一小時與體力)。")
    q_once, q_rep = E.quest_gold()
    print(f"任務(未估點擊):一次性 {sum(n for n, _ in q_once.values())} 個、金幣合計 {sum(t for _n, t in q_once.values())};可重複中位數 {q_rep:.0f}。")
    print("商人行情 / 議價:不是獨立收入(只放大賣出價),沒有單獨的每點擊收入。")
    # 一行結論(機器算的比值,敘述由人下)
    t2_now, t2_cur = THEFT[("top", 2, "now")], THEFT[("top", 2, "current")]
    mid = [dung_pc[d] for d in (4, 5) if d in dung_pc]
    print(f"\n→ 頂級·階 2 行竊(實得,贓物銷贓 ×{fr:.2f}):R226 之前 {t2_now * fr:.0f} → 現行 {t2_cur * fr:.0f} 金/點擊;"
          f"地城全部 {(tot_g + tot_v * lo) / tot_p:.0f}(悲觀·新手議價)~ {(tot_g + tot_v * hi) / tot_o:.0f}(樂觀·議價滿),"
          f"危險度 4~5(72 座中佔大宗){S.mean(x[2] for x in mid):.0f} ~ {S.mean(x[3] for x in mid):.0f}。")
    return per


# ---------------------------------------------------------------- 3 訓練收入減支出
def section3(per):
    print("\n== 3 訓練收入減支出(依危險度由低到高累積;實得 = 金幣 + 戰利品 × 換現比)==")
    lo, hi = sell_ratio(dict(mercantile=5, personality=40)), sell_ratio(E.MAXED)
    marks, all_cost, final = E.buy_levels(tuple(range(2, 120)))
    lv_sorted = sorted(marks)

    def buyable(gold):
        got = 1
        for lv in lv_sorted:
            if marks[lv] <= gold:
                got = lv
        return got
    order = sorted(per, key=lambda dk: (per[dk][0], dk))        # 依危險度由低到高清(地城沒有等級門檻;怪物 min_level 只是出現下限,不拿來當「自然等級」)
    q_once, _rep = E.quest_gold()
    quest_total = sum(t for _n, t in q_once.values())
    print(f"純靠付費訓練買等級:到 5 級 {marks.get(5, 0)} · 10 級 {marks.get(10, 0)} · 20 級 {marks.get(20, 0)} · 全技能到訓練師上限 {all_cost} 金(角色 {final} 級)")
    print(f"{'清到危險度':>10}{'累積座數':>9}{'累積實得(新手)':>15}{'可買等級':>9}{'累積實得(議價滿)':>17}{'可買等級':>9}{'占全訓練':>9}")
    cum_g = cum_v = 0.0
    done = 0
    last = {}
    for dk in order:
        cum_g += per[dk][1]
        cum_v += per[dk][2]
        done += 1
        last[per[dk][0]] = (done, cum_g + cum_v * lo, cum_g + cum_v * hi)
    for danger in sorted(last):
        n, g_lo, g_hi = last[danger]
        print(f"{danger:>10}{n:>9}{g_lo:>15.0f}{buyable(g_lo):>9}{g_hi:>17.0f}{buyable(g_hi):>9}{g_hi / all_cost:>9.0%}")
    sk = E.sinks()
    sink_total = all_cost + sk["houses"] + sk["upgrades"] + sk["spells"] + sk["mounts"]
    print(f"一次性任務金幣另有 {quest_total}(上表未含)。全部一次性去處合計 {sink_total}:訓練 {all_cost} · 房產 {sk['houses']} · 擴建 {sk['upgrades']} · 法術 {sk['spells']} · 坐騎 {sk['mounts']}")
    g_hi_all = cum_g + cum_v * hi + quest_total
    g_lo_all = cum_g + cum_v * lo + quest_total
    print(f"全地城清完加任務的總收入:{g_lo_all:.0f}(新手議價)~ {g_hi_all:.0f}(議價滿)= 全部去處總價的 {g_lo_all / sink_total:.0%} ~ {g_hi_all / sink_total:.0%}。"
          f"(地城重踞 / 可重複任務 / 行竊另計。)")


# ---------------------------------------------------------------- 4 金幣換實力 vs 親自玩(使用者判準:金幣路徑比親自玩更快 = 過度)
PLAY_SKILLS = ("blade", "light_armor", "acrobatics", "scout", "sneak", "security", "athletics", "speechcraft")


def play_xp_rates(per, n=150):
    """親自玩(清地城)每點擊的技能經驗(依技能)。戰鬥部分用真實戰鬥量:中階小偷構築打危險度 3~4 地城的怪物池,
    攔截 progression.use_skill 記每回合各技能經驗(combat.resolve_attack 內部發命中 / 被擊中 / 閃避 / 格擋經驗);
    再依 A2 的地城點擊組成(戰鬥回合 / 移動 / 開箱)換成每點擊。回 (每點擊各技能 xp, 總 xp/點擊, 戰鬥回合占點擊比例)。"""
    from tesrpg.systems import progression
    pools = [spec["monsters"] for spec in SD.SPECS.values() if spec["danger"] in (3, 4)]
    got, rounds = {}, 0
    holder = {}
    real_use = progression.use_skill

    def counted(char, gdata, sid, xp):
        if char is holder.get("c"):
            got[sid] = got.get(sid, 0.0) + xp
        return real_use(char, gdata, sid, xp)
    progression.use_skill = counted
    try:
        for i in range(n):
            r = RNG(7000 + i)
            pool = pools[i % len(pools)]
            ids = [pool[r.randint(0, len(pool) - 1)] for _ in range(1 + i % 2)]
            c = make_mid_fighter()
            holder["c"] = c
            foes = [combat.spawn_creature(gd, t, RNG(i * 9 + j)) for j, t in enumerate(ids)]
            rng, opening, used = RNG(i), False, [0]
            for _ in range(60):
                if not any(combat.is_alive(e) for e in foes) or c.health <= 0:
                    break
                opening = SA._round(c, foes, rng, opening, used, False)
                rounds += 1
                magic.tick_effects(c, gd)
                for e in foes:
                    if combat.is_alive(e):
                        magic.tick_effects(e, gd)
                stats.clamp_resources(c)
    finally:
        progression.use_skill = real_use
    per_round = {k: v / rounds for k, v in got.items()}
    tot_r = sum(v[5] for v in per.values())
    tot_o = sum(v[3] for v in per.values())
    tot_p = sum(v[4] for v in per.values())
    f_r = (tot_r / tot_o + tot_r / tot_p) / 2                         # 戰鬥回合占點擊(樂觀 / 悲觀組成取平均)
    moves_frac = 1 - f_r - sum(v[8] for v in per.values()) / ((tot_o + tot_p) / 2)
    rate = {k: v * f_r for k, v in per_round.items()}
    rate["scout"] = rate.get("scout", 0.0) + 0.12 * max(0.0, moves_frac)       # 地城每探明一格 → 偵查 xp
    return rate, sum(rate.values()), f_r


def progress(clicks_max, rates, g=0.0, buy=False, batch=20, limit=None):
    """真實 progression 逐批推進:每批把 rates(每點擊各技能 xp)× batch 灌進技能,金幣 += g × batch,
    buy = True 則把金幣拿去付費訓練(永遠訓練當下最低的技能,同 sim_economy.buy_levels);limit = 每個角色等級最多訓練幾次(Skyrim 式限次;None = 不限,現行規則)。回 {角色等級: 達到時的點擊數}。"""
    from tesrpg.systems import progression
    c = build_character(gd, name="徒", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
    gold, reach, t, trained = 0.0, {c.level: 0}, 0, 0
    while t < clicks_max:
        for sid, r in rates.items():
            progression.use_skill(c, gd, sid, r * batch)
        gold += g * batch
        t += batch
        while buy:
            cand = [x for x in gd.skills if c.skills.get(x, formulas.SKILL_BASE) < formulas.TRAINER_CAP]
            if not cand:
                break
            sid = min(cand, key=lambda k: c.skills.get(k, formulas.SKILL_BASE))
            lv = c.skills.get(sid, formulas.SKILL_BASE)
            cost = world.train_cost(lv)
            if gold < cost or (limit is not None and trained >= limit):
                break
            gold -= cost
            trained += 1
            progression.use_skill(c, gd, sid, formulas.skill_threshold(lv))
        while c.can_level_up():
            progression.apply_level_up(c, gd, {"endurance": formulas.LEVELUP_ATTRIBUTE_POINTS})
            reach[c.level] = t
            trained = 0                                                      # 升級後本級的訓練額度重置
    return reach


def clicks_to(reach, level):
    ok = [t for lv, t in reach.items() if lv >= level]
    return min(ok) if ok else None


def section4(per):
    print("\n== 4 金幣換實力 vs 親自玩(判準:同點擊預算下,金幣路徑比親自玩更快 = 金幣過度影響實力)==")
    rate, total, f_r = play_xp_rates(per)
    top = ", ".join(f"{k} {v:.3f}" for k, v in sorted(rate.items(), key=lambda kv: -kv[1])[:5])
    print(f"親自玩(清地城)每點擊技能經驗:合計 {total:.3f} xp/點擊(戰鬥回合占點擊 {f_r:.0%});前幾名:{top}")
    horizon = 60000
    even = {sid: total / len(PLAY_SKILLS) for sid in PLAY_SKILLS}            # 慷慨版:同樣的總經驗平均灌進 8 個技能(玩家把各項都練到)
    fight_rate = {k: v / f_r for k, v in rate.items() if k != "scout"}      # 上限版:每個點擊都是戰鬥回合(例如連續探索狩獵)
    fight_even = {sid: sum(fight_rate.values()) / len(PLAY_SKILLS) for sid in PLAY_SKILLS}
    paths = {
        "親自玩·實測分佈": progress(horizon, rate),
        "親自玩·8 技能平均": progress(horizon, even),
        "親自玩·純戰鬥(上限)": progress(horizon, fight_rate),
        "親自玩·純戰鬥 8 技能(上限)": progress(horizon, fight_even),
    }
    marks, all_cost, final = E.buy_levels(tuple(range(2, 120)))
    levels = (5, 10, 20, 30, 40)
    print(f"\n到達角色等級所需點擊(--- = 預算 {horizon} 點擊內到不了;純靠訓練上限 = 全技能 75 → 角色約 {final} 級):")
    print(f"{'路徑':26}" + "".join(f"{'Lv' + str(L):>9}" for L in levels))
    for name, reach in paths.items():
        print(f"{name:26}" + "".join(f"{(clicks_to(reach, L) or '---'):>9}" for L in levels))
    for g in (10, 30, 70):
        reach = progress(horizon, {}, g=g, buy=True)
        paths[f"純賺錢買訓練 {g} 金/點擊"] = reach
        print(f"{'純賺錢買訓練 ' + str(g) + ' 金/點擊':26}" + "".join(f"{(clicks_to(reach, L) or '---'):>9}" for L in levels))
    for g in (15, 40, 75):
        reach = progress(horizon, even, g=g, buy=True)
        paths[f"玩 + 賺錢買訓練 {g}"] = reach
        print(f"{'玩(8技能)+地城賺錢買 ' + str(g):26}" + "".join(f"{(clicks_to(reach, L) or '---'):>9}" for L in levels))
    print("\n臨界收入(金/點擊):純賺錢買訓練的速度剛好追平「親自玩」所需的收入 = 買到該等級的總價 / 親自玩到該等級的點擊;"
          "實際收入高於它,金幣路徑就比親自玩快。")
    print(f"{'親自玩版本':26}" + "".join(f"{'Lv' + str(L):>9}" for L in levels))
    for name in ("親自玩·實測分佈", "親自玩·8 技能平均", "親自玩·純戰鬥(上限)", "親自玩·純戰鬥 8 技能(上限)"):
        row = ""
        for L in levels:
            t = clicks_to(paths[name], L)
            row += f"{(marks.get(L, 0) / t if t and L in marks else float('nan')):>9.1f}"
        print(f"{name:26}{row}")
    print("\n金幣加速倍率(= 親自玩到該等級的點擊 / 玩 + 地城賺錢買訓練〔40 金/點擊〕到該等級的點擊;> 1 = 買訓練讓你更快):")
    print(f"{'親自玩版本':26}" + "".join(f"{'Lv' + str(L):>9}" for L in levels))
    for name in ("親自玩·8 技能平均", "親自玩·純戰鬥 8 技能(上限)"):
        sp = progress(horizon, even if "純戰鬥" not in name else fight_even, g=40, buy=True)
        row = ""
        for L in levels:
            a, b = clicks_to(paths[name], L), clicks_to(sp, L)
            row += f"{(a / b if a and b else float('nan')):>8.1f}x"
        print(f"{name:26}{row}")
    print("\n訓練「每個角色等級最多 N 次」的效果(設計用敏感度;玩 8 技能 + 地城賺錢 40 金/點擊;加速倍率 = 親自玩的點擊 / 該路徑的點擊):")
    print(f"{'每級限次':14}" + "".join(f"{'Lv' + str(L):>9}" for L in levels))
    for lim in (None, 5, 3, 2, 1):
        sp = progress(horizon, even, g=40, buy=True, limit=lim)
        row = ""
        for L in levels:
            a, b = clicks_to(paths["親自玩·8 技能平均"], L), clicks_to(sp, L)
            row += f"{(a / b if a and b else float('nan')):>8.1f}x"
        print(f"{('不限(現行)' if lim is None else str(lim) + ' 次/級'):14}{row}")
    print("對照實得收入(金/點擊,A2):頂級·階 2 行竊 %.0f;地城 %s;中階 / 新手小偷 4~12 / 2~7;配方轉賣 ≤ 5。"
          % (THEFT[("top", 2, "current")] * 1.20, "全部 18~89、危險度 4~5 為 14~73"))
    print("⚠ 限制:每點擊經驗為中階構築 + 地城組成的估計(固定值,不隨等級變);純賺錢那條假設從第 1 點擊就有該收入(對金幣路徑慷慨);"
          "親自玩沒算旅行 / 休息 / 練習 / 事件等其他經驗來源;訓練上限 75(76 以上只能實戰)。")


if __name__ == "__main__":
    with Pool(NPROC) as pool:
        for key, wr in pool.map(_fight_job, [(a, c) for a in FIGHTERS for c in GUARD_CFG]):
            WIN[key] = wr
    print("衛兵戰勝率(盤查非伏擊;完整治療;n=%d):" % N_FIGHT)
    for a in FIGHTERS:
        print(f"  {a:7}" + "".join(f"{c}={WIN[(a, c)]:.0%}  " for c in GUARD_CFG))
    print()
    with Pool(NPROC) as pool:                       # 勝率表算完才 fork(子行程要看得到 WIN)
        section1(pool)
        per = section2(pool)
    section3(per)
    section4(per)
