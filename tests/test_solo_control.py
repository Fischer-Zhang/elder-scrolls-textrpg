"""R44 控場集中化 + solo BOSS 機率減免:`magic.apply_control` 單一決策點。

涵蓋:
  - solo BOSS 對硬控(fear/paralyze)由「完全免疫」改機率減免(≈1-SOLO_CONTROL_RESIST_CHANCE)。
  - 非 solo 敵 100% 生效;玩家為 target 走 willpower(resisted_mind)。
  - 硬控去重 / 同源去重;軟控(stagger/slow/weaken)對 solo 一律生效(收斂鈍器 stagger 不一致)。
  - 戀人座『戀人之觸』破口閉合(powers.use 路由 helper)。
"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, powers


def _gd():
    return get_gamedata()


def _solo_boss(gd):
    tid = next(t for t, d in gd.bestiary.items() if d.get("solo"))
    return combat.spawn_creature(gd, tid, RNG(1))


def _player(willpower=40):
    gd = _gd()
    c = build_character(gd, name="P", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.attributes["willpower"] = willpower
    return c


def test_hard_control_solo_probabilistic_rate():
    """solo BOSS 對 fear/paralyze:生效率 ≈ 1 - SOLO_CONTROL_RESIST_CHANCE(機率減免,既非 0 亦非 1)。"""
    gd = _gd()
    boss = _solo_boss(gd)
    expect = 1 - formulas.SOLO_CONTROL_RESIST_CHANCE
    for kind in ("fear", "paralyze"):
        applied, n = 0, 2000
        for s in range(n):
            boss.active_effects = []
            if magic.apply_control(boss, kind, gd, RNG(s), turns=2) == "applied":
                applied += 1
        rate = applied / n
        assert abs(rate - expect) < 0.06, (kind, rate, expect)


def test_nonsolo_enemy_full_control():
    """非 solo 敵人:fear/paralyze 100% 生效(無抵抗)。"""
    gd = _gd()
    for kind in ("fear", "paralyze"):
        for s in range(50):
            wolf = combat.spawn_creature(gd, "wolf", RNG(s))
            assert magic.apply_control(wolf, kind, gd, RNG(s), turns=2) == "applied"


def test_player_hard_control_via_willpower():
    """玩家為 target:fear/paralyze 走 willpower(resisted_mind)——意志 40 必中、高意志多抗(不碰 solo 機率)。"""
    gd = _gd()

    def applied_rate(wp, n=400):
        a = 0
        for s in range(n):
            p = _player(willpower=wp)
            if magic.apply_control(p, "fear", gd, RNG(s), turns=2) == "applied":
                a += 1
        return a / n

    assert applied_rate(40) == 1.0          # 中性意志:必中(resisted_mind=0)
    assert applied_rate(255) < 0.5          # 高意志:顯著抗下


def test_hard_control_dedup():
    """硬控去重:已 fear 中再施 fear → 'blocked',不疊不延長。"""
    gd = _gd()
    wolf = combat.spawn_creature(gd, "wolf", RNG(1))
    assert magic.apply_control(wolf, "fear", gd, RNG(1), turns=3) == "applied"
    assert magic.apply_control(wolf, "fear", gd, RNG(2), turns=3) == "blocked"
    assert sum(1 for e in wolf.active_effects if e["kind"] == "fear") == 1


def test_soft_control_solo_always_applies():
    """軟控(stagger/slow/weaken)對 solo BOSS 一律生效(無免疫;收斂鈍器內建 stagger 的不一致)。"""
    gd = _gd()
    for kind, mag in (("stagger", 0.0), ("slow", 0.3), ("weaken", 0.25)):
        boss = _solo_boss(gd)
        boss.active_effects = []
        # 多次擲皆 applied(軟控不受 SOLO_CONTROL_RESIST_CHANCE)
        for s in range(20):
            boss.active_effects = []
            assert magic.apply_control(boss, kind, gd, RNG(s), magnitude=mag, turns=2) == "applied"


def test_source_dedup_soft_control():
    """同源去重:帶 source 的軟控(元素 rider)不疊兩份(雙持不重複)。"""
    gd = _gd()
    wolf = combat.spawn_creature(gd, "wolf", RNG(1))
    assert magic.apply_control(wolf, "weaken", gd, RNG(1), magnitude=0.15, turns=2, source="ench_chill") == "applied"
    assert magic.apply_control(wolf, "weaken", gd, RNG(2), magnitude=0.15, turns=2, source="ench_chill") == "blocked"
    assert sum(1 for e in wolf.active_effects if e["kind"] == "weaken") == 1


def test_lover_paralyze_touch_solo_reduced():
    """戀人座『戀人之觸』破口閉合:對 solo BOSS 由「保證 3 回合鎖」改機率減免;非 solo 仍必中。"""
    gd = _gd()
    c = build_character(gd, name="L", sex="female", race="imperial", birthsign="lover", class_id="warrior")
    assert powers.power_id(c, gd) == "paralyze_touch"
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    # 非 solo:必中
    wolf = combat.spawn_creature(gd, "wolf", RNG(1))
    powers.use(c, st, gd, target=wolf)
    assert magic.is_paralyzed(wolf)
    # solo BOSS:機率減免(會中也會抗)→ 不再保證鎖
    locked = 0
    for s in range(200):
        boss = _solo_boss(gd)
        st.rng = RNG(s * 3 + 1)
        powers.use(c, st, gd, target=boss)
        if magic.is_paralyzed(boss):
            locked += 1
    assert 0 < locked < 200, locked


def run():
    test_hard_control_solo_probabilistic_rate()
    test_nonsolo_enemy_full_control()
    test_player_hard_control_via_willpower()
    test_hard_control_dedup()
    test_soft_control_solo_always_applies()
    test_source_dedup_soft_control()
    test_lover_paralyze_touch_solo_reduced()


if __name__ == "__main__":
    run()
    print("test_solo_control OK")
