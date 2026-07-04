"""戴德拉誓福引擎 + 神殿任務(R45)回歸測試:
- 通用誓福獨立疊加層(grant/聚合/多誓福相加/不污染 base/存檔 round-trip/舊檔遷移);
- reward.grant_boon 派發(新 boons 登錄表 vs 達貢 legacy 各走各的);
- 神殿任務可接門檻(requires_level/requires_fame)+ 神殿(shrine)分流;
- 首位親王阿祖拉深線雙結局(淨化→永久誓福 / 墮化→神器)+ 內容資料完整(boss solo/控場節制/地城有任務)。
"""
from tesrpg import formulas
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.systems import boons, inventory, magic, quests


def _gd_char(level: int = 1):
    gd = get_gamedata()
    c = build_character(gd, name="試", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    c.level = level
    return gd, c


# --- 通用誓福永久層 ----------------------------------------------------
def test_boon_layer_stacks_without_base_write():
    gd, c = _gd_char()
    w0, i0, mg0 = c.attr("willpower"), c.attr("intelligence"), c.max_magicka
    myst0 = c.skill("mysticism")
    wmr0 = formulas.willpower_magic_resist(c.attr("willpower"))   # R65 意志魔抗(誓福抬意志 → 連帶增)
    magres0 = magic.entity_resist(c, gd).get("magic", 0)
    boons.grant(c, gd, "azura")
    assert c.attr("willpower") == w0 + 8 and c.attr("intelligence") == i0 + 6
    assert c.skill("mysticism") == myst0 + 10
    # max_magicka 升幅 = 智力 +6 的公式貢獻 + 誓福固定 +20(故 ≥ +20)
    assert c.boon_magic_bonus == 20 and c.max_magicka >= mg0 + 20
    # 魔抗升幅 = 誓福直接 +20 + 意志 +8 連帶的 R65 意志魔抗增量
    wmr1 = formulas.willpower_magic_resist(c.attr("willpower"))
    assert magic.entity_resist(c, gd).get("magic", 0) == magres0 + 20 + (wmr1 - wmr0)
    # 🔴 鐵律:絕不寫回 base
    assert c.base_attr("willpower") == w0 and c.base_skill("mysticism") == myst0
    assert boons.has_boon(c, "azura")


def test_boon_grant_is_idempotent_no_double():
    gd, c = _gd_char()
    w0 = c.attr("willpower")
    boons.grant(c, gd, "azura")
    boons.grant(c, gd, "azura")          # 重複授予不疊加
    assert c.boons.count("azura") == 1
    assert c.attr("willpower") == w0 + 8


def test_multiple_boons_sum():
    """收集軸:同時持有多位親王的誓福 → 各自相加(注入暫時測試誓福驗證聚合)。"""
    gd, c = _gd_char()
    w0, mg0 = c.attr("willpower"), c.max_magicka
    gd.boons["_test_boon"] = {"name": "測試", "attr": {"willpower": 3},
                              "skill": {}, "resist": {}, "magicka": 5}
    try:
        boons.grant(c, gd, "azura")
        boons.grant(c, gd, "_test_boon")
        assert c.attr("willpower") == w0 + 8 + 3              # 屬性相加
        assert c.boon_magic_bonus == 20 + 5                  # 固定魔力上限相加
        assert c.max_magicka >= mg0 + 25                     # (另含智力 +6 的公式貢獻)
    finally:
        gd.boons.pop("_test_boon", None)


def test_boon_save_roundtrip_and_migration():
    gd, c = _gd_char()
    boons.grant(c, gd, "azura")
    w = c.attr("willpower")
    c2 = Character.from_dict(c.to_dict())
    boons.ensure_boon_fields(c2, gd)
    assert boons.has_boon(c2, "azura") and c2.attr("willpower") == w
    # 舊存檔(無 boon_* 欄)→ 遷移補欄為空、零加成
    d = c.to_dict()
    for k in [k for k in list(d) if k.startswith("boon")]:
        del d[k]
    c3 = Character.from_dict(d)
    boons.ensure_boon_fields(c3, gd)
    assert c3.boons == [] and c3.boon_attr_bonus == {} and c3.boon_magic_bonus == 0


def test_unknown_boon_id_skipped():
    """陳舊/毀損存檔殘留未知 boon id → 靜默略過,不崩。"""
    gd, c = _gd_char()
    c.boons = ["azura", "_no_such_boon"]
    boons.apply_to_character(c, gd)                 # 不應拋例外
    assert c.boon_attr_bonus.get("willpower") == 8   # 已知者照算


# --- reward.grant_boon 派發 -------------------------------------------
def test_reward_dispatch_grants_registry_boon():
    """完成 azura_star(淨化結局)→ reward.grant_boon=azura 經通用 boons 登錄表授予。"""
    gd, c = _gd_char(level=15)
    w0 = c.attr("willpower")
    quests.accept_quest(c, gd, "azura_star", branch=0)
    inventory.add_item(c, "nightshade", 2)
    c.location_id = "azura_defiled_shrine"
    quests.record_dungeon_clear(c, "azura_defiled_shrine")
    quests.check_completion(c, gd)
    assert "azura_star" in c.completed_quests
    assert boons.has_boon(c, "azura") and c.attr("willpower") == w0 + 8
    assert "azura_star_cleansed" in c.world_events_fired


def test_corrupt_branch_grants_artifact_not_boon():
    """墮化結局 → 得神器黑星護符、不得誓福、惡名上升。"""
    gd, c = _gd_char(level=15)
    quests.accept_quest(c, gd, "azura_star", branch=1)
    inventory.add_item(c, "empty_black_soul_gem", 1)
    c.location_id = "azura_defiled_shrine"
    quests.record_dungeon_clear(c, "azura_defiled_shrine")
    quests.check_completion(c, gd)
    assert "azura_star" in c.completed_quests
    assert inventory.count_item(c, "black_star_amulet") == 1
    assert not boons.has_boon(c, "azura") and c.infamy >= 25


# --- 神殿任務可接門檻 / 分流 ------------------------------------------
def test_daedric_quest_availability_gating():
    gd, c = _gd_char(level=10)
    assert "azura_star" not in quests.available_quests(c, gd, "daedric")   # 等級不足不現
    c.level = 15
    av = quests.available_quests(c, gd, "daedric")
    assert "azura_star" in av
    # 神殿分流:任務帶 shrine="azura"(action_shrine 以此篩到對應祭壇)
    assert gd.quests["azura_star"]["shrine"] == "azura"
    # 接取後不再列出(避免重複接);完成後亦然
    quests.accept_quest(c, gd, "azura_star", branch=0)
    assert "azura_star" not in quests.available_quests(c, gd, "daedric")


def test_requires_fame_gate_backcompat():
    """requires_fame 門檻向後相容(無此欄=不限);其他既有任務不受新門檻影響。"""
    gd, c = _gd_char(level=15)
    # azura_star 無 requires_fame → fame 0 仍可見
    assert "azura_star" in quests.available_quests(c, gd, "daedric")


# --- 內容資料完整 ------------------------------------------------------
def test_azura_content_integrity():
    gd, _ = _gd_char()
    # boon 登錄 + 神器存在
    assert "azura" in gd.boons
    assert "black_star_amulet" in gd.items
    # 神殿地點帶 shrine 標記 + 新地城存在且為 boss 龍頭
    assert gd.world["locations"]["azuras_coast"].get("shrine") == "azura"
    assert "azura_defiled_shrine" in gd.dungeons
    assert "azura_defiled_shrine" in gd.world["locations"]
    boss = gd.dungeons["azura_defiled_shrine"]["boss"]["enemy"]
    assert boss == "malyn_varen" and gd.bestiary[boss].get("solo") is True
    # boss 控場節制:硬控 chance ≤ 0.30、turns ≤ 1(R43/R44 內容紀律)
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("paralyze", "fear", "stagger"):
            assert oh.get("chance", 1.0) <= 0.30, atk
            if oh.get("status") in ("paralyze", "fear"):
                assert oh.get("turns", 1) <= 1, atk
    # 地城怪皆存在
    for m in gd.dungeons["azura_defiled_shrine"]["monsters"]:
        assert m in gd.bestiary, m
    # 每地城有對應 clear_dungeon 任務(test_polish/test_detailing 同精神)
    cleared = set()
    for q in gd.quests.values():
        objs = ([q["objective"]] if "objective" in q else [])
        for s in q.get("stages", []):
            objs.append(s.get("objective", {}))
        for b in q.get("branches", []):
            for s in b.get("stages", []):
                objs.append(s.get("objective", {}))
        for o in objs:
            if o.get("type") == "clear_dungeon":
                cleared.add(o["dungeon"])
    assert "azura_defiled_shrine" in cleared


# --- 第二位親王:莫拉格巴爾(serve→神器 vs defy→誓福,翻轉道德軸)----------
def test_molag_serve_branch_grants_mace_not_boon():
    """臣服之路 → 得神器 莫拉格巴爾之鎚、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=16)
    quests.accept_quest(c, gd, "molag_bal_vault", branch=0)
    inventory.add_item(c, "filled_common_soul_gem", 1)
    c.location_id = "molag_vault"
    quests.record_dungeon_clear(c, "molag_vault")
    quests.check_completion(c, gd)
    assert "molag_bal_vault" in c.completed_quests
    assert inventory.count_item(c, "mace_of_molag_bal") == 1
    assert not boons.has_boon(c, "molag_defiance") and c.infamy >= 30
    assert "molag_bal_served" in c.world_events_fired


def test_molag_defy_branch_grants_boon_not_mace():
    """反抗之路 → 得永久誓福 不屈之心(willpower+10/endurance+6)、不得神器、聲望上升。"""
    gd, c = _gd_char(level=16)
    w0, e0 = c.attr("willpower"), c.attr("endurance")
    quests.accept_quest(c, gd, "molag_bal_vault", branch=1)
    inventory.add_item(c, "filled_common_soul_gem", 1)
    c.location_id = "molag_vault"
    quests.record_dungeon_clear(c, "molag_vault")
    quests.check_completion(c, gd)
    assert "molag_bal_vault" in c.completed_quests
    assert boons.has_boon(c, "molag_defiance")
    assert c.attr("willpower") == w0 + 10 and c.attr("endurance") == e0 + 6
    assert c.base_attr("willpower") == w0          # 🔴 不寫 base
    assert inventory.count_item(c, "mace_of_molag_bal") == 0
    assert "molag_bal_defied" in c.world_events_fired


def test_molag_quest_availability_gating():
    gd, c = _gd_char(level=15)
    assert "molag_bal_vault" not in quests.available_quests(c, gd, "daedric")   # 等級不足
    c.level = 16
    av = quests.available_quests(c, gd, "daedric")
    assert "molag_bal_vault" in av and "azura_star" in av                       # 兩座神殿任務並存
    assert gd.quests["molag_bal_vault"]["shrine"] == "molag_bal"                # 神殿分流


def test_molag_content_integrity():
    gd, _ = _gd_char()
    assert "molag_defiance" in gd.boons and "mace_of_molag_bal" in gd.items
    assert gd.world["locations"]["molag_mar"].get("shrine") == "molag_bal"
    boss = gd.dungeons["molag_vault"]["boss"]["enemy"]
    assert boss == "molag_bloodlord" and gd.bestiary[boss].get("solo") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # 神器走既有 absorb_health 路徑(weapon_status),非新 combat kind
    ench = gd.items["mace_of_molag_bal"]["enchant"]
    assert ench["kind"] == "weapon_status" and ench["status"] == "absorb_health"
    # 誓福守紅線:無 sneak/武器技能
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["molag_defiance"].get("skill", {})))


# --- 第三位親王:海爾辛(hunt→誓福 vs claim→神器)----------------------
def _complete_hircine(gd, c, branch):
    quests.accept_quest(c, gd, "hircine_hunt", branch=branch)
    c.kill_counts["wolf"] = c.kill_counts.get("wolf", 0) + 3   # 初獵之血(kill 階段)
    c.location_id = "moonlit_grove"
    quests.record_dungeon_clear(c, "moonlit_grove")
    quests.check_completion(c, gd)


def test_hircine_hunt_branch_grants_boon_not_hide():
    """狩成之路 → 永久誓福 獵者之佑(agility+10/speed+6/light_armor+8)、不得神器。"""
    gd, c = _gd_char(level=16)
    a0, sp0, la0 = c.attr("agility"), c.attr("speed"), c.skill("light_armor")
    _complete_hircine(gd, c, 0)
    assert "hircine_hunt" in c.completed_quests
    assert boons.has_boon(c, "hircine_blessing")
    assert c.attr("agility") == a0 + 10 and c.attr("speed") == sp0 + 6
    assert c.skill("light_armor") == la0 + 8
    assert c.base_attr("agility") == a0          # 🔴 不寫 base
    assert inventory.count_item(c, "saviors_hide") == 0
    assert "hircine_hunt_completed" in c.world_events_fired


def test_hircine_claim_branch_grants_hide_not_boon():
    """奪皮之路 → 得神器 救主之皮(輕甲·魔抗)、不得誓福。"""
    gd, c = _gd_char(level=16)
    _complete_hircine(gd, c, 1)
    assert "hircine_hunt" in c.completed_quests
    assert inventory.count_item(c, "saviors_hide") == 1
    assert not boons.has_boon(c, "hircine_blessing")
    assert "hircine_hide_claimed" in c.world_events_fired


def test_hircine_availability_and_three_shrines_coexist():
    gd, c = _gd_char(level=15)
    assert "hircine_hunt" not in quests.available_quests(c, gd, "daedric")   # 等級不足
    c.level = 16
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt"} <= set(av)        # 三座神殿任務並存
    assert gd.quests["hircine_hunt"]["shrine"] == "hircine"


def test_hircine_content_integrity():
    gd, _ = _gd_char()
    assert "hircine_blessing" in gd.boons and "saviors_hide" in gd.items
    assert gd.world["locations"]["grahtwood"].get("shrine") == "hircine"
    boss = gd.dungeons["moonlit_grove"]["boss"]["enemy"]
    assert boss == "blood_moon_beast" and gd.bestiary[boss].get("solo") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Savior's Hide 為輕甲·魔抗,且僅任務 reward(不漏進地城寶藏 → 分支抉擇有意義)
    hide = gd.items["saviors_hide"]
    assert hide["weight_class"] == "light" and hide["enchant"]["element"] == "magic"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "saviors_hide" not in tl + dd.get("loot", [])
    # 誓福守紅線:無 sneak/武器技能(agility/speed/light_armor 安全)
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["hircine_blessing"].get("skill", {})))


# --- 第四位親王:波耶西亞(prove→神器烏木甲 vs refuse→誓福)--------------
def _complete_boethiah(gd, c, branch):
    quests.accept_quest(c, gd, "boethiah_calling", branch=branch)
    c.kill_counts["bandit"] = c.kill_counts.get("bandit", 0) + 3   # 血債(kill 階段)
    c.location_id = "boethiah_proving"
    quests.record_dungeon_clear(c, "boethiah_proving")
    quests.check_completion(c, gd)


def test_boethiah_prove_branch_grants_mail_not_boon():
    """試煉之路 → 得神器 烏木甲(荊棘反傷)、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=17)
    _complete_boethiah(gd, c, 0)
    assert "boethiah_calling" in c.completed_quests
    assert inventory.count_item(c, "ebony_mail") == 1
    assert not boons.has_boon(c, "boethiah_resolve") and c.infamy >= 30
    assert "boethiah_champion_won" in c.world_events_fired


