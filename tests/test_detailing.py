"""細化省分的測試:生態遭遇表(biome 加權)、告示板按省過濾、在地 NPC/任務、
省份風味事件、天際補密度、各 JSON 引用完整性。"""

from collections import Counter

from tesrpg import formulas
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
    """各 biome 統計上偏抽在地生態怪、且後備池不空(通用怪四海皆有)。
    參數化合一(原 snow/swamp/moor/jungle/savanna/heartland 六條同形 steering 測):
    每 case 600 抽,斷在地>他鄉(heartland 例外:賽羅迪爾為通用走廊,只斷在地>0),
    斷 sum==600(後備池不被清空)。"""
    gd, _ = _char()
    SNOW = {"skeleton", "draugr", "ice_wraith", "frost_troll", "frost_giant", "frostbite_spider"}
    SWAMP = {"swamp_lizard", "marsh_zombie", "will_o_wisp", "bog_troll", "wamasu"}

    def biome_set(b):
        return {cid for cid, c in gd.bestiary.items() if b in c.get("biomes", [])}

    moor, desert = biome_set("moor"), biome_set("desert")
    jungle, swamp_b = biome_set("jungle"), biome_set("swamp")
    savanna = biome_set("savanna")
    heartland = biome_set("heartland")

    def sample(biome, seed_base, n=600, lvl=20, danger=5):
        tally = Counter()
        for i in range(n):
            c = combat.random_encounter(gd, lvl, RNG(seed_base + i), max_danger=danger, biome=biome)
            tally[c.template_id] += 1
        return tally

    # (biome, 在地集, 他鄉集, seed_base):各 600 抽、在地>他鄉、池不空
    cases = [
        ("snow", SNOW, SWAMP, 1000),
        ("swamp", SWAMP, SNOW, 1000),
        ("moor", moor, desert, 7000),
        ("jungle", jungle, swamp_b, 9000),
        ("savanna", savanna, jungle, 11000),
    ]
    for biome, local, foreign, seed_base in cases:
        t = sample(biome, seed_base)
        local_n = sum(t[k] for k in local)
        foreign_n = sum(t[k] for k in foreign)
        assert local_n > foreign_n, (biome, local_n, foreign_n)   # 在地生態 > 他鄉生態
        assert sum(t.values()) == 600, (biome, sum(t.values()))   # 後備池不被清空

    # heartland 特判:賽羅迪爾為通用走廊(lvl5/danger3,斷言較弱:只 local>0,不強加 local>foreign)
    assert heartland, "heartland 仍無專屬生態怪"
    ht = sample("heartland", 4000, lvl=5, danger=3)
    assert sum(ht[k] for k in heartland) > 0, "heartland 招牌怪抽不到"
    assert sum(ht.values()) == 600, sum(ht.values())


def test_every_location_has_biome():
    gd, _ = _char()
    valid = {"heartland", "snow", "ashland", "swamp", "desert", "moor", "jungle", "savanna"}
    for lid, loc in gd.world["locations"].items():
        assert loc.get("biome") in valid, f"{lid} biome 非法:{loc.get('biome')}"
    # absorb test_creature_biomes_are_valid:bestiary 每隻怪的 biomes 全合法(共用同一 valid 集合)
    for cid, c in gd.bestiary.items():
        for b in c.get("biomes", []):
            assert b in valid, f"{cid} biomes 非法:{b}"


# --- 各省生態弱性軸:招牌怪須『真的』弱於該省剋星元素 --------------------
def test_highrock_signature_creatures_weak_to_shock():
    """各省生態弱性軸(參數化合一:原 highrock/valenwood/elsweyr 三條同形弱性測):
    取該 biome 招牌怪,斷 len≥5、逐隻斷 formulas.resist_multiplier(resist, element) > 1.0
    (招牌怪『真的』弱於該省剋星元素)。各 case 的疊鍵陷阱要點以註解保留:"""
    gd, _ = _char()
    # (biome, element):
    #  moor/shock  ── 高岩=練電系。shock ∈ MAGIC_ELEMENTS,計電抗會疊 magic 鍵(r=shock+magic),
    #                 故 shock 負值須夠負以蓋過 magic 正值,招牌怪才真弱電。
    #  jungle/fire ── 瓦倫森林=以烈焰焚林。fire ∈ MAGIC_ELEMENTS 會疊 magic 鍵,故招牌怪刻意不帶 magic 鍵。
    #  savanna/poison ── 艾爾斯維爾=練塗毒/煉金刺客。poison ∉ MAGIC_ELEMENTS,不疊 magic 鍵,負值即直接放大傷害。
    #  🔴 R139 現實邏輯豁免:不死系(undead:true)無血肉代謝 → 不吃生態弱性軸(dro_mathra_shade
    #     曾被此測試鎖成「弱毒 -45 且以毒攻擊的幽魂」= 鐵律零號總則違例;豁免後改 poison:100)。
    for biome, element in [("moor", "shock"), ("jungle", "fire"), ("savanna", "poison")]:
        cids = [cid for cid, c in gd.bestiary.items()
                if biome in c.get("biomes", []) and not c.get("undead")]
        assert len(cids) >= 5, f"{biome} 招牌怪太少:{cids}"
        for cid in cids:
            m = formulas.resist_multiplier(gd.bestiary[cid].get("resist", {}), element)
            assert m > 1.0, f"{cid} 並非真的弱 {element}(係數 {m} ≤ 1.0)"


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
        # absorb test_npc_rumors_are_strings:NPC rumor 欄是非空字串
        if "rumor" in npc:
            assert isinstance(npc["rumor"], str) and npc["rumor"], f"{nid} rumor 非法"
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


# 小工具:events.eligible_events 需要一個有 .player/.time 的 state-like
class _S:
    def __init__(self, player, time):
        self.player = player
        self.time = time


def gd_state(gd, c):
    from tesrpg.state import GameTime
    return _S(c, GameTime())


def test_every_city_meets_npc_standard():
    """每座非邊境城/鎮達居民標準(城≥3 / 鎮≥2)—— 杜絕『有店無人』空城(回報修補後守門)。"""
    from collections import Counter
    gd, _ = _char()
    na = Counter(n["location"] for n in gd.npcs.values() if n.get("location"))
    thin = []
    for lid, l in gd.world["locations"].items():
        if l.get("type") not in ("city", "town") or l.get("province") == "邊境":
            continue
        want = 2 if l["type"] == "town" else 3
        if na[lid] < want:
            thin.append(f'{l["name"]}({na[lid]}/{want})')
    assert not thin, f"NPC 不足的城:{thin}"


def test_morrowind_ecology_and_npc_quest_targets():
    """晨風生態怪池 ≥4(委託可輪替不再全打灰蹦蟲);所有 npc-source 任務目標合法。"""
    from tesrpg.systems import court
    gd, _ = _char()
    assert len(court._province_objectives(gd)["晨風"][0]) >= 4
    reg = set(gd.items) | set(gd.weapons) | set(gd.armor)
    for qid, q in gd.quests.items():
        if q.get("source") != "npc" or "objective" not in q:
            continue
        o = q["objective"]
        if o["type"] == "kill":
            assert o["creature"] in gd.bestiary, f"{qid} 目標怪 {o.get('creature')} 不存在"
        elif o["type"] == "clear_dungeon":
            assert o["dungeon"] in gd.dungeons, f"{qid} 目標地城 {o.get('dungeon')} 不存在"
        elif o["type"] == "collect":
            assert o["item"] in reg, f"{qid} 目標物品 {o.get('item')} 不存在"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_detailing OK")
