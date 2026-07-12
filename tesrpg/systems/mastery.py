"""技能里程碑(Skill Mastery)v2 —— 達門檻「二選一」。

技能練到關鍵門檻(50/75/100)→ 在安全互動點(升級畫面 / 回城)從**兩個 perk 擇一**
銘刻,給 learn-by-doing 的終點一個「身份印記」+ build 能動性。

設計鐵律:
- **門檻只認 base_skill**:`_has` 用 ``char.base_skill()`` 即時推導 → 裝備/吸血鬼/里程碑
  加成都不得觸發門檻(避免污染成長/夾限、避免持久加成自我推過下一門檻)。
- **選擇是唯一新存檔種子**:玩家選了什麼記在 ``char.mastery_choices``(node_id -> opt_id,永久);
  其餘(持久 fortify 加成)由選擇 + JSON 決定性推導(見 stats.recompute_mastery_bonuses)。
- **未選 = 暫無此 perk**:達門檻但尚未選(pending)→ getter 回中性值,絕不崩;舊存檔達門檻
  → 留 pending(不自動指派,守住「選擇權」),回城時呈現。
- **效果走既有層**:質變/floor/active_effects/持久 fortify 層;真權衡型(boon+同源代價)夾 cap。
- **白名單惰性**:kind 不在 ``_IMPLEMENTED_KINDS`` 的 option 一律過濾(不顯示/不可選/零效果),
  避免 JSON 打錯 kind 時「計分+播報卻零效果」的沉默 foot-gun。

資料結構(``data/mastery.json``):**節點** = 一個技能門檻上的二選一。
``{"id": "<skill>_<thr>", "skill", "threshold", "options": [{"opt_id","name","kind",<params>,"desc"}, ...]}``
退化:一個節點可只有 1 個(可選)option → 無真正選擇,直接授予(不打擾玩家)。

新增一條里程碑 option(用既有 kind)= 純改 JSON;新增一種 **kind** = 加 getter + 一處呼叫端分支
(誠實:這步不是純 JSON),並登錄白名單。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData


# 已實作分派的 kind 白名單(單一真實來源)。不在此集合的 kind 視為「未實作」→
# 完全不顯示/不可選/不計分/無效果。新增 kind:此處登錄 + getter + 一處呼叫端分支。
# 持久 fortify 層的 kind:效果不靠 getter,而由 stats.recompute_mastery_bonuses 推導進
# mastery_*_bonus dict,再經 attr()/skill()/entity_resist 疊加。
_FORTIFY_KINDS = {"skill_fortify", "attr_fortify", "resist_fortify"}

_IMPLEMENTED_KINDS = {
    "block_deflect", "block_reflect", "bulwark", "overheal_ward",
    "spell_overload", "lock_floor", "guaranteed_persuade",
    *_FORTIFY_KINDS,                       # P1:持久 fortify 層
    # P2 戰鬥系:武器流派調變(命中/威力/破甲/反作用/耗體/命中附狀態,target=武器技能)、
    # 盾擊踉蹌、淬鍊上限/省料、旅速、戰鬥省體。
    "weapon_mod", "block_riposte", "on_evade", "temper_cap_bonus", "temper_cost_free", "temper_power",
    "travel_factor_bonus", "fatigue_cost_bonus",
    "offbalance_unlock",   # 徒手 25(R103):解鎖失衡累積(單一 perk 自動授予;gate 走 has_offbalance_unlock=門檻已達 + 非重甲)
    # P3 魔法系:法術調變(學派 power/cost/命中附狀態,吸收 spell_overload)、召喚調變、
    # 被動護甲、煉金/附魔增幅、塗毒次數、命中懼意、低血再生、商貿議價。
    "spell_mod", "summon_mod", "summon_casting", "bound_mastery", "passive_armor", "potion_potency", "poison_charge_bonus",
    "enchant_potency", "fear_on_hit", "regen_on_low", "merchant_bonus",
    "poison_unlock",   # 煉金深化(R31):解鎖特殊毒型家族(weaken/slow/fear)+ 毒效延長

    # P4 潛行系:閃避、隱遁下限、偷襲倍率(刺客 apex,受 >3 敵反制)、連環隱遁(無重複遞減)、
    # 潛近頻率、輕甲潛行減噪、偵查備戰、弱點揭露門檻、開鎖器不折、補貨量、威嚇下限。
    "vanish_unlock",   # 潛行 25:解鎖戰中隱遁(單一 perk 自動授予;gate 走 has_vanish=門檻已達)
    "evasion_bonus", "vanish_floor", "sneak_mult_bonus", "vanish_relentless", "approach_bonus",
    "armor_sneak_relief", "prep_bonus", "recon_resist_read", "pick_no_break",
    "restock_bonus", "intimidate_floor",
    # speechcraft 功能化(混合):衛兵說退槓桿、戰陣號令(鼓舞盟友)。
    "talk_down_lever", "rally",
    # 八職功能性身份:法師連鎖 / 戰法師共鳴·回魔 / 治療師急救 / 弓手散兵戰技(瞄準/牽制/走位)/ 刺客烙印。
    # (warrior 盾牆 / knight 戰旗 為戰鬥動作,非里程碑 kind;弓手散兵戰技 bow_technique 同屬戰鬥動作但走里程碑解鎖。)
    "cascade", "resonant_strike", "mana_on_hit", "triage_heal", "recon_reveal_floor", "bow_technique", "deathmark",
    # 廣度 pass:運動逃跑加成、重甲反傷、安全解陷保底。
    "armor_reflect", "armor_stagger", "combat_regen", "trap_floor",   # R147:flee_bonus 隨 escape_artist 移除(逃跑加成孤兒化)
    "rest_bonus",   # R147 運動「調息」開源:主動調息(耗一回合換回體·自動解除姿態)回復量加成(SUM)

    "shield_recoil",   # 變化 100(R118):作用中護膚盾時被物理擊中→機率震開攻方(接被動 flesh 為主動反噬)
    "consecration_boost",   # 恢復 75(R122 聖騎士):聖化領域減傷幅度 +(施法時加在 magnitude 上·守護頂點)
    # security 功能化(混合身份):盜賊行竊加成、地城賊眼窺探(布林解鎖)。
    "theft_skill", "dungeon_casing",
    # R106C 死靈經濟:解鎖(召喚 25·取代省魔)、亡者收集(每擊殺多給 token)、亡者統御(真·亡者更強韌兇猛)。
    "soul_economy", "soul_harvest", "undead_mastery",
    # R120 神秘頂點:秘蝕(布林解鎖)—— 傷害法術削目標魔抗、輔助所有傷害魔法。
    "arcane_erosion",
}


# --- 節點 / option 基礎 --------------------------------------------------
def _nodes(gamedata: GameData) -> list:
    """v2 節點清單;容忍 legacy flat v1 列(包成單 option 節點),過渡安全。"""
    out = []
    for e in (getattr(gamedata, "mastery", []) or []):
        if "options" in e:
            out.append(e)
        else:   # legacy flat v1 → 包成單 option 節點
            opt = {k: v for k, v in e.items() if k not in ("skill", "threshold")}
            opt.setdefault("opt_id", e.get("id", e.get("name", "opt")))
            out.append({"id": e.get("id", opt["opt_id"]), "skill": e["skill"],
                        "threshold": e["threshold"], "options": [opt]})
    return out


def _augment(opt: dict, node: dict) -> dict:
    """把節點脈絡(skill/threshold/node_id)併進 option,供既有 UI/legacy 以扁平條目消費。

    同時補 ``id`` = opt_id,讓舊消費端(以 e["id"] 比對)穩定。
    """
    return {**opt, "id": opt.get("opt_id", node["id"]), "opt_id": opt.get("opt_id", node["id"]),
            "skill": node["skill"], "threshold": node["threshold"], "node_id": node["id"]}


def _choosable_options(node: dict) -> list:
    """kind 已實作的 option(過濾未實作 → 玩家永不選到死 perk)。"""
    return [o for o in node.get("options", []) if o.get("kind") in _IMPLEMENTED_KINDS]


def _has(char, threshold_skill: str, threshold: int) -> bool:
    """玩家的 base 技能(不含裝備/吸血鬼/里程碑疊加)是否達門檻。僅對有 base_skill 的玩家成立。"""
    if not hasattr(char, "base_skill"):   # 怪物/同伴無技能里程碑
        return False
    return char.base_skill(threshold_skill) >= threshold


def _node_reached(char, node: dict) -> bool:
    return _has(char, node["skill"], node["threshold"])


def _defs(gamedata: GameData) -> list:
    """所有『kind 已實作』的 option(攤平、各帶 skill/threshold/node_id);供 UI 列門檻。"""
    return [_augment(o, n) for n in _nodes(gamedata) for o in _choosable_options(n)]


def _chosen_options_by_kind(char, gamedata: GameData, kind: str) -> list:
    """已達門檻、玩家『已選』、且為該 kind 的**所有** option(可能多來源,如 vanish_floor 來自
    acrobatics+sneak、merchant_bonus 來自 illusion+mercantile)。"""
    if not hasattr(char, "base_skill"):
        return []
    choices = getattr(char, "mastery_choices", {}) or {}
    out = []
    for node in _nodes(gamedata):
        if not _node_reached(char, node):
            continue
        oid = choices.get(node["id"])
        if oid is None:
            continue
        opt = next((o for o in node["options"] if o.get("opt_id") == oid), None)
        if opt and opt.get("kind") == kind:
            out.append(opt)
    return out


def _chosen_options_with_tree(char, gamedata: GameData, kind: str) -> list:
    """同 _chosen_options_by_kind,但連同來源技能樹回傳 [(tree_skill, opt), ...]
    (R141:輕甲/重甲/盾系 perk 需真的穿著對應裝備才生效 → 呼叫端按樹過濾)。"""
    if not hasattr(char, "base_skill"):
        return []
    choices = getattr(char, "mastery_choices", {}) or {}
    out = []
    for node in _nodes(gamedata):
        if not _node_reached(char, node):
            continue
        oid = choices.get(node["id"])
        if oid is None:
            continue
        opt = next((o for o in node["options"] if o.get("opt_id") == oid), None)
        if opt and opt.get("kind") == kind:
            out.append((node.get("skill", ""), opt))
    return out


def _armor_tree_active(char, gamedata: GameData, tree: str) -> bool:
    """R141 現實邏輯:護甲/持盾系 perk 的裝備前提 —— light_armor 樹=未穿任何重甲件、
    heavy_armor 樹=至少一件重甲、block 樹=持盾;其餘樹(雜技/變化/召喚…)恆 True。"""
    from tesrpg.systems import inventory
    if tree == "light_armor":
        return not inventory.wears_heavy_armor(char, gamedata)
    if tree == "heavy_armor":
        return inventory.wears_heavy_armor(char, gamedata)
    if tree == "block":
        return bool(getattr(char, "equipped", {}).get("shield"))
    return True


def _chosen_option_by_kind(char, gamedata: GameData, kind: str) -> dict | None:
    """已達門檻、玩家『已選』、且為該 kind 的 option(取第一個);未選 → None(回中性,絕不崩)。

    ⚠️ 僅供「每玩家至多一個來源」的 kind。多來源(vanish_floor/merchant_bonus)請用
    _chosen_options_by_kind 聚合(max/sum),否則只取第一個會吃到較弱值(審查抓到)。
    """
    opts = _chosen_options_by_kind(char, gamedata, kind)
    return opts[0] if opts else None


# --- UI / 查詢 -----------------------------------------------------------
def unlocked(char, gamedata: GameData) -> list:
    """玩家已達門檻**且已選**的里程碑 option(攤平 augmented;供結算/角色面板/計分)。"""
    if not hasattr(char, "base_skill"):
        return []
    choices = getattr(char, "mastery_choices", {}) or {}
    out = []
    for node in _nodes(gamedata):
        if not _node_reached(char, node):
            continue
        oid = choices.get(node["id"])
        if oid is None:
            continue
        opt = next((o for o in node["options"]
                    if o.get("opt_id") == oid and o.get("kind") in _IMPLEMENTED_KINDS), None)
        if opt:
            out.append(_augment(opt, node))
    return out


def pending_choices(char, gamedata: GameData) -> list:
    """已達門檻、尚未選、且至少有一個可選 option 的**節點**(供安全點呈現選單)。零副作用。"""
    if not hasattr(char, "base_skill"):
        return []
    choices = getattr(char, "mastery_choices", {}) or {}
    out = [n for n in _nodes(gamedata)
           if _node_reached(char, n) and n["id"] not in choices and _choosable_options(n)]
    return sorted(out, key=lambda n: (n["threshold"], n["skill"]))


def nodes_at(char, gamedata: GameData, skill_id: str, new_level: int) -> list:
    """技能剛升到 new_level 這級、恰好跨過門檻、且有可選 option 的節點(供「可選里程碑」播報)。"""
    return [n for n in _nodes(gamedata)
            if n["skill"] == skill_id and n["threshold"] == new_level and _choosable_options(n)]


def choose(char, gamedata: GameData, node_id: str, opt_id: str) -> dict | None:
    """記錄玩家在某節點的選擇(**冪等、永久不可覆寫**)。回傳選中的 option;非法則 None。"""
    node = next((n for n in _nodes(gamedata) if n["id"] == node_id), None)
    if node is None or not _node_reached(char, node):
        return None
    if not hasattr(char, "mastery_choices"):
        return None
    if node_id in char.mastery_choices:          # 永久不可改
        return None
    opt = next((o for o in _choosable_options(node) if o.get("opt_id") == opt_id), None)
    if opt is None:
        return None
    char.mastery_choices[node_id] = opt_id
    # 持久 fortify 立即流進有效數值/資源上限(同 vampirism.apply_to_character 模式)
    from tesrpg.systems import stats
    stats.recompute_max_resources(char, gamedata)
    return opt


def chosen_fortify_options(char, gamedata: GameData) -> list:
    """玩家已選、屬持久 fortify 層的 option(供 stats.recompute_mastery_bonuses)。"""
    if not hasattr(char, "base_skill"):
        return []
    choices = getattr(char, "mastery_choices", {}) or {}
    out = []
    for node in _nodes(gamedata):
        if not _node_reached(char, node):
            continue
        oid = choices.get(node["id"])
        if oid is None:
            continue
        opt = next((o for o in node["options"] if o.get("opt_id") == oid), None)
        if opt and opt.get("kind") in _FORTIFY_KINDS:
            out.append(opt)
    return out


def next_threshold(char, gamedata: GameData, skill_id: str) -> dict | None:
    """該技能(以 base_skill 計)尚未跨越的下一個里程碑門檻;全已達/無里程碑 → None。

    回傳 {name, threshold, remaining}(remaining = 還差幾級,>=1)。供 UI 提示用,**零副作用**。
    用 _nodes(過白名單);門檻只認 base_skill(鐵律)。同門檻多 option → 取節點層級。
    """
    base = char.base_skill(skill_id) if hasattr(char, "base_skill") else 0
    cands = sorted((n for n in _nodes(gamedata)
                    if n["skill"] == skill_id and n["threshold"] > base and _choosable_options(n)),
                   key=lambda n: n["threshold"])
    if not cands:
        return None
    n = cands[0]
    opts = _choosable_options(n)
    name = opts[0]["name"] if len(opts) == 1 else "里程碑(二選一)"
    return {"name": name, "threshold": n["threshold"], "remaining": n["threshold"] - base}


# --- 各 kind 的使用點 getter(呼叫端各取一處;只認『已選』的 option)----------
def block_hit_penalty(char, gamedata: GameData) -> float:
    """格擋時施加給攻擊者的命中懲罰(預設 BLOCK_HIT_PENALTY;block_deflect 加深)。"""
    e = _chosen_option_by_kind(char, gamedata, "block_deflect")
    return e["penalty"] if e else formulas.BLOCK_HIT_PENALTY


def block_reflect(char, gamedata: GameData) -> dict:
    """盾反(block_50 戰技):受物理近戰擊中時反彈 reflect 比例傷害,每次扣 fatigue 體力(體力不足則不反)。空 = 無。"""
    e = _chosen_option_by_kind(char, gamedata, "block_reflect")
    return {"reflect": e.get("reflect", 0.0), "fatigue": e.get("fatigue", 0)} if e else {}


def incoming_physical_factor(char, gamedata: GameData) -> float:
    """壁壘:受物理攻擊的減傷倍率(<1.0 = 更耐打);非物理(元素)不適用。"""
    e = _chosen_option_by_kind(char, gamedata, "bulwark")
    return e["factor"] if e else 1.0


def consecration_bonus(char, gamedata: GameData) -> float:
    """R122 聖騎士「聖化壁壘」(恢復 75 守護頂點):施放聖化領域時額外的減傷幅度加成
    (加在法術 magnitude 上;無此里程碑 → 0.0)。"""
    e = _chosen_option_by_kind(char, gamedata, "consecration_boost")
    return e.get("bonus", 0.0) if e else 0.0


def attack_fatigue_factor(char, gamedata: GameData) -> float:
    """壁壘的同源代價:攻擊一擊的體力消耗倍率(>1.0 = 更耗)。"""
    e = _chosen_option_by_kind(char, gamedata, "bulwark")
    return e["attack_fatigue_factor"] if e else 1.0


def _chosen_spell_options(char, gamedata: GameData, school: str) -> list:
    """已選、影響該學派的**所有**法術系 option(spell_overload / spell_mod);school 須一致。
    可跨多節點(廣度 pass:alteration_50 efficient_shield + alteration_75 spell_reach),須聚合不遮蔽。"""
    return [o for o in _chosen_options_by_kind(char, gamedata, "spell_mod")
            if o.get("school") == school] + \
           [o for o in _chosen_options_by_kind(char, gamedata, "spell_overload")
            if o.get("school") == school]


def spell_power_bonus(char, gamedata: GameData, school: str) -> float:
    """過載/術法增幅:對應學派的 _power 額外加成(多來源相加)。"""
    return sum(o.get("power_bonus", 0.0) for o in _chosen_spell_options(char, gamedata, school))


def spell_cost_factor(char, gamedata: GameData, school: str) -> float:
    """同源代價:對應學派的法力消耗倍率(多來源相乘;>1.0 = 更耗魔、<1.0 = 省魔)。"""
    f = 1.0
    for o in _chosen_spell_options(char, gamedata, school):
        if "cost_factor" in o:
            f *= o["cost_factor"]
    return f


def spell_on_hit(char, gamedata: GameData, school: str) -> dict | None:
    """衝擊餘波:該學派傷害法術命中時附加的狀態 {kind, chance, magnitude?, turns?};無則 None(取最後一個)。"""
    last = None
    for o in _chosen_spell_options(char, gamedata, school):
        if o.get("on_hit"):
            last = o["on_hit"]
    return last


def summon_mod(char, gamedata: GameData) -> dict:
    """召喚調變:{extra?, hp_factor?(額外召喚物血量係數), hp_bonus?, turn_bonus?};無則 {}。"""
    e = _chosen_option_by_kind(char, gamedata, "summon_mod")
    return e if e else {}


def summon_casting_mod(char, gamedata: GameData) -> dict:
    """R106「咒靈共鳴」(conjuration 50):法術召喚物支援施法強化 {power, cooldown};無則 {}。"""
    e = _chosen_option_by_kind(char, gamedata, "summon_casting")
    return e if e else {}


def bound_mastery_mod(char, gamedata: GameData) -> dict:
    """R106「束縛精通」(conjuration 50):束縛兵刃 {dmg_bonus, turn_bonus};無則 {}。"""
    e = _chosen_option_by_kind(char, gamedata, "bound_mastery")
    return e if e else {}


def soul_harvest_bonus(char, gamedata: GameData) -> int:
    """R106C「亡者收集」(conjuration 75):每擊殺額外 +N 靈魂 token(SUM 聚合,防未來多源遮蔽)。"""
    return int(sum(o.get("per_kill", 0)
                   for o in _chosen_options_by_kind(char, gamedata, "soul_harvest")))


def undead_mastery_mod(char, gamedata: GameData) -> dict:
    """R106C「亡者統御」(conjuration 100):真·亡者戰力加成 {hp_bonus, dmg_bonus};無則 {}。"""
    e = _chosen_option_by_kind(char, gamedata, "undead_mastery")
    return e if e else {}


def passive_armor_bonus(char, gamedata: GameData) -> int:
    """被動護甲加值(0 = 無)。多來源(石膚/靈體護壁/撐架/護體召喚/柔革護持)相加,不遮蔽。
    R141 現實邏輯:護甲/持盾系來源需真的穿著對應裝備(裸身沒有「撐架如鑄鐵堡壘」的盾;
    魔法系來源如石膚/護體召喚不受影響)。"""
    return int(sum(o.get("armor_bonus", 0)
                   for tree, o in _chosen_options_with_tree(char, gamedata, "passive_armor")
                   if _armor_tree_active(char, gamedata, tree)))


def potion_potency(char, gamedata: GameData) -> float:
    """濃縮萃取/萬靈藥:藥水/毒藥強度額外 ×(1+potency_bonus);多節點相加(alchemy 75+100)。"""
    return sum(o.get("potency_bonus", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "potion_potency"))


def armor_stagger(char, gamedata: GameData) -> float:
    """重壓:被近戰物理擊中時,震開攻擊者(使其踉蹌)的機率(0 = 無)。"""
    return _param(char, gamedata, "armor_stagger", "chance", 0.0)


def shield_recoil(char, gamedata: GameData) -> float:
    """變化「破盾反震/石膚反擊」(R118):**作用中護膚盾**期間被物理擊中 → 震開攻方(踉蹌)的機率
    (0 = 無;呼叫端另 gate `magic.active_shield(defender)>0`)。把被動 flesh 護盾接上主動反噬。"""
    return _param(char, gamedata, "shield_recoil", "chance", 0.0)


def combat_regen(char, gamedata: GameData) -> int:
    """生生不息:戰鬥中每回合自癒的生命(0 = 無)。"""
    return int(_param(char, gamedata, "combat_regen", "heal", 0))


def poison_charge_bonus(char, gamedata: GameData) -> int:
    """塗毒入門等:塗毒可附著的額外攻擊次數(多來源相加)。"""
    return int(sum(o.get("charge_bonus", 0)
                   for o in _chosen_options_by_kind(char, gamedata, "poison_charge_bonus")))


def poison_unlocks(char, gamedata: GameData) -> set:
    """煉金里程碑解鎖的特殊毒型家族(weaken/slow/fear)。DoT + 麻痺為基礎,永遠可釀,不需解鎖。"""
    fams: set = set()
    for o in _chosen_options_by_kind(char, gamedata, "poison_unlock"):
        fams.update(o.get("families", []))
    return fams


def poison_duration_bonus(char, gamedata: GameData) -> int:
    """毒效延長回合數(「劇毒淬煉」等,多來源相加)。"""
    return int(sum(o.get("duration_bonus", 0)
                   for o in _chosen_options_by_kind(char, gamedata, "poison_unlock")))


def enchant_potency(char, gamedata: GameData) -> float:
    """靈魂虹吸:附魔強度額外 ×(1+potency_bonus)。"""
    return _param(char, gamedata, "enchant_potency", "potency_bonus", 0.0)


def fear_on_hit(char, gamedata: GameData) -> dict:
    """懾心術/懾意/懾魂:武器命中時施加懼意。多節點聚合(illusion 50/75/100:chance 相加夾 FEAR_ON_HIT_CHANCE_CAP、turns 取最),空 = {}。"""
    opts = _chosen_options_by_kind(char, gamedata, "fear_on_hit")
    if not opts:
        return {}
    return {
        "chance": min(FEAR_ON_HIT_CHANCE_CAP, sum(o.get("chance", 0.0) for o in opts)),
        "turns": max((o.get("turns", 1) for o in opts), default=1),
    }


def regen_on_low(char, gamedata: GameData) -> dict | None:
    """不屈祝禱:低於 threshold 生命時觸發再生 {threshold, regen, turns};無則 None。"""
    return _chosen_option_by_kind(char, gamedata, "regen_on_low")


def merchant_bonus(char, gamedata: GameData) -> float:
    """精算買賣/魅惑交易:商店議價係數加成(多來源相加:illusion 魅惑 + mercantile 精算)。"""
    return sum(o.get("disposition_bonus", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "merchant_bonus"))


# --- P4 潛行系 getter ---------------------------------------------------
EVASION_BONUS_CAP = 0.15   # 多技能閃避來源(雜技/運動/輕甲)相加的硬上限 —— 守『群戰須具真實風險』(sim 背書)
ON_EVADE_RESTAMINA_CAP = 12   # 閃避回體(輕甲/雜技 on_evade)多源相加上限
FEAR_ON_HIT_CHANCE_CAP = 0.30   # 懾心術 fear_on_hit(illusion 50/75/100)多源 chance 相加上限


def evasion_bonus(char, gamedata: GameData) -> float:
    """身輕如燕/翻滾卸勁/疾風:額外閃避(直接從敵命中率扣;多來源 acrobatics/athletics/light_armor 相加,夾 EVASION_BONUS_CAP)。
    R141 現實邏輯:light_armor 樹的閃避 perk(柔革閃身/身如鬼魅)穿著重甲不生效(雜技/運動樹不受影響)。"""
    return min(EVASION_BONUS_CAP, sum(o.get("evasion_bonus", 0.0)
               for tree, o in _chosen_options_with_tree(char, gamedata, "evasion_bonus")
               if _armor_tree_active(char, gamedata, tree)))


def on_evade(char, gamedata: GameData) -> dict:
    """迴身反打/風暴之舞/凌空奇襲:成功閃避敵近戰時的反制。多節點聚合(反擊機率/比例取最、
    踉蹌任一、回體相加夾 ON_EVADE_RESTAMINA_CAP),空 = 無。"""
    opts = [o for tree, o in _chosen_options_with_tree(char, gamedata, "on_evade")
            if _armor_tree_active(char, gamedata, tree)]   # R141:輕甲樹閃身反打穿重甲不生效
    if not opts:
        return {}
    return {
        "counter_chance": max((o.get("counter_chance", 0.0) for o in opts), default=0.0),
        "counter_frac": max((o.get("counter_frac", 0.0) for o in opts), default=0.0),
        "counter_stagger": any(o.get("counter_stagger") for o in opts),
        "restamina": min(ON_EVADE_RESTAMINA_CAP, sum(o.get("restamina", 0) for o in opts)),
    }


def vanish_floor(char, gamedata: GameData) -> float:
    """踏影/翻滾脫離:隱遁成功率的保底下限(多來源取最高:acrobatics 0.10 vs sneak 0.15)。"""
    return max((o.get("floor", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "vanish_floor")), default=0.0)


def sneak_mult_bonus(char, gamedata: GameData) -> float:
    """影刃·暗殺宗師:偷襲倍率額外 ×(1+mult_bonus)。刺客 apex 的核心 —— 對 ≤3 敵可無傷清場;
    反制不靠秒殺率上限,而靠『>3 敵潛匿大減 + 隱遁耗體』(見 formulas)。調此值務必重跑 sim_assassin.py。"""
    return _param(char, gamedata, "sneak_mult_bonus", "mult_bonus", 0.0)


def has_vanish(char, gamedata: GameData) -> bool:
    """隱遁之術(潛行 25 里程碑):是否解鎖戰中隱遁。

    單一 perk『自動授予』節點 → gate **以門檻已達(base_skill)判定**,不依賴『已選』:
    達 25 即可用(零遷移、舊存檔與剛跨門檻未到安全點者皆即時生效),正式銘刻/播報則由安全點
    `_present_mastery_node` 退化授予補上(同步進 mastery_choices,供結算/面板計入)。
    門檻只認 base_skill(鐵律)→ 順帶修掉舊 `can_vanish` 用 `skill()` 致附魔可跨門檻的名實不符。"""
    if not hasattr(char, "base_skill"):
        return False
    return any(char.base_skill(node["skill"]) >= node["threshold"]
               for node in _nodes(gamedata)
               if any(o.get("kind") == "vanish_unlock" for o in node.get("options", [])))


def has_soul_economy(char, gamedata: GameData) -> bool:
    """死靈經濟解鎖(召喚 25 里程碑·R106C·取代舊省魔 conj_basics):是否解鎖靈魂 token 死靈經濟。

    單一 perk『自動授予』節點 → gate 以門檻已達(base_skill)判定(鏡像 has_vanish):達 conjuration 25
    即解鎖擊殺積魂/召亡者/死靈祭壇、零遷移、舊存檔即時生效。門檻只認 base_skill(鐵律)。"""
    if not hasattr(char, "base_skill"):
        return False
    return any(char.base_skill(node["skill"]) >= node["threshold"]
               for node in _nodes(gamedata)
               if any(o.get("kind") == "soul_economy" for o in node.get("options", [])))


def has_offbalance_unlock(char, gamedata: GameData) -> bool:
    """徒手失衡解鎖(徒手 25 里程碑·R103):是否解鎖「失衡累積」。

    單一 perk『自動授予』節點 → gate 以門檻已達(base_skill)判定(鏡像 has_vanish):達 25 即解鎖、
    零遷移、舊存檔即時生效。實際是否累積另需「未穿重甲」(由 combat 端再閘 inventory.wears_heavy_armor)
    —— 此函式只回『里程碑是否解鎖』,不看護甲。門檻只認 base_skill(鐵律)。"""
    if not hasattr(char, "base_skill"):
        return False
    return any(char.base_skill(node["skill"]) >= node["threshold"]
               for node in _nodes(gamedata)
               if any(o.get("kind") == "offbalance_unlock" for o in node.get("options", [])))


def has_vanish_relentless(char, gamedata: GameData) -> bool:
    """連環踏影:再隱匿無同場重複使用遞減 + 解除每場 vanish 上限(仍受 >3 敵懲罰壓制)。"""
    return _chosen_option_by_kind(char, gamedata, "vanish_relentless") is not None


def approach_bonus(char, gamedata: GameData) -> float:
    """無聲潛近/料敵機先:提高接戰時搶到開場偷襲的機率(頻率,非倍率)。
    多來源相加(sneak 潛近 + scout 情報);`stealth_approach_chance` 公式自帶 [0.05,0.97] 夾限
    + >3 敵壓制 → 無需另夾,且永不破偷襲倍率/solo clamp。"""
    return sum(o.get("approach_bonus", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "approach_bonus"))


def armor_sneak_relief(char, gamedata: GameData) -> float:
    """無聲披掛:抵消護甲對偷襲的兩道懲罰(0~1,1=全免)。
    命中端=潛近噪音(stealth_approach_chance);傷害端=偷襲倍率重量折扣(R72,armor_sneak_mult_factor)。"""
    return _param(char, gamedata, "armor_sneak_relief", "relief", 0.0)


def prep_bonus(char, gamedata: GameData) -> int:
    """先機在握/諜報偵搜:戰前備戰動作 +n(多來源相加:scout 先機在握 + mercantile 諜報偵搜)。"""
    return int(sum(o.get("prep_bonus", 0)
                   for o in _chosen_options_by_kind(char, gamedata, "prep_bonus")))


def recon_reveal_threshold(char, gamedata: GameData) -> int:
    """洞察弱點:抗性/弱點揭露的偵查門檻(選了 → 75 降為 50)。"""
    return 50 if _chosen_option_by_kind(char, gamedata, "recon_resist_read") else 75


def recon_scout_floor(char, gamedata: GameData) -> int:
    """獵手偵察/斥候之眼:視同偵查技能的下限(0 = 無)。多來源(marksman_50 獵手偵察 + scout_25 斥候之眼)取最高。"""
    return int(max((o.get("scout_floor", 0) for o in _chosen_options_by_kind(char, gamedata, "recon_reveal_floor")),
                   default=0))


def has_recon_perk(char, gamedata: GameData) -> bool:
    """是否擁有任一偵查里程碑(洞察弱點 recon_resist_read / 獵手偵察 recon_reveal_floor)。
    供地城探索:有偵查之力 → 可探明四方鄰格。"""
    return bool(_chosen_option_by_kind(char, gamedata, "recon_resist_read")
                or _chosen_option_by_kind(char, gamedata, "recon_reveal_floor"))


# --- 八職功能性身份 getter(法師/戰法師/治療師/刺客)----------------------
def _cascade_depth(char) -> int:
    """目前奧術連鎖層數(存 active_effects 的暫態,戰鬥邊界清空);非戰鬥/無效果 → 0。"""
    return max((int(e.get("magnitude", 0)) for e in getattr(char, "active_effects", [])
               if e.get("kind") == "cascade" and e.get("turns", 0) > 0), default=0)


def cascade_power(char, gamedata: GameData) -> float:
    """法師「奧術連鎖」:依目前連鎖層數對 _power 的額外加成(未選節點 → 0)。"""
    opt = _chosen_option_by_kind(char, gamedata, "cascade")
    return opt.get("power_per_depth", 0.0) * _cascade_depth(char) if opt else 0.0


def cascade_fatigue_factor(char, gamedata: GameData) -> float:
    """法師「奧術連鎖」:依層數的施法體力折扣(1.0 = 無;乘在法袍折扣之後,獨立乘法)。"""
    opt = _chosen_option_by_kind(char, gamedata, "cascade")
    if not opt:
        return 1.0
    return max(0.4, 1.0 - opt.get("fatigue_relief_per_depth", 0.0) * _cascade_depth(char))


def bump_cascade(char, gamedata: GameData) -> None:
    """成功施法後推進連鎖層數(cap max_depth、source 去重);未選節點 → no-op。"""
    opt = _chosen_option_by_kind(char, gamedata, "cascade")
    if not opt or not hasattr(char, "active_effects"):
        return
    depth = _cascade_depth(char)
    char.active_effects[:] = [e for e in char.active_effects if e.get("kind") != "cascade"]
    new_depth = min(depth + 1, int(opt.get("max_depth", 2)))
    char.active_effects.append({"kind": "cascade", "magnitude": new_depth,
                                "turns": int(opt.get("window", 1)) + 1})


def resonant_strike(char, gamedata: GameData) -> dict | None:
    """戰法師「共鳴一擊」:施毀滅傷害法術後強化下一近戰的 {transfer, dot_magnitude, dot_turns};無則 None。"""
    return _chosen_option_by_kind(char, gamedata, "resonant_strike")


def mana_on_hit(char, gamedata: GameData) -> int:
    """戰法師「法力回擊」:玩家近戰命中回復的法力點數(0 = 無此里程碑)。"""
    return int(_param(char, gamedata, "mana_on_hit", "magnitude", 0))


def triage(char, gamedata: GameData) -> dict | None:
    """治療師「戰地搶救」:同伴瀕死時急救的成本折扣 {magicka_factor, fatigue_factor};無則 None。"""
    return _chosen_option_by_kind(char, gamedata, "triage_heal")


def deathmark(char, gamedata: GameData) -> dict | None:
    """刺客「致命烙印」:標記敵 → 後續(非開場)近戰破甲的 {pen, fatigue_cost, sneak_gate, turns, cooldown};無則 None。"""
    return _chosen_option_by_kind(char, gamedata, "deathmark")


def has_bow_technique(char, gamedata: GameData, technique: str) -> bool:
    """弓手散兵戰技(marksman 里程碑解鎖):是否選了對應的 `technique`(aimed/crippling/skirmish)。

    取代舊「裝備弓即免費全給」——三式各為一個里程碑二選一,選了才開放對應戰技動作
    (main.py 仍另閘 archetype==bow + 非獸形;skirmish 另受 vanish 次數上限,但不再要 sneak 解鎖)。"""
    return any(o.get("technique") == technique
               for o in _chosen_options_by_kind(char, gamedata, "bow_technique"))


def pick_keep_chance(char, gamedata: GameData) -> float:
    """巧手不折:撬鎖失敗時開鎖器不折斷的機率(0 = 無)。"""
    return _param(char, gamedata, "pick_no_break", "keep_chance", 0.0)


def restock_mult(char, gamedata: GameData) -> float:
    """行商人脈:商店補貨量倍率(1.0 = 無)。"""
    return _param(char, gamedata, "restock_bonus", "restock_mult", 1.0)


def intimidate_floor(char, gamedata: GameData) -> float:
    """威風喝退/威名懾敵:威嚇喝退成功率下限(0 = 無)。多來源(speechcraft 50+75)取最高
    (對齊 lock_floor/vanish_floor 成長線;R35:floor 軸 MAX 聚合,後一階不被前一階遮蔽)。"""
    return max((o.get("floor", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "intimidate_floor")), default=0.0)


def talk_down_mod(char, gamedata: GameData) -> dict:
    """衛兵說退 —— 賞金上限加成(相加)+ 成功率下限(取最)。空 = 無。
    來源聚合:里程碑 `talk_down_lever`(speechcraft_75 silver_pardon)+ 任意裝備附魔 `kind=="talk_down_cap"`
    (灰狐面具,R47)。兩源皆用 cap_bonus/floor 鍵 → 同一路徑相加/取最;皆無則回 {}(back-compat)。
    """
    cap = 0
    floors = []
    for o in _chosen_options_by_kind(char, gamedata, "talk_down_lever"):
        cap += o.get("cap_bonus", 0)
        floors.append(o.get("floor", 0.0))
    for iid in getattr(char, "equipped", {}).values():
        ench = (gamedata.item_or_none(iid) or {}).get("enchant")
        if ench and ench.get("kind") == "talk_down_cap":
            cap += ench.get("cap_bonus", 0)
            floors.append(ench.get("floor", 0.0))
    if cap == 0 and not floors:
        return {}
    return {"cap_bonus": cap, "floor": max(floors, default=0.0)}


def has_rally(char, gamedata: GameData) -> bool:
    """戰陣號令(speechcraft_100):布林解鎖 → 開戰可立號令(鼓舞 living_allies 增傷光環;自身無益)。"""
    return _chosen_option_by_kind(char, gamedata, "rally") is not None


def lock_floor(char, gamedata: GameData) -> float:
    """撬鎖名家/神偷之手:撬鎖成功率下限(0.0 = 無里程碑)。多來源(security_75 + security_100)取最高。"""
    return max((o.get("floor", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "lock_floor")), default=0.0)


def theft_bonus(char, gamedata: GameData) -> dict:
    """順手牽羊(security_50):行竊得手率加成 + 失風賞金倍率。空 = 無。
    聚合 shape(steal_bonus 相加、bounty_factor 取最低)→ 防未來多源 first-wins 遮蔽(鐵則)。"""
    opts = _chosen_options_by_kind(char, gamedata, "theft_skill")
    if not opts:
        return {}
    return {"steal_bonus": sum(o.get("steal_bonus", 0.0) for o in opts),
            "bounty_factor": min((o.get("bounty_factor", 1.0) for o in opts), default=1.0)}


def has_dungeon_casing(char, gamedata: GameData) -> bool:
    """賊眼·窺探(security_100):進地城每層即揭該層所有陷阱+上鎖寶箱(不含怪/樓梯)。
    布林解鎖型 → 刻意不落 lock_floor 的 MAX 聚合軸,永不被同軸更強來源二元遮蔽(R35 安全);
    與 scout has_recon_perk(揭四鄰任意 type)互補不重複。"""
    return _chosen_option_by_kind(char, gamedata, "dungeon_casing") is not None


def has_arcane_erosion(char, gamedata: GameData) -> bool:
    """秘蝕(mysticism_100·R120):持頂點者的傷害法術命中疊「秘蝕」層 → 削目標通用魔抗
    (magic.EROSION_*),因火/冰/雷亦吃 magic 抗 → 輔助所有傷害魔法。布林解鎖型(R35 安全,同
    has_dungeon_casing/has_rally)→ 非頂點者恆 False → magic.cast 短路不施加 → sim byte-identical。"""
    return _chosen_option_by_kind(char, gamedata, "arcane_erosion") is not None


def overheal_ward(char, gamedata: GameData) -> dict | None:
    """聖光·溢盾:回傳 {convert, cap_ratio, turns} 或 None。"""
    return _chosen_option_by_kind(char, gamedata, "overheal_ward")


def can_guaranteed_persuade(char, gamedata: GameData, npc_id: str) -> bool:
    """辯舌·折服:此 NPC 是否可被一次性必定說服(每 NPC 限一次)。"""
    if _chosen_option_by_kind(char, gamedata, "guaranteed_persuade") is None:
        return False
    return npc_id not in getattr(char, "persuaded_npcs", [])


def _param(char, gamedata: GameData, kind: str, key: str, default):
    """通用單值 getter:取已選該 kind option 的某參數,無則 default。"""
    e = _chosen_option_by_kind(char, gamedata, kind)
    return e.get(key, default) if e else default


# --- P2 戰鬥系 getter ---------------------------------------------------
def weapon_mod(char, gamedata: GameData, wpn_skill_id: str | None) -> dict:
    """目前武器技能對應的『武器流派』已選 option(target 須與 wpn_skill_id 一致);無則 {}。

    參數:hit(命中+)/power(傷害×(1+power),在偷襲倍率之前套)/pen(破甲+)/
         recoil(自損=造成傷害×recoil,不致死)/fatigue(一擊額外耗體)/
         poise_rate(徒手失衡積累×(1+poise_rate),僅 hand_to_hand 命中時由 combat 讀)/
         extra_shot(R136 連珠箭:弓命中後追加一箭的機率;追加箭=普通射擊 sneak=False,main/sim 動作層讀)/
         exploit(R136 獵手之眼:目標帶控場狀態〔衰/踉/緩/凍麻/懼/麻痺〕→ 補傷 raw×exploit,
                 走 power_bonus 車道=偷襲倍率後相加·受 solo 夾 → 守紅線;combat 讀)/
         on_hit_status({kind:stagger|weaken, chance, magnitude?, turns?})。
    """
    if not wpn_skill_id or not hasattr(char, "base_skill"):
        return {}
    # 合併同 target 的所有已選 weapon_mod option(廣度 pass:同武器技能可有兩節點,如 blade_50+blade_100)
    # —— 數值參數相加、on_hit_status 取最後一個;否則前一節點會遮蔽後一節點(審查級正確性)。
    merged: dict = {}
    for opt in _chosen_options_by_kind(char, gamedata, "weapon_mod"):
        if opt.get("target") != wpn_skill_id:
            continue
        for k in ("hit", "power", "pen", "fatigue", "recoil", "poise_rate", "extra_shot", "exploit"):
            if k in opt:
                merged[k] = merged.get(k, 0) + opt[k]
        if "on_hit_status" in opt:
            merged["on_hit_status"] = opt["on_hit_status"]
    return merged


def block_riposte(char, gamedata: GameData) -> dict:
    """盾擊踉蹌/破勢/完美格擋:格擋來犯時的反制。多節點聚合(機率/削弱/反傷各取最),空 = 無。
    shield_bash(50)=踉蹌、盾擊破勢(75)+削弱敵下擊、盾威·完美格擋(100)+盾擊反傷。"""
    opts = _chosen_options_by_kind(char, gamedata, "block_riposte")
    if not opts:
        return {}
    return {
        "stagger_chance": max((o.get("stagger_chance", 0.0) for o in opts), default=0.0),
        "weaken": max((o.get("weaken", 0.0) for o in opts), default=0.0),
        "weaken_turns": max((o.get("weaken_turns", 1) for o in opts), default=1),
        "counter": max((o.get("counter", 0.0) for o in opts), default=0.0),
    }


def temper_cap_bonus(char, gamedata: GameData) -> int:
    """淬火宗師:淬鍊級上限額外 +n(同時抬高 TEMPER_MAX 硬夾,見 smithing)。"""
    return int(_param(char, gamedata, "temper_cap_bonus", "cap_bonus", 0))


def temper_free_chance(char, gamedata: GameData) -> float:
    """物盡其用/傳奇工匠:淬鍊有機率不消耗錠(0 = 無)。多來源(smithing_75 + smithing_100)取最高。"""
    return max((o.get("free_chance", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "temper_cost_free")), default=0.0)


def temper_power(char, gamedata: GameData) -> float:
    """淬鋒/淬鍊大師(smithing_50+100,鋒銳側):淬鍊加成額外 ×(1+power)。
    多節點相加(0.10+0.15)→ float-factor 軸,與 free(max-float)/cap(int)各自獨立,不二元遮蔽(R35)。"""
    return sum(o.get("power", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "temper_power"))


# --- 廣度 pass 新 getter(皆單源:只一個技能授予 → 無需聚合)--------------------
def armor_reflect(char, gamedata: GameData) -> float:
    """重甲反震:被近戰物理擊中時,反彈此比例傷害給攻擊者(0 = 無)。"""
    return _param(char, gamedata, "armor_reflect", "reflect", 0.0)


def trap_floor(char, gamedata: GameData) -> float:
    """機關通曉:解陷/避陷成功率下限(0 = 無)。"""
    return _param(char, gamedata, "trap_floor", "floor", 0.0)


def travel_factor_bonus(char, gamedata: GameData) -> float:
    """長途健步:旅行耗時係數額外 −bonus(更快;world.travel 夾 floor 0.5)。"""
    return _param(char, gamedata, "travel_factor_bonus", "bonus", 0.0)


FATIGUE_COST_BONUS_CAP = 0.35   # R147 節流省體多節點相加上限(防三節點疊到動作近乎免費)

def fatigue_cost_bonus(char, gamedata: GameData) -> float:
    """運動「節流」:戰鬥攻擊耗體額外 ×(1−bonus)。R147 改多源相加(運動 50/75/100 三節點可疊)、
    夾 FATIGUE_COST_BONUS_CAP(R35 防 first-wins 遮蔽 → 弱邊不製造隱形 no-brainer;單源時 SUM==原值 byte-identical)。"""
    return min(FATIGUE_COST_BONUS_CAP,
               sum(o.get("bonus", 0.0) for o in _chosen_options_by_kind(char, gamedata, "fatigue_cost_bonus")))


def rest_bonus(char, gamedata: GameData) -> int:
    """R147 運動「調息·開源」:主動調息(耗一回合換回體)的里程碑回復量加成(0 = 無)。
    多節點相加(25 地基 + 75/100 開源);base 回體量在 formulas.rest_fatigue_amount(運動技能)。"""
    return int(sum(o.get("rest_bonus", 0) for o in _chosen_options_by_kind(char, gamedata, "rest_bonus")))
