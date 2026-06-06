"""公會:入會/晉升門檻、對立排他、階級福利。

扁平化修正(對齊 DESIGN §3.7「晉升需技能門檻 + 完成晉升任務」):
- **入會門檻**:把關技能(`gate_skills` 取最高)須達 `join_skill`,給職業認同。
- **晉升門檻**:每階 `rank_skill_req[rank]` —— 技能不到位就接不到該階晉升任務。
- **對立排他**(`rivals`):不能同時加入勢不兩立的公會。
- **守法**(`lawful`):戰士公會不收/不升有未繳賞金的通緝犯。
- **階級福利**(`perk`):隨階級成長的實質回報(修理折扣/法術折扣/銷贓加成)。

晉升本身仍由 `quests._complete` 在完成晉升任務時觸發。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character


def is_member(char: Character, faction_id: str) -> bool:
    return faction_id in char.factions


def rank_index(char: Character, faction_id: str) -> int:
    return char.factions.get(faction_id, -1)


def rank_name(char: Character, gamedata: GameData, faction_id: str) -> str:
    idx = rank_index(char, faction_id)
    if idx < 0:
        return "非會員"
    ranks = gamedata.factions[faction_id]["ranks"]
    return ranks[min(idx, len(ranks) - 1)]


# --- 技能把關 -----------------------------------------------------------
def gate_level(char: Character, gamedata: GameData, faction_id: str) -> int:
    """把關技能(`gate_skills`)中的最高等級 —— 代表你在這個領域的造詣。"""
    skills = gamedata.factions[faction_id].get("gate_skills", [])
    return max((char.skill(s) for s in skills), default=0)


def gate_skill_names(gamedata: GameData, faction_id: str) -> str:
    skills = gamedata.factions[faction_id].get("gate_skills", [])
    return "、".join(gamedata.skill_name(s) for s in skills)


def rank_skill_req(gamedata: GameData, faction_id: str, rank: int) -> int:
    reqs = gamedata.factions[faction_id].get("rank_skill_req", [])
    if not reqs or rank < 0:
        return 0
    return reqs[min(rank, len(reqs) - 1)]


def _has_unpaid_bounty(char: Character) -> bool:
    return sum(char.bounties.values()) > 0


def joined_rivals(char: Character, gamedata: GameData, faction_id: str) -> list[str]:
    rivals = gamedata.factions[faction_id].get("rivals", [])
    return [r for r in rivals if r in char.factions]


# --- 入會 ---------------------------------------------------------------
def join_block_reason(char: Character, gamedata: GameData, faction_id: str) -> str | None:
    """回傳「不能入會」的原因(繁中);可入會則 None。"""
    f = gamedata.factions[faction_id]
    if is_member(char, faction_id):
        return "你已是會員。"
    # 大事件解鎖:某些組織(如神話黎明)須待 world_events_fired 含指定大事件後才現身/可入會
    unlock_event = f.get("unlock_event")
    if unlock_event and unlock_event not in getattr(char, "world_events_fired", []):
        return "此處空無一人 —— 改變世道的大事件尚未到來,這個組織還隱於陰影之中。"
    rivals = joined_rivals(char, gamedata, faction_id)
    if rivals:
        names = "、".join(gamedata.factions[r]["name"] for r in rivals)
        return f"你身屬{names},與本會勢不兩立,恕不接納。"
    if f.get("lawful") and _has_unpaid_bounty(char):
        return "你身負通緝賞金,先把案底了結再來談入會。"
    need = f.get("join_skill", 0)
    if gate_level(char, gamedata, faction_id) < need:
        return f"入會須 {gate_skill_names(gamedata, faction_id)} 任一達 {need}(你目前 {gate_level(char, gamedata, faction_id)})。"
    return None


def can_join(char: Character, gamedata: GameData, faction_id: str) -> bool:
    return join_block_reason(char, gamedata, faction_id) is None


def join(char: Character, faction_id: str) -> None:
    if faction_id not in char.factions:
        char.factions[faction_id] = 0      # 入會即最低階


# --- 晉升門檻 -----------------------------------------------------------
def meets_rank_skill(char: Character, gamedata: GameData, faction_id: str) -> bool:
    """是否達到「接取當前階級晉升任務」所需的技能門檻。"""
    rank = rank_index(char, faction_id)
    return gate_level(char, gamedata, faction_id) >= rank_skill_req(gamedata, faction_id, rank)


def advance_block_reason(char: Character, gamedata: GameData, faction_id: str) -> str | None:
    """回傳「目前無法晉升」的原因;可接晉升任務則 None。"""
    f = gamedata.factions[faction_id]
    rank = rank_index(char, faction_id)
    if rank >= len(f.get("rank_quests", [])):
        return "你已達公會目前開放的最高階級,暫無新委託(更多晉升內容待後續更新)。"
    if f.get("lawful") and _has_unpaid_bounty(char):
        return "通緝在身,公會暫停你的晉升 —— 先繳清賞金。"
    need = rank_skill_req(gamedata, faction_id, rank)
    if gate_level(char, gamedata, faction_id) < need:
        return (f"晉升下一階須 {gate_skill_names(gamedata, faction_id)} 任一達 {need}"
                f"(你目前 {gate_level(char, gamedata, faction_id)}) —— 多歷練再回來。")
    return None


# --- 階級福利(perk)----------------------------------------------------
def perk_value(char: Character, gamedata: GameData, faction_id: str) -> float:
    """會員在此公會的福利強度(隨階級成長,夾限到 cap);非會員=0。"""
    if not is_member(char, faction_id):
        return 0.0
    perk = gamedata.factions[faction_id].get("perk")
    if not perk:
        return 0.0
    return min(perk["cap"], perk["per_rank"] * rank_index(char, faction_id))


def _best_perk(char: Character, gamedata: GameData, kind: str) -> float:
    """跨所有已入會公會,取指定 perk 類型的最佳值。"""
    best = 0.0
    for fid in char.factions:
        perk = gamedata.factions.get(fid, {}).get("perk")
        if perk and perk["kind"] == kind:
            best = max(best, perk_value(char, gamedata, fid))
    return best


def repair_discount(char: Character, gamedata: GameData) -> float:
    """戰士公會:鐵匠修理費折扣(0..1,1=免費)。"""
    return _best_perk(char, gamedata, "repair_discount")


def spell_discount(char: Character, gamedata: GameData) -> float:
    """法師公會:公會販售法術的折扣(0..1)。"""
    return _best_perk(char, gamedata, "spell_discount")


def sell_bonus(char: Character, gamedata: GameData) -> float:
    """盜賊公會:出售(銷贓)價的加成比例(0..1)。"""
    return _best_perk(char, gamedata, "sell_bonus")


def conjure_boon(char: Character, gamedata: GameData) -> float:
    """神話黎明:達貢之佑 —— 召喚物生命/駐留的強化比例(0..cap)。"""
    return _best_perk(char, gamedata, "conjure_boon")


def restoration_boon(char: Character, gamedata: GameData) -> float:
    """九神騎士團:聖光眷顧 —— 治療法術回復量的強化比例(0..cap)。"""
    return _best_perk(char, gamedata, "restoration_boon")


def perk_desc(char: Character, gamedata: GameData, faction_id: str) -> str | None:
    """給 UI 顯示的福利說明(含目前強度)。"""
    perk = gamedata.factions[faction_id].get("perk")
    if not perk:
        return None
    val = perk_value(char, gamedata, faction_id)
    pct = int(round(val * 100))
    return f"{perk['desc']}(目前 {pct}%)"
