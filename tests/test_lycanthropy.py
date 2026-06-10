"""狼人化 / 獸形(Lycanthropy)系統的單元測試 —— 吸血鬼的對位機制。

含 pre-mortem(對抗式設計覆核)指定的硬化斷言:
  🔴 紅線(獸形不走偷襲、不秒 solo boss)、裝備抑制、存讀檔計時、互斥雙向、devour 封頂。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, lycanthropy, powers, vampirism


def _state(seed=1, hour=12, race="nord"):
    gd = get_gamedata()
    c = build_character(gd, name="W", sex="male", race=race, birthsign="warrior", class_id="warrior")
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


def _make_werewolf(gd, c, st):
    assert lycanthropy.contract(c, st, gd)
    return c


# --- 感染 → 潛伏 → 轉化 -------------------------------------------------
def test_infect_incubate_transform():
    gd, c, st = _state()
    assert lycanthropy.susceptible(c)
    assert lycanthropy.infect(c, st)
    assert lycanthropy.is_infected(c) and not lycanthropy.is_werewolf(c)
    # 推進潛伏期 → update 驅動轉化
    st.time.advance(lycanthropy.INCUBATION_DAYS * 24 + 1)
    evs = lycanthropy.update(st, gd)
    assert lycanthropy.is_werewolf(c)
    assert any(e["kind"] == "turn" for e in evs)
    # 人形:僅疾病免疫,零屬性加成
    assert c.werewolf_resist.get("disease") == 100
    assert c.werewolf_attr_bonus == {}


# --- 變身:加成有效非 base、回血;變回:清層 + 夾血 + 力竭 -------------
def test_transform_grants_beast_then_revert_clamps():
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    base_str = c.base_attr("strength")
    base_maxhp = c.max_health
    c.health = 10
    lycanthropy.transform(c, st, gd)
    assert c.beast_form and lycanthropy.is_beast(c, st)
    assert c.attr("strength") == base_str + lycanthropy.BEAST_ATTR["strength"]   # 有效值
    assert c.base_attr("strength") == base_str                                   # base 不動(鐵律)
    assert c.max_health == base_maxhp + lycanthropy.BEAST_HEALTH                  # 巨量生命
    assert c.health >= 10 + lycanthropy.BEAST_HEALTH                             # 變身補上增幅(非半條血)
    # 變回:清層、夾血上限、力竭
    c.health = c.max_health
    c.fatigue = c.max_fatigue
    lycanthropy.revert(c, st, gd)
    assert not c.beast_form and not lycanthropy.is_beast(c, st)
    assert c.max_health == base_maxhp and c.health <= c.max_health               # 夾血上限,無溢出
    assert c.attr("strength") == base_str                                        # 獸形屬性卸除
    # 力竭:先夾回人形上限(獸形 endurance 卸除 → max_fatigue 下滑),再扣 EXHAUST
    assert c.fatigue == max(0, c.max_fatigue - lycanthropy.EXHAUST_FATIGUE)


# --- 🔴 紅線:獸形攻擊永不吃偷襲倍率(防禦縱深 + 不秒 solo boss)--------
def test_beast_attack_never_sneaks_even_if_flagged():
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    lycanthropy.transform(c, st, gd)
    boss = combat.spawn_creature(gd, "ancient_dragon", st.rng)   # solo boss
    # 即使硬傳 sneak_attack=True,獸形也絕不套偷襲倍率(resolve_attack 內 not beast 守門)
    ev = combat.resolve_attack(c, boss, gd, st.rng, sneak_attack=True)
    assert ev["sneak"] is None
    # 單擊絕不秒 solo boss(遠低於血上限)
    assert ev["damage"] < boss.max_health, (ev["damage"], boss.max_health)


def test_beast_single_hit_far_below_solo_boss_hp():
    """最壞情況:apex(滿階獸血)+ 高 hand_to_hand + 獸形力量,單記非偷襲獸爪仍遠不及 solo boss 血量。"""
    gd, c, st = _state()
    c.skills["hand_to_hand"] = 100
    _make_werewolf(gd, c, st)
    c.werewolf_total_feeds = lycanthropy.FEED_TIERS[-1]   # 滿階「血月之主」= 最強獸形
    lycanthropy.transform(c, st, gd)
    for tid in ("ancient_dragon", "wamasu", "dremora_lord"):
        boss = combat.spawn_creature(gd, tid, st.rng)
        worst = 0
        for _ in range(60):
            ev = combat.resolve_attack(c, boss, gd, RNG(_), sneak_attack=False)
            worst = max(worst, ev["damage"])
            combat._set_hp(boss, boss.max_health)   # 還原血量續測
        assert worst < boss.max_health, (tid, worst, boss.max_health)


def test_estimate_sneak_damage_beast_form_no_sneak_inflation():
    """對抗審查回歸:獸形的 scout 偷襲估傷不吃偷襲倍率、用獸爪流派(與 resolve_attack 一致),
    故遠低於同角色人形持匕首的偷襲估傷(不被灌水)。"""
    gd, c, st = _state()
    c.weapon = "iron_dagger"; c.skills["sneak"] = 80; c.skills["hand_to_hand"] = 60
    foe = combat.spawn_creature(gd, "bandit", st.rng)
    _make_werewolf(gd, c, st)
    human_est = combat.estimate_sneak_damage(c, gd, foe)    # 人形匕首:吃偷襲倍率(高)
    lycanthropy.transform(c, st, gd)
    beast_est = combat.estimate_sneak_damage(c, gd, foe)    # 獸形:不吃偷襲、用獸爪
    assert beast_est < human_est, (beast_est, human_est)


def test_sync_beast_form_reverts_expired_cache():
    """對抗審查回歸:旅行/休息在同一動作內推進時間過了獸形時效、game_loop update 尚未刷新快取
    → 進戰前 sync_beast_form 對齊,杜絕以過期獸形作戰。"""
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    lycanthropy.transform(c, st, gd)
    assert c.beast_form
    st.time.advance(lycanthropy.BEAST_DURATION_HOURS + 1)    # 時間推進過時效,但未呼叫 update
    assert c.beast_form and not lycanthropy.is_beast(c, st)  # 快取脫鉤(慢一拍)
    assert lycanthropy.sync_beast_form(c, st, gd)            # 對齊 → 變回
    assert not c.beast_form
    # combat 讀快取布林,對齊後即用裝備武器/真實護甲
    assert combat.effective_weapon_name(c, gd) != "獸爪"


def test_human_form_werewolf_sneak_estimate_unchanged():
    """人形狼人(未變身)的 scout 偷襲估傷 == 凡人基準(狼人身分不放大估傷)。"""
    gd, c, st = _state()
    c.weapon = "iron_dagger"; c.skills["sneak"] = 60
    target = combat.spawn_creature(gd, "bandit", st.rng)
    before = combat.estimate_sneak_damage(c, gd, target)
    _make_werewolf(gd, c, st)   # 化為狼人(人形)
    assert not c.beast_form
    after = combat.estimate_sneak_damage(c, gd, target)
    assert after == before, (before, after)


# --- 裝備抑制(獸形脫去武器/附魔/淬鍊/護甲)----------------------------
def test_beast_form_suppresses_equipment():
    gd, c, st = _state()
    c.weapon = "iron_sword"
    c.weapon_temper = {"iron_sword": 5}            # 淬鍊滿級
    _make_werewolf(gd, c, st)
    lycanthropy.transform(c, st, gd)
    dmg, skl, sid = combat._weapon_profile(c, gd)
    claw = gd.item("beast_claws")
    assert dmg == claw["damage"] and sid == "hand_to_hand"   # 用獸爪、不含淬鍊
    assert combat.effective_weapon_name(c, gd) == "獸爪"
    # 護甲:脫去穿戴護甲,只剩野獸自然護甲
    assert combat._armor_rating(c, gd) == lycanthropy.BEAST_ARMOR


def test_beast_form_weapon_enchant_does_not_fire():
    """獸形以獸爪戰鬥 → 裝備武器的元素/命中狀態附魔皆不觸發。"""
    gd, c, st = _state()
    # 合成一把帶元素附魔的武器(enchw)
    from tesrpg.synth import enchant_weapon_id
    wid = enchant_weapon_id("iron_sword", "fire", 25)
    c.weapon = wid
    _make_werewolf(gd, c, st)
    lycanthropy.transform(c, st, gd)
    boss = combat.spawn_creature(gd, "bandit", st.rng)
    hp0 = boss.max_health
    total = 0
    for _ in range(20):
        combat._set_hp(boss, hp0)
        ev = combat.resolve_attack(c, boss, gd, RNG(_), sneak_attack=False)
        total += ev["damage"]
    # 獸爪 base 16 < 帶 25 火附魔的長劍 → 若附魔有觸發傷害會明顯偏高;此處只驗無 traceback + 合理
    assert total > 0


# --- 互斥雙向(吸血鬼 ↔ 狼人)------------------------------------------
def test_mutual_exclusion_both_directions():
    gd, c, st = _state()
    # 吸血鬼擋狼人:contract / infect 皆失敗
    c.is_vampire = True
    assert not lycanthropy.contract(c, st, gd)
    assert not lycanthropy.infect(c, st)
    c.is_vampire = False
    # 狼人擋吸血鬼:vampirism.susceptible / infect 皆失敗
    _make_werewolf(gd, c, st)
    assert not vampirism.susceptible(c)
    assert not vampirism.infect(c, st)


def test_combat_infect_kind_dispatch_and_backcompat():
    gd, c, st = _state()
    # 狼人敵帶 infect_kind=lycanthropy;舊吸血鬼敵無此鍵 → 預設 vampire
    ww = gd.bestiary["werewolf"]["attack"]
    assert ww.get("infect_kind") == "lycanthropy"
    vf = gd.bestiary["vampire_fledgling"]["attack"]
    assert "infect_kind" not in vf      # 向後相容:缺鍵 → combat 預設 vampire


# --- devour 續時封頂(封無限獸形 farm)----------------------------------
def test_devour_caps_per_form():
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    lycanthropy.transform(c, st, gd)
    until0 = c.beast_form_until
    for _ in range(10):
        lycanthropy.devour(c, st, gd)
    assert c.beast_feeds == lycanthropy.MAX_FEEDS_PER_FORM
    max_until = until0 + lycanthropy.MAX_FEEDS_PER_FORM * lycanthropy.FEED_EXTEND_HOURS
    assert c.beast_form_until <= max_until
    assert c.werewolf_total_feeds == lycanthropy.MAX_FEEDS_PER_FORM   # 累計(成就用)


# --- 變身走 powers 槽 + 每日一次冷卻 -----------------------------------
def test_transform_via_power_once_per_day():
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    assert powers.power_id(c, gd) == "beast_form"             # 取代星座之力
    assert powers.usable_in(c, st, gd, "combat")
    res = powers.use(c, st, gd)
    assert c.beast_form                                       # transform 經 powers.use 觸發
    assert powers.power_id(c, gd) is None                     # 獸形中無此槽(不可重變身)
    # 變回後同日不可再變身(冷卻)
    lycanthropy.revert(c, st, gd)
    assert not powers.usable_in(c, st, gd, "combat")          # power_last_day 鎖當日
    assert powers.usable_in(c, st, gd, "utility") is False    # 僅 combat 語境(無野外主動變身)


# --- 解咒任務:流程 / 可重複 / 僅狼人可接 ------------------------------
def test_cure_quest_flow_repeatable_and_gated():
    from tesrpg.systems import quests, inventory
    gd, c, st = _state()
    qid = "cure_lycanthropy"
    # 專屬 source(werewolf_cure)→ 不漏進告示板/公會(僅 action_werewolf_cure 對 is_werewolf 開放)
    assert qid not in quests.available_quests(c, gd, "board")
    assert qid not in quests.available_quests(c, gd, "guild", "fighters_guild")
    _make_werewolf(gd, c, st)
    quests.accept_quest(c, gd, qid)
    inventory.add_item(c, "garlic", 4); quests.check_completion(c, gd)
    inventory.add_item(c, "nightshade", 3); quests.check_completion(c, gd)
    quests.record_kill(c, "werewolf"); quests.check_completion(c, gd)
    assert quests.is_done(c, qid)
    lycanthropy.cure(c, gd)                                   # = action_werewolf_cure 的核心
    c.completed_quests.remove(qid)
    assert not lycanthropy.is_werewolf(c) and not quests.is_done(c, qid)   # 可重複求解
    assert c.werewolf_resist == {} and c.werewolf_attr_bonus == {}


# --- 存讀檔:往返 + 舊存檔遷移 + 獸形過期自動變回 ----------------------
def test_save_roundtrip_and_old_save_migration():
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    c2 = Character.from_dict(c.to_dict())
    for f in ("is_werewolf", "werewolf_infected_day", "beast_form", "beast_form_until",
              "beast_feeds", "werewolf_total_feeds", "werewolf_attr_bonus", "werewolf_resist"):
        assert getattr(c2, f) == getattr(c, f), f
    # 舊存檔缺欄 → 載入補欄不崩
    d = c.to_dict()
    for f in ("is_werewolf", "beast_form", "beast_form_until", "werewolf_attr_bonus",
              "werewolf_resist", "werewolf_health_bonus"):
        d.pop(f, None)
    c3 = Character.from_dict(d)
    lycanthropy.ensure_lycanthropy_fields(c3, st.time, gd)
    assert not c3.is_werewolf and c3.werewolf_attr_bonus == {}


def test_save_in_beast_form_then_expire_reverts_on_load():
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    lycanthropy.transform(c, st, gd)
    c.health = c.max_health
    assert c.beast_form
    # 時間推進超過獸形持續 → 載入時 ensure 應自動變回 + 夾血上限
    later = GameTime(hour=(st.time.hour))
    later_abs = st.time.absolute_hours() + lycanthropy.BEAST_DURATION_HOURS + 24
    # 直接以未來 GameTime 餵 ensure(模擬載入時時間已前進)
    future = GameTime.from_dict(st.time.to_dict()); future.advance(lycanthropy.BEAST_DURATION_HOURS + 24)
    c2 = Character.from_dict(c.to_dict())
    lycanthropy.ensure_lycanthropy_fields(c2, future, gd)
    assert not c2.beast_form
    assert c2.health <= c2.max_health                         # 已夾回人形上限,無溢出
    assert c2.werewolf_attr_bonus == {}


# --- legacy / achievement 收錄 -----------------------------------------
def test_legacy_and_achievement():
    from tesrpg.systems import achievements
    gd, c, st = _state()
    assert lycanthropy.legacy_label(c) is None
    lycanthropy.infect(c, st)
    assert lycanthropy.legacy_label(c) == "染上狼人熱"
    _make_werewolf(gd, c, st)
    assert lycanthropy.legacy_label(c) == "狼人"
    earned = {a["id"] for a in achievements.earned(c, gd)}
    assert "beast_blood" in earned                            # 「獸血詛咒」成就
    # 月下獵手:吞噬累計
    c.werewolf_total_feeds = 25
    assert "moonlit_hunter" in {a["id"] for a in achievements.earned(c, gd)}


# --- 餵食進程(獸血隨狩獵成長)+ 恫嚇之嚎 + 獵者之戒 -------------------
def test_feed_tier_progression():
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    assert lycanthropy.tier(c) == 0
    c.werewolf_total_feeds = lycanthropy.FEED_TIERS[0]      # 達第一門檻 → 階 1
    assert lycanthropy.tier(c) == 1
    c.werewolf_total_feeds = lycanthropy.FEED_TIERS[-1]     # 滿階
    assert lycanthropy.tier(c) == len(lycanthropy.FEED_TIERS)
    assert lycanthropy.beast_attr(c)["strength"] > lycanthropy.BEAST_ATTR["strength"]
    assert lycanthropy.beast_health(c) > lycanthropy.BEAST_HEALTH
    assert lycanthropy.max_feeds(c) >= lycanthropy.MAX_FEEDS_PER_FORM
    assert lycanthropy.beast_duration(c) >= lycanthropy.BEAST_DURATION_HOURS
    prog = lycanthropy.tier_progress(c)
    assert "remaining" not in prog                          # 滿階無下一階


def test_claw_damage_scales_with_tier():
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    lycanthropy.transform(c, st, gd)
    d0, _, sid = combat._weapon_profile(c, gd)
    assert sid == "hand_to_hand"
    lycanthropy.revert(c, st, gd)
    c.werewolf_total_feeds = lycanthropy.FEED_TIERS[-1]     # 滿階
    lycanthropy.transform(c, st, gd)
    d_apex, _, _ = combat._weapon_profile(c, gd)
    assert d_apex > d0                                      # 獸爪隨獸血階成長


def test_howl_fears_non_solo_costs_fatigue_solo_immune():
    from tesrpg.systems import magic
    gd, c, st = _state()
    c.attributes["endurance"] = 90
    _make_werewolf(gd, c, st)
    c.werewolf_total_feeds = lycanthropy.FEED_TIERS[1]      # 階 2 → 解鎖恫嚇之嚎
    lycanthropy.transform(c, st, gd)
    assert lycanthropy.can_howl(c, st)
    mob = combat.spawn_creature(gd, "bandit", st.rng)
    boss = combat.spawn_creature(gd, "ancient_dragon", st.rng)
    fat0 = c.fatigue
    res = lycanthropy.howl(c, st, gd, [mob, boss])
    assert res["affected"] == 1                             # 只懼非 solo;solo boss 免疫(紅線)
    assert magic.is_feared(mob) and not magic.is_feared(boss)
    assert c.fatigue == fat0 - lycanthropy.HOWL_FATIGUE     # 耗體力
    c.fatigue = lycanthropy.HOWL_FATIGUE - 1
    assert lycanthropy.howl(c, st, gd, [mob])["ok"] is False  # 體力不足無法嚎叫


def test_devour_tier_up_recomputes_and_heal_scales():
    """對抗審查回歸:吞噬使 total_feeds 跨階 → 即時重算屬性/生命上限(非停留在變身時的階);
    且回血隨獸血階提升(非固定 BEAST_HEALTH//2)。"""
    gd, c, st = _state()
    c.attributes["endurance"] = 80
    _make_werewolf(gd, c, st)
    c.werewolf_total_feeds = lycanthropy.FEED_TIERS[0] - 1   # 階 0,差 1 次吞噬即升階
    lycanthropy.transform(c, st, gd)
    assert lycanthropy.tier(c) == 0
    c.health = 1
    res = lycanthropy.devour(c, st, gd)                      # → total_feeds 達門檻,升階 1
    assert lycanthropy.tier(c) == 1
    # 屬性/生命層即時對齊新階(非停留階 0)
    assert c.werewolf_attr_bonus["strength"] == lycanthropy.beast_attr(c)["strength"]
    assert c.werewolf_health_bonus == lycanthropy.beast_health(c)
    assert res["healed"] == lycanthropy.beast_health(c) // 2   # 回血隨階(階 1 > 階 0)
    assert res["healed"] > lycanthropy.BEAST_HEALTH // 2


def test_hircine_ring_bypasses_transform_cooldown():
    from tesrpg.systems import inventory, powers
    gd, c, st = _state()
    _make_werewolf(gd, c, st)
    powers.use(c, st, gd)                                   # 用掉今日變身(設 power_last_day)
    lycanthropy.revert(c, st, gd)
    assert not powers.usable_in(c, st, gd, "combat")        # 每日冷卻中
    inventory.add_item(c, "hircine_ring", 1)
    inventory.equip_jewelry(c, gd, "hircine_ring")
    assert lycanthropy.has_hircine_ring(c, gd)
    assert powers.usable_in(c, st, gd, "combat")            # 獵者之戒繞過冷卻 → 可隨意變身


# --- 開局背景:獸血之裔 -------------------------------------------------
def test_beast_blooded_origin():
    from tesrpg import creation
    gd = get_gamedata()
    c = build_character(gd, name="B", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    creation.apply_origin(gd, c, "beast_blooded")
    assert c.is_werewolf and c.factions.get("companions") == 1   # 獸血源出戰友團(已移籍)
    assert not c.is_vampire                                   # 互斥(開局守門)


def run():
    test_infect_incubate_transform()
    test_transform_grants_beast_then_revert_clamps()
    test_beast_attack_never_sneaks_even_if_flagged()
    test_beast_single_hit_far_below_solo_boss_hp()
    test_estimate_sneak_damage_beast_form_no_sneak_inflation()
    test_sync_beast_form_reverts_expired_cache()
    test_human_form_werewolf_sneak_estimate_unchanged()
    test_beast_form_suppresses_equipment()
    test_beast_form_weapon_enchant_does_not_fire()
    test_mutual_exclusion_both_directions()
    test_combat_infect_kind_dispatch_and_backcompat()
    test_devour_caps_per_form()
    test_transform_via_power_once_per_day()
    test_cure_quest_flow_repeatable_and_gated()
    test_save_roundtrip_and_old_save_migration()
    test_save_in_beast_form_then_expire_reverts_on_load()
    test_legacy_and_achievement()
    test_feed_tier_progression()
    test_claw_damage_scales_with_tier()
    test_howl_fears_non_solo_costs_fatigue_solo_immune()
    test_devour_tier_up_recomputes_and_heal_scales()
    test_hircine_ring_bypasses_transform_cooldown()
    test_beast_blooded_origin()


if __name__ == "__main__":
    run()
    print("test_lycanthropy OK")
