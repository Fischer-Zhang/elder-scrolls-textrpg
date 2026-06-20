"""斯庫瑪 / 月糖成癮系統的單元測試(亢奮 ↔ 成癮詛咒 的 power↔curse 天平)。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import skooma


def _state(race="khajiit", seed=1, hour=12):
    gd = get_gamedata()
    c = build_character(gd, name="K", sex="male", race=race, birthsign="thief", class_id="thief")
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


def _clear_high(c, st, gd):
    """推進到(疊加後的)亢奮結束之後並結算 → 進入清醒/戒斷。"""
    now = st.time.absolute_hours()
    st.time.advance(max(0, c.skooma_high_until - now) + 1)
    return skooma.update(st, gd)


def _addict(c, st, gd, n=4):
    for _ in range(n):
        skooma.dose(st, gd, strong=True)
    _clear_high(c, st, gd)


# --- 用藥 → 亢奮(有效值、非 base)----------------------------------------
def test_dose_grants_timed_high_effective_not_base():
    gd, c, st = _state()
    base_spd = c.base_attr("speed"); base_str = c.base_attr("strength")
    c.fatigue = 1                                           # 先耗盡體力(absorb)
    base_fat = c.max_fatigue
    r = skooma.dose(st, gd, strong=True)
    assert r["ok"] and skooma.is_high(c, st)
    assert c.max_fatigue > base_fat                         # 意志/敏捷增益 → 體力上限上升(absorb)
    assert r["restored"].get("fatigue", 0) > 0             # 一次性回復體力(absorb)
    assert c.attr("speed") == base_spd + 8                  # 亢奮增益進有效值
    assert c.base_attr("speed") == base_spd                 # base 不動(鐵律)
    # 亢奮過期 → 清空(此例未成癮 → 不轉戒斷)
    st.time.advance(skooma.SKOOMA_HIGH_HOURS + 1)
    evs = skooma.update(st, gd)
    assert not skooma.is_high(c, st) and c.skooma_attr_bonus == {}
    assert any(e["kind"] == "comedown" for e in evs)


# --- 成癮 → 戒斷 ---------------------------------------------------------
def test_addiction_triggers_withdrawal():
    gd, c, st = _state()
    base_str = c.base_attr("strength"); base_fat = c.max_fatigue
    _addict(c, st, gd, n=skooma.WITHDRAWAL_THRESHOLD)
    assert skooma.is_addicted(c) and not skooma.is_high(c, st)
    assert skooma.withdrawal_step(c, st) > 0
    assert c.attr("strength") < base_str                    # 戒斷負層削屬性
    assert c.max_fatigue < base_fat                         # 力量/意志/敏捷/耐力 ↓ → 體力上限下滑


def test_deeper_addiction_deeper_withdrawal():
    gd, light, st1 = _state(seed=1)
    _addict(light, st1, gd, n=skooma.WITHDRAWAL_THRESHOLD)      # 剛過門檻 → 最輕戒斷
    gd2, heavy, st2 = _state(seed=2)
    _addict(heavy, st2, gd, n=skooma.WITHDRAWAL_THRESHOLD + 3)  # 沉淪更深
    assert skooma.withdrawal_step(heavy, st2) > skooma.withdrawal_step(light, st1)
    assert heavy.attr("strength") < light.attr("strength")     # 成癮越深、戒斷越痛


def test_redose_relieves_withdrawal_but_deepens_addiction():
    gd, c, st = _state()
    first = skooma.dose(st, gd, strong=True)["hours"]
    _addict(c, st, gd, n=skooma.WITHDRAWAL_THRESHOLD)
    assert skooma.withdrawal_step(c, st) > 0
    add_before = c.skooma_addiction
    later = skooma.dose(st, gd, strong=True)                # 再用藥
    assert skooma.is_high(c, st) and skooma.withdrawal_step(c, st) == 0   # 戒斷暫解
    assert c.skooma_addiction == add_before + 1             # 但成癮更深
    assert later["hours"] < first                           # 耐受性:同劑量亢奮更短


# --- 戒除:熬過去 / 解癮儀式 ---------------------------------------------
def test_ride_it_out_decay_to_clean():
    gd, c, st = _state()
    _addict(c, st, gd, n=5)
    assert skooma.is_addicted(c)
    for _ in range(40):                                     # 長期清醒 → 成癮逐步衰減
        st.time.advance(24); skooma.update(st, gd)
    assert c.skooma_addiction == 0 and c.skooma_attr_bonus == {}


def test_cure_quest_flow_and_repeatable():
    from tesrpg.systems import quests, inventory
    gd, c, st = _state()
    base_str = c.base_attr("strength")                      # absorb
    _addict(c, st, gd, n=5)
    assert skooma.is_addicted(c) and c.attr("strength") < base_str   # absorb: 戒斷層削屬性
    qid = "quest_skooma_cure"
    quests.accept_quest(c, gd, qid)
    assert quests.is_active(c, qid)
    inventory.add_item(c, "garlic", 4); quests.check_completion(c, gd)       # 階段1
    inventory.add_item(c, "nightshade", 3); quests.check_completion(c, gd)   # 階段2
    quests.record_kill(c, "dro_mathra_shade"); quests.check_completion(c, gd)  # 階段3
    assert quests.is_done(c, qid)
    assert inventory.count_item(c, "garlic") == 0           # 採集物上繳消耗
    skooma.cure(c, gd)                                      # = action_skooma_cure 的核心
    assert c.skooma_addiction == 0                          # 併自 test_cure:成癮計數歸零
    assert c.skooma_attr_bonus == {} and c.skooma_skill_bonus == {}  # absorb: 雙層清空
    assert c.attr("strength") == base_str                   # absorb: 戒斷層復原
    c.completed_quests.remove(qid)
    assert not skooma.is_addicted(c) and not quests.is_done(c, qid)   # 可重複求解


def test_no_free_cure_after_riding_out_a_completed_quest():
    """對抗審查漏洞回歸:完成淨糖採集/擊殺但『不行儀式』、改以長期清醒戒掉 → 殘留的已完成
    任務不得在日後再成癮時免費解癮(自然戒除須棄置任務,使每次成癮都得重新賺取)。"""
    from tesrpg.systems import quests, inventory
    gd, c, st = _state()
    _addict(c, st, gd, n=5)
    qid = skooma.CURE_QUEST_ID
    quests.accept_quest(c, gd, qid)
    inventory.add_item(c, "garlic", 4); quests.check_completion(c, gd)
    inventory.add_item(c, "nightshade", 3); quests.check_completion(c, gd)
    quests.record_kill(c, "dro_mathra_shade"); quests.check_completion(c, gd)
    assert quests.is_done(c, qid)
    for _ in range(40):                                     # 不行儀式,熬過去(ride-it-out)
        st.time.advance(24); skooma.update(st, gd)
    assert not skooma.is_addicted(c)
    assert not quests.is_done(c, qid) and qid not in c.quests   # 殘留任務已作廢
    _addict(c, st, gd, n=5)                                 # 再成癮
    assert not quests.is_done(c, qid)                       # 不得免費解 → 須重新賺取


# --- 紅線守門:亢奮絕不碰 力量/潛行/武器傷害 ----------------------------
def test_high_never_touches_strength_or_sneak():
    gd, c, st = _state()
    base_str = c.base_attr("strength"); base_sneak = c.base_skill("sneak")
    skooma.dose(st, gd, strong=True)
    assert skooma.is_high(c, st)
    assert "strength" not in c.skooma_attr_bonus            # 不放大 attack_damage(str_mult)
    assert c.attr("strength") == base_str
    assert c.skooma_skill_bonus == {}                       # 亢奮不碰任何技能
    assert c.skill("sneak") == base_sneak                   # 不放大偷襲倍率


# --- 存檔向後相容 -------------------------------------------------------
def test_save_roundtrip_preserves_skooma_state():
    gd, c, st = _state()
    skooma.dose(st, gd, strong=True)
    skooma.dose(st, gd, strong=False)
    c2 = Character.from_dict(c.to_dict())
    for f in ("skooma_addiction", "skooma_high_until", "skooma_last_dose_hour",
              "skooma_attr_bonus", "skooma_skill_bonus"):
        assert getattr(c2, f) == getattr(c, f), f


def test_old_save_without_skooma_fields_loads():
    gd, c, st = _state()
    d = c.to_dict()
    for f in ("skooma_addiction", "skooma_high_until", "skooma_last_dose_hour",
              "skooma_attr_bonus", "skooma_skill_bonus"):
        d.pop(f, None)
    c2 = Character.from_dict(d)
    skooma.ensure_skooma_fields(c2, st.time, gd)
    assert c2.skooma_addiction == 0 and c2.skooma_high_until == 0
    assert c2.skooma_attr_bonus == {} and c2.skooma_skill_bonus == {}


def test_legacy_label():
    gd, c, st = _state()
    assert skooma.legacy_label(c) is None
    skooma.dose(st, gd, strong=False)                       # 沾染但未成癮
    assert skooma.legacy_label(c) == "沾染月糖"
    _addict(c, st, gd, n=5)
    assert skooma.legacy_label(c) == "斯庫瑪成癮者"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_skooma OK")
