"""R193 徒手 100「崩勁釋放」(hand_to_hand_100 transcend_fist·`release` 子欄):
主動戰技 —— 把目標身上累積的失衡層一口氣釋放成一記重擊 ×(1+per_stack×層),命中清層、落空保留。
🔴 紅線:sneak_attack=False(永不吃偷襲倍率)·不累積/不觸發踉蹌擊倒·不重複疊 ramp·未選/非徒手/獸形/重甲 → 不開放且零 rng。
"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, magic, mastery, stats


def _monk(selected=True, armor=None, weapon="fists", h100="transcend_fist"):
    gd = get_gamedata()
    c = build_character(gd, name="僧", sex="m", race="khajiit", birthsign="warrior", class_id="warrior")
    c.skills["hand_to_hand"] = 100
    c.attributes["strength"] = 100
    c.weapon = weapon
    if armor:
        inventory.add_item(c, armor, 1); inventory.equip_armor(c, gd, armor)
    mastery.choose(c, gd, "hand_to_hand_50", "grapple")
    if selected:
        mastery.choose(c, gd, "hand_to_hand_100", h100)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.fatigue = c.max_fatigue
    return gd, c


def _dummy(gd, stacks=0):
    """巨血假人(不會死)+ 預堆失衡層數;bandit 非 solo、無物抗。"""
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.health = foe.max_health = 10 ** 7
    foe.resist = {}
    if stacks:
        magic.add_offbalance(foe, stacks)
    return foe


# --- 規格 / 解鎖 / 閘 ------------------------------------------------------------
def test_release_spec_only_when_selected():
    gd, c = _monk(selected=False)
    assert combat.release_spec(c, gd) == {}                    # 沒選 → 不開放
    gd, c = _monk(h100="iron_shirt")
    assert combat.release_spec(c, gd) == {}                    # 選了另一側 → 不開放
    gd, c = _monk()
    assert combat.release_spec(c, gd) == {"min_stacks": 4, "per_stack": 0.2, "fatigue": 20}


def test_release_ready_gates_each_branch_in_isolation():
    """逐一單獨驗每個閘(不靠 run() 整體過;見記憶 integration-test-vacuity)。"""
    gd, c = _monk()
    foe = _dummy(gd, stacks=5)
    assert combat.release_ready(c, foe, gd)                    # 對照組:全條件齊 → 可用
    assert not combat.release_ready(c, _dummy(gd, stacks=3), gd)       # 層數 < 門檻 4
    assert combat.release_ready(c, _dummy(gd, stacks=4), gd)           # 恰 4 層 → 可用(門檻含等號)
    c.fatigue = 19
    assert not combat.release_ready(c, foe, gd)                # 體力付不起額外耗體 20
    c.fatigue = c.max_fatigue
    dead = _dummy(gd, stacks=5); dead.health = 0
    assert not combat.release_ready(c, dead, gd)               # 目標已死
    assert not combat.release_ready(c, None, gd)               # 無目標不當機
    c.beast_form = True
    assert not combat.release_ready(c, foe, gd)                # 獸形(利爪)不開放
    c.beast_form = False
    gd2, blade = _monk(weapon="steel_dagger")
    assert not combat.release_ready(blade, _dummy(gd2, stacks=5), gd2)  # 持匕首 → wpn skill 非徒手
    gd3, heavy = _monk(armor="iron_cuirass")
    assert not combat.release_ready(heavy, _dummy(gd3, stacks=5), gd3)  # R103:穿重甲 → 失衡無效 → 不開放
    gd4, light = _monk(armor="leather_cuirass")
    assert combat.release_ready(light, _dummy(gd4, stacks=5), gd4)      # 輕甲仍可用(輕裝武僧)


def test_release_unready_is_zero_rng_and_none():
    """未選/未達標 → release_strike 回 None 且不消耗 rng、不耗體(既有構築 byte-identical)。"""
    for gd, c, foe in [(*_monk(selected=False), None), (*_monk(), None)]:
        foe = _dummy(gd, stacks=3 if c.mastery_choices.get("hand_to_hand_100") else 5)
        rng = RNG(7)
        before = rng._random.getstate()
        f0 = c.fatigue
        assert combat.release_strike(c, foe, gd, rng) is None
        assert rng._random.getstate() == before and c.fatigue == f0


# --- 效果:倍率 / 清層 / 落空保留 ------------------------------------------------
def test_release_damage_is_one_plus_per_stack_over_plain_hit():
    """同種子:釋放 5 層 ≈ 普攻(0 層)×(1+0.2×5)=2.0;用不吃 ramp 的 0 層普攻作基準。"""
    gd, c = _monk()
    ratios = []
    for seed in range(60):
        plain_foe = _dummy(gd)
        c.fatigue = c.max_fatigue
        p = combat.resolve_attack(c, plain_foe, gd, RNG(seed))
        rel_foe = _dummy(gd, stacks=5)
        c.fatigue = c.max_fatigue
        r = combat.release_strike(c, rel_foe, gd, RNG(seed))
        if p["hit"] and r["hit"] and p["damage"] > 10:
            ratios.append(r["damage"] / p["damage"])
    assert len(ratios) >= 20                                   # 防空測:要有足夠命中樣本
    assert all(1.85 <= x <= 2.15 for x in ratios), (min(ratios), max(ratios))


def test_release_hit_clears_stacks_and_miss_keeps_them():
    gd, c = _monk()
    hit_seen = miss_seen = False
    for seed in range(300):
        foe = _dummy(gd, stacks=5)
        c.fatigue = c.max_fatigue
        ev = combat.release_strike(c, foe, gd, RNG(seed))
        if ev["hit"]:
            assert magic.offbalance_stacks(foe) == 0           # 命中 → 層數歸零
            hit_seen = True
        else:
            assert magic.offbalance_stacks(foe) == 5           # 落空 → 層數保留
            miss_seen = True
        if hit_seen and miss_seen:
            break
    assert hit_seen and miss_seen                              # 兩條分支都真的走到(非隨機退路)


def test_release_does_not_accumulate_stagger_or_knockdown():
    """釋放那一擊不累積失衡、不觸發踉蹌/擊倒;對照組:同條件普攻會觸發控場(證明此測試有偵測力)。"""
    gd, c = _monk()
    ctl_released = ctl_plain = 0
    for seed in range(60):
        foe = _dummy(gd, stacks=8)
        c.fatigue = c.max_fatigue
        combat.release_strike(c, foe, gd, RNG(seed))
        ctl_released += combat.afflicted(foe, ("stagger", "paralyze"))
        foe2 = _dummy(gd, stacks=5)
        c.fatigue = c.max_fatigue
        combat.resolve_attack(c, foe2, gd, RNG(seed))          # 普攻:5+5→滿層 8 → 踉蹌/擊倒
        ctl_plain += combat.afflicted(foe2, ("stagger", "paralyze"))
    assert ctl_released == 0
    assert ctl_plain > 0                                       # 對照:普攻確實會施加控場


def test_release_call_contract_no_sneak_and_no_ramp_double_count():
    """spy resolve_attack:sneak_attack=False、offbalance_release=True、damage_factor=(1+0.2×層)(🔴 永不吃偷襲倍率)。"""
    gd, c = _monk()
    seen = {}
    orig = combat.resolve_attack
    def spy(*a, **k):
        seen.update(k)
        return orig(*a, **k)
    combat.resolve_attack = spy
    try:
        foe = _dummy(gd, stacks=8)
        combat.release_strike(c, foe, gd, RNG(3))
    finally:
        combat.resolve_attack = orig
    assert seen["sneak_attack"] is False and seen["offbalance_release"] is True
    assert abs(seen["damage_factor"] - (1.0 + 0.2 * 8)) < 1e-9
    # 不重複疊 ramp:釋放旗標下 0 層與 8 層同種子傷害相同
    a = orig(c, _dummy(gd, stacks=0), gd, RNG(11), offbalance_release=True)
    b = orig(c, _dummy(gd, stacks=8), gd, RNG(11), offbalance_release=True)
    assert a["damage"] == b["damage"]


def test_release_costs_fatigue_and_stack_cap_applies():
    gd, c = _monk()
    c.fatigue = c.max_fatigue
    foe = _dummy(gd, stacks=5)
    f0 = c.fatigue
    combat.release_strike(c, foe, gd, RNG(5))
    assert f0 - c.fatigue >= 20                                # 額外耗體 20 + 一般揮擊耗體
    # 層數上限:超出 MAX 的虛高層數不放大(夾 OFFBALANCE_MAX_STACKS)
    seen = {}
    orig = combat.resolve_attack
    def spy(*a, **k):
        seen.update(k); return orig(*a, **k)
    combat.resolve_attack = spy
    try:
        big = _dummy(gd); big.active_effects.append({"kind": "offbalance", "stacks": 99, "turns": 3})
        c.fatigue = c.max_fatigue
        combat.release_strike(c, big, gd, RNG(5))
    finally:
        combat.resolve_attack = orig
    assert seen["damage_factor"] <= 1.0 + 0.2 * formulas.OFFBALANCE_MAX_STACKS + 1e-9


# --- 資料/選單/存檔相容 -------------------------------------------------------------
def test_release_desc_numbers_match_data():
    """desc 與資料同步(內容準確性:desc 的門檻/係數/耗體必須等於 release 子欄)。"""
    gd = get_gamedata()
    node = next(n for n in gd.mastery if n["id"] == "hand_to_hand_100")
    opt = next(o for o in node["options"] if o["opt_id"] == "transcend_fist")
    r = opt["release"]
    assert f"{r['min_stacks']} 層" in opt["desc"]
    assert f"{int(round(r['per_stack'] * 100))}%" in opt["desc"]
    assert f"{r['fatigue']} 體力" in opt["desc"]
    assert "power" not in opt                                  # 取代舊 +10%:不再帶純數值傷害


def test_release_in_attack_bucket_and_opt_id_stable():
    from tesrpg import main
    assert main._COMBAT_BUCKETS["release"] == "攻擊"
    gd, c = _monk()
    assert c.mastery_choices["hand_to_hand_100"] == "transcend_fist"   # opt_id 不變(存檔相容)


# --- 對抗審查補(Sonnet 審查 + 變異驗證抓到的缺口)-------------------------------------
def test_release_gate_needs_extra_fatigue_plus_one_swing_and_pays_exactly():
    """審查 #1:閘須付得起「額外耗體 20 + 這一揮耗體」,且實付不被 max(0) 吞;並釘死 attack_cost 有被呼叫(變異 no_attack_cost)。"""
    gd, c = _monk()
    cost = combat.attack_fatigue_cost(c, gd)
    assert cost > 0
    foe = _dummy(gd, stacks=5)
    c.fatigue = 20 + cost - 0.01
    assert not combat.release_ready(c, foe, gd)                # 只夠額外耗體、不夠那一揮 → 不開放
    c.fatigue = 20 + cost
    assert combat.release_ready(c, foe, gd)                    # 恰好付得起 → 開放(含等號)
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    combat.release_strike(c, foe, gd, RNG(5))
    assert abs((f0 - c.fatigue) - (20 + cost)) < 1e-6, (f0 - c.fatigue, 20 + cost)   # 一分不少、一分不多
    # 邊界:體力恰 20+cost 放出後歸 0(不為負),且釋放前夠付、不被力竭罰
    c2 = _monk()[1]
    c2.fatigue = 20 + combat.attack_fatigue_cost(c2, gd)
    combat.release_strike(c2, _dummy(gd, stacks=5), gd, RNG(5))
    assert c2.fatigue == 0


