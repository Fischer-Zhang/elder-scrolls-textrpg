"""進入點與主行動迴圈(M1:練功場沙盒)。

目前可玩內容:創角 → 在練功場「做什麼練什麼」累積技能 → 升級選屬性 → 存讀檔。
戰鬥、世界探索、魔法製作、公會任務見 DESIGN.md 後續里程碑。
"""

from __future__ import annotations

from pathlib import Path

from tesrpg import creation, formulas
from tesrpg.gamedata import GameData, get_gamedata
from tesrpg.rng import RNG, make_seed
from tesrpg.state import GameState
from tesrpg.systems import (alchemy, brotherhood, combat, court, crafting, crime, dialogue, dungeon,
                            enchanting, events, factions, inventory, legacy, magic, politics, powers,
                            progression, quests, stats, vampirism, world)
from tesrpg.ui import console as ui

SAVE_PATH = Path.home() / ".tesrpg" / "save.json"


# ======================================================================
# 角色創建
# ======================================================================
def create_character(gamedata: GameData, rng: RNG):
    ui.rule("創建角色")
    if ui.confirm("快速開始(隨機種族/職業)?"):
        return _quick_character(gamedata, rng)

    sex = ui.menu("性別", [("male", "男"), ("female", "女")])

    race = ui.menu("種族", [
        (rid, f"{r['name']} — {r['ability']}")
        for rid, r in gamedata.races.items()
    ])

    sign = ui.menu("出生星座", [
        (sid, f"{s['name']} — {s['note']}")
        for sid, s in gamedata.birthsigns.items()
    ])

    class_opts = [(cid, f"{c['name']} — {c['desc']}") for cid, c in gamedata.classes.items()]
    class_opts.append(("custom", "自訂職業（選專精、偏好屬性、主修技能）"))
    class_id = ui.menu("職業", class_opts)
    custom = _create_custom_class(gamedata) if class_id == "custom" else None

    origin_id = ui.menu("開局背景(不一樣的人生)", [
        (oid, f"{o['name']} — {o['blurb']}") for oid, o in gamedata.origins.items()
    ])

    default_name = creation.random_name(gamedata, race, sex, rng)
    name = ui.ask_text("姓名", default=default_name)

    char = creation.build_character(
        gamedata, name=name, sex=sex, race=race, birthsign=sign,
        class_id=class_id, custom_class=custom, origin_id=origin_id, rng=rng,
    )
    ui.message(f"歡迎來到 Tamriel,{char.name}。", style="bold green")
    return char


def _quick_character(gamedata: GameData, rng: RNG):
    sex = rng.choice(["male", "female"])
    race = rng.choice(list(gamedata.races.keys()))
    sign = rng.choice(list(gamedata.birthsigns.keys()))
    class_id = rng.choice(list(gamedata.classes.keys()))
    origin_id = rng.choice(list(gamedata.origins.keys()))
    name = creation.random_name(gamedata, race, sex, rng)
    char = creation.build_character(
        gamedata, name=name, sex=sex, race=race, birthsign=sign, class_id=class_id,
        origin_id=origin_id, rng=rng,
    )
    ui.message(
        f"{name} —— {gamedata.races[race]['name']}·"
        f"{gamedata.birthsigns[sign]['name']}·{gamedata.classes[class_id]['name']}·"
        f"{gamedata.origins[origin_id]['name']}",
        style="bold green",
    )
    return char


def _create_custom_class(gamedata: GameData) -> dict:
    spec = ui.menu("專精", [(s, formulas.SPEC_NAMES[s]) for s in ("combat", "magic", "stealth")])
    ui.message("挑選 2 個偏好屬性:")
    favored = _pick_distinct(
        [(a, formulas.ATTRIBUTE_NAMES[a]) for a in formulas.ATTRIBUTES], 2, "偏好屬性")
    ui.message("挑選 7 個主修技能(升點給 ×1.5 等級經驗、起始較高):")
    skill_opts = [(sid, f"{s['name']}（{formulas.SPEC_NAMES[s['spec']]}）")
                  for sid, s in gamedata.skills.items()]
    majors = _pick_distinct(skill_opts, 7, "主修技能")
    return {"specialization": spec, "favored_attributes": favored, "major_skills": majors}


def _pick_distinct(options: list[tuple[str, str]], count: int, label: str) -> list[str]:
    chosen: list[str] = []
    remaining = list(options)
    for i in range(count):
        key = ui.menu(f"{label} ({i + 1}/{count})", remaining)
        chosen.append(key)
        remaining = [o for o in remaining if o[0] != key]
    return chosen


# ======================================================================
# 行動
# ======================================================================
def action_practice(state: GameState, gamedata: GameData) -> None:
    spec = ui.menu("要練哪一類?", [
        ("combat", "戰鬥技能"), ("magic", "魔法技能"), ("stealth", "潛行技能"),
    ], allow_back=True)
    if spec is None:
        return
    char = state.player
    opts = []
    for sid in gamedata.skills_by_spec(spec):
        s = gamedata.skills[sid]
        opts.append((sid, f"{s['name']} (Lv {char.skill(sid)}) — {s['practice']['label']}"))
    sid = ui.menu("練習哪項技能?", opts, allow_back=True)
    if sid is None:
        return

    pdef = gamedata.skills[sid]["practice"]
    xp, hours, tired = progression.practice_cost(char, gamedata, sid)
    events = progression.use_skill(char, gamedata, sid, xp)
    state.time.advance(hours)

    ui.message(f"你{pdef['label']}……（{hours} 小時)")
    if tired:
        ui.message("體力不濟,訓練成效減半。先休息會更有效率。", style="yellow")
    ui.show_events(events, gamedata)
    if not events:
        need = formulas.skill_threshold(char.skill(sid))
        prog = char.skill_xp.get(sid, 0.0)
        ui.message(f"{gamedata.skill_name(sid)} 熟練度 {prog:.1f}/{need:.1f} → 下一點",
                   style="grey70")


def action_rest(state: GameState, gamedata: GameData) -> str | None:
    hours = ui.ask_int("休息幾小時?", default=8, lo=1, hi=24)
    char = state.player
    no_magicka_regen = char.birthsign == "atronach"

    char.fatigue = min(char.max_fatigue, char.fatigue + char.max_fatigue * hours / 8)
    char.health = min(char.max_health, char.health + char.max_health * hours / 24)
    if not no_magicka_regen:
        char.magicka = min(char.max_magicka, char.magicka + char.max_magicka * hours / 12)

    state.time.advance(hours)
    ui.message(f"你休息了 {hours} 小時,神清氣爽。")
    if no_magicka_regen:
        ui.message("（巨魔像座:魔力不會自然回復,需靠吸收魔法補充。)", style="grey70")

    _maybe_db_recruit(state, gamedata)   # 血債在身者,夜母使者入夢招募

    return "dead" if maybe_event(state, gamedata, "rest") == "dead" else None


def _maybe_db_recruit(state: GameState, gamedata: GameData) -> None:
    """血債招募:謀殺過無辜者、尚未入會者,在睡夢中被黑暗兄弟會使者找上門。"""
    char = state.player
    if not brotherhood.should_recruit(char, gamedata):
        return
    ui.rule("夢中的訪客")
    ui.message("你自夢中驚醒 —— 床畔的暗影裡,一個兜帽身影端坐如石,聲音如墓中低語:", style="bold magenta")
    ui.message("「你奪人性命的手藝,夜母都看在眼裡。黑暗兄弟會……想請你入會。」", style="magenta")
    if ui.confirm("接受黑暗兄弟會的邀請、踏入暗影之中嗎?"):
        brotherhood.recruit(char)
        ui.message(f"「{brotherhood.SANCTUARY_PASSWORD_A}」—— 你已是兄弟會的『"
                   f"{brotherhood.rank_name(char, gamedata)}』。聖所之門,自此為你而開。",
                   style="bold green")
        ui.message("(在設有聖所的城市可找到『黑暗兄弟會』,接取與執行合約。)", style="grey70")
    else:
        brotherhood.decline_recruit(char)
        ui.message("兜帽身影微微頷首:「想清楚了,便來尋我們。聖所,設於海芬古與布魯瑪的暗處。」",
                   style="grey70")


def action_level_up(state: GameState, gamedata: GameData) -> None:
    char = state.player
    if not char.can_level_up():
        ui.message("還不能升級 —— 多練些技能累積等級經驗吧。", style="yellow")
        return

    ui.rule(f"升級 → Lv {char.level + 1}")

    # ① 三選一:強化哪條資源
    gains = formulas.LEVELUP_RESOURCE_GAIN
    resource = ui.menu("這一級要強化哪條資源?", [
        ("health", f"生命 +{gains['health']}"),
        ("magicka", f"魔力 +{gains['magicka']}"),
        ("fatigue", f"體力 +{gains['fatigue']}"),
    ])

    # ② 自由分配屬性點(逐點挑屬性,clamp 100;選到已滿的不耗點,重挑)
    points = formulas.LEVELUP_ATTRIBUTE_POINTS
    alloc: dict[str, int] = {}

    def _cur(a):   # 該屬性「含本次尚未送出的分配」的當前值
        return char.attr(a) + alloc.get(a, 0)

    ui.message(f"分配 {points} 點屬性(可集中或分散):", style="bold")
    remaining = points
    while remaining > 0:
        if all(_cur(a) >= formulas.ATTRIBUTE_CAP for a in formulas.ATTRIBUTES):
            break   # 八屬性全滿(極高等),無處可加
        opts = [(a, f"{formulas.ATTRIBUTE_NAMES[a]} {_cur(a)}"
                 + ("（已滿）" if _cur(a) >= formulas.ATTRIBUTE_CAP else ""))
                for a in formulas.ATTRIBUTES]
        a = ui.menu(f"剩 {remaining} 點 →", opts)
        if _cur(a) < formulas.ATTRIBUTE_CAP:
            alloc[a] = alloc.get(a, 0) + 1
            remaining -= 1

    summary = progression.apply_level_up(char, gamedata, alloc, resource)
    ui.message(f"★ 升級!現在是 Lv {summary['level']}。", style="bold yellow")
    for a, g in summary["attr_gains"].items():
        ui.message(f"  {formulas.ATTRIBUTE_NAMES[a]} +{g}", style="green")
    rname = {"health": "生命", "magicka": "魔力", "fatigue": "體力"}[summary["resource_choice"]]
    ui.message(f"  {rname}上限 +{summary['resource_gain']},三圍已回滿。", style="green")
    if summary["can_level_again"]:
        ui.message("  你還能再升一級!", style="yellow")


def action_save(state: GameState) -> None:
    state.save(SAVE_PATH)
    ui.message(f"已存檔 → {SAVE_PATH}", style="green")


# ======================================================================
# 戰鬥
# ======================================================================
def _choose_enemy_target(gamedata: GameData, enemies: list):
    """從存活敵人中選一個目標(僅一個時自動選)。"""
    alive = [e for e in enemies if combat.is_alive(e)]
    if len(alive) == 1:
        return alive[0]
    opts = [(str(i), f"{e.name}（{int(e.health)}/{e.max_health})") for i, e in enumerate(alive)]
    return alive[int(ui.menu("攻擊哪個目標?", opts))]


