"""R81 NPC 社交叢集復活回歸:role 身份話題 + 流言線索(混合)+ 好感 gate + 防刷。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import dialogue, quests, landmarks
from tesrpg.ui import console as ui
import tesrpg.main as M


def _mk():
    gd = get_gamedata()
    c = build_character(gd, name="探", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def _state(c):
    return GameState(player=c, rng=RNG(1), game_mode="adventure")


def _set_disp(c, gd, nid, target):
    """把對某 NPC 的好感調到 target(用 npc_disposition 加成層)。"""
    base = gd.npcs[nid]["disposition"]
    c.npc_disposition[nid] = target - base


# --- role 身份話題 --------------------------------------------------------

def test_role_topic_appears_for_roled_npc():
    gd, c = _mk(); st = _state(c)
    nid = "whiterun_smith"                          # blacksmith → forge_talk
    assert gd.npcs[nid].get("role") == "blacksmith"
    _set_disp(c, gd, nid, 50)
    ctx = dialogue.talk_ctx(st, gd, nid)
    att = dialogue.attitude(c, st, gd, nid, ctx)
    tids = [t["id"] for t in dialogue.topics_for(c, st, gd, nid, ctx, att)]
    assert "forge_talk" in tids


def test_blessing_disposition_gate_and_once():
    gd, c = _mk(); st = _state(c)
    # 找一個 priest role NPC
    nid = next(n for n, v in gd.npcs.items() if v.get("role") == "priest")
    ctx = dialogue.talk_ctx(st, gd, nid)
    # 好感不足(<50)→ blessing 不出現
    _set_disp(c, gd, nid, 40)
    att = dialogue.attitude(c, st, gd, nid, ctx)
    assert "blessing" not in [t["id"] for t in dialogue.topics_for(c, st, gd, nid, ctx, att)]
    # 好感足(≥50)→ blessing 出現,施放回血一次後消失(once 防刷)
    _set_disp(c, gd, nid, 60)
    att = dialogue.attitude(c, st, gd, nid, ctx)
    assert "blessing" in [t["id"] for t in dialogue.topics_for(c, st, gd, nid, ctx, att)]
    c.health = max(1, c.max_health - 50)
    td = dialogue._topic_def(gd, nid, "blessing")
    dialogue.resolve_topic(st, gd, nid, {"id": "blessing", **td}, ctx, st.rng)
    assert c.health >= 1                              # heal 套用(夾 max)
    assert "blessing" not in [t["id"] for t in dialogue.topics_for(c, st, gd, nid, ctx, att)]  # once 後消失


# --- 流言線索:quest 路 ---------------------------------------------------

def test_offered_rumor_quest_and_lock():
    gd, c = _mk()
    nid = "marcus"                                   # rumor_quest=rumor_cedernoc, rumor_disposition 45
    _set_disp(c, gd, nid, 50)
    r = dialogue.offered_rumor(c, gd, nid)
    assert r == {"kind": "quest", "id": "rumor_cedernoc"}
    quests.accept_quest(c, gd, r["id"])
    assert dialogue.offered_rumor(c, gd, nid) is None     # 接取後不再提供
    # 完成(clear cedernoc)→ 一次性鎖,仍不提供
    c.cleared_dungeons.append("cedernoc_cave")
    c.quests.pop("rumor_cedernoc", None); c.completed_quests.append("rumor_cedernoc")
    assert dialogue.offered_rumor(c, gd, nid) is None


def test_offered_rumor_quest_skips_already_cleared():
    gd, c = _mk()
    nid = "marcus"
    _set_disp(c, gd, nid, 50)
    c.cleared_dungeons.append("cedernoc_cave")        # 已肅清 → 不給(避免接取即時免費完成)
    assert dialogue.offered_rumor(c, gd, nid) is None


def test_rumor_disposition_gate():
    gd, c = _mk()
    nid = "marcus"
    _set_disp(c, gd, nid, 30)                         # < rumor_disposition 45
    assert dialogue.offered_rumor(c, gd, nid) is None


# --- 流言線索:landmark 路 ------------------------------------------------

def test_offered_rumor_landmark_reveal_and_lock():
    gd, c = _mk(); st = _state(c)
    nid = "olfina"                                    # rumor_landmark=imperial_road, disp 30
    _set_disp(c, gd, nid, 40)
    r = dialogue.offered_rumor(c, gd, nid)
    assert r == {"kind": "landmark", "id": "imperial_road"}
    assert not landmarks.is_discovered(c, "imperial_road")
    res = landmarks.discover(st, gd, "imperial_road")
    assert res is not None and landmarks.is_discovered(c, "imperial_road")
    assert dialogue.offered_rumor(c, gd, nid) is None     # 已揭露 → 不再提供


# --- source:rumor 任務不漏進告示板 ---------------------------------------

def test_rumor_quests_not_on_board():
    gd, c = _mk()
    for prov in ("賽羅迪爾", "天際", "漢默法爾"):
        av = quests.available_quests(c, gd, "board", province=prov, day=999)
        assert not [q for q in av if gd.quests[q].get("source") == "rumor"]


# --- action_talk 追問傳聞煙霧(手動 patch UI,無 pytest 依賴)-------------

def test_action_talk_rumor_smoke():
    gd, c = _mk(); st = _state(c)
    nid = "marcus"
    c.location_id = gd.npcs[nid]["location"]
    _set_disp(c, gd, nid, 60)
    scripted = iter([nid, "rumor"])                   # 選 NPC → 追問傳聞
    saved = {k: getattr(ui, k) for k in ("menu", "npc_panel", "message", "rule",
                                         "landmark_discovery", "board_panel", "show_events")}
    saved_rq = M._report_quests
    try:
        ui.menu = lambda prompt, opts, allow_back=False: next(scripted, None)
        for fn in ("npc_panel", "message", "rule", "landmark_discovery", "board_panel", "show_events"):
            setattr(ui, fn, lambda *a, **k: None)
        M._report_quests = lambda *a, **k: None
        M.action_talk(st, gd)
    finally:
        for k, v in saved.items():
            setattr(ui, k, v)
        M._report_quests = saved_rq
    assert "rumor_cedernoc" in c.quests or "rumor_cedernoc" in c.completed_quests


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_rumor_clues 全通過")
