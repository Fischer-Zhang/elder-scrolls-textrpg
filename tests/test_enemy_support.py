"""R87 敵方支援施法者:敵陣治療/護盾 AI(對稱 R86)+ 共用 core 一般化 + byte-identical 守恆。"""

from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic

_ALLY_KINDS = {"heal", "shield", "apply_status", "empower"}
# sim_assassin 群戰場景用到的怪 → 必須無 spells(belt-and-suspenders 守 byte-identical;sim 雖走自有
# _round 不呼叫 enemy_support_act,仍堅持 sim-touched 怪不帶 spells)。
_SIM_TOUCHED = {"bandit", "wolf", "skeleton", "vampire_fledgling", "dremora", "frost_troll",
                "dremora_lord", "vampire_lord", "wamasu", "frost_giant", "ancient_dragon",
                "mehrunes_dagon", "mehrunes_dagon_diminished"}


def _spawn(gd, cid, seed=1):
    return combat.spawn_creature(gd, cid, RNG(seed))


def test_caster_creatures_schema_and_sim_safe():
    gd = get_gamedata()
    casters = [k for k, c in gd.bestiary.items() if c.get("spells")]
    assert casters, "應有敵方 caster 怪"
    for k in casters:
        c = gd.bestiary[k]
        assert not c.get("solo"), f"{k} 是 solo boss(無隊友→支援無意義)"
        for sid in c["spells"]:
            sp = gd.spells[sid]
            assert sp["target"] in ("ally", "allies") and sp["effect"]["kind"] in _ALLY_KINDS, (k, sid)
    bad = [s for s in _SIM_TOUCHED if gd.bestiary.get(s, {}).get("spells")]
    assert not bad, f"🔴 sim-touched 怪不該帶 spells:{bad}"


def test_enemy_heals_lowest_other_enemy_scaled():
    gd = get_gamedata()
    witch = _spawn(gd, "moor_witch")               # spells: heal_other
    ally = _spawn(gd, "bandit")
    ally.health = int(ally.max_health * 0.3)
    before = ally.health
    res = magic.enemy_support_act(witch, [witch, ally], gd)
    assert res and res["spell"] == "heal_other"
    assert ally.health - before == round(50 * magic.ENEMY_SUPPORT_POWER)   # 敵方幅度因子(非全量 50)
    assert magic._co_has_kind(witch, "support_cd")                          # 冷卻


def test_enemy_no_support_when_all_healthy():
    gd = get_gamedata()
    witch = _spawn(gd, "moor_witch")
    ally = _spawn(gd, "bandit")                    # 滿血
    assert magic.enemy_support_act(witch, [witch, ally], gd) is None   # → 走攻擊


def test_enemy_support_on_cooldown():
    gd = get_gamedata()
    witch = _spawn(gd, "moor_witch")
    ally = _spawn(gd, "bandit")
    ally.health = int(ally.max_health * 0.3)
    assert magic.enemy_support_act(witch, [witch, ally], gd) is not None
    ally.health = int(ally.max_health * 0.3)
    assert magic.enemy_support_act(witch, [witch, ally], gd) is None       # 冷卻中


def test_non_caster_enemy_returns_none():
    gd = get_gamedata()
    bandit = _spawn(gd, "bandit")
    ally = _spawn(gd, "wolf")
    ally.health = 1
    assert magic.enemy_support_act(bandit, [bandit, ally], gd) is None     # 無 spells → 純近戰


def test_generalized_empower_exclude_set():
    """一般化 core(R86/R87 共用):敵側(無 exclude)empower 套全體;同伴側 exclude 排除指定者(玩家)。"""
    gd = get_gamedata()
    a, b = _spawn(gd, "bandit"), _spawn(gd, "bandit", 2)
    magic._support_act(a, ["rally"], [a, b], gd, exclude_from_empower=())          # 敵側:無排除
    assert magic._co_has_kind(a, "empower") and magic._co_has_kind(b, "empower")
    c, d = _spawn(gd, "wolf", 3), _spawn(gd, "wolf", 4)
    magic._support_act(c, ["rally"], [c, d], gd, exclude_from_empower=(d,))         # 同伴側:排除 d(模擬玩家)
    assert magic._co_has_kind(c, "empower") and not magic._co_has_kind(d, "empower")


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_enemy_support")