def _choose_combat_action(state: GameState, gamedata: GameData, enemies: list, vanish_used: int = 0):
    """回傳玩家本回合的行動 dict:{type, spell_id?, target?}。"""
    player = state.player
    opts = [("attack", f"攻擊（{gamedata.item(player.weapon)['name']})")]
    castable = [s for s in player.spells if magic.can_cast(player, gamedata, s)]
    if castable:
        opts.append(("cast", "施法"))
    if powers.usable_in(player, state, gamedata, "combat"):
        plabel = "吸血之力" if player.is_vampire else "星座之力"
        opts.append(("power", f"{plabel}({powers.power_def(powers.power_id(player, gamedata))['name']})"))
    if not inventory.is_dual_wielding(player, gamedata):   # 雙持占用雙手 → 不能格擋
        opts.append(("block", "格擋"))
    if combat.can_vanish(player) and vanish_used < formulas.MAX_VANISHES_PER_BATTLE:
        n_alive = len([e for e in enemies if combat.is_alive(e)])
        pct = int(combat.vanish_chance(player, n_alive, vanish_used) * 100)
        left = formulas.MAX_VANISHES_PER_BATTLE - vanish_used
        opts.append(("vanish", f"隱遁再襲（成功率 {pct}%,剩 {left} 次)"))
    opts.append(("flee", "逃跑"))
    choice = ui.menu("你的回合", opts)

    if choice == "attack":
        return {"type": "attack", "target": _choose_enemy_target(gamedata, enemies)}
    if choice == "cast":
        spell_opts = [(s, f"{gamedata.spells[s]['name']}"
                       f"（{magic.effective_cost(player, gamedata, s)} 魔力 · {gamedata.spells[s]['school']})")
                      for s in castable]
        sid = ui.menu("施放哪道法術?", spell_opts, allow_back=True)
        if sid is None:
            return _choose_combat_action(state, gamedata, enemies, vanish_used)
        target = _choose_enemy_target(gamedata, enemies) if gamedata.spells[sid]["target"] == "enemy" else None
        return {"type": "cast", "spell_id": sid, "target": target}
    if choice == "power":
        eff = powers.power_def(powers.power_id(player, gamedata))["effect"]
        needs_target = any(k in eff for k in ("paralyze", "poison", "drain"))
        target = _choose_enemy_target(gamedata, enemies) if needs_target else None
        return {"type": "power", "target": target}
    return {"type": choice}


def _prep_phase(state: GameState, gamedata: GameData, enemies, battle: dict, budget: int) -> None:
    """開戰前備戰(偵查掙得):花預算施增益/召喚(鎖高 scout)/喝藥/塗毒。

    增益走 active_effects(計時從第一回合 tick)、召喚 append battle["allies"](開場即在場、
    免去首回合施法),皆不持久、戰後隨 run_battle 出口 clear,無存檔影響、不送永久強度。
    同一法術每場備戰不可重施(避免零成本疊滿同一護盾)。"""
    player = state.player
    SELF_BUFF = ("heal", "shield", "restore_fatigue", "apply_status")
    ui.rule("備戰")
    ui.message(f"你搶得先機、從容布置 —— 可進行 {budget} 個準備。", style="bold green")
    cast_done: set[str] = set()
    while budget > 0:
        buffs = [s for s in player.spells
                 if gamedata.spells[s]["target"] == "self"
                 and gamedata.spells[s]["effect"]["kind"] in SELF_BUFF
                 and s not in cast_done and magic.can_cast(player, gamedata, s)]
        summons = [s for s in player.spells
                   if gamedata.spells[s]["effect"]["kind"] == "summon"
                   and s not in cast_done and magic.can_cast(player, gamedata, s)] \
            if player.skill("scout") >= formulas.PREP_SUMMON_MIN_SCOUT else []
        potions = list(dict.fromkeys(
            s["id"] for s in player.inventory if gamedata.item(s["id"]).get("kind") == "potion"))
        poisons = list(dict.fromkeys(
            s["id"] for s in player.inventory if gamedata.item(s["id"]).get("kind") == "poison"))
        opts = []
        if buffs:
            opts.append(("buff", "施放增益法術"))
        if summons:
            opts.append(("summon", "召喚助戰"))
        if potions:
            opts.append(("potion", "喝藥水"))
        if poisons and player.weapon != "fists":
            opts.append(("coat", "武器塗毒"))
        if not opts:
            ui.message("沒有可進行的備戰了。", style="grey70")
            break
        ui.message(f"(剩餘備戰 {budget})", style="grey62")
        choice = ui.menu("備戰", opts, allow_back=True)
        if choice is None:
            break
        spent = False
        if choice in ("buff", "summon"):
            pool = buffs if choice == "buff" else summons
            sid = ui.menu("施放哪道法術?",
                          [(s, f"{gamedata.spells[s]['name']}（{magic.effective_cost(player, gamedata, s)} 魔力)")
                           for s in pool], allow_back=True)
            if sid is not None:
                res = magic.cast(player, gamedata, sid, state.rng, battle=battle)
                ui.message(res["message"], style="cyan")
                ui.show_events(res.get("skill_events", []), gamedata)
                cast_done.add(sid)
                spent = True
        elif choice == "potion":
            pid = ui.menu("喝哪瓶?",
                          [(p, f"{gamedata.item_name(p)} ×{inventory.count_item(player, p)}") for p in potions],
                          allow_back=True)
            if pid is not None:
                ui.message(inventory.use_item(player, gamedata, pid) or "你飲下藥水。", style="green")
                spent = True
        elif choice == "coat":
            pid = ui.menu("塗哪瓶毒?",
                          [(p, f"{gamedata.item_name(p)} ×{inventory.count_item(player, p)}") for p in poisons],
                          allow_back=True)
            if pid is not None and inventory.coat_weapon(player, gamedata, pid):
                ui.message(f"你把{gamedata.item_name(pid)}抹上了刃口。", style="green")
                spent = True
        if spent:
            budget -= 1
    stats.clamp_resources(player)


def run_battle(state: GameState, gamedata: GameData, enemies, companions=None,
               alerted: bool = False, prep_budget: int = 0) -> str:
    """團隊/多敵回合制戰鬥。階段制回合:玩家 → 同伴 → 敵人 → 結算。

    enemies:敵方 Creature 清單(也接受單一 Creature)。companions 未指定時用玩家隊伍。
    回傳 'victory' / 'fled' / 'dead'。
    """
    player = state.player
    if not isinstance(enemies, list):
        enemies = [enemies]
    party = player.companions if companions is None else companions
    party = [cid for cid in party if cid in gamedata.companions]   # 略過已不存在的同伴(存檔前向相容)
    battle = {"allies": [combat.spawn_companion(gamedata, cid, state.rng) for cid in party]}
    trapped_kills: set[int] = set()
    opening = not alerted   # 開場偷襲:首個攻擊吃潛行加成;若敵人已警覺(撤退失敗)則無
    vanishes_done = 0  # 本場已成功隱遁次數(成功率遞減,防無限風箏)

    # active_effects 是「戰鬥內」臨時效果 —— 進場先清,杜絕戰鬥外施法(如里程碑「聖光·溢盾」)
    # 殘留的護盾/效果洩漏進本場。必須在 _prep_phase「之前」清(備戰施放的增益在清除後才套用,照常保留)。
    player.active_effects.clear()

    # 偵查掙得的開戰前備戰空間:在第一個交戰回合「之前」進行(opening 因此保留;
    # buff/召喚的計時從第一回合照 tick,故不延長時效、只省下開場那一動)。
    if prep_budget > 0:
        _prep_phase(state, gamedata, enemies, battle, prep_budget)

    def alive_e():
        return [e for e in enemies if combat.is_alive(e)]

    def note_trap(e):
        if not combat.is_alive(e) and magic.has_soul_trap(e):
            trapped_kills.add(id(e))

    while combat.is_alive(player) and alive_e():
        ui.combat_status_group(player, battle["allies"], enemies, gamedata)
        action = _choose_combat_action(state, gamedata, enemies, vanishes_done)
        blocking = action["type"] == "block"
        vanish_success = False        # 本回合是否成功隱遁(成功 → 重置偷襲 + 跳過敵人階段)

        # ---- 玩家階段 ----
        if action["type"] == "flee":
            foe = max(alive_e(), key=lambda e: e.speed)
            if combat.try_flee(player, foe, state.rng):
                ui.message("你成功擺脫了敵人,脫離戰鬥!", style="yellow")
                player.active_effects.clear()
                state.time.advance(1)
                return "fled"
            ui.message("逃跑失敗!", style="red")
        elif action["type"] == "attack":
            tgt = action["target"]
            if combat.is_alive(tgt):
                combat.player_attack_cost(player, gamedata)
                ui.combat_event(combat.resolve_attack(player, tgt, gamedata, state.rng,
                                                      sneak_attack=opening), gamedata)
        elif action["type"] == "cast":
            res = magic.cast(player, gamedata, action["spell_id"], state.rng,
                             target=action.get("target"), battle=battle, enemies=alive_e())
            ui.message(res["message"], style="cyan")
            ui.show_events(res["skill_events"], gamedata)
        elif action["type"] == "power":
            pres = powers.use(player, state, gamedata, target=action.get("target"))
            for m in pres["messages"]:
                ui.message(m, style="bold magenta")
            if pres["escape"]:
                player.active_effects.clear()
                state.time.advance(1)
                return "fled"
        elif action["type"] == "block":
            combat.player_block_cost(player)
            ui.message("你舉盾戒備,準備擋下來襲。", style="grey70")
        elif action["type"] == "vanish":
            combat.player_vanish_cost(player)        # 隱遁耗大量體力(連續隱遁會耗竭)
            attempt_used = vanishes_done
            vanishes_done += 1                       # 每次「嘗試」即遞增 → 成功率遞減真正生效
            if combat.try_vanish(player, len(alive_e()), attempt_used, state.rng):
                vanish_success = True
                ui.show_events(progression.use_skill(player, gamedata, "sneak",
                                                     formulas.COMBAT_SNEAK_XP), gamedata)
                ui.show_events(progression.use_skill(player, gamedata, "acrobatics",
                                                     formulas.COMBAT_DODGE_XP), gamedata)
                ui.message("你翻身遁入陰影 —— 敵人一時失去了你的蹤跡,下一擊將再度致命。",
                           style="bold magenta")
            else:
                ui.message("隱遁失敗!你的身形仍暴露在敵人眼前。", style="red")

        # 隱遁成功 → 重新點亮偷襲(下一次攻擊再吃 sneak 倍率);其餘行動後敵人已警覺
        opening = vanish_success

        # 玩家階段可能殺死(被擒魂的)敵人 → 統一記錄(涵蓋單體/AoE/星座之力)
        for e in enemies:
            note_trap(e)

        # ---- 同伴階段(各自攻擊一個隨機存活敵人)----
        for a in battle["allies"]:
            if not alive_e():
                break
            if not combat.is_alive(a) or magic.is_incapacitated(a):
                continue
            tgt = state.rng.choice(alive_e())
            ui.combat_event(combat.resolve_attack(a, tgt, gamedata, state.rng), gamedata)
            note_trap(tgt)

        # ---- 敵人階段(各自挑我方一個目標)----隱遁成功則本回合敵人撲空 ----
        for e in (enemies if not vanish_success else []):
            if not combat.is_alive(player):
                break
            if not combat.is_alive(e):
                continue
            if magic.is_incapacitated(e):
                why = "恐懼" if magic.is_feared(e) else "麻痺"
                ui.message(f"{e.name}因{why}而無法行動。", style="blue")
                continue
            tgt = combat.pick_player_side_target(player, battle["allies"], state.rng)
            blk = blocking if tgt is player else False
            ev = combat.resolve_attack(e, tgt, gamedata, state.rng, defender_blocking=blk)
            ui.combat_event(ev, gamedata)
            if ev.get("infected") and vampirism.infect(player, state):
                ui.message("獠牙刺入你的頸側 —— 傷口隱隱發燙。你染上了某種不祥的熱症……",
                           style="bold red")

        # ---- 回合結束:持續傷害/狀態計時 ----
        pre_trap = {id(e): magic.has_soul_trap(e) for e in enemies if combat.is_alive(e)}
        ui.combat_tick(magic.tick_effects(player, gamedata))
        for a in battle["allies"]:
            if combat.is_alive(a):
                ui.combat_tick(magic.tick_effects(a, gamedata))
        for e in enemies:
            if combat.is_alive(e):
                ui.combat_tick(magic.tick_effects(e, gamedata))
        for e in enemies:                       # 持續傷害收掉的、原本被擒魂的敵人
            if not combat.is_alive(e) and pre_trap.get(id(e)):
                trapped_kills.add(id(e))
        # 召喚物計時、移除陣亡/到期的同伴
        for a in battle["allies"]:
            if a.summon_turns is not None:
                a.summon_turns -= 1
        battle["allies"] = [a for a in battle["allies"]
                            if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)]

    player.active_effects.clear()
    state.time.advance(1)
    if not combat.is_alive(player):
        return "dead"

    # ---- 勝利結算:全部敵人的戰利品 / 擒魂 / 擊殺與任務 ----
    if len(enemies) == 1:
        ui.message(f"你擊敗了{enemies[0].name}!", style="bold green")
    else:
        ui.message(f"你擊敗了所有敵人({len(enemies)} 名)!", style="bold green")
    total = {"gold": 0, "items": []}
    for e in enemies:
        r = combat.grant_loot(player, e, gamedata, state.rng)
        total["gold"] += r["gold"]
        total["items"] += r["items"]
        if id(e) in trapped_kills:
            gem = magic.soul_gem_for(e)
            if gem:
                inventory.add_item(player, gem, 1)
                ui.message(f"擒魂成功 —— 獲得{gamedata.item_name(gem)}。", style="magenta")
        quests.record_kill(player, e.template_id)
    ui.loot_report(total, gamedata)
    _report_quests(state, gamedata)
    return "victory"


