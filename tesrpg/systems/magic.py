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
            * (1.0 + inventory.set_spell_power_bonus(char, gamedata)           # R68 法袍套裝:法術威力(乘性,與智力威力疊乘)
                   + inventory.staff_spell_power(char, gamedata)              # R77 持杖施法焦點:法術威力(與套裝相加)
                   + getattr(char, "boon_spell_power", 0.0)))                 # R78b 大法師通悟誓福:法術威力(與套裝/法杖相加)


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
            d.active_effects.append(make_status_effect(_scaled_status(eff["status"], power)))   # R76 HoT/DoT 吃威力
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


# ── 支援施法 AI(R86 同伴 / R87 敵方·陣營無關 core + 兩薄 wrapper)──────────────
# 輔助型施法者依其 `spells`(同伴=companions.json·敵怪=bestiary.json)對「自己這一側」主動施放支援:
# 法系→治療(反應式)、盾衛→護盾 / 領袖→激勵(主動式)。複用 `_apply_to_allies`(非玩家耦合的套用
# 路徑),**不碰 magic.cast**(cast 玩家專用,讀 magicka/skill/attr,Creature 無)。🔴 平衡:固定
# power=1.0(不吃智力/裝備)、HP 門檻觸發治療、冷卻、與既有 buff(capstone 光環/自身)去重。
# **只在 main.run_battle 的 ally/enemy phase 呼叫**(sim_assassin 走自有 `_round`·sim_builds 1v1
# → 永不呼叫此路徑·sim byte-identical)。
COMPANION_HEAL_THRESHOLD = 0.55   # 池中(含玩家)HP 比最低者低於此 → 反應式治療
COMPANION_SUPPORT_COOLDOWN = 2    # 任一支援後的冷卻回合(active_effects support_cd;tick_effects 遞減)
ENEMY_SUPPORT_POWER = 0.35        # R87 敵方支援幅度因子(<1:同伴維持 1.0·敵治療不全補小血量怪 → 威脅但可破解;sim 調校)
_COMPANION_HEAL_KINDS = ("heal", "apply_status")   # 反應式(直接治療 / HoT)
_COMPANION_BUFF_KINDS = ("shield", "empower")      # 主動式(護盾 / 激勵)


def _co_hp_ratio(e) -> float:
    mx = getattr(e, "max_health", 0) or 1
    return e.health / mx


def _co_has_kind(entity, kind: str) -> bool:
    return any(x.get("kind") == kind and x.get("turns", 0) > 0
               for x in getattr(entity, "active_effects", []))


def _support_act(caster, spells, pool, gamedata, exclude_from_empower=(), power=1.0,
                 cooldown=COMPANION_SUPPORT_COOLDOWN) -> dict | None:
    """陣營無關的支援施法決策(R86 同伴 / R87 敵方 共用 core)。`pool`=施法者這一側的成員(含 self)。
    回施放結果 dict(用本回合)或 None(→ 呼叫端走攻擊)。優先序:① 反應式治療(池中 HP 比 < 門檻)
    ② 主動式增益(目標缺該 buff)。冷卻中或無 spells → None。掃 active_effects 去重。
    `exclude_from_empower`=不套激勵者(玩家被 combat `not _is_player` 守門 → 同伴側排除玩家);
    `power`=幅度因子(同伴 1.0;敵方 `ENEMY_SUPPORT_POWER`<1·治療不全補小血量怪 → 可破解)。"""
    if not spells or _co_has_kind(caster, "support_cd"):
        return None
    res = (_support_try_heal(caster, spells, pool, gamedata, power)
           or _support_try_buff(caster, spells, pool, gamedata, exclude_from_empower, power))
    if res:
        caster.active_effects.append({"kind": "support_cd", "turns": cooldown})
    return res


def companion_support_act(companion, player, allies, gamedata) -> dict | None:
    """R86 輔助型同伴支援(角色感知)。pool=[player]+存活同伴(治療/護盾照顧英雄);empower 排除玩家
    (玩家被 combat `not _is_player` 守門 → rally 只益同伴)。"""
    from tesrpg.systems import combat
    spells = list(gamedata.companions.get(getattr(companion, "template_id", ""), {}).get("spells", []) or [])
    pool = [player] + [a for a in allies if combat.is_alive(a)]
    return _support_act(companion, spells, pool, gamedata, exclude_from_empower=(player,))


def enemy_support_act(enemy, enemies, gamedata) -> dict | None:
    """R87 敵方支援施法者(對稱 R86):法系/祭司怪治療/護盾/號令其他敵人。pool=存活敵人(含 self);
    敵群無玩家 → empower 全套。spells 讀 bestiary[tid]。**只由 main.run_battle 敵方階段呼叫**。"""
    from tesrpg.systems import combat
    spells = list(gamedata.bestiary.get(getattr(enemy, "template_id", ""), {}).get("spells", []) or [])
    pool = [e for e in enemies if combat.is_alive(e)]     # 含 self(self 必活)
    return _support_act(enemy, spells, pool, gamedata, power=ENEMY_SUPPORT_POWER)


