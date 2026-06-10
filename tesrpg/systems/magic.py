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
from tesrpg.systems import factions, mastery, progression, stats

CAST_XP = 0.5
SOUL_GEM_BY_DANGER = {
    1: "filled_petty_soul_gem", 2: "filled_lesser_soul_gem",
    3: "filled_common_soul_gem", 4: "filled_greater_soul_gem",
}


def _fail(message: str) -> dict:
    """施法失敗時的一致回傳格式(與成功時同樣帶 damage/killed)。"""
    return {"ok": False, "message": message, "damage": 0, "killed": False, "skill_events": []}


def effective_cost(char: Character, gamedata: GameData, spell_id: str) -> int:
    """技能越高,魔力消耗越低(最多打到原價的 60%);里程碑「過載」會抬高該學派魔耗。"""
    sp = gamedata.spells[spell_id]
    skill = char.skill(sp["school"])
    cost = sp["cost"] * (1.0 - min(0.4, skill / 250.0))
    cost *= mastery.spell_cost_factor(char, gamedata, sp["school"])
    return max(1, round(cost))


def _power(char: Character, gamedata: GameData, school: str) -> float:
    """學派技能對效果強度的加成(0.7x ~ 1.37x);里程碑「過載」再疊加。"""
    return 0.7 + char.skill(school) / 150.0 + mastery.spell_power_bonus(char, gamedata, school)


def spell_fatigue_cost(char: Character, gamedata: GameData, spell_id: str) -> int:
    """施法的體力消耗(法師三系資源對稱):固定底耗 + 隨有效魔耗成長,再由運動降低
    (與近戰共用 fatigue_cost_factor),最後乘法袍套裝折扣。effective_cost 已含學派折扣與
    『過載』倍率 → 過載自動更耗體力。最低 1。"""
    from tesrpg.systems import inventory   # 區域匯入避免循環
    ec = effective_cost(char, gamedata, spell_id)
    raw = formulas.CAST_FATIGUE_BASE + formulas.CAST_FATIGUE_PER_MAGICKA * ec
    raw *= formulas.fatigue_cost_factor(char.skill("athletics"))
    raw *= inventory.cast_fatigue_factor(char, gamedata)   # 法袍(同材質整套)省體施法
    return max(1, round(raw))


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
    # 施法消耗體力(法師三系資源對稱;玩家專用——敵人/召喚走 combat.resolve_attack 不經此)。
    # 先擷取「扣體力前」的體力比例 → 本次施法不自我削弱(鏡像近戰:出招前的體力決定本擊)。
    fatigue_ratio = char.fatigue / char.max_fatigue if char.max_fatigue > 0 else 0.0
    char.fatigue = max(0, char.fatigue - spell_fatigue_cost(char, gamedata, spell_id))
    eff = sp["effect"]
    kind = eff["kind"]
    power = _power(char, gamedata, sp["school"]) * formulas.cast_fatigue_power_factor(fatigue_ratio)
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
        # 里程碑「衝擊餘波」:該學派傷害法術命中時附加狀態(stagger/weaken/fear)
        if not killed:
            ohs = mastery.spell_on_hit(char, gamedata, sp["school"])
            if ohs and rng.chance(ohs.get("chance", 1.0)):
                if ohs["kind"] == "stagger":
                    target.active_effects.append({"kind": "stagger", "turns": ohs.get("turns", 1)})
                elif ohs["kind"] == "weaken":
                    target.active_effects.append({"kind": "weaken", "magnitude": ohs.get("magnitude", 0.0),
                                                  "turns": ohs.get("turns", 1)})
                elif ohs["kind"] == "fear":
                    target.active_effects.append({"kind": "fear", "turns": ohs.get("turns", 1)})

    elif kind == "heal":
        # 九神騎士團:聖光眷顧 —— 治療回復量隨階級放大(只對會員;乘在溢盾計算之前)
        amt = round(eff["magnitude"] * power * (1 + factions.restoration_boon(char, gamedata)))
        before = char.health
        char.health = min(char.max_health, char.health + amt)
        msg = f"{sp['name']}回復了 {int(char.health - before)} 點生命。"
        # 里程碑「聖光·溢盾」:溢出生命上限的治療量轉為臨時護盾(走既有 shield 管線)。
        # cap 夾「溢盾總量」而非單次 → 反覆施放不能疊破 cap_ratio×生命上限(審查抓到的破口);
        # 用 source 標記只夾自家溢盾,不污染戰鬥內逐回合施放的一般 shield 法術額度。
        ward = mastery.overheal_ward(char, gamedata)
        if ward:
            overflow = (before + amt) - char.max_health
            if overflow > 0:
                cap_total = round(char.max_health * ward["cap_ratio"])
                current = sum(e["magnitude"] for e in char.active_effects
                              if e["kind"] == "shield" and e.get("source") == "overheal_ward")
                mag = min(round(overflow * ward["convert"]), max(0, cap_total - current))
                if mag > 0:
                    char.active_effects.append({"kind": "shield", "magnitude": mag,
                                                "turns": ward["turns"], "source": "overheal_ward"})
                    msg += f" 滿溢的聖光凝成護盾(護甲 +{mag},{ward['turns']} 回合)。"

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
            boon = factions.conjure_boon(char, gamedata)   # 神話黎明:達貢之佑強化召喚物
            smod = mastery.summon_mod(char, gamedata)      # 里程碑:雙重召喚 / 束縛兵刃
            # 力竭削弱召喚物 HP(只取體力因子、不取整個 power → 滿體 ×1.0 不動既有平衡;
            # 與 heal/shield/damage 同步符合「施法力竭法效降」對稱意圖)
            fat_pen = formulas.cast_fatigue_power_factor(fatigue_ratio)
            hp_mult = (1 + boon) * (1 + smod.get("hp_bonus", 0.0)) * fat_pen
            if hp_mult != 1.0:
                ally.max_health = max(1, round(ally.max_health * hp_mult))
                ally.health = ally.max_health
            bonus_turns = int(boon * 3) + int(smod.get("turn_bonus", 0))
            ally.summon_turns = eff["turns"] + bonus_turns
            battle.setdefault("allies", []).append(ally)
            extra_msg = ""
            if smod.get("extra"):     # 雙重召喚:額外多召一隻較弱的盟友
                for _ in range(int(smod["extra"])):
                    ally2 = combat.spawn_creature(gamedata, eff["creature"], rng)
                    ally2.max_health = max(1, round(ally2.max_health * smod.get("hp_factor", 0.6) * (1 + boon) * fat_pen))
                    ally2.health = ally2.max_health
                    ally2.summon_turns = ally.summon_turns
                    battle.setdefault("allies", []).append(ally2)
                extra_msg = "(雙重召喚:多一隻較弱的盟友)"
            blessed = "(達貢之佑加持)" if boon > 0 else ""
            msg = f"你召喚出了{ally.name}{blessed}{extra_msg},它將為你而戰({ally.summon_turns} 回合)。"

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


