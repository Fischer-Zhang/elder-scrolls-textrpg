"""技能里程碑(Skill Mastery)v2 單元測試 —— 達門檻二選一。

涵蓋:門檻判定(只認 base_skill)、二選一選擇/永久性/pending 衍生、6 條既有效果(選後生效)、
解鎖播報精確性、存檔向後相容(舊存檔達門檻→pending、不自動指派)、白名單惰性、
以及守住反 min-max 紅線(里程碑不寫進 base、不破既有夾限)。
"""

from tesrpg import formulas
from tesrpg import formulas as F
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.systems import combat, crime, dialogue, dungeon, inventory, magic, mastery, progression, stats, world


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
    assert not any(n["id"] == "block_50" for n in mastery.pending_choices(c, gd))
    # 裝備加成把有效技能推到 50,但 base 仍 49 → 不達門檻
    c.equip_skill_bonus["block"] = 5
    assert c.skill("block") >= 50 and c.base_skill("block") == 49
    assert not any(n["id"] == "block_50" for n in mastery.pending_choices(c, gd))
    # base 真的到 50 → 進 pending;選了才解鎖
    c.skills["block"] = 50
    assert any(n["id"] == "block_50" for n in mastery.pending_choices(c, gd))
    mastery.choose(c, gd, "block_50", "shieldwall")
    assert any(e["opt_id"] == "shieldwall" for e in mastery.unlocked(c, gd))


def test_creatures_have_no_mastery():
    """怪物無 base_skill → 任何 getter 都回預設(不得因防守方是怪而誤觸)。"""
    gd, _ = _char()
    rat = combat.spawn_creature(gd, "giant_rat", RNG(1))
    assert mastery.incoming_physical_factor(rat, gd) == 1.0
    assert mastery.block_hit_penalty(rat, gd) == formulas.BLOCK_HIT_PENALTY


# --- 二選一機制(plumbing,以注入節點測試,獨立於出貨內容)-----------------
def test_two_option_choice_plumbing():
    """注入一個兩選項(皆已實作 kind)的節點:pending→未選中性→選後生效→永久不可覆寫。"""
    gd, c = _char(blade=100)
    node = {"id": "blade_test", "skill": "blade", "threshold": 50, "options": [
        {"opt_id": "a", "name": "甲", "kind": "block_deflect", "penalty": 0.30, "desc": ""},
        {"opt_id": "b", "name": "乙", "kind": "lock_floor", "floor": 0.40, "desc": ""}]}
    gd.mastery.append(node)
    try:
        assert any(n["id"] == "blade_test" for n in mastery.pending_choices(c, gd))
        assert mastery.block_hit_penalty(c, gd) == formulas.BLOCK_HIT_PENALTY   # 未選 → 中性
        assert mastery.choose(c, gd, "blade_test", "a") is not None
        assert mastery.block_hit_penalty(c, gd) == 0.30                          # 選 a → 生效
        assert mastery.lock_floor(c, gd) == 0.0                                  # 未選 b → 中性
        assert mastery.choose(c, gd, "blade_test", "b") is None                  # 永久不可覆寫
        assert mastery.block_hit_penalty(c, gd) == 0.30
        assert all(n["id"] != "blade_test" for n in mastery.pending_choices(c, gd))  # 已選 → 不再 pending
        # 併入 reject 輸入驗證(真實 block_50/shieldwall,各自起新 _char 不共用 blade char)
        _, rc = _char(block=40)
        assert mastery.choose(rc, gd, "block_50", "shieldwall") is None  # 未達門檻
        _, rc = _char(block=40)
        rc.skills["block"] = 50
        assert mastery.choose(rc, gd, "block_50", "nonexistent") is None  # 無此 opt
        assert mastery.choose(rc, gd, "no_such_node", "x") is None        # 無此節點
    finally:
        gd.mastery.remove(node)
        c.mastery_choices.pop("blade_test", None)


# --- 盾反(block 50;R39)----------------------------------------------------
def test_block_reflect_returns_damage_and_costs_fatigue():
    """R42 盾反:受物理近戰擊中 → 反彈「攻方完整物理輸出」10%(吃 raw)+ 每次扣 10 體;力竭(< 10 體)則不反、不扣。"""
    gd, c = _char(block=50)
    assert mastery.block_reflect(c, gd) == {}                              # 未選 → 空
    assert mastery.block_hit_penalty(c, gd) == formulas.BLOCK_HIT_PENALTY  # 盾陣已移除 → 格擋基礎懲罰仍預設
    mastery.choose(c, gd, "block_50", "shieldwall")
    assert mastery.block_reflect(c, gd) == {"reflect": 0.10, "fatigue": 10}
    c.health = c.max_health = 9999; c.weapon = "fists"                     # 排除被秒;徒手(不附元素)
    foe = combat.spawn_creature(gd, "bandit", RNG(1)); foe.attack["skill"] = 90; foe.attack["damage"] = 20
    hp0 = foe.health
    for s in range(80):                                                    # 擲到一次命中(物理)以驗反彈
        foe.health = hp0; c.fatigue = 100
        r = combat.resolve_attack(foe, c, gd, RNG(s))
        if r["hit"] and r["damage"] > 0:
            assert foe.health < hp0 and c.fatigue == 90                    # 攻擊者被反彈 + 扣 10 體
            break
    else:
        raise AssertionError("應至少一次命中以驗盾反")
    for s in range(80):                                                    # 力竭(3 < 10)→ 不反、不扣負
        foe.health = hp0; c.fatigue = 3
        r = combat.resolve_attack(foe, c, gd, RNG(s))
        if r["hit"] and r["damage"] > 0:
            assert foe.health == hp0 and c.fatigue == 3                    # 力竭施展不出
            break


def test_empower_diminishing_stack_curve():
    """R39 empower 遞減疊加(戰旗+號令同時生效):降序 最強×1 + 次強×0.7…;單道不變(byte-identical)。"""
    foe = combat.spawn_creature(gd0 := get_gamedata(), "bandit", RNG(2))   # 任一非玩家攻擊者
    target = combat.spawn_creature(gd0, "bandit", RNG(3)); target.max_health = target.health = 99999
    def dmg(effs):
        foe.active_effects[:] = [{"kind": "empower", "magnitude": m, "turns": 1} for m in effs]
        return sum(combat.resolve_attack(foe, target, gd0, RNG(s))["damage"] for s in range(60))
    base = dmg([])
    one = dmg([0.20])                                  # 單道:×1.20
    two = dmg([0.20, 0.15])                            # 雙道遞減:×(1 + 0.20 + 0.15×0.7)=×1.305
    assert one > base and two > one                    # 疊加有感、但…
    # 比例驗證:雙道增幅 / 單道增幅 ≈ (0.20+0.105)/0.20 = 1.525(遞減,非線性 1.75)
    assert (two - base) < (one - base) * 1.75          # 遞減:小於純相加(SUM)
    assert (two - base) > (one - base) * 1.0           # 但確有疊加(大於 MAX 的不疊)


# --- 壁壘(heavy_armor 75)---------------------------------------------
def test_bulwark_reduces_physical_and_costs_fatigue():
    gd, c = _char(heavy_armor=75)
    mastery.choose(c, gd, "heavy_armor_75", "bulwark")
    assert mastery.incoming_physical_factor(c, gd) == 0.85
    assert mastery.attack_fatigue_factor(c, gd) > 1.0
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
    mastery.choose(c, gd, "heavy_armor_75", "bulwark")
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
    mastery.choose(c, gd, "restoration_75", "overheal_ward")
    c.active_effects = []
    c.health = c.max_health             # 血滿 → 治療全溢出
    magic.cast(c, gd, "minor_heal", RNG(1))
    shields = [e for e in c.active_effects if e["kind"] == "shield"]
    assert shields and shields[0]["magnitude"] > 0
    assert shields[0]["magnitude"] <= round(c.max_health * 0.5)   # 夾 cap
    assert shields[0]["turns"] == 4
    # 負向邊界(併入):大幅缺血 → 治療被血上限吸收無溢出 → 不產生護盾
    c.active_effects = []
    c.health = 1
    magic.cast(c, gd, "minor_heal", RNG(1))
    assert not [e for e in c.active_effects if e["kind"] == "shield"]


def test_overheal_ward_aggregate_cap_across_casts():
    """審查破口回歸:反覆施放治療,溢盾『總量』不得疊破 cap_ratio×生命上限。"""
    gd, c = _char(restoration=75)
    mastery.choose(c, gd, "restoration_75", "overheal_ward")
    c.active_effects = []
    c.health = c.max_health
    c.magicka = c.max_magicka = 999
    cap = round(c.max_health * 0.5)
    for _ in range(12):
        magic.cast(c, gd, "minor_heal", RNG(1))
    assert magic.active_shield(c) <= cap, "溢盾總量不得超過 cap"
    c.active_effects.append({"kind": "shield", "magnitude": 30, "turns": 3})
    assert magic.active_shield(c) <= cap + 30


# --- 過載(destruction 100)-------------------------------------------
def test_overload_raises_cost_and_power_destruction_only():
    gd, c = _char(destruction=100, restoration=100)
    assert mastery.spell_cost_factor(c, gd, "destruction") == 1.0   # 未選 → 中性
    mastery.choose(c, gd, "destruction_100", "overload")
    assert mastery.spell_cost_factor(c, gd, "destruction") == 1.30
    assert mastery.spell_power_bonus(c, gd, "destruction") == 0.20
    assert mastery.spell_cost_factor(c, gd, "restoration") == 1.0
    assert mastery.spell_power_bonus(c, gd, "restoration") == 0.0
    c.skills["destruction"] = 100
    cost_100 = magic.effective_cost(c, gd, "flames")
    c.skills["destruction"] = 99
    cost_99 = magic.effective_cost(c, gd, "flames")
    assert cost_100 > cost_99


