"""R100 玩家雙面間諜(臥底)系統回歸測試 —— Phase 1 機制核心。

涵蓋:① 非臥底時全 no-op(sim byte-identical 之本)② 入局設值 ③ 掩護抑制 B 敵意 + B NPC 相認
+ 零戰鬥 perk ④ secrecy 每日衰減 ratchet + 歸零/逾期曝光 + 曝光後 B 自動敵視(R96)⑤ 知情者
選定(現有具名 B NPC·排除 murdered·優先省)⑥ 殺知情者滅口(victory→保住 / fled_enemy→曝光)
⑦ 忠誠漂移閾(叛變/抽身)⑧ 叛變棄 A 入 B ⑨ run_battle flee_after_rounds 預設 None 不擾既有。

🔴 零戰鬥面狀態 → 不碰 combat/formulas → sim_assassin byte-identical(刺客 cover_guild=="")。
"""

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import undercover, factions, dialogue


def _mk(**fac):
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = dict(fac) or {"thieves_guild": 3}
    return gd, c


def _state(c):
    return GameState(player=c, time=GameTime(), rng=RNG(1))


def _infiltrate(gd, c, *, a="thieves_guild", b="fighters_guild"):
    st = _state(c)
    undercover.infiltrate(c, st, gd, true_guild=a, cover_guild=b)
    return st


# ---------------------------------------------------------------- no-op (byte-identical 之本)
def test_noop_when_not_undercover():
    gd, c = _mk()
    st = _state(c)
    assert not undercover.on_mission(c)
    assert undercover.update(st, gd) == []
    assert undercover.legacy_label(c) is None
    assert undercover.pick_knower(c, gd) is None


# ---------------------------------------------------------------- 入局 + 掩護
def test_infiltrate_sets_state():
    gd, c = _mk()
    _infiltrate(gd, c)
    assert undercover.on_mission(c)
    assert c.cover_guild == "fighters_guild" and c.cover_true_guild == "thieves_guild"
    assert c.cover_secrecy == undercover.SECRECY_START and c.cover_loyalty == 0
    assert undercover.legacy_label(c) == "雙面間諜"


def test_cover_suppresses_hostility_and_grants_recognition():
    gd, c = _mk()
    # 入局前:身為盜賊(戰士公會宿敵)→ 戰士公會敵視你
    assert factions.faction_hostility(c, gd, "fighters_guild") > 0
    _infiltrate(gd, c)
    assert factions.faction_hostility(c, gd, "fighters_guild") == 0   # 掩護期不敵視
    fnpc = next(n for n, v in gd.npcs.items() if v.get("guild") == "fighters_guild")
    assert dialogue.attitude(c, _state(c), gd, fnpc) == "comrade"     # B NPC 認你為自己人


def test_cover_grants_no_combat_perk():
    """🔴 掩護期 B 不入 char.factions → perk_value(B)=0 → 零戰鬥 perk。"""
    gd, c = _mk()
    _infiltrate(gd, c)
    assert factions.perk_value(c, gd, "fighters_guild") == 0.0
    assert "fighters_guild" not in c.factions          # 絕不寫進 factions(保 R96 互斥)


# ---------------------------------------------------------------- secrecy 衰減 + 曝光
def test_secrecy_daily_decay_ratchet():
    gd, c = _mk()
    st = _infiltrate(gd, c)
    st.time.advance(24 * 5)
    undercover.update(st, gd)
    assert c.cover_secrecy == undercover.SECRECY_START - 5 * undercover.SECRECY_DAILY_DECAY
    undercover.update(st, gd)                            # 同日再 update → ratchet 不重複扣
    assert c.cover_secrecy == undercover.SECRECY_START - 5 * undercover.SECRECY_DAILY_DECAY


def test_secrecy_zero_exposes_and_b_turns_hostile():
    gd, c = _mk()
    st = _infiltrate(gd, c)
    st.time.advance(24 * 40)                             # 遠超 secrecy 見底
    evs = undercover.update(st, gd)
    assert any(e["kind"] == "exposed" for e in evs)
    assert not undercover.on_mission(c)                  # 掩護瓦解
    assert any("cover_blown" in f for f in c.world_events_fired)   # 永久死局旗標
    assert factions.faction_hostility(c, gd, "fighters_guild") > 0  # 仍是盜賊 → B 自動恢復敵視


