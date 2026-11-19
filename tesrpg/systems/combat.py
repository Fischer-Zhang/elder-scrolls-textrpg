"""回合制戰鬥的規則引擎。

設計成「邏輯與 IO 分離」:
  - 這裡只算結果、改數值、發 learn-by-doing 的技能 xp,回傳事件 dict;
  - 互動式的逐回合呈現在 main.py / ui,呼叫這裡的純函式。
另提供 auto_resolve():無 IO 的全自動對戰,給單元測試與平衡用。
"""

from __future__ import annotations

from tesrpg import formulas
from tesrpg.gamedata import GameData
from tesrpg.models import Character, Creature
from tesrpg.rng import RNG
from tesrpg.systems import divines, inventory, loot, magic, mastery, progression, race_ability, smithing, stats


# ======================================================================
# 生成怪物
# ======================================================================
def spawn_creature(gamedata: GameData, template_id: str, rng: RNG) -> Creature:
    t = gamedata.bestiary[template_id]
    hp = max(1, round(t["max_health"] * rng.roll(0.85, 1.15)))
    return Creature(
        template_id=template_id, name=t["name"],
        strength=t["strength"], agility=t["agility"], speed=t["speed"],
        max_health=hp, health=hp, armor_rating=t["armor_rating"],
        attack=dict(t["attack"]), attacks=[dict(a) for a in t.get("attacks", [])],
        loot_gold=list(t["loot_gold"]),
        loot_table=list(t.get("loot", [])), flavor=t.get("flavor", ""),
        danger=t.get("danger", 1), resist=dict(t.get("resist", {})),
        reflect=t.get("reflect", 0.0),
    )


# 生態遭遇表:野外抽怪依「地點 biome」加權,讓各省玩起來不同(細化省分)。
# 帶 biomes 標籤的怪在符合 biome 處更常出現、在他鄉罕見;無標籤怪=四海皆有的通用池
# (giant_rat/wolf/bandit…),確保任何 biome 的池都不會被抽空。
BIOME_MATCH_WEIGHT = 3.0      # 怪的 biomes 含當地 → 權重 ×3(在地常見)
BIOME_MISMATCH_WEIGHT = 0.25  # 怪有 biomes 但不含當地 → 權重 ×0.25(離鄉的遊蕩者,罕見)


def _biome_weight(template: dict, biome: str | None) -> float:
    """依當地 biome 調整某怪的抽取權重。無當地 biome 或怪無 biomes 標籤 → 不調整。"""
    base = template.get("weight", 1)
    biomes = template.get("biomes")
    if not biome or not biomes:
        return base
    if biome not in biomes and template.get("habitat_bound"):
        return 0.0   # R144 現實邏輯:物理上離不開棲地的怪(水生魚/位面元素)永不「離鄉遊蕩」
    return base * (BIOME_MATCH_WEIGHT if biome in biomes else BIOME_MISMATCH_WEIGHT)


def random_encounter_group(gamedata: GameData, player_level: int, rng: RNG,
                           max_danger: int | None = None,
                           biome: str | None = None) -> list[Creature]:
    """隨機遭遇一「群」敵人;危險度越高越容易成群、規模越大(最危險區可達 4)。
    biome:當地生態(雪原/火山/沼澤…),影響抽到哪些怪(見 _biome_weight)。"""
    roll = rng.random()
    d = max_danger or 1
    if d >= 5:        # 最危險區:常成群
        size = 1 if roll < 0.35 else (2 if roll < 0.68 else (3 if roll < 0.90 else 4))
    elif d >= 3:      # 中危區
        size = 1 if roll < 0.55 else (2 if roll < 0.85 else 3)
    else:             # 低危區
        size = 1 if roll < 0.75 else (2 if roll < 0.94 else 3)
    group = [random_encounter(gamedata, player_level, rng, max_danger, biome) for _ in range(size)]
    # BOSS 級(solo)只單獨出現:群中若含 solo 敵人,收斂成那一隻(避免一次多隻王)
    boss = next((e for e in group
                 if gamedata.bestiary.get(e.template_id, {}).get("solo")), None)
    return [boss] if boss is not None else group


def spawn_companion(gamedata: GameData, companion_id: str, rng: RNG,
                    current_hp: int | None = None, max_health_bonus: int = 0,
                    char=None) -> Creature:
    """把雇用的同伴生成為我方戰鬥單位。

    current_hp:持久 HP(同伴系統深化;None=滿血登場,向後相容);max_health_bonus:羈絆耐久加成。
    char(同伴深化 Tier 2):提供時,以「屬性+技能+裝備」經共用玩家公式**生成時烘焙**戰力(裝備=戰利品 sink)+
    掛武器附魔載體(完全比照玩家);**char=None → 走既有模板路徑逐位元組不變**(現有 3-/5-arg 呼叫全不動)。
    """
    t = gamedata.companions[companion_id]
    attack = dict(t["attack"])
    armor = t["armor_rating"]
    resist = dict(t.get("resist", {}))
    hp_bonus = max_health_bonus
    gear_weapon = None
    if char is not None:
        from tesrpg.systems import party
        dmg, wskill, gear_weapon = party.derived_weapon(char, gamedata, companion_id)
        attack["damage"], attack["skill"] = dmg, wskill
        if gear_weapon is not None:      # 裝上實體武器 → 基礎傷改物理(模板固有元素移除;武器自身元素附魔走附魔派發)
            attack.pop("element", None)
        armor, ar_resist = party.derived_armor(char, gamedata, companion_id, armor)
        for el, v in ar_resist.items():                 # 護甲抗元素附魔烘焙進 resist
            resist[el] = resist.get(el, 0) + v
    mx = t["max_health"] + hp_bonus
    hp = mx if current_hp is None else max(0, min(int(current_hp), mx))
    cre = Creature(
        template_id=companion_id, name=t["name"],
        strength=t["strength"], agility=t["agility"], speed=t["speed"],
        max_health=mx, health=hp, armor_rating=armor,
        attack=attack, loot_gold=[0, 0], loot_table=[],
        flavor=t.get("blurb", ""), danger=0, resist=resist,
        summon_turns=None,
    )
    if gear_weapon is not None:   # 附魔完全比照玩家:掛武器附魔載體 + 共享玩家充能池(武器是玩家的·借入同伴槽)
        cre._gear_weapon = gear_weapon
        cre.offhand = ""
        cre.enchant_charges = char.enchant_charges
    return cre


def alive_list(combatants: list) -> list:
    return [c for c in combatants if is_alive(c)]


TAUNT_AGGRO_CHANCE = 0.6   # R105 坦克召喚嘲諷:嘲諷中的召喚物吸引敵人火力的機率


def pick_player_side_target(player: Character, allies: list, rng: RNG):
    """敵人選擇攻擊我方目標:偏好玩家(約 55%),其餘平分給存活同伴。

    戰士「盾牆」嘲諷:玩家立盾牆時,把所有敵火力吸到坦身上(只護同袍 HP,不轉嫁傷害)。
    R105 坦克召喚「嘲諷」:場上有嘲諷中的盟友(魔人/魔靈伴)→ 機率把敵火力吸到它身上,掩護召喚主。"""
    living_allies = [a for a in allies if is_alive(a)]
    if has_shield_wall(player):          # 盾牆嘲諷:強制鎖定坦
        return player
    # 🔴 無嘲諷者 → taunters 空 → and 短路不擲 rng → 逐位元組同(sim 無盟友/一般同伴無 taunt)
    taunters = [a for a in living_allies
                if any(e.get("kind") == "taunt" and e.get("turns", 0) > 0 for e in getattr(a, "active_effects", []))]
    if taunters and rng.chance(TAUNT_AGGRO_CHANCE):
        return rng.choice(taunters)
    if not living_allies or rng.chance(0.55):
        return player
    return rng.choice(living_allies)


def spawn_boss(gamedata: GameData, template_id: str, rng: RNG, name: str | None = None) -> Creature:
    """地城首領:在模板基礎上強化生命與攻擊。"""
    cr = spawn_creature(gamedata, template_id, rng)
    cr.max_health = round(cr.max_health * 1.6)
    cr.health = cr.max_health
    cr.attack = dict(cr.attack)
    cr.attacks = [dict(a) for a in cr.attacks]   # 強化套到整個曲目(每招獨立 copy → 不動模板)
    for a in [cr.attack] + cr.attacks:
        a["damage"] = round(a["damage"] * 1.3)
        a["skill"] = min(100, a["skill"] + 15)
    cr.armor_rating += 6
    if name:
        cr.name = name
    return cr


# ======================================================================
# 攻擊曲目選招(怪物多攻擊模式)
# ======================================================================
ATTACK_COOLDOWN_MARKER = "atk_cooldown"   # 蓄力/大招冷卻:暫存 active_effects、由 tick_effects 每回合遞減(未知 kind → 靜默)


def _attack_on_cooldown(creature, name) -> bool:
    return any(e.get("kind") == ATTACK_COOLDOWN_MARKER and e.get("name") == name and e.get("turns", 0) > 0
               for e in creature.active_effects)


def _weighted_pick(items: list, rng: RNG):
    """依各條 `weight`(預設 1)加權隨機;零/負總權退化為均勻挑。"""
    total = sum(max(0.0, a.get("weight", 1)) for a in items)
    if total <= 0:
        return rng.choice(items)
    r = rng.random() * total
    upto = 0.0
    for a in items:
        upto += max(0.0, a.get("weight", 1))
        if r < upto:
            return a
    return items[-1]


def choose_attack(creature, rng: RNG, target=None) -> dict:
    """從怪物攻擊曲目 `attacks` 選一招:`when` 血量階段閘 + `cooldown` 蓄力冷卻 + `weight` 加權隨機。

    無 `attacks`(同伴/未配曲目的怪)→ 回後備單招 `creature.attack`(byte-identical,行為不變)。
    選到帶 cooldown 的招 → 推一條冷卻標記到 active_effects(由回合末 tick_effects 遞減)。"""
    reps = getattr(creature, "attacks", None)
    if not reps:
        return creature.attack
    hp_ratio = (creature.health / creature.max_health) if getattr(creature, "max_health", 0) else 1.0
    avail = []
    for a in reps:
        when = a.get("when")
        if when:
            if "hp_below" in when and hp_ratio >= when["hp_below"]:
                continue
            if "hp_above" in when and hp_ratio < when["hp_above"]:
                continue
        if a.get("cooldown") and _attack_on_cooldown(creature, a.get("name")):
            continue
        avail.append(a)
    if not avail:   # 全被 when/cooldown 濾掉 → 落回無階段限制者,再不行用後備單招
        avail = [a for a in reps if not a.get("when")] or [creature.attack]
    chosen = _weighted_pick(avail, rng)
    if chosen.get("cooldown"):
        creature.active_effects.append({"kind": ATTACK_COOLDOWN_MARKER,
                                        "name": chosen.get("name"), "turns": chosen["cooldown"]})
    return chosen


def choose_enemy_attack(creature, rng: RNG, target=None) -> dict:
    """敵方選招:同 choose_attack,但「嘲諷」招對敵方無意義(那是玩家召喚坦克的 R105 拉仇恨招,
    只有 run_battle 的**盟友**階段會解讀)→ 抽到即退回基礎單招。R134 起敵方可能使用玩家召喚模板
    (summoned_* 被 boss 召為爪牙),故需此防呆;無 taunt 招的怪 → 與 choose_attack 逐位元組同。"""
    atk = choose_attack(creature, rng, target)
    if atk and atk.get("taunt"):
        return creature.attack
    return atk


def try_boss_summon(boss, enemies: list, gamedata: GameData, rng: RNG) -> str | None:
    """R134 BOSS 召喚爪牙 —— **唯一決策點**(main.run_battle 與 sim_builds 共用,防語意漂移)。

    bestiary 可選 `summon` 譜:{"id": 爪牙模板, "wave": 每波隻數, "cap": 全場總量上限, "cooldown": 冷卻回合}。
    條件:冷卻到 + 場上無存活爪牙 + 未達總量 → 生成 wave 隻(標 `summoned=True`)append 進 enemies、
    回訊息(呼叫端以此**耗掉 boss 本回合攻擊** = mode A 自限);否則回 None(照常攻擊)。
    🔴 爪牙三重排除(使用者定案):擒魂 / 擊殺計數 / 戰利品 —— 由 run_battle 勝利結算讀 `summoned` 旗標。
    🔴 殺王=爪牙潰散(呼叫端 scatter);計數器 `_summon_cd/_summon_total` 為戰鬥暫態(不入檔,R03)。
    無 `summon` 譜 → 在任何 rng 消耗**之前**回 None → 既有怪 byte-identical。"""
    spec = gamedata.bestiary.get(getattr(boss, "template_id", ""), {}).get("summon")
    if not spec:
        return None
    cd = getattr(boss, "_summon_cd", 0)
    boss._summon_cd = cd - 1
    total = getattr(boss, "_summon_total", 0)
    cap = int(spec.get("cap", 6))
    if cd > 0 or total >= cap:
        return None
    if any(getattr(e, "summoned", False) and is_alive(e) for e in enemies):
        return None                       # 場上仍有存活爪牙 → 不重召(打完一波才有下一波)
    wave = min(int(spec.get("wave", 2)), cap - total)
    ids = spec.get("ids")                 # R135 隨機爪牙表(瘋神混沌):每隻獨立抽;僅 ids 分支耗 rng → 固定 id 譜 byte-identical
    adds = []
    for i in range(wave):
        cre = spawn_creature(gamedata, rng.choice(ids) if ids else spec["id"], rng)
        cre.summoned = True               # 戰鬥暫態旗標:勝利結算三重排除 + 潰散判定
        adds.append(cre)
    enemies.extend(adds)                  # 本回合即參戰(敵人階段迭代會走到)
    boss._summon_total = total + wave
    boss._summon_cd = int(spec.get("cooldown", 3))
    names = "、".join(a.name for a in adds)
    # R135 可選 msg 模板(增援風味:狼嚎/號角 ≠ 位面裂隙);預設=R134 原句 → 既有 18 譜逐字不變
    return spec.get("msg", "{name}撕開一道裂隙,喚出了{names}!").format(name=boss.name, names=names)


def scatter_orphan_summons(enemies: list, gamedata: GameData) -> bool:
    """R134 殺王=爪牙潰散:任一「有召喚譜的召主」死亡 → 其存活爪牙即刻潰散(自 enemies 移除,
    不進勝利結算 → 天然無戰利品/擒魂/擊殺計數)。無召主死亡或無存活爪牙 → False(無事)。
    ⚠ 無歸屬追蹤(潰散「全部」summoned):現行不變式=召主皆 solo(schema 測試守)→ 一場恰一名召主。
    若未來允許非 solo 召主 / 一場多召主,須加 ownership 標記,否則會誤散他人爪牙。"""
    summoner_dead = any(not is_alive(e) and gamedata.bestiary.get(e.template_id, {}).get("summon")
                        for e in enemies)
    if not summoner_dead:
        return False
    orphans = [e for e in enemies if getattr(e, "summoned", False) and is_alive(e)]
    for o in orphans:
        enemies.remove(o)
    return bool(orphans)


