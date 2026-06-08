"""招兵買馬(城戰的金幣/領袖路線):親衛(將領=companions)+ 軍隊(士兵)+ 營地。

階段一:資格門檻 + 營地 + 兩級軍制 + 攻城整合(大軍壓境 + 實戰援軍)。
階段二:**軍餉**(週期金幣沉,付不出 → 逃兵)+ **永久傷亡**(攻城陣亡的親衛/士兵永久折損,
不再戰戰滿血復生)+ **親衛複合來源**(`warlord:true` 將領唯領袖可在營地招募,旅店招不到)。

士兵門檻:你是「領主」(持武士銜 / 已征服城)或「首領」(任一公會掌門),且已建立營地
(野外紮營 / 佔領已清空地城)。士兵在攻城當**實戰援軍**(少數上場)+ 解鎖**大軍壓境**削守軍方略。
加兵種純改 companions.json(`troop:true` 者不在旅店招、僅供點兵;`warlord:true` 者唯營地可招)。
調軍餉/傷亡只動本檔常數。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

SOLDIER_TROOP = "footman"     # 士兵在 run_battle 出場用的兵種模板(companions.json,troop:true)
SOLDIER_COST = 40             # 每名士兵招募金
MAX_SOLDIERS = 30             # 士兵上限
FIELD_CAP = 6                 # 攻城時實際上場的士兵數上限(其餘戰力以大軍壓境體現)
ARMY_SOFTEN_PER = 3           # 大軍壓境:每名士兵削守軍量

# --- 階段二:軍餉(週期金幣沉) ---
WAGE_HOURS = 168              # 每約一週(7 遊戲日)發一次餉
WAGE_PER_SOLDIER = 5          # 每名士兵每週餉銀(招一名士兵 SOLDIER_COST=40,週餉≈12.5%)


def is_guildmaster(char: Character, gamedata: GameData) -> bool:
    for fid, rank in char.factions.items():
        ranks = gamedata.factions.get(fid, {}).get("ranks", [])
        if ranks and rank >= len(ranks) - 1:
            return True
    return False


def is_warlord(char: Character, gamedata: GameData) -> bool:
    """有資格招募軍隊:領主(持武士銜 / 已征服城)、首領(任一公會掌門),
    或**已宣誓擴張性大義**(自立稱雄 own / 神話黎明 daedric,即 `politics.EXPANSIONIST_CAUSES`)。

    擴張派以己之力問鼎天下 —— 招兵買馬正是其立身之本,理當可組軍;否則會陷入「要先征服一城
    才能組軍、卻又要組軍才好攻城」的雞生蛋僵局(擴張派對所有城皆為敵、無武士晉身之階,連 thane
    路都走不通)。**own 與 daedric 同屬此僵局,須一併解**。組軍仍受金幣/軍餉/傷亡牽制 →
    純加性、不破平衡;稅基紅線(held_tax_cities 只認 city_faction)不受影響。"""
    from tesrpg.systems import politics    # 區域 import 避免循環依賴
    return (bool(char.thaneships) or bool(char.city_faction)
            or char.allegiance in politics.EXPANSIONIST_CAUSES or is_guildmaster(char, gamedata))


def has_camp(char: Character) -> bool:
    return bool(char.camp)


def can_make_camp(char: Character, gamedata: GameData, loc_id: str) -> bool:
    """須為領主/首領,且當地可紮營:野外紮營 或 佔領已清空地城。"""
    if not is_warlord(char, gamedata):
        return False
    loc = gamedata.location(loc_id)
    if loc["type"] == "wilderness":
        return True
    return loc["type"] == "dungeon" and loc.get("dungeon") in char.cleared_dungeons


def make_camp(char: Character, loc_id: str) -> None:
    char.camp = loc_id


def recruit_soldiers(char: Character, n: int) -> int:
    """在營地招募 n 名士兵(夾士兵上限與金幣、扣金)。回傳實際招募數。"""
    if not has_camp(char):
        return 0
    n = max(0, min(n, MAX_SOLDIERS - char.soldiers, char.gold // SOLDIER_COST))
    char.gold -= n * SOLDIER_COST
    char.soldiers += n
    return n


def fielded_soldiers(char: Character) -> int:
    """攻城時實際上場的士兵數(其餘戰力以大軍壓境體現)。"""
    return min(char.soldiers, FIELD_CAP)


def army_soften(char: Character) -> int:
    """大軍壓境削守軍量(以士兵總數計)。"""
    return char.soldiers * ARMY_SOFTEN_PER


# --- 軍餉(階段二:週期金幣沉,付不出 → 逃兵)------------------------------
def tick_upkeep(state) -> list[dict]:
    """於 game_loop 每圈頂端結算軍餉(同 vampirism.update / 商店補貨的時間鉤子)。

    無士兵 → 不計餉(並重置週期,下次招募後重新給一週寬限);足額付餉則扣金;
    付不出 → 付得起的份額領餉,其餘**半數**未領餉者憤而離營(至少 1)。可能一次補結多個週期。
    回傳事件清單 [{"kind":"paid"|"desert", ...}] 供呼叫端呈現。
    """
    char = state.player
    now = state.time.absolute_hours()
    # 無兵 → 清週期(下次有兵重新給寬限)。⚠️ 此「歸零重置」既是必要也是安全的,改動前務必看懂:
    #   ‧ 必要:士兵只會經「逃兵 / 攻城傷亡」歸零(皆實質損失);重置讓重建的新軍能拿到應得的一週寬限
    #     (apply_casualties 不自行重置 wage_due_at,靠這裡在下一圈頂端統一收斂)。
    #   ‧ 安全:「遣散後重招洗寬限」不成立 —— 無遣散士兵的入口,且重招每名 SOLDIER_COST(40)遠高於
    #     週餉(WAGE_PER_SOLDIER=5)→ 即使日後加遣散功能,洗寬限也是淨虧。守則:任何遣散士兵的路徑都須付重招成本。
    if char.soldiers <= 0:
        char.wage_due_at = 0
        return []
    if char.wage_due_at == 0:         # 首次有兵(或傷亡歸零後重建)→ 給一週寬限再開始計餉
        char.wage_due_at = now + WAGE_HOURS
        return []
    events: list[dict] = []
    while now >= char.wage_due_at and char.soldiers > 0:
        wage = char.soldiers * WAGE_PER_SOLDIER
        if char.gold >= wage:
            char.gold -= wage
            events.append({"kind": "paid", "wage": wage, "soldiers": char.soldiers})
        else:
            affordable = char.gold // WAGE_PER_SOLDIER          # 付得起幾名
            char.gold -= affordable * WAGE_PER_SOLDIER
            unpaid = char.soldiers - affordable
            deserters = max(1, (unpaid + 1) // 2)               # 未領餉者半數離營(至少 1)
            char.soldiers = max(0, char.soldiers - deserters)
            events.append({"kind": "desert", "deserters": deserters,
                           "soldiers": char.soldiers, "wage": wage})
        char.wage_due_at += WAGE_HOURS
    return events


# --- 永久傷亡(階段二:攻城陣亡的盟友永久折損)----------------------------
def apply_casualties(char: Character, gamedata: GameData, casualties: list[str]) -> dict:
    """把攻城中陣亡的盟友永久從名冊扣除(親衛 → 移出 companions;士兵 → soldiers 遞減)。

    casualties 為陣亡盟友的來源 id 清單(由 run_battle 回報)。回傳 {officers:[名], soldiers:n}。
    """
    lost_soldiers = 0
    lost_officers: list[str] = []
    for cid in casualties:
        if cid == SOLDIER_TROOP:
            lost_soldiers += 1
        elif cid in char.companions:
            char.companions.remove(cid)
            lost_officers.append(gamedata.companions.get(cid, {}).get("name", cid))
    before = char.soldiers
    char.soldiers = max(0, before - lost_soldiers)
    # 回報「實際扣減」而非陣亡 id 計數 —— 兩者在實戰恆等(上陣兵 fielded ≤ soldiers),
    # 但這樣即使被傳入超量名單(如測試)報數也與真實狀態一致,不會誤報。
    return {"officers": lost_officers, "soldiers": before - char.soldiers}


# --- 親衛複合來源(階段二:warlord 專屬將領,唯營地可招)--------------------
def recruitable_officers(char: Character, gamedata: GameData) -> list[str]:
    """可在營地招募的將領 id(companions.json `warlord:true`、尚未在隊伍中)。"""
    return [cid for cid, c in gamedata.companions.items()
            if c.get("warlord") and cid not in char.companions]


def officer_cost(gamedata: GameData, cid: str) -> int:
    return gamedata.companions.get(cid, {}).get("cost", 0)
