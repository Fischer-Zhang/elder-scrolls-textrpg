"""領主區(宮廷)Phase 1:謁見領主 回歸測試。

涵蓋:接待語氣依聲望分級(fame/infamy)、謁見有領主的城市顯示宮廷面板、
無領主地點安全不崩(不顯示面板)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState


def _setup():
    gd = get_gamedata()
    c = build_character(gd, name="侯", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_reception_tiers():
    import tesrpg.main as M
    gd, c = _setup()
    c.fame = 0; c.infamy = 0
    assert "無名" in M._court_reception(c)              # 無名過客
    c.fame = 50; c.infamy = 0
    assert "威名" in M._court_reception(c)              # 揚名 → 禮遇
    c.fame = 0; c.infamy = 50
    assert "聲名狼藉" in M._court_reception(c)          # 惡名 → 提防
    c.fame = 5; c.infamy = 10                           # 略有名聲、未達門檻 → 例行
    assert "例行" in M._court_reception(c)


def test_action_court_at_city_shows_ruler():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    assert gd.ruler_at(c.location_id)                   # 起始城布魯瑪有領主
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    captured = {}
    saved = (ui.court_panel, ui.message)
    ui.court_panel = lambda ruler, gamedata, reception: captured.update(ruler=ruler, reception=reception)
    ui.message = lambda *a, **k: None
    try:
        M.action_court(state, gd)
    finally:
        ui.court_panel, ui.message = saved
    assert captured.get("ruler") == gd.ruler_at(c.location_id)
    assert captured.get("reception")


def test_action_court_no_ruler_is_safe():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    noruler = next(lid for lid in gd.world["locations"] if not gd.ruler_at(lid))
    c.location_id = noruler
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    shown = []
    saved = (ui.court_panel, ui.message)
    ui.court_panel = lambda *a, **k: shown.append("PANEL")
    ui.message = lambda *a, **k: shown.append("MSG")
    try:
        M.action_court(state, gd)                       # 不應崩
    finally:
        ui.court_panel, ui.message = saved
    assert "PANEL" not in shown                         # 無領主 → 不顯示宮廷面板


def run():
    test_reception_tiers()
    test_action_court_at_city_shows_ruler()
    test_action_court_no_ruler_is_safe()


if __name__ == "__main__":
    run()
    print("test_court 全通過")