def is_staggered(creature) -> bool:
    """陣腳大亂(暗殺殘響):攻擊命中率下降一回合(不等於失能,仍會行動)。"""
    return any(e["kind"] == "stagger" and e["turns"] > 0 for e in creature.active_effects)


def is_incapacitated(creature) -> bool:
    """恐懼或麻痺 → 本回合無法行動。"""
    return is_feared(creature) or is_paralyzed(creature)


def resisted_mind(entity, status: str, rng) -> bool:
    """玩家以意志「精神韌性」抵抗心智控場(恐懼/麻痺)。非玩家或非心智狀態 → False(不抗)。
    base-40 中性:意志 40 抗性 0(行為等同改前)。"""
    from tesrpg.models import Character
    if not isinstance(entity, Character) or status not in ("fear", "paralyze"):
        return False
    return rng.chance(formulas.mind_resist_chance(entity.attr("willpower")))


def weaken_factor(creature) -> float:
    """回傳攻擊傷害應乘上的係數(多個耗弱取最強)。"""
    factor = 1.0
    for e in creature.active_effects:
        if e["kind"] == "weaken" and e["turns"] > 0:
            factor = min(factor, 1.0 - e["magnitude"])
    return max(0.1, factor)


def has_soul_trap(creature) -> bool:
    return any(e["kind"] == "soul_trap" and e["turns"] > 0 for e in creature.active_effects)


_ELEMENT_CN = {"fire": "火焰", "frost": "冰霜", "shock": "雷電", "poison": "毒素",
               "magic": "魔法", "bleed": "撕裂"}


def entity_resist(entity, gamedata) -> dict:
    """玩家抗性取自種族 + 穿戴裝備附魔/套裝(加總);怪物取自自身 resist。"""
    if isinstance(entity, Character):
        race = gamedata.races[entity.race].get("resist", {}) if gamedata else {}
        merged = dict(race)
        for elem, val in entity.equip_resist.items():     # 裝備抗性與種族抗性相加
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in entity.vampire_resist.items():   # 吸血鬼階級:耐霜/免疫疾病/火焰弱點
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in getattr(entity, "mastery_resist", {}).items():   # 技能里程碑 resist_fortify
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in getattr(entity, "werewolf_resist", {}).items():   # 狼人:疾病免疫(與吸血鬼互斥)
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
