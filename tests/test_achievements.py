"""成就(Achievements)單元測試。

涵蓋:各 cond.type 判定、初生角色幾乎零達成、出貨 id 合法、未知 type inert、
傳奇結算整合(列出但不加分)、評估器唯讀(零 char 變動)、earned/locked 配對。
"""

import copy

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import achievements, inventory, legacy, mastery


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="A", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, c


def _ids(gd, c):
    return {a["id"] for a in achievements.earned(c, gd)}


def test_kills_total_and_kill_boss():
    gd, c = _char()
    assert "first_blood" not in _ids(gd, c)
    c.kill_counts = {"bandit": 50}
    assert "first_blood" in _ids(gd, c) and "slayer" not in _ids(gd, c)
    c.kill_counts = {"bandit": 500}
    assert "slayer" in _ids(gd, c)
    assert "ancient_dragon" in gd.bestiary
    c.kill_counts = {"ancient_dragon": 1}
    assert "dragonslayer" in _ids(gd, c)


def test_progress_counters():
    gd, c = _char()
    c.cleared_dungeons = list(range(10))
    assert "delver" in _ids(gd, c)
    c.completed_quests = list(range(30))
    assert "questmaster" in _ids(gd, c)
    c.level = 20
    assert "veteran_hero" in _ids(gd, c)
    c.gold = 50000
    assert "magnate" in _ids(gd, c)
    c.murders = 10
    assert "bloodprice" in _ids(gd, c)


def test_provinces_and_landmarks():
    gd, c = _char()
    locs = gd.world["locations"]
    by_prov = {}
    for lid, l in locs.items():
        by_prov.setdefault(l["province"], lid)
    c.visited_locations = list(by_prov.values())[:4]
    assert "wayfarer" in _ids(gd, c)
    c.discovered_landmarks = list(gd.landmarks.keys())[:8] + ["bogus_landmark"]   # 毀損 id 不計
    assert "cartographer" in _ids(gd, c)


def test_skill_cap_uses_base_only():
    gd, c = _char()
    for s in ("blade", "block", "heavy_armor"):
        c.skills[s] = 100
    assert "grandmaster_skill" in _ids(gd, c)
    # 裝備疊加不算(只認 base):一項 base 退回 99 即不達 3 項
    c.skills["blade"] = 99
    c.equip_skill_bonus = {"blade": 5}     # 有效 104 但 base 99
    assert "grandmaster_skill" not in _ids(gd, c)


def test_guildmaster_any_and_specific():
    gd, c = _char()
    assert "guildmaster" not in _ids(gd, c)
    c.factions["mages_guild"] = len(gd.factions["mages_guild"]["ranks"]) - 1
    ids = _ids(gd, c)
    assert "guildmaster" in ids and "archmage" in ids and "listener" not in ids
    c.factions["dark_brotherhood"] = len(gd.factions["dark_brotherhood"]["ranks"]) - 1
    assert "listener" in _ids(gd, c)


def test_mastery_count():
    """milestone_walker 計『已選』里程碑數(count=12)。
    🔴 回歸守門:創角主修起始 30-40 ≥ 首階門檻 25 → 白送 7 個里程碑可選;選 4 個(舊 count)
    不該達成,須真投資到 12 個才達標(否則一開局即達成)。"""
    gd, c = _char()
    for s in ("block", "heavy_armor", "destruction", "security", "blade", "sneak"):
        c.skills[s] = 100   # 練滿數技 → 解鎖大量 _25/_50/_75/_100 節點
    reached = [n for n in mastery._nodes(gd) if mastery._node_reached(c, n)]
    chosen = 0
    for n in reached:
        if mastery.choose(c, gd, n["id"], n["options"][0]["opt_id"]):
            chosen += 1
        if chosen == 4:
            assert "milestone_walker" not in _ids(gd, c)   # 選 4 個(含創角白送)不達成
        if chosen >= 12:
            break
    assert chosen >= 12
    assert "milestone_walker" in _ids(gd, c)               # 滿 12 個 → 達成


def test_milestone_walker_not_earned_at_creation():
    """🔴 核心回歸:即使把創角白送的 7 個里程碑全選滿,也不該得 milestone_walker(7 < 12)。"""
    gd, c = _char()
    pend = [n for n in mastery._nodes(gd)
            if mastery._node_reached(c, n) and n["id"] not in (c.mastery_choices or {})]
    for n in pend:
        mastery.choose(c, gd, n["id"], n["options"][0]["opt_id"])
    assert len(mastery.unlocked(c, gd)) <= 7                # 創角白送上限 = 7 個主修 _25
    assert "milestone_walker" not in _ids(gd, c)


