"""R89 戰士/法師公會功能化 —— rank-gated 招牌動詞(承 R88·複用 action_guild_hall 服務模式)。

戰士=軍械庫淬鍊(公會供料·免材料·受 temper cap 夾)、法師=奧術回充(免靈魂石)+ 法力補給(有上限)。
🔴 byte-safe:smithing.temper(guild_free=False) 預設行為不變;不碰 combat/formulas。
"""

from tesrpg import main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.state import GameState, GameTime
from tesrpg.systems import enchanting, factions, inventory, smithing
from tesrpg.synth import enchant_weapon_status_id


def _state(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.location_id = "imperial_city"          # 任一真實城(forge_ok 不看 province·只需 current_location 合法)
    c.skills["smithing"] = 40                # 確保 effective_temper_cap >= 1
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime())


def _capture_guild_opts(gd, st, faction_id):
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


# ---------------------------------------------------------------- 戰士:軍械庫淬鍊
def test_forge_rank_gate():
    gd, st = _state()
    c = st.player
    c.factions["fighters_guild"] = main.FORGE_RANK
    assert "forge" in _capture_guild_opts(gd, st, "fighters_guild")
    c.factions["fighters_guild"] = main.FORGE_RANK - 1
    assert "forge" not in _capture_guild_opts(gd, st, "fighters_guild")


def test_guild_free_temper_skips_ingot():
    gd, st = _state()
    c = st.player
    assert inventory.count_item(c, "iron_ingot") == 0          # 無錠
    res = smithing.temper(c, gd, "iron_sword", guild_free=True)
    assert res["ok"] and res["free"]
    assert c.weapon_temper.get("iron_sword") == 1              # 淬鍊 +1
    assert inventory.count_item(c, "iron_ingot") == 0          # 公會供料·未耗錠


def test_normal_temper_still_requires_and_consumes_ingot():
    """🔴 byte-safe:guild_free 預設 False → 既有行為(缺錠擋下·有錠則消耗)逐字不變。"""
    gd, st = _state()
    c = st.player
    res = smithing.temper(c, gd, "iron_sword")                 # 無錠 → 擋下
    assert not res["ok"] and "缺少" in res["message"]
    assert c.weapon_temper.get("iron_sword", 0) == 0
    inventory.add_item(c, "iron_ingot", 1)
    res = smithing.temper(c, gd, "iron_sword")                 # 有錠 → 成功並消耗
    assert res["ok"] and not res["free"]
    assert inventory.count_item(c, "iron_ingot") == 0


def test_guild_temper_bounded_by_cap():
    """軍械庫供料但仍受 effective_temper_cap 夾(無無限迴圈·非印鈔機)。"""
    gd, st = _state()
    c = st.player
    cap = smithing.effective_temper_cap(c, gd)
    for _ in range(cap):
        assert smithing.temper(c, gd, "iron_sword", guild_free=True)["ok"]
    over = smithing.temper(c, gd, "iron_sword", guild_free=True)   # 超 cap → 擋下
    assert not over["ok"]
    assert c.weapon_temper["iron_sword"] == cap


# ---------------------------------------------------------------- 法師:奧術回充 + 法力補給
def test_arcane_rank_gate():
    gd, st = _state(race="high_elf", birthsign="mage", class_id="mage")
    c = st.player
    c.factions["mages_guild"] = main.ARCANE_RECHARGE_RANK
    assert "arcane_svc" in _capture_guild_opts(gd, st, "mages_guild")
    c.factions["mages_guild"] = main.ARCANE_RECHARGE_RANK - 1
    assert "arcane_svc" not in _capture_guild_opts(gd, st, "mages_guild")


def test_recharge_full_refills_charge_weapon_only():
    gd, st = _state()
    c = st.player
    wid = enchant_weapon_status_id("steel_sword", "soul_trap", 10, 1)   # 充能型(容量 10)
    inventory.add_item(c, wid, 1)
    cap = enchanting.charge_capacity(gd, wid)
    c.enchant_charges[wid] = 3                                  # 已耗至 3
    assert enchanting.recharge_full(c, gd, wid) is True         # 回充至滿
    assert c.enchant_charges[wid] == cap
    assert enchanting.recharge_full(c, gd, wid) is False        # 已滿 → 無變
    # 非充能武器不被視為可回充
    inventory.add_item(c, "iron_sword", 1)
    assert "iron_sword" not in enchanting.chargeable_weapons(c, gd)


def test_magicka_supply_bounded():
    """法力補給:補滿至 N 後不再增加(有上限·非無限);rank>=ARCANE_SUPPLY_RANK 才出現。"""
    gd, st = _state(race="high_elf", birthsign="mage", class_id="mage")
    c = st.player
    c.factions["mages_guild"] = main.ARCANE_SUPPLY_RANK
    # 驅動 _arcane_services 選一次「supply」再返回
    seq = iter(["supply", None])
    om, omsg = main.ui.menu, main.ui.message
    main.ui.menu = lambda title, opts, **k: next(seq, None)
    main.ui.message = lambda *a, **k: None
    try:
        main._arcane_services(st, gd)
    finally:
        main.ui.menu, main.ui.message = om, omsg
    assert inventory.count_item(c, "minor_magicka_potion") == main.MAGE_POTION_SUPPLY_N
    # 再補一次不超過上限
    seq2 = iter(["supply", None])
    main.ui.menu = lambda title, opts, **k: next(seq2, None)
    main.ui.message = lambda *a, **k: None
    try:
        main._arcane_services(st, gd)
    finally:
        main.ui.menu, main.ui.message = om, omsg
    assert inventory.count_item(c, "minor_magicka_potion") == main.MAGE_POTION_SUPPLY_N


def test_supply_gated_below_supply_rank():
    gd, st = _state(race="high_elf", birthsign="mage", class_id="mage")
    c = st.player
    c.factions["mages_guild"] = main.ARCANE_SUPPLY_RANK - 1     # 有 recharge 無 supply
    captured = []
    om = main.ui.menu
    main.ui.menu = lambda title, opts, **k: captured.extend(o[0] for o in opts) or None
    try:
        main._arcane_services(st, gd)
    finally:
        main.ui.menu = om
    assert "recharge" in captured and "supply" not in captured


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_guild_services")
