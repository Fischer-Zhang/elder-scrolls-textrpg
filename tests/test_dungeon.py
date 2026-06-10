"""格子探索地城(程序化 n×n × m 層,原子探索)的測試:

生成合法性(連通/樓梯+boss 可達/入口/id 合法)、衝 boss 勝利 → 肅清 + 寶藏自動解鎖
(免開鎖器)、逃跑/離開不計清剿、零新存檔欄。承既有「逃跑不誤判清剿」回歸防線。
"""

from collections import deque

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import dungeoncrawl as DC
from tesrpg.ui import console as ui
import tesrpg.main as M


def _char(dloc="cedernoc_cave"):
    gd = get_gamedata()
    c = build_character(gd, name="探", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    loc = next(l for l, n in gd.world["locations"].items() if n.get("dungeon") == dloc)
    c.location_id = loc
    return gd, c, GameState(player=c, time=GameTime(), rng=RNG(11))


# --- 生成合法性 ---------------------------------------------------------
def test_generate_all_valid():
    gd = get_gamedata()
    for did, spec in gd.dungeons.items():
        for seed in (1, 7, 42, 99, 2024):                                 # 多種子:生成對任意 RNG 皆合法
            g = DC.generate(spec, gd, RNG(seed))
            n, m = g["n"], g["m"]
            assert g["layers"][0][0][0]["type"] == DC.ENTRANCE, did       # 入口在 (0,0) layer0
            for z in range(m):
                reach = DC.reachable_cells(g, z)
                assert len(reach) == n * n, (did, z, seed)                # 開放格 → 全連通
                target = DC.STAIRS if z < m - 1 else DC.BOSS
                cell = DC.find_cell(g, z, target)
                assert cell is not None and cell in reach, (did, z, target, seed)  # 樓梯/boss 必存在且可達
        for tid in spec["monsters"]:                                      # id 合法性檢查跑一次即可
            assert tid in gd.bestiary, (did, tid)
        assert spec["boss"]["enemy"] in gd.bestiary, did
        for x in spec.get("loot", []):
            assert gd.item_or_none(x) is not None, (did, x)
        for x in spec["boss"]["treasure"]["loot"]:
            if isinstance(x, str):
                assert gd.item_or_none(x) is not None, (did, x)


# --- crawl 驅動 ----------------------------------------------------------
def _run(gd, st, battle_result, navigate=True):
    """以 patched ui 跑 action_dungeon;navigate=True 時自動往 樓梯→下層→boss 前進。
    battle_result(foes)→ 'victory'|'fled'|'dead'(foes 為 list=一般格、單一 Creature=boss)。"""
    stash = {}
    real_gen = DC.generate
    def gen(spec, g, rng):
        grid = real_gen(spec, g, rng); stash["g"] = grid; stash.update(z=0, x=0, y=0); return grid
    def step(grid, z, sx, sy, goal):
        if goal is None:
            return None
        q = deque([(sx, sy, None)]); seen = {(sx, sy)}
        while q:
            x, y, first = q.popleft()
            if (x, y) == goal:
                return first
            for k, _l, nx, ny in DC.neighbors(grid, x, y):
                if (nx, ny) not in seen:
                    seen.add((nx, ny)); q.append((nx, ny, first or k))
        return None
    def menu(title, opts, allow_back=False):
        if not navigate:
            return "leave"
        g = stash["g"]; z, x, y = stash["z"], stash["x"], stash["y"]
        goal = DC.find_cell(g, z, DC.STAIRS) if z < g["m"] - 1 else DC.find_cell(g, z, DC.BOSS)
        if (x, y) == goal and any(o[0] == "descend" for o in opts):
            stash.update(z=z + 1, x=0, y=0); return "descend"
        s = step(g, z, x, y, goal)
        if s:
            for k, _l, nx, ny in DC.neighbors(g, x, y):
                if k == s:
                    stash.update(x=nx, y=ny); break
            return "go:" + s
        return "leave"
    saved = (ui.menu, ui.message, ui.dungeon_grid, ui.loot_report, ui.confirm, ui.rule,
             ui.show_events, M.run_battle, DC.generate)
    ui.menu = menu
    ui.message = ui.dungeon_grid = ui.loot_report = ui.rule = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True
    M.run_battle = lambda state, g, foes, *a, **k: battle_result(foes)
    DC.generate = gen
    try:
        return M.action_dungeon(st, gd)
    finally:
        (ui.menu, ui.message, ui.dungeon_grid, ui.loot_report, ui.confirm, ui.rule,
         ui.show_events, M.run_battle, DC.generate) = saved


def test_clear_on_boss_victory_and_auto_loot_treasure():
    gd, c, st = _char()
    did = gd.world["locations"][c.location_id]["dungeon"]
    c.inventory = [it for it in c.inventory if it["id"] != "lockpick"]   # 身上無開鎖器
    gold0 = c.gold
    ret = _run(gd, st, lambda foes: "victory")
    assert ret is None
    assert did in c.cleared_dungeons                                    # 肅清計入
    assert c.gold > gold0                                               # boss 寶藏自動入袋(免開鎖器)


def test_recleared_dungeon_grants_no_guaranteed_loot():
    """反刷寶:已肅清地城重訪 → boss 重生可再戰,但寶藏/寶箱皆已搬空(不再給保證戰利品)。"""
    gd, c, st = _char()
    did = gd.world["locations"][c.location_id]["dungeon"]
    c.cleared_dungeons = [did]                                           # 預設已肅清 → 重訪
    gold0, inv0 = c.gold, [dict(it) for it in c.inventory]
    ret = _run(gd, st, lambda foes: "victory")                          # 一路清到 boss 並擊殺
    assert ret is None
    assert did in c.cleared_dungeons                                    # record 仍冪等
    assert c.gold == gold0                                              # boss 寶藏不再入袋
    assert c.inventory == inv0                                          # 寶箱/寶藏皆零保證掉落


def test_flee_boss_does_not_clear_or_loot():
    gd, c, st = _char()
    did = gd.world["locations"][c.location_id]["dungeon"]
    gold0 = c.gold
    ret = _run(gd, st, lambda foes: "victory" if isinstance(foes, list) else "fled")   # 一般格勝、boss 逃
    assert ret is None
    assert did not in c.cleared_dungeons                               # 逃 boss → 不計清剿
    assert c.gold == gold0                                             # 不開 boss 寶藏


def test_dead_in_boss_returns_dead():
    gd, c, st = _char()
    ret = _run(gd, st, lambda foes: "victory" if isinstance(foes, list) else "dead")
    assert ret == "dead"
    assert gd.world["locations"][c.location_id]["dungeon"] not in c.cleared_dungeons


def test_leave_does_not_clear():
    gd, c, st = _char()
    did = gd.world["locations"][c.location_id]["dungeon"]
    ret = _run(gd, st, lambda foes: "victory", navigate=False)          # 立刻離開
    assert ret is None and did not in c.cleared_dungeons


def test_zero_new_save_fields():
    gd, c, st = _char()
    keys_before = set(c.to_dict().keys())
    _run(gd, st, lambda foes: "victory")
    assert set(c.to_dict().keys()) == keys_before                      # crawl 不新增任何存檔欄


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_dungeon OK")
