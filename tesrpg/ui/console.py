"""rich 終端渲染與輸入。

把所有 print / prompt 收斂在這層,規則邏輯不直接碰 IO。
"""

from __future__ import annotations

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.state import GameState
from tesrpg.systems import achievements, mastery

console = Console()

# --- Web 後端接點(單人/本機;終端模式 _web=None 時完全惰性)----------------
# launcher 呼叫 use_web_backend() 後:`console` 換成錄製用 Console,5 個輸入原語
# 改走 _web_prompt()(沖出累積畫面 HTML + 輸入規格 → backend,阻塞等回覆)。
# 渲染函式一律不動(照常 console.print → 錄進緩衝)。
_web = None
_hud_state = None       # web:常駐 HUD 的資料來源(同一 state 物件就地變動 → 即時值)
_hud_gamedata = None    # web HUD 顯示隊伍同伴所需(同伴 HP 由 party 系統算,需 gamedata)
_hud_allies = None      # web HUD:當前情境召喚物清單(地城預召喚;非戰鬥時 None)


def _party_status(char, gamedata) -> list:
    """當前隊伍同伴狀態(名稱 + HP + 負傷),供持久狀態條。無 gamedata → 空。"""
    if gamedata is None:
        return []
    from tesrpg.systems import party
    out = []
    for cid in getattr(char, "companions", []) or []:
        if cid not in gamedata.companions:
            continue
        out.append({"name": gamedata.companions[cid].get("name", cid),
                    "hp": [party.current_hp(char, gamedata, cid), party.max_hp(char, gamedata, cid)],
                    "downed": party.is_downed(char, gamedata, cid)})
    return out


def _allies_status(allies) -> list:
    """當前召喚物狀態(名稱 + HP + 剩餘回合),供持久狀態條。"""
    return [{"name": a.name, "hp": [max(0, int(a.health)), int(a.max_health)],
             "turns": getattr(a, "summon_turns", None)}
            for a in (allies or [])
            if a.health > 0 and (getattr(a, "summon_turns", None) is None or a.summon_turns > 0)]


def use_web_backend(backend, recording_console) -> None:
    global console, _web
    console = recording_console
    _web = backend


def _plain(markup: str) -> str:
    try:
        return Text.from_markup(markup).plain
    except Exception:
        return markup


def _web_prompt(spec: dict):
    """沖出殘餘畫面 HTML(未轉換面板的裸 <span> 片段)+ 輸入規格,阻塞等回覆。"""
    html = console.export_html(inline_styles=True, code_format="{code}", clear=True)
    return _web.prompt(html, spec, _hud_view())


def _hud_view():
    """常駐 HUD 的即時值(跨所有子畫面顯示 HP/MP/體力/金幣/時間)。無遊戲進行中→None。"""
    if _hud_state is None:
        return None
    c = _hud_state.player
    v = {"name": c.name, "level": c.level, "time": _hud_state.time.label(),
         "hp": [int(c.health), int(c.max_health)],
         "mp": [int(c.magicka), int(c.max_magicka)],
         "fp": [int(c.fatigue), int(c.max_fatigue)],
         "gold": c.gold, "bounty": sum(c.bounties.values()),
         "can_level": c.can_level_up(), "vampire": None,
         "party": _party_status(c, _hud_gamedata), "allies": _allies_status(_hud_allies)}
    if getattr(c, "is_vampire", False):
        from tesrpg.systems import vampirism
        v["vampire"] = vampirism.STAGE_NAMES[min(3, max(0, c.vampire_stage))]
    return v


def clear_hud() -> None:
    """一局結束、回到主選單時清掉常駐 HUD,使下一局/重開的主選單不殘留前一角色的
    血條/金幣(web;主選單無進行中角色 → HUD 應隱藏)。終端模式無副作用。"""
    global _hud_state, _hud_gamedata, _hud_allies
    _hud_state = None
    _hud_gamedata = None
    _hud_allies = None


def _emit_view(name: str, data) -> None:
    """web 模式:把一個面板渲成原生 view block(先沖出未轉換面板的殘餘 HTML 以保序)。"""
    html = console.export_html(inline_styles=True, code_format="{code}", clear=True)
    _web.add_block(html, name, data)


_fmt_console = None


def _markup_html(markup: str) -> str:
    """把一行 rich 標記渲成彩色 HTML span(供 log/flavor 行原生顯示;非等寬框線)。"""
    global _fmt_console
    if _fmt_console is None:
        import io
        import os
        _fmt_console = Console(record=True, file=open(os.devnull, "w"), width=400,
                               force_terminal=True, color_system="truecolor")
    _fmt_console.print(Text.from_markup(markup))
    return _fmt_console.export_html(inline_styles=True, code_format="{code}", clear=True).strip()


def _emit_log(markup: str) -> None:
    """web 模式:一行 log/flavor → log block(無框彩色文字行)。"""
    pending = console.export_html(inline_styles=True, code_format="{code}", clear=True)
    _web.add_log(pending, _markup_html(markup))


# 通用原生面板列(供角色卡 sheet_* 子檢視)
def _kv(k, v) -> dict:
    return {"t": "kv", "k": str(k), "v": str(v)}


def _hd(s) -> dict:
    return {"t": "head", "s": str(s)}


def _ln(s, c=None) -> dict:
    return {"t": "line", "s": str(s), "c": c}


def _emit_panel(title: str, rows: list) -> None:
    _emit_view("panel", {"title": title, "rows": rows})


# --- web view-models(原生 HTML 渲染用;與終端渲染函式同源資料,客戶端畫成元件)-----
def _status_view(state: GameState) -> dict:
    c = state.player
    v = {"name": c.name, "level": c.level, "time": state.time.label(),
         "hp": [int(c.health), int(c.max_health)],
         "mp": [int(c.magicka), int(c.max_magicka)],
         "fp": [int(c.fatigue), int(c.max_fatigue)],
         "fame": c.fame, "bounty": sum(c.bounties.values()),
         "can_level": c.can_level_up(), "vampire": None, "infected": False}
    if getattr(c, "is_vampire", False):
        from tesrpg.systems import vampirism
        v["vampire"] = vampirism.STAGE_NAMES[min(3, max(0, c.vampire_stage))]
    elif getattr(c, "vampire_infected_day", -1) >= 0:
        v["infected"] = True
    return v


def _location_view(char: Character, gamedata: GameData, brief: bool = False) -> dict:
    from tesrpg.systems import landmarks, politics
    loc = gamedata.location(char.location_id)
    v = {"name": loc["name"], "province": loc["province"],
         "type": LOC_TYPE_NAME.get(loc["type"], loc["type"]), "danger": loc.get("danger", 0),
         "desc": loc["desc"], "landmark": None, "ruler": None,
         "faction": None, "bloc": None, "exits": [], "brief": brief}
    lm = gamedata.landmark_at(char.location_id)
    if lm and landmarks.is_discovered(char, char.location_id):
        v["landmark"] = {"name": lm["name"], "revisit": lm.get("revisit")}
    ruler = gamedata.ruler_at(char.location_id)
    if ruler:
        v["ruler"] = {"title": ruler["title"], "name": ruler["name"]}
        v["faction"] = politics.stance_label(politics.faction_of(char, gamedata, char.location_id))
        v["bloc"] = ruler.get("bloc_label")
    for d, h in loc.get("links", {}).items():
        v["exits"].append({"name": gamedata.location(d)["name"], "hours": h, "key": "go:" + d})
    return v


def _sheet_view(char: Character, gamedata: GameData) -> dict:
    from tesrpg.systems import factions
    from tesrpg.systems import inventory as _inv
    cls = "自訂" if char.class_id == "custom" else gamedata.classes[char.class_id]["name"]
    return {
        "name": char.name, "race": gamedata.races[char.race]["name"],
        "sex": "男" if char.sex == "male" else "女",
        "sign": gamedata.birthsigns[char.birthsign]["name"], "cls": cls,
        "spec": formulas.SPEC_NAMES.get(char.specialization, char.specialization),
        "level": char.level,
        "level_xp": [int(char.level_xp), int(formulas.levelup_xp_threshold(char.level))],
        "hp": [int(char.health), int(char.max_health)],
        "mp": [int(char.magicka), int(char.max_magicka)],
        "fp": [int(char.fatigue), int(char.max_fatigue)],
        "encumbrance": formulas.max_encumbrance(char.attr("strength")),
        "gold": char.gold, "weapon": _plain(weapon_line(char, gamedata)),
        "armor": _inv.worn_armor_rating(char, gamedata),
        "resist": _resist_summary(char, gamedata),
        "fame": char.fame, "infamy": char.infamy, "bounty": sum(char.bounties.values()),
        "attrs": [{"name": formulas.ATTRIBUTE_NAMES[k], "value": char.attr(k),
                   "favored": k in char.favored_attributes} for k in formulas.ATTRIBUTES],
        "skills": {s: [{"name": gamedata.skill_name(sid), "level": char.skill(sid),
                        "major": char.is_major_skill(sid)} for sid in gamedata.skills_by_spec(s)]
                   for s in ("combat", "magic", "stealth")},
        "spec_names": {s: formulas.SPEC_NAMES[s] for s in ("combat", "magic", "stealth")},
        "masteries": [{"name": e["name"], "skill": gamedata.skill_name(e["skill"]),
                       "threshold": e["threshold"], "desc": e["desc"]}
                      for e in mastery.unlocked(char, gamedata)],
        "guilds": [f"{gamedata.factions[f]['name']}「{factions.rank_name(char, gamedata, f)}」"
                   for f in char.factions if f in gamedata.factions],
        "effects": [_effect_label(e) for e in char.active_effects],
        "origin": gamedata.origins.get(char.origin, {}).get("name", ""),
        "origin_blurb": gamedata.origins.get(char.origin, {}).get("blurb", ""),
        "intro_quest": _active_origin_quest(char, gamedata),
    }


def _status_tags_list(entity) -> list:
    out = []
    for e in entity.active_effects:
        if e.get("turns", 0) <= 0:
            continue
        kind = e["kind"]
        good = True if kind in _BUFF_KINDS else (False if kind in _STATUS_TAG else None)
        out.append({"s": f"{_STATUS_TAG.get(kind, kind)}{e['turns']}", "good": good})
    return out


def _combatant(ent, idx=None, down=False) -> dict:
    return {"name": ent.name, "idx": idx, "down": down,
            "hp": [max(0, int(ent.health)), int(ent.max_health)],
            "mp": [max(0, int(getattr(ent, "magicka", 0))), int(getattr(ent, "max_magicka", 0))],
            "fp": [int(getattr(ent, "fatigue", 0)), int(getattr(ent, "max_fatigue", 0))],
            "tags": [] if down else _status_tags_list(ent)}


def _combat_view(player: Character, allies: list, enemies: list) -> dict:
    foes, n = [], 0
    for e in enemies:
        if e.health > 0:
            n += 1
            # key=0-based 存活索引,對齊 main._choose_enemy_target 的目標選單鍵 → 卡片可點選目標
            foes.append({**_combatant(e, idx=n), "key": str(n - 1)})
        else:
            foes.append(_combatant(e, down=True))
    return {"me": _combatant(player), "has_fp": True,
            "allies": [_combatant(a) for a in allies if a.health > 0], "enemies": foes}


def _legacy_view(s: dict) -> dict:
    origins = []   # 身世:出身/詛咒/血業/功業/精通
    for key in ("origin", "condition", "lycanthropy", "addiction", "dark_deeds", "comrade", "loyalty", "dominion"):
        label = {"origin": "出身", "condition": "詛咒", "lycanthropy": "獸血", "addiction": "癮疾",
                 "dark_deeds": "血業", "comrade": "羈絆", "loyalty": "忠誠", "dominion": "功業"}[key]
        if s.get(key):
            origins.append([label, str(s[key])])
    if s.get("masteries"):
        origins.append(["精通", "、".join(s["masteries"])])

    life = [["等級", str(s["level"])],
            ["在世", f"{s['years']} 年 {s['days']} 天"],
            ["足跡", f"踏遍 {s['places_visited']}/{s['total_locations']} 處地點"]]
    if s.get("total_landmarks"):
        life.append(["奇景", f"尋得 {s.get('landmarks_found', 0)}/{s['total_landmarks']} 處具名地標"])

    deeds = [["地城", f"肅清 {s['dungeons_cleared']} 座"],
             ["任務", f"完成 {s['quests_completed']} 件"],
             ["斬獲", f"擊殺 {s['total_kills']} 敵"]]
    if s["factions"]:
        deeds.append(["公會", "、".join(f"{n}「{r}」" for n, r in s["factions"])])

    fame = [["聲望", f"{s['fame']}" + (f"  惡名 {s['infamy']}" if s["infamy"] else "")],
            ["財富", f"{s['gold']} 金" + (f"  通緝 {s['bounty']}" if s["bounty"] else "")]]
    if s.get("seed") is not None:
        fame.append(["種子", str(s["seed"])])

    achv = []
    if s.get("achievements"):
        achv = ([["達成", f"{len(s['achievements'])}/{s.get('achievements_total', len(s['achievements']))}"]]
                + [["✦", name] for name in s["achievements"]])
    sections = [{"header": h, "items": it} for h, it in
                (("身世", origins), ("生涯", life), ("功績", deeds),
                 ("名望", fame), ("成就", achv)) if it]
    return {"head": "⚰ 傳 奇 落 幕" if s["ending"] == "death" else "🌅 功 成 身 退",
            "name": s["name"], "sub": f"{s['race']} · {s['sex']} · {s['birthsign']} · {s['class']}",
            "playstyle": s["playstyle"], "sections": sections,
            "top_skills": "  ".join(f"{n} {lv}" for n, lv in s["top_skills"]),
            "score": s["score"], "title": s["title"]}


