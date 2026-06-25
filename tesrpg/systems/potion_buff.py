"""限時增益藥水(R30)—— 煉金產出的「強化屬性 / 強化技能 / 抗元素」藥水的持久增益層。

設計沿用斯庫瑪(skooma.py)的「限時獨立層」骨架,但更單純:純到期、無成癮/戒斷。

  飲下增益藥水 → 在 `char.potion_buffs` 記一筆 `{kind,param,magnitude,expires_at}`(絕對小時到期)。
  三個推導快取 `potion_attr_bonus / potion_skill_bonus / potion_resist` 由 potion_buffs 重算而來,
  讓 `attr()/skill()/entity_resist()` 不帶 gamedata 也能即時讀(同 skooma/裝備/里程碑模式)。

紅線(與全系統加成層一致):**增益走獨立 potion_* 層、絕不寫回 base**;成長/夾限只用 base_*。
疊加規則:**同 (kind,param) 取最強量值 + 取較晚到期**(刷新或取最強),不相加 → 杜絕灌多瓶疊強度;
不同 param 各自獨立疊。`active_effects`(戰鬥內護盾/再生)不在此層 —— 那是入場即清、不入檔的另一條路。

效果 kind 採「參數內嵌」字串(`fattr_<屬性>` / `fskill_<技能>` / `resist_<元素>`),如此煉金的
「共有效果」偵測(以 kind 比對)天然要求同參數才算共有(見 alchemy.brew)。本層解析前綴還原成
與附魔同形的 fortify_attribute / fortify_skill / resist_element 效果(見 synth.synthesize)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats

_ATTR_CN = {"strength": "力量", "intelligence": "智力", "willpower": "意志", "agility": "敏捷",
            "speed": "速度", "endurance": "耐力", "personality": "魅力", "luck": "幸運"}
_RESIST_CN = {"fire": "烈焰", "frost": "冰霜", "shock": "雷電", "poison": "毒素", "disease": "疾病", "magic": "魔法"}


class _TimeState:
    """ensure 等情境下,以單一 GameTime 餵給只讀 `state.time` 的內部函式的輕量殼(仿 skooma)。"""

    def __init__(self, time):
        self.time = time


def _now(state) -> int:
    return state.time.absolute_hours()


def _valid(b) -> bool:
    """防呆:壞值(缺欄/型別不對)一律視為無效,recompute 時剔除。"""
    return (isinstance(b, dict) and isinstance(b.get("kind"), str)
            and b.get("param") is not None and isinstance(b.get("magnitude"), (int, float))
            and isinstance(b.get("expires_at"), int))


# ======================================================================
# 推導快取 + 重算
# ======================================================================
def recompute(char: Character, state, gamedata: GameData) -> None:
    """剔除過期/壞值,由現存 potion_buffs 重建三個快取層,並重算衍生資源上限(R05)。"""
    now = _now(state)
    char.potion_buffs = [b for b in char.potion_buffs if _valid(b) and b["expires_at"] > now]
    attr: dict[str, int] = {}
    skill: dict[str, int] = {}
    resist: dict[str, int] = {}
    for b in char.potion_buffs:
        if b["kind"] == "fortify_attribute":
            attr[b["param"]] = attr.get(b["param"], 0) + b["magnitude"]
        elif b["kind"] == "fortify_skill":
            skill[b["param"]] = skill.get(b["param"], 0) + b["magnitude"]
        elif b["kind"] == "resist_element":
            resist[b["param"]] = resist.get(b["param"], 0) + b["magnitude"]
    char.potion_attr_bonus = attr
    char.potion_skill_bonus = skill
    char.potion_resist = resist
    stats.recompute_max_resources(char, gamedata)   # 強意志/耐力 → 體力上限等衍生資源


def _buff_label(kind: str, param: str, magnitude: int, gamedata: GameData) -> str:
    if kind == "fortify_attribute":
        return f"強化{_ATTR_CN.get(param, param)} +{magnitude}"
    if kind == "fortify_skill":
        nm = gamedata.skills[param]["name"] if gamedata and param in gamedata.skills else param
        return f"強化{nm} +{magnitude}"
    if kind == "resist_element":
        return f"抗{_RESIST_CN.get(param, param)} +{magnitude}%"
    return ""


# ======================================================================
# 飲用 / 每圈 update / 存檔遷移
# ======================================================================
def apply_buff(char: Character, state, gamedata: GameData,
               kind: str, param: str, magnitude: int, hours: int) -> str:
    """飲下一瓶增益藥水:記/刷新一筆增益(同 kind+param 取最強量值 + 取較晚到期),重算快取。
    回傳人類可讀標籤(供 UI 報「強化XX +N」)。不主動推進時間(由呼叫端推進)。"""
    now = _now(state)
    expires = now + max(1, hours)
    for b in char.potion_buffs:
        if _valid(b) and b["kind"] == kind and b["param"] == param:
            b["magnitude"] = max(b["magnitude"], magnitude)
            b["expires_at"] = max(b["expires_at"], expires)
            break
    else:
        char.potion_buffs.append({"kind": kind, "param": param,
                                  "magnitude": magnitude, "expires_at": expires})
    recompute(char, state, gamedata)
    return _buff_label(kind, param, magnitude, gamedata)


def update(state, gamedata: GameData) -> list[dict]:
    """每圈掛在 game_loop(skooma.update 之後):有增益到期則重算 + 回事件供 UI 報「藥力散去」。

    事件 kind:`expire`(本圈剛到期的增益清單)。
    """
    char = state.player
    now = _now(state)
    expired = [b for b in char.potion_buffs if _valid(b) and b["expires_at"] <= now]
    if not expired:
        return []
    recompute(char, state, gamedata)
    return [{"kind": "expire", "buffs": expired}]


def ensure_potion_fields(char: Character, time, gamedata: GameData) -> None:
    """舊存檔遷移(state.from_dict 接線):補欄(dataclass 預設已處理大半)+ 依當前時間重算
    → 載入當下即正確(已過期的增益直接剔除;同 skooma/mastery 的 recompute-on-load)。"""
    if not isinstance(getattr(char, "potion_buffs", None), list):
        char.potion_buffs = []
    if not isinstance(getattr(char, "potion_attr_bonus", None), dict):
        char.potion_attr_bonus = {}
    if not isinstance(getattr(char, "potion_skill_bonus", None), dict):
        char.potion_skill_bonus = {}
    if not isinstance(getattr(char, "potion_resist", None), dict):
        char.potion_resist = {}
    recompute(char, _TimeState(time), gamedata)
