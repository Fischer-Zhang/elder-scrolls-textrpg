"""R146 地城第三互動格 FEATURE(祭壇/碑文/機關):catalog FK/schema、shrine 安全池(守 byte-identical)、
generate 佈格(opt-in·對照組永不生成)、resolve 煙霧(三 kind)、零新存檔欄。"""
from tesrpg.gamedata import get_gamedata
from tesrpg.creation import build_character
from tesrpg.state import GameState, GameTime
from tesrpg.rng import RNG
from tesrpg.systems import dungeoncrawl
from tesrpg import formulas
import tesrpg.main as main

gd = get_gamedata()

_FORBIDDEN_ATTR = {"strength"}                                   # 🔴 shrine 安全池:力量禁
_FORBIDDEN_SKILL = {"blade", "blunt", "hand_to_hand", "marksman", "sneak"}   # 武器技能 + 潛行禁
_BUFF_CAP = {"fortify_attribute": 15, "fortify_skill": 19, "resist_element": 30}


def _p(seed=1):
    c = build_character(gd, name="F", sex="male", race="breton", birthsign="mage", class_id="mage")
    c.skills.update(alteration=60, security=60, restoration=50)
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=12))
    return c, st


def _silence():
    om, ol, os = main.ui.message, main.ui.loot_report, main.ui.show_events
    main.ui.message = lambda *a, **k: None
    main.ui.loot_report = lambda *a, **k: None
    main.ui.show_events = lambda *a, **k: None
    return om, ol, os


def _restore(saved):
    main.ui.message, main.ui.loot_report, main.ui.show_events = saved


# --- 1. catalog FK / schema ------------------------------------------------
def test_catalog_schema_and_fk():
    for fid, f in gd.dungeon_features.items():
        if fid.startswith("_"):
            continue
        kind = f.get("kind")
        assert kind in ("shrine", "lore", "puzzle"), f"{fid} kind 非法:{kind}"
        if kind == "lore":
            assert f.get("text"), f"{fid} lore text 空"
        elif kind == "shrine":
            assert f.get("offers"), f"{fid} shrine 無 offers"
            for o in f["offers"]:
                b = o["buff"]
                assert b["kind"] in _BUFF_CAP, f"{fid} buff kind {b['kind']}"
                if b["kind"] == "fortify_attribute":
                    assert b["param"] in formulas.ATTRIBUTES
                elif b["kind"] == "fortify_skill":
                    assert b["param"] in gd.skills
                else:
                    assert b["param"] in ("physical", "fire", "frost", "shock", "magic", "poison", "disease")
                assert b["hours"] > 0
                if o.get("risk"):
                    _check_risk(fid, o["risk"])
        elif kind == "puzzle":
            assert f["check"] in gd.skills, f"{fid} check 非技能"
            assert isinstance(f.get("difficulty"), (int, float))
            for e in (f.get("reward") or {}).get("loot", []):
                iid = e if isinstance(e, str) else e.get("item")
                if iid:
                    assert gd.item_or_none(iid), f"{fid} reward item {iid} 不存在"
            if f.get("penalty"):
                _check_risk(fid, f["penalty"])


def _check_risk(fid, r):
    assert r["type"] in ("damage", "curse"), f"{fid} risk type {r['type']}"
    if r["type"] == "damage":
        lo, hi = r["amount"]
        assert 0 < lo <= hi
    else:
        assert r["skill"] in gd.skills, f"{fid} curse skill {r['skill']}"


def test_dungeons_features_ref_valid():
    import json
    D = json.load(open("tesrpg/data/dungeons.json"))
    seen = 0
    for did, d in D.items():
        for fid in d.get("features", []):
            assert fid in gd.dungeon_features, f"{did} 引用不存在的特色格 {fid}"
            seen += 1
    assert seen >= 3, "應至少 wire 幾座示範地城"


# --- 1b. R151 內容擴充:泛用地城全鋪 + puzzle 階配 danger + 對照組仍空 --------
_LOW_PUZZLES = {"puzzle_cracked_coffer", "puzzle_alchemists_lock"}     # danger 1-2
_HIGH_PUZZLES = {"puzzle_soul_conduit", "puzzle_sealed_reliquary"}     # danger 5


def test_r151_generic_dungeons_all_featured():
    """R151:泛用探索地城(帶 reinfest)除對照組 cedernoc_cave 外皆宣告 features;cedernoc 仍空。"""
    missing = []
    for did, d in gd.dungeons.items():
        if not d.get("reinfest"):
            continue                                   # 特殊/首領地城不在此輪
        if did == "cedernoc_cave":
            assert not d.get("features"), "cedernoc_cave 須維持無 features(負控制組)"
            continue
        if not d.get("features"):
            missing.append(did)
    assert not missing, f"泛用地城未鋪 features:{missing}"


def test_r151_puzzle_tier_matches_danger():
    """R151:低階 puzzle 不得出現在 danger>2 地城、高階 puzzle 不得出現在 danger<5 地城
    (∵ 每層 rng.choice(pool) → 池內每 id 都可能被抽中,故必須全池階配)。"""
    bad = []
    for did, d in gd.dungeons.items():
        dg = d.get("danger", 0)
        for fid in d.get("features", []):
            if fid in _LOW_PUZZLES and dg > 2:
                bad.append((did, dg, fid, "low-puzzle-in-high-danger"))
            if fid in _HIGH_PUZZLES and dg < 5:
                bad.append((did, dg, fid, "high-puzzle-in-low-danger"))
    assert not bad, f"puzzle 階配錯誤:{bad}"


