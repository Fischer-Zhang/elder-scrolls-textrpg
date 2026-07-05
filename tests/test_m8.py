"""M8:元素抗性/弱點、狀態效果(DoT/麻痺/再生)、出生星座能力。"""

import tempfile
from pathlib import Path

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, dungeon, magic, mastery, powers


def _mage():
    gd = get_gamedata()
    c = build_character(gd, name="法", sex="female", race="breton",
                        birthsign="mage", class_id="mage")
    c.skills["destruction"] = 50
    c.magicka = 999
    return gd, c


def _st(c):
    return GameState(player=c, time=GameTime())


# --- 抗性公式 -----------------------------------------------------------
def test_resist_multiplier():
    assert formulas.resist_multiplier({"fire": 75}, "fire") == 0.25
    assert formulas.resist_multiplier({"fire": -50}, "fire") == 1.5      # 弱點放大
    assert formulas.resist_multiplier({"frost": 100}, "frost") == 0.0    # 完全免疫
    # magic 抗性疊加在魔法元素上,但不影響毒素
    assert formulas.resist_multiplier({"magic": 50}, "fire") == 0.5
    assert formulas.resist_multiplier({"magic": 50}, "poison") == 1.0


def test_cast_respects_resist_and_weakness():
    gd, c = _mage()
    # dremora 強抗火、不抗冰 → 火傷遠低於冰傷
    fire = magic.cast(c, gd, "flames", RNG(1), target=combat.spawn_creature(gd, "dremora", RNG(1)))
    frost = magic.cast(c, gd, "frostbite", RNG(1), target=combat.spawn_creature(gd, "dremora", RNG(1)))
    assert fire["damage"] < frost["damage"]
    assert "被抵抗" in fire["message"]
    # ice_wraith 弱火 → 火傷被放大,且命中弱點標記
    weak = magic.cast(c, gd, "flames", RNG(1), target=combat.spawn_creature(gd, "ice_wraith", RNG(1)))
    assert "弱點" in weak["message"]


def test_frostbite_applies_benumb_control():
    """冰系法術凍麻(純減命中):frostbite 命中未殺即附 benumb → 降敵命中;軟控對 solo BOSS 照施。"""
    gd, c = _mage()
    foe = combat.spawn_creature(gd, "dremora_lord", RNG(3))    # solo BOSS·高血 → 不會被一發秒
    magic.cast(c, gd, "frostbite", RNG(3), target=foe)
    assert any(e["kind"] == "benumb" and e["turns"] > 0 for e in foe.active_effects)  # 凍麻施加
    assert magic.benumb_hit_penalty(foe) > 0                   # 命中懲罰生效(降敵命中)
    # frost_nova 對群附 AoE 凍麻(較弱)
    mob = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(2)]
    magic.cast(c, gd, "frost_nova", RNG(0), enemies=mob)
    assert all(magic.benumb_hit_penalty(e) > 0 for e in mob)


def test_dot_and_hot_scale_with_spell_power_r76():
    """R76:DoT(延燒/毒雲)與 HoT(再生 renewal)的 magnitude 吃法術威力(同直擊/直接治療);
    低威力(基礎)→ 高威力(放大)。非 cast 來源(武器/塗毒)不受影響(走 combat 路徑)。"""
    gd, c = _mage()
    c.skills.update(destruction=100, restoration=100)
    c.attributes.update(intelligence=100)
    c.magicka = 999999
    foe = combat.spawn_creature(gd, "frost_troll", RNG(1)); foe.health = foe.max_health = 10**6
    magic.cast(c, gd, "ignite", RNG(1), target=foe)               # 延燒基礎 DoT 6
    assert next(e["magnitude"] for e in foe.active_effects if e["kind"] == "dot") > 6   # 吃威力放大
    foe2 = combat.spawn_creature(gd, "bandit", RNG(2)); foe2.health = foe2.max_health = 10**6
    magic.cast(c, gd, "poison_cloud", RNG(2), target=foe2)        # 毒雲基礎 DoT 6
    assert next(e["magnitude"] for e in foe2.active_effects if e["kind"] == "dot") > 6
    c.health = 1
    magic.cast(c, gd, "renewal", RNG(3))                          # 再生 HoT 基礎 10(self)
    assert next(e["magnitude"] for e in c.active_effects if e["kind"] == "regen") > 10  # HoT 吃威力放大


