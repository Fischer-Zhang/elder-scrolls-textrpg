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
    """本輪 UI 改版的 view-model 形狀回歸:戰鬥魔力/狀態標分色、傳奇分段、地圖省份進度。"""
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
    assert cv["enemies"][0]["mp"] == [0, 0]                   # 怪物無魔力 → JS 以 mp[1] 假值隱藏
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
        assert b["name"] == "resistances" and len(b["data"]["rows"]) == 6
        assert all(isinstance(r["value"], int) for r in b["data"]["rows"])
        ui.sheet_spellbook(c, gd)
        b = backend.blocks[-1]
        assert b["name"] == "spellbook"
        for s in b["data"]["schools"]:
            assert s["spells"] and all(sp["cost"] >= 0 and sp["effect"] for sp in s["spells"])
    finally:
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
            if title == "主選單":
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
    backend = WebBackend()
    ui.use_web_backend(backend, _rec())
    saved_path = M.SAVE_PATH
    M.SAVE_PATH = Path(tempfile.gettempdir()) / "tesrpg_test_nosave.json"
    M.SAVE_PATH.unlink(missing_ok=True)
    try:
        for game in range(2):                          # 跑兩局:第二局仍能開到主選單 = 可重開
            res = _drive_one_game(backend)
            assert res["exc"] is None, (game, repr(res["exc"]))
            assert res["returned"], (game, "main() 未乾淨返回 → _run_game 迴圈無法重啟")
            assert res["mainmenu"] >= 2, (game, res)   # 開局主選單 + 隱退後主選單(內建可重開)
            backend.flush_final("")                    # 模擬 _run_game 兩局之間的 end 哨兵
            try:
                backend.outbound.get(timeout=1)        # 抽掉 end 幀,免污染下一局驅動
            except Exception:
                pass
    finally:
        M.SAVE_PATH = saved_path
        (Path(tempfile.gettempdir()) / "tesrpg_test_nosave.json").unlink(missing_ok=True)
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
