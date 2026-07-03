"""practice 成本回歸測試:行竊/撬鎖/說服接上各技能 practice 的「體力 + 時間」成本。

守住「不准零風險刷技能」的反 min-max 紅線(原本三者都繞過了正規訓練代價):
- progression.practice_cost 共用 data/skills.json 的 practice 價碼(與訓練師 action_practice 一致)。
- 行竊「得手才給潛行 xp」(被抓不給 → 杜絕「故意被抓刷潛行」)。
- 撬鎖**需開鎖器**(失敗折斷)、**不耗時**、僅扣少量體力;成功給全額 security xp、**失敗給少量 xp**(R36);「塔之鑰」招牌免開鎖器/免成本/免耗時。
- 說服每次付體力 + 時間,連「辯舌·折服」必成路徑也照付(非免費必成)。

每條都可反向驗證:還原修改前的程式碼會因缺 hours/tired 鍵或被抓仍給 xp 而紅。
"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import crime, dialogue, dungeon, inventory, mastery, progression


def _char(**skills):
    gd = get_gamedata()
    c = build_character(gd, name="P", sex="male", race="imperial",
                        birthsign="warrior", class_id="thief")
    c.specialization = ""   # 中性化專精 → 隔離「專精系技能 +20% XP」層,純測 practice 基礎成本/xp
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


# --- 行竊:得手才學藝(杜絕故意被抓刷潛行)+ 成本在擲骰前無條件付清 ----
def test_steal_xp_only_on_success():
    """得手才給潛行 xp(被抓不給);併入原 test_steal_costs_fatigue_and_returns_time:
    成本(practice_cost)在擲骰前無條件呼叫,被抓/得手兩支皆回 hours/tired 且都已扣 fatigue。"""
    gd, c = _char(sneak=10, security=10)           # 得手率約 33% → 兩種結果都會出現
    pdef = gd.skills["sneak"]["practice"]
    saw_caught = saw_success = False
    for i in range(30):
        c.fatigue = c.max_fatigue                  # 排除 tired 干擾,專測「被抓不給 xp」
        f0 = c.fatigue
        before = c.skill_xp.get("sneak", 0.0)
        lvl_before = c.skills["sneak"]
        r = crime.steal_item(c, gd, "iron_sword", RNG(i))
        after = c.skill_xp.get("sneak", 0.0)
        # 成本在擲骰前無條件付清:caught/success 兩支皆回 hours/tired 且都已扣 fatigue
        assert r["hours"] == pdef["hours"]
        assert "tired" in r
        assert c.fatigue == f0 - pdef["fatigue"]
        if r["caught"]:
            saw_caught = True
            assert r["skill_events"] == []
            assert after == before and c.skills["sneak"] == lvl_before  # 被抓不學藝
        else:
            saw_success = True
            assert after > before or c.skills["sneak"] > lvl_before     # 得手才長技能
    assert saw_caught and saw_success


# --- 撬鎖:需開鎖器(失敗折斷)、不耗時、少量體力;塔之鑰招牌免費 ----
def test_pick_lock_needs_pick_no_time_low_fatigue():
    gd, c = _char(security=50)
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    [c.inventory.remove(s) for s in list(c.inventory) if s["id"] == "lockpick"]  # 清掉起始開鎖器
    r = dungeon.pick_lock(c, gd, 10, RNG(0))                  # 無開鎖器 → 撬不了、零成本
    assert r["no_pick"] and not r["success"] and r["hours"] == 0 and c.fatigue == f0
    inventory.add_item(c, "lockpick", 3)
    r = dungeon.pick_lock(c, gd, 10, RNG(0))                  # 有開鎖器 → 不耗時、僅扣少量體力
    assert not r["tower_key"] and r["hours"] == 0
    assert c.fatigue == f0 - dungeon.LOCKPICK_FATIGUE
    assert inventory.count_item(c, "lockpick") == 2          # 每次嘗試耗一根(成功/失敗皆然)


def test_every_attempt_consumes_pick_gates_xp():
    """對抗審查確認的反 min-max 修正:**每次撬鎖嘗試(成功也算)都耗一根開鎖器** →
    security xp 有金幣閘,杜絕高技能者免費重撬同鎖刷 security(原『成功不耗』讓 95% 成功者近乎免費刷)。"""
    gd, c = _char(security=95)                                # 高技能 → 近乎必成功
    c.fatigue = c.max_fatigue
    [c.inventory.remove(s) for s in list(c.inventory) if s["id"] == "lockpick"]  # 清起始開鎖器
    inventory.add_item(c, "lockpick", 5)
    successes = 0
    for i in range(5):
        n0 = inventory.count_item(c, "lockpick")
        r = dungeon.pick_lock(c, gd, 5, RNG(i))
        assert inventory.count_item(c, "lockpick") == n0 - 1   # 即便成功也耗一根 → xp 非免費
        successes += int(r["success"])
    assert successes >= 1 and inventory.count_item(c, "lockpick") == 0   # 5 次耗盡 5 根
    assert dungeon.pick_lock(c, gd, 5, RNG(9))["no_pick"]    # 用盡後撬不了


def test_lockpick_broken_on_failure_small_xp():
    """R36:失敗折斷一根開鎖器、且給**少量** security xp(base × SECURITY_FAIL_XP_FRAC,從失誤學);
    小到不划算刷功 + lockpick 金幣閘仍在,守住反 min-max。成功給全額。"""
    gd, c = _char(security=5)                                 # 低技能撬難鎖 → 近乎必失敗
    c.fatigue = c.max_fatigue
    inventory.add_item(c, "lockpick", 20)
    base_xp = gd.skills["security"]["practice"]["xp"]
    for i in range(20):
        n0 = inventory.count_item(c, "lockpick")
        x0 = c.skill_xp.get("security", 0.0)
        r = dungeon.pick_lock(c, gd, 99, RNG(i))
        if not r["success"]:
            assert r["broke_pick"] and inventory.count_item(c, "lockpick") == n0 - 1   # 折斷一根
            gained = c.skill_xp.get("security", 0.0) - x0                               # security 5 不會因小 xp 升級
            assert abs(gained - base_xp * formulas.SECURITY_FAIL_XP_FRAC) < 1e-9        # 失敗給少量 xp(非 0、非全額)
            assert 0 < gained < base_xp
            break
    else:
        raise AssertionError("低技能撬難鎖應至少失敗一次")


def test_tower_key_unlock_is_free_and_keeps_signature():
    gd, c = _char(security=5)
    c.tower_key_charge = True
    c.fatigue = c.max_fatigue
    f0 = c.fatigue
    r = dungeon.pick_lock(c, gd, 95, RNG(0))         # 高難度鎖,靠塔之鑰
    assert r["success"] and r["tower_key"] and not c.tower_key_charge
    assert r["hours"] == 0 and not r["tired"]        # 招牌:免耗時
    assert c.fatigue == f0                            # 招牌:免體力


# --- 說服:折服必成路徑也付費(每次付體力+時間;非免費必成)----------
def test_charm_path_also_pays_cost():
    gd, c = _char(speechcraft=100)                   # 辯舌·折服:對該 NPC 必成一次
    mastery.choose(c, gd, "speechcraft_100", "charm")   # v2:達門檻後須二選一銘刻
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
    silent = ("message", "show_events", "loot_report", "npc_panel", "dungeon_grid")
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


def test_smoke_lockpick_no_time():
    import tesrpg.main as M
    gd, state = _smoke_state()
    state.player.skills["security"] = 100          # 高技能 → 很快開(用起始開鎖器)
    t0 = state.time.absolute_hours()
    restore = _patch_ui(_seq_menu(), _bounded_yes())
    try:
        M._resolve_container(state, gd, {"locked": 5, "loot": [{"gold": [5, 5]}]}, "箱子")
    finally:
        restore()
    assert state.time.absolute_hours() == t0, "撬鎖不應推進時間"


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


def test_lockpick_loop_bounded_by_picks():
    """撬鎖自動重試迴圈受**開鎖器數量**所限(失敗折斷),即便玩家選「連試到開」(R113 選單
    的 auto 路徑,免逐次確認)也不會無限刷:用盡開鎖器即 no_pick 收手。終局必為
    「開鎖成功」或「開鎖器耗盡」二者之一。
    反向驗證:還原「失敗不折斷開鎖器」會讓本迴圈一路免費重試到偶然成功。
    """
    import tesrpg.main as M
    gd, state = _smoke_state()
    state.player.skills["security"] = 5                 # 低技能,難鎖近乎必失敗 → 每次折斷
    state.player.inventory = [s for s in state.player.inventory if s["id"] != "lockpick"]
    inventory.add_item(state.player, "lockpick", 3)     # 精確 3 根
    gold0 = state.player.gold
    restore = _patch_ui(_seq_menu("auto"), _bounded_yes(50))  # 失敗即選「連試到底」(R113 選單),不靠玩家放棄
    try:
        M._resolve_container(state, gd, {"locked": 99, "loot": [{"gold": [5, 5]}]}, "箱子")
    finally:
        restore()
    opened = state.player.gold > gold0                              # 開了 → 拿到 loot
    out_of_picks = inventory.count_item(state.player, "lockpick") == 0
    assert opened or out_of_picks                                   # 二者之一即終止,非無限刷


# --- 製作/維護系(煉金/附魔/修理)也接上 practice 成本 ----------------
def test_crafting_entries_pay_practice():
    """製作入口皆付 practice(資料驅動,併入原 test_enchant_costs_fatigue_and_time):
    煉金 brew 與附魔 enchant_jewelry 回傳同形 {ok,hours,tired,...},成功皆付體力+時間。
    每 case 各自 _char(以對應 skill 起手)+各自 import/add_item,語意與斷言零流失。"""
    def _brew_case():
        from tesrpg.systems import alchemy, inventory
        gd, c = _char(alchemy=40)
        inventory.add_item(c, "wheat", 1); inventory.add_item(c, "blue_mountain_flower", 1)  # 共通 heal
        c.fatigue = c.max_fatigue
        return c, alchemy.brew(c, gd, "wheat", "blue_mountain_flower", RNG(0))

    def _enchant_case():
        from tesrpg.systems import enchanting, inventory
        gd, c = _char(mysticism=40)
        inventory.add_item(c, "silver_ring", 1)
        inventory.add_item(c, "filled_common_soul_gem", 1)
        c.fatigue = c.max_fatigue
        return c, enchanting.enchant_jewelry(c, gd, "silver_ring", "skill", "destruction", "filled_common_soul_gem")

    cases = [("alchemy", _brew_case), ("mysticism", _enchant_case)]
    gd = get_gamedata()
    for skill_id, make in cases:
        pdef = gd.skills[skill_id]["practice"]
        c, r = make()
        f0 = c.max_fatigue
        assert r["ok"], skill_id
        assert r["hours"] == pdef["hours"] and "tired" in r, skill_id
        assert c.fatigue == f0 - pdef["fatigue"], skill_id


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


# --- 一次練多小時:批次 practice -------------------------------------
def _patch_practice_ui(skill_id, hours):
    """暫換 ui.menu(分類→技能)+ ui.ask_int(時數)+ 靜音輸出;回傳 restore()。"""
    from tesrpg.ui import console as ui
    saved = {n: getattr(ui, n) for n in ("menu", "ask_int", "message", "show_events")}
    seq = iter([gd_spec_of(skill_id), skill_id])
    ui.menu = lambda *a, **k: next(seq, None)
    ui.ask_int = lambda *a, **k: hours
    ui.message = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None

    def restore():
        for n, fn in saved.items():
            setattr(ui, n, fn)
    return restore


def gd_spec_of(skill_id):
    return get_gamedata().skills[skill_id]["spec"]


def test_practice_batches_multiple_hours():
    """一次練多小時:action_practice 連跑 N 輪 practice → 時間/體力/xp 按輪數累積。"""
    import tesrpg.main as M
    gd, state = _smoke_state()
    c = state.player
    c.skills["blade"] = 40                          # 門檻 4.2 > 5×0.6=3.0 → 本批不升級,xp 純累積
    c.fatigue = c.max_fatigue
    pdef = gd.skills["blade"]["practice"]
    hours, t0, f0, x0 = 5, state.time.absolute_hours(), c.fatigue, c.skill_xp.get("blade", 0.0)
    restore = _patch_practice_ui("blade", hours)
    try:
        M.action_practice(state, gd)
    finally:
        restore()
    assert state.time.absolute_hours() - t0 == hours * pdef["hours"]   # N 輪各推進時間
    assert c.fatigue == f0 - hours * pdef["fatigue"]                   # N 輪各扣體力
    assert c.skills["blade"] == 40                                      # 未跨門檻
    assert abs(c.skill_xp.get("blade", 0.0) - (x0 + hours * pdef["xp"])) < 1e-9   # 全額 xp 累積


def test_practice_stops_at_skill_cap():
    """練到滿級就停:base_skill 已達上限 → action_practice 零成本收手(不空耗時間/體力)。"""
    import tesrpg.main as M
    from tesrpg import formulas
    gd, state = _smoke_state()
    c = state.player
    c.skills["blade"] = formulas.SKILL_CAP
    c.fatigue = c.max_fatigue
    t0, f0 = state.time.absolute_hours(), c.fatigue
    restore = _patch_practice_ui("blade", 5)
    try:
        M.action_practice(state, gd)
    finally:
        restore()
    assert state.time.absolute_hours() == t0 and c.fatigue == f0       # 滿級不耗時間/體力


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_practice_cost 全通過")
