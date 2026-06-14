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
from tesrpg.systems import inventory, loot, magic, mastery, progression, smithing, stats


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
                    current_hp: int | None = None, max_health_bonus: int = 0) -> Creature:
    """把雇用的同伴生成為我方戰鬥單位。

    current_hp:持久 HP(同伴系統深化;None=滿血登場,向後相容);max_health_bonus:羈絆耐久加成。
    """
    t = gamedata.companions[companion_id]
    mx = t["max_health"] + max_health_bonus
    hp = mx if current_hp is None else max(0, min(int(current_hp), mx))
    return Creature(
        template_id=companion_id, name=t["name"],
        strength=t["strength"], agility=t["agility"], speed=t["speed"],
        max_health=mx, health=hp, armor_rating=t["armor_rating"],
        attack=dict(t["attack"]), loot_gold=[0, 0], loot_table=[],
        flavor=t.get("blurb", ""), danger=0, resist=dict(t.get("resist", {})),
        summon_turns=None,
    )


def alive_list(combatants: list) -> list:
    return [c for c in combatants if is_alive(c)]


def pick_player_side_target(player: Character, allies: list, rng: RNG):
    """敵人選擇攻擊我方目標:偏好玩家(約 55%),其餘平分給存活同伴。

    戰士「盾牆」嘲諷:玩家立盾牆時,把所有敵火力吸到坦身上(只護同袍 HP,不轉嫁傷害)。"""
    living_allies = [a for a in allies if is_alive(a)]
    if has_shield_wall(player):          # 盾牆嘲諷:強制鎖定坦
        return player
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
    return actor.attr("speed") if _is_player(actor) else actor.speed


def _is_beast(actor) -> bool:
    """玩家是否處於狼人獸形(讀快取布林,不需 state)。"""
    return _is_player(actor) and getattr(actor, "beast_form", False)


def _weapon_profile(actor, gamedata: GameData):
    """回傳 (weapon_damage, weapon_skill_level, weapon_skill_id|None)。"""
    if _is_player(actor):
        if _is_beast(actor):     # 獸形:以獸爪戰鬥,略過裝備武器/淬鍊/附魔(資料驅動讀 beast_claws)
            from tesrpg.systems import lycanthropy
            wp = gamedata.item(lycanthropy.BEAST_CLAW)
            return wp["damage"] + lycanthropy.claw_bonus(actor), actor.skill(wp["skill"]), wp["skill"]
        bw = next((e for e in actor.active_effects
                   if e.get("kind") == "bound_weapon" and e.get("turns", 0) > 0), None)
        if bw:   # 召喚「束縛兵刃」:取代裝備武器 → 固定傷害、用咒術技能、不吃淬鍊/附魔/塗毒/耐久(skill_id=None)
            return bw["magnitude"], actor.skill("conjuration"), None
        wp = gamedata.item(actor.weapon)   # 用 item() 以支援附魔(合成)武器
        return wp["damage"] + smithing.weapon_temper_bonus(actor), actor.skill(wp["skill"]), wp["skill"]
    return actor.attack["damage"], actor.attack["skill"], None


def eff_weapon_id(player) -> str:
    """玩家當前實際使用的武器 id(獸形 → beast_claws;否則裝備武器)。"""
    from tesrpg.systems import lycanthropy
    return lycanthropy.BEAST_CLAW if getattr(player, "beast_form", False) else player.weapon


def effective_weapon_name(player, gamedata: GameData) -> str:
    """玩家當前實際使用的武器名(獸形 → 獸爪;否則裝備武器)。供戰鬥/選單標籤。"""
    return gamedata.item(eff_weapon_id(player))["name"]


