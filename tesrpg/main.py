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
from tesrpg.systems import (achievements, aiwar, alchemy, boons, brotherhood, combat, court, crafting, crime, dialogue, diseases, dungeon,
                            dungeoncrawl, enchanting, events, factions, housing, inventory, landmarks, legacy,
                            lycanthropy, magic, mastery, mounts, party, politics, potion_buff, powers,
                            progression, quests, race_ability, skooma, smithing, stats, undercover, vampirism, warband, world, worldpulse, worldstate)
from tesrpg.ui import console as ui

SAVE_PATH = Path.home() / ".tesrpg" / "save.json"


# ======================================================================
# 角色創建
# ======================================================================
def create_character(gamedata: GameData, rng: RNG):
    ui.rule("創建角色")
    if ui.confirm("快速開始(隨機種族/職業)?"):
        return _quick_character(gamedata, rng)

    # 逐步創角:每步可返回上一步(選單按「返回」→ 退回重選);走完進總覽,可逐項改、確認才生成。
    # 角色直到 build_character 才真正生成 → 全程零存檔、零遊戲時間,任何重選皆無損失。
    sex = _pick_sex()                     # 首步:無上一步
    race = sign = origin_id = class_id = custom = name = None
    STEPS = ("race", "sign", "origin", "class", "name", "review")
    i = 0
    while i < len(STEPS):
        step = STEPS[i]
        if step == "race":
            r = _pick_race(gamedata, allow_back=True)
            if r is None:                 # 返回 → 退回性別(再選一次)
                sex = _pick_sex()
            else:
                race, i = r, i + 1
        elif step == "sign":
            sg = _pick_sign(gamedata, allow_back=True)
            sign, i = (sign, i - 1) if sg is None else (sg, i + 1)
        elif step == "origin":
            o = _choose_origin(gamedata, allow_back=True)
            origin_id, i = (origin_id, i - 1) if o is None else (o, i + 1)
        elif step == "class":
            cid = _choose_class(gamedata, origin_id, allow_back=True)
            if cid is None:
                i -= 1
            else:
                class_id = cid
                custom = _create_custom_class(gamedata) if cid == "custom" else None
                i += 1
        elif step == "name":
            name = ui.ask_text("姓名", default=creation.random_name(gamedata, race, sex, rng))
            i += 1                        # 文字輸入無返回 → 進總覽(可在總覽改名)
        elif step == "review":
            action = _creation_review(gamedata, sex, race, sign, origin_id, class_id, custom, name)
            if action == "confirm":
                break
            if action == "sex":
                sex = _pick_sex(allow_back=True) or sex
            elif action == "race":
                race = _pick_race(gamedata, allow_back=True) or race
            elif action == "sign":
                sign = _pick_sign(gamedata, allow_back=True) or sign
            elif action == "origin":
                origin_id = _choose_origin(gamedata, allow_back=True) or origin_id
            elif action == "class":
                cid = _choose_class(gamedata, origin_id, allow_back=True)
                if cid is not None:
                    class_id = cid
                    custom = _create_custom_class(gamedata) if cid == "custom" else None
            elif action == "name":
                name = ui.ask_text("姓名", default=name)
            # 改完留在總覽(i 不變)→ 再確認

    char = creation.build_character(
        gamedata, name=name, sex=sex, race=race, birthsign=sign,
        class_id=class_id, custom_class=custom, origin_id=origin_id, rng=rng,
    )
    ui.message(f"歡迎來到 Tamriel,{char.name}。", style="bold green")
    return char


def _pick_sex(allow_back: bool = False) -> str | None:
    return ui.menu("性別", [("male", "男"), ("female", "女")], allow_back=allow_back)


def _pick_race(gamedata: GameData, allow_back: bool = False) -> str | None:
    return ui.menu("種族", [(rid, f"{r['name']} — {r['ability']}", _race_chips(gamedata, r))
                            for rid, r in gamedata.races.items()], allow_back=allow_back)


def _pick_sign(gamedata: GameData, allow_back: bool = False) -> str | None:
    return ui.menu("出生星座", [(sid, f"{s['name']} — {s['note']}", _sign_chips(s))
                               for sid, s in gamedata.birthsigns.items()], allow_back=allow_back)


def _creation_review(gamedata: GameData, sex, race, sign, origin_id, class_id, custom, name) -> str:
    """創角總覽:列出目前選擇,可逐項改;回傳 'confirm' 或要改的欄位 key(改完回到總覽)。"""
    rn = gamedata.races[race]["name"]
    sn = gamedata.birthsigns[sign]["name"]
    on = gamedata.origins.get(origin_id, {}).get("name", origin_id)
    cn = custom["name"] if custom else gamedata.classes.get(class_id, {}).get("name", class_id)
    sx = "男" if sex == "male" else "女"
    return ui.menu(f"確認開局 —— {name}", [
        ("confirm", "✔ 確認,以此踏上 Tamriel 之旅"),
        ("race", f"改種族(目前:{rn})"),
        ("sign", f"改星座(目前:{sn})"),
        ("origin", f"改開局(目前:{on})"),
        ("class", f"改職業(目前:{cn})"),
        ("sex", f"改性別(目前:{sx})"),
        ("name", f"改名字(目前:{name})"),
    ])


# 開局分類(兩層選單:24 種太長 → 先選一類、再選開局)。新增開局未列入者自動歸「浪人 · 處境」。
ORIGIN_CATEGORIES = [
    ("⚔ 戰士 · 近戰", ["sellsword", "fighters_recruit", "alikr_blade", "orc_outcast",
                       "legion_veteran", "caravan_guard", "knight_aspirant",
                       "hist_warden", "oathbound_paladin", "desert_spellsword", "cloud_monk"]),
    ("✦ 法師 · 法術", ["mage_initiate", "temple_healer", "reach_witch",
                       "marsh_conjurer", "tribunal_battlemage", "arcane_scholar", "marsh_healer"]),
    ("🗡 潛行 · 弓手", ["dark_initiate", "guild_thief", "tomb_seeker", "dockside_stowaway",
                       "wood_hunter", "ranger_scout"]),
    ("🩸 特殊血脈", ["nightborn", "beast_blooded"]),
    ("🧭 浪人 · 處境", ["newcomer", "fugitive", "pilgrim", "fallen_noble",
                       "shipwreck_survivor", "ashlander", "wandering_bard", "khajiit_trader"]),
]


def _choose_origin(gamedata: GameData, allow_back: bool = False) -> str | None:
    """兩層開局選單:先選類別 → 看該類資訊面板 → 選開局。
    類別選單可返回(allow_back → 回上一步,回傳 None);開局卡選單返回 → 退回類別(內層 always-on)。"""
    listed = {oid for _, oids in ORIGIN_CATEGORIES for oid in oids}
    extra = [oid for oid in gamedata.origins if oid not in listed]   # 安全網:漏歸類者進浪人
    cats = [(lbl, [o for o in oids if o in gamedata.origins] + (extra if i == len(ORIGIN_CATEGORIES) - 1 else []))
            for i, (lbl, oids) in enumerate(ORIGIN_CATEGORIES)]
    cats = [(lbl, oids) for lbl, oids in cats if oids]
    while True:
        ui.clear_screen()                     # 進類別選單前清 #screen → 沖掉上一輪 picker 的開局一覽面板(免殘留)
        cat = ui.menu("開局背景(不一樣的人生)—— 先選一類",
                      [(lbl, f"{lbl}（{len(oids)} 種)") for lbl, oids in cats], allow_back=allow_back)
        if cat is None:                       # 類別選單返回 → 退回上一步(星座);#screen 已於本圈頂清乾淨
            return None
        pick = ui.origin_picker(gamedata, dict(cats)[cat])   # 一覽即選單:點開局卡(web)/輸入編號(終端)
        if pick is not None:
            ui.clear_screen()                 # 選定 → 沖開局一覽面板,讓下一步(職業)從乾淨畫面開始
            return pick


def _choose_class(gamedata: GameData, origin_id: str, allow_back: bool = False) -> str | None:
    """選職業:把契合所選出身的職業標★推薦並排到最前(不過濾、不強制——自由組合保留)。

    出身的 `classes` 欄(origins.json,選用)是純 UI 推薦清單:只排序/標記,不碰屬性/技能(守 R18)。
    出身沒列推薦(處境型開局,適配任何職業)時 → 不排序、不標★、標題回「職業」。
    """
    odef = gamedata.origins.get(origin_id, {})
    rec = set(odef.get("classes", []))
    ordered = sorted(gamedata.classes.items(), key=lambda kv: kv[0] not in rec)  # 推薦在前(穩定)
    class_opts = []
    for cid, c in ordered:
        chips = _class_chips(c)
        if cid in rec:
            chips = [{"text": "★推薦", "tone": "gold"}] + chips
        class_opts.append((cid, f"{c['name']} — {c['desc']}", chips))
    class_opts.append(("custom", "自訂職業（選專精、偏好屬性、主修技能）"))
    title = f"職業(★ = 契合你的出身「{odef.get('name', '')}」)" if rec else "職業"
    return ui.menu(title, class_opts, allow_back=allow_back)


def _intro_quest_briefing(state: GameState, gamedata: GameData) -> None:
    """創角後、入主迴圈前:若有起手任務,提示其敘事動機與第一個目標(單次)。"""
    char = state.player
    for qid in char.quests:
        q = gamedata.quests.get(qid, {})
        if q.get("source") == "origin":
            ui.rule("你的去向")
            ui.message(q.get("text", ""), style="bold cyan")
            ui.message("起手任務:" + quests.objective_text(char, gamedata, qid), style="white")
            break


def _quick_character(gamedata: GameData, rng: RNG):
    sex = rng.choice(["male", "female"])
    race = rng.choice(list(gamedata.races.keys()))
    sign = rng.choice(list(gamedata.birthsigns.keys()))
    origin_id = rng.choice(list(gamedata.origins.keys()))
    rec = gamedata.origins[origin_id].get("classes")   # 出身有推薦職業 → 隨機也抽契合的,免得身分與本事打架
    class_id = rng.choice(rec) if rec else rng.choice(list(gamedata.classes.keys()))
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


# --- 創角 build chips:把種族/星座/職業的數值加成做成選單上的視覺小標 -------------
_RESIST_CN_MAIN = {"fire": "火焰", "frost": "冰霜", "shock": "雷電",
                   "magic": "魔法", "poison": "毒素", "disease": "疾病"}


def _attr_chips(attr_mods: dict) -> list[dict]:
    out = []
    for attr, v in attr_mods.items():
        if not v:
            continue
        name = formulas.ATTRIBUTE_NAMES.get(attr, attr)
        out.append({"text": f"{name}{'+' if v > 0 else '−'}{abs(v)}",
                    "tone": "green" if v > 0 else "red"})
    return out


def _race_chips(gamedata: GameData, r: dict) -> list[dict]:
    chips = _attr_chips(r.get("attr_mods", {}))
    if r.get("magicka_bonus"):
        chips.append({"text": f"魔力+{r['magicka_bonus']}", "tone": "gold"})
    for sid, v in r.get("skill_bonuses", {}).items():
        if v:
            chips.append({"text": f"{gamedata.skill_name(sid)}+{v}", "tone": "cyan"})
    for elem, v in r.get("resist", {}).items():
        if v:
            name = _RESIST_CN_MAIN.get(elem, elem)
            chips.append({"text": f"抗{name}{v}%" if v > 0 else f"{name}弱{abs(v)}%",
                          "tone": "gold" if v > 0 else "red"})
    if r.get("racial_power"):                       # R61:種族每日主動威能(比照星座「異能×N」)
        chips.append({"text": "種族威能", "tone": "mag"})
    if r.get("passive"):                            # R61:種族持續被動天賦
        chips.append({"text": "天賦", "tone": "mag"})
    return chips


def _sign_chips(s: dict) -> list[dict]:
    chips = _attr_chips(s.get("attr_mods", {}))
    if s.get("magicka_bonus"):
        chips.append({"text": f"魔力+{s['magicka_bonus']}", "tone": "gold"})
    if s.get("powers"):
        chips.append({"text": f"異能×{len(s['powers'])}", "tone": "mag"})
    return chips


