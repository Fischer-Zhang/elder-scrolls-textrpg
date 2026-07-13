"""Web 後端 + console seam 測試(不需 pip、不跑瀏覽器、不跑整個 main())。

驗證:5 個輸入原語在 web 模式產生正確 spec 並 round-trip;畫面 HTML 是裸 <span>
片段(code_format 生效、無 <!DOCTYPE);雙擊/亂序 prompt_id 被擋;越界整數重新詢問;
flush_final 出 end 哨兵;generation 遞增。

**鐵律**:測試結束務必還原 ui._web=None / ui.console,以免污染後續測試模組。"""

import importlib
import io
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

from tesrpg.ui import console as ui
from tesrpg.web.backend import WebBackend, _validate


def _rec():
    return Console(record=True, file=io.StringIO(), width=100)


def _restore():
    ui._web = None
    ui.console = Console()
    ui._hud_state = None
    ui._hud_gamedata = None    # 一併清 HUD 全域(比照 clear_hud)→ 不把共享 gamedata 洩漏到後續模組
    ui._hud_allies = None


def _drive_multi(backend, call, answers):
    """在 thread 跑會多次 prompt 的呼叫;逐 prompt 作答(answers=作答函式列),回傳 (frames, 結果)。"""
    box = {}

    def worker():
        try:
            box["v"] = call()
        except BaseException as e:
            box["exc"] = e

    t = threading.Thread(target=worker)
    t.start()
    frames = []
    for ans_fn in answers:
        fr = backend.outbound.get(timeout=5)
        frames.append(fr)
        assert backend.submit(fr["prompt_id"], ans_fn(fr["prompt"])), "submit 被拒"
    t.join(timeout=5)
    if "exc" in box:
        raise box["exc"]
    assert not t.is_alive(), "呼叫未返回(疑似死鎖)"
    return frames, box.get("v")


def _drive(backend, call, answer_for):
    """在 thread 跑阻塞的 ui.* 呼叫,讀出 frame、作答、回傳 (frame, 呼叫結果)。"""
    import queue as _q
    box = {}

    def worker():
        try:
            box["v"] = call()
        except BaseException as e:        # noqa: surface worker error to main thread
            box["exc"] = e

    t = threading.Thread(target=worker)
    t.start()
    try:
        frame = backend.outbound.get(timeout=5)
    except _q.Empty:
        t.join(0.5)
        raise AssertionError("輸入原語未送出 frame;worker 例外=%r" % box.get("exc"))
    ans = answer_for(frame["prompt"])
    assert backend.submit(frame["prompt_id"], ans), "submit 被拒"
    t.join(timeout=5)
    if "exc" in box:
        raise box["exc"]
    assert not t.is_alive(), "呼叫未返回(疑似死鎖)"
    return frame, box.get("v")


def test_validate():
    assert _validate({"type": "confirm"}, True) == (True, True)
    assert _validate({"type": "int", "lo": 1, "hi": 24}, 8) == (True, 8)
    assert _validate({"type": "int", "lo": 1, "hi": 24}, 99)[0] is False
    assert _validate({"type": "int", "lo": 1, "hi": 24}, "x")[0] is False
    assert _validate({"type": "text"}, None) == (True, "")
    assert _validate({"type": "menu", "options": [{"key": "a"}], "allow_back": True}, None) == (True, None)
    assert _validate({"type": "menu", "options": [{"key": "a"}], "allow_back": False}, None)[0] is False
    assert _validate({"type": "menu", "options": [{"key": "a"}]}, "a") == (True, "a")
    assert _validate({"type": "menu", "options": [{"key": "a"}]}, "zzz")[0] is False


def test_seam_roundtrip():
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        fr, v = _drive(backend, lambda: ui.menu("選擇", [("k1", "選項一"), ("k2", "選項二")]),
                       lambda s: "k2")
        assert fr["prompt"]["type"] == "menu" and v == "k2"
        assert [o["key"] for o in fr["prompt"]["options"]] == ["k1", "k2"]
        assert fr["prompt"]["title"] == "選擇"
        assert "chips" not in fr["prompt"]["options"][0]    # 無 chips 的選項不帶該鍵

        # 創角 build chips:選項可帶第三元素(數值小標),round-trip 後出現在 spec
        fr, v = _drive(backend,
                       lambda: ui.menu("種族", [("altmer", "高精靈", [{"text": "智力+10", "tone": "green"}]),
                                                ("nord", "諾德")], ),   # 混長度 tuple 共存
                       lambda s: "altmer")
        assert v == "altmer"
        assert fr["prompt"]["options"][0]["chips"][0]["text"] == "智力+10"
        assert "chips" not in fr["prompt"]["options"][1]    # 2-tuple 選項不帶 chips

        _, v = _drive(backend, lambda: ui.menu("X", [("k", "l")], allow_back=True), lambda s: None)
        assert v is None      # 返回

        fr, v = _drive(backend,
                       lambda: ui.grouped_menu("要做什麼?", [("冒險", [("travel", "旅行")]), ("空", [])]),
                       lambda s: "travel")
        assert fr["prompt"]["type"] == "grouped" and v == "travel"
        assert len(fr["prompt"]["groups"]) == 1          # 空分組自動略過

        _, v = _drive(backend, lambda: ui.confirm("確定?"), lambda s: True)
        assert v is True
        _, v = _drive(backend, lambda: ui.confirm("確定?"), lambda s: False)
        assert v is False

        _, v = _drive(backend, lambda: ui.ask_int("幾小時?", 8, 1, 24), lambda s: 12)
        assert v == 12
        _, v = _drive(backend, lambda: ui.ask_text("姓名", default="阿"), lambda s: "貝")
        assert v == "貝"
    finally:
        _restore()


def test_blocks_protocol():
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        ui.message("[gold1]測試訊息[/]")                 # 已轉原生 → log block(彩色文字行)
        fr, _ = _drive(backend, lambda: ui.menu("X", [("k", "l")]), lambda s: "k")
        logs = [b["html"] for b in fr["blocks"] if b["kind"] == "log"]
        assert logs and "<span" in logs[0]                       # rich 標記→彩色 span
        assert "<!DOCTYPE" not in logs[0] and "<html" not in logs[0]   # code_format 生效
    finally:
        _restore()


