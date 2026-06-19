"""血月詛咒深化(R50)單元測試:月相 + 狼人主動變身 + 雙血脈識破圍捕。

涵蓋:月相純推導/決定性/窗、滿月免冷卻 + 時程加成、平時(utility)主動變身 + 變回人形、
吸血鬼/狼人識破 → 衛兵圍捕(patch run_battle/ui/rng)、月相連動(滿月識破↑/新月進食↓)、
零新存檔欄(月相不入檔)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import lycanthropy, moons, powers, vampirism


def _state(seed=1, hour=12, race="nord"):
    gd = get_gamedata()
    c = build_character(gd, name="W", sex="male", race=race, birthsign="warrior", class_id="warrior")
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


def _advance_until(st, pred, limit=48):
    for _ in range(limit):
        if pred():
            return True
        st.time.advance(24)
    return False


def _today(st):
    return st.time.absolute_hours() // 24


# --- 月相純推導 --------------------------------------------------------
def test_moon_phase_deterministic_and_cycle():
    gd, c, st = _state()
    assert moons.phase_name(st) == moons.phase_name(st)          # 同一時間恆同相
    p0 = moons.phase_index(st)
    st.time.advance(moons.LUNAR_PERIOD_DAYS * 24)
    assert moons.phase_index(st) == p0                          # 整週期相位回歸


def test_moon_windows_one_full_one_new_per_cycle():
    gd, c, st = _state()
    fulls = news = 0
    for _ in range(moons.LUNAR_PERIOD_DAYS):
        fulls += moons.is_full_moon(st)
        news += moons.is_new_moon(st)
        st.time.advance(24)
    assert fulls == moons._DAYS_PER_PHASE == 3                  # 每週期恰一段滿月(3 日)
    assert news == moons._DAYS_PER_PHASE == 3                   # 每週期恰一段新月(3 日)
    assert not (moons.is_full_moon(st) and moons.is_new_moon(st))   # 互斥


def test_moon_accepts_state_or_time():
    gd, c, st = _state()
    assert moons.phase_name(st) == moons.phase_name(st.time)    # 接受 state 或 GameTime


# --- 滿月免冷卻 + 時程加成 + 平時主動變身 -------------------------------
def test_full_moon_free_transform_and_duration_bonus():
    gd, c, st = _state()
    lycanthropy.contract(c, st, gd)
    assert _advance_until(st, lambda: moons.is_full_moon(st))
    base = lycanthropy.beast_duration(c)
    assert lycanthropy.effective_duration(c, st) == base + lycanthropy.FULL_MOON_DURATION_BONUS
    powers.use(c, st, gd)                                       # 滿月變身(設當日冷卻)
    assert lycanthropy.is_beast(c, st)
    rem = c.beast_form_until - st.time.absolute_hours()
    assert rem == base + lycanthropy.FULL_MOON_DURATION_BONUS   # 獸形時程含滿月加成
    lycanthropy.revert(c, st, gd)
    assert powers.available(c, st, gd, "combat")               # 滿月 → 同日仍可再變身(免冷卻)


def test_non_full_moon_daily_cooldown_blocks_second():
    gd, c, st = _state()
    lycanthropy.contract(c, st, gd)
    assert _advance_until(st, lambda: not moons.is_full_moon(st))
    assert not lycanthropy.has_hircine_ring(c, gd)
    powers.use(c, st, gd)                                       # 非滿月變身 → 記當日冷卻
    lycanthropy.revert(c, st, gd)
    assert not powers.available(c, st, gd, "combat")           # 非滿月、同日第二次擋
    assert not powers.available(c, st, gd, "utility")


def test_active_transform_in_utility_context_and_revert():
    gd, c, st = _state()
    lycanthropy.contract(c, st, gd)
    assert powers.usable_in(c, st, gd, "utility")              # 平時(野外/城鎮)可主動變身
    base_str = c.base_attr("strength")
    powers.use(c, st, gd)                                       # 非戰鬥變身
    assert lycanthropy.is_beast(c, st)
    assert c.attr("strength") > base_str                       # werewolf_attr_bonus 生效
    assert c.base_attr("strength") == base_str                 # 🔴 不寫 base
    lycanthropy.revert(c, st, gd)
    assert not lycanthropy.is_beast(c, st)
    assert c.werewolf_attr_bonus == {}                         # 變回人形 → 卸獸形層
    assert c.attr("strength") == base_str


# --- 雙血脈識破 → 衛兵圍捕(patch run_battle / ui / rng)------------------
def _force_vampire_stage(c, st, gd, stg):
    c.is_vampire = True
    c.vampire_fed_day = _today(st) - vampirism.STAGE_DAYS * stg
    vampirism.apply_to_character(c, st, gd)


def _run_manhunt(st, gd, chance_hit):
    from tesrpg import main
    from tesrpg.ui import console as ui
    called = {"battle": 0}
    _rb, _msg, _chance = main.run_battle, ui.message, st.rng.chance
    main.run_battle = lambda *a, **k: called.__setitem__("battle", called["battle"] + 1)
    ui.message = lambda *a, **k: None
    st.rng.chance = lambda p: chance_hit
    try:
        res = main._curse_manhunt(st, gd)
    finally:
        main.run_battle, ui.message, st.rng.chance = _rb, _msg, _chance
    return called["battle"], res


def test_shunned_vampire_manhunt_in_town():
    gd, c, st = _state()
    _force_vampire_stage(c, st, gd, vampirism.SHUN_STAGE)       # stage 2 = shunned
    assert vampirism.is_shunned(c, st)
    c.location_id = "daggerfall"                                 # 高岩城(type city)
    inf0 = c.infamy
    battles, _ = _run_manhunt(st, gd, chance_hit=True)
    assert battles == 1 and c.infamy == inf0 + 1               # 召衛兵 + 惡名 +1


def test_fed_vampire_not_hunted():
    gd, c, st = _state()
    _force_vampire_stage(c, st, gd, 0)                          # 剛進食 → 非 shunned
    c.location_id = "daggerfall"
    assert not vampirism.is_shunned(c, st)
    battles, res = _run_manhunt(st, gd, chance_hit=True)        # 即使擲中也不觸發(階級不足)
    assert battles == 0 and res is None


def test_beast_in_town_manhunt():
    gd, c, st = _state()
    lycanthropy.contract(c, st, gd)
    powers.use(c, st, gd)                                       # 變身
    assert lycanthropy.is_beast(c, st)
    c.location_id = "daggerfall"
    battles, _ = _run_manhunt(st, gd, chance_hit=True)
    assert battles == 1


def test_manhunt_only_in_settlements():
    gd, c, st = _state()
    _force_vampire_stage(c, st, gd, vampirism.SHUN_STAGE)
    c.location_id = "imperial_reserve"                          # 非城/鎮(wilderness)→ 不觸發
    # 任挑一個非城鎮地點:若該 id 不存在則退而求其次找一個 wilderness
    loc = gd.world["locations"].get(c.location_id)
    if loc is None or loc.get("type") in ("city", "town"):
        c.location_id = next(lid for lid, l in gd.world["locations"].items()
                             if l.get("type") not in ("city", "town"))
    battles, res = _run_manhunt(st, gd, chance_hit=True)
    assert battles == 0 and res is None


# --- 月相連動 ----------------------------------------------------------
def test_full_moon_raises_vampire_detection():
    gd, c, st = _state()
    assert _advance_until(st, lambda: not moons.is_full_moon(st))
    _force_vampire_stage(c, st, gd, vampirism.SHUN_STAGE)
    p_norm = vampirism.detection_chance(c, st)
    assert _advance_until(st, lambda: moons.is_full_moon(st))
    _force_vampire_stage(c, st, gd, vampirism.SHUN_STAGE)       # 重釘 fed_day → 階級仍 2(隔離月相)
    p_full = vampirism.detection_chance(c, st)
    assert p_full == p_norm + vampirism.FULL_MOON_DETECT_BONUS > p_norm


def test_new_moon_eases_feeding():
    gd, c, st = _state(hour=22)                                 # 夜晚(非烈日時段)
    c.is_vampire = True
    captured = []

    def _cap(p):
        captured.append(p)
        return False                                           # 不被撞見,專注量機率

    st.rng.chance = _cap
    assert _advance_until(st, lambda: not moons.is_new_moon(st) and not vampirism._is_sun_hour(st.time.hour))
    vampirism.feed(st, gd)
    p_norm = captured[-1]
    assert _advance_until(st, lambda: moons.is_new_moon(st) and not vampirism._is_sun_hour(st.time.hour))
    vampirism.feed(st, gd)
    p_new = captured[-1]
    assert p_new == max(0.0, p_norm - vampirism.NEW_MOON_STEALTH_BONUS) < p_norm


# --- 零新存檔欄(月相純推導) ------------------------------------------
def test_moon_not_persisted_and_roundtrip():
    gd, c, st = _state()
    lycanthropy.contract(c, st, gd)
    d = c.to_dict()
    assert not any("moon" in k for k in d)                     # 月相不入檔
    c2 = type(c).from_dict(d)
    assert c2.is_werewolf == c.is_werewolf                     # cursed 角色 round-trip 一致


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
