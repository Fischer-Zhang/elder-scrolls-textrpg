"""R212 單槽:法術施放的持續回復(生機 renewal / 生機共鳴 regen_aura)重施取代舊的(不疊);他源 regen 不受影響。

緣起(R211 後的同類稽核):玩家路徑的 apply_status 對 regen 直接追加、無去重;地城內施法是「自由行動(不耗回合)」且預施增益
會帶進戰鬥 → 預施連放 N 道並存。實測:聖騎夾具(魔力 80)4 層 = 每回合 68 點(生命上限 26%,已大於 solo 王任一單次攻擊),
法師夾具(魔力 460)27 層 = 每回合 528 點(生命上限 377%)。專案其他處皆明確不疊(同伴 / 敵方 / 召喚物支援 AI「無人持有才施」、
武器再生附魔 ench_regen 與堅毅 steadfast 以 source 去重、聖化領域刷新非疊加)——玩家生機是唯一漏網。

守衛:
  1. 生機連放 → 恆一道;預施 20 次的回合回復量 == 施 1 次(行為斷言,不依賴常數 → 修前 HEAD 會真的失敗)
  2. 他源 regen(附魔再生 / 堅毅 / 宗師光環)不被誤刪;護盾等其他效果不動
  3. 盟友側(生機共鳴)同理
"""
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import combat, magic


def _healer():
    gd = get_gamedata()
    c = build_character(gd, name="H", sex="male", race="altmer", birthsign="mage", class_id="healer")
    c.spells = list(dict.fromkeys(list(c.spells) + ["renewal", "regen_aura", "oakflesh"]))
    c.active_effects.clear()
    _fill(c)
    return gd, c


def _fill(c):
    c.magicka = c.max_magicka = 5000        # 不讓資源成為變因:測的是「去重」
    c.fatigue = c.max_fatigue = 5000


def _regens(entity):
    return [e for e in entity.active_effects if e.get("kind") == "regen"]


def _cast_renewal(gd, c, n):
    for i in range(n):
        _fill(c)
        assert magic.cast(c, gd, "renewal", RNG(i), battle={"allies": []})["ok"]


def test_renewal_recast_never_stacks():
    gd, c = _healer()
    _cast_renewal(gd, c, 1)
    single = _regens(c)[0]["magnitude"]
    _cast_renewal(gd, c, 12)
    assert len(_regens(c)) == 1, "連放生機只能留一道"
    assert _regens(c)[0]["magnitude"] == single


def test_precast_regen_heal_per_turn_equals_single_cast():
    """地城預施(自由行動)連放 20 次生機 → 進戰後每回合回復量與只施 1 次相同(R212 前:20 倍)。"""
    healed = []
    for n in (1, 20):
        gd, c = _healer()
        _cast_renewal(gd, c, n)
        c.max_health = 10_000
        c.health = 1
        magic.tick_effects(c, gd)
        healed.append(c.health - 1)
    assert healed[0] > 0 and healed[0] == healed[1], healed


def test_other_source_regen_and_other_effects_untouched():
    gd, c = _healer()
    foreign = [{"kind": "regen", "magnitude": 4, "turns": 3, "source": "ench_regen"},      # 武器再生附魔
               {"kind": "regen", "magnitude": 4, "turns": 3, "source": "steadfast"},       # 堅毅里程碑
               {"kind": "regen", "magnitude": 6, "turns": 2, "source": "capstone:ally_regen"}]   # 宗師光環
    shield = {"kind": "shield", "magnitude": 30, "turns": 4, "source": "spell_shield"}
    c.active_effects.extend(foreign + [shield])
    _cast_renewal(gd, c, 5)
    for f in foreign:
        assert f in c.active_effects, f"他源 regen 被誤刪:{f}"
    assert shield in c.active_effects                                 # 護盾不受影響
    assert len(_regens(c)) == len(foreign) + 1                        # 他源各一 + 法術回復恰一道


def test_ally_regen_aura_single_slot_other_sources_untouched():
    gd, c = _healer()
    ally = combat.spawn_companion(gd, "sellsword", RNG(1))
    foreign = {"kind": "regen", "magnitude": 6, "turns": 3, "source": "capstone:ally_regen"}
    ally.active_effects.append(foreign)
    for i in range(4):
        _fill(c)
        r = magic.cast(c, gd, "regen_aura", RNG(i), battle={"allies": [ally]})
        assert r["ok"], r.get("message")
    assert foreign in ally.active_effects
    assert len(_regens(ally)) == 2, "生機共鳴連放只留一道(加上他源一道)"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_regen_slot_r212 OK")
