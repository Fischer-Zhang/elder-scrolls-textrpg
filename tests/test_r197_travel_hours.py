"""R197 子提交 (c):旅行選單 / 地點卡 / 世界地圖顯示「實際時數」(預覽 = 實擲)。

🔴 核心紅線:
  ① 單一出處:`world.travel_hours`(= `travel_factor` × 名目,逐跳 max(1, round))—— 真正出發的 `world.travel()` 與所有
     顯示共用;抽出前後**逐位元組同舊**(對 R197 前寫在 travel() 內的算式在格點上全等)。
  ② 路線實際時數 = 逐跳**真的旅行**所耗時數的總和(逐跳各自取整,不是「總和 × 係數」);用真 `world.travel` 對帳。
  ③ 名目的 `route_hours` / `routes_from()` 預設不動(引擎與既有測試用);`actual=True` 才套旅速。
  ④ 顯示:有差異才附「·原 N」;沒有加速來源(運動低且無里程碑 / 星座 / 同伴 / 坐騎 / 神殿)→ 畫面與 R197 前逐位元組同。
  ⑤ 地點卡出口、地圖邊標與節點出口、互動地圖 reach(action_map 傳 actual=True)全部用實際時數 → 同一條路在各畫面數字一致。
"""
import inspect

from tesrpg import formulas, main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import birthsign_ability, divines, mastery, mounts, party, stats, world
import tesrpg.ui.console as ui

gd = get_gamedata()
LOCS = gd.world["locations"]


class _NoEncounterRNG(RNG):
    """chance 一律 False(旅途不遇敵);其餘走真 RNG。"""

    def chance(self, p):
        return False


def _mk(athletics=5, marathon=False, steed=False, start="bruma"):
    c = build_character(gd, name="客", sex="male", race="nord",
                        birthsign="steed" if steed else "warrior", class_id="warrior")
    c.skills["athletics"] = athletics
    if marathon:
        mastery.choose(c, gd, "athletics_50", "marathon")        # 兼帶 −0.10 旅速(R195)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.location_id = start
    return c


# 旅速係數各來源不同的角色格點(0 = 無加速 → 畫面應與舊版逐位元組同)
_CONFIGS = [dict(athletics=5), dict(athletics=31), dict(athletics=32), dict(athletics=50), dict(athletics=62),
            dict(athletics=63), dict(athletics=75), dict(athletics=100),
            dict(athletics=50, marathon=True), dict(athletics=100, marathon=True, steed=True), dict(athletics=5, steed=True)]


def _old_travel_hours(char, base):
    """R197 前寫在 world.travel() 內的算式,原樣重寫(含運算順序)—— 供逐位元組比對。"""
    f = max(0.5, formulas.athletics_travel_factor(char.skill("athletics"))
            - mastery.travel_factor_bonus(char, gd)
            - party.passive_capstone_factor(char, gd, "travel")
            - mounts.travel_factor_bonus(char, gd)
            - birthsign_ability.travel_factor_bonus(char, gd)
            - divines.travel_factor_bonus(char, gd))
    return max(1, round(base * f))


# --- ① 單一出處 -----------------------------------------------------------
def test_travel_hours_is_bytewise_identical_to_the_pre_r197_inline_formula():
    n = 0
    for cfg in _CONFIGS:
        c = _mk(**cfg)
        for base in (1, 2, 3, 4, 5, 8):
            assert world.travel_hours(c, gd, base) == _old_travel_hours(c, base), (cfg, base)
            n += 1
    assert n == len(_CONFIGS) * 6
    # 夾限:疊滿加速仍不低於 0.5
    assert world.travel_factor(_mk(athletics=100, marathon=True, steed=True), gd) == 0.5
    assert world.travel_factor(_mk(athletics=5), gd) == formulas.athletics_travel_factor(5)


def _links_by_base():
    """每種名目時數(1..4)各取一條真實連線 (出發地, 目的地)。"""
    return {1: ("bruma", "jerall_mountains"), 2: ("bruma", "imperial_city"),
            3: ("bruma", "chorrol"), 4: ("whiterun", "windhelm")}