def test_ebony_mail_thorns_reflect_active_when_worn():
    """烏木甲穿戴 → inventory.thorns_reflect 反映 8% 反傷(R42 反傷流)。"""
    gd, c = _gd_char(level=17)
    r0 = inventory.thorns_reflect(c, gd)
    _complete_boethiah(gd, c, 0)
    inventory.equip_armor(c, gd, "ebony_mail")
    r1 = inventory.thorns_reflect(c, gd)
    assert abs((r1 - r0) - 0.08) < 1e-9, (r0, r1)   # +8% 反傷


def test_boethiah_refuse_branch_grants_boon_not_mail():
    """拒血之路 → 永久誓福 弒逆之志(endurance+10/heavy_armor+10)、不得神器。"""
    gd, c = _gd_char(level=17)
    e0, ha0 = c.attr("endurance"), c.skill("heavy_armor")
    _complete_boethiah(gd, c, 1)
    assert boons.has_boon(c, "boethiah_resolve")
    assert c.attr("endurance") == e0 + 10 and c.skill("heavy_armor") == ha0 + 10
    assert c.base_attr("endurance") == e0          # 🔴 不寫 base
    assert inventory.count_item(c, "ebony_mail") == 0
    assert "boethiah_defied" in c.world_events_fired


def test_boethiah_availability_and_four_shrines_coexist():
    gd, c = _gd_char(level=16)
    assert "boethiah_calling" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 17)
    c.level = 17
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling"} <= set(av)
    assert gd.quests["boethiah_calling"]["shrine"] == "boethiah"


def test_boethiah_content_integrity():
    gd, _ = _gd_char()
    assert "boethiah_resolve" in gd.boons and "ebony_mail" in gd.items
    assert gd.world["locations"]["falkreath_wood"].get("shrine") == "boethiah"
    boss = gd.dungeons["boethiah_proving"]["boss"]["enemy"]
    assert boss == "boethiah_champion" and gd.bestiary[boss].get("solo") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # 烏木甲:重甲·荊棘反傷·無 material(守 test_every_material_has_full_set)·僅任務 reward
    em = gd.items["ebony_mail"]
    assert em["weight_class"] == "heavy" and em["enchant"]["kind"] == "thorns" and "material" not in em
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "ebony_mail" not in tl + dd.get("loot", [])
    # 誓福守紅線:無 sneak/武器技能(endurance/agility/heavy_armor 安全)
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["boethiah_resolve"].get("skill", {})))


# --- 第五位親王:克拉維克斯·瓦爾(社交軸;serve→Masque 神器 vs keep-word→誓福)--
def _complete_clavicus(gd, c, branch):
    quests.accept_quest(c, gd, "clavicus_bargain", branch=branch)
    inventory.add_item(c, "filled_greater_soul_gem", 1)   # 議價籌碼(collect 階段)
    c.location_id = "haemars_shame"
    quests.record_dungeon_clear(c, "haemars_shame")
    quests.check_completion(c, gd)


