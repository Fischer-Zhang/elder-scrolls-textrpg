"""R218 單槽取代的可見性(R216 B4):戰報補「取代了原有的 X」+「↻ 再施」標籤標出耗回合 / 取代。

緣起(R216 對抗審查的未驗證觀察):瞬發護體免費施放後,頂端選單變成「↻ 再施:石膚」,再按會耗一回合並取代剛上的盾,
且無任何提示;R211 / R212 單槽取代舊盾 / 舊刃 / 舊回復時,戰報也一字不提。

守衛:
  1. 純讀 helper:`magic.occupied_slot` 只認法術護盾 / 法術回復(他源不算)、已耗盡 / 已到期不算佔槽;`spell_slot` 只算自身目標的單槽法術
     (同伴護盾 / 群體回復 / 治療不算);`replaced_slot` 不改任何狀態
  2. 戰報:五種單槽(護盾 / 結界 / 兵刃灌注 / 束縛兵刃 / 持續回復)首施不提、重施才提「取代了原有的 X」;他源護盾 / 回復不被取代也不提
  3. 預覽 = 實擲:施放前 `replaced_slot` 回傳的名字 == 施放後戰報提到的名字(逐法術 × 逐狀態對帳)
  4. ↻ 標籤:瞬發在手「瞬發·不耗回合」/ 剛瞬發完「耗回合」/ 佔槽「取代原有 X」;不適用的法術標籤逐字同舊
  5. 併括號:敵方目標法術的附註併進同一組括號,`_split_combat_label` 能拆出 chip(含「重選目標」變體)
"""
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic, stats

gd = get_gamedata()
_ALL = ["stoneflesh", "oakflesh", "ironflesh", "flame_blade", "frost_blade", "bound_sword", "bound_armor",
        "renewal", "ward", "heal", "flames", "ward_ally", "regen_aura"]


def _mage(quick_ward=False, conj_seal=False):
    c = build_character(gd, name="取", sex="male", race="altmer", birthsign="mage", class_id="battlemage")
    c.skills.update(alteration=100, conjuration=100, restoration=60, mysticism=60, destruction=60)
    c.attributes.update(intelligence=100, willpower=100)
    c.spells = list(dict.fromkeys(list(c.spells) + _ALL))
    c.weapon = "iron_sword"
    if quick_ward:
        c.mastery_choices["alteration_75"] = "quick_ward"
    if conj_seal:
        c.mastery_choices["conjuration_75"] = "conj_efficiency"
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.active_effects.clear()
    _fill(c)
    return c


def _fill(c):
    c.magicka = c.max_magicka = 5000
    c.fatigue = c.max_fatigue = 5000


def _cast(c, sid, seed=0):
    _fill(c)
    r = magic.cast(c, gd, sid, RNG(seed), battle={"allies": []}, target=None)
    assert r["ok"], (sid, r)
    return r["message"]


# ---------------------------------------------------------------- 1. 純讀 helper
def test_occupied_slot_counts_only_spell_sourced_shield_and_regen():
    c = _mage()
    c.active_effects.append({"kind": "shield", "magnitude": 30, "turns": 3, "source": "war_banner"})
    c.active_effects.append({"kind": "regen", "magnitude": 4, "turns": 3, "source": "enchant_regen"})
    assert magic.occupied_slot(c, "shield") == "" and magic.occupied_slot(c, "regen") == "", "他源不是法術槽,不會被取代"
    c.active_effects.append({"kind": "shield", "magnitude": 30, "turns": 3, "source": magic.SPELL_SHIELD_SOURCE})
    c.active_effects.append({"kind": "regen", "magnitude": 4, "turns": 3, "source": magic.SPELL_REGEN_SOURCE})
    assert magic.occupied_slot(c, "shield") == "護盾" and magic.occupied_slot(c, "regen") == "持續回復"


def test_occupied_slot_ignores_spent_shield_and_expired_effects():
    c = _mage()
    c.active_effects.append({"kind": "shield", "magnitude": 0, "turns": 3, "source": magic.SPELL_SHIELD_SOURCE})
    c.active_effects.append({"kind": "weapon_imbue", "element": "fire", "magnitude": 5, "turns": 0})
    assert magic.occupied_slot(c, "shield") == "" and magic.occupied_slot(c, "weapon_imbue") == ""


