"""R203b「永契之僕」(conjuration_100 · opt_id lasting_summon,取代舊持久召喚 +1 回合;使用者 2026-11-22 拍板)。

規則:選了永契之僕時,場上沒有存活契僕 → 下一隻「非亡者、非支援型(bestiary 有 spells,如治療精靈)」召喚物成為契僕
(暫態 `_anchor`,不入檔):`combat.tick_summons` 不遞減其回合 → 戰鬥每輪 / 地城每走一格都不逾時,直到被擊殺;
同時只能有一隻;計入非亡者名額 3。舊 +1 回合取代(Q2),死靈師的亡者不再吃 +1(Q3)。

🔴 守衛:① 預覽 = 實擲(`magic.summon_outcome`)② 資格(首隻 / 排除治療精靈與亡者 / 同時一隻 / 死後遞補)
   ③ 契僕不遞減、其餘照舊逾時、跨地城格與跨戰鬥仍在 ④ 舊 +1 回合確實消失(召喚 / 復生 / 亡者都不再 +1)
   ⑤ 未選者逐位元組同舊(回合數與 rng 軌跡)⑥ HUD 帶 anchor 旗標、施法選單預覽「場上 N/3 · 成為契僕(永駐)」。
"""
import copy
import io

from rich.console import Console

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, mastery, stats
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)   # 戰鬥戰報不洗版(同其他戰鬥測試)

gd = get_gamedata()


