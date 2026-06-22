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
    5: "filled_grand_soul_gem",                       # danger5 頂級魂(附魔深化 Phase 2)
}
# 空魂石填充循環:擒魂→填手上空魂石(白魂)。人形/有靈魂需黑魂石+法術擒魂(見 resolve_soul_capture)。
_EMPTY_BY_TIER = {1: "empty_petty_soul_gem", 2: "empty_lesser_soul_gem", 3: "empty_common_soul_gem",
                  4: "empty_greater_soul_gem", 5: "empty_grand_soul_gem"}
BLACK_SOUL_INFAMY = 2                                 # 囚禁有靈之魂=黑暗之舉,小幅惡名
# 秘術「驅散」可淨化的不良效果(只清控場/侵蝕,不動護盾/再生/結界/灌注等增益)
_DISPELLABLE = ("fear", "paralyze", "dot", "weaken", "stagger", "slow")
# 亡者復生:起出的屍體是「虛弱化的亡魂」→ 以原 HP 的此比例復生(避免滿血復生高 HP 精英遠超召喚物階)
REANIMATE_HP_FACTOR = 0.6


def _fail(message: str) -> dict:
    """施法失敗時的一致回傳格式(與成功時同樣帶 damage/killed)。"""
    return {"ok": False, "message": message, "damage": 0, "killed": False, "skill_events": []}


def effective_cost(char: Character, gamedata: GameData, spell_id: str) -> int:
    """技能越高,魔力消耗越低(最多打到原價的 60%);里程碑「過載」會抬高該學派魔耗。"""
    sp = gamedata.spells[spell_id]
    skill = char.skill(sp["school"])
    cost = sp["cost"] * (1.0 - min(0.4, skill / 250.0))
    cost *= mastery.spell_cost_factor(char, gamedata, sp["school"])
    cost *= formulas.willpower_cost_factor(char.attr("willpower"))   # R63 意志續航:過 115 漸近省魔
    return max(1, round(cost))                                       # max(1) 地板 → 永不免費施法


def _power(char: Character, gamedata: GameData, school: str) -> float:
    """學派技能對效果強度的加成(0.7x ~ 1.37x);里程碑「過載」+「奧術連鎖」+ R63 智力威力 + R68 法袍套裝威力再疊加。"""
    from tesrpg.systems import inventory   # 區域匯入避免循環(同 spell_fatigue_cost)
    return ((0.7 + char.skill(school) / 150.0 + mastery.spell_power_bonus(char, gamedata, school)
             + mastery.cascade_power(char, gamedata))   # 法師「奧術連鎖」:連續施法漸增威力
            * formulas.intelligence_spell_potency(char.attr("intelligence"))   # R63 智力 → 法術威力(過 100 漸近)
            * (1.0 + inventory.set_spell_power_bonus(char, gamedata)))   # R68 法袍套裝:法術威力(乘性,與智力威力疊乘)


def spell_fatigue_cost(char: Character, gamedata: GameData, spell_id: str) -> int:
    """施法的體力消耗(法師三系資源對稱):固定底耗 + 隨有效魔耗成長,再由運動降低
    (與近戰共用 fatigue_cost_factor),最後乘法袍套裝折扣。effective_cost 已含學派折扣與
    『過載』倍率 → 過載自動更耗體力。最低 1。"""
    from tesrpg.systems import inventory   # 區域匯入避免循環
    ec = effective_cost(char, gamedata, spell_id)
    raw = formulas.CAST_FATIGUE_BASE + formulas.CAST_FATIGUE_PER_MAGICKA * ec
    raw *= formulas.fatigue_cost_factor(char.skill("athletics"))
    raw *= inventory.cast_fatigue_factor(char, gamedata)   # 法袍(同材質整套)省體施法
    raw *= mastery.cascade_fatigue_factor(char, gamedata)  # 法師「奧術連鎖」:連發省體(乘在法袍折扣之後,獨立)
    return max(1, round(raw))


def can_cast(char: Character, gamedata: GameData, spell_id: str) -> bool:
    return char.magicka >= effective_cost(char, gamedata, spell_id)


def known_spells(char: Character) -> list[str]:
    return list(char.spells)


