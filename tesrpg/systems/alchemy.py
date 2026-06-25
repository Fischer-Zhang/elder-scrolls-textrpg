"""煉金:把兩種材料的共通效果調成藥水或毒藥。

共通效果若是「恢復類」(回血/回魔/回體)→ 飲用藥水;
若是「有害類」(毒傷/麻痺)→ 塗抹用毒藥(可塗在武器上,見 inventory.coat_weapon);
若是「療疾類」(cure_disease,R54)→ 療疾藥水(統一淨化,效果同神殿/法術/cure_disease_potion)。
技能越高 → 成品越強(療疾為二元、不隨技能縮放)。learn-by-doing 鍛鍊煉金。產出為合成物品(見 synth)。
"""

from __future__ import annotations

from tesrpg import synth
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import inventory, progression

BREW_FAIL_FACTOR = 0.5   # 沒煉成(無共通效果)只學到一半的 practice 成效

# --- 斯庫瑪精煉(R-smuggle:盜賊公會走私生意的製藥)---------------------------
# 月糖(原料)→ 斯庫瑪(成品)的「轉換」(非 brew 的雙材料合成)。**刻意是嚴格 sink**:
# 🔴 反印鈔機鐵則 SKOOMA_REFINE_COST × moon_sugar.value ≥ skooma.value
#   (5×25=125 ≥ 120)→ 精煉產出的「可售價值」恆 ≤ 投入月糖的可售價值,且買賣價對兩物
#   同乘 (0.3+0.5d)(1+sell_bonus) 故此不等式在任何議價/銷贓階都成立 → 精煉永不勝過直接賣月糖,
#   即使月糖是免費撿來的(月糖可由怪掉落/採集)。精煉只為了「自用施打(亢奮)」或備貨,絕非金幣泵。
SKOOMA_REFINE_COST = 5     # 幾份月糖煉一瓶斯庫瑪(由上方反套利不等式定錨;調此值必重跑 test 套利斷言)
SKOOMA_REFINE_SKILL = 20   # 精煉門檻(違禁製藥):煉金 base_skill 須達此

RESTORATIVE = {"heal", "restore_magicka", "restore_fatigue"}
# 有害效果(文件用;實際路由見 brew 的字串分支)。優先序:麻痺>懼意>遲緩>衰減>持續傷害。
# 特殊毒型(fear/slow/damage_strength)需里程碑解鎖(R31),否則退回 damage_health DoT。
HARMFUL = {"paralyze", "fear", "slow", "damage_strength", "damage_health"}
POTION_BUFF_BASE_HOURS = 2   # 限時增益藥水基礎時長(× factor 隨煉金/濃縮縮放),見 R30


def _is_buff_kind(k: str) -> bool:
    """限時增益效果 kind(R30;參數內嵌:fattr_<屬性>/fskill_<技能>/resist_<元素>)。
    以 kind 比對的「共有效果」偵測天然要求同參數才算共有(力量藥材 ≠ 敏捷藥材)。"""
    return k.startswith(("fattr_", "fskill_", "resist_"))


def ingredient_effects(gamedata: GameData, ing_id: str) -> list[dict]:
    return gamedata.ingredients[ing_id]["effects"]


# --- 效果逐步揭露(R32:試驗發現系統)----------------------------------------
# 材料效果預設隱藏為「???」,經 (a) 嚐一口 (b) 煉製成功用到該效果 (c) 煉金技能被動 逐步揭露。
# 純資訊層 —— 完全不影響 brew 的數學/路由(玩家仍可拿未知材料下鍋)。通用於任何 kind。
TASTE_FATIGUE = 2   # 嚐一口的微體力代價(由呼叫端扣;便宜,絕不勸退早期玩家)
_TASTE_HINT = {"heal": "暖意", "restore_magicka": "靈光", "restore_fatigue": "提神的甘",
               "damage_health": "灼痛", "paralyze": "麻木", "fear": "莫名的悸慄",
               "slow": "遲滯的沉重", "damage_strength": "酸軟無力", "cure_disease": "滌淨的清涼"}