def _report_quests(state: GameState, gamedata: GameData) -> None:
    """結算任務的階段推進與完成,並向玩家報告。"""
    for ev in quests.check_completion(state.player, gamedata):
        if ev["type"] == "stage_advanced":
            ui.message(f"▸ 任務推進:{ev['name']}(階段 {ev['stage_idx'] + 1}/{ev['total']})",
                       style="yellow")
            if ev["stage_text"]:
                ui.message(f"  {ev['stage_text']}", style="white")
            continue
        ui.message(f"✔ 任務完成:{ev['name']}", style="bold yellow")
        r = ev["reward"]
        if r.get("gold"):
            ui.message(f"  獎勵 {r['gold']} 金", style="yellow")
        for iid in r.get("items", []):
            ui.message(f"  獎勵 {gamedata.item_name(iid)}", style="green")
        if r.get("fame"):
            ui.message(f"  聲望 +{r['fame']}", style="cyan")
        if ev.get("standing_loc"):
            loc_name = gamedata.location(ev["standing_loc"])["name"]
            ui.message(f"  ◈ {loc_name}城邦功勳 +{r.get('standing', 1)}", style="gold1")
        if ev["promoted"]:
            fac, rank = ev["promoted"]
            ui.message(f"  ★ 你在{gamedata.factions[fac]['name']}晉升為「{rank}」!", style="bold magenta")
            if ev.get("stipend"):
                ui.message(f"  ◈ 晉升俸祿 {ev['stipend']} 金", style="yellow")


# ======================================================================
# 事件引擎(DESIGN 3.8)
# ======================================================================
def run_event(state: GameState, gamedata: GameData, event_id: str) -> str | None:
    """呈現一個事件並結算所選選項。回傳 'dead'(若觸發的戰鬥致死)或 None。"""
    e = gamedata.events[event_id]
    ui.event_panel(e)

    opts = [(str(i), opt["text"]) for i, opt in enumerate(e["options"])
            if events.option_available(state.player, gamedata, opt)]
    if not opts:                       # 全部選項都不符資格(理論上事件應留安全選項)
        ui.message("你權衡之後,選擇了離開。", style="grey70")
        return None
    idx = int(ui.menu("你要怎麼做?", opts))
    opt = e["options"][idx]

    if "check" in opt:
        ok = events.resolve_check(state.player, opt["check"], state.rng)
        branch = opt["check"]["success" if ok else "failure"]
        ui.message(branch.get("text", "成功!" if ok else "失敗……"),
                   style="green" if ok else "yellow")
        result = events.apply_effects(state, gamedata, branch.get("effects", []), state.rng)
    else:
        result = events.apply_effects(state, gamedata, opt.get("effects", []), state.rng)

    for m in result["messages"]:
        ui.message(m)
    for tid in result["combat"]:
        foe = combat.spawn_creature(gamedata, tid, state.rng)
        ui.combat_intro(foe, state.player, gamedata)
        if run_battle(state, gamedata, foe) == "dead":
            return "dead"
    if state.player.health <= 0:       # 例如陷阱傷害致死
        return "dead"
    _report_quests(state, gamedata)
    return None


def maybe_event(state: GameState, gamedata: GameData, context: str) -> str | None:
    """按情境機率擲一次事件。回傳 'dead' / 'fired'(有事件發生)/ None(無)。"""
    if not state.rng.chance(events.CONTEXT_CHANCE.get(context, 0.0)):
        return None
    eid = events.pick_event(state, gamedata, context, state.rng)
    if eid is None:
        return None
    return "dead" if run_event(state, gamedata, eid) == "dead" else "fired"


def _group_name(enemies: list) -> str:
    """把敵群摘要成「強盜×2、野狼」之類的字串。"""
    counts: dict[str, int] = {}
    for e in enemies:
        counts[e.name] = counts.get(e.name, 0) + 1
    return "、".join(f"{n}×{c}" if c > 1 else n for n, c in counts.items())


def _scout_report(state: GameState, gamedata: GameData, enemies: list) -> None:
    """偵查敵情:依偵查技能逐級揭露情報(數量→血量/危險度→偷襲估傷→抗性弱點),並練偵查。"""
    char = state.player
    sk = char.skill("scout")
    ui.rule("偵查敵情")
    if sk < 20:
        ui.message(f"你壓低身形觀察,但看不真切 —— 約莫有 {len(enemies)} 個敵人。"
                   "(偵查越高,看得越清楚)", style="grey70")
    else:
        for e in enemies:
            parts = [e.name, f"HP {int(e.health)}/{e.max_health}", f"危險度 {e.danger}"]
            if sk >= 50:
                est = combat.estimate_sneak_damage(char, gamedata, e)
                verdict = ("可一擊斃命" if est >= e.health
                           else "重傷但秒不掉" if est >= e.health * 0.5 else "搔癢而已")
                parts.append(f"偷襲約 {est} 傷 → {verdict}")
            if sk >= 75 and e.resist:
                weak = [magic._ELEMENT_CN.get(k, k) for k, v in e.resist.items() if v < 0]
                tough = [magic._ELEMENT_CN.get(k, k) for k, v in e.resist.items() if v >= 50]
                if weak:
                    parts.append("弱點:" + "/".join(weak))
                if tough:
                    parts.append("抗:" + "/".join(tough))
            ui.message("· " + "  |  ".join(parts), style="white")
    ui.show_events(progression.use_skill(char, gamedata, "scout", formulas.COMBAT_SNEAK_XP), gamedata)


def offer_battle(state: GameState, gamedata: GameData, enemies, ambush_chance: float = 0.25,
                 surprise: bool = False) -> str | None:
    """呈現遭遇 → 接戰 / 偵查 / 潛行撤退。回傳結果或 None(撤退成功,未交戰)。

    接戰時擲「入場潛行檢定」決定有無開場偷襲(吃潛行/敵警覺/敵數/護甲/夜間/偵查)。
    surprise=True(被伏擊)大幅扣減先機 → 受害者難以反偷襲加害者。
    ambush_chance 保留作簽名相容(舊呼叫端傳入);避戰已改為吃潛行/速度的潛行撤退。
    """
    if not isinstance(enemies, list):
        enemies = [enemies]
    char = state.player
    name = _group_name(enemies)
    night = state.time.hour < 6 or state.time.hour >= 21
    ui.combat_intro(enemies[0], state.player, gamedata)
    if len(enemies) > 1:
        ui.message(f"來者不止一個 —— 你面對的是:{name}!", style="bold red")
    if surprise:
        ui.message("猝不及防 —— 你已陷入埋伏,難以搶得先機!", style="bold red")
    scouted = False
    while True:
        apct = int(combat.stealth_approach_chance(char, enemies, gamedata, night, scouted, surprise) * 100)
        opts = [("fight", f"接戰（偷襲先機 {apct}%)")]
        if not scouted and not surprise:
            opts.append(("scout", "偵查敵情(看清敵情並提升偷襲先機)"))
        rpct = int(combat.stealth_retreat_chance(char, enemies) * 100)
        opts.append(("retreat", f"潛行撤退（成功率 {rpct}%)"))
        choice = ui.menu(f"要與{name}交戰嗎?", opts)
        if choice == "scout":
            _scout_report(state, gamedata, enemies)
            scouted = True
            continue
        if choice == "retreat":
            if combat.try_stealth_retreat(char, enemies, state.rng):
                ui.message("你悄無聲息地退入暗處,沒有驚動任何人。", style="grey70")
                return None
            ui.message("撤退失敗 —— 敵人發現了你,且已有戒備!", style="red")
            return run_battle(state, gamedata, enemies, alerted=True)
        # 接戰 → 入場潛行檢定:成功取得開場偷襲先機,失敗則敵人警覺(無偷襲)
        got_drop = combat.try_stealth_approach(char, enemies, state.rng, gamedata, night, scouted, surprise)
        if got_drop:
            ui.message("你屏息潛近,敵人渾然未覺 —— 搶得致命先機!", style="bold green")
        else:
            ui.message("你的接近被察覺了,沒能搶到偷襲的先機。", style="yellow")
        # 偵查掙得的備戰空間:潛近成功且未被伏擊時,依偵查技能換得開戰前準備
        pb = formulas.prep_budget(char.skill("scout")) if (got_drop and not surprise) else 0
        return run_battle(state, gamedata, enemies, alerted=not got_drop, prep_budget=pb)


def _maybe_sunburn(state: GameState, gamedata: GameData, hours: int) -> None:
    """吸血鬼在戶外、白天活動 hours 小時 → 陽光灼傷(不致死,只削血)。"""
    burn = vampirism.expose_to_sun(state, gamedata, hours)
    if burn:
        ui.message(f"烈日炙烤著你不死的血肉 —— 灼傷 {burn} 點生命。", style="red")


def action_explore(state: GameState, gamedata: GameData) -> str | None:
    """荒野探索:隨機遭遇一隻敵人(回傳 'dead' 表示陣亡)。"""
    player = state.player
    if player.fatigue < formulas.ATTACK_FATIGUE_COST:
        ui.message("你太疲憊了,先休息再出發吧。", style="yellow")
        return None
    state.time.advance(1)
    _maybe_sunburn(state, gamedata, 1)
    ev = maybe_event(state, gamedata, "explore")    # 探索可能引發奇遇而非戰鬥
    if ev == "dead":
        return "dead"
    if ev == "fired":
        return None
    danger = world.current_location(player, gamedata).get("danger", 1)
    enemies = combat.random_encounter_group(gamedata, player.level, state.rng, max_danger=danger + 1,
                                            biome=world.current_location(player, gamedata).get("biome"))
    return offer_battle(state, gamedata, enemies)


def end_run(state: GameState, gamedata: GameData, ending: str) -> None:
    """結束此生:呈現傳奇總結;依模式決定是否抹除存檔。

    ending = 'death'(陣亡)或 'retire'(隱退)。
    """
    c = state.player
    if ending == "death":
        ui.rule("陣亡")
        ui.message(f"{c.name} 倒下了……一生的冒險就此終結。", style="bold red")
    else:
        ui.rule("隱退")
        ui.message(f"{c.name} 卸下行囊,從此歸隱山林。", style="yellow")

    ui.legacy_screen(legacy.compute(state, gamedata, ending=ending))

    if state.game_mode == GameState.LEGEND and ending == "death":
        SAVE_PATH.unlink(missing_ok=True)   # 傳奇模式只在「死亡」時永久抹除存檔(隱退保留)
        ui.message("【傳奇模式】此生已成定局,存檔已封存。", style="magenta")
    elif ending == "death" and state.game_mode == GameState.ADVENTURE and SAVE_PATH.exists():
        ui.message("(冒險模式:可從主選單『讀取存檔』回到上次存檔點。)", style="grey70")


# ======================================================================
# 旅行
# ======================================================================
def action_travel(state: GameState, gamedata: GameData) -> str | None:
    opts = [(dest, f"{gamedata.location(dest)['name']}（{h} 時)")
            for dest, h in world.travel_options(state.player, gamedata)]
    dest = ui.menu("前往何處?", opts, allow_back=True)
    if dest is None:
        return None
    res = world.travel(state.player, gamedata, dest, state.time, state.rng)
    foe = res["foe"]
    if dest not in state.player.visited_locations:   # 已抵達(location_id 已更新)→ 先記足跡,
        state.player.visited_locations.append(dest)  # 即使途中埋伏致死也算到過此地
    ui.message(f"你啟程前往{gamedata.location(dest)['name']}……", style="grey70")
    _maybe_sunburn(state, gamedata, res["hours"])    # 吸血鬼:白天趕路會被日光灼傷
    if res["hours"] < res["base_hours"]:
        ui.message(f"矯健的身手讓旅程縮短到 {res['hours']} 時(原需 {res['base_hours']} 時)。",
                   style="grey70")
    ui.show_events(res["skill_events"], gamedata)
    if foe is not None:
        ui.message("途中遭遇了埋伏!", style="yellow")
        result = offer_battle(state, gamedata, foe, ambush_chance=0.4, surprise=True)
        if result == "dead":
            return "dead"
    ui.message(f"你抵達了{gamedata.location(dest)['name']}。", style="cyan")
    _report_quests(state, gamedata)              # 「抵達」類任務結算

    # 旅途中的奇遇(途中事件)
    if maybe_event(state, gamedata, "travel") == "dead":
        return "dead"

    loc = gamedata.location(dest)
    # 抵達城鎮的見聞事件
    if loc["type"] in ("city", "town"):
        if maybe_event(state, gamedata, "arrive") == "dead":
            return "dead"
    # 帶著賞金進城 → 衛兵盤查
    if loc["type"] in ("city", "town") and crime.bounty(state.player, loc["province"]) > 0:
        if guard_confrontation(state, gamedata) == "dead":
            return "dead"
    return None