def test_release_damage_mult_scales_and_is_evaluated_after_fatigue_is_paid():
    """審查 #2:damage_mult(R137 姿態稅)要乘進去;callable 在耗體之後才求值(變異 drop_mult)。"""
    gd, c = _monk()
    ratios = []
    for seed in range(60):
        c.fatigue = c.max_fatigue
        full = combat.release_strike(c, _dummy(gd, stacks=5), gd, RNG(seed), damage_mult=1.0)
        c.fatigue = c.max_fatigue
        half = combat.release_strike(c, _dummy(gd, stacks=5), gd, RNG(seed), damage_mult=0.5)
        if full["hit"] and half["hit"] and full["damage"] > 10:
            ratios.append(half["damage"] / full["damage"])
    assert len(ratios) >= 20 and all(0.4 <= x <= 0.6 for x in ratios), (len(ratios), min(ratios), max(ratios))
    seen = {}
    c.fatigue = c.max_fatigue
    f0 = c.fatigue

    def probe():
        seen["fat"] = c.fatigue
        return 1.0
    combat.release_strike(c, _dummy(gd, stacks=5), gd, RNG(1), damage_mult=probe)
    assert seen["fat"] <= f0 - 20                              # callable 求值時,額外耗體已扣


# main.py 接線(選單 / 選目標 / 派發)—— 對照 test_reckless_r191 的寫法
import io
from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)
from tesrpg.state import GameState, GameTime
import tesrpg.main as main