def _inventory_view(char: Character, gamedata: GameData) -> dict:
    from tesrpg.systems import inventory as inv
    order = {"weapon": 0, "armor": 1, "potion": 2, "misc": 3}
    stacks = sorted(char.inventory, key=lambda s: order.get(gamedata.item(s["id"])["kind"], 9))
    items = [{"key": s["id"], "label": _plain(item_label(gamedata, char, s["id"], s["qty"])),
              "kind": gamedata.item(s["id"])["kind"]} for s in stacks]
    w = inv.total_weight(char, gamedata)
    mx = inv.max_weight(char, gamedata)
    return {"items": items, "weight": float(w), "max": mx, "over": w > mx, "gold": char.gold}


def _shop_view(char: Character, gamedata: GameData, loc_id: str, qids: list) -> dict:
    from tesrpg.systems import world
    items = []
    for iid in qids:
        d = gamedata.item(iid)
        price = world.buy_price(char, gamedata, iid)
        items.append({"key": iid,
                      "label": f"{d['name']} ×{world.stock_qty(char, loc_id, iid)} — {price} 金",
                      "kind": d["kind"], "afford": char.gold >= price})
    return {"items": items, "gold": char.gold}


def shop_panel(char: Character, gamedata: GameData, loc_id: str, qids: list) -> None:
    """web:商店買貨可點面板(列 key=item id,對齊買單 → wireActionableRows 接管);終端不發。"""
    if _web is not None:
        _emit_view("shop", _shop_view(char, gamedata, loc_id, qids))


def _guild_view(char: Character, gamedata: GameData, faction_id: str) -> dict:
    from tesrpg.systems import factions
    f = gamedata.factions[faction_id]
    v = {"name": f["name"], "blurb": f["blurb"], "member": factions.is_member(char, faction_id)}
    if v["member"]:
        reason = factions.advance_block_reason(char, gamedata, faction_id)
        v.update({"rank": factions.rank_name(char, gamedata, faction_id),
                  "perk": factions.perk_desc(char, gamedata, faction_id) or None,
                  "advance": reason or "已可接取下一階晉升任務", "advance_blocked": bool(reason)})
    else:
        reason = factions.join_block_reason(char, gamedata, faction_id)
        v.update({"join_req": f"{factions.gate_skill_names(gamedata, faction_id)} 任一達 "
                              f"{f.get('join_skill', 0)}(你目前 {factions.gate_level(char, gamedata, faction_id)})",
                  "rivals": "、".join(gamedata.factions[r]["name"] for r in f["rivals"]) if f.get("rivals") else None,
                  "join_status": reason or "你已符合入會資格,可申請加入。", "join_blocked": bool(reason)})
    return v


_QUEST_GROUPS = [("origin", "🧭 起手任務"), ("guild", "⚜ 公會"), ("other", "📜 委託")]


def _quest_group(q: dict) -> str:
    if q.get("source") == "origin":
        return "origin"
    return "guild" if q.get("faction") else "other"


def _quest_entry(char: Character, gamedata: GameData, qid: str) -> dict:
    """單一任務的呈現資料:當前目標 + 各階段進度(done/cur/todo)。"""
    from tesrpg.systems import quests
    q = gamedata.quests[qid]
    obj, idx, total = quests.current_objective(char, gamedata, qid)
    rq = quests.resolved(char, gamedata, qid)
    stage_defs = rq.get("stages") or [{"text": rq.get("text", "")}]
    stages = [{"text": s.get("text", ""),
               "state": ("done" if i < idx else "cur" if i == idx else "todo")}
              for i, s in enumerate(stage_defs)]
    return {"name": q["name"],
            "faction": (gamedata.factions[q["faction"]]["name"] if q.get("faction") else None),
            "objective": quests.objective_text(char, gamedata, qid),
            "stage": [idx + 1, total], "stages": stages}


def _quests_view(char: Character, gamedata: GameData) -> dict:
    buckets: dict = {k: [] for k, _ in _QUEST_GROUPS}
    for qid in char.quests:
        buckets[_quest_group(gamedata.quests[qid])].append(_quest_entry(char, gamedata, qid))
    groups = [{"title": title, "quests": buckets[k]} for k, title in _QUEST_GROUPS if buckets[k]]
    return {"groups": groups, "completed": len(char.completed_quests)}


def _active_origin_quest(char: Character, gamedata: GameData) -> dict | None:
    """進行中的起手任務(出身任務)摘要;無則 None。"""
    from tesrpg.systems import quests
    for qid in char.quests:
        if gamedata.quests.get(qid, {}).get("source") == "origin":
            return {"name": gamedata.quests[qid]["name"],
                    "objective": quests.objective_text(char, gamedata, qid)}
    return None


def _board_view(char: Character, gamedata: GameData, qids: list) -> dict:
    from tesrpg.systems import quests
    cards = []
    for qid in qids:
        q = gamedata.quests[qid]
        rw = q.get("reward", {})
        chips = []
        if rw.get("gold"):
            chips.append({"text": f"{rw['gold']} 金", "tone": "gold"})
        if rw.get("fame"):
            chips.append({"text": f"聲望 +{rw['fame']}", "tone": "cyan"})
        for iid in rw.get("items", []):
            chips.append({"text": gamedata.item_name(iid), "tone": "green"})
        cards.append({"key": qid, "name": q["name"],
                      "faction": (gamedata.factions[q["faction"]]["name"] if q.get("faction") else None),
                      "objective": quests.objective_text(char, gamedata, qid), "rewards": chips})
    return {"quests": cards}


def board_panel(char: Character, gamedata: GameData, qids: list) -> None:
    """web:告示板可點委託卡(列 key=quest id,對齊委託選單 → wireActionableRows 接管);終端不發。"""
    if _web is not None:
        _emit_view("board", _board_view(char, gamedata, qids))


def _origin_card(gamedata: GameData, oid: str, od: dict) -> dict:
    """單一開局的「起始處境」摘要(供創角資訊面板;終端+Web 共用)。"""
    loc_id = od.get("location") or gamedata.world.get("start_location", "bruma")
    gear = ([gamedata.item_name(od["weapon"])] if od.get("weapon") else []) \
        + [gamedata.item_name(e) for e in od.get("equip", [])]
    tags = [gamedata.factions[f]["name"] for f in od.get("faction", {}) if f in gamedata.factions]
    if od.get("vampire"):
        tags.append("吸血鬼")
    if od.get("werewolf"):
        tags.append("狼人")
    if od.get("bounty"):
        tags.append("通緝在身")
    if od.get("companions"):
        tags.append("帶同伴")
    if od.get("spells"):
        tags.append("會法術")
    q = gamedata.quests.get(od.get("quest", ""), {})
    return {"id": oid, "name": od["name"], "blurb": od["blurb"],
            "location": gamedata.location(loc_id)["name"],
            "gold": od.get("gold"), "gear": gear, "tags": tags, "quest": q.get("name", "")}


def _origins_view(gamedata: GameData, oids: list | None = None) -> dict:
    ids = oids if oids is not None else list(gamedata.origins)
    return {"origins": [_origin_card(gamedata, oid, gamedata.origins[oid]) for oid in ids]}


def origins_panel(gamedata: GameData, oids: list | None = None) -> None:
    """創角開局選擇前的資訊面板:逐開局列出起始地/金幣/裝備·身分/起手任務(終端表 + Web 卡)。
    oids 給定時只列該批(兩層選單:選定類別後只顯示該類)。"""
    if _web is not None:
        _emit_view("origins", _origins_view(gamedata, oids))
        return
    tbl = Table(box=None, pad_edge=False, padding=(0, 1))
    tbl.add_column("開局", style=f"bold {PARCH}", no_wrap=True)
    tbl.add_column("起始地", style=INK, no_wrap=True)
    tbl.add_column("金幣", justify="right", style=GOLD_DIM)
    tbl.add_column("裝備 · 身分", style=INK)
    tbl.add_column("起手任務", style="cyan")
    for c in _origins_view(gamedata, oids)["origins"]:
        ident = "、".join(c["gear"] + c["tags"]) or "標準起始"
        gold = str(c["gold"]) if c["gold"] is not None else "標準"
        tbl.add_row(c["name"], c["location"], gold, ident, c["quest"])
    console.print(_panel(tbl, title="🧭 開局背景一覽(各自帶起手任務)"))


def _court_view(ruler, gamedata, reception, standing, thane, politics, territory) -> dict:
    v = {"title": ruler["title"], "name": ruler["name"], "reception": reception, "blurb": ruler["blurb"],
         "race": gamedata.races.get(ruler["race"], {}).get("name", ruler["race"]),
         "garrison": (politics or {}).get("garrison", ruler["garrison"]), "bloc": ruler.get("bloc_label"),
         "stance": (f"{politics['stance']} · 與你 {politics['relation']}" if politics else None),
         "thane": thane, "standing": (standing if (not thane and standing is not None) else None),
         "territory": None}
    if territory:
        v["territory"] = {"population": territory["population"], "tax": territory["tax"],
                          "garrison": territory["garrison"], "base": territory["base"],
                          "maint": territory["maint"], "unrest": territory["unrest"], "net": territory.get("net")}
    return v


def _territory_view(rows, gamedata, gold) -> dict:
    out = []
    for r in rows:
        cd = r["countdown"]
        out.append({"name": gamedata.location(r["loc"])["name"], "population": r["population"],
                    "tax": r["tax"], "garrison": r["garrison"], "base": r["base"], "maint": r["maint"],
                    "net": r["net"], "unrest": r["unrest"],
                    "countdown": ("—" if cd is None else f"{cd // 24}天{cd % 24}時")})
    return {"rows": out, "gold": gold}


def _map_view(char: Character, gamedata: GameData) -> dict:
    from tesrpg.systems import landmarks, politics
    locs = gamedata.world["locations"]
    by_prov: dict[str, list[str]] = {}
    order: list[str] = []
    for lid, loc in locs.items():
        by_prov.setdefault(loc["province"], []).append(lid)
        if loc["province"] not in order:
            order.append(loc["province"])
    _FAC = {"imperial": "帝", "independent": "獨", "neutral": "中", "daedric": "湮", "own": "己"}
    provs = []
    for prov in order:
        nodes = []
        visited_n = 0
        for lid in by_prov[prov]:
            loc = locs[lid]
            if lid in char.visited_locations:
                visited_n += 1
            fac = None
            if gamedata.ruler_at(lid):
                fac = "己" if lid in char.city_faction else _FAC.get(politics.faction_of(char, gamedata, lid))
            nodes.append({"name": loc["name"], "type": LOC_TYPE_NAME.get(loc["type"], ""),
                          "here": lid == char.location_id, "visited": lid in char.visited_locations,
                          "danger": loc.get("danger", 0), "faction": fac,
                          "landmark": bool(gamedata.landmark_at(lid) and landmarks.is_discovered(char, lid)),
                          "services": [_SERVICE_CN[s] for s in loc.get("services", []) if s in _SERVICE_CN],
                          "exits": [{"name": locs[d]["name"], "hours": h} for d, h in loc.get("links", {}).items()]})
        provs.append({"name": prov, "nodes": nodes,
                      "visited": visited_n, "total": len(by_prov[prov])})
    return {"provinces": provs}


# --- 視覺識別 -----------------------------------------------------------
# 金=主結構/強調色(面板邊框、選項編號、標題);語意色維持(紅戰鬥/青魔法/綠潛行)。
GOLD = "gold1"
GOLD_DIM = "gold3"
PARCH = "wheat1"   # 面板內文淺色(羊皮紙感)
INK = "grey70"     # 次要資訊
FAINT = "grey50"   # 註腳/分隔

PANEL = box.ROUNDED       # 一般面板
HERO = box.DOUBLE_EDGE    # 標題/結算/升級等重點畫面

SPEC_COLOR = {"combat": "red", "magic": "cyan", "stealth": "green"}
RESOURCE_STYLE = {"health": "red", "magicka": "cyan", "fatigue": "green"}


def _panel(body, title: str | None = None, style: str = GOLD,
           box_=PANEL, **kw) -> Panel:
    """統一框線風格的面板工廠。"""
    return Panel(body, title=title, border_style=style, box=box_,
                 title_align="left", **kw)


# --- 基本元件 -----------------------------------------------------------
def banner() -> None:
    if _web is not None:
        return                   # 報頭已是標題;web 模式不重複畫 banner
    title = Text("流   亡   者", justify="center", style=f"bold {GOLD}")
    orn = Text("⚔  ◈  ✦  ◈  ⚔", justify="center", style=GOLD_DIM)
    sub = Text("上古卷軸風格 · 技能驅動沙盒文字 RPG", justify="center", style=PARCH)
    body = Group(Text(), title, Text(), orn, Text(), sub, Text())
    console.print(Align.center(_panel(body, box_=HERO, padding=(0, 4), width=54)))


def _bar(cur: float, mx: float, color: str, width: int = 16) -> Text:
    mx = max(1, mx)
    filled = int(round(width * max(0, min(cur, mx)) / mx))
    t = Text()
    t.append("█" * filled, style=color)
    t.append("░" * (width - filled), style="grey37")
    t.append(f" {int(cur)}/{int(mx)}", style="white")
    return t


