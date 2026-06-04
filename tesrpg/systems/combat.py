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
from tesrpg.systems import inventory, loot, magic, progression, stats


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
        attack=dict(t["attack"]), loot_gold=list(t["loot_gold"]),
        loot_table=list(t.get("loot", [])), flavor=t.get("flavor", ""),
        danger=t.get("danger", 1), resist=dict(t.get("resist", {})),
    )


def random_encounter_group(gamedata: GameData, player_level: int, rng: RNG,
                           max_danger: int | None = None) -> list[Creature]:
    """隨機遭遇一「群」敵人;危險度越高越容易成群、規模越大(最危險區可達 4)。"""
    roll = rng.random()
    d = max_danger or 1
    if d >= 5:        # 最危險區:常成群
        size = 1 if roll < 0.35 else (2 if roll < 0.68 else (3 if roll < 0.90 else 4))
    elif d >= 3:      # 中危區
        size = 1 if roll < 0.55 else (2 if roll < 0.85 else 3)
    else:             # 低危區
        size = 1 if roll < 0.75 else (2 if roll < 0.94 else 3)
    group = [random_encounter(gamedata, player_level, rng, max_danger) for _ in range(size)]
    # BOSS 級(solo)只單獨出現:群中若含 solo 敵人,收斂成那一隻(避免一次多隻王)
    boss = next((e for e in group
                 if gamedata.bestiary.get(e.template_id, {}).get("solo")), None)
    return [boss] if boss is not None else group


def spawn_companion(gamedata: GameData, companion_id: str, rng: RNG) -> Creature:
    """把雇用的同伴生成為我方戰鬥單位(每場戰鬥滿血登場)。"""
    t = gamedata.companions[companion_id]
    return Creature(
        template_id=companion_id, name=t["name"],
        strength=t["strength"], agility=t["agility"], speed=t["speed"],
        max_health=t["max_health"], health=t["max_health"], armor_rating=t["armor_rating"],
        attack=dict(t["attack"]), loot_gold=[0, 0], loot_table=[],
        flavor=t.get("blurb", ""), danger=0, resist=dict(t.get("resist", {})),
        summon_turns=None,
    )


def alive_list(combatants: list) -> list:
    return [c for c in combatants if is_alive(c)]


def pick_player_side_target(player: Character, allies: list, rng: RNG):
    """敵人選擇攻擊我方目標:偏好玩家(約 55%),其餘平分給存活同伴。"""
    living_allies = [a for a in allies if is_alive(a)]
    if not living_allies or rng.chance(0.55):
        return player
    return rng.choice(living_allies)


def spawn_boss(gamedata: GameData, template_id: str, rng: RNG, name: str | None = None) -> Creature:
    """地城首領:在模板基礎上強化生命與攻擊。"""
    cr = spawn_creature(gamedata, template_id, rng)
    cr.max_health = round(cr.max_health * 1.6)
    cr.health = cr.max_health
    cr.attack = dict(cr.attack)
    cr.attack["damage"] = round(cr.attack["damage"] * 1.3)
    cr.attack["skill"] = min(100, cr.attack["skill"] + 15)
    cr.armor_rating += 6
    if name:
        cr.name = name
    return cr


def random_encounter(gamedata: GameData, player_level: int, rng: RNG,
                     max_danger: int | None = None) -> Creature:
    """依玩家等級加權抽一隻敵人(危險度越高越罕見);max_danger 限制最高危險度。"""
    pool = []
    weights = []
    for tid, t in gamedata.bestiary.items():
        if t.get("min_level", 1) > player_level:
            continue
        if max_danger is not None and t.get("danger", 1) > max_danger:
            continue
        pool.append(tid)
        weights.append(t.get("weight", 1))
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
    return actor.attr("speed") if _is_player(actor) else actor.speed


def _weapon_profile(actor, gamedata: GameData):
    """回傳 (weapon_damage, weapon_skill_level, weapon_skill_id|None)。"""
    if _is_player(actor):
        wp = gamedata.item(actor.weapon)   # 用 item() 以支援附魔(合成)武器
        return wp["damage"], actor.skill(wp["skill"]), wp["skill"]
    return actor.attack["damage"], actor.attack["skill"], None


def _armor_rating(actor, gamedata: GameData) -> int:
    if not _is_player(actor):
        return actor.armor_rating
    worn = inventory.effective_armor_rating(actor, gamedata)   # 已計入耐久折損
    wc = inventory.dominant_weight_class(actor, gamedata)
    if worn == 0 or wc is None:
        base = formulas.player_armor_rating(actor.skill("heavy_armor"), actor.skill("light_armor"))
    else:
        skill = actor.skill("heavy_armor" if wc == "heavy" else "light_armor")
        base = round(worn * (0.5 + skill / 100.0))
    return base + magic.active_shield(actor)   # 變化系護盾疊加


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


def initiative_order(player: Character, creature: Creature) -> list:
    """速度高者先行;同速玩家優先。"""
    return sorted([player, creature], key=lambda a: (_speed(a), _is_player(a)), reverse=True)


