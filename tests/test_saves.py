"""存檔槽位 / 多角色(G)測試:名冊 meta / 空槽配置 / 遷移 / 刪除 / 毀損安全。

存讀檔格式不變(仍走 GameState.save/load);本模組只驗「哪個檔在哪個槽 + 輕量名冊」。
SAVES_DIR/LEGACY_PATH 於每測覆寫到暫存目錄,免污染真實 ~/.tesrpg。
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import hall, saves


def _env():
    """回 (tempdir_obj, restore_fn);把 saves + 名人堂目錄指向暫存(免污染真實 ~/.tesrpg)。"""
    td = tempfile.TemporaryDirectory()
    orig = (saves.SAVES_DIR, saves.LEGACY_PATH, hall.HALL_PATH)
    saves.SAVES_DIR = Path(td.name) / "saves"
    saves.LEGACY_PATH = Path(td.name) / "save.json"
    hall.HALL_PATH = Path(td.name) / "hall.json"   # R160:end_run 終局會寫名人堂 → 同樣隔離

    def restore():
        saves.SAVES_DIR, saves.LEGACY_PATH, hall.HALL_PATH = orig
        td.cleanup()
    return td, restore


def _mk_state(gd, name="測", mode="adventure"):
    c = build_character(gd, name=name, sex="male", race="nord", birthsign="warrior", class_id="warrior")
    return GameState(player=c, rng=RNG(1), game_mode=mode)


def test_empty_and_next_free_and_fill():
    gd = get_gamedata()
    _td, restore = _env()
    try:
        assert saves.used_slots() == [] and saves.roster(gd) == []
        assert saves.next_free_slot() == 1
        # 填滿 → next_free 回 None
        for n in range(1, saves.MAX_SLOTS + 1):
            _mk_state(gd, name=f"角{n}").save(saves.slot_path(n))
        assert saves.used_slots() == list(range(1, saves.MAX_SLOTS + 1))
        assert saves.next_free_slot() is None            # 滿
        saves.delete_slot(3)                              # 刪中間 → next_free 補該洞
        assert saves.next_free_slot() == 3
    finally:
        restore()


def test_slot_meta_and_roster():
    gd = get_gamedata()
    _td, restore = _env()
    try:
        _mk_state(gd, name="索菈", mode="legend").save(saves.slot_path(2))
        m = saves.slot_meta(2, gd)
        assert m["slot"] == 2 and m["name"] == "索菈" and m["level"] >= 1
        assert m["mode"] == "legend" and m["mode_cn"] == "傳奇"
        assert m["province"] and m["day"] and not m["corrupt"]
        assert saves.slot_meta(5, gd) is None            # 不存在 → None
        # roster 按槽位序
        _mk_state(gd, name="卡").save(saves.slot_path(1))
        r = saves.roster(gd)
        assert [x["slot"] for x in r] == [1, 2]
    finally:
        restore()


def test_corrupt_slot_is_safe():
    gd = get_gamedata()
    _td, restore = _env()
    try:
        saves.SAVES_DIR.mkdir(parents=True, exist_ok=True)
        saves.slot_path(1).write_text("{ not valid json", encoding="utf-8")
        m = saves.slot_meta(1, gd)
        assert m is not None and m["corrupt"] is True     # 不拋例外,回毀損佔位
        assert m["slot"] == 1
        assert saves.used_slots() == [1]                  # 毀損檔仍算佔用(可刪)
        r = saves.roster(gd)
        assert len(r) == 1 and r[0]["corrupt"]
        saves.delete_slot(1)
        assert saves.used_slots() == []
    finally:
        restore()


def test_migrate_legacy():
    gd = get_gamedata()
    _td, restore = _env()
    try:
        # 舊單一存檔存在、無 slot1 → 遷移到 slot1
        _mk_state(gd, name="老角").save(saves.LEGACY_PATH)
        assert not saves.slot_path(1).exists()
        saves.migrate_legacy()
        assert saves.slot_path(1).exists() and not saves.LEGACY_PATH.exists()
        assert saves.slot_meta(1, gd)["name"] == "老角"
        # 冪等:再呼叫不出事
        saves.migrate_legacy()
        assert saves.slot_path(1).exists()
        # 已有 slot1 時,舊檔不覆蓋(保留既有 slot1)
        _mk_state(gd, name="新角").save(saves.LEGACY_PATH)
        saves.migrate_legacy()
        assert saves.slot_meta(1, gd)["name"] == "老角"   # slot1 未被覆蓋
        assert saves.LEGACY_PATH.exists()                 # 舊檔留著(不搬)
    finally:
        restore()


def test_slot_label_shows_identity():
    import tesrpg.main as M
    m = {"slot": 2, "name": "索菈", "level": 12, "province": "天際", "mode_cn": "冒險", "day": 45, "mtime": 0, "corrupt": False}
    label = M._slot_label(m)
    for token in ("索菈", "Lv.12", "天際", "冒險", "第45日"):
        assert token in label, (token, label)
    cm = M._slot_label({"slot": 3, "corrupt": True})
    assert "毀損" in cm and "槽 3" in cm


def test_delete_flow_confirm_and_cancel():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd = get_gamedata()
    _td, restore = _env()
    om, oc, omsg = ui.menu, ui.confirm, ui.message
    ui.message = lambda *a, **k: None
    try:
        _mk_state(gd, name="甲").save(saves.slot_path(1))
        _mk_state(gd, name="乙").save(saves.slot_path(2))
        roster = saves.roster(gd)
        # 取消(confirm=False)→ 不刪
        ui.menu = lambda *a, **k: "del:2"; ui.confirm = lambda *a, **k: False
        M._delete_save_flow(roster)
        assert saves.used_slots() == [1, 2]
        # 確認(confirm=True)→ 刪指定槽
        ui.confirm = lambda *a, **k: True
        M._delete_save_flow(roster)
        assert saves.used_slots() == [1]
        # 返回(menu 回 None)→ 不刪
        ui.menu = lambda *a, **k: None
        M._delete_save_flow(saves.roster(gd))
        assert saves.used_slots() == [1]
    finally:
        ui.menu, ui.confirm, ui.message = om, oc, omsg
        restore()


def test_retire_persists_state_and_legend_death_deletes_slot():
    """審查修:隱退存最終狀態(名冊/繼續反映隱退點);傳奇死亡抹除該槽(冒險死亡保留)。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd = get_gamedata()
    _td, restore = _env()
    saved_ui = (ui.rule, ui.message, ui.legacy_screen)
    saved_active = M._active_save
    ui.rule = lambda *a, **k: None
    ui.message = lambda *a, **k: None
    ui.legacy_screen = lambda *a, **k: None
    try:
        # --- 隱退:存最終狀態 ---
        st = _mk_state(gd, name="隱者")
        st.player.level = 7                                # 區別性狀態
        M._active_save = saves.slot_path(1)
        M.end_run(st, gd, "retire")
        assert saves.slot_path(1).exists()                 # 隱退保留槽
        assert saves.slot_meta(1, gd)["level"] == 7        # 反映隱退當下(非上次手動存檔)

        # --- 傳奇模式死亡:抹除該角槽,不動別人 ---
        other = _mk_state(gd, name="旁人")
        other.save(saves.slot_path(2))
        dead = _mk_state(gd, name="亡者", mode="legend")
        dead.save(saves.slot_path(3))
        M._active_save = saves.slot_path(3)
        M.end_run(dead, gd, "death")
        assert not saves.slot_path(3).exists()             # 傳奇死亡:自己的槽被抹除
        assert saves.slot_path(2).exists()                 # 別人的槽不動

        # --- 冒險模式死亡:保留槽(可讀檔重來)---
        adv = _mk_state(gd, name="冒險者", mode="adventure")
        adv.save(saves.slot_path(4))
        M._active_save = saves.slot_path(4)
        M.end_run(adv, gd, "death")
        assert saves.slot_path(4).exists()                 # 冒險死亡:槽保留
    finally:
        ui.rule, ui.message, ui.legacy_screen = saved_ui
        M._active_save = saved_active
        restore()


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_saves")