def status_line(state: GameState, gamedata: GameData | None = None, allies: list | None = None) -> None:
    """行動之間的精簡狀態列(金色頂欄分隔)。allies=當前情境召喚物(地城預召喚);
    gamedata 提供 → 一併顯示隊伍同伴狀態(名稱+HP+負傷)。"""
    if _web is not None:
        global _hud_state, _hud_gamedata, _hud_allies
        _hud_state = state          # web:不發 status 卡,改由常駐 HUD(frame.hud)顯示
        _hud_gamedata = gamedata
        _hud_allies = allies
        return
    c = state.player
    t = Text()
    t.append("❖ ", style=GOLD)
    t.append(f"{c.name}", style="bold")
    t.append(f"  Lv.{c.level}", style=GOLD)
    t.append(f"   ◷ {state.time.label()}", style=INK)
    extra = []
    if getattr(c, "is_vampire", False):
        from tesrpg.systems import vampirism
        extra.append(f"[bold red]🩸 {vampirism.STAGE_NAMES[min(3, max(0, c.vampire_stage))]}吸血鬼[/]")
    elif getattr(c, "vampire_infected_day", -1) >= 0:
        extra.append("[red]🦠 吸血熱潛伏中[/]")
    if getattr(c, "beast_form", False):
        extra.append("[bold red]🐺 獸形[/]")
    elif getattr(c, "is_werewolf", False):
        extra.append("[red]🐺 狼人[/]")
    elif getattr(c, "werewolf_infected_day", -1) >= 0:
        extra.append("[red]🌑 狼人熱潛伏中[/]")
    from tesrpg.systems import skooma
    if skooma.is_high(c, state):
        extra.append("[magenta]🌙 月糖之醉[/]")
    elif skooma.is_addicted(c):
        extra.append("[red]💀 斯庫瑪戒斷[/]")
    if c.fame:
        extra.append(f"[cyan]聲望 {c.fame}[/]")
    total_bounty = sum(c.bounties.values())
    if total_bounty:
        extra.append(f"[red]通緝 {total_bounty}[/]")
    console.print(t)
    rsrc = (("生命", c.health, c.max_health, "red"),
            ("魔力", c.magicka, c.max_magicka, "cyan"),
            ("體力", c.fatigue, c.max_fatigue, "green"))
    if console.width >= 84:   # 寬終端:血條
        grid = Table.grid(padding=(0, 2))
        grid.add_row(*[x for label, cur, mx, color in rsrc
                       for x in (Text(label, style=color), _bar(cur, mx, color))])
        console.print(grid)
    else:                     # 窄終端:一行純數字,避免折行
        line = Text()
        for label, cur, mx, color in rsrc:
            line.append(f"{label} ", style=color)
            line.append(f"{int(cur)}/{int(mx)}", style=f"bold {color}")
            line.append("   ")
        console.print(line)
    if extra:
        console.print(" " + "   ".join(extra))
    for p in _party_status(c, gamedata):     # 隊伍同伴(名稱+HP+負傷)
        tag = "[red](負傷)[/]" if p["downed"] else ""
        console.print(f"  [cyan]└ {p['name']}[/] {p['hp'][0]}/{p['hp'][1]} {tag}")
    for a in _allies_status(allies):         # 當前召喚物(名稱+HP+剩餘回合)
        tt = f" · {a['turns']} 回合" if a["turns"] is not None else ""
        console.print(f"  [magenta]└ {a['name']}(召喚)[/] {a['hp'][0]}/{a['hp'][1]}{tt}")
    if c.can_level_up():
        console.print(f"  [bold {GOLD}]★ 可以升級了![/]")


# --- 角色卡 -------------------------------------------------------------
_RESIST_CN = {"fire": "火焰", "frost": "冰霜", "shock": "雷電", "magic": "魔法",
              "poison": "毒素", "disease": "疾病", "bleed": "撕裂"}
_RES_ELEMS = ("fire", "frost", "shock", "magic", "poison", "disease")
_SLOT_CN = {"helmet": "頭盔", "cuirass": "胸甲", "gauntlets": "護手", "boots": "靴",
            "shield": "盾", "amulet": "項鍊", "ring1": "戒指一", "ring2": "戒指二"}


def _resist_summary(char: Character, gamedata: GameData) -> str:
    """非零抗性的精簡摘要(供 overview):火焰+30% 毒素+50% …;負值=弱點。"""
    from tesrpg.systems import magic
    r = magic.entity_resist(char, gamedata)
    return "　".join(f"{_RESIST_CN.get(e, e)}{r[e]:+d}%" for e in _RES_ELEMS if r.get(e))


def _effect_label(e: dict) -> str:
    k = e.get("kind"); turns = e.get("turns", 0); mag = e.get("magnitude", 0)
    elem = _RESIST_CN.get(e.get("element"), "")
    names = {"shield": f"護盾 +{mag}", "regen": f"再生 +{mag}/回合",
             "dot": f"{elem}侵蝕 {mag}/回合", "fear": "恐懼", "paralyze": "麻痺",
             "weaken": "耗弱", "stagger": "踉蹌", "soul_trap": "擒魂"}
    base = names.get(k, k or "效果")
    return f"{base}（{turns} 回合)" if turns else base


def _sheet_overview_extra(char: Character, gamedata: GameData) -> Text | None:
    """overview 底部的精簡狀態塊(公會/血脈/進行中效果);全為 state-independent。"""
    from tesrpg.systems import factions
    extra = Text()
    guilds = [f"{gamedata.factions[f]['name']}「{factions.rank_name(char, gamedata, f)}」"
              for f in char.factions if f in gamedata.factions]
    if guilds:
        extra.append("公會  ", style=GOLD)
        extra.append("　".join(guilds) + "\n", style=PARCH)
    if getattr(char, "is_vampire", False):
        from tesrpg.systems import vampirism
        nm = vampirism.STAGE_NAMES[min(3, max(0, char.vampire_stage))]
        extra.append("血脈  ", style="red")
        extra.append(f"吸血鬼 階級{char.vampire_stage}「{nm}」\n", style=PARCH)
    if char.active_effects:
        extra.append("效果  ", style=GOLD)
        extra.append("、".join(_effect_label(e) for e in char.active_effects), style=PARCH)
    return extra if extra.plain.strip() else None


def character_sheet(char: Character, gamedata: GameData) -> None:
    if _web is not None:
        _emit_view("sheet", _sheet_view(char, gamedata))
        return
    race = gamedata.races[char.race]["name"]
    sign = gamedata.birthsigns[char.birthsign]["name"]
    cls = ("自訂" if char.class_id == "custom"
           else gamedata.classes[char.class_id]["name"])
    sex = "男" if char.sex == "male" else "女"
    spec = formulas.SPEC_NAMES.get(char.specialization, char.specialization)

    header = Text()
    header.append(f"{char.name}\n", style=f"bold {GOLD}")
    header.append(f"{race} · {sex} · {sign} · {cls}（{spec}專精）\n", style=PARCH)
    header.append(f"等級 {char.level}", style=GOLD)
    header.append(f"   等級經驗 {int(char.level_xp)}/{int(formulas.levelup_xp_threshold(char.level))}",
                  style=INK)

    # 資源
    res = Table.grid(padding=(0, 2))
    res.add_row(Text("生命", style="red"), _bar(char.health, char.max_health, "red"))
    res.add_row(Text("魔力", style="cyan"), _bar(char.magicka, char.max_magicka, "cyan"))
    res.add_row(Text("體力", style="green"), _bar(char.fatigue, char.max_fatigue, "green"))
    res.add_row(Text("負重", style=GOLD),
                Text(f"上限 {formulas.max_encumbrance(char.attr('strength'))}", style=INK))
    res.add_row(Text("金幣", style=GOLD), Text(str(char.gold), style=PARCH))
    _od = gamedata.origins.get(char.origin)
    if _od:
        res.add_row(Text("出身", style=GOLD), Text(_od["name"], style=PARCH))
    _iq = _active_origin_quest(char, gamedata)
    if _iq:
        res.add_row(Text("起手", style="cyan"), Text(f"{_iq['name']} — {_iq['objective']}", style=INK))
    res.add_row(Text("武器", style=GOLD), Text(weapon_line(char, gamedata), style=PARCH))
    from tesrpg.systems import inventory as _inv
    _worn = _inv.worn_armor_rating(char, gamedata)
    if _worn:
        res.add_row(Text("護甲", style=GOLD), Text(str(_worn), style=PARCH))
    _rsum = _resist_summary(char, gamedata)
    if _rsum:
        res.add_row(Text("抗性", style=GOLD), Text(_rsum, style=PARCH))
    res.add_row(Text("聲望", style=GOLD),
                Text(f"{char.fame}" + (f"   惡名 {char.infamy}" if char.infamy else ""), style=PARCH))
    _bounty = sum(char.bounties.values())
    if _bounty:
        res.add_row(Text("通緝", style="red"), Text(f"{_bounty} 金", style=PARCH))

    # 屬性
    attr_tbl = Table(title="屬性", title_style=f"bold {GOLD}", box=None, pad_edge=False)
    attr_tbl.add_column("", style=INK)
    attr_tbl.add_column("", justify="right", style=PARCH)
    attr_tbl.add_column("", style=INK)
    attr_tbl.add_column("", justify="right", style=PARCH)
    items = [(k, formulas.ATTRIBUTE_NAMES[k], char.attr(k)) for k in formulas.ATTRIBUTES]
    for i in range(0, len(items), 2):
        left = items[i]
        right = items[i + 1] if i + 1 < len(items) else ("", "", "")
        fav_l = f"[{GOLD}]★[/]" if left[0] in char.favored_attributes else " "
        fav_r = f"[{GOLD}]★[/]" if right and right[0] in char.favored_attributes else " "
        attr_tbl.add_row(f"{fav_l}{left[1]}", str(left[2]),
                         (f"{fav_r}{right[1]}" if right[1] else ""),
                         (str(right[2]) if right[1] else ""))

    parts = [header, Rule(style=GOLD_DIM), Columns([res, attr_tbl], padding=(0, 6))]
    extra = _sheet_overview_extra(char, gamedata)
    if extra is not None:
        parts += [Rule(style=GOLD_DIM), extra]
    console.print(_panel(Group(*parts)))
    skill_table(char, gamedata)


def skill_table(char: Character, gamedata: GameData) -> None:
    """三系技能並排成單一對齊格線(去除冗餘欄頭)。"""
    specs = ("combat", "magic", "stealth")
    lists = {s: gamedata.skills_by_spec(s) for s in specs}
    rows = max(len(v) for v in lists.values())

    tbl = Table(box=box.SIMPLE_HEAD, pad_edge=False, padding=(0, 1),
                header_style="", border_style=GOLD_DIM, expand=True)
    for s in specs:
        tbl.add_column(formulas.SPEC_NAMES[s], header_style=f"bold {SPEC_COLOR[s]}",
                       style=PARCH, ratio=3, no_wrap=True)
        tbl.add_column("", justify="right", style="bold", ratio=1)

    for i in range(rows):
        cells: list[str] = []
        for s in specs:
            ids = lists[s]
            if i < len(ids):
                sid = ids[i]
                star = f"[{GOLD}]✦[/]" if char.is_major_skill(sid) else "·"
                cells += [f"{star} {gamedata.skill_name(sid)}", str(char.skill(sid))]
            else:
                cells += ["", ""]
        tbl.add_row(*cells)

    console.print(_panel(tbl, title="技能"))
    console.print(f"  [{FAINT}]✦ = 主修技能(升點給 ×1.5 等級經驗);右欄為技能等級[/]")
    unlocked = mastery.unlocked(char, gamedata)
    if unlocked:
        lines = Text()
        for i, e in enumerate(unlocked):
            sk = gamedata.skill_name(e["skill"])
            lines.append(f"✦ {e['name']}", style="bold magenta")
            lines.append(f"（{sk} {e['threshold']}） {e['desc']}", style=INK)
            if i < len(unlocked) - 1:
                lines.append("\n")
        console.print(_panel(lines, title="技能里程碑"))


# --- 角色卡:互動式檢視(各支唯讀渲染器;不改 char 狀態、不耗時)----------
def sheet_resistances(char: Character, gamedata: GameData) -> None:
    from tesrpg.systems import magic
    r = magic.entity_resist(char, gamedata)
    if _web is not None:
        _emit_view("resistances",
                   {"rows": [{"name": _RESIST_CN[e], "value": int(r.get(e, 0))} for e in _RES_ELEMS]})
        return
    tbl = Table(box=box.SIMPLE_HEAD, border_style=GOLD_DIM, pad_edge=False)
    tbl.add_column("元素", style=INK)
    tbl.add_column("抗性", justify="right", style=PARCH)
    tbl.add_column("", style=FAINT)
    for e in _RES_ELEMS:
        v = r.get(e, 0)
        note = "弱點" if v < 0 else ("免疫" if v >= 100 else "")
        tbl.add_row(_RESIST_CN[e], f"{v:+d}%", note)
    console.print(_panel(tbl, title="元素抗性(種族+裝備+血脈)"))


def sheet_effects(char: Character, gamedata: GameData) -> None:
    if _web is not None:
        rows = ([_ln(f"• {_effect_label(e)}") for e in char.active_effects]
                or [_ln("目前沒有進行中的效果。", "muted")])
        _emit_panel("進行中效果", rows)
        return
    body = Text()
    if not char.active_effects:
        body.append("目前沒有進行中的效果。", style=INK)
    for e in char.active_effects:
        body.append(f"• {_effect_label(e)}\n", style=PARCH)
    console.print(_panel(body, title="進行中效果"))


def sheet_factions(char: Character, gamedata: GameData) -> None:
    from tesrpg.systems import factions
    members = [f for f in char.factions if f in gamedata.factions]
    if _web is not None:
        rows = []
        for fid in members:
            rows.append(_hd(f"{gamedata.factions[fid]['name']}「{factions.rank_name(char, gamedata, fid)}」"))
            perk = factions.perk_desc(char, gamedata, fid)
            if perk:
                rows.append(_ln(perk, "muted"))
        _emit_panel("公會與階級", rows or [_ln("你尚未加入任何公會。", "muted")])
        return
    body = Text()
    if not members:
        body.append("你尚未加入任何公會。", style=INK)
    for fid in members:
        body.append(f"{gamedata.factions[fid]['name']}", style=f"bold {GOLD}")
        body.append(f"　「{factions.rank_name(char, gamedata, fid)}」\n", style=PARCH)
        perk = factions.perk_desc(char, gamedata, fid)
        if perk:
            body.append(f"   {perk}\n", style=INK)
    console.print(_panel(body, title="公會與階級"))


