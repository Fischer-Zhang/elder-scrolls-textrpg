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


# ── R180 趕路避險:路線偏好(存在角色身上)──────────────────────────────────────────────
# 只過濾「途中經過」的節點;起點與終點豁免(目的地本身是危險地城照樣可去)。
# 過濾後到不了就是到不了(回 [] / 不入 routes_from),**絕不**悄悄改走危險的路 —— 由呼叫端提示。
ROUTE_CAUTION = ("off", "dungeon", "danger")          # 不限 / 避開地城格 / 避開高危
ROUTE_CAUTION_DANGER = 4                              # 「高危」門檻:danger ≥ 4(避開 ≥3 會讓六成聚落互不相通)
ROUTE_CAUTION_LABEL = {"off": "不限(最短路)", "dungeon": "避開地城", "danger": "避開高危(危險度 4 以上)"}


def route_caution(char: Character) -> str:
    """角色目前的路線偏好;舊存檔/壞值一律視為 off(不限)。"""
    v = getattr(char, "route_caution", "off")
    return v if v in ROUTE_CAUTION else "off"


def cycle_route_caution(char: Character) -> str:
    """切到下一檔(不限 → 避開地城 → 避開高危 → 不限),回新檔位。"""
    char.route_caution = ROUTE_CAUTION[(ROUTE_CAUTION.index(route_caution(char)) + 1) % len(ROUTE_CAUTION)]
    return char.route_caution


def _passable(loc: dict, caution: str) -> bool:
    """能否把這個節點當「途中節點」穿越(不判斷起點/終點)。"""
    if caution == "dungeon":
        return loc.get("type") != "dungeon"
    if caution == "danger":
        return loc.get("danger", 0) < ROUTE_CAUTION_DANGER
    return True


def route_blocked(char: Character, gamedata: GameData, dest_id: str) -> bool:
    """目的地是否「只因路線偏好」而到不了(放寬到不限就有路)。"""
    if route_caution(char) == "off" or route_to(char, gamedata, dest_id):
        return False
    return bool(route_to(char, gamedata, dest_id, caution="off"))


def route_blocker(char: Character, gamedata: GameData, dest_id: str) -> str | None:
    """被路線偏好擋下時,最短路上第一個不能穿越的地點(給玩家「先去那裡」的線索);沒被擋 → None。"""
    if not route_blocked(char, gamedata, dest_id):
        return None
    locs, caution = gamedata.world["locations"], route_caution(char)
    return next((m for m in route_to(char, gamedata, dest_id, caution="off")[:-1]
                 if not _passable(locs[m], caution)), None)


def route_to(char: Character, gamedata: GameData, dest_id: str, caution: str | None = None) -> list[str]:
    """R114D 長途旅行:BFS 最短(跳數)路徑,回 [下一跳, …, dest_id](含終點·不含起點);
    已在該地或不可達 → []。**只經可見地點**(湮滅之門/神殿 gate 一致);純圖走、零 rng
    → 決定性(links 為 JSON 插入序·BFS 逐層 → 等長路徑取穩定序)。
    R180:依路線偏好不穿越被避開的節點(`caution=None` 取角色設定;傳 "off" 可查不設限的路)。"""
    from collections import deque
    if dest_id == char.location_id or not is_visible(char, gamedata, dest_id):
        return []
    locs = gamedata.world["locations"]
    if dest_id not in locs:
        return []
    caution = route_caution(char) if caution is None else caution
    prev: dict = {char.location_id: None}
    frontier = deque([char.location_id])
    while frontier:
        cur = frontier.popleft()
        if cur == dest_id:
            break
        for d in locs[cur].get("links", {}):
            if d in prev or not is_visible(char, gamedata, d):
                continue
            prev[d] = cur                                     # 先記下:被避開的節點仍可以是「終點」
            if _passable(locs[d], caution):                   # ……但不從它往外走
                frontier.append(d)
    if dest_id not in prev:
        return []
    path: list[str] = []
    n = dest_id
    while n != char.location_id:
        path.append(n)
        n = prev[n]
    path.reverse()
    return path


def route_hours(char: Character, gamedata: GameData, path: list[str]) -> int:
    """路徑名目總時數(各跳 base_hours 和;不含運動/坐騎加速的估計值)。純讀。"""
    locs = gamedata.world["locations"]
    total, cur = 0, char.location_id
    for hop in path:
        total += (locs[cur].get("links", {}) or {}).get(hop, 0)
        cur = hop
    return total


