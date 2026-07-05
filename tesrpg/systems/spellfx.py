"""實用/幻術魔法的限時自我增益層(R104)。

讓魔法首次在**戰鬥外**有意義 —— 幻術「魅惑 charm」「隱形 invisibility」+ 變換「羽落 feather」
「偵知 detect_life」施放後,在 `char.spell_effects` 記一筆 `{kind, magnitude, expires_at}`
(絕對小時到期):社交(魅惑)、潛行(隱形)、探索(負重/偵知)。

設計沿用限時藥水(potion_buff.py)的「限時獨立層」骨架,但更輕:**純到期、無推導快取** ——
社交/負重/潛行的加成皆由 helper on-the-fly 讀 `spell_effects`,不寫任何 base、不需 recompute。
每圈 `spellfx.update` 掛 game_loop 剔過期;helper 只認「仍在清單中的效果」為生效(= 由 update
負責時基剔除,同 potion_buff「cache 只留未過期」的模式)。

紅線:**絕不寫 base**;隱形重置戰鬥偷襲先機仍受 combat 的 SOLO_SNEAK 夾(見 main.run_battle);
`calm` 安撫不在此層 —— 它是敵方 active_effects 控場,走 `magic.apply_control`(R44)。

平衡數值(R104·使用者逐項拍板):魅惑逐面加成、隱形遭遇折減、羽落負重量皆常數在此集中。
"""

from __future__ import annotations

from tesrpg.models import Character

# --- 魅惑 charm:逐面社交加成(使用者拍板「逐面不同幅度」)-------------------
CHARM_PERSUADE_BONUS = 0.12    # 說服 persuade_chance / 套話 pry_chance
CHARM_TALK_DOWN_BONUS = 0.10   # 化解衛兵/賞金 talk_down_chance
CHARM_BARTER_BONUS = 0.08      # 商人議價 _disposition_factor(買賣同利)
CHARM_STEAL_BONUS = 0.10       # 行竊得手率 crime.steal_chance
CHARM_BOUNTY_FACTOR = 0.7      # 行竊失風賞金 ×(crime.steal_item;「兩者都要」)
# --- 隱形 invisibility ------------------------------------------------------
INVIS_ENCOUNTER_FACTOR = 0.4   # 隱形時旅途遭遇率 ×(world.travel;越小越安全)
# --- 羽落 feather -----------------------------------------------------------
FEATHER_CARRY_BONUS = 50       # 負重上限 +(inventory.max_weight)


def _valid(e) -> bool:
    return isinstance(e, dict) and isinstance(e.get("kind"), str) and isinstance(e.get("expires_at"), int)


def _has(char: Character, kind: str) -> bool:
    return any(_valid(e) and e["kind"] == kind for e in getattr(char, "spell_effects", []))


def _drop(char: Character, kind: str) -> None:
    se = getattr(char, "spell_effects", None)
    if isinstance(se, list):
        se[:] = [e for e in se if not (_valid(e) and e["kind"] == kind)]


# --- 幻術魅惑 charm(社交)---------------------------------------------------
def is_charmed(char: Character) -> bool:
    return _has(char, "charm")


def charm_persuade_bonus(char: Character) -> float:
    return CHARM_PERSUADE_BONUS if is_charmed(char) else 0.0


def charm_talk_down_bonus(char: Character) -> float:
    return CHARM_TALK_DOWN_BONUS if is_charmed(char) else 0.0


def charm_barter_bonus(char: Character) -> float:
    return CHARM_BARTER_BONUS if is_charmed(char) else 0.0


def charm_steal_bonus(char: Character) -> float:
    return CHARM_STEAL_BONUS if is_charmed(char) else 0.0


def charm_bounty_factor(char: Character) -> float:
    return CHARM_BOUNTY_FACTOR if is_charmed(char) else 1.0


# --- 幻術隱形 invisibility(潛行)-------------------------------------------
def is_invisible(char: Character) -> bool:
    return _has(char, "invisibility")


def invis_encounter_factor(char: Character) -> float:
    """旅途遭遇率乘數(隱形 → ×INVIS_ENCOUNTER_FACTOR;否則 1.0 = 既有行為逐位元組同)。"""
    return INVIS_ENCOUNTER_FACTOR if is_invisible(char) else 1.0


def break_invisibility(char: Character) -> None:
    """入戰/攻擊即破隱形(一次偷襲先機後消耗)。"""
    _drop(char, "invisibility")


# --- 變換羽落 feather(負重)------------------------------------------------
def feather_bonus(char: Character) -> int:
    return FEATHER_CARRY_BONUS if _has(char, "feather") else 0


# --- 變換偵知 detect_life(探索)--------------------------------------------
def is_detecting(char: Character) -> bool:
    return _has(char, "detect_life")


def consume_detect(char: Character) -> None:
    """下一場遭遇消耗偵知(揭露敵情 + 給偵查先機)。"""
    _drop(char, "detect_life")


# --- 秘術靈識 arcane_sight / 念力 telekinesis(R121:地城探索/機關)-----------
def is_sensing(char: Character) -> bool:
    """靈識術作用中:地城探索時揭露四鄰(暫時性奧術偵測;Phase B:亦揭露法術封印)。"""
    return _has(char, "arcane_sight")


def is_telekinetic(char: Character) -> bool:
    """念力術作用中:地城中隔空化解陷阱機關(Phase B:亦可撥動遠處封印機栝)。"""
    return _has(char, "telekinesis")


# --- 施放 / 每圈 update / 存檔遷移 ------------------------------------------
def apply(char: Character, state, kind: str, hours: int, magnitude: float = 1.0) -> None:
    """施放實用法術 → 記/刷新一筆限時自我增益(同 kind 取較晚到期 + 取最強量值;不主動推進時間)。"""
    now = state.time.absolute_hours()
    expires = now + max(1, hours)
    if not isinstance(getattr(char, "spell_effects", None), list):
        char.spell_effects = []
    for e in char.spell_effects:
        if _valid(e) and e["kind"] == kind:
            e["expires_at"] = max(e["expires_at"], expires)
            e["magnitude"] = max(e.get("magnitude", 1.0), magnitude)
            return
    char.spell_effects.append({"kind": kind, "magnitude": magnitude, "expires_at": expires})


def update(state, gamedata) -> list[dict]:
    """每圈掛在 game_loop(potion_buff.update 之後):有效果到期則剔除 + 回事件供 UI 報「法術消退」。"""
    char = state.player
    now = state.time.absolute_hours()
    src = getattr(char, "spell_effects", [])
    live = [e for e in src if _valid(e) and e["expires_at"] > now]
    if len(live) == len(src):
        return []
    char.spell_effects = live
    return [{"kind": "spellfx_expire"}]


def ensure_spell_effect_fields(char: Character, time, gamedata) -> None:
    """舊存檔遷移(save_migrations 接線):補欄(dataclass 預設已處理大半)+ 依當前時間剔除過期。"""
    if not isinstance(getattr(char, "spell_effects", None), list):
        char.spell_effects = []
    now = time.absolute_hours()
    char.spell_effects = [e for e in char.spell_effects if _valid(e) and e["expires_at"] > now]