def test_spell_slot_self_target_slot_spells_only():
    sp = gd.spells
    assert magic.spell_slot(sp["stoneflesh"]) == "shield" and magic.spell_slot(sp["bound_armor"]) == "shield"
    assert magic.spell_slot(sp["flame_blade"]) == "weapon_imbue" and magic.spell_slot(sp["bound_sword"]) == "bound_weapon"
    assert magic.spell_slot(sp["ward"]) == "ward" and magic.spell_slot(sp["renewal"]) == "regen"
    for sid in ("ward_ally", "regen_aura", "heal", "flames"):
        assert magic.spell_slot(sp[sid]) is None, f"{sid}:同伴 / 群體 / 治療 / 傷害法術不佔你的單槽"


def test_replaced_slot_is_a_pure_read():
    c = _mage()
    _cast(c, "stoneflesh")
    before = [dict(e) for e in c.active_effects]
    for sid in _ALL:
        magic.replaced_slot(c, gd, sid)
    assert c.active_effects == before and magic.replaced_slot(c, gd, "stoneflesh") == "護盾"


# ---------------------------------------------------------------- 2. 戰報
_SLOT_SPELLS = [("stoneflesh", "護盾"), ("bound_armor", "護盾"), ("flame_blade", "兵刃灌注"),
                ("bound_sword", "束縛兵刃"), ("renewal", "持續回復"), ("ward", "結界")]


def test_first_cast_is_silent_recast_names_what_it_replaced():
    for sid, name in _SLOT_SPELLS:
        c = _mage()
        first = _cast(c, sid)
        assert "取代" not in first, f"{sid}:槽內本來沒有舊效果 → 戰報不提取代:{first!r}"
        again = _cast(c, sid, seed=1)
        assert f"取代了原有的{name}" in again, f"{sid}:重施要提:{again!r}"


def test_cross_spell_replacement_names_the_slot_not_the_spell():
    c = _mage()
    _cast(c, "flame_blade")
    assert "取代了原有的兵刃灌注" in _cast(c, "frost_blade", seed=1), "換施另一元素的刃 → 仍是取代兵刃灌注"
    c2 = _mage()
    _cast(c2, "oakflesh")
    assert "取代了原有的護盾" in _cast(c2, "stoneflesh", seed=1), "換施另一道護盾法術 → 取代護盾"


def test_foreign_source_effects_are_neither_replaced_nor_mentioned():
    c = _mage()
    c.active_effects.append({"kind": "shield", "magnitude": 30, "turns": 3, "source": "war_banner"})
    c.active_effects.append({"kind": "regen", "magnitude": 4, "turns": 3, "source": "enchant_regen"})
    for sid in ("stoneflesh", "renewal"):
        assert "取代" not in _cast(c, sid)
    sources = {e.get("source") for e in c.active_effects}
    assert {"war_banner", "enchant_regen"} <= sources, "他源效果原封不動(取代只動法術槽)"


# ---------------------------------------------------------------- 3. 預覽 = 實擲
def test_preview_matches_the_actual_report_across_states():
    for sid, _name in _SLOT_SPELLS:
        for pre_casts in (0, 1, 2):
            c = _mage()
            for i in range(pre_casts):
                _cast(c, sid, seed=i)
            for other in ("stoneflesh", "frost_blade", "renewal"):     # 再混入別槽的舊效果:不應影響本法術的判定
                if magic.spell_slot(gd.spells[other]) != magic.spell_slot(gd.spells[sid]):
                    _cast(c, other, seed=9)
            preview = magic.replaced_slot(c, gd, sid)
            msg = _cast(c, sid, seed=7)
            assert (f"取代了原有的{preview}" in msg) if preview else ("取代" not in msg), (sid, pre_casts, preview, msg)


# ---------------------------------------------------------------- 4. ↻ 標籤
def _label(c, sid, enemies=(), allies=()):
    mem = {"last": {"type": "cast", "spell_id": sid}, "target": None, "ally": None}
    return M._repeat_option(c, gd, list(enemies), list(allies), mem)


