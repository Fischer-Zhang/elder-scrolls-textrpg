"""rich 終端渲染與輸入。

把所有 print / prompt 收斂在這層,規則邏輯不直接碰 IO。
"""

from __future__ import annotations

from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.state import GameState

console = Console()

SPEC_COLOR = {"combat": "red", "magic": "cyan", "stealth": "green"}
RESOURCE_STYLE = {"health": "red", "magicka": "cyan", "fatigue": "green"}


# --- 基本元件 -----------------------------------------------------------
def banner() -> None:
    console.print(Panel.fit(
        Text("流  亡  者", justify="center", style="bold yellow"),
        subtitle="上古卷軸風格 · 技能驅動沙盒文字 RPG",
        border_style="yellow",
    ))


def _bar(cur: float, mx: float, color: str, width: int = 16) -> Text:
    mx = max(1, mx)
    filled = int(round(width * max(0, min(cur, mx)) / mx))
    t = Text()
    t.append("█" * filled, style=color)
    t.append("░" * (width - filled), style="grey37")
    t.append(f" {int(cur)}/{int(mx)}", style="white")
    return t


def status_line(state: GameState) -> None:
    """行動之間的精簡狀態列。"""
    c = state.player
    t = Text()
    t.append(f"{c.name}", style="bold")
    t.append(f"  Lv.{c.level}", style="yellow")
    t.append(f"  ⏿ {state.time.label()}", style="grey70")
    console.print(t)
    grid = Table.grid(padding=(0, 2))
    grid.add_row(
        Text("生命", style="red"), _bar(c.health, c.max_health, "red"),
        Text("魔力", style="cyan"), _bar(c.magicka, c.max_magicka, "cyan"),
        Text("體力", style="green"), _bar(c.fatigue, c.max_fatigue, "green"),
    )
    console.print(grid)
    extra = []
    if c.fame:
        extra.append(f"[cyan]聲望 {c.fame}[/]")
    total_bounty = sum(c.bounties.values())
    if total_bounty:
        extra.append(f"[red]通緝 {total_bounty}[/]")
    if extra:
        console.print("  " + "  ".join(extra))
    if c.can_level_up():
        console.print("  [bold yellow]★ 可以升級了![/]")


# --- 角色卡 -------------------------------------------------------------
def character_sheet(char: Character, gamedata: GameData) -> None:
    race = gamedata.races[char.race]["name"]
    sign = gamedata.birthsigns[char.birthsign]["name"]
    cls = ("自訂" if char.class_id == "custom"
           else gamedata.classes[char.class_id]["name"])
    sex = "男" if char.sex == "male" else "女"
    spec = formulas.SPEC_NAMES.get(char.specialization, char.specialization)

    header = Text()
    header.append(f"{char.name}\n", style="bold yellow")
    header.append(f"{race} · {sex} · {sign} · {cls}（{spec}專精）\n", style="white")
    header.append(f"等級 {char.level}", style="yellow")
    header.append(f"   升級進度 {char.level_progress}/{formulas.LEVELUP_MAJOR_SKILLUPS} 主修升點",
                  style="grey70")

    # 資源
    res = Table.grid(padding=(0, 2))
    res.add_row(Text("生命", style="red"), _bar(char.health, char.max_health, "red"))
    res.add_row(Text("魔力", style="cyan"), _bar(char.magicka, char.max_magicka, "cyan"))
    res.add_row(Text("體力", style="green"), _bar(char.fatigue, char.max_fatigue, "green"))
    res.add_row(Text("負重", style="yellow"),
                Text(f"上限 {formulas.max_encumbrance(char.attr('strength'))}", style="grey70"))
    res.add_row(Text("金幣", style="yellow"), Text(str(char.gold), style="white"))
    res.add_row(Text("武器", style="yellow"), Text(weapon_line(char, gamedata), style="white"))

    # 屬性
    attr_tbl = Table(title="屬性", title_style="bold", box=None, pad_edge=False)
    attr_tbl.add_column("", style="grey70")
    attr_tbl.add_column("", justify="right")
    attr_tbl.add_column("", style="grey70")
    attr_tbl.add_column("", justify="right")
    items = [(k, formulas.ATTRIBUTE_NAMES[k], char.attr(k)) for k in formulas.ATTRIBUTES]
    for i in range(0, len(items), 2):
        left = items[i]
        right = items[i + 1] if i + 1 < len(items) else ("", "", "")
        fav_l = "★" if left[0] in char.favored_attributes else " "
        fav_r = "★" if right and right[0] in char.favored_attributes else " "
        attr_tbl.add_row(f"{fav_l}{left[1]}", str(left[2]),
                         (f"{fav_r}{right[1]}" if right[1] else ""),
                         (str(right[2]) if right[1] else ""))

    console.print(Panel(Group(header, Text(), Columns([res, attr_tbl], padding=(0, 6))),
                        border_style="yellow"))
    skill_table(char, gamedata)


