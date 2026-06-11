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


def run():
    test_time_rollover()
    test_save_load_roundtrip()


if __name__ == "__main__":
    run()
    print("test_state OK")
