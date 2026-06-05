"""城戰(Phase 3+4):政治立場 + 選邊 + 攻城戰。城為單位 —— 各城主自有立場。

立場種子在 rulers.json 的 `stance`(imperial 復辟 / independent 獨立 / neutral 觀望),依各城主考據
指派(刻意跨省混合)。玩家擁護一個「大義」(allegiance)後:同立場=盟、對立=可攻、中立=觀望。

**攻城=混合制**(讓全套技能都有用武之地,不只戰鬥系):
  1. 圍城方略(SIEGE_OPS):一批**技能門檻**的作戰選項(偵查/夜襲/撬側門/勸降/賄賂/轟城/召喚襲擾…),
     各自耗時間/資源、**每役每略限一次**,成功則**削減守軍**(deplete_garrison)。涵蓋潛行/社交/工具/魔法系。
  2. 強攻(輕量化單場決戰):一場 `combat` 群戰,守軍數 = `assault_force(剩餘守軍)` + 守將 boss;
     勝 → 破城易幟。守軍越少(方略削得越多)強攻越輕鬆 → 方略與強攻形成 build 取捨。

動態戰況掛 Character(存檔):city_faction(歸屬)、garrison_current(守軍,被方略削)、siege_ops(已用方略);
首次存取由 rulers 種子懶初始化。加城/改立場純改 rulers.json;加圍城方略改 SIEGE_OPS;調平衡改本檔常數。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

CAUSES = {"imperial": "帝國復辟派", "independent": "獨立同盟"}   # 玩家可擁護的兩大義
STANCE_LABEL = {"imperial": "帝國復辟派", "independent": "獨立同盟", "neutral": "中立觀望"}
SIEGE_SOLDIER = "city_guard"   # 守軍/守將兵種(複用既有衛兵)
SIEGE_FAME = 30                # 攻下一城的聲望獎勵


def stance_label(stance: str | None) -> str:
    return STANCE_LABEL.get(stance, stance or "—")


def cause_name(cause: str) -> str:
    return CAUSES.get(cause, cause)


def base_stance(gamedata: GameData, loc_id: str) -> str | None:
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("stance", "neutral") if ruler else None


def faction_of(char: Character, gamedata: GameData, loc_id: str) -> str | None:
    """該城現時歸屬(攻城翻轉後以 city_faction 為準,否則回種子立場)。無領主回 None。"""
    if loc_id in char.city_faction:
        return char.city_faction[loc_id]
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
        return "neutral"
    return "enemy"


REL_LABEL = {"ally": "盟友", "enemy": "敵對", "neutral": "中立", "unaligned": "(你尚未選邊)"}


def pledge(char: Character, cause: str) -> None:
    char.allegiance = cause


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


def assault_force(remaining: int) -> int:
    """輕量化強攻的守軍數(隨剩餘守軍單調遞增;守將另計)。守軍削得越少 → 強攻越硬。"""
    return max(2, min(8, round(remaining / 55)))


def conquer(char: Character, gamedata: GameData, loc_id: str) -> None:
    """攻下:該城歸屬翻轉為你的大義,由你方重新駐軍,並清掉本役方略紀錄(下次可重新佈局)。"""
    char.city_faction[loc_id] = char.allegiance
    ruler = gamedata.ruler_at(loc_id) or {}
    char.garrison_current[loc_id] = ruler.get("garrison", 100)
    char.siege_ops.pop(loc_id, None)


def held_cities(char: Character, gamedata: GameData) -> list[str]:
    """目前歸屬玩家大義的城(供結算/戰情圖);未選邊則空。"""
    if not char.allegiance:
        return []
    return [lid for lid in gamedata.rulers
            if faction_of(char, gamedata, lid) == char.allegiance]