def sheet_masteries(char: Character, gamedata: GameData) -> None:
    """技能里程碑(v2 二選一):已選(✦)/ 待選=達門檻未選(◆,回城或升級時二選一)/ 未達門檻(○)。

    待選與未達各列出該節點的兩個選項,讓玩家預覽抉擇。已選節點的「另一條路」不再列出。
    """
    unl = mastery.unlocked(char, gamedata)
    chosen_nodes = set(getattr(char, "mastery_choices", {}).keys())
    other = [e for e in mastery._defs(gamedata)
             if e not in unl and e["node_id"] not in chosen_nodes]
    pending = sorted([e for e in other if char.base_skill(e["skill"]) >= e["threshold"]],
                     key=lambda x: (x["skill"], x["threshold"]))
    future = sorted([e for e in other if char.base_skill(e["skill"]) < e["threshold"]],
                    key=lambda x: (x["skill"], x["threshold"]))
    if _web is not None:
        vm_unl = [{"name": e["name"], "skill": gamedata.skill_name(e["skill"]), "desc": e["desc"]}
                  for e in unl]
        single_nodes = {n["id"] for n in mastery._nodes(gamedata) if len(mastery._choosable_options(n)) == 1}
        vm_lock = []
        for e in pending + future:
            cur = char.base_skill(e["skill"])
            vm_lock.append({"name": e["name"], "skill": gamedata.skill_name(e["skill"]),
                            "desc": e["desc"], "cur": cur, "threshold": e["threshold"],
                            "remaining": max(0, e["threshold"] - cur),
                            "auto": e["node_id"] in single_nodes})   # 單一 perk 自動授予(非二選一)
        _emit_view("masteries", {"unlocked": vm_unl, "locked": vm_lock})
        return
    body = Text()
    if unl:
        body.append("已銘刻\n", style=f"bold {GOLD}")
        for e in unl:
            body.append(f"  ✦ {e['name']}", style="bold magenta")
            body.append(f"（{gamedata.skill_name(e['skill'])} {e['threshold']}） {e['desc']}\n", style=INK)
    if pending:
        single_nodes = {n["id"] for n in mastery._nodes(gamedata) if len(mastery._choosable_options(n)) == 1}
        body.append("\n待選(已達門檻 —— 回城或升級時生效;二選一者擇一,單一者自動授予)\n", style=f"bold {GOLD}")
        for e in pending:
            auto = "(自動授予)" if e["node_id"] in single_nodes else ""
            body.append(f"  ◆ {e['name']}{auto}（{gamedata.skill_name(e['skill'])} {e['threshold']}） {e['desc']}\n",
                        style=PARCH)
    if future:
        body.append("\n未達門檻\n", style=f"bold {GOLD}")
        for e in future:
            cur = char.base_skill(e["skill"])
            body.append(f"  ○ {e['name']}（{gamedata.skill_name(e['skill'])} {cur}/{e['threshold']}）"
                        f" {e['desc']}\n", style=FAINT)
    if not unl and not pending and not future:
        body.append("(無里程碑資料)", style=INK)
    console.print(_panel(body, title="技能里程碑"))


def sheet_achievements(char: Character, gamedata: GameData) -> None:
    """成就子檢視:已達成(✦)+ 未達成(○,desc 兼作如何取得的提示)。唯讀推導。"""
    won, locked = achievements.earned_and_locked(char, gamedata)
    if _web is not None:
        _emit_view("achievements", {
            "earned": [{"name": a["name"], "desc": a["desc"]} for a in won],
            "locked": [{"name": a["name"], "desc": a["desc"]} for a in locked],
        })
        return
    body = Text()
    total = len(achievements._defs(gamedata))
    body.append(f"已達成 {len(won)}/{total}\n", style=f"bold {GOLD}")
    for a in won:
        body.append(f"  ✦ {a['name']}", style="bold magenta")
        body.append(f"  {a['desc']}\n", style=INK)
    if locked:
        body.append("\n未達成\n", style=f"bold {GOLD}")
        for a in locked:
            body.append(f"  ○ {a['name']}  {a['desc']}\n", style=FAINT)
    if not won and not locked:
        body.append("(無成就資料)", style=INK)
    console.print(_panel(body, title="成就"))


def sheet_power(char: Character, state: GameState, gamedata: GameData) -> None:
    from tesrpg.systems import powers
    pid = powers.power_id(char, gamedata)
    if _web is not None:
        if not pid:
            _emit_panel("星座之力", [_ln("你沒有可施展的星座之力。", "muted")])
            return
        pdef = powers.power_def(pid)
        rows = [_hd(pdef["name"])]
        if pdef.get("desc"):
            rows.append(_ln(pdef["desc"]))
        if pdef.get("contexts"):
            rows.append(_kv("可用場景", "、".join(pdef["contexts"])))
        ready = powers.available(char, state, gamedata)
        rows.append(_ln("狀態:今日就緒" if ready else "狀態:今日已施展", "green" if ready else "yellow"))
        _emit_panel("星座之力", rows)
        return
    body = Text()
    if not pid:
        body.append("你沒有可施展的星座之力。", style=INK)
    else:
        pdef = powers.power_def(pid)
        body.append(f"{pdef['name']}\n", style=f"bold {GOLD}")
        if pdef.get("desc"):
            body.append(f"{pdef['desc']}\n", style=PARCH)
        if pdef.get("contexts"):
            body.append(f"可用場景:{'、'.join(pdef['contexts'])}\n", style=INK)
        ready = powers.available(char, state, gamedata)
        body.append("狀態:今日就緒" if ready else "狀態:今日已施展",
                    style="green" if ready else "yellow")
    console.print(_panel(body, title="星座之力"))


def sheet_bounty(char: Character, gamedata: GameData) -> None:
    total = sum(char.bounties.values())
    if _web is not None:
        rows = [_kv("聲望", char.fame), _kv("惡名", char.infamy)]
        if total:
            rows.append(_ln(f"通緝總額 {total} 金", "red"))
            for prov, amt in sorted(char.bounties.items()):
                if amt:
                    rows.append(_kv(prov, f"{amt} 金"))
        else:
            rows.append(_ln("目前無通緝在身。", "green"))
        _emit_panel("聲望與通緝", rows)
        return
    body = Text()
    body.append(f"聲望 {char.fame}    惡名 {char.infamy}\n", style=PARCH)
    if total:
        body.append(f"通緝總額 {total} 金\n", style="red")
        for prov, amt in sorted(char.bounties.items()):
            if amt:
                body.append(f"  {prov}:{amt} 金\n", style=INK)
    else:
        body.append("目前無通緝在身。", style="green")
    console.print(_panel(body, title="聲望與通緝"))


def _tr_bonus(category: str, key: str, gamedata: GameData) -> str:
    if category == "skills":
        return gamedata.skill_name(key)
    if category == "attrs":
        return formulas.ATTRIBUTE_NAMES.get(key, key)
    if category == "resist":
        return _RESIST_CN.get(key, key)
    return {"health": "生命", "magicka": "魔力", "fatigue": "體力"}.get(key, key)


def _describe_set_bonus(b: dict | None, gamedata: GameData) -> str:
    """把套裝 bonus dict 譯成人話(供角色卡顯示實際效果,如「魔力上限 +40、施法省力 20%」)。"""
    if not b:
        return ""
    k = b.get("kind"); mag = int(b.get("magnitude", 0)); parts = []
    if k in ("fortify_resource", "armor_fortify"):
        parts.append(f"{_tr_bonus('resources', b['stat'], gamedata)}上限 +{mag}")
    elif k == "fortify_skill":
        parts.append(f"{_tr_bonus('skills', b['skill'], gamedata)} +{mag}")
    elif k == "fortify_attribute":
        parts.append(f"{_tr_bonus('attrs', b['attr'], gamedata)} +{mag}")
    elif k == "resist_element":
        parts.append(f"{_tr_bonus('resist', b['element'], gamedata)}抗性 +{mag}%")
    if "cast_fatigue_factor" in b:
        parts.append(f"施法省力 {int(round((1 - b['cast_fatigue_factor']) * 100))}%")
    return "、".join(parts)


def sheet_equipment(char: Character, gamedata: GameData) -> None:
    from tesrpg.systems import inventory
    if _web is not None:
        rows = [_kv("武器", _plain(weapon_line(char, gamedata)))]
        if char.offhand:
            rows.append(_kv("副手", gamedata.item_name(char.offhand)))
        for slot in ("helmet", "cuirass", "gauntlets", "boots", "shield", "amulet", "ring1", "ring2"):
            iid = char.equipped.get(slot)
            if iid:
                rows.append(_kv(_SLOT_CN[slot], gamedata.item_name(iid) + _temper_suffix(char, iid)))
        worn = inventory.worn_armor_rating(char, gamedata)
        eff = inventory.effective_armor_rating(char, gamedata)
        rows.append(_kv("護甲值", f"名目 {worn} · 有效 {eff:.0f}"))
        _smat, _scnt, _sb = inventory.set_progress(char, gamedata)
        if _scnt == 4 and _sb:                          # 穿滿四件同材質 → 套裝啟用
            _sn = gamedata.armor_sets.get(_smat, {}).get("name", "整套同材質")
            rows.append(_ln(f"套裝加成　{_sn}（{_describe_set_bonus(_sb, gamedata)}）", "green"))
        elif _scnt >= 2 and _sb:                         # 部分湊齊 → 進度提示(讓玩家知道快湊滿)
            _sn = gamedata.armor_sets.get(_smat, {}).get("name", "套裝")
            rows.append(_ln(f"套裝進度　{_sn} {_scnt}/4(穿滿享:{_describe_set_bonus(_sb, gamedata)})", "faint"))
        bon = inventory.equipment_bonuses(char, gamedata)
        for label, cat in (("技能", "skills"), ("屬性", "attrs"), ("抗性", "resist"), ("資源", "resources")):
            d = bon.get(cat) or {}
            if d:
                rows.append(_kv(f"{label}加成", "、".join(f"{_tr_bonus(cat, k, gamedata)}{v:+d}" for k, v in d.items())))
        _emit_panel("穿戴與套裝", rows)
        return
    body = Text()
    body.append("武器  ", style=GOLD)
    body.append(weapon_line(char, gamedata) + "\n", style=PARCH)
    if char.offhand:
        body.append("副手  ", style=GOLD)
        body.append(gamedata.item_name(char.offhand) + "\n", style=PARCH)
    for slot in ("helmet", "cuirass", "gauntlets", "boots", "shield", "amulet", "ring1", "ring2"):
        iid = char.equipped.get(slot)
        if iid:
            body.append(f"{_SLOT_CN[slot]}  ", style=GOLD)
            body.append(gamedata.item_name(iid) + _temper_suffix(char, iid) + "\n", style=PARCH)
    worn = inventory.worn_armor_rating(char, gamedata)
    eff = inventory.effective_armor_rating(char, gamedata)
    body.append(f"護甲值  名目 {worn} · 有效 {eff:.0f}\n", style=INK)
    _smat, _scnt, _sb = inventory.set_progress(char, gamedata)
    if _scnt == 4 and _sb:                              # 穿滿四件同材質 → 套裝啟用(顯示實際效果)
        _setname = gamedata.armor_sets.get(_smat, {}).get("name", "整套同材質")
        body.append(f"套裝加成  {_setname}（{_describe_set_bonus(_sb, gamedata)}）\n", style="bold green")
    elif _scnt >= 2 and _sb:                            # 部分湊齊 → 進度提示
        _setname = gamedata.armor_sets.get(_smat, {}).get("name", "套裝")
        body.append(f"套裝進度  {_setname} {_scnt}/4(穿滿享:{_describe_set_bonus(_sb, gamedata)})\n", style="grey62")
    bon = inventory.equipment_bonuses(char, gamedata)
    for label, cat in (("技能", "skills"), ("屬性", "attrs"), ("抗性", "resist"), ("資源", "resources")):
        d = bon.get(cat) or {}
        if d:
            body.append(f"{label}加成  ", style=GOLD)
            body.append("、".join(f"{_tr_bonus(cat, k, gamedata)}{v:+d}" for k, v in d.items()) + "\n",
                        style=PARCH)
    console.print(_panel(body, title="穿戴與套裝"))


def sheet_vampirism(char: Character, gamedata: GameData) -> None:
    from tesrpg.systems import vampirism
    if _web is not None:
        if not vampirism.is_vampire(char):
            _emit_panel("吸血鬼狀態", [_ln("你不是吸血鬼。", "muted")])
            return
        nm = vampirism.STAGE_NAMES[min(3, max(0, char.vampire_stage))]
        rows = [_ln(f"吸血鬼 階級 {char.vampire_stage} 「{nm}」", "red")]
        for cat, label, d in (("attrs", "屬性", char.vampire_attr_bonus),
                              ("skills", "技能", char.vampire_skill_bonus),
                              ("resist", "抗性", char.vampire_resist)):
            if d:
                rows.append(_kv(label, "、".join(f"{_tr_bonus(cat, k, gamedata)}{v:+d}" for k, v in d.items())))
        rows.append(_ln("(階級越餓越高,進食歸 0;火焰轉弱點、免疫疾病)", "faint"))
        _emit_panel("吸血鬼狀態", rows)
        return
    body = Text()
    if not vampirism.is_vampire(char):
        body.append("你不是吸血鬼。", style=INK)
    else:
        nm = vampirism.STAGE_NAMES[min(3, max(0, char.vampire_stage))]
        body.append(f"吸血鬼 階級 {char.vampire_stage} 「{nm}」\n", style="bold red")
        for cat, label, d in (("attrs", "屬性", char.vampire_attr_bonus),
                              ("skills", "技能", char.vampire_skill_bonus),
                              ("resist", "抗性", char.vampire_resist)):
            if d:
                body.append(f"{label}  ", style=GOLD)
                body.append("、".join(f"{_tr_bonus(cat, k, gamedata)}{v:+d}" for k, v in d.items())
                            + "\n", style=PARCH)
        body.append("（階級越餓越高,進食歸 0;火焰轉弱點、免疫疾病)", style=FAINT)
    console.print(_panel(body, title="吸血鬼狀態"))


