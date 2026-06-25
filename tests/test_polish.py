"""省份內容補強 pass(非陣營純資料):法術可及性不變式、地城任務覆蓋、forage 省份齊備、
龍狩 NPC + 屠龍任務 完整性。全部資料驅動,守門避免回歸到「某系區域鎖死 / 地城零任務 / 某省無採集」。"""

import json

from tesrpg.gamedata import get_gamedata

ALL_SCHOOLS = {"destruction", "restoration", "alteration", "illusion", "conjuration", "mysticism"}


def _gd():
    return get_gamedata()


# --- 法術可及性 ---------------------------------------------------------
# (spell_stock id 有效性 + 無重複 已併入 test_world.test_shop_stock_ids_are_valid)
def test_every_school_sold_in_multiple_cities():
    gd = _gd()
    school = {k: v["school"] for k, v in gd.spells.items()}
    cities = {sch: set() for sch in ALL_SCHOOLS}
    for lid, loc in gd.world["locations"].items():
        for s in loc.get("spell_stock", []):
            cities[school[s]].add(lid)
    for sch in ALL_SCHOOLS:
        assert len(cities[sch]) >= 3, f"{sch} 僅 {len(cities[sch])} 城可學(防區域鎖死,須 ≥3)"


def test_no_province_locked_out_of_any_school():
    # 每個有城的省份都能在省內買到全部六系(補掉黑沼澤原本無變化術的破口)
    gd = _gd()
    school = {k: v["school"] for k, v in gd.spells.items()}
    prov = {}
    for lid, loc in gd.world["locations"].items():
        for s in loc.get("spell_stock", []):
            prov.setdefault(loc["province"], set()).add(school[s])
    for p, schools in prov.items():
        assert ALL_SCHOOLS <= schools, f"{p} 缺學派:{ALL_SCHOOLS - schools}"
    # 起始省(賽羅迪爾)六系基礎全可及 → 起手不卡(併自 test_start_province_has_all_schools)
    assert "賽羅迪爾" in prov and ALL_SCHOOLS <= prov["賽羅迪爾"], "起始省賽羅迪爾六系須全可及"


# --- 地城任務覆蓋 -------------------------------------------------------
def _quest_dungeon_refs(gd):
    refs = set()
    def objs(qd):
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
    for qd in gd.quests.values():
        for o in objs(qd):
            if o.get("type") in ("clear_dungeon", "reach"):
                refs.add(o.get("dungeon") or o.get("location"))
    return refs


def test_every_dungeon_has_a_quest():
    gd = _gd()
    dungeons = {lid for lid, l in gd.world["locations"].items() if l["type"] == "dungeon"}
    refs = _quest_dungeon_refs(gd)
    uncovered = dungeons - refs
    assert not uncovered, f"這些地城無任務指向:{uncovered}"


def test_dragon_lair_quest_wired():
    gd = _gd()
    hd = gd.quests["hunt_dragon"]
    assert hd["source"] == "npc"
    assert hd["objective"] == {"type": "clear_dungeon", "dungeon": "dragon_lair"}
    assert gd.world["locations"]["dragon_lair"]["type"] == "dungeon"
    for it in hd["reward"].get("items", []):
        assert gd.item(it) is not None, f"hunt_dragon 獎勵 {it} 不存在"
    # NPC↔任務反向接線 + greeting 非空(併自 test_dragon_hunter_npc):
    # greeting 是 load-bearing(console.py 無防護下標,缺欄即對話崩潰)
    npc = gd.npcs["molag_mar_dragonhunter_jorgen"]
    assert npc["quest"] == "hunt_dragon"
    assert npc.get("greeting") and npc.get("rumor")


# --- forage 省份齊備 ----------------------------------------------------
def _is_forage(e):
    # 採集事件特徵:explore 觸發 + 限省份 + 某選項是 forage_pool 生態系採集(R93;
    # 或 legacy「煉金 xp + 物品」固定束),與掠食/風暴等省份事件區隔。
    t = e.get("trigger", {})
    if "explore" not in t.get("contexts", []) or not t.get("provinces"):
        return False
    for opt in e.get("options", []):
        effs = opt.get("effects", [])
        if any(ef.get("type") == "forage_pool" for ef in effs):
            return True
        gives_item = any(ef.get("type") == "item" for ef in effs)
        gives_alch = any(ef.get("type") == "skill_xp" and ef.get("skill") == "alchemy" for ef in effs)
        if gives_item and gives_alch:
            return True
    return False


def test_every_explorable_province_has_forage():
    gd = _gd()
    provs = {loc["province"] for loc in gd.world["locations"].values()}
    forage = {}
    for k, e in gd.events.items():
        if _is_forage(e):
            for p in e["trigger"]["provinces"]:
                forage.setdefault(p, []).append(k)
    for p in provs:
        assert p in forage, f"{p} 無招牌採集事件(forage):已有 {forage}"


def test_new_forage_ingredients_valid():
    gd = _gd()
    ing = set(gd.ingredients)
    pools = gd.ecology["pools"]
    for fe in ("skyrim_forage", "border_forage"):
        e = gd.events[fe]
        assert e["trigger"]["provinces"][0] in {"天際", "邊境"}
        for opt in e["options"]:
            for eff in opt["effects"]:
                if eff["type"] == "item":
                    assert eff["item"] in ing, f"{fe} 不明素材 {eff['item']}"
                elif eff["type"] == "forage_pool":   # R93:採集走生態系池,驗 pool 存在且成員皆合法材料
                    pool = pools[eff["pool"]]
                    for members in pool.values():
                        if isinstance(members, list):
                            assert all(m in ing for m in members), f"{fe} 池含不明素材"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_polish OK")
