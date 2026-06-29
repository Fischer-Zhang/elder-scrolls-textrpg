"""R99 公會諜報層回歸測試:臥底揭發 + 招募內線 + 反間任務 + 大廳反間服務。

涵蓋:① 揭發資格(mole+已揭露+外人→expose;真公會同志→betray;未揭露/一般 NPC 不現)
② 揭發後果(翻臉 hostile → 失去 R98 犯罪服務 + 不可再揭·once)③ 招募內線(secret_comrade
gated → start_quest 反間線索·非會員不現)④ 反間委託(cint_ 可重複/聚光/獎勵限純量·cintlead_
可達)⑤ 臥底維持掩護直到揭露(R97 不變式)⑥ 大廳反間榜 rank-gated + 派發。

🔴 不碰 combat/formulas → sim byte-identical;零新存檔欄(揭發/招募衍生 dialogue_done/factions/quests)。
"""

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import dialogue, factions, quests


def _char(**factions_in):
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = dict(factions_in)
    return gd, c


def _state(c):
    return GameState(player=c, time=GameTime(), rng=RNG(1))


def _topics(c, gd, nid):
    st = _state(c)
    ctx = dialogue.talk_ctx(st, gd, nid)
    att = dialogue.attitude(c, st, gd, nid, ctx)
    return att, [t["id"] for t in dialogue.topics_for(c, st, gd, nid, ctx, att)]


_NEW_MOLES = ["chorrol_fighters_steward", "winterhold_college_adept"]
_NEW_COVERT = {"markarth_silver_fence": "thieves_guild", "sentinel_dock_smuggler": "thieves_guild",
               "anvil_quiet_widow": "dark_brotherhood", "vivec_canton_zealot": "mythic_dawn",
               "gideon_marsh_devotee": "mythic_dawn"}


# ---------------------------------------------------------------- 臥底揭發
def test_expose_hidden_until_revealed():
    """臥底真身未揭露 → 無揭發/出賣選項(連同掩護維持·R97 不變式)。"""
    gd, c = _char()                         # 無會籍 → 不揭露
    for mole in _NEW_MOLES:
        assert not dialogue.secret_guild_revealed(c, gd, mole)
        _, ids = _topics(c, gd, mole)
        assert "expose_mole" not in ids and "betray_mole" not in ids


def test_outsider_can_expose_revealed_mole():
    """外人(非其真公會員)查出臥底真身 → 見 expose_mole(吹哨),不見 betray_mole。"""
    gd = get_gamedata()
    mole = "chorrol_fighters_steward"        # secret=dark_brotherhood
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = {}
    c.npc_disposition[mole] = 100            # disposition≥75 → 揭露
    assert dialogue.secret_guild_revealed(c, gd, mole)
    _, ids = _topics(c, gd, mole)
    assert "expose_mole" in ids and "betray_mole" not in ids


def test_real_guild_comrade_can_betray_not_expose():
    """臥底真公會的同志 → comrade + 見 betray_mole(大義滅親),不見 expose_mole。"""
    gd, c = _char(dark_brotherhood=2)
    mole = "chorrol_fighters_steward"        # secret=dark_brotherhood → 你是其真同志
    att, ids = _topics(c, gd, mole)
    assert att == "comrade"
    assert "betray_mole" in ids and "expose_mole" not in ids


def test_ordinary_npc_never_exposable():
    """一般 NPC(無 secret_guild)永不出現揭發選項(mole_expose 需 guild+secret_guild)。"""
    gd = get_gamedata()
    ordinary = next(n for n, v in gd.npcs.items()
                    if not v.get("secret_guild") and not v.get("guild"))
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.npc_disposition[ordinary] = 100
    _, ids = _topics(c, gd, ordinary)
    assert "expose_mole" not in ids and "betray_mole" not in ids


def test_exposed_mole_turns_hostile_and_loses_services():
    """揭發後臥底翻臉 hostile → topics_for 回 [](連 R98 犯罪服務一併斷絕);once 不可再揭。"""
    gd, c = _char(dark_brotherhood=2)
    mole = "chorrol_fighters_steward"
    # 揭發前:comrade,有 betray_mole + R98 crime_contract 服務
    _, before = _topics(c, gd, mole)
    assert "crime_contract" in before
    # 模擬揭發(once-topic id 落入 dialogue_done,鏡像 resolve_topic)
    c.dialogue_done.setdefault(mole, []).append("betray_mole")
    att, after = _topics(c, gd, mole)
    assert att == "hostile" and after == []      # 翻臉 + 失去所有服務(含 crime_contract)