def known_kinds(char: Character, ing_id: str) -> list[str]:
    return list(char.known_effects.get(ing_id, []))


def is_known(char: Character, ing_id: str, kind: str) -> bool:
    return kind in char.known_effects.get(ing_id, [])


def undiscovered_kinds(char: Character, gamedata: GameData, ing_id: str) -> list[str]:
    """該材料尚未揭露的效果 kind,維持 JSON 順序(決定性,非 rng)。"""
    known = set(char.known_effects.get(ing_id, []))
    return [e["kind"] for e in ingredient_effects(gamedata, ing_id) if e["kind"] not in known]


def reveal(char: Character, gamedata: GameData, ing_id: str, kind: str) -> bool:
    """揭露單一效果。回傳 True 表本次首次揭露(供 UI 報喜)。只揭露該材料實際擁有的 kind。"""
    if kind not in {e["kind"] for e in ingredient_effects(gamedata, ing_id)}:
        return False
    lst = char.known_effects.setdefault(ing_id, [])
    if kind in lst:
        return False
    lst.append(kind)
    return True


def auto_reveal_count(char: Character) -> int:
    """首次接觸某材料時,憑煉金學識自動辨識的效果數(0–24→1,25→2,50→3,75+→5)。讀 base_skill。"""
    return 1 + char.base_skill("alchemy") // 25


def passive_reveal(char: Character, gamedata: GameData, ing_id: str) -> list[str]:
    """依煉金技能,把該材料前 N 個效果視為已知;回傳本次新揭露的 kinds(idempotent,可空)。"""
    want = auto_reveal_count(char)
    newly: list[str] = []
    while len(char.known_effects.get(ing_id, [])) < want:
        und = undiscovered_kinds(char, gamedata, ing_id)
        if not und:
            break
        if reveal(char, gamedata, ing_id, und[0]):
            newly.append(und[0])
    return newly


def taste(char: Character, gamedata: GameData, ing_id: str) -> dict:
    """嚐一口材料 → 揭露下一個未知效果(依 JSON 序,決定性);**確有可揭露才**消耗 1 份材料。
    回傳 {"ok","message","revealed":kind|None}(ok=False → 未消耗,呼叫端應略過體力/時間成本)。"""
    name = gamedata.item_name(ing_id)
    if inventory.count_item(char, ing_id) < 1:
        return {"ok": False, "message": "你沒有這種材料。", "revealed": None}
    und = undiscovered_kinds(char, gamedata, ing_id)
    if not und:                                          # 已嚐遍 → 不消耗、不收成本(避免無謂浪費材料)
        return {"ok": False, "message": f"你已嚐遍{name}的滋味,沒有新發現。", "revealed": None}
    inventory.remove_item(char, ing_id, 1)               # 嚐 = 吃掉一份(材料代價)
    kind = und[0]
    reveal(char, gamedata, ing_id, kind)
    return {"ok": True, "revealed": kind,
            "message": f"你嚐了一口{name},舌尖泛起一陣{_TASTE_HINT.get(kind, '異樣')}……"}


def ensure_known_effects(char: Character, gamedata: GameData) -> None:
    """存檔遷移(接 state.from_dict):壞值→{}、清陳舊 ing_id、剔除該材料沒有的 kind。"""
    raw = getattr(char, "known_effects", None)
    if not isinstance(raw, dict):
        char.known_effects = {}
        return
    clean: dict[str, list[str]] = {}
    for iid, kinds in raw.items():
        if iid not in gamedata.ingredients or not isinstance(kinds, list):
            continue
        valid = {e["kind"] for e in ingredient_effects(gamedata, iid)}
        kept = [k for k in kinds if k in valid]
        if kept:
            clean[iid] = kept
    char.known_effects = clean


