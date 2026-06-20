"""吸血鬼能力深化(R56)單元測試:夜視(夜間潛近/迴避)、社交魅惑、偽裝套裝、requires_vampire 穿戴閘。

戰鬥魅惑凝視(_choose_combat_action 的 UI 動作 + run_battle apply_control fear)由無頭煙霧覆蓋;
此處測可單元化的底層機制。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, dialogue, inventory, moons, vampirism

_NIGHTSHADE = ["nightshade_hood", "nightshade_cuirass", "nightshade_gloves", "nightshade_boots"]


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="V", sex="male", race="breton", birthsign="thief", class_id="thief")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, c


# --- 夜視(潛行/偵察)----------------------------------------------------
def test_is_night_window():
    assert moons.is_night(GameTime(hour=23)) and moons.is_night(GameTime(hour=3))
    assert not moons.is_night(GameTime(hour=12)) and not moons.is_night(GameTime(hour=8))


def test_night_vision_bonus_scales_with_stage_vampire_only():
    gd, c = _char()
    assert vampirism.night_vision_bonus(c) == 0.0           # 非吸血鬼 → 0
    c.is_vampire = True
    c.vampire_stage = 0
    assert vampirism.night_vision_bonus(c) == 0.0           # 剛進食(stage 0)→ 0
    c.vampire_stage = 3
    assert vampirism.night_vision_bonus(c) == 3 * vampirism.NIGHT_VISION_PER_STAGE   # 階級越高越強


def test_night_vision_raises_night_stealth_approach():
    gd, c = _char(); c.is_vampire = True; c.vampire_stage = 3
    gd2, human = _char()
    for x in (c, human):
        x.skills["sneak"] = 30                              # 同潛行 + 適中(避免夾到 0.97)
    foes = [combat.spawn_creature(gd, "bandit", RNG(1))]
    v_night = combat.stealth_approach_chance(c, foes, gd, night=True)
    h_night = combat.stealth_approach_chance(human, foes, gd, night=True)
    assert v_night > h_night                                # 夜視:吸血鬼夜間潛近更高(唯一差異=night_vision_bonus)
    assert combat.stealth_approach_chance(c, foes, gd, night=False) < v_night   # 白天無夜視


def test_night_evade_vampire_at_night_only():
    gd, c = _char(); c.is_vampire = True; c.vampire_stage = 2
    assert vampirism.night_evade(c, GameTime(hour=23)) > 0.0    # 夜間吸血鬼 → 迴避遭遇
    assert vampirism.night_evade(c, GameTime(hour=12)) == 0.0   # 白天 → 0
    gd2, human = _char()
    assert vampirism.night_evade(human, GameTime(hour=23)) == 0.0   # 非吸血鬼 → 0


# --- 社交魅惑 -----------------------------------------------------------
def test_charm_social_bonus_vampire_only():
    gd, c = _char()
    assert vampirism.charm_social_bonus(c) == 0.0
    c.is_vampire = True
    assert vampirism.charm_social_bonus(c) == vampirism.CHARM_SOCIAL_BONUS


def test_social_charm_raises_persuade_and_talk_down():
    gd, c = _char()
    c.skills["speechcraft"] = 30; c.attributes["personality"] = 40   # 適中,避開夾限
    base_persuade = dialogue.persuade_chance(c, gd, "any_npc")
    base_talk = dialogue.talk_down_chance(c, 60, gd)
    c.is_vampire = True
    assert dialogue.persuade_chance(c, gd, "any_npc") > base_persuade   # 吸血鬼魅力 → 說服更易
    assert dialogue.talk_down_chance(c, 60, gd) > base_talk             # → 說退衛兵更易


# --- 專屬裝備 + 偽裝套裝 ------------------------------------------------
def test_requires_vampire_equip_gate():
    gd, human = _char()
    for iid in _NIGHTSHADE + ["nightfang_dagger", "bloodkin_amulet"]:
        inventory.add_item(human, iid, 1)
    assert inventory.equip_armor(human, gd, "nightshade_hood") is False     # 非吸血鬼穿不上套裝
    assert inventory.equip_weapon(human, gd, "nightfang_dagger") is False   # 也裝不了武器
    assert inventory.equip_jewelry(human, gd, "bloodkin_amulet") is None    # 也戴不了飾品
    human.is_vampire = True
    assert inventory.equip_armor(human, gd, "nightshade_hood")              # 轉化後可穿
    assert inventory.equip_weapon(human, gd, "nightfang_dagger")


def test_disguise_needs_full_nightshade_set_and_vampire():
    gd, c = _char(); c.is_vampire = True
    for p in _NIGHTSHADE:
        inventory.add_item(c, p, 1)
        assert inventory.equip_armor(c, gd, p)
    assert vampirism.is_disguised(c, gd)                    # 穿滿四件 → 偽裝
    inventory.unequip(c, "helmet")
    assert not vampirism.is_disguised(c, gd)                # 缺一件 → 不偽裝
    # 非吸血鬼即使穿滿(理論上)也不偽裝
    gd2, human = _char()
    for p in _NIGHTSHADE:
        human.equipped[gd.item(p)["slot"]] = p             # 直接塞(繞過穿戴閘,測 is_vampire 前提)
    assert not vampirism.is_disguised(human, gd2)


def test_disguise_suppresses_shun_consequence():
    gd, c = _char()
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    st.time.advance(24 * 10)                                # today = 10
    c.is_vampire = True; c.vampire_fed_day = 1              # 久未進食 → 高階
    vampirism.apply_to_character(c, st, gd)
    assert vampirism.stage(c, st) >= vampirism.SHUN_STAGE and vampirism.is_shunned(c, st)
    assert vampirism.is_shunned(c, st) and not vampirism.is_disguised(c, gd)   # 未偽裝:後果 gate 條件成立
    for p in _NIGHTSHADE:
        inventory.add_item(c, p, 1); inventory.equip_armor(c, gd, p)
    assert vampirism.is_disguised(c, gd)
    assert not (vampirism.is_shunned(c, st) and not vampirism.is_disguised(c, gd))   # 偽裝 → 識破/排斥被 gate 掉


def test_cure_sheds_requires_vampire_gear():
    """治癒後凡人之身不再吃吸血鬼專屬裝加成(R56·審查修):卸下 requires_vampire 裝備(留背包)。"""
    gd, c = _char(); c.is_vampire = True
    for p in _NIGHTSHADE:
        inventory.add_item(c, p, 1); inventory.equip_armor(c, gd, p)
    inventory.add_item(c, "nightfang_dagger", 1); inventory.equip_weapon(c, gd, "nightfang_dagger")
    assert c.weapon == "nightfang_dagger" and "helmet" in c.equipped
    vampirism.cure(c, gd)
    assert c.weapon == "fists"                                  # 武器脫下 → 徒手
    assert not any((gd.item_or_none(i) or {}).get("requires_vampire") for i in c.equipped.values())  # 專屬甲全脫
    assert inventory.count_item(c, "nightfang_dagger") == 1     # 仍在背包(只脫不丟)
    assert not vampirism.is_disguised(c, gd)                    # 已非吸血鬼


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_vampire_abilities")
