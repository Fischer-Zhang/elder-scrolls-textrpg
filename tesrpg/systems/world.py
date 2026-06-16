"""世界地圖、旅行、商店與訓練師的規則。

地圖是「地點圖」:每個地點有若干通往他處的連結(各帶旅行時數)。
旅行會推進時間,並可能在途中觸發遭遇。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import combat, progression


# --- 地點 / 旅行 --------------------------------------------------------
def current_location(char: Character, gamedata: GameData) -> dict:
    return gamedata.location(char.location_id)


def is_visible(char: Character, gamedata: GameData, loc_id: str) -> bool:
    """地點是否對玩家可見/可達。無 `visible` 欄=恆可見;有則對 world_events_fired /
    cleared_dungeons / factions 做 AND 判定(湮滅之門逐門開合、神殿入會後解鎖)。"""
    vis = gamedata.world["locations"].get(loc_id, {}).get("visible")
    if not vis:
        return True
    fired = getattr(char, "world_events_fired", [])
    cleared = getattr(char, "cleared_dungeons", [])
    if vis.get("after_event") and vis["after_event"] not in fired:
        return False
    if vis.get("after_cleared") and vis["after_cleared"] not in cleared:
        return False
    if "after_faction" in vis:
        fac, rank = vis["after_faction"]
        if char.factions.get(fac, -1) < rank:
            return False
    if vis.get("until_event") and vis["until_event"] in fired:
        return False
    if vis.get("until_cleared") and vis["until_cleared"] in cleared:
        return False
    return True


def relocate_target(char: Character, gamedata: GameData) -> str:
    """所在地變不可見時的去處:沿 links BFS 找最近的可見城/鎮;無則回起始地。"""
    locs = gamedata.world["locations"]
    seen = {char.location_id}
    frontier = [char.location_id]
    while frontier:
        cur = frontier.pop(0)
        for d in locs[cur].get("links", {}):
            if d in seen:
                continue
            seen.add(d)
            if locs[d]["type"] in ("city", "town") and is_visible(char, gamedata, d):
                return d
            frontier.append(d)
    return gamedata.world["start_location"]


def travel_options(char: Character, gamedata: GameData) -> list[tuple[str, int]]:
    """回傳 [(目的地 id, 旅行時數), ...];隱藏地點(湮滅之門未開/已閉、神殿未解鎖)不列。"""
    loc = current_location(char, gamedata)
    return [(d, h) for d, h in loc.get("links", {}).items() if is_visible(char, gamedata, d)]


def encounter_chance(dest_danger: int, hour: int) -> float:
    if dest_danger <= 0:
        return 0.0
    chance = dest_danger * 0.18
    if hour < 6 or hour >= 21:        # 夜間更危險
        chance += 0.10
    return min(0.85, chance)


def travel(char: Character, gamedata: GameData, dest_id: str, time, rng: RNG) -> dict:
    """執行旅行:依運動加速耗時、推進時間、移動、鍛鍊運動。

    回傳 {"foe":遭遇 Creature 或 None, "hours":實際耗時, "base_hours":名目耗時,
          "skill_events":運動升點事件}。遭遇尚未開打 —— 由上層決定接戰/逃避。
    """
    from tesrpg.systems import mastery, mounts, party
    links = current_location(char, gamedata).get("links", {})
    base_hours = links[dest_id]
    travel_factor = max(0.5, formulas.athletics_travel_factor(char.skill("athletics"))
                        - mastery.travel_factor_bonus(char, gamedata)
                        - party.passive_capstone_factor(char, gamedata, "travel")
                        - mounts.travel_factor_bonus(char, gamedata))   # 「長途健步」+ 同伴「識途」+ 坐騎,夾 floor 0.5
    hours = max(1, round(base_hours * travel_factor))
    dest = gamedata.location(dest_id)

    foe = None
    chance = encounter_chance(dest.get("danger", 0), time.hour) * (1 - mounts.encounter_evade(char, gamedata))   # 獵馬規避路途埋伏
    if rng.chance(chance):
        foe = combat.random_encounter(gamedata, char.level, rng,
                                      max_danger=dest.get("danger", 1) + 1,
                                      biome=dest.get("biome"))

    time.advance(hours)
    char.location_id = dest_id
    skill_events = progression.use_skill(char, gamedata, "athletics", formulas.ATHLETICS_TRAVEL_XP)
    return {"foe": foe, "hours": hours, "base_hours": base_hours, "skill_events": skill_events}


# --- 商店定價(受 交易 + 魅力 影響)-----------------------------------
def _disposition_factor(char: Character, gamedata: GameData | None = None) -> float:
    base = (char.skill("mercantile") + char.attr("personality") * 0.5) / 150.0
    if gamedata is not None:                       # 里程碑「精算買賣/魅惑交易」議價加成 + 同伴忠誠頂點
        from tesrpg.systems import mastery, party
        base += mastery.merchant_bonus(char, gamedata)
        base += party.passive_capstone_factor(char, gamedata, "barter")   # 同伴「人脈/巧手」忠誠頂點:議價
    return max(0.0, min(1.0, base))


LOCKPICK_OUTSIDER_MARKUP = 2.0   # 開鎖器是盜賊公會的營生:非會員(含敵對)買得到但被坑這麼多倍


def buy_price(char: Character, gamedata: GameData, item_id: str) -> int:
    from tesrpg.systems import factions
    item = gamedata.item(item_id)
    price = item["value"] * (2.2 - _disposition_factor(char, gamedata))
    # 開鎖器只在有盜賊公會的城販售;會員按常價,外人/敵對加價(仍買得到,但較貴)
    if item_id == "lockpick" and not factions.is_member(char, "thieves_guild"):
        price *= LOCKPICK_OUTSIDER_MARKUP
    # 戰士公會「軍械庫之誼」:買武器/護甲(含盾/弓/法杖)享階級折扣
    if "damage" in item or "armor_rating" in item:
        price *= 1 - factions.armory_discount(char, gamedata)
    # 反套利鐵則:同物買價恆 > 賣價(極端議價 + 滿階軍械庫折扣下,折扣不得倒掛成金幣泵)
    return max(1, round(price), sell_price(char, gamedata, item_id) + 1)


def sell_price(char: Character, gamedata: GameData, item_id: str) -> int:
    from tesrpg.systems import factions
    value = gamedata.item(item_id)["value"]
    base = value * (0.3 + _disposition_factor(char, gamedata) * 0.5)
    base *= 1 + factions.sell_bonus(char, gamedata)   # 盜賊公會銷贓加成(階級越高越多)
    return max(1, round(base))


# --- 商店庫存(Skyrim 式:每商人有限數量 + 定時補貨 + 補貨品項有變化)------
# 商人不再是「無限供貨機」:每件商品有有限數量,定時補貨且每次補的量(乃至有無)會變動。
# 這從「供給側」掐住了「買廉價材料 → 煉製 → 高價賣回」的無限金幣套利:一輪只買得到有限的量。
RESTOCK_HOURS = 72        # 商人每約 3 天補一次貨


# loot-only 稀材:即使誤入配方輸入,也不享足量補貨(維持「只能打怪取得」紅線於程式,不靠資料慣例)
_LOOT_ONLY_MATERIALS = {"daedra_heart", "dragon_scale"}

# 鍛造材料的城鎮供給分級(使用者拍板:一般材料幾乎每座城都有、高級材料只在大城)。
# 規則注入於 merchant_catalog → 每座 type=city 自動供應一般材料;大城另供高級材料(新城自動涵蓋)。
_COMMON_MATERIALS = ("iron_ingot", "steel_ingot", "bolt_of_cloth", "wolf_pelt")    # 一般材料:每城
_HIGH_MATERIALS = ("moonstone_ingot", "dwarven_ingot", "malachite_ingot", "ebony_ingot")  # 高級材料:大城
# 大城 = 各省首府(高級材料採買點;每省一座 → 區域內買得到頂材,不必跨圖)。調整供給點純改此集合。
MAJOR_CITIES = frozenset({"imperial_city", "markarth", "blacklight", "gideon",
                          "sentinel", "daggerfall", "falinesti", "rimmen"})


def _crafting_material_ids(gamedata: GameData) -> set:
    """可量產的鍛造/製作配方輸入材料 id(消耗性輸入 → 補貨給足量);排除 loot-only 稀材。"""
    return {iid for r in gamedata.recipes.values()
            for iid in r.get("inputs", {})} - _LOOT_ONLY_MATERIALS


def _restock_qty(value: int, rng: RNG, material: bool = False) -> int:
    """依物品價值分級給補貨量,帶隨機變化(可能為 0 → 不同次補貨的品項有別)。
    鍛造材料(material=True)例外:即使高價也給足量、且不缺貨(消耗性輸入,湊得齊一件裝備);
    成品仍照價值稀缺 → 反「買廉材 → 煉製 → 高價賣回」套利的防線不動。"""
    if material:                  # 鍛造材料:錠/獸皮/布匹等,獨立於價值給充足補貨
        return rng.randint(3, 8)
    if value <= 10:               # 廉價消耗品/煉金材料
        return rng.randint(1, 6)
    if value <= 80:               # 中價:藥水、基礎裝備、配件
        return rng.randint(0, 3)
    return rng.randint(0, 1)      # 高價裝備:時常缺貨


_EMPTY_GEM_STOCK = ("empty_petty_soul_gem", "empty_lesser_soul_gem",
                    "empty_common_soul_gem", "empty_greater_soul_gem")   # 法師城售白魂空石
_EMPTY_GEM_STOCK_MAJOR = ("empty_grand_soul_gem", "empty_black_soul_gem")  # 大城另售空大/黑魂石


def merchant_catalog(gamedata: GameData, loc_id: str) -> list[str]:
    """該地商人「可能販售」的完整品項目錄:world.json 的 merchant_stock + 鍛造材料分級供給 + 法師城空魂石。
    每座 type=city 自動供應一般材料(_COMMON_MATERIALS);大城(MAJOR_CITIES)另供高級材料;法師城供空魂石(填充燃料)。"""
    loc = gamedata.location(loc_id)
    catalog = list(loc.get("merchant_stock", []))
    if loc.get("type") == "city":
        extra = list(_COMMON_MATERIALS) + (list(_HIGH_MATERIALS) if loc_id in MAJOR_CITIES else [])
        catalog += [iid for iid in extra if iid not in catalog]   # 去重:既有明列者不重複
    if "mages_guild" in loc.get("services", []):                  # 填充循環燃料:法師城供空魂石
        gems = list(_EMPTY_GEM_STOCK) + (list(_EMPTY_GEM_STOCK_MAJOR) if loc_id in MAJOR_CITIES else [])
        catalog += [iid for iid in gems if iid not in catalog]
    return catalog


def ensure_stock(char: Character, gamedata: GameData, loc_id: str, time, rng: RNG) -> None:
    """首次造訪或已過補貨時點 → 依目錄重抽當前庫存(數量隨機、可能個別缺貨)。"""
    if not merchant_catalog(gamedata, loc_id):
        return
    now = time.absolute_hours()
    if loc_id in char.shop_restock_at and now < char.shop_restock_at[loc_id]:
        return
    from tesrpg.systems import mastery
    rmult = mastery.restock_mult(char, gamedata)                # 「行商人脈」補貨量倍率
    mats = _crafting_material_ids(gamedata)                     # 鍛造材料 → 足量補貨

    def _qty(iid):
        q = _restock_qty(gamedata.item(iid)["value"], rng, material=iid in mats)
        return 0 if q == 0 else max(1, round(q * rmult))        # 保留「擲 0 = 缺貨」的稀缺性(反套利)
    char.shop_stock[loc_id] = {iid: _qty(iid) for iid in merchant_catalog(gamedata, loc_id)}
    char.shop_restock_at[loc_id] = now + RESTOCK_HOURS


def stock_qty(char: Character, loc_id: str, item_id: str) -> int:
    return char.shop_stock.get(loc_id, {}).get(item_id, 0)


def take_stock(char: Character, loc_id: str, item_id: str, n: int = 1) -> None:
    """買走/偷走後扣減庫存(夾在 0)。"""
    cur = char.shop_stock.get(loc_id)
    if cur and item_id in cur:
        cur[item_id] = max(0, cur[item_id] - n)


def in_stock_items(char: Character, gamedata: GameData, loc_id: str) -> list[str]:
    """目錄中目前仍有貨(數量>0)的品項,維持目錄原順序。"""
    return [iid for iid in merchant_catalog(gamedata, loc_id) if stock_qty(char, loc_id, iid) > 0]


# --- 訓練師 -------------------------------------------------------------
def train_cost(skill_level: int) -> int:
    return max(20, skill_level * 8)


# --- 城鎮服務專精化:訓練師依公會/lore 只教部分技能(handoff R29)----------
# 每座城的訓練師不再教全部 23 技;可教範圍 =
#   ① data/trainers.json 的 "skills" 覆寫(系 id 或顯式技能 id;招牌城手工點綴)
#   ② 否則由該城既有公會服務推導系(下表)
#   ③ 皆無 → 全系全技(現行行為;無公會的鎮/特例安全後備)
#   再 ∪ 招牌「master」技(該城宗師之技,必可在此習得)。
# 純讀靜態世界資料即時推導,零存檔欄位、不動 combat/economy 常數。
_GUILD_SPEC = {
    "mages_guild": "magic",
    "fighters_guild": "combat",
    "companions": "combat",
    "knights_nine": "combat",
    "thieves_guild": "stealth",
    "dark_brotherhood": "stealth",
    "mythic_dawn": "stealth",
}
_SPECS = ("combat", "magic", "stealth")   # 固定呈現序


def _trainable_skill_set(gamedata: GameData, loc_id: str) -> set:
    """該城訓練師可指點的技能 id 集合(見上規則)。"""
    loc = gamedata.location(loc_id)
    td = gamedata.trainer_data(loc_id)
    override = td.get("skills") if td else None
    skills: set = set()
    if override:
        for entry in override:
            if entry in _SPECS:                    # 系 id → 展開該系全技
                skills.update(gamedata.skills_by_spec(entry))
            elif entry in gamedata.skills:         # 顯式技能 id
                skills.add(entry)
    else:
        specs = {_GUILD_SPEC[s] for s in loc.get("services", []) if s in _GUILD_SPEC}
        if specs:
            for sp in specs:
                skills.update(gamedata.skills_by_spec(sp))
        else:                                      # 無公會可推導 → 全技(現行行為)
            skills.update(gamedata.all_skill_ids())
    if td and td.get("master"):                    # 宗師之技必可在此習得
        skills.add(td["master"]["skill"])
    return skills


def trainer_specs(gamedata: GameData, loc_id: str) -> list[str]:
    """該城訓練師有得教的「系」清單(固定 combat/magic/stealth 序;供選單)。"""
    s = _trainable_skill_set(gamedata, loc_id)
    return [sp for sp in _SPECS if any(sid in s for sid in gamedata.skills_by_spec(sp))]


def trainer_skills(gamedata: GameData, loc_id: str, spec: str) -> list[str]:
    """該城在某系下實際可教的技能 id(保持 skills_by_spec 既有序)。"""
    s = _trainable_skill_set(gamedata, loc_id)
    return [sid for sid in gamedata.skills_by_spec(spec) if sid in s]


def trainer_cap(gamedata: GameData, loc_id: str, skill_id: str) -> int:
    """此城訓練師對該技的指點上限:一般 formulas.TRAINER_CAP;招牌城宗師之技取其 cap。"""
    td = gamedata.trainer_data(loc_id)
    if td and td.get("master") and td["master"]["skill"] == skill_id:
        return td["master"].get("cap", formulas.SKILL_CAP)
    return formulas.TRAINER_CAP


# --- 法師公會 -----------------------------------------------------------
def spell_price(gamedata: GameData, spell_id: str) -> int:
    return max(25, gamedata.spells[spell_id]["cost"] * 12)
