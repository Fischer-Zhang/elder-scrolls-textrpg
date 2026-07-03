"""地城輔助:撬鎖(安全技能)、開箱取寶,與再滋擾(R111 重返迴圈)。

地城的逐房間推進是互動流程,放在 main.py;這裡提供可測的純規則。

再滋擾(R111):已清地城隔一段時日被新勢力「重踞」(亡靈→盜匪等主題換血,純
`dungeons.json` `reinfest` 區塊)—— 掃蕩重踞頭目可得其自帶的**較小**寶藏(首通
大寶藏仍唯一),並可接告示板「清剿委託」(`purge_dungeon` objective)。
🔴 鐵律:`cleared_dungeons` 恆單調不減(主線門鏈 `after_cleared`/`until_cleared`、
98 條 `clear_dungeon` 任務、成就/legacy 皆依賴)—— 重踞是**平行的衍生狀態**
(`dungeon_reinfest_at` 時間戳 dict,比照 R110 `house_garden_at` 模式),絕不動
cleared 名單。玩家軍營駐守(char.camp)的地城由駐軍守著、不再滋擾。
"""

from __future__ import annotations

from tesrpg.gamedata import GameData
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import inventory, loot, mastery, progression

# --- 再滋擾(R111)-------------------------------------------------------
REINFEST_CYCLE_DAYS = 15                       # 掃蕩/首通後隔幾日重踞(平衡旋鈕;調整先問)
REINFEST_CYCLE_HOURS = REINFEST_CYCLE_DAYS * 24


def reinfest_block(gamedata: GameData, dungeon_id: str) -> dict | None:
    """該地城的重踞變體區塊(`dungeons.json` `reinfest`;無=永不滋擾)。主線門鏈/
    親王/試煉/聖物等特殊地城刻意不帶此欄。"""
    return (gamedata.dungeons.get(dungeon_id) or {}).get("reinfest")


def dungeon_location_id(gamedata: GameData, dungeon_id: str) -> str | None:
    """dungeon_id → 所在地點 loc_id(掃 world locations;無=孤兒地城,回 None 安全)。"""
    for lid, l in gamedata.world["locations"].items():
        if l.get("dungeon") == dungeon_id:
            return lid
    return None


def is_reinfested(char: Character, gamedata: GameData, dungeon_id: str, now: int) -> bool:
    """該地城當下是否被重踞:已清 + 有變體區塊 + 時間戳到期 + 無玩家軍營駐守。
    重踞狀態**持續到玩家掃蕩為止**(mark_purged 才把時間戳推進未來)。"""
    if dungeon_id not in (getattr(char, "cleared_dungeons", []) or []):
        return False
    if reinfest_block(gamedata, dungeon_id) is None:
        return False
    at = getattr(char, "dungeon_reinfest_at", {}).get(dungeon_id)
    if at is None or now < at:
        return False
    # 軍營駐守 → 駐軍守著營地,不會被重踞(warband 與地城迴圈的互動點)
    camp = getattr(char, "camp", "")
    if camp and (gamedata.world["locations"].get(camp) or {}).get("dungeon") == dungeon_id:
        return False
    return True


def mark_purged(char: Character, gamedata: GameData, dungeon_id: str, now: int) -> None:
    """首通/掃蕩重踞後排下一輪滋擾(時間戳嚴格遞增 → purge_dungeon objective 的
    base 快照判定依賴此性質);無變體區塊的地城不排(永不滋擾)。"""
    if reinfest_block(gamedata, dungeon_id) is not None:
        char.dungeon_reinfest_at[dungeon_id] = now + REINFEST_CYCLE_HOURS


def effective_spec(gamedata: GameData, dungeon_id: str, infested: bool) -> dict:
    """實際生效的地城 spec:重踞中 → 疊上變體的 monsters/boss(/loot);否則原 spec。
    變體 boss 自帶較小寶藏(treasure 定義於變體區塊,絕無神器)。"""
    spec = gamedata.dungeons[dungeon_id]
    if not infested:
        return spec
    rb = reinfest_block(gamedata, dungeon_id) or {}
    eff = {**spec, "monsters": rb.get("monsters", spec["monsters"]), "boss": rb.get("boss", spec["boss"])}
    if rb.get("loot"):
        eff["loot"] = rb["loot"]
    return eff


def reinfest_notices(char: Character, gamedata: GameData, now: int, seen: set) -> list[str]:
    """本省「重踞傳聞」一次性通知(session 暫態 seen 去重,key=(dungeon,時間戳)→
    每輪滋擾至多報一次;比照 R55 成就通知模式,零存檔欄)。"""
    locs = gamedata.world["locations"]
    here_prov = (locs.get(getattr(char, "location_id", "")) or {}).get("province")
    if not here_prov:
        return []
    out: list[str] = []
    for did in (getattr(char, "cleared_dungeons", []) or []):
        if not is_reinfested(char, gamedata, did, now):
            continue
        key = (did, getattr(char, "dungeon_reinfest_at", {}).get(did))
        if key in seen:
            continue
        lid = dungeon_location_id(gamedata, did)
        if lid is None or (locs.get(lid) or {}).get("province") != here_prov:
            continue
        seen.add(key)
        rb = reinfest_block(gamedata, did) or {}
        name = gamedata.dungeons[did]["name"]
        out.append(rb.get("rumor") or f"四方傳聞:聽說{name}又有不乾淨的東西盤踞了……")
    return out