# ======================================================================
# 地城探索
# ======================================================================
def _resolve_container(state: GameState, gamedata: GameData, container: dict, label: str) -> None:
    if container is None:
        return
    lock = container.get("locked", 0)
    if lock > 0:
        ch = dungeon.effective_pick_lock_chance(state.player, gamedata, lock)
        if not ui.confirm(f"發現一個上鎖的{label}(鎖難度 {lock},你的成功率約 {int(ch*100)}%),嘗試撬鎖?"):
            return
        while True:
            r = dungeon.pick_lock(state.player, gamedata, lock, state.rng)
            state.time.advance(r["hours"])
            ui.show_events(r["skill_events"], gamedata)
            if r["success"]:
                ui.message("塔之鑰應驗,鎖無聲而開。" if r.get("tower_key") else "喀噠 —— 鎖開了!",
                           style="green")
                break
            if r["tired"]:
                # 體力耗盡 → 停止這個自動重試迴圈(讓體力成為「單場撬鎖次數」的真實上限,
                # 而非以半額效率無限重試同一把鎖刷 security)。要再撬得先休息。
                ui.message("你精疲力竭,手抖得使不上力 —— 得先歇口氣才撬得動這把鎖。", style="yellow")
                return
            if not ui.confirm("撬鎖失敗。再試一次?"):
                return
    spoils = dungeon.open_container(state.player, gamedata, container, state.rng)
    ui.message(f"你打開了{label}:", style="green")
    ui.loot_report(spoils, gamedata)


def _room_enemies(gamedata: GameData, room: dict, rng: RNG) -> list:
    """房間敵人:支援 'enemies'(清單)或 'enemy'(單一)。"""
    ids = room.get("enemies") or ([room["enemy"]] if room.get("enemy") else [])
    return [combat.spawn_creature(gamedata, tid, rng) for tid in ids]


def action_dungeon(state: GameState, gamedata: GameData) -> str | None:
    loc = world.current_location(state.player, gamedata)
    dg = gamedata.dungeons[loc["dungeon"]]
    rooms = dg["rooms"]
    total = len(rooms) + 1
    ui.message(f"你踏入了{dg['name']}的幽暗深處……", style="magenta")

    for i, room in enumerate(rooms, 1):
        ui.dungeon_room(dg["name"], i, total, room["desc"])
        room_enemies = _room_enemies(gamedata, room, state.rng)
        if room_enemies and run_battle(state, gamedata, room_enemies) == "dead":
            return "dead"
        _resolve_container(state, gamedata, room.get("container"), "箱子")
        if i < len(rooms) and not ui.confirm("繼續深入?"):
            ui.message("你循原路退出了地城。", style="grey70")
            state.time.advance(1)
            return None

    boss = dg["boss"]
    ui.dungeon_room(dg["name"], total, total, boss["desc"], is_boss=True)
    if boss.get("enemy"):
        if boss.get("raw"):   # 已是 elite 的首領以原始強度登場(避免 spawn_boss 再 ×1.6 疊加)
            foe = combat.spawn_creature(gamedata, boss["enemy"], state.rng)
            foe.name = f"{dg['name']}首領"
        else:
            foe = combat.spawn_boss(gamedata, boss["enemy"], state.rng, name=f"{dg['name']}首領")
        if run_battle(state, gamedata, foe) == "dead":
            return "dead"
    _resolve_container(state, gamedata, boss.get("treasure"), "首領寶藏")
    ui.message(f"你肅清了{dg['name']}!", style="bold green")
    quests.record_dungeon_clear(state.player, loc["dungeon"])
    _report_quests(state, gamedata)
    state.time.advance(1)
    return None


# ======================================================================
# 背包與裝備
# ======================================================================
def action_inventory(state: GameState, gamedata: GameData) -> None:
    char = state.player
    while True:
        ui.inventory_panel(char, gamedata)
        if not char.inventory:
            return
        opts = [(s["id"], ui.item_label(gamedata, char, s["id"], s["qty"])) for s in char.inventory]
        item_id = ui.menu("選擇物品(查看/操作)", opts, allow_back=True)
        if item_id is None:
            return
        _item_actions(state, gamedata, item_id)


def _equipped_slot_of(char: Character, item_id: str) -> str | None:
    """找出該物品實際佔用的裝備槽鍵(護甲=slot;飾品=ring1/ring2/amulet)。"""
    for slot, wid in char.equipped.items():
        if wid == item_id:
            return slot
    return None


def _item_actions(state: GameState, gamedata: GameData, item_id: str) -> None:
    char = state.player
    d = gamedata.item(item_id)
    worn = sum(1 for v in char.equipped.values() if v == item_id)
    acts = []
    if d["kind"] == "weapon" and char.weapon != item_id:
        acts.append(("equip_w", "裝備為手持武器"))
    # 雙持匕首:主手是匕首、此物也是匕首、且持有足夠(同型需 2 把)→ 可作副手
    if (d["kind"] == "weapon" and d.get("archetype") == "dagger" and char.offhand != item_id
            and gamedata.item(char.weapon).get("archetype") == "dagger"
            and inventory.count_item(char, item_id) >= (2 if item_id == char.weapon else 1)):
        acts.append(("equip_off", "雙持(副手匕首)"))
    if char.offhand == item_id:
        acts.append(("unequip_off", "卸下副手"))
    if d["kind"] == "armor" and char.equipped.get(d["slot"]) != item_id:
        acts.append(("equip_a", "穿戴"))
    if d["kind"] == "jewelry" and inventory.count_item(char, item_id) > worn:
        acts.append(("equip_j", "戴上"))
    if worn > 0:
        acts.append(("unequip", "卸下"))
    if d["kind"] == "potion":
        acts.append(("use", "使用"))
    acts.append(("drop", "丟棄一件"))
    act = ui.menu(d["name"], acts, allow_back=True)
    if act == "equip_w":
        inventory.equip_weapon(char, gamedata, item_id)
        ui.message(f"你握起了{d['name']}。", style="green")
    elif act == "equip_off":
        inventory.equip_offhand(char, gamedata, item_id)
        ui.message(f"你以副手握起了另一把{d['name']},擺出雙持架式 —— 傷害大增,但無法再格擋。",
                   style="green")
    elif act == "unequip_off":
        inventory.unequip_offhand(char)
        ui.message("你收起了副手匕首。", style="grey70")
    elif act == "equip_a":
        inventory.equip_armor(char, gamedata, item_id)
        stats.recompute_max_resources(char, gamedata)   # 套用護甲 fortify/套裝
        ui.message(f"你穿上了{d['name']}。", style="green")
    elif act == "equip_j":
        slot = inventory.equip_jewelry(char, gamedata, item_id)
        stats.recompute_max_resources(char, gamedata)   # 套用飾品附魔
        ui.message(f"你戴上了{d['name']}。", style="green")
    elif act == "unequip":
        inventory.unequip(char, _equipped_slot_of(char, item_id))
        stats.recompute_max_resources(char, gamedata)   # 移除護甲/飾品加成
        ui.message(f"你卸下了{d['name']}。", style="grey70")
    elif act == "use":
        msg = inventory.use_item(char, gamedata, item_id)
        ui.message(msg or "無法使用。", style="green")
    elif act == "drop":
        inventory.remove_item(char, item_id, 1)
        # 丟棄最後一件會自動卸下;若是 fortify 護甲,須重算以移除其加成並夾限當前值
        stats.recompute_max_resources(char, gamedata)
        ui.message(f"你丟棄了一件{d['name']}。", style="grey70")


# ======================================================================
# 城鎮服務:商店 / 旅店 / 訓練師
# ======================================================================
def action_shop(state: GameState, gamedata: GameData) -> None:
    char = state.player
    loc_id = char.location_id
    world.ensure_stock(char, gamedata, loc_id, state.time, state.rng)   # 首訪/逾期 → 補貨
    while True:
        mode = ui.menu(f"商店(你有 {char.gold} 金幣)", [
            ("buy", "購買"), ("sell", "出售"), ("steal", "行竊(觸法)"),
        ], allow_back=True)
        if mode is None:
            return
        if mode == "steal":
            avail = world.in_stock_items(char, gamedata, loc_id)
            if not avail:
                ui.message("貨架上空空如也,沒什麼好下手的。", style="grey70")
                continue
            opts = [(iid, f"{gamedata.item_name(iid)} ×{world.stock_qty(char, loc_id, iid)}"
                     f"（價值 {gamedata.item(iid)['value']})") for iid in avail]
            iid = ui.menu(f"行竊哪件?(得手率約 {int(crime.steal_chance(char)*100)}%)",
                          opts, allow_back=True)
            if iid is None:
                continue
            r = crime.steal_item(char, gamedata, iid, state.rng)
            state.time.advance(r["hours"])
            if r["ok"]:
                world.take_stock(char, loc_id, iid)
                ui.message(f"你神不知鬼不覺地摸走了{gamedata.item_name(iid)}。", style="green")
            else:
                ui.message(f"「住手!小偷!」 —— 你被逮個正著,賞金 +{r['bounty_added']}。", style="red")
            if r["tired"]:
                ui.message("體力不濟,手腳不聽使喚,差點失風。", style="yellow")
            ui.show_events(r["skill_events"], gamedata)
            continue
        if mode == "buy":
            avail = world.in_stock_items(char, gamedata, loc_id)
            if not avail:
                ui.message("貨架空空如也,等商人補貨再來吧。", style="grey70")
                continue
            opts = [(iid, f"{gamedata.item_name(iid)} ×{world.stock_qty(char, loc_id, iid)}"
                     f" — {world.buy_price(char, gamedata, iid)} 金") for iid in avail]
            iid = ui.menu("買什麼?", opts, allow_back=True)
            if iid is None:
                continue
            price = world.buy_price(char, gamedata, iid)
            if char.gold < price:
                ui.message("金幣不足。", style="red")
            elif not inventory.can_carry(char, gamedata, iid):
                ui.message("背負不下,太重了。", style="red")
            else:
                char.gold -= price
                inventory.add_item(char, iid, 1)
                world.take_stock(char, loc_id, iid)
                ui.message(f"買下了{gamedata.item_name(iid)}。", style="green")
        else:
            sellable = [s for s in char.inventory if gamedata.item(s["id"])["value"] > 0]
            if not sellable:
                ui.message("沒有可賣的東西。", style="grey70")
                continue
            opts = [(s["id"], f"{ui.item_label(gamedata, char, s['id'], s['qty'])} — 售 "
                     f"{world.sell_price(char, gamedata, s['id'])} 金") for s in sellable]
            iid = ui.menu("賣什麼?", opts, allow_back=True)
            if iid is None:
                continue
            price = world.sell_price(char, gamedata, iid)
            inventory.remove_item(char, iid, 1)
            # 賣掉最後一件會自動卸下;若是 fortify 護甲,須重算以移除其加成並夾限當前值
            stats.recompute_max_resources(char, gamedata)
            char.gold += price
            progression.use_skill(char, gamedata, "mercantile", 0.3)
            ui.message(f"賣出{gamedata.item_name(iid)},得 {price} 金。", style="green")


MAX_PARTY = 2


