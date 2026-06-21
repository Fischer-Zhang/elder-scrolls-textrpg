"""各 build「完全體」對各 SOLO BOSS 的勝率模擬(非測試;手動跑:PYTHONPATH=. python3 sim_builds.py)。

對標 sim_assassin.py 的方法論,但橫跨多個 build。每場 1v1:玩家 build vs solo boss(spawn_creature,
raw·只 ±15% HP 變異·不縮放),回合制直到一方死或逾時。每回合忠實鏡像 run_battle 的維護:
  - 玩家行動(per-build policy:偷襲/施法/攻擊;麻痺/恐懼則跳過 = is_incapacitated)
  - boss 反擊(choose_attack 多攻擊曲目)
  - 回合末:意志回魔 + tick_effects(雙方)+ clamp_resources

⚠ 已知保真度邊界(看數字時必記):
  - 此戰鬥模型「無距離/走位」→ 弓手的安全射程不存在(弓手 ≈ 偷襲較弱的近戰);牆/風箏無法表現。
  - per-build policy 是「合理」非「完美」:法師選最佳元素 + 低血治療;戰士純輸出不格擋(最大 DPS);
    刺客低血隱遁(同 sim_assassin)。
  - **刻意排除**:戴德拉誓福 + 玩家自附魔武器/防具(會一致拉高所有 build 的勝率;此處量「近完全體」相對強弱)。
  - 純輔助(聖騎/治療)與純龜(大盾)build 不入列:傷害太低 → 必逾時,非「勝率」問題。
"""
from tesrpg.gamedata import get_gamedata
from tesrpg.creation import build_character
from tesrpg.systems import combat, magic, stats, inventory, mastery
from tesrpg.synth import enchant_armor_id
from tesrpg import formulas
from tesrpg.rng import RNG

gd = get_gamedata()

# --- 通用構築工具 -------------------------------------------------------
def _equip_set(c, material, pieces=("helmet", "cuirass", "gauntlets", "boots")):
    for slot in pieces:
        iid = f"{material}_{slot}"
        if iid in gd.armor:
            inventory.add_item(c, iid, 1)
            inventory.equip_armor(c, gd, iid)


def _choices(c, choices):
    for nid, oid in choices.items():
        try:
            mastery.choose(c, gd, nid, oid)
        except Exception:
            pass


