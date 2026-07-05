"""R121 念力球反噬機制:_apply_orb_curse 隨機大減**非秘術**技能(暫態 _dungeon_curse·地城限·離場即清)+
_dungeon_orb_break(念力術破球免反噬)。skill() 讀暫態負層、清空即恢復(不入檔·非地城者 None→+0 byte-identical)。"""
from tesrpg.gamedata import get_gamedata
from tesrpg.creation import build_character
from tesrpg.state import GameState, GameTime
from tesrpg.rng import RNG
import tesrpg.main as main


def _p(seed=1):
    gd = get_gamedata()
    c = build_character(gd, name="O", sex="male", race="breton", birthsign="mage", class_id="mage")
    c.skills.update(mysticism=100, blade=80, destruction=70, block=60)
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=12))
    return gd, c, st


def _silence():
    om, os = main.ui.message, main.ui.show_events
    main.ui.message = lambda *a, **k: None
    main.ui.show_events = lambda *a, **k: None
    return om, os


def test_skill_curse_read_and_clear():
    gd, c, st = _p()
    assert not hasattr(c, "_dungeon_curse") or not c._dungeon_curse
    base = c.skill("blade")
    c._dungeon_curse = {"blade": -30}
    assert c.skill("blade") == base - 30          # 暫態負層計入 skill()
    assert c.skill("mysticism") == 100            # 未反噬技能不受影響
    c._dungeon_curse = {}                          # 離場清除 → 恢復
    assert c.skill("blade") == base


def test_orb_curse_hits_random_nonmysticism_skill_no_repeat():
    gd, c, st = _p()
    om, os = _silence()
    try:
        c._dungeon_curse = {}
        main._apply_orb_curse(st, gd)
        assert c._dungeon_curse and "mysticism" not in c._dungeon_curse   # 秘術永不反噬
        sid, pen = next(iter(c._dungeon_curse.items()))
        assert pen < 0 and c.base_skill(sid) > 0                          # 挑有點數技能·大減
        assert c.skill(sid) == c.base_skill(sid) + pen                    # skill() 反映反噬
        assert -pen == min(c.base_skill(sid), main._ORB_CURSE)           # 效果大·夾不低於 0
        main._apply_orb_curse(st, gd)                                     # 第二顆未破 → 反噬另一技能(不重複)
        assert len(c._dungeon_curse) == 2 and "mysticism" not in c._dungeon_curse
    finally:
        main.ui.message, main.ui.show_events = om, os


def test_orb_break_requires_telekinesis_and_magicka():
    gd, c, st = _p()
    om, os = _silence()
    try:
        c.spells = [s for s in c.spells if s != "telekinesis"]
        assert main._dungeon_orb_break(st, gd) is False          # 無念力術 → 破不了
        c.spells.append("telekinesis"); c.magicka = c.max_magicka = 300
        before = c.magicka
        assert main._dungeon_orb_break(st, gd) is True           # 會念力術 + 魔力 → 破除
        assert c.magicka < before                                # 耗魔
        c.magicka = 0
        assert main._dungeon_orb_break(st, gd) is False          # 魔力不足 → 破不了
    finally:
        main.ui.message, main.ui.show_events = om, os


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