# --- 撬鎖名家(security 75)-------------------------------------------
def test_lock_floor_only_raises_never_lowers():
    gd, c = _char(security=75)
    mastery.choose(c, gd, "security_75", "master_floor")
    assert mastery.lock_floor(c, gd) == 0.30
    hard = dungeon.effective_pick_lock_chance(c, gd, 100)
    assert abs(hard - 0.30) < 1e-9
    easy_base = dungeon.pick_lock_chance(c.skill("security"), 0)
    easy_eff = dungeon.effective_pick_lock_chance(c, gd, 0)
    assert easy_eff == max(easy_base, 0.30) == easy_base
    gd2, c2 = _char(security=74)
    assert dungeon.effective_pick_lock_chance(c2, gd2, 100) == dungeon.pick_lock_chance(74, 100)


# --- 辯舌·折服(speechcraft 100)------------------------------------
def test_charm_guarantees_once_per_npc():
    gd, c = _char(speechcraft=100)
    mastery.choose(c, gd, "speechcraft_100", "charm")
    nid = next(iter(gd.npcs))
    r1 = dialogue.persuade(c, gd, nid, RNG(1))
    assert r1["ok"] and r1.get("charmed") and nid in c.persuaded_npcs
    r2 = dialogue.persuade(c, gd, nid, RNG(1))
    assert not r2.get("charmed")
    gd2, c2 = _char(speechcraft=99)
    assert not dialogue.persuade(c2, gd2, nid, RNG(1)).get("charmed")


# --- 解鎖(可選)播報精確性 ---------------------------------------------
def test_choice_ready_event_fires_exactly_once_across_multilevel():
    """一次灌注跨越門檻(含一次跨多級)時,每個被跨過的門檻恰好一次,不漏不重;區間內不跨則無事件。"""
    gd, c = _char()
    c.skills["security"] = 70
    c.skill_xp["security"] = 0.0
    evs = progression.use_skill(c, gd, "security", 200.0)   # 大量 xp 一次跨過 75(可能連帶跨 100)
    node_ids = [e["node_id"] for e in evs if e["type"] == "mastery_choice_ready"]
    assert node_ids.count("security_75") == 1              # 跨 75 恰一次
    assert len(node_ids) == len(set(node_ids))            # 不重複(跨多門檻各一次)
    assert c.skills["security"] >= 75
    # 重設到門檻間(80,遠離 100)小幅加 xp → 不跨任何門檻 → 無事件
    c.skills["security"] = 80
    c.skill_xp["security"] = 0.0
    evs2 = progression.use_skill(c, gd, "security", 5.0)
    assert c.skills["security"] < 100
    assert not [e for e in evs2 if e["type"] == "mastery_choice_ready"]


# --- 存檔向後相容 -------------------------------------------------------
def test_mastery_choices_roundtrip_and_backward_compat():
    gd, c = _char(block=50)
    mastery.choose(c, gd, "block_50", "shieldwall")
    d = c.to_dict()
    assert d["mastery_choices"]["block_50"] == "shieldwall"
    assert Character.from_dict(d).mastery_choices == {"block_50": "shieldwall"}
    d.pop("mastery_choices")            # 舊存檔缺此欄 → dataclass 預設空 dict
    assert Character.from_dict(d).mastery_choices == {}


def test_persuaded_npcs_roundtrip_and_backward_compat():
    gd, c = _char(speechcraft=100)
    c.persuaded_npcs = ["alpha", "beta"]
    d = c.to_dict()
    assert Character.from_dict(d).persuaded_npcs == ["alpha", "beta"]
    d.pop("persuaded_npcs")
    assert Character.from_dict(d).persuaded_npcs == []


def test_pending_choice_derivation_backcompat():
    """舊存檔達門檻但無選擇 → pending 列出、getter 中性,選後才生效(不自動指派)。"""
    gd, c = _char(block=50, security=75)
    d = c.to_dict()
    d.pop("mastery_choices", None)
    c2 = Character.from_dict(d)
    progression.ensure_mastery_choices(c2, gd)
    assert c2.mastery_choices == {}
    node_ids = {n["id"] for n in mastery.pending_choices(c2, gd)}
    assert "block_50" in node_ids and "security_75" in node_ids
    assert mastery.block_hit_penalty(c2, gd) == formulas.BLOCK_HIT_PENALTY
    assert mastery.lock_floor(c2, gd) == 0.0
    mastery.choose(c2, gd, "security_75", "master_floor")
    assert mastery.lock_floor(c2, gd) == 0.30


def test_ensure_mastery_choices_prunes_stale():
    """JSON 改版安全:指向已不存在 node/opt 的陳舊選擇被清掉,有效者保留。"""
    gd, c = _char(block=50)
    c.mastery_choices = {"block_50": "shieldwall", "gone_node": "x", "block_50_bad": "nope"}
    progression.ensure_mastery_choices(c, gd)
    assert c.mastery_choices == {"block_50": "shieldwall"}


def test_relocated_group_resets_together():
    """毀滅 50/75 互換遷移:搬家組任一選擇陳舊 → 整組退 pending
    (舊檔 50=凝神+75=共鳴 只清共鳴會把它永久鎖死);全有效則整組保留、不過度清除。"""
    gd, c = _char(destruction=75)
    c.mastery_choices = {"destruction_50": "focused_mind", "destruction_75": "resonant_strike"}
    progression.ensure_mastery_choices(c, gd)
    assert c.mastery_choices == {}
    pend = {n["id"] for n in mastery.pending_choices(c, gd)}
    assert {"destruction_50", "destruction_75"} <= pend
    gd, c = _char(destruction=75)
    c.mastery_choices = {"destruction_50": "focused_mind", "destruction_75": "arcane_battery"}
    progression.ensure_mastery_choices(c, gd)
    assert c.mastery_choices == {"destruction_50": "focused_mind",
                                 "destruction_75": "arcane_battery"}


def test_shipped_kinds_all_implemented():
    """fail-fast:出貨 mastery.json 每個 option 的 kind 都須已實作 + opt_id 入 _defs 白名單,
    否則玩家看到可選卻零效果 / 成死 perk(併入 batch1 的死 perk 防線,升級為全節點而非僅 100 級)。"""
    gd = get_gamedata()
    defids = {d["opt_id"] for d in mastery._defs(gd)}
    for node in mastery._nodes(gd):
        for o in node["options"]:
            assert o["kind"] in mastery._IMPLEMENTED_KINDS, f"未實作的 kind:{o['kind']}"
            assert o["opt_id"] in defids, f"死 perk:{node['id']} {o['opt_id']}({o['kind']})"


def test_unimplemented_kind_is_inert():
    """打錯/未實作的 kind:不出 pending、不可選、不計分(完全 inert)。"""
    gd, c = _char(blade=100)
    bogus = {"id": "blade_x", "skill": "blade", "threshold": 33,   # 33:無任何真實節點的空門檻
             "options": [{"opt_id": "ghost", "name": "幻影", "kind": "not_a_real_kind"}]}
    gd.mastery.append(bogus)
    try:
        assert all(n["id"] != "blade_x" for n in mastery.pending_choices(c, gd))
        assert not mastery.nodes_at(c, gd, "blade", 33)
        c.mastery_choices["blade_x"] = "ghost"   # 即使硬塞,unlocked 仍過濾
        assert all(e.get("node_id") != "blade_x" for e in mastery.unlocked(c, gd))
    finally:
        gd.mastery.remove(bogus)
        c.mastery_choices.pop("blade_x", None)


def test_mastery_never_writes_base_skill():
    """里程碑不得寫進 char.skills(否則破壞 learn-by-doing 與夾限)。"""
    gd, c = _char(heavy_armor=75, destruction=100, block=50)
    mastery.choose(c, gd, "heavy_armor_75", "bulwark")
    mastery.choose(c, gd, "destruction_100", "overload")
    mastery.choose(c, gd, "block_50", "shieldwall")
    snapshot = dict(c.skills)
    mastery.unlocked(c, gd)
    mastery.incoming_physical_factor(c, gd)
    mastery.spell_power_bonus(c, gd, "destruction")
    mastery.block_hit_penalty(c, gd)
    assert c.skills == snapshot


def test_next_threshold_hint_uses_base_and_skips_done():
    """訓練師里程碑提示:回傳下一個未達門檻、以 base_skill 計、全達/無里程碑→None。"""
    gd, c = _char(block=44)            # block 節點:50 / 75(廣度 pass)
    nxt = mastery.next_threshold(c, gd, "block")
    assert nxt and nxt["threshold"] == 50 and nxt["remaining"] == 6 and nxt["name"]
    c.equip_skill_bonus["block"] = 10
    assert c.skill("block") >= 50 and mastery.next_threshold(c, gd, "block")["remaining"] == 6
    c.skills["block"] = 50             # 達 50 → 下一個未達門檻為 75
    nxt = mastery.next_threshold(c, gd, "block")
    assert nxt and nxt["threshold"] == 75 and nxt["remaining"] == 25
    c.skills["block"] = 75             # 達 75 → 下一個未達門檻為 100(補頂點 pass)
    nxt = mastery.next_threshold(c, gd, "block")
    assert nxt and nxt["threshold"] == 100 and nxt["remaining"] == 25
    c.skills["block"] = 100            # 達最高門檻 → None
    assert mastery.next_threshold(c, gd, "block") is None
    # 已達某技能最高門檻 → None(athletics 門檻 50/75/100)
    c.skills["athletics"] = 100
    assert mastery.next_threshold(c, gd, "athletics") is None


