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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_summoning OK")
