"""遊戲內指南/圖鑑(codex)測試:schema lint + 渲染煙霧 + action 唯讀(R60)。

codex 是唯讀 how-to 內容:內容在 data/codex.json,渲染走 ui.codex_panel(複用原生 panel view)。
鐵律:測試結束務必還原 ui._web=None / ui.console,以免污染後續測試模組。
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

from tesrpg.gamedata import get_gamedata
from tesrpg.ui import console as ui
from tesrpg.web.backend import WebBackend

_TONES = {"muted", "faint", "green", "red", "cyan", "gold", "magenta", "yellow"}
# v1 應有的分類 id(刪類/打錯 id 會被這條測到)
_EXPECTED_IDS = {
    "core_loop", "races_signs", "skills_mastery", "combat_control", "magic_schools", "alchemy_poison",
    "enchant_soulgem", "factions_guilds", "curse_vampire", "curse_werewolf",
    "disease_temple", "crime_bounty", "world_explore", "realm_warband",
}


def _entries(gd):
    return {cid: e for cid, e in gd.codex.items() if not cid.startswith("_")}


def test_codex_loads_and_covers_expected():
    gd = get_gamedata()
    entries = _entries(gd)
    assert entries, "gamedata.codex 應載入且非空"
    assert _EXPECTED_IDS <= set(entries), f"缺少分類:{_EXPECTED_IDS - set(entries)}"


def test_codex_schema():
    gd = get_gamedata()
    for cid, e in _entries(gd).items():
        assert isinstance(e, dict), cid
        assert cid == cid.lower() and cid.replace("_", "").isalnum(), f"id 格式須小寫英數底線:{cid}"
        assert isinstance(e.get("title"), str) and e["title"], f"{cid} 缺非空 title"
        if "order" in e:
            assert isinstance(e["order"], int), f"{cid} order 非 int"
        if "icon" in e:
            assert isinstance(e["icon"], str) and e["icon"], f"{cid} icon 非空字串"
        secs = e.get("sections")
        assert isinstance(secs, list) and secs, f"{cid} sections 須非空 list"
        for sec in secs:
            assert isinstance(sec, dict), f"{cid} section 非 dict"
            shapes = [k for k in ("h", "p", "kv", "li") if k in sec]
            assert len(shapes) == 1, f"{cid} section 須恰含 h/p/kv/li 其一:{sec}"
            if "kv" in sec:
                assert isinstance(sec["kv"], list) and len(sec["kv"]) == 2, f"{cid} kv 須 2 元素:{sec}"
            if "c" in sec:
                assert sec["c"] in _TONES, f"{cid} 著色非法:{sec['c']}"


def test_codex_index_sorted():
    gd = get_gamedata()
    idx = ui.codex_index(gd)
    assert len(idx) == len(_entries(gd))
    assert idx[0][0] == "core_loop"                                  # order 10 → 置頂
    orders = [gd.codex[cid].get("order", 9999) for cid, _ in idx]
    assert orders == sorted(orders), "codex_index 須依 order 遞增"
    assert all(lbl.strip() for _cid, lbl in idx), "選單標籤須非空"


def test_codex_panel_renders_all_entries():
    """每個分類經 WebBackend 渲成合法 panel view,無例外;disease_temple 追加動態神殿一覽。"""
    gd = get_gamedata()
    be = WebBackend()
    ui.use_web_backend(be, Console(record=True, file=io.StringIO(), width=100))
    try:
        for cid in _entries(gd):
            ui.codex_panel(gd.codex[cid], gd)
            b = be.blocks[-1]
            assert b["kind"] == "view" and b["name"] == "panel", cid
            assert isinstance(b["data"]["title"], str) and b["data"]["title"], cid
            rows = b["data"]["rows"]
            assert rows and all(r["t"] in ("head", "kv", "line") for r in rows), cid
        # 動態鉤子:disease_temple 含『神殿一覽』head + 對上 world 帶 shrine 的地點
        ui.codex_panel(gd.codex["disease_temple"], gd)
        rows = be.blocks[-1]["data"]["rows"]
        assert any(r["t"] == "head" and "神殿一覽" in r["s"] for r in rows)
        shrine_locs = [loc for loc in gd.world["locations"].values() if loc.get("shrine")]
        assert len([r for r in rows if r["t"] == "kv"]) >= len(shrine_locs) >= 1
        # 動態鉤子:races_signs 追加『十大種族』+『出生星座』速查 → 每族/每星座各一列(隨資料更新,防陳舊)
        ui.codex_panel(gd.codex["races_signs"], gd)
        rows = be.blocks[-1]["data"]["rows"]
        assert any(r["t"] == "head" and "種族" in r["s"] for r in rows)
        kvs = [r for r in rows if r["t"] == "kv"]
        assert len(kvs) == len(gd.races) + len(gd.birthsigns)
        rk = {r["k"] for r in kvs}
        assert all(r["name"] in rk for r in gd.races.values()), "每個種族都應有一列"
    finally:
        ui._web = None
        ui.console = Console()


def test_codex_panel_terminal_fallback():
    """終端 fallback(_web=None)渲染每個分類無例外(R27 退路保留,web-only 下不執行)。"""
    gd = get_gamedata()
    saved = ui.console
    ui._web = None
    ui.console = Console(file=io.StringIO(), width=100)
    try:
        for cid in _entries(gd):
            ui.codex_panel(gd.codex[cid], gd)        # 不應 raise
    finally:
        ui.console = saved


def test_action_codex_readonly():
    """action_codex:menu-stub 驅動 → 回 None、角色與時間皆不變(唯讀、零存檔)。"""
    import tesrpg.main as M
    from tesrpg.creation import build_character
    from tesrpg.state import GameState, GameTime
    from tesrpg.rng import RNG
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    before_char, before_hours = c.to_dict(), st.time.absolute_hours()
    seq = iter(["core_loop", "disease_temple", None])    # 看兩個分類再返回
    saved_menu, saved_panel = ui.menu, ui.codex_panel
    ui.menu = lambda *a, **k: next(seq, None)
    ui.codex_panel = lambda *a, **k: None                 # 本測只驗唯讀性,渲染另測
    try:
        assert M.action_codex(st, gd) is None
    finally:
        ui.menu, ui.codex_panel = saved_menu, saved_panel
    assert c.to_dict() == before_char, "codex 不應改動角色"
    assert st.time.absolute_hours() == before_hours, "codex 不應推進時間"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_codex")
