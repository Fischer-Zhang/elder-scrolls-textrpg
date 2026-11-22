"""R203a 非亡者召喚物同場名額(SUMMON_FIELD_CAP = 3)+ 召喚物回合結算單一出處(combat.tick_summons)。

背景(2026-11-22 召喚 75 / 100 重新設計的前置,使用者拍板):遊戲規則原本只限制真·亡者(軍團上限),非亡者召喚物(元素 / 魔人 /
魔靈伴 / 治療精靈 / 祖靈…)無同場上限;而 sim_party 的召喚師政策寫死「最多 3 隻」,把「召喚師打達貢 0%」遮成假象
(貪婪 + 地城預召喚下不選 21%、持久召喚 54%)。補名額 = 削弱現行行為(使用者知情拍板)。

🔴 守衛:① tick_summons 對舊內嵌邏輯逐位元組同(隨機構成,含同伴 None / 陣亡 / 逾時);② 第 4 隻被擋、不收費不耗體力、說明原因;
   ③ 不計入名額者:同伴、真·亡者、已逾時、已陣亡;④ 真·亡者另走軍團上限,不受非亡者名額影響;⑤ 種族威能召喚同樣受限且不燒當日冷卻;
   ⑥ 貪婪連施永遠停在名額上限(政策不可繞過規則)。
"""
import copy
import random

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, magic, necromancy, powers, stats

gd = get_gamedata()


