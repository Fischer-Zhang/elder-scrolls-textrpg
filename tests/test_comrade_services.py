"""R98 犯罪公會服務層(承 R97)回歸測試。

涵蓋:① 可見性閘(已揭露犯罪同志才見服務·未揭露/非會員/公開公會同志不見·跨公會不洩漏);
② 防套利(_MYTHIC_SUPPLY 買价恆 > 銷价·跨惡名階)+ loot-only 紅線排除 + 全 id 存在;
③ DB 接私活複用既有合約池(無新 source/無雙重獎勵);④ 掩護保全(揭露只疊加既有話題);
⑤ 整合煙霧(禁術貨源買入·接私活領受走既有 _accept_and_brief)。

🔴 不碰 combat/formulas → sim byte-identical;零新存檔欄(閘=char.factions + R97 衍生揭露)。
"""

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import brotherhood, crime, dialogue, factions, quests, world


def _char(**factions_in):
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = dict(factions_in)
    return gd, c


def _state(c):
    return GameState(player=c, time=GameTime(), rng=RNG(1))


def _topic_ids(c, gd, nid):
    st = _state(c)
    ctx = dialogue.talk_ctx(st, gd, nid)
    att = dialogue.attitude(c, st, gd, nid, ctx)
    return att, [t["id"] for t in dialogue.topics_for(c, st, gd, nid, ctx, att)]


# 三犯罪公會各取一名 R97 隱蔽身分 NPC(資料驅動,避免硬寫單一 id 失效)
def _secret_npc(gd, guild):
    return next(n for n in gd.npcs if gd.npcs[n].get("secret_guild") == guild)


_SERVICE_TOPIC = {"thieves_guild": "crime_fence",
                  "dark_brotherhood": "crime_contract",
                  "mythic_dawn": "crime_supply"}


# ---------------------------------------------------------------- 可見性閘
def test_revealed_comrade_sees_own_service():
    """揭露的犯罪同志(同會自知)→ comrade + 對應服務話題。"""
    for guild, topic in _SERVICE_TOPIC.items():
        gd, c = _char(**{guild: 3})
        nid = _secret_npc(gd, guild)
        att, ids = _topic_ids(c, gd, nid)
        assert att == "comrade", f"{guild}: 同會自知應 comrade,得 {att}"
        assert topic in ids, f"{guild}: 應見服務 {topic},得 {ids}"


def test_nonmember_sees_no_service():
    """非會員 → 隱蔽身分未揭露 → 無任何犯罪服務。"""
    for guild, topic in _SERVICE_TOPIC.items():
        gd, c = _char()                      # 無任何會籍
        nid = _secret_npc(gd, guild)
        att, ids = _topic_ids(c, gd, nid)
        assert not dialogue.secret_guild_revealed(c, gd, nid)
        assert topic not in ids, f"{guild}: 非會員不應見 {topic}"


def test_revealed_by_investigation_still_gated_to_members():
    """調查揭露(非會員,_GUILD_KNOWN 標記)→ 身分已揭露但你非秘密同會 → 仍不得服務。
    (服務閘是 is_member,不只是『揭露』→ 知道對方是賊 ≠ 能用賊的門路。)"""
    for guild, topic in _SERVICE_TOPIC.items():
        gd, c = _char()
        nid = _secret_npc(gd, guild)
        c.dialogue_done.setdefault(nid, []).append(dialogue._GUILD_KNOWN)
        assert dialogue.secret_guild_revealed(c, gd, nid)     # 已揭露
        att, ids = _topic_ids(c, gd, nid)
        assert att != "comrade"                                # 非同會 → 非 comrade
        assert topic not in ids, f"{guild}: 揭露但非會員不應見 {topic}"


def test_cross_guild_no_leak():
    """多犯罪會籍玩家在某犯罪同志處,只見『該 NPC 公會』的服務(不洩漏他會服務)。"""
    gd, c = _char(thieves_guild=3, mythic_dawn=2, dark_brotherhood=2)
    nid = _secret_npc(gd, "thieves_guild")
    att, ids = _topic_ids(c, gd, nid)
    assert "crime_fence" in ids
    assert "crime_supply" not in ids and "crime_contract" not in ids, \
        f"跨公會洩漏:盜賊同志處不應見他會服務,得 {ids}"


def test_public_guild_comrade_no_crime_service():
    """公開公會同會相認(secret_guild=None)→ comrade,但無犯罪服務(secret_comrade 閘擋)。"""
    gd = get_gamedata()
    nid = next(n for n in gd.npcs
               if gd.npcs[n].get("guild") and not gd.npcs[n].get("secret_guild"))
    g = gd.npcs[nid]["guild"]
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.factions = {g: 3}
    att, ids = _topic_ids(c, gd, nid)
    assert att == "comrade"                                    # 公開同會相認
    assert not any(i.startswith("crime_") for i in ids), \
        f"公開公會同志不應見犯罪服務,得 {ids}"


# ---------------------------------------------------------------- 防套利 / 紅線
def test_mythic_supply_ids_exist_and_not_loot_only():
    gd = get_gamedata()
    assert main._MYTHIC_SUPPLY, "供貨清單不可空"
    for iid in main._MYTHIC_SUPPLY:
        assert gd.item_or_none(iid) is not None, f"供貨 id {iid} 不存在"
    assert not (set(main._MYTHIC_SUPPLY) & world._LOOT_ONLY_MATERIALS), \
        "供貨清單不得含 loot-only 紅線物(daedra_heart/dragon_scale)"


