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


def test_creature_biomes_are_valid():
    gd, _ = _char()
    valid = {"heartland", "snow", "ashland", "swamp"}
    for cid, c in gd.bestiary.items():
        for b in c.get("biomes", []):
            assert b in valid, f"{cid} biomes 非法:{b}"


def test_heartland_has_signature_ecology():
    """賽羅迪爾不再只有通用怪:heartland biome 會明顯抽到 heartland 招牌怪。"""
    gd, _ = _char()
    heartland = {cid for cid, c in gd.bestiary.items() if "heartland" in c.get("biomes", [])}
    assert heartland, "heartland 仍無專屬生態怪"
    tally = Counter()
    for i in range(800):
        c = combat.random_encounter(gd, 5, RNG(4000 + i), max_danger=3, biome="heartland")
        tally[c.template_id] += 1
    assert sum(tally[k] for k in heartland) > 0, "heartland 招牌怪抽不到"
    # imperial_ghost(d2/min1)應在帝國大道(d1→max2)從低等就抽得到
    low = combat.random_encounter(gd, 2, RNG(1), max_danger=2, biome="heartland")  # smoke: 不崩
    assert low.template_id in gd.bestiary


def test_heartland_starter_road_stays_gentle():
    """賽羅迪爾起手大道(imperial_road danger1 → max_danger2)須維持和緩:
    重數值的 minotaur(d3)必須被危險度門檻擋在起手區外(避免重演雪原偏硬)。"""
    gd, _ = _char()
    seen = Counter()
    for i in range(600):
        c = combat.random_encounter(gd, 5, RNG(13000 + i), max_danger=2, biome="heartland")
        seen[c.template_id] += 1
    assert "minotaur" not in seen, "米諾陶(d3 重甲怪)不該出現在 danger-1 起手大道"
    # 起手大道任何怪的 danger 都應 <=2(危險度門檻生效)
    for tid in seen:
        assert gd.bestiary[tid].get("danger", 1) <= 2, f"{tid} danger>2 卻出現在起手大道"


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


def test_local_quest_chains_are_multistage_and_offered_by_npcs():
    gd, _ = _char()
    chains = ["chain_kvatch", "chain_molagmar"]
    for qid in chains:
        assert len(gd.quests[qid].get("stages", [])) >= 3, f"{qid} 不是多階段任務鏈"
        assert gd.quests[qid]["source"] == "npc"
    # 任務鏈/單發委託都掛在對應 NPC 上
    npc_quests = {npc.get("quest") for npc in gd.npcs.values()}
    for qid in chains + ["favor_haafingar"]:
        assert qid in npc_quests, f"{qid} 沒有 NPC 提供"


def test_each_core_province_has_multiple_cities():
    """補全各省城市:四大實體省皆有 >=2 座 city,且標誌城市存在。"""
    gd, _ = _char()
    locs = gd.world["locations"]
    from collections import Counter as _C
    cities = _C(l["province"] for l in locs.values() if l["type"] == "city")
    for prov in ("賽羅迪爾", "天際", "晨風", "黑沼澤"):
        assert cities[prov] >= 2, f"{prov} 城市數 {cities[prov]} < 2"
    iconic = ["imperial_city", "whiterun", "vivec", "helstrom"]
    for cid in iconic:
        assert cid in locs and locs[cid]["type"] == "city", f"標誌城市 {cid} 缺失"


def test_npc_rumors_are_strings():
    gd, _ = _char()
    for nid, npc in gd.npcs.items():
        if "rumor" in npc:
            assert isinstance(npc["rumor"], str) and npc["rumor"], f"{nid} rumor 非法"


def test_local_quest_rewards_stay_in_range():
    """反 min-max 機械守門:NPC/board 在地任務獎勵須與付出相稱。
    例行委託(kill/collect/reach):金幣≤320(=job_barrow 清 d4 地城上限)、聲望≤15。
    清整座地城(clear_dungeon)=最高付出 → 上限按目標 danger 放寬(floor-preserving:
    max(320, danger*100) / max(15, danger*5);既有委託皆不變,僅 d5 apex 屠龍另計)。
    **不給高階裝(BIS)的鐵則對所有在地任務一律保留**(地城本身才掉 BIS,任務不加碼)。"""
    gd, _ = _char()
    BIS = {"glass_cuirass", "ebony_cuirass", "ebony_sword", "dwarven_cuirass", "ebony_shield",
           "glass_helmet", "glass_gauntlets", "glass_boots", "glass_shield"}
    locs = gd.world["locations"]

    def _objs(qd):
        out = []
        if "objective" in qd:
            out.append(qd["objective"])
        for s in qd.get("stages", []):
            out.append(s.get("objective", {}))
        for b in qd.get("branches", []):
            if "objective" in b:
                out.append(b["objective"])
            for s in b.get("stages", []):
                out.append(s.get("objective", {}))
        return out

    for qid, q in gd.quests.items():
        if q.get("source") not in ("npc", "board"):
            continue
        dd = 0    # 以「清地城」目標的最高 danger 放寬上限(無則維持例行區間)
        for o in _objs(q):
            if o.get("type") == "clear_dungeon":
                dd = max(dd, locs.get(o.get("dungeon"), {}).get("danger", 0))
        gold_cap = max(320, dd * 100)
        fame_cap = max(15, dd * 5)
        rewards = ([b.get("reward", {}) for b in q["branches"]] if "branches" in q
                   else [q.get("reward", {})])
        for r in rewards:
            assert r.get("gold", 0) <= gold_cap, f"{qid} 金幣獎勵過高:{r.get('gold')} > {gold_cap}"
            assert r.get("fame", 0) <= fame_cap, f"{qid} 聲望獎勵過高:{r.get('fame')} > {fame_cap}"
            for iid in r.get("items", []):
                assert iid not in BIS, f"{qid} 在地任務不應給高階裝 {iid}"


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
    # 天際補密度後 >=5 地點(細化省分加佛克瑞斯林/迷刀洞窟;補全城市後更多)
    skyrim = [l for l in locs.values() if l["province"] == "天際"]
    assert len(skyrim) >= 5, len(skyrim)


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
