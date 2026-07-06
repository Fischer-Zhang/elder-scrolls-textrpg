"""R124 試煉指引:讓 33+ 深層試煉(戴德拉神殿 / 九神祭壇 / 秘術·聖光終極真言)可被發現。

問題:試煉全靠「走到對的地點 + 達技能/等級閘」被動觸發,流言系統只指向傳說地城(rumor_quest),
從不指向試煉 → 玩家常「夠格卻不知試煉存在」。本模組是三層指引的共用衍生層:
  ① 門檻觸發提示(main.py game_loop·session 暫態去重·鏡像 R55 achievements·零存檔欄)
  ② NPC 流言指向(dialogue.offered_rumor 讀 npc.rumor_trial → 揭露試煉地點)
  ③ codex 索引(console._trial_index_rows → magic_schools dynamic 鉤子)

純衍生:讀 quests/world/char,複用 quests.available_quests(已濾 requires_skill/level/fame/faction/event
+ 未接未完成)→ 夠格試煉一目了然。零新存檔欄。
"""
from tesrpg.gamedata import GameData
from tesrpg.models import Character

# 試煉族:(quest source, world 地點 tag, quest 的 site 欄, 族名, 一句指引)
FAMILIES = [
    ("daedric", "shrine",        "shrine",      "戴德拉神殿",
     "諸親王的低語掠過你的心神 —— 你已有資格踏上戴德拉神殿的試煉。八省的神殿各有一位親王在等待夠格者"
     "(指南『疾病、神殿與誓福』列有神殿一覽)。"),
    ("divine",  "divine",        "divine",      "九神祭壇",
     "九神的目光落在你身上 —— 神性試煉已向你開啟。賽羅迪爾各城的九神祭壇各有一場考驗與一道永久誓福"
     "(指南『九神信仰與朝聖』列有祭壇一覽)。"),
    ("arcane",  "arcane_trials", "arcane_site", "奧術試煉",
     "奧術的低鳴在你指尖迴響 —— 你已夠格挑戰終極真言的試煉。晨風、天際、黑沼澤與帝都的法師公會有"
     "『奧術試煉的引路人』在等你(指南『魔法與六學派』列有試煉一覽)。"),
    ("holy",    "holy_trials",   "holy_site",   "破曉試煉",
     "破曉的餘暉在你掌心微亮 —— 你已夠格承載傳說中的破曉之光。高岩匕落的法師公會有『破曉試煉的引路人』在等你。"),
]

_TAG_BY_SOURCE = {src: tag for src, tag, _, _, _ in FAMILIES}
_SITE_FIELD = {src: sf for src, _, sf, _, _ in FAMILIES}
_HINT = {src: hint for src, _, _, _, hint in FAMILIES}
_FAM_NAME = {src: name for src, _, _, name, _ in FAMILIES}


def location_for_trial(gamedata: GameData, source: str, qid: str) -> dict | None:
    """試煉任務 → 其發起地點 dict(以 site 欄值配對 world 地點 tag)。無則 None。"""
    tag = _TAG_BY_SOURCE.get(source)
    site = (gamedata.quests.get(qid) or {}).get(_SITE_FIELD.get(source, ""))
    if not tag or site is None:
        return None
    for loc in gamedata.world["locations"].values():
        if loc.get(tag) == site:
            return loc
    return None


def eligible_families(char: Character, gamedata: GameData) -> set:
    """玩家目前『夠格但未接/未完成』至少一場試煉的族 → {source}。
    複用 available_quests(已濾所有閘 + active/done)。"""
    from tesrpg.systems import quests
    out = set()
    for src, _, _, _, _ in FAMILIES:
        # 只計「有明確發起地點」的試煉(排除無 site 的通用任務,如九神朝聖 pilgrimage_nine
        # → 神性試煉的提示才在 god-trial〔L15〕真正開啟時觸發,而非朝聖一開局就報)
        if any(location_for_trial(gamedata, src, qid) is not None
               for qid in quests.available_quests(char, gamedata, src)):
            out.add(src)
    return out


# ── ① 門檻觸發提示(session 暫態·鏡像 achievements.seed_seen / update)──────────
def seed_hinted(char: Character, gamedata: GameData) -> set:
    """載入當下已夠格的族 → 種入(視為已知曉,不重報;零存檔欄)。"""
    return set(eligible_families(char, gamedata))


def update(state, gamedata: GameData, hinted: set) -> list:
    """game_loop:本圈『新夠格』的試煉族 → 一次性指路提示(去重靠 session 暫態 hinted)。"""
    events = []
    for src in sorted(eligible_families(state.player, gamedata)):
        if src not in hinted:
            hinted.add(src)
            events.append(_HINT[src])
    return events


# ── ② NPC 流言指路(dialogue rumor_trial → main.py 兌現)──────────────────────
_SITE_POINTER = {
    "shrine":        "{name}({prov})一帶立著一座戴德拉神殿 —— 供奉那位親王,或有試煉與神器等著夠格者。",
    "divine":        "{name}({prov})有座九神的祭壇 —— 虔誠而無愧者,可在此求得神性試煉與一道永久誓福。",
    "arcane_trials": "{name}({prov})的法師公會有位『奧術試煉的引路人』,只授予夠格的破壞或神秘大師 —— 終極真言不在任何法師塔出售。",
    "holy_trials":   "{name}({prov})的法師公會有位『破曉試煉的引路人』,傳說中的破曉之光,只予歷經試煉的復原大師。",
}


def site_pointer(gamedata: GameData, location_id: str) -> str:
    """R124 NPC 指路:依該地點的試煉 tag 生成一句指引(無試煉 tag → 泛泛帶過)。"""
    loc = gamedata.world["locations"].get(location_id, {})
    for tag, tmpl in _SITE_POINTER.items():
        if loc.get(tag):
            return tmpl.format(name=loc.get("name", "?"), prov=loc.get("province", ""))
    return f"{loc.get('name', '那處')}或許藏著些什麼,值得你走一趟。"


# ── ③ codex 索引資料(console._trial_index_rows 用)────────────────────────────
def index_sites(gamedata: GameData) -> list:
    """終極真言試煉一覽(秘術 + 聖光;戴德拉/九神已有各自 codex 索引)→ [(族名, 地名·省, 技能閘)]。"""
    rows = []
    for src in ("arcane", "holy"):
        tag = _TAG_BY_SOURCE[src]
        for qid, q in gamedata.quests.items():
            if q.get("source") != src:
                continue
            loc = location_for_trial(gamedata, src, qid)
            if not loc:
                continue
            rs = q.get("requires_skill") or {}
            gate = "・".join(f"{s} {v}" for s, v in rs.items()) or "—"
            rows.append((_FAM_NAME[src], f"{loc.get('name','?')}({loc.get('province','')})", gate, q.get("name", qid)))
    return rows