# 中庸·盟友指向(治療師援護 / 騎士號令):heal/shield/apply_status/empower 套用到同伴 Creature。
def _apply_to_allies(kind: str, eff: dict, power: float, dests: list) -> list[str]:
    names = []
    for d in dests:
        if kind == "heal":
            d.health = min(d.max_health, d.health + round(eff["magnitude"] * power))
        elif kind == "shield":
            d.active_effects.append({"kind": "shield", "magnitude": round(eff["magnitude"] * power),
                                     "turns": eff["turns"]})
        elif kind == "apply_status":
            d.active_effects.append(make_status_effect(eff["status"]))
        elif kind == "empower":
            # 號令增傷比照 heal/shield 吃施法 power(學派技能 + 力竭)→ 投資越深、鼓舞越強;
            # 維持分數型(不取整,否則 0.25 會被 round 成 0)。combat 端以 max 聚合,封堆疊暴衝。
            d.active_effects.append({"kind": "empower", "magnitude": round(eff["magnitude"] * power, 3),
                                     "turns": eff["turns"]})
        names.append(d.name)
    return names


def _ally_verb(kind: str) -> str:
    return {"heal": "回復了生命", "shield": "得到護盾庇護", "apply_status": "受到法術加持",
            "empower": "受號令鼓舞、戰意大振"}.get(kind, "受到法術影響")