def test_clavicus_serve_branch_grants_masque_not_boon():
    """獻祭之路 → 得神器 克拉維克斯面具、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=17)
    _complete_clavicus(gd, c, 0)
    assert "clavicus_bargain" in c.completed_quests
    assert inventory.count_item(c, "masque_of_clavicus_vile") == 1
    assert not boons.has_boon(c, "clavicus_silver_tongue") and c.infamy >= 25
    assert "clavicus_masque_won" in c.world_events_fired


def test_masque_fortifies_speechcraft_when_worn():
    """克拉維克斯面具穿戴 → 口才技能 +25(社交軸 / fortify_skill 路徑)。"""
    from tesrpg.systems import stats
    gd, c = _gd_char(level=17)
    sp0 = c.skill("speechcraft")
    _complete_clavicus(gd, c, 0)
    inventory.equip_armor(c, gd, "masque_of_clavicus_vile")
    stats.recompute_equipment(c, gd)
    assert c.skill("speechcraft") == sp0 + 25
    assert c.base_skill("speechcraft") == sp0          # 🔴 裝備層不寫 base


def test_clavicus_keepword_branch_grants_boon_not_masque():
    """守諾之路 → 永久誓福 言靈之佑(personality+12/speechcraft+12)、不得神器。"""
    gd, c = _gd_char(level=17)
    p0, sp0 = c.attr("personality"), c.skill("speechcraft")
    _complete_clavicus(gd, c, 1)
    assert boons.has_boon(c, "clavicus_silver_tongue")
    assert c.attr("personality") == p0 + 12 and c.skill("speechcraft") == sp0 + 12
    assert c.base_attr("personality") == p0          # 🔴 不寫 base
    assert inventory.count_item(c, "masque_of_clavicus_vile") == 0
    assert "clavicus_kept_word" in c.world_events_fired


def test_clavicus_availability_and_five_shrines_coexist():
    gd, c = _gd_char(level=16)
    assert "clavicus_bargain" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 17)
    c.level = 17
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain"} <= set(av)
    assert gd.quests["clavicus_bargain"]["shrine"] == "clavicus"


def test_clavicus_content_integrity():
    gd, _ = _gd_char()
    assert "clavicus_silver_tongue" in gd.boons and "masque_of_clavicus_vile" in gd.items
    assert gd.world["locations"]["stormhaven"].get("shrine") == "clavicus"
    boss = gd.dungeons["haemars_shame"]["boss"]["enemy"]
    assert boss == "wish_eaten_sorcerer" and gd.bestiary[boss].get("solo") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Masque：helmet·fortify_skill speechcraft·無 material·僅任務 reward
    mq = gd.items["masque_of_clavicus_vile"]
    assert mq["slot"] == "helmet" and mq["enchant"]["skill"] == "speechcraft" and "material" not in mq
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "masque_of_clavicus_vile" not in tl + dd.get("loot", [])
    # 社交誓福純社交/防禦,守紅線(無 sneak/武器技能)
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["clavicus_silver_tongue"].get("skill", {})))


# --- 第六位親王:佩雷丽特(盾/防魔軸;serve→Spellbreaker 神器 vs defy→誓福)----
def _complete_peryite(gd, c, branch):
    quests.accept_quest(c, gd, "peryite_cure", branch=branch)
    inventory.add_item(c, "deathbell", 2)   # 疫物之引(collect 階段)
    c.location_id = "plague_warren"
    quests.record_dungeon_clear(c, "plague_warren")
    quests.check_completion(c, gd)


def test_peryite_serve_branch_grants_shield_not_boon():
    """役疫之路 → 得神器 靈破者、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=17)
    _complete_peryite(gd, c, 0)
    assert "peryite_cure" in c.completed_quests
    assert inventory.count_item(c, "spellbreaker") == 1
    assert not boons.has_boon(c, "peryite_ward") and c.infamy >= 25
    assert "peryite_served" in c.world_events_fired


def test_spellbreaker_magic_resist_when_worn():
    """靈破者穿戴 → 魔法抗性 +45(防魔/盾軸 / resist_element 路徑)。"""
    from tesrpg.systems import magic, stats
    gd, c = _gd_char(level=17)
    mr0 = magic.entity_resist(c, gd).get("magic", 0)
    _complete_peryite(gd, c, 0)
    inventory.equip_armor(c, gd, "spellbreaker")
    stats.recompute_equipment(c, gd)
    assert magic.entity_resist(c, gd).get("magic", 0) == mr0 + 45


def test_peryite_defy_branch_grants_boon_not_shield():
    """淨疫之路 → 永久誓福 守序之佑(endurance+10/block+10/disease+25)、不得神器。"""
    gd, c = _gd_char(level=17)
    e0, bl0 = c.attr("endurance"), c.skill("block")
    dis0 = __import__("tesrpg.systems.magic", fromlist=["entity_resist"]).entity_resist(c, gd).get("disease", 0)
    _complete_peryite(gd, c, 1)
    assert boons.has_boon(c, "peryite_ward")
    assert c.attr("endurance") == e0 + 10 and c.skill("block") == bl0 + 10
    assert c.base_attr("endurance") == e0          # 🔴 不寫 base
    from tesrpg.systems import magic
    assert magic.entity_resist(c, gd).get("disease", 0) == dis0 + 25
    assert inventory.count_item(c, "spellbreaker") == 0
    assert "peryite_defied" in c.world_events_fired


def test_peryite_availability_and_six_shrines_coexist():
    gd, c = _gd_char(level=16)
    assert "peryite_cure" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 17)
    c.level = 17
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure"} <= set(av)
    assert gd.quests["peryite_cure"]["shrine"] == "peryite"


def test_peryite_content_integrity():
    gd, _ = _gd_char()
    assert "peryite_ward" in gd.boons and "spellbreaker" in gd.items
    assert gd.world["locations"]["shadowfen"].get("shrine") == "peryite"
    boss = gd.dungeons["plague_warren"]["boss"]["enemy"]
    assert boss == "plague_renegade" and gd.bestiary[boss].get("solo") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Spellbreaker：1H shield(非 great_shield)·magic resist·無 material·僅任務 reward
    sb = gd.items["spellbreaker"]
    assert sb["slot"] == "shield" and not sb.get("great_shield") and sb["enchant"]["element"] == "magic" and "material" not in sb
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "spellbreaker" not in tl + dd.get("loot", [])
    # 誓福守紅線:無 sneak/武器技能(endurance/willpower/block 安全)
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["peryite_ward"].get("skill", {})))


# --- 第七位親王:梅赫拉(暗影/魂刃軸;serve→Ebony Blade 神器 vs seal→誓福)----
def _complete_mephala(gd, c, branch):
    quests.accept_quest(c, gd, "mephala_whisper", branch=branch)
    inventory.add_item(c, "spider_egg", 2)   # 蛛裔供奉(collect 階段)
    c.location_id = "whispering_warren"
    quests.record_dungeon_clear(c, "whispering_warren")
    quests.check_completion(c, gd)


def test_mephala_serve_branch_grants_blade_not_boon():
    """弒密之路 → 得神器 黑檀刃、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=17)
    _complete_mephala(gd, c, 0)
    assert "mephala_whisper" in c.completed_quests
    assert inventory.count_item(c, "ebony_blade") == 1
    assert not boons.has_boon(c, "mephala_shadow") and c.infamy >= 30
    assert "mephala_blade_claimed" in c.world_events_fired


def test_ebony_blade_vampiric_lifesteal_in_combat():
    """黑檀刃 vampiric → 命中造成傷害後回血(複用 blade_of_woe 路徑;sword archetype 無偷襲加成)。"""
    from tesrpg.systems import combat
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=17)
    _complete_mephala(gd, c, 0)
    c.weapon = "ebony_blade"; c.is_player = True
    c.skills["blade"] = 100; c.max_health = 300
    healed = 0
    for i in range(8):
        c.health = 50
        d = combat.spawn_creature(gd, "bandit", RNG(i)); d.max_health = d.health = 400
        d.agility = 1; d.armor_rating = 0
        combat.resolve_attack(c, d, gd, RNG(70 + i))
        if c.health > 50:
            healed += c.health - 50
    assert healed > 0, "vampiric 未回血(命中造成傷害應吸血)"
    # sword archetype:無偷襲加成(守刺客紅線,非 dagger/bow)
    assert gd.items["ebony_blade"]["archetype"] == "sword"


def test_mephala_seal_branch_grants_boon_not_blade():
    """封密之路 → 永久誓福 蛛影之佑(agility+10/illusion+10)、不得神器。"""
    gd, c = _gd_char(level=17)
    a0, il0 = c.attr("agility"), c.skill("illusion")
    _complete_mephala(gd, c, 1)
    assert boons.has_boon(c, "mephala_shadow")
    assert c.attr("agility") == a0 + 10 and c.skill("illusion") == il0 + 10
    assert c.base_attr("agility") == a0          # 🔴 不寫 base
    assert inventory.count_item(c, "ebony_blade") == 0
    assert "mephala_door_sealed" in c.world_events_fired


def test_mephala_availability_and_seven_shrines_coexist():
    gd, c = _gd_char(level=16)
    assert "mephala_whisper" not in quests.available_quests(c, gd, "daedric")   # 等級不足
    c.level = 17
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper"} <= set(av)
    assert gd.quests["mephala_whisper"]["shrine"] == "mephala"


def test_mephala_content_integrity():
    gd, _ = _gd_char()
    assert "mephala_shadow" in gd.boons and "ebony_blade" in gd.items
    assert gd.world["locations"]["blackwood"].get("shrine") == "mephala"
    boss = gd.dungeons["whispering_warren"]["boss"]["enemy"]
    assert boss == "mephala_webspinner" and gd.bestiary[boss].get("solo") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Ebony Blade：sword archetype(非 dagger/bow → 無偷襲加成)·vampiric·僅任務 reward
    eb = gd.items["ebony_blade"]
    assert eb["archetype"] == "sword" and eb["enchant"]["status"] == "vampiric"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "ebony_blade" not in tl + dd.get("loot", [])
    # 誓福守紅線:illusion 是魔法學派(非武器技能/sneak)
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["mephala_shadow"].get("skill", {})))


# --- 第八位親王:桑格玖完(召喚師軸;serve→Sanguine Rose 神器 vs sober→誓福)--
def _complete_sanguine(gd, c, branch):
    quests.accept_quest(c, gd, "sanguine_party", branch=branch)
    inventory.add_item(c, "moon_sugar", 2)   # 縱情供奉(collect 階段)
    c.location_id = "misty_grove"
    quests.record_dungeon_clear(c, "misty_grove")
    quests.check_completion(c, gd)


def test_sanguine_serve_branch_grants_rose_not_boon():
    """縱酒之路 → 得神器 桑格玖完之薔薇、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=17)
    _complete_sanguine(gd, c, 0)
    assert "sanguine_party" in c.completed_quests
    assert inventory.count_item(c, "sanguine_rose") == 1
    assert not boons.has_boon(c, "sanguine_revel") and c.infamy >= 25
    assert "sanguine_rose_taken" in c.world_events_fired


