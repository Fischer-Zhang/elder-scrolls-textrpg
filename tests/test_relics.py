"""九神騎士團聖物戒律(R108)單元測試。

涵蓋:鎖裝三路(惡名/吸血鬼/狼人)、正典容忍線(infamy≤1 可裝)、破戒自動卸下(物品留背包·
只卸聖物·recompute)、邊緣警告(session 一次性+歸零重置)、朝聖贖罪端到端(歸零→復裝+
pilgrim_vision 異象旗)、聖物任務鏈雙閘與獎勵齊全、**聖物單一來源**(不入商店/地城散件/怪掉落)、
套裝 bonus、Umaril boss 規格(solo·raw·控場紅線)、暫態警告旗不入檔。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import divines, inventory, quests, stats

RELICS = ["crusader_helm", "crusader_cuirass", "crusader_gauntlets", "crusader_boots",
          "crusader_shield", "sword_of_the_crusader", "mace_of_the_crusader"]
ARMOR_PIECES = RELICS[:5]


def _state():
    gd = get_gamedata()
    c = build_character(gd, name="K", sex="male", race="imperial", birthsign="warrior",
                        class_id="knight")
    c.is_player = True
    for iid in RELICS:
        inventory.add_item(c, iid, 1)
    st = GameState(player=c, rng=RNG(1), time=GameTime(hour=10))
    return gd, c, st


def _equip_all(gd, c):
    assert inventory.equip_weapon(c, gd, "sword_of_the_crusader")
    for iid in ARMOR_PIECES:
        assert inventory.equip_armor(c, gd, iid), iid
    stats.recompute_max_resources(c, gd)


# --- 鎖裝三路 + 正典容忍線 ---------------------------------------------------
def test_equip_allowed_at_infamy_zero_and_one():
    gd, c, st = _state()
    _equip_all(gd, c)          # infamy 0 → 全可裝
    c.infamy = 1
    assert inventory.equip_weapon(c, gd, "mace_of_the_crusader")   # ≤1 仍可裝(容忍一次失足)


def test_equip_blocked_at_infamy_two_and_by_curses():
    gd, c, st = _state()
    c.infamy = 2
    assert not inventory.equip_armor(c, gd, "crusader_helm")
    assert not inventory.equip_weapon(c, gd, "sword_of_the_crusader")
    c.infamy = 0
    c.is_vampire = True        # 吸血鬼 → 拒
    assert not inventory.equip_armor(c, gd, "crusader_helm")
    c.is_vampire = False
    c.is_werewolf = True       # 狼人 → 拒(人形也藏不住獸血)
    assert not inventory.equip_armor(c, gd, "crusader_helm")
    c.is_werewolf = False
    assert inventory.equip_armor(c, gd, "crusader_helm")           # 潔身 → 放行


def test_normal_gear_unaffected_by_virtue():
    gd, c, st = _state()
    inventory.add_item(c, "steel_dagger", 1)
    c.infamy = 50
    c.is_vampire = True
    assert inventory.equip_weapon(c, gd, "steel_dagger")   # 戒律只鎖 requires_virtue 物品


# --- 破戒自動卸下 ------------------------------------------------------------
def test_auto_shed_on_infamy_rise():
    gd, c, st = _state()
    _equip_all(gd, c)
    hp_capped = c.max_health
    c.infamy = 2
    evs = divines.update(st, gd)
    assert any(e["kind"] == "relic_shed" and e["reason"] == "infamy" for e in evs)
    assert c.weapon == "fists" and not any(iid in c.equipped.values() for iid in RELICS)
    for iid in RELICS:
        assert inventory.count_item(c, iid) == 1      # 物品留背包(R56 骨架)
    assert c.max_health <= hp_capped                   # 聖靴耐力加成回落(recompute 已跑,R05)
    assert divines.update(st, gd) == []                # 已卸乾淨 → 不重複發事件


def test_auto_shed_on_curse_and_only_relics():
    gd, c, st = _state()
    inventory.add_item(c, "steel_dagger", 1)
    _equip_all(gd, c)
    c.equipped.pop("shield")                           # 換上凡俗盾驗「只卸聖物」
    inventory.add_item(c, "iron_shield", 1)
    inventory.equip_armor(c, gd, "iron_shield")
    c.is_werewolf = True                               # 染獸血 → 下一圈聖物褪落
    evs = divines.update(st, gd)
    assert any(e["kind"] == "relic_shed" and e["reason"] == "curse" for e in evs)
    assert c.equipped.get("shield") == "iron_shield"   # 凡俗裝不受牽連
    assert c.weapon == "fists"


# --- 邊緣警告 ----------------------------------------------------------------
def test_warning_once_per_session_and_resets_at_zero():
    gd, c, st = _state()
    _equip_all(gd, c)
    c.infamy = 1
    evs = divines.update(st, gd)
    assert any(e["kind"] == "relic_warning" for e in evs)
    assert divines.update(st, gd) == []                # session 去重
    c.infamy = 0
    divines.update(st, gd)                             # 歸零 → 重置警告旗
    c.infamy = 1
    assert any(e["kind"] == "relic_warning" for e in divines.update(st, gd))


def test_warning_flag_is_transient_not_saved():
    gd, c, st = _state()
    c._virtue_warned = True
    assert "_virtue_warned" not in c.to_dict()         # 暫態旗不入檔(R03)


# --- 朝聖贖罪端到端 ----------------------------------------------------------
def test_pilgrimage_restores_relic_rights_and_grants_vision():
    gd, c, st = _state()
    c.infamy = 30
    assert not inventory.equip_armor(c, gd, "crusader_helm")
    quests.accept_quest(c, gd, divines.PILGRIMAGE_QID)
    for stg in gd.quests[divines.PILGRIMAGE_QID]["stages"]:
        obj = stg["objective"]
        if obj["type"] == "collect":
            inventory.add_item(c, obj["item"], obj["count"])
        elif obj["type"] == "reach":
            c.location_id = obj["location"]
        else:
            for _ in range(obj["count"]):
                quests.record_kill(c, obj["creature"])
        quests.check_completion(c, gd)
    assert c.infamy == 0
    assert "pilgrim_vision" in c.world_events_fired    # 異象旗(冪等 once-fire)
    assert inventory.equip_armor(c, gd, "crusader_helm")   # 贖罪 → 聖物再認你


# --- 任務鏈 ------------------------------------------------------------------
def test_relic_quest_gates_and_chain():
    gd, c, st = _state()
    c.level = 18
    assert quests.available_quests(c, gd, "relic") == []          # 無異象/無會籍 → 不可見
    c.world_events_fired.append("pilgrim_vision")
    assert quests.available_quests(c, gd, "relic") == []          # 只有異象仍不可見
    c.factions["knights_nine"] = 1
    assert quests.available_quests(c, gd, "relic") == []          # rank 1 < 2 → 不可見
    c.factions["knights_nine"] = 2
    assert quests.available_quests(c, gd, "relic") == ["relic_vigil"]
    c.completed_quests.append("relic_vigil")
    assert quests.available_quests(c, gd, "relic") == ["relic_umaril"]


def test_relic_rewards_cover_all_seven_exactly_once():
    gd = get_gamedata()
    granted = (gd.quests["relic_vigil"]["reward"]["items"]
               + gd.quests["relic_umaril"]["reward"]["items"])
    assert sorted(granted) == sorted(RELICS)


def test_relics_single_source():
    """聖物只從聖物任務 reward 發放:不入商店、不進地城散件/寶藏、不掛怪掉落、不進其他任務。"""
    gd = get_gamedata()
    relic_set = set(RELICS)
    for qid, q in gd.quests.items():
        pools = [q.get("reward", {})] + [b.get("reward", {}) for b in q.get("branches", [])]
        for r in pools:
            hits = relic_set & set(r.get("items", []))
            assert not hits or qid in ("relic_vigil", "relic_umaril"), (qid, hits)
    for did, d in gd.dungeons.items():
        assert not relic_set & set(d.get("loot", [])), did
        tr = [x for x in (d.get("boss", {}).get("treasure", {}).get("loot", []))
              if isinstance(x, str)]
        assert not relic_set & set(tr), did
    for lid, loc in gd.world["locations"].items():
        assert not relic_set & set(loc.get("merchant_stock", [])), lid
    for tid, mon in gd.bestiary.items():
        drops = {e.get("item") for e in mon.get("loot", []) if isinstance(e, dict)}
        assert not relic_set & drops, tid


# --- 套裝與 boss 規格 ---------------------------------------------------------
def test_crusader_set_bonus():
    gd, c, st = _state()
    _equip_all(gd, c)
    sb = inventory.active_set_bonus(c, gd)
    assert sb and sb["kind"] == "fortify_skill" and sb["skill"] == "restoration"
    assert c.equip_skill_bonus.get("restoration", 0) >= sb["magnitude"]
    assert c.equip_resist.get("magic", 0) >= sb["resist"]["magic"]   # 套裝抗性子鍵已併入


# R108 通用 guard(R109 強化):任務戰鬥目標必須有真實可達路徑,防「引用打不到的目標」死鎖。
# 程式碼字面 spawn 的白名單:
_SPAWNED_BY_CODE = {
    "city_guard", "city_captain", "townsperson", "mythic_dawn_acolyte",   # 圍捕/盤查/事件
    "guild_enforcer", "guild_avenger",                                    # R96 宿敵打手 + R100 知情者替身
    "bounty_hunter", "mercenary_tracker", "master_hunter",                # R84 賞金獵人
    "imperial_soldier", "rebel_soldier",                                  # 城戰圍城兵
    "coven_patriarch", "dire_alpha",                                      # R52 巢穴頂階決鬥
}
# R109:「任務條件式狩獵生成」(quests.active_hunt_target + world.travel/action_explore)讓**任何 active
# kill 任務的劇情敵目標(weight==0)**在對省野外可獵 → 原 R99/R100 的 23 條 rogue_thief/blade_agent
# 死鎖全數解除,`_KNOWN_LATENT_UNREACHABLE` 清空。此後 kill 目標只要在 bestiary 即可達(野遇池 or 狩獵鉤子)。


def test_quest_kill_targets_are_reachable():
    """所有任務戰鬥目標須可達:kill → 野遇池 / 地城 / events / 程式碼 spawn / faction 合約 /
    **R109 任務條件式狩獵鉤子(weight-0 劇情敵)**;assassinate → 目標為已置放且帶 combat_template 的具名 NPC。"""
    import re as _re
    gd = get_gamedata()
    dungeon_pool = set()
    for d in gd.dungeons.values():
        dungeon_pool.update(d.get("monsters", []))
        if d.get("boss"):
            dungeon_pool.add(d["boss"]["enemy"])
    ev_raw = open("tesrpg/data/events.json", encoding="utf-8").read()
    event_creatures = set(_re.findall(r'"creature":\s*"([a-z_]+)"', ev_raw))

    def kill_reachable(tid, q):
        m = gd.bestiary.get(tid)
        if m is None:
            return False
        wild = m.get("weight", 0) > 0 and m.get("min_level", 0) < 99
        hunt = m.get("weight", 0) == 0            # R109:weight-0 劇情敵由任務條件式狩獵鉤子生成
        return (wild or hunt or tid in dungeon_pool or tid in event_creatures
                or tid in _SPAWNED_BY_CODE or bool(q.get("faction")))

    bad_kill, bad_assassinate = [], []
    for qid, q in gd.quests.items():
        objs = []
        for pool in [q] + q.get("branches", []):
            if pool.get("objective"):
                objs.append(pool["objective"])
            objs += [st["objective"] for st in pool.get("stages", [])]
        for o in objs:
            if o.get("type") == "kill" and not kill_reachable(o["creature"], q):
                bad_kill.append((qid, o["creature"]))
            elif o.get("type") == "assassinate":   # R109:暗殺目標須為已置放 + 可戰鬥的具名 NPC(單 npc 或多 npcs)
                for tnid in (o.get("npcs") or ([o["npc"]] if o.get("npc") else [])):
                    npc = gd.npcs.get(tnid)
                    if npc is None or not npc.get("combat_template"):
                        bad_assassinate.append((qid, tnid))
    assert not bad_kill, f"kill 目標無生成路徑(死鎖):{bad_kill}"
    assert not bad_assassinate, f"assassinate 目標未置放或缺 combat_template:{bad_assassinate}"


def test_vision_message_only_on_first_pilgrimage():
    """朝聖 repeatable:pilgrim_vision 只在首次完成回報 new_flags(重走不重播異象)。"""
    gd, c, st = _state()
    for _round in range(2):
        quests.accept_quest(c, gd, divines.PILGRIMAGE_QID)
        evs = []
        for stg in gd.quests[divines.PILGRIMAGE_QID]["stages"]:
            obj = stg["objective"]
            if obj["type"] == "collect":
                inventory.add_item(c, obj["item"], obj["count"])
            elif obj["type"] == "reach":
                c.location_id = obj["location"]
            else:
                for _ in range(obj["count"]):
                    quests.record_kill(c, obj["creature"])
            evs += quests.check_completion(c, gd)
        done = [e for e in evs if e["type"] == "completed"][0]
        if _round == 0:
            assert "pilgrim_vision" in done["new_flags"]
        else:
            assert "pilgrim_vision" not in done["new_flags"]


def test_garlas_malatar_gated_until_relics_recovered():
    """預清漏洞已關死(審查 finding):蓋拉斯瑪拉塔在 relics_recovered 旗前不可見。"""
    from tesrpg.systems import world
    gd, c, st = _state()
    assert not world.is_visible(c, gd, "garlas_malatar")
    c.world_events_fired.append("relics_recovered")
    assert world.is_visible(c, gd, "garlas_malatar")


def test_relics_not_sellable_but_stashable():
    """使用者拍板:聖物不可賣(no_sell·兩條賣出路徑都過濾)、可存房產倉庫(stash 走 inventory 不受限)。"""
    gd = get_gamedata()
    for iid in RELICS:
        assert gd.item(iid).get("no_sell") is True, iid
    src = open("tesrpg/main.py", encoding="utf-8").read()
    assert src.count('not gamedata.item(s["id"]).get("no_sell")') == 2   # 商店出售 + 藏身處銷贓


def test_crusader_weapons_at_artifact_band():
    """使用者拍板:壓軸神器上調同帶(聖劍 fire 26/speed 1.1 對標 dawnfang;聖鎚 28/absorb 16)。"""
    gd = get_gamedata()
    sw = gd.item("sword_of_the_crusader")
    assert sw["enchant"]["magnitude"] >= 26 and sw["speed"] >= 1.1
    mc = gd.item("mace_of_the_crusader")
    assert mc["damage"] >= 28 and mc["enchant"]["magnitude"] >= 16


def test_umaril_boss_spec():
    gd = get_gamedata()
    u = gd.bestiary["umaril_the_unfeathered"]
    assert u.get("solo") is True and u.get("min_level", 0) >= 18
    for atk in u.get("attacks", []):
        oh = atk.get("on_hit")
        if oh and oh.get("status") in ("fear", "paralyze"):        # 硬控紅線(R43/R44)
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 99) <= 1
    d = gd.dungeons["garlas_malatar"]
    assert d["boss"]["enemy"] == "umaril_the_unfeathered" and d["boss"]["raw"] is True
    loc = gd.world["locations"]["garlas_malatar"]
    assert loc["type"] == "dungeon" and loc["dungeon"] == "garlas_malatar"


def run():
    for name in sorted(globals()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  ✓ {name}")
