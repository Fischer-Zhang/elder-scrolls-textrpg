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


def _worn_by_companion(char: Character, item_id: str) -> bool:
    """該 id 是否仍穿戴在某同伴身上(companion_gear 各槽)。無 companion_gear → False(舊檔/刺客 byte-identical)。"""
    return any(item_id in slots.values()
               for slots in getattr(char, "companion_gear", {}).values() if isinstance(slots, dict))


def remove_item(char: Character, item_id: str, qty: int = 1, keep_temper: bool = False) -> bool:
    """keep_temper=True(裝到同伴的移轉):跳過最後份清淬鍊(物件搬到同伴槽非銷毀 → 保留投資)。
    預設 False → 既有行為逐位元組不變(且同伴仍穿戴一份時亦不誤清 → companion_gear 空即 no-op)。"""
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
                # 最後一件離開背包 → 清該 id 淬鍊紀錄(賣/丟即失去投資);但移轉到同伴(keep_temper)
                # 或同伴仍穿戴一份時保留(否則毀掉同伴穿戴份的淬鍊)。companion_gear 空 → 條件退化 = byte-identical。
                if not keep_temper and not _worn_by_companion(char, item_id):
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
    from tesrpg.systems import spellfx
    base = formulas.max_encumbrance(char.attr("strength")) + spellfx.feather_bonus(char)   # R104 羽落術:限時 +負重(無 feather → +0 逐位元組同)
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
def is_two_handed(gamedata: GameData, item_id) -> bool:
    """武器是否雙手持(戰錘/戰斧/維蘇拉德):占雙手 → 不可帶盾/副手、不可格擋。item_id 可為 None/空。"""
    return bool(item_id and (gamedata.item_or_none(item_id) or {}).get("two_handed"))


def is_great_shield(gamedata: GameData, item_id) -> bool:
    """盾是否為雙手重盾(占雙手·無武器·盾擊作戰·高護甲+被動減傷)。item_id 可為 None/空。"""
    return bool(item_id and (gamedata.item_or_none(item_id) or {}).get("great_shield"))


def thorns_reflect(char: Character, gamedata: GameData) -> float:
    """荊棘附魔反傷比例(R42):盔/胸/手/靴/盾各可附一條,magnitude=反傷%(靈魂石階 1~5),聚合相加後 /100。"""
    if getattr(char, "beast_form", False):
        return 0.0   # R144 現實邏輯:獸形無甲可佈荊棘
    total = 0
    for slot in ARMOR_SLOTS:
        iid = char.equipped.get(slot)
        if not iid:
            continue
        ench = (gamedata.item_or_none(iid) or {}).get("enchant")
        if ench and ench.get("kind") == "thorns":
            total += ench.get("magnitude", 0)
    return total / 100.0


def _vampire_locked(char: Character, gamedata: GameData, item_id) -> bool:
    """吸血鬼專屬裝備:非吸血鬼不可裝(R56·資料欄 `requires_vampire`·向後相容預設無)。"""
    if not (gamedata.item_or_none(item_id) or {}).get("requires_vampire"):
        return False
    from tesrpg.systems import vampirism
    return not vampirism.is_vampire(char)


VIRTUE_INFAMY_LIMIT = 1   # 正典 KotN:infamy≤1 可裝(容忍一次失足)、≥2 聖物棄你而去


def virtue_violated(char: Character) -> bool:
    """聖物戒律(R108·R56 的鏡像對:夜影要求「是」吸血鬼、聖物要求「無垢」):
    惡名 > VIRTUE_INFAMY_LIMIT、或身負吸血鬼/狼人詛咒 → 違戒。
    贖罪路各走各的:惡名 → 朝聖歸零(R107);詛咒 → 既有解咒任務。"""
    from tesrpg.systems import lycanthropy, vampirism
    return (getattr(char, "infamy", 0) > VIRTUE_INFAMY_LIMIT
            or vampirism.is_vampire(char) or lycanthropy.is_werewolf(char))


def _virtue_locked(char: Character, gamedata: GameData, item_id) -> bool:
    """聖物裝備:違戒者不可裝(R108·資料欄 `requires_virtue`·向後相容預設無)。"""
    if not (gamedata.item_or_none(item_id) or {}).get("requires_virtue"):
        return False
    return virtue_violated(char)


def wearing_virtue_locked(char: Character, gamedata: GameData) -> bool:
    """是否身穿任何聖物(供破戒檢查/警告)。"""
    ids = [getattr(char, "weapon", ""), getattr(char, "offhand", "")] + \
        list(getattr(char, "equipped", {}).values())
    return any(iid and (gamedata.item_or_none(iid) or {}).get("requires_virtue") for iid in ids)


