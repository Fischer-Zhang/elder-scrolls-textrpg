"""R109 Phase A 引擎:暗殺 objective / 任務條件式狩獵生成 / 謀殺目擊制。

涵蓋:assassinate 目標判定 + 文字;active_hunt_target(省份配對/僅 weight-0 劇情敵/決定性/
無任務→None 保 byte-identical);murder_witness_chance(城>鎮>野·潛行/夜遞減·夾限);
record_murder witnessed vs 潛殺乾淨(賞金/惡名僅目擊時加·血債恆計)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import brotherhood, crime, quests


def _st(seed=1):
    gd = get_gamedata()
    c = build_character(gd, name="H", sex="male", race="imperial", birthsign="thief",
                        class_id="assassin")
    c.is_player = True
    c.level = 10
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=12))
    return gd, c, st


def _wild_in(gd, province):
    return [l for l, v in gd.world["locations"].items()
            if v.get("province") == province and v.get("type") == "wilderness"][0]


def _first(gd, loc_type):
    return [l for l, v in gd.world["locations"].items() if v.get("type") == loc_type][0]


# --- assassinate objective --------------------------------------------------
def test_assassinate_objective_met_by_murdered_npcs():
    gd, c, st = _st()
    obj = {"type": "assassinate", "npc": "olfina"}
    assert not quests._objective_met(c, gd, obj, 0)
    c.murdered_npcs.append("olfina")
    assert quests._objective_met(c, gd, obj, 0)


# --- active_hunt_target -----------------------------------------------------
def test_hunt_target_matches_province_only():
    gd, c, st = _st()
    quests.accept_quest(c, gd, "cint_skyrim_spies")   # provinces=天際·kill rogue_thief(weight0)
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "天際")) == "rogue_thief"
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "賽羅迪爾")) is None   # 不符省 → 不獵


def test_hunt_target_none_without_quest_is_byte_safe():
    gd, c, st = _st()
    # 無任何 kill 任務 → 恆 None(world.travel 據此走原路徑·byte-identical 前提)
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "天際")) is None


def test_hunt_target_ignores_normal_pool_creatures():
    gd, c, st = _st()
    # comm_ 委託目標是野遇池怪(weight>0)→ 不走狩獵鉤子(池裡本就抽得到)
    quests.accept_quest(c, gd, "comm_skyrim_wolf")   # kill wolf(weight>0)
    assert quests.active_hunt_target(c, gd, _wild_in(gd, "天際")) is None


def test_hunt_hook_can_spawn_target_on_travel():
    from tesrpg.systems import world
    gd, c, st = _st()
    quests.accept_quest(c, gd, "cint_skyrim_spies")
    # 找一條「終點在天際、危險度>0」的旅行邊,多 seed 跑 travel,應能撞見 rogue_thief
    src = None
    for lid, v in gd.world["locations"].items():
        if v.get("province") == "天際":
            for dst in v.get("links", {}):
                d = gd.world["locations"][dst]
                if d.get("province") == "天際" and d.get("type") == "wilderness" and d.get("danger", 0) > 0:
                    src, dest = lid, dst
                    break
        if src:
            break
    assert src, "找不到天際野外旅行邊"
    seen = False
    for seed in range(40):
        c.location_id = src
        c.fatigue = c.max_fatigue
        r = world.travel(c, gd, dest, GameTime(hour=12), RNG(seed))
        foe = r["foe"]
        if foe is not None and getattr(foe, "template_id", None) == "rogue_thief":
            seen = True
            break
    assert seen, "狩獵鉤子未能在天際野外生成 rogue_thief"


# --- 謀殺目擊制 -------------------------------------------------------------
def test_witness_chance_by_guard_density_and_stealth():
    gd, c, st = _st()
    c.skills["sneak"] = 0
    c.location_id = _first(gd, "city")
    city_day = crime.murder_witness_chance(c, gd, night=False)
    c.location_id = _first(gd, "town")
    town_day = crime.murder_witness_chance(c, gd, night=False)
    wild = _wild_in(gd, "賽羅迪爾")
    c.location_id = wild
    wild_day = crime.murder_witness_chance(c, gd, night=False)
    assert city_day > town_day > wild_day             # 城守密度:大城>小鎮>野外
    # 潛行 + 夜色顯著降低目擊率
    c.location_id = _first(gd, "city")
    c.skills["sneak"] = 100
    assert crime.murder_witness_chance(c, gd, night=True) < city_day
    # 夾限
    assert crime.MURDER_WITNESS_FLOOR <= crime.murder_witness_chance(c, gd, night=True) <= crime.MURDER_WITNESS_CEIL


def test_record_murder_witnessed_vs_clean():
    gd, c, st = _st()
    c.location_id = _first(gd, "city")
    prov = crime.province_of(c, gd)
    # 目擊 → 賞金+惡名(既有行為·預設 witnessed=True)
    r = brotherhood.record_murder(st, gd, "olfina", witnessed=True)
    assert r["bounty"] == brotherhood.MURDER_BOUNTY and crime.bounty(c, prov) == brotherhood.MURDER_BOUNTY
    assert c.infamy == brotherhood.MURDER_INFAMY and "olfina" in c.murdered_npcs and c.murders == 1
    # 潛殺乾淨 → 血債照計、NPC 照除,但零賞金/零惡名
    inf0, b0 = c.infamy, crime.bounty(c, prov)
    r2 = brotherhood.record_murder(st, gd, "brand", witnessed=False)
    assert r2["bounty"] == 0 and crime.bounty(c, prov) == b0 and c.infamy == inf0
    assert "brand" in c.murdered_npcs and c.murders == 2


def run():
    for name in sorted(globals()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  ✓ {name}")