def test_meets_dialogue_mole_expose_modes():
    """meets_dialogue mole_expose:outsider/comrade 依會籍精確分流。"""
    gd = get_gamedata()
    mole = "winterhold_college_adept"             # secret=thieves_guild
    ctx_npc = mole
    def meets(mode, **fac):
        c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
        c.factions = dict(fac); c.npc_disposition[mole] = 100   # 揭露
        st = _state(c); ctx = dialogue.talk_ctx(st, gd, ctx_npc)
        return dialogue.meets_dialogue(c, st, gd, {"mole_expose": mode}, ctx)
    assert meets("outsider")                       # 非 thieves → 外人可揭
    assert not meets("comrade")                     # 非 thieves → 不能背叛
    assert meets("comrade", thieves_guild=3)        # thieves 同志 → 可背叛
    assert not meets("outsider", thieves_guild=3)   # thieves 同志 → 非外人


# ---------------------------------------------------------------- 招募內線
def test_recruit_informant_gated_to_secret_comrade():
    """招募內線只對『已揭露的真公會同志』現身;非會員/他會員不現。"""
    gd = get_gamedata()
    for nid, guild in _NEW_COVERT.items():
        _, c = _char(**{guild: 3})
        _, ids = _topics(c, gd, nid)
        assert "recruit_informant" in ids, f"{nid}: 同志應見招募"
        _, c2 = _char()                            # 非會員
        _, ids2 = _topics(c2, gd, nid)
        assert "recruit_informant" not in ids2, f"{nid}: 非會員不應見招募"


def test_recruit_starts_counterintel_lead():
    """招募內線(once)→ start_quest 一條反間線索進 char.quests;再招募不重發。"""
    gd, c = _char(thieves_guild=3)
    nid = "markarth_silver_fence"
    st = _state(c)
    ctx = dialogue.talk_ctx(st, gd, nid)
    td = dialogue._topic_def(gd, nid, "recruit_informant")
    dialogue.resolve_topic(st, gd, nid, {"id": "recruit_informant", **td}, ctx, st.rng)
    assert "cintlead_markarth" in c.quests
    # once:再呼叫(模擬已表態)→ effects 清空,不重複派發(quests 數不變)
    c.dialogue_done.setdefault(nid, []).append("recruit_informant")
    _, ids = _topics(c, gd, nid)
    assert "recruit_informant" not in ids          # once 已表態 → 隱藏


# ---------------------------------------------------------------- 反間任務
def test_cint_board_quests_repeatable_scalar_reward_spotlighted():
    gd = get_gamedata()
    spot = set()                                  # 聚光集合(由 world_pulse 設定)
    for p in gd.world_pulse.values():
        spot |= set(p.get("spotlight_quests", []))
    cints = [q for q in gd.quests if q.startswith("cint_")]
    assert cints, "應有 cint_ 反間委託"
    for qid in cints:
        q = gd.quests[qid]
        assert q.get("repeatable") and q.get("source") == "board"
        assert set(q["reward"]) <= {"gold", "fame", "infamy"}, f"{qid} 獎勵超出純量"
        assert q["objective"]["type"] == "kill"
        assert spot == set() or qid in spot, f"{qid} 未被任何脈動聚光"


def test_cintlead_reachable_via_recruit_topic():
    """cintlead_ source:npc 皆由招募話題 start_quest 派發(可達·非孤兒)。"""
    gd = get_gamedata()
    given = set()
    for npc in gd.dialogue.get("npcs", {}).values():
        for td in (npc.get("deep") or {}).values():
            given |= {e["quest"] for e in td.get("effects", []) if e.get("type") == "start_quest"}
    for qid, q in gd.quests.items():
        if qid.startswith("cintlead_"):
            assert q.get("source") == "npc"
            assert qid in given, f"{qid} 無招募話題派發 → 孤兒"