def sheet_lycanthropy(char: Character, state: GameState, gamedata: GameData) -> None:
    from tesrpg.systems import lycanthropy
    beast = lycanthropy.is_beast(char, state)
    is_ww = lycanthropy.is_werewolf(char)
    has_ring = is_ww and lycanthropy.has_hircine_ring(char, gamedata)
    if beast:
        remain = max(0, getattr(char, "beast_form_until", 0) - state.time.absolute_hours())
        phase = f"🐺 獸形中(尚餘約 {remain} 小時;吞噬獵物可續)"
    elif is_ww:
        phase = "人形(可於戰鬥中獸化變身," + ("獵者之戒:可隨意變身)" if has_ring else "每日一次)")
    elif lycanthropy.is_infected(char):
        phase = "🌑 狼人熱潛伏中(數日後將轉化)"
    else:
        phase = "未染狼人之血"
    # 獸血進程(餵食成長):階名 + 距下一階
    tier_lines: list[str] = []
    if is_ww:
        prog = lycanthropy.tier_progress(char)
        tline = f"獸血階 {prog['tier']}「{prog['name']}」(累計吞噬 {prog['feeds']})"
        if "remaining" in prog:
            tline += f" · 距「{prog['next_name']}」還 {prog['remaining']} 次吞噬"
        tier_lines.append(tline)
        if prog["tier"] >= lycanthropy.HOWL_TIER:
            tier_lines.append("已習「恫嚇之嚎」(獸形中可嚎叫懼敵)")
        if has_ring:
            tier_lines.append("✦ 佩戴獵者之戒 —— 不受每日變身次數所限")
    layers = (("attrs", "屬性", getattr(char, "werewolf_attr_bonus", {})),
              ("resist", "抗性", getattr(char, "werewolf_resist", {})))
    note = "(獸形:利爪撕敵、巨量生命、刀槍難傷,但脫去裝備、無法施法/用物/持械;與潛行互斥。越常以獸形吞噬獵物,獸血越濃。入城會被驅避;尋獵巫女巫可解咒)"
    if _web is not None:
        rows = [_ln(phase, "red" if beast else "muted")]
        for t in tier_lines:
            rows.append(_ln(t, "magenta"))
        if beast and getattr(char, "werewolf_health_bonus", 0):
            rows.append(_kv("獸形生命", f"+{char.werewolf_health_bonus}"))
        for cat, label, d in layers:
            if d:
                rows.append(_kv(label, "、".join(f"{_tr_bonus(cat, k, gamedata)}{v:+d}" for k, v in d.items())))
        rows.append(_ln(note, "faint"))
        _emit_panel("狼人狀態", rows)
        return
    body = Text()
    body.append(phase + "\n", style="bold red" if beast else INK)
    for t in tier_lines:
        body.append(t + "\n", style="magenta")
    if beast and getattr(char, "werewolf_health_bonus", 0):
        body.append("獸形生命  ", style=GOLD)
        body.append(f"+{char.werewolf_health_bonus}\n", style=PARCH)
    for cat, label, d in layers:
        if d:
            body.append(f"{label}  ", style=GOLD)
            body.append("、".join(f"{_tr_bonus(cat, k, gamedata)}{v:+d}" for k, v in d.items())
                        + "\n", style=PARCH)
    body.append(note, style=FAINT)
    console.print(_panel(body, title="狼人狀態"))


def party_panel(char: Character, gamedata: GameData) -> None:
    """隊伍面板:各同伴 HP/上限 + 羈絆級(倒下標『負傷待療』)+ 忠誠弧/頂點狀態。"""
    from tesrpg.systems import party
    items = []
    for cid in char.companions:
        nm = gamedata.companions.get(cid, {}).get("name", cid)   # 防毀損存檔的已移除同伴 id
        cur, mx = party.current_hp(char, gamedata, cid), party.max_hp(char, gamedata, cid)
        downed = party.is_downed(char, gamedata, cid)
        hp_s = "負傷待療" if downed else f"{cur}/{mx}"
        if party.arc_done(char, gamedata, cid):          # 忠誠弧已成 → 標頂點名
            cap = gamedata.companions.get(cid, {}).get("capstone", {})
            arc = f"★ {cap.get('label', '忠誠')}"
        elif party.arc_offerable(char, gamedata, cid):   # 羈絆達門檻 → 暗示可傾聽心事
            arc = "（有心事可傾聽）"
        else:
            arc = ""
        items.append((nm, hp_s, party.bond_name(char, cid), downed, arc))
    note = "(同伴 HP 跨戰持久;倒下→負傷退場,休息/旅店過夜可康復再上陣。並肩獲勝累積羈絆 → 更耐打;達羈絆門檻可『與同伴交談』傾聽其專屬支線)"
    if _web is not None:
        rows = []
        for nm, hp_s, bond, downed, arc in items:
            rows.append(_kv(nm, f"{hp_s} · 羈絆「{bond}」{('· ' + arc) if arc else ''}"))
        if not rows:
            rows = [_ln("你目前沒有同伴。", "muted")]
        rows.append(_ln(note, "faint"))
        _emit_panel("隊伍", rows)
        return
    body = Text()
    if not items:
        body.append("你目前沒有同伴。", style=INK)
    for nm, hp_s, bond, downed, arc in items:
        body.append(f"{nm}  ", style=GOLD)
        body.append(hp_s, style=("red" if downed else PARCH))
        body.append(f"  羈絆「{bond}」", style="cyan")
        if arc:
            body.append(f"  {arc}", style="gold1")
        body.append("\n")
    body.append(note, style=FAINT)
    console.print(_panel(body, title="隊伍"))


def companion_talk(name: str, line: str, bond: str) -> None:
    """同伴對話:名 + 依羈絆階的台詞(就地交談,非分支對話樹)。"""
    if _web is not None:
        _emit_panel(f"💬 {name}", [_ln(f"「{line}」"), _ln(f"羈絆「{bond}」", "faint")])
        return
    body = Text()
    body.append(f"{name}：", style=GOLD)
    body.append(f"「{line}」\n", style="italic " + PARCH)
    body.append(f"（羈絆「{bond}」)", style=FAINT)
    console.print(_panel(body, title="交談", style="green"))


def sheet_skooma(char: Character, state: GameState, gamedata: GameData) -> None:
    from tesrpg.systems import skooma
    add = getattr(char, "skooma_addiction", 0)
    high = skooma.is_high(char, state)
    remain = max(0, getattr(char, "skooma_high_until", 0) - state.time.absolute_hours()) if high else 0
    step = skooma.withdrawal_step(char, state)
    if high:
        phase = f"🌙 亢奮中(尚餘 {remain} 小時)"
    elif step > 0:
        phase = f"💀 戒斷中(階 {step}/{skooma.WITHDRAWAL_MAX_STEPS})"
    elif add > 0:
        phase = "清醒(殘癮未消;持續清醒會慢慢戒掉)"
    else:
        phase = "未沾染月糖"
    layers = (("attrs", "屬性", char.skooma_attr_bonus),
              ("skills", "技能", char.skooma_skill_bonus))
    note = "(亢奮短而戒斷長;追藥越深、越久未用藥越痛。清醒夠久可自行戒除,或行淨糖之儀解癮)"
    if _web is not None:
        rows = [_ln(phase, "magenta" if high else ("red" if step else "muted")),
                _kv("成癮度", f"{add} / 上限 {skooma.MAX_ADDICTION}(門檻 {skooma.WITHDRAWAL_THRESHOLD})")]
        for cat, label, d in layers:
            if d:
                rows.append(_kv(label, "、".join(f"{_tr_bonus(cat, k, gamedata)}{v:+d}" for k, v in d.items())))
        rows.append(_ln(note, "faint"))
        _emit_panel("斯庫瑪/月糖狀態", rows)
        return
    body = Text()
    body.append(phase + "\n", style="bold magenta" if high else ("bold red" if step else INK))
    body.append("成癮度  ", style=GOLD)
    body.append(f"{add} / 上限 {skooma.MAX_ADDICTION}(戒斷門檻 {skooma.WITHDRAWAL_THRESHOLD})\n", style=PARCH)
    for cat, label, d in layers:
        if d:
            body.append(f"{label}  ", style=GOLD)
            body.append("、".join(f"{_tr_bonus(cat, k, gamedata)}{v:+d}" for k, v in d.items())
                        + "\n", style=PARCH)
    body.append(note, style=FAINT)
    console.print(_panel(body, title="斯庫瑪/月糖狀態"))


def sheet_skill_detail(char: Character, gamedata: GameData, skill_id: str) -> None:
    sd = gamedata.skills[skill_id]
    eff, base = char.skill(skill_id), char.base_skill(skill_id)
    if _web is not None:
        rows = [_hd(f"{sd['name']}（{formulas.SPEC_NAMES.get(sd['spec'], sd['spec'])}）　等級 {eff}"
                    + (f"(基礎 {base})" if eff != base else ""))]
        if char.is_major_skill(skill_id):
            rows.append(_ln("✦ 主修技能(升點給 ×1.5 等級經驗)", "magenta"))
        if sd.get("desc"):
            rows.append(_ln(sd["desc"], "muted"))
        if sd.get("mechanic"):
            rows.append(_kv("作用", sd["mechanic"]))
        need = formulas.skill_threshold(base)
        cur = char.skill_xp.get(skill_id, 0.0)
        pct = int(cur / need * 100) if need > 0 else 0
        rows.append(_kv("熟練進度", f"{pct}%（{cur:.1f}/{need:.1f} → {base + 1} 級)"))
        nxt = mastery.next_threshold(char, gamedata, skill_id)
        if nxt:
            rows.append(_ln(f"下一里程碑　{nxt['name']}（{nxt['threshold']} 級,還差 {nxt['remaining']}）", "faint"))
        p = sd.get("practice", {})
        if p:
            rows.append(_kv("練習成本", f"體力 {p.get('fatigue', '?')} · {p.get('hours', '?')} 小時 · "
                                       f"+{p.get('xp', 0):.2f} xp(體力不足時 xp 減半)"))
        _emit_panel("技能詳情", rows)
        return
    body = Text()
    body.append(f"{sd['name']}（{formulas.SPEC_NAMES.get(sd['spec'], sd['spec'])}）", style=f"bold {GOLD}")
    body.append(f"   等級 {eff}" + (f"(基礎 {base})" if eff != base else "") + "\n", style=PARCH)
    if char.is_major_skill(skill_id):
        body.append("✦ 主修技能(升點給 ×1.5 等級經驗)\n", style="bold magenta")
    if sd.get("desc"):
        body.append(sd["desc"] + "\n", style=INK)
    if sd.get("mechanic"):
        body.append("作用  ", style=GOLD)
        body.append(sd["mechanic"] + "\n", style=PARCH)
    need = formulas.skill_threshold(base)
    cur = char.skill_xp.get(skill_id, 0.0)
    pct = int(cur / need * 100) if need > 0 else 0
    body.append(f"熟練進度  {pct}%（{cur:.1f}/{need:.1f} → {base + 1} 級)\n", style=INK)
    nxt = mastery.next_threshold(char, gamedata, skill_id)
    if nxt:
        body.append(f"下一里程碑  {nxt['name']}（{nxt['threshold']} 級,還差 {nxt['remaining']}）\n", style=FAINT)
    p = sd.get("practice", {})       # 唯讀:直接讀靜態 practice 價碼(切勿呼叫 progression.practice_cost,它會扣體力)
    if p:
        body.append(f"練習成本  體力 {p.get('fatigue', '?')} · {p.get('hours', '?')} 小時 · "
                    f"+{p.get('xp', 0):.2f} xp(體力不足時 xp 減半)", style=INK)
    console.print(_panel(body, title="技能詳情"))


_SCHOOL_CN = {"destruction": "毀滅", "restoration": "復原", "alteration": "變化",
              "conjuration": "召喚", "illusion": "幻術", "mysticism": "神秘"}


def school_name(school: str) -> str:
    """法術學派英文 id → 繁中名(未知則原樣回傳)。"""
    return _SCHOOL_CN.get(school, school)


