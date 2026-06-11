"""刺客流派強化的單元測試:暗殺殘響/combo、雙持匕首、隱遁再襲、偵查技能。"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Creature
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic


def _assassin(sneak=70, blade=50, alchemy=40, weapon="iron_dagger"):
    gd = get_gamedata()
    c = build_character(gd, name="刺", sex="male", race="khajiit",
                        birthsign="shadow", class_id="assassin")
    c.skills["sneak"] = sneak
    c.skills["blade"] = blade
    c.skills["marksman"] = blade
    c.skills["alchemy"] = alchemy
    c.weapon = weapon
    return gd, c


def _dummy(hp=9999, armor=0, agility=40):
    return Creature(template_id="t", name="靶", strength=40, agility=agility, speed=40,
                    max_health=hp, health=hp, armor_rating=armor,
                    attack={"name": "揮擊", "damage": 10, "skill": 50})


def _sneak_until_nonlethal_hit(gd, c, target):
    """擲到一次『偷襲命中但沒殺死』的事件(偷襲命中率高,幾下內必中)。"""
    for i in range(40):
        target.health = target.max_health
        target.active_effects = []
        ev = combat.resolve_attack(c, target, gd, RNG(i), sneak_attack=True)
        if ev["hit"] and not ev["defender_dead"]:
            return ev
    raise AssertionError("偷襲始終沒有命中(命中下限應 >=0.9)")


# --- 暗殺殘響(武器 × 殘響矩陣)-----------------------------------------
def test_dagger_sneak_aftermath_staggers_and_bleeds():
    """武器 × 暗殺殘響矩陣:匕首=踉蹌+撕裂、弓=只踉蹌、劍=無殘響、致命一擊不留殘響;
    並驗撕裂幅度公式隨潛行/煉金成長、撕裂 dot 無視一般抗性確實掉血。"""
    # (1) 匕首段:踉蹌 + 撕裂(原斷言全保留)
    gd, c = _assassin(weapon="iron_dagger")
    target = _dummy()
    ev = _sneak_until_nonlethal_hit(gd, c, target)
    assert ev["aftermath"] and ev["aftermath"]["staggered"]
    assert ev["aftermath"]["bleed"] > 0
    assert magic.is_staggered(target)
    assert any(e["kind"] == "dot" and e.get("element") == "bleed" for e in target.active_effects)
    # (6) 撕裂 dot 延伸:匕首殘響掛上 bleed 的 target → tick 後確實掉血(無視一般抗性)
    before = target.health
    magic.tick_effects(target, gd)
    assert target.health < before

    # (2) 弓段:只踉蹌、無撕裂(各自重建 dummy/char 避免狀態污染)
    gd, c = _assassin(weapon="hunting_bow")
    target = _dummy()
    ev = _sneak_until_nonlethal_hit(gd, c, target)
    assert ev["aftermath"]["staggered"] and ev["aftermath"]["bleed"] == 0
    assert magic.is_staggered(target)
    assert not any(e.get("element") == "bleed" for e in target.active_effects)

    # (3) 劍段:無殘響
    gd, c = _assassin(weapon="iron_sword")
    target = _dummy()
    ev = _sneak_until_nonlethal_hit(gd, c, target)
    assert ev["aftermath"] is None
    assert not magic.is_staggered(target)

    # (4) 致命一擊段:被秒則不留殘響(獨立 setup)
    gd, c = _assassin(sneak=100, blade=100, weapon="glass_dagger")
    target = _dummy(hp=5)               # 一定被秒
    ev = combat.resolve_attack(c, target, gd, RNG(1), sneak_attack=True)
    assert ev["defender_dead"] and ev["aftermath"] is None

    # (5) 撕裂幅度公式(純公式,無 setup):隨潛行/煉金成長,下限=base
    lo = formulas.sneak_bleed_magnitude(0, 0)
    hi = formulas.sneak_bleed_magnitude(100, 80)
    assert hi > lo == formulas.SNEAK_BLEED_BASE


def test_staggered_enemy_hits_less_often():
    gd, c = _assassin()
    foe = _dummy(hp=200, agility=50)

    def hit_rate(staggered):
        hits = 0
        for i in range(500):
            c.health = c.max_health
            foe.active_effects = [{"kind": "stagger", "turns": 1}] if staggered else []
            if combat.resolve_attack(foe, c, gd, RNG(i + 1))["hit"]:
                hits += 1
        return hits / 500

    assert hit_rate(True) < hit_rate(False) - 0.15   # 踉蹌顯著降低敵人命中


# --- 雙持匕首 -----------------------------------------------------------
def test_equip_offhand_dagger_rules():
    from tesrpg.systems import inventory
    from tesrpg.models import Character
    gd, c = _assassin(weapon="iron_dagger")
    inventory.add_item(c, "iron_dagger", 1)        # 主手 1 把,需第 2 把才能同型雙持
    assert not inventory.equip_offhand(c, gd, "iron_dagger")   # 只有 1 把 → 不行
    inventory.add_item(c, "iron_dagger", 1)        # 現在共 2 把
    assert inventory.equip_offhand(c, gd, "iron_dagger")
    assert inventory.is_dual_wielding(c, gd)
    # 劍不能當副手
    inventory.add_item(c, "iron_sword", 1)
    assert not inventory.equip_offhand(c, gd, "iron_sword")
    # 存檔往返保留副手
    assert Character.from_dict(c.to_dict()).offhand == "iron_dagger"

    # (A) 雙持需匕首主手:主手是劍 → 雙持不成立、無加成傷(獨立 char 避免污染上方 offhand 狀態)
    gd2, c2 = _assassin(weapon="iron_sword")
    inventory.add_item(c2, "steel_dagger", 1)
    inventory.equip_offhand(c2, gd2, "steel_dagger")
    assert not inventory.is_dual_wielding(c2, gd2)
    assert inventory.dual_wield_bonus_damage(c2, gd2) == 0.0

    # (B) 雙持加成傷公式 = 副手匕首傷 × OFFHAND_DAMAGE_FACTOR
    #     (avg_hit() 800 次統計半段已捨棄;副手不吃偷襲倍率的紅線由 test_offhand_not_amplified_by_sneak_attack 守)
    gd3, c3 = _assassin(weapon="steel_dagger")
    inventory.add_item(c3, "steel_dagger", 2)
    assert inventory.equip_offhand(c3, gd3, "steel_dagger")
    assert inventory.dual_wield_bonus_damage(c3, gd3) == gd3.item("steel_dagger")["damage"] * formulas.OFFHAND_DAMAGE_FACTOR


def test_drop_breaks_pair_ends_dualwield():
    from tesrpg.systems import inventory
    gd, c = _assassin(weapon="iron_dagger")
    inventory.add_item(c, "iron_dagger", 2)          # 主手+副手共 2 把
    assert inventory.equip_offhand(c, gd, "iron_dagger")
    assert inventory.is_dual_wielding(c, gd)
    inventory.remove_item(c, "iron_dagger", 1)        # 只剩 1 把
    assert not inventory.is_dual_wielding(c, gd)       # 自動退出雙持
    assert c.offhand == ""                             # 殘留副手已被清除(修正 review minor)


def test_offhand_not_amplified_by_sneak_attack():
    """回歸(review major):副手傷害不吃偷襲倍率 → 滿練雙持仍秒不掉高血精英 frost_troll。"""
    from tesrpg.systems import inventory, stats
    gd = get_gamedata()
    c = build_character(gd, name="x", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
    c.skills.update(sneak=100, blade=100, alchemy=100); c.weapon = "glass_dagger"
    inventory.add_item(c, "glass_dagger", 2); inventory.equip_offhand(c, gd, "glass_dagger")
    stats.recompute_max_resources(c, gd, restore_full=True)
    kills = sum(combat.resolve_attack(c, combat.spawn_creature(gd, "frost_troll", RNG(i + 1)),
                                      gd, RNG(i * 7 + 3), sneak_attack=True)["defender_dead"]
                for i in range(600))
    assert kills / 600 < 0.30, f"雙持偷襲秒殺 frost_troll 率過高:{kills/600:.0%}"


def test_vanish_costs_fatigue():
    gd, c = _assassin()
    c.fatigue = c.max_fatigue
    combat.player_vanish_cost(c)
    assert c.fatigue < c.max_fatigue                   # 隱遁耗體力(壓制無限風箏)


# --- 隱遁再襲 -----------------------------------------------------------
def test_restealth_chance_drops_with_crowd_and_reuse():
    from tesrpg import formulas
    base = formulas.restealth_chance(70, 50, 1, 0)
    assert formulas.restealth_chance(70, 50, 3, 0) < base       # 敵人越多越難
    assert formulas.restealth_chance(70, 50, 1, 2) < base       # 重複用遞減
    assert 0.05 <= formulas.restealth_chance(0, 0, 9, 9) <= 0.90  # 夾限
    assert formulas.restealth_chance(100, 100, 1, 0) > formulas.restealth_chance(20, 0, 1, 0)


def test_vanish_is_sneak25_milestone():
    """隱遁=潛行 25 里程碑「隱遁之術」:base_skill≥25 解鎖(門檻認 base、附魔不可跨門檻)。"""
    from tesrpg.systems import mastery
    gd, c = _assassin(sneak=24)
    assert not mastery.has_vanish(c, gd) and not combat.can_vanish(c, gd)   # 24<25
    c.skills["sneak"] = 25
    assert mastery.has_vanish(c, gd) and combat.can_vanish(c, gd)           # 達 25 自動解鎖
    # 門檻只認 base_skill:+sneak 裝備加成把 skill() 推過 25 但 base 仍 24 → 不解鎖
    gd2, c2 = _assassin(sneak=24)
    c2.equip_skill_bonus = {"sneak": 10}                                    # skill()=34 但 base=24
    assert c2.skill("sneak") >= 25 and not combat.can_vanish(c2, gd2)
    # 無 gd fallback 路徑(combat.py:634,gamedata is None → 退回 base_skill>=VANISH_MIN_SNEAK):
    # combat.can_vanish(c) 無 gd 呼叫端的唯一保險,不可流失
    gd3, c3 = _assassin(sneak=5)
    assert not combat.can_vanish(c3)            # 不帶 gd、非潛行流派 → 不解鎖
    c3.skills["sneak"] = 40
    assert combat.can_vanish(c3)                # 不帶 gd、達門檻 → 解鎖


def test_vanish_decays_vs_lone_foe_even_relentless():
    """連環踏影對單一強敵(1 對 1)仍逐次遞減 → 反 solo boss 無限風箏;敵群(>1)仍免遞減。"""
    f = formulas.restealth_chance
    solo = [f(100, 100, 1, u, relentless=True) for u in (0, 1, 2, 3)]
    assert solo[0] > solo[1] > solo[2] > solo[3]                            # 一對一逐次遞減
    group = [f(100, 100, 2, u, relentless=True) for u in (0, 1, 2, 3)]
    assert group[0] == group[1] == group[2] == group[3]                    # 敵群中仍免遞減(連環踏影本意)
    # >3 敵群戰反制(crowd+horde penalty)仍強力壓制,即便連環踏影(紅線:平衡靠群體規模)
    assert f(100, 100, 4, 2, relentless=True) <= 0.20
    assert f(100, 100, 5, 2, relentless=True) <= 0.10


def test_single_option_milestone_announced_as_auto_grant():
    """隱遁之術=系統唯一單一 perk 節點 → 跨門檻事件標 single(措辭『習得』,不誤導去做不存在的二選一)。"""
    from tesrpg.systems import progression
    gd, c = _assassin(sneak=25)
    evs = []
    progression._on_skill_increase(c, gd, "sneak", evs)
    mc = [e for e in evs if e["type"] == "mastery_choice_ready"]
    assert any(e.get("single") and e.get("name") == "隱遁之術" for e in mc)   # 自動授予旗標 + 名稱
    c.skills["sneak"] = 50                              # 對照:二選一節點 → single=False
    evs2 = []
    progression._on_skill_increase(c, gd, "sneak", evs2)
    sneak50 = [e for e in evs2 if e.get("node_id") == "sneak_50"]
    assert sneak50 and sneak50[0].get("single") is False


# --- 偵查技能(第 22 個技能)+ 潛行撤退 ---------------------------------
def test_new_character_has_scout_trained_by_use():
    from tesrpg.models import Character
    from tesrpg.systems import progression
    gd, c = _assassin()
    # scout 是真正的潛行系技能(spec=stealth、入 skills_by_spec)
    # (len(gd.skills)==23 已被 test_smithing.test_smithing_is_a_skill 等強覆蓋,跨模組去重)
    assert "scout" in gd.skills and gd.skills["scout"]["spec"] == "stealth"
    assert "scout" in gd.skills_by_spec("stealth")
    assert "scout" in c.skills                          # 新角色含偵查
    # 舊存檔(缺 scout)仍可載入並靠 use_skill 成長
    d = c.to_dict(); d["skills"].pop("scout", None); d["skill_xp"].pop("scout", None)
    old = Character.from_dict(d)
    assert old.skill("scout") == 0
    before = old.skill("scout")
    for _ in range(200):
        progression.use_skill(old, gd, "scout", 1.0)
    assert old.skill("scout") > before                 # learn-by-doing 對新技能照常運作


def test_estimate_sneak_damage_reflects_build():
    from tesrpg.systems import inventory
    gd, c = _assassin(sneak=80, blade=60, weapon="steel_dagger")
    foe = _dummy(hp=200, armor=10)
    single = combat.estimate_sneak_damage(c, gd, foe)
    inventory.add_item(c, "steel_dagger", 2); inventory.equip_offhand(c, gd, "steel_dagger")
    dual = combat.estimate_sneak_damage(c, gd, foe)
    assert dual > single > 0                           # 雙持估傷更高


def test_stealth_retreat_chance_drops_with_group():
    from tesrpg import formulas
    solo = formulas.stealth_retreat_chance(70, 50, 40, 1)
    pack = formulas.stealth_retreat_chance(70, 50, 40, 4)
    assert pack < solo
    assert 0.10 <= formulas.stealth_retreat_chance(0, 0, 99, 9) <= 0.92


# --- 入場潛行檢定(B+C+E)----------------------------------------------
def test_stealth_approach_chance_factors():
    from tesrpg import formulas as F
    base = F.stealth_approach_chance(70, 40, 1, "light")
    assert F.stealth_approach_chance(100, 40, 1, "light") > base           # 潛行越高越易
    assert F.stealth_approach_chance(70, 40, 3, "light") < base            # 敵多更難
    assert F.stealth_approach_chance(70, 40, 1, "heavy") < base            # E:重甲噪音懲罰
    assert F.stealth_approach_chance(70, 40, 1, "light", night=True) > base   # 夜間掩護
    assert F.stealth_approach_chance(70, 40, 1, "light", scouted=True) > base  # B:偵查加成
    assert F.stealth_approach_chance(70, 40, 1, "light", surprise=True) < base  # C:被伏擊難先機
    assert 0.05 <= F.stealth_approach_chance(0, 99, 9, "heavy", surprise=True) <= 0.97
    # 重甲莽夫幾乎偷不到、輕甲高潛行很可靠
    assert F.stealth_approach_chance(10, 40, 1, "heavy") < 0.20
    assert F.stealth_approach_chance(100, 40, 1, "light", night=True) > 0.85

    # combat 包裝層:讀玩家實際穿著的甲種 → 穿上重甲後入場先機下降
    from tesrpg.systems import inventory, stats
    gd, c = _assassin(sneak=80)
    light = combat.stealth_approach_chance(c, [_dummy()], gd)
    inventory.add_item(c, "iron_cuirass", 1); inventory.equip_armor(c, gd, "iron_cuirass")
    stats.recompute_max_resources(c, gd)
    heavy = combat.stealth_approach_chance(c, [_dummy()], gd)
    assert heavy < light


def test_prep_budget_tiers_and_summon_gate():
    """偵查掙得的備戰預算分級(<20→0、20/50/75→1/2/3)+ 召喚門檻鎖高 scout。"""
    assert formulas.prep_budget(0) == 0 and formulas.prep_budget(19) == 0
    assert formulas.prep_budget(20) == 1 and formulas.prep_budget(49) == 1
    assert formulas.prep_budget(50) == 2 and formulas.prep_budget(74) == 2
    assert formulas.prep_budget(75) == 3 and formulas.prep_budget(100) == 3
    assert formulas.PREP_SUMMON_MIN_SCOUT == 50   # 召喚這類高價值備戰鎖在 scout>=50


def test_prep_phase_preloads_summon_and_buff():
    """備戰階段:召喚預載進 battle['allies'](解開場佔回合)、增益上 active_effects;
    低 scout 無召喚選項。需以腳本化 ui.menu 驅動。"""
    import io
    from rich.console import Console
    from tesrpg.state import GameState, GameTime
    import tesrpg.main as M
    from tesrpg.ui import console as ui
    gd = get_gamedata()
    orig_console, orig_menu = ui.console, ui.menu
    ui.console = Console(file=io.StringIO(), width=100)
    try:
        c = build_character(gd, name="法", sex="male", race="altmer", birthsign="mage", class_id="mage")
        c.skills["scout"] = 80
        c.spells = ["oakflesh", "conjure_familiar"]
        c.max_magicka = 300; c.magicka = 300
        st = GameState(player=c, time=GameTime(), rng=RNG(1))
        battle = {"allies": []}
        seq = iter([("summon",), ("conjure_familiar",), ("buff",), ("oakflesh",)])
        def script(title, options, allow_back=False):
            keys = [o[0] for o in options]
            nxt = next(seq, None)
            return None if nxt is None else (nxt[0] if nxt[0] in keys else None)
        ui.menu = script
        M._prep_phase(st, gd, [combat.spawn_creature(gd, "wolf", RNG(2))], battle, 3)
        assert any(a.template_id == "summoned_familiar" for a in battle["allies"]), "召喚未預載進 allies"
        assert any(e.get("kind") == "shield" for e in c.active_effects), "增益未上身"
        # 低 scout(30):備戰頂層不得出現召喚選項
        c.skills["scout"] = 30
        cap = {}
        ui.menu = lambda t, o, allow_back=False: cap.setdefault("keys", [x[0] for x in o]) and None
        M._prep_phase(st, gd, [], {"allies": []}, 1)
        assert "summon" not in cap["keys"], "低 scout 不該能召喚"
    finally:
        ui.console, ui.menu = orig_console, orig_menu


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_assassin OK")