def random_encounter(gamedata: GameData, player_level: int, rng: RNG,
                     max_danger: int | None = None, biome: str | None = None) -> Creature:
    """依玩家等級加權抽一隻敵人(危險度越高越罕見);max_danger 限制最高危險度;
    biome 依當地生態調整各怪權重(在地怪常見、他鄉怪罕見,通用怪不受影響)。"""
    pool = []
    weights = []
    for tid, t in gamedata.bestiary.items():
        if t.get("min_level", 1) > player_level:
            continue
        if max_danger is not None and t.get("danger", 1) > max_danger:
            continue
        pool.append(tid)
        weights.append(_biome_weight(t, biome))
    if not pool:  # 後備:至少給最弱的
        pool, weights = ["giant_rat"], [1]
    # 以權重做加權隨機(不依賴 random.choices,維持 RNG 介面單純)
    total = sum(weights)
    r = rng.roll(0, total)
    acc = 0.0
    chosen = pool[-1]
    for tid, w in zip(pool, weights):
        acc += w
        if r <= acc:
            chosen = tid
            break
    return spawn_creature(gamedata, chosen, rng)


# ======================================================================
# 戰鬥資料存取(玩家 = Character、敵人 = Creature,以小工具統一讀取)
# ======================================================================
def _is_player(actor) -> bool:
    return isinstance(actor, Character)


def _name(actor) -> str:
    return actor.name


def _agility(actor) -> int:
    return actor.attr("agility") if _is_player(actor) else actor.agility


def _strength(actor) -> int:
    return actor.attr("strength") if _is_player(actor) else actor.strength


def _speed(actor) -> int:
    base = actor.attr("speed") if _is_player(actor) else actor.speed
    sf = magic.slow_factor(actor)        # 遲緩毒(R31):降先攻(僅影響行動順序,不碰傷害)
    return max(1, int(round(base * (1.0 - sf)))) if sf else base


def _is_beast(actor) -> bool:
    """玩家是否處於狼人獸形(讀快取布林,不需 state)。"""
    return _is_player(actor) and getattr(actor, "beast_form", False)


# R136 獵手之眼:「陷入頹勢」認定的控場狀態集(衰/踉/緩/凍麻/懼/麻痺;刻意不含 dot →
# 元素附魔/塗毒不可自我點燃 +20%,須真控場 → 與牽制射/踉蹌餘響成套的「壓制→處決」)
_EXPLOIT_KINDS = ("weaken", "stagger", "slow", "benumb", "fear", "paralyze")


def _self_empower(actor) -> float:
    """玩家「獸人狂暴/紅衛腎上腺」自身增傷(R61)。加在 power_bonus → 在偷襲倍率之後相加 →
    不餵偷襲爆發(守紅線),且整體流進 dmg → solo 偷襲夾仍夾。非玩家/無 buff → 0.0(sim byte-identical)。"""
    if not _is_player(actor):
        return 0.0
    return sum(e.get("magnitude", 0.0) for e in getattr(actor, "active_effects", [])
               if e.get("kind") == "berserk_buff" and e.get("turns", 0) > 0)


def _weapon_profile(actor, gamedata: GameData, attack: dict | None = None):
    """回傳 (weapon_damage, weapon_skill_level, weapon_skill_id|None)。

    attack:怪物的「選定招」(多攻擊模式);None → 用 actor.attack 後備(玩家側忽略)。"""
    if _is_player(actor):
        if _is_beast(actor):     # 獸形:以獸爪戰鬥,略過裝備武器/淬鍊/附魔(資料驅動讀 beast_claws)
            from tesrpg.systems import lycanthropy
            wp = gamedata.item(lycanthropy.BEAST_CLAW)
            return wp["damage"] + lycanthropy.claw_bonus(actor), actor.skill(wp["skill"]), wp["skill"]
        bw = next((e for e in actor.active_effects
                   if e.get("kind") == "bound_weapon" and e.get("turns", 0) > 0), None)
        if bw:   # 召喚「束縛兵刃」:取代裝備武器 → 固定傷害、用咒術技能、不吃淬鍊/附魔/塗毒/耐久(skill_id=None)
            bmul = 1.0 + mastery.bound_mastery_mod(actor, gamedata).get("dmg_bonus", 0.0)   # R106 束縛精通:傷害 +%(無里程碑→×1)
            return round(bw["magnitude"] * bmul), actor.skill("conjuration"), None
        gs = actor.equipped.get("shield")
        gsd = gamedata.item_or_none(gs) if gs else None
        if gsd and gsd.get("great_shield"):   # 雙手重盾占雙手 → 盾擊作戰(手持武器休眠);用 block 技、算物理、無附魔/塗毒/archetype
            return gsd.get("bash_damage", 0), actor.skill("block"), "block"
        wp = gamedata.item(actor.weapon)   # 用 item() 以支援附魔(合成)武器
        # 虎人利爪(R61):僅徒手(hand_to_hand)時加爪傷;匕首/blade 路徑永不觸發 → 不餵偷襲倍率、sim byte-identical
        claw = race_ability.claw_bonus(actor, gamedata) if wp["skill"] == "hand_to_hand" else 0
        return wp["damage"] + smithing.weapon_temper_bonus(actor, gamedata) + claw, actor.skill(wp["skill"]), wp["skill"]
    src = attack if attack is not None else actor.attack
    return src["damage"], src["skill"], None


def eff_weapon_id(player, gamedata: GameData | None = None) -> str:
    """玩家當前實際使用的武器 id(獸形 → beast_claws;雙手重盾 → 該盾〔盾擊〕;否則裝備武器)。"""
    from tesrpg.systems import lycanthropy
    if getattr(player, "beast_form", False):
        return lycanthropy.BEAST_CLAW
    gs = getattr(player, "equipped", {}).get("shield")
    if gamedata is not None and gs and (gamedata.item_or_none(gs) or {}).get("great_shield"):
        return gs   # 雙手重盾占雙手 → 以盾為「武器」(盾擊),手持武器休眠
    return player.weapon


def effective_weapon_name(player, gamedata: GameData) -> str:
    """玩家當前實際使用的武器名(獸形 → 獸爪;雙手重盾 → 盾;否則裝備武器)。供戰鬥/選單標籤。"""
    return gamedata.item(eff_weapon_id(player, gamedata))["name"]


def _armor_rating(actor, gamedata: GameData) -> int:
    if not _is_player(actor):
        # 同伴也吃 active_shield(盾牆護同袍光環 / 盟友指向護盾術才真生效);敵人無護盾效果 → +0 不變(sim 零位移)
        return actor.armor_rating + magic.active_shield(actor)
    if _is_beast(actor):     # 獸形:脫去穿戴護甲,只剩野獸厚皮的微薄防護(權衡:易受擊,靠巨量血量扛)
        from tesrpg.systems import lycanthropy
        return lycanthropy.BEAST_ARMOR
    worn = inventory.worn_armor_rating(actor, gamedata)
    wc = inventory.dominant_weight_class(actor, gamedata)
    if worn == 0 or wc is None:
        base = formulas.player_armor_rating(actor.skill("heavy_armor"), actor.skill("light_armor"))
    else:
        skill = actor.skill("heavy_armor" if wc == "heavy" else "light_armor")
        base = formulas.worn_armor_base(worn, skill)
    # 被動護甲(石膚/靈體護壁=法系、撐架/柔革護持=物理 stance):里程碑 perk,無條件生效
    # (廣度 pass 加入物理 stance 後不再綁法力;原「有法力才生效」對物理 stance 不合理)。
    passive = mastery.passive_armor_bonus(actor, gamedata)
    # R106C 亡者護甲:花 soul_token 買的永久全域護甲(獨立層·夾 NECRO_ARMOR_CAP·絕不寫 base;
    # necro_upgrades 空 → 0 → 刺客/非死靈師 byte-identical)
    from tesrpg.systems import necromancy
    return (base + passive + smithing.armor_temper_bonus(actor, gamedata) + magic.active_shield(actor)
            + necromancy.undead_armor_bonus(actor))   # 淬鍊 + 變化系護盾 + 亡者護甲疊加


def _player_armor_skill(actor, gamedata: GameData) -> str:
    """玩家被擊中時應鍛鍊的護甲技能(以穿戴的重/輕甲為準)。"""
    wc = inventory.dominant_weight_class(actor, gamedata)
    if wc == "heavy":
        return "heavy_armor"
    if wc == "light":
        return "light_armor"
    return max(formulas.ARMOR_SKILL_IDS, key=actor.skill)


def _fatigue_ratio(actor) -> float:
    if _is_player(actor) and actor.max_fatigue > 0:
        return actor.fatigue / actor.max_fatigue
    return 1.0


def _get_hp(actor) -> float:
    return actor.health


def _set_hp(actor, value: float) -> None:
    actor.health = max(0, value)


def is_alive(actor) -> bool:
    return _get_hp(actor) > 0


def _apply_dot_capped(target, eff) -> None:
    """對目標施加狀態效果;**dot 按元素設疊加上限**(防多次被擊時同元素 DoT 無限疊加→暴斃)。
    達 `formulas.DOT_STACK_CAP` 層時:新效果較強(magnitude×turns)→ 替換最弱同元素 dot,否則丟棄。
    非 dot(麻痺/恐懼等 binary 控場)照常 append。僅用於玩家受擊側;攻擊側 DoT 不經此(法術/塗毒照疊)。"""
    if eff.get("kind") == "dot":
        same = [e for e in target.active_effects
                if e.get("kind") == "dot" and e.get("element") == eff.get("element") and e.get("turns", 0) > 0]
        if len(same) >= formulas.DOT_STACK_CAP:
            weakest = min(same, key=lambda e: e.get("magnitude", 0) * e.get("turns", 0))
            if eff.get("magnitude", 0) * eff.get("turns", 0) > weakest.get("magnitude", 0) * weakest.get("turns", 0):
                target.active_effects.remove(weakest)
            else:
                return
    target.active_effects.append(eff)


def _apply_imbue_rider(defender, element, rider, gamedata, rng) -> None:
    """R149 元素刃招牌狀態:焰刃引燃(fire→burn DoT)/霜刃凍麻(frost→benumb 減命中)/
    雷刃踉蹌(shock→stagger)。命中時掛載,給戰法師「選哪一系刃」的戰術身份。
    比照附魔 rider 慣例:DoT 同源(imbue_dot)刷新取 max(免疊爆);控場走 apply_control(R44:
    solo 機率抵抗 + 同源去重防多刃疊),soft 控無 solo 免疫。rider 非 burst → 不碰 solo 偷襲夾。"""
    status = rider.get("status")
    if status == "dot":
        mag = max(1, int(rider.get("magnitude", 1)))
        turns = rider.get("turns", formulas.WEAPON_DOT_TURNS)
        existing = next((e for e in defender.active_effects
                         if e.get("kind") == "dot" and e.get("source") == "imbue_dot"
                         and e.get("element") == element), None)
        if existing:
            existing["turns"] = max(existing.get("turns", 0), turns)
            existing["magnitude"] = max(existing.get("magnitude", 0), mag)
        else:
            defender.active_effects.append({"kind": "dot", "element": element, "magnitude": mag,
                                            "turns": turns, "source": "imbue_dot"})
    elif status in ("benumb", "stagger", "weaken", "slow"):
        if rng.chance(rider.get("chance", 1.0)):
            magic.apply_control(defender, status, gamedata, rng,
                                magnitude=rider.get("magnitude", 0.0),
                                turns=rider.get("turns", 1), source=f"imbue_{element}")


def _is_solo(creature, gamedata: GameData) -> bool:
    """該防守單位是否為 BOSS 級(bestiary `solo`)→ 適用「偷襲開場一擊不可致死」夾限。"""
    tid = getattr(creature, "template_id", None)
    return bool(tid and gamedata.bestiary.get(tid, {}).get("solo"))


def _has_deathmark(creature) -> bool:
    """敵身上是否有刺客「致命烙印」(存敵方 active_effects,戰鬥邊界清)。"""
    return any(e.get("kind") == "deathmark" and e.get("turns", 0) > 0
               for e in getattr(creature, "active_effects", []))


def _offbalance_active(attacker, gamedata: GameData) -> bool:
    """徒手失衡是否啟用(R103):已解鎖里程碑(hand_to_hand≥25)且未穿重甲(輕裝武僧身份)。
    🔴 僅由 resolve_attack 的玩家徒手路徑呼叫(wpn_skill_id=="hand_to_hand"·not beast)→ sim 持匕首不觸及。"""
    return (mastery.has_offbalance_unlock(attacker, gamedata)
            and not inventory.wears_heavy_armor(attacker, gamedata))


def has_shield_wall(char) -> bool:
    """玩家是否處於戰士「盾牆」架勢(存 active_effects 的常駐 stance)。"""
    return any(e.get("kind") == "shield_wall" and e.get("turns", 0) > 0
               for e in getattr(char, "active_effects", []))


def has_guard_stance(char) -> bool:
    """R137 玩家是否處於「格擋姿態」(常駐 stance·取代整回合格擋動作):姿態中攻擊傷害
    ×GUARD_STANCE_DAMAGE_TAX,來襲物理傷害吃**純減傷**(_guard_stance_factor·乘性·不碰命中),
    被命中即可觸發 block 反擊樹與 block XP。🔴 刻意不給攻方命中懲罰 → 敵照常打中 →
    荊棘反傷流可常駐姿態(使用者拍板:姿態不得產生落空)。"""
    return any(e.get("kind") == "guard_stance" and e.get("turns", 0) > 0
               for e in getattr(char, "active_effects", []))


def _wields_great_shield(char, gamedata: GameData) -> bool:
    """是否裝備雙手重盾(None-safe;非玩家 equipped 缺欄 → False)。"""
    sh = getattr(char, "equipped", {}).get("shield")
    sd = gamedata.item_or_none(sh) if sh else None
    return bool(sd and sd.get("great_shield"))


