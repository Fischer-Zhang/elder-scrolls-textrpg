"""R203b「永契之僕」(conjuration_100 · opt_id lasting_summon,取代舊持久召喚 +1 回合;使用者 2026-11-22 拍板)。

規則:選了永契之僕時,場上沒有存活契僕 → 下一隻「非亡者、非支援型(bestiary 有 spells,如治療精靈)」召喚物成為契僕
(暫態 `_anchor`,不入檔):`combat.tick_summons` 不遞減其回合 → 戰鬥每輪 / 地城每走一格都不逾時,直到被擊殺;
同時只能有一隻;計入非亡者名額 3。舊 +1 回合取代(Q2),死靈師的亡者不再吃 +1(Q3)。

🔴 守衛:① 預覽 = 實擲(`magic.summon_outcome`)② 資格(首隻 / 排除治療精靈與亡者 / 同時一隻 / 死後遞補)
   ③ 契僕不遞減、其餘照舊逾時、跨地城格與跨戰鬥仍在 ④ 舊 +1 回合確實消失(召喚 / 復生 / 亡者都不再 +1)
   ⑤ 未選者逐位元組同舊(回合數與 rng 軌跡)⑥ HUD 帶 anchor 旗標、施法選單預覽「場上 N/3 · 成為契僕(永駐)」。
"""
import copy

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic, mastery, stats
import tesrpg.ui.console as ui

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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r203_anchor")
