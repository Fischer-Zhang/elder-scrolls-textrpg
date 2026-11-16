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


# ═══ R180 趕路避險:路線偏好(存在角色身上·三檔·只過濾途中節點)═══════════════════════════════════════
def _mini(char, start="a"):
    """小圖:a─x(地城 d3)─b、a─w(野外 d2)─v(野外 d4)─b、b─t(地城 d5)─z。回 fake gamedata(只需 world/location)。"""
    from types import SimpleNamespace
    def n(name, typ, danger, links):
        return {"name": name, "type": typ, "danger": danger, "province": "測", "links": links}
    locs = {
        "a": n("甲城", "city", 0, {"x": 1, "w": 1}),
        "x": n("矮窟", "dungeon", 3, {"a": 1, "b": 1}),
        "w": n("近郊", "wilderness", 2, {"a": 1, "v": 1}),
        "v": n("險嶺", "wilderness", 4, {"w": 1, "b": 1}),
        "b": n("乙城", "city", 0, {"x": 1, "v": 1, "t": 1}),
        "t": n("深塔", "dungeon", 5, {"b": 1, "z": 1}),
        "z": n("丙村", "town", 0, {"t": 1}),
    }
    char.location_id = start
    return SimpleNamespace(world={"locations": locs}, location=lambda lid: locs[lid])


def test_r180_default_off_and_filter_semantics_on_a_small_graph():
    gd0, c, st = _cs()
    assert c.route_caution == "off" and world.route_caution(c) == "off"       # 預設不限
    gd = _mini(c)
    # 不限:最短路穿過地城格
    assert world.route_to(c, gd, "b") == ["x", "b"]
    # 避開地城:改走野外(v 雖 danger 4,但不是地城格 → 可穿越)
    c.route_caution = "dungeon"
    assert world.route_to(c, gd, "b") == ["w", "v", "b"]
    assert world.route_to(c, gd, "x") == ["x"]                                 # 終點豁免:目的地本身是地城照樣可去
    assert world.route_to(c, gd, "t") == ["w", "v", "b", "t"]
    assert world.route_to(c, gd, "z") == [] and world.route_blocked(c, gd, "z")   # 唯一的路穿過地城 → 到不了(不改走)
    assert world.route_blocker(c, gd, "z") == "x"                              # 最短路上第一個不能穿越的地點
    # route_blocked 只在「因偏好而到不了」時為真:到得了/已在該地/不存在的地點都不是
    assert not world.route_blocked(c, gd, "b") and world.route_blocker(c, gd, "b") is None
    assert not world.route_blocked(c, gd, "a") and not world.route_blocked(c, gd, "nowhere")
    assert world.route_to(c, gd, "z", caution="off") == ["x", "b", "t", "z"]
    # 避開高危(danger ≥4):d3 地城可穿越、d4 野外不可
    c.route_caution = "danger"
    assert world.ROUTE_CAUTION_DANGER == 4
    assert world.route_to(c, gd, "b") == ["x", "b"]
    assert world.route_to(c, gd, "v") == ["w", "v"]                            # 終點豁免
    assert world.route_blocked(c, gd, "z")                                     # 得穿過 d5 的深塔
    # 起點豁免:人已在被避開的節點上,照樣走得出去
    for tier in ("dungeon", "danger"):
        c.route_caution = tier
        gd = _mini(c, start="t")
        assert world.route_to(c, gd, "z") == ["z"] and world.route_to(c, gd, "b") == ["b"]
    # routes_from 與 route_to 同口徑(段數/時數/可達集合)
    for tier in world.ROUTE_CAUTION:
        c.route_caution = tier
        gd = _mini(c)
        reach = world.routes_from(c, gd)
        for lid in gd.world["locations"]:
            path = world.route_to(c, gd, lid)
            assert (lid in reach) == bool(path), (tier, lid)
            if path:
                assert reach[lid] == (len(path), world.route_hours(c, gd, path)), (tier, lid)
    c.route_caution = "off"
    assert not world.route_blocked(c, gd, "z")                                 # 不限 → 無所謂「被擋」


