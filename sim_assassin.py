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


def _round(c, foes, rng, opening, used, stam=False):
    """打一個回合:低血(<45%)且能隱遁就嘗試隱遁,否則攻最低血敵人。回傳新的 opening。
    R71:隱遁不再無敵 —— 成功只重置偷襲,敵人照常攻擊(防禦純靠 evasion)。"""
    alive = [e for e in foes if combat.is_alive(e)]
    vanished = False
    if not opening and combat.afterimage_ready(c, gd, len(alive)):
        # R186 幻影步:殘影達門檻 → 殘影連襲(偷襲先機在手時先偷襲;與 main.run_battle 共用 afterimage_ready 閘)。
        # 沒選此里程碑的構築 afterimage_ready 恆 False 且不擲 rng → 既有輸出逐位元組不變。
        for _ in combat.phantom_flurry(c, foes, gd, rng):
            pass
    elif c.health < c.max_health * 0.45 and combat.can_vanish(c, gd) \
            and combat.try_vanish(c, len(alive), used[0], rng):
        used[0] += 1
        combat.player_vanish_cost(c)         # 保真:隱遁耗體力(連續隱遁會耗竭→後續命中下降),對齊 main.py
        vanished = True                      # R71:只重獲偷襲先機,不再讓敵人撲空
    else:
        tgt = min(alive, key=lambda e: e.health)
        if stam:                             # R187:普攻也耗體(借風騰挪的核心代價是體力;fixture 預設普攻不耗體會失真)
            combat.player_attack_cost(c, gd)
        combat.resolve_attack(c, tgt, gd, rng, sneak_attack=opening)
    for e in foes:                           # R71:敵人照常攻擊(隱遁不再無敵)
        if combat.is_alive(e) and c.health > 0 and not magic.is_incapacitated(e):
            _atk = combat.choose_attack(e, rng, c)   # 多攻擊模式選招
            _ev = combat.resolve_attack(e, c, gd, rng, attack=_atk)
            combat.misdirect_redirect(c, e, foes, gd, rng, _ev, _atk)   # R187 借風騰挪(沒選此節點者在任何 rng 之前返回 → 既有輸出逐位元組不變)
    return vanished


def fight(maker, enemy_ids, seed, stam=False):
    c = maker()
    foes = [combat.spawn_creature(gd, t, RNG(seed * 9 + i)) for i, t in enumerate(enemy_ids)]
    rng = RNG(seed)
    opening, used = True, [0]
    for _ in range(50):
        if not any(combat.is_alive(e) for e in foes):
            return "win"
        if c.health <= 0:
            return "dead"
        opening = _round(c, foes, rng, opening, used, stam)
        magic.tick_effects(c, gd)
        for e in foes:
            if combat.is_alive(e):
                magic.tick_effects(e, gd)
        stats.clamp_resources(c)
    return "win" if not any(combat.is_alive(e) for e in foes) else "timeout"


def rate(maker, ids, outcome="dead", n=2000, stam=False):
    return sum(fight(maker, ids, s, stam) == outcome for s in range(n)) / n


def oneshot(maker, tid, n=2500):
    k = 0
    for i in range(n):
        ev = combat.resolve_attack(maker(), combat.spawn_creature(gd, tid, RNG(i + 1)),
                                   gd, RNG(i * 7 + 3), sneak_attack=True)
        k += ev["defender_dead"]
    return k / n


def oneshot_with_followup(maker, tid, n=2500):
    """R63 速度追擊紅線:首擊偷襲(受 SOLO_SNEAK 夾)+ 一記『必中』普通追擊(sneak_attack=False)。
    模擬高速度玩家一回合內偷襲+追擊是否秒殺 solo boss(追擊為普通擊 → boss 偷襲後 ≥60% HP,
    普通擊遠不足補刀 → 應仍 0%)。刻意每次都追擊(略過機率)以驗最壞情形。"""
    k = 0
    for i in range(n):
        atk = maker()
        boss = combat.spawn_creature(gd, tid, RNG(i + 1))
        rng = RNG(i * 7 + 3)
        combat.resolve_attack(atk, boss, gd, rng, sneak_attack=True)
        if combat.is_alive(boss):
            combat.resolve_attack(atk, boss, gd, rng, sneak_attack=False)   # 追擊=普通擊(非偷襲)
        k += not combat.is_alive(boss)
    return k / n