def test_sanguine_rose_restores_magicka_on_hit():
    """桑格玖完之薔薇 on_hit_self → 命中回復施術者法力(召喚師續航;複用 magicka_staff 路徑)。"""
    from tesrpg.systems import combat, stats
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=17)
    _complete_sanguine(gd, c, 0)
    c.weapon = "sanguine_rose"; c.is_player = True
    c.skills["conjuration"] = 100
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.magicka = 0
    gained = 0
    for i in range(6):
        c.magicka = 0
        d = combat.spawn_creature(gd, "bandit", RNG(i)); d.max_health = d.health = 400
        d.agility = 1; d.armor_rating = 0
        combat.resolve_attack(c, d, gd, RNG(80 + i))
        if c.magicka > 0:
            gained += c.magicka
    assert gained > 0, "on_hit_self 未回魔(命中應回復法力)"
    assert gd.items["sanguine_rose"]["archetype"] == "staff"


def test_sanguine_sober_branch_grants_boon_not_rose():
    """清醒之路 → 永久誓福 歡愉之佑(conjuration+12/willpower+8/magicka+15)、不得神器。"""
    gd, c = _gd_char(level=17)
    cj0, mg0 = c.skill("conjuration"), c.max_magicka
    _complete_sanguine(gd, c, 1)
    assert boons.has_boon(c, "sanguine_revel")
    assert c.skill("conjuration") == cj0 + 12
    assert c.base_skill("conjuration") == cj0          # 🔴 不寫 base
    assert c.max_magicka >= mg0 + 15                   # 召喚續航(固定魔力上限 +15)
    assert inventory.count_item(c, "sanguine_rose") == 0
    assert "sanguine_declined" in c.world_events_fired


def test_sanguine_availability_and_eight_shrines_coexist():
    gd, c = _gd_char(level=16)
    assert "sanguine_party" not in quests.available_quests(c, gd, "daedric")   # 等級不足
    c.level = 17
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party"} <= set(av)
    assert gd.quests["sanguine_party"]["shrine"] == "sanguine"


def test_sanguine_content_integrity():
    gd, _ = _gd_char()
    assert "sanguine_revel" in gd.boons and "sanguine_rose" in gd.items
    assert gd.world["locations"]["rimmen_desert"].get("shrine") == "sanguine"
    boss = gd.dungeons["misty_grove"]["boss"]["enemy"]
    assert boss == "revel_daedra" and gd.bestiary[boss].get("solo") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Sanguine Rose：staff·on_hit_self 回魔(召喚續航)·僅任務 reward
    sr = gd.items["sanguine_rose"]
    assert sr["archetype"] == "staff" and sr["on_hit_self"]["stat"] == "magicka"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "sanguine_rose" not in tl + dd.get("loot", [])
    # 誓福守紅線:conjuration 是召喚學派(已見於達貢誓福),非武器/sneak 技能
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["sanguine_revel"].get("skill", {})))


# --- 第九位親王:馬拉凱斯(雙手武器軸;serve→Volendrung 神器 vs defy→誓福)----
def _complete_malacath(gd, c, branch):
    quests.accept_quest(c, gd, "malacath_curse", branch=branch)
    inventory.add_item(c, "bone_meal", 2)   # 詛咒之引(collect 階段)
    c.location_id = "malacath_cursed_hold"
    quests.record_dungeon_clear(c, "malacath_cursed_hold")
    quests.check_completion(c, gd)


def test_malacath_serve_branch_grants_hammer_not_boon():
    """臣服之路 → 得神器 沃倫鎚、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=18)
    _complete_malacath(gd, c, 0)
    assert "malacath_curse" in c.completed_quests
    assert inventory.count_item(c, "volendrung") == 1
    assert not boons.has_boon(c, "malacath_might") and c.infamy >= 30
    assert "malacath_served" in c.world_events_fired


def test_volendrung_restores_fatigue_on_hit():
    """沃倫鎚 absorb_fatigue → 命中回復揮鎚者氣力(雙手鈍器續航;複用 absorb_fatigue 路徑)。"""
    from tesrpg.systems import combat, stats
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=18)
    _complete_malacath(gd, c, 0)
    c.weapon = "volendrung"; c.is_player = True
    c.skills["blunt"] = 100
    stats.recompute_max_resources(c, gd, restore_full=True)
    gained = 0
    for i in range(6):
        c.fatigue = 0
        d = combat.spawn_creature(gd, "bandit", RNG(i)); d.max_health = d.health = 400
        d.agility = 1; d.armor_rating = 0
        combat.resolve_attack(c, d, gd, RNG(80 + i))
        if c.fatigue > 0:
            gained += c.fatigue
    assert gained > 0, "absorb_fatigue 未回氣力(命中應回復揮鎚者氣力)"
    # 雙手鈍器(blunt 非 dagger/bow → 無偷襲加成,守刺客紅線)
    assert gd.items["volendrung"]["two_handed"] is True and gd.items["volendrung"]["archetype"] == "mace"


def test_malacath_defy_branch_grants_boon_not_hammer():
    """抗咒之路 → 永久誓福 棄絕者之力(strength+10/endurance+8/smithing+10)、不得神器。"""
    gd, c = _gd_char(level=18)
    s0, e0, sm0 = c.attr("strength"), c.attr("endurance"), c.skill("smithing")
    _complete_malacath(gd, c, 1)
    assert boons.has_boon(c, "malacath_might")
    assert c.attr("strength") == s0 + 10 and c.attr("endurance") == e0 + 8
    assert c.skill("smithing") == sm0 + 10
    assert c.base_attr("strength") == s0          # 🔴 不寫 base
    assert inventory.count_item(c, "volendrung") == 0
    assert "malacath_defied" in c.world_events_fired


def test_malacath_availability_and_nine_shrines_coexist():
    gd, c = _gd_char(level=17)
    assert "malacath_curse" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 18)
    c.level = 18
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party",
            "malacath_curse"} <= set(av)
    assert gd.quests["malacath_curse"]["shrine"] == "malacath"


def test_malacath_content_integrity():
    gd, _ = _gd_char()
    assert "malacath_might" in gd.boons and "volendrung" in gd.items
    assert gd.world["locations"]["dragontail_peaks"].get("shrine") == "malacath"
    assert "malacath_cursed_hold" in gd.dungeons and "malacath_cursed_hold" in gd.world["locations"]
    boss = gd.dungeons["malacath_cursed_hold"]["boss"]["enemy"]
    assert boss == "malacath_outcast_chief" and gd.bestiary[boss].get("solo") is True
    assert gd.dungeons["malacath_cursed_hold"]["boss"].get("raw") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Volendrung:雙手鈍器(two_handed mace)·absorb_fatigue·blunt 非 dagger/bow·僅任務 reward
    v = gd.items["volendrung"]
    assert v["two_handed"] is True and v["archetype"] == "mace" and v["skill"] == "blunt"
    assert v["enchant"]["kind"] == "weapon_status" and v["enchant"]["status"] == "absorb_fatigue"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "volendrung" not in tl + dd.get("loot", [])
    # 地城怪皆存在
    for m in gd.dungeons["malacath_cursed_hold"]["monsters"]:
        assert m in gd.bestiary, m
    # 誓福守紅線:無 sneak/武器技能(smithing 是工匠技能);strength ≤ 達貢(18)+18
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["malacath_might"].get("skill", {})))
    assert gd.boons["malacath_might"].get("attr", {}).get("strength", 0) <= 18 + 18


# --- 第十位親王:梅瑞迪雅(恢復/聖光軸;serve→Dawnbreaker 神器 vs defy→誓福)----
def _complete_meridia(gd, c, branch):
    quests.accept_quest(c, gd, "meridia_beacon", branch=branch)
    inventory.add_item(c, "glow_dust", 2)   # 聖光之引(collect 階段)
    c.location_id = "defiled_lightshrine"
    quests.record_dungeon_clear(c, "defiled_lightshrine")
    quests.check_completion(c, gd)


def test_meridia_serve_branch_grants_sword_not_boon():
    """執刃之路 → 得神器 破曉者、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=18)
    _complete_meridia(gd, c, 0)
    assert "meridia_beacon" in c.completed_quests
    assert inventory.count_item(c, "dawnbreaker") == 1
    assert not boons.has_boon(c, "meridia_light") and c.infamy >= 25
    assert "meridia_champion" in c.world_events_fired