def ensure_reinfest_fields(char: Character, gamedata: GameData, now: int) -> None:
    """冪等自癒 `dungeon_reinfest_at`:型別矯正(含 Infinity→OverflowError,R110 教訓)+
    未來時間戳上夾;**舊檔回填**——已清且參與滋擾但缺時間戳的地城,排一輪後滋擾
    (溫和升級:不會載入即全面重踞)。未知 dungeon id 保留不刪(inert)。"""
    gat = getattr(char, "dungeon_reinfest_at", None)
    char.dungeon_reinfest_at = gat if isinstance(gat, dict) else {}
    cap = now + REINFEST_CYCLE_HOURS
    for did, v in list(char.dungeon_reinfest_at.items()):
        try:
            char.dungeon_reinfest_at[did] = min(int(v), cap)
        except (TypeError, ValueError, OverflowError):
            char.dungeon_reinfest_at.pop(did)
    for did in getattr(char, "cleared_dungeons", []) or []:
        if reinfest_block(gamedata, did) is not None and did not in char.dungeon_reinfest_at:
            char.dungeon_reinfest_at[did] = cap


def pick_lock_chance(security_skill: int, lock_level: int) -> float:
    return max(0.05, min(0.95, 0.10 + (security_skill - lock_level) * 0.03))


def has_skeleton_key(char: Character, gamedata: GameData) -> bool:
    """是否穿戴骷髏鑰匙(盜賊公會掌門神器)→ 撬鎖必成、不耗開鎖器(諾克圖拉爾的萬能之鑰)。"""
    return any((gamedata.item_or_none(i) or {}).get("skeleton_key")
               for i in getattr(char, "equipped", {}).values())


def effective_pick_lock_chance(char: Character, gamedata: GameData, lock_level: int) -> float:
    """含里程碑「撬鎖名家」下限的實際撬鎖成功率(顯示與擲骰共用,確保一致)。
    骷髏鑰匙 → 恆 100%;幸運「時來運轉」微升成功率(base-40 中性 +0)。"""
    if has_skeleton_key(char, gamedata):
        return 1.0
    from tesrpg import formulas
    chance = min(0.95, pick_lock_chance(char.skill("security"), lock_level)
                 + formulas.luck_fortune(char.attr("luck")))
    return max(chance, mastery.lock_floor(char, gamedata))


LOCKPICK_ITEM = "lockpick"
LOCKPICK_FATIGUE = 2    # 每次撬鎖嘗試的少量體力;主閘改為「開鎖器」(失敗折斷),非時間


def pick_lock(char: Character, gamedata: GameData, lock_level: int, rng: RNG) -> dict:
    """嘗試撬鎖一次。**需要開鎖器,每次嘗試耗一根**(成功=用掉、失敗=折斷),**不耗時**、僅扣少量體力。
    成功鍛鍊安全技能(learn-by-doing);**失敗也給少量 xp**(SECURITY_FAIL_XP_FRAC,從失誤中學)。
    **每次嘗試都耗一根開鎖器 → security xp 有金幣閘**(失敗 xp 小 + 開鎖器成本 → 故意失敗刷功不划算;
    開鎖器=這道反 min-max 的成本閘,以金幣換取)。
    「塔之鑰」(塔座能力)充能則必定成功、消耗之 —— 招牌仍免開鎖器/免體力/免耗時。
    回傳含 hours(恆 0)/tired/no_pick(無開鎖器)/broke_pick(本次失敗折斷),供呼叫端提示。
    """
    chance = effective_pick_lock_chance(char, gamedata, lock_level)
    base_xp = gamedata.skills["security"]["practice"]["xp"]
    if char.tower_key_charge:
        char.tower_key_charge = False
        skill_events = progression.use_skill(char, gamedata, "security", base_xp)
        return {"success": True, "chance": 1.0, "tower_key": True, "no_pick": False,
                "broke_pick": False, "hours": 0, "tired": False, "skill_events": skill_events}
    if has_skeleton_key(char, gamedata):     # 骷髏鑰匙:必成、不耗開鎖器/體力;刻意不給 security xp(非親手習得 → 防免費刷技能)
        return {"success": True, "chance": 1.0, "tower_key": False, "skeleton_key": True,
                "no_pick": False, "broke_pick": False, "hours": 0, "tired": False, "skill_events": []}
    if inventory.count_item(char, LOCKPICK_ITEM) <= 0:            # 沒有開鎖器 → 撬不了
        return {"success": False, "chance": chance, "tower_key": False, "no_pick": True,
                "broke_pick": False, "hours": 0, "tired": False, "skill_events": []}
    tired = char.fatigue < LOCKPICK_FATIGUE
    char.fatigue = max(0, char.fatigue - LOCKPICK_FATIGUE)
    success = rng.chance(chance)
    from tesrpg.systems import mastery
    from tesrpg import formulas
    keep = (not success) and rng.chance(mastery.pick_keep_chance(char, gamedata))   # 「巧手不折」失敗不折
    if not keep:
        inventory.remove_item(char, LOCKPICK_ITEM, 1)           # 每次嘗試耗一根(成功也耗 → xp 的金幣閘)
    xp = base_xp if success else base_xp * formulas.SECURITY_FAIL_XP_FRAC   # 失敗也學(少量;learn-by-doing)
    skill_events = progression.use_skill(char, gamedata, "security", xp)
    return {"success": success, "chance": chance, "tower_key": False, "no_pick": False,
            "broke_pick": not success and not keep, "hours": 0, "tired": tired, "skill_events": skill_events}


def open_container(char: Character, gamedata: GameData, container: dict, rng: RNG) -> dict:
    """開啟(已解鎖的)容器,內容入袋(幸運「戰利豐厚」加權)。回傳 {"gold", "items":[(id,qty)]}。"""
    from tesrpg import formulas
    result = loot.resolve_loot(container.get("loot", []), rng,
                               formulas.luck_loot_factor(char.attr("luck")))
    char.gold += result["gold"]
    for item_id, qty in result["items"]:
        inventory.add_item(char, item_id, qty)
    return result