def travel_factor(char: Character, gamedata: GameData) -> float:
    """旅行耗時係數(越小越快;夾 floor 0.5)。純讀、零 rng。R197:自 `travel()` 抽出,**旅行選單 / 地點卡 / 地圖顯示的
    實際時數與真正出發共用此式**(預覽 = 實擲)。來源:運動 + 運動 50「健步如飛」兼帶旅速(R195 前稱長途健步)+ 同伴「識途」+
    坐騎 + 駿馬座疾行 + 凱娜瑞絲之佑(R107)。⚠ 各項相減的順序即浮點運算順序,勿重排(逐位元組同舊)。"""
    from tesrpg.systems import birthsign_ability, divines, mastery, mounts, party
    return max(0.5, formulas.athletics_travel_factor(char.skill("athletics"))
               - mastery.travel_factor_bonus(char, gamedata)
               - party.passive_capstone_factor(char, gamedata, "travel")
               - mounts.travel_factor_bonus(char, gamedata)
               - birthsign_ability.travel_factor_bonus(char, gamedata)
               - divines.travel_factor_bonus(char, gamedata))


def scaled_hours(base_hours: int, factor: float) -> int:
    """一跳的實際耗時:max(1, round(名目 × 係數))(逐跳取整,與真實逐跳旅行同一個式子)。"""
    return max(1, round(base_hours * factor))


def travel_hours(char: Character, gamedata: GameData, base_hours: int) -> int:
    """一跳 base_hours 名目時數 → 實際耗時(套用旅速係數)。`travel()` 與所有「實際時數」顯示共用(預覽 = 實擲)。"""
    return scaled_hours(base_hours, travel_factor(char, gamedata))


def route_hours_actual(char: Character, gamedata: GameData, path: list[str]) -> int:
    """路徑實際總時數 = 逐跳旅行實際耗時之和(各跳各自取整,非「總和 × 係數」)。純讀。
    這是**估計值**(以出發當下的技能計):旅途中每跳都會練運動、常常升級,升級後旅速係數變小 → 真實耗時**永遠 ≤ 預測**,
    只有升級恰好跨過取整門檻(例:運動 31→32 使 4 時連線變 3 時)才有差。審查實測:隨機等級下約 1.4% 的路線有差;
    落在門檻等級的玩家,≥5 跳路線的不符率可達 26–58%(最大差數時)。故長途 / 任務目標選單標「約 M 時」。
    單跳(旅行選單)的實際時數則是精確的(travel() 先算時數、後練技能)。名目的 `route_hours` 不動(引擎 / 測試用)。"""
    locs = gamedata.world["locations"]
    factor = travel_factor(char, gamedata)
    total, cur = 0, char.location_id
    for hop in path:
        base = (locs[cur].get("links", {}) or {}).get(hop, 0)
        total += scaled_hours(base, factor) if base else 0
        cur = hop
    return total


