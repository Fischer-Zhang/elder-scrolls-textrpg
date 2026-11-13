"""R176 夏暮群島(第九省)專屬回歸:版圖 / 海路連接 / 守護學派 / 生態 / 內容完整性。

文獻依據(UESP·Fandom·Legendarium 摘要):群島在大陸西南、瓦倫森林以西,最近的鄰國僅瓦倫森林,
無任何來源把它連到漢默法爾 → 兩條海路邊境只接瓦倫森林,且是兩個不同入口(成環,不接成走廊尾巴)。"""

import json
import re
from collections import Counter
from types import SimpleNamespace

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import (combat, court, dialogue, dungeon, events, housing, inventory, landmarks, quests, world,
                            worldpulse)

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
    # R178:國王避風隘由野外原地改為地城(使用者拍板)→ 節點總數不變,野外 8→7、地城 5→6
    assert Counter(l["type"] for l in nodes.values()) == {"city": 4, "town": 3, "wilderness": 7, "dungeon": 6}
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
    assert len(isle) == 9                                              # R178:+獅鷲、+「旋風」阿芙瑪
    for cid, c in isle.items():
        assert not c.get("undead"), cid
        assert "magic" not in c.get("resist", {}), cid                 # shock∈MAGIC_ELEMENTS 會疊 magic 鍵
        assert formulas.resist_multiplier(c.get("resist", {}), "shock") > 1.0, cid
        assert len(c.get("attacks", [])) >= 2, cid                     # 有曲目(BESTIARY 不標「缺曲目」)
    for cid in ("maormer_captain", "snakeskin_leviathan", "sload_prelate", "avuuma_whirlwind"):
        assert gd.bestiary[cid]["weight"] == 0                         # 地城專屬頭目,不入隨機遭遇
        # 慣例:weight 0 的具名地城頭目一律 solo(既有 35/38)——帶偷襲傷害夾與控場機率抗(R44 紅線),
        # 並被領主懸賞素材池排除(court._province_objectives 只排 solo,不看 weight)
        assert gd.bestiary[cid].get("solo") is True, cid
    for cid in ("snakeskin_leviathan", "sload_prelate", "avuuma_whirlwind"):
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
    assert sorted(evs) == PROVINCE_EVENTS          # R177 Phase 2:2 → 6(加 4 個省級事件)
    # 事件觸發無 biome 篩選(只有 contexts/location_types/provinces)→ 文字須對全省符合節點(海邊/內陸)皆合
    for eid in evs:
        blob = json.dumps(gd.events[eid], ensure_ascii=False)
        assert not re.search(r"潮|白沙|貝殼|礁|海灘|浪", blob), eid
    # 伏擊的對手是抽得到的人形怪(非水生;水生怪已 habitat_bound)
    assert gd.events["isle_raider_ambush"]["options"][0]["effects"][0]["creature"] == "maormer_raider"


# ═══ R177 Phase 2「風味與深度」══════════════════════════════════════════════════
# 正典依據(UESP 搜尋摘要):Arena「Temple of Mad God」在里蘭德里東南、住著祭司與僧侶;ESO 伊頓尼爾石窟
# 深處有梅瑞迪雅神殿;「The Beautiful」是第三紀元毀壞先祖紀念物的激進團體;獅鷲、神聖檢察院司法官、
# 托里納安(第一位登上群島的先祖)皆出自 Lore/Online 條目。
SETTLEMENTS = ("alinor", "lillandril", "firsthold", "skywatch", "shimmerene", "sunhold", "cloudrest")
REINFEST = ("cey_tarn_keep", "eldbur_ruins", "sil_var_woad", "dusk_keep")
PROVINCE_EVENTS = ["isle_forage", "isle_raider_ambush", "summerset_gryphon_shadow",
                   "summerset_justiciar_check", "summerset_the_beautiful", "wild_summerset_courier"]
PULSES = ("pulse_summerset_searaid", "pulse_summerset_deepstir")
ORIGINS = ("sapiarch_auditor", "sunhold_marine", "skywatch_runner")
LANDMARKS = {"illumination_academy", "eton_nir", "alinor", "auridon_coast"}
GRYPHON_PASS = "kings_haven_pass"                # R178:原地改地城的國王避風隘(「旋風」阿芙瑪的巢)


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="行者", sex="male", race="altmer", birthsign="mage", class_id="mage")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime(), rng=RNG(7))


def _objectives(q):
    return [q["objective"]] if "objective" in q else [s["objective"] for s in q.get("stages", [])]


def _spawnable_in_isle(gd, L, max_min_level=99):
    """群島野外抽得到的怪(口徑同 combat.random_encounter):isle 在地怪 ∪ 無 biome 標籤的通用怪,
    非 solo、weight>0,且 danger ≤ 島上最危險野外節點的 max_danger(=地點 danger+1)。"""
    cap = max(l["danger"] for l in _nodes(L).values() if l["type"] == "wilderness") + 1
    return {cid for cid, c in gd.bestiary.items()
            if (not c.get("biomes") or "isle" in c["biomes"])
            and c.get("weight", 1) > 0 and not c.get("solo")
            and c.get("min_level", 1) <= max_min_level and c.get("danger", 1) <= cap}


