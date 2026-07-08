"""R127 物理抗性(resist.physical)單元測試:護甲之外的 pen-免疫物理減傷層 + 玩家 cap25 + 附魔/煉金玩家來源。

物理抗性補完抗性系統(物理原是唯一無抗性軸的傷害類型);boss 用之築成 pen 免疫的物理牆(封 2H 破甲流),
玩家可經附魔/煉金取得但夾 PLAYER_PHYSICAL_RESIST_CAP(守 R71 群戰須具真實風險)。
"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Creature
from tesrpg.rng import RNG
from tesrpg.synth import enchant_armor_id, _RESIST_NAME
from tesrpg.systems import combat, magic, inventory, enchanting, stats, alchemy


def _avg_hit_damage(defender_factory, n=3000, weapon="steel_mace"):
    """attacker(固定物理 build)打 defender_factory() n 次的平均實傷(每次新 defender 免累積)。
    weapon:steel_mace=無 archetype pen;steel_war_axe=axe archetype pen 0.30(測 pen 免疫)。"""
    gd = get_gamedata()
    atk = build_character(gd, name="攻", sex="male", race="orsimer", birthsign="warrior", class_id="warrior")
    atk.skills["blunt"] = 100
    atk.attributes["strength"] = 80
    atk.weapon = weapon
    total = 0
    for s in range(n):
        d = defender_factory()
        hp0 = d.health
        combat.resolve_attack(atk, d, gd, RNG(s * 7 + 1))
        total += hp0 - d.health
    return total / n


# ---------- 公式層:physical 是正規抗性、不吃 magic 抗 ----------

def test_physical_is_resist_type_not_magic_element():
    assert "physical" not in formulas.MAGIC_ELEMENTS
    # magic 抗不滲入 physical(physical ∉ MAGIC_ELEMENTS)
    assert formulas.resist_multiplier({"physical": 60, "magic": 40}, "physical") == 0.40
    assert formulas.resist_multiplier({"physical": 0}, "physical") == 1.0    # 無物抗 → ×1.0(byte-identical 基石)


def test_no_physical_resist_is_byte_identical_multiplier():
    """既有怪/未附魔玩家:entity_resist 無 physical → resist_multiplier 回 1.0(×1.0 逐位元組同)。"""
    gd = get_gamedata()
    rat = combat.spawn_creature(gd, "giant_rat", RNG(1))
    assert magic.entity_resist(rat, gd).get("physical", 0) == 0
    assert formulas.resist_multiplier(magic.entity_resist(rat, gd), "physical") == 1.0


# ---------- combat:物理抗性減傷 + pen 免疫 ----------

def test_physical_resist_reduces_weapon_damage():
    gd = get_gamedata()
    def plain():   # 無物抗怪
        return combat.spawn_creature(gd, "bandit", RNG(0))
    def resisted():
        c = combat.spawn_creature(gd, "bandit", RNG(0))
        c.resist = dict(c.resist or {}); c.resist["physical"] = 50
        return c
    d0, d1 = _avg_hit_damage(plain), _avg_hit_damage(resisted)
    assert d1 < d0
    assert 0.42 < d1 / d0 < 0.58   # ~×0.50(物抗 50)


def test_physical_resist_is_pen_immune():
    """物理抗性走抗性層,非護甲 → 破甲(pen)不減其效力:無論用不用破甲,物抗的『減傷因子』恆定。
    對照:護甲會被 pen 削弱,物抗不會 → 有甲時 axe(pen0.30)vs mace(無 pen)的『物抗因子』應一致。"""
    gd = get_gamedata()
    def plain():   # 有甲、無物抗
        c = combat.spawn_creature(gd, "bandit", RNG(0)); c.armor_rating = 100
        c.resist = dict(c.resist or {})
        return c
    def resisted():   # 有甲 + 物抗 50
        c = combat.spawn_creature(gd, "bandit", RNG(0)); c.armor_rating = 100
        c.resist = dict(c.resist or {}); c.resist["physical"] = 50
        return c
    # 物抗因子 = 有物抗/無物抗;pen 若能削弱物抗,axe 的因子會偏離 mace → 應一致 ≈0.50
    factor_mace = _avg_hit_damage(resisted, weapon="steel_mace") / _avg_hit_damage(plain, weapon="steel_mace")
    factor_axe = _avg_hit_damage(resisted, weapon="steel_war_axe") / _avg_hit_damage(plain, weapon="steel_war_axe")
    assert 0.45 < factor_mace < 0.55 and 0.45 < factor_axe < 0.55   # 兩者皆 ~×0.50 → pen 不碰物抗
    assert abs(factor_mace - factor_axe) < 0.05


# ---------- 玩家 cap25 vs boss 不夾 ----------

def test_player_physical_resist_capped():
    assert formulas.PLAYER_PHYSICAL_RESIST_CAP == 25
    gd = get_gamedata()
    atk = combat.spawn_creature(gd, "bandit", RNG(0))
    def player(phys):
        p = build_character(gd, name="玩", sex="male", race="imperial", birthsign="mage", class_id="mage")
        p.equip_resist["physical"] = phys
        return p
    # 注入 57 與注入 25 的實傷應相同(玩家側夾 25)
    def hit(phys, n=3000):
        tot = 0
        for s in range(n):
            p = player(phys); hp0 = p.health
            combat.resolve_attack(atk, p, gd, RNG(s * 3 + 1))
            tot += hp0 - p.health
        return tot / n
    assert abs(hit(57) - hit(25)) / hit(25) < 0.05      # 夾平:57 效果 == 25
    assert hit(25) < hit(0)                              # 25 確實減傷


def test_boss_physical_resist_uncapped():
    """boss(非玩家)物抗不受 PLAYER cap → 真身 70 全額生效。"""
    gd = get_gamedata()
    b = gd.bestiary["mehrunes_dagon_true"]
    assert b["resist"]["physical"] == 70 and b["resist"]["magic"] == 52 and b.get("solo")
    # 70 > cap25,但怪不夾 → resist_multiplier 全額
    cr = combat.spawn_creature(gd, "mehrunes_dagon_true", RNG(0))
    assert abs(formulas.resist_multiplier(magic.entity_resist(cr, gd), "physical") - 0.30) < 1e-9


# ---------- 玩家來源:附魔 + 煉金 ----------

def test_physical_resist_enchant_conservative_and_flows():
    gd = get_gamedata()
    assert "physical" in enchanting.RESIST_ELEMENTS
    # 保守:物抗走「魔抗」低階(不 ×2)→ 甲件 = 魔抗值 = fire 的一半
    m_phys = enchanting._resist_magnitude("armor", "physical", 5, 100)
    m_magic = enchanting._resist_magnitude("armor", "magic", 5, 100)
    m_fire = enchanting._resist_magnitude("armor", "fire", 5, 100)
    assert m_phys == m_magic == m_fire // 2
    # 附魔 → equip_resist → entity_resist
    eid = enchant_armor_id("iron_cuirass", "resist", "physical", m_phys)
    ed = gd.item(eid)
    assert ed["enchant"] == {"kind": "resist_element", "element": "physical", "magnitude": m_phys}
    c = build_character(gd, name="附", sex="male", race="imperial", birthsign="mage", class_id="mage")
    inventory.add_item(c, eid, 1); inventory.equip_armor(c, gd, eid); stats.recompute_max_resources(c, gd)
    assert c.equip_resist.get("physical") == m_phys
    assert "物理" in ed["name"]        # 名稱翻譯(非 raw physical)


def test_physical_resist_brew_fail_set():
    """troll_fat/bear_claw/bone_meal 三兩兩相配 → resist_physical 藥(FAIL-set,不擾既有配方)。"""
    gd = get_gamedata()
    for a, b in [("troll_fat", "bear_claw"), ("troll_fat", "bone_meal"), ("bear_claw", "bone_meal")]:
        c = build_character(gd, name="釀", sex="male", race="imperial", birthsign="mage", class_id="mage")
        c.skills["alchemy"] = 100
        c.known_effects = {a: ["resist_physical"], b: ["resist_physical"]}
        inventory.add_item(c, a, 1); inventory.add_item(c, b, 1)
        r = alchemy.brew(c, gd, a, b, RNG(1))
        assert r["ok"] and "resist_physical" in r["item_id"]
        pot = gd.item(r["item_id"])
        assert pot["effect"]["type"] == "resist_element" and pot["effect"]["element"] == "physical"
        assert "物理" in pot["name"]    # 藥名翻譯


def test_player_cap_keeps_group_risk_real_r71():
    """R127 對抗審查補測:物理抗性 cap 對 R71「群戰須具真實風險」的軟化須有界 —— 用 sim_assassin 的
    apex 潛行 fixture(輕甲低護甲=R71 最壞情形)+ 物理抗性堆到超夾,4-bandit 死亡率仍須 ≥15%
    (使用者拍板中等 cap 25% → 實測 ~25%;若 cap 被調高致 trivialize,此測失敗)。"""
    import sim_assassin as S
    def apex_phys():   # 複用 sim_assassin apex(sneak100/blade100/dual/影刃)+ 物抗超夾
        c = S.assassin(sneak=100, blade=100, alchemy=60, scout=75, dual=True,
                       mastery_choices={"sneak_100": "shadowblade"})
        c.equip_resist["physical"] = formulas.PLAYER_PHYSICAL_RESIST_CAP + 40   # 超 cap → 驗夾生效
        return c
    dr = S.rate(apex_phys, ["bandit"] * 4, "dead", n=1200)
    assert dr >= 0.15, f"滿物抗 apex 4-bandit 死亡率 {dr:.1%} < 15% → 物抗把 R71 群戰紅線軟化過猛(cap 過高?)"


def test_resist_labels_parametric():
    import tesrpg.main as M
    assert _RESIST_NAME["physical"] == "物理"
    # R127 順帶修 resist_fire/disease 原顯示 raw 的缺口
    assert M._effect_cn("resist_physical") == "抗物理"
    assert M._effect_cn("resist_fire") == "抗火焰"
    assert M._effect_cn("resist_disease") == "抗疾病"


def test_monster_physical_resist_by_category_r128():
    """R128:物理抗性按類別填入 149 怪 —— 幽體/構造/元素高、骨系/血肉/sim 群戰常見怪 0(守 byte-identical + R71)。"""
    gd = get_gamedata()
    def phys(cid):
        return (gd.bestiary[cid].get("resist") or {}).get("physical", 0)
    # 幽體(凡兵穿體)/構造(石金)/元素(元素之軀):高物抗
    for cid in ["will_o_wisp", "imperial_ghost", "grief_shade", "gargoyle", "dwarven_centurion", "storm_atronach"]:
        assert phys(cid) >= 25, f"{cid}(幽體/構造/元素)應有高物抗"
    # 骨系/血肉/**群戰紅線怪**:0(骨易碎、凡兵有效;bandit/wolf/skeleton 是 sim_assassin 群戰 fixture·守 R71 須恆 0)
    for cid in ["skeleton", "draugr", "lich", "bandit", "wolf", "bear", "vampire_lord"]:
        assert phys(cid) == 0, f"{cid}(骨/肉/群戰紅線怪)須為 0"
    # R128b:base dremora/frost_troll 改與變體一致(物種一致性)。R37/R92 精英 oneshot 增幅檢查已降為資訊列
    # (飽和假象·非紅線);真紅線=temper/fortify 不破 solo cap,不受影響(sim_assassin part① 全 0%)。
    assert phys("dremora") == 10, "base dremora 對齊 dremora_lord=10"
    assert phys("frost_troll") == 20, "base frost_troll 對齊 bog_troll/frost_giant=20"
    # 召喚物(幽體/元素)也得物抗(R128 強化召喚師·sim_party 驗不 trivialize)
    assert phys("ancestral_ghost") >= 40 and phys("summoned_storm_atronach") >= 25
    # 真身仍最高(位面化身特例)
    assert phys("mehrunes_dagon_true") == 70
    # R133:主線/削弱達貢也高物抗(位面之君抗物理·刻意破 R128「魔神 8-10」rubric = 終王「物理不獨大」;
    # 三達貢一致階梯 真身 70 > 化身 50 > 削弱 30〔削弱形每條抗性皆 < 化身·真身最堅〕)。
    assert phys("mehrunes_dagon") == 50 and phys("mehrunes_dagon_diminished") == 30


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