# --- P1:持久 fortify 加成層 -------------------------------------------
def test_skill_fortify_stacks_effective_not_base():
    gd, c = _char(blade=50)
    base_marks = c.base_skill("marksman")
    node = {"id": "blade_sf", "skill": "blade", "threshold": 50, "options": [
        {"opt_id": "m", "name": "射", "kind": "skill_fortify", "skill": {"marksman": 8}, "desc": ""}]}
    gd.mastery.append(node)
    try:
        assert mastery.choose(c, gd, "blade_sf", "m") is not None
        assert c.mastery_skill_bonus.get("marksman") == 8
        assert c.skill("marksman") == base_marks + 8
        assert c.base_skill("marksman") == base_marks          # base 不動(鐵律)
    finally:
        gd.mastery.remove(node)
        c.mastery_choices.pop("blade_sf", None)
        stats.recompute_mastery_bonuses(c, gd)


def test_fortify_does_not_bootstrap_threshold():
    """里程碑 +skill 持久加成只進 skill(),不進 base_skill → 不得自我推過更高門檻。"""
    gd, c = _char(block=50)
    c.mastery_skill_bonus["block"] = 40                     # 模擬 recompute 後的快取
    try:
        assert c.skill("block") == 90 and c.base_skill("block") == 50
        for node in mastery._nodes(gd):
            if node["skill"] == "block" and node["threshold"] > 50:
                assert not mastery._node_reached(c, node), "fortify 不得推過更高門檻"
        assert all(n["threshold"] <= 50 for n in mastery.pending_choices(c, gd)
                   if n["skill"] == "block")
    finally:
        c.mastery_skill_bonus.pop("block", None)


def test_recompute_mastery_idempotent():
    gd, c = _char(blade=50)
    node = {"id": "blade_idem", "skill": "blade", "threshold": 50, "options": [
        {"opt_id": "m", "name": "射", "kind": "skill_fortify", "skill": {"marksman": 8}, "desc": ""}]}
    gd.mastery.append(node)
    try:
        mastery.choose(c, gd, "blade_idem", "m")
        snap = dict(c.skills)
        stats.recompute_mastery_bonuses(c, gd)
        stats.recompute_mastery_bonuses(c, gd)
        assert c.mastery_skill_bonus == {"marksman": 8}     # 不累積、不漂移
        assert c.skills == snap                             # recompute 不寫 base
    finally:
        gd.mastery.remove(node)
        c.mastery_choices.pop("blade_idem", None)
        stats.recompute_mastery_bonuses(c, gd)


# --- P2:戰鬥系內容 -----------------------------------------------------
def test_weapon_mod_target_matches_weapon_skill():
    gd, c = _char(blade=100)
    mastery.choose(c, gd, "blade_100", "savage")
    assert mastery.weapon_mod(c, gd, "blade").get("power") == 0.12
    assert mastery.weapon_mod(c, gd, "blunt") == {}        # target 不符 → 不適用
    assert mastery.weapon_mod(c, gd, None) == {}


def test_weapon_mod_power_increases_damage_with_recoil():
    def dealt(savage, seed):
        gd, c = _char(blade=100, strength=80)
        c.weapon = "steel_dagger"
        if savage:
            mastery.choose(c, gd, "blade_100", "savage")
        foe = combat.spawn_creature(gd, "giant_rat", RNG(1))
        foe.health = foe.max_health = 99999
        c.health = c.max_health
        ev = combat.resolve_attack(c, foe, gd, RNG(seed))
        return (ev["damage"], c.max_health - c.health) if ev["hit"] and ev["damage"] > 0 else None
    more = recoiled = 0
    for s in range(120):
        a = dealt(False, s)
        b = dealt(True, s)
        if a and b:
            assert b[0] >= a[0]                  # 威力 +12% → 傷害不減
            if b[0] > a[0]:
                more += 1
            if b[1] > 0:                          # 迅捷連斬反作用 → 自損
                recoiled += 1
    assert more >= 3 and recoiled >= 3


def test_blunt_pen_increases_damage_vs_armor():
    def dealt(sunder, seed):
        gd, c = _char(blunt=100, strength=80)
        c.weapon = "iron_mace"
        if sunder:
            mastery.choose(c, gd, "blunt_100", "sunder")
        foe = combat.spawn_creature(gd, "dremora", RNG(1))   # 高護甲精英
        foe.health = foe.max_health = 99999
        ev = combat.resolve_attack(c, foe, gd, RNG(seed))
        return ev["damage"] if ev["hit"] and ev["damage"] > 0 else None
    more = 0
    for s in range(120):
        a = dealt(False, s)
        b = dealt(True, s)
        if a and b:
            assert b >= a
            if b > a:
                more += 1
    assert more >= 3, "破甲應對高護甲敵提高有效傷害"


def test_blunt_concussion_weakens_enemy():
    gd, c = _char(blunt=100)
    c.weapon = "iron_mace"
    mastery.choose(c, gd, "blunt_100", "concussion")
    foe = combat.spawn_creature(gd, "giant_rat", RNG(1))
    foe.health = foe.max_health = 99999
    got = 0
    for s in range(60):
        foe.active_effects = []
        ev = combat.resolve_attack(c, foe, gd, RNG(s))
        if ev["hit"] and any(e["kind"] == "weaken" for e in foe.active_effects):
            got += 1
    assert got >= 1
    # 併入 disarm getter pin(iron_fists power 0.15 已被聚合測覆蓋,僅保唯一的 stagger on_hit_status)
    gd2, c2 = _char(hand_to_hand=75)
    c2.weapon = "fists"
    mastery.choose(c2, gd2, "hand_to_hand_75", "disarm")
    assert mastery.weapon_mod(c2, gd2, "hand_to_hand")["on_hit_status"]["kind"] == "stagger"


def test_block_riposte_staggers_attacker():
    gd, c = _char(block=50)
    mastery.choose(c, gd, "block_50", "shield_bash")
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.attack["skill"] = 100
    foe.attack["damage"] = 4
    got = 0
    for s in range(60):
        foe.active_effects = []
        c.health = c.max_health
        combat.resolve_attack(foe, c, gd, RNG(s), defender_blocking=True)
        if any(e["kind"] == "stagger" for e in foe.active_effects):
            got += 1
    assert got >= 1, "盾擊踉蹌應至少觸發一次"


def test_heavy_armor_unyielding_resist():
    gd, c = _char(heavy_armor=75)
    base = magic.entity_resist(c, gd).get("magic", 0)
    mastery.choose(c, gd, "heavy_armor_75", "unyielding")
    assert c.mastery_resist.get("magic") == 10
    assert magic.entity_resist(c, gd).get("magic", 0) == base + 10
    assert mastery.incoming_physical_factor(c, gd) == 1.0   # 非壁壘 → 無物理減傷


def test_smithing_temper_cap_and_free():
    from tesrpg.systems import smithing
    gd, c = _char(smithing=100)
    base_cap = smithing.effective_temper_cap(c, gd)
    mastery.choose(c, gd, "smithing_75", "master_temper")
    assert smithing.effective_temper_cap(c, gd) == base_cap + 1
    gd2, c2 = _char(smithing=100)
    mastery.choose(c2, gd2, "smithing_75", "efficient")
    assert mastery.temper_free_chance(c2, gd2) == 0.30


def test_athletics_travel_and_fatigue():
    gd, c = _char(athletics=50)
    mastery.choose(c, gd, "athletics_50", "marathon")
    assert mastery.travel_factor_bonus(c, gd) == 0.10
    # 戰鬥省體:second_wind 使攻擊耗體更低
    gd2, c2 = _char(athletics=50)
    mastery.choose(c2, gd2, "athletics_50", "second_wind")
    c2.weapon = "steel_dagger"
    c2.fatigue = c2.max_fatigue
    f0 = c2.fatigue
    combat.player_attack_cost(c2, gd2)
    cost_with = f0 - c2.fatigue
    gd3, c3 = _char(athletics=50)
    c3.weapon = "steel_dagger"
    c3.fatigue = c3.max_fatigue
    f0b = c3.fatigue
    combat.player_attack_cost(c3, gd3)
    cost_without = f0b - c3.fatigue
    assert cost_with < cost_without


# --- P3:魔法系內容 -----------------------------------------------------
def test_destruction_impact_staggers_on_hit():
    gd, c = _char(destruction=100)
    mastery.choose(c, gd, "destruction_100", "impact")
    assert mastery.spell_on_hit(c, gd, "destruction")["kind"] == "stagger"
    assert mastery.spell_cost_factor(c, gd, "destruction") == 1.0      # 衝擊餘波無額外魔耗
    c.spells = ["flames"]
    c.magicka = c.max_magicka = 99999
    got = 0
    for s in range(60):
        foe = combat.spawn_creature(gd, "dremora", RNG(1))
        foe.health = foe.max_health = 99999
        magic.cast(c, gd, "flames", RNG(s), target=foe)
        c.magicka = 99999
        if any(e["kind"] == "stagger" for e in foe.active_effects):
            got += 1
    assert got >= 1


def test_conjuration_summon_mods():
    gd, c = _char(conjuration=100)
    mastery.choose(c, gd, "conjuration_100", "twin_summon")
    assert mastery.summon_mod(c, gd).get("extra") == 1
    summon_spell = next((sid for sid, sp in gd.spells.items()
                         if sp.get("effect", {}).get("kind") == "summon"), None)
    if summon_spell:
        c.spells = [summon_spell]
        c.magicka = c.max_magicka = 99999
        battle = {}
        magic.cast(c, gd, summon_spell, RNG(1), battle=battle)
        assert len(battle.get("allies", [])) == 2          # 主 + 額外較弱盟友
    gd2, c2 = _char(conjuration=100)
    mastery.choose(c2, gd2, "conjuration_100", "bound_blade")
    assert mastery.summon_mod(c2, gd2).get("hp_bonus") == 0.25