def _obtainable_in_isle(gd, L):
    """群島內「實際拿得到」的東西:商店有售 ∪ 野採尋常(common)檔 ∪ 可遇怪掉率 ≥15%。
    刻意不算 uncommon 野採:採集事件每次探索約 4% 且稀有檔產量低,當任務目標等於做不完
    (審查抓到苦綠花瓣 ×3 要上百次探索)。"""
    out = set(gd.ecology["pools"]["isle"]["common"])
    for cid in _spawnable_in_isle(gd, L):
        out |= {e["item"] for e in gd.bestiary[cid].get("loot", []) if e.get("chance", 0) >= 0.15}
    for l in _nodes(L).values():
        out |= set(l.get("merchant_stock") or [])
    return out


def _local_quest_ids(gd, L):
    """群島在地任務:島上 NPC 的委託/流言、野外遇人、脈動聚光、清剿、秘藏、三個開局的起手任務。"""
    isle_npcs = {nid: n for nid, n in gd.npcs.items() if L[n["location"]]["province"] == PROV}
    ids = {n["quest"] for n in isle_npcs.values() if n.get("quest")}
    ids |= {n["rumor_quest"] for n in isle_npcs.values() if n.get("rumor_quest")}
    ids |= {"wq_summerset_courier", "secret_eldbur"}
    ids |= {sq for pid in PULSES for sq in gd.world_pulse[pid]["spotlight_quests"]}
    ids |= {f"dcomm_{did}" for did in REINFEST}
    ids |= {f"job_{GRYPHON_PASS}", f"dcomm_{GRYPHON_PASS}"}          # R178
    ids |= {gd.origins[oid]["quest"] for oid in ORIGINS}
    return ids


def test_r177_temples_are_landmarks_not_altars():
    """使用者拍板「神殿只做地標」:兩座正典神殿立為可發現的地標,不設可供奉的 shrine 祭壇
    → 圖鑑「八省各地散落著戴德拉親王的祭壇」仍屬實,兩位親王的試煉仍只在原祭壇接。"""
    gd, L = _gd()
    assert not [lid for lid, l in _nodes(L).items() if l.get("shrine")], "群島不得出現 shrine 祭壇"
    assert {lid for lid in gd.landmarks if L[lid]["province"] == PROV} == LANDMARKS
    assert gd.landmarks["illumination_academy"]["name"] == "瘋神神殿"
    assert "謝歐格拉斯" in gd.landmarks["illumination_academy"]["discover"]
    assert "梅瑞迪雅" in gd.landmarks["eton_nir"]["discover"]         # 沿用遊戲既有譯名(非另造)
    # 瘋神神殿在里蘭德里東南、且相鄰(Arena:a short way southeast of Lillandril)
    lx, ly = L["lillandril"]["pos"]
    ax, ay = L["illumination_academy"]["pos"]
    assert ax > lx and ay > ly and "illumination_academy" in L["lillandril"]["links"]
    # 走既有發現機制:領賞一次、不重發
    gd, st = _state(location_id="illumination_academy")
    c, rw = st.player, gd.landmarks["illumination_academy"]["reward"]
    g0, f0, n0 = c.gold, c.fame, inventory.count_item(c, "filled_lesser_soul_gem")
    assert landmarks.discover(st, gd, "illumination_academy")["name"] == "瘋神神殿"
    assert (c.gold - g0, c.fame - f0) == (rw["gold"], rw["fame"])
    assert inventory.count_item(c, "filled_lesser_soul_gem") - n0 == 1
    assert landmarks.discover(st, gd, "illumination_academy") is None


def test_r177_every_settlement_has_a_local_npc_quest():
    """七個聚落各有一位 NPC 給一次性委託(Phase 1 全省 0 件);好感閘高於初始好感(要先打好關係)。"""
    gd, L = _gd()
    for lid in SETTLEMENTS:
        givers = [(nid, n) for nid, n in gd.npcs.items() if n["location"] == lid and n.get("quest")]
        assert len(givers) == 1, f"{lid} 委託 NPC 數 {len(givers)}"
        nid, n = givers[0]
        q = gd.quests[n["quest"]]
        assert q["source"] == "npc" and not q.get("repeatable")
        assert n["disposition"] < n["quest_disposition"] <= 100, nid
        c = _state()[1].player
        assert dialogue.offered_quest(c, gd, nid) is None                # 初始好感不給
        c.npc_disposition[nid] = n["quest_disposition"] - n["disposition"]
        assert dialogue.offered_quest(c, gd, nid) == n["quest"]


