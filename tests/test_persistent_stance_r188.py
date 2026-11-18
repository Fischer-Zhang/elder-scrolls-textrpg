"""R188 常駐戰鬥效果哨兵修正(R137 既有 bug,R187 前瞻 ⑤):格擋姿態/盾牆/戰旗/號令原用 turns=99,
tick_effects 每回合 −1 → ①HUD 第 2 回合起顯示「格擋姿態98」倒數(與 _STANCE_MAINTAINED「常駐不顯回合數」本意相違)
②打滿 99 回合靜默失效。改用 combat.PERSISTENT_TURNS(10**6;氣勢 R187 已驗證的做法)。
另:迴身反打/風暴之舞效果文補寫實際閘條件(僅物理近戰;元素與遠程招式閃過不反擊 — R145/R183 行為本就如此)。
🔴 不碰任何戰鬥數學/上限/偷襲倍率:純顯示 + 效果壽命;離戰一律 clear() → 不殘留進存檔。"""
import io
from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, mastery, stats
import tesrpg.main as main

gd = get_gamedata()

# 立架式的玩家動作 → (效果 kind, HUD 標籤)
STANCES = {
    "guard": ("guard_stance", "格擋姿態"),
    "wall": ("shield_wall", "盾牆"),
    "standard": ("battle_standard", "戰旗"),
    "rally": ("rally_banner", "號令"),
}


