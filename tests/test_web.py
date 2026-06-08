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
        assert backend.submit(fr1["prompt_id"], 99) is True   # 投遞成功但越界 → 重新詢問
        fr2 = backend.outbound.get(timeout=5)
        assert fr2["prompt_id"] != fr1["prompt_id"]
        assert backend.submit(fr2["prompt_id"], 10) is True
        t.join(timeout=5)
        assert box["v"] == 10
    finally:
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


def run():
    # 其他測試模組(test_m12/m13 等)在 import 時就把 ui.menu 換成 stub 並未還原;
    # reload 還原真正的 5 個輸入原語,確保此處測到的是 web seam 而非別人的 stub。
    importlib.reload(ui)
    test_validate()
    test_seam_roundtrip()
    test_blocks_protocol()
    test_hud_and_view_block()
    test_view_model_shapes()
    test_combat_target_key_parity()
    test_combat_target_reemit_web()
    test_double_submit_and_stale()
    test_int_revalidate()
    test_flush_final_and_generation()
    _restore()


if __name__ == "__main__":
    run()
    print("✓ test_web")