def test_r177_local_quest_objectives_are_achievable_inside_the_province():
    """在地任務的目標都在群島內辦得到:獵殺對象抽得到、蒐集物拿得到、要去的地方在島上
    (否則委託文字說「群島野外可尋」卻永遠遇不到)。起手任務另限 min_level 1(一級角色即可完成)。"""
    gd, L = _gd()
    nodes, spawn, have = _nodes(L), _spawnable_in_isle(gd, L), _obtainable_in_isle(gd, L)
    origin_q = {gd.origins[oid]["quest"] for oid in ORIGINS}
    lvl1 = _spawnable_in_isle(gd, L, max_min_level=1)
    for qid in sorted(_local_quest_ids(gd, L)):
        for o in _objectives(gd.quests[qid]):
            t = o["type"]
            if t == "kill":
                assert o["creature"] in (lvl1 if qid in origin_q else spawn), f"{qid}: {o['creature']}"
            elif t == "collect":
                assert o["item"] in have, f"{qid}: {o['item']} 在群島拿不到"
            elif t == "reach":
                assert o["location"] in nodes, f"{qid}: {o['location']} 不在群島"
            elif t in ("clear_dungeon", "purge_dungeon"):
                assert o["dungeon"] in nodes, f"{qid}: {o['dungeon']} 不在群島"
            else:
                raise AssertionError(f"{qid}: 未預期的 objective {t}")


def test_r177_pulses_spotlight_local_repeatables():
    """兩個脈動各聚光 3 個可重複委託;脈動激增時才上群島告示板、別省不現、過窗消失。"""
    gd, L = _gd()
    for pid in PULSES:
        p = gd.world_pulse[pid]
        assert p["province"] == PROV and len(p["spotlight_quests"]) == 3
        for sq in p["spotlight_quests"]:
            q = gd.quests[sq]
            assert q["source"] == "board" and q["repeatable"] and "provinces" not in q, sq
            assert _objectives(q)[0]["type"] != "reach", sq
    c, today = _state()[1].player, 500
    pid = PULSES[0]
    spot = set(gd.world_pulse[pid]["spotlight_quests"])
    assert not spot & set(quests.available_quests(c, gd, "board", province=PROV, day=today))
    c.world_pulse_day[pid] = today
    assert worldpulse.spotlighted_board_quests(c, gd, PROV, today) == spot
    assert spot <= set(quests.available_quests(c, gd, "board", province=PROV, day=today))
    assert not spot & set(quests.available_quests(c, gd, "board", province="瓦倫森林", day=today))
    window = gd.world_pulse[pid]["active_window_days"]
    assert not spot & set(quests.available_quests(c, gd, "board", province=PROV, day=today + window))


def test_r177_reinfest_variants_stay_in_tier_and_dungeons_are_featured():
    """四座泛用地城配重踞變體 + 特色格 + 清剿委託;水晶塔(終局級)維持特殊、兩者皆無。
    變體不越階:頭目與雜兵的 danger 都 ≤ 該地城 danger(R11:難度靠 min_level + danger)。"""
    gd, L = _gd()
    pay = {3: (65, 1), 4: (85, 2)}                      # 同他省 dcomm 的 danger→報酬行情
    for did in REINFEST:
        spec = gd.dungeons[did]
        rb = spec["reinfest"]
        assert rb["boss"]["enemy"] != spec["boss"]["enemy"], did
        for cid in rb["monsters"] + [rb["boss"]["enemy"]]:
            assert gd.bestiary[cid].get("danger", 1) <= spec["danger"], f"{did}: {cid} 越階"
        eff = dungeon.effective_spec(gd, did, infested=True)
        assert (eff["monsters"], eff["boss"]["enemy"]) == (rb["monsters"], rb["boss"]["enemy"])
        assert dungeon.effective_spec(gd, did, infested=False)["boss"] == spec["boss"]
        kinds = Counter(gd.dungeon_features[f]["kind"] for f in spec["features"])
        assert kinds == {"lore": 1, "shrine": 1, "puzzle": 2}, f"{did}: {dict(kinds)}"
        assert "shrine_tidal_prism" in spec["features"]
        dc = gd.quests[f"dcomm_{did}"]
        assert dc["objective"] == {"type": "purge_dungeon", "dungeon": did}
        assert dc["provinces"] == [PROV] and dc["repeatable"]
        assert (dc["reward"]["gold"], dc["reward"]["fame"]) == pay[spec["danger"]], did
    apex = gd.dungeons["crystal_tower"]
    assert not apex.get("reinfest") and not apex.get("features")
    # 群島祭壇的抗毒選項貼在地威脅:島上的怪確實用毒(海蛇毒牙/斯洛德腐液)
    offers = {o["buff"]["param"] for o in gd.dungeon_features["shrine_tidal_prism"]["offers"]}
    assert offers == {"intelligence", "poison"}
    assert any(a.get("element") == "poison" for cid in _spawnable_in_isle(gd, L)
               for a in gd.bestiary[cid].get("attacks", []))


