"""R224 練習的上限與條件(練習與訓練師分工)。

使用者裁決(2026-11-26):
  - 練習要符合它自己的描述(場地 / 器材 / 材料 / 法術);運動、雜技、潛行、偵查、徒手不設條件,描述改成不綁場地。
  - 方案 A:練習只能把技能練到 50(formulas.PRACTICE_CAP);訓練師 75、宗師 100 不變;實戰不設限。
    理由:兩者上限相同時,免費的練習讓付費的訓練師毫無價值(遊戲時間沒有代價)。

守衛:
  1. 條件表逐技能等於定案的那一張;五個不設條件的技能,描述不再綁場地;requires 只用支援的鍵,指到的服務 / 物品存在。
  2. `progression.practice_block`:每種條件「不符 → 說明原因、符合 → 放行」;不設條件的五個技能在荒野空手也能練。
  3. 上限:基礎技能 50 就不能再練(看 base_skill,不看裝備加成);真流程練到 50 就停、不空耗時間;訓練師上限仍是 75、宗師 100。
  4. 耗材:安全每小時耗一根開鎖器、煉金每小時耗一份材料(挑最便宜的);時數上限 = 手邊件數;提示與實際消耗同源。
  5. 選單:不能練的技能標出原因;選了不耗時間、回到類別選單;「↻ 再練上次」只在還能練時出現。
  6. 條件只管「練習」這個動作:實戰 / 製作沿用的 practice_cost 不受影響。
  7. 技能詳情的「練習」一行與選單同源。
  8. 量測腳本:練習上限低於訓練師上限;只靠練習能到的角色等級低於訓練到頂。
  9. 以上在就地突變下會紅。
"""
import io

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

import sim_economy as E
from tesrpg import formulas
from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import inventory, progression, stats, world

gd = E.gd
LOCS = gd.world["locations"]
CITY = next(lid for lid, loc in LOCS.items() if {"merchant", "inn", "armorer"} <= set(loc.get("services", [])))
WILD = next(lid for lid, loc in LOCS.items() if not loc.get("services"))
SHIELD = next(i for i, d in gd.armor.items() if d["slot"] == "shield" and not d.get("two_handed"))
HEAVY = next(i for i, d in gd.armor.items() if d["slot"] == "cuirass" and d["weight_class"] == "heavy")
LIGHT = next(i for i, d in gd.armor.items() if d["slot"] == "cuirass" and d["weight_class"] == "light")
BOW = next(i for i, d in gd.weapons.items() if d["skill"] == "marksman")
MACE = next(i for i, d in gd.weapons.items() if d["skill"] == "blunt")
MAGIC = ("alteration", "conjuration", "destruction", "illusion", "mysticism", "restoration")
FREE = ("athletics", "hand_to_hand", "acrobatics", "sneak", "scout")
EXPECTED = {
    "athletics": None, "hand_to_hand": None, "acrobatics": None, "sneak": None, "scout": None,
    "blade": {"weapon": True}, "blunt": {"weapon": True}, "marksman": {"weapon": True},
    "block": {"shield": True},
    "heavy_armor": {"armor_class": "heavy"}, "light_armor": {"armor_class": "light"},
    "mercantile": {"service": "merchant"}, "speechcraft": {"service": "inn"}, "smithing": {"service": "armorer"},
    "security": {"consume": "lockpick"}, "alchemy": {"consume_kind": "ingredient"},
    **{s: {"spell_school": True} for s in MAGIC},
}


