"""R176 夏暮群島(第九省)專屬回歸:版圖 / 海路連接 / 守護學派 / 生態 / 內容完整性。

文獻依據(UESP·Fandom·Legendarium 摘要):群島在大陸西南、瓦倫森林以西,最近的鄰國僅瓦倫森林,
無任何來源把它連到漢默法爾 → 兩條海路邊境只接瓦倫森林,且是兩個不同入口(成環,不接成走廊尾巴)。"""

import json
import re
from collections import Counter

from tesrpg import formulas
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import combat, world

PROV = "夏暮群島"
BASELINE = {"flames", "frostbite", "sparks", "minor_heal", "oakflesh",
            "ward", "soul_trap", "conjure_familiar", "fear"}


def _gd():
    gd = get_gamedata()
    return gd, gd.world["locations"]


def _nodes(L, prov=PROV):
    return {lid: l for lid, l in L.items() if l["province"] == prov}


def _reach(L, start, banned=()):
    seen, stack = {start}, [start]
    while stack:
        n = stack.pop()
        for m in L[n]["links"]:
            if m not in seen and m not in banned:
                seen.add(m)
                stack.append(m)
    return seen


def test_summerset_is_the_ninth_province_with_20_nodes():
    gd, L = _gd()
    provinces = {l["province"] for l in L.values()} - {"邊境"}
    assert PROV in provinces and len(provinces) == 9
    nodes = _nodes(L)
    assert len(nodes) == 20
    assert Counter(l["type"] for l in nodes.values()) == {"city": 4, "town": 3, "wilderness": 8, "dungeon": 5}
    # 全省統一 isle(使用者拍板 B;與其餘八省「一省一生態」先例一致,領主懸賞素材池只含在地怪)
    assert {l["biome"] for l in nodes.values()} == {"isle"}
    # 網格已為群島騰出西側:所有座標界內且不同格(通用測試亦守,此處鎖「確實擴格」)
    assert gd.world["map"]["cols"] == 50 and gd.world["map"]["rows"] == 24


def test_summerset_sea_lanes_reach_only_valenwood_and_close_a_loop():
    gd, L = _gd()
    lanes = sorted(lid for lid, l in L.items() if l["province"] == "邊境"
                   and any(L[n]["province"] == PROV for n in l["links"]))
    assert lanes == ["auridon_strait", "southern_sea_lane"]
    mainland_ports = set()
    for lid in lanes:
        outside = {L[n]["province"] for n in L[lid]["links"]} - {"邊境", PROV}
        assert outside == {"瓦倫森林"}, (lid, outside)               # 文獻:最近鄰國僅瓦倫森林;不連漢默法爾
        mainland_ports |= {n for n in L[lid]["links"] if L[n]["province"] == "瓦倫森林"}
    assert len(mainland_ports) == 2                                  # 兩個不同的瓦倫森林入口
    # 任一條航道被切斷,群島仍連得到大陸 → 環,而非走廊尾巴
    for cut in lanes:
        seen = _reach(L, "alinor", banned={cut})
        assert any(L[n]["province"] == "瓦倫森林" for n in seen), cut
    # 兩條航道皆為海側 biome、危險度 3(比照灰海航道 sea_route)
    for lid in lanes:
        assert L[lid]["biome"] == "isle" and L[lid]["danger"] == 3 and L[lid]["type"] == "wilderness"


def test_summerset_links_are_symmetric_with_equal_weights():
    """審查補洞(變異 m11 存活):既有 test_world 只驗『反向連線存在』,不驗權重相等;
    此處對本次動到的節點(群島 20 + 2 航道 + 接航道的 woodhearth/greenshade_coast)逐條驗權重對稱。"""
    gd, L = _gd()
    scope = set(_nodes(L)) | {"auridon_strait", "southern_sea_lane", "woodhearth", "greenshade_coast"}
    bad = [(a, b, w, L[b]["links"].get(a)) for a in scope for b, w in L[a]["links"].items()
           if L[b]["links"].get(a) != w]
    assert not bad, bad


def test_summerset_guardian_schools_destruction_and_mysticism_split_by_city():
    """R176 守護學派 A+B(使用者拍板):高精靈毀滅 +10(唯一最高項)→ 毀滅;文獻意象(智者學院)→ 神秘。
    R29 不變式『每城進階學派 ≤1』→ 兩派拆城:阿林諾爾=毀滅、里蘭德里=神秘;省內兩派並存。"""
    gd, L = _gd()
    sk = gd.races["altmer"]["skill_bonuses"]
    assert max(sk, key=sk.get) == "destruction"                       # 評估依據:資料驅動,非憑空
    stocks = {lid: set(l["spell_stock"]) for lid, l in L.items() if l.get("spell_stock")}
    base = set.intersection(*stocks.values())
    mage = sorted(lid for lid, l in _nodes(L).items() if "mages_guild" in l["services"])
    assert mage == ["alinor", "lillandril"]
    schools = {lid: {gd.spells[s]["school"] for s in stocks[lid] - base} for lid in mage}
    assert schools == {"alinor": {"destruction"}, "lillandril": {"mysticism"}}
    for lid in mage:
        assert BASELINE <= stocks[lid]                                 # 保底集:任何法師城皆有


def test_summerset_capital_is_its_only_major_city():
    gd, L = _gd()
    majors = sorted(lid for lid in world.MAJOR_CITIES if L[lid]["province"] == PROV)
    assert majors == ["alinor"]
    cat = world.merchant_catalog(gd, "alinor")
    assert all(m in cat for m in world._HIGH_MATERIALS)                # 首府供應高級材料
    for lid in ("lillandril", "firsthold", "skywatch"):
        assert not any(m in world.merchant_catalog(gd, lid) for m in world._HIGH_MATERIALS)