def routes_from(char: Character, gamedata: GameData, caution: str | None = None,
                actual: bool = False) -> dict[str, tuple[int, int]]:
    """一次 BFS 回 {lid: (hops, hours)} —— 從當前地可達的所有可見地點(不含當前地)。
    等同對每個目的地各跑一次 `route_to`+`route_hours`,但攤成 O(V+E) 單趟(供互動地圖批量標
    「N 段·約 M 時」)。純圖走、零 rng、決定性(links 為 JSON 插入序、BFS 逐層 → 等長路徑穩定序;
    hops/hours 語意與 route_to/route_hours 一致)。R180:同 route_to 的路線偏好過濾。
    R197:`actual=True` → hours 改為實際時數(= route_hours_actual,逐跳套旅速係數);預設 False = 名目(逐位元組同舊)。"""
    from collections import deque
    locs = gamedata.world["locations"]
    start = char.location_id
    caution = route_caution(char) if caution is None else caution
    factor = travel_factor(char, gamedata) if actual else None
    prev: dict = {start: None}
    frontier = deque([start])
    while frontier:
        cur = frontier.popleft()
        for d in locs[cur].get("links", {}):
            if d in prev or not is_visible(char, gamedata, d):
                continue
            prev[d] = cur
            if _passable(locs[d], caution):                   # 被避開的節點仍是可達的「終點」,只是不穿越
                frontier.append(d)
    out: dict[str, tuple[int, int]] = {}
    for lid in prev:
        if lid == start:
            continue
        path: list[str] = []           # 回溯 → hops
        n = lid
        while n != start:
            path.append(n)
            n = prev[n]
        path.reverse()
        hours, cur = 0, start          # 沿路徑各跳 base 時數(同 route_hours;actual → 逐跳套旅速係數,同 route_hours_actual)
        for hop in path:
            base = (locs[cur].get("links", {}) or {}).get(hop, 0)
            hours += base if factor is None else (scaled_hours(base, factor) if base else 0)
            cur = hop
        out[lid] = (len(path), hours)
    return out


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
    from tesrpg.systems import mounts, spellfx, vampirism
    links = current_location(char, gamedata).get("links", {})
    base_hours = links[dest_id]
    hours = travel_hours(char, gamedata, base_hours)   # R197:與旅行選單 / 地點卡 / 地圖顯示的實際時數同一個函式(預覽 = 實擲)
    dest = gamedata.location(dest_id)

    foe = None
    _org_danger = current_location(char, gamedata).get("danger", 0)
    chance = (encounter_chance(max(dest.get("danger", 0), _org_danger), time.hour)   # R144:走出龍喉峰不比走進去安全(取兩端較險)
              * (1 - mounts.encounter_evade(char, gamedata))     # 獵馬規避路途埋伏
              * (1 - vampirism.night_evade(char, time))          # 吸血鬼夜視:夜間旅行更易避開埋伏(R56)
              * spellfx.invis_encounter_factor(char))            # R104 幻術隱形:大幅降低旅途遭遇(無隱形 → ×1.0 逐位元組同)
    from tesrpg.systems import quests
    hunt = quests.active_hunt_target(char, gamedata, dest_id)    # R109:狩獵中的劇情敵目標(無則 None → 下方逐位元組不變)
    if hunt is not None and rng.chance(HUNT_ENCOUNTER_CHANCE):
        foe = combat.spawn_creature(gamedata, hunt, rng)         # 任務啟動 → 高機率在對省野外撞見目標
    elif rng.chance(chance):
        foe = combat.random_encounter(gamedata, char.level, rng,
                                      max_danger=dest.get("danger", 1) + 1,
                                      biome=dest.get("biome"))

    time.advance(hours)
    char.location_id = dest_id
    skill_events = progression.use_skill(char, gamedata, "athletics", formulas.ATHLETICS_TRAVEL_XP)
    return {"foe": foe, "hours": hours, "base_hours": base_hours, "skill_events": skill_events}


# --- 商店定價(受 交易 + 魅力 影響)-----------------------------------
# R222:定價常數具名(值不變),讓價格函式與「議價來源分解」(barter_breakdown)共用同一組數字。
BARTER_CAP = 1.0               # 議價係數上限:技能 + 魅力 + 各加成「相加之後」才夾限(交易 100 + 魅力 100 即頂到)
BARTER_SKILL_DIVISOR = 150.0   # 議價係數基底 = (交易 + 魅力 × BARTER_ATTR_WEIGHT) / 此值
BARTER_ATTR_WEIGHT = 0.5
BUY_BASE_MULT = 2.2            # 買價 = 底價 × (BUY_BASE_MULT − 議價係數) → 2.2 ~ 1.2 倍
SELL_BASE_MULT = 0.3           # 賣價 = 底價 × (SELL_BASE_MULT + 議價係數 × SELL_BARTER_MULT) → 0.3 ~ 0.8 倍
SELL_BARTER_MULT = 0.5


def _barter_parts(char: Character, gamedata: GameData | None = None) -> list[tuple[str, float]]:
    """議價係數的各項來源,**依相加順序**排列。`_disposition_factor` 就是把它們照序相加再夾限,
    所以顯示用的分解(barter_breakdown)與實際價格同源;順序也不得更動(浮點相加順序 = 既有物價逐位元組同)。"""
    from tesrpg.systems import spellfx
    parts = [("base", (char.skill("mercantile") + char.attr("personality") * BARTER_ATTR_WEIGHT) / BARTER_SKILL_DIVISOR),
             ("charm", spellfx.charm_barter_bonus(char))]   # R104 幻術魅惑術:議價更划算(無 charm → +0)
    if gamedata is not None:                                # 里程碑「精算買賣/魅惑交易」議價加成 + 同伴忠誠頂點
        from tesrpg.systems import mastery, party
        parts.append(("mastery", mastery.merchant_bonus(char, gamedata)))
        parts.append(("companion", party.passive_capstone_factor(char, gamedata, "barter")))   # 同伴「人脈/巧手」忠誠頂點
    return parts


