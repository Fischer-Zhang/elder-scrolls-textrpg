"""M14:護甲附魔(armor_fortify)—— 穿戴時強化生命/魔力/體力。

驗證:
  1. enchant_armor 產出正確的合成物品(消耗護甲+靈魂石、鍛鍊神秘、id 可還原)。
  2. 穿戴 fortify 護甲 → 有效上限即時 +magnitude;卸下 → 還原。
  3. base_max_health 為真基底:health fortify 只影響 max_health,不污染基底。
  4. 存讀檔往返保留「有效上限 + 基底」,讀檔後穿/卸仍正確。
  5. 舊存檔遷移(無 base_max_health 欄位):recompute 不會讓血量崩塌;升級亦然。
  6. 不重複計數(重穿同件不疊加);卸下時當前值被夾限。
"""

import io
import json

from tesrpg import creation, synth
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import enchanting, inventory, progression, stats

gd = get_gamedata()


def _new_char():
    return creation.build_character(
        gd, name="附魔師", sex="female", race="breton",
        birthsign="mage", class_id="mage", rng=RNG(seed=1))


def _give(char, item_id, qty=1):
    inventory.add_item(char, item_id, qty)


# ---------------------------------------------------------------------------
def test_enchant_armor_produces_item():
    char = _new_char()
    _give(char, "leather_cuirass", 1)
    _give(char, "filled_common_soul_gem", 1)   # soul 3
    before_myst = char.skill("mysticism")

    res = enchanting.enchant_armor(char, gd, "leather_cuirass", "res", "magicka",
                                   "filled_common_soul_gem")
    assert res["ok"], res
    assert inventory.count_item(char, "leather_cuirass") == 0, "基底護甲應被消耗"
    assert inventory.count_item(char, "filled_common_soul_gem") == 0, "靈魂石應被消耗"

    enchanted = res["item_id"]
    assert synth.is_synth(enchanted) and enchanted.startswith("encha|")
    d = gd.item(enchanted)
    assert d["kind"] == "armor" and d["slot"] == "cuirass"
    assert d["enchant"] == {"kind": "armor_fortify", "stat": "magicka",
                            "magnitude": int(enchanted.split("|")[4])}
    assert inventory.count_item(char, enchanted) == 1
    # 神秘技能應有鍛鍊(可能升級也可能只累進度,至少不會下降)
    assert char.skill("mysticism") >= before_myst


def test_unknown_stat_rejected():
    char = _new_char()
    _give(char, "leather_cuirass", 1)
    _give(char, "filled_petty_soul_gem", 1)
    res = enchanting.enchant_armor(char, gd, "leather_cuirass", "bogus", "speed",
                                   "filled_petty_soul_gem")
    assert not res["ok"]
    # 失敗不該消耗材料
    assert inventory.count_item(char, "leather_cuirass") == 1
    assert inventory.count_item(char, "filled_petty_soul_gem") == 1


# ---------------------------------------------------------------------------
def test_equip_fortify_raises_and_unequip_restores():
    for stat, getter in (("magicka", lambda c: c.max_magicka),
                         ("fatigue", lambda c: c.max_fatigue),
                         ("health", lambda c: c.max_health)):
        char = _new_char()
        base = getter(char)
        eid = synth.enchant_armor_id("leather_cuirass", "res", stat, 25)
        _give(char, eid, 1)

        assert inventory.equip_armor(char, gd, eid)
        stats.recompute_max_resources(char, gd)
        assert getter(char) == base + 25, f"{stat}: 穿戴後應 +25"
        # health fortify 不可污染基底
        if stat == "health":
            assert char.base_max_health == base, "base_max_health 不應被改動"

        inventory.unequip(char, "cuirass")
        stats.recompute_max_resources(char, gd)
        assert getter(char) == base, f"{stat}: 卸下後應還原"


def test_no_double_count_on_reequip():
    char = _new_char()
    base = char.max_magicka
    eid = synth.enchant_armor_id("leather_cuirass", "res", "magicka", 20)
    _give(char, eid, 1)
    inventory.equip_armor(char, gd, eid)
    stats.recompute_max_resources(char, gd)
    inventory.equip_armor(char, gd, eid)            # 重穿同一件(同部位)
    stats.recompute_max_resources(char, gd)
    assert char.max_magicka == base + 20, "重穿不應疊加"


def test_unequip_clamps_current():
    char = _new_char()
    eid = synth.enchant_armor_id("leather_cuirass", "res", "magicka", 30)
    _give(char, eid, 1)
    inventory.equip_armor(char, gd, eid)
    stats.recompute_max_resources(char, gd, restore_full=True)   # 灌到滿(base+30)
    assert char.magicka == char.max_magicka
    inventory.unequip(char, "cuirass")
    stats.recompute_max_resources(char, gd)
    assert char.magicka <= char.max_magicka, "卸下後當前值應被夾限"