def _guard_stance_factor(defender, atk_element=None, gamedata=None) -> float:
    """R137 格擋姿態「舉盾卸力」減傷倍率(<1.0=更耐打):乘性·隨 block 技能縮放、力竭整組暫停。
    物理全額卸力;**元素折半**(盾面卸得開刀劍、卸不全火焰 → 元素仍是盾系的相對剋星,
    且守終王包絡〔R134 拍板 720 達貢單人 0-8%〕不被生存堆疊突破)。非玩家/非姿態 → 1.0(byte-identical)。
    R138b 重盾「掩體」:持雙手重盾時元素卸力係數 0.5→0.70(乘在姿態卸力上;**使用者鐵令
    「現實邏輯優先——格擋不可能防元素比物理多」** → 元素永遠 ≤ 物理卸力,重盾只是折損較少)。
    gamedata=None(舊呼叫端/測試)→ 一律非重盾路徑。"""
    if not (_is_player(defender) and has_guard_stance(defender) and defender.fatigue > 0
            and not _is_beast(defender)):    # 審查修:獸形無盾 → 姿態卸力不套(鏡像重盾 _is_beast 閘)
        return 1.0
    if _overextended(defender):  # R191 搏命連斬:還擊期間門戶大開 → 姿態卸力不計(與力竭暫停對稱)
        return 1.0
    m = formulas.GUARD_STANCE_MITIGATION * min(1.0, defender.skill("block") / 100.0)
    m += divines.block_bonus(defender)   # R107 斯丹達爾之佑:原掛手動格擋(R137 移除)→ 遷入姿態卸力(+0.10)
    if atk_element:
        m *= (formulas.GREAT_SHIELD_ELEMENTAL_FACTOR
              if gamedata is not None and _wields_great_shield(defender, gamedata)
              else formulas.GUARD_STANCE_ELEMENTAL_FACTOR)
    return 1.0 - min(0.60, m)            # 防呆總夾(祝福/未來源疊加也不至近免傷)


def bunker_fatigue_regen(char, gamedata: GameData) -> int:
    """R138 重盾「掩體回氣」:格擋姿態+持重盾 → 每回合應回體力量(單一決策點,main 與 sim 共用)。
    🔴 刻意不 gate fatigue>0 —— 力竭時盾後喘息正是脫困路;+2 < 攻擊成本 ~4.2 → 邊打邊回不可能,
    力竭煞車(姿態效果暫停)仍咬合;站樁不打可持續回=零輸出雕像,自費時間非永動。非重盾/非姿態/獸形 → 0。"""
    if (_is_player(char) and has_guard_stance(char) and not _is_beast(char)
            and _wields_great_shield(char, gamedata)):
        return formulas.GREAT_SHIELD_BUNKER_FATIGUE
    return 0


def _shield_wall_factor(defender) -> float:
    """盾牆物理減傷倍率(<1.0 = 更耐打);非盾牆 → 1.0。"""
    e = next((e for e in getattr(defender, "active_effects", [])
              if e.get("kind") == "shield_wall" and e.get("turns", 0) > 0), None)
    if e and _overextended(defender):   # R191 搏命連斬:還擊期間門戶大開 → 盾牆卸力不計
        return 1.0
    return (1.0 - e.get("mitigation", 0.0)) if e else 1.0


def _consecration_factor(defender) -> float:
    """R122 聖騎士「聖化領域」:作用中的聖化光環 → 來襲傷害(物理+元素)乘性減免(<1.0 = 更耐打)。
    僅玩家(自我庇佑);非玩家/無光環 → 1.0(byte-identical:刺客/怪永不持此增益)。"""
    if not _is_player(defender):
        return 1.0
    e = next((e for e in getattr(defender, "active_effects", [])
              if e.get("kind") == "consecration" and e.get("turns", 0) > 0), None)
    return (1.0 - e.get("magnitude", 0.0)) if e else 1.0


def _great_shield_mitigation_factor(defender, gamedata: GameData) -> float:
    """雙手重盾被動物理減傷倍率(<1.0 = 更耐打);非重盾/獸形 → 1.0。讀裝備盾的 `mitigation` 欄。"""
    if not _is_player(defender) or _is_beast(defender):
        return 1.0
    sd = gamedata.item_or_none(defender.equipped.get("shield")) if defender.equipped.get("shield") else None
    return (1.0 - sd.get("mitigation", 0.0)) if (sd and sd.get("great_shield")) else 1.0


def initiative_order(player: Character, creature: Creature) -> list:
    """速度高者先行;同速玩家優先。"""
    return sorted([player, creature], key=lambda a: (_speed(a), _is_player(a)), reverse=True)


# ======================================================================
# 結算單次攻擊
# ======================================================================
def _ride_evasion(char) -> float:
    """騎射(獵馬戰技)賦予的臨時閃避(active_effect;與雜技/里程碑閃避聚合相加,不遮蔽)。"""
    return sum(e.get("evasion", 0.0) for e in getattr(char, "active_effects", [])
               if e.get("kind") == "ride_evasion" and e.get("turns", 0) > 0)


def _player_counter_damage(player, gamedata: GameData, rng: RNG) -> float:
    """玩家反擊基礎傷害(輕甲「迴身反打」/盾牌「完美格擋」):以當前武器一記普通攻擊估算,
    不吃偷襲倍率/流派加成 → 純基礎反擊,不觸碰 solo 紅線。"""
    wpn_dmg, wpn_skill, _ = _weapon_profile(player, gamedata)
    _lo = formulas.DAMAGE_ROLL_LO + formulas.luck_damage_floor(player.attr("luck"))   # 幸運抬下界(luck≤40 → 0.85 = byte-identical)
    return formulas.attack_damage(wpn_dmg, wpn_skill, _strength(player),
                                  rng.roll(_lo, formulas.DAMAGE_ROLL_HI), 1.0)


# ---- R186 幻影步(輕甲 100·afterimage):殘影蓄勢 / 殘影連襲 ----
# 殘影層是「戰鬥內」記帳:存成 active_effects 的 afterimage(stacks),與 cascade/guard_stance 同慣例 →
# 入戰/離戰整包清、不入存檔語意;層數歸零即移除(HUD 只在有層時顯示)。turns 用常駐哨兵 PERSISTENT_TURNS(不顯示回合數)。
# R188:戰鬥內「常駐」效果(格擋姿態/盾牆/戰旗/號令/殘影/氣勢)的 turns 哨兵。tick_effects 每回合 −1,
# 原本用 99 → ①HUD 第 2 回合起顯示「格擋姿態98」倒數(違反 _STANCE_MAINTAINED「不顯示回合數」本意)
# ②打滿 99 回合靜默失效。改大數後 ≥99 恆成立(HUD 不顯數字)、實務上永不過期;離戰一律 clear() 不殘留。
PERSISTENT_TURNS = 10 ** 6
_AFTERIMAGE_TURNS = PERSISTENT_TURNS


def _afterimage_eff(player):
    return next((e for e in player.active_effects if e.get("kind") == "afterimage"), None)


def afterimage_stacks(player) -> int:
    eff = _afterimage_eff(player)
    return eff["stacks"] if eff else 0


# ---- R187 解法二「氣勢」:殘影擊每記耗 1 點氣勢;開戰自帶 start 點,親手斬殺一名敵人 +per_kill(夾 max)----
# 為守終王牆(R186 殘影連襲對 solo 王/召喚爪牙的 solo 勝率提升超出牆):額外出手靠「斬獲」維持,久攻不下的巨物會耗盡。
# 存成玩家的戰鬥內 active_effect(kind=momentum);**不存在 = 本場尚未動用 = start 點**(懶建立 → 各 sim 迴圈免初始化);
# turns 用大數而非 99 哨兵:tick_effects 每回合 −1,過期就等於「不存在」= 白白回滿 start(原型實測踩過);
# run_battle 入戰/離戰 clear() 與 preserve_buffs 剝除 → 戰鬥邊界必歸零。召喚爪牙(R134·不計擊殺)斬之不回氣勢。
_MOMENTUM_TURNS = PERSISTENT_TURNS


def _momentum_eff(player):
    return next((e for e in player.active_effects if e.get("kind") == "momentum"), None)


def momentum_enabled(player, gamedata: GameData) -> bool:
    return bool(mastery.momentum(player, gamedata))


def momentum(player, gamedata: GameData) -> int:
    """目前氣勢點數(未選/未啟用 → 0)。純讀、零 rng。"""
    spec = mastery.momentum(player, gamedata)
    if not spec:
        return 0
    eff = _momentum_eff(player)
    return eff["stacks"] if eff else spec["start"]


def _momentum_set(player, gamedata: GameData, value: int) -> None:
    spec = mastery.momentum(player, gamedata)
    eff = _momentum_eff(player)
    if eff is None:
        eff = {"kind": "momentum", "stacks": spec["start"], "turns": _MOMENTUM_TURNS}
        player.active_effects.append(eff)
    eff["stacks"] = max(0, min(spec["max"], value))
    eff["turns"] = _MOMENTUM_TURNS


def momentum_reset(player, gamedata: GameData) -> None:
    """開戰重置為 start(run_battle 入戰呼叫 → HUD 一開場就看得到;sim 不呼叫也等同,因為「不存在 = start」)。"""
    spec = mastery.momentum(player, gamedata)
    if spec:
        player.active_effects[:] = [e for e in player.active_effects if e.get("kind") != "momentum"]
        _momentum_set(player, gamedata, spec["start"])


def _momentum_spend(player, gamedata: GameData) -> bool:
    """花 1 點氣勢出一記花招;未啟用 → 恆 True(行為同改前);氣勢為 0 → False(出不了手)。"""
    if not momentum_enabled(player, gamedata):
        return True
    cur = momentum(player, gamedata)
    if cur <= 0:
        return False
    _momentum_set(player, gamedata, cur - 1)
    return True


def momentum_on_kill(player, enemy, gamedata: GameData) -> None:
    """玩家親手斬殺一名敵人 → 氣勢 +per_kill(夾 max)。召喚爪牙(summoned·R134 不計擊殺)不回;未啟用 no-op。"""
    spec = mastery.momentum(player, gamedata)
    if not spec or getattr(enemy, "summoned", False):
        return
    _momentum_set(player, gamedata, momentum(player, gamedata) + spec["per_kill"])


def afterimage_gain(player, gamedata: GameData) -> None:
    """玩家閃過任何敵攻(含遠程/元素;與 R145 閃身反打「限物理近戰」不同)→ 凝一層殘影(夾 max_stacks)。
    無 afterimage 里程碑/穿重甲(R141)→ spec 為空 no-op。"""
    spec = mastery.afterimage(player, gamedata)
    if not spec:
        return
    eff = _afterimage_eff(player)
    if eff is None:
        eff = {"kind": "afterimage", "stacks": 0, "turns": _AFTERIMAGE_TURNS}
        player.active_effects.append(eff)
    eff["stacks"] = min(spec["max_stacks"], eff["stacks"] + 1)
    eff["turns"] = _AFTERIMAGE_TURNS


def afterimage_lose(player) -> None:
    """被命中(造成傷害)→ 殘影散去一層;歸零即移除效果。"""
    eff = _afterimage_eff(player)
    if eff is None:
        return
    eff["stacks"] -= 1
    if eff["stacks"] <= 0:
        player.active_effects.remove(eff)


def afterimage_ready(player, gamedata: GameData, n_alive: int) -> bool:
    """殘影連襲可用:殘影 ≥ min_stacks 且在場存活敵 ≥ min_foes(預設 1;資料可調成 2=單挑不開放)。
    選單與 sim 共用同一個閘,避免兩邊漂移。"""
    spec = mastery.afterimage(player, gamedata)
    return bool(spec and afterimage_stacks(player) >= spec["min_stacks"] and n_alive >= spec["min_foes"]
                and (not momentum_enabled(player, gamedata) or momentum(player, gamedata) > 0))   # R187:沒氣勢 → 連襲開不了(殘影留著)


def phantom_flurry_strikes(player, gamedata: GameData) -> int:
    """此刻殘影連襲實際會出手的記數:第一擊免費、其餘每記耗 1 點氣勢 → min(層數, 1+氣勢);未啟用氣勢 → 層數。
    選單標籤與戰報共用,避免高估(審查發現:原顯示「N 道殘影」但氣勢不足時實際出手較少)。"""
    n = afterimage_stacks(player)
    return min(n, 1 + momentum(player, gamedata)) if momentum_enabled(player, gamedata) else n


def phantom_flurry(player, foes, gamedata: GameData, rng: RNG, damage_mult=1.0):
    """殘影連襲(產生器,逐擊 yield resolve_attack 事件,呼叫端逐擊顯示;玩家倒下即停):
    耗盡全部殘影,每層對**當下最低血**的存活敵出手一記(殺死即轉下一個=集火)。整個動作只耗一次攻擊的體力。
    🔴 紅線:每擊 sneak_attack=False(普通擊,永不吃偷襲倍率 → 不碰 SOLO_SNEAK 夾)、武器傷 × strike_factor
    (走 damage_factor 車道,同 R136 箭雨)。damage_mult 供呼叫端疊 R137 格擋姿態攻擊稅(姿態不可免稅):
    可傳數值,或傳 callable(**在扣完體力之後**才求值,與普通攻擊「先耗體再算 _df()」同序——力竭時姿態稅整組暫停)。
    ⚠ 附魔元素傷/on-hit proc/雙持副手傷每擊各結算一次、不吃 strike_factor(`raw *= damage_factor` 在其之前;
    同箭雨既有行為,附魔流實得高於「武器傷八成」,見 R186 handoff)。武器不限:弓=連射、法杖=連擊(語意用「連擊」)。"""
    spec = mastery.afterimage(player, gamedata)
    eff = _afterimage_eff(player)
    if not spec or eff is None or eff["stacks"] < spec["min_stacks"]:
        return
    n = eff["stacks"]
    player.active_effects.remove(eff)             # 耗盡殘影(先移除再出手,途中被反傷打死也不留殘層)
    player_attack_cost(player, gamedata)
    mult = damage_mult() if callable(damage_mult) else damage_mult
    for i in range(n):
        alive = [e for e in foes if is_alive(e)]
        if not alive or not is_alive(player):
            return
        if i > 0 and not _momentum_spend(player, gamedata):   # R187 氣勢:第一擊=本體出手;其餘各層殘影擊各耗 1 點,耗盡即散
            return
        t = min(alive, key=lambda e: e.health)
        yield resolve_attack(player, t, gamedata, rng, sneak_attack=False,
                             damage_factor=spec["strike_factor"] * mult)


