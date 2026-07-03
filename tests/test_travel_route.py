"""長途旅行(R114D·UI/UX 審計 包D)回歸測試。

涵蓋:BFS route_to(最短跳數/決定性/只經可見/已在或不可達=[])、route_hours、
_travel_hop 狀態(clear/fought/dead)、_travel_route 逐跳自走 + 遇襲中斷 + 死亡停、
action_travel「長途前往」清單(已到訪·可達·非相鄰城鎮)。純選單流·零 rng 消耗於選路。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import world
import tesrpg.ui.console as ui
import tesrpg.main as M


def _cs():
    gd = get_gamedata()
    c = build_character(gd, name="旅", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    return gd, c, GameState(player=c, time=GameTime(), rng=RNG(1))


def _far_city(gd, c):
    """回一個距起點 ≥2 跳的可達城市 + 其 BFS 路徑。"""
    locs = gd.world["locations"]
    adj = set(locs[c.location_id].get("links", {}))
    for lid, l in locs.items():
        if l["type"] == "city" and lid != c.location_id and lid not in adj:
            p = world.route_to(c, gd, lid)
            if len(p) >= 2:
                return lid, p
    raise AssertionError("找不到遠城(fixture 前提)")


# --- BFS route_to --------------------------------------------------------
def test_route_to_shortest_deterministic_adjacent_chain():
    gd, c, st = _cs()
    far, path = _far_city(gd, c)
    assert world.route_to(c, gd, far) == path           # 決定性(同輸入同輸出)
    locs = gd.world["locations"]
    cur = c.location_id
    for hop in path:                                    # 每跳與前一跳相鄰(可逐跳走)
        assert hop in locs[cur].get("links", {}), (cur, hop)
        cur = hop
    assert path[-1] == far
    # 最短性抽查:路徑長度 = BFS 層數,不存在更短的直接相鄰
    assert far not in locs[c.location_id].get("links", {})   # 遠城非相鄰(否則 len 應為 1)


def test_route_to_edge_cases():
    gd, c, st = _cs()
    assert world.route_to(c, gd, c.location_id) == []   # 已在該地
    assert world.route_to(c, gd, "ghost_loc_xyz") == []  # 不存在
    # 不可見地點(湮滅之門未開)不可達
    hidden = next((lid for lid, l in gd.world["locations"].items()
                   if not world.is_visible(c, gd, lid)), None)
    if hidden:
        assert world.route_to(c, gd, hidden) == []


def test_route_hours_sums_base_hours():
    gd, c, st = _cs()
    far, path = _far_city(gd, c)
    locs = gd.world["locations"]
    manual, cur = 0, c.location_id
    for hop in path:
        manual += locs[cur]["links"][hop]
        cur = hop
    assert world.route_hours(c, gd, path) == manual


# --- _travel_route 逐跳自走 + 中斷 --------------------------------------
def _patch(no_encounter=True):
    """patch ui + 遭遇(no_encounter=True → 途中零遭遇,只驗導航);回 restore。"""
    saved = (ui.message, ui.show_events, ui.menu, ui.confirm)
    ui.message = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None
    ui.menu = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True

    def restore():
        ui.message, ui.show_events, ui.menu, ui.confirm = saved
    return restore


def test_travel_route_walks_full_path_when_clear():
    gd, c, st = _cs()
    far, path = _far_city(gd, c)
    start = c.location_id
    # 途中零遭遇(encounter 0)+ 零奇遇事件(maybe_event None)→ 純導航驗證走完整路
    saved_ec, saved_ev = world.encounter_chance, M.maybe_event
    world.encounter_chance = lambda danger, hour: 0.0
    M.maybe_event = lambda *a, **k: None
    restore = _patch()
    try:
        r = M._travel_route(st, gd, far)
    finally:
        restore(); world.encounter_chance = saved_ec; M.maybe_event = saved_ev
    assert r is None
    assert c.location_id == far                          # 平安走完整路 → 抵達終點
    assert start != far


def test_travel_route_stops_on_midway_encounter():
    gd, c, st = _cs()
    far, path = _far_city(gd, c)
    # 讓第一跳必遇襲 → _travel_hop 回 'fought' 且非終點 → 中斷停在首跳
    calls = {"n": 0}
    saved_hop = M._travel_hop

    def fake_hop(state, gamedata, dest):
        calls["n"] += 1
        state.player.location_id = dest                 # 模擬移動
        return "fought" if calls["n"] == 1 else "clear"
    M._travel_hop = fake_hop
    restore = _patch()
    try:
        r = M._travel_route(st, gd, far)
    finally:
        restore(); M._travel_hop = saved_hop
    assert r is None
    assert calls["n"] == 1                               # 首跳遇襲即停,不續走
    assert c.location_id == path[0]                      # 停在第一段


def test_travel_hop_fought_via_battle_counter():
    """🔴 審查 MAJOR 修:非埋伏戰鬥(事件/衛兵/圍捕)也讓本跳判 'fought' —— 靠 run_battle
    計數偵測「本跳真打了一場」,而非只認三個埋伏分支。"""
    gd, c, st = _cs()
    far, path = _far_city(gd, c)
    dest = path[0]
    saved = (world.encounter_chance, M.maybe_event, ui.message, ui.show_events)
    world.encounter_chance = lambda d, h: 0.0                # 無隨機埋伏遭遇
    def fake_event(state, gamedata, ctx):                    # 模擬抵達事件觸發一場戰鬥(=run_battle 被呼叫)
        if ctx == "travel":
            state.battles_fought = getattr(state, "battles_fought", 0) + 1
        return None
    M.maybe_event = fake_event
    ui.message = ui.show_events = lambda *a, **k: None
    try:
        status = M._travel_hop(st, gd, dest)
    finally:
        world.encounter_chance, M.maybe_event, ui.message, ui.show_events = saved
    assert status == "fought"                                # 事件戰鬥 → fought(非埋伏分支亦停)
    # 對照:同跳無任何戰鬥 → clear
    c2 = build_character(gd, name="旅2", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    st2 = GameState(player=c2, time=GameTime(), rng=RNG(1))
    saved2 = (world.encounter_chance, M.maybe_event, ui.message, ui.show_events)
    world.encounter_chance = lambda d, h: 0.0
    M.maybe_event = lambda *a, **k: None
    ui.message = ui.show_events = lambda *a, **k: None
    try:
        assert M._travel_hop(st2, gd, world.route_to(c2, gd, far)[0]) == "clear"
    finally:
        world.encounter_chance, M.maybe_event, ui.message, ui.show_events = saved2


def test_travel_hop_stops_on_guard_confrontation_even_if_no_battle():
    """🔴 懲罰類:帶賞金進城被衛兵盤查,即使繳罰金/服刑(未開打)也讓本跳 'fought' →
    長途停下,不繞過處罰。武士特權放行(未受罰)則不中斷。"""
    from tesrpg.systems import crime
    gd, c, st = _cs()
    # 找一個相鄰城/鎮當終點(guard 只在城/鎮觸發)
    dest = next((d for d in gd.world["locations"][c.location_id].get("links", {})
                 if gd.world["locations"][d]["type"] in ("city", "town")), None)
    assert dest, "起點應有相鄰城鎮(fixture 前提)"
    prov = gd.world["locations"][dest]["province"]
    crime.add_bounty(c, prov, 200)                            # 帶賞金 → 觸發盤查
    saved = (world.encounter_chance, M.maybe_event, M.guard_confrontation, ui.message, ui.show_events)
    world.encounter_chance = lambda d, h: 0.0
    M.maybe_event = lambda *a, **k: None
    M.guard_confrontation = lambda s, g: "confronted"        # 模擬「繳罰金過關」(未開打)
    ui.message = ui.show_events = lambda *a, **k: None
    try:
        status = M._travel_hop(st, gd, dest)
    finally:
        (world.encounter_chance, M.maybe_event, M.guard_confrontation, ui.message, ui.show_events) = saved
    assert status == "fought"                                # 被盤查處置 → 中斷長途
    # 對照:武士特權放行(guard 回 None)→ 不中斷
    c2 = build_character(gd, name="武", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    st2 = GameState(player=c2, time=GameTime(), rng=RNG(1))
    crime.add_bounty(c2, prov, 200)
    saved2 = (world.encounter_chance, M.maybe_event, M.guard_confrontation, ui.message, ui.show_events)
    world.encounter_chance = lambda d, h: 0.0
    M.maybe_event = lambda *a, **k: None
    M.guard_confrontation = lambda s, g: None                # 武士放行
    ui.message = ui.show_events = lambda *a, **k: None
    try:
        assert M._travel_hop(st2, gd, dest) == "clear"       # 未受罰 → 不中斷
    finally:
        (world.encounter_chance, M.maybe_event, M.guard_confrontation, ui.message, ui.show_events) = saved2


def test_travel_route_dead_stops():
    gd, c, st = _cs()
    far, path = _far_city(gd, c)
    saved_hop = M._travel_hop
    M._travel_hop = lambda s, g, d: "dead"
    restore = _patch()
    try:
        r = M._travel_route(st, gd, far)
    finally:
        restore(); M._travel_hop = saved_hop
    assert r == "dead"


def test_travel_route_noop_when_unreachable():
    gd, c, st = _cs()
    restore = _patch()
    try:
        assert M._travel_route(st, gd, c.location_id) is None   # 已在該地
        assert M._travel_route(st, gd, "ghost_xyz") is None
    finally:
        restore()


# --- action_travel 長途清單 ---------------------------------------------
def test_action_travel_offers_long_travel_to_visited_far_city():
    gd, c, st = _cs()
    far, path = _far_city(gd, c)
    c.visited_locations = list(set(c.visited_locations) | {far})   # 標記已到訪
    seen = []
    saved = (ui.menu, ui.message)
    ui.message = lambda *a, **k: None
    # 第一層選 __far__;第二層驗清單含遠城 → 選它;_travel_route 內部再走(patch hop 為 clear)
    seq = iter(["__far__", far])

    def _menu(title, options, allow_back=False):
        seen.append((title, [o[0] for o in options]))
        return next(seq, None)
    ui.menu = _menu
    saved_hop = M._travel_hop
    M._travel_hop = lambda s, g, d: (setattr(s.player, "location_id", d) or "clear")
    try:
        M.action_travel(st, gd)
    finally:
        ui.menu, ui.message = saved; M._travel_hop = saved_hop
    assert any(t == "前往何處?" and "__far__" in k for t, k in seen)     # 主選單有長途入口
    assert any("長途前往何處" in t and far in k for t, k in seen)         # 長途清單含遠城
    assert c.location_id == far                                          # 選了 → 走到


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_travel_route 全通過")