def cast(char: Character, gamedata: GameData, spell_id: str, rng: RNG,
         target=None, battle: dict | None = None, enemies: list | None = None,
         corpses: list | None = None, mounted: bool = False) -> dict:
    """施放法術。回傳事件 dict:
       {"ok","message","damage","skill_events","killed": bool}
    target 為單體攻擊的敵方 Creature;enemies 為 AoE(全體)法術的「存活」敵群清單;
    corpses 為「亡者復生」可用的完整敵群清單(含已死者,死靈系專用,戰外為 None);
    battle 為戰鬥情境字典(供召喚加入盟友);非戰鬥可為 None。
    """
    sp = gamedata.spells[spell_id]
    cost = effective_cost(char, gamedata, spell_id)
    # 治療師「戰地搶救」:武裝中 + 施治療/援護術 → 本道近乎免費(覆寫成本,非注入額外行動)。
    triage_heal = (sp["effect"]["kind"] == "heal" or sp["target"] in ("ally", "allies"))
    triage_opt = mastery.triage(char, gamedata) if triage_heal else None
    triaged = triage_opt is not None and any(e.get("kind") == "triage_ready" and e.get("turns", 0) > 0
                                             for e in char.active_effects)
    if triaged:           # 折扣成本(旗標延到「治療確實施放」才消耗 → 失敗退費時不白費 buff)
        cost = max(0, round(cost * triage_opt.get("magicka_factor", 0.15)))
    if char.magicka < cost:
        return _fail("魔力不足。")

    char.magicka -= cost
    # 施法消耗體力(法師三系資源對稱;玩家專用——敵人/召喚走 combat.resolve_attack 不經此)。
    # 先擷取「扣體力前」的體力比例 → 本次施法不自我削弱(鏡像近戰:出招前的體力決定本擊)。
    # fatigue_before 為退費快照:任何「失敗退魔」分支都連體力一併還原(退魔卻不退體 = 不對稱資源損失)。
    fatigue_before = char.fatigue
    fatigue_ratio = fatigue_before / char.max_fatigue if char.max_fatigue > 0 else 0.0
    fat = spell_fatigue_cost(char, gamedata, spell_id)
    if triaged:           # 戰地搶救:急救亦折體力
        fat = max(1, round(fat * triage_opt.get("fatigue_factor", 0.25)))
    char.fatigue = max(0, fatigue_before - fat)
    eff = sp["effect"]
    kind = eff["kind"]
    power = _power(char, gamedata, sp["school"]) * formulas.cast_fatigue_power_factor(fatigue_ratio)
    # 法駒:騎乘作戰時法術增益(只在野外騎乘戰生效;mounted=False 處處中性,sim/地城不受影響)。
    if mounted:
        from tesrpg.systems import mounts
        power *= 1.0 + mounts.spell_bonus_dmg(char, gamedata, mounted)
    msg = ""
    damage = 0
    killed = False

    # 中庸·盟友指向(治療師援護 / 騎士號令):heal/shield/apply_status/empower 對同伴施放(僅戰鬥)。
    if sp["target"] in ("ally", "allies"):
        if battle is None:
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("這道法術需在戰鬥中對同伴施放。")
        dests = ([target] if sp["target"] == "ally" and target is not None and target.health > 0
                 else [a for a in battle.get("allies", []) if a.health > 0] if sp["target"] == "allies" else [])
        if not dests:
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("沒有可施放的同伴。")
        names = _apply_to_allies(kind, eff, power, dests)
        if triaged:       # 援護確實施放 → 此時才消耗戰地搶救旗標
            char.active_effects[:] = [e for e in char.active_effects if e.get("kind") != "triage_ready"]
        stats.clamp_resources(char)
        skill_events = progression.use_skill(char, gamedata, sp["school"], CAST_XP)
        return {"ok": True, "message": f"{sp['name']} —— {'、'.join(names)}{_ally_verb(kind)}。",
                "damage": 0, "killed": False, "skill_events": skill_events}

    if kind in ("damage", "damage_status"):
        if target is None:
            char.magicka += cost  # 無目標,退還(魔力 + 體力)
            char.fatigue = fatigue_before
            return _fail("沒有施法目標。")
        element = eff.get("element", "magic")
        mult = formulas.resist_multiplier(entity_resist(target, gamedata), element)
        dmg = _scaled_damage(eff["magnitude"] * power * rng.roll(0.9, 1.1), mult)
        if element == "shock":                         # 感電易傷(R75):依目標導電層放大電傷(抗性後)
            dmg = max(1, int(round(dmg * conduct_damage_multiplier(target))))
        before = target.health
        target.health = max(0, target.health - dmg)   # 法術傷害無視物理護甲(但受元素抗性)
        damage = before - target.health               # 實際扣血(避免溢殺灌水)
        killed = target.health <= 0
        if element == "shock" and not killed:          # 每次電擊 +1 層導電(夾 10·刷新 3 回合)
            add_conduct(target)
        msg = f"{sp['name']}命中{target.name},造成 {dmg} 點魔法傷害{_resist_tag(mult)}!"
        if kind == "damage_status" and not killed:
            st = eff["status"]
            if st.get("status") in _CONTROL_KINDS:   # 控場走集中 helper(R44:閉合潛在缺口,fear/paralyze 受 solo 管)
                if apply_control(target, st["status"], gamedata, rng,
                                 magnitude=st.get("magnitude", 0.0), turns=st["turns"]) == "applied":
                    msg += f" {target.name}{_status_verb(st)}!"
            else:
                target.active_effects.append(make_status_effect(st))   # dot 等非控場照舊
                msg += f" {target.name}{_status_verb(st)}!"
        # 里程碑「衝擊餘波」:該學派傷害法術命中時附加狀態(stagger/weaken/fear)→ 集中 helper(R44)
        if not killed:
            ohs = mastery.spell_on_hit(char, gamedata, sp["school"])
            if ohs and rng.chance(ohs.get("chance", 1.0)):
                apply_control(target, ohs["kind"], gamedata, rng,
                              magnitude=ohs.get("magnitude", 0.0), turns=ohs.get("turns", 1))
        # 戰法師「共鳴一擊」:毀滅傷害法術後武裝下一記近戰(灌半數法傷 + 引燃同系 DoT;combat 端讀取消耗)
        rs = mastery.resonant_strike(char, gamedata)
        if rs and sp["school"] == "destruction" and damage > 0:
            char.active_effects[:] = [e for e in char.active_effects if e.get("kind") != "resonance"]
            # magnitude 存「抗性未折算」基底(damage/mult):combat 消耗端會按打擊目標抗性再折算一次,
            # 同目標淨值恰為半數實際法傷 —— 存折算後值會雙重套抗(弱點目標最高灌到 2 倍)
            char.active_effects.append({"kind": "resonance", "element": element,
                                        "magnitude": round(damage / mult * rs.get("transfer", 0.5)),
                                        "dot_magnitude": rs.get("dot_magnitude", 4),
                                        "dot_turns": rs.get("dot_turns", 3), "turns": 2})
            msg += " 法力在你的兵刃上共鳴,蓄勢待發。"

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

    elif kind == "cure_disease":   # R53「淨疫術」:統一治癒(普通病 + 吸血/狼人潛伏期);不解已轉化詛咒
        from tesrpg.systems import diseases
        msg = f"{sp['name']} —— " + diseases.purify_message(diseases.purify(char, gamedata))

    elif kind == "shield":
        mag = round(eff["magnitude"] * power)
        char.active_effects.append({"kind": "shield", "magnitude": mag, "turns": eff["turns"]})
        msg = f"{sp['name']}在你身上凝成護盾(護甲 +{mag},{eff['turns']} 回合)。"

    elif kind == "ward":   # 秘術「結界」:吸收來襲法術/元素傷害的可耗盡池(吸魔變體按吸收量回魔)
        mag = round(eff["magnitude"] * power)
        char.active_effects[:] = [e for e in char.active_effects if e.get("kind") != "ward"]  # 重施去重 → 不疊無敵
        entry = {"kind": "ward", "magnitude": mag, "turns": eff["turns"]}
        if eff.get("absorb"):
            entry["absorb"] = eff["absorb"]
        char.active_effects.append(entry)
        extra = "・吸收部分法力" if eff.get("absorb") else ""
        msg = f"{sp['name']} —— 一道結界護住了你(可吸收 {mag} 點法術傷害{extra},{eff['turns']} 回合)。"

    elif kind == "weapon_imbue":   # 戰法師「奧術灌注」:自我增益 → 近戰加元素傷害(比照附魔,戰鬥內讀取)
        mag = round(eff["magnitude"] * power)
        char.active_effects.append({"kind": "weapon_imbue", "element": eff["element"],
                                    "magnitude": mag, "turns": eff["turns"]})
        msg = f"{sp['name']} —— 你的兵刃纏上了{_ELEMENT_CN.get(eff['element'], '')}之力(每擊 +{mag},{eff['turns']} 回合)。"

    elif kind == "bound_weapon":   # 召喚「束縛兵刃」:凝出法系近戰武器,取代裝備武器(無視物理護甲、可空手)
        # 存「基礎傷害」不乘 power:傷害在 combat._weapon_profile→attack_damage 隨咒術技能/力量縮放一次
        # (若此處再乘 power 會技能雙重縮放)。重施去重 → 不可疊成更強的刃。
        mag = eff["magnitude"]
        char.active_effects[:] = [e for e in char.active_effects if e.get("kind") != "bound_weapon"]
        char.active_effects.append({"kind": "bound_weapon", "element": eff.get("element", "magic"),
                                    "magnitude": mag, "turns": eff["turns"]})
        msg = f"{sp['name']} —— 你手中凝出一柄束縛兵刃(基礎傷害 {mag},隨咒術精進,{eff['turns']} 回合)。"

    elif kind == "fear":
        if target is not None:
            # R44:集中 helper —— solo BOSS 對 fear 由「完全免疫」改機率減免(SOLO_CONTROL_RESIST_CHANCE)
            res = apply_control(target, "fear", gamedata, rng, turns=eff["turns"])
            msg = (f"{target.name}陷入了恐懼,{eff['turns']} 回合內不敢進攻!" if res == "applied"
                   else f"{target.name}意志如淵,恐懼無從附身。")

    elif kind == "weaken":
        if target is not None:
            apply_control(target, "weaken", gamedata, rng, magnitude=eff["magnitude"], turns=eff["turns"])
            msg = f"{target.name}的攻勢被削弱了({eff['turns']} 回合)。"

    elif kind == "soul_trap":
        if target is not None:
            target.active_effects.append({"kind": "soul_trap", "turns": eff["turns"]})
            msg = f"擒魂咒纏上了{target.name} —— 若在咒效內擊殺,可擒獲其靈魂。"

    elif kind == "apply_status":
        dest = char if sp["target"] == "self" else target
        if dest is not None:
            st = eff["status"]
            if dest is not char and st.get("status") in _CONTROL_KINDS:   # 對敵控場走 helper(R44:閉合潛在缺口)
                apply_control(dest, st["status"], gamedata, rng,
                              magnitude=st.get("magnitude", 0.0), turns=st["turns"])
            else:                                                          # 自身/盟友增益、dot 照舊
                dest.active_effects.append(make_status_effect(st))
            who = "你" if dest is char else dest.name
            msg = f"{sp['name']} —— {who}{_status_verb(st)}。"

    elif kind == "dispel":   # 秘術「驅散」:淨化自身的不良控場/侵蝕效果(不動護盾/再生等增益)
        removed = [e for e in char.active_effects if e.get("kind") in _DISPELLABLE]
        char.active_effects[:] = [e for e in char.active_effects if e.get("kind") not in _DISPELLABLE]
        msg = (f"{sp['name']} —— 你驅散了身上的 {len(removed)} 道不良效果。" if removed
               else f"{sp['name']} —— 你身上沒有可驅散的不良效果。")

    elif kind in ("damage_all", "damage_status_all", "status_all"):
        living = [e for e in (enemies or []) if e.health > 0]
        if not living:
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("沒有可及的敵人。")
        element = eff.get("element", "magic")
        parts = []
        for e in living:
            if kind != "status_all":            # 含傷害的 AoE
                mult = formulas.resist_multiplier(entity_resist(e, gamedata), element)
                dmg = _scaled_damage(eff["magnitude"] * power * rng.roll(0.9, 1.1), mult)
                if element == "shock":          # 感電易傷(R75):每敵各依自身導電層放大電傷
                    dmg = max(1, int(round(dmg * conduct_damage_multiplier(e))))
                before = e.health
                e.health = max(0, e.health - dmg)
                loss = before - e.health        # 實際扣血(避免溢殺灌水)
                damage += loss
                if e.health > 0:                # 每敵各 +1 層導電
                    add_conduct(e)
                parts.append(f"{e.name} {loss}{_resist_tag(mult)}")
            if kind in ("status_all", "damage_status_all") and e.health > 0:
                st = eff["status"]
                if st.get("status") in _CONTROL_KINDS:   # 控場走集中 helper(R44:fear/paralyze 受 solo 機率減免)
                    apply_control(e, st["status"], gamedata, rng,
                                  magnitude=st.get("magnitude", 0.0), turns=st["turns"])
                else:                                    # dot/soul_trap 等照常(各敵獨立 dict,R17)
                    e.active_effects.append(make_status_effect(st))
        if kind == "status_all":
            msg = f"{sp['name']} —— 全體敵人{_status_verb(eff['status'])}!"
        else:
            msg = f"{sp['name']}席捲全場 —— " + "、".join(parts) + "!"

    elif kind == "summon":
        if battle is None:
            msg = f"{sp['name']}需要在戰鬥中施放。"
        elif eff["creature"] not in gamedata.bestiary:   # 防資料錯字在戰鬥中崩潰
            char.magicka += cost
            char.fatigue = fatigue_before
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

    elif kind == "reanimate":   # 召喚/死靈「亡者復生」:把一具非 solo 敵屍喚為限時盟友(復用召喚物生命週期)
        if battle is None:
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("亡者復生需要在戰鬥中施放。")
        from tesrpg.systems import combat
        corpse = next((e for e in (corpses or [])
                       if not combat.is_alive(e) and getattr(e, "template_id", None)
                       and e.template_id in gamedata.bestiary
                       and not gamedata.bestiary[e.template_id].get("solo")
                       and not getattr(e, "_reanimated", False)), None)
        if corpse is None:
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("周圍沒有可供復生的屍體。")
        corpse._reanimated = True   # 同一具屍體不可反覆復生(封無限刷盟友)
        ally = combat.spawn_creature(gamedata, corpse.template_id, rng)
        boon = factions.conjure_boon(char, gamedata)
        smod = mastery.summon_mod(char, gamedata)   # 刻意不讀 smod['extra']:復生綁定單屍(見 _reanimated),雙重召喚不適用
        fat_pen = formulas.cast_fatigue_power_factor(fatigue_ratio)
        # REANIMATE_HP_FACTOR 收斂高 HP 精英(虛弱化的亡魂);仍吃 boon/hp_bonus/力竭(與召喚對稱)
        hp_mult = REANIMATE_HP_FACTOR * (1 + boon) * (1 + smod.get("hp_bonus", 0.0)) * fat_pen
        ally.max_health = max(1, round(ally.max_health * hp_mult))
        ally.health = ally.max_health
        ally.summon_turns = eff["turns"] + int(boon * 3) + int(smod.get("turn_bonus", 0))
        battle.setdefault("allies", []).append(ally)
        msg = f"你以亡者復生喚起了{ally.name},它將為你而戰({ally.summon_turns} 回合)。"

    if triaged:           # 自我治療確實施放 → 消耗戰地搶救旗標(damage 等非治療術 triaged 必為 False)
        char.active_effects[:] = [e for e in char.active_effects if e.get("kind") != "triage_ready"]
    stats.clamp_resources(char)
    mastery.bump_cascade(char, gamedata)   # 法師「奧術連鎖」:成功施法 → 推進連鎖層(未選節點 no-op)
    skill_events = progression.use_skill(char, gamedata, sp["school"], CAST_XP)
    return {"ok": True, "message": msg, "damage": damage, "killed": killed,
            "skill_events": skill_events}