def test_hud_and_view_block():
    """status_line 在 web 設常駐 HUD(frame.hud 帶即時資源,非 block);其餘面板發 view block。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="dunmer", birthsign="lady", class_id="knight")
    st = GameState(player=c, time=GameTime(), rng=RNG(3))
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__("v", ui.confirm("?")))
        ui.status_line(st)          # web:設 _hud_state(常駐 HUD),不發 block
        ui.location_panel(c, gd)    # 應發 location view block
        t.start()
        fr = backend.outbound.get(timeout=5)
        assert fr["hud"] and fr["hud"]["name"] == "測" and len(fr["hud"]["hp"]) == 2 and "gold" in fr["hud"]
        views = [b for b in fr["blocks"] if b["kind"] == "view"]
        assert any(b["name"] == "location" for b in views), fr["blocks"]
        assert not any(b["name"] == "status" for b in views)   # status 不再是 block
        backend.submit(fr["prompt_id"], True); t.join(timeout=5)
    finally:
        _restore()


def test_dungeon_grid_view_block():
    """格子地城 dungeon_grid view:發 block,帶 n/layer/rows(含當前格 @ + 相鄰可點 move key)。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.rng import RNG
    from tesrpg.systems import dungeoncrawl as DC
    gd = get_gamedata()
    g = DC.generate(gd.dungeons["cedernoc_cave"], gd, RNG(3))
    n, m = g["n"], g["m"]
    explored = [[[False] * n for _ in range(n)] for _ in range(m)]
    explored[0][0][0] = True
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        t = threading.Thread(target=lambda: ui.confirm("?"))
        ui.dungeon_grid(g, 0, 0, 0, explored)          # 發 dungeon_grid view block
        t.start()
        fr = backend.outbound.get(timeout=5)
        views = [b for b in fr["blocks"] if b["kind"] == "view" and b["name"] == "dungeon_grid"]
        assert views, fr["blocks"]
        d = views[0]["data"]
        assert d["n"] == n and d["layer"] == 1 and d["layers"] == m
        assert len(d["rows"]) == n and len(d["rows"][0]) == n
        assert d["rows"][0][0]["current"] and d["rows"][0][0]["icon"] == "@"        # (0,0)=當前
        moves = [c.get("move") for row in d["rows"] for c in row if c.get("move")]
        assert any(mv.startswith("go:") for mv in moves)                            # 相鄰格帶可點移動 key
        backend.submit(fr["prompt_id"], True); t.join(timeout=5)

        # --- 併入 content_icons_and_resolved:偵查揭示有資訊量 ---
        # 已探「未結算」內容格顯示怪/寶/陷阱圖示;已結算則回 ·(stairs 恆顯)。
        grid = {"name": "T", "n": 2, "m": 1, "layers": [[
            [{"type": "monster"}, {"type": "container"}],
            [{"type": "trap"}, {"type": "stairs"}]]]}
        explored2 = [[[True, True], [True, True]]]
        t = threading.Thread(target=lambda: ui.confirm("?"))
        ui.dungeon_grid(grid, 0, 0, 0, explored2, resolved=None)   # 全未結算
        t.start()
        fr = backend.outbound.get(timeout=5)
        rows = [b for b in fr["blocks"] if b["kind"] == "view" and b["name"] == "dungeon_grid"][0]["data"]["rows"]
        # (0,0)=當前 @;(1,0)=container $;(0,1)=trap ^;(1,1)=stairs ↓
        assert rows[0][1]["icon"] == "$" and rows[1][0]["icon"] == "^" and rows[1][1]["icon"] == "↓"
        backend.submit(fr["prompt_id"], True); t.join(timeout=5)
        # 已結算 → 內容格回 ·(stairs 結構格恆顯)
        resolved = [[[True, True], [True, True]]]
        t2 = threading.Thread(target=lambda: ui.confirm("?"))
        ui.dungeon_grid(grid, 0, 0, 0, explored2, resolved=resolved)
        t2.start()
        fr2 = backend.outbound.get(timeout=5)
        rows2 = [b for b in fr2["blocks"] if b["kind"] == "view" and b["name"] == "dungeon_grid"][0]["data"]["rows"]
        assert rows2[0][1]["icon"] == "·" and rows2[1][0]["icon"] == "·" and rows2[1][1]["icon"] == "↓"
        backend.submit(fr2["prompt_id"], True); t2.join(timeout=5)
    finally:
        _restore()


def test_hud_includes_party_and_allies():
    """狀態條(web HUD):帶入 gamedata + allies → HUD 含隊伍同伴 + 召喚物。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    from tesrpg.systems import combat
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.companions = ["sellsword"]
    st = GameState(player=c, time=GameTime(), rng=RNG(3))
    summon = combat.spawn_creature(gd, "summoned_familiar", RNG(0)); summon.summon_turns = 5
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        t = threading.Thread(target=lambda: ui.confirm("?"))
        ui.status_line(st, gd, allies=[summon])     # 設常駐 HUD(含 party + allies)
        ui.location_panel(c, gd)
        t.start()
        fr = backend.outbound.get(timeout=5)
        hud = fr["hud"]
        assert hud["party"] and hud["party"][0]["name"] and len(hud["party"][0]["hp"]) == 2
        assert hud["allies"] and hud["allies"][0]["name"] == summon.name
        assert hud["allies"][0]["turns"] == 5
        backend.submit(fr["prompt_id"], True); t.join(timeout=5)
    finally:
        _restore()


def test_view_model_shapes():
    """本輪 UI 改版的 view-model 形狀回歸:戰鬥法力/狀態標分色、傳奇分段、地圖省份進度。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    from tesrpg.systems import combat, legacy
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="altmer", birthsign="mage", class_id="mage")
    st = GameState(player=c, time=GameTime(), rng=RNG(7))

    # --- 戰鬥:玩家有 mp 雙元素;狀態標為 {s,good} dict,增益綠/減益紅 ---
    c.active_effects = [{"kind": "shield", "turns": 3, "magnitude": 20},
                        {"kind": "dot", "turns": 2, "element": "fire", "magnitude": 5}]
    foe = combat.spawn_creature(gd, "giant_rat", RNG(1))
    cv = ui._combat_view(c, [], [foe])
    assert len(cv["me"]["mp"]) == 2 and cv["me"]["mp"][1] == int(c.max_magicka)
    assert len(cv["me"]["fp"]) == 2
    tags = {t["s"][0]: t["good"] for t in cv["me"]["tags"]}   # 以首字(盾/蝕)為鍵
    assert tags.get("盾") is True and tags.get("蝕") is False
    assert all(isinstance(t, dict) and "s" in t and "good" in t for t in cv["me"]["tags"])
    assert cv["enemies"][0]["mp"] == [0, 0]                   # 怪物無法力 → JS 以 mp[1] 假值隱藏
    assert cv["enemies"][0]["key"] == "0" and cv["enemies"][0]["idx"] == 1   # 卡顯 "1." 但 key=0(0-based 目標鍵)
    assert "key" not in cv["me"]                              # 玩家卡無 key(不可被當目標點選)
    c.active_effects = []

    # --- 傳奇:rows → sections(每段 {header, items});不再有頂層 rows ---
    lv = ui._legacy_view(legacy.compute(st, gd, ending="retirement"))
    assert "rows" not in lv and isinstance(lv["sections"], list) and lv["sections"]
    headers = [s["header"] for s in lv["sections"]]
    assert "生涯" in headers and "功績" in headers and "名望" in headers
    for sec in lv["sections"]:
        assert sec["items"] and all(len(it) == 2 for it in sec["items"])

    # --- 地圖:每省帶 visited/total(int),且 visited≤total ---
    mv = ui._map_view(c, gd)
    assert mv["provinces"]
    for p in mv["provinces"]:
        assert isinstance(p["visited"], int) and isinstance(p["total"], int)
        assert 0 <= p["visited"] <= p["total"] == len(p["nodes"])
    # --- 相對位置地圖 grid:cols/rows + 每地點帶 id/pos(界內);節點數 == 可見地點數 ---
    from tesrpg.systems import world as _world
    g = mv["grid"]
    cols, rows = g["cols"], g["rows"]
    assert cols == gd.world["map"]["cols"] and rows == gd.world["map"]["rows"]
    visible_n = sum(1 for lid in gd.world["locations"] if _world.is_visible(c, gd, lid))
    assert len(g["nodes"]) == visible_n          # 隱藏的湮滅之門不上圖(開局未開)
    assert len(g["nodes"]) < len(gd.world["locations"])   # 開局確實有隱藏地點(湮滅之門/神殿)
    ids = set()
    for n in g["nodes"]:
        assert n["id"] in gd.world["locations"]
        cx, cy = n["pos"]
        assert 0 <= cx < cols and 0 <= cy < rows, f"{n['id']} pos 越界"
        assert "type" in n and "here" in n and "visited" in n and isinstance(n["svc"], list)
        ids.add(n["id"])
    # edges:無向去重、指向合法節點、帶時數(供地圖畫連線 + 放大標時長)
    assert g["edges"]
    for e in g["edges"]:
        assert e["a"] in ids and e["b"] in ids, f"edge 指向不存在節點:{e}"
        assert isinstance(e["h"], int) and e["h"] >= 1
    # --- 互動地圖(reach):預設 reach=None → 每 node hops/hours 皆 None(back-compat,逐位元組同唯讀) ---
    for n in g["nodes"]:
        assert n["hops"] is None and n["hours"] is None
        assert isinstance(n["svc_all"], list)
    # world.routes_from:一次 BFS,不含當前地,只含可見可達點;hops/hours 對齊 route_to/route_hours
    reach = _world.routes_from(c, gd)
    assert reach and c.location_id not in reach
    for lid, hh in list(reach.items())[:8]:
        hops, hours = hh
        assert hops >= 1 and hours >= 1 and _world.is_visible(c, gd, lid)
        assert len(_world.route_to(c, gd, lid)) == hops
        assert _world.route_hours(c, gd, _world.route_to(c, gd, lid)) == hours
    assert any(h == 1 for h, _ in reach.values())          # 開局應有相鄰(1 段)可達點
    # 傳入 reach → 可達 node 帶 hops/hours(對齊 reach);當前地=None
    mv2 = ui._map_view(c, gd, reach)
    nodes2 = {n["id"]: n for n in mv2["grid"]["nodes"]}
    assert nodes2[c.location_id]["hops"] is None           # 當前地無前往按鈕
    for lid in reach:
        assert nodes2[lid]["hops"] == reach[lid][0] and nodes2[lid]["hours"] == reach[lid][1]

    # --- 背包(R-inv):items 帶 kind+tier;weight/max/over 齊;品質階由價值推導 ---
    from tesrpg.systems import inventory as _inv
    for it, q in [("iron_sword", 1), ("steel_sword", 1), ("daedric_mace", 1),
                  ("glass_cuirass", 1), ("healing_potion", 2)]:
        _inv.add_item(c, it, q)
    iv = ui._inventory_view(c, gd)
    assert isinstance(iv["weight"], float) and isinstance(iv["max"], int) and isinstance(iv["over"], bool)
    by = {x["key"]: x for x in iv["items"]}
    assert all("tier" in x and "kind" in x for x in iv["items"])
    assert by["iron_sword"]["tier"] == "common" and by["steel_sword"]["tier"] == "uncommon"
    assert by["glass_cuirass"]["tier"] == "rare" and by["daedric_mace"]["tier"] == "legendary"
    assert ui._item_tier({"enchant": {"kind": "x"}, "value": 1}) == "legendary"   # 附魔升頂
    # --- 換裝對比 panel:武器比當前手持,含傷害增減 head/kv 行 ---
    cap = {}
    orig_ep = ui._emit_panel
    ui._emit_panel = lambda title, rws: cap.update(title=title, rows=rws)
    ui._web = object()
    try:
        ui.item_compare_panel(c, gd, "daedric_mace")
    finally:
        ui._emit_panel = orig_ep
        ui._web = None
    assert cap["title"] == "換裝對比"
    kv = {r["k"]: r["v"] for r in cap["rows"] if r.get("t") == "kv"}
    assert "傷害" in kv and "手持" in kv["傷害"] and "+" in kv["傷害"]   # 顯示與當前手持的增減