def test_travel_hours_equals_what_world_travel_really_spends():
    n = 0
    for cfg in _CONFIGS:
        for base, (start, dest) in _links_by_base().items():
            assert LOCS[start]["links"][dest] == base                       # 夾具自檢:連線名目時數確實是 base
            shown = world.travel_hours(_mk(start=start, **cfg), gd, base)   # 顯示用
            c = _mk(start=start, **cfg)                                      # 真的出發(新角色:升級不影響取整)
            res = world.travel(c, gd, dest, GameTime(), _NoEncounterRNG(0))
            assert res["hours"] == shown and res["base_hours"] == base, (cfg, base)
            n += 1
    assert n == len(_CONFIGS) * 4


# --- ② 路線 = 逐跳真實旅行的總和 -------------------------------------------
def _routes_with_mixed_hops(c, lo, hi):
    """在幾個出發地找 lo..hi 跳、含 ≥3 時與 1 時路段的路線 → [(start, dest, path, bases)]。"""
    found = []
    for start in ("bruma", "whiterun", "riften", "balmora", "skingrad"):
        if start not in LOCS:
            continue
        c.location_id = start
        for lid in world.routes_from(c, gd):
            path = world.route_to(c, gd, lid)
            if not (lo <= len(path) <= hi):
                continue
            bases, cur = [], start
            for hop in path:
                bases.append(LOCS[cur]["links"][hop])
                cur = hop
            if any(b >= 3 for b in bases) and any(b == 1 for b in bases) and any(b == 2 for b in bases):
                found.append((start, lid, path, bases))
        if len(found) >= 3:
            break
    return found


def test_route_hours_actual_equals_the_sum_of_really_travelled_hops():
    probe = _mk()
    routes = _routes_with_mixed_hops(probe, 4, 8)
    assert len(routes) >= 2, "找不到含混合時數的路線 → 此測試會空轉"
    differs = 0
    for cfg in (dict(athletics=100), dict(athletics=50), dict(athletics=100, marathon=True, steed=True), dict(athletics=5)):
        for start, dest, path, bases in routes[:3]:
            c = _mk(start=start, **cfg)
            c.skill_xp["athletics"] = 0.0
            predicted = world.route_hours_actual(c, gd, path)
            spent = 0
            for hop in path:                                       # 真的逐跳旅行(同一個角色,位置隨之更新)
                spent += world.travel(c, gd, hop, GameTime(), _NoEncounterRNG(0))["hours"]
            assert spent == predicted, (cfg, start, dest, spent, predicted)
            nominal = world.route_hours(_mk(start=start, **cfg), gd, path)
            assert predicted <= nominal                             # 加速只會更快
            assert sum(bases) == nominal
            differs += predicted < nominal
            if cfg == dict(athletics=5):
                assert predicted == nominal                         # 無加速來源 → 與名目相同
    assert differs >= 3, "必須真有「實際 < 名目」的路線,否則此測試空轉"


def test_routes_from_actual_matches_route_hours_actual_and_default_stays_nominal():
    c = _mk(athletics=100, start="bruma")
    nominal = world.routes_from(c, gd)
    actual = world.routes_from(c, gd, actual=True)
    assert set(nominal) == set(actual) and len(nominal) > 50
    faster = 0
    for lid in nominal:
        path = world.route_to(c, gd, lid)
        assert nominal[lid] == (len(path), world.route_hours(c, gd, path))             # 預設仍是名目(逐位元組同舊)
        assert actual[lid] == (len(path), world.route_hours_actual(c, gd, path))
        faster += actual[lid][1] < nominal[lid][1]
    assert faster > 10
    slow = _mk(athletics=5, start="bruma")                                              # 無加速:actual 與名目完全相同
    assert world.routes_from(slow, gd, actual=True) == world.routes_from(slow, gd)


