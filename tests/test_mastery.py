"""技能里程碑(Skill Mastery)單元測試。

涵蓋:門檻判定(只認 base_skill)、6 條 MVP 各自效果、解鎖播報精確性、
存檔向後相容、以及守住反 min-max 紅線(里程碑不寫進 base、不破既有夾限)。
"""

from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import combat, dialogue, dungeon, magic, mastery, progression


def _char(**skills):
    gd = get_gamedata()
    c = build_character(gd, name="M", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    for k, v in skills.items():
        c.skills[k] = v
    return gd, c


# --- 門檻判定 -----------------------------------------------------------
def test_threshold_uses_base_skill_only():
    """里程碑只認 base_skill:裝備/吸血鬼疊加值不得觸發(避免污染成長/夾限)。"""
    gd, c = _char(block=49)
    assert not any(e["id"] == "block_shieldwall" for e in mastery.unlocked(c, gd))
    # 裝備加成把有效技能推到 50,但 base 仍 49 → 不解鎖
    c.equip_skill_bonus["block"] = 5
    assert c.skill("block") >= 50 and c.base_skill("block") == 49
    assert not any(e["id"] == "block_shieldwall" for e in mastery.unlocked(c, gd))
    # base 真的到 50 → 解鎖
    c.skills["block"] = 50
    assert any(e["id"] == "block_shieldwall" for e in mastery.unlocked(c, gd))


def test_creatures_have_no_mastery():
    """怪物無 base_skill → 任何 getter 都回預設(不得因防守方是怪而誤觸)。"""
    gd, _ = _char()
    rat = combat.spawn_creature(gd, "giant_rat", RNG(1))
    assert mastery.incoming_physical_factor(rat, gd) == 1.0
    assert mastery.block_hit_penalty(rat, gd) == formulas.BLOCK_HIT_PENALTY


# --- 盾陣(block 50)----------------------------------------------------
def test_shieldwall_deepens_block_penalty():
    gd, c = _char(block=50)
    assert mastery.block_hit_penalty(c, gd) == 0.25
    # 加深的懲罰確實讓來犯更難命中
    base = formulas.hit_chance(60, 40, 40, 1.0, defender_blocking=True, block_penalty=0.15)
    deep = formulas.hit_chance(60, 40, 40, 1.0, defender_blocking=True, block_penalty=0.25)
    assert deep < base
    gd2, c2 = _char(block=49)
    assert mastery.block_hit_penalty(c2, gd2) == formulas.BLOCK_HIT_PENALTY


# --- 壁壘(heavy_armor 75)---------------------------------------------
def test_bulwark_reduces_physical_and_costs_fatigue():
    gd, c = _char(heavy_armor=75)
    assert mastery.incoming_physical_factor(c, gd) == 0.85
    assert mastery.attack_fatigue_factor(c, gd) > 1.0
    # 物理攻擊實扣血更少(同 seed,唯一變因是壁壘門檻)
    foe = combat.spawn_creature(gd, "giant_rat", RNG(1))
    foe.attack["damage"] = 80
    foe.attack["skill"] = 100

    def dmg(ha, seed):
        c.skills["heavy_armor"] = ha
        c.health = c.max_health
        before = c.health
        combat.resolve_attack(foe, c, gd, RNG(seed))
        return before - c.health

    compared = 0
    for s in range(60):
        lo, hi = dmg(74, s), dmg(75, s)   # 74 無壁壘 / 75 有
        if lo > 0 and hi > 0:
            assert hi <= lo
            if hi < lo:
                compared += 1
    assert compared >= 3, "壁壘應在多數命中下實際降低物理傷害"

    # 攻擊耗體:有壁壘更耗
    def attack_cost(ha):
        c.skills["heavy_armor"] = ha
        c.fatigue = c.max_fatigue
        before = c.fatigue
        combat.player_attack_cost(c, gd)
        return before - c.fatigue
    assert attack_cost(75) > attack_cost(74)


def test_bulwark_does_not_reduce_elemental():
    """壁壘只擋物理:元素攻擊(走元素抗性分支)不受 incoming_physical_factor 影響。"""
    gd, c = _char(heavy_armor=75)
    c.equip_resist = {}
    foe = combat.spawn_creature(gd, "giant_rat", RNG(1))
    foe.attack = {"name": "火咬", "damage": 60, "skill": 100, "element": "fire"}

    def dmg(ha, seed):
        c.skills["heavy_armor"] = ha
        c.health = c.max_health
        before = c.health
        combat.resolve_attack(foe, c, gd, RNG(seed))
        return before - c.health

    same = 0
    for s in range(40):
        lo, hi = dmg(74, s), dmg(75, s)
        if lo > 0 and hi > 0:
            assert hi == lo, f"元素傷害不應被壁壘削減:seed={s} {hi} vs {lo}"
            same += 1
    assert same >= 3


# --- 聖光·溢盾(restoration 75)---------------------------------------
def test_overheal_ward_converts_overflow_and_caps():
    gd, c = _char(restoration=75)
    c.active_effects = []
    c.health = c.max_health             # 血滿 → 治療全溢出
    magic.cast(c, gd, "minor_heal", RNG(1))
    shields = [e for e in c.active_effects if e["kind"] == "shield"]
    assert shields and shields[0]["magnitude"] > 0
    assert shields[0]["magnitude"] <= round(c.max_health * 0.5)   # 夾 cap
    assert shields[0]["turns"] == 4


def test_overheal_ward_aggregate_cap_across_casts():
    """審查破口回歸:反覆施放治療,溢盾『總量』不得疊破 cap_ratio×生命上限。"""
    gd, c = _char(restoration=75)
    c.active_effects = []
    c.health = c.max_health
    c.magicka = c.max_magicka = 999
    cap = round(c.max_health * 0.5)
    for _ in range(12):
        magic.cast(c, gd, "minor_heal", RNG(1))
    assert magic.active_shield(c) <= cap, "溢盾總量不得超過 cap"
    # 一般 shield 法術額度不被溢盾佔用(source 區隔):另疊一個一般護盾應照常生效
    c.active_effects.append({"kind": "shield", "magnitude": 30, "turns": 3})
    assert magic.active_shield(c) <= cap + 30


def test_no_overheal_ward_when_not_full():
    """未溢出(血沒滿且治療不滿)→ 不產生護盾。"""
    gd, c = _char(restoration=75)
    c.active_effects = []
    c.health = 1                        # 大幅缺血 → 治療被血上限吸收,無溢出
    magic.cast(c, gd, "minor_heal", RNG(1))
    assert not [e for e in c.active_effects if e["kind"] == "shield"]


def test_overheal_ward_requires_threshold():
    gd, c = _char(restoration=74)
    c.active_effects = []
    c.health = c.max_health
    magic.cast(c, gd, "minor_heal", RNG(1))
    assert not [e for e in c.active_effects if e["kind"] == "shield"]


# --- 過載(destruction 100)-------------------------------------------
def test_overload_raises_cost_and_power_destruction_only():
    gd, c = _char(destruction=100, restoration=100)
    assert mastery.spell_cost_factor(c, gd, "destruction") == 1.30
    assert mastery.spell_power_bonus(c, gd, "destruction") == 0.20
    # 不影響其他學派
    assert mastery.spell_cost_factor(c, gd, "restoration") == 1.0
    assert mastery.spell_power_bonus(c, gd, "restoration") == 0.0
    # destruction 100 的有效魔耗 > destruction 99(過載抬高)
    c.skills["destruction"] = 100
    cost_100 = magic.effective_cost(c, gd, "flames")
    c.skills["destruction"] = 99
    cost_99 = magic.effective_cost(c, gd, "flames")
    assert cost_100 > cost_99


# --- 撬鎖名家(security 75)-------------------------------------------
def test_lock_floor_only_raises_never_lowers():
    gd, c = _char(security=75)
    assert mastery.lock_floor(c, gd) == 0.30
    # 難鎖:原本被夾到 0.05,里程碑抬到 0.30
    hard = dungeon.effective_pick_lock_chance(c, gd, 100)
    assert abs(hard - 0.30) < 1e-9
    # 簡單鎖:本就高於下限 → 不被壓低
    easy_base = dungeon.pick_lock_chance(c.skill("security"), 0)
    easy_eff = dungeon.effective_pick_lock_chance(c, gd, 0)
    assert easy_eff == max(easy_base, 0.30) == easy_base
    # 未達門檻 → 無下限
    gd2, c2 = _char(security=74)
    assert dungeon.effective_pick_lock_chance(c2, gd2, 100) == dungeon.pick_lock_chance(74, 100)


# --- 辯舌·折服(speechcraft 100)------------------------------------
def test_charm_guarantees_once_per_npc():
    gd, c = _char(speechcraft=100)
    nid = next(iter(gd.npcs))
    r1 = dialogue.persuade(c, gd, nid, RNG(1))
    assert r1["ok"] and r1.get("charmed") and nid in c.persuaded_npcs
    # 第二次同一 NPC:不再保證(走一般機率,無 charmed 旗標)
    r2 = dialogue.persuade(c, gd, nid, RNG(1))
    assert not r2.get("charmed")
    # 未達門檻者不享折服
    gd2, c2 = _char(speechcraft=99)
    assert not dialogue.persuade(c2, gd2, nid, RNG(1)).get("charmed")


# --- 解鎖播報精確性 -----------------------------------------------------
def test_unlock_event_fires_exactly_once_across_multilevel():
    """一次灌注跨越門檻(含一次跨多級)時,解鎖事件恰好一次,不漏不重。"""
    gd, c = _char()
    c.skills["security"] = 70
    c.skill_xp["security"] = 0.0
    evs = progression.use_skill(c, gd, "security", 200.0)   # 大量 xp 一次跨過 75
    unlocks = [e for e in evs if e["type"] == "mastery_unlocked"]
    assert len(unlocks) == 1 and unlocks[0]["name"] == "撬鎖名家"
    assert c.skills["security"] >= 75
    # 已解鎖後再練不重報
    evs2 = progression.use_skill(c, gd, "security", 50.0)
    assert not [e for e in evs2 if e["type"] == "mastery_unlocked"]


# --- 存檔向後相容 -------------------------------------------------------
def test_persuaded_npcs_roundtrip_and_backward_compat():
    gd, c = _char(speechcraft=100)
    c.persuaded_npcs = ["alpha", "beta"]
    d = c.to_dict()
    assert d["persuaded_npcs"] == ["alpha", "beta"]
    assert Character.from_dict(d).persuaded_npcs == ["alpha", "beta"]
    # 舊存檔缺此欄 → dataclass 預設空 list
    d.pop("persuaded_npcs")
    assert Character.from_dict(d).persuaded_npcs == []


def test_shipped_kinds_all_implemented():
    """fail-fast(以測試代替載入期例外):出貨的 mastery.json 每條 kind 都須已實作,
    否則玩家會看到解鎖/加分卻零效果(審查抓到的沉默 foot-gun)。"""
    gd = get_gamedata()
    for e in gd.mastery:
        assert e["kind"] in mastery._IMPLEMENTED_KINDS, f"未實作的 kind:{e['kind']}"


def test_unimplemented_kind_is_inert():
    """打錯/未實作的 kind:不顯示、不計分、不播報(完全 inert,而非半套)。"""
    gd, c = _char(blade=100)
    bogus = {"id": "x", "skill": "blade", "threshold": 50, "name": "幻影", "kind": "not_a_real_kind"}
    gd.mastery.append(bogus)
    try:
        assert all(e["id"] != "x" for e in mastery.unlocked(c, gd))
        assert not mastery.newly_unlocked(c, gd, "blade", 50)
    finally:
        gd.mastery.remove(bogus)


def test_mastery_never_writes_base_skill():
    """里程碑不得寫進 char.skills(否則破壞 learn-by-doing 與夾限)。"""
    gd, c = _char(heavy_armor=75, destruction=100, block=50)
    snapshot = dict(c.skills)
    mastery.unlocked(c, gd)
    mastery.incoming_physical_factor(c, gd)
    mastery.spell_power_bonus(c, gd, "destruction")
    mastery.block_hit_penalty(c, gd)
    assert c.skills == snapshot


def run():
    test_threshold_uses_base_skill_only()
    test_creatures_have_no_mastery()
    test_shieldwall_deepens_block_penalty()
    test_bulwark_reduces_physical_and_costs_fatigue()
    test_bulwark_does_not_reduce_elemental()
    test_overheal_ward_converts_overflow_and_caps()
    test_overheal_ward_aggregate_cap_across_casts()
    test_no_overheal_ward_when_not_full()
    test_overheal_ward_requires_threshold()
    test_overload_raises_cost_and_power_destruction_only()
    test_lock_floor_only_raises_never_lowers()
    test_charm_guarantees_once_per_npc()
    test_unlock_event_fires_exactly_once_across_multilevel()
    test_persuaded_npcs_roundtrip_and_backward_compat()
    test_shipped_kinds_all_implemented()
    test_unimplemented_kind_is_inert()
    test_mastery_never_writes_base_skill()


if __name__ == "__main__":
    run()
    print("test_mastery 全通過")