def test_dawnbreaker_burns_on_hit():
    """破曉者 weapon_status burn → 命中對目標施加火焰 DoT(複用既有 ench_dot 路徑)。"""
    from tesrpg.systems import combat
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=18)
    _complete_meridia(gd, c, 0)
    c.weapon = "dawnbreaker"; c.is_player = True
    c.skills["blade"] = 100
    applied = 0
    for i in range(8):
        d = combat.spawn_creature(gd, "bandit", RNG(i)); d.max_health = d.health = 400
        d.agility = 1; d.armor_rating = 0
        combat.resolve_attack(c, d, gd, RNG(60 + i))
        if any(e.get("kind") == "dot" and e.get("element") == "fire" and e.get("source") == "ench_dot"
               for e in d.active_effects):
            applied += 1
    assert applied > 0, "burn 未施加火焰 DoT(命中應點燃目標)"
    # sword archetype:無偷襲加成(守刺客紅線,非 dagger/bow)
    assert gd.items["dawnbreaker"]["archetype"] == "sword"


def test_meridia_defy_branch_grants_boon_not_sword():
    """守光之路 → 永久誓福 光之佑(personality+8/willpower+6/restoration+10/light_armor+6)、不得神器。"""
    gd, c = _gd_char(level=18)
    p0, w0 = c.attr("personality"), c.attr("willpower")
    rs0, la0 = c.skill("restoration"), c.skill("light_armor")
    _complete_meridia(gd, c, 1)
    assert boons.has_boon(c, "meridia_light")
    assert c.attr("personality") == p0 + 8 and c.attr("willpower") == w0 + 6
    assert c.skill("restoration") == rs0 + 10 and c.skill("light_armor") == la0 + 6
    assert c.base_attr("personality") == p0          # 🔴 不寫 base
    assert inventory.count_item(c, "dawnbreaker") == 0
    assert "meridia_light_kept" in c.world_events_fired


def test_meridia_availability_and_ten_shrines_coexist():
    gd, c = _gd_char(level=17)
    assert "meridia_beacon" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 18)
    c.level = 18
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party",
            "malacath_curse", "meridia_beacon"} <= set(av)
    assert gd.quests["meridia_beacon"]["shrine"] == "meridia"


def test_meridia_content_integrity():
    gd, _ = _gd_char()
    assert "meridia_light" in gd.boons and "dawnbreaker" in gd.items
    assert gd.world["locations"]["gold_coast"].get("shrine") == "meridia"
    assert "defiled_lightshrine" in gd.dungeons and "defiled_lightshrine" in gd.world["locations"]
    boss = gd.dungeons["defiled_lightshrine"]["boss"]["enemy"]
    assert boss == "meridia_defiler" and gd.bestiary[boss].get("solo") is True
    assert gd.dungeons["defiled_lightshrine"]["boss"].get("raw") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Dawnbreaker:sword archetype(非 dagger/bow → 無偷襲)·火焰 burn DoT·僅任務 reward
    db = gd.items["dawnbreaker"]
    assert db["archetype"] == "sword" and db["skill"] == "blade"
    assert db["enchant"]["kind"] == "weapon_status" and db["enchant"]["status"] == "burn" and db["enchant"]["element"] == "fire"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "dawnbreaker" not in tl + dd.get("loot", [])
    # 地城怪皆存在
    for m in gd.dungeons["defiled_lightshrine"]["monsters"]:
        assert m in gd.bestiary, m
    # 誓福守紅線:restoration 是魔法學派、light_armor 是護甲技能(皆非 sneak/武器技能);無 strength
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["meridia_light"].get("skill", {})))
    assert "strength" not in gd.boons["meridia_light"].get("attr", {})


# --- 第十一位親王:瓦瑪納(純元素破壞法系軸;serve→Skull of Corruption 神器 vs defy→誓福)----
def _complete_vaermina(gd, c, branch):
    quests.accept_quest(c, gd, "waking_nightmare", branch=branch)
    inventory.add_item(c, "lavender", 2)   # 沉眠夢香(collect 階段)
    c.location_id = "nightcaller_temple"
    quests.record_dungeon_clear(c, "nightcaller_temple")
    quests.check_completion(c, gd)


def test_vaermina_serve_branch_grants_skull_not_boon():
    """執顱之路 → 得神器 腐敗之顱、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=18)
    _complete_vaermina(gd, c, 0)
    assert "waking_nightmare" in c.completed_quests
    assert inventory.count_item(c, "skull_of_corruption") == 1
    assert not boons.has_boon(c, "vaermina_nightmare") and c.infamy >= 30
    assert "vaermina_served" in c.world_events_fired


def test_skull_of_corruption_shock_damage():
    """腐敗之顱 weapon_element shock → 命中附加電擊傷,且吃目標電抗(複用既有 weapon_element 路徑)。"""
    from tesrpg.systems import combat
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=18)
    _complete_vaermina(gd, c, 0)
    c.weapon = "skull_of_corruption"; c.is_player = True
    c.skills["destruction"] = 100

    def total_dmg(resist_shock):
        tot = 0
        for i in range(12):
            d = combat.spawn_creature(gd, "bandit", RNG(i)); d.max_health = d.health = 9999
            d.agility = 1; d.armor_rating = 0; d.resist = {"shock": resist_shock}
            combat.resolve_attack(c, d, gd, RNG(50 + i))
            tot += 9999 - d.health
        return tot

    assert total_dmg(0) > total_dmg(80), "電抗未削減電擊傷(weapon_element 未生效或未吃抗性)"
    assert gd.items["skull_of_corruption"]["archetype"] == "staff"


def test_vaermina_defy_branch_grants_boon_not_skull():
    """破夢之路 → 永久誓福 夢魘之佑(intelligence+8/willpower+6/destruction+10/magicka+20)、不得神器。"""
    gd, c = _gd_char(level=18)
    i0, w0, ds0, mg0 = c.attr("intelligence"), c.attr("willpower"), c.skill("destruction"), c.max_magicka
    _complete_vaermina(gd, c, 1)
    assert boons.has_boon(c, "vaermina_nightmare")
    assert c.attr("intelligence") == i0 + 8 and c.attr("willpower") == w0 + 6
    assert c.skill("destruction") == ds0 + 10
    assert c.max_magicka >= mg0 + 20                   # 法師續航(固定魔力上限 +20)
    assert c.base_attr("intelligence") == i0          # 🔴 不寫 base
    assert inventory.count_item(c, "skull_of_corruption") == 0
    assert "vaermina_defied" in c.world_events_fired


def test_vaermina_availability_and_eleven_shrines_coexist():
    gd, c = _gd_char(level=17)
    assert "waking_nightmare" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 18)
    c.level = 18
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party",
            "malacath_curse", "meridia_beacon", "waking_nightmare"} <= set(av)
    assert gd.quests["waking_nightmare"]["shrine"] == "vaermina"


def test_vaermina_content_integrity():
    gd, _ = _gd_char()
    assert "vaermina_nightmare" in gd.boons and "skull_of_corruption" in gd.items
    assert gd.world["locations"]["the_pale_tundra"].get("shrine") == "vaermina"
    assert "nightcaller_temple" in gd.dungeons and "nightcaller_temple" in gd.world["locations"]
    boss = gd.dungeons["nightcaller_temple"]["boss"]["enemy"]
    assert boss == "dream_devourer" and gd.bestiary[boss].get("solo") is True
    assert gd.dungeons["nightcaller_temple"]["boss"].get("raw") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Skull of Corruption:staff·destruction·weapon_element shock·僅任務 reward
    sk = gd.items["skull_of_corruption"]
    assert sk["archetype"] == "staff" and sk["skill"] == "destruction"
    assert sk["enchant"]["kind"] == "weapon_element" and sk["enchant"]["element"] == "shock"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "skull_of_corruption" not in tl + dd.get("loot", [])
    # 地城怪皆存在
    for m in gd.dungeons["nightcaller_temple"]["monsters"]:
        assert m in gd.bestiary, m
    # 誓福守紅線:destruction 是魔法學派(已見於達貢誓福)·非 sneak/武器技能;無 strength
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["vaermina_nightmare"].get("skill", {})))
    assert "strength" not in gd.boons["vaermina_nightmare"].get("attr", {})


# --- 第十二位親王:娜米拉(煉金/毒藥匠軸;serve→Ring of Namira 神器 vs defy→誓福)----
def _complete_namira(gd, c, branch):
    quests.accept_quest(c, gd, "namira_feast", branch=branch)
    inventory.add_item(c, "imp_stool", 2)   # 腐物之引(collect 階段)
    c.location_id = "carrion_grotto"
    quests.record_dungeon_clear(c, "carrion_grotto")
    quests.check_completion(c, gd)


def test_namira_serve_branch_grants_ring_not_boon():
    """赴宴之路 → 得神器 娜米拉之戒、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=18)
    _complete_namira(gd, c, 0)
    assert "namira_feast" in c.completed_quests
    assert inventory.count_item(c, "ring_of_namira") == 1
    assert not boons.has_boon(c, "namira_decay") and c.infamy >= 30
    assert "namira_feast_joined" in c.world_events_fired