# ======================================================================
# 結算單次攻擊
# ======================================================================
def resolve_attack(attacker, defender, gamedata: GameData, rng: RNG,
                   defender_blocking: bool = False, sneak_attack: bool = False) -> dict:
    """attacker 攻擊 defender,套用傷害、發放玩家技能 xp。回傳事件 dict。

    sneak_attack:玩家開場偷襲(不察之敵)→ 傷害依潛行加倍、命中下限拉高、鍛鍊潛行。

    事件:{"attacker","defender","hit":bool,"damage":int,"blocked":bool,
           "skill_events":[...], "defender_dead":bool, "sneak":倍率|None}
    """
    sneaking = sneak_attack and _is_player(attacker)
    wpn_dmg, wpn_skill, wpn_skill_id = _weapon_profile(attacker, gamedata)
    wdef = gamedata.item(attacker.weapon) if _is_player(attacker) else None
    archetype = wdef.get("archetype") if wdef else None
    speed = wdef.get("speed", formulas.WEAPON_SPEED_DEFAULT) if wdef else formulas.WEAPON_SPEED_DEFAULT
    fr = _fatigue_ratio(attacker)
    evasion = formulas.dodge_evasion(defender.skill("acrobatics")) if _is_player(defender) else 0.0
    chance = formulas.hit_chance(wpn_skill, _agility(attacker), _agility(defender),
                                 fr, defender_blocking, defender_evasion=evasion)
    if _is_player(attacker):    # 武器速度:快武器更易命中、慢武器較難
        chance = max(0.05, min(0.95, chance + formulas.weapon_speed_hit(speed)))
    if magic.is_staggered(attacker):   # 暗殺殘響:陣腳大亂的單位本回合更難命中
        chance = max(0.05, chance - formulas.STAGGER_HIT_PENALTY)
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
    aftermath = None
    sneak_mult = (formulas.sneak_attack_multiplier(attacker.skill("sneak"))
                  * formulas.archetype_sneak_bonus(archetype)) if sneaking else None

    if hit:
        cond_mult = inventory.weapon_damage_mult(attacker) if _is_player(attacker) else 1.0
        raw = formulas.attack_damage(wpn_dmg, wpn_skill, _strength(attacker),
                                     rng.roll(0.85, 1.15), defender_blocking) * cond_mult
        if sneaking:
            raw *= sneak_mult
        atk_element = None if _is_player(attacker) else attacker.attack.get("element")
        if not _is_player(attacker):
            raw *= magic.weaken_factor(attacker)        # 怪物受耗弱影響

        if atk_element:
            # 元素攻擊:無視物理護甲,改吃元素抗性;巨魔像座可吸收為魔力
            if _is_player(defender) and defender.birthsign == "atronach" and rng.chance(0.5):
                gain = int(round(raw))
                defender.magicka = min(defender.max_magicka, defender.magicka + gain)
                absorbed = True
                dmg = 0.0
            else:
                mult = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), atk_element)
                dmg = magic._scaled_damage(raw, mult)
        else:
            pen = formulas.archetype_armor_pen(archetype)   # 鈍器破甲
            dmg = formulas.damage_after_armor(raw, _armor_rating(defender, gamedata), pen)
            # 武器附魔:額外元素傷害(無視護甲,受對方元素抗性)
            if _is_player(attacker):
                ench = gamedata.item(attacker.weapon).get("enchant")
                if ench and ench.get("kind") == "weapon_element":
                    em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), ench["element"])
                    dmg += magic._scaled_damage(ench["magnitude"], em)

        dmg_done = int(round(dmg))
        _set_hp(defender, _get_hp(defender) - dmg_done)

        # 法杖等「命中回復施術者資源」(D:on_hit_self)→ 由後面的 clamp_resources 夾限
        if _is_player(attacker) and wdef and wdef.get("on_hit_self"):
            ohs = wdef["on_hit_self"]
            setattr(attacker, ohs["stat"], getattr(attacker, ohs["stat"]) + ohs["magnitude"])
            self_restored = (ohs["stat"], ohs["magnitude"])

        # 怪物攻擊的觸發狀態(中毒/凍傷等)→ 加到玩家身上
        if not _is_player(attacker) and _is_player(defender):
            oh = attacker.attack.get("on_hit")
            if oh and rng.chance(oh.get("chance", 1.0)):
                defender.active_effects.append({"kind": oh["status"], "element": oh.get("element"),
                                                "magnitude": oh["magnitude"], "turns": oh["turns"]})
                status_applied = oh.get("element")
            # 吸血鬼咬擊傳染「吸血熱」:命中機率 × 疾病抗性削弱(只標記,轉化由 vampirism 驅動)
            inf = attacker.attack.get("infect")
            if inf and not defender.is_vampire:
                dmult = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), "disease")
                if dmult > 0 and rng.chance(inf * dmult):
                    infected = True

        # 玩家武器塗毒 → 命中即把毒效附到敵人身上,消耗一次塗層
        if _is_player(attacker) and attacker.weapon_poison and attacker.weapon_poison["charges"] > 0:
            wp = attacker.weapon_poison
            defender.active_effects.append(magic.make_status_effect(wp["status"]))
            poison_applied = wp["name"]
            wp["charges"] -= 1
            if wp["charges"] <= 0:
                attacker.weapon_poison = None

        # 暗殺殘響:偷襲命中但沒秒殺 → 依武器流派留下踉蹌(命中減成)/撕裂傷(DoT),
        # 強度吃潛行+煉金。讓「失手的暗殺」不再是斷崖,而是 combo 的第一段。
        if sneaking and is_alive(defender):
            am = formulas.sneak_aftermath(archetype)
            staggered = bool(am.get("stagger"))
            bleed_mag = 0
            if staggered:
                defender.active_effects.append({"kind": "stagger", "turns": 1})
            if am.get("bleed"):
                bleed_mag = formulas.sneak_bleed_magnitude(
                    attacker.skill("sneak"), attacker.skill("alchemy"))
                defender.active_effects.append({"kind": "dot", "element": "bleed",
                                                "magnitude": bleed_mag,
                                                "turns": formulas.SNEAK_BLEED_TURNS})
            if staggered or bleed_mag:
                aftermath = {"staggered": staggered, "bleed": bleed_mag}

        # 耐久折損:玩家攻擊磨損武器、被擊中磨損護甲
        if _is_player(attacker):
            inventory.degrade_weapon(attacker)
        if _is_player(defender) and defender.equipped:
            inventory.degrade_random_armor(defender, rng)

        # learn-by-doing:攻擊方是玩家 → 練武器;防守方是玩家 → 練護甲
        if _is_player(attacker) and wpn_skill_id:
            skill_events += progression.use_skill(attacker, gamedata, wpn_skill_id,
                                                  formulas.COMBAT_HIT_XP)
        if sneaking:   # 偷襲命中 → 鍛鍊潛行(讓 sneak 也能在戰鬥中成長)
            skill_events += progression.use_skill(attacker, gamedata, "sneak",
                                                  formulas.COMBAT_SNEAK_XP)
        if _is_player(defender):
            skill_events += progression.use_skill(defender, gamedata,
                                                  _player_armor_skill(defender, gamedata),
                                                  formulas.COMBAT_ARMOR_XP)
            if defender_blocking:
                skill_events += progression.use_skill(defender, gamedata, "block",
                                                      formulas.COMBAT_BLOCK_XP)
        if _is_player(attacker):           # 只夾限玩家資源;怪物 hp 已由 _set_hp 夾限
            stats.clamp_resources(attacker)
        if _is_player(defender):
            stats.clamp_resources(defender)
    elif _is_player(defender):             # 敵人攻擊落空 + 防守方是玩家 → 成功閃避 → 鍛鍊雜技
        skill_events += progression.use_skill(defender, gamedata, "acrobatics",
                                              formulas.COMBAT_DODGE_XP)

    return {
        "attacker": _name(attacker), "defender": _name(defender),
        "hit": hit, "damage": dmg_done, "blocked": defender_blocking,
        "skill_events": skill_events, "defender_dead": not is_alive(defender),
        "absorbed": absorbed, "status_applied": status_applied, "poison_applied": poison_applied,
        "sneak": sneak_mult, "self_restored": self_restored, "infected": infected,
        "aftermath": aftermath,
    }


