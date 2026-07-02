"""黑暗兄弟會(里程碑)的測試:謀殺/血債招募、合約晉升階梯、分支壓軸、
夜母祝福(潛殺加成)、洗白賞金 perk、存檔向後相容、暗殺者開局。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import brotherhood, combat, crime, factions, quests, stats

FACTION = brotherhood.FACTION


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="影", sex="male", race="khajiit",
                        birthsign="shadow", class_id="assassin")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime(), rng=RNG(7))


# --- 謀殺 / 血債 -------------------------------------------------------
def test_record_murder_adds_bounty_infamy_and_removes_npc():
    gd, st = _state(location_id="bruma")
    c = st.player
    before_inf = c.infamy
    res = brotherhood.record_murder(st, gd, "olfina")
    assert c.murders == 1
    assert c.infamy == before_inf + brotherhood.MURDER_INFAMY
    assert crime.bounty(c, res["province"]) >= brotherhood.MURDER_BOUNTY
    assert "olfina" in c.murdered_npcs


def test_blood_debt_and_should_recruit():
    gd, st = _state()
    c = st.player
    assert not brotherhood.should_recruit(c, gd)        # 尚無血債
    c.murders = 1
    assert brotherhood.has_blood_debt(c)
    assert brotherhood.should_recruit(c, gd)
    brotherhood.decline_recruit(c)                       # 婉拒 → 不再每次觸發
    assert not brotherhood.should_recruit(c, gd)
    # 婉拒後仍可自行入會:recruit 重設 db_invited 並正式入會(rank 0「新血」)
    brotherhood.recruit(c)
    assert brotherhood.is_member(c)
    assert brotherhood.rank(c) == 0
    assert c.db_invited is True
    assert brotherhood.rank_name(c, gd) == gd.factions[FACTION]["ranks"][0]
    # 對立公會員(戰士公會)不會被招募:用新鮮 char(兄弟會與戰士公會互為 rivals)
    _, st_b = _state()
    b = st_b.player
    b.murders = 5
    factions.join(b, "fighters_guild")                  # 戰士公會員(對立)
    assert brotherhood.in_rival_faction(b, gd) is True
    assert not brotherhood.should_recruit(b, gd)


# --- 夜母祝福(潛殺加成)----------------------------------------------
def test_night_mother_sneak_bonus_scales_with_rank():
    assert formulas.night_mother_sneak_bonus(-1) == 1.0   # 非會員
    assert formulas.night_mother_sneak_bonus(0) == 1.0    # 新血:尚無加成
    assert formulas.night_mother_sneak_bonus(6) > formulas.night_mother_sneak_bonus(3) > 1.0


def test_blessing_increases_player_sneak_estimate():
    gd, st = _state()
    c = st.player
    c.skills["sneak"] = 60
    c.weapon = "steel_dagger"
    stats.recompute_max_resources(c, gd, restore_full=True)
    foe = combat.spawn_creature(gd, "greedy_merchant", RNG(1))
    base = combat.estimate_sneak_damage(c, gd, foe)
    factions.join(c, FACTION)
    c.factions[FACTION] = 6        # 聆聽者
    boosted = combat.estimate_sneak_damage(c, gd, foe)
    assert boosted > base


# --- 洗白賞金 perk ----------------------------------------------------
def test_launder_cost_drops_with_rank_and_clears_bounty():
    gd, st = _state(location_id="bruma")
    c = st.player
    factions.join(c, FACTION)
    crime.add_bounty(c, "賽羅迪爾", 1000)
    c.factions[FACTION] = 0
    cost0 = brotherhood.launder_cost(c, gd, 1000)
    c.factions[FACTION] = 5
    cost5 = brotherhood.launder_cost(c, gd, 1000)
    assert cost0 == 1000 and cost5 < cost0           # 新血無折扣、高階有折扣
    c.gold = cost5
    r = brotherhood.launder_bounty(st, gd)
    assert r["ok"] and crime.bounty(c, "賽羅迪爾") == 0


# --- 合約晉升階梯 -----------------------------------------------------
def test_contract_ladder_promotes_on_kill():
    gd, st = _state()
    c = st.player
    c.skills.update(sneak=80, blade=60)
    factions.join(c, FACTION)                         # 直接入會(rank 0)
    avail = quests.available_quests(c, gd, "guild", FACTION)
    assert avail == ["db1"], avail                    # 只開放當前階級合約
    quests.accept_quest(c, gd, "db1")
    # R109:合約目標改為城內置放 NPC 暗殺(assassinate)→ 抹去該 NPC 即完成晉升
    obj, _, _ = quests.current_objective(c, gd, "db1")
    assert obj["type"] == "assassinate" and obj["npcs"] == ["db_greedy"]
    c.murdered_npcs.append("db_greedy")
    evs = quests.check_completion(c, gd)
    assert any(e["type"] == "completed" and e.get("promoted") for e in evs)
    assert brotherhood.rank(c) == 1
    assert "db1" in c.completed_quests
    # 升階後開放下一張(技能門檻 rank_skill_req[1]=12,sneak 80 已過)
    assert quests.available_quests(c, gd, "guild", FACTION) == ["db2"]


# --- 分支壓軸(五戒 vs 淨化背叛)-------------------------------------
def test_finale_branches_resolve_to_different_targets():
    gd, st = _state()
    c = st.player
    c.skills.update(sneak=90)
    factions.join(c, FACTION)
    c.factions[FACTION] = 5                            # 代言人:可接 db6
    assert "db6" in quests.available_quests(c, gd, "guild", FACTION)
    # 忠誠之路 → 叛徒;淨化之路 → 代言人
    quests.accept_quest(c, gd, "db6", branch=0)
    assert quests.current_objective(c, gd, "db6")[0]["npcs"] == ["db_traitor"]
    c.quests["db6"]["branch"] = 1
    assert quests.current_objective(c, gd, "db6")[0]["npcs"] == ["db_speaker"]
    # 兩條路線完成皆晉升為聆聽者(rank 6);R109 改暗殺置放 NPC
    c.murdered_npcs.append("db_speaker")
    quests.check_completion(c, gd)
    assert brotherhood.rank(c) == 6


def test_contract_targets_exist_in_bestiary():
    gd, _ = _state()
    for qid in gd.factions[FACTION]["rank_quests"]:
        q = gd.quests[qid]
        branch_objs = ([b["objective"] for b in q["branches"]] if "branches" in q
                       else [q["objective"]])
        for obj in branch_objs:
            if obj["type"] == "kill":                    # db3 怪物目標保留 kill
                assert obj["creature"] in gd.bestiary, f"{qid} 目標 {obj['creature']} 不在 bestiary"
            else:                                        # R109:humanoid 目標轉城內置放 NPC 暗殺
                assert obj["type"] == "assassinate"
                for nid in obj["npcs"]:
                    assert gd.npcs.get(nid, {}).get("combat_template") in gd.bestiary, f"{qid} 目標 {nid} 未置放/無戰鬥模板"


# --- 開局 / 一生傳奇 / 存檔 -------------------------------------------
def test_dark_initiate_origin_grants_membership():
    gd = get_gamedata()
    c = build_character(gd, name="刃", sex="female", race="dunmer",
                        birthsign="shadow", class_id="assassin", origin_id="dark_initiate")
    assert brotherhood.is_member(c)
    assert brotherhood.rank(c) == 0
    assert c.weapon == "steel_dagger"


def test_legacy_label():
    gd, st = _state()
    c = st.player
    assert brotherhood.legacy_label(c, gd) is None
    c.murders = 3
    assert "謀殺 3 人" in brotherhood.legacy_label(c, gd)
    factions.join(c, FACTION)
    c.factions[FACTION] = 6
    assert "聆聽者" in brotherhood.legacy_label(c, gd)


def test_save_load_roundtrip_and_backward_compat():
    gd, st = _state(murders=2, db_invited=True)
    c = st.player
    factions.join(c, FACTION)
    c.factions[FACTION] = 3
    c.murdered_npcs = ["olfina"]
    d = st.to_dict()
    st2 = GameState.from_dict(d)
    assert st2.player.murders == 2 and st2.player.db_invited is True
    assert st2.player.murdered_npcs == ["olfina"]
    assert brotherhood.rank(st2.player) == 3
    # 向後相容:舊存檔缺新欄位 → dataclass 預設值
    pd = c.to_dict()
    for k in ("murders", "db_invited", "murdered_npcs"):
        pd.pop(k, None)
    old = Character.from_dict(pd)
    assert old.murders == 0 and old.db_invited is False and old.murdered_npcs == []


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_brotherhood OK")