SUMMON_SUPPORT_POWER = 0.8   # R106 召喚物支援施法幅度(< 玩家 1.0·固定·不隨召喚主威力爆走)


def summon_support_act(summon, player, allies, gamedata) -> dict | None:
    """R106 召喚物支援施法(如召喚治療精靈):spells 讀 **bestiary**[tid](召喚物是 bestiary 生物·非
    companions.json → 不能走 companion_support_act);pool=[player]+存活盟友(照顧英雄與其他召喚物);
    empower 排除玩家(rally 只益盟友);固定 power(不隨召喚主成長)。**只由 main.run_battle ally 階段呼叫**。"""
    from tesrpg.systems import combat, mastery
    spells = list(gamedata.bestiary.get(getattr(summon, "template_id", ""), {}).get("spells", []) or [])
    pool = [player] + [a for a in allies if combat.is_alive(a)]
    mod = mastery.summon_casting_mod(player, gamedata)   # R106 咒靈共鳴:法術召喚物施法更強更頻繁(無此里程碑 → 用預設 0.8/CD2)
    return _support_act(summon, spells, pool, gamedata, exclude_from_empower=(player,),
                        power=mod.get("power", SUMMON_SUPPORT_POWER),
                        cooldown=mod.get("cooldown", COMPANION_SUPPORT_COOLDOWN))


def _support_try_heal(caster, spells, pool, gamedata, power=1.0):
    """反應式治療:池中最低 HP 比 < 門檻才施。regen(HoT)只在無人持有時施(不疊);否則直接治療。"""
    heals = [s for s in spells if gamedata.spells[s]["effect"]["kind"] in _COMPANION_HEAL_KINDS]
    if not heals:
        return None
    lowest = min(pool, key=_co_hp_ratio)
    if _co_hp_ratio(lowest) >= COMPANION_HEAL_THRESHOLD:
        return None
    living = [e for e in pool if e.health > 0]
    for s in heals:                                                    # regen(AoE HoT):無人持有才施(避免疊)
        eff = gamedata.spells[s]["effect"]
        if eff["kind"] == "apply_status" and all(not _co_has_kind(e, eff["status"]["status"]) for e in living):
            return _support_cast(caster, s, living, gamedata, power)
    hurt_n = sum(1 for e in pool if _co_hp_ratio(e) < COMPANION_HEAL_THRESHOLD)
    aoe = [s for s in heals if gamedata.spells[s]["effect"]["kind"] == "heal"
           and gamedata.spells[s]["target"] == "allies"]
    if aoe and hurt_n >= 2:                                            # ≥2 人傷且有 AoE → AoE 直接治療
        return _support_cast(caster, aoe[0], living, gamedata, power)
    single = [s for s in heals if gamedata.spells[s]["effect"]["kind"] == "heal"
              and gamedata.spells[s]["target"] == "ally"]
    if single:                                                         # 否則單體援護最低者
        return _support_cast(caster, single[0], [lowest], gamedata, power)
    return None


def _support_try_buff(caster, spells, pool, gamedata, exclude_from_empower=(), power=1.0):
    """主動式增益:目標缺該 buff 才施(與既有 buff/capstone 光環去重)。
    shield 護池中最脆且無盾者;empower 套缺激勵者(排除 `exclude_from_empower`,如同伴側的玩家)。"""
    from tesrpg.systems import combat
    for s in spells:
        kind = gamedata.spells[s]["effect"]["kind"]
        if kind == "shield":
            cand = [e for e in pool if e.health > 0 and not _co_has_kind(e, "shield")]
            if cand:
                return _support_cast(caster, s, [min(cand, key=_co_hp_ratio)], gamedata, power)
        elif kind == "empower":
            troops = [a for a in pool if all(a is not x for x in exclude_from_empower)
                      and combat.is_alive(a) and not _co_has_kind(a, "empower")]
            if troops:
                return _support_cast(caster, s, troops, gamedata, power)
    return None


def _support_cast(caster, spell_id, dests, gamedata, power=1.0) -> dict:
    """套用支援法術到 dests(power 幅度因子;複用 `_apply_to_allies`)。回 UI 結果。"""
    sp = gamedata.spells[spell_id]
    names = _apply_to_allies(sp["effect"]["kind"], sp["effect"], power, dests)
    return {"ok": True, "spell": spell_id,
            "message": f"{caster.name}施展「{sp['name']}」 —— {'、'.join(names)}{_ally_verb(sp['effect']['kind'])}。"}


