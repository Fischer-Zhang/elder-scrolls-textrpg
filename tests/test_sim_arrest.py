"""sim_arrest.py(R227 前置量測工具)與遊戲本體的同步守衛。

腳本為了模擬反抗戰,複製了 main.guard_confrontation 的「衛兵數 / 隊長」規則;main 改了而腳本沒跟 → 量測悄悄失真。
這裡以真實的 guard_confrontation(patch run_battle 攔截生成的衛兵)對照腳本的 guard_cfg_for。
"""
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

import sim_arrest as SAR
from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import crime

gd = get_gamedata()


def _guards_for(bounty):
    c = build_character(gd, name="賊", sex="male", race="imperial", birthsign="shadow", class_id="thief")
    c.location_id = "whiterun"
    prov = crime.province_of(c, gd)
    c.bounties[prov] = bounty
    st = GameState(player=c, time=GameTime(), rng=RNG(3))
    seen = {}
    saved = (ui.menu, ui.message, ui.show_events, M.run_battle)
    ui.menu = lambda title, options, allow_back=False, **k: "resist"
    ui.message = ui.show_events = lambda *a, **k: None
    M.run_battle = lambda state, gamedata, guards, *a, **k: (seen.setdefault("g", [g.template_id for g in guards]), "fled")[1]
    try:
        M.guard_confrontation(st, gd)
    finally:
        ui.menu, ui.message, ui.show_events, M.run_battle = saved
    return seen["g"]


def test_sim_guard_roster_matches_the_real_resist_branch():
    for bounty in (1, 79, 80, 159, 160, 400, 699, 700, 2000):
        assert _guards_for(bounty) == SAR.GUARD_CFG[SAR.guard_cfg_for(bounty)], bounty


def test_sim_uses_the_real_constants_not_copies():
    assert SAR.crime is crime and SAR.crime.SHOP_REFUSE_BOUNTY == 300 and SAR.crime.GUARD_KILL_BOUNTY == 700
    assert SAR.GUARD_CFG["cap3"][0] == "city_captain" and len(SAR.GUARD_CFG["g3"]) == 3


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