def _disposition_factor(char: Character, gamedata: GameData | None = None) -> float:
    parts = _barter_parts(char, gamedata)
    base = parts[0][1]
    for _key, value in parts[1:]:
        base += value
    return max(0.0, min(BARTER_CAP, base))


# R225 ① 議價溢出折抵服務價:議價超過上限(被夾掉的那一截)不再白耗,折成「服務價」折扣。
# 服務 = 訓練、法術、房產與擴建、坐騎、雇用傭兵(固定價目、不吃買賣倍率的付費項目);罰金 / 旅店不適用。
SERVICE_REBATE_PER_OVERFLOW = 0.5   # 溢出每 1.0 折 50%(= 每 0.1 折 5%)
SERVICE_REBATE_CAP = 0.20           # 折抵上限 20%(溢出 0.40 即頂到)


def barter_overflow(char: Character, gamedata: GameData | None = None) -> float:
    """議價被上限吃掉的量(raw 超過 BARTER_CAP 的部分);與 `_disposition_factor` 同源、同相加順序。"""
    parts = _barter_parts(char, gamedata)
    raw = parts[0][1]
    for _key, value in parts[1:]:
        raw += value
    return max(0.0, raw - BARTER_CAP)


def service_rebate(char: Character, gamedata: GameData | None = None) -> float:
    """溢出折抵的服務價折扣(0 ~ SERVICE_REBATE_CAP)。取到萬分位,免得浮點雜訊讓「零溢出」變成 0.9999…。"""
    return round(min(SERVICE_REBATE_CAP, barter_overflow(char, gamedata) * SERVICE_REBATE_PER_OVERFLOW), 4)


def service_price(char: Character, gamedata: GameData, base: float, guild_discount: float = 0.0) -> int:
    """服務價單一出處(R225):底價 ×(1 − 公會折扣)×(1 − 議價溢出折抵)。
    選單標籤、確認句、扣款一律走這個(預覽 = 實扣);無溢出、無公會折扣 → 逐位元組同舊價。"""
    return max(1, round(base * (1 - guild_discount) * (1 - service_rebate(char, gamedata))))


def rebate_pct_text(rebate: float) -> str:
    """折抵率 → 百分比字串(不含正負號):≥ 1% 取整,不到 1% 留一位小數(免得實際有折扣卻顯示「0%」)。"""
    pct = rebate * 100
    return f"{round(pct)}%" if pct >= 1 else f"{pct:.1f}%"


def rebate_note(char: Character, gamedata: GameData | None = None) -> str:
    """選單標題用的一小段:有折抵才出字(例:「議價折抵 −10%」),沒有就回空字串。"""
    r = service_rebate(char, gamedata)
    return f"議價折抵 −{rebate_pct_text(r)}" if r > 0 else ""


LOCKPICK_OUTSIDER_MARKUP = 2.0  # 開鎖器是盜賊公會的營生:非會員(含敵對)買得到但被坑這麼多倍
HUNT_ENCOUNTER_CHANCE = 0.6      # R109 任務條件式狩獵:接了以劇情敵為目標的 kill 任務時,在對省野外撞見目標的機率(高)


def _buy_chain(char: Character, gamedata: GameData, item_id: str, item: dict,
               pact_discount: float | None = None) -> float:
    """買價連乘(取整與反套利地板之前)。buy_price 與 barter_breakdown 的「實際倍率」共用同一條鏈(R222 抽出;
    運算順序不變 → 既有物價逐位元組同)。item 只讀 value / damage / armor_rating。"""
    from tesrpg.systems import factions
    price = item["value"] * (BUY_BASE_MULT - _disposition_factor(char, gamedata))
    # 開鎖器只在有盜賊公會的城販售;會員按常價,外人/敵對加價(仍買得到,但較貴)
    if item_id == "lockpick" and not factions.is_member(char, "thieves_guild"):
        price *= LOCKPICK_OUTSIDER_MARKUP
    # 戰士公會「軍械庫之誼」:買武器/護甲(含盾/弓/法杖)享階級折扣
    if "damage" in item or "armor_rating" in item:
        price *= 1 - factions.armory_discount(char, gamedata)
    # R101 聲望議價:聲望折扣 / 惡名加價(tier-0 → ×1.0 → 既有買價逐位元組同;只動買價·賣價不碰)
    from tesrpg.systems import renown
    price *= renown.price_factor(char)
    # R107 澤尼薩爾之佑:商賈之神的祝福享買價折扣(無祝福 → ×1.0 逐位元組同;只動買價·賣價不碰)
    from tesrpg.systems import divines
    price *= divines.buy_price_factor(char)
    # R110 在地商誼:本省有「已購在地商誼」的自有房產 → 買價折扣(無 → ×1.0 逐位元組同;
    # 只動買價·賣價不碰;插在反套利地板之前 → 任何疊加皆不可能倒掛)
    # pact_discount:None = 依目前所在省(一般買價);給值 = 指定商誼折扣(R223 算「任何商店的最低買價」用)
    from tesrpg.systems import housing
    price *= 1 - (housing.province_discount(char, gamedata) if pact_discount is None else pact_discount)
    return price