def test_alteration_stoneflesh_passive_armor():
    gd, c = _char(alteration=75)
    mastery.choose(c, gd, "alteration_75", "stoneflesh")
    assert mastery.passive_armor_bonus(c, gd) == 20
    c.magicka = 10
    a_with = combat._armor_rating(c, gd)
    c.magicka = 0
    a_without = combat._armor_rating(c, gd)
    assert a_with == a_without                            # 被動護甲改無條件(對抗審查:物理 stance 不綁魔力)
    assert a_without >= 20                                # 魔力 0 仍含 +20


def test_alchemy_potion_potency_and_poison_unlocks():
    """R31:濃縮萃取仍給 potion_potency;原塗毒次數選項改為功能性毒型解鎖(weaken/slow/fear)。"""
    gd, c = _char(alchemy=100)
    mastery.choose(c, gd, "alchemy_75", "concentrated")
    assert mastery.potion_potency(c, gd) == 0.20
    # 未選功能性選項 → 無特殊毒型解鎖(基礎 DoT/麻痺永遠可釀)
    gd2, c2 = _char(alchemy=100)
    assert mastery.poison_unlocks(c2, gd2) == set()
    mastery.choose(c2, gd2, "alchemy_50", "toxin_master")     # → 衰毒
    mastery.choose(c2, gd2, "alchemy_75", "potent_poison")    # → 遲緩毒 + 毒效延長
    mastery.choose(c2, gd2, "alchemy_100", "venom_lord")      # → 懼毒
    assert mastery.poison_unlocks(c2, gd2) == {"weaken", "slow", "fear"}
    assert mastery.poison_duration_bonus(c2, gd2) == 1
    # 解鎖後實際釀得出對應毒型:衰毒(deathbell+imp_stool 共有 damage_strength)
    c2.weapon = "steel_dagger"
    inventory.add_item(c2, "deathbell", 1); inventory.add_item(c2, "imp_stool", 1)
    from tesrpg.systems import alchemy as _alc
    from tesrpg.rng import RNG as _RNG
    r = _alc.brew(c2, gd2, "deathbell", "imp_stool", _RNG(0))
    assert gd2.item(r["item_id"])["poison"]["status"] == "weaken"


def test_mysticism_enchant_potency_and_absorb():
    gd, c = _char(mysticism=100)
    mastery.choose(c, gd, "mysticism_100", "soul_siphon")
    assert mastery.enchant_potency(c, gd) == 0.20
    gd2, c2 = _char(mysticism=100)
    mastery.choose(c2, gd2, "mysticism_100", "spectral_aegis")
    assert mastery.passive_armor_bonus(c2, gd2) == 15     # 靈光護壁(原 spell_absorb 抗性 → 改被動護甲 apex)


def test_illusion_fear_on_hit_and_merchant():
    gd, c = _char(illusion=75, mercantile=50)
    sp0 = world.sell_price(c, gd, "steel_dagger")
    mastery.choose(c, gd, "illusion_75", "charm_market")
    assert world.sell_price(c, gd, "steel_dagger") >= sp0
    gd2, c2 = _char(illusion=75)
    mastery.choose(c2, gd2, "illusion_75", "cowardice")
    c2.weapon = "steel_dagger"
    got = 0
    for s in range(80):
        foe = combat.spawn_creature(gd2, "giant_rat", RNG(1))
        foe.health = foe.max_health = 99999
        ev = combat.resolve_attack(c2, foe, gd2, RNG(s))
        if ev["hit"] and any(e["kind"] == "fear" for e in foe.active_effects):
            got += 1
    assert got >= 1


def test_restoration_steadfast_regen_on_low():
    gd, c = _char(restoration=75)
    mastery.choose(c, gd, "restoration_75", "steadfast")
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    foe.attack["damage"] = 4
    foe.attack["skill"] = 100
    c.max_health = 100
    triggered = False
    for s in range(40):
        c.active_effects = [e for e in c.active_effects if e.get("source") != "steadfast"]
        c.health = 20                                      # < 25% → 應觸發
        combat.resolve_attack(foe, c, gd, RNG(s))
        if any(e.get("source") == "steadfast" and e["kind"] == "regen" for e in c.active_effects):
            triggered = True
            break
    assert triggered


# --- P4:潛行系內容 + 群體規模反制 -------------------------------------
def test_horde_penalty_crushes_stealth_above_three():
    """>3 敵:潛近/隱遁機率陡降(取代秒殺率上限的載重級反制)。"""
    a3 = F.stealth_approach_chance(100, 30, 3, 0)   # 第 4 引數現為穿戴總重(0=無甲)
    a4 = F.stealth_approach_chance(100, 30, 4, 0)
    a5 = F.stealth_approach_chance(100, 30, 5, 0)
    assert a4 < a3 - 0.20 and a5 < a4               # 第 4 敵起大減
    r3 = F.restealth_chance(100, 100, 3, 0)
    r4 = F.restealth_chance(100, 100, 4, 0)
    assert r4 < r3 - 0.20                            # 隱遁同樣大減


def test_solo_boss_survives_apex_opener():
    """solo boss 反一刀:即使最壞 apex(影刃+夜母+雙持+淬鍊),單次偷襲也不可秒 solo boss。"""
    gd, c = _char(sneak=100, blade=100, smithing=100, acrobatics=100)
    inventory.add_item(c, "glass_dagger", 2)
    c.weapon = "glass_dagger"
    inventory.equip_offhand(c, gd, "glass_dagger")
    c.weapon_temper = {"glass_dagger": 5}
    c.factions["dark_brotherhood"] = 6
    mastery.choose(c, gd, "sneak_100", "shadowblade")
    killed = 0
    for s in range(400):
        boss = combat.spawn_creature(gd, "vampire_lord", RNG(s))   # 較低血的 solo boss
        ev = combat.resolve_attack(c, boss, gd, RNG(s * 3 + 1), sneak_attack=True)
        if ev["defender_dead"]:
            killed += 1
    assert killed == 0, f"solo boss 不應被單擊秒殺,卻有 {killed}/400 次"
    # 但對非 solo 精英照常可秒(影刃力量幻想不受夾限影響)
    elite_kills = sum(combat.resolve_attack(
        c, _seed_elite(gd, s), gd, RNG(s * 3 + 1), sneak_attack=True)["defender_dead"]
        for s in range(200))
    assert elite_kills > 0


def _seed_elite(gd, s):
    e = combat.spawn_creature(gd, "dremora", RNG(s))
    return e


def test_sneak_mult_bonus_raises_sneak_damage():
    gd, c = _char(sneak=100, blade=100)
    c.weapon = "steel_dagger"
    foe = combat.spawn_creature(gd, "dremora", RNG(1))
    foe.health = foe.max_health = 99999
    base = combat.estimate_sneak_damage(c, gd, foe)
    mastery.choose(c, gd, "sneak_100", "shadowblade")
    assert mastery.sneak_mult_bonus(c, gd) == 0.50
    assert combat.estimate_sneak_damage(c, gd, foe) > base   # 影刃放大偷襲傷害


def test_vanish_relentless_removes_reuse_decay_but_not_horde():
    gd, c = _char(sneak=100, acrobatics=100)
    mastery.choose(c, gd, "sneak_75", "relentless_shadow")
    assert mastery.has_vanish_relentless(c, gd)
    # 免重複遞減:used=3 與 used=0 同機率
    assert combat.vanish_chance(c, 2, 3, gd) == combat.vanish_chance(c, 2, 0, gd)
    # 但 >3 敵仍被壓制(連環踏影擋不住大群)
    assert combat.vanish_chance(c, 5, 0, gd) <= 0.10


def test_vanish_floor_takes_max_across_sources():
    """審查回歸:同時選 tumble(acro 0.10)+ shadowstep(sneak 0.15)→ 取最高 0.15(非第一個)。"""
    gd, c = _char(sneak=100, acrobatics=100)
    mastery.choose(c, gd, "acrobatics_75", "tumble")        # vanish_floor 0.10(JSON 在前)
    mastery.choose(c, gd, "sneak_100", "shadowstep")        # vanish_floor 0.15
    assert mastery.vanish_floor(c, gd) == 0.15
    assert combat.vanish_chance(c, 5, 2, gd) >= 0.15


def test_merchant_bonus_sums_across_sources():
    """審查回歸:illusion 魅惑 + mercantile 精算 兩來源相加(非只取第一個)。"""
    gd, c = _char(illusion=75, mercantile=50)
    mastery.choose(c, gd, "illusion_75", "charm_market")    # 0.12
    mastery.choose(c, gd, "mercantile_50", "haggler")       # 0.12
    assert abs(mastery.merchant_bonus(c, gd) - 0.24) < 1e-9


def test_sneak_approach_and_armor_relief():
    gd, c = _char(sneak=100)
    foes = [combat.spawn_creature(gd, "bandit", RNG(1))]
    base = combat.stealth_approach_chance(c, foes, gd)
    mastery.choose(c, gd, "sneak_75", "silent_approach")
    assert combat.stealth_approach_chance(c, foes, gd) > base   # 無聲潛近 +頻率
    # 無聲披掛:抵消重甲噪音(穿重甲時潛近不再被罰)
    gd2, c2 = _char(light_armor=75)
    mastery.choose(c2, gd2, "light_armor_75", "featherweight")
    assert mastery.armor_sneak_relief(c2, gd2) == 1.0