def test_mythic_supply_buy_exceeds_sell_all_tiers():
    """買价恆 > 銷价 → 買回再賣恆虧,杜絕無限刷錢(跨惡名階 + 盜賊議價 sell_bonus 確認地板)。"""
    for tg in (0, 5):                         # 0=無盜賊議價;5=滿階 sell_bonus(覆審查點名缺口)
        gd, c = _char(**({"thieves_guild": tg} if tg else {}))
        for infamy in (0, 10, 50, 200):       # 拉高惡名 → outlaw_standing 各階
            c.infamy = infamy
            for iid in main._MYTHIC_SUPPLY:
                b, s = world.buy_price(c, gd, iid), world.sell_price(c, gd, iid)
                assert b > s, f"盜賊階 {tg}·惡名 {infamy} 供貨 {iid}:買 {b} 須 > 銷 {s}"


def test_no_cross_service_arbitrage_supply_to_fence():
    """🔴 跨服務反套利:身兼盜賊(便攜 fence·加價銷贓)+ 神話黎明(禁術貨源)的玩家,
    自貨源買入再到 fence 銷贓不得獲利。最壞情境=最高惡名(fence_bonus 0.45)+ 滿盜賊議價;
    供貨買价(含商人加成 ~數倍)恆 > fence 加價銷价 → 永無正 EV(零金幣泵)。"""
    gd, c = _char(thieves_guild=5)            # 盜賊+神話黎明非宿敵 → 雙會籍可行
    c.factions["mythic_dawn"] = 2
    c.infamy = 9999                           # outlaw_standing 頂階 → fence_bonus 0.45
    bonus = crime.fence_bonus(c)
    for iid in main._MYTHIC_SUPPLY:
        buy = world.buy_price(c, gd, iid)                      # 自貨源買入(付出)
        fence_sell = int(world.sell_price(c, gd, iid) * (1 + bonus))   # fence 加價銷出(收入)
        assert buy > fence_sell, f"跨服務套利:{iid} 買 {buy} ≤ fence銷 {fence_sell}(fence_bonus {bonus})"


# ---------------------------------------------------------------- DB 複用(無新 source)
def test_db_contract_reuses_guild_pool_no_new_source():
    """接私活複用既有 source='guild' 的 DB 合約池;不得新增 source='comrade' 之類雙重獎勵來源。"""
    gd, c = _char(dark_brotherhood=2)
    pool = quests.available_quests(c, gd, "guild", brotherhood.FACTION)
    assert pool, "DB 公會合約池應非空(複用之)"
    assert all(q.get("source") != "comrade" for q in gd.quests.values()), \
        "不應存在 source='comrade' 任務(避免另開雙重獎勵管線)"


# ---------------------------------------------------------------- 掩護保全(R96/R97)
def test_reveal_only_adds_keeps_cover_topics():
    """揭露只疊加:成為犯罪同志後,既有 comrade 話題(guild_intel/local_politics)仍在。"""
    gd, c = _char(thieves_guild=3)
    nid = _secret_npc(gd, "thieves_guild")
    _, ids = _topic_ids(c, gd, nid)
    assert "guild_intel" in ids and "crime_fence" in ids, \
        f"揭露應疊加服務而非抹除既有同道話題,得 {ids}"


# ---------------------------------------------------------------- 整合煙霧(patch ui.menu 驅動)
def _drive_menu(seq):
    """回傳一個依序吐出 seq 的 ui.menu 替身(用盡回 None)。"""
    it = iter(seq)
    return lambda title, opts, **k: next(it, None)


def test_comrade_supply_buys_item():
    gd, c = _char(mythic_dawn=2)
    c.gold = 9999
    iid = main._MYTHIC_SUPPLY[0]
    before_gold = c.gold
    om, omsg = main.ui.menu, main.ui.message
    main.ui.menu = _drive_menu([iid, None])           # 選首件 → 返回
    main.ui.message = lambda *a, **k: None
    try:
        main._comrade_supply(_state(c), gd)
    finally:
        main.ui.menu, main.ui.message = om, omsg
    from tesrpg.systems import inventory
    assert inventory.count_item(c, iid) >= 1, "應購入一件供貨"
    assert c.gold < before_gold, "金幣應減少(只出不進)"


def test_comrade_contract_accepts_from_db_pool():
    """接私活『接取新合約』→ 走既有 _accept_and_brief → 進 char.quests(同聖所合約)。"""
    gd, c = _char(dark_brotherhood=2)
    st = _state(c)
    avail = quests.available_quests(c, gd, "guild", brotherhood.FACTION)
    assert avail, "DB 公會合約池應非空"
    qid = avail[0]
    seq = ["accept"] + (["0"] if quests.branches(gd.quests[qid]) else []) + [None]
    before = set(c.quests)
    om, omsg = main.ui.menu, main.ui.message
    main.ui.menu = _drive_menu(seq)
    main.ui.message = lambda *a, **k: None
    try:
        res = main._comrade_contract(st, gd)
    finally:
        main.ui.menu, main.ui.message = om, omsg
    assert res is None
    added = set(c.quests) - before
    assert added, "接取後應有新 DB 合約進入 char.quests"
    assert all(gd.quests[q].get("source") == "guild" for q in added), "接取的應是公會合約池任務"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_comrade_services")
