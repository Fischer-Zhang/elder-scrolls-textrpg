"""R187 原型 P1:偵察 75「臨陣預判」(preempt)= 臨危備戰 alert_prep
(取代被 EVASION_BONUS_CAP 遮蔽成 0 的 +0.04 平調閃避)。

機制:潛近被識破(alerted)或遭伏擊(surprise)時,開戰前仍可倉促備戰 1 個準備動作;
與同節點「先機在握」互補(先機在握只在潛近成功且未被伏擊時算;兩者不疊加)。
🔴 紅線:零戰鬥數學改動(只動備戰預算)→ 不碰偷襲倍率/SOLO_SNEAK 夾;備戰仍在第 1 回合之前、不延長時效。"""
import io
from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg import formulas
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, mastery, stats
import tesrpg.main as main

gd = get_gamedata()


def _scout(choice=None, **skills):
    c = build_character(gd, name="探", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
    c.skills.update({"scout": 100, "sneak": 80, **skills})
    if choice:
        mastery.choose(c, gd, "scout_75", choice)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def _bandits(n=2):
    return [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(n)]


# ---------------------------------------------------------------- 資料 / getter
def test_option_is_alert_prep_with_flat_evasion_kept():
    c = _scout("preempt")
    assert mastery.alert_prep(c, gd) == 1
    assert abs(mastery.evasion_bonus(c, gd) - 0.04) < 1e-9       # 兼帶舊 +0.04 平調閃避(R187:使用者採「兼帶」建議,不讓未撐滿構築退步)
    assert mastery.evasion_bonus(_scout("vanguard"), gd) == 0.0   # 同節點另一選項無此加成
    assert "alert_prep" in mastery._IMPLEMENTED_KINDS
    assert mastery.alert_prep(_scout(), gd) == 0                 # 未選 → 0(中性)
    van = _scout("vanguard")
    assert mastery.alert_prep(van, gd) == 0 and mastery.prep_bonus(van, gd) == 1   # 同節點互斥:先機在握者無倉促備戰


def test_flat_evasion_aggregates_with_other_sources_and_caps():
    """🔴 同源聚合不遮蔽:臨陣預判兼帶 +0.04 與輕盈 +0.05 相加(0.09);雜技線+輕盈已撐滿 → 仍夾 EVASION_BONUS_CAP(不繞上限)。"""
    c = _scout("preempt")
    c.skills.update(light_armor=50, acrobatics=75)
    mastery.choose(c, gd, "light_armor_50", "lithe_evasion")
    assert abs(mastery.evasion_bonus(c, gd) - 0.09) < 1e-9
    for nid, oid in (("acrobatics_25", "tumble_basics"), ("acrobatics_50", "tumbler"), ("acrobatics_75", "evasion")):
        mastery.choose(c, gd, nid, oid)
    assert mastery.evasion_bonus(c, gd) == mastery.EVASION_BONUS_CAP    # 0.04+0.05+0.11=0.20 → 夾 0.15


def test_alert_prep_independent_of_prep_bonus_sources():
    """scout_100 決勝先機 / 諜報偵搜等 prep_bonus 來源不灌 alert_prep(兩條預算互斥,不疊加)。"""
    c = _scout("preempt")
    mastery.choose(c, gd, "scout_100", "battle_master")
    assert mastery.prep_bonus(c, gd) == 1 and mastery.alert_prep(c, gd) == 1


# ---------------------------------------------------------------- offer_battle 接線:成功/失敗/伏擊
def _offer(c, got_drop, surprise=False, foes=None):
    """跑 offer_battle:選「接戰」、潛近檢定強制成敗、攔下 run_battle 的參數。"""
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    seen = {}
    o_menu, o_try, o_run = ui.menu, combat.try_stealth_approach, main.run_battle
    ui.menu = lambda title, options, *a, **k: "fight"
    combat.try_stealth_approach = lambda *a, **k: got_drop
    main.run_battle = lambda state, gamedata, enemies, **k: seen.update(k) or "victory"
    try:
        main.offer_battle(st, gd, foes or _bandits(2), surprise=surprise)
    finally:
        ui.menu, combat.try_stealth_approach, main.run_battle = o_menu, o_try, o_run
    return seen


def test_success_keeps_calm_prep_and_failure_gets_hurried_prep():
    c = _scout("preempt")
    calm = formulas.prep_budget(c.skill("scout")) + mastery.prep_bonus(c, gd)
    ok = _offer(c, True)
    assert ok["prep_budget"] == calm and ok["alerted"] is False and ok["hurried_prep"] is False
    bad = _offer(c, False)
    assert bad["prep_budget"] == 1 and bad["alerted"] is True and bad["hurried_prep"] is True


def test_ambush_gets_hurried_prep_even_if_roll_succeeds():
    c = _scout("preempt")
    amb = _offer(c, True, surprise=True)          # 遭伏擊:先機在握不算(not surprise 閘),倉促備戰頂上
    assert amb["prep_budget"] == 1 and amb["hurried_prep"] is True


def test_unchosen_and_vanguard_get_nothing_on_failure():
    for choice in (None, "vanguard"):
        c = _scout(choice)
        bad = _offer(c, False)
        assert bad["prep_budget"] == 0, choice
        amb = _offer(c, True, surprise=True)
        assert amb["prep_budget"] == 0, choice


def test_vanguard_still_adds_one_on_calm_success():
    c = _scout("vanguard")
    base = formulas.prep_budget(c.skill("scout"))
    ok = _offer(c, True)
    assert ok["prep_budget"] == base + 1


# ---------------------------------------------------------------- 備戰階段訊息(如實:倉促 ≠ 從容)
def _prep_msgs(hurried):
    c = _scout("preempt")
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    msgs = []
    o_menu, o_msg = ui.menu, ui.message
    ui.menu = lambda *a, **k: None
    ui.message = lambda text, *a, **k: msgs.append(text)
    try:
        main._prep_phase(st, gd, _bandits(2), {"allies": []}, 2, hurried=hurried)
    finally:
        ui.menu, ui.message = o_menu, o_msg
    return "".join(msgs)


def test_prep_phase_message_distinguishes_hurried():
    assert "倉促" in _prep_msgs(True) and "從容" not in _prep_msgs(True)
    assert "從容" in _prep_msgs(False) and "倉促" not in _prep_msgs(False)
    # 訊息須中性:遭伏擊但潛近檢定成功時前文印過「搶得致命先機」,倉促訊息不得再說「被察覺」(審查抓到的自相矛盾)
    assert "被察覺" not in _prep_msgs(True)


# ---------------------------------------------------------------- 共用 helper / action_murder / run_battle 轉發(審查補:原本整條無測)
def test_approach_prep_helper_single_source():
    c = _scout("preempt")
    calm = formulas.prep_budget(c.skill("scout")) + mastery.prep_bonus(c, gd)
    assert main._approach_prep(c, gd, True) == (calm, False)
    assert main._approach_prep(c, gd, False) == (1, True)
    assert main._approach_prep(c, gd, True, surprise=True) == (1, True)          # 遭伏擊:先機在握不算
    assert main._approach_prep(_scout(), gd, False) == (0, True)                  # 未選 → 0(中性)


def test_action_murder_uses_helper_and_forwards_hurried():
    """潛殺:潛近失敗 → 倉促備戰(臨危備戰);成功 → 偵查備戰。action_murder 與 offer_battle 必走同一個 helper。"""
    import tests.test_hits as th
    from tesrpg.systems import quests
    for got_drop in (False, True):
        gd2, c, st = th._st()
        c.skills.update({"scout": 100, "sneak": 80})
        mastery.choose(c, gd2, "scout_75", "preempt")
        seen, helper_calls = {}, []
        o_menu, o_msg, o_conf, o_rule = ui.menu, ui.message, ui.confirm, ui.rule
        o_run, o_try, o_help = main.run_battle, combat.try_stealth_approach, main._approach_prep
        ui.message = lambda *a, **k: None
        ui.confirm = lambda *a, **k: True
        ui.rule = lambda *a, **k: None
        main.run_battle = lambda state, gamedata, enemies, **k: seen.update(k) or "victory"
        combat.try_stealth_approach = lambda *a, **k: got_drop
        main._approach_prep = lambda *a, **k: helper_calls.append(a[2:]) or o_help(*a, **k)
        try:
            c.location_id = "markarth"
            quests.accept_quest(c, gd2, "cintlead_markarth")
            main.action_murder(st, gd2, "cint_mark_a")
        finally:
            ui.menu, ui.message, ui.confirm, ui.rule = o_menu, o_msg, o_conf, o_rule
            main.run_battle, combat.try_stealth_approach, main._approach_prep = o_run, o_try, o_help
        assert helper_calls, "action_murder 必須走 _approach_prep(單一出處)"
        calm = formulas.prep_budget(c.skill("scout")) + mastery.prep_bonus(c, gd2)
        if got_drop:
            assert seen["prep_budget"] == calm and seen["hurried_prep"] is False
        else:
            assert seen["prep_budget"] == 1 and seen["hurried_prep"] is True


def test_run_battle_forwards_hurried_flag_to_prep_phase():
    """run_battle 必須把 hurried_prep 轉給 _prep_phase(審查抓到:漏轉 → 遊戲內永遠顯示「從容」)。"""
    for hurried in (True, False):
        c = _scout("preempt")
        st = GameState(player=c, rng=RNG(1), time=GameTime())
        got = {}
        o_prep, o_act = main._prep_phase, main._choose_combat_action
        main._prep_phase = lambda state, gamedata, enemies, battle, budget, hurried=False: got.update(h=hurried, b=budget)
        main._choose_combat_action = lambda *a, **k: {"type": "flee"}
        try:
            main.run_battle(st, gd, _bandits(1), prep_budget=2, hurried_prep=hurried)
        finally:
            main._prep_phase, main._choose_combat_action = o_prep, o_act
        assert got == {"h": hurried, "b": 2}, (hurried, got)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("OK")
