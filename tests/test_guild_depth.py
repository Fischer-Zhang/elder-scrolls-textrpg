"""公會深度化:入會/晉升技能門檻、對立排他、守法、階級福利、晉升任務分支。

對應「公會太扁平」的四層修正(L1 門檻 / L2 福利 / L3 排他 / L4 分支)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import factions, inventory, quests, world


def _char(**kw):
    gd = get_gamedata()
    base = dict(name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    base.update(kw)
    return gd, build_character(gd, **base)


def _zero_skills(c):
    for s in list(c.skills):
        c.skills[s] = 0


# --- L1 入會門檻 --------------------------------------------------------
def test_join_requires_gate_skill():
    gd, c = _char()
    _zero_skills(c)
    assert not factions.can_join(c, gd, "mages_guild")           # 技能 0 < 門檻
    assert "達" in factions.join_block_reason(c, gd, "mages_guild")
    c.skills["destruction"] = 10                                 # 把關技能達門檻
    assert factions.can_join(c, gd, "mages_guild")               # 7 gate_skill 只 1 達標即過(best-of)
    assert factions.join_block_reason(c, gd, "mages_guild") is None
    # best-of 多 gate_skill:盜賊有 5 把關技能,只要一技達標即可入會
    # (destruction 不屬 thieves gate_skills、其餘 thieves gate_skill 仍為 0,故僅 security 驅動)
    c.skills["security"] = 12
    assert factions.can_join(c, gd, "thieves_guild")


# --- L1 晉升門檻 --------------------------------------------------------
def test_advancement_blocked_by_skill_then_unblocked():
    gd, c = _char()
    _zero_skills(c)
    c.skills["blade"] = 20
    factions.join(c, "fighters_guild")
    c.factions["fighters_guild"] = 2          # rank2 需 rank_skill_req[2]=26
    assert quests.available_quests(c, gd, "guild", "fighters_guild") == []
    assert "26" in factions.advance_block_reason(c, gd, "fighters_guild")
    c.skills["blade"] = 26
    assert quests.available_quests(c, gd, "guild", "fighters_guild") == ["fg3"]
    assert factions.advance_block_reason(c, gd, "fighters_guild") is None


# --- L3 對立排他 --------------------------------------------------------
def test_rival_guilds_mutually_exclusive():
    gd, c = _char()
    for s in list(c.skills):
        c.skills[s] = 50
    factions.join(c, "fighters_guild")
    assert not factions.can_join(c, gd, "thieves_guild")        # 戰士的死對頭
    assert "勢不兩立" in factions.join_block_reason(c, gd, "thieves_guild")
    # 反向亦然
    gd2, c2 = _char()
    for s in list(c2.skills):
        c2.skills[s] = 50
    factions.join(c2, "thieves_guild")
    assert not factions.can_join(c2, gd2, "fighters_guild")


# --- L3 守法(通緝賞金擋戰士公會)--------------------------------------
def test_lawful_guild_rejects_wanted_criminal():
    gd, c = _char()
    for s in list(c.skills):
        c.skills[s] = 50
    c.bounties["賽羅迪爾"] = 200
    assert not factions.can_join(c, gd, "fighters_guild")
    assert "通緝" in factions.join_block_reason(c, gd, "fighters_guild")
    # 非守法公會不受影響
    assert factions.can_join(c, gd, "mages_guild")
    # 繳清後可入會
    c.bounties["賽羅迪爾"] = 0
    assert factions.can_join(c, gd, "fighters_guild")


# --- L2 階級福利 --------------------------------------------------------
def test_perks_scale_with_rank_and_cap():
    gd, c = _char()
    factions.join(c, "thieves_guild")
    c.factions["thieves_guild"] = 0
    assert factions.sell_bonus(c, gd) == 0.0                    # 最低階無加成
    c.factions["thieves_guild"] = 3
    mid = factions.sell_bonus(c, gd)
    assert mid > 0
    c.factions["thieves_guild"] = 99                            # 遠超頂階 → 夾限到 cap
    assert factions.sell_bonus(c, gd) == gd.factions["thieves_guild"]["perk"]["cap"]


def test_thief_sells_for_more():
    gd, c = _char()
    base = world.sell_price(c, gd, "ruby")
    factions.join(c, "thieves_guild")
    c.factions["thieves_guild"] = 5
    assert world.sell_price(c, gd, "ruby") > base               # 銷贓加成生效


def test_armory_and_spell_discounts():
    gd, c = _char()
    factions.join(c, "fighters_guild")
    c.factions["fighters_guild"] = 7                            # 會長 → 軍械庫折扣達上限(cap 0.35)
    assert factions.armory_discount(c, gd) == 0.35
    # 軍械庫折扣只套在武器/護甲:同角色入會 vs 退會,鋼劍變便宜、藥水不受影響(處置不變)
    sword_member = world.buy_price(c, gd, "steel_sword")
    potion_member = world.buy_price(c, gd, "minor_healing_potion")
    saved = c.factions.pop("fighters_guild")
    assert factions.armory_discount(c, gd) == 0.0
    assert world.buy_price(c, gd, "steel_sword") > sword_member        # 武器享折扣
    assert world.buy_price(c, gd, "minor_healing_potion") == potion_member   # 藥水不享折扣
    c.factions["fighters_guild"] = saved
    factions.join(c, "mages_guild")
    c.factions["mages_guild"] = 5
    assert 0 < factions.spell_discount(c, gd) <= 0.45


# --- L2 晉升俸祿 --------------------------------------------------------
def test_promotion_pays_stipend():
    gd, c = _char()
    factions.join(c, "fighters_guild")          # rank 0
    g0 = c.gold
    quests.accept_quest(c, gd, "fg1")           # kill wolf x2 → 完成晉升 rank1
    for _ in range(2):
        quests.record_kill(c, "wolf")
    evs = quests.check_completion(c, gd)
    done = next(e for e in evs if e["type"] == "completed")
    assert done["promoted"][0] == "fighters_guild"
    assert done["stipend"] == quests.STIPEND_PER_RANK * 1       # 升到 rank1
    # 金幣 = 任務獎勵 + 俸祿
    assert c.gold == g0 + done["reward"].get("gold", 0) + done["stipend"]
    # 併入 [test_m5.test_guild_promotion_on_rank_quest]:晉升後才解鎖 fg2。
    assert quests.available_quests(c, gd, "guild", "fighters_guild") == ["fg2"]


# --- L4 敘事分支 --------------------------------------------------------
def test_branch_choice_changes_objective_and_reward():
    gd, c = _char()
    c.factions["fighters_guild"] = 6
    # 分支 0:以武立威(先清灰燼墓塚);分支 1:掃境安民(先殺強盜)
    quests.accept_quest(c, gd, "fg7", branch=1)
    obj, idx, total = quests.current_objective(c, gd, "fg7")
    assert obj["type"] == "kill" and obj["creature"] == "bandit"   # 分支 1 首階
    assert (idx, total) == (0, 3)

    # 走完分支 1 三階段 → 拿到分支 1 的獎勵(ebony_shield),而非分支 0 的 ebony_sword
    for _ in range(30):
        o, _, _ = quests.current_objective(c, gd, "fg7")
        t = o["type"]
        if t == "kill":
            for _ in range(o["count"]):
                quests.record_kill(c, o["creature"])
        elif t == "clear_dungeon":
            quests.record_dungeon_clear(c, o["dungeon"])
        elif t == "reach":
            c.location_id = o["location"]
        evs = quests.check_completion(c, gd)
        if "fg7" in c.completed_quests:
            break
    assert "fg7" in c.completed_quests
    assert inventory.count_item(c, "ebony_shield") == 1
    assert inventory.count_item(c, "ebony_sword") == 0


def test_branch_persists_across_stage_advance():
    gd, c = _char()
    c.factions["thieves_guild"] = 4
    quests.accept_quest(c, gd, "tg5", branch=1)        # 銷贓網絡:collect ruby x4 先行
    assert c.quests["tg5"]["branch"] == 1
    inventory.add_item(c, "ruby", 4)
    quests.check_completion(c, gd)                      # 推進到下一階段
    assert c.quests["tg5"]["branch"] == 1              # 分支不因階段推進而遺失
    assert quests.current_objective(c, gd, "tg5")[0]["type"] == "reach"


def test_guildmaster_artifacts():
    """5 個持久公會的壓軸任務(掌門)兩條 branch 皆授予該會專屬神器;神器皆有定義。
    (法師公會 mg5 改授永久『大法師通悟』誓福〔+10% 法術威力〕而非神器 → 見下測。)"""
    gd, _ = _char()
    reg = {**gd.weapons, **gd.armor, **gd.items}
    arts = {"fg7": "valor_blade", "tg5": "gray_fox_mask",
            "db6": "blade_of_woe", "kn6": "crusaders_ward", "companions6": "wuuthrad"}
    for qid, art in arts.items():
        assert art in reg, f"神器未定義:{art}"
        for b in gd.quests[qid]["branches"]:
            assert art in b.get("reward", {}).get("items", []), f"{qid} 某 branch 未授予 {art}"


def test_mages_guild_capstone_grants_spell_power_boon():
    """法師公會壓軸 mg5(首席法師)兩條 branch 皆授予『大法師通悟』誓福(+10% 法術威力),
    不再給馬格努斯之杖(改由 R78 奧術試煉合體王頂點 trial_fused 提供)。"""
    gd, _ = _char()
    boon = gd.boons["archmage_insight"]
    assert boon.get("spell_power") == 0.1
    for b in gd.quests["mg5"]["branches"]:
        r = b.get("reward", {})
        assert r.get("grant_boon") == "archmage_insight", "mg5 某 branch 未授予大法師通悟誓福"
        assert "staff_of_magnus" not in r.get("items", []), "mg5 不應再給馬格努斯之杖"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_guild_depth OK")