def player_attack_cost(player: Character, gamedata: GameData | None = None) -> None:
    """玩家攻擊一擊消耗體力(運動越高越省;慢重武器更耗、輕快武器更省)。"""
    speed = formulas.WEAPON_SPEED_DEFAULT
    if gamedata is not None:
        speed = gamedata.item(player.weapon).get("speed", formulas.WEAPON_SPEED_DEFAULT)
    cost = (formulas.ATTACK_FATIGUE_COST
            * formulas.fatigue_cost_factor(player.skill("athletics"))
            * formulas.weapon_attack_fatigue_factor(speed))
    player.fatigue = max(0, player.fatigue - cost)


def player_block_cost(player: Character) -> None:
    """玩家舉盾格擋消耗體力(運動越高越省)。"""
    cost = formulas.BLOCK_FATIGUE_COST * formulas.fatigue_cost_factor(player.skill("athletics"))
    player.fatigue = max(0, player.fatigue - cost)


def try_flee(player: Character, creature: Creature, rng: RNG) -> bool:
    return rng.chance(formulas.flee_chance(_speed(player), _agility(player), _speed(creature)))


def grant_loot(player: Character, creature: Creature, gamedata: GameData, rng: RNG) -> dict:
    """結算怪物戰利品,金幣與物品入袋。回傳 {"gold", "items":[(id,qty)]}。"""
    result = loot.creature_loot(creature, rng)
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
                resolve_attack(creature, player, gamedata, rng)
        # 回合結束結算持續傷害/再生/狀態(與 run_battle 一致,讓毒/法術 DoT 生效)
        magic.tick_effects(player, gamedata)
        magic.tick_effects(creature, gamedata)
    winner = "player" if is_alive(player) and not is_alive(creature) else (
        "creature" if not is_alive(player) else "draw")
    return {"winner": winner, "rounds": rounds,
            "player_hp": player.health, "creature_hp": creature.health}