# --- 各 build 完全體 -----------------------------------------------------
def make_assassin():
    c = build_character(gd, name="刺", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
    c.skills.update(sneak=100, blade=100, acrobatics=100, alchemy=60, scout=100, light_armor=100)
    c.attributes.update(agility=100, speed=100, endurance=85, strength=60, luck=60)
    c.weapon = "glass_dagger"
    inventory.add_item(c, "glass_dagger", 2); inventory.equip_offhand(c, gd, "glass_dagger")
    c.weapon_temper = {"glass_dagger": 6}
    c.factions["dark_brotherhood"] = 6
    _equip_set(c, "leather")
    _choices(c, {"sneak_100": "shadowblade", "blade_100": "savage", "sneak_75": "relentless_shadow",
                 "acrobatics_75": "evasion", "sneak_50": "deathmark", "smithing_75": "master_temper"})
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def make_archer():
    c = build_character(gd, name="弓", sex="male", race="bosmer", birthsign="shadow", class_id="archer")
    c.skills.update(marksman=100, sneak=100, acrobatics=100, scout=75, light_armor=100)
    c.attributes.update(agility=100, speed=100, endurance=85, strength=55)
    c.weapon = "daedric_bow"; inventory.add_item(c, "daedric_bow", 1)
    c.weapon_temper = {"daedric_bow": 6}
    c.factions["dark_brotherhood"] = 6
    _equip_set(c, "glass")
    _choices(c, {"marksman_100": "penetrator", "marksman_75": "aimed_shot", "marksman_50": "skirmish_shot",
                 "sneak_100": "shadowblade", "sneak_75": "relentless_shadow", "acrobatics_75": "evasion"})
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def make_warrior_sword():
    c = build_character(gd, name="劍", sex="male", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(blade=100, heavy_armor=100, block=100, smithing=100, athletics=75)
    c.attributes.update(strength=100, endurance=100, agility=65)
    c.weapon = "daedric_sword"; inventory.add_item(c, "daedric_sword", 1)
    c.weapon_temper = {"daedric_sword": 6}
    _equip_set(c, "daedric")
    inventory.add_item(c, "daedric_shield", 1); inventory.equip_armor(c, gd, "daedric_shield")
    _choices(c, {"blade_100": "savage", "block_100": "perfect_block", "heavy_armor_100": "ironhide",
                 "heavy_armor_50": "armor_reflect", "smithing_75": "master_temper"})
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def make_warrior_2h():
    c = build_character(gd, name="斧", sex="male", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(blunt=100, heavy_armor=100, smithing=100, athletics=75)
    c.attributes.update(strength=100, endurance=100, agility=60)
    c.weapon = "daedric_battleaxe"; inventory.add_item(c, "daedric_battleaxe", 1)
    c.weapon_temper = {"daedric_battleaxe": 6}
    _equip_set(c, "daedric")
    _choices(c, {"blunt_100": "sunder", "heavy_armor_100": "ironhide", "heavy_armor_75": "bulwark",
                 "smithing_75": "master_temper"})
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


_MAGE_DMG = ["lightning_bolt", "fireball", "ignite", "frostbite", "sparks", "flames"]


def make_mage():
    c = build_character(gd, name="法", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills.update(destruction=100, restoration=100, alteration=100, mysticism=100, conjuration=100, alchemy=75)
    c.attributes.update(intelligence=100, willpower=100, endurance=70)
    c.spells = _MAGE_DMG + ["close_wounds", "heal", "stoneflesh"]
    _equip_set(c, "archmage", pieces=("hood", "robe", "gloves", "slippers"))   # archmage 件名非 helmet/cuirass…
    _choices(c, {"destruction_100": "overload", "destruction_75": "efficient_destruction"})
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def make_battlemage():
    c = build_character(gd, name="戰法", sex="male", race="altmer", birthsign="mage", class_id="battlemage")
    c.skills.update(blade=100, destruction=100, alteration=75, heavy_armor=75, smithing=75)
    c.attributes.update(strength=85, intelligence=100, willpower=80, endurance=85)
    c.weapon = "daedric_sword"; inventory.add_item(c, "daedric_sword", 1)
    c.weapon_temper = {"daedric_sword": 6}
    c.spells = ["lightning_bolt", "fireball", "flames", "close_wounds"]
    _equip_set(c, "ebony")
    _choices(c, {"blade_100": "savage", "destruction_100": "overload"})
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def make_shield_reflect():
    """盾反坦(R42 反傷流):daedric_sword + 荊棘 daedric 全套(5×5%=25%)+ 重甲反震 + 盾反 shieldwall。
    被物理擊中 → 反彈 ~0.41 攻方 raw(thorns25 + armor_reflect6 + block_reflect10·力竭不計);**反傷物理限定**
    (元素 boss 完全不反=天然剋星)。perfect_block 反擊需主動格擋·此 policy 純攻不格擋故未用(by design 保守)。"""
    c = build_character(gd, name="盾反", sex="male", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(blade=100, heavy_armor=100, block=100, smithing=100, athletics=75)
    c.attributes.update(strength=85, endurance=100, agility=60)
    c.weapon = "daedric_sword"; inventory.add_item(c, "daedric_sword", 1)
    c.weapon_temper = {"daedric_sword": 6}
    for slot in ("helmet", "cuirass", "gauntlets", "boots", "shield"):   # 荊棘 daedric 5 件(同材質→保套裝 health+60)
        iid = enchant_armor_id(f"daedric_{slot}", "thorns", "x", 5)
        inventory.add_item(c, iid, 1); inventory.equip_armor(c, gd, iid)
    _choices(c, {"block_50": "shieldwall", "heavy_armor_50": "armor_reflect", "block_100": "perfect_block",
                 "heavy_armor_100": "ironhide", "smithing_75": "master_temper"})
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


BUILDS = {"assassin": make_assassin, "archer": make_archer, "warrior_1H": make_warrior_sword,
          "warrior_2H": make_warrior_2h, "shield_reflect": make_shield_reflect,
          "mage": make_mage, "battlemage": make_battlemage}

# --- per-build 戰鬥 policy ----------------------------------------------
def _regen(c):
    mr = formulas.magicka_regen_combat(c.attr("willpower"))
    if mr and c.birthsign != "atronach" and c.magicka < c.max_magicka:
        c.magicka = min(c.max_magicka, c.magicka + mr)


def _mage_act(c, boss, rng, st):
    # 開場先上石肌護盾(物理減傷;maxed 法師會預 buff)
    if not st.get("buffed") and magic.can_cast(c, gd, "stoneflesh"):
        st["buffed"] = True; magic.cast(c, gd, "stoneflesh", rng); return
    # 低血治療(撐得起就治)
    if c.health < c.max_health * 0.35:
        for h in ("close_wounds", "heal"):
            if magic.can_cast(c, gd, h):
                magic.cast(c, gd, h, rng); return
    # 選對 boss 最佳元素的可負擔傷害法術(magnitude×(1−resist))
    best, best_ev = None, -1
    for sid in _MAGE_DMG:
        if not magic.can_cast(c, gd, sid):
            continue
        eff = gd.spells[sid]["effect"]; el = eff.get("element"); mag = eff.get("magnitude", 0)
        res = boss.resist.get(el, 0) if hasattr(boss, "resist") else 0
        ev = mag * (1 - res / 100.0)
        if ev > best_ev:
            best, best_ev = sid, ev
    if best:
        magic.cast(c, gd, best, rng, target=boss, enemies=[boss], battle={"allies": []})
    else:                                   # 空藍 → 杖近戰(微傷)
        combat.player_attack_cost(c, gd); combat.resolve_attack(c, boss, gd, rng)


_BM_DMG = ["lightning_bolt", "fireball", "flames"]


def _battlemage_act(c, boss, rng, st):
    if c.health < c.max_health * 0.35 and magic.can_cast(c, gd, "close_wounds"):
        magic.cast(c, gd, "close_wounds", rng); return
    # 選 boss 最佳元素法術,**含威力係數 power_factor**(修審查:原只用 base magnitude 低估 37%);
    # 只在「該元素核彈 ≥ 一記 daedric_sword 揮擊」時才放,否則近戰更划算(resist-aware)。
    pf = (0.7 + c.skill("destruction") / 150.0) * formulas.intelligence_spell_potency(c.attr("intelligence"))
    best, best_dmg = None, 0.0
    for sid in _BM_DMG:
        if not magic.can_cast(c, gd, sid):
            continue
        eff = gd.spells[sid]["effect"]
        d = eff.get("magnitude", 0) * pf * (1 - boss.resist.get(eff.get("element"), 0) / 100.0)
        if d > best_dmg:
            best, best_dmg = sid, d
    if best and best_dmg >= 45:                       # 強元素核彈(否則 daedric_sword 近戰更划算)
        magic.cast(c, gd, best, rng, target=boss, enemies=[boss], battle={"allies": []}); return
    combat.player_attack_cost(c, gd); combat.resolve_attack(c, boss, gd, rng)


def _melee_sneak_act(c, boss, rng, st):
    """刺客/弓手:低血隱遁(重置偷襲),否則偷襲/攻擊。
    弓手不再每發都 aimed(原 bug:aimed 是偶發特殊動作非常駐 buff → 高估弓手);此處走純武器攻擊
    + 偷襲 + 隱遁(保守基準;偶發 aimed 蓄力會再添爆發,刻意不模型化以免高估)。"""
    if c.health < c.max_health * 0.45 and combat.can_vanish(c, gd) \
            and combat.try_vanish(c, 1, st["vanish"], rng, gd):
        # 保真:隱遁耗體力 + R71 隱遁不再無敵(對任何敵都不跳過攻擊)→ 純重置偷襲、照常挨打
        st["vanish"] += 1; combat.player_vanish_cost(c); st["opening"] = True
        st["skip_boss"] = False; return
    combat.player_attack_cost(c, gd)
    combat.resolve_attack(c, boss, gd, rng, sneak_attack=st["opening"])
    st["opening"] = False


def _attack_act(c, boss, rng, st):
    combat.player_attack_cost(c, gd); combat.resolve_attack(c, boss, gd, rng)


_POLICY = {"assassin": _melee_sneak_act, "archer": _melee_sneak_act,
           "warrior_1H": _attack_act, "warrior_2H": _attack_act, "shield_reflect": _attack_act,
           "mage": _mage_act, "battlemage": _battlemage_act}


def fight(build_name, boss_id, seed, max_rounds=80):
    c = BUILDS[build_name]()
    boss = combat.spawn_creature(gd, boss_id, RNG(seed * 9 + 1))
    rng = RNG(seed)
    act = _POLICY[build_name]
    st = {"opening": True, "vanish": 0, "aimed": build_name == "archer", "skip_boss": False}
    for _ in range(max_rounds):
        if not combat.is_alive(boss):
            return "win"
        if c.health <= 0:
            return "dead"
        c._evade_counter_used = False
        st["skip_boss"] = False
        if not magic.is_incapacitated(c):        # 麻痺/恐懼 → 跳過玩家行動
            act(c, boss, rng, st)
        if not combat.is_alive(boss):
            return "win"
        if not st["skip_boss"] and c.health > 0:  # boss 反擊(隱遁成功則撲空)
            combat.resolve_attack(boss, c, gd, rng, attack=combat.choose_attack(boss, rng, c))
        _regen(c)
        magic.tick_effects(c, gd)
        if combat.is_alive(boss):
            magic.tick_effects(boss, gd)
        stats.clamp_resources(c)
    return "win" if not combat.is_alive(boss) else "timeout"


def winrate(build_name, boss_id, n=300):
    return sum(fight(build_name, boss_id, s) == "win" for s in range(n)) / n


if __name__ == "__main__":
    solo = [bid for bid, b in gd.bestiary.items() if b.get("solo")]
    solo.sort(key=lambda b: gd.bestiary[b].get("max_health", 0))

    print("== 構築驗證(各 build 完全體的衍生數值)==")
    for name, mk in BUILDS.items():
        c = mk()
        print(f"  {name:11} HP {c.max_health:4}  MP {c.max_magicka:4}  FAT {c.max_fatigue:4}  "
              f"str{c.attr('strength')} agi{c.attr('agility')} int{c.attr('intelligence')}  weapon={c.weapon}")

    names = list(BUILDS)
    print("\n== 勝率矩陣(完全體 1v1·n=300·數字=擊殺 boss 的比率)==")
    print(f"  {'BOSS (HP·型)':28} " + " ".join(f"{n:>10}" for n in names))
    for bid in solo:
        b = gd.bestiary[bid]
        el = b.get("attack", {}).get("element") or "phys"
        tag = f"{bid}({b.get('max_health')}·{el})"
        row = " ".join(f"{winrate(n, bid):>9.0%} " for n in names)
        print(f"  {tag:28} {row}")