def test_dominion_allegiance_vampire():
    gd, c = _char()
    c.thaneships = ["bruma", "kvatch"]
    assert "thane" in _ids(gd, c)
    c.allegiance = "own"
    assert "self_made_king" in _ids(gd, c)
    c.city_faction = {"bruma": "own", "kvatch": "own", "chorrol": "own"}
    assert "warlord" in _ids(gd, c)
    c.is_vampire = True
    assert "child_of_night" in _ids(gd, c)


def test_pure_spec_not_trivially_earned():
    """初生角色雖有起始專精偏向,但未達絕對門檻 → 不該得『純粹流派』。"""
    gd, c = _char()
    assert not ({"purist_warrior", "purist_mage", "purist_thief"} & _ids(gd, c))
    for s in gd.skills_by_spec("combat"):
        c.skills[s] = 100
    for s in list(gd.skills_by_spec("magic")) + list(gd.skills_by_spec("stealth")):
        c.skills[s] = 5
    assert "purist_warrior" in _ids(gd, c)


def test_fresh_character_earns_none():
    gd, c = _char()
    assert achievements.earned(c, gd) == []


# --- R55 後期成就(新 cond.type,複用既有 accessor)-----------------------
def test_boons_count():
    gd, c = _char()
    c.boons = ["azura", "hircine_blessing", "boethiah_resolve", "meridia_light",
               "namira_decay", "nocturnal_shadow", "jyggalag_order"]            # 7 個
    assert "prince_favored" not in _ids(gd, c)
    c.boons = c.boons + ["hermaeus_magic"]                                      # 8 個
    assert "prince_favored" in _ids(gd, c) and "prince_chosen" not in _ids(gd, c)
    c.boons = c.boons + ["sanguine_revel", "malacath_might", "vaermina_nightmare",
                         "peryite_ward", "clavicus_silver_tongue", "molag_defiance",
                         "sheogorath_madness"]                                  # 15 個
    assert "prince_chosen" in _ids(gd, c)


def test_faction_rank():
    gd, c = _char()
    c.factions["coven_vampire"] = 3
    assert "blood_matron" not in _ids(gd, c)                                   # 血裔(index 3)未達頂階
    c.factions["coven_vampire"] = 5
    assert "blood_matron" in _ids(gd, c)                                       # 血主(index 5,R160 修)
    c.factions["werewolf_pack"] = 5
    assert "alpha_wolf" in _ids(gd, c)
    c.factions["dark_brotherhood"] = 3
    assert "silencer" not in _ids(gd, c)                                       # rank 4 才是沉默者
    c.factions["dark_brotherhood"] = 4
    assert "silencer" in _ids(gd, c)


def test_disease_achievements():
    gd, c = _char()
    assert "afflicted" not in _ids(gd, c)
    c.diseases = [{"id": "rockjoint"}]
    assert "afflicted" in _ids(gd, c) and "pestilent" not in _ids(gd, c)
    c.diseases = [{"id": "rockjoint"}, {"id": "witbane"}, {"id": "ataxia"}]
    assert "pestilent" in _ids(gd, c)


def test_soul_gems_filled():
    gd, c = _char()
    inventory.add_item(c, "filled_petty_soul_gem", 4)
    assert "soul_collector" not in _ids(gd, c)                                 # 4 顆不足
    inventory.add_item(c, "filled_petty_soul_gem", 1)                          # 同型堆成一格、qty=5
    assert "soul_collector" in _ids(gd, c)                                     # qty 加總計顆數,非堆疊數


def test_soul_gems_filled_handles_corrupt_inventory():
    """毀損存檔:背包含未知 item id → 求值不崩潰(achievements 鐵律「缺漏/空欄位安全」,同 R47)。"""
    gd, c = _char()
    c.inventory = [{"id": "filled_petty_soul_gem", "qty": 5}, {"id": "BOGUS_ITEM_ID", "qty": 1}]
    assert "soul_collector" in _ids(gd, c)        # 未知 id 安全略過、有效魂石照計
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    achievements.seed_seen(c, gd)                 # 載入鉤不崩
    achievements.update(st, gd, set())            # 迴圈鉤不崩


def test_prince_boss_kills():
    gd, c = _char()
    assert "malyn_varen" in gd.bestiary and "apocrypha_seeker" in gd.bestiary
    c.kill_counts = {"malyn_varen": 1}
    assert "star_breaker" in _ids(gd, c) and "forbidden_bane" not in _ids(gd, c)
    c.kill_counts = {"apocrypha_seeker": 1}
    assert "forbidden_bane" in _ids(gd, c)