# ---------------------------------------------------------------------------
def test_save_load_roundtrip_with_fortify():
    char = _new_char()
    base_mag = char.max_magicka
    base_hp = char.base_max_health
    eid = synth.enchant_armor_id("leather_cuirass", "res", "magicka", 18)
    _give(char, eid, 1)
    inventory.equip_armor(char, gd, eid)
    stats.recompute_max_resources(char, gd)
    eff_mag = char.max_magicka
    assert eff_mag == base_mag + 18

    # 往返序列化(模擬存讀檔)
    blob = json.loads(json.dumps(char.to_dict()))
    loaded = Character.from_dict(blob)
    assert loaded.base_max_health == base_hp
    assert loaded.max_magicka == eff_mag, "讀檔應保留有效上限(存的是有效值)"

    # 讀檔後卸下 → 重算回基底
    inventory.unequip(loaded, "cuirass")
    stats.recompute_max_resources(loaded, gd)
    assert loaded.max_magicka == base_mag


# ---------------------------------------------------------------------------
def test_legacy_save_migration_no_collapse():
    """舊存檔沒有 base_max_health(預設 0):recompute 不可讓血量崩塌。"""
    char = _new_char()
    d = char.to_dict()
    old_hp = d["max_health"]
    del d["base_max_health"]              # 模擬舊存檔
    old = Character.from_dict(d)
    assert old.base_max_health == 0       # 缺欄位 → dataclass 預設

    stats.recompute_max_resources(old, gd)   # 無 fortify 護甲
    assert old.base_max_health == old_hp, "遷移應把現值搬成基底"
    assert old.max_health == old_hp, "血量不可崩塌"


def test_legacy_save_levelup_no_collapse():
    """改版前存檔(無 base_max_health)升級時不可崩血;ensure_base_health 仍生效。"""
    from tesrpg import formulas
    char = _new_char()
    d = char.to_dict()
    del d["base_max_health"]               # 模擬 M14 之前的存檔
    old = Character.from_dict(d)
    old_hp = old.max_health
    old.level_xp = formulas.levelup_xp_threshold(old.level)   # 直接設成可升級

    progression.apply_level_up(old, gd, {"endurance": 4})
    assert old.base_max_health == old_hp, "ensure_base_health 應把現值搬成基底(冗餘相容)"
    # R64:無資源三選一;R63 生命隨耐力 live 耦合 → 加 4 耐力 → +4×ENDURANCE_HEALTH_PER 生命,不崩塌
    assert old.max_health == old_hp + 4 * formulas.ENDURANCE_HEALTH_PER, \
        "舊存檔升級不崩塌 + 耐力 live 耦合加血"


# ---------------------------------------------------------------------------
# 回歸:丟棄/出售「穿戴中的 fortify 護甲」必須重算上限並夾限當前值
# (remove_item 移除最後一件會自動卸下,但本身不重算 → 曾導致幻影永久加成)
def _equipped_fortify_char(stat, mag):
    from tesrpg.state import GameState
    from tesrpg.rng import RNG
    char = _new_char()
    eid = synth.enchant_armor_id("leather_cuirass", "res", stat, mag)
    _give(char, eid, 1)
    inventory.equip_armor(char, gd, eid)
    stats.recompute_max_resources(char, gd, restore_full=True)
    state = GameState(player=char, rng=RNG(seed=1), game_mode="adventure")
    return char, state, eid


def _patch_ui(menu_fn):
    """暫時替換 ui.menu/message/show_events/confirm,回傳還原用的 restore()。
    confirm 預設回 True(R114C:高價丟棄/回爐加了確認 → 測試沿用「同意」語意)。"""
    from tesrpg.ui import console as ui
    saved = (ui.menu, ui.message, ui.show_events, ui.confirm)
    ui.menu = menu_fn
    ui.message = lambda *a, **k: None
    ui.show_events = lambda *a, **k: None
    ui.confirm = lambda *a, **k: True

    def restore():
        ui.menu, ui.message, ui.show_events, ui.confirm = saved
    return restore


def test_drop_equipped_fortify_recomputes():
    import tesrpg.main as M
    char, state, eid = _equipped_fortify_char("magicka", 40)
    base = char.max_magicka - 40
    assert char.max_magicka == base + 40 and char.magicka == base + 40
    restore = _patch_ui(lambda *a, **k: "drop")     # 對該護甲選「丟棄一件」
    try:
        M._item_actions(state, gd, eid)
    finally:
        restore()
    assert char.equipped == {}, "丟棄最後一件應自動卸下"
    assert char.max_magicka == base, "丟棄 fortify 護甲後上限須回到基底"
    assert char.magicka <= char.max_magicka, "當前值須被夾限"
    loaded = Character.from_dict(json.loads(json.dumps(char.to_dict())))
    assert loaded.max_magicka == base, "幻影加成不可被存檔固化"


def test_sell_equipped_fortify_recomputes():
    import tesrpg.main as M
    char, state, eid = _equipped_fortify_char("fatigue", 30)
    base = char.max_fatigue - 30
    assert char.max_fatigue == base + 30
    seq = iter(["sell", eid, None])                 # 商店→出售→賣該護甲→返回
    restore = _patch_ui(lambda *a, **k: next(seq, None))
    try:
        M.action_shop(state, gd)
    finally:
        restore()
    assert char.equipped == {}, "賣掉最後一件應自動卸下"
    assert char.max_fatigue == base, "賣掉 fortify 護甲後上限須回到基底"
    assert char.fatigue <= char.max_fatigue, "當前值須被夾限"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_m14 OK")
