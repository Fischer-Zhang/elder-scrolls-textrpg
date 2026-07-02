"""黑暗兄弟會(Dark Brotherhood)—— 血債招募 → 合約晉升 → 夜母祝福。

循環(仿 TES):你**謀殺無辜者** → 血債驚動夜母 → 在你**休息入夢時**,兄弟會使者
現身邀你入會(不像三大公會那樣走進大廳報名)→ 入會後沿「合約」一階階晉升:每階
一張暗殺委託(目標即首領),刀刀見血、爬上聆聽者之位。階級越高,夜母祝福越深
(潛殺更致命),且兄弟會替你「擺平」官府(繳賞金更便宜)。壓軸晉升任務有抉擇:
忠於五戒,或背叛——「淨化」自己的聖所。

設計與本作哲學的調和:這是**真權衡**而非免費強度 —— 入會要先背上謀殺重罪(高額
賞金、惡名、滿城衛兵),換取的是一條專屬刺客 build 的晉升軸與祝福。狀態存在
Character 上(持久、進存檔):入會前的 `murders`/`db_invited`,入會後的階級在
`factions["dark_brotherhood"]`(與其他公會同制)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character

FACTION = "dark_brotherhood"

# --- 血債 / 謀殺 --------------------------------------------------------
BLOOD_DEBT_THRESHOLD = 1     # 謀殺幾名無辜者後,夜母遣使招募(原作:一樁即可)
MURDER_BOUNTY = 500          # 當眾行兇的賞金(謀殺是重罪,遠高於行竊)
MURDER_INFAMY = 2            # 每樁謀殺累加的惡名

# --- 聖所暗號(風味)----------------------------------------------------
SANCTUARY_PASSWORD_Q = "黑暗中可有甜美之語?"
SANCTUARY_PASSWORD_A = "靜謐,我的兄弟/姊妹。"

# --- 五戒(Tenets)------------------------------------------------------
TENETS = [
    "一、絕不背棄夜母,亦不褻瀆暗影之主西斯爾。",
    "二、絕不出賣兄弟會的密令與同袍。",
    "三、絕不竊取契約同袍的目標。",
    "四、絕不傷害兄弟會的同袍。",
    "五、絕不違抗代言人或聆聽者轉達的夜母之意。",
]


# ======================================================================
# 狀態查詢
# ======================================================================
def is_member(char: Character) -> bool:
    return FACTION in char.factions


def rank(char: Character) -> int:
    return char.factions.get(FACTION, -1)


def rank_name(char: Character, gamedata: GameData) -> str:
    idx = rank(char)
    if idx < 0:
        return "非會員"
    ranks = gamedata.factions[FACTION]["ranks"]
    return ranks[min(idx, len(ranks) - 1)]


def has_blood_debt(char: Character) -> bool:
    """血債已足以驚動夜母(且尚未入會)。"""
    return (not is_member(char)) and char.murders >= BLOOD_DEBT_THRESHOLD


def in_rival_faction(char: Character, gamedata: GameData) -> bool:
    """是否身屬與兄弟會勢不兩立的公會(戰士公會)→ 不會被招募。"""
    from tesrpg.systems import factions   # 區域 import 避免循環
    return bool(factions.joined_rivals(char, gamedata, FACTION))


def should_recruit(char: Character, gamedata: GameData) -> bool:
    """休息時是否該觸發招募:有血債、尚未入會、使者尚未現身過、且非對立公會成員。"""
    return (has_blood_debt(char) and not char.db_invited
            and not in_rival_faction(char, gamedata))


# ======================================================================
# 謀殺(血債來源)
# ======================================================================
def record_murder(state, gamedata: GameData, npc_id: str | None = None, *,
                  witnessed: bool = True) -> dict:
    """記下一樁謀殺:血債 +1、抹去 NPC(必然);**賞金/惡名僅在被目擊時追加**(R109 目擊制,
    `witnessed` 預設 True → 既有呼叫端逐位元組不變)。潛殺乾淨(未被目擊)仍計血債、DB 仍會注意
    你的手藝,只是官府一無所知、不加賞金/惡名。

    回傳 {"bounty","province","witnessed"}。實際擊殺戰鬥由上層(main.action_murder)跑。
    """
    from tesrpg.systems import crime   # 區域 import 避免循環

    char = state.player
    char.murders += 1
    province = crime.province_of(char, gamedata)
    added = 0
    if witnessed:
        char.infamy += MURDER_INFAMY
        crime.add_bounty(char, province, MURDER_BOUNTY)
        added = MURDER_BOUNTY
    if npc_id and npc_id not in char.murdered_npcs:
        char.murdered_npcs.append(npc_id)
    return {"bounty": added, "province": province, "witnessed": witnessed}


# ======================================================================
# 招募 / 入會
# ======================================================================
def recruit(char: Character) -> None:
    """夜母使者招募成功 → 正式入會(最低階「新血」),並標記已招募。"""
    from tesrpg.systems import factions   # 區域 import 避免循環
    char.db_invited = True
    factions.join(char, FACTION)


def decline_recruit(char: Character) -> None:
    """婉拒招募:標記使者已現身(不再每次休息重複觸發);日後可自行於聖所入會。"""
    char.db_invited = True


# ======================================================================
# 夜母祝福(被動潛殺加成)與洗白賞金(perk)
# ======================================================================
def launder_cost(char: Character, gamedata: GameData, amount: int) -> int:
    """以兄弟會門路「洗白」一筆賞金的花費(階級越高,門路越廣、越便宜)。"""
    from tesrpg.systems import factions
    discount = factions.perk_value(char, gamedata, FACTION)   # perk: kind=bounty_launder
    return max(0, int(round(amount * (1.0 - discount))))


def launder_bounty(state, gamedata: GameData) -> dict:
    """花錢請兄弟會擺平當地賞金(享階級折扣)。回傳 {ok, paid, cleared, province, owed?}。"""
    from tesrpg.systems import crime
    char = state.player
    province = crime.province_of(char, gamedata)
    amt = crime.bounty(char, province)
    if amt <= 0:
        return {"ok": False, "cleared": 0, "province": province}
    cost = launder_cost(char, gamedata, amt)
    if char.gold < cost:
        return {"ok": False, "owed": cost, "province": province}
    char.gold -= cost
    crime.clear_bounty(char, province)
    return {"ok": True, "paid": cost, "cleared": amt, "province": province}


# ======================================================================
# 一生傳奇:黑暗兄弟會身分標籤
# ======================================================================
def legacy_label(char: Character, gamedata: GameData) -> str | None:
    """一生傳奇的「血業」標籤。會員身分已由公會階級欄呈現,此處只補述謀殺事蹟:
    入會者顯示『黑暗兄弟會·階級(謀殺 N 人)』,純兇手顯示謀殺數;清白者 None。"""
    if is_member(char):
        suffix = f"(謀殺 {char.murders} 人)" if char.murders else ""
        return f"黑暗兄弟會·{rank_name(char, gamedata)}{suffix}"
    if char.murders > 0:
        return f"血債在身的兇手(謀殺 {char.murders} 人)"
    return None