def test_staff_spell_focus_r77():
    """R77 持杖施法焦點:元素法杖同系直擊加傷(他系不受益)、馬格努斯 +威力+全元素加傷、法力法杖 +威力。"""
    gd, c = _mage()
    c.skills.update(destruction=100); c.attributes.update(intelligence=100)
    def dmg(staff, spell):
        c.weapon = staff or ""
        c.magicka = 99999; c.active_effects = []
        foe = combat.spawn_creature(gd, "bandit", RNG(1)); foe.health = foe.max_health = 10**7; foe.resist = {}
        return magic.cast(c, gd, spell, RNG(1), target=foe)["damage"]
    base_fire, base_frost = dmg(None, "fireball"), dmg(None, "frostbite")
    assert dmg("flame_staff", "fireball") > base_fire                 # 烈焰杖:火受益
    assert dmg("flame_staff", "frostbite") == base_frost             # 烈焰杖:冰不受益(同系限定)
    assert dmg("staff_of_magnus", "fireball") > base_fire            # 馬格努斯:全元素受益
    assert dmg("staff_of_magnus", "frostbite") > base_frost
    assert dmg("magicka_staff", "fireball") > base_fire              # 法力法杖:法術威力加成


def test_conduct_stacks_amplifies_shock_and_clears():
    """R75 感電易傷:電系法術每命中疊一層導電(夾10·+3%/層·只放大電傷);3 回合無電擊清零。"""
    gd, c = _mage()
    c.max_magicka = c.magicka = 10**6             # 大魔力池 → 連續電擊不 OOM(純測疊層)
    foe = combat.spawn_creature(gd, "frost_troll", RNG(1))
    foe.health = foe.max_health = 10**6           # 高血 → 永不被秒,純測疊層
    for i in range(1, 6):
        magic.cast(c, gd, "lightning_bolt", RNG(i), target=foe)
        assert magic.conduct_stacks(foe) == i      # 每擊 +1 層
    for i in range(20):
        magic.cast(c, gd, "lightning_bolt", RNG(i + 99), target=foe)
    assert magic.conduct_stacks(foe) == 10         # 夾 10 層
    assert abs(magic.conduct_damage_multiplier(foe) - 1.30) < 1e-9   # +30%
    # 非電系不疊也不放大
    fb_foe = combat.spawn_creature(gd, "bandit", RNG(2)); fb_foe.health = fb_foe.max_health = 10**6
    magic.cast(c, gd, "fireball", RNG(3), target=fb_foe)
    assert magic.conduct_stacks(fb_foe) == 0
    # 3 回合無電擊 → 整組清零(turns 歸零移除,非逐層遞減)
    for _ in range(3):
        magic.tick_effects(foe, gd)
    assert magic.conduct_stacks(foe) == 0


