"""AI 陣營自走戰爭(worldstate 階段五)回歸測試:
- war_tick_at 週期閘;非玩家城易主只寫 world_faction(不入稅基);反攻玩家城走削 garrison→tick_tax revolt;
- 持有期免疫 + reinforce 可守;決定性重播;雪球收斂;daedric 解鎖閘;選邊有感;存檔向後相容。
不破既有 test_worldstate / test_politics 契約(aiwar 只寫 world_faction/garrison_current/city_threat)。
"""
import collections
import json

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import aiwar, politics


def _state(seed=1, alleg=""):
    gd = get_gamedata()
    c = build_character(gd, name="戰", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    c.allegiance = alleg
    return gd, GameState(player=c, rng=RNG(seed), game_mode="adventure")


def _run(st, gd, weeks, tick_tax=False, reinforce=False):
    flips = peak = 0
    fell = None
    for wk in range(1, weeks + 1):
        st.time.advance(168)
        w = 0
        for ev in aiwar.update(st, gd):
            if ev["kind"] == "flip":
                flips += 1; w += 1
        peak = max(peak, w)
        if reinforce:
            for loc in list(st.player.city_faction):
                politics.reinforce_garrison(st.player, gd, loc, 999)
        if tick_tax:
            for ev in politics.tick_tax(st, gd):
                if ev["kind"] == "revolt" and fell is None:
                    fell = wk
    return flips, peak, fell


def _shares(st, gd):
    return collections.Counter(f for f in aiwar._controller_map(st.player, gd).values() if f)


def test_war_tick_gate():
    gd, st = _state()
    assert aiwar.update(st, gd) == []                 # 首圈起算,不結算
    st.time.advance(aiwar.WAR_HOURS - 1)
    assert aiwar.update(st, gd) == []                 # 未到週期
    st.time.advance(2)
    aiwar.update(st, gd)                               # 到週期 → 結算(不崩)


def test_ai_flip_writes_world_faction_not_city_faction():
    gd, st = _state(seed=2)
    _run(st, gd, 40)
    # 至少有城被 AI 易主到 world_faction,且 city_faction 全空(玩家未攻城)
    assert st.player.world_faction, "AI 應已造成城邦易幟"
    assert st.player.city_faction == {}
    assert politics.held_tax_cities(st.player, gd) == []   # 稅基不被污染


def test_at_most_one_flip_per_week():
    gd, st = _state(seed=4)
    _, peak, _ = _run(st, gd, 60)
    assert peak <= aiwar.MAX_FLIPS_PER_WEEK


def test_player_held_city_immune_while_held():
    gd, st = _state(seed=1, alleg="imperial")
    politics.conquer(st.player, gd, "whiterun", now=st.time.absolute_hours())
    _run(st, gd, 6, tick_tax=False)                    # 不跑 tick_tax → 不會 revolt
    # 持有期間:faction_of 恆回玩家大義、仍在稅基,即使被圍削守軍
    assert politics.faction_of(st.player, gd, "whiterun") == "imperial"
    assert "whiterun" in politics.held_tax_cities(st.player, gd)
    assert "whiterun" not in st.player.world_faction   # 絕不對玩家城寫 world_faction


def test_reattack_depletes_then_tick_tax_revolts():
    gd, st = _state(seed=1, alleg="imperial")
    politics.conquer(st.player, gd, "whiterun", now=st.time.absolute_hours())
    _, _, fell = _run(st, gd, 30, tick_tax=True)       # AI 圍攻 + tick_tax → 終究 revolt 失守
    assert fell is not None and fell >= 3, f"應數週後才失守(第 {fell} 週)"
    assert "whiterun" not in st.player.city_faction    # 已脫離掌握(浮回下層)


def test_reinforce_holds_against_raid():
    gd, st = _state(seed=1, alleg="imperial")
    politics.conquer(st.player, gd, "whiterun", now=st.time.absolute_hours())
    st.player.gold = 10 ** 9                           # 不缺錢回防
    _, _, fell = _run(st, gd, 30, tick_tax=True, reinforce=True)
    assert fell is None, "每週回防應守得住"


def test_deterministic_replay():
    gd, a = _state(seed=9); gd, b = _state(seed=9)
    _run(a, gd, 50); _run(b, gd, 50)
    assert a.player.world_faction == b.player.world_faction
    assert a.player.garrison_current == b.player.garrison_current


def test_no_snowball_convergence():
    gd, st = _state(seed=6)
    _run(st, gd, 150)
    sh = _shares(st, gd)
    tot = sum(sh.values())
    assert max(sh.values()) / tot < 0.70              # 無一統
    assert len([f for f in sh if sh[f] > 0]) >= 3     # 多陣營存活
    assert sh.get("neutral", 0) >= aiwar.NEUTRAL_FLOOR  # 中立緩衝存活


def test_picked_side_no_snowball():
    """玩家選邊會傾斜戰局,但不可雪球一統(審查抓到的真實情境):支持的陣營壯大但世界仍多極。"""
    gd, st = _state(seed=5, alleg="imperial")
    _run(st, gd, 120)
    sh = _shares(st, gd)
    tot = sum(sh.values())
    assert max(sh.values()) / tot < 0.78, f"選邊不可雪球一統({max(sh.values())/tot:.0%})"
    assert len([f for f in sh if sh[f] > 0]) >= 2, "選邊不可致他方全滅"
    assert sh.get("imperial", 0) > 0


def test_daedric_active_no_snowball():
    """daedric 參戰(kvatch_falls 後)同樣收斂:中立緩衝存活、不雪球。"""
    gd, st = _state(seed=2)
    st.player.world_events_fired.append("kvatch_falls")
    st.player.world_faction["kvatch"] = "daedric"
    _run(st, gd, 120)
    sh = _shares(st, gd)
    assert max(sh.values()) / sum(sh.values()) < 0.78
    assert sh.get("neutral", 0) >= aiwar.NEUTRAL_FLOOR


def test_daedric_resurges_not_permanently_wiped():
    """湮滅復現:kvatch_falls 後 daedric 大義打不死 —— 即使被打到 0 城也會再開湮滅之門(回應「大義太容易被消滅」)。
    跨多 seed 跑長線:終局 daedric 必 >0 城(修復前 7/12 局永久滅亡)。"""
    gd = get_gamedata()
    wiped = 0
    for seed in range(8):
        gd, st = _state(seed=seed)
        st.player.world_events_fired.append("kvatch_falls")
        st.player.world_faction["kvatch"] = "daedric"
        _run(st, gd, 120)
        if _shares(st, gd).get("daedric", 0) == 0:
            wiped += 1
    assert wiped == 0, f"daedric 大義不該被永久消滅(仍有 {wiped} 局終局 0 城)"


def test_daedric_locked_no_resurge_before_kvatch():
    """kvatch_falls 未觸發前,湮滅復現不啟動(daedric 不無端冒出)。"""
    gd, st = _state(seed=1)
    _run(st, gd, 60)
    assert _shares(st, gd).get("daedric", 0) == 0


def test_city_threat_pruned_after_loss():
    """城失守後 city_threat 殘留必被清除(防存檔膨脹;審查 minor)。"""
    gd, st = _state(seed=1, alleg="imperial")
    politics.conquer(st.player, gd, "whiterun", now=st.time.absolute_hours())
    _run(st, gd, 30, tick_tax=True)        # 終究失守
    assert "whiterun" not in st.player.city_faction
    assert "whiterun" not in st.player.city_threat, "失守城的 city_threat 殘留未清"


def test_daedric_locked_until_kvatch_falls():
    gd, st = _state()
    cmap = aiwar._controller_map(st.player, gd)
    assert "daedric" not in aiwar._aggressors(st.player, cmap)
    st.player.world_events_fired.append("kvatch_falls")
    st.player.world_faction["kvatch"] = "daedric"      # 給 daedric 一座城
    cmap = aiwar._controller_map(st.player, gd)
    assert "daedric" in aiwar._aggressors(st.player, cmap)


def test_allegiance_sways_war():
    gd, a = _state(seed=5, alleg="imperial")
    gd, b = _state(seed=5, alleg="independent")
    _run(a, gd, 100); _run(b, gd, 100)
    imp_when_support = _shares(a, gd).get("imperial", 0)
    imp_when_oppose = _shares(b, gd).get("imperial", 0)
    assert imp_when_support > imp_when_oppose, "支持帝國應讓帝國擴張更多(選邊有感)"


def test_save_roundtrip_and_backward_compat():
    gd, st = _state()
    st.player.war_tick_at = 5000
    st.player.city_threat = {"whiterun": "independent"}
    loaded = Character.from_dict(json.loads(json.dumps(st.player.to_dict())))
    assert loaded.war_tick_at == 5000 and loaded.city_threat == {"whiterun": "independent"}
    d = st.player.to_dict()
    del d["war_tick_at"]; del d["city_threat"]          # 舊存檔
    old = Character.from_dict(d)
    assert old.war_tick_at == 0 and old.city_threat == {}


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_aiwar OK")