def _class_chips(c: dict) -> list[dict]:
    chips = [{"text": f"專精·{formulas.SPEC_NAMES.get(c['spec'], c['spec'])}", "tone": "gold"}]
    for a in c.get("favored_attributes", []):
        chips.append({"text": f"★{formulas.ATTRIBUTE_NAMES.get(a, a)}", "tone": "gold"})
    chips.append({"text": f"主修{len(c.get('major_skills', []))}", "tone": "cyan"})
    return chips


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
    if char.base_skill(sid) >= formulas.SKILL_CAP:
        ui.message(f"{gamedata.skill_name(sid)} 已達上限,無法再從練習中精進。", style="grey70")
        return

    # 一次可練多小時:每小時 = 一輪 practice;體力足以全效的小時數當預設,之後成效遞減
    fat_cost = pdef["fatigue"]
    fresh = max(1, char.fatigue // fat_cost) if fat_cost > 0 else 24
    hours = ui.ask_int(
        f"練習幾小時?(每小時耗 {fat_cost} 體力;體力足以全效約 {min(fresh, 24)} 小時,之後成效減半)",
        default=min(fresh, 24), lo=1, hi=24)

    total_hours, tired_hours, events = 0, 0, []
    for _ in range(hours):
        if char.base_skill(sid) >= formulas.SKILL_CAP:       # 練到滿級就停,不空耗時間/體力
            break
        xp, hrs, tired = progression.practice_cost(char, gamedata, sid)
        events += progression.use_skill(char, gamedata, sid, xp)
        state.time.advance(hrs)
        total_hours += hrs
        tired_hours += 1 if tired else 0

    ui.message(f"你{pdef['label']}……(共 {total_hours} 小時)")
    if tired_hours:
        ui.message(f"其中 {tired_hours} 小時體力不濟、成效減半 —— 先休息會更有效率。", style="yellow")
    ui.show_events(events, gamedata)
    if char.base_skill(sid) >= formulas.SKILL_CAP:
        ui.message(f"{gamedata.skill_name(sid)} 已練至上限。", style="green")
    elif not events:
        need = formulas.skill_threshold(char.skill(sid))
        prog = char.skill_xp.get(sid, 0.0)
        ui.message(f"{gamedata.skill_name(sid)} 熟練度 {prog:.1f}/{need:.1f} → 下一點",
                   style="grey70")


def action_rest(state: GameState, gamedata: GameData) -> str | None:
    hours = ui.ask_int("休息幾小時?", default=8, lo=1, hi=24)
    char = state.player
    no_magicka_regen = char.birthsign == "atronach"

    char.fatigue = min(char.max_fatigue, char.fatigue + char.max_fatigue * hours / 8)
    # 亞龍癒膚(R61):休息 HP 回復加成(非亞龍 ×1 → 不變)
    char.health = min(char.max_health, char.health
                      + char.max_health * hours / 24 * (1 + race_ability.histskin_factor(char, gamedata)))
    if not no_magicka_regen:   # 意志「施法續航」:回魔速率隨意志(base-40 中性 ×1.0)。高精靈高貴血脈再乘加成(非高精靈 ×1)
        rate = (hours / 12 * formulas.magicka_regen_rest_factor(char.attr("willpower"))
                * race_ability.magicka_regen_factor(char, gamedata))
        char.magicka = min(char.max_magicka, char.magicka + char.max_magicka * rate)

    party.heal(char, gamedata, hours / 24)   # 同伴隨休息回復(負傷者康復後可再上陣)
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


def _prompt_mastery_choice(state: GameState, gamedata: GameData, node: dict) -> bool:
    """呈現單一里程碑節點的二選一。回傳 True=已選/已授予,False=玩家選擇稍後再決定。

    絕不在戰鬥中呼叫(run_battle 全域 patch ui.menu);只在升級畫面/回城安全點。
    """
    char = state.player
    opts = mastery._choosable_options(node)
    if not opts:
        return True
    if len(opts) == 1:                       # 退化節點:無真正選擇 → 直接授予,不打擾
        mastery.choose(char, gamedata, node["id"], opts[0]["opt_id"])
        ui.message(f"✦ 技能里程碑「{opts[0]['name']}」確立!", style="bold magenta")
        return True
    sk = gamedata.skill_name(node["skill"])
    ui.rule(f"技能里程碑 · {sk} {node['threshold']}")
    menu_opts = [(o["opt_id"], f"{o['name']}　{o['desc']}") for o in opts]
    choice = ui.menu("你已臻宗師之境 —— 擇一銘刻你的道(此選擇永久):", menu_opts, allow_back=True)
    if choice is None:                       # 稍後再選(留 pending,下次安全點再問)
        return False
    opt = mastery.choose(char, gamedata, node["id"], choice)
    if opt:
        ui.message(f"✦ 你選擇了「{opt['name']}」,此道已定。", style="bold magenta")
    return True


def _drain_mastery_choices(state: GameState, gamedata: GameData) -> None:
    """在安全互動點消化所有待決的里程碑二選一;玩家選擇稍後 → 本回合不再追問。"""
    for node in mastery.pending_choices(state.player, gamedata):
        if not _prompt_mastery_choice(state, gamedata, node):
            break


def action_level_up(state: GameState, gamedata: GameData) -> None:
    char = state.player
    if not char.can_level_up():
        ui.message("還不能升級 —— 多練些技能累積等級經驗吧。", style="yellow")
        return

    ui.rule(f"升級 → Lv {char.level + 1}")

    # 自由分配屬性點(逐點挑屬性,clamp 100;選到已滿的不耗點,重挑)。
    # R64:資源已純屬性驅動(endurance→生命·int→魔力·str/wil/agi/end→體力)→ 無資源三選一,屬性點 4→5。
    points = formulas.LEVELUP_ATTRIBUTE_POINTS
    alloc: dict[str, int] = {}

    def _cur(a):   # 該屬性「含本次尚未送出的分配」的當前值
        return char.attr(a) + alloc.get(a, 0)

    ui.message(f"分配 {points} 點屬性(可集中或分散):", style="bold")
    remaining = points
    while remaining > 0:
        if all(_cur(a) >= formulas.ATTRIBUTE_CAP for a in formulas.ATTRIBUTES):
            break   # 八屬性全滿(極高等),無處可加
        opts = [(a, f"{formulas.ATTRIBUTE_NAMES[a]} {_cur(a)} — {formulas.ATTRIBUTE_FUNCTION[a]}"
                 + ("（已滿）" if _cur(a) >= formulas.ATTRIBUTE_CAP else ""))
                for a in formulas.ATTRIBUTES]
        a = ui.menu(f"剩 {remaining} 點 →", opts)
        if _cur(a) < formulas.ATTRIBUTE_CAP:
            alloc[a] = alloc.get(a, 0) + 1
            remaining -= 1

    summary = progression.apply_level_up(char, gamedata, alloc)
    ui.message(f"★ 升級!現在是 Lv {summary['level']}。", style="bold yellow")
    for a, g in summary["attr_gains"].items():
        ui.message(f"  {formulas.ATTRIBUTE_NAMES[a]} +{g}", style="green")
    ui.message("  三圍已回滿。", style="green")
    if summary["can_level_again"]:
        ui.message("  你還能再升一級!", style="yellow")
    _drain_mastery_choices(state, gamedata)   # 升級是「你成長了」的自然節拍 → 順勢二選一


def action_save(state: GameState) -> None:
    state.save(SAVE_PATH)
    ui.message(f"已存檔 → {SAVE_PATH}", style="green")


# ======================================================================
# 戰鬥
# ======================================================================
def _choose_enemy_target(state: GameState, gamedata: GameData, enemies: list, allies: list):
    """從存活敵人中選一個目標(僅一個時自動選)。"""
    alive = [e for e in enemies if combat.is_alive(e)]
    if len(alive) == 1:
        return alive[0]
    if ui._web is not None:        # web:重新顯示戰場(blocks 每幀清空),讓敵方卡片可點選目標
        ui.combat_status_group(state.player, allies, enemies, gamedata)
    opts = [(str(i), f"{e.name}（{int(e.health)}/{e.max_health})") for i, e in enumerate(alive)]
    return alive[int(ui.menu("攻擊哪個目標?", opts))]


def _choose_ally_target(state: GameState, gamedata: GameData, allies: list):
    """從存活同伴中選一個施放(無同伴回 None;僅一個時自動選)。供治療師援護法術。"""
    living = [a for a in allies if combat.is_alive(a)]
    if not living:
        return None
    if len(living) == 1:
        return living[0]
    if ui._web is not None:
        ui.combat_status_group(state.player, allies, [], gamedata)
    opts = [(str(i), f"{a.name}（{int(a.health)}/{a.max_health})") for i, a in enumerate(living)]
    return living[int(ui.menu("援護哪個同伴?", opts))]


def _has_standard(char) -> bool:
    """騎士是否已立戰旗(存 active_effects 的常駐 stance)。"""
    return any(e.get("kind") == "battle_standard" and e.get("turns", 0) > 0
               for e in getattr(char, "active_effects", []))


def _has_rally(char) -> bool:
    """口才是否已立戰陣號令(存 active_effects 的常駐 stance;鼓舞盟友增傷)。"""
    return any(e.get("kind") == "rally_banner" and e.get("turns", 0) > 0
               for e in getattr(char, "active_effects", []))


def _on_deathmark_cd(enemy) -> bool:
    """該敵是否在致命烙印冷卻中(防每回合重標)。"""
    return any(e.get("kind") == "deathmark_cd" and e.get("turns", 0) > 0
               for e in getattr(enemy, "active_effects", []))


def _triage_armed(char) -> bool:
    """治療師「戰地搶救」是否已武裝(下一道治療折扣;存 active_effects)。"""
    return any(e.get("kind") == "triage_ready" and e.get("turns", 0) > 0
               for e in getattr(char, "active_effects", []))


def _choose_combat_action(state: GameState, gamedata: GameData, enemies: list, allies: list,
                          vanish_used: int = 0, mounted: bool = False, first_round: bool = False,
                          charm_used: bool = False):
    """回傳玩家本回合的行動 dict:{type, spell_id?, target?}。

    mounted/first_round:野外騎乘遭遇的第一回合 → 開放坐騎戰技(戰馬衝鋒 / 獵馬騎射)。
    """
    player = state.player
    # 每次進入(含子選單「返回」遞迴)都重顯戰場 → 動作選單恆見敵情(web 每幀清空重繪)。
    ui.combat_status_group(player, allies, enemies, gamedata)
    if getattr(player, "beast_form", False):     # 獸形:爪擊 /(達階)恫嚇之嚎 / 變回人形 / 逃跑
        opts = [("attack", f"獸爪猛擊（{combat.effective_weapon_name(player, gamedata)})")]
        if lycanthropy.can_howl(player, state) and player.fatigue >= lycanthropy.HOWL_FATIGUE:
            opts.append(("howl", f"恫嚇之嚎（懼敵 · 耗 {lycanthropy.HOWL_FATIGUE} 體力)"))
        opts += [("revert", "變回人形"), ("flee", "逃跑")]
        choice = ui.menu("你的回合(獸形)", opts)
        if choice == "attack":
            return {"type": "attack", "target": _choose_enemy_target(state, gamedata, enemies, allies)}
        return {"type": choice}
    _gs = inventory.is_great_shield(gamedata, player.equipped.get("shield"))
    opts = [("attack", f"攻擊（{combat.effective_weapon_name(player, gamedata)}{' · 盾擊' if _gs else ''})")]
    castable = [s for s in player.spells if magic.can_cast(player, gamedata, s)]
    if castable:
        opts.append(("cast", "施法"))
    if powers.usable_in(player, state, gamedata, "combat"):
        pid = powers.power_id(player, gamedata)
        if pid == "beast_form":
            opts.append(("power", "🐺 獸化變身（化身嗜血巨狼)"))
        else:
            plabel = "吸血之力" if player.is_vampire else "星座之力"
            opts.append(("power", f"{plabel}({powers.power_def(pid)['name']})"))
    # 種族之力(R61):與星座威能槽不相交的第二槽 —— 戰系種族每日一招。控場威能須有合類存活敵才提供。
    if powers.racial_available(player, state, gamedata, "combat"):
        rpid = powers.racial_power_id(player, gamedata)
        if "control" not in powers.racial_def(rpid)["effect"] or powers.racial_combat_targets(rpid, enemies, gamedata):
            opts.append(("racial_power", f"🐾 種族之力（{powers.racial_def(rpid)['name']})"))
    if (not inventory.is_dual_wielding(player, gamedata)
            and not inventory.is_two_handed(gamedata, player.weapon)):   # 雙持/雙手武器占雙手 → 不能格擋
        opts.append(("block", "格擋"))
    vcap = combat.vanish_cap(player, gamedata)
    if combat.can_vanish(player, gamedata) and vanish_used < vcap:
        n_alive = len([e for e in enemies if combat.is_alive(e)])
        pct = int(combat.vanish_chance(player, n_alive, vanish_used, gamedata) * 100)
        left = "∞" if vcap >= 99 else (vcap - vanish_used)
        # R71:隱遁不再閃避(敵照常攻擊)→ 純重獲偷襲先機;標籤如實說明
        opts.append(("vanish", f"隱遁再襲（重獲偷襲·不閃避·成功率 {pct}%,剩 {left} 次)"))
    # 弓手「散兵」武技:持弓 + 選了對應 marksman 里程碑才開放(瞄準射 75 / 牽制射 50 / 散兵走位 50)
    # —— 不再「裝備弓即免費全給」;散兵走位選了即可用(解鎖自帶,不再要 sneak 隱遁),仍受每場 vanish 次數上限。
    if (gamedata.item(player.weapon).get("archetype") == "bow"
            and not getattr(player, "beast_form", False)):
        if mastery.has_bow_technique(player, gamedata, "aimed"):
            opts.append(("aimed", "瞄準射（蓄力強擊 · 額外耗體)"))
        if mastery.has_bow_technique(player, gamedata, "crippling"):
            opts.append(("crippling", "牽制射（削弱目標攻勢)"))
        if mastery.has_bow_technique(player, gamedata, "skirmish") and vanish_used < vcap:
            opts.append(("skirmish", "散兵走位（射一箭後遁走)"))
    # 坐騎戰技(僅野外騎乘遭遇的第一回合;戰馬+近戰=衝鋒、獵馬+弓=騎射)
    if mounted and first_round and mounts.can_charge(player, gamedata, True):
        opts.append(("charge", "🐎 衝鋒（坐騎開場突擊 · 長槍藉馬勢洞穿)"))
    if mounted and first_round and mounts.can_skirmish_ride(player, gamedata, True):
        opts.append(("skirmish_ride", "🏹 騎射（馬背放箭 · 大幅提升閃避)"))
    # 戰士「盾牆」:持盾 + 格擋達門檻 → 立/撤防禦架勢(前向減傷 + 嘲諷 + 護同袍 · 耗體力)
    if (player.equipped.get("shield") and player.base_skill("block") >= SHIELD_WALL_BLOCK_GATE
            and not inventory.is_dual_wielding(player, gamedata)
            and not inventory.is_two_handed(gamedata, player.weapon)):   # 雙手武器無盾 → 自然無盾牆(舊存檔保險)
        if combat.has_shield_wall(player):
            opts.append(("wall", "撤下盾牆"))
        elif player.fatigue > SHIELD_WALL_UPKEEP:   # 須有體力維持 → 體力耗盡後不可免費再立(盾牆是有限防禦資源,堵 fatigue-0 永久免費坦)
            opts.append(("wall", "🛡 立盾牆（減傷·嘲諷·護同袍 · 每回合耗體)"))
    # 騎士「戰旗」:幻術達門檻 → 立戰旗(全隊不需重施的增傷光環 + 自身護甲);已立則不重複
    if (player.base_skill("illusion") >= STANDARD_ILLUSION_GATE and not _has_standard(player)
            and player.magicka >= STANDARD_COST_MAGICKA):
        opts.append(("standard", "🚩 立戰旗（鼓舞全隊增傷 · 耗魔體)"))
    # 口才「戰陣號令」:選了里程碑 + 體力足 → 立號令(全隊增傷光環;純耗體不耗魔);已立則不重複
    if (mastery.has_rally(player, gamedata) and not _has_rally(player)
            and player.fatigue >= RALLY_FATIGUE):
        opts.append(("rally", "📣 號令（鼓舞全隊增傷 · 耗體)"))
    # 吸血鬼「魅惑凝視」:轉化後 + 體力足 + 本場未用 → 迷惑一敵使其恐懼不進攻(每場一次;R56)
    if (vampirism.is_vampire(player) and not charm_used
            and player.fatigue >= VAMPIRE_CHARM_FATIGUE
            and any(combat.is_alive(e) for e in enemies)):
        opts.append(("vampire_charm", f"🩸 魅惑凝視（迷惑一敵 · 使其恐懼不進攻 · 耗 {VAMPIRE_CHARM_FATIGUE} 體力)"))
    # 刺客「致命烙印」:選了里程碑 + 潛行達門檻 + 體力足 → 標記一敵(後續近戰破甲)
    _dm = mastery.deathmark(player, gamedata)
    if (_dm and player.base_skill("sneak") >= _dm.get("sneak_gate", 50)
            and player.fatigue >= _dm.get("fatigue_cost", 15)
            and any(combat.is_alive(e) and not combat._has_deathmark(e)
                    and not _on_deathmark_cd(e) for e in enemies)):
        opts.append(("deathmark", f"🔪 致命烙印（標記一敵 · 耗 {_dm.get('fatigue_cost', 15)} 體力)"))
    opts.append(("flee", "逃跑"))
    choice = ui.menu("你的回合", opts)

    if choice == "attack":
        return {"type": "attack", "target": _choose_enemy_target(state, gamedata, enemies, allies)}
    if choice == "cast":
        if ui._web is not None:    # web:blocks 每幀清空 → 選法術時重顯戰場,免「敵狀態丟失」
            ui.combat_status_group(player, allies, enemies, gamedata)
        spell_opts = [(s, f"{gamedata.spells[s]['name']}"
                       f"（{magic.effective_cost(player, gamedata, s)} 魔力) · "
                       f"{ui.spell_effect_summary(gamedata, s)}")
                      for s in castable]
        sid = ui.menu("施放哪道法術?", spell_opts, allow_back=True)
        if sid is None:
            return _choose_combat_action(state, gamedata, enemies, allies, vanish_used,
                                         mounted, first_round, charm_used)   # 補 charm_used:施法→返回重入不得重置「每場一次」魅惑
        tk = gamedata.spells[sid]["target"]
        if tk == "enemy":
            target = _choose_enemy_target(state, gamedata, enemies, allies)
        elif tk == "ally":                       # 治療師援護:選一個同伴施放
            target = _choose_ally_target(state, gamedata, allies)
        else:
            target = None
        return {"type": "cast", "spell_id": sid, "target": target}
    if choice in ("aimed", "crippling", "skirmish", "deathmark", "charge", "skirmish_ride", "vampire_charm"):   # 皆先選敵方目標(散兵武技 / 刺客烙印 / 坐騎戰技 / 吸血鬼魅惑)
        return {"type": choice, "target": _choose_enemy_target(state, gamedata, enemies, allies)}
    if choice == "power":
        eff = powers.power_def(powers.power_id(player, gamedata))["effect"]
        needs_target = any(k in eff for k in ("paralyze", "poison", "drain"))
        target = _choose_enemy_target(state, gamedata, enemies, allies) if needs_target else None
        return {"type": "power", "target": target}
    if choice == "racial_power":
        rpid = powers.racial_power_id(player, gamedata)
        if powers.racial_needs_target(rpid):    # 單體控場:限定合類(野獸/人形)存活敵
            valid = powers.racial_combat_targets(rpid, enemies, gamedata)
            return {"type": "racial_power", "target": _choose_enemy_target(state, gamedata, valid, allies)}
        return {"type": "racial_power", "target": None}
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
                ui.message(inventory.use_item(player, gamedata, pid, state) or "你飲下藥水。", style="green")
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


_CAPSTONE_AURA_KIND = {"ally_empower": "empower", "ally_shield": "shield", "ally_regen": "regen"}


def _apply_companion_capstone_auras(char: Character, gamedata: GameData, roster: list, allies: list) -> None:
    """忠誠弧頂點(戰術型):弧完成 + 存活的同伴 → 對盟友側套盟友限定光環(empower/shield/regen)。
    複用戰旗/盾牆同模式(turns:1、source 去重、逐回合刷新),**只作用盟友** ——
    empower 在 combat 端另有 `not _is_player` 守門 → 永不碰玩家偷襲倍率/solo boss 夾限(sim 零位移)。"""
    living = [a for a in allies if combat.is_alive(a)]
    if not living:
        return
    for cid, cre in roster:
        if not combat.is_alive(cre):
            continue                                  # 倒下的頂點持有者不發光環
        cap = party.active_capstone(char, gamedata, cid)
        eff_kind = _CAPSTONE_AURA_KIND.get(cap.get("kind")) if cap else None
        if not eff_kind:
            continue                                  # 無頂點 / 被動型(barter/travel 不在戰鬥套用)
        src = f"capstone:{cid}"
        mag = cap.get("magnitude", 0)
        for a in living:
            a.active_effects[:] = [e for e in a.active_effects if e.get("source") != src]
            a.active_effects.append({"kind": eff_kind, "magnitude": mag, "turns": 1, "source": src})


def run_battle(state: GameState, gamedata: GameData, enemies, companions=None,
               alerted: bool = False, prep_budget: int = 0, casualties: list | None = None,
               carry_allies: list | None = None, preserve_buffs: bool = False,
               mounted: bool = False, flee_after_rounds: int | None = None) -> str:
    """團隊/多敵回合制戰鬥。階段制回合:玩家 → 同伴 → 敵人 → 結算。

    enemies:敵方 Creature 清單(也接受單一 Creature)。companions 未指定時用玩家隊伍。
    casualties:若給定一個 list,戰後把**陣亡盟友的來源 id** 填入(供攻城永久折損用;
    一般戰鬥不傳 → 同伴照常滿血復生)。回傳 'victory' / 'fled' / 'dead'。
    carry_allies:地城戰鬥情境帶入的「預召喚物」(不在 roster → 不回寫持久同伴),併入戰列。
    preserve_buffs:為 True 時不清玩家 active_effects(地城預施增益帶進本場;仍剝 cascade/過期)。
    """
    player = state.player
    if not isinstance(enemies, list):
        enemies = [enemies]
    # 上陣名單:略過已不存在的同伴;排除冊封坐鎮的總管(已離隊治理);**排除倒下/負傷者**(benched 至治療)。
    if companions is None:
        field_ids = party.fieldable(player, gamedata)
    else:                                                       # 顯式名冊(城戰等)→ 同樣排除坐鎮總管與倒下者
        stationed = set(getattr(player, "stewards", {}).values())
        field_ids = [cid for cid in companions if cid in gamedata.companions and cid not in stationed
                     and not party.is_downed(player, gamedata, cid)]
    # roster:本場一開始上陣的盟友(cid → 戰鬥單位);召喚物不在此列。戰後查 is_alive 判陣亡。
    # 持久 HP:以 spawn_hp 帶入(夾上限);羈絆 → 該同伴 max_health 加成。
    roster = [(cid, combat.spawn_companion(gamedata, cid, state.rng,
                                           current_hp=party.spawn_hp(player, gamedata, cid),
                                           max_health_bonus=party.bond_hp_bonus(player, cid)))
              for cid in field_ids]
    battle = {"allies": [cre for _, cre in roster]}
    if carry_allies:   # 地城預召喚物併入戰列(不在 roster → record_after_battle 不回寫持久同伴)
        battle["allies"].extend(carry_allies)

    def tally_casualties():
        # 同伴持久 HP 回寫(0=倒下 benched,須治療);攻城另填 casualties 供 apply_casualties 永久折損。
        downed = party.record_after_battle(player, gamedata, roster)
        if casualties is None:
            for nm in downed:
                ui.message(f"{nm}重傷倒地,暫時退出戰列 —— 休養(旅店過夜 / 原地休息)後方能再上陣。",
                           style="yellow")
        else:
            casualties.extend(cid for cid, cre in roster if not combat.is_alive(cre))
    trapped_kills: set[int] = set()
    opening = not alerted   # 開場偷襲:首個攻擊吃潛行加成;若敵人已警覺(撤退失敗)則無
    vanishes_done = 0  # 本場已成功隱遁次數(成功率遞減,防無限風箏)
    charm_used = False  # 本場是否已用吸血鬼「魅惑凝視」(每場一次;暫態,不入檔)

    # 獸形快取對齊:旅行/休息可能在「同一動作內」推進時間過了獸形時效又觸發戰鬥,
    # 而 combat 讀快取布林、game_loop 的 update 只在每圈頂端刷新 → 進戰前對齊,杜絕以過期獸形作戰。
    if lycanthropy.sync_beast_form(player, state, gamedata):
        ui.message("獸形的狂暴恰在此刻退去 —— 你以人形之軀迎敵。", style="magenta")

    # active_effects 是「戰鬥內」臨時效果 —— 進場先清,杜絕戰鬥外施法(如里程碑「聖光·溢盾」)
    # 殘留的護盾/效果洩漏進本場。必須在 _prep_phase「之前」清(備戰施放的增益在清除後才套用,照常保留)。
    # preserve_buffs(地城預施帶入):不全清,只剝 cascade(戰鬥內累積層)+ 已過期效果。
    if preserve_buffs:
        player.active_effects[:] = [e for e in player.active_effects
                                    if e.get("kind") != "cascade" and e.get("turns", 1) > 0]
    else:
        player.active_effects.clear()

    # 偵查掙得的開戰前備戰空間:在第一個交戰回合「之前」進行(opening 因此保留;
    # buff/召喚的計時從第一回合照 tick,故不延長時效、只省下開場那一動)。
    if prep_budget > 0:
        _prep_phase(state, gamedata, enemies, battle, prep_budget)
        # 奧術連鎖不由「備戰施法」預堆(備戰只省開場一動、不送額外威力)→ 清連鎖層,保留 prep 的增益/召喚
        player.active_effects[:] = [e for e in player.active_effects if e.get("kind") != "cascade"]

    def alive_e():
        return [e for e in enemies if combat.is_alive(e)]

    def note_trap(e):
        if not combat.is_alive(e) and magic.has_soul_trap(e):
            trapped_kills.add(id(e))

    # 忠誠弧頂點(戰術型):開場即套盟友限定光環,使第一回合的同伴也受惠(後續逐回合於回合末刷新)
    _apply_companion_capstone_auras(player, gamedata, roster, battle["allies"])

    round_no = 0
    while combat.is_alive(player) and alive_e():
        round_no += 1
        # R100 限時決鬥(殺知情者):未在 flee_after_rounds 回合內擊殺 → 對方脫逃回報(預設 None 不影響任何既有戰鬥)。
        if flee_after_rounds is not None and round_no > flee_after_rounds:
            player.active_effects.clear()
            state.time.advance(1)
            tally_casualties()
            return "fled_enemy"
        player._evade_counter_used = False        # 每回合重置 on_evade 反制額度(守群戰風險;鏡像 EVASION_BONUS_CAP)
        vanish_success = False        # 本回合是否成功隱遁(R71:成功 → 只重置偷襲;不再跳過敵人階段)
        # 怪物硬控(R43):恐懼/麻痺 → 玩家本回合無法行動 → 跳過選單與玩家階段(同伴/敵人照常,回合末 tick 解除)。
        # 防禦雙軌第二道(命中後)已由 willpower resisted_mind 機率擋下;此處只結算「已成功上身」的硬控。
        if magic.is_incapacitated(player):
            why = "恐懼" if magic.is_feared(player) else "麻痺"
            ui.message(f"你因{why}而無法行動!", style="bold red")
            action = {"type": "incapacitated"}
            blocking = False
        else:
            action = _choose_combat_action(state, gamedata, enemies, battle["allies"], vanishes_done,
                                           mounted=mounted, first_round=(round_no == 1), charm_used=charm_used)
            blocking = action["type"] == "block"

        # ---- 玩家階段 ----
        if action["type"] == "flee":
            foe = max(alive_e(), key=lambda e: e.speed)
            if combat.try_flee(player, foe, state.rng, gamedata):
                ui.message("你成功擺脫了敵人,脫離戰鬥!", style="yellow")
                player.active_effects.clear()
                state.time.advance(1)
                tally_casualties()
                return "fled"
            ui.message("逃跑失敗!", style="red")
        elif action["type"] == "attack":
            tgt = action["target"]
            if combat.is_alive(tgt):
                combat.player_attack_cost(player, gamedata)
                # 🔴 紅線:獸形攻擊永不吃偷襲倍率(變身破壞潛行)→ solo boss 夾限不被觸碰。
                # 即使帶著殘留獸形入場 + 潛近成功(opening=True),此 guard 也使首爪不偷襲。
                sneak = opening and not getattr(player, "beast_form", False)
                ui.combat_event(combat.resolve_attack(player, tgt, gamedata, state.rng,
                                                      sneak_attack=sneak), gamedata)
                # R63 速度第二段:過 100 漸近 30% 機率追擊一記。追擊強制 sneak_attack=False
                # → 普通擊(不碰 SOLO_SNEAK 夾;首擊已耗 opening),耗體力自限,不破 solo 秒殺紅線。
                if combat.is_alive(tgt) and state.rng.chance(
                        formulas.speed_extra_action_chance(player.attr("speed"))):
                    combat.player_attack_cost(player, gamedata)
                    ui.message("你身形如電,順勢追擊!", style="cyan")
                    ui.combat_event(combat.resolve_attack(player, tgt, gamedata, state.rng,
                                                          sneak_attack=False), gamedata)
        elif action["type"] in ("aimed", "crippling", "skirmish"):   # 弓手散兵武技
            tgt = action["target"]
            if combat.is_alive(tgt):
                combat.player_attack_cost(player, gamedata)
                if action["type"] == "aimed":
                    combat.player_attack_cost(player, gamedata)       # 瞄準蓄力:額外耗體
                sneak = opening and not getattr(player, "beast_form", False)
                ui.combat_event(combat.resolve_attack(player, tgt, gamedata, state.rng,
                                                      sneak_attack=sneak,
                                                      aimed=(action["type"] == "aimed")), gamedata)
                if action["type"] == "crippling" and combat.is_alive(tgt):
                    magic.apply_control(tgt, "weaken", gamedata, state.rng,   # R44:集中 helper
                                        magnitude=formulas.CRIPPLING_WEAKEN, turns=formulas.CRIPPLING_TURNS)
                    ui.message(f"{tgt.name}被牽制射壓制,攻勢一時削弱。", style="cyan")
                if action["type"] == "skirmish":   # 射後遁走:複用既有 vanish 三道煞車(防無限風箏)
                    combat.player_vanish_cost(player)
                    attempt = vanishes_done
                    vanishes_done += 1
                    if combat.try_vanish(player, len(alive_e()), attempt, state.rng, gamedata):
                        vanish_success = True
                        ui.message("你射出一箭,旋即翻身遁走 —— 重獲偷襲先機。", style="bold magenta")
                    else:
                        ui.message("你射後欲走,卻被敵人緊咬不放。", style="grey70")
        elif action["type"] == "charge":   # 坐騎「衝鋒」(開場;近戰/長槍;不走偷襲倍率,受 solo 夾限)
            tgt = action["target"]
            if combat.is_alive(tgt):
                combat.player_attack_cost(player, gamedata)
                ui.message("你策馬挺進,藉馬勢猛然衝鋒!", style="bold yellow")
                ui.combat_event(combat.resolve_attack(player, tgt, gamedata, state.rng,
                                                      mounted_charge=True,
                                                      charge_spec=mounts.charge_spec(player, gamedata)), gamedata)
        elif action["type"] == "skirmish_ride":   # 獵馬「騎射」(弓;給閃避增益 + 一記弓擊)
            tgt = action["target"]
            if combat.is_alive(tgt):
                spec = mounts.ride_evasion_spec(player, gamedata) or {}
                player.active_effects.append({"kind": "ride_evasion",
                                              "evasion": spec.get("amount", 0.0),
                                              "turns": spec.get("turns", 1)})
                ui.message("你策馬繞射 —— 馬背的機動讓你大幅更難被擊中。", style="bold cyan")
                combat.player_attack_cost(player, gamedata)
                sneak = opening and not getattr(player, "beast_form", False)
                ui.combat_event(combat.resolve_attack(player, tgt, gamedata, state.rng,
                                                      sneak_attack=sneak), gamedata)
        elif action["type"] == "cast":
            res = magic.cast(player, gamedata, action["spell_id"], state.rng,
                             target=action.get("target"), battle=battle, enemies=alive_e(),
                             corpses=enemies, mounted=mounted)   # 亡者復生需見「完整」敵群(含已死屍體);存活清單仍走 enemies=alive_e()
            ui.message(res["message"], style="cyan")
            ui.show_events(res["skill_events"], gamedata)
        elif action["type"] == "power":
            pres = powers.use(player, state, gamedata, target=action.get("target"))
            for m in pres["messages"]:
                ui.message(m, style="bold magenta")
            if pres["escape"]:
                player.active_effects.clear()
                state.time.advance(1)
                tally_casualties()
                return "fled"
        elif action["type"] == "racial_power":   # 種族之力(R61):自身增傷 / 控場(走 apply_control)/ 召喚靈體
            rres = powers.racial_use(player, state, gamedata, target=action.get("target"),
                                     battle=battle, enemies=alive_e())
            for m in rres["messages"]:
                ui.message(m, style="bold magenta")
        elif action["type"] == "revert":          # 狼人:主動變回人形(力竭代價)
            lycanthropy.revert(player, state, gamedata)
            ui.message("你壓下狂暴,重歸人形 —— 筋疲力盡。", style="magenta")
        elif action["type"] == "howl":            # 狼人(達階):恫嚇之嚎 → 使敵恐懼
            res = lycanthropy.howl(player, state, gamedata, alive_e())
            if res["affected"]:
                ui.message(f"你仰天發出撕裂夜空的狼嚎 —— {res['affected']} 名敵人膽寒退縮!",
                           style="bold magenta")
            else:
                ui.message("你發出震懾的狼嚎,但眼前的強敵毫不退縮。", style="grey70")
        elif action["type"] == "vampire_charm":   # 吸血鬼:魅惑凝視 → 迷惑一敵使其恐懼不進攻(每場一次;R56)
            tgt = action["target"]
            if combat.is_alive(tgt):
                player.fatigue = max(0, player.fatigue - VAMPIRE_CHARM_FATIGUE)
                charm_used = True
                res = magic.apply_control(tgt, "fear", gamedata, state.rng,   # R44:走集中 helper(solo BOSS 機率抵抗 + 去重)
                                          turns=VAMPIRE_CHARM_TURNS, source="vampire_charm")
                if res == "applied":
                    ui.message(f"你以血族魅力凝視{tgt.name} —— 牠目光渙散、心神被攝,不敢進攻。", style="bold magenta")
                else:
                    ui.message(f"你施展魅惑凝視,但{tgt.name}意志如鐵,掙脫了你的蠱惑。", style="grey70")
        elif action["type"] == "block":
            combat.player_block_cost(player)
            ui.message("你舉盾戒備,準備擋下來襲。", style="grey70")
        elif action["type"] == "wall":            # 戰士:立/撤盾牆架勢(常駐 stance)
            if combat.has_shield_wall(player):
                player.active_effects[:] = [e for e in player.active_effects if e.get("kind") != "shield_wall"]
                ui.message("你卸下盾牆,恢復機動。", style="grey70")
            else:
                player.active_effects.append({"kind": "shield_wall",
                                              "mitigation": SHIELD_WALL_MITIGATION, "turns": 99})
                ui.message("你舉盾結陣 —— 化身移動堡壘,敵火力盡向你而來。", style="bold cyan")
        elif action["type"] == "standard":        # 騎士:立戰旗(增傷光環 + 自身護甲,常駐)
            player.magicka = max(0, player.magicka - STANDARD_COST_MAGICKA)
            player.fatigue = max(0, player.fatigue - STANDARD_COST_FATIGUE)
            player.active_effects.append({"kind": "battle_standard", "turns": 99})
            ui.message("你將戰旗插上戰場 —— 旗影所及,同袍士氣大振、敵膽皆寒。", style="bold cyan")
        elif action["type"] == "rally":           # 口才:立戰陣號令(增傷光環,常駐;純耗體,鼓舞他人)
            player.fatigue = max(0, player.fatigue - RALLY_FATIGUE)
            player.active_effects.append({"kind": "rally_banner", "turns": 99})
            ui.message("你振臂高呼、鼓舞士氣 —— 號令所及,同袍鬥志昂揚、攻勢如潮。", style="bold cyan")
        elif action["type"] == "deathmark":       # 刺客:標記一敵(後續近戰破甲;開場偷襲不受惠)
            tgt = action["target"]
            dm = mastery.deathmark(player, gamedata)
            if dm and combat.is_alive(tgt) and not combat._has_deathmark(tgt) and not _on_deathmark_cd(tgt):
                player.fatigue = max(0, player.fatigue - dm.get("fatigue_cost", 15))
                tgt.active_effects.append({"kind": "deathmark", "turns": dm.get("turns", 4)})
                tgt.active_effects.append({"kind": "deathmark_cd", "turns": dm.get("cooldown", 3)})
                ui.message(f"你以殺意鎖定{tgt.name},烙下無形的致命標記 —— 後續每擊直取要害。",
                           style="bold magenta")
            else:
                ui.message("此刻無法標記該目標。", style="grey70")
        elif action["type"] == "vanish":
            combat.player_vanish_cost(player)        # 隱遁耗大量體力(連續隱遁會耗竭)
            attempt_used = vanishes_done
            vanishes_done += 1                       # 每次「嘗試」即遞增 → 成功率遞減真正生效
            if combat.try_vanish(player, len(alive_e()), attempt_used, state.rng, gamedata):
                vanish_success = True
                ui.show_events(progression.use_skill(player, gamedata, "sneak",
                                                     formulas.COMBAT_SNEAK_XP), gamedata)
                ui.show_events(progression.use_skill(player, gamedata, "acrobatics",
                                                     formulas.COMBAT_DODGE_XP), gamedata)
                ui.message("你遁回陰影,重獲偷襲先機 —— 但敵人並未被甩脫,下一擊將再度致命。",
                           style="bold magenta")
            else:
                ui.message("隱遁失敗!你的身形仍暴露在敵人眼前。", style="red")

        # 隱遁成功 → 重新點亮偷襲(下一次攻擊再吃 sneak 倍率);其餘行動後敵人已警覺
        opening = vanish_success

        # 玩家階段可能殺死(被擒魂的)敵人 → 統一記錄(涵蓋單體/AoE/星座之力)
        for e in enemies:
            note_trap(e)

        # ---- 同伴階段(輔助型先試支援施法,否則攻擊一個隨機存活敵人)----
        for a in battle["allies"]:
            if not alive_e():
                break
            if not combat.is_alive(a) or magic.is_incapacitated(a):
                continue
            # R86 角色感知支援:輔助型同伴在受傷/缺 buff 時施治療/護盾/激勵(含照顧玩家),否則攻擊。
            support = magic.companion_support_act(a, player, battle["allies"], gamedata)
            if support is not None:
                ui.message(support["message"], style="green")
                continue
            tgt = state.rng.choice(alive_e())
            a_atk = combat.choose_attack(a, state.rng, tgt)   # 同伴多攻擊模式(無曲目 → 後備單招,行為不變)
            ui.combat_event(combat.resolve_attack(a, tgt, gamedata, state.rng, attack=a_atk), gamedata)
            note_trap(tgt)

        # ---- 敵人階段(各自挑我方一個目標)----R71:隱遁不再無敵 → 敵人照常攻擊(隱遁只重置偷襲,防禦純靠 evasion)----
        for e in enemies:
            if not combat.is_alive(player):
                break
            if not combat.is_alive(e):
                continue
            if magic.is_incapacitated(e):
                why = "恐懼" if magic.is_feared(e) else "麻痺"
                ui.message(f"{e.name}因{why}而無法行動。", style="blue")
                continue
            # R87 敵方支援施法者:法系/祭司怪在隊友血低/缺 buff 時治療/護盾/號令其他敵人(換損該回合攻擊)。
            support = magic.enemy_support_act(e, enemies, gamedata)
            if support is not None:
                ui.message(support["message"], style="cyan")
                continue
            tgt = combat.pick_player_side_target(player, battle["allies"], state.rng)
            blk = blocking if tgt is player else False
            e_atk = combat.choose_attack(e, state.rng, tgt)   # 怪物多攻擊模式:選招(加權/血量階段/蓄力冷卻)
            ev = combat.resolve_attack(e, tgt, gamedata, state.rng, defender_blocking=blk, attack=e_atk)
            ui.combat_event(ev, gamedata)
            if ev.get("infected"):    # 疾病傳染:依種類分派到吸血鬼 / 狼人狀態機
                kind = ev.get("infect_kind", "vampire")
                if kind == "lycanthropy" and lycanthropy.infect(player, state):
                    ui.message("利爪撕開你的皮肉 —— 傷口深處傳來灼燒的悸動。你染上了某種野性的熱症……",
                               style="bold red")
                elif kind == "vampire" and vampirism.infect(player, state):
                    ui.message("獠牙刺入你的頸側 —— 傷口隱隱發燙。你染上了某種不祥的熱症……",
                               style="bold red")
                elif kind == "disease" and diseases.contract(player, state, gamedata, ev.get("disease_id")):
                    _spec = gamedata.diseases.get(ev.get("disease_id"), {})
                    ui.message(f"傷口紅腫發熱、隱隱作痛 —— 你染上了「{_spec.get('name', '某種疾病')}」。"
                               f"{_spec.get('symptom', '')}", style="bold red")
        for e in enemies:          # 敵人階段可能因「重甲反震」反殺被擒魂的敵 → 補記擒魂(免漏靈魂石)
            note_trap(e)

        # ---- 回合結束:持續傷害/狀態計時 ----
        # 意志「施法續航」:戰鬥每回合被動回魔(base-40 中性;巨魔像座不自然回魔,沿用既有設定)
        mregen = formulas.magicka_regen_combat(player.attr("willpower"))
        _rf = race_ability.magicka_regen_factor(player, gamedata)   # 高精靈高貴血脈:戰鬥回魔加成(非高精靈 ×1 不變)
        if _rf != 1.0:
            mregen *= _rf
        if mregen and player.birthsign != "atronach" and player.magicka < player.max_magicka:
            player.magicka = min(player.max_magicka, player.magicka + mregen)
        hregen = mastery.combat_regen(player, gamedata)   # 里程碑「生生不息」:戰鬥中每回合自癒
        if hregen and combat.is_alive(player) and player.health < player.max_health:   # is_alive:不得回血復活本回合被擊殺的玩家(對齊 auto_resolve)
            player.health = min(player.max_health, player.health + hregen)
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
        # ---- 八職常駐 stance 的回合末維護(盾牆/戰旗/戰地搶救;暫態存 active_effects,戰鬥邊界清)----
        living_allies = [a for a in battle["allies"] if combat.is_alive(a)]
        if combat.has_shield_wall(player):       # 戰士「盾牆」:上繳體力(歸 0 落陣)+ 護同袍護甲光環
            player.fatigue = max(0, player.fatigue - SHIELD_WALL_UPKEEP)
            if player.fatigue <= 0:
                player.active_effects[:] = [e for e in player.active_effects if e.get("kind") != "shield_wall"]
                ui.message("你力竭難支,盾牆隨之鬆動落下。", style="yellow")
            else:
                for a in living_allies:
                    a.active_effects[:] = [e for e in a.active_effects if e.get("source") != "shield_wall_aura"]
                    a.active_effects.append({"kind": "shield", "magnitude": SHIELD_WALL_ALLY_ARMOR,
                                             "turns": 1, "source": "shield_wall_aura"})
        if _has_standard(player):                # 騎士「戰旗」:全隊增傷光環(不需重施)+ 自身護甲
            emp = round(STANDARD_EMPOWER_BASE * magic._power(player, gamedata, "illusion"), 3)
            for a in living_allies:
                a.active_effects[:] = [e for e in a.active_effects if e.get("source") != "standard"]
                a.active_effects.append({"kind": "empower", "magnitude": emp, "turns": 1, "source": "standard"})
            player.active_effects[:] = [e for e in player.active_effects if e.get("source") != "standard_self"]
            player.active_effects.append({"kind": "shield", "magnitude": STANDARD_SELF_ARMOR,
                                          "turns": 1, "source": "standard_self"})
        if _has_rally(player):                    # 口才「戰陣號令」:全隊增傷光環(固定 0.15,不吃 power;自身無益)
            for a in living_allies:               # empower MAX 聚合(combat) → 與戰旗同開不疊加,取較強者
                a.active_effects[:] = [e for e in a.active_effects if e.get("source") != "rally"]
                a.active_effects.append({"kind": "empower", "magnitude": RALLY_EMPOWER, "turns": 1, "source": "rally"})
        if mastery.triage(player, gamedata) and not _triage_armed(player):   # 治療師「戰地搶救」:同伴瀕死 → 武裝折扣急救
            if any(a.health < a.max_health * TRIAGE_ALLY_HP_RATIO for a in living_allies):
                player.active_effects.append({"kind": "triage_ready", "turns": 2})
                ui.message("同袍命懸一線 —— 你的戰地醫者本能瞬間繃緊,下一道治療近乎免費。", style="bold green")
        _apply_companion_capstone_auras(player, gamedata, roster, battle["allies"])   # 忠誠弧頂點:逐回合刷新盟友光環
        # 召喚物計時、移除陣亡/到期的同伴
        for a in battle["allies"]:
            if a.summon_turns is not None:
                a.summon_turns -= 1
        battle["allies"] = [a for a in battle["allies"]
                            if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)]

    player.active_effects.clear()
    state.time.advance(1)
    if not combat.is_alive(player):
        tally_casualties()
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
        if id(e) in trapped_kills:                     # 擒魂結算:填手上空魂石(人形→空黑魂石+法術)
            msg = magic.resolve_soul_capture(player, e, gamedata)
            if msg:
                ui.message(msg, style="magenta")
        quests.record_kill(player, e.template_id)
    ui.loot_report(total, gamedata)
    _report_quests(state, gamedata)
    if getattr(player, "beast_form", False):    # 獸形勝利:吞噬獵物續時 + 回血(每場有上限,封無限獸形)
        dv = lycanthropy.devour(player, state, gamedata)
        if dv["extended"]:
            ui.message(f"你俯身吞噬倒下的獵物 —— 狂暴得以延續(回復 {dv['healed']} 點生命)。",
                       style="bold red")
    for nm, tier_name in party.award_victory(player, gamedata, roster):   # 並肩獲勝 → 羈絆累積
        ui.message(f"並肩奮戰,你與{nm}的情誼更深了 —— 羈絆提升至「{tier_name}」。", style="bold cyan")
    tally_casualties()
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
        for sid in r.get("spells", []):                # R-arcane:奧術試煉授終極法術(實際發放在 quests._complete)
            ui.message(f"  ✦ 習得終極奧義:{gamedata.spells[sid]['name']}", style="bold magenta")
        if r.get("fame"):
            ui.message(f"  聲望 +{r['fame']}", style="cyan")
        if r.get("companion"):                         # 同伴角色化:招募任務授予具名同伴(入夥 / 滿員待召集)
            cid = r["companion"]; cnm = gamedata.companions.get(cid, {}).get("name", cid)
            if cid in state.player.companions:
                ui.message(f"  ◈ {cnm}加入了你的隊伍!", style="bold green")
            else:
                ui.message(f"  ◈ {cnm}願追隨你 —— 隊伍已滿,可在「隊伍」選單召集歸隊。", style="green")
        for bcid, n in (r.get("bond") or {}).items():  # 專屬支線完成 → 羈絆躍升(與 _complete 的套用條件一致)
            if bcid in gamedata.companions and (bcid in state.player.companions
                                                or party.keeps_state_on_dismiss(gamedata, bcid)):
                bnm = gamedata.companions[bcid].get("name", bcid)
                ui.message(f"  ◈ 你與{bnm}並肩交心,羈絆躍升至「{party.bond_name(state.player, bcid)}」",
                           style="bold cyan")
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
    # 弓手「獵手偵察」里程碑:無 scout 技能也視同偵查 50(獵人之眼);取兩者高者
    sk = max(char.skill("scout"), mastery.recon_scout_floor(char, gamedata))
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
            if sk >= mastery.recon_reveal_threshold(char, gamedata) and e.resist:   # 「洞察弱點」降門檻 75→50
                weak = [magic._ELEMENT_CN.get(k, k) for k, v in e.resist.items() if v < 0]
                tough = [magic._ELEMENT_CN.get(k, k) for k, v in e.resist.items() if v >= 50]
                if weak:
                    parts.append("弱點:" + "/".join(weak))
                if tough:
                    parts.append("抗:" + "/".join(tough))
            ui.message("· " + "  |  ".join(parts), style="white")
    ui.show_events(progression.use_skill(char, gamedata, "scout", formulas.COMBAT_SNEAK_XP), gamedata)


