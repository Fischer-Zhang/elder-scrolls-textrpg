"""R193 徒手 100「鐵布衫」(hand_to_hand_100 iron_shirt·kind fatigue_ward):體力化傷。
受到的**物理**傷害(含遠程物理)在所有減傷之後,share(0.30)比例由體力 1:1 代扣,體力見底即停;
元素/法術/DoT/反傷不吃、獸形無效、未選 → 零影響且無 rng(替換舊 passive_armor +12)。
"""
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic, mastery, stats

gd = get_gamedata()
SHARE = 0.20


def _monk(h100="iron_shirt", fatigue=None):
    c = build_character(gd, name="僧", sex="m", race="khajiit", birthsign="warrior", class_id="warrior")
    c.skills["hand_to_hand"] = 100
    c.weapon = "fists"
    mastery.choose(c, gd, "hand_to_hand_50", "grapple")
    if h100:
        mastery.choose(c, gd, "hand_to_hand_100", h100)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 5000                     # 吃得住:不因死亡截斷樣本
    c.fatigue = c.max_fatigue if fatigue is None else fatigue
    return c


def _hit(c, seed, attack=None, foe_id="bandit"):
    foe = combat.spawn_creature(gd, foe_id, RNG(1))
    return combat.resolve_attack(foe, c, gd, RNG(seed), attack=attack)


def _pair(seed, fatigue=None, attack=None, **kw):
    """同種子、同起始體力:已選鐵布衫 vs 未選對照 → (選, 對照, 事件選, 事件對照, 體力損失選, 體力損失對照)。"""
    a, b = _monk(fatigue=fatigue), _monk(h100=None, fatigue=fatigue)
    for c in (a, b):
        for e in kw.get("effects", []):
            c.active_effects.append(dict(e))
    fa0, fb0 = a.fatigue, b.fatigue
    ea, eb = _hit(a, seed, attack), _hit(b, seed, attack)
    return a, b, ea, eb, fa0 - a.fatigue, fb0 - b.fatigue


# --- 資料 / getter ---------------------------------------------------------------
def test_getter_only_when_selected_and_old_armor_is_gone():
    assert abs(mastery.fatigue_ward(_monk(), gd) - SHARE) < 1e-9
    assert mastery.fatigue_ward(_monk(h100=None), gd) == 0.0
    assert mastery.fatigue_ward(_monk(h100="transcend_fist"), gd) == 0.0     # 選另一側 → 無
    assert mastery.passive_armor_bonus(_monk(), gd) == 0                     # 舊 +12 護甲已移除(替換,不兼帶)


def test_desc_numbers_match_data_and_kind_is_registered():
    node = next(n for n in gd.mastery if n["id"] == "hand_to_hand_100")
    opt = next(o for o in node["options"] if o["opt_id"] == "iron_shirt")        # opt_id 不變(存檔相容)
    assert opt["kind"] == "fatigue_ward" and "armor_bonus" not in opt
    assert f"{int(round(opt['share'] * 100))}%" in opt["desc"]
    assert opt["kind"] in mastery._IMPLEMENTED_KINDS


# --- 效果:拆成 血 + 體力,總量守恆 -------------------------------------------------
def test_physical_hit_is_split_between_hp_and_fatigue_and_total_is_conserved():
    seen = 0
    for seed in range(120):
        a, b, ea, eb, fa, fb = _pair(seed)
        if not (ea["hit"] and eb["hit"]) or eb["damage"] < 6:
            continue
        seen += 1
        assert abs((ea["damage"] + ea["iron_absorbed"]) - eb["damage"]) <= 1, (ea, eb)   # 總量守恆(±取整)
        assert abs(ea["iron_absorbed"] - SHARE * eb["damage"]) <= 1.0, (ea["iron_absorbed"], eb["damage"])
        assert abs(fa - ea["iron_absorbed"]) <= 0.5 and fb == 0     # 體力扣量 = 化去量;對照無此扣
        assert eb["iron_absorbed"] == 0                             # 未選 → 事件欄位為 0
        assert 5000 - a.health == ea["damage"] and 5000 - b.health == eb["damage"]
    assert seen >= 40                                               # 防空測


