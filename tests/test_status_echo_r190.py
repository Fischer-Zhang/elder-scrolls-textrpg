"""R190 狀態讀取一致化:`magic.apply_control` 為控場唯一入口,成功施加(或被去重擋下)時對非玩家目標統一留「餘韻」
{"kind":"echo","of":k,"turns":2};對狀態有加乘的讀取端(看破/獵手之眼)一律走 `combat.afflicted`(實際狀態或餘韻)。
動機:各來源給的回合數不一(玩家階段 t1 控場回合末即歸零,下一擊讀不到;t2+ 讀得到)→ 同一狀態因來源不同被不同對待。
🔴 餘韻只供讀取:命中減益/失能/tick/驅散(is_staggered 等實際效果)不得讀它;不擲 rng;玩家本人不留;resisted 不留;
   blocked(去重)要刷新(否則同源每擊重施的 t2 控場會隔回合才讀得到,把不一致倒過來 —— Opus 審查指出)。"""
import io
import pathlib
import re

from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import synth
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, inventory, magic, mastery, stats
import tesrpg.main as main

gd = get_gamedata()


def _hero(blade=100, weapon="steel_sword", precision=True):
    c = build_character(gd, name="餘", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.skills["blade"] = blade
    c.attributes["strength"] = 80
    c.weapon = weapon
    if precision:
        mastery.choose(c, gd, "blade_100", "precision")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 10 ** 5
    return c


def _foe(tid="bandit", hp=10 ** 6):
    f = combat.spawn_creature(gd, tid, RNG(7))
    f.health = f.max_health = hp
    return f


def _echoes(foe):
    return [e for e in foe.active_effects if e.get("kind") == "echo"]


def _live(foe, kind):
    return any(e.get("kind") == kind and e.get("turns", 0) > 0 for e in foe.active_effects)


# ---------------------------------------------------------------- apply_control 單一處理點
def test_echo_left_for_every_exploit_kind_on_applied():
    for kind in magic.ECHO_KINDS:
        foe = _foe()
        assert magic.apply_control(foe, kind, gd, RNG(1), turns=1) == "applied", kind
        assert [(e["of"], e["turns"]) for e in _echoes(foe)] == [(kind, magic.ECHO_TURNS)], kind
    assert set(magic.ECHO_KINDS) == {"stagger", "weaken", "slow", "benumb", "fear", "paralyze"}


def test_no_echo_for_resisted_or_unread_kinds_or_player():
    # resisted:solo BOSS 硬控機率抵抗 → 不留(找一個被抵抗的 seed;非空洞斷言 resisted 確實出現)
    boss = _foe("mehrunes_dagon")
    hit = 0
    for s in range(200):
        boss.active_effects.clear()
        if magic.apply_control(boss, "paralyze", gd, RNG(s), turns=1) == "resisted":
            hit += 1
            assert not _echoes(boss)
    assert hit > 0
    skel = _foe("skeleton") if "skeleton" in gd.bestiary else None
    if skel is not None:                                          # 無心智者嚇不動 → resisted → 不留
        assert magic.apply_control(skel, "fear", gd, RNG(1), turns=1) == "resisted" and not _echoes(skel)
    for kind in ("calm", "frenzied"):                             # 目前無讀取端 → 不建(避免死資料)
        foe = _foe()
        assert magic.apply_control(foe, kind, gd, RNG(1), turns=2) == "applied" and not _echoes(foe), kind
    me = _hero()                                                  # 玩家本人不留(HUD/邏輯皆不需要)
    for kind in magic.ECHO_KINDS:
        me.active_effects.clear()
        magic.apply_control(me, kind, gd, RNG(1), turns=1)
        assert not _echoes(me), kind


def test_blocked_refreshes_echo_both_dedupe_paths():
    """🔴 去重擋下(blocked)也要刷新餘韻:否則同源每擊重施的 t2 控場(感電附魔凍緩)會隔回合才讀得到。"""
    foe = _foe()                                                  # 硬控去重
    assert magic.apply_control(foe, "fear", gd, RNG(1), turns=2) == "applied"
    magic.tick_effects(foe, gd)
    assert _echoes(foe)[0]["turns"] == 1
    assert magic.apply_control(foe, "fear", gd, RNG(1), turns=2) == "blocked"
    assert _echoes(foe)[0]["turns"] == magic.ECHO_TURNS
    foe = _foe()                                                  # 同源去重
    assert magic.apply_control(foe, "weaken", gd, RNG(1), magnitude=0.2, turns=2, source="ench_chill") == "applied"
    magic.tick_effects(foe, gd)
    assert magic.apply_control(foe, "weaken", gd, RNG(1), magnitude=0.2, turns=2, source="ench_chill") == "blocked"
    assert [e["turns"] for e in _echoes(foe)] == [magic.ECHO_TURNS]       # 同 of 只一個、已刷新
    assert len([e for e in foe.active_effects if e.get("kind") == "weaken"]) == 1   # 實際效果仍只有一份(去重不變)


def test_blocked_cross_kind_same_source_does_not_leave_echo():
    """審查補:同源去重可跨狀態擋下(同 source 的衰弱還活著時,同源踉蹌回 blocked)——目標此刻並無踉蹌 → 不得留踉蹌餘韻
    (否則 afflicted 說『被踉蹌』而 is_staggered 說沒有,兩個讀法不一致)。"""
    foe = _foe()
    assert magic.apply_control(foe, "weaken", gd, RNG(1), magnitude=0.2, turns=2, source="wabbajack") == "applied"
    assert magic.apply_control(foe, "stagger", gd, RNG(1), turns=1, source="wabbajack") == "blocked"
    assert not magic.is_staggered(foe)
    assert not combat.afflicted(foe, ("stagger",)), "目標並未踉蹌,不得有踉蹌餘韻"
    assert [(e["of"]) for e in _echoes(foe)] == ["weaken"]


def test_allies_and_summons_also_get_echo_but_it_is_inert():
    """設計(Opus 審查):同伴/召喚物(Creature)被控場也留餘韻——補傷只在玩家出手時讀、玩家打不到我方,故功能上無影響;
    只在 HUD 隱藏。鎖住此行為,免日後被誤當 bug 或誤改成『排除』而增加判斷敵我的出錯面。"""
    ally = _foe(); ally.summoned = True; ally.summon_turns = 3
    assert magic.apply_control(ally, "stagger", gd, RNG(1), turns=1) == "applied"
    assert [(e["of"], e["turns"]) for e in _echoes(ally)] == [("stagger", magic.ECHO_TURNS)]
    magic.tick_effects(ally, gd); magic.tick_effects(ally, gd)
    assert not _echoes(ally)                                       # 2 回合自清


def test_exploit_reader_is_derived_from_data_not_hardcoded():
    assert mastery.exploit_reader(_hero(), gd) is True             # 看破
    assert mastery.exploit_reader(_hero(precision=False), gd) is False
    a = build_character(gd, name="弓", sex="male", race="bosmer", birthsign="shadow", class_id="archer")
    a.skills["marksman"] = 100
    assert mastery.exploit_reader(a, gd) is False
    mastery.choose(a, gd, "marksman_100", "hunters_eye")
    assert mastery.exploit_reader(a, gd) is True                   # 獵手之眼
    b = build_character(gd, name="弓", sex="male", race="bosmer", birthsign="shadow", class_id="archer")
    b.skills["marksman"] = 100
    mastery.choose(b, gd, "marksman_100", "rapid_shot")            # 里程碑是永久銘刻:選連珠箭的弓手不是讀取端
    assert mastery.exploit_reader(b, gd) is False


def test_echo_is_read_only_no_effect_on_real_logic():
    foe = _foe()
    for kind in magic.ECHO_KINDS:
        foe.active_effects.append({"kind": "echo", "of": kind, "turns": 2})
    assert not magic.is_staggered(foe) and not magic.is_slowed(foe)
    assert magic.benumb_hit_penalty(foe) == 0.0
    assert not magic.is_incapacitated(foe)
    me = _hero(precision=False)
    plain, with_echo = _foe(), _foe()
    with_echo.active_effects += [{"kind": "echo", "of": k, "turns": 2} for k in magic.ECHO_KINDS]
    for s in range(40):                                           # 怪打玩家:命中/傷害逐 seed 相同(餘韻不碰命中減益)
        a = combat.resolve_attack(plain, me, gd, RNG(s))
        b = combat.resolve_attack(with_echo, me, gd, RNG(s))
        assert (a["hit"], a["damage"]) == (b["hit"], b["damage"])
    foe.active_effects[:] = [{"kind": "echo", "of": "stagger", "turns": 1}]
    assert magic.tick_effects(foe, gd) == [] and foe.active_effects == []      # 過期靜默移除、不發訊息


# ---------------------------------------------------------------- 各來源一致:t1 來源在 tick 後仍讀得到
def _afterglow(foe):
    magic.tick_effects(foe, gd)                                  # 敵階段 + 回合末
    return not _live(foe, "stagger") and combat.afflicted(foe, ("stagger",))


def test_every_stagger_source_leaves_a_readable_afterglow():
    # 1) 雷刃術 rider(R149 imbue,t1)
    c = _hero()
    c.active_effects.append({"kind": "weapon_imbue", "element": "shock", "magnitude": 8, "turns": 5,
                             "rider": {"status": "stagger", "turns": 1, "chance": 1.0}})
    foe = _foe()
    combat.resolve_attack(c, foe, gd, RNG(1))
    assert _live(foe, "stagger") and _afterglow(foe), "雷刃術"
    # 2) 感電附魔 jolt rider(t1,20%)
    wid = synth.enchant_weapon_status_id("steel_sword", "jolt", 5, 3)
    c = _hero(); inventory.add_item(c, wid, 1); c.weapon = wid
    got = 0
    for s in range(200):
        foe = _foe()
        combat.resolve_attack(c, foe, gd, RNG(s))
        if _live(foe, "stagger"):
            got += 1
            assert _afterglow(foe), "感電附魔"
    assert got > 10
    # 3) 釘錘內建擊暈(t1,20%)
    c = _hero(blade=1, weapon="steel_mace"); c.skills["blunt"] = 100
    got = 0
    for s in range(200):
        foe = _foe()
        combat.resolve_attack(c, foe, gd, RNG(s))
        if _live(foe, "stagger"):
            got += 1
            assert _afterglow(foe), "釘錘"
    assert got > 10
    # 4) 徒手失衡 / 瘋神等:凡走 apply_control 的 stagger(含 source 標)一律
    for src in (None, "offbalance", "wabbajack", "imbue_shock"):
        foe = _foe()
        assert magic.apply_control(foe, "stagger", gd, RNG(1), turns=1, source=src) == "applied"
        assert _afterglow(foe), src


def test_other_status_t1_sources_are_equally_readable_by_the_six_state_reader():
    """通則的『其他 debuff 也一樣』:t1 的恐懼/衰弱/麻痺/遲緩/凍麻餘韻,獵手之眼六態讀取端同樣讀得到。"""
    for kind in magic.ECHO_KINDS:
        foe = _foe()
        magic.apply_control(foe, kind, gd, RNG(1), turns=1, magnitude=0.2)
        magic.tick_effects(foe, gd)
        assert not _live(foe, kind) and combat.afflicted(foe, combat._EXPLOIT_KINDS), kind
        magic.tick_effects(foe, gd)                              # 再過一回合 → 窗口關閉
        assert not combat.afflicted(foe, combat._EXPLOIT_KINDS), kind


def test_hunters_eye_reads_afterglow_of_every_state_like_live_ones():
    """通則:獵手之眼(弓,六態)與看破(刀,踉蹌)走同一讀取入口 → 六態的餘韻都算,其他狀態(安撫)不算;
    使用者裁決(R190):獵手之眼不縮小(範圍六態、+20% 不變);實測一致化對弓手影響 +0.0~+1.8pp(雜訊內)。"""
    a = build_character(gd, name="弓", sex="male", race="bosmer", birthsign="shadow", class_id="archer")
    a.skills["marksman"] = 100
    a.weapon = "hunting_bow"
    mastery.choose(a, gd, "marksman_100", "hunters_eye")
    stats.recompute_max_resources(a, gd, restore_full=True)
    a.health = a.max_health = 10 ** 5
    assert mastery.weapon_mod(a, gd, "marksman")["exploit"] == 0.20          # 不縮:+20%
    assert "exploit_kinds" not in mastery.weapon_mod(a, gd, "marksman")      # 不縮:缺省六態

    def dmg(foe, s):
        return combat.resolve_attack(a, foe, gd, RNG(s))["damage"]
    base = sum(dmg(_foe(), s) for s in range(60))
    for kind in magic.ECHO_KINDS:
        f_live = _foe(); f_live.active_effects.append({"kind": kind, "magnitude": 0.3, "turns": 2})
        f_echo = _foe(); f_echo.active_effects.append({"kind": "echo", "of": kind, "turns": 1})
        live = sum(dmg(_foe_with(f_live), s) for s in range(60))
        echo = sum(dmg(_foe_with(f_echo), s) for s in range(60))
        assert live > base * 1.05 and echo == live, (kind, base, live, echo)  # 餘韻與實際狀態讀起來一致
    f_calm = _foe(); f_calm.active_effects.append({"kind": "echo", "of": "calm", "turns": 1})
    assert sum(dmg(_foe_with(f_calm), s) for s in range(60)) == base           # 非六態的餘韻不算


def _foe_with(template):
    f = _foe()
    f.active_effects = [dict(e) for e in template.active_effects]
    return f


def test_both_exploit_readers_share_the_single_entry():
    """看破(刀)與獵手之眼(弓)都經 combat.afflicted 讀狀態(R190 鐵律:讀取端不得自掃 active_effects)。"""
    calls = []
    orig = combat.afflicted
    combat.afflicted = lambda t, k: calls.append(tuple(k)) or orig(t, k)
    try:
        c = _hero()                                                   # 刀劍看破:只認踉蹌
        combat.resolve_attack(c, _foe(), gd, RNG(1))
        a = build_character(gd, name="弓", sex="male", race="bosmer", birthsign="shadow", class_id="archer")
        a.skills["marksman"] = 100; a.weapon = "hunting_bow"
        mastery.choose(a, gd, "marksman_100", "hunters_eye")
        combat.resolve_attack(a, _foe(), gd, RNG(1))                  # 弓手獵手之眼:六態
    finally:
        combat.afflicted = orig
    assert ("stagger",) in calls and tuple(combat._EXPLOIT_KINDS) in calls, calls


# ---------------------------------------------------------------- 真實 run_battle 時序
def test_real_battle_player_hit_sees_previous_rounds_stagger():
    """雷刃術 rider(chance 1.0,t1)每擊都踉蹌:無餘韻時第 2 擊讀不到上一回合的踉蹌(補傷判定在命中附加狀態之前);
    有餘韻時第 2 擊起恆讀得到 —— 在真實 run_battle 迴圈驗證(玩家→同伴→敵人→回合末 tick)。"""
    c = _hero()
    c.active_effects.append({"kind": "weapon_imbue", "element": "shock", "magnitude": 8, "turns": 9,
                             "rider": {"status": "stagger", "turns": 1, "chance": 1.0}})
    foe = _foe()
    seen = []
    orig = combat.afflicted

    def spy(target, kinds):
        r = orig(target, kinds)
        if target is foe:
            seen.append(r)
        return r
    combat.afflicted = spy
    n = {"i": 0}

    def act(*a, **k):
        n["i"] += 1
        return {"type": "attack", "target": foe} if n["i"] <= 4 else {"type": "flee"}
    o_act = main._choose_combat_action
    main._choose_combat_action = act
    try:
        main.run_battle(GameState(player=c, rng=RNG(3), time=GameTime()), gd, [foe], preserve_buffs=True)
    finally:
        combat.afflicted, main._choose_combat_action = orig, o_act
    assert len(seen) >= 3, seen                                   # 非空洞:補傷判定確實被呼叫多次
    assert seen[0] is False and all(seen[1:]), seen               # 第 1 擊尚無;其後每擊讀得到上一回合的踉蹌餘韻


# ---------------------------------------------------------------- 鐵律守衛(原始碼掃描)
def _py_sources():
    root = pathlib.Path(main.__file__).parent
    return {p: p.read_text(encoding="utf-8") for p in root.rglob("*.py")}


def test_choke_point_no_direct_control_append_and_single_reader_entry():
    pat = re.compile(r'active_effects\.append\(\{"kind":\s*"(stagger|slow|weaken|benumb|fear|paralyze)"')
    for p, src in _py_sources().items():
        assert not pat.search(src), f"{p.name}:控場須走 magic.apply_control(R44/R190 單一處理點),不得直接 append"
    for p, src in _py_sources().items():
        if p.name == "combat.py":
            continue
        assert "_EXPLOIT_KINDS" not in src, f"{p.name}:狀態加乘讀取一律走 combat.afflicted"
    combat_src = (pathlib.Path(main.__file__).parent / "systems" / "combat.py").read_text(encoding="utf-8")
    assert not re.search(r'kind"\)\s*in\s*_?(xk|EXPLOIT_KINDS)', combat_src), "combat.py 不得自掃狀態集合"
    assert "exposed" not in combat_src and "_mark_exposed" not in combat_src      # R189 逐點標記已移除


# ---------------------------------------------------------------- HUD
def test_hud_echo_tag_only_on_enemy_cards_and_not_duplicated():
    me, ally, foe = _hero(), _foe(), _foe()
    for ent in (me, ally, foe):
        ent.active_effects.append({"kind": "echo", "of": "stagger", "turns": 1})
    assert ui._combat_view(me, [ally], [foe])["enemies"][0]["tags"] == []      # 沒有狀態加乘里程碑的玩家:不顯示(無用的雜訊)
    view = ui._combat_view(me, [ally], [foe], show_echo=True)
    assert [t["s"] for t in view["enemies"][0]["tags"]] == ["破綻·踉"]
    assert view["enemies"][0]["tags"][0]["good"] is False
    assert view["me"]["tags"] == [] and view["allies"][0]["tags"] == []        # 玩家/同伴不顯示餘韻
    foe.active_effects.append({"kind": "stagger", "turns": 1})                 # 實際狀態仍在 → 不重複顯示餘韻
    assert [t["s"] for t in ui._combat_view(me, [ally], [foe], show_echo=True)["enemies"][0]["tags"]] == ["踉1"]
    foe.active_effects[:] = [{"kind": "echo", "of": "slow", "turns": 1}, {"kind": "echo", "of": "fear", "turns": 1},
                             {"kind": "echo", "of": "slow", "turns": 1}]
    assert [t["s"] for t in ui._combat_view(me, [ally], [foe], show_echo=True)["enemies"][0]["tags"]] == ["破綻·緩", "破綻·懼"]
    assert ui._status_tags(foe, echo=True) == "破綻·緩 破綻·懼"                  # rich 退路(字串版)同規則
    assert ui._status_tags_list(foe) == [] and ui._status_tags(foe) == ""      # 預設(非敵方卡片)不顯示


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_status_echo_r190 OK")