def _menu(c, foes):
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    cap = {}
    orig = ui.menu

    def _fake(title, options, *a, **k):
        cap["opts"] = list(options)
        return "flee"
    ui.menu = _fake
    try:
        main._choose_combat_action(st, get_gamedata(), foes, [])
    finally:
        ui.menu = orig
    return dict(cap["opts"])


def test_menu_offers_release_only_when_some_enemy_is_ready_and_says_the_cost():
    gd, c = _monk()
    ready, cold = _dummy(gd, stacks=5), _dummy(gd, stacks=3)
    label = _menu(c, [cold, ready])["release"]                 # 兩敵只一個達標 → 仍開放
    assert "崩勁" in label and "20%" in label and "20 體力" in label and "4 層" in label and "不吃偷襲" in label, label
    assert "release" not in _menu(c, [cold])                   # 無人達標 → 不出現
    c.fatigue = 20 + combat.attack_fatigue_cost(c, gd) - 0.5
    assert "release" not in _menu(c, [ready])                  # 體力不夠 → 不出現
    c.fatigue = c.max_fatigue
    assert "release" not in _menu(_monk(selected=False)[1], [_dummy(gd, stacks=5)])
    c.beast_form = True
    assert "release" not in _menu(c, [ready])


def test_choose_action_release_only_targets_ready_enemies():
    gd, c = _monk()
    ready, cold = _dummy(gd, stacks=5), _dummy(gd, stacks=1)
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    picks = iter(["release"])
    listed = {}
    orig = ui.menu

    def _fake(title, options, *a, **k):
        try:
            return next(picks)
        except StopIteration:
            listed["targets"] = [k2 for k2, _ in options]
            return options[0][0]
    ui.menu = _fake
    try:
        act = main._choose_combat_action(st, gd, [cold, ready], [])
    finally:
        ui.menu = orig
    assert act["type"] == "release" and act["target"] is ready, act     # 只有達標者可選(只剩 1 個 → 自動選定)