def test_repeat_label_instant_ward_ready_then_spent_then_replacing():
    c = _mage(quick_ward=True)
    name = gd.spells["stoneflesh"]["name"]
    assert _label(c, "stoneflesh") == f"↻ 再施:{name}（瞬發·不耗回合)", "護體未用 → 再按仍是免費的"
    _cast(c, "stoneflesh")
    combat.quick_ward_spend(c)                                     # 模擬 run_battle:剛瞬發完
    assert _label(c, "stoneflesh") == f"↻ 再施:{name}（耗回合·取代原有護盾)", "剛瞬發完:再按耗回合且換掉剛上的盾"


def test_repeat_label_without_mastery_only_flags_the_replacement():
    c = _mage()
    name = gd.spells["stoneflesh"]["name"]
    assert _label(c, "stoneflesh") == f"↻ 再施:{name}", "沒有舊效果也沒有瞬發 → 逐字同舊"
    _cast(c, "stoneflesh")
    assert _label(c, "stoneflesh") == f"↻ 再施:{name}（取代原有護盾)", "沒選瞬發 → 不謊稱耗回合,只標取代"


def test_repeat_label_conjuration_seal_spent_flags_turn_cost():
    c = _mage(conj_seal=True)
    name = gd.spells["bound_armor"]["name"]
    assert _label(c, "bound_armor") == f"↻ 再施:{name}（瞬發·不耗回合)"
    _cast(c, "bound_armor")
    combat.quick_seal_spend(c)
    assert _label(c, "bound_armor") == f"↻ 再施:{name}（耗回合·取代原有護盾)"
    # 契印只管召喚系、護體只管自我護盾:互不串味(護盾法術用掉契印不影響護體資格,反之亦然)
    c2 = _mage(quick_ward=True, conj_seal=True)
    combat.quick_seal_spend(c2)
    assert _label(c2, "stoneflesh").endswith("（瞬發·不耗回合)"), "契印用掉不影響護體的免費額度"


def test_repeat_label_unaffected_spells_are_byte_identical():
    c = _mage(quick_ward=True, conj_seal=True)
    combat.quick_seal_spend(c)
    combat.quick_ward_spend(c)
    heal = gd.spells["heal"]["name"]
    assert _label(c, "heal") == f"↻ 再施:{heal}", "非單槽 / 非瞬發類法術(治療)不受影響"
    assert M._repeat_option(c, gd, [], [], {"last": {"type": "attack"}, "target": None}) == "↻ 再攻（重選目標)"


# ---------------------------------------------------------------- 5. 併括號
def test_enemy_target_hint_merges_into_the_same_bracket_and_splits_into_chips():
    c = _mage()
    flames = gd.spells["flames"]["name"]
    foes = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(2)]
    orig = M._repeat_cast_hint
    M._repeat_cast_hint = lambda *a, **k: "耗回合"
    try:
        two = _label(c, "flames", enemies=foes)
        assert two == f"↻ 再施:{flames}（重選目標·耗回合)", two
        one = _label(c, "flames", enemies=foes[:1])
        assert one == f"↻ 再施:{flames}→{foes[0].name}（耗回合)", one
        for lbl, chip in ((two, "重選目標·耗回合"), (one, "耗回合")):
            verb, chips, note = M._split_combat_label(lbl)
            assert chips and chips[0]["text"] == chip and note == lbl
    finally:
        M._repeat_cast_hint = orig
    # 無附註時與舊標籤逐字同(含「重選目標」變體)
    assert _label(c, "flames", enemies=foes) == f"↻ 再施:{flames}（重選目標)"
    assert _label(c, "flames", enemies=foes[:1]) == f"↻ 再施:{flames}→{foes[0].name}"


def test_new_labels_split_into_chips_losslessly():
    for lbl in ("↻ 再施:石膚（耗回合·取代原有護盾)", "↻ 再施:石膚（瞬發·不耗回合)", "↻ 再施:束縛甲冑（取代原有護盾)"):
        verb, chips, note = M._split_combat_label(lbl)
        assert verb.startswith("↻ 再施:") and note == lbl
        for seg in lbl[lbl.index("（") + 1:-1].split("·"):
            assert seg in chips[0]["text"], (lbl, seg)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_replace_report_r218 OK")
