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


def _tier_of(gd, pool_id, iid):
    pool = gd.ecology["pools"][pool_id]
    for tier in ("common", "uncommon", "rare"):
        if iid in pool.get(tier, []):
            return tier
    return None


def _spent(gd, pool_id, picks):
    return sum(events._FORAGE_TIER_COST[_tier_of(gd, pool_id, i)] * q for i, q in picks)


# --- 定值預算:總成本不超過最大可能預算(R94)-----------------------------
def test_forage_respects_budget():
    gd = get_gamedata()
    for scout in (0, 25, 50, 100, 200):
        _, c = _char(scout=scout)
        scout_eff = int(c.skill("scout"))
        max_budget = (events._FORAGE_BASE_BUDGET + scout_eff // events._FORAGE_BUDGET_PER_SCOUT
                      + events._FORAGE_BUDGET_JITTER)   # jitter 最大值
        for seed in range(60):
            picks = events.forage_pool_draw(c, gd, "snow", RNG(seed))
            assert _spent(gd, "snow", picks) <= max_budget
            for i, q in picks:                      # 單品上限
                assert q <= events._FORAGE_MAX_QTY_PER_ITEM


# --- scout 成長同時放大「數量」與「稀有度」(R94 核心語意)-----------------
def test_higher_scout_yields_more_and_rarer():
    gd = get_gamedata()
    def sample(scout, n=400):
        _, c = _char(scout=scout)
        items = rares = 0
        for s in range(n):
            picks = events.forage_pool_draw(c, gd, "snow", RNG(s))
            items += sum(q for _, q in picks)
            rares += sum(q for i, q in picks if _tier_of(gd, "snow", i) == "rare")
        return items, rares
    lo_items, lo_rare = sample(0)
    hi_items, hi_rare = sample(160)
    assert hi_items > lo_items          # 偵查高 → 件數更多
    assert hi_rare > lo_rare            # 偵查高 → 稀有件數更多


# --- 浮動制:低偵查仍有「非常小機會」採到 rare(但確實很小)----------------
def test_low_scout_rare_is_small_but_possible():
    gd = get_gamedata()
    _, c = _char(scout=0)
    n = 1000
    got_rare = sum(
        1 for s in range(n)
        if any(_tier_of(gd, "snow", i) == "rare" for i, _ in events.forage_pool_draw(c, gd, "snow", RNG(s)))
    )
    frac = got_rare / n
    assert 0 < frac < 0.10, f"低偵查 rare 機率應「小而非零」,實得 {frac:.1%}"


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


# --- 每種材料皆可取得:入某生態池 或 有非野採來源(怪掉落/商店)------------
# daedra_heart 等「打稀有怪才得」的材料刻意 loot-only(不入野採池);其餘野採材料須入池。
def test_every_ingredient_is_reachable():
    gd = get_gamedata()
    pooled = _all_pool_members(gd)
    loot = set()
    for c in gd.bestiary.values():
        for e in (c.get("loot") or []):
            iid = e if isinstance(e, str) else (e.get("item") or e.get("id"))
            loot.add(iid)
    shop = set()
    for loc in gd.world["locations"].values():
        shop.update(loc.get("merchant_stock") or [])
    unreachable = set(gd.ingredients) - pooled - loot - shop
    assert not unreachable, f"無任何取得途徑的材料(非野採/非掉落/非商店):{sorted(unreachable)}"


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