# ---------------------------------------------------------------- 大廳反間榜
def test_counterintel_board_rank_gate_thieves():
    """盜賊大廳:rank<CINT_RANK 不顯示反間榜選項;rank≥CINT_RANK 顯示。"""
    def opts(rank):
        gd, c = _char(thieves_guild=rank)
        c.location_id = "riften"
        st = GameState(player=c, time=GameTime())
        captured = []
        om, og, omsg = main.ui.menu, main.ui.guild_panel, main.ui.message
        main.ui.menu = lambda title, o, **k: captured.extend(x[0] for x in o) or None
        main.ui.guild_panel = lambda *a, **k: None
        main.ui.message = lambda *a, **k: None
        try:
            main.action_guild_hall(st, gd, "thieves_guild")
        finally:
            main.ui.menu, main.ui.guild_panel, main.ui.message = om, og, omsg
        return captured
    assert "counterintel" not in opts(main.CINT_RANK - 1)
    assert "counterintel" in opts(main.CINT_RANK)


def test_counterintel_board_accepts_spotlighted_cint():
    """反間榜接取:patch available_quests 給一條 cint_ → 走 _accept_and_brief 進 char.quests。"""
    gd, c = _char(thieves_guild=3)
    c.location_id = "imperial_city"             # 賽羅迪爾 → cint_cyrodiil_blades
    st = GameState(player=c, time=GameTime())
    seq = iter(["cint_cyrodiil_blades", None])
    oaq = main.quests.available_quests
    main.quests.available_quests = lambda ch, g, src, **k: (["cint_cyrodiil_blades"] if src == "board" else oaq(ch, g, src, **k))
    om, omsg = main.ui.menu, main.ui.message
    main.ui.menu = lambda title, o, **k: next(seq, None)
    main.ui.message = lambda *a, **k: None
    try:
        main._counterintel_board(st, gd)
    finally:
        main.quests.available_quests = oaq
        main.ui.menu, main.ui.message = om, omsg
    assert "cint_cyrodiil_blades" in c.quests


def test_cint_excluded_from_public_board():
    """🔴 反間委託(cint_)絕不上正規告示板(只走犯罪公會大廳 rank-gated)→ 防繞過階級閘。"""
    gd, c = _char()
    c.location_id = "imperial_city"
    st = GameState(player=c, time=GameTime())
    oaq = main.quests.available_quests
    main.quests.available_quests = lambda ch, g, src, *a, **k: (
        ["cint_cyrodiil_blades", "comm_cyrodiil_bandit"] if src == "board" else oaq(ch, g, src, *a, **k))
    captured = []
    om, omsg, ob = main.ui.menu, main.ui.message, main.ui.board_panel
    main.ui.menu = lambda title, o, **k: captured.extend(x[0] for x in o) or None
    main.ui.message = lambda *a, **k: None
    main.ui.board_panel = lambda *a, **k: None
    try:
        main.action_board(st, gd)
    finally:
        main.quests.available_quests = oaq
        main.ui.menu, main.ui.message, main.ui.board_panel = om, omsg, ob
    assert "cint_cyrodiil_blades" not in captured, "反間委託洩漏到公開告示板(繞過大廳階級閘)"
    assert "comm_cyrodiil_bandit" in captured, "一般委託應正常上板(健全性)"


def test_counterintel_excluded_from_knights_hall():
    """九神騎士團(非犯罪公會·與神話黎明共用 _contract_hall)不得出現反間委託榜。"""
    gd, c = _char(knights_nine=5)
    c.location_id = "anvil"
    st = GameState(player=c, time=GameTime())
    captured = []
    om, og, omsg = main.ui.menu, main.ui.guild_panel, main.ui.message
    main.ui.menu = lambda title, o, **k: captured.extend(x[0] for x in o) or None
    main.ui.guild_panel = lambda *a, **k: None
    main.ui.message = lambda *a, **k: None
    try:
        main.action_knights_hall(st, gd)
    finally:
        main.ui.menu, main.ui.guild_panel, main.ui.message = om, og, omsg
    assert "counterintel" not in captured, "九神騎士團不應有反間委託榜(非犯罪公會)"


def test_recruit_requires_membership_not_just_reveal():
    """招募內線需『真公會會員』,非僅『秘密已揭露』——高好感揭露的外人不能招募。"""
    gd = get_gamedata()
    nid = "markarth_silver_fence"            # secret=thieves_guild
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = {}                          # 非盜賊
    c.npc_disposition[nid] = 100             # disposition≥75 → 秘密對你揭露
    assert dialogue.secret_guild_revealed(c, gd, nid)   # 已揭露
    _, ids = _topics(c, gd, nid)
    assert "recruit_informant" not in ids    # 但非會員 → 不能招募


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_espionage")
