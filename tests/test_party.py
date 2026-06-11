"""同伴系統深化(持久 HP / 負傷 benched / 羈絆)的單元測試。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, party, warband


def _setup(cids=("sellsword",)):
    gd = get_gamedata()
    c = build_character(gd, name="L", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    for cid in cids:
        c.companions.append(cid)
    st = GameState(player=c, rng=RNG(1), time=GameTime(hour=12))
    return gd, c, st


def test_persistent_hp_spawn_and_record():
    gd, c, st = _setup()
    cid = "sellsword"; mx = party.max_hp(c, gd, cid)
    assert party.spawn_hp(c, gd, cid) == mx and cid in party.fieldable(c, gd)   # 初始滿血可上陣
    cre = combat.spawn_companion(gd, cid, st.rng); cre.health = 20              # 戰中受傷
    downed = party.record_after_battle(c, gd, [(cid, cre)])
    assert downed == [] and c.companion_hp[cid] == 20                            # 持久回寫
    assert party.spawn_hp(c, gd, cid) == 20
    cre2 = combat.spawn_companion(gd, cid, st.rng, current_hp=party.spawn_hp(c, gd, cid))
    assert cre2.health == 20                                                     # 下場以持久 HP 生成


def test_downed_benched_then_heal_restores_fieldable():
    gd, c, st = _setup()
    cid = "sellsword"
    cre = combat.spawn_companion(gd, cid, st.rng); cre.health = 0               # 倒下
    downed = party.record_after_battle(c, gd, [(cid, cre)])
    assert downed == [gd.companions[cid]["name"]]
    assert party.is_downed(c, gd, cid) and cid not in party.fieldable(c, gd)    # benched
    party.heal(c, gd, 0.5)                                                       # 休息回復
    assert not party.is_downed(c, gd, cid) and cid in party.fieldable(c, gd)    # 康復可再上陣


def test_bond_grows_on_victory_and_boosts_hp():
    gd, c, st = _setup()
    cid = "sellsword"; base_mx = gd.companions[cid]["max_health"]
    assert party.bond_tier(c, cid) == 0 and party.max_hp(c, gd, cid) == base_mx
    for _ in range(party.BOND_TIERS[0]):                                         # 多場並肩獲勝
        cre = combat.spawn_companion(gd, cid, st.rng)                            # 存活
        party.award_victory(c, gd, [(cid, cre)])
    assert party.bond_tier(c, cid) >= 1
    assert party.max_hp(c, gd, cid) > base_mx                                    # 羈絆 → 更耐打
    bonus = party.bond_hp_bonus(c, cid)
    cre = combat.spawn_companion(gd, cid, st.rng, max_health_bonus=bonus)
    assert cre.max_health == base_mx + bonus                                     # 加成流進生成
    # 併入 test_downed_companion_not_awarded_bond:陣亡同伴走負分支(party.py:98)→ 不累積羈絆
    cre = combat.spawn_companion(gd, cid, st.rng); cre.health = 0                # 陣亡
    before = party.bond_points(c, cid)                                          # into 已非零基線
    party.award_victory(c, gd, [(cid, cre)])
    assert party.bond_points(c, cid) == before                                  # 陣亡不得羈絆


def test_heal_full_and_forget():
    gd, c, st = _setup(("sellsword", "shieldmaiden"))
    c.companion_hp["sellsword"] = 5
    party.heal_full(c, gd)
    assert c.companion_hp["sellsword"] == party.max_hp(c, gd, "sellsword")
    party.forget(c, "sellsword")
    assert "sellsword" not in c.companion_hp and "sellsword" not in c.companion_bond


def test_siege_casualty_forgets_persistent_state():
    gd, c, st = _setup(("veteran",))
    c.companion_hp["veteran"] = 10; c.companion_bond["veteran"] = 20
    warband.apply_casualties(c, gd, ["veteran"])
    assert "veteran" not in c.companions
    assert "veteran" not in c.companion_hp and "veteran" not in c.companion_bond  # 永久陣亡 → forget


def test_save_roundtrip_and_old_save_defaults():
    gd, c, st = _setup()
    c.companion_hp["sellsword"] = 30; c.companion_bond["sellsword"] = 12
    c2 = Character.from_dict(c.to_dict())
    assert c2.companion_hp == c.companion_hp and c2.companion_bond == c.companion_bond
    d = c.to_dict(); d.pop("companion_hp", None); d.pop("companion_bond", None)  # 舊存檔缺欄
    c3 = Character.from_dict(d)
    assert c3.companion_hp == {} and c3.companion_bond == {}
    assert party.spawn_hp(c3, gd, "sellsword") == party.max_hp(c3, gd, "sellsword")   # 預設滿血


def test_defensive_clamps_and_no_stale_legacy():
    """對抗審查回歸:current_hp/heal 夾 [0,上限](防毀損存檔負值);legacy 只認在隊者(無羈絆殘影)。"""
    gd, c, st = _setup()
    cid = "sellsword"
    c.companion_hp[cid] = -5                                  # 模擬毀損存檔負值
    assert party.current_hp(c, gd, cid) == 0
    party.heal(c, gd, 0.0)
    assert c.companion_hp[cid] == 0                            # heal 也夾回 ≥0
    c.companion_bond["shieldmaiden"] = party.BOND_TIERS[0]     # 離隊殘留羈絆(不在 companions)
    assert party.legacy_label(c, gd) is None                   # 只認在隊者 → 不受殘影影響
    # 併入 test_legacy_label 正面路徑(須排在上面零羈絆基線斷言之後,以免污染):在隊者有羈絆 → 標籤帶其名
    c.companion_bond["sellsword"] = party.BOND_TIERS[0]
    lbl = party.legacy_label(c, gd)
    assert lbl and gd.companions["sellsword"]["name"] in lbl


def test_display_safe_on_unknown_companion_id():
    """對抗審查回歸:companions.json 移除某同伴後的舊存檔,列表/面板不 KeyError。"""
    import tesrpg.main as main
    gd, c, st = _setup()
    c.companions.append("ghost_removed_id")
    assert party.max_hp(c, gd, "ghost_removed_id") == 0        # party.* 防禦不崩
    assert party.is_downed(c, gd, "ghost_removed_id")          # 視為負傷 benched
    lbl = main._party_label(c, gd, "ghost_removed_id")         # 不 KeyError
    assert "ghost_removed_id" in lbl


def test_companion_schema_complete():
    """併入 test_m12.test_all_spawn_refs_valid 的唯一獨有段:同伴模板 schema 完整
    (法術召喚段/地城段已被 test_spell_schema / test_dungeon 更強覆蓋,丟棄)。"""
    gd = get_gamedata()
    for comp in gd.companions.values():
        assert {"name", "cost", "strength", "max_health", "attack"} <= set(comp)


def run():
    test_persistent_hp_spawn_and_record()
    test_downed_benched_then_heal_restores_fieldable()
    test_bond_grows_on_victory_and_boosts_hp()
    test_heal_full_and_forget()
    test_siege_casualty_forgets_persistent_state()
    test_save_roundtrip_and_old_save_defaults()
    test_defensive_clamps_and_no_stale_legacy()
    test_display_safe_on_unknown_companion_id()
    test_companion_schema_complete()


if __name__ == "__main__":
    run()
    print("test_party OK")
