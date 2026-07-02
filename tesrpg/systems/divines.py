"""九神信仰(R107):單槽限時祝福 + 德行閘 + 朝聖贖罪的引擎層。

正典模型(3E 433;UESP 考據):
  - **Skyrim 排他單槽祝福**:同時只能持有一位神的祝福,拜新壇即整包覆蓋、祈禱附帶淨疾。
  - **Oblivion 德行閘**:惡名高於名聲、或本省有通緝賞金 → 神明拒賜福(「懺悔你的罪行吧,惡徒!」)。
  - **KotN 朝聖贖罪**:走「朝聖之路」試煉任務(quests.json `pilgrimage_nine`)→ 惡名歸零
    (全遊戲唯一 infamy 清除途徑;刻意反轉 R84「惡名終身」—— 使用者拍板的例外)。

骨架 = potion_buff(有 attr/resist 推導快取 → 需 recompute)× spellfx(功能加成由 getter on-the-fly 讀)。
`char.divine_blessing` 為唯一權威({"divine","expires_at"} 絕對小時;{}=無);單槽=dict 非 list →
「同時只能一個、新覆蓋舊」由資料形狀結構性保證。到期剔除由 game_loop 的 update 負責(戰鬥中不掉層,
同 potion 慣例);getter 只認仍在槽中的祝福。

紅線:**絕不寫 base**(attr 走 divine_attr_bonus 疊加層);祝福不含 sneak/武器技能(比照 R45 誓福紅線;
塔洛斯力量 +10 有 R92 fortify-strength 的 sim 先例,且 sim fixture 空槽 → 全 hook 恆等 = byte-identical)。
平衡數值(使用者核准計畫拍板)集中在本模組頂。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats

BLESSING_HOURS = 48       # 祝福時長(絕對小時)
BLOCK_FLOOR = 0.25        # 斯丹達爾格擋加成後 block_factor 下限(防疊到近免傷)
PILGRIMAGE_QID = "pilgrimage_nine"   # 朝聖之路任務 id(quests.json)

# 登錄表(powers.POWERS R83 模式;佈點欄在 world.json 各地點 "divine")。
# attr 型走 divine_attr_bonus 快取層、resist 型走 divine_resist;功能型(travel/buy/heal/block)由
# 專屬 getter on-the-fly 讀 —— 對映正典:Oblivion 祈願祠屬性軸 × Skyrim 功能軸混搭,每神一條身份。
BLESSINGS = {
    "akatosh":  {"name": "阿卡托什", "title": "時間之龍神", "attr": {"speed": 10},
                 "desc": "速度 +10"},
    "arkay":    {"name": "阿爾凱", "title": "生死輪迴之神", "resist": {"disease": 30},
                 "desc": "疾病抗性 +30%"},
    "dibella":  {"name": "蒂貝拉", "title": "美與愛之女神", "attr": {"personality": 10},
                 "desc": "個性 +10"},
    "julianos": {"name": "朱利安諾斯", "title": "智慧與魔法之神", "attr": {"intelligence": 10},
                 "desc": "智力 +10"},
    "kynareth": {"name": "凱娜瑞絲", "title": "天穹與旅人之女神", "travel_bonus": 0.10,
                 "desc": "旅途更迅捷"},
    "mara":     {"name": "瑪拉", "title": "慈愛之母神", "heal_bonus": 0.15,
                 "desc": "治療法術 +15%"},
    "stendarr": {"name": "斯丹達爾", "title": "慈悲與正義之神", "block_bonus": 0.10,
                 "desc": "格擋減傷 +10%"},
    "zenithar": {"name": "澤尼薩爾", "title": "勞動與商業之神", "buy_factor": 0.90,
                 "desc": "買價 −10%"},
    "talos":    {"name": "塔洛斯", "title": "人皇英雄神", "attr": {"strength": 10},
                 "desc": "力量 +10"},
}


class _TimeState:
    """ensure 等情境下,以單一 GameTime 餵給只讀 `state.time` 的內部函式的輕量殼(仿 potion_buff)。"""

    def __init__(self, time):
        self.time = time


def _valid(b) -> bool:
    """防呆:壞值(缺欄/型別不對/未知神)一律視為無效。"""
    return (isinstance(b, dict) and isinstance(b.get("divine"), str)
            and b.get("divine") in BLESSINGS and isinstance(b.get("expires_at"), int))


# ======================================================================
# 查詢
# ======================================================================
def active_id(char: Character) -> str:
    """現持祝福的神 id(""=無)。時基剔除由 update/recompute 負責(同 potion 慣例)。"""
    b = getattr(char, "divine_blessing", None)
    return b["divine"] if _valid(b) else ""


def _active_blessing(char: Character) -> dict:
    b = getattr(char, "divine_blessing", None)
    return BLESSINGS[b["divine"]] if _valid(b) else {}


def blessing_label(char: Character, now: int | None = None) -> str:
    """UI 徽記:「⛪ 瑪拉之佑」(可帶剩餘時數)。"""
    b = getattr(char, "divine_blessing", None)
    if not _valid(b):
        return ""
    name = BLESSINGS[b["divine"]]["name"]
    if now is None:
        return f"{name}之佑"
    return f"{name}之佑·餘 {max(0, b['expires_at'] - now)} 時"


# ======================================================================
# 功能型 getter(無祝福 → 恆等值;sim fixture 空槽 → 全 hook byte-identical)
# ======================================================================
def travel_factor_bonus(char: Character, gamedata: GameData | None = None) -> float:
    """凱娜瑞絲:旅行耗時減項(插進 world.travel 既有減項鏈,吃既有 floor 0.5)。"""
    return _active_blessing(char).get("travel_bonus", 0.0)


def buy_price_factor(char: Character) -> float:
    """澤尼薩爾:買價乘數(只買價防 faucet;無祝福 → ×1.0 浮點恆等)。"""
    return _active_blessing(char).get("buy_factor", 1.0)


def heal_power_bonus(char: Character) -> float:
    """瑪拉:cast 治療加成(與九神騎士團 restoration_boon 同槽相加;僅 heal kind)。"""
    return _active_blessing(char).get("heal_bonus", 0.0)


def block_bonus(char: Character) -> float:
    """斯丹達爾:格擋減傷加成(combat 端 `_is_player` + `if _db:` 雙 gate)。"""
    return _active_blessing(char).get("block_bonus", 0.0)


# ======================================================================
# 德行閘(Oblivion 正典)
# ======================================================================
def can_bless(char: Character, province: str) -> tuple[bool, str]:
    """名聲須不低於惡名、且本省無通緝賞金,神明才肯賜福。回 (ok, 拒因 ""|"bounty"|"infamy")。

    新角 fame=infamy=0 → 放行(正典是「惡名超過名聲」才拒,非要求先有名聲)。
    他省賞金不擋(各省法度各管各的;infamy 是全域道德軸才全域擋)。
    """
    from tesrpg.systems import crime   # 區域 import:避免 divines→crime→world→combat 頂層鏈
    if crime.bounty(char, province) > 0:
        return False, "bounty"
    if char.infamy > char.fame:
        return False, "infamy"
    return True, ""


# ======================================================================
# 受福 / 重算 / 每圈 update / 存檔遷移
# ======================================================================
def recompute(char: Character, state, gamedata: GameData) -> None:
    """剔除過期/壞值 → 由現持祝福重建 attr/resist 快取 → 重算衍生資源上限(R05:
    智力→魔力、力量→體力皆 live,必帶 gamedata)。"""
    now = state.time.absolute_hours()
    b = getattr(char, "divine_blessing", None)
    if not _valid(b) or b["expires_at"] <= now:
        char.divine_blessing = {}
    bl = _active_blessing(char)
    char.divine_attr_bonus = dict(bl.get("attr", {}))
    char.divine_resist = dict(bl.get("resist", {}))
    stats.recompute_max_resources(char, gamedata)


def bless(char: Character, state, gamedata: GameData, god: str) -> dict:
    """祭壇祈禱受福:單槽整包覆寫(拜新壇即覆蓋)+ recompute。

    回 {"god", "replaced"}(replaced=被覆蓋的舊神 id,同神刷新/原本無祝福則 "";供 UI 敘事)。
    德行閘與淨疾由呼叫端(main.action_divine_altar)處理 —— 本函式只管祝福本身。
    """
    prev = active_id(char)
    char.divine_blessing = {"divine": god,
                            "expires_at": state.time.absolute_hours() + BLESSING_HOURS}
    recompute(char, state, gamedata)
    return {"god": god, "replaced": prev if prev and prev != god else ""}


def update(state, gamedata: GameData) -> list[dict]:
    """每圈掛在 game_loop(spellfx.update 之後):祝福到期則清槽重算 + 回事件供 UI 報「神恩散去」。"""
    char = state.player
    b = getattr(char, "divine_blessing", None)
    if not _valid(b):
        if b:   # 壞值靜默清掉(防呆)
            char.divine_blessing = {}
        return []
    if b["expires_at"] > state.time.absolute_hours():
        return []
    god = b["divine"]
    recompute(char, state, gamedata)
    return [{"kind": "blessing_expire", "god": god, "name": BLESSINGS[god]["name"]}]


def ensure_divine_fields(char: Character, time, gamedata: GameData) -> None:
    """舊存檔遷移(save_migrations 接線):補欄 + 依當前時間重算(載入即剔過期,冪等)。"""
    if not isinstance(getattr(char, "divine_blessing", None), dict):
        char.divine_blessing = {}
    if not isinstance(getattr(char, "divine_attr_bonus", None), dict):
        char.divine_attr_bonus = {}
    if not isinstance(getattr(char, "divine_resist", None), dict):
        char.divine_resist = {}
    recompute(char, _TimeState(time), gamedata)
