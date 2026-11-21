"""R198 事件資料整理(R196 審查後的決策備忘錄 → 使用者「照建議」)。

  ① wild_beast 的省份限定原寫在事件**頂層**(引擎只讀 trigger.provinces → 死資料,霜咬蜘蛛全圖 229 地點出沒,
     其中 193 個非雪地):改為 trigger.provinces=天際 + location_types=wilderness(比照 skyrim_predator 等兄弟事件)
  ② 事件檢定成功一律練「被檢定的技能」(原 23/41 → 41/41;「做什麼練什麼」);值比照既有:
     潛行 / 雜技 0.6、口才與安全依難度分級
  ③ 檢定選項標籤句尾必為「(被檢定技能的正典名)」(原 36/41;「(秘法)」→「(神秘)」·R161)
  ④ 事件文字無全形 ，！？(資料慣例:半形逗號 / 驚嘆號;原 4 處)
  ⑤ 事件綱要無死鍵(事件層只許 weight/trigger/title/text/options;trigger 只許 _trigger_ok 真的會讀的鍵)
🔴 純資料 + 守衛;零程式、零存檔欄位;sim 不走事件。
"""
import re
from collections import defaultdict

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import events

gd = get_gamedata()

_EVENT_KEYS = {"weight", "trigger", "title", "text", "options"}
_TRIGGER_KEYS = {"contexts", "min_level", "max_level", "location_types", "provinces", "require"}   # = events._trigger_ok 會讀的鍵


def _checks():
    for eid, e in gd.events.items():
        for i, o in enumerate(e["options"]):
            if "check" in o:
                yield eid, i, o


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _player():
    return build_character(gd, name="客", sex="male", race="nord", birthsign="warrior", class_id="warrior")


# --- ⑤ 綱要無死鍵 ---------------------------------------------------------
def test_event_schema_has_no_dead_keys():
    for eid, e in gd.events.items():
        assert set(e) <= _EVENT_KEYS, (eid, set(e) - _EVENT_KEYS)          # R198 前 wild_beast 多一個頂層 provinces
        assert set(e["trigger"]) <= _TRIGGER_KEYS, (eid, set(e["trigger"]) - _TRIGGER_KEYS)


# --- ① wild_beast 出現地點 -------------------------------------------------
def test_wild_beast_only_in_skyrim_wilderness():
    assert gd.events["wild_beast"]["trigger"] == {
        "contexts": ["explore"], "provinces": ["天際"], "location_types": ["wilderness"]}
    c = _player()
    st = GameState(player=c, time=GameTime())
    on, off = [], []
    for lid, loc in gd.world["locations"].items():
        c.location_id = lid
        hit = "wild_beast" in events.eligible_events(st, gd, "explore")
        assert hit == (loc["province"] == "天際" and loc["type"] == "wilderness"), (lid, loc["province"], loc["type"])
        (on if hit else off).append(lid)
    assert len(on) >= 5 and len(off) > 200, "必須真有出現的點與被擋掉的點,否則此測試空轉"
    c.location_id = on[0]
    for ctx in ("travel", "rest", "arrive"):                              # 其餘情境本就不觸發
        assert "wild_beast" not in events.eligible_events(st, gd, ctx)


def _event_creatures(e):
    """事件所有分支(選項效果 / 檢定成功·失敗)會召喚的生物 id。"""
    out = set()

    def eff(lst):
        for x in lst or []:
            if x.get("type") == "combat":
                out.add(x["creature"])

    for o in e["options"]:
        eff(o.get("effects"))
        c = o.get("check")
        if c:
            eff(c["success"].get("effects"))
            eff(c["failure"].get("effects"))
    return out


