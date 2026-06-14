"""同伴系統深化:持久 HP / 負傷 benched / 羈絆。

補 §7 既有限制(同伴每戰滿血重生、無持久 HP)。
- **持久 HP**:同伴的當前 HP 存 Character(`companion_hp`,cid→HP),每場戰後回寫。
  倒下(HP≤0)的同伴「負傷」benched —— 須休息/旅店回復才能再上陣;**冒險模式不永久死亡**
  (維持 §7「刻意從簡」的寬容),**攻城仍走 `warband.apply_casualties` 永久折損**(不變)。
- **羈絆**:`companion_bond`(cid→點)隨並肩獲勝累積,升級提升該同伴 max_health(更願為信任的領袖死戰)。
  同伴永遠是盟友,不影響玩家偷襲紅線;`sim_assassin` 零位移。

戰鬥生成(`combat.spawn_companion`)讀 `spawn_hp`(持久值夾上限)+ `bond_hp_bonus`(羈絆耐久)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

# --- 羈絆(並肩獲勝累積)----------------------------------------------------
BOND_PER_VICTORY = 1
BOND_MAX = 60
BOND_TIERS = [5, 15, 30]               # 累積點達門檻 → 升一級(0..3)
BOND_NAMES = ["雇傭", "同袍", "摯友", "生死之交"]
BOND_HP_PER_TIER = 12                   # 每級羈絆 → 該同伴 +max_health(更耐打)

INJURED = 0                             # HP ≤ 此值 = 倒下/負傷(benched,須治療)

MAX_PARTY = 2                           # 同時在隊同伴上限(召集/雇用時夾;此處為單一真實來源)

# 忠誠弧頂點 · 被動型(非戰鬥)加成的加總上限(防多同伴疊加虛高;戰術型走盟友光環不在此)
PASSIVE_CAP = {"barter": 0.15, "travel": 0.15}


def bond_points(char: Character, cid: str) -> int:
    return char.companion_bond.get(cid, 0)


def bond_tier(char: Character, cid: str) -> int:
    return sum(1 for t in BOND_TIERS if bond_points(char, cid) >= t)


def bond_name(char: Character, cid: str) -> str:
    return BOND_NAMES[min(bond_tier(char, cid), len(BOND_NAMES) - 1)]


def bond_hp_bonus(char: Character, cid: str) -> int:
    return bond_tier(char, cid) * BOND_HP_PER_TIER


def max_hp(char: Character, gamedata: GameData, cid: str) -> int:
    """同伴有效生命上限(模板 + 羈絆加成)。"""
    base = gamedata.companions.get(cid, {}).get("max_health", 0)
    return base + bond_hp_bonus(char, cid)


def current_hp(char: Character, gamedata: GameData, cid: str) -> int:
    """目前持久 HP(未記錄=滿血;夾 [0, 有效上限],防毀損存檔的越界值)。"""
    mx = max_hp(char, gamedata, cid)
    return max(0, min(int(char.companion_hp.get(cid, mx)), mx))


def is_downed(char: Character, gamedata: GameData, cid: str) -> bool:
    """是否倒下/負傷(HP≤0,benched 至治療);未記錄=滿血=否。"""
    return char.companion_hp.get(cid, max_hp(char, gamedata, cid)) <= INJURED


def fieldable(char: Character, gamedata: GameData) -> list[str]:
    """可上陣的同伴(排除倒下/負傷者、與冊封坐鎮的總管 —— 坐鎮者已離隊治理、不隨行出戰)。"""
    stationed = set(getattr(char, "stewards", {}).values())
    return [cid for cid in char.companions if cid in gamedata.companions
            and cid not in stationed and not is_downed(char, gamedata, cid)]


def spawn_hp(char: Character, gamedata: GameData, cid: str) -> int:
    """戰鬥生成時的 HP(持久值夾有效上限;未記錄=滿血)。"""
    return current_hp(char, gamedata, cid)


# --- 戰後回寫 / 羈絆累積 ---------------------------------------------------
def record_after_battle(char: Character, gamedata: GameData, roster: list) -> list[str]:
    """戰後回寫同伴持久 HP(0=倒下→benched)。roster=[(cid, Creature)];召喚物/troop/已移除者不持久。
    回傳本戰「剛倒下」的同伴名(供提示)。"""
    from tesrpg.systems import combat
    downed = []
    for cid, cre in roster:
        if cid not in char.companions:          # footman(troop,在 soldiers)/召喚物/已移除 → 不持久
            continue
        was_up = char.companion_hp.get(cid, 1) > INJURED
        char.companion_hp[cid] = max(0, int(cre.health))
        if char.companion_hp[cid] <= INJURED and was_up and not combat.is_alive(cre):
            downed.append(gamedata.companions.get(cid, {}).get("name", cid))
    return downed


def award_victory(char: Character, gamedata: GameData, roster: list) -> list[tuple[str, str]]:
    """並肩獲勝 → 存活同伴 +羈絆。回傳剛升級者 [(同伴名, 新羈絆級名)]。"""
    from tesrpg.systems import combat
    ups = []
    for cid, cre in roster:
        # footman(troop,在 soldiers)/召喚物/已移除者不在 char.companions → 略過(不累積持久羈絆)
        if cid not in char.companions or not combat.is_alive(cre):
            continue
        before = bond_tier(char, cid)
        char.companion_bond[cid] = min(BOND_MAX, bond_points(char, cid) + BOND_PER_VICTORY)
        if bond_tier(char, cid) > before:
            ups.append((gamedata.companions.get(cid, {}).get("name", cid), bond_name(char, cid)))
    return ups


# --- 治療(休息/旅店)-----------------------------------------------------
def heal(char: Character, gamedata: GameData, fraction: float) -> None:
    """休息回復:每個同伴回 max_health × fraction(夾上限);倒下者一併回復(回到正值即可再上陣)。"""
    for cid in char.companions:
        mx = max_hp(char, gamedata, cid)
        cur = max(0, int(char.companion_hp.get(cid, mx)))
        char.companion_hp[cid] = max(0, min(mx, cur + int(round(mx * max(0.0, fraction)))))


def heal_full(char: Character, gamedata: GameData) -> None:
    for cid in char.companions:
        char.companion_hp[cid] = max_hp(char, gamedata, cid)


def forget(char: Character, cid: str) -> None:
    """同伴離隊(解散/陣亡)→ 清其持久狀態,避免殘留污染。"""
    char.companion_hp.pop(cid, None)
    char.companion_bond.pop(cid, None)


# --- 同伴角色化:招募 / 專屬支線 / 忠誠弧頂點(全由既有 completed_quests/bond 推導,零新存檔欄)----
def keeps_state_on_dismiss(gamedata: GameData, cid: str) -> bool:
    """具名同伴(circle 盾袍兄弟 + 招募任務取得者)解散時保留持久 HP/羈絆、可免費再召集 ——
    比照 circle 鐵律(否則『解散→再召集』成免費回血/解負傷洞)。泛用傭兵照舊 forget。"""
    c = gamedata.companions.get(cid, {})
    return bool(c.get("circle") or c.get("recruit_quest"))


def recruited_named(char: Character, gamedata: GameData) -> list[str]:
    """已透過招募任務解鎖、目前不在隊的具名同伴(可在隊伍選單免費再召集)。
    circle 盾袍兄弟另由戰友團聖殿召集 → 不在此列(行為不變)。"""
    out = []
    for cid, c in gamedata.companions.items():
        rq = c.get("recruit_quest")
        if rq and rq in char.completed_quests and cid not in char.companions:
            out.append(cid)
    return out


def summonable(char: Character, gamedata: GameData) -> list[str]:
    """可免費召集歸隊者:招募任務具名同伴 + 領主待命侍從(pending_companions);去重、排除在隊。"""
    out = list(recruited_named(char, gamedata))
    for cid in getattr(char, "pending_companions", []):
        if cid not in char.companions and cid not in out:
            out.append(cid)
    return out


def personal_quest_id(gamedata: GameData, cid: str) -> str | None:
    return gamedata.companions.get(cid, {}).get("personal_quest")


def arc_done(char: Character, gamedata: GameData, cid: str) -> bool:
    """同伴專屬支線已完成 → 忠誠弧達成(頂點解鎖)。由 completed_quests 推導,永久。"""
    qid = personal_quest_id(gamedata, cid)
    return bool(qid) and qid in char.completed_quests


def arc_offerable(char: Character, gamedata: GameData, cid: str) -> bool:
    """專屬支線可在『與同伴交談』提供:有定義、羈絆達門檻、尚未接取/完成。"""
    qid = personal_quest_id(gamedata, cid)
    if not qid or qid in char.quests or qid in char.completed_quests:
        return False
    gate = gamedata.companions.get(cid, {}).get("personal_quest_gate", 1)
    return bond_tier(char, cid) >= gate


def active_capstone(char: Character, gamedata: GameData, cid: str) -> dict | None:
    """該同伴已完成專屬支線 → 其忠誠頂點 dict;否則 None。"""
    if not arc_done(char, gamedata, cid):
        return None
    return gamedata.companions.get(cid, {}).get("capstone")


def passive_capstone_factor(char: Character, gamedata: GameData, kind: str) -> float:
    """在隊且弧完成的同伴中,具該被動 kind 頂點的加總強度(夾 PASSIVE_CAP)。
    被動型頂點(barter/travel)純非戰鬥 → 不碰偷襲/solo boss 紅線。"""
    total = sum(cap.get("magnitude", 0.0)
                for cid in char.companions
                if (cap := active_capstone(char, gamedata, cid)) and cap.get("kind") == kind)
    return min(total, PASSIVE_CAP.get(kind, 0.5))


# --- 一生傳奇:最深羈絆的同伴 + 完成的忠誠弧 ------------------------------
def legacy_label(char: Character, gamedata: GameData) -> str | None:
    best = None
    for cid in char.companions:        # 只認在隊者(forget 已清離隊者 → 不殘留羈絆殘影)
        t = bond_tier(char, cid)
        if best is None or t > best[1]:
            best = (cid, t)
    if not best or best[1] == 0:
        return None
    return f"{bond_name(char, best[0])}·{gamedata.companions.get(best[0], {}).get('name', best[0])}"


def loyalty_arcs(char: Character, gamedata: GameData) -> list[str]:
    """在隊同伴中已完成專屬支線者的 cid。"""
    return [cid for cid in char.companions if arc_done(char, gamedata, cid)]


def loyalty_label(char: Character, gamedata: GameData) -> str | None:
    names = [gamedata.companions.get(cid, {}).get("name", cid)
             for cid in loyalty_arcs(char, gamedata)]
    return "、".join(names) if names else None