# --- 主動效果 ----------------------------------------------------------
def active_shield(char: Character) -> int:
    return sum(e["magnitude"] for e in char.active_effects if e["kind"] == "shield")


def consume_ward(char, dmg: float) -> tuple[float, int]:
    """秘術結界:吸收來襲法術/元素傷害。扣減 ward magnitude(耗盡即失效),回傳
    (剩餘傷害, 吸魔回魔量)。cast 端已重施去重 → 至多一道,取第一道未耗盡者。
    吸魔結界(absorb)按實際吸收量比例回魔;一般結界回魔 0。"""
    for e in char.active_effects:
        if e.get("kind") == "ward" and e.get("turns", 0) > 0 and e.get("magnitude", 0) > 0:
            absorbed = min(dmg, e["magnitude"])
            e["magnitude"] -= absorbed
            refund = round(absorbed * e["absorb"]) if e.get("absorb") else 0
            return dmg - absorbed, refund
    return dmg, 0


def _is_solo(creature, gamedata: GameData) -> bool:
    """BOSS 級(bestiary `solo`)→ 對控制型(fear/paralyze)免疫(R31;與 combat._is_solo 一致)。"""
    tid = getattr(creature, "template_id", None)
    return bool(tid and gamedata.bestiary.get(tid, {}).get("solo"))