def test_summerset_every_settlement_has_an_altmer_ruler_and_enough_npcs():
    gd, L = _gd()
    for lid, l in _nodes(L).items():
        if l["type"] not in ("city", "town"):
            continue
        r = gd.ruler_at(lid)
        assert r and r["race"] == "altmer" and r["bloc"] and r["bloc_label"], lid
        want = 3 if l["type"] == "city" else 2
        assert len(gd.npcs_at(lid)) >= want, lid


def test_isle_biome_roster_is_shock_weak_and_bosses_are_unique_spawns():
    gd, L = _gd()
    isle = {cid: c for cid, c in gd.bestiary.items() if "isle" in c.get("biomes", [])}
    assert len(isle) == 7
    for cid, c in isle.items():
        assert not c.get("undead"), cid
        assert "magic" not in c.get("resist", {}), cid                 # shock∈MAGIC_ELEMENTS 會疊 magic 鍵
        assert formulas.resist_multiplier(c.get("resist", {}), "shock") > 1.0, cid
        assert len(c.get("attacks", [])) >= 2, cid                     # 有曲目(BESTIARY 不標「缺曲目」)
    for cid in ("maormer_captain", "snakeskin_leviathan", "sload_prelate"):
        assert gd.bestiary[cid]["weight"] == 0                         # 地城專屬頭目,不入隨機遭遇
        # 慣例:weight 0 的具名地城頭目一律 solo(既有 35/38)——帶偷襲傷害夾與控場機率抗(R44 紅線),
        # 並被領主懸賞素材池排除(court._province_objectives 只排 solo,不看 weight)
        assert gd.bestiary[cid].get("solo") is True, cid
    for cid in ("snakeskin_leviathan", "sload_prelate"):
        assert gd.bestiary[cid].get("raw") is True
    # R144 現實邏輯:水生怪離不開棲地,永不離鄉遊蕩(他鄉權重 0);人形海精靈可遠征劫掠,不綁棲地
    for cid in ("sea_serpent", "yaghra", "sea_sload"):
        c = gd.bestiary[cid]
        assert c.get("habitat_bound") is True, cid
        assert combat._biome_weight(c, "jungle") == 0.0 and combat._biome_weight(c, "isle") > 0, cid
    r = gd.bestiary["maormer_raider"]
    assert not r.get("habitat_bound") and combat._biome_weight(r, "jungle") > 0


def test_summerset_ruler_commissions_only_target_spawnable_creatures():
    """審查抓到的真缺陷:weight 0 的非 solo 頭目(船長)被領主懸賞素材池選中 → 『殺 6 隻船長』
    隨機遭遇永遠遇不到、做不完,還卡住該城受封武士路線。領主懸賞的殺怪目標必須能被抽到。"""
    gd, L = _gd()
    seen = 0
    for lid in _nodes(L):
        r = gd.ruler_at(lid)
        if not r:
            continue
        for qid in r.get("quests", []):
            o = gd.quests[qid].get("objective", {})
            if o.get("type") == "kill":
                seen += 1
                c = gd.bestiary[o["creature"]]
                assert c.get("weight", 1) > 0 and not c.get("solo"), (qid, o["creature"])
    assert seen >= 3                                                   # 7 位領主中至少 3 位拿到殺怪委託(輪替)


def test_summerset_dungeons_bosses_and_board_quests_are_wired():
    gd, L = _gd()
    for lid, l in _nodes(L).items():
        if l["type"] != "dungeon":
            continue
        d = gd.dungeons[l["dungeon"]]
        assert d["biome"] == "isle" and d["danger"] == l["danger"], lid
        assert all(m in gd.bestiary for m in d["monsters"]), lid
        assert d["boss"]["enemy"] in gd.bestiary, lid
        boards = [q for q in gd.quests.values() if q.get("source") == "board"
                  and q.get("objective", {}).get("dungeon") == l["dungeon"]]
        assert boards and all(PROV in q["provinces"] for q in boards), lid
    # 水晶塔=終局級(danger 5)、頭目=斯洛德祭司長
    assert gd.dungeons["crystal_tower"]["boss"]["enemy"] == "sload_prelate"
    assert gd.dungeons["crystal_tower"]["danger"] == 5


def test_summerset_forage_pool_and_province_events():
    gd, L = _gd()
    pool = gd.ecology["pools"]["isle"]
    assert pool["common"] and pool["uncommon"]
    for tier in ("common", "uncommon"):
        for iid in pool[tier]:
            assert iid in gd.ingredients, iid
    evs = [eid for eid, e in gd.events.items() if PROV in e.get("trigger", {}).get("provinces", [])]
    assert sorted(evs) == ["isle_forage", "isle_raider_ambush"]
    # 事件觸發無 biome 篩選(只有 contexts/location_types/provinces)→ 文字須對全省符合節點(海邊/內陸)皆合
    for eid in evs:
        blob = json.dumps(gd.events[eid], ensure_ascii=False)
        assert not re.search(r"潮|白沙|貝殼|礁|海灘|浪", blob), eid
    # 伏擊的對手是抽得到的人形怪(非水生;水生怪已 habitat_bound)
    assert gd.events["isle_raider_ambush"]["options"][0]["effects"][0]["creature"] == "maormer_raider"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_summerset 全通過")
