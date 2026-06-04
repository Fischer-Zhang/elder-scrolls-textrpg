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
    """隨機遭遇一「群」敵人:多半 1 隻,偶爾成群(2–3 隻)。"""
    roll = rng.random()
    size = 1 if roll < 0.6 else (2 if roll < 0.88 else 3)
    return [random_encounter(gamedata, player_level, rng, max_danger) for _ in range(size)]


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
                   defender_blocking: bool = False) -> dict:
    """attacker 攻擊 defender,套用傷害、發放玩家技能 xp。回傳事件 dict。

    事件:{"attacker","defender","hit":bool,"damage":int,"blocked":bool,
           "skill_events":[...], "defender_dead":bool}
    """
    wpn_dmg, wpn_skill, wpn_skill_id = _weapon_profile(attacker, gamedata)
    fr = _fatigue_ratio(attacker)
    chance = formulas.hit_chance(wpn_skill, _agility(attacker), _agility(defender),
                                 fr, defender_blocking)
    skill_events: list[dict] = []
    hit = rng.chance(chance)
    dmg_done = 0
    absorbed = False
    status_applied = None
    poison_applied = None

    if hit:
        cond_mult = inventory.weapon_damage_mult(attacker) if _is_player(attacker) else 1.0
        raw = formulas.attack_damage(wpn_dmg, wpn_skill, _strength(attacker),
                                     rng.roll(0.85, 1.15), defender_blocking) * cond_mult
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
            dmg = formulas.damage_after_armor(raw, _armor_rating(defender, gamedata))
            # 武器附魔:額外元素傷害(無視護甲,受對方元素抗性)
            if _is_player(attacker):
                ench = gamedata.item(attacker.weapon).get("enchant")
                if ench and ench.get("kind") == "weapon_element":
                    em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), ench["element"])
                    dmg += magic._scaled_damage(ench["magnitude"], em)

        dmg_done = int(round(dmg))
        _set_hp(defender, _get_hp(defender) - dmg_done)

        # 怪物攻擊的觸發狀態(中毒/凍傷等)→ 加到玩家身上
        if not _is_player(attacker) and _is_player(defender):
            oh = attacker.attack.get("on_hit")
            if oh and rng.chance(oh.get("chance", 1.0)):
                defender.active_effects.append({"kind": oh["status"], "element": oh.get("element"),
                                                "magnitude": oh["magnitude"], "turns": oh["turns"]})
                status_applied = oh.get("element")

        # 玩家武器塗毒 → 命中即把毒效附到敵人身上,消耗一次塗層
        if _is_player(attacker) and attacker.weapon_poison and attacker.weapon_poison["charges"] > 0:
            wp = attacker.weapon_poison
            defender.active_effects.append(magic.make_status_effect(wp["status"]))
            poison_applied = wp["name"]
            wp["charges"] -= 1
            if wp["charges"] <= 0:
                attacker.weapon_poison = None

        # 耐久折損:玩家攻擊磨損武器、被擊中磨損護甲
        if _is_player(attacker):
            inventory.degrade_weapon(attacker)
        if _is_player(defender) and defender.equipped:
            inventory.degrade_random_armor(defender, rng)

        # learn-by-doing:攻擊方是玩家 → 練武器;防守方是玩家 → 練護甲
        if _is_player(attacker) and wpn_skill_id:
            skill_events += progression.use_skill(attacker, gamedata, wpn_skill_id,
                                                  formulas.COMBAT_HIT_XP)
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

    return {
        "attacker": _name(attacker), "defender": _name(defender),
        "hit": hit, "damage": dmg_done, "blocked": defender_blocking,
        "skill_events": skill_events, "defender_dead": not is_alive(defender),
        "absorbed": absorbed, "status_applied": status_applied, "poison_applied": poison_applied,
    }


def player_attack_cost(player: Character) -> None:
    """玩家近戰一擊消耗體力。"""
    player.fatigue = max(0, player.fatigue - formulas.ATTACK_FATIGUE_COST)


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
                player_attack_cost(player)
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
