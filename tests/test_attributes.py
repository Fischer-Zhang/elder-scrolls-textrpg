"""補屬性功能缺口(意志 / 幸運 名實相符)的單元測試。

鐵律:所有係數在屬性 = BASE_ATTRIBUTE(40)時回中性值(=改前行為)。
"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, dungeon, loot, magic


def _char(willpower=40, luck=40):
    gd = get_gamedata()
    c = build_character(gd, name="A", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    c.attributes["willpower"] = willpower
    c.attributes["luck"] = luck
    return gd, c


# --- base-40 中性 + 縮放 + 夾限 -----------------------------------------
def test_factors_neutral_at_base():
    b = formulas.BASE_ATTRIBUTE
    # 中性端(base-40)
    assert formulas.magicka_regen_combat(b) == 0
    assert formulas.magicka_regen_rest_factor(b) == 1.0
    assert formulas.mind_resist_chance(b) == 0.0
    assert formulas.luck_loot_factor(b) == 1.0
    assert formulas.luck_fortune(b) == 0.0
    # 縮放端(>base)+ 上界夾限
    assert formulas.magicka_regen_combat(100) > 0
    assert formulas.magicka_regen_rest_factor(100) > 1.0
    assert 0 < formulas.mind_resist_chance(100) <= formulas.MIND_RESIST_CAP
    assert 1.0 < formulas.luck_loot_factor(100) <= formulas.LUCK_LOOT_CAP
    assert 0 < formulas.luck_fortune(100) <= formulas.LUCK_FORTUNE_CAP
    # 夾限端(超大值 == 各 CAP)
    assert formulas.magicka_regen_combat(999) == formulas.MAGICKA_REGEN_COMBAT_CAP
    assert formulas.luck_loot_factor(999) == formulas.LUCK_LOOT_CAP
    assert formulas.mind_resist_chance(999) == formulas.MIND_RESIST_CAP


# --- 幸運:戰利豐厚 -----------------------------------------------------
def test_luck_loot_factor_in_resolve():
    # 高倍率:低機率必掉 + 金幣放大(確定性)
    r = loot.resolve_loot([{"gold": [10, 10]}, {"item": "gold_ring", "chance": 0.5}], RNG(1), luck_factor=2.0)
    assert r["gold"] == 20                              # 10 × 2.0
    assert ("gold_ring", 1) in r["items"]              # 0.5 × 2.0 → 1.0 → 必掉
    # 零機率排除側(併自 test_world.test_loot_resolver):即使倍率放大,chance 0.0 仍濾掉
    assert ("ruby", 1) not in loot.resolve_loot(
        [{"item": "ruby", "chance": 0.0}], RNG(1), luck_factor=2.0)["items"]
    # 中性 1.0:不放大(怪物中性掉落不變)
    assert loot.resolve_loot([{"gold": [10, 10]}], RNG(1), luck_factor=1.0)["gold"] == 10


def test_grant_loot_uses_player_luck():
    gd, c = _char(luck=100)
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.loot_gold = [100, 100]; foe.loot_table = []
    res = combat.grant_loot(c, foe, gd, RNG(1))
    assert res["gold"] > 100                            # 幸運放大金幣(100×factor>100)


# --- 幸運:時來運轉(撬鎖/逃跑) ----------------------------------------
def test_luck_fortune_lockpick_and_flee():
    gd, lo = _char(luck=40)
    _, hi = _char(luck=100)
    assert (dungeon.effective_pick_lock_chance(hi, gd, 50)
            > dungeon.effective_pick_lock_chance(lo, gd, 50))   # 高幸運撬鎖率更高
    # 逃跑率:統計上高幸運更易逃
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    flee_lo = sum(1 for s in range(300) if combat.try_flee(_char(luck=40)[1], foe, RNG(s)))
    flee_hi = sum(1 for s in range(300) if combat.try_flee(_char(luck=100)[1], foe, RNG(s)))
    assert flee_hi > flee_lo


# --- 意志:精神韌性(抗恐懼/麻痺) ------------------------------------
def test_mind_resist_helper():
    gd, base = _char(willpower=40)
    _, tough = _char(willpower=100)
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    assert not magic.resisted_mind(base, "fear", RNG(1))       # base-40 → 抗性 0,永不抗
    assert not magic.resisted_mind(tough, "dot", RNG(1))       # 非心智狀態 → 不抗
    assert not magic.resisted_mind(foe, "fear", RNG(1))        # 非玩家(怪物)→ 不抗
    resists = sum(1 for s in range(300) if magic.resisted_mind(tough, "paralyze", RNG(s)))
    assert resists > 0                                          # 高意志統計上會抗一部分


def test_combat_fear_resisted_by_willpower():
    gd, _ = _char()
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.strength = 80; foe.agility = 80                        # 提高命中率,確保多數攻擊命中
    foe.attack = {"name": "懾魂", "damage": 1, "skill": 90,
                  "on_hit": {"status": "fear", "element": None, "magnitude": 0, "turns": 2, "chance": 1.0}}
    base_feared = tough_feared = 0
    for s in range(120):
        b = _char(willpower=40)[1]
        combat.resolve_attack(foe, b, gd, RNG(s))
        base_feared += magic.is_feared(b)
        t = _char(willpower=100)[1]
        combat.resolve_attack(foe, t, gd, RNG(s))
        tough_feared += magic.is_feared(t)
    assert base_feared > tough_feared                          # 高意志較不易被控場


def run():
    test_factors_neutral_at_base()
    test_luck_loot_factor_in_resolve()
    test_grant_loot_uses_player_luck()
    test_luck_fortune_lockpick_and_flee()
    test_mind_resist_helper()
    test_combat_fear_resisted_by_willpower()


if __name__ == "__main__":
    run()
    print("test_attributes OK")
