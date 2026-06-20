"""血族/獵群任務線深化(R57)單元測試:6 階 5 任務、目標多樣、available_quests 逐階對齊、
偽裝 cuirass 鎖在頂階決鬥、決鬥自動指 rank_quests 末位、獸形 capstone(pack 誓福→爪傷/時程)、存檔相容。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import factions, lycanthropy, quests, vampirism


def _state(seed=1):
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    return gd, c, GameState(player=c, rng=RNG(seed), time=GameTime(hour=12))


# --- 結構:6 階 5 任務、與其他公會齊平 ----------------------------------
def test_both_factions_have_five_rank_quests():
    gd = get_gamedata()
    for fac in ("coven_vampire", "werewolf_pack"):
        f = gd.factions[fac]
        assert len(f["ranks"]) == 6 and len(f["rank_quests"]) == 5      # 4→6 階、3→5 任務
        for i, qid in enumerate(f["rank_quests"]):
            q = gd.quests[qid]
            assert q["faction"] == fac and q["source"] == "guild" and q["rank"] == i   # rank 逐階對齊


def test_objective_variety_and_legal_ids():
    """新任務目標多樣(非全 kill)+ 引用的 dungeon/item id 皆合法。"""
    gd = get_gamedata()
    types = set()
    for fac in ("coven_vampire", "werewolf_pack"):
        for qid in gd.factions[fac]["rank_quests"]:
            q = gd.quests[qid]
            for obj in ([q["objective"]] if "objective" in q else
                        [b["objective"] for b in q.get("branches", []) if "objective" in b]):
                types.add(obj["type"])
                if obj["type"] == "clear_dungeon":
                    assert obj["dungeon"] in gd.dungeons, obj["dungeon"]
                if obj["type"] == "collect":
                    assert gd.item_or_none(obj["item"]), obj["item"]
                if obj["type"] == "kill":
                    assert obj["creature"] in gd.bestiary, obj["creature"]
    assert {"kill", "clear_dungeon", "collect"} <= types                # 至少三種目標型別


# --- available_quests 逐階推進(深化後仍正確篩本階)---------------------
def test_available_quests_walks_the_new_ladder():
    gd, c, st = _state()
    c.is_vampire = True; c.vampire_fed_day = st.time.absolute_hours() // 24
    vampirism.apply_to_character(c, st, gd)
    factions.join(c, "coven_vampire")
    expected = ["coven1", "coven2", "coven_a", "coven_b", "coven3"]
    for rank, qid in enumerate(expected):
        c.factions["coven_vampire"] = rank
        assert quests.available_quests(c, gd, "guild", "coven_vampire") == [qid], rank


# --- 偽裝鎖在頂階決鬥(原始痛點修復)-----------------------------------
def test_disguise_cuirass_only_from_capstone_duel():
    """夜影胸甲(=湊齊偽裝的關鍵件)只在頂階決鬥 coven3 兩分支發放,前期任務拿不到。"""
    gd = get_gamedata()
    def reward_items(q):
        out = list(q.get("reward", {}).get("items", []))
        for b in q.get("branches", []):
            out += b.get("reward", {}).get("items", [])
        return out
    # 前 4 個任務:無 cuirass
    for qid in ("coven1", "coven2", "coven_a", "coven_b"):
        assert "nightshade_cuirass" not in reward_items(gd.quests[qid]), qid
    # 頂階決鬥:兩分支皆給 cuirass
    cap = gd.quests["coven3"]
    assert all("nightshade_cuirass" in b["reward"].get("items", []) for b in cap["branches"])
    # 其餘三件散在 rank 0-2
    early = reward_items(gd.quests["coven1"]) + reward_items(gd.quests["coven2"]) + reward_items(gd.quests["coven_a"])
    assert {"nightshade_hood", "nightshade_gloves", "nightshade_boots"} <= set(early)


# --- 頂階決鬥自動指 rank_quests 末位(零 UI 改)------------------------
def test_capstone_duel_is_last_rank_quest_and_kill():
    gd = get_gamedata()
    for fac in ("coven_vampire", "werewolf_pack"):
        cap = gd.factions[fac]["rank_quests"][-1]            # _lair_pending_duel 讀末位
        q = gd.quests[cap]
        assert q["rank"] == len(gd.factions[fac]["ranks"]) - 2   # 倒數第二階(決鬥後晉頂)
        assert all(b["objective"]["type"] == "kill" for b in q["branches"])   # 決鬥須 kill


# --- 獸形強化 capstone(複用 pack_heir/usurper 誓福)-------------------
def test_pack_capstone_boosts_beast_form():
    gd, c, st = _state()
    lycanthropy.contract(c, st, gd)
    claw0 = lycanthropy.claw_bonus(c)
    dur0 = lycanthropy.effective_duration(c, st, gd)
    c.boons = ["pack_usurper"]                                # 頂階獸形 capstone
    assert lycanthropy.claw_bonus(c) == claw0 + lycanthropy.ALPHA_BLOOD_CLAW
    assert lycanthropy.effective_duration(c, st, gd) == dur0 + lycanthropy.ALPHA_BLOOD_DURATION
    c.boons = ["pack_heir"]                                   # 另一分支誓福亦觸發
    assert lycanthropy.claw_bonus(c) == claw0 + lycanthropy.ALPHA_BLOOD_CLAW
    c.boons = ["azura"]                                       # 無關誓福 → 不觸發
    assert lycanthropy.claw_bonus(c) == claw0


def test_old_save_with_accepted_capstone_self_heals():
    """存檔相容(對抗審查覆核):舊存檔停在舊頂階 rank 2 且已 accept 舊 coven3(當時 rank 2)→
    改版後 coven3.rank=4,該玩家在 rank 2 仍能接新 coven_a、爬到 rank 4 後舊 coven3 自然生效 → 不卡死。"""
    gd, c, st = _state()
    c.is_vampire = True; c.vampire_fed_day = st.time.absolute_hours() // 24
    vampirism.apply_to_character(c, st, gd)
    factions.join(c, "coven_vampire")
    c.factions["coven_vampire"] = 2                       # 舊存檔:停在舊頂階 rank 2
    quests.accept_quest(c, gd, "coven3", branch=0)        # 且已接受舊 coven3(當時 rank 2 決鬥)
    # 仍能走新階梯(coven3 active 不擋 coven_a)
    assert quests.available_quests(c, gd, "guild", "coven_vampire") == ["coven_a"]
    quests.accept_quest(c, gd, "coven_a")
    c.cleared_dungeons = list(getattr(c, "cleared_dungeons", [])) + ["moonlit_grove"]
    quests.check_completion(c, gd)                        # → rank 3
    quests.accept_quest(c, gd, "coven_b")
    from tesrpg.systems import inventory
    inventory.add_item(c, "vampire_dust", 4)
    quests.check_completion(c, gd)                        # → rank 4
    assert factions.rank_index(c, "coven_vampire") == 4
    quests.record_kill(c, "coven_patriarch")             # 舊 coven3 在 rank 4 自然生效
    quests.check_completion(c, gd)
    assert factions.rank_index(c, "coven_vampire") == 5  # 自癒到頂階,不永久卡死


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_curse_quest_depth")
