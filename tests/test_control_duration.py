"""R181 回合照字面:控場/護盾的 `turns: N` = 持有者的 N 個行動(修「怪物 1 回合硬控對玩家不生效」)。

根因:怪物在「敵人階段」施加控場,同回合末 tick_effects 就 −1,玩家下次行動前才檢查 → t1 的
恐懼/麻痺/踉蹌永遠不生效(116 招)、t2 的衰弱/遲緩/凍麻只剩 1 個玩家回合。
修法(使用者拍板 R3·施加端補償):combat 怪物 on_hit 對**玩家**施加時 turns+1(dot 不補);
敵方施護盾 +1(buff 在持有者的對手回合結束 −1);閃身反打 counter_stagger turns:1→2(原死機制)。

既有整合測試 test_monster_attacks 的 `turns: 99` 讓此缺陷漏網 → 本檔用 turns:1 的**真實回合**驅動。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Creature
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic, mastery
from tesrpg.ui import console as ui


def _gd():
    return get_gamedata()


def _player(hp=10**6):
    gd = _gd()
    c = build_character(gd, name="P", sex="male", race="redguard", birthsign="warrior", class_id="warrior")
    c.attributes["willpower"] = 40            # 意志抗性 0 → 命中必上身
    c.max_health = c.health = hp
    return c


def _foe(attack, hp=10**6):
    return Creature(template_id="dummy", name="測試怪", strength=50, agility=40, speed=40,
                    max_health=hp, health=hp, armor_rating=0, attack=attack, attacks=[attack], danger=3)


def _atk(status, turns, magnitude=0.0, chance=1.0, **extra):
    on_hit = {"status": status, "turns": turns, "chance": chance}
    if magnitude:
        on_hit["magnitude"] = magnitude
    on_hit.update(extra)
    return {"name": "測試招", "damage": 4, "skill": 100, "on_hit": on_hit}


def _land(attacker, defender, atk, kind, tries=300):
    """反覆讓 attacker 打 defender 直到 kind 效果上身(命中才判 on_hit)。回該 effect dict。"""
    gd = _gd()
    for s in range(tries):
        defender.active_effects[:] = []
        combat.resolve_attack(attacker, defender, gd, RNG(1000 + s), attack=atk)
        eff = next((e for e in defender.active_effects if e["kind"] == kind), None)
        if eff is not None:
            return eff
    raise AssertionError(f"{tries} 次攻擊都沒讓 {kind} 上身")


def _windows(player, active) -> int:
    """模擬回合末 tick 後玩家的下一次行動:效果仍在 = 一個被影響的玩家行動。回傳被影響的行動數。"""
    n = 0
    for _ in range(8):
        magic.tick_effects(player, _gd())
        if active(player):
            n += 1
    return n


# ----------------------------------------------------------------------
# 怪物 → 玩家:turns N = 玩家的 N 個行動
# ----------------------------------------------------------------------
def test_t1_hard_control_now_costs_exactly_one_player_action():
    for kind, pred in (("fear", magic.is_feared), ("paralyze", magic.is_paralyzed)):
        p = _player()
        _land(_foe(_atk(kind, 1)), p, _atk(kind, 1), kind)
        assert _windows(p, pred) == 1, f"{kind} t1 應損失恰好 1 個玩家行動"


def test_t1_stagger_now_penalizes_exactly_one_player_action():
    p = _player()
    _land(_foe(_atk("stagger", 1)), p, _atk("stagger", 1), "stagger")
    assert _windows(p, magic.is_staggered) == 1


def test_t2_soft_controls_last_two_player_actions():
    """使用者拍板:所有技能影響照字面回合 → t2 衰弱/遲緩/凍麻 = 2 個玩家行動(原只 1 個)。"""
    for kind, mag, pred in (("weaken", 0.25, lambda c: magic.weaken_factor(c) < 1.0),
                            ("slow", 0.3, magic.is_slowed),
                            ("benumb", 0.25, lambda c: magic.benumb_hit_penalty(c) > 0)):
        p = _player()
        _land(_foe(_atk(kind, 2, mag)), p, _atk(kind, 2, mag), kind)
        assert _windows(p, pred) == 2, f"{kind} t2 應影響恰好 2 個玩家行動"


def test_dot_is_not_extended():
    """dot 逐回合結算(同回合末即首跳)→ 照字面 N 跳,不補 +1。"""
    p = _player()
    eff = _land(_foe(_atk("dot", 2, 3, element="poison")), p, _atk("dot", 2, 3, element="poison"), "dot")
    assert eff["turns"] == 2


def test_hard_control_dedupe_caps_consecutive_loss_at_one_in_real_run_battle():
    """真實 run_battle:敵人每回合必施恐懼 t1。玩家被鎖的回合之後,效果仍在身上 → 敵人階段再施被去重擋下 →
    下一回合必能行動(**同種**硬控連續損失上限 1)。要求:出現過被鎖(相鄰詢問間隔 2),且從不連鎖(間隔 ≤2)。
    ⚠ 去重只按 kind:fear 在身時另一隻怪施 paralyze 不被擋 → 跨種串連理論上可連損 2 回合(R181 審查發現;
    目前資料只有 1 招 paralyze〔馬林·瓦倫的囚魂〕且他沒有 fear,實務不可達)。本測試只守同種。"""
    import tesrpg.main as M
    from tesrpg.state import GameState, GameTime
    gd = _gd()
    player = _player(hp=200)
    foe = _foe(_atk("fear", 1))
    foe.attack["damage"] = 6

    enemy_attacks = [0]
    asks: list[int] = []
    real_resolve = combat.resolve_attack

    def counting_resolve(attacker, defender, *a, **k):
        if attacker is foe:
            enemy_attacks[0] += 1
        return real_resolve(attacker, defender, *a, **k)

    def fake_choose(*a, **k):
        asks.append(enemy_attacks[0])
        if len(asks) > 60:                       # 安全閥:避免(理論上不會的)長戰卡死
            player.health = 0
        return {"type": "attack", "target": foe}

    ui_names = ("combat_event", "combat_tick", "message", "show_events", "loot_report")
    saved_ui = {n: getattr(ui, n) for n in ui_names}
    saved_choose = M._choose_combat_action
    try:
        for n in ui_names:
            setattr(ui, n, lambda *a, **k: None)
        M._choose_combat_action = fake_choose
        combat.resolve_attack = counting_resolve
        st = GameState(player=player, time=GameTime(), rng=RNG(5))
        M.run_battle(st, gd, [foe])
    finally:
        combat.resolve_attack = real_resolve
        for n, fn in saved_ui.items():
            setattr(ui, n, fn)
        M._choose_combat_action = saved_choose

    diffs = [b - a for a, b in zip(asks, asks[1:])]
    assert len(asks) >= 4, f"戰鬥過短無法驗證(asks={asks})"
    assert 2 in diffs, f"恐懼 t1 應讓玩家損失過回合(asks={asks})— 修前為 0 次(永不生效)"
    assert max(diffs) <= 2, f"硬控不得連鎖鎖定超過 1 回合(去重失效?asks={asks})"


# ----------------------------------------------------------------------
# 召喚物 → 敵人:同伴階段施加,回合末 tick 後本就完整 N 回合 → 不補
# ----------------------------------------------------------------------
def test_summon_to_enemy_control_is_not_extended():
    atk = _atk("stagger", 1)
    summon = _foe(atk)
    summon.summon_turns = 3                      # 召喚物標記(R105:攻敵時也施加自身 on_hit)
    victim = _foe(_atk("stagger", 1))
    eff = _land(summon, victim, atk, "stagger")
    assert eff["turns"] == 1, "召喚物在同伴階段施加,不應 +1(否則多控一回合)"


# ----------------------------------------------------------------------
# 敵方護盾 +1(對手時鐘);再生/號令/玩家側不補
# ----------------------------------------------------------------------
def _caster_with(gd, spell):
    tid = next(k for k, v in gd.bestiary.items() if spell in (v.get("spells") or []))
    return combat.spawn_creature(gd, tid, RNG(7))


def test_enemy_ward_shield_gets_plus_one_turn_but_default_cast_does_not():
    gd = _gd()
    base_turns = gd.spells["ward_ally"]["effect"]["turns"]
    caster = _caster_with(gd, "ward_ally")
    mate = combat.spawn_creature(gd, "wolf", RNG(8))
    res = magic.enemy_support_act(caster, [caster, mate], gd)
    assert res and res["spell"] == "ward_ally", res
    shields = [e for u in (caster, mate) for e in u.active_effects if e["kind"] == "shield"]
    assert len(shields) == 1 and shields[0]["turns"] == base_turns + magic.ENEMY_SHIELD_TURNS_BONUS
    # 預設路徑(同伴/玩家側):不補
    ally = combat.spawn_creature(gd, "wolf", RNG(9))
    magic._support_cast(caster, "ward_ally", [ally], gd)
    assert next(e for e in ally.active_effects if e["kind"] == "shield")["turns"] == base_turns


def test_enemy_regen_is_not_extended():
    """再生回復次數本來就是 N 次,換對手時鐘不變 → 不補(補了會多一次回復)。"""
    gd = _gd()
    caster = _caster_with(gd, "regen_aura")
    mate = combat.spawn_creature(gd, "wolf", RNG(8))
    mate.health = max(1, int(mate.max_health * 0.3))          # 觸發反應式治療路徑(regen 優先)
    res = magic.enemy_support_act(caster, [caster, mate], gd)
    assert res and res["spell"] == "regen_aura", res
    regen = next(e for e in mate.active_effects if e["kind"] == "regen")
    assert regen["turns"] == gd.spells["regen_aura"]["effect"]["status"]["turns"]


# ----------------------------------------------------------------------
# 閃身反打 counter_stagger:turns:1 是死機制(施加 388 次、怪物下一擊讀到 0 次)→ turns:2
# ----------------------------------------------------------------------
def test_counter_stagger_actually_staggers_the_next_enemy_attack():
    gd = _gd()
    p = _player()
    foe = _foe({"name": "撲擊", "damage": 2, "skill": 100})
    orig_oe, orig_stag, orig_apply = mastery.on_evade, magic.is_staggered, magic.apply_control
    cnt = {"applied": 0, "consumed": 0}

    def apply(target, kind, gd_, rng, **kw):
        r = orig_apply(target, kind, gd_, rng, **kw)
        if kind == "stagger" and target is foe and r == "applied":
            cnt["applied"] += 1
        return r

    def stag(creature):
        r = orig_stag(creature)
        if r and creature is foe:
            cnt["consumed"] += 1                 # 怪物出手判命中時讀到踉蹌
        return r

    try:
        mastery.on_evade = lambda d, g: {"counter_chance": 1.0, "counter_frac": 0.6,
                                         "counter_stagger": True, "restamina": 0}
        magic.is_staggered, magic.apply_control = stag, apply
        rng = RNG(11)
        for _ in range(400):
            p._evade_counter_used = False
            combat.resolve_attack(foe, p, gd, rng, attack=foe.attack)   # 敵人階段:怪物出手 → 玩家閃過 → 反打
            magic.tick_effects(p, gd)
            magic.tick_effects(foe, gd)           # 回合末 tick
            foe.health = foe.max_health
    finally:
        mastery.on_evade, magic.is_staggered, magic.apply_control = orig_oe, orig_stag, orig_apply
    assert cnt["applied"] >= 5, f"測試設定應產生足夠閃避反打(applied={cnt['applied']})"
    assert cnt["consumed"] >= cnt["applied"] - 1, f"反打踉蹌應在怪物下一擊生效(applied/consumed={cnt})"


# ----------------------------------------------------------------------
# R182:盾擊破勢 `weaken_turns: 2` = 怪物的 2 次出手(同族缺陷:在怪物自己階段施加 → 原只剩 1 次)
# ----------------------------------------------------------------------
def test_shield_break_weaken_lasts_literal_monster_attacks_r182():
    gd = _gd()
    p = _player()
    foe = _foe({"name": "撲擊", "damage": 2, "skill": 100})
    orig = mastery.block_riposte
    try:
        mastery.block_riposte = lambda d, g: {"stagger_chance": 1.0, "weaken": 0.15,
                                              "weaken_turns": 2, "counter": 0.0}
        for s in range(300):                       # 怪物須「命中格擋中的玩家」才觸發盾反
            foe.active_effects[:] = []
            combat.resolve_attack(foe, p, gd, RNG(2000 + s), attack=foe.attack, defender_blocking=True)
            if any(e["kind"] == "weaken" for e in foe.active_effects):
                break
        else:
            raise AssertionError("300 次攻擊都沒觸發盾擊破勢")
    finally:
        mastery.block_riposte = orig
    weakened = staggered = 0
    for _ in range(8):                             # 回合末 tick 後,怪物的下一次出手是否仍受影響
        magic.tick_effects(foe, gd)
        weakened += magic.weaken_factor(foe) < 1.0
        staggered += magic.is_staggered(foe)
    assert weakened == 2, f"weaken_turns:2 應衰弱怪物恰好 2 次出手(實得 {weakened};修前為 1)"
    assert staggered == 1, f"盾擊踉蹌本意=下一擊=1 次出手,不得被連帶延長(實得 {staggered})"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("OK")