def buy_price(char: Character, gamedata: GameData, item_id: str) -> int:
    item = gamedata.item(item_id)
    # 反套利鐵則:同物買價恆 > 賣價(極端議價 + 滿階軍械庫折扣下,折扣不得倒掛成金幣泵)
    return max(1, round(_buy_chain(char, gamedata, item_id, item)), sell_price(char, gamedata, item_id) + 1)


def _sell_chain(char: Character, gamedata: GameData, value: float) -> float:
    """賣價連乘(取整之前)。sell_price 與 barter_breakdown 的「實際倍率」共用(R222 抽出;運算順序不變)。"""
    from tesrpg.systems import factions
    base = value * (SELL_BASE_MULT + _disposition_factor(char, gamedata) * SELL_BARTER_MULT)
    base *= 1 + factions.sell_bonus(char, gamedata)   # 盜賊公會銷贓加成(階級越高越多)
    return base


def sell_price(char: Character, gamedata: GameData, item_id: str) -> int:
    return max(1, round(_sell_chain(char, gamedata, gamedata.item(item_id)["value"])))


def min_buy_price(char: Character, gamedata: GameData, item_id: str) -> int:
    """這個角色在「任何」一般商店買到此物的最低價(R223)。買價鏈裡唯一隨地點變的是在地商誼,
    所以以「名下任一商誼」計;其餘(議價、公會、聲望、神恩)都跟著角色走。
    全域規則「任何攤位的賣出價都低於任何攤位的買入價」以它為界。"""
    from tesrpg.systems import housing
    chain = _buy_chain(char, gamedata, item_id, gamedata.item(item_id),
                       pact_discount=housing.best_province_discount(char, gamedata))
    return max(1, round(chain), sell_price(char, gamedata, item_id) + 1)


def fence_sell_price(char: Character, gamedata: GameData, item_id: str) -> int:
    """銷贓價(R84):一般賣價 ×(1 + 惡名分級加價),再受全域規則約束(R223):必須低於這個角色
    買得到的最低價(`min_buy_price`)——「商店買、銷贓賣」不得有利可圖,也不得打平。
    夾的是賣出價,不抬任何買價(R110 否決過抬買價)。下限是一般賣價(銷贓不會比賣給商店差)。
    銷贓選單的標籤、實際收款與 sim_economy 共用這一個函式。"""
    from tesrpg.systems import crime
    shop = sell_price(char, gamedata, item_id)
    raw = int(shop * (1 + crime.fence_bonus(char)))
    return max(shop, min(raw, min_buy_price(char, gamedata, item_id) - 1))


def black_market_price(char: Character, gamedata: GameData, item_id: str) -> int:
    """黑市買價(R84 / R200):恆 > 銷贓價 → 買來回銷必虧。選單標籤與扣款共用。"""
    return max(buy_price(char, gamedata, item_id), fence_sell_price(char, gamedata, item_id) + 1)


# --- R225 ③ 行情:各省固定偏好 + 脈動帶來的短期行情,只動「賣給一般商店」的價錢 ----------------
# 固定偏好(data/market.json 每省一類 ×1.2、一類 ×0.9);短期行情(data/world_pulse.json 的 market,通常 ×1.3,
# 在該脈動的聚光視窗內)。兩者相乘;同類多筆短期行情取最大。
# 🔴 全域規則(R223)不得破:`sell_price` 維持「無行情基準價」(銷贓、買價地板、min_buy_price 都只看它),
# 帶行情的賣價 = min(round(基準連乘 × 行情), min_buy_price − 1);行情 < 1 沒有套利問題,只下限 1 金。
MARKET_FAVORED_MULT = 1.2
MARKET_GLUTTED_MULT = 0.9


def item_market_category(gamedata: GameData, item_id: str) -> str | None:
    """物品所屬的市場類別(依 kind 或明列 id);不屬於任何類別 → None(不受行情影響)。每件至多一類(守衛驗證)。"""
    item = gamedata.item(item_id)
    for cid, cat in gamedata.market["categories"].items():
        if item_id in cat.get("items", ()) or item["kind"] in cat.get("kinds", ()):
            return cid
    return None


