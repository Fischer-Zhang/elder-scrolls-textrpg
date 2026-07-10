"""限時增益藥水(R30)單元測試:強化屬性/技能/抗元素藥水的釀造、限時層、存檔相容。

涵蓋:brew 路由與優先序、synth round-trip、effective-not-base(增益走獨立層不寫 base)、
到期清除、抗元素入 entity_resist、刷新/取最強非疊加、param-specific kind 不誤判共有、
存檔 round-trip、舊存檔遷移、載入即剔除過期。
"""

from tesrpg import synth
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import alchemy, inventory, magic, potion_buff


def _state(seed=1, hour=12, skill=60):
    gd = get_gamedata()
    c = build_character(gd, name="藥", sex="female", race="breton",
                        birthsign="mage", class_id="mage")
    c.is_player = True
    c.skills["alchemy"] = skill
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour),
                   start_time=GameTime(hour=hour))
    return gd, c, st


# --- 釀造路由 -----------------------------------------------------------
def test_brew_fortify_attribute():
    gd, c, st = _state()
    inventory.add_item(c, "lavender", 1); inventory.add_item(c, "glow_dust", 1)
    r = alchemy.brew(c, gd, "lavender", "glow_dust", RNG(0))
    assert r["ok"] and r["kind"] == "buff"
    eff = gd.item(r["item_id"])["effect"]
    assert eff["type"] == "fortify_attribute" and eff["attr"] == "willpower"
    assert eff["magnitude"] >= 1 and eff["duration_hours"] >= 1


def test_brew_fortify_skill():
    gd, c, st = _state()
    inventory.add_item(c, "ash_yam", 1); inventory.add_item(c, "nirnroot", 1)   # R143:骨粉改死靈主題 → 煉金對=灰燼薯+奈恩根(煉金師招牌)
    r = alchemy.brew(c, gd, "ash_yam", "nirnroot", RNG(0))
    assert r["ok"] and r["kind"] == "buff"
    eff = gd.item(r["item_id"])["effect"]
    assert eff["type"] == "fortify_skill" and eff["skill"] == "alchemy"


def test_brew_resist_element():
    gd, c, st = _state()
    inventory.add_item(c, "monarch_wing", 1); inventory.add_item(c, "scrib_jelly", 1)
    r = alchemy.brew(c, gd, "monarch_wing", "scrib_jelly", RNG(0))
    assert r["ok"] and r["kind"] == "buff"
    eff = gd.item(r["item_id"])["effect"]
    assert eff["type"] == "resist_element" and eff["element"] == "magic"


def test_param_specific_kind_not_falsely_shared():
    """不同屬性的強化材(意志 vs 敏捷)不應被誤判為共有效果 → 仍釀造失敗。"""
    gd, c, st = _state()
    inventory.add_item(c, "lavender", 1); inventory.add_item(c, "garlic", 1)
    r = alchemy.brew(c, gd, "lavender", "garlic", RNG(0))
    assert not r["ok"]   # 一個強化意志、一個強化敏捷,kind 不同 → 無共有效果


def test_buff_brew_time_cost_is_practice_not_duration():
    """釀造耗時(res[hours],呼叫端推進世界時間)= 煉金 practice 成本,
    與藥效時長(編入 id 的 duration_hours)無關 —— 防回歸:勿用同一變數混淆兩者。"""
    gd, c, st = _state(skill=100)   # 高技能 → 時長(3)明顯 ≠ 釀造耗時(1),否則測不出混淆
    practice_h = gd.skills["alchemy"]["practice"]["hours"]
    inventory.add_item(c, "lavender", 1); inventory.add_item(c, "glow_dust", 1)
    rb = alchemy.brew(c, gd, "lavender", "glow_dust", RNG(0))
    assert rb["kind"] == "buff"
    assert rb["hours"] == practice_h                       # 釀造耗時 = practice(1),非藥效時長
    assert gd.item(rb["item_id"])["effect"]["duration_hours"] > rb["hours"]   # 時長確實 > 耗時
    # 與回復藥水同耗時(一致性)
    inventory.add_item(c, "wheat", 1); inventory.add_item(c, "blue_mountain_flower", 1)
    rp = alchemy.brew(c, gd, "wheat", "blue_mountain_flower", RNG(0))
    assert rp["hours"] == rb["hours"] == practice_h


def test_higher_alchemy_stronger_buff():
    gd, c, st = _state(skill=0)
    inventory.add_item(c, "lavender", 1); inventory.add_item(c, "glow_dust", 1)
    lo = gd.item(alchemy.brew(c, gd, "lavender", "glow_dust", RNG(0))["item_id"])["effect"]["magnitude"]
    c.skills["alchemy"] = 100
    inventory.add_item(c, "lavender", 1); inventory.add_item(c, "glow_dust", 1)
    hi = gd.item(alchemy.brew(c, gd, "lavender", "glow_dust", RNG(0))["item_id"])["effect"]["magnitude"]
    assert hi > lo