def test_r177_houses_stables_and_capital_master_trainer():
    """房產 2(王都宅邸 + 奧里頓小屋)、馬廄設在同兩城、王都宗師教幻術(全圖唯一的幻術宗師)。"""
    gd, L = _gd()
    isle_houses = {lid: h for lid, h in gd.houses.items() if lid in L and L[lid]["province"] == PROV}
    assert {lid: h["tier"] for lid, h in isle_houses.items()} == {"alinor": 2, "skywatch": 1}
    for lid in isle_houses:
        assert housing.garden_pool_id(gd, lid) == "isle"              # 藥草園接得上群島生態池
    assert {lid for lid in _nodes(L) if gd.has_stable(lid)} == set(isle_houses)
    assert world.trainer_cap(gd, "alinor", "illusion") == formulas.SKILL_CAP
    assert "illusion" in world.trainer_skills(gd, "alinor", "magic")
    masters = [lid for lid in L if (gd.trainer_data(lid) or {}).get("master", {}).get("skill") == "illusion"]
    assert masters == ["alinor"]
    assert world.trainer_cap(gd, "lillandril", "illusion") == formulas.TRAINER_CAP


def test_r177_origins_start_in_safe_settlements_with_live_quests():
    """三個開局:起在群島的安全聚落(非地城·danger 0)、起手任務已接且未即時達標、歸在對的選單分類。"""
    import tesrpg.main as M
    gd, L = _gd()
    cat = {oid: label for label, oids in M.ORIGIN_CATEGORIES for oid in oids}
    want = {"sapiarch_auditor": "法師", "sunhold_marine": "戰士", "skywatch_runner": "潛行"}
    for oid in ORIGINS:
        od = gd.origins[oid]
        loc = L[od["location"]]
        assert loc["province"] == PROV and loc["type"] in ("city", "town") and loc["danger"] == 0, oid
        assert want[oid] in cat[oid], f"{oid} 歸類 {cat.get(oid)}"
        c = build_character(gd, name="T", sex="male", race="altmer", birthsign="warrior",
                            class_id="warrior", origin_id=oid, is_player=True)
        assert c.location_id == od["location"] and od["quest"] in c.quests
        assert not quests.objective_met(c, gd, od["quest"]), f"{oid}: 起手任務創角即達標"
    mage = build_character(gd, name="T", sex="male", race="altmer", birthsign="mage",
                           class_id="mage", origin_id="sapiarch_auditor", is_player=True)
    assert "arcane_bolt" in mage.spells and "mages_guild" in mage.factions


def test_r177_secrets_and_rumor_leads_pay_out_once():
    """套話秘密 3 筆(開鎖器 / 暗帳金 / 秘藏線索)與流言線索(2 地標 + 2 地城)走既有機制兌現。"""
    gd, L = _gd()
    pump = {"id": "pump_for_info", "action": "pump"}

    def do_pump(c, nid):
        """套話到成功為止(口才 100 仍非必中;換種子重試,不綁單一首擲)。"""
        for seed in range(1, 40):
            st = GameState(player=c, rng=RNG(seed), game_mode="adventure")
            if dialogue._do_pump(st, gd, nid, pump, dialogue.talk_ctx(st, gd, nid), RNG(seed))["ok"]:
                return
        raise AssertionError(f"{nid} 套話 39 次皆失敗")

    c = _state()[1].player
    c.skills["speechcraft"] = 100
    n0, g0 = inventory.count_item(c, "lockpick"), c.gold
    do_pump(c, "skywatch_smuggler")
    assert inventory.count_item(c, "lockpick") - n0 == 3
    do_pump(c, "firsthold_harbormaster")
    assert c.gold - g0 == 65
    do_pump(c, "firsthold_harbormaster")                                  # 再套話不重發
    assert c.gold - g0 == 65
    do_pump(c, "lillandril_scribe")
    assert "secret_eldbur" in c.quests and gd.quests["secret_eldbur"]["objective"]["dungeon"] == "eldbur_ruins"

    c = _state()[1].player
    for nid in ("cloudrest_hermit", "lillandril_archivist", "firsthold_sailor", "cloudrest_stargazer"):
        c.npc_disposition[nid] = -60                                       # 交惡 → 不透露(好感閘)
        assert dialogue.offered_rumor(c, gd, nid) is None
        c.npc_disposition[nid] = 0                                         # 回到初始好感即肯說(同他省行情)
    assert dialogue.offered_rumor(c, gd, "cloudrest_hermit") == {"kind": "landmark", "id": "eton_nir"}
    assert dialogue.offered_rumor(c, gd, "lillandril_archivist") == {"kind": "landmark", "id": "illumination_academy"}
    assert dialogue.offered_rumor(c, gd, "firsthold_sailor") == {"kind": "quest", "id": "rumor_dusk_keep"}
    assert dialogue.offered_rumor(c, gd, "cloudrest_stargazer") == {"kind": "quest", "id": "rumor_crystal_tower"}
    c.cleared_dungeons.append("dusk_keep")                                 # 已肅清 → 不再派(防接取即完成)
    assert dialogue.offered_rumor(c, gd, "firsthold_sailor") is None


