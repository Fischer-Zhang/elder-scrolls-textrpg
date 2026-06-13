"""條件式對話樹 + NPC 外交(里程碑)回歸測試:
- events.meets 對既有 req 行為等價 + 新無 state 鍵(allegiance/min_fame/min_infamy/is_member/
  member_rank_min/faction_standing_min/is_vampire/is_werewolf)正反斷言。
- attitude 分級(vampire_seen/hostile/cold/friendly/neutral)、greeting_for fallback。
- topics_for 門檻(hostile 收窄、partisan、min_disposition、faction_standing)+ @npc 解析。
- 看破吸血鬼報官、套話付 practice、faction_standing 互斥+夾限+存檔相容。
- 全 102 NPC 走對話引擎不崩;不破既有 persuade/bribe 契約。
"""

import io
import json

from rich.console import Console

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import dialogue, events, crime
from tesrpg.ui import console as ui
import tesrpg.main as M


def _state(allegiance="", speechcraft=0, personality=50, day=1):
    gd = get_gamedata()
    c = build_character(gd, name="話", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    c.allegiance = allegiance
    c.skills["speechcraft"] = speechcraft
    c.attributes["personality"] = personality
    c.fatigue = c.max_fatigue
    st = GameState(player=c, rng=RNG(1), game_mode="adventure")
    st.time.day = day
    return gd, st


# --- events.meets:既有行為等價 + 新鍵 -----------------------------------
def test_meets_backward_compat():
    gd, st = _state()
    c = st.player
    # 既有鍵:無 req → True;gold_min / skill_min / faction / quest_available 照舊
    assert events.meets(c, gd, None) and events.meets(c, gd, {})
    c.gold = 100
    assert events.meets(c, gd, {"gold_min": 50})
    assert not events.meets(c, gd, {"gold_min": 500})
    assert not events.meets(c, gd, {"skill_min": {"speechcraft": 50}})
    assert not events.meets(c, gd, {"faction": "fighters_guild"})
    c.factions["fighters_guild"] = 0
    assert events.meets(c, gd, {"faction": "fighters_guild"})


def test_meets_new_keys():
    gd, st = _state(allegiance="imperial")
    c = st.player
    assert events.meets(c, gd, {"allegiance": "imperial"})
    assert not events.meets(c, gd, {"allegiance": "independent"})
    c.fame, c.infamy = 20, 5
    assert events.meets(c, gd, {"min_fame": 20}) and not events.meets(c, gd, {"min_fame": 21})
    assert events.meets(c, gd, {"min_infamy": 5}) and not events.meets(c, gd, {"min_infamy": 6})
    c.factions["thieves_guild"] = 2
    assert events.meets(c, gd, {"is_member": "thieves_guild"})
    assert not events.meets(c, gd, {"is_member": "mages_guild"})
    assert events.meets(c, gd, {"member_rank_min": {"thieves_guild": 2}})
    assert not events.meets(c, gd, {"member_rank_min": {"thieves_guild": 3}})
    c.faction_standing = {"imperial": 30}
    assert events.meets(c, gd, {"faction_standing_min": {"imperial": 30}})
    assert not events.meets(c, gd, {"faction_standing_min": {"imperial": 31}})
    c.is_vampire = True
    assert events.meets(c, gd, {"is_vampire": True})
    c.is_vampire = False
    assert not events.meets(c, gd, {"is_vampire": True})


# --- attitude 分級 -------------------------------------------------------
def _imperial_npc(gd):
    """挑一個位於 imperial 城的 NPC(stance=imperial)。"""
    import tesrpg.systems.politics as P
    for nid, n in gd.npcs.items():
        if P.base_stance(gd, n["location"]) == "imperial":
            return nid
    raise AssertionError("找不到帝國城 NPC")


def test_attitude_levels():
    gd, st = _state()
    nid = _imperial_npc(gd)
    # 未選邊 → neutral
    assert dialogue.attitude(st.player, st, gd, nid) == "neutral"
    # 同陣營 → friendly
    st.player.allegiance = "imperial"
    assert dialogue.attitude(st.player, st, gd, nid) == "friendly"
    # 敵陣營 → hostile
    st.player.allegiance = "independent"
    assert dialogue.attitude(st.player, st, gd, nid) == "hostile"
    # 好感過低 → cold(非敵對前提)
    st.player.allegiance = ""
    st.player.npc_disposition[nid] = -gd.npcs[nid]["disposition"]   # 壓到 0
    assert dialogue.attitude(st.player, st, gd, nid) == "cold"


def test_attitude_vampire_seen_reports():
    gd, st = _state(day=10)
    nid = _imperial_npc(gd)
    st.player.is_vampire = True
    st.player.vampire_fed_day = 1     # 距今 9 日未進食 → stage 夾頂 ≥ SHUN_STAGE
    assert dialogue.attitude(st.player, st, gd, nid) == "vampire_seen"
    prov = gd.location(gd.npcs[nid]["location"])["province"]
    b0 = crime.bounty(st.player, prov)
    inf0 = st.player.infamy
    dialogue.report_vampire(st.player, gd)   # 注意:report 以玩家當前所在省結算
    # 報官後賞金+惡名上升(以玩家所在省;此處玩家在 start,僅斷言 infamy + 有賞金增量)
    assert st.player.infamy == inf0 + 1
    assert sum(st.player.bounties.values()) >= b0 + dialogue.REPORT_BOUNTY


# --- greeting_for ---------------------------------------------------------
def test_greeting_for_neutral_fallback():
    gd, st = _state()
    nid = _imperial_npc(gd)
    ctx = dialogue.talk_ctx(st, gd, nid)
    # neutral 模板 = "{greeting}" → 等於 NPC 既有問候(向後相容)
    g = dialogue.greeting_for(st.player, st, gd, nid, ctx, "neutral")
    assert g == gd.npcs[nid]["greeting"]
    # hostile 問候插值 {cause}
    st.player.allegiance = "imperial"
    g2 = dialogue.greeting_for(st.player, st, gd, nid, ctx, "hostile")
    assert g2 and "{cause}" not in g2


# --- topics_for 門檻 ------------------------------------------------------
def test_topics_hostile_collapses():
    gd, st = _state(allegiance="independent")
    nid = _imperial_npc(gd)            # 對 independent 玩家為敵
    ctx = dialogue.talk_ctx(st, gd, nid)
    assert ctx["relationship"] == "enemy"
    # 預設模板話題在 hostile 收窄為空(pledge/buy_intel/local 不出現)
    ids = [t["id"] for t in dialogue.topics_for(st.player, st, gd, nid, ctx, "hostile")]
    assert "pledge_support" not in ids and "buy_intel" not in ids and "local_politics" not in ids


def test_topics_partisan_and_disposition_and_standing():
    gd, st = _state(allegiance="imperial", speechcraft=0)
    nid = _imperial_npc(gd)
    st.player.npc_disposition[nid] = 60   # 拉高好感讓 pledge 門檻(50)過
    ctx = dialogue.talk_ctx(st, gd, nid)
    ids = [t["id"] for t in dialogue.topics_for(st.player, st, gd, nid, ctx, "friendly")]
    assert "local_politics" in ids and "pledge_support" in ids
    # buy_intel 需 faction_standing@npc ≥30 → 尚未達標應隱藏
    assert "buy_intel" not in ids
    st.player.faction_standing = {"imperial": 30}
    ids2 = [t["id"] for t in dialogue.topics_for(st.player, st, gd, nid, ctx, "friendly")]
    assert "buy_intel" in ids2


def test_meets_dialogue_at_npc_resolution():
    gd, st = _state(allegiance="imperial")
    nid = _imperial_npc(gd)
    ctx = dialogue.talk_ctx(st, gd, nid)   # faction = imperial
    st.player.faction_standing = {"imperial": 40}
    assert dialogue.meets_dialogue(st.player, st, gd, {"faction_standing_min": {"@npc": 40}}, ctx)
    assert not dialogue.meets_dialogue(st.player, st, gd, {"faction_standing_min": {"@npc": 41}}, ctx)
    # partisan:imperial 城過、neutral 城不過
    assert dialogue.meets_dialogue(st.player, st, gd, {"partisan": True}, ctx)


# --- 外交立場軸(faction_standing)--------------------------------------
def test_faction_standing_rival_tradeoff_and_cap():
    gd, st = _state()
    c = st.player
    dialogue.adjust_standing(c, "imperial", 8, rival_penalty=5)
    assert c.faction_standing["imperial"] == 8
    assert c.faction_standing["independent"] == -5    # 互斥:對立方受損
    # 夾限 [-100, 100]
    dialogue.adjust_standing(c, "imperial", 999, 0)
    assert c.faction_standing["imperial"] == dialogue.STANDING_CAP
    dialogue.adjust_standing(c, "independent", -999, 0)
    assert c.faction_standing["independent"] == -dialogue.STANDING_CAP


def test_faction_standing_save_roundtrip_and_backward_compat():
    gd, st = _state()
    st.player.faction_standing = {"imperial": 25, "independent": -10}
    loaded = Character.from_dict(json.loads(json.dumps(st.player.to_dict())))
    assert loaded.faction_standing == {"imperial": 25, "independent": -10}
    # 舊存檔(無此欄)→ from_dict 自動補 {}
    d = st.player.to_dict()
    del d["faction_standing"]
    old = Character.from_dict(d)
    assert old.faction_standing == {}


# --- 套話付 practice ------------------------------------------------------
def test_pry_pays_practice():
    gd, st = _state(speechcraft=40)
    nid = _imperial_npc(gd)
    ctx = dialogue.talk_ctx(st, gd, nid)
    td = dialogue._topic_def(gd, nid, "pump_for_info")
    f0 = st.player.fatigue
    x0 = st.player.skill_xp.get("speechcraft", 0.0)
    res = dialogue.resolve_topic(st, gd, nid, {"id": "pump_for_info", **td}, ctx, RNG(0))
    assert res["hours"] > 0                       # 付時間
    assert st.player.fatigue < f0                 # 付體力
    assert st.player.skill_xp.get("speechcraft", 0.0) > x0   # learn-by-doing 灌 xp
    assert res["text"]                            # 有回應文字(成功揭密 或 守口如瓶)


# --- 不破既有對話契約 ----------------------------------------------------
def test_persuade_bribe_unchanged():
    gd, st = _state(speechcraft=100, personality=100)
    nid = _imperial_npc(gd)
    # persuade_delta 曲線不變(test_speechcraft 契約)
    assert dialogue.persuade_delta(0) == 6 and dialogue.persuade_delta(100) == 18
    st.player.gold = 50
    r = dialogue.bribe(st.player, gd, nid)
    assert r["ok"] and st.player.gold == 40       # bribe 仍 10 金 +12 好感


# --- 全 102 NPC 走引擎不崩 ----------------------------------------------
def test_all_npcs_dialogue_no_crash():
    gd, st = _state(allegiance="imperial", speechcraft=50)
    for nid in gd.npcs:
        ctx = dialogue.talk_ctx(st, gd, nid)
        att = dialogue.attitude(st.player, st, gd, nid, ctx)
        g = dialogue.greeting_for(st.player, st, gd, nid, ctx, att)
        assert isinstance(g, str) and g
        for t in dialogue.topics_for(st.player, st, gd, nid, ctx, att):
            assert "{" not in dialogue._interp(t.get("text", "") or "", st.player, gd, nid, ctx)


# --- action_talk 端到端(monkeypatch UI)--------------------------------
def test_action_talk_vampire_report_smoke():
    gd, st = _state(day=10)
    ui.console = Console(file=io.StringIO(), width=100)
    nid = _imperial_npc(gd)
    loc = gd.npcs[nid]["location"]
    st.player.location_id = loc
    st.player.is_vampire = True
    st.player.vampire_fed_day = 1
    picks = iter([nid])
    orig_menu = ui.menu
    ui.menu = lambda *a, **k: next(picks, None)
    try:
        prov = gd.location(loc)["province"]
        b0 = crime.bounty(st.player, prov)
        M.action_talk(st, gd)
        assert crime.bounty(st.player, prov) >= b0 + dialogue.REPORT_BOUNTY   # 報官加賞金
    finally:
        ui.menu = orig_menu


# --- 對抗審查回歸:關閉零成本刷分漏洞 ------------------------------------
def test_once_topic_not_repeatable():
    """pledge_support 是一次性表態:套用一次後從話題消失,且重選不再套 effects(防無限刷立場)。"""
    gd, st = _state(allegiance="imperial")
    nid = _imperial_npc(gd)
    st.player.npc_disposition[nid] = 60
    ctx = dialogue.talk_ctx(st, gd, nid)
    td = dialogue._topic_def(gd, nid, "pledge_support")
    assert td.get("once") is True
    # 首次套用 → imperial +8
    dialogue.resolve_topic(st, gd, nid, {"id": "pledge_support", **td}, ctx, RNG(0))
    assert st.player.faction_standing["imperial"] == 8
    # 已表態 → topics_for 不再列出
    ids = [t["id"] for t in dialogue.topics_for(st.player, st, gd, nid, ctx, "friendly")]
    assert "pledge_support" not in ids
    # 即使硬呼叫 resolve,也不再累加(effects 跳過)
    dialogue.resolve_topic(st, gd, nid, {"id": "pledge_support", **td}, ctx, RNG(0))
    assert st.player.faction_standing["imperial"] == 8


def test_intel_and_insider_grant_no_fame():
    """buy_intel / guild_insider 純情報、無 fame effect(防無限刷 fame 灌 legacy 分)。"""
    gd, st = _state(allegiance="imperial")
    nid = _imperial_npc(gd)
    st.player.faction_standing = {"imperial": 40}
    ctx = dialogue.talk_ctx(st, gd, nid)
    td = dialogue._topic_def(gd, nid, "buy_intel")
    f0 = st.player.fame
    for _ in range(5):
        dialogue.resolve_topic(st, gd, nid, {"id": "buy_intel", **td}, ctx, RNG(0))
    assert st.player.fame == f0       # 重選 5 次,fame 不變


def test_hostile_blocks_extra_deep_topics():
    """敵陣營拒談:即便 NPC 有 extra/deep 話題(帶 faction_standing effect),hostile 一律收窄為空。"""
    gd, st = _state(allegiance="imperial")
    nid = "windhelm_galmar"           # 獨立城 → 對 imperial 玩家為 enemy/hostile
    st.player.npc_disposition[nid] = 100
    ctx = dialogue.talk_ctx(st, gd, nid)
    assert dialogue.attitude(st.player, st, gd, nid, ctx) == "hostile"
    assert dialogue.topics_for(st.player, st, gd, nid, ctx, "hostile") == []


def test_pump_does_not_change_standing():
    """套話只給情報(+練口才),不推進外交立場(外交軸走顯式一次性表態)。"""
    gd, st = _state(allegiance="imperial", speechcraft=80, personality=80)
    nid = _imperial_npc(gd)
    ctx = dialogue.talk_ctx(st, gd, nid)
    td = dialogue._topic_def(gd, nid, "pump_for_info")
    dialogue.resolve_topic(st, gd, nid, {"id": "pump_for_info", **td}, ctx, RNG(0))
    assert st.player.faction_standing == {}


def test_say_by_rel_precedence():
    """local_politics 同時有 say_by_rel 與 text → say_by_rel(關係專屬)優先,不被 text 蓋死。"""
    gd, st = _state(allegiance="imperial")
    nid = _imperial_npc(gd)            # imperial 玩家 + imperial 城 → ally
    st.player.npc_disposition[nid] = 60
    ctx = dialogue.talk_ctx(st, gd, nid)
    td = dialogue._topic_def(gd, nid, "local_politics")
    res = dialogue.resolve_topic(st, gd, nid, {"id": "local_politics", **td}, ctx, RNG(0))
    ally_line = dialogue._interp(td["say_by_rel"]["ally"], st.player, gd, nid, ctx)
    assert res["text"] == ally_line and res["text"] != td.get("text")


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_dialogue_tree OK")