def brew(char: Character, gamedata: GameData, ing_a: str, ing_b: str, rng: RNG) -> dict:
    """調配 ing_a + ing_b。回傳 {"ok","message","item_id"?,"hours","tired","skill_events"}。

    每次調配付出煉金 practice 的體力 + 時間成本(時間由呼叫端推進),與訓練師/正規練習對齊,
    讓「在煉金台調藥」不再是零時間零體力的免費刷煉金捷徑。
    """
    if ing_a == ing_b or inventory.count_item(char, ing_a) < 1 or inventory.count_item(char, ing_b) < 1:
        return {"ok": False, "message": "材料不足或重複。", "hours": 0, "tired": False,
                "skill_events": [], "learn": {}}

    eff_a = {e["kind"]: e["magnitude"] for e in ingredient_effects(gamedata, ing_a)}
    eff_b = {e["kind"]: e["magnitude"] for e in ingredient_effects(gamedata, ing_b)}
    shared = set(eff_a) & set(eff_b)

    # 無論成敗都消耗材料(煉金的材料代價)+ 付出 practice 的體力/時間
    inventory.remove_item(char, ing_a, 1)
    inventory.remove_item(char, ing_b, 1)
    xp, hours, tired = progression.practice_cost(char, gamedata, "alchemy")

    if not shared:
        events = progression.use_skill(char, gamedata, "alchemy", xp * BREW_FAIL_FACTOR)
        return {"ok": False, "message": "兩種材料沒有共通效果,化作一灘廢液。",
                "hours": hours, "tired": tired, "skill_events": events, "learn": {}}

    from tesrpg.systems import mastery
    factor = (0.6 + char.skill("alchemy") / 100.0) * (1 + mastery.potion_potency(char, gamedata))  # 「濃縮萃取」
    events = progression.use_skill(char, gamedata, "alchemy", xp)
    sk = char.skill("alchemy")
    unlocked = mastery.poison_unlocks(char, gamedata)        # 里程碑解鎖的特殊毒型(weaken/slow/fear)
    dur_bonus = mastery.poison_duration_bonus(char, gamedata)  # 「劇毒淬煉」毒效延長回合

    def _pct(k):   # 衰毒/遲緩毒百分比:材料量值輕度隨煉金縮放,夾 10..35
        return max(10, min(35, round((eff_a[k] + eff_b[k]) / 2.0 * (0.5 + sk / 200.0))))

    # 有害共通效果 → 毒藥。優先序:麻痺 > 懼意 > 遲緩 > 衰減 > 持續傷害(特殊毒型需里程碑解鎖,
    # 否則因特殊材料皆兼具 damage_health → 自然退回基礎 DoT,材料永不淪為死內容)。
    if "paralyze" in shared:
        turns = max(1, min(3, 1 + sk // 50))
        item_id = synth.poison_id("paralyze", turns)
        result_kind = "poison"
    elif "fear" in shared and "fear" in unlocked:
        turns = max(1, min(2, 1 + sk // 60))
        item_id = synth.poison_id("fear", turns)
        result_kind = "poison"
    elif "slow" in shared and "slow" in unlocked:
        item_id = synth.poison_id("slow", _pct("slow"), 2 + dur_bonus)
        result_kind = "poison"
    elif "damage_strength" in shared and "weaken" in unlocked:
        item_id = synth.poison_id("weaken", _pct("damage_strength"), 2 + dur_bonus)
        result_kind = "poison"
    elif "damage_health" in shared:
        per_turn = max(1, round((eff_a["damage_health"] + eff_b["damage_health"]) / 2.0 * factor))
        item_id = synth.poison_id("dot", per_turn, 3 + dur_bonus)
        result_kind = "poison"
    elif "cure_disease" in shared:
        # 有益共通效果之首:療疾(R54 疾病可釀)→ 統一淨化(治所有普通病 + 斬斷吸血/狼人潛伏期,
        # 與藥水/神殿/法術同一行為)。治療為二元(無強度),不隨煉金縮放;煉金仍經 practice 練功。
        # 🔴 現有資料中,帶 cure_disease 的材料(大蒜/焦皮鼠革/吸血鬼塵)無一與其他 cure 材料共享有害效果
        # → 永不落入上方毒藥分支;此分支只在「兩材皆療疾」時觸發。
        item_id = synth.brew_cure_id()
        result_kind = "cure"
    else:
        # 有益共通效果:限時增益(強化屬性/技能/抗元素)優先於即時回復藥水
        buff_kinds = [k for k in shared if _is_buff_kind(k)]
        restore_kinds = shared & RESTORATIVE
        if buff_kinds:
            kind = max(buff_kinds, key=lambda k: eff_a[k] + eff_b[k])
            magnitude = max(1, round((eff_a[kind] + eff_b[kind]) / 2.0 * factor))
            dur = max(1, round(POTION_BUFF_BASE_HOURS * factor))   # 藥效時長(編入 id),非釀造耗時(hours)
            item_id = synth.brew_buff_id(kind, magnitude, dur)
            result_kind = "buff"
        elif restore_kinds:
            kind = max(restore_kinds, key=lambda k: eff_a[k] + eff_b[k])
            magnitude = max(1, round((eff_a[kind] + eff_b[kind]) / 2.0 * factor))
            item_id = synth.brew_id(kind, magnitude)
            result_kind = "potion"
        else:
            # 防呆:共有效果不屬有害/療疾/增益/回復(現有資料不會發生;留給未來新 kind 不致 max() 空集崩潰)
            return {"ok": False, "message": "兩種材料的效果無法調合,化作一灘廢液。",
                    "hours": hours, "tired": tired, "skill_events": events, "learn": {}}

    inventory.add_item(char, item_id, 1)
    name = gamedata.item(item_id)["name"]
    verb = ("煉出了一瓶毒藥" if result_kind == "poison"
            else "調出了一瓶增益藥劑" if result_kind == "buff"
            else "調出了一瓶療疾藥水" if result_kind == "cure"
            else "調出了一瓶藥水")
    # 成功 → 兩材料皆「學會」這次用到的共有效果(R32:純資料,由呼叫端套用 reveal)。
    learn = {ing_a: sorted(shared), ing_b: sorted(shared)}
    return {"ok": True, "kind": result_kind, "message": f"你{verb}:{name}。",
            "item_id": item_id, "hours": hours, "tired": tired, "skill_events": events, "learn": learn}


def can_refine_skooma(char: Character) -> tuple[bool, str]:
    """是否可精煉斯庫瑪(月糖數量 + 煉金門檻);回 (ok, 不可的原因)。"""
    if inventory.count_item(char, "moon_sugar") < SKOOMA_REFINE_COST:
        return False, f"月糖不足 —— 精煉一瓶斯庫瑪需 {SKOOMA_REFINE_COST} 份月糖。"
    if char.base_skill("alchemy") < SKOOMA_REFINE_SKILL:
        return False, f"你的煉金造詣還不足以精煉斯庫瑪(需煉金 {SKOOMA_REFINE_SKILL})。"
    return True, ""


def refine_skooma(char: Character, gamedata: GameData) -> dict:
    """精煉:`SKOOMA_REFINE_COST` 份月糖 → 1 瓶斯庫瑪(走私生意的製藥;練 alchemy)。
    回傳 {"ok","message","hours","tired","skill_events"}。條件不足 → ok False、零成本(不扣料/不耗時)。

    刻意是嚴格 sink(見模組頂端反套利不等式):精煉只為自用施打或備貨,不可作金幣泵。
    """
    ok, reason = can_refine_skooma(char)
    if not ok:
        return {"ok": False, "message": reason, "hours": 0, "tired": False, "skill_events": []}
    inventory.remove_item(char, "moon_sugar", SKOOMA_REFINE_COST)
    xp, hours, tired = progression.practice_cost(char, gamedata, "alchemy")
    events = progression.use_skill(char, gamedata, "alchemy", xp)
    inventory.add_item(char, "skooma", 1)
    return {"ok": True, "message": f"你把 {SKOOMA_REFINE_COST} 份月糖熬煉成一瓶斯庫瑪。",
            "hours": hours, "tired": tired, "skill_events": events}