def action_inn(state: GameState, gamedata: GameData) -> None:
    char = state.player
    while True:
        party = "、".join(gamedata.companions[c]["name"] for c in char.companions) or "無"
        opts = [("rest", "過夜(10 金,完全回復)"), ("hire", "雇用傭兵同伴")]
        if char.companions:
            opts.append(("dismiss", "解散傭兵"))
        choice = ui.menu(f"旅店(目前隊伍:{party})", opts, allow_back=True)
        if choice is None:
            return
        if choice == "rest":
            fee = 10
            if char.gold < fee:
                ui.message(f"住一晚要 {fee} 金,你付不起。", style="red")
            else:
                char.gold -= fee
                char.health, char.magicka, char.fatigue = char.max_health, char.max_magicka, char.max_fatigue
                state.time.advance(8)
                ui.message("一夜好眠,氣力盡復。", style="green")
        elif choice == "hire":
            _hire_mercenary(state, gamedata)
        elif choice == "dismiss":
            _dismiss_mercenary(state, gamedata)


def action_feed(state: GameState, gamedata: GameData) -> None:
    """吸血鬼進食:獵取活人 → 飢餓歸零(階級 0)、回血;白天易被撞見而染上賞金。"""
    char = state.player
    stg = vampirism.stage(char, state)
    if stg == 0:
        if not ui.confirm("你尚未飢渴(已是初擁之境),仍要進食嗎?"):
            return
    if not ui.confirm("你潛近一名落單的活人,獠牙逼近其頸動脈 —— 下手嗎?"):
        return
    res = vampirism.feed(state, gamedata)
    ui.message(f"溫熱的鮮血湧入,飢渴退去 —— 回復了 {res['healed']} 點生命,血之飢餓重歸初擁。",
               style="bold red")
    if res["caught"]:
        ui.message(f"但你被人撞見了!{res['province']}懸起了你的賞金(+{res['bounty']}),惡名加身。",
                   style="yellow")
    else:
        ui.message("夜色掩護了你,無人知曉。", style="grey70")


CURE_QID = "cure_vampirism"


def action_vampire_cure(state: GameState, gamedata: GameData) -> None:
    """探詢/推進/完成「驅逐血咒」——D 治療任務(任何法師公會,僅吸血鬼可見)。"""
    char = state.player
    if not char.is_vampire:
        return
    _report_quests(state, gamedata)   # 先結算可能已達標的採集/擊殺階段

    if quests.is_done(char, CURE_QID):
        ui.message("梅莉桑德取出你備齊的大蒜、毒茄參與那瓶受詛之血,在燭火與符文間低聲誦咒……",
                   style="white")
        if not ui.confirm("血咒之根將在此夜被斬斷 —— 進行解咒儀式嗎?"):
            return
        vampirism.cure(char, gamedata)
        char.completed_quests.remove(CURE_QID)   # 解咒可重複(日後再被感染,可再求一次)
        ui.rule("血咒已解")
        ui.message("一陣撕裂般的劇痛後,暖意重回血脈 —— 你的心臟再度跳動,恢復了凡人之身。",
                   style="bold green")
        return

    if quests.is_active(char, CURE_QID):
        ui.message(f"解咒進度:{quests.objective_text(char, gamedata, CURE_QID)}", style="white")
        ui.message("備齊媒介、取得受詛之血後,回到任一法師公會行儀式。", style="grey70")
        return

    ui.message(gamedata.quests[CURE_QID]["text"], style="white")
    if ui.confirm("接下『驅逐血咒』,踏上解咒之路嗎?"):
        quests.accept_quest(char, gamedata, CURE_QID)
        ui.message("已接取任務:驅逐血咒", style="bold yellow")
        _report_quests(state, gamedata)


# ======================================================================
# 黑暗兄弟會聖所(合約晉升 + 夜母祝福 + 洗白賞金)
# ======================================================================
def _active_db_quest(state: GameState, gamedata: GameData) -> str | None:
    """目前進行中的黑暗兄弟會合約 id(沒有則 None)。"""
    for qid in state.player.quests:
        if gamedata.quests.get(qid, {}).get("faction") == brotherhood.FACTION:
            return qid
    return None


def action_sanctuary(state: GameState, gamedata: GameData) -> str | None:
    """黑暗兄弟會聖所:接取/執行合約、洗白賞金、重溫五戒。回傳 'dead'|None。"""
    char = state.player
    if not brotherhood.is_member(char):
        return None
    _report_quests(state, gamedata)   # 先結算可能已交付的合約
    ui.guild_panel(char, gamedata, brotherhood.FACTION)
    rk = brotherhood.rank(char)
    if rk > 0:
        ui.message(f"夜母祝福:潛殺傷害 +{int(round(rk * formulas.NIGHT_MOTHER_SNEAK_PER_RANK * 100))}%。",
                   style="magenta")

    while True:
        opts: list = []
        active = _active_db_quest(state, gamedata)
        if active:
            obj, _, _ = quests.current_objective(char, gamedata, active)
            tname = gamedata.bestiary[obj["creature"]]["name"]
            opts.append(("execute", f"執行合約 —— 行刺{tname}"))
        else:
            avail = quests.available_quests(char, gamedata, "guild", brotherhood.FACTION)
            if avail:
                opts.append(("accept", "接取新合約"))
        province = crime.province_of(char, gamedata)
        if crime.bounty(char, province) > 0:
            owed = crime.bounty(char, province)
            cost = brotherhood.launder_cost(char, gamedata, owed)
            opts.append(("launder", f"洗白{province}的賞金({owed} → {cost} 金)"))
        opts.append(("tenets", "重溫五戒"))
        choice = ui.menu("聖所", opts, allow_back=True)
        if choice is None:
            return None
        if choice == "accept":
            avail = quests.available_quests(char, gamedata, "guild", brotherhood.FACTION)
            if avail:
                _accept_and_brief(state, gamedata, avail[0])
        elif choice == "execute":
            died = action_contract(state, gamedata, active)
            if died == "dead":
                return "dead"
        elif choice == "launder":
            r = brotherhood.launder_bounty(state, gamedata)
            if r["ok"]:
                ui.message(f"兄弟會的門路替你抹去了{r['province']}的 {r['cleared']} 金賞金"
                           f"(花費 {r['paid']} 金)。", style="green")
            elif "owed" in r:
                ui.message(f"洗白需 {r['owed']} 金,你付不起。", style="red")
        elif choice == "tenets":
            ui.message("黑暗兄弟會五戒:", style="bold magenta")
            for t in brotherhood.TENETS:
                ui.message(f"  {t}", style="white")


def action_contract(state: GameState, gamedata: GameData, qid: str) -> str | None:
    """執行一張合約:前往行刺目標(可先靠潛行搶得先機)。回傳 'dead'|None。"""
    char = state.player
    rq = quests.resolved(char, gamedata, qid)
    obj, _, _ = quests.current_objective(char, gamedata, qid)
    target_id = obj["creature"]
    tname = gamedata.bestiary[target_id]["name"]
    if not ui.confirm(f"潛入目標所在,取「{tname}」的性命嗎?"):
        return None

    enemies = [combat.spawn_creature(gamedata, target_id, state.rng)]
    for eid in rq.get("escort", []):
        enemies.append(combat.spawn_creature(gamedata, eid, state.rng))

    night = state.time.hour < 6 or state.time.hour >= 21
    got_drop = combat.try_stealth_approach(char, enemies, state.rng, gamedata, night, False, False)
    if got_drop:
        ui.message("你如影潛近,目標渾然未覺 —— 致命先機在握。", style="bold green")
    else:
        ui.message("你的接近驚動了目標,沒能搶到偷襲先機。", style="yellow")

    pb = formulas.prep_budget(char.skill("scout")) if got_drop else 0   # 合約暗殺也享偵查備戰
    result = run_battle(state, gamedata, enemies, alerted=not got_drop, prep_budget=pb)
    if result == "dead":
        return "dead"
    if result == "fled":
        ui.message("你暫且退去 —— 合約仍懸而未決。", style="grey70")
        return None
    # 勝利:結算合約晉升,並對「無人目擊的乾淨擊殺」額外發賞
    _report_quests(state, gamedata)
    if got_drop:
        bonus = rq.get("clean_bonus", 0)
        if bonus:
            char.gold += bonus
            ui.message(f"無人目擊、一擊致命 —— 兄弟會額外賞你 {bonus} 金。", style="bold green")
    return None


def _hire_mercenary(state: GameState, gamedata: GameData) -> None:
    char = state.player
    if len(char.companions) >= MAX_PARTY:
        ui.message(f"隊伍已滿(最多 {MAX_PARTY} 名傭兵),先解散一名吧。", style="yellow")
        return
    avail = [cid for cid in gamedata.companions if cid not in char.companions]
    opts = [(cid, f"{gamedata.companions[cid]['name']} — {gamedata.companions[cid]['cost']} 金:"
             f"{gamedata.companions[cid]['blurb']}") for cid in avail]
    cid = ui.menu(f"雇用哪位?(你有 {char.gold} 金)", opts, allow_back=True)
    if cid is None:
        return
    cost = gamedata.companions[cid]["cost"]
    if char.gold < cost:
        ui.message("金幣不足。", style="red")
        return
    char.gold -= cost
    char.companions.append(cid)
    ui.message(f"{gamedata.companions[cid]['name']}加入了你的隊伍,將在戰鬥中並肩作戰。", style="bold green")


def _dismiss_mercenary(state: GameState, gamedata: GameData) -> None:
    char = state.player
    opts = [(cid, gamedata.companions[cid]["name"]) for cid in char.companions]
    cid = ui.menu("解散哪位傭兵?", opts, allow_back=True)
    if cid is None:
        return
    char.companions.remove(cid)
    ui.message(f"{gamedata.companions[cid]['name']}拿了酬勞,就此別過。", style="grey70")


def action_trainer(state: GameState, gamedata: GameData) -> None:
    char = state.player
    spec = ui.menu("向訓練師學哪一類?", [
        ("combat", "戰鬥"), ("magic", "魔法"), ("stealth", "潛行"),
    ], allow_back=True)
    if spec is None:
        return
    opts = []
    for sid in gamedata.skills_by_spec(spec):
        cost = world.train_cost(char.skill(sid))
        opts.append((sid, f"{gamedata.skill_name(sid)} (Lv {char.skill(sid)}) — {cost} 金 +1"))
    sid = ui.menu("訓練哪項技能?", opts, allow_back=True)
    if sid is None:
        return
    if char.skill(sid) >= formulas.SKILL_CAP:
        ui.message("此技能已臻化境,無需再學。", style="grey70")
        return
    cost = world.train_cost(char.skill(sid))
    if char.gold < cost:
        ui.message("金幣不足。", style="red")
        return
    char.gold -= cost
    events = progression.use_skill(char, gamedata, sid, formulas.skill_threshold(char.skill(sid)))
    ui.message(f"訓練師指點了你的{gamedata.skill_name(sid)}。", style="green")
    ui.show_events(events, gamedata)


# ======================================================================
# 領主區(宮廷):謁見領主(Phase 1)
#   後續分層(藍圖見 handoff §6):Phase 2 領主委託 + 武士冊封;
#   Phase 3 政治/選邊;Phase 4 攻城戰(複用 combat 群戰)。
# ======================================================================
def _court_reception(char) -> str:
    """依聲望決定領主的接待語氣(Oblivion 風:榮耀/惡名影響貴族態度)。"""
    fame, infamy = char.fame, char.infamy
    if infamy >= 15 and infamy >= fame:
        return "守衛按劍戒備,領主冷眼端詳你這聲名狼藉之徒,語氣中盡是提防。"
    if fame >= 15 and fame > infamy:
        return "領主起身相迎,對你赫赫威名禮遇有加,左右無不側目。"
    if fame == 0 and infamy == 0:
        return "領主只略一頷首 —— 在這朝堂上,你不過是個無名過客。"
    return "領主端坐王座,以例行的禮節接見你。"


