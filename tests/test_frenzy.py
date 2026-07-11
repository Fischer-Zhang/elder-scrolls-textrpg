"""R152 幻術「狂亂」frenzy:心智劫持 → 敵人攻向同類(借刀殺人)。

涵蓋:cast 施加 frenzied(單體/AoE·R17 各敵獨立)、敵方階段重定向攻同類(整合)、
孤身無同類 → 空轉自限不 crash。solo 機率抵抗 + mindless 免疫另見 test_solo_control / test_mindless_control。
"""

import io

from rich.console import Console

import tesrpg.ui.console as ui
import tesrpg.main as main
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic

gd = get_gamedata()


def _caster():
    c = build_character(gd, name="幻", sex="male", race="breton", birthsign="mage", class_id="mage")
    c.skills.update(illusion=70, blade=60)
    c.attributes.update(strength=60)
    c.magicka = c.max_magicka = 300
    c.spells = list(c.spells) + [s for s in ("frenzy", "mass_frenzy") if s not in c.spells]
    return c


def _dummy(tid, hp):
    e = combat.spawn_creature(gd, tid, RNG(1))
    e.max_health = e.health = hp
    return e


# --- cast 施加 ---------------------------------------------------------------
def test_cast_frenzy_applies_frenzied_to_nonsolo_enemy():
    c = _caster()
    foe = _dummy("bandit", 100)          # 非 solo → 必中
    magic.cast(c, gd, "frenzy", RNG(1), target=foe)
    assert magic.is_frenzied(foe)


def test_mass_frenzy_independent_per_enemy():
    """R17:AoE 對每敵各自獨立 frenzied dict(非共用別名)。"""
    c = _caster()
    foes = [_dummy("bandit", 100) for _ in range(3)]
    magic.cast(c, gd, "mass_frenzy", RNG(1), enemies=foes, battle={"allies": []})
    dicts = [next((e for e in f.active_effects if e["kind"] == "frenzied"), None) for f in foes]
    assert all(dicts), "全體應各自狂亂"
    assert len({id(d) for d in dicts}) == 3, "每敵須獨立 dict(R17)"


# --- 敵方階段重定向(整合)---------------------------------------------------
def _menu(title, options, allow_back=False):
    keys = [k for k, _ in options]
    return "attack" if "attack" in keys else keys[0]


def _run(st, enemies):
    saved = (ui.menu, ui.console, ui.message)
    ui.menu = _menu
    ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)
    ui.message = lambda *a, **k: None
    try:
        return main.run_battle(st, gd, enemies)
    finally:
        ui.menu, ui.console, ui.message = saved


def test_frenzied_enemy_attacks_own_side():
    """狂亂敵在敵方階段攻擊同類(非玩家)—— 2 敵時唯一同類 B → 決定性首擊打 B。"""
    c = _caster()
    c.health = c.max_health = 600
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    A = _dummy("bandit", 120); B = _dummy("bandit", 120)
    A.active_effects.append({"kind": "frenzied", "turns": 2})   # 如同玩家對 A 施 frenzy(直接施繞過機率,固定測試)
    assert magic.is_frenzied(A)
    hits = []
    saved = combat.resolve_attack

    def spy(attacker, defender, *a, **k):
        if attacker is A:
            hits.append(defender)
        return saved(attacker, defender, *a, **k)

    combat.resolve_attack = spy
    try:
        _run(st, [A, B])
    finally:
        combat.resolve_attack = saved
    assert hits, "狂亂敵應有出手"
    assert hits[0] is B, "狂亂敵首擊應打同類 B(非玩家)"


