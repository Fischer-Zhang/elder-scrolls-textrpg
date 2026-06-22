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
_DLG_EFFECT_TYPES = {"faction_standing"}           # 對照 dialogue.apply_topic_effects
_GREETING_ATTITUDES = {"friendly", "neutral", "cold", "hostile", "vampire_seen"}
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

    def _check_topic(where, t):
        r = t.get("requires", {})
        if "is_member" in r:
            assert r["is_member"] in gd.factions, f"{where} is_member 指向不存在公會 {r['is_member']}"
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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_data_schema")