def _shed_by_flag(char: Character, gamedata: GameData, flag: str) -> None:
    """卸下所有帶指定資料旗標的裝備:物品留背包、僅脫下(共用骨架;呼叫端負責 recompute R05)。"""
    def _locked(iid):
        return bool(iid and (gamedata.item_or_none(iid) or {}).get(flag))
    if _locked(getattr(char, "weapon", "")):
        char.weapon = "fists"
    if _locked(getattr(char, "offhand", "")):
        char.offhand = ""
    for slot, iid in list(getattr(char, "equipped", {}).items()):
        if _locked(iid):
            char.equipped.pop(slot, None)


def shed_vampire_locked(char: Character, gamedata: GameData) -> None:
    """卸下所有 `requires_vampire` 裝備(失去吸血鬼身分時用,如治癒):物品留背包、僅脫下,
    以免凡人之身仍吃到吸血鬼專屬套裝/附魔加成(R56)。"""
    _shed_by_flag(char, gamedata, "requires_vampire")


def shed_virtue_locked(char: Character, gamedata: GameData) -> None:
    """卸下所有 `requires_virtue` 聖物(破戒時用:惡名≥2 / 染詛咒):物品留背包、僅脫下(R108)。"""
    _shed_by_flag(char, gamedata, "requires_virtue")


def equip_weapon(char: Character, gamedata: GameData, item_id: str) -> bool:
    if getattr(char, "beast_form", False):
        return False   # R144:巨狼之爪無法穿脫裝備
    if gamedata.item(item_id).get("kind") != "weapon":
        return False
    if (count_item(char, item_id) <= 0 or _vampire_locked(char, gamedata, item_id)
            or _virtue_locked(char, gamedata, item_id)):
        return False
    char.weapon = item_id
    if is_two_handed(gamedata, item_id):    # 雙手握持 → 自動卸下盾與副手(沿用 remove_item 自動卸裝風格)
        char.offhand = ""
        char.equipped.pop("shield", None)
    return True


def is_dual_wielding(char: Character, gamedata: GameData) -> bool:
    """雙持成立:主手與副手都是匕首,且確實持有足夠的實體匕首(同型需 2 把)。"""
    if not getattr(char, "offhand", ""):
        return False
    if is_two_handed(gamedata, char.weapon):   # 雙手武器占雙手 → 不雙持(防守式)
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
    if getattr(char, "beast_form", False):
        return False   # R144:巨狼之爪無法穿脫裝備
    if is_two_handed(gamedata, char.weapon):   # 主手雙手武器占雙手 → 無副手槽
        return False
    d = gamedata.item(item_id)
    if (d.get("kind") != "weapon" or d.get("archetype") != "dagger"
            or _vampire_locked(char, gamedata, item_id) or _virtue_locked(char, gamedata, item_id)):
        return False
    need = 2 if item_id == char.weapon else 1
    if count_item(char, item_id) < need:
        return False
    char.offhand = item_id
    return True


def unequip_offhand(char: Character) -> None:
    char.offhand = ""


def equip_armor(char: Character, gamedata: GameData, item_id: str) -> bool:
    if getattr(char, "beast_form", False):
        return False   # R144:巨狼之爪無法穿脫裝備
    d = gamedata.item(item_id)
    if (d.get("kind") != "armor" or count_item(char, item_id) <= 0
            or _vampire_locked(char, gamedata, item_id) or _virtue_locked(char, gamedata, item_id)):
        return False
    if d["slot"] == "shield" and is_two_handed(gamedata, char.weapon):   # 雙手武器在手 → 不能裝盾
        return False
    char.equipped[d["slot"]] = item_id
    if d["slot"] == "shield" and is_great_shield(gamedata, item_id):   # 雙手重盾占雙手 → 卸副手(手持武器戰中休眠)
        char.offhand = ""
    return True


def ensure_grip(char: Character, gamedata: GameData) -> None:
    """握法正規化(載入路徑;idempotent):雙手武器在手 → 清殘留盾與副手;雙手重盾在手 → 清殘留副手
    (處理舊存檔『雙手武器/重盾 + 並存』的情形)。無新存檔欄位。"""
    if is_two_handed(gamedata, getattr(char, "weapon", "")):
        char.offhand = ""
        char.equipped.pop("shield", None)
    elif is_great_shield(gamedata, getattr(char, "equipped", {}).get("shield")):
        char.offhand = ""


