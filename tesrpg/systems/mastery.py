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
    "block_deflect", "bulwark", "overheal_ward",
    "spell_overload", "lock_floor", "guaranteed_persuade",
    *_FORTIFY_KINDS,                       # P1:持久 fortify 層
    # P2 戰鬥系:武器流派調變(命中/威力/破甲/反作用/耗體/命中附狀態,target=武器技能)、
    # 盾擊踉蹌、淬鍊上限/省料、野修下限、旅速、戰鬥省體。
    "weapon_mod", "block_riposte", "temper_cap_bonus", "temper_cost_free",
    "repair_floor", "travel_factor_bonus", "fatigue_cost_bonus",
    # P3 魔法系:法術調變(學派 power/cost/命中附狀態,吸收 spell_overload)、召喚調變、
    # 被動護甲、煉金/附魔增幅、塗毒次數、命中懼意、低血再生、商貿議價。
    "spell_mod", "summon_mod", "passive_armor", "potion_potency", "poison_charge_bonus",
    "enchant_potency", "fear_on_hit", "regen_on_low", "merchant_bonus",
    # P4 潛行系:閃避、隱遁下限、偷襲倍率(刺客 apex,受 >3 敵反制)、連環隱遁(無重複遞減)、
    # 潛近頻率、輕甲潛行減噪、偵查備戰、弱點揭露門檻、開鎖器不折、補貨量、威嚇下限。
    "evasion_bonus", "vanish_floor", "sneak_mult_bonus", "vanish_relentless", "approach_bonus",
    "armor_sneak_relief", "prep_bonus", "recon_resist_read", "pick_no_break",
    "restock_bonus", "intimidate_floor",
    # 八職功能性身份:法師連鎖 / 戰法師共鳴·回魔 / 治療師急救 / 弓手獵手偵察 / 刺客烙印。
    # (warrior 盾牆 / knight 戰旗 為戰鬥動作,非里程碑 kind。)
    "cascade", "resonant_strike", "mana_on_hit", "triage_heal", "recon_reveal_floor", "deathmark",
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
    """格擋時施加給攻擊者的命中懲罰(預設 BLOCK_HIT_PENALTY;盾陣加深)。"""
    e = _chosen_option_by_kind(char, gamedata, "block_deflect")
    return e["penalty"] if e else formulas.BLOCK_HIT_PENALTY


def incoming_physical_factor(char, gamedata: GameData) -> float:
    """壁壘:受物理攻擊的減傷倍率(<1.0 = 更耐打);非物理(元素)不適用。"""
    e = _chosen_option_by_kind(char, gamedata, "bulwark")
    return e["factor"] if e else 1.0


def attack_fatigue_factor(char, gamedata: GameData) -> float:
    """壁壘的同源代價:攻擊一擊的體力消耗倍率(>1.0 = 更耗)。"""
    e = _chosen_option_by_kind(char, gamedata, "bulwark")
    return e["attack_fatigue_factor"] if e else 1.0


def _chosen_spell_option(char, gamedata: GameData, school: str) -> dict | None:
    """已選、影響該學派的法術系 option(spell_overload 舊制 / spell_mod 通用),school 須一致。"""
    if not hasattr(char, "base_skill"):
        return None
    choices = getattr(char, "mastery_choices", {}) or {}
    for node in _nodes(gamedata):
        if not _node_reached(char, node):
            continue
        oid = choices.get(node["id"])
        if oid is None:
            continue
        opt = next((o for o in node["options"] if o.get("opt_id") == oid), None)
        if opt and opt.get("kind") in ("spell_overload", "spell_mod") and opt.get("school") == school:
            return opt
    return None


def spell_power_bonus(char, gamedata: GameData, school: str) -> float:
    """過載/術法增幅:對應學派的 _power 額外加成。"""
    e = _chosen_spell_option(char, gamedata, school)
    return e.get("power_bonus", 0.0) if e else 0.0


def spell_cost_factor(char, gamedata: GameData, school: str) -> float:
    """同源代價:對應學派的魔力消耗倍率(>1.0 = 更耗魔)。"""
    e = _chosen_spell_option(char, gamedata, school)
    return e.get("cost_factor", 1.0) if e else 1.0


def spell_on_hit(char, gamedata: GameData, school: str) -> dict | None:
    """衝擊餘波:該學派傷害法術命中時附加的狀態 {kind, chance, magnitude?, turns?};無則 None。"""
    e = _chosen_spell_option(char, gamedata, school)
    return e.get("on_hit") if e else None


