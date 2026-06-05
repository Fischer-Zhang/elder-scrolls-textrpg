"""招兵買馬 階段一回歸測試:資格門檻 / 營地 / 招募 / 攻城整合(大軍壓境 + 實戰援軍)。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import politics, warband


def _setup():
    gd = get_gamedata()
    c = build_character(gd, name="帥", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    return gd, c


def test_warlord_gate():
    gd, c = _setup()
    assert not warband.is_warlord(c, gd)                  # 一介白身
    c.thaneships.append("bruma")                          # 武士 → 領主
    assert warband.is_warlord(c, gd)
    gd, c = _setup(); c.city_faction["windhelm"] = "imperial"   # 征服城 → 領主
    assert warband.is_warlord(c, gd)
    gd, c = _setup()                                      # 公會掌門 → 首領
    fid = next(iter(gd.factions)); c.factions[fid] = len(gd.factions[fid]["ranks"]) - 1
    assert warband.is_guildmaster(c, gd) and warband.is_warlord(c, gd)


def test_camp_eligibility():
    gd, c = _setup(); c.thaneships.append("bruma")
    wild = next(lid for lid, l in gd.world["locations"].items() if l["type"] == "wilderness")
    city = next(lid for lid, l in gd.world["locations"].items() if l["type"] == "city")
    dgn = next(lid for lid, l in gd.world["locations"].items() if l["type"] == "dungeon")
    assert warband.can_make_camp(c, gd, wild)            # 野外可紮營
    assert not warband.can_make_camp(c, gd, city)        # 城內不行
    assert not warband.can_make_camp(c, gd, dgn)         # 地城未肅清 → 不行
    c.cleared_dungeons.append(gd.location(dgn)["dungeon"])
    assert warband.can_make_camp(c, gd, dgn)             # 肅清後可佔領
    gd, c = _setup()                                      # 非領主 → 哪都不能紮營
    assert not warband.can_make_camp(c, gd, wild)


def test_recruit_caps_and_costs():
    gd, c = _setup(); c.thaneships.append("bruma")
    assert warband.recruit_soldiers(c, 5) == 0           # 無營地不能招
    warband.make_camp(c, "bruma"); c.gold = 1000
    assert warband.recruit_soldiers(c, 5) == 5
    assert c.soldiers == 5 and c.gold == 1000 - 5 * warband.SOLDIER_COST
    c.gold = warband.SOLDIER_COST * 2                     # 金幣上限
    assert warband.recruit_soldiers(c, 10) == 2
    c.gold = 99999; c.soldiers = warband.MAX_SOLDIERS - 1  # 士兵上限
    assert warband.recruit_soldiers(c, 10) == 1 and c.soldiers == warband.MAX_SOLDIERS


def test_fielded_and_soften():
    gd, c = _setup()
    c.soldiers = 20
    assert warband.fielded_soldiers(c) == warband.FIELD_CAP        # 上場數有上限
    c.soldiers = 3
    assert warband.fielded_soldiers(c) == 3
    assert warband.army_soften(c) == 3 * warband.ARMY_SOFTEN_PER


def test_footman_is_troop():
    gd, _ = _setup()
    assert gd.companions["footman"].get("troop") is True          # 士兵兵種,不在旅店招


def test_save_roundtrip_and_backward_compat():
    import json
    gd, c = _setup(); c.soldiers = 12; c.camp = "bruma"
    loaded = Character.from_dict(json.loads(json.dumps(c.to_dict())))
    assert loaded.soldiers == 12 and loaded.camp == "bruma"
    d = c.to_dict()
    for k in ("soldiers", "camp"):
        del d[k]
    old = Character.from_dict(d)
    assert old.soldiers == 0 and old.camp == ""


# --- 攻城整合煙霧 -------------------------------------------------------
def _siege(menu_seq, battle_result, soldiers=20):
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd, c = _setup()
    c.allegiance = "imperial"; c.location_id = "windhelm"   # 敵城(獨立)
    c.soldiers = soldiers; c.camp = "bruma"
    state = GameState(player=c, rng=RNG(1), game_mode="adventure")
    mseq = iter(menu_seq); captured = {}

    def battle(*a, **k):
        captured["companions"] = k.get("companions")
        return battle_result
    saved = (M.run_battle, ui.menu, ui.confirm, ui.message)
    M.run_battle = battle
    ui.menu = lambda *a, **k: next(mseq, None)
    ui.confirm = lambda *a, **k: True
    ui.message = lambda *a, **k: None
    try:
        res = M.action_siege(state, gd, "windhelm")
    finally:
        M.run_battle, ui.menu, ui.confirm, ui.message = saved
    return gd, c, res, captured


def test_army_press_depletes_garrison_once():
    gd, c, res, _ = _siege(["army", None], "victory", soldiers=20)   # 大軍壓境後退出
    seed = gd.rulers["windhelm"]["garrison"]
    assert politics.garrison_of(c, gd, "windhelm") == seed - 20 * warband.ARMY_SOFTEN_PER
    assert "army" in politics.ops_done(c, "windhelm")                # 每役一次(已記)


def test_assault_fields_soldiers_as_allies():
    gd, c, res, cap = _siege(["assault"], "victory", soldiers=20)
    assert res is None and politics.faction_of(c, gd, "windhelm") == "imperial"
    assert cap["companions"].count(warband.SOLDIER_TROOP) == warband.FIELD_CAP   # 6 名士兵上陣


def run():
    test_warlord_gate()
    test_camp_eligibility()
    test_recruit_caps_and_costs()
    test_fielded_and_soften()
    test_footman_is_troop()
    test_save_roundtrip_and_backward_compat()
    test_army_press_depletes_garrison_once()
    test_assault_fields_soldiers_as_allies()


if __name__ == "__main__":
    run()
    print("test_warband 全通過")