def cast(char: Character, gamedata: GameData, spell_id: str, rng: RNG,
         target=None, battle: dict | None = None, enemies: list | None = None,
         corpses: list | None = None, mounted: bool = False, state=None) -> dict:
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
    from tesrpg.systems import inventory   # R77 持杖施法焦點(元素直擊加傷);區域匯入避循環
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
        resist = entity_resist(target, gamedata)
        eroding = mastery.has_arcane_erosion(char, gamedata)   # R120 秘蝕頂點:削目標魔抗 → 輔助「所有」傷害魔法(火/冰/雷亦吃 magic 抗)
        if eroding and erosion_stacks(target):
            resist = {**resist, "magic": max(0, resist.get("magic", 0) - erosion_resist_reduction(target))}   # 破抗:降魔抗·floored≥0
        mult = formulas.resist_multiplier(resist, element)
        dmg = _scaled_damage(eff["magnitude"] * power * rng.roll(0.9, 1.1), mult)
        if element == "shock":                         # 感電易傷(R75):依目標導電層放大電傷(抗性後)
            dmg = max(1, int(round(dmg * conduct_damage_multiplier(target))))
        dmg += round(inventory.staff_element_flat(char, gamedata, element) * mult)   # R77 持杖同系直擊加傷(吃抗性)
        before = target.health
        target.health = max(0, target.health - dmg)   # 法術傷害無視物理護甲(但受元素抗性)
        damage = before - target.health               # 實際扣血(避免溢殺灌水)
        killed = target.health <= 0
        if element == "shock" and not killed:          # 每次電擊 +1 層導電(夾 10·刷新 3 回合)
            add_conduct(target)
        if eroding and not killed:                     # R120 每次傷害法術 +1 層秘蝕(削魔抗,任何傷害元素皆疊·輔助全體傷害魔法)
            add_erosion(target)
        if eff.get("deepen_erosion") and not killed:   # R121 湮識(秘術終極):命中永久提升該敵秘蝕上限(本場·單敵)→ 秘蝕可蝕更深
            target._deep_erosion = True
        msg = f"{sp['name']}命中{target.name},造成 {dmg} 點魔法傷害{_resist_tag(mult)}!"
        if kind == "damage_status" and not killed:
            st = eff["status"]
            if st.get("status") in _CONTROL_KINDS:   # 控場走集中 helper(R44:閉合潛在缺口,fear/paralyze 受 solo 管)
                # R122 聖光驅散只對不死系:holy 法術的控場對活人無效(靈魂灼傷驅不動活人)
                if eff.get("holy") and not _is_undead(target, gamedata):
                    pass
                elif apply_control(target, st["status"], gamedata, rng,
                                   magnitude=st.get("magnitude", 0.0), turns=st["turns"]) == "applied":
                    msg += f" {target.name}{_status_verb(st)}!"
            else:
                target.active_effects.append(make_status_effect(_scaled_status(st, power)))   # R76 DoT 吃威力
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

    elif kind == "heal" and sp.get("smite_undead") and target is not None and _is_undead(target, gamedata):
        # R123 聖騎士:治療能量對不死是烈焰 —— 指向不死敵的治療法術造傷(而非療癒),element magic(吃 magic 抗)。
        # 🔴 只對不死(targeting 只讓 smite 治療指向不死敵);對活物治療法術永遠零傷害 → 恢復系對活人零遠程輸出。
        mult = formulas.resist_multiplier(entity_resist(target, gamedata), "magic")
        dmg = _scaled_damage(eff["magnitude"] * power * formulas.HEAL_SMITE_FACTOR, mult)
        before = target.health
        target.health = max(0, target.health - dmg)
        damage = before - target.health
        killed = target.health <= 0
        msg = f"{sp['name']}的聖光灼燒{target.name},造成 {dmg} 點傷害{_resist_tag(mult)}!"

    elif kind == "heal":
        # 九神騎士團:聖光眷顧 —— 治療回復量隨階級放大(只對會員;乘在溢盾計算之前)
        # R107 瑪拉之佑:治療法術加成(同槽相加;無祝福 → +0 逐位元組同;僅 heal kind,不碰 HoT/同伴 AI)
        from tesrpg.systems import divines
        amt = round(eff["magnitude"] * power
                    * (1 + factions.restoration_boon(char, gamedata) + divines.heal_power_bonus(char)))
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

    elif kind == "radiant":   # R123 破曉之光(終極):治全隊 + 灼燒全體不死(生命燒盡死亡的極致;皆吃威力)
        heal_amt = round(eff.get("heal", 0) * power)
        healed = []
        for d in [char] + ([a for a in battle.get("allies", []) if a.health > 0] if battle else []):
            b = d.health
            d.health = min(getattr(d, "max_health", b), d.health + heal_amt)
            if d.health > b:
                healed.append("你" if d is char else d.name)
        parts = []
        for e in [x for x in (enemies or []) if x.health > 0 and _is_undead(x, gamedata)]:
            mult = formulas.resist_multiplier(entity_resist(e, gamedata), "magic")
            dmg = _scaled_damage(eff["magnitude"] * power, mult)
            b = e.health
            e.health = max(0, e.health - dmg)
            damage += b - e.health
            parts.append(f"{e.name} {b - e.health}{_resist_tag(mult)}")
        seg = []
        if parts:
            seg.append("聖光焚盡 " + "、".join(parts))
        if healed:
            seg.append("、".join(healed) + "沐光回復")
        msg = f"{sp['name']} —— 破曉的光輝普照全場!" + ("　" + ";".join(seg) + "。" if seg else "")
        stats.clamp_resources(char)

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
        # R106 束縛兵刃 archetype 差異化:存 archetype → combat 據此給原型身份(釘錘擊暈 stagger 等);
        # 仍走咒術技能傷害 + 元素(無視物理護甲)。無 archetype(舊 bound_sword)→ 行為不變。
        # R106 束縛精通:多駐留 turn_bonus 回合(無里程碑 → +0 不變)。
        bturns = eff["turns"] + mastery.bound_mastery_mod(char, gamedata).get("turn_bonus", 0)
        char.active_effects.append({"kind": "bound_weapon", "element": eff.get("element", "magic"),
                                    "magnitude": mag, "turns": bturns, "archetype": eff.get("archetype")})
        msg = f"{sp['name']} —— 你手中凝出一柄束縛兵刃(基礎傷害 {mag},隨咒術精進,{bturns} 回合)。"

    elif kind in ("charm", "invisibility", "feather", "detect_life", "telekinesis"):   # R104 實用/幻術 + R121 念力:限時自我增益(戰鬥外社交/潛行/探索/地城)
        from tesrpg.systems import spellfx
        hours = eff.get("hours", 4)
        if state is not None:
            spellfx.apply(char, state, kind, hours)
        _flavor = {
            "charm": "你周身縈起蠱惑的魅力,言語間更易取信於人。",
            "invisibility": "你的身形融入空氣,隱沒於無形之中。",
            "feather": "一股輕靈之力托起你的行囊,負擔霎時輕了許多。",
            "detect_life": "生機在你感官中亮起 —— 你能預先察覺周遭潛伏的生靈。",
            "telekinesis": "一股無形念力纏繞指尖 —— 你已能隔空撥動遠處的機栝與封印。",         # R121 念力
        }
        msg = f"{sp['name']} —— {_flavor.get(kind, '')}"

    elif kind == "scry":   # R121 靈視/靈識:地城揭露法術(實際揭露由地城「靈識揭露」動作處理;此處為誤經一般施法路徑的安全回覆)
        char.magicka += cost              # 退還(靈視須在地城中對準目標施展,非一般自我增益)
        char.fatigue = fatigue_before
        return _fail("靈視之法須在地城中對準一格施展 —— 於地城探索時選「🔮 靈識揭露」。")

    elif kind == "calm":   # R104 幻術安撫:對每個非 solo 敵人擲檢定(成功率隨敵數非線性遞減);全數安撫可從容脫戰
        living = [e for e in (enemies or []) if e.health > 0]
        if not living:
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("沒有可安撫的敵人。")
        n = len(living)
        calmed = []
        for e in living:
            if rng.chance(formulas.calm_chance(char.skill("illusion"), char.attr("personality"), n)):
                if apply_control(e, "calm", gamedata, rng, turns=eff["turns"]) == "applied":
                    calmed.append(e.name)
        if calmed:
            msg = f"{sp['name']} —— 你以幻術平息了{'、'.join(calmed)}的殺意,牠們茫然佇立、暫失戰意。"
        else:
            msg = f"{sp['name']} —— 但眼前的敵人殺意如鐵,未被安撫。"

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
                st2 = _scaled_status(st, power)                             # R76 DoT/HoT 吃威力
                if st2.get("status") == "consecration":                    # R122 聖化領域
                    cb = mastery.consecration_bonus(char, gamedata)         # 聖化壁壘:守護頂點加大減傷幅度
                    if cb:
                        st2 = {**st2, "magnitude": round(st2.get("magnitude", 0.0) + cb, 3)}
                    # 刷新非疊加:重施覆蓋舊光環(避免兩道並存→舊者到期誤報「黯淡」+ 減傷不疊加,審查 nit)
                    dest.active_effects[:] = [e for e in dest.active_effects if e.get("kind") != "consecration"]
                dest.active_effects.append(make_status_effect(st2))
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
        eroding = mastery.has_arcane_erosion(char, gamedata)   # R120 秘蝕頂點:削目標魔抗 → 輔助「所有」傷害魔法
        parts = []
        repelled = []          # R122 聖光驅散(turn_undead):實際被驅散的不死系名(供訊息如實呈現)
        undead_present = False  # 場上是否有不死系(區隔「無不死」vs「有不死但抵抗/已懼」→ 訊息不誤導)
        for e in living:
            if kind != "status_all":            # 含傷害的 AoE
                resist = entity_resist(e, gamedata)
                if eroding and erosion_stacks(e):
                    resist = {**resist, "magic": max(0, resist.get("magic", 0) - erosion_resist_reduction(e))}   # 破抗:降魔抗·floored≥0
                mult = formulas.resist_multiplier(resist, element)
                dmg = _scaled_damage(eff["magnitude"] * power * rng.roll(0.9, 1.1), mult)
                if element == "shock":          # 感電易傷(R75):每敵各依自身導電層放大電傷
                    dmg = max(1, int(round(dmg * conduct_damage_multiplier(e))))
                dmg += round(inventory.staff_element_flat(char, gamedata, element) * mult)   # R77 持杖同系直擊加傷
                before = e.health
                e.health = max(0, e.health - dmg)
                loss = before - e.health        # 實際扣血(避免溢殺灌水)
                damage += loss
                if e.health > 0:                # 每敵各 +1 層(電=導電〔R75·shock 閘=對齊單體〕·秘蝕=R120 頂點·任何傷害元素)
                    if element == "shock":
                        add_conduct(e)
                    if eroding:
                        add_erosion(e)
                parts.append(f"{e.name} {loss}{_resist_tag(mult)}")
            if kind in ("status_all", "damage_status_all") and e.health > 0:
                st = eff["status"]
                if st.get("status") in _CONTROL_KINDS:   # 控場走集中 helper(R44:fear/paralyze 受 solo 機率減免)
                    # R122 聖光驅散(turn_undead)只對不死系:holy 群體控場對活人無效
                    if eff.get("holy") and not _is_undead(e, gamedata):
                        continue
                    if eff.get("holy"):
                        undead_present = True   # 不死系在場(不論驅散成功/被抵抗/已懼 → 訊息可區隔)
                    if apply_control(e, st["status"], gamedata, rng,
                                     magnitude=st.get("magnitude", 0.0), turns=st["turns"]) == "applied":
                        repelled.append(e.name)
                else:                                    # dot/soul_trap 等照常(各敵獨立 dict,R17)
                    e.active_effects.append(make_status_effect(_scaled_status(st, power)))   # R76 DoT 吃威力
        if kind == "status_all":
            if eff.get("holy"):   # R122 驅散亡者:如實呈現三態(驅散成功 / 不死抵抗 / 場上無不死)
                if repelled:
                    msg = f"{sp['name']} —— 聖光乍現,{'、'.join(repelled)}倉皇退避!"
                elif undead_present:
                    msg = f"{sp['name']} —— 聖光灼過不死之軀,但牠們的意志未被驅散。"
                else:
                    msg = f"{sp['name']} —— 但眼前沒有可驅散的不死之物,聖光徒然閃耀。"
            else:
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
            from tesrpg.systems import combat, necromancy
            # R106C 死靈經濟:token 閘 + 亡者軍團上限(僅真·亡者〔undead〕受限;
            # 既有召喚無 token_cost/undead → tc=0/不判上限 → 全跳過,byte-identical)。
            tc = necromancy.spend_cost(char, eff.get("token_cost", 0))
            if tc > getattr(char, "soul_tokens", 0):
                char.magicka += cost
                char.fatigue = fatigue_before
                return _fail("靈魂 token 不足,無法喚起亡者。")
            if eff.get("undead") and necromancy.undead_count(battle) >= necromancy.undead_field_cap(char):
                char.magicka += cost
                char.fatigue = fatigue_before
                return _fail("你的亡者軍團已達上限,無法再喚起更多亡者。")
            ally = combat.spawn_creature(gamedata, eff["creature"], rng)
            boon = factions.conjure_boon(char, gamedata)   # 神話黎明:達貢之佑強化召喚物
            smod = mastery.summon_mod(char, gamedata)      # 里程碑:持久召喚(turn_bonus)
            um = mastery.undead_mastery_mod(char, gamedata) if eff.get("undead") else {}   # R106C 亡者統御:真·亡者更強韌兇猛
            # R105 召喚師深化:召喚物強度(HP + 傷害)隨召喚主的 conjuration 威力成長。
            # `power`(:245)已 = _power(conjuration)〔技能+法術威力+智力+奧術連鎖〕× 力竭因子 → 直接複用;
            # 再乘 (1+達貢之佑)〔階級〕,夾 SUMMON_POWER_CAP 防 apex spell-power 暴衝(「初始弱」靠 bestiary 基礎下修)。
            scale = min(formulas.SUMMON_POWER_CAP, power * (1 + boon))

            def _empower_summon(cre, hp_factor=1.0):
                if eff.get("undead"):
                    # 真·亡者(raise_thrall):**分軸縮放**(使用者拍板)——conjuration 技能 → 生命(undead_conj_scale·
                    # 較緩·初始更弱)·法術威力 → 攻擊(undead_attack_scale·不含技能)。再疊亡者統御 + 永久亡者生命。
                    uscale = necromancy.undead_conj_scale(char)                                    # 技能 → 生命
                    cre.summon_power = necromancy.undead_attack_scale(char, gamedata) * (1 + um.get("dmg_bonus", 0.0))   # 法術威力 → 攻擊
                    cre.max_health = (max(1, round(cre.max_health * uscale * (1 + smod.get("hp_bonus", 0.0))
                                                   * (1 + um.get("hp_bonus", 0.0)) * hp_factor))
                                      + necromancy.undead_health_bonus(char))   # 亡者生命永久平坦加值
                    cre._undead = True   # 真·亡者旗(暫態,不入檔):戰後回收 / 軍團上限 / 亡者統御
                else:
                    cre.summon_power = scale                   # 傷害側乘子:resolve_attack 讀取(非召喚者無此屬性 → ×1.0 byte-identical)
                    cre.max_health = max(1, round(cre.max_health * scale * (1 + smod.get("hp_bonus", 0.0)) * hp_factor))
                cre.health = cre.max_health

            _empower_summon(ally)
            bonus_turns = int(boon * 3) + int(smod.get("turn_bonus", 0))
            ally.summon_turns = eff["turns"] + bonus_turns
            battle.setdefault("allies", []).append(ally)
            extra_msg = ""
            if smod.get("extra"):     # 雙重召喚:額外多召一隻較弱的盟友(現無節點提供 extra,保留相容)
                for _ in range(int(smod["extra"])):
                    ally2 = combat.spawn_creature(gamedata, eff["creature"], rng)
                    _empower_summon(ally2, hp_factor=smod.get("hp_factor", 0.6))
                    ally2.summon_turns = ally.summon_turns
                    battle.setdefault("allies", []).append(ally2)
                extra_msg = "(雙重召喚:多一隻較弱的盟友)"
            if tc > 0:
                char.soul_tokens = getattr(char, "soul_tokens", 0) - tc
            blessed = "(達貢之佑加持)" if boon > 0 else ""
            token_msg = f"(靈魂 token −{tc},餘 {char.soul_tokens})" if tc > 0 else ""
            msg = f"你召喚出了{ally.name}{blessed}{extra_msg}{token_msg},它將為你而戰({ally.summon_turns} 回合)。"

    elif kind == "reanimate":   # 召喚/死靈「亡者復生」:把一具非 solo 敵屍喚為限時盟友(復用召喚物生命週期)
        if battle is None:
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("亡者復生需要在戰鬥中施放。")
        from tesrpg.systems import combat, necromancy
        corpse = next((e for e in (corpses or [])
                       if not combat.is_alive(e) and getattr(e, "template_id", None)
                       and e.template_id in gamedata.bestiary
                       and not gamedata.bestiary[e.template_id].get("solo")
                       and not getattr(e, "_reanimated", False)), None)
        if corpse is None:
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("周圍沒有可供復生的屍體。")
        # R106C 死靈經濟:強化復生(reanimate_thrall)才吃 token;軍團上限計入(base 亡者復生無 token_cost → tc=0)
        tc = necromancy.spend_cost(char, eff.get("token_cost", 0))
        if tc > getattr(char, "soul_tokens", 0):
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("靈魂 token 不足,無法奴役此亡者。")
        if necromancy.undead_count(battle) >= necromancy.undead_field_cap(char):
            char.magicka += cost
            char.fatigue = fatigue_before
            return _fail("你的亡者軍團已達上限,無法再奴役更多亡者。")
        corpse._reanimated = True   # 同一具屍體不可反覆復生(封無限刷盟友)
        ally = combat.spawn_creature(gamedata, corpse.template_id, rng)
        boon = factions.conjure_boon(char, gamedata)
        smod = mastery.summon_mod(char, gamedata)   # 刻意不讀 smod['extra']:復生綁定單屍(見 _reanimated),雙重召喚不適用
        um = mastery.undead_mastery_mod(char, gamedata)   # R106C 亡者統御:復生的亡者恆真·亡者
        fat_pen = formulas.cast_fatigue_power_factor(fatigue_ratio)
        # base_factor:舊 spell 無 hp_factor 鍵 → REANIMATE_HP_FACTOR(0.6)逐位元組同;reanimate_thrall 帶 1.0 滿血
        base_factor = eff.get("hp_factor", REANIMATE_HP_FACTOR)
        uscale = necromancy.undead_conj_scale(char)   # 技能 → 生命(較緩·初始更弱)
        # 虛弱化的亡魂;仍吃 boon/hp_bonus/力竭(與召喚對稱)+ 亡者統御 + conjuration 技能縮放(生命)
        hp_mult = base_factor * (1 + boon) * (1 + smod.get("hp_bonus", 0.0)) * (1 + um.get("hp_bonus", 0.0)) * fat_pen * uscale
        ally.max_health = max(1, round(ally.max_health * hp_mult)) + necromancy.undead_health_bonus(char)   # 亡者生命永久平坦加值
        ally.health = ally.max_health
        ally.summon_power = necromancy.undead_attack_scale(char, gamedata) * (1 + um.get("dmg_bonus", 0.0))   # 法術威力 → 攻擊(分軸)
        ally.summon_turns = eff["turns"] + int(boon * 3) + int(smod.get("turn_bonus", 0)) + int(eff.get("turn_bonus", 0))
        ally._undead = True   # 復生產物恆真·亡者:戰後回收 / 軍團上限 / 亡者統御
        battle.setdefault("allies", []).append(ally)
        if tc > 0:
            char.soul_tokens = getattr(char, "soul_tokens", 0) - tc
        token_msg = f"(靈魂 token −{tc},餘 {char.soul_tokens})" if tc > 0 else ""
        msg = f"你以亡者復生喚起了{ally.name}{token_msg},它將為你而戰({ally.summon_turns} 回合)。"

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


