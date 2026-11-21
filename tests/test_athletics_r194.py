"""R194 運動 100:二次呼吸 = 「一氣呵成」(tidal_breath·kind second_breath)/ 無盡之軀 = 「殺勢回體」(frugal·kind fatigue_on_kill)。
使用者 2026-11-21 拍板「開有限例外·照校準版」(R147「恢復必須付代價」的有限例外):
  一氣呵成 = 每場戰鬥行動時體力 ≤ 25% 最大體力(使用者拍板由「歸零」改 25%:歸零對會提早調息/重盾持架者無增益)→ 免耗回合回一次調息量(一場一次);
  殺勢回體 = 親手擊殺回 3% 最大體力(召喚爪牙不算;使用者拍板由 2% 調 3%:n=80 的 2% 效果被雜訊高估)。
🔴 紅線:免費但結構上有限(一場一次/擊殺數有限)→ 無無限迴路;不碰力竭懸崖;零 rng;未選 → 完全不動(byte-identical);
   戰鬥內記帳(second_breath_spent)入戰/離戰必清;法術/同伴擊殺不算。
"""
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, mastery, stats
import tesrpg.main as main

gd = get_gamedata()
PCT = 0.03
BELOW = 0.25


def _char(h100=None, **extra):
    c = build_character(gd, name="運", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    c.skills["athletics"] = 100
    c.skills.update(extra)
    if h100:
        mastery.choose(c, gd, "athletics_100", h100)
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 5000
    c.fatigue = c.max_fatigue
    return c


def _foe(hp=10 ** 6, summoned=False):
    f = combat.spawn_creature(gd, "bandit", RNG(1))
    f.health = f.max_health = hp
    f.resist = {}
    if summoned:
        f.summoned = True
    return f


# --- 資料 / getter ------------------------------------------------------------------
def test_options_are_mechanisms_not_numbers_and_ids_are_stable():
    node = next(n for n in gd.mastery if n["id"] == "athletics_100")
    opts = {o["opt_id"]: o for o in node["options"]}
    assert set(opts) == {"tidal_breath", "frugal"}                      # opt_id 不變(存檔相容)
    assert opts["tidal_breath"]["kind"] == "second_breath" and "rest_bonus" not in opts["tidal_breath"]
    assert opts["frugal"]["kind"] == "fatigue_on_kill" and "bonus" not in opts["frugal"]
    assert abs(opts["frugal"]["pct"] - PCT) < 1e-9 and abs(opts["tidal_breath"]["below"] - BELOW) < 1e-9
    assert f"{int(round(opts['frugal']['pct'] * 100))}%" in opts["frugal"]["desc"]        # desc 數字與資料同步
    assert f"{int(round(opts['tidal_breath']['below'] * 100))}%" in opts["tidal_breath"]["desc"]
    assert "取代舊" not in opts["tidal_breath"]["desc"] + opts["frugal"]["desc"]          # 玩家文案不夾帶改版史
    for k in ("second_breath", "fatigue_on_kill"):
        assert k in mastery._IMPLEMENTED_KINDS


def test_getters_only_when_selected():
    assert mastery.second_breath(_char(), gd) == {} and mastery.fatigue_on_kill(_char(), gd) == 0.0
    assert mastery.second_breath(_char("tidal_breath"), gd) == {"below": BELOW} and mastery.fatigue_on_kill(_char("tidal_breath"), gd) == 0.0
    assert mastery.second_breath(_char("frugal"), gd) == {}
    assert abs(mastery.fatigue_on_kill(_char("frugal"), gd) - PCT) < 1e-9


def test_the_athletics_50_option_named_second_wind_is_not_the_breath_mechanic():
    """審查:既有 opt_id `second_wind`(節氣·athletics_50·fatigue_cost_bonus)與本機制易混 → 本機制 kind 命名為 second_breath,並釘死兩者互不啟動。"""
    c = _char()
    mastery.choose(c, gd, "athletics_50", "second_wind")
    assert not mastery.second_breath(c, gd)                             # 選節氣 ≠ 啟動一氣呵成
    assert abs(mastery.fatigue_cost_bonus(c, gd) - 0.10) < 1e-9         # 節氣仍是 −10% 揮擊耗體
    c.fatigue = 0
    assert not combat.second_breath_ready(c, gd)


# --- 一氣呵成:各閘逐一單獨驗 --------------------------------------------------------
def test_second_breath_gates_each_branch_in_isolation():
    c = _char("tidal_breath")
    c.fatigue = 0
    assert combat.second_breath_ready(c, gd)                              # 對照組:全條件齊 → 可用
    c.fatigue = BELOW * c.max_fatigue
    assert combat.second_breath_ready(c, gd)                              # 恰在門檻 → 可用(≤)
    c.fatigue = BELOW * c.max_fatigue + 1
    assert not combat.second_breath_ready(c, gd)                          # 高於門檻 → 不可用
    c.fatigue = 0
    c.active_effects.append({"kind": "second_breath_spent", "turns": combat.PERSISTENT_TURNS})
    assert not combat.second_breath_ready(c, gd)                          # 本場已用過
    assert combat.second_breath_use(c, gd) == 0 and c.fatigue == 0        # 不可用 → 0 且不動體力
    plain = _char(); plain.fatigue = 0
    assert not combat.second_breath_ready(plain, gd)                      # 未選
    assert combat.second_breath_use(plain, gd) == 0 and plain.fatigue == 0 and not plain.active_effects
    foe = _foe(); foe.fatigue = 0
    assert not combat.second_breath_ready(foe, gd)                        # 非玩家(怪物)


def test_second_breath_threshold_comes_from_the_data_not_a_hardcoded_constant():
    """門檻讀 mastery.json 的 below(日後純改 JSON 可調;below=0 即回到「歸零」語意)。"""
    opt = next(o for n in gd.mastery if n["id"] == "athletics_100" for o in n["options"] if o["opt_id"] == "tidal_breath")
    orig = opt["below"]
    try:
        c = _char("tidal_breath")
        opt["below"] = 0.5
        c.fatigue = 0.4 * c.max_fatigue
        assert combat.second_breath_ready(c, gd)
        c.fatigue = 0.6 * c.max_fatigue
        assert not combat.second_breath_ready(c, gd)
        opt["below"] = 0.0
        c.fatigue = 1
        assert not combat.second_breath_ready(c, gd)
        c.fatigue = 0
        assert combat.second_breath_ready(c, gd)
    finally:
        opt["below"] = orig


def test_second_breath_recovers_one_rest_amount_once_and_clamps():
    c = _char("tidal_breath")
    mastery.choose(c, gd, "athletics_25", "steady_breath")
    mastery.choose(c, gd, "athletics_75", "deep_breath")
    expect = formulas.rest_fatigue_amount(100) + 8 + 12                 # 一次調息量(含勻息/深息加成)
    c.fatigue = 0
    assert combat.second_breath_use(c, gd) == expect and abs(c.fatigue - expect) < 1e-9
    assert any(e["kind"] == "second_breath_spent" for e in c.active_effects)
    c.fatigue = 0
    assert combat.second_breath_use(c, gd) == 0 and c.fatigue == 0        # 一場一次
    c.active_effects.clear()                                            # 新的一場(入戰整包清)
    c.max_fatigue = 10; c.fatigue = 0
    assert combat.second_breath_use(c, gd) == expect and c.fatigue == 10  # 夾 max,不溢出


def test_triggers_even_when_fatigue_never_reaches_zero():
    """審查/拍板的動機:會提早調息、或重盾持架(掩體 +2/回合)的玩家體力永遠 >0 → 「歸零」觸發不了;25% 門檻照樣觸發。"""
    c = _char("tidal_breath")
    c.fatigue = 2.0                                                      # 體力 >0 但已低於 25%
    assert c.fatigue > 0 and combat.second_breath_ready(c, gd)
    expect = formulas.rest_fatigue_amount(100) + mastery.rest_bonus(c, gd)
    assert combat.second_breath_use(c, gd) == expect and abs(c.fatigue - (2.0 + expect)) < 1e-9


def test_unselected_helpers_change_nothing():
    """未選:兩個 helper 不改任何狀態(兩者簽名都不吃 rng → 結構上零 rng;未選構築的整場 byte-identical 由下方黃金值釘死)。"""
    c = _char(); c.fatigue = 0
    f0 = c.fatigue
    assert combat.second_breath_use(c, gd) == 0
    combat.fatigue_on_kill(c, _foe(1), gd)
    assert c.fatigue == f0 and c.active_effects == []


# R194 前 HEAD 的黃金值:同一夾具(未選運動 100 的諾德戰士·6 隻 10 血山賊逐隻擊殺並被還擊·RNG(21))在 R194 前的乾淨 HEAD 與 R194 後完全相同。
# (審查指出原「零 rng」斷言從未把 rng 傳給任何函式 → 恆真;改釘死對 HEAD 的值。日後若合理改了戰鬥公式,重算並更新此值,連同 sim 基線。)
def _golden_run():
    c = _char()
    rng = RNG(21)
    out = []
    for i in range(6):
        foe = combat.spawn_creature(gd, "bandit", RNG(100 + i))
        foe.health = foe.max_health = 10
        foe.resist = {}
        for _ in range(40):
            if not combat.is_alive(foe):
                break
            combat.player_attack_cost(c, gd)
            ev = combat.resolve_attack(c, foe, gd, rng)
            out.append("K" if not combat.is_alive(foe) else ("H" if ev["hit"] else "m"))
            if combat.is_alive(foe):
                combat.resolve_attack(foe, c, gd, rng)           # 敵人還擊(消耗 rng、可能扣血)
    return "".join(out), round(c.fatigue, 3), round(c.health), repr(rng.random())


GOLDEN = ('KmmHmKKmmHmKHKK', 127.5, 4930, '0.8939658303409488')   # 取自乾淨 HEAD(R194 前)


def test_unselected_battle_is_byte_identical_to_the_pre_r194_head_golden():
    assert _golden_run() == GOLDEN


# --- 殺勢回體 ----------------------------------------------------------------------
def _hits(c, foe_factory, seeds=range(80)):
    """對 1 血敵人揮擊,逐種子回 (命中?, 擊殺?, 揮擊前後體力差);體力預設半滿(不被夾 max)。"""
    out = []
    for s in seeds:
        c.fatigue = c.max_fatigue * 0.5
        foe = foe_factory()
        f0 = c.fatigue
        ev = combat.resolve_attack(c, foe, gd, RNG(s))
        out.append((ev["hit"], not combat.is_alive(foe), c.fatigue - f0))
    return out


def test_kill_refunds_pct_of_max_fatigue_only_on_a_kill():
    c = _char("frugal")
    res = _hits(c, lambda: _foe(1))
    kills = [d for hit, dead, d in res if dead]
    misses = [d for hit, dead, d in res if not dead]
    assert len(kills) >= 30 and len(misses) >= 1                        # 兩支都真的走到(防空測)
    assert all(abs(d - PCT * c.max_fatigue) < 1e-6 for d in kills)      # 擊殺 → +2% 最大體力
    assert all(d == 0 for d in misses)                                  # 落空 → 不回
    res2 = _hits(c, lambda: _foe(10 ** 6))                              # 命中但沒殺死 → 不回
    assert all(d == 0 for hit, dead, d in res2)
    ctl = _hits(_char(), lambda: _foe(1))                               # 對照:未選 → 擊殺也不回
    assert all(d == 0 for hit, dead, d in ctl) and any(dead for hit, dead, d in ctl)


def test_summoned_minions_do_not_refund_and_refund_clamps_at_max():
    c = _char("frugal")
    res = _hits(c, lambda: _foe(1, summoned=True))                      # 召喚爪牙(R134·不計擊殺)
    assert any(dead for hit, dead, d in res) and all(d == 0 for hit, dead, d in res)
    c.fatigue = c.max_fatigue - 1
    foe = _foe(1)
    for s in range(200):                                                # 接近滿時夾 max
        c.fatigue = c.max_fatigue - 1
        foe = _foe(1)
        ev = combat.resolve_attack(c, foe, gd, RNG(s))
        if not combat.is_alive(foe):
            assert c.fatigue == c.max_fatigue
            return
    raise AssertionError("樣本內沒有任何一擊擊殺")


def test_spell_and_companion_kills_do_not_refund():
    """親手 = 玩家武器攻擊(resolve_attack):法術擊殺不走該 hook → 不回體(對照:同法術未選/已選的體力差相同)。"""
    gd2 = get_gamedata()
    def run(h100):
        c = build_character(gd2, name="法", sex="female", race="altmer", birthsign="mage", class_id="mage")
        c.skills["athletics"] = 100
        if h100:
            mastery.choose(c, gd2, "athletics_100", h100)
        stats.recompute_max_resources(c, gd2, restore_full=True)
        c.fatigue = c.max_fatigue * 0.5
        foe = combat.spawn_creature(gd2, "mudcrab", RNG(1)); foe.health = 1
        f0 = c.fatigue
        ev = magic.cast(c, gd2, "flames", RNG(3), target=foe)
        return ev, foe, c.fatigue - f0
    ev_a, foe_a, d_a = run("frugal")
    ev_b, foe_b, d_b = run(None)
    assert not combat.is_alive(foe_a) and not combat.is_alive(foe_b)    # 兩邊都真的殺死了
    assert abs(d_a - d_b) < 1e-9                                        # 已選與未選的體力變化相同 = 法術擊殺沒回體
    calls = []
    orig = combat.fatigue_on_kill
    combat.fatigue_on_kill = lambda p, e, g: calls.append(p) or orig(p, e, g)
    try:
        comp = combat.spawn_creature(gd, "wolf", RNG(2))                # 同伴/怪物當攻擊方:resolve_attack 的玩家擊殺 hook 不被呼叫
        killed = False
        for s in range(80):
            victim = _foe(1)
            combat.resolve_attack(comp, victim, gd, RNG(s))
            killed = killed or not combat.is_alive(victim)
        assert killed and calls == []                                   # spy 直驗(審查補:原斷言只驗體力不變,恆真)
        c = _char("frugal")
        for s in range(80):
            victim = _foe(1)
            combat.resolve_attack(c, victim, gd, RNG(s))
        assert calls and all(p is c for p in calls)                     # 玩家擊殺才呼叫,且只呼叫玩家
    finally:
        combat.fatigue_on_kill = orig


def test_kill_is_a_transition_so_corpses_and_late_enchant_kills_are_handled():
    """審查:擊殺 = 這一擊使目標『活→死』。①對已死目標再打(命中也)不得重複回體;②武器附魔(absorb_health)在同一擊內補的最後一刀算擊殺。"""
    c = _char("frugal")
    corpse = _foe(1)
    for s in range(200):                                                # 先殺死
        if not combat.is_alive(corpse):
            break
        combat.resolve_attack(c, corpse, gd, RNG(s))
    assert not combat.is_alive(corpse)
    reps = 0
    for s in range(60):
        c.fatigue = c.max_fatigue * 0.5
        f0 = c.fatigue
        ev = combat.resolve_attack(c, corpse, gd, RNG(s))               # 對屍體再打(直接呼叫,繞過各路徑的 is_alive 守衛)
        reps += 1 if ev["hit"] else 0
        assert c.fatigue == f0
    assert reps >= 20                                                   # 防空測:確實命中過屍體
    # ② 莫拉格巴爾之鎚:enemy hp = 基礎傷害 + 1 → 基礎傷害打不死,附魔吸血補的最後一刀才殺死
    late = 0
    for s in range(300):
        mace = _char("frugal")
        mace.skills["blunt"] = 100
        mace.weapon = "mace_of_molag_bal"
        ctl = _foe(10 ** 6)
        ev0 = combat.resolve_attack(mace, ctl, gd, RNG(s))
        if not ev0["hit"]:
            continue
        foe = _foe(ev0["damage"] + 1)
        mace.fatigue = mace.max_fatigue * 0.5
        f0 = mace.fatigue
        ev = combat.resolve_attack(mace, foe, gd, RNG(s))
        if ev["hit"] and ev["damage"] == ev0["damage"] and not combat.is_alive(foe):
            late += 1
            assert abs((mace.fatigue - f0) - PCT * mace.max_fatigue) < 1e-6
    assert late >= 5                                                    # 附魔補刀擊殺確實出現並回體


# --- main.run_battle 接線 ------------------------------------------------------------
def _drive(c, chooser, foe=None, **kw):
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    foe = foe if foe is not None else _foe()
    orig = main._choose_combat_action
    main._choose_combat_action = chooser
    try:
        res = main.run_battle(st, gd, [foe], **kw)
    finally:
        main._choose_combat_action = orig
    return res


def test_run_battle_triggers_before_the_menu_once_per_battle_and_leaves_no_residue():
    c = _char("tidal_breath"); c.fatigue = 0
    seen = []
    foe0 = _foe()
    uses = []
    orig_use = combat.second_breath_use
    combat.second_breath_use = lambda p, g: uses.append(1) or orig_use(p, g)
    def chooser(*a, **k):
        seen.append(c.fatigue)
        if len(seen) == 2:
            c.fatigue = 0                                               # 第二回合又見底 → 不應再回(一場一次)
        return {"type": "flee"} if len(seen) >= 3 else {"type": "attack", "target": foe0}
    try:
        _drive(c, chooser, foe0)
    finally:
        combat.second_breath_use = orig_use
    assert len(seen) == 3
    assert len(uses) == len(seen)                                       # 只在「玩家回合開頭、選單之前」各呼叫一次,敵方階段等處不額外呼叫(審查補)
    assert seen[0] == formulas.rest_fatigue_amount(100) + mastery.rest_bonus(c, gd)   # 第一次選單前已回氣(免耗回合:選單就看得到)
    assert seen[1] > 0 and seen[2] == 0                                 # 第二回合見底後沒再回(第三次選單讀到 0)
    assert not any(e.get("kind") == "second_breath_spent" for e in c.active_effects)   # 離戰整包清,不殘留
    c.fatigue = 0
    seen2 = []
    def chooser2(*a, **k):
        seen2.append(c.fatigue); return {"type": "flee"}
    _drive(c, chooser2)
    assert seen2[0] > 0                                                 # 新的一場可再觸發


def test_preserve_buffs_battle_strips_the_marker_so_each_dungeon_fight_is_fresh():
    c = _char("tidal_breath"); c.fatigue = 0
    c.active_effects.append({"kind": "second_breath_spent", "turns": combat.PERSISTENT_TURNS})   # 上一場地城戰鬥殘留
    seen = []
    def chooser(*a, **k):
        seen.append(c.fatigue); return {"type": "flee"}
    _drive(c, chooser, preserve_buffs=True)
    assert seen[0] > 0                                                  # 標記被剝除 → 這場仍可觸發


def test_marker_is_hidden_from_the_hud_and_incapacitated_turns_do_not_trigger():
    c = _char("tidal_breath")
    c.active_effects.append({"kind": "second_breath_spent", "turns": combat.PERSISTENT_TURNS})
    assert ui._status_tags(c) == "" and ui._status_tags_list(c) == []
    c.active_effects.clear(); c.fatigue = 0
    c.active_effects.append({"kind": "paralyze", "turns": 2})
    assert magic.is_incapacitated(c)                                    # 入戰前確實失能
    calls = []
    orig = combat.second_breath_use
    def spy(p, g):
        calls.append(magic.is_incapacitated(p)); return orig(p, g)
    combat.second_breath_use = spy
    try:
        _drive(c, lambda *a, **k: {"type": "flee"}, preserve_buffs=True)   # 🔴 須 preserve_buffs:否則入戰整包清會洗掉麻痺(審查抓到的空轉)
    finally:
        combat.second_breath_use = orig
    assert calls and not any(calls)                                     # 只在「可行動」的回合開頭才檢查(失能回合跳過)


def test_works_with_iron_shirt_draining_fatigue_to_zero():
    """鐵布衫(R193)把體力代扣到 0 的那一擊之後,下個玩家回合開頭一氣呵成照常觸發(兩個 100 階機制可並存)。"""
    c = _char("tidal_breath")
    c.skills["hand_to_hand"] = 100
    mastery.choose(c, gd, "hand_to_hand_100", "iron_shirt")
    drained = 0
    for seed in range(60):
        c.fatigue = 1.0
        ev = combat.resolve_attack(combat.spawn_creature(gd, "bandit", RNG(1)), c, gd, RNG(seed),
                                   attack={"name": "重擊", "damage": 80, "skill": 60})
        if ev["hit"] and ev["iron_absorbed"] > 0:
            drained += 1
            assert c.fatigue == 0 and combat.second_breath_ready(c, gd)   # 鐵布衫把體力抽到 0 → 下個回合開頭一氣呵成可用
            c.active_effects.clear()
    assert drained >= 20                                                # 防空測


def run():
    for name in sorted(globals()):
        if name.startswith("test_"):
            globals()[name]()