def test_r177_province_events_are_wired_and_checks_use_real_skills():
    """四個新省級事件:野外遇人能派任務、檢定用真實技能、效果型別在引擎支援集內。"""
    gd, L = _gd()
    supported = {"gold", "message", "fame", "infamy", "bounty", "skill_xp", "damage", "start_quest", "combat"}
    for eid in PROVINCE_EVENTS[2:]:
        ev = gd.events[eid]
        assert ev["trigger"]["provinces"] == [PROV] and len(ev["options"]) >= 3, eid
        assert any("requirements" not in o for o in ev["options"]), f"{eid} 需有恆可選的選項(檢定不算門檻)"
        for o in ev["options"]:
            effs = list(o.get("effects", []))
            if "check" in o:
                assert o["check"]["skill"] in gd.skills, eid
                effs += o["check"]["success"]["effects"] + o["check"]["failure"]["effects"]
            assert {e["type"] for e in effs} <= supported, eid
    start = [e["quest"] for o in gd.events["wild_summerset_courier"]["options"]
             for e in o.get("effects", []) if e["type"] == "start_quest"]
    assert start == ["wq_summerset_courier"] and gd.quests[start[0]]["source"] == "npc"


def test_r177_roadside_events_do_not_fire_at_dungeon_nodes():
    """「路口關卡」「路旁石像」是路邊場景:抵達地城節點時不該觸發(審查抓到:原本只擋省份不擋地點類型)。"""
    roadside = {"summerset_justiciar_check", "summerset_the_beautiful"}
    gd, st = _state(location_id="crystal_tower")
    for eid in roadside:
        assert "dungeon" not in gd.events[eid]["trigger"]["location_types"], eid
    assert not roadside & set(events.eligible_events(st, gd, "travel"))
    st.player.location_id = "veyond_wyte"
    assert roadside <= set(events.eligible_events(st, gd, "travel"))
    # R178:國王避風隘改地城後,同樣不再有路邊場景(也不再有野外限定的獅鷲掠空)
    st.player.location_id = "kings_haven_pass"
    assert not (roadside | {"summerset_gryphon_shadow"}) & set(events.eligible_events(st, gd, "travel"))


def test_r177_forage_event_share_not_diluted_below_other_provinces():
    """群島草藥只靠採集事件取得:加省級事件不得把採集事件在「探索事件池」的占比擠到低於他省最低
    (審查量到 11.5% → 8.8%,低於全部他省;「美麗者」改為只在旅途觸發後回到他省水準)。"""
    gd, L = _gd()
    explore = {eid: e for eid, e in gd.events.items() if "explore" in e["trigger"].get("contexts", [])}
    generic = sum(e["weight"] for e in explore.values() if not e["trigger"].get("provinces"))

    def share(prov):
        mine = [e for e in explore.values() if prov in e["trigger"].get("provinces", [])]
        forage = sum(e["weight"] for e in mine
                     if any(ef.get("type") == "forage_pool" for o in e["options"] for ef in o.get("effects", [])))
        return forage / (generic + sum(e["weight"] for e in mine))

    others = {l["province"] for l in L.values()} - {PROV, "邊境"}
    assert share(PROV) >= min(share(p) for p in others), f"群島採集占比 {share(PROV):.3f} 低於他省"


def test_r177_rumor_rewards_stay_within_existing_band():
    """流言線索的賞金不得高於他省既有上限(rumor 不在 test_detailing 的賞金守門範圍內,在地補鎖)。"""
    gd, L = _gd()
    rumors = {qid: q for qid, q in gd.quests.items() if q.get("source") == "rumor"}
    mine = {qid for qid, q in rumors.items() if PROV in q.get("provinces", [])}
    assert mine == {"rumor_dusk_keep", "rumor_crystal_tower"}
    cap_gold = max(q["reward"]["gold"] for qid, q in rumors.items() if qid not in mine)
    cap_fame = max(q["reward"]["fame"] for qid, q in rumors.items() if qid not in mine)
    for qid in mine:
        rw = rumors[qid]["reward"]
        assert rw["gold"] <= cap_gold and rw["fame"] <= cap_fame, f"{qid}: {rw}"
        assert L[_objectives(rumors[qid])[0]["dungeon"]]["province"] == PROV


# 任務文字裡用來指稱獵殺對象的字眼(海蛇在文字裡也寫作「巨蛇」)
_CREATURE_WORD = {"maormer_raider": "突襲者", "sea_serpent": "蛇", "sea_sload": "斯洛德", "yaghra": "亞格拉",
                  "mudcrab": "泥蟹", "giant_rat": "巨鼠"}