def spell_effect_summary(gamedata: GameData, spell_id: str) -> str:
    """把法術 effect 結構渲染成一行可讀「作用」(資料驅動,直接讀 effect 結構顯示基礎效果;
    施法者加成如達貢之佑增幅召喚不計入此基礎摘要)。"""
    sp = gamedata.spells[spell_id]
    e = sp["effect"]
    k = e["kind"]
    elem = _RESIST_CN.get(e.get("element"), "")
    mag = e.get("magnitude", 0)
    turns = e.get("turns", 0)
    tgt = sp.get("target")
    ally_p = "群體" if tgt == "allies" else ""              # 群體前綴
    ally_who = "同伴" if tgt in ("ally", "allies") else ""   # 對同伴

    def _st(st: dict) -> str:
        s = st.get("status")
        el = _RESIST_CN.get(st.get("element"), "")
        m = st.get("magnitude", 0)
        t = st.get("turns", 0)
        return {"dot": f"{el}持續傷害 {m}/回合×{t}", "regen": f"再生 +{m}/回合×{t}",
                "paralyze": f"麻痺 {t} 回合", "fear": f"恐懼 {t} 回合",
                "soul_trap": f"擒魂 {t} 回合"}.get(s, "狀態")

    if k == "damage":
        return f"{elem}傷害 {mag}"
    if k == "damage_status":
        return f"{elem}傷害 {mag} + {_st(e['status'])}"
    if k == "damage_all":
        return f"全體{elem}傷害 {mag}"
    if k == "damage_status_all":
        return f"全體{elem}傷害 {mag} + {_st(e['status'])}"
    if k == "heal":
        return f"{ally_p}治療{ally_who} +{mag}"
    if k == "shield":
        return f"{ally_who}護盾 +{mag}（{turns} 回合)"
    if k == "weapon_imbue":   # 戰法師奧術灌注
        return f"兵刃附{elem} +{mag}/擊（{turns} 回合)"
    if k == "empower":        # 騎士號令
        return f"{ally_p}鼓舞{ally_who}攻擊 +{round(mag * 100)}%（{turns} 回合)"
    if k == "restore_fatigue":
        return f"回復體力 +{mag}"
    if k == "fear":
        return f"使目標恐懼（{turns} 回合)"
    if k == "weaken":
        return f"削弱目標攻擊 {round(mag * 100)}%（{turns} 回合)"
    if k == "soul_trap":
        return f"擒魂:死亡時捕獲靈魂（{turns} 回合)"
    if k == "summon":
        cn = gamedata.bestiary.get(e.get("creature"), {}).get("name", e.get("creature", ""))
        return f"召喚 {cn}（{turns} 回合)"
    if k == "bound_weapon":   # 召喚束縛兵刃
        return f"束縛兵刃:傷害 {mag},無視護甲（{turns} 回合)"
    if k == "ward":           # 秘術結界
        ab = "・吸魔" if e.get("absorb") else ""
        return f"結界:吸收法術傷害 {mag}{ab}（{turns} 回合)"
    if k == "dispel":         # 秘術驅散
        return "驅散自身的恐懼/麻痺/侵蝕等不良效果"
    if k == "reanimate":      # 召喚亡者復生
        return f"復生一具敵屍為盟友（{turns} 回合)"
    if k == "apply_status":
        who = "使目標" if tgt == "enemy" else (ally_who or "自身")
        return who + _st(e["status"])
    if k == "status_all":
        return f"全體{_st(e['status'])}"
    return "效果"


def sheet_spellbook(char: Character, gamedata: GameData) -> None:
    """法術書:已習法術依學派分組,逐道顯示魔耗 + 作用(資料驅動的效果摘要)。"""
    from tesrpg.systems import magic
    known = [s for s in char.spells if s in gamedata.spells]
    if _web is not None:
        bs: dict[str, list[str]] = {}
        for sid in known:
            bs.setdefault(gamedata.spells[sid]["school"], []).append(sid)
        schools = []
        for school in ("destruction", "restoration", "alteration", "conjuration", "illusion", "mysticism"):
            ids = bs.get(school)
            if not ids:
                continue
            schools.append({"key": school, "name": _SCHOOL_CN.get(school, school),
                            "spells": [{"name": gamedata.spells[sid]["name"],
                                        "cost": magic.effective_cost(char, gamedata, sid),
                                        "effect": spell_effect_summary(gamedata, sid)} for sid in ids]})
        _emit_view("spellbook", {"schools": schools})
        return
    if not known:
        console.print(_panel(Text("你還沒學會任何法術。", style=INK), title="法術書"))
        return
    by_school: dict[str, list[str]] = {}
    for sid in known:
        by_school.setdefault(gamedata.spells[sid]["school"], []).append(sid)
    body = Text()
    for school in ("destruction", "restoration", "alteration", "conjuration", "illusion", "mysticism"):
        ids = by_school.get(school)
        if not ids:
            continue
        body.append(f"{_SCHOOL_CN.get(school, school)}\n", style=f"bold {GOLD}")
        for sid in ids:
            sp = gamedata.spells[sid]
            body.append(f"  {sp['name']}", style=PARCH)
            body.append(f"（{magic.effective_cost(char, gamedata, sid)} 魔力)", style=INK)
            body.append(f"  {spell_effect_summary(gamedata, sid)}\n", style=FAINT)
    console.print(_panel(body, title="法術書"))


# --- 事件訊息 -----------------------------------------------------------
def show_events(events: list[dict], gamedata: GameData) -> None:
    for ev in events:
        if ev["type"] == "skill_up":
            m = f"[bold green]↑ {gamedata.skill_name(ev['skill'])} 提升到 {ev['level']}![/]"
        elif ev["type"] == "level_ready":
            m = "[bold yellow]★ 你感到脫胎換骨 —— 可以升級了!（選單選「升級」）[/]"
        elif ev["type"] == "mastery_choice_ready":
            if ev.get("single"):     # 退化節點(單一 perk 自動授予)→ 措辭為「習得」,不誤導去做不存在的二選一
                m = (f"[bold magenta]✦ 你的{gamedata.skill_name(ev['skill'])}已臻新境({ev['threshold']})"
                     f" —— 回城或升級時將習得里程碑「{ev.get('name', '')}」![/]")
            else:
                m = (f"[bold magenta]✦ 你的{gamedata.skill_name(ev['skill'])}已臻新境({ev['threshold']})"
                     f" —— 回到城鎮或升級時可擇一里程碑![/]")
        else:
            continue
        if _web is not None:
            _emit_log(m)
        else:
            console.print("  " + m)


def message(text: str, style: str = "white") -> None:
    if _web is not None:
        _emit_log(f"[{style}]{text}[/]")
        return
    console.print(f"  [{style}]{text}[/]")


def event_panel(event: dict) -> None:
    if _web is not None:
        _emit_view("event", {"title": event["title"], "text": event["text"]})
        return
    console.print(_panel(Text(event["text"], style=PARCH),
                         title=f"✦ {event['title']}", style="magenta"))


def landmark_discovery(res: dict) -> None:
    """首次抵達某地的『發現』:意境文字 + 一次性獎勵(systems.landmarks.discover 回傳)。"""
    if _web is not None:
        _emit_view("discovery", {"name": res["name"], "text": res["text"],
                                 "rewards": res.get("reward_lines", [])})
        return
    body = Text()
    body.append(res["text"] + "\n", style=PARCH)
    for line in res.get("reward_lines", []):
        body.append(f"  {line}\n", style="green")
    console.print(_panel(body, title=f"✦ 發現:{res['name']}", style=GOLD))


def legacy_screen(s: dict) -> None:
    """一生傳奇總結畫面(英雄級結算)。"""
    if _web is not None:
        _emit_view("legacy", _legacy_view(s))
        return
    head = "⚰  傳 奇 落 幕" if s["ending"] == "death" else "🌅  功 成 身 退"
    title = Text(justify="center")
    title.append(f"{s['name']}\n", style=f"bold {GOLD}")
    title.append(f"{s['race']} · {s['sex']} · {s['birthsign']} · {s['class']}\n", style=PARCH)
    title.append(f"{s['playstyle']}", style="cyan")

    body = Table.grid(padding=(0, 3))
    body.add_column(justify="right", style=GOLD)
    body.add_column(style=PARCH)
    if s.get("origin"):
        body.add_row("出身", str(s["origin"]))
    if s.get("condition"):
        body.add_row("詛咒", str(s["condition"]))
    if s.get("lycanthropy"):
        body.add_row("獸血", str(s["lycanthropy"]))
    if s.get("comrade"):
        body.add_row("羈絆", str(s["comrade"]))
    if s.get("loyalty"):
        body.add_row("忠誠", str(s["loyalty"]))
    if s.get("dark_deeds"):
        body.add_row("血業", str(s["dark_deeds"]))
    if s.get("dominion"):
        body.add_row("功業", str(s["dominion"]))
    if s.get("masteries"):
        body.add_row("精通", "、".join(s["masteries"]))
    body.add_row("等級", str(s["level"]))
    body.add_row("在世", f"{s['years']} 年 {s['days']} 天")
    body.add_row("足跡", f"踏遍 {s['places_visited']}/{s['total_locations']} 處地點")
    if s.get("total_landmarks"):
        body.add_row("奇景", f"尋得 {s.get('landmarks_found', 0)}/{s['total_landmarks']} 處具名地標")
    body.add_row("地城", f"肅清 {s['dungeons_cleared']} 座")
    body.add_row("任務", f"完成 {s['quests_completed']} 件")
    body.add_row("斬獲", f"擊殺 {s['total_kills']} 敵")
    if s["factions"]:
        body.add_row("公會", "、".join(f"{n}「{r}」" for n, r in s["factions"]))
    body.add_row("聲望", f"{s['fame']}" + (f"  惡名 {s['infamy']}" if s["infamy"] else ""))
    body.add_row("財富", f"{s['gold']} 金" + (f"  通緝 {s['bounty']}" if s["bounty"] else ""))
    if s.get("achievements"):
        body.add_row("成就", f"{len(s['achievements'])}/{s.get('achievements_total', len(s['achievements']))}  "
                            + "、".join(s["achievements"]))
    if s.get("seed") is not None:
        body.add_row("種子", str(s["seed"]))

    skills = "  ".join(f"{n} {lv}" for n, lv in s["top_skills"])

    score = Text(justify="center")
    score.append("✦ 傳 奇 分 數 ✦\n", style=GOLD_DIM)
    score.append(str(s["score"]), style=f"bold {GOLD}")
    score.append(f"\n「{s['title']}」", style="bold magenta")

    console.print(Align.center(_panel(
        Group(title, Rule(style=GOLD_DIM),
              Align.center(body), Text(),
              Text(f"最高技能:{skills}", style=INK, justify="center"),
              Rule(style=GOLD_DIM), score),
        title=head, box_=HERO, padding=(1, 4), width=58)))


# --- 戰鬥 ---------------------------------------------------------------
def _temper_suffix(char: Character, item_id: str) -> str:
    """已淬鍊裝備的「·淬+N」小標(武器行/角色卡穿戴行顯示;未淬鍊或舊存檔→空)。"""
    lvl = max(getattr(char, "weapon_temper", {}).get(item_id, 0),
              getattr(char, "armor_temper", {}).get(item_id, 0))
    return f" ·淬+{lvl}" if lvl else ""


def weapon_line(char: Character, gamedata: GameData) -> str:
    wp = gamedata.item_or_none(char.weapon)
    if wp is None:                       # 毀損/未知武器 id → 顯示原 id,不崩潰(防毀損存檔)
        return f"{char.weapon}(未知武器)"
    cond = "" if char.weapon == "fists" else f" 耐久{int(char.weapon_condition)}%"
    poison = ""
    if char.weapon_poison:
        poison = f" [green]· 塗毒:{char.weapon_poison['name']}×{char.weapon_poison['charges']}[/]"
    arch = _ARCHETYPE_CN.get(wp.get("archetype"), "")
    arch_tag = f"·{arch}" if arch and char.weapon != "fists" else ""
    from tesrpg.systems import inventory
    dual = (f" [bold red]· 雙持 {gamedata.item(char.offhand)['name']}[/]"
            if inventory.is_dual_wielding(char, gamedata) else "")
    return (f"{wp['name']}（{gamedata.skill_name(wp['skill'])} {char.skill(wp['skill'])}"
            f"{arch_tag}{cond})" + _temper_suffix(char, char.weapon) + poison + dual)


def combat_intro(creature, player: Character, gamedata: GameData) -> None:
    if _web is not None:
        _emit_view("encounter", {"name": creature.name,
                                 "flavor": creature.flavor or f"你遇上了{creature.name}!"})
        return
    console.print(_panel(
        Text(creature.flavor or f"你遇上了{creature.name}!", style=PARCH),
        title=f"⚔ 遭遇:{creature.name}", style="red", box_=box.HEAVY))


def combat_status(player: Character, creature, gamedata: GameData) -> None:
    if _web is not None:
        _emit_view("combat", _combat_view(player, [], [creature]))
        return
    grid = Table.grid(padding=(0, 2))
    grid.add_row(Text(player.name, style="bold"), _bar(player.health, player.max_health, "red"),
                 Text("體力", style="green"), _bar(player.fatigue, player.max_fatigue, "green", 10))
    grid.add_row(Text(creature.name, style="bold red"),
                 _bar(creature.health, creature.max_health, "red"), Text(""), Text(""))
    console.print(grid)


_STATUS_TAG = {"shield": "盾", "dot": "蝕", "fear": "懼", "paralyze": "痺",
               "weaken": "弱", "soul_trap": "魂", "regen": "生", "stagger": "踉"}
_BUFF_KINDS = {"shield", "regen"}   # 增益(綠);其餘 _STATUS_TAG 條目=減益(紅);未知=中性


def _status_tags(entity) -> str:
    tags = []
    for e in entity.active_effects:
        if e.get("turns", 0) <= 0:
            continue
        tags.append(f"{_STATUS_TAG.get(e['kind'], e['kind'])}{e['turns']}")
    return " ".join(tags)


def combat_status_group(player: Character, allies: list, enemies: list, gamedata: GameData) -> None:
    """團隊/多敵戰鬥狀態:我方(玩家+同伴)在上,敵方在下(編號供指定目標)。"""
    if _web is not None:
        _emit_view("combat", _combat_view(player, allies, enemies))
        return
    side = Table.grid(padding=(0, 2))
    side.add_row(Text(player.name, style="bold"), _bar(player.health, player.max_health, "red"),
                 Text("體力", style="green"), _bar(player.fatigue, player.max_fatigue, "green", 10),
                 Text(_status_tags(player), style="cyan"))
    for a in allies:
        if a.health > 0:
            side.add_row(Text("└ " + a.name, style="cyan"), _bar(a.health, a.max_health, "cyan"),
                         Text(""), Text(""), Text(_status_tags(a), style="cyan"))
    console.print(side)
    console.print(Rule("[bold red]⚔ VS ⚔[/]", style="red", characters="─"))
    foes = Table.grid(padding=(0, 2))
    n = 0
    for e in enemies:
        if e.health > 0:
            n += 1
            foes.add_row(Text(f"{n}. {e.name}", style="bold red"),
                         _bar(e.health, e.max_health, "red"),
                         Text(_status_tags(e), style="magenta"))
        else:
            foes.add_row(Text(f"   {e.name}(已倒下)", style="grey42"), Text(""), Text(""))
    console.print(foes)


