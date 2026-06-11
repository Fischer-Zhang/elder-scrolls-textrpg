"""神話黎明(Mythic Dawn,第 5 公會 / 陣營 Phase D ①)的測試:
大事件解鎖入會(含 unlock_event 泛型閘資料 pin)、合約晉升階梯、分支壓軸、
達貢之佑 perk(召喚增幅;perk 值資料 pin 折入召喚物放大整合測)、
fg↔md rivals 雙向資料、合約/護送目標 in bestiary。

註:技能門檻擋晉升 / rival 拒入 / 會籍存檔往返 / legacy 列名 等同型機制由
test_guild_depth、test_brotherhood 等 canonical 測試覆蓋,本模組重複測已裁減。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import factions, magic, quests

FACTION = "mythic_dawn"
UNLOCK = "kvatch_falls"


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="赤袍", sex="female", race="dunmer",
                        birthsign="apprentice", class_id="mage")
    c.skills.update(conjuration=30, destruction=20, blade=20, sneak=20, mysticism=20)
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime(), rng=RNG(7))


# --- 大事件解鎖 -------------------------------------------------------
def test_locked_until_kvatch_falls():
    gd, st = _state()
    c = st.player
    # 事件閘讀 factions.json 的 unlock_event 欄、非硬編碼(吸收自
    # test_unlock_gate_is_generic_not_hardcoded);無此欄的公會不受影響。
    assert gd.factions[FACTION]["unlock_event"] == UNLOCK
    assert "unlock_event" not in gd.factions["fighters_guild"]
    assert c.world_events_fired == []                 # 開局=Oblivion 現狀
    assert not factions.can_join(c, gd, FACTION)       # 事件未發生 → 隱於陰影
    assert factions.join_block_reason(c, gd, FACTION) is not None
    c.world_events_fired.append(UNLOCK)                # 凱瓦奇陷落
    assert factions.can_join(c, gd, FACTION)           # 信徒現身,可入會
    assert factions.join_block_reason(c, gd, FACTION) is None


def test_fighters_guild_rivals_mythic_dawn_bidirectional():
    gd, _ = _state()
    assert FACTION in gd.factions["fighters_guild"]["rivals"]
    assert "fighters_guild" in gd.factions[FACTION]["rivals"]


# --- 合約晉升階梯 -----------------------------------------------------
def test_contract_ladder_promotes_on_kill():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.skills.update(conjuration=80)                     # 確保跨門檻
    factions.join(c, FACTION)
    assert quests.available_quests(c, gd, "guild", FACTION) == ["md1"]
    quests.accept_quest(c, gd, "md1")
    obj, _, _ = quests.current_objective(c, gd, "md1")
    assert obj["creature"] == "faithful_of_nine"
    quests.record_kill(c, "faithful_of_nine")
    evs = quests.check_completion(c, gd)
    assert any(e["type"] == "completed" and e.get("promoted") for e in evs)
    assert factions.rank_index(c, FACTION) == 1
    assert "md1" in c.completed_quests
    assert quests.available_quests(c, gd, "guild", FACTION) == ["md2"]


def test_finale_branches_resolve_to_different_targets():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.skills.update(conjuration=90)
    factions.join(c, FACTION)
    c.factions[FACTION] = 5                             # 達貢之選:可接 md6
    assert "md6" in quests.available_quests(c, gd, "guild", FACTION)
    quests.accept_quest(c, gd, "md6", branch=0)
    assert quests.current_objective(c, gd, "md6")[0]["creature"] == "mythic_apostate"
    c.quests["md6"]["branch"] = 1
    assert quests.current_objective(c, gd, "md6")[0]["creature"] == "dawn_mentor"
    quests.record_kill(c, "dawn_mentor")
    quests.check_completion(c, gd)
    assert factions.rank_index(c, FACTION) == 6        # 曼卡的門徒


def test_contract_targets_exist_in_bestiary():
    gd, _ = _state()
    for qid in gd.factions[FACTION]["rank_quests"]:
        q = gd.quests[qid]
        branch_objs = ([b["objective"] for b in q["branches"]] if "branches" in q
                       else [q["objective"]])
        for obj in branch_objs:
            assert obj["type"] == "kill"
            assert obj["creature"] in gd.bestiary, f"{qid} 目標 {obj['creature']} 不在 bestiary"


def test_escort_target_exists():
    gd, _ = _state()
    for eid in gd.quests["md4"].get("escort", []):
        assert eid in gd.bestiary


# --- 達貢之佑 perk(召喚增幅)----------------------------------------
def test_summon_boon_strengthens_ally():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.magicka = 999
    # 達貢之佑 perk 值資料 pin(吸收自 test_conjure_boon_scales_with_rank):
    # 非會員=0 / rank0=0 / 滿階夾在 cap 0.6,接續驗召喚物放大接線。
    assert factions.conjure_boon(c, gd) == 0.0          # 非會員=0
    # 同種子下:非會員 vs 滿階會員 召喚同一隻 → 會員召喚物更耐久、駐留更久
    base_hp = gd.bestiary["summoned_familiar"]["max_health"]

    battle0 = {}
    magic.cast(c, gd, "conjure_familiar", RNG(11), battle=battle0)
    ally0 = battle0["allies"][0]

    factions.join(c, FACTION)
    assert factions.conjure_boon(c, gd) == 0.0          # rank 0=0
    c.factions[FACTION] = 6                              # boon=0.6
    assert abs(factions.conjure_boon(c, gd) - 0.6) < 1e-9   # 夾在 cap
    c.magicka = 999
    battle1 = {}
    magic.cast(c, gd, "conjure_familiar", RNG(11), battle=battle1)
    ally1 = battle1["allies"][0]

    assert ally1.max_health == round(ally0.max_health * 1.6)
    assert ally1.health == ally1.max_health
    assert ally1.max_health > base_hp                   # 確實放大
    assert ally1.summon_turns == 6 + int(0.6 * 3)        # +1 回合


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_mythicdawn OK")