def test_event_creatures_are_native_to_every_location_the_event_can_fire():
    """現實邏輯(R138b / R12):事件固定召喚的生物,其棲地(biomes)必須涵蓋事件可出現的每個地點的 biome
    (biomes 為空的泛用怪如 bandit / wolf 不受限)。R198 前 wild_beast(霜咬蜘蛛·snow)因頂層 provinces 是死資料,
    在 193 個非雪地地點出沒 —— 此守衛涵蓋**全部**含戰鬥的事件(全情境 × 全地點),不只 wild_beast;
    之後任何事件換怪、改觸發條件而造成棲地矛盾都會變紅。"""
    c = _player()
    st = GameState(player=c, time=GameTime())
    checked, constrained_events = 0, set()
    for lid, loc in gd.world["locations"].items():
        c.location_id = lid
        for ctx in ("travel", "rest", "explore", "arrive"):
            for eid in events.eligible_events(st, gd, ctx):
                for cid in _event_creatures(gd.events[eid]):
                    biomes = gd.bestiary[cid].get("biomes")
                    if biomes:
                        assert loc["biome"] in biomes, (eid, cid, lid, loc["biome"])
                        checked += 1
                        constrained_events.add(eid)
    assert checked > 50 and len(constrained_events) >= 8, (checked, len(constrained_events))   # 非空轉(實測 133 組 / 12 個事件)


# --- ② 檢定成功必練同技能 --------------------------------------------------
def test_every_event_check_success_trains_its_own_skill():
    n = 0
    for eid, i, o in _checks():
        c = o["check"]
        own = [x for x in c["success"].get("effects", [])
               if x.get("type") == "skill_xp" and x.get("skill") == c["skill"]]
        assert len(own) == 1, (eid, i, c["skill"])
        assert 0 < own[0]["amount"] <= 1.0, (eid, i, own[0]["amount"])
        n += 1
    assert n >= 41                                                        # 33 舊 + R196 的 8 新;之後只增不減


def test_success_xp_actually_reaches_use_skill():
    c = _player()
    st = GameState(player=c, time=GameTime())
    calls = []
    orig = events.progression.use_skill

    def spy(char, gamedata, skill_id, xp):
        calls.append((skill_id, xp))
        return orig(char, gamedata, skill_id, xp)

    events.progression.use_skill = spy
    try:
        n = 0
        for eid, i, o in _checks():
            for x in (e for e in o["check"]["success"]["effects"] if e["type"] == "skill_xp"):
                calls.clear()
                events.apply_effects(st, gd, [x], RNG(0))
                assert calls == [(x["skill"], x["amount"])], (eid, i)
                n += 1
        assert n >= 41
    finally:
        events.progression.use_skill = orig


def test_tiered_skills_xp_is_monotone_in_difficulty():
    """口才 / 安全:難度越高經驗不會越少。R198 補經驗時採分級(口才 ≤35→0.4、36–44→0.6、≥45→0.8;
    安全 ≤35→0.4、否則 0.6);此守衛只釘「不降」這條底線,**不鎖分級的確切數值**(成長旋鈕留給內容作者調)。"""
    by = defaultdict(list)
    for eid, i, o in _checks():
        c = o["check"]
        if c["skill"] in ("speechcraft", "security"):
            amts = [x["amount"] for x in c["success"]["effects"]
                    if x["type"] == "skill_xp" and x["skill"] == c["skill"]]
            assert len(amts) == 1, (eid, i, "檢定成功必須恰有一筆同技能經驗")
            by[c["skill"]].append((c["difficulty"], amts[0], eid))
    assert set(by) == {"speechcraft", "security"}
    for skill, rows in by.items():
        rows.sort()
        amts = [a for _, a, _ in rows]
        assert amts == sorted(amts), (skill, rows)


# --- ③ 標籤句尾技能名 -----------------------------------------------------
def test_check_option_labels_end_with_the_checked_skill_name():
    n = 0
    for eid, i, o in _checks():
        m = re.search(r"\(([^()]*)\)$", o["text"])
        assert m and m.group(1) == gd.skill_name(o["check"]["skill"]), (eid, i, o["text"])
        n += 1
    assert n >= 41


# --- ④ 標點慣例 ----------------------------------------------------------
def test_event_texts_use_halfwidth_comma_and_bang():
    n = 0
    for s in _strings(gd.events):
        assert not re.search("[，！？]", s), s[:24]
        n += 1
    assert n > 500                                                        # 真的走過大量字串(非空轉)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
