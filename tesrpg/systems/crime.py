"""犯罪與賞金:行竊、各行省賞金、衛兵盤查。

賞金按「行省 (province)」累計;帶著賞金進城會被衛兵攔下。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import progression, world

JAIL_DAYS_PER_BOUNTY = 0.02   # 每點賞金折算坐牢時數的係數

# R109 謀殺目擊/偵測:被撞見才吃賞金(潛殺乾淨無罰)。基礎目擊率依「城守密度」——
# 大城衛兵密佈最難脫身、小鎮次之、野外幾無耳目;再由潛行(背後了結)、夜色掩護遞減。
_MURDER_WITNESS_BASE = {"city": 0.75, "town": 0.55, "wilderness": 0.15, "dungeon": 0.10}
_MURDER_WITNESS_DEFAULT = 0.55            # 未知地點型別的保守值
MURDER_SNEAK_FACTOR = 0.006               # 每點潛行降低目擊率(sneak 100 → −0.60)
MURDER_NIGHT_BONUS = 0.15                 # 夜間(夜色掩護)額外降低目擊率
MURDER_WITNESS_FLOOR = 0.02               # 目擊率下限(再高明也可能倒楣被瞧見)
MURDER_WITNESS_CEIL = 0.95                # 目擊率上限


def province_of(char: Character, gamedata: GameData) -> str:
    return world.current_location(char, gamedata)["province"]


def murder_witness_chance(char: Character, gamedata: GameData, *, night: bool) -> float:
    """一樁謀殺被目擊(→ 追加賞金/惡名)的機率。城守密度(地點型別)為底,潛行+夜色遞減。
    授權獵殺(反間/聖戰)不走此路 → 由呼叫端以 sanctioned 略過。"""
    loc = world.current_location(char, gamedata)
    base = _MURDER_WITNESS_BASE.get(loc.get("type"), _MURDER_WITNESS_DEFAULT)
    chance = base - char.skill("sneak") * MURDER_SNEAK_FACTOR - (MURDER_NIGHT_BONUS if night else 0.0)
    return max(MURDER_WITNESS_FLOOR, min(MURDER_WITNESS_CEIL, chance))


def bounty(char: Character, province: str) -> int:
    return char.bounties.get(province, 0)


def add_bounty(char: Character, province: str, amount: int) -> None:
    char.bounties[province] = char.bounties.get(province, 0) + amount


def clear_bounty(char: Character, province: str) -> None:
    char.bounties[province] = 0


# --- 行竊 ---------------------------------------------------------------
def steal_chance(char: Character, gamedata: GameData) -> float:
    """得手機率:潛行 + 安全為主 + 里程碑「順手牽羊」加成(theft_skill)。夾 [0.05, 0.95]。"""
    from tesrpg.systems import mastery, spellfx
    base = (0.25 + char.skill("sneak") * 0.005 + char.skill("security") * 0.003
            + mastery.theft_bonus(char, gamedata).get("steal_bonus", 0.0)
            + spellfx.charm_steal_bonus(char))   # R104 幻術魅惑術:降低偷竊風險(提高得手率)
    return max(0.05, min(0.95, base))


def steal_item(char: Character, gamedata: GameData, item_id: str, rng: RNG) -> dict:
    """嘗試從商店順手牽羊。回傳 {ok, caught, bounty_added, hours, tired, skill_events}。

    每次嘗試付出潛行 practice 的體力 + 時間成本(由呼叫端推進時間),
    讓行竊不再繞過正規訓練的代價;且**得手才學到手藝**(被抓不給潛行 xp →
    杜絕「故意被抓刷潛行」)。
    """
    from tesrpg.systems import inventory, mastery, spellfx
    province = province_of(char, gamedata)
    value = gamedata.item(item_id)["value"]
    xp, hours, tired = progression.practice_cost(char, gamedata, "sneak")
    if rng.chance(steal_chance(char, gamedata)):
        inventory.add_item(char, item_id, 1)
        events = progression.use_skill(char, gamedata, "sneak", xp)
        return {"ok": True, "caught": False, "bounty_added": 0,
                "hours": hours, "tired": tired, "skill_events": events}
    bf = mastery.theft_bonus(char, gamedata).get("bounty_factor", 1.0)   # 「順手牽羊」失風賞金減免
    fine = int(round(max(20, value * 2) * bf * spellfx.charm_bounty_factor(char)))   # R104 幻術魅惑術:失風賞金 ×0.7
    add_bounty(char, province, fine)
    return {"ok": False, "caught": True, "bounty_added": fine,
            "hours": hours, "tired": tired, "skill_events": []}


# --- 衛兵盤查 -----------------------------------------------------------
def jail_hours(amount: int) -> int:
    return max(6, int(amount * JAIL_DAYS_PER_BOUNTY * 24))


def serve_sentence(char: Character, gamedata: GameData, time) -> dict:
    """入獄服刑:清空當地賞金、推進時間。"""
    province = province_of(char, gamedata)
    amt = bounty(char, province)
    hours = jail_hours(amt)
    time.advance(hours)
    clear_bounty(char, province)
    return {"hours": hours, "cleared": amt}


def pay_fine(char: Character, gamedata: GameData) -> dict:
    province = province_of(char, gamedata)
    amt = bounty(char, province)
    if char.gold < amt:
        return {"ok": False, "owed": amt}
    char.gold -= amt
    clear_bounty(char, province)
    return {"ok": True, "paid": amt}


# --- 通緝身份(純衍生·零存檔欄)------------------------------------------------
#   雙軸刻意不耦合:威脅側讀 active_heat(由賞金衍生·付清/坐牢即降溫=可管理的脫身閥);
#   地下側讀 outlaw_standing(由累積惡名 infamy 衍生·終身·清賞金不抹去)。
#   階梯複用 lycanthropy.tier 的 `sum(1 for thr in THRESHOLDS if v>=thr)` 慣用法。
#   全為只吃 char 的純函式(無 gamedata/rng/state)→ sim/測試/威脅側/地下側共用同一真相源。
ACTIVE_HEAT_THRESHOLDS = (80, 300, 700)      # 最高省賞金 → 路途獵殺 tier 0..3(可清)
OUTLAW_THRESHOLDS = (5, 20, 50)              # 累積惡名 → 地下身份 tier 0..3(終身)
_NOTORIETY_TITLES = ("", "通緝犯", "惡名昭彰", "江湖鬼影")   # outlaw_standing 對應稱號
FENCE_BONUS_BY_TIER = (0.0, 0.15, 0.30, 0.45)   # 銷贓加價(對標盜賊公會 0.40·上限 0.45)


def max_bounty(char: Character) -> int:
    """玩家當前最高的「單一行省」賞金(取最大·非加總)。無賞金 → 0。"""
    return max(getattr(char, "bounties", {}).values(), default=0)


def active_heat(char: Character) -> int:
    """路途獵殺強度 tier(0..3),由最高省賞金衍生 —— 威脅軸·可清(付清/坐牢該省即降溫)。"""
    v = max_bounty(char)
    return sum(1 for thr in ACTIVE_HEAT_THRESHOLDS if v >= thr)


def outlaw_standing(char: Character) -> int:
    """地下身份 tier(0..3),由累積惡名 infamy 衍生 —— 身份軸·終身(清賞金不降)。"""
    v = getattr(char, "infamy", 0)
    return sum(1 for thr in OUTLAW_THRESHOLDS if v >= thr)


def notoriety_tier(char: Character) -> int:
    """惡名總評(UI/世界脈動·取兩軸最大);**不**用於閘戰鬥(戰鬥只讀 active_heat)。"""
    return max(active_heat(char), outlaw_standing(char))


def is_outlaw(char: Character) -> bool:
    """是否亡命徒(可見地下世界):地下身份達 tier1 **或** 當前有賞金在身
    (雙軸:有賞金即開門·累積惡名讓門常開)。"""
    return outlaw_standing(char) >= 1 or max_bounty(char) > 0


def notoriety_title(char: Character) -> str:
    """亡命徒身分稱號(由地下身份 tier;tier0 → 空字串)。"""
    return _NOTORIETY_TITLES[outlaw_standing(char)]


def fence_bonus(char: Character) -> float:
    """銷贓加價倍率(由地下身份 tier;上限 0.45)。"""
    return FENCE_BONUS_BY_TIER[outlaw_standing(char)]
