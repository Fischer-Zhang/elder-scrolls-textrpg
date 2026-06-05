"""領主區(宮廷)回歸測試 —— Phase 1 謁見 + Phase 2 領主委託/武士冊封。

涵蓋:接待語氣分級、謁見面板、無領主安全、領主委託依序開放 + 完成累積城邦功勳、
武士冊封(信物/侍從)、武士賞金寬待、存檔向後相容。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import court, crime, quests


def _setup():
    gd = get_gamedata()
    c = build_character(gd, name="侯", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def _patch_court_ui(menu_ret=None):
    """暫換 court 互動會用到的 ui;回傳 (captured, restore)。"""
    from tesrpg.ui import console as ui
    captured = {}
    saved = (ui.court_panel, ui.menu, ui.message)
    ui.court_panel = lambda ruler, gamedata, reception, **kw: captured.update(ruler=ruler, **kw)
    ui.menu = lambda *a, **k: menu_ret
    ui.message = lambda *a, **k: None

    def restore():
        ui.court_panel, ui.menu, ui.message = saved
    return captured, restore


# --- Phase 1 --------------------------------------------------------------
def test_reception_tiers():
    import tesrpg.main as M
    gd, c = _setup()
    c.fame = 0; c.infamy = 0
    assert "無名" in M._court_reception(c)
    c.fame = 50; c.infamy = 0
    assert "威名" in M._court_reception(c)
    c.fame = 0; c.infamy = 50
    assert "聲名狼藉" in M._court_reception(c)
    c.fame = 5; c.infamy = 10
    assert "例行" in M._court_reception(c)


def test_action_court_shows_ruler_panel():
    import tesrpg.main as M
    gd, c = _setup()
    assert gd.ruler_at(c.location_id)                   # 起始城布魯瑪有領主
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    captured, restore = _patch_court_ui(menu_ret=None)  # 看完面板就退下
    try:
        M.action_court(state, gd)
    finally:
        restore()
    assert captured.get("ruler") == gd.ruler_at(c.location_id)
    assert captured.get("standing") == 0 and captured.get("thane") is False


def test_action_court_no_ruler_is_safe():
    import tesrpg.main as M
    gd, c = _setup()
    c.location_id = next(lid for lid in gd.world["locations"] if not gd.ruler_at(lid))
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    captured, restore = _patch_court_ui()
    try:
        M.action_court(state, gd)                       # 不應崩
    finally:
        restore()
    assert "ruler" not in captured                      # 無領主 → 不顯示宮廷面板


# --- Phase 2:領主委託 + 城邦功勳 ----------------------------------------
def test_ruler_quests_open_in_order_and_grant_standing():
    gd, c = _setup()
    loc = "bruma"
    assert court.offered_ruler_quest(c, gd, loc) == "ruler_bruma1"
    # 接取後在進行中 → 不再開放下一個
    quests.accept_quest(c, gd, "ruler_bruma1")
    assert court.offered_ruler_quest(c, gd, loc) is None
    # 完成委託一(殺 6 狼)→ 城邦功勳 +1,開放委託二
    for _ in range(6):
        quests.record_kill(c, "wolf")
    quests.check_completion(c, gd)
    assert court.standing(c, loc) == 1
    assert court.offered_ruler_quest(c, gd, loc) == "ruler_bruma2"
    # 完成委託二(肅清切德納寇)→ 功勳達 3
    quests.accept_quest(c, gd, "ruler_bruma2")
    quests.record_dungeon_clear(c, "cedernoc_cave")
    quests.check_completion(c, gd)
    assert court.standing(c, loc) == 3
    assert court.offered_ruler_quest(c, gd, loc) is None   # 委託線已盡


# --- Phase 2:武士冊封 ----------------------------------------------------
def test_thaneship_grants_gift_and_housecarl():
    gd, c = _setup()
    loc = "bruma"
    assert not court.can_become_thane(c, gd, loc)        # 功勳不足
    c.city_standing[loc] = court.THANE_STANDING
    assert court.can_become_thane(c, gd, loc)
    granted = court.make_thane(c, gd, loc)
    assert court.is_thane(c, loc) and loc in c.thaneships
    assert not court.can_become_thane(c, gd, loc)        # 已是武士,不再開放
    assert granted["gift"] == "elven_sword"
    from tesrpg.systems import inventory
    assert inventory.count_item(c, "elven_sword") == 1   # 信物已入袋
    assert granted["housecarl"] == "shieldmaiden"        # 侍從由呼叫端決定是否入隊
    # 冪等:重複受封不重發信物、不重複加冊(防刷信物)
    again = court.make_thane(c, gd, loc)
    assert again["gift"] is None and again["housecarl"] is None
    assert inventory.count_item(c, "elven_sword") == 1
    assert c.thaneships.count(loc) == 1


def test_thane_bounty_leniency_in_province():
    import tesrpg.main as M
    gd, c = _setup()                                     # 起始於布魯瑪(賽羅迪爾)
    province = gd.world["locations"]["bruma"]["province"]
    assert not court.is_thane_in_province(c, gd, province)
    court.make_thane(c, gd, "bruma")
    assert court.is_thane_in_province(c, gd, province)
    crime.add_bounty(c, province, 50)                    # 小額(≤ THANE_BOUNTY_FORGIVE)
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    _, restore = _patch_court_ui()
    try:
        assert M.guard_confrontation(state, gd) is None  # 武士放行,不開戰
    finally:
        restore()
    assert crime.bounty(c, province) == 0               # 小額賞金一筆勾銷


# --- 存檔向後相容 --------------------------------------------------------
def test_save_roundtrip_and_backward_compat():
    import json
    gd, c = _setup()
    c.city_standing["bruma"] = 2
    c.thaneships.append("bruma")
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.city_standing == {"bruma": 2} and loaded.thaneships == ["bruma"]
    d = c.to_dict()
    del d["city_standing"]; del d["thaneships"]          # 模擬舊存檔
    old = Character.from_dict(d)
    assert old.city_standing == {} and old.thaneships == []


def run():
    test_reception_tiers()
    test_action_court_shows_ruler_panel()
    test_action_court_no_ruler_is_safe()
    test_ruler_quests_open_in_order_and_grant_standing()
    test_thaneship_grants_gift_and_housecarl()
    test_thane_bounty_leniency_in_province()
    test_save_roundtrip_and_backward_compat()


if __name__ == "__main__":
    run()
    print("test_court 全通過")
