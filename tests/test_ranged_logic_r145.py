"""R145 現實邏輯(群 4·方案 C):心智攻擊=魔法傷害(板甲擋不住凝視)、遠程攻擊無身體接觸
(荊棘反彈不了弩矢·隔空盾擊不了弩手·閃過龍息搆不到龍);戰吼/嚎叫維持物理(音波衝擊)。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, magic, mastery, stats
from tesrpg.synth import enchant_armor_id

gd = get_gamedata()

_PSYCHIC = {"魂縛凝視", "支配凝視", "魅惑凝視", "攝魂凝視", "懾魂凝視", "懾魂尖嘯", "懾心咒",
            "懾魂之嘯", "凝滯咒印", "棄絕者的詛咒", "衰朽詛咒"}
_RANGED = {"弩矢攢射", "鋼弩重矢", "精準弩擊", "銀箭射擊", "投擲碎石"}
_WARCRY = {"戰吼威壓", "威嚇怒吼", "血月嚎叫", "林間哀嚎"}


def _attacks(cid):
    c = gd.bestiary[cid]
    return ([c["attack"]] if c.get("attack") else []) + (c.get("attacks") or [])


def test_attack_typing_data():
    seen_p = seen_r = 0
    for cid in gd.bestiary:
        for a in _attacks(cid):
            nm = a.get("name", "")
            if nm in _PSYCHIC:
                assert a.get("element") == "magic", f"{cid}『{nm}』心智攻擊須為 magic"
                seen_p += 1
            if nm in _RANGED:
                assert a.get("ranged") is True, f"{cid}『{nm}』須標 ranged"
                seen_r += 1
            if nm in _WARCRY:
                assert not a.get("element"), f"{cid}『{nm}』戰吼=音波衝擊維持物理(使用者拍板)"
    assert seen_p >= 10 and seen_r >= 5


def _tank(riposte=True):
    c = build_character(gd, name="坦", sex="m", race="orsimer", birthsign="warrior", class_id="warrior")
    c.skills.update(block=100, heavy_armor=100, blade=90)
    c.attributes.update(strength=85, endurance=100)
    c.weapon = "steel_sword"; inventory.add_item(c, "steel_sword", 1)
    tid = enchant_armor_id("steel_cuirass", "thorns", "x", 5)
    inventory.add_item(c, tid, 1); inventory.equip_armor(c, gd, tid)
    inventory.add_item(c, "steel_shield", 1); inventory.equip_armor(c, gd, "steel_shield")
    if riposte:
        c.mastery_choices.update({"block_50": "shield_bash", "heavy_armor_50": "armor_reflect"})
    c.active_effects.append({"kind": "guard_stance", "turns": 99})
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 5000
    return c


def test_ranged_hits_trigger_no_reflect_no_riposte():
    for s in range(120):
        c = _tank()
        foe = combat.spawn_creature(gd, "master_hunter", RNG(1))
        hp0 = foe.health
        atk = next(a for a in _attacks("master_hunter") if a.get("ranged"))
        ev = combat.resolve_attack(foe, c, gd, RNG(s), attack=atk)
        if ev["hit"] and ev["damage"] > 0:
            assert foe.health == hp0, "弩矢命中不得觸發荊棘/反震/盾反(30 呎外反彈不到)"
            assert not magic.is_staggered(foe), "隔空盾擊不了弩手"


def test_melee_hits_still_trigger_reflect():
    reflected = False
    for s in range(120):
        c = _tank()
        foe = combat.spawn_creature(gd, "bandit", RNG(1)); foe.health = foe.max_health = 9999
        hp0 = foe.health
        ev = combat.resolve_attack(foe, c, gd, RNG(s))
        if ev["hit"] and ev["damage"] > 0 and foe.health < hp0:
            reflected = True
            break
    assert reflected, "近戰命中反傷組照常(回歸)"


def _dodger():
    """輕甲閃避者(on_evade 需非重甲=R141 gate;高雜技高敏捷=夠多落空樣本)。"""
    c = build_character(gd, name="閃", sex="m", race="bosmer", birthsign="thief", class_id="thief")
    c.skills.update(acrobatics=100, light_armor=100, blade=90)
    c.attributes.update(agility=100, speed=90)
    c.weapon = "steel_sword"; inventory.add_item(c, "steel_sword", 1)
    inventory.add_item(c, "leather_cuirass", 1); inventory.equip_armor(c, gd, "leather_cuirass")
    for node in gd.mastery:                      # 授予所有 on_evade 節點(輕甲/雜技樹)
        for o in node["options"]:
            if o.get("kind") == "on_evade":
                c.skills[node["skill"]] = max(c.skills.get(node["skill"], 0), node["threshold"])
                c.mastery_choices[node["id"]] = o["opt_id"]
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 5000
    return c


def test_on_evade_no_counter_vs_breath_or_bolt():
    def counters(attack):
        n = 0
        for s in range(200):
            c = _dodger()
            c._evade_counter_used = False
            foe = combat.spawn_creature(gd, "ancient_dragon", RNG(2)); foe.health = foe.max_health = 9999
            hp0 = foe.health
            ev = combat.resolve_attack(foe, c, gd, RNG(s), attack=dict(attack))
            if not ev["hit"] and foe.health < hp0:
                n += 1
        return n
    breath = next(a for a in _attacks("ancient_dragon") if a.get("element"))
    assert counters(breath) == 0, "閃過龍息搆不到龍(元素落空無反擊)"
    melee = next((a for a in _attacks("ancient_dragon") if not a.get("element")), None)
    if melee is not None:
        assert counters(melee) > 0, "閃過物理近戰仍可反擊(回歸)"


def test_gaze_bypasses_armor():
    """凝視=魔法傷害:同 raw 下,重甲角色吃凝視應遠高於吃等值物理(板甲擋不住心智入侵)。"""
    gaze = next(a for a in _attacks("vampire_lord") if a.get("name") == "魅惑凝視")
    assert gaze.get("element") == "magic"
    dmg_g = dmg_p = 0
    phys = {"name": "爪擊", "damage": gaze["damage"], "skill": gaze.get("skill", 60)}
    for s in range(300):
        c = _tank(riposte=False)
        foe = combat.spawn_creature(gd, "vampire_lord", RNG(3))
        ev = combat.resolve_attack(foe, c, gd, RNG(s), attack=dict(gaze))
        if ev["hit"]:
            dmg_g += ev["damage"]
        c2 = _tank(riposte=False)
        ev2 = combat.resolve_attack(foe, c2, gd, RNG(s), attack=dict(phys))
        if ev2["hit"]:
            dmg_p += ev2["damage"]
    assert dmg_g > dmg_p, "凝視(magic)須穿透護甲 > 等值物理(被甲吃掉)"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
