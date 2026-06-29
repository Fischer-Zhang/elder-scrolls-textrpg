"""資料檔 schema + 交叉引用守門(集中式;補 spells 之外的薄覆蓋檔)。

承測試基建補強:trainers/armor_sets/birthsigns/world_events/dialogue 原僅間接覆蓋
(載入壞掉才崩),缺像 test_spell_schema 的語意守門 —— 打錯 id / 斷鏈不會崩,卻成
靜默死內容。本檔確保「每個外鍵都指向真實存在物」,在資料層即攔下。

設計(自我維護優先):交叉引用一律對照活的 gamedata → 照既有形狀加內容(新訓練師/
星座/對話/世界事件/套裝)時自動涵蓋、免動本檔。少數 enum 白名單對照實作端的 dispatch
(inventory/worldstate);加「全新種類」時測試失敗 = 刻意的登錄提醒(同 test_spell_schema._KINDS)。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tesrpg import formulas
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import powers

_SPECS = {"combat", "magic", "stealth"}            # trainers skills 可為系別(world._trainable_skill_set)
_ATTRS = set(formulas.ATTRIBUTES)
_POWER_IDS = set(powers.POWERS)                     # 星座 powers 權威集(systems/powers.py)
# 抗性元素(火/冰/電吃 magic 抗,毒/疾不吃;見 formulas.MAGIC_ELEMENTS + R14)
_RESIST_ELEMENTS = {"fire", "frost", "shock", "poison", "magic", "disease", "bleed"}
# 套裝 bonus.kind:對照 inventory.py:234-240 的 dispatch(無單一可 import 集合)
_SET_BONUS_KINDS = {"fortify_skill", "fortify_attribute", "fortify_resource", "armor_fortify", "resist_element"}
# world_events effect type:對照 worldstate.py:_apply
_WE_EFFECT_TYPES = {"faction_flip", "clear_flip", "fame", "message"}
# events.apply_effects 支援的 effect type(對照 events.py:apply_effects dispatch)
_EVENTS_EFFECT_TYPES = {"gold", "item", "skill_xp", "heal", "restore_magicka", "restore_fatigue",
                        "damage", "fame", "infamy", "bounty", "start_quest", "learn_spell",
                        "combat", "message"}
# 對話 topic effect:dialogue._apply_topic_effects 攔 faction_standing、其餘委派 events.apply_effects(R81)
_DLG_EFFECT_TYPES = {"faction_standing"} | _EVENTS_EFFECT_TYPES
# 話題 action 派發(dialogue.resolve_topic pump / main.action_talk fence·supply·contract)
_TOPIC_ACTIONS = {"pump", "fence", "supply", "contract"}
_GREETING_ATTITUDES = {"comrade", "friendly", "neutral", "cold", "hostile", "vampire_seen"}
_REL_KEYS = {"ally", "enemy", "neutral", "unaligned"}


def _entries(d: dict) -> dict:
    """跳過 _ 前綴的 meta 鍵(如 _doc)。"""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def test_trainers_foreign_keys():
    gd = get_gamedata()
    locs = gd.world["locations"]
    for loc, spec in _entries(gd.trainers).items():
        assert loc in locs, f"trainers 鍵 {loc} 非真實地點"
        if not isinstance(spec, dict):
            continue
        for s in spec.get("skills", []):
            assert s in gd.skills or s in _SPECS, f"{loc} 可教技能 {s} 不存在(非技能/非系別)"
        m = spec.get("master")
        if m:
            assert m.get("skill") in gd.skills, f"{loc} 宗師技 {m.get('skill')} 不存在"
            assert isinstance(m.get("cap"), int) and m["cap"] > 0, f"{loc} 宗師 cap 非正整數"


def test_armor_sets_foreign_keys():
    gd = get_gamedata()
    materials = {a.get("material") for a in gd.armor.values() if a.get("material")}   # 活資料 → 自我維護
    for mat, spec in _entries(gd.armor_sets).items():
        assert mat in materials, f"armor_set 材質 {mat} 在 armor.json 無對應裝備"
        b = spec.get("bonus") or {}
        k = b.get("kind")
        assert k in _SET_BONUS_KINDS, f"{mat} 套裝 bonus.kind {k} 未實作(對照 inventory.py)"
        assert isinstance(b.get("magnitude", 0), int), f"{mat} magnitude 非整數"
        if k == "fortify_skill":
            assert b.get("skill") in gd.skills, f"{mat} fortify_skill 指向不存在技能 {b.get('skill')}"
        elif k == "fortify_attribute":
            assert b.get("attr") in _ATTRS, f"{mat} fortify_attribute 指向不明屬性 {b.get('attr')}"
        elif k in ("fortify_resource", "armor_fortify"):
            assert b.get("stat") in {"health", "magicka", "fatigue"}, f"{mat} fortify_resource stat 不明 {b.get('stat')}"
        elif k == "resist_element":
            assert b.get("element") in _RESIST_ELEMENTS, f"{mat} resist_element 不明元素 {b.get('element')}"


def test_birthsigns_foreign_keys():
    gd = get_gamedata()
    for sid, bs in _entries(gd.birthsigns).items():
        for key in ("name", "attr_mods", "magicka_bonus"):
            assert key in bs, f"星座 {sid} 缺鍵 {key}"
        assert isinstance(bs["magicka_bonus"], int), f"{sid} magicka_bonus 非整數"
        for a, v in (bs.get("attr_mods") or {}).items():
            assert a in _ATTRS, f"{sid} attr_mods 指向不明屬性 {a}"
            assert isinstance(v, int), f"{sid} attr_mods[{a}] 非整數"
        for p in bs.get("powers") or []:
            assert p in _POWER_IDS, f"{sid} powers 指向不存在的星座能力 {p}"
        for e in (bs.get("resist") or {}):
            assert e in _RESIST_ELEMENTS, f"{sid} resist 指向不明元素 {e}"


def test_world_events_foreign_keys():
    gd = get_gamedata()
    locs = gd.world["locations"]
    for eid, e in _entries(gd.world_events).items():
        for ef in e.get("effects", []):
            t = ef.get("type")
            assert t in _WE_EFFECT_TYPES, f"{eid} effect type {t} 未實作(對照 worldstate._apply)"
            if "loc" in ef:
                assert ef["loc"] in locs, f"{eid} effect loc {ef['loc']} 非真實地點"
            if "to" in ef:
                assert ef["to"] in gd.factions or ef["to"] == "independent", \
                    f"{eid} effect to {ef['to']} 非合法陣營/independent"
        # 註:trigger.requires 可引用外部旗標(如 oblivion_crisis_ended,非本檔事件)→ 不做交叉引用斷言


def test_dialogue_foreign_keys():
    gd = get_gamedata()
    dlg = gd.dialogue
    topics = dlg.get("topics", {})
    assert set(dlg.get("greetings", {})) <= _GREETING_ATTITUDES, "greetings 含不明 attitude"
    for att, lst in dlg.get("attitude_topics", {}).items():
        assert att in _GREETING_ATTITUDES, f"attitude_topics 不明 attitude {att}"
        for tid in lst:
            assert tid in topics, f"attitude_topics[{att}] 引用不存在話題 {tid}"
    # R81 role 身份話題:roles map 每個 topic id ∈ topics;每個 npc.role ∈ roles keys(防死 role)
    roles = dlg.get("roles", {})
    for role, tids in roles.items():
        for tid in tids:
            assert tid in topics, f"roles[{role}] 引用不存在話題 {tid}"
    for npc_id, npc in gd.npcs.items():
        if npc.get("role"):
            assert npc["role"] in roles, f"npc {npc_id}: role {npc['role']} 不在 dialogue.roles"
        if npc.get("guild"):     # R96:公會歸屬標(驅動宿敵敵意態度)須指向真實公會
            assert npc["guild"] in gd.factions, f"npc {npc_id}: guild {npc['guild']} 非真實公會"
        if npc.get("secret_guild"):   # R97:隱蔽(犯罪)身分標 → 須真實公會,且應為犯罪公會
            from tesrpg.systems import factions
            assert npc["secret_guild"] in gd.factions, f"npc {npc_id}: secret_guild {npc['secret_guild']} 非真實公會"
            assert factions.is_criminal_guild(npc["secret_guild"]), \
                f"npc {npc_id}: secret_guild {npc['secret_guild']} 非犯罪/隱蔽公會(公開公會用 guild 標)"
            sec = npc.get("secret_secrecy", 50)   # 調查難度(0-100 int;鏡像 rumor_disposition 守門)
            assert isinstance(sec, int) and 0 <= sec <= 100, f"npc {npc_id}: secret_secrecy {sec} 須 0-100 int"

    def _check_topic(where, t):
        from tesrpg.systems import factions
        r = t.get("requires", {})
        if "is_member" in r:
            assert r["is_member"] in gd.factions, f"{where} is_member 指向不存在公會 {r['is_member']}"
        if "secret_comrade" in r:   # R98:犯罪同志服務閘 → 須真實犯罪/隱蔽公會
            sc = r["secret_comrade"]
            assert sc in gd.factions and factions.is_criminal_guild(sc), \
                f"{where} secret_comrade {sc} 非犯罪/隱蔽公會"
        if "action" in t:           # 話題 action 須為已實作派發(R82 pump / R98 fence·supply·contract)
            assert t["action"] in _TOPIC_ACTIONS, f"{where} action {t['action']} 未實作派發"
        if "mole_expose" in r:      # R99 臥底揭發資格(meets_dialogue mole_expose 分支)
            assert r["mole_expose"] in ("outsider", "comrade"), f"{where} mole_expose {r['mole_expose']} 非法"
        for sk in (r.get("skill_min") or {}):
            assert sk in gd.skills, f"{where} skill_min 指向不存在技能 {sk}"
        for e in t.get("effects", []):
            assert e.get("type") in _DLG_EFFECT_TYPES, f"{where} effect type {e.get('type')} 未實作"
        for rel in (t.get("say_by_rel") or {}):
            assert rel in _REL_KEYS, f"{where} say_by_rel 不明立場 {rel}"
        # 註:faction_standing_min / effect.faction 可為政治集團(imperial/independent)或 @npc 佔位符,
        # 非 gamedata.factions 命名空間 → 不做 faction 交叉引用斷言(避免誤判)

    for tid, t in topics.items():
        _check_topic(f"topic:{tid}", t)
    for npc_id, npc in dlg.get("npcs", {}).items():
        assert npc_id in gd.npcs, f"dialogue.npcs 鍵 {npc_id} 非真實 NPC"
        deep = npc.get("deep") or {}
        for tid, t in deep.items():
            _check_topic(f"npc:{npc_id}:deep:{tid}", t)
        for tid in npc.get("extra") or []:
            assert tid in topics or tid in deep, f"{npc_id} extra 引用不存在話題 {tid}"
        # R82 功能化秘密:secret 可為 str(flavor)或 {text, effects}(撬出藏寶/線索);
        # 效果型別 ∈ _DLG_EFFECT_TYPES,且 start_quest→quests、item→items 外鍵成立。
        sec = npc.get("secret")
        assert sec is None or isinstance(sec, (str, dict)), f"{npc_id} secret 須為 str 或 dict"
        if isinstance(sec, dict):
            assert isinstance(sec.get("text", ""), str), f"{npc_id} secret.text 須為 str"
            for e in sec.get("effects", []):
                assert e.get("type") in _DLG_EFFECT_TYPES, f"{npc_id} secret effect {e.get('type')} 未實作"
                if e.get("type") == "start_quest":
                    assert e["quest"] in gd.quests, f"{npc_id} secret start_quest {e['quest']} 不存在"
                if e.get("type") == "item":
                    assert gd.item_or_none(e["item"]) is not None, f"{npc_id} secret item {e['item']} 不存在"


def test_monster_on_hit_status_is_implemented():
    """怪物 attack/attacks on_hit.status 必為 combat on_hit dispatch 認得的 kind
    (combat.py:649-657:'dot' -> _apply_dot_capped,其餘 -> magic.apply_control)。
    防「conduct 寫進 on_hit 卻 no-op」(conduct 是 magic.cast 專用)類靜默失效。"""
    from tesrpg.systems import magic
    gd = get_gamedata()
    legal = {"dot"} | set(magic._CONTROL_KINDS)
    bad = []
    for cid, c in gd.bestiary.items():
        for a in [c.get("attack", {})] + c.get("attacks", []):
            st = (a.get("on_hit") or {}).get("status")
            if st and st not in legal:
                bad.append(f"{cid}:{a.get('name')}={st}")
    assert not bad, f"on_hit.status 非法/未實作:{bad}(合法:{sorted(legal)})"


def test_quest_objective_types_and_reward_keys_implemented():
    """所有任務(含 stages/branches)objective.type ∈ _OBJECTIVE_TYPES、reward key ∈ _REWARD_KEYS。
    防 objective.type 打錯 -> 任務永不可完成;reward key 打錯 -> 獎勵被 .get() 默默吃掉。"""
    from tesrpg.systems import quests
    gd = get_gamedata()

    def objs(qd):
        out = ([qd["objective"]] if "objective" in qd else []) + \
              [s.get("objective", {}) for s in qd.get("stages", [])]
        for b in qd.get("branches", []):
            out += ([b["objective"]] if "objective" in b else []) + \
                   [s.get("objective", {}) for s in b.get("stages", [])]
        return out

    def rewards(qd):
        return [qd.get("reward", {})] + [b.get("reward", {}) for b in qd.get("branches", [])]

    bad_obj, bad_rwd = [], []
    for qid, q in gd.quests.items():
        for o in objs(q):
            if o.get("type") and o["type"] not in quests._OBJECTIVE_TYPES:
                bad_obj.append(f"{qid}:{o['type']}")
        for r in rewards(q):
            bad_rwd.extend(f"{qid}:{k}" for k in r if k not in quests._REWARD_KEYS)
    assert not bad_obj, f"objective.type 未實作:{bad_obj}"
    assert not bad_rwd, f"reward key 未實作:{bad_rwd}"

    # 常態世界脈動(R-pulse / R80):可重複委託只准帶 gold/fame/infamy(反 min-max,不可刷限定內容);
    # objective 不可為 clear_dungeon(cleared_dungeons 永久 → 已清地城即時重複達標=免費金);
    # 首階段 objective 不可為 reach(接取時若已在目標地會即時自動完成=免費刷;reach 只可做後段交付)。
    def first_obj(q):
        if "stages" in q and q["stages"]:
            return q["stages"][0].get("objective", {})
        return q.get("objective", {})

    bad_rep, bad_rep_obj, bad_rep_reach = [], [], []
    for qid, q in gd.quests.items():
        if not q.get("repeatable"):
            continue
        for r in rewards(q):
            bad_rep.extend(f"{qid}:{k}" for k in r if k not in quests._REPEATABLE_REWARD_KEYS)
        for o in objs(q):
            if o.get("type") == "clear_dungeon":
                bad_rep_obj.append(qid)
        if first_obj(q).get("type") == "reach":
            bad_rep_reach.append(qid)
    assert not bad_rep, f"可重複委託只准 gold/fame/infamy:{bad_rep}"
    assert not bad_rep_obj, f"可重複委託 objective 不可為 clear_dungeon(永久達標):{bad_rep_obj}"
    assert not bad_rep_reach, f"可重複委託首階段不可為 reach(接取即在目標地會自動完成):{bad_rep_reach}"


def test_world_pulse_schema_and_foreign_keys():
    """常態世界脈動 world_pulse.json:province 合法、cooldown≥active_window、weight>0、
    spotlight_quests 指向真實的 repeatable board 委託、requires_event 指向真實大事件(R-pulse)。"""
    gd = get_gamedata()
    provinces = {loc["province"] for loc in gd.world["locations"].values() if "province" in loc}
    bad = []
    for pid, p in gd.world_pulse.items():
        if p.get("province") not in provinces:
            bad.append(f"{pid}: province {p.get('province')} 不在世界省份")
        if p.get("weight", 1) <= 0:
            bad.append(f"{pid}: weight<=0")
        if p.get("cooldown_days", 0) < p.get("active_window_days", 7):
            bad.append(f"{pid}: cooldown_days < active_window_days(視窗未閉即可重觸)")
        req = p.get("requires_event")
        if req and req not in gd.world_events and req not in _KNOWN_WORLD_FLAGS:
            bad.append(f"{pid}: requires_event {req} 非真實大事件/旗標")
        for sq in p.get("spotlight_quests", []):
            q = gd.quests.get(sq)
            if q is None:
                bad.append(f"{pid}: spotlight {sq} 不存在")
            elif not q.get("repeatable"):
                bad.append(f"{pid}: spotlight {sq} 非 repeatable")
            elif q.get("source") != "board":
                bad.append(f"{pid}: spotlight {sq} 非 board 委託")
    assert not bad, "world_pulse schema 違規:" + "; ".join(bad)


# 非 world_events.json 但仍合法的世界旗標(由任務 reward.world_flags 設入 world_events_fired)。
_KNOWN_WORLD_FLAGS = frozenset({"oblivion_crisis_ended"})


def _event_start_quests(ev):
    """蒐集一個事件所有 option(含 check success/failure)的 start_quest 目標 id。"""
    out = []
    for opt in ev.get("options", []):
        out += [ef["quest"] for ef in opt.get("effects", []) if ef.get("type") == "start_quest"]
        chk = opt.get("check")
        if chk:
            for br in ("success", "failure"):
                out += [ef["quest"] for ef in chk.get(br, {}).get("effects", [])
                        if ef.get("type") == "start_quest"]
    return out


def test_quest_givers_and_reachability():
    """任務派發外鍵 + 不成孤兒(R80):① npcs.json 每個 quest 欄 → 存在於 quests;
    ② events.json 每個 start_quest → 存在;③ 每個 source:'npc' 任務必可達(由某 NPC quest 欄、
    或某事件 start_quest、或某同伴 recruit_quest 回指)—— 防新增一次性任務成孤兒永不可接。"""
    gd = get_gamedata()
    bad = []
    # ① NPC quest 欄外鍵
    npc_quests = set()
    for nid, npc in gd.npcs.items():
        qid = npc.get("quest")
        if qid:
            npc_quests.add(qid)
            if qid not in gd.quests:
                bad.append(f"npc {nid}: quest {qid} 不存在")
    # ② 事件 start_quest 外鍵
    event_quests = set()
    for eid, ev in gd.events.items():
        for qid in _event_start_quests(ev):
            event_quests.add(qid)
            if qid not in gd.quests:
                bad.append(f"event {eid}: start_quest {qid} 不存在")
    # ③ R81 流言線索外鍵:npc.rumor_quest → 存在且 source=="rumor";npc.rumor_landmark → 真實地標;
    #    rumor_disposition → 0-100 int。
    world = gd.world["locations"]
    rumor_quests = set()
    for nid, npc in gd.npcs.items():
        rq = npc.get("rumor_quest")
        if rq:
            rumor_quests.add(rq)
            if rq not in gd.quests:
                bad.append(f"npc {nid}: rumor_quest {rq} 不存在")
            elif gd.quests[rq].get("source") != "rumor":
                bad.append(f"npc {nid}: rumor_quest {rq} source 非 rumor")
        rl = npc.get("rumor_landmark")
        if rl and gd.landmark_at(rl) is None:
            bad.append(f"npc {nid}: rumor_landmark {rl} 非真實地標")
        rd = npc.get("rumor_disposition")
        if rd is not None and not (isinstance(rd, int) and 0 <= rd <= 100):
            bad.append(f"npc {nid}: rumor_disposition {rd} 非 0-100 int")
    # R82 套話功能化:dialogue.npcs[*].secret(dict 形)的 start_quest 也是任務派發來源(秘藏線索)
    secret_quests = set()
    for npc in gd.dialogue.get("npcs", {}).values():
        sec = npc.get("secret")
        if isinstance(sec, dict):
            secret_quests |= {e["quest"] for e in sec.get("effects", []) if e.get("type") == "start_quest"}
    # R99 對話話題 start_quest 也是任務派發來源(招募內線 deep 話題 → 反間線索 cintlead_)
    topic_quests = set()
    _topic_defs = list(gd.dialogue.get("topics", {}).values())
    for npc in gd.dialogue.get("npcs", {}).values():
        _topic_defs += list((npc.get("deep") or {}).values())
    for td in _topic_defs:
        topic_quests |= {e["quest"] for e in td.get("effects", []) if e.get("type") == "start_quest"}
    # ④ 可達性:source:npc(npc 欄∪事件∪招募∪秘藏∪對話話題);source:rumor(npc.rumor_quest 派發,防孤兒)
    recruit_quests = {c.get("recruit_quest") for c in gd.companions.values() if c.get("recruit_quest")}
    reachable = npc_quests | event_quests | recruit_quests | secret_quests | topic_quests
    for qid, q in gd.quests.items():
        if q.get("source") == "npc" and qid not in reachable:
            bad.append(f"孤兒 npc 任務 {qid}:無 NPC/事件/招募 派發 → 永不可接")
        if q.get("source") == "rumor":
            if qid not in rumor_quests:
                bad.append(f"孤兒 rumor 線索 {qid}:無 NPC rumor_quest 回指 → 永不可接")
            # ⑤ 線索目標地城/地點不可有 visible gate(否則可接卻去不了)
            obj = q.get("objective", {})
            loc = obj.get("dungeon") or obj.get("location")
            if loc and world.get(loc, {}).get("visible"):
                bad.append(f"rumor 線索 {qid}:目標 {loc} 有 visible gate(可接去不了)")
    assert not bad, "任務派發/可達性違規:" + "; ".join(bad)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_data_schema")