def action_court(state: GameState, gamedata: GameData) -> str | None:
    """領主區:謁見 + 領主委託 + 受封武士 + 選邊/攻城(Phase 2+3+4)。回傳 'dead'(攻城陣亡)或 None。"""
    char = state.player
    loc_id = char.location_id
    ruler = gamedata.ruler_at(loc_id)
    if not ruler:
        ui.message("此地沒有領主可謁見。", style="grey70")
        return None
    rel = politics.relationship(char, gamedata, loc_id)
    pol = {"stance": politics.stance_label(politics.faction_of(char, gamedata, loc_id)),
           "relation": politics.REL_LABEL.get(rel, rel),
           "garrison": politics.garrison_of(char, gamedata, loc_id)}
    ui.court_panel(ruler, gamedata, _court_reception(char),
                   standing=court.standing(char, loc_id), thane=court.is_thane(char, loc_id),
                   politics=pol)
    opts = []
    offered = court.offered_ruler_quest(char, gamedata, loc_id)
    if rel != "enemy" and offered:              # 敵城不接你的委託
        opts.append(("quest", f"領取委託:{gamedata.quests[offered]['name']}"))
    if rel != "enemy" and court.can_become_thane(char, gamedata, loc_id):
        opts.append(("thane", "✦ 受封武士"))
    if not char.allegiance:
        opts.append(("pledge", "宣誓效忠 —— 選擇你的大義"))
    if politics.can_siege(char, gamedata, loc_id):
        opts.append(("siege", f"⚔ 發動攻城(守軍 {politics.garrison_of(char, gamedata, loc_id)})"))
    if not opts:
        return None                             # 純謁見:領主暫無吩咐
    choice = ui.menu("領主有何吩咐?", opts, allow_back=True)
    if choice == "quest":
        _accept_and_brief(state, gamedata, offered)
    elif choice == "thane":
        _become_thane(state, gamedata, loc_id, ruler)
    elif choice == "pledge":
        _pledge_allegiance(state, gamedata)
    elif choice == "siege":
        return action_siege(state, gamedata, loc_id)
    return None


def _pledge_allegiance(state: GameState, gamedata: GameData) -> None:
    char = state.player
    ui.message("大空位之世,紅寶石王座空懸 —— 你決意擁護哪一方大義?", style="white")
    cause = ui.menu("宣誓效忠", [(c, politics.cause_name(c)) for c in politics.CAUSES],
                    allow_back=True)
    if cause is None:
        return
    politics.pledge(char, cause)
    ui.message(f"你宣誓擁護「{politics.cause_name(cause)}」。從此同道之城以你為友,"
               f"對立之城則成你刀鋒所向。", style="bold gold1")


def action_siege(state: GameState, gamedata: GameData, loc_id: str) -> str | None:
    """對對立大義之城發動攻城:消耗戰 —— 每破一波永久削減守軍(進度保留,可分次圍攻),
    削到 0 則城池易幟。波間可趁隙重整。回傳 'dead'(陣亡)或 None。"""
    char = state.player
    city = gamedata.location(loc_id)["name"]
    remaining = politics.garrison_of(char, gamedata, loc_id)
    if not ui.confirm(f"對「{city}」發動攻城?現存守軍約 {remaining} —— 這是連場血戰的消耗戰,"
                      f"戰果會保留(可分次圍攻),但一旦力竭敗陣便是死路。"):
        return None
    ui.message(f"號角長鳴,你向{city}的城牆發起猛攻 ——", style="bold magenta")
    base = politics.base_garrison(gamedata, loc_id)
    wave_no = 0
    while politics.garrison_of(char, gamedata, loc_id) > 0:
        wave_no += 1
        rem = politics.garrison_of(char, gamedata, loc_id)
        wave = politics.siege_wave(rem, base)
        enemies = [combat.spawn_creature(gamedata, politics.SIEGE_SOLDIER, state.rng)
                   for _ in range(wave["guards"])]
        if wave["boss"]:
            enemies.append(combat.spawn_boss(gamedata, politics.SIEGE_SOLDIER, state.rng,
                                             name=f"{city}守將"))
        if wave_no > 1:                         # 破上一波後趁隙重整(部分回復,非全補)
            politics.regroup(char)
            ui.message("你退到殘垣後包紮喘息,稍稍恢復了氣力。", style="grey70")
        ui.message(f"⚔ 守軍迎面殺到(殘軍約 {rem})!", style="magenta")
        res = run_battle(state, gamedata, enemies)
        if res == "dead":
            return "dead"
        if res == "fled":
            ui.message(f"你且戰且退 —— 城未下,但守軍已折損,戰果保留,改日可再續攻。", style="yellow")
            return None
        politics.deplete_garrison(char, gamedata, loc_id, wave["strength"])   # 永久削減,進度持久
    politics.conquer(char, gamedata, loc_id)
    char.fame += politics.SIEGE_FAME
    ui.message(f"城門洞開,守將伏誅 —— 「{city}」易幟,自此歸於{politics.cause_name(char.allegiance)}!",
               style="bold gold1")
    ui.message(f"你的威名響徹四方(聲望 +{politics.SIEGE_FAME})。", style="cyan")
    return None


def _become_thane(state: GameState, gamedata: GameData, loc_id: str, ruler: dict) -> None:
    char = state.player
    granted = court.make_thane(char, gamedata, loc_id)   # 記入 thaneships + 授信物
    city = gamedata.location(loc_id)["name"]
    ui.message(f"{ruler['title']}起身,當眾冊封你為「{city}武士」—— 領地的榮譽與守護從此繫於你身。",
               style="bold gold1")
    if granted["gift"]:
        ui.message(f"領主賜下信物:{gamedata.item_name(granted['gift'])}。", style="green")
    hc = granted["housecarl"]
    if hc and hc in gamedata.companions and hc not in char.companions:
        if len(char.companions) < MAX_PARTY:
            char.companions.append(hc)
            ui.message(f"侍從 {gamedata.companions[hc]['name']} 從此追隨左右。", style="green")
        else:
            ui.message(f"領主欲遣侍從 {gamedata.companions[hc]['name']} 隨你,但你隊伍已滿,"
                       f"婉拒了這份護衛。", style="yellow")
    ui.message(f"自此{gamedata.location(loc_id)['province']}的衛兵,對你的小過睜隻眼閉隻眼。",
               style="grey70")


# ======================================================================
# 魔法與製作:施法 / 法師公會 / 煉金 / 附魔 / 修理
# ======================================================================
def action_cast_self(state: GameState, gamedata: GameData) -> None:
    """戰鬥外施法:治療、回體力等自我增益(練功也行)。"""
    char = state.player
    usable = [s for s in char.spells
              if gamedata.spells[s]["target"] == "self"
              and gamedata.spells[s]["effect"]["kind"] in ("heal", "restore_fatigue")]
    if not usable:
        ui.message("你沒有可在戰鬥外施放的法術。", style="grey70")
        return
    opts = [(s, f"{gamedata.spells[s]['name']}（{magic.effective_cost(char, gamedata, s)} 魔力)")
            for s in usable]
    sid = ui.menu(f"施放哪道法術?(魔力 {int(char.magicka)}/{char.max_magicka})", opts, allow_back=True)
    if sid is None:
        return
    if not magic.can_cast(char, gamedata, sid):
        ui.message("魔力不足。", style="red")
        return
    res = magic.cast(char, gamedata, sid, state.rng)
    ui.message(res["message"], style="cyan")
    ui.show_events(res["skill_events"], gamedata)


def action_use_power(state: GameState, gamedata: GameData) -> None:
    """平時施展出生星座能力(治療/淨化/塔之鑰)。"""
    pid = powers.power_id(state.player, gamedata)
    pdef = powers.power_def(pid)
    if not ui.confirm(f"施展「{pdef['name']}」?({pdef['desc']}每日一次)"):
        return
    res = powers.use(state.player, state, gamedata)
    for m in res["messages"]:
        ui.message(m, style="bold magenta")


def action_spell_vendor(state: GameState, gamedata: GameData) -> None:
    char = state.player
    loc = world.current_location(char, gamedata)
    for_sale = [s for s in loc.get("spell_stock", []) if s not in char.spells]
    if not for_sale:
        ui.message("公會裡沒有你還沒學會的法術了。", style="grey70")
        return
    disc = factions.spell_discount(char, gamedata)   # 法師公會階級折扣
    def _sp(s):
        return max(1, round(world.spell_price(gamedata, s) * (1 - disc)))
    label = f"學習法術(你有 {char.gold} 金"
    label += f",會員 -{int(disc*100)}%)" if disc else ")"
    opts = [(s, f"{gamedata.spells[s]['name']}（{gamedata.spells[s]['school']}) — {_sp(s)} 金")
            for s in for_sale]
    sid = ui.menu(label, opts, allow_back=True)
    if sid is None:
        return
    price = _sp(sid)
    if char.gold < price:
        ui.message("金幣不足。", style="red")
        return
    char.gold -= price
    char.spells.append(sid)
    ui.message(f"你習得了{gamedata.spells[sid]['name']}!", style="bold green")


def action_alchemy(state: GameState, gamedata: GameData) -> None:
    char = state.player
    ings = [s["id"] for s in char.inventory if gamedata.item(s["id"]).get("kind") == "ingredient"]
    if len(ings) < 2:
        ui.message("材料不足,至少需要兩種煉金材料。", style="grey70")
        return

    def _ing_opts(exclude=None):
        out = []
        for iid in ings:
            if iid == exclude:
                continue
            effs = "、".join(_EFFECT_CN.get(e["kind"], e["kind"])
                            for e in alchemy.ingredient_effects(gamedata, iid))
            out.append((iid, f"{gamedata.item_name(iid)} ×{inventory.count_item(char, iid)}（{effs})"))
        return out

    a = ui.menu("選第一種材料", _ing_opts(), allow_back=True)
    if a is None:
        return
    b = ui.menu("選第二種材料", _ing_opts(exclude=a), allow_back=True)
    if b is None:
        return
    res = alchemy.brew(char, gamedata, a, b, state.rng)
    state.time.advance(res["hours"])
    ui.message(res["message"], style="green" if res["ok"] else "yellow")
    if res["tired"]:
        ui.message("體力不濟,煉製時心不在焉,成效減半。", style="yellow")
    ui.show_events(res["skill_events"], gamedata)


def action_enchant(state: GameState, gamedata: GameData) -> None:
    char = state.player
    gems = enchanting.filled_soul_gems(char, gamedata)
    if not gems:
        ui.message("你沒有充能的靈魂石(用『擒魂術』擊殺敵人可獲得)。", style="grey70")
        return
    weapons = enchanting.enchantable_weapons(char, gamedata)
    armors = enchanting.enchantable_armor(char, gamedata)
    jewels = enchanting.enchantable_jewelry(char, gamedata)

    kinds = []
    if weapons:
        kinds.append(("weapon", "武器(附元素傷害)"))
    if armors:
        kinds.append(("armor", "護甲(強化生命/魔力/體力)"))
    if jewels:
        kinds.append(("jewelry", "飾品(強化技能/屬性/抗性/資源)"))
    if not kinds:
        ui.message("沒有可附魔的武器、護甲或飾品。", style="grey70")
        return
    kind = kinds[0][0] if len(kinds) == 1 else ui.menu("附魔什麼?", kinds, allow_back=True)
    if kind is None:
        return

    gem = ui.menu("使用哪顆靈魂石?",
                  [(g, f"{gamedata.item_name(g)}(靈魂 {gamedata.item(g)['soul']})") for g in gems],
                  allow_back=True)
    if gem is None:
        return

    if kind == "weapon":
        wid = ui.menu("為哪把武器附魔?",
                      [(w, gamedata.item_name(w)) for w in weapons], allow_back=True)
        if wid is None:
            return
        elem = ui.menu("附上哪種元素?", [("fire", "烈焰"), ("frost", "冰霜"), ("shock", "雷電")],
                       allow_back=True)
        if elem is None:
            return
        res = enchanting.enchant_weapon(char, gamedata, wid, elem, gem)
    elif kind == "armor":
        aid = ui.menu("為哪件護甲附魔?",
                      [(a, gamedata.item_name(a)) for a in armors], allow_back=True)
        if aid is None:
            return
        stat = ui.menu("穿戴時強化哪項?",
                       [("health", "生命"), ("magicka", "魔力"), ("fatigue", "體力")],
                       allow_back=True)
        if stat is None:
            return
        res = enchanting.enchant_armor(char, gamedata, aid, stat, gem)
    else:   # jewelry
        jid = ui.menu("為哪件飾品附魔?",
                      [(j, gamedata.item_name(j)) for j in jewels], allow_back=True)
        if jid is None:
            return
        jkind = ui.menu("附魔型別?", enchanting.JEWELRY_KINDS, allow_back=True)
        if jkind is None:
            return
        if jkind == "skill":
            param_opts = [(sid, gamedata.skill_name(sid)) for sid in gamedata.skills]
        elif jkind == "attr":
            param_opts = [(a, formulas.ATTRIBUTE_NAMES[a]) for a in formulas.ATTRIBUTES]
        elif jkind == "resist":
            param_opts = [(e, n) for e, n in
                          [("fire", "烈焰"), ("frost", "冰霜"), ("shock", "雷電"),
                           ("poison", "毒素"), ("magic", "魔法")]]
        else:  # res
            param_opts = [("health", "生命"), ("magicka", "魔力"), ("fatigue", "體力")]
        param = ui.menu("強化哪一項?", param_opts, allow_back=True)
        if param is None:
            return
        res = enchanting.enchant_jewelry(char, gamedata, jid, jkind, param, gem)

    state.time.advance(res["hours"])
    ui.message(res["message"], style="bold green" if res["ok"] else "red")
    if res["tired"]:
        ui.message("精神耗弱,難以將靈魂束入符文,成效減半。", style="yellow")
    ui.show_events(res["skill_events"], gamedata)