def test_scout_prep_and_recon():
    """偵查里程碑「情報→戰力」:備戰 prep / 料敵機先 approach / 臨陣預判 evasion;
    R35 去冗餘:scout_50 去 skill_fortify 死填充 → 料敵判讀(recon_resist_read,弱點揭露門檻 75→50,
    與交易·線人耳目同源)→ scout 取得「戰場判讀」身份,二選一變 approach(搶先機)vs 判讀(看弱點)。"""
    gd, c = _char(scout=100)
    mastery.choose(c, gd, "scout_75", "vanguard"); mastery.choose(c, gd, "scout_100", "battle_master")
    assert mastery.prep_bonus(c, gd) == 2                            # 兩階備戰相加
    gd, c = _char(scout=100)
    mastery.choose(c, gd, "scout_50", "intel_strike"); mastery.choose(c, gd, "scout_100", "first_blood")
    assert abs(mastery.approach_bonus(c, gd) - (0.10 + 0.12)) < 1e-9   # 料敵機先+先聲奪人 approach 多源相加
    gd, c = _char(scout=75)
    mastery.choose(c, gd, "scout_75", "preempt")
    assert mastery.evasion_bonus(c, gd) == 0.04                      # 臨陣預判閃避
    gd, c = _char(scout=50)                                          # R35:scout_50 料敵判讀亦降弱點門檻 75→50
    assert mastery.recon_reveal_threshold(c, gd) == 75
    mastery.choose(c, gd, "scout_50", "threat_read")
    assert mastery.recon_reveal_threshold(c, gd) == 50
    gd, c = _char(mercantile=75)                                     # 弱點揭露門檻亦可掛交易·線人耳目
    assert mastery.recon_reveal_threshold(c, gd) == 75
    mastery.choose(c, gd, "mercantile_75", "informant")
    assert mastery.recon_reveal_threshold(c, gd) == 50
    # thief 諜報偵搜(併自 test_class_identity.test_subterfuge_prep_bonus_sums_with_scout):
    # subterfuge_intel 接 prep_bonus,且與 scout 線跨來源相加(原 bug:只取 1)
    gd, c = _char(mercantile=75, scout=80)
    mastery.choose(c, gd, "mercantile_75", "subterfuge_intel")
    assert mastery.prep_bonus(c, gd) == 1
    mastery.choose(c, gd, "scout_75", "vanguard")
    assert mastery.prep_bonus(c, gd) == 2


def test_has_recon_perk():
    """地城探明四鄰:任一 recon 里程碑解鎖(scout 斥候之眼 / mercantile 線人耳目;marksman 獵手偵察 R40 已移除)。"""
    gd, c = _char()
    assert not mastery.has_recon_perk(c, gd)                 # 無偵查 perk
    gd1, c1 = _char(scout=25)
    mastery.choose(c1, gd1, "scout_25", "recon_basics")      # 斥候之眼(recon_reveal_floor)→ 解鎖
    assert mastery.has_recon_perk(c1, gd1)
    gd2, c2 = _char(mercantile=75)
    mastery.choose(c2, gd2, "mercantile_75", "informant")    # 線人耳目(recon_resist_read)→ 另一 recon kind
    assert mastery.has_recon_perk(c2, gd2)


def test_security_pick_no_break():
    gd, c = _char(security=75)
    mastery.choose(c, gd, "security_75", "pick_thrift")
    assert mastery.pick_keep_chance(c, gd) == 0.50
    inventory.add_item(c, dungeon.LOCKPICK_ITEM, 50)
    c.fatigue = c.max_fatigue = 9999
    kept_some = False
    for s in range(60):
        before = inventory.count_item(c, dungeon.LOCKPICK_ITEM)
        r = dungeon.pick_lock(c, gd, 100, RNG(s))   # 高難鎖 → 多半失敗
        after = inventory.count_item(c, dungeon.LOCKPICK_ITEM)
        if not r["success"] and after == before:    # 失敗卻沒折斷 → 巧手不折生效
            kept_some = True
            break
    assert kept_some


def test_security_theft_and_casing():
    """R36 security 功能化(混合身份):順手牽羊(theft_skill)+ 賊眼·窺探(dungeon_casing 布林)。"""
    # 白名單
    assert "theft_skill" in mastery._IMPLEMENTED_KINDS
    assert "dungeon_casing" in mastery._IMPLEMENTED_KINDS
    # theft_bonus 聚合:未選 → {};選 light_fingers → 得手率+0.15、賞金 ×0.5
    gd, c = _char(security=50)
    assert mastery.theft_bonus(c, gd) == {}
    mastery.choose(c, gd, "security_50", "light_fingers")
    assert mastery.theft_bonus(c, gd) == {"steal_bonus": 0.15, "bounty_factor": 0.5}
    # steal_chance 套加成且夾 0.95
    gd, c = _char(security=50, sneak=10)
    base = crime.steal_chance(c, gd)
    mastery.choose(c, gd, "security_50", "light_fingers")
    assert abs(crime.steal_chance(c, gd) - min(0.95, base + 0.15)) < 1e-9
    gd, c = _char(security=100, sneak=100)
    mastery.choose(c, gd, "security_50", "light_fingers")
    assert crime.steal_chance(c, gd) <= 0.95                          # 高技能+perk 仍不破 cap
    # 失風賞金減半:強制必被抓(patch steal_chance→0),比較有/無 perk 的 bounty_added
    real_sc = crime.steal_chance
    crime.steal_chance = lambda ch, gd_: 0.0
    try:
        gd, c0 = _char()
        r0 = crime.steal_item(c0, gd, "iron_sword", RNG(0))
        gd, c1 = _char(security=50)
        mastery.choose(c1, gd, "security_50", "light_fingers")
        r1 = crime.steal_item(c1, gd, "iron_sword", RNG(0))
    finally:
        crime.steal_chance = real_sc
    assert r0["caught"] and r1["caught"]
    assert r1["bounty_added"] == int(round(r0["bounty_added"] * 0.5))   # 賞金減半
    # dungeon_casing 布林解鎖 + 與 scout recon 互補不互斥(R35 防隱形重複)
    gd, c = _char(security=100)
    mastery.choose(c, gd, "security_100", "thiefs_eye")
    assert mastery.has_dungeon_casing(c, gd) is True
    gd, c = _char(security=100)
    mastery.choose(c, gd, "security_100", "master_thief")
    assert mastery.has_dungeon_casing(c, gd) is False and mastery.lock_floor(c, gd) == 0.50
    gd, c = _char(security=100, scout=100)
    mastery.choose(c, gd, "security_100", "thiefs_eye")
    mastery.choose(c, gd, "scout_25", "recon_basics")
    assert mastery.has_dungeon_casing(c, gd) and mastery.has_recon_perk(c, gd)   # 並存:全層機關 vs 四鄰任意,互補
    # 遷移:舊存檔死填充 nimble_fingers/deft_hands → ensure 後清除退 pending
    gd, c = _char(security=100)
    c.mastery_choices = {"security_50": "nimble_fingers", "security_100": "deft_hands"}
    progression.ensure_mastery_choices(c, gd)
    assert "security_50" not in c.mastery_choices and "security_100" not in c.mastery_choices
    pend = {n["id"] for n in mastery.pending_choices(c, gd)}
    assert "security_50" in pend and "security_100" in pend


def test_mercantile_and_intimidate():
    gd, c = _char(mercantile=50)
    mastery.choose(c, gd, "mercantile_50", "haggler")
    assert mastery.merchant_bonus(c, gd) == 0.12
    gd2, c2 = _char(mercantile=50)
    mastery.choose(c2, gd2, "mercantile_50", "investor")
    assert mastery.restock_mult(c2, gd2) == 1.5
    # R38:威嚇下限移至 speechcraft 50(war_cry 0.30)+ 75(iron_presence 0.45),MAX 聚合成長線
    gd3, c3 = _char(speechcraft=100)
    foes = [combat.spawn_creature(gd3, "bandit", RNG(1)) for _ in range(3)]
    mastery.choose(c3, gd3, "speechcraft_50", "war_cry")
    assert dialogue.intimidate_chance(c3, foes, False, gd3) >= 0.30   # war_cry 下限 0.30
    mastery.choose(c3, gd3, "speechcraft_75", "iron_presence")
    assert mastery.intimidate_floor(c3, gd3) == 0.45                  # 50+75 取最(MAX 聚合)
    assert dialogue.intimidate_chance(c3, foes, False, gd3) >= 0.45


# --- 廣度 pass:17 薄技能各 +1 節點 + 4 新 kind + 2 getter 微修 -------------------
def test_breadth_all_skills_have_full_ladder():
    """補齊階梯:全 22 技能各 4 節點(25/50/75/100);共 88 節點(護甲修理移除後)。"""
    from collections import Counter
    gd = get_gamedata()
    nodes = mastery._nodes(gd)
    cnt = Counter(n["skill"] for n in nodes)
    assert len(cnt) == 22 and all(v == 4 for v in cnt.values())
    assert len(nodes) == 88
    # 每技能門檻恰為 {25,50,75,100}
    thr = {}
    for n in nodes:
        thr.setdefault(n["skill"], set()).add(n["threshold"])
    assert all(t == {25, 50, 75, 100} for t in thr.values())


def test_batch3_all_25_are_single_auto_grant_no_dead():
    """21 個新 25 節點皆單一 perk(自動授予退化節點),無死 perk。"""
    gd = get_gamedata()
    t25 = [n for n in mastery._nodes(gd) if n["threshold"] == 25]
    assert len(t25) == 22                                    # sneak + 21
    assert all(len(mastery._choosable_options(n)) == 1 for n in t25)   # 全單一 → 自動授予
    defids = {o["opt_id"] for o in mastery._defs(gd)}
    for n in t25:
        for o in n["options"]:
            assert o["opt_id"] in defids, f"死 perk {n['id']} {o['opt_id']}"


