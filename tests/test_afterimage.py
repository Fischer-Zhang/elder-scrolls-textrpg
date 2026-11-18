"""R186 幻影步(輕甲 100·phantom_step)= 殘影蓄勢 + 殘影連襲(取代 R183 後被 EVASION_BONUS_CAP 遮蔽成 0 的 +0.06 平調閃避)。

機制:閃過**任何**敵攻(含元素/遠程;與 R145 閃身反打「限物理近戰」不同)→ 凝一層殘影(至多 3,被命中散一層);
殘影 ≥ 2 層可選「殘影連襲」:耗盡殘影、每層連斬當下最低血敵一記(武器傷 ×0.8),整個動作只耗一次攻擊體力。
🔴 紅線:連襲每斬 sneak_attack=False(永不吃偷襲倍率 → 不碰 SOLO_SNEAK 夾);穿重甲不生效(R141);戰鬥邊界必清層。"""
import io
from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg import formulas
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, inventory, mastery, stats
import tesrpg.main as main

gd = get_gamedata()


def _phantom(choose=True, **skills):
    c = build_character(gd, name="影", sex="male", race="khajiit", birthsign="shadow", class_id="assassin")
    c.skills.update(light_armor=100, blade=60, **skills)
    c.weapon = "steel_dagger"
    if choose:
        mastery.choose(c, gd, "light_armor_100", "phantom_step")
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.health = c.max_health = 10 ** 5          # 不死(只驗殘影機制,不測存活)
    return c


def _set_stacks(c, n):
    c.active_effects[:] = [e for e in c.active_effects if e.get("kind") != "afterimage"]
    if n:
        c.active_effects.append({"kind": "afterimage", "stacks": n, "turns": 99})


def _bandit(i=0, hp=10 ** 6, name=None):
    f = combat.spawn_creature(gd, "bandit", RNG(i))
    f.health = f.max_health = hp
    if name:
        f.name = name
    return f


def _afterimage_effects(c):
    return [e for e in c.active_effects if e.get("kind") == "afterimage"]


# ---------------------------------------------------------------- 資料 / getter
def test_option_is_afterimage_kind_not_evasion():
    c = _phantom()
    spec = mastery.afterimage(c, gd)
    assert spec == {"max_stacks": 3, "min_stacks": 2, "min_foes": 1, "strike_factor": 0.8}
    assert mastery.evasion_bonus(c, gd) == 0.0                 # 不再是平調閃避(舊 +0.06 被 cap 遮蔽成 0)
    assert "afterimage" in mastery._IMPLEMENTED_KINDS
    assert mastery.afterimage(_phantom(choose=False), gd) == {}  # 未選 → 中性空 dict


def test_getter_gated_by_armor_tree():
    """R141 現實邏輯:穿重甲(笨重)就沒有輕靈身法 → 殘影不凝、不可連襲。"""
    c = _phantom()
    assert mastery.afterimage(c, gd)
    inventory.add_item(c, "steel_cuirass", 1)
    inventory.equip_armor(c, gd, "steel_cuirass")
    assert mastery.afterimage(c, gd) == {}
    combat.afterimage_gain(c, gd)                              # no-op
    assert combat.afterimage_stacks(c) == 0 and not _afterimage_effects(c)


# ---------------------------------------------------------------- 凝層 / 散層 / 上限
def _evade_once(c, atk, tries=600):
    """反覆讓敵人以 atk 打 c,直到閃過一次;每次嘗試前清層 → 回傳該次閃避後的殘影層數。"""
    for s in range(tries):
        _set_stacks(c, 0)
        ev = combat.resolve_attack(_bandit(s), c, gd, RNG(900 + s), attack=atk)
        if not ev["hit"]:
            return combat.afterimage_stacks(c)
    raise AssertionError(f"{tries} 次都沒閃過")


def test_gain_on_dodging_any_attack_including_ranged_and_elemental():
    c = _phantom()
    phys = {"name": "揮砍", "damage": 4, "skill": 40}
    fire = {"name": "火球", "damage": 4, "skill": 40, "element": "fire"}
    arrow = {"name": "弩矢", "damage": 4, "skill": 40, "ranged": True}
    for atk in (phys, fire, arrow):                            # 風暴之舞(R145)反擊不了元素/遠程,殘影要能凝
        assert _evade_once(c, atk) == 1, atk["name"]