def test_map_svc_all_includes_guild_halls_r159():
    """R159 修 R153 回歸:svc_all 原缺公會鍵且前端 svc_all 非空即優先 → 戰友團/九神騎士團被永久遮蔽。
    現 svc_all=公會全名領頭 + 通用服務全名;svc(公會清單)須為 svc_all 前綴。"""
    from tesrpg.creation import build_character
    from tesrpg.gamedata import get_gamedata
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    nodes = {n["id"]: n for n in ui._map_view(c, gd)["grid"]["nodes"]}
    assert "戰友團" in nodes["whiterun"]["svc_all"], "戰友團大廳不得再被遮蔽(R153 回歸)"
    assert "九神騎士團" in nodes["anvil"]["svc_all"]
    assert "旅店" in nodes["whiterun"]["svc_all"] and "告示板" in nodes["whiterun"]["svc_all"]
    for n in nodes.values():   # 公會領頭:svc ⊆ svc_all 且為前綴(前端 svc_all 優先 → svc 資訊不再丟失)
        assert n["svc_all"][:len(n["svc"])] == n["svc"], n["id"]
    # 🔴 詞彙守衛(R153 回歸的成因=鍵集漂移):world services 值集必 ⊆ 公會表 ∪ 通用表 →
    #    未來新 service 鍵漏登記 CN 表時在資料編輯當下亮紅燈,而非又一次靜默遮蔽
    vocab = {s for l in gd.world["locations"].values() for s in l.get("services", [])}
    known = set(ui._GUILD_HALL_CN) | set(ui._SVC_FULL)
    assert vocab <= known, f"未登記 CN 名的 service 鍵:{vocab - known}"
    # 公會大廳名稱=factions.json 正典名(防顯示名漂移,如 R159 修正的 聖騎士團→九神騎士團)
    for fid, cn in ui._GUILD_HALL_CN.items():
        canon = (gd.factions.get(fid) or {}).get("name")
        assert canon == cn, f"{fid} 顯示名 {cn} ≠ factions.json 正典名 {canon}"


def test_map_and_location_surface_stables_houses_r160b():
    """R160b:馬廄/房產不在 services vocab → 補入地圖 svc_all + 地點卡 services + 目錄;
    地點卡並標 R29 專精(訓練師宗師技·法師公會學派)——就地正查,補地圖之外的『站在城裡』易讀性。"""
    from tesrpg.creation import build_character
    from tesrpg.gamedata import get_gamedata
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    stable_cities = [lid for lid in gd.world["locations"] if gd.has_stable(lid)]
    house_cities = [lid for lid in gd.world["locations"] if gd.house_at(lid)]
    assert stable_cities and house_cities
    # --- 地圖 svc_all:馬廄/房產 依 accessor 衍生(非 services vocab)---
    nodes = {n["id"]: n for n in ui._map_view(c, gd)["grid"]["nodes"]}
    for lid in stable_cities:
        if lid in nodes:
            assert "馬廄" in nodes[lid]["svc_all"], lid
    for lid in house_cities:
        if lid in nodes:
            assert "房產" in nodes[lid]["svc_all"], lid
    # 非馬廄城不誤標
    non_stable = next(lid for lid in nodes if not gd.has_stable(lid))
    assert "馬廄" not in nodes[non_stable]["svc_all"]
    # --- 地點卡 services chips:公會/服務/馬廄/房產 + 專精標註 ---
    c.location_id = "whiterun"                       # 戰友團 + 法師公會(毀滅) + 重甲宗師 + 馬廄 + 房產
    v = ui._location_view(c, gd)
    svc = v["services"]
    assert "戰友團" in svc and "馬廄" in svc and "房產" in svc
    assert any(s.startswith("法師公會（") and "毀滅" in s for s in svc), svc   # 法師公會標學派
    assert any(s.startswith("訓練師（") and "宗師" in s for s in svc), svc      # 訓練師標宗師技
    c.location_id = "imperial_city"                  # 通才法師公會
    assert any("通才" in s for s in ui._location_view(c, gd)["services"])
    # brief 麵包屑不重畫 → services 空(省算)
    assert ui._location_view(c, gd, brief=True)["services"] == []
    # 非設施城(地城)無服務不崩、chips 為空
    dungeon_lid = next((lid for lid, l in gd.world["locations"].items()
                        if l.get("type") == "dungeon" and not l.get("services")), None)
    if dungeon_lid:
        c.location_id = dungeon_lid
        assert ui._location_view(c, gd)["services"] == []


