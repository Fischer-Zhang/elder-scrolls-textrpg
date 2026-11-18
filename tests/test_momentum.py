"""R187 解法二「氣勢」:殘影連襲(輕甲 100 phantom_step)的燃料——第一擊之外的每記殘影擊耗 1 點氣勢;
開戰 start(3)點,親手斬殺一名敵人 +per_kill(3)、夾 max(6);召喚爪牙(R134·不計擊殺)斬之不回。
氣勢 0 → 殘影連襲開不了(殘影留著)。為守終王牆:R186 殘影連襲讓武僧單挑達貢真身 9%→73%(handoff R187)。
🔴 紅線:不碰閃避上限/偷襲倍率;未選節點 → 全部 no-op、零 rng;氣勢是戰鬥內 active_effect(不存在 = start)→ 戰鬥邊界必歸零。"""
import io
from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, mastery, stats, magic
import tesrpg.main as main

gd = get_gamedata()


def _hero(choose=True):
    c = build_character(gd, name="勢", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
    c.skills.update(acrobatics=100, light_armor=100, blade=60, sneak=70)
    c.weapon = "steel_dagger"
    if choose:
        mastery.choose(c, gd, "light_armor_100", "phantom_step")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 10 ** 5
    return c


def _foe(tid="bandit", hp=10 ** 6, seed=1):
    f = combat.spawn_creature(gd, tid, RNG(seed))
    f.health = f.max_health = hp
    return f


def _stacks(c, n):
    c.active_effects[:] = [e for e in c.active_effects if e.get("kind") != "afterimage"]
    c.active_effects.append({"kind": "afterimage", "stacks": n, "turns": 99})


def test_getter_and_neutral_when_unchosen():
    assert mastery.momentum(_hero(choose=False), gd) == {} and combat.momentum(_hero(choose=False), gd) == 0
    assert not combat.momentum_enabled(_hero(choose=False), gd)
    assert combat._momentum_spend(_hero(choose=False), gd) is True                      # 未啟用 → 恆 True(行為同改前)
    c = _hero()
    assert mastery.momentum(c, gd) == {"start": 3, "per_kill": 3, "max": 6}
    assert combat.momentum(c, gd) == 3                                                  # 不存在 = start(懶建立)
    assert not any(e.get("kind") == "momentum" for e in c.active_effects)


def test_getter_gated_by_light_armor_tree():
    """R141:輕甲樹 perk,穿重甲不生效(氣勢隨殘影連襲一起失效,不留下免費額外出手)。"""
    from tesrpg.systems import inventory
    c = _hero()
    inventory.add_item(c, "steel_cuirass", 1); inventory.equip_armor(c, gd, "steel_cuirass")
    assert mastery.momentum(c, gd) == {} and combat.momentum(c, gd) == 0


def test_flurry_first_strike_free_rest_cost_and_gate():
    c = _hero()
    f = _foe()
    _stacks(c, 3); combat._momentum_set(c, gd, 1)
    assert combat.afterimage_ready(c, gd, 1)
    evs = list(combat.phantom_flurry(c, [f], gd, RNG(1)))
    assert len(evs) == 2 and combat.momentum(c, gd) == 0                                # 本體一擊 + 1 記殘影擊(氣勢只夠 1)
    _stacks(c, 3)
    assert not combat.afterimage_ready(c, gd, 1)                                        # 沒氣勢 → 連襲開不了(殘影留著)
    assert combat.afterimage_stacks(c) == 3


def test_flurry_full_momentum_allows_all_three_strikes_and_spends_two():
    c = _hero()
    _stacks(c, 3)
    evs = list(combat.phantom_flurry(c, [_foe()], gd, RNG(2)))
    assert len(evs) == 3 and combat.momentum(c, gd) == 3 - 2                            # 第一擊免費,其餘兩擊各 1 點


def test_flurry_stops_midway_when_momentum_runs_out_and_stacks_are_spent():
    c = _hero()
    _stacks(c, 3); combat._momentum_set(c, gd, 0)
    # afterimage_ready 已擋;若呼叫端硬呼叫,第一擊之後也出不了手,殘影照樣耗盡(耗盡即散)
    evs = list(combat.phantom_flurry(c, [_foe()], gd, RNG(3)))
    assert len(evs) == 1 and combat.afterimage_stacks(c) == 0


def test_kill_refuels_capped_and_summoned_do_not():
    c = _hero()
    combat._momentum_set(c, gd, 0)
    weak = _foe(hp=1); weak.armor_rating = 0
    for s in range(50):
        if not combat.is_alive(weak):
            break
        combat.resolve_attack(c, weak, gd, RNG(s))
    assert not combat.is_alive(weak) and combat.momentum(c, gd) == 3                    # 親手斬殺 +3
    combat.momentum_on_kill(c, weak, gd); combat.momentum_on_kill(c, weak, gd)
    assert combat.momentum(c, gd) == 6                                                  # 夾 max
    combat._momentum_set(c, gd, 0)
    minion = _foe(hp=1); minion.summoned = True
    combat.momentum_on_kill(c, minion, gd)
    assert combat.momentum(c, gd) == 0                                                  # 召喚爪牙不回氣勢


def test_only_player_kills_call_the_refuel_hook():
    """只有「玩家親手」斬殺才觸發回氣勢鉤子:敵人殺敵人(狂亂/借風騰挪誤傷)不算(spy 直驗呼叫次數)。"""
    calls = []
    orig = combat.momentum_on_kill
    combat.momentum_on_kill = lambda p, e, g: calls.append((p, e)) or orig(p, e, g)
    try:
        a, v = _foe(seed=1), _foe(hp=1, seed=2)
        v.armor_rating = 0
        for s in range(60):
            if not combat.is_alive(v):
                break
            combat.resolve_attack(a, v, gd, RNG(s))
        assert not combat.is_alive(v) and calls == [], "敵人殺敵人不得觸發回氣勢"
        c = _hero()
        w = _foe(hp=1, seed=3); w.armor_rating = 0
        for s in range(60):
            if not combat.is_alive(w):
                break
            combat.resolve_attack(c, w, gd, RNG(s))
        assert not combat.is_alive(w) and len(calls) == 1 and calls[0][0] is c
    finally:
        combat.momentum_on_kill = orig


def test_flurry_strikes_helper_matches_what_actually_happens():
    """選單/戰報顯示的出手記數 = 實際出手數(審查補:原顯示層數,氣勢不足時高估)。"""
    for stacks, mom in ((3, 3), (3, 1), (3, 0), (2, 5), (3, 2)):
        c = _hero()
        _stacks(c, stacks); combat._momentum_set(c, gd, mom)
        want = combat.phantom_flurry_strikes(c, gd)
        got = len(list(combat.phantom_flurry(c, [_foe()], gd, RNG(stacks * 10 + mom))))
        assert got == want == min(stacks, 1 + mom), (stacks, mom, got, want)
    assert combat.phantom_flurry_strikes(_hero(choose=False), gd) == 0                  # 未選 → 0 層


def test_menu_label_states_momentum_cost_and_real_strike_count():
    c = _hero()
    _stacks(c, 3); combat._momentum_set(c, gd, 1)
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    seen = {}
    orig = ui.menu
    ui.menu = lambda title, options, *a, **k: seen.setdefault("o", dict(options)) and "flee"
    try:
        main._choose_combat_action(st, gd, [_foe(), _foe(seed=2)], [])
    finally:
        ui.menu = orig
    label = seen["o"]["phantom_flurry"]
    assert "氣勢" in label and "2 記" in label and "現有 1" in label, label            # 層數 3、氣勢 1 → 實際 2 記


def test_run_battle_resets_momentum_at_entry_and_clears_on_exit():
    c = _hero()
    seen = {}
    foe = _foe(hp=9999)
    st = GameState(player=c, rng=RNG(3), time=GameTime())

    def act(*a, **k):
        seen.setdefault("m", combat.momentum(c, gd))
        seen.setdefault("tag", ui._status_tags(c))
        return {"type": "flee"}
    orig = main._choose_combat_action
    main._choose_combat_action = act
    try:
        for preserve in (False, True):
            seen.clear()
            c.active_effects.append({"kind": "momentum", "stacks": 0, "turns": 99})     # 上一場殘留(理論上不會有)
            main.run_battle(st, gd, [foe], preserve_buffs=preserve)
            assert seen["m"] == 3 and "氣勢×3" in seen["tag"], (preserve, seen)
            assert not any(e.get("kind") == "momentum" for e in c.active_effects), "離戰必清"
    finally:
        main._choose_combat_action = orig


def test_momentum_does_not_refill_by_expiring_in_long_fights():
    """氣勢效果不得被 tick_effects 磨到過期(過期 = 不存在 = 白白回滿 start;99 哨兵會在 >99 回合的長戰回滿)。"""
    c = _hero()
    combat._momentum_set(c, gd, 0)
    for _ in range(150):
        magic.tick_effects(c, gd)
    assert combat.momentum(c, gd) == 0


def test_wall_regression_flurry_dries_up_against_a_single_huge_foe():
    """終王牆守衛(單元版):對打不倒的巨物,連襲最多放行「開戰 3 點」的殘影擊,之後 afterimage_ready 恆 False
    ——不論殘影再怎麼堆。(整牆勝率見 handoff R187;sim_assassin 守衛段)"""
    c = _hero()
    boss = _foe(hp=10 ** 9)
    strikes = 0
    for rnd in range(40):
        _stacks(c, 3)
        if not combat.afterimage_ready(c, gd, 1):
            break
        strikes += len(list(combat.phantom_flurry(c, [boss], gd, RNG(rnd))))
    assert strikes == 5, strikes        # 開戰 3 點:第一輪 3 擊(1 免費+2 耗)剩 1 點;第二輪 2 擊(1 免費+1 耗)歸零;之後開不了
    assert not combat.afterimage_ready(c, gd, 1)
    assert combat.momentum(c, gd) == 0


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("OK")