def test_arcane_erosion_shreds_magic_resist_for_all_damage_magic():
    """R120 秘蝕(mysticism_100 頂點):持頂點者的**任何傷害法術**命中疊「秘蝕」→ 削目標通用魔抗
    (3/層·夾 5=−15·floored≥0);因火/冰/雷亦吃 magic 抗 → **輔助所有傷害魔法**;3 回合無傷害法術則清零;
    非頂點者不施加(byte-identical)。"""
    gd, c = _mage()
    c.max_magicka = c.magicka = 10**6
    c.skills["mysticism"] = 100
    mastery.choose(c, gd, "mysticism_100", "arcane_erosion")
    assert mastery.has_arcane_erosion(c, gd)
    foe = combat.spawn_creature(gd, "dremora_lord", RNG(1))   # fire75 + magic30
    foe.health = foe.max_health = 10**6
    for i in range(1, 6):
        magic.cast(c, gd, "arcane_bolt", RNG(i), target=foe)
        assert magic.erosion_stacks(foe) == i                 # 每擊 +1 層
    for i in range(10):
        magic.cast(c, gd, "arcane_bolt", RNG(i + 99), target=foe)
    assert magic.erosion_stacks(foe) == 5                      # 夾 5 層
    assert magic.erosion_resist_reduction(foe) == 15          # 3×5

    # 輔助「所有」傷害魔法:fireball(fire·亦吃 magic 抗)在秘蝕滿層時解牆(dremora fire75+magic30:
    # 無秘蝕 fireball ×0 全牆;−15 魔抗 → fire75+magic15=90 → ×0.10 解牆 → 破抗輔助火系)
    def _fire_dmg(n_stacks):
        gd3, cc = _mage(); cc.max_magicka = cc.magicka = 10**6; cc.skills["mysticism"] = 100
        mastery.choose(cc, gd3, "mysticism_100", "arcane_erosion")
        f = combat.spawn_creature(gd3, "dremora_lord", RNG(5)); f.health = f.max_health = 10**6
        for _ in range(n_stacks):
            magic.add_erosion(f)
        return magic.cast(cc, gd3, "fireball", RNG(7), target=f)["damage"]
    assert _fire_dmg(0) == 0 and _fire_dmg(5) > 0             # 破抗解火系牆 → 輔助所有傷害魔法

    # 非頂點者:不疊秘蝕(短路 → byte-identical)
    gd2, c2 = _mage(); c2.max_magicka = c2.magicka = 10**6
    foe2 = combat.spawn_creature(gd2, "dremora_lord", RNG(1)); foe2.health = foe2.max_health = 10**6
    magic.cast(c2, gd2, "arcane_bolt", RNG(1), target=foe2)
    assert magic.erosion_stacks(foe2) == 0

    # 3 回合無傷害法術 → 整組清零
    for _ in range(3):
        magic.tick_effects(foe, gd)
    assert magic.erosion_stacks(foe) == 0


# --- 狀態效果 -----------------------------------------------------------
def test_dot_ticks_and_respects_resist():
    gd, c = _mage()
    wolf = combat.spawn_creature(gd, "wolf", RNG(2))
    magic.cast(c, gd, "poison_cloud", RNG(2), target=wolf)
    # 併入 normalization:資料用 {'status':'dot'},放進 active_effects 須正規化成 {'kind':'dot'}。
    # 須在 tick 前驗(tick_effects 會 turns-1 並移除歸零者,放 tick 後語意失真)。
    assert all("kind" in e for e in wolf.active_effects)
    assert any(e["kind"] == "dot" for e in wolf.active_effects)
    hp0 = wolf.health
    msgs = magic.tick_effects(wolf, gd)
    assert wolf.health < hp0 and msgs
    # 亞龍人免疫毒素 → DoT 0
    arg = build_character(gd, name="A", sex="m", race="argonian", birthsign="warrior", class_id="warrior")
    arg.active_effects = [{"kind": "dot", "element": "poison", "magnitude": 10, "turns": 2}]
    h0 = arg.health
    magic.tick_effects(arg, gd)
    assert arg.health == h0


def test_regen_and_paralyze():
    gd, c = _mage()
    c.health = 1
    c.active_effects = [{"kind": "regen", "magnitude": 10, "turns": 2}]
    magic.tick_effects(c, gd)
    assert c.health == 11
    foe = combat.spawn_creature(gd, "wolf", RNG(0))
    foe.active_effects = [{"kind": "paralyze", "turns": 2}]
    assert magic.is_paralyzed(foe) and magic.is_incapacitated(foe)