def market_state(char: Character, gamedata: GameData, loc_id: str, today: int) -> dict:
    """該地商店此刻的行情:{類別 id: {"fixed": 固定倍率, "pulse": 短期倍率, "mult": 相乘, "days_left", "note"}}(只列有行情的類別)。"""
    from tesrpg.systems import worldpulse
    province = gamedata.location(loc_id).get("province")
    pref = gamedata.market["provinces"].get(province, {})
    out: dict = {}
    if pref.get("favored"):
        out[pref["favored"]] = {"fixed": MARKET_FAVORED_MULT, "pulse": 1.0}
    if pref.get("glutted"):
        out[pref["glutted"]] = {"fixed": MARKET_GLUTTED_MULT, "pulse": 1.0}
    for cid, m in worldpulse.active_markets(char, gamedata, province, today).items():
        row = out.setdefault(cid, {"fixed": 1.0, "pulse": 1.0})
        row.update(pulse=m["mult"], days_left=m["days_left"], note=m["note"])
    for row in out.values():
        row["mult"] = row["fixed"] * row["pulse"]
    return out


def market_factor(char: Character, gamedata: GameData, loc_id: str, item_id: str, today: int) -> float:
    cat = item_market_category(gamedata, item_id)
    return market_state(char, gamedata, loc_id, today).get(cat, {}).get("mult", 1.0) if cat else 1.0


def shop_sell_price(char: Character, gamedata: GameData, item_id: str, loc_id: str, today: int) -> int:
    """賣給這地方一般商店的實際價:`sell_price`(基準)× 行情,上限受全域規則夾住。
    沒有行情(倍率恰為 1.0)→ 與 `sell_price` 逐位元組相同。選單標籤、確認句與實收共用這一個函式。"""
    f = market_factor(char, gamedata, loc_id, item_id, today)
    base = sell_price(char, gamedata, item_id)
    if f == 1.0:
        return base
    chain = _sell_chain(char, gamedata, gamedata.item(item_id)["value"])
    if f > 1.0:
        return max(base, min(round(chain * f), min_buy_price(char, gamedata, item_id) - 1))
    return max(1, round(chain * f))


def pulse_market_news(gamedata: GameData, pulse_id: str) -> str:
    """脈動廣播時附帶的行情一句話(該脈動沒有 market → 空字串)。例:行情:賽羅迪爾的商人收購武器價 +30%(約 8 天)—— 原因。"""
    from tesrpg.systems import worldpulse
    p = gamedata.world_pulse[pulse_id]
    m = p.get("market")
    if not m:
        return ""
    name = gamedata.market["categories"][m["category"]]["name"]
    return (f"行情:{p['province']}的商人收購{name}的價錢 {_signed_pct(m['mult'])}"
            f"(約 {p.get('active_window_days', worldpulse.DEFAULT_ACTIVE_WINDOW)} 天)—— {m.get('note', '')}")


def _signed_pct(ratio: float) -> str:
    """倍率 → 帶正負號的百分比字串(例 1.2 → 「+20%」、0.9 → 「−10%」)。"""
    n = round((ratio - 1) * 100)
    return f"{'+' if n >= 0 else '−'}{abs(n)}%"


def market_tag(char: Character, gamedata: GameData, item_id: str, loc_id: str, today: int) -> str:
    """賣貨清單單列的行情標示:例「行情 +20%」(行情本身的百分比,免得便宜貨的整數取整讓數字失真);
    被全域規則夾住(賣價已頂到買價之下)時,改標實際漲幅並註明;沒有行情 → 空字串。"""
    f = market_factor(char, gamedata, loc_id, item_id, today)
    if f == 1.0:
        return ""
    base, shop = sell_price(char, gamedata, item_id), shop_sell_price(char, gamedata, item_id, loc_id, today)
    if f > 1.0 and shop < round(_sell_chain(char, gamedata, gamedata.item(item_id)["value"]) * f):
        return f"行情 {_signed_pct(shop / base)},已頂到買價上限"
    return f"行情 {_signed_pct(f)}"


