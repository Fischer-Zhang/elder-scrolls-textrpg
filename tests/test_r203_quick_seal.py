"""R203c「瞬發契印」(conjuration_75 · opt_id conj_efficiency,取代舊「召喚精算」純 −15% 省魔;使用者 2026-11-22 拍板)。

規則:每場戰鬥第一道**召喚系**(conjuration 學派:召喚 / 復生 / 束縛兵刃 / 束縛護甲;亡者仍照付靈魂 token)法術瞬發 ——
選單階段當場施放、**不耗回合**,然後重新提示本回合的真正行動;你的**非亡者**召喚物被**擊殺**後,契印重新凝聚(逾時消散不算;
亡者 / 同伴不算;最多存 1 次);施法失敗(名額已滿 / 無屍體…)不耗契印也不耗回合。兼帶舊 −15% 省魔(Q4)。

🔴 守衛:① 資料 / getter(opt_id 不變、兼帶省魔、未選回 False)② 閘門 `combat.quick_seal_ready`(召喚系才算、用過即關、其他學派不算)
③ 回補謂詞 `quick_seal_recharge`(陣亡的非亡者召喚物才算;逾時 / 亡者 / 同伴 / 未選 / 未用都不算;最多一次)
④ `run_battle` 接線:免費施法不結束回合(tick_summons 計數不變)、第二道照一般施法耗回合、失敗不耗契印、安全閥、
   擊殺回補、每場重置、非召喚系法術不動契印 ⑤ 未選者逐位元組同舊(施法照常耗回合)⑥ 預覽 = 實擲:選單標題 / 標籤 / 戰鬥卡片標籤。
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
from tesrpg.systems import combat, magic, mastery, stats

gd = get_gamedata()
CONJ_SPELLS = sorted(s for s, d in gd.spells.items() if d.get("school") == "conjuration")


def _mage(choice="conj_efficiency", conj=100):
    c = build_character(gd, name="召", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills.update(conjuration=conj, destruction=60)
    c.attributes.update(intelligence=100, willpower=100)
    c.spells = ["conjure_dremora", "conjure_flame_atronach", "conjure_frost_atronach", "conjure_healer", "conjure_familiar",
                "raise_thrall", "reanimate_corpse", "flames"]
    if choice:
        c.mastery_choices["conjuration_75"] = choice
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = c.max_magicka = 5000
    c.fatigue = c.max_fatigue
    c.health = c.max_health = 5000
    c.soul_tokens = 40
    return c


def _foe(hp=10 ** 6):
    """打不死、也不出手的靶(麻痺哨兵:敵方階段整個跳過)→ 戰鬥走向完全由腳本決定,不吃戰鬥 rng。"""
    f = combat.spawn_creature(gd, "bandit", RNG(1))
    f.health = f.max_health = hp
    f.resist = {}
    f.active_effects.append({"kind": "paralyze", "turns": 10 ** 6})
    return f


def _ally(template="summoned_dremora", turns=10, undead=False, hp=None):
    a = combat.spawn_creature(gd, template, RNG(1))
    a.summon_turns = turns
    if undead:
        a._undead = True
    if hp is not None:
        a.health = hp
    return a


def _drive(c, script, foe=None, carry=None, **kw):
    """以腳本取代選單跑 `run_battle`:script 的每項是 action dict 或 callable(allies, snapshot)→action;
    腳本用完回「從容離去」(確定性收尾)。回傳每次提示當下的快照(tick_summons 已呼叫次數 = 已結束的回合數)。"""
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    foe = foe if foe is not None else _foe()
    ticks = [0]
    snaps = []
    queue = list(script)
    orig_choose, orig_tick = M._choose_combat_action, combat.tick_summons

    def counting_tick(allies):
        ticks[0] += 1
        return orig_tick(allies)

    def chooser(state, gamedata, enemies, allies, *a, **k):
        snap = {"ticks": ticks[0], "allies": len(allies), "status": combat.quick_seal_status(c, gd),
                "mana": c.magicka, "tokens": c.soul_tokens, "ally_list": list(allies)}
        snaps.append(snap)
        step = queue.pop(0) if queue else {"type": "leave"}
        return step(allies, snap) if callable(step) else step

    M._choose_combat_action, combat.tick_summons = chooser, counting_tick
    try:
        res = M.run_battle(st, gd, [foe], carry_allies=carry, **kw)
    finally:
        M._choose_combat_action, combat.tick_summons = orig_choose, orig_tick
    return snaps, res


# --- ① 資料 / getter ----------------------------------------------------------------------
def test_node_data_option_id_stable_cost_rider_kept_and_getter_only_when_selected():
    node = next(n for n in gd.mastery if n["id"] == "conjuration_75")
    opts = {o["opt_id"]: o for o in node["options"]}
    assert set(opts) == {"conj_efficiency", "soul_harvest"}                       # opt_id 不變(存檔相容、零遷移)
    o = opts["conj_efficiency"]
    assert o["name"] == "瞬發契印" and o["kind"] == "spell_mod" and o["school"] == "conjuration"
    assert o["quick_seal"] == 1 and abs(o["cost_factor"] - 0.85) < 1e-9           # 機制 + 兼帶舊 −15% 省魔(Q4)
    assert "瞬發" in o["desc"] and "15%" in o["desc"] and "取代舊" not in o["desc"]
    assert mastery.quick_seal(_mage(), gd) is True
    assert mastery.quick_seal(_mage(None), gd) is False
    assert mastery.quick_seal(_mage("soul_harvest"), gd) is False
    assert abs(mastery.spell_cost_factor(_mage(), gd, "conjuration") - 0.85) < 1e-9
    assert mastery.spell_cost_factor(_mage(None), gd, "conjuration") == 1.0
    base, sealed = _mage(None), _mage()
    assert magic.effective_cost(sealed, gd, "conjure_dremora") < magic.effective_cost(base, gd, "conjure_dremora")


# --- ② 閘門 -------------------------------------------------------------------------------
def test_ready_gate_covers_the_whole_conjuration_school_and_nothing_else():
    assert {"conjure_dremora", "raise_thrall", "reanimate_corpse", "bound_sword", "bound_armor"} <= set(CONJ_SPELLS)
    c = _mage()
    for sid in CONJ_SPELLS:
        assert combat.quick_seal_ready(c, gd, sid), sid                          # 召喚 / 復生 / 亡者 / 束縛全算「召喚系」
    for sid, d in gd.spells.items():
        if d.get("school") != "conjuration":
            assert not combat.quick_seal_ready(c, gd, sid), sid                  # 其他學派(毀滅 / 恢復…)不算
    assert not combat.quick_seal_ready(c, gd, "no_such_spell")
    assert combat.quick_seal_status(c, gd) == "available"
    combat.quick_seal_spend(c)
    combat.quick_seal_spend(c)                                                    # 重複記帳不疊(最多存 1 次的結構保證)
    assert sum(e.get("kind") == combat.QUICK_SEAL_SPENT for e in c.active_effects) == 1
    assert combat.quick_seal_status(c, gd) == "spent" and not any(combat.quick_seal_ready(c, gd, s) for s in CONJ_SPELLS)
    for other in (_mage(None), _mage("soul_harvest")):                            # 未選:閘門永遠關、狀態 None
        assert not combat.quick_seal_ready(other, gd, "conjure_dremora") and combat.quick_seal_status(other, gd) is None
    foe = _foe()
    assert not combat.quick_seal_ready(foe, gd, "conjure_dremora") and combat.quick_seal_status(foe, gd) is None   # 非玩家不適用


# --- ③ 回補謂詞 ----------------------------------------------------------------------------
def test_recharge_only_when_a_non_undead_summon_is_killed_never_on_expiry_undead_or_companions():
    def spent():
        c = _mage()
        combat.quick_seal_spend(c)
        return c

    killed = _ally(hp=0)
    expired = _ally(turns=0)                                                      # 逾時消散但還活著
    assert combat.is_alive(expired) and not combat.is_alive(killed)
    undead_dead = _ally("reanimated_thrall", undead=True, hp=0)
    companion_dead = _ally(hp=0)
    companion_dead.summon_turns = None                                            # 同伴:summon_turns 為 None
    anchor_dead = _ally(hp=0)
    anchor_dead._anchor = True
    cases = [([killed], True), ([anchor_dead], True), ([expired], False), ([undead_dead], False), ([companion_dead], False),
             ([expired, undead_dead, companion_dead], False), ([expired, killed], True), ([], False)]
    for gone, want in cases:
        c = spent()
        assert combat.quick_seal_recharge(c, gd, gone) is want, [(a.name, a.health, a.summon_turns) for a in gone]
        assert (combat.quick_seal_status(c, gd) == "available") is want
    c = _mage()                                                                   # 契印沒用過 → 沒東西可回補
    assert combat.quick_seal_recharge(c, gd, [killed]) is False and combat.quick_seal_status(c, gd) == "available"
    c = spent()
    assert combat.quick_seal_recharge(c, gd, [killed, _ally(hp=0)]) is True       # 多隻同時陣亡也只回補一次
    assert combat.quick_seal_recharge(c, gd, [killed]) is False                   # 再來沒有東西可回補(最多存 1 次)
    other = _mage(None)
    other.active_effects.append({"kind": combat.QUICK_SEAL_SPENT, "turns": combat.PERSISTENT_TURNS})
    assert combat.quick_seal_recharge(other, gd, [killed]) is False               # 未選者不處理(殘留標記也不動)


# --- ④ run_battle 接線 --------------------------------------------------------------------
def test_first_summon_is_free_the_round_continues_and_the_second_cast_costs_the_turn():
    c = _mage()
    snaps, res = _drive(c, [{"type": "cast", "spell_id": "conjure_dremora"},          # 免費
                            {"type": "cast", "spell_id": "conjure_flame_atronach"},   # 契印已用 → 一般施法,耗掉本回合
                            {"type": "leave"}])
    assert res == "fled"
    assert [s["ticks"] for s in snaps] == [0, 0, 1], "免費施法不結束回合;第二道照一般施法耗回合(回合末才 tick)"
    assert [s["allies"] for s in snaps] == [0, 1, 2]
    assert [s["status"] for s in snaps] == ["available", "spent", "spent"]
    assert snaps[1]["mana"] < snaps[0]["mana"], "免費 = 不耗回合,不是不耗法力"
    assert not any(e.get("kind") == combat.QUICK_SEAL_SPENT for e in c.active_effects), "離戰整包清,不殘留"


def test_unselected_player_pays_the_turn_for_every_cast_as_before():
    for choice in (None, "soul_harvest"):
        c = _mage(choice)
        snaps, _ = _drive(c, [{"type": "cast", "spell_id": "conjure_dremora"}, {"type": "leave"}])
        assert [s["ticks"] for s in snaps] == [0, 1] and [s["allies"] for s in snaps] == [0, 1], choice
        assert [s["status"] for s in snaps] == [None, None]


def test_free_cast_keeps_the_opening_sneak_attack_and_still_allows_a_real_action_in_the_same_round():
    """免費施法不碰 `opening`(回合末才重設)→ 同一回合的真正行動(此處:攻擊)仍吃開場偷襲。對照:未選者施法後第一擊不再是開場偷襲。"""
    c = _mage()
    foe = _foe(hp=10 ** 6)
    seen = []
    orig = combat.resolve_attack

    def spy(att, tgt, gdata, rng, *a, **k):
        if att is c:
            seen.append(bool(k.get("sneak_attack")))
        return orig(att, tgt, gdata, rng, *a, **k)

    combat.resolve_attack = spy
    try:
        snaps, _ = _drive(c, [{"type": "cast", "spell_id": "conjure_dremora"},
                              lambda allies, snap: {"type": "attack", "target": foe}, {"type": "leave"}], foe=foe)
    finally:
        combat.resolve_attack = orig
    assert seen and seen[0] is True, "免費施法之後的攻擊仍是開場偷襲"
    assert [s["ticks"] for s in snaps][:3] == [0, 0, 1]                              # 攻擊那一下才結束回合


def test_failed_free_cast_costs_nothing_not_the_seal_not_the_turn_and_a_later_success_is_still_free():
    c = _mage()
    full = [_ally(turns=10) for _ in range(3)]                                      # 名額已滿(3 隻非亡者)
    assert magic.nonundead_summon_count({"allies": full}) == 3

    def free_up_slot_then_cast(allies, snap):
        full[0].health = 0                                                          # 一隻陣亡 → 空出名額(回合末才移出,這裡仍在清單)
        return {"type": "cast", "spell_id": "conjure_dremora"}

    snaps, _ = _drive(c, [{"type": "cast", "spell_id": "conjure_dremora"},           # 名額滿 → 拒絕(失敗)
                          {"type": "cast", "spell_id": "reanimate_corpse"},          # 無屍體 → 失敗
                          free_up_slot_then_cast,                                    # 名額空出 → 成功且免費
                          {"type": "leave"}], carry=full)
    assert [s["status"] for s in snaps] == ["available", "available", "available", "spent"], "兩次失敗都沒耗契印"
    assert [s["ticks"] for s in snaps] == [0, 0, 0, 0], "失敗與成功的免費施法都沒結束回合"
    assert snaps[0]["mana"] == snaps[1]["mana"] == snaps[2]["mana"], "失敗不收法力"
    assert snaps[3]["mana"] < snaps[2]["mana"]


def test_retry_cap_safety_valve_turns_the_fourth_failure_into_an_ordinary_cast_that_burns_the_turn():
    from tesrpg.main import QUICK_SEAL_RETRY_CAP
    c = _mage()
    full = [_ally(turns=10) for _ in range(3)]
    script = [{"type": "cast", "spell_id": "conjure_dremora"}] * (QUICK_SEAL_RETRY_CAP + 1) + [{"type": "leave"}]
    snaps, _ = _drive(c, script, carry=full)
    assert [s["ticks"] for s in snaps] == [0] * (QUICK_SEAL_RETRY_CAP + 1) + [1], \
        "連續失敗達上限後,下一次施法照一般施法結算(耗回合)→ 驅動器不會無限空轉"
    assert all(s["status"] == "available" for s in snaps)


def test_a_killed_summon_recharges_the_seal_for_the_next_round_but_expiry_does_not():
    c = _mage()

    def kill_the_summon(allies, snap):
        for a in allies:
            if a.summon_turns is not None:
                a.health = 0                                                         # 敵方階段把它打死(回合末 tick_summons 移出)
        return {"type": "cast", "spell_id": "flames", "target": foe}                 # 一般法術(耗回合)

    foe = _foe()
    snaps, _ = _drive(c, [{"type": "cast", "spell_id": "conjure_dremora"},           # 免費,契印用掉
                          kill_the_summon,                                           # 同回合:召喚物陣亡、施法耗回合
                          {"type": "cast", "spell_id": "conjure_frost_atronach"},    # 下一回合:契印已回補 → 又免費
                          {"type": "leave"}], foe=foe)
    assert [s["status"] for s in snaps] == ["available", "spent", "available", "spent"]
    assert [s["ticks"] for s in snaps] == [0, 0, 1, 1], "回補後的第二次免費施法同樣不耗回合"
    # 對照:召喚物只是逾時消散(還活著)→ 不回補
    c2 = _mage()
    short = _ally(turns=1)
    snaps2, _ = _drive(c2, [{"type": "cast", "spell_id": "conjure_dremora"},
                            {"type": "cast", "spell_id": "flames", "target": foe}, {"type": "leave"}], foe=_foe(), carry=[short])
    assert [s["status"] for s in snaps2] == ["available", "spent", "spent"]
    assert short not in snaps2[2]["ally_list"] and combat.is_alive(short), "它逾時離場、但活著"


def test_undead_deaths_do_not_recharge_but_the_undead_cast_itself_uses_the_seal_and_still_pays_tokens():
    c = _mage()
    base = _mage(None)
    t0 = c.soul_tokens
    foe = _foe()

    def kill_undead_then_flames(allies, snap):
        for a in allies:
            if getattr(a, "_undead", False):
                a.health = 0                                                         # 亡者陣亡(回合末 tick_summons 移出)
        return {"type": "cast", "spell_id": "flames", "target": foe}

    snaps, _ = _drive(c, [{"type": "cast", "spell_id": "raise_thrall"},              # 亡者也算召喚系:免費,token 照付
                          kill_undead_then_flames,
                          {"type": "leave"}], foe=foe)
    assert [s["status"] for s in snaps] == ["available", "spent", "spent"], "亡者陣亡不回補契印"
    assert snaps[1]["ticks"] == 0 and snaps[2]["ticks"] == 1
    paid = t0 - snaps[1]["tokens"]
    _drive(base, [{"type": "cast", "spell_id": "raise_thrall"}, {"type": "leave"}])
    assert paid >= 1 and paid == 40 - base.soul_tokens, "亡者免費施放仍照付靈魂 token(與一般施法同額)"


def test_non_conjuration_casts_never_touch_the_seal():
    c = _mage()
    foe = _foe()
    snaps, _ = _drive(c, [{"type": "cast", "spell_id": "flames", "target": foe},
                          {"type": "cast", "spell_id": "flames", "target": foe}, {"type": "leave"}], foe=foe)
    assert [s["status"] for s in snaps] == ["available"] * 3 and [s["ticks"] for s in snaps] == [0, 1, 2]


def test_every_battle_starts_with_a_fresh_seal_including_dungeon_fights_that_preserve_buffs():
    c = _mage()
    _drive(c, [{"type": "cast", "spell_id": "conjure_dremora"}, {"type": "leave"}])
    snaps, _ = _drive(c, [{"type": "leave"}])
    assert snaps[0]["status"] == "available"                                         # 新的一場又有一次
    c2 = _mage()
    c2.active_effects.append({"kind": combat.QUICK_SEAL_SPENT, "turns": combat.PERSISTENT_TURNS})   # 上一場地城戰鬥殘留
    snaps2, _ = _drive(c2, [{"type": "leave"}], preserve_buffs=True)
    assert snaps2[0]["status"] == "available", "preserve_buffs 入戰剝除本場記帳 → 地城每場都是新的一次"
    c3 = _mage()
    c3.active_effects.append({"kind": combat.QUICK_SEAL_SPENT, "turns": combat.PERSISTENT_TURNS})
    snaps3, _ = _drive(c3, [{"type": "leave"}])
    assert snaps3[0]["status"] == "available"
    assert combat.QUICK_SEAL_SPENT in combat.BATTLE_LOCAL_KINDS and "second_breath_spent" in combat.BATTLE_LOCAL_KINDS


def test_incapacitated_player_gets_no_menu_and_therefore_no_free_cast():
    c = _mage()
    c.active_effects.append({"kind": "paralyze", "turns": 1})
    assert magic.is_incapacitated(c)
    snaps, _ = _drive(c, [{"type": "leave"}], preserve_buffs=True)                   # 一般入戰會清空效果;地城預施路徑才保留麻痺
    assert snaps[0]["ticks"] >= 1, "第一次提示前至少已過一個完整回合(失能回合跳過選單)"
    assert snaps[0]["status"] == "available"


# --- ⑥ 預覽 = 實擲 ------------------------------------------------------------------------
def _spell_menu(c, allies=()):
    """直接跑 `_choose_combat_action` 到施法子選單,擷取標題與選項(暫換 ui.menu,finally 還原)。"""
    seen = {}
    orig = ui.menu

    def fake(title, options, allow_back=False):
        if "施放哪道法術" in title:
            seen["title"], seen["options"] = title, list(options)
            return options[0][0]
        return "cast"

    ui.menu = fake
    try:
        st = GameState(player=c, rng=RNG(3), time=GameTime())
        M._choose_combat_action(st, gd, [_foe()], list(allies))
    finally:
        ui.menu = orig
    return seen


def test_cast_menu_title_and_labels_preview_exactly_what_the_cast_will_do():
    c = _mage()
    seen = _spell_menu(c)
    assert "瞬發契印:可用" in seen["title"]
    labels = dict(seen["options"])
    for sid in ("conjure_dremora", "raise_thrall", "reanimate_corpse"):
        if sid in labels:
            assert "瞬發(不耗回合)" in labels[sid], (sid, labels[sid])
    assert "瞬發" not in labels["flames"], "非召喚系法術不標瞬發"
    for sid in labels:                                                               # 標籤與實際閘門一一對應(預覽 = 實擲)
        assert ("瞬發(不耗回合)" in labels[sid]) == combat.quick_seal_ready(c, gd, sid), sid
    combat.quick_seal_spend(c)
    seen2 = _spell_menu(c)
    assert "瞬發契印:已用" in seen2["title"] and not any("瞬發(不耗回合)" in v for _k, v in seen2["options"])
    seen3 = _spell_menu(_mage(None))
    assert "瞬發" not in seen3["title"] and not any("瞬發" in v for _k, v in seen3["options"]), "未選者選單逐字不變"
    assert seen3["title"] == "施放哪道法術?"


def test_combat_card_tag_shows_available_then_spent_and_the_bookkeeping_marker_stays_hidden():
    c = _mage()
    tags = ui._player_state_tags(c, gd)
    tag = next(t for t in tags if t["s"].startswith("瞬發契印"))
    assert tag["s"] == "瞬發契印 可用" and tag["good"] is True and "召喚系" in tag["tip"]
    combat.quick_seal_spend(c)
    tag2 = next(t for t in ui._player_state_tags(c, gd) if t["s"].startswith("瞬發契印"))
    assert tag2["s"] == "瞬發契印 已用" and tag2["good"] is None
    assert ui._status_tags_list(c) == [] and ui._status_tags(c) == "", "本場已用記帳是隱藏標籤,不洩漏成怪異狀態"
    assert not any(t["s"].startswith("瞬發契印") for t in ui._player_state_tags(_mage(None), gd)), "未選者卡片不顯示"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r203_quick_seal")
