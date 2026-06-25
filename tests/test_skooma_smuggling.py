"""R-smuggle:盜賊公會斯庫瑪走私生意(月糖精煉 sink + 走私委託 + 反印鈔機 + rank/省份閘)。

整併三層犯罪內容:斯庫瑪走私 = 盜賊公會高階解鎖的招牌生意線(只在艾爾斯維爾分舵)。
🔴 反印鈔機鐵則:精煉是嚴格 sink(N×月糖售價 ≥ 斯庫瑪售價)→ 精煉/買進再賣恆虧;利潤只走固定報酬走私委託。
"""

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.state import GameState, GameTime
from tesrpg.systems import alchemy, factions, inventory, quests, world, worldpulse

_SCOMM = ["scomm_bravil", "scomm_riften", "scomm_wayrest", "scomm_balmora"]


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="khajiit", birthsign="thief", class_id="thief")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime())


# ---------------------------------------------------------------- 反印鈔機 / 精煉 sink
def test_refine_value_invariant_no_faucet():
    """🔴 核心反印鈔機:N×月糖價值 ≥ 斯庫瑪價值 → 精煉產出的可售價值恆 ≤ 投入月糖,
    且買賣價對兩物同乘 (0.3+0.5d)(1+sell_bonus) → 此不等式在任何議價/銷贓階皆成立(即使月糖免費撿)。"""
    gd, _ = _state()
    ms_v = gd.item("moon_sugar")["value"]
    sk_v = gd.item("skooma")["value"]
    assert alchemy.SKOOMA_REFINE_COST * ms_v >= sk_v, \
        f"精煉成印鈔機:{alchemy.SKOOMA_REFINE_COST}×{ms_v}={alchemy.SKOOMA_REFINE_COST*ms_v} < skooma {sk_v}"


def test_refine_no_arbitrage_at_max_generosity():
    """具體售價斷言:即使滿階盜賊(sell_bonus 上限)+ 各議價檔,賣 N 月糖 ≥ 賣 1 斯庫瑪 → 精煉再賣恆虧;
    且斯庫瑪買價 > 賣價(既有反套利地板),買進再賣也虧。"""
    gd, st = _state()
    c = st.player
    c.factions["thieves_guild"] = len(gd.factions["thieves_guild"]["ranks"]) - 1   # 滿階 → sell_bonus 上限
    for merc in (0, 50, 100):                                                       # 掃低/中/高議價
        c.skills["mercantile"] = merc
        sell_ms = world.sell_price(c, gd, "moon_sugar")
        sell_sk = world.sell_price(c, gd, "skooma")
        assert alchemy.SKOOMA_REFINE_COST * sell_ms >= sell_sk, \
            f"merc={merc}: {alchemy.SKOOMA_REFINE_COST}×{sell_ms} < {sell_sk}(精煉再賣套利)"
        assert world.buy_price(c, gd, "skooma") > sell_sk         # 買進再賣恆虧(既有地板)


def test_refine_skooma_consumes_and_trains():
    gd, st = _state()
    c = st.player
    c.skills["alchemy"] = alchemy.SKOOMA_REFINE_SKILL
    inventory.add_item(c, "moon_sugar", alchemy.SKOOMA_REFINE_COST)
    res = alchemy.refine_skooma(c, gd)
    assert res["ok"]
    assert inventory.count_item(c, "moon_sugar") == 0            # N 份月糖被吃掉
    assert inventory.count_item(c, "skooma") == 1                # 產 1 瓶斯庫瑪
    assert res["skill_events"] is not None                        # 練了煉金(use_skill 回事件)


def test_refine_skooma_gated_by_sugar_and_skill():
    gd, st = _state()
    c = st.player
    # 月糖不足 → 失敗、零消耗
    c.skills["alchemy"] = alchemy.SKOOMA_REFINE_SKILL
    inventory.add_item(c, "moon_sugar", alchemy.SKOOMA_REFINE_COST - 1)
    res = alchemy.refine_skooma(c, gd)
    assert not res["ok"] and res["hours"] == 0
    assert inventory.count_item(c, "moon_sugar") == alchemy.SKOOMA_REFINE_COST - 1   # 未扣料
    assert inventory.count_item(c, "skooma") == 0
    # 煉金不足 → 失敗、零消耗
    c.skills["alchemy"] = alchemy.SKOOMA_REFINE_SKILL - 1
    inventory.add_item(c, "moon_sugar", 1)                        # 補足數量,只差技能
    res = alchemy.refine_skooma(c, gd)
    assert not res["ok"]
    assert inventory.count_item(c, "skooma") == 0