def offer_battle(state: GameState, gamedata: GameData, enemies, ambush_chance: float = 0.25,
                 surprise: bool = False, mounted: bool = False, recruit: str | None = None) -> str | None:
    """呈現遭遇 → 接戰 / 偵查 / 潛行撤退。回傳結果或 None(撤退成功,未交戰)。

    接戰時擲「入場潛行檢定」決定有無開場偷襲(吃潛行/敵警覺/敵數/護甲/夜間/偵查)。
    surprise=True(被伏擊)大幅扣減先機 → 受害者難以反偷襲加害者。
    ambush_chance 保留作簽名相容(舊呼叫端傳入);避戰已改為吃潛行/速度的潛行撤退。
    """
    if not isinstance(enemies, list):
        enemies = [enemies]
    char = state.player
    lycanthropy.sync_beast_form(char, state, gamedata)   # 偵查估傷前對齊獸形快取(時間可能已推進過時效)
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
        if dialogue.can_intimidate(gamedata, enemies):       # 全為弱人形敵(盜匪)→ 可口才喝退
            ipct = int(dialogue.intimidate_chance(char, enemies, night, gamedata) * 100)
            opts.append(("intimidate", f"威嚇喝退(口才,成功率 {ipct}%)"))
        if recruit and not factions.is_member(char, recruit):   # 教徒招募:口才說服可入會(否則開打)
            opts.append(("recruit", f"說服加入(口才,成功率 {int(dialogue.recruit_chance(char) * 100)}%)"))
        rpct = int(combat.stealth_retreat_chance(char, enemies) * 100)
        opts.append(("retreat", f"潛行撤退（成功率 {rpct}%)"))
        choice = ui.menu(f"要與{name}交戰嗎?", opts)
        if choice == "scout":
            _scout_report(state, gamedata, enemies)
            scouted = True
            continue
        if choice == "intimidate":
            r = dialogue.intimidate(char, gamedata, enemies, night, state.rng)
            state.time.advance(r["hours"])
            ui.show_events(r["skill_events"], gamedata)
            if r["ok"]:                                       # 喝退成功 → 避戰(無戰利/擊殺/xp 來自敵)
                ui.message("你冷然報出幾個名號、目光如刀 —— 對方面面相覷,終於悻悻退去。", style="green")
                return None
            ui.message("對方非但不退,反被你激怒,拔刀撲上!", style="red")
            return run_battle(state, gamedata, enemies, alerted=True, mounted=mounted)
        if choice == "recruit":
            r = dialogue.recruit_persuade(char, gamedata, state.rng)
            state.time.advance(r["hours"])
            ui.show_events(r["skill_events"], gamedata)
            if r["ok"]:
                if ui.confirm("赤袍信徒低語:「達貢在等你。」 —— 加入神話黎明?"):
                    factions.join(char, recruit)
                    ui.message(f"你誦下達貢的誓言,成為神話黎明的「{factions.rank_name(char, gamedata, recruit)}」"
                               " —— 信徒引你望向湖深處,神話黎明聖殿就此向你顯現。", style="bold green")
                    return None
                ui.message("你婉拒了皈依 —— 信徒臉色一沉,赤刃出鞘!", style="red")
                return run_battle(state, gamedata, enemies, alerted=True, mounted=mounted)
            ui.message("你的言辭未能取信 —— 信徒拔刀撲上!", style="red")
            return run_battle(state, gamedata, enemies, alerted=True, mounted=mounted)
        if choice == "retreat":
            if combat.try_stealth_retreat(char, enemies, state.rng):
                ui.message("你悄無聲息地退入暗處,沒有驚動任何人。", style="grey70")
                return None
            ui.message("撤退失敗 —— 敵人發現了你,且已有戒備!", style="red")
            return run_battle(state, gamedata, enemies, alerted=True, mounted=mounted)
        # 接戰 → 入場潛行檢定:成功取得開場偷襲先機,失敗則敵人警覺(無偷襲)
        got_drop = combat.try_stealth_approach(char, enemies, state.rng, gamedata, night, scouted, surprise)
        if got_drop:
            ui.message("你屏息潛近,敵人渾然未覺 —— 搶得致命先機!", style="bold green")
        else:
            ui.message("你的接近被察覺了,沒能搶到偷襲的先機。", style="yellow")
        # 偵查掙得的備戰空間:潛近成功且未被伏擊時,依偵查技能換得開戰前準備
        pb = (formulas.prep_budget(char.skill("scout")) + mastery.prep_bonus(char, gamedata)) if (got_drop and not surprise) else 0
        return run_battle(state, gamedata, enemies, alerted=not got_drop, prep_budget=pb, mounted=mounted)


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
    # 神話黎明招募:阿留斯湖洞窟(凱瓦奇陷落後信徒現身),非會員且可入會 → 有機率遇上教徒,口才可入會
    if (player.location_id == "lake_arrius_caverns"
            and politics.DAEDRIC_UNLOCK_EVENT in getattr(player, "world_events_fired", [])
            and not factions.is_member(player, "mythic_dawn")
            and factions.join_block_reason(player, gamedata, "mythic_dawn") is None
            and state.rng.chance(0.5)):
        cultists = [combat.spawn_creature(gamedata, "mythic_dawn_acolyte", state.rng) for _ in range(2)]
        ui.message("湖畔陰影裡走出幾名赤袍人 —— 神話黎明的信徒,正不動聲色地打量著你。", style="red")
        return offer_battle(state, gamedata, cultists, recruit="mythic_dawn", mounted=True)
    danger = world.current_location(player, gamedata).get("danger", 1)
    enemies = combat.random_encounter_group(gamedata, player.level, state.rng, max_danger=danger + 1,
                                            biome=world.current_location(player, gamedata).get("biome"))
    return offer_battle(state, gamedata, enemies, mounted=True)   # 野外探索=騎乘語境(坐騎戰技生效)


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
    return _travel_to(state, gamedata, dest)


def _travel_to(state: GameState, gamedata: GameData, dest: str) -> str | None:
    """前往指定地點(供旅行選單與 hub/地點卡的可點出口共用)。回傳 'dead' 或 None。"""
    res = world.travel(state.player, gamedata, dest, state.time, state.rng)
    foe = res["foe"]
    # 路途伏擊:R84 賞金獵人(通緝)優先,否則 R96 宿敵公會打手;觸發則「取代」本趟一般遭遇
    # (一趟最多一場戰);騎馬降低被攔機率。優先序 bounty > guild → 絕不雙觸。
    evade = mounts.encounter_evade(state.player, gamedata)
    heat = crime.active_heat(state.player)
    bounty_ambush = heat >= 1 and state.rng.chance(
        min(0.75, _BOUNTY_HUNT_BASE_CHANCE + 0.12 * (heat - 1)) * (1 - evade))
    g_fid, g_tier, guild_ambush = None, 0, False
    if not bounty_ambush:
        g_fid, g_tier = factions.most_hostile_guild(state.player, gamedata)
        guild_ambush = g_tier >= _GUILD_HOSTILITY_AMBUSH_MIN and state.rng.chance(
            min(0.35, _GUILD_AMBUSH_BASE * g_tier) * (1 - evade))
    if bounty_ambush or guild_ambush:
        foe = None
    if dest not in state.player.visited_locations:   # 已抵達(location_id 已更新)→ 先記足跡,
        state.player.visited_locations.append(dest)  # 即使途中埋伏致死也算到過此地
    ui.message(f"你啟程前往{gamedata.location(dest)['name']}……", style="grey70")
    _maybe_sunburn(state, gamedata, res["hours"])    # 吸血鬼:白天趕路會被日光灼傷
    if res["hours"] < res["base_hours"]:
        ui.message(f"矯健的身手讓旅程縮短到 {res['hours']} 時(原需 {res['base_hours']} 時)。",
                   style="grey70")
    ui.show_events(res["skill_events"], gamedata)
    if bounty_ambush:
        if _bounty_hunter_ambush(state, gamedata) == "dead":
            return "dead"
    elif guild_ambush:
        if _guild_enforcer_ambush(state, gamedata, g_fid, g_tier) == "dead":
            return "dead"
    elif foe is not None:
        ui.message("途中遭遇了埋伏!", style="yellow")
        result = offer_battle(state, gamedata, foe, ambush_chance=0.4, surprise=True, mounted=True)   # 旅途=騎乘語境
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
    # R50:詛咒被識破 → 衛兵圍捕(高階吸血鬼被看破 / 獸形現於城中)
    if loc["type"] in ("city", "town"):
        if _curse_manhunt(state, gamedata) == "dead":
            return "dead"
    # R100:臥底在城鎮被某 B NPC 起疑(低 secrecy → 機率識破 → 指派知情者 + 限時追殺)
    if loc["type"] in ("city", "town"):
        _undercover_detection(state, gamedata)
    return None


# ======================================================================
# 地城探索
# ======================================================================
def _resolve_container(state: GameState, gamedata: GameData, container: dict, label: str) -> None:
    if container is None:
        return
    lock = container.get("locked", 0)
    if lock > 0:
        picks = inventory.count_item(state.player, "lockpick")
        if picks <= 0 and not state.player.tower_key_charge and not dungeon.has_skeleton_key(state.player, gamedata):
            ui.message(f"這個{label}上了鎖,而你沒有開鎖器 —— 撬不開(城鎮可買開鎖器)。", style="grey70")
            return
        ch = dungeon.effective_pick_lock_chance(state.player, gamedata, lock)
        if not ui.confirm(f"發現一個上鎖的{label}(鎖難度 {lock},成功率約 {int(ch*100)}%,開鎖器 ×{picks}),嘗試撬鎖?"):
            return
        while True:
            r = dungeon.pick_lock(state.player, gamedata, lock, state.rng)
            state.time.advance(r["hours"])               # 不耗時(hours 恆 0)
            ui.show_events(r["skill_events"], gamedata)
            if r.get("no_pick"):                         # 開鎖器用盡 → 收手(主成本閘)
                ui.message("你的開鎖器用盡了,只得作罷(城鎮可補開鎖器)。", style="yellow")
                return
            if r["success"]:
                ui.message("骷髏鑰匙輕輕一轉,任何鎖都形同虛設。" if r.get("skeleton_key")
                           else "塔之鑰應驗,鎖無聲而開。" if r.get("tower_key")
                           else "喀噠 —— 鎖開了!(用掉一根開鎖器)", style="green")
                break
            broke = "(折斷了一根開鎖器)" if r.get("broke_pick") else ""
            if r["tired"]:
                ui.message(f"撬鎖失敗{broke},你已精疲力竭 —— 得先歇口氣。", style="yellow")
                return
            if not ui.confirm(f"撬鎖失敗{broke}。再試一次?"):
                return
    spoils = dungeon.open_container(state.player, gamedata, container, state.rng)
    ui.message(f"你打開了{label}:", style="green")
    ui.loot_report(spoils, gamedata)


def _resolve_trap(state: GameState, gamedata: GameData, trap: dict) -> None:
    """陷阱格:擲 敏捷/安全/幸運 規避;失敗受少量傷(可被治療,刻意非高致命;極低血才可能致死)。
    避陷/觸發皆鍛鍊 security(learn-by-doing:避陷=用技能 full xp,觸發=從失誤學 少量 xp)。"""
    char = state.player
    base_xp = gamedata.skills["security"]["practice"]["xp"]
    dodge = min(0.9, 0.30 + (char.attr("agility") - 40) * 0.01 + char.skill("security") * 0.003
                + formulas.luck_fortune(char.attr("luck")))
    dodge = max(dodge, mastery.trap_floor(char, gamedata))   # 里程碑「機關通曉」:避陷保底
    if state.rng.chance(dodge):
        ui.message("你察覺地面的機關,及時閃避。", style="green")
        ui.show_events(progression.use_skill(char, gamedata, "security", base_xp), gamedata)
        return
    lo, hi = trap.get("damage", [4, 8])
    dmg = state.rng.randint(lo, hi)
    char.health = max(0, char.health - dmg)
    ui.message(f"機關觸發 —— 你閃避不及,受了 {dmg} 點傷害!", style="red")
    if combat.is_alive(char):   # 對抗審查:陷阱致死則不給 xp(鏡像 R34 combat_regen「復活死人」守:死人不成長)
        ui.show_events(progression.use_skill(char, gamedata, "security", base_xp * formulas.SECURITY_FAIL_XP_FRAC), gamedata)