def is_feared(creature) -> bool:
    return any(e["kind"] == "fear" and e["turns"] > 0 for e in creature.active_effects)


def is_paralyzed(creature) -> bool:
    return any(e["kind"] == "paralyze" and e["turns"] > 0 for e in creature.active_effects)


def is_staggered(creature) -> bool:
    """陣腳大亂(暗殺殘響):攻擊命中率下降一回合(不等於失能,仍會行動)。"""
    return any(e["kind"] == "stagger" and e["turns"] > 0 for e in creature.active_effects)


def is_slowed(creature) -> bool:
    """中毒遲緩(R31 遲緩毒):降先攻 + 命中(非失能,仍會行動)。"""
    return any(e["kind"] == "slow" and e["turns"] > 0 for e in creature.active_effects)


def slow_factor(creature) -> float:
    """遲緩減速比例(多個遲緩取最強,非相加;夾 0..0.6 防鎖死)。"""
    mag = max((e.get("magnitude", 0.0) for e in creature.active_effects
               if e["kind"] == "slow" and e["turns"] > 0), default=0.0)
    return max(0.0, min(0.6, mag))


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


def benumb_hit_penalty(creature) -> float:
    """凍麻(冰系法術控場·純減命中):直接從攻方命中率扣除的比例(多源取最強,非相加;夾 0..0.6)。
    刻意只減命中、不碰先攻(1v1 持久戰減先攻幾近空轉);鏡像 slow_factor 結構。"""
    mag = max((e.get("magnitude", 0.0) for e in creature.active_effects
               if e["kind"] == "benumb" and e["turns"] > 0), default=0.0)
    return max(0.0, min(0.6, mag))


