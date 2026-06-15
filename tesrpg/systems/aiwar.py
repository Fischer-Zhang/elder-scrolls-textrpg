"""AI 陣營自走戰爭(worldstate 階段五):讓政治地圖在玩家不插手時也會動。

仿 worldstate.update 的狀態機:`update(state, gd)` 掛 game_loop 每圈頂端、**在 worldstate.update 之後、
warband/politics.tick_tax 之前**。每 WAR_HOURS(一週)結算一輪(`while` 補結多週)。imperial/independent
兩陣營互吞中立城、互翻彼此的城,並反攻玩家親手攻下的城(神話黎明=末世密教,非世界大戰陣營)。

鐵則(務必遵守):
- **決定性**:全程 `state.rng` + 一切迭代 `sorted`(同 seed/同時間 → 重播一致)。
- **非玩家城易主只寫 `char.world_faction`**;玩家城(city_faction)走「削 garrison_current → 既有 tick_tax
  revolt 失守浮回」安全路徑,**絕不對玩家城寫 world_faction**(故 test_player_held_city_immune_to_flip 原樣通過)。
- **不改 politics.py 行為、不碰 bestiary 怪數值(R11)**;只複用 politics 的 garrison/faction 函式與常數。
- 雪球防線:每週翻城上限、霸權反撲、佔領折扣、中立緩衝(見常數,由 sim_worldwar.py 校準)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.systems import politics

# --- AI 戰爭平衡常數(由 sim_worldwar.py 校準)-------------------------------
WAR_HOURS = 168                # 結算週期(每約一遊戲週,與稅/軍餉同節律)
MAX_FLIPS_PER_WEEK = 1         # 每週非玩家城易主上限(雪球結構閘)
ATTACK_COEFF = 1.0             # 攻方戰力 = 相鄰同陣營城現存守軍和 × 此係數
DEFENSE_RALLY = 0.5            # 守方相鄰同陣營城的馳援係數(被同盟環抱難攻 → 反雪球前線)
MIN_WIN, MAX_WIN = 0.05, 0.85  # 單場勝率夾限
HEGEMONY_CAP = 0.58            # 某陣營控城佔比 > 此 → 進攻被抑、其城更易被奪(樹大招風);
#                               刻意高於自然均衡(~46-51%)→ 玩家選邊可推到此處才被煞車(有感但不一統)
HEGEMONY_DAMP = 0.4            # 霸權陣營進攻勝率乘數
HEGEMONY_VULN = 2.0           # 攻打霸權陣營城的勝率乘數(過度伸展 → 易被反推;制衡玩家選邊雪球)
OCCUPY_RATIO = 0.5             # 易主後守軍 = base × 此(佔領折扣 → 新城脆弱可反推)
REPEL_LOSS = 12               # 攻城失敗(或本週翻城額滿)時守方仍被削的守軍
GARRISON_REGEN_PER = 6        # 非玩家城每週和平回補(複用 politics 同名量級;< 攻防消耗 → 不無限長)
NEUTRAL_FLOOR = 4             # 全圖中立城 ≤ 此 → 禁止再吞中立(永久觀望緩衝帶)
NEUTRAL_DEFENSE_MULT = 1.4    # 中立城防禦加成(難攻但非不可攻)
RAID_ATTRITION = 18          # 反攻:每週削玩家城守軍(配 tick_tax 的 UNREST_DECAY → 數週才失守)
ALLEGIANCE_BOOST = 1.4       # 你支持的大義進攻勝率乘數(選邊有感)
ALLEGIANCE_DEFEND = 0.65     # 你支持的大義城被攻時的勝率乘數(更難失守 → 助其擴張)
WAR_SWAY = 0.3               # faction_standing 對戰爭天平的影響幅度([-100,100] → ±此)
AGGRESSOR_ORDER = ["imperial", "independent"]   # 固定處理序(決定性);王座之爭兩陣營
# 神話黎明=末世密教,非世界大戰陣營:危機只由湮滅之門地城 + 主線弧 + 新聞呈現,城池不易幟 daedric。

_ADJ_CACHE: dict | None = None


def _adjacent_cities(gd: GameData) -> dict:
    """城↔城相鄰表:BFS over world.json links,穿越荒野/地城節點直到撞到另一座有領主的城。
    結果快取(資料唯讀);無相鄰則 fallback 同省其他城。"""
    global _ADJ_CACHE
    if _ADJ_CACHE is not None:
        return _ADJ_CACHE
    locs = gd.world["locations"]
    cities = set(gd.rulers)
    out: dict[str, set] = {}
    for start in cities:
        seen = {start}
        frontier = [start]
        found: set = set()
        while frontier:
            n = frontier.pop()
            for m in locs.get(n, {}).get("links", {}):
                if m in seen:
                    continue
                seen.add(m)
                if m in cities:
                    found.add(m)            # 撞到城 → 相鄰(不再往該城後方擴展)
                else:
                    frontier.append(m)      # 荒野/地城 → 繼續穿越
        if not found:                       # fallback:同省其他城
            prov = locs[start]["province"]
            found = {c for c in cities if c != start and locs[c]["province"] == prov}
        out[start] = found
    _ADJ_CACHE = out
    return out


def _controller_map(char, gd: GameData) -> dict:
    """每座城當前控制者:玩家親手攻下 → None(走反攻路徑);否則 faction_of(world_faction/種子)。"""
    out = {}
    for loc in gd.rulers:
        out[loc] = None if loc in char.city_faction else politics.faction_of(char, gd, loc)
    return out


def _share(cmap: dict, faction: str) -> float:
    total = len(cmap) or 1
    return sum(1 for f in cmap.values() if f == faction) / total


def _aggressors(char, cmap: dict) -> list[str]:
    """本輪可發動進攻的陣營(控有 ≥1 城)。固定序回傳(決定性)。"""
    return [f for f in AGGRESSOR_ORDER if any(c == f for c in cmap.values())]


def _diplomacy_mod(char, faction: str, dst_owner: str | None) -> float:
    """玩家外交傾斜戰爭天平(決定性):你支持的大義進攻 +ALLEGIANCE_BOOST、其城被攻 ×ALLEGIANCE_DEFEND(更難失守);
    faction_standing 對攻方連續加權(討好的陣營更能打)。"""
    mod = 1.0
    if char.allegiance:
        if faction == char.allegiance:
            mod *= ALLEGIANCE_BOOST                       # 你支持的陣營攻得更兇
        if dst_owner == char.allegiance:
            mod *= ALLEGIANCE_DEFEND                      # 你支持的陣營守得更穩(它的城更難被攻下)
    standing = getattr(char, "faction_standing", {}).get(faction, 0)
    mod *= max(0.1, 1.0 + (standing / 100.0) * WAR_SWAY)
    return mod


def _attack_power(char, gd: GameData, faction: str, dst: str, cmap: dict) -> int:
    adj = _adjacent_cities(gd)[dst]
    return round(sum(politics.garrison_of(char, gd, c) for c in adj if cmap.get(c) == faction) * ATTACK_COEFF)


def _defense_power(char, gd: GameData, dst: str, cmap: dict) -> int:
    """守方戰力 = 該城守軍 + 同陣營相鄰城馳援(被同盟環抱的城難攻 → 天然前線、反雪球)。"""
    owner = cmap.get(dst)
    adj = _adjacent_cities(gd)[dst]
    rally = sum(politics.garrison_of(char, gd, c) for c in adj if cmap.get(c) == owner) if owner else 0
    return politics.garrison_of(char, gd, dst) + round(rally * DEFENSE_RALLY)


def _win_chance(char, gd: GameData, faction: str, dst: str, cmap: dict, neutral_count: int) -> float:
    atk = _attack_power(char, gd, faction, dst, cmap)
    if atk <= 0:
        return 0.0
    defn = max(1, _defense_power(char, gd, dst, cmap))
    p = atk / (atk + defn)
    if cmap.get(dst) == "neutral":
        p /= NEUTRAL_DEFENSE_MULT
    p *= _diplomacy_mod(char, faction, cmap.get(dst))      # 外交天平先套
    # 霸權煞車「最後」套用 → 蓋過玩家選邊,防止支持的陣營雪球一統:
    if _share(cmap, faction) > HEGEMONY_CAP:
        p *= HEGEMONY_DAMP                       # 樹大招風:霸權陣營難再擴
    dst_owner = cmap.get(dst)
    if dst_owner and dst_owner != "neutral" and _share(cmap, dst_owner) > HEGEMONY_CAP:
        p *= HEGEMONY_VULN                       # 霸權帝國過度伸展 → 其城更易被奪(制衡 ALLEGIANCE_DEFEND)
    return max(MIN_WIN, min(MAX_WIN, p))


def _best_target(char, gd: GameData, faction: str, cmap: dict, neutral_count: int):
    """該陣營本週最佳進攻目標(相鄰、非己、非玩家城、過中立緩衝閘);回 (dst, p) 或 (None, 0)。"""
    cand = set()
    for c in sorted(cmap):
        if cmap[c] != faction:
            continue
        for d in _adjacent_cities(gd)[c]:
            if cmap.get(d) == faction or d in char.city_faction:
                continue
            if cmap.get(d) == "neutral" and neutral_count <= NEUTRAL_FLOOR:
                continue                         # 中立緩衝:不再吞中立
            cand.add(d)
    best, best_p = None, 0.0
    for d in sorted(cand):                        # 決定性:同 p 取字典序在前
        p = _win_chance(char, gd, faction, d, cmap, neutral_count)
        if p > best_p:
            best, best_p = d, p
    return best, best_p


def _flip(char, gd: GameData, loc: str, to: str) -> None:
    char.world_faction[loc] = to                  # 只寫世界層(玩家城三層免疫)
    char.garrison_current[loc] = round(politics.base_garrison(gd, loc) * OCCUPY_RATIO)


def _flip_news(gd: GameData, loc: str, to: str, frm: str | None) -> str:
    cname = gd.location(loc)["name"]
    return (f"{politics.cause_name(to)}揮師{cname},"
            f"{politics.stance_label(frm)}旗號崩落 —— {cname}就此易主。")


def _raider_of(char, gd: GameData, ploc: str, cmap: dict) -> str | None:
    """圍攻某玩家城的敵對陣營(相鄰、黨派、非玩家大義);取字典序在前者。無則 None。"""
    adj = _adjacent_cities(gd).get(ploc)          # 防呆:非 ruler 城(理論上 conquer 只給敵城)→ 無威脅
    if not adj:
        return None
    enemies = sorted({cmap[c] for c in adj
                      if cmap.get(c) and cmap[c] != "neutral" and cmap[c] != char.allegiance})
    return enemies[0] if enemies else None


def _resolve_week(state, gd: GameData) -> list[dict]:
    char = state.player
    events: list[dict] = []
    cmap = _controller_map(char, gd)
    # ① 和平回補(只動已被削過的非玩家城,夾 base)→ 給世界平衡點,免守軍單向歸零
    for loc in sorted(char.garrison_current):
        if loc in char.city_faction or cmap.get(loc) is None:
            continue
        base = politics.base_garrison(gd, loc)
        if char.garrison_current[loc] < base:
            char.garrison_current[loc] = min(base, char.garrison_current[loc] + GARRISON_REGEN_PER)
    # ② AI 互攻(每陣營一次最佳進攻;全圖每週翻城 ≤ MAX_FLIPS_PER_WEEK)
    neutral_count = sum(1 for f in cmap.values() if f == "neutral")
    flips_left = MAX_FLIPS_PER_WEEK
    for faction in _aggressors(char, cmap):
        dst, p = _best_target(char, gd, faction, cmap, neutral_count)
        if dst is None:
            continue
        defender = cmap[dst]
        if state.rng.chance(p):
            if flips_left > 0:
                _flip(char, gd, dst, faction)
                cmap[dst] = faction
                flips_left -= 1
                if defender == "neutral":
                    neutral_count -= 1
                events.append({"kind": "flip", "loc": dst, "to": faction, "frm": defender,
                               "news": _flip_news(gd, dst, faction, defender)})
            else:
                politics.deplete_garrison(char, gd, dst, REPEL_LOSS)   # 額滿 → 只削不翻
        else:
            politics.deplete_garrison(char, gd, dst, REPEL_LOSS)
    # ③ 反攻玩家城:削守軍 + 預警(真正失守由本圈稍後的 tick_tax revolt 收斂)
    for stale in [c for c in sorted(char.city_threat) if c not in char.city_faction]:
        char.city_threat.pop(stale, None)         # 清掉已失守/已易主城的殘留威脅(防存檔膨脹)
    for ploc in sorted(char.city_faction):
        if char.city_faction[ploc] != char.allegiance:
            continue
        faction = _raider_of(char, gd, ploc, cmap)
        if faction is None:
            char.city_threat.pop(ploc, None)
            continue
        politics.deplete_garrison(char, gd, ploc, RAID_ATTRITION)
        char.city_threat[ploc] = faction
        events.append({"kind": "raid", "loc": ploc, "by": faction,
                       "garrison": politics.garrison_of(char, gd, ploc)})
    return events


def ensure_war_fields(char, time) -> None:
    """存檔相容:補欄 + 把 war_tick_at==0 設為下個整週(仿 skooma/lycanthropy ensure)。"""
    if not hasattr(char, "war_tick_at"):
        return
    if char.war_tick_at == 0:
        char.war_tick_at = time.absolute_hours() + WAR_HOURS


def update(state, gd: GameData) -> list[dict]:
    """game_loop 每圈頂端結算 AI 戰爭;回傳 [{kind:flip/raid, ...}] 供 ui 廣播。"""
    char = state.player
    now = state.time.absolute_hours()
    # 獨立戰爭是湮滅危機平息後的第二幕(梅魯尼斯·達貢被擊退、賽普汀血脈斷絕 → 帝國崩解、群雄並起)。
    # 危機未了 → 內戰按兵不動,並讓開戰時鐘隨危機結束才起算(避免危機平息瞬間補結大量積週)。
    if "oblivion_crisis_ended" not in getattr(char, "world_events_fired", []):
        char.war_tick_at = now + WAR_HOURS
        return []
    if char.war_tick_at == 0:                      # 首次:給一週寬限再開戰
        char.war_tick_at = now + WAR_HOURS
        return []
    events: list[dict] = []
    while now >= char.war_tick_at:                 # 補結跨越的多週
        events += _resolve_week(state, gd)
        char.war_tick_at += WAR_HOURS
    return events
