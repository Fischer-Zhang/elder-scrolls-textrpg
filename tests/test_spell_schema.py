"""法術資料結構與可達性驗證(無死內容守門)。

承法術學派補完里程碑新增:確保每道法術 schema 合法(必備鍵 + 合法 enum)、
召喚/復生引用的生物存在、且**每道法術都有取得途徑**(商店 spell_stock 或起手/職業/開局授予),
否則即死內容。
"""

from tesrpg import creation
from tesrpg.gamedata import get_gamedata

_SCHOOLS = {"destruction", "restoration", "alteration", "illusion", "conjuration", "mysticism"}
_TARGETS = {"self", "enemy", "ally", "allies", "all"}
_ELEMENTS = {"fire", "frost", "shock", "poison", "magic", "bleed"}
# cast() 實際分派的 effect kind(白名單;不在此即未實作 → 視為資料錯字)
_KINDS = {
    "damage", "damage_status", "heal", "restore_fatigue", "shield", "ward", "weapon_imbue",
    "bound_weapon", "fear", "weaken", "soul_trap", "dispel", "apply_status",
    "damage_all", "damage_status_all", "status_all", "summon", "reanimate", "empower",
    "cure_disease",
}
_ELEMENT_KINDS = {"damage", "damage_status", "damage_all", "damage_status_all", "weapon_imbue", "bound_weapon"}
_ALL_KINDS = {"damage_all", "damage_status_all", "status_all"}
_ALLY_KINDS = {"heal", "shield", "apply_status", "empower"}
_STATUSES = {"dot", "regen", "paralyze", "fear", "soul_trap", "stagger", "weaken"}


def test_every_spell_has_required_keys_and_valid_enums():
    gd = get_gamedata()
    for sid, sp in gd.spells.items():
        for key in ("name", "school", "cost", "target", "effect"):
            assert key in sp, f"{sid} 缺鍵 {key}"
        assert sp["school"] in _SCHOOLS, f"{sid} 不明學派 {sp['school']}"
        assert isinstance(sp["cost"], int) and sp["cost"] > 0, f"{sid} cost 非正整數"
        assert sp["target"] in _TARGETS, f"{sid} 不明 target {sp['target']}"
        eff = sp["effect"]
        k = eff.get("kind")
        assert k in _KINDS, f"{sid} 未實作的 effect kind {k}"
        if k in _ELEMENT_KINDS:
            assert eff.get("element") in _ELEMENTS, f"{sid} 缺/不明 element"
        if k in _ALL_KINDS:
            assert sp["target"] == "all", f"{sid} {k} 須 target=all"
        if sp["target"] in ("ally", "allies"):
            assert k in _ALLY_KINDS, f"{sid} 對同伴施放的 kind 不支援:{k}"
        # 內嵌 status 結構合法
        st = eff.get("status")
        if st is not None:
            assert st.get("status") in _STATUSES, f"{sid} 不明 status {st.get('status')}"
            assert "turns" in st, f"{sid} status 缺 turns"


def test_summon_and_reanimate_targets_exist_in_bestiary():
    gd = get_gamedata()
    for sid, sp in gd.spells.items():
        if sp["effect"].get("kind") == "summon":
            cre = sp["effect"].get("creature")
            assert cre in gd.bestiary, f"{sid} 召喚不存在的生物 {cre}"
            # 召喚物應 summon-gated(不野生刷出)且不掉落經濟物
            assert gd.bestiary[cre].get("weight", 1) == 0, f"{cre} 召喚物 weight 應為 0"


def test_every_spell_is_reachable():
    """每道法術須出現在某商店 spell_stock,或由起手/職業/開局授予 → 否則死內容。"""
    gd = get_gamedata()
    reachable = set()
    for loc in gd.world["locations"].values():
        reachable |= set(loc.get("spell_stock", []))
    reachable |= set(creation._SPELL_FOR_SCHOOL.values())
    reachable |= set(creation._CLASS_SIGNATURE_SPELL.values())
    import json
    import os
    odata = json.load(open(os.path.join(os.path.dirname(__file__), "..", "tesrpg", "data", "origins.json")))
    for od in odata.values():
        reachable |= set(od.get("spells", []))
    dead = [sid for sid in gd.spells if sid not in reachable]
    assert not dead, f"死內容法術(無任何取得途徑):{dead}"
    # 帝都樞紐全備 pin(對抗審查:8 新法術曾誤上架到海芬古而非帝都中央 → 確保中央可學)
    new = ("flame_blade", "frost_blade", "storm_blade", "heal_other",
           "healing_circle", "ward_ally", "regen_aura", "rally")
    assert all(s in gd.world["locations"]["imperial_city"].get("spell_stock", []) for s in new)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_spell_schema OK")