def equip_jewelry(char: Character, gamedata: GameData, item_id: str) -> str | None:
    """戴上飾品(amulet/ring)。戒指有兩個槽,填第一個空槽(都滿則換掉 ring1)。

    回傳實際使用的槽位(供 UI),不可戴回傳 None。
    """
    d = gamedata.item(item_id)
    if (d.get("kind") != "jewelry" or count_item(char, item_id) <= 0
            or _vampire_locked(char, gamedata, item_id) or _virtue_locked(char, gamedata, item_id)):
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
    if getattr(char, "beast_form", False):
        return None   # R144 現實邏輯:獸形套裝加成失效(巨狼穿不出夜影偽裝)
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


def set_spell_power_bonus(char: Character, gamedata: GameData) -> float:
    """穿滿整套法袍(cloth/archmage/dragonpriest 四件)→ 法術威力加成(R68;乘進 magic._power);否則 0.0。
    `spell_power` 鍵藏在套裝 bonus dict 內,_apply_enchant 不認故安全忽略(同 cast_fatigue_factor/disguise/resist 子鍵);
    on-the-fly 讀取,不需新存檔欄位。"""
    return float((active_set_bonus(char, gamedata) or {}).get("spell_power", 0.0))


def staff_spell_focus(char: Character, gamedata: GameData) -> dict:
    """R77 持杖施法焦點:{power: 法術威力加成, flat: 元素直擊加傷, elements: [適用元素]}。非持杖回 {}。
    法力法杖/馬格努斯之杖由資料 `spell_focus` 明寫;元素法杖(flame/frost/storm/daedric/skull)由
    既有 `weapon_element`(命中元素)推導同系加傷 → 同一支杖同時強化近戰元素與同系法術直擊。"""
    wid = getattr(char, "weapon", "") or ""
    d = gamedata.item(wid) if wid else {}
    if d.get("archetype") != "staff":
        return {}
    if "spell_focus" in d:                                  # 資料明寫優先(法力法杖/馬格努斯)
        return d["spell_focus"]
    el = d.get("enchant") or {}                             # 元素法杖:weapon_element → 同系直擊加傷
    if el.get("kind") == "weapon_element":
        return {"flat": el.get("magnitude", 0), "elements": [el.get("element")]}
    return {}


def staff_spell_power(char: Character, gamedata: GameData) -> float:
    """持杖的法術威力加成(乘進 _power,與法袍套裝相加);非持杖/無加成 0.0。"""
    return float(staff_spell_focus(char, gamedata).get("power", 0.0))


def staff_element_flat(char: Character, gamedata: GameData, element) -> int:
    """持杖對該元素傷害法術直擊的加傷(吃抗性);法杖不適用該元素則 0。"""
    sf = staff_spell_focus(char, gamedata)
    return int(sf.get("flat", 0)) if element in (sf.get("elements") or ()) else 0


def equipment_bonuses(char: Character, gamedata: GameData) -> dict:
    """穿戴護甲/飾品的所有附魔 + 套裝加成,彙整成 {skills,attrs,resist,resources}。"""
    out = {"skills": {}, "attrs": {}, "resist": {}, "resources": {}}
    for iid in char.equipped.values():
        _apply_enchant(out, (gamedata.item_or_none(iid) or {}).get("enchant"))
    sb = active_set_bonus(char, gamedata)
    _apply_enchant(out, sb)
    for elem, val in (sb or {}).get("resist", {}).items():   # R65:套裝 bonus 可帶額外 resist 子鍵(如大法師套裝魔抗)
        out["resist"][elem] = out["resist"].get(elem, 0) + val
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
    base = poison_charges(char) + mastery.poison_charge_bonus(char, gamedata)   # 「淬毒名家/塗毒入門」+次數
    # 依毒型強度調節塗層次數(R31):控制型(麻痺/懼意)塗層少、遲緩居中、DoT/衰減全額,防控場過載
    fam = d["poison"].get("status")
    if fam in ("paralyze", "fear"):
        charges = max(1, base // 2 + 1)
    elif fam == "slow":
        charges = max(1, base - 1)
    else:                                  # dot / weaken
        charges = base
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


def wears_heavy_armor(char: Character, gamedata: GameData) -> bool:
    """是否穿戴任何重甲件(含重盾)。任一件 weight_class=='heavy' → True;全輕甲/無甲 → False。
    供徒手失衡(R103:輕裝武僧才能累積失衡)等「輕裝才生效」的機制判定。"""
    return any(gamedata.item(i).get("weight_class") == "heavy" for i in char.equipped.values())


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
    elif eff["type"] == "cure_disease":     # R53:治療疾病藥水 → 統一治癒(普通病 + 吸血/狼人潛伏期)
        from tesrpg.systems import diseases
        msg = f"飲下{d['name']} —— " + diseases.purify_message(diseases.purify(char, gamedata))
    else:
        return None
    remove_item(char, item_id, 1)
    stats.clamp_resources(char)
    return msg