def _armor_rating(actor, gamedata: GameData) -> int:
    if not _is_player(actor):
        # 同伴也吃 active_shield(盾牆護同袍光環 / 盟友指向護盾術才真生效);敵人無護盾效果 → +0 不變(sim 零位移)
        return actor.armor_rating + magic.active_shield(actor)
    if _is_beast(actor):     # 獸形:脫去穿戴護甲,只剩野獸厚皮的微薄防護(權衡:易受擊,靠巨量血量扛)
        from tesrpg.systems import lycanthropy
        return lycanthropy.BEAST_ARMOR
    worn = inventory.effective_armor_rating(actor, gamedata)   # 已計入耐久折損
    wc = inventory.dominant_weight_class(actor, gamedata)
    if worn == 0 or wc is None:
        base = formulas.player_armor_rating(actor.skill("heavy_armor"), actor.skill("light_armor"))
    else:
        skill = actor.skill("heavy_armor" if wc == "heavy" else "light_armor")
        base = round(worn * (0.5 + skill / 100.0))
    # 被動護甲(石膚/靈體護壁=法系、撐架/柔革護持=物理 stance):里程碑 perk,無條件生效
    # (廣度 pass 加入物理 stance 後不再綁魔力;原「有魔力才生效」對物理 stance 不合理)。
    passive = mastery.passive_armor_bonus(actor, gamedata)
    return base + passive + smithing.armor_temper_bonus(actor) + magic.active_shield(actor)   # 淬鍊 + 變化系護盾疊加


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


def _is_solo(creature, gamedata: GameData) -> bool:
    """該防守單位是否為 BOSS 級(bestiary `solo`)→ 適用「偷襲開場一擊不可致死」夾限。"""
    tid = getattr(creature, "template_id", None)
    return bool(tid and gamedata.bestiary.get(tid, {}).get("solo"))


def _has_deathmark(creature) -> bool:
    """敵身上是否有刺客「致命烙印」(存敵方 active_effects,戰鬥邊界清)。"""
    return any(e.get("kind") == "deathmark" and e.get("turns", 0) > 0
               for e in getattr(creature, "active_effects", []))


def has_shield_wall(char) -> bool:
    """玩家是否處於戰士「盾牆」架勢(存 active_effects 的常駐 stance)。"""
    return any(e.get("kind") == "shield_wall" and e.get("turns", 0) > 0
               for e in getattr(char, "active_effects", []))


def _shield_wall_factor(defender) -> float:
    """盾牆物理減傷倍率(<1.0 = 更耐打);非盾牆 → 1.0。"""
    e = next((e for e in getattr(defender, "active_effects", [])
              if e.get("kind") == "shield_wall" and e.get("turns", 0) > 0), None)
    return (1.0 - e.get("mitigation", 0.0)) if e else 1.0


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


