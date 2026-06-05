"""practice 成本回歸測試:行竊/撬鎖/說服接上各技能 practice 的「體力 + 時間」成本。

守住「不准零風險刷技能」的反 min-max 紅線(原本三者都繞過了正規訓練代價):
- progression.practice_cost 共用 data/skills.json 的 practice 價碼(與訓練師 action_practice 一致)。
- 行竊「得手才給潛行 xp」(被抓不給 → 杜絕「故意被抓刷潛行」)。
- 撬鎖每次擲骰付體力 + 時間;「塔之鑰」招牌仍免成本、免耗時。
- 說服每次付體力 + 時間,連「辯舌·折服」必成路徑也照付(非免費必成)。

每條都可反向驗證:還原修改前的程式碼會因缺 hours/tired 鍵或被抓仍給 xp 而紅。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import crime, dialogue, dungeon, progression


def _char(**skills):
    gd = get_gamedata()
    c = build_character(gd, name="P", sex="male", race="imperial",
                        birthsign="warrior", class_id="thief")
    for k, v in skills.items():
        c.skills[k] = v
    return gd, c


# --- practice_cost 共用扣費 -------------------------------------------
def test_practice_cost_deducts_fatigue_and_matches_skills_json():
    gd, c = _char()
    pdef = gd.skills["security"]["practice"]
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    xp, hours, tired = progression.practice_cost(c, gd, "security")
    assert not tired
    assert xp == pdef["xp"]                       # 體力充足:全額 xp(單一真實來源)
    assert hours == pdef["hours"]
    assert c.fatigue == f0 - pdef["fatigue"]      # 確實扣體力


def test_practice_cost_tired_halves_xp_and_clamps():
    gd, c = _char()
    pdef = gd.skills["speechcraft"]["practice"]
    c.fatigue = pdef["fatigue"] - 1               # 低於門檻 → 累
    xp, hours, tired = progression.practice_cost(c, gd, "speechcraft")
    assert tired and xp == pdef["xp"] * 0.5
    assert c.fatigue == 0                          # 夾在 0,不為負


# --- 行竊:得手才學藝(杜絕故意被抓刷潛行)---------------------------
def test_steal_xp_only_on_success():
    gd, c = _char(sneak=10, security=10)           # 得手率約 33% → 兩種結果都會出現
    saw_caught = saw_success = False
    for i in range(30):
        c.fatigue = c.max_fatigue                  # 排除 tired 干擾,專測「被抓不給 xp」
        before = c.skill_xp.get("sneak", 0.0)
        lvl_before = c.skills["sneak"]
        r = crime.steal_item(c, gd, "iron_sword", RNG(i))
        after = c.skill_xp.get("sneak", 0.0)
        if r["caught"]:
            saw_caught = True
            assert r["skill_events"] == []
            assert after == before and c.skills["sneak"] == lvl_before  # 被抓不學藝
        else:
            saw_success = True
            assert after > before or c.skills["sneak"] > lvl_before     # 得手才長技能
    assert saw_caught and saw_success


def test_steal_costs_fatigue_and_returns_time():
    gd, c = _char(sneak=100, security=100)          # 幾乎必得手
    pdef = gd.skills["sneak"]["practice"]
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    r = crime.steal_item(c, gd, "iron_sword", RNG(0))
    assert r["ok"]
    assert r["hours"] == pdef["hours"] and "tired" in r
    assert c.fatigue == f0 - pdef["fatigue"]


# --- 撬鎖:擲骰付體力 + 時間;塔之鑰招牌免費 ------------------------
def test_pick_lock_roll_costs_fatigue_and_time():
    gd, c = _char(security=50)
    pdef = gd.skills["security"]["practice"]
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    r = dungeon.pick_lock(c, gd, 10, RNG(0))
    assert not r["tower_key"]
    assert r["hours"] == pdef["hours"] and r["hours"] > 0
    assert c.fatigue == f0 - pdef["fatigue"]


def test_tower_key_unlock_is_free_and_keeps_signature():
    gd, c = _char(security=5)
    c.tower_key_charge = True
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    r = dungeon.pick_lock(c, gd, 95, RNG(0))         # 高難度鎖,靠塔之鑰
    assert r["success"] and r["tower_key"] and not c.tower_key_charge
    assert r["hours"] == 0 and not r["tired"]        # 招牌:免耗時
    assert c.fatigue == f0                            # 招牌:免體力


# --- 說服:每次付費;折服必成路徑也付費 -----------------------------
def test_persuade_costs_fatigue_and_time():
    gd, c = _char(speechcraft=40)
    nid = next(iter(gd.npcs))
    pdef = gd.skills["speechcraft"]["practice"]
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    r = dialogue.persuade(c, gd, nid, RNG(0))
    assert r["hours"] == pdef["hours"] and r["hours"] > 0
    assert c.fatigue == f0 - pdef["fatigue"]


def test_charm_path_also_pays_cost():
    gd, c = _char(speechcraft=100)                   # 辯舌·折服:對該 NPC 必成一次
    nid = next(iter(gd.npcs))
    pdef = gd.skills["speechcraft"]["practice"]
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    r = dialogue.persuade(c, gd, nid, RNG(0))
    assert r.get("charmed")                          # 確走折服路徑
    assert c.fatigue == f0 - pdef["fatigue"]         # 仍付體力(非免費必成)
    assert r["hours"] == pdef["hours"]


# --- 接線煙霧:三個真實互動入口確實推進時間(time-advance wiring)----
_FIRST = object()


def _patch_ui(menu_fn, confirm_fn):
    """暫換 ui 的互動函式為腳本/啞實作,回傳 restore()(finally 還原,避免汙染其他模組)。"""
    from tesrpg.ui import console as ui
    silent = ("message", "show_events", "loot_report", "npc_panel", "dungeon_room")
    saved = {n: getattr(ui, n) for n in ("menu", "confirm", *silent)}
    ui.menu = menu_fn
    ui.confirm = confirm_fn
    for n in silent:
        setattr(ui, n, lambda *a, **k: None)

    def restore():
        for n, fn in saved.items():
            setattr(ui, n, fn)
    return restore


def _seq_menu(*returns):
    it = iter(returns)

    def fn(title=None, opts=None, **k):
        v = next(it, None)
        return opts[0][0] if (v is _FIRST and opts) else v
    return fn


def _bounded_yes(limit=20):
    """前 limit 次回 True 之後 False —— 防撬鎖重試萬一不中而無限迴圈。"""
    n = {"i": 0}

    def fn(*a, **k):
        n["i"] += 1
        return n["i"] <= limit
    return fn


def _smoke_state():
    from tesrpg.state import GameState
    gd = get_gamedata()
    c = build_character(gd, name="S", sex="male", race="imperial",
                        birthsign="warrior", class_id="thief")
    c.fatigue = c.max_fatigue
    return gd, GameState(player=c, rng=RNG(seed=1), game_mode="adventure")


def test_smoke_shop_steal_advances_time():
    import tesrpg.main as M
    gd, state = _smoke_state()
    t0 = state.time.absolute_hours()
    restore = _patch_ui(_seq_menu("steal", _FIRST, None), _bounded_yes())
    try:
        M.action_shop(state, gd)
    finally:
        restore()
    assert state.time.absolute_hours() > t0, "行竊應推進時間"


def test_smoke_lockpick_advances_time():
    import tesrpg.main as M
    gd, state = _smoke_state()
    state.player.skills["security"] = 100          # 高技能 → 很快開,且為真實擲骰(非塔之鑰)
    t0 = state.time.absolute_hours()
    restore = _patch_ui(_seq_menu(), _bounded_yes())
    try:
        M._resolve_container(state, gd, {"locked": 5, "loot": [{"gold": [5, 5]}]}, "箱子")
    finally:
        restore()
    assert state.time.absolute_hours() > t0, "撬鎖應推進時間"


def test_smoke_talk_persuade_advances_time():
    import tesrpg.main as M
    gd, state = _smoke_state()
    t0 = state.time.absolute_hours()
    restore = _patch_ui(_seq_menu(_FIRST, "persuade", None), _bounded_yes())
    try:
        M.action_talk(state, gd)
    finally:
        restore()
    assert state.time.absolute_hours() > t0, "說服應推進時間"


def test_lockpick_loop_stops_when_exhausted():
    """體力耗盡時撬鎖自動重試迴圈會收手(體力=單場撬鎖次數的真實上限),

    而非以半額效率無限重試同一把鎖刷 security。即便玩家一律選「再試」也擋不住。
    對抗審查確認的唯一發現:_resolve_container 的 while True 是最低摩擦的刷取迴圈。
    反向驗證:還原「tired 只警告不停止」會讓本迴圈一路重試到偶然成功(時間遠超體力預算)。
    """
    import tesrpg.main as M
    gd, state = _smoke_state()
    state.player.skills["security"] = 5                 # 低技能,難鎖近乎必失敗
    state.player.fatigue = 8                            # 體力預算:撬 2 次即耗盡(cost 5)
    t0 = state.time.absolute_hours()
    restore = _patch_ui(_seq_menu(), _bounded_yes(50))  # 一律「再試」,不靠玩家放棄
    try:
        M._resolve_container(state, gd, {"locked": 95, "loot": [{"gold": [5, 5]}]}, "箱子")
    finally:
        restore()
    assert state.time.absolute_hours() - t0 <= 2        # 耗盡即停,不會無限刷


# --- 製作/維護系(煉金/附魔/修理)也接上 practice 成本 ----------------
def test_brew_costs_fatigue_and_time():
    from tesrpg.systems import alchemy, inventory
    gd, c = _char(alchemy=40)
    inventory.add_item(c, "wheat", 1); inventory.add_item(c, "blue_mountain_flower", 1)  # 共通 heal
    pdef = gd.skills["alchemy"]["practice"]
    c.fatigue = c.max_fatigue; f0 = c.fatigue
    r = alchemy.brew(c, gd, "wheat", "blue_mountain_flower", RNG(0))
    assert r["ok"]
    assert r["hours"] == pdef["hours"] and "tired" in r
    assert c.fatigue == f0 - pdef["fatigue"]


def test_brew_fail_still_costs_fatigue_and_time():
    """沒煉成(無共通效果)也付出體力+時間(白忙也花了工夫),只是學得少。"""
    from tesrpg.systems import alchemy, inventory
    gd, c = _char(alchemy=40)
    inventory.add_item(c, "glow_dust", 1); inventory.add_item(c, "deathbell", 1)  # 無共通效果
    pdef = gd.skills["alchemy"]["practice"]
    c.fatigue = c.max_fatigue; f0 = c.fatigue
    r = alchemy.brew(c, gd, "glow_dust", "deathbell", RNG(0))
    assert not r["ok"]
    assert r["hours"] == pdef["hours"]
    assert c.fatigue == f0 - pdef["fatigue"]


def test_enchant_costs_fatigue_and_time():
    from tesrpg.systems import enchanting, inventory
    gd, c = _char(mysticism=40)
    inventory.add_item(c, "silver_ring", 1)
    inventory.add_item(c, "filled_common_soul_gem", 1)
    pdef = gd.skills["mysticism"]["practice"]
    c.fatigue = c.max_fatigue; f0 = c.fatigue
    r = enchanting.enchant_jewelry(c, gd, "silver_ring", "skill", "destruction", "filled_common_soul_gem")
    assert r["ok"]
    assert r["hours"] == pdef["hours"] and "tired" in r
    assert c.fatigue == f0 - pdef["fatigue"]


def test_repair_hammer_costs_fatigue_and_time():
    import tesrpg.main as M
    from tesrpg.systems import inventory
    gd, state = _smoke_state()
    inventory.add_item(state.player, "repair_hammer", 1)
    pdef = gd.skills["armorer"]["practice"]
    t0 = state.time.absolute_hours(); f0 = state.player.fatigue
    restore = _patch_ui(_seq_menu("hammer"), _bounded_yes())
    try:
        M.action_repair(state, gd)
    finally:
        restore()
    assert inventory.count_item(state.player, "repair_hammer") == 0     # 鎚已消耗
    assert state.time.absolute_hours() - t0 == pdef["hours"]            # 修理耗時
    assert state.player.fatigue == f0 - pdef["fatigue"]                # 修理耗體


def run():
    test_practice_cost_deducts_fatigue_and_matches_skills_json()
    test_practice_cost_tired_halves_xp_and_clamps()
    test_steal_xp_only_on_success()
    test_steal_costs_fatigue_and_returns_time()
    test_pick_lock_roll_costs_fatigue_and_time()
    test_tower_key_unlock_is_free_and_keeps_signature()
    test_persuade_costs_fatigue_and_time()
    test_charm_path_also_pays_cost()
    test_smoke_shop_steal_advances_time()
    test_smoke_lockpick_advances_time()
    test_smoke_talk_persuade_advances_time()
    test_lockpick_loop_stops_when_exhausted()
    test_brew_costs_fatigue_and_time()
    test_brew_fail_still_costs_fatigue_and_time()
    test_enchant_costs_fatigue_and_time()
    test_repair_hammer_costs_fatigue_and_time()


if __name__ == "__main__":
    run()
    print("test_practice_cost 全通過")