def _mage(choice="lasting_summon"):
    c = build_character(gd, name="召", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills.update(conjuration=100)
    c.attributes.update(intelligence=100, willpower=100)
    c.spells = ["conjure_dremora", "conjure_healer", "conjure_flame_atronach", "conjure_frost_atronach",
                "conjure_familiar", "raise_thrall", "reanimate_thrall"]
    c.max_magicka = c.magicka = 5000
    if choice:
        c.mastery_choices["conjuration_100"] = choice
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = c.max_magicka = 5000
    c.fatigue = c.max_fatigue
    c.soul_tokens = 40
    return c


def _cast(c, sid, battle, seed=3):
    res = magic.cast(c, gd, sid, RNG(seed), battle=battle)
    assert res["ok"], (sid, res)
    return battle["allies"][-1]


def _ally(template="summoned_dremora", turns=5, anchor=False, hp=None):
    a = combat.spawn_creature(gd, template, RNG(1))
    a.summon_turns = turns
    if anchor:
        a._anchor = True
    if hp is not None:
        a.health = hp
    return a


# --- ① 預覽 = 實擲 -------------------------------------------------------------------
def test_summon_outcome_preview_equals_what_the_real_cast_produces():
    spells = ["conjure_dremora", "conjure_healer", "conjure_flame_atronach", "conjure_familiar", "raise_thrall"]
    seen_anchor = seen_plain = 0
    for choice in ("lasting_summon", "undead_dominion", None):
        for pre_anchor in (False, True):
            for sid in spells:
                c = _mage(choice)
                battle = {"allies": [_ally(anchor=True)] if pre_anchor else []}
                eff = gd.spells[sid]["effect"]
                predicted = magic.summon_outcome(c, gd, eff, battle)
                ally = _cast(c, sid, battle)
                assert ally.summon_turns == predicted["turns"], (choice, pre_anchor, sid)
                assert bool(getattr(ally, "_anchor", False)) == predicted["anchor"], (choice, pre_anchor, sid, predicted)
                seen_anchor += predicted["anchor"]
                seen_plain += not predicted["anchor"]
    assert seen_anchor >= 3 and seen_plain >= 15, "夾具要同時涵蓋成為契僕與不成為(否則空轉)"


# --- ② 資格 ----------------------------------------------------------------------------
def test_anchor_eligibility_first_combat_summon_only_one_at_a_time_and_succession():
    c = _mage()
    battle = {"allies": []}
    healer = _cast(c, "conjure_healer", battle)                 # 支援型:不成為契僕
    assert not getattr(healer, "_anchor", False)
    thrall = _cast(c, "raise_thrall", battle)                   # 真·亡者:不成為契僕
    assert not getattr(thrall, "_anchor", False)
    tank = _cast(c, "conjure_dremora", battle)                  # 第一隻戰鬥型 → 契僕
    assert tank._anchor is True and magic.has_anchor(battle)
    battle2 = {"allies": [tank]}
    second = _cast(c, "conjure_flame_atronach", battle2)        # 已有契僕 → 第二隻不是
    assert not getattr(second, "_anchor", False)
    tank.health = 0                                             # 契僕陣亡 → 下一隻符合資格者成為新契僕
    assert not magic.has_anchor(battle2)
    third = _cast(c, "conjure_frost_atronach", battle2)
    assert third._anchor is True and sum(bool(getattr(a, "_anchor", False)) for a in battle2["allies"]) == 2  # 死的那隻旗標還在但不算
    assert sum(1 for a in battle2["allies"] if getattr(a, "_anchor", False) and combat.is_alive(a)) == 1
    c2 = _mage("undead_dominion")                               # 選了亡者統御 → 不會有契僕
    assert not getattr(_cast(c2, "conjure_dremora", {"allies": []}), "_anchor", False)
    c3 = _mage(None)                                            # 沒選 → 不會有契僕
    assert not getattr(_cast(c3, "conjure_dremora", {"allies": []}), "_anchor", False)


def test_anchor_counts_toward_the_summon_cap_and_message_says_so():
    c = _mage()
    battle = {"allies": []}
    msg = magic.cast(c, gd, "conjure_dremora", RNG(1), battle=battle)["message"]
    assert "契僕" in msg and "回合" not in msg, msg
    magic.cast(c, gd, "conjure_flame_atronach", RNG(2), battle=battle)
    magic.cast(c, gd, "conjure_frost_atronach", RNG(3), battle=battle)
    assert magic.nonundead_summon_count(battle) == 3
    res = magic.cast(c, gd, "conjure_healer", RNG(4), battle=battle)
    assert res["ok"] is False                                   # 契僕佔名額:滿 3 隻後第 4 隻被擋
    plain = magic.cast(_mage(None), gd, "conjure_dremora", RNG(1), battle={"allies": []})["message"]
    assert "契僕" not in plain and "回合" in plain              # 未選者訊息照舊


# --- ③ 契僕不遞減、其餘照舊逾時 -------------------------------------------------------------
def test_anchor_never_expires_while_ordinary_summons_do_across_battle_rounds_and_dungeon_steps():
    c = _mage()
    battle = {"allies": []}
    tank = _cast(c, "conjure_dremora", battle)
    atro = _cast(c, "conjure_flame_atronach", battle)
    turns0 = tank.summon_turns
    for _step in range(40):                                     # 戰鬥每輪 / 地城每走一格:同一個 tick_summons
        battle["allies"], gone = combat.tick_summons(battle["allies"])
    assert tank in battle["allies"] and tank.summon_turns == turns0, "契僕不遞減、不逾時"
    assert atro not in battle["allies"], "非契僕照舊逾時離場"
    tank.health = 0
    battle["allies"], gone = combat.tick_summons(battle["allies"])
    assert tank in gone and tank not in battle["allies"], "被擊殺才會離場"


def test_anchor_survives_between_battles_via_the_dungeon_carry_filter():
    """地城戰後 sync_allies 只留「存活且未逾時」者(summon_turns > 0);契僕回合不遞減 → 恆被保留並帶進下一場。"""
    c = _mage()
    battle = {"allies": []}
    tank = _cast(c, "conjure_dremora", battle)
    for _ in range(25):
        battle["allies"], _ = combat.tick_summons(battle["allies"])
    carried = [a for a in battle["allies"] if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)]
    assert carried == [tank]


# --- ④ 舊 +1 回合確實消失 --------------------------------------------------------------------
def test_old_plus_one_turn_is_gone_for_summons_reanimates_and_undead():
    base = _mage(None)
    picked = _mage("lasting_summon")
    for sid in ("conjure_flame_atronach", "conjure_healer", "raise_thrall"):
        a0 = _cast(base, sid, {"allies": []})
        a1 = _cast(picked, sid, {"allies": [_ally(anchor=True)]})     # 已有契僕 → 這隻不是契僕,可比回合數
        assert a1.summon_turns == a0.summon_turns, (sid, a0.summon_turns, a1.summon_turns)
    sm = mastery.summon_mod(picked, gd)
    assert sm.get("anchor") == 1 and not sm.get("turn_bonus")