LOC_TYPE_NAME = {"city": "大城", "town": "城鎮", "dungeon": "地城", "wilderness": "荒野"}


def location_panel(char: Character, gamedata: GameData, brief: bool = False) -> None:
    if _web is not None:
        _emit_view("location", _location_view(char, gamedata, brief))
        return
    loc = gamedata.location(char.location_id)
    body = Text()
    body.append(loc["desc"] + "\n", style=PARCH)
    from tesrpg.systems import landmarks    # 局部匯入避免循環
    lm = gamedata.landmark_at(char.location_id)   # 已發現的具名地標 → 標記(未發現則此地看來尋常)
    if lm and landmarks.is_discovered(char, char.location_id):
        body.append("❖ 已發現  ", style=GOLD)
        body.append(lm["name"] + "\n", style=PARCH)
        if lm.get("revisit"):
            body.append(lm["revisit"] + "\n", style=FAINT)
    ruler = gamedata.ruler_at(char.location_id)
    if ruler:
        body.append("👑 統治者  ", style=GOLD)
        body.append(f"{ruler['title']}·{ruler['name']}", style=PARCH)
        body.append("（大空位·自治)\n", style=FAINT)
        from tesrpg.systems import politics    # 局部匯入避免循環;旗號=大義·正史陣營
        fac = politics.stance_label(politics.faction_of(char, gamedata, char.location_id))
        bloc = ruler.get("bloc_label")
        body.append("🏴 旗號  ", style=GOLD)
        body.append(f"{fac}·{bloc}\n" if bloc else f"{fac}\n", style=PARCH)
    exits = loc.get("links", {})
    if exits:
        body.append("出口  ", style=GOLD)
        body.append("　".join(
            f"{gamedata.location(d)['name']}（{h}時）" for d, h in exits.items()), style=INK)
    danger = loc.get("danger", 0)
    dtag = "" if danger == 0 else f"  [red]⚠危險度 {danger}[/]"
    console.print(_panel(
        body,
        title=f"📍 {loc['name']} · {loc['province']}"
              f"（{LOC_TYPE_NAME.get(loc['type'], loc['type'])}）{dtag}"))


def item_label(gamedata: GameData, char: Character, item_id: str, qty: int = 1) -> str:
    d = gamedata.item(item_id)
    tag = ""
    if char.weapon == item_id:
        tag = " [yellow](手持)[/]"
    elif item_id in char.equipped.values():
        tag = " [green](穿戴)[/]"
    extra = ""
    if d["kind"] == "weapon":
        arch = _ARCHETYPE_CN.get(d.get("archetype"), "")
        extra = f" 傷害{d['damage']}/{gamedata.skill_name(d['skill'])}" + (f"/{arch}" if arch else "")
    elif d["kind"] == "armor":
        extra = f" 護甲{d['armor_rating']}/{d['slot']}"
    elif d["kind"] == "jewelry":
        extra = " 飾品"
        ench = d.get("enchant")
        if ench:
            extra += "·已附魔"
    qtystr = f" ×{qty}" if qty > 1 else ""
    return f"{d['name']}{qtystr}（{d['weight']:g}斤{extra}){tag}"


def inventory_panel(char: Character, gamedata: GameData) -> None:
    if _web is not None:
        _emit_view("inventory", _inventory_view(char, gamedata))
        return
    from tesrpg.systems import inventory as inv
    if not char.inventory:
        console.print(_panel(f"[{INK}]背包空空如也。[/]", title="🎒 背包"))
        return
    tbl = Table(box=None, pad_edge=False)
    tbl.add_column("物品", style=PARCH)
    order = {"weapon": 0, "armor": 1, "potion": 2, "misc": 3}
    stacks = sorted(char.inventory, key=lambda s: order.get(gamedata.item(s["id"])["kind"], 9))
    for s in stacks:
        tbl.add_row(item_label(gamedata, char, s["id"], s["qty"]))
    w = inv.total_weight(char, gamedata)
    mx = inv.max_weight(char, gamedata)
    over = " [red]超重![/]" if w > mx else ""
    foot = Text()
    foot.append(f"負重 {w:g}/{mx}", style=GOLD if w <= mx else "red")
    foot.append(over, style="")
    foot.append(f"   金幣 {char.gold}", style=GOLD)
    console.print(_panel(Group(tbl, Rule(style=GOLD_DIM), foot), title="🎒 背包"))


def _emit_or_print(markup: str) -> None:
    if _web is not None:
        _emit_log(markup)
    else:
        console.print("  " + markup)


def loot_report(result: dict, gamedata: GameData) -> None:
    lines = []
    if result.get("gold"):
        lines.append(f"[yellow]獲得 {result['gold']} 枚金幣。[/]")
    for item_id, qty in result.get("items", []):
        q = f" ×{qty}" if qty > 1 else ""
        lines.append(f"[green]拾得 {gamedata.item_name(item_id)}{q}。[/]")
    if not lines:
        lines.append("[grey62]沒有任何收穫。[/]")
    for m in lines:
        _emit_or_print(m)


def guild_panel(char: Character, gamedata: GameData, faction_id: str) -> None:
    if _web is not None:
        _emit_view("guild", _guild_view(char, gamedata, faction_id))
        return
    from tesrpg.systems import factions
    f = gamedata.factions[faction_id]
    gate = factions.gate_level(char, gamedata, faction_id)
    body = Text()
    body.append(f["blurb"] + "\n\n", style=PARCH)

    if factions.is_member(char, faction_id):
        body.append("你的階級  ", style=GOLD)
        body.append(factions.rank_name(char, gamedata, faction_id) + "\n", style=f"bold {PARCH}")
        perk = factions.perk_desc(char, gamedata, faction_id)
        if perk:
            body.append("會員福利  ", style=GOLD)
            body.append(perk + "\n", style="green")
        reason = factions.advance_block_reason(char, gamedata, faction_id)
        body.append("晉升      ", style=GOLD)
        body.append((reason or "已可接取下一階晉升任務") + "\n",
                    style=INK if reason else "cyan")
    else:
        body.append("入會條件  ", style=GOLD)
        body.append(f"{factions.gate_skill_names(gamedata, faction_id)} 任一達 "
                    f"{f.get('join_skill', 0)}(你目前 {gate})\n", style=INK)
        if f.get("rivals"):
            rn = "、".join(gamedata.factions[r]["name"] for r in f["rivals"])
            body.append("敵對公會  ", style=GOLD)
            body.append(rn + "\n", style=INK)
        reason = factions.join_block_reason(char, gamedata, faction_id)
        body.append(reason or "你已符合入會資格,可申請加入。",
                    style="yellow" if reason else "cyan")
    console.print(_panel(body, title=f"🏛 {f['name']}"))


def quest_log(char: Character, gamedata: GameData) -> None:
    if _web is not None:
        _emit_view("quests", _quests_view(char, gamedata))
        return
    from rich.console import Group
    if not char.quests:
        console.print(_panel(f"[{INK}]目前沒有進行中的任務。[/]", title="📜 任務日誌"))
    else:
        v = _quests_view(char, gamedata)
        parts = []
        for g in v["groups"]:
            t = Text()
            t.append(g["title"] + "\n", style=f"bold {GOLD}")
            for q in g["quests"]:
                head = f"〔{q['faction']}〕{q['name']}" if q.get("faction") else q["name"]
                t.append(f"  {head}  ", style=f"bold {PARCH}")
                t.append(f"({q['stage'][0]}/{q['stage'][1]})\n", style=INK)
                for s in q["stages"]:
                    mark, st = (("✔", FAINT) if s["state"] == "done"
                                else ("▶", "cyan") if s["state"] == "cur" else ("·", INK))
                    t.append(f"      {mark} {s['text']}\n", style=st)
            parts.append(t)
        console.print(_panel(Group(*parts), title="📜 任務日誌"))
    if char.completed_quests:
        console.print(f"  [{FAINT}]已完成 {len(char.completed_quests)} 件委託。[/]")