def test_new_types_implemented():
    for t in ("boons_count", "faction_rank", "disease_count", "soul_gems_filled",
              "boons_source", "loyalty_arcs", "world_event"):
        assert t in achievements._IMPLEMENTED_TYPES
    # 新成就全通過 _defs 過濾(非靜默消失)
    gd = get_gamedata()
    ids = {a["id"] for a in achievements._defs(gd)}
    for aid in ("prince_favored", "blood_matron", "afflicted", "soul_collector", "star_breaker",
                "divine_pilgrim", "divine_chosen", "crisis_ender", "loyal_bond"):
        assert aid in ids


# --- R160 名人堂批次:誓福按來源 / 忠誠弧 / 修 curse-rank 回歸 ------------
def test_boons_source_divine_and_daedric():
    """boons_source:按來源集齊(divine all / count·daedric count),來源集由 boons.json source 派生。"""
    from tesrpg.systems import boons as boonsys
    gd, c = _char()
    divine = [bid for bid, b in gd.boons.items() if b.get("source") == "divine"]
    daedric = [bid for bid, b in gd.boons.items() if b.get("source") == "daedric"]
    assert len(divine) == 9, f"divine 誓福應恰 9(對應九神試煉):{len(divine)}"
    assert len(daedric) >= 15, f"daedric 誓福應 ≥15(15 親王 + 3 莫拉書):{len(daedric)}"
    assert "divine_pilgrim" not in _ids(gd, c)
    for bid in divine[:3]:
        boonsys.grant(c, gd, bid)
    assert "divine_pilgrim" in _ids(gd, c) and "divine_chosen" not in _ids(gd, c)   # 3 → pilgrim,未全
    for bid in divine[3:]:
        boonsys.grant(c, gd, bid)
    assert "divine_chosen" in _ids(gd, c)                                            # 全 9 → all
    # daedric count 門檻(prince_favored 8 / prince_chosen 15;retarget 自 boons_count → 名符其實)
    gd2, c2 = _char()
    for bid in daedric[:8]:
        boonsys.grant(c2, gd2, bid)
    assert "prince_favored" in _ids(gd2, c2) and "prince_chosen" not in _ids(gd2, c2)


def test_boons_source_ignores_other_categories():
    """divine 成就不被非 divine 誓福(guild/undercover/…)滿足 → source 篩選正確。"""
    from tesrpg.systems import boons as boonsys
    gd, c = _char()
    non_divine = [bid for bid, b in gd.boons.items() if b.get("source") != "divine"][:5]
    for bid in non_divine:
        boonsys.grant(c, gd, bid)
    assert "divine_pilgrim" not in _ids(gd, c)   # 5 個非 divine 誓福 ≠ 3 divine


def test_loyalty_arcs_achievement_is_monotonic():
    """loyalty_arcs:數 completed_quests 內的同伴 personal_quest(曾完成即算,遣散不失效 → 成就單調)。"""
    gd, c = _char()
    assert "loyal_bond" not in _ids(gd, c)                     # 無完成任何弧 → 0
    cand = next((cid for cid, cd in gd.companions.items()
                 if isinstance(cd, dict) and cd.get("personal_quest")), None)
    assert cand is not None, "資料應有具名弧同伴"
    c.completed_quests = [gd.companions[cand]["personal_quest"]]
    c.companions = []                                          # 🔴 同伴已遣散 → 仍應保有成就(單調)
    assert "loyal_bond" in _ids(gd, c)


def test_world_event_crisis_ender_both_endings():
    """crisis_ender 走 world_event(oblivion_crisis_ended)→ 雙結局(救世/墮落)皆設此旗 → 兩通路公平。"""
    gd, c = _char()
    assert "crisis_ender" not in _ids(gd, c)
    c.world_events_fired = ["oblivion_crisis_ended"]           # 兩條主線結局皆設此旗(quests.json:4051/4091)
    assert "crisis_ender" in _ids(gd, c)


def test_curse_rank_top_requires_rank_5_r160():
    """修 R57 回歸:血主/頭狼在頂階 index 5(非 3);rank 3(血裔/月牙)不再誤授頂階成就。"""
    gd, c = _char()
    for fid, aid in (("coven_vampire", "blood_matron"), ("werewolf_pack", "alpha_wolf")):
        top = len(gd.factions[fid]["ranks"]) - 1
        assert top == 5, f"{fid} 頂階 index 應為 5:{top}"
        c.factions[fid] = 3
        assert aid not in _ids(gd, c), f"rank 3 不應授 {aid}(R57 回歸修復)"
        c.factions[fid] = 5
        assert aid in _ids(gd, c)
        del c.factions[fid]


