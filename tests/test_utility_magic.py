"""實用/幻術魔法(R104)單元測試:魅惑(社交)/ 隱形(潛行)/ 安撫(脫戰)/ 羽落(負重)/ 偵知(探索)。

涵蓋:spellfx 限時層(施放/到期/遷移/往返)、魅惑六社交面加成 + 過期歸零、隱形遭遇折減 + 破除、
安撫人數非線性曲線 + solo boss 免疫 + 失能、羽落負重、偵知消耗、byte-identical(無增益 → 加成全 0)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg import formulas
from tesrpg.systems import combat, crime, dialogue, inventory, magic, spellfx, world


def _state(seed=1, hour=12):
    gd = get_gamedata()
    c = build_character(gd, name="U", sex="male", race="breton", birthsign="mage", class_id="mage")
    c.spells = list(c.spells) + ["charm", "invisibility", "feather", "calm", "detect_life"]
    c.magicka = c.max_magicka = 300
    c.fatigue = c.max_fatigue = 200
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


def _cast(gd, c, st, sid, **kw):
    return magic.cast(c, gd, sid, st.rng, state=st, **kw)


# --- spellfx 限時層 --------------------------------------------------------
def test_spellfx_apply_and_expire():
    gd, c, st = _state()
    _cast(gd, c, st, "charm")
    assert spellfx.is_charmed(c)
    # 未到期:update 無事件、仍生效
    assert spellfx.update(st, gd) == []
    assert spellfx.is_charmed(c)
    # 過 6 小時後到期 → update 剔除 + 回事件
    st.time.advance(7)
    evs = spellfx.update(st, gd)
    assert evs and evs[0]["kind"] == "spellfx_expire"
    assert not spellfx.is_charmed(c)


def test_spellfx_refresh_takes_later_expiry():
    gd, c, st = _state()
    _cast(gd, c, st, "feather")
    first = [e for e in c.spell_effects if e["kind"] == "feather"][0]["expires_at"]
    st.time.advance(2)
    _cast(gd, c, st, "feather")   # 重施 → 取較晚到期(刷新)
    again = [e for e in c.spell_effects if e["kind"] == "feather"][0]["expires_at"]
    assert again > first
    assert len([e for e in c.spell_effects if e["kind"] == "feather"]) == 1   # 不重複堆


def test_spellfx_roundtrip_and_migration():
    gd, c, st = _state()
    _cast(gd, c, st, "charm")
    d = c.to_dict()
    assert "spell_effects" in d
    c2 = Character.from_dict(d)
    assert spellfx.is_charmed(c2)   # 往返保留
    # 舊存檔缺欄 → dataclass 預設空 list(不崩)
    d.pop("spell_effects")
    c3 = Character.from_dict(d)
    assert c3.spell_effects == []
    # ensure 依當前時間剔過期
    c3.spell_effects = [{"kind": "charm", "magnitude": 1.0, "expires_at": st.time.absolute_hours() - 1},
                        {"kind": "feather", "magnitude": 1.0, "expires_at": st.time.absolute_hours() + 100}]
    spellfx.ensure_spell_effect_fields(c3, st.time, gd)
    assert not spellfx.is_charmed(c3) and spellfx.feather_bonus(c3) == spellfx.FEATHER_CARRY_BONUS


# --- 魅惑 charm(六社交面)-------------------------------------------------
def test_charm_boosts_all_six_social_facets():
    gd, c, st = _state()
    npc = list(gd.npcs)[0]
    item = "healing_potion"
    p0 = dialogue.persuade_chance(c, gd, npc)
    t0 = dialogue.talk_down_chance(c, 50, gd)
    y0 = dialogue.pry_chance(c)
    steal0 = crime.steal_chance(c, gd)
    buy0 = world.buy_price(c, gd, item)
    _cast(gd, c, st, "charm")
    assert dialogue.persuade_chance(c, gd, npc) > p0
    assert dialogue.talk_down_chance(c, 50, gd) > t0
    assert dialogue.pry_chance(c) > y0
    assert crime.steal_chance(c, gd) > steal0
    assert world.buy_price(c, gd, item) <= buy0    # 議價更划算(買價不升)
    assert abs(spellfx.charm_bounty_factor(c) - spellfx.CHARM_BOUNTY_FACTOR) < 1e-9


def test_charm_bonuses_zero_without_buff():
    """byte-identical 守:無 charm → 各面加成恆 0(既有社交/物價逐位元組同)。"""
    gd, c, st = _state()
    assert spellfx.charm_persuade_bonus(c) == 0.0
    assert spellfx.charm_talk_down_bonus(c) == 0.0
    assert spellfx.charm_barter_bonus(c) == 0.0
    assert spellfx.charm_steal_bonus(c) == 0.0
    assert spellfx.charm_bounty_factor(c) == 1.0


# --- 隱形 invisibility(潛行)---------------------------------------------
def test_invisibility_encounter_factor_and_break():
    gd, c, st = _state()
    assert spellfx.invis_encounter_factor(c) == 1.0   # 無隱形 → ×1.0
    _cast(gd, c, st, "invisibility")
    assert spellfx.is_invisible(c)
    assert spellfx.invis_encounter_factor(c) == spellfx.INVIS_ENCOUNTER_FACTOR
    spellfx.break_invisibility(c)                     # 攻擊/入戰即破
    assert not spellfx.is_invisible(c)
    assert spellfx.invis_encounter_factor(c) == 1.0


def test_invisibility_sneak_on_solo_boss_still_capped():
    """紅線:隱形重置偷襲先機,但首擊仍受 SOLO_SNEAK 夾 → 不秒 solo boss。"""
    gd, c, st = _state()
    c.weapon = "iron_dagger"
    solo = next((t for t in gd.bestiary if gd.bestiary[t].get("solo")), None)
    assert solo is not None
    boss = combat.spawn_boss(gd, solo, RNG(1))
    hp0 = boss.health
    ev = combat.resolve_attack(c, boss, gd, RNG(2), sneak_attack=True)   # 隱形授予的偷襲首擊
    dealt = hp0 - boss.health
    assert dealt <= boss.max_health * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO + 1


# --- 安撫 calm(脫戰)------------------------------------------------------
def test_calm_chance_nonlinear_decreasing():
    prev = 1.0
    for n in (1, 2, 3, 4, 5):
        ch = formulas.calm_chance(60, 50, n)
        assert ch <= prev, f"人數 {n} 成功率未遞減"
        prev = ch
    assert formulas.calm_chance(60, 50, 1) > formulas.calm_chance(60, 50, 4)   # 單體遠高於群體
    # 技能越高越易安撫
    assert formulas.calm_chance(100, 60, 3) > formulas.calm_chance(30, 30, 3)


def test_calm_solo_boss_immune():
    gd, c, st = _state()
    solo = next((t for t in gd.bestiary if gd.bestiary[t].get("solo")), None)
    boss = combat.spawn_boss(gd, solo, RNG(1))
    assert magic.apply_control(boss, "calm", gd, RNG(1), turns=2) == "resisted"
    assert not magic.is_calm(boss)


class _AlwaysRNG(RNG):
    def chance(self, p):   # 強制成功 → 決定性驗「全數安撫」路徑(避開 calm_chance 機率)
        return True


def test_calm_pacifies_trash_and_incapacitates():
    gd, c, st = _state()
    # 決定性:apply_control 對非 solo 敵必施加 calm → 走 is_incapacitated 閘(敵跳過行動)
    bandit = combat.spawn_creature(gd, "bandit", RNG(1))
    assert magic.apply_control(bandit, "calm", gd, RNG(1), turns=2) == "applied"
    assert magic.is_calm(bandit) and magic.is_incapacitated(bandit)
    assert not magic.is_paralyzed(bandit) and not magic.is_feared(bandit)   # calm 是獨立態(失能訊息須三態:恐懼/麻痺/安撫)
    # 去重:同敵重施 calm → blocked(不延長鎖定)
    assert magic.apply_control(bandit, "calm", gd, RNG(1), turns=2) == "blocked"
    # cast 路徑(強制成功 rng):全體被安撫
    trash = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(3)]
    magic.cast(c, gd, "calm", _AlwaysRNG(1), enemies=trash, state=st)
    assert all(magic.is_calm(e) for e in trash)


# --- 羽落 feather / 偵知 detect_life --------------------------------------
def test_feather_raises_carry_and_reverts():
    gd, c, st = _state()
    mw0 = inventory.max_weight(c, gd)
    _cast(gd, c, st, "feather")
    assert inventory.max_weight(c, gd) == mw0 + spellfx.FEATHER_CARRY_BONUS
    spellfx.ensure_spell_effect_fields(c, GameTime(hour=st.time.hour), gd)  # 同時未過期 → 仍在
    assert inventory.max_weight(c, gd) == mw0 + spellfx.FEATHER_CARRY_BONUS


def test_detect_life_is_consumed():
    gd, c, st = _state()
    _cast(gd, c, st, "detect_life")
    assert spellfx.is_detecting(c)
    spellfx.consume_detect(c)
    assert not spellfx.is_detecting(c)


# --- 變化「負重」控場(R118)---------------------------------------------
def test_burden_slows_enemy_and_penalizes_hit_r118():
    """負重術:施放→敵 slow(magnitude 0.4)→命中 −0.20(對戰況有利=敵少命中);軟控對 solo boss 亦生效(無免疫)。"""
    gd, c, st = _state()
    c.spells = list(c.spells) + ["burden", "mass_burden"]
    c.skills["alteration"] = 60
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    _cast(gd, c, st, "burden", target=foe)
    assert magic.is_slowed(foe) and abs(magic.slow_factor(foe) - 0.4) < 1e-9
    assert abs(formulas.slow_hit_penalty(magic.slow_factor(foe)) - 0.20) < 1e-9   # 負重 −20% 命中
    boss = combat.spawn_creature(gd, "knight_of_order", RNG(2))
    _cast(gd, c, st, "burden", target=boss)
    assert magic.is_slowed(boss)                                                  # 軟控無 solo 免疫
    assert gd.spells["burden"]["school"] == "alteration" and gd.spells["mass_burden"]["school"] == "alteration"


def test_slow_hit_penalty_scaling_r118():
    """slow 命中懲罰 magnitude 縮放:≤0.3 恆等舊 flat 0.15(既有 slow byte-identical)·負重 0.4→0.20·夾 cap 0.30。"""
    f = formulas.slow_hit_penalty
    assert f(0.0) == 0.15 and f(0.1) == 0.15 and f(0.2) == 0.15 and f(0.3) == 0.15   # 地板=既有恆等(byte-identical)
    assert abs(f(0.4) - 0.20) < 1e-9 and abs(f(0.5) - 0.25) < 1e-9
    assert f(0.6) == 0.30 and f(1.0) == 0.30                                          # cap


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_utility_magic OK")
