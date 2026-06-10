"""戰友團(The Companions,第 7 公會 + 狼人血脈歸宿)的測試:
一般戰士公會流(非合約大廳)入會 / 技能門檻階梯 / 內圈引渡多階任務 / 終局二選一分支、
獸血儀式由戰士公會「移籍」到戰友團內圈(rank≥4)、盾袍之誼 merc_discount perk、
內圈召集免費盾袍兄弟(allies-only)、銀手/格倫魔女為野生可遇敵、存檔向後相容、legacy 收錄。"""

import json

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import factions, lycanthropy, quests

FACTION = "companions"


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="新血", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    c.skills.update(blade=80, blunt=80, hand_to_hand=80, marksman=80, heavy_armor=80)
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime(), rng=RNG(7))


# --- 一般戰士公會流:無大事件解鎖、技能即可入會 -----------------------
def test_no_unlock_event_join_by_skill():
    gd, st = _state()
    c = st.player
    assert "unlock_event" not in gd.factions[FACTION]
    assert factions.can_join(c, gd, FACTION)              # 技能達門檻即可走入入會
    factions.join(c, FACTION)
    assert factions.is_member(c, FACTION)
    assert factions.rank_index(c, FACTION) == 0
    assert factions.rank_name(c, gd, FACTION) == gd.factions[FACTION]["ranks"][0]


def test_low_skill_blocks_join():
    gd, st = _state()
    c = st.player
    c.skills.update(blade=5, blunt=5, hand_to_hand=5, marksman=5, heavy_armor=5)
    assert not factions.can_join(c, gd, FACTION)
    assert factions.join_block_reason(c, gd, FACTION) is not None


def test_not_lawful_wanted_may_still_join():
    # 戰友團 lawful:false —— 收容浪人,通緝者照樣能入會(與戰士公會/九神對位)
    gd, st = _state()
    c = st.player
    c.bounties["天際"] = 500
    assert gd.factions[FACTION]["lawful"] is False
    assert factions.can_join(c, gd, FACTION)
    factions.join(c, FACTION)
    c.factions[FACTION] = 1
    # 通緝中仍可晉升(非 lawful → advance 不被賞金擋)
    assert factions.advance_block_reason(c, gd, FACTION) is None


def test_no_rivals_warriors_may_cross_join():
    # rivals 為空 → 戰士系玩家可兼修戰士公會 + 戰友團
    gd, st = _state()
    c = st.player
    assert gd.factions[FACTION]["rivals"] == []
    factions.join(c, "fighters_guild")
    assert factions.can_join(c, gd, FACTION)
    factions.join(c, FACTION)
    assert factions.can_join(c, gd, "fighters_guild") or factions.is_member(c, "fighters_guild")


# --- 技能門檻階梯 + 晉升 ---------------------------------------------
def test_rank_ladder_promotes_on_completion():
    gd, st = _state()
    c = st.player
    factions.join(c, FACTION)
    assert quests.available_quests(c, gd, "guild", FACTION) == ["companions1"]
    quests.accept_quest(c, gd, "companions1")
    obj, _, _ = quests.current_objective(c, gd, "companions1")
    assert obj["type"] == "kill" and obj["creature"] == "wolf"
    quests.record_kill(c, "wolf"); quests.record_kill(c, "wolf")
    evs = quests.check_completion(c, gd)
    assert any(e["type"] == "completed" and e.get("promoted") for e in evs)
    assert factions.rank_index(c, FACTION) == 1
    assert quests.available_quests(c, gd, "guild", FACTION) == ["companions2"]


def test_rank_skill_gate_blocks_advancement():
    gd, st = _state()
    c = st.player
    c.skills.update(blade=10, blunt=10, hand_to_hand=10, marksman=10, heavy_armor=10)
    factions.join(c, FACTION)
    c.factions[FACTION] = 2                                # 晉升需 rank_skill_req[2]=26
    assert quests.available_quests(c, gd, "guild", FACTION) == []
    assert "26" in (factions.advance_block_reason(c, gd, FACTION) or "")


