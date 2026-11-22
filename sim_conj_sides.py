"""召喚系三節點「兩側」強度對照(R203 後新增;手動工具·print-only·不接 check.sh):確認每個節點的兩個選項差距不會太大、各有被選擇的理由。
用法(須在倉庫根目錄,sim_dungeon 讀相對路徑):`PYTHONPATH=. CMP_N=120 python3 sim_conj_sides.py`(並行 ~18 工,約 8 分鐘;CMP_N 預設 150)。

節點:50 咒靈共鳴 vs 束縛精通 / 75 瞬發契印 vs 就地起屍(屍僕)/ 100 永契之僕 vs 亡者統御;每個節點另列「不選」。
構築:S 激進 / S 保守(召喚師)、N 死靈師(夾具種 40 token)、N 缺魂(起手 4 token)、B 騎士(束縛騎士·雙手束縛巨劍·無盾)、B 騎 1H(束縛騎士·束縛長劍 + 盾 + 姿態;R204 起取代舊的法袍 B 束縛夾具——那個夾具力量 30 + 法袍,刃傷只看召喚與力量,結論失真)。
情境:王野 / 王城 = 古龍·烏瑪利單王(野外 / 地城預召喚×3);牆野 / 牆城剩血 = 達貢(胜率恆 0,看王剩餘血);群野 / 群城 = 5 種敵群平均;
      地城灰 / 地城龍 = 真實地城整趟(sim_dungeon 同一套規格:灰燼墓 15 怪格 + 魔人領主 / 龍巢;通關 = 打到終王倒下,進度 = 清掉的怪格比例;
      場間走 3 格、無休息無回魔、進格前自由預召喚、契僕 / 屍僕跨戰、token 收割照 main)。
讀法:每個節點下方列「A 領先 B ≥5pp 的情境」與反向;**任一側在所有構築 × 情境都沒有領先處 = 被支配 = 沒有選擇理由**(R203 評估即靠此抓到起屍被契印支配)。
⚠ 限制:策略是我寫的模擬策略(激進為理想化)、n=120 時單格噪聲 ±9pp(只看明顯超出噪聲的差距)、龍巢對所有構築太難(通關全 0)。
"""
import collections, os, sys
_argv, sys.argv = sys.argv, ["sim_conj.py", "100"]   # sim_conj 於匯入時讀 argv[1] 當 N
import sim_conj as S
sys.argv = _argv
import sim_dungeon as D
from concurrent.futures import ProcessPoolExecutor
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, magic, necromancy, stats
sb, sp, gd = S.sb, S.sp, S.gd
N = int(os.environ.get("CMP_N", "150"))

# ---------- 構築與策略 ----------
def _bound_present(c):
    return any(e.get("kind") == "bound_weapon" and e.get("turns", 0) > 0 for e in c.active_effects)

def _knight_maker(name):
    """束縛騎士(sim_builds 夾具,R204)+ 戰鬥用藥水疊(同 sb.fight 對近戰構築的處理)。"""
    def f():
        c = sb.BUILDS[name]()
        inventory.add_item(c, "healing_potion", sb._COMBAT_POTIONS)
        return c
    return f

def _knight_act(name):
    """sim_builds 的束縛騎士策略(束縛兵刃失效就重施 → 回 "summon" 讓契印可免費施放)接成本工具的 (c, boss, rng, battle, st) 簽名。"""
    pol = sb._POLICY[name]
    def act(c, boss, rng, battle, st):
        st.setdefault("use_stance", name in sb._STANCE_BUILDS)
        return pol(c, boss, rng, st)
    def prep(c, boss, rng, battle, st):      # 備戰(自由行動)只預凝束縛兵刃,不揮砍
        spell = next(s for s in ("bound_sword", "bound_mace", "bound_axe", "bound_greatsword") if s in c.spells)
        if not _bound_present(c) and magic.can_cast(c, gd, spell):
            magic.cast(c, gd, spell, rng, battle=battle)
            return "summon"
        return None
    act.prep = prep
    return act

def make_necro_poor():
    c = sb.make_necromancer(); c.soul_tokens = 4        # token 緊張的死靈師(實戰靠打怪 + 回收積累;夾具預設 40 隔離稀缺,看不出免費起屍 / +1 token 的價值)
    return c

ARCH = {"S激進": (sb.make_summoner, S.act_aggressive), "S保守": (sb.make_summoner, S.act_conservative),
        "N死靈": (sb.make_necromancer, S.act_necro), "N缺魂": (make_necro_poor, S.act_necro),
        "B騎士": (_knight_maker("bound_knight"), _knight_act("bound_knight")),            # 束縛騎士·雙手(束縛巨劍·無盾)
        "B騎1H": (_knight_maker("bound_knight_1h"), _knight_act("bound_knight_1h"))}      # 束縛騎士·單手(束縛長劍 + 盾 + 姿態)

OPTS = {"none": {}, "50共鳴": {"conjuration_50": "summon_casting"}, "50束縛": {"conjuration_50": "bound_mastery"},
        "75契印": {"conjuration_75": "conj_efficiency"}, "75起屍": {"conjuration_75": "soul_harvest"},
        "100永契": {"conjuration_100": "lasting_summon"}, "100統御": {"conjuration_100": "undead_dominion"}}
