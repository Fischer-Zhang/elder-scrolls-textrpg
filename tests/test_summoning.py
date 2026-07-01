"""召喚師深化(R105)單元測試:召喚物隨召喚主成長 + 角色定位 + 行動模式(嘲諷)+ 元素被動。

涵蓋:HP+傷害隨 conjuration 威力成長(conj25 弱·conj100 強)、summon_power 夾 CAP、
非召喚者傷害 ×1.0(byte-identical 守)、坦克嘲諷 action → 敵人 aggro(無嘲諷者不變)、
三元素 on_hit(火 dot/冰 benumb/雷 stagger)summon→敵生效、怪物→一般同伴不觸發(surgical 守)、
角色 stat 定位(坦克高血高甲 / 法師低甲)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg import formulas
from tesrpg.systems import combat, magic


def _summoner(conj, intel=100):
    gd = get_gamedata()
    c = build_character(gd, name="召", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills["conjuration"] = conj
    c.attributes["intelligence"] = intel
    c.magicka = c.max_magicka = 500
    c.fatigue = c.max_fatigue = 200
    return gd, c


def _summon(gd, c, spell="conjure_familiar", seed=1):
    battle = {"allies": []}
    magic.cast(c, gd, spell, RNG(seed), battle=battle, state=None)
    return battle["allies"][0]


# --- 成長軸 ----------------------------------------------------------------
def test_summon_scales_with_conjuration_skill():
    gd, c25 = _summoner(25)
    gd, c100 = _summoner(100)
    a25 = _summon(gd, c25)
    a100 = _summon(gd, c100)
    assert a100.max_health > a25.max_health, "召喚物 HP 應隨 conjuration 成長"
    assert a100.summon_power > a25.summon_power
    # 傷害側也成長(summon_power 乘子)
    assert getattr(a100, "summon_power", 1.0) > getattr(a25, "summon_power", 1.0)


def test_summon_power_capped():
    gd, c = _summoner(100, intel=100)
    # 極端法術威力堆疊也不超過 CAP
    a = _summon(gd, c)
    assert a.summon_power <= formulas.SUMMON_POWER_CAP + 1e-9


def test_summon_power_stamped_and_scales_damage():
    gd, c = _summoner(100)
    a = _summon(gd, c, spell="conjure_flame_atronach")
    assert hasattr(a, "summon_power") and a.summon_power > 1.0
    # 同一隻,summon_power 越高傷害越高(對照 ×1.0)
    enemy = combat.spawn_creature(gd, "bandit", RNG(2)); enemy.max_health = enemy.health = 9999
    atk = dict(a.attacks[1])   # 非 on_hit 的純傷害招(熔岩噴發)
    combat.resolve_attack(a, enemy, gd, RNG(3), attack=atk)
    scaled = enemy.health
    enemy2 = combat.spawn_creature(gd, "bandit", RNG(2)); enemy2.max_health = enemy2.health = 9999
    a.summon_power = 1.0
    combat.resolve_attack(a, enemy2, gd, RNG(3), attack=dict(a.attacks[1]))
    assert (9999 - scaled) > (9999 - enemy2.health), "summon_power>1 應打得更痛"


def test_non_summon_damage_byte_identical():
    """🔴 byte-identical 守:一般怪物無 summon_power 屬性 → resolve_attack ×1.0(getattr 預設)。"""
    gd = get_gamedata()
    e = combat.spawn_creature(gd, "bandit", RNG(1))
    assert not hasattr(e, "summon_power")   # 一般怪無此屬性 → resolve_attack 讀 getattr 預設 1.0


# --- 坦克嘲諷 --------------------------------------------------------------
def test_taunt_action_and_aggro():
    gd = get_gamedata()
    dremora = gd.bestiary["summoned_dremora"]
    assert any(a.get("taunt") for a in dremora["attacks"]), "魔人 moveset 應含嘲諷 action"
    # 嘲諷態 → 敵人高機率改打嘲諷者
    gd2, player = _summoner(50)
    tank = combat.spawn_creature(gd, "summoned_dremora", RNG(5))
    tank.active_effects.append({"kind": "taunt", "turns": 3})
    hit_tank = sum(1 for i in range(400) if combat.pick_player_side_target(player, [tank], RNG(i)) is tank)
    assert hit_tank / 400 > 0.6, "嘲諷中的坦克應吸引多數敵人火力"


def test_no_taunt_target_dist_unchanged():
    """🔴 byte-identical 守:無嘲諷者 → pick_player_side_target 不擲額外 rng(空清單短路)。"""
    gd = get_gamedata()
    _, player = _summoner(50)
    ally = combat.spawn_creature(gd, "summoned_familiar", RNG(5))   # 無 taunt 效果
    hit_ally = sum(1 for i in range(400) if combat.pick_player_side_target(player, [ally], RNG(i)) is ally)
    assert 0.35 < hit_ally / 400 < 0.55, "無嘲諷 → 維持約 45% 同伴目標率(既有行為)"


# --- 三元素 on_hit ---------------------------------------------------------
def test_elemental_on_hit_fires_summon_vs_enemy():
    gd = get_gamedata()
    cases = [("summoned_atronach", "dot"), ("summoned_frost_atronach", "benumb"), ("summoned_storm_atronach", "stagger")]
    for tid, expect in cases:
        got = set()
        for seed in range(50):
            a = combat.spawn_creature(gd, tid, RNG(seed)); a.summon_turns = 6
            enemy = combat.spawn_creature(gd, "bandit", RNG(seed + 100)); enemy.max_health = enemy.health = 999
            combat.resolve_attack(a, enemy, gd, RNG(seed + 200), attack=dict(a.attacks[0]))
            got.update(e["kind"] for e in enemy.active_effects)
        assert expect in got, f"{tid} 主招 on_hit 應施加 {expect}(summon→敵)"


def test_on_hit_not_fired_monster_vs_ally():
    """🔴 surgical 守:一般怪物(無 summon_turns)攻擊一般同伴 → 不觸發 on_hit(不改既有 monster→ally)。"""
    gd = get_gamedata()
    # 造一個帶 on_hit 的怪物攻擊、打一個非玩家非召喚的同伴 → on_hit 不上
    monster = combat.spawn_creature(gd, "summoned_atronach", RNG(1))   # 借其帶 on_hit 的招
    monster.summon_turns = None   # 視為一般怪物(非召喚)
    ally = combat.spawn_creature(gd, "summoned_familiar", RNG(2)); ally.summon_turns = None
    ally.max_health = ally.health = 999
    for seed in range(40):
        combat.resolve_attack(monster, ally, gd, RNG(seed), attack=dict(monster.attacks[0]))
    assert all(e["kind"] != "dot" for e in ally.active_effects), "非召喚攻擊者→同伴不施 on_hit"


# --- 角色定位 --------------------------------------------------------------
def test_role_stat_profiles():
    gd = get_gamedata()
    b = gd.bestiary
    # 坦克:高血高甲
    assert b["summoned_dremora"]["max_health"] >= 60 and b["summoned_dremora"]["armor_rating"] >= 20
    # 法師玻璃大砲:低甲
    for tid in ("summoned_atronach", "summoned_frost_atronach", "summoned_storm_atronach"):
        assert b[tid]["armor_rating"] <= 8, f"{tid} 應為低甲玻璃大砲"


# --- R106 Phase A:角色擴展(support/control/bound)------------------------
def test_summon_support_casting_heals_ally():
    """治療精靈(bestiary spells)走 summon_support_act 治療受傷盟友(讀 bestiary·非 companions.json)。"""
    gd, c = _summoner(100)
    healer = _summon(gd, c, spell="conjure_healer")
    assert healer.template_id == "summoned_healer"
    wounded = combat.spawn_creature(gd, "summoned_dremora", RNG(9))
    wounded.summon_turns = 6
    wounded.health = wounded.max_health // 3
    before = wounded.health
    res = magic.summon_support_act(healer, c.player if hasattr(c, "player") else c, [healer, wounded], gd)
    assert res is not None, "治療精靈應施治療"
    assert wounded.health > before, "受傷盟友應被治療"


def test_control_summon_on_hit_fear_weaken():
    gd = get_gamedata()
    got = set()
    for s in range(60):
        t = combat.spawn_creature(gd, "summoned_terror", RNG(s)); t.summon_turns = 6
        en = combat.spawn_creature(gd, "bandit", RNG(s + 11)); en.max_health = en.health = 999
        combat.resolve_attack(t, en, gd, RNG(s + 71), attack=dict(t.attacks[0]))
        combat.resolve_attack(t, en, gd, RNG(s + 81), attack=dict(t.attacks[1]))
        got.update(x["kind"] for x in en.active_effects)
    assert "fear" in got and "weaken" in got, "恐懼幽靈 on_hit 應施 fear + weaken"


def test_bound_weapon_archetype_differentiation():
    gd, c = _summoner(80)
    p = c

    def _cast_bound(spell):
        p.active_effects = []
        magic.cast(p, gd, spell, RNG(1), state=None)
        return [e for e in p.active_effects if e.get("kind") == "bound_weapon"][0]

    # bound_sword 無 archetype 控場;bound_mace 命中擊暈 stagger
    assert _cast_bound("bound_sword").get("archetype") == "sword"
    assert _cast_bound("bound_mace").get("archetype") == "mace"

    def _stagger_rate(spell, n=60):
        _cast_bound(spell)
        hits = 0
        for s in range(n):
            e = combat.spawn_creature(gd, "bandit", RNG(s)); e.max_health = e.health = 9999
            combat.resolve_attack(p, e, gd, RNG(s + 100))
            if any(x["kind"] == "stagger" for x in e.active_effects):
                hits += 1
        return hits

    assert _stagger_rate("bound_mace") > 0, "束縛釘錘應會擊暈(mace stagger)"
    assert _stagger_rate("bound_sword") == 0, "束縛長劍不擊暈(sword 無內建 stagger)"


def test_bound_greatsword_hits_harder_than_sword():
    gd, c = _summoner(80)
    p = c

    def _maxdmg(spell):
        p.active_effects = []
        magic.cast(p, gd, spell, RNG(1), state=None)
        best = 0
        for s in range(40):
            e = combat.spawn_creature(gd, "bandit", RNG(s)); e.max_health = e.health = 9999
            combat.resolve_attack(p, e, gd, RNG(s + 200))
            best = max(best, 9999 - e.health)
        return best

    assert _maxdmg("bound_greatsword") > _maxdmg("bound_sword"), "束縛巨劍(mag20)應比束縛長劍(mag14)痛"


# --- R106 Phase B:conjuration 50 身份分岔(咒靈共鳴 / 束縛精通)--------------
def test_bound_mastery_amps_damage_and_duration():
    from tesrpg.systems import mastery

    def _bound(pick):
        _, cc = _summoner(80)
        if pick:
            mastery.choose(cc, get_gamedata(), "conjuration_50", pick)
        cc.active_effects = []
        magic.cast(cc, get_gamedata(), "bound_sword", RNG(1), state=None)
        bw = [e for e in cc.active_effects if e["kind"] == "bound_weapon"][0]
        best = 0
        for s in range(40):
            e = combat.spawn_creature(get_gamedata(), "bandit", RNG(s)); e.max_health = e.health = 9999
            combat.resolve_attack(cc, e, get_gamedata(), RNG(s + 300)); best = max(best, 9999 - e.health)
        return bw["turns"], best

    t0, d0 = _bound(None)
    t1, d1 = _bound("bound_mastery")
    assert t1 == t0 + 2, "束縛精通 +2 回合時程"
    assert d1 > d0, "束縛精通 +傷害"


def test_summon_casting_boosts_support_power_and_cooldown():
    from tesrpg.systems import mastery
    gd, c = _summoner(100)
    assert mastery.summon_casting_mod(c, gd) == {}   # 未選 → 預設
    mastery.choose(c, gd, "conjuration_50", "summon_casting")
    mod = mastery.summon_casting_mod(c, gd)
    assert mod.get("power") == 1.0 and mod.get("cooldown") == 1


def test_conjuration_50_redesign_retires_old_choice():
    """R106:conjuration_50 改身份節點 → 舊 warding_focus/efficient_summon 選擇走 ensure 退 pending(零存檔欄)。"""
    from tesrpg.systems import progression
    gd, c = _summoner(100)
    c.mastery_choices["conjuration_50"] = "warding_focus"   # 舊選(已移除)
    progression.ensure_mastery_choices(c, gd)
    assert "conjuration_50" not in c.mastery_choices, "舊 warding_focus 選擇應退 pending(可重選)"


# --- R106C 靈魂 token 死靈經濟 --------------------------------------------
def test_soul_token_gain_per_kill_and_harvest():
    from tesrpg.systems import necromancy, mastery
    gd, c = _summoner(100)
    c.soul_tokens = 0
    r = necromancy.harvest_and_recover(c, gd, 3, [])
    assert c.soul_tokens == 3 and r["gained"] == 3 and r["recovered"] == 0
    # 亡者收集 → 每擊殺額外 +1(共 ×2)
    mastery.choose(c, gd, "conjuration_75", "soul_harvest")
    c.soul_tokens = 0
    necromancy.harvest_and_recover(c, gd, 3, [])
    assert c.soul_tokens == 6, "亡者收集:3 kills × (1+1)"


def test_no_token_gain_for_non_conjurer():
    """死靈經濟限召喚系:base_skill(conjuration) < 25 的純戰士不積 token(防全 build 漏出)。"""
    from tesrpg.systems import necromancy
    gd = get_gamedata()
    w = build_character(gd, name="戰", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    w.skills["conjuration"] = 5
    w.soul_tokens = 0
    r = necromancy.harvest_and_recover(w, gd, 5, [])
    assert w.soul_tokens == 0 and r["gained"] == 0 and r["message"] is None
    # 達門檻(25)即積
    w.skills["conjuration"] = 25
    necromancy.harvest_and_recover(w, gd, 3, [])
    assert w.soul_tokens == 3


def test_recover_only_surviving_true_undead():
    from tesrpg.systems import necromancy
    gd, c = _summoner(100)
    c.soul_tokens = 0
    alive = combat.spawn_creature(gd, "reanimated_thrall", RNG(1)); alive._undead = True
    dead = combat.spawn_creature(gd, "reanimated_thrall", RNG(2)); dead._undead = True; dead.health = 0
    atronach = combat.spawn_creature(gd, "summoned_atronach", RNG(3))   # 非亡者:無 _undead
    r = necromancy.harvest_and_recover(c, gd, 0, [alive, dead, atronach])
    assert r["recovered"] == 1 and c.soul_tokens == 1, "只回收倖存的真·亡者"


def test_raise_thrall_spawns_undead_and_spends_token():
    gd, c = _summoner(100)
    c.soul_tokens = 5
    c.spells.append("raise_thrall")
    battle = {"allies": []}
    ev = magic.cast(c, gd, "raise_thrall", RNG(1), battle=battle)
    assert ev["ok"]
    ally = battle["allies"][0]
    assert getattr(ally, "_undead", False) and ally.summon_turns is not None
    assert c.soul_tokens == 3, "5 − 2 token"
    # token 不足 → 退費失敗(token/magicka 皆不扣)
    c.soul_tokens = 1
    mk_before = c.magicka
    battle2 = {"allies": []}
    ev2 = magic.cast(c, gd, "raise_thrall", RNG(2), battle=battle2)
    assert not ev2["ok"] and len(battle2["allies"]) == 0
    assert c.soul_tokens == 1 and c.magicka == mk_before


def test_undead_field_cap_blocks_over_summon():
    from tesrpg.systems import necromancy
    gd, c = _summoner(100)
    c.soul_tokens = 99
    c.spells.append("raise_thrall")
    battle = {"allies": []}
    cap = necromancy.undead_field_cap(c)   # base 3
    for _ in range(cap):
        magic.cast(c, gd, "raise_thrall", RNG(1), battle=battle)
    assert necromancy.undead_count(battle) == cap
    ev = magic.cast(c, gd, "raise_thrall", RNG(2), battle=battle)   # 超過軍團上限
    assert not ev["ok"] and necromancy.undead_count(battle) == cap


def test_reanimate_thrall_enhances_and_costs_token():
    gd, c = _summoner(100)
    c.spells += ["reanimate_corpse", "reanimate_thrall"]

    def _corpse():
        e = combat.spawn_creature(gd, "bandit", RNG(5)); e.health = 0
        return e

    c.soul_tokens = 5
    b1 = {"allies": []}
    magic.cast(c, gd, "reanimate_corpse", RNG(1), battle=b1, corpses=[_corpse()])
    base_hp = b1["allies"][0].max_health
    assert c.soul_tokens == 5, "base 亡者復生不吃 token"
    b2 = {"allies": []}
    magic.cast(c, gd, "reanimate_thrall", RNG(1), battle=b2, corpses=[_corpse()])
    enh = b2["allies"][0]
    assert enh.max_health > base_hp, "強化復生 1.0x > base 0.6x"
    assert c.soul_tokens == 4 and getattr(enh, "_undead", False)


def test_undead_mastery_boosts_only_true_undead():
    from tesrpg.systems import mastery
    gd, c = _summoner(100)
    mastery.choose(c, gd, "conjuration_100", "undead_dominion")
    c.soul_tokens = 9
    c.spells += ["raise_thrall", "conjure_flame_atronach"]
    b1 = {"allies": []}
    magic.cast(c, gd, "raise_thrall", RNG(1), battle=b1)
    thrall = b1["allies"][0]
    # 真·亡者:summon_power = 1 × (1+0.2)〔只吃亡者統御·刻意不吃 conjuration 縮放〕
    assert abs(thrall.summon_power - 1.2) < 1e-9
    b2 = {"allies": []}
    magic.cast(c, gd, "conjure_flame_atronach", RNG(1), battle=b2)
    atro = b2["allies"][0]
    assert not getattr(atro, "_undead", False), "元素召喚物非真·亡者"
    assert atro.summon_power > 1.2, "atronach 仍吃 conjuration 縮放(未被 dominion 影響)"


def test_soul_harvest_and_undead_mastery_getters():
    from tesrpg.systems import mastery
    gd, c = _summoner(100)
    assert mastery.soul_harvest_bonus(c, gd) == 0 and mastery.undead_mastery_mod(c, gd) == {}
    mastery.choose(c, gd, "conjuration_75", "soul_harvest")
    mastery.choose(c, gd, "conjuration_100", "undead_dominion")
    assert mastery.soul_harvest_bonus(c, gd) == 1
    um = mastery.undead_mastery_mod(c, gd)
    assert um["hp_bonus"] == 0.3 and um["dmg_bonus"] == 0.2


def test_conjuration_75_100_redesign_retires_old_choices():
    from tesrpg.systems import progression
    gd, c = _summoner(100)
    c.mastery_choices["conjuration_75"] = "warding_summon"   # 舊選(已移除)
    c.mastery_choices["conjuration_100"] = "twin_summon"     # 舊選(已移除)
    progression.ensure_mastery_choices(c, gd)
    assert "conjuration_75" not in c.mastery_choices
    assert "conjuration_100" not in c.mastery_choices


def test_necromancy_spells_exist_and_reachable():
    gd, _ = _summoner(100)
    for sid in ("raise_thrall", "reanimate_thrall"):
        assert sid in gd.spells
    assert "reanimated_thrall" in gd.bestiary
    hubs = [lid for lid, l in gd.world["locations"].items()
            if "raise_thrall" in l.get("spell_stock", [])]
    assert len(hubs) >= 4, "召喚重鎮 spell_stock 應含 raise_thrall(可達)"


# --- R106C 永久死靈升級選單(C2)-------------------------------------------
def test_necromancy_permanent_upgrades_buy_and_cap():
    from tesrpg.systems import necromancy
    gd, c = _summoner(100)
    c.soul_tokens = 20
    c.necro_upgrades = {}
    r = necromancy.buy_upgrade(c, gd, "undead_armor")
    assert r["ok"] and necromancy.undead_armor_bonus(c) == 2 and c.soul_tokens == 17   # step 2
    for _ in range(3):                       # 買滿 4 級 → 夾 NECRO_ARMOR_CAP(+8)
        necromancy.buy_upgrade(c, gd, "undead_armor")
    assert necromancy.undead_armor_bonus(c) == necromancy.NECRO_ARMOR_CAP == 8
    assert not necromancy.buy_upgrade(c, gd, "undead_armor")["ok"], "已滿級不可再買"
    base_cap = necromancy.undead_field_cap(c)
    necromancy.buy_upgrade(c, gd, "undead_cap")
    assert necromancy.undead_field_cap(c) == base_cap + 1
    c.soul_tokens = 0
    assert not necromancy.buy_upgrade(c, gd, "grave_thrift")["ok"], "token 不足不可買"
    assert necromancy.upgrade_level(c, "grave_thrift") == 0


def test_undead_armor_flows_into_combat_armor_rating():
    from tesrpg.systems import necromancy
    gd, c = _summoner(100)
    c.necro_upgrades = {}
    base = combat._armor_rating(c, gd)
    c.necro_upgrades = {"undead_armor": 3}   # 3 × step 2 = +6 護甲
    assert combat._armor_rating(c, gd) == base + 6


def test_grave_thrift_reduces_token_cost():
    from tesrpg.systems import necromancy
    gd, c = _summoner(100)
    assert necromancy.spend_cost(c, 2) == 2
    c.necro_upgrades = {"grave_thrift": 1}
    assert necromancy.spend_cost(c, 2) == 1   # −1
    assert necromancy.spend_cost(c, 1) == 1   # floor 1
    assert necromancy.spend_cost(c, 0) == 0   # 無 token_cost 不折


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_summoning OK")
