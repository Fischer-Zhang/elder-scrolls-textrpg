"""靈魂 token 死靈經濟(Soul Token Necromancy Economy)—— R106 Phase C。

召喚師的一條**可管理的持久資源迴圈**,把「每次施法花法力」的一次性投入,升級成一條
跨戰鬥經營的靈魂經濟:

  打怪 → 積 `soul_tokens`(每擊殺 +1,里程碑「就地起屍」兼帶再 +1)
  花 token → 造亡者軍團(`raise_thrall`)/ 強化 `reanimate` / 買永久死靈升級
  戰後 → 回收倖存的**真·亡者**(每具 +1 token)

**經濟張力**:對雜兵群,清怪給的 token ≈ 投入的軀體、倖存者退款 → 大致打平;對 solo boss
(1 kill、亡者常全滅)刻意淨虧 → **token 買不過終王牆**(守 mehrunes_dagon 720HP 0%)。永久
死靈升級(亡者護甲/軍團上限/喚魂精算)吸收雜兵農出的盈餘,讓池子不會無限膨脹。

**「只真·亡者」(使用者拍板)**:只有 token 召的骷髏奴僕(`raise_thrall`)與 `reanimate` 復生的
屍體帶 `_undead` 暫態旗 → 參與回收、受「亡者統御」戰力加成、計入軍團上限。元素/魔人維持
純法力經濟,不碰 token。

**紅線**:`soul_tokens`/`necro_upgrades` 是持久欄但**絕不進 attr()/skill()/formulas**;死靈加成只
在 `magic.cast` spawn 時併入召喚物(不碰 `resolve_attack`);永久護甲走 `_armor_rating` 獨立加法
層(絕不寫 base)。刺客 `soul_tokens=0`/`necro_upgrades={}` → 全 helper 回中性 → sim byte-identical。
"""
from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

# --- 常數 -------------------------------------------------------------------
# 死靈經濟解鎖走里程碑(召喚 25·mastery.has_soul_economy·取代舊 base≥25 code 閘·非召喚者零漏出)。
BASE_UNDEAD_CAP = 3        # 同場真·亡者基礎上限(軍團升級每級 +1;base 3 守終王牆,擴到 5 方能磨穿=陡增費用 gated)
NECRO_ARMOR_STEP = 2       # 亡者護甲每級 +N 護甲
NECRO_ARMOR_CAP = 10       # 亡者護甲硬上限(offense-neutral;擴到極致靠陡增的升級費用 gated,非低夾)
NECRO_HEALTH_STEP = 6      # 亡者生命每級 +N 真·亡者最大生命(平坦加值)
NECRO_HEALTH_CAP = 30      # 亡者生命硬上限
# 真·亡者分軸縮放(使用者拍板:**conjuration 技能 → 生命·法術威力 → 攻擊**):
UNDEAD_CONJ_SCALE_FLOOR = 0.4   # 生命:base_skill(conjuration) 0 時的下限(初始更弱)
UNDEAD_CONJ_SCALE_CAP = 1.25    # 生命:conj100 封頂(隨技能線性升)
UNDEAD_ATK_SCALE_CAP = 2.0      # 攻擊:法術威力縮放上限(不含技能;智力威力 × 法袍/法杖/誓福)


# --- 永久死靈升級讀取(讀 char.necro_upgrades;空 → 中性 → 刺客 byte-identical)----------
def undead_field_cap(char: Character) -> int:
    """同場真·亡者上限 = 基礎 + 軍團升級等級。"""
    return BASE_UNDEAD_CAP + int(getattr(char, "necro_upgrades", {}).get("undead_cap", 0))


def undead_armor_bonus(char: Character) -> int:
    """亡者護甲永久全域護甲加成(獨立層,夾 NECRO_ARMOR_CAP;絕不寫 base)。"""
    lv = int(getattr(char, "necro_upgrades", {}).get("undead_armor", 0))
    return min(NECRO_ARMOR_CAP, lv * NECRO_ARMOR_STEP)


def undead_health_bonus(char: Character) -> int:
    """亡者生命永久平坦最大生命加值(套進 magic.cast 召/復生真·亡者;夾 NECRO_HEALTH_CAP)。"""
    lv = int(getattr(char, "necro_upgrades", {}).get("undead_health", 0))
    return min(NECRO_HEALTH_CAP, lv * NECRO_HEALTH_STEP)