# --- 2. 🔴 shrine 安全池(平衡紅線·免-re-sim)------------------------------
def test_shrine_safe_pool_r146():
    for fid, f in gd.dungeon_features.items():
        if fid.startswith("_") or f.get("kind") != "shrine":
            continue
        for o in f["offers"]:
            b = o["buff"]
            if b["kind"] == "fortify_attribute":
                assert b["param"] not in _FORBIDDEN_ATTR, f"{fid} 祭壇不得強化力量(逸出 sim 包絡)"
            elif b["kind"] == "fortify_skill":
                assert b["param"] not in _FORBIDDEN_SKILL, f"{fid} 祭壇不得強化武器/潛行技能"
            assert b["magnitude"] <= _BUFF_CAP[b["kind"]], f"{fid} magnitude 超單瓶上界"


# --- 3. generate 佈格(opt-in·對照組永不生成)-----------------------------
def _spec(dungeon_id):
    import json
    return json.load(open("tesrpg/data/dungeons.json"))[dungeon_id]


def test_generate_places_feature():
    found = False
    for seed in range(20):
        g = dungeoncrawl.generate(_spec("ashfall_barrow"), gd, RNG(seed))
        for z in range(g["m"]):
            reach = dungeoncrawl.reachable_cells(g, z)
            assert len(reach) == g["n"] * g["n"]            # FEATURE 是開放格 → 仍全連通
            assert g["layers"][z][0][0]["type"] == dungeoncrawl.ENTRANCE if z == 0 else True
            for row in g["layers"][z]:
                for cell in row:
                    if cell["type"] == dungeoncrawl.FEATURE:
                        found = True
                        assert cell["feature"] in gd.dungeon_features
    assert found, "features 地城應生成 FEATURE 格"


def test_control_dungeon_never_gets_feature():
    for seed in range(20):
        g = dungeoncrawl.generate(_spec("cedernoc_cave"), gd, RNG(seed))   # 無 features 宣告
        for z in range(g["m"]):
            for row in g["layers"][z]:
                for cell in row:
                    assert cell["type"] != dungeoncrawl.FEATURE, "無 features 地城永不生成 FEATURE(byte-identical 保護)"


# --- 4. resolve 煙霧(三 kind)---------------------------------------------
def test_resolve_lore_pure_message():
    c, st = _p()
    saved = _silence()
    try:
        before = c.to_dict()
        main._resolve_feature(st, gd, "lore_soul_weave")   # 純敘事
        assert c.to_dict() == before                        # 狀態不變
    finally:
        _restore(saved)


def test_resolve_shrine_grants_safe_buff_and_risk():
    saved = _silence()
    try:
        # patch menu → 選第一個 offer(drink=耐力+傷害)
        om = main.ui.menu
        main.ui.menu = lambda title, opts, **k: opts[0][0]
        c, st = _p()
        hp0 = c.health
        main._resolve_feature(st, gd, "shrine_endurance_font")
        assert any(b["param"] == "endurance" for b in c.potion_buffs)   # 安全池增益入 potion_buffs
        assert c.health < hp0 and c.health >= 0                          # damage 風險扣血不為負
        # 選第二個 offer(attune=恢復+curse)
        main.ui.menu = lambda title, opts, **k: opts[1][0]
        c2, st2 = _p()
        main._resolve_feature(st2, gd, "shrine_endurance_font")
        assert getattr(c2, "_dungeon_curse", {}).get("alteration", 0) < 0   # curse 寫暫態負層
        # 返回(None)→ 無任何變更
        main.ui.menu = lambda title, opts, **k: None
        c3, st3 = _p()
        before = c3.to_dict()
        main._resolve_feature(st3, gd, "shrine_endurance_font")
        assert c3.to_dict() == before and not getattr(c3, "_dungeon_curse", {})
    finally:
        main.ui.menu = om
        _restore(saved)


def test_resolve_puzzle_success_and_fail():
    saved = _silence()
    try:
        # 成功:patch rng.chance → True
        c, st = _p()
        st.rng.chance = lambda p: True
        gold0 = c.gold
        main._resolve_feature(st, gd, "puzzle_rusted_mechanism")
        assert c.gold >= gold0                              # 獎勵(金幣/物品)入袋
        assert c.skill_xp.get("security", 0) > 0            # 成功練 security(full xp)
        # 失敗:patch → False
        c2, st2 = _p()
        st2.rng.chance = lambda p: False
        st2.rng.randint = lambda a, b: b
        hp0 = c2.health
        main._resolve_feature(st2, gd, "puzzle_rusted_mechanism")
        assert c2.health < hp0                              # penalty 扣血
    finally:
        _restore(saved)


# --- 5. 零新存檔欄 ---------------------------------------------------------
def test_no_new_save_field():
    saved = _silence()
    try:
        om = main.ui.menu
        main.ui.menu = lambda title, opts, **k: opts[1][0]   # 選 curse offer(寫 _dungeon_curse)
        c, st = _p()
        keys_before = set(c.to_dict().keys())
        main._resolve_feature(st, gd, "shrine_endurance_font")
        assert set(c.to_dict().keys()) == keys_before        # _dungeon_curse 不入 to_dict
    finally:
        main.ui.menu = om
        _restore(saved)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