def test_action_map_route_dispatch():
    """互動地圖:面板 route:<lid> → action_map 走 _travel_route(dest);__back__ → 乾淨返回。"""
    import types
    from tesrpg.creation import build_character
    from tesrpg.gamedata import get_gamedata
    from tesrpg.systems import world
    import tesrpg.main as main

    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    st = types.SimpleNamespace(player=c)
    reach = world.routes_from(c, gd)
    adj = next(lid for lid, (h, _h) in reach.items() if h == 1)

    calls, seq = [], iter(["route:" + adj, "__back__"])
    orig_wm, orig_gm, orig_tr = ui.world_map, ui.grouped_menu, main._travel_route
    ui.world_map = lambda *a, **k: None                              # 免 web backend(不 emit)
    ui.grouped_menu = lambda *a, **k: next(seq)                      # 先點面板前往,再返回
    main._travel_route = lambda state, gamedata, dest: (calls.append(dest), None)[1]
    try:
        r = main.action_map(st, gd)
    finally:
        ui.world_map, ui.grouped_menu, main._travel_route = orig_wm, orig_gm, orig_tr
    assert calls == [adj]          # route:<相鄰> → _travel_route(相鄰 lid)
    assert r is None               # __back__ → 乾淨返回


def test_combat_target_key_parity():
    """戰鬥可點目標的命脈不變式:存活敵人卡的 key 為 0-based 且對齊 _choose_enemy_target
    的 enumerate(alive) 鍵;陣亡卡無 key;卡顯示 idx=key+1。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.rng import RNG
    from tesrpg.systems import combat
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    live_a = combat.spawn_creature(gd, "giant_rat", RNG(1))
    dead = combat.spawn_creature(gd, "giant_rat", RNG(2)); dead.health = 0
    live_b = combat.spawn_creature(gd, "giant_rat", RNG(3))
    cv = ui._combat_view(c, [], [live_a, dead, live_b])
    keyed = [(e.get("key"), e["idx"]) for e in cv["enemies"] if e.get("key") is not None]
    assert keyed == [("0", 1), ("1", 2)]                       # 跳過陣亡者、key 連號 0/1、idx=key+1
    assert all(e.get("key") is None for e in cv["enemies"] if e["down"])   # 陣亡卡無 key
    # 對齊 _choose_enemy_target 的鍵:alive 索引 == 卡 key
    alive = [e for e in [live_a, dead, live_b] if combat.is_alive(e)]
    assert [str(i) for i in range(len(alive))] == [k for k, _ in keyed]


def test_combat_readability_d_batch_r156():
    """R156 戰鬥/日誌可讀性:D1 戰鬥流水帳 ephemeral · D4 屍體收束 · D2 動作選單分桶(web)/扁平(非 web)。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    from tesrpg.systems import combat
    from tesrpg import main as M
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")

    def _mk(hp):
        e = combat.spawn_creature(gd, "bandit", RNG(1)); e.health = hp; return e

    # D4:>2 已倒下 → 收束成單列 collapsed;≤2 逐列;存活敵帶對齊 key
    mv = ui._combat_view(c, [], [_mk(20), _mk(0), _mk(0), _mk(0)])
    alive = [f for f in mv["enemies"] if not f.get("down")]
    downs = [f for f in mv["enemies"] if f.get("down")]
    assert [f["key"] for f in alive] == ["0"]
    assert len(downs) == 1 and downs[0].get("collapsed") is True and "×3" in downs[0]["name"]
    mv2 = ui._combat_view(c, [], [_mk(20), _mk(0), _mk(0)])
    assert sum(1 for f in mv2["enemies"] if f.get("down")) == 2
    assert not any(f.get("collapsed") for f in mv2["enemies"])   # ≤2 具不收束

    be = WebBackend()
    ui.use_web_backend(be, _rec())
    try:
        # D1:逐擊流水帳 log block 帶 ephemeral;敘事(戰利品)不帶(→ 退役時進永久故事日誌)
        ui.combat_event({"attacker": "你", "defender": "強盜", "hit": True, "blocked": False,
                         "damage": 9, "skill_events": []}, gd)
        logs = [b for b in be.blocks if b["kind"] == "log"]
        assert logs and all(b.get("ephemeral") is True for b in logs)
        # 審查 MAJOR 修:施法/戰技逐回合流水帳走 _cmsg → 同樣 ephemeral(否則法師仍淹沒故事日誌)
        be.blocks = []
        M._cmsg("你的火球命中強盜,造成 24 點魔法傷害!", style="cyan")
        assert [b.get("ephemeral") for b in be.blocks if b["kind"] == "log"] == [True]
        be.blocks = []
        ui.loot_report({"gold": 5, "items": []}, gd)
        assert all("ephemeral" not in b for b in be.blocks if b["kind"] == "log")   # 敘事(戰利品)入永久日誌

        # D2(web):動作選單走 grouped(分桶),回同 key;repeat/攻擊置頂;無「其他」桶(所有 key 已分桶)
        state = GameState(player=c, time=GameTime(), rng=RNG(1))
        grp = {}
        og, ocsg = ui.grouped_menu, ui.combat_status_group
        ui.combat_status_group = lambda *a, **k: None
        ui.grouped_menu = lambda title, groups, extra_keys=None, cta_keys=None: (   # R162:option 可為 (k,label) 或 (k,label,meta) → 取 t[0]
            grp.update(title=title, groups=[(g, [t[0] for t in o]) for g, o in groups]) or "flee")
        try:
            act = M._choose_combat_action(state, gd, [_mk(20)], [])
        finally:
            ui.grouped_menu, ui.combat_status_group = og, ocsg
        assert act["type"] == "flee"
        assert grp["title"] == "你的回合"
        assert grp["groups"][0][0] == "攻擊" and grp["groups"][0][1][0] == "attack"   # 攻擊桶置頂
        assert "其他" not in [g for g, _ in grp["groups"]]                            # 所有動作皆有分桶
        assert "法術·威能" not in [g for g, _ in grp["groups"]]                       # 桶名改 spell-agnostic(涵蓋 rally/deathmark)
    finally:
        _restore()

    # D2(非 web):無 backend → 退回扁平 ui.menu(回同 key)→ 既有 combat 測試零改
    seen = {}
    om, ocsg = ui.menu, ui.combat_status_group
    ui.combat_status_group = lambda *a, **k: None
    ui.menu = lambda title, options, allow_back=False: (seen.update(title=title, flat=True) or "flee")
    try:
        state2 = GameState(player=c, time=GameTime(), rng=RNG(1))
        act2 = M._choose_combat_action(state2, gd, [_mk(20)], [])
    finally:
        ui.menu, ui.combat_status_group = om, ocsg
    assert act2["type"] == "flee" and seen.get("flat") and seen["title"] == "你的回合"


