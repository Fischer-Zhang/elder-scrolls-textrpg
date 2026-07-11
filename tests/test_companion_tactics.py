"""R129 同伴戰術傾向「消費端」回歸(bug 修復):

🔴 原 bug:`companion_tactic` 回 tactic-kind("taunt"/"focus"),但 main.py 消費端比對
build id("bulwark"/"skirmisher")→ 恆 False → 鎮守自施嘲諷 / 游擊集火**從未生效**
(招牌功能死機制)。舊 `test_companion_build` 只驗 getter、未驗消費 → 漏抓。
本模組驗:① party.focus_target 先點治療者/其次最低血;② run_battle 真的執行修好的分支。
"""

import io

from rich.console import Console

import tesrpg.ui.console as ui
import tesrpg.main as main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, party

gd = get_gamedata()


def _dummy(tid, hp):
    e = combat.spawn_creature(gd, tid, RNG(1))
    e.max_health = e.health = hp
    return e


def _player_with_companion(build):
    c = build_character(gd, name="隊", sex="male", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(blade=80, heavy_armor=60)
    c.attributes.update(strength=70, endurance=70)
    c.weapon = "steel_sword"
    c.companions.append("veteran")
    c.companion_bond["veteran"] = party.BOND_TIERS[0]      # 達羈絆門檻
    assert party.choose_build(c, gd, "veteran", build)
    return c


def _menu(title, options, allow_back=False):
    keys = [k for k, _ in options]
    return "attack" if "attack" in keys else keys[0]       # 玩家每回合攻擊第一個目標


def _run(st, enemies):
    saved = (ui.menu, ui.console, ui.message)
    msgs = []
    ui.menu = _menu
    ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)
    ui.message = lambda *a, **k: msgs.append(a[0] if a else "")
    try:
        result = main.run_battle(st, gd, enemies)
    finally:
        ui.menu, ui.console, ui.message = saved
    return result, msgs


# --- party.focus_target 單元(先點治療者·其次最低血)-----------------------
def test_focus_target_prioritizes_support_caster():
    healer = _dummy("moor_witch", 100)     # heal_other → R87 支援施法者
    trash = _dummy("bandit", 5)            # 血更低但非治療者
    assert party.focus_target([trash, healer], gd) is healer   # 先點治療者(即使血較高)


def test_focus_target_lowest_hp_when_no_healer():
    a = _dummy("bandit", 40); b = _dummy("wolf", 12); c = _dummy("skeleton", 25)
    assert party.focus_target([a, b, c], gd) is b              # 無治療者 → 最低血
    assert party.focus_target([], gd) is None                 # 空 → None


# --- 消費端整合(run_battle 真的走修好的分支)-------------------------------
def test_bulwark_companion_taunts_in_battle():
    """鎮守(taunt):同伴戰鬥中自施嘲諷 → 冒出「吸引敵人火力」訊息(原比對恆 False 從不觸發)。"""
    c = _player_with_companion("bulwark")
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    _, msgs = _run(st, [_dummy("bandit", 220)])               # 撐過首回合 → 同伴階段執行
    assert any("吸引敵人火力" in m for m in msgs), "鎮守同伴從未自施嘲諷(R129 bug 回歸)"


def test_skirmisher_companion_focus_fires_healer():
    """游擊(focus):同伴優先集火敵方治療者(原恆 False → 退回隨機目標)。
    🔴 治療者 HP **高於**雜兵 → 選它證明「先點治療者」而非最低血 tiebreak;
    RNG(1) 下 buggy 隨機退路首擊打雜兵 → 此測對 focus 分支 wiring 非空(revert→FAIL 已驗)。"""
    c = _player_with_companion("skirmisher")
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    hits = []
    saved = combat.resolve_attack

    def spy(attacker, defender, *a, **k):
        if getattr(attacker, "template_id", None) == "veteran":
            hits.append(defender.template_id)
        return saved(attacker, defender, *a, **k)

    combat.resolve_attack = spy
    try:
        _run(st, [_dummy("moor_witch", 150), _dummy("bandit", 80)])   # 治療者血更高·仍先被集火
    finally:
        combat.resolve_attack = saved
    assert hits, "游擊同伴從未攻擊(未取得目標)"
    assert hits[0] == "moor_witch", f"游擊未先集火治療者:{hits[:3]}"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_companion_tactics OK")
