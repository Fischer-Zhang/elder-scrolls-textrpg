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
from tesrpg.systems import mastery

console = Console()

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


def status_line(state: GameState) -> None:
    """行動之間的精簡狀態列(金色頂欄分隔)。"""
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
    if c.can_level_up():
        console.print(f"  [bold {GOLD}]★ 可以升級了![/]")


# --- 角色卡 -------------------------------------------------------------
def character_sheet(char: Character, gamedata: GameData) -> None:
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
    res.add_row(Text("武器", style=GOLD), Text(weapon_line(char, gamedata), style=PARCH))

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

    console.print(_panel(Group(header, Rule(style=GOLD_DIM),
                               Columns([res, attr_tbl], padding=(0, 6)))))
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


# --- 事件訊息 -----------------------------------------------------------
def show_events(events: list[dict], gamedata: GameData) -> None:
    for ev in events:
        if ev["type"] == "skill_up":
            name = gamedata.skill_name(ev["skill"])
            console.print(f"  [bold green]↑ {name} 提升到 {ev['level']}![/]")
        elif ev["type"] == "level_ready":
            console.print("  [bold yellow]★ 你感到脫胎換骨 —— 可以升級了!（選單選「升級」）[/]")
        elif ev["type"] == "mastery_unlocked":
            console.print(f"  [bold magenta]✦ 技能里程碑「{ev['name']}」解鎖![/] [grey70]{ev['desc']}[/]")


def message(text: str, style: str = "white") -> None:
    console.print(f"  [{style}]{text}[/]")


def event_panel(event: dict) -> None:
    console.print(_panel(Text(event["text"], style=PARCH),
                         title=f"✦ {event['title']}", style="magenta"))


def legacy_screen(s: dict) -> None:
    """一生傳奇總結畫面(英雄級結算)。"""
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
    if s.get("dark_deeds"):
        body.add_row("血業", str(s["dark_deeds"]))
    if s.get("masteries"):
        body.add_row("精通", "、".join(s["masteries"]))
    body.add_row("等級", str(s["level"]))
    body.add_row("在世", f"{s['years']} 年 {s['days']} 天")
    body.add_row("足跡", f"踏遍 {s['places_visited']}/{s['total_locations']} 處地點")
    body.add_row("地城", f"肅清 {s['dungeons_cleared']} 座")
    body.add_row("任務", f"完成 {s['quests_completed']} 件")
    body.add_row("斬獲", f"擊殺 {s['total_kills']} 敵")
    if s["factions"]:
        body.add_row("公會", "、".join(f"{n}「{r}」" for n, r in s["factions"]))
    body.add_row("聲望", f"{s['fame']}" + (f"  惡名 {s['infamy']}" if s["infamy"] else ""))
    body.add_row("財富", f"{s['gold']} 金" + (f"  通緝 {s['bounty']}" if s["bounty"] else ""))
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
def weapon_line(char: Character, gamedata: GameData) -> str:
    wp = gamedata.item(char.weapon)
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
            f"{arch_tag}{cond})" + poison + dual)


def combat_intro(creature, player: Character, gamedata: GameData) -> None:
    console.print(_panel(
        Text(creature.flavor or f"你遇上了{creature.name}!", style=PARCH),
        title=f"⚔ 遭遇:{creature.name}", style="red", box_=box.HEAVY))


def combat_status(player: Character, creature, gamedata: GameData) -> None:
    grid = Table.grid(padding=(0, 2))
    grid.add_row(Text(player.name, style="bold"), _bar(player.health, player.max_health, "red"),
                 Text("體力", style="green"), _bar(player.fatigue, player.max_fatigue, "green", 10))
    grid.add_row(Text(creature.name, style="bold red"),
                 _bar(creature.health, creature.max_health, "red"), Text(""), Text(""))
    console.print(grid)


_STATUS_TAG = {"shield": "盾", "dot": "蝕", "fear": "懼", "paralyze": "痺",
               "weaken": "弱", "soul_trap": "魂", "regen": "生"}


def _status_tags(entity) -> str:
    tags = []
    for e in entity.active_effects:
        if e.get("turns", 0) <= 0:
            continue
        tags.append(f"{_STATUS_TAG.get(e['kind'], e['kind'])}{e['turns']}")
    return " ".join(tags)


def combat_status_group(player: Character, allies: list, enemies: list, gamedata: GameData) -> None:
    """團隊/多敵戰鬥狀態:我方(玩家+同伴)在上,敵方在下(編號供指定目標)。"""
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