def test_creature_on_hit_status():
    gd, _ = _mage()
    p = build_character(gd, name="P", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    spider = combat.spawn_creature(gd, "frostbite_spider", RNG(5))
    applied = any(combat.resolve_attack(spider, p, gd, RNG(i)).get("status_applied") for i in range(25))
    assert applied
    assert any(e["kind"] == "dot" for e in p.active_effects)


# --- 巨魔像吸收 ---------------------------------------------------------
def test_atronach_absorbs_elemental():
    gd, _ = _mage()
    c = build_character(gd, name="At", sex="m", race="nord", birthsign="atronach", class_id="warrior")
    c.max_magicka = 200
    c.magicka = 0
    dre = combat.spawn_creature(gd, "dremora", RNG(0))     # fire 攻擊
    absorbed = any(combat.resolve_attack(dre, c, gd, RNG(i)).get("absorbed") for i in range(40))
    assert absorbed and c.magicka > 0


# --- 出生星座能力 -------------------------------------------------------
def test_power_id_per_sign():
    gd, _ = _mage()
    def pid(sign):
        c = build_character(gd, name="X", sex="m", race="nord", birthsign=sign, class_id="warrior")
        return powers.power_id(c, gd)
    assert pid("lord") == "heal_self"
    assert pid("lover") == "paralyze_touch"
    # 星座深化(R61 後續):戰士/法師/淑女補主動威能;竊賊/駿馬走被動(主動槽仍 None)
    assert pid("warrior") == "warrior_fury"
    assert pid("mage") == "magicka_surge"
    assert pid("lady") == "ladys_grace"
    assert pid("thief") is None            # 竊賊座走被動巧手(無主動威能槽)
    assert pid("steed") is None            # 駿馬座走被動疾行


def test_power_cooldown_per_day():
    gd, _ = _mage()
    c = build_character(gd, name="L", sex="m", race="nord", birthsign="lord", class_id="warrior")
    st = _st(c)
    assert powers.available(c, st, gd)
    c.health = 1
    powers.use(c, st, gd)
    assert not powers.available(c, st, gd)         # 同日不可再用
    st.time.advance(24)
    assert powers.available(c, st, gd)             # 隔日恢復


def test_tower_key_auto_unlock():
    gd, _ = _mage()
    c = build_character(gd, name="T", sex="m", race="nord", birthsign="tower", class_id="thief")
    st = _st(c)
    powers.use(c, st, gd)
    assert c.tower_key_charge
    r = dungeon.pick_lock(c, gd, 95, RNG(0))        # 高難度鎖
    assert r["success"] and r["tower_key"] and not c.tower_key_charge   # 必開且消耗


def test_mara_cure_removes_dot():
    gd, _ = _mage()
    c = build_character(gd, name="R", sex="m", race="nord", birthsign="ritual", class_id="warrior")
    c.active_effects = [{"kind": "dot", "element": "fire", "magnitude": 5, "turns": 3},
                        {"kind": "shield", "magnitude": 20, "turns": 3}]
    powers.use(c, _st(c), gd)
    assert not any(e["kind"] == "dot" for e in c.active_effects)
    assert any(e["kind"] == "shield" for e in c.active_effects)   # 只淨化 DoT,不動護盾


# --- 存讀檔 -------------------------------------------------------------
def test_active_effects_not_persisted():
    """回歸審查 [2]:戰鬥內臨時效果(護盾/中毒)不可寫入存檔(否則離線永久 tick)。"""
    gd, _ = _mage()
    c = build_character(gd, name="P", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    c.active_effects = [{"kind": "dot", "element": "poison", "magnitude": 5, "turns": 10}]
    st = _st(c)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        st.save(p)
        lo = GameState.load(p)
    assert lo.player.active_effects == []           # 載入後為空,不會在休息/旅途中持續扣血


def test_power_state_roundtrip():
    gd, _ = _mage()
    c = build_character(gd, name="S", sex="m", race="nord", birthsign="tower", class_id="thief")
    st = _st(c)
    powers.use(c, st, gd)              # 設定冷卻 + tower_key_charge
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        st.save(p)
        lo = GameState.load(p)
    assert lo.player.power_last_day == c.power_last_day
    assert lo.player.tower_key_charge == c.tower_key_charge


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m8 OK")