def npc_panel(npc: dict, disposition: int, greeting: str | None = None) -> None:
    line = greeting or npc["greeting"]      # 條件式對話:依 attitude 的動態問候(預設用 NPC 既有 greeting)
    if _web is not None:
        _emit_view("npc", {"name": npc["name"], "greeting": line,
                           "rumor": npc.get("rumor"), "disposition": disposition,
                           "hearts": disposition // 10})
        return
    body = Text()
    body.append(line + "\n", style="italic " + PARCH)
    if npc.get("rumor"):       # 在地傳聞:指向同省的地城/野外/奇景(細化省分)
        body.append("傳聞:" + npc["rumor"] + "\n", style="grey62")
    body.append("\n")
    filled = disposition // 10
    body.append("好感 ", style=INK)
    body.append("♥" * filled, style="red")
    body.append("·" * (10 - filled), style="grey37")
    body.append(f" {disposition}/100", style=INK)
    console.print(_panel(body, title=f"💬 {npc['name']}", style="green"))


def court_panel(ruler: dict, gamedata: GameData, reception: str,
                standing: int | None = None, thane: bool = False,
                politics: dict | None = None, territory: dict | None = None) -> None:
    """謁見領主:接待語氣 + 考據背景 + 種族/駐軍/時局/政治立場,並顯示功勳/武士身分(領主區)。
    territory 給定時(你親手攻下的城)額外顯示「你的領地」:居民稅/駐軍維護/民心/淨收。"""
    if _web is not None:
        _emit_view("court", _court_view(ruler, gamedata, reception, standing, thane, politics, territory))
        return
    race = gamedata.races.get(ruler["race"], {}).get("name", ruler["race"])
    body = Text()
    body.append(reception + "\n\n", style="italic " + PARCH)
    body.append(ruler["blurb"] + "\n\n", style=PARCH)
    body.append("種族  ", style=GOLD)
    body.append(f"{race}\n", style=INK)
    body.append("駐軍  ", style=GOLD)
    body.append(f"{(politics or {}).get('garrison', ruler['garrison'])} 兵\n", style=INK)
    if ruler.get("bloc_label"):
        body.append("旗號  ", style=GOLD)
        body.append(f"{ruler['bloc_label']}\n", style=INK)
    if politics:
        body.append("立場  ", style=GOLD)
        body.append(f"{politics['stance']} · 與你 {politics['relation']}\n", style=INK)
    body.append("時局  ", style=GOLD)
    body.append("大空位 · 各城自治(紅寶石王座空懸)", style=FAINT)
    if thane:
        body.append("\n✦ ", style=GOLD)
        body.append("你是本城武士,享領地禮遇", style="bold " + GOLD)
    elif standing is not None:
        body.append("\n城邦功勳  ", style=GOLD)
        body.append(f"{standing}", style=INK)
    if territory:
        body.append("\n\n【你的領地】\n", style="bold " + GOLD)
        body.append("居民  ", style=GOLD)
        body.append(f"{territory['population']} 口 → 週稅 {territory['tax']} 金\n", style=INK)
        body.append("駐軍  ", style=GOLD)
        body.append(f"{territory['garrison']}/{territory['base']}(維護 {territory['maint']} 金/週)\n", style=INK)
        if territory["unrest"]:
            body.append("民心  ", style=GOLD)
            body.append("浮動 —— 稅收中斷,速加強駐軍回防!", style="bold red")
        else:
            body.append("淨收  ", style=GOLD)
            body.append(f"{territory['net']:+d} 金/週", style="green" if territory["net"] >= 0 else "red")
    console.print(_panel(body, title=f"👑 {ruler['title']}·{ruler['name']}", style=GOLD))


def territory_panel(rows: list[dict], gamedata: GameData, gold: int) -> None:
    """領地總覽:一覽所有親手攻下的城(階段四)。rows = politics.territory_overview 結果清單。"""
    if _web is not None:
        _emit_view("territory", _territory_view(rows, gamedata, gold))
        return
    tbl = Table(box=box.SIMPLE_HEAD, pad_edge=False, padding=(0, 1),
                border_style=GOLD_DIM, expand=True)
    for h in ("城邦", "居民", "週稅", "駐軍", "維護", "淨收", "民心", "下次徵稅"):
        tbl.add_column(h, header_style=f"bold {GOLD}", style=PARCH)
    for r in rows:
        name = gamedata.location(r["loc"])["name"]
        cd = r["countdown"]
        cd_s = "—" if cd is None else f"{cd // 24}天{cd % 24}時"
        if r["unrest"]:
            heart, net_s = "[red]浮動[/]", "[red]稅斷[/]"
            gar = f"[red]{r['garrison']}/{r['base']}[/]"
        else:
            heart = "[green]安定[/]"
            net_s = f"[{'green' if r['net'] >= 0 else 'red'}]{r['net']:+d}[/]"
            gar = f"{r['garrison']}/{r['base']}"
        tbl.add_row(name, str(r["population"]), str(r["tax"]), gar,
                    str(r["maint"]), net_s, heart, cd_s)
    console.print(_panel(Group(tbl, Rule(style=GOLD_DIM),
                               Text(f"金庫 {gold} 金", style=GOLD)),
                         title="🏰 領地總覽", style=GOLD))


_DUNGEON_ICON = {"stairs": "↓", "boss": "✦", "entrance": "◊"}   # 結構格:已探即恆顯
_DUNGEON_CONTENT_ICON = {"monster": "!", "container": "$", "trap": "^"}  # 內容格:已探「未結算」才顯(偵查揭示用)
_DUNGEON_LEGEND = "@你  ✦首領  ↓樓梯  ◊入口  !敵  $寶  ^阱  ·已探  ?未探"


def dungeon_grid(grid: dict, z: int, cx: int, cy: int, explored: list, resolved: list | None = None) -> None:
    """格子地城小地圖 + 當前層;迷霧:未探 ?,已探顯示型別圖示。雙端渲染。
    resolved(可選):已結算(清空)的內容格顯示 ·,未結算的顯示內容圖示(怪/寶/陷阱)→ 偵查揭示有資訊量。"""
    from tesrpg.systems import dungeoncrawl
    n, m = grid["n"], grid["m"]
    adj = {(nx, ny): "go:" + k for k, _l, nx, ny in dungeoncrawl.neighbors(grid, cx, cy)}
    rows = []
    for yy in range(n):
        row = []
        for xx in range(n):
            t = grid["layers"][z][yy][xx]["type"]
            ex = bool(explored[z][yy][xx])
            cur = (xx == cx and yy == cy)
            done = bool(resolved[z][yy][xx]) if resolved is not None else False
            if cur:
                icon = "@"
            elif not ex:
                icon = "?"
            elif t in _DUNGEON_ICON:                       # 樓梯/首領/入口:結構格,恆顯
                icon = _DUNGEON_ICON[t]
            elif t in _DUNGEON_CONTENT_ICON and not done:  # 怪/寶/陷阱:未結算(偵查揭示或未踏入)→ 顯內容
                icon = _DUNGEON_CONTENT_ICON[t]
            else:
                icon = "·"                                 # 已結算/空格 → 純已探
            row.append({"icon": icon, "explored": ex, "current": cur,
                        "type": t, "move": adj.get((xx, yy))})
        rows.append(row)
    if _web is not None:
        _emit_view("dungeon_grid", {"name": grid["name"], "n": n, "layer": z + 1, "layers": m,
                                    "pos": [cx, cy], "rows": rows, "legend": _DUNGEON_LEGEND})
        return
    body = Text("\n".join("   " + "  ".join(c["icon"] for c in row) for row in rows), style=PARCH)
    console.print(_panel(body, title=f"🗺 {grid['name']} · 第 {z + 1}/{m} 層 · 座標 ({cx},{cy})",
                         style="magenta"))
    console.print(Text("   " + _DUNGEON_LEGEND, style="grey50"))


_ELEM_CN = {"fire": "火焰", "frost": "冰霜", "shock": "雷電", "poison": "毒素", "magic": "魔法"}
_STAT_CN = {"health": "生命", "magicka": "魔力", "fatigue": "體力"}
_ARCHETYPE_CN = {"dagger": "匕首", "sword": "劍", "blunt": "鈍器", "bow": "弓",
                 "staff": "法杖", "hand_to_hand": "徒手"}


def combat_event(ev: dict, gamedata: GameData) -> None:
    lines = []
    if ev.get("absorbed"):
        lines.append(f"[bold cyan]{ev['defender']} 吸收了來襲的魔法,化為魔力![/]")
    elif ev["hit"]:
        blk = "(被格擋)" if ev["blocked"] else ""
        if ev.get("sneak"):
            lines.append(f"[bold magenta]🗡 偷襲![/] [white]{ev['attacker']}[/] 自暗處突襲 "
                         f"[white]{ev['defender']}[/],致命一擊造成 "
                         f"[bold red]{ev['damage']}[/] 傷害(×{ev['sneak']:.1f}){blk}")
        else:
            lines.append(f"[white]{ev['attacker']}[/] 命中 [white]{ev['defender']}[/]"
                         f",造成 [bold red]{ev['damage']}[/] 傷害{blk}")
    else:
        sneak_miss = "[magenta](偷襲落空!)[/] " if ev.get("sneak") else ""
        lines.append(f"{sneak_miss}[grey62]{ev['attacker']} 的攻擊被 {ev['defender']} 閃過了。[/]")
    if ev.get("status_applied"):
        if ev["status_applied"] == "paralyze":
            lines.append(f"[magenta]{ev['defender']} 被兵刃上的符文震懾,僵立當場(麻痺)![/]")
        else:
            lines.append(f"[magenta]{ev['defender']} 中了{_ELEM_CN.get(ev['status_applied'], '異常')}![/]")
    if ev.get("poison_applied"):
        lines.append(f"[green]武器上的{ev['poison_applied']}滲入了{ev['defender']}的傷口![/]")
    if ev.get("lifesteal"):
        lines.append(f"[red]🩸 兵刃汲血,{ev['attacker']} 回復了 {ev['lifesteal']} 點生命。[/]")
    if ev.get("aftermath"):
        am = ev["aftermath"]
        bits = []
        if am.get("staggered"):
            bits.append("陣腳大亂(這一擊更難命中你)")
        if am.get("bleed"):
            bits.append(f"傷口撕裂(每回合 {am['bleed']} 傷)")
        if bits:
            lines.append(f"[magenta]🩸 暗殺殘響 —— {ev['defender']}{'、'.join(bits)}![/]")
    if ev.get("self_restored"):
        stat, amt = ev["self_restored"]
        lines.append(f"[cyan]法杖將生機回流,{_STAT_CN.get(stat, stat)} +{amt}。[/]")
    for m in lines:
        _emit_or_print(m)
    show_events(ev.get("skill_events", []), gamedata)


def combat_tick(messages: list) -> None:
    for m in messages:
        _emit_or_print(f"[magenta]{m}[/]")


def ally_event(ev: dict) -> None:
    _emit_or_print(f"[magenta]{ev['name']}[/] 撲向敵人,造成 [bold red]{ev['damage']}[/] 傷害"
                   if ev["hit"] else f"[grey62]{ev['name']} 的攻擊落空了。[/]")


def active_effects_line(player: Character, creature) -> None:
    tags = []
    from tesrpg.systems import magic
    sh = magic.active_shield(player)
    if sh:
        tags.append(f"[cyan]護盾+{sh}[/]")
    for e in creature.active_effects:
        if e["turns"] <= 0:
            continue
        if e["kind"] == "fear":
            tags.append(f"[blue]{creature.name}·恐懼{e['turns']}[/]")
        elif e["kind"] == "weaken":
            tags.append(f"[blue]{creature.name}·耗弱{e['turns']}[/]")
        elif e["kind"] == "soul_trap":
            tags.append(f"[magenta]{creature.name}·擒魂{e['turns']}[/]")
    if tags:
        _emit_or_print("狀態:" + "  ".join(tags))


def rule(title: str = "") -> None:
    if _web is not None:
        _emit_view("divider", {"title": title})
        return
    console.rule(title, style="grey37")


# --- 選單 / 輸入 --------------------------------------------------------
def grouped_menu(title: str, groups: list, extra_keys: list | None = None,
                 cta_keys: list | None = None) -> str:
    """分組顯示的編號選單(連續編號、依分類加小標),回傳選中的 key。

    groups: [(分類名, [(key, 顯示文字), ...]), ...];空分類自動略過。
    extra_keys:額外合法但不渲染成按鈕的 key(web:供可點內容列 submit,如地點出口 go:dest)。
    """
    if _web is not None:
        g = [{"header": header, "options": [{"key": k, "label": _plain(lbl)} for k, lbl in opts]}
             for header, opts in groups if opts]
        return _web_prompt({"type": "grouped", "title": title or "", "groups": g,
                            "extra_keys": list(extra_keys or []),
                            "cta_keys": list(cta_keys or [])})
    if title:
        console.print(f"\n[bold {GOLD}]❖ {title}[/]")
    flat: list[str] = []
    blocks = []
    for header, opts in groups:
        if not opts:
            continue
        blk = Text()
        blk.append(f"{header}\n", style=f"bold {GOLD_DIM}")
        for key, label in opts:
            flat.append(key)
            blk.append(f"{len(flat):>2}", style=GOLD)
            blk.append(" ", style=FAINT)
            blk.append(f"{label}\n", style=PARCH)
        blocks.append(blk)
    # 分組區塊並排成多欄,避免長選單塞滿整個畫面
    console.print(Columns(blocks, padding=(0, 4), equal=False, column_first=True))
    while True:
        n = IntPrompt.ask("  請選擇", default=1)
        if 1 <= n <= len(flat):
            return flat[n - 1]
        console.print("[red]  無效的選項[/]")


_SERVICE_CN = {"inn": "宿", "merchant": "商", "trainer": "訓", "mages_guild": "法",
               "fighters_guild": "戰", "thieves_guild": "盜", "armorer": "鐵", "task_board": "板"}
_MAP_ICON = {"city": "◆", "town": "◇", "dungeon": "✦", "wilderness": "·"}


def world_map(char: Character, gamedata: GameData) -> None:
    """資料驅動的 Tamriel 地圖:依行省分組,標出當前位置、危險度、服務與出口。"""
    if _web is not None:
        _emit_view("map", _map_view(char, gamedata))
        return
    locs = gamedata.world["locations"]
    by_prov: dict[str, list[str]] = {}
    order: list[str] = []
    for lid, loc in locs.items():
        p = loc["province"]
        by_prov.setdefault(p, []).append(lid)
        if p not in order:
            order.append(p)

    from tesrpg.systems import landmarks, politics    # 局部匯入避免循環;標每城現時大義 + 已發現地標
    _FAC_MARK = {"imperial": "[red]帝[/]", "independent": "[cyan]獨[/]",
                 "neutral": "[grey62]中[/]", "daedric": "[magenta]湮[/]", "own": "[gold1]己[/]"}
    tree = Tree(f"[bold {GOLD}]Tamriel · 泰姆瑞爾[/]", guide_style=GOLD_DIM)
    for prov in order:
        pb = tree.add(f"[bold cyan]{prov}[/]")
        for lid in by_prov[prov]:
            loc = locs[lid]
            here = lid == char.location_id
            visited = lid in char.visited_locations
            icon = _MAP_ICON.get(loc["type"], "·")
            style = "bold green" if here else ("white" if visited else "grey42")
            star = "★ " if here else ("" if visited else "[grey42]?[/] ")
            danger = f" [red]⚠{loc['danger']}[/]" if loc.get("danger") else ""
            svc = "·".join(_SERVICE_CN[s] for s in loc.get("services", []) if s in _SERVICE_CN)
            svc = f" [grey46]({svc})[/]" if svc else ""
            fac = "" if not gamedata.ruler_at(lid) else (
                "[bold gold1]★己[/]" if lid in char.city_faction
                else _FAC_MARK.get(politics.faction_of(char, gamedata, lid), ""))
            fac = f" {fac}" if fac else ""
            lm = " [gold1]❖[/]" if (gamedata.landmark_at(lid)        # ❖=已發現地標(避開 ✦=地城圖示)
                                    and landmarks.is_discovered(char, lid)) else ""
            node = pb.add(f"{star}{icon} [{style}]{loc['name']}[/]"
                          f"[grey50]·{LOC_TYPE_NAME.get(loc['type'], '')}[/]{danger}{fac}{lm}{svc}")
            exits = loc.get("links", {})
            if exits:
                ex = "、".join(f"{locs[d]['name']}{h}時" for d, h in exits.items())
                node.add(f"[grey42]→ {ex}[/]")
    legend = (f"[{FAINT}]★=所在 ◆城 ◇鎮 ✦地城 ·荒野 ❖已發現地標 ⚠危險度 ?未到訪"
              "  服務:宿商訓法戰盜鐵板[/]")
    console.print(_panel(Group(tree, Rule(style=GOLD_DIM), Text.from_markup(legend)),
                         title="🗺 世界地圖"))


def menu(title: str, options: list[tuple], allow_back: bool = False) -> str | None:
    """顯示編號選單,回傳選中的 key;allow_back 時 0 回傳 None。

    options: [(key, 顯示文字), ...] 或 [(key, 顯示文字, chips), ...]
      chips(選用)= [{"text": 文字, "tone": 色調}, ...] —— web 渲成選項下的數值小標;
      終端版串成淡色行內後綴。
    """
    if _web is not None:
        opts = []
        for opt in options:
            o = {"key": opt[0], "label": _plain(opt[1])}
            if len(opt) > 2 and opt[2]:
                o["chips"] = opt[2]
            opts.append(o)
        spec = {"type": "menu", "title": title or "", "allow_back": bool(allow_back), "options": opts}
        return _web_prompt(spec)
    if title:
        console.print(f"\n[bold {GOLD}]❖ {title}[/]")
    for i, opt in enumerate(options, 1):
        label = opt[1]
        if len(opt) > 2 and opt[2]:
            label = f"{label}  [{FAINT}]{'  '.join(c['text'] for c in opt[2])}[/]"
        console.print(f"  [{GOLD}]{i:>2}[/][{FAINT}].[/] {label}")
    if allow_back:
        console.print(f"  [{GOLD}] 0[/][{FAINT}].[/] [{INK}]返回[/]")
    lo = 0 if allow_back else 1
    while True:
        n = IntPrompt.ask("  請選擇", default=lo)
        if allow_back and n == 0:
            return None
        if 1 <= n <= len(options):
            return options[n - 1][0]
        console.print("[red]  無效的選項[/]")


def ask_text(prompt: str, default: str | None = None) -> str:
    if _web is not None:
        return _web_prompt({"type": "text", "prompt": prompt, "default": default})
    return Prompt.ask(f"  {prompt}", default=default)


def ask_int(prompt: str, default: int, lo: int, hi: int) -> int:
    if _web is not None:
        return _web_prompt({"type": "int", "prompt": prompt,
                            "default": default, "lo": lo, "hi": hi})
    while True:
        n = IntPrompt.ask(f"  {prompt}", default=default)
        if lo <= n <= hi:
            return n
        console.print(f"[red]  請輸入 {lo}–{hi} 之間[/]")


def confirm(prompt: str) -> bool:
    if _web is not None:
        return _web_prompt({"type": "confirm", "prompt": prompt})
    return Prompt.ask(f"  {prompt} [y/n]", choices=["y", "n"], default="n") == "y"
