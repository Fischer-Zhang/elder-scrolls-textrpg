"""R191 刀劍 100「搏命連斬」(opt_id 仍是 savage;取代舊的 +12% 傷害/回噬 5% 純數值)。

機制(使用者 2026-11 拍板「以攻對攻」,第二記係數 0.6):主動戰技——對同一目標連斬兩記(第 2 記 ×0.6),另耗 30 體力;
連斬後目標若沒倒下且能行動 → 立刻趁隙還擊你一記,這一記你的閃避歸零、格擋姿態/盾牆卸力與格擋反擊不計
(閃過才有的閃身反打/殘影也不觸發、不練雜技)。被恐懼/麻痺/狂亂的目標不還擊。
🔴 紅線:每記 sneak_attack=False(永不吃偷襲倍率 → 不碰 SOLO_SNEAK 夾)、走 resolve_attack(照吃護甲/物抗);
   `overextended` 只存在於那一記還擊之內(不跨回合/不入常駐,例外也不殘留);未選 → 零 rng、既有構築 byte-identical。"""
import io
from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg import formulas
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, mastery, progression, stats
import tesrpg.main as main

gd = get_gamedata()
SPEC = {"strikes": 2, "factor": 0.6, "fatigue": 30}


def _swordsman(choose=True, **skills):
    c = build_character(gd, name="劍", sex="male", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(blade=100, **skills)
    c.weapon = "steel_sword"
    if choose:
        mastery.choose(c, gd, "blade_100", "savage")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 10 ** 5          # 不死(只驗機制,不測存活)
    return c


def _bandit(i=0, hp=10 ** 6, name=None):
    f = combat.spawn_creature(gd, "bandit", RNG(i))
    f.health = f.max_health = hp
    if name:
        f.name = name
    return f


def _ovx_effects(c):
    return [e for e in c.active_effects if e.get("kind") == "overextended"]


class _Patch:
    """暫時換掉 module 屬性(測完還原)。"""
    def __init__(self, *triples):
        self.triples = triples

    def __enter__(self):
        self.saved = [(o, n, getattr(o, n)) for o, n, _ in self.triples]
        for o, n, v in self.triples:
            setattr(o, n, v)

    def __exit__(self, *a):
        for o, n, v in self.saved:
            setattr(o, n, v)


# ---------------------------------------------------------------- 資料 / getter
def test_option_is_active_skill_not_flat_numbers():
    node = next(n for n in gd.mastery if n["id"] == "blade_100")
    opt = next(o for o in node["options"] if o["opt_id"] == "savage")        # opt_id 不變(存檔相容)
    assert opt["name"] == "搏命連斬" and opt["reckless"] == SPEC, opt
    assert "power" not in opt and "recoil" not in opt, "舊的 +12%/回噬 5% 已整個拿掉"
    c = _swordsman()
    assert mastery.reckless(c, gd, "blade") == SPEC
    assert mastery.reckless(c, gd, "blunt") == {} and mastery.reckless(c, gd, None) == {}    # target 不符 → 不開放
    assert mastery.reckless(_swordsman(choose=False), gd, "blade") == {}                    # 未選 → 空
    wm = mastery.weapon_mod(c, gd, "blade")
    assert not wm.get("power") and not wm.get("recoil"), wm                                  # 不再貢獻被動數值


def test_old_saves_with_savage_chosen_still_load_and_work():
    """存檔相容:舊檔已選 savage(opt_id 不變)→ 讀進來即得到新戰技,不需遷移。"""
    c = _swordsman()
    c2 = type(c).from_dict(c.to_dict())
    assert c2.mastery_choices.get("blade_100") == "savage"
    assert mastery.reckless(c2, gd, "blade") == SPEC


def test_ready_gate_choice_weapon_fatigue_and_beast_form():
    c = _swordsman()
    assert combat.reckless_ready(c, gd)
    assert not combat.reckless_ready(_swordsman(choose=False), gd)
    c.fatigue = 29
    assert not combat.reckless_ready(c, gd), "體力不足額外耗體 30 → 不開放"
    c.fatigue = 30
    assert combat.reckless_ready(c, gd)
    c.weapon = "iron_mace"                                       # 鈍器 → wpn_skill 不是 blade
    assert not combat.reckless_ready(c, gd)
    c.weapon = "steel_sword"
    c.beast_form = True                                          # 獸形無刀劍
    assert not combat.reckless_ready(c, gd)


# ---------------------------------------------------------------- 連斬本體
def test_flurry_two_strikes_factor_no_sneak_then_counter_with_exposure():
    c = _swordsman()
    f = _bandit(1)
    real = combat.resolve_attack
    calls = []

    def spy(att, dfn, gamedata, rng, *a, **k):
        calls.append({"player": att is c, "sneak": k.get("sneak_attack"), "factor": k.get("damage_factor"),
                      "ovx": combat._overextended(c)})
        return real(att, dfn, gamedata, rng, *a, **k)
    f0 = c.fatigue
    with _Patch((combat, "resolve_attack", spy)):
        evs = list(combat.reckless_flurry(c, f, gd, RNG(5)))
    assert [k for k, _ in evs] == ["strike", "strike", "counter"], evs
    assert [x["player"] for x in calls] == [True, True, False]
    assert [x["sneak"] for x in calls[:2]] == [False, False], "🔴 每記 sneak_attack=False(永不吃偷襲倍率)"
    assert [x["factor"] for x in calls[:2]] == [1.0, 0.6], "第 2 記武器傷 ×0.6"
    assert [x["ovx"] for x in calls] == [False, False, True], "門戶大開只存在於那一記還擊之內"
    assert not _ovx_effects(c), "還擊後立即移除(不跨回合)"
    base = _swordsman()
    b0 = base.fatigue
    combat.player_attack_cost(base, gd)
    attack_cost = b0 - base.fatigue
    assert attack_cost > 0 and f0 - c.fatigue == attack_cost + SPEC["fatigue"], "一次攻擊體力 + 額外 30(不是每記各耗)"


def test_no_counter_when_target_dies_or_is_helpless():
    # 目標在連斬中被斬殺 → 沒有還擊,也不繼續出第 2 記以外的任何動作
    c = _swordsman()
    killed = False
    for s in range(1, 80):
        f = _bandit(s, 1)
        f.armor_rating = 0
        evs = list(combat.reckless_flurry(c, f, gd, RNG(s)))
        if any(ev["defender_dead"] for k, ev in evs if k == "strike"):
            assert all(k == "strike" for k, _ in evs), "斬殺 → 無還擊"
            assert len(evs) <= 2
            killed = True
            break
        c.fatigue = c.max_fatigue
    assert killed, "找不到會斬殺的種子"
    # 被恐懼/麻痺/狂亂 → 沒有門戶可趁
    for kind in ("fear", "paralyze", "frenzied"):
        c = _swordsman()
        f = _bandit(2)
        assert magic.apply_control(f, kind, gd, RNG(1), turns=5) == "applied", kind
        evs = list(combat.reckless_flurry(c, f, gd, RNG(3)))
        assert evs and all(k == "strike" for k, _ in evs), f"{kind} 中的目標不還擊:{evs}"


def test_flurry_noop_without_choice_or_dead_target_and_free():
    c = _swordsman(choose=False)
    fat = c.fatigue
    assert list(combat.reckless_flurry(c, _bandit(1), gd, RNG(1))) == [] and c.fatigue == fat   # 未選 → 不耗體、零動作
    c = _swordsman()
    f = _bandit(1)
    f.health = 0
    fat = c.fatigue
    assert list(combat.reckless_flurry(c, f, gd, RNG(1))) == [] and c.fatigue == fat           # 死目標 → 不耗體


def test_exposure_never_survives_an_exception_in_the_counter():
    c = _swordsman()
    f = _bandit(1)
    real = combat.resolve_attack

    def boom(att, dfn, gamedata, rng, *a, **k):
        if att is not c:
            raise RuntimeError("counter blew up")
        return real(att, dfn, gamedata, rng, *a, **k)
    with _Patch((combat, "resolve_attack", boom)):
        try:
            list(combat.reckless_flurry(c, f, gd, RNG(1)))
        except RuntimeError:
            pass
        else:
            raise AssertionError("例外應照常上拋")
    assert not _ovx_effects(c), "例外也不得殘留 overextended(try/finally)"


# ---------------------------------------------------------------- 還擊期間的「門戶大開」
def _ovx_on(c):
    c.active_effects.append({"kind": "overextended", "turns": 1})


def test_evasion_is_zeroed_only_while_exposed():
    seen = []

    def spy(*a, **k):
        seen.append(k.get("defender_evasion"))
        return 0.5
    c = _swordsman(acrobatics=100)
    f = _bandit(1)
    with _Patch((formulas, "hit_chance", spy)):
        combat.resolve_attack(f, c, gd, RNG(1))
        _ovx_on(c)
        combat.resolve_attack(f, c, gd, RNG(1))
    assert seen[0] > 0, "基準:雜技 100 的玩家有閃避"
    assert seen[1] == 0.0, "🔴 門戶大開 → 閃避歸零(只歸零玩家自己的;命中上下限不動)"


def test_guard_stance_and_shield_wall_mitigation_pause_while_exposed():
    c = _swordsman(block=100)
    c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
    c.active_effects.append({"kind": "shield_wall", "turns": 3, "mitigation": 0.4})
    assert combat._guard_stance_factor(c, None, gd) < 1.0 and abs(combat._shield_wall_factor(c) - 0.6) < 1e-9
    _ovx_on(c)
    assert combat._guard_stance_factor(c, None, gd) == 1.0, "姿態卸力不計"
    assert combat._shield_wall_factor(c) == 1.0, "盾牆卸力不計"
    # 非玩家防守者的 _shield_wall_factor 不受影響(怪物沒有 overextended)
    assert combat._shield_wall_factor(_bandit(1)) == 1.0


def test_block_riposte_and_dodge_rewards_are_skipped_while_exposed():
    calls = {"riposte": 0, "xp": 0, "bxp": 0, "image": 0, "evade": 0}

    def riposte(*a, **k):
        calls["riposte"] += 1
        return {}

    def xp(c, gamedata, skill, *a, **k):
        calls["xp"] += skill == "acrobatics"
        calls["bxp"] += skill == "block"
        return []

    def image(*a, **k):
        calls["image"] += 1

    def evade(*a, **k):
        calls["evade"] += 1
        return None
    patches = (combat.mastery, "block_riposte", riposte), (combat.progression, "use_skill", xp), \
              (combat, "afterimage_gain", image), (combat.mastery, "on_evade", evade)

    def run(exposed, chance):
        for k in calls:
            calls[k] = 0
        c = _swordsman(block=100)
        c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
        if exposed:
            _ovx_on(c)
        with _Patch(*patches, (formulas, "hit_chance", lambda *a, **k: chance)):
            for s in range(1, 40):
                ev = combat.resolve_attack(_bandit(s), c, gd, RNG(s))
                if (chance == 1.0 and ev["hit"]) or (chance == 0.0 and not ev["hit"]):
                    return dict(calls)
        raise AssertionError("找不到符合的種子")
    base_hit, ovx_hit = run(False, 1.0), run(True, 1.0)
    assert base_hit["riposte"] >= 1 and ovx_hit["riposte"] == 0, "格擋反擊:基準會觸發、門戶大開時不觸發"
    assert base_hit["bxp"] >= 1 and ovx_hit["bxp"] == 0, "門戶大開的還擊沒有舉盾 → 不練 block(基準:姿態中被命中會練)"
    base_miss, ovx_miss = run(False, 0.0), run(True, 0.0)
    assert base_miss["xp"] == 1 and base_miss["image"] == 1 and base_miss["evade"] == 1      # 基準:落空 = 你閃過
    assert ovx_miss == {"riposte": 0, "xp": 0, "bxp": 0, "image": 0, "evade": 0}, \
        "門戶大開時敵人落空是對方失手、不是你閃過 → 不練雜技、不凝殘影、不觸發閃身反打"


# ---------------------------------------------------------------- 選單 / 戰鬥接線
def _menu_keys(c, foes):
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    captured = {}
    orig = ui.menu

    def _fake(title, options, *a, **k):
        captured["opts"] = list(options)
        return "flee"
    ui.menu = _fake
    try:
        main._choose_combat_action(st, gd, foes, [])
    finally:
        ui.menu = orig
    return dict(captured["opts"])


def test_menu_offers_reckless_only_when_ready_and_says_the_cost():
    c = _swordsman()
    foes = [_bandit(1), _bandit(2)]
    opts = _menu_keys(c, foes)
    label = opts["reckless"]
    assert "搏命連斬" in label and "60%" in label and "30" in label and "不吃偷襲" in label and "還擊" in label, label
    assert main._COMBAT_BUCKETS["reckless"] == "攻擊"
    c.fatigue = 10
    assert "reckless" not in _menu_keys(c, foes)
    assert "reckless" not in _menu_keys(_swordsman(choose=False), foes)
    c = _swordsman()
    c.beast_form = True
    assert "reckless" not in _menu_keys(c, foes)


def test_choose_action_returns_reckless_with_a_target():
    c = _swordsman()
    foe = _bandit(1)
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    picks = iter(["reckless"])
    orig = ui.menu

    def _fake(title, options, *a, **k):
        try:
            return next(picks)
        except StopIteration:
            return options[0][0]        # 選目標時取第一個
    ui.menu = _fake
    try:
        act = main._choose_combat_action(st, gd, [foe], [])
    finally:
        ui.menu = orig
    assert act["type"] == "reckless" and act["target"] is foe, act


def _drive(c, script, foe=None):
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    foe = foe if foe is not None else _bandit(7, 9999)
    n = {"i": 0}

    def _act(*a, **k):
        n["i"] += 1
        return script(n["i"], foe) or {"type": "flee"}
    orig = main._choose_combat_action
    main._choose_combat_action = _act
    try:
        res = main.run_battle(st, gd, [foe])
    finally:
        main._choose_combat_action = orig
    return res, foe


def test_run_battle_reckless_dispatch_hits_costs_fatigue_and_leaves_no_residue():
    c = _swordsman()
    seen = {}

    def script(i, foe):
        if i == 1:
            seen["fat0"] = c.fatigue
            return {"type": "reckless", "target": foe}
        if i == 2:
            seen["fat1"] = c.fatigue
            seen["ovx"] = list(_ovx_effects(c))
            seen["hp"] = c.health
    res, foe = _drive(c, script)
    assert foe.health < 9999, "連斬應造成傷害(兩記至少中 1 次;種子固定)"
    assert seen["fat0"] - seen["fat1"] >= SPEC["fatigue"] - 5, "額外耗 30 體力(回合內有少量回復,留餘裕)"
    assert seen["ovx"] == [], "門戶大開不跨回合"
    assert not _ovx_effects(c)


# ---------------------------------------------------------------- 對抗審查補(Sonnet 審查 + 變異驗證抓到的缺口)
def test_player_killed_by_the_counter_ends_the_battle_without_companion_revival():
    """審查 B1:還擊在玩家階段打死玩家 → 同伴階段不得再行動(治療型同伴的援護術曾把 HP=0 的玩家救活)。"""
    real_support = magic.companion_support_act
    found_death = False
    for seed in range(1, 60):
        c = _swordsman()
        c.health = 3
        foe = _bandit(seed)
        st = GameState(player=c, rng=RNG(seed), time=GameTime())
        n = {"i": 0, "hp_at_support": []}

        def chooser(*a, **k):
            n["i"] += 1
            return {"type": "reckless", "target": foe} if n["i"] == 1 else {"type": "flee"}

        def support(comp, player, allies, gd_):
            n["hp_at_support"].append(player.health)
            return real_support(comp, player, allies, gd_)
        with _Patch((main, "_choose_combat_action", chooser), (magic, "companion_support_act", support)):
            res = main.run_battle(st, gd, [foe], companions=["hedge_mage"])
        assert all(hp > 0 for hp in n["hp_at_support"]), f"seed {seed}: 玩家 HP≤0 時同伴仍行動 {n['hp_at_support']}"
        if res == "dead" and n["i"] == 1:
            found_death = True
            assert c.health <= 0, "致死後不得被治活"
    assert found_death, "找不到『還擊在玩家階段打死玩家』的種子(測試空轉)"


def test_counter_hit_can_infect_just_like_an_enemy_phase_hit():
    """審查 B2:還擊是真實的一擊(resolve_attack 已擲傳染 rng),結果不得被丟棄 —— 與敵方階段同一條分派。"""
    from tesrpg.systems import lycanthropy
    real_infect = lycanthropy.infect
    found = False
    for seed in range(1, 40):
        c = _swordsman()
        foe = combat.spawn_creature(gd, "werewolf", RNG(seed))
        foe.health = foe.max_health = 10 ** 6
        for atk in [foe.attack, *getattr(foe, "attacks", [])]:
            atk["infect"] = 1.0
            atk["infect_kind"] = "lycanthropy"
        seq = []
        n = {"i": 0}

        def chooser(*a, **k):
            n["i"] += 1
            return {"type": "reckless", "target": foe} if n["i"] == 1 else {"type": "flee"}

        def on_event(e, g):
            if getattr(e.get("defender"), "name", e.get("defender")) == c.name:
                seq.append(("hit_on_player", bool(e.get("infected"))))

        def infect(*a, **k):
            seq.append(("infect",))
            return real_infect(*a, **k)
        st = GameState(player=c, rng=RNG(seed), time=GameTime())
        with _Patch((main, "_choose_combat_action", chooser), (ui, "combat_event", on_event), (lycanthropy, "infect", infect)):
            main.run_battle(st, gd, [foe])
        if seq and seq[0] == ("hit_on_player", True):          # 第一個打在玩家身上的事件 = 還擊(玩家階段)
            assert len(seq) > 1 and seq[1] == ("infect",), f"還擊後應立刻走傳染分派,實際 {seq[:3]}"
            found = True
            break
    assert found, "找不到『還擊帶傳染標記』的種子(測試空轉)"


def test_flurry_never_swings_again_after_the_first_strike_kills():
    """審查 M02:第一記已斬殺 → 第二記不得再砍屍體(否則 momentum_on_kill 會重複給氣勢)。"""
    real = combat.resolve_attack
    for s in range(1, 150):
        c = _swordsman()
        f = _bandit(s, 1)
        f.armor_rating = 0
        calls = []

        def spy(att, dfn, gamedata, rng, *a, **k):
            calls.append(att is c)
            return real(att, dfn, gamedata, rng, *a, **k)
        with _Patch((combat, "resolve_attack", spy)):
            evs = list(combat.reckless_flurry(c, f, gd, RNG(s)))
        if evs and evs[0][1]["defender_dead"]:
            assert calls == [True] and [k for k, _ in evs] == ["strike"], (calls, evs)
            return
    raise AssertionError("找不到第一記就斬殺的種子(測試空轉)")


def test_dispatch_stacks_the_guard_stance_tax_on_both_strikes():
    """審查 M08:main 的 reckless 分支須把 R137 格擋姿態攻擊稅疊在兩記上(damage_mult=_df)。"""
    c = _swordsman(block=100)
    foe = _bandit(7, 9999)
    real = combat.resolve_attack
    seen = []

    def spy(att, dfn, gamedata, rng, *a, **k):
        if att is c:
            seen.append(k.get("damage_factor"))
        return real(att, dfn, gamedata, rng, *a, **k)
    n = {"i": 0}

    def chooser(*a, **k):
        n["i"] += 1
        if n["i"] == 1:
            c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
            return {"type": "reckless", "target": foe}
        return {"type": "flee"}
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    with _Patch((main, "_choose_combat_action", chooser), (combat, "resolve_attack", spy)):
        main.run_battle(st, gd, [foe])
    tax = formulas.GUARD_STANCE_DAMAGE_TAX
    assert len(seen) >= 2 and abs(seen[0] - tax) < 1e-9 and abs(seen[1] - 0.6 * tax) < 1e-9, seen


# R191 前 HEAD(39bc2ba)的黃金值:同一夾具(orsimer 戰士·刀劍 100·鋼劍 vs 5000 血 bandit·RNG(21)·各 8 次互毆)在
# 乾淨 HEAD 與 R191 後完全相同。審查指出原「已選 vs 未選」只比同一份新碼,對「逐位元組同 HEAD」是重言式 → 改釘死對 HEAD 的值。
# 日後若合理改了命中/戰鬥公式,重算(git archive 舊版跑同一夾具)並更新此值,連同 sim 基線。
GOLDEN_HITS = "HHHHHHHHHmmmmHHm"
GOLDEN_RNG = "0.3684466408433329"


def _golden_run(choose):
    c = _swordsman(choose=choose)
    f = _bandit(4, 5000)
    rng = RNG(21)
    evs = [combat.resolve_attack(c, f, gd, rng) for _ in range(8)] + [combat.resolve_attack(f, c, gd, rng) for _ in range(8)]
    return "".join("H" if e["hit"] else "m" for e in evs), repr(rng.random())


def test_unchosen_swordsman_matches_the_pre_r191_head_golden():
    assert _golden_run(False) == (GOLDEN_HITS, GOLDEN_RNG), "未選構築的 rng 序列須與 R191 前 HEAD 逐位元組相同(零 rng 新路徑)"


def test_chosen_but_unused_savage_no_longer_changes_ordinary_attacks():
    """舊 savage 的 +12%/自損會改變普攻;新戰技不按就等於沒選 → 普攻/受擊與未選逐位元組相同(同一份 HEAD 黃金值)。"""
    assert _golden_run(True) == (GOLDEN_HITS, GOLDEN_RNG)

def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_reckless_r191 OK")
