"""九神騎士團(Knights of the Nine,第 6 公會 / 陣營 Phase D ②)的測試:
大事件解鎖入會、雙向對立(神話黎明 + 黑暗兄弟會)、lawful 賞金門檻、聖戰合約階梯、
分支壓軸、聖光眷顧 perk(治療增幅 + 與溢盾精通的複利受 cap 夾住)、存檔向後相容。"""

import json

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import factions, magic, mastery, quests

FACTION = "knights_nine"
UNLOCK = "kvatch_falls"


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="聖徽", sex="male", race="imperial",
                        birthsign="lady", class_id="knight")
    c.skills.update(block=30, heavy_armor=30, restoration=30, blade=30, blunt=30)
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime(), rng=RNG(7))


# --- 大事件解鎖 -------------------------------------------------------
def test_locked_until_kvatch_falls():
    gd, st = _state()
    c = st.player
    assert c.world_events_fired == []
    assert not factions.can_join(c, gd, FACTION)        # 危機未至,聖團尚未重組
    assert factions.join_block_reason(c, gd, FACTION) is not None
    c.world_events_fired.append(UNLOCK)
    assert factions.can_join(c, gd, FACTION)             # 聖團於安維爾重新集結


def test_unlock_gate_is_generic():
    gd, _ = _state()
    assert gd.factions[FACTION]["unlock_event"] == UNLOCK


# --- 對立 / lawful -----------------------------------------------------
def test_rival_members_cannot_join():
    for rival in ("mythic_dawn", "dark_brotherhood"):
        gd, st = _state(world_events_fired=[UNLOCK])
        c = st.player
        factions.join(c, rival)
        assert not factions.can_join(c, gd, FACTION), rival
        assert "勢不兩立" in factions.join_block_reason(c, gd, FACTION)


def test_rivals_bidirectional():
    gd, _ = _state()
    assert set(gd.factions[FACTION]["rivals"]) == {"mythic_dawn", "dark_brotherhood"}
    assert FACTION in gd.factions["mythic_dawn"]["rivals"]
    assert FACTION in gd.factions["dark_brotherhood"]["rivals"]


def test_fighters_guild_member_may_join():
    # 聖騎士可兼戰士公會(刻意不對立 → 不逼走既有 FG 玩家)
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    factions.join(c, "fighters_guild")
    assert factions.can_join(c, gd, FACTION)


def test_lawful_bounty_blocks_join_and_advance():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.bounties["賽羅迪爾"] = 100                          # 通緝在身
    reason = factions.join_block_reason(c, gd, FACTION)
    assert reason is not None and "賞金" in reason         # lawful:true 拒收通緝者
    c.bounties.clear()
    factions.join(c, FACTION)
    c.factions[FACTION] = 1
    c.skills.update(block=80)                             # 達晉升技能門檻
    assert factions.advance_block_reason(c, gd, FACTION) is None
    assert quests.available_quests(c, gd, "guild", FACTION) == ["kn2"]
    c.bounties["賽羅迪爾"] = 100                          # 再度通緝 → 暫停晉升
    assert factions.advance_block_reason(c, gd, FACTION) is not None
    # 關鍵:閘必須「真的」擋住晉升 —— 通緝中不得開放任務(光擋訊息不夠;審查抓到的既有破口)
    assert quests.available_quests(c, gd, "guild", FACTION) == []
    # 反向驗證:還原舊碼(只擋訊息、available 仍回任務)會讓此斷言失敗


# --- 聖戰合約階梯 -----------------------------------------------------
def test_contract_ladder_promotes_on_kill():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.skills.update(block=80)
    factions.join(c, FACTION)
    assert quests.available_quests(c, gd, "guild", FACTION) == ["kn1"]
    quests.accept_quest(c, gd, "kn1")
    obj, _, _ = quests.current_objective(c, gd, "kn1")
    assert obj["creature"] == "corrupt_priest"
    quests.record_kill(c, "corrupt_priest")
    evs = quests.check_completion(c, gd)
    assert any(e["type"] == "completed" and e.get("promoted") for e in evs)
    assert factions.rank_index(c, FACTION) == 1
    assert quests.available_quests(c, gd, "guild", FACTION) == ["kn2"]


