"""R137 格擋姿態(純減傷版):取代整回合「格擋」動作 —— 姿態切換/攻擊稅/物理減傷(不碰命中)/
被命中觸發反擊樹與 block XP/荊棘相容(敵照常打中)。"""

import io

from rich.console import Console

import tesrpg.ui.console as ui

ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

_SEEN_MENUS: list = []
_SCRIPT = {"first": "guard"}


def _menu(title, options, allow_back=False):
    keys = [k for k, _ in options]
    if "你的回合" in title:
        _SEEN_MENUS.append(list(keys))
        if _SCRIPT["first"] and _SCRIPT["first"] in keys:
            act = _SCRIPT["first"]; _SCRIPT["first"] = None
            return act
        return "attack"
    if "攻擊哪個目標" in title:
        return keys[0]
    return keys[0]


ui.menu = _menu

import tesrpg.main as main                            # noqa: E402
from tesrpg.creation import build_character            # noqa: E402
from tesrpg.gamedata import get_gamedata                # noqa: E402
from tesrpg.rng import RNG                               # noqa: E402
from tesrpg.state import GameState, GameTime              # noqa: E402
from tesrpg.systems import combat, inventory, magic, mastery, stats   # noqa: E402
from tesrpg import formulas                                # noqa: E402

gd = get_gamedata()