# 感電易傷(R75 電系識別):電系法術命中 → 目標疊「導電 conduct」層,每層 +CONDUCT_PER_STACK
# 受電傷(夾 CONDUCT_MAX_STACKS 層=+30%);每次電擊刷新 CONDUCT_TURNS,3 回合內無新電擊則
# 整組清零(非逐層遞減,靠 tick turns 歸零移除)。**只放大電系法術傷害**(combat 武器/他系不讀)。
CONDUCT_PER_STACK = 0.03
CONDUCT_MAX_STACKS = 10
CONDUCT_TURNS = 3


def conduct_stacks(creature) -> int:
    e = next((x for x in creature.active_effects if x.get("kind") == "conduct" and x.get("turns", 0) > 0), None)
    return e.get("stacks", 0) if e else 0


def conduct_damage_multiplier(creature) -> float:
    """電系法術對該目標的傷害放大倍率(1 + 每層 0.03,夾 +30%)。電系傷害路徑專讀。"""
    return 1.0 + CONDUCT_PER_STACK * conduct_stacks(creature)


def add_conduct(creature) -> None:
    """命中電擊 → 疊一層導電(夾 CONDUCT_MAX_STACKS)+ 刷新計時;無則新建。"""
    e = next((x for x in creature.active_effects if x.get("kind") == "conduct" and x.get("turns", 0) > 0), None)
    if e:
        e["stacks"] = min(CONDUCT_MAX_STACKS, e.get("stacks", 0) + 1)
        e["turns"] = CONDUCT_TURNS
    else:
        creature.active_effects.append({"kind": "conduct", "stacks": 1, "turns": CONDUCT_TURNS})


