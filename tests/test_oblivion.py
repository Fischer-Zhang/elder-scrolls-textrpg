"""湮滅危機主線弧 + 達貢之力永久層 回歸測試:
- 達貢之力獨立疊加層(grant/聚合/不污染 base/存檔 round-trip/舊檔遷移);
- 任務 gate(requires_event / requires_faction)、叛離(expel_faction)、雙結局互斥;
- 兩結局皆消滅神話黎明 + 阻擋再入會;教徒結局授 boon + 教團全滅 + 惡名;
- 內容資料完整(5 地城/達貢2變體/world 節點/4 神器/賽羅迪爾九城)。
"""
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.systems import dagon_boon, factions, magic, quests, worldstate
from tesrpg.state import GameState, GameTime
from tesrpg.rng import RNG


def _gd_char():
    gd = get_gamedata()
    c = build_character(gd, name="試", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    return gd, c


# --- 達貢之力永久層 ----------------------------------------------------
def test_dagon_boon_layer_stacks_without_base_write():
    gd, c = _gd_char()
    s0, w0, mg0 = c.attr("strength"), c.attr("willpower"), c.max_magicka
    fire0, destr0 = magic.entity_resist(c, gd).get("fire", 0), c.skill("destruction")
    dagon_boon.grant(c, gd)
    assert c.attr("strength") == s0 + 18 and c.attr("willpower") == w0 + 12
    assert c.skill("destruction") == destr0 + 10
    assert c.max_magicka == mg0 + 25
    assert magic.entity_resist(c, gd).get("fire", 0) == fire0 + 60
    assert c.base_attr("strength") == s0      # 🔴 鐵律:絕不寫回 base
    assert c.base_skill("destruction") == destr0


def test_dagon_boon_save_roundtrip_and_migration():
    gd, c = _gd_char()
    dagon_boon.grant(c, gd)
    s = c.attr("strength")
    c2 = Character.from_dict(c.to_dict())
    dagon_boon.ensure_dagon_fields(c2, gd)
    assert c2.dagon_boon and c2.attr("strength") == s
    # 舊存檔(無 dagon_* 欄)→ 遷移補欄為 False、零加成
    d = c.to_dict()
    for k in [k for k in list(d) if k.startswith("dagon_")]:
        del d[k]
    c3 = Character.from_dict(d)
    dagon_boon.ensure_dagon_fields(c3, gd)
    assert c3.dagon_boon is False and c3.dagon_attr_bonus == {}


# --- 任務 gate / 叛離 ---------------------------------------------------
def test_main_quest_gated_by_event_and_faction():
    gd, c = _gd_char()
    assert quests.available_quests(c, gd, "main") == []          # kvatch_falls 前不現
    c.world_events_fired.append("kvatch_falls")
    av = quests.available_quests(c, gd, "main")
    assert "main_oblivion" in av and "md7" not in av             # 非教徒看不到 md7
    c.factions["mythic_dawn"] = 6
    assert "md7" in quests.available_quests(c, gd, "main")        # 教徒頂階才見 md7


def test_defection_expels_mythic_dawn():
    gd, c = _gd_char()
    c.world_events_fired.append("kvatch_falls")
    c.factions["mythic_dawn"] = 3
    quests.accept_quest(c, gd, "main_oblivion")                   # 接正道 → 叛離
    assert c.factions["mythic_dawn"] == -1


# --- 雙結局:互斥 + 都消滅神話黎明 -------------------------------------
def _finish(gd, c, dungeons, kill, quest=None):
    if quest:
        quests.accept_quest(c, gd, quest)
    if quest == "md7":
        c.location_id = "dawn_sanctum"; quests.check_completion(c, gd)   # reach 達標
    for d in dungeons:
        quests.record_dungeon_clear(c, d)
    c.kill_counts[kill] = 1
    return quests.check_completion(c, gd)


def test_hero_ending_banishes_and_eradicates_cult():
    gd, c = _gd_char()
    c.world_events_fired.append("kvatch_falls")
    _finish(gd, c, ["kvatch_gate", "bravil_gate", "dagon_shrine", "the_deadlands"],
            "mehrunes_dagon", quest="main_oblivion")
    st = GameState(player=c, time=GameTime(), rng=RNG(1), start_time=GameTime())
    fired = [e["id"] for e in worldstate.update(st, gd)]
    assert "dagon_banished" in fired and "dawn_undone" not in fired   # 殺滿血達貢
    assert "mythic_dawn" not in c.factions                            # 正道亦消滅教團
    assert "mythic_dawn_eradicated" in c.world_events_fired
    assert factions.join_block_reason(c, gd, "mythic_dawn") is not None   # 不可再入會


def test_cult_ending_grants_boon_and_destroys_cult():
    gd, c = _gd_char()
    c.world_events_fired.append("kvatch_falls")
    c.factions["mythic_dawn"] = 6
    s0 = c.attr("strength")
    _finish(gd, c, ["dawn_sanctum"], "mehrunes_dagon_diminished", quest="md7")
    assert c.dagon_boon and c.attr("strength") == s0 + 18         # 竊得達貢之力
    assert "mythic_dawn" not in c.factions and c.infamy >= 40     # 教團全滅 + 惡名
    st = GameState(player=c, time=GameTime(), rng=RNG(1), start_time=GameTime())
    fired = [e["id"] for e in worldstate.update(st, gd)]
    assert "dawn_undone" in fired and "dagon_banished" not in fired   # 殺削弱達貢


# --- 內容資料完整 ------------------------------------------------------
def test_content_integrity():
    gd, _ = _gd_char()
    items = set(gd.items) | set(gd.weapons) | set(gd.armor)
    for art in ["crusaders_aegis", "dawnfang", "mysterium_xarxes", "sigil_stone_fragment"]:
        assert art in items, art
    for d in ["kvatch_gate", "bravil_gate", "dagon_shrine", "the_deadlands", "dawn_sanctum"]:
        assert d in gd.dungeons, d
        assert gd.dungeons[d]["boss"]["enemy"] in gd.bestiary
    assert gd.bestiary["mehrunes_dagon"]["solo"] and gd.bestiary["mehrunes_dagon_diminished"]["solo"]
    # 賽羅迪爾九城補全(含 bravil/chorrol/leyawiin)
    cyr = [lid for lid, d in gd.world["locations"].items()
           if d.get("province") == "賽羅迪爾" and d.get("type") in ("city", "town")]
    assert len(cyr) == 9 and {"bravil", "chorrol", "leyawiin"} <= set(cyr)


def test_oblivion_gate_visibility():
    """湮滅之門逐門開合:開局全隱、kvatch_falls 開第一道、清掉就閉、下一道開;
    死亡之地要破祭壇才現;神殿要入會;危機落幕全消;隱藏地點會把玩家拋回最近的城。"""
    from tesrpg.systems import world
    gd, c = _gd_char()
    gates = ["kvatch_gate", "bravil_gate", "dagon_shrine", "the_deadlands", "dawn_sanctum"]
    assert all(not world.is_visible(c, gd, g) for g in gates)                  # 開局全隱
    c.world_events_fired.append("kvatch_falls")
    assert world.is_visible(c, gd, "kvatch_gate") and not world.is_visible(c, gd, "bravil_gate")
    c.cleared_dungeons.append("kvatch_gate")
    assert not world.is_visible(c, gd, "kvatch_gate") and world.is_visible(c, gd, "bravil_gate")
    c.cleared_dungeons += ["bravil_gate", "dagon_shrine"]
    assert world.is_visible(c, gd, "the_deadlands")                            # 破祭壇→死亡之地裂開
    assert not world.is_visible(c, gd, "dawn_sanctum")                         # 神殿仍須入會
    c.factions["mythic_dawn"] = 0
    assert world.is_visible(c, gd, "dawn_sanctum")
    c.world_events_fired.append("oblivion_crisis_ended")
    assert all(not world.is_visible(c, gd, g) for g in gates)                  # 危機落幕全消
    c.location_id = "the_deadlands"                                            # 站在崩合的地城裡
    dest = world.relocate_target(c, gd)
    assert gd.world["locations"][dest]["type"] in ("city", "town") and world.is_visible(c, gd, dest)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_oblivion OK")