def test_r180_off_is_identical_to_the_unfiltered_search_on_the_real_map():
    """預設(不限)= 原行為:與顯式 caution="off" 完全相同;舊存檔沒有這個欄位也一樣。"""
    gd, c, st = _cs()
    locs = gd.world["locations"]
    for origin in (c.location_id, "alinor", "kings_haven_pass", "imperial_city"):
        if origin not in locs:
            continue
        c.location_id = origin
        assert world.routes_from(c, gd) == world.routes_from(c, gd, caution="off")
        for lid in locs:
            assert world.route_to(c, gd, lid) == world.route_to(c, gd, lid, caution="off"), (origin, lid)
    del c.route_caution
    assert world.route_caution(c) == "off"                                     # 欄位缺席(極舊物件)→ 不限
    c.route_caution = "nonsense"
    assert world.route_caution(c) == "off" and world.cycle_route_caution(c) == "dungeon"
    assert world.cycle_route_caution(c) == "danger" and world.cycle_route_caution(c) == "off"


def test_r180_real_map_routes_only_cross_allowed_nodes_and_nothing_is_cut_off():
    """真實地圖:兩檔的路徑「途中節點」全數合規;且新角色眼中沒有任何地點因此到不了
    (日後若加了「只能穿過地城才到得了」的地點,這裡會紅 —— 屆時是內容決定,不是 bug)。
    主線期間的例外見 test_r180_main_quest_deadlands_is_the_only_blocked_destination。"""
    gd, c, st = _cs()
    locs = gd.world["locations"]
    origins = [lid for lid, l in locs.items() if l["type"] in ("city", "town")][::6] + ["kings_haven_pass", "crystal_tower"]
    detours = 0
    for tier, ok in (("dungeon", lambda l: l["type"] != "dungeon"), ("danger", lambda l: l.get("danger", 0) < 4)):
        c.route_caution = tier
        for origin in origins:
            c.location_id = origin
            free, lim = world.routes_from(c, gd, caution="off"), world.routes_from(c, gd)
            assert set(free) == set(lim), f"{tier}: {origin} 有地點被擋下 {sorted(set(free) - set(lim))[:5]}"
            for lid in list(lim)[::7]:
                path = world.route_to(c, gd, lid)
                assert all(ok(locs[m]) for m in path[:-1]), (tier, origin, lid, path)
                detours += len(path) > free[lid][0]
    assert detours > 0                                                         # 過濾確實改了路(不是空轉)
    # 具體例:里蘭德里 → 初堡,不限取道國王避風隘(R178 改成 danger 4 地城);兩檔都繞開
    c.location_id = "lillandril"
    paths = {t: world.route_to(c, gd, "firsthold", caution=t) for t in world.ROUTE_CAUTION}
    assert "kings_haven_pass" in paths["off"]
    assert "kings_haven_pass" not in paths["dungeon"] and "kings_haven_pass" not in paths["danger"]
    assert not any(locs[m]["type"] == "dungeon" for m in paths["dungeon"][:-1])
    assert "eldbur_ruins" in paths["danger"]                                   # d3 地城不算高危 → 兩檔確實不同


def test_r180_preference_survives_save_and_bad_values_fall_back():
    from tesrpg.models.character import Character
    gd, c, st = _cs()
    c.route_caution = "danger"
    d = c.to_dict()
    assert d["route_caution"] == "danger" and Character.from_dict(dict(d)).route_caution == "danger"
    old = dict(d); old.pop("route_caution")                                    # 舊存檔沒有這個鍵
    assert Character.from_dict(old).route_caution == "off"
    bad = dict(d); bad["route_caution"] = "≥3"
    assert Character.from_dict(bad).route_caution == "off"


def _block_everything():
    """讓任何過濾檔位都「寸步難行」(只剩相鄰可達)→ 在真實地圖上製造『被偏好擋下』的遠城。回還原函式。"""
    saved = world._passable
    world._passable = lambda loc, caution: caution == "off"
    return lambda: setattr(world, "_passable", saved)


