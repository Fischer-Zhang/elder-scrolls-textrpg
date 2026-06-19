"""戴德拉誓福引擎 + 神殿任務(R45)回歸測試:
- 通用誓福獨立疊加層(grant/聚合/多誓福相加/不污染 base/存檔 round-trip/舊檔遷移);
- reward.grant_boon 派發(新 boons 登錄表 vs 達貢 legacy 各走各的);
- 神殿任務可接門檻(requires_level/requires_fame)+ 神殿(shrine)分流;
- 首位親王阿祖拉深線雙結局(淨化→永久誓福 / 墮化→神器)+ 內容資料完整(boss solo/控場節制/地城有任務)。
"""
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
    magres0 = magic.entity_resist(c, gd).get("magic", 0)
    boons.grant(c, gd, "azura")
    assert c.attr("willpower") == w0 + 8 and c.attr("intelligence") == i0 + 6
    assert c.skill("mysticism") == myst0 + 10
    # max_magicka 升幅 = 智力 +6 的公式貢獻 + 誓福固定 +20(故 ≥ +20)
    assert c.boon_magic_bonus == 20 and c.max_magicka >= mg0 + 20
    assert magic.entity_resist(c, gd).get("magic", 0) == magres0 + 20
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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_daedric OK")