# --- synth round-trip ---------------------------------------------------
def test_synth_roundtrip():
    gd, _, _ = _state()
    for kind, want in (("fattr_willpower", ("fortify_attribute", "attr", "willpower")),
                       ("fskill_alchemy", ("fortify_skill", "skill", "alchemy")),
                       ("resist_fire", ("resist_element", "element", "fire"))):
        d = gd.item(synth.brew_buff_id(kind, 5, 3))
        assert d["kind"] == "potion"
        eff = d["effect"]
        assert eff["type"] == want[0] and eff[want[1]] == want[2]
        assert eff["magnitude"] == 5 and eff["duration_hours"] == 3
        assert gd.item_name(synth.brew_buff_id(kind, 5, 3))   # 不應拋例外(coat/背包選單會用)


# --- 限時層:effective-not-base + 到期 ---------------------------------
def test_use_fortify_effective_not_base():
    gd, c, st = _state()
    base = c.base_attr("willpower")
    # apply_buff 等同飲用(脫離 inventory 計數,直接驗證限時層行為)
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "willpower", 5, 2)
    assert c.attr("willpower") == base + 5
    assert c.base_attr("willpower") == base          # 絕不寫 base(R19/R20)
    # 推進超過時長 → update 剔除 → 回到 base
    st.time.advance(3)
    evs = potion_buff.update(st, gd)
    assert any(e["kind"] == "expire" for e in evs)
    assert c.attr("willpower") == base and not c.potion_buffs


def test_use_item_requires_state_for_buff():
    """限時增益在無 state 時不可用(也不消耗);即時藥水不受影響。"""
    gd, c, st = _state()
    pid = synth.brew_buff_id("fattr_willpower", 5, 2)
    inventory.add_item(c, pid, 1)
    assert inventory.use_item(c, gd, pid) is None          # 無 state → None
    assert inventory.count_item(c, pid) == 1               # 未消耗
    assert inventory.use_item(c, gd, pid, st) is not None  # 帶 state → 生效
    assert inventory.count_item(c, pid) == 0


def test_resist_into_entity_resist():
    gd, c, st = _state()
    before = magic.entity_resist(c, gd).get("frost", 0)
    potion_buff.apply_buff(c, st, gd, "resist_element", "frost", 12, 2)
    assert magic.entity_resist(c, gd).get("frost", 0) == before + 12
    st.time.advance(3); potion_buff.update(st, gd)
    assert magic.entity_resist(c, gd).get("frost", 0) == before


def test_fortify_endurance_raises_max_fatigue():
    """強化耐力/意志須經 recompute 流進衍生資源上限(R05)。"""
    gd, c, st = _state()
    mf = c.max_fatigue
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "endurance", 8, 4)
    assert c.max_fatigue > mf


# --- 疊加規則:刷新/取最強,非相加 -----------------------------------
def test_stacking_refresh_or_max_not_additive():
    gd, c, st = _state()
    base = c.base_attr("willpower")
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "willpower", 5, 2)
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "willpower", 3, 2)
    assert c.attr("willpower") == base + 5            # 取最強,不是 +8
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "willpower", 7, 2)
    assert c.attr("willpower") == base + 7            # 更強者取代
    assert len(c.potion_buffs) == 1                   # 同 kind+param 僅一筆


def test_different_params_stack_independently():
    gd, c, st = _state()
    bw, ba = c.base_attr("willpower"), c.base_attr("agility")
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "willpower", 5, 2)
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "agility", 4, 2)
    assert c.attr("willpower") == bw + 5 and c.attr("agility") == ba + 4
    assert len(c.potion_buffs) == 2


# --- 存檔相容 -----------------------------------------------------------
def test_save_roundtrip_preserves_buffs():
    gd, c, st = _state()
    potion_buff.apply_buff(c, st, gd, "fortify_attribute", "willpower", 5, 99)
    d = c.to_dict()
    assert "potion_buffs" in d
    c2 = Character.from_dict(d)
    assert c2.potion_buffs == c.potion_buffs


def test_old_save_without_potion_fields_loads():
    gd, c, st = _state()
    d = c.to_dict()
    for k in ("potion_buffs", "potion_attr_bonus", "potion_skill_bonus", "potion_resist"):
        d.pop(k, None)
    c2 = Character.from_dict(d)
    assert c2.potion_buffs == [] and c2.potion_attr_bonus == {}
    # ensure 補欄 + 重算不應拋例外
    potion_buff.ensure_potion_fields(c2, st.time, gd)
    assert c2.potion_buffs == []


def test_expired_buff_dropped_on_load():
    """存了一筆已過期的增益 → ensure(載入接線)應剔除,屬性回 base。"""
    gd, c, st = _state(hour=100)
    base = c.base_attr("willpower")
    # 手工塞一筆過期增益(expires_at 在當前之前)
    c.potion_buffs = [{"kind": "fortify_attribute", "param": "willpower",
                       "magnitude": 5, "expires_at": st.time.absolute_hours() - 1}]
    potion_buff.ensure_potion_fields(c, st.time, gd)
    assert c.potion_buffs == [] and c.attr("willpower") == base


def test_bad_buff_entry_is_pruned():
    gd, c, st = _state()
    c.potion_buffs = ["garbage", {"kind": "fortify_attribute"}, None]   # 壞值
    potion_buff.recompute(c, st, gd)
    assert c.potion_buffs == []


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_potion_buff")
