"""R86 同伴戰鬥施法:輔助型同伴角色感知支援(治療含玩家·護盾·激勵·冷卻·去重)。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic

_ALLY_KINDS = {"heal", "shield", "apply_status", "empower"}
_SUPPORT = ("hedge_mage", "drelas", "shieldmaiden", "veteran")


def _setup():
    gd = get_gamedata()
    p = build_character(gd, name="hero", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    return gd, p


def _spawn(gd, cid):
    return combat.spawn_companion(gd, cid, RNG(1))


# --- 資料 schema:輔助同伴的 spells 合法 --------------------------------------
def test_support_companions_have_valid_spells():
    gd = get_gamedata()
    for cid in _SUPPORT:
        spells = gd.companions[cid].get("spells")
        assert spells, cid
        for sid in spells:
            sp = gd.spells[sid]
            assert sp["target"] in ("ally", "allies"), (cid, sid)
            assert sp["effect"]["kind"] in _ALLY_KINDS, (cid, sid)
    # 非輔助同伴無 spells 欄(不破)
    assert "spells" not in gd.companions["sellsword"]


# --- 反應式治療:含治療玩家本人 + 門檻 + 冷卻 ---------------------------------
def test_healer_heals_the_player_below_threshold():
    gd, p = _setup()
    healer = _spawn(gd, "hedge_mage")
    p.health = int(p.max_health * 0.30)
    before = p.health
    res = magic.companion_support_act(healer, p, [healer], gd)
    assert res and res["spell"] == "heal_other"
    assert p.health == before + 50              # 固定 power=1.0:援護術 base magnitude 50,無智力加成
    assert magic._co_has_kind(healer, "support_cd")   # 冷卻已設


def test_no_support_when_everyone_healthy():
    gd, p = _setup()
    healer = _spawn(gd, "hedge_mage")
    p.health = p.max_health
    assert magic.companion_support_act(healer, p, [healer], gd) is None   # 全滿血 → 不施放 → 走攻擊


def test_support_on_cooldown_skips():
    gd, p = _setup()
    healer = _spawn(gd, "hedge_mage")
    p.health = int(p.max_health * 0.30)
    assert magic.companion_support_act(healer, p, [healer], gd) is not None
    p.health = int(p.max_health * 0.30)         # 仍受傷,但冷卻中
    assert magic.companion_support_act(healer, p, [healer], gd) is None


# --- 主動式增益:護盾含玩家 / 激勵只給同伴(玩家被 combat 守門) ---------------
def test_shield_protects_player_empower_excludes_player():
    gd, p = _setup()
    sm = _spawn(gd, "shieldmaiden")
    res = magic.companion_support_act(sm, p, [sm], gd)
    assert res and res["spell"] == "ward_ally"
    assert magic._co_has_kind(p, "shield")      # 護盾照顧玩家

    gd2, p2 = _setup()
    vet = _spawn(gd2, "veteran")
    ally = combat.spawn_companion(gd2, "sellsword", RNG(2))
    res2 = magic.companion_support_act(vet, p2, [vet, ally], gd2)
    assert res2 and res2["spell"] == "rally"
    assert magic._co_has_kind(ally, "empower")          # 同伴受激勵
    assert not magic._co_has_kind(p2, "empower")        # 🔴 玩家被 combat not-_is_player 守門 → 排除


# --- 去重:目標已有 buff(模擬 capstone 光環)→ 不重施護盾 --------------------
def test_buff_dedup_skips_if_already_buffed():
    gd, p = _setup()
    sm = _spawn(gd, "shieldmaiden")
    # 模擬 capstone ally_shield 已套在玩家+同伴身上
    for e in (p, sm):
        e.active_effects.append({"kind": "shield", "magnitude": 10, "turns": 1, "source": "capstone:x"})
    assert magic.companion_support_act(sm, p, [sm], gd) is None   # 皆有盾 → 不重施 → 走攻擊


# --- 優先序:反應治療優先於主動增益 ------------------------------------------
def test_heal_prioritized_over_buff():
    gd, p = _setup()
    drelas = _spawn(gd, "drelas")        # spells: regen_aura(治療) + heal_other
    p.health = int(p.max_health * 0.30)
    res = magic.companion_support_act(drelas, p, [drelas], gd)
    assert res and gd.spells[res["spell"]]["effect"]["kind"] in ("heal", "apply_status")   # 治療類,非 buff


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_companion_cast")
