"""九神騎士團(Knights of the Nine,第 6 公會 / 陣營 Phase D ②)的測試:
雙向對立資料、lawful 賞金門檻『真擋任務』回歸 pin、聖戰合約階梯、分支壓軸、
聖光眷顧 perk(restoration_boon 縮放/夾 cap + 治療增幅 + 與溢盾精通的複利受 cap 夾住)。
(解鎖/rank-gate/bestiary/存檔/legacy 等三會同型模板已 C 砍或 D 併出檔,見內文標注。)"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
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
# test_locked_until_kvatch_falls / test_unlock_gate_is_generic 已 D 併入
#   test_mythicdawn.test_locked_until_kvatch_falls(參數化迭代 ['mythic_dawn','knights_nine']:
#   驗 can_join 事件前 False/事件後 True + unlock_event=='kvatch_falls' 資料 pin)。


# --- 對立 / lawful -----------------------------------------------------
# test_rival_members_cannot_join 已 C 砍(can_join 對 rival 擋路機制 canonical 於
#   test_guild_depth.test_rival_guilds_mutually_exclusive;rivals 雙向資料由
#   test_rivals_bidirectional 守)。
def test_rivals_bidirectional():
    gd, _ = _state()
    assert set(gd.factions[FACTION]["rivals"]) == {"mythic_dawn", "dark_brotherhood"}
    assert FACTION in gd.factions["mythic_dawn"]["rivals"]
    assert FACTION in gd.factions["dark_brotherhood"]["rivals"]


# test_fighters_guild_member_may_join 已 C 砍(純資料同一性:rivals 不含 fighters_guild
#   的設計決定;機制零新路徑,雙向不變式由 test_rivals_bidirectional 守)。


def test_lawful_bounty_blocks_join_and_advance():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    # 大事件解鎖閘資料 pin + 事件前鎖死(併自 test_locked_until_kvatch_falls;
    # mythicdawn 端只測 mythic_dawn、未參數化涵蓋 knights_nine)
    assert gd.factions[FACTION]["unlock_event"] == UNLOCK
    _, locked = _state()                                  # kvatch_falls 未發生
    assert not factions.can_join(locked.player, gd, FACTION)
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


# test_rank_skill_gate_blocks_advancement 已 C 砍(第三份逐字複本;canonical 於
#   test_guild_depth.test_advancement_blocked_by_skill_then_unblocked)。


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


# test_contract_targets_exist_in_bestiary 已 D 併入 test_detailing.test_quest_objective_targets_valid
#   (該測迭代全 gd.quests〔含 branches/stages〕驗 kill→bestiary,是嚴格超集;
#   kn 附帶的『rank_quests 全為 kill 型』設計斷言折進 detailing 尾端的全域 rank_quests 型別迴圈)。


def test_no_clean_bonus_on_crusade_quests():
    # 聖戰正面開打 → 合約不帶 clean_bonus(對位刺客合約)
    gd, _ = _state()
    for qid in gd.factions[FACTION]["rank_quests"]:
        q = gd.quests[qid]
        assert "clean_bonus" not in q
        for b in q.get("branches", []):
            assert "clean_bonus" not in b
        # 聖戰合約全為 kill 型(併自 test_contract_targets_exist_in_bestiary;
        # 目標存在性由 test_detailing 覆蓋,此處 pin「kn 合約皆 kill」設計意圖)
        objs = ([b["objective"] for b in q["branches"]] if "branches" in q else [q["objective"]])
        for obj in objs:
            assert obj["type"] == "kill"


# --- 聖光眷顧 perk(治療增幅)----------------------------------------
def test_heal_boon_amplifies_heal():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    # 併入 test_restoration_boon_scales_with_rank:restoration_boon 泛型縮放/夾 cap 資料 pin
    #   (factions._best_perk 薄包裝;非會員=0 / rank0=0 / rank5=0.35觸cap / rank6=0.35夾住)
    assert factions.restoration_boon(c, gd) == 0.0       # 非會員
    factions.join(c, FACTION)
    assert factions.restoration_boon(c, gd) == 0.0       # rank 0
    c.factions[FACTION] = 5
    assert abs(factions.restoration_boon(c, gd) - 0.35) < 1e-9   # rank5 觸 cap
    c.factions[FACTION] = 6
    assert abs(factions.restoration_boon(c, gd) - 0.35) < 1e-9   # cap 夾住
    # ── 行為整合(原 test_heal_boon_amplifies_heal):治療量隨 boon 放大 ─────────
    c.factions.clear()                                   # 還原非會員,重跑行為對照
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
    c.skills.update(restoration=75)                       # 達門檻
    mastery.choose(c, gd, "restoration_75", "overheal_ward")   # v2:二選一銘刻溢盾精通
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
# test_membership_survives_save_roundtrip 已 C 砍(公會會籍=Character.factions 老欄位,
#   零新存檔欄;同型往返 canonical 於 test_brotherhood.test_save_load_roundtrip_and_backward_compat
#   + test_state.test_save_load_roundtrip)。
# test_legacy_includes_knights_nine 已 C 砍(legacy.compute 自動迭代 char.factions → faction
#   name 入榜屬泛型資料同一性、覆蓋價值近零,不另 pin;防禦/空路徑由
#   test_politics.test_legacy_survives_corrupt_faction_id 守)。


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_knights OK")