def test_knower_deadline_exposes():
    gd, c = _mk()
    st = _infiltrate(gd, c)
    undercover.assign_knower(c, st, "bruma_legion_veteran_brand")
    assert c.cover_knower and c.cover_knower_deadline > 0
    st.time.advance(24 * (undercover.KNOWER_GRACE_DAYS + 1))
    evs = undercover.update(st, gd)
    assert any(e["kind"] == "exposed" for e in evs) and not undercover.on_mission(c)


# ---------------------------------------------------------------- 知情者選定
def test_pick_knower_is_existing_named_b_npc():
    gd, c = _mk()
    _infiltrate(gd, c)
    k = undercover.pick_knower(c, gd)
    assert k in gd.npcs and gd.npcs[k]["guild"] == "fighters_guild"


def test_pick_knower_excludes_murdered_and_prefers_province():
    gd, c = _mk()
    _infiltrate(gd, c)
    fnpcs = [n for n, v in gd.npcs.items() if v.get("guild") == "fighters_guild"]
    c.murdered_npcs = list(fnpcs[:-1])                   # 殺掉除一名外的所有戰士 NPC
    assert undercover.pick_knower(c, gd) == fnpcs[-1]    # 只剩可選那名
    # 省偏好:指定某 B NPC 所在省 → 回該省的 B NPC
    target = fnpcs[-1]
    prov = gd.location(gd.npcs[target]["location"])["province"]
    assert gd.location(gd.npcs[undercover.pick_knower(c, gd, province=prov)]["location"])["province"] == prov


# ---------------------------------------------------------------- 殺知情者滅口(patch run_battle)
def test_silence_victory_holds_cover():
    gd, c = _mk()
    st = _infiltrate(gd, c)
    c.cover_secrecy = 10
    undercover.assign_knower(c, st, "bruma_legion_veteran_brand")
    inf0 = c.infamy
    orb, omsg = main.run_battle, main.ui.message
    main.run_battle = lambda *a, **k: "victory"
    main.ui.message = lambda *a, **k: None
    try:
        res = main._undercover_silence(st, gd, "bruma_legion_veteran_brand")
    finally:
        main.run_battle, main.ui.message = orb, omsg
    assert res is None
    assert undercover.on_mission(c)                      # 掩護保住
    assert c.cover_secrecy == undercover.SILENCE_SECRECY_FLOOR and c.cover_knower == ""
    assert c.infamy == inf0 + undercover.SILENCE_INFAMY
    assert "bruma_legion_veteran_brand" in c.murdered_npcs


def test_silence_fled_enemy_exposes():
    gd, c = _mk()
    st = _infiltrate(gd, c)
    undercover.assign_knower(c, st, "bruma_legion_veteran_brand")
    orb, omsg = main.run_battle, main.ui.message
    main.run_battle = lambda *a, **k: "fled_enemy"       # 限時決鬥未殺 → 脫逃
    main.ui.message = lambda *a, **k: None
    try:
        main._undercover_silence(st, gd, "bruma_legion_veteran_brand")
    finally:
        main.run_battle, main.ui.message = orb, omsg
    assert not undercover.on_mission(c)                  # 曝光
    assert any("cover_blown" in f for f in c.world_events_fired)


# ---------------------------------------------------------------- 忠誠漂移 + 結局
def test_loyalty_thresholds():
    gd, c = _mk()
    _infiltrate(gd, c)
    undercover.apply_cover_deltas(c, loyalty_delta=undercover.LOYALTY_DEFECT)
    assert undercover.defection_unlocked(c) and not undercover.extraction_unlocked(c)
    undercover.apply_cover_deltas(c, loyalty_delta=-undercover.LOYALTY_DEFECT)   # 回中性
    assert undercover.extraction_unlocked(c)             # loyalty<=0


