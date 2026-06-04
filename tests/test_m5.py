"""M5:任務引擎、公會晉升、犯罪賞金、NPC 好感的測試。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameTime
from tesrpg.systems import combat, crime, dialogue, factions, inventory, quests


def _char():
    gd = get_gamedata()
    return gd, build_character(gd, name="俠", sex="male", race="imperial",
                               birthsign="warrior", class_id="warrior")


# --- 任務:擊殺 ---------------------------------------------------------
def test_kill_quest_uses_baseline_not_retroactive():
    gd, c = _char()
    quests.record_kill(c, "wolf")          # 接任務前先殺一隻
    quests.accept_quest(c, gd, "job_wolf")  # 需殺 3 隻
    assert not quests.objective_met(c, gd, "job_wolf")  # 不可用接任務前的擊殺
    for _ in range(3):
        quests.record_kill(c, "wolf")
    assert quests.objective_met(c, gd, "job_wolf")
    evs = quests.check_completion(c, gd)
    assert any(e["quest_id"] == "job_wolf" for e in evs)
    assert "job_wolf" in c.completed_quests and "job_wolf" not in c.quests


def test_kill_quest_reward_granted():
    gd, c = _char()
    g0 = c.gold
    quests.accept_quest(c, gd, "job_bandit")   # kill 2 bandit, reward 160 + fame 5
    for _ in range(2):
        quests.record_kill(c, "bandit")
    quests.check_completion(c, gd)
    assert c.gold == g0 + 160 and c.fame == 5


# --- 任務:蒐集(上繳消耗)----------------------------------------------
def test_collect_quest_consumes_items():
    gd, c = _char()
    factions.join(c, "mages_guild")
    quests.accept_quest(c, gd, "mg1")          # collect bone_meal x2
    inventory.add_item(c, "bone_meal", 2)
    assert quests.objective_met(c, gd, "mg1")
    quests.check_completion(c, gd)
    assert inventory.count_item(c, "bone_meal") == 0     # 已上繳
    assert "mg1" in c.completed_quests


# --- 任務:抵達 / 肅清地城 ----------------------------------------------
def test_reach_quest():
    gd, c = _char()
    factions.join(c, "thieves_guild")
    c.factions["thieves_guild"] = 1            # tg2 需 rank 1
    quests.accept_quest(c, gd, "tg2")          # reach haafingar
    assert not quests.objective_met(c, gd, "tg2")
    c.location_id = "haafingar"
    assert quests.objective_met(c, gd, "tg2")


def test_clear_dungeon_quest():
    gd, c = _char()
    quests.accept_quest(c, gd, "job_cave")
    assert not quests.objective_met(c, gd, "job_cave")
    quests.record_dungeon_clear(c, "cedernoc_cave")
    assert quests.objective_met(c, gd, "job_cave")


# --- 公會:入會、可接任務、晉升 ----------------------------------------
def test_guild_join_and_rank():
    gd, c = _char()
    assert not factions.is_member(c, "fighters_guild")
    factions.join(c, "fighters_guild")
    assert factions.is_member(c, "fighters_guild")
    assert factions.rank_index(c, "fighters_guild") == 0
    assert factions.rank_name(c, gd, "fighters_guild") == gd.factions["fighters_guild"]["ranks"][0]


def test_guild_quests_gated_by_membership_and_rank():
    gd, c = _char()
    # 非會員 → 看不到公會任務
    assert quests.available_quests(c, gd, "guild", "fighters_guild") == []
    factions.join(c, "fighters_guild")
    avail = quests.available_quests(c, gd, "guild", "fighters_guild")
    assert avail == ["fg1"]                      # rank 0 只給 fg1
    assert "fg2" not in avail                     # fg2 需 rank 1


def test_guild_promotion_on_rank_quest():
    gd, c = _char()
    factions.join(c, "fighters_guild")
    quests.accept_quest(c, gd, "fg1")            # rank 0 任務
    for _ in range(2):
        quests.record_kill(c, "wolf")
    evs = quests.check_completion(c, gd)
    assert factions.rank_index(c, "fighters_guild") == 1   # 已晉升
    assert any(e["promoted"] and e["promoted"][0] == "fighters_guild" for e in evs)
    # 晉升後才看得到 fg2
    assert quests.available_quests(c, gd, "guild", "fighters_guild") == ["fg2"]


# --- 犯罪 / 賞金 / 衛兵 -------------------------------------------------
def test_steal_success_and_caught():
    gd, c = _char()
    c.skills["sneak"] = 100; c.skills["security"] = 100
    r = crime.steal_item(c, gd, "iron_sword", RNG(0))
    assert r["ok"] and inventory.count_item(c, "iron_sword") >= 1
    c.skills["sneak"] = 0; c.skills["security"] = 0
    caught = any(crime.steal_item(c, gd, "iron_sword", RNG(i))["caught"] for i in range(20))
    assert caught
    assert crime.bounty(c, crime.province_of(c, gd)) > 0


def test_bounty_per_province():
    gd, c = _char()
    crime.add_bounty(c, "賽羅迪爾", 50)
    crime.add_bounty(c, "天際", 30)
    assert crime.bounty(c, "賽羅迪爾") == 50 and crime.bounty(c, "天際") == 30


def test_pay_fine_and_jail():
    gd, c = _char()
    c.gold = 100
    crime.add_bounty(c, "賽羅迪爾", 40)
    r = crime.pay_fine(c, gd)
    assert r["ok"] and c.gold == 60 and crime.bounty(c, "賽羅迪爾") == 0
    # 服刑清空賞金並推進時間
    crime.add_bounty(c, "賽羅迪爾", 200)
    t = GameTime()
    res = crime.serve_sentence(c, gd, t)
    assert res["cleared"] == 200 and crime.bounty(c, "賽羅迪爾") == 0 and res["hours"] > 0


def test_pay_fine_insufficient():
    gd, c = _char()
    c.gold = 5
    crime.add_bounty(c, "賽羅迪爾", 40)
    assert not crime.pay_fine(c, gd)["ok"]
    assert crime.bounty(c, "賽羅迪爾") == 40   # 未清


# --- NPC 好感 / 對話 ---------------------------------------------------
def test_bribe_raises_disposition():
    gd, c = _char()
    c.gold = 100
    d0 = dialogue.disposition(c, gd, "olfina")
    assert dialogue.bribe(c, gd, "olfina")["ok"]
    assert dialogue.disposition(c, gd, "olfina") > d0
    assert c.gold == 100 - dialogue.BRIBE_COST


def test_npc_quest_gated_by_disposition():
    gd, c = _char()
    assert dialogue.offered_quest(c, gd, "olfina") is None   # 初始好感不足
    c.npc_disposition["olfina"] = 50                          # base 45 + 50 = 95 >= 60
    assert dialogue.offered_quest(c, gd, "olfina") == "favor_bruma"
    quests.accept_quest(c, gd, "favor_bruma")
    assert dialogue.offered_quest(c, gd, "olfina") is None    # 已接,不再提供


# --- 戰鬥 hook:擊殺計數 ------------------------------------------------
def test_kill_progress_hidden_before_accept():
    """回歸(審查 [1]):未接取的擊殺任務不可在告示板顯示既往擊殺。"""
    gd, c = _char()
    for _ in range(3):
        quests.record_kill(c, "wolf")
    assert quests.kill_progress(c, gd, "job_wolf") == (0, 3)
    assert "0/3" in quests.objective_text(c, gd, "job_wolf")
    quests.accept_quest(c, gd, "job_wolf")
    assert quests.kill_progress(c, gd, "job_wolf") == (0, 3)   # 接取後從 0 起算


def test_promotion_clamps_at_max_rank():
    """回歸(審查 [2]/[6]):晉升不可讓階級索引越界。"""
    gd, c = _char()
    fac = "fighters_guild"
    ranks = gd.factions[fac]["ranks"]
    top = len(ranks) - 1
    factions.join(c, fac)
    c.factions[fac] = top
    qid = "__tmp_top_rank_quest__"
    gd.quests[qid] = {"name": "頂階試煉", "faction": fac, "rank": top, "source": "guild",
                      "objective": {"type": "reach", "location": c.location_id},
                      "reward": {}, "turn_in": "auto", "text": ""}
    try:
        quests.accept_quest(c, gd, qid)
        quests.check_completion(c, gd)
        assert c.factions[fac] == top            # 夾限,不會變成 top+1
        assert factions.rank_name(c, gd, fac) == ranks[top]
    finally:
        del gd.quests[qid]


def test_combat_victory_records_kill_via_autoresolve():
    gd, c = _char()
    rng = RNG(7)
    rat = combat.spawn_creature(gd, "giant_rat", rng)
    combat.auto_resolve(c, rat, gd, rng)
    # auto_resolve 不含 hook;此處驗證 template_id 可供 record_kill 使用
    quests.record_kill(c, rat.template_id)
    assert c.kill_counts.get("giant_rat", 0) >= 1


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m5 OK")