# --- ⑤ 未選者逐位元組同舊 ---------------------------------------------------------------------
def test_unselected_players_are_untouched_turns_and_rng_trail_identical():
    for other in (None, "undead_dominion"):
        c1, c2 = _mage(other), _mage(None)
        for sid in ("conjure_dremora", "conjure_flame_atronach", "conjure_healer", "raise_thrall"):
            r1, r2 = RNG(11), RNG(11)
            b1, b2 = {"allies": []}, {"allies": []}
            magic.cast(c1, gd, sid, r1, battle=b1)
            magic.cast(c2, gd, sid, r2, battle=b2)
            assert b1["allies"][0].summon_turns == b2["allies"][0].summon_turns
            assert not getattr(b1["allies"][0], "_anchor", False)
            assert r1.random() == r2.random(), "rng 消耗次序必須相同(summon_outcome 不碰 rng)"


# --- ⑥ HUD 與施法選單預覽 ----------------------------------------------------------------------
def test_hud_payload_flags_the_anchor_and_spell_labels_preview_slots_and_anchor():
    anchored, plain = _ally(anchor=True), _ally("summoned_flame_atronach", turns=4)
    st = ui._allies_status([anchored, plain])
    assert st[0]["anchor"] is True and st[1]["anchor"] is False and st[1]["turns"] == 4
    c = _mage()
    s0 = M._summon_slot_suffix(c, gd, "conjure_dremora", [])
    assert "場上 0/3" in s0 and "成為契僕(永駐)" in s0, s0
    s1 = M._summon_slot_suffix(c, gd, "conjure_flame_atronach", [anchored])
    assert "場上 1/3" in s1 and "契僕" not in s1, s1
    assert "契僕" not in M._summon_slot_suffix(c, gd, "conjure_healer", []), "治療精靈不會成為契僕,不預告"
    assert M._summon_slot_suffix(c, gd, "raise_thrall", []) == "", "亡者不受非亡者名額 / 契僕影響"
    assert M._summon_slot_suffix(c, gd, "flames", []) == "", "非召喚法術不加後綴"


def test_full_slots_label_drops_the_anchor_promise_and_effect_text_says_permanent_only_when_it_will_anchor():
    """審查 #3:名額滿時實際施放會被拒,標籤不得預告「成為契僕」;作用摘要對將成為契僕者標「永駐」而非基礎回合數。"""
    c = _mage()
    full = [_ally(turns=8) for _ in range(3)]
    lbl = M._summon_slot_suffix(c, gd, "conjure_dremora", full)
    assert "場上 3/3" in lbl and "已滿" in lbl and "契僕" not in lbl, lbl
    assert M._summon_will_anchor(c, gd, "conjure_dremora", full) is False
    assert M._summon_will_anchor(c, gd, "conjure_dremora", []) is True
    assert M._summon_will_anchor(c, gd, "conjure_dremora", [_ally(anchor=True)]) is False, "已有契僕 → 不會再成為契僕"
    assert M._summon_will_anchor(c, gd, "conjure_healer", []) is False and M._summon_will_anchor(c, gd, "raise_thrall", []) is False
    assert M._summon_will_anchor(_mage(None), gd, "conjure_dremora", []) is False
    # 實際行為對帳:滿額被拒、有位才成為契僕
    assert magic.cast(c, gd, "conjure_dremora", RNG(1), battle={"allies": list(full)})["ok"] is False
    battle = {"allies": []}
    assert magic.cast(c, gd, "conjure_dremora", RNG(1), battle=battle)["ok"] and battle["allies"][0]._anchor
    # 作用摘要
    t_anchor = M._spell_effect_text(c, gd, "conjure_dremora", [])
    assert "永駐" in t_anchor and "回合" not in t_anchor, t_anchor
    for sid, allies in (("conjure_dremora", [_ally(anchor=True)]), ("conjure_healer", []), ("conjure_dremora", full)):
        t = M._spell_effect_text(c, gd, sid, allies)
        assert "永駐" not in t and "回合" in t, (sid, t)
    assert "回合" in M._spell_effect_text(_mage(None), gd, "conjure_dremora", [])
    assert ui.spell_effect_summary(gd, "conjure_dremora") == M._spell_effect_text(_mage(None), gd, "conjure_dremora", []), "預設參數行為不變"


def test_sim_party_summoner_loop_uses_the_shared_tick_so_anchors_do_not_expire_there():
    """審查 #4:sim_party.fight_summoner 曾自寫遞減迴圈(不認契僕),R203 的 tick_summons 單一出處有第二份漏網。"""
    import sim_party as sp
    calls = []
    orig = combat.tick_summons
    combat.tick_summons = lambda allies: calls.append(len(allies)) or orig(allies)
    try:
        sp.fight_summoner("mehrunes_dagon", 3, max_rounds=3)
    finally:
        combat.tick_summons = orig
    assert calls, "fight_summoner 的回合末召喚時效必須走 combat.tick_summons"


