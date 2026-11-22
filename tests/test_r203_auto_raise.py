"""R203d「就地起屍」(conjuration_75 · opt_id soul_harvest,取代舊「亡者收集」純 +1 token / 擊殺;使用者 2026-11-22 拍板)。

規則:每場戰鬥,第一具符合資格的敵屍在**回合末、召喚物計時之前**自動起屍為你的真·亡者盟友 —— 不耗行動、法力、體力與靈魂 token;
資格 = 亡者復生既有排除(solo 首領 / 已復生 / BOSS 爪牙 / 無此模板)+ 戰場上仍有存活敵人 + 亡者軍團未滿(滿了不耗掉本場那一次)。
一場一次;取敵群排列順序的第一具;起屍參數取「亡者奴役」(滿血、回合 6 + 1)。兼帶舊 +1 token / 擊殺(Q5)。

🔴 守衛:① 資料 / getter(opt_id 不變、兼帶 per_kill、未選回 False)② 重構不改既有復生:`magic.reanimate_candidate` /
   `raise_corpse` 搬移自 cast 分支,對 HEAD 原樹差分逐位元組同(52 場景)+ 此處黃金值 ③ `necromancy.auto_raise` 資格與一次性、
   不消耗 rng / 資源 ④ `run_battle` 接線:群戰起屍、順序在 tick 前(剩 6 回合)、單敵不起屍、未選不起屍、軍團滿延後、
   略過首領屍 ⑤ 起屍參數 = 亡者奴役實際施放的參數。
"""
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, mastery, necromancy, stats

gd = get_gamedata()