# ---- R187 借風騰挪(雜技 100 wind_step·misdirect):閃過敵攻 → 讓那一擊誤中另一名敵人 ----
def misdirect_redirect(player, attacker, foes, gamedata: GameData, rng: RNG, ev: dict, atk: dict | None):
    """敵方階段每次 `resolve_attack(attacker→player)` 之後呼叫(main/sim 共用;與 R152 狂亂同為「roster 層」處理,
    resolve_attack 不知道敵群)。落空(閃過)+ 有里程碑 + 場上另有存活敵 + 付得起體力 + 擲中機率 →
    attacker 以**同一招**再對隨機另一敵出手一記(damage_factor;走一般命中/元素抗性結算,**on_hit 狀態不上同伴**)。
    無里程碑/命中/無其他敵 → 在任何 rng 之前返回(既有構築 byte-identical)。回傳誤傷事件或 None。"""
    if ev.get("hit") or not is_alive(player):
        return None
    spec = mastery.misdirect(player, gamedata)
    if not spec or not is_alive(attacker):
        return None
    others = [f for f in foes if f is not attacker and is_alive(f)]
    if not others or player.fatigue < spec["fatigue_cost"]:
        return None
    if not rng.chance(spec["chance"]):
        return None
    player.fatigue = max(0, player.fatigue - spec["fatigue_cost"])
    victim = rng.choice(others)
    return resolve_attack(attacker, victim, gamedata, rng, attack=atk, damage_factor=spec["factor"])


def afflicted(target, kinds) -> bool:
    """R190 狀態讀取的**唯一入口**:目標此刻是否處於 kinds 內任一狀態。任何「對某狀態有加乘」的程式(獵手之眼、
    看破、日後新增者)一律呼叫本函式,**不得**自己掃 active_effects、不得讀來源或回合數。
    讀「實際狀態」或其「餘韻」(magic.apply_control 於成功施加/被去重時統一留下,見 magic.ECHO_KINDS):
    餘韻讓玩家階段 t1 控場(回合末即歸零)也能被下一擊讀到,與 t2+ 來源一致。
    🔴 本函式只供「加乘」讀取;命中減益/失能(magic.is_staggered 等實際效果)不得改走這裡。"""
    for e in getattr(target, "active_effects", []):
        if e.get("turns", 0) <= 0:
            continue
        k = e.get("kind")
        if k in kinds or (k == "echo" and e.get("of") in kinds):
            return True
    return False


# ---- R191 搏命連斬(blade_100 savage·`reckless` 子欄;使用者拍板「以攻對攻」,第二記係數 0.6)----
# 主動戰技(非被動數值):同一目標連斬 strikes 記(第 2 記起 ×factor),每記 sneak_attack=False(永不吃偷襲倍率 →
# 不碰 SOLO_SNEAK 夾)、照常吃護甲/物抗(走 resolve_attack,無任何穿透)。
# 代價:連斬後目標若沒倒下且能行動 → 立刻趁隙還擊你一記;這一記你的閃避歸零(閃過才有的閃身反打/殘影不觸發)、
# 格擋姿態/盾牆卸力與格擋反擊不計。其餘敵人不受影響(之後照常行動)。被恐懼/麻痺/狂亂的目標不還擊(沒有門戶可趁)。
# `overextended` 只存在於那一記還擊之內(加入 → resolve_attack → 移除):不跨回合、不入戰鬥內常駐、不需 PERSISTENT_TURNS;
# 萬一中途例外殘留,turns:1 會在回合尾 tick 掉。🔴 純讀 getter:未選/武器不符 → reckless_ready False、零 rng,既有構築 byte-identical。
def _overextended(char) -> bool:
    """玩家此刻是否處於「搏命後門戶大開」(只在敵人那一記還擊期間為真)。"""
    return any(e.get("kind") == "overextended" and e.get("turns", 0) > 0 for e in getattr(char, "active_effects", []))


def reckless_spec(player, gamedata: GameData) -> dict:
    """當前實際武器(獸形=獸爪/束縛兵刃=None/重盾=block)對應的搏命連斬參數;不適用 → {}。"""
    if not _is_player(player):
        return {}
    return mastery.reckless(player, gamedata, _weapon_profile(player, gamedata)[2])


def reckless_ready(player, gamedata: GameData) -> bool:
    """搏命連斬可用(選單與 sim 共用同一個閘):已選 + 持對應武器 + 體力付得起額外耗體。"""
    spec = reckless_spec(player, gamedata)
    return bool(spec) and player.fatigue >= spec["fatigue"]


def reckless_flurry(player, target, gamedata: GameData, rng: RNG, damage_mult=1.0):
    """搏命連斬(產生器,逐事件 yield ("strike"|"counter", event);呼叫端逐擊顯示)。
    damage_mult:同 phantom_flurry,可傳 callable(耗體之後才求值 → R137 姿態稅同普攻序)。"""
    spec = reckless_spec(player, gamedata)
    if not spec or not is_alive(target):
        return
    player_attack_cost(player, gamedata)
    player.fatigue = max(0, player.fatigue - spec["fatigue"])
    mult = damage_mult() if callable(damage_mult) else damage_mult
    for i in range(spec["strikes"]):
        if not is_alive(target) or not is_alive(player):
            break
        yield ("strike", resolve_attack(player, target, gamedata, rng, sneak_attack=False,
                                        damage_factor=(1.0 if i == 0 else spec["factor"]) * mult))
    if not is_alive(player):
        return
    if is_alive(target) and not magic.is_incapacitated(target) and not magic.is_frenzied(target):
        eff = {"kind": "overextended", "turns": 1}
        player.active_effects.append(eff)                       # 只在這一記還擊期間露出破綻
        try:
            atk = choose_enemy_attack(target, rng, player)
            ev = resolve_attack(target, player, gamedata, rng, attack=atk)
        finally:
            if eff in player.active_effects:
                player.active_effects.remove(eff)
        yield ("counter", ev)


def _gear_weapon_id(attacker):
    """攻擊者當前武器 id:玩家=裝備武器;同伴=生成時掛的 `_gear_weapon`;一般怪=None。"""
    return attacker.weapon if _is_player(attacker) else getattr(attacker, "_gear_weapon", None)


def _gear_weapon_item(attacker, gamedata: GameData):
    """攻擊者武器的 item dict(供附魔派發);無武器(一般怪/無裝同伴)→ None。
    🔴 玩家路徑回 `gamedata.item(attacker.weapon)`(玩家恆有武器 → 非 None)→ 附魔 gate 由 `_is_player(attacker)`
    改「(...) is not None」對玩家逐位元組同、對一般怪回 None 同 `_is_player`=False,對帶裝同伴新納入。"""
    wid = _gear_weapon_id(attacker)
    return gamedata.item(wid) if wid else None