def test_run_battle_release_dispatch_hits_clears_stacks_pays_fatigue_and_stacks_the_stance_tax():
    gd, c = _monk()
    c.skills["block"] = 100
    foe = _dummy(gd, stacks=5)
    calls = []
    real = combat.resolve_attack

    def spy(att, dfn, gamedata, rng, *a, **k):
        ev = real(att, dfn, gamedata, rng, *a, **k)
        if att is c:
            calls.append((dict(k), ev))
        return ev
    n = {"i": 0}
    seen = {}

    def chooser(*a, **k):
        n["i"] += 1
        if n["i"] == 1:
            c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
            seen["fat0"] = c.fatigue
            return {"type": "release", "target": foe}
        seen["fat1"] = c.fatigue
        seen["stacks"] = magic.offbalance_stacks(foe)
        return {"type": "flee"}
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    orig_c, orig_r = main._choose_combat_action, combat.resolve_attack
    main._choose_combat_action, combat.resolve_attack = chooser, spy
    try:
        main.run_battle(st, gd, [foe])
    finally:
        main._choose_combat_action, combat.resolve_attack = orig_c, orig_r
    k, ev = calls[0]
    assert k["offbalance_release"] is True and k["sneak_attack"] is False
    tax = formulas.GUARD_STANCE_DAMAGE_TAX                     # R137:main 的 release 分支須把姿態稅疊進 damage_factor
    assert abs(k["damage_factor"] - (1.0 + 0.2 * 5) * tax) < 1e-9, k["damage_factor"]
    assert seen["stacks"] == (0 if ev["hit"] else 5)           # 命中清層 / 落空保留(經真實派發)
    assert seen["fat0"] - seen["fat1"] >= 20 - 5               # 額外耗 20 體(回合內有少量回復,留餘裕)


def run():
    for name in sorted(globals()):
        if name.startswith("test_"):
            globals()[name]()
