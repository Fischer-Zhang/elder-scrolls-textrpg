"""learn-by-doing 技能成長與升級 —— 本作的核心系統(混合 Skyrim 式)。

流程:
  使用技能 → 累積該技能 xp → 滿門檻則 +1 點
         → 該次升點餵給「等級 XP 池」level_xp(所有技能都計入,主修 ×1.5)
  level_xp 達 levelup_xp_threshold(level) → 可升級
         → 升級時玩家:① 生命/魔力/體力三選一 ② 自由分配屬性點(無倍率)
  技能成長本身完全沿用 learn-by-doing;只有「升級觸發與給予」改為 RPG 點數制。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import mastery, stats


def ensure_level_xp(char: Character) -> None:
    """舊存檔遷移:把停用的 level_progress 進度搬成等級經驗 level_xp(只搬一次)。

    舊系統需「主修升 10 點」可升級;新系統用 level_xp。把殘餘 level_progress 直接當經驗
    搬過去(不浪費玩家進度),搬完歸零避免重複觸發。
    """
    if char.level_xp <= 0 and char.level_progress > 0:
        char.level_xp = float(char.level_progress)
        char.level_progress = 0
        char.level_skillups = {}


def ensure_all_skills(char: Character, gamedata: GameData) -> None:
    """舊存檔遷移:補上資料新增、但存檔缺漏的技能(如第 22 技能 scout)為底值。"""
    for sid in gamedata.skills:
        if sid not in char.skills:
            char.skills[sid] = formulas.SKILL_BASE
            char.skill_xp.setdefault(sid, 0.0)


# 同技能節點間「搬家」過 perk 的節點組(如毀滅 50/75 互換:省魔催動⇄共鳴一擊):
# 任一成員的選擇陳舊 → 整組退回 pending。只清陳舊的那個會把舊佈局下的搭配鎖死在新佈局
# (舊檔 50=凝神聚法 + 75=共鳴一擊 → 共鳴被清、50 已被凝神永久鎖 → 共鳴對該角色永不可得),
# 整組重選讓玩家以新佈局重組(可重建雙 gish loop 或純法師線),守選擇權。
RELOCATED_NODE_GROUPS = (("destruction_50", "destruction_75"),)


def ensure_mastery_choices(char: Character, gamedata: GameData) -> None:
    """技能里程碑 v2 舊存檔遷移:確保四個欄位存在、清掉指向已不存在 node/opt 的陳舊選擇、
    重算持久加成快取。**達門檻但未選的舊存檔 → 留 pending(不自動指派,守選擇權)**:
    getter 對未選節點回中性值 → 不崩、不誤效,玩家下次回城再二選一。
    """
    for fld in ("mastery_choices", "mastery_skill_bonus", "mastery_attr_bonus", "mastery_resist"):
        if getattr(char, fld, None) is None:
            setattr(char, fld, {})
    # 防呆:清掉指向已不存在 node/opt 的陳舊選擇(JSON 改版安全)
    valid = {n["id"]: {o.get("opt_id") for o in n["options"]} for n in mastery._nodes(gamedata)}
    for group in RELOCATED_NODE_GROUPS:        # perk 搬家組:任一陳舊 → 整組退 pending
        if any(nid in char.mastery_choices and char.mastery_choices[nid] not in valid.get(nid, ())
               for nid in group):
            for nid in group:
                char.mastery_choices.pop(nid, None)
    char.mastery_choices = {nid: oid for nid, oid in char.mastery_choices.items()
                            if oid in valid.get(nid, ())}
    stats.recompute_mastery_bonuses(char, gamedata)


def practice_cost(char: Character, gamedata: GameData, skill_id: str) -> tuple[float, int, bool]:
    """套用該技能 data/skills.json 的 practice 體力成本,算出本次 xp 與耗時。

    與訓練師 action_practice 共用同一份 practice 價碼,讓「實戰中順手練技能」
    (行竊/撬鎖/說服)不再繞過正規訓練的代價:扣體力、體力不濟時 xp 減半。
    回傳 (xp, hours, tired);**呼叫端**負責推進時間(state.time)與授予 xp(use_skill)。
    """
    pdef = gamedata.skills[skill_id]["practice"]
    tired = char.fatigue < pdef["fatigue"]
    xp = pdef["xp"] * (0.5 if tired else 1.0)
    char.fatigue = max(0, char.fatigue - pdef["fatigue"])
    return xp, pdef["hours"], tired


def use_skill(char: Character, gamedata: GameData, skill_id: str, xp: float) -> list[dict]:
    """對某技能灌注 xp,結算升點。回傳事件列表(供 UI 呈現)。

    事件型別:
      {"type": "skill_up", "skill": id, "level": 新等級}
      {"type": "level_ready"}                      # 本次首度達到可升級
    """
    events: list[dict] = []
    if skill_id not in gamedata.skills:
        return events                      # 防呆:拒絕不存在的技能 id(打錯字)
    # 自癒:合法但缺漏的技能(如舊存檔遇到新增的第 22 技能 scout)→ 初始化為底值再成長
    char.skills.setdefault(skill_id, formulas.SKILL_BASE)
    char.skill_xp.setdefault(skill_id, 0.0)

    # 房產「精神飽滿」:在家最佳休息後一段時間技能成長加速(讀快取布林;舊存檔/未睡 → 中性)。
    if getattr(char, "well_rested", False):
        xp *= formulas.WELL_RESTED_XP_MULT
    # 職業專精:同專精系(combat/magic/stealth)技能練更快(跑時 learn-by-doing 身份;非專精系 ×1)
    if gamedata.skills[skill_id].get("spec") == getattr(char, "specialization", None):
        xp *= formulas.SPEC_SKILL_XP_MULT

    ensure_level_xp(char)
    could_level_before = char.can_level_up()
    char.skill_xp[skill_id] = char.skill_xp.get(skill_id, 0.0) + xp

    # 可能一次灌注跨過多個門檻
    while char.skills[skill_id] < formulas.SKILL_CAP:
        need = formulas.skill_threshold(char.skills[skill_id])
        if char.skill_xp[skill_id] < need:
            break
        char.skill_xp[skill_id] -= need
        char.skills[skill_id] += 1
        _on_skill_increase(char, gamedata, skill_id, events)

    if char.skills[skill_id] >= formulas.SKILL_CAP:
        char.skill_xp[skill_id] = 0.0  # 滿級不再累積

    if char.can_level_up() and not could_level_before:
        events.append({"type": "level_ready"})
    return events


def _on_skill_increase(char: Character, gamedata: GameData, skill_id: str, events: list[dict]) -> None:
    new_level = char.skills[skill_id]
    char.level_xp += formulas.levelup_xp_for_skillup(
        new_level, char.is_major_skill(skill_id))
    events.append({"type": "skill_up", "skill": skill_id, "level": new_level})
    # 技能里程碑 v2:恰好跨過門檻這一級 → 開啟「二選一」(不在此處授予;於 game_loop/升級畫面
    # 安全點呈現選單)。精確判定避免跨多級時漏/重報;選擇本身為衍生 pending,事件漏看也不會遺失。
    for n in mastery.nodes_at(char, gamedata, skill_id, new_level):
        opts = mastery._choosable_options(n)
        single = len(opts) == 1                         # 退化節點(如潛行 25 隱遁之術)= 自動授予,非二選一
        events.append({"type": "mastery_choice_ready", "skill": skill_id,
                       "threshold": new_level, "node_id": n["id"],
                       "single": single, "name": opts[0]["name"] if single else None})


def apply_level_up(char: Character, gamedata: GameData,
                   attribute_points: dict[str, int]) -> dict:
    """套用升級:分配屬性點 + 回滿三資源。回傳結算摘要供 UI。

    attribute_points: {attr: 點數};總和上限 LEVELUP_ATTRIBUTE_POINTS,逐屬夾 ATTRIBUTE_CAP。
    R64:移除資源三選一 → 資源純屬性驅動(endurance→生命·int→魔力·str/wil/agi/end→體力);
    `resource_levels`(舊存檔累積)仍由 recompute 讀,只是不再新增。
    """
    ensure_level_xp(char)
    if not char.can_level_up():
        raise ValueError("尚未滿足升級條件")

    # 屬性點(無倍率,自由分配;防禦性夾限總量與單屬上限)
    attr_gains: dict[str, int] = {}
    spent = 0   # 以「實際套用點數」計帳:屬性觸頂時剩餘預算留給其它屬性,不憑空吞點
    for attr, pts in attribute_points.items():
        if attr not in formulas.ATTRIBUTES or pts <= 0:
            continue
        pts = min(pts, formulas.LEVELUP_ATTRIBUTE_POINTS - spent)
        if pts <= 0:
            break
        cur = char.base_attr(attr)                       # 用原始屬性,勿把裝備加成寫進 base
        new_val = min(formulas.ATTRIBUTE_CAP, cur + pts)
        applied = new_val - cur
        char.attributes[attr] = new_val
        spent += applied
        if applied:
            attr_gains[attr] = applied

    char.level_xp -= formulas.levelup_xp_threshold(char.level)  # 保留溢出
    char.level += 1
    stats.ensure_base_health(char)
    stats.recompute_max_resources(char, gamedata, restore_full=True)  # 升級回滿三資源

    return {
        "level": char.level,
        "attr_gains": attr_gains,
        "can_level_again": char.can_level_up(),
    }
