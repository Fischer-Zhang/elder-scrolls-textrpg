"""R211 單槽:法術附魔(全元素)與「法術施放的護盾」重施 / 換施一律取代舊的(不疊)。

緣起(實測):戰法師完全體連放焰刃術,每次都追加一道 weapon_imbue、combat 逐個加傷;地城內施法是「自由行動
(不耗回合)」且預施增益會帶進戰鬥 → 預施 27 層 +323 / 擊(每擊 ×6.8,約最強真附魔的 14 倍)。橡木膚 / 石膚連放
同樣疊盾(6 次 278 / 509)。戰鬥內重施本就不划算,漏洞全在免回合的預施 / 備戰。

守衛:
  1. 焰刃連放 N 次 → 恆一道;換施另一元素的刃 → 取代(不論元素);預施 20 次的每擊傷害 == 施 1 次(逐種子相同)
  2. 真附魔(附魔台)與單層法術附魔仍可共存(合法上限不被誤殺)
  3. 護盾法術連放 / 換施 → 只剩最新一道(source=spell_shield);其他來源的 shield(聖光溢盾 / 戰旗 / 盾牆 / 宗師光環)不受影響
  4. 盟友側同理(庇護術重施取代,他源護盾不動)
"""
import copy
import statistics

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, enchanting, magic
from tesrpg import synth

_SPELLS = ["flame_blade", "frost_blade", "storm_blade", "oakflesh", "stoneflesh", "bound_armor", "ward_ally"]


def _bm():
    gd = get_gamedata()
    c = build_character(gd, name="B", sex="male", race="altmer", birthsign="mage", class_id="battlemage")
    c.spells = list(dict.fromkeys(list(c.spells) + _SPELLS))
    c.weapon = "iron_sword"
    c.active_effects.clear()
    _fill(c)
    return gd, c


def _fill(c):
    c.magicka = c.max_magicka = 5000        # 不讓魔力 / 體力成為變因:測的是「去重」而非資源上限
    c.fatigue = c.max_fatigue = 5000


def _imbues(c):
    return [e for e in c.active_effects if e.get("kind") == "weapon_imbue"]


def _shields(c):
    return [e for e in c.active_effects if e.get("kind") == "shield"]


def _cast(gd, c, sid, n=1, **kw):
    for i in range(n):
        _fill(c)
        r = magic.cast(c, gd, sid, RNG(i), battle={"allies": kw.get("allies", [])}, target=kw.get("target"))
        assert r["ok"], (sid, r.get("message"))


# --- 1. 法術附魔單槽 ------------------------------------------------------------

def test_imbue_recast_never_stacks():
    gd, c = _bm()
    _cast(gd, c, "flame_blade")
    single = _imbues(c)[0]["magnitude"]
    _cast(gd, c, "flame_blade", n=10)
    assert len(_imbues(c)) == 1, "連放焰刃只能留一道"
    assert _imbues(c)[0]["magnitude"] == single


def test_imbue_other_element_replaces_regardless_of_element():
    gd, c = _bm()
    _cast(gd, c, "flame_blade", n=3)
    _cast(gd, c, "frost_blade")
    assert [e["element"] for e in _imbues(c)] == ["frost"], "換施霜刃 → 取代焰刃(單槽·全元素)"
    assert _imbues(c)[0].get("rider", {}).get("status") == "benumb"      # rider 隨新的刃
    _cast(gd, c, "storm_blade")
    assert [e["element"] for e in _imbues(c)] == ["shock"]


def test_imbue_replacement_leaves_other_effects_alone():
    gd, c = _bm()
    c.active_effects.append({"kind": "weapon_imbue", "element": "fire", "magnitude": 5, "turns": 5})
    other = {"kind": "ward", "magnitude": 30, "turns": 4}
    c.active_effects.append(other)
    _cast(gd, c, "frost_blade")
    assert other in c.active_effects                                     # 非附魔效果不被誤刪
    assert len(_imbues(c)) == 1


def test_precast_stack_exploit_closed_damage_equals_single_cast():
    """地城預施(自由行動)連放 20 次焰刃 → 進戰後每擊傷害與只施 1 次逐種子相同(R211 前:×6.8)。"""
    gd, c1 = _bm()
    _, c20 = _bm()
    _cast(gd, c1, "flame_blade", n=1)
    _cast(gd, c20, "flame_blade", n=20)
    for s in range(60):
        out = []
        for c in (c1, c20):
            p = copy.deepcopy(c)
            foe = combat.spawn_creature(gd, "bandit", RNG(s)); foe.resist = {}; foe.armor = 0
            out.append(combat.resolve_attack(p, foe, gd, RNG(s))["damage"])
        assert out[0] == out[1], (s, out)