def test_ring_of_namira_fortifies_alchemy_when_worn():
    """娜米拉之戒穿戴 → 煉金技能 +25(毒藥匠軸 / 飾品 fortify_skill 路徑)。"""
    from tesrpg.systems import stats
    gd, c = _gd_char(level=18)
    al0 = c.skill("alchemy")
    _complete_namira(gd, c, 0)
    inventory.equip_jewelry(c, gd, "ring_of_namira")
    stats.recompute_equipment(c, gd)
    assert c.skill("alchemy") == al0 + 25
    assert c.base_skill("alchemy") == al0          # 🔴 裝備層不寫 base


def test_namira_defy_branch_grants_boon_not_ring():
    """淨化之路 → 永久誓福 腐朽之佑(agility+8/endurance+6/alchemy+12)、不得神器。"""
    gd, c = _gd_char(level=18)
    a0, e0, al0 = c.attr("agility"), c.attr("endurance"), c.skill("alchemy")
    _complete_namira(gd, c, 1)
    assert boons.has_boon(c, "namira_decay")
    assert c.attr("agility") == a0 + 8 and c.attr("endurance") == e0 + 6
    assert c.skill("alchemy") == al0 + 12
    assert c.base_attr("agility") == a0          # 🔴 不寫 base
    from tesrpg.systems import magic
    assert magic.entity_resist(c, gd).get("poison", 0) >= 20
    assert inventory.count_item(c, "ring_of_namira") == 0
    assert "namira_cult_purged" in c.world_events_fired


def test_namira_availability_and_twelve_shrines_coexist():
    gd, c = _gd_char(level=17)
    assert "namira_feast" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 18)
    c.level = 18
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party",
            "malacath_curse", "meridia_beacon", "waking_nightmare", "namira_feast"} <= set(av)
    assert gd.quests["namira_feast"]["shrine"] == "namira"


def test_namira_content_integrity():
    gd, _ = _gd_char()
    assert "namira_decay" in gd.boons and "ring_of_namira" in gd.items
    assert gd.world["locations"]["malabal_tor"].get("shrine") == "namira"
    assert "carrion_grotto" in gd.dungeons and "carrion_grotto" in gd.world["locations"]
    boss = gd.dungeons["carrion_grotto"]["boss"]["enemy"]
    assert boss == "carrion_priest" and gd.bestiary[boss].get("solo") is True
    assert gd.dungeons["carrion_grotto"]["boss"].get("raw") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Ring of Namira:jewelry ring·fortify_skill alchemy·僅任務 reward
    rn = gd.items["ring_of_namira"]
    assert rn["slot"] == "ring" and rn["enchant"]["kind"] == "fortify_skill" and rn["enchant"]["skill"] == "alchemy"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "ring_of_namira" not in tl + dd.get("loot", [])
    # 地城怪皆存在
    for m in gd.dungeons["carrion_grotto"]["monsters"]:
        assert m in gd.bestiary, m
    # 誓福守紅線:alchemy 是工藝技能(非 sneak/武器技能);無 strength
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["namira_decay"].get("skill", {})))
    assert "strength" not in gd.boons["namira_decay"].get("attr", {})


# --- 第十三位親王:謝歐格拉斯(瘋神;新機制 Wabbajack 混沌·serve→神器 vs defy→alteration 誓福)----
def _complete_sheogorath(gd, c, branch):
    quests.accept_quest(c, gd, "mind_of_madness", branch=branch)
    inventory.add_item(c, "monarch_wing", 2)   # 沒道理的供品(collect 階段)
    c.location_id = "madness_realm"
    quests.record_dungeon_clear(c, "madness_realm")
    quests.check_completion(c, gd)


def test_sheogorath_serve_branch_grants_wabbajack_not_boon():
    """執杖之路 → 得神器 瓦巴賈克、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=18)
    _complete_sheogorath(gd, c, 0)
    assert "mind_of_madness" in c.completed_quests
    assert inventory.count_item(c, "wabbajack") == 1
    assert not boons.has_boon(c, "sheogorath_madness") and c.infamy >= 30
    assert "sheogorath_served" in c.world_events_fired


def test_sheogorath_defy_branch_grants_boon_not_wabbajack():
    """守心之路 → 永久誓福 瘋癲之佑(willpower+8/luck+6/alteration+12/magicka+20)、不得神器。"""
    gd, c = _gd_char(level=18)
    w0, lk0, al0, mg0 = c.attr("willpower"), c.attr("luck"), c.skill("alteration"), c.max_magicka
    _complete_sheogorath(gd, c, 1)
    assert boons.has_boon(c, "sheogorath_madness")
    assert c.attr("willpower") == w0 + 8 and c.attr("luck") == lk0 + 6
    assert c.skill("alteration") == al0 + 12
    assert c.max_magicka >= mg0 + 20
    assert c.base_attr("willpower") == w0          # 🔴 不寫 base
    assert inventory.count_item(c, "wabbajack") == 0
    assert "sheogorath_defied" in c.world_events_fired


def test_wabbajack_chaos_effects_fire_and_stay_safe():
    """瓦巴賈克命中觸發隨機混沌(R46):多種不同效果都會出現·回火永不致死·不拋例外。"""
    from tesrpg.systems import combat
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=19)
    c.weapon = "wabbajack"; c.is_player = True
    c.skills["destruction"] = 100
    c.max_health = 300; c.max_magicka = 300; c.max_fatigue = 300
    seen = set()
    for i in range(150):
        c.health = 250; c.magicka = 0; c.fatigue = 0
        d = combat.spawn_creature(gd, "bandit", RNG(i)); d.max_health = d.health = 9999
        d.agility = 1; d.armor_rating = 0; d.active_effects = []
        combat.resolve_attack(c, d, gd, RNG(3000 + i))   # 絕不拋例外
        assert c.health >= 1, "回火自傷不可致死(max(1,…))"
        wsrc = [e for e in d.active_effects if e.get("source") == "wabbajack"]
        if any(e.get("kind") in ("fear", "paralyze", "stagger") for e in wsrc): seen.add("control")
        if any(e.get("kind") == "weaken" for e in wsrc): seen.add("weaken")
        if c.magicka > 0 or c.health > 250: seen.add("self_restore")
        if c.health < 250: seen.add("backfire_self")
    assert len(seen) >= 3, f"混沌效果種類過少:{seen}"
    assert gd.items["wabbajack"]["archetype"] == "staff"   # staff → 零偷襲守紅線


def test_wabbajack_control_routes_apply_control_solo_resists():
    """硬控走 magic.apply_control:solo BOSS 比一般怪更難被控(SOLO_CONTROL_RESIST_CHANCE);且永不一擊秒殺 solo。"""
    from tesrpg.systems import combat
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=20)
    c.weapon = "wabbajack"; c.is_player = True; c.skills["destruction"] = 100

    def hard_control_landings(template, n):
        applied = 0; max_hit = 0.0
        for i in range(n):
            t = combat.spawn_creature(gd, template, RNG(i))
            t.active_effects = []; t.max_health = 9999; t.health = 9999
            t.agility = 1; t.armor_rating = 0
            combat.resolve_attack(c, t, gd, RNG(i))
            if any(e.get("kind") in ("fear", "paralyze") for e in t.active_effects):
                applied += 1
            max_hit = max(max_hit, 9999 - t.health)
        return applied, max_hit

    solo_applied, solo_max_hit = hard_control_landings("madness_avatar", 300)   # solo:true
    mob_applied, _ = hard_control_landings("bandit", 300)                       # 一般怪無 solo 抵抗
    assert solo_applied > 0, "硬控完全沒上 → apply_control 未生效"
    assert solo_applied < mob_applied, "solo BOSS 未享機率抵抗(應比一般怪更難被控)"
    # 單擊永不秒殺 solo BOSS(法杖無偷襲·爆發受 WABBAJACK_BURST_SOLO_FACTOR 夾)
    boss_hp = gd.bestiary["madness_avatar"]["max_health"]
    assert solo_max_hit < boss_hp, "單擊不可秒殺 solo BOSS"


def test_wabbajack_not_craftable_and_sim_isolated():
    """瓦巴賈克玩家不可鍛造(不入白名單);且 sim 的匕首路徑無附魔 → 機制與 sim_assassin 完全隔離。"""
    from tesrpg.systems import enchanting
    gd, _ = _gd_char()
    assert "wabbajack" not in enchanting._WEAPON_STATUSES
    assert gd.items["steel_dagger"].get("enchant") is None


def test_sheogorath_availability_and_thirteen_shrines_coexist():
    gd, c = _gd_char(level=17)
    assert "mind_of_madness" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 18)
    c.level = 18
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party",
            "malacath_curse", "meridia_beacon", "waking_nightmare", "namira_feast",
            "mind_of_madness"} <= set(av)
    assert gd.quests["mind_of_madness"]["shrine"] == "sheogorath"


def test_sheogorath_content_integrity():
    gd, _ = _gd_char()
    assert "sheogorath_madness" in gd.boons and "wabbajack" in gd.items
    assert gd.world["locations"]["hist_grove"].get("shrine") == "sheogorath"
    assert "madness_realm" in gd.dungeons and "madness_realm" in gd.world["locations"]
    boss = gd.dungeons["madness_realm"]["boss"]["enemy"]
    assert boss == "madness_avatar" and gd.bestiary[boss].get("solo") is True
    assert gd.dungeons["madness_realm"]["boss"].get("raw") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # Wabbajack:staff·weapon_status "wabbajack"·僅任務 reward
    wj = gd.items["wabbajack"]
    assert wj["archetype"] == "staff" and wj["enchant"]["kind"] == "weapon_status" and wj["enchant"]["status"] == "wabbajack"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "wabbajack" not in tl + dd.get("loot", [])
    # 地城怪皆存在
    for m in gd.dungeons["madness_realm"]["monsters"]:
        assert m in gd.bestiary, m
    # 誓福守紅線:alteration 是魔法學派(補最後一個未覆蓋學派)·非 sneak/武器技能·無 strength
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["sheogorath_madness"].get("skill", {})))
    assert "strength" not in gd.boons["sheogorath_madness"].get("attr", {})


# --- 第十四位親王:諾克圖娜爾(盜賊/security 軸;steal→骷髏鑰 神器 vs guard→誓福)----
def _complete_nocturnal(gd, c, branch):
    quests.accept_quest(c, gd, "twilight_sepulcher", branch=branch)
    inventory.add_item(c, "ruby", 2)   # 賊贓供奉(collect 階段)
    c.location_id = "twilight_crypt"
    quests.record_dungeon_clear(c, "twilight_crypt")
    quests.check_completion(c, gd)


def test_nocturnal_steal_branch_grants_skeleton_key_not_boon():
    """竊鑰之路 → 得神器 骷髏鑰匙、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=18)
    _complete_nocturnal(gd, c, 0)
    assert "twilight_sepulcher" in c.completed_quests
    assert inventory.count_item(c, "skeleton_key") == 1
    assert not boons.has_boon(c, "nocturnal_shadow") and c.infamy >= 30
    assert "nocturnal_key_taken" in c.world_events_fired


