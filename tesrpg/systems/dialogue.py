"""NPC 對話與好感 (disposition):說服(口才)、賄賂。

好感影響 NPC 是否願意託付任務。說服會 learn-by-doing 鍛鍊口才。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import events, factions, mastery, politics, progression

BRIBE_COST = 10
TALK_DOWN_MAX = 120          # 可「說服衛兵」的最高賞金(大罪說不過去;對齊武士 ~100 量級)
INTIMIDATE_DIFFICULTY = 40   # 威嚇喝退基準難度(對齊 events.json 既有威嚇 DC40)
INTIMIDATABLE = {"bandit", "rogue_thief", "city_guard"}   # 可威嚇喝退的人形敵:bandit(隨遇常見)+ rogue_thief/city_guard(劇情敵,罕見)。皆人形·非 solo boss·非具名要角;不死/魔人/野獸/boss 不可。實務上主要對盜匪生效(其餘為劇情情境)


def persuade_delta(skill: int) -> int:
    """說服成功的好感增益,隨口才成長(0→+6、50→+12、100→+18)→ 高口才勝過 bribe(+12)且免金幣。"""
    return round(6 + skill * 0.12)


def recruit_chance(char: Character) -> float:
    """遭遇式入會的說服成功率(吃口才+魅力);夾 0.10–0.85。供 UI 預示與 recruit_persuade 同源。"""
    return max(0.10, min(0.85, 0.20 + (char.skill("speechcraft") + char.attr("personality") - 50) * 0.005))


def recruit_persuade(char: Character, gamedata: GameData, rng: RNG) -> dict:
    """以口才說服遇上的教徒引你入會。付 speechcraft practice(體力+時間)→ 非免費刷。
    回傳 {ok, chance, hours, tired, skill_events}。"""
    chance = recruit_chance(char)
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    events = progression.use_skill(char, gamedata, "speechcraft", xp)
    return {"ok": rng.chance(chance), "chance": chance, "hours": hours, "tired": tired, "skill_events": events}


def disposition(char: Character, gamedata: GameData, npc_id: str) -> int:
    base = gamedata.npcs[npc_id]["disposition"]
    return max(0, min(100, base + char.npc_disposition.get(npc_id, 0)))


def _adjust(char: Character, npc_id: str, delta: int) -> None:
    char.npc_disposition[npc_id] = char.npc_disposition.get(npc_id, 0) + delta


def persuade_chance(char: Character, gamedata: GameData, npc_id: str) -> float:
    """說服成功率(唯讀,供 UI 預示;與 persuade 公式單一來源)。折服里程碑 → 1.0。"""
    if mastery.can_guaranteed_persuade(char, gamedata, npc_id):
        return 1.0
    from tesrpg.systems import vampirism
    skill = char.skill("speechcraft")
    return formulas.persuade_curve(0.35 + (skill + char.attr("personality") - 50) * 0.005
                                   + vampirism.charm_social_bonus(char))   # R63 漸進(舊夾 0.9→漸近 0.95);R56 吸血鬼魅惑


def persuade(char: Character, gamedata: GameData, npc_id: str, rng: RNG) -> dict:
    """以口才說服。成功提升好感,失敗略降。回傳 {ok, delta, hours, tired, skill_events}。

    每次說服付出口才 practice 的體力 + 時間成本(時間由呼叫端推進),與酒館練說服
    對齊,讓「對話磨嘴皮」不再是零代價的免費刷口才/刷好感(折服里程碑路徑同樣付費)。
    """
    skill = char.skill("speechcraft")
    delta = persuade_delta(skill)
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    events = progression.use_skill(char, gamedata, "speechcraft", xp)
    # 里程碑「辯舌·折服」:口才大師對每個 NPC 可一次性必定說服(記入 persuaded_npcs)。
    if mastery.can_guaranteed_persuade(char, gamedata, npc_id):
        char.persuaded_npcs.append(npc_id)
        _adjust(char, npc_id, delta)
        return {"ok": True, "delta": delta, "charmed": True,
                "hours": hours, "tired": tired, "skill_events": events}
    chance = formulas.persuade_curve(0.35 + (skill + char.attr("personality") - 50) * 0.005)   # R63 漸進
    if rng.chance(chance):
        _adjust(char, npc_id, delta)
        return {"ok": True, "delta": delta, "hours": hours, "tired": tired, "skill_events": events}
    _adjust(char, npc_id, -5)
    return {"ok": False, "delta": -5, "hours": hours, "tired": tired, "skill_events": events}


def bribe(char: Character, gamedata: GameData, npc_id: str) -> dict:
    if char.gold < BRIBE_COST:
        return {"ok": False, "message": "金幣不足。"}
    char.gold -= BRIBE_COST
    _adjust(char, npc_id, 12)
    return {"ok": True, "message": f"你塞了 {BRIBE_COST} 金,對方臉色和緩了些。"}


def offered_quest(char: Character, gamedata: GameData, npc_id: str) -> str | None:
    """好感足夠且任務未完成/未接 → 回傳該 NPC 可給的任務 id。"""
    npc = gamedata.npcs[npc_id]
    qid = npc.get("quest")
    if not qid:
        return None
    if qid in char.quests or qid in char.completed_quests:
        return None
    if disposition(char, gamedata, npc_id) < npc.get("quest_disposition", 60):
        return None
    return qid


def offered_rumor(char: Character, gamedata: GameData, npc_id: str) -> dict | None:
    """好感足夠且未兌現 → 回傳該 NPC 可「追問」的傳聞線索(R81 流言復活)。
    {"kind":"quest","id":qid}(線索任務,呼叫端走 _accept_and_brief)或
    {"kind":"landmark","id":loc}(即時揭露同省地標,呼叫端走 landmarks.discover)。
    一次性鎖全由既有狀態推導(quests/completed_quests/discovered_landmarks)→ 零新存檔欄。"""
    npc = gamedata.npcs[npc_id]
    if disposition(char, gamedata, npc_id) < npc.get("rumor_disposition", 0):
        return None
    qid = npc.get("rumor_quest")
    if qid and qid not in char.quests and qid not in char.completed_quests:
        obj = (gamedata.quests.get(qid) or {}).get("objective", {})
        # clear_dungeon 線索:已肅清過則不再給(避免接取即時免費完成)
        if not (obj.get("type") == "clear_dungeon" and obj.get("dungeon") in char.cleared_dungeons):
            return {"kind": "quest", "id": qid}
    loc = npc.get("rumor_landmark")
    if loc:
        from tesrpg.systems import landmarks
        if not landmarks.is_discovered(char, loc):
            return {"kind": "landmark", "id": loc}
    return None


# --- 拓展用途①:說服衛兵減免賞金(犯罪/社交;對位武士特權,走技能)----------
def talk_down_chance(char: Character, bounty: int, gamedata: GameData = None) -> float:
    """以口才說退衛兵的成功率:吃口才+魅力,賞金越高越難。夾 0.05–0.80。
    里程碑「巧言脫罪」(talk_down_lever)抬高下限。"""
    from tesrpg.systems import vampirism
    base = max(0.05, min(0.80,
               0.10 + (char.skill("speechcraft") + char.attr("personality") - 50) * 0.005 - bounty * 0.002
               + vampirism.charm_social_bonus(char)))               # 吸血鬼社交魅惑(R56·沿用夾限)
    if gamedata is not None:
        from tesrpg.systems import mastery
        base = max(base, mastery.talk_down_mod(char, gamedata).get("floor", 0.0))
    return base


def talk_down_guard(char: Character, gamedata: GameData, province: str, rng: RNG) -> dict:
    """以口才說退攔路衛兵(僅小額賞金,呼叫端負責 TALK_DOWN_MAX 門檻)。
    付 speechcraft practice(體力+時間)→ 非免費刷;成功 → 清該省賞金,失敗 → 賞金不動。"""
    from tesrpg.systems import crime
    b = crime.bounty(char, province)
    chance = talk_down_chance(char, b, gamedata)
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    events = progression.use_skill(char, gamedata, "speechcraft", xp)
    ok = rng.chance(chance)
    if ok:
        crime.clear_bounty(char, province)
    return {"ok": ok, "chance": chance, "hours": hours, "tired": tired, "skill_events": events}


# --- 拓展用途②:威嚇喝退弱人形敵(遭遇/避戰;對位潛行撤退)-------------------
def can_intimidate(gamedata: GameData, enemies) -> bool:
    """全部敵人皆屬可威嚇的弱人形(盜匪類)→ 才可威嚇喝退。"""
    return bool(enemies) and all(getattr(e, "template_id", None) in INTIMIDATABLE for e in enemies)


def intimidate_chance(char: Character, enemies, night: bool, gamedata=None) -> float:
    """威嚇喝退成功率:吃口才,敵越多越難、夜間略難。夾 0.05–0.90(仿 events 既有威嚇檢定)。
    里程碑「不怒自威」抬高下限。"""
    chance = 0.5 + (char.skill("speechcraft") - INTIMIDATE_DIFFICULTY) / 100.0 - (len(enemies) - 1) * 0.15
    if night:
        chance -= 0.10
    floor = 0.05
    if gamedata is not None:
        from tesrpg.systems import mastery
        floor = max(floor, mastery.intimidate_floor(char, gamedata))
    return max(floor, min(0.90, chance))


def intimidate(char: Character, gamedata: GameData, enemies, night: bool, rng: RNG) -> dict:
    """威嚇喝退弱人形敵(避戰)。付 speechcraft practice(體力+時間)→ 練口才但非免費刷;
    成功 → 敵退去(呼叫端避戰、**不給任何戰利/擊殺/xp 來自敵人**),失敗 → 接戰(警覺)。"""
    chance = intimidate_chance(char, enemies, night, gamedata)
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    skill_events = progression.use_skill(char, gamedata, "speechcraft", xp)
    return {"ok": rng.chance(chance), "chance": chance,
            "hours": hours, "tired": tired, "skill_events": skill_events}


# ======================================================================
# 條件式對話樹 + NPC 外交(里程碑)
# NPC 因玩家身分/陣營而有不同問候與話題;外交立場(faction_standing)記住你的選擇。
# 條件語法複用 events.meets(無 state 鍵)+ meets_dialogue(需 state/ctx 鍵)。
# ======================================================================

REPORT_BOUNTY = 40           # 看破吸血鬼報官 → 該省賞金
PRY_DIFFICULTY = 45          # 套話檢定基準難度
STANDING_CAP = 100           # 外交立場分夾限 [-CAP, CAP]

# 公會宿敵生態(R97):犯罪/隱蔽身分揭露門檻 + 調查揭露的 dialogue_done 標記(零新存檔欄)
GUILD_REVEAL_DISPOSITION = 75   # 高好感信任 → 得知其隱藏(犯罪)身分(秘密更深於一般任務門檻 60)
_GUILD_KNOWN = "__guild_known__"  # dialogue_done[npc] 標記:已調查揭露該 NPC 的隱藏身分

# 程式內 fallback(dialogue.json 缺漏時仍可運作;正式內容在 data/dialogue.json)
DEFAULT_GREETINGS = {
    "comrade": ["「自己人。風聲緊,長話短說 —— 有什麼要打聽的?」"],
    "friendly": ["「自己人 —— 有話直說。」"],
    "neutral": ["{greeting}"],
    "cold": ["「……有事快說。」"],
    "hostile": ["「{cause}的人,在這城裡可不受歡迎。」"],
    "vampire_seen": ["「你那雙眼睛……來人啊!這裡有吸血鬼!」"],
}
DEFAULT_ATTITUDE_TOPICS = {
    "comrade": ["guild_intel", "local_politics", "pledge_support", "buy_intel", "pump_for_info"],   # 同會相認 ⊇ friendly + 情報
    "friendly": ["local_politics", "pledge_support", "buy_intel", "pump_for_info"],
    "neutral": ["local_politics", "pump_for_info"],
    "cold": ["pump_for_info"],
    "hostile": [],
}


# --- 陣營歸屬 / 關係 / 立場 --------------------------------------------
def _rel_for_faction(char: Character, fac: str | None) -> str:
    """NPC 帶 faction 覆寫時自算關係(複刻 politics.relationship 內層,供例外 NPC)。"""
    if fac is None:
        return "none"
    if not char.allegiance:
        return "unaligned"
    if fac == char.allegiance:
        return "ally"
    if fac == "neutral":
        return "enemy" if char.allegiance in politics.EXPANSIONIST_CAUSES else "neutral"
    return "enemy"


def npc_relationship(char: Character, gamedata: GameData, npc_id: str) -> str:
    """NPC 相對玩家 allegiance 的關係:npcs.json `faction` 覆寫 ▸ 否則由所在城推導。"""
    npc = gamedata.npcs[npc_id]
    if "faction" in npc:
        return _rel_for_faction(char, npc["faction"])
    return politics.relationship(char, gamedata, npc["location"])


def talk_ctx(state, gamedata: GameData, npc_id: str) -> dict:
    """攀談上下文(供 meets_dialogue / 文字插值):npc_id / relationship / province / faction。"""
    char = state.player
    npc = gamedata.npcs[npc_id]
    loc = npc["location"]
    return {
        "npc_id": npc_id,
        "relationship": npc_relationship(char, gamedata, npc_id),
        "province": gamedata.location(loc)["province"],
        "faction": npc.get("faction") or politics.faction_of(char, gamedata, loc),
    }


def attitude(char: Character, state, gamedata: GameData, npc_id: str, ctx: dict | None = None) -> str:
    """NPC 對玩家的態度分級(驅動問候池 + 話題可見性):
    vampire_seen(看破吸血鬼,優先)> hostile(敵陣營)> cold(好感<25)> friendly(同陣營)> neutral。"""
    from tesrpg.systems import vampirism
    if vampirism.is_shunned(char, state) and not vampirism.is_disguised(char, gamedata):   # 偽裝入城 → 不被看破(R56)
        return "vampire_seen"
    rel = (ctx or talk_ctx(state, gamedata, npc_id))["relationship"]
    if rel == "enemy":
        base = "hostile"
    elif disposition(char, gamedata, npc_id) < 25:
        base = "cold"
    elif rel == "ally":
        base = "friendly"
    else:
        base = "neutral"
    return _guild_attitude(char, gamedata, npc_id, base)


def secret_guild_revealed(char: Character, gamedata: GameData, npc_id: str) -> bool:
    """NPC 的隱藏(犯罪)身分 `secret_guild` 是否已對玩家揭露(R97·零新存檔欄,衍生自既有狀態):
    ① 你是該秘密公會會員(同會自知) ② 高好感信任(disposition≥75) ③ 調查成功(dialogue_done 標記)。"""
    secret = gamedata.npcs[npc_id].get("secret_guild")
    if not secret:
        return False
    if factions.is_member(char, secret):
        return True
    if disposition(char, gamedata, npc_id) >= GUILD_REVEAL_DISPOSITION:
        return True
    return _GUILD_KNOWN in char.dialogue_done.get(npc_id, [])


def _guild_attitude(char: Character, gamedata: GameData, npc_id: str, base: str) -> str:
    """公會身分對態度的覆寫(R96 宿敵敵意 + R97 隱蔽身分/同會相認/臥底掩護):
    - **隱藏身分已揭露** → 以真實身分主導:同(秘密)會 → comrade 相認(植入內線);否則維持 base
      (犯罪公會即使被你看穿仍不公然敵視·知情走情報話題)。
    - 否則以**表面身分 `guild`**(公開公會,或臥底的掩護)處理:同公會 → comrade;公開公會公然敵視
      宿敵(臥底以掩護公會行事 → 會佯裝敵視自己真正的同志,維持掩護)。"""
    npc = gamedata.npcs[npc_id]
    secret = npc.get("secret_guild")
    # 隱藏身分已揭露 + 你正是該秘密公會同會 → comrade 相認(植入內線/同志)。
    if secret and factions.is_member(char, secret) and secret_guild_revealed(char, gamedata, npc_id):
        return "comrade"
    # 其餘(未揭露·或已揭露但你非秘密同會)→ 以**表面 guild**(公開公會,或臥底掩護)處理:
    # 「另外發現他暗中是賊」只疊加情報,不抹除既有掩護公會的同袍/宿敵關係(臥底仍以掩護身分行事)。
    apparent = npc.get("guild")
    if apparent:
        if factions.is_member(char, apparent):
            return "comrade"
        h = factions.faction_hostility(char, gamedata, apparent)
        if h >= 2:
            return "hostile"
        if h == 1 and base in ("friendly", "neutral"):
            return "cold"
    return base


# --- 文字插值 / 問候 ---------------------------------------------------
def _interp(text: str, char: Character, gamedata: GameData, npc_id: str, ctx: dict) -> str:
    npc = gamedata.npcs[npc_id]
    repl = {
        "{greeting}": npc.get("greeting", ""),
        "{rumor}": npc.get("rumor", ""),
        "{npc_name}": npc.get("name", ""),
        "{bloc_label}": politics.current_banner_label(char, gamedata, npc["location"]) or "本地當權者",
        "{cause}": politics.cause_name(char.allegiance) if char.allegiance else "你那面旗",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text


def greeting_for(char: Character, state, gamedata: GameData, npc_id: str, ctx: dict, att: str) -> str:
    """依 attitude 選問候(dialogue.json `greetings` ▸ 程式 fallback ▸ NPC 既有 greeting)。"""
    data = getattr(gamedata, "dialogue", {}) or {}
    pool = data.get("greetings", {}).get(att) or DEFAULT_GREETINGS.get(att)
    if not pool:
        return gamedata.npcs[npc_id].get("greeting", "")
    out = _interp(pool[0], char, gamedata, npc_id, ctx)
    return out or gamedata.npcs[npc_id].get("greeting", "")


# --- 條件評估(對話層;包裝 events.meets + 需 state/ctx 的鍵)----------
def _resolve_req(req: dict | None, ctx: dict) -> dict | None:
    """把 faction_standing_min 裡的 "@npc" 佔位符換成該 NPC 的陣營(供 events.meets)。"""
    if not req or "faction_standing_min" not in req:
        return req
    req = dict(req)
    req["faction_standing_min"] = {(ctx["faction"] if k == "@npc" else k): v
                                   for k, v in req["faction_standing_min"].items()}
    return req


def meets_dialogue(char: Character, state, gamedata: GameData, req: dict | None, ctx: dict) -> bool:
    """對話條件評估:就地判定需 state/ctx 的鍵,其餘委派 events.meets(零新存檔欄,全純讀)。"""
    if not req:
        return True
    if "min_disposition" in req and disposition(char, gamedata, ctx["npc_id"]) < req["min_disposition"]:
        return False
    if "npc_relationship" in req:
        want = req["npc_relationship"]
        want = want if isinstance(want, list) else [want]
        if ctx["relationship"] not in want:
            return False
    if req.get("vampire_shunned"):
        from tesrpg.systems import vampirism
        if not vampirism.is_shunned(char, state):
            return False
    if "bounty_min" in req:
        from tesrpg.systems import crime
        if crime.bounty(char, ctx["province"]) < req["bounty_min"]:
            return False
    if req.get("partisan") and ctx["faction"] not in politics.CAUSES:
        return False     # 該城非黨派(neutral/無領主)→ 無大義可結交
    if "secret_comrade" in req:
        # R98:犯罪同志專屬服務閘 —— 該 NPC 的隱蔽身分須正是指定犯罪公會、你是其會員、且已揭露。
        # comrade 態度也來自公開公會相認(secret_guild 為 None)→ 此閘擋掉公開同志與揭露前洩漏。
        secret = gamedata.npcs[ctx["npc_id"]].get("secret_guild")
        if not (secret == req["secret_comrade"]
                and factions.is_member(char, secret)
                and secret_guild_revealed(char, gamedata, ctx["npc_id"])):
            return False
    base = {k: v for k, v in req.items()
            if k not in ("min_disposition", "npc_relationship", "vampire_shunned",
                         "bounty_min", "partisan", "secret_comrade")}
    return events.meets(char, gamedata, _resolve_req(base, ctx))


# --- 話題選單(淺對話樹:問候 → 話題 → 回應 → 可選子話題)-------------
def _topic_chips(td: dict) -> list[dict]:
    """由 requires 推導門檻提示 chips(供選單顯示)。"""
    req = td.get("requires", {})
    chips = []
    if "min_disposition" in req:
        chips.append({"text": f"需好感 {req['min_disposition']}", "tone": "red"})
    if "is_member" in req:
        chips.append({"text": "同袍", "tone": "gold"})
    if "secret_comrade" in req:
        chips.append({"text": "內線", "tone": "gold"})
    if "skill_min" in req:
        chips.append({"text": "口才 " + str(max(req["skill_min"].values())), "tone": "cyan"})
    if "faction_standing_min" in req:
        chips.append({"text": "需外交立場", "tone": "mag"})
    return chips


def topics_for(char: Character, state, gamedata: GameData, npc_id: str, ctx: dict, att: str) -> list[dict]:
    """該 NPC 當前可見的話題(依 attitude 模板 + role + 手寫覆寫,經 meets_dialogue 過濾)。"""
    if att == "hostile":
        return []                     # 敵陣營拒談:連同 extra/deep 一併收窄(只剩 persuade/bribe 回暖)
    data = getattr(gamedata, "dialogue", {}) or {}
    att_topics = data.get("attitude_topics", DEFAULT_ATTITUDE_TOPICS)
    ids = list(att_topics.get(att, DEFAULT_ATTITUDE_TOPICS.get(att, [])))
    npc = gamedata.npcs[npc_id]
    role = npc.get("role")
    if role:
        ids += data.get("roles", {}).get(role, [])
    override = data.get("npcs", {}).get(npc_id, {})
    if "topics" in override:          # 完全覆寫
        ids = list(override["topics"])
    ids += override.get("extra", [])
    defs = data.get("topics", {})
    deep = override.get("deep", {})
    done = char.dialogue_done.get(npc_id, [])
    out, seen = [], set()
    for tid in ids:
        if tid in seen:
            continue
        seen.add(tid)
        td = deep.get(tid) or defs.get(tid)
        if not td:
            continue
        if td.get("once") and tid in done:     # 一次性話題已表態 → 不再出現
            continue
        if not meets_dialogue(char, state, gamedata, _resolve_req(td.get("requires"), ctx), ctx):
            continue
        out.append({"id": tid, **td})
    return out


def _topic_def(gamedata: GameData, npc_id: str, tid: str) -> dict | None:
    data = getattr(gamedata, "dialogue", {}) or {}
    deep = data.get("npcs", {}).get(npc_id, {}).get("deep", {})
    return deep.get(tid) or data.get("topics", {}).get(tid)


# --- 外交立場軸(faction_standing;互斥真權衡)-------------------------
def adjust_standing(char: Character, cause: str, amount: int, rival_penalty: int = 0) -> None:
    """調整對某大義的外交立場;rival_penalty>0 則連帶降低其餘大義(討好一方得罪對立方)。"""
    fs = char.faction_standing
    fs[cause] = max(-STANDING_CAP, min(STANDING_CAP, fs.get(cause, 0) + amount))
    if rival_penalty:
        for other in politics.CAUSES:
            if other != cause:
                fs[other] = max(-STANDING_CAP, min(STANDING_CAP, fs.get(other, 0) - rival_penalty))


def _apply_topic_effects(state, gamedata: GameData, effects: list, ctx: dict) -> dict:
    """套用話題 effects:攔截 faction_standing(對話專屬),其餘委派 events.apply_effects。"""
    char = state.player
    msgs, passthru = [], []
    for ef in effects or []:
        if ef.get("type") == "faction_standing":
            cause = ctx.get("faction") if ef.get("faction") == "@npc" else ef.get("faction")
            if cause in politics.CAUSES:
                amt = ef.get("amount", 0)
                adjust_standing(char, cause, amt, ef.get("rival_penalty", 0))
                verb = "增進" if amt >= 0 else "惡化"
                msgs.append(f"你與{politics.cause_name(cause)}的關係{verb}了。")
        else:
            passthru.append(ef)
    res = (events.apply_effects(state, gamedata, passthru, state.rng)
           if passthru else {"messages": [], "combat": []})
    return {"messages": msgs + res["messages"], "combat": res["combat"]}


# --- 套話(speechcraft 第二用途)+ 報官 -------------------------------
def pry_chance(char: Character) -> float:
    """套話成功率(唯讀,供 UI 預示)。"""
    return max(0.1, min(0.9, 0.30 + (char.skill("speechcraft") + char.attr("personality") - PRY_DIFFICULTY) * 0.005))


_PUMP_PAID = "__pump_paid__"      # dialogue_done[npc_id] 標記:該 NPC 的功能化秘密已兌現一次(防刷,零新存檔欄)


def _maybe_reveal_secret_guild(char: Character, gamedata: GameData, npc_id: str, rng: RNG) -> str | None:
    """R97 調查揭露:以偵查/口才探查 NPC 的隱藏(犯罪)身分 `secret_guild`。
    一般人(無 secret_guild)→ None(查無所獲);已揭露 → None;否則技能檢定 vs `secret_secrecy`
    (難度·臥底/高階藏得深),成功 → 標 `_GUILD_KNOWN`(永久揭露·零新存檔欄)+ 回報訊息。"""
    secret = gamedata.npcs[npc_id].get("secret_guild")
    if not secret or secret_guild_revealed(char, gamedata, npc_id):
        return None
    secrecy = gamedata.npcs[npc_id].get("secret_secrecy", 50)
    skill = max(char.skill("scout"), char.skill("speechcraft"))
    chance = max(0.05, min(0.85, 0.20 + (skill + char.attr("personality") - secrecy) * 0.005))
    if not rng.chance(chance):
        return None
    char.dialogue_done.setdefault(npc_id, []).append(_GUILD_KNOWN)
    gname = gamedata.factions.get(secret, {}).get("name", secret)
    return f"言談間你察覺端倪 —— 此人竟與{gname}有牽連。"


def _do_pump(state, gamedata: GameData, npc_id: str, topic: dict, ctx: dict, rng: RNG) -> dict:
    """旁敲側擊套話:付 speechcraft practice(體力+時間,非免費刷)。
    成功 → 揭露隱藏情報(topic/NPC `secret`);**功能化秘密**(dict 形)額外撬出可行動情報
    (藏寶 gold/item·線索 start_quest)一次性兌現(`dialogue_done` 標記去重);失敗 → 略降好感。"""
    char = state.player
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    skill_events = progression.use_skill(char, gamedata, "speechcraft", xp)
    if rng.chance(pry_chance(char)):
        # 🔴 秘密存於 dialogue.json 的 npcs 覆寫層(非 npcs.json)。R82 前 _do_pump 誤讀 gamedata.npcs
        # → 既有秘密永遠讀不到、套話只吐預設旁白(等同死功能)。本輪正讀 dialogue 覆寫並功能化。
        dlg_npc = (gamedata.dialogue.get("npcs", {}) or {}).get(npc_id, {})
        raw = topic.get("secret") or dlg_npc.get("secret") or "對方壓低聲音,透了個風聲給你。"
        messages, combat = [], []
        if isinstance(raw, dict):                          # R82 功能化秘密:{text, effects}
            text = _interp(raw.get("text", ""), char, gamedata, npc_id, ctx)
            done = char.dialogue_done.setdefault(npc_id, [])
            if raw.get("effects") and _PUMP_PAID not in done:   # 一次性兌現(再套話只重述、不重發)
                res = _apply_topic_effects(state, gamedata, raw["effects"], ctx)
                messages, combat = res["messages"], res["combat"]
                done.append(_PUMP_PAID)
        else:
            text = _interp(raw, char, gamedata, npc_id, ctx)
        # R97 調查揭露:套話成功 → 順帶以偵查/口才探查隱藏(犯罪)身分(broad:一般人查無所獲、
        # 隱蔽成員/臥底成功才揭露;難度隨 secret_secrecy)。融入套話 → 選項不洩密、無 meta-gaming。
        reveal_msg = _maybe_reveal_secret_guild(char, gamedata, npc_id, rng)
        if reveal_msg:
            messages = messages + [reveal_msg]
        # 套話只給情報/藏寶(+練口才),不推進外交軸(外交立場走顯式的表態話題)
        return {"text": text, "ok": True, "hours": hours, "tired": tired,
                "skill_events": skill_events, "messages": messages, "combat": combat, "subtopics": []}
    _adjust(char, npc_id, -3)
    return {"text": "對方守口如瓶,還似乎有些被你冒犯。", "ok": False, "hours": hours, "tired": tired,
            "skill_events": skill_events, "messages": [], "combat": [], "subtopics": []}


def resolve_topic(state, gamedata: GameData, npc_id: str, topic: dict, ctx: dict, rng: RNG) -> dict:
    """解析一個話題 → 回傳 {text, messages, combat, hours, tired, skill_events, subtopics}。"""
    char = state.player
    if topic.get("action") == "pump":
        return _do_pump(state, gamedata, npc_id, topic, ctx, rng)
    # 關係專屬台詞優先(say_by_rel),否則退回通用 text
    text = (topic.get("say_by_rel") or {}).get(ctx["relationship"]) or topic.get("text") or ""
    text = _interp(text, char, gamedata, npc_id, ctx)
    effects = topic.get("effects", [])
    tid = topic.get("id")
    if topic.get("once"):                          # 一次性話題:已表態則只敘事、不再套 effects
        done = char.dialogue_done.setdefault(npc_id, [])
        if tid in done:
            effects = []
        else:
            done.append(tid)
    res = _apply_topic_effects(state, gamedata, effects, ctx)
    return {"text": text, "messages": res["messages"], "combat": res["combat"],
            "hours": 0, "tired": False, "skill_events": [], "subtopics": topic.get("subtopics", [])}


def report_vampire(char: Character, gamedata: GameData) -> dict:
    """看破吸血鬼報官:該省賞金 +REPORT_BOUNTY、惡名 +1(報官即終止對話,賞金嚇阻 → 不需去重欄)。"""
    from tesrpg.systems import crime
    prov = crime.province_of(char, gamedata)
    crime.add_bounty(char, prov, REPORT_BOUNTY)
    char.infamy += 1
    return {"bounty": REPORT_BOUNTY,
            "message": f"對方驚呼著奪門而出,衛兵已被驚動!(賞金 +{REPORT_BOUNTY}、惡名 +1)"}