def resolve_attack(attacker, defender, gamedata: GameData, rng: RNG,
                   defender_blocking: bool = False, sneak_attack: bool = False,
                   aimed: bool = False, mounted_charge: bool = False,
                   charge_spec: dict | None = None, attack: dict | None = None,
                   damage_factor: float = 1.0) -> dict:
    """attacker 攻擊 defender,套用傷害、發放玩家技能 xp。回傳事件 dict。

    sneak_attack:玩家開場偷襲(不察之敵)→ 傷害依潛行加倍、命中下限拉高、鍛鍊潛行。
    mounted_charge:坐騎「衝鋒」戰技(開場、僅野外遭遇)→ 長槍×高倍率 / 其他近戰追加坐騎踐踏;
    **絕不走 sneak_mult**(charge_spec 來自 mounts.charge_spec),對 solo boss 受獨立夾限。
    damage_factor(R136 箭雨):基礎武器傷害係數(<1=較弱的一箭);預設 1.0 → byte-identical。

    事件:{"attacker","defender","hit":bool,"damage":int,"blocked":bool,
           "skill_events":[...], "defender_dead":bool, "sneak":倍率|None}
    """
    # 怪物的「選定招」(多攻擊模式 R43):呼叫端傳入 choose_attack 的結果;未傳則用單招 attack 後備。
    # 玩家無 .attack → atk=None(下方所有 atk 讀取點皆已 None-guard 或在 not-player 區塊內)。
    atk = (attack if attack is not None else attacker.attack) if not _is_player(attacker) else None
    beast = _is_beast(attacker)     # 獸形:獸爪戰鬥,結構性略過裝備武器/附魔/淬鍊/副手/耐久
    # 召喚「束縛兵刃」:凝出的法系武器「完全取代」裝備武器(比照獸形)→ 不吃裝備武器的塗毒/命中附魔/
    # 耐久/副手/archetype/法杖命中回資源。存效果 dict(供下方 atk_element 取元素);無則 None。
    bound = (next((e for e in attacker.active_effects
                   if e.get("kind") == "bound_weapon" and e.get("turns", 0) > 0), None)
             if _is_player(attacker) and not beast else None)
    # 🔴 紅線:獸形攻擊永不吃偷襲倍率(防禦縱深 —— 即便呼叫端誤傳 sneak_attack=True 亦然;
    # 變身破壞潛行 → solo boss 反一刀夾限不被觸碰)
    sneaking = sneak_attack and _is_player(attacker) and not beast
    # 雙手重盾:以盾擊作戰,手持武器戰中休眠(比照束縛兵刃,完全取代武器 → 無 archetype 破甲/控制、無附魔/塗毒)。
    great = (inventory.is_great_shield(gamedata, attacker.equipped.get("shield"))
             if _is_player(attacker) and not beast and not bound else False)
    wpn_dmg, wpn_skill, wpn_skill_id = _weapon_profile(attacker, gamedata, atk)
    # 雙持副手傷害另計:作為一記「普通補刀」疊上,不吃偷襲倍率(避免偷襲秒精英)。獸形/束縛兵刃無副手。
    offhand_dmg = (inventory.dual_wield_bonus_damage(attacker, gamedata)
                   if _is_player(attacker) and not beast and not bound else 0.0)
    # 副手匕首的附魔(元素/吸血/麻痺/再生)也活,但以 OFFHAND_DAMAGE_FACTOR(0.6)權重生效並與主手疊加
    # (與副手補刀傷害同一個折扣;非雙持為 None)。
    offhand_ench = (gamedata.item(attacker.offhand).get("enchant")
                    if offhand_dmg and getattr(attacker, "offhand", "") else None)
    wdef = gamedata.item(attacker.weapon) if _is_player(attacker) and not beast and not bound and not great else None
    # R106 束縛兵刃 archetype 差異化:束縛以自身 archetype 取得原型身份(釘錘擊暈等·軟控只在下方 stagger 分支用;
    # 破甲對元素束縛無意義走元素分支略過);舊 bound_sword 無 archetype → None → 行為不變。
    archetype = (bound.get("archetype") if bound else (wdef.get("archetype") if wdef else None))
    speed = wdef.get("speed", formulas.WEAPON_SPEED_DEFAULT) if wdef else formulas.WEAPON_SPEED_DEFAULT
    fr = _fatigue_ratio(attacker)
    evasion = (formulas.dodge_evasion(defender.skill("acrobatics"))
               + mastery.evasion_bonus(defender, gamedata)
               + formulas.agility_evasion(_agility(defender))   # R63 敏捷第二段:過 100 漸近 +0.12(命中下夾 0.05 仍在)
               + _ride_evasion(defender)) if _is_player(defender) else 0.0   # 騎射閃避:聚合相加,不遮蔽
    if evasion and defender.fatigue <= 0:
        evasion *= 0.5   # R141 現實邏輯:力竭懲罰也打防端 —— 腿軟閃不動(原只罰攻/施法)
    _ovx = _is_player(defender) and _overextended(defender)   # R191 搏命連斬:還擊期間門戶大開(純讀;無效果 → False)
    if _ovx:
        evasion = 0.0    # 來不及閃(只歸零玩家自己的閃避;命中上下限不動)
    block_pen = mastery.block_hit_penalty(defender, gamedata) if defender_blocking else formulas.BLOCK_HIT_PENALTY
    chance = formulas.hit_chance(wpn_skill, _agility(attacker), _agility(defender),
                                 fr, defender_blocking, defender_evasion=evasion,
                                 block_penalty=block_pen)
    wmod = mastery.weapon_mod(attacker, gamedata, wpn_skill_id) if _is_player(attacker) else {}
    if _is_player(attacker):    # 武器速度:快武器更易命中、慢武器較難
        chance = max(0.05, min(0.95, chance + formulas.weapon_speed_hit(speed)))
    if wmod.get("hit"):         # 里程碑武器流派:命中加成(命中非傷害,不破偷襲紅線)
        chance = max(0.05, min(0.95, chance + wmod["hit"]))
    if aimed:                   # 弓手「瞄準射」:蓄力強擊命中加成
        chance = max(0.05, min(0.95, chance + formulas.AIMED_SHOT_HIT))
    if magic.is_staggered(attacker):   # 暗殺殘響:陣腳大亂的單位本回合更難命中
        chance = max(0.05, chance - formulas.STAGGER_HIT_PENALTY)
    if magic.is_slowed(attacker):      # 遲緩毒/負重(R31/R118):遲鈍 → 命中下降(magnitude 縮放·疊踉蹌各自夾 0.05)
        chance = max(0.05, chance - formulas.slow_hit_penalty(magic.slow_factor(attacker)))
    if (benumb := magic.benumb_hit_penalty(attacker)):   # 凍麻(冰系法術控場):純減命中(magnitude 驅動,各自夾 0.05)
        chance = max(0.05, chance - benumb)
    if sneaking:
        chance = max(chance, formulas.SNEAK_ATTACK_HIT_FLOOR)
    skill_events: list[dict] = []
    hit = rng.chance(chance)
    dmg_done = 0
    absorbed = False
    status_applied = None
    poison_applied = None
    self_restored = None
    infected = False
    infect_kind = None     # 傳染的詛咒種類("vampire"/"lycanthropy"/"disease"),供 run_battle 分派
    disease_id = None      # R53:普通病感染的病種 id(僅 infect_kind=="disease" 時有值)
    lifesteal = 0          # 武器吸血附魔本擊回血量(供敘事)
    aftermath = None
    sneak_mult = (formulas.sneak_attack_multiplier(attacker.skill("sneak"))
                  * formulas.archetype_sneak_bonus(archetype)
                  * formulas.night_mother_sneak_bonus(attacker.factions.get("dark_brotherhood", -1))
                  * (1 + mastery.sneak_mult_bonus(attacker, gamedata))   # 里程碑「影刃」:apex 偷襲倍率
                  * formulas.armor_sneak_mult_factor(inventory.armor_worn_weight(attacker, gamedata),
                                                     mastery.armor_sneak_relief(attacker, gamedata))  # R70 重甲爆發打折(W=0 起罰);R72 里程碑「無聲披掛」relief 對稱免之
                  ) if sneaking else None

    if hit:
        # 秩序之劍(賈格拉格神器)order 附魔:移除傷害變異,永遠取最大 roll(反 Wabbajack;R48)。
        # 僅玩家裝備武器(非獸形/束縛/重盾)且 enchant.kind=="order" 時生效 → sim 持匕首走 else、rng 序不變。
        # always-max 流進 attack_damage,在 solo 偷襲夾之前;sword archetype 偷襲 ×1.0 → 永不破 solo 夾。
        if (_is_player(attacker) and not beast and not bound and not great
                and (gamedata.item(attacker.weapon).get("enchant") or {}).get("kind") == "order"):
            roll = formulas.DAMAGE_ROLL_HI
        else:
            _lo = formulas.DAMAGE_ROLL_LO
            if _is_player(attacker):   # 幸運「天命」抬傷害骰下界(少壞骰·上界不動;luck≤40 → +0 → rng 序不變 = byte-identical)
                _lo += formulas.luck_damage_floor(attacker.attr("luck"))
            roll = rng.roll(_lo, formulas.DAMAGE_ROLL_HI)
        block_factor = (formulas.block_damage_factor(defender.skill("block"))
                        if defender_blocking else 1.0)
        # R107 斯丹達爾之佑:格擋減傷加成(僅玩家防守側;無祝福 → _db=0 不進分支 = byte-identical;
        # floor 防疊到近免傷。反傷流 raw/block_factor 讀同值 → 下游自動一致)
        if defender_blocking and _is_player(defender):
            _db = divines.block_bonus(defender)
            if _db:
                block_factor = max(divines.BLOCK_FLOOR, block_factor - _db)
        raw = formulas.attack_damage(wpn_dmg, wpn_skill, _strength(attacker),
                                     roll, block_factor)
        raw *= damage_factor    # R136 箭雨:齊射每箭較弱(預設 1.0 → byte-identical)。⚠ 只縮武器傷車道
        # (raw 及其衍生 power_bonus/exploit);附魔 weapon_element / 灌注 / 共鳴的 flat 加傷在後段、不縮 →
        # 附魔弓箭雨對每個目標仍送全額元素傷(審查 F2 記載·非偷襲車道無紅線·量測留待群戰 sim 場景)。
        # 號令/戰旗等 empower 增益的攻擊者(同伴)傷害提升 —— **只對同伴施放 → 永不碰玩家偷襲紅線**
        # 多源**遞減疊加曲線**(降序:最強×1 + 次強×0.7 + 第三×0.49…):戰旗+號令可同時生效又不暴衝
        # (上限 ≈3.33×最強;單道時等同舊行為 = 不變 → solo/單光環 byte-identical)。
        if not _is_player(attacker):
            mags = sorted((e.get("magnitude", 0) for e in getattr(attacker, "active_effects", [])
                           if e.get("kind") == "empower" and e.get("turns", 0) > 0), reverse=True)
            emp = sum(m * (formulas.EMPOWER_STACK_RATIO ** i) for i, m in enumerate(mags))
            if emp:
                raw *= (1 + emp)
        # 里程碑武器威力 + 弓手「瞄準射」:補傷「不吃偷襲倍率」(同副手補刀模式,守紅線;仍受 solo 夾限)
        power_bonus = raw * (wmod.get("power", 0.0) + (formulas.AIMED_SHOT_POWER if aimed else 0.0))
        # R136 獵手之眼(marksman_100):目標陷入頹勢(控場狀態)→ 乘勢補傷(同 power_bonus 車道守紅線;
        # 非弓手/未選 exploit=0 → 不掃 → byte-identical)
        # R189 刀劍「看破」(blade_100 precision):同引擎,選項自帶頹勢集 exploit_kinds=["stagger"](只認踉蹌);
        # 未帶 exploit_kinds → 弓手原六態。R190:一律走 afflicted()(實際狀態或餘韻),對各來源一致。
        if wmod.get("exploit"):
            if afflicted(defender, wmod.get("exploit_kinds") or _EXPLOIT_KINDS):
                power_bonus += raw * wmod["exploit"]
        _se = _self_empower(attacker)   # 種族「狂暴/腎上腺」自身增傷(R61):同 power_bonus 模式,偷襲倍率後加 → 守紅線
        if _se:
            power_bonus += raw * _se
        # 坐騎「衝鋒」:長槍藉馬勢洞穿(武器傷×高倍率)/ 其他近戰追加坐騎踐踏(flat)。不吃偷襲倍率(charge≠sneak)。
        if mounted_charge and not beast and not bound and charge_spec:
            if archetype == "spear":
                power_bonus += raw * (charge_spec.get("mult_spear", 1.0) - 1.0)
            else:
                power_bonus += charge_spec.get("mount_dmg", 0)
        if sneaking:
            raw *= sneak_mult
        raw += power_bonus
        if offhand_dmg:    # 雙持副手補刀:照常吃技能/力量,但不吃偷襲倍率
            raw += formulas.attack_damage(offhand_dmg, wpn_skill, _strength(attacker),
                                          roll, block_factor)
        atk_element = atk.get("element") if atk else None
        if bound:   # 召喚「束縛兵刃」:法系近戰 → 走元素分支(無視護甲、吃元素抗性;元素分支不讀附魔/灌注 → 不雙吃)
            atk_element = bound.get("element", "magic")
        raw *= magic.weaken_factor(attacker)            # 衰弱:攻方傷害打折(玩家/怪皆適用 R43;無衰弱→×1 byte-identical)
        raw *= getattr(attacker, "summon_power", 1.0)   # R105 召喚物傷害隨召喚主 conjuration 威力成長(非召喚者無此屬性 → ×1.0 byte-identical)

        if atk_element:
            # 元素攻擊:無視物理護甲,改吃元素抗性;巨魔像座可吸收為法力
            if _is_player(defender) and defender.birthsign == "atronach" and rng.chance(0.5):
                gain = int(round(raw))
                defender.magicka = min(defender.max_magicka, defender.magicka + gain)
                absorbed = True
                dmg = 0.0
            elif (_is_player(defender)
                  and (_ds := race_ability.dragonskin_chance(defender, gamedata)) > 0
                  and rng.chance(_ds)):
                # 布萊頓龍皮(R61):來襲元素/魔法吸收為法力(比照巨魔像座)。
                # 🔴 非布萊頓 _ds=0 → `> 0` 短路 → 永不擲 rng → sim(虎人)byte-identical。
                gain = int(round(raw))
                defender.magicka = min(defender.max_magicka, defender.magicka + gain)
                absorbed = True
                dmg = 0.0
            else:
                mult = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), atk_element)
                dmg = magic._scaled_damage(raw, mult)
                if _is_player(defender):   # 神秘「結界」:先吃法術/元素傷,吸魔結界按吸收量回魔(可耗盡池)
                    dmg, refunded = magic.consume_ward(defender, dmg)
                    if refunded:
                        defender.magicka = min(defender.max_magicka, defender.magicka + refunded)
        else:
            # 刺客「致命烙印」破甲:🔴 只在 follow-up(非開場偷襲)生效 → 開場一擊永不受惠 → solo 反一刀夾限不被繞過
            dm_pen = 0.0
            if _is_player(attacker) and not sneaking and _has_deathmark(defender):
                dm = mastery.deathmark(attacker, gamedata)
                dm_pen = dm.get("pen", 0.0) if dm else 0.0
            pen = min(0.85, formulas.archetype_armor_pen(archetype) + wmod.get("pen", 0)
                      + (formulas.AIMED_SHOT_PEN if aimed else 0.0) + dm_pen)   # 鈍器破甲 + 里程碑穿甲 + 瞄準射 + 烙印
            dmg = formulas.damage_after_armor(raw, _armor_rating(defender, gamedata), pen)
            # R127 物理抗性:護甲之外的乘性物理減傷層,**pen 完全無法穿透**(抗性層非護甲層 → 封 2H 破甲流繞牆)。
            # 補完抗性系統(物理原是唯一無抗性軸的傷害類型)。玩家側夾 PLAYER_PHYSICAL_RESIST_CAP=25(附魔/藥/誓福
            # 堆滿仍夾)。⚠ 此夾**軟化**但不消除 R71「群戰須具真實風險」:apex 潛行滿物抗時 4-bandit 死亡 ~60%→~25%、
            # 2b2w ~41%→~12%(使用者拍板「中等 cap 25%」知情接受;sim_assassin `physical_resist_cap` 場景守此數不再惡化)。
            # boss 的高物抗不受此夾(_is_player gate)。🔴 無物抗實體(既有怪 + 未附魔玩家)→ phys_r=0 → ×1.0 → byte-identical。
            phys_r = magic.entity_resist(defender, gamedata).get("physical", 0)
            if _is_player(defender):
                phys_r = min(formulas.PLAYER_PHYSICAL_RESIST_CAP, phys_r)
            dmg *= formulas.resist_multiplier({"physical": phys_r}, "physical")
            dmg *= mastery.incoming_physical_factor(defender, gamedata)   # 里程碑「壁壘」:物理再減傷
            dmg *= _shield_wall_factor(defender)            # 戰士「盾牆」架勢:物理再減傷(僅物理,元素穿透)
            dmg *= _great_shield_mitigation_factor(defender, gamedata)   # 雙手重盾被動物理減傷(乘性疊加,僅物理)
            # 徒手失衡 ramp:對已失衡之敵,(非偷襲)徒手傷害隨層數放大(讀本擊「前」層數=敵原已失衡)。
            # 🔴 not sneaking → 永不放大偷襲(守 R61 + solo 偷襲夾);徒手專屬+player+非獸形 → sim 持匕首 byte-identical。
            # R103:失衡須里程碑解鎖(hand_to_hand≥25)且未穿重甲;重甲/未解鎖時 stacks 恆 0,此處 ×1.0(冗餘但對稱明確)。
            if (_is_player(attacker) and wpn_skill_id == "hand_to_hand" and not beast and not sneaking
                    and _offbalance_active(attacker, gamedata)):
                dmg *= formulas.offbalance_damage_multiplier(magic.offbalance_stacks(defender))
            # 武器附魔:額外元素傷害(無視護甲,受對方元素抗性)。獸形/重盾盾擊以非裝備武器戰鬥 → 無附魔。
            # 同伴深化:gate 由 `_is_player` 改讀 `_gear_weapon_item`(玩家 byte-identical·帶裝同伴納入·一般怪 None 略過)。
            if not beast and not great and (_ewi := _gear_weapon_item(attacker, gamedata)) is not None:
                ench = _ewi.get("enchant")
                # 嗜血怒擊 berserk:依攻方已損生命比例提傷(滿血=×1 → 開場偷襲不放大);
                # 乘在物理 dmg、於 solo 偷襲/衝鋒夾限之前 → solo boss 仍受夾、守紅線。
                if ench and ench.get("kind") == "berserk":
                    dmg *= formulas.berserk_factor(attacker, ench.get("magnitude", 0))
                if ench and ench.get("kind") == "weapon_element":
                    em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), ench["element"])
                    dmg += magic._scaled_damage(ench["magnitude"], em)
                # 雙持副手的元素附魔:同樣無視護甲、吃元素抗性,但以 ×0.6 權重疊上(夾限前 → 偷襲不放大、solo 受夾)
                if offhand_ench and offhand_ench.get("kind") == "weapon_element":
                    em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), offhand_ench["element"])
                    dmg += magic._scaled_damage(offhand_ench["magnitude"] * formulas.OFFHAND_DAMAGE_FACTOR, em)
                # 戰法師「奧術灌注」:active weapon_imbue 自我增益 → 近戰加元素傷害
                # (加在 dmg、於 solo 偷襲夾限之前 → 偷襲不放大、solo boss 受夾,守紅線)
                for ie in attacker.active_effects:
                    if ie.get("kind") == "weapon_imbue" and ie.get("turns", 0) > 0:
                        em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), ie["element"])
                        dmg += magic._scaled_damage(ie["magnitude"], em)
                        # R149 元素刃招牌狀態:焰刃引燃(DoT)/霜刃凍麻(benumb)/雷刃踉蹌(stagger)——
                        # 給「選哪一系刃」的戰術身份;比照附魔 rider(同源去重、控場走 apply_control R44)。
                        # rider 非 burst(DoT 吃抗性/控場零傷)→ 不碰 solo 偷襲夾與終王輸出牆。
                        if ie.get("rider"):
                            _apply_imbue_rider(defender, ie["element"], ie["rider"], gamedata, rng)
                # 戰法師「共鳴一擊」:消耗 resonance → 加元素傷 + 引燃同系 DoT(同位置,夾限前;單次用後移除)
                for ie in list(attacker.active_effects):
                    if ie.get("kind") == "resonance" and ie.get("turns", 0) > 0:
                        em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), ie["element"])
                        dmg += magic._scaled_damage(ie["magnitude"], em)
                        defender.active_effects.append({"kind": "dot", "element": ie["element"],
                                                        "magnitude": ie.get("dot_magnitude", 4),
                                                        "turns": ie.get("dot_turns", 3)})
                        attacker.active_effects.remove(ie)
                        break

        # R122 聖騎士「聖化領域」:玩家的聖化光環對來襲傷害(物理+元素皆已匯入 dmg)乘性減免。
        # 置於物理/元素分支之後 → 兩路皆減;gated _is_player(defender) → 刺客/怪永不持此增益 → byte-identical。
        dmg *= _consecration_factor(defender)
        # R137 格擋姿態「舉盾卸力」:同聖化車道位置(物理+元素皆減),但**元素折半**
        # (盾卸不全火焰 → 元素仍剋盾系·守終王包絡;反擊樹另行物理限定守 R127 牆)。
        # R138b:持雙手重盾時元素卸力係數 0.5→0.70(乘在姿態卸力上·元素恆 ≤ 物理;見 _guard_stance_factor)。
        dmg *= _guard_stance_factor(defender, atk_element, gamedata)

        # solo BOSS 反一刀:偷襲開場單擊夾在生命上限的固定比例 → 絕不一刀秒 boss
        # (apex 仍可隱遁循環無傷清,但須多刀;精英/小遭遇不受影響)。
        if sneaking and not _is_player(defender) and _is_solo(defender, gamedata):
            cap = (getattr(defender, "max_health", 0) or _get_hp(defender)) * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO
            dmg = min(dmg, cap)
        # 坐騎衝鋒反一刀:衝鋒(尤其長槍×高倍率)對 solo boss 的單擊夾在生命上限比例 → 開場一擊不秒王。
        # 獨立於偷襲夾(衝鋒不走 sneak_mult);僅針對 solo,精英/小遭遇不受影響。
        if mounted_charge and not _is_player(defender) and _is_solo(defender, gamedata):
            cap = (getattr(defender, "max_health", 0) or _get_hp(defender)) * formulas.MOUNTED_CHARGE_DAMAGE_CAP_RATIO
            dmg = min(dmg, cap)
        dmg_done = int(round(dmg))
        _set_hp(defender, _get_hp(defender) - dmg_done)
        if _is_player(attacker) and not is_alive(defender):   # R187 氣勢:親手斬殺回氣勢(未啟用/爪牙 → no-op·零 rng)
            momentum_on_kill(attacker, defender, gamedata)

        # 里程碑「沉勁揮擊」(blunt_50 heavy_swing)反作用:造成傷害的一部分回噬自身(代價,不致死 → 夾 ≥1)
        # (R191 起刀劍 100 savage 改成主動戰技搏命連斬,不再走 recoil;recoil 只剩沉勁揮擊)
        if _is_player(attacker) and wmod.get("recoil") and dmg_done > 0:
            attacker.health = max(1, attacker.health - int(round(dmg_done * wmod["recoil"])))

        # 里程碑「重甲反震/重壓 + 格擋盾反」:玩家受物理擊中 → 反彈傷害 + 機率震開攻擊者(只物理;攻擊者可被反殺)
        # R145 現實邏輯:`ranged` 攻擊(弩矢/投石)無身體接觸 → 反傷/反震全套不觸發(荊棘反彈不了 30 呎外的弩手)。
        if _is_player(defender) and not atk_element and dmg_done > 0 and not (atk or {}).get("ranged"):
            # 反傷流(R42):吃「攻方完整物理輸出(連格擋前)」= raw / block_factor → 解耦護甲/盾牆/重盾/格擋,
            # 讓龜也能反出有意義的傷。物理限定(元素穿透不反)+ player-only(直接扣血、非遞迴 → 無 A→B→A 環)。
            # 來源相加:重甲反震 0.06 + 荊棘附魔(盔/胸/手/靴/盾·1%/靈魂階)+ 盾反 0.10(耗體 10、力竭則不計)。
            base = raw / block_factor if block_factor else raw
            # R141 現實邏輯 gate:重甲反震/重壓要真的穿著重甲、盾反要真的持盾(裸身沒有可反震的厚甲)。
            _heavy = inventory.wears_heavy_armor(defender, gamedata)
            ratio = ((mastery.armor_reflect(defender, gamedata) if _heavy else 0.0)
                     + inventory.thorns_reflect(defender, gamedata))
            br = mastery.block_reflect(defender, gamedata)
            if br and defender.equipped.get("shield") and defender.fatigue >= br["fatigue"]:
                defender.fatigue = max(0, defender.fatigue - br["fatigue"])
                ratio += br["reflect"]
            if ratio:
                _set_hp(attacker, _get_hp(attacker) - int(round(base * ratio)))
            st = mastery.armor_stagger(defender, gamedata) if _heavy else 0.0
            if st and is_alive(attacker) and rng.chance(st):
                # turns:2 → 撐過本回合末 tick,於攻擊者「下一次出手」時仍踉蹌生效(防守側反制的正確時序)
                magic.apply_control(attacker, "stagger", gamedata, rng, turns=2)   # R44:集中 helper
            # 變化「破盾反震/石膚反擊」(R118):有作用中護膚盾時被物理擊中 → 機率震開攻方。
            # 🔴 gate `active_shield>0`(須維持 flesh)+ 短路(sr==0 或無盾 → 不擲 rng → 刺客/無此里程碑 byte-identical)。
            sr = mastery.shield_recoil(defender, gamedata)
            if sr and magic.active_shield(defender) > 0 and is_alive(attacker) and rng.chance(sr):
                magic.apply_control(attacker, "stagger", gamedata, rng, turns=2)

        # 敵方反傷(R117):防守方為帶 `reflect` 的怪(如秩序騎士「灰潮的反噬」)→ 玩家物理擊中時,其
        # **完整物理輸出** base=raw/block_factor(**含偷襲倍率·pre solo-cap** → 懲罰爆發/秒殺者最重)按 reflect 比例回噬玩家。
        # 🔴 物理限定(元素/火法師=剋星穿透不反·對稱 R42 元素 boss 反傷免疫)+ 直接扣血非遞迴(不觸發玩家自身 thorns → 無 A→B→A 環)
        #    + 可致死(_set_hp clamp 0);reflect==0 的怪(全既有怪)→ 短路不動 = byte-identical。
        if _is_player(attacker) and not atk_element and dmg_done > 0:
            _refl = getattr(defender, "reflect", 0.0)
            if _refl:
                _rbase = raw / block_factor if block_factor else raw
                _set_hp(attacker, _get_hp(attacker) - int(round(_rbase * _refl)))

        # 法杖等「命中回復施術者資源」(D:on_hit_self)→ 由後面的 clamp_resources 夾限
        if _is_player(attacker) and wdef and wdef.get("on_hit_self"):
            ohs = wdef["on_hit_self"]
            setattr(attacker, ohs["stat"], getattr(attacker, ohs["stat"]) + ohs["magnitude"])
            self_restored = (ohs["stat"], ohs["magnitude"])
        # 戰法師「法力回擊」:近戰命中回魔(純資源、零傷害 → 零紅線;clamp_resources 夾上限)。
        # 不沿用 self_restored(那是法杖專屬敘事「法杖將生機回流」)→ 無杖揮劍回魔時不誤報法杖;法力條自會上升。
        if _is_player(attacker) and not beast:
            mox = mastery.mana_on_hit(attacker, gamedata)
            if mox:
                attacker.magicka = attacker.magicka + mox

        # 怪物攻擊的觸發狀態(中毒/凍傷/控場)→ 加到防守方身上(R43 放寬:不再只 dot,支援控場 kind)
        # 防禦雙軌:① on_hit 整段在 `if hit:` 內 → 落空即連控帶傷全免(閃躲/格擋第一道);
        #          ② fear/paralyze 命中後再吃 resisted_mind(willpower)第二道;軟控命中即中。
        # R105:召喚物(summon_turns 標記)攻擊敵人時也施加自身 on_hit(元素被動:火灼燒/冰凍麻/雷踉蹌);
        # 🔴 怪物→一般同伴仍不觸發(僅 summon 或 →玩家)→ 不改既有 monster→ally 行為·sim 無召喚故 byte-identical。
        if not _is_player(attacker) and (_is_player(defender) or getattr(attacker, "summon_turns", None) is not None):
            oh = atk.get("on_hit")
            if oh and rng.chance(oh.get("chance", 1.0)):
                st = oh["status"]
                if st == "dot":
                    _apply_dot_capped(defender, {"kind": "dot", "element": oh.get("element"),
                                                 "magnitude": oh["magnitude"], "turns": oh["turns"]})
                    status_applied = oh.get("element")
                # 控場 → 集中 helper(R44:玩家 willpower 抗硬控 + 去重,移入 apply_control)
                # R181 回合照字面:`turns: N` = 持有者的 N 個行動。怪物在敵人階段施加,回合末 tick 就 −1,
                # 玩家不會在下次行動前見到 → t1 恐懼/麻痺/踉蹌永遠不生效、t2 衰弱/遲緩/凍麻只剩 1 回合。
                # 故對**玩家**施加時 +1(施加端補償,去重照擋 → 連續損失上限 1;dot 逐回合結算不補)。
                # 召喚物→敵人在同伴階段施加(玩家階段之後、敵人階段之前)→ 回合末 tick 後仍完整 N 回合,不補。
                elif magic.apply_control(defender, st, gamedata, rng,
                                         magnitude=oh.get("magnitude", 0.0),
                                         turns=oh["turns"] + (1 if _is_player(defender) else 0)) == "applied":
                    status_applied = st
            # 疾病傳染(吸血鬼吸血熱 / 狼人狼人熱):命中機率 × 疾病抗性削弱(只標記,轉化由各系驅動)。
            # `infect_kind` 缺省 "vampire"(舊吸血鬼敵向後相容);跨詛咒互斥靠疾病免疫使 dmult=0 自然擋掉,
            # 此處再以 `already` 防同詛咒重複感染。
            inf = atk.get("infect")
            if inf:
                kind = atk.get("infect_kind", "vampire")
                already = (defender.is_vampire if kind == "vampire"
                           else getattr(defender, "is_werewolf", False))
                dmult = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), "disease")
                if not already and dmult > 0 and rng.chance(inf * dmult):
                    infected = True
                    infect_kind = kind
            # R53 普通病傳染:`atk["disease"]={"id","chance"}`,同走疾病抗性削弱(吸血鬼/狼人 disease:100 → dmult=0 自然免疫)。
            # 只標記,實際 contract 由 run_battle 分派。`disease` 欄只加在非 sim 怪 → sim byte-identical。
            dis = atk.get("disease")
            if dis and infect_kind is None:    # 詛咒感染優先;同一擊不同時染詛咒與普通病
                dmult2 = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), "disease")
                if dmult2 > 0 and rng.chance(dis.get("chance", 0.3) * dmult2):
                    infected = True
                    infect_kind = "disease"
                    disease_id = dis.get("id")

        # 玩家武器塗毒 → 命中即把毒效附到敵人身上,消耗一次塗層。獸形/束縛兵刃以非裝備武器戰鬥 → 不沾塗毒
        if (_is_player(attacker) and not beast and not bound and not great
                and attacker.weapon_poison and attacker.weapon_poison["charges"] > 0):
            wp = attacker.weapon_poison
            pk = wp["status"].get("status")
            if pk in magic._CONTROL_KINDS:   # 控場毒走集中 helper(R44:fear/paralyze 受 solo 機率減免 + 去重)
                if magic.apply_control(defender, pk, gamedata, rng,
                                       magnitude=wp["status"].get("magnitude", 0.0),
                                       turns=wp["status"]["turns"]) == "applied":
                    poison_applied = wp["name"]
            else:                            # dot 等非控場毒照舊
                defender.active_effects.append(magic.make_status_effect(wp["status"]))
                poison_applied = wp["name"]
            wp["charges"] -= 1                       # 毒在接觸即耗(即使抵抗 → 杜絕無限重試泵)
            if wp["charges"] <= 0:
                attacker.weapon_poison = None

        # 武器命中觸發附魔(weapon_status:吸血/麻痺/再生)—— 玩家專屬,與元素/毒/里程碑各自獨立、不重複套。
        # 獸形/束縛兵刃/雙手重盾盾擊以非裝備武器戰鬥 → 無裝備武器附魔
        # 同伴深化:gate 由 `_is_player` 改讀 `_gear_weapon_item`(玩家 byte-identical·帶裝同伴完全比照玩家附魔·一般怪 None 略過)。
        if not beast and not bound and not great and (_swi := _gear_weapon_item(attacker, gamedata)) is not None:
            # 主手 + 副手(雙持)的命中觸發附魔:副手以 OFFHAND_DAMAGE_FACTOR 權重疊加。
            # 吸血累計成總比例後一次回血;再生以 source 去重(主手優先);麻痺各自獨立擲一次(binary 不打折,solo 仍免疫)。
            heal_frac = 0.0
            for hench, w, wid in ((_swi.get("enchant"), 1.0, _gear_weapon_id(attacker)),
                                  (offhand_ench, formulas.OFFHAND_DAMAGE_FACTOR, attacker.offhand)):
                if not (hench and hench.get("kind") == "weapon_status"
                        and rng.chance(hench.get("chance", 1.0))):
                    continue
                st = hench["status"]
                if st == "vampiric" and dmg_done > 0:
                    # 吸血比例:武器 enchant.magnitude(%)優先,缺省回 WEAPON_VAMPIRIC_FRACTION(向後相容 30%)
                    heal_frac += formulas.vampiric_fraction(hench) * w
                elif st == "regen":   # self-HoT;以 source 去重(命中刷新不疊加;副手以 ×w 折幅)
                    if not any(e.get("source") == "ench_regen" and e.get("turns", 0) > 0
                               for e in attacker.active_effects):
                        attacker.active_effects.append(
                            {"kind": "regen", "magnitude": int(round(hench.get("magnitude", 0) * w)),
                             "turns": hench.get("turns", 0), "source": "ench_regen"})
                elif st in ("burn", "chill", "jolt") and is_alive(defender):
                    # 元素 DoT:逐回合吃抗性(magic.tick_effects);命中刷新取 max(免疊爆)
                    element = hench.get("element", "fire")
                    mag = max(1, int(round(hench.get("magnitude", 0) * w)))
                    turns = hench.get("turns", formulas.WEAPON_DOT_TURNS)
                    existing = next((e for e in defender.active_effects
                                     if e.get("kind") == "dot" and e.get("source") == "ench_dot"
                                     and e.get("element") == element), None)
                    if existing:
                        existing["turns"] = max(existing.get("turns", 0), turns)
                        existing["magnitude"] = max(existing.get("magnitude", 0), mag)
                    else:
                        defender.active_effects.append({"kind": "dot", "element": element, "magnitude": mag,
                                                        "turns": turns, "source": "ench_dot"})
                    if st == "chill":                         # 凍緩 rider:減敵輸出 → 集中 helper(同源去重:雙持不疊)
                        magic.apply_control(defender, "weaken", gamedata, rng,
                                            magnitude=formulas.WEAPON_CHILL_WEAKEN, turns=2, source="ench_chill")
                    elif st == "jolt":                        # 感電 rider:燒魔 + 機率踉蹌 → 集中 helper
                        if getattr(defender, "magicka", 0) > 0:
                            defender.magicka = max(0, defender.magicka - formulas.WEAPON_JOLT_MAGICKA)
                        if rng.chance(formulas.WEAPON_JOLT_STAGGER):
                            magic.apply_control(defender, "stagger", gamedata, rng, turns=1)
                elif st in ("absorb_health", "absorb_magicka", "absorb_fatigue"):
                    # 命中吸取:回攻擊者資源;吸取生命另扣目標(solo boss 受夾,杜絕無限回血泵)
                    stat = st.split("_", 1)[1]
                    amt = max(1, int(round(hench.get("magnitude", 0) * w)))
                    if stat == "health":
                        if _is_solo(defender, gamedata):
                            amt = max(1, int(round(amt * formulas.WEAPON_ABSORB_SOLO_FACTOR)))
                        if is_alive(defender):
                            _set_hp(defender, _get_hp(defender) - amt)
                    cur = getattr(attacker, stat, 0)
                    setattr(attacker, stat, min(getattr(attacker, "max_" + stat, cur), cur + amt))
                elif st == "soul_trap" and is_alive(defender):
                    # 命中擒魂(充能型):已擒中不重複扣;cap=0 為 legacy 無限。發魂在勝利結算(Phase 2)
                    cap = int(hench.get("magnitude", 0))
                    charges = getattr(attacker, "enchant_charges", {})
                    if not magic.has_soul_trap(defender) and (cap <= 0 or charges.get(wid, cap) > 0):
                        defender.active_effects.append(
                            {"kind": "soul_trap", "turns": hench.get("turns", formulas.WEAPON_SOULTRAP_TURNS),
                             "src": "weapon"})   # 武器擒魂:人形/黑魂專屬於法術 → 標記來源
                        if cap > 0:
                            charges[wid] = max(0, charges.get(wid, cap) - 1)
                elif st == "paralyze" and is_alive(defender):
                    # 附魔麻痺 → 集中 helper(R44:solo BOSS 機率減免 + 去重);充能型先確認有格再施,抵抗則不扣格
                    cap = int(hench.get("magnitude", 0))
                    charges = getattr(attacker, "enchant_charges", {})
                    if cap <= 0 or charges.get(wid, cap) > 0:
                        if magic.apply_control(defender, "paralyze", gamedata, rng,
                                               turns=hench.get("turns", 1)) == "applied":
                            if cap > 0:
                                charges[wid] = max(0, charges.get(wid, cap) - 1)
                            status_applied = status_applied or "paralyze"
                elif st == "wabbajack":
                    # 瘋神謝歐格拉斯·瓦巴賈克:命中觸發隨機混沌效果(R46)——六效果各走既有安全 helper,
                    # solo 夾/控場機率抵抗/非遞迴 由 helper 自動成立;玩家專屬(此區已被 _is_player 包住)。
                    _wab_total = sum(_wt for _wt, _ in formulas.WABBAJACK_TABLE)
                    _wab_r = rng.roll(0, _wab_total)
                    _wab_acc = 0.0
                    _wab_effect = formulas.WABBAJACK_TABLE[-1][1]
                    for _wt, _eid in formulas.WABBAJACK_TABLE:
                        _wab_acc += _wt
                        if _wab_r < _wab_acc:
                            _wab_effect = _eid
                            break
                    # 幸運偏轉混沌(R116):抽到回火(自傷/治敵)時,以幸運 save 機率改抽好效果。
                    # 🔴 luck≤40 → save=0 → `and` 短路不擲 rng → byte-identical;沙盒專屬法杖·刺客不持 → sim 不觸此區。
                    if _wab_effect in ("backfire_self", "backfire_enemy"):
                        # 幸運 save 是玩家天命(同伴無 .attr → 0·不 reroll·回火照發=自平衡);玩家 byte-identical。
                        _wsave = formulas.luck_wabbajack_save(attacker.attr("luck")) if _is_player(attacker) else 0.0
                        if _wsave > 0 and rng.chance(_wsave):
                            _good = [(w, e) for w, e in formulas.WABBAJACK_TABLE
                                     if e not in ("backfire_self", "backfire_enemy")]
                            _gr = rng.roll(0, sum(w for w, _ in _good))
                            _ga = 0.0
                            _wab_effect = _good[-1][1]
                            for _w, _e in _good:
                                _ga += _w
                                if _gr < _ga:
                                    _wab_effect = _e
                                    break
                    if _wab_effect == "burst" and is_alive(defender):
                        # 隨機元素爆發:複用 weapon_element 數學(吃抗性)·非偷襲傷·solo 另受夾
                        _wab_elem = rng.choice(("fire", "frost", "shock"))
                        _wab_em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), _wab_elem)
                        _wab_amt = magic._scaled_damage(formulas.WABBAJACK_ELEMENT_BURST, _wab_em)
                        if _is_solo(defender, gamedata):
                            _wab_amt = max(1, int(round(_wab_amt * formulas.WABBAJACK_BURST_SOLO_FACTOR)))
                        _set_hp(defender, _get_hp(defender) - _wab_amt)
                    elif _wab_effect == "control" and is_alive(defender):
                        # 隨機硬/軟控 → 中央 helper(solo BOSS 機率抵抗 + willpower + 去重;turns 1 守紀律)
                        magic.apply_control(defender, rng.choice(("fear", "paralyze", "stagger")),
                                            gamedata, rng, turns=1, source="wabbajack")
                    elif _wab_effect == "self_restore":
                        _wab_stat = rng.choice(("health", "magicka", "fatigue"))
                        _wab_cur = getattr(attacker, _wab_stat, 0)
                        setattr(attacker, _wab_stat,
                                min(getattr(attacker, "max_" + _wab_stat, _wab_cur),
                                    _wab_cur + formulas.WABBAJACK_SELF_RESTORE))
                    elif _wab_effect == "weaken" and is_alive(defender):
                        magic.apply_control(defender, "weaken", gamedata, rng,
                                            magnitude=formulas.WABBAJACK_WEAKEN_MAG, turns=2, source="wabbajack")
                    elif _wab_effect == "backfire_self":
                        # 回火自傷:max(1,…) 永不致死;直接賦值非遞迴
                        attacker.health = max(1, attacker.health - formulas.WABBAJACK_BACKFIRE_SELF)
                    elif _wab_effect == "backfire_enemy" and is_alive(defender):
                        # 回火治敵:自限的混沌·直接賦值非遞迴(solo 上微不足道)
                        _set_hp(defender, min(defender.max_health,
                                              _get_hp(defender) + formulas.WABBAJACK_BACKFIRE_TARGET_HEAL))
            if heal_frac > 0:   # 雙持雙吸血 → 0.30 + 0.30×0.6 = 0.48(回血夾在本擊傷害內,不超過造成傷害)
                heal = min(int(round(dmg_done * heal_frac)), dmg_done)
                before = attacker.health
                attacker.health = min(attacker.max_health, attacker.health + heal)
                lifesteal = int(attacker.health - before)

        # 里程碑武器流派「命中附狀態」(震盪一擊=weaken / 卸力擒拿=stagger)+「盾擊踉蹌」
        if _is_player(attacker) and is_alive(defender):
            ohs = wmod.get("on_hit_status")
            if ohs and rng.chance(ohs.get("chance", 1.0)):   # 卸力擒拿 stagger / 震盪一擊 weaken / 牽制箭 slow → 集中 helper
                magic.apply_control(defender, ohs["kind"], gamedata, rng,
                                    magnitude=ohs.get("magnitude", 0.0),
                                    turns=ohs.get("turns", 2 if ohs["kind"] == "slow" else 1))
        # 武器原型內建命中附狀態(釘錘/戰錘=控制流擊暈;斧走破甲不在此)→ 集中 helper
        # (R44 收斂:stagger 軟控不免 solo → 與里程碑/盾反/感電 stagger 一致,移除原 mace-only 的 _is_solo 免疫)
        if _is_player(attacker) and is_alive(defender):
            bs = formulas.archetype_builtin_status(archetype)
            if bs and bs["kind"] == "stagger" and rng.chance(bs.get("chance", 0.0)):
                magic.apply_control(defender, "stagger", gamedata, rng, turns=bs.get("turns", 1))
        # 徒手「失衡」warfare:拳腳連擊堆疊敵失衡層 → 放大後續徒手傷害(疊加提升傷害·見上 ramp);跨門檻
        # 踉蹌(軟控·來源去重·不重置 ramp),滿頂罕見真擊倒(硬控·solo 機率抵抗 R44)+ 重置(防 lock-loop)。
        # 🔴 只玩家徒手(wpn_skill_id=="hand_to_hand")非獸形 → 匕首/法系/獸形/sim 永不觸發 → byte-identical。
        # R103:另須里程碑解鎖(hand_to_hand≥25)且未穿重甲(輕裝武僧)→ 重甲/未解鎖完全不累積失衡。
        if (_is_player(attacker) and wpn_skill_id == "hand_to_hand" and not beast and is_alive(defender)
                and _offbalance_active(attacker, gamedata)):
            stacks = magic.add_offbalance(defender, formulas.offbalance_stack_gain(
                attacker.skill("hand_to_hand"), wmod.get("poise_rate", 0.0)))
            if stacks >= formulas.OFFBALANCE_MAX_STACKS \
                    and rng.chance(formulas.OFFBALANCE_KNOCKDOWN_CHANCE):   # 滿頂罕見真擊倒(掀翻在地)
                magic.apply_control(defender, "paralyze", gamedata, rng, turns=1)   # R44:solo 機率抵抗 + 去重
                # 🔴 刻意「無條件」重置(即使 paralyze 被 solo 抵抗/硬控去重未真施加):防 ramp 卡在 MAX
                # 反覆擲 0.25 proc 趨近鎖定 solo boss(對抗審查確認此為守 anti-perma-lock 紅線的機制,
                # 非 bug)。改成「只在 applied 才重置」會抬高 solo 失能率=平衡取捨→須先問 + 重跑 sim_builds。
                magic.reset_offbalance(defender)
            elif stacks >= formulas.OFFBALANCE_STAGGER_THRESHOLD:             # 門檻:踉蹌(來源去重·不重置 ramp)
                magic.apply_control(defender, "stagger", gamedata, rng, turns=1, source="offbalance")
        # R137:反擊樹觸發=手動格擋(defender_blocking·外部呼叫端仍可傳)**或**格擋姿態中被命中。
        # 🔴 僅**物理**來襲觸發(鏡像 R42 荊棘 not atk_element):盾身接觸才有反擊,火焰吐息等元素
        # 攻擊不觸發 → 元素攻擊仍是反擊/反傷流的天然反制。🔴 姿態不套用於獸形(利爪無盾·鏡像重盾)。
        if (_is_player(defender) and is_alive(attacker) and not atk_element
                and not (atk or {}).get("ranged")   # R145:隔空盾擊不了弩手
                and not _ovx                        # R191 搏命連斬:還擊期間門戶大開 → 來不及舉盾反擊
                and (defender_blocking or (has_guard_stance(defender) and defender.fatigue > 0
                                           and not _is_beast(defender)))):
            rp = mastery.block_riposte(defender, gamedata)
            if rp.get("stagger_chance") and rng.chance(rp["stagger_chance"]):
                # turns:2 → 防守側(敵階段)施加的踉蹌須撐過回合末 tick,才在敵下次出手時生效(修既有 shield_bash 死時序)
                magic.apply_control(attacker, "stagger", gamedata, rng, turns=2)
                if rp.get("weaken"):          # 盾擊破勢:反擊同時削弱敵下擊
                    # R182 回合照字面:`weaken_turns: N` = 怪物的 N 次出手。此處在**怪物自己的階段**施加,
                    # 回合末 tick 先 −1 → 資料寫 2 實際只衰弱 1 次出手(R181 前瞻同族缺陷)→ +1 補償。
                    # (上方 stagger 的 turns:2 本意就是「下一擊」= 1 次出手,已正確,不動。)
                    magic.apply_control(attacker, "weaken", gamedata, rng,
                                        magnitude=rp["weaken"], turns=rp.get("weaken_turns", 2) + 1)
                if rp.get("counter"):         # 盾威·完美格擋:盾擊反傷(基礎武器傷的一部分)
                    # 🔴 R137 審查修:反擊=物理傷,**吃攻擊者物抗**(resist_multiplier·pen-免疫車道)——
                    # 否則直接扣血繞過 R127/R133 物理牆(實測 720 達貢 2%→12% 全由此洩;套抗後回包絡)。
                    cdmg = _player_counter_damage(defender, gamedata, rng) * rp["counter"]
                    cdmg *= formulas.resist_multiplier(magic.entity_resist(attacker, gamedata), "physical")
                    _set_hp(attacker, _get_hp(attacker) - int(round(cdmg)))
        # 里程碑「懾心術/懾意/懾魂」:玩家武器命中施加懼意(illusion 控場)→ 集中 helper(R44:solo 機率減免)
        if _is_player(attacker) and is_alive(defender):
            foh = mastery.fear_on_hit(attacker, gamedata)
            if foh and rng.chance(foh.get("chance", 0.0)):
                magic.apply_control(defender, "fear", gamedata, rng, turns=foh.get("turns", 2))
        # 里程碑「不屈祝禱」:玩家受擊跌破低血線 → 觸發再生(每段只在無效時補,避免無限疊)
        if _is_player(defender) and is_alive(defender):
            rg = mastery.regen_on_low(defender, gamedata)
            if rg and defender.health < defender.max_health * rg.get("threshold", 0.25) \
                    and not any(e.get("source") == "steadfast" and e.get("turns", 0) > 0
                                for e in defender.active_effects):
                defender.active_effects.append({"kind": "regen", "magnitude": rg.get("regen", 4),
                                                "turns": rg.get("turns", 3), "source": "steadfast"})

        # 暗殺殘響:偷襲命中但沒秒殺 → 依武器流派留下踉蹌(命中減成)/撕裂傷(DoT),
        # 強度吃潛行+煉金。讓「失手的暗殺」不再是斷崖,而是 combo 的第一段。
        if sneaking and is_alive(defender):
            am = formulas.sneak_aftermath(archetype)
            staggered = bool(am.get("stagger"))
            bleed_mag = 0
            if staggered:
                magic.apply_control(defender, "stagger", gamedata, rng, turns=1)   # R44:集中 helper(R190:餘韻由它統一留)
            if am.get("bleed"):
                bleed_mag = formulas.sneak_bleed_magnitude(
                    attacker.skill("sneak"), attacker.skill("alchemy"))
                defender.active_effects.append({"kind": "dot", "element": "bleed",
                                                "magnitude": bleed_mag,
                                                "turns": formulas.SNEAK_BLEED_TURNS})
            if staggered or bleed_mag:
                aftermath = {"staggered": staggered, "bleed": bleed_mag}

        # learn-by-doing:攻擊方是玩家 → 練武器;防守方是玩家 → 練護甲
        if _is_player(attacker) and wpn_skill_id:
            skill_events += progression.use_skill(attacker, gamedata, wpn_skill_id,
                                                  formulas.COMBAT_HIT_XP)
        elif bound:   # 束縛兵刃命中 → 練咒術(法系近戰也成長對應技能,補 learn-by-doing 一致性)
            skill_events += progression.use_skill(attacker, gamedata, "conjuration",
                                                  formulas.COMBAT_HIT_XP)
        if sneaking:   # 偷襲命中 → 鍛鍊潛行(讓 sneak 也能在戰鬥中成長)
            skill_events += progression.use_skill(attacker, gamedata, "sneak",
                                                  formulas.COMBAT_SNEAK_XP)
        if _is_player(defender):
            if dmg_done > 0 and not _is_player(attacker):   # R186 幻影步:被命中(實際受傷)→ 殘影散去一層
                afterimage_lose(defender)
            if inventory.dominant_weight_class(defender, gamedata) is not None:   # R141:裸身被打不練護甲(沒有甲可習)
                skill_events += progression.use_skill(defender, gamedata,
                                                      _player_armor_skill(defender, gamedata),
                                                      formulas.COMBAT_ARMOR_XP)
            if (defender_blocking or has_guard_stance(defender)) and not _ovx:   # R137:姿態中被命中也練 block(learn-by-doing);R191 門戶大開的還擊沒有舉盾 → 不練
                skill_events += progression.use_skill(defender, gamedata, "block",
                                                      formulas.COMBAT_BLOCK_XP)
        if _is_player(attacker):           # 只夾限玩家資源;怪物 hp 已由 _set_hp 夾限
            stats.clamp_resources(attacker)
        if _is_player(defender):
            stats.clamp_resources(defender)
    elif _is_player(defender):             # 敵人攻擊落空 + 防守方是玩家 → 成功閃避 → 鍛鍊雜技
        if not _ovx:   # R191 搏命連斬:還擊期間閃避歸零、敵人落空是對方失手而非你閃過 → 不練雜技、不凝殘影、不反制
            skill_events += progression.use_skill(defender, gamedata, "acrobatics",
                                                  formulas.COMBAT_DODGE_XP)
        # 輕甲「迴身反打/風暴之舞」+ 雜技「凌空奇襲」:閃過敵攻即反制(只對敵)。
        # R183(使用者拍板,取代 R34「每回合至多一次」):**每次**閃過都各自判定——回體力每次給、反擊每次各擲一次機率
        # (效果文本來就寫「每次閃過敵攻即回復」);N 隻怪同回合攻擊 → 最多 N 次反擊/N 個踉蹌。
        # 反擊仍限物理近戰:元素(龍息/法術/凝視)與標 ranged 的攻擊閃過無反擊(R145,回體力照給)。
        if not _is_player(attacker) and not _ovx:   # R186 幻影步:閃過**任何**敵攻(含遠程/元素)皆凝殘影;無里程碑/穿重甲 → no-op、零 rng
            afterimage_gain(defender, gamedata)
        oe = None if _ovx else mastery.on_evade(defender, gamedata)
        if oe and not _is_player(attacker):
            if oe.get("restamina"):
                defender.fatigue = min(defender.max_fatigue, defender.fatigue + oe["restamina"])
            if (oe.get("counter_frac") and is_alive(attacker)
                    and not (atk or {}).get("element") and not (atk or {}).get("ranged")   # R145:閃過龍息/弩矢搆不到人 → 無反擊(回氣照舊;落空分支 atk_element 未綁定 → 直讀 atk)
                    and rng.chance(oe.get("counter_chance", 0.0))):
                # R137 審查修:閃身反打同為物理反擊 → 吃攻擊者物抗(同盾反擊·守 R127/R133 pen-免疫牆;
                # 物抗 0 之敵 ×1.0 行為不變)
                _cd = _player_counter_damage(defender, gamedata, rng) * oe["counter_frac"]
                _cd *= formulas.resist_multiplier(magic.entity_resist(attacker, gamedata), "physical")
                _set_hp(attacker, _get_hp(attacker) - int(round(_cd)))
                if oe.get("counter_stagger"):
                    # R181:turns:2 → 敵人階段對怪物施加的踉蹌須撐過回合末 tick,才在該怪「下一次出手」時生效
                    # (原 turns:1 實測施加 388 次、怪物下一擊讀到 0 次 = 死機制;與上方盾擊/荊棘同款時序修法)
                    magic.apply_control(attacker, "stagger", gamedata, rng, turns=2)   # R44:集中 helper

    return {
        "attacker": _name(attacker), "defender": _name(defender),
        "attack_name": atk.get("name") if atk else None,   # 怪物選定招名(玩家=None)→ 供 UI 顯示「使出【招】」
        "hit": hit, "damage": dmg_done, "blocked": defender_blocking,
        "skill_events": skill_events, "defender_dead": not is_alive(defender),
        "absorbed": absorbed, "status_applied": status_applied, "poison_applied": poison_applied,
        "sneak": sneak_mult, "self_restored": self_restored, "infected": infected,
        "infect_kind": infect_kind, "disease_id": disease_id, "lifesteal": lifesteal,
        "aftermath": aftermath,
    }