def test_induction_quest_is_multistage_kill_then_reach():
    gd, st = _state()
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 3                                # 內圈引渡 companions4
    assert quests.available_quests(c, gd, "guild", FACTION) == ["companions4"]
    quests.accept_quest(c, gd, "companions4")
    obj, _, _ = quests.current_objective(c, gd, "companions4")
    assert obj["type"] == "kill" and obj["creature"] == "silver_hand"
    for _ in range(3):
        quests.record_kill(c, "silver_hand")
    quests.check_completion(c, gd)                         # 推進到 reach 階段
    obj2, _, _ = quests.current_objective(c, gd, "companions4")
    assert obj2["type"] == "reach" and obj2["location"] == "whiterun"
    c.location_id = "whiterun"
    quests.check_completion(c, gd)
    assert factions.rank_index(c, FACTION) == 4            # 內圈戰友


def test_finale_branches_resolve_to_different_targets():
    gd, st = _state()
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 5
    assert "companions6" in quests.available_quests(c, gd, "guild", FACTION)
    quests.accept_quest(c, gd, "companions6", branch=0)
    assert quests.current_objective(c, gd, "companions6")[0]["creature"] == "werewolf_alpha"
    c.quests["companions6"]["branch"] = 1
    assert quests.current_objective(c, gd, "companions6")[0]["creature"] == "glenmoril_witch"
    quests.record_kill(c, "glenmoril_witch")
    quests.check_completion(c, gd)
    assert factions.rank_index(c, FACTION) == 6            # 先驅


def test_quest_targets_and_dungeons_exist():
    gd, _ = _state()
    for qid in gd.factions[FACTION]["rank_quests"]:
        q = gd.quests[qid]
        steps = q.get("branches") or q.get("stages") or [q]
        for s in steps:
            obj = s["objective"]
            if obj["type"] == "kill":
                assert obj["creature"] in gd.bestiary, f"{qid} {obj['creature']}"
            elif obj["type"] == "clear_dungeon":
                assert obj["dungeon"] in gd.dungeons, f"{qid} {obj['dungeon']}"
            elif obj["type"] == "reach":
                assert gd.location(obj["location"]) is not None, f"{qid} {obj['location']}"


# --- 銀手 / 格倫魔女 = 野生可遇敵(戰士公會 kill 目標須 weight>0,非合約直生) ---
def test_quest_enemies_are_wild_spawnable():
    gd, _ = _state()
    for cid in ("silver_hand", "glenmoril_witch"):
        e = gd.bestiary[cid]
        assert e["weight"] > 0, f"{cid} 必須可野外刷出(被動 kill_counts 才追蹤得到)"
        assert e["biomes"] == ["snow"], f"{cid} 應掛天際雪原生態,不污染他省"


# --- 獸血儀式由戰士公會「移籍」到戰友團內圈 ---------------------------
def test_ritual_rehomed_to_companions_circle():
    gd, st = _state()
    c = st.player
    # 戰士公會再高階也不再給狼血(已移籍)
    factions.join(c, "fighters_guild"); c.factions["fighters_guild"] = 6
    assert not lycanthropy.can_offer_ritual(c)
    # 戰友團未達內圈(rank<4)→ 不獻
    factions.join(c, FACTION); c.factions[FACTION] = 3
    assert not lycanthropy.can_offer_ritual(c)
    # 內圈戰友(rank≥4)→ 獻上獸血儀式
    c.factions[FACTION] = 4
    assert lycanthropy.can_offer_ritual(c)
    assert main.COMPANIONS_CIRCLE_RANK == lycanthropy.RITUAL_RANK_INDEX == 4


def test_ritual_excludes_vampire_and_existing_werewolf():
    gd, st = _state()
    c = st.player
    factions.join(c, FACTION); c.factions[FACTION] = 5
    c.is_werewolf = True
    assert not lycanthropy.can_offer_ritual(c)             # 已是狼人 → 不重複
    c.is_werewolf = False
    c.is_vampire = True
    assert not lycanthropy.can_offer_ritual(c)             # 吸血鬼互斥 → 不獻