NODES = {"50": ("50共鳴", "50束縛"), "75": ("75契印", "75起屍"), "100": ("100永契", "100統御")}

def mk_with(mk, choices):
    def f():
        c = mk()
        for nid in S.NODES: c.mastery_choices.pop(nid, None)
        for nid, opt in choices.items(): c.mastery_choices[nid] = opt
        stats.recompute_max_resources(c, gd, restore_full=True)
        return c
    return f

PACKS = [("4×魔人", ("dremora",) * 4), ("5×魔人", ("dremora",) * 5), ("4×巨魔", ("bog_troll",) * 4),
         ("3魔人+3風暴亞", ("dremora",) * 3 + ("storm_atronach",) * 3), ("6×魔人", ("dremora",) * 6)]
BOSSES = ("ancient_dragon", "umaril_the_unfeathered", "mehrunes_dagon")
DUNGEON = [("3×魔人", ("dremora",) * 3), ("3×巨魔", ("bog_troll",) * 3), ("4×魔人", ("dremora",) * 4), ("古龍", ("ancient_dragon",))]

# ---------- 戰鬥迴圈(鏡像 main.run_battle;狀態外部持有以便地城連戰)----------
def battle_loop(c, act, enemies, battle, st, rng, boss=None, max_rounds=60):
    alive_en = lambda: [e for e in enemies if combat.is_alive(e)]
    rounds = 0
    for _ in range(max_rounds):
        if boss is not None and not combat.is_alive(boss): return "win", rounds
        if not alive_en(): return "win", rounds
        if c.health <= 0: return "dead", rounds
        rounds += 1
        if not magic.is_incapacitated(c):
            S.player_phase(c, alive_en()[0] if boss is None else boss, rng, battle, st, act)
        if (boss is not None and not combat.is_alive(boss)) or not alive_en(): return "win", rounds
        for a in sp._living_allies(battle):
            if not alive_en(): break
            if magic.is_incapacitated(a): continue
            if magic.summon_support_act(a, c, sp._living_allies(battle), gd) is not None: continue
            tgt = rng.choice(alive_en()); atk = combat.choose_attack(a, rng, tgt)
            if atk.get("taunt"):
                a.active_effects.append({"kind": "taunt", "turns": atk.get("turns", 3)}); continue
            combat.resolve_attack(a, tgt, gd, rng, attack=atk)
        if (boss is not None and not combat.is_alive(boss)): return "win", rounds
        for e in list(enemies):
            if c.health <= 0: break
            if not combat.is_alive(e) or magic.is_incapacitated(e): continue
            if boss is not None and combat.try_boss_summon(e, enemies, gd, rng) is not None: continue
            tgt = combat.pick_player_side_target(c, battle["allies"], rng)
            combat.resolve_attack(e, tgt, gd, rng, attack=combat.choose_enemy_attack(e, rng, tgt))
        necromancy.auto_raise(c, gd, rng, battle, enemies)
        battle["allies"], gone = combat.tick_summons(battle["allies"])
        combat.quick_seal_recharge(c, gd, gone)
        sb._regen(c); magic.tick_effects(c, gd)
        for a in battle["allies"]:
            if combat.is_alive(a): magic.tick_effects(a, gd)
        for e in enemies:
            if combat.is_alive(e): magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    return "timeout", rounds

def prep(c, act, target, rng, battle, st, presummon):
    pf = getattr(act, "prep", act)
    for _ in range(presummon):
        if pf(c, target, rng, battle, st) != "summon": break
    if presummon:
        battle["allies"], _g = combat.tick_summons(battle["allies"])

def boss_fight(maker, act, boss_id, seed, presummon):
    c = maker(); boss = combat.spawn_creature(gd, boss_id, RNG(seed * 9 + 1))
    rng = RNG(seed); battle = {"allies": []}; st = {"buffed": False}
    prep(c, act, boss, rng, battle, st, presummon)
    res, _ = battle_loop(c, act, [boss], battle, st, rng, boss=boss, max_rounds=80)
    return res, max(0, boss.health)

def pack_fight(maker, act, ids, seed, presummon):
    c = maker(); enemies = [combat.spawn_creature(gd, e, RNG(seed * 13 + i + 1)) for i, e in enumerate(ids)]
    rng = RNG(seed); battle = {"allies": []}; st = {"buffed": False}
    prep(c, act, enemies[0], rng, battle, st, presummon)
    return battle_loop(c, act, enemies, battle, st, rng)[0]

from tesrpg.systems import dungeoncrawl

