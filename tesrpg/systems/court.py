"""領主區(宮廷)Phase 2:領主委託 + 武士冊封(Thaneship)。

委託走既有任務引擎(source "ruler";`rulers.json` 的 `quests` 列出各領主的委託線,依序開放);
完成累積該城 `city_standing`(由 quests._complete 反查領主目錄發放)→ 達 THANE_STANDING
即可受封武士(記入 char.thaneships)。武士特權:該省小額賞金衛兵放行、領主賜侍從(housecarl)+ 信物。

加領主委託純改 rulers.json(`quests`)+ quests.json(source "ruler" + reward.standing);
加侍從/信物純改 rulers.json(`housecarl`/`thane_gift`)。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.systems import inventory, quests

THANE_STANDING = 3           # 受封武士所需的城邦功勳
THANE_BOUNTY_FORGIVE = 100   # 武士特權:該省賞金 ≤ 此額,衛兵睜隻眼閉隻眼(大罪仍追緝)

# 程序化領主委託(讓每座有領主的城/鎮都能受封武士):各省一份信物 + 一輪侍從。
# 手寫委託(rulers.json 已有 `quests`,如布魯瑪 + 重點城)會被保留、不被覆蓋。
_PROVINCE_GIFT = {
    "賽羅迪爾": "elven_sword", "天際": "steel_sword", "晨風": "dwarven_mace",
    "黑沼澤": "glass_dagger", "漢默法爾": "steel_mace", "高岩": "elven_sword",
    "瓦倫森林": "glass_dagger", "艾爾斯維爾": "glass_dagger",
}
_HOUSECARLS = ["shieldmaiden", "footman", "veteran", "sellsword", "ranger", "hedge_mage"]


def _province_objectives(gamedata: GameData) -> dict:
    """每省的委託素材池(供同省各城輪替):在地非 solo 生態怪清單(依危險度排序)+ 省內地城清單
    (依危險度排序,各為 (dungeon_key, name))。回傳 {province: (creatures[], dungeons[])}。"""
    w = gamedata.world["locations"]
    out = {}
    for p in {l["province"] for l in w.values() if l["province"] != "邊境"}:
        biomes = {l.get("biome") for l in w.values() if l["province"] == p}
        cands = [(cid, c.get("danger", 1), c.get("min_level", 1)) for cid, c in gamedata.bestiary.items()
                 if set(c.get("biomes", [])) & biomes and not c.get("solo")
                 and c.get("min_level", 1) <= 8 and c.get("danger", 1) <= 4]
        cands.sort(key=lambda x: (x[1], x[2], x[0]))
        creatures = [c[0] for c in cands] or ["wolf"]
        dungeons = sorted(((lid, l.get("danger", 9)) for lid, l in w.items()
                           if l["province"] == p and l["type"] == "dungeon"),
                          key=lambda x: (x[1], x[0]))
        dlist = [(w[lid]["dungeon"], w[lid]["name"]) for lid, _ in dungeons]
        out[p] = (creatures, dlist)
    return out


def _province_forage(gamedata: GameData) -> dict:
    """每省可野採的煉金材料(掃 events.json 採集事件:explore context + provinces + 給 item 的選項)。
    無採集事件的省(如艾爾斯維爾)回空 → 該省委託改走獵殺/懸賞。決定性(sorted)。"""
    out: dict = {}
    for ev in gamedata.events.values():
        tr = ev.get("trigger", {})
        if "explore" not in tr.get("contexts", []):
            continue
        items = sorted({eff["item"] for opt in ev.get("options", [])
                        for eff in opt.get("effects", []) if eff.get("type") == "item"})
        if not items:
            continue
        for p in tr.get("provinces", []):
            for it in items:
                if it not in out.setdefault(p, []):
                    out[p].append(it)
    for p in out:
        out[p].sort()
    return out


def generate_ruler_commissions(gamedata: GameData) -> None:
    """於 gamedata 載入後就地補齊:每座有領主、卻無手寫委託的城/鎮,程序化生成 2 個領主委託
    (q1 +1 / q2 +2 → 滿 THANE_STANDING)並登錄進 gamedata.quests;再補預設信物/侍從。
    手寫委託(已有 `quests`)保留不動,可逐城考據覆寫。
    🔴 反「一批解決整省」:同省各城以**省內序位**輪替不同生態怪 / 地城,且 q1 型別輪替
    (肅清獵殺 / 懸賞較兇怪 / 採辦藥材)→ 打一批怪、清一地城只解到對應的那幾城。
    決定性、冪等(sorted 迭代 + 穩定 qid,每次載入重建相同)。"""
    objs = _province_objectives(gamedata)
    forage = _province_forage(gamedata)
    prov_ord: dict = {}
    for idx, (loc_id, ruler) in enumerate(sorted(gamedata.rulers.items())):
        if ruler.get("quests"):
            continue                                  # 手寫委託(布魯瑪/重點城)→ 不覆蓋
        loc = gamedata.world["locations"].get(loc_id)
        if not loc:
            continue
        p = loc["province"]
        creatures, dlist = objs.get(p, (["wolf"], []))
        nc = len(creatures)
        i = prov_ord.get(p, 0)                         # 省內序位(輪替基準)
        prov_ord[p] = i + 1
        cr = creatures[i % nc]                          # 輪替在地怪(肅清)
        tough = creatures[(nc - 1 - (i // 3)) % nc]     # 偏兇猛端、依型別內序位輪替(懸賞/再肅用)
        mats = forage.get(p, [])
        cname, title, rname = loc["name"], ruler.get("title", ""), ruler.get("name", "")
        q1, q2 = f"ruler_auto_{loc_id}_1", f"ruler_auto_{loc_id}_2"
        kind = i % 3
        if kind == 1:                                  # 懸賞:獵殺較兇猛的在地怪(數少賞高)
            tname = gamedata.bestiary.get(tough, {}).get("name", tough)
            gamedata.quests[q1] = {
                "name": "領主委託:懸賞獵殺", "faction": None, "rank": None, "source": "ruler",
                "objective": {"type": "kill", "creature": tough, "count": 3},
                "reward": {"gold": 180, "fame": 6, "standing": 1}, "turn_in": "auto",
                "text": f"{cname}的{title}{rname}張出懸賞:為禍鄉里的{tname}已奪數命 —— 取其 3 條性命,城邦自有重謝。"}
        elif kind == 2 and mats:                       # 採集:野採在地藥材(無採集事件的省退回獵殺)
            mat = mats[(i // 3) % len(mats)]
            mname = gamedata.item_name(mat)
            gamedata.quests[q1] = {
                "name": "領主委託:採辦藥材", "faction": None, "rank": None, "source": "ruler",
                "objective": {"type": "collect", "item": mat, "count": 5},
                "reward": {"gold": 110, "fame": 4, "standing": 1}, "turn_in": "auto",
                "text": f"{title}{rname}的醫者短缺藥材,委你自{cname}城郊野地採辦{mname} 5 份,以備民疾。"}
        else:                                          # 肅清:獵殺在地生態怪
            crname = gamedata.bestiary.get(cr, {}).get("name", cr)
            gamedata.quests[q1] = {
                "name": "領主委託:肅清城郊", "faction": None, "rank": None, "source": "ruler",
                "objective": {"type": "kill", "creature": cr, "count": 6},
                "reward": {"gold": 120, "fame": 5, "standing": 1}, "turn_in": "auto",
                "text": f"{cname}的{title}{rname}委你肅清城郊作亂的{crname}(獵殺 6 隻),以安民心。"}
        if dlist:                                      # q2:輪替清剿不同省內地城
            dkey, dname = dlist[i % len(dlist)]
            gamedata.quests[q2] = {
                "name": f"領主委託:清剿{dname}", "faction": None, "rank": None, "source": "ruler",
                "objective": {"type": "clear_dungeon", "dungeon": dkey},
                "reward": {"gold": 250, "fame": 10, "standing": 2}, "turn_in": "auto",
                "text": f"{title}{rname}委你清剿為禍一方的{dname},蕩平其中盤踞之敵,證明你配得上{cname}的信賴。"}
        else:                                          # 無地城省 → 再肅(較兇的在地怪)
            tname = gamedata.bestiary.get(tough, {}).get("name", tough)
            gamedata.quests[q2] = {
                "name": "領主委託:再肅邊患", "faction": None, "rank": None, "source": "ruler",
                "objective": {"type": "kill", "creature": tough, "count": 10},
                "reward": {"gold": 250, "fame": 10, "standing": 2}, "turn_in": "auto",
                "text": f"{title}{rname}再委你重創城郊的{tname}巢穴(獵殺 10 隻),徹底安定一方。"}
        ruler["quests"] = [q1, q2]
        ruler.setdefault("thane_gift", _PROVINCE_GIFT.get(p, "elven_sword"))
        ruler.setdefault("housecarl", _HOUSECARLS[idx % len(_HOUSECARLS)])


def ruler_quest_line(gamedata: GameData, loc_id: str) -> list[str]:
    ruler = gamedata.ruler_at(loc_id)
    return ruler.get("quests", []) if ruler else []


def offered_ruler_quest(char: Character, gamedata: GameData, loc_id: str) -> str | None:
    """該城領主目前可接的下一個委託(依序、未完成);已有委託在進行中則回 None。"""
    line = ruler_quest_line(gamedata, loc_id)
    if any(quests.is_active(char, qid) for qid in line):
        return None
    for qid in line:
        if qid in gamedata.quests and not quests.is_done(char, qid):
            return qid
    return None


def standing(char: Character, loc_id: str) -> int:
    return char.city_standing.get(loc_id, 0)


def is_thane(char: Character, loc_id: str) -> bool:
    return loc_id in char.thaneships


def can_become_thane(char: Character, gamedata: GameData, loc_id: str) -> bool:
    return (gamedata.ruler_at(loc_id) is not None
            and not is_thane(char, loc_id)
            and standing(char, loc_id) >= THANE_STANDING)


def make_thane(char: Character, gamedata: GameData, loc_id: str) -> dict:
    """受封武士:記入 thaneships + 授信物(thane_gift)。回傳 {gift, housecarl}。

    **冪等**:已是該城武士時不重複加冊、不重發信物/侍從(回傳 None,避免重複受封刷信物)。
    housecarl 只回傳 id(不直接入隊)—— 由呼叫端依 MAX_PARTY 決定是否隨行。
    """
    was_new = loc_id not in char.thaneships
    if was_new:
        char.thaneships.append(loc_id)
    ruler = gamedata.ruler_at(loc_id) or {}
    gift = ruler.get("thane_gift") if was_new else None
    if gift:
        inventory.add_item(char, gift, 1)
    return {"gift": gift, "housecarl": ruler.get("housecarl") if was_new else None}


def is_thane_in_province(char: Character, gamedata: GameData, province: str) -> bool:
    """玩家是否在該行省享有有效武士特權(賞金寬待用)。

    階段四:武士所在城若**翻給敵方**(已選邊、且該城歸屬 ≠ 你的大義)→ 該城特權**暫停**;
    城再翻回我方即自動恢復(可逆、不動 thaneships)。`char.allegiance` guard 必要:
    未選邊時 faction_of 回種子立場,沒它會誤判所有武士城為翻敵 → 破壞未選邊玩家的特權。
    """
    from tesrpg.systems import politics    # 區域匯入避免循環(politics 只依 gamedata/models)
    for loc_id in char.thaneships:
        loc = gamedata.world["locations"].get(loc_id)
        if not (loc and loc.get("province") == province):
            continue
        if char.allegiance and politics.faction_of(char, gamedata, loc_id) != char.allegiance:
            continue                          # 該城已翻敵 → 此城武士特權暫停
        return True
    return False
