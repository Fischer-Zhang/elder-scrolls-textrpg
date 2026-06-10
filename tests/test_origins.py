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


def test_fugitive_hard_start():
    gd = get_gamedata()
    c = _build(gd, "fugitive")
    assert c.location_id == "imperial_road"
    assert c.visited_locations == ["imperial_road"]
    assert c.gold == 0
    assert c.bounties.get("賽羅迪爾") == 40


def test_sellsword_grants_companion_and_weapon():
    gd = get_gamedata()
    c = _build(gd, "sellsword")
    assert c.location_id == "haafingar"
    assert "sellsword" in c.companions
    assert c.weapon == "steel_sword"
    assert inventory.count_item(c, "steel_sword") >= 1


def test_mage_initiate_grants_membership_staff_spell():
    gd = get_gamedata()
    c = _build(gd, "mage_initiate")
    # 直接給會籍 → 繞過 join_skill 門檻
    assert c.factions.get("mages_guild") == 0
    assert c.weapon == "flame_staff"
    assert "flames" in c.spells
    # 法杖傷害靠法師技能成長,起始可施法(資源已重算)
    assert c.max_magicka > 0


def test_fallen_noble_wears_amulet_and_rich():
    gd = get_gamedata()
    c = _build(gd, "fallen_noble")
    assert c.gold == 250
    assert c.equipped.get("amulet") == "gold_amulet"


def test_pilgrim_relocates_to_morrowind():
    gd = get_gamedata()
    c = _build(gd, "pilgrim")
    assert gd.world["locations"][c.location_id]["province"] == "晨風"


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


def test_new_origins_situational_distinctives():
    """六個新開局各自的處境特徵(補戰士/盜賊公會、漢默法爾、海難/治療/獸人)。"""
    gd = get_gamedata()
    base = _build(gd, "newcomer")
    # 戰友團新血:授戰友團會籍(無起手賞金;戰友團 lawful:false 自洽)
    c = _build(gd, "fighters_recruit")
    assert c.factions.get("companions") == 0 and c.weapon == "steel_sword" and c.bounties == {}
    # 盜賊公會:授盜賊會籍 + 匕首在手
    c = _build(gd, "guild_thief")
    assert c.factions.get("thieves_guild") == 0 and inventory.count_item(c, "iron_dagger") >= 1
    # 阿利克爾劍客:起點在漢默法爾(用上新省)
    c = _build(gd, "alikr_blade")
    assert gd.world["locations"][c.location_id]["province"] == "漢默法爾"
    # 海難倖存者:硬開局(低金、無賞金、無會籍)
    c = _build(gd, "shipwreck_survivor")
    assert c.gold == 15 and c.bounties == {} and c.factions == {}
    # 神殿治療者:授非預設的「治療術」(minor_heal 人人皆有,heal 才是處境加成)
    c = _build(gd, "temple_healer")
    assert "heal" in c.spells and "heal" not in base.spells
    # 獸人放逐者:穿鐵甲、提戰斧
    c = _build(gd, "orc_outcast")
    assert c.equipped.get("cuirass") == "iron_cuirass" and c.weapon == "iron_war_axe"


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
    test_fugitive_hard_start()
    test_sellsword_grants_companion_and_weapon()
    test_mage_initiate_grants_membership_staff_spell()
    test_fallen_noble_wears_amulet_and_rich()
    test_pilgrim_relocates_to_morrowind()
    test_new_origins_situational_distinctives()
    test_every_origin_references_valid_content()
    test_save_roundtrip_preserves_origin_state()
    test_old_save_without_origin_field_loads()


if __name__ == "__main__":
    run()
    print("test_origins OK")
