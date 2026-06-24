"""R85 湮滅危機尾聲:英雄/叛徒的餘暉 —— 結局分流 gate + 傳奇誓福 payoff(守紅線)。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import boons, quests

# 誓福紅線:絕不給 strength / sneak / 武器技能(餵偷襲秒殺)。R45。
_RED = {"strength", "sneak", "blade", "blunt", "axe", "marksman", "hand_to_hand"}


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="x", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, c


def test_epilogue_boons_exist_and_respect_red_lines():
    gd = get_gamedata()
    for b in ("kvatch_hero", "dagon_apostate"):
        d = gd.boons[b]
        bad = _RED & (set(d.get("attr", {})) | set(d.get("skill", {})))
        assert not bad, f"{b} 誓福踩紅線:{bad}"
        assert d.get("name")


def test_hero_ending_sees_only_hero_epilogue():
    gd, c = _char()
    c.world_events_fired.append("oblivion_crisis_ended")
    c.completed_quests.append("main_oblivion")
    av = quests.available_quests(c, gd, "main")
    assert "epilogue_hero" in av and "epilogue_apostate" not in av


def test_apostate_ending_sees_only_apostate_epilogue():
    gd, c = _char()
    c.world_events_fired.append("oblivion_crisis_ended")
    c.completed_quests.append("md7")
    av = quests.available_quests(c, gd, "main")
    assert "epilogue_apostate" in av and "epilogue_hero" not in av


def test_pre_victory_sees_no_epilogue():
    gd, c = _char()
    av = quests.available_quests(c, gd, "main")
    assert not any(q.startswith("epilogue_") for q in av)
    # 只觸發旗標但未完成對應結局任務 → 仍不現(requires_quest gate)
    c.world_events_fired.append("oblivion_crisis_ended")
    av2 = quests.available_quests(c, gd, "main")
    assert not any(q.startswith("epilogue_") for q in av2)


def test_epilogue_grant_boon_applies():
    gd, c = _char()
    boons.grant(c, gd, "kvatch_hero")
    assert "kvatch_hero" in c.boons
    assert c.boon_attr_bonus.get("personality", 0) >= 10   # 聚合層生效
    boons.grant(c, gd, "dagon_apostate")
    assert "dagon_apostate" in c.boons
    assert c.boon_skill_bonus.get("illusion", 0) >= 10


def test_epilogue_quest_schema_and_fks():
    gd = get_gamedata()
    for qid, ending in (("epilogue_hero", "main_oblivion"), ("epilogue_apostate", "md7")):
        q = gd.quests[qid]
        assert q["source"] == "main"
        assert q["requires_event"] == "oblivion_crisis_ended"
        assert q["requires_quest"] == ending and ending in gd.quests   # 指向真實結局任務
        assert q["reward"]["grant_boon"] in gd.boons                    # 誓福存在
        for st in q["stages"]:
            obj = st["objective"]
            assert obj["type"] == "reach"
            assert obj["location"] in gd.world["locations"], obj["location"]   # reach 目標存在


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_epilogue")
