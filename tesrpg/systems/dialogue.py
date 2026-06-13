"""NPC 對話與好感 (disposition):說服(口才)、賄賂。

好感影響 NPC 是否願意託付任務。說服會 learn-by-doing 鍛鍊口才。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import events, mastery, politics, progression

BRIBE_COST = 10
TALK_DOWN_MAX = 120          # 可「說服衛兵」的最高賞金(大罪說不過去;對齊武士 ~100 量級)
INTIMIDATE_DIFFICULTY = 40   # 威嚇喝退基準難度(對齊 events.json 既有威嚇 DC40)
INTIMIDATABLE = {"bandit"}   # 可威嚇喝退的弱人形敵(盜匪;不死/魔人/野獸/boss/具名目標皆不可)


def persuade_delta(skill: int) -> int:
    """說服成功的好感增益,隨口才成長(0→+6、50→+12、100→+18)→ 高口才勝過 bribe(+12)且免金幣。"""
    return round(6 + skill * 0.12)


def disposition(char: Character, gamedata: GameData, npc_id: str) -> int:
    base = gamedata.npcs[npc_id]["disposition"]
    return max(0, min(100, base + char.npc_disposition.get(npc_id, 0)))


def _adjust(char: Character, npc_id: str, delta: int) -> None:
    char.npc_disposition[npc_id] = char.npc_disposition.get(npc_id, 0) + delta


def persuade_chance(char: Character, gamedata: GameData, npc_id: str) -> float:
    """說服成功率(唯讀,供 UI 預示;與 persuade 公式單一來源)。折服里程碑 → 1.0。"""
    if mastery.can_guaranteed_persuade(char, gamedata, npc_id):
        return 1.0
    skill = char.skill("speechcraft")
    return max(0.1, min(0.9, 0.35 + (skill + char.attr("personality") - 50) * 0.005))


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
    chance = max(0.1, min(0.9, 0.35 + (skill + char.attr("personality") - 50) * 0.005))
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


# --- 拓展用途①:說服衛兵減免賞金(犯罪/社交;對位武士特權,走技能)----------
def talk_down_chance(char: Character, bounty: int) -> float:
    """以口才說退衛兵的成功率:吃口才+魅力,賞金越高越難。夾 0.05–0.80。"""
    return max(0.05, min(0.80,
               0.10 + (char.skill("speechcraft") + char.attr("personality") - 50) * 0.005 - bounty * 0.002))


def talk_down_guard(char: Character, gamedata: GameData, province: str, rng: RNG) -> dict:
    """以口才說退攔路衛兵(僅小額賞金,呼叫端負責 TALK_DOWN_MAX 門檻)。
    付 speechcraft practice(體力+時間)→ 非免費刷;成功 → 清該省賞金,失敗 → 賞金不動。"""
    from tesrpg.systems import crime
    b = crime.bounty(char, province)
    chance = talk_down_chance(char, b)
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

# 程式內 fallback(dialogue.json 缺漏時仍可運作;正式內容在 data/dialogue.json)
DEFAULT_GREETINGS = {
    "friendly": ["「自己人 —— 有話直說。」"],
    "neutral": ["{greeting}"],
    "cold": ["「……有事快說。」"],
    "hostile": ["「{cause}的人,在這城裡可不受歡迎。」"],
    "vampire_seen": ["「你那雙眼睛……來人啊!這裡有吸血鬼!」"],
}
DEFAULT_ATTITUDE_TOPICS = {
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
    if vampirism.is_shunned(char, state):
        return "vampire_seen"
    rel = (ctx or talk_ctx(state, gamedata, npc_id))["relationship"]
    if rel == "enemy":
        return "hostile"
    if disposition(char, gamedata, npc_id) < 25:
        return "cold"
    if rel == "ally":
        return "friendly"
    return "neutral"


# --- 文字插值 / 問候 ---------------------------------------------------
def _interp(text: str, char: Character, gamedata: GameData, npc_id: str, ctx: dict) -> str:
    npc = gamedata.npcs[npc_id]
    repl = {
        "{greeting}": npc.get("greeting", ""),
        "{rumor}": npc.get("rumor", ""),
        "{npc_name}": npc.get("name", ""),
        "{bloc_label}": politics.city_bloc_label(gamedata, npc["location"]) or "本地當權者",
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
    base = {k: v for k, v in req.items()
            if k not in ("min_disposition", "npc_relationship", "vampire_shunned", "bounty_min", "partisan")}
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


def _do_pump(state, gamedata: GameData, npc_id: str, topic: dict, ctx: dict, rng: RNG) -> dict:
    """旁敲側擊套話:付 speechcraft practice(體力+時間,非免費刷)。
    成功 → 揭露隱藏情報(topic/NPC `secret`)+ 小幅外交立場;失敗 → 略降好感。"""
    char = state.player
    xp, hours, tired = progression.practice_cost(char, gamedata, "speechcraft")
    skill_events = progression.use_skill(char, gamedata, "speechcraft", xp)
    if rng.chance(pry_chance(char)):
        secret = topic.get("secret") or gamedata.npcs[npc_id].get("secret") or "對方壓低聲音,透了個風聲給你。"
        secret = _interp(secret, char, gamedata, npc_id, ctx)
        # 套話只給情報(+練口才),不推進外交軸(外交立場走顯式的表態/結交一次性話題)
        return {"text": secret, "ok": True, "hours": hours, "tired": tired,
                "skill_events": skill_events, "messages": [], "combat": [], "subtopics": []}
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