def test_r177_quest_text_matches_objective():
    """R80 鐵律「任務 text 的數量/對象/地點須與 objective 一致」的在地自動守門(審查用變異探測證實:
    把數量、地點或派發 NPC 改錯,原本全套測試無一變紅)。逐階段比對:
    獵殺/蒐集的對象與數量、要去的地名、清剿的地城名,以及派發 NPC 的名字,都要出現在任務文字裡。"""
    gd, L = _gd()
    giver = {n["quest"]: n["name"].split()[-1] for n in gd.npcs.values()
             if L[n["location"]]["province"] == PROV and n.get("quest")}
    assert len(giver) == len(SETTLEMENTS)
    for qid in sorted(_local_quest_ids(gd, L)):
        q = gd.quests[qid]
        for s in q.get("stages") or [{"objective": q["objective"]}]:
            o, text = s["objective"], q["text"] + s.get("text", "")
            t = o["type"]
            if t in ("kill", "collect"):
                word = (_CREATURE_WORD[o["creature"]] if t == "kill"
                        else (gd.ingredients.get(o["item"]) or gd.item(o["item"]))["name"])
                assert word in text, f"{qid}: 文字沒提到「{word}」"
                assert str(o["count"]) in text or (o["count"] == 1 and "一" in text), f"{qid}: 數量 {o['count']} 與文字不符"
            elif t == "reach":
                assert L[o["location"]]["name"] in text, f"{qid}: 文字沒提到 {L[o['location']]['name']}"
            else:                                                  # clear_dungeon / purge_dungeon
                assert L[o["dungeon"]]["name"] in text, f"{qid}: 文字沒提到 {L[o['dungeon']]['name']}"
        if qid in giver:
            assert giver[qid] in q["text"], f"{qid}: 文字沒提到派發者 {giver[qid]}"


# ═══ R178 獅鷲:野怪 + 「旋風」阿芙瑪 + 國王避風隘原地改地城 + 獅鷲掠空加險 ═══════════════════════════
# 正典(UESP Lore:Gryphon / Online:Avuuma the Whirlwind / Online:King's Haven Pass):獅鷲是群島的大型肉食
# 飛行掠食者;阿芙瑪是國王避風隘地城的頭目,窩在滿地碎骨的巢裡;隘內住著裂珊哥布林部落。
# 名字出自第二紀元,遊戲在第三紀元末 → 寫成「島民世代相傳的名號」,不寫成同一隻。
_COASTAL = r"潮|白沙|貝殼|礁|海灘|沙灘|浪|海風|海岸|港|漁|船"       # 山隘/內陸不該出現的海邊意象
_WOODLAND = r"樹林|林蔭|枝葉|林間"                                 # 海灘節點不該出現的林地意象
_CONTROL_HARD = {"stagger", "paralyze", "fear"}


def test_r178_gryphon_event_every_option_carries_risk():
    """使用者點名:提高失敗傷害;「站定不動」不得再零風險(原為純訊息,壓過另兩個有風險的選項)。"""
    gd, st = _state(location_id="eton_nir")
    ev = gd.events["summerset_gryphon_shadow"]
    assert ev["trigger"]["location_types"] == ["wilderness"]
    checks = [o["check"] for o in ev["options"]]                    # 三個選項都要過檢定
    assert [c["skill"] for c in checks] == ["sneak", "athletics", "speechcraft"]
    dmg = [next(e["amount"] for e in c["failure"]["effects"] if e["type"] == "damage") for c in checks]
    # 事件裡的一爪 ≈ 牠在戰鬥裡的一擊(事件傷害不吃護甲 → 下限取最輕招式的八成,上限不超過最重一招)
    hits = [a["damage"] for a in gd.bestiary["gryphon"]["attacks"]]
    assert all(0.8 * min(hits) <= d <= max(hits) for d in dmg), dmg
    # 站定不動=風險與回報皆最高:檢定最難、失敗最痛,成功才有名聲
    stand = checks[2]
    assert dmg[2] == max(dmg) and stand["difficulty"] == max(c["difficulty"] for c in checks)
    assert stand["success"]["effects"] == [{"type": "fame", "amount": 2},
                                           {"type": "skill_xp", "skill": "speechcraft", "amount": 0.8}]
    assert all("fame" not in {e["type"] for e in c["success"]["effects"]} for c in checks[:2])
    # 新手沒有穩贏的選項(審查實測 110 種種族×職業:最佳選項成功率 17–47%)
    assert max(events.check_chance(st.player, c) for c in checks) < 0.5
    assert "summerset_gryphon_shadow" in events.eligible_events(st, gd, "travel")
    # 全省野外皆可觸發(海灘到山麓)→ 文字須地形中性(R177②;原「衝向樹林」在海灘不通)
    assert not re.search(_COASTAL + "|" + _WOODLAND, json.dumps(ev, ensure_ascii=False))