# ---------------------------------------------------------------- rank / 省份閘(走私生意子選單)
def _capture_guild_opts(gd, st, faction_id):
    """驅動 action_guild_hall,擷取選單選項 key(ui.menu 回 None 即返回)。"""
    captured = []
    om, og, omsg = main.ui.menu, main.ui.guild_panel, main.ui.message
    main.ui.menu = lambda title, opts, **k: captured.extend(o[0] for o in opts) or None
    main.ui.guild_panel = lambda *a, **k: None
    main.ui.message = lambda *a, **k: None
    try:
        main.action_guild_hall(st, gd, faction_id)
    finally:
        main.ui.menu, main.ui.guild_panel, main.ui.message = om, og, omsg
    return captured


def test_smuggle_submenu_rank_and_province_gate():
    gd, st = _state(location_id="senchal")                        # 森查爾 = 艾爾斯維爾 TG 分舵
    c = st.player
    # 高階盜賊 @ 艾爾斯維爾 → 走私生意現身
    c.factions["thieves_guild"] = main.SMUGGLE_RANK_1
    assert "smuggle" in _capture_guild_opts(gd, st, "thieves_guild")
    # 未達階 → 不現
    c.factions["thieves_guild"] = main.SMUGGLE_RANK_1 - 1
    assert "smuggle" not in _capture_guild_opts(gd, st, "thieves_guild")
    # 達階但不在艾爾斯維爾(布魯瑪=賽羅迪爾 TG 總部)→ 不現(只在月糖源經營)
    c.factions["thieves_guild"] = main.SMUGGLE_RANK_1
    c.location_id = "bruma"
    assert "smuggle" not in _capture_guild_opts(gd, st, "thieves_guild")


# ---------------------------------------------------------------- scomm_ schema + 聚光
def test_scomm_schema_repeatable_collect_reach_infamy():
    gd, _ = _state()
    for qid in _SCOMM:
        q = gd.quests[qid]
        assert q["repeatable"] and q["source"] == "board"
        assert set(q["reward"]) <= {"gold", "infamy"}            # 走私=惡名,不給聲望/物品(反 min-max)
        stages = q["stages"]
        assert stages[0]["objective"] == {"type": "collect", "item": "moon_sugar", "count": stages[0]["objective"]["count"]}
        assert stages[1]["objective"]["type"] == "reach"
        dest = stages[1]["objective"]["location"]
        assert dest in gd.world["locations"]                      # 送達地真實存在
        assert gd.world["locations"][dest]["province"] != "艾爾斯維爾"   # 走私=運「出」貓人故土
        assert q.get("provinces") == ["艾爾斯維爾"]               # 在艾爾斯維爾接貨


def test_scomm_in_smuggle_pulse_spotlight():
    gd, _ = _state()
    spot = gd.world_pulse["pulse_elsweyr_smuggle"]["spotlight_quests"]
    assert gd.world_pulse["pulse_elsweyr_smuggle"]["province"] == "艾爾斯維爾"
    assert set(_SCOMM) == set(spot)                               # 走私脈動聚光全部 scomm_


# ---------------------------------------------------------------- 走私委託:聚光 + rank 過濾
def _capture_contract_opts(gd, st):
    captured = []
    om, omsg = main.ui.menu, main.ui.message
    main.ui.menu = lambda title, opts, **k: captured.extend(o[0] for o in opts) or None
    main.ui.message = lambda *a, **k: None
    try:
        main._smuggling_contracts(st, gd)
    finally:
        main.ui.menu, main.ui.message = om, omsg
    return captured


def test_smuggling_contracts_pulse_gated_and_rank_filtered():
    gd, st = _state(location_id="senchal")
    c = st.player
    today = worldpulse.day_index(st)
    # 脈動未開 → 無委託
    assert _capture_contract_opts(gd, st) == []
    # 開走私脈動窗
    c.world_pulse_day["pulse_elsweyr_smuggle"] = today
    # 低階(SMUGGLE_RANK_1):只見近程委託,長程(riften/wayrest)被 rank 擋
    c.factions["thieves_guild"] = main.SMUGGLE_RANK_1
    low = _capture_contract_opts(gd, st)
    assert "scomm_bravil" in low and "scomm_balmora" in low
    assert "scomm_riften" not in low and "scomm_wayrest" not in low
    # 高階(SMUGGLE_RANK_2):長程大宗解鎖
    c.factions["thieves_guild"] = main.SMUGGLE_RANK_2
    high = _capture_contract_opts(gd, st)
    assert {"scomm_riften", "scomm_wayrest"} <= set(high)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_skooma_smuggling")