def test_ward_stops_when_fatigue_runs_out_and_never_goes_negative():
    seen = 0
    for seed in range(120):
        a, b, ea, eb, fa, fb = _pair(seed, fatigue=1.0)             # 只剩 1 點體力
        if not (ea["hit"] and eb["hit"]) or eb["damage"] < 8:       # 30%×8 ≥ 2.4 > 1 → 體力是限制因素
            continue
        seen += 1
        assert a.fatigue == 0 and abs(fa - 1.0) < 1e-9              # 最多代扣到 0
        assert ea["iron_absorbed"] == 1                              # 只化去 1 點
        assert abs((ea["damage"] + 1) - eb["damage"]) <= 1           # 其餘照扣血
    assert seen >= 30
    # 體力 0:完全不代扣(= 對照)
    for seed in range(40):
        a, b, ea, eb, fa, fb = _pair(seed, fatigue=0)
        if ea["hit"] and eb["hit"]:
            assert ea["damage"] == eb["damage"] and ea["iron_absorbed"] == 0 and a.fatigue == 0


def test_ward_is_applied_after_other_mitigation():
    """格擋姿態(R137)等減傷先算,化傷吃減傷後的那份(不是原始傷害)。"""
    stance = [{"kind": "guard_stance", "turns": combat.PERSISTENT_TURNS}]
    seen = 0
    for seed in range(120):
        a, b, ea, eb, fa, fb = _pair(seed, effects=stance)
        _, _, _, plain, _, _ = _pair(seed)
        if ea["hit"] and eb["hit"] and plain["hit"] and eb["damage"] >= 4:
            seen += 1
            assert eb["damage"] < plain["damage"]                    # 對照:姿態確實減傷(測試有偵測力)
            assert abs(ea["iron_absorbed"] - SHARE * eb["damage"]) <= 1.0     # 化的是姿態後的份
    assert seen >= 20


# --- 範圍:只物理 ------------------------------------------------------------------
def test_elemental_attacks_are_not_warded():
    fire = {"name": "炎擊", "damage": 20, "skill": 50, "element": "fire"}
    for seed in range(40):
        a, b, ea, eb, fa, fb = _pair(seed, attack=fire)
        if ea["hit"]:
            assert ea["iron_absorbed"] == 0 and fa == 0 and ea["damage"] == eb["damage"]


def test_ranged_physical_is_warded_like_melee():
    arrow = {"name": "冷箭", "damage": 20, "skill": 50, "ranged": True}
    seen = 0
    for seed in range(80):
        a, b, ea, eb, fa, fb = _pair(seed, attack=arrow)
        if ea["hit"] and eb["hit"] and eb["damage"] >= 6:
            seen += 1
            assert ea["iron_absorbed"] > 0 and abs(fa - ea["iron_absorbed"]) <= 0.5
    assert seen >= 20


def test_dot_and_beast_form_are_not_warded():
    c = _monk()
    f0 = c.fatigue
    c.active_effects.append({"kind": "dot", "element": "fire", "magnitude": 20, "turns": 3})
    h0 = c.health
    magic.tick_effects(c, gd)
    assert c.health < h0 and c.fatigue >= f0 - 1e-9                  # 持續傷害照扣血、不動體力
    b = _monk()
    b.beast_form = True
    fb0 = b.fatigue
    for seed in range(40):
        ev = _hit(b, seed)
        assert ev["iron_absorbed"] == 0
    assert b.fatigue >= fb0 - 1e-9                                   # 獸形無效


def test_unselected_is_byte_identical_no_rng_no_fatigue():
    """未選:零體力損耗、事件欄位 0;且與「選但 share 全由體力吃光」無關 → 對照組與選擇組使用同一 rng 序,結果一致只差代扣。"""
    c = _monk(h100=None)
    f0 = c.fatigue
    rng = RNG(9)
    st0 = rng._random.getstate()
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    ev = combat.resolve_attack(foe, c, gd, rng)
    st1 = rng._random.getstate()
    rng2 = RNG(9)
    c2 = _monk()
    foe2 = combat.spawn_creature(gd, "bandit", RNG(1))
    combat.resolve_attack(foe2, c2, gd, rng2)
    assert rng2._random.getstate() == st1                             # 選與未選消耗完全相同的 rng(鐵布衫零 rng)
    assert ev["iron_absorbed"] == 0 and c.fatigue == f0


# --- 顯示 --------------------------------------------------------------------------
def test_event_line_is_shown_in_combat_log():
    for seed in range(80):
        c = _monk()
        ev = _hit(c, seed)
        if ev["hit"] and ev["iron_absorbed"] > 0:
            ui.console = Console(file=io.StringIO(), force_terminal=False, width=200)
            ui.combat_event(ev, gd)
            out = ui.console.file.getvalue()
            assert "鐵布衫化去" in out and str(ev["iron_absorbed"]) in out, out
            return
    raise AssertionError("樣本內沒有任何一擊被化傷")


def run():
    for name in sorted(globals()):
        if name.startswith("test_"):
            globals()[name]()