def location_panel(char: Character, gamedata: GameData) -> None:
    loc = gamedata.location(char.location_id)
    body = Text()
    body.append(loc["desc"] + "\n", style=PARCH)
    ruler = gamedata.ruler_at(char.location_id)
    if ruler:
        body.append("👑 統治者  ", style=GOLD)
        body.append(f"{ruler['title']}·{ruler['name']}", style=PARCH)
        body.append("（大空位·自治)\n", style=FAINT)
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
    mx = inv.max_weight(char)
    over = " [red]超重![/]" if w > mx else ""
    foot = Text()
    foot.append(f"負重 {w:g}/{mx}", style=GOLD if w <= mx else "red")
    foot.append(over, style="")
    foot.append(f"   金幣 {char.gold}", style=GOLD)
    console.print(_panel(Group(tbl, Rule(style=GOLD_DIM), foot), title="🎒 背包"))


def loot_report(result: dict, gamedata: GameData) -> None:
    if result.get("gold"):
        console.print(f"  [yellow]獲得 {result['gold']} 枚金幣。[/]")
    for item_id, qty in result.get("items", []):
        q = f" ×{qty}" if qty > 1 else ""
        console.print(f"  [green]拾得 {gamedata.item_name(item_id)}{q}。[/]")
    if not result.get("gold") and not result.get("items"):
        console.print("  [grey62]沒有任何收穫。[/]")


def guild_panel(char: Character, gamedata: GameData, faction_id: str) -> None:
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
    from tesrpg.systems import quests
    if not char.quests:
        console.print(_panel(f"[{INK}]目前沒有進行中的任務。[/]", title="📜 任務日誌"))
    else:
        tbl = Table(box=None, pad_edge=False, padding=(0, 2))
        tbl.add_column("任務", style=f"bold {PARCH}")
        tbl.add_column("目標", style=INK)
        for qid in char.quests:
            q = gamedata.quests[qid]
            fac = f"[{GOLD_DIM}]〔{gamedata.factions[q['faction']]['name']}〕[/]" if q.get("faction") else ""
            tbl.add_row(f"{fac}{q['name']}", quests.objective_text(char, gamedata, qid))
        console.print(_panel(tbl, title="📜 任務日誌"))
    if char.completed_quests:
        console.print(f"  [{FAINT}]已完成 {len(char.completed_quests)} 件委託。[/]")


def npc_panel(npc: dict, disposition: int) -> None:
    body = Text()
    body.append(npc["greeting"] + "\n", style="italic " + PARCH)
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
                politics: dict | None = None) -> None:
    """謁見領主:接待語氣 + 考據背景 + 種族/駐軍/時局/政治立場,並顯示功勳/武士身分(領主區)。"""
    race = gamedata.races.get(ruler["race"], {}).get("name", ruler["race"])
    body = Text()
    body.append(reception + "\n\n", style="italic " + PARCH)
    body.append(ruler["blurb"] + "\n\n", style=PARCH)
    body.append("種族  ", style=GOLD)
    body.append(f"{race}\n", style=INK)
    body.append("駐軍  ", style=GOLD)
    body.append(f"{(politics or {}).get('garrison', ruler['garrison'])} 兵\n", style=INK)
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
    console.print(_panel(body, title=f"👑 {ruler['title']}·{ruler['name']}", style=GOLD))


def dungeon_room(name: str, idx: int, total: int, desc: str, is_boss: bool = False) -> None:
    tag = "✦ 首領 ✦" if is_boss else f"第 {idx}/{total} 室"
    console.print(_panel(Text(desc, style=PARCH),
                         title=f"🏚 {name} · {tag}",
                         style="magenta" if is_boss else "blue"))


_ELEM_CN = {"fire": "火焰", "frost": "冰霜", "shock": "雷電", "poison": "毒素", "magic": "魔法"}
_STAT_CN = {"health": "生命", "magicka": "魔力", "fatigue": "體力"}
_ARCHETYPE_CN = {"dagger": "匕首", "sword": "劍", "blunt": "鈍器", "bow": "弓",
                 "staff": "法杖", "hand_to_hand": "徒手"}