def test_combat_label_split_chip_hover_r162():
    """R162:戰鬥標籤拆「動作詞 / 決策數字 chips / 完整備註 note」——含數字段進 chip、純風味不進 chip。"""
    from tesrpg import main as M
    # 無括號 → 原樣動作詞,無 chip/note
    assert M._split_combat_label("施法") == ("施法", [], "")
    assert M._split_combat_label("↻ 再攻:糖晶藤") == ("↻ 再攻:糖晶藤", [], "")
    # 純風味 → 動作詞 + note(=完整原標籤),無 chip;全形/半形括號皆拆
    assert M._split_combat_label("攻擊（鐵長劍)") == ("攻擊", [], "攻擊（鐵長劍)")
    verb, chips, note = M._split_combat_label("星座之力(瑪拉祝福)")
    assert verb == "星座之力" and chips == [] and note == "星座之力(瑪拉祝福)"
    # 混合 → 只有含數字的段進 chip;風味段不進 chip(但完整備註在 note 供 hover)
    verb, chips, note = M._split_combat_label("隱遁再襲（重獲偷襲·不閃避·成功率 70%,剩 3 次)")
    assert verb == "隱遁再襲"
    assert chips and "70%" in chips[0]["text"] and "剩3次" in chips[0]["text"]
    assert "重獲偷襲" not in chips[0]["text"] and "不閃避" not in chips[0]["text"]
    assert note == "隱遁再襲（重獲偷襲·不閃避·成功率 70%,剩 3 次)"
    assert M._split_combat_label("🔪 致命烙印（標記一敵 · 耗 15 體力)")[1][0]["text"] == "耗15體力"
    # 🔴 守恆(全選單清單,非抽樣):對每個真實戰鬥標籤 —— 動作詞非空、有括號者 note=完整原標籤、
    # 無括號者原樣透傳、且每個含數字/%/∞ 的備註段(去空白後)都必進 chip(否則決策數字漏到只剩 hover)。
    # 這鎖住整個標籤面:未來新增/改標籤若把決策數字漏到 hover-only 會被此測攔下(對抗審查補強)。
    inventory = [
        "施法", "逃跑", "撤下盾牆", "↻ 再攻:糖晶藤", "↻ 再攻（重選目標)",
        "↻ 再施:秘術飛彈→糖晶藤", "↻ 再施:秘術飛彈（重選目標)",
        "攻擊（鐵長劍)", "攻擊（鐵長劍 · 盾擊)", "🐾 種族之力（祖靈守護)",
        "🐺 獸化變身（化身嗜血巨狼)", "收起格擋姿態（恢復全力攻擊)", "格擋姿態（攻擊變緩 · 舉盾卸力減傷)",
        "瞄準射（蓄力強擊 · 額外耗體)", "牽制射（削弱目標攻勢)", "散兵走位（射一箭後遁走)",
        "🐎 衝鋒（坐騎開場突擊 · 長槍藉馬勢洞穿)", "🏹 騎射（馬背放箭 · 大幅提升閃避)",
        "🛡 立盾牆（減傷·嘲諷·護同袍 · 每回合耗體)", "🚩 立戰旗（鼓舞全隊增傷 · 耗魔體)",
        "📣 號令（鼓舞全隊增傷 · 耗體)", "🕊 從容離去（敵意已全平息 · 安然脫身)",
        "星座之力(瑪拉祝福)", "吸血之力(夜之領主)",
        "隱遁再襲（重獲偷襲·不閃避·成功率 70%,剩 3 次)", "隱遁再襲（重獲偷襲·不閃避·成功率 100%,剩 ∞ 次)",
        "重盾掩體（攻擊變緩 · 卸力-38% · 元素-26% · 回氣+2/回)", "箭雨（齊射全體 60% 傷害 · 倍耗體)",
        "🩸 魅惑凝視（迷惑一敵 · 使其恐懼不進攻 · 耗 15 體力)", "🔪 致命烙印（標記一敵 · 耗 15 體力)",
        "🧪 用藥（喝下藥水 · 耗一回合)", "😮‍💨 調息（喘息回體 ~12 · 耗一回合 · 解除架式)",
    ]
    digits = "0123456789０１２３４５６７８９%∞"
    for lbl in inventory:
        verb, chips, note = M._split_combat_label(lbl)
        assert verb.strip(), f"動作詞不得為空:{lbl!r}"
        lo = [i for i in (lbl.find("（"), lbl.find("(")) if i >= 0]
        if lo and (lbl.endswith(")") or lbl.endswith("）")):
            assert note == lbl, f"note 應=完整原標籤:{lbl!r} -> {note!r}"
            chip_text = chips[0]["text"] if chips else ""
            for seg in lbl[min(lo) + 1:-1].replace("，", "·").replace(",", "·").split("·"):
                if any(ch in digits for ch in seg):
                    assert "".join(seg.split()) in chip_text, f"決策數字段 {seg!r} 漏出 chip({lbl!r})"
        else:
            assert (verb, chips, note) == (lbl, [], ""), f"無括號應原樣透傳:{lbl!r} -> {(verb, chips, note)}"


def test_grouped_menu_carries_chips_and_note_r162():
    """R162:真 console.grouped_menu 把 (key,label,meta) 的 chips/note 帶進 spec;
    (key,label) 2-tuple 不帶額外鍵 → 與改動前 byte-identical(地圖/hub/開局 grouped 不受影響)。"""
    captured = {}
    o_wp, o_web = ui._web_prompt, ui._web
    ui._web_prompt = lambda spec: (captured.update(spec) or "x")
    ui._web = object()                     # 非 None → grouped_menu 不 raise
    try:
        ui.grouped_menu("你的回合", [("攻擊", [
            ("vanish", "隱遁再襲", {"chips": [{"text": "70%·剩3"}], "note": "隱遁再襲（…70%,剩3)"}),
            ("cast", "施法"),
        ])])
    finally:
        ui._web_prompt, ui._web = o_wp, o_web
    opts = captured["groups"][0]["options"]
    assert opts[0]["label"] == "隱遁再襲" and opts[0]["chips"] == [{"text": "70%·剩3"}]
    assert opts[0]["note"] == "隱遁再襲（…70%,剩3)"
    assert opts[1]["label"] == "施法" and "chips" not in opts[1] and "note" not in opts[1]