def player_attack_cost(player: Character, gamedata: GameData | None = None) -> None:
    """玩家攻擊一擊消耗體力(運動越高越省;慢重武器更耗、輕快武器更省)。"""
    speed = formulas.WEAPON_SPEED_DEFAULT
    if gamedata is not None:
        wid = "beast_claws" if getattr(player, "beast_form", False) else player.weapon
        speed = gamedata.item(wid).get("speed", formulas.WEAPON_SPEED_DEFAULT)
        gs = player.equipped.get("shield") if not getattr(player, "beast_form", False) else None
        gsd = gamedata.item_or_none(gs) if gs else None
        if gsd and gsd.get("great_shield"):
            speed = gsd.get("speed", 0.85)   # R141 現實邏輯:盾擊耗體以重盾自身(慢重)計,非休眠中的手持武器
    cost = (formulas.ATTACK_FATIGUE_COST
            * formulas.fatigue_cost_factor(player.skill("athletics"))
            * formulas.weapon_attack_fatigue_factor(speed))
    if gamedata is not None:                       # 里程碑「壁壘」同源代價:揮擊更耗體
        cost *= mastery.attack_fatigue_factor(player, gamedata)
        cost *= (1 - mastery.fatigue_cost_bonus(player, gamedata))   # 「不竭之軀」:戰鬥省體
        wsid = gamedata.item(wid).get("skill")     # 獸形用獸爪技能(hand_to_hand),非裝備武器
        cost += mastery.weapon_mod(player, gamedata, wsid).get("fatigue", 0)   # 「穿甲箭」draw_fatigue 代價
    player.fatigue = max(0, player.fatigue - cost)


