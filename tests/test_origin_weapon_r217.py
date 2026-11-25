"""R217 出身武器 × 職業固定起手武器(R216 審查 A1;使用者 2026-11-25「照建議」= 方案 a)。

R208 / R209 給 8 個職業固定起手武器(= 身分:刺客 / 盜賊匕首、弓手 / 斥候弓、法師 / 治療師 / 召喚師 / 死靈師法杖),
但創角的出身武器段沿用 R208 前的規則「有武器主修就換手」→ 弓手 + 商隊護衛 → 鋼長劍、斥候 + 灰民部族子弟 → 鐵長槍、
盜賊 + 綠約遊俠 → 長弓……職業的固定武器被異系出身武器蓋掉(16 組出身推薦配對中 7 組),且全無 class×origin 測試。

R217:有固定起手武器的職業,出身武器只在「同系升級」(獵弓換長弓、鐵匕首換鋼匕首、法杖換更好的法杖)才換手;
異系只進背包。沒有固定起手武器的職業(戰士 / 騎士 / 戰法師 / 自訂)維持舊規則,逐位元組不變。

守衛:
  1. 全掃「有固定武器的職業」×「全部出身」:實際裝備的武器恆與職業固定武器同系;出身武器不會消失(背包或已裝備)
  2. 同系升級仍換手(長弓 / 鋼匕首 / 法杖)——合成出身,不依賴資料內容
  3. 異系只進背包(含 法杖給盜賊 / 弓手:舊規則的另一個漏洞)
  4. 沒有固定武器的職業 + 未知 / 自訂職業 id:維持舊規則
  5. R216 審查重現的 7 組異系配對現況釘死
"""
from contextlib import contextmanager

from tesrpg import creation
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import inventory

gd = get_gamedata()

# R216 審查重現的 7 組「異系」配對(職業, 出身, 該出身的武器)
_AUDIT_CROSS_FAMILY = (
    ("archer", "caravan_guard", "steel_sword"), ("archer", "sunhold_marine", "steel_sword"),
    ("scout", "ashlander", "iron_spear"), ("scout", "hist_warden", "iron_spear"),
    ("thief", "ranger_scout", "long_bow"), ("assassin", "tomb_seeker", "iron_sword"),
    ("thief", "tomb_seeker", "iron_sword"),
)


def _build(class_id, origin_id):
    return build_character(gd, name="T", sex="male", race="imperial", birthsign="shadow",
                           class_id=class_id, origin_id=origin_id)


@contextmanager
def _origin(weapon, oid="_r217_probe"):
    """合成一個只給一把武器的出身(測完移除)→ 規則測試不依賴 origins.json 的內容。"""
    gd.origins[oid] = {"name": "測試出身", "weapon": weapon}
    try:
        yield oid
    finally:
        gd.origins.pop(oid, None)


def _fam(weapon_id):
    """測試自己的獨立判定(不呼叫被測的 creation._weapon_family,否則突變把它改了、標準跟著變 = 空轉):
    法杖類同系,其餘看 (武器技能, 型態)。"""
    w = gd.item(weapon_id)
    return "staff" if w.get("archetype") == "staff" else (w.get("skill"), w.get("archetype"))


def test_every_fixed_weapon_class_keeps_its_weapon_family_under_every_origin():
    fixed = {cid: c["starting_weapon"] for cid, c in gd.classes.items() if c.get("starting_weapon") in gd.weapons}
    assert {"archer", "scout", "thief", "assassin", "mage"} <= set(fixed), fixed      # 前提:身分職業確實有固定武器
    assert len(gd.origins) >= 20                                                      # 掃描量防呆
    for cid, fw in fixed.items():
        for oid, od in gd.origins.items():
            c = _build(cid, oid)
            assert _fam(c.weapon) == _fam(fw), (cid, oid, c.weapon, fw)
            ow = od.get("weapon")
            if ow:                                    # 出身武器不會消失:在背包或已裝備
                assert inventory.count_item(c, ow) >= 1 or c.weapon == ow, (cid, oid, ow)


def test_same_family_origin_weapon_still_swaps_in():
    for cid, wid in (("archer", "long_bow"), ("scout", "long_bow"), ("assassin", "steel_dagger"),
                     ("thief", "steel_dagger"), ("mage", "flame_staff"), ("healer", "magicka_staff")):
        with _origin(wid) as oid:
            c = _build(cid, oid)
        assert c.weapon == wid, (cid, wid, c.weapon)


def test_cross_family_origin_weapon_goes_to_the_bag_only():
    for cid, wid in (("archer", "iron_sword"), ("archer", "iron_spear"), ("scout", "steel_sword"), ("thief", "long_bow"),
                     ("assassin", "iron_sword"), ("thief", "flame_staff"), ("archer", "flame_staff"), ("mage", "iron_sword")):
        fixed = gd.classes[cid]["starting_weapon"]
        with _origin(wid) as oid:
            c = _build(cid, oid)
        assert c.weapon == fixed, (cid, wid, c.weapon)
        assert inventory.count_item(c, wid) == 1, (cid, wid)            # 出身武器仍給玩家(在背包)


def test_classes_without_a_fixed_weapon_keep_the_old_rule():
    for cid in ("warrior", "knight", "battlemage"):
        assert not gd.classes[cid].get("starting_weapon"), cid           # 前提:這三職沒有固定起手武器
    for cid, wid in (("warrior", "iron_spear"), ("warrior", "long_bow"), ("warrior", "flame_staff"),
                     ("battlemage", "flame_staff")):
        with _origin(wid) as oid:
            c = _build(cid, oid)
        assert c.weapon == wid, (cid, wid, c.weapon)                    # 舊規則:有武器主修就換手 / 施法武器永遠裝
    c = _build("warrior", None)
    c.class_id = "custom"                                               # 未知 / 自訂職業 id → 沒有固定武器 → 走舊規則
    assert creation._equips_origin_weapon(c, gd, "iron_sword") is True


def test_the_seven_audited_cross_family_pairs_no_longer_override_the_class_weapon():
    for cid, oid, wid in _AUDIT_CROSS_FAMILY:
        assert gd.origins[oid].get("weapon") == wid, f"資料前提:{oid} 的出身武器應為 {wid}(資料若已改,請同步更新此守衛清單)"
        c = _build(cid, oid)
        assert c.weapon == gd.classes[cid]["starting_weapon"], (cid, oid, c.weapon)
        assert inventory.count_item(c, wid) >= 1, (cid, oid)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_origin_weapon_r217 OK")
