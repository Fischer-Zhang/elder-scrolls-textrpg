"""R187 雜技 100 凌風身法 → 借風騰挪(wind_step·misdirect):閃過敵攻 → 30% 機率讓那一擊(同一招·約七成力道)誤中另一名敵人。
每次耗 6 體力;場上須另有存活敵;遠程/元素招亦適用(補風暴之舞限物理近戰的缺口);走一般命中與元素抗性結算,on_hit 狀態不上同伴。
選項兼帶舊 +0.06 平調閃避(同源聚合,仍夾 EVASION_BONUS_CAP)。
🔴 紅線:不碰任何閃避上限;無里程碑/命中/無他敵/體力不足 → 於任何 rng 之前返回(既有構築逐位元組不變);
   solo 終王牆(含 BOSS 召喚爪牙)實測在雜訊內(handoff R187)。"""
import io
from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, mastery, stats
import tesrpg.main as main

gd = get_gamedata()
MISS = {"hit": False}


def _hero(choose=True):
    c = build_character(gd, name="風", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
    c.skills.update(acrobatics=100, blade=60, sneak=70)
    if choose:
        mastery.choose(c, gd, "acrobatics_100", "wind_step")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 10 ** 5
    return c


def _foes(n, tid="bandit", hp=10 ** 6):
    out = []
    for i in range(n):
        f = combat.spawn_creature(gd, tid, RNG(i))
        f.health = f.max_health = hp
        out.append(f)
    return out


class _CountRNG(RNG):
    n = 0

    def chance(self, p):
        type(self).n += 1
        return super().chance(p)

    def roll(self, lo, hi):
        type(self).n += 1
        return super().roll(lo, hi)

    def choice(self, seq):
        type(self).n += 1
        return super().choice(seq)


# ---------------------------------------------------------------- 資料 / getter / 聚合
def test_getter_and_bundle():
    c = _hero()
    assert mastery.misdirect(c, gd) == {"chance": 0.3, "factor": 0.7, "fatigue_cost": 6}
    assert abs(mastery.evasion_bonus(c, gd) - 0.06) < 1e-9       # 兼帶舊 +0.06 平調閃避
    assert mastery.misdirect(_hero(choose=False), gd) == {}
    assert mastery.evasion_bonus(_hero(choose=False), gd) == 0.0
    assert "misdirect" in mastery._IMPLEMENTED_KINDS


def test_flat_evasion_aggregates_and_caps():
    """🔴 同源聚合不遮蔽、仍夾上限:借風騰挪 +0.06 與輕盈 +0.05 相加(0.11);雜技線已撐滿 → 夾 EVASION_BONUS_CAP(不繞上限)。"""
    c = _hero()
    c.skills.update(light_armor=50)
    mastery.choose(c, gd, "light_armor_50", "lithe_evasion")
    assert abs(mastery.evasion_bonus(c, gd) - 0.11) < 1e-9
    for nid, oid in (("acrobatics_25", "tumble_basics"), ("acrobatics_50", "tumbler"), ("acrobatics_75", "evasion")):
        mastery.choose(c, gd, nid, oid)
    assert mastery.evasion_bonus(c, gd) == mastery.EVASION_BONUS_CAP     # 0.17+0.05 → 夾 0.15


# ---------------------------------------------------------------- misdirect_redirect 單元
def test_no_rng_when_not_applicable():
    foes = _foes(3)
    _CountRNG.n = 0
    r = _CountRNG(1)
    # 未選 / 命中 / 無他敵 / 體力不足:全部在任何 rng 之前返回(既有構築逐位元組不變)
    assert combat.misdirect_redirect(_hero(choose=False), foes[0], foes, gd, r, MISS, foes[0].attack) is None
    assert combat.misdirect_redirect(_hero(), foes[0], foes, gd, r, {"hit": True}, foes[0].attack) is None
    assert combat.misdirect_redirect(_hero(), foes[0], foes[:1], gd, r, MISS, foes[0].attack) is None
    c = _hero(); c.fatigue = 5
    assert combat.misdirect_redirect(c, foes[0], foes, gd, r, MISS, foes[0].attack) is None
    assert _CountRNG.n == 0


def test_redirect_hits_other_foe_not_self_pays_stamina():
    n_hit = 0
    for s in range(300):
        c = _hero(); foes = _foes(3)
        f0 = foes[0]
        hp0 = [f.health for f in foes]
        before = c.fatigue
        ev = combat.misdirect_redirect(c, f0, foes, gd, RNG(s), MISS, f0.attack)
        if ev is None:
            assert c.fatigue == before and [f.health for f in foes] == hp0   # 沒觸發 → 不扣體不傷
            continue
        n_hit += 1
        assert c.fatigue == before - 6
        assert foes[0].health == hp0[0]                                       # 絕不誤傷攻擊者自己
    assert 65 < n_hit < 115                                                    # ≈30% × 300


def test_redirect_forwards_same_attack_and_factor_and_picks_random_other_alive_foe():
    """審查補:誤傷必須是「同一招」×factor 0.7、對象在「另一名存活敵人」中隨機(不是固定第一個、不含屍體)。"""
    calls = []
    orig = combat.resolve_attack

    def spy(att, dfn, gdata, rng, **kw):
        calls.append((att, dfn, kw.get("attack"), kw.get("damage_factor")))
        return orig(att, dfn, gdata, rng, **kw)
    combat.resolve_attack = spy
    try:
        for s in range(300):
            c = _hero(); foes = _foes(4)
            for i, f in enumerate(foes):
                f.name = f"敵{i}"                                          # 固定名稱:跨種子可辨識受害者
            foes[1].health = 0                                                 # 名冊含屍體:不得選為受害者
            atk = foes[0].attack
            combat.misdirect_redirect(c, foes[0], foes, gd, RNG(s), MISS, atk)
        assert calls, "300 次內應觸發過誤傷"
        for att, dfn, a, f in calls:
            assert a is foes[0].attack or a == foes[0].attack, "必須是同一招(attack 轉傳)"
            assert f == 0.7, "力道必為 redirect_factor 0.7"
            assert dfn.health > 0 and dfn is not att, "受害者必須存活且不是攻擊者"
        assert {d.name for _, d, _, _ in calls} == {"敵2", "敵3"}, "「隨機」:兩名存活的他敵都應被選到過(不得恆選第一個、不得選到屍體敵1)"
    finally:
        combat.resolve_attack = orig


def test_dead_attacker_or_dead_player_no_redirect():
    foes = _foes(2)
    foes[0].health = 0
    assert combat.misdirect_redirect(_hero(), foes[0], foes, gd, RNG(1), MISS, foes[0].attack) is None
    c = _hero(); c.health = 0
    assert combat.misdirect_redirect(c, _foes(2)[0], _foes(2), gd, RNG(1), MISS, None) is None


def test_on_hit_status_not_applied_to_ally():
    # 帶 on_hit 控場/DoT 的怪被導向同伴:同伴身上不得出現新狀態(on_hit 僅對玩家/召喚物生效)
    for tid in ("moor_witch", "ice_wraith"):
        for s in range(100):
            c = _hero(); foes = _foes(2, tid)
            combat.misdirect_redirect(c, foes[0], foes, gd, RNG(s), MISS, foes[0].attack)
            assert foes[1].active_effects == [], tid


def test_element_resist_applies_to_victim():
    """元素招誤傷:抗該元素的同伴(冰魂免疫冰)傷害恆 0;無抗性的同伴(山賊)吃得到傷害 → 結算走一般元素抗性。"""
    def total(victim_tid):
        dmg = trig = 0
        for s in range(300):
            c = _hero()
            ghost = combat.spawn_creature(gd, "ice_wraith", RNG(1)); ghost.health = ghost.max_health = 10 ** 6
            v = combat.spawn_creature(gd, victim_tid, RNG(2)); v.health = v.max_health = 10 ** 6
            atk = next(a for a in ghost.attacks if a.get("element") == "frost")
            ev = combat.misdirect_redirect(c, ghost, [ghost, v], gd, RNG(s), MISS, atk)
            if ev is not None:
                trig += 1
                dmg += ev["damage"]
        return trig, dmg
    t_res, d_res = total("ice_wraith")
    t_bnd, d_bnd = total("bandit")
    assert t_res > 30 and t_bnd > 30
    assert d_res == 0 and d_bnd > 0


# ---------------------------------------------------------------- run_battle 整合(敵方階段接線)
def _run(script, foes, c):
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    n = {"i": 0}

    def _act(*a, **k):
        n["i"] += 1
        return script(n["i"])
    orig = main._choose_combat_action
    main._choose_combat_action = _act
    try:
        return main.run_battle(st, gd, foes)
    finally:
        main._choose_combat_action = orig


def test_run_battle_enemy_phase_calls_redirect_and_victims_take_damage():
    """玩家全程不攻擊(guard),敵人互不相識 → 任何敵人掉血都只可能來自借風騰挪的誤傷。"""
    c = _hero()
    foes = _foes(3)
    calls = []
    orig = combat.misdirect_redirect

    def spy(player, attacker, roster, gamedata, rng, ev, atk):
        out = orig(player, attacker, roster, gamedata, rng, ev, atk)
        calls.append((attacker.name, bool(ev.get("hit")), out is not None, roster is foes))
        return out
    combat.misdirect_redirect = spy
    try:
        _run(lambda i: {"type": "guard"} if i <= 14 else {"type": "flee"}, foes, c)
    finally:
        combat.misdirect_redirect = orig
    assert calls, "敵方階段必須對每次敵→玩家的出手呼叫 misdirect_redirect"
    assert all(roster for *_, roster in calls), "必須傳整個敵方名冊(roster 層),不是單一敵人"
    assert any(redirected for _, hit, redirected, _r in calls if not hit), "14 回合內至少發生過一次誤傷轉向"
    assert sum(f.max_health - f.health for f in foes) > 0, "玩家沒出手,敵人掉血必來自誤傷"


def test_run_battle_no_redirect_when_enemy_targets_an_ally():
    """審查補:`tgt is player` 閘——敵人打的是同伴時,玩家不得白扣體力/觸發誤傷。"""
    c = _hero()
    foes = _foes(3)
    ally = combat.spawn_creature(gd, "bandit", RNG(9)); ally.health = ally.max_health = 10 ** 6
    calls = []
    orig, orig_pick = combat.misdirect_redirect, combat.pick_player_side_target
    combat.misdirect_redirect = lambda *a, **k: calls.append(1) or orig(*a, **k)
    combat.pick_player_side_target = lambda player, allies, rng: ally
    fat0 = c.fatigue
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    n = {"i": 0}

    def _act(*a, **k):
        n["i"] += 1
        return {"type": "guard"} if n["i"] <= 8 else {"type": "flee"}
    o_act = main._choose_combat_action
    main._choose_combat_action = _act
    try:
        main.run_battle(st, gd, foes, carry_allies=[ally])
    finally:
        main._choose_combat_action, combat.misdirect_redirect, combat.pick_player_side_target = o_act, orig, orig_pick
    assert calls == [], "敵人打同伴 → 玩家與此無關,不得呼叫誤傷(否則白扣體力)"
    assert c.fatigue >= fat0 - 1, "玩家體力不得因同伴被攻擊而被扣"


def test_run_battle_without_milestone_never_redirects():
    c = _hero(choose=False)
    foes = _foes(3)
    _run(lambda i: {"type": "guard"} if i <= 10 else {"type": "flee"}, foes, c)
    assert all(f.health == f.max_health for f in foes), "沒選節點 → 敵人不會互傷(玩家也沒出手)"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("OK")