def summon_mod(char, gamedata: GameData) -> dict:
    """召喚調變:{extra?, hp_factor?(額外召喚物血量係數), hp_bonus?, turn_bonus?};無則 {}。"""
    e = _chosen_option_by_kind(char, gamedata, "summon_mod")
    return e if e else {}


def passive_armor_bonus(char, gamedata: GameData) -> int:
    """石膚:有魔力時的被動護甲加值(0 = 無)。"""
    return int(_param(char, gamedata, "passive_armor", "armor_bonus", 0))


def potion_potency(char, gamedata: GameData) -> float:
    """濃縮萃取:藥水/毒藥強度額外 ×(1+potency_bonus)。"""
    return _param(char, gamedata, "potion_potency", "potency_bonus", 0.0)


def poison_charge_bonus(char, gamedata: GameData) -> int:
    """劇毒淬煉:塗毒可附著的額外攻擊次數。"""
    return int(_param(char, gamedata, "poison_charge_bonus", "charge_bonus", 0))


def enchant_potency(char, gamedata: GameData) -> float:
    """靈魂虹吸:附魔強度額外 ×(1+potency_bonus)。"""
    return _param(char, gamedata, "enchant_potency", "potency_bonus", 0.0)


def fear_on_hit(char, gamedata: GameData) -> dict | None:
    """懾心術:武器命中時施加懼意的 {chance, turns};無則 None。"""
    return _chosen_option_by_kind(char, gamedata, "fear_on_hit")


def regen_on_low(char, gamedata: GameData) -> dict | None:
    """不屈祝禱:低於 threshold 生命時觸發再生 {threshold, regen, turns};無則 None。"""
    return _chosen_option_by_kind(char, gamedata, "regen_on_low")


def merchant_bonus(char, gamedata: GameData) -> float:
    """精算買賣/魅惑交易:商店議價係數加成(多來源相加:illusion 魅惑 + mercantile 精算)。"""
    return sum(o.get("disposition_bonus", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "merchant_bonus"))


# --- P4 潛行系 getter ---------------------------------------------------
def evasion_bonus(char, gamedata: GameData) -> float:
    """身輕如燕:額外閃避(直接從敵命中率扣)。"""
    return _param(char, gamedata, "evasion_bonus", "evasion_bonus", 0.0)


def vanish_floor(char, gamedata: GameData) -> float:
    """踏影/翻滾脫離:隱遁成功率的保底下限(多來源取最高:acrobatics 0.10 vs sneak 0.15)。"""
    return max((o.get("floor", 0.0)
               for o in _chosen_options_by_kind(char, gamedata, "vanish_floor")), default=0.0)


def sneak_mult_bonus(char, gamedata: GameData) -> float:
    """影刃·暗殺宗師:偷襲倍率額外 ×(1+mult_bonus)。刺客 apex 的核心 —— 對 ≤3 敵可無傷清場;
    反制不靠秒殺率上限,而靠『>3 敵潛匿大減 + 隱遁耗體』(見 formulas)。調此值務必重跑 sim_assassin.py。"""
    return _param(char, gamedata, "sneak_mult_bonus", "mult_bonus", 0.0)


def has_vanish_relentless(char, gamedata: GameData) -> bool:
    """連環踏影:再隱匿無同場重複使用遞減 + 解除每場 vanish 上限(仍受 >3 敵懲罰壓制)。"""
    return _chosen_option_by_kind(char, gamedata, "vanish_relentless") is not None


def approach_bonus(char, gamedata: GameData) -> float:
    """無聲潛近:提高接戰時搶到開場偷襲的機率(頻率,非倍率)。"""
    return _param(char, gamedata, "approach_bonus", "approach_bonus", 0.0)


def armor_sneak_relief(char, gamedata: GameData) -> float:
    """無聲披掛:抵消護甲噪音對潛近的懲罰(0~1,1=全免)。"""
    return _param(char, gamedata, "armor_sneak_relief", "relief", 0.0)


def prep_bonus(char, gamedata: GameData) -> int:
    """先機在握/諜報偵搜:戰前備戰動作 +n(多來源相加:scout 先機在握 + mercantile 諜報偵搜)。"""
    return int(sum(o.get("prep_bonus", 0)
                   for o in _chosen_options_by_kind(char, gamedata, "prep_bonus")))


