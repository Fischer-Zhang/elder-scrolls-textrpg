"""R227 訓練每級限次:訓練師每個角色等級最多教 5 次(每次 +1 技能等級;升級確認時歸零)—— 限制「金幣換實力」。

緣起:R227 前置量測(sim_arrest 第 4 段)—— 不限次時「玩 + 賺錢買訓練」比純親自玩快 4.4~5.5 倍;使用者拍板 5 次/級(壓到約 1.4~1.6 倍)。
守衛:
  A 單一出處:formulas.TRAININGS_PER_LEVEL(使用者拍板 5,寫死字面值守住)· world.trainings_left / record_training(壞值夾限)
  B 真流程(action_trainer,腳本化 ui):首次購買與「↻ 再訓練」都計次、買滿 5 次後不再扣款不再加技能;選單標題顯示剩餘額度且 = 函式;
    用完時擋下的訊息優先於「金幣不足」;宗師訓練與一般訓練同額度
  C 重置:只有升級確認(progression.apply_level_up)會歸零;升級失敗(未達條件)不動
  D 存檔:往返 / 舊存檔沒有這欄 → 0 / 壞值夾回 0
  E 玩家文字:圖鑑 / README 的次數與常數一致
  F 突變下會紅(限次失效 / 不記次 / 預覽恆為滿 / 升級不重置 / 標題不顯示 …)
"""
import io
import json
import pathlib

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import formulas
from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models.character import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import progression, world

gd = get_gamedata()
LOC = "whiterun"