def market_line(char: Character, gamedata: GameData, loc_id: str, today: int) -> str:
    """商店入口的一句話:本地行情(固定偏好 + 短期行情);沒有任何行情 → 空字串。"""
    state = market_state(char, gamedata, loc_id, today)
    if not state:
        return ""
    cats = gamedata.market["categories"]
    fixed, pulse = [], []
    for cid, row in state.items():
        if row["fixed"] != 1.0:
            fixed.append(f"{cats[cid]['name']} {_signed_pct(row['fixed'])}")
        if row["pulse"] != 1.0:
            pulse.append(f"{cats[cid]['name']} {_signed_pct(row['pulse'])}(餘 {row['days_left']} 天)")
    parts = []
    if fixed:
        parts.append("、".join(fixed))
    if pulse:
        parts.append("短期行情:" + "、".join(pulse))
    return "本地商人收購行情 —— " + ";".join(parts) + "(只動賣給商店的價錢;買價與銷贓不受影響)"


def barter_breakdown(char: Character, gamedata: GameData) -> dict:
    """議價係數的來源分解(R222;商店標題、角色卡、sim_economy 共用)。

    係數 d 與買賣倍率取自與 buy_price / sell_price 同一組函式(預覽 = 實價):
      - buy_mult / sell_mult:只算議價的倍率(底價 × 多少)。
      - buy_goods / buy_gear / sell_all:一般貨、武器護甲、賣出的「實際倍率」——走真實的連乘鏈
        (聲望、神恩、商誼、公會折扣都算進去),只差取整與「買價至少比賣價多 1」的地板。
    rows 只供顯示:基底拆成交易與魅力兩列、里程碑拆成各選項;各列相加 = raw。
    wasted = 被上限吃掉的部分(raw 超過 BARTER_CAP 的量)。"""
    from tesrpg.systems import mastery
    parts = _barter_parts(char, gamedata)
    by_key = dict(parts)
    merc, pers = char.skill("mercantile"), char.attr("personality")
    rows = [{"key": "mercantile", "label": f"交易 {merc}", "value": merc / BARTER_SKILL_DIVISOR},
            {"key": "personality", "label": f"魅力 {pers}",
             "value": pers * BARTER_ATTR_WEIGHT / BARTER_SKILL_DIVISOR}]
    for name, value in mastery.merchant_bonus_sources(char, gamedata):
        rows.append({"key": "mastery", "label": name, "value": value})
    if by_key.get("charm"):
        rows.append({"key": "charm", "label": "魅惑術", "value": by_key["charm"]})
    if by_key.get("companion"):
        rows.append({"key": "companion", "label": "同伴", "value": by_key["companion"]})
    raw = parts[0][1]
    for _key, value in parts[1:]:
        raw += value
    d = _disposition_factor(char, gamedata)
    return {
        "rows": rows, "raw": raw, "cap": BARTER_CAP, "d": d, "wasted": max(0.0, raw - BARTER_CAP),
        "service_rebate": service_rebate(char, gamedata),   # R225:溢出折抵的服務價折扣
        "buy_mult": BUY_BASE_MULT - d, "sell_mult": SELL_BASE_MULT + d * SELL_BARTER_MULT,
        "buy_goods": _buy_chain(char, gamedata, "", {"value": 1.0}),
        "buy_gear": _buy_chain(char, gamedata, "", {"value": 1.0, "damage": 0}),
        "sell_all": _sell_chain(char, gamedata, 1.0),
    }


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
                          "sentinel", "daggerfall", "falinesti", "rimmen", "alinor"})


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


def merchant_catalog(gamedata: GameData, loc_id: str, tier: int = 0) -> list[str]:
    """該地商人「可能販售」的完整品項目錄:world.json 的 merchant_stock + 鍛造材料分級供給 + 法師城空魂石。
    每座 type=city 自動供應一般材料(_COMMON_MATERIALS);大城(MAJOR_CITIES)另供高級材料;法師城供空魂石(填充燃料)。
    tier = 這家店的投資階數(R225 ②;char.shop_invest):第 2 階起比照大城,另供高級材料與(法師城)大型 / 黑色空魂石。
    預設 0 = 原目錄(逐項同序同舊)。"""
    loc = gamedata.location(loc_id)
    catalog = list(loc.get("merchant_stock", []))
    major = loc_id in MAJOR_CITIES or tier >= SHOP_SUPPLY_TIER
    if loc.get("type") == "city":
        extra = list(_COMMON_MATERIALS) + (list(_HIGH_MATERIALS) if major else [])
        catalog += [iid for iid in extra if iid not in catalog]   # 去重:既有明列者不重複
    elif tier >= SHOP_SUPPLY_TIER:                                # 投資後的鎮:只補高級材料(一般材料原本就不賣,不憑空多賣)
        catalog += [iid for iid in _HIGH_MATERIALS if iid not in catalog]
    if "mages_guild" in loc.get("services", []):                  # 填充循環燃料:法師城供空魂石
        gems = list(_EMPTY_GEM_STOCK) + (list(_EMPTY_GEM_STOCK_MAJOR) if major else [])
        catalog += [iid for iid in gems if iid not in catalog]
    return catalog


