"""疾病系統 + 統一治癒(R53)單元測試:染病負層/惡化/DoT、治癒三途(藥水/法術/purify)、
吸血熱/狼人熱潛伏期解除、combat 感染傳遞、疾病免疫、存檔相容、未染病者 byte-identical 不變。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import combat, diseases, inventory, lycanthropy, magic, vampirism


def _state(seed=1, hour=12):
    gd = get_gamedata()
    c = build_character(gd, name="S", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.is_player = True
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


# --- 染病 + 負層 + 不寫 base ------------------------------------------
def test_contract_applies_penalty_layer_not_base():
    gd, c, st = _state()
    s0 = c.attr("strength")
    assert diseases.contract(c, st, gd, "rockjoint")
    assert c.attr("strength") == s0 - 10            # 基礎懲罰 -10
    assert c.base_attr("strength") == s0            # 🔴 不寫 base
    assert diseases.has(c, "rockjoint")
    assert not diseases.contract(c, st, gd, "rockjoint")   # 去重:不重複染


def test_endurance_disease_lowers_max_resources():
    gd, c, st = _state()
    mf0 = c.max_fatigue
    diseases.contract(c, st, gd, "bone_break_fever")        # endurance -10 → 衍生資源下修
    assert c.max_fatigue < mf0


def test_unknown_disease_id_ignored():
    gd, c, st = _state()
    assert not diseases.contract(c, st, gd, "no_such_plague")
    assert not diseases.has_any(c)


# --- 惡化 + cap ---------------------------------------------------------
def test_worsen_deepens_to_cap():
    gd, c, st = _state()
    s0 = c.attr("strength")
    diseases.contract(c, st, gd, "rockjoint")               # -10·worsen -4/2日·cap 3
    st.time.advance(2 * 24); diseases.update(st, gd)
    assert c.attr("strength") == s0 - 14                    # step 1
    st.time.advance(20 * 24); diseases.update(st, gd)       # 遠超 cap
    assert c.attr("strength") == s0 - 10 - 4 * 3            # 夾 max_steps=3 → -22


# --- DoT + clamp≥1(不致死)---------------------------------------------
def test_dot_drains_but_never_lethal():
    gd, c, st = _state()
    diseases.contract(c, st, gd, "swamp_rot")               # dot 2/6h
    c.health = c.max_health
    h0 = c.health
    st.time.advance(24); evs = diseases.update(st, gd)      # 4 跳 → 扣 8
    assert c.health < h0 and any(e["kind"] == "dot" for e in evs)
    c.health = 1                                            # 瀕死 → DoT 不可致死
    st.time.advance(24); diseases.update(st, gd)
    assert c.health >= 1


# --- 治癒(purify / 藥水 / 法術)---------------------------------------
def test_purify_clears_diseases_and_layer():
    gd, c, st = _state()
    s0 = c.attr("strength")
    diseases.contract(c, st, gd, "rockjoint")
    diseases.contract(c, st, gd, "witbane")
    res = diseases.purify(c, gd)
    assert res["diseases"] == 2 and not diseases.has_any(c)
    assert c.attr("strength") == s0 and c.disease_attr_penalty == {}


def test_cure_potion_route():
    gd, c, st = _state()
    diseases.contract(c, st, gd, "rockjoint")
    inventory.add_item(c, "cure_disease_potion", 1)
    msg = inventory.use_item(c, gd, "cure_disease_potion", st)
    assert msg and not diseases.has_any(c)
    assert inventory.count_item(c, "cure_disease_potion") == 0   # 藥水消耗


def test_cure_spell_route():
    gd, c, st = _state()
    diseases.contract(c, st, gd, "ataxia")
    c.spells = ["cure_disease"]; c.magicka = c.max_magicka
    magic.cast(c, gd, "cure_disease", RNG(2))
    assert not diseases.has_any(c)


# --- 吸血熱/狼人熱潛伏期解除(治癒含此)-------------------------------
def test_cure_infection_clears_incubation_not_transformed():
    gd, c, st = _state()
    assert vampirism.infect(c, st) and vampirism.is_infected(c)
    res = diseases.purify(c, gd)                            # 統一治癒解潛伏
    assert res["vamp_incub"] and not vampirism.is_infected(c) and not c.is_vampire   # 避免轉化
    # 已轉化的吸血鬼 → 治癒不解(仍須深度解咒任務)
    gd2, c2, st2 = _state()
    c2.is_vampire = True; c2.vampire_fed_day = st2.time.absolute_hours() // 24
    vampirism.apply_to_character(c2, st2, gd2)
    assert diseases.purify(c2, gd2)["vamp_incub"] is False and c2.is_vampire


def test_werewolf_incubation_cured():
    gd, c, st = _state()
    assert lycanthropy.infect(c, st) and lycanthropy.is_infected(c)
    assert diseases.purify(c, gd)["were_incub"] and not lycanthropy.is_infected(c) and not lycanthropy.is_werewolf(c)


# --- combat 感染傳遞 + 免疫 -------------------------------------------
def test_combat_contraction_plumbing():
    gd, c, st = _state()
    # giant_rat 帶 disease on-hit;多打幾下,某次命中應傳回 disease_id
    got = False
    for i in range(60):
        rat = combat.spawn_creature(gd, "giant_rat", RNG(i))
        ev = combat.resolve_attack(rat, c, gd, RNG(100 + i))
        if ev.get("infected") and ev.get("infect_kind") == "disease":
            assert ev.get("disease_id") == "rockjoint"
            got = True
            break
    assert got, "giant_rat 應能傳染 rockjoint"
    # sim 樣本怪(bandit)無 disease 欄 → 永不傳病
    bandit = gd.bestiary["bandit"]
    assert "disease" not in bandit.get("attack", {})


def test_vampire_werewolf_disease_immune():
    gd, c, st = _state()
    from tesrpg import formulas
    base = formulas.resist_multiplier(magic.entity_resist(c, gd), "disease")
    assert base > 0                                         # 凡人會染
    c.is_vampire = True; c.vampire_fed_day = st.time.absolute_hours() // 24
    vampirism.apply_to_character(c, st, gd)
    assert formulas.resist_multiplier(magic.entity_resist(c, gd), "disease") == 0   # 吸血鬼 disease:100 → 免疫


# --- 存檔 + 未染病 byte-identical ------------------------------------
def test_save_roundtrip_with_disease():
    gd, c, st = _state()
    diseases.contract(c, st, gd, "rockjoint")
    d = c.to_dict()
    c2 = type(c).from_dict(d)
    diseases.ensure_disease_fields(c2, st.time, gd)         # 載入鉤重算負層
    assert diseases.has(c2, "rockjoint") and c2.attr("strength") == c.attr("strength")


def test_clean_char_unaffected():
    gd, c, st = _state()
    assert c.disease_attr_penalty == {} and c.disease_skill_penalty == {}
    s0 = c.attr("strength")                                 # 未染病 → 負層 +0,屬性不變(sim byte-identical 之本)
    assert c.attr("strength") == s0


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