def test_cast_frenzy_solo_boss_resists_probabilistically():
    """🔴 cast() 路由守衛:solo boss 經 magic.cast 施 frenzy 仍受 solo 機率減免
    (若 frenzied 掉出 _CONTROL_KINDS 會繞過 apply_control → rate≈1.0 觸發此測)。"""
    import tesrpg.formulas as F
    boss_id = next(t for t, d in gd.bestiary.items() if d.get("solo") and not d.get("mindless"))
    applied, n = 0, 400
    for s in range(n):
        c = _caster()
        boss = combat.spawn_creature(gd, boss_id, RNG(s))
        magic.cast(c, gd, "frenzy", RNG(s), target=boss)
        if magic.is_frenzied(boss):
            applied += 1
    rate = applied / n
    assert rate < 0.6, rate                                    # 有明顯抵抗·非 1.0(繞過機率減免會失敗)
    assert rate > (1 - F.SOLO_CONTROL_RESIST_CHANCE) - 0.12, rate


def test_cast_frenzy_mindless_immune_no_false_message():
    """🔴 cast() 路由守衛 + 訊息:對無心智者施 frenzy → 不生效、不印假成功(Fix)。"""
    c = _caster()
    skel = combat.spawn_creature(gd, "skeleton", RNG(1))
    ev = magic.cast(c, gd, "frenzy", RNG(1), target=skel)
    assert not magic.is_frenzied(skel)
    assert "陷入狂亂" not in ev["message"], ev["message"]        # 不印假成功
    assert "抵抗" in ev["message"], ev["message"]


def test_frenzied_caster_fully_hijacked_attacks_kin():
    """🔴 Fix(完全劫持):狂亂的祭司/法系怪**完全**被劫持 → 不先治療/召喚,直接攻擊同類
    (frenzy 置於 support/summon 之前)。守衛:狂亂者**永不被詢問支援**(否則會先治療再被劫持)。"""
    c = _caster()
    c.health = c.max_health = 600
    st = GameState(player=c, rng=RNG(7), time=GameTime())
    witch = combat.spawn_creature(gd, "moor_witch", RNG(1)); witch.max_health = witch.health = 200
    ally = combat.spawn_creature(gd, "moor_witch", RNG(2)); ally.max_health = 200; ally.health = 60   # 傷→非狂亂會觸發治療
    witch.active_effects.append({"kind": "frenzied", "turns": 2})
    hits, asked_while_frenzied = [], []
    saved_ra, saved_sup = combat.resolve_attack, magic.enemy_support_act

    def ra_spy(attacker, defender, *a, **k):
        if attacker is witch:
            hits.append(defender)
        return saved_ra(attacker, defender, *a, **k)

    def sup_spy(caster, *a, **k):
        if caster is witch and magic.is_frenzied(witch):   # 狂亂**期間**被問支援 → 未完全劫持(bug)
            asked_while_frenzied.append(caster)
        return saved_sup(caster, *a, **k)

    combat.resolve_attack = ra_spy
    magic.enemy_support_act = sup_spy
    try:
        _run(st, [witch, ally])
    finally:
        combat.resolve_attack, magic.enemy_support_act = saved_ra, saved_sup
    assert not asked_while_frenzied, "狂亂中的祭司不應被詢問支援(frenzy 須在 support 之前短路,完全劫持)"
    assert hits and hits[0] is ally, "狂亂祭司應直接攻擊同類"


def test_frenzied_solo_no_ally_skips_no_crash():
    """孤身敵被狂亂 + 無同類 → 空轉跳過(不 crash、狂亂期間零出手);守 rng.choice([]) IndexError。"""
    c = _caster()
    c.health = c.max_health = 800
    st = GameState(player=c, rng=RNG(2), time=GameTime())
    lone = _dummy("bandit", 100)
    lone.active_effects.append({"kind": "frenzied", "turns": 2})
    assert magic.is_frenzied(lone)
    frenzied_hits = []
    saved = combat.resolve_attack

    def spy(attacker, defender, *a, **k):
        if attacker is lone and magic.is_frenzied(lone):
            frenzied_hits.append(defender)
        return saved(attacker, defender, *a, **k)

    combat.resolve_attack = spy
    try:
        _run(st, [lone])   # 只有一敵·無同類 → 狂亂期間空轉
    finally:
        combat.resolve_attack = saved
    assert frenzied_hits == [], "孤身狂亂應空轉,不應出手"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_frenzy OK")
