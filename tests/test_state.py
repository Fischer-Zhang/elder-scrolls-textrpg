"""時間/曆法與存讀檔的單元測試。"""

import tempfile
from pathlib import Path

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import progression


def test_time_rollover():
    t = GameTime(era=3, year=433, month=12, day=30, hour=20)
    t.advance(10)  # 20 + 10 = 30 → 跨日、跨月、跨年
    assert (t.year, t.month, t.day, t.hour) == (434, 1, 1, 6)


def test_save_load_roundtrip():
    gd = get_gamedata()
    c = build_character(gd, name="Saver", sex="female", race="breton",
                        birthsign="apprentice", class_id="mage")
    progression.use_skill(c, gd, "destruction", 5.0)
    state = GameState(player=c, time=GameTime(year=433, month=3, day=5, hour=14),
                      rng=RNG(12345))
    state.rng.randint(1, 100)  # 推進亂數狀態

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "save.json"
        state.save(path)
        loaded = GameState.load(path)

    assert loaded.player.name == "Saver"
    assert loaded.player.skills == c.skills
    assert loaded.player.skill_xp == c.skill_xp
    assert loaded.player.max_magicka == c.max_magicka
    assert (loaded.time.year, loaded.time.month, loaded.time.day, loaded.time.hour) == (433, 3, 5, 14)
    # 亂數序列可續接重現
    assert loaded.rng.randint(1, 100) == state.rng.randint(1, 100)
    # 種子欄保留(供 legacy 總結/角色卡顯示與分享)
    assert loaded.rng.seed == 12345


def test_legacy_save_drops_removed_durability_and_armorer():
    """向後相容:移除耐久/修理 + Armorer 技能後,含舊欄位的存檔仍能乾淨載入。"""
    import json
    gd = get_gamedata()
    c = build_character(gd, name="OldHero", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    state = GameState(player=c, time=GameTime(year=433, month=1, day=1, hour=8), rng=RNG(7))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "save.json"
        state.save(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        p = raw["player"]
        # 注入舊存檔遺留:耐久欄 + 已移除的 armorer 技能 + 指向已刪/已改節點的里程碑選擇 + major_skills 含 armorer
        p["weapon_condition"] = 73.0
        p["armor_condition"] = {"cuirass": 40.0}
        p["skills"]["armorer"] = 88
        p["skill_xp"]["armorer"] = 12.5
        p["mastery_choices"] = {"armorer_50": "field_smith", "smithing_50": "forge_repair"}
        p["major_skills"] = list(p.get("major_skills", [])) + ["armorer"]
        path.write_text(json.dumps(raw), encoding="utf-8")
        loaded = GameState.load(path)               # 不得拋例外
    pl = loaded.player
    assert not hasattr(pl, "weapon_condition") and not hasattr(pl, "armor_condition")
    assert "armorer" not in pl.skills and "armorer" not in pl.skill_xp
    assert "armorer" not in pl.major_skills         # 主修殘留也剝
    assert "armorer_50" not in pl.mastery_choices   # 指向已刪節點 → 清掉
    assert "smithing_50" not in pl.mastery_choices  # 舊 opt 不存在 → 清掉(回 pending)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_state OK")
