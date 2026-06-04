"""細化省分的測試:生態遭遇表(biome 加權)、告示板按省過濾、在地 NPC/任務、
省份風味事件、天際補密度、各 JSON 引用完整性。"""

from collections import Counter

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, events, quests


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="A", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, c


# --- Tier2-a 生態遭遇表 ------------------------------------------------
def test_biome_weight_logic():
    gd, _ = _char()
    snow = {"weight": 4, "biomes": ["snow"]}
    universal = {"weight": 4}
    assert combat._biome_weight(snow, "snow") > combat._biome_weight(snow, "swamp")
    # 通用怪(無 biomes)不受地點 biome 影響
    assert combat._biome_weight(universal, "snow") == combat._biome_weight(universal, "swamp") == 4
    # 無當地 biome → 不調整
    assert combat._biome_weight(snow, None) == 4


def test_biome_steers_encounters_without_emptying_pool():
    """高等級下,雪原偏雪怪、沼澤偏沼怪;但兩者池都不空、通用怪四海皆有。"""
    gd, _ = _char()
    SNOW = {"skeleton", "draugr", "ice_wraith", "frost_troll", "frost_giant", "frostbite_spider"}
    SWAMP = {"swamp_lizard", "marsh_zombie", "will_o_wisp", "bog_troll", "wamasu"}

    def sample(biome, n=600):
        tally = Counter()
        for i in range(n):
            c = combat.random_encounter(gd, 20, RNG(1000 + i), max_danger=5, biome=biome)
            tally[c.template_id] += 1
        return tally

    snow_t, swamp_t = sample("snow"), sample("swamp")
    snow_snow = sum(snow_t[k] for k in SNOW)
    snow_swamp = sum(snow_t[k] for k in SWAMP)
    swamp_swamp = sum(swamp_t[k] for k in SWAMP)
    swamp_snow = sum(swamp_t[k] for k in SNOW)
    # 在地生態明顯多於他鄉生態
    assert snow_snow > snow_swamp, (snow_snow, snow_swamp)
    assert swamp_swamp > swamp_snow, (swamp_swamp, swamp_snow)
    # 池不空:雪原仍抽得到一些他鄉/通用怪(後備池不被清空)
    assert sum(snow_t.values()) == 600 and sum(swamp_t.values()) == 600


def test_every_location_has_biome():
    gd, _ = _char()
    valid = {"heartland", "snow", "ashland", "swamp"}
    for lid, loc in gd.world["locations"].items():
        assert loc.get("biome") in valid, f"{lid} biome 非法:{loc.get('biome')}"


# --- Tier2-b 告示板按省過濾 -------------------------------------------
def test_board_province_filter():
    gd, c = _char()
    # job_xanmeer 只在黑沼澤板;job_falkreath 只在天際板;job_wolf 全圖通用
    bm = quests.available_quests(c, gd, "board", province="黑沼澤")
    sky = quests.available_quests(c, gd, "board", province="天際")
    assert "job_xanmeer" in bm and "job_xanmeer" not in sky
    assert "job_falkreath" in sky and "job_falkreath" not in bm
    assert "job_wolf" in bm and "job_wolf" in sky          # 無 provinces → 通用
    # 不傳 province(向後相容)→ 不過濾,全部 board 委託都在
    no_filter = quests.available_quests(c, gd, "board")
    assert "job_xanmeer" in no_filter and "job_falkreath" in no_filter


# --- Tier1-b NPC / 在地任務 -------------------------------------------
def test_npcs_have_valid_locations_and_quests():
    gd, _ = _char()
    for nid, npc in gd.npcs.items():
        assert npc["location"] in gd.world["locations"], f"{nid} 地點非法"
        if npc.get("quest"):
            assert npc["quest"] in gd.quests, f"{nid} 委託 {npc['quest']} 不存在"
    # 原本零 NPC 的省份現在有人
    provinces_with_npc = {gd.world["locations"][npc["location"]]["province"] for npc in gd.npcs.values()}
    assert {"晨風", "黑沼澤"} <= provinces_with_npc


def test_quest_objective_targets_valid():
    """所有任務 objective 引用的 creature/dungeon/location/item 都存在。"""
    gd, _ = _char()

    def check_obj(qid, obj):
        t = obj["type"]
        if t == "kill":
            assert obj["creature"] in gd.bestiary, f"{qid}: 怪 {obj['creature']} 不存在"
        elif t == "clear_dungeon":
            assert obj["dungeon"] in gd.dungeons, f"{qid}: 地城 {obj['dungeon']} 不存在"
        elif t == "reach":
            assert obj["location"] in gd.world["locations"], f"{qid}: 地點 {obj['location']} 不存在"
        elif t == "collect":
            assert gd.item(obj["item"]), f"{qid}: 物品 {obj['item']} 不存在"

    for qid, q in gd.quests.items():
        branches = q.get("branches")
        if branches:
            for b in branches:
                for st in (b.get("stages") or ([{"objective": b["objective"]}] if "objective" in b else [])):
                    check_obj(qid, st["objective"])
        else:
            for st in (q.get("stages") or [{"objective": q["objective"]}]):
                check_obj(qid, st["objective"])


def test_local_quests_point_at_detailed_content():
    gd, _ = _char()
    assert gd.quests["job_xanmeer"]["objective"]["dungeon"] == "xanmeer"
    assert gd.quests["favor_lostknife"]["objective"]["dungeon"] == "lostknife_cave"
    assert gd.quests["favor_gideon"]["objective"]["location"] == "xanmeer"


# --- Tier1-c 省份風味事件 ---------------------------------------------
def test_province_events_filter_by_province():
    gd, c = _char()
    valid_provs = {loc["province"] for loc in gd.world["locations"].values()}
    prov_events = {eid: e for eid, e in gd.events.items() if "provinces" in e.get("trigger", {})}
    assert len(prov_events) >= 6, "省份風味事件太少"
    for eid, e in prov_events.items():
        for p in e["trigger"]["provinces"]:
            assert p in valid_provs, f"{eid} 引用不存在的行省 {p}"
        # 事件 combat 效果引用的怪都存在
        for opt in e["options"]:
            for ef in opt.get("effects", []):
                if ef.get("type") == "combat":
                    assert ef["creature"] in gd.bestiary, f"{eid} 事件怪 {ef['creature']} 不存在"

    # 黑沼澤事件在黑沼澤地點 eligible、在賽羅迪爾不 eligible
    c.location_id = "murkmire"   # 黑沼澤 wilderness
    elig = events.eligible_events(gd_state(gd, c), gd, "explore")
    assert "blackmarsh_predator" in elig
    c.location_id = "imperial_road"   # 賽羅迪爾
    elig2 = events.eligible_events(gd_state(gd, c), gd, "explore")
    assert "blackmarsh_predator" not in elig2


def test_tianji_density_falkreath_and_lostknife():
    gd, _ = _char()
    locs = gd.world["locations"]
    assert locs["falkreath_wood"]["province"] == "天際" and locs["falkreath_wood"]["type"] == "wilderness"
    assert locs["lostknife_cave"]["dungeon"] == "lostknife_cave" and "lostknife_cave" in gd.dungeons
    # 天際現在 5 地點
    skyrim = [l for l in locs.values() if l["province"] == "天際"]
    assert len(skyrim) == 5, len(skyrim)


# 小工具:events.eligible_events 需要一個有 .player/.time 的 state-like
class _S:
    def __init__(self, player, time):
        self.player = player
        self.time = time


def gd_state(gd, c):
    from tesrpg.state import GameTime
    return _S(c, GameTime())


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_detailing OK")
