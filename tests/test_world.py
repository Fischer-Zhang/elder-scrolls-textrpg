"""M3:背包/裝備/負重、世界圖、旅行、戰利品、地城、定價的測試。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, dungeon, inventory, loot, world


def _char():
    gd = get_gamedata()
    return gd, build_character(gd, name="A", sex="male", race="nord",
                               birthsign="warrior", class_id="warrior")


# --- 背包 / 裝備 / 負重 -------------------------------------------------
def test_starting_inventory():
    gd, c = _char()
    assert inventory.count_item(c, "minor_healing_potion") == 2
    assert c.location_id == gd.world["start_location"]
    # 起始武器同時在手上與背包
    assert c.weapon != "fists"
    assert inventory.count_item(c, c.weapon) == 1


def test_add_remove_and_weight():
    gd, c = _char()
    w0 = inventory.total_weight(c, gd)
    inventory.add_item(c, "iron_cuirass", 1)
    assert inventory.total_weight(c, gd) == w0 + gd.item("iron_cuirass")["weight"]
    assert inventory.remove_item(c, "iron_cuirass", 1)
    assert inventory.total_weight(c, gd) == w0
    assert not inventory.remove_item(c, "iron_cuirass", 1)  # 已無


def test_encumbrance_limit():
    gd, c = _char()
    assert inventory.max_weight(c) == formulas.max_encumbrance(c.attr("strength"))


def test_equip_armor_and_combat_rating():
    gd, c = _char()
    inventory.add_item(c, "iron_cuirass", 1)
    assert inventory.equip_armor(c, gd, "iron_cuirass")
    assert c.equipped["cuirass"] == "iron_cuirass"
    assert inventory.dominant_weight_class(c, gd) == "heavy"
    assert inventory.worn_armor_rating(c, gd) == gd.item("iron_cuirass")["armor_rating"]
    # 戰鬥用護甲值應採用穿戴護甲(高於無甲後備)
    assert combat._armor_rating(c, gd) > 0


def test_remove_equipped_unequips():
    gd, c = _char()
    inventory.add_item(c, "iron_helmet", 1)
    inventory.equip_armor(c, gd, "iron_helmet")
    inventory.remove_item(c, "iron_helmet", 1)
    assert "helmet" not in c.equipped


def test_use_healing_potion():
    gd, c = _char()
    c.health = 1
    msg = inventory.use_item(c, gd, "minor_healing_potion")
    assert msg and c.health == min(c.max_health, 1 + 25)
    assert inventory.count_item(c, "minor_healing_potion") == 1


# --- 世界圖 / 旅行 ------------------------------------------------------
def test_world_graph_bidirectional_and_valid():
    gd, _ = _char()
    locs = gd.world["locations"]
    assert gd.world["start_location"] in locs
    for lid, loc in locs.items():
        for dest in loc.get("links", {}):
            assert dest in locs, f"{lid} 連到不存在的 {dest}"
            assert lid in locs[dest].get("links", {}), f"{lid}->{dest} 非雙向"
        if loc["type"] == "dungeon":
            assert loc["dungeon"] in gd.dungeons


def test_world_graph_connected_and_has_loops():
    """世界是『有環的連通圖』,不是單線走廊:
    從起點 BFS 能到所有地點,且邊數 >= 點數(連通圖必含環路)。"""
    gd, _ = _char()
    locs = gd.world["locations"]
    start = gd.world["start_location"]

    seen = {start}
    frontier = [start]
    while frontier:
        cur = frontier.pop()
        for dest in locs[cur].get("links", {}):
            if dest not in seen:
                seen.add(dest)
                frontier.append(dest)
    assert seen == set(locs), f"圖不連通,孤立地點:{set(locs) - seen}"

    undirected = {frozenset((lid, dest))
                  for lid, loc in locs.items() for dest in loc.get("links", {})}
    assert len(undirected) >= len(locs), "邊數 < 點數 → 是樹/走廊,沒有環路"


def test_dungeons_are_through_routes_not_dead_ends():
    """地城捷徑:這些地城有 2 條以上連結(可穿越),不再是 degree-1 盲腸。"""
    gd, _ = _char()
    locs = gd.world["locations"]
    for did in ("cedernoc_cave", "frostwind_ruin", "ashfall_barrow"):
        assert len(locs[did].get("links", {})) >= 2, f"{did} 仍是死路"


def test_dungeon_enemies_and_loot_valid():
    """所有地城房間/首領的敵人 id 都存在於 bestiary(防新增內容打錯字)。"""
    gd, _ = _char()
    for did, dg in gd.dungeons.items():
        for room in dg.get("rooms", []):
            ids = room.get("enemies") or ([room["enemy"]] if room.get("enemy") else [])
            for tid in ids:
                assert tid in gd.bestiary, f"{did} 房間敵人 {tid} 不在 bestiary"
        boss = dg.get("boss", {})
        if boss.get("enemy"):
            assert boss["enemy"] in gd.bestiary, f"{did} 首領 {boss['enemy']} 不在 bestiary"


def test_every_settlement_has_a_ruler():
    """城戰前置:每座大城/城鎮都有合法的統治者(湮滅期各城自治);荒野/地城無城主。"""
    gd, _ = _char()
    for lid, loc in gd.world["locations"].items():
        ruler = gd.ruler_at(lid)
        if loc["type"] in ("city", "town"):
            assert ruler is not None, f"{lid} 缺統治者"
            assert ruler.get("name") and ruler.get("title"), f"{lid} 統治者缺名/銜"
            assert ruler.get("race") in gd.races, f"{lid} 統治者種族非法:{ruler.get('race')}"
            assert isinstance(ruler.get("garrison"), int) and ruler["garrison"] > 0
        else:
            assert ruler is None, f"{lid}（{loc['type']})不該有城主"
    # rulers.json 的每個 key 都對應真實地點(防打錯字)
    for lid in gd.rulers:
        assert lid in gd.world["locations"], f"rulers.json 的 {lid} 不是有效地點"


def test_travel_moves_and_advances_time():
    gd, c = _char()
    from tesrpg.state import GameTime
    t = GameTime()
    start = c.location_id
    dest, hours = world.travel_options(c, gd)[0]
    h0 = t.hour
    world.travel(c, gd, dest, t, RNG(5))
    assert c.location_id == dest
    # 時間有推進(可能跨日)
    assert (t.day, t.hour) != (1, h0) or hours == 0


def test_pricing_buy_more_than_sell():
    gd, c = _char()
    assert world.buy_price(c, gd, "iron_sword") > world.sell_price(c, gd, "iron_sword")
    # 交易技能越高,買價越低
    c.skills["mercantile"] = 100
    c.attributes["personality"] = 100
    assert world.buy_price(c, gd, "iron_sword") < gd.item("iron_sword")["value"] * 2.2


# --- 戰利品 / 地城 ------------------------------------------------------
def test_loot_resolver():
    rng = RNG(2)
    out = loot.resolve_loot(["iron_sword", {"gold": [5, 5]}, {"item": "ruby", "chance": 0.0}], rng)
    ids = [i for i, _ in out["items"]]
    assert "iron_sword" in ids and "ruby" not in ids and out["gold"] == 5


def test_creature_loot_into_inventory():
    gd, c = _char()
    rng = RNG(1)
    wolf = combat.spawn_creature(gd, "wolf", rng)
    res = combat.grant_loot(c, wolf, gd, rng)
    # 金幣入袋
    assert c.gold >= 50 + res["gold"]
    for iid, qty in res["items"]:
        assert inventory.count_item(c, iid) >= qty


def test_lockpick_chance_and_open():
    gd, c = _char()
    assert dungeon.pick_lock_chance(100, 10) > dungeon.pick_lock_chance(10, 100)
    c.skills["security"] = 100
    # 高技能撬低鎖,多試幾次必開
    opened = any(dungeon.pick_lock(c, gd, 5, RNG(i))["success"] for i in range(10))
    assert opened
    before = c.gold
    spoils = dungeon.open_container(c, gd, {"loot": [{"gold": [10, 10]}, "ruby"]}, RNG(0))
    assert c.gold == before + 10 and inventory.count_item(c, "ruby") == 1


def test_boss_is_tougher():
    gd, _ = _char()
    rng = RNG(0)
    normal = combat.spawn_creature(gd, "skeleton", rng)
    boss = combat.spawn_boss(gd, "skeleton", RNG(0), name="領主")
    assert boss.max_health > normal.max_health
    assert boss.attack["damage"] > normal.attack["damage"]
    assert boss.name == "領主"


def test_athletics_speeds_travel_and_trains():
    """運動越高旅行越快;旅行也會鍛鍊運動(補上原本的死技能)。"""
    from tesrpg.state import GameTime
    gd, slow = _char()
    route = [(d, h) for d, h in world.travel_options(slow, gd) if h >= 2]
    dest, base = route[0]
    slow.skills["athletics"] = 0
    gd2, fast = _char()
    fast.skills["athletics"] = 100
    r_slow = world.travel(slow, gd, dest, GameTime(), RNG(1))
    r_fast = world.travel(fast, gd2, dest, GameTime(), RNG(1))
    assert r_slow["hours"] == base                      # 運動 0 → 名目耗時
    assert r_fast["base_hours"] == base
    assert r_fast["hours"] < r_slow["hours"]            # 運動 100 → 更快
    # 旅行鍛鍊運動
    gd3, c3 = _char()
    c3.skills["athletics"] = 20
    x0 = c3.skill_xp.get("athletics", 0.0)
    world.travel(c3, gd3, dest, GameTime(), RNG(2))
    assert c3.skill_xp.get("athletics", 0.0) > x0


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_world OK")