# --- 補頂點 pass(Batch 1):14 個 100 級 capstone ---------------------------
def test_batch1_same_source_aggregation_no_shadow():
    """同源多節點不遮蔽:temper/lock 取最高、evasion/passive_armor/poison 相加、weapon_mod 合併、spell power 相加。"""
    gd, c = _char(smithing=100, security=100, acrobatics=100, hand_to_hand=100,
                  alchemy=100, restoration=100, heavy_armor=100, block=100)
    mastery.choose(c, gd, "smithing_75", "efficient"); mastery.choose(c, gd, "smithing_100", "legendary_smith")
    assert mastery.temper_free_chance(c, gd) == 0.50                     # max(0.30,0.50)
    mastery.choose(c, gd, "security_75", "master_floor"); mastery.choose(c, gd, "security_100", "master_thief")
    assert mastery.lock_floor(c, gd) == 0.50                            # max(0.30,0.50)
    mastery.choose(c, gd, "acrobatics_50", "tumbler"); mastery.choose(c, gd, "acrobatics_75", "evasion")
    assert abs(mastery.evasion_bonus(c, gd) - (0.04 + 0.05)) < 1e-9   # 同源相加不遮蔽(acrobatics 50+75)
    mastery.choose(c, gd, "hand_to_hand_75", "iron_fists"); mastery.choose(c, gd, "hand_to_hand_100", "transcend_fist")
    assert abs(mastery.weapon_mod(c, gd, "hand_to_hand").get("power", 0) - (0.15 + 0.10)) < 1e-9  # weapon_mod 合併
    mastery.choose(c, gd, "alchemy_50", "toxin_master"); mastery.choose(c, gd, "alchemy_100", "venom_lord")
    assert mastery.poison_unlocks(c, gd) == {"weaken", "fear"}          # 多節點 union 不遮蔽(R31)
    mastery.choose(c, gd, "heavy_armor_100", "ironhide"); mastery.choose(c, gd, "block_75", "bracing")
    mastery.choose(c, gd, "block_100", "iron_bastion")
    assert mastery.passive_armor_bonus(c, gd) == 18 + 10 + 12          # 跨技能相加(heavy+block 三節點;R35 後輕甲弱邊已改閃避)
    mastery.choose(c, gd, "restoration_100", "divine_grace")
    assert mastery.spell_power_bonus(c, gd, "restoration") == 0.20     # 治療登峰流入 _power


def test_batch1_evasion_bonus_capped():
    """雜技/運動/輕甲三源閃避相加夾 EVASION_BONUS_CAP(對抗審查:0.24 會 trivialize 群戰)。"""
    gd, c = _char(acrobatics=100, athletics=100, scout=100)
    for nid, oid in [("acrobatics_50", "tumbler"), ("acrobatics_75", "evasion"),
                     ("athletics_100", "windstep"), ("scout_75", "preempt")]:
        mastery.choose(c, gd, nid, oid)
    raw = 0.04 + 0.05 + 0.05 + 0.04                         # 0.18 未夾
    assert raw > mastery.EVASION_BONUS_CAP
    assert mastery.evasion_bonus(c, gd) == mastery.EVASION_BONUS_CAP   # 夾 0.15


def test_cold_skill_identity_perks():
    """冷技能身份化(檔A):弓手散兵戰技(里程碑解鎖)/盾擊宗師(block_riposte 聚合)/輕甲游擊·雜技(on_evade 聚合)。"""
    gd, c = _char(marksman=100, block=100, light_armor=100, acrobatics=100)
    # 弓手散兵戰技(R40:由「裝弓即免費」改為 marksman 里程碑解鎖):牽制射(50)+ 瞄準射(75)
    mastery.choose(c, gd, "marksman_50", "crippling_shot")
    assert mastery.has_bow_technique(c, gd, "crippling")
    mastery.choose(c, gd, "marksman_75", "aimed_shot")
    assert mastery.has_bow_technique(c, gd, "aimed")
    # 盾擊宗師:block_riposte 多節點聚合(踉蹌取最 + 削弱 + 反傷)
    for nid, oid in [("block_50", "shield_bash"), ("block_75", "shield_break"), ("block_100", "perfect_block")]:
        mastery.choose(c, gd, nid, oid)
    rp = mastery.block_riposte(c, gd)
    assert rp["stagger_chance"] == 0.40 and rp["weaken"] == 0.15 and rp["counter"] == 0.5
    # 輕甲游擊 + 雜技:on_evade 聚合(反擊取最、踉蹌任一、回體相加夾上限)
    for nid, oid in [("light_armor_50", "riposte_step"), ("light_armor_100", "storm_dance"),
                     ("acrobatics_100", "aerial_ambush")]:
        mastery.choose(c, gd, nid, oid)
    oe = mastery.on_evade(c, gd)
    assert oe["counter_chance"] == 0.6 and oe["counter_frac"] == 0.6 and oe["counter_stagger"] is True
    assert oe["restamina"] == 10                           # aerial_ambush 10(尚未疊 fluid_motion)
    mastery.choose(c, gd, "light_armor_75", "fluid_motion")   # +8 → 18 夾 ON_EVADE_RESTAMINA_CAP
    assert mastery.on_evade(c, gd)["restamina"] == mastery.ON_EVADE_RESTAMINA_CAP


def test_dedup_nobrainer_wave():
    """R35 去冗餘/修 no-brainer 波次:純複用既有 kind、零新存檔欄。
    (1) acrobatics_100 修 R34 自製 no-brainer:deft_roll(vanish_floor 與 75 tumble 完全重複的死選項)
        → whirl_riposte(on_evade 反擊)→ 100 變「回體流 aerial_ambush vs 反擊流 whirl_riposte」真二選一。
    (2) light_armor 棄 passive_armor 填充 → 閃避流(evasion)vs 反擊流(on_evade)雙路線。
    (3) scout_50 去 skill_fortify 填充 → threat_read(見 test_scout_prep_and_recon)。"""
    # (1) acrobatics_100 兩選項現為功能互異的 evasion(閃避流)vs on_evade(回體流);**對抗審查教訓**:
    #     原 whirl_riposte 用 on_evade-counter(MAX 聚合)→ 被 light_armor_100 storm_dance(0.6)完全遮蔽成
    #     「隱形陷阱」(同 deft_roll 被 75 tumble 遮蔽的老 no-brainer)→ 改 evasion_bonus(SUM 夾上限,永不被二元遮蔽)。
    gd, c = _char(acrobatics=100)
    mastery.choose(c, gd, "acrobatics_100", "wind_step")
    assert mastery.evasion_bonus(c, gd) == 0.06                           # 閃避流(雜技 capstone evasion)
    assert mastery.on_evade(c, gd) == {}                                  # 不再走 on_evade-counter → 無遮蔽風險
    gd, c = _char(acrobatics=100)
    mastery.choose(c, gd, "acrobatics_100", "aerial_ambush")
    assert mastery.on_evade(c, gd)["restamina"] == 10 and mastery.on_evade(c, gd)["counter_chance"] == 0.0  # 回體流(互異選擇)
    # **修真 bug 回歸**:wind_step + light_armor storm_dance → evasion 與 counter 各自獨立貢獻,非二元遮蔽
    gd, c = _char(acrobatics=100, light_armor=100)
    mastery.choose(c, gd, "acrobatics_100", "wind_step"); mastery.choose(c, gd, "light_armor_100", "storm_dance")
    assert mastery.evasion_bonus(c, gd) == 0.06                           # wind_step 閃避照常生效(storm_dance 不遮蔽)
    assert mastery.on_evade(c, gd)["counter_chance"] == 0.6               # storm_dance 反擊照常(各管各)
    # deft_roll 死選項已移除:acrobatics_100 不再有 vanish_floor(與 75 tumble 重複的 no-brainer 敗筆已消)
    gd, c = _char(acrobatics=100); mastery.choose(c, gd, "acrobatics_100", "aerial_ambush")
    assert mastery.vanish_floor(c, gd) == 0.0
    gd, c = _char(acrobatics=100); mastery.choose(c, gd, "acrobatics_75", "tumble")
    assert mastery.vanish_floor(c, gd) == 0.10                            # 雜技 vanish_floor 僅留 75 tumble(唯一來源,不重複)
    # (2) light_armor 弱邊改 evasion:50 lithe_evasion +0.05、100 phantom_step +0.06(同源相加,不再是 flat armor 填充)
    gd, c = _char(light_armor=100)
    mastery.choose(c, gd, "light_armor_50", "lithe_evasion"); mastery.choose(c, gd, "light_armor_100", "phantom_step")
    assert abs(mastery.evasion_bonus(c, gd) - (0.05 + 0.06)) < 1e-9
    assert mastery.passive_armor_bonus(c, gd) == 0                        # 輕甲 50/100 弱邊不再貢獻 passive_armor
    # 反擊流路線仍在(50 riposte_step + 100 storm_dance);與閃避流為二選一
    gd, c = _char(light_armor=100)
    mastery.choose(c, gd, "light_armor_50", "riposte_step"); mastery.choose(c, gd, "light_armor_100", "storm_dance")
    assert mastery.on_evade(c, gd)["counter_chance"] == 0.6
    assert mastery.evasion_bonus(c, gd) == 0.0                            # 走反擊流則無 evasion(真二選一,非兼得)