def test_apply_cover_deltas_noop_when_not_undercover():
    gd, c = _mk()
    undercover.apply_cover_deltas(c, loyalty_delta=50, secrecy_delta=50)
    assert c.cover_loyalty == 0 and c.cover_secrecy == 0


def test_defect_flips_allegiance():
    gd, c = _mk()
    _infiltrate(gd, c)
    undercover.defect(c, gd)
    assert "thieves_guild" not in c.factions             # 棄 A
    assert c.factions.get("fighters_guild") == 0          # 真入 B(rank0)
    assert not undercover.on_mission(c)


def test_clear_cover_resets():
    gd, c = _mk()
    _infiltrate(gd, c)
    undercover.clear_cover(c)
    assert not undercover.on_mission(c) and c.cover_secrecy == 0 and c.cover_knower == ""
    assert "thieves_guild" in c.factions                  # 抽身留在 A


# ---------------------------------------------------------------- run_battle flee 預設安全
def test_run_battle_flee_param_default_none():
    import inspect
    sig = inspect.signature(main.run_battle)
    assert sig.parameters["flee_after_rounds"].default is None   # 預設 None → 既有戰鬥逐位元組同


# ---------------------------------------------------------------- P2 入局 + 漂移任務
def test_can_infiltrate_gate():
    gd, c = _mk(thieves_guild=undercover.INFILTRATE_RANK)
    assert undercover.can_infiltrate(c, gd, "thieves_guild")       # 達階 → 可入局
    c.factions = {"thieves_guild": undercover.INFILTRATE_RANK - 1}
    assert not undercover.can_infiltrate(c, gd, "thieves_guild")   # 未達階
    c.factions = {}                                                # 非會員
    assert not undercover.can_infiltrate(c, gd, "thieves_guild")
    c.factions = {"fighters_guild": 3}                            # 非犯罪公會(非 A)→ 無 INFILTRATE_PAIRS
    assert not undercover.can_infiltrate(c, gd, "fighters_guild")
    # 已曝光該對 → 永久死局,不可再潛
    c.factions = {"thieves_guild": 3}
    c.world_events_fired.append(undercover.cover_blown_flag("thieves_guild", "fighters_guild"))
    assert not undercover.can_infiltrate(c, gd, "thieves_guild")


def test_drift_quests_gated_by_cover():
    from tesrpg.systems import quests
    gd, c = _mk(thieves_guild=3)
    assert quests.available_quests(c, gd, "undercover") == []      # 未臥底 → 無潛入任務
    _infiltrate(gd, c)                                             # 掩護 fighters
    av = quests.available_quests(c, gd, "undercover")
    assert "ucov_fighters_prove" in av and "ucov_fighters_sabotage" in av
    assert not any("knights" in q for q in av)                     # 他會潛入任務不洩漏


def test_cover_deltas_applied_on_complete():
    from tesrpg.systems import quests
    gd, c = _mk(thieves_guild=3)
    _infiltrate(gd, c)
    quests.accept_quest(c, gd, "ucov_fighters_prove")
    quests._complete(c, gd, "ucov_fighters_prove")
    assert c.cover_loyalty == 20                                   # 取信於敵 → loyalty 升
    quests.accept_quest(c, gd, "ucov_fighters_sabotage")
    s0 = c.cover_secrecy
    quests._complete(c, gd, "ucov_fighters_sabotage")
    assert c.cover_loyalty == 0 and c.cover_secrecy == s0 - 15     # 破壞 → loyalty 降·secrecy 降


def test_infiltrate_via_hall():
    gd, c = _mk(thieves_guild=3)
    c.location_id = "riften"
    st = _state(c)
    seq = iter(["infiltrate", None])
    om, omsg = main.ui.menu, main.ui.message
    main.ui.menu = lambda *a, **k: next(seq, None)
    main.ui.message = lambda *a, **k: None
    try:
        main._undercover_hall(st, gd, "thieves_guild")
    finally:
        main.ui.menu, main.ui.message = om, omsg
    assert undercover.on_mission(c) and c.cover_guild == "fighters_guild"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_undercover")