def _warrior(riposte=False):
    c = build_character(gd, name="盾", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(blade=90, heavy_armor=90, block=100)
    c.attributes.update(strength=90, endurance=100)
    c.weapon = "steel_sword"
    inventory.add_item(c, "steel_sword", 1)
    inventory.add_item(c, "steel_shield", 1)
    inventory.equip_armor(c, gd, "steel_shield")
    if riposte:
        mastery.choose(c, gd, "block_50", "shield_bash")   # 反擊樹:盾擊踉蹌 0.35
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def test_helper_and_toggle():
    c = _warrior()
    assert not combat.has_guard_stance(c)
    c.active_effects.append({"kind": "guard_stance", "turns": 99})
    assert combat.has_guard_stance(c)


def test_stance_pure_mitigation_no_hit_change():
    """姿態=純減傷:同 seed 下敵方命中與否**完全相同**(不碰命中·荊棘流照樣被打中),
    命中時傷害嚴格更低;力竭(fatigue 0)→ 減傷失效(同 seed 同傷)。"""
    def hit_dmg(stance, fatigue=None, seed=0):
        c = _warrior()
        if stance:
            c.active_effects.append({"kind": "guard_stance", "turns": 99})
        if fatigue is not None:
            c.fatigue = fatigue
        foe = combat.spawn_creature(gd, "bandit", RNG(seed))
        ev = combat.resolve_attack(foe, c, gd, RNG(seed * 7 + 1))
        return ev["hit"], ev["damage"]
    hits_plain = [hit_dmg(False, seed=s)[0] for s in range(60)]
    hits_stance = [hit_dmg(True, seed=s)[0] for s in range(60)]
    assert hits_plain == hits_stance                       # 🔴 命中序完全相同(不碰命中)
    for s in range(60):
        h0, d0 = hit_dmg(False, seed=s)
        h1, d1 = hit_dmg(True, seed=s)
        if h0 and d0 > 1:
            assert d1 < d0                                 # 命中時姿態傷害更低(純減傷)
        h2, d2 = hit_dmg(True, fatigue=0, seed=s)
        assert d2 == d0                                    # 力竭 → 減傷失效(同傷)


def test_stance_triggers_riposte_and_block_xp_on_hit():
    """姿態中被命中 → block 反擊樹(盾擊踉蹌)可觸發 + block XP 訓練(learn-by-doing 存續)。"""
    staggered = 0
    for s in range(120):
        c = _warrior(riposte=True)
        c.active_effects.append({"kind": "guard_stance", "turns": 99})
        foe = combat.spawn_creature(gd, "bandit", RNG(s))
        ev = combat.resolve_attack(foe, c, gd, RNG(s * 7 + 1))
        if ev["hit"]:
            staggered += magic.is_staggered(foe)
    assert staggered > 0                                   # 反擊樹在姿態中活著(無需手動格擋)
    c = _warrior()
    c.skills["block"] = 80                                 # 未達 SKILL_CAP 才有 XP 可練
    c.active_effects.append({"kind": "guard_stance", "turns": 99})
    foe = combat.spawn_creature(gd, "bandit", RNG(2))
    xp0 = c.skill_xp.get("block", 0.0)
    for s in range(20):
        combat.resolve_attack(foe, c, gd, RNG(s * 3 + 5))
    assert c.skill_xp.get("block", 0.0) > xp0              # 被命中訓練 block


def test_run_battle_guard_replaces_block():
    """整合:選單不再有「block」、有「guard」切換;立姿態後可勝。"""
    _SEEN_MENUS.clear(); _SCRIPT["first"] = "guard"
    c = _warrior()
    st = GameState(player=c, rng=RNG(9), time=GameTime())
    enemies = [combat.spawn_creature(gd, "bandit", RNG(i + 1)) for i in range(3)]
    assert main.run_battle(st, gd, enemies) == "victory"
    assert _SEEN_MENUS
    for keys in _SEEN_MENUS:
        assert "block" not in keys, "整回合格擋動作應已移除(R137)"
    assert any("guard" in keys for keys in _SEEN_MENUS)


def test_stance_sneak_solo_cap_red_line():
    """紅線:姿態攻擊稅走 damage_factor(倍率前)→ 偷襲對 solo 仍受夾(只會更低)。"""
    c = _warrior()
    c.skills["sneak"] = 100
    c.active_effects.append({"kind": "guard_stance", "turns": 99})
    boss = combat.spawn_creature(gd, "ancient_dragon", RNG(1))
    cap = boss.max_health * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO
    worst = 0
    for s in range(120):
        combat._set_hp(boss, boss.max_health)
        worst = max(worst, combat.resolve_attack(
            c, boss, gd, RNG(s), sneak_attack=True,
            damage_factor=formulas.GUARD_STANCE_DAMAGE_TAX)["damage"])
    assert worst <= cap


def _gs_tank():
    """R138 重盾坦:魔族重盾(盾擊接管攻擊)+ 姿態常駐。"""
    c = build_character(gd, name="重盾", sex="m", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(block=100, heavy_armor=90)
    c.attributes.update(strength=90, endurance=100)
    inventory.add_item(c, "daedric_great_shield", 1)
    inventory.equip_armor(c, gd, "daedric_great_shield")
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def test_great_shield_elemental_guard_r138():
    """R138b 重盾掩體元素卸力(使用者鐵令「格擋不可能防元素比物理多」):元素=姿態卸力×0.70
    (一般盾 ×0.5);**元素卸力恆 ≤ 物理**;gamedata=None(舊呼叫端)→ 一律非重盾路徑(back-compat)。"""
    c = _gs_tank()
    c.active_effects.append({"kind": "guard_stance", "turns": 99})
    m_full = formulas.GUARD_STANCE_MITIGATION                                 # block100 → 物理卸 38%
    f_elem = combat._guard_stance_factor(c, "fire", gd)
    f_phys = combat._guard_stance_factor(c, None, gd)
    assert abs(f_elem - (1.0 - m_full * formulas.GREAT_SHIELD_ELEMENTAL_FACTOR)) < 1e-9   # 元素卸 26.6%
    assert abs(f_phys - (1.0 - m_full)) < 1e-9
    assert f_elem > f_phys                                                    # 🔴 現實邏輯:元素卸力 < 物理(因子更接近 1)
    c.skills["block"] = 50                                                    # 隨 block 縮放
    assert abs(combat._guard_stance_factor(c, "fire", gd)
               - (1.0 - m_full * 0.5 * formulas.GREAT_SHIELD_ELEMENTAL_FACTOR)) < 1e-9
    c.skills["block"] = 100
    w = _warrior()                                                            # 一般盾:元素折半不變
    w.active_effects.append({"kind": "guard_stance", "turns": 99})
    m = formulas.GUARD_STANCE_MITIGATION * formulas.GUARD_STANCE_ELEMENTAL_FACTOR
    assert abs(combat._guard_stance_factor(w, "fire", gd) - (1.0 - m)) < 1e-9
    assert combat._guard_stance_factor(c, "fire", gd) < combat._guard_stance_factor(w, "fire", gd)  # 重盾元素仍優於一般盾
    assert abs(combat._guard_stance_factor(c, "fire") - combat._guard_stance_factor(w, "fire")) < 1e-9  # 無 gamedata → 非重盾路徑


def test_bunker_fatigue_regen_r138():
    """R138 掩體回氣:姿態+重盾 → +2/回;一般盾/未立姿態 → 0;🔴 力竭(fatigue 0)仍回=脫困非死鎖;
    回氣 < 攻擊成本(雜技 75 ≈4.2)→ 邊打邊回不可能(無限姿態否決的數學根據)。"""
    c = _gs_tank()
    assert combat.bunker_fatigue_regen(c, gd) == 0                            # 未立姿態
    c.active_effects.append({"kind": "guard_stance", "turns": 99})
    assert combat.bunker_fatigue_regen(c, gd) == formulas.GREAT_SHIELD_BUNKER_FATIGUE
    c.fatigue = 0
    assert combat.bunker_fatigue_regen(c, gd) == formulas.GREAT_SHIELD_BUNKER_FATIGUE   # 力竭也回(脫困)
    w = _warrior()
    w.active_effects.append({"kind": "guard_stance", "turns": 99})
    assert combat.bunker_fatigue_regen(w, gd) == 0                            # 一般盾無回氣
    atk_cost = formulas.ATTACK_FATIGUE_COST * formulas.fatigue_cost_factor(75) \
        * formulas.weapon_attack_fatigue_factor(1.0)
    assert formulas.GREAT_SHIELD_BUNKER_FATIGUE < atk_cost                    # 🔴 邊打邊回不可能


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