def _is_undead(creature, gamedata: GameData) -> bool:
    """不死系(R122 聖騎士):bestiary `undead` 旗標,或 R106 復生屍體的暫態 `_undead` 旗標
    (讓死靈師從敵屍復生的亡者也算不死 → 聖光/驅散一致對待)。聖光傷害對其放大、驅散只對其生效。"""
    if getattr(creature, "_undead", False):
        return True
    tid = getattr(creature, "template_id", None)
    return bool(tid and gamedata.bestiary.get(tid, {}).get("undead"))


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


def is_calm(creature) -> bool:
    """幻術安撫(R104):敵意被平息 → 本回合不行動(同 fear/paralyze 走 is_incapacitated 閘)。"""
    return any(e["kind"] == "calm" and e["turns"] > 0 for e in creature.active_effects)


def is_incapacitated(creature) -> bool:
    """恐懼 / 麻痺 / 安撫 → 本回合無法行動。"""
    return is_feared(creature) or is_paralyzed(creature) or is_calm(creature)


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


# 秘蝕(R120 秘術破抗「輔助」頂點·capstone-gated):持頂點者的**任何傷害法術**命中 → 目標疊「秘蝕
# erosion」層,每層**削減目標 EROSION_RESIST_PER_STACK 點通用魔法抗性**(夾 EROSION_MAX_STACKS 層 = −15·
# **floored ≥0:只蝕穿既有抗性、不製造弱點**)。因火/冰/雷(MAGIC_ELEMENTS)亦吃 magic 抗 → 削 magic 抗
# **輔助所有傷害魔法**(非僅秘術 magic 系),破抗=降魔抗、非直接增傷。每次命中刷新 EROSION_TURNS,3 回
# 合內無新傷害法術則整組清零(靠 tick turns 歸零)。**僅 mastery.has_arcane_erosion 頂點者施加·純法術
# 傷害路徑**(combat 武器/非頂點者不讀 → sim byte-identical;鏡像 conduct 疊層結構但削抗而非增傷)。
# 🔴 磁量使用者拍板 3/層·夾 5 層 = −15 魔抗;達貢 fire85 恆牆火系·720HP + 削抗後絕對傷害仍小 → 必 sim 守牆。
EROSION_RESIST_PER_STACK = 3
EROSION_MAX_STACKS = 5
EROSION_DEEP_MAX_STACKS = 10   # R121 湮識(秘術終極)命中 → 永久提升該敵秘蝕上限(−30·單敵·本場戰鬥·暫態旗標)
EROSION_TURNS = 3