def action_repair(state: GameState, gamedata: GameData) -> None:
    char = state.player
    loc = world.current_location(char, gamedata)
    at_smith = "armorer" in loc.get("services", [])
    has_hammer = inventory.count_item(char, "repair_hammer") > 0
    repair_disc = factions.repair_discount(char, gamedata)            # 戰士公會階級折扣
    smith_fee = max(0, round(world.repair_fee() * (1 - repair_disc)))
    opts = []
    if at_smith:
        fee_txt = "免費" if smith_fee == 0 else f"{smith_fee} 金"
        opts.append(("smith", f"請鐵匠修復全部裝備({fee_txt},修到全新)"))
    if has_hammer:
        cap = int(inventory.repairable_cap(char.skill("armorer")))
        opts.append(("hammer", f"用修理鎚自行修理(修到 {cap}%,鍛鍊護甲修理)"))
    if not opts:
        ui.message("這裡沒有鐵匠,你也沒有修理鎚。", style="grey70")
        return
    choice = ui.menu("如何修理?", opts, allow_back=True)
    if choice == "smith":
        if char.gold < smith_fee:
            ui.message("金幣不足。", style="red")
            return
        char.gold -= smith_fee
        inventory.repair_all(char, 100.0)
        ui.message("鐵匠叮叮噹噹一陣,你的裝備煥然一新。", style="green")
    elif choice == "hammer":
        cap = inventory.repairable_cap(char.skill("armorer"))
        inventory.repair_all(char, cap)
        inventory.remove_item(char, "repair_hammer", 1)
        # 與訓練師/正規練習對齊:自行修理付出護甲修理 practice 的體力 + 時間,非零成本刷 armorer
        xp, hours, tired = progression.practice_cost(char, gamedata, "armorer")
        events = progression.use_skill(char, gamedata, "armorer", xp)
        state.time.advance(hours)
        ui.message(f"你用修理鎚整備了裝備(上限 {int(cap)}%)。", style="green")
        if tired:
            ui.message("體力不濟,修整得馬虎。", style="yellow")
        ui.show_events(events, gamedata)


def action_craft(state: GameState, gamedata: GameData) -> None:
    """製革/加工:把獸皮等原料依配方做成裝備(需鐵匠/製革處)。"""
    char = state.player
    loc = world.current_location(char, gamedata)
    station = "smith" if "armorer" in loc.get("services", []) else None
    rids = crafting.recipes_for_station(gamedata, station)
    if not rids:
        ui.message("這裡沒有可用的工坊。", style="grey70")
        return
    opts = []
    for rid in rids:
        r = gamedata.recipes[rid]
        inp = "、".join(f"{gamedata.item_name(i)}×{n}" for i, n in r["inputs"].items())
        tag = "" if crafting.can_craft(char, gamedata, rid) else "(材料不足)"
        opts.append((rid, f"{r['name']}:{inp} → {gamedata.item_name(r['output'])}{tag}"))
    rid = ui.menu("製作什麼?", opts, allow_back=True)
    if rid is None:
        return
    res = crafting.craft(char, gamedata, rid)
    state.time.advance(res["hours"])
    ui.message(res["message"], style="green" if res["ok"] else "red")
    if res["tired"]:
        ui.message("體力不濟,做工馬虎。", style="yellow")
    ui.show_events(res["skill_events"], gamedata)


_EFFECT_CN = {"heal": "回血", "restore_magicka": "回魔", "restore_fatigue": "回體",
              "damage_health": "毒傷", "paralyze": "麻痺"}


def action_coat_weapon(state: GameState, gamedata: GameData) -> None:
    """把一瓶毒藥塗到手持武器上。"""
    char = state.player
    if char.weapon == "fists":
        ui.message("徒手無從塗毒,先裝備一把武器。", style="yellow")
        return
    poisons = [s["id"] for s in char.inventory if gamedata.item(s["id"]).get("kind") == "poison"]
    if not poisons:
        ui.message("你沒有可用的毒藥(用煉金把有害材料調成毒藥)。", style="grey70")
        return
    if char.weapon_poison:
        ui.message(f"目前武器已塗:{char.weapon_poison['name']}(剩 {char.weapon_poison['charges']} 次)。",
                   style="grey70")
    opts = [(p, f"{gamedata.item_name(p)} ×{inventory.count_item(char, p)}") for p in poisons]
    pid = ui.menu(f"塗哪瓶毒?(可附著 {inventory.poison_charges(char)} 次攻擊)", opts, allow_back=True)
    if pid is None:
        return
    if inventory.coat_weapon(char, gamedata, pid):
        ui.message(f"你把{gamedata.item_name(pid)}抹上了{gamedata.item(char.weapon)['name']}的刃口。",
                   style="green")


# ======================================================================
# 公會、任務、犯罪、對話
# ======================================================================
def action_guild_hall(state: GameState, gamedata: GameData, faction_id: str) -> None:
    char = state.player
    f = gamedata.factions[faction_id]
    ui.guild_panel(char, gamedata, faction_id)

    opts = []
    if not factions.is_member(char, faction_id):
        reason = factions.join_block_reason(char, gamedata, faction_id)
        if reason is not None:                       # 門檻/對立/通緝 → 說明原因
            ui.message(reason, style="yellow")
            return
        opts.append(("join", "申請入會"))
    else:
        avail = quests.available_quests(char, gamedata, "guild", faction_id)
        if avail:
            opts.append(("accept", "接取晉升任務"))
        else:
            # 區分「手上還有公會任務沒交」與「技能/通緝/已達頂點擋住晉升」
            has_active = any(gamedata.quests[q].get("faction") == faction_id for q in char.quests)
            if has_active:
                ui.message("先完成你手上的公會任務,再回來談晉升。", style="grey70")
            else:
                ui.message(factions.advance_block_reason(char, gamedata, faction_id)
                           or "公會目前沒有你能接的委託。", style="grey70")
            return
    choice = ui.menu("公會事務", opts, allow_back=True)
    if choice == "join":
        factions.join(char, faction_id)
        ui.message(f"你加入了{f['name']},現為「{factions.rank_name(char, gamedata, faction_id)}」。",
                   style="bold green")
    elif choice == "accept":
        avail = quests.available_quests(char, gamedata, "guild", faction_id)
        _accept_and_brief(state, gamedata, avail[0])


def action_board(state: GameState, gamedata: GameData) -> None:
    char = state.player
    province = world.current_location(char, gamedata)["province"]
    avail = quests.available_quests(char, gamedata, "board", province=province)
    if not avail:
        ui.message("告示板上沒有你還沒接的委託。", style="grey70")
        return
    opts = [(qid, f"{gamedata.quests[qid]['name']} — {quests.objective_text(char, gamedata, qid)}"
             f"(賞 {gamedata.quests[qid]['reward'].get('gold', 0)} 金)") for qid in avail]
    qid = ui.menu("告示板委託", opts, allow_back=True)
    if qid is None:
        return
    _accept_and_brief(state, gamedata, qid)


def _accept_and_brief(state: GameState, gamedata: GameData, qid: str) -> None:
    q = gamedata.quests[qid]
    branch = 0
    brs = quests.branches(q)
    if brs:                                  # 敘事分支:接取前先選路線
        ui.message(q.get("text", ""), style="white")
        pick = ui.menu("選擇你的路線", [(str(i), b["label"]) for i, b in enumerate(brs)],
                       allow_back=True)
        if pick is None:
            return
        branch = int(pick)
    quests.accept_quest(state.player, gamedata, qid, branch)
    ui.message(brs[branch]["text"] if brs else q.get("text", ""), style="white")
    ui.message(f"已接取任務:{q['name']}", style="bold yellow")
    _report_quests(state, gamedata)   # 可能當下即達標(如已持有上繳物)


def action_quest_log(state: GameState, gamedata: GameData) -> None:
    ui.quest_log(state.player, gamedata)


def _living_npcs_at(state: GameState, gamedata: GameData) -> list[str]:
    """當地仍在世(未被你滅口)的可攀談 NPC。"""
    return [n for n in gamedata.npcs_at(state.player.location_id)
            if n not in state.player.murdered_npcs]


def action_talk(state: GameState, gamedata: GameData) -> str | None:
    char = state.player
    npc_ids = _living_npcs_at(state, gamedata)
    if not npc_ids:
        ui.message("這裡沒有可攀談的人。", style="grey70")
        return None
    nid = ui.menu("與誰攀談?", [(n, gamedata.npcs[n]["name"]) for n in npc_ids], allow_back=True)
    if nid is None:
        return None
    while True:
        npc = gamedata.npcs[nid]
        disp = dialogue.disposition(char, gamedata, nid)
        ui.npc_panel(npc, disp)
        offered = dialogue.offered_quest(char, gamedata, nid)
        opts = []
        if offered:
            opts.append(("quest", f"接受委託:{gamedata.quests[offered]['name']}"))
        opts += [("persuade", "說服(口才)"), ("bribe", f"賄賂({dialogue.BRIBE_COST} 金)")]
        opts.append(("murder", "🔪 暗殺此人"))
        choice = ui.menu("對話", opts, allow_back=True)
        if choice is None:
            return None
        if choice == "quest":
            _accept_and_brief(state, gamedata, offered)
            return None
        elif choice == "persuade":
            r = dialogue.persuade(char, gamedata, nid, state.rng)
            state.time.advance(r["hours"])
            ui.message("對方頗為受用,好感提升。" if r["ok"] else "話不投機,對方有些不悅。",
                       style="green" if r["ok"] else "yellow")
            if r["tired"]:
                ui.message("舌乾口燥,話都說不利索了。", style="yellow")
            ui.show_events(r["skill_events"], gamedata)
        elif choice == "bribe":
            r = dialogue.bribe(char, gamedata, nid)
            ui.message(r["message"], style="green" if r["ok"] else "red")
        elif choice == "murder":
            return action_murder(state, gamedata, nid)


def action_murder(state: GameState, gamedata: GameData, nid: str) -> str | None:
    """謀殺一名無辜城民:重罪(高額賞金 + 惡名),但血債會引來黑暗兄弟會的青睞。

    回傳 'dead'(玩家在反抗中喪命)或 None。"""
    char = state.player
    name = gamedata.npcs[nid]["name"]
    ui.message("殺害手無寸鐵的無辜者是滔天重罪 —— 一旦動手,全城都會與你為敵。", style="red")
    if not ui.confirm(f"當真要取「{name}」的性命嗎?"):
        return None
    # 偷襲先機:看你潛行(背後一刀);旁人遲早會察覺尖叫
    victim = combat.spawn_creature(gamedata, "townsperson", state.rng)
    victim.name = name
    night = state.time.hour < 6 or state.time.hour >= 21
    got_drop = combat.try_stealth_approach(char, [victim], state.rng, gamedata, night, False, False)
    if got_drop:
        ui.message(f"你自{name}背後欺近,寒光一閃 ——", style="magenta")
    pb = formulas.prep_budget(char.skill("scout")) if got_drop else 0   # 潛殺成功也享偵查備戰
    result = run_battle(state, gamedata, victim, alerted=not got_drop, prep_budget=pb)
    if result == "dead":
        return "dead"
    if result == "fled":
        ui.message(f"你收手退去,{name}僥倖逃過一劫。", style="grey70")
        return None
    if result == "victory":
        res = brotherhood.record_murder(state, gamedata, nid)
        ui.rule("血債")
        ui.message(f"{name}倒在血泊之中 —— 你成了殺人兇手。", style="bold red")
        ui.message(f"消息驚動全城,{res['province']}懸起 {res['bounty']} 金的賞金,惡名加身。",
                   style="yellow")
        if not brotherhood.is_member(char):
            ui.message("……某雙眼睛,正從暗處注視著你的手藝。", style="magenta")
    return None


