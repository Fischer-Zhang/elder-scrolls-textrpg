"""背包與裝備:物品堆疊、負重、裝備武器/護甲、使用藥水。

約定:
  - char.inventory = [{"id": item_id, "qty": n}, ...](堆疊)
  - char.equipped  = {slot: item_id}  穿戴中的護甲(item 仍留在 inventory,只是被標記為穿戴)
  - char.weapon    = item_id          手持武器('fists' 為內建,不在 inventory 內)
  負重計入所有 inventory 堆疊(含穿戴中的護甲);徒手不計重。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats

ARMOR_SLOTS = ["helmet", "cuirass", "gauntlets", "boots", "shield"]
JEWELRY_SLOTS = ["amulet", "ring1", "ring2"]        # 飾品槽(不占重量、無護甲值,純附魔載體)
SET_SLOTS = ["helmet", "cuirass", "gauntlets", "boots"]   # 判定「同材質整套」的四件


# --- 增減 ---------------------------------------------------------------
def add_item(char: Character, item_id: str, qty: int = 1) -> None:
    for stack in char.inventory:
        if stack["id"] == item_id:
            stack["qty"] += qty
            return
    char.inventory.append({"id": item_id, "qty": qty})


def count_item(char: Character, item_id: str) -> int:
    return sum(s["qty"] for s in char.inventory if s["id"] == item_id)


def remove_item(char: Character, item_id: str, qty: int = 1) -> bool:
    for stack in char.inventory:
        if stack["id"] == item_id:
            if stack["qty"] < qty:
                return False
            stack["qty"] -= qty
            if stack["qty"] <= 0:
                char.inventory.remove(stack)
                # 移除最後一件 → 一併卸下
                if char.weapon == item_id:
                    char.weapon = "fists"
                if getattr(char, "offhand", "") == item_id:
                    char.offhand = ""
                for slot, wid in list(char.equipped.items()):
                    if wid == item_id:
                        del char.equipped[slot]
                # 最後一件離開背包 → 清掉該 id 的淬鍊紀錄(賣/丟即失去淬鍊投資,杜絕「賣後重買免費續淬」)
                char.weapon_temper.pop(item_id, None)
                char.armor_temper.pop(item_id, None)
            # 雙持一致性:同型雙持丟到剩 1 把(stack 未清空)→ 副手失效,清掉殘留
            if char.offhand == item_id and count_item(char, item_id) < (2 if char.weapon == item_id else 1):
                char.offhand = ""
            return True
    return False


# --- 負重 ---------------------------------------------------------------
def total_weight(char: Character, gamedata: GameData) -> float:
    return sum(gamedata.item(s["id"])["weight"] * s["qty"] for s in char.inventory)


def max_weight(char: Character, gamedata: GameData | None = None) -> int:
    """負重上限 = 力量×5 +(若現乘坐騎)鞍袋加成。鞍袋即時計算、非資源 → 不進
    recompute_max_resources、不寫 base;帶 gamedata 時才計入(無 gamedata 維持基底,向後相容)。"""
    base = formulas.max_encumbrance(char.attr("strength"))
    if gamedata is not None:
        from tesrpg.systems import mounts
        base += mounts.saddlebag_bonus(char, gamedata)
    return base


def can_carry(char: Character, gamedata: GameData, item_id: str, qty: int = 1) -> bool:
    added = gamedata.item(item_id)["weight"] * qty
    return total_weight(char, gamedata) + added <= max_weight(char, gamedata)


def is_overencumbered(char: Character, gamedata: GameData) -> bool:
    return total_weight(char, gamedata) > max_weight(char, gamedata)


# --- 裝備 ---------------------------------------------------------------
def equip_weapon(char: Character, gamedata: GameData, item_id: str) -> bool:
    if gamedata.item(item_id).get("kind") != "weapon":
        return False
    if count_item(char, item_id) <= 0:
        return False
    char.weapon = item_id
    return True


def is_dual_wielding(char: Character, gamedata: GameData) -> bool:
    """雙持成立:主手與副手都是匕首,且確實持有足夠的實體匕首(同型需 2 把)。"""
    if not getattr(char, "offhand", ""):
        return False
    if gamedata.item(char.weapon).get("archetype") != "dagger":
        return False
    if gamedata.item(char.offhand).get("archetype") != "dagger":
        return False
    if char.offhand == char.weapon and count_item(char, char.offhand) < 2:
        return False   # 同型雙持需 2 把(丟掉一把後自動退出雙持)
    return True


def dual_wield_bonus_damage(char: Character, gamedata: GameData) -> float:
    """雙持時副手匕首折入每一擊的額外基礎傷害(非雙持為 0)。"""
    if not is_dual_wielding(char, gamedata):
        return 0.0
    return gamedata.item(char.offhand)["damage"] * formulas.OFFHAND_DAMAGE_FACTOR


def equip_offhand(char: Character, gamedata: GameData, item_id: str) -> bool:
    """以副手裝備一把匕首(僅匕首可雙持)。同型與主手需持有 2 把。"""
    d = gamedata.item(item_id)
    if d.get("kind") != "weapon" or d.get("archetype") != "dagger":
        return False
    need = 2 if item_id == char.weapon else 1
    if count_item(char, item_id) < need:
        return False
    char.offhand = item_id
    return True


def unequip_offhand(char: Character) -> None:
    char.offhand = ""


def equip_armor(char: Character, gamedata: GameData, item_id: str) -> bool:
    d = gamedata.item(item_id)
    if d.get("kind") != "armor" or count_item(char, item_id) <= 0:
        return False
    char.equipped[d["slot"]] = item_id
    return True


def equip_jewelry(char: Character, gamedata: GameData, item_id: str) -> str | None:
    """戴上飾品(amulet/ring)。戒指有兩個槽,填第一個空槽(都滿則換掉 ring1)。

    回傳實際使用的槽位(供 UI),不可戴回傳 None。
    """
    d = gamedata.item(item_id)
    if d.get("kind") != "jewelry" or count_item(char, item_id) <= 0:
        return None
    slot = d["slot"]
    if slot == "ring":
        target = "ring1" if "ring1" not in char.equipped else (
            "ring2" if "ring2" not in char.equipped else "ring1")
    else:
        target = "amulet"
    char.equipped[target] = item_id
    return target


def unequip(char: Character, slot: str) -> None:
    char.equipped.pop(slot, None)


# --- 穿戴裝備的總加成(附魔 + 套裝)------------------------------------
def _apply_enchant(out: dict, ench: dict | None) -> None:
    """把單一附魔/套裝效果累加進 out({skills,attrs,resist,resources})。"""
    if not ench:
        return
    k = ench.get("kind")
    mag = int(ench.get("magnitude", 0))
    if k in ("armor_fortify", "fortify_resource"):
        out["resources"][ench["stat"]] = out["resources"].get(ench["stat"], 0) + mag
    elif k == "fortify_skill":
        out["skills"][ench["skill"]] = out["skills"].get(ench["skill"], 0) + mag
    elif k == "fortify_attribute":
        out["attrs"][ench["attr"]] = out["attrs"].get(ench["attr"], 0) + mag
    elif k == "resist_element":
        out["resist"][ench["element"]] = out["resist"].get(ench["element"], 0) + mag


def set_progress(char: Character, gamedata: GameData) -> tuple:
    """套裝進度:四件套裝槽中最多的同材質 →(material, 件數 0..4, 該材質套裝 bonus 供預覽)。
    無任何套裝槽有材質 → (None, 0, None)。供 UI 顯示「X/4 進度 + 穿滿效果」。"""
    from collections import Counter
    mats: Counter = Counter()
    for slot in SET_SLOTS:
        iid = char.equipped.get(slot)
        d = gamedata.item_or_none(iid) if iid else None
        m = d.get("material") if d else None
        if m:
            mats[m] += 1
    if not mats:
        return (None, 0, None)
    mat, cnt = mats.most_common(1)[0]
    return (mat, cnt, gamedata.armor_sets.get(mat, {}).get("bonus"))


def active_set_bonus(char: Character, gamedata: GameData) -> dict | None:
    """穿戴 helmet/cuirass/gauntlets/boots 四件同材質 → 回傳該套裝 bonus(否則 None)。"""
    mats = []
    for slot in SET_SLOTS:
        iid = char.equipped.get(slot)
        if not iid:
            return None
        d = gamedata.item_or_none(iid)
        mat = d.get("material") if d else None
        if not mat:
            return None
        mats.append(mat)
    if len(set(mats)) != 1:
        return None
    return gamedata.armor_sets.get(mats[0], {}).get("bonus")


def cast_fatigue_factor(char: Character, gamedata: GameData) -> float:
    """穿滿整套法袍(cloth/archmage 同材質四件)→ 施法體力消耗折扣(<1.0);否則 1.0。
    折扣鍵 `cast_fatigue_factor` 藏在套裝 bonus dict 內,_apply_enchant 不認故安全忽略;
    此處 on-the-fly 讀取,不需新存檔欄位。"""
    return float((active_set_bonus(char, gamedata) or {}).get("cast_fatigue_factor", 1.0))


def equipment_bonuses(char: Character, gamedata: GameData) -> dict:
    """穿戴護甲/飾品的所有附魔 + 套裝加成,彙整成 {skills,attrs,resist,resources}。"""
    out = {"skills": {}, "attrs": {}, "resist": {}, "resources": {}}
    for iid in char.equipped.values():
        _apply_enchant(out, (gamedata.item_or_none(iid) or {}).get("enchant"))
    _apply_enchant(out, active_set_bonus(char, gamedata))
    return out


# --- 武器塗毒 -----------------------------------------------------------
def poison_charges(char: Character) -> int:
    """塗一次毒能附著的攻擊次數(隨煉金技能提升)。"""
    return max(1, 1 + char.skill("alchemy") // 30)


def coat_weapon(char: Character, gamedata: GameData, poison_id: str) -> bool:
    """把一瓶毒藥塗到手持武器上(徒手不可塗)。成功回傳 True。"""
    d = gamedata.item(poison_id)
    if d.get("kind") != "poison" or count_item(char, poison_id) <= 0 or char.weapon == "fists":
        return False
    from tesrpg.systems import mastery
    charges = poison_charges(char) + mastery.poison_charge_bonus(char, gamedata)   # 「劇毒淬煉」+1 次
    char.weapon_poison = {"status": d["poison"], "charges": charges, "name": d["name"]}
    remove_item(char, poison_id, 1)
    return True


def worn_armor_rating(char: Character, gamedata: GameData) -> int:
    """穿戴護甲的名目護甲值(不含耐久折損,供 UI 顯示)。毀損 id 視為 0(防毀損存檔)。"""
    return sum((gamedata.item_or_none(i) or {}).get("armor_rating", 0)
               for i in char.equipped.values())


def armor_fortify_totals(char: Character, gamedata: GameData) -> dict[str, int]:
    """穿戴護甲上的 armor_fortify 附魔加總 → {stat: 總強化值}。

    供 stats.recompute_max_resources 把「穿上時強化生命/魔力/體力」套進有效上限。
    fortify 不受耐久折損影響(附魔效果 ≠ 物理護甲值)。
    """
    totals: dict[str, int] = {}
    for iid in char.equipped.values():
        ench = (gamedata.item_or_none(iid) or {}).get("enchant")
        if ench and ench.get("kind") == "armor_fortify":
            totals[ench["stat"]] = totals.get(ench["stat"], 0) + int(ench["magnitude"])
    return totals


# --- 耐久 (condition) ---------------------------------------------------
def _cond_mult(condition: float) -> float:
    """耐久 → 效能倍率(100→1.0、0→0.5)。"""
    return 0.5 + 0.5 * max(0.0, min(100.0, condition)) / 100.0


def weapon_damage_mult(char: Character) -> float:
    return _cond_mult(char.weapon_condition)


def effective_armor_rating(char: Character, gamedata: GameData) -> float:
    """計入各部位耐久折損後的實際護甲值。"""
    total = 0.0
    for slot, iid in char.equipped.items():
        rating = (gamedata.item_or_none(iid) or {}).get("armor_rating")  # 飾品/毀損 id 無此鍵
        if not rating:
            continue
        cond = char.armor_condition.get(slot, 100.0)
        total += rating * _cond_mult(cond)
    return total


def degrade_weapon(char: Character, amount: float = 1.0) -> None:
    if char.weapon not in ("fists", "beast_claws"):   # 自然武器(徒手/獸爪)不磨損
        char.weapon_condition = max(0.0, char.weapon_condition - amount)


def degrade_random_armor(char: Character, rng, amount: float = 1.5) -> None:
    if not char.equipped:
        return
    slot = rng.choice(list(char.equipped.keys()))
    cur = char.armor_condition.get(slot, 100.0)
    char.armor_condition[slot] = max(0.0, cur - amount)


def repairable_cap(armorer_skill: int) -> float:
    """Armorer 技能決定能修到幾成(技能 100 才能修到 100%)。"""
    return min(100.0, 50.0 + armorer_skill * 0.5)


def repair_all(char: Character, cap: float = 100.0) -> None:
    if char.weapon != "fists":
        char.weapon_condition = max(char.weapon_condition, cap)
    for slot in char.equipped:
        char.armor_condition[slot] = max(char.armor_condition.get(slot, 100.0), cap)


def dominant_weight_class(char: Character, gamedata: GameData) -> str | None:
    """穿戴中以重甲還是輕甲為主?無護甲回傳 None。"""
    counts = {"heavy": 0, "light": 0}
    for i in char.equipped.values():
        wc = gamedata.item(i).get("weight_class")
        if wc in counts:
            counts[wc] += 1
    if counts["heavy"] == counts["light"] == 0:
        return None
    return "heavy" if counts["heavy"] >= counts["light"] else "light"


def armor_worn_weight(char: Character, gamedata: GameData) -> float:
    """穿戴護甲(含盾)的總重 —— 餵潛行噪音/偷襲倍率的重量懲罰。
    只計帶 weight_class 的真正甲/盾;飾品(護身符/戒指)與武器不計(無噪音)。"""
    total = 0.0
    for i in char.equipped.values():
        d = gamedata.item(i)
        if d.get("weight_class"):
            total += d.get("weight", 0)
    return total


# --- 使用 ---------------------------------------------------------------
def use_item(char: Character, gamedata: GameData, item_id: str, state=None) -> str | None:
    """使用消耗品(藥水)。回傳給玩家的訊息,不可用回傳 None。

    即時回復(heal/魔/體)不需 state;限時增益(R30:強化屬性/技能/抗元素)需 state
    取絕對小時推算到期 —— 呼叫端(備戰/背包)務必帶 state。
    """
    d = gamedata.item(item_id)
    if d.get("kind") != "potion" or count_item(char, item_id) <= 0:
        return None
    eff = d["effect"]
    if eff["type"] in ("fortify_attribute", "fortify_skill", "resist_element"):
        if state is None:
            return None            # 無時間語境無法計到期;不消耗、視為不可用
        from tesrpg.systems import potion_buff
        param = eff.get("attr") or eff.get("skill") or eff.get("element")
        hours = eff.get("duration_hours", 1)
        label = potion_buff.apply_buff(char, state, gamedata, eff["type"], param,
                                       eff["magnitude"], hours)
        remove_item(char, item_id, 1)
        return f"飲下{d['name']},{label}(持續 {hours} 小時)。"
    if eff["type"] == "heal":
        before = char.health
        char.health = min(char.max_health, char.health + eff["magnitude"])
        gained = int(char.health - before)
        msg = f"飲下{d['name']},回復 {gained} 點生命。"
    elif eff["type"] == "restore_magicka":
        before = char.magicka
        char.magicka = min(char.max_magicka, char.magicka + eff["magnitude"])
        gained = int(char.magicka - before)
        msg = f"飲下{d['name']},回復 {gained} 點魔力。"
    elif eff["type"] == "restore_fatigue":
        before = char.fatigue
        char.fatigue = min(char.max_fatigue, char.fatigue + eff["magnitude"])
        gained = int(char.fatigue - before)
        msg = f"飲下{d['name']},回復 {gained} 點體力。"
    else:
        return None
    remove_item(char, item_id, 1)
    stats.clamp_resources(char)
    return msg