def test_no_afterimage_without_the_mastery():
    c = _phantom(choose=False)
    assert _evade_once(c, {"name": "揮砍", "damage": 4, "skill": 40}) == 0
    assert not _afterimage_effects(c)


def test_stacks_capped_at_max():
    c = _phantom()
    for _ in range(6):
        combat.afterimage_gain(c, gd)
    assert combat.afterimage_stacks(c) == 3
    assert len(_afterimage_effects(c)) == 1                    # 單一效果記帳,不重複 append


def test_lose_one_layer_per_damaging_hit_then_effect_removed():
    c = _phantom()
    _set_stacks(c, 3)
    hits = 0
    for s in range(3000):
        if hits == 3:
            break
        before = combat.afterimage_stacks(c)
        ev = combat.resolve_attack(_bandit(s), c, gd, RNG(5000 + s),
                                   attack={"name": "重擊", "damage": 20, "skill": 100})
        after = combat.afterimage_stacks(c)
        if ev["hit"] and ev["damage"] > 0:
            hits += 1
            assert after == before - 1, "被命中(受傷)應散一層"
        else:
            assert after == before, "落空/零傷不散層(落空另有凝層邏輯,但 3 層已滿)"
        c.health = c.max_health
    assert hits == 3
    assert combat.afterimage_stacks(c) == 0 and not _afterimage_effects(c)   # 歸零即移除(HUD 不留空殼)


# ---------------------------------------------------------------- 閘 / 連襲
def test_ready_gate_min_stacks_and_foes():
    c = _phantom()
    _set_stacks(c, 1)
    assert not combat.afterimage_ready(c, gd, 3)               # 1 層 < min_stacks 2
    _set_stacks(c, 2)
    assert combat.afterimage_ready(c, gd, 3)
    assert combat.afterimage_ready(c, gd, 1)                   # 資料 min_foes=1:solo 也可(此槓桿由使用者定,見 handoff)
    assert not combat.afterimage_ready(c, gd, 0)               # 場上無敵 → 不可
    assert not combat.afterimage_ready(_phantom(choose=False), gd, 3)


def test_flurry_below_min_stacks_is_noop_and_free():
    c = _phantom()
    _set_stacks(c, 1)
    fat = c.fatigue
    assert list(combat.phantom_flurry(c, [_bandit(1)], gd, RNG(1))) == []
    assert c.fatigue == fat and combat.afterimage_stacks(c) == 1   # 不耗體、不耗層


def test_flurry_focuses_lowest_hp_one_cost_no_sneak_clears_stacks():
    c = _phantom()
    # 單次攻擊體力成本(基準)
    f0 = c.fatigue
    combat.player_attack_cost(c, gd)
    one_cost = f0 - c.fatigue
    assert one_cost > 0
    c.fatigue = f0
    a, b, d = _bandit(1, 5000, "甲"), _bandit(2, 5, "乙"), _bandit(3, 3000, "丙")   # 乙血最低
    _set_stacks(c, 3)
    evs = list(combat.phantom_flurry(c, [a, b, d], gd, RNG(11)))
    assert len(evs) == 3                                       # 每層一斬
    assert evs[0]["defender"] == "乙"                          # 首斬 = 當下最低血
    dead_b = False
    for ev in evs:
        if dead_b:
            assert ev["defender"] != "乙", "殺死即轉下一個(集火最低血者,不砍屍體)"
        dead_b = dead_b or ev["defender_dead"] and ev["defender"] == "乙"
        assert ev["sneak"] is None, "🔴 連襲每斬 sneak_attack=False(永不吃偷襲倍率)"
    assert f0 - c.fatigue == one_cost, "整個連襲只耗一次攻擊體力(不是每斬各耗)"
    assert combat.afterimage_stacks(c) == 0 and not _afterimage_effects(c)   # 耗盡殘影