def test_skeleton_key_still_perfect_lockpick_after_rehome():
    """骷髏鑰換手到 Nocturnal 後,撬鎖必成機制不變(認 skeleton_key 旗標,非發放來源)。"""
    from tesrpg.systems import dungeon
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=18)
    c.skills["security"] = 0
    assert not dungeon.has_skeleton_key(c, gd)
    c.equipped["amulet"] = "skeleton_key"
    assert dungeon.has_skeleton_key(c, gd)
    assert dungeon.effective_pick_lock_chance(c, gd, 80) == 1.0
    sec0 = c.base_skill("security")
    r = dungeon.pick_lock(c, gd, 80, RNG(0))
    assert r["success"] and r.get("skeleton_key") and not r["no_pick"]
    assert c.base_skill("security") == sec0          # 仍不給 security xp


def test_nocturnal_guard_branch_grants_boon_not_key():
    """守鑰之路 → 永久誓福 夜影之佑(agility+8/luck+6/security+12/illusion+10)、不得神器。"""
    gd, c = _gd_char(level=18)
    a0, lk0, se0, il0 = c.attr("agility"), c.attr("luck"), c.skill("security"), c.skill("illusion")
    _complete_nocturnal(gd, c, 1)
    assert boons.has_boon(c, "nocturnal_shadow")
    assert c.attr("agility") == a0 + 8 and c.attr("luck") == lk0 + 6
    assert c.skill("security") == se0 + 12 and c.skill("illusion") == il0 + 10
    assert c.base_attr("agility") == a0          # 🔴 不寫 base
    assert inventory.count_item(c, "skeleton_key") == 0
    assert "nocturnal_nightingale" in c.world_events_fired


def test_nocturnal_availability_and_fourteen_shrines_coexist():
    gd, c = _gd_char(level=17)
    assert "twilight_sepulcher" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 18)
    c.level = 18
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party",
            "malacath_curse", "meridia_beacon", "waking_nightmare", "namira_feast",
            "mind_of_madness", "twilight_sepulcher"} <= set(av)
    assert gd.quests["twilight_sepulcher"]["shrine"] == "nocturnal"


def test_nocturnal_content_integrity():
    gd, _ = _gd_char()
    assert "nocturnal_shadow" in gd.boons and "skeleton_key" in gd.items
    assert gd.world["locations"]["tenmar_forest"].get("shrine") == "nocturnal"
    assert "twilight_crypt" in gd.dungeons and "twilight_crypt" in gd.world["locations"]
    boss = gd.dungeons["twilight_crypt"]["boss"]["enemy"]
    assert boss == "twilight_sentinel" and gd.bestiary[boss].get("solo") is True
    assert gd.dungeons["twilight_crypt"]["boss"].get("raw") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # skeleton_key 換手:Nocturnal 任務發、不在任何 dungeon loot;tg5 改發 gray_fox_mask
    tg5_items = [it for b in gd.quests["tg5"]["branches"] for it in b.get("reward", {}).get("items", [])]
    assert "gray_fox_mask" in tg5_items and "skeleton_key" not in tg5_items
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "skeleton_key" not in tl + dd.get("loot", [])
    # 地城怪皆存在
    for m in gd.dungeons["twilight_crypt"]["monsters"]:
        assert m in gd.bestiary, m
    # 誓福守紅線:security 是盜賊技能(非 sneak/武器技能)·無 strength
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["nocturnal_shadow"].get("skill", {})))
    assert "strength" not in gd.boons["nocturnal_shadow"].get("attr", {})


# --- 第十五位親王:賈格拉格(秩序之主;新機制 order 移除傷害變異·serve→秩序之劍 vs defy→誓福)----
def _complete_jyggalag(gd, c, branch):
    quests.accept_quest(c, gd, "greymarch", branch=branch)
    inventory.add_item(c, "moonstone_ingot", 2)   # 無瑕之引(collect 階段)
    c.location_id = "order_sanctum"
    quests.record_dungeon_clear(c, "order_sanctum")
    quests.check_completion(c, gd)


def test_jyggalag_serve_branch_grants_sword_not_boon():
    """臣服之路 → 得神器 秩序之劍、惡名上升、不得誓福。"""
    gd, c = _gd_char(level=18)
    _complete_jyggalag(gd, c, 0)
    assert "greymarch" in c.completed_quests
    assert inventory.count_item(c, "sword_of_jyggalag") == 1
    assert not boons.has_boon(c, "jyggalag_order") and c.infamy >= 30
    assert "jyggalag_served" in c.world_events_fired


def test_sword_of_jyggalag_removes_damage_variance():
    """R48 秩序之劍 order 附魔:命中傷害零變異(永遠最大 roll = DAMAGE_ROLL_HI);普通劍仍有變異(對照)。"""
    from tesrpg.systems import combat
    from tesrpg.rng import RNG
    from tesrpg import formulas
    gd, c = _gd_char(level=18)
    c.is_player = True; c.skills["blade"] = 80
    def dmg_values(weapon):
        c.weapon = weapon
        out = set()
        for i in range(40):
            c.fatigue = c.max_fatigue; c.skills["blade"] = 80   # 固定體力/技能 → 隔離,只看 roll 變異
            d = combat.spawn_creature(gd, "bandit", RNG(i)); d.max_health = d.health = 99999
            d.agility = 1; d.armor_rating = 0
            combat.resolve_attack(c, d, gd, RNG(500 + i))
            dealt = round(99999 - d.health, 3)
            if dealt > 0:   # 命中
                out.add(dealt)
        return out
    order = dmg_values("sword_of_jyggalag")
    normal = dmg_values("daedric_sword")
    assert len(order) == 1, f"秩序之劍命中傷害應零變異,實得 {order}"
    assert len(normal) > 1, f"普通劍應有傷害變異(對照組),實得 {normal}"
    # 固定值 = 最大 roll(armor 0·無格擋/增益 → dealt = attack_damage(26,blade,str,HI))
    exp = formulas.attack_damage(26, c.skill("blade"), c.attr("strength"), formulas.DAMAGE_ROLL_HI)
    assert abs(next(iter(order)) - exp) < 0.5, (order, exp)


def test_jyggalag_sword_no_oneshot_solo():
    """秩序之劍 always-max 仍不破 solo 偷襲夾(sword archetype 偷襲 ×1.0·夾在 always-max 之後)。"""
    from tesrpg.systems import combat
    from tesrpg.rng import RNG
    gd, c = _gd_char(level=20)
    c.is_player = True; c.weapon = "sword_of_jyggalag"
    c.skills["blade"] = 100; c.skills["sneak"] = 100; c.attributes["strength"] = 100
    boss_hp = gd.bestiary["knight_of_order"]["max_health"]
    worst = 0
    for i in range(60):
        b = combat.spawn_creature(gd, "knight_of_order", RNG(i)); b.max_health = b.health = boss_hp
        b.agility = 1; b.armor_rating = 0
        combat.resolve_attack(c, b, gd, RNG(700 + i), sneak_attack=True)
        worst = max(worst, boss_hp - b.health)
    assert worst < boss_hp, f"秩序之劍單擊不可秒殺 solo BOSS(實得 {worst}/{boss_hp})"