def resolve_attack(attacker, defender, gamedata: GameData, rng: RNG,
                   defender_blocking: bool = False, sneak_attack: bool = False,
                   aimed: bool = False, mounted_charge: bool = False,
                   charge_spec: dict | None = None) -> dict:
    """attacker 攻擊 defender,套用傷害、發放玩家技能 xp。回傳事件 dict。

    sneak_attack:玩家開場偷襲(不察之敵)→ 傷害依潛行加倍、命中下限拉高、鍛鍊潛行。
    mounted_charge:坐騎「衝鋒」戰技(開場、僅野外遭遇)→ 長槍×高倍率 / 其他近戰追加坐騎踐踏;
    **絕不走 sneak_mult**(charge_spec 來自 mounts.charge_spec),對 solo boss 受獨立夾限。

    事件:{"attacker","defender","hit":bool,"damage":int,"blocked":bool,
           "skill_events":[...], "defender_dead":bool, "sneak":倍率|None}
    """
    beast = _is_beast(attacker)     # 獸形:獸爪戰鬥,結構性略過裝備武器/附魔/淬鍊/副手/耐久
    # 召喚「束縛兵刃」:凝出的法系武器「完全取代」裝備武器(比照獸形)→ 不吃裝備武器的塗毒/命中附魔/
    # 耐久/副手/archetype/法杖命中回資源。存效果 dict(供下方 atk_element 取元素);無則 None。
    bound = (next((e for e in attacker.active_effects
                   if e.get("kind") == "bound_weapon" and e.get("turns", 0) > 0), None)
             if _is_player(attacker) and not beast else None)
    # 🔴 紅線:獸形攻擊永不吃偷襲倍率(防禦縱深 —— 即便呼叫端誤傳 sneak_attack=True 亦然;
    # 變身破壞潛行 → solo boss 反一刀夾限不被觸碰)
    sneaking = sneak_attack and _is_player(attacker) and not beast
    wpn_dmg, wpn_skill, wpn_skill_id = _weapon_profile(attacker, gamedata)
    # 雙持副手傷害另計:作為一記「普通補刀」疊上,不吃偷襲倍率(避免偷襲秒精英)。獸形/束縛兵刃無副手。
    offhand_dmg = (inventory.dual_wield_bonus_damage(attacker, gamedata)
                   if _is_player(attacker) and not beast and not bound else 0.0)
    wdef = gamedata.item(attacker.weapon) if _is_player(attacker) and not beast and not bound else None
    archetype = wdef.get("archetype") if wdef else None
    speed = wdef.get("speed", formulas.WEAPON_SPEED_DEFAULT) if wdef else formulas.WEAPON_SPEED_DEFAULT
    fr = _fatigue_ratio(attacker)
    evasion = (formulas.dodge_evasion(defender.skill("acrobatics"))
               + mastery.evasion_bonus(defender, gamedata)
               + _ride_evasion(defender)) if _is_player(defender) else 0.0   # 騎射閃避:聚合相加,不遮蔽
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
    infect_kind = None     # 傳染的詛咒種類("vampire"/"lycanthropy"),供 run_battle 分派
    lifesteal = 0          # 武器吸血附魔本擊回血量(供敘事)
    aftermath = None
    sneak_mult = (formulas.sneak_attack_multiplier(attacker.skill("sneak"))
                  * formulas.archetype_sneak_bonus(archetype)
                  * formulas.night_mother_sneak_bonus(attacker.factions.get("dark_brotherhood", -1))
                  * (1 + mastery.sneak_mult_bonus(attacker, gamedata))   # 里程碑「影刃」:apex 偷襲倍率
                  ) if sneaking else None

    if hit:
        cond_mult = (inventory.weapon_damage_mult(attacker)
                     if _is_player(attacker) and not beast and not bound else 1.0)   # 束縛兵刃不吃裝備武器耐久
        roll = rng.roll(0.85, 1.15)
        block_factor = (formulas.block_damage_factor(defender.skill("block"))
                        if defender_blocking else 1.0)
        raw = formulas.attack_damage(wpn_dmg, wpn_skill, _strength(attacker),
                                     roll, block_factor) * cond_mult
        # 騎士「號令」:帶 empower 增益的攻擊者(同伴)傷害提升 —— **只對同伴施放 → 永不碰玩家偷襲紅線**
        # 以 max 聚合(取最強的一道,非加總)→ 反覆施放號令不疊乘成暴衝;單道仍隨施法 power 成長。
        if not _is_player(attacker):
            emp = max((e.get("magnitude", 0) for e in getattr(attacker, "active_effects", [])
                       if e.get("kind") == "empower" and e.get("turns", 0) > 0), default=0)
            if emp:
                raw *= (1 + emp)
        # 里程碑武器威力 + 弓手「瞄準射」:補傷「不吃偷襲倍率」(同副手補刀模式,守紅線;仍受 solo 夾限)
        power_bonus = raw * (wmod.get("power", 0.0) + (formulas.AIMED_SHOT_POWER if aimed else 0.0))
        # 坐騎「衝鋒」:長槍藉馬勢洞穿(武器傷×高倍率)/ 其他近戰追加坐騎踐踏(flat)。不吃偷襲倍率(charge≠sneak)。
        if mounted_charge and not beast and not bound and charge_spec:
            if archetype == "spear":
                power_bonus += raw * (charge_spec.get("mult_spear", 1.0) - 1.0)
            else:
                power_bonus += charge_spec.get("mount_dmg", 0)
        if sneaking:
            raw *= sneak_mult
        raw += power_bonus
        if offhand_dmg:    # 雙持副手補刀:照常吃技能/力量/耐久,但不吃偷襲倍率
            raw += formulas.attack_damage(offhand_dmg, wpn_skill, _strength(attacker),
                                          roll, block_factor) * cond_mult
        atk_element = None if _is_player(attacker) else attacker.attack.get("element")
        if bound:   # 召喚「束縛兵刃」:法系近戰 → 走元素分支(無視護甲、吃元素抗性;元素分支不讀附魔/灌注 → 不雙吃)
            atk_element = bound.get("element", "magic")
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
                if _is_player(defender):   # 秘術「結界」:先吃法術/元素傷,吸魔結界按吸收量回魔(可耗盡池)
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
            dmg *= mastery.incoming_physical_factor(defender, gamedata)   # 里程碑「壁壘」:物理再減傷
            dmg *= _shield_wall_factor(defender)            # 戰士「盾牆」架勢:物理再減傷(僅物理,元素穿透)
            # 武器附魔:額外元素傷害(無視護甲,受對方元素抗性)。獸形以獸爪戰鬥 → 無附魔
            if _is_player(attacker) and not beast:
                ench = gamedata.item(attacker.weapon).get("enchant")
                if ench and ench.get("kind") == "weapon_element":
                    em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), ench["element"])
                    dmg += magic._scaled_damage(ench["magnitude"], em)
                # 戰法師「奧術灌注」:active weapon_imbue 自我增益 → 近戰加元素傷害
                # (加在 dmg、於 solo 偷襲夾限之前 → 偷襲不放大、solo boss 受夾,守紅線)
                for ie in attacker.active_effects:
                    if ie.get("kind") == "weapon_imbue" and ie.get("turns", 0) > 0:
                        em = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), ie["element"])
                        dmg += magic._scaled_damage(ie["magnitude"], em)
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

        # 里程碑「迅捷連斬」反作用:造成傷害的一部分回噬自身(代價,不致死 → 夾 ≥1)
        if _is_player(attacker) and wmod.get("recoil") and dmg_done > 0:
            attacker.health = max(1, attacker.health - int(round(dmg_done * wmod["recoil"])))

        # 里程碑「重甲反震」:玩家受物理擊中 → 反彈一部分傷害給攻擊者(只物理;攻擊者可被反殺)
        if _is_player(defender) and not atk_element and dmg_done > 0:
            refl = mastery.armor_reflect(defender, gamedata)
            if refl:
                _set_hp(attacker, _get_hp(attacker) - int(round(dmg_done * refl)))

        # 法杖等「命中回復施術者資源」(D:on_hit_self)→ 由後面的 clamp_resources 夾限
        if _is_player(attacker) and wdef and wdef.get("on_hit_self"):
            ohs = wdef["on_hit_self"]
            setattr(attacker, ohs["stat"], getattr(attacker, ohs["stat"]) + ohs["magnitude"])
            self_restored = (ohs["stat"], ohs["magnitude"])
        # 戰法師「法力回擊」:近戰命中回魔(純資源、零傷害 → 零紅線;clamp_resources 夾上限)。
        # 不沿用 self_restored(那是法杖專屬敘事「法杖將生機回流」)→ 無杖揮劍回魔時不誤報法杖;魔力條自會上升。
        if _is_player(attacker) and not beast:
            mox = mastery.mana_on_hit(attacker, gamedata)
            if mox:
                attacker.magicka = attacker.magicka + mox

        # 怪物攻擊的觸發狀態(中毒/凍傷等)→ 加到玩家身上
        if not _is_player(attacker) and _is_player(defender):
            oh = attacker.attack.get("on_hit")
            if oh and rng.chance(oh.get("chance", 1.0)) and not magic.resisted_mind(defender, oh["status"], rng):
                defender.active_effects.append({"kind": oh["status"], "element": oh.get("element"),
                                                "magnitude": oh["magnitude"], "turns": oh["turns"]})
                status_applied = oh.get("element")
            # 疾病傳染(吸血鬼吸血熱 / 狼人狼人熱):命中機率 × 疾病抗性削弱(只標記,轉化由各系驅動)。
            # `infect_kind` 缺省 "vampire"(舊吸血鬼敵向後相容);跨詛咒互斥靠疾病免疫使 dmult=0 自然擋掉,
            # 此處再以 `already` 防同詛咒重複感染。
            inf = attacker.attack.get("infect")
            if inf:
                kind = attacker.attack.get("infect_kind", "vampire")
                already = (defender.is_vampire if kind == "vampire"
                           else getattr(defender, "is_werewolf", False))
                dmult = formulas.resist_multiplier(magic.entity_resist(defender, gamedata), "disease")
                if not already and dmult > 0 and rng.chance(inf * dmult):
                    infected = True
                    infect_kind = kind

        # 玩家武器塗毒 → 命中即把毒效附到敵人身上,消耗一次塗層。獸形/束縛兵刃以非裝備武器戰鬥 → 不沾塗毒
        if (_is_player(attacker) and not beast and not bound
                and attacker.weapon_poison and attacker.weapon_poison["charges"] > 0):
            wp = attacker.weapon_poison
            defender.active_effects.append(magic.make_status_effect(wp["status"]))
            poison_applied = wp["name"]
            wp["charges"] -= 1
            if wp["charges"] <= 0:
                attacker.weapon_poison = None

        # 武器命中觸發附魔(weapon_status:吸血/麻痺/再生)—— 玩家專屬,與元素/毒/里程碑各自獨立、不重複套。
        # 獸形/束縛兵刃以非裝備武器戰鬥 → 無裝備武器附魔
        if _is_player(attacker) and not beast and not bound:
            sench = gamedata.item(attacker.weapon).get("enchant")
            if sench and sench.get("kind") == "weapon_status" and rng.chance(sench.get("chance", 1.0)):
                st = sench["status"]
                if st == "vampiric" and dmg_done > 0:
                    heal = min(int(round(dmg_done * formulas.WEAPON_VAMPIRIC_FRACTION)), dmg_done)
                    before = attacker.health
                    attacker.health = min(attacker.max_health, attacker.health + heal)
                    lifesteal = int(attacker.health - before)
                elif st == "regen":   # self-HoT;以 source 去重(命中刷新不疊加)
                    if not any(e.get("source") == "ench_regen" and e.get("turns", 0) > 0
                               for e in attacker.active_effects):
                        attacker.active_effects.append(
                            {"kind": "regen", "magnitude": sench.get("magnitude", 0),
                             "turns": sench.get("turns", 0), "source": "ench_regen"})
                elif st == "paralyze" and is_alive(defender):
                    # solo BOSS 完全免疫附魔麻痺(反鎖王作弊,比照偷襲秒殺夾限);已麻痺中不重複套
                    if (not _is_solo(defender, gamedata)
                            and not any(e["kind"] == "paralyze" and e["turns"] > 0
                                        for e in defender.active_effects)):
                        defender.active_effects.append({"kind": "paralyze", "turns": sench.get("turns", 1)})
                        status_applied = status_applied or "paralyze"

        # 里程碑武器流派「命中附狀態」(震盪一擊=weaken / 卸力擒拿=stagger)+「盾擊踉蹌」
        if _is_player(attacker) and is_alive(defender):
            ohs = wmod.get("on_hit_status")
            if ohs and rng.chance(ohs.get("chance", 1.0)):
                if ohs["kind"] == "stagger":
                    defender.active_effects.append({"kind": "stagger", "turns": ohs.get("turns", 1)})
                elif ohs["kind"] == "weaken":
                    defender.active_effects.append({"kind": "weaken", "magnitude": ohs.get("magnitude", 0.0),
                                                    "turns": ohs.get("turns", 1)})
        if defender_blocking and _is_player(defender) and is_alive(attacker):
            rp = mastery.block_riposte_chance(defender, gamedata)
            if rp and rng.chance(rp):
                attacker.active_effects.append({"kind": "stagger", "turns": 1})
        # 里程碑「懾心術」:玩家武器命中時施加懼意(illusion 流派的控場)
        if _is_player(attacker) and is_alive(defender):
            foh = mastery.fear_on_hit(attacker, gamedata)
            if foh and rng.chance(foh.get("chance", 0.0)):
                defender.active_effects.append({"kind": "fear", "turns": foh.get("turns", 2)})
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
                defender.active_effects.append({"kind": "stagger", "turns": 1})
            if am.get("bleed"):
                bleed_mag = formulas.sneak_bleed_magnitude(
                    attacker.skill("sneak"), attacker.skill("alchemy"))
                defender.active_effects.append({"kind": "dot", "element": "bleed",
                                                "magnitude": bleed_mag,
                                                "turns": formulas.SNEAK_BLEED_TURNS})
            if staggered or bleed_mag:
                aftermath = {"staggered": staggered, "bleed": bleed_mag}

        # 耐久折損:玩家攻擊磨損武器、被擊中磨損護甲。獸形/束縛兵刃以非裝備武器戰鬥 → 不磨損裝備武器
        if _is_player(attacker) and not beast and not bound:
            inventory.degrade_weapon(attacker)
        if _is_player(defender) and defender.equipped:
            inventory.degrade_random_armor(defender, rng)

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
        "infect_kind": infect_kind, "lifesteal": lifesteal,
        "aftermath": aftermath,
    }


