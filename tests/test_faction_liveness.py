"""公會宿敵生態 Phase 1(R96)回歸測試。

涵蓋:衍生敵意(零存檔欄·宿敵公會視你為仇敵)、對稱、無宿敵公會恆不敵視、
most_hostile_guild 取最高 tier,以及對話態度(宿敵公會 NPC 對你冷待/敵視)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import dialogue, factions


def _char(**factions_in):
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = dict(factions_in)
    return gd, c


# --- 衍生敵意:身屬宿敵公會 → 對方視你為仇敵 -------------------------------
def test_hostility_derived_from_rival_membership():
    gd, c = _char(fighters_guild=3)
    # 戰士公會的宿敵(thieves/db/mythic_dawn)都視高階戰士為仇敵
    for rival in ("thieves_guild", "dark_brotherhood", "mythic_dawn"):
        assert factions.faction_hostility(c, gd, rival) >= 1, rival
        assert factions.is_hostile(c, gd, rival)
    # 非宿敵公會(法師)不敵視
    assert factions.faction_hostility(c, gd, "mages_guild") == 0
    # 對自己所屬公會無敵意
    assert factions.faction_hostility(c, gd, "fighters_guild") == 0


def test_hostility_symmetric():
    # 盜賊高階 → 戰士公會敵視(反方向)
    gd, c = _char(thieves_guild=4)
    assert factions.is_hostile(c, gd, "fighters_guild")
    assert factions.faction_hostility(c, gd, "fighters_guild") == 5   # rank_index 4 +1


def test_hostility_tier_scales_with_rank():
    gd = get_gamedata()
    lo = build_character(gd, name="低", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    hi = build_character(gd, name="高", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    lo.factions = {"fighters_guild": 0}
    hi.factions = {"fighters_guild": 6}
    assert factions.faction_hostility(hi, gd, "thieves_guild") > factions.faction_hostility(lo, gd, "thieves_guild")
    assert factions.faction_hostility(lo, gd, "thieves_guild") == 1   # rank0 會員 → tier1


def test_no_rival_guilds_never_hostile():
    # mages/companions/coven/werewolf 無 rivals → 對任何人皆不敵視
    gd, c = _char(fighters_guild=6, thieves_guild=0)   # 多公會(忽略互斥,純測敵意)
    for g in ("mages_guild", "companions", "coven_vampire", "werewolf_pack"):
        assert not gd.factions[g].get("rivals"), g
        assert factions.faction_hostility(c, gd, g) == 0, g


def test_zero_save_field_pure_derivation():
    # 全新角色(零公會)→ 對所有公會敵意 0,且不需任何額外 char 屬性
    gd, c = _char()
    assert all(factions.faction_hostility(c, gd, g) == 0 for g in gd.factions)
    assert not hasattr(c, "guild_hostility")   # 純衍生·無新存檔欄


def test_most_hostile_guild_picks_max_tier():
    gd, c = _char(fighters_guild=5)
    fid, tier = factions.most_hostile_guild(c, gd)
    assert fid in ("thieves_guild", "dark_brotherhood", "mythic_dawn")
    assert tier == 6
    # 零公會 → 無宿敵
    _, c0 = _char()
    assert factions.most_hostile_guild(c0, gd) == (None, 0)


# --- 對話態度:宿敵公會 NPC 對你冷待/敵視 ---------------------------------
def test_rival_guild_npc_attitude_hostile():
    gd = get_gamedata()
    c = build_character(gd, name="賊", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = {"thieves_guild": 4}                      # 高階盜賊 → 戰士公會 NPC 敵視
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    # bruma_legion_veteran_brand 標 fighters_guild
    att = dialogue.attitude(c, st, gd, "bruma_legion_veteran_brand")
    assert att == "hostile", att


def test_non_member_npc_attitude_unaffected():
    # 非盜賊/戰士的中立角色 → 該 NPC 不因公會敵意變色(走原態度邏輯)
    gd = get_gamedata()
    c = build_character(gd, name="路", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = {}
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    att = dialogue.attitude(c, st, gd, "bruma_legion_veteran_brand")
    assert att in ("neutral", "friendly", "cold"), att        # 不會 hostile(無敵意)


def test_guild_npcs_carry_only_guild_content():
    """🔴 R96 通用不變式(可擴展至更多 NPC):被標 guild 的 NPC 只攜帶「公會相關內容」——
    敵對 NPC 不發任務給你是正確的(宿敵敵意 → hostile → 不給任務),但若 guild NPC 攜帶**一般**
    任務/流言,身屬其宿敵的玩家會被永久鎖死那段一般內容。故規則:guild NPC 不攜帶一般 rumor;
    其 npc-source quest(若有)的 faction 須等於該 NPC 的 guild(即只給該公會的任務)。
    一般任務歸一般 NPC(如 marcus 的 chain_kvatch);加新 guild NPC 時此 guard 自動把關。"""
    gd = get_gamedata()
    bad = []
    for nid, n in gd.npcs.items():
        g = n.get("guild")
        if not g:
            continue
        if n.get("rumor_quest") or n.get("rumor_landmark"):
            bad.append((nid, "一般 rumor"))
        qid = n.get("quest")
        if qid and gd.quests.get(qid, {}).get("faction") != g:
            bad.append((nid, f"非該公會任務 {qid}"))
    assert not bad, f"guild NPC 攜帶非公會內容(會被宿敵敵意鎖死一般內容):{bad}"


def test_guild_enforcer_ambush_spawns_tier_scaled_foes():
    """R96 伏擊管線:tier→打手種類/數量(tier>=4→guild_avenger·count=min(3,1+tier//3))。"""
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _char(thieves_guild=4)
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    cap = {}
    saved_ob, saved_msg = M.offer_battle, ui.message
    M.offer_battle = lambda state, g, foes, **k: cap.update(foes=foes)
    ui.message = lambda *a, **k: None
    try:
        M._guild_enforcer_ambush(st, gd, "fighters_guild", 5)
    finally:
        M.offer_battle, ui.message = saved_ob, saved_msg
    foes = cap["foes"]
    assert len(foes) == 2                                            # tier5 → min(3,1+5//3)=2
    assert all(f.template_id == "guild_avenger" for f in foes)      # tier>=4 → avenger


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_faction_liveness")
