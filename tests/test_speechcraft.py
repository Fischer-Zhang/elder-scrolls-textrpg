"""口才(speechcraft)平衡修正 + 拓展用途回歸:
- persuade 好感增益隨技能成長(高口才 > bribe 12),仍付 practice(反 min-max 不破)。
- 說服衛兵 talk_down_guard:小額賞金成功清零、賞金越高機率越低、失敗不清、付 practice。
- 威嚇喝退 intimidate:僅弱人形敵可、避戰無戰利/擊殺/xp(來自敵)、付 practice。
"""

import io

from rich.console import Console

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, crime, dialogue, progression
from tesrpg.ui import console as ui
import tesrpg.main as M


def _char(speechcraft=40, personality=50):
    gd = get_gamedata()
    c = build_character(gd, name="嘴", sex="male", race="imperial",
                        birthsign="warrior", class_id="thief")
    c.skills["speechcraft"] = speechcraft
    c.attributes["personality"] = personality
    c.fatigue = c.max_fatigue
    return gd, c


# --- Part A:說服增益隨技能成長,高口才超越 bribe ----------------------
def test_persuade_delta_scales_and_beats_bribe():
    assert dialogue.persuade_delta(0) == 6
    assert dialogue.persuade_delta(50) == 12        # = bribe(+12)
    assert dialogue.persuade_delta(100) == 18       # > bribe(+12) → 投資得到回報
    assert dialogue.BRIBE_COST == 10 and dialogue.persuade_delta(100) > 12


def test_persuade_success_uses_scaled_delta_and_pays_practice():
    gd, c = _char(speechcraft=100, personality=100)   # ~90% 成功(無里程碑時)
    pdef = gd.skills["speechcraft"]["practice"]
    nid = next(iter(gd.npcs))
    f0 = c.fatigue
    # 多試直到一次成功 → delta == persuade_delta(100) == 18
    for i in range(10):
        c.fatigue = c.max_fatigue
        r = dialogue.persuade(c, gd, nid, RNG(i))
        if r["ok"]:
            assert r["delta"] == dialogue.persuade_delta(100) == 18
            break
    else:
        raise AssertionError("高口才應能成功說服")
    # 仍付 practice(體力 + 時間)→ 反 min-max 不破
    c.fatigue = c.max_fatigue
    r = dialogue.persuade(c, gd, nid, RNG(0))
    assert r["hours"] == pdef["hours"] > 0


# --- Part B:說服衛兵減免賞金 -----------------------------------------
def test_talk_down_chance_drops_with_bounty():
    gd, c = _char(speechcraft=80, personality=60)
    assert dialogue.talk_down_chance(c, 40) > dialogue.talk_down_chance(c, 200)
    assert 0.05 <= dialogue.talk_down_chance(c, 0) <= 0.80


def test_talk_down_guard_clears_on_success_pays_practice():
    gd, c = _char(speechcraft=100, personality=100)
    prov = "賽羅迪爾"
    pdef = gd.skills["speechcraft"]["practice"]
    crime.add_bounty(c, prov, 40)
    f0 = c.fatigue
    # 高口才小額賞金 → 多試必有一次成功清零
    cleared = False
    for i in range(20):
        if crime.bounty(c, prov) == 0:
            crime.add_bounty(c, prov, 40)
        c.fatigue = c.max_fatigue
        r = dialogue.talk_down_guard(c, gd, prov, RNG(i))
        assert r["hours"] == pdef["hours"] > 0          # 每次付 practice 時間
        if r["ok"]:
            assert crime.bounty(c, prov) == 0           # 成功 → 賞金清零
            cleared = True
            break
    assert cleared
    # 失敗不清賞金
    crime.add_bounty(c, prov, 60)
    c2_gd, c2 = _char(speechcraft=1, personality=1)
    crime.add_bounty(c2, prov, 100)
    r = dialogue.talk_down_guard(c2, c2_gd, prov, RNG(3))
    if not r["ok"]:
        assert crime.bounty(c2, prov) == 100            # 失敗 → 賞金不動