def test_combat_target_reemit_web():
    """web 選敵目標的端到端:該 prompt 幀重發 combat view(敵人卡帶 key),選單鍵對齊卡 key,
    選 "1" 回傳第二隻存活敵人。釘住「blocks 每幀清空 → 須重發才可點卡」的設計。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    from tesrpg.systems import combat
    from tesrpg import main as M
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    foes = [combat.spawn_creature(gd, "giant_rat", RNG(1)), combat.spawn_creature(gd, "giant_rat", RNG(2))]
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        fr, ret = _drive(backend, lambda: M._choose_enemy_target(st, gd, foes, []), lambda s: "1")
        views = [b for b in fr["blocks"] if b["kind"] == "view" and b["name"] == "combat"]
        assert views, fr["blocks"]                                   # 該幀重發了戰鬥畫面
        assert [e.get("key") for e in views[0]["data"]["enemies"]] == ["0", "1"]
        assert [o["key"] for o in fr["prompt"]["options"]] == ["0", "1"]   # 選單鍵對齊卡 key
        assert ret is foes[1]
    finally:
        _restore()


def test_web_combat_menus_each_show_one_board():
    """戰鬥每個 prompt(動作選單 / 法術子選單 / 子選單『返回』後的動作選單)都恰顯一張戰場 ——
    釘住「動作選單丟失敵情」(返回遞迴未重發)與「重複戰場卡」兩個回報 bug。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    from tesrpg.systems import combat
    from tesrpg import main as M
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="female", race="altmer", birthsign="mage", class_id="mage")
    if "minor_heal" not in c.spells:
        c.spells.append("minor_heal")
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    foes = [combat.spawn_creature(gd, "giant_rat", RNG(1))]   # 單敵 → attack 自動選目標、不另起 prompt
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        # 動作選單 → cast;法術選單 → None(返回)→ 遞迴動作選單 → attack(單敵自動選目標 → 返回 action)
        frames, ret = _drive_multi(backend, lambda: M._choose_combat_action(st, gd, foes, []),
                                   [lambda p: "cast", lambda p: None, lambda p: "attack"])
        for i, fr in enumerate(frames):
            n = len([b for b in fr["blocks"] if b["kind"] == "view" and b["name"] == "combat"])
            assert n == 1, f"frame {i} 戰場卡數={n}(應恰 1):{fr['blocks']}"
        assert ret["type"] == "attack"
    finally:
        _restore()


def test_sheet_subview_models():
    """角色卡三子檢視改走專屬 view block(非 panel),形狀正確。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills["block"] = 44       # block 25 待選(達門檻未選)/ 50 未達(差 6 級)
    from tesrpg.systems import mastery as _m   # 再製造一個已選節點 → 覆蓋 chosen 形狀
    _bn = next(n for n in _m._nodes(gd) if n["skill"] == "destruction" and n["threshold"] == 25)
    c.skills["destruction"] = 30
    _m.choose(c, gd, _bn["id"], _m._choosable_options(_bn)[0]["opt_id"])
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        ui.sheet_masteries(c, gd)
        b = backend.blocks[-1]
        assert b["kind"] == "view" and b["name"] == "masteries"
        data = b["data"]
        assert {"chosen", "pending"} <= set(data["summary"])
        assert [s["key"] for s in data["systems"]] == ["combat", "magic", "stealth"]   # 按系統分組
        allnodes = [nd for s in data["systems"] for sk in s["skills"] for nd in sk["nodes"]]
        assert allnodes, "里程碑節點不應為空"
        for nd in allnodes:                                  # 三態 + 配對卡形狀不變式
            assert nd["state"] in ("chosen", "pending", "future")
            assert nd["threshold"] in (25, 50, 75, 100)
            assert nd["options"] and all("name" in o and "desc" in o for o in nd["options"])
            if nd["state"] == "future":
                assert nd["remaining"] >= 0
        blk = next(sk for s in data["systems"] for sk in s["skills"] if sk["skill"] == gd.skill_name("block"))
        n50 = next(nd for nd in blk["nodes"] if nd["threshold"] == 50)
        assert n50["state"] == "future" and n50["remaining"] == 6   # base 44 → 差 6 級未達
        assert blk["has_pending"]                                   # block 25 已達門檻未選 → 預設展開
        chosen = [nd for nd in allnodes if nd["state"] == "chosen"]   # 已選節點:單一 option + foregone 鍵
        assert chosen and all(len(nd["options"]) == 1 and "foregone" in nd for nd in chosen)
        ui.sheet_resistances(c, gd)
        b = backend.blocks[-1]
        assert b["name"] == "resistances" and len(b["data"]["rows"]) == 7   # R127:+物理抗性
        assert all(isinstance(r["value"], int) for r in b["data"]["rows"])
        ui.sheet_spellbook(c, gd)
        b = backend.blocks[-1]
        assert b["name"] == "spellbook"
        for s in b["data"]["schools"]:
            assert s["spells"] and all(sp["cost"] >= 0 and sp["effect"] for sp in s["spells"])
    finally:
        _restore()


def test_sheet_boons_diseases_charges_and_hud_r154():
    """R154 角色卡資訊補完:誓福/疾病 review 面板 + 附魔充能讀數 + HUD renown/魂 chip。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    from tesrpg.systems import boons, dagon_boon, diseases, inventory
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="dunmer", birthsign="mage", class_id="mage")
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        # --- 誓福:空 → panel muted;授予 azura + kvatch_hero + 達貢 → 每道一個 head + 加成 line ---
        ui.sheet_boons(c, gd)
        b = backend.blocks[-1]
        assert b["name"] == "panel" and b["data"]["title"] == "永久誓福"
        assert any(r["t"] == "line" and "尚未" in r["s"] for r in b["data"]["rows"])
        boons.grant(c, gd, "azura"); boons.grant(c, gd, "kvatch_hero"); dagon_boon.grant(c, gd)
        ui.sheet_boons(c, gd)
        rows = backend.blocks[-1]["data"]["rows"]
        heads = [r["s"] for r in rows if r["t"] == "head"]
        assert "達貢之力 —— 主線慘勝" in heads and "晨昏之佑" in heads and "救世主之譽" in heads
        # 每個 head 後緊跟一個加成 line(非空)
        for i, r in enumerate(rows):
            if r["t"] == "head":
                assert rows[i + 1]["t"] == "line" and rows[i + 1]["s"]
        assert any("共 3 道" in r["s"] for r in rows if r["t"] == "line")

        # --- 疾病:空 → muted;染 rockjoint 過 7 日 → 懲罰含惡化階、惡化=已達最重 ---
        ui.sheet_diseases(c, st, gd)
        assert any("沒有染上" in r["s"] for r in backend.blocks[-1]["data"]["rows"] if r["t"] == "line")
        diseases.contract(c, st, gd, "rockjoint")
        st2 = GameState(player=c, time=GameTime(day=8), rng=RNG(1))   # 約 7 日後(惡化 3 階·封頂)
        ui.sheet_diseases(c, st2, gd)
        kv = {r["k"]: r["v"] for r in backend.blocks[-1]["data"]["rows"] if r["t"] == "kv"}
        assert "力量-22" in kv["懲罰"]          # base -10 + worsen -4×3
        assert "已達最重" in kv["惡化"]

        # --- HUD:_hud_view 帶 renown(稱號)+ souls(魂 token) key(在動裝備前查,免污染負重計算)---
        c.fame = 400; c.soul_tokens = 7
        ui._hud_state, ui._hud_gamedata = st, gd
        hv = ui._hud_view()
        assert "renown" in hv and "souls" in hv and hv["souls"] == 7
        assert hv["renown"]   # fame 400 → 有稱號(tier>0)

        # --- 附魔充能:充能型武器顯 ·充能 N/cap(耗盡加⚠);一般武器無此標 ---
        # gd 為共享快取 → 末尾務必 pop 掉臨時物品,且 pop 前不再讀 char 背包(已 unequip 還原)。
        fake = "r154_charged_sword"
        gd.items[fake] = {"name": "噬魂劍", "kind": "weapon", "skill": "blade", "archetype": "sword",
                          "damage": 10, "weight": 10, "value": 50, "enchant": {"kind": "soul_trap", "magnitude": 5}}
        inventory.add_item(c, fake, 1); inventory.equip_weapon(c, gd, fake)
        c.enchant_charges[fake] = 3
        assert "·充能 3/5" in ui._plain(ui.weapon_line(c, gd))
        c.enchant_charges[fake] = 0
        assert "·充能 0/5⚠耗盡" in ui._plain(ui.weapon_line(c, gd))
        assert ui._charge_suffix(c, gd, "iron_sword") == ""   # 一般武器無充能標
        # 防毀損存檔:充能記錄殘留但物品附魔無 magnitude → 不 KeyError,回空(審查 confirmed nit 修)
        broke = "r154_broken_ench"
        gd.items[broke] = {"name": "殘魔劍", "kind": "weapon", "skill": "blade", "damage": 5,
                           "weight": 5, "value": 10, "enchant": {"kind": "soul_trap"}}   # 無 magnitude
        c.enchant_charges[broke] = 2
        assert ui._charge_suffix(c, gd, broke) == ""
    finally:
        gd.items.pop("r154_charged_sword", None)   # 還原共享 gamedata(即使斷言失敗)
        gd.items.pop("r154_broken_ench", None)
        _restore()