def test_flurry_strike_factor_and_damage_mult_scale_weapon_damage():
    """走 damage_factor 車道:0.8 係數 + 呼叫端 damage_mult(R137 格擋姿態攻擊稅不可免)。"""
    def total(mult, seed):
        c = _phantom()
        _set_stacks(c, 3)
        f = _bandit(1, 10 ** 6)
        f.armor_rating = 0
        return sum(ev["damage"] for ev in combat.phantom_flurry(c, [f], gd, RNG(seed), damage_mult=mult))
    for seed in range(1, 40):                                  # 同 rng 同命中序列 → 只差傷害係數
        full, half = total(1.0, seed), total(0.5, seed)
        if full > 0:
            assert 0 < half < full
            return
    raise AssertionError("找不到會命中的種子")


def test_flurry_stops_when_all_foes_dead():
    c = _phantom()
    _set_stacks(c, 3)
    f = _bandit(1, 1)                                          # 一擊必死
    f.armor_rating = 0
    evs = []
    for s in range(1, 60):
        _set_stacks(c, 3)
        f.health = 1
        evs = list(combat.phantom_flurry(c, [f], gd, RNG(s)))
        if any(e["defender_dead"] for e in evs):
            break
    assert evs and evs[-1]["defender_dead"] and len(evs) <= 3
    assert not _afterimage_effects(c)


# ---------------------------------------------------------------- 選單 / HUD
def _menu_keys(c, foes):
    st = GameState(player=c, rng=RNG(1), time=GameTime())
    captured = {}
    orig = ui.menu

    def _fake(title, options, *a, **k):
        captured["opts"] = list(options)
        return "flee"
    ui.menu = _fake
    try:
        main._choose_combat_action(st, gd, foes, [])
    finally:
        ui.menu = orig
    return dict(captured["opts"])


def test_menu_offers_flurry_only_when_ready():
    c = _phantom()
    foes = [_bandit(1), _bandit(2)]
    _set_stacks(c, 1)
    assert "phantom_flurry" not in _menu_keys(c, foes)
    _set_stacks(c, 2)
    opts = _menu_keys(c, foes)
    assert "phantom_flurry" in opts and "殘影連襲" in opts["phantom_flurry"] and "2" in opts["phantom_flurry"]
    c.beast_form = True                                        # 獸形無武器連斬 → 不開放
    assert "phantom_flurry" not in _menu_keys(c, foes)
    c.beast_form = False
    assert "phantom_flurry" not in _menu_keys(_phantom(choose=False), foes)
    assert main._COMBAT_BUCKETS["phantom_flurry"] == "攻擊"


def test_hud_tag_shows_stack_count():
    c = _phantom()
    _set_stacks(c, 2)
    assert ui._status_tags(c) == "殘影×2"
    tag = next(t for t in ui._status_tags_list(c) if t["s"].startswith("殘影"))
    assert tag == {"s": "殘影×2", "good": True}
    _set_stacks(c, 0)
    assert "殘影" not in ui._status_tags(c)


# ---------------------------------------------------------------- 戰鬥邊界(不跨戰洩漏)
def _drive(c, script, preserve=False, foe=None):
    """patch _choose_combat_action:script(call_no) → action dict;其餘回 flee。回 (結果, foe)。"""
    st = GameState(player=c, rng=RNG(3), time=GameTime())
    foe = foe if foe is not None else _bandit(7, 9999)
    n = {"i": 0}

    def _act(*a, **k):
        n["i"] += 1
        return script(n["i"]) or {"type": "flee"}
    orig = main._choose_combat_action
    main._choose_combat_action = _act
    try:
        res = main.run_battle(st, gd, [foe], preserve_buffs=preserve)
    finally:
        main._choose_combat_action = orig
    return res, foe


def test_run_battle_flurry_dispatch_hits_and_clears_on_exit():
    c = _phantom()

    def script(i):
        if i == 1:
            _set_stacks(c, 3)
            return {"type": "phantom_flurry"}
    res, foe = _drive(c, script)
    assert foe.health < 9999, "連襲應造成傷害(3 斬至少中 1 次的機率極高;種子固定)"
    assert not _afterimage_effects(c), "戰鬥離場必清殘影(active_effects.clear)"


