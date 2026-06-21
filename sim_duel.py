"""各 build 互鬥(duel)勝率 —— 非正典(遊戲無 PvP);純相對戰力探針。手動跑:PYTHONPATH=. python3 sim_duel.py

⚠ 重大保真度警告(數字只是好奇心,非平衡訊號):
  - 遊戲**無 PvP**;戰鬥引擎是 PvE 不對稱設計。對 Character(非 solo-boss creature)**SOLO_SNEAK 夾不生效**
    → 偷襲開場可達 ~468 傷(實測)一擊秒任何 build。故「埋伏(ambush)」對局退化成「誰先偷襲誰贏」。
  - 此處主表 = **正面對決(face-off)**:無回合1免費偷襲;潛行 build 仍可靠隱遁(vanish)中途重入潛行→
    **無夾偷襲**(對 build 不受 solo 夾)→ 隱遁成功即可能一擊。先手以「半數對局各先手」公平化。
  - per-build policy 沿用 sim_builds(法師/戰法改讀對手 entity_resist);法師開場石肌、低血治療;戰士純輸出。
  - 排除戴德拉誓福 + 自附魔(同 sim_builds)。逾時(60 回合)以剩血% 高者判勝。
"""
import sim_builds as S
from tesrpg.systems import combat, magic, stats
from tesrpg import formulas
from tesrpg.rng import RNG

gd = S.gd


def _opp_res(opp, el):
    return magic.entity_resist(opp, gd).get(el, 0) if el else 0


def _mage_act(c, opp, rng, st):
    if not st.get("buffed") and magic.can_cast(c, gd, "stoneflesh"):
        st["buffed"] = True; magic.cast(c, gd, "stoneflesh", rng); return
    if c.health < c.max_health * 0.35:
        for h in ("close_wounds", "heal"):
            if magic.can_cast(c, gd, h):
                magic.cast(c, gd, h, rng); return
    best, bev = None, -1.0
    for sid in S._MAGE_DMG:
        if not magic.can_cast(c, gd, sid):
            continue
        eff = gd.spells[sid]["effect"]
        ev = eff.get("magnitude", 0) * (1 - _opp_res(opp, eff.get("element")) / 100.0)
        if ev > bev:
            best, bev = sid, ev
    if best:
        magic.cast(c, gd, best, rng, target=opp, enemies=[opp], battle={"allies": []})
    else:
        combat.player_attack_cost(c, gd); combat.resolve_attack(c, opp, gd, rng)


def _bm_act(c, opp, rng, st):
    if c.health < c.max_health * 0.35 and magic.can_cast(c, gd, "close_wounds"):
        magic.cast(c, gd, "close_wounds", rng); return
    pf = (0.7 + c.skill("destruction") / 150.0) * formulas.intelligence_spell_potency(c.attr("intelligence"))
    best, bd = None, 0.0
    for sid in S._BM_DMG:
        if not magic.can_cast(c, gd, sid):
            continue
        eff = gd.spells[sid]["effect"]
        d = eff.get("magnitude", 0) * pf * (1 - _opp_res(opp, eff.get("element")) / 100.0)
        if d > bd:
            best, bd = sid, d
    if best and bd >= 45:
        magic.cast(c, gd, best, rng, target=opp, enemies=[opp], battle={"allies": []}); return
    combat.player_attack_cost(c, gd); combat.resolve_attack(c, opp, gd, rng)


def _sneak_act(c, opp, rng, st):
    if c.health < c.max_health * 0.45 and combat.can_vanish(c, gd) \
            and combat.try_vanish(c, 1, st["vanish"], rng, gd):
        st["vanish"] += 1; st["opening"] = True; st["skip"] = True; return   # 隱遁:躲過 + 重置偷襲(對 build 無夾)
    combat.player_attack_cost(c, gd)
    combat.resolve_attack(c, opp, gd, rng, sneak_attack=st["opening"])
    st["opening"] = False


def _atk_act(c, opp, rng, st):
    combat.player_attack_cost(c, gd); combat.resolve_attack(c, opp, gd, rng)


POLICY = {"assassin": _sneak_act, "archer": _sneak_act, "warrior_1H": _atk_act,
          "warrior_2H": _atk_act, "mage": _mage_act, "battlemage": _bm_act}


def _post(c):
    mr = formulas.magicka_regen_combat(c.attr("willpower"))
    if mr and c.birthsign != "atronach" and c.magicka < c.max_magicka:
        c.magicka = min(c.max_magicka, c.magicka + mr)
    magic.tick_effects(c, gd); stats.clamp_resources(c)


def duel(nameA, nameB, seed, a_first, ambush=False, max_rounds=60):
    b = {"A": S.BUILDS[nameA](), "B": S.BUILDS[nameB]()}
    nm = {"A": nameA, "B": nameB}
    st = {"A": {"opening": ambush and a_first, "vanish": 0, "skip": False},
          "B": {"opening": ambush and not a_first, "vanish": 0, "skip": False}}
    rng = RNG(seed)
    seq = ["A", "B"] if a_first else ["B", "A"]
    for _ in range(max_rounds):
        hidden = {"A": False, "B": False}
        for k in seq:
            ok = "B" if k == "A" else "A"
            c, opp = b[k], b[ok]
            if c.health <= 0 or opp.health <= 0 or hidden[ok]:
                continue                      # 對手已死/已隱遁 → 我這回合不出手
            c._evade_counter_used = False
            st[k]["skip"] = False
            if not magic.is_incapacitated(c):
                POLICY[nm[k]](c, opp, rng, st[k])
            if st[k]["skip"]:
                hidden[k] = True              # 我隱遁了 → 本回合對手撲空
        _post(b["A"]); _post(b["B"])
        if b["A"].health <= 0 and b["B"].health <= 0:
            return "draw"
        if b["B"].health <= 0:
            return "A"
        if b["A"].health <= 0:
            return "B"
    return "A" if b["A"].health / b["A"].max_health >= b["B"].health / b["B"].max_health else "B"


def winrate(nameA, nameB, n=200, ambush=False):
    """A 對 B 的勝率;先手公平化(半數 A 先手、半數 B 先手)。"""
    wins = 0
    for s in range(n):
        wins += duel(nameA, nameB, s, a_first=(s % 2 == 0), ambush=ambush) == "A"
    return wins / n


if __name__ == "__main__":
    names = list(S.BUILDS)
    print("== build 互鬥勝率矩陣(face-off·無開場偷襲·先手公平化·n=200;列=攻方 A vs 欄=B)==")
    print("   ⚠ 非正典(無 PvP);對 build 無 SOLO_SNEAK 夾 → 隱遁→偷襲可一擊。對角=鏡像(~50%)。")
    print(f"  {'A \\\\ B':12}" + "".join(f"{n:>11}" for n in names))
    for a in names:
        row = "".join(f"{winrate(a, b):>10.0%} " for b in names)
        print(f"  {a:12}{row}")
    print("\n== 參考:ambush(潛行 build 拿到開場偷襲·固定先手)→ 勝率(展示退化:開場即秒)==")
    for a in ("assassin", "archer"):
        for d in ("mage", "warrior_1H", "warrior_2H"):
            w = sum(duel(a, d, s, a_first=True, ambush=True) == "A" for s in range(150)) / 150
            print(f"  {a} 開場偷襲 vs {d}: {w:.0%} 勝")