# --- ④ 選單標籤 -----------------------------------------------------------
def test_travel_hours_label_adds_the_original_only_when_it_differs():
    fast, slow = _mk(athletics=100), _mk(athletics=5)
    assert [M._travel_hours_label(fast, gd, b) for b in (1, 2, 3, 4)] == ["1 時", "1 時·原 2", "2 時·原 3", "2 時·原 4"]
    assert [M._travel_hours_label(slow, gd, b) for b in (1, 2, 3, 4)] == ["1 時", "2 時", "3 時", "4 時"]


def _menu_options(c):
    st = GameState(player=c, time=GameTime())
    cap = {}
    saved = ui.menu
    ui.menu = lambda title, options, allow_back=False: (cap.setdefault("opts", list(options)), None)[1]
    try:
        assert M.action_travel(st, gd) is None
    finally:
        ui.menu = saved
    return cap["opts"], ui._quest_target_location_set(c, gd)


def test_travel_menu_labels_show_actual_hours_and_are_unchanged_without_speedups():
    # 有加速:與 world.travel_hours 對得上,且有差異者標「·原 N」
    c = _mk(athletics=100, start="bruma")
    opts, targets = _menu_options(c)
    links = LOCS["bruma"]["links"]
    seen_diff = False
    for key, label in opts:
        if key not in links:
            continue                                                 # __far__ / __caution__ 等非旅行目的地
        base = links[key]
        actual = world.travel_hours(c, gd, base)
        want = f"（{actual} 時·原 {base}" if actual != base else f"（{base} 時"
        assert want in label, (key, label)
        seen_diff |= actual != base
    assert seen_diff
    # 無加速:標籤與 R197 前的樣式逐位元組同
    slow = _mk(athletics=5, start="bruma")
    opts, targets = _menu_options(slow)
    for key, label in opts:
        if key in links:
            old = (f"{'◎ ' if key in targets else ''}{gd.location(key)['name']}"
                   f"（{links[key]} 時{' · 任務' if key in targets else ''})")
            assert label == old, (label, old)


# --- ⑤ 地點卡出口 / 地圖 -----------------------------------------------------
def test_location_card_exits_use_actual_hours():
    c = _mk(athletics=100, start="bruma")
    exits = ui._location_view(c, gd)["exits"]
    assert exits
    diff = 0
    for e in exits:
        dest = e["key"][len("go:"):]
        base = LOCS["bruma"]["links"][dest]
        assert e["hours"] == world.travel_hours(c, gd, base)
        diff += e["hours"] != base
    assert diff >= 1
    slow = _mk(athletics=5, start="bruma")
    assert [e["hours"] for e in ui._location_view(slow, gd)["exits"]] == [
        LOCS["bruma"]["links"][e["key"][len("go:"):]] for e in ui._location_view(slow, gd)["exits"]]


def test_world_map_edges_exits_and_reach_use_actual_hours():
    c = _mk(athletics=100, start="bruma")
    reach = world.routes_from(c, gd, actual=True)
    view = ui._map_view(c, gd, reach)
    edges = view["grid"]["edges"]
    assert len(edges) > 100
    diff = 0
    for e in edges:
        base = LOCS[e["a"]]["links"][e["b"]]
        assert e["h"] == world.travel_hours(c, gd, base), e
        diff += e["h"] != base
    assert diff > 20
    for n in view["grid"]["nodes"]:
        if n["id"] in reach:
            assert (n["hops"], n["hours"]) == reach[n["id"]]
    for prov in view["provinces"]:
        for node in prov["nodes"]:
            for ex in node["exits"]:
                assert ex["hours"] >= 1
    # 無加速:地圖資料與名目完全相同
    slow = _mk(athletics=5, start="bruma")
    sv = ui._map_view(slow, gd, world.routes_from(slow, gd, actual=True))
    assert all(e["h"] == LOCS[e["a"]]["links"][e["b"]] for e in sv["grid"]["edges"])


def test_action_map_asks_for_actual_reach():
    """守衛:互動地圖的 reach 必須以 actual=True 取得,否則「約 M 時」又回到名目值。"""
    assert "routes_from(state.player, gamedata, actual=True)" in inspect.getsource(M.action_map)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