# 控場 kind 分類(R44:集中施加判定)
_HARD_CONTROL = ("fear", "paralyze")     # 失能(經 is_incapacitated 跳過行動)→ 受抵抗/去重
_CONTROL_KINDS = ("fear", "paralyze", "stagger", "slow", "weaken", "benumb")


def apply_control(target, kind, gamedata, rng, *, magnitude=0.0, turns=1, source=None) -> str:
    """集中施加「控場 debuff」到 target,統一 solo/willpower 抵抗與去重(R44 單一決策點)。回傳:
      'applied'  —— 實際施加
      'resisted' —— 被抵抗(玩家意志 resisted_mind / solo BOSS 機率減免)
      'blocked'  —— 已有同硬控/同源效果生效中(去重防延長鎖定)

    硬控(fear/paralyze)= 失能控場:玩家以 willpower 抗、solo BOSS 以
    `SOLO_CONTROL_RESIST_CHANCE` 機率抗(取代舊「完全免疫」);軟控(stagger/slow/weaken)
    一律照施(solo 無免疫)→ 收斂鈍器內建 stagger 與其餘 stagger 路徑的不一致。
    source:帶來源標(如元素 rider `ench_chill`)→ 同源去重(雙持不疊兩份)。
    dot/soul_trap/deathmark 等非控場不走此 helper。"""
    hard = kind in _HARD_CONTROL
    if hard and any(e.get("kind") == kind and e.get("turns", 0) > 0 for e in target.active_effects):
        return "blocked"                                  # 去重:硬控不疊、不延長鎖定
    if source and any(e.get("source") == source and e.get("turns", 0) > 0 for e in target.active_effects):
        return "blocked"                                  # 同源去重(元素 rider 雙持不疊)
    if hard:
        if resisted_mind(target, kind, rng):              # 玩家意志(非玩家/非心智 → False,不變)
            return "resisted"
        if _is_solo(target, gamedata) and rng.chance(formulas.SOLO_CONTROL_RESIST_CHANCE):
            return "resisted"                             # solo BOSS 機率減免(R44)
    eff = {"kind": kind, "turns": turns}
    if magnitude:
        eff["magnitude"] = magnitude
    if source is not None:
        eff["source"] = source
    target.active_effects.append(eff)
    return "applied"


def has_soul_trap(creature) -> bool:
    return any(e["kind"] == "soul_trap" and e["turns"] > 0 for e in creature.active_effects)


_ELEMENT_CN = {"fire": "火焰", "frost": "冰霜", "shock": "雷電", "poison": "毒素",
               "magic": "魔法", "bleed": "撕裂"}


