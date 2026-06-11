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
    # 併入 no_ruler:換到無領主地點 → 不應崩、不顯宮廷面板(用全新 captured2,避免沿用已填 ruler 的 captured)
    captured2, restore2 = _patch_court_ui()
    c.location_id = next(lid for lid in gd.world["locations"] if not gd.ruler_at(lid))
    try:
        M.action_court(state, gd)                       # 不應崩
    finally:
        restore2()
    assert "ruler" not in captured2                     # 無領主 → 不顯示宮廷面板


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


# --- 階段四:武士所在城翻敵 → 特權暫停(可逆)----------------------------
def test_thane_privilege_suspended_when_city_flips():
    from tesrpg.systems import politics
    gd, c = _setup()
    province = gd.world["locations"]["bruma"]["province"]
    court.make_thane(c, gd, "bruma")
    politics.pledge(c, "imperial")                          # 布魯瑪種子立場=imperial → 同盟
    assert court.is_thane_in_province(c, gd, province)      # 同盟城 → 武士特權有效
    c.city_faction["bruma"] = "independent"                 # 該城翻給敵方
    assert not court.is_thane_in_province(c, gd, province)  # 特權暫停
    # 併入 reflips:城再翻回我方 → 特權自動恢復(可逆)、thaneships 全程未變(非銷毀)
    c.city_faction["bruma"] = "imperial"                    # 城再翻回我方
    assert court.is_thane_in_province(c, gd, province)      # 特權自動恢復(可逆)
    assert "bruma" in c.thaneships                          # thaneships 全程未變(非銷毀)


def test_thane_privilege_intact_before_pledge():
    gd, c = _setup()
    province = gd.world["locations"]["bruma"]["province"]
    court.make_thane(c, gd, "bruma")
    assert c.allegiance == ""
    assert court.is_thane_in_province(c, gd, province)      # 未選邊 → 特權照常(allegiance guard)


def test_thane_suspended_blocks_guard_forgive():
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    from tesrpg.systems import politics
    gd, c = _setup()
    province = gd.world["locations"]["bruma"]["province"]
    court.make_thane(c, gd, "bruma"); politics.pledge(c, "imperial")
    c.city_faction["bruma"] = "independent"                 # 翻敵 → 特權暫停
    crime.add_bounty(c, province, 50)
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    msgs = []; saved = (ui.menu, ui.message)
    ui.message = lambda m="", **k: msgs.append(m)
    ui.menu = lambda *a, **k: "jail"                        # 入獄服刑了結(非特權勾銷)
    try:
        M.guard_confrontation(state, gd)
    finally:
        ui.menu, ui.message = saved
    assert not any("武士閣下" in m for m in msgs)            # 未走武士寬待
    assert any("束手就擒" in m for m in msgs)                # 走一般攔查
    assert crime.bounty(c, province) == 0                   # 改由服刑了結


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


def test_every_ruler_settlement_is_thaneable():
    """程序化為底:每座有領主的城/鎮都能受封武士 —— 委託齊備(功勳可達門檻)、信物/侍從合法。"""
    gd, _ = _setup()
    for loc_id, ruler in gd.rulers.items():
        line = ruler.get("quests", [])
        assert line and all(q in gd.quests for q in line), f"{loc_id} 無有效委託"
        total = sum(gd.quests[q]["reward"].get("standing", 0) for q in line)
        assert total >= court.THANE_STANDING, f"{loc_id} 委託功勳 {total} < {court.THANE_STANDING}"
        assert gd.item_or_none(ruler.get("thane_gift")), f"{loc_id} 信物非法"
        assert ruler.get("housecarl") in gd.companions, f"{loc_id} 侍從非法"
        for q in line:                                   # 委託目標(怪/地城)皆須存在
            o = gd.quests[q]["objective"]
            if o.get("creature"):
                assert o["creature"] in gd.bestiary, f"{q} 怪不存在"
            if o.get("dungeon"):
                assert o["dungeon"] in gd.dungeons, f"{q} 地城不存在"


def test_procedural_commissions_earn_thaneship():
    """在一座『程序化委託』的城走完委託線 → 功勳達標 → 可受封(冊封得信物+侍從)。"""
    gd, c = _setup()
    loc = "anvil"                                        # 賽羅迪爾,非手寫 → 程序化委託
    line = court.ruler_quest_line(gd, loc)
    assert line and all(q.startswith("ruler_auto_") for q in line)
    for qid in line:
        quests.accept_quest(c, gd, qid)
        o = gd.quests[qid]["objective"]
        if o["type"] == "kill":
            for _ in range(o["count"]):
                quests.record_kill(c, o["creature"])
        elif o["type"] == "clear_dungeon":
            quests.record_dungeon_clear(c, o["dungeon"])
        quests.check_completion(c, gd)
    assert court.standing(c, loc) >= court.THANE_STANDING
    assert court.can_become_thane(c, gd, loc)
    granted = court.make_thane(c, gd, loc)
    assert court.is_thane(c, loc) and granted["gift"] and granted["housecarl"]


def run():
    test_reception_tiers()
    test_every_ruler_settlement_is_thaneable()
    test_procedural_commissions_earn_thaneship()
    test_action_court_shows_ruler_panel()
    test_ruler_quests_open_in_order_and_grant_standing()
    test_thaneship_grants_gift_and_housecarl()
    test_thane_bounty_leniency_in_province()
    test_thane_privilege_suspended_when_city_flips()
    test_thane_privilege_intact_before_pledge()
    test_thane_suspended_blocks_guard_forgive()
    test_save_roundtrip_and_backward_compat()


if __name__ == "__main__":
    run()
    print("test_court 全通過")