def skill_table(char: Character, gamedata: GameData) -> None:
    cols = []
    for spec in ("combat", "magic", "stealth"):
        tbl = Table(title=formulas.SPEC_NAMES[spec], title_style=f"bold {SPEC_COLOR[spec]}",
                    box=None, pad_edge=False)
        tbl.add_column("技能")
        tbl.add_column("", justify="right")
        for sid in gamedata.skills_by_spec(spec):
            name = gamedata.skill_name(sid)
            lvl = char.skill(sid)
            star = "[yellow]✦[/]" if char.is_major_skill(sid) else " "
            tbl.add_row(f"{star} {name}", f"[bold]{lvl}[/]")
        cols.append(tbl)
    console.print(Columns(cols, padding=(0, 4), equal=True))
    console.print("[grey50]✦ = 主修技能(升點計入升級);右欄為技能等級[/]")


# --- 事件訊息 -----------------------------------------------------------
def show_events(events: list[dict], gamedata: GameData) -> None:
    for ev in events:
        if ev["type"] == "skill_up":
            name = gamedata.skill_name(ev["skill"])
            console.print(f"  [bold green]↑ {name} 提升到 {ev['level']}![/]")
        elif ev["type"] == "level_ready":
            console.print("  [bold yellow]★ 你感到脫胎換骨 —— 可以升級了!（選單選「升級」）[/]")


def message(text: str, style: str = "white") -> None:
    console.print(f"  [{style}]{text}[/]")


def event_panel(event: dict) -> None:
    console.print(Panel(Text(event["text"], style="white"),
                        title=f"✦ {event['title']}", border_style="magenta"))


def legacy_screen(s: dict) -> None:
    """一生傳奇總結畫面。"""
    head = "⚰ 傳奇落幕" if s["ending"] == "death" else "🌅 功成身退"
    title = Text()
    title.append(f"{s['name']}\n", style="bold yellow")
    title.append(f"{s['race']} · {s['sex']} · {s['birthsign']} · {s['class']}\n", style="white")
    title.append(f"{s['playstyle']}", style="cyan")

    body = Table.grid(padding=(0, 3))
    body.add_column(justify="right", style="grey70")
    body.add_column(style="white")
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

    skills = "  ".join(f"{n} {lv}" for n, lv in s["top_skills"])

    score = Text()
    score.append("傳奇分數  ", style="grey70")
    score.append(str(s["score"]), style="bold yellow")
    score.append(f"\n「{s['title']}」", style="bold magenta")

    console.print(Panel(Group(title, Text(), body, Text(),
                              Text(f"最高技能:{skills}", style="grey70"), Text(), score),
                        title=head, border_style="yellow", padding=(1, 4)))


# --- 戰鬥 ---------------------------------------------------------------
def weapon_line(char: Character, gamedata: GameData) -> str:
    wp = gamedata.item(char.weapon)
    cond = "" if char.weapon == "fists" else f" 耐久{int(char.weapon_condition)}%"
    poison = ""
    if char.weapon_poison:
        poison = f" [green]· 塗毒:{char.weapon_poison['name']}×{char.weapon_poison['charges']}[/]"
    return f"{wp['name']}（{gamedata.skill_name(wp['skill'])} {char.skill(wp['skill'])}{cond})" + poison


def combat_intro(creature, player: Character, gamedata: GameData) -> None:
    console.print(Panel(
        Text(creature.flavor or f"你遇上了{creature.name}!", style="white"),
        title=f"⚔ 遭遇:{creature.name}", border_style="red"))


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
    console.print("  [grey50]──── VS ────[/]")
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
    body.append(loc["desc"] + "\n\n", style="white")
    exits = loc.get("links", {})
    if exits:
        body.append("出口:", style="grey70")
        body.append("、".join(
            f"{gamedata.location(d)['name']}({h}時)" for d, h in exits.items()), style="grey70")
    danger = loc.get("danger", 0)
    dtag = "" if danger == 0 else f"  危險度 {danger}"
    console.print(Panel(
        body,
        title=f"📍 {loc['name']} · {loc['province']}({LOC_TYPE_NAME.get(loc['type'], loc['type'])}){dtag}",
        border_style="cyan"))


def item_label(gamedata: GameData, char: Character, item_id: str, qty: int = 1) -> str:
    d = gamedata.item(item_id)
    tag = ""
    if char.weapon == item_id:
        tag = " [yellow](手持)[/]"
    elif item_id in char.equipped.values():
        tag = " [green](穿戴)[/]"
    extra = ""
    if d["kind"] == "weapon":
        extra = f" 傷害{d['damage']}/{gamedata.skill_name(d['skill'])}"
    elif d["kind"] == "armor":
        extra = f" 護甲{d['armor_rating']}/{d['slot']}"
    qtystr = f" ×{qty}" if qty > 1 else ""
    return f"{d['name']}{qtystr}（{d['weight']:g}斤{extra}){tag}"