def recon_reveal_threshold(char, gamedata: GameData) -> int:
    """洞察弱點:抗性/弱點揭露的偵查門檻(選了 → 75 降為 50)。"""
    return 50 if _chosen_option_by_kind(char, gamedata, "recon_resist_read") else 75


def recon_scout_floor(char, gamedata: GameData) -> int:
    """獵手偵察(弓手):視同偵查技能的下限(無 scout 也能戰前看清敵情)。0 = 無此里程碑。"""
    return int(_param(char, gamedata, "recon_reveal_floor", "scout_floor", 0))


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
    """戰法師「法力回擊」:玩家近戰命中回復的魔力點數(0 = 無此里程碑)。"""
    return int(_param(char, gamedata, "mana_on_hit", "magnitude", 0))


def triage(char, gamedata: GameData) -> dict | None:
    """治療師「戰地搶救」:同伴瀕死時急救的成本折扣 {magicka_factor, fatigue_factor};無則 None。"""
    return _chosen_option_by_kind(char, gamedata, "triage_heal")


def deathmark(char, gamedata: GameData) -> dict | None:
    """刺客「致命烙印」:標記敵 → 後續(非開場)近戰破甲的 {pen, fatigue_cost, sneak_gate, turns, cooldown};無則 None。"""
    return _chosen_option_by_kind(char, gamedata, "deathmark")


def pick_keep_chance(char, gamedata: GameData) -> float:
    """巧手不折:撬鎖失敗時開鎖器不折斷的機率(0 = 無)。"""
    return _param(char, gamedata, "pick_no_break", "keep_chance", 0.0)


def restock_mult(char, gamedata: GameData) -> float:
    """行商人脈:商店補貨量倍率(1.0 = 無)。"""
    return _param(char, gamedata, "restock_bonus", "restock_mult", 1.0)


def intimidate_floor(char, gamedata: GameData) -> float:
    """不怒自威:威嚇喝退成功率下限(0 = 無)。"""
    return _param(char, gamedata, "intimidate_floor", "floor", 0.0)


def lock_floor(char, gamedata: GameData) -> float:
    """撬鎖名家:撬鎖成功率下限(0.0 = 無里程碑)。"""
    e = _chosen_option_by_kind(char, gamedata, "lock_floor")
    return e["floor"] if e else 0.0


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
         on_hit_status({kind:stagger|weaken, chance, magnitude?, turns?})。
    """
    if not wpn_skill_id or not hasattr(char, "base_skill"):
        return {}
    choices = getattr(char, "mastery_choices", {}) or {}
    for node in _nodes(gamedata):
        if not _node_reached(char, node):
            continue
        oid = choices.get(node["id"])
        if oid is None:
            continue
        opt = next((o for o in node["options"] if o.get("opt_id") == oid), None)
        if opt and opt.get("kind") == "weapon_mod" and opt.get("target") == wpn_skill_id:
            return opt
    return {}


def block_riposte_chance(char, gamedata: GameData) -> float:
    """盾擊踉蹌:成功格擋來犯時,使攻擊者踉蹌的機率(0 = 無)。"""
    return _param(char, gamedata, "block_riposte", "stagger_chance", 0.0)


def temper_cap_bonus(char, gamedata: GameData) -> int:
    """淬火宗師:淬鍊級上限額外 +n(同時抬高 TEMPER_MAX 硬夾,見 smithing)。"""
    return int(_param(char, gamedata, "temper_cap_bonus", "cap_bonus", 0))


def temper_free_chance(char, gamedata: GameData) -> float:
    """物盡其用:淬鍊有機率不消耗錠(0 = 無)。"""
    return _param(char, gamedata, "temper_cost_free", "free_chance", 0.0)


def repair_floor(char, gamedata: GameData) -> float:
    """行軍鐵匠:不論 armorer 高低,修理可達的最低成數下限(0 = 無)。"""
    return _param(char, gamedata, "repair_floor", "floor", 0.0)


def travel_factor_bonus(char, gamedata: GameData) -> float:
    """長途健步:旅行耗時係數額外 −bonus(更快;world.travel 夾 floor 0.5)。"""
    return _param(char, gamedata, "travel_factor_bonus", "bonus", 0.0)


def fatigue_cost_bonus(char, gamedata: GameData) -> float:
    """不竭之軀:戰鬥攻擊耗體額外 ×(1−bonus)。"""
    return _param(char, gamedata, "fatigue_cost_bonus", "bonus", 0.0)
