"""名人堂 / 往昔英雄(Hall of Fame)測試(R160)。

hall.json 為獨立持久檔(零存檔格式變更);只在 end_run「終局」(隱退 / 傳奇死)留名。
HALL_PATH 於每測覆寫到暫存,免污染真實 ~/.tesrpg。
"""

import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

from tesrpg.gamedata import get_gamedata
from tesrpg.systems import hall
from tesrpg.ui import console as ui


def _env():
    """回 (tempdir_obj, restore_fn);把 HALL_PATH 指向暫存。"""
    td = tempfile.TemporaryDirectory()
    orig = hall.HALL_PATH
    hall.HALL_PATH = Path(td.name) / "hall.json"

    def restore():
        hall.HALL_PATH = orig
        td.cleanup()
    return td, restore


def _legacy(name="阿", score=1000, ending="death", **kw):
    d = {"name": name, "race": "諾德", "sex": "男", "birthsign": "戰士座", "class": "戰士",
         "playstyle": "沙場武者", "level": 20, "years": 2, "days": 30, "score": score,
         "title": "英傑", "ending": ending, "achievements": ["a"], "achievements_total": 46,
         "factions": [], "condition": None, "lycanthropy": None, "dominion": None,
         "dark_deeds": None, "comrade": None}
    d.update(kw)
    return d


def test_is_terminal_records_only_completed_lives():
    # 隱退(任何模式)+ 傳奇死 = 終局留名;冒險死=回上次存檔續命 → 不留名(避免重複記錄)
    assert hall.is_terminal("retire", "adventure") is True
    assert hall.is_terminal("retire", "legend") is True
    assert hall.is_terminal("death", "legend") is True
    assert hall.is_terminal("death", "adventure") is False


def test_record_sorts_by_score_and_caps():
    _td, restore = _env()
    try:
        assert hall.load_entries() == [] and hall.has_entries() is False
        hall.record(_legacy("低", 500), "adventure")
        hall.record(_legacy("高", 5000), "legend")
        hall.record(_legacy("中", 2000, ending="retire"), "adventure")
        ents = hall.load_entries()
        assert [e["name"] for e in ents] == ["高", "中", "低"]          # 依分數遞減
        assert ents[0]["mode"] == "legend" and ents[0]["ending"] == "death"
        # 上限:塞爆 MAX_ENTRIES+5 筆 → 只留最高 MAX_ENTRIES 筆
        for i in range(hall.MAX_ENTRIES + 5):
            hall.record(_legacy(f"x{i}", 6000 + i), "adventure")
        ents = hall.load_entries()
        assert len(ents) == hall.MAX_ENTRIES
        assert ents[0]["score"] == 6000 + hall.MAX_ENTRIES + 4          # 最高分在頂
        assert all(e["score"] >= 6000 for e in ents)                    # 低分全被擠出
    finally:
        restore()


def test_entry_distills_feats_from_legacy():
    _td, restore = _env()
    try:
        lg = _legacy("英雄", 3000, factions=[("戰士公會", "公會長"), ("戰友團", "先驅")],
                     condition="吸血鬼·血主", dominion="據有 3 城")
        hall.record(lg, "legend")
        e = hall.load_entries()[0]
        assert e["feats"][:2] == ["戰士公會·公會長", "戰友團·先驅"]
        assert "吸血鬼·血主" in e["feats"] and "據有 3 城" in e["feats"]
        assert len(e["feats"]) <= 5
        assert e["achievements"] == 1 and e["achievements_total"] == 46
    finally:
        restore()


def test_corruption_and_missing_are_safe():
    _td, restore = _env()
    try:
        assert hall.load_entries() == []                    # 缺檔 → 空
        hall.HALL_PATH.parent.mkdir(parents=True, exist_ok=True)
        hall.HALL_PATH.write_text("{ not json", encoding="utf-8")
        assert hall.load_entries() == [] and hall.has_entries() is False   # 毀損 → 空(不崩)
        hall.HALL_PATH.write_text('{"not": "a list"}', encoding="utf-8")
        assert hall.load_entries() == []                    # 非 list → 空
        # 手改/毀損檔:合法 JSON list 但 score 為 null/非數值 → 排序鍵不得 int(None) 崩(啟動路徑)
        hall.HALL_PATH.write_text('[{"name":"壞","score":null},{"name":"好","score":9}]', encoding="utf-8")
        ents = hall.load_entries()
        assert [e["name"] for e in ents] == ["好", "壞"]      # null score 視為 0,排最後,不崩
        hall.record(_legacy("恢復", 100), "adventure")       # 毀損後仍可寫入
        assert "恢復" in [e["name"] for e in hall.load_entries()]
    finally:
        restore()


def test_atomic_write_no_tmp_left():
    _td, restore = _env()
    try:
        hall.record(_legacy("甲", 100), "adventure")
        # 原子寫:.tmp 已 replace 覆蓋,不殘留
        assert not hall.HALL_PATH.with_name(hall.HALL_PATH.name + ".tmp").exists()
        assert hall.HALL_PATH.exists()
    finally:
        restore()


def test_hall_screen_renders(monkeypatch=None):
    """名人堂面板渲染(終端 fallback:_web=None)——空 + 非空皆不 raise。"""
    _td, restore = _env()
    saved_console, saved_web = ui.console, ui._web
    ui._web = None
    ui.console = Console(file=io.StringIO(), width=100)
    try:
        ui.hall_screen([])                                  # 空
        hall.record(_legacy("演示", 2000, factions=[("法師公會", "大法師")]), "legend")
        ui.hall_screen(hall.load_entries())                 # 非空
    finally:
        ui.console, ui._web = saved_console, saved_web
        restore()


def test_hall_screen_web_view_shape():
    """web 模式:hall_screen 發出合法 panel view block(rows 皆 head/kv/line)。"""
    from tesrpg.web.backend import WebBackend
    _td, restore = _env()
    be = WebBackend()
    ui.use_web_backend(be, Console(record=True, file=io.StringIO(), width=100))
    try:
        hall.record(_legacy("網頁", 1500), "adventure")
        ui.hall_screen(hall.load_entries())
        b = be.blocks[-1]
        assert b["kind"] == "view" and b["name"] == "panel"
        rows = b["data"]["rows"]
        assert rows and all(r["t"] in ("head", "kv", "line") for r in rows)
        assert any("網頁" in str(r.get("k", "")) for r in rows if r["t"] == "kv")
    finally:
        ui._web = None
        ui.console = Console()
        restore()


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_hall")