def erosion_stacks(creature) -> int:
    e = next((x for x in creature.active_effects if x.get("kind") == "erosion" and x.get("turns", 0) > 0), None)
    return e.get("stacks", 0) if e else 0


def erosion_max_stacks(creature) -> int:
    """該敵秘蝕層上限:被 湮識 標記(`_deep_erosion`·暫態·本場戰鬥)者用加深上限,否則預設(R121)。"""
    return EROSION_DEEP_MAX_STACKS if getattr(creature, "_deep_erosion", False) else EROSION_MAX_STACKS


def erosion_resist_reduction(creature) -> int:
    """秘蝕層對應的魔法抗性削減點數(每層 × 層數;層數已於 add_erosion 夾上限;破抗=降魔抗,cast 端 floored ≥0)。"""
    return EROSION_RESIST_PER_STACK * erosion_stacks(creature)


def add_erosion(creature) -> None:
    """秘術命中 → 疊一層秘蝕(夾 erosion_max_stacks:湮識加深者 10 否則 5)+ 刷新計時;無則新建。"""
    cap = erosion_max_stacks(creature)
    e = next((x for x in creature.active_effects if x.get("kind") == "erosion" and x.get("turns", 0) > 0), None)
    if e:
        e["stacks"] = min(cap, e.get("stacks", 0) + 1)
        e["turns"] = EROSION_TURNS
    else:
        creature.active_effects.append({"kind": "erosion", "stacks": 1, "turns": EROSION_TURNS})