def test_cold_skill_combat_paths():
    """檔A 戰鬥路徑回歸(對抗審查抓到的真 bug):牽制箭 slow 帶 magnitude 不崩 initiative;on_evade 反制每回合至多一次。"""
    from tesrpg.rng import RNG
    from tesrpg.systems import combat
    # (1) slow 狀態必帶 magnitude → initiative_order→_speed→slow_factor 不崩(原 harrying_shot 回歸;
    #     R40 弓手牽制改 weaken·marksman slow 線移除後,改通用 slow 注入守 magnitude 讀取路徑)
    gd, c = _char(blade=100); c.weapon = "steel_sword"
    c.health = c.max_health = 500; c.fatigue = c.max_fatigue = 200
    foe = combat.spawn_creature(gd, "frost_troll", RNG(1)); foe.health = foe.max_health = 400
    foe.active_effects.append({"kind": "slow", "magnitude": 0.20, "turns": 99})
    c.active_effects.append({"kind": "slow", "magnitude": 0.20, "turns": 99})
    combat.auto_resolve(c, foe, gd, RNG(2), max_rounds=60)     # 不得拋例外(slow magnitude 讀取)
    # (2) on_evade 反制每回合至多一次:同一回合內(flag 未重置)連續多次敵攻落空只反制一次 → 不隨敵數線性放大
    gd, p = _char(light_armor=100, acrobatics=100, blade=100); p.weapon = "steel_sword"
    p.health = p.max_health = 600; p.fatigue = 50
    mastery.choose(p, gd, "light_armor_100", "storm_dance")    # counter 0.6/0.6
    e = combat.spawn_creature(gd, "bandit", RNG(3)); e.health = e.max_health = 99999
    p._evade_counter_used = False
    counters = 0
    for i in range(40):                                        # 模擬「同一回合」40 次敵攻(不重置 flag)
        if not combat.is_alive(p):
            break
        hp0 = e.health
        combat.resolve_attack(e, p, gd, RNG(8000 + i))
        if e.health < hp0:
            counters += 1
    assert counters <= 1, f"同回合 on_evade 反制應 ≤1,實得 {counters}"


def test_magic_school_no_brainer_fix():
    """🅑 砍法系『省魔恆勝』無腦選:alt/myst_50 改威力(吃 _power)、conj_50 改被動護甲、illusion 50/100 改懾意(fear 聚合夾 + solo 免疫)。"""
    from tesrpg.rng import RNG
    gd, c = _char(alteration=50, mysticism=50, conjuration=100, illusion=100)
    mastery.choose(c, gd, "alteration_50", "shield_focus")
    assert abs(mastery.spell_power_bonus(c, gd, "alteration") - 0.10) < 1e-9   # 護盾增幅(原意志+4 → 真功能)
    mastery.choose(c, gd, "mysticism_50", "ward_focus")
    assert abs(mastery.spell_power_bonus(c, gd, "mysticism") - 0.10) < 1e-9    # 結界增幅
    mastery.choose(c, gd, "conjuration_50", "warding_focus")
    mastery.choose(c, gd, "conjuration_75", "warding_summon")
    assert mastery.passive_armor_bonus(c, gd) == 8 + 15                        # 護體召喚 50+75 相加不遮蔽
    for nid, oid in [("illusion_50", "dread_touch"), ("illusion_75", "cowardice"), ("illusion_100", "soul_dread")]:
        mastery.choose(c, gd, nid, oid)
    foh = mastery.fear_on_hit(c, gd)
    assert foh["chance"] == mastery.FEAR_ON_HIT_CHANCE_CAP and foh["turns"] == 3   # chance 0.45→夾0.30;turns 取最=3(soul_dread)
    # solo BOSS 對 fear 免疫(R31 一致;補既有 cowardice 缺口)
    c.weapon = "steel_dagger"
    boss = combat.spawn_creature(gd, "mehrunes_dagon", RNG(1)); boss.health = boss.max_health = 99999
    feared = 0
    for s in range(40):
        boss.active_effects = []
        combat.resolve_attack(c, boss, gd, RNG(s))
        if any(e["kind"] == "fear" for e in boss.active_effects):
            feared += 1
    assert feared == 0, "solo boss 不得被 fear"


def test_capstone_apex_fix():
    """🅒 頂點 apex 化:6 capstone 弱 stat 邊 → 二 apex(passive_armor×3 相加 / potion_potency 聚合 / combat_regen / 重壓 stagger)。"""
    from tesrpg.rng import RNG
    gd, c = _char(hand_to_hand=100, alteration=100, mysticism=100, alchemy=100, restoration=100, heavy_armor=100)
    mastery.choose(c, gd, "hand_to_hand_100", "iron_shirt")
    mastery.choose(c, gd, "alteration_100", "mage_flesh")
    mastery.choose(c, gd, "mysticism_100", "spectral_aegis")
    assert mastery.passive_armor_bonus(c, gd) == 12 + 14 + 15          # 跨技能 passive_armor 相加不遮蔽
    mastery.choose(c, gd, "alchemy_75", "concentrated"); mastery.choose(c, gd, "alchemy_100", "panacea")
    assert abs(mastery.potion_potency(c, gd) - 0.35) < 1e-9            # 0.20+0.15 聚合(原單源)
    mastery.choose(c, gd, "restoration_100", "everflow")
    assert mastery.combat_regen(c, gd) == 8
    # 重壓:被近戰物理擊中 → 震開攻擊者;turns:2 須撐過回合末 tick,才在敵「下次出手」生效(非死時序)
    from tesrpg.systems import magic
    mastery.choose(c, gd, "heavy_armor_100", "crushing_bulk")
    c.weapon = "steel_sword"; c.health = c.max_health = 500
    landed = 0
    for i in range(120):
        foe = combat.spawn_creature(gd, "bandit", RNG(i)); foe.health = foe.max_health = 99999
        combat.resolve_attack(foe, c, gd, RNG(i))          # 敵攻玩家 → 可能震開敵
        if magic.is_staggered(foe):
            magic.tick_effects(foe, gd)                     # 回合末 tick(turns 2→1)
            if magic.is_staggered(foe):                     # 仍踉蹌 → 對敵下次攻擊生效
                landed += 1
    assert landed > 0, "重壓 stagger 須 turns:2 撐過回合末 tick,否則對敵下次出手永不生效(死 perk)"


# --- 補洞 pass(Batch 2):8 個 50/75 gap-fill ------------------------------
def test_batch2_gapfills_present_and_aggregate():
    """blade/blunt/marksman/speechcraft 補 75;四魔法學派補 50 → 全 23 技能 ≥3 節點(sneak 4)。"""
    from collections import Counter
    gd = get_gamedata()
    cnt = Counter(n["skill"] for n in mastery._nodes(gd))
    assert all(v >= 3 for v in cnt.values()) and cnt["sneak"] == 4
    defids = {o["opt_id"] for o in mastery._defs(gd)}
    for nid in ("blade_75", "blunt_75", "marksman_75", "speechcraft_75",
                "conjuration_50", "destruction_50", "illusion_50", "mysticism_50"):
        n = next(x for x in mastery._nodes(gd) if x["id"] == nid)
        for o in n["options"]:
            assert o["opt_id"] in defids, f"死 perk {nid} {o['opt_id']}"
    # spell_mod cost 聚合不遮蔽(destruction 75 省魔 × 100 過載加耗;省魔催動與共鳴一擊 50/75 互換後)
    gd, c = _char(destruction=100)
    mastery.choose(c, gd, "destruction_75", "efficient_destruction")
    mastery.choose(c, gd, "destruction_100", "overload")
    assert abs(mastery.spell_cost_factor(c, gd, "destruction") - 0.85 * 1.30) < 1e-9
    # weapon_mod blade 50/75/100 合併(不遮蔽)
    gd, c = _char(blade=100)
    mastery.choose(c, gd, "blade_75", "blade_flow"); mastery.choose(c, gd, "blade_100", "savage")
    assert abs(mastery.weapon_mod(c, gd, "blade").get("power", 0) - (0.08 + 0.12)) < 1e-9


def test_flee_bonus_getter_and_try_flee():
    gd, c = _char(athletics=75)
    assert mastery.flee_bonus(c, gd) == 0.0
    mastery.choose(c, gd, "athletics_75", "escape_artist")
    assert mastery.flee_bonus(c, gd) == 0.15
    foe = combat.spawn_creature(gd, "mudcrab", RNG(0))
    combat.try_flee(c, foe, RNG(0), gd)                          # 帶 gamedata 不崩


def test_armor_reflect_damages_attacker():
    gd, c = _char(heavy_armor=50)
    mastery.choose(c, gd, "heavy_armor_50", "armor_reflect")
    assert mastery.armor_reflect(c, gd) == 0.06            # R42:吃 raw 後重定 0.12→0.06
    c.health = c.max_health = 9999
    foe = combat.spawn_creature(gd, "bear", RNG(0)); foe.health = foe.max_health = 9999
    reflected = False
    for i in range(25):
        before = foe.health
        ev = combat.resolve_attack(foe, c, gd, RNG(i))          # 敵打玩家(物理)
        if ev["hit"] and ev["damage"] > 0 and foe.health < before:
            reflected = True
            break
        foe.health = 9999
    assert reflected                                            # 反彈傷害確實扣敵血


def test_trap_floor_floors_dodge():
    gd, c = _char(security=50)
    assert mastery.trap_floor(c, gd) == 0.0
    mastery.choose(c, gd, "security_50", "trapwise")
    assert mastery.trap_floor(c, gd) == 0.30


def test_weapon_mod_merges_same_target():
    """blade_50 + blade_100 同 target → 合併(不遮蔽);審查級正確性。"""
    gd, c = _char(blade=100)
    mastery.choose(c, gd, "blade_50", "keen_edge")              # hit 0.05
    mastery.choose(c, gd, "blade_100", "precision")             # hit 0.05
    wm = mastery.weapon_mod(c, gd, "blade")
    assert abs(wm.get("hit", 0) - 0.10) < 1e-9


