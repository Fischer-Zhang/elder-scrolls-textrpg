"""新手清晰度(R155):創角 build 槓桿說明 + 衍生數值預覽 + 系統開場指路(session 暫態·零存檔)。

鐵律:測試結束還原被 patch 的 ui 函式,以免污染後續模組。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tesrpg.gamedata import get_gamedata
from tesrpg.ui import console as ui
import tesrpg.main as M


def test_hint_once_disabled_by_default_and_fires_once():
    """_onset_hinted=None(game_loop 外·測試/sim 路徑)→ no-op;啟用後每 key 只報一次。"""
    saved = M._onset_hinted
    msgs = []
    om = ui.message
    ui.message = lambda s, **k: msgs.append(s)
    try:
        M._onset_hinted = None                     # 未啟用 → 直呼 run_battle 等不噴提示(byte-safe)
        M._hint_once("combat", "SHOULD_NOT_SHOW")
        assert msgs == []
        M._onset_hinted = set()                    # game_loop 內啟用 → 去重
        M._hint_once("combat", "A")
        M._hint_once("combat", "B")                # 同 key 第二次 → 不報
        M._hint_once("alchemy", "C")
        assert msgs == ["A", "C"]
    finally:
        ui.message = om
        M._onset_hinted = saved


def test_explain_build_levers_prints_three_levers():
    """預設職業路徑也講明 專精/偏好/主修 三個 build 槓桿(過去只有自訂分支說明)。"""
    msgs = []
    om = ui.message
    ui.message = lambda s, **k: msgs.append(s)
    try:
        M._explain_build_levers()
        assert len(msgs) == 3
        joined = "".join(msgs)
        assert "專精" in joined and "偏好" in joined and "主修" in joined
    finally:
        ui.message = om


def test_creation_review_previews_derived_sheet():
    """確認前先渲染這套選擇的實際角色卡(build_character 純函式·丟棄 rng·不擋創角)。"""
    gd = get_gamedata()
    seen = {}
    osheet, omenu = ui.character_sheet, ui.menu
    ui.character_sheet = lambda c, g: seen.update(name=c.name, hp=int(c.max_health), race=c.race)
    ui.menu = lambda *a, **k: "confirm"
    try:
        r = M._creation_review(gd, "male", "nord", "warrior", "sellsword", "warrior", None, "阿夫")
        assert r == "confirm"
        assert seen.get("name") == "阿夫" and seen.get("race") == "nord" and seen.get("hp", 0) > 0
    finally:
        ui.character_sheet, ui.menu = osheet, omenu


def test_creation_review_preview_never_blocks_on_error():
    """預覽是純加值:build_character 若丟例外(邊角資料)也不擋創角,仍回選單結果。"""
    gd = get_gamedata()
    osheet, omenu, obuild = ui.character_sheet, ui.menu, M.creation.build_character
    ui.character_sheet = lambda c, g: None
    ui.menu = lambda *a, **k: "confirm"
    M.creation.build_character = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        assert M._creation_review(gd, "male", "nord", "warrior", "sellsword", "warrior", None, "阿夫") == "confirm"
    finally:
        ui.character_sheet, ui.menu, M.creation.build_character = osheet, omenu, obuild


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_onboarding")