def guard_confrontation(state: GameState, gamedata: GameData) -> str | None:
    char = state.player
    province = crime.province_of(char, gamedata)
    # 武士特權:身為本省某城武士,小額賞金衛兵放行(大罪仍追緝)
    if court.is_thane_in_province(char, gamedata, province) \
            and crime.bounty(char, province) <= court.THANE_BOUNTY_FORGIVE:
        ui.message(f"「武士閣下!」衛兵認出你的身分,躬身讓道 —— {province}的小額賞金一筆勾銷。",
                   style="green")
        crime.clear_bounty(char, province)
        return None
    ui.message(f"城門衛兵攔住了你:「你在{province}的賞金是 {crime.bounty(char, province)} 金 —— 束手就擒!」",
               style="red")
    while crime.bounty(char, province) > 0:
        choice = ui.menu("如何應對?", [
            ("pay", f"繳清罰金({crime.bounty(char, province)} 金)"),
            ("jail", "乖乖入獄服刑"),
            ("resist", "拔劍反抗(與衛兵開戰)"),
        ])
        if choice == "pay":
            r = crime.pay_fine(char, gamedata)
            if r["ok"]:
                ui.message(f"你繳清了 {r['paid']} 金罰金,衛兵讓開了路。", style="green")
            else:
                ui.message(f"你付不起 {r['owed']} 金 —— 只能服刑或反抗。", style="yellow")
        elif choice == "jail":
            r = crime.serve_sentence(char, gamedata, state.time)
            ui.message(f"你被關押了 {r['hours']} 小時,{province}的賞金一筆勾銷。", style="grey70")
        elif choice == "resist":
            # 賞金越高,出動的衛兵越多(1–3 名)
            n = 1 + min(2, crime.bounty(char, province) // 80)
            guards = [combat.spawn_creature(gamedata, "city_guard", state.rng) for _ in range(n)]
            if run_battle(state, gamedata, guards) == "dead":
                return "dead"
            crime.add_bounty(char, province, 40)   # 拒捕罪加一等
            ui.message("你殺出重圍逃進巷弄 —— 但賞金又添了一筆,你仍是通緝犯。", style="red")
            return None
    return None


# ======================================================================
# 主迴圈
# ======================================================================
def game_loop(state: GameState, gamedata: GameData) -> None:
    while True:
        # 吸血鬼狀態先結算(潛伏轉化 / 階級升降),再呈現本回合
        for ev in vampirism.update(state, gamedata):
            if ev["kind"] == "turn":
                ui.rule("血色甦醒")
                ui.message("高燒退去,飢渴湧上 —— 你已不再是活人。從此夜行嗜血,直到詛咒解除或永滅。",
                           style="bold red")
            elif ev["kind"] == "stage" and ev.get("rising"):
                name = vampirism.STAGE_NAMES[ev["stage"]]
                ui.message(f"血之飢渴加深 —— 你進入「{name}」之境:力量更盛,卻更難見容於日光與世人。",
                           style="magenta")

        ui.rule()
        ui.status_line(state)
        ui.location_panel(state.player, gamedata)
        loc = world.current_location(state.player, gamedata)
        services = loc.get("services", [])

        player = state.player
        shunned = vampirism.is_shunned(player, state)   # 高階吸血鬼被世人拒於門外
        # --- 冒險 ---
        adventure: list = []
        if loc["type"] == "dungeon":
            adventure.append(("dungeon", "深入地城 ⚔"))
        if loc.get("danger", 0) > 0 and loc["type"] != "dungeon":
            adventure.append(("explore", "探索狩獵 ⚔"))
        adventure.append(("travel", "旅行"))
        adventure.append(("map", "世界地圖"))
        # --- 城區(分區域:市集區 / 公會區 / 廣場)---
        if shunned:
            ui.message("世人察覺了你的真面目,紛紛走避 —— 高階吸血鬼無法與人交易,先進食壓下飢渴吧。",
                       style="red")
        market: list = []     # 市集區:商業
        guilds: list = []     # 公會區:各公會分部 / 聖所
        plaza: list = []      # 廣場:旅店 / 訓練 / 告示 / 攀談 / 進食
        if "merchant" in services and not shunned:
            market.append(("shop", "商店"))
        if "armorer" in services or inventory.count_item(player, "repair_hammer") > 0:
            market.append(("repair", "修理裝備"))
        if "armorer" in services:
            market.append(("craft", "製革加工 🛠"))
        if "mages_guild" in services:
            guilds.append(("guild_mages", "法師公會"))   # 學習法術 + 入會/任務,進子選單
        if "fighters_guild" in services:
            guilds.append(("fg_hall", "戰士公會"))
        if "thieves_guild" in services:
            guilds.append(("tg_hall", "盜賊公會"))
        # 黑暗兄弟會聖所:唯有入會者才知其所在(血債招募後解鎖)
        if "dark_brotherhood" in services and brotherhood.is_member(player):
            guilds.append(("db_hall", "黑暗兄弟會聖所 🗡"))
        if player.is_vampire and loc["type"] in ("town", "city"):
            plaza.append(("feed", "🩸 吸血進食(獵取活人,重置飢餓)"))
        if "inn" in services and not shunned:
            plaza.append(("inn", "旅店(10金)"))
        if "trainer" in services and not shunned:
            plaza.append(("trainer", "訓練師"))
        if "task_board" in services:
            plaza.append(("board", "告示板"))
        if _living_npcs_at(state, gamedata) and not shunned:
            plaza.append(("talk", "與人攀談"))
        court: list = []     # 領主區:謁見領主(Phase 1);後續加委託/效忠/外交
        if gamedata.ruler_at(player.location_id) and loc["type"] in ("city", "town") and not shunned:
            court.append(("court", "謁見領主"))
        # 只列出有內容的城區;頂層只顯示區域入口(進入後才見區內服務)
        districts = []
        if market:
            districts.append(("_market", "市集區 🛒", market))
        if guilds:
            districts.append(("_guilds", "公會區 ⚜", guilds))
        if plaza:
            districts.append(("_plaza", "廣場 🏛", plaza))
        if court:
            districts.append(("_court", "領主區 👑", court))
        city_group = [(k, lbl) for k, lbl, _ in districts]
        # --- 施法與製作 ---
        craft: list = []
        if player.spells:
            craft.append(("cast", "施法增益"))
        if powers.usable_in(player, state, gamedata, "utility"):
            pdef = powers.power_def(powers.power_id(player, gamedata))
            craft.append(("power", f"星座之力({pdef['name']})"))
        craft.append(("alchemy", "煉金"))
        if any(gamedata.item(s["id"]).get("kind") == "poison" for s in player.inventory):
            craft.append(("coat", "塗毒"))
        if enchanting.filled_soul_gems(player, gamedata):
            craft.append(("enchant", "附魔"))
        # --- 角色與物品 ---
        character: list = [("quests", "任務日誌"), ("inventory", "背包"),
                           ("practice", "練習技能"), ("rest", "原地休息"), ("sheet", "角色卡")]
        if player.can_level_up():
            character.insert(0, ("levelup", "★ 升級"))
        # --- 系統 ---
        system = [("save", "存檔"), ("retire", "隱退江湖"), ("quit", "回主選單")]

        choice = ui.grouped_menu("要做什麼?", [
            ("冒險", adventure), ("城區", city_group),
            ("製作", craft), ("人物", character), ("系統", system),
        ])
        # 選了某個城區 → 進入該區的子選單挑實際服務(返回則回到城區)
        _dist = next((d for d in districts if d[0] == choice), None)
        if _dist:
            choice = ui.menu(_dist[1], _dist[2], allow_back=True)
            if choice is None:
                continue
        died = None
        if choice == "map":
            ui.world_map(player, gamedata)
        elif choice == "dungeon":
            died = action_dungeon(state, gamedata)
        elif choice == "explore":
            died = action_explore(state, gamedata)
        elif choice == "travel":
            died = action_travel(state, gamedata)
        elif choice == "shop":
            action_shop(state, gamedata)
        elif choice == "inn":
            action_inn(state, gamedata)
        elif choice == "feed":
            action_feed(state, gamedata)
        elif choice == "trainer":
            action_trainer(state, gamedata)
        elif choice == "court":
            died = action_court(state, gamedata)
        elif choice == "guild_mages":
            mg_opts = [("spells", "學習法術"), ("mg_hall", "公會事務(入會 / 任務)")]
            if player.is_vampire:
                mg_opts.append(("cure", "✦ 探詢血咒的解法"))
            sub = ui.menu("法師公會", mg_opts, allow_back=True)
            if sub == "spells":
                action_spell_vendor(state, gamedata)
            elif sub == "mg_hall":
                action_guild_hall(state, gamedata, "mages_guild")
            elif sub == "cure":
                action_vampire_cure(state, gamedata)
        elif choice == "fg_hall":
            action_guild_hall(state, gamedata, "fighters_guild")
        elif choice == "tg_hall":
            action_guild_hall(state, gamedata, "thieves_guild")
        elif choice == "db_hall":
            died = action_sanctuary(state, gamedata)
        elif choice == "board":
            action_board(state, gamedata)
        elif choice == "talk":
            died = action_talk(state, gamedata)
        elif choice == "quests":
            action_quest_log(state, gamedata)
        elif choice == "repair":
            action_repair(state, gamedata)
        elif choice == "craft":
            action_craft(state, gamedata)
        elif choice == "cast":
            action_cast_self(state, gamedata)
        elif choice == "power":
            action_use_power(state, gamedata)
        elif choice == "alchemy":
            action_alchemy(state, gamedata)
        elif choice == "coat":
            action_coat_weapon(state, gamedata)
        elif choice == "enchant":
            action_enchant(state, gamedata)
        elif choice == "inventory":
            action_inventory(state, gamedata)
        elif choice == "practice":
            action_practice(state, gamedata)
        elif choice == "rest":
            died = action_rest(state, gamedata)
        elif choice == "sheet":
            ui.character_sheet(state.player, gamedata)
        elif choice == "levelup":
            action_level_up(state, gamedata)
        elif choice == "save":
            action_save(state)
        elif choice == "retire":
            if ui.confirm("確定就此封劍隱退、結束這趟冒險?"):
                end_run(state, gamedata, "retire")
                return
        elif choice == "quit":
            if ui.confirm("離開這趟冒險、回到主選單?(未存檔的進度會遺失)"):
                if ui.confirm("離開前要存檔嗎?"):
                    action_save(state)
                return

        if died == "dead":
            end_run(state, gamedata, "death")
            return


def main() -> None:
    gamedata = get_gamedata()
    ui.banner()

    while True:   # 主選單迴圈:一趟冒險(死亡/隱退/離開)結束後回到這裡
        opts = [("new", "新遊戲")]
        if SAVE_PATH.exists():
            opts.append(("load", "讀取存檔"))
        opts.append(("quit", "離開遊戲"))
        choice = ui.menu("主選單", opts)

        if choice == "quit":
            ui.message("再會,旅人。", style="yellow")
            return
        if choice == "load":
            state = GameState.load(SAVE_PATH)
            ui.message(f"歡迎回來,{state.player.name}。", style="green")
        else:
            mode = ui.menu("選擇遊戲模式", [
                ("adventure", "冒險模式 —— 死亡可讀檔重來,適合悠閒探索"),
                ("legend", "傳奇模式 —— 永久死亡(roguelike),一條命定生死"),
            ])
            seed = make_seed(ui.ask_text("世界種子(留空=隨機;可輸入數字或任意文字)", default=""))
            char = create_character(gamedata, RNG(seed))
            state = GameState(player=char, rng=RNG(seed), game_mode=mode)
            ui.character_sheet(char, gamedata)
            ui.message(f"世界種子:{seed}（記下它,即可重玩同一個世界與命運)", style="grey70")

        game_loop(state, gamedata)


if __name__ == "__main__":
    main()