def test_r178_wild_gryphon_is_a_mountain_predator_that_stays_home():
    gd, L = _gd()
    g = gd.bestiary["gryphon"]
    assert (g["danger"], g["min_level"]) == (4, 7) and g["weight"] > 0 and not g.get("solo")
    assert g.get("habitat_bound") is True                           # 群島特有種:不離鄉遊蕩
    assert combat._biome_weight(g, "jungle") == 0.0 and combat._biome_weight(g, "isle") > 0
    assert "physical" not in g.get("resist", {})                    # R128:羽毛血肉,凡兵有效
    # 野外「探索」只在山區遇得到:max_danger(=地點 danger+1)構得著 danger 4 的野外節點只有兩處(正典棲地)。
    # 「旅途」遭遇另算:走進任何 danger ≥3 的群島節點(含南岸地城)都可能抽到 —— 全省統一 isle、
    # 引擎無地形篩選(同 R176 海蛇會出現在山麓;handoff §6 的 P4)。獅鷲會飛,正典在西南雷倫希爾一帶也有巢。
    wild = {lid for lid, l in _nodes(L).items() if l["type"] == "wilderness" and l["danger"] + 1 >= g["danger"]}
    assert wild == {"eton_nir", "veyond_wyte"}

    def seen(lid, level, n=400):                                    # 引擎口徑實抽
        rng = RNG(11)
        return {combat.random_encounter(gd, level, rng, L[lid]["danger"] + 1, "isle").template_id for _ in range(n)}

    assert "gryphon" in seen("eton_nir", 10) and "gryphon" in seen("veyond_wyte", 7)
    assert "gryphon" not in seen("rellenthil", 30) and "gryphon" not in seen("eton_nir", 6)
    assert "avuuma_whirlwind" not in seen("eton_nir", 30) | seen(GRYPHON_PASS, 30)      # 具名頭目不遊蕩


def test_r178_kings_haven_pass_is_avuumas_dungeon():
    gd, L = _gd()
    node, spec = L[GRYPHON_PASS], gd.dungeons[GRYPHON_PASS]
    assert node["type"] == "dungeon" and node["dungeon"] == GRYPHON_PASS and node["danger"] == spec["danger"] == 4
    # 原地改、不搬家:座標與山道連線不動,雲棲往東岸仍經此隘
    assert node["pos"] == [6, 17] and node["links"] == {"eton_nir": 1, "veyond_wyte": 1}
    assert "veyond_wyte" in _reach(L, "eton_nir", banned=("eldbur_ruins", "firsthold", "eastern_pass"))
    wild, boss = gd.bestiary["gryphon"], gd.bestiary[spec["boss"]["enemy"]]
    assert spec["boss"]["enemy"] == "avuuma_whirlwind" and spec["boss"]["raw"] is True
    assert boss["solo"] is True and boss["weight"] == 0 and boss["danger"] == 5
    assert boss["min_level"] > wild["min_level"] and boss["max_health"] > 2 * wild["max_health"]
    assert min(a["damage"] for a in boss["attacks"]) > min(a["damage"] for a in wild["attacks"])
    assert spec["boss"].get("named") is True and boss["name"] == "「旋風」阿芙瑪"      # 以本名登場
    peers = [gd.bestiary[c]["max_health"] for c in ("snakeskin_leviathan", "sload_prelate")]
    assert min(peers) <= boss["max_health"] <= max(peers)                              # 群島 danger 5 頭目帶
    for c in (wild, boss):
        first = {k: v for k, v in c["attacks"][0].items() if k != "weight"}
        assert c["attack"] == first, c["name"]                                         # 單招=曲目首招
        for a in c["attacks"]:                                                         # R43 控場紀律
            oh = a.get("on_hit")
            if oh:
                hard = oh["status"] in _CONTROL_HARD
                assert oh["chance"] <= (0.30 if hard else 0.35) and oh["turns"] <= (1 if hard else 2), a["name"]
                assert oh.get("magnitude", 0) <= 0.3, a["name"]
    gust = next(a for a in boss["attacks"] if a["name"] == "旋風振翼")
    assert gust.get("ranged") is True and "element" not in gust     # R145:狂風非接觸 → 不吃荊棘/盾反
    # 正典:裂珊哥布林 + 獅鷲;雜兵不越階
    assert {"goblin", "gryphon"} <= set(spec["monsters"])
    rb = spec["reinfest"]
    assert rb["boss"]["enemy"] == "gryphon"                         # 空巢引來新的獅鷲(名號世代相傳)
    assert "raw" not in rb["boss"] and "named" not in rb["boss"]    # 走 spawn_boss 強化;還沒有名號
    tier = gd.dungeons["dusk_keep"]                                 # 同為 danger 4:規模與經濟一致
    assert all(spec[k] == tier[k] for k in ("grid", "layers", "loot_locked"))
    gold = lambda b: next(x["gold"] for x in b["treasure"]["loot"] if isinstance(x, dict))
    assert gold(spec["boss"]) == gold(tier["boss"]) and gold(rb["boss"]) == gold(tier["reinfest"]["boss"])
    for cid in spec["monsters"] + rb["monsters"] + [rb["boss"]["enemy"]]:
        assert gd.bestiary[cid].get("danger", 1) <= spec["danger"], f"{cid} 越階"
    eff = dungeon.effective_spec(gd, GRYPHON_PASS, infested=True)
    assert (eff["monsters"], eff["boss"]["enemy"]) == (rb["monsters"], "gryphon")
    assert dungeon.effective_spec(gd, GRYPHON_PASS, infested=False)["boss"] == spec["boss"]
    kinds = Counter(gd.dungeon_features[f]["kind"] for f in spec["features"])
    assert kinds == {"lore": 1, "shrine": 1, "puzzle": 2}
    # 山隘不放「潮光稜晶」,整座地城文字不帶海邊意象;祭壇的抗電選項貼在地威脅(隘底的哥布林薩滿放電)
    assert "shrine_tidal_prism" not in spec["features"]
    texts = [spec, node["desc"]] + [gd.dungeon_features[f] for f in spec["features"]]
    assert not re.search(_COASTAL, json.dumps(texts, ensure_ascii=False))
    shrine = next(f for f in spec["features"] if gd.dungeon_features[f]["kind"] == "shrine")
    offers = {o["buff"]["param"] for o in gd.dungeon_features[shrine]["offers"]}
    threats = {a.get("element") for cid in spec["monsters"] for a in gd.bestiary[cid].get("attacks", [])}
    assert "shock" in offers & threats
    # 告示板懸賞 + 重踞清剿:報酬比照同為 danger 4 的暮色塔
    job, dc = gd.quests[f"job_{GRYPHON_PASS}"], gd.quests[f"dcomm_{GRYPHON_PASS}"]
    assert job["objective"] == {"type": "clear_dungeon", "dungeon": GRYPHON_PASS} and job["provinces"] == [PROV]
    assert job["reward"] == gd.quests["job_dusk_keep"]["reward"]
    assert dc["objective"] == {"type": "purge_dungeon", "dungeon": GRYPHON_PASS}
    assert dc["provinces"] == [PROV] and dc["repeatable"] and dc["reward"] == gd.quests["dcomm_dusk_keep"]["reward"]