def test_board_and_shop_view_shapes():
    """告示板/商店可點面板的命脈:卡 key == 對齊選單的 id(quest-id / item-id);唯讀。"""
    from tesrpg.gamedata import get_gamedata
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    from tesrpg.systems import world
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    # 告示板:view-model 卡 key == 委託 id(== action_board 的選單 key)
    bq = [qid for qid, q in gd.quests.items() if q.get("source") == "board"][:3]
    bv = ui._board_view(c, gd, bq)
    assert [card["key"] for card in bv["quests"]] == bq
    assert all("objective" in card and "rewards" in card for card in bv["quests"])
    # 商店:ensure_stock 後 _shop_view 卡 key == 在庫 item id(== 買單 key),唯讀
    loc = c.location_id
    world.ensure_stock(c, gd, loc, GameTime(), RNG(5))
    avail = world.in_stock_items(c, gd, loc)
    if avail:                                            # 起始城應有商人;無則略過(防呆)
        gold0 = c.gold
        sv = ui._shop_view(c, gd, loc, avail)
        assert [it["key"] for it in sv["items"]] == avail
        assert all(isinstance(it["afford"], bool) and it["kind"] for it in sv["items"])
        assert c.gold == gold0                           # 唯讀


def test_double_submit_and_stale():
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__("v", ui.confirm("?")))
        t.start()
        fr = backend.outbound.get(timeout=5)
        pid = fr["prompt_id"]
        assert backend.submit(pid, True) is True
        assert backend.submit(pid, True) is False         # 雙擊被擋
        assert backend.submit(pid + 5, True) is False      # 亂序 pid 被擋
        t.join(timeout=5)
        assert box["v"] is True
    finally:
        _restore()


def test_int_revalidate():
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__("v", ui.ask_int("?", 8, 1, 24)))
        t.start()
        fr1 = backend.outbound.get(timeout=5)
        assert fr1["resend"] is False                         # 首送 → 故事日誌照記
        assert backend.submit(fr1["prompt_id"], 99) is True   # 投遞成功但越界 → 重新詢問
        fr2 = backend.outbound.get(timeout=5)
        assert fr2["prompt_id"] != fr1["prompt_id"]
        assert fr2["resend"] is True                          # 重送同 blocks → 前端據此才做內容去重(否則正常重複敘事被誤吞)
        assert fr2["blocks"] == fr1["blocks"]                 # 重送=逐位元組同一 blocks
        assert backend.submit(fr2["prompt_id"], 10) is True
        t.join(timeout=5)
        assert box["v"] == 10
    finally:
        _restore()


