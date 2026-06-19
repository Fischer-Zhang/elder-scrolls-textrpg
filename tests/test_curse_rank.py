"""血族階級政治 + 巢穴升級(R52)單元測試:curse-gated 入會、逐階晉升、perk 隨階+只詛咒、
sun_ward/beast_vigor 效果、頂階分支(篡位/繼承)、頂階誓福紅線、boss 紀律、存檔相容。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import boons, crime, factions, lycanthropy, quests, vampirism


def _state(seed=1, hour=12):
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


def _vampire(gd, c, st):
    c.is_vampire = True
    c.vampire_fed_day = st.time.absolute_hours() // 24
    vampirism.apply_to_character(c, st, gd)
    return c


# --- curse-gated 入會(無技能/賞金閘)------------------------------------
def test_curse_faction_join_no_skill_or_bounty_block():
    gd, c, st = _state()
    _vampire(gd, c, st)
    crime.add_bounty(c, "高岩", 500)                                  # 帶賞金
    assert factions.join_block_reason(c, gd, "coven_vampire") is None  # lawful:false·join_skill:0 → 不擋
    factions.join(c, "coven_vampire")
    assert factions.is_member(c, "coven_vampire") and factions.rank_index(c, "coven_vampire") == 0


# --- 逐階晉升 + available_quests 閘 -------------------------------------
def test_rank_progression_and_quest_gating():
    gd, c, st = _state()
    _vampire(gd, c, st)
    factions.join(c, "coven_vampire")
    assert quests.available_quests(c, gd, "guild", "coven_vampire") == ["coven1"]   # 只回本階
    quests.accept_quest(c, gd, "coven1")
    for _ in range(3):
        quests.record_kill(c, "bandit")
    quests.check_completion(c, gd)
    assert factions.rank_index(c, "coven_vampire") == 1                            # 晉升
    assert quests.available_quests(c, gd, "guild", "coven_vampire") == ["coven2"]   # 換下一階


# --- perk 隨階聚合 + 只詛咒者 -------------------------------------------
def test_perk_scales_with_rank_and_member_only():
    gd, c, st = _state()
    _vampire(gd, c, st)
    assert factions.sun_ward(c, gd) == 0.0                            # 非會員 = 0
    factions.join(c, "coven_vampire")
    assert factions.sun_ward(c, gd) == 0.0                            # rank 0 = 0
    c.factions["coven_vampire"] = 2
    assert abs(factions.sun_ward(c, gd) - 0.4) < 1e-9                 # rank 2 = 0.4
    c.factions["coven_vampire"] = 3
    assert abs(factions.sun_ward(c, gd) - 0.6) < 1e-9                 # cap 0.6
    gd2, m, st2 = _state()                                            # 凡人 = 0
    assert factions.sun_ward(m, gd2) == 0.0 and factions.beast_vigor(m, gd2) == 0.0


def test_sun_ward_reduces_sun_damage():
    gd, c, st = _state(hour=12)
    c.is_vampire = True
    c.vampire_fed_day = st.time.absolute_hours() // 24 - vampirism.STAGE_DAYS * 2   # stage 2
    vampirism.apply_to_character(c, st, gd)
    c.location_id = "rivenspire"                                      # 荒野(非地城)→ 日光生效
    c.health = c.max_health
    dmg0 = vampirism.expose_to_sun(st, gd, 4)                         # 無會籍 → 全傷
    factions.join(c, "coven_vampire"); c.factions["coven_vampire"] = 3   # rank 3 → 抗日 0.6
    c.health = c.max_health
    dmg3 = vampirism.expose_to_sun(st, gd, 4)
    assert 0 < dmg3 < dmg0                                            # 灼傷隨 sun_ward 降


def test_beast_vigor_extends_duration():
    gd, c, st = _state()
    lycanthropy.contract(c, st, gd)
    base = lycanthropy.effective_duration(c, st, gd)                  # 非會員 → 0 加成
    c.factions["werewolf_pack"] = 3                                   # rank 3 → beast_vigor 0.6
    boosted = lycanthropy.effective_duration(c, st, gd)
    assert boosted == base + int(base * 0.6) > base


# --- 頂階分支(篡位 / 繼承)---------------------------------------------
def _climb_and_capstone(gd, c, cap_qid, fac, master, branch):
    c.factions[fac] = 2                                               # 直升夜眷/撕咬者(rank 2)
    quests.accept_quest(c, gd, cap_qid, branch=branch)
    quests.record_kill(c, master)                                    # 決鬥勝(直接記擊殺)
    quests.check_completion(c, gd)


def test_coven_capstone_usurp():
    gd, c, st = _state(); _vampire(gd, c, st)
    _climb_and_capstone(gd, c, "coven3", "coven_vampire", "coven_patriarch", branch=0)
    assert factions.rank_index(c, "coven_vampire") == 3              # 血主
    assert boons.has_boon(c, "coven_usurper") and "coven_usurped" in c.world_events_fired
    assert c.infamy >= 20 and not boons.has_boon(c, "coven_heir")


def test_coven_capstone_inherit():
    gd, c, st = _state(); _vampire(gd, c, st)
    _climb_and_capstone(gd, c, "coven3", "coven_vampire", "coven_patriarch", branch=1)
    assert factions.rank_index(c, "coven_vampire") == 3
    assert boons.has_boon(c, "coven_heir") and "coven_inherited" in c.world_events_fired
    assert c.fame >= 20 and not boons.has_boon(c, "coven_usurper")


def test_pack_capstone_both_branches():
    gd, c, st = _state(); lycanthropy.contract(c, st, gd)
    _climb_and_capstone(gd, c, "pack3", "werewolf_pack", "dire_alpha", branch=0)
    assert factions.rank_index(c, "werewolf_pack") == 3 and boons.has_boon(c, "pack_usurper")
    gd2, c2, st2 = _state(); lycanthropy.contract(c2, st2, gd2)
    _climb_and_capstone(gd2, c2, "pack3", "werewolf_pack", "dire_alpha", branch=1)
    assert boons.has_boon(c2, "pack_heir") and "pack_inherited" in c2.world_events_fired


# --- 紅線 / boss / 存檔 -------------------------------------------------
def test_capstone_boons_red_lines():
    gd = get_gamedata()
    weap = {"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
    for bid in ("coven_usurper", "coven_heir", "pack_usurper", "pack_heir"):
        bo = gd.boons[bid]
        assert not (weap & set(bo.get("skill", {}))), bid
        assert bo.get("attr", {}).get("strength", 0) <= 10, bid       # ≤ 既有 R45 上界


def test_capstone_boss_discipline():
    gd = get_gamedata()
    for boss in ("coven_patriarch", "dire_alpha"):
        b = gd.bestiary[boss]
        assert b.get("solo") is True
        for atk in b.get("attacks", []):
            oh = atk.get("on_hit") or {}
            if oh.get("status") in ("fear", "paralyze"):
                assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk


def test_content_integrity_factions():
    gd = get_gamedata()
    for fid, perk in (("coven_vampire", "sun_ward"), ("werewolf_pack", "beast_vigor")):
        f = gd.factions[fid]
        assert f["perk"]["kind"] == perk and f["join_skill"] == 0 and f["lawful"] is False
        assert len(f["rank_quests"]) == len(f["ranks"]) - 1
        for qid in f["rank_quests"]:
            assert gd.quests[qid]["faction"] == fid and gd.quests[qid]["source"] == "guild"
        # hall = 對應巢穴
        assert gd.world["locations"][f["hall"]].get("lair")


def test_save_roundtrip_faction_and_capstone_boon():
    gd, c, st = _state(); _vampire(gd, c, st)
    _climb_and_capstone(gd, c, "coven3", "coven_vampire", "coven_patriarch", branch=0)
    d = c.to_dict()
    c2 = type(c).from_dict(d)
    assert c2.factions.get("coven_vampire") == 3 and boons.has_boon(c2, "coven_usurper")
    assert not any(k in ("rank", "perk") for k in d)                  # 無新存檔頂層欄


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