def test_run_battle_entry_strips_carried_stacks_even_with_preserve_buffs():
    for preserve in (False, True):                             # 地城預施增益路徑只剝 cascade/afterimage,不全清
        c = _phantom()
        _set_stacks(c, 3)
        seen = {}

        def script(i, c=c, seen=seen):
            seen.setdefault("stacks", combat.afterimage_stacks(c))
        _drive(c, script, preserve=preserve)
        assert seen["stacks"] == 0, f"入戰帶入的殘影不得洩進本場(preserve_buffs={preserve})"


def test_flurry_each_strike_uses_strike_factor_exactly():
    """鎖 strike_factor(R186 審查補:原測試只比 damage_mult 1.0 vs 0.5,忽略 0.8 的突變會漏網)。
    連襲 = 先耗一次體力 + 每層 resolve_attack(sneak=False, damage_factor=strike_factor)——逐擊傷害與手動重放逐位元組相同。"""
    def mk():
        c = _phantom()
        _set_stacks(c, 3)
        f = _bandit(1, 10 ** 6)
        f.armor_rating = 0
        return c, f
    sf = mastery.afterimage(_phantom(), gd)["strike_factor"]
    for seed in range(1, 40):
        c1, f1 = mk()
        got = [ev["damage"] for ev in combat.phantom_flurry(c1, [f1], gd, RNG(seed))]
        c2, f2 = mk()
        combat.player_attack_cost(c2, gd)
        rng = RNG(seed)
        want = [combat.resolve_attack(c2, f2, gd, rng, sneak_attack=False, damage_factor=sf)["damage"]
                for _ in range(3)]
        assert got == want, (seed, got, want)
        if sum(got) > 0:
            return
    raise AssertionError("找不到會命中的種子")


def test_run_battle_victory_and_death_exits_clear_afterimage():
    """離場必清(審查補:原只測逃跑出口,刪掉勝利/死亡出口的 active_effects.clear() 會漏網)。
    每次選單前重種 3 層殘影,確保離場當下身上確實有殘影可洩。"""
    c = _phantom()
    foe = _bandit(1, 1)                                        # 1 血:普通攻擊命中即勝(落空則續戰至命中)
    foe.armor_rating = 0

    def hit_script(i):
        _set_stacks(c, 3)
        return {"type": "attack", "target": foe}
    res, _ = _drive(c, hit_script, foe=foe)
    assert res == "victory" and not _afterimage_effects(c), "勝利出口必清殘影"

    c = _phantom()
    c.health = c.max_health = 1                                # 1 血:敵人任一命中即死
    foe = _bandit(2, 10 ** 6)

    def die_script(i):
        _set_stacks(c, 3)
        return {"type": "attack", "target": foe}
    res, _ = _drive(c, die_script, foe=foe)
    assert res == "dead" and not _afterimage_effects(c), "死亡出口必清殘影"


def test_run_battle_flurry_stacks_guard_stance_tax_after_cost():
    """R137 姿態攻擊稅不可被連襲免掉,且(與普攻同序)在**耗體之後**才求值(審查發現:原先在耗體前求值)。"""
    for stance in (True, False):
        c = _phantom()
        seen = {}
        orig = combat.phantom_flurry

        def spy(player, foes, gamedata, rng, damage_mult=1.0):
            seen["callable"] = callable(damage_mult)
            seen["fat_before"] = player.fatigue

            def probe():
                seen["fat_at_eval"] = player.fatigue
                seen["mult"] = damage_mult() if callable(damage_mult) else damage_mult
                return seen["mult"]
            return orig(player, foes, gamedata, rng, damage_mult=probe)

        def script(i):
            if i == 1:
                _set_stacks(c, 3)
                if stance:
                    c.active_effects.append({"kind": "guard_stance", "turns": 99})
                return {"type": "phantom_flurry"}
        combat.phantom_flurry = spy
        try:
            _drive(c, script)
        finally:
            combat.phantom_flurry = orig
        assert seen["callable"] and seen["fat_at_eval"] < seen["fat_before"], "姿態稅須在耗體後求值"
        assert seen["mult"] == (formulas.GUARD_STANCE_DAMAGE_TAX if stance else 1.0), (stance, seen["mult"])


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("OK")
