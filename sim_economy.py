"""經濟量測(R222 建立、R223 起跨攤位倒掛應為 0;非測試;手動跑:PYTHONPATH=. python3 sim_economy.py [seeds=20];約 5 秒)

為什麼另寫:既有 sim 全是戰鬥,金幣流動從來沒有量測。R222 評估經濟時的數字(價格、套利、收入、去處)原本都是臨時腳本量的,
而之後四個里程碑(銷贓與贓物 / 練習與訓練 / 商人玩法 / 交易 100)每次動數值都要重量 → 收成一支固定工具。
所有價格都呼叫遊戲的真實函式(world.buy_price / sell_price / fence_sell_price / black_market_price / barter_breakdown /
train_cost / spell_price / merchant_catalog / _restock_qty),地城收入用真實生成器 dungeoncrawl.generate + loot.resolve_loot
擲 N 組種子;腳本本身不重寫任何公式。

輸出六段(6 行情見守衛 7):
  1 議價:係數 → 買賣倍率表;各加成來源與上限(加成合計遠大於上限留下的空間 = 上限遮蔽)。
  2 套利掃描:各種折扣組合下,逐一比對每種可賣物品的「一般商店買價」與「同店賣價 / 銷贓價 / 黑市買價」。
  3 收入:72 座地城各清一次的金幣與物品底價(依危險度)、一次性任務金幣、商店架上貨。
  4 去處:訓練、練習時數、用訓練買角色等級的價格、房產與擴建、法術、坐騎。
  5 配方轉賣:買原料 → 製作 → 賣成品是否有利可圖(只算原料全都買得到的配方)。

基準(R222·2026-11-26·seeds=20):
  議價:交易 5 魅力 40 → 買 ×2.03 賣 ×0.38;交易 100 魅力 100 → 買 ×1.20 賣 ×0.80(係數頂到上限 1.00)。
       七個加成來源合計 0.56,但交易 100 魅力 40 時只剩 0.20 空間、魅力 100 時空間為 0。
  套利:230 種可賣物品;同店 / 黑市 / 跨攤位倒掛全為 0(R223 起:銷贓價夾在該角色最低買價之下)。
       R222 當時(未夾):「議價滿 + 盜賊公會頂階 + 惡名 50」223 種銷贓價 ≥ 商店買價、206 種有賺(每件約底價的 32%),
       把貨架買光拿去銷贓每城每次補貨期望 418 金;「議價滿 + 惡名 50 + 聲望 700」205 / 175 種(約 6%)、65 金。
  收入:72 地城一次 ≈ 9.7 萬金 + 物品底價 ≈ 30.8 萬(賣掉實得 11.8 ~ 24.7 萬);
       425 個一次性任務(含執行時生成的領主委託)金幣 ≈ 8.9 萬;商店架上貨每家每次補貨底價中位數 ≈ 1,376。
  去處:22 技能全訓練到 75 = 43.6 萬金(角色 44 級);只靠訓練 1 → 5 級 2,848 金、→ 10 級 11,560 金、→ 20 級 59,288 金;
       免費練習只能到 50(R224;5 → 50 約 259 小時,只靠練習全技能到 50 = 角色 31 級);訓練師獨有的 50 → 75 每技能
       12,400 金、22 個技能共 27.3 萬;房產 16 棟 6.8 萬 + 擴建最多 4.96 萬;法術全買 2.9 萬;坐騎 0.64 萬。
  配方:原料買得到、買料製作再賣有賺的只剩鞣製皮革系(產出底價是原料的 1.33 倍):受庫存限制後每城每次補貨最多
       9 ~ 15 金,且每件要花一小時與體力 → 微利,使用者 R223 裁定不處理(RESALE_FLAG = 50 金以下不列警示)。
       R222 當時另有 130 組只在銷贓有賺(跨攤位倒掛經製作放大),R223 的全域規則一併關掉。

守衛(⚠;非自動閘門,改價格 / 折扣 / 銷贓 / 配方 / 物品底價後人工看):
  1. 同店倒掛:任一物品 一般商店買價 ≤ 同店賣價(world.buy_price 的反套利鐵則破了)。
  2. 黑市倒掛:任一物品 黑市買價 ≤ 銷贓價(R84 地板破了)。
  3. 跨攤位倒掛:任一物品 銷贓價 ≥ 一般商店買價(商店買、銷贓賣可獲利或打平)。R223 起應恆為 0
     (world.fence_sell_price 夾在 world.min_buy_price − 1);亮了 = 全域「賣出價 < 買入價」規則破了。
  4. 配方轉賣:原料全都買得到的配方,買料製作再賣,受庫存限制後每城每次補貨的期望利潤 ≥ RESALE_FLAG(50 金)。
  5. 練習上限 ≥ 訓練師上限:免費練習就能到訓練師賣的等級 → 訓練師沒有獨有的區段(R224)。
  8. 盜賊加成抬高買價 / 贓物價越界 / 行竊衰減太鬆(R225 ④):第 7 段。
  7. 行情倒掛(R225 ③):所有脈動行情同時生效時,賣給商店的價錢仍須低於最低買價(R223 全域規則)。
  6. 配方轉賣(商店投資後):全部商店投資到第 1 / 2 階(補貨加倍、不缺貨、另賣大城貨)時,守衛 4 的同一個門檻(R225 ②)。
"""
import statistics as S
import sys

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import dungeoncrawl, housing, loot, mastery, progression, spellfx, world

