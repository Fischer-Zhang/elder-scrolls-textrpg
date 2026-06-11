"""種子(seed)開放:make_seed 語意 + RNG 遊戲層可重現。

把可重現 RNG 接到創角入口,讓玩家能輸入/分享種子重玩同一個世界與命運。
(存讀檔後 rng.seed 欄保留由 test_state.test_save_load_roundtrip 覆蓋。)
"""

from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG, make_seed
from tesrpg.systems import combat


# --- make_seed 語意 -----------------------------------------------------
def test_make_seed_semantics():
    """make_seed 三段輸入語意:空白 → 隨機具體整數、數字 → 直通、文字 → 穩定雜湊。"""
    # 空白/None → 隨機但具體的整數(可知、可分享),不是 None。
    for blank in ("", "   ", None):
        s = make_seed(blank)
        assert isinstance(s, int) and s >= 1
    # 數字字串(含空白、負號)直通為 int
    assert make_seed("12345") == 12345
    assert make_seed("  42  ") == 42      # 去除前後空白
    assert make_seed("-7") == -7
    # 文字種子 → 穩定雜湊:同字串跨呼叫一致,不同字串(幾乎)不同。
    assert make_seed("流亡者") == make_seed("流亡者")
    assert make_seed("hello") == make_seed("hello")
    assert make_seed("hello") != make_seed("world")
    assert isinstance(make_seed("dragon"), int)


# --- RNG 可重現 ---------------------------------------------------------
def test_same_seed_reproduces_world_draws():
    """同種子下,世界遭遇抽樣完全一致(種子挑戰的核心保證)。"""
    gd = get_gamedata()
    draws = []
    for _ in range(2):
        rng = RNG(make_seed("ashfall-run"))
        foes = [combat.random_encounter(gd, 5, rng, max_danger=4) for _ in range(8)]
        draws.append([f.template_id for f in foes])
    assert draws[0] == draws[1]
    # 負向(併自 test_same_seed_reproduces_sequence):異種子 → 異序列,證種子真的有作用
    # (否則忽略 seed 的退化 RNG 也會通過上面的同序列斷言)
    assert [RNG(1).randint(0, 9999) for _ in range(20)] != [RNG(2).randint(0, 9999) for _ in range(20)]


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_seed OK")