def test_r180_blocked_trip_is_reported_and_the_player_does_not_move():
    gd, c, st = _cs()
    far, _path = _far_city(gd, c)
    c.route_caution = "dungeon"
    start, msgs = c.location_id, []
    unblock = _block_everything()
    saved_msg, saved_hop = ui.message, M._travel_hop
    ui.message = lambda text, **k: msgs.append(text)
    M._travel_hop = lambda *a, **k: (_ for _ in ()).throw(AssertionError("被擋下時不該起步"))
    try:
        assert world.route_blocked(c, gd, far)
        assert M._travel_route(st, gd, far) is None
    finally:
        ui.message, M._travel_hop = saved_msg, saved_hop
        unblock()
    assert c.location_id == start
    assert len(msgs) == 1 and M.ROUTE_BLOCKED_NOTE in msgs[0]
    assert world.ROUTE_CAUTION_LABEL["dungeon"] in msgs[0] and gd.location(far)["name"] in msgs[0]
    # 對照:真的沒有路(不存在的地點)仍是原訊息,不誤報成避險
    msgs.clear()
    ui.message = lambda text, **k: msgs.append(text)
    try:
        M._travel_route(st, gd, "ghost_xyz")
    finally:
        ui.message = saved_msg
    assert msgs and M.ROUTE_BLOCKED_NOTE not in msgs[0]


def test_r180_menus_toggle_the_preference_and_label_blocked_destinations():
    gd, c, st = _cs()
    far, _path = _far_city(gd, c)
    c.visited_locations = list(set(c.visited_locations) | {far})
    seen, msgs = [], []
    seq = iter(["__caution__", "__caution__", "__caution__", "__caution__", "__far__", None])

    def _menu(title, options, allow_back=False):
        seen.append((title, dict(options)))
        return next(seq, None)
    saved = (ui.menu, ui.message)
    ui.menu, ui.message = _menu, (lambda text, **k: msgs.append(text))
    unblock = _block_everything()
    try:
        assert M.action_travel(st, gd) is None
    finally:
        ui.menu, ui.message = saved
        unblock()
    # 旅行選單每次重繪都帶目前檔位;切四次:不限→地城→高危→不限→地城
    labels = [opts["__caution__"] for title, opts in seen if title == "前往何處?"]
    L = world.ROUTE_CAUTION_LABEL
    assert [next(k for k, v in L.items() if v in lab) for lab in labels] == ["off", "dungeon", "danger", "off", "dungeon"]
    assert c.route_caution == "dungeon" and len(msgs) >= 4
    # 長途清單:遠城仍列出,標明避險擋下(不是無聲消失)
    far_title, far_opts = seen[-1]
    assert far_title.startswith("長途前往") and M.ROUTE_BLOCKED_NOTE in far_opts[far]


def test_r180_map_marks_blocked_nodes_and_offers_no_route_key_for_them():
    gd, c, st = _cs()
    far, _path = _far_city(gd, c)
    c.route_caution = "danger"
    calls, seq = [], iter(["__caution__", "__back__"])
    saved = (ui.world_map, ui.grouped_menu, ui.message)
    ui.world_map = lambda char, g, reach=None, blocked=None: calls.append((dict(reach or {}), set(blocked or ())))
    ui.grouped_menu = lambda title, groups, extra_keys=(): (calls.append(("menu", list(extra_keys), dict(groups[0][1]))), next(seq))[1]
    ui.message = lambda *a, **k: None
    unblock = _block_everything()
    try:
        assert M.action_map(st, gd) is None
    finally:
        ui.world_map, ui.grouped_menu, ui.message = saved
        unblock()
    (reach1, blocked1), (_m, extra1, group1) = calls[0], calls[1]
    assert far in blocked1 and far not in reach1 and "route:" + far not in extra1
    assert all(k[len("route:"):] in reach1 for k in extra1)
    assert world.ROUTE_CAUTION_LABEL["danger"] in group1["__caution__"]
    reach2, blocked2 = calls[2]                                                # 切到「不限」後重繪:沒有被擋的地點
    assert c.route_caution == "off" and blocked2 == set() and far in reach2
    # view-model:被擋的節點帶 blocked 旗標、無段數
    view = ui._map_view(c, gd, reach1, blocked1)
    node = next(n for n in view["grid"]["nodes"] if n["id"] == far)
    assert node["blocked"] is True and node["hops"] is None
    assert all(n["blocked"] is False for n in ui._map_view(c, gd, reach2)["grid"]["nodes"])