def _hero():
    c = build_character(gd, name="架", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 10 ** 5
    return c


def _foe(hp=10 ** 6):
    f = combat.spawn_creature(gd, "bandit", RNG(1))
    f.health = f.max_health = hp
    return f


def _run(c, foe, script):
    """run_battle 以 script(i) 決定第 i 個玩家動作;回傳每次選動作當下的 HUD 標籤 + 效果 kinds。"""
    seen = []
    n = {"i": 0}

    def act(*a, **k):
        n["i"] += 1
        seen.append((ui._status_tags(c), [e["kind"] for e in c.active_effects]))
        return script(n["i"], foe)
    orig = main._choose_combat_action
    main._choose_combat_action = act
    try:
        main.run_battle(GameState(player=c, rng=RNG(3), time=GameTime()), gd, [foe])
    finally:
        main._choose_combat_action = orig
    return seen


# ---------------------------------------------------------------- 哨兵常數
def test_sentinel_is_one_shared_large_constant():
    assert combat.PERSISTENT_TURNS >= 10 ** 5, "必須遠大於任何實際戰鬥回合數(99 會在長戰失效)"
    assert combat._MOMENTUM_TURNS == combat._AFTERIMAGE_TURNS == combat.PERSISTENT_TURNS
    assert ui._STANCE_MAINTAINED <= combat.PERSISTENT_TURNS, "HUD 的「常駐不顯數字」門檻必須涵蓋哨兵"


# ---------------------------------------------------------------- HUD:真實 run_battle 路徑
def test_real_battle_hud_never_shows_countdown_for_any_stance():
    """立架式後連打數回合:每回合 HUD 標籤恆為純名稱(不得出現「格擋姿態98」之類倒數)。"""
    for action, (kind, label) in STANCES.items():
        c = _hero()
        f = _foe()
        seen = _run(c, f, lambda i, foe: {"type": action} if i == 1 else
                    ({"type": "attack", "target": foe} if i <= 7 else {"type": "flee"}))
        later = seen[1:7]
        assert len(later) == 6, (action, len(seen))
        for tags, kinds in later:
            assert kind in kinds, (action, kinds)                    # 架式確實還在(不是因攻擊/調息被解除)
            # 逐 token 精確比對:標籤本身必為純名稱(戰旗另帶每回合重推的自護盾「盾1」,屬正常顯示,不在檢查範圍)
            assert label in tags.split(), (action, tags)


def test_timed_effects_still_show_countdown_control():
    """對照組:一般限時效果仍顯示剩餘回合(改動不得波及 HUD 其他標籤)。"""
    c = _hero()
    c.active_effects[:] = [{"kind": "dot", "element": "poison", "magnitude": 1, "turns": 4}]
    assert ui._status_tags(c) == "蝕4"
    magic.tick_effects(c, gd)
    assert ui._status_tags(c) == "蝕3"


# ---------------------------------------------------------------- 壽命:長戰不失效
def test_stances_survive_far_beyond_99_rounds():
    """舊行為:99 次 tick 後消失(has_* 變 False、姿態稅/減傷靜默失效)。"""
    for action, (kind, label) in STANCES.items():
        c = _hero()
        if kind == "shield_wall":
            c.active_effects.append({"kind": kind, "mitigation": main.SHIELD_WALL_MITIGATION,
                                     "turns": combat.PERSISTENT_TURNS})
        else:
            c.active_effects.append({"kind": kind, "turns": combat.PERSISTENT_TURNS})
        for _ in range(500):
            magic.tick_effects(c, gd)
        assert any(e["kind"] == kind for e in c.active_effects), kind
        assert ui._status_tags(c) == label, (kind, ui._status_tags(c))
    c = _hero()
    c.active_effects.append({"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS})
    for _ in range(500):
        magic.tick_effects(c, gd)
    assert combat.has_guard_stance(c)


def test_real_battle_stance_persists_past_99_rounds():
    """真實 run_battle 迴圈打滿 120 回合:架式仍在、回合 100+ 時 HUD 仍無倒數(不入檔邊界另測)。"""
    c = _hero()
    f = _foe(hp=10 ** 9)
    c.fatigue = c.max_fatigue
    seen = _run(c, f, lambda i, foe: {"type": "guard"} if i == 1 else
                ({"type": "attack", "target": foe} if i <= 120 else {"type": "flee"}))
    assert len(seen) >= 121, len(seen)
    assert "guard_stance" in seen[110][1], "第 111 回合架式應仍在(舊 99 哨兵第 99 回合即消失)"
    assert seen[110][0] == "格擋姿態", seen[110][0]


# ---------------------------------------------------------------- 邊界:離戰必清(大數哨兵不得殘留)
def test_battle_exit_leaves_no_persistent_effects_on_flee_and_on_win():
    persistent = {"guard_stance", "shield_wall", "battle_standard", "rally_banner", "afterimage", "momentum"}
    for action, (kind, _label) in STANCES.items():
        # 逃走離戰
        c = _hero()
        _run(c, _foe(), lambda i, foe: {"type": action} if i == 1 else {"type": "flee"})
        assert not persistent & {e["kind"] for e in c.active_effects}, (action, "flee")
        # 擊殺離戰
        c = _hero()
        weak = _foe(hp=1)
        weak.armor_rating = 0
        _run(c, weak, lambda i, foe: {"type": action} if i == 1 else {"type": "attack", "target": foe})
        assert not combat.is_alive(weak), (action, "應已斬殺")
        assert not persistent & {e["kind"] for e in c.active_effects}, (action, "win")


# ---------------------------------------------------------------- 效果文:迴身反打/風暴之舞寫明實際閘條件
def _on_evade_opts():
    import json
    import pathlib
    raw = json.loads((pathlib.Path(main.__file__).parent / "data" / "mastery.json").read_text(encoding="utf-8"))
    out = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get("kind") == "on_evade":
                out[o["opt_id"]] = o
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(raw)
    return out


def test_counter_descs_state_physical_melee_only():
    opts = _on_evade_opts()
    assert set(opts) >= {"riposte_step", "storm_dance", "fluid_motion", "aerial_ambush"}
    for oid in ("riposte_step", "storm_dance"):
        d = opts[oid]["desc"]
        assert "物理近戰" in d and "元素" in d and "遠程" in d, (oid, d)
    # 僅回體力的兩個節點不反擊 → 不應被加上此限制語
    for oid in ("fluid_motion", "aerial_ambush"):
        assert "物理近戰" not in opts[oid]["desc"], oid


def test_counter_actually_gated_by_element_and_ranged_as_text_claims():
    """效果文宣稱「元素與遠程招式閃過不反擊」→ 真實 resolve_attack 驗:閃過物理近戰招會反擊(攻擊者掉血),
    閃過元素/ranged 招絕不反擊(回體力照給)。分母=閃過次數,故需足夠樣本。"""
    def run_kind(patch):
        evaded = countered = 0
        for s in range(900):
            c = build_character(gd, name="舞", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
            c.skills.update(light_armor=100, acrobatics=60, blade=50)
            mastery.choose(c, gd, "light_armor_100", "storm_dance")
            stats.recompute_max_resources(c, gd, restore_full=True)
            c.health = c.max_health = 10 ** 5
            foe = _foe()
            atk = {"name": "揮砍", "damage": 4, "skill": 40, **patch}
            ev = combat.resolve_attack(foe, c, gd, RNG(500 + s), attack=atk)
            if not ev["hit"]:
                evaded += 1
                if foe.health < foe.max_health:
                    countered += 1
        return evaded, countered
    e_p, c_p = run_kind({})
    e_e, c_e = run_kind({"element": "fire"})
    e_r, c_r = run_kind({"ranged": True})
    assert min(e_p, e_e, e_r) > 100, (e_p, e_e, e_r)     # 樣本足夠(非空洞通過)
    assert 0.45 < c_p / e_p < 0.75, (c_p, e_p)            # ≈60% 反擊
    assert c_e == 0 and c_r == 0, (c_e, c_r)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("OK")