# --- R225 ② 投資商店:在任一家商店付錢、永久升級那家店(兩階;存在 char.shop_invest[loc_id])---------------
# 第 1 階「擴充貨架」:補貨量加倍,且每樣貨補貨時至少 1 件(原本高價貨常常補 0 件=缺貨)。
# 第 2 階「大城貨源」:再開始賣大城才有的貨(高級錠材;法師城另有大型 / 黑色空魂石)。
# 刻意**不給賣價加成**(永久賣價加成 = 算得回本的理財商品);價錢吃 ① 的議價折抵(`service_price`)。
SHOP_INVEST_TIERS = (
    {"name": "擴充貨架", "price": 1000, "desc": "補貨量加倍,每樣貨至少補兩件(不再缺貨)"},
    {"name": "大城貨源", "price": 3000, "desc": "另賣大城才有的貨:高級錠材,法師城另有大型與黑色空魂石"},
)
SHOP_INVEST_RESTOCK_MULT = 2
SHOP_SUPPLY_TIER = 2          # 達此階才擴大目錄


def shop_tier(char: Character, loc_id: str) -> int:
    """這家店目前的投資階數(0 ~ len(SHOP_INVEST_TIERS));存檔裡的壞值一律夾回範圍。"""
    try:
        t = int(char.shop_invest.get(loc_id, 0))
    except (TypeError, ValueError, OverflowError):   # 手改存檔的 Infinity / NaN / 字串 / None → 當作沒投資
        return 0
    return max(0, min(len(SHOP_INVEST_TIERS), t))


def shop_invest_next(char: Character, gamedata: GameData, loc_id: str) -> dict | None:
    """下一階的投資資訊 {tier, name, desc, price};價錢已吃議價折抵。已到頂 / 此地沒有商店 → None。
    選單標籤、確認句與扣款共用這一個函式(預覽 = 實扣)。"""
    t = shop_tier(char, loc_id)
    if t >= len(SHOP_INVEST_TIERS) or not merchant_catalog(gamedata, loc_id):
        return None
    d = SHOP_INVEST_TIERS[t]
    return {"tier": t + 1, "name": d["name"], "desc": d["desc"],
            "price": service_price(char, gamedata, d["price"])}


def invest_shop(char: Character, gamedata: GameData, loc_id: str) -> int | None:
    """付錢升一階。成功回實付金額;已到頂 / 金幣不足 → None(不動任何狀態)。
    升級視為落成當下重新補貨一次(清掉補貨時點,呼叫端接著 ensure_stock),不然付了錢卻要等 3 天才看得到。"""
    nxt = shop_invest_next(char, gamedata, loc_id)
    if nxt is None or char.gold < nxt["price"]:
        return None
    char.gold -= nxt["price"]
    char.shop_invest[loc_id] = nxt["tier"]
    char.shop_restock_at.pop(loc_id, None)
    return nxt["price"]


def shop_qty(q: int, tier: int, rmult: float) -> int:
    """補貨抽到 q 之後的最終數量。tier 0:擲 0 = 缺貨(保留稀缺性 = 反套利),其餘照「行商人脈」倍率;
    tier ≥ 1:至少 1 件再 ×SHOP_INVEST_RESTOCK_MULT,最後同樣乘倍率。擲骰次數與 tier 無關(rng 序列不變)。"""
    if tier >= 1:
        return max(1, round(max(1, q) * SHOP_INVEST_RESTOCK_MULT * rmult))
    return 0 if q == 0 else max(1, round(q * rmult))


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
    tier = shop_tier(char, loc_id)                              # R225 ②:這家店的投資階數

    def _qty(iid):
        q = _restock_qty(gamedata.item(iid)["value"], rng, material=iid in mats)
        return shop_qty(q, tier, rmult)                         # tier 0:保留「擲 0 = 缺貨」的稀缺性(反套利)
    char.shop_stock[loc_id] = {iid: _qty(iid) for iid in merchant_catalog(gamedata, loc_id, tier)}
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
    return [iid for iid in merchant_catalog(gamedata, loc_id, shop_tier(char, loc_id)) if stock_qty(char, loc_id, iid) > 0]


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
