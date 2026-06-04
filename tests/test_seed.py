"""種子(seed)開放:make_seed 語意 + RNG 可重現 + 存檔保留種子。

把可重現 RNG 接到創角入口,讓玩家能輸入/分享種子重玩同一個世界與命運。
"""

import tempfile
from pathlib import Path

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG, make_seed
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat


# --- make_seed 語意 -----------------------------------------------------
def test_blank_seed_is_random_concrete_int():
    """空白/None → 隨機但具體的整數(可知、可分享),不是 None。"""
    for blank in ("", "   ", None):
        s = make_seed(blank)
        assert isinstance(s, int) and s >= 1


def test_numeric_seed_passthrough():
    assert make_seed("12345") == 12345
    assert make_seed("  42  ") == 42      # 去除前後空白
    assert make_seed("-7") == -7


def test_text_seed_is_stable_hash():
    """文字種子 → 穩定雜湊:同字串跨呼叫一致,不同字串(幾乎)不同。"""
    assert make_seed("流亡者") == make_seed("流亡者")
    assert make_seed("hello") == make_seed("hello")
    assert make_seed("hello") != make_seed("world")
    assert isinstance(make_seed("dragon"), int)


# --- RNG 可重現 ---------------------------------------------------------
def test_same_seed_reproduces_sequence():
    a, b = RNG(2024), RNG(2024)
    seq_a = [a.randint(1, 100) for _ in range(20)] + [a.random() for _ in range(5)]
    seq_b = [b.randint(1, 100) for _ in range(20)] + [b.random() for _ in range(5)]
    assert seq_a == seq_b
    # 不同種子 → 不同序列(幾乎必然)
    assert [RNG(1).randint(1, 10**9) for _ in range(5)] != \
           [RNG(2).randint(1, 10**9) for _ in range(5)]


def test_same_seed_reproduces_world_draws():
    """同種子下,世界遭遇抽樣完全一致(種子挑戰的核心保證)。"""
    gd = get_gamedata()
    draws = []
    for _ in range(2):
        rng = RNG(make_seed("ashfall-run"))
        foes = [combat.random_encounter(gd, 5, rng, max_danger=4) for _ in range(8)]
        draws.append([f.template_id for f in foes])
    assert draws[0] == draws[1]


# --- 存檔保留種子 -------------------------------------------------------
def test_save_load_preserves_seed():
    gd = get_gamedata()
    c = build_character(gd, name="Seeded", sex="male", race="nord",
                        birthsign="warrior", class_id="warrior")
    state = GameState(player=c, time=GameTime(), rng=RNG(777))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "save.json"
        state.save(path)
        loaded = GameState.load(path)
    assert loaded.rng.seed == 777


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_seed OK")
