"""同伴深化(Tier 2)測試:屬性+技能+裝備 → 生成時導出戰力、裝備 sink 移轉(保淬鍊)、
附魔完全比照玩家、char=None byte-identical、單同伴孤立牆、技能夾限、存檔遷移。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import combat, inventory, party, smithing


def _char(cids=("veteran",)):
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    for cid in cids:
        c.companions.append(cid)
    return gd, c


def test_no_gear_is_template():
    """無裝同伴 → 走模板數值(byte-identical to 今日),不掛附魔載體。"""
    gd, c = _char()
    cr = combat.spawn_companion(gd, "veteran", RNG(1), char=c)
    t = gd.companions["veteran"]
    assert cr.attack["damage"] == t["attack"]["damage"]
    assert cr.attack["skill"] == t["attack"]["skill"]
    assert cr.armor_rating == t["armor_rating"]
    assert not hasattr(cr, "_gear_weapon")


def test_char_none_equals_no_gear():
    """char=None(既有 3-/5-arg 呼叫)與 char=無裝 → 逐位元組同(向後相容)。"""
    gd, c = _char()
    a = combat.spawn_companion(gd, "veteran", RNG(1))
    b = combat.spawn_companion(gd, "veteran", RNG(1), char=c)
    assert (a.attack["damage"], a.attack["skill"], a.armor_rating) == \
           (b.attack["damage"], b.attack["skill"], b.armor_rating)


def test_gear_derives_from_skill_and_temper():
    gd, c = _char()
    inventory.add_item(c, "daedric_sword", 1)
    c.weapon_temper["daedric_sword"] = 5
    assert party.equip_gear(c, gd, "veteran", "daedric_sword")
    cr = combat.spawn_companion(gd, "veteran", RNG(1), char=c)
    sw = gd.item("daedric_sword")
    assert cr.attack["damage"] == sw["damage"] + 5 * smithing.TEMPER_WEAPON_PER   # 裝備傷 + flat 淬鍊
    assert cr.attack["skill"] == party.companion_skill(gd, "veteran", "blade")     # 同伴武器技能
    assert getattr(cr, "_gear_weapon") == "daedric_sword"
    assert "element" not in cr.attack                                              # 實體武器 → 物理基礎


def test_equip_moves_item_and_preserves_temper():
    gd, c = _char()
    inventory.add_item(c, "steel_sword", 2)
    c.weapon_temper["steel_sword"] = 3
    assert party.equip_gear(c, gd, "veteran", "steel_sword")
    assert inventory.count_item(c, "steel_sword") == 1   # 移出一件(戰利品 sink)
    assert c.weapon_temper.get("steel_sword") == 3       # 淬鍊保留(移轉非銷毀)
    assert party.unequip_gear(c, gd, "veteran", "weapon")
    assert inventory.count_item(c, "steel_sword") == 2   # 卸回背包


def test_sell_last_copy_keeps_temper_if_companion_wears():
    """賣掉背包最後一份、但同伴仍穿戴一份 → 不誤清共享淬鍊(companion-worn 守衛)。"""
    gd, c = _char()
    inventory.add_item(c, "iron_sword", 1)
    c.weapon_temper["iron_sword"] = 2
    party.equip_gear(c, gd, "veteran", "iron_sword")     # 移出 → 背包 0、同伴穿戴
    inventory.add_item(c, "iron_sword", 1)               # 又撿一把
    inventory.remove_item(c, "iron_sword", 1)            # 賣掉背包最後份
    assert c.weapon_temper.get("iron_sword") == 2         # 同伴仍穿戴 → 淬鍊不失


def test_skill_clamped_to_cap():
    """companion_skill 夾 ≤ CAP(即使 JSON 誤植 >80 亦守牆)。"""
    gd, c = _char()
    old = gd.companions["veteran"]["skills"].get("blade")
    gd.companions["veteran"]["skills"]["blade"] = 999
    try:
        assert party.companion_skill(gd, "veteran", "blade") == party.COMPANION_WEAPON_SKILL_CAP
    finally:
        gd.companions["veteran"]["skills"]["blade"] = old


def test_armor_resist_enchant_baked():
    gd, c = _char()
    aid = "daedric_cuirass"
    it = gd.item(aid)
    old = it.get("enchant")
    it["enchant"] = {"kind": "resist_element", "element": "fire", "magnitude": 30}
    try:
        inventory.add_item(c, aid, 1)
        party.equip_gear(c, gd, "veteran", aid)
        cr = combat.spawn_companion(gd, "veteran", RNG(1), char=c)
        assert cr.resist.get("fire", 0) >= 30
    finally:
        if old is None:
            it.pop("enchant", None)
        else:
            it["enchant"] = old


def test_weapon_enchant_parity_fires():
    """完全比照玩家:同伴持附魔武器(元素 DoT)命中 → 敵中 DoT(附魔派發對同伴生效)。"""
    gd, c = _char()
    wid = "steel_sword"
    it = gd.item(wid)
    old = it.get("enchant")
    it["enchant"] = {"kind": "weapon_status", "status": "burn", "element": "fire",
                     "magnitude": 10, "turns": 3, "chance": 1.0}
    try:
        inventory.add_item(c, wid, 1)
        party.equip_gear(c, gd, "veteran", wid)
        applied = False
        for s in range(25):
            comp = combat.spawn_companion(gd, "veteran", RNG(s), char=c)
            dummy = combat.spawn_creature(gd, "bandit", RNG(s + 100))
            dummy.max_health = 9999
            dummy.health = 9999
            combat.resolve_attack(comp, dummy, gd, RNG(s + 1))
            if any(e.get("kind") == "dot" and e.get("source") == "ench_dot" for e in dummy.active_effects):
                applied = True
                break
        assert applied, "companion weapon enchant (burn DoT) never fired"
    finally:
        if old is None:
            it.pop("enchant", None)
        else:
            it["enchant"] = old


def test_fortify_skill_parity_clamped():
    """護甲 fortify_skill 附魔平價:加向技能 CAP·但 SUM 一律夾 ≤80(守單同伴孤立牆)。char=None → 無平價。"""
    gd, c = _char(("rashid",))
    aid = "daedric_cuirass"
    it = gd.item(aid)
    old = it.get("enchant")
    it["enchant"] = {"kind": "fortify_skill", "skill": "blade", "magnitude": 20}
    try:
        # 無 char → 純模板(rashid blade 74)
        assert party.companion_skill(gd, "rashid", "blade") == 74
        inventory.add_item(c, aid, 1)
        party.equip_gear(c, gd, "rashid", aid)
        # char + fortify blade +20 → 74+20=94 夾 → 80(守牆)
        assert party.companion_skill(gd, "rashid", "blade", c) == party.COMPANION_WEAPON_SKILL_CAP
        # 不匹配的技能不受影響
        assert party.companion_skill(gd, "rashid", "marksman", c) == party.companion_skill(gd, "rashid", "marksman")
    finally:
        if old is None:
            it.pop("enchant", None)
        else:
            it["enchant"] = old


def test_single_companion_wall_holds():
    """🔴 紅線:單一同伴(排除玩家)滿裝+吸血 vs 達貢 = 0%(快查 n=12)。"""
    import sim_party as sp
    w, _avg = sp.solo_companion_rates(
        "farkas", n=12, weapon="volendrung", armor="daedric_cuirass", temper=5,
        inject_ench={"kind": "weapon_status", "status": "vampiric", "magnitude": 50})
    assert w == 0.0, f"single-companion wall broken: {w:.0%}"


def test_save_roundtrip_and_old_save_defaults():
    gd, c = _char()
    inventory.add_item(c, "steel_sword", 1)
    party.equip_gear(c, gd, "veteran", "steel_sword")
    c.companion_build["veteran"] = "bulwark"
    c2 = Character.from_dict(c.to_dict())
    assert c2.companion_gear == c.companion_gear and c2.companion_build == c.companion_build
    d = c.to_dict()
    d.pop("companion_gear", None)
    d.pop("companion_build", None)                      # 舊存檔缺欄
    c3 = Character.from_dict(d)
    assert c3.companion_gear == {} and c3.companion_build == {}


def test_ensure_prunes_stale_and_returns_gear():
    gd, c = _char()
    c.companion_gear["ghost_cid"] = {"weapon": "steel_sword"}   # 無效同伴
    party.ensure_companion_gear(c, gd)
    assert "ghost_cid" not in c.companion_gear
    assert inventory.count_item(c, "steel_sword") == 1          # 退回背包不遺失
    c.companion_build["veteran"] = "bogus"                      # 未知 build_id
    party.ensure_companion_build(c, gd)
    assert "veteran" not in c.companion_build


def test_forget_returns_gear():
    gd, c = _char()
    inventory.add_item(c, "steel_sword", 1)
    party.equip_gear(c, gd, "veteran", "steel_sword")
    party.forget(c, "veteran")
    assert "veteran" not in c.companion_gear
    assert inventory.count_item(c, "steel_sword") == 1


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_companion_gear OK")
