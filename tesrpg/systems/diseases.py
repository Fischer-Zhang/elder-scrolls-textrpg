"""疾病(Diseases)—— 普通病:被怪傳染的「懲罰層」,治癒前持續、可惡化、部分帶 DoT(R53)。

與斯庫瑪戒斷負層(`systems/skooma.py`)同模式 —— 這是整套疾病層的精確範式:
  - `char.diseases` 為**唯一權威**(已染病 id + 染病絕對小時);`disease_attr_penalty`/`disease_skill_penalty`
    是「由 diseases ∩ diseases.json 決定性推導的**負值快取**」,只疊在 `attr()/skill()` 上,
    **成長/夾限只用 base_***、絕不寫回 base(R03/R05)。
  - **惡化**:部分病每 `worsen.per_days` 日未治 → 懲罰加深一階(夾 `max_steps`)。
  - **DoT**:部分病每 `worsen` 外加 `dot`:每 `per_hours` 小時於 game-loop 扣 `magnitude` 血,
    **clamp 至少留 1 點生命**(選單不致死,死亡只應來自戰鬥,同吸血鬼日照 R19)。

感染走 combat on-hit `disease` 旁路(`atk["disease"]` → run_battle 分派到 `contract`),受**疾病抗性**削弱
(`magic.entity_resist` 的 disease;吸血鬼/狼人 disease:100 → 天然免疫不染)。治癒走統一 `_purify`(藥水/
神殿/法術三途共用),`cure_all` 清空本層;**只解普通病 + 潛伏期,不解已轉化的吸血鬼/狼人深度詛咒**。

🔴 sim:`disease_*_penalty` 對未染病的刺客 fixture 恆為空 dict → `attr()/skill()` 多一項 `+{}.get(k,0)=+0`
→ byte-identical;`disease` on-hit 只加在非 sim 怪。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import stats


class _TimeState:
    """ensure 等情境下,以單一 GameTime 餵給只讀 `state.time` 的內部函式的輕量殼。"""

    def __init__(self, time):
        self.time = time


def _now(state) -> int:
    return state.time.absolute_hours()


# ======================================================================
# 狀態查詢
# ======================================================================
def has_any(char: Character) -> bool:
    return bool(getattr(char, "diseases", None))


def has(char: Character, disease_id: str) -> bool:
    return any(d.get("id") == disease_id for d in getattr(char, "diseases", []) or [])


def active_ids(char: Character) -> list[str]:
    return [d["id"] for d in getattr(char, "diseases", []) or [] if "id" in d]


def _worsen_step(spec: dict, at: int, now: int) -> int:
    """惡化階(0=未惡化或無惡化規則):每 per_days 日未治 +1,夾 max_steps。"""
    w = spec.get("worsen")
    if not w:
        return 0
    days = max(0, (now - at) // 24)
    return min(w.get("max_steps", 0), days // max(1, w.get("per_days", 1)))


# ======================================================================
# 懲罰層(獨立負值層,與斯庫瑪戒斷層同模式)
# ======================================================================
def apply_to_character(char: Character, state, gamedata: GameData) -> None:
    """依 `char.diseases` + 惡化階重算 disease_*_penalty 負層,並重算衍生資源(耐力/意志 → 上限)。

    `state` 提供現在時間(算惡化階);`state=None`(cure 路徑)→ 不惡化(直接清/算基礎)。決定性、可重複呼叫。
    """
    reg = getattr(gamedata, "diseases", {}) or {}
    now = _now(state) if state is not None else 0
    attr: dict[str, int] = {}
    skill: dict[str, int] = {}
    for d in getattr(char, "diseases", []) or []:
        spec = reg.get(d.get("id"))
        if not spec:
            continue                                   # 未知/陳舊 id → 略過(R03 防禦)
        step = _worsen_step(spec, d.get("at", now), now) if state is not None else 0
        w = spec.get("worsen") or {}
        for k, v in spec.get("attr", {}).items():
            attr[k] = attr.get(k, 0) + v + w.get("attr", {}).get(k, 0) * step
        for k, v in spec.get("skill", {}).items():
            skill[k] = skill.get(k, 0) + v + w.get("skill", {}).get(k, 0) * step
    char.disease_attr_penalty = attr
    char.disease_skill_penalty = skill
    stats.recompute_max_resources(char, gamedata)      # 耐力/意志負層 → 衍生資源上限下修(夾)


# ======================================================================
# 感染 / 治癒
# ======================================================================
def contract(char: Character, state, gamedata: GameData, disease_id: str) -> bool:
    """染上一種普通病(去重)。未知 id / 已染 → False。成功 → 加入權威 list + 套負層。"""
    if disease_id not in (getattr(gamedata, "diseases", {}) or {}) or has(char, disease_id):
        return False
    if getattr(char, "diseases", None) is None:
        char.diseases = []
    now = _now(state)
    char.diseases.append({"id": disease_id, "at": now, "dot_at": now})
    apply_to_character(char, state, gamedata)
    return True


def cure_one(char: Character, gamedata: GameData, disease_id: str) -> bool:
    """治好單一普通病。"""
    before = len(getattr(char, "diseases", []) or [])
    char.diseases = [d for d in (getattr(char, "diseases", []) or []) if d.get("id") != disease_id]
    if len(char.diseases) == before:
        return False
    apply_to_character(char, None, gamedata)
    return True


def cure_all(char: Character, gamedata: GameData) -> int:
    """治好所有普通病(神殿/藥水/法術統一治癒的一環)。回傳治好的數量。"""
    n = len(getattr(char, "diseases", []) or [])
    char.diseases = []
    apply_to_character(char, None, gamedata)           # 清層 + recompute
    return n


def purify(char: Character, gamedata: GameData) -> dict:
    """**統一治癒**(藥水/神殿/法術三途共用):治好所有普通病 + 解除吸血熱/狼人熱**潛伏期**。
    🔴 只解普通病 + 潛伏期,**不解已轉化的吸血鬼/狼人**(那仍須各自的深度解咒任務)。
    回傳 {"diseases": 治好數, "vamp_incub": bool, "were_incub": bool}。"""
    from tesrpg.systems import lycanthropy, vampirism
    return {"diseases": cure_all(char, gamedata),
            "vamp_incub": vampirism.cure_infection(char),
            "were_incub": lycanthropy.cure_infection(char)}


def purify_message(res: dict) -> str:
    """把 purify 結果組成玩家訊息;無事可治回提示。"""
    parts = []
    if res["diseases"]:
        parts.append(f"{res['diseases']} 種疾病被滌除")
    if res["vamp_incub"]:
        parts.append("吸血熱在轉化前被斬斷")
    if res["were_incub"]:
        parts.append("狼人熱在轉化前被滌淨")
    if not parts:
        return "你身上並無可淨化的病症。"
    return "一陣暖流滌過全身 —— " + "、".join(parts) + "。"


# ======================================================================
# 每圈 update(掛 game_loop,skooma 之後):惡化推進 + DoT 扣血
# ======================================================================
def update(state, gamedata: GameData) -> list[dict]:
    """處理惡化階推進(層強度變動 → 重算)+ DoT 扣血(watermark,clamp≥1);回傳事件供 UI。

    事件 kind:`worsen`(某病惡化,帶 name)/`dot`(本圈 DoT 扣血,帶 total)。
    """
    char = state.player
    events: list[dict] = []
    if not has_any(char):
        return events
    reg = getattr(gamedata, "diseases", {}) or {}
    now = _now(state)

    # DoT:逐病按 watermark 扣血(每 per_hours 一跳),clamp 至少留 1 點生命
    total_dot = 0
    for d in char.diseases:
        spec = reg.get(d.get("id"))
        dot = (spec or {}).get("dot") if spec else None
        if not dot:
            continue
        per = max(1, dot.get("per_hours", 6))
        ticks = (now - d.get("dot_at", now)) // per
        if ticks > 0:
            dmg = dot.get("magnitude", 0) * ticks
            dmg = min(dmg, max(0.0, char.health - 1))  # 不在選單中病死(死亡只來自戰鬥)
            char.health -= dmg
            d["dot_at"] = d.get("dot_at", now) + ticks * per
            total_dot += int(round(dmg))
    if total_dot > 0:
        events.append({"kind": "dot", "total": total_dot})

    # 惡化:若任何病的惡化階已推進 → 重算負層(決定性:比對快取)
    pa, ps = char.disease_attr_penalty, char.disease_skill_penalty
    apply_to_character(char, state, gamedata)
    if char.disease_attr_penalty != pa or char.disease_skill_penalty != ps:
        events.append({"kind": "worsen"})
    return events


# ======================================================================
# 存檔遷移 + UI
# ======================================================================
def ensure_disease_fields(char: Character, time, gamedata: GameData) -> None:
    """舊存檔遷移(state.from_dict 接線):補欄(dataclass 預設已處理大半)+ 依當前時間重算負層
    → 載入當下即正確(惡化階即時反映;同 skooma recompute-on-load)。"""
    if getattr(char, "diseases", None) is None:
        char.diseases = []
    if getattr(char, "disease_attr_penalty", None) is None:
        char.disease_attr_penalty = {}
    if getattr(char, "disease_skill_penalty", None) is None:
        char.disease_skill_penalty = {}
    apply_to_character(char, _TimeState(time), gamedata)


def active_labels(char: Character, gamedata: GameData) -> list[str]:
    """供角色卡:當前疾病的名稱 + 症狀。"""
    reg = getattr(gamedata, "diseases", {}) or {}
    out = []
    for d in getattr(char, "diseases", []) or []:
        spec = reg.get(d.get("id"))
        if spec:
            out.append(f"{spec['name']} —— {spec.get('symptom', '')}")
    return out


def legacy_label(char: Character) -> str | None:
    n = len(getattr(char, "diseases", []) or [])
    return f"染病({n})" if n else None