def test_codex_and_buffs_catalog_name_the_three_r203_options_exactly_as_the_data_does():
    """審查 #5:新機制要進 codex / BUFFS.md(同類 R194 有);名稱以 mastery.json 為準,日後改名這裡會亮燈。"""
    import json
    import os
    names = {o["opt_id"]: o["name"] for n in gd.mastery if n["id"] in ("conjuration_75", "conjuration_100") for o in n["options"]}
    for opt in ("lasting_summon", "conj_efficiency", "soul_harvest"):
        assert names[opt] in ("永契之僕", "瞬發契印", "就地起屍"), names[opt]
    codex_text = json.dumps(gd.codex, ensure_ascii=False)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    buffs_text = open(os.path.join(root, "BUFFS.md"), encoding="utf-8").read()
    for opt in ("lasting_summon", "conj_efficiency", "soul_harvest"):
        assert names[opt] in codex_text, f"codex 缺「{names[opt]}」"
        assert names[opt] in buffs_text, f"BUFFS.md 缺「{names[opt]}」"
    for stale in ("持久召喚", "召喚精算", "亡者收集"):
        assert stale not in codex_text, f"codex 殘留舊名「{stale}」"


# --- 地城跨戰(使用者 2026-11-22 拍板「寫回並跨戰留存」)---------------------------------------------
def _dungeon_battle(c, script, dungeon_allies, kill=None):
    """地城式呼叫 `run_battle(carry_allies=dungeon_allies, preserve_buffs=True)`;script 的每項是 action dict 或 callable(allies)→action。
    kill = 敵人;腳本跑完後把它打死(走正常勝利收尾 → 寫回邏輯在迴圈結束後)。回傳 (結果, 每次提示當下的盟友清單快照)。"""
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    foe = kill if kill is not None else combat.spawn_creature(gd, "bandit", RNG(1))
    foe.health = foe.max_health = 10 ** 6
    foe.resist = {}
    foe.active_effects.append({"kind": "paralyze", "turns": 10 ** 6})              # 麻痺哨兵:敵方階段跳過 → 走向全由腳本決定
    queue, seen = list(script), []
    orig = M._choose_combat_action

    def chooser(state, gamedata, enemies, allies, *a, **k):
        seen.append(list(allies))
        if queue:
            step = queue.pop(0)
            return step(allies) if callable(step) else step
        foe.health = 0                                                              # 腳本用完:讓這一輪打死敵人 → 勝利
        return {"type": "rest"}

    M._choose_combat_action = chooser
    try:
        res = M.run_battle(st, gd, [foe], carry_allies=dungeon_allies, preserve_buffs=True)
    finally:
        M._choose_combat_action = orig
    return res, seen


def _sync(dungeon_allies):
    """與 main 地城 sync_allies 同一條濾法(戰後只留存活且未逾時者)。"""
    dungeon_allies[:] = [a for a in dungeon_allies if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)]


def test_anchor_summoned_during_a_dungeon_battle_is_written_back_and_fights_the_next_battle_too():
    c = _mage()
    dungeon_allies = []
    res, seen = _dungeon_battle(c, [{"type": "cast", "spell_id": "conjure_dremora"}], dungeon_allies)
    assert res == "victory"
    anchors = [a for a in dungeon_allies if getattr(a, "_anchor", False)]
    assert len(anchors) == 1 and combat.is_alive(anchors[0]), "戰鬥中召出、戰後存活的契僕寫回地城盟友清單"
    turns0 = anchors[0].summon_turns
    _sync(dungeon_allies)
    assert dungeon_allies == [anchors[0]] and dungeon_allies[0] is anchors[0], "地城 sync_allies 濾法留得住它(回合不遞減 → 恆 > 0)"
    res2, seen2 = _dungeon_battle(c, [], dungeon_allies)                            # 下一戰:契僕自動在場、回合仍不變
    assert res2 == "victory" and any(a is anchors[0] for a in seen2[0]), "下一場開打時契僕已在戰列"
    assert anchors[0].summon_turns == turns0
    _sync(dungeon_allies)
    assert any(a is anchors[0] for a in dungeon_allies), "直到被擊殺前一路跟著"
    anchors[0].health = 0
    _sync(dungeon_allies)
    assert dungeon_allies == [], "被擊殺才離場"


