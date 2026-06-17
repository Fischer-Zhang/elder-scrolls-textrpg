"""格子探索地城(程序化 n×n × m 層,原子探索)的測試:

生成合法性(連通/樓梯+boss 可達/入口/id 合法)、衝 boss 勝利 → 肅清 + 寶藏自動解鎖
(免開鎖器)、逃跑/離開不計清剿。承既有「逃跑不誤判清剿」回歸防線。
"""

from collections import deque

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import dungeoncrawl as DC
from tesrpg.ui import console as ui
import tesrpg.main as M


def _char(dloc="cedernoc_cave"):
    gd = get_gamedata()
    c = build_character(gd, name="探", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    loc = next(l for l, n in gd.world["locations"].items() if n.get("dungeon") == dloc)
    c.location_id = loc
    return gd, c, GameState(player=c, time=GameTime(), rng=RNG(11))


# --- 生成合法性 ---------------------------------------------------------
def test_generate_all_valid():
    gd = get_gamedata()
    for did, spec in gd.dungeons.items():
        for seed in (1, 7, 42, 99, 2024):                                 # 多種子:生成對任意 RNG 皆合法
            g = DC.generate(spec, gd, RNG(seed))
            n, m = g["n"], g["m"]
            assert g["layers"][0][0][0]["type"] == DC.ENTRANCE, did       # 入口在 (0,0) layer0
            for z in range(m):
                reach = DC.reachable_cells(g, z)
                assert len(reach) == n * n, (did, z, seed)                # 開放格 → 全連通
                target = DC.STAIRS if z < m - 1 else DC.BOSS
                cell = DC.find_cell(g, z, target)
                assert cell is not None and cell in reach, (did, z, target, seed)  # 樓梯/boss 必存在且可達
        for tid in spec["monsters"]:                                      # id 合法性檢查跑一次即可
            assert tid in gd.bestiary, (did, tid)
        assert spec["boss"]["enemy"] in gd.bestiary, did
        for x in spec.get("loot", []):
            assert gd.item_or_none(x) is not None, (did, x)
        for x in spec["boss"]["treasure"]["loot"]:
            if isinstance(x, str):
                assert gd.item_or_none(x) is not None, (did, x)


# --- crawl 驅動 ----------------------------------------------------------
def _run(gd, st, battle_result, navigate=True, cap=None):
    """以 patched ui 跑 action_dungeon;navigate=True 時自動往 樓梯→下層→boss 前進。
    battle_result(foes)→ 'victory'|'fled'|'dead'(foes 為 list=一般格、單一 Creature=boss)。
    cap(可選 dict):驅動過程觀測 —— last_opts(最後選單鍵)/ rb_kwargs(run_battle 末次 kwargs)/ rb_calls。"""
    cap = cap if cap is not None else {}
    stash = {}
    real_gen = DC.generate
    def gen(spec, g, rng):
        grid = real_gen(spec, g, rng); stash["g"] = grid; stash.update(z=0, x=0, y=0); return grid
    def step(grid, z, sx, sy, goal):
        if goal is None:
            return None
        q = deque([(sx, sy, None)]); seen = {(sx, sy)}
        while q:
            x, y, first = q.popleft()
            if (x, y) == goal:
                return first
            for k, _l, nx, ny in DC.neighbors(grid, x, y):
                if (nx, ny) not in seen:
                    seen.add((nx, ny)); q.append((nx, ny, first or k))
        return None
    def menu(title, opts, allow_back=False):
        cap["last_opts"] = [o[0] for o in opts]
        if not navigate:
            return "leave"
        g = stash["g"]; z, x, y = stash["z"], stash["x"], stash["y"]
        goal = DC.find_cell(g, z, DC.STAIRS) if z < g["m"] - 1 else DC.find_cell(g, z, DC.BOSS)
        if (x, y) == goal and any(o[0] == "descend" for o in opts):
            stash.update(z=z + 1, x=0, y=0); return "descend"
        s = step(g, z, x, y, goal)
        if s:
            for k, _l, nx, ny in DC.neighbors(g, x, y):
                if k == s:
                    stash.update(x=nx, y=ny); break
            return "go:" + s
        return "leave"
    def rb(state, g, foes, *a, **k):
        cap["rb_kwargs"] = k
        cap["rb_calls"] = cap.get("rb_calls", 0) + 1
        return battle_result(foes)
    saved = (ui.menu, ui.message, ui.dungeon_grid, ui.loot_report, ui.confirm, ui.rule,
             ui.show_events, ui.status_line, M.run_battle, DC.generate)
    ui.menu = menu
    ui.message = ui.dungeon_grid = ui.loot_report = ui.rule = ui.status_line = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True
    M.run_battle = rb
    DC.generate = gen
    try:
        return M.action_dungeon(st, gd)
    finally:
        (ui.menu, ui.message, ui.dungeon_grid, ui.loot_report, ui.confirm, ui.rule,
         ui.show_events, ui.status_line, M.run_battle, DC.generate) = saved


def test_clear_on_boss_victory_and_auto_loot_treasure():
    gd, c, st = _char()
    did = gd.world["locations"][c.location_id]["dungeon"]
    c.inventory = [it for it in c.inventory if it["id"] != "lockpick"]   # 身上無開鎖器
    gold0 = c.gold
    ret = _run(gd, st, lambda foes: "victory")
    assert ret is None
    assert did in c.cleared_dungeons                                    # 肅清計入
    assert c.gold > gold0                                               # boss 寶藏自動入袋(免開鎖器)


def test_recleared_dungeon_boss_treasure_not_regiven():
    """反刷寶(R36 後):已肅清地城重訪 → **首領寶藏不再給**(boss 重生可再戰但寶藏已取走)。
    一般寶箱則隨機刷新可重撈(見 test_recleared_dungeon_general_chests_respawn);此處清空開鎖器隔離一般寶箱,只驗首領寶藏。"""
    gd, c, st = _char()
    did = gd.world["locations"][c.location_id]["dungeon"]
    c.inventory = [it for it in c.inventory if it["id"] != "lockpick"]   # 無開鎖器 → 一般寶箱撬不開 → 隔離出首領寶藏
    c.cleared_dungeons = [did]                                           # 預設已肅清 → 重訪
    gold0, inv0 = c.gold, [dict(it) for it in c.inventory]
    ret = _run(gd, st, lambda foes: "victory")                          # 一路清到 boss 並擊殺
    assert ret is None
    assert did in c.cleared_dungeons                                    # record 仍冪等
    assert c.gold == gold0                                              # 首領寶藏不再入袋
    assert c.inventory == inv0                                          # 無開鎖器 → 重訪零掉落


def test_recleared_dungeon_general_chests_respawn():
    """R36:已肅清地城重訪,一般寶箱隨機刷新 → CONTAINER 格仍呼 _resolve_container(非昔日空箱)。
    spy 計數 _resolve_container;多種子求至少一次 beeline 路徑踏上寶箱格(15% 密度,極可能)。"""
    gd = get_gamedata()
    saw_resolve = False
    for seed in range(8):
        c = build_character(gd, name="探", sex="male", race="nord", birthsign="warrior", class_id="warrior")
        loc = next(l for l, n in gd.world["locations"].items() if n.get("dungeon") == "cedernoc_cave")
        c.location_id = loc
        c.cleared_dungeons = [gd.world["locations"][loc]["dungeon"]]      # 重訪
        st = GameState(player=c, time=GameTime(), rng=RNG(seed))
        calls = {"n": 0}
        real = M._resolve_container
        M._resolve_container = lambda *a, **k: calls.__setitem__("n", calls["n"] + 1)   # spy(不開箱→零掉落干擾)
        try:
            _run(gd, st, lambda foes: "victory")
        finally:
            M._resolve_container = real
        if calls["n"] > 0:
            saw_resolve = True
            break
    assert saw_resolve, "重訪地城應至少一次踏上 CONTAINER 格並呼叫 _resolve_container(一般寶箱已刷新,非空箱)"


def test_trap_xp_guarded_on_death():
    """R36 對抗審查修:陷阱觸發給 security xp,但致死則不給(鏡像 combat_regen 死人不成長守)。"""
    from tesrpg.systems import combat

    def _trigger(health, dmg):
        gd, c, st = _char()
        c.health = health
        c.skills["security"] = 80                            # 高技能 → 小 xp 不會升級攪局
        x0 = c.skill_xp.get("security", 0.0)
        sv = ui.message, ui.show_events
        ui.message = ui.show_events = lambda *a, **k: None
        st.rng.chance = lambda p: False                      # 避陷檢定必失敗 → 必觸發
        try:
            M._resolve_trap(st, gd, {"damage": [dmg, dmg]})
        finally:
            ui.message, ui.show_events = sv
        return c, x0

    c1, x1 = _trigger(999, 5)
    assert combat.is_alive(c1) and c1.skill_xp.get("security", 0.0) > x1      # 存活觸發 → 給少量 xp
    c2, x2 = _trigger(1, 99)
    assert not combat.is_alive(c2) and c2.skill_xp.get("security", 0.0) == x2  # 致死 → 不給 xp(死人不成長)


def test_flee_boss_does_not_clear_or_loot():
    # 一函式兩情境:非勝利出口皆不計肅清,但走兩條不同 action_dungeon 出口。
    # 情境一(flee):navigate → boss 戰回 'fled' → 命中 main.py 首領逃離分支。
    gd, c, st = _char()
    did = gd.world["locations"][c.location_id]["dungeon"]
    gold0 = c.gold
    ret = _run(gd, st, lambda foes: "victory" if isinstance(foes, list) else "fled")   # 一般格勝、boss 逃
    assert ret is None
    assert did not in c.cleared_dungeons                               # 逃 boss → 不計清剿
    assert c.gold == gold0                                             # 不開 boss 寶藏
    # 情境二(leave):navigate=False → ui.menu 恆回 'leave' → 命中菜單離開分支(從不觸發 run_battle)。
    gd2, c2, st2 = _char()
    did2 = gd2.world["locations"][c2.location_id]["dungeon"]
    ret2 = _run(gd2, st2, lambda foes: "victory", navigate=False)       # 立刻離開
    assert ret2 is None and did2 not in c2.cleared_dungeons            # 菜單離開 → 不計清剿


def test_dead_in_boss_returns_dead():
    gd, c, st = _char()
    ret = _run(gd, st, lambda foes: "victory" if isinstance(foes, list) else "dead")
    assert ret == "dead"
    assert gd.world["locations"][c.location_id]["dungeon"] not in c.cleared_dungeons


# --- 地城視為戰鬥情境:一般行動 / 預施預召喚 / 每格回合 / 偵查 -------------------
def test_crawl_menu_has_general_actions():
    gd, c, st = _char()
    c.spells = ["minor_heal"]                                           # 確保有法術 → cast 選項
    cap = {}
    _run(gd, st, lambda foes: "victory", navigate=False, cap=cap)       # 立刻 leave;選單已建好
    assert {"cast", "inventory", "sheet"} <= set(cap["last_opts"])      # 一般行動齊備


def test_crawl_passes_carry_allies_and_preserve_buffs():
    gd, c, st = _char()
    cap = {}
    _run(gd, st, lambda foes: "victory", cap=cap)                      # navigate → 觸發戰鬥
    assert cap.get("rb_calls", 0) >= 1
    assert isinstance(cap["rb_kwargs"].get("carry_allies"), list)       # 預召喚物帶入戰鬥
    assert cap["rb_kwargs"].get("preserve_buffs") is True              # 預施增益帶入戰鬥


def test_crawl_move_ticks_player_buff():
    gd, c, st = _char()
    c.active_effects.append({"kind": "shield", "magnitude": 30, "turns": 50})
    _run(gd, st, lambda foes: "victory")                               # 一路移動到 boss
    shields = [e for e in c.active_effects if e["kind"] == "shield"]
    assert (not shields) or shields[0]["turns"] < 50                   # 每格 1 回合 → 護盾遞減


def test_crawl_move_grants_scout_xp():
    from tesrpg.systems import progression
    gd, c, st = _char()
    calls = []
    orig = progression.use_skill
    progression.use_skill = lambda ch, g, sk, xp, *a, **k: (calls.append(sk), orig(ch, g, sk, xp, *a, **k))[1]
    try:
        _run(gd, st, lambda foes: "victory")
    finally:
        progression.use_skill = orig
    assert "scout" in calls                                            # 每探明新格 → 練偵查


def test_dot_kills_player_in_crawl():
    gd, c, st = _char()
    c.health = c.max_health
    c.active_effects.append({"kind": "dot", "element": "poison", "magnitude": 9999, "turns": 5})
    ret = _run(gd, st, lambda foes: "victory")
    assert ret == "dead"                                               # 移動 tick → DoT 致死出口


def test_crawl_cast_can_presummon_into_battle():
    """預召喚:地城施法情境(battle 傳入)→ 召喚法術可施,召喚物入 battle['allies']。"""
    from tesrpg.systems import stats
    gd, c, st = _char()
    c.spells = ["conjure_familiar"]
    c.skills["conjuration"] = 60
    stats.recompute_max_resources(c, gd, restore_full=True)
    battle = {"allies": []}
    saved = (ui.menu, ui.message, ui.show_events)
    ui.menu = lambda *a, **k: "conjure_familiar"
    ui.message = ui.show_events = lambda *a, **k: None
    try:
        M.action_cast_self(st, gd, battle=battle)
    finally:
        (ui.menu, ui.message, ui.show_events) = saved
    assert len(battle["allies"]) == 1 and battle["allies"][0].summon_turns is not None


def test_run_battle_carry_allies_not_persisted():
    """🔴 召喚物不污染持久同伴:carry_allies 不入 roster → record_after_battle 不回寫。"""
    from tesrpg.systems import combat
    gd = get_gamedata()
    c = build_character(gd, name="召", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    st = GameState(player=c, time=GameTime(), rng=RNG(3))
    summon = combat.spawn_creature(gd, "summoned_familiar", RNG(0)); summon.summon_turns = 6
    foe = combat.spawn_creature(gd, "mudcrab", RNG(0)); foe.health = 0   # 即勝(略過戰鬥迴圈)
    saved = (ui.combat_status_group, ui.combat_event, ui.message, ui.show_events,
             ui.rule, ui.combat_tick, ui.loot_report)
    ui.combat_status_group = ui.combat_event = ui.message = ui.show_events = \
        ui.rule = ui.combat_tick = ui.loot_report = lambda *a, **k: None
    try:
        res = M.run_battle(st, gd, [foe], carry_allies=[summon], preserve_buffs=True)
    finally:
        (ui.combat_status_group, ui.combat_event, ui.message, ui.show_events,
         ui.rule, ui.combat_tick, ui.loot_report) = saved
    assert res == "victory"
    assert c.companion_hp == {} and c.companions == []                 # 召喚物未寫入持久同伴


def test_skeleton_key_perfect_lockpick():
    """骷髏鑰匙(盜賊掌門神器):撬鎖必成、不耗開鎖器、刻意不給 security xp(防免費刷技能)。"""
    from tesrpg.systems import dungeon
    gd, c, st = _char()
    c.skills["security"] = 0
    assert not dungeon.has_skeleton_key(c, gd)
    c.equipped["amulet"] = "skeleton_key"
    assert dungeon.has_skeleton_key(c, gd)
    assert dungeon.effective_pick_lock_chance(c, gd, 80) == 1.0          # 高難度鎖亦 100%
    sec0 = c.base_skill("security")
    r = dungeon.pick_lock(c, gd, 80, st.rng)                            # 無開鎖器仍成功
    assert r["success"] and r.get("skeleton_key") and not r["no_pick"]
    assert c.base_skill("security") == sec0                             # 不給 xp(非親手習得)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_dungeon OK")