def test_r180_main_quest_deadlands_is_the_only_blocked_destination():
    """審查抓到的前提漏洞:「三檔都不會讓地點到不了」只對新角色成立。主線打到達貢的祭壇之後,
    死亡之地只接祭壇(danger 6 地城)→ 兩檔都到不了,除非人已在祭壇。提示要指出可以先去祭壇。"""
    gd, c, st = _cs()
    c.world_events_fired = ["kvatch_falls"]
    c.cleared_dungeons = ["kvatch_gate", "bravil_gate", "dagon_shrine"]
    c.location_id = "cheydinhal"
    assert world.is_visible(c, gd, "the_deadlands") and world.is_visible(c, gd, "dagon_shrine")
    for tier in ("dungeon", "danger"):
        c.route_caution = tier
        free, lim = world.routes_from(c, gd, caution="off"), world.routes_from(c, gd)
        assert set(free) - set(lim) == {"the_deadlands"}, tier
        assert world.route_blocker(c, gd, "the_deadlands") == "dagon_shrine"
        assert world.route_to(c, gd, "dagon_shrine") == ["dagon_shrine"]       # 祭壇本身是合法目的地
    msgs = []
    saved = ui.message
    ui.message = lambda text, **k: msgs.append(text)
    try:
        assert M._travel_route(st, gd, "the_deadlands") is None
    finally:
        ui.message = saved
    assert c.location_id == "cheydinhal"
    assert M.ROUTE_BLOCKED_NOTE in msgs[0] and gd.location("dagon_shrine")["name"] in msgs[0]
    c.location_id = "dagon_shrine"                                             # 人到了祭壇(起點豁免)→ 走得進去
    assert world.route_to(c, gd, "the_deadlands") == ["the_deadlands"]


def test_r180_quest_shortcut_survives_a_blocked_target_and_explains_it():
    """任務目標被偏好擋下時,🎯 捷徑不可無聲消失;單一目標直接說明,多個目標則列出並標明。"""
    gd, c, st = _cs()
    far, _path = _far_city(gd, c)
    near = next(lid for lid, (h, _hr) in world.routes_from(c, gd).items() if h == 2)   # 兩跳:封鎖後也到不了
    c.route_caution = "dungeon"
    saved = (ui.menu, ui.message, ui._quest_target_location_set, M._travel_hop)
    msgs, seen = [], []
    ui.message = lambda text, **k: msgs.append(text)
    M._travel_hop = lambda *a, **k: (_ for _ in ()).throw(AssertionError("被擋下時不該起步"))
    unblock = _block_everything()
    try:
        ui._quest_target_location_set = lambda ch, g: {far}
        seq = iter(["__goal__"])
        ui.menu = lambda title, options, allow_back=False: (seen.append((title, dict(options))), next(seq, None))[1]
        assert M.action_travel(st, gd) is None
        assert "__goal__" in seen[0][1]                                        # 捷徑還在(以不設限的可達性判斷)
        assert len(msgs) == 1 and M.ROUTE_BLOCKED_NOTE in msgs[0]              # 單一目標:直接說明原因
        # 多個目標:清單照列,被擋的標明
        msgs.clear(); seen.clear()
        ui._quest_target_location_set = lambda ch, g: {far, near}
        seq = iter(["__goal__", None])
        assert M.action_travel(st, gd) is None
        title, opts = seen[1]
        assert title.startswith("前往哪個任務目標") and set(opts) == {far, near}
        assert all(M.ROUTE_BLOCKED_NOTE in label for label in opts.values()) and not msgs
    finally:
        ui.menu, ui.message, ui._quest_target_location_set, M._travel_hop = saved
        unblock()
    # 切回不限的提示不該說「只過濾途中地點」
    msgs.clear()
    ui.message = lambda text, **k: msgs.append(text)
    try:
        c.route_caution = "danger"
        M._cycle_route_caution(c)
        assert c.route_caution == "off" and "只過濾" not in msgs[-1] and "最短路" in msgs[-1]
        M._cycle_route_caution(c)
        assert c.route_caution == "dungeon" and "只過濾途中" in msgs[-1]
    finally:
        ui.message = saved[1]


def test_r180_blocked_phrase_is_the_same_in_backend_and_frontend():
    """「避險設定下無路可通」後端(清單/提示)與前端(地圖面板、服務搜尋)各自寫死一份 → 釘住不得走樣。"""
    from pathlib import Path
    html = (Path(M.__file__).parent / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert html.count(M.ROUTE_BLOCKED_NOTE) == 2


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_travel_route 全通過")