def test_only_a_living_anchor_is_written_back_not_plain_summons_nor_a_dead_anchor_and_never_twice():
    c = _mage()
    # 非契僕(第二隻元素 / 治療精靈 / 亡者)戰後照舊消散;契僕本身寫回一次
    dungeon_allies = []
    res, _ = _dungeon_battle(c, [{"type": "cast", "spell_id": "conjure_dremora"}, {"type": "cast", "spell_id": "conjure_flame_atronach"},
                                 {"type": "cast", "spell_id": "conjure_healer"}, {"type": "cast", "spell_id": "raise_thrall"}], dungeon_allies)
    assert res == "victory" and [bool(getattr(a, "_anchor", False)) for a in dungeon_allies] == [True], "只寫回契僕本身"
    # 契僕在戰中陣亡 → 不寫回
    dungeon_allies = []

    def kill_anchor(allies):
        for a in allies:
            if getattr(a, "_anchor", False):
                a.health = 0
        return {"type": "rest"}

    res, _ = _dungeon_battle(c, [{"type": "cast", "spell_id": "conjure_dremora"}, kill_anchor], dungeon_allies)
    assert res == "victory" and dungeon_allies == []
    # 預召喚的契僕本來就在清單 → 戰後清單裡仍恰好一份(不重複寫回)
    dungeon_allies = []
    pre = {"allies": dungeon_allies}
    assert magic.cast(c, gd, "conjure_dremora", RNG(1), battle=pre)["ok"] and dungeon_allies[0]._anchor
    res, _ = _dungeon_battle(c, [], dungeon_allies)
    assert res == "victory" and len(dungeon_allies) == 1 and dungeon_allies[0]._anchor


def test_write_back_compares_by_identity_not_by_dataclass_equality_and_wilderness_battles_do_not_write_back():
    """Creature 是 dataclass:`x in list` 以欄位相等判斷。清單裡有一隻與新契僕「數值全同」的別隻時,仍要寫回新契僕。
    孿生體必須在**最後一回合**才植入(之前植入會被後續回合改動而不再相等 → 測試空轉:曾有突變存活)。"""
    import copy
    c = _mage()
    dungeon_allies = []
    holder = {}
    foe = combat.spawn_creature(gd, "bandit", RNG(1))

    def plant_twin_then_win(allies):
        anchor = next(a for a in allies if getattr(a, "_anchor", False))
        twin = copy.copy(anchor)
        twin.active_effects = list(anchor.active_effects)
        del twin._anchor                                                             # 動態屬性不在 dataclass 欄位 → twin == anchor 為 True,但不是同一隻
        dungeon_allies.append(twin)                                                  # 模擬地城清單裡已有一隻數值全同的普通召喚物
        holder["anchor"], holder["twin"] = anchor, twin
        foe.health = 0                                                               # 這一輪打死敵人 → 勝利收尾(寫回在迴圈結束後)
        return {"type": "rest"}

    res, _ = _dungeon_battle(c, [{"type": "cast", "spell_id": "conjure_dremora"}, plant_twin_then_win], dungeon_allies, kill=foe)
    assert res == "victory"
    assert holder["twin"] == holder["anchor"] and holder["twin"] is not holder["anchor"], "前提:收尾時兩者仍欄位相等(否則本測試空轉)"
    assert any(a is holder["anchor"] for a in dungeon_allies), "身分比對:新契僕仍被寫回(相等判斷會誤以為已在清單)"
    # 野外戰鬥:carry_allies=None → 不寫回、不出錯(召喚物隨戰鬥結束消散)
    st = GameState(player=_mage(), rng=RNG(3), time=GameTime())
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.health = foe.max_health = 10 ** 6
    foe.active_effects.append({"kind": "paralyze", "turns": 10 ** 6})
    queue = [{"type": "cast", "spell_id": "conjure_dremora"}]
    orig = M._choose_combat_action
    M._choose_combat_action = lambda state, gamedata, enemies, allies, *a, **k: queue.pop(0) if queue else (setattr(foe, "health", 0) or {"type": "rest"})
    try:
        assert M.run_battle(st, gd, [foe]) == "victory"
    finally:
        M._choose_combat_action = orig


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r203_anchor")