def _drive_one_game(backend):
    """在 thread 跑一整局 main():新遊戲→快速角色→隱退→主選單→離開,自動作答。
    回傳 {mainmenu:主選單出現次數, returned:main 是否乾淨返回, exc:例外}。"""
    import queue as _q
    from tesrpg import main as M
    box = {"returned": False, "exc": None}

    def worker():
        try:
            M.main()
            box["returned"] = True
        except BaseException as e:        # noqa: 把 worker 例外帶回主執行緒
            box["exc"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    mm = 0
    for _ in range(80):                   # 步數上限防卡死
        try:
            fr = backend.outbound.get(timeout=0.5)
        except _q.Empty:
            if t.is_alive():
                continue                  # worker 仍在跑、偶發慢幀 → 續等(不誤判本局結束)
            break                         # worker 已返回 → 無更多幀,本局正常結束
                                          # (修競態:原 timeout=5 在最終答 quit 後盲等永不到來的幀 → 每局吃滿 5s)
        spec = fr["prompt"]; typ = spec.get("type"); title = spec.get("title", "")
        if typ == "end":
            break
        if typ == "confirm":
            ans = True                    # 快速開始 / 隱退確認 一律是
        elif typ == "menu":
            if title.startswith("主選單"):   # G:標題改「主選單 —— 角色名冊」
                mm += 1; ans = "quit" if mm >= 2 else "new"
            elif title == "選擇遊戲模式":
                ans = "adventure"
            else:
                ans = spec["options"][0]["key"]
        elif typ == "grouped":
            keys = [o["key"] for g in spec["groups"] for o in g["options"]]
            ans = "retire" if "retire" in keys else keys[0]
        elif typ == "int":
            ans = spec["lo"]
        elif typ == "text":
            ans = ""
        else:
            ans = None
        backend.submit(fr["prompt_id"], ans)
        if box["returned"] and backend.outbound.empty():
            break
    t.join(timeout=5)
    box["mainmenu"] = mm
    return box


def test_web_session_restartable_after_game_over():
    """修『結束無法重開(重整也沒用)』的核心不變式:main() 一局結束後可在同一 backend
    上**再跑一局**(= _run_game 迴圈所倚賴 —— main() 可重複進入,無模組殘留致死)。
    驅動兩局『新遊戲→快速角色→隱退→主選單→離開』,證明第二局照常開到主選單。"""
    import tempfile
    from pathlib import Path
    from tesrpg import main as M
    from tesrpg.systems import saves, hall
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    tmp = tempfile.TemporaryDirectory()
    saved = (saves.SAVES_DIR, saves.LEGACY_PATH)   # G:槽位隔離到暫存目錄,免污染真實 ~/.tesrpg
    saved_hall = hall.HALL_PATH                     # R160:隱退=終局 → end_run 會寫名人堂,同樣隔離
    saves.SAVES_DIR = Path(tmp.name) / "saves"
    saves.LEGACY_PATH = Path(tmp.name) / "save.json"
    hall.HALL_PATH = Path(tmp.name) / "hall.json"
    try:
        for game in range(2):                          # 跑兩局:第二局仍能開到主選單 = 可重開
            res = _drive_one_game(backend)
            assert res["exc"] is None, (game, repr(res["exc"]))
            assert res["returned"], (game, "main() 未乾淨返回 → _run_game 迴圈無法重啟")
            assert res["mainmenu"] >= 2, (game, res)   # 開局主選單 + 隱退後主選單(內建可重開)
            assert M._onset_hinted is None, "R155:main() 乾淨返回後 finally 須把 _onset_hinted 復位為 None(game_loop 外=no-op)"
            backend.flush_final("")                    # 模擬 _run_game 兩局之間的 end 哨兵
            try:
                backend.outbound.get(timeout=1)        # 抽掉 end 幀,免污染下一局驅動
            except Exception:
                pass
        assert saves.used_slots(), "隱退後角色應留在名冊(槽位存檔)"   # G:新增名冊不變式
    finally:
        saves.SAVES_DIR, saves.LEGACY_PATH = saved
        hall.HALL_PATH = saved_hall
        M._active_save = None   # G:main() 驅動設了活槽 → 復位免洩漏死路徑到後續模組
        tmp.cleanup()
        _restore()


def test_flush_final_and_generation():
    backend = WebBackend()
    g1 = backend.new_generation()
    g2 = backend.new_generation()
    assert g2 == g1 + 1
    backend.flush_final("<span>bye</span>")
    fr = backend.outbound.get(timeout=2)
    assert fr["prompt"]["type"] == "end"
    assert any(b["kind"] == "html" and "bye" in b["html"] for b in fr["blocks"])
    assert fr["seq"] > 0


def test_card_grid_for_chip_menus():
    """R61:帶 chips 的選卡選單(種族/星座/職業)走等寬 grid → 孤卡不撐滿整排。
    守前端契約:cardgrid CSS 規則 + renderPrompt 依 o.chips 切換 class 不被誤刪。"""
    static = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tesrpg", "web", "static", "index.html")
    with open(static, encoding="utf-8") as f:
        html = f.read()
    assert ".btns.cardgrid" in html                              # grid 規則存在
    assert "repeat(auto-fill, minmax(230px, 1fr))" in html       # auto-fill 保留空軌(孤卡不撐大)
    assert 'classList.add("cardgrid")' in html                   # renderPrompt 依 chips 切換
    assert "o.chips && o.chips.length" in html                   # 偵測訊號 = 選項帶 chips


def test_map_service_filter_and_pips_r160c():
    """R160c 地圖服務標記/篩選:前端契約 —— 篩選 chip 列 + 公會徽 pip + 高亮/暗化/最近X 邏輯存在,
    且 payload 已備(svc/svc_all/hops)零後端改動。純字串契約(前端 JS 不由 run_all 執行)。"""
    static = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tesrpg", "web", "static", "index.html")
    with open(static, encoding="utf-8") as f:
        html = f.read()
    # 篩選 chip 列(動態衍生自 svc_all·單選)+ 說明(aria-live)在 pan surface 外
    assert '<div class="msvcbar"' in html and 'class="msvc-find" aria-live="polite"' in html
    assert 'class="mzb svc"' in html and 'data-svc=' in html and 'aria-pressed=' in html
    assert "SVC_ORDER" in html and "IS_GUILD" in html and "SVC_ABBR" in html   # 固定序 + 公會軸 + 縮寫
    # 公會徽 pip(縮放/行省檢視才顯,復用 .prov/.zoomed gate;篩選時匹配城強制顯)
    assert 'class="mpip"' in html
    assert ".mapstage.prov .mpip,.mapstage.zoomed .mpip{display:inline-block;}" in html
    # 高亮/暗化:filtering 暗化非匹配、★你在此豁免、匹配金光
    assert ".mapzoom.filtering .mmark{opacity:.22;}" in html
    assert ".mapzoom.filtering .mmark.here{opacity:.9;}" in html
    assert ".mapzoom.filtering .mmark.svcmatch{" in html
    # applyMatch(重繪後重套)+ updateFind(最近X·hops 排序·前往走既有 route:)
    assert "function applyMatch()" in html and "applyMatch();" in html   # draw 尾呼叫
    assert "function updateFind()" in html and 'submit("route:" + reach[0].id)' in html
    assert "n.hops != null" in html and ".sort(" in html                 # 最近=可達且 hops 最小
    # fs-scale + 主題安全 + WCAG 觸控目標:新控件確實用 fs-scale,且觸控目標有 24px 地板
    assert ".msvcbar .lab{color:var(--gold-dim);font-size:calc(11.5px*var(--fs-scale,1))" in html
    assert "min-height:max(24px,calc(26px*var(--fs-scale,1)))" in html   # chip 觸控目標不低於 WCAG 24px
    assert ".msvc-find .mi-hint{color:var(--faint);}" in html            # 淡化提示在 .msvc-find 亦生效(非只 .mapinfo)
    assert 'role="group"' in html and 'aria-label="依服務篩選地點"' in html   # 篩選 chip 列曝光為具名群組(AT)
    # 公會徽強制顯只在公會篩選(gfilter);常見服務篩選不顯無關公會徽
    assert ".mapzoom.gfilter .mmark.svcmatch .mpip{display:inline-block;}" in html
    assert 'zoom.classList.toggle("gfilter"' in html
    assert 'data-key' not in html.split('class="mzb svc"')[0][-200:]     # svc chip 不掛 data-key(不搶數字鍵)


def test_back_key_works_on_large_menus():
    """選單審查修:≥10 項選單按 0 也要觸發返回(原本被多位數字緩衝吞掉 → 頁尾承諾的 0=返回 失效)。"""
    static = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tesrpg", "web", "static", "index.html")
    with open(static, encoding="utf-8") as f:
        html = f.read()
    assert 'e.key === "0" && !digitBuf' in html       # 大選單:首位 0(非接續數字)→ 返回


def test_origin_pick_clears_screen():
    """創角開局選定/返回後送出 clear 狀態塊 → 後續職業選單不殘留『開局一覽』面板(stale residue 修)。"""
    from tesrpg import main as M
    from tesrpg.gamedata import get_gamedata
    gd = get_gamedata()
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    try:
        def ans(spec):
            if spec["type"] == "menu":                       # 類別選單 → 選第一類
                return spec["options"][0]["key"]
            return spec.get("extra_keys", ["__back__"])[0]   # picker(grouped)→ 點第一張開局卡
        frames, pick = _drive_multi(backend, lambda: M._choose_origin(gd, allow_back=True), [ans, ans])
        assert pick is not None
        assert any(b["kind"] == "clear" for b in frames[0]["blocks"])    # 類別選單前已清屏
        assert any(b.get("kind") == "clear" for b in backend.blocks)     # 選定後 pending clear(供下一步職業清屏)
    finally:
        _restore()


def test_clear_block_and_frontend_filter():
    """clear 機制契約:後端 clear_block 出 clear kind;前端 render 把 clear 計入 stateBlocks(→ 清屏)。"""
    backend = WebBackend()
    backend.clear_block()
    assert backend.blocks and backend.blocks[-1]["kind"] == "clear"
    static = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tesrpg", "web", "static", "index.html")
    with open(static, encoding="utf-8") as f:
        html = f.read()
    assert 'b.kind === "clear"' in html   # render() 把 clear 視為 state block → renderScreen 清屏


def run():
    # 其他測試模組(test_m12/m13 等)在 import 時就把 ui.menu 換成 stub 並未還原;
    # reload 還原真正的 5 個輸入原語,確保此處測到的是 web seam 而非別人的 stub。
    importlib.reload(ui)
    for _name, _fn in sorted(globals().items()):      # 與其餘模組一致:globals() 自動收集,免手動清單漏跑
        if _name.startswith("test_") and callable(_fn):
            _fn()
    _restore()                                         # 清 ui._web,免污染後續模組


if __name__ == "__main__":
    run()
    print("✓ test_web")
