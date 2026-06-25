"""野採生態系材料池 隨機抽取(R93)回歸測試。

涵蓋:採集動作/物品/數量解耦(forage_pool 從生態系池加權隨機抽任意組合+數量)、
決定性(同 seed 同結果)、總量上限、scout(偵查)技能成長放大產出、
全材料皆入某池(野外可採)、全 forage_pool 引用的 pool id 皆存在、
以及 apply_effects 整合(真的進背包 + 練偵查/煉金)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import events


def _char(scout=0):
    gd = get_gamedata()
    c = build_character(gd, name="採", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    c.skills["scout"] = scout
    return gd, c


def _all_pool_members(gd):
    out = set()
    for pool in gd.ecology["pools"].values():
        for members in pool.values():
            if isinstance(members, list):
                out.update(members)
    return out


# --- 決定性:同 seed 同結果 -------------------------------------------------
def test_forage_draw_is_deterministic():
    gd, c = _char(scout=60)
    a = events.forage_pool_draw(c, gd, "snow", RNG(7))
    b = events.forage_pool_draw(c, gd, "snow", RNG(7))
    assert a == b
    # 不同 seed 應大致不同(極小機率相同,挑兩個明顯不同的)
    assert events.forage_pool_draw(c, gd, "snow", RNG(7)) != \
        events.forage_pool_draw(c, gd, "snow", RNG(9999))


# --- 總量上限:任何 scout 都不超過 cap 公式 --------------------------------
def test_forage_respects_cap():
    gd = get_gamedata()
    for scout in (0, 25, 50, 100, 200):
        _, c = _char(scout=scout)
        scout_eff = int(c.skill("scout"))   # helper 讀有效偵查;cap 須以同一值算
        cap = events._FORAGE_BASE_CAP + scout_eff // events._FORAGE_CAP_PER_SCOUT
        for seed in range(40):
            picks = events.forage_pool_draw(c, gd, "snow", RNG(seed))
            assert sum(q for _, q in picks) <= cap


# --- scout 成長放大採集產出 ------------------------------------------------
def test_higher_scout_yields_more():
    gd = get_gamedata()
    _, low = _char(scout=0)
    _, high = _char(scout=160)
    lo = sum(sum(q for _, q in events.forage_pool_draw(low, gd, "snow", RNG(s)))
             for s in range(60))
    hi = sum(sum(q for _, q in events.forage_pool_draw(high, gd, "snow", RNG(s)))
             for s in range(60))
    assert hi > lo


# --- 至少抽到一樣(基礎抽取次數 ≥1)----------------------------------------
def test_forage_always_yields_something():
    gd, c = _char(scout=0)
    for pool_id in gd.ecology["pools"]:
        for seed in range(20):
            assert events.forage_pool_draw(c, gd, pool_id, RNG(seed))


# --- 空/未知池 安全回空 ----------------------------------------------------
def test_unknown_pool_returns_empty():
    gd, c = _char()
    assert events.forage_pool_draw(c, gd, "nonexistent_biome", RNG(1)) == []


# --- 池成員皆合法材料 id ---------------------------------------------------
def test_pool_members_are_valid_ingredients():
    gd = get_gamedata()
    ings = set(gd.ingredients)
    bad = _all_pool_members(gd) - ings
    assert not bad, f"生態池含非材料 id:{sorted(bad)}"


# --- 每種材料都入某池(野外可採;補商店/掉落限定材料入野採)-----------------
def test_every_ingredient_is_in_some_pool():
    gd = get_gamedata()
    missing = set(gd.ingredients) - _all_pool_members(gd)
    assert not missing, f"無任何生態池可野採的材料:{sorted(missing)}"


# --- 每個 forage_pool 引用的 pool id 皆存在(防孤兒)----------------------
def test_forage_pool_ids_resolve():
    gd = get_gamedata()
    pools = set(gd.ecology["pools"])
    used = set()
    for ev in gd.events.values():
        for opt in ev.get("options", []):
            for ef in opt.get("effects", []) or []:
                if ef.get("type") == "forage_pool":
                    used.add(ef["pool"])
    assert used, "沒有任何事件使用 forage_pool(轉換失敗?)"
    assert used <= pools, f"forage_pool 引用了不存在的 pool:{sorted(used - pools)}"


# --- 整合:apply_effects 真的進背包 + 練偵查/煉金 -------------------------
def test_apply_forage_pool_adds_items_and_trains_skills():
    gd, c = _char(scout=30)
    before_scout = c.skill_xp.get("scout", 0.0)
    before_alch = c.skill_xp.get("alchemy", 0.0)
    inv_before = sum(s["qty"] for s in c.inventory)
    st = GameState(player=c, time=GameTime(), rng=RNG(3))
    res = events.apply_effects(st, gd, [{"type": "forage_pool", "pool": "ashland"}], st.rng)
    assert sum(s["qty"] for s in c.inventory) > inv_before          # 確實採到材料進背包
    assert any("採得" in m for m in res["messages"])
    assert c.skill_xp.get("scout", 0.0) > before_scout              # learn-by-doing:練偵查
    assert c.skill_xp.get("alchemy", 0.0) > before_alch             # 練煉金


def test_empty_forage_grants_nothing_and_no_xp():
    # 空/未知池:不採到材料時不練技能(R93 審查 nit 修正:空手不長偵查/煉金)
    gd, c = _char(scout=20)
    before = (c.skill_xp.get("scout", 0.0), c.skill_xp.get("alchemy", 0.0))
    inv_before = sum(s["qty"] for s in c.inventory)
    st = GameState(player=c, time=GameTime(), rng=RNG(1))
    res = events.apply_effects(st, gd, [{"type": "forage_pool", "pool": "no_such_biome"}], st.rng)
    assert sum(s["qty"] for s in c.inventory) == inv_before
    assert (c.skill_xp.get("scout", 0.0), c.skill_xp.get("alchemy", 0.0)) == before
    assert any("沒有可採" in m for m in res["messages"])


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_foraging")