# 徒手「失衡 off-balance」warfare(落實 skills.json 招牌「耗損對手體力」):玩家徒手命中堆疊敵
# 失衡層 → 層數放大後續徒手傷害(formulas.offbalance_damage_multiplier)+ 跨門檻踉蹌/滿頂真擊倒。
# 鏡像 conduct:暫態 active_effects 疊層、刷新窗口、tick turns 歸零整組清(不入檔 R03)。
# 🔴 只由 combat.resolve_attack 的玩家徒手路徑讀寫 → sim 持匕首 byte-identical。
def offbalance_stacks(creature) -> int:
    e = next((x for x in creature.active_effects if x.get("kind") == "offbalance" and x.get("turns", 0) > 0), None)
    return e.get("stacks", 0) if e else 0


def add_offbalance(creature, amount: int = 1) -> int:
    """徒手命中 → 疊 amount 層失衡(夾 OFFBALANCE_MAX_STACKS)+ 刷新計時;無則新建。回傳新層數。"""
    e = next((x for x in creature.active_effects if x.get("kind") == "offbalance" and x.get("turns", 0) > 0), None)
    if e:
        e["stacks"] = min(formulas.OFFBALANCE_MAX_STACKS, e.get("stacks", 0) + amount)
        e["turns"] = formulas.OFFBALANCE_TURNS
        return e["stacks"]
    stacks = min(formulas.OFFBALANCE_MAX_STACKS, amount)
    creature.active_effects.append({"kind": "offbalance", "stacks": stacks, "turns": formulas.OFFBALANCE_TURNS})
    return stacks