# ═══ R179 獅鷲收尾:委託任務排除獅鷲 + 阿芙瑪加心智攻擊(使用者拍板)═══════════════════════════════════
def test_r179_gryphons_are_never_commission_targets():
    """正典:高精靈敬重獅鷲 → 領主不懸賞獵殺。`no_bounty` 把牠擋在領主程序委託素材池外,
    靜態任務(告示板/NPC/脈動)與載入時寫入的領主委託也都不得以牠為獵殺目標。"""
    gd, L = _gd()
    banned = {cid for cid, c in gd.bestiary.items() if c.get("no_bounty")}
    assert banned == {"gryphon"}
    creatures, dungeons_ = court._province_objectives(gd)[PROV]
    assert "gryphon" not in creatures and "yaghra" in creatures     # 同級的亞格拉照常可懸賞(旗標只排獅鷲)
    assert GRYPHON_PASS in [d for d, _name in dungeons_]            # 巢穴本身仍可被懸賞清剿(頭目傷人)
    # 反證:擋下牠的是旗標本身(拿掉旗標就會進池)——不改動共用的 gamedata
    bare = {k: v for k, v in gd.bestiary["gryphon"].items() if k != "no_bounty"}
    probe = SimpleNamespace(world=gd.world, bestiary={**gd.bestiary, "gryphon": bare})
    assert "gryphon" in court._province_objectives(probe)[PROV][0]
    def every_objective(q):                                         # 主線 + 所有分支(24 個任務有 branches)
        for part in [q] + list(q.get("branches", [])):
            yield from _objectives(part)
    assert any(o.get("type") == "kill" for q in gd.quests.values() for b in q.get("branches", []) for o in _objectives(b))
    kills = [(qid, o["creature"]) for qid, q in gd.quests.items() for o in every_objective(q) if o.get("type") == "kill"]
    assert any(qid.startswith("ruler_auto_") for qid, _ in kills)   # 領主程序委託確實在掃描範圍內
    assert not [k for k in kills if k[1] in banned]


def test_r179_avuuma_mixes_physical_and_mind_attacks():
    """使用者點名:阿芙瑪加精神類攻擊(原本純物理,板甲/重盾擋得太輕鬆)。
    R145:心智攻擊標 element magic、非投射;R43/R44:恐懼=硬控,機率 ≤0.30、1 回合。"""
    gd, L = _gd()
    wild, boss = gd.bestiary["gryphon"], gd.bestiary["avuuma_whirlwind"]
    mind = [a for a in boss["attacks"] if a.get("element") == "magic"]
    phys = [a for a in boss["attacks"] if "element" not in a]
    assert len(mind) == 1 and len(phys) == 3
    screech = mind[0]
    assert screech["on_hit"] == {"status": "fear", "turns": 1, "chance": 0.25} and not screech.get("ranged")
    assert min(a["damage"] for a in phys) <= screech["damage"] <= max(a["damage"] for a in phys)
    assert boss["attacks"][-1].get("cooldown") and "cooldown" not in screech    # 冷卻大招殿後;長唳是常規招
    claw = boss["attacks"][0]
    assert screech["weight"] == 2 < claw["weight"] and screech["skill"] == claw["skill"]   # 主招仍是利爪;命中不特別準
    assert all("element" not in a for a in wild["attacks"])                     # 野生同類仍是純物理
    assert "magic" not in boss.get("resist", {})                                # R176②:isle 怪不帶 magic 鍵


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_summerset 全通過")
