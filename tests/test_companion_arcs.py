"""同伴角色化(具名招募 / 專屬支線 / 對話 / 忠誠弧頂點)的單元測試。

紅線:頂點皆「盟友限定戰術光環」或「非戰鬥被動」→ 玩家偷襲/solo boss 路徑零位移
(sim_assassin 另行覆核);**零新存檔欄位** —— 解鎖/弧完成/頂點皆由 completed_quests/bond 推導。
"""

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, inventory, party, quests, world


def _setup(cids=()):
    gd = get_gamedata()
    c = build_character(gd, name="L", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    for cid in cids:
        c.companions.append(cid)
    st = GameState(player=c, rng=RNG(1), time=GameTime(hour=12))
    return gd, c, st


def _satisfy(c, gd, obj):
    t = obj["type"]
    if t == "kill":
        c.kill_counts[obj["creature"]] = c.kill_counts.get(obj["creature"], 0) + obj["count"]
    elif t == "reach":
        c.location_id = obj["location"]
    elif t == "clear_dungeon":
        if obj["dungeon"] not in c.cleared_dungeons:
            c.cleared_dungeons.append(obj["dungeon"])
    elif t == "collect":
        inventory.add_item(c, obj["item"], obj["count"])


def _drive_quest(c, gd, qid):
    """接取並逐階滿足目標,推進至完成。"""
    quests.accept_quest(c, gd, qid)
    for _ in range(12):
        if qid in c.completed_quests:
            break
        obj, _, _ = quests.current_objective(c, gd, qid)
        _satisfy(c, gd, obj)
        quests.check_completion(c, gd)
    assert qid in c.completed_quests, f"{qid} 未能推進至完成"


# --- 招募任務授予具名同伴 -------------------------------------------------
def test_recruit_quest_grants_named_companion():
    gd, c, st = _setup()
    assert "drelas" not in c.companions
    _drive_quest(c, gd, "recruit_drelas")
    assert "drelas" in c.companions                      # reward.companion 入夥
    assert "recruit_drelas" in c.completed_quests


def test_recruit_grant_respects_max_party_then_summonable():
    # 隊伍已滿 → 不自動入夥,但 recruit_quest ∈ completed → 可在隊伍選單召集
    gd, c, st = _setup(cids=["sellsword", "shieldmaiden"])
    assert len(c.companions) == party.MAX_PARTY
    _drive_quest(c, gd, "recruit_jarakal")
    assert "ja_rakal" not in c.companions                # 滿員未自動入夥
    assert "ja_rakal" in party.recruited_named(c, gd)    # 已解鎖,待召集
    c.companions.remove("sellsword")                     # 騰出位
    assert "ja_rakal" in party.recruited_named(c, gd)
    c.companions.append("ja_rakal")                      # 召集歸隊
    assert "ja_rakal" not in party.recruited_named(c, gd)  # 在隊 → 不再列為待召集


# --- 專屬支線:羈絆門檻 + 來源隔離 ---------------------------------------
def test_personal_quest_bond_gated():
    gd, c, st = _setup(cids=["sellsword"])
    # arc_sellsword gate=1(同袍);bond 0 → 不可提供
    assert not party.arc_offerable(c, gd, "sellsword")
    c.companion_bond["sellsword"] = party.BOND_TIERS[0]   # 升至 tier 1
    assert party.bond_tier(c, "sellsword") >= 1
    assert party.arc_offerable(c, gd, "sellsword")        # 達門檻 → 可傾聽
    # 已接取 / 已完成 → 不再提供(兩個 early-return 分支;sellsword 仍在 tier1)
    quests.accept_quest(c, gd, "arc_sellsword")
    assert not party.arc_offerable(c, gd, "sellsword")    # 已接取 → 不再提供
    c.quests.pop("arc_sellsword", None)
    c.completed_quests.append("arc_sellsword")
    assert not party.arc_offerable(c, gd, "sellsword")    # 已完成 → 不再提供
    c.completed_quests.remove("arc_sellsword")            # 還原,免污染後段 farkas 場景
    # gate=2 的同伴在 tier 1 仍不可提供
    c.companions.append("farkas"); c.companion_bond["farkas"] = party.BOND_TIERS[0]
    assert not party.arc_offerable(c, gd, "farkas")       # 需 tier 2
    c.companion_bond["farkas"] = party.BOND_TIERS[1]
    assert party.arc_offerable(c, gd, "farkas")


def test_personal_and_recruit_quests_hidden_from_board_and_guild():
    gd, c, st = _setup()
    # available_quests 只用 guild/board → companion/npc 來源的弧與招募皆不洩漏
    board = quests.available_quests(c, gd, "board")
    for fid in ("fighters_guild", "companions", "thieves_guild"):
        c.factions[fid] = 0
        guild = quests.available_quests(c, gd, "guild", fid)
        for qid in ("arc_sellsword", "arc_farkas", "recruit_drelas", "recruit_rashid"):
            assert qid not in guild
    for qid in ("arc_sellsword", "arc_farkas", "recruit_drelas", "recruit_rashid"):
        assert qid not in board


# --- 弧完成:羈絆躍升 + 頂點解鎖 -----------------------------------------
def test_personal_quest_completion_jumps_bond_and_unlocks_capstone():
    gd, c, st = _setup(cids=["sellsword", "rashid"])
    c.companion_bond["sellsword"] = party.BOND_TIERS[0]   # 5
    assert party.active_capstone(c, gd, "sellsword") is None
    _drive_quest(c, gd, "arc_sellsword")
    assert c.companion_bond["sellsword"] == party.BOND_TIERS[0] + 15   # reward.bond 躍升
    assert party.arc_done(c, gd, "sellsword")             # 由 completed_quests 推導
    cap = party.active_capstone(c, gd, "sellsword")
    assert cap and cap["kind"] == "ally_empower"          # 頂點解鎖
    # reward.bond +15 夾 BOND_MAX(起始 BOND_MAX-3 → 不溢位)
    c.companion_bond["rashid"] = party.BOND_MAX - 3
    _drive_quest(c, gd, "arc_rashid")                     # reward.bond +15
    assert c.companion_bond["rashid"] == party.BOND_MAX   # 夾 BOND_MAX


# --- 忠誠頂點:戰術型盟友限定、被動型在隊才生效 -------------------------
def test_tactical_capstone_is_ally_only():
    gd, c, st = _setup(cids=["sellsword", "ranger"])
    c.completed_quests.append("arc_sellsword")            # 弧完成 → 頂點啟用
    ally = combat.spawn_companion(gd, "sellsword", st.rng)
    main._apply_companion_capstone_auras(c, gd, [("sellsword", ally)], [ally])
    assert any(e["kind"] == "empower" and e.get("source") == "capstone:sellsword"
               for e in ally.active_effects)              # 盟友受光環
    assert all(e.get("source") != "capstone:sellsword" for e in c.active_effects)  # 玩家永不受光環
    # 重複套用 → source 去重,不疊加
    main._apply_companion_capstone_auras(c, gd, [("sellsword", ally)], [ally])
    assert sum(1 for e in ally.active_effects if e.get("source") == "capstone:sellsword") == 1
    # 倒下的頂點持有者不發光環(source 第 546-547 行 skip 分支;用新 spawn 單位避免殘留污染)
    holder = combat.spawn_companion(gd, "sellsword", st.rng); holder.health = 0   # 倒下
    other = combat.spawn_companion(gd, "ranger", st.rng)
    main._apply_companion_capstone_auras(c, gd, [("sellsword", holder), ("ranger", other)], [other])
    assert all(e.get("source") != "capstone:sellsword" for e in other.active_effects)  # 倒下者不發光環


def test_passive_capstone_only_when_in_party():
    gd, c, st = _setup(cids=["ja_rakal"])
    c.completed_quests.append("arc_jarakal")              # 巧手(barter)弧完成
    assert party.passive_capstone_factor(c, gd, "barter") > 0
    assert party.passive_capstone_factor(c, gd, "barter") <= party.PASSIVE_CAP["barter"]  # 夾 PASSIVE_CAP
    item = "wolf_pelt"
    sell_with = world.sell_price(c, gd, item)
    c.companions[:] = []                                  # 離隊
    assert party.passive_capstone_factor(c, gd, "barter") == 0   # 離隊即失
    sell_without = world.sell_price(c, gd, item)
    assert sell_with >= sell_without                      # 在隊議價更好(夾限後至少不更差)


def test_all_capstone_kinds_are_red_line_safe():
    """頂點 kind 限定於盟友光環/非戰鬥被動 —— 無任何作用於玩家攻擊的型別。"""
    gd, _ = get_gamedata(), None
    allowed = {"ally_empower", "ally_shield", "ally_regen", "barter", "travel"}
    for cid, c in gd.companions.items():
        cap = c.get("capstone")
        if cap:
            assert cap["kind"] in allowed, f"{cid} 頂點 kind {cap['kind']} 不在盟友限定/被動白名單"


# --- 傳奇 / 存檔 ---------------------------------------------------------
def test_forgotten_merc_arc_bond_not_resurrected():
    """對抗審查破口:泛用傭兵接支線→解散(forget 清羈絆)→隊外完成,不得寫回 orphan 羈絆。"""
    gd, c, st = _setup(cids=["sellsword"])
    c.companion_bond["sellsword"] = party.BOND_TIERS[0]
    quests.accept_quest(c, gd, "arc_sellsword")
    c.companions.remove("sellsword"); party.forget(c, "sellsword")   # 解散傭兵
    for _ in range(12):
        if "arc_sellsword" in c.completed_quests:
            break
        obj, _, _ = quests.current_objective(c, gd, "arc_sellsword")
        _satisfy(c, gd, obj); quests.check_completion(c, gd)
    assert "arc_sellsword" in c.completed_quests
    assert "sellsword" not in c.companion_bond            # 無 orphan 羈絆(再雇=滿血 tier0,破口已堵)


def test_named_companion_arc_bond_applies_even_when_benched():
    """具名同伴(解散保留羈絆)即使暫離隊,完成其支線仍得羈絆躍升。"""
    gd, c, st = _setup()
    c.completed_quests.append("recruit_drelas")           # 已招募解鎖
    c.companion_bond["drelas"] = party.BOND_TIERS[1]
    quests.accept_quest(c, gd, "arc_drelas")
    # drelas 不在隊(待命),但 keeps_state_on_dismiss → 羈絆套用
    assert "drelas" not in c.companions
    for _ in range(12):
        if "arc_drelas" in c.completed_quests:
            break
        obj, _, _ = quests.current_objective(c, gd, "arc_drelas")
        _satisfy(c, gd, obj); quests.check_completion(c, gd)
    assert c.companion_bond["drelas"] == party.BOND_TIERS[1] + 15   # 具名同伴仍得羈絆


def test_ally_shield_capstone_no_dissipation_spam():
    """ally_shield 忠誠頂點每回合刷新,tick_effects 不應誤報「護盾消散了」。"""
    from tesrpg.systems import magic
    gd, c, st = _setup(cids=["farkas"])                   # farkas = ally_shield 頂點
    c.completed_quests.append("arc_farkas")
    ally = combat.spawn_companion(gd, "farkas", st.rng)
    main._apply_companion_capstone_auras(c, gd, [("farkas", ally)], [ally])
    msgs = magic.tick_effects(ally, gd)
    assert "護盾消散了。" not in msgs                       # 常駐光環不報消散(與盾牆/戰旗一致)


def test_legacy_counts_loyalty_arcs():
    gd, c, st = _setup(cids=["sellsword", "farkas"])
    c.completed_quests.extend(["arc_sellsword", "arc_farkas"])
    assert party.loyalty_arcs(c, gd) == ["sellsword", "farkas"]
    label = party.loyalty_label(c, gd)
    assert label and gd.companions["sellsword"]["name"] in label
    from tesrpg.systems import legacy
    res = legacy.compute(st, gd)
    assert res["loyalty"] == label


def test_save_roundtrip_zero_new_fields_derives_state():
    gd, c, st = _setup(cids=["drelas"])
    c.completed_quests.extend(["recruit_drelas", "arc_drelas"])
    c.companion_bond["drelas"] = 30
    # 序列化往返 → 狀態由既有欄位推導,無新欄位
    d = c.to_dict()
    assert "companion_arcs" not in d and "recruited" not in d   # 確未引入新存檔欄
    c2 = Character.from_dict(d)
    assert party.arc_done(c2, gd, "drelas")                     # 弧完成正確推導
    assert party.active_capstone(c2, gd, "drelas")["kind"] == "ally_regen"
    assert c2.companion_bond["drelas"] == 30


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print(f"{__name__} OK")