def _state(gold=100000, loc=LOC):
    c = build_character(gd, name="學", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    c.location_id, c.gold = loc, gold
    return GameState(player=c, time=GameTime(), rng=RNG(3)), c


def _trainable(loc=LOC):
    """(spec, sid):此城訓練師有得教、且一般上限 < 宗師線的第一個技能。"""
    spec = world.trainer_specs(gd, loc)[0]
    return spec, world.trainer_skills(gd, loc, spec)[0]


def _master_spot():
    """找一個有宗師之技(上限 > 一般訓練師上限)的 (地點, 類別, 技能)。"""
    for loc, d in gd.world["locations"].items():
        if "trainer" not in d.get("services", []):
            continue
        for spec in world.trainer_specs(gd, loc):
            for sid in world.trainer_skills(gd, loc, spec):
                if world.trainer_cap(gd, loc, sid) > formulas.TRAINER_CAP:
                    return loc, spec, sid
    raise AssertionError("找不到宗師之技(資料變了?)")


class _Trainer:
    """腳本化 ui:依標題回答(類別選單 → spec;技能選單 → sid,最多 rounds 次,之後回 None = 返回);confirm 預設 True。"""

    def __init__(self, spec, sid, rounds=1, confirm=True):
        self.spec, self.sid, self.rounds, self.confirm_ans = spec, sid, rounds, confirm
        self.asked, self.titles, self.msgs, self.confirms = 0, [], [], []

    def menu(self, title, options, allow_back=False, **kw):
        self.titles.append(title)
        assert len(self.titles) <= 40, "訓練選單被反覆開啟 40 次以上 = 流程空轉"
        if title.startswith("向訓練師學哪一類"):
            return self.spec if self.asked < self.rounds else None
        if title.startswith("訓練哪項技能"):
            if self.asked < self.rounds:
                self.asked += 1
                return self.sid
            return None
        return None

    def confirm_fn(self, prompt, *a, **k):
        self.confirms.append(prompt)
        return self.confirm_ans


def _run_trainer(st, loc, spec, sid, rounds=1, confirm=True):
    script = _Trainer(spec, sid, rounds, confirm)
    saved = (ui.menu, ui.confirm, ui.message, ui.show_events)
    ui.menu, ui.confirm = script.menu, script.confirm_fn
    ui.message = lambda text, **k: script.msgs.append(text)
    ui.show_events = lambda *a, **k: None
    try:
        M.action_trainer(st, gd)
    finally:
        ui.menu, ui.confirm, ui.message, ui.show_events = saved
    return script


def _expected_cost(st, c, sid, n):
    lv, total = c.skill(sid), 0
    for _ in range(n):
        total += world.service_price(c, gd, world.train_cost(lv))
        lv += 1
    return total


# --- A 單一出處 ---------------------------------------------------------------------
def test_constant_is_five_and_the_allowance_function_clamps_bad_values():
    assert formulas.TRAININGS_PER_LEVEL == 5                                   # 使用者拍板(寫死字面值:突變會改常數,測試不能跟著動)
    st, c = _state()
    assert world.trainings_left(c) == 5
    for used, want in ((0, 5), (1, 4), (4, 1), (5, 0), (6, 0), (10 ** 9, 0), (-3, 5), ("x", 5), (None, 5), (2.9, 3)):
        c.trainings_this_level = used
        assert world.trainings_left(c) == want, (used, world.trainings_left(c))
    c.trainings_this_level = 0
    for i in range(1, 8):
        world.record_training(c)
        assert c.trainings_this_level == i and world.trainings_left(c) == max(0, 5 - i)
    c.trainings_this_level = "壞值"
    world.record_training(c)
    assert c.trainings_this_level == 1                                         # 壞值從 0 起算


# --- B 真流程 -----------------------------------------------------------------------
def test_first_buy_and_the_again_loop_both_count_and_stop_at_five():
    st, c = _state()
    spec, sid = _trainable()
    base, gold0 = c.skill(sid), c.gold
    expect = _expected_cost(st, c, sid, 5)
    script = _run_trainer(st, LOC, spec, sid)                                  # 首次購買 +1,之後 ↻ 全部確認 → 應在第 5 次停
    assert c.skill(sid) == base + 5 and c.trainings_this_level == 5 and world.trainings_left(c) == 0, (c.skill(sid), base)
    assert c.gold == gold0 - expect                                            # 只付了 5 級的錢
    assert len(script.confirms) == 4 and any("額度用完" in m for m in script.msgs), (len(script.confirms), script.msgs)
    assert "本級額度剩 4 次" in script.confirms[0] and "本級額度剩 1 次" in script.confirms[-1]


def test_an_exhausted_allowance_never_charges_and_beats_the_not_enough_gold_message():
    st, c = _state()
    spec, sid = _trainable()
    _run_trainer(st, LOC, spec, sid)
    lv, gold = c.skill(sid), c.gold
    script = _run_trainer(st, LOC, spec, sid)                                  # 額度已用完:再選同一技能
    assert c.skill(sid) == lv and c.gold == gold and c.trainings_this_level == 5
    assert any("學習已到極限" in m for m in script.msgs) and not script.confirms
    c.gold = 0                                                                 # 沒錢又沒額度:先講額度(不是「金幣不足」)
    script = _run_trainer(st, LOC, spec, sid)
    assert any("學習已到極限" in m for m in script.msgs) and not any("金幣不足" in m for m in script.msgs)


def test_menu_titles_show_the_remaining_allowance_and_equal_the_function():
    st, c = _state()
    spec, sid = _trainable()
    script = _run_trainer(st, LOC, spec, sid, rounds=2, confirm=False)         # 買 1 次(↻ 拒絕)→ 再進選單
    skill_titles = [t for t in script.titles if t.startswith("訓練哪項技能")]
    assert "剩 5/5" in skill_titles[0] and "剩 4/5" in skill_titles[1], skill_titles
    assert c.trainings_this_level == 2                                         # 兩輪各買 1 次
    c.trainings_this_level = 5
    script = _run_trainer(st, LOC, spec, sid, rounds=0)
    title = next(t for t in script.titles if t.startswith("訓練哪項技能") or t.startswith("向訓練師學哪一類"))
    assert "剩 0/5" in title and "用完了" in title
    for used in range(0, 6):                                                   # 預覽 = 函式
        c.trainings_this_level = used
        script = _run_trainer(st, LOC, spec, sid, rounds=0)
        t = next(t for t in script.titles if "本級訓練額度" in t)
        assert f"剩 {world.trainings_left(c)}/5" in t, (used, t)


def test_master_trainings_share_the_same_allowance():
    loc, spec, sid = _master_spot()
    st, c = _state(loc=loc)
    c.skills[sid] = formulas.TRAINER_CAP                                       # 已在一般上限 → 只有宗師能再教
    script = _run_trainer(st, loc, spec, sid)
    assert c.skill(sid) == formulas.TRAINER_CAP + 5 and c.trainings_this_level == 5, (c.skill(sid), c.trainings_this_level)
    st, c = _state(loc=loc)                                                    # 先在一般訓練用掉 3 次 → 宗師只剩 2 次
    c.trainings_this_level = 3
    c.skills[sid] = formulas.TRAINER_CAP
    _run_trainer(st, loc, spec, sid)
    assert c.skill(sid) == formulas.TRAINER_CAP + 2 and c.trainings_this_level == 5


# --- C 重置 -------------------------------------------------------------------------
def test_only_a_confirmed_level_up_restores_the_allowance():
    st, c = _state()
    spec, sid = _trainable()
    _run_trainer(st, LOC, spec, sid)
    assert world.trainings_left(c) == 0
    assert Character.from_dict(c.to_dict()).trainings_this_level == 5          # 存檔往返不會把額度「洗掉」
    try:
        progression.apply_level_up(c, gd, {"endurance": 5})                    # 尚未達升級條件 → 拋例外,額度不動
    except ValueError:
        pass
    assert c.trainings_this_level == 5
    progression.ensure_level_xp(c)
    c.level_xp = formulas.levelup_xp_threshold(c.level)                        # 滿足升級條件
    assert c.can_level_up()
    lv0 = c.level
    progression.apply_level_up(c, gd, {"endurance": 5})
    assert c.level == lv0 + 1 and c.trainings_this_level == 0 and world.trainings_left(c) == 5
    gold = c.gold
    _run_trainer(st, LOC, spec, sid)                                           # 新的一級又能訓練
    assert c.gold < gold and c.trainings_this_level == 5


def test_a_training_is_exactly_one_level_whatever_the_xp_multipliers():
    """R227 審查 F1:訓練灌的 xp 曾被睡飽 ×1.25 / 專精 ×1.2 / 竊賊座放大 → 5 次實得 +6~+8 級、還能衝過訓練師上限 75。現在剛好 +1。"""
    spec, sid = _trainable()
    for wr in (False, True):
        for specz in (None, "combat", "magic", "stealth"):
            st, c = _state()
            c.well_rested, c.specialization = wr, specz
            base, xp0 = c.skill(sid), c.skill_xp.get(sid, 0.0)
            _run_trainer(st, LOC, spec, sid)
            assert c.skill(sid) == base + 5 and c.trainings_this_level == 5, (wr, specz, c.skill(sid) - base)
            assert abs(c.skill_xp.get(sid, 0.0) - xp0) < 1e-9, (wr, specz)          # 餘量不被放大、也不憑空增減
    # 已有大量餘量(離下一級只差一點)+ 睡飽:買 1 次仍只 +1(舊行為會 +2)
    st, c = _state()
    c.well_rested = True
    c.skill_xp[sid] = formulas.skill_threshold(c.skill(sid)) - 0.01
    base = c.skill(sid)
    c.trainings_this_level = formulas.TRAININGS_PER_LEVEL - 1                         # 只剩 1 次額度 → 恰好買 1 次
    _run_trainer(st, LOC, spec, sid)
    assert c.skill(sid) == base + 1, c.skill(sid) - base
    # 不會衝過訓練師上限:技能 74、餘量 0.6 個門檻、睡飽 → 買 1 次到 75 為止(舊行為 76)
    loc, mspec, msid = LOC, spec, sid
    st, c = _state()
    c.well_rested = True
    c.skills[sid] = formulas.TRAINER_CAP - 1
    c.skill_xp[sid] = 0.6 * formulas.skill_threshold(formulas.TRAINER_CAP - 1)
    cap = world.trainer_cap(gd, LOC, sid)
    if cap == formulas.TRAINER_CAP:                                                    # 此城對該技能沒有宗師 → 走一般上限
        _run_trainer(st, LOC, spec, sid)
        assert c.skill(sid) == formulas.TRAINER_CAP, c.skill(sid)


def test_the_raw_flag_only_skips_the_multipliers_play_xp_is_unchanged():
    """`raw=True` 只給訓練師用;做事給 xp 的呼叫端(預設 raw=False)倍率照舊。"""
    st, c = _state()
    spec, sid = _trainable()
    sk_spec = gd.skills[sid].get("spec")
    assert sk_spec is not None                                                          # 前提:該技能有專精系(否則 None == None 會誤中專精倍率)
    c.well_rested, c.specialization = True, None
    c.skill_xp[sid] = 0.0
    progression.use_skill(c, gd, sid, 1.0)
    assert abs(c.skill_xp[sid] - formulas.WELL_RESTED_XP_MULT) < 1e-9, c.skill_xp[sid]   # 只睡飽:×1.25(非竊賊座 → 潛行系也 ×1.0)
    c.skill_xp[sid] = 0.0
    progression.use_skill(c, gd, sid, 1.0, raw=True)
    assert abs(c.skill_xp[sid] - 1.0) < 1e-9                                           # raw:不乘任何倍率
    c.well_rested, c.specialization = True, sk_spec
    c.skill_xp[sid] = 0.0
    progression.use_skill(c, gd, sid, 1.0)
    assert c.skill_xp[sid] > formulas.WELL_RESTED_XP_MULT - 1e-9                       # 預設:睡飽 × 專精 都乘(play 路徑不變)


def test_being_too_poor_does_not_burn_an_allowance_slot():
    """審查 F4:金幣不足的那一下不得扣額度(窮的時候點一下就白白燒掉一次)。"""
    st, c = _state(gold=0)
    spec, sid = _trainable()
    lv = c.skill(sid)
    script = _run_trainer(st, LOC, spec, sid)
    assert any("金幣不足" in m for m in script.msgs)
    assert c.skill(sid) == lv and c.trainings_this_level == 0 and world.trainings_left(c) == 5


def test_each_confirmed_level_up_restores_the_allowance_even_when_two_are_pending():
    """審查 F4:連升兩級時,每一次升級確認各自歸零(不是「全升完才歸零」)。"""
    st, c = _state()
    spec, sid = _trainable()
    _run_trainer(st, LOC, spec, sid)
    assert world.trainings_left(c) == 0
    progression.ensure_level_xp(c)
    c.level_xp = formulas.levelup_xp_threshold(c.level) + formulas.levelup_xp_threshold(c.level + 1)   # 兩級的量
    progression.apply_level_up(c, gd, {"endurance": 5})
    assert c.can_level_up(), "前提:第一次升級後仍可再升一級"
    assert c.trainings_this_level == 0                                                  # 第一級就恢復
    _run_trainer(st, LOC, spec, sid)
    assert c.trainings_this_level == 5
    progression.apply_level_up(c, gd, {"endurance": 5})
    assert c.trainings_this_level == 0                                                  # 第二級再恢復


# --- D 存檔 -------------------------------------------------------------------------
def test_trainings_this_level_save_round_trip_old_saves_and_bad_values():
    st, c = _state()
    assert Character.from_dict(c.to_dict()).trainings_this_level == 0
    c.trainings_this_level = 3
    assert Character.from_dict(c.to_dict()).trainings_this_level == 3
    d = c.to_dict()
    d.pop("trainings_this_level")
    assert Character.from_dict(d).trainings_this_level == 0                    # 舊存檔沒有這欄 → 滿額 5 次
    for bad in (-1, "x", 2.5, None, True, [1]):
        d = c.to_dict()
        d["trainings_this_level"] = bad
        assert Character.from_dict(d).trainings_this_level == 0, bad


# --- E 玩家看得到的文字 ---------------------------------------------------------------
def test_player_facing_text_matches_the_constant():
    root = pathlib.Path(__file__).resolve().parent.parent
    codex = json.dumps(json.load(open(root / "tesrpg" / "data" / "codex.json", encoding="utf-8")), ensure_ascii=False)
    readme = (root / "README.md").read_text(encoding="utf-8")
    n = formulas.TRAININGS_PER_LEVEL
    assert f"每個角色等級最多教你 {n} 次" in codex and f"每個角色等級最多買 {n} 次" in readme


# --- F 突變 -------------------------------------------------------------------------
def _swap(obj, name, value, probes):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        for probe in probes:
            probe()
    except AssertionError:                     # 只認斷言失敗(吞任何例外會讓突變被意外錯誤「抓到」)
        return False
    finally:
        setattr(obj, name, old)
    return True


def test_guards_fail_under_mutation():
    flow = (test_first_buy_and_the_again_loop_both_count_and_stop_at_five,
            test_an_exhausted_allowance_never_charges_and_beats_the_not_enough_gold_message)
    assert not _swap(formulas, "TRAININGS_PER_LEVEL", 10 ** 6, flow + (test_constant_is_five_and_the_allowance_function_clamps_bad_values,))
    assert not _swap(formulas, "TRAININGS_PER_LEVEL", 6, (test_constant_is_five_and_the_allowance_function_clamps_bad_values,
                                                          test_player_facing_text_matches_the_constant))
    assert not _swap(world, "record_training", lambda char: None, flow)                                   # 買了不記次
    assert not _swap(world, "trainings_left", lambda char: 5, flow + (test_menu_titles_show_the_remaining_allowance_and_equal_the_function,))   # 預覽恆為滿
    assert not _swap(M, "_training_note", lambda char: "", (test_menu_titles_show_the_remaining_allowance_and_equal_the_function,))   # 標題不顯示額度
    real_up = progression.apply_level_up

    real_use = progression.use_skill

    def _ignores_raw(char, gamedata, skill_id, xp, raw=False):                    # 訓練又吃倍率(F1 修前行為)
        return real_use(char, gamedata, skill_id, xp)
    assert not _swap(progression, "use_skill", _ignores_raw, (test_a_training_is_exactly_one_level_whatever_the_xp_multipliers,))
    def _no_reset(char, gamedata, attribute_points):
        keep = char.trainings_this_level
        r = real_up(char, gamedata, attribute_points)
        char.trainings_this_level = keep
        return r
    assert not _swap(progression, "apply_level_up", _no_reset, (test_only_a_confirmed_level_up_restores_the_allowance,))   # 升級不重置

    def _resets_on_failure(char, gamedata, attribute_points):                # 升級失敗也重置(額度可被「空升級」洗掉)
        char.trainings_this_level = 0
        return real_up(char, gamedata, attribute_points)
    assert not _swap(progression, "apply_level_up", _resets_on_failure, (test_only_a_confirmed_level_up_restores_the_allowance,))


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
