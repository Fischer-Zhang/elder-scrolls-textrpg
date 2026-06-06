"""神話黎明(Mythic Dawn,第 5 公會 / 陣營 Phase D ①)的測試:
大事件解鎖入會、合約晉升階梯、技能門檻、分支壓軸、達貢之佑 perk(召喚增幅)、
與戰士公會雙向對立、存檔向後相容(零新欄位)。"""

import json

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, factions, magic, quests

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
    assert c.world_events_fired == []                 # 開局=Oblivion 現狀
    assert not factions.can_join(c, gd, FACTION)       # 事件未發生 → 隱於陰影
    assert factions.join_block_reason(c, gd, FACTION) is not None
    c.world_events_fired.append(UNLOCK)                # 凱瓦奇陷落
    assert factions.can_join(c, gd, FACTION)           # 信徒現身,可入會
    assert factions.join_block_reason(c, gd, FACTION) is None


def test_unlock_gate_is_generic_not_hardcoded():
    # 事件閘讀 factions.json 的 unlock_event 欄位,非硬編碼 mythic_dawn
    gd, _ = _state()
    assert gd.factions[FACTION]["unlock_event"] == UNLOCK
    # 無 unlock_event 的公會不受影響(戰士公會照常)
    assert "unlock_event" not in gd.factions["fighters_guild"]


def test_rival_member_cannot_join():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    factions.join(c, "fighters_guild")                 # 戰士公會員(對立)
    assert not factions.can_join(c, gd, FACTION)
    assert "勢不兩立" in factions.join_block_reason(c, gd, FACTION)


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


def test_rank_skill_gate_blocks_advancement():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.skills.update(conjuration=5, destruction=5, blade=5, sneak=5, mysticism=5)
    factions.join(c, FACTION)
    c.factions[FACTION] = 1                             # 追隨者:晉升需門檻 12
    assert quests.available_quests(c, gd, "guild", FACTION) == []
    assert factions.advance_block_reason(c, gd, FACTION) is not None


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
def test_conjure_boon_scales_with_rank():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    assert factions.conjure_boon(c, gd) == 0.0          # 非會員=0
    factions.join(c, FACTION)
    assert factions.conjure_boon(c, gd) == 0.0          # rank 0=0
    c.factions[FACTION] = 6                              # 曼卡的門徒
    assert abs(factions.conjure_boon(c, gd) - 0.6) < 1e-9   # 夾在 cap


def test_summon_boon_strengthens_ally():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    c.magicka = 999
    # 同種子下:非會員 vs 滿階會員 召喚同一隻 → 會員召喚物更耐久、駐留更久
    base_hp = gd.bestiary["summoned_familiar"]["max_health"]

    battle0 = {}
    magic.cast(c, gd, "conjure_familiar", RNG(11), battle=battle0)
    ally0 = battle0["allies"][0]

    factions.join(c, FACTION)
    c.factions[FACTION] = 6                              # boon=0.6
    c.magicka = 999
    battle1 = {}
    magic.cast(c, gd, "conjure_familiar", RNG(11), battle=battle1)
    ally1 = battle1["allies"][0]

    assert ally1.max_health == round(ally0.max_health * 1.6)
    assert ally1.health == ally1.max_health
    assert ally1.max_health > base_hp                   # 確實放大
    assert ally1.summon_turns == 6 + int(0.6 * 3)        # +1 回合


# --- 存檔向後相容(零新欄位)----------------------------------------
def test_membership_survives_save_roundtrip():
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 3
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert factions.is_member(loaded, FACTION)
    assert factions.rank_index(loaded, FACTION) == 3
    assert UNLOCK in loaded.world_events_fired


def test_legacy_includes_mythic_dawn():
    from tesrpg.systems import legacy
    gd, st = _state(world_events_fired=[UNLOCK])
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 2
    result = legacy.compute(st, gd)
    names = [name for name, _ in result["factions"]]
    assert "神話黎明" in names


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_mythicdawn OK")
