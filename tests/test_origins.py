"""開局背景(不一樣的人生)的單元測試。

覆蓋:預設開局 == 標準起始(向後相容基準)、每個開局產出合法角色、
開局只給「處境」不給「數值」、存檔往返、舊存檔無 origin 欄位、未知 id 防禦。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.systems import inventory


def _build(gd, origin_id=None, race="nord", class_id="warrior"):
    return build_character(gd, name="T", sex="male", race=race,
                           birthsign="warrior", class_id=class_id, origin_id=origin_id)


def test_default_origin_matches_standard_start():
    """未指定 / newcomer 開局 = 原本的標準起始(布魯瑪、50 金、無會籍/賞金/同伴)。"""
    gd = get_gamedata()
    for oid in (None, "newcomer"):
        c = _build(gd, oid)
        assert c.origin == "newcomer"
        assert c.location_id == gd.world["start_location"] == "bruma"
        assert c.visited_locations == ["bruma"]
        assert c.gold == 50
        assert c.factions == {} and c.bounties == {} and c.companions == []
        # 標準起始包仍在
        assert inventory.count_item(c, "minor_healing_potion") == 2
        assert inventory.count_item(c, "wheat") == 2


def test_unknown_origin_is_noop():
    """毀損/未知 origin id → 退回 newcomer,不丟例外、不留半套覆寫。"""
    gd = get_gamedata()
    c = _build(gd, "nonexistent_origin_xyz")
    assert c.origin == "newcomer"
    assert c.location_id == "bruma" and c.gold == 50


def test_origin_is_situational_not_power():
    """開局只動處境,不動屬性/技能 → 同種族同職業換開局,屬性與技能必須一致。"""
    gd = get_gamedata()
    base = _build(gd, "newcomer")
    for oid in gd.origins:
        c = _build(gd, oid)
        assert c.attributes == base.attributes, f"{oid} 改動了屬性"
        assert c.skills == base.skills, f"{oid} 改動了技能"


def test_origin_field_mechanics_apply():
    """資料驅動:逐一驗證每種開局欄位機制各套用一次(原 fugitive/sellsword/
    mage_initiate/fallen_noble/new_origins 六個 per-origin JSON 對照測試的合併)。

    每種欄位機制取一個代表開局驗一次,涵蓋高/低/零金邊界、各機制的繞門檻/
    疊加/穿戴/入背包路徑;另保留 temple_healer 的「heal 不在 newcomer base」
    差異斷言(否則 temple_healer 掉 heal 不會被抓)。
    """
    gd = get_gamedata()
    base = _build(gd, "newcomer")  # 差異對照基準(spell 疊加用)

    cs = {oid: _build(gd, oid) for oid in (
        "fugitive", "sellsword", "mage_initiate", "fallen_noble",
        "fighters_recruit", "guild_thief", "alikr_blade", "pilgrim",
        "shipwreck_survivor", "temple_healer", "orc_outcast")}

    # location + visited(硬開局換省起點)
    assert cs["fugitive"].location_id == "imperial_road"
    assert cs["fugitive"].visited_locations == ["imperial_road"]
    assert cs["sellsword"].location_id == "haafingar"      # 併自 test_sellsword_grants_companion_and_weapon

    # gold 三邊界:高(fallen_noble=250)/低(shipwreck_survivor=15)/零(fugitive=0)
    assert cs["fallen_noble"].gold == 250
    assert cs["shipwreck_survivor"].gold == 15
    assert cs["fugitive"].gold == 0

    # bounty(起手賞金套用)
    assert cs["fugitive"].bounties.get("賽羅迪爾") == 40

    # companion(同伴授予)
    assert "sellsword" in cs["sellsword"].companions

    # weapon + 入背包(配武器且武器真的進背包)
    assert cs["sellsword"].weapon == "steel_sword"
    assert inventory.count_item(cs["sellsword"], "steel_sword") >= 1
    assert cs["mage_initiate"].weapon == "flame_staff"     # 併自 test_mage_initiate(法杖配發)
    assert cs["fighters_recruit"].weapon == "steel_sword"
    assert cs["guild_thief"].weapon == "iron_dagger"
    assert inventory.count_item(cs["guild_thief"], "iron_dagger") >= 1
    assert cs["orc_outcast"].weapon == "iron_war_axe"

    # faction 直授繞 join_skill 門檻(三公會代表)
    assert cs["mage_initiate"].factions.get("mages_guild") == 0
    assert cs["fighters_recruit"].factions.get("companions") == 0
    assert cs["guild_thief"].factions.get("thieves_guild") == 0

    # spell 疊加 + 可施法資源重算;temple_healer 的 heal 差異須保留
    assert "flames" in cs["mage_initiate"].spells
    assert cs["mage_initiate"].max_magicka > 0
    assert "heal" in cs["temple_healer"].spells and "heal" not in base.spells

    # equip 穿戴(飾品 / 護甲各一)
    assert cs["fallen_noble"].equipped.get("amulet") == "gold_amulet"
    assert cs["orc_outcast"].equipped.get("cuirass") == "iron_cuirass"

    # 跨省 province(用上新省)
    assert gd.world["locations"][cs["alikr_blade"].location_id]["province"] == "漢默法爾"
    assert gd.world["locations"][cs["pilgrim"].location_id]["province"] == "晨風"   # 併自 test_pilgrim_relocates_to_morrowind

    # 無起手賞金自洽(硬開局/正派開局不夾帶賞金/會籍)
    assert cs["fighters_recruit"].bounties == {}
    assert cs["shipwreck_survivor"].factions == {} and cs["shipwreck_survivor"].bounties == {}


def test_every_origin_references_valid_content():
    """資料驗證:所有開局引用的地點/物品/裝備/公會/同伴/法術/賞金省份都真實存在,
    且裝備真的穿上、資源重算到健康滿值(防作者打錯 id)。"""
    gd = get_gamedata()
    provinces = {l["province"] for l in gd.world["locations"].values()}
    for oid, odef in gd.origins.items():
        assert "name" in odef and "blurb" in odef, f"{oid} 缺 name/blurb"
        if "location" in odef:
            assert odef["location"] in gd.world["locations"], f"{oid} 地點不存在"
        for entry in odef.get("items", []):
            assert entry[0] in gd.items, f"{oid} 物品 {entry[0]} 不存在"
        if "weapon" in odef:
            assert gd.item(odef["weapon"]).get("kind") == "weapon", f"{oid} weapon 非武器"
        for item_id in odef.get("equip", []):
            assert gd.item(item_id).get("kind") in ("armor", "jewelry"), f"{oid} equip 非裝備"
        for sid in odef.get("spells", []):
            assert sid in gd.spells, f"{oid} 法術 {sid} 不存在"
        for fid in odef.get("faction", {}):
            assert fid in gd.factions, f"{oid} 公會 {fid} 不存在"
        for cid in odef.get("companions", []):
            assert cid in gd.companions, f"{oid} 同伴 {cid} 不存在"
        for prov in odef.get("bounty", {}):
            assert prov in provinces, f"{oid} 賞金省份 {prov} 不存在"

        # 實際建出來必須是合法、滿血的角色
        c = _build(gd, oid)
        assert c.health == c.max_health and c.max_health > 0
        assert c.fatigue == c.max_fatigue and c.max_fatigue > 0
        # 穿上的護甲/飾品都還在背包(equip 的前置)
        for slot, item_id in c.equipped.items():
            assert inventory.count_item(c, item_id) >= 1, f"{oid} 穿了沒持有的 {item_id}"


def test_save_roundtrip_preserves_origin_state():
    """開局帶來的會籍/賞金/同伴/裝備/origin 欄位,存檔往返後完整保留。"""
    gd = get_gamedata()
    for oid in ("mage_initiate", "fugitive", "sellsword", "fallen_noble",
                "fighters_recruit", "guild_thief", "alikr_blade"):
        c = _build(gd, oid)
        c2 = Character.from_dict(c.to_dict())
        assert c2.origin == c.origin
        assert c2.factions == c.factions
        assert c2.bounties == c.bounties
        assert c2.companions == c.companions
        assert c2.equipped == c.equipped
        assert c2.location_id == c.location_id
        assert c2.gold == c.gold


def test_old_save_without_origin_field_loads():
    """舊存檔沒有 origin 欄位 → cls(**d) 用 dataclass 預設空字串,不報錯。"""
    gd = get_gamedata()
    d = _build(gd, "newcomer").to_dict()
    del d["origin"]
    c = Character.from_dict(d)
    assert c.origin == ""


def run():
    test_default_origin_matches_standard_start()
    test_unknown_origin_is_noop()
    test_origin_is_situational_not_power()
    test_origin_field_mechanics_apply()
    test_every_origin_references_valid_content()
    test_save_roundtrip_preserves_origin_state()
    test_old_save_without_origin_field_loads()


if __name__ == "__main__":
    run()
    print("test_origins OK")
