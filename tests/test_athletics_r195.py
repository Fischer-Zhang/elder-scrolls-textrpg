"""R195 運動 50「健步如飛」:逃跑 / 潛行撤退成功率加成(原「長途健步」opt_id `marathon` 改掛 escape_bonus,兼帶舊 −0.10 旅速)。
🔴 核心紅線:
  ① 未選者逐位元組不變(formulas bonus 預設 0.0 · try_flee 擲骰序列同舊版 · gamedata=None 舊呼叫端無加成)
  ② 預覽 = 實擲(main 的撤退率預覽、實際撤退、戰中逃跑三個呼叫點都傳 gamedata)
  ③ 加成加在緩肩/夾限**之前**:慢手收益近全額、快手遞減、永不超 0.95(逃跑)/ 0.92(撤退)
  ④ 存檔向後相容:opt_id 不變;已選 marathon 的角色同時保有舊 −0.10 旅速與新脫身加成
  ⑤ 同源 getter 聚合(SUM);不動 R147 開源/節流樹形(節氣 second_wind 不碰脫身)
  ⑥ 文案防回歸:skills.json 運動說明不得再寫「格擋」(player_block_cost 無正式呼叫端)、codex 不得再寫「見底會重創」(實為線性斜坡)
"""
import io
import json
from pathlib import Path

from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, mastery, progression, stats

gd = get_gamedata()
ROOT = Path(__file__).resolve().parent.parent


