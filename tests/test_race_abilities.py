"""R61 種族深化:戰系主動威能(與星座不相交的第二威能槽)+ 其餘種族被動天賦。

混合身份:獸人/紅衛/木精靈/帝國/諾德/暗精靈 = 每日一次主動威能;
虎人/亞龍/高精靈/布萊頓 = 持續被動(即時讀,零存檔欄)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, powers, race_ability, smithing


def _mk(race, sign="warrior", cls="warrior"):
    gd = get_gamedata()
    return gd, build_character(gd, name="x", sex="m", race=race, birthsign=sign, class_id=cls)


def _st(c):
    return GameState(player=c, time=GameTime())


# --- 第二威能槽:派發 + 與星座槽不相交 -------------------------------------
def test_racial_power_id_per_race():
    gd = get_gamedata()
    expect = {"orsimer": "orc_berserk", "redguard": "adrenaline_rush",
              "bosmer": "command_beast", "imperial": "imperial_voice",
              "nord": "battle_cry", "dunmer": "ancestor_guardian",
              "khajiit": None, "argonian": None, "altmer": None, "breton": None}
    for race, pid in expect.items():
        c = build_character(gd, name="x", sex="m", race=race, birthsign="warrior", class_id="warrior")
        assert powers.racial_power_id(c, gd) == pid, race


def test_dual_slots_disjoint():
    # 星座威能槽(戀人座麻痺)+ 種族威能槽(狂暴)各自獨立,互不遮蔽
    gd, c = _mk("orsimer", "lover")
    assert powers.power_id(c, gd) == "paralyze_touch"
    assert powers.racial_power_id(c, gd) == "orc_berserk"


def test_beast_form_closes_racial_slot():
    gd, c = _mk("orsimer", "warrior")
    c.is_werewolf = True
    c.beast_form = True
    assert powers.racial_power_id(c, gd) is None


def test_vampire_override_leaves_racial_slot():
    # 吸血鬼 override 只蓋星座槽,種族槽不受影響(正典:詛咒不奪種族能力)
    gd, c = _mk("orsimer", "lover")
    c.is_vampire = True
    assert powers.power_id(c, gd) == "vampiric_drain"
    assert powers.racial_power_id(c, gd) == "orc_berserk"


# --- 每日冷卻(複用 power_last_day,key 不撞)----------------------------
def test_racial_daily_cooldown():
    gd, c = _mk("nord")
    st = _st(c)
    assert powers.racial_available(c, st, gd, "combat")
    powers.racial_use(c, st, gd, enemies=[])
    assert not powers.racial_available(c, st, gd, "combat")
    st.time.advance(24)
    assert powers.racial_available(c, st, gd, "combat")


def test_racial_context_gate():
    gd, c = _mk("nord")
    st = _st(c)
    assert powers.racial_available(c, st, gd, "combat")
    assert not powers.racial_available(c, st, gd, "utility")   # 戰吼只 combat


# --- 自身增傷:獸人狂暴 / 紅衛腎上腺 -------------------------------------
def test_orc_berserk_buff_and_heal():
    gd, c = _mk("orsimer")
    st = _st(c)
    c.max_health = 200
    c.health = 100
    powers.racial_use(c, st, gd)
    bb = [e for e in c.active_effects if e["kind"] == "berserk_buff"]
    assert bb and bb[0]["magnitude"] == 0.20 and bb[0]["turns"] == 3
    assert c.health == 140
    assert combat._self_empower(c) == 0.20


def test_adrenaline_restores_fatigue():
    gd, c = _mk("redguard")
    st = _st(c)
    c.fatigue = 0
    powers.racial_use(c, st, gd)
    assert c.fatigue == c.max_fatigue
    assert combat._self_empower(c) == 0.15


def test_self_empower_zero_without_buff():
    # 無 buff → 0:這是 sim(虎人/無狂暴)byte-identical 的基石
    gd, c = _mk("redguard")
    assert combat._self_empower(c) == 0.0


def test_berserk_raises_damage():
    # 同種子、同新生敵下,有 berserk_buff 的傷害嚴格大於無(增傷確實流入)
    gd, c = _mk("orsimer")
    c.skills["hand_to_hand"] = 90
    c.fatigue = c.max_fatigue
    diffs = []
    for seed in range(20):
        foe = combat.spawn_creature(gd, "bandit", RNG(seed))
        base = combat.resolve_attack(c, foe, gd, RNG(100 + seed))["damage"]
        c.active_effects.append({"kind": "berserk_buff", "magnitude": 0.20, "turns": 3})
        foe2 = combat.spawn_creature(gd, "bandit", RNG(seed))
        buffed = combat.resolve_attack(c, foe2, gd, RNG(100 + seed))["damage"]
        c.active_effects.clear()
        if base > 0:
            diffs.append(buffed - base)
    assert diffs and all(d > 0 for d in diffs)


# --- 控場:類別閘 + 走 magic.apply_control -------------------------------
def test_command_beast_only_beasts():
    gd, c = _mk("bosmer")
    st = _st(c)
    wolf = combat.spawn_creature(gd, "wolf", RNG(0))      # 非 sentient = 野獸
    bandit = combat.spawn_creature(gd, "bandit", RNG(0))  # sentient = 人形
    assert powers._control_class_ok(wolf, gd, "beast")
    assert not powers._control_class_ok(bandit, gd, "beast")
    powers.racial_use(c, st, gd, target=wolf, enemies=[wolf])
    assert any(e["kind"] == "fear" and e["turns"] > 0 for e in wolf.active_effects)


def test_imperial_voice_only_humanoids():
    gd, c = _mk("imperial")
    st = _st(c)
    bandit = combat.spawn_creature(gd, "bandit", RNG(0))
    wolf = combat.spawn_creature(gd, "wolf", RNG(0))
    assert powers._control_class_ok(bandit, gd, "humanoid")
    assert not powers._control_class_ok(wolf, gd, "humanoid")
    powers.racial_use(c, st, gd, target=bandit, enemies=[bandit])
    assert any(e["kind"] == "fear" for e in bandit.active_effects)


def test_battle_cry_aoe_all():
    gd, c = _mk("nord")
    st = _st(c)
    foes = [combat.spawn_creature(gd, "bandit", RNG(i)) for i in range(3)]
    powers.racial_use(c, st, gd, enemies=foes)
    assert all(any(e["kind"] == "fear" for e in f.active_effects) for f in foes)


def test_racial_combat_targets_filters_class():
    gd, c = _mk("bosmer")
    wolf = combat.spawn_creature(gd, "wolf", RNG(0))
    bandit = combat.spawn_creature(gd, "bandit", RNG(0))
    tg = powers.racial_combat_targets("command_beast", [wolf, bandit], gd)
    assert wolf in tg and bandit not in tg


def test_control_routes_apply_control_solo_resist():
    # solo 野獸 boss:command_beast 走 apply_control → R44 機率減免,至少抵抗過一次(非必中)
    gd, c = _mk("bosmer")
    resisted = 0
    for seed in range(40):
        boss = combat.spawn_creature(gd, "blood_moon_beast", RNG(seed))
        st = GameState(player=c, time=GameTime())
        powers.racial_use(c, st, gd, target=boss, enemies=[boss])
        if not any(e["kind"] == "fear" for e in boss.active_effects):
            resisted += 1
        c.power_last_day.clear()
    assert resisted > 0


# --- 召喚:暗精靈祖靈守護 -----------------------------------------------
def test_ancestor_guardian_summons_ally():
    gd, c = _mk("dunmer")
    st = _st(c)
    battle = {"allies": []}
    powers.racial_use(c, st, gd, battle=battle)
    assert len(battle["allies"]) == 1
    ally = battle["allies"][0]
    assert ally.template_id == "ancestral_ghost"
    assert ally.summon_turns == 5


# --- 被動天賦讀值 ------------------------------------------------------
def test_passive_helpers_per_race():
    gd = get_gamedata()

    def mk(race, cls="warrior"):
        return build_character(gd, name="x", sex="m", race=race, birthsign="warrior", class_id=cls)
    kh = mk("khajiit")
    assert race_ability.night_eye_bonus(kh, gd) == 0.15
    assert race_ability.claw_bonus(kh, gd) == 4
    assert race_ability.histskin_factor(mk("argonian"), gd) == 0.5
    assert race_ability.magicka_regen_factor(mk("altmer", "mage"), gd) == 1.5
    assert race_ability.dragonskin_chance(mk("breton", "mage"), gd) == 0.25


def test_passive_neutral_for_other_races():
    # 非對應族讀回中性值(sim 虎人讀回魔/吸魔/癒膚皆中性 → byte-identical 基石)
    gd, c = _mk("khajiit")
    assert race_ability.magicka_regen_factor(c, gd) == 1.0
    assert race_ability.dragonskin_chance(c, gd) == 0.0
    assert race_ability.histskin_factor(c, gd) == 0.0
    nord = build_character(gd, name="n", sex="m", race="nord", birthsign="warrior", class_id="warrior")
    assert race_ability.night_eye_bonus(nord, gd) == 0.0
    assert race_ability.claw_bonus(nord, gd) == 0


def test_passive_helpers_safe_on_creature():
    # 怪物(無 .race)讀回中性 → _weapon_profile/吸魔對怪安全
    gd = get_gamedata()
    wolf = combat.spawn_creature(gd, "wolf", RNG(0))
    assert race_ability.claw_bonus(wolf, gd) == 0
    assert race_ability.dragonskin_chance(wolf, gd) == 0.0


# --- 虎人利爪:只進徒手路徑(紅線:不餵偷襲倍率)-----------------------
def test_claws_only_unarmed():
    gd, c = _mk("khajiit")
    c.weapon = "fists"
    dmg_fist, _, skill = combat._weapon_profile(c, gd)
    assert skill == "hand_to_hand"
    assert dmg_fist == gd.item("fists")["damage"] + 4
    c.weapon = "iron_dagger"
    dmg_dagger, _, dskill = combat._weapon_profile(c, gd)
    assert dskill != "hand_to_hand"
    assert dmg_dagger == gd.item("iron_dagger")["damage"] + smithing.weapon_temper_bonus(c, gd)


def test_claws_zero_for_nonkhajiit_unarmed():
    gd, c = _mk("nord")
    c.weapon = "fists"
    dmg, _, _ = combat._weapon_profile(c, gd)
    assert dmg == gd.item("fists")["damage"]


# --- 虎人夜視:確實流入潛近、且只在夜間 --------------------------------
def test_night_eye_flows_into_night_stealth():
    gd, c = _mk("khajiit")
    c.skills["sneak"] = 10                    # 低潛行 → 機率遠離飽和,加成可辨
    foes = [combat.spawn_creature(gd, "bandit", RNG(0))]
    saved = dict(gd.races["khajiit"].get("passive", {}))
    try:
        with_ne = combat.stealth_approach_chance(c, foes, gd, night=True)
        gd.races["khajiit"]["passive"] = {k: v for k, v in saved.items() if k != "night_eye"}
        without_ne = combat.stealth_approach_chance(c, foes, gd, night=True)
        assert with_ne > without_ne
    finally:
        gd.races["khajiit"]["passive"] = saved


def test_night_eye_absent_in_daytime():
    # 白天不入 if night: 區 → 虎人/非虎人白天潛近相同(夜視零作用)
    gd = get_gamedata()
    kh = build_character(gd, name="k", sex="m", race="khajiit", birthsign="warrior", class_id="warrior")
    kh.skills["sneak"] = 10
    saved = dict(gd.races["khajiit"].get("passive", {}))
    foes = [combat.spawn_creature(gd, "bandit", RNG(0))]
    try:
        with_ne = combat.stealth_approach_chance(kh, foes, gd, night=False)
        gd.races["khajiit"]["passive"] = {k: v for k, v in saved.items() if k != "night_eye"}
        without_ne = combat.stealth_approach_chance(kh, foes, gd, night=False)
        assert with_ne == without_ne   # 白天:夜視不套用
    finally:
        gd.races["khajiit"]["passive"] = saved


# --- 防呆 + 創角可見性(R61 審查修正)----------------------------------
def test_racial_use_none_guard():
    # 被動族(無 racial_power)誤呼 racial_use → 安全 no-op,不崩、不燒冷卻
    gd, c = _mk("khajiit")
    st = _st(c)
    res = powers.racial_use(c, st, gd)
    assert res == {"messages": []}
    assert c.power_last_day == {}   # 未燒冷卻


def test_race_chips_show_ability_indicator():
    # 創角種族卡:戰系族顯「種族威能」、被動族顯「天賦」(可發現性,比照星座異能×N)
    from tesrpg import main as M
    gd = get_gamedata()
    active = [chip["text"] for chip in M._race_chips(gd, gd.races["orsimer"])]
    passive = [chip["text"] for chip in M._race_chips(gd, gd.races["khajiit"])]
    plain = [chip["text"] for chip in M._race_chips(gd, gd.races["dunmer"])]
    assert "種族威能" in active
    assert "天賦" in passive
    assert "種族威能" in plain   # dunmer 也是戰系(ancestor_guardian)


def test_altmer_flavor_no_unsupported_magic_weakness():
    # 高精靈 flavor 不得再宣稱「對魔法較敏感」(資料無負魔抗 → 內容事實一致)
    gd = get_gamedata()
    assert "magic" not in gd.races["altmer"].get("resist", {})
    assert "對魔法較敏感" not in gd.races["altmer"]["ability"]


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_race_abilities OK")