def _mage(choice="soul_harvest", um="undead_dominion", fat=1.0):
    c = build_character(gd, name="召", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills.update(conjuration=100)
    c.attributes.update(intelligence=100, willpower=100)
    c.spells = ["reanimate_corpse", "reanimate_thrall", "raise_thrall", "flames"]
    if um:
        c.mastery_choices["conjuration_100"] = um
    if choice:
        c.mastery_choices["conjuration_75"] = choice
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = c.max_magicka = 5000
    c.fatigue = c.max_fatigue * fat
    c.health = c.max_health = 5000
    c.soul_tokens = 40
    return c


def _corpse(tid="bandit", **flags):
    k = combat.spawn_creature(gd, tid, RNG(5))
    k.health = 0
    for key, val in flags.items():
        setattr(k, key, val)
    return k


def _live(tid="bandit"):
    f = combat.spawn_creature(gd, tid, RNG(1))
    f.health = f.max_health = 10 ** 6
    f.resist = {}
    f.active_effects.append({"kind": "paralyze", "turns": 10 ** 6})       # 麻痺哨兵:敵方階段整個跳過,走向完全由腳本決定
    return f


def _undead_ally(turns=10):
    a = combat.spawn_creature(gd, "reanimated_thrall", RNG(1))
    a.summon_turns = turns
    a._undead = True
    return a


# --- ① 資料 / getter ----------------------------------------------------------------------
def test_node_data_option_id_stable_per_kill_rider_kept_and_getter_only_when_selected():
    node = next(n for n in gd.mastery if n["id"] == "conjuration_75")
    opts = {o["opt_id"]: o for o in node["options"]}
    assert set(opts) == {"conj_efficiency", "soul_harvest"}                       # opt_id 不變(存檔相容、零遷移)
    o = opts["soul_harvest"]
    assert o["name"] == "就地起屍" and o["kind"] == "soul_harvest" and o["auto_raise"] == 1 and o["per_kill"] == 1
    assert "起屍" in o["desc"] and "+1 靈魂" in o["desc"] and "取代舊" not in o["desc"]
    assert mastery.auto_raise(_mage(), gd) is True
    assert mastery.auto_raise(_mage(None), gd) is False
    assert mastery.auto_raise(_mage("conj_efficiency"), gd) is False
    assert mastery.soul_harvest_bonus(_mage(), gd) == 1 and mastery.soul_harvest_bonus(_mage(None), gd) == 0   # 兼帶舊效果(Q5)
    assert mastery.quick_seal(_mage(), gd) is False                                # 與瞬發契印互斥(同節點二選一)


# --- ② 重構不改既有復生(黃金值;對 HEAD 原樹 52 場景差分逐位元組同,見 handoff R203d)-------------------
def test_reanimate_spell_unchanged_after_extracting_pick_and_raise_helpers_golden_values():
    golden = [  # (um, soul75, 體力比, 法術, 屍體模板) → (max_health, summon_power, summon_turns, token 餘量, 法力餘量, 體力餘量)
        (("undead_dominion", None, 1.0, "reanimate_thrall", "bandit"), (55, 1.56, 7, 38, 4974, 193.0)),
        (("undead_dominion", None, 0.1, "reanimate_corpse", "draugr"), (29, 1.56, 5, 39, 4976, 14.0)),
        (("lasting_summon", "soul_harvest", 0.5, "reanimate_thrall", "draugr"), (43, 1.3, 7, 38, 4974, 93.0)),
    ]
    for (um, sc, ff, sid, tid), want in golden:
        c = _mage(sc, um, ff)
        battle = {"allies": []}
        r = magic.cast(c, gd, sid, RNG(11), battle=battle, corpses=[_corpse(tid)], enemies=[])
        a = battle["allies"][0]
        got = (a.max_health, round(a.summon_power, 9), a.summon_turns, c.soul_tokens, round(c.magicka, 6), round(c.fatigue, 6))
        assert r["ok"] and got == want and a._undead and a.health == a.max_health, ((um, sc, ff, sid, tid), got)
    # 失敗路徑仍原樣:無屍 / 已復生 / solo / 爪牙 → 不起屍、退魔退體不收 token
    for label, corpses in (("none", []), ("already", [_corpse(_reanimated=True)]),
                           ("solo", [_corpse("mehrunes_dagon")]), ("summoned", [_corpse(summoned=True)])):
        c = _mage()
        m0, f0, t0 = c.magicka, c.fatigue, c.soul_tokens
        battle = {"allies": []}
        r = magic.cast(c, gd, "reanimate_thrall", RNG(3), battle=battle, corpses=corpses, enemies=[])
        assert r["ok"] is False and not battle["allies"], label
        assert (c.magicka, c.fatigue, c.soul_tokens) == (m0, f0, t0), label


def test_candidate_picks_first_in_enemy_list_order_and_skips_every_excluded_kind():
    alive = _live()
    solo, summoned, again = _corpse("mehrunes_dagon"), _corpse(summoned=True), _corpse(_reanimated=True)
    ok1, ok2 = _corpse("bandit"), _corpse("draugr")
    ghost = _corpse(); ghost.template_id = "no_such_template"
    assert magic.reanimate_candidate([alive, solo, summoned, again, ghost, ok1, ok2], gd) is ok1
    assert magic.reanimate_candidate([ok2, ok1], gd) is ok2, "取列表順序的第一具,不是『最先死的』"
    assert magic.reanimate_candidate([alive, solo, summoned, again, ghost], gd) is None
    assert magic.reanimate_candidate([], gd) is None and magic.reanimate_candidate(None, gd) is None


# --- ③ necromancy.auto_raise ---------------------------------------------------------------
def test_auto_raise_picks_the_first_eligible_corpse_once_per_battle_and_charges_nothing():
    c = _mage()
    battle = {"allies": []}
    enemies = [_live(), _corpse("mehrunes_dagon"), _corpse("bandit"), _corpse("draugr")]   # 首領屍不佔名額、不耗掉那一次
    m0, f0, t0 = c.magicka, c.fatigue, c.soul_tokens
    ally = necromancy.auto_raise(c, gd, RNG(3), battle, enemies)
    assert ally is not None and enemies[2]._reanimated is True and not getattr(enemies[3], "_reanimated", False)
    assert ally in battle["allies"] and ally._undead and ally.health == ally.max_health and battle["auto_raised"] is True
    assert (c.magicka, c.fatigue, c.soul_tokens) == (m0, f0, t0), "不耗法力 / 體力 / token"
    assert necromancy.auto_raise(c, gd, RNG(3), battle, enemies) is None, "一場一次:第二具屍體不再起"
    assert len(battle["allies"]) == 1


def test_auto_raise_conditions_unselected_no_enemy_left_cap_full_and_cap_does_not_burn_the_use():
    def trail(fn):
        rng = RNG(3)
        out = fn(rng)
        return out, rng.random() == RNG(3).random()

    # 未選 / 無死靈經濟前提不成立:不起、不碰 rng
    for choice in (None, "conj_efficiency"):
        c = _mage(choice)
        out, untouched = trail(lambda rng: necromancy.auto_raise(c, gd, rng, {"allies": []}, [_live(), _corpse()]))
        assert out is None and untouched, choice
    # (死靈經濟閘 `has_soul_economy` 在 75 階必成立〔召喚 ≥ 25〕→ 純防禦性檢查,結構上不可單獨觸發,故不測)
    # 戰場上已無存活敵人:不起(也不記一次)
    c = _mage()
    b = {"allies": []}
    out, untouched = trail(lambda rng: necromancy.auto_raise(c, gd, rng, b, [_corpse(), _corpse("draugr")]))
    assert out is None and untouched and "auto_raised" not in b
    # 軍團已滿:不起、不耗掉那一次;空出名額後仍能起
    cap = necromancy.undead_field_cap(c)
    full = {"allies": [_undead_ally() for _ in range(cap)]}
    enemies = [_live(), _corpse()]
    out, untouched = trail(lambda rng: necromancy.auto_raise(c, gd, rng, full, enemies))
    assert out is None and untouched and "auto_raised" not in full
    full["allies"][0].health = 0
    assert necromancy.auto_raise(c, gd, RNG(3), full, enemies) is not None, "名額空出 → 這場那一次還在"


def test_auto_raise_uses_the_thrall_spell_numbers_exactly_hp_power_and_turns():
    for ff in (1.0, 0.4):
        for um in ("undead_dominion", "lasting_summon"):
            a_char = _mage("soul_harvest", um, ff)
            auto = necromancy.auto_raise(a_char, gd, RNG(7), {"allies": []}, [_live(), _corpse("draugr")])
            b_char = _mage("soul_harvest", um, ff)
            battle = {"allies": []}
            assert magic.cast(b_char, gd, "reanimate_thrall", RNG(7), battle=battle, corpses=[_corpse("draugr")], enemies=[])["ok"]
            spell = battle["allies"][0]
            assert (auto.max_health, auto.health, round(auto.summon_power, 9), auto.summon_turns, auto._undead) == \
                   (spell.max_health, spell.health, round(spell.summon_power, 9), spell.summon_turns, True), (ff, um)


# --- ④ run_battle 接線 --------------------------------------------------------------------
def _drive(c, script, foes, carry=None):
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    snaps, queue = [], list(script)
    orig_choose = M._choose_combat_action

    def chooser(state, gamedata, enemies, allies, *a, **k):
        snaps.append({"allies": list(allies), "undead": [x for x in allies if getattr(x, "_undead", False)],
                      "tokens": c.soul_tokens, "raised": [getattr(e, "_reanimated", False) for e in enemies],   # 提示當下的屍體起屍旗標
                      "undead_turns": [x.summon_turns for x in allies if getattr(x, "_undead", False)]})   # 與亡者剩餘回合(物件事後還會變)
        step = queue.pop(0) if queue else {"type": "leave"}
        return step(allies) if callable(step) else step

    msgs, orig_cmsg = [], M._cmsg
    M._choose_combat_action, M._cmsg = chooser, (lambda text, style="white": msgs.append(text))
    try:
        res = M.run_battle(st, gd, foes, carry_allies=carry)
    finally:
        M._choose_combat_action, M._cmsg = orig_choose, orig_cmsg
    _drive.msgs = msgs                                                             # 本場「本回合」戰報(供斷言文字)
    return snaps, res


def _kill_then_flames(victim, target):
    def step(allies):
        victim.health = 0                                                          # 同伴 / 召喚物擊殺(敵方階段前已倒下)
        return {"type": "cast", "spell_id": "flames", "target": target}
    return step


def _flames(target):
    return {"type": "cast", "spell_id": "flames", "target": target}


def test_group_battle_first_fallen_enemy_rises_at_round_end_before_the_summon_clock_and_only_once():
    c = _mage()
    f1, f2, f3 = _live(), _live(), _live("draugr")
    snaps, res = _drive(c, [_kill_then_flames(f1, f2),                              # 第 1 回合:f1 倒下
                            _kill_then_flames(f2, f3),                              # 第 2 回合:f2 也倒下(已起過一次 → 不再起)
                            _flames(f3), {"type": "leave"}], [f1, f2, f3])
    assert res == "fled"
    assert len(snaps[0]["undead"]) == 0
    assert len(snaps[1]["undead"]) == 1 and snaps[1]["undead"][0].name == f1.name and f1._reanimated is True
    assert snaps[1]["undead_turns"] == [6], "起屍在回合末、計時之前:7 回合先起、同回合末 tick −1 = 6"
    raised_msgs = [m for m in _drive.msgs if "重新站起" in m]
    assert len(raised_msgs) == 1 and "(6 回合)" in raised_msgs[0], \
        f"戰報的回合數 = 它實際還能出手的次數(審查 #1:舊版先印 7 後 −1):{raised_msgs}"
    assert not getattr(f2, "_reanimated", False) and len(snaps[2]["undead"]) == 1, "一場一次"
    assert snaps[1]["tokens"] == snaps[0]["tokens"] == 40, "免費:不收靈魂 token"


def test_lone_enemy_never_rises_unselected_never_rises_and_boss_corpse_is_skipped_for_the_next_one():
    c = _mage()                                                                    # 單敵:最後一隻倒下 = 戰鬥結束,不起屍(也不白送勝利回收 token)
    lone = _live()
    def kill_lone(allies):
        lone.health = 0
        return {"type": "rest"}                                                    # 一般動作:本回合照常走完回合末,再由 while 條件結束戰鬥
    snaps, res = _drive(c, [kill_lone], [lone])
    assert res == "victory" and not getattr(lone, "_reanimated", False)
    for choice in (None, "conj_efficiency"):                                       # 未選:群戰第一具倒下也不起
        c = _mage(choice)
        a, b = _live(), _live()
        snaps, _ = _drive(c, [_kill_then_flames(a, b), _flames(b), {"type": "leave"}], [a, b])
        assert not snaps[1]["undead"] and not getattr(a, "_reanimated", False), choice
    c = _mage()                                                                    # 首領屍排第一:略過,起第二具(一場那一次沒被浪費)
    boss, minion, other = combat.spawn_creature(gd, "mehrunes_dagon", RNG(1)), _live(), _live("draugr")
    boss.active_effects.append({"kind": "paralyze", "turns": 10 ** 6})
    def kill_boss_and_minion(allies):
        boss.health = 0
        minion.health = 0
        return _flames(other)
    snaps, _ = _drive(c, [kill_boss_and_minion, _flames(other), {"type": "leave"}], [boss, minion, other])
    assert len(snaps[1]["undead"]) == 1 and snaps[1]["undead"][0].name == minion.name
    assert minion._reanimated is True and not getattr(boss, "_reanimated", False)


def test_full_legion_defers_the_raise_until_a_slot_opens_in_a_real_battle():
    c = _mage()
    cap = necromancy.undead_field_cap(c)
    carry = [_undead_ally() for _ in range(cap)]
    f1, f2, f3 = _live(), _live(), _live("draugr")

    def free_a_slot(allies):
        carry[0].health = 0                                                        # 一具亡者陣亡 → 空出名額(回合末起屍在 tick 移除它之前判定)
        return _flames(f2)

    snaps, _ = _drive(c, [_kill_then_flames(f1, f2), free_a_slot, _flames(f3), {"type": "leave"}], [f1, f2, f3], carry=carry)
    assert len(snaps[1]["undead"]) == cap and snaps[1]["raised"][0] is False, "軍團滿 → 第 1 回合不起,也沒耗掉那一次"
    assert snaps[2]["raised"][0] is True and len(snaps[2]["undead"]) == cap, "空出名額的回合末補起(陣亡那具同回合末移出,總數回到上限)"
    assert any(a.name == f1.name for a in snaps[2]["undead"])


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r203_auto_raise")
