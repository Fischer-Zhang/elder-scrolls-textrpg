"""程序化地城格子生成(原子探索:進場現生、離場即棄、零存檔)。

每地城 spec(`data/dungeons.json`)只給參數 —— grid n、layers m、biome、danger、
monsters 池、loot 池、loot_locked、boss —— 由 `generate()` 組裝 n×n × m 層格子:
怪 / 寶箱 / 陷阱 / 樓梯 / boss / 空 / 入口。**開放格(無內牆)→ 全連通、boss 必可達**。
互動推進(移動/結算/下層)的 crawl 子迴圈在 `main.py`(複用 run_battle/pick_lock/loot)。

cell = {"type": ...,(+ "enemies":[tid] | "container":{locked,loot} | "trap":{damage})}。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.rng import RNG

# --- cell 型別 --------------------------------------------------------------
ENTRANCE = "entrance"
EMPTY = "empty"
MONSTER = "monster"
CONTAINER = "container"
TRAP = "trap"
STAIRS = "stairs"
BOSS = "boss"

# 每層內容密度(套用於非特殊格;餘為空)。調平衡改這三個常數。
# 開放格 → 玩家自行路由(只結算「踏入」的格)→ 衝 boss 遭遇少、全清遭遇多(風險/回報探索)。
MONSTER_DENSITY = 0.22
CONTAINER_DENSITY = 0.15
TRAP_DENSITY = 0.08

# 移動四方向(開放格無內牆 → 格內皆可走)
_DIRS = [("n", "北 ↑", 0, -1), ("s", "南 ↓", 0, 1), ("w", "西 ←", -1, 0), ("e", "東 →", 1, 0)]


def _shuffled(coords: list, rng: RNG) -> list:
    """以 RNG 穩定洗牌(RNG 無 shuffle → 以隨機鍵排序)。"""
    return sorted(coords, key=lambda _c: rng.random())


def generate(spec: dict, gamedata: GameData, rng: RNG) -> dict:
    """依 spec 生成一座格子地城。回傳 {name, n, m, layers[z][y][x]=cell, boss}。"""
    n = int(spec["grid"])
    m = int(spec["layers"])
    danger = int(spec["danger"])
    monsters = spec["monsters"]
    loot_pool = spec.get("loot", [])
    lo, hi = spec.get("loot_locked", [danger * 6, danger * 9])
    gold = danger * 8
    layers = []
    for z in range(m):
        cells = [[{"type": EMPTY} for _ in range(n)] for _ in range(n)]
        cells[0][0] = {"type": ENTRANCE if z == 0 else EMPTY}   # (0,0) = 進場 / 下層到達點
        coords = _shuffled([(x, y) for y in range(n) for x in range(n) if (x, y) != (0, 0)], rng)
        # 特殊格(非末層=樓梯、末層=boss)置於遠半邊,離進場點有距離
        far = [c for c in coords if c[0] + c[1] >= n - 1] or coords
        sx, sy = rng.choice(far)
        cells[sy][sx] = {"type": STAIRS if z < m - 1 else BOSS}
        rest = [c for c in coords if (c[0], c[1]) != (sx, sy)]
        total = len(rest)
        n_mon = int(round(total * MONSTER_DENSITY)) if monsters else 0   # 無怪物池 → 不放怪格
        n_con = int(round(total * CONTAINER_DENSITY))
        n_trap = int(round(total * TRAP_DENSITY))
        for (x, y) in rest[:n_mon]:
            count = 1 + (1 if monsters and rng.chance(0.30 + 0.10 * z) else 0)   # 越深層越可能多敵
            cells[y][x] = {"type": MONSTER, "enemies": [rng.choice(monsters) for _ in range(count)]}
        for (x, y) in rest[n_mon:n_mon + n_con]:
            items = ([rng.choice(loot_pool) for _ in range(1 + (1 if rng.chance(0.4) else 0))]
                     if loot_pool else [])
            cells[y][x] = {"type": CONTAINER,
                           "container": {"locked": rng.randint(lo, hi),
                                         "loot": items + [{"gold": [gold, gold * 2]}]}}
        for (x, y) in rest[n_mon + n_con:n_mon + n_con + n_trap]:
            cells[y][x] = {"type": TRAP, "trap": {"damage": [danger * 2, danger * 4]}}
        layers.append(cells)
    return {"name": spec["name"], "n": n, "m": m, "layers": layers, "boss": spec["boss"]}


def cell_at(grid: dict, z: int, x: int, y: int) -> dict:
    return grid["layers"][z][y][x]


def neighbors(grid: dict, x: int, y: int) -> list:
    """格內四方向可走鄰格:回傳 [(key, label, nx, ny), …]。"""
    n = grid["n"]
    out = []
    for key, label, dx, dy in _DIRS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < n and 0 <= ny < n:
            out.append((key, label, nx, ny))
    return out


def minimap(grid: dict, z: int, cx: int, cy: int, explored: list) -> list:
    """目前層的 n×n 顯示矩陣(供 UI 渲染):每格 {x,y,current,explored,type}。"""
    n = grid["n"]
    return [[{"x": x, "y": y, "current": (x == cx and y == cy),
              "explored": bool(explored[z][y][x]),
              "type": grid["layers"][z][y][x]["type"]}
             for x in range(n)] for y in range(n)]


def reachable_cells(grid: dict, z: int) -> set:
    """BFS 從 (0,0) 可達的格(開放格 → 全格;供測試驗證 boss/樓梯可達)。"""
    n = grid["n"]
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        x, y = stack.pop()
        for _k, _l, nx, ny in neighbors(grid, x, y):
            if (nx, ny) not in seen:
                seen.add((nx, ny))
                stack.append((nx, ny))
    return seen


def find_cell(grid: dict, z: int, ctype: str):
    """回傳該層第一個指定型別格的 (x,y);無則 None。"""
    n = grid["n"]
    for y in range(n):
        for x in range(n):
            if grid["layers"][z][y][x]["type"] == ctype:
                return (x, y)
    return None
