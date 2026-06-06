"""陣營大事件引擎(動態政局,Phase C):開局=Oblivion 當下歸屬,後續由 authored 大事件觸發城邦易幟。

仿 vampirism.update / brotherhood 的狀態機:`update(state, gamedata)` 掛 game_loop 每圈頂端,
讀 `data/world_events.json` 時間軸,對「尚未觸發且 trigger 條件成立」的事件 fire 一次 → 套用 effects
→ 記入 char.world_events_fired → 回傳戰報事件供 ui 廣播。

鐵則:
- **易幟一律寫 `char.world_faction`(非 city_faction)** → 不污染稅基(held_tax_cities 只認 city_faction);
  玩家親手攻下的城(city_faction)在 faction_of 三層中壓在 world_faction 之上 → **自動免疫事件易幟**。
- **決定性**:事件按 `sorted(id)` 順序處理、`chance` 走 state.rng;同 seed/同時間/同里程碑 → 重播一致。
- **觸發=條件首次成立即 fire 一次**(once-fire,非週期);trigger 內各條件 AND 全成立。
- 加事件純改 `world_events.json`(trigger:days_min/requires/milestone/chance;effect:faction_flip/clear_flip/fame/message)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.systems import politics


def _trigger_ok(char, gamedata: GameData, trig: dict, days: int, rng) -> bool:
    """trigger 各條件 AND 全成立才回 True。"""
    if days < trig.get("days_min", 0):
        return False
    if not all(r in char.world_events_fired for r in trig.get("requires", [])):
        return False
    ms = trig.get("milestone", {})
    if char.level < ms.get("level", 0):
        return False
    if char.fame < ms.get("fame", 0):
        return False
    if "allegiance" in ms and char.allegiance != ms["allegiance"]:
        return False
    if len(politics.held_tax_cities(char, gamedata)) < ms.get("held_cities", 0):
        return False
    if not all(loc in char.city_faction for loc in ms.get("held_includes", [])):
        return False
    if not all(d in char.cleared_dungeons for d in ms.get("cleared", [])):
        return False
    if not all(char.kill_counts.get(t, 0) >= n for t, n in ms.get("kills", {}).items()):
        return False
    if not all(char.factions.get(f, -1) >= r for f, r in ms.get("faction", {}).items()):
        return False
    if "chance" in trig and not rng.chance(trig["chance"]):   # 條件成立後的擲骰(MVP 事件皆未用 → 全決定性)
        return False
    return True


def _apply(char, gamedata: GameData, effects: list) -> None:
    for e in effects:
        t = e.get("type")
        if t == "faction_flip":                       # 易幟:寫世界層(玩家持有城被 city_faction 蓋過 → 免疫)
            char.world_faction[e["loc"]] = e["to"]
        elif t == "clear_flip":                       # 撤旗:還原該城至種子立場(如關閉湮滅之門光復)
            char.world_faction.pop(e["loc"], None)
        elif t == "fame":
            char.fame = max(0, char.fame + e.get("amount", 0))
        # message 不在此處理(由 news 統一廣播)


def update(state, gamedata: GameData) -> list[dict]:
    """於 game_loop 每圈頂端結算大事件;回傳 [{"id","news"}] 供 ui 廣播戰報。"""
    char = state.player
    days = max(0, (state.time.absolute_hours() - state.start_time.absolute_hours()) // 24)
    events: list[dict] = []
    changed = True
    while changed:                                     # 定點迴圈:鏈式事件(requires)同圈觸發,不受字母序影響
        changed = False
        for eid in sorted(gamedata.world_events):      # 決定性順序
            if eid in char.world_events_fired:
                continue
            ev = gamedata.world_events[eid]
            if not _trigger_ok(char, gamedata, ev.get("trigger", {}), days, state.rng):
                continue
            char.world_events_fired.append(eid)        # once-fire
            _apply(char, gamedata, ev.get("effects", []))
            events.append({"id": eid, "news": ev.get("news", "")})
            changed = True
    return events