def undead_conj_scale(char) -> float:
    """真·亡者**生命**隨 conjuration 技能的縮放乘子:較緩·初始更弱·封頂 UNDEAD_CONJ_SCALE_CAP。
    線性 FLOOR..CAP 隨 base_skill(conjuration)/100(門檻只認 base)。**只餵生命,不餵攻擊**(使用者拍板分軸)。"""
    if not hasattr(char, "base_skill"):
        return 1.0
    conj = char.base_skill("conjuration")
    return min(UNDEAD_CONJ_SCALE_CAP,
               UNDEAD_CONJ_SCALE_FLOOR + (conj / 100.0) * (UNDEAD_CONJ_SCALE_CAP - UNDEAD_CONJ_SCALE_FLOOR))


def undead_attack_scale(char, gamedata) -> float:
    """真·亡者**攻擊**隨**法術威力**縮放:智力威力 × (法袍套裝 + 法杖焦點 + 誓福威力)·**刻意不含 conjuration 技能**
    (技能只餵生命)·夾 UNDEAD_ATK_SCALE_CAP。使用者拍板分軸:技能→生命、法術威力→攻擊。"""
    from tesrpg import formulas
    from tesrpg.systems import inventory
    if not hasattr(char, "attr"):
        return 1.0
    potency = formulas.intelligence_spell_potency(char.attr("intelligence"))   # 智力 → 法術威力(R63)
    gear = (1.0 + inventory.set_spell_power_bonus(char, gamedata)              # 法袍套裝(R68)
            + inventory.staff_spell_power(char, gamedata)                      # 法杖焦點(R77)
            + getattr(char, "boon_spell_power", 0.0))                          # 誓福威力(R78b)
    return min(UNDEAD_ATK_SCALE_CAP, potency * gear)


def thrift_discount(char: Character) -> int:
    """喚魂精算:真·亡者召喚的 token 花費折減(呼叫端 floor 1)。"""
    return int(getattr(char, "necro_upgrades", {}).get("grave_thrift", 0))


# --- 戰鬥中軍團計數 ---------------------------------------------------------
def undead_count(battle: dict | None) -> int:
    """戰場上存活的真·亡者數(供軍團上限判定)。"""
    from tesrpg.systems import combat
    if not battle:
        return 0
    return sum(1 for a in battle.get("allies", [])
               if getattr(a, "_undead", False) and combat.is_alive(a))


# --- R203d 就地起屍(conjuration 75-b · opt_id soul_harvest;使用者 2026-11-22 拍板)-------------------
AUTO_RAISE_SPELL = "reanimate_thrall"   # 起屍參數(滿血 hp_factor 1.0 / 回合 6 + turn_bonus 1)取自「亡者奴役」,但**不收法力 / 體力 / token**


def auto_raise(player, gamedata: GameData, rng, battle: dict, enemies: list):
    """每場戰鬥第一具符合資格的敵屍,於回合末(召喚物計時之前)自動起屍為真·亡者盟友;回傳新盟友,不觸發 → None。
    資格 = 亡者復生既有排除(`magic.reanimate_candidate`:solo 首領 / 已復生 / BOSS 爪牙 / 無此模板)+ 已選就地起屍 + 已解鎖死靈
    經濟 + 本場尚未觸發(`battle["auto_raised"]`)+ 戰場上仍有存活敵人(戰局已定的起屍沒有意義,也不讓它白送勝利回收 token)
    + 亡者軍團未滿(軍團上限滿 → 不耗掉本場那一次,等有空位再起)。取敵群排列順序的第一具(非嚴格死亡先後)。
    🔴 零 rng 於不觸發路徑(未選 → 第一行就返回,逐位元組同舊);起屍公式走 `magic.raise_corpse`(與亡者復生法術同一出處)。
    使用者 2026-11-22 拍板「屍僕」:起出的亡者成為屍僕(`_servant`:不逾時、地城戰後寫回盟友清單跨戰、直到被擊殺;同時一具、獨立於
    契僕名額、仍計入亡者軍團上限);所有自動起屍的亡者標 `_free_raised` → 存活不回收 token。"""
    from tesrpg.systems import combat, magic, mastery
    if not (mastery.auto_raise(player, gamedata) and mastery.has_soul_economy(player, gamedata)):
        return None
    if battle.get("auto_raised") or not any(combat.is_alive(e) for e in enemies):
        return None
    if undead_count(battle) >= undead_field_cap(player):
        return None
    corpse = magic.reanimate_candidate(enemies, gamedata)
    if corpse is None:
        return None
    ratio = player.fatigue / player.max_fatigue if player.max_fatigue > 0 else 0.0
    ally = magic.raise_corpse(player, gamedata, rng, battle, corpse, gamedata.spells[AUTO_RAISE_SPELL]["effect"], ratio)
    ally._free_raised = True   # 免費產物:存活不回收 token(未付費就沒有退款;否則不逾時的屍僕等於每場白送 1 token)
    if not any(getattr(a, "_servant", False) and combat.is_alive(a) for a in battle.get("allies", []) if a is not ally):
        ally._servant = True   # 屍僕:不逾時、可跨地城戰鬥(戰後寫回盟友清單);同時一具,獨立於契僕名額;已有屍僕時這具是普通限時亡者
    battle["auto_raised"] = True
    return ally