def reckless_oneaction(maker, tid, n=800):
    """R191 搏命連斬紅線:**不靠偷襲**、單一「搏命連斬」動作擊殺目標的比例(戰技 = 兩記普通擊,第 2 記 ×0.6,
    每記 sneak_attack=False → 不吃偷襲倍率、不碰 SOLO_SNEAK 夾)。solo 王須 0%;精英僅供參考。
    選了 savage 但戰技不可用(reckless_ready 假)→ 等同沒出手(回 0)。"""
    k = 0
    for i in range(n):
        atk = maker()
        boss = combat.spawn_creature(gd, tid, RNG(i + 1))
        rng = RNG(i * 7 + 3)
        if combat.reckless_ready(atk, gd):
            for _ in combat.reckless_flurry(atk, boss, gd, rng):
                pass
        k += not combat.is_alive(boss)
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
    # R191:savage 已改成主動戰技「搏命連斬」(無 power/recoil)→ 這段現在守「已選 savage 時偷襲路徑不得被連動」;
    # 戰技本身的紅線見下方「R191 搏命連斬紅線」,群戰規模/終王牆守衛見 sim_reckless.py。
    print("\n== P2 里程碑覆核:blade 搏命連斬(已選;主動戰技·不改偷襲傷害)==")
    apex_blade = lambda: assassin(sneak=70, blade=100,
                                  mastery_choices={"blade_100": "savage"})
    for t in ["dremora", "frost_troll"]:
        base = oneshot(lambda: assassin(blade=100), t)
        mod = oneshot(apex_blade, t)
        flag = " ⚠破1.5%" if mod > 0.015 else ""
        print(f"  {t:18} 無里程碑 {base:5.1%} → 搏命連斬 {mod:5.1%}{flag}")

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

    print("\n== R63 速度追擊紅線:apex 偷襲 + 一記普通追擊一回合內是否秒殺 solo boss(應 0%)==")
    print("   追擊強制 sneak_attack=False(普通擊) → 不碰 SOLO_SNEAK 夾;偷襲後 boss ≥60% HP 普通擊補不掉:")
    for t in ["dremora_lord", "vampire_lord", "ancient_dragon", "mehrunes_dagon"]:
        r = oneshot_with_followup(apex_max, t)
        flag = " ⚠破紅線(應為 0%)" if r > 0.0 else " ✓存活"
        print(f"  {t:16} 偷襲+追擊秒殺 {r:5.1%}{flag}")

    print("\n== R191 搏命連斬紅線:已選 savage 的最壞 apex(戰技每記 sneak_attack=False·第 2 記 ×0.6)==")
    print("   ① 不靠偷襲、單一搏命動作擊殺 solo 王(應 0%);② 已選 savage 下偷襲+追擊(R63)仍 0%:")
    # 已知限制(R191 對抗審查實測):夾具無自附魔(與本檔其他紅線段、sim_builds 同「刻意排除自附魔」)。加火附魔 24(主手+副手)後,
    # flat 的附魔/副手補刀傷不吃 damage_factor、兩記各吃一次 → 單一搏命動作擊殺 maormer_captain(96 血)87.9%、vampire_lord 8.5%;
    # 但同夾具「一回合兩記普通攻擊」(R63 追擊最壞)是 91.5% / 60.5% → 搏命沒有超出既有最壞上限。附魔流的 solo 秒殺面另案。
    def apex_savage():
        c = apex_max()
        c.mastery_choices["blade_100"] = "savage"
        return c
    solo_ids = [bid for bid, b in gd.bestiary.items() if b.get("solo")]
    rows = [(t, reckless_oneaction(apex_savage, t, 400)) for t in solo_ids]
    bad = [(t, r) for t, r in rows if r > 0.0]
    print(f"  solo 王 {len(rows)} 隻:單一搏命動作擊殺最大 {max(r for _, r in rows):5.1%}"
          + (f" ⚠破紅線(應為 0%) {bad}" if bad else " ✓全 0%"))
    for t in ["dremora_lord", "vampire_lord", "ancient_dragon", "mehrunes_dagon"]:
        r = oneshot_with_followup(apex_savage, t, 800)
        flag = " ⚠破紅線(應為 0%)" if r > 0.0 else " ✓存活"
        print(f"  {t:16} 已選 savage:偷襲+追擊秒殺 {r:5.1%}{flag}")
    for t in ["dremora", "frost_troll"]:
        print(f"  精英 {t:14} 單一搏命動作擊殺 {reckless_oneaction(apex_savage, t, 400):5.1%}(資訊·非紅線)")

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
    # ② 精英 oneshot 增幅(資訊列·**非紅線**·R128b 由 ⚠守衛降級):
    #    此增幅只在「低HP飽和 fixture」上才 ≤2pp —— 探針證實任何脫飽和精英(lich 等 0-物抗高HP·gap +29pp)
    #    都讓 temper flat(+5)有感,是「飽和函數」而非 temper_power 本質變強。R128 給 dremora/frost_troll
    #    物抗使其脫飽和,同理浮現。對「精英(非 boss·無 cap·可秒)」oneshot 有感=by-design(武器投資對硬敵本該有用);
    #    **真紅線 = temper flat 不破 solo cap → 由 ① 直接守**(且物抗只讓偷襲傷更小 → ① 更穩)。故此列僅印、不 ⚠。
    for t in ["dremora", "frost_troll"]:
        base = oneshot(apex_max, t)
        mod = oneshot(apex_temper, t)
        print(f"  精英 {t:18} apex_max {base:5.1%} → temper_power {mod:5.1%}(Δ{mod - base:+.1%}·資訊非紅線)")
    # ③ 群戰死亡率(對抗審查補):隔離 temper_power 邊際效應 —— 同淬鍊6 build,有/無 power。
    #    註:tempered glass_dagger apex 本就把 4-bandit 死亡率壓到 ~0.4%(既有 tempering+裝備,**非本輪引入**;
    #    舊 26.2% 紅線量的是「無淬鍊」apex,非真實最壞)。此處只驗 temper_power 的邊際不再壓垮。
    dr_notemper = rate(lambda: apex_max(temper=6), ['bandit'] * 4)   # 淬鍊6,factor 0
    dr_power = rate(apex_temper, ['bandit'] * 4)                     # 淬鍊6 + temper_power 0.25
    flag = " ⚠temper_power 邊際壓垮(>10pp)" if (dr_notemper - dr_power) > 0.10 else ""
    print(f"  4 bandit 死亡率(淬鍊6)  無power {dr_notemper:.1%} → +temper_power {dr_power:.1%}(Δ{dr_power - dr_notemper:+.1%}){flag}")

    print("\n== R92 fortify-dosed 覆核:攻擊向 fortify 藥(單瓶最強·potion_buff 取最強非疊加 R30)不破紅線 ==")
    print("   依 R30『放開→必過 sim』:強化力量/武器/潛行藥開放可釀;同 kind+param 取最強非相加(apply_buff)")
    print("   → 單瓶上限 strength~+15/skill~+19(含 fortify-alchemy 抬 brew factor);取 +20 為保守上界驗 solo 0% + 精英不增:")
    def apex_dosed():
        c = apex_max()
        c.potion_attr_bonus = {"strength": 20}              # 單瓶最強~+15(含 fortify-alchemy 增 brew factor);取 +20 保守上界
        c.potion_skill_bonus = {"sneak": 20, "blade": 20}   # 單瓶最強~+19;取 +20 保守上界
        stats.recompute_max_resources(c, gd)
        return c
    for t in ["dremora_lord", "vampire_lord", "ancient_dragon", "mehrunes_dagon"]:   # solo 仍須 0%(SOLO_SNEAK cap 夾 fortify)
        srate = oneshot(apex_dosed, t)
        flag = " ⚠破紅線(應為 0%)" if srate > 0.0 else " ✓存活"
        print(f"  solo {t:16} fortify-dosed 秒殺 {srate:5.1%}{flag}")
    # 精英 oneshot 增幅(資訊列·**非紅線**·R128b 同 R37 part② 降級):同理 —— 脫飽和精英(frost_troll 物抗20)
    #    上 fortify 加傷把 oneshot 補回是「飽和函數」非紅線;真紅線=fortify 不破 solo cap → 上方 solo 列直接守(仍 ⚠)。
    for t in ["dremora", "frost_troll"]:
        base = oneshot(apex_max, t)
        mod = oneshot(apex_dosed, t)
        print(f"  精英 {t:18} apex_max {base:5.1%} → fortify-dosed {mod:5.1%}(Δ{mod - base:+.1%}·資訊非紅線)")

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

    # R186 守衛:輕甲 100 同層「風暴之舞 vs 幻影步(殘影連襲)」。R185 曾想削弱風暴之舞,被使用者否決;R186 改補強幻影步。
    # 設計共識:風暴之舞=物理近戰群王者(反擊限物理近戰·R145);幻影步=閃過任何敵攻(含元素/法術)凝殘影 → 連襲。
    # ⚠ 如實性:首版(傷害 0.8·無 +0.06)幻影步只在「純元素群」勝出;使用者拍板「兩者都做」(傷害 1.0+保留 +0.06)後,
    #    本守衛構築:物理近戰/弩手群風暴之舞仍優,遠程3/純元素/冰魂/混合群幻影步勝。判定列仍只守兩端
    #    (物理近戰→風暴之舞、純元素→幻影步),其餘列只印數字不下判定(資訊,供之後調旋鈕時對照)。
    # 本 sim 的 apex 刺客不選輕甲里程碑 → 固定量一次;守衛構築(輕甲100+雜技100,無裝甲)比完整寫實構築脆。
    print("\n== R186 守衛:輕甲100 風暴之舞 vs 幻影步(判定:物理近戰→風暴之舞、純元素群→幻影步;資訊列不判定)==")
    _lithe = {"light_armor_50": "lithe_evasion"}
    _storm = lambda: assassin(light_armor=100, acrobatics=100, mastery_choices={**_lithe, "light_armor_100": "storm_dance"})
    _phant = lambda: assassin(light_armor=100, acrobatics=100, mastery_choices={**_lithe, "light_armor_100": "phantom_step"})
    for gname, gids, home, n in (("4 bandit(物理近戰)", ["bandit"] * 4, "storm", 500),
                                 ("2 bandit+2 wolf(物理近戰)", ["bandit", "bandit", "wolf", "wolf"], "storm", 500),
                                 ("4 moor_witch(純元素)", ["moor_witch"] * 4, "phantom", 500),
                                 ("4 maormer_raider(遠程)", ["maormer_raider"] * 4, None, 300),
                                 ("4 ice_wraith(冰)", ["ice_wraith"] * 4, None, 300),
                                 ("2 moor_witch+2 bandit(混合)", ["moor_witch", "moor_witch", "bandit", "bandit"], None, 300)):
        rs, rp = rate(_storm, gids, n=n), rate(_phant, gids, n=n)
        if home == "storm":      # 物理近戰:風暴之舞須不劣於幻影步(否則幻影步搶了它的招牌地盤)
            flag = " ✓各擅勝場" if rs <= rp else " ⚠幻影步搶了風暴之舞的物理近戰地盤"
        elif home == "phantom":  # 純元素群:幻影步須贏風暴之舞(否則幻影步退回「被上限遮蔽的死選項」)
            flag = " ✓各擅勝場" if rp < rs else " ⚠幻影步贏不了純元素群(淪為死選項)"
        else:
            flag = "  (資訊·不判定)"
        print(f"  {gname:26} 風暴之舞 {rs:5.1%}   幻影步 {rp:5.1%}{flag}")

    # R187 守衛:雜技 100「借風騰挪」(wind_step)vs 未選 vs 凌空奇襲(aerial_ambush)——閃避加成已撐滿的雜技閃避線構築
    # (改前凌風身法 +0.06 被 EVASION_BONUS_CAP 遮蔽成 0;改後借風騰挪的 +0.06 仍被 cap 擋→不繞上限,效果來自「誤中另一名敵人」)。
    # stam=True:普攻也耗體(借風騰挪每次耗 6 體力,長戰多敵會吃光體力;無此建模會高估)。判定:借風騰挪不得比「未選」更差超過 3pp
    # (回歸守衛);凌空奇襲在輕構築只有約 2~3pp、完整構築惰性(R187 設計代理實測)——僅供對照。
    # ⚠ 已知(設計代理量測):完整武僧打鬼火×8 借風騰挪比改前凌風身法差(體力稅);輕構築此守衛看不到,屬資訊,見 handoff R187。
    print("\n== R187 守衛:雜技100 借風騰挪 vs 未選 vs 凌空奇襲(閃避已撐滿的雜技線構築·普攻耗體;判定:借風騰挪不得比未選更差>3pp)==")
    _acro = {"acrobatics_25": "tumble_basics", "acrobatics_50": "tumbler", "acrobatics_75": "evasion", "light_armor_50": "lithe_evasion"}
    _mk = lambda opt: (lambda: assassin(light_armor=100, acrobatics=100,
                                        mastery_choices={**_acro, **({"acrobatics_100": opt} if opt else {})}))
    for gname, gids in (("4 bandit", ["bandit"] * 4), ("2 bandit+2 wolf", ["bandit", "bandit", "wolf", "wolf"]),
                        ("5 wolf(圍攻)", ["wolf"] * 5), ("4 moor_witch(純元素)", ["moor_witch"] * 4),
                        ("4 ice_wraith(冰)", ["ice_wraith"] * 4), ("4 maormer_raider(遠程)", ["maormer_raider"] * 4),
                        ("2 moor_witch+2 bandit(混合)", ["moor_witch", "moor_witch", "bandit", "bandit"]),
                        ("1 dremora_lord(solo)", ["dremora_lord"])):
        r0, ra, rm = (rate(_mk(o), gids, n=500, stam=True) for o in (None, "aerial_ambush", "wind_step"))
        flag = " ✓不劣於未選" if rm <= r0 + 0.03 else " ⚠借風騰挪反比未選更差"
        print(f"  {gname:28} 未選 {r0:5.1%}   凌空奇襲 {ra:5.1%}   借風騰挪 {rm:5.1%}{flag}")
