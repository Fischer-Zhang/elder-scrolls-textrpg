"""城戰(Phase 3+4):政治立場 + 選邊 + 攻城戰。城為單位 —— 各城主自有立場。

立場種子在 rulers.json 的 `stance`(imperial 復辟 / independent 獨立 / neutral 觀望),依各城主考據
指派(刻意跨省混合)。玩家擁護一個「大義」(allegiance)後:同立場=盟、對立=可攻、中立=觀望。

**攻城=混合制**(讓全套技能都有用武之地,不只戰鬥系):
  1. 圍城方略(SIEGE_OPS):一批**技能門檻**的作戰選項(偵查/夜襲/撬側門/勸降/賄賂/轟城/召喚襲擾…),
     各自耗時間/資源、**每役每略限一次**,成功則**削減守軍**(deplete_garrison)。涵蓋潛行/社交/工具/魔法系。
  2. 總攻(波次決戰):守軍折算成 `assault_waves(剩餘守軍)` 波,**每波一場 `combat` 群戰**(末波加守將 boss);
     波間**不恢復**傷勢/體力/魔力(消耗戰)、傷亡永久、可鳴金收兵(已破波次的折損持久)。守軍越多波數越多 →
     上百守軍無法靠少數人硬吞,圍城方略/大軍壓境削得越多波數越少 → 削弱真正兌現在波數上。

佔領後治理(A3):攻下的城你即為**事實領主**(court 顯示你而非舊領主);可**冊封總管**(`stewards`,一名親衛坐鎮)
→ 減叛亂流失令城自給。動態戰況掛 Character(存檔):city_faction(歸屬)、garrison_current(守軍)、siege_ops(已用方略)、
stewards(總管);首次存取由 rulers 種子懶初始化。加城/改立場純改 rulers.json;加圍城方略改 SIEGE_OPS;調平衡改本檔常數。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

CAUSES = {"imperial": "帝國復辟派", "independent": "獨立同盟",
          "own": "自立稱雄"}        # 三大義(王座之爭;神話黎明=末世密教,不列為政治大義)
STANCE_LABEL = {"imperial": "帝國復辟派", "independent": "獨立同盟", "neutral": "中立觀望",
                "own": "自立稱雄"}
# 擴張型大義:視「中立」為可吞(普世征服者);帝國/獨立則對中立維持觀望(不可攻)。
EXPANSIONIST_CAUSES = {"own"}
SIEGE_SOLDIER = "city_guard"   # 守軍/守將兵種(複用既有衛兵)
SIEGE_FAME = 30                # 攻下一城的聲望獎勵


def stance_label(stance: str | None) -> str:
    return STANCE_LABEL.get(stance, stance or "—")


def cause_name(cause: str) -> str:
    return CAUSES.get(cause, cause)


def base_stance(gamedata: GameData, loc_id: str) -> str | None:
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("stance", "neutral") if ruler else None


def city_bloc(gamedata: GameData, loc_id: str) -> str | None:
    """該城的正史旗號 id(rulers.json `bloc`;= Oblivion 當下歸屬的陣營身分)。無領主回 None。"""
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("bloc") if ruler else None


def city_bloc_label(gamedata: GameData, loc_id: str) -> str | None:
    """該城旗號的繁中名(rulers.json `bloc_label`,如「雷多然家族」)。無則回 None。"""
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("bloc_label") if ruler else None


def current_banner_label(char: Character, gamedata: GameData, loc_id: str) -> str | None:
    """該城『現時旗號』的繁中名(供對話 {bloc_label} 等內容 token 反映征服後歸屬):
    玩家攻下(city_faction)/大事件易幟(world_faction)→ 該大義名;否則回 rulers.json 靜態 bloc_label。
    根因修補:`{bloc_label}` 原讀靜態 bloc_label → 征服後仍喊舊陣營旗號(立場已翻、內容沒翻)。"""
    fac = char.city_faction.get(loc_id) or char.world_faction.get(loc_id)
    if fac:
        return cause_name(fac)
    return city_bloc_label(gamedata, loc_id)


def faction_of(char: Character, gamedata: GameData, loc_id: str) -> str | None:
    """該城現時歸屬,三層優先序:① city_faction(玩家親手攻下,最高;稅基紅線只認此層)
    ② world_faction(大事件易幟層;Phase C)③ base_stance(rulers.json 種子=Oblivion 當下)。無領主回 None。"""
    if loc_id in char.city_faction:
        return char.city_faction[loc_id]
    if loc_id in char.world_faction:                  # 大事件易幟(被玩家征服的城自動蓋過 → 免疫)
        return char.world_faction[loc_id]
    return base_stance(gamedata, loc_id)


def garrison_of(char: Character, gamedata: GameData, loc_id: str) -> int:
    if loc_id in char.garrison_current:
        return char.garrison_current[loc_id]
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("garrison", 0) if ruler else 0


def relationship(char: Character, gamedata: GameData, loc_id: str) -> str:
    """相對玩家 allegiance:none(無領主)/unaligned(未選邊)/ally/neutral/enemy。"""
    fac = faction_of(char, gamedata, loc_id)
    if fac is None:
        return "none"
    if not char.allegiance:
        return "unaligned"
    if fac == char.allegiance:
        return "ally"
    if fac == "neutral":
        return "enemy" if char.allegiance in EXPANSIONIST_CAUSES else "neutral"   # 自立/達貢吞中立
    return "enemy"


REL_LABEL = {"ally": "盟友", "enemy": "敵對", "neutral": "中立", "unaligned": "(你尚未選邊)"}


def pledge(char: Character, cause: str) -> None:
    char.allegiance = cause


# 凱瓦奇陷落大事件:解鎖神話黎明「密教公會」(招募/聖堂可見);神話黎明非政治大義,不可宣誓。
DAEDRIC_UNLOCK_EVENT = "kvatch_falls"


def pledgeable_causes(char: Character) -> list[str]:
    # 王座之爭三大義;神話黎明=末世密教(走公會入會 + 主線弧),不列為可宣誓的政治大義。
    return ["imperial", "independent", "own"]


def can_siege(char: Character, gamedata: GameData, loc_id: str) -> bool:
    """唯有已選邊、且該城為對立大義者可攻(中立/盟友不可攻)。"""
    return relationship(char, gamedata, loc_id) == "enemy"


def deplete_garrison(char: Character, gamedata: GameData, loc_id: str, amount: int) -> None:
    """圍城方略削減該城現存守軍(永久、進度持久化;清掉的守軍不再重生)。"""
    char.garrison_current[loc_id] = max(0, garrison_of(char, gamedata, loc_id) - amount)


# --- 圍城方略(siege operations:讓潛行/社交/工具/魔法系都有攻城用途)-----
# 每略:skill 門檻才開放、耗時間 + 資源、**每役每略限一次**(siege_ops 持久),成功削守軍。
# risk=True 者(夜襲/撬門)依技能擲成功;失敗不削、仍耗成本(被守軍察覺)。加略純改本表。
SIEGE_OPS = [
    {"id": "recon",     "name": "偵查弱點", "skill": "scout",       "min": 20, "hours": 2,
     "cost": {}, "base": 10, "per": 0.30, "risk": False,
     "desc": "摸清守軍布防與換崗,標出城防破綻。"},
    {"id": "nightraid", "name": "夜襲哨兵", "skill": "sneak",       "min": 30, "hours": 4,
     "cost": {"fatigue": 25}, "base": 15, "per": 0.55, "risk": True,
     "desc": "趁夜潛入,無聲清除哨兵與巡騎。"},
    {"id": "postern",   "name": "撬開側門", "skill": "security",    "min": 40, "hours": 2,
     "cost": {"fatigue": 10}, "base": 25, "per": 0.60, "risk": True,
     "desc": "撬開無人看守的側門,放細作入城製造混亂。"},
    {"id": "parley",    "name": "勸降策反", "skill": "speechcraft", "min": 40, "hours": 3,
     "cost": {}, "base": 15, "per": 0.70, "risk": False,
     "desc": "遣使勸降,策動守軍中的不滿者倒戈。"},
    {"id": "bribe",     "name": "賄賂守軍", "skill": "mercantile",  "min": 25, "hours": 1,
     "cost": {"gold": 150}, "base": 20, "per": 0.45, "risk": False,
     "desc": "金幣開路,買通守將麾下的隊長放水。"},
    {"id": "bombard",   "name": "法術轟城", "skill": "destruction", "min": 40, "hours": 1,
     "cost": {"magicka": 35}, "base": 20, "per": 0.65, "risk": False,
     "desc": "以毀滅法術轟擊城垛,在城牆上炸開缺口。"},
    {"id": "harry",     "name": "召喚襲擾", "skill": "conjuration", "min": 50, "hours": 1,
     "cost": {"magicka": 30}, "base": 20, "per": 0.55, "risk": False,
     "desc": "召喚魔物日夜襲擾,消磨守軍士氣與兵力。"},
]
SIEGE_OP_BY_ID = {op["id"]: op for op in SIEGE_OPS}


def ops_done(char: Character, loc_id: str) -> list[str]:
    return char.siege_ops.get(loc_id, [])


def can_afford_op(char: Character, op: dict) -> bool:
    c = op["cost"]
    return (char.gold >= c.get("gold", 0) and char.magicka >= c.get("magicka", 0)
            and char.fatigue >= c.get("fatigue", 0))


def available_ops(char: Character, gamedata: GameData, loc_id: str) -> list[dict]:
    """技能達門檻、且此役尚未施行過的圍城方略(可能因資源不足而仍列出但不可執行)。"""
    done = ops_done(char, loc_id)
    return [op for op in SIEGE_OPS
            if op["id"] not in done and char.skill(op["skill"]) >= op["min"]]


def op_deplete_amount(char: Character, op: dict) -> int:
    return round(op["base"] + char.skill(op["skill"]) * op["per"])


def resolve_op(char: Character, gamedata: GameData, loc_id: str, op_id: str, rng) -> dict:
    """施行一個圍城方略:扣成本、(風險型)擲成功、成功則削守軍、記為已用。

    回傳 {ok, deplete, reason?}。呼叫端須先確認 can_afford_op + 未用過。
    """
    op = SIEGE_OP_BY_ID[op_id]
    c = op["cost"]
    char.gold = max(0, char.gold - c.get("gold", 0))
    char.magicka = max(0, char.magicka - c.get("magicka", 0))
    char.fatigue = max(0, char.fatigue - c.get("fatigue", 0))
    char.siege_ops.setdefault(loc_id, []).append(op_id)   # 每役每略限一次(無論成敗)
    if op["risk"]:
        chance = max(0.1, min(0.95, 0.30 + char.skill(op["skill"]) * 0.006))
        if not rng.chance(chance):
            return {"ok": False, "deplete": 0, "reason": "alarm"}   # 被守軍察覺,無功而返
    amount = op_deplete_amount(char, op)
    deplete_garrison(char, gamedata, loc_id, amount)
    return {"ok": True, "deplete": amount}


WAVE_GARRISON = 50    # 每波總攻所折算的守軍當量(波數 = ceil(殘存守軍 / 此))
WAVE_GUARDS = 4       # 每波正面接戰的守兵數(末波另加守將);其餘戰力以波數體現


def assault_waves(remaining: int) -> int:
    """總攻波數:殘存守軍每 WAVE_GARRISON 折一波(至少 1 波=守將決戰)。
    守軍越多波數越多(上百守軍非少數人可硬吞);圍城方略/大軍壓境削守軍 → 直接砍波數,
    削弱的戰果在此兌現。每破一波永久削 WAVE_GARRISON 守軍 → 鳴金收兵亦保留戰果。"""
    return max(1, -(-max(0, int(remaining)) // WAVE_GARRISON))    # ceil 不依賴 math


def conquer(char: Character, gamedata: GameData, loc_id: str, now: int | None = None) -> None:
    """攻下:該城歸屬翻轉為你的大義,由你方重新駐軍,清掉本役方略紀錄,並起算徵稅週期(若給 now)。"""
    char.city_faction[loc_id] = char.allegiance
    ruler = gamedata.ruler_at(loc_id) or {}
    char.garrison_current[loc_id] = ruler.get("garrison", 100)
    char.siege_ops.pop(loc_id, None)
    if now is not None:                       # 起算佔領後徵稅(首期一週寬限);tick_tax 對缺漏亦會自癒
        char.tax_due_at[loc_id] = now + TAX_HOURS


def held_cities(char: Character, gamedata: GameData) -> list[str]:
    """目前歸屬玩家大義的城(含未攻的同立場盟城;供結算/戰情圖)。未選邊則空。
    ⚠️ 收稅切勿用本函式 —— 會把「未攻的同立場盟城」算進稅基(白送鉅額被動收入)。收稅用 held_tax_cities。"""
    if not char.allegiance:
        return []
    return [lid for lid in gamedata.rulers
            if faction_of(char, gamedata, lid) == char.allegiance]


# --- 城戰階段三:佔領後收稅(按居民數量)− 駐軍維護 + 輕量叛亂計時 -----------------
# 經濟對偶:招兵軍餉是「出」,佔領收稅是「進」。每座**你親手攻下**的城每 TAX_HOURS 結算一次:
#   居民稅(population×TAX_PER_POP)− 駐軍維護(garrison×GARRISON_MAINT_PER)→ 淨額入庫。
# 輕量叛亂計時:占領駐軍每期流失 UNREST_DECAY;駐軍跌破 UNREST_WARN → 民心浮動(稅收中斷、仍付維護);
#   潰散(≤GARRISON_REVOLT_AT)→ 城邦叛離脫離掌握。可出資加強駐軍回防(reinforce_garrison)。
# ⚠️ 紅線:稅基只認 city_faction(攻下的城),**不可**用 held_cities()(含盟城 → 白送稅,實測達 2000+/週)。
TAX_HOURS = 168               # 徵稅週期(每約一週;與軍餉同節律但各城獨立計時)
TAX_PER_POP = 0.5             # 居民稅率:稅 = 居民數 × 此值
GARRISON_MAINT_PER = 0.4      # 駐軍維護費率:支出 = 現存駐軍 × 此值(「守軍是支出維護費」)
UNREST_DECAY = 10             # 每期占領駐軍流失(輕量叛亂計時)
GARRISON_REGEN_PER = 6        # 階段四:安定領地每期自動回補駐軍(< UNREST_DECAY → 淨仍 −4/期,不破叛亂計時)
UNREST_WARN = 30              # 駐軍 ≤ 此 → 民心浮動(稅收中斷、將失守、不自動重建)
GARRISON_REVOLT_AT = 0        # 駐軍 ≤ 此 → 城邦叛離(脫離掌握)
REINFORCE_COST_PER = 4        # 加強駐軍:每補 1 兵的金幣
STEWARD_UNREST_RELIEF = 6     # 冊封總管:每期叛亂流失減免(總管坐鎮安民 → decay 10→4 < regen 6,城自給)


# --- 佔領治理(A3):自任領主 / 冊封總管 ----------------------------------
def steward_of(char: Character, loc_id: str) -> str | None:
    """你在該城冊封的總管 companion_id;未冊封回 None。"""
    return getattr(char, "stewards", {}).get(loc_id)


def has_steward(char: Character, loc_id: str) -> bool:
    """該城有在任總管(且該親衛仍在世/在列 —— 陣亡親衛不殘留治理加成)。"""
    sid = steward_of(char, loc_id)
    return bool(sid) and sid in char.companions


def appoint_steward(char: Character, loc_id: str, companion_id: str) -> None:
    char.stewards[loc_id] = companion_id


def recall_steward(char: Character, loc_id: str) -> None:
    char.stewards.pop(loc_id, None)


def effective_unrest_decay(char: Character, loc_id: str) -> int:
    """該城每期占領駐軍流失:有總管坐鎮 → 減免 STEWARD_UNREST_RELIEF(令安定城自給)。"""
    return max(0, UNREST_DECAY - (STEWARD_UNREST_RELIEF if has_steward(char, loc_id) else 0))


def held_tax_cities(char: Character, gamedata: GameData) -> list[str]:
    """你親手攻下且仍在手的城(city_faction 由 conquer 寫成你的大義)。
    與 held_cities 不同:**不含未攻的同立場盟城** —— 收稅務必用本函式(紅線見上)。"""
    if not char.allegiance:
        return []
    return [loc for loc, fac in char.city_faction.items() if fac == char.allegiance]


def city_population(gamedata: GameData, loc_id: str) -> int:
    return (gamedata.ruler_at(loc_id) or {}).get("population", 0)


def city_tax(gamedata: GameData, loc_id: str) -> int:
    return round(city_population(gamedata, loc_id) * TAX_PER_POP)


def base_garrison(gamedata: GameData, loc_id: str) -> int:
    return (gamedata.ruler_at(loc_id) or {}).get("garrison", 0)


def garrison_upkeep(char: Character, gamedata: GameData, loc_id: str) -> int:
    return round(garrison_of(char, gamedata, loc_id) * GARRISON_MAINT_PER)


def reinforce_cost(n: int) -> int:
    return n * REINFORCE_COST_PER


def can_reinforce(char: Character, gamedata: GameData, loc_id: str) -> bool:
    """你持有該城、駐軍未滿、且至少付得起 1 兵。"""
    return (loc_id in held_tax_cities(char, gamedata)
            and garrison_of(char, gamedata, loc_id) < base_garrison(gamedata, loc_id)
            and char.gold >= REINFORCE_COST_PER)


def reinforce_garrison(char: Character, gamedata: GameData, loc_id: str, n: int) -> int:
    """出資加強駐軍(gold → garrison,夾「該城原始守軍」上限與金幣)。回傳實際補的兵數。"""
    cur = garrison_of(char, gamedata, loc_id)
    n = max(0, min(n, base_garrison(gamedata, loc_id) - cur, char.gold // REINFORCE_COST_PER))
    char.gold -= n * REINFORCE_COST_PER
    char.garrison_current[loc_id] = cur + n
    return n


def territory_overview(char: Character, gamedata: GameData, loc_id: str, now: int) -> dict:
    """單城領地經營快照(供 court 面板與領地總覽共用)。countdown=距下次徵稅的小時(無紀錄→None)。"""
    g = garrison_of(char, gamedata, loc_id)
    maint = garrison_upkeep(char, gamedata, loc_id)
    tax = city_tax(gamedata, loc_id)
    due = char.tax_due_at.get(loc_id)
    return {"loc": loc_id, "population": city_population(gamedata, loc_id), "tax": tax,
            "garrison": g, "base": base_garrison(gamedata, loc_id), "maint": maint,
            "net": tax - maint, "unrest": g <= UNREST_WARN,
            "countdown": None if due is None else max(0, due - now)}


def tick_tax(state, gamedata: GameData) -> list[dict]:
    """於 game_loop 每圈頂端(緊接軍餉)結算各佔領城的徵稅/維護/叛亂。

    每座攻下的城每 TAX_HOURS:① 占領駐軍流失 UNREST_DECAY;② 潰散(≤floor)→ 城叛離;
    ③ 民心浮動(駐軍 ≤ UNREST_WARN)→ 稅收中斷但仍付維護(逼你回防);④ 否則收「居民稅 − 維護」淨額。
    可一次補結多個跳過的週期。回傳事件 [{kind:"tax"/"revolt", ...}] 供呈現。
    """
    char = state.player
    now = state.time.absolute_hours()
    events: list[dict] = []
    for loc in held_tax_cities(char, gamedata):
        if loc not in char.tax_due_at:           # 防呆:攻下未記時點(舊存檔/conquer 未傳 now)→ 給一週寬限
            char.tax_due_at[loc] = now + TAX_HOURS
            continue
        while (faction_of(char, gamedata, loc) == char.allegiance
               and loc in char.tax_due_at and now >= char.tax_due_at[loc]):
            g = max(0, garrison_of(char, gamedata, loc) - effective_unrest_decay(char, loc))   # 占領駐軍流失(總管減緩)
            char.garrison_current[loc] = g
            if g <= GARRISON_REVOLT_AT:                                   # 駐軍潰散 → 城叛離
                char.city_faction.pop(loc, None)
                char.garrison_current.pop(loc, None)
                char.tax_due_at.pop(loc, None)
                events.append({"kind": "revolt", "loc": loc})
                break
            maint = round(g * GARRISON_MAINT_PER)                         # 維護以「本期領餉駐軍」(回補前)計
            unrest = g <= UNREST_WARN                                     # 民心浮動 → 稅收中斷
            tax = 0 if unrest else city_tax(gamedata, loc)
            if not unrest:                                                # 階段四:安定領地自動緩慢重建
                g = min(base_garrison(gamedata, loc), g + GARRISON_REGEN_PER)  # 夾 base;淨 −4/期(decay 贏)
                char.garrison_current[loc] = g
            char.gold = max(0, char.gold + tax - maint)                   # 淨額入庫(夾 ≥0)
            char.tax_due_at[loc] += TAX_HOURS
            events.append({"kind": "tax", "loc": loc, "tax": tax, "maint": maint,
                           "net": tax - maint, "garrison": g, "unrest": unrest})
    return events