gd = get_gamedata()
SEEDS = 20
POOL = [iid for iid, d in gd.items.items() if d.get("value", 0) > 0 and not d.get("no_sell")]   # 可賣物品(每種一次)
BARTER_NODES = [(n["id"], o["opt_id"], o["name"], o.get("disposition_bonus", 0.0))
                for n in gd.mastery for o in n["options"] if o.get("kind") == "merchant_bonus"]
SHOP_LOCS = [lid for lid, loc in gd.world["locations"].items() if loc.get("merchant_stock")]
HOUSE_LOC = next(iter(gd.houses))          # 商誼折扣只看「所在省有自有的商誼房產」,任一房產城即可
TOP_THIEF = len(gd.factions["thieves_guild"]["ranks"]) - 1
TOP_FIGHTER = len(gd.factions["fighters_guild"]["ranks"]) - 1


def make_char(mercantile=5, personality=40, *, thieves=None, fighters=None, infamy=0, fame=0,
              blessing=False, pact=False, charm=False, nodes=False):
    """量測用角色:只設定會進價格鏈的欄位(全走真實欄位,不 patch 函式)。
    nodes=True → 把「達得到門檻」的議價里程碑全選(mastery.choose 自己會擋未達門檻者)。"""
    c = build_character(gd, name="商", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    c.skills.update(mercantile=mercantile)
    c.attributes.update(personality=personality)
    if thieves is not None:
        c.factions["thieves_guild"] = thieves
    if fighters is not None:
        c.factions["fighters_guild"] = fighters
    c.infamy, c.fame = infamy, fame
    if blessing:
        c.divine_blessing = {"divine": "zenithar", "expires_at": 10 ** 9}
    if pact:
        c.location_id = HOUSE_LOC
        c.houses_owned = [HOUSE_LOC]
        c.house_upgrades = {HOUSE_LOC: ["trade_pact"]}
    if charm:
        c.spell_effects = [{"kind": "charm", "magnitude": 1.0, "expires_at": 10 ** 9}]
    if nodes:
        c.skills.update(speechcraft=100, illusion=100)
        for nid, oid, _name, _v in BARTER_NODES:
            mastery.choose(c, gd, nid, oid)
    return c


MAXED = dict(mercantile=100, personality=100)
PROFILES = [
    ("新手(交易 5·魅力 40)", dict(mercantile=5, personality=40)),
    ("議價滿", dict(MAXED)),
    ("議價滿 + 惡名 50", dict(MAXED, infamy=50)),
    ("議價滿 + 惡名 50 + 聲望 700", dict(MAXED, infamy=50, fame=700)),
    ("議價滿 + 盜賊公會頂階", dict(MAXED, thieves=TOP_THIEF)),
    ("議價滿 + 盜賊公會頂階 + 惡名 50", dict(MAXED, thieves=TOP_THIEF, infamy=50)),
    ("交易 75·魅力 50 + 盜賊公會頂階 + 惡名 50", dict(mercantile=75, personality=50, thieves=TOP_THIEF, infamy=50)),
    ("全折扣疊滿", dict(MAXED, thieves=TOP_THIEF, fighters=TOP_FIGHTER, infamy=50, fame=700,
                      blessing=True, pact=True)),
]


# --- 1 議價 ---------------------------------------------------------------
def barter_table():
    """[(交易, 魅力, 係數, 一般貨買倍率, 賣倍率)]——倍率取自 world.barter_breakdown(真實連乘鏈)。"""
    rows = []
    for merc in (5, 25, 50, 75, 100):
        for pers in (40, 70, 100):
            b = world.barter_breakdown(make_char(merc, pers), gd)
            rows.append((merc, pers, b["d"], b["buy_goods"], b["sell_all"]))
    return rows


def barter_sources():
    """所有會加議價係數的來源 [(說明, 加成)](里程碑節點 + 魅惑術 + 同伴忠誠頂點)。"""
    out = [(f"{nid} {name}", v) for nid, _oid, name, v in BARTER_NODES]
    out.append(("魅惑術(生效中)", spellfx.CHARM_BARTER_BONUS))
    for cid, comp in gd.companions.items():
        cap = comp.get("capstone") or {}
        if cap.get("kind") == "barter":
            out.append((f"同伴 {cid} 忠誠頂點", cap.get("magnitude", 0.0)))
    return out


# --- 2 套利掃描 -------------------------------------------------------------
_QTY_CACHE: dict = {}


def expected_restock(item_id: str, tier: int = 0) -> float:
    """一次補貨的期望數量:對真實的 world._restock_qty 取樣、再經真實的 world.shop_qty(店面投資階數 tier,R225)取平均
    (不重寫補貨規則;tier 0 = 一般商店)。"""
    value = gd.item(item_id)["value"]
    material = item_id in world._crafting_material_ids(gd)
    key = (material, 0 if value <= 10 else 1 if value <= 80 else 2, tier)
    if key not in _QTY_CACHE:
        rng = RNG(7)
        _QTY_CACHE[key] = S.mean(world.shop_qty(world._restock_qty(value, rng, material=material), tier, 1.0)
                                 for _ in range(600))
    return _QTY_CACHE[key]


def arbitrage_scan():
    """逐 PROFILES 掃描。回傳 [dict(label, same_shop, black_market, cross, profit, worst_item, worst_pct, per_city)]。
    same_shop / black_market 是鐵則倒掛件數(應為 0);cross = 銷贓價 ≥ 商店買價的物品數(含打平);
    profit = 銷贓價 > 商店買價(真的有賺)的物品數;
    per_city = 各店「一次補貨的期望庫存 × 每件利潤」的中位數(把貨架買光拿去銷贓的期望利潤)。"""
    out = []
    for label, kw in PROFILES:
        c = make_char(**kw)
        same = black = cross = profit = 0
        worst = (0.0, "")
        gain = {}
        for iid in POOL:
            buy = world.buy_price(c, gd, iid)
            sell = world.sell_price(c, gd, iid)
            fence = world.fence_sell_price(c, gd, iid)
            if buy <= sell:
                same += 1
            if world.black_market_price(c, gd, iid) <= fence:
                black += 1
            if fence >= buy:                      # 鐵則口徑(賣出價必須「低於」買入價):打平也算倒掛
                cross += 1
            if fence > buy:                       # 真的賺得到錢的
                profit += 1
                gain[iid] = fence - buy
                pct = (fence - buy) / gd.item(iid)["value"]
                if pct > worst[0]:
                    worst = (pct, iid)
        per_city = [sum(expected_restock(i) * gain.get(i, 0) for i in world.merchant_catalog(gd, lid))
                    for lid in SHOP_LOCS]
        out.append({"label": label, "same_shop": same, "black_market": black, "cross": cross, "profit": profit,
                    "worst_item": worst[1], "worst_pct": worst[0], "per_city": S.median(per_city)})
    return out


# --- 3 收入 ---------------------------------------------------------------
def _value(entries) -> float:
    return sum(gd.item(i)["value"] * q for i, q in entries)


def _creature_loot(cid: str, rng: RNG) -> dict:
    c = gd.bestiary[cid]
    return loot.resolve_loot([{"gold": c["loot_gold"]}] + list(c["loot"]), rng, 1.0)


def dungeon_income(seeds: int = SEEDS):
    """每座地城清一次(全部怪、全部寶箱、首領與寶藏;幸運中性)的期望金幣與物品底價。
    回傳 {dungeon_id: (danger, gold, item_value)};用真實生成器 + 真實戰利品擲骰,取 seeds 組平均。"""
    out = {}
    for did, spec in gd.dungeons.items():
        gold = val = 0.0
        for seed in range(seeds):
            rng = RNG(1000 + seed)
            grid = dungeoncrawl.generate(spec, gd, rng)
            for layer in grid["layers"]:
                for row in layer:
                    for cell in row:
                        if cell["type"] == dungeoncrawl.CONTAINER:
                            r = loot.resolve_loot(cell["container"]["loot"], rng, 1.0)
                            gold += r["gold"]
                            val += _value(r["items"])
                        elif cell["type"] == dungeoncrawl.MONSTER:
                            for enemy in cell["enemies"]:
                                r = _creature_loot(enemy, rng)
                                gold += r["gold"]
                                val += _value(r["items"])
            boss = spec["boss"]
            if boss.get("enemy") in gd.bestiary:
                r = _creature_loot(boss["enemy"], rng)
                gold += r["gold"]
                val += _value(r["items"])
            r = loot.resolve_loot((boss.get("treasure") or {}).get("loot", []), rng, 1.0)
            gold += r["gold"]
            val += _value(r["items"])
        out[did] = (int(spec["danger"]), gold / seeds, val / seeds)
    return out


def quest_gold():
    """一次性任務的金幣報酬 {source: (件數, 總額)} 與可重複任務的中位數報酬。"""
    once: dict = {}
    repeat = []
    for q in gd.quests.values():
        g = (q.get("reward") or {}).get("gold", 0)
        if q.get("repeatable"):
            repeat.append(g)
        else:
            n, tot = once.get(q["source"], (0, 0))
            once[q["source"]] = (n + 1, tot + g)
    return once, (S.median(repeat) if repeat else 0)


def shelf_values(tier: int = 0):
    """各店一次補貨的期望架上貨底價(tier = 全部商店都投資到第幾階,R225)。"""
    return [sum(expected_restock(i, tier) * gd.item(i)["value"] for i in world.merchant_catalog(gd, lid, tier))
            for lid in SHOP_LOCS]


# --- 4 去處 ---------------------------------------------------------------
def train_total(lo: int, hi: int) -> int:
    """單一技能從 lo 訓練到 hi 的總價(真實 world.train_cost)。"""
    return sum(world.train_cost(level) for level in range(lo, hi))


def buy_levels(target_levels=(5, 10, 20)):
    """只靠付費訓練買角色等級:永遠訓練當下最便宜(等級最低)的技能,到訓練師上限為止。
    回傳 ({角色等級: 累計金幣}, 全部技能到訓練師上限的總價, 最終角色等級)。全走真實 progression。"""
    c = build_character(gd, name="徒", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    spent = 0
    marks = {}
    while True:
        cand = [s for s in gd.skills if c.skills.get(s, formulas.SKILL_BASE) < formulas.TRAINER_CAP]
        if not cand:
            break
        sid = min(cand, key=lambda k: c.skills.get(k, formulas.SKILL_BASE))
        level = c.skills.get(sid, formulas.SKILL_BASE)
        spent += world.train_cost(level)
        progression.use_skill(c, gd, sid, formulas.skill_threshold(level))
        while c.can_level_up():
            progression.apply_level_up(c, gd, {"endurance": formulas.LEVELUP_ATTRIBUTE_POINTS})
            marks[c.level] = spent
    return {lv: marks[lv] for lv in target_levels if lv in marks}, spent, c.level


def level_if_all_skills_reach(cap: int) -> int:
    """全部技能都升到 cap 時的角色等級(不論靠練習或訓練,升點給的等級經驗相同)。全走真實 progression。"""
    c = build_character(gd, name="徒", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    for sid in gd.skills:
        while c.skills.get(sid, formulas.SKILL_BASE) < cap:
            progression.use_skill(c, gd, sid, formulas.skill_threshold(c.skills.get(sid, formulas.SKILL_BASE)))
            while c.can_level_up():
                progression.apply_level_up(c, gd, {"endurance": formulas.LEVELUP_ATTRIBUTE_POINTS})
    return c.level


def practice_hours(lo: int, hi: int):
    """各技能靠免費練習從 lo 到 hi 需要的遊戲小時(不計體力不足的減半)。回傳 list。"""
    need = sum(formulas.skill_threshold(level) for level in range(lo, hi))
    return [need / s["practice"]["xp"] * s["practice"]["hours"] for s in gd.skills.values() if s.get("practice")]


def sinks():
    """一次性大額去處的總價。"""
    upg = 0
    for loc in gd.houses:
        prices = sorted((u["price"] for u in gd.house_upgrades.values()), reverse=True)
        upg += sum(prices[:housing.slots(gd, loc)])
    return {
        "houses": sum(h["price"] for h in gd.houses.values()),
        "upgrades": upg,
        "spells": sum(world.spell_price(gd, s) for s in gd.spells),
        "mounts": sum(m["price"] for m in gd.mounts.values()),
        "masters": sum(1 for t in gd.trainers.values() if t.get("master")),
    }


# --- 5 配方轉賣 -------------------------------------------------------------
RESALE_FLAG = 50      # 配方轉賣:受庫存限制後「每城每次補貨的期望利潤」達此金額才算警示(低於此 = 微利,使用者 R223 裁定不處理)


def recipe_resale(tier: int = 0):
    """原料全都買得到的配方:買料 → 製作 → 賣成品的利潤。
    回傳 [(profile_label, recipe_id, 原料買價, 賣給商店的收入, 賣給銷贓的收入, 每城每次補貨的期望利潤)](只列有利可圖者)。
    期望利潤 = 一次補貨買得到的原料做得出幾件(最缺的那種原料決定)× 每件利潤 —— 商店限量供貨,這才是實際賺得到的錢。
    另外每做一件還要花一小時與體力(crafting.craft 付該技能的 practice 成本),這裡沒有折算。"""
    buyable = {i for lid in SHOP_LOCS for i in world.merchant_catalog(gd, lid, tier)}
    out = []
    for label, kw in PROFILES:
        c = make_char(**kw)
        for rid, r in gd.recipes.items():
            if not all(i in buyable for i in r["inputs"]):
                continue
            cost = sum(world.buy_price(c, gd, i) * q for i, q in r["inputs"].items())
            o, n = r["output"], r.get("output_qty", 1)
            shop, fence = world.sell_price(c, gd, o) * n, world.fence_sell_price(c, gd, o) * n
            if max(shop, fence) > cost:
                crafts = min(expected_restock(i, tier) / q for i, q in r["inputs"].items())
                out.append((label, rid, cost, shop, fence, crafts * (max(shop, fence) - cost)))
    return out


# --- 6 行情(R225 ③)------------------------------------------------------------
PROVINCE_SHOPS = list({gd.world["locations"][lid]["province"]: lid for lid in reversed(SHOP_LOCS)}.values())   # 每省一家商店


def market_scan():
    """行情倒掛掃描:每個情境 × 每家商店 × 每種可賣物品,在「所有脈動行情同時生效」的最壞情況下,
    賣給商店的價錢(world.shop_sell_price)必須仍低於這個角色買得到的最低價(world.min_buy_price)——
    R223 全域規則不得被行情破壞。回傳 [(情境, 倒掛件數(商店 × 物品), 例)]。"""
    out = []
    # 另加一個只有商誼折扣的情境:「全折扣疊滿」的買價被 sell+1 地板頂住,商誼折扣在那裡沒作用,掃不出「夾限誤用所在地買價」的退化
    for label, kw in PROFILES + [("議價滿 + 在地商誼", dict(MAXED, pact=True))]:
        c = make_char(**kw)
        for pid in gd.world_pulse:
            c.world_pulse_day[pid] = 0              # 全部脈動在 today=0 同時生效
        bad, example = 0, ""
        here = [c.location_id]                      # 角色所在地(有商誼的情境 = 商誼所在省)
        if kw.get("pact"):                          # 持商誼的角色也要站在「別的省」掃一次:商誼折扣只在所在省生效,
            away = next(lid for lid in PROVINCE_SHOPS if gd.world["locations"][lid]["province"]
                        != gd.world["locations"][HOUSE_LOC]["province"])
            here.append(away)                       # 站別省時 buy_price 比 min_buy_price 高 → 夾限若誤用所在地買價就會漏出倒掛(R225 審查)
        for at in here:
            c.location_id = at
            for lid in PROVINCE_SHOPS:              # 同省商店的行情完全相同 → 每省掃一家代表店即可(72 家全掃要 20 秒)
                for iid in POOL:
                    shop = world.shop_sell_price(c, gd, iid, lid, 0)
                    boosted = world.market_factor(c, gd, lid, iid, 0) > 1.0
                    if shop >= world.min_buy_price(c, gd, iid) or (boosted and shop < world.sell_price(c, gd, iid)):
                        bad += 1
                        example = example or f"{lid}/{iid}(角色在 {at})"
        out.append((label, bad, example))
    return out


def market_uplift(province_loc: str, category: str, pulses=()):
    """各情境在某地賣出某市場類別物品的「賣價 ÷ 基準價」(平均;看議價高低讓行情的實際效益差多少)。"""
    ids = [i for i in POOL if world.item_market_category(gd, i) == category]
    out = []
    for label, kw in PROFILES:
        c = make_char(**kw)
        for pid in pulses:
            c.world_pulse_day[pid] = 0
        out.append((label, S.mean(world.shop_sell_price(c, gd, i, province_loc, 0) / world.sell_price(c, gd, i) for i in ids)))
    return out


# --- 7 贓物與行竊(R225 ④)-------------------------------------------------------
def thief_buy_scan():
    """盜賊公會加成不得抬高買價:每個有盜賊加成的情境,把「盜賊公會階級」拿掉後,買價必須完全相同
    (R225 ④ 之前買價地板看含公會加成的賣價 → 盜賊頂階買貨 +20%、買武甲 +35%)。開鎖器例外(會員免 ×2 外人加價,另一項公會福利)。
    回傳 [(情境, 買價不同的件數, 例)]。"""
    out = []
    for label, kw in PROFILES:
        if kw.get("thieves") is None:
            continue
        c, plain = make_char(**kw), make_char(**dict(kw, thieves=None))
        bad = [i for i in POOL if i != "lockpick" and world.buy_price(c, gd, i) != world.buy_price(plain, gd, i)]
        out.append((label, len(bad), bad[0] if bad else ""))
    return out


def stolen_scan():
    """贓物價(world.fence_stolen_price)對每個情境 × 每種物品:≥ 一般銷贓價;> 一般銷贓價的部分不超過上限(stolen_ceiling)。
    回傳 [(情境, 違反件數, 贓物價 ÷ 一般銷贓價 的平均, 有溢價的件數)]。"""
    from tesrpg.systems import crime
    out = []
    for label, kw in PROFILES:
        c = make_char(**kw)
        bad = prem = 0
        ratios = []
        for iid in POOL:
            clean, stolen = world.fence_sell_price(c, gd, iid), world.fence_stolen_price(c, gd, iid)
            if stolen < clean or stolen > max(clean, world.stolen_ceiling(c, gd, iid)):
                bad += 1
            prem += stolen > clean
            ratios.append(stolen / clean)
        out.append((label, bad, S.mean(ratios), prem))
    return out


# --- 報告 -----------------------------------------------------------------
def main() -> None:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else SEEDS
    flags = []

    print("== 1 議價:係數 → 實際買賣倍率(一般貨;底價 × 多少)==")
    print(f"{'交易':>4}{'魅力':>5}{'係數':>7}{'買×':>7}{'賣×':>7}{'買/賣':>7}")
    for merc, pers, d, buy, sell in barter_table():
        print(f"{merc:>6}{pers:>7}{d:>9.2f}{buy:>8.2f}{sell:>8.2f}{buy / sell:>8.2f}")
    src = barter_sources()
    print(f"加議價的來源 {len(src)} 個,合計 {sum(v for _n, v in src):.2f};係數上限 {world.BARTER_CAP:.2f}:")
    for name, v in src:
        print(f"  +{v:.2f}  {name}")
    for merc, pers in ((100, 40), (100, 100)):
        b = world.barter_breakdown(make_char(merc, pers), gd)
        print(f"  交易 {merc} 魅力 {pers}:基底 {b['raw']:.2f} → 還有 {max(0.0, world.BARTER_CAP - b['raw']):.2f} 空間給加成")
    b = world.barter_breakdown(make_char(100, 100, nodes=True, charm=True), gd)
    print(f"  交易 100 魅力 100 + 全部里程碑 + 魅惑術:相加 {b['raw']:.2f},超出上限的 {b['wasted']:.2f} "
          f"折抵服務價 −{b['service_rebate']:.0%}(R225;每溢出 0.1 折 5%、上限 20%)")

    print(f"\n== 2 套利掃描({len(POOL)} 種可賣物品;倒掛 = 件數)==")
    print(f"{'情境':34}{'同店':>5}{'黑市':>5}{'跨攤位':>7}{'有賺':>5}{'每件最多賺':>12}{'每城每次補貨':>14}")
    for r in arbitrage_scan():
        worst = f"{r['worst_pct']:.0%} {r['worst_item']}" if r["profit"] else "—"
        print(f"{r['label']:34}{r['same_shop']:>6}{r['black_market']:>6}{r['cross']:>8}{r['profit']:>6}"
              f"{worst:>22}{r['per_city']:>10.0f}")
        if r["same_shop"]:
            flags.append(f"⚠同店倒掛 {r['label']}:{r['same_shop']} 種物品買價 ≤ 賣價")
        if r["black_market"]:
            flags.append(f"⚠黑市倒掛 {r['label']}:{r['black_market']} 種物品黑市買價 ≤ 銷贓價")
        if r["cross"]:
            flags.append(f"⚠跨攤位倒掛 {r['label']}:{r['cross']} 種物品銷贓價 ≥ 商店買價,其中 {r['profit']} 種有賺"
                         f"(每城每次補貨約 {r['per_city']:.0f} 金)—— 全域「賣出價 < 買入價」規則破了")

    print(f"\n== 3 收入(地城用真實生成器 × {seeds} 組種子)==")
    inc = dungeon_income(seeds)
    low = world.barter_breakdown(make_char(5, 40), gd)["sell_all"]
    high = world.barter_breakdown(make_char(100, 100), gd)["sell_all"]
    print(f"{'危險度':>4}{'座數':>5}{'每座金幣':>9}{'每座物品底價':>12}")
    for danger in sorted({d for d, _g, _v in inc.values()}):
        xs = [(g, v) for d, g, v in inc.values() if d == danger]
        print(f"{danger:>6}{len(xs):>7}{S.mean(g for g, _ in xs):>12.0f}{S.mean(v for _, v in xs):>16.0f}")
    gold_all = sum(g for _d, g, _v in inc.values())
    val_all = sum(v for _d, _g, v in inc.values())
    print(f"{len(inc)} 座各清一次:金幣 {gold_all:.0f} + 物品底價 {val_all:.0f}"
          f"(賣掉實得 {val_all * low:.0f} ~ {val_all * high:.0f},看議價)")
    once, rep = quest_gold()
    quest_all = sum(t for _n, t in once.values())
    print(f"一次性任務 {sum(n for n, _t in once.values())} 個,金幣報酬合計 {quest_all};可重複任務報酬中位數 {rep:.0f}")
    for source, (n, tot) in sorted(once.items(), key=lambda kv: -kv[1][1])[:6]:
        print(f"  {source:10}{n:>4} 個 {tot:>7}")
    shelves = shelf_values()
    print(f"商店 {len(shelves)} 家,一次補貨的架上貨底價:中位數 {S.median(shelves):.0f}、合計 {sum(shelves):.0f}")
    for t, tdef in enumerate(world.SHOP_INVEST_TIERS, 1):       # R225 ②:商店投資後的架上貨(行竊 / 銷贓的上界)
        sv = shelf_values(t)
        print(f"  全部商店投資到第 {t} 階「{tdef['name']}」:中位數 {S.median(sv):.0f}"
              f"(×{S.median(sv) / S.median(shelves):.1f})、合計 {sum(sv):.0f}")

    print("\n== 4 去處 ==")
    base, cap = formulas.SKILL_BASE, formulas.TRAINER_CAP
    print(f"訓練單價 = max(20, 8 × 技能等級);單一技能 {base}→{cap}:{train_total(base, cap)} 金,"
          f"{cap}→{formulas.SKILL_CAP}(僅宗師技能):{train_total(cap, formulas.SKILL_CAP)} 金")
    marks, all_cost, final_level = buy_levels()
    print(f"只靠訓練買角色等級(永遠訓練最低的技能):"
          + "、".join(f"{lv} 級 {gold} 金" for lv, gold in marks.items())
          + f";{len(gd.skills)} 個技能全到 {cap} 共 {all_cost} 金(角色 {final_level} 級)")
    pcap = formulas.PRACTICE_CAP
    hrs = S.median(practice_hours(base, pcap))
    print(f"免費練習只能到 {pcap}(R224):{base}→{pcap} 中位數 {hrs:.0f} 小時(約 {hrs / 24:.0f} 遊戲日),"
          f"同一段訓練師收 {train_total(base, pcap)} 金;只靠練習(零風險)全技能到 {pcap} → 角色 {level_if_all_skills_reach(pcap)} 級")
    print(f"訓練師獨有的區段 {pcap}→{cap}:每技能 {train_total(pcap, cap)} 金,{len(gd.skills)} 個技能共 "
          f"{len(gd.skills) * train_total(pcap, cap)} 金")
    if pcap >= cap:
        flags.append(f"⚠練習上限 {pcap} ≥ 訓練師上限 {cap}:訓練師沒有獨有的區段(免費練習就能到同樣的等級)")
    sk = sinks()
    invest = sum(d["price"] for d in world.SHOP_INVEST_TIERS)
    print(f"投資商店(R225 ②):每家 {' + '.join(str(d['price']) for d in world.SHOP_INVEST_TIERS)} = {invest} 金,"
          f"{len(SHOP_LOCS)} 家全投資 {invest * len(SHOP_LOCS)} 金(不含議價折抵)")
    print(f"房產 {len(gd.houses)} 棟 {sk['houses']} 金 + 擴建(格位裝滿)最多 {sk['upgrades']} 金;"
          f"法術 {len(gd.spells)} 道全買 {sk['spells']} 金;坐騎 {sk['mounts']} 金;宗師技能 {sk['masters']} 個")
    master_extra = sk["masters"] * train_total(cap, formulas.SKILL_CAP)
    print(f"帳:一次性收入 金幣 {gold_all + quest_all:.0f} + 物品實得 {val_all * low:.0f} ~ {val_all * high:.0f};"
          f"去處 訓練到頂 {all_cost + master_extra} + 房產擴建 {sk['houses'] + sk['upgrades']}"
          f" + 法術 {sk['spells']} + 坐騎 {sk['mounts']}")

    print("\n== 5 配方轉賣(原料全都買得到的配方)==")
    resale = recipe_resale()
    if resale:
        print(f"{'情境':34}{'有賺的配方':>8}{'每城每次補貨最多賺':>14}   最賺的一組")
        for label, _kw in PROFILES:
            rows = [x for x in resale if x[0] == label]
            if not rows:
                continue
            best = max(rows, key=lambda x: x[5])
            print(f"{label:34}{len(rows):>10}{best[5]:>18.0f}   {best[1]} 原料 {best[2]} → 商店 {best[3]} / 銷贓 {best[4]}")
        big = [x for x in resale if x[5] >= RESALE_FLAG]
        if big:
            worst = max(big, key=lambda x: x[5])
            flags.append(f"⚠配方轉賣 {len(big)} 組(情境 × 配方)每城每次補貨期望利潤 ≥ {RESALE_FLAG} 金"
                         f"(最多 {worst[5]:.0f}:{worst[0]} 的 {worst[1]})")
        else:
            print(f"  以上都是微利(每城每次補貨不到 {RESALE_FLAG} 金,且每件還要花一小時與體力)→ 不列警示")
    else:
        print("  沒有任何情境 × 配方有利可圖")
    for t, tdef in enumerate(world.SHOP_INVEST_TIERS, 1):       # R225 ②:補貨加倍會放大「買料製作再賣」的量 → 投資後再量一次
        rs = recipe_resale(t)
        best = max(rs, key=lambda x: x[5], default=None)
        print(f"  全部商店投資到第 {t} 階「{tdef['name']}」:有賺的組合 {len(rs)} 組,每城每次補貨最多賺 "
              + (f"{best[5]:.0f}({best[0]} 的 {best[1]})" if best else "—"))
        if best and best[5] >= RESALE_FLAG:
            flags.append(f"⚠配方轉賣(商店投資第 {t} 階後)每城每次補貨期望利潤 ≥ {RESALE_FLAG} 金"
                         f"(最多 {best[5]:.0f}:{best[0]} 的 {best[1]})")

    print("\n== 6 行情(R225 ③:各省固定偏好 ×1.2 / ×0.9 + 脈動短期行情 ×1.3;只動賣給商店的價錢)==")
    cats = gd.market["categories"]
    print("市場類別:" + "、".join(f"{c['name']} {sum(1 for i in POOL if world.item_market_category(gd, i) == cid)} 種"
                                for cid, c in cats.items())
          + f";不屬任何類別 {sum(1 for i in POOL if world.item_market_category(gd, i) is None)} 種(不受行情影響)")
    scan = market_scan()
    for label, bad, example in scan:
        if bad:
            flags.append(f"⚠行情倒掛 {label}:{bad} 組(商店 × 物品)賣給商店的價錢 ≥ 最低買價,如 {example}(R223 全域規則被行情破壞)")
    print(f"倒掛掃描(所有脈動行情同時生效 × {len(PROVINCE_SHOPS)} 省各一家商店 × {len(POOL)} 種物品 × {len(scan)} 個情境):"
          + ("全為 0" if not any(b for _l, b, _e in scan) else "有倒掛,見警示"))
    boosted = [(pid, p["market"]["category"]) for pid, p in sorted(gd.world_pulse.items()) if p.get("market")]
    print(f"有行情的脈動 {len(boosted)} / {len(gd.world_pulse)};各省固定偏好 {len(gd.market['provinces'])} 省")
    print("實際效益(賣價 ÷ 基準價;議價越高、行情越容易頂到「賣價必須低於買價」的上限):")
    print(f"  {'情境':34}{'武器·天際 固定 ×1.2':>20}{'魂石·夏暮 固定+行情 ×1.56':>26}")
    fixed = dict(market_uplift("whiterun", "weapon"))
    stack = dict(market_uplift("alinor", "soul", ("pulse_summerset_deepstir",)))
    for label, _kw in PROFILES:
        print(f"  {label:34}{fixed[label]:>20.3f}{stack[label]:>26.3f}")

    print("\n== 7 贓物與行竊(R225 ④:盜賊加成不抬買價 / 贓物例外 / 行竊衰減)==")
    from tesrpg.systems import crime
    for label, bad, example in thief_buy_scan():
        if bad:
            flags.append(f"⚠盜賊加成抬高買價 {label}:{bad} 種物品的買價與「沒有盜賊公會」的同款情境不同,如 {example}")
    print("盜賊情境的買價與「拿掉盜賊公會」後逐件相同:" + ("全部相同" if not any(b for _l, b, _e in thief_buy_scan()) else "有差異,見警示"))
    print(f"{'情境':36}{'贓物價 ÷ 一般銷贓價':>20}{'有溢價的件數':>12}")
    for label, bad, ratio, prem in stolen_scan():
        print(f"{label:36}{ratio:>20.2f}{prem:>9}/{len(POOL)}")
        if bad:
            flags.append(f"⚠贓物價越界 {label}:{bad} 種物品的贓物價低於一般銷贓價或超過贓物上限")
    g = crime.SHOP_THEFT_DECAY
    cap = 0.95 / (1 - g)
    print(f"行竊衰減:同店同補貨期每次下手(含失手)得手率 ×{g};單一貨品期望得手上限 = 0.95 /(1 − {g}) = {cap:.1f} 件"
          f"(店家重補貨歸零);贓物價上限 = 底價 ×(1.20 + 0.5 × min(溢出, 0.40)),最高 ×1.40")
    if cap > 20:
        flags.append(f"⚠行竊衰減太鬆:期望得手上限 {cap:.1f} 件 > 20(SHOP_THEFT_DECAY = {g})")

    if flags:                                    # 只有真的有警示才印「⚠ 守衛警示」(check.sh 以此行 grep)
        print("\n⚠ 守衛警示:\n  " + "\n  ".join(flags))
    else:
        print("\n✓ 經濟守衛全過(無同店 / 黑市 / 跨攤位倒掛;配方轉賣都在微利門檻之下;練習上限低於訓練師上限)")


if __name__ == "__main__":
    main()