def player_attack_cost(player: Character, gamedata: GameData | None = None) -> None:
    """玩家攻擊一擊消耗體力(運動越高越省;慢重武器更耗、輕快武器更省)。"""
    speed = formulas.WEAPON_SPEED_DEFAULT
    if gamedata is not None:
        wid = "beast_claws" if getattr(player, "beast_form", False) else player.weapon
        speed = gamedata.item(wid).get("speed", formulas.WEAPON_SPEED_DEFAULT)
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
        chance = min(0.95, chance + mastery.flee_bonus(player, gamedata))
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
    armor_class = inventory.dominant_weight_class(player, gamedata)
    return formulas.stealth_approach_chance(
        player.skill("sneak"), foe_agi, len(enemies), armor_class, night, scouted, surprise,
        approach_bonus=mastery.approach_bonus(player, gamedata),       # 「無聲潛近」
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
    archetype = gamedata.item(eff_weapon_id(player)).get("archetype")
    wm = mastery.weapon_mod(player, gamedata, wpn_skill_id)   # 與 resolve_attack 一致
    raw = formulas.attack_damage(wpn_dmg, wpn_skill, _strength(player), 1.0)
    power_bonus = raw * wm.get("power", 0.0)                  # weapon_mod 威力:flat 補傷(不吃偷襲倍率)
    if not beast:    # 🔴 獸形與潛行互斥 → 不套偷襲倍率(與 resolve_attack 的 not beast 守門一致)
        raw *= (formulas.sneak_attack_multiplier(player.skill("sneak"))
                * formulas.archetype_sneak_bonus(archetype)
                * formulas.night_mother_sneak_bonus(player.factions.get("dark_brotherhood", -1))
                * (1 + mastery.sneak_mult_bonus(player, gamedata)))   # 里程碑「影刃」
    raw += power_bonus
    if offhand_dmg:    # 副手補刀不吃偷襲倍率(與 resolve_attack 一致)
        raw += formulas.attack_damage(offhand_dmg, wpn_skill, _strength(player), 1.0)
    pen = min(0.85, formulas.archetype_armor_pen(archetype) + wm.get("pen", 0))
    est = formulas.damage_after_armor(raw, creature.armor_rating, pen)
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
                resolve_attack(creature, player, gamedata, rng)
        # 回合結束結算持續傷害/再生/狀態(與 run_battle 一致,讓毒/法術 DoT 生效)
        magic.tick_effects(player, gamedata)
        magic.tick_effects(creature, gamedata)
    winner = "player" if is_alive(player) and not is_alive(creature) else (
        "creature" if not is_alive(player) else "draw")
    return {"winner": winner, "rounds": rounds,
            "player_hp": player.health, "creature_hp": creature.health}