# --- token 花費(真·亡者召喚/復生;吃喚魂精算折減)---------------------------
def spend_cost(char: Character, base_cost: int) -> int:
    """真·亡者召喚/復生的實際 token 花費 = 基礎 − 喚魂精算(**可降至 0**·使用者拍板)。
    無 token_cost(base 0)回 0;精算滿級可讓便宜亡者(復生1/奴役2)完全免費,raise_thrall(3)仍 ≥1(守牆)。"""
    if base_cost <= 0:
        return 0
    return max(0, base_cost - thrift_discount(char))


# --- 永久死靈升級購買(靈魂 token 買斷·資料驅動目錄 gamedata.necromancy)-----------
def upgrade_level(char: Character, upgrade_id: str) -> int:
    return int(getattr(char, "necro_upgrades", {}).get(upgrade_id, 0))


def upgrade_max_level(cat: dict) -> int:
    return len(cat["costs"])


def buy_upgrade(char: Character, gamedata: GameData, upgrade_id: str) -> dict:
    """花 soul_tokens 升一級永久死靈升級(**每級費用陡增** costs[cur];使用者拍板:可推極致但難)。回傳 {ok, message}。"""
    cat = gamedata.necromancy.get(upgrade_id)
    if not cat:
        return {"ok": False, "message": "未知的死靈升級。"}
    mx = upgrade_max_level(cat)
    cur = upgrade_level(char, upgrade_id)
    if cur >= mx:
        return {"ok": False, "message": f"{cat['name']}已臻極致(等級 {cur}/{mx})。"}
    cost = int(cat["costs"][cur])
    if getattr(char, "soul_tokens", 0) < cost:
        return {"ok": False, "message": f"靈魂 token 不足(需 {cost},餘 {getattr(char, 'soul_tokens', 0)})。"}
    char.soul_tokens -= cost
    char.necro_upgrades[upgrade_id] = cur + 1
    return {"ok": True,
            "message": f"你以 {cost} 枚靈魂 token 精進了「{cat['name']}」(等級 {cur + 1}/{mx},餘 {char.soul_tokens})。"}


# --- 戰後結算:擊殺給予 + 倖存真·亡者回收 -----------------------------------
def harvest_and_recover(player: Character, gamedata: GameData,
                        num_kills: int, allies: list) -> dict:
    """勝利結算:擊殺給 token(含「就地起屍」兼帶的 +1)+ 回收倖存真·亡者。回傳 {gained, recovered, message}。"""
    from tesrpg.systems import combat, mastery
    if not mastery.has_soul_economy(player, gamedata):   # 死靈經濟里程碑未解鎖(召喚 25)→ 不積 token
        return {"gained": 0, "recovered": 0, "message": None}
    per_kill = 1 + mastery.soul_harvest_bonus(player, gamedata)
    gained = max(0, num_kills) * per_kill
    recovered = sum(1 for a in (allies or [])
                    if getattr(a, "_undead", False) and combat.is_alive(a)
                    and not getattr(a, "_free_raised", False))   # R203d 就地起屍的免費亡者不回收(沒付 token 就沒有退款)
    total = gained + recovered
    if total <= 0:
        return {"gained": 0, "recovered": 0, "message": None}
    player.soul_tokens = getattr(player, "soul_tokens", 0) + total
    if recovered:
        msg = (f"你收割了戰場的靈魂(+{gained}),並召回 {recovered} 具倖存亡者的魂魄"
               f"(+{recovered})—— 靈魂 token 共 {player.soul_tokens}。")
    else:
        msg = f"你收割了戰場的靈魂(靈魂 token +{gained},共 {player.soul_tokens})。"
    return {"gained": gained, "recovered": recovered, "message": msg}
