"""地城逃跑回歸:逃離房間/首領戰 → 退出地城,不清剿、不開首領寶箱、不結算任務。

(修 bug『地城逃跑仍可繼續,boss 戰逃跑會判定任務完成、還能開首領寶箱』——
action_dungeon 原本只擋 run_battle=='dead','fled' 落到勝利分支。)"""

import io

from rich.console import Console

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.ui import console as ui
import tesrpg.main as M


def _setup(dloc="cedernoc_cave"):
    gd = get_gamedata()
    c = build_character(gd, name="逃", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.location_id = dloc
    return gd, c, GameState(player=c, time=GameTime(), rng=RNG(5))


def _drive(gd, st, battle_result):
    """跑 action_dungeon,以 battle_result(enemies)→結果 控制戰鬥;記錄開箱 label 與訊息。"""
    saved = (ui.console, ui.confirm, ui.dungeon_room, ui.message, M.run_battle, M._resolve_container)
    labels, msgs = [], []
    ui.console = Console(file=io.StringIO(), width=100)
    ui.confirm = lambda *a, **k: True                                  # 繼續深入 → 是
    ui.dungeon_room = lambda *a, **k: None
    ui.message = lambda *a, **k: msgs.append(a[0] if a else "")
    M.run_battle = lambda state, g, enemies, *a, **k: battle_result(enemies)
    M._resolve_container = lambda state, g, container, label: labels.append(label)
    try:
        ret = M.action_dungeon(st, gd)
    finally:
        (ui.console, ui.confirm, ui.dungeon_room, ui.message, M.run_battle, M._resolve_container) = saved
    return ret, labels, msgs


def test_flee_boss_does_not_clear_or_loot():
    gd, c, st = _setup()
    dgkey = gd.world["locations"][c.location_id]["dungeon"]
    ret, labels, msgs = _drive(gd, st, lambda e: "victory" if isinstance(e, list) else "fled")  # 房間勝、首領逃
    assert ret is None
    assert "首領寶藏" not in labels                        # 不開首領寶箱
    assert dgkey not in c.cleared_dungeons                 # 不計清剿
    assert not any("你肅清了" in m for m in msgs)           # 無「肅清成功」結算


def test_flee_room_exits_dungeon():
    gd, c, st = _setup()
    dgkey = gd.world["locations"][c.location_id]["dungeon"]
    ret, labels, msgs = _drive(gd, st, lambda e: "fled")   # 第一場有敵房間即逃
    assert ret is None
    assert "首領寶藏" not in labels and dgkey not in c.cleared_dungeons


def test_victory_still_clears_and_loots():
    gd, c, st = _setup()
    dgkey = gd.world["locations"][c.location_id]["dungeon"]
    ret, labels, msgs = _drive(gd, st, lambda e: "victory")   # 全勝(回歸防線:正常清剿不受修改影響)
    assert ret is None
    assert "首領寶藏" in labels                             # 開首領寶箱
    assert dgkey in c.cleared_dungeons                      # 正常計清剿
    assert any("你肅清了" in m for m in msgs)


def run():
    test_flee_boss_does_not_clear_or_loot()
    test_flee_room_exits_dungeon()
    test_victory_still_clears_and_loots()


if __name__ == "__main__":
    run()
    print("test_dungeon OK")