def action_dungeon(state: GameState, gamedata: GameData) -> str | None:
    """格子探索地城 —— **視為戰鬥情境**的自足子迴圈(維持盟友清單 + 回合制效果計時)。

    清空末層 boss = 肅清(record_dungeon_clear);離開/逃跑/死亡皆不計。
    原子探索:格子進場現生、離場即棄(零新存檔欄)。boss 死亡 → 寶藏自動解鎖。
    可預施增益 / 預召喚召喚物(隨移動逐回合衰減,經 carry_allies/preserve_buffs 帶進觸發戰鬥);
    偵查 perk → 探明四鄰;每探明一新格 → 少量偵查 xp。
    """
    player = state.player
    loc = world.current_location(player, gamedata)
    spec = gamedata.dungeons[loc["dungeon"]]
    # 首次肅清才給保證戰利品(boss 寶藏 + 一般格寶箱)→ 反「重訪刷寶」:已清地城再衝,
    # 怪物/陷阱照常(戰鬥 XP/掉落是有風險的正常 grind),但寶箱與寶藏皆已被你搬空。
    first_clear = loc["dungeon"] not in player.cleared_dungeons
    grid = dungeoncrawl.generate(spec, gamedata, state.rng)
    n, m = grid["n"], grid["m"]
    explored = [[[False] * n for _ in range(n)] for _ in range(m)]
    resolved = [[[False] * n for _ in range(n)] for _ in range(m)]
    z = x = y = 0
    battle = {"allies": []}   # 戰鬥情境:預召喚物(transient,不入持久同伴;隨移動衰減)
    ui.message(f"你踏入了{spec['name']}的幽暗深處……（{n}×{n} 格 · 共 {m} 層）", style="magenta")
    if not first_clear:
        ui.message("（你早已肅清此地 —— 首領寶藏已被你取走;一般寶箱與機關則隨歲月重新佈設,游蕩的新怪亦不少。）", style="grey70")

    def reveal_and_train(zz, xx, yy):
        """標記 (xx,yy) 及(有偵查 perk 時)四鄰為已探;每「新探明」格授少量偵查 xp(已探不重複給)。"""
        cells = [(xx, yy)]
        if mastery.has_recon_perk(player, gamedata):
            cells += [(nx, ny) for _k, _l, nx, ny in dungeoncrawl.neighbors(grid, xx, yy)]
        newly = 0
        for cx, cy in cells:
            if not explored[zz][cy][cx]:
                explored[zz][cy][cx] = True
                newly += 1
        if newly:
            ui.show_events(progression.use_skill(player, gamedata, "scout",
                                                 newly * formulas.DUNGEON_REVEAL_SCOUT_XP), gamedata)

    def case_layer(zz):
        """賊眼·窺探(security_100):進該層即揭所有陷阱/上鎖寶箱格(不含怪/樓梯/首領);
        零回合、不結算、不發 scout xp(守 security≠scout 界線)。UI 自動顯 ^/$(已探未結算)。"""
        if not mastery.has_dungeon_casing(player, gamedata):
            return
        for cy in range(n):
            for cx in range(n):
                if grid["layers"][zz][cy][cx]["type"] in (dungeoncrawl.TRAP, dungeoncrawl.CONTAINER):
                    explored[zz][cy][cx] = True

    def tick_turn() -> bool:
        """行動 1 格 = 1 回合:玩家增益 + 召喚物 summon_turns/效果衰減。回 True = 玩家陣亡(DoT)。"""
        for msg in magic.tick_effects(player, gamedata):
            ui.message(msg, style="grey70")
        for a in battle["allies"]:
            for msg in magic.tick_effects(a, gamedata):   # 召喚物的 DoT/再生也報(與玩家 tick 對稱)
                ui.message(msg, style="grey70")
            if a.summon_turns is not None:
                a.summon_turns -= 1
        for a in [a for a in battle["allies"]
                  if not combat.is_alive(a) or (a.summon_turns is not None and a.summon_turns <= 0)]:
            ui.message(f"{a.name}的身影消散了。", style="grey70")
        battle["allies"][:] = [a for a in battle["allies"]
                               if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)]
        return not combat.is_alive(player)

    def sync_allies():
        """戰後重濾預召喚物為存活且未逾時者(run_battle 已就地更新其 HP/summon_turns)。"""
        battle["allies"][:] = [a for a in battle["allies"]
                               if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)]

    reveal_and_train(z, x, y)   # 進場格(不耗回合)
    case_layer(z)               # 賊眼·窺探:進場層即揭該層陷阱/寶箱

    while True:
        cell = dungeoncrawl.cell_at(grid, z, x, y)
        if not resolved[z][y][x]:                          # 首次進入該格 → 結算內容
            resolved[z][y][x] = True
            t = cell["type"]
            if t == dungeoncrawl.MONSTER:
                foes = [combat.spawn_creature(gamedata, tid, state.rng) for tid in cell["enemies"]]
                res = run_battle(state, gamedata, foes,
                                 carry_allies=battle["allies"], preserve_buffs=True)
                sync_allies()
                if res == "dead":
                    return "dead"
                if res == "fled":
                    ui.message("你逃離了戰鬥,倉皇退出了地城。", style="yellow")
                    state.time.advance(1)
                    return None
            elif t == dungeoncrawl.CONTAINER:
                # 一般寶箱隨機刷新:generate() 每次重入生新寶箱/鎖 → 可重撬(可再生 security 練功 + 戰利品;
                # 首領寶藏仍 first_clear 限定,見下)。自然閘:每撬耗開鎖器(金幣)+ 推進時間 + 游蕩怪風險。
                _resolve_container(state, gamedata, cell["container"], "箱子")
            elif t == dungeoncrawl.TRAP:
                _resolve_trap(state, gamedata, cell["trap"])
                if not combat.is_alive(player):
                    return "dead"
            elif t == dungeoncrawl.BOSS:
                boss = grid["boss"]
                if boss.get("desc"):
                    ui.message(boss["desc"], style="magenta")
                # 教徒終局「逆轉法陣的反噬」:玩家入場即被抽乾(雙方削弱 —— 削弱版達貢由 bestiary 變體承載)。
                # 血量夾 ≥1(不致死);魔力/體力砍至三分。重訪照樣反噬(死亡之地位面本就不穩)。
                if loc.get("dungeon") == "dawn_sanctum":
                    player.health = max(1, player.health // 3)
                    player.magicka //= 3
                    player.fatigue //= 3
                    ui.message("逆轉召喚法陣的反噬撕裂你的血肉與心神 —— 你氣力僅存三分,但半成的達貢化身同樣虛弱。", style="yellow")
                if boss.get("raw"):   # 已是 elite 的首領以原始強度登場(避免 spawn_boss 再 ×1.6 疊加)
                    foe = combat.spawn_creature(gamedata, boss["enemy"], state.rng)
                    foe.name = f"{spec['name']}首領"
                else:
                    foe = combat.spawn_boss(gamedata, boss["enemy"], state.rng, name=f"{spec['name']}首領")
                res = run_battle(state, gamedata, foe,
                                 carry_allies=battle["allies"], preserve_buffs=True)
                sync_allies()
                if res == "dead":
                    return "dead"
                if res == "fled":                          # 從首領逃離 → 未肅清:不開寶藏、不計清剿、不結算
                    ui.message("你從首領面前倉皇逃離,未能肅清地城。", style="yellow")
                    state.time.advance(1)
                    return None
                if first_clear:
                    # 🔴 首次肅清 → 寶藏「自動解鎖」直接開啟(免開鎖器/免技能,一般格寶箱才走 pick_lock)
                    spoils = dungeon.open_container(player, gamedata, boss.get("treasure") or {}, state.rng)
                    ui.message("首領倒下,守護的寶藏應聲而開 ——", style="bold green")
                    ui.loot_report(spoils, gamedata)
                else:                                      # 重訪:首領照常重生再戰,但寶藏早已被你取走
                    ui.message("首領再度倒下,但守護的寶藏早已被你取走 —— 空空如也。", style="grey70")
                ui.message(f"你肅清了{spec['name']}!", style="bold green")
                quests.record_dungeon_clear(player, loc["dungeon"])
                _report_quests(state, gamedata)
                state.time.advance(1)
                return None

        ui.status_line(state, gamedata, allies=battle["allies"])   # 持久狀態條:英雄 + 夥伴 + 召喚物
        ui.dungeon_grid(grid, z, x, y, explored, resolved)  # 小地圖 + 當前格(偵查揭示鄰格內容)
        opts = [("go:" + key, f"往{label}") for key, label, _nx, _ny in dungeoncrawl.neighbors(grid, x, y)]
        if any(gamedata.spells[s]["target"] == "self" and gamedata.spells[s]["effect"]["kind"] != "reanimate"
               for s in player.spells):    # 僅當有可在地城施放的 self 法術才列 cast(免空選單)
            opts.append(("cast", "施法(預施/預召喚)"))
        opts.append(("inventory", "背包"))
        opts.append(("sheet", "角色卡"))
        if player.can_level_up():                          # 地城內也能升級(達門檻即可,免回城)
            opts.append(("levelup", "★ 升級"))
        if cell["type"] == dungeoncrawl.STAIRS:
            opts.append(("descend", f"⬇ 下到第 {z + 2}/{m} 層"))
        opts.append(("leave", "離開地城"))
        choice = ui.menu("地城探索", opts)
        if choice is None or choice == "leave":
            ui.message("你循來路退出了地城。", style="grey70")
            state.time.advance(1)
            return None
        if choice == "cast":                               # 自由行動(不耗回合)
            action_cast_self(state, gamedata, battle=battle)
        elif choice == "levelup":                          # 自由行動(不耗回合):安全點主動升級
            action_level_up(state, gamedata)
        elif choice == "inventory":
            action_inventory(state, gamedata)
        elif choice == "sheet":
            action_character_sheet(state, gamedata)
        elif choice == "descend":
            z += 1
            x = y = 0
            ui.message(f"你拾級而下,來到第 {z + 1}/{m} 層。", style="magenta")
            reveal_and_train(z, x, y)
            case_layer(z)                                  # 賊眼·窺探:新層即揭陷阱/寶箱
            if tick_turn():                                # 移動=1 回合(增益/召喚衰減 + DoT 結算)
                return "dead"
        elif choice.startswith("go:"):
            key = choice[3:]
            for k, _l, nx, ny in dungeoncrawl.neighbors(grid, x, y):
                if k == key:
                    x, y = nx, ny
                    break
            reveal_and_train(z, x, y)
            if tick_turn():
                return "dead"


# ======================================================================
# 背包與裝備
# ======================================================================
def _read_book(state: GameState, gamedata: GameData, item_id: str) -> None:
    """閱讀一本「擇徑禁書」(R49:赫麥尤斯·莫拉的無限祕典)——

    三選一永久誓福機制:讀者於力量/暗影/魔法之徑中擇一,授予對應誓福(走通用 boons 層),
    書隨即消耗(Mora 收回)。**選擇永久且不可逆**;未選(返回)則不消耗,可日後再讀。
    UI 留在 main.py(R27:systems 不直呼 ui),比照 action_shrine。
    """
    char = state.player
    d = gamedata.item(item_id)
    eff = d.get("effect") or {}
    if eff.get("type") != "grant_choice" or inventory.count_item(char, item_id) <= 0:
        return
    paths = eff.get("paths") or []
    opts = [(p["boon"], p["label"]) for p in paths
            if p.get("boon") in getattr(gamedata, "boons", {})]
    if not opts:
        return
    ui.message(f"你翻開了{d['name']} —— 書頁自行翻動,墨綠色的字句在眼前重組,"
               "要你擇一徑而行。此選擇永久且不可逆。", style="cyan")
    choice = ui.menu("無限祕典 —— 擇一徑而行(永久且不可逆)", opts, allow_back=True)
    if choice is None:
        return   # 未擇徑:書不消耗,可日後再讀
    boons.grant(char, gamedata, choice)            # 末尾自帶 recompute_max_resources
    inventory.remove_item(char, item_id, 1)        # 書隨即消失(Mora 收回)
    bname = gamedata.boons[choice]["name"]
    ui.message(f"真知如潮水般湧入你的識海 —— 你得到了永久的誓福「{bname}」。"
               f"{d['name']}在你掌中化作墨綠色的霧氣消散,回到了莫拉的書架上。", style="green")


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
    if d["kind"] == "book" and (d.get("effect") or {}).get("type") == "grant_choice":
        acts.append(("read", "閱讀"))
    if item_id in ("moon_sugar", "skooma"):
        acts.append(("dose", "服用(亢奮 ↔ 成癮)"))
    acts.append(("drop", "丟棄一件"))
    if any(a[0] in ("equip_w", "equip_a") for a in acts):   # 可換裝武器/護甲 → 先呈現換裝對比
        ui.item_compare_panel(char, gamedata, item_id)
    act = ui.menu(d["name"], acts, allow_back=True)
    if act == "equip_w":
        inventory.equip_weapon(char, gamedata, item_id)
        stats.recompute_max_resources(char, gamedata)   # R05:雙手武器自動卸盾 → 沖掉盾的 fortify/resist 幽靈值
        if inventory.is_two_handed(gamedata, item_id):
            ui.message(f"你雙手握起了{d['name']},卸下了盾與副手。", style="green")
        else:
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
        msg = inventory.use_item(char, gamedata, item_id, state)
        ui.message(msg or "無法使用。", style="green")
    elif act == "read":
        _read_book(state, gamedata, item_id)
    elif act == "dose":
        res = skooma.dose(state, gamedata, strong=(item_id == "skooma"))
        inventory.remove_item(char, item_id, 1)
        state.time.advance(1)
        cn = {"fatigue": "體力", "health": "生命", "magicka": "魔力"}
        bits = "、".join(f"{cn[k]} +{v}" for k, v in res["restored"].items() if v)
        ui.message(f"你服下了{d['name']} —— 一陣暖流竄遍全身,反射與耐力陡然亢奮({res['hours']} 小時)"
                   + (f";{bits}。" if bits else "。"), style="magenta")
        if res["addiction"] >= skooma.WITHDRAWAL_THRESHOLD:
            ui.message(f"……但你越來越離不開這抹甜了(成癮 {res['addiction']})。", style="red")
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
            iid = ui.menu(f"行竊哪件?(得手率約 {int(crime.steal_chance(char, gamedata)*100)}%)",
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
            while True:                          # 停留在買貨清單 → 可連續買多樣不同商品
                avail = world.in_stock_items(char, gamedata, loc_id)
                if not avail:
                    ui.message("貨架空空如也,等商人補貨再來吧。", style="grey70")
                    break
                opts = [(iid, f"{gamedata.item_name(iid)} ×{world.stock_qty(char, loc_id, iid)}"
                         f" — {world.buy_price(char, gamedata, iid)} 金") for iid in avail]
                ui.shop_panel(char, gamedata, loc_id, avail)    # web:可點買貨面板(對齊選單 key=iid)
                iid = ui.menu(f"買什麼?(你有 {char.gold} 金)", opts, allow_back=True)
                if iid is None:
                    break
                price = world.buy_price(char, gamedata, iid)
                stock = world.stock_qty(char, loc_id, iid)
                cap = min(stock, char.gold // price) if price > 0 else stock
                if cap < 1:
                    ui.message("金幣不足。", style="red")
                elif not inventory.can_carry(char, gamedata, iid):
                    ui.message("背負不下,太重了。", style="red")
                else:
                    qty = 1 if cap == 1 else ui.ask_int(f"買幾個?(上限 {cap})", 1, 1, cap)
                    bought = 0
                    for _ in range(qty):
                        if (char.gold < price or world.stock_qty(char, loc_id, iid) <= 0
                                or not inventory.can_carry(char, gamedata, iid)):
                            break
                        char.gold -= price
                        inventory.add_item(char, iid, 1)
                        world.take_stock(char, loc_id, iid)
                        bought += 1
                    if bought:
                        ui.message(f"買下了{gamedata.item_name(iid)} ×{bought}。", style="green")
                    else:
                        ui.message("背負不下,太重了。", style="red")
        else:
            while True:                          # 停留在賣貨清單 → 可連續賣多樣不同商品
                sellable = [s for s in char.inventory if gamedata.item(s["id"])["value"] > 0]
                if not sellable:
                    ui.message("沒有可賣的東西。", style="grey70")
                    break
                opts = [(s["id"], f"{ui.item_label(gamedata, char, s['id'], s['qty'])} — 售 "
                         f"{world.sell_price(char, gamedata, s['id'])} 金") for s in sellable]
                ui.inventory_panel(char, gamedata)    # web:複用背包面板,可賣列(key=stack id)可點
                iid = ui.menu(f"賣什麼?(你有 {char.gold} 金)", opts, allow_back=True)
                if iid is None:
                    break
                owned = inventory.count_item(char, iid)
                qty = 1 if owned <= 1 else ui.ask_int(f"賣幾個?(共 {owned})", 1, 1, owned)
                total = sold = 0
                for _ in range(qty):
                    if inventory.count_item(char, iid) <= 0:
                        break
                    total += world.sell_price(char, gamedata, iid)   # 隨交易技能微升,逐件結算
                    inventory.remove_item(char, iid, 1)
                    sold += 1
                    progression.use_skill(char, gamedata, "mercantile", 0.3)
                char.gold += total
                # 賣掉最後一件會自動卸下;若是 fortify 護甲,須重算以移除其加成並夾限當前值
                stats.recompute_max_resources(char, gamedata)
                ui.message(f"賣出{gamedata.item_name(iid)} ×{sold},得 {total} 金。", style="green")


MAX_PARTY = party.MAX_PARTY              # 同時在隊上限(單一真實來源在 party.py)
COMPANIONS_CIRCLE_RANK = lycanthropy.RITUAL_RANK_INDEX   # 戰友團「內圈」門檻(獸血儀式 + 召集盾袍兄弟)
# R-smuggle:盜賊公會「斯庫瑪走私生意」(高階解鎖·只在艾爾斯維爾分舵=月糖源)。兩段 gate 讓階級梯有意義。
SMUGGLE_PROVINCE = "艾爾斯維爾"           # 走私生意只在貓人故土的盜賊公會分舵(森查爾/科林斯)經營
SMUGGLE_RANK_1 = 2                        # 拉拔手:解鎖走私生意(精煉 + 近程走私委託)
SMUGGLE_RANK_2 = 4                        # 夜行者:解鎖長程大宗走私委託
_SCOMM_MIN_RANK = {"scomm_riften": SMUGGLE_RANK_2, "scomm_wayrest": SMUGGLE_RANK_2}   # 長程委託需高階;其餘 = SMUGGLE_RANK_1
CINT_RANK = 2                             # R99 反間委託榜:犯罪公會高階(rank≥2)在大廳解鎖獵敵方諜員的反間契約
# R89:戰士/法師公會「招牌動詞」rank-gated 服務(承 R88·功能化原本只有折扣的冷階級梯)。不限省份(一般公會服務)。
FORGE_RANK = 2            # 戰士公會步兵:軍械庫淬鍊(公會供料·免材料)
ARCANE_RECHARGE_RANK = 2  # 法師公會魔導士:奧術回充(免靈魂石回充充能型附魔武器)
ARCANE_SUPPLY_RANK = 3    # 法師公會巫師:魔力補給(補滿魔力藥水)
MAGE_POTION_SUPPLY_N = 3  # 魔力補給上限(低值 minor_magicka_potion·< R52 治療藥水補給先例 → 售賣套利可忽略)

# 八職功能性身份:戰士盾牆 / 騎士戰旗 為戰鬥動作的常數(技能門檻用 base_skill;暫態存 active_effects)
SHIELD_WALL_BLOCK_GATE = 50     # 持盾 + 格擋達此 base 技能 → 可立盾牆
SHIELD_WALL_MITIGATION = 0.30   # 盾牆物理減傷
SHIELD_WALL_ALLY_ARMOR = 8      # 盾牆給每位同伴的護甲光環
SHIELD_WALL_UPKEEP = 6          # 盾牆每回合體力上繳(歸 0 自動落陣)
STANDARD_ILLUSION_GATE = 50     # 幻術達此 base 技能 → 可立戰旗(騎士專屬軸)
STANDARD_EMPOWER_BASE = 0.20    # 戰旗對同伴的基礎增傷(隨幻術 power 縮放)
STANDARD_SELF_ARMOR = 6         # 戰旗給騎士自身的護甲(單挑也值得立)
STANDARD_COST_MAGICKA = 15      # 立旗魔力代價
STANDARD_COST_FATIGUE = 10      # 立旗體力代價
RALLY_EMPOWER = 0.15            # 口才「戰陣號令」對同伴的增傷(固定,不吃 power;嚴格 < 戰旗 0.20 上界)
RALLY_FATIGUE = 12             # 立號令體力代價(純耗體不耗魔;口才宗師以聲喝振士氣)
VAMPIRE_CHARM_FATIGUE = 10     # 吸血鬼「魅惑凝視」體力代價(每場一次;R56)
VAMPIRE_CHARM_TURNS = 2        # 魅惑凝視:被迷惑之敵恐懼不進攻的回合數
TRIAGE_ALLY_HP_RATIO = 0.30     # 同伴生命低於此 → 觸發治療師「戰地搶救」武裝


def action_inn(state: GameState, gamedata: GameData) -> None:
    char = state.player
    while True:
        roster_str = "、".join(_party_label(char, gamedata, c) for c in char.companions) or "無"
        opts = [("rest", "過夜(10 金,完全回復)"), ("hire", "雇用傭兵同伴")]
        if char.companions:
            opts.append(("dismiss", "解散傭兵"))
        choice = ui.menu(f"旅店(目前隊伍:{roster_str})", opts, allow_back=True)
        if choice is None:
            return
        if choice == "rest":
            fee = 10
            if char.gold < fee:
                ui.message(f"住一晚要 {fee} 金,你付不起。", style="red")
            else:
                char.gold -= fee
                char.health, char.magicka, char.fatigue = char.max_health, char.max_magicka, char.max_fatigue
                party.heal_full(char, gamedata)   # 同伴一併滿血(負傷盡復,可再上陣)
                state.time.advance(8)
                ui.message("一夜好眠,你與同伴皆氣力盡復。", style="green")
        elif choice == "hire":
            _hire_mercenary(state, gamedata)
        elif choice == "dismiss":
            _dismiss_mercenary(state, gamedata)


# ======================================================================
# 馬廄(坐騎 + 騎兵長槍)
# ======================================================================
def action_stable(state: GameState, gamedata: GameData) -> None:
    """馬廄:購置坐騎(戰馬/獵馬/法駒)、切換現乘、選購長槍(騎兵武器)。"""
    char = state.player
    while True:
        cur = gamedata.mount(char.active_mount)
        opts: list = []
        for mid, m in gamedata.mounts.items():        # 購買尚未擁有的坐騎
            if not mounts.owns(char, mid):
                opts.append((f"buy:{mid}", f"購買{m['name']}({m['price']} 金) · {m['desc']}"))
        if char.mounts_owned:
            opts.append(("switch", "切換現乘坐騎"))
        opts.append(("spear", "選購長槍(騎兵武器)"))
        choice = ui.menu(f"馬廄(現乘:{cur['name'] if cur else '步行'})", opts, allow_back=True)
        if choice is None:
            return
        if choice.startswith("buy:"):
            mid = choice[4:]
            m = gamedata.mount(mid)
            if char.gold < m["price"]:
                ui.message("金幣不足,買不起這匹坐騎。", style="red")
                continue
            char.gold -= m["price"]
            mounts.buy(char, gamedata, mid)
            ui.message(f"你購得{m['name']},翻身上馬 —— 從此趕路更快、馱載更多。", style="bold green")
        elif choice == "switch":
            sopts = [("__walk__", "步行(下馬)")] + [(mid, gamedata.mount(mid)["name"])
                                                    for mid in char.mounts_owned]
            pick = ui.menu("現乘哪匹坐騎?", sopts, allow_back=True)
            if pick is None:
                continue
            char.active_mount = "" if pick == "__walk__" else pick
            ui.message("你選擇步行。" if pick == "__walk__"
                       else f"你改乘{gamedata.mount(pick)['name']}。", style="cyan")
        elif choice == "spear":
            _buy_stable_spears(state, gamedata)


def _buy_stable_spears(state: GameState, gamedata: GameData) -> None:
    """馬廄選購長槍(騎兵武器;可衝鋒高倍率)。價格走一般商店定價。"""
    char = state.player
    while True:
        opts = []
        for sid in gamedata.stable_spears:
            d = gamedata.item(sid)
            opts.append((sid, f"{d['name']}(傷 {d['damage']} · {world.buy_price(char, gamedata, sid)} 金)"))
        pick = ui.menu("選購長槍(騎兵武器)", opts, allow_back=True)
        if pick is None:
            return
        price = world.buy_price(char, gamedata, pick)
        if char.gold < price:
            ui.message("金幣不足。", style="red")
            continue
        if not inventory.can_carry(char, gamedata, pick):
            ui.message("負重不足,背不動了。", style="red")
            continue
        char.gold -= price
        inventory.add_item(char, pick, 1)
        ui.message(f"你購得{gamedata.item_name(pick)}。", style="green")


# ======================================================================
# 房產(收納倉庫 + 最佳休息 + 精神飽滿)
# ======================================================================
def action_house(state: GameState, gamedata: GameData) -> None:
    """房產:未擁有 → 置產;已擁有 → 在家安睡(全回 + 精神飽滿)+ 收納倉庫存取。"""
    char = state.player
    loc_id = char.location_id
    if not housing.owns(char, loc_id):
        h = gamedata.house_at(loc_id)
        if not h:
            ui.message("此地沒有可置辦的房產。", style="grey70")
            return
        ui.message(h["desc"], style="grey70")
        if char.gold < h["price"]:
            ui.message(f"「{h['name']}」售價 {h['price']} 金,你的金幣不足。", style="red")
            return
        if not ui.confirm(f"以 {h['price']} 金購置「{h['name']}」嗎?"):
            return
        char.gold -= h["price"]
        housing.buy(char, gamedata, loc_id)
        ui.message(f"你購置了「{h['name']}」—— 從此在此地有了一個家。", style="bold green")
        return
    h = gamedata.house_at(loc_id) or {}
    while True:
        opts = [("rest", "在家安睡(免費全回 + 精神飽滿)"),
                ("deposit", "存入倉庫(卸下負重)"), ("withdraw", "從倉庫取出")]
        choice = ui.menu(h.get("name", "你的房產"), opts, allow_back=True)
        if choice is None:
            return
        if choice == "rest":
            char.health, char.magicka, char.fatigue = char.max_health, char.max_magicka, char.max_fatigue
            party.heal_full(char, gamedata)
            housing.set_well_rested(char, state.time.absolute_hours())
            state.time.advance(8)
            ui.message("你在自家床榻上安睡一夜 —— 氣力盡復,精神飽滿(此後一段時間技能成長加速)。",
                       style="bold green")
        elif choice == "deposit":
            _stash_transfer(state, gamedata, loc_id, deposit=True)
        elif choice == "withdraw":
            _stash_transfer(state, gamedata, loc_id, deposit=False)


def _stash_transfer(state: GameState, gamedata: GameData, loc_id: str, deposit: bool) -> None:
    """房產倉庫存取一件(deposit=True 背包→倉庫;False 倉庫→背包)。"""
    char = state.player
    while True:
        if deposit:   # 可存:背包中「非穿戴/手持」的堆疊
            rows = [(s["id"], s["qty"]) for s in char.inventory
                    if not housing.is_equipped(char, s["id"])]
            title = "存入哪件?(穿戴/手持中的裝備須先卸下)"
        else:
            rows = [(s["id"], s["qty"]) for s in char.house_stash.get(loc_id, [])]
            title = "取出哪件?"
        if not rows:
            ui.message("沒有可" + ("存入" if deposit else "取出") + "的物品。", style="grey70")
            return
        opts = [(iid, f"{gamedata.item_name(iid)} ×{qty}") for iid, qty in rows]
        pick = ui.menu(title, opts, allow_back=True)
        if pick is None:
            return
        avail = dict(rows)[pick]
        n = 1 if avail == 1 else ui.ask_int(f"幾個?(上限 {avail})", default=avail, lo=1, hi=avail)
        if deposit:
            ok = housing.deposit(char, gamedata, loc_id, pick, n)
            ui.message(f"存入 {gamedata.item_name(pick)} ×{n}。" if ok else "無法存入此物。",
                       style="green" if ok else "red")
        else:
            ok = housing.withdraw(char, gamedata, loc_id, pick, n)
            ui.message(f"取出 {gamedata.item_name(pick)} ×{n}。" if ok else "負重不足,取不出這麼多。",
                       style="green" if ok else "red")


def _player_is_lair_kin(player, loc: dict) -> bool:
    """R51:玩家是否為此巢穴的同類(吸血鬼隱穴↔吸血鬼、狼人巢穴↔狼人)。"""
    lr = loc.get("lair")
    return ((lr == "vampire" and vampirism.is_vampire(player))
            or (lr == "werewolf" and lycanthropy.is_werewolf(player)))


_LAIR_FACTION = {"vampire": "coven_vampire", "werewolf": "werewolf_pack"}   # R52:巢穴 → 詛咒陣營


def _lair_pending_duel(char, gamedata: GameData, fac: str):
    """頂階任務已接、未完成 → 回 (qid, master 生物 id)(決鬥對象);否則 (None, None)。"""
    cap_qid = gamedata.factions[fac]["rank_quests"][-1]
    if cap_qid in char.quests and cap_qid not in char.completed_quests:
        obj = quests.resolved(char, gamedata, cap_qid).get("objective") or {}
        if obj.get("type") == "kill":
            return cap_qid, obj.get("creature")
    return None, None


def _lair_affairs(state: GameState, gamedata: GameData, fac: str) -> str | None:
    """R52 血族/獵群事務:入會 / 接晉階任務 / 頂階決鬥(挑戰現任血主·頭狼)。比照 action_guild_hall。
    回傳 'dead'(決鬥身亡)或 None。"""
    char = state.player
    f = gamedata.factions[fac]
    while True:
        opts = []
        if not factions.is_member(char, fac):
            opts.append(("join", f"加入{f['name']}"))
        else:
            _qid, master = _lair_pending_duel(char, gamedata, fac)
            if master:
                opts.append(("duel", f"⚔ {f['ranks'][-1]}之爭 —— 挑戰{gamedata.bestiary[master]['name']}"))
            avail = quests.available_quests(char, gamedata, "guild", fac)
            if avail:
                opts.append(("accept", f"接取晉階任務:{gamedata.quests[avail[0]]['name']}"))
        rank_lbl = f"(階級:{factions.rank_name(char, gamedata, fac)})" if factions.is_member(char, fac) else ""
        choice = ui.menu(f"{f['name']}事務{rank_lbl}", opts, allow_back=True)
        if choice is None:
            return None
        if choice == "join":
            reason = factions.join_block_reason(char, gamedata, fac)
            if reason:
                ui.message(reason, style="yellow")
            else:
                factions.join(char, fac)
                ui.message(f"你被接納為{f['name']}的{factions.rank_name(char, gamedata, fac)} —— "
                           "自此巢穴是你的家,階序是你攀爬的路。", style="bold red")
        elif choice == "accept":
            avail = quests.available_quests(char, gamedata, "guild", fac)
            if avail:
                _accept_and_brief(state, gamedata, avail[0])
                return None
        elif choice == "duel":
            _qid, master = _lair_pending_duel(char, gamedata, fac)
            if not master:
                continue
            ui.rule(f"{f['ranks'][-1]}之爭")
            ui.message(f"最後一階只能以血與牙來定 —— 你直面{gamedata.bestiary[master]['name']}。", style="bold red")
            boss = combat.spawn_creature(gamedata, master, state.rng)
            if run_battle(state, gamedata, boss) == "dead":
                return "dead"
            quests.record_kill(char, master)
            quests.check_completion(char, gamedata)   # 頂階任務完成 → 晉升 + 授頂階誓福(grant_boon)+ 頭銜旗
            ui.message(f"你踏著對手的血,坐上了{f['name']}的最高之位 —— 你成了"
                       f"{factions.rank_name(char, gamedata, fac)}。", style="bold green")
            return None


def action_lair(state: GameState, gamedata: GameData) -> str | None:
    """R51 巢穴(安全區)+ R52 血族/獵群階級事務 + 巢穴升級(rank-gated 設施)。
    回傳 'dead'(頂階決鬥身亡)或 None。巢穴非城/鎮 → R50 圍捕不觸發;hub 已以詛咒閘擋凡人。"""
    char = state.player
    loc = world.current_location(char, gamedata)
    if not _player_is_lair_kin(char, loc):
        return None
    lair = loc.get("lair")
    fac = _LAIR_FACTION[lair]
    loc_id = char.location_id
    kin = next((n for n in gamedata.npcs if gamedata.npcs[n].get("location") == loc_id), None)
    while True:
        rank = factions.rank_index(char, fac)
        affairs_lbl = ("🩸 血族事務" if lair == "vampire" else "🐺 獵群事務") \
            + (f"(階級:{factions.rank_name(char, gamedata, fac)})" if rank >= 0 else "(入會)")
        opts = [("affairs", affairs_lbl)]
        if lair == "vampire":
            opts.append(("feed", "🩸 安心進食(同類供血,不被撞見)"))
        elif lair == "werewolf" and lycanthropy.can_transform(char, state, gamedata):
            opts.append(("shift", "🐺 在巢穴中獸化(安全)"))
        if rank >= 1:        # R52 巢穴升級:血泉/獵壇(即時全回)
            opts.append(("font", "🩸 血泉(即時全回)" if lair == "vampire" else "🐺 獵壇(即時全回)"))
        if rank >= 2:        # R52 巢穴升級:補給(補滿治療藥水)
            opts.append(("supply", "血庫補給(補滿治療藥水)" if lair == "vampire" else "獸糧補給(補滿治療藥水)"))
        opts += [("rest", "在此安歇(免費全回 + 精神飽滿)"),
                 ("deposit", "存入密窖(卸下負重)"), ("withdraw", "從密窖取出")]
        if kin:
            opts.append(("kin", f"與{gamedata.npcs[kin]['name']}交談"))
        choice = ui.menu(loc["name"], opts, allow_back=True)
        if choice is None:
            return None
        if choice == "affairs":
            if _lair_affairs(state, gamedata, fac) == "dead":
                return "dead"
        elif choice == "feed":
            res = vampirism.feed(state, gamedata, safe=True)     # 同類供血:必不被撞見
            ui.message(f"同類為你引來溫順的活人 —— 你飽飲一頓,飢渴盡退(回復 {res['healed']} 生命),無人撞見。",
                       style="bold green")
        elif choice == "shift":
            action_use_power(state, gamedata)                    # 變身;巢穴非城鎮 → 無圍捕
        elif choice == "font":
            char.health, char.magicka, char.fatigue = char.max_health, char.max_magicka, char.max_fatigue
            party.heal_full(char, gamedata)
            ui.message("你俯身飲下巢穴湧出的血泉 —— 傷勢瞬間癒合、氣力如新(即時、不耗時)。" if lair == "vampire"
                       else "你在獵壇前飽食生肉 —— 傷勢瞬間癒合、氣力如新(即時、不耗時)。", style="bold green")
        elif choice == "supply":
            got = 0
            while inventory.count_item(char, "healing_potion") < 3:
                inventory.add_item(char, "healing_potion", 1)
                got += 1
            ui.message(f"同類替你備足了補給(治療藥水 +{got},補至 3 瓶)。" if got else "你的補給已滿。",
                       style="green")
        elif choice == "rest":
            char.health, char.magicka, char.fatigue = char.max_health, char.max_magicka, char.max_fatigue
            party.heal_full(char, gamedata)
            housing.set_well_rested(char, state.time.absolute_hours())
            state.time.advance(8)
            ui.message("你在同類環伺的巢穴中安歇一晚 —— 氣力盡復,精神飽滿(此後一段時間技能成長加速)。",
                       style="bold green")
        elif choice == "deposit":
            _stash_transfer(state, gamedata, loc_id, deposit=True)
        elif choice == "withdraw":
            _stash_transfer(state, gamedata, loc_id, deposit=False)
        elif choice == "kin" and kin:
            _lair_kin_talk(state, gamedata, kin)


def _lair_kin_talk(state: GameState, gamedata: GameData, nid: str) -> None:
    """與巢穴同類交談:招呼 +(好感足夠且未接/未完成)接其委託(招募同類同伴)。複用 dialogue/任務管線。"""
    char = state.player
    npc = gamedata.npcs[nid]
    ui.message(npc.get("greeting", ""), style="cyan")
    offered = dialogue.offered_quest(char, gamedata, nid)
    if offered:
        if ui.confirm(f"接受{npc['name']}的委託「{gamedata.quests[offered]['name']}」?"):
            _accept_and_brief(state, gamedata, offered)
    else:
        ui.message("(你與同類在火光邊低語了一陣 —— 暫無新的託付。)", style="grey70")


# R84 亡命徒地下世界:銷贓 fence + 地下委託 + 藏身處(安全區)。is_outlaw 閘可見性;refuge 地點 danger1·非城鎮 → 天然安全區。
_BLACK_MARKET = ["lockpick", "skooma", "moon_sugar", "nightshade"]   # 黑市常售(亡命徒窩點;防套利地板恆守)

# R98 神話黎明同志「禁術貨源」可購清單:廣義黑市稀材(平時難買的試劑 + 靈魂石)。
# 🔴 全為既有可購 id、刻意排除 world._LOOT_ONLY_MATERIALS(daedra_heart/dragon_scale);
# 售價走 world.buy_price(內建 max(1,round,sell+1) 地板 → 買回再賣恆虧,金幣只出不進)。
_MYTHIC_SUPPLY = ["vampire_dust", "void_salts", "deathbell", "nightshade",
                  "crimson_nirnroot", "glow_dust",
                  "empty_common_soul_gem", "empty_greater_soul_gem"]


def action_fence(state: GameState, gamedata: GameData) -> None:
    """銷贓窩點:贓物/雜物以加價(fence_bonus·隨惡名分級)賣出 + 購入黑市貨。
    🔴 防套利:黑市買價恆 = max(正常買價, 該物銷價+1) > 銷價 → 買來回銷必虧,杜絕無限刷錢(比照 R33)。"""
    char = state.player
    bonus = crime.fence_bonus(char)

    def fsell(iid):                                 # 銷贓價(加價);buy 端用它築地板
        return int(world.sell_price(char, gamedata, iid) * (1 + bonus))

    while True:
        choice = ui.menu(f"銷贓窩點(加價 +{int(bonus * 100)}%)",
                         [("sell", "銷贓(賣出贓物/雜物)"), ("buy", "購入黑市貨")], allow_back=True)
        if choice is None:
            return
        if choice == "sell":
            while True:
                sellable = [s for s in char.inventory if gamedata.item(s["id"])["value"] > 0]
                if not sellable:
                    ui.message("沒有可銷的東西。", style="grey70")
                    break
                opts = [(s["id"], f"{ui.item_label(gamedata, char, s['id'], s['qty'])} — 銷 {fsell(s['id'])} 金")
                        for s in sellable]
                iid = ui.menu(f"銷什麼?(你有 {char.gold} 金)", opts, allow_back=True)
                if iid is None:
                    break
                owned = inventory.count_item(char, iid)
                qty = 1 if owned <= 1 else ui.ask_int(f"銷幾個?(共 {owned})", 1, 1, owned)
                total = sold = 0
                for _ in range(qty):
                    if inventory.count_item(char, iid) <= 0:
                        break
                    total += fsell(iid)
                    inventory.remove_item(char, iid, 1)
                    sold += 1
                    progression.use_skill(char, gamedata, "mercantile", 0.3)
                char.gold += total
                stats.recompute_max_resources(char, gamedata)   # 銷掉穿戴中最後一件會自動卸下 → 重算
                ui.message(f"銷出 {gamedata.item_name(iid)} ×{sold},得 {total} 金。", style="green")
        elif choice == "buy":
            while True:
                opts = [(iid, f"{gamedata.item_name(iid)} — {max(world.buy_price(char, gamedata, iid), fsell(iid) + 1)} 金")
                        for iid in _BLACK_MARKET]
                iid = ui.menu(f"購入什麼?(你有 {char.gold} 金)", opts, allow_back=True)
                if iid is None:
                    break
                price = max(world.buy_price(char, gamedata, iid), fsell(iid) + 1)   # 防套利地板:恆 > 銷贓價
                if char.gold < price:
                    ui.message("錢不夠。", style="yellow")
                    continue
                char.gold -= price
                inventory.add_item(char, iid, 1)
                ui.message(f"購入 {gamedata.item_name(iid)},付 {price} 金。", style="green")


def _comrade_supply(state: GameState, gamedata: GameData) -> None:
    """R98 神話黎明同志「禁術貨源」:買入廣義黑市稀材(buy-only)。
    price 走 world.buy_price 內建防套利地板(買回再賣恆虧),金幣只出不進。"""
    char = state.player
    while True:
        opts = [(iid, f"{gamedata.item_name(iid)} — {world.buy_price(char, gamedata, iid)} 金")
                for iid in _MYTHIC_SUPPLY]
        iid = ui.menu(f"禁術貨源(你有 {char.gold} 金)", opts, allow_back=True)
        if iid is None:
            return
        price = world.buy_price(char, gamedata, iid)
        if char.gold < price:
            ui.message("錢不夠。", style="yellow")
            continue
        char.gold -= price
        inventory.add_item(char, iid, 1)
        ui.message(f"購入 {gamedata.item_name(iid)},付 {price} 金。", style="green")


def _comrade_contract(state: GameState, gamedata: GameData) -> str | None:
    """R98 黑暗兄弟會同志「接私活」:就地領受/執行合約(複用聖所合約池,無雙重獎勵)。
    刻意只開接取/執行(不含聖所專屬的洗白/五戒)→ 不把可攜式賞金洗白偷渡進來。回傳 'dead'|None。"""
    char = state.player
    _report_quests(state, gamedata)   # 先結算可能已交付的合約
    while True:
        active = _active_db_quest(state, gamedata)
        opts: list = []
        if active:
            obj, _, _ = quests.current_objective(char, gamedata, active)
            tname = gamedata.bestiary[obj["creature"]]["name"]
            opts.append(("execute", f"執行合約 —— 行刺{tname}"))
        else:
            avail = quests.available_quests(char, gamedata, "guild", brotherhood.FACTION)
            if avail:
                opts.append(("accept", "接取新合約"))
            else:
                ui.message("「……眼下沒有見得了人的活計。靜候風聲。」", style="grey70")
        choice = ui.menu("私活", opts, allow_back=True) if opts else None
        if choice is None:
            return None
        if choice == "accept":
            avail = quests.available_quests(char, gamedata, "guild", brotherhood.FACTION)
            if avail:
                _accept_and_brief(state, gamedata, avail[0])
        elif choice == "execute":
            if action_contract(state, gamedata, active) == "dead":
                return "dead"


def _counterintel_board(state: GameState, gamedata: GameData) -> None:
    """R99 反間委託榜:列出本省被脈動聚光的 cint_* 反間契約(獵敵方諜員)。
    犯罪公會 rank-gated 大廳服務(由各大廳閘 rank≥CINT_RANK);複用 R79 board+pulse,與正規告示板分流。"""
    char = state.player
    province = world.current_location(char, gamedata)["province"]
    while True:
        today = worldpulse.day_index(state)
        avail = [q for q in quests.available_quests(char, gamedata, "board", province=province, day=today)
                 if q.startswith("cint_")]
        if not avail:
            ui.message("眼下沒有反間的線報 —— 敵方諜員蟄伏未動,或風聲尚未傳到本地。"
                       "(反間委託隨『四方傳聞』的風向起落)", style="grey70")
            return
        opts = [(qid, f"{gamedata.quests[qid]['name']} — {quests.objective_text(char, gamedata, qid)}"
                 f"(賞 {gamedata.quests[qid]['reward'].get('gold', 0)} 金·聲望 +{gamedata.quests[qid]['reward'].get('fame', 0)})")
                for qid in avail]
        qid = ui.menu("反間委託榜", opts, allow_back=True)
        if qid is None:
            return
        _accept_and_brief(state, gamedata, qid)


def _underworld_contracts(state: GameState, gamedata: GameData) -> None:
    """地下委託:列出本省被聚光的 ucomm_* 可重複契約(複用 R79 board+pulse;與正規告示板分流)。"""
    char = state.player
    province = world.current_location(char, gamedata)["province"]
    while True:
        today = worldpulse.day_index(state)
        avail = [q for q in quests.available_quests(char, gamedata, "board", province=province, day=today)
                 if q.startswith("ucomm_")]
        if not avail:
            ui.message("地下風聲未起 —— 眼下沒有見得了人的委託。(地下委託隨『四方傳聞』的風向起落)", style="grey70")
            return
        opts = [(qid, f"{gamedata.quests[qid]['name']} — {quests.objective_text(char, gamedata, qid)}"
                 f"(賞 {gamedata.quests[qid]['reward'].get('gold', 0)} 金·惡名 +{gamedata.quests[qid]['reward'].get('infamy', 0)})")
                for qid in avail]
        qid = ui.menu("地下委託", opts, allow_back=True)
        if qid is None:
            return
        _accept_and_brief(state, gamedata, qid)


def action_refuge(state: GameState, gamedata: GameData) -> None:
    """R84 亡命徒藏身處(安全區):休息 / 密窖 / 銷贓 / 地下委託。
    refuge 地點 danger1·非城鎮 → guard_confrontation/_curse_manhunt 天然不觸發;hub 已以 is_outlaw 閘擋良民。"""
    char = state.player
    loc = world.current_location(char, gamedata)
    if not crime.is_outlaw(char) or not loc.get("refuge"):
        return
    loc_id = char.location_id
    while True:
        title = crime.notoriety_title(char)
        header = loc["name"] + (f"(身分:{title})" if title else "")
        opts = [("rest", "在此安歇(免費全回 + 精神飽滿)"),
                ("fence", "🪙 銷贓窩點"),
                ("contracts", "📜 地下委託"),
                ("deposit", "存入密窖(卸下負重)"),
                ("withdraw", "從密窖取出")]
        choice = ui.menu(header, opts, allow_back=True)
        if choice is None:
            return
        if choice == "rest":
            char.health, char.magicka, char.fatigue = char.max_health, char.max_magicka, char.max_fatigue
            party.heal_full(char, gamedata)
            housing.set_well_rested(char, state.time.absolute_hours())
            state.time.advance(8)
            ui.message("你在亡命徒環伺的窩點歇了一晚 —— 氣力盡復,精神飽滿(此後一段時間技能成長加速)。",
                       style="bold green")
        elif choice == "fence":
            action_fence(state, gamedata)
        elif choice == "contracts":
            _underworld_contracts(state, gamedata)
        elif choice == "deposit":
            _stash_transfer(state, gamedata, loc_id, deposit=True)
        elif choice == "withdraw":
            _stash_transfer(state, gamedata, loc_id, deposit=False)


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


SKOOMA_CURE_QID = skooma.CURE_QUEST_ID   # 唯一來源在 skooma.py(自然戒除時亦由其棄置殘留任務)


def action_skooma_cure(state: GameState, gamedata: GameData) -> None:
    """探詢/推進/完成『淨糖之儀』—— 解除斯庫瑪/月糖之癮(任何聚落療者,僅成癮者可見)。"""
    char = state.player
    if not skooma.is_addicted(char):
        return
    _report_quests(state, gamedata)   # 先結算可能已達標的採集/擊殺階段

    if quests.is_done(char, SKOOMA_CURE_QID):
        ui.message("療者取來你備齊的大蒜、毒茄參與那縷暗潮腐血,在雙月的微光下行起古老的淨糖之儀……",
                   style="white")
        if not ui.confirm("月糖之癮將在此夜被滌淨 —— 進行淨糖之儀嗎?"):
            return
        skooma.cure(char, gamedata)
        char.completed_quests.remove(SKOOMA_CURE_QID)   # 解咒可重複(日後再沾染,可再求一次)
        ui.rule("月糖之癮已解")
        ui.message("一陣翻江倒海的冷顫後,渴求自血脈退散 —— 你的神智重歸澄澈,不再為那抹甜所縛。",
                   style="bold green")
        return

    if quests.is_active(char, SKOOMA_CURE_QID):
        ui.message(f"淨糖進度:{quests.objective_text(char, gamedata, SKOOMA_CURE_QID)}", style="white")
        ui.message("備齊淨化媒介、取得暗潮腐血後,回到任一聚落療者處行儀式。", style="grey70")
        return

    ui.message(gamedata.quests[SKOOMA_CURE_QID]["text"], style="white")
    if ui.confirm("接下『淨糖之儀』,踏上戒除之路嗎?"):
        quests.accept_quest(char, gamedata, SKOOMA_CURE_QID)
        ui.message("已接取任務:淨糖之儀", style="bold yellow")
        _report_quests(state, gamedata)


WEREWOLF_CURE_QID = "cure_lycanthropy"


def action_disease_cure(state: GameState, gamedata: GameData) -> None:
    """R53 神殿療者淨化(任何聚落,僅有病/潛伏時可見):免費治好普通病 + 解吸血/狼人**潛伏期**。
    🔴 **不解已轉化的吸血鬼/狼人**(那仍須各自的深度解咒任務)。"""
    char = state.player
    if not (diseases.has_any(char) or vampirism.is_infected(char) or lycanthropy.is_infected(char)):
        ui.message("神殿療者端詳了你一陣:「你身上並無需要淨化的病症,旅人。」", style="grey70")
        return
    if not ui.confirm("讓神殿療者為你誦經淨化(免費)?"):
        return
    res = diseases.purify(char, gamedata)
    ui.rule("神殿淨化")
    ui.message("神殿療者以聖水與禱詞為你淨化 —— " + diseases.purify_message(res), style="bold green")


def action_werewolf_cure(state: GameState, gamedata: GameData) -> None:
    """探詢/推進/完成『滌淨獸血』—— 解除狼人化(任何聚落的獵巫女巫,僅狼人可見)。"""
    char = state.player
    if not lycanthropy.is_werewolf(char):
        return
    _report_quests(state, gamedata)   # 先結算可能已達標的採集/擊殺階段

    if quests.is_done(char, WEREWOLF_CURE_QID):
        ui.message("獵巫女巫取來你備齊的格倫摩女巫之首與那縷受詛獸血,在篝火與符文間誦起淨化的古調……",
                   style="white")
        if not ui.confirm("獸血之咒將在此夜被滌淨 —— 進行解咒儀式嗎?"):
            return
        lycanthropy.cure(char, gamedata)
        char.completed_quests.remove(WEREWOLF_CURE_QID)   # 解咒可重複(日後再染,可再求一次)
        ui.rule("獸血之咒已解")
        ui.message("一陣翻江倒海的灼痛後,奔流的狼血漸漸冷卻 —— 你重歸純粹的凡人之軀,不再受月之牽引。",
                   style="bold green")
        return

    if quests.is_active(char, WEREWOLF_CURE_QID):
        ui.message(f"滌淨進度:{quests.objective_text(char, gamedata, WEREWOLF_CURE_QID)}", style="white")
        ui.message("備齊淨化媒介、取得受詛獸血後,回到任一聚落的獵巫女巫處行儀式。", style="grey70")
        return

    ui.message(gamedata.quests[WEREWOLF_CURE_QID]["text"], style="white")
    if ui.confirm("接下『滌淨獸血』,踏上解咒之路嗎?"):
        quests.accept_quest(char, gamedata, WEREWOLF_CURE_QID)
        ui.message("已接取任務:滌淨獸血", style="bold yellow")
        _report_quests(state, gamedata)


# ======================================================================
# 黑暗兄弟會聖所(合約晉升 + 夜母祝福 + 洗白賞金)
# ======================================================================
def _active_faction_quest(state: GameState, gamedata: GameData, faction_id: str) -> str | None:
    """目前進行中、屬於某公會的任務 id(沒有則 None)。"""
    for qid in state.player.quests:
        if gamedata.quests.get(qid, {}).get("faction") == faction_id:
            return qid
    return None


def _active_db_quest(state: GameState, gamedata: GameData) -> str | None:
    """目前進行中的黑暗兄弟會合約 id(沒有則 None)。"""
    return _active_faction_quest(state, gamedata, brotherhood.FACTION)


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
        if factions.rank_index(char, brotherhood.FACTION) >= CINT_RANK:   # R99 高階反間委託榜
            opts.append(("counterintel", "🕵 反間委託榜（獵敵方諜員)"))
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
        elif choice == "counterintel":
            _counterintel_board(state, gamedata)
        elif choice == "tenets":
            ui.message("黑暗兄弟會五戒:", style="bold magenta")
            for t in brotherhood.TENETS:
                ui.message(f"  {t}", style="white")


def action_contract(state: GameState, gamedata: GameData, qid: str, *,
                    stealth: bool = True) -> str | None:
    """執行一張合約:暗殺(stealth=True:潛行先機 + 乾淨擊殺賞)或正面討伐
    (stealth=False:聖戰開打,無潛行、無 clean_bonus、無偵查備戰)。回傳 'dead'|None。"""
    char = state.player
    rq = quests.resolved(char, gamedata, qid)
    obj, _, _ = quests.current_objective(char, gamedata, qid)
    target_id = obj["creature"]
    tname = gamedata.bestiary[target_id]["name"]
    prompt = (f"潛入目標所在,取「{tname}」的性命嗎?" if stealth
              else f"正面迎敵,討伐「{tname}」嗎?")
    if not ui.confirm(prompt):
        return None

    enemies = [combat.spawn_creature(gamedata, target_id, state.rng)]
    for eid in rq.get("escort", []):
        enemies.append(combat.spawn_creature(gamedata, eid, state.rng))

    got_drop = False
    pb = 0
    if stealth:
        night = state.time.hour < 6 or state.time.hour >= 21
        got_drop = combat.try_stealth_approach(char, enemies, state.rng, gamedata, night, False, False)
        if got_drop:
            ui.message("你如影潛近,目標渾然未覺 —— 致命先機在握。", style="bold green")
        else:
            ui.message("你的接近驚動了目標,沒能搶到偷襲先機。", style="yellow")
        pb = (formulas.prep_budget(char.skill("scout")) + mastery.prep_bonus(char, gamedata)) if got_drop else 0   # 合約暗殺也享偵查備戰
    else:
        ui.message("你舉起武器、堂堂正正迎敵 —— 以鋼鐵裁決。", style="bold cyan")

    result = run_battle(state, gamedata, enemies, alerted=not got_drop, prep_budget=pb)
    if result == "dead":
        return "dead"
    if result == "fled":
        ui.message("你暫且退去 —— 合約仍懸而未決。" if stealth
                   else "你暫且退下 —— 討伐尚未完成。", style="grey70")
        return None
    # 勝利:結算晉升;暗殺對「無人目擊的乾淨擊殺」額外發賞(正面討伐無此項)
    _report_quests(state, gamedata)
    if stealth and got_drop:
        bonus = rq.get("clean_bonus", 0)
        if bonus:
            char.gold += bonus
            ui.message(f"無人目擊、一擊致命 —— 額外賞你 {bonus} 金。", style="bold green")
    return None


# ======================================================================
# 合約制公會大廳(神話黎明 / 九神騎士團 共用骨架;
# 黑暗兄弟會聖所另有 launder/tenets,維持自有 action_sanctuary 不走此處)
# ======================================================================
_MYTHIC_DAWN_VERSES = [
    "「諸界皆達貢之夢,凡塵不過待焚的薪柴。」",
    "「九聖是牢籠,湮滅之門才是解脫之路。」",
    "「於黎明破曉之時,曼卡將領我等步入天堂。」",
]
_KNIGHTS_NINE_VERSES = [
    "「以無翼者佩利納爾之名,吾劍只為守護而出鞘。」",
    "「九聖同在 —— 阿卡托什的堅毅、瑪拉的慈悲、史丹達爾的公義。」",
    "「縱使秩序將傾,聖徽之光永不熄滅。」",
]


def _contract_hall(state: GameState, gamedata: GameData, faction_id: str, *,
                   stealth: bool, title: str,
                   accept_label: str, execute_label: str, no_quest_msg: str,
                   verses_label: str, verses_intro: str, verses: list,
                   verses_style: str = "bold red",
                   join_prompt: str | None = None, join_success: str | None = None) -> str | None:
    """合約制公會大廳通用骨架:(可選)走入式入會 → 領受/執行委託 → 風味箴言。
    有傳 `join_prompt` 才提供走入入會(九神騎士團於安維爾正面招募);神話黎明改回史實後
    招募只在阿留斯湖遭遇(見 action_explore),故不傳 join_prompt → 對非會員不開門。
    `stealth` 決定執行走暗殺(action_contract 預設)或正面討伐。回傳 'dead'|None。
    (黑暗兄弟會聖所另有洗白/五戒,維持自有 action_sanctuary。)"""
    char = state.player
    _report_quests(state, gamedata)   # 先結算可能已交付的委託
    ui.guild_panel(char, gamedata, faction_id)

    if not factions.is_member(char, faction_id):
        reason = factions.join_block_reason(char, gamedata, faction_id)
        if reason is not None:
            ui.message(reason, style="yellow")
            return None
        # 走入式入會僅限有傳 join_prompt 的公會(九神騎士團);神話黎明不傳 → 此處對非會員不開門
        # (其神殿服務本就 after_faction-gated,非會員無從抵達;此守門僅為自我文件化+防未來誤接服務)。
        if join_prompt is not None and ui.confirm(join_prompt):
            factions.join(char, faction_id)
            ui.message(join_success.format(rank=factions.rank_name(char, gamedata, faction_id)),
                       style="bold green")
        return None

    while True:
        opts: list = []
        active = _active_faction_quest(state, gamedata, faction_id)
        if active:
            obj, _, _ = quests.current_objective(char, gamedata, active)
            tname = gamedata.bestiary[obj["creature"]]["name"]
            opts.append(("execute", execute_label.format(tname=tname)))
        else:
            avail = quests.available_quests(char, gamedata, "guild", faction_id)
            if avail:
                opts.append(("accept", accept_label))
            else:
                ui.message(factions.advance_block_reason(char, gamedata, faction_id)
                           or no_quest_msg, style="grey70")
        # R99:犯罪邪教高階(神話黎明)解鎖反間委託榜;九神騎士團非犯罪公會 → 不顯示
        if factions.is_criminal_guild(faction_id) and factions.rank_index(char, faction_id) >= CINT_RANK:
            opts.append(("counterintel", "🕵 反間委託榜（獵敵方諜員)"))
        opts.append(("verses", verses_label))
        choice = ui.menu(title, opts, allow_back=True)
        if choice is None:
            return None
        if choice == "accept":
            avail = quests.available_quests(char, gamedata, "guild", faction_id)
            if avail:
                _accept_and_brief(state, gamedata, avail[0])
        elif choice == "counterintel":
            _counterintel_board(state, gamedata)
        elif choice == "execute":
            died = action_contract(state, gamedata, active, stealth=stealth)
            if died == "dead":
                return "dead"
        elif choice == "verses":
            ui.message(verses_intro, style=verses_style)
            for line in verses:
                ui.message(f"  {line}", style="white")


def action_mythic_dawn(state: GameState, gamedata: GameData) -> str | None:
    """神話黎明聖堂(神殿內,僅會員可達):領受/執行『獻祭』合約、聆聽《魔典》箴言。回傳 'dead'|None。
    不設走入式入會 —— 招募改回史實,只在阿留斯湖洞窟遭遇教徒、口才說服(見 action_explore)。"""
    return _contract_hall(
        state, gamedata, "mythic_dawn", stealth=True,
        title="神話黎明聖堂", accept_label="領受新的獻祭",
        execute_label="執行獻祭 —— 行刺{tname}",
        no_quest_msg="聖堂目前沒有交付給你的獻祭。",
        verses_label="聆聽《魔典》箴言", verses_intro="赤袍信徒誦讀《魔典》:",
        verses=_MYTHIC_DAWN_VERSES, verses_style="bold red")


def action_knights_hall(state: GameState, gamedata: GameData) -> str | None:
    """九聖小修道院:入會、領受/出征聖戰委託、聆聽聖訓。回傳 'dead'|None。"""
    return _contract_hall(
        state, gamedata, "knights_nine", stealth=False,
        join_prompt="騎士團長按劍而立:「湮滅之門已開,聖團需要新的劍。可願以聖光與鋼鐵,加入九神騎士團?」",
        join_success="你跪在九聖祭壇前立誓,成為九神騎士團的「{rank}」。",
        title="九聖小修道院", accept_label="領受新的聖戰",
        execute_label="出征討伐 —— {tname}",
        no_quest_msg="修道院目前沒有交付給你的聖戰。",
        verses_label="聆聽聖訓", verses_intro="騎士團長誦念聖訓:",
        verses=_KNIGHTS_NINE_VERSES, verses_style="bold cyan")


def _hire_mercenary(state: GameState, gamedata: GameData) -> None:
    char = state.player
    if len(char.companions) >= MAX_PARTY:
        ui.message(f"隊伍已滿(最多 {MAX_PARTY} 名傭兵),先解散一名吧。", style="yellow")
        return
    avail = [cid for cid in gamedata.companions
             if cid not in char.companions and not gamedata.companions[cid].get("troop")
             and not gamedata.companions[cid].get("warlord")    # warlord 將領唯營地可招
             and not gamedata.companions[cid].get("circle")     # circle 盾袍兄弟唯戰友團聖殿召集
             and not gamedata.companions[cid].get("recruit_quest")]  # 具名招募同伴唯任務取得(非花錢即得)
    disc = factions.merc_discount(char, gamedata)               # 戰友團「盾袍之誼」:招募折扣
    def _merc_price(cid: str) -> int:
        return int(round(gamedata.companions[cid]["cost"] * (1 - disc)))
    opts = [(cid, f"{gamedata.companions[cid]['name']} — {_merc_price(cid)} 金:"
             f"{gamedata.companions[cid]['blurb']}") for cid in avail]
    cid = ui.menu(f"雇用哪位?(你有 {char.gold} 金)", opts, allow_back=True)
    if cid is None:
        return
    cost = _merc_price(cid)
    if char.gold < cost:
        ui.message("金幣不足。", style="red")
        return
    char.gold -= cost
    char.companions.append(cid)
    ui.message(f"{gamedata.companions[cid]['name']}加入了你的隊伍,將在戰鬥中並肩作戰。", style="bold green")


def _available_shield_siblings(char: Character, gamedata: GameData) -> list[str]:
    """戰友團圈內可召集、尚未在隊伍中的盾袍兄弟(companions.json `circle:true`)。"""
    return [cid for cid in gamedata.companions
            if gamedata.companions[cid].get("circle") and cid not in char.companions]


def _rally_shield_sibling(state: GameState, gamedata: GameData) -> None:
    """內圈戰友召集一名盾袍兄弟並肩作戰(免費,受隊伍上限)。"""
    char = state.player
    if len(char.companions) >= MAX_PARTY:
        ui.message(f"隊伍已滿(最多 {MAX_PARTY} 名),先解散一名再來召集盾袍兄弟。", style="yellow")
        return
    avail = _available_shield_siblings(char, gamedata)
    opts = [(cid, f"{gamedata.companions[cid]['name']} —— {gamedata.companions[cid]['blurb']}")
            for cid in avail]
    cid = ui.menu("召集哪位盾袍兄弟並肩作戰?", opts, allow_back=True)
    if cid is None:
        return
    char.companions.append(cid)
    ui.message(f"{gamedata.companions[cid]['name']}握住你的前臂:「同袍同澤,與子偕行。」"
               "—— 他加入了你的隊伍。", style="bold green")


def _dismiss_mercenary(state: GameState, gamedata: GameData) -> None:
    char = state.player
    opts = [(cid, _party_label(char, gamedata, cid)) for cid in char.companions]
    cid = ui.menu("解散哪位傭兵?", opts, allow_back=True)
    if cid is None:
        return
    char.companions.remove(cid)
    for _loc in [l for l, s in char.stewards.items() if s == cid]:
        char.stewards.pop(_loc, None)        # 解散坐鎮中的總管 → 同步清掉指派,免殘留死 cid 占住總管位
    nm = gamedata.companions.get(cid, {}).get("name", cid)
    # 一律保留持久 HP/負傷/羈絆(離隊不忘交情):具名同伴可免費再召集;雇傭兵再雇用須付酬金。
    # 不清狀態 → 防「解散→再得」零成本回滿血/解負傷(負傷者仍負傷),且羈絆有記憶(玩家要求)。
    if party.keeps_state_on_dismiss(gamedata, cid):
        ui.message(f"{nm}暫別你的隊伍待命 —— 你隨時能再召集{'他' if gamedata.companions.get(cid,{}).get('circle') else '其'}並肩作戰。",
                   style="grey70")
    else:
        ui.message(f"{nm}拿了酬勞暫別 —— 日後可再花酬金雇回,你們並肩的交情仍在。", style="grey70")


def _party_label(char: Character, gamedata: GameData, cid: str) -> str:
    """同伴列表標籤:名 + HP/上限 + 羈絆級(倒下標『負傷』;冊封坐鎮者標『坐鎮〔城〕』=已離隊治理)。"""
    name = gamedata.companions.get(cid, {}).get("name", cid)   # 防毀損存檔的已移除同伴 id
    loc = next((l for l, s in getattr(char, "stewards", {}).items() if s == cid), None)
    if loc:                                                    # 冊封坐鎮 → 離隊不隨行出戰
        return f"{name}（坐鎮 {gamedata.location(loc)['name']}·{party.bond_name(char, cid)})"
    cur, mx = party.current_hp(char, gamedata, cid), party.max_hp(char, gamedata, cid)
    state = "負傷待療" if party.is_downed(char, gamedata, cid) else f"{cur}/{mx}"
    return f"{name}（{state}·{party.bond_name(char, cid)})"


def _summon_named_companion(state: GameState, gamedata: GameData) -> None:
    """召集一名待命同伴歸隊:招募任務具名同伴 + 領主待命侍從(pending)。免費,受隊伍上限。"""
    char = state.player
    if len(char.companions) >= MAX_PARTY:
        ui.message(f"隊伍已滿(最多 {MAX_PARTY} 名),先解散一名再召集。", style="yellow")
        return
    avail = party.summonable(char, gamedata)
    opts = [(cid, f"{gamedata.companions[cid]['name']} —— {gamedata.companions[cid]['blurb']}")
            for cid in avail]
    cid = ui.menu("召集哪位同伴歸隊?", opts, allow_back=True)
    if cid is None:
        return
    char.companions.append(cid)
    if cid in char.pending_companions:            # 領主待命侍從 → 召集後移出待命池
        char.pending_companions.remove(cid)
    ui.message(f"{gamedata.companions[cid]['name']}應召歸隊,與你並肩同行。", style="bold green")


def _talk_companion(state: GameState, gamedata: GameData) -> None:
    """與一名在隊同伴交談:依羈絆階呈現對話;達羈絆門檻 → 可傾聽其心事(接取專屬支線)。"""
    char = state.player
    cid = ui.menu("與哪位同伴交談?",
                  [(c, gamedata.companions.get(c, {}).get("name", c)) for c in char.companions],
                  allow_back=True)
    if cid is None:
        return
    c = gamedata.companions.get(cid, {})
    nm = c.get("name", cid)
    tier = party.bond_tier(char, cid)
    lines = c.get("dialogue", [])
    line = lines[min(tier, len(lines) - 1)] if lines else c.get("blurb", "")
    ui.companion_talk(nm, line, party.bond_name(char, cid))
    if party.arc_done(char, gamedata, cid):
        cap = c.get("capstone", {})
        if cap.get("label"):
            ui.message(f"（忠誠弧已成 · {cap['label']}:{cap.get('desc', '')}）", style="cyan")
        return
    if party.arc_offerable(char, gamedata, cid):
        qid = party.personal_quest_id(gamedata, cid)
        pick = ui.menu(f"{nm}的神情似有未了的心事 —— 願意傾聽嗎?",
                       [("listen", "傾聽他的心事")], allow_back=True)
        if pick == "listen" and qid:
            _accept_and_brief(state, gamedata, qid)


def action_party(state: GameState, gamedata: GameData) -> None:
    """隊伍管理:檢視同伴 HP/羈絆/負傷、與同伴交談(專屬支線)、召集待命具名同伴、就地解散(不限旅店)。"""
    char = state.player
    while True:
        summonable = party.summonable(char, gamedata)
        if not char.companions and not summonable:
            ui.message("你目前沒有同伴。(旅店可雇用傭兵;受封武士得侍從;營地可延攬將領)", style="grey70")
            return
        ui.party_panel(char, gamedata)
        opts = []
        if char.companions:
            opts.append(("talk", "與同伴交談"))
        if summonable and len(char.companions) < MAX_PARTY:
            opts.append(("summon", f"召集同伴歸隊({len(summonable)} 人待命)"))
        if char.companions:
            opts.append(("dismiss", "解散一名同伴"))
        choice = ui.menu("隊伍", opts, allow_back=True)
        if choice is None:
            return
        if choice == "talk":
            _talk_companion(state, gamedata)
        elif choice == "summon":
            _summon_named_companion(state, gamedata)
        elif choice == "dismiss":
            _dismiss_mercenary(state, gamedata)


_TRAINER_SPEC_LABEL = {"combat": "戰鬥", "magic": "魔法", "stealth": "潛行"}


def action_trainer(state: GameState, gamedata: GameData) -> None:
    char = state.player
    loc_id = char.location_id
    while True:                                       # 可連續訓練,返回才離開
        specs = world.trainer_specs(gamedata, loc_id)   # 此城訓練師有得教的系(已依公會/lore 專精)
        if not specs:                                   # 防禦:有 trainer 服務必能推導,理論上不為空
            ui.message("此地的訓練師沒什麼能指點你的。", style="grey70")
            return
        if len(specs) == 1:
            spec = specs[0]                             # 單系城直接列技能,免空選單
        else:
            spec = ui.menu("向訓練師學哪一類?",
                           [(sp, _TRAINER_SPEC_LABEL[sp]) for sp in specs], allow_back=True)
            if spec is None:
                return
        opts = []
        for sid in world.trainer_skills(gamedata, loc_id, spec):
            cost = world.train_cost(char.skill(sid))
            cap = world.trainer_cap(gamedata, loc_id, sid)
            label = f"{gamedata.skill_name(sid)} (Lv {char.skill(sid)}) — {cost} 金 +1"
            tags = []
            if cap > formulas.TRAINER_CAP:              # 招牌城宗師之技(可破一般上限)
                tags.append({"text": "宗師", "tone": "gold"})
            nxt = mastery.next_threshold(char, gamedata, sid)   # 顯示距下一個技能里程碑還幾級
            if nxt:
                tags.append({"text": f"距 {nxt['name']} 還 {nxt['remaining']} 級", "tone": "mag"})
            opts.append((sid, label, tags) if tags else (sid, label))
        sid = ui.menu("訓練哪項技能?", opts, allow_back=True)
        if sid is None:
            if len(specs) == 1:
                return                                  # 單系:技能選單即頂層,返回=離開
            continue
        cap = world.trainer_cap(gamedata, loc_id, sid)
        if char.skill(sid) >= cap:
            if cap < formulas.SKILL_CAP:
                ui.message("此城訓練師已傾囊相授;更高深處,須另尋宗師或親身歷練。", style="grey70")
            else:
                ui.message("此技能已臻化境,無需再學。", style="grey70")
            continue
        cost = world.train_cost(char.skill(sid))
        if char.gold < cost:
            ui.message("金幣不足。", style="red")
            continue
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


def _governing_ruler(state: GameState, gamedata: GameData, loc_id: str, base_ruler: dict):
    """佔領城的朝堂顯示(A3 自任領主/冊封總管):你即事實領主,或由冊封的總管代你坐鎮 ——
    取代被推翻的舊領主顯示(修補「領主沒變」)。回傳 (ruler_dict, reception)。"""
    char = state.player
    city = gamedata.location(loc_id)["name"]
    banner = politics.current_banner_label(char, gamedata, loc_id) or base_ruler.get("bloc_label")
    garrison = politics.garrison_of(char, gamedata, loc_id)
    sid = politics.steward_of(char, loc_id)
    if sid and sid in char.companions:                 # 冊封的總管代你坐鎮
        comp = gamedata.companions.get(sid, {})
        ruler = {"title": "總管", "name": comp.get("name", sid),
                 "race": comp.get("race", base_ruler["race"]),
                 "blurb": f"奉你之命坐鎮「{city}」,代你安民理政、彈壓不臣。",
                 "garrison": garrison, "bloc_label": banner}
        reception = "總管起身行禮:「主上,城中諸事安好,謹候吩咐。」"
    else:                                              # 你親自坐鎮(征服者即領主)
        ruler = {"title": "征服者", "name": char.name, "race": char.race,
                 "blurb": f"你以刀鋒奪下「{city}」,自此這城奉你的旗號、聽你號令。",
                 "garrison": garrison, "bloc_label": banner}
        reception = "你端坐於昔日領主的主位,廳中文武皆肅立候命。"
    return ruler, reception


def action_court(state: GameState, gamedata: GameData) -> str | None:
    """領主區:謁見 + 領主委託 + 受封武士 + 選邊/攻城(Phase 2+3+4)。回傳 'dead'(攻城陣亡)或 None。"""
    char = state.player
    loc_id = char.location_id
    ruler = gamedata.ruler_at(loc_id)
    if not ruler:
        ui.message("此地沒有領主可謁見。", style="grey70")
        return None
    while True:                                       # 可連續處理朝堂事務,返回才離開(攻城仍為終局)
        rel = politics.relationship(char, gamedata, loc_id)
        pol = {"stance": politics.stance_label(politics.faction_of(char, gamedata, loc_id)),
               "relation": politics.REL_LABEL.get(rel, rel),
               "garrison": politics.garrison_of(char, gamedata, loc_id)}
        held = loc_id in politics.held_tax_cities(char, gamedata)   # 你親手攻下的城 → 你即領主 + 領地經營
        territory = (politics.territory_overview(char, gamedata, loc_id, state.time.absolute_hours())
                     if held else None)
        if held:                                       # A3:朝堂顯示你/總管為領主(取代被推翻的舊領主)
            disp_ruler, reception = _governing_ruler(state, gamedata, loc_id, ruler)
        else:
            disp_ruler, reception = ruler, _court_reception(char)
        ui.court_panel(disp_ruler, gamedata, reception,
                       standing=court.standing(char, loc_id), thane=court.is_thane(char, loc_id),
                       politics=pol, territory=territory)
        opts = []
        offered = court.offered_ruler_quest(char, gamedata, loc_id)
        if rel != "enemy" and not held and offered:   # 敵城/自家領地不接領主委託
            opts.append(("quest", f"領取委託:{gamedata.quests[offered]['name']}"))
        if rel != "enemy" and court.can_become_thane(char, gamedata, loc_id):
            opts.append(("thane", "✦ 受封武士"))
        if held:                                       # A3 佔領治理:冊封/召回總管(緩叛亂、令城自給)
            sid = politics.steward_of(char, loc_id)
            if sid and sid in char.companions:
                opts.append(("recall_steward", f"召回總管({gamedata.companions.get(sid, {}).get('name', sid)})"))
            elif any(c not in set(char.stewards.values()) for c in char.companions):
                opts.append(("appoint_steward", "✦ 冊封總管 —— 派一名親衛坐鎮安民(緩叛亂、令城自給)"))
        if politics.can_reinforce(char, gamedata, loc_id):
            opts.append(("reinforce", f"加強駐軍({politics.REINFORCE_COST_PER} 金/兵 → 鎮民心、防叛亂)"))
        if not char.allegiance:
            opts.append(("pledge", "宣誓效忠 —— 選擇你的大義"))
        if politics.can_siege(char, gamedata, loc_id):
            opts.append(("siege", f"⚔ 發動攻城(守軍 {politics.garrison_of(char, gamedata, loc_id)})"))
        if not opts:
            return None                             # 純謁見:領主暫無吩咐
        prompt = "你坐鎮朝堂,有何決斷?" if held else "領主有何吩咐?"
        choice = ui.menu(prompt, opts, allow_back=True)
        if choice is None:
            return None
        if choice == "quest":
            _accept_and_brief(state, gamedata, offered)
        elif choice == "thane":
            _become_thane(state, gamedata, loc_id, ruler)
        elif choice == "appoint_steward":
            _appoint_steward(state, gamedata, loc_id)
        elif choice == "recall_steward":
            sid = politics.steward_of(char, loc_id)
            politics.recall_steward(char, loc_id)
            ui.message(f"你召回了總管{gamedata.companions.get(sid, {}).get('name', '')} —— "
                       f"該城重歸你親自坐鎮(叛亂流失回升)。", style="yellow")
        elif choice == "reinforce":
            _reinforce_garrison(state, gamedata, loc_id)
        elif choice == "pledge":
            _pledge_allegiance(state, gamedata)
        elif choice == "siege":
            return action_siege(state, gamedata, loc_id)


def _appoint_steward(state: GameState, gamedata: GameData, loc_id: str) -> None:
    """冊封一名親衛為該佔領城的總管(每名親衛只能坐鎮一城 → 須把親衛分派到各領地)。"""
    char = state.player
    busy = set(char.stewards.values())                 # 已派任他城的親衛不重複任用
    opts = [(cid, gamedata.companions.get(cid, {}).get("name", cid))
            for cid in char.companions if cid not in busy]
    if not opts:
        ui.message("你麾下沒有可委任的親衛(其餘皆已派任他城)。", style="grey70")
        return
    cid = ui.menu("冊封誰為總管坐鎮此城?", opts, allow_back=True)
    if cid is None:
        return
    politics.appoint_steward(char, loc_id, cid)
    name = gamedata.companions.get(cid, {}).get("name", cid)
    ui.message(f"你冊封 {name} 為「{gamedata.location(loc_id)['name']}」總管 —— "
               f"由其坐鎮安民,叛亂流失大減,城可自給。", style="green")


def _reinforce_garrison(state: GameState, gamedata: GameData, loc_id: str) -> None:
    """出資加強佔領城的駐軍(鎮壓民心浮動、抵銷叛亂流失)。"""
    char = state.player
    cur = politics.garrison_of(char, gamedata, loc_id)
    cap = politics.base_garrison(gamedata, loc_id)
    affordable = char.gold // politics.REINFORCE_COST_PER
    hi = min(cap - cur, affordable)
    ui.message(f"現存駐軍 {cur}/{cap};你有 {char.gold} 金(每兵 {politics.REINFORCE_COST_PER} 金,"
               f"最多可補 {hi} 兵)。", style="gold1")
    n = ui.ask_int("加強多少駐軍?", default=min(hi, politics.UNREST_DECAY), lo=0, hi=hi)
    got = politics.reinforce_garrison(char, gamedata, loc_id, n)
    if got:
        state.time.advance(2)
        ui.message(f"你出資招募 {got} 名守兵入駐,城防為之一振(駐軍 "
                   f"{politics.garrison_of(char, gamedata, loc_id)})。", style="green")
    else:
        ui.message("金幣不足,或駐軍已滿。", style="yellow")


def _pledge_allegiance(state: GameState, gamedata: GameData) -> None:
    char = state.player
    ui.message("大空位之世,紅寶石王座空懸 —— 你決意擁護哪一方大義?", style="white")
    _CAUSE_DESC = {
        "imperial": "復辟賽普汀帝國,重整長老會與軍團的秩序。",
        "independent": "支持各省自治,讓地方掙脫帝國的羈縻。",
        "own": "不奉帝國、不附獨立 —— 以己之名舉旗,問鼎這片無主之地。",
    }
    opts = [(c, f"{politics.cause_name(c)} —— {_CAUSE_DESC.get(c, '')}")
            for c in politics.pledgeable_causes(char)]
    cause = ui.menu("宣誓效忠", opts, allow_back=True)
    if cause is None:
        return
    politics.pledge(char, cause)
    if cause == "own":
        ui.message("你舉起自己的旗幟 —— 自此天下皆敵、寸土皆需親取,問鼎之路由你的刀鋒開闢。",
                   style="bold gold1")
    else:
        ui.message(f"你宣誓擁護「{politics.cause_name(cause)}」。從此同道之城以你為友,"
                   f"對立之城則成你刀鋒所向。", style="bold gold1")


def action_siege(state: GameState, gamedata: GameData, loc_id: str) -> str | None:
    """圍攻敵城:混合制 —— 先施圍城方略(全套技能各有用)削弱守軍,再發動輕量化強攻。
    回傳 'dead'(強攻陣亡)或 None。"""
    char = state.player
    city = gamedata.location(loc_id)["name"]
    while True:
        remaining = politics.garrison_of(char, gamedata, loc_id)
        opts = []
        for op in politics.available_ops(char, gamedata, loc_id):
            est = politics.op_deplete_amount(char, op)
            cost = "、".join(f"{v}{ {'gold':'金','magicka':'魔','fatigue':'體'}[k] }"
                            for k, v in op["cost"].items()) or "免"
            tag = "" if politics.can_afford_op(char, op) else "(資源不足)"
            risk = "(有風險)" if op["risk"] else ""
            opts.append((op["id"], f"{op['name']}〔{gamedata.skill_name(op['skill'])}〕"
                                   f"耗 {op['hours']}時/{cost}{risk} → 削守軍約 {est}{tag}"))
        # 大軍壓境:以軍隊規模(非個人技能)削守軍 —— 招兵買馬的攻城路。每役一次。
        if char.soldiers > 0 and "army" not in politics.ops_done(char, loc_id):
            opts.append(("army", f"⚑ 大軍壓境〔軍隊 {char.soldiers}〕→ 削守軍約 {warband.army_soften(char)}"))
        opts.append(("assault", f"⚔ 發動強攻(現存守軍 {remaining})"))
        choice = ui.menu(f"圍攻「{city}」—— 守軍 {remaining}", opts, allow_back=True)
        if choice is None:
            return None
        if choice == "assault":
            return _siege_assault(state, gamedata, loc_id, city)
        if choice == "army":
            amount = warband.army_soften(char)
            politics.deplete_garrison(char, gamedata, loc_id, amount)
            char.siege_ops.setdefault(loc_id, []).append("army")
            state.time.advance(2)
            ui.message(f"你的大軍壓向城下,連日襲擾消磨 —— 守軍折損約 {amount}。", style="green")
            continue
        op = politics.SIEGE_OP_BY_ID[choice]
        if not politics.can_afford_op(char, op):
            ui.message("資源不足,難以施行此略。", style="red")
            continue
        r = politics.resolve_op(char, gamedata, loc_id, choice, state.rng)
        state.time.advance(op["hours"])
        if r["ok"]:
            ui.message(f"{op['desc']} 守軍折損約 {r['deplete']}。", style="green")
        else:
            ui.message("行動被守軍察覺,無功而返 —— 此略已不可再用。", style="yellow")


def _siege_assault(state: GameState, gamedata: GameData, loc_id: str, city: str) -> str | None:
    """波次總攻(β):守軍折算成數波,每波一場群戰、波間不恢復(消耗戰)、傷亡永久、可鳴金收兵。
    每破一波永久削 WAVE_GARRISON 守軍 → 中途退兵亦保留戰果。回傳 'dead'(陣亡)或 None。"""
    char = state.player
    remaining = politics.garrison_of(char, gamedata, loc_id)
    waves = politics.assault_waves(remaining)
    if not ui.confirm(f"向「{city}」發動總攻?守軍 {remaining} → 須連破 {waves} 波("
                      f"波間不得休整、傷亡永久,倒下即死)。決意一戰?"):
        return None
    ui.message(f"號角長鳴,你率眾撞開{city}的城門 ——", style="bold magenta")
    for wave in range(1, waves + 1):
        last = wave == waves
        enemies = [combat.spawn_creature(gamedata, politics.SIEGE_SOLDIER, state.rng)
                   for _ in range(politics.WAVE_GUARDS)]
        if last:                                       # 末波:守將親自壓陣
            enemies.append(combat.spawn_boss(gamedata, politics.SIEGE_SOLDIER, state.rng, name=f"{city}守將"))
        # 親衛 + 麾下士兵每波重新上陣(以當前名冊計;陣亡者已折損 → 兵力遞減=消耗戰)
        fielded = warband.fielded_soldiers(char)
        allies = char.companions + [warband.SOLDIER_TROOP] * fielded
        cur = politics.garrison_of(char, gamedata, loc_id)
        ui.message(f"⚔ 第 {wave}/{waves} 波 —— "
                   + ("守將親自壓陣,這是最後一搏!" if last else f"守軍湧上城頭(殘存 {cur})。"),
                   style="bold magenta" if last else "yellow")
        # 攻城的盟友永久折損:run_battle 回報陣亡者 → 名冊扣減(階段二「戰爭的代價」)
        fallen: list = []
        res = run_battle(state, gamedata, enemies, companions=allies, casualties=fallen)
        if res == "dead":
            return "dead"
        loss = warband.apply_casualties(char, gamedata, fallen)
        if loss["officers"] or loss["soldiers"]:
            parts = list(loss["officers"]) + ([f"{loss['soldiers']} 名士兵"] if loss["soldiers"] else [])
            ui.message(f"此波折損:{'、'.join(parts)} —— 戰死城下者,長眠不歸。", style="red")
        politics.deplete_garrison(char, gamedata, loc_id, politics.WAVE_GARRISON)   # 破一波 → 守軍永久折損
        if res == "fled":
            ui.message("你且戰且退 —— 城未下,但已破的城防仍在,改日可再攻。", style="yellow")
            return None
        if not last and not ui.confirm(
                f"第 {wave} 波已破(尚餘 {waves - wave} 波)。傷勢、體力、魔力皆不予恢復 —— 繼續總攻?"):
            ui.message("你暫且鳴金收兵 —— 已破的城防仍在,養精蓄銳後可再戰。", style="yellow")
            return None
    politics.conquer(char, gamedata, loc_id, now=state.time.absolute_hours())
    char.fame += politics.SIEGE_FAME
    ui.message(f"城門洞開,守將伏誅 —— 「{city}」易幟,自此歸於{politics.cause_name(char.allegiance)}!",
               style="bold gold1")
    ui.message(f"你的威名響徹四方(聲望 +{politics.SIEGE_FAME})。", style="cyan")


def action_warband(state: GameState, gamedata: GameData) -> None:
    """整軍經武:建立/移動營地、招募士兵、檢視軍勢(招兵買馬階段一)。"""
    char = state.player
    while True:
        loc_id = char.location_id
        camp_name = gamedata.location(char.camp)["name"] if char.camp else "未建立"
        _stationed = set(char.stewards.values())   # 坐鎮總管已離隊治理,不計入軍勢親衛
        officers = "、".join(gamedata.companions[c]["name"]
                            for c in char.companions if c not in _stationed) or "無"
        ui.message(f"【軍勢】親衛:{officers} | 士兵:{char.soldiers}/{warband.MAX_SOLDIERS} | "
                   f"營地:{camp_name}", style="gold1")
        opts = []
        if warband.can_make_camp(char, gamedata, loc_id):
            opts.append(("camp", "移營至此" if char.camp else "在此建立營地(野外/已肅清地城)"))
        if warband.has_camp(char):
            opts.append(("recruit", f"招募士兵({warband.SOLDIER_COST} 金/名)"))
            if warband.recruitable_officers(char, gamedata):
                opts.append(("officer", "招募親衛將領(領袖專屬)"))
        if not opts:
            if not warband.is_warlord(char, gamedata):
                ui.message("唯有領主(武士 / 征服城)或公會掌門方能招兵買馬。", style="grey70")
            else:
                ui.message("此地無法紮營 —— 需在野外或已肅清的地城建立營地。", style="grey70")
            return
        choice = ui.menu("整軍經武 ⚑", opts, allow_back=True)
        if choice is None:
            return
        if choice == "camp":
            warband.make_camp(char, loc_id)
            ui.message(f"你在{gamedata.location(loc_id)['name']}立起營地,旌旗招展。", style="green")
        elif choice == "recruit":
            n = ui.ask_int("招募幾名士兵?", default=1, lo=0, hi=warband.MAX_SOLDIERS)
            got = warband.recruit_soldiers(char, n)
            if got:
                ui.message(f"{got} 名士兵入伍,你的軍隊更壯大了(共 {char.soldiers} 名)。", style="green")
            else:
                ui.message("金幣不足,或軍隊已達上限。", style="yellow")
        elif choice == "officer":
            if len(char.companions) >= MAX_PARTY:
                ui.message(f"親衛已滿(最多 {MAX_PARTY} 名),先解散一名吧。", style="yellow")
                continue
            pool = warband.recruitable_officers(char, gamedata)
            oopts = [(cid, f"{gamedata.companions[cid]['name']} — "
                      f"{warband.officer_cost(gamedata, cid)} 金:{gamedata.companions[cid]['blurb']}")
                     for cid in pool]
            cid = ui.menu(f"招募哪位將領?(你有 {char.gold} 金)", oopts, allow_back=True)
            if cid is None:
                continue
            cost = warband.officer_cost(gamedata, cid)
            if char.gold < cost:
                ui.message("金幣不足。", style="red")
                continue
            char.gold -= cost
            char.companions.append(cid)
            ui.message(f"{gamedata.companions[cid]['name']}受你延攬,從此為你執掌一軍。", style="bold green")
    return None


def action_territory(state: GameState, gamedata: GameData) -> None:
    """領地總覽(城戰階段四):一覽所有親手攻下的城,並可就地遠程加強任一城駐軍。"""
    char = state.player
    while True:
        cities = politics.held_tax_cities(char, gamedata)   # 🔴 紅線:只認攻下的城,絕不可 held_cities
        if not cities:
            ui.message("你目前沒有親手攻下的領地。", style="grey70")
            return
        now = state.time.absolute_hours()
        rows = [politics.territory_overview(char, gamedata, loc, now) for loc in cities]
        ui.territory_panel(rows, gamedata, char.gold)
        opts = [(loc, f"加強駐軍:{gamedata.location(loc)['name']}")
                for loc in cities if politics.can_reinforce(char, gamedata, loc)]
        if not opts:
            ui.message("各城駐軍皆已滿,或金幣不足以增兵。", style="grey70")
            return
        choice = ui.menu("領地總覽 🏰 —— 加強哪座城的駐軍?", opts, allow_back=True)
        if choice is None:
            return
        _reinforce_garrison(state, gamedata, choice)        # 複用逐城回防(含時間推進/訊息)


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
        else:                                          # 隊伍已滿 → 侍從於領地待命,可日後召集(不丟棄)
            if hc not in char.pending_companions:
                char.pending_companions.append(hc)
            ui.message(f"領主賜下侍從 {gamedata.companions[hc]['name']},但你隊伍已滿 —— "
                       f"他在領地待命,隊伍有空位時可於「隊伍」選單召集他歸隊。", style="green")
    ui.message(f"自此{gamedata.location(loc_id)['province']}的衛兵,對你的小過睜隻眼閉隻眼。",
               style="grey70")


# ======================================================================
# 魔法與製作:施法 / 法師公會 / 煉金 / 附魔 / 修理
# ======================================================================
def action_cast_self(state: GameState, gamedata: GameData, battle: dict | None = None) -> None:
    """戰鬥外施法:治療、回體力等自我增益(練功也行)。

    battle 非 None(地城戰鬥情境):放寬為「所有 self-target、非 reanimate」法術 —— 含召喚與
    各式自我增益(預施/預召喚);召喚物加入 battle["allies"]。battle 為 None(城鎮):僅 heal/restore。"""
    char = state.player
    if battle is not None:   # 地城戰鬥情境:可預施增益 + 預召喚(reanimate 需屍體 → 地城無,排除)
        usable = [s for s in char.spells
                  if gamedata.spells[s]["target"] == "self"
                  and gamedata.spells[s]["effect"]["kind"] != "reanimate"]
    else:
        usable = [s for s in char.spells
                  if gamedata.spells[s]["target"] == "self"
                  and gamedata.spells[s]["effect"]["kind"] in ("heal", "restore_fatigue")]
    if not usable:
        ui.message("你沒有可施放的法術。", style="grey70")
        return
    opts = [(s, f"{gamedata.spells[s]['name']}（{magic.effective_cost(char, gamedata, s)} 魔力)"
             f" · {ui.spell_effect_summary(gamedata, s)}") for s in usable]
    sid = ui.menu(f"施放哪道法術?(魔力 {int(char.magicka)}/{char.max_magicka})", opts, allow_back=True)
    if sid is None:
        return
    if not magic.can_cast(char, gamedata, sid):
        ui.message("魔力不足。", style="red")
        return
    res = magic.cast(char, gamedata, sid, state.rng, battle=battle)
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
    while True:                                       # 可連續學多道法術,返回才離開
        for_sale = [s for s in loc.get("spell_stock", []) if s not in char.spells]
        if not for_sale:
            ui.message("公會裡沒有你還沒學會的法術了。", style="grey70")
            return
        disc = factions.spell_discount(char, gamedata)   # 法師公會階級折扣

        def _sp(s):
            return max(1, round(world.spell_price(gamedata, s) * (1 - disc)))
        label = f"學習法術(你有 {char.gold} 金"
        label += f",會員 -{int(disc*100)}%)" if disc else ")"
        opts = [(s, f"{gamedata.spells[s]['name']}（{ui.school_name(gamedata.spells[s]['school'])}) — {_sp(s)} 金"
                 f" · {ui.spell_effect_summary(gamedata, s)}") for s in for_sale]
        sid = ui.menu(label, opts, allow_back=True)
        if sid is None:
            return
        price = _sp(sid)
        if char.gold < price:
            ui.message("金幣不足。", style="red")
            continue
        char.gold -= price
        char.spells.append(sid)
        ui.message(f"你習得了{gamedata.spells[sid]['name']}!", style="bold green")


def action_alchemy(state: GameState, gamedata: GameData) -> None:
    char = state.player
    while True:                                       # 可連續煉製/嚐試,返回才離開
        ings = [s["id"] for s in char.inventory if gamedata.item(s["id"]).get("kind") == "ingredient"]
        if not ings:
            ui.message("你沒有任何煉金材料。", style="grey70")
            return

        # R32:憑煉金學識被動辨識(開選單即觸發,idempotent)→ 報新揭露
        newly = [(iid, k) for iid in ings for k in alchemy.passive_reveal(char, gamedata, iid)]
        if newly:
            ui.message("憑著煉金學識,你一眼看出了:" +
                       "、".join(f"{gamedata.item_name(i)}的{_EFFECT_CN.get(k, k)}" for i, k in newly),
                       style="cyan")

        def _effect_label(iid):
            parts = []
            for e in alchemy.ingredient_effects(gamedata, iid):
                if alchemy.is_known(char, iid, e["kind"]):
                    parts.append(f"{_EFFECT_CN.get(e['kind'], e['kind'])}{e['magnitude']}")
                else:
                    parts.append("???")           # R32:未揭露的效果隱藏
            return "、".join(parts)

        def _ing_opts(exclude=None):
            return [(iid, f"{gamedata.item_name(iid)} ×{inventory.count_item(char, iid)}（{_effect_label(iid)})")
                    for iid in ings if iid != exclude]

        has_taste = any(alchemy.undiscovered_kinds(char, gamedata, iid) for iid in ings)
        if len(ings) < 2 and not has_taste:
            ui.message("材料不足調配,也沒有可再試出的效果(調配需兩種不同材料)。", style="grey70")
            return

        mode = "brew"
        if has_taste:                                  # 有未知效果 → 提供「嚐一口」分支
            mode = ui.menu("煉金台", [("brew", "調配藥水/毒藥"),
                                      ("taste", "嚐一口材料(試出效果)")], allow_back=True)
            if mode is None:
                return

        if mode == "taste":
            # 只列「仍有未知效果」的材料(全已知者不該被當嚐試目標 → 避免白白吃掉)
            taste_opts = [o for o in _ing_opts() if alchemy.undiscovered_kinds(char, gamedata, o[0])]
            tid = ui.menu("嚐哪種材料?", taste_opts, allow_back=True)
            if tid is None:
                continue
            r = alchemy.taste(char, gamedata, tid)
            if r["ok"]:                                   # 確有揭露才付體力/時間(no-op 不消耗、不收成本)
                char.fatigue = max(0, char.fatigue - alchemy.TASTE_FATIGUE)
                state.time.advance(1)
            ui.message(r["message"], style="green" if r["revealed"] else "grey70")
            if r["revealed"]:
                ui.message(f"你記住了:{gamedata.item_name(tid)} → {_EFFECT_CN.get(r['revealed'], r['revealed'])}。",
                           style="bold cyan")
            continue

        if len(ings) < 2:
            ui.message("調配至少需要兩種不同材料。", style="grey70")
            continue                                   # has_taste 必為真(否則上方已 return)→ 回模式選單
        a = ui.menu("選第一種材料", _ing_opts(), allow_back=True)
        if a is None:
            if has_taste:
                continue                               # 回模式選單
            return                                     # 無模式選單 → 直接離開
        b = ui.menu("選第二種材料", _ing_opts(exclude=a), allow_back=True)
        if b is None:
            continue
        res = alchemy.brew(char, gamedata, a, b, state.rng)
        state.time.advance(res["hours"])
        ui.message(res["message"], style="green" if res["ok"] else "yellow")
        if res["tired"]:
            ui.message("體力不濟,煉製時心不在焉,成效減半。", style="yellow")
        # R32:套用本次煉製揭露的共有效果 → 報新學會
        learned = []
        for iid, kinds in res.get("learn", {}).items():
            for k in kinds:
                if alchemy.reveal(char, gamedata, iid, k):
                    learned.append(f"{gamedata.item_name(iid)}→{_EFFECT_CN.get(k, k)}")
        if learned:
            ui.message("這鍋讓你看清了材料的本性:" + "、".join(learned), style="bold cyan")
        ui.show_events(res["skill_events"], gamedata)


def action_enchant(state: GameState, gamedata: GameData) -> None:
    char = state.player
    while True:                                       # 可連續附魔,任一選單返回即離開
        gems = enchanting.filled_soul_gems(char, gamedata)
        if not gems:
            ui.message("你沒有充能的靈魂石(用『擒魂術』擊殺敵人可獲得)。", style="grey70")
            return
        weapons = enchanting.enchantable_weapons(char, gamedata)
        armors = enchanting.enchantable_armor(char, gamedata)
        jewels = enchanting.enchantable_jewelry(char, gamedata)

        kinds = []
        if weapons:
            kinds.append(("weapon", "武器(元素 / DoT / 吸取 / 命中觸發)"))
        if armors:
            kinds.append(("armor", "護甲(強化資源 / 技能 / 抗性)"))
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
            fam = ui.menu("附魔效果?", [
                ("element", "元素傷害(即時)"),
                ("dot", "元素持續(DoT + 異常)"),
                ("absorb", "命中吸取(生命 / 魔力 / 體力)"),
                ("trigger", "命中觸發(吸血 / 再生 / 麻痺 · 擒魂 · 充能)"),
            ], allow_back=True)
            if fam is None:
                return
            if fam == "element":
                elem = ui.menu("附上哪種元素?", [("fire", "烈焰"), ("frost", "冰霜"), ("shock", "雷電")],
                               allow_back=True)
                if elem is None:
                    return
                res = enchanting.enchant_weapon(char, gamedata, wid, elem, gem)
            else:
                st = ui.menu("選擇效果?",
                             {"dot": enchanting.WEAPON_DOT_KINDS, "absorb": enchanting.WEAPON_ABSORB_KINDS,
                              "trigger": enchanting.WEAPON_TRIGGER_KINDS}[fam], allow_back=True)
                if st is None:
                    return
                res = enchanting.enchant_weapon_status(char, gamedata, wid, st, gem)
        elif kind == "armor":
            aid = ui.menu("為哪件護甲附魔?",
                          [(a, gamedata.item_name(a)) for a in armors], allow_back=True)
            if aid is None:
                return
            akind = ui.menu("附魔型別?", enchanting.ARMOR_KINDS, allow_back=True)
            if akind is None:
                return
            if akind == "thorns":   # 荊棘無 param(純反傷%,靈魂石階決定)
                aparam = ""
            else:
                if akind == "skill":
                    aparam_opts = [(sid, gamedata.skill_name(sid)) for sid in gamedata.skills]
                elif akind == "resist":
                    aparam_opts = [("fire", "烈焰"), ("frost", "冰霜"), ("shock", "雷電"),
                                   ("poison", "毒素"), ("magic", "魔法")]
                else:  # res
                    aparam_opts = [("health", "生命"), ("magicka", "魔力"), ("fatigue", "體力")]
                aparam = ui.menu("強化哪一項?", aparam_opts, allow_back=True)
                if aparam is None:
                    return
            res = enchanting.enchant_armor(char, gamedata, aid, akind, aparam, gem)
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


def action_craft(state: GameState, gamedata: GameData) -> None:
    """製革/加工:把獸皮等原料依配方做成裝備(需鐵匠/製革處)。
    兩層選單:第一層選材質系列,點進去後才列該系列要做的裝備。"""
    char = state.player
    loc = world.current_location(char, gamedata)
    station = "smith" if "armorer" in loc.get("services", []) else None
    groups = crafting.recipes_by_material(gamedata, station)
    if not groups:
        ui.message("這裡沒有可用的工坊。", style="grey70")
        return
    while True:                                       # 第一層:選材質系列
        mat_opts = []
        for mat, rids in groups:
            name = crafting.MATERIAL_SERIES_NAME.get(mat, mat)
            craftable = sum(1 for rid in rids
                            if crafting.meets_skill_req(char, gamedata, rid)
                            and crafting.can_craft(char, gamedata, rid))
            tag = f"(可做 {craftable}/{len(rids)})" if craftable else f"(共 {len(rids)} 件)"
            mat_opts.append((mat, f"{name} {tag}"))
        mat = ui.menu("鍛造哪個材質系列?", mat_opts, allow_back=True)
        if mat is None:
            return
        rids = next(r for m, r in groups if m == mat)
        _craft_series(state, gamedata, mat, rids)


def _craft_series(state: GameState, gamedata: GameData, mat: str, rids: list) -> None:
    """鍛造選單第二層:在選定材質系列下挑要做的裝備(可連續製作,返回才回上層)。"""
    char = state.player
    name = crafting.MATERIAL_SERIES_NAME.get(mat, mat)
    while True:
        opts = []
        for rid in rids:
            r = gamedata.recipes[rid]
            inp = "、".join(f"{gamedata.item_name(i)}×{n}" for i, n in r["inputs"].items())
            if not crafting.meets_skill_req(char, gamedata, rid):
                tag = f"(需鍛造 {r.get('skill_req', 0)} 級)"
            elif not crafting.can_craft(char, gamedata, rid):
                tag = "(材料不足)"
            else:
                tag = ""
            opts.append((rid, f"{r['name']}:{inp} → {gamedata.item_name(r['output'])}{tag}"))
        rid = ui.menu(f"鍛造{name}系列 — 做什麼?", opts, allow_back=True)
        if rid is None:
            return
        res = crafting.craft(char, gamedata, rid)
        state.time.advance(res["hours"])
        ui.message(res["message"], style="green" if res["ok"] else "red")
        if res["tired"]:
            ui.message("體力不濟,做工馬虎。", style="yellow")
        ui.show_events(res["skill_events"], gamedata)


def action_temper(state: GameState, gamedata: GameData) -> None:
    """淬鍊強化:在鐵匠處消耗對應材質的錠,把手持武器/穿戴護甲永久淬鍊一級(練鍛造)。"""
    char = state.player
    loc = world.current_location(char, gamedata)
    if "armorer" not in loc.get("services", []):
        ui.message("這裡沒有鐵匠的鐵砧。", style="grey70")
        return
    while True:                                       # 可連續淬鍊,返回才離開
        cap = smithing.effective_temper_cap(char, gamedata)
        ids = []
        if char.weapon != "fists":
            ids.append(char.weapon)
        for slot in ("helmet", "cuirass", "gauntlets", "boots", "shield"):
            iid = char.equipped.get(slot)
            if iid:
                ids.append(iid)
        ids = [i for i in dict.fromkeys(ids) if smithing.is_temperable(gamedata, i)]
        if not ids:
            ui.message("沒有可淬鍊的裝備(手持武器或穿戴護甲須為可鍛材質:鐵/鋼/精靈/矮人/玻璃/黑檀/皮/布;飾品與法杖不可淬)。", style="grey70")
            return
        opts = []
        for iid in ids:
            lvl = smithing.current_temper(char, gamedata, iid)
            ingot = smithing.required_ingot(gamedata, iid)
            have = inventory.count_item(char, ingot)
            ok, _ = smithing.can_temper(char, gamedata, iid)
            opts.append((iid, f"{gamedata.item_name(iid)} +{lvl}/{cap}　需 {gamedata.item_name(ingot)}(有 {have}){'' if ok else ' ✗'}"))
        iid = ui.menu(f"淬鍊強化哪件?(鍛造 {char.skill('smithing')} 級 → 上限 +{cap})", opts, allow_back=True)
        if iid is None:
            return
        res = smithing.temper(char, gamedata, iid, state.rng)
        state.time.advance(res["hours"])
        ui.message(res["message"], style="green" if res["ok"] else "red")
        if res.get("tired"):
            ui.message("體力不濟,鍛打得馬虎。", style="yellow")
        ui.show_events(res["skill_events"], gamedata)


def action_meltdown(state: GameState, gamedata: GameData) -> None:
    """回爐熔解:把背包裡不需要的武器/護甲熔回部分材料(有損耗),同時練鍛造(需鐵匠鐵砧)。"""
    char = state.player
    loc = world.current_location(char, gamedata)
    if "armorer" not in loc.get("services", []):
        ui.message("這裡沒有鐵匠的鐵砧。", style="grey70")
        return
    while True:                                       # 可連續回爐,返回才離開
        opts = []
        for s in char.inventory:
            iid = s["id"]
            if not smithing.meltable(gamedata, iid):
                continue
            spare = s["qty"] - smithing.worn_count(char, iid)   # 只熔多餘份(穿戴/手持中的受保護)
            if spare <= 0:
                continue
            ingot, qty = smithing.meltdown_yield(gamedata, iid)
            held = f"可熔 {spare}/{s['qty']}" if spare < s["qty"] else f"可熔 {spare}"
            opts.append((iid, f"{gamedata.item_name(iid)}({held}) → 每件 {gamedata.item_name(ingot)} ×{qty}"))
        if not opts:
            ui.message("背包裡沒有可回爐的多餘武器/護甲(穿戴/手持中的份受保護,無多餘者請先卸下;"
                       "法杖·弓·飾品·附魔神器·龍鱗裝、及熔之無得的廉價單品不可回爐)。", style="grey70")
            return
        iid = ui.menu(f"回爐哪件?(熔解有損耗,煉回部分材料並練鍛造 {char.skill('smithing')} 級)",
                      opts, allow_back=True)
        if iid is None:
            return
        res = smithing.meltdown(char, gamedata, iid)
        state.time.advance(res["hours"])
        ui.message(res["message"], style="green" if res["ok"] else "red")
        if res.get("tired"):
            ui.message("體力不濟,熔煉得馬虎。", style="yellow")
        ui.show_events(res["skill_events"], gamedata)


_EFFECT_CN = {"heal": "回血", "restore_magicka": "回魔", "restore_fatigue": "回體",
              "damage_health": "毒傷", "paralyze": "麻痺",
              # 限時增益(R30):強化屬性/技能/抗元素(參數內嵌的 kind)
              "fattr_willpower": "強意志", "fattr_agility": "強敏捷",
              "fskill_alchemy": "精煉金", "resist_magic": "抗魔法",
              # 毒劑深化(R31):特殊有害效果
              "damage_strength": "弱攻", "slow": "遲緩", "fear": "懼意",
              # 疾病可釀(R54):療疾類
              "cure_disease": "療疾"}


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


def action_recharge_enchant(state: GameState, gamedata: GameData) -> None:
    """以靈魂石為「充能型」附魔武器(命中擒魂 / 麻痺)回充使用次數。"""
    char = state.player
    chargeable = enchanting.chargeable_weapons(char, gamedata)
    if not chargeable:
        ui.message("沒有可充能的附魔武器(命中擒魂 / 麻痺)。", style="grey70")
        return
    gems = enchanting.filled_soul_gems(char, gamedata)
    if not gems:
        ui.message("你沒有充能的靈魂石可灌注(用『擒魂術』擊殺取得)。", style="grey70")
        return

    def _cap(iid):
        return enchanting.charge_capacity(gamedata, iid)
    wid = ui.menu("為哪把附魔武器充能?",
                  [(iid, f"{gamedata.item_name(iid)}(充能 {char.enchant_charges.get(iid, _cap(iid))}/{_cap(iid)})")
                   for iid in chargeable], allow_back=True)
    if wid is None:
        return
    cap = _cap(wid)
    if char.enchant_charges.get(wid, cap) >= cap:
        ui.message("此武器充能已滿。", style="grey70")
        return
    gem = ui.menu("用哪顆靈魂石灌注?",
                  [(g, f"{gamedata.item_name(g)}(靈魂 {gamedata.item(g)['soul']} → +"
                       f"{gamedata.item(g)['soul'] * formulas.CHARGE_PER_SOUL} 充能)") for g in gems],
                  allow_back=True)
    if gem is None:
        return
    gain = gamedata.item(gem)["soul"] * formulas.CHARGE_PER_SOUL
    inventory.remove_item(char, gem, 1)
    char.enchant_charges[wid] = min(cap, char.enchant_charges.get(wid, cap) + gain)
    ui.message(f"靈魂石碎裂,{gamedata.item_name(wid)} 重獲鋒芒(充能 {char.enchant_charges[wid]}/{cap})。",
               style="bold green")


# ======================================================================
# 公會、任務、犯罪、對話
# ======================================================================
def action_guild_hall(state: GameState, gamedata: GameData, faction_id: str) -> None:
    char = state.player
    f = gamedata.factions[faction_id]
    while True:                                      # 留在公會可連續處理(入會→接任務),返回才離開
        ui.guild_panel(char, gamedata, faction_id)
        opts = []
        # 戰友團內圈的祕密:晉內圈戰友(非吸血鬼、未狼人化)會被獻上獸血儀式
        ritual_ok = (faction_id == "companions" and lycanthropy.can_offer_ritual(char))
        # 內圈戰友可召集尚未入隊的盾袍兄弟(免費,受隊伍上限)
        circle_recruit_ok = (faction_id == "companions"
                             and factions.rank_index(char, "companions") >= COMPANIONS_CIRCLE_RANK
                             and bool(_available_shield_siblings(char, gamedata))
                             and len(char.companions) < MAX_PARTY)
        # R-smuggle:盜賊公會高階(只在艾爾斯維爾分舵=月糖源)解鎖斯庫瑪走私生意(精煉 + 走私委託)
        smuggle_ok = (faction_id == "thieves_guild"
                      and world.current_location(char, gamedata).get("province") == SMUGGLE_PROVINCE
                      and factions.rank_index(char, "thieves_guild") >= SMUGGLE_RANK_1)
        # R89:戰士公會軍械庫淬鍊(公會供料·免材料)/ 法師公會奧術服務(回充 + 魔力補給)
        forge_ok = (faction_id == "fighters_guild"
                    and factions.rank_index(char, "fighters_guild") >= FORGE_RANK)
        arcane_ok = (faction_id == "mages_guild"
                     and factions.rank_index(char, "mages_guild") >= ARCANE_RECHARGE_RANK)
        # R99:犯罪公會高階(此處唯盜賊;黑兄/神話黎明各走自有大廳)解鎖反間委託榜
        cint_ok = (factions.is_criminal_guild(faction_id)
                   and factions.rank_index(char, faction_id) >= CINT_RANK)
        if not factions.is_member(char, faction_id):
            reason = factions.join_block_reason(char, gamedata, faction_id)
            if reason is not None:                   # 門檻/對立/通緝 → 說明原因
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
                if not ritual_ok and not circle_recruit_ok and not smuggle_ok \
                        and not forge_ok and not arcane_ok and not cint_ok:   # 無委託且無任何階級服務 → 離開
                    return
        if ritual_ok:
            opts.append(("beast_ritual", "🐺 獸血儀式（內圈戰友的祕密)"))
        if circle_recruit_ok:
            opts.append(("rally_sibling", "🛡 召集盾袍兄弟（免費 · 受隊伍上限)"))
        if smuggle_ok:
            opts.append(("smuggle", "🌙 斯庫瑪走私生意"))
        if forge_ok:
            opts.append(("forge", "⚒ 軍械庫淬鍊（公會供料 · 免材料)"))
        if arcane_ok:
            opts.append(("arcane_svc", "✨ 奧術服務（回充 / 魔力補給)"))
        if cint_ok:
            opts.append(("counterintel", "🕵 反間委託榜（獵敵方諜員)"))
        choice = ui.menu("公會事務", opts, allow_back=True)
        if choice is None:
            return
        if choice == "join":
            factions.join(char, faction_id)
            ui.message(f"你加入了{f['name']},現為「{factions.rank_name(char, gamedata, faction_id)}」。",
                       style="bold green")
        elif choice == "accept":
            avail = quests.available_quests(char, gamedata, "guild", faction_id)
            _accept_and_brief(state, gamedata, avail[0])
        elif choice == "beast_ritual":
            _beast_blood_ritual(state, gamedata)
        elif choice == "rally_sibling":
            _rally_shield_sibling(state, gamedata)
        elif choice == "smuggle":
            _skooma_smuggling(state, gamedata)
        elif choice == "forge":
            _guild_armory_temper(state, gamedata)
        elif choice == "arcane_svc":
            _arcane_services(state, gamedata)
        elif choice == "counterintel":
            _counterintel_board(state, gamedata)


def _beast_blood_ritual(state: GameState, gamedata: GameData) -> None:
    """戰友團獸血儀式:飲下戰友的獸血,成為狼人(內圈祕密)。"""
    char = state.player
    ui.message("圈內的戰友引你至地底密室,一只盛著漆黑獸血的石碗在火光中泛著腥光:"
               "「飲下它,你便與我等同族 —— 月之裔,獸之兄弟。」", style="white")
    if not ui.confirm("飲下獸血,接受狼人之軀嗎?(可日後尋獵巫女巫解咒)"):
        return
    if lycanthropy.contract(char, state, gamedata):
        ui.rule("獸血之契")
        ui.message("熾熱的獸血灼過喉嚨、沉入骨髓 —— 你聽見了血脈深處野獸的低吼。"
                   "戰鬥中,你已能化身嗜血巨狼。", style="bold red")
    else:
        ui.message("某種力量排斥著這份契約 —— 你無法接受獸血。", style="yellow")


def _skooma_smuggling(state: GameState, gamedata: GameData) -> None:
    """R-smuggle:盜賊公會高階解鎖的斯庫瑪走私生意 —— 精煉月糖→斯庫瑪 + 跨省走私委託。
    只在艾爾斯維爾分舵(月糖源)、thieves rank≥SMUGGLE_RANK_1 可達(由 action_guild_hall 閘)。
    精煉刻意是嚴格 sink(見 alchemy 反套利不等式),利潤走固定報酬走私委託。"""
    char = state.player
    while True:
        ms = inventory.count_item(char, "moon_sugar")
        opts = [("refine", f"🌙 精煉斯庫瑪(月糖 ×{alchemy.SKOOMA_REFINE_COST} → 斯庫瑪 ×1;你有月糖 ×{ms})"),
                ("contracts", "📦 走私委託(運月糖出省 · 固定酬勞 · 惡名加身)")]
        choice = ui.menu("斯庫瑪走私生意", opts, allow_back=True)
        if choice is None:
            return
        if choice == "refine":
            res = alchemy.refine_skooma(char, gamedata)
            if res["ok"]:
                state.time.advance(res["hours"])
            ui.message(res["message"], style="green" if res["ok"] else "grey70")
            if res.get("tired"):
                ui.message("熬煉時體力不濟,手腳發軟。", style="yellow")
            ui.show_events(res.get("skill_events", []), gamedata)
        elif choice == "contracts":
            _smuggling_contracts(state, gamedata)


def _smuggling_contracts(state: GameState, gamedata: GameData) -> None:
    """走私委託:列出艾爾斯維爾被脈動聚光、且達階級門檻的 scomm_* 委託(複用 R79 board+pulse·與正規告示板分流)。"""
    char = state.player
    rank = factions.rank_index(char, "thieves_guild")
    while True:
        today = worldpulse.day_index(state)
        avail = [q for q in quests.available_quests(char, gamedata, "board", province=SMUGGLE_PROVINCE, day=today)
                 if q.startswith("scomm_") and rank >= _SCOMM_MIN_RANK.get(q, SMUGGLE_RANK_1)]
        if not avail:
            ui.message("眼下沒有走私的單子 —— 月糖商隊的窗口未開,或你的地位還搆不上長程大宗的貨。"
                       "(走私委託隨『四方傳聞』的風向起落)", style="grey70")
            return
        opts = [(qid, f"{gamedata.quests[qid]['name']} — {quests.objective_text(char, gamedata, qid)}"
                 f"(賞 {gamedata.quests[qid]['reward'].get('gold', 0)} 金·惡名 +{gamedata.quests[qid]['reward'].get('infamy', 0)})")
                for qid in avail]
        qid = ui.menu("走私委託", opts, allow_back=True)
        if qid is None:
            return
        _accept_and_brief(state, gamedata, qid)


def _guild_armory_temper(state: GameState, gamedata: GameData) -> None:
    """R89 戰士公會軍械庫:公會供料**免材料**淬鍊手持武器/穿戴護甲(rank-gated 由 action_guild_hall 閘)。
    比照 action_temper 但不查 location armorer 服務(公會自有鐵砧)+ `guild_free=True`;仍受 `effective_temper_cap` 夾、耗時/體力。"""
    char = state.player
    while True:
        cap = smithing.effective_temper_cap(char, gamedata)
        ids = []
        if char.weapon != "fists":
            ids.append(char.weapon)
        for slot in ("helmet", "cuirass", "gauntlets", "boots", "shield"):
            iid = char.equipped.get(slot)
            if iid:
                ids.append(iid)
        ids = [i for i in dict.fromkeys(ids) if smithing.is_temperable(gamedata, i)]
        if not ids:
            ui.message("沒有可淬鍊的裝備(手持武器或穿戴護甲須為可鍛材質)。", style="grey70")
            return
        opts = []
        for iid in ids:
            lvl = smithing.current_temper(char, gamedata, iid)
            ok, _ = smithing.can_temper(char, gamedata, iid, guild_free=True)
            opts.append((iid, f"{gamedata.item_name(iid)} +{lvl}/{cap}{'' if ok else ' ✗(已達上限)'}"))
        iid = ui.menu(f"軍械庫淬鍊哪件?(公會供料免材料 · 鍛造 {char.skill('smithing')} 級 → 上限 +{cap})",
                      opts, allow_back=True)
        if iid is None:
            return
        res = smithing.temper(char, gamedata, iid, guild_free=True)
        if res["ok"]:
            state.time.advance(res["hours"])
        ui.message(res["message"], style="green" if res["ok"] else "grey70")
        if res.get("tired"):
            ui.message("體力不濟,鍛打得馬虎。", style="yellow")
        ui.show_events(res.get("skill_events", []), gamedata)


def _arcane_services(state: GameState, gamedata: GameData) -> None:
    """R89 法師公會奧術服務:免靈魂石回充充能型附魔武器(rank≥RECHARGE)+ 補給魔力藥水(rank≥SUPPLY)。"""
    char = state.player
    while True:
        rank = factions.rank_index(char, "mages_guild")
        opts = [("recharge", "✨ 奧術回充(免費充滿擒魂/麻痺附魔武器)")]
        if rank >= ARCANE_SUPPLY_RANK:
            have = inventory.count_item(char, "minor_magicka_potion")
            opts.append(("supply", f"🔮 魔力補給(補次級魔力藥水至 {MAGE_POTION_SUPPLY_N};你有 {have})"))
        choice = ui.menu("奧術服務", opts, allow_back=True)
        if choice is None:
            return
        if choice == "recharge":
            chargeable = enchanting.chargeable_weapons(char, gamedata)
            recharged = [iid for iid in chargeable if enchanting.recharge_full(char, gamedata, iid)]
            if recharged:
                ui.message("公會奧術師為你的附魔武器重新灌注魔力 —— "
                           + "、".join(gamedata.item_name(i) for i in recharged) + " 充能已滿。", style="bold green")
            elif chargeable:
                ui.message("你的充能型附魔武器都已是滿充能。", style="grey70")
            else:
                ui.message("你沒有充能型附魔武器(命中擒魂 / 麻痺)。", style="grey70")
        elif choice == "supply":
            got = 0
            while inventory.count_item(char, "minor_magicka_potion") < MAGE_POTION_SUPPLY_N:
                inventory.add_item(char, "minor_magicka_potion", 1)
                got += 1
            ui.message(f"公會替你備足了魔力藥水(次級魔力藥水 +{got},補至 {MAGE_POTION_SUPPLY_N} 瓶)。" if got
                       else "你的魔力藥水已滿。", style="green")


def action_board(state: GameState, gamedata: GameData) -> None:
    char = state.player
    province = world.current_location(char, gamedata)["province"]
    while True:                                       # 留在告示板可連續接多個委託,返回才離開
        # 主線(湮滅危機)在 kvatch_falls 後現於各地告示板;md7 教徒頂點受 requires_faction 閘只對教徒露出。
        # 常態世界脈動:board 傳 day → 可重複委託只在被 active 脈動聚光時現身(R-pulse)。
        # day 必用 worldpulse.day_index(開局後天數)= 與 world_pulse_day 同基準,否則 active 視窗永不命中。
        today = worldpulse.day_index(state)
        main = quests.available_quests(char, gamedata, "main")
        board = [q for q in quests.available_quests(char, gamedata, "board", province=province, day=today)
                 if not q.startswith(("ucomm_", "scomm_", "cint_"))]   # R84 地下委託(ucomm_)走藏身處;R-smuggle 走私委託(scomm_)走盜賊公會走私生意;R99 反間委託(cint_)走犯罪公會大廳 rank-gated:皆不上正規告示板
        avail = main + board
        if not avail:
            ui.message("告示板上沒有你還沒接的委託。", style="grey70")
            return
        opts = [(qid, f"{'【主線】' if gamedata.quests[qid].get('source') == 'main' else ''}"
                 f"{gamedata.quests[qid]['name']} — {quests.objective_text(char, gamedata, qid)}"
                 f"({'可重複·' if gamedata.quests[qid].get('repeatable') else ''}"
                 f"賞 {gamedata.quests[qid]['reward'].get('gold', 0)} 金)") for qid in avail]
        ui.board_panel(char, gamedata, avail)     # web:可點委託卡(對齊選單 key=qid)
        qid = ui.menu("告示板委託", opts, allow_back=True)
        if qid is None:
            return
        _accept_and_brief(state, gamedata, qid)


def action_shrine(state: GameState, gamedata: GameData) -> None:
    """戴德拉神殿:供奉祈願 → 接取該親王的試煉任務(R45)。

    任務 source="daedric"、帶 `shrine` 欄對應本地點的 `shrine`;requires_level/requires_fame
    門檻不達則親王沉默(任務不現)。複用既有 _accept_and_brief(含分支選路/簡報)。
    """
    char = state.player
    loc = world.current_location(char, gamedata)
    prince = loc.get("shrine")
    if not prince:
        return
    avail = [qid for qid in quests.available_quests(char, gamedata, "daedric")
             if gamedata.quests[qid].get("shrine") == prince]
    if not avail:
        ui.message("你在祭壇前俯首祈願,神殿一片寂靜 —— 此刻無人應你之聲。", style="grey70")
        return
    opts = [(qid, f"{gamedata.quests[qid]['name']} — {quests.objective_text(char, gamedata, qid)}")
            for qid in avail]
    qid = ui.menu("祭壇前的低語", opts, allow_back=True)
    if qid is None:
        return
    _accept_and_brief(state, gamedata, qid)


def action_arcane_trials(state: GameState, gamedata: GameData) -> None:
    """奧術試煉的在地引路人(R-arcane):毀滅 base≥75 → 該地點對應的元素試煉。

    比照 action_shrine:地點 `arcane_trials` 標籤(fire/frost/shock 分散各省法師城·fused 在帝都)
    配對任務 `arcane_site`,列可接者 → 複用 _accept_and_brief。門檻(requires_skill/level/quests)
    由 available_quests 把關。
    """
    char = state.player
    loc = world.current_location(char, gamedata)
    site = loc.get("arcane_trials")
    if not site:
        return
    avail = [qid for qid in quests.available_quests(char, gamedata, "arcane")
             if gamedata.quests[qid].get("arcane_site") == site]
    if not avail:
        if char.base_skill("destruction") < 75:
            ui.message("引路人瞥了你一眼,搖頭:「你的破壞之術還沒到能承受終極奧義的境界 —— "
                       "回去再淬煉,毀滅之道至少要登堂入室(75)才談得上試煉。」", style="grey70")
        elif site == "fused":
            ui.message("引路人凝視著你:「三系真言尚未在你身上齊聚 —— 先走遍各省、集齊火冰雷的試煉,"
                       "融合的試煉方會在此顯現。」", style="grey70")
        else:
            ui.message("引路人微微頷首:「此地的試煉你已了結 —— 其餘真言,得往別省的法師公會尋訪。」",
                       style="grey70")
        return
    ui.message("一名眼瞳燃著奧術微光的引路人打量著你:「終極真言不予空有天賦者 —— "
               "你不能用一個元素去征服它的化身,先以血肉與鋼鐵勝過牠,真言才會降臨於你。」", style="cyan")
    opts = [(qid, f"{gamedata.quests[qid]['name']} — {quests.objective_text(char, gamedata, qid)}")
            for qid in avail]
    qid = ui.menu("奧術試煉的引路人", opts, allow_back=True)
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
    """當地仍在世(未被你滅口)的可攀談 NPC。R51:巢穴同類只透過 action_lair(詛咒閘)互動,
    不入一般「攀談」→ 凡人/異種詛咒在巢穴只見沉寂,不外露同類。"""
    if gamedata.location(state.player.location_id).get("lair"):
        return []
    return [n for n in gamedata.npcs_at(state.player.location_id)
            if n not in state.player.murdered_npcs]


def _resolve_dialogue_topic(state: GameState, gamedata: GameData, nid: str,
                            topic: dict, ctx: dict, depth: int = 0) -> None:
    """解析並呈現一個對話話題(套 effects/外交立場、套話、淺子話題;深度封頂 2)。"""
    res = dialogue.resolve_topic(state, gamedata, nid, topic, ctx, state.rng)
    if res.get("hours"):
        state.time.advance(res["hours"])
    if res.get("text"):
        ui.message(res["text"], style="italic white")
    for m in res.get("messages", []):
        ui.message(m, style="grey70")
    if res.get("tired"):
        ui.message("舌乾口燥,話都說不利索了。", style="yellow")
    ui.show_events(res.get("skill_events", []), gamedata)
    subs = res.get("subtopics", []) if depth == 0 else []
    if subs:
        char = state.player
        subopts = []
        for sid in subs:
            sd = dialogue._topic_def(gamedata, nid, sid)
            if sd and dialogue.meets_dialogue(char, state, gamedata,
                                              dialogue._resolve_req(sd.get("requires"), ctx), ctx):
                subopts.append((sid, sd.get("label", sid), dialogue._topic_chips(sd)))
        if subopts:
            pick = ui.menu("追問", subopts, allow_back=True)
            if pick:
                sd = dialogue._topic_def(gamedata, nid, pick)
                _resolve_dialogue_topic(state, gamedata, nid, {"id": pick, **sd}, ctx, depth=1)


def action_talk(state: GameState, gamedata: GameData) -> str | None:
    char = state.player
    npc_ids = _living_npcs_at(state, gamedata)
    if not npc_ids:
        ui.message("這裡沒有可攀談的人。", style="grey70")
        return None
    nid = ui.menu("與誰攀談?", [(n, gamedata.npcs[n]["name"]) for n in npc_ids], allow_back=True)
    if nid is None:
        return None
    npc = gamedata.npcs[nid]
    ctx = dialogue.talk_ctx(state, gamedata, nid)
    att = dialogue.attitude(char, state, gamedata, nid, ctx)
    # 看破吸血鬼 → 驚呼報官,對話即止(賞金嚇阻)
    if att == "vampire_seen":
        ui.npc_panel(npc, dialogue.disposition(char, gamedata, nid),
                     greeting=dialogue.greeting_for(char, state, gamedata, nid, ctx, att))
        rep = dialogue.report_vampire(char, gamedata)
        ui.message(rep["message"], style="red")
        return None
    while True:
        disp = dialogue.disposition(char, gamedata, nid)
        ui.npc_panel(npc, disp, greeting=dialogue.greeting_for(char, state, gamedata, nid, ctx, att))
        opts = []
        for t in dialogue.topics_for(char, state, gamedata, nid, ctx, att):
            opts.append((f"topic:{t['id']}", t["label"], dialogue._topic_chips(t)))
        offered = dialogue.offered_quest(char, gamedata, nid)
        if offered and att != "hostile":                 # 敵陣營不託付委託
            opts.append(("quest", f"接受委託:{gamedata.quests[offered]['name']}"))
        rumor = dialogue.offered_rumor(char, gamedata, nid)   # R81:追問傳聞 → 線索任務 / 即時指路
        if rumor and att != "hostile":
            tag = "線索" if rumor["kind"] == "quest" else "指路"
            opts.append(("rumor", f"追問傳聞·{tag}:「{npc.get('rumor', '')[:16]}…」"))
        pc = int(dialogue.persuade_chance(char, gamedata, nid) * 100)
        sp = gamedata.skills["speechcraft"]["practice"]   # 唯讀靜態價碼;勿呼叫 practice_cost(會扣體力)
        opts.append(("persuade", "說服(口才)",
                     [{"text": f"成功率 {pc}%", "tone": "gold"},
                      {"text": f"成功 +{dialogue.persuade_delta(char.skill('speechcraft'))} 好感", "tone": "green"},
                      {"text": f"耗 {sp['hours']}時·體力{sp['fatigue']}", "tone": "cyan"}]))
        opts.append(("bribe", f"賄賂({dialogue.BRIBE_COST} 金)"))
        if char.cover_knower == nid:                  # R100:此人正是識破你的知情者 → 限時滅口
            opts.append(("silence", "🔪 滅口(限時決鬥 —— 在他通風報信前了結他)"))
        opts.append(("murder", "🔪 暗殺此人"))
        choice = ui.menu("對話", opts, allow_back=True)
        if choice is None:
            return None
        if choice.startswith("topic:"):
            tid = choice.split(":", 1)[1]
            td = dialogue._topic_def(gamedata, nid, tid)
            act = td.get("action") if td else None
            if act == "fence":                       # R98 盜賊同志:便攜銷贓門路
                action_fence(state, gamedata)
            elif act == "supply":                    # R98 神話黎明同志:禁術貨源
                _comrade_supply(state, gamedata)
            elif act == "contract":                  # R98 黑暗兄弟會同志:接私活(可能戰死)
                if _comrade_contract(state, gamedata) == "dead":
                    return "dead"
            elif td:
                _resolve_dialogue_topic(state, gamedata, nid, {"id": tid, **td}, ctx)
            att = dialogue.attitude(char, state, gamedata, nid, ctx)
        elif choice == "quest":
            _accept_and_brief(state, gamedata, offered)
            return None
        elif choice == "rumor":                              # R81:追問傳聞兌現
            if rumor["kind"] == "quest":
                _accept_and_brief(state, gamedata, rumor["id"])
                return None
            res = landmarks.discover(state, gamedata, rumor["id"])   # 即時揭露同省地標 + 小獎勵
            ui.message("對方壓低聲音,給你指了條道。", style="grey70")
            if res:
                ui.landmark_discovery(res)
            else:
                ui.message("那地方你早已知曉了。", style="grey70")
            att = dialogue.attitude(char, state, gamedata, nid, ctx)
        elif choice == "persuade":
            r = dialogue.persuade(char, gamedata, nid, state.rng)
            state.time.advance(r["hours"])
            ui.message("對方頗為受用,好感提升。" if r["ok"] else "話不投機,對方有些不悅。",
                       style="green" if r["ok"] else "yellow")
            if r["tired"]:
                ui.message("舌乾口燥,話都說不利索了。", style="yellow")
            ui.show_events(r["skill_events"], gamedata)
            att = dialogue.attitude(char, state, gamedata, nid, ctx)   # 回暖可能改變態度
        elif choice == "bribe":
            r = dialogue.bribe(char, gamedata, nid)
            ui.message(r["message"], style="green" if r["ok"] else "red")
            att = dialogue.attitude(char, state, gamedata, nid, ctx)
        elif choice == "silence":
            if _undercover_silence(state, gamedata, nid) == "dead":
                return "dead"
            return None
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
    pb = (formulas.prep_budget(char.skill("scout")) + mastery.prep_bonus(char, gamedata)) if got_drop else 0   # 潛殺成功也享偵查備戰
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
    talked = False
    while crime.bounty(char, province) > 0:
        b = crime.bounty(char, province)
        opts = [
            ("pay", f"繳清罰金({b} 金)"),
            ("jail", "乖乖入獄服刑"),
            ("resist", "拔劍反抗(與衛兵開戰)"),
        ]
        talk_cap = dialogue.TALK_DOWN_MAX + mastery.talk_down_mod(char, gamedata).get("cap_bonus", 0)   # 里程碑「巧言脫罪」抬高可說退賞金上限
        if not talked and b <= talk_cap:                 # 小額賞金可試以口才說退(大罪說不過去;巧言脫罪可化解更大的事)
            tpct = int(dialogue.talk_down_chance(char, b, gamedata) * 100)
            opts.insert(0, ("talk", f"說服衛兵(口才,成功率 {tpct}%)"))
        choice = ui.menu("如何應對?", opts)
        if choice == "talk":
            r = dialogue.talk_down_guard(char, gamedata, province, state.rng)
            state.time.advance(r["hours"])
            ui.show_events(r["skill_events"], gamedata)
            if r["ok"]:
                ui.message("你三言兩語,說得衛兵將信將疑、終於揮手放行 —— 賞金一筆勾銷。", style="green")
            else:
                ui.message("衛兵不為所動:「少廢話,束手就擒!」", style="yellow")
                talked = True       # 該次說服消耗:下一輪不再提供 talk,逼玩家繳金/服刑/反抗
            if r["tired"]:
                ui.message("口乾舌燥,話都說不利索了。", style="yellow")
        elif choice == "pay":
            r = crime.pay_fine(char, gamedata)
            if r["ok"]:
                ui.message(f"你繳清了 {r['paid']} 金罰金,衛兵讓開了路。", style="green")
            else:
                ui.message(f"你付不起 {r['owed']} 金 —— 只能服刑或反抗。", style="yellow")
        elif choice == "jail":
            r = crime.serve_sentence(char, gamedata, state.time)
            ui.message(f"你被關押了 {r['hours']} 小時,{province}的賞金一筆勾銷。", style="grey70")
        elif choice == "resist":
            # 賞金越高,出動的衛兵越多(1–3 名);省賞金達 T3 → 一名換成衛兵隊長(R84 城門升級)
            n = 1 + min(2, crime.bounty(char, province) // 80)
            guards = [combat.spawn_creature(gamedata, "city_guard", state.rng) for _ in range(n)]
            if crime.bounty(char, province) >= crime.ACTIVE_HEAT_THRESHOLDS[-1]:
                guards[0] = combat.spawn_creature(gamedata, "city_captain", state.rng)
            if run_battle(state, gamedata, guards) == "dead":
                return "dead"
            crime.add_bounty(char, province, 40)   # 拒捕罪加一等
            ui.message("你殺出重圍逃進巷弄 —— 但賞金又添了一筆,你仍是通緝犯。", style="red")
            return None
    return None


_BEAST_TOWN_MANHUNT_CHANCE = 0.85   # R50:獸形現於城中被衛兵圍捕的機率(主動入城=自找;高但非必中)
_KNOWER_CREATURE = "guild_enforcer"   # R100:知情者決鬥用的戰鬥替身(複用 R96 公會打手 bestiary)


def _undercover_detection(state: GameState, gamedata: GameData) -> None:
    """R100:臥底在城鎮被某現有具名 B NPC 起疑(rng·低 secrecy → 高機率)→ 指派知情者 + 限時追殺視窗。
    僅指派(不戰鬥);滅口走 action_talk 的「🔪 滅口」限時決鬥。"""
    char = state.player
    if not undercover.on_mission(char) or undercover.has_knower(char):
        return
    if not state.rng.chance(undercover.detection_chance(char)):
        return
    loc = world.current_location(char, gamedata)
    nid = undercover.pick_knower(char, gamedata, province=loc.get("province"))
    if not nid:
        return
    undercover.assign_knower(char, state, nid)
    name = gamedata.npcs[nid]["name"]
    where = gamedata.location(gamedata.npcs[nid]["location"])["name"]
    ui.message(f"⚠ {name}起了疑心 —— 他察覺你的身分不對勁,正打算通風報信。"
               f"趕在他開口前讓他閉嘴(他人在{where};第 {char.cover_knower_deadline} 日前)。", style="bold red")


def _undercover_silence(state: GameState, gamedata: GameData, nid: str) -> str | None:
    """R100 殺知情者滅口:限時決鬥(KNOWER_DUEL_ROUNDS 回合內擊殺)。
    擊殺→掩護保住(secrecy 回地板+惡名);脫逃(逾回合)→曝光。回傳 'dead'|None。"""
    char = state.player
    name = gamedata.npcs[nid]["name"]
    ui.message(f"你尾隨{name}至無人處 —— 必須在他喊出口前的電光石火間了結他。", style="magenta")
    foe = combat.spawn_creature(gamedata, _KNOWER_CREATURE, state.rng)
    foe.name = name
    res = run_battle(state, gamedata, foe, flee_after_rounds=undercover.KNOWER_DUEL_ROUNDS)
    if res == "dead":
        return "dead"
    if res == "victory":
        char.murdered_npcs.append(nid)               # 知情者已死 → 自世界移除(pick_knower 亦排除)
        undercover.silence_knower(char)
        ui.message(f"{name}癱軟在你臂彎裡,情報隨他一同沉默 —— 掩護保住了,但你手上又添一條人命。",
                   style="red")
    else:                                            # fled_enemy:沒能在限時內了結 → 對方脫逃回報
        ev = undercover.expose(char)
        bname = gamedata.factions.get(ev["cover_guild"], {}).get("name", ev["cover_guild"])
        ui.message(f"{name}掙脫你的手、奪路狂奔 —— 你的身分將傳遍{bname}。掩護就此瓦解。", style="bold red")
    return None


def _curse_manhunt(state: GameState, gamedata: GameData) -> str | None:
    """R50:詛咒被識破 → 衛兵實戰圍捕(把被動社交封鎖升為主動危險)。回傳 'dead' 或 None。

    只在城/鎮觸發、互斥兩源(吸血鬼/狼人不能同時):
      - 狼人獸形現於城中 → 高機率引衛兵+鎮民圍捕(鬧市現巨狼)。
      - 高階(shunned)吸血鬼 → `vampirism.detection_chance`(隨階/滿月升)被識破。
    進食壓階 / 變回人形即可規避(= 玩家可管理的詛咒 loop)。複用 guard resist 分支的 spawn 管線。"""
    char = state.player
    loc = world.current_location(char, gamedata)
    if loc["type"] not in ("city", "town"):
        return None
    province = crime.province_of(char, gamedata)
    if lycanthropy.is_beast(char, state):
        if not state.rng.chance(_BEAST_TOWN_MANHUNT_CHANCE):
            return None
        n = 3 + min(2, lycanthropy.tier(char))
        bounty_add = 100
        ui.message("一頭巨狼現身鬧市 —— 鎮民驚逃、警鐘大作,衛兵舉刃自四面湧來圍捕你!", style="bold red")
    elif vampirism.is_shunned(char, state) and not vampirism.is_disguised(char, gamedata):   # 偽裝入城 → 不被識破圍捕(R56)
        if not state.rng.chance(vampirism.detection_chance(char, state)):
            return None
        n = 2 + min(2, vampirism.stage(char, state) - vampirism.SHUN_STAGE)
        bounty_add = vampirism.FEED_BOUNTY
        ui.message("人群中有人厲聲尖叫:「是吸血鬼!」—— 火把與刀刃霎時將你團團圍住!", style="bold red")
    else:
        return None
    crime.add_bounty(char, province, bounty_add)
    char.infamy += 1
    guards = [combat.spawn_creature(gamedata, "city_guard", state.rng) for _ in range(n)]
    if run_battle(state, gamedata, guards) == "dead":
        return "dead"
    ui.message("你殺退了圍捕的衛兵,趁亂遁入暗巷 —— 但通緝令已然加身。", style="red")
    return None


# R84:賞金獵人路途追殺 —— 城門有衛兵,路上有獵人。tier 隨「最高省賞金」(active_heat)升。
_BOUNTY_HUNT_BASE_CHANCE = 0.35   # active_heat=1 的基礎被攔機率;每升一階 +0.12 夾 0.75;騎馬另乘 (1−規避)
_BOUNTY_HUNT_TIER = {1: "bounty_hunter", 2: "mercenary_tracker", 3: "master_hunter"}


def _bounty_hunter_ambush(state: GameState, gamedata: GameData) -> str | None:
    """R84:被通緝者旅途中遭賞金獵人攔截(tier 隨 active_heat,1–3 名)。回傳 'dead' 或 None。

    與城門 guard_confrontation 互補(城門=地方治安·讀省賞金;路途=跨省獵人·讀全域最高賞金 active_heat)。
    存活**不**加賞金/惡名(自衛 → 保「付清即冷卻路途」的可清契約);無新冷卻欄(travel 本身節流)。
    複用 offer_battle → 玩家保有 偵查/潛行撤退 等路途遭遇選項(專業獵人不可威嚇)。"""
    char = state.player
    heat = crime.active_heat(char)
    if heat < 1:
        return None
    tid = _BOUNTY_HUNT_TIER[heat]
    hunters = [combat.spawn_creature(gamedata, tid, state.rng) for _ in range(heat)]   # T1→1 / T2→2 / T3→3
    ui.message("一夥賞金獵人攔住了去路 —— 你的人頭,正高價懸賞。", style="bold red")
    if offer_battle(state, gamedata, hunters, surprise=True, mounted=True) == "dead":
        return "dead"
    return None


# R96:公會宿敵打手路途伏擊(複用 R84 範式;優先序低於賞金獵人,見 _travel_to)
_GUILD_AMBUSH_BASE = 0.10          # 每敵意 tier 的基礎被攔機率(×tier,夾 0.35);騎馬另乘 (1−規避)
_GUILD_HOSTILITY_AMBUSH_MIN = 2    # 只「敵視」(tier≥2=在宿敵公會 rank≥1)才出鋼;tier1「冷待」止於對話態度


def _guild_enforcer_ambush(state: GameState, gamedata: GameData, fid: str, tier: int) -> str | None:
    """R96:鬧翻某公會宿敵 → 其打手途中伏擊(敵意 tier 越高越多越強)。回傳 'dead' 或 None。

    敵意純衍生自 char.factions(身屬其宿敵公會),零存檔欄。**永久後果·by-design**:本作無退會
    機制 → 加入一個公會即與其宿敵結怨一生(burn-your-bridges,加入公會的代價;與 R84 可清賞金不同)。
    緩衝靠騎馬降頻 + offer_battle 偵查/潛行撤退;存活**不**加賞金/惡名(自衛,不雪上加霜)。"""
    creature = "guild_avenger" if tier >= 4 else "guild_enforcer"
    count = min(3, 1 + tier // 3)
    foes = [combat.spawn_creature(gamedata, creature, state.rng) for _ in range(count)]
    name = gamedata.factions[fid]["name"]
    ui.message(f"{name}的打手堵住了去路 —— 你壞了他們的事,該來算這筆帳了。", style="bold red")
    if offer_battle(state, gamedata, foes, surprise=True, mounted=True) == "dead":
        return "dead"
    return None


def action_character_sheet(state: GameState, gamedata: GameData) -> None:
    """互動式角色卡:渲染 overview,再提供唯讀檢視子選單(空/不適用項自動隱藏)。"""
    char = state.player
    ui.character_sheet(char, gamedata)
    while True:
        opts: list = [("resist", "元素抗性")]
        if char.active_effects:
            opts.append(("effects", "進行中效果"))
        if any(f in gamedata.factions for f in char.factions):
            opts.append(("factions", "公會與階級"))
        opts.append(("mastery", "技能里程碑"))
        opts.append(("achievements", "成就"))
        if powers.power_id(char, gamedata):
            opts.append(("power", "星座之力"))
        opts.append(("bounty", "聲望與通緝"))
        opts.append(("equip", "穿戴與套裝"))
        if char.spells:
            opts.append(("spellbook", "法術書"))
        if vampirism.is_vampire(char):
            opts.append(("vampire", "吸血鬼狀態"))
        if lycanthropy.is_werewolf(char):
            opts.append(("werewolf", "狼人狀態"))
        if skooma.has_touched_sugar(char):
            opts.append(("skooma", "斯庫瑪/月糖狀態"))
        opts += [("skill", "技能詳情"), ("resheet", "重看角色卡")]
        choice = ui.menu("角色資訊(檢視)", opts, allow_back=True)
        if choice is None:
            return
        if choice == "resist":
            ui.sheet_resistances(char, gamedata)
        elif choice == "effects":
            ui.sheet_effects(char, gamedata)
        elif choice == "factions":
            ui.sheet_factions(char, gamedata)
        elif choice == "mastery":
            ui.sheet_masteries(char, gamedata)
        elif choice == "achievements":
            ui.sheet_achievements(char, gamedata)
        elif choice == "power":
            ui.sheet_power(char, state, gamedata)
        elif choice == "bounty":
            ui.sheet_bounty(char, gamedata)
        elif choice == "equip":
            ui.sheet_equipment(char, gamedata)
        elif choice == "spellbook":
            ui.sheet_spellbook(char, gamedata)
        elif choice == "vampire":
            ui.sheet_vampirism(char, gamedata)
        elif choice == "werewolf":
            ui.sheet_lycanthropy(char, state, gamedata)
        elif choice == "skooma":
            ui.sheet_skooma(char, state, gamedata)
        elif choice == "skill":
            sk = ui.menu("檢視哪個技能?",
                         [(sid, f"{gamedata.skill_name(sid)} {char.skill(sid)}")
                          for sid in gamedata.skills], allow_back=True)
            if sk:
                ui.sheet_skill_detail(char, gamedata, sk)
        elif choice == "resheet":
            ui.character_sheet(char, gamedata)


def action_codex(state: GameState, gamedata: GameData) -> None:
    """遊戲內指南/圖鑑(唯讀、零存檔):選系統分類 → 渲染該條目 panel → 迴圈。

    比照 action_character_sheet;內容在 data/codex.json,渲染走 ui.codex_panel(R60)。"""
    index = ui.codex_index(gamedata)
    while True:
        choice = ui.menu("指南 / 圖鑑 📖", index, allow_back=True)
        if choice is None:
            return
        ui.codex_panel(gamedata.codex[choice], gamedata)


# ======================================================================
# 主迴圈
# ======================================================================
def _try_discover(state: GameState, gamedata: GameData, loc_id: str) -> None:
    """若當前地有未發現的具名地標 → 觸發一次性發現並呈現(純加性,不致死)。"""
    res = landmarks.discover(state, gamedata, loc_id)
    if res:
        ui.landmark_discovery(res)


def game_loop(state: GameState, gamedata: GameData) -> None:
    last_hub_loc = None
    _ach_seen = achievements.seed_seen(state.player, gamedata)   # 成就首達通知:載入當下已達成 → 重載不重報(零存檔欄)
    while True:
        # 吸血鬼狀態先結算(潛伏轉化 / 階級升降),再呈現本回合
        for ev in vampirism.update(state, gamedata):
            if ev["kind"] == "turn":
                ui.rule("血色甦醒")
                ui.message("高燒退去,飢渴湧上 —— 你已不再是活人。從此夜行嗜血,直到詛咒解除或永滅。",
                           style="bold red")
                ui.message("……血脈深處浮起一個方位:高岩裂石郡的荒沼下,一座血族地窖正召喚同類前去。",
                           style="grey70")
            elif ev["kind"] == "stage" and ev.get("rising"):
                name = vampirism.STAGE_NAMES[ev["stage"]]
                ui.message(f"血之飢渴加深 —— 你進入「{name}」之境:力量更盛,卻更難見容於日光與世人。",
                           style="magenta")

        # 斯庫瑪成癮:亢奮退去 / 戒斷起或加深 / 脫離戒斷(掛在吸血鬼之後)
        for ev in skooma.update(state, gamedata):
            if ev["kind"] == "comedown":
                ui.message("月糖的甜膩自血脈退去,世界重歸灰暗而遲鈍 —— 亢奮已盡。", style="magenta")
            elif ev["kind"] == "withdrawal":
                ui.message("戒斷的顫慄攫住你 —— 四肢虛軟、心神渙散,只剩對那抹甜的渴求在啃噬。",
                           style="bold red")
            elif ev["kind"] == "clean":
                ui.message("你撐過了最深的渴求,身體漸漸清明 —— 月糖的枷鎖鬆開了。", style="green")

        # 雙面間諜(R100):secrecy 衰減 + 逾期/歸零 → 掩護曝光(掛在斯庫瑪之後)
        for ev in undercover.update(state, gamedata):
            if ev["kind"] == "exposed":
                bname = gamedata.factions.get(ev["cover_guild"], {}).get("name", ev["cover_guild"])
                ui.message(f"風聲走漏 —— 你在{bname}的掩護身分敗露,潛入任務功虧一簣,自此與他們不共戴天。",
                           style="bold red")

        # 疾病(R53):惡化 / DoT 扣血(掛在斯庫瑪之後)
        for ev in diseases.update(state, gamedata):
            if ev["kind"] == "dot":
                ui.message(f"病灶在你體內潰爛 —— 你流失了 {ev['total']} 點生命(病痛不止,該求治了)。",
                           style="red")
            elif ev["kind"] == "worsen":
                ui.message("拖著未治的病,你的身子一日壞過一日 —— 症狀加重了。", style="yellow")

        # 限時增益藥水(R30):藥力到期 → 重算 + 報「藥力散去」(掛在斯庫瑪之後)
        for ev in potion_buff.update(state, gamedata):
            if ev["kind"] == "expire":
                ui.message("藥力散去 —— 你體內方才的增益逐漸消退。", style="grey70")

        # 狼人化:潛伏轉化 / 獸形過期變回(掛在斯庫瑪之後)
        for ev in lycanthropy.update(state, gamedata):
            if ev["kind"] == "turn":
                ui.rule("獸血甦醒")
                ui.message("月升之夜,你的骨骼錯裂、皮肉迸張 —— 狼人之血自此在你體內奔流。"
                           "從今往後,你能化身嗜血巨狼,直到詛咒解除。", style="bold red")
                ui.message("……血液裡躁動著歸屬的渴望:瓦倫森林綠影林深處,一支獵群在血月下嚎叫,等你同窩。",
                           style="grey70")
            elif ev["kind"] == "revert":
                ui.message("獸形的狂暴退去,你重歸人形 —— 筋疲力盡,四肢仍因方才的撕咬而顫抖。",
                           style="magenta")

        # 房產「精神飽滿」:依到期刷新現行快取(progression.use_skill 讀;過期則本圈起 xp 回中性)
        housing.refresh_well_rested(state.player, state.time.absolute_hours())

        # 陣營大事件(動態政局):authored 時間軸觸發城邦易幟,廣播天下大勢
        for ev in worldstate.update(state, gamedata):
            ui.rule("天下大勢")
            ui.message(ev["news"], style="bold magenta")

        # 常態世界脈動(動態新聞層):主線後世界不靜默,持續廣播在地新聞;部分聚光某省可重複委託一段時間。
        # 別於 worldstate「天下大勢」(政權劇變):脈動是常態餘響,以「四方傳聞」橫幅 + 別色區隔。
        for ev in worldpulse.update(state, gamedata):
            ui.rule("四方傳聞")
            ui.message(ev["news"], style="cyan")

        # 湮滅之門逐門開合:所在地若已不可見(如殺達貢、危機落幕後死亡之地崩合),拋回最近的城
        if not world.is_visible(state.player, gamedata, state.player.location_id):
            _dest = world.relocate_target(state.player, gamedata)
            state.player.location_id = _dest
            ui.message(f"身後的裂隙轟然崩合 —— 你被拋回{gamedata.location(_dest)['name']}。", style="yellow")

        # AI 陣營自走戰爭(階段五):NPC 互吞中立/互翻彼此城 + 反攻你的領地(在 tick_tax 前 → 本圈即結算失守)
        for ev in aiwar.update(state, gamedata):
            if ev["kind"] == "flip":
                ui.rule("天下大勢")
                ui.message(ev["news"], style="bold magenta")
            elif ev["kind"] == "raid":
                cname = gamedata.location(ev["loc"])["name"]
                ui.message(f"⚠ {politics.cause_name(ev['by'])}兵臨你的「{cname}」,守軍僅 {ev['garrison']} —— 速回防,"
                           f"否則城邦將失守!", style="bold red")

        # 軍餉結算(招兵買馬階段二):週期扣餉,付不出 → 逃兵
        for ev in warband.tick_upkeep(state):
            if ev["kind"] == "paid":
                ui.message(f"你發放了軍餉 —— 餉銀 {ev['wage']} 金,{ev['soldiers']} 名士兵士氣高昂。",
                           style="grey70")
            elif ev["kind"] == "desert":
                ui.message(f"軍餉短缺,{ev['deserters']} 名士兵憤而離營(餘 {ev['soldiers']} 名)。",
                           style="red")

        # 領地稅收結算(城戰階段三):居民稅 − 駐軍維護;民心浮動則稅斷、潰散則城叛
        for ev in politics.tick_tax(state, gamedata):
            cname = gamedata.location(ev["loc"])["name"]
            if ev["kind"] == "revolt":
                ui.message(f"⚠ 駐軍潰散,「{cname}」民變四起,城邦就此叛離你的掌握!", style="bold red")
            elif ev["kind"] == "tax":
                if ev["unrest"]:
                    ui.message(f"「{cname}」民心浮動,稅收中斷 —— 仍須付駐軍維護 {ev['maint']} 金"
                               f"(駐軍僅 {ev['garrison']},須回防!)。", style="red")
                else:
                    ui.message(f"領地稅收:「{cname}」入庫 {ev['tax']} 金(扣駐軍維護 {ev['maint']} → "
                               f"淨 {ev['net']:+d})。", style="grey70")

        # 具名地標:首次身處某地 → 一次性「發現」(統一在此觸發 → 起始城/旅行抵達/任意當前地皆涵蓋)
        _try_discover(state, gamedata, state.player.location_id)

        # 技能里程碑 v2:達門檻的待決二選一,在安全互動點(回城迴圈頂)呈現 —— 絕不在戰鬥中
        _drain_mastery_choices(state, gamedata)

        # 成就首達通知(R55):本圈新達成的成就 → 一次性「榮譽印記」(去重靠 session 暫態 _ach_seen)
        for ev in achievements.update(state, gamedata, _ach_seen):
            ui.rule("榮譽印記")
            ui.message(f"★ 成就達成:「{ev['name']}」—— {ev['desc']}", style="bold yellow")

        ui.rule()
        ui.status_line(state, gamedata)
        brief = state.player.location_id == last_hub_loc   # 同地點重複回合 → 麵包屑(不重畫整張地點卡)
        ui.location_panel(state.player, gamedata, brief=brief)
        last_hub_loc = state.player.location_id
        loc = world.current_location(state.player, gamedata)
        services = loc.get("services", [])

        player = state.player
        # 世人拒於門外:高階吸血鬼,或在城鎮中仍處獸形的狼人(獸形入城經計時 carryover)
        beast_in_town = lycanthropy.is_beast(player, state) and loc["type"] in ("town", "city")
        shunned = (vampirism.is_shunned(player, state)
                   and not vampirism.is_disguised(player, gamedata)) or beast_in_town   # 偽裝入城 → 不被拒於門外(R56)
        # --- 冒險 ---
        adventure: list = []
        if loc["type"] == "dungeon":
            adventure.append(("dungeon", "深入地城 ⚔"))
        if loc.get("danger", 0) > 0 and loc["type"] != "dungeon" and not loc.get("lair") and not loc.get("refuge"):
            adventure.append(("explore", "探索狩獵 ⚔"))
        # 戴德拉神殿:在此地祭壇供奉祈願,接取該親王的試煉任務(R45;達門檻才現任務)。
        if loc.get("shrine"):
            adventure.append(("shrine", "🕯 供奉祈願"))
        # R51:詛咒巢穴(吸血鬼隱穴 / 狼人巢穴)——唯對應詛咒者得入,凡人只見沉寂。
        if _player_is_lair_kin(player, loc):
            adventure.append(("lair", "🦇 進入血族地窖" if loc["lair"] == "vampire" else "🐺 進入獵群巢穴"))
        # R84:亡命徒藏身處 —— 唯通緝者/亡命徒得入(衛兵不擾的安全區),良民只見沉寂。
        if loc.get("refuge") and crime.is_outlaw(player):
            adventure.append(("refuge", "🗡 潛入藏身處"))
        adventure.append(("travel", "旅行"))
        adventure.append(("map", "世界地圖"))
        # --- 城區(分區域:市集區 / 公會區 / 廣場)---
        if beast_in_town:
            ui.message("一頭嗜血巨狼闖入城中,人們驚恐奔逃、店門緊閉 —— 獸形之軀無從與人交易,"
                       "待變回人形再來吧。", style="red")
        elif shunned:
            ui.message("世人察覺了你的真面目,紛紛走避 —— 高階吸血鬼無法與人交易,先進食壓下飢渴吧。",
                       style="red")
        market: list = []     # 市集區:商業
        guilds: list = []     # 公會區:各公會分部 / 聖所
        plaza: list = []      # 廣場:旅店 / 訓練 / 告示 / 攀談 / 進食
        if "merchant" in services and not shunned:
            market.append(("shop", "商店"))
        if "armorer" in services:
            market.append(("craft", "鍛造工坊 🛠"))
            market.append(("temper", "淬鍊強化 ⚒"))
            market.append(("meltdown", "回爐熔解 ♻(成品→材料)"))
        if gamedata.has_stable(player.location_id) and not shunned:
            market.append(("stable", "馬廄 🐎(坐騎 · 長槍)"))
        if "mages_guild" in services:
            guilds.append(("guild_mages", "法師公會"))   # 學習法術 + 入會/任務,進子選單
        if "fighters_guild" in services:
            guilds.append(("fg_hall", "戰士公會"))
        if "companions" in services:
            guilds.append(("cmp_hall", "戰友團 🐺"))
        if "thieves_guild" in services:
            guilds.append(("tg_hall", "盜賊公會"))
        # 黑暗兄弟會聖所:唯有入會者才知其所在(血債招募後解鎖)
        if "dark_brotherhood" in services and brotherhood.is_member(player):
            guilds.append(("db_hall", "黑暗兄弟會聖所 🗡"))
        # 神話黎明聖堂:唯有「凱瓦奇陷落」大事件後,信徒才自陰影中現身
        if ("mythic_dawn" in services
                and politics.DAEDRIC_UNLOCK_EVENT in getattr(player, "world_events_fired", [])):
            guilds.append(("md_hall", "神話黎明 🔥"))
        # 九聖小修道院:同一場湮滅危機後,沉寂的聖團於安維爾重新集結
        if ("knights_nine" in services
                and politics.DAEDRIC_UNLOCK_EVENT in getattr(player, "world_events_fired", [])):
            guilds.append(("kn_hall", "九神騎士團 ⚜"))
        if player.is_vampire and loc["type"] in ("town", "city"):
            plaza.append(("feed", "🩸 吸血進食(獵取活人,重置飢餓)"))
        if skooma.is_addicted(player) and loc["type"] in ("town", "city") and not shunned:
            plaza.append(("skooma_cure", "🌙 尋訪療者,求解月糖之癮"))
        if lycanthropy.is_werewolf(player) and loc["type"] in ("town", "city") and not shunned:
            plaza.append(("werewolf_cure", "🐺 尋訪獵巫女巫,求解獸血之咒"))
        if (loc["type"] in ("town", "city") and not shunned
                and (diseases.has_any(player) or vampirism.is_infected(player)
                     or lycanthropy.is_infected(player))):
            plaza.append(("disease_cure", "🩹 尋訪神殿療者(淨化疾病)"))
        if (gamedata.house_at(player.location_id) or housing.owns(player, player.location_id)) and not shunned:
            owned = housing.owns(player, player.location_id)
            plaza.append(("house", "🏠 我的房產" if owned else "🏠 房產仲介(置產)"))
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
            _pid = powers.power_id(player, gamedata)
            if _pid == "beast_form":     # R50:狼人平時(野外/城鎮)可主動獸化(滿月免冷卻)
                craft.append(("power", "🐺 獸化變身(化身嗜血巨狼)"))
            else:
                craft.append(("power", f"星座之力({powers.power_def(_pid)['name']})"))
        if lycanthropy.is_beast(player, state):   # R50:獸形中可主動變回人形(力竭代價)
            craft.append(("revert_human", "🧍 變回人形(力竭)"))
        craft.append(("alchemy", "煉金"))
        if any(gamedata.item(s["id"]).get("kind") == "poison" for s in player.inventory):
            craft.append(("coat", "塗毒"))
        if enchanting.filled_soul_gems(player, gamedata):
            craft.append(("enchant", "附魔"))
            if enchanting.chargeable_weapons(player, gamedata):
                craft.append(("recharge", "附魔充能"))
        # --- 角色與物品 ---
        character: list = [("quests", "任務日誌"), ("inventory", "背包"),
                           ("practice", "練習技能"), ("rest", "原地休息"), ("sheet", "角色卡"),
                           ("guide", "指南/圖鑑 📖")]
        if player.companions:                            # 有同伴 → 隊伍管理(檢視 HP/羈絆/解散)
            character.insert(0, ("party", "隊伍 ⚔"))
        if politics.held_tax_cities(player, gamedata):   # 有親手攻下的城 → 領地總覽(階段四)
            character.insert(0, ("territory", "領地總覽 🏰"))
        if warband.is_warlord(player, gamedata):     # 領主/首領 → 招兵買馬(整軍經武)
            character.insert(0, ("warband", "整軍經武 ⚑"))
        if player.can_level_up():
            character.insert(0, ("levelup", "★ 升級"))
        # --- 系統 ---
        system = [("save", "存檔"), ("retire", "隱退江湖"), ("quit", "回主選單")]
        goto_keys = ["go:" + dest for dest, _h in world.travel_options(player, gamedata)]   # 地點卡出口可點旅行

        choice = ui.grouped_menu("要做什麼?", [
            ("冒險", adventure), ("城區", city_group),
            ("製作", craft), ("人物", character), ("系統", system),
        ], extra_keys=goto_keys, cta_keys=["levelup"])
        # 選了某個城區 → 進入該區的子選單挑實際服務(返回則回到城區)
        _dist = next((d for d in districts if d[0] == choice), None)
        if _dist:
            choice = ui.menu(_dist[1], _dist[2], allow_back=True)
            if choice is None:
                continue
        died = None
        if choice.startswith("go:"):                 # 地點卡出口直接旅行(web 可點 chip)
            died = _travel_to(state, gamedata, choice[3:])
        elif choice == "map":
            ui.world_map(player, gamedata)
        elif choice == "dungeon":
            died = action_dungeon(state, gamedata)
            ui.status_line(state, gamedata)          # 出地城即重設 HUD(清掉召喚物列,免里程碑選擇彈窗殘留)
        elif choice == "explore":
            died = action_explore(state, gamedata)
        elif choice == "shrine":
            action_shrine(state, gamedata)
        elif choice == "lair":
            died = action_lair(state, gamedata)
        elif choice == "refuge":
            action_refuge(state, gamedata)
        elif choice == "travel":
            died = action_travel(state, gamedata)
        elif choice == "shop":
            action_shop(state, gamedata)
        elif choice == "inn":
            action_inn(state, gamedata)
        elif choice == "stable":
            action_stable(state, gamedata)
        elif choice == "house":
            action_house(state, gamedata)
        elif choice == "feed":
            action_feed(state, gamedata)
        elif choice == "skooma_cure":
            action_skooma_cure(state, gamedata)
        elif choice == "werewolf_cure":
            action_werewolf_cure(state, gamedata)
        elif choice == "disease_cure":
            action_disease_cure(state, gamedata)
        elif choice == "trainer":
            action_trainer(state, gamedata)
        elif choice == "court":
            died = action_court(state, gamedata)
        elif choice == "guild_mages":
            mg_opts = [("spells", "學習法術"), ("mg_hall", "公會事務(入會 / 任務)")]
            if loc.get("arcane_trials"):                 # R-arcane:奧術試煉引路人(終極法術試煉發起點)
                mg_opts.append(("arcane", "🔥 奧術試煉的引路人"))
            if player.is_vampire:
                mg_opts.append(("cure", "✦ 探詢血咒的解法"))
            sub = ui.menu("法師公會", mg_opts, allow_back=True)
            if sub == "spells":
                action_spell_vendor(state, gamedata)
            elif sub == "mg_hall":
                action_guild_hall(state, gamedata, "mages_guild")
            elif sub == "arcane":
                action_arcane_trials(state, gamedata)
            elif sub == "cure":
                action_vampire_cure(state, gamedata)
        elif choice == "fg_hall":
            action_guild_hall(state, gamedata, "fighters_guild")
        elif choice == "cmp_hall":
            action_guild_hall(state, gamedata, "companions")
        elif choice == "tg_hall":
            action_guild_hall(state, gamedata, "thieves_guild")
        elif choice == "db_hall":
            died = action_sanctuary(state, gamedata)
        elif choice == "md_hall":
            died = action_mythic_dawn(state, gamedata)
        elif choice == "kn_hall":
            died = action_knights_hall(state, gamedata)
        elif choice == "board":
            action_board(state, gamedata)
        elif choice == "talk":
            died = action_talk(state, gamedata)
        elif choice == "quests":
            action_quest_log(state, gamedata)
        elif choice == "craft":
            action_craft(state, gamedata)
        elif choice == "temper":
            action_temper(state, gamedata)
        elif choice == "meltdown":
            action_meltdown(state, gamedata)
        elif choice == "cast":
            action_cast_self(state, gamedata)
        elif choice == "power":
            action_use_power(state, gamedata)
            # R50:若剛在城鎮中主動獸化 → 鬧市現巨狼,衛兵圍捕
            if lycanthropy.is_beast(player, state):
                died = _curse_manhunt(state, gamedata)
        elif choice == "revert_human":
            lycanthropy.revert(player, state, gamedata)
            ui.message("你的骨骼重新歸位、獸性褪去 —— 你變回了人形,精疲力竭。", style="grey70")
        elif choice == "alchemy":
            action_alchemy(state, gamedata)
        elif choice == "coat":
            action_coat_weapon(state, gamedata)
        elif choice == "enchant":
            action_enchant(state, gamedata)
        elif choice == "recharge":
            action_recharge_enchant(state, gamedata)
        elif choice == "inventory":
            action_inventory(state, gamedata)
        elif choice == "practice":
            action_practice(state, gamedata)
        elif choice == "warband":
            action_warband(state, gamedata)
        elif choice == "party":
            action_party(state, gamedata)
        elif choice == "territory":
            action_territory(state, gamedata)
        elif choice == "rest":
            died = action_rest(state, gamedata)
        elif choice == "sheet":
            action_character_sheet(state, gamedata)
        elif choice == "guide":
            action_codex(state, gamedata)
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
        ui.clear_hud()        # web:回到主選單時清掉前一局殘留的常駐 HUD(死亡重開/離開重啟皆然)
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
            _intro_quest_briefing(state, gamedata)   # 起手任務首入提示(我為何在這)

        game_loop(state, gamedata)


if __name__ == "__main__":
    main()