def test_all_boons_have_valid_source_r160():
    """boons.json 每筆誓福皆有合法 source(自我文件化 + 讓 boons_source 成就防陳舊);
    boons_source 成就引用的 source 須真實存在於註冊表(否則永不可達)。"""
    gd = get_gamedata()
    valid = {"divine", "daedric", "guild", "undercover", "main", "arcane"}
    for bid, b in gd.boons.items():
        assert b.get("source") in valid, f"誓福 {bid} 缺合法 source:{b.get('source')}"
    for a in gd.achievements:
        if a["cond"]["type"] == "boons_source":
            src = a["cond"]["source"]
            assert any(b.get("source") == src for b in gd.boons.values()), \
                f"成就 {a['id']} 的 source={src} 無任何誓福 → 永不可達"


# --- R55 首達通知(零存檔欄,session 暫態去重)----------------------------
def test_first_earned_notification_once():
    gd, c = _char()
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    seen = achievements.seed_seen(c, gd)                  # 初生:近乎空
    c.gold = 50000
    evs = achievements.update(st, gd, seen)
    assert any(e["id"] == "magnate" for e in evs)         # 首次達成 → 報一次
    evs2 = achievements.update(st, gd, seen)
    assert all(e["id"] != "magnate" for e in evs2)        # 同 session 不重報


def test_seed_suppresses_already_earned():
    gd, c = _char(gold=50000)                             # 載入當下已達成
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    seen = achievements.seed_seen(c, gd)                  # magnate 已在 seed
    assert "magnate" in seen
    evs = achievements.update(st, gd, seen)
    assert all(e["id"] != "magnate" for e in evs)         # 重載不重報既得成就


def test_update_is_read_only():
    gd, c = _char(gold=50000, level=20)
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    snapshot = copy.deepcopy(c.to_dict())
    achievements.update(st, gd, set())
    assert c.to_dict() == snapshot                        # update 純讀(只動呼叫端 seen)


def test_shipped_ids_are_legal():
    gd = get_gamedata()
    for a in gd.achievements:
        t = a["cond"]["type"]
        assert t in achievements._IMPLEMENTED_TYPES, f"未實作的 type:{t}"
        assert a.get("id") and a.get("name") and a.get("desc")
        if t == "kill_boss":
            assert a["cond"]["creature"] in gd.bestiary, a["cond"]["creature"]
        if t in ("guildmaster", "faction_rank"):
            assert a["cond"]["faction"] in gd.factions, a["cond"]["faction"]
        if t == "allegiance":
            assert a["cond"]["cause"] in {"imperial", "independent", "own"}
        if t == "pure_spec":
            assert a["cond"]["spec"] in {"combat", "magic", "stealth"}
        if t == "boons_source":
            assert any(b.get("source") == a["cond"]["source"] for b in gd.boons.values()), a["cond"]["source"]
            assert a["cond"].get("all") or isinstance(a["cond"].get("count"), int)
        if t == "loyalty_arcs":
            assert isinstance(a["cond"]["count"], int) and a["cond"]["count"] >= 1
        if t == "world_event":
            assert isinstance(a["cond"]["event"], str) and a["cond"]["event"]
    ids = [a["id"] for a in gd.achievements]
    assert len(ids) == len(set(ids)), "成就 id 重複"


def test_unimplemented_type_is_inert():
    gd, c = _char()
    bogus = {"id": "x", "name": "幻", "desc": "?", "cond": {"type": "not_real"}}
    gd.achievements.append(bogus)
    try:
        assert all(a["id"] != "x" for a in achievements.earned(c, gd))
        assert all(a["id"] != "x" for a in achievements._defs(gd))
    finally:
        gd.achievements.remove(bogus)


def test_evaluator_is_read_only():
    gd, c = _char(level=20, gold=50000, murders=10)
    c.kill_counts = {"ancient_dragon": 1, "bandit": 500}
    c.factions["mages_guild"] = 5
    snapshot = copy.deepcopy(c.to_dict())
    achievements.earned(c, gd)
    won, locked = achievements.earned_and_locked(c, gd)
    assert c.to_dict() == snapshot
    # 併入 earned/locked 全集無交集分割斷言(唯讀,順序無關);本測 setup 達成多項成就,
    # won 非空 → 首次在 won/locked 兩側皆有元素時驗證分割。
    all_ids = {a["id"] for a in achievements._defs(gd)}
    assert {a["id"] for a in won} | {a["id"] for a in locked} == all_ids
    assert not ({a["id"] for a in won} & {a["id"] for a in locked})


def test_legacy_integration_lists_without_scoring():
    gd, c = _char()
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    base = legacy.compute(st, gd)["score"]
    # murders 是成就條件(血債累累)但**不在 score 公式內** → 達成新成就而 score 不變,
    # 證明成就純表彰、不參與計分(避免雙重計分)。
    c.murders = 10
    out = legacy.compute(st, gd)
    assert "血債累累" in out["achievements"]
    assert out["score"] == base
    assert out["achievements_total"] == len(achievements._defs(gd))
    assert all(isinstance(n, str) for n in out["achievements"])


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_achievements 全通過")