def entity_resist(entity, gamedata) -> dict:
    """玩家抗性取自種族 + 穿戴裝備附魔/套裝(加總);怪物取自自身 resist。"""
    if isinstance(entity, Character):
        race = gamedata.races[entity.race].get("resist", {}) if gamedata else {}
        merged = dict(race)
        # 出生星座抗性/弱點(學徒座魔法弱點、領主座火弱點;星座不可變 → 即時讀,免存檔欄/向後相容)
        for elem, val in (gamedata.birthsigns.get(entity.birthsign, {}).get("resist", {})
                          if gamedata else {}).items():
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in entity.equip_resist.items():     # 裝備抗性與種族抗性相加
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in entity.vampire_resist.items():   # 吸血鬼階級:耐霜/免疫疾病/火焰弱點
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in getattr(entity, "mastery_resist", {}).items():   # 技能里程碑 resist_fortify
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in getattr(entity, "werewolf_resist", {}).items():   # 狼人:疾病免疫(與吸血鬼互斥)
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in getattr(entity, "dagon_resist", {}).items():   # 達貢之力:烈焰之主 → 火抗
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in getattr(entity, "boon_resist", {}).items():   # 戴德拉誓福(R45;如晨昏之佑魔抗)
            merged[elem] = merged.get(elem, 0) + val
        for elem, val in getattr(entity, "potion_resist", {}).items():   # 限時抗元素藥水(R30)
            merged[elem] = merged.get(elem, 0) + val
        merged["magic"] = merged.get("magic", 0) + formulas.willpower_magic_resist(entity.attr("willpower"))  # R65 意志=精神壁壘
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
    if k == "benumb":
        return f"被凍麻,命中下降({status['turns']} 回合)"
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
            # 每回合重推的常駐光環護盾(盾牆護同袍 / 戰旗自護 / 同伴忠誠頂點 capstone:*)不報「消散」
            # —— 它其實是被持續刷新,非真消失。
            _src = e.get("source")
            if (e["kind"] == "shield" and _src not in ("shield_wall_aura", "standard_self")
                    and not (isinstance(_src, str) and _src.startswith("capstone:"))):
                msgs.append("護盾消散了。")
            elif e["kind"] == "ward":
                msgs.append("結界消散了。")
            elif e["kind"] == "bound_weapon":
                msgs.append("束縛兵刃消散了。")
            elif e["kind"] == "paralyze":
                msgs.append(f"{name}從麻痺中恢復。")
            elif e["kind"] == "fear":
                msgs.append(f"{name}自驚懼中回神。")
            elif e["kind"] == "slow":
                msgs.append(f"{name}體內的遲緩毒素消退。")
            elif e["kind"] == "weaken":
                msgs.append(f"{name}的攻勢恢復了氣力。")
            elif e["kind"] == "stagger":
                msgs.append(f"{name}重整了陣腳。")
            elif e["kind"] == "benumb":
                msgs.append(f"{name}自凍麻中回復了準頭。")
            elif e["kind"] == "conduct":
                msgs.append(f"{name}身上的導電消退了。")
    return msgs


def soul_tier_for(creature) -> int:
    """擒魂可得的魂階(= 危險度,夾 1–5)。"""
    return min(5, max(1, getattr(creature, "danger", 1)))


def soul_gem_for(creature) -> str | None:
    """擒魂成功時依危險度對應的充能靈魂石 id(舊式直給;新填充循環見 resolve_soul_capture)。"""
    return SOUL_GEM_BY_DANGER.get(soul_tier_for(creature))


def resolve_soul_capture(player, creature, gamedata) -> str | None:
    """擊殺擒魂結算(附魔深化 Phase 2):依手上**空魂石**填充。回傳玩家訊息(None=不顯示)。
    - 一般怪:填入「夠裝該階的最小空魂石」→ filled_<階>;無合適空魂石 → 魂逸散。
    - 人形/有靈(bestiary `sentient`):凡魂石盛不住 → 需手持**空黑魂石**且為**法術擒魂**(非武器)
      才囚成 filled_black(soul5),並 +infamy;否則逸散 → 縛魂術對人形/黑魂專屬。"""
    from tesrpg.systems import inventory
    tier = soul_tier_for(creature)
    sentient = gamedata.bestiary.get(getattr(creature, "template_id", ""), {}).get("sentient")
    spell_trapped = any(e.get("kind") == "soul_trap" and e.get("turns", 0) > 0 and e.get("src") != "weapon"
                        for e in getattr(creature, "active_effects", []))   # turns>0 比照 has_soul_trap:過期法咒不算
    if sentient:
        if spell_trapped and inventory.count_item(player, "empty_black_soul_gem") > 0:
            inventory.remove_item(player, "empty_black_soul_gem", 1)
            inventory.add_item(player, "filled_black_soul_gem", 1)
            player.infamy = getattr(player, "infamy", 0) + BLACK_SOUL_INFAMY
            return f"黑色擒魂 —— {creature.name}的靈魂被囚入黑魂石(惡名 +{BLACK_SOUL_INFAMY})。"
        return f"{creature.name}是有靈之輩,凡魂石盛不住其魂 —— 靈魂逸散(需空黑魂石 + 擒魂咒)。"
    for t in range(tier, 6):                          # 夠裝該階的最小空魂石
        if inventory.count_item(player, _EMPTY_BY_TIER[t]) > 0:
            inventory.remove_item(player, _EMPTY_BY_TIER[t], 1)
            filled = SOUL_GEM_BY_DANGER[tier]
            inventory.add_item(player, filled, 1)
            return f"擒魂成功 —— {gamedata.item_name(filled)} 充能。"
    return f"{creature.name}的靈魂無處可盛 —— 逸散了(備妥空魂石再來)。"