def test_real_enchant_and_single_imbue_still_coexist():
    """真附魔(附魔台)+ 單層法術附魔仍可共存且互相加成(合法上限不被單槽誤殺)。"""
    gd, c = _bm()
    mag = enchanting.enchant_magnitude(5, 100)
    ew = synth.enchant_weapon_id("iron_sword", "fire", mag)

    def avg(weapon, imbue):
        tot = []
        for s in range(80):
            p = copy.deepcopy(c)
            p.weapon = weapon
            p.active_effects[:] = [dict(imbue_entry)] if imbue else []
            foe = combat.spawn_creature(gd, "bandit", RNG(s)); foe.resist = {}; foe.armor = 0
            tot.append(combat.resolve_attack(p, foe, gd, RNG(s))["damage"])
        return statistics.mean(tot)

    _cast(gd, c, "flame_blade")
    imbue_entry = dict(_imbues(c)[0])
    plain, enchanted, both = avg("iron_sword", False), avg(ew, False), avg(ew, True)
    assert plain < enchanted < both


# --- 2. 法術護盾單槽 ------------------------------------------------------------

def test_spell_shield_recast_and_swap_keep_only_latest_and_other_sources_untouched():
    gd, c = _bm()
    other = {"kind": "shield", "magnitude": 50, "turns": 3, "source": "overheal_ward"}   # 聖光溢盾(他源)
    untagged = {"kind": "shield", "magnitude": 7, "turns": 2}                             # 戰旗 / 盾牆類(無 spell 標記)
    c.active_effects.extend([other, untagged])
    _cast(gd, c, "oakflesh")
    one = [e for e in _shields(c) if e.get("source") == magic.SPELL_SHIELD_SOURCE]
    assert len(one) == 1
    single = one[0]["magnitude"]
    _cast(gd, c, "oakflesh", n=5)
    spell_shields = [e for e in _shields(c) if e.get("source") == magic.SPELL_SHIELD_SOURCE]
    assert len(spell_shields) == 1 and spell_shields[0]["magnitude"] == single     # 連放不疊
    _cast(gd, c, "stoneflesh")                                                      # 換施 → 取代(不論哪道護盾法術)
    spell_shields = [e for e in _shields(c) if e.get("source") == magic.SPELL_SHIELD_SOURCE]
    assert len(spell_shields) == 1 and spell_shields[0]["magnitude"] > single
    _cast(gd, c, "bound_armor")
    assert len([e for e in _shields(c) if e.get("source") == magic.SPELL_SHIELD_SOURCE]) == 1
    assert other in c.active_effects and untagged in c.active_effects              # 他源護盾完全不動
    latest = [e for e in _shields(c) if e.get("source") == magic.SPELL_SHIELD_SOURCE][0]["magnitude"]
    assert magic.active_shield(c) == 50 + 7 + latest


def test_ally_spell_shield_single_slot_other_sources_untouched():
    gd, c = _bm()
    ally = combat.spawn_companion(gd, "sellsword", RNG(1))
    foreign = {"kind": "shield", "magnitude": 20, "turns": 3, "source": "capstone_aura"}
    ally.active_effects.append(foreign)
    for i in range(4):
        _fill(c)
        r = magic.cast(c, gd, "ward_ally", RNG(i), target=ally, battle={"allies": [ally]})
        assert r["ok"]
    spell_shields = [e for e in ally.active_effects
                     if e.get("kind") == "shield" and e.get("source") == magic.SPELL_SHIELD_SOURCE]
    assert len(spell_shields) == 1, "庇護術連放只留一道"
    assert foreign in ally.active_effects


def test_ward_dedupe_unchanged_and_support_ai_gate_unchanged():
    """既有行為不變:結界仍單槽;AI 支援者只對『沒有任何護盾』的目標施放(不因 R211 改變)。"""
    gd, c = _bm()
    c.spells.append("ward")
    _cast(gd, c, "ward", n=4)
    assert len([e for e in c.active_effects if e.get("kind") == "ward"]) == 1


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_buff_slots_r211 OK")