# --- 盾袍之誼 perk(招募折扣)----------------------------------------
def test_merc_discount_scales_with_rank():
    gd, st = _state()
    c = st.player
    assert factions.merc_discount(c, gd) == 0.0            # 非會員
    factions.join(c, FACTION)
    assert factions.merc_discount(c, gd) == 0.0            # rank 0
    c.factions[FACTION] = 5
    assert abs(factions.merc_discount(c, gd) - 0.40) < 1e-9
    c.factions[FACTION] = 6
    assert abs(factions.merc_discount(c, gd) - 0.48) < 1e-9   # 仍 < cap 0.5


# --- 內圈召集盾袍兄弟(免費 · allies-only)---------------------------
def test_shield_siblings_are_circle_only_allies():
    gd, _ = _state()
    for cid in ("farkas", "aela"):
        assert gd.companions[cid].get("circle") is True
        assert gd.companions[cid]["cost"] == 0


def test_circle_recruit_helper_lists_and_adds():
    gd, st = _state()
    c = st.player
    avail = main._available_shield_siblings(c, gd)
    assert set(avail) == {"farkas", "aela"}
    c.companions.append("farkas")
    assert main._available_shield_siblings(c, gd) == ["aela"]   # 已入隊者不重列


def test_shield_siblings_excluded_from_inn_pool():
    # 旅店傭兵池(_hire_mercenary 的 avail 過濾)不含 circle 盾袍兄弟
    gd, st = _state()
    c = st.player
    inn_pool = [cid for cid in gd.companions
                if cid not in c.companions
                and not gd.companions[cid].get("troop")
                and not gd.companions[cid].get("warlord")
                and not gd.companions[cid].get("circle")]
    assert "farkas" not in inn_pool and "aela" not in inn_pool
    assert "sellsword" in inn_pool                          # 一般傭兵仍在池中


# --- 存檔 / legacy --------------------------------------------------
def test_membership_survives_save_roundtrip():
    gd, st = _state()
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 4
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert factions.is_member(loaded, FACTION)
    assert factions.rank_index(loaded, FACTION) == 4


def test_legacy_includes_companions():
    from tesrpg.systems import legacy
    gd, st = _state()
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 2
    result = legacy.compute(st, gd)
    names = [name for name, _ in result["factions"]]
    assert "戰友團" in names


def test_shield_siblings_excluded_from_warband_officer_pool():
    from tesrpg.systems import warband
    gd, st = _state()
    officers = warband.recruitable_officers(st.player, gd)
    assert "farkas" not in officers and "aela" not in officers   # 非 warlord → 不在營地將領池
    assert "veteran" in officers                                  # warlord 將領仍唯營地可招


def _dismiss_via_ui(gd, st, cid):
    """以 patched ui 走真實 _dismiss_mercenary(避免互動 prompt),用後還原。"""
    u = main.ui
    saved = (u.menu, u.message)
    u.menu = lambda *a, **k: cid
    u.message = lambda *a, **k: None
    try:
        main._dismiss_mercenary(st, gd)
    finally:
        u.menu, u.message = saved


def test_circle_sibling_dismiss_retains_persistent_hp():
    # 對抗審查確認的 farm 漏洞:免費盾袍兄弟「解散→再召集」不得零成本回滿血/解負傷。
    from tesrpg.systems import party
    gd, st = _state()
    c = st.player
    c.companions.append("farkas")
    c.companion_hp["farkas"] = 0                      # 負傷倒下
    assert party.is_downed(c, gd, "farkas")
    _dismiss_via_ui(gd, st, "farkas")
    assert "farkas" not in c.companions
    assert c.companion_hp.get("farkas") == 0          # 持久 HP 保留(circle 不 forget)
    c.companions.append("farkas")                     # 模擬再召集
    assert party.is_downed(c, gd, "farkas")           # 仍負傷 → 沒被免費治療


def test_paid_mercenary_dismiss_still_forgets():
    # 對位:雇傭兵照舊 forget(再雇須付酬金=既有金幣閘,不受本次修正影響)
    from tesrpg.systems import party
    gd, st = _state()
    c = st.player
    c.companions.append("sellsword")
    c.companion_hp["sellsword"] = 5
    _dismiss_via_ui(gd, st, "sellsword")
    assert "sellsword" not in c.companions
    assert "sellsword" not in c.companion_hp          # 持久 HP 已清(forget)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_companions OK")