def dungeon_run(maker, act, seed, dkey="ashfall_barrow", steps=3, start_tokens=None):
    """整趟真實地城(sim_dungeon 同一套規格:真實怪格序列 + 該地城終王);怪格順序走完才進終王;場間走 steps 格
    (玩家效果 / 召喚物 tick,無休息無回魔)、進格前自由預召喚;戰後清玩家效果,只留『戰前就在清單者(預召喚 / 前戰帶入)』與戰中存活契僕
    (R203b 跨戰);token 收割 + 回收照 main。回 (通關?, 通過怪格數 / 總怪格數, 終血比)。"""
    spec = D.SPECS[dkey]
    grid = dungeoncrawl.generate(spec, gd, RNG(seed * 7 + 3))
    mobs = [cell["enemies"] for layer in grid["layers"] for row in layer for cell in row if cell["type"] == dungeoncrawl.MONSTER]
    c = maker(); rng = RNG(seed); allies = []; cleared = 0
    if start_tokens is not None: c.soul_tokens = start_tokens
    fights = [("m", ids) for ids in mobs] + [("boss", None)]
    for fi, (kind, ids) in enumerate(fights):
        if kind == "boss":
            enemies = [D.spawn_boss(spec, RNG(seed * 13 + 5))]
        else:
            enemies = [combat.spawn_creature(gd, e, RNG(seed * 1009 + fi * 7 + i + 1)) for i, e in enumerate(ids)]
        if fi > 0:
            for _ in range(steps):
                magic.tick_effects(c, gd)
                for a in allies:
                    if combat.is_alive(a): magic.tick_effects(a, gd)
                allies, _g = combat.tick_summons(allies)
        battle = {"allies": allies}; st = {"buffed": False}
        prep(c, act, enemies[0], rng, battle, st, 3)
        pre_ids = {id(a) for a in battle["allies"]}
        boss = enemies[0] if kind == "boss" else None
        res, _ = battle_loop(c, act, enemies, battle, st, rng, boss=boss, max_rounds=120 if kind == "boss" else 80)
        if res != "win":
            return False, cleared / len(mobs), max(0.0, c.health / c.max_health)
        if kind == "m":
            cleared += 1
        necromancy.harvest_and_recover(c, gd, sum(1 for e in enemies if not combat.is_alive(e)), battle["allies"])
        allies = [a for a in battle["allies"] if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)
                  and (id(a) in pre_ids or combat.is_persistent_servant(a))]   # 與 main 地城寫回同一謂詞(契僕 / 屍僕)
        c.active_effects.clear()
    return True, 1.0, max(0.0, c.health / c.max_health)

# ---------- 單一(構築, 選項)格 ----------
def eval_cell(task):
    arch, opt = task
    mk, act = ARCH[arch]; maker = mk_with(mk, OPTS[opt]); out = {}
    for ps, tag in ((0, "野"), (3, "城")):
        r = [boss_fight(maker, act, b, s, ps) for b in BOSSES[:2] for s in range(N // 2)]
        out[f"王{tag}"] = sum(x[0] == "win" for x in r) * 100.0 / len(r)
        r = [boss_fight(maker, act, "mehrunes_dagon", s, ps) for s in range(N // 3)]
        out[f"牆{tag}剩血"] = sum(x[1] for x in r) / len(r)
        r = [pack_fight(maker, act, ids, s, ps) for _, ids in PACKS for s in range(N // 2)]
        out[f"群{tag}"] = sum(x == "win" for x in r) * 100.0 / len(r)
    for dkey, tag in (("ashfall_barrow", "灰"), ("dragon_lair", "龍")):
        r = [dungeon_run(maker, act, s, dkey) for s in range(N)]
        out[f"地城{tag}通關"] = sum(x[0] for x in r) * 100.0 / N
        out[f"地城{tag}進度"] = sum(x[1] for x in r) * 100.0 / N
    return task, out

if __name__ == "__main__":
    tasks = [(a, o) for a in ARCH for o in OPTS]
    res = {}
    with ProcessPoolExecutor(max_workers=min(18, len(tasks))) as ex:
        for task, out in ex.map(eval_cell, tasks):
            res[task] = out
    keys = ["王野", "王城", "牆野剩血", "牆城剩血", "群野", "群城", "地城灰通關", "地城灰進度", "地城龍通關", "地城龍進度"]
    print(f"######## 召喚系兩側對照(n={N};勝率% / 牆剩血 = 達貢剩餘血 / 地城 = 通關% 與清怪格進度%) ########")
    for nid, (a, b) in NODES.items():
        print(f"\n== 節點 {nid}:{a}  vs  {b}  (另列『不選』) ==")
        print("構築    選項      " + " ".join(k[:6].ljust(7) for k in keys))
        for arch in ARCH:
            for o in ("none", a, b):
                print(f"{arch:6} {o:8} " + " ".join(f"{res[(arch, o)][k]:6.0f} " for k in keys))
            ra, rb, r0 = res[(arch, a)], res[(arch, b)], res[(arch, "none")]
            lead = lambda x, y: [k for k in ("王野", "王城", "群野", "群城", "地城灰通關", "地城灰進度", "地城龍通關", "地城龍進度") if x[k] - y[k] >= 5]
            print(f"       → {a} 領先{b}≥5pp:{lead(ra, rb) or '—'};{b} 領先{a}≥5pp:{lead(rb, ra) or '—'}")
    print("\n※ 讀法:某一側在所有構築 × 情境都沒有『領先 ≥5pp』處 = 被另一側支配(沒有選擇理由);幅度差 >3 倍也值得人眼覆核。")
