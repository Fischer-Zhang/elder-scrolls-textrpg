"""法術與施法 —— 六大學派、戰鬥內外皆可施法。

設計與 combat 一致:純規則函式回傳事件;互動呈現在 main/ui。
施法會 learn-by-doing 鍛鍊對應學派技能;技能越高 → 費用越低、效果越強。
主動效果(護盾/恐懼/耗弱/擒魂/召喚)以回合為單位,在戰鬥迴圈逐回合 tick。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import progression, stats

CAST_XP = 0.5
SOUL_GEM_BY_DANGER = {
    1: "filled_petty_soul_gem", 2: "filled_lesser_soul_gem",
    3: "filled_common_soul_gem", 4: "filled_greater_soul_gem",
}


def _fail(message: str) -> dict:
    """施法失敗時的一致回傳格式(與成功時同樣帶 damage/killed)。"""
    return {"ok": False, "message": message, "damage": 0, "killed": False, "skill_events": []}


def effective_cost(char: Character, gamedata: GameData, spell_id: str) -> int:
    """技能越高,魔力消耗越低(最多打到原價的 60%)。"""
    sp = gamedata.spells[spell_id]
    skill = char.skill(sp["school"])
    return max(1, round(sp["cost"] * (1.0 - min(0.4, skill / 250.0))))


def _power(char: Character, school: str) -> float:
    """學派技能對效果強度的加成(0.7x ~ 1.37x)。"""
    return 0.7 + char.skill(school) / 150.0


def can_cast(char: Character, gamedata: GameData, spell_id: str) -> bool:
    return char.magicka >= effective_cost(char, gamedata, spell_id)


def known_spells(char: Character) -> list[str]:
    return list(char.spells)


def cast(char: Character, gamedata: GameData, spell_id: str, rng: RNG,
         target=None, battle: dict | None = None, enemies: list | None = None) -> dict:
    """施放法術。回傳事件 dict:
       {"ok","message","damage","skill_events","killed": bool}
    target 為單體攻擊的敵方 Creature;enemies 為 AoE(全體)法術的敵群清單;
    battle 為戰鬥情境字典(供召喚加入盟友);非戰鬥可為 None。
    """
    sp = gamedata.spells[spell_id]
    cost = effective_cost(char, gamedata, spell_id)
    if char.magicka < cost:
        return _fail("魔力不足。")

    char.magicka -= cost
    eff = sp["effect"]
    kind = eff["kind"]
    power = _power(char, sp["school"])
    msg = ""
    damage = 0
    killed = False

    if kind in ("damage", "damage_status"):
        if target is None:
            char.magicka += cost  # 無目標,退還
            return _fail("沒有施法目標。")
        element = eff.get("element", "magic")
        mult = formulas.resist_multiplier(entity_resist(target, gamedata), element)
        dmg = _scaled_damage(eff["magnitude"] * power * rng.roll(0.9, 1.1), mult)
        before = target.health
        target.health = max(0, target.health - dmg)   # 法術傷害無視物理護甲(但受元素抗性)
        damage = before - target.health               # 實際扣血(避免溢殺灌水)
        killed = target.health <= 0
        msg = f"{sp['name']}命中{target.name},造成 {dmg} 點魔法傷害{_resist_tag(mult)}!"
        if kind == "damage_status" and not killed:
            target.active_effects.append(make_status_effect(eff["status"]))
            msg += f" {target.name}{_status_verb(eff['status'])}!"

    elif kind == "heal":
        amt = round(eff["magnitude"] * power)
        before = char.health
        char.health = min(char.max_health, char.health + amt)
        msg = f"{sp['name']}回復了 {int(char.health - before)} 點生命。"

    elif kind == "restore_fatigue":
        before = char.fatigue
        char.fatigue = min(char.max_fatigue, char.fatigue + eff["magnitude"])
        msg = f"{sp['name']}回復了 {int(char.fatigue - before)} 點體力。"

    elif kind == "shield":
        mag = round(eff["magnitude"] * power)
        char.active_effects.append({"kind": "shield", "magnitude": mag, "turns": eff["turns"]})
        msg = f"{sp['name']}在你身上凝成護盾(護甲 +{mag},{eff['turns']} 回合)。"

    elif kind == "fear":
        if target is not None:
            target.active_effects.append({"kind": "fear", "turns": eff["turns"]})
            msg = f"{target.name}陷入了恐懼,{eff['turns']} 回合內不敢進攻!"

    elif kind == "weaken":
        if target is not None:
            target.active_effects.append({"kind": "weaken", "magnitude": eff["magnitude"],
                                          "turns": eff["turns"]})
            msg = f"{target.name}的攻勢被削弱了({eff['turns']} 回合)。"

    elif kind == "soul_trap":
        if target is not None:
            target.active_effects.append({"kind": "soul_trap", "turns": eff["turns"]})
            msg = f"擒魂咒纏上了{target.name} —— 若在咒效內擊殺,可擒獲其靈魂。"

    elif kind == "apply_status":
        dest = char if sp["target"] == "self" else target
        if dest is not None:
            dest.active_effects.append(make_status_effect(eff["status"]))
            who = "你" if dest is char else dest.name
            msg = f"{sp['name']} —— {who}{_status_verb(eff['status'])}。"

    elif kind in ("damage_all", "damage_status_all", "status_all"):
        living = [e for e in (enemies or []) if e.health > 0]
        if not living:
            char.magicka += cost
            return _fail("沒有可及的敵人。")
        element = eff.get("element", "magic")
        parts = []
        for e in living:
            if kind != "status_all":            # 含傷害的 AoE
                mult = formulas.resist_multiplier(entity_resist(e, gamedata), element)
                dmg = _scaled_damage(eff["magnitude"] * power * rng.roll(0.9, 1.1), mult)
                before = e.health
                e.health = max(0, e.health - dmg)
                loss = before - e.health        # 實際扣血(避免溢殺灌水)
                damage += loss
                parts.append(f"{e.name} {loss}{_resist_tag(mult)}")
            if kind in ("status_all", "damage_status_all") and e.health > 0:
                e.active_effects.append(make_status_effect(eff["status"]))
        if kind == "status_all":
            msg = f"{sp['name']} —— 全體敵人{_status_verb(eff['status'])}!"
        else:
            msg = f"{sp['name']}席捲全場 —— " + "、".join(parts) + "!"

    elif kind == "summon":
        if battle is None:
            msg = f"{sp['name']}需要在戰鬥中施放。"
        elif eff["creature"] not in gamedata.bestiary:   # 防資料錯字在戰鬥中崩潰
            char.magicka += cost
            return _fail(f"召喚失敗:未知的生物「{eff['creature']}」。")
        else:
            from tesrpg.systems import combat
            ally = combat.spawn_creature(gamedata, eff["creature"], rng)
            ally.summon_turns = eff["turns"]
            battle.setdefault("allies", []).append(ally)
            msg = f"你召喚出了{ally.name},它將為你而戰({eff['turns']} 回合)。"

    stats.clamp_resources(char)
    skill_events = progression.use_skill(char, gamedata, sp["school"], CAST_XP)
    return {"ok": True, "message": msg, "damage": damage, "killed": killed,
            "skill_events": skill_events}


# --- 主動效果 ----------------------------------------------------------
def active_shield(char: Character) -> int:
    return sum(e["magnitude"] for e in char.active_effects if e["kind"] == "shield")


def is_feared(creature) -> bool:
    return any(e["kind"] == "fear" and e["turns"] > 0 for e in creature.active_effects)


def is_paralyzed(creature) -> bool:
    return any(e["kind"] == "paralyze" and e["turns"] > 0 for e in creature.active_effects)


def is_incapacitated(creature) -> bool:
    """恐懼或麻痺 → 本回合無法行動。"""
    return is_feared(creature) or is_paralyzed(creature)


def weaken_factor(creature) -> float:
    """回傳攻擊傷害應乘上的係數(多個耗弱取最強)。"""
    factor = 1.0
    for e in creature.active_effects:
        if e["kind"] == "weaken" and e["turns"] > 0:
            factor = min(factor, 1.0 - e["magnitude"])
    return max(0.1, factor)


def has_soul_trap(creature) -> bool:
    return any(e["kind"] == "soul_trap" and e["turns"] > 0 for e in creature.active_effects)


_ELEMENT_CN = {"fire": "火焰", "frost": "冰霜", "shock": "雷電", "poison": "毒素", "magic": "魔法"}


def entity_resist(entity, gamedata) -> dict:
    """玩家抗性取自種族 + 穿戴裝備附魔/套裝(加總);怪物取自自身 resist。"""
    if isinstance(entity, Character):
        race = gamedata.races[entity.race].get("resist", {}) if gamedata else {}
        merged = dict(race)
        for elem, val in entity.equip_resist.items():     # 裝備抗性與種族抗性相加
            merged[elem] = merged.get(elem, 0) + val
        return merged
    return getattr(entity, "resist", {}) or {}


def _scaled_damage(base: float, mult: float) -> int:
    if mult <= 0:
        return 0
    return max(1, round(base * mult))


def _resist_tag(mult: float) -> str:
    if mult <= 0:
        return "(完全免疫)"
    if mult < 0.7:
        return "(被抵抗)"
    if mult > 1.15:
        return "(命中弱點!)"
    return ""


def make_status_effect(status: dict) -> dict:
    """把資料中的狀態定義({"status": "dot"...})正規化成 active_effects 條目({"kind": ...})。"""
    return {"kind": status["status"], "element": status.get("element"),
            "magnitude": status.get("magnitude", 0), "turns": status["turns"]}


def _status_verb(status: dict) -> str:
    k = status.get("status")
    if k == "dot":
        return f"陷入{_ELEMENT_CN.get(status.get('element'), '')}侵蝕({status['turns']} 回合)"
    if k == "paralyze":
        return f"被麻痺({status['turns']} 回合)"
    if k == "regen":
        return f"獲得再生({status['turns']} 回合)"
    return "受到法術影響"


def tick_effects(entity, gamedata=None) -> list[str]:
    """回合結束:先結算持續傷害/再生,再 turns-1、移除歸零者。回傳提示訊息。"""
    msgs: list[str] = []
    resist = entity_resist(entity, gamedata) if gamedata else {}
    name = getattr(entity, "name", "你")

    for e in entity.active_effects:
        if e["turns"] <= 0:
            continue
        if e["kind"] == "dot":
            mult = formulas.resist_multiplier(resist, e.get("element", "poison"))
            dmg = _scaled_damage(e["magnitude"], mult)
            if dmg > 0:
                entity.health = max(0, entity.health - dmg)
                msgs.append(f"{name}受到 {dmg} 點{_ELEMENT_CN.get(e.get('element'), '')}持續傷害。")
        elif e["kind"] == "regen":
            mx = getattr(entity, "max_health", None)
            if mx is not None:
                before = entity.health
                entity.health = min(mx, entity.health + e["magnitude"])
                if entity.health > before:
                    msgs.append(f"{name}的再生回復了 {int(entity.health - before)} 點生命。")

    for e in entity.active_effects:
        e["turns"] -= 1
    for e in list(entity.active_effects):
        if e["turns"] <= 0:
            entity.active_effects.remove(e)
            if e["kind"] == "shield":
                msgs.append("護盾消散了。")
            elif e["kind"] == "paralyze":
                msgs.append(f"{name}從麻痺中恢復。")
    return msgs


def soul_gem_for(creature) -> str | None:
    """擒魂成功時,依危險度給予對應的充能靈魂石。"""
    return SOUL_GEM_BY_DANGER.get(min(4, max(1, getattr(creature, "danger", 1))))
