"""吸血熱 / 吸血鬼化的單元測試(A 狀態機 + B 戰鬥身分 + C 詛咒 + E 開局)。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, powers, vampirism


def _state(race="imperial", origin=None, seed=1, hour=12):
    gd = get_gamedata()
    c = build_character(gd, name="V", sex="male", race=race, birthsign="warrior",
                        class_id="warrior", origin_id=origin)
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


# --- A:感染 → 潛伏 → 轉化 -------------------------------------------------
def test_infection_incubates_then_turns():
    gd, c, st = _state()
    assert vampirism.susceptible(c)
    assert vampirism.infect(c, st) is True
    assert vampirism.is_infected(c) and not c.is_vampire
    assert vampirism.infect(c, st) is False        # 已潛伏 → 再感染無效

    vampirism.update(st, gd)                        # 未滿潛伏期 → 還沒轉化
    assert not c.is_vampire
    st.time.advance(vampirism.INCUBATION_DAYS * 24)
    evs = vampirism.update(st, gd)
    assert c.is_vampire and not vampirism.is_infected(c)
    assert any(e["kind"] == "turn" for e in evs)
    assert vampirism.stage(c, st) == 0             # 轉化當下視為剛進食


def test_stage_rises_with_hunger_and_feeding_resets():
    gd, c, st = _state(origin="nightborn")
    vampirism.update(st, gd)
    assert c.is_vampire and vampirism.stage(c, st) == 0
    st.time.advance(vampirism.STAGE_DAYS * vampirism.MAX_STAGE * 24)   # 餓到頂
    vampirism.update(st, gd)
    assert vampirism.stage(c, st) == vampirism.MAX_STAGE
    assert c.vampire_stage == vampirism.MAX_STAGE
    res = vampirism.feed(st, gd)
    assert res["ok"] and vampirism.stage(c, st) == 0


# --- 疾病抗性削弱感染機率(combat 感染擲骰)------------------------------
def test_disease_resist_blocks_infection():
    gd, _, _ = _state()
    bat = combat.spawn_creature(gd, "vampire_fledgling", RNG(0))
    bat.attack = {**bat.attack, "infect": 1.0, "skill": 100, "damage": 1}

    def infect_hits(race):
        c = build_character(gd, name="X", sex="male", race=race,
                            birthsign="warrior", class_id="warrior")
        c.attributes["agility"] = 5            # 壓低閃避,讓多半命中
        hits = 0
        for i in range(60):
            ev = combat.resolve_attack(bat, c, gd, RNG(i))
            if ev.get("infected"):
                hits += 1
        return hits

    # 帝國人無疾病抗性 → 易感;亞龍人疾病抗性 75 → 感染機率大幅降低(但非完全免疫)
    assert infect_hits("imperial") > infect_hits("argonian")


# --- B:階級加成只進有效值、不進 base;火焰弱點 -------------------------
def test_stage_bonus_is_effective_not_base():
    gd, c, st = _state(origin="nightborn")
    vampirism.update(st, gd)                       # 先初始化進食日
    fatigue0 = c.max_fatigue                        # 加成前的體力上限(折入自 derived_resources)
    st.time.advance(vampirism.STAGE_DAYS * 3 * 24)
    vampirism.update(st, gd)
    assert vampirism.stage(c, st) == 3
    assert c.attr("strength") == c.base_attr("strength") + 15
    assert c.skill("sneak") == c.base_skill("sneak") + 15
    # 火焰由抗性轉弱點(負抗性 → 傷害放大),且免疫疾病
    resist = magic.entity_resist(c, gd)
    assert resist.get("fire", 0) < 0 and resist.get("disease", 0) >= 100
    assert c.max_fatigue > fatigue0                 # 力量/意志加成 → 體力上限上升


def test_vampire_power_overrides_and_drains():
    gd, c, st = _state(origin="nightborn")
    vampirism.update(st, gd)
    assert powers.power_id(c, gd) == "vampiric_drain"
    bat = combat.spawn_creature(gd, "wolf", RNG(0))
    bat.health = 100
    c.health = 10
    powers.use(c, st, gd, target=bat)
    assert bat.health < 100 and c.health > 10   # 汲取敵血、回復己身


# --- C:陽光灼傷 ---------------------------------------------------------
def test_sun_burns_by_day_not_night_or_dungeon():
    gd, c, st = _state(origin="nightborn")
    vampirism.update(st, gd)                      # 先初始化進食日
    st.time.advance(vampirism.STAGE_DAYS * 24)   # 升到階級 1,陽光開始灼傷
    vampirism.update(st, gd)
    c.location_id = "imperial_road"               # 戶外(wilderness)
    st.time.hour = 12
    c.health = c.max_health
    burned = vampirism.expose_to_sun(st, gd, 4)
    assert burned > 0 and c.health < c.max_health

    c.health = c.max_health                       # 深夜不灼傷
    st.time.hour = 2
    assert vampirism.expose_to_sun(st, gd, 4) == 0

    c.location_id = "ashfall_barrow"              # 地城遮蔽日光
    st.time.hour = 12
    assert vampirism.expose_to_sun(st, gd, 4) == 0

    # 低血 + 大量日照仍夾限至 health>=1,不在選單層曬死(紅線:死亡只應來自戰鬥;折入自 sun_never_kills_in_menu)
    c.location_id = "imperial_road"
    st.time.hour = 12
    c.health = 3
    vampirism.expose_to_sun(st, gd, 12)           # 12 小時日照 dmg 遠大於 2 → 觸發夾限路徑
    assert c.health >= 1


def test_shunned_at_high_stage():
    gd, c, st = _state(origin="nightborn")
    vampirism.update(st, gd)
    assert not vampirism.is_shunned(c, st)        # 剛進食(階級 0)可融入
    st.time.advance(vampirism.STAGE_DAYS * vampirism.SHUN_STAGE * 24)
    vampirism.update(st, gd)
    assert vampirism.is_shunned(c, st)            # 高階被世人拒絕


# --- E:開局 + 存檔 + 結算 + 向後相容 -----------------------------------
def test_save_roundtrip_preserves_vampire_state():
    gd, c, st = _state(origin="nightborn")
    vampirism.update(st, gd)
    st.time.advance(vampirism.STAGE_DAYS * 2 * 24)
    vampirism.update(st, gd)
    c2 = Character.from_dict(c.to_dict())
    for f in ("is_vampire", "vampire_infected_day", "vampire_fed_day", "vampire_stage",
              "vampire_attr_bonus", "vampire_skill_bonus", "vampire_resist"):
        assert getattr(c2, f) == getattr(c, f), f


def test_old_save_without_vampire_fields_loads():
    gd, c, _ = _state()
    d = c.to_dict()
    for f in ("is_vampire", "vampire_infected_day", "vampire_fed_day", "vampire_stage",
              "vampire_attr_bonus", "vampire_skill_bonus", "vampire_resist"):
        d.pop(f, None)
    c2 = Character.from_dict(d)
    assert c2.is_vampire is False and c2.vampire_infected_day == -1


def test_cure_quest_flow_and_repeatable():
    from tesrpg.systems import quests, inventory
    gd, c, st = _state(origin="nightborn")
    vampirism.update(st, gd)
    qid = "cure_vampirism"
    quests.accept_quest(c, gd, qid)
    assert quests.is_active(c, qid)
    inventory.add_item(c, "garlic", 4); quests.check_completion(c, gd)      # 階段1
    inventory.add_item(c, "nightshade", 3); quests.check_completion(c, gd)  # 階段2
    quests.record_kill(c, "vampire_lord"); quests.check_completion(c, gd)   # 階段3
    assert quests.is_done(c, qid)
    assert inventory.count_item(c, "garlic") == 0                # 採集物上繳消耗
    # 推進到階級 3 以驗證解咒清除階級加成(quest 完成判定看 completed_quests,不受時間影響)
    st.time.advance(vampirism.STAGE_DAYS * 3 * 24)
    vampirism.update(st, gd)
    assert c.is_vampire and c.attr("strength") > c.base_attr("strength")
    assert powers.power_id(c, gd) == "vampiric_drain"
    # 儀式解咒(=action_vampire_cure 的核心)
    vampirism.cure(c, gd)
    c.completed_quests.remove(qid)
    assert not c.is_vampire and not quests.is_done(c, qid)       # 可重複求咒
    assert c.attr("strength") == c.base_attr("strength")       # 階級加成清除(折入自 cure_clears_vampire_state)
    assert c.vampire_resist == {} and c.vampire_attr_bonus == {}
    assert powers.power_id(c, gd) != "vampiric_drain"          # 星座之力回歸
    assert vampirism.susceptible(c)                             # 日後仍可再被感染


def test_legacy_label():
    gd, c, st = _state(origin="nightborn")
    vampirism.update(st, gd)
    assert "吸血鬼" in vampirism.legacy_label(c)
    gd, c2, st2 = _state()
    assert vampirism.legacy_label(c2) is None
    vampirism.infect(c2, st2)
    assert vampirism.legacy_label(c2) == "染上吸血熱"


def run():
    test_infection_incubates_then_turns()
    test_stage_rises_with_hunger_and_feeding_resets()
    test_disease_resist_blocks_infection()
    test_stage_bonus_is_effective_not_base()
    test_vampire_power_overrides_and_drains()
    test_sun_burns_by_day_not_night_or_dungeon()
    test_shunned_at_high_stage()
    test_save_roundtrip_preserves_vampire_state()
    test_old_save_without_vampire_fields_loads()
    test_cure_quest_flow_and_repeatable()
    test_legacy_label()


if __name__ == "__main__":
    run()
    print("test_vampirism OK")