def combat_event(ev: dict, gamedata: GameData) -> None:
    if ev.get("absorbed"):
        console.print(f"  [bold cyan]{ev['defender']} 吸收了來襲的魔法,化為魔力![/]")
    elif ev["hit"]:
        blk = "(被格擋)" if ev["blocked"] else ""
        if ev.get("sneak"):
            console.print(f"  [bold magenta]🗡 偷襲![/] [white]{ev['attacker']}[/] 自暗處突襲 "
                          f"[white]{ev['defender']}[/],致命一擊造成 "
                          f"[bold red]{ev['damage']}[/] 傷害(×{ev['sneak']:.1f}){blk}")
        else:
            console.print(f"  [white]{ev['attacker']}[/] 命中 [white]{ev['defender']}[/]"
                          f",造成 [bold red]{ev['damage']}[/] 傷害{blk}")
    else:
        sneak_miss = "[magenta](偷襲落空!)[/] " if ev.get("sneak") else ""
        console.print(f"  {sneak_miss}[grey62]{ev['attacker']} 的攻擊被 {ev['defender']} 閃過了。[/]")
    if ev.get("status_applied"):
        console.print(f"  [magenta]{ev['defender']} 中了{_ELEM_CN.get(ev['status_applied'], '異常')}![/]")
    if ev.get("poison_applied"):
        console.print(f"  [green]武器上的{ev['poison_applied']}滲入了{ev['defender']}的傷口![/]")
    if ev.get("aftermath"):
        am = ev["aftermath"]
        bits = []
        if am.get("staggered"):
            bits.append("陣腳大亂(這一擊更難命中你)")
        if am.get("bleed"):
            bits.append(f"傷口撕裂(每回合 {am['bleed']} 傷)")
        if bits:
            console.print(f"  [magenta]🩸 暗殺殘響 —— {ev['defender']}{'、'.join(bits)}![/]")
    if ev.get("self_restored"):
        stat, amt = ev["self_restored"]
        console.print(f"  [cyan]法杖將生機回流,{_STAT_CN.get(stat, stat)} +{amt}。[/]")
    show_events(ev.get("skill_events", []), gamedata)


def combat_tick(messages: list) -> None:
    for m in messages:
        console.print(f"  [magenta]{m}[/]")


def ally_event(ev: dict) -> None:
    if ev["hit"]:
        console.print(f"  [magenta]{ev['name']}[/] 撲向敵人,造成 [bold red]{ev['damage']}[/] 傷害")
    else:
        console.print(f"  [grey62]{ev['name']} 的攻擊落空了。[/]")


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
        console.print("  狀態:" + "  ".join(tags))


def rule(title: str = "") -> None:
    console.rule(title, style="grey37")


# --- 選單 / 輸入 --------------------------------------------------------
def grouped_menu(title: str, groups: list) -> str:
    """分組顯示的編號選單(連續編號、依分類加小標),回傳選中的 key。

    groups: [(分類名, [(key, 顯示文字), ...]), ...];空分類自動略過。
    """
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
    locs = gamedata.world["locations"]
    by_prov: dict[str, list[str]] = {}
    order: list[str] = []
    for lid, loc in locs.items():
        p = loc["province"]
        by_prov.setdefault(p, []).append(lid)
        if p not in order:
            order.append(p)

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
            node = pb.add(f"{star}{icon} [{style}]{loc['name']}[/]"
                          f"[grey50]·{LOC_TYPE_NAME.get(loc['type'], '')}[/]{danger}{svc}")
            exits = loc.get("links", {})
            if exits:
                ex = "、".join(f"{locs[d]['name']}{h}時" for d, h in exits.items())
                node.add(f"[grey42]→ {ex}[/]")
    legend = (f"[{FAINT}]★=所在 ◆城 ◇鎮 ✦地城 ·荒野 ⚠危險度 ?未到訪"
              "  服務:宿商訓法戰盜鐵板[/]")
    console.print(_panel(Group(tree, Rule(style=GOLD_DIM), Text.from_markup(legend)),
                         title="🗺 世界地圖"))


def menu(title: str, options: list[tuple[str, str]], allow_back: bool = False) -> str | None:
    """顯示編號選單,回傳選中的 key;allow_back 時 0 回傳 None。

    options: [(key, 顯示文字), ...]
    """
    if title:
        console.print(f"\n[bold {GOLD}]❖ {title}[/]")
    for i, (_key, label) in enumerate(options, 1):
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
    return Prompt.ask(f"  {prompt}", default=default)


def ask_int(prompt: str, default: int, lo: int, hi: int) -> int:
    while True:
        n = IntPrompt.ask(f"  {prompt}", default=default)
        if lo <= n <= hi:
            return n
        console.print(f"[red]  請輸入 {lo}–{hi} 之間[/]")


def confirm(prompt: str) -> bool:
    return Prompt.ask(f"  {prompt} [y/n]", choices=["y", "n"], default="n") == "y"