def reset_offbalance(creature) -> None:
    """滿頂真擊倒 → 消耗(移除)失衡層,ramp 重建(防每擊重觸擊倒 lock-loop)。"""
    creature.active_effects[:] = [e for e in creature.active_effects if e.get("kind") != "offbalance"]


# 控場 kind 分類(R44:集中施加判定)
_HARD_CONTROL = ("fear", "paralyze")     # 失能(經 is_incapacitated 跳過行動)→ 受抵抗/去重
_CONTROL_KINDS = ("fear", "paralyze", "stagger", "slow", "weaken", "benumb", "calm")


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
    if kind == "calm":   # R104 幻術安撫:solo boss 完全免疫(非機率)、去重防延長;成功率已由 calm_chance 群數閘,故此處不再 willpower 抗
        if _is_solo(target, gamedata):
            return "resisted"
        if any(e.get("kind") == "calm" and e.get("turns", 0) > 0 for e in target.active_effects):
            return "blocked"
        target.active_effects.append({"kind": "calm", "turns": turns})
        return "applied"
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
        for elem, val in getattr(entity, "divine_resist", {}).items():   # 九神祝福(R107;阿爾凱之佑疾病抗)
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


# R76:法術施加的「持續傷害 DoT / 持續治療 HoT(regen)」的 magnitude 吃法術威力(與直擊/直接治療一致);
# 其餘狀態(soul_trap 等)原樣。只在 cast 路徑套用 → 武器/塗毒/撕裂/感染的 DoT(combat 路徑)不受影響。
_POWER_SCALED_STATUSES = ("dot", "regen")


def _scaled_status(status: dict, power: float) -> dict:
    """DoT/HoT 的 magnitude × 法術威力(夾 ≥1);非 DoT/HoT 原樣回傳。"""
    if status.get("status") in _POWER_SCALED_STATUSES:
        return {**status, "magnitude": max(1, int(round(status.get("magnitude", 0) * power)))}
    return status


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
    if k == "consecration":
        return f"被聖光庇佑,來襲傷害減免({status['turns']} 回合)"
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
            elif e["kind"] == "calm":
                msgs.append(f"{name}回過神來,敵意重新燃起。")
            elif e["kind"] == "conduct":
                msgs.append(f"{name}身上的導電消退了。")
            elif e["kind"] == "consecration":
                msgs.append("聖化領域的光輝黯淡下來。")
            elif e["kind"] == "erosion":
                msgs.append(f"{name}身上的秘蝕褪去,魔法抗性回復如常。")   # R120 秘蝕過期
            elif e["kind"] == "offbalance":
                msgs.append(f"{name}穩住了重心。")
            elif e["kind"] == "taunt":
                msgs.append(f"{name}的威懾漸漸散去,不再牽制敵人。")   # R105 坦克嘲諷過期
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