def _char(**skills):
    c = build_character(gd, name="運", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(skills)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def _foe():
    return combat.spawn_creature(gd, "wolf" if "wolf" in gd.bestiary else next(iter(gd.bestiary)), RNG(1))


class _RecRNG:
    """記錄 chance(p) 收到的 p,回固定結果。"""

    def __init__(self, result=True):
        self.ps, self.result = [], result

    def chance(self, p):
        self.ps.append(p)
        return self.result


# --- 資料形狀 ---------------------------------------------------------------
def test_marathon_option_data_shape():
    node = next(n for n in mastery._nodes(gd) if n["id"] == "athletics_50")
    opts = {o["opt_id"]: o for o in node["options"]}
    assert set(opts) == {"marathon", "second_wind"}                       # opt_id 不變 → 存檔零遷移
    m = opts["marathon"]
    assert m["kind"] == "escape_bonus" and m["bonus"] == 0.15 and m["travel_bonus"] == 0.1
    assert m["name"] == "健步如飛"
    assert opts["second_wind"]["kind"] == "fatigue_cost_bonus"             # 節氣不動(第 5 題決議:先不碰續戰線)
    assert "escape_bonus" in mastery._IMPLEMENTED_KINDS                    # 白名單(否則 option 被過濾 = 死選項)
    assert len(mastery._choosable_options(node)) == 2


# --- getter:門檻 / 二選一 / 聚合 -------------------------------------------
def test_escape_bonus_getter_gates_and_exclusivity():
    c = _char(athletics=49)
    assert mastery.choose(c, gd, "athletics_50", "marathon") is None        # 門檻只認 base_skill(R21)
    assert mastery.escape_bonus(c, gd) == 0.0 and mastery.travel_factor_bonus(c, gd) == 0.0
    c.skills["athletics"] = 50
    assert mastery.escape_bonus(c, gd) == 0.0                                # 達標未選 → 0(待選不生效)
    assert mastery.choose(c, gd, "athletics_50", "marathon")
    assert mastery.escape_bonus(c, gd) == 0.15 and mastery.travel_factor_bonus(c, gd) == 0.1
    assert mastery.choose(c, gd, "athletics_50", "second_wind") is None      # 二選一:選定後不可重選
    d = _char(athletics=50)
    mastery.choose(d, gd, "athletics_50", "second_wind")
    assert mastery.escape_bonus(d, gd) == 0.0 and mastery.travel_factor_bonus(d, gd) == 0.0


def test_escape_bonus_sums_across_sources():
    """同源多節點 getter 必聚合(R35):即使日後第二個來源出現也相加,不 first-wins 遮蔽。"""
    orig = mastery._chosen_options_by_kind
    try:
        mastery._chosen_options_by_kind = (
            lambda ch, g, kind: [{"bonus": 0.15}, {"bonus": 0.10}] if kind == "escape_bonus" else orig(ch, g, kind))
        assert abs(mastery.escape_bonus(_char(), gd) - 0.25) < 1e-12
    finally:
        mastery._chosen_options_by_kind = orig


# --- 公式層:未選者逐位元組同舊版 --------------------------------------------
def test_formula_bonus_default_is_byte_identical():
    for s in (0, 20, 40, 60, 90, 140, 250):
        for a in (0, 30, 60, 100):
            for f in (0, 30, 60, 120):
                legacy = max(formulas.FLEE_FLOOR, formulas._soft_ceiling(
                    0.45 + (s + a * 0.5 - f) * 0.006, formulas.FLEE_KNEE, formulas.FLEE_WIDTH, formulas.FLEE_ASYMPTOTE))
                assert formulas.flee_chance(s, a, f) == legacy == formulas.flee_chance(s, a, f, 0.0)
    for sn in (0, 30, 100):
        for sp in (0, 40, 100):
            for fs in (0, 50, 100):
                for g in (1, 2, 5, 8):
                    legacy = max(0.10, min(0.92, (formulas.STEALTH_RETREAT_BASE + sn * 0.004 + (sp - fs) * 0.004
                                                  - max(0, g - 1) * formulas.RETREAT_GROUP_PENALTY)))
                    assert formulas.stealth_retreat_chance(sn, sp, fs, g) == legacy
                    assert formulas.stealth_retreat_chance(sn, sp, fs, g, 0.0) == legacy


# --- 公式層:加成位置(緩肩/夾限之前)與上限 ---------------------------------
def test_flee_bonus_acts_before_soft_ceiling_and_never_exceeds_cap():
    slow = formulas.flee_chance(20, 20, 60, 0.15) - formulas.flee_chance(20, 20, 60)
    assert abs(slow - 0.15) < 1e-9                                           # 慢手:未進緩肩 → 全額
    fast = formulas.flee_chance(150, 100, 40, 0.15) - formulas.flee_chance(150, 100, 40)
    assert 0 <= fast < 0.05                                                  # 快手:緩肩內遞減(不硬頂)
    # 次序釘死(審查 F1):加成在緩肩『之前』→ 速度 100/敏捷 50 對敵 50:0.9 → 0.9197;若改成緩肩之後再夾 0.95 會是 0.95
    assert abs(formulas.flee_chance(100, 50, 50) - 0.9) < 1e-9
    assert abs(formulas.flee_chance(100, 50, 50, 0.15) - 0.9197) < 1e-3
    for s in (0, 40, 90, 200):
        for b in (0.0, 0.05, 0.15, 0.30):
            assert formulas.FLEE_FLOOR <= formulas.flee_chance(s, 50, 50, b) <= formulas.FLEE_ASYMPTOTE
    xs = [formulas.flee_chance(70, 40, 50, b) for b in (0.0, 0.05, 0.10, 0.15, 0.20)]
    assert xs == sorted(xs)                                                  # bonus 越大不會更低


def test_retreat_bonus_lifts_big_groups_and_respects_cap():
    assert formulas.stealth_retreat_chance(5, 40, 60, 6) == 0.10             # 大群:原始值低於地板
    assert formulas.stealth_retreat_chance(5, 40, 60, 6, 0.15) > 0.10        # 加成讓大群也抬離地板
    # 次序釘死(審查 F1):加在夾限『之前』→ 0.14;若改成夾限之後再夾 0.92 會是 0.25
    assert abs(formulas.stealth_retreat_chance(5, 40, 60, 6, 0.15) - 0.14) < 1e-9
    assert formulas.stealth_retreat_chance(0, 30, 60, 8, 0.15) == 0.10       # 超大群:原始值深陷地板 → 加成抬不動(審查 F3:效果有限)
    # 低潛行快手(武僧)撤退端不被夾限 → 全額 +0.15;被夾限吞掉的是戰中逃跑與潛行 100 的刺客/弓手(審查 F2)
    assert abs(formulas.stealth_retreat_chance(10, 80, 45, 2, 0.15)
               - formulas.stealth_retreat_chance(10, 80, 45, 2) - 0.15) < 1e-9
    assert formulas.stealth_retreat_chance(100, 120, 40, 1, 0.15) == 0.92    # 快手:夾限吞掉(無感)
    assert formulas.stealth_retreat_chance(100, 120, 40, 1) == 0.92


# --- 戰鬥層:單一出處 / 預覽=實擲 / 舊呼叫端 ---------------------------------
def test_try_flee_uses_single_source_probability():
    c, foe = _char(athletics=50), _foe()
    r0 = _RecRNG()
    combat.try_flee(c, foe, r0, gd)
    assert r0.ps == [combat.flee_probability(c, foe, gd)]                    # 單次擲骰、機率來自單一出處
    p_unsel = r0.ps[0]
    mastery.choose(c, gd, "athletics_50", "marathon")
    r1 = _RecRNG()
    combat.try_flee(c, foe, r1, gd)
    expect = min(0.95, formulas.flee_chance(combat._speed(c), combat._agility(c), combat._speed(foe), 0.15)
                 + formulas.luck_fortune(c.attr("luck")))
    assert r1.ps == [expect] and r1.ps[0] > p_unsel
    r2 = _RecRNG()
    combat.try_flee(c, foe, r2)                                              # gamedata=None(舊呼叫端)→ 無加成
    assert r2.ps == [p_unsel]


def test_flee_probability_never_exceeds_cap_with_max_stats_and_bonus():
    """審查 F1 突變 j(bonus 加在 min(0.95) 之後)會讓速度/敏捷/幸運皆高者的逃跑率飆過 1.0。"""
    c, foe = _char(athletics=50), _foe()
    for k in ("speed", "agility", "luck"):
        c.attributes[k] = 200
    mastery.choose(c, gd, "athletics_50", "marathon")
    p = combat.flee_probability(c, foe, gd)
    assert 0.0 < p <= 0.95
    r = _RecRNG()
    combat.try_flee(c, foe, r, gd)
    assert r.ps == [p] and r.ps[0] <= 0.95
    assert combat.stealth_retreat_chance(c, [foe], gd) <= 0.92              # 撤退端亦不超夾限


def test_retreat_preview_equals_actual_roll_and_main_passes_gamedata():
    c, foes = _char(athletics=50), [_foe(), _foe()]
    pre = combat.stealth_retreat_chance(c, foes, gd)
    r = _RecRNG()
    combat.try_stealth_retreat(c, foes, r, gd)
    assert r.ps == [pre]
    mastery.choose(c, gd, "athletics_50", "marathon")
    pre2 = combat.stealth_retreat_chance(c, foes, gd)
    r2 = _RecRNG()
    combat.try_stealth_retreat(c, foes, r2, gd)
    assert r2.ps == [pre2] and pre2 > pre
    assert combat.stealth_retreat_chance(c, foes) == pre                     # gamedata=None → 無加成
    src = (ROOT / "tesrpg" / "main.py").read_text(encoding="utf-8")          # 呼叫端守衛:漏傳 gamedata → 預覽與實擲分裂
    assert "combat.stealth_retreat_chance(char, enemies, gamedata)" in src
    assert "combat.try_stealth_retreat(char, enemies, state.rng, gamedata)" in src
    assert "combat.try_flee(player, foe, state.rng, gamedata)" in src


def test_unselected_flee_roll_stream_is_legacy_identical():
    c, foe = _char(athletics=60), _foe()
    legacy_p = min(0.95, formulas.flee_chance(combat._speed(c), combat._agility(c), combat._speed(foe))
                   + formulas.luck_fortune(c.attr("luck")))
    a, b = RNG(123), RNG(123)
    got = [combat.try_flee(c, foe, a, gd) for _ in range(300)]
    want = [b.chance(legacy_p) for _ in range(300)]
    assert got == want                                                       # 未選:擲骰序列逐位元組同舊版


def test_second_wind_does_not_touch_flee():
    foe = _foe()
    p0 = combat.flee_probability(_char(athletics=50), foe, gd)
    sw = _char(athletics=50)
    mastery.choose(sw, gd, "athletics_50", "second_wind")
    assert combat.flee_probability(sw, foe, gd) == p0                        # 節氣線(續戰)與脫身線互不串味


# --- 存檔相容 ----------------------------------------------------------------
def test_old_save_marathon_keeps_both_effects():
    c = _char(athletics=60)
    c.mastery_choices = {"athletics_25": "steady_breath", "athletics_50": "marathon"}   # 舊存檔:opt_id 不變
    progression.ensure_mastery_choices(c, gd)
    assert c.mastery_choices.get("athletics_50") == "marathon"                # 不被當陳舊清掉
    assert mastery.escape_bonus(c, gd) == 0.15 and mastery.travel_factor_bonus(c, gd) == 0.1   # 舊旅速保留 + 新脫身
    assert mastery.rest_bonus(c, gd) == 8                                      # 25 勻息不受影響
    assert mastery.fatigue_cost_bonus(c, gd) == 0.0                            # 節流線未被誤開


# --- 文案防回歸 ---------------------------------------------------------------
def test_text_guards_no_stale_claims():
    sk = json.loads((ROOT / "tesrpg" / "data" / "skills.json").read_text(encoding="utf-8"))["athletics"]
    assert "隱遁" in sk["mechanic"] and "施法" in sk["mechanic"] and "格擋" not in sk["mechanic"]
    codex = (ROOT / "tesrpg" / "data" / "codex.json").read_text(encoding="utf-8")
    assert "見底會重創" not in codex


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
