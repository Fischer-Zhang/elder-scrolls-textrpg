"""R197 子提交 (a):事件經驗升點提示 + 機率顯示取整統一。

🔴 核心紅線:
  ① `events.apply_effects` 的 skill_xp / forage_pool 分支不得再丟棄 `progression.use_skill` 的回傳:
     回傳 dict 多一個 `skill_events`;`main.run_event` 必須顯示(原本事件經驗造成的升點 / 可升級 / 里程碑通知全被吞)。
  ② 對話通路同理:`_apply_topic_effects` → `resolve_topic` / `_do_pump` 把 effects 的 skill_events 往上傳。
  ③ 所有「給玩家看的機率」走 `ui.pct`(四捨五入),不得再用 `int(p * 100)` 截斷(浮點:0.58 * 100 = 57.99…)。
🔴 零規則改動:只改顯示與回傳;不碰任何數值、存檔、戰鬥公式。
"""
import io
import re
from pathlib import Path

from rich.console import Console
import tesrpg.ui.console as ui

from tesrpg import formulas, main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import dialogue, events, stats

gd = get_gamedata()
ROOT = Path(__file__).resolve().parent.parent


class _RecRNG(RNG):
    """chance(p) 一律回固定結果;其餘走真 RNG。"""

    def __init__(self, seed=0, result=True):
        super().__init__(seed)
        self.result = result

    def chance(self, p):
        return self.result


def _char():
    c = build_character(gd, name="客", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.location_id = "imperial_road"
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def _near_levelup(c, skill, level, margin=0.05):
    """把技能設在 level,經驗只差 margin 就升下一級(任何 ≥ margin 的經驗灌注都會升)。"""
    c.skills[skill] = level
    c.skill_xp[skill] = formulas.skill_threshold(level) - margin


def _ups(skill_events):
    return [(e["skill"], e["level"]) for e in skill_events if e["type"] == "skill_up"]


# --- ① events.apply_effects -------------------------------------------------
def test_skill_xp_effect_returns_skill_up_when_it_crosses_a_level():
    c = _char()
    st = GameState(player=c, time=GameTime())
    _near_levelup(c, "athletics", 30)
    res = events.apply_effects(st, gd, [{"type": "skill_xp", "skill": "athletics", "amount": 0.6}], RNG(0))
    assert set(res) == {"messages", "combat", "skill_events"}
    assert _ups(res["skill_events"]) == [("athletics", 31)]
    # 沒跨門檻 → 無通知(不憑空造訊息)
    c.skill_xp["athletics"] = 0.0
    res = events.apply_effects(st, gd, [{"type": "skill_xp", "skill": "athletics", "amount": 0.6}], RNG(0))
    assert res["skill_events"] == []


def test_forage_pool_effect_returns_skill_events_too():
    c = _char()
    st = GameState(player=c, time=GameTime())
    _near_levelup(c, "scout", 20)
    seed = next((s for s in range(60) if events.forage_pool_draw(c, gd, "ashland", RNG(s))), None)
    assert seed is not None, "找不到會採到東西的種子 → 此測試會空轉"
    res = events.apply_effects(st, gd, [{"type": "forage_pool", "pool": "ashland"}], RNG(seed))
    assert ("scout", 21) in _ups(res["skill_events"])               # 採集練偵查 → 升點通知


# --- ① main.run_event 真的顯示 -----------------------------------------------
def test_run_event_prints_the_skill_up_notification():
    c = _char()
    _near_levelup(c, "athletics", 30)
    st = GameState(player=c, time=GameTime(), rng=_RecRNG(result=True))
    saved_console, saved_menu = ui.console, ui.menu
    buf = io.StringIO()
    ui.console = Console(file=buf, force_terminal=False, color_system=None, width=100)   # 純文字(無 ANSI 色碼切斷字串)
    ui.menu = lambda title, options, allow_back=False: options[0][0]        # skyrim_blizzard 第 0 項 = 運動檢定
    try:
        M.run_event(st, gd, "skyrim_blizzard")
    finally:
        ui.console, ui.menu = saved_console, saved_menu
    out = buf.getvalue()
    assert "運動" in out and "提升到 31" in out, out[-300:]
    assert c.skills["athletics"] == 31


# --- ② 對話通路 -------------------------------------------------------------
def _dialogue_setup():
    c = _char()
    st = GameState(player=c, time=GameTime(), rng=_RecRNG(result=True))
    npc_id = next(iter(gd.npcs))
    ctx = dialogue.talk_ctx(st, gd, npc_id)
    return c, st, npc_id, ctx


_XP_EFFECTS = [{"type": "skill_xp", "skill": "athletics", "amount": 0.6}]


def test_dialogue_topic_effects_carry_skill_events_up():
    c, st, npc_id, ctx = _dialogue_setup()
    _near_levelup(c, "athletics", 30)
    r = dialogue._apply_topic_effects(st, gd, _XP_EFFECTS, ctx)
    assert _ups(r["skill_events"]) == [("athletics", 31)]
    assert dialogue._apply_topic_effects(st, gd, [], ctx)["skill_events"] == []          # 無 effects → 空,鍵仍在
    _near_levelup(c, "athletics", 30)
    res = dialogue.resolve_topic(st, gd, npc_id, {"id": "t_r197", "effects": _XP_EFFECTS}, ctx, RNG(0))
    assert _ups(res["skill_events"]) == [("athletics", 31)]                              # resolve_topic 不再硬寫 []


def test_pump_secret_effects_merge_their_skill_events_with_practice_events():
    c, st, npc_id, ctx = _dialogue_setup()
    _near_levelup(c, "athletics", 30)                       # 效果練運動;套話本身練口才 → 兩種通知來源分得開
    topic = {"action": "pump", "secret": {"text": "x", "effects": _XP_EFFECTS}}
    r = dialogue._do_pump(st, gd, npc_id, topic, ctx, _RecRNG(result=True))
    assert r["ok"] is True
    assert ("athletics", 31) in _ups(r["skill_events"])


# --- ③ 取整 ----------------------------------------------------------------
def test_pct_rounds_instead_of_truncating():
    assert int(0.58 * 100) == 57 and ui.pct(0.58) == 58     # 浮點:0.58 * 100 = 57.99999999999999
    p = 0.5 + (1 - 35) / 100.0                              # 事件檢定的真實算式(難度 35、運動 1):0.15999999999999998
    assert int(p * 100) == 15 and ui.pct(p) == 16
    assert ui.pct(0.0) == 0 and ui.pct(1.0) == 100 and ui.pct(0.5) == 50
    assert isinstance(ui.pct(0.73), int)


def test_main_has_no_truncating_probability_display_left():
    """原始碼守衛:機率顯示一律 ui.pct;不得再有 int(<*_chance(...)> * 100) / int(ch*100) 這類截斷寫法。
    (非機率的 int(...*100),如卸力比例 / 加價 %,不在此限。)"""
    src = (ROOT / "tesrpg" / "main.py").read_text(encoding="utf-8")
    bad = [ln.strip()[:90] for ln in src.splitlines() if re.search(r"int\((?:[\w.]*chance[\w]*\(|ch\s*\*)", ln)]
    assert not bad, bad
    assert src.count("ui.pct(") >= 10                       # 9 處機率顯示 + 事件檢定 chip(R196)
    # 事件 chip 與其他機率顯示同口徑
    c = _char()
    st = GameState(player=c, time=GameTime())
    chk = gd.events["highwayman"]["options"][1]["check"]
    assert M._event_check_chips(st, {"check": chk})[0]["text"] == f"成功率 {ui.pct(events.check_chance(c, chk))}%"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