def inventory_panel(char: Character, gamedata: GameData) -> None:
    from tesrpg.systems import inventory as inv
    if not char.inventory:
        console.print(Panel("背包空空如也。", title="🎒 背包", border_style="yellow"))
        return
    tbl = Table(box=None, pad_edge=False)
    tbl.add_column("物品")
    order = {"weapon": 0, "armor": 1, "potion": 2, "misc": 3}
    stacks = sorted(char.inventory, key=lambda s: order.get(gamedata.item(s["id"])["kind"], 9))
    for s in stacks:
        tbl.add_row(item_label(gamedata, char, s["id"], s["qty"]))
    w = inv.total_weight(char, gamedata)
    mx = inv.max_weight(char)
    over = "[red](超重!)[/]" if w > mx else ""
    foot = Text(f"負重 {w:g}/{mx}  {('' if not over else '超重!')}  金幣 {char.gold}",
                style="yellow")
    console.print(Panel(Group(tbl, foot), title="🎒 背包", border_style="yellow"))


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
    body = Text()
    body.append(f["blurb"] + "\n\n", style="white")
    if factions.is_member(char, faction_id):
        body.append(f"你的階級:{factions.rank_name(char, gamedata, faction_id)}", style="yellow")
    else:
        body.append("你尚未加入此公會。", style="grey70")
    console.print(Panel(body, title=f"🏛 {f['name']}", border_style="cyan"))


def quest_log(char: Character, gamedata: GameData) -> None:
    from tesrpg.systems import quests
    if not char.quests:
        console.print(Panel("目前沒有進行中的任務。", title="📜 任務日誌", border_style="yellow"))
    else:
        tbl = Table(box=None, pad_edge=False)
        tbl.add_column("任務")
        tbl.add_column("目標")
        for qid in char.quests:
            q = gamedata.quests[qid]
            fac = f"[{gamedata.factions[q['faction']]['name']}] " if q.get("faction") else ""
            tbl.add_row(f"{fac}{q['name']}", quests.objective_text(char, gamedata, qid))
        console.print(Panel(tbl, title="📜 任務日誌", border_style="yellow"))
    if char.completed_quests:
        console.print(f"  [grey62]已完成 {len(char.completed_quests)} 件委託。[/]")


def npc_panel(npc: dict, disposition: int) -> None:
    body = Text()
    body.append(npc["greeting"] + "\n\n", style="italic white")
    filled = disposition // 10
    body.append("好感 ", style="grey70")
    body.append("♥" * filled, style="red")
    body.append("·" * (10 - filled), style="grey37")
    body.append(f" {disposition}/100", style="grey70")
    console.print(Panel(body, title=f"💬 {npc['name']}", border_style="green"))


def dungeon_room(name: str, idx: int, total: int, desc: str, is_boss: bool = False) -> None:
    tag = "首領" if is_boss else f"第 {idx}/{total} 室"
    console.print(Panel(Text(desc, style="white"),
                        title=f"🏚 {name} · {tag}",
                        border_style="magenta" if is_boss else "blue"))


_ELEM_CN = {"fire": "火焰", "frost": "冰霜", "shock": "雷電", "poison": "毒素", "magic": "魔法"}


def combat_event(ev: dict, gamedata: GameData) -> None:
    if ev.get("absorbed"):
        console.print(f"  [bold cyan]{ev['defender']} 吸收了來襲的魔法,化為魔力![/]")
    elif ev["hit"]:
        blk = "(被格擋)" if ev["blocked"] else ""
        console.print(f"  [white]{ev['attacker']}[/] 命中 [white]{ev['defender']}[/]"
                      f",造成 [bold red]{ev['damage']}[/] 傷害{blk}")
    else:
        console.print(f"  [grey62]{ev['attacker']} 的攻擊被 {ev['defender']} 閃過了。[/]")
    if ev.get("status_applied"):
        console.print(f"  [magenta]{ev['defender']} 中了{_ELEM_CN.get(ev['status_applied'], '異常')}![/]")
    if ev.get("poison_applied"):
        console.print(f"  [green]武器上的{ev['poison_applied']}滲入了{ev['defender']}的傷口![/]")
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
        console.print(f"\n[bold]{title}[/]")
    flat: list[str] = []
    for header, opts in groups:
        if not opts:
            continue
        console.print(f"  [grey50]── {header} ──[/]")
        for key, label in opts:
            flat.append(key)
            console.print(f"   [yellow]{len(flat)}[/]. {label}")
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

    tree = Tree("[bold yellow]🗺  Tamriel 地圖[/]")
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
    console.print(tree)
    console.print("  [grey50]★=所在 ◆城 ◇鎮 ✦地城 ·荒野 ⚠危險度 ?未到訪"
                  "  服務:宿商訓法戰盜鐵板[/]")


def menu(title: str, options: list[tuple[str, str]], allow_back: bool = False) -> str | None:
    """顯示編號選單,回傳選中的 key;allow_back 時 0 回傳 None。

    options: [(key, 顯示文字), ...]
    """
    if title:
        console.print(f"\n[bold]{title}[/]")
    for i, (_key, label) in enumerate(options, 1):
        console.print(f"  [yellow]{i}[/]. {label}")
    if allow_back:
        console.print("  [yellow]0[/]. 返回")
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