def _c(loc=CITY, **skills):
    """空手、空背包、沒有法術、沒穿裝備的角色(測試完全掌握條件)。"""
    c = build_character(gd, name="徒", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    c.inventory, c.weapon, c.equipped, c.spells = [], "fists", {}, []
    c.location_id = loc
    for sid in gd.skills:
        c.skills[sid] = 5
    c.skills.update(skills)
    stats.recompute_max_resources(c, gd, restore_full=True)
    return c


def _wield(c, item_id):
    inventory.add_item(c, item_id, 1)
    assert inventory.equip_weapon(c, gd, item_id)


def _wear(c, item_id):
    inventory.add_item(c, item_id, 1)
    assert inventory.equip_armor(c, gd, item_id)
    stats.recompute_max_resources(c, gd)


class _Script:
    NAMES = ("menu", "ask_int", "message", "show_events")

    def __init__(self, answers, ints=()):
        self.answers, self.ints = list(answers), list(ints)
        self.menus, self.prompts, self.msgs = [], [], []

    def __enter__(self):
        self.saved = {n: getattr(ui, n) for n in self.NAMES}
        self.saved_last = M._last_practice_skill
        M._last_practice_skill = None      # 別的測試模組在同一個行程裡留下的「上次練的技能」不得影響本檔的選單順序
        ui.menu = self._menu
        ui.ask_int = self._ask_int
        ui.message = lambda text, *_a, **_k: self.msgs.append(text)
        ui.show_events = lambda *_a, **_k: None
        return self

    def __exit__(self, *_exc):
        for n, fn in self.saved.items():
            setattr(ui, n, fn)
        M._last_practice_skill = self.saved_last

    def _menu(self, title, options, allow_back=False):
        self.menus.append((title, [k for k, _l in options], {k: lbl for k, lbl in options}))
        return self.answers.pop(0)

    def _ask_int(self, prompt, default=None, lo=None, hi=None):
        self.prompts.append((prompt, default, lo, hi))
        return self.ints.pop(0) if self.ints else default


def _state(c):
    return GameState(player=c, rng=RNG(seed=1), game_mode="adventure")


def _expect_fail(fn) -> bool:
    try:
        fn()
    except AssertionError:
        return True
    return False


# --- 1 條件表 -------------------------------------------------------------
def test_requirements_table_is_the_approved_one():
    assert set(gd.skills) == set(EXPECTED)
    for sid, want in EXPECTED.items():
        assert gd.skills[sid]["practice"].get("requires") == want, sid
    for sid in FREE:                                               # 不設條件的五個:描述不得再綁場地
        label = gd.skills[sid]["practice"]["label"]
        assert not any(w in label for w in ("城牆", "屋脊", "守衛", "哨點", "假人", "酒館", "市集")), (sid, label)
    services = {s for loc in LOCS.values() for s in loc.get("services", [])}
    for sid, d in gd.skills.items():
        req = d["practice"].get("requires") or {}
        assert set(req) <= {"service", "weapon", "shield", "armor_class", "consume", "consume_kind", "spell_school"}, sid
        assert len(req) <= 1, sid
        if "service" in req:
            assert req["service"] in services and req["service"] in progression._PRACTICE_SERVICE_NAMES
        if "consume" in req:
            assert gd.item_or_none(req["consume"]) is not None
        if "consume_kind" in req:
            assert any(it.get("kind") == req["consume_kind"] for it in gd.items.values())
        if "armor_class" in req:
            assert req["armor_class"] in progression._PRACTICE_ARMOR_NAMES
        if req.get("weapon"):
            assert any(w["skill"] == sid for w in gd.weapons.values()), sid
        if req.get("spell_school"):
            assert any(sp["school"] == sid for sp in gd.spells.values()), sid


# --- 2 條件判定 -------------------------------------------------------------
def test_each_requirement_blocks_until_it_is_met():
    block = progression.practice_block
    c = _c(WILD)
    for sid in FREE:                                               # 荒野、空手、空背包也能練
        assert block(c, gd, sid) is None, sid
    for sid, service in (("mercantile", "商店"), ("speechcraft", "旅店"), ("smithing", "鐵匠")):
        assert block(c, gd, sid) == f"這裡沒有{service}"
        assert block(_c(CITY), gd, sid) is None
    assert block(c, gd, "blade") == "要手持刀劍類的武器" and block(c, gd, "blunt") == "要手持鈍器類的武器"
    assert block(c, gd, "marksman") == "要手持射術類的武器"
    _wield(c, "iron_sword")
    assert block(c, gd, "blade") is None and block(c, gd, "blunt") == "要手持鈍器類的武器"
    _wield(c, MACE)
    assert block(c, gd, "blunt") is None and block(c, gd, "blade") == "要手持刀劍類的武器"
    _wield(c, BOW)
    assert block(c, gd, "marksman") is None

    c = _c(WILD)
    assert block(c, gd, "block") == "要裝備盾牌"
    assert block(c, gd, "heavy_armor") == "要穿著至少一件重甲" and block(c, gd, "light_armor") == "要穿著至少一件輕甲"
    _wear(c, SHIELD)
    assert block(c, gd, "block") is None
    _wear(c, HEAVY)
    assert block(c, gd, "heavy_armor") is None
    light = _c(WILD)
    _wear(light, LIGHT)
    assert block(light, gd, "light_armor") is None and block(light, gd, "heavy_armor") == "要穿著至少一件重甲"

    c = _c(WILD)
    assert block(c, gd, "security") == "手邊沒有開鎖器" and block(c, gd, "alchemy") == "手邊沒有煉金材料"
    inventory.add_item(c, "lockpick", 1)
    inventory.add_item(c, "wheat", 1)
    assert block(c, gd, "security") is None and block(c, gd, "alchemy") is None
    for sid in MAGIC:
        assert block(c, gd, sid) == f"還不會任何{gd.skill_name(sid)}系法術", sid
        spell = next(k for k, sp in gd.spells.items() if sp["school"] == sid)
        mage = _c(WILD)
        mage.spells = [spell]
        assert block(mage, gd, sid) is None
        assert all(block(mage, gd, other) is not None for other in MAGIC if other != sid)   # 只開自己那一系


# --- 3 上限 ---------------------------------------------------------------
def test_practice_stops_at_fifty_and_trainers_still_reach_seventy_five():
    assert formulas.PRACTICE_CAP == 50 < formulas.TRAINER_CAP == 75 < formulas.SKILL_CAP == 100
    c = _c(WILD, athletics=49)
    assert progression.practice_block(c, gd, "athletics") is None
    c.skills["athletics"] = 50
    why = progression.practice_block(c, gd, "athletics")
    assert why == "自己練已經到頂(練習上限 50),再上去得找訓練師或在實戰中磨練"
    master_city, master = next((lid, t["master"]) for lid, t in gd.trainers.items() if t.get("master"))
    assert world.trainer_cap(gd, master_city, master["skill"]) == 100
    other = next(s for s in gd.skills if s != master["skill"])
    assert world.trainer_cap(gd, master_city, other) == 75          # 訓練師賣的是 50 → 75 這一段

    c = _c(WILD, athletics=49)
    st = _state(c)
    t0 = st.time.absolute_hours()
    with _Script(["combat", "athletics"], ints=[24]) as s:
        M.action_practice(st, gd)
    need = formulas.skill_threshold(49) / gd.skills["athletics"]["practice"]["xp"]
    spent = st.time.absolute_hours() - t0
    assert c.base_skill("athletics") == 50 and 0 < spent < 24 and spent <= need * 2 + 1   # 練到 50 就停,不空耗
    assert any("已練到自學的上限(50)" in m for m in s.msgs), s.msgs

    with _Script(["combat", "athletics", None]) as s:               # 已到頂:選了只說明原因,不耗時間
        M.action_practice(st, gd)
    assert st.time.absolute_hours() - t0 == spent
    assert "〔現在不能練:自己練已經到頂" in s.menus[1][2]["athletics"]
    assert any(m.startswith("運動:自己練已經到頂") for m in s.msgs)


# --- 4 耗材 ---------------------------------------------------------------
def test_consumables_are_spent_one_per_hour_cheapest_first():
    c = _c(WILD)
    inventory.add_item(c, "lockpick", 3)
    assert progression.practice_supply(c, gd, "security") == ("開鎖器", 3)
    assert progression.practice_supply(c, gd, "athletics") is None
    st = _state(c)
    with _Script(["stealth", "security"]) as s:
        M.action_practice(st, gd)
    prompt, default, lo, hi = s.prompts[0]
    assert (lo, hi) == (1, 3) and default <= 3 and "每小時耗 1 件開鎖器,手邊有 3 件" in prompt
    assert inventory.count_item(c, "lockpick") == 0 and any(m == "用掉了開鎖器 ×3。" for m in s.msgs), s.msgs

    c = _c(WILD)
    pricey = max((i for i, d in gd.ingredients.items()), key=lambda i: gd.item(i)["value"])
    inventory.add_item(c, pricey, 1)
    inventory.add_item(c, "wheat", 2)
    assert gd.item("wheat")["value"] < gd.item(pricey)["value"]
    assert progression.practice_supply(c, gd, "alchemy") == ("煉金材料", 3)
    assert progression.practice_consume(c, gd, "alchemy") == "wheat"          # 挑最便宜的
    assert progression.practice_consume(c, gd, "alchemy") == "wheat"
    assert progression.practice_consume(c, gd, "alchemy") == pricey
    assert progression.practice_block(c, gd, "alchemy") == "手邊沒有煉金材料"
    assert progression.practice_consume(c, gd, "athletics") is None           # 不耗材料的技能


# --- 5 選單 ---------------------------------------------------------------
def test_menu_marks_blocked_skills_and_a_blocked_pick_costs_nothing():
    c = _c(WILD)
    st = _state(c)
    t0, f0 = st.time.absolute_hours(), c.fatigue
    with _Script(["combat", "blade", "stealth", "mercantile", None]) as s:
        M.action_practice(st, gd)
    assert st.time.absolute_hours() == t0 and c.fatigue == f0                  # 選了不能練的:不耗時間與體力
    labels = s.menus[1][2]
    assert labels["blade"].endswith("〔現在不能練:要手持刀劍類的武器〕")
    assert labels["athletics"].endswith(gd.skills["athletics"]["practice"]["label"])
    assert s.menus[3][2]["mercantile"].endswith("〔現在不能練:這裡沒有商店〕")
    assert [m for m in s.msgs] == ["刀劍:要手持刀劍類的武器。", "交易:這裡沒有商店。"]
    assert [t for t, _k, _l in s.menus] == ["要練哪一類?", "練習哪項技能?", "要練哪一類?", "練習哪項技能?", "要練哪一類?"]

    with _Script(["combat", "athletics"], ints=[1]) as s:                      # 練過一次 → 記住
        M.action_practice(st, gd)
        assert M._last_practice_skill == "athletics"
        s.answers = ["__last__"]
        M.action_practice(st, gd)
        assert s.menus[-1][0] == "要練什麼?" and "__last__" in s.menus[-1][1]
        c.skills["athletics"] = formulas.PRACTICE_CAP                          # 到頂之後不再給「↻ 再練」
        s.answers = [None]
        M.action_practice(st, gd)
        assert s.menus[-1][0] == "要練哪一類?"


# --- 6 只管練習這個動作 --------------------------------------------------------
def test_requirements_do_not_touch_the_shared_practice_price():
    c = _c(WILD, security=60)
    f0 = c.fatigue
    xp, hours, tired = progression.practice_cost(c, gd, "security")            # 實戰撬鎖沿用的體力 / 時數價碼
    p = gd.skills["security"]["practice"]
    assert (xp, hours, tired) == (p["xp"], p["hours"], False) and c.fatigue == f0 - p["fatigue"]
    assert inventory.count_item(c, "lockpick") == 0                            # 不會因此耗開鎖器、也不看上限


# --- 7 技能詳情 -------------------------------------------------------------
def test_skill_detail_note_matches_the_menu_reason():
    c = _c(WILD)
    note = ui._practice_note(c, gd, "blade")
    assert note.startswith(gd.skills["blade"]["practice"]["label"] + "(只能練到 50 級,再上去靠訓練師或實戰)")
    why = progression.practice_block(c, gd, "blade")
    assert why is not None and note.endswith("—— 現在不能練:" + why)
    assert "現在不能練" not in ui._practice_note(c, gd, "athletics")


# --- 8 量測腳本 -------------------------------------------------------------
def test_trainers_keep_an_exclusive_band():
    assert formulas.PRACTICE_CAP < formulas.TRAINER_CAP
    assert E.train_total(formulas.PRACTICE_CAP, formulas.TRAINER_CAP) == 12400
    assert E.level_if_all_skills_reach(formulas.PRACTICE_CAP) < E.level_if_all_skills_reach(formulas.TRAINER_CAP)
    hours = E.practice_hours(formulas.SKILL_BASE, formulas.PRACTICE_CAP)
    assert 200 < min(hours) and max(hours) < 320                               # 5 → 50 約 259 小時(量級守衛)


# --- 9 突變 ---------------------------------------------------------------
def test_guards_bite_under_in_process_mutations():
    real = progression.practice_block
    progression.practice_block = lambda *_a, **_k: None                        # 1 條件與上限全不擋
    try:
        assert _expect_fail(test_each_requirement_blocks_until_it_is_met)
        assert _expect_fail(test_menu_marks_blocked_skills_and_a_blocked_pick_costs_nothing)
        assert _expect_fail(test_skill_detail_note_matches_the_menu_reason)
    finally:
        progression.practice_block = real
    saved = formulas.PRACTICE_CAP
    formulas.PRACTICE_CAP = formulas.TRAINER_CAP                               # 2 練習上限退回與訓練師相同
    try:
        assert _expect_fail(test_practice_stops_at_fifty_and_trainers_still_reach_seventy_five)
        assert _expect_fail(test_trainers_keep_an_exclusive_band)
    finally:
        formulas.PRACTICE_CAP = saved
    real = progression.practice_consume
    progression.practice_consume = lambda *_a, **_k: None                      # 3 練習不耗材料
    try:
        assert _expect_fail(test_consumables_are_spent_one_per_hour_cheapest_first)
    finally:
        progression.practice_consume = real
    saved = dict(gd.skills["athletics"]["practice"])
    gd.skills["athletics"]["practice"]["requires"] = {"service": "merchant"}    # 4 資料被改:不設條件的技能多了條件
    try:
        assert _expect_fail(test_requirements_table_is_the_approved_one)
        assert _expect_fail(test_each_requirement_blocks_until_it_is_met)
    finally:
        gd.skills["athletics"]["practice"] = saved
    real = progression._practice_stock
    progression._practice_stock = lambda c, g, s: sorted(real(c, g, s), key=lambda r: -g.item(r[0]).get("value", 0))   # 5 挑最貴的
    try:
        assert _expect_fail(test_consumables_are_spent_one_per_hour_cheapest_first)
    finally:
        progression._practice_stock = real
    test_each_requirement_blocks_until_it_is_met()                             # 還原後仍綠
    test_requirements_table_is_the_approved_one()


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_practice_r224 OK")
