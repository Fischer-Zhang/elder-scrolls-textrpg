"""M5:任務引擎、公會晉升、犯罪賞金、NPC 好感的測試。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameTime
from tesrpg.systems import crime, dialogue, factions, inventory, quests


def _char():
    gd = get_gamedata()
    return gd, build_character(gd, name="俠", sex="male", race="imperial",
                               birthsign="warrior", class_id="warrior")


# --- 任務:擊殺(基線非溯及 + 既往隱藏 + 獎勵授予)---------------------
def test_kill_quest_uses_baseline_not_retroactive():
    gd, c = _char()
    # 既往擊殺:接任務前先殺 3 隻(超過需求 count=3)
    for _ in range(3):
        quests.record_kill(c, "wolf")
    # 併入 [test_kill_progress_hidden_before_accept]:未接取的擊殺任務
    # 告示板不顯示既往擊殺(回歸審查 [1])。
    assert quests.kill_progress(c, gd, "job_wolf") == (0, 3)
    assert "0/3" in quests.objective_text(c, gd, "job_wolf")

    g0 = c.gold                              # 接 job_wolf 前的金幣基線
    quests.accept_quest(c, gd, "job_wolf")  # 需殺 3 隻
    # 接取後從 0 起算/不溯及:既往擊殺不算數
    assert quests.kill_progress(c, gd, "job_wolf") == (0, 3)
    assert not quests.objective_met(c, gd, "job_wolf")  # 不可用接任務前的擊殺
    for _ in range(3):
        quests.record_kill(c, "wolf")
    assert quests.objective_met(c, gd, "job_wolf")
    evs = quests.check_completion(c, gd)
    assert any(e["quest_id"] == "job_wolf" for e in evs)
    assert "job_wolf" in c.completed_quests and "job_wolf" not in c.quests
    # 併入 [test_kill_quest_reward_granted](job_wolf 段):reward {gold:120} 無 fame
    assert c.gold == g0 + 120

    # 併入 [test_kill_quest_reward_granted](job_bandit 段):
    # fame 獎勵唯有 job_bandit 才有,fame 斷言零流失。
    g1 = c.gold
    quests.accept_quest(c, gd, "job_bandit")   # kill 2 bandit, reward 160 + fame 5
    for _ in range(2):
        quests.record_kill(c, "bandit")
    quests.check_completion(c, gd)
    assert c.gold == g1 + 160 and c.fame == 5


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


def test_pay_fine_and_jail():
    gd, c = _char()
    # 跨省賞金隔離(併自 test_bounty_per_province):對賽羅迪爾的 add/pay/serve 全程不污染天際
    crime.add_bounty(c, "天際", 30)
    # 併入 [test_pay_fine_insufficient]:金不足繳不了罰款且賞金不清。
    c.gold = 5
    crime.add_bounty(c, "賽羅迪爾", 40)
    assert not crime.pay_fine(c, gd)["ok"]
    assert crime.bounty(c, "賽羅迪爾") == 40   # 未清
    crime.clear_bounty(c, "賽羅迪爾")          # 重置續跑足額分支

    c.gold = 100
    crime.add_bounty(c, "賽羅迪爾", 40)
    r = crime.pay_fine(c, gd)
    assert r["ok"] and c.gold == 60 and crime.bounty(c, "賽羅迪爾") == 0
    # 服刑清空賞金並推進時間
    crime.add_bounty(c, "賽羅迪爾", 200)
    t = GameTime()
    res = crime.serve_sentence(c, gd, t)
    assert res["cleared"] == 200 and crime.bounty(c, "賽羅迪爾") == 0 and res["hours"] > 0
    assert crime.bounty(c, "天際") == 30        # 全程未被賽羅迪爾的 add/pay/serve 污染


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


# --- 戰鬥 hook:晉升夾限 ------------------------------------------------
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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m5 OK")