def _mage():
    c = build_character(gd, name="召", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills.update(conjuration=100)
    c.attributes.update(intelligence=100, willpower=100)
    c.spells = ["conjure_dremora", "conjure_healer", "conjure_flame_atronach", "conjure_frost_atronach", "raise_thrall"]
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.fatigue = c.max_fatigue
    c.soul_tokens = 40
    return c


def _ally(template="summoned_dremora", turns=5, hp=None, undead=False):
    a = combat.spawn_creature(gd, template, RNG(1))
    a.summon_turns = turns
    if hp is not None:
        a.health = hp
    if undead:
        a._undead = True
    return a


# --- ① tick_summons == 舊內嵌邏輯 ------------------------------------------------
def _old_tick(allies):
    """R203 前 main.py 兩處各寫一份的遞減 + 過濾(原樣重寫,作為逐位元組對照基準)。"""
    for a in allies:
        if a.summon_turns is not None:
            a.summon_turns -= 1
    keep = [a for a in allies if combat.is_alive(a) and (a.summon_turns is None or a.summon_turns > 0)]
    gone = [a for a in allies if not combat.is_alive(a) or (a.summon_turns is not None and a.summon_turns <= 0)]
    return keep, gone


def test_tick_summons_is_byte_identical_to_the_old_inline_logic():
    rnd = random.Random(2026)
    templates = ["summoned_dremora", "summoned_healer", "summoned_flame_atronach"]
    seen_keep = seen_gone = seen_companion = 0
    for _ in range(300):
        pool = []
        for _i in range(rnd.randint(0, 6)):
            kind = rnd.choice(["summon", "summon", "companion", "dead", "expiring"])
            t = rnd.choice([x for x in templates if x in gd.bestiary] or ["summoned_dremora"])
            if kind == "companion":
                pool.append(_ally(t, turns=None))
            elif kind == "dead":
                pool.append(_ally(t, turns=rnd.randint(1, 6), hp=0))
            elif kind == "expiring":
                pool.append(_ally(t, turns=1))
            else:
                pool.append(_ally(t, turns=rnd.randint(1, 6)))
        a, b = copy.deepcopy(pool), copy.deepcopy(pool)
        keep_new, gone_new = combat.tick_summons(a)
        keep_old, gone_old = _old_tick(b)
        assert [(x.template_id, x.summon_turns, x.health) for x in keep_new] == [(x.template_id, x.summon_turns, x.health) for x in keep_old]
        assert [(x.template_id, x.summon_turns, x.health) for x in gone_new] == [(x.template_id, x.summon_turns, x.health) for x in gone_old]
        seen_keep += bool(keep_new)
        seen_gone += bool(gone_new)
        seen_companion += any(x.summon_turns is None for x in keep_new)
    assert seen_keep > 100 and seen_gone > 100 and seen_companion > 50, "隨機構成要同時涵蓋留下 / 離場 / 同伴三類(否則空轉)"


# --- ②③ 名額:第 4 隻被擋、什麼不計入 ------------------------------------------------
def _cast(c, sid, battle, seed=3):
    return magic.cast(c, gd, sid, RNG(seed), battle=battle)


def test_fourth_non_undead_summon_is_refused_without_charge_and_says_why():
    assert formulas.SUMMON_FIELD_CAP == 3
    c = _mage()
    battle = {"allies": [_ally(), _ally("summoned_healer"), _ally("summoned_flame_atronach")]}
    assert magic.nonundead_summon_count(battle) == 3
    mana0, fat0, n0 = c.magicka, c.fatigue, len(battle["allies"])
    res = _cast(c, "conjure_dremora", battle)
    assert res["ok"] is False and f"{formulas.SUMMON_FIELD_CAP} 隻" in res["message"], res
    assert (c.magicka, c.fatigue, len(battle["allies"])) == (mana0, fat0, n0), "被擋 = 不收法力、不耗體力、不多一隻"
    battle["allies"].pop()                                   # 只剩 2 隻 → 第 3 隻可召
    res = _cast(c, "conjure_dremora", battle)
    assert res["ok"] is True and magic.nonundead_summon_count(battle) == 3


def test_cap_ignores_companions_undead_expired_and_dead_but_undead_keeps_its_own_cap():
    c = _mage()
    battle = {"allies": [
        _ally(turns=None),                                   # 同伴(summon_turns None)
        _ally("summoned_dremora", turns=3, undead=True),     # 真·亡者:另受軍團上限
        _ally("summoned_healer", turns=0),                   # 已逾時(待過濾)
        _ally("summoned_flame_atronach", turns=4, hp=0),     # 已陣亡
    ]}
    assert magic.nonundead_summon_count(battle) == 0, "同伴 / 亡者 / 逾時 / 陣亡都不佔非亡者名額"
    for sid in ("conjure_dremora", "conjure_healer", "conjure_flame_atronach"):
        assert _cast(c, sid, battle)["ok"] is True, sid      # 三隻都能召(仍有 2 個空位以外的第 3 隻)
    assert magic.nonundead_summon_count(battle) == 3
    # 非亡者名額已滿時,真·亡者仍可喚起(各走各的上限;token / 軍團上限照舊)
    battle["allies"] = [_ally(), _ally("summoned_healer"), _ally("summoned_flame_atronach")]
    res = magic.cast(c, gd, "raise_thrall", RNG(5), battle=battle)
    assert res["ok"] is True, res
    assert necromancy.undead_count(battle) == 1


# --- ⑤ 種族威能召喚同樣受限,且不燒當日冷卻 -------------------------------------------------
def test_racial_summon_power_obeys_the_cap_and_keeps_the_daily_use():
    c = build_character(gd, name="魂", sex="male", race="dunmer", birthsign="warrior", class_id="warrior")
    st = GameState(player=c, time=GameTime(), rng=RNG(7))
    assert "summon" in powers.RACIAL_POWERS[powers.racial_power_id(c, gd)]["effect"]
    full = {"allies": [_ally(), _ally("summoned_healer"), _ally("summoned_flame_atronach")]}
    cooldown0 = dict(c.power_last_day)
    res = powers.racial_use(c, st, gd, battle=full, enemies=[])
    assert any("上限" in m for m in res["messages"]), res
    assert c.power_last_day == cooldown0, "滿額失敗不燒當日冷卻"
    assert len(full["allies"]) == 3
    room = {"allies": [_ally(), _ally("summoned_healer")]}
    res = powers.racial_use(c, st, gd, battle=room, enemies=[])
    assert len(room["allies"]) == 3 and c.power_last_day != cooldown0, "有空位 → 照常召喚並設冷卻"


# --- ⑥ 貪婪連施永遠停在名額上限 ---------------------------------------------------------
def test_greedy_casting_can_never_exceed_the_cap():
    c = _mage()
    c.max_magicka = c.magicka = 5000                         # 法力管夠:限制只剩規則本身
    battle = {"allies": []}
    sids = ["conjure_dremora", "conjure_healer", "conjure_flame_atronach", "conjure_frost_atronach"]
    ok = refused = 0
    for i in range(40):
        res = _cast(c, sids[i % 4], battle, seed=i)
        ok += bool(res["ok"])
        refused += not res["ok"]
        assert magic.nonundead_summon_count(battle) <= formulas.SUMMON_FIELD_CAP
    assert ok == formulas.SUMMON_FIELD_CAP and refused == 40 - ok, (ok, refused)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_r203_summon_cap")