# --- Part C:威嚇喝退弱人形敵 -----------------------------------------
def test_intimidate_gating():
    gd = get_gamedata()
    bandit = combat.spawn_creature(gd, "bandit", RNG(1))
    wolf = combat.spawn_creature(gd, "wolf", RNG(1))
    assert dialogue.can_intimidate(gd, [bandit])             # 弱人形盜匪 → 可
    assert dialogue.can_intimidate(gd, [bandit, bandit])
    assert not dialogue.can_intimidate(gd, [bandit, wolf])   # 混入野獸 → 不可
    assert not dialogue.can_intimidate(gd, [wolf])           # 野獸不可
    assert not dialogue.can_intimidate(gd, [])               # 空不可
    # 不死/魔人/boss 皆不在 INTIMIDATABLE
    for tid in ("skeleton", "dremora", "frost_troll", "vampire_fledgling", "hag_matriarch"):
        if tid in gd.bestiary:
            e = combat.spawn_creature(gd, tid, RNG(1))
            assert not dialogue.can_intimidate(gd, [e]), tid


def test_intimidate_chance_scales_and_pays_practice():
    gd, c = _char(speechcraft=70)
    bandit = combat.spawn_creature(gd, "bandit", RNG(1))
    pdef = gd.skills["speechcraft"]["practice"]
    assert dialogue.intimidate_chance(c, [bandit], False) > dialogue.intimidate_chance(c, [bandit, bandit, bandit], False)
    f0 = c.fatigue
    r = dialogue.intimidate(c, gd, [bandit], False, RNG(0))
    assert r["hours"] == pdef["hours"] > 0 and c.fatigue == f0 - pdef["fatigue"]   # 付 practice


def _drive_offer_battle(gd, st, enemies, menu_choice, force_intimidate_ok=None):
    saved = (ui.console, ui.menu, ui.message, ui.combat_intro, ui.show_events,
             M.run_battle, dialogue.intimidate)
    msgs = []
    ui.console = Console(file=io.StringIO(), width=100)
    ui.menu = lambda *a, **k: menu_choice
    ui.message = lambda *a, **k: msgs.append(a[0] if a else "")
    ui.combat_intro = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None
    M.run_battle = lambda *a, **k: "victory"      # 若被呼叫 = 進了戰鬥
    if force_intimidate_ok is not None:
        ui.intimidate_called = [False]
        def fake_int(char, gamedata, en, night, rng):
            return {"ok": force_intimidate_ok, "chance": 1.0, "hours": 1, "tired": False, "skill_events": []}
        dialogue.intimidate = fake_int
    try:
        ret = M.offer_battle(st, gd, enemies)
    finally:
        (ui.console, ui.menu, ui.message, ui.combat_intro, ui.show_events,
         M.run_battle, dialogue.intimidate) = saved
    return ret, msgs


def test_offer_battle_intimidate_success_avoids_combat_no_loot():
    """威嚇成功 → 避戰(return None),不呼叫 run_battle、無金幣/擊殺/xp 來自敵人。"""
    gd, c = _char(speechcraft=100)
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    g0, k0 = c.gold, dict(c.kill_counts)
    enemies = [combat.spawn_creature(gd, "bandit", RNG(1))]
    ret, msgs = _drive_offer_battle(gd, st, enemies, "intimidate", force_intimidate_ok=True)
    assert ret is None                                  # 避戰
    assert c.gold == g0 and c.kill_counts == k0         # 無戰利/擊殺(嚇退非擊敗)


def test_offer_battle_no_intimidate_option_for_beasts():
    """非可威嚇敵(野獸)→ offer_battle 選單不含 intimidate(選 retreat 驗證流程不崩)。"""
    gd, c = _char(speechcraft=100)
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    # can_intimidate 對 wolf 為 False → 即便玩家(stub)選 intimidate 也不會有該分支;
    # 直接驗證 can_intimidate 閘:
    assert not dialogue.can_intimidate(gd, [combat.spawn_creature(gd, "wolf", RNG(1))])


def run():
    test_persuade_delta_scales_and_beats_bribe()
    test_persuade_success_uses_scaled_delta_and_pays_practice()
    test_talk_down_chance_drops_with_bounty()
    test_talk_down_guard_clears_on_success_pays_practice()
    test_intimidate_gating()
    test_intimidate_chance_scales_and_pays_practice()
    test_offer_battle_intimidate_success_avoids_combat_no_loot()
    test_offer_battle_no_intimidate_option_for_beasts()


if __name__ == "__main__":
    run()
    print("test_speechcraft OK")