def test_smithing_50_options_replaced():
    """R37 功能化:smithing_50 = 工匠(thrifty_forge 省料 0.20)vs 鋒銳(temper_edge temper_power 0.10);
    死填充 smith_arm(鈍器 fortify)已移除。"""
    gd, c = _char(smithing=50)
    mastery.choose(c, gd, "smithing_50", "thrifty_forge")
    assert mastery.temper_free_chance(c, gd) >= 0.20 and mastery.temper_power(c, gd) == 0.0
    _, c2 = _char(smithing=50)
    mastery.choose(c2, gd, "smithing_50", "temper_edge")
    assert mastery.temper_power(c2, gd) == 0.10 and mastery.temper_free_chance(c2, gd) == 0.0   # 二選一:選鋒銳則無省料


def test_temper_power_aggregates_and_applies():
    """R37 鋒銳:temper_power 多節點相加(50 0.10 + 100 0.15 = 0.25)+ 套進 weapon/armor_temper_bonus ×(1+power)。"""
    from tesrpg.systems import smithing
    assert "temper_power" in mastery._IMPLEMENTED_KINDS
    gd, c = _char(smithing=100)
    inventory.add_item(c, "steel_sword", 1); inventory.equip_weapon(c, gd, "steel_sword")
    inventory.add_item(c, "steel_ingot", 20)
    for _ in range(5):                                          # 淬至上限(cap 5 @ smithing 100)→ flat = 5×2 = 10
        smithing.temper(c, gd, "steel_sword")
    flat0 = smithing.weapon_temper_bonus(c, gd)
    assert mastery.temper_power(c, gd) == 0.0 and flat0 == 10    # 未選鋒銳 → factor 0
    mastery.choose(c, gd, "smithing_50", "temper_edge"); mastery.choose(c, gd, "smithing_100", "temper_mastery")
    assert abs(mastery.temper_power(c, gd) - 0.25) < 1e-9        # 50+100 相加
    assert smithing.weapon_temper_bonus(c, gd) == int(10 * 1.25)   # ×1.25 = 12(+2 鋒銳;floor)
    # 護甲側同套倍率
    inventory.add_item(c, "steel_cuirass", 1); inventory.equip_armor(c, gd, "steel_cuirass")
    inventory.add_item(c, "steel_ingot", 20)
    for _ in range(5):
        smithing.temper(c, gd, "steel_cuirass")
    worn = set(c.equipped.values())
    aflat = sum(lvl for iid, lvl in c.armor_temper.items() if iid in worn) * smithing.TEMPER_ARMOR_PER
    assert smithing.armor_temper_bonus(c, gd) == int(aflat * 1.25)


def test_same_source_masking_fixed_spell_poison_evasion_passive():
    """對抗審查修正:廣度 pass 使多 getter 出現同源多節點 → 須聚合不遮蔽。"""
    # spell_mod:alteration_50 efficient_shield(cost 0.85)+ alteration_75 spell_reach(power 0.15)同時生效
    gd, c = _char(alteration=100)
    mastery.choose(c, gd, "alteration_50", "efficient_shield")
    mastery.choose(c, gd, "alteration_75", "spell_reach")
    assert abs(mastery.spell_cost_factor(c, gd, "alteration") - 0.85) < 1e-9
    assert abs(mastery.spell_power_bonus(c, gd, "alteration") - 0.15) < 1e-9
    # poison_unlock:alchemy_50(weaken)+ alchemy_75(slow,+1延長)→ union 不遮蔽(R31)
    gd2, c2 = _char(alchemy=100)
    mastery.choose(c2, gd2, "alchemy_50", "toxin_master")
    mastery.choose(c2, gd2, "alchemy_75", "potent_poison")
    assert mastery.poison_unlocks(c2, gd2) == {"weaken", "slow"}
    assert mastery.poison_duration_bonus(c2, gd2) == 1
    # evasion:acrobatics_50(0.04)+ acrobatics_75(0.05)= 0.09
    gd3, c3 = _char(acrobatics=100)
    mastery.choose(c3, gd3, "acrobatics_50", "tumbler")
    mastery.choose(c3, gd3, "acrobatics_75", "evasion")
    assert abs(mastery.evasion_bonus(c3, gd3) - 0.09) < 1e-9
    # 行為面(併自 test_acrobatics_evasion_lowers_enemy_hit):evasion_bonus 真的降低敵命中(resolve_attack 整合)
    foe = combat.spawn_creature(gd3, "bandit", RNG(1)); foe.attack["skill"] = 60
    hits_with = sum(combat.resolve_attack(foe, c3, gd3, RNG(s))["hit"] for s in range(200))
    gd0, c0 = _char(acrobatics=100)                       # 同 base、未選閃避 → 對照
    hits_without = sum(combat.resolve_attack(foe, c0, gd0, RNG(s))["hit"] for s in range(200))
    assert hits_with < hits_without
    # passive_armor:block_75 bracing(10)+ block_100 iron_bastion(12)= 22(相加不遮蔽)
    gd4, c4 = _char(block=100)
    mastery.choose(c4, gd4, "block_75", "bracing")
    mastery.choose(c4, gd4, "block_100", "iron_bastion")
    assert mastery.passive_armor_bonus(c4, gd4) == 22


def test_illusion_mind_mastery_reduces_cost():
    """對抗審查修正:illusion_100 改 mind_mastery(走 live spell_cost_factor),非死碼 on_hit。"""
    gd, c = _char(illusion=100)
    mastery.choose(c, gd, "illusion_100", "mind_mastery")
    assert abs(mastery.spell_cost_factor(c, gd, "illusion") - 0.85) < 1e-9


def test_shipped_attr_fortify_node_flows_to_resources():
    gd, c = _char(athletics=75)
    base_end = c.attr("endurance")
    base_fat = c.max_fatigue
    mastery.choose(c, gd, "athletics_75", "enduring")           # attr endurance +5(choose 內已重算)
    assert c.attr("endurance") == base_end + 5
    assert c.base_attr("endurance") == base_end                # base 不動(鐵律)
    assert c.max_fatigue > base_fat                            # 耐力 → 體力上限提升


def run():
    test_threshold_uses_base_skill_only()
    test_creatures_have_no_mastery()
    test_two_option_choice_plumbing()
    test_block_reflect_returns_damage_and_costs_fatigue()
    test_empower_diminishing_stack_curve()
    test_bulwark_reduces_physical_and_costs_fatigue()
    test_bulwark_does_not_reduce_elemental()
    test_overheal_ward_converts_overflow_and_caps()
    test_overheal_ward_aggregate_cap_across_casts()
    test_overload_raises_cost_and_power_destruction_only()
    test_lock_floor_only_raises_never_lowers()
    test_charm_guarantees_once_per_npc()
    test_choice_ready_event_fires_exactly_once_across_multilevel()
    test_mastery_choices_roundtrip_and_backward_compat()
    test_persuaded_npcs_roundtrip_and_backward_compat()
    test_pending_choice_derivation_backcompat()
    test_ensure_mastery_choices_prunes_stale()
    test_relocated_group_resets_together()
    test_shipped_kinds_all_implemented()
    test_unimplemented_kind_is_inert()
    test_mastery_never_writes_base_skill()
    test_next_threshold_hint_uses_base_and_skips_done()
    test_skill_fortify_stacks_effective_not_base()
    test_fortify_does_not_bootstrap_threshold()
    test_recompute_mastery_idempotent()
    test_weapon_mod_target_matches_weapon_skill()
    test_weapon_mod_power_increases_damage_with_recoil()
    test_blunt_pen_increases_damage_vs_armor()
    test_blunt_concussion_weakens_enemy()
    test_block_riposte_staggers_attacker()
    test_heavy_armor_unyielding_resist()
    test_smithing_temper_cap_and_free()
    test_athletics_travel_and_fatigue()
    test_destruction_impact_staggers_on_hit()
    test_conjuration_summon_mods()
    test_alteration_stoneflesh_passive_armor()
    test_alchemy_potion_potency_and_poison_unlocks()
    test_mysticism_enchant_potency_and_absorb()
    test_illusion_fear_on_hit_and_merchant()
    test_restoration_steadfast_regen_on_low()
    test_horde_penalty_crushes_stealth_above_three()
    test_solo_boss_survives_apex_opener()
    test_sneak_mult_bonus_raises_sneak_damage()
    test_vanish_relentless_removes_reuse_decay_but_not_horde()
    test_vanish_floor_takes_max_across_sources()
    test_merchant_bonus_sums_across_sources()
    test_sneak_approach_and_armor_relief()
    test_scout_prep_and_recon()
    test_has_recon_perk()
    test_security_pick_no_break()
    test_security_theft_and_casing()
    test_breadth_all_skills_have_full_ladder()
    test_batch1_same_source_aggregation_no_shadow()
    test_batch1_evasion_bonus_capped()
    test_cold_skill_identity_perks()
    test_cold_skill_combat_paths()
    test_magic_school_no_brainer_fix()
    test_capstone_apex_fix()
    test_batch2_gapfills_present_and_aggregate()
    test_batch3_all_25_are_single_auto_grant_no_dead()
    test_flee_bonus_getter_and_try_flee()
    test_armor_reflect_damages_attacker()
    test_trap_floor_floors_dodge()
    test_weapon_mod_merges_same_target()
    test_smithing_50_options_replaced()
    test_temper_power_aggregates_and_applies()
    test_same_source_masking_fixed_spell_poison_evasion_passive()
    test_illusion_mind_mastery_reduces_cost()
    test_shipped_attr_fortify_node_flows_to_resources()
    test_mercantile_and_intimidate()


if __name__ == "__main__":
    run()
    print("test_mastery 全通過")