def player_block_cost(player: Character) -> None:
    """玩家舉盾格擋消耗體力(運動越高越省)。"""
    cost = formulas.BLOCK_FATIGUE_COST * formulas.fatigue_cost_factor(player.skill("athletics"))
    player.fatigue = max(0, player.fatigue - cost)


def player_vanish_cost(player: Character) -> None:
    """隱遁消耗大量體力(運動越高越省);連續隱遁會耗竭體力,壓制無限風箏。"""
    cost = formulas.VANISH_FATIGUE_COST * formulas.fatigue_cost_factor(player.skill("athletics"))
    player.fatigue = max(0, player.fatigue - cost)


def try_flee(player: Character, creature: Creature, rng: RNG, gamedata: GameData | None = None) -> bool:
    chance = formulas.flee_chance(_speed(player), _agility(player), _speed(creature))
    chance = min(0.95, chance + formulas.luck_fortune(player.attr("luck")))   # 幸運「時來運轉」
    if gamedata is not None:                          # 里程碑「逃命好手」(運動):逃跑率加成
        chance = min(0.95, chance)   # R147:逃跑加成里程碑(escape_artist)已移除
    return rng.chance(chance)


def can_vanish(player: Character, gamedata: GameData | None = None) -> bool:
    """是否解鎖戰中隱遁:走潛行 25 里程碑「隱遁之術」(`mastery.has_vanish`,門檻認 base_skill)。
    無 gamedata 時退回 base_skill ≥ VANISH_MIN_SNEAK(與該里程碑門檻一致;非潛行流派不適用)。"""
    if gamedata is not None:
        return mastery.has_vanish(player, gamedata)
    base = player.base_skill("sneak") if hasattr(player, "base_skill") else player.skill("sneak")
    return base >= formulas.VANISH_MIN_SNEAK


