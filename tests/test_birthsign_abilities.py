"""出生星座深化(R61 後續):5 個冷星座(戰士/法師/竊賊/淑女/駿馬)補主動威能/被動天賦。

混合身份:戰士/法師/淑女 = 每日一次主動威能(走 powers.POWERS,複用既有 use() 管線);
竊賊/駿馬 = 持續被動(birthsign_ability 即時讀,零存檔欄,比照 R61 種族被動)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.state import GameState, GameTime
from tesrpg.systems import birthsign_ability, combat, powers, progression


def _mk(sign, race="imperial", cls="warrior"):
    gd = get_gamedata()
    return gd, build_character(gd, name="x", sex="m", race=race, birthsign=sign, class_id=cls)


def _st(c):
    return GameState(player=c, time=GameTime())


# --- 不再有「死星座」:5 冷星座皆有主動威能或被動 ----------------------------
def test_no_cold_birthsign_left():
    gd = get_gamedata()
    for sign in ("warrior", "mage", "thief", "lady", "steed"):
        d = gd.birthsigns[sign]
        has_power = bool(d.get("powers"))
        has_passive = bool(d.get("passive"))
        assert has_power or has_passive, f"{sign} 仍是純創角加值的死星座"


# --- 戰士座:戰意奔湧(self_empower,複用 R61 berserk_buff) ------------------
def test_warrior_fury_self_empower():
    gd, c = _mk("warrior")
    st = _st(c)
    assert powers.power_id(c, gd) == "warrior_fury"
    assert powers.usable_in(c, st, gd, "combat")
    powers.use(c, st, gd)
    bb = [e for e in c.active_effects if e["kind"] == "berserk_buff"]
    assert bb and bb[0]["magnitude"] == 0.20 and bb[0]["turns"] == 3
    assert abs(combat._self_empower(c) - 0.20) < 1e-9    # 增傷確實流入 combat 讀取點
    assert not powers.usable_in(c, st, gd, "combat")     # 每日冷卻已燒掉


def test_warrior_fury_stacks_with_orc_berserk_bounded():
    """戰士座 + 獸人:兩個獨立每日威能(星座槽 + 種族槽)各加一道 berserk_buff → ≤0.40,有界(by-design)。"""
    gd, c = _mk("warrior", race="orsimer")
    st = _st(c)
    powers.use(c, st, gd)                                # 戰士座 0.20
    powers.racial_use(c, st, gd)                         # 獸人狂暴 0.20(+heal)
    assert abs(combat._self_empower(c) - 0.40) < 1e-9    # 上界 0.40(只兩個 berserk 源,有界)


# --- 法師座:法力湧現(補滿法力) -------------------------------------------
def test_mage_surge_restores_magicka():
    gd, c = _mk("mage")
    st = _st(c)
    assert powers.power_id(c, gd) == "magicka_surge"
    c.magicka = 0
    powers.use(c, st, gd)
    assert c.magicka == c.max_magicka and c.max_magicka > 0
    assert powers.power_def("magicka_surge")["contexts"] == ["combat", "utility"]


# --- 淑女座:淑女恩典(回血 + 回滿氣力 + 淨化 DoT) --------------------------
def test_lady_grace_heal_fatigue_cure():
    gd, c = _mk("lady")
    st = _st(c)
    assert powers.power_id(c, gd) == "ladys_grace"
    c.health = 1
    c.fatigue = 0
    c.active_effects.append({"kind": "dot", "element": "poison", "magnitude": 5, "turns": 3})
    powers.use(c, st, gd)
    assert c.health > 1                                  # 回血
    assert c.fatigue == c.max_fatigue                    # 回滿氣力
    assert not any(e["kind"] == "dot" for e in c.active_effects)   # DoT 淨化


# --- 竊賊座:巧手(潛行系技能 learn-by-doing 加速) --------------------------
def test_thief_stealth_aptitude_value():
    gd = get_gamedata()
    assert birthsign_ability.stealth_aptitude(_mk("thief")[1], gd) == 0.15
    for other in ("warrior", "mage", "lady", "steed", "shadow"):
        assert birthsign_ability.stealth_aptitude(_mk(other)[1], gd) == 0.0


def test_thief_stealth_xp_faster_only_for_stealth_spec():
    gd = get_gamedata()

    def mk(sign):
        c = build_character(gd, name="x", sex="m", race="imperial", birthsign=sign, class_id="warrior")
        c.specialization = ""        # 隔離職業專精層(R62),只留星座巧手
        c.well_rested = False
        c.skill_xp["sneak"] = 0.0
        c.skill_xp["blade"] = 0.0
        return c

    t, w = mk("thief"), mk("warrior")
    progression.use_skill(t, gd, "sneak", 1.0)           # 潛行系(spec==stealth)
    progression.use_skill(w, gd, "sneak", 1.0)
    assert t.skill_xp["sneak"] > w.skill_xp["sneak"]
    assert abs(t.skill_xp["sneak"] - 1.15 * w.skill_xp["sneak"]) < 1e-9

    t2, w2 = mk("thief"), mk("warrior")
    progression.use_skill(t2, gd, "blade", 1.0)          # 戰鬥系(非潛行)→ 不受影響
    progression.use_skill(w2, gd, "blade", 1.0)
    assert t2.skill_xp["blade"] == w2.skill_xp["blade"]

    # 竊賊座無主動威能槽(走被動)
    assert powers.power_id(t, gd) is None


# --- 駿馬座:疾行(旅行耗時降低) -------------------------------------------
def test_steed_swift_travel_value_and_faster():
    gd = get_gamedata()
    assert birthsign_ability.travel_factor_bonus(_mk("steed")[1], gd) == 0.15
    for other in ("warrior", "thief", "shadow"):
        assert birthsign_ability.travel_factor_bonus(_mk(other)[1], gd) == 0.0
    assert powers.power_id(_mk("steed")[1], gd) is None   # 駿馬座走被動,無主動槽


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_birthsign_abilities OK")