def test_rank_skill_gate_blocks_advancement():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.skills.update(block=5, heavy_armor=5, restoration=5, blade=5, blunt=5)
    factions.join(c, FACTION)
    c.factions[FACTION] = 1                               # 晉升需門檻 12
    assert quests.available_quests(c, gd, "guild", FACTION) == []
    assert factions.advance_block_reason(c, gd, FACTION) is not None


def test_finale_branches_resolve_to_different_targets():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.skills.update(block=90)
    factions.join(c, FACTION)
    c.factions[FACTION] = 5
    assert "kn6" in quests.available_quests(c, gd, "guild", FACTION)
    quests.accept_quest(c, gd, "kn6", branch=0)
    assert quests.current_objective(c, gd, "kn6")[0]["creature"] == "defiled_crusader"
    c.quests["kn6"]["branch"] = 1
    assert quests.current_objective(c, gd, "kn6")[0]["creature"] == "dawn_mentor"
    quests.record_kill(c, "dawn_mentor")
    quests.check_completion(c, gd)
    assert factions.rank_index(c, FACTION) == 6          # 九聖騎士團長


def test_contract_targets_exist_in_bestiary():
    gd, _ = _state()
    for qid in gd.factions[FACTION]["rank_quests"]:
        q = gd.quests[qid]
        branch_objs = ([b["objective"] for b in q["branches"]] if "branches" in q
                       else [q["objective"]])
        for obj in branch_objs:
            assert obj["type"] == "kill"
            assert obj["creature"] in gd.bestiary, f"{qid} 目標 {obj['creature']} 不在 bestiary"


def test_no_clean_bonus_on_crusade_quests():
    # 聖戰正面開打 → 合約不帶 clean_bonus(對位刺客合約)
    gd, _ = _state()
    for qid in gd.factions[FACTION]["rank_quests"]:
        q = gd.quests[qid]
        assert "clean_bonus" not in q
        for b in q.get("branches", []):
            assert "clean_bonus" not in b


# --- 聖光眷顧 perk(治療增幅)----------------------------------------
def test_restoration_boon_scales_with_rank():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    assert factions.restoration_boon(c, gd) == 0.0       # 非會員
    factions.join(c, FACTION)
    assert factions.restoration_boon(c, gd) == 0.0       # rank 0
    c.factions[FACTION] = 5
    assert abs(factions.restoration_boon(c, gd) - 0.35) < 1e-9   # rank5 觸 cap
    c.factions[FACTION] = 6
    assert abs(factions.restoration_boon(c, gd) - 0.35) < 1e-9   # cap 夾住


def test_heal_boon_amplifies_heal():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.skills.update(restoration=80)
    c.max_health = 100000
    c.magicka = 99999
    # 非會員
    c.health = 1
    magic.cast(c, gd, "close_wounds", RNG(5))
    amt0 = c.health - 1
    # 滿階會員(boon 0.35)
    factions.join(c, FACTION); c.factions[FACTION] = 5
    c.health = 1; c.magicka = 99999
    magic.cast(c, gd, "close_wounds", RNG(5))
    amt1 = c.health - 1
    assert amt1 > amt0
    assert 1.30 <= amt1 / amt0 <= 1.40                   # ≈ ×1.35


def test_overheal_ward_cap_contains_boon():
    # 治療增幅與「聖光·溢盾」精通複利,但總護盾仍被 0.5×血上限夾住
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.skills.update(restoration=75)                       # 解鎖溢盾精通
    assert mastery.overheal_ward(c, gd) is not None
    c.max_health = 200
    c.magicka = 999999
    factions.join(c, FACTION); c.factions[FACTION] = 5    # 滿階治療增幅
    for _ in range(12):
        c.health = c.max_health                           # 滿血 → 治療全溢出
        magic.cast(c, gd, "close_wounds", RNG(1))
    ward_total = sum(e["magnitude"] for e in c.active_effects
                     if e.get("kind") == "shield" and e.get("source") == "overheal_ward")
    assert ward_total > 0                                 # 確有溢盾
    assert ward_total <= round(c.max_health * 0.5)        # 仍被 cap 夾住


# --- 存檔向後相容(零新欄位)----------------------------------------
def test_membership_survives_save_roundtrip():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 3
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert factions.is_member(loaded, FACTION)
    assert factions.rank_index(loaded, FACTION) == 3


def test_legacy_includes_knights_nine():
    from tesrpg.systems import legacy
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 2
    result = legacy.compute(st, gd)
    names = [name for name, _ in result["factions"]]
    assert "九神騎士團" in names


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_knights OK")