def vanish_chance(player: Character, n_alive: int, used: int, gamedata: GameData | None = None) -> float:
    relentless = floor = 0.0
    if gamedata is not None:                       # 里程碑「連環踏影」(免重複遞減)/「踏影」(保底下限)
        relentless = mastery.has_vanish_relentless(player, gamedata)
        floor = mastery.vanish_floor(player, gamedata)
    return formulas.restealth_chance(player.skill("sneak"), player.skill("acrobatics"), n_alive, used,
                                     relentless=bool(relentless), floor=floor)


def try_vanish(player: Character, n_alive: int, used: int, rng: RNG, gamedata: GameData | None = None) -> bool:
    """嘗試隱遁再襲:成功回傳 True(由 run_battle 跳過本回合敵人攻擊並重置偷襲)。"""
    return rng.chance(vanish_chance(player, n_alive, used, gamedata))


def vanish_cap(player: Character, gamedata: GameData | None = None) -> int:
    """每場 vanish 次數上限;里程碑「連環踏影」解除(實質無限,仍受 >3 敵懲罰 + 體力壓制)。"""
    if gamedata is not None and mastery.has_vanish_relentless(player, gamedata):
        return 99
    return formulas.MAX_VANISHES_PER_BATTLE


def stealth_retreat_chance(player: Character, enemies: list) -> float:
    foe_speed = max((e.speed for e in enemies), default=0)
    return formulas.stealth_retreat_chance(player.skill("sneak"), _speed(player),
                                           foe_speed, len(enemies))


def try_stealth_retreat(player: Character, enemies: list, rng: RNG) -> bool:
    return rng.chance(stealth_retreat_chance(player, enemies))


def stealth_approach_chance(player: Character, enemies: list, gamedata: GameData,
                            night: bool = False, scouted: bool = False, surprise: bool = False) -> float:
    foe_agi = max((e.agility for e in enemies), default=0)
    armor_weight = inventory.armor_worn_weight(player, gamedata)
    approach_bonus = mastery.approach_bonus(player, gamedata)          # 「無聲潛近」
    if night:                                                          # 吸血鬼夜視:夜間潛近額外加成(R56·非吸血鬼為 0 → sim byte-identical)
        from tesrpg.systems import vampirism
        approach_bonus += vampirism.night_vision_bonus(player)
        approach_bonus += race_ability.night_eye_bonus(player, gamedata)   # 虎人夜視(R61·非虎人 0;sim night=False 不入此區)
    return formulas.stealth_approach_chance(
        player.skill("sneak"), foe_agi, len(enemies), armor_weight, night, scouted, surprise,
        approach_bonus=approach_bonus,
        armor_relief=mastery.armor_sneak_relief(player, gamedata))     # 「無聲披掛」


def try_stealth_approach(player: Character, enemies: list, rng: RNG, gamedata: GameData,
                         night: bool = False, scouted: bool = False, surprise: bool = False) -> bool:
    """接戰時擲一次入場潛行檢定;成功 → 取得開場偷襲先機。"""
    return rng.chance(stealth_approach_chance(player, enemies, gamedata, night, scouted, surprise))


def estimate_sneak_damage(player: Character, gamedata: GameData, creature: Creature) -> int:
    """偵查用:玩家對該敵人一記偷襲的『中位』傷害估算(roll=1.0,過甲後)。

    與 resolve_attack 一致:獸形不吃偷襲倍率、無副手、用獸爪流派(咆哮現身 → 偷襲無效)。"""
    beast = _is_beast(player)
    wpn_dmg, wpn_skill, wpn_skill_id = _weapon_profile(player, gamedata)
    offhand_dmg = 0.0 if beast else inventory.dual_wield_bonus_damage(player, gamedata)
    archetype = gamedata.item(eff_weapon_id(player, gamedata)).get("archetype")
    wm = mastery.weapon_mod(player, gamedata, wpn_skill_id)   # 與 resolve_attack 一致
    raw = formulas.attack_damage(wpn_dmg, wpn_skill, _strength(player), 1.0)
    power_bonus = raw * wm.get("power", 0.0)                  # weapon_mod 威力:flat 補傷(不吃偷襲倍率)
    if not beast:    # 🔴 獸形與潛行互斥 → 不套偷襲倍率(與 resolve_attack 的 not beast 守門一致)
        raw *= (formulas.sneak_attack_multiplier(player.skill("sneak"))
                * formulas.archetype_sneak_bonus(archetype)
                * formulas.night_mother_sneak_bonus(player.factions.get("dark_brotherhood", -1))
                * (1 + mastery.sneak_mult_bonus(player, gamedata))   # 里程碑「影刃」
                * formulas.armor_sneak_mult_factor(inventory.armor_worn_weight(player, gamedata),
                                                   mastery.armor_sneak_relief(player, gamedata)))  # 與 resolve_attack 一致:重量折扣 + R72 無聲披掛 relief
    raw += power_bonus
    if offhand_dmg:    # 副手補刀不吃偷襲倍率(與 resolve_attack 一致)
        raw += formulas.attack_damage(offhand_dmg, wpn_skill, _strength(player), 1.0)
    pen = min(0.85, formulas.archetype_armor_pen(archetype) + wm.get("pen", 0))
    est = formulas.damage_after_armor(raw, creature.armor_rating, pen)
    est *= formulas.resist_multiplier(magic.entity_resist(creature, gamedata), "physical")  # R127 物理抗性(與 resolve_attack 一致;既有怪無物抗 → ×1.0 不變)
    if _is_solo(creature, gamedata):    # 與 resolve_attack 一致:solo boss 偷襲單擊夾限
        est = min(est, (getattr(creature, "max_health", 0) or creature.health)
                  * formulas.SOLO_SNEAK_DAMAGE_CAP_RATIO)
    return int(round(est))


def grant_loot(player: Character, creature: Creature, gamedata: GameData, rng: RNG) -> dict:
    """結算怪物戰利品,金幣與物品入袋(幸運「戰利豐厚」加權)。回傳 {"gold", "items":[(id,qty)]}。"""
    result = loot.creature_loot(creature, rng, formulas.luck_loot_factor(player.attr("luck")))
    player.gold += result["gold"]
    for item_id, qty in result["items"]:
        inventory.add_item(player, item_id, qty)
    return result


# ======================================================================
# 無 IO 的全自動對戰(測試/平衡用):玩家固定攻擊
# ======================================================================
def auto_resolve(player: Character, creature: Creature, gamedata: GameData,
                 rng: RNG, max_rounds: int = 100) -> dict:
    rounds = 0
    while is_alive(player) and is_alive(creature) and rounds < max_rounds:
        rounds += 1
        for actor in initiative_order(player, creature):
            if not (is_alive(player) and is_alive(creature)):
                break
            if _is_player(actor):
                player_attack_cost(player, gamedata)
                resolve_attack(player, creature, gamedata, rng)
            else:
                resolve_attack(creature, player, gamedata, rng, attack=choose_attack(creature, rng, player))
        # 回合結束結算持續傷害/再生/狀態(與 run_battle 一致,讓毒/法術 DoT 生效)
        hregen = mastery.combat_regen(player, gamedata)   # 里程碑「生生不息」:每回合自癒
        if hregen and is_alive(player) and player.health < player.max_health:
            player.health = min(player.max_health, player.health + hregen)
        magic.tick_effects(player, gamedata)
        magic.tick_effects(creature, gamedata)
    winner = "player" if is_alive(player) and not is_alive(creature) else (
        "creature" if not is_alive(player) else "draw")
    return {"winner": winner, "rounds": rounds,
            "player_hp": player.health, "creature_hp": creature.health}