def test_jyggalag_defy_branch_grants_boon_not_sword():
    """抗序之路 → 永久誓福 秩序之佑(intelligence+8/willpower+6/mysticism+12/magicka+10)、不得神器。"""
    gd, c = _gd_char(level=18)
    i0, w0, sc0, mg0 = c.attr("intelligence"), c.attr("willpower"), c.skill("mysticism"), c.max_magicka
    _complete_jyggalag(gd, c, 1)
    assert boons.has_boon(c, "jyggalag_order")
    assert c.attr("intelligence") == i0 + 8 and c.attr("willpower") == w0 + 6
    assert c.skill("mysticism") == sc0 + 12
    assert c.max_magicka >= mg0 + 10
    assert c.base_attr("intelligence") == i0          # 🔴 不寫 base
    assert inventory.count_item(c, "sword_of_jyggalag") == 0
    assert "jyggalag_defied" in c.world_events_fired


def test_jyggalag_availability_and_fifteen_shrines_coexist():
    gd, c = _gd_char(level=17)
    assert "greymarch" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 18)
    c.level = 18
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party",
            "malacath_curse", "meridia_beacon", "waking_nightmare", "namira_feast",
            "mind_of_madness", "twilight_sepulcher", "greymarch"} <= set(av)
    assert gd.quests["greymarch"]["shrine"] == "jyggalag"


def test_jyggalag_content_integrity():
    gd, _ = _gd_char()
    assert "jyggalag_order" in gd.boons and "sword_of_jyggalag" in gd.items
    assert gd.world["locations"]["bangkorai_valley"].get("shrine") == "jyggalag"
    assert "order_sanctum" in gd.dungeons and "order_sanctum" in gd.world["locations"]
    boss = gd.dungeons["order_sanctum"]["boss"]["enemy"]
    assert boss == "knight_of_order" and gd.bestiary[boss].get("solo") is True
    assert gd.dungeons["order_sanctum"]["boss"].get("raw") is True
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # 秩序之劍:sword archetype(非 dagger/bow → 無偷襲)·order 附魔·僅任務 reward
    sj = gd.items["sword_of_jyggalag"]
    assert sj["archetype"] == "sword" and sj["enchant"]["kind"] == "order"
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "sword_of_jyggalag" not in tl + dd.get("loot", [])
    # 地城怪皆存在
    for m in gd.dungeons["order_sanctum"]["monsters"]:
        assert m in gd.bestiary, m
    # 誓福守紅線:scout 是偵查技能(非 sneak/武器技能)·無 strength
    assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                & set(gd.boons["jyggalag_order"].get("skill", {})))
    assert "strength" not in gd.boons["jyggalag_order"].get("attr", {})


# --- 赫麥尤斯·莫拉(第十六位親王·R49:Oghma 無限祕典三徑機制)-------------
def _complete_forbidden_knowledge(gd, c):
    quests.accept_quest(c, gd, "forbidden_knowledge")
    inventory.add_item(c, "moonstone_ingot", 2)   # 無瑕之引(collect 階段)
    c.location_id = "forbidden_archive"
    quests.record_dungeon_clear(c, "forbidden_archive")
    quests.check_completion(c, gd)


def test_hermaeus_quest_grants_oghma_book_no_boon_yet():
    """完成試煉 → 得無限祕典(書)、聲望+30、world_flag;讀書前不得任何誓福。"""
    gd, c = _gd_char(level=18)
    _complete_forbidden_knowledge(gd, c)
    assert "forbidden_knowledge" in c.completed_quests
    assert inventory.count_item(c, "oghma_infinium") == 1
    assert not any(boons.has_boon(c, b)
                   for b in ("hermaeus_might", "hermaeus_shadow", "hermaeus_magic"))
    assert c.fame >= 30 and "hermaeus_mora_seeker" in c.world_events_fired


def test_oghma_read_grants_chosen_boon_and_consumes_book():
    """R49 新機制:讀無限祕典 → 三選一永久誓福、書消耗;走通用 boons 層、不寫 base。"""
    import types
    from tesrpg import main
    from tesrpg.ui import console as ui
    gd, c = _gd_char(level=18)
    inventory.add_item(c, "oghma_infinium", 1)
    i0, w0, d0, my0, mg0 = (c.attr("intelligence"), c.attr("willpower"),
                            c.skill("destruction"), c.skill("mysticism"), c.max_magicka)
    state = types.SimpleNamespace(player=c)
    _menu, _msg = ui.menu, ui.message
    ui.menu = lambda *a, **k: "hermaeus_magic"     # 玩家擇「魔法之徑」
    ui.message = lambda *a, **k: None
    try:
        main._read_book(state, gd, "oghma_infinium")
    finally:
        ui.menu, ui.message = _menu, _msg
    assert boons.has_boon(c, "hermaeus_magic")
    assert inventory.count_item(c, "oghma_infinium") == 0   # 書消耗(Mora 收回)
    assert c.attr("intelligence") == i0 + 10 and c.attr("willpower") == w0 + 6
    assert c.skill("destruction") == d0 + 8 and c.skill("mysticism") == my0 + 8
    assert c.max_magicka >= mg0 + 25
    assert c.base_attr("intelligence") == i0          # 🔴 不寫 base


def test_oghma_read_back_does_not_consume_book():
    """選擇返回(未擇徑)→ 書不消耗、無誓福(可日後再讀)。"""
    import types
    from tesrpg import main
    from tesrpg.ui import console as ui
    gd, c = _gd_char(level=18)
    inventory.add_item(c, "oghma_infinium", 1)
    state = types.SimpleNamespace(player=c)
    _menu, _msg = ui.menu, ui.message
    ui.menu = lambda *a, **k: None      # 返回
    ui.message = lambda *a, **k: None
    try:
        main._read_book(state, gd, "oghma_infinium")
    finally:
        ui.menu, ui.message = _menu, _msg
    assert inventory.count_item(c, "oghma_infinium") == 1
    assert not any(boons.has_boon(c, b)
                   for b in ("hermaeus_might", "hermaeus_shadow", "hermaeus_magic"))


def test_hermaeus_availability_and_sixteen_shrines_coexist():
    gd, c = _gd_char(level=17)
    assert "forbidden_knowledge" not in quests.available_quests(c, gd, "daedric")   # 等級不足(需 18)
    c.level = 18
    av = quests.available_quests(c, gd, "daedric")
    assert {"azura_star", "molag_bal_vault", "hircine_hunt", "boethiah_calling",
            "clavicus_bargain", "peryite_cure", "mephala_whisper", "sanguine_party",
            "malacath_curse", "meridia_beacon", "waking_nightmare", "namira_feast",
            "mind_of_madness", "twilight_sepulcher", "greymarch",
            "forbidden_knowledge"} <= set(av)
    assert gd.quests["forbidden_knowledge"]["shrine"] == "hermaeus_mora"


def test_hermaeus_content_integrity():
    gd, _ = _gd_char()
    # 三徑誓福 + 書登錄(新 kind "book" + grant_choice 三路徑)
    for b in ("hermaeus_might", "hermaeus_shadow", "hermaeus_magic"):
        assert b in gd.boons, b
    bk = gd.items["oghma_infinium"]
    assert bk["kind"] == "book" and bk["effect"]["type"] == "grant_choice"
    assert {p["boon"] for p in bk["effect"]["paths"]} == \
        {"hermaeus_might", "hermaeus_shadow", "hermaeus_magic"}
    # 神殿(高岩第二座)/地城/boss
    assert gd.world["locations"]["rivenspire"].get("shrine") == "hermaeus_mora"
    assert "forbidden_archive" in gd.dungeons and "forbidden_archive" in gd.world["locations"]
    boss = gd.dungeons["forbidden_archive"]["boss"]["enemy"]
    assert boss == "apocrypha_seeker" and gd.bestiary[boss].get("solo") is True
    assert gd.dungeons["forbidden_archive"]["boss"].get("raw") is True
    # boss 控場紀律:硬控 fear/paralyze ≤0.30 機率·turns ≤1(R43/R44)
    for atk in gd.bestiary[boss].get("attacks", []):
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("fear", "paralyze"):
            assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, atk
    # 無限祕典:僅任務 reward·不在任何 loot 表(神器規則)
    for dd in gd.dungeons.values():
        tl = [x for x in dd.get("boss", {}).get("treasure", {}).get("loot", []) if isinstance(x, str)]
        assert "oghma_infinium" not in tl + dd.get("loot", [])
    # 地城怪皆存在
    for m in gd.dungeons["forbidden_archive"]["monsters"]:
        assert m in gd.bestiary, m
    # 🔴 三徑誓福守紅線:無 sneak/任何武器技能·無 strength
    for b in ("hermaeus_might", "hermaeus_shadow", "hermaeus_magic"):
        assert not ({"sneak", "blade", "blunt", "marksman", "hand_to_hand"}
                    & set(gd.boons[b].get("skill", {}))), b
        assert "strength" not in gd.boons[b].get("attr", {}), b


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_daedric OK")
