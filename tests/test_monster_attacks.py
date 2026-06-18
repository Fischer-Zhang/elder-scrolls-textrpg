"""怪物攻擊多樣化(R43):攻擊曲目選招 + on_hit 控場放寬 + 雙軌防禦 + 招式名。

涵蓋:
  - choose_attack:無曲目後備、加權、`when` 血量階段閘、`cooldown` 蓄力冷卻、spawn_boss 縮放曲目。
  - on_hit 控場:stagger/slow/weaken/fear/paralyze 命中套用;硬控去重;willpower 抗硬控;落空不上控(雙軌第一道)。
  - weaken 對稱:被耗弱的玩家攻擊傷害下降(修先前 player-only 漏洞)。
  - 玩家硬控門:麻痺/恐懼 → run_battle 該回合跳過玩家行動。
  - 事件 attack_name;back-compat 怪(無曲目)選招 === 單招(守 sim byte-identical 假設)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Creature
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic
from tesrpg.ui import console as ui


def _gd():
    return get_gamedata()


def _player(willpower=40, **attrs):
    gd = _gd()
    c = build_character(gd, name="P", sex="male", race="redguard",
                        birthsign="warrior", class_id="warrior")
    c.attributes["willpower"] = willpower
    for k, v in attrs.items():
        c.attributes[k] = v
    return c


def _foe(attack, attacks=None, hp=40, danger=3):
    """直接造一隻測試用怪(避免依賴 bestiary 數值)。"""
    return Creature(template_id="dummy", name="測試怪", strength=50, agility=40, speed=40,
                    max_health=hp, health=hp, armor_rating=0, attack=attack,
                    attacks=attacks or [], danger=danger)


# ----------------------------------------------------------------------
# choose_attack 選招
# ----------------------------------------------------------------------
def test_choose_attack_fallback_when_no_repertoire():
    gd = _gd()
    # 仍維持單招的低危 trash(d1-d2;R43 之後 d3-d6 boss-tier 已陸續配曲目)→ 後備路徑回單招本體
    for tid in ["giant_rat", "wolf", "mudcrab", "frostbite_spider"]:
        cr = combat.spawn_creature(gd, tid, RNG(1))
        # 無 attacks 曲目 → choose_attack 回單招本體(物件同一)
        assert not cr.attacks, f"{tid} 不應有曲目"
        assert combat.choose_attack(cr, RNG(3)) is cr.attack


def test_choose_attack_weighted_covers_modes_and_hp_gate():
    gd = _gd()
    # bear 曲目:熊掌橫掃 / 血盆撕咬 / 狂暴揮爪(when hp_below 0.5, cooldown)
    cr = combat.spawn_creature(gd, "bear", RNG(1))
    assert cr.attacks, "bear 本輪應有曲目"
    # 滿血:enrage(狂暴揮爪)不應出現(hp_below 0.5 閘)
    full = [combat.choose_attack(cr, RNG(s)).get("name") for s in range(200)]
    assert "狂暴揮爪" not in full
    assert "熊掌橫掃" in full and "血盆撕咬" in full     # 兩個常態模式都選得到
    # 低血:enrage 解鎖(用乾淨 creature,避免 cooldown 標記污染)
    low = combat.spawn_creature(gd, "bear", RNG(1))
    low.health = low.max_health * 0.3
    names = set()
    for s in range(200):
        low.active_effects.clear()                       # 清掉上一輪可能加的 cooldown 標記
        names.add(combat.choose_attack(low, RNG(s)).get("name"))
    assert "狂暴揮爪" in names


def test_choose_attack_cooldown_blocks_reselection_until_tick():
    cd_atk = {"name": "蓄力", "damage": 20, "skill": 60, "cooldown": 3}
    normal = {"name": "普攻", "damage": 8, "skill": 50, "weight": 0.0001}   # 幾乎不被選 → 逼出蓄力
    cr = _foe(cd_atk, attacks=[cd_atk, normal])
    # 第一次:幾乎必選蓄力(普攻權重趨0)→ 留下冷卻標記
    chosen = combat.choose_attack(cr, RNG(2))
    assert chosen["name"] == "蓄力"
    assert combat._attack_on_cooldown(cr, "蓄力")
    # 冷卻中:即便蓄力權重壓倒,也只能退回普攻
    assert combat.choose_attack(cr, RNG(2))["name"] == "普攻"
    # tick 三回合 → 標記消退 → 蓄力再度可選
    for _ in range(3):
        magic.tick_effects(cr, None)
    assert not combat._attack_on_cooldown(cr, "蓄力")
    assert combat.choose_attack(cr, RNG(2))["name"] == "蓄力"


def test_spawn_boss_scales_whole_repertoire():
    gd = _gd()
    base = gd.bestiary["frost_giant"]
    boss = combat.spawn_boss(gd, "frost_giant", RNG(1))
    assert boss.attacks, "frost_giant 應有曲目"
    # 每條曲目傷害 ×1.3、命中 +15(夾 100)→ 對齊單招強化
    for a, src in zip(boss.attacks, base["attacks"]):
        assert a["damage"] == round(src["damage"] * 1.3)
        assert a["skill"] == min(100, src["skill"] + 15)
    # 不污染模板
    assert base["attacks"][0]["damage"] != boss.attacks[0]["damage"]


# ----------------------------------------------------------------------
# on_hit 控場(雙軌防禦)
# ----------------------------------------------------------------------
def _resolve_on_hit(player, attack, seeds=400):
    """重複擲到一記「命中且未格擋」的怪攻;回傳該次 event(每次重置玩家狀態)。"""
    gd = _gd()
    foe = _foe(attack)
    for s in range(seeds):
        player.health = player.max_health
        player.active_effects = []
        ev = combat.resolve_attack(foe, player, gd, RNG(s * 13 + 1), attack=attack)
        if ev["hit"] and not ev["blocked"]:
            return ev
    raise AssertionError("找不到命中樣本(機率設定有誤?)")


def test_soft_cc_applied_on_hit():
    p = _player()
    atk = {"name": "震擊", "damage": 5, "skill": 100,
           "on_hit": {"status": "stagger", "turns": 1, "chance": 1.0}}
    ev = _resolve_on_hit(p, atk)
    assert ev["status_applied"] == "stagger"
    assert magic.is_staggered(p)


def test_slow_and_weaken_applied_with_magnitude():
    p = _player()
    for st, getter in [("slow", lambda c: magic.slow_factor(c) > 0),
                       ("weaken", lambda c: magic.weaken_factor(c) < 1.0)]:
        atk = {"name": st, "damage": 4, "skill": 100,
               "on_hit": {"status": st, "magnitude": 0.3, "turns": 2, "chance": 1.0}}
        ev = _resolve_on_hit(p, atk)
        assert ev["status_applied"] == st
        assert getter(p), f"{st} 未生效"


def test_hard_cc_dedup_no_chain_lock():
    gd = _gd()
    p = _player()
    atk = {"name": "懾心", "damage": 4, "skill": 100,
           "on_hit": {"status": "fear", "turns": 1, "chance": 1.0}}
    foe = _foe(atk)
    # 玩家已帶 fear → 命中時不得再疊第二層(去重防連鎖鎖死)
    for s in range(400):
        p.health = p.max_health
        p.active_effects = [{"kind": "fear", "turns": 3}]      # 既有恐懼
        ev = combat.resolve_attack(foe, p, gd, RNG(s * 13 + 1), attack=atk)
        if ev["hit"] and not ev["blocked"]:
            fears = [e for e in p.active_effects if e["kind"] == "fear" and e["turns"] > 0]
            assert len(fears) == 1, "硬控應去重,不得疊加"
            return
    raise AssertionError("找不到命中樣本")


def test_hard_cc_resisted_by_willpower():
    gd = _gd()
    atk = {"name": "懾心", "damage": 4, "skill": 100,
           "on_hit": {"status": "fear", "turns": 1, "chance": 1.0}}
    foe = _foe(atk)

    def applied_among_hits(willpower, n=500):
        applied = hits = 0
        for s in range(n):
            c = _player(willpower=willpower)
            ev = combat.resolve_attack(foe, c, gd, RNG(s * 7 + 1), attack=atk)
            if ev["hit"] and not ev["blocked"]:
                hits += 1
                if any(e["kind"] == "fear" for e in c.active_effects):
                    applied += 1
        return applied, hits

    low_applied, low_hits = applied_among_hits(40)     # 意志 40(中性)→ 抗性 0 → 命中必中控
    high_applied, high_hits = applied_among_hits(255)  # 高意志 → 抗性高 → 部分擲開
    assert low_applied == low_hits                     # 中性意志:每記命中都中控
    assert high_applied < low_applied                  # 高意志:顯著少於(willpower 是防守槓桿)


def test_miss_applies_no_cc():
    """雙軌第一道:攻擊落空 → 連控帶傷全免(on_hit 在 if hit 內)。"""
    gd = _gd()
    p = _player()
    # 命中率極低:怪技能 1 + 玩家高敏捷 + 舉盾
    atk = {"name": "笨拙揮擊", "damage": 5, "skill": 1,
           "on_hit": {"status": "fear", "turns": 2, "chance": 1.0}}
    foe = _foe(atk)
    misses = 0
    for s in range(120):
        p.health = p.max_health
        p.active_effects = []
        ev = combat.resolve_attack(foe, p, gd, RNG(s * 5 + 2), attack=atk, defender_blocking=True)
        if not ev["hit"]:
            misses += 1
            assert not p.active_effects, "落空不得施加任何控場/狀態"
    assert misses > 0, "測試前提:應有落空樣本"


# ----------------------------------------------------------------------
# weaken 對稱(被耗弱的玩家傷害下降)
# ----------------------------------------------------------------------
def test_weaken_reduces_player_damage_symmetric():
    gd = _gd()
    target_id = "bear"
    # 找一個「玩家命中」的種子,讓兩次比較同 roll
    for s in range(300):
        attacker = _player()
        foe = combat.spawn_creature(gd, target_id, RNG(99))
        ev = combat.resolve_attack(attacker, foe, gd, RNG(s), )
        if ev["hit"] and ev["damage"] > 1:
            seed = s
            break
    else:
        raise AssertionError("找不到玩家命中樣本")
    # 未耗弱
    a1 = _player()
    f1 = combat.spawn_creature(gd, target_id, RNG(99))
    d_normal = combat.resolve_attack(a1, f1, gd, RNG(seed))["damage"]
    # 耗弱 0.5(同種子同 roll)→ 應明顯較低(證明 weaken_factor 現對玩家也生效)
    a2 = _player()
    a2.active_effects = [{"kind": "weaken", "magnitude": 0.5, "turns": 2}]
    f2 = combat.spawn_creature(gd, target_id, RNG(99))
    d_weak = combat.resolve_attack(a2, f2, gd, RNG(seed))["damage"]
    assert d_weak < d_normal


# ----------------------------------------------------------------------
# 事件 attack_name
# ----------------------------------------------------------------------
def test_event_carries_attack_name():
    gd = _gd()
    p = _player()
    foe = _foe({"name": "啃咬", "damage": 3, "skill": 50})
    ev = combat.resolve_attack(foe, p, gd, RNG(1), attack={"name": "凜霜重擊", "damage": 6, "skill": 50})
    assert ev["attack_name"] == "凜霜重擊"
    # 玩家攻擊 → 無招式名(用武器)
    ev2 = combat.resolve_attack(p, foe, gd, RNG(1))
    assert ev2["attack_name"] is None


# ----------------------------------------------------------------------
# 玩家硬控門(整合:run_battle 該回合跳過玩家行動)
# ----------------------------------------------------------------------
def test_player_incapacitation_skips_turn_in_run_battle():
    import tesrpg.main as M
    from tesrpg.state import GameState, GameTime
    gd = _gd()
    player = _player(willpower=40)            # 抗性 0 → 命中必麻痺
    player.max_health = player.health = 60
    # 不可殺的敵人,命中必使玩家麻痺(turns 大 → 一旦上身便長期空過)
    para = {"name": "石化凝視", "damage": 4, "skill": 100,
            "on_hit": {"status": "paralyze", "turns": 99, "chance": 1.0}}
    foe = combat.spawn_creature(gd, "giant_rat", RNG(1))
    foe.max_health = foe.health = 9999
    foe.attack = para
    foe.attacks = [para]

    calls = [0]

    def fake_choose(*a, **k):
        calls[0] += 1
        return {"type": "attack", "target": foe}     # 能行動就攻擊(打不死 9999 血敵 → 靠麻痺空過致死)

    ui_names = ("combat_event", "combat_tick", "message", "show_events", "loot_report")
    saved_ui = {n: getattr(ui, n) for n in ui_names}
    saved_choose = M._choose_combat_action
    try:
        for n in ui_names:
            setattr(ui, n, lambda *a, **k: None)
        M._choose_combat_action = fake_choose
        st = GameState(player=player, time=GameTime(), rng=RNG(5))
        M.run_battle(st, gd, [foe])
    finally:
        for n, fn in saved_ui.items():
            setattr(ui, n, fn)
        M._choose_combat_action = saved_choose

    assert not combat.is_alive(player), "玩家應因長期麻痺空過而被不可殺敵打死"
    # 一旦麻痺上身即永久空過 → 玩家被詢問行動的次數極少(若 gate 失效則每回合都問 ≈ 致死回合數)
    assert 1 <= calls[0] <= 5, f"被麻痺回合不應詢問行動(calls={calls[0]})"


def run():
    test_choose_attack_fallback_when_no_repertoire()
    test_choose_attack_weighted_covers_modes_and_hp_gate()
    test_choose_attack_cooldown_blocks_reselection_until_tick()
    test_spawn_boss_scales_whole_repertoire()
    test_soft_cc_applied_on_hit()
    test_slow_and_weaken_applied_with_magnitude()
    test_hard_cc_dedup_no_chain_lock()
    test_hard_cc_resisted_by_willpower()
    test_miss_applies_no_cc()
    test_weaken_reduces_player_damage_symmetric()
    test_event_carries_attack_name()
    test_player_incapacitation_skips_turn_in_run_battle()


if __name__ == "__main__":
    run()
    print("test_monster_attacks OK")
