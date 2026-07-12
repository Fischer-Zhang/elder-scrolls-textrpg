"""出生星座的招牌能力(每日一次)。

把 data/birthsigns.json 裡原本只是死資料的 `powers` 接成實際可用的能力:
戰士/法師/竊賊等三大守護星沒有主動能力(只給屬性/法力);其餘星座各有一招。
冷卻以「遊戲日」為單位(同一天只能用一次)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

# power_id -> 定義。contexts:combat=戰鬥中可用、utility=平時可用、passive=被動(不主動觸發)
POWERS = {
    "heal_self":        {"name": "領主再生", "contexts": ["combat", "utility"],
                         "effect": {"heal": 60}, "desc": "回復 60 點生命。"},
    "mara_blessing":    {"name": "瑪拉祝福", "contexts": ["combat", "utility"],
                         "effect": {"heal": 80, "cure": True}, "desc": "回復 80 點生命並解除身上的持續傷害。"},
    "paralyze_touch":   {"name": "戀人之觸", "contexts": ["combat"],
                         "effect": {"paralyze": 3}, "desc": "使敵人麻痺 3 回合,無法行動。"},
    "serpent_curse":    {"name": "蛇之詛咒", "contexts": ["combat"],
                         "effect": {"poison": {"magnitude": 8, "turns": 4}, "heal": 25},
                         "desc": "對敵人下毒(每回合 8 點,4 回合),並汲取 25 點生命。"},
    # 三大守護星(原本只給屬性/法力,零主動能力)各補一招(R61 種族威能同構;冷卻共用 power_last_day):
    "warrior_fury":     {"name": "戰意奔湧", "contexts": ["combat"],
                         "effect": {"self_empower": 0.20, "empower_turns": 3},
                         "desc": "戰意奔湧,攻勢凌厲 3 回合(增傷 20%)。"},
    "magicka_surge":    {"name": "法力湧現", "contexts": ["combat", "utility"],
                         "effect": {"restore_magicka": True},
                         "desc": "法力如泉湧現,瞬間補滿法力。"},
    "ladys_grace":      {"name": "淑女恩典", "contexts": ["combat", "utility"],
                         "effect": {"heal": 70, "restore_fatigue": True, "cure": True},
                         "desc": "重整旗鼓:回復 70 點生命與全部體力,並淨化身上的持續傷害。"},
    "invisibility":     {"name": "陰影遁形", "contexts": ["combat"],
                         "effect": {"escape": True}, "desc": "遁入陰影,必定脫離戰鬥。"},
    "tower_key":        {"name": "塔之鑰", "contexts": ["utility"],
                         "effect": {"unlock_charge": True}, "desc": "下一次撬鎖必定成功。"},
    "spell_absorption": {"name": "巨魔像吸收", "contexts": ["passive"],
                         "effect": {}, "desc": "(被動)有機率將來襲的元素魔法吸收為法力。"},
    # 吸血鬼專屬(轉化後取代出生星座之力):每日一次的汲血擁抱
    "vampiric_drain":   {"name": "汲血擁抱", "contexts": ["combat"],
                         "effect": {"drain": 40}, "desc": "撕咬汲取敵人 40 點生命為己用。"},
    # 狼人專屬(取代出生星座之力):每日一次的獸化變身。R50:加 utility → 平時(野外/城鎮)亦可主動變身。
    "beast_form":       {"name": "獸化變身", "contexts": ["combat", "utility"],
                         "effect": {"transform": True},
                         "desc": "化為嗜血巨狼:利爪撕敵、刀槍難傷,但無法施法、用物或持械。"},
}


def power_id(char: Character, gamedata: GameData) -> str | None:
    if getattr(char, "is_vampire", False):   # 吸血鬼:詛咒之力取代出生星座之力
        return "vampiric_drain"
    if getattr(char, "is_werewolf", False):  # 狼人:獸化變身取代出生星座之力(獸形中此槽關閉,不可重變身)
        return None if getattr(char, "beast_form", False) else "beast_form"
    powers = gamedata.birthsigns[char.birthsign].get("powers", [])
    pid = powers[0] if powers else None
    return pid if pid in POWERS else None


def power_def(pid: str) -> dict:
    return POWERS[pid]


def _today(state) -> int:
    return state.time.absolute_hours() // 24


def available(char: Character, state, gamedata: GameData, context: str | None = None) -> bool:
    pid = power_id(char, gamedata)
    if not pid:
        return False
    if context is not None and context not in POWERS[pid]["contexts"]:
        return False
    if pid == "beast_form":   # 獵者之戒 / 滿月(R50):狼人可隨意變身(繞過每日冷卻)
        from tesrpg.systems import lycanthropy, moons
        if lycanthropy.has_hircine_ring(char, gamedata) or moons.is_full_moon(state):
            return True
    return char.power_last_day.get(pid) != _today(state)


def usable_in(char: Character, state, gamedata: GameData, context: str) -> bool:
    return available(char, state, gamedata, context)


def use(char: Character, state, gamedata: GameData, target=None) -> dict:
    """施展星座能力。回傳 {"messages": [...], "escape": bool}。設置當日冷卻。"""
    pid = power_id(char, gamedata)
    pdef = POWERS[pid]
    eff = pdef["effect"]
    messages: list[str] = []
    escape = False

    if "self_empower" in eff:   # 戰士座戰意:自身增傷 buff(combat._self_empower 讀 → power_bonus,偷襲倍率後相加 → 守紅線;與 R61 種族狂暴同槽相加)
        char.active_effects.append({"kind": "berserk_buff",
                                    "magnitude": eff["self_empower"],
                                    "turns": eff.get("empower_turns", 3)})
        messages.append(f"{pdef['name']} —— 戰意奔湧,攻勢凌厲了起來({eff.get('empower_turns', 3)} 回合)。")
    if "heal" in eff:
        before = char.health
        char.health = min(char.max_health, char.health + eff["heal"])
        messages.append(f"{pdef['name']}回復了 {int(char.health - before)} 點生命。")
    if eff.get("restore_magicka"):   # 法師座法力湧現:補滿法力
        before = char.magicka
        char.magicka = char.max_magicka
        messages.append(f"{pdef['name']}補滿了法力(+{int(char.magicka - before)})。")
    if eff.get("restore_fatigue"):   # 淑女座恩典:回滿體力
        char.fatigue = char.max_fatigue
        messages.append("你體力全復、精神抖擻。")
    if eff.get("cure"):
        removed = [e for e in char.active_effects if e["kind"] == "dot"]
        char.active_effects = [e for e in char.active_effects if e["kind"] != "dot"]
        if removed:
            messages.append("身上的持續傷害被淨化了。")
    if "paralyze" in eff and target is not None:
        # R44:戀人座麻痺走集中 helper → solo BOSS 由「保證 3 回合鎖」改機率減免(閉合反鎖王破口)
        from tesrpg.systems import magic
        if magic.apply_control(target, "paralyze", gamedata, state.rng, turns=eff["paralyze"]) == "applied":
            messages.append(f"{target.name}被{pdef['name']}定在原地({eff['paralyze']} 回合)!")
        else:
            messages.append(f"{target.name}意志如淵,掙脫了{pdef['name']}的禁錮。")
    if "poison" in eff and target is not None:
        p = eff["poison"]
        target.active_effects.append({"kind": "dot", "element": "poison",
                                      "magnitude": p["magnitude"], "turns": p["turns"]})
        messages.append(f"{target.name}中了蛇毒({p['turns']} 回合)。")
    if "drain" in eff and target is not None:
        amount = min(eff["drain"], int(target.health))
        target.health = max(0, target.health - eff["drain"])
        char.health = min(char.max_health, char.health + amount)
        messages.append(f"{pdef['name']}撕咬{target.name},汲取了 {amount} 點生命。")
    if eff.get("escape"):
        escape = True
        messages.append(f"{pdef['name']} —— 你隱入陰影,悄然脫身。")
    if eff.get("unlock_charge"):
        char.tower_key_charge = True
        messages.append(f"{pdef['name']}已蓄勢 —— 下一道鎖將應手而開。")
    if eff.get("transform"):     # 狼人獸化變身:化為獸形(每日一次,冷卻由下方 power_last_day 記)
        from tesrpg.systems import lycanthropy
        res = lycanthropy.transform(char, state, gamedata)
        messages.extend(res.get("messages", []))

    char.power_last_day[pid] = _today(state)
    return {"messages": messages, "escape": escape}


# ── 種族威能(R61):與星座威能槽**不相交**的「第二威能槽」。每日一次,複用 char.power_last_day
#    (種族 pid 與星座 pid 天然不撞 → 零新存檔欄)。`power_id()` 一字不動。
#    戰系種族各一招:獸人/紅衛=自身增傷 buff、木精靈/帝國/諾德=控場(走 magic.apply_control)、
#    暗精靈=召喚靈體;被動族(虎人/亞龍/高精靈/布萊頓)無 racial_power key → racial_power_id 回 None。
RACIAL_POWERS = {
    "orc_berserk":       {"name": "獸人狂暴", "contexts": ["combat"],
                          "effect": {"self_empower": 0.20, "empower_turns": 3, "heal": 40},
                          "desc": "血脈狂怒奔湧:增傷 3 回合,並回復 40 點生命。"},
    "adrenaline_rush":   {"name": "腎上腺爆發", "contexts": ["combat"],
                          "effect": {"self_empower": 0.15, "empower_turns": 3, "restore_fatigue": True},
                          "desc": "腎上腺奔湧:增傷 3 回合,並回滿體力。"},
    "command_beast":     {"name": "林語馭獸", "contexts": ["combat"],
                          "effect": {"control": "fear", "turns": 1, "target_class": "beast"},
                          "desc": "以林間之語震懾一頭野獸,使其驚懼退縮 1 回合。"},
    "imperial_voice":    {"name": "帝皇之聲", "contexts": ["combat"],
                          "effect": {"control": "fear", "turns": 1, "target_class": "humanoid"},
                          "desc": "天生威儀震懾一名人形之敵,使其驚懼退縮 1 回合。"},
    "battle_cry":        {"name": "諾德戰吼", "contexts": ["combat"],
                          "effect": {"control": "fear", "turns": 1, "target_class": "all"},
                          "desc": "撼天戰吼,使全體敵人驚懼退縮 1 回合。"},
    "ancestor_guardian": {"name": "祖靈守護", "contexts": ["combat"],
                          "effect": {"summon": "ancestral_ghost", "turns": 5},
                          "desc": "召喚一縷先祖之靈並肩作戰(5 回合)。"},
}


def racial_power_id(char: Character, gamedata: GameData) -> str | None:
    """種族威能 id(與 power_id 不相交)。被動族無 racial_power → None;獸形中關閉(鏡像 power_id 狼人 guard)。"""
    if getattr(char, "beast_form", False):   # 獸形:化身巨狼,種族威能槽暫閉
        return None
    pid = (getattr(gamedata, "races", {}) or {}).get(getattr(char, "race", ""), {}).get("racial_power")
    return pid if pid in RACIAL_POWERS else None


def racial_def(pid: str) -> dict:
    return RACIAL_POWERS[pid]


def racial_available(char: Character, state, gamedata: GameData, context: str | None = None) -> bool:
    pid = racial_power_id(char, gamedata)
    if not pid:
        return False
    if context is not None and context not in RACIAL_POWERS[pid]["contexts"]:
        return False
    return char.power_last_day.get(pid) != _today(state)


def racial_needs_target(pid: str) -> bool:
    """是否需先選單一敵方目標(單體控場=是;AoE/召喚/自身 buff=否)。"""
    return RACIAL_POWERS[pid]["effect"].get("target_class") in ("beast", "humanoid")


def _control_class_ok(target, gamedata: GameData, target_class) -> bool:
    """敵方類別閘:beast=活體野獸(非 sentient 且非不死/無心智);humanoid=sentient(人形);all/None=不限。
    R140 現實邏輯:對蒸汽傀儡/白骨/石像講森林語馭獸嚇不退 → beast 類排除 undead/mindless。"""
    if target_class in (None, "all"):
        return True
    tpl = (getattr(gamedata, "bestiary", {}) or {}).get(getattr(target, "template_id", ""), {})
    sentient = bool(tpl.get("sentient"))
    if target_class == "humanoid":
        return sentient
    return not sentient and not tpl.get("undead") and not tpl.get("mindless")


def racial_combat_targets(pid: str, enemies: list, gamedata: GameData) -> list:
    """該威能在當前敵群中的有效目標 list(控場單體=合類存活敵;all=全存活;自身/召喚=[])。"""
    eff = RACIAL_POWERS[pid]["effect"]
    if "control" not in eff:
        return []   # 自身 buff / 召喚:不需選目標
    from tesrpg.systems import combat
    tcls = eff.get("target_class")
    living = [e for e in enemies if combat.is_alive(e)]
    if tcls == "all":
        return living
    return [e for e in living if _control_class_ok(e, gamedata, tcls)]


def racial_use(char: Character, state, gamedata: GameData, target=None,
               battle=None, enemies=None) -> dict:
    """施展種族威能。回傳 {"messages": [...]}。設置當日冷卻。"""
    from tesrpg.systems import combat, magic
    pid = racial_power_id(char, gamedata)
    if pid is None:   # 防呆:正常呼叫端皆先過 racial_available;無種族威能時安全 no-op(不崩、不燒冷卻)
        return {"messages": []}
    pdef = RACIAL_POWERS[pid]
    eff = pdef["effect"]
    name = pdef["name"]
    messages: list[str] = []

    if "self_empower" in eff:   # 自身增傷 buff(combat._self_empower 讀 → 加在 power_bonus,偷襲倍率之後相加 → 守紅線)
        char.active_effects.append({"kind": "berserk_buff",
                                    "magnitude": eff["self_empower"],
                                    "turns": eff.get("empower_turns", 3)})
        messages.append(f"{name} —— 你怒意爆發,攻勢凌厲了起來({eff.get('empower_turns', 3)} 回合)。")
    if "heal" in eff:
        before = char.health
        char.health = min(char.max_health, char.health + eff["heal"])
        if char.health > before:
            messages.append(f"傷處迅速癒合,回復了 {int(char.health - before)} 點生命。")
    if eff.get("restore_fatigue"):
        char.fatigue = char.max_fatigue
        messages.append("你體力全復、精神抖擻。")
    if "control" in eff:
        tcls = eff.get("target_class")
        if tcls == "all":
            targets = [e for e in (enemies or []) if combat.is_alive(e)]
        else:
            targets = [target] if (target is not None and combat.is_alive(target)) else []
        affected = 0
        for t in targets:
            if _control_class_ok(t, gamedata, tcls) and \
                    magic.apply_control(t, eff["control"], gamedata, state.rng,
                                        turns=eff.get("turns", 1), source=pid) == "applied":
                affected += 1
        messages.append(f"{name} —— {affected} 名敵人膽寒退縮!" if affected
                        else f"{name},但敵人無動於衷。")
    if "summon" in eff and battle is not None:
        ally = combat.spawn_creature(gamedata, eff["summon"], state.rng)
        ally.summon_turns = eff.get("turns", 5)
        battle.setdefault("allies", []).append(ally)
        messages.append(f"{name} —— {ally.name}自靈界現身,與你並肩而戰({ally.summon_turns} 回合)。")

    char.power_last_day[pid] = _today(state)
    return {"messages": messages}
