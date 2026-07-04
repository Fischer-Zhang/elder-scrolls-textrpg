"""九神信仰(R107)單元測試:單槽限時祝福 / 德行閘 / 六 hook / 朝聖贖罪(clear_infamy)。

涵蓋:祝福單槽覆蓋、到期兩路(update + ensure)、德行閘四象限(含他省賞金應放行)、
attr 快取(塔洛斯力量/朱利安諾斯智力 → recompute 資源)、阿爾凱疾病抗、凱娜瑞絲旅行減項、
澤尼薩爾買價(折扣 + 反套利地板恆守)、瑪拉治療、斯丹達爾格擋(玩家限定)、
朝聖端到端(13 階 → infamy 歸零 → crime/renown 衍生層同步歸零 = 刻意設計)、repeatable 再接、
存檔 roundtrip + 壞值防呆。無祝福 → 全 getter 恆等(byte-identical 前提)。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.models import Character
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import boons, combat, crime, divines, inventory, magic, quests, renown, world


def _state(seed=1, hour=12):
    gd = get_gamedata()
    c = build_character(gd, name="P", sex="male", race="imperial", birthsign="lady",
                        class_id="warrior")
    c.is_player = True
    st = GameState(player=c, rng=RNG(seed), time=GameTime(hour=hour))
    return gd, c, st


# --- 單槽 / 到期 / 遷移 ------------------------------------------------------
def test_single_slot_overwrite():
    gd, c, st = _state()
    divines.bless(c, st, gd, "talos")
    assert divines.active_id(c) == "talos"
    assert c.divine_attr_bonus == {"strength": 10}
    r = divines.bless(c, st, gd, "mara")          # 拜新壇 → 整包覆蓋
    assert r["replaced"] == "talos"
    assert divines.active_id(c) == "mara"
    assert c.divine_attr_bonus == {}              # 塔洛斯的力量隨之消失
    assert divines.heal_power_bonus(c) == 0.15
    r2 = divines.bless(c, st, gd, "mara")         # 同神重拜 = 刷新,非「覆蓋」
    assert r2["replaced"] == ""


def test_expiry_via_update_and_ensure():
    gd, c, st = _state()
    divines.bless(c, st, gd, "zenithar")
    assert divines.update(st, gd) == []           # 未到期:無事件
    st.time.advance(divines.BLESSING_HOURS + 1)
    evs = divines.update(st, gd)
    assert evs and evs[0]["kind"] == "blessing_expire" and evs[0]["god"] == "zenithar"
    assert divines.active_id(c) == "" and divines.buy_price_factor(c) == 1.0
    # ensure 路:過期祝福在載入時剔除
    divines.bless(c, st, gd, "akatosh")
    c.divine_blessing["expires_at"] = st.time.absolute_hours() - 1
    divines.ensure_divine_fields(c, st.time, gd)
    assert divines.active_id(c) == "" and c.divine_attr_bonus == {}


def test_ensure_heals_bad_values():
    gd, c, st = _state()
    c.divine_blessing = {"divine": "not_a_god", "expires_at": 10**9}   # 未知神 → 無效
    c.divine_attr_bonus = None
    divines.ensure_divine_fields(c, st.time, gd)
    assert c.divine_blessing == {} and c.divine_attr_bonus == {}
    c.divine_blessing = "garbage"                 # 型別壞值 → update 靜默清
    divines.update(st, gd)
    assert c.divine_blessing == {}


def test_save_roundtrip_keeps_blessing():
    gd, c, st = _state()
    divines.bless(c, st, gd, "julianos")
    d = c.to_dict()
    c2 = Character.from_dict(d)
    divines.ensure_divine_fields(c2, st.time, gd)
    assert divines.active_id(c2) == "julianos"
    assert c2.divine_attr_bonus == {"intelligence": 10}


# --- 德行閘(Oblivion 正典)--------------------------------------------------
def test_virtue_gate_quadrants():
    gd, c, st = _state()
    ok, _ = divines.can_bless(c, "賽羅迪爾")
    assert ok                                     # 新角 fame=infamy=0 → 放行
    c.infamy = 5
    ok, reason = divines.can_bless(c, "賽羅迪爾")
    assert not ok and reason == "infamy"          # 惡名超過名聲 → 拒
    c.fame = 6
    ok, _ = divines.can_bless(c, "賽羅迪爾")
    assert ok                                     # 名聲壓過惡名 → 放行
    crime.add_bounty(c, "賽羅迪爾", 40)
    ok, reason = divines.can_bless(c, "賽羅迪爾")
    assert not ok and reason == "bounty"          # 本省賞金 → 拒
    ok, _ = divines.can_bless(c, "天際")
    assert ok                                     # 他省賞金不擋(法度各管各的)


# --- 六 hook ---------------------------------------------------------------
def test_talos_strength_feeds_attr_and_resources():
    gd, c, st = _state()
    s0, f0 = c.attr("strength"), c.max_fatigue
    divines.bless(c, st, gd, "talos")
    assert c.attr("strength") == s0 + 10
    assert c.max_fatigue > f0                     # 力量 → 體力上限(recompute 已跑,R05)
    assert c.base_attr("strength") + c.equip_attr_bonus.get("strength", 0) <= s0  # 絕不寫 base


def test_julianos_intelligence_feeds_magicka():
    gd, c, st = _state()
    m0 = c.max_magicka
    divines.bless(c, st, gd, "julianos")
    assert c.attr("intelligence") == 10 + sum((
        c.attributes.get("intelligence", 0), c.equip_attr_bonus.get("intelligence", 0),
        c.boon_attr_bonus.get("intelligence", 0)))
    assert c.max_magicka > m0                     # 智力 → 魔力上限(recompute)


def test_arkay_disease_resist_in_entity_resist():
    gd, c, st = _state()
    base = magic.entity_resist(c, gd).get("disease", 0)
    divines.bless(c, st, gd, "arkay")
    assert magic.entity_resist(c, gd).get("disease", 0) == base + 30


def test_kynareth_travel_bonus():
    gd, c, st = _state()
    assert divines.travel_factor_bonus(c, gd) == 0.0
    divines.bless(c, st, gd, "kynareth")
    assert divines.travel_factor_bonus(c, gd) == 0.10


def test_zenithar_discount_and_floor_holds():
    gd, c, st = _state()
    c.location_id = "leyawiin"
    p0 = world.buy_price(c, gd, "steel_dagger")
    divines.bless(c, st, gd, "zenithar")
    p1 = world.buy_price(c, gd, "steel_dagger")
    assert p1 < p0                                # 商賈之神的折扣
    # 反套利地板恆守:疊滿議價/聲望/祝福,買價仍嚴格 > 賣價(全品項抽查)
    c.fame = 400                                  # R101 名聲折扣也疊上
    for iid in ("steel_dagger", "minor_healing_potion", "lockpick"):
        assert world.buy_price(c, gd, iid) > world.sell_price(c, gd, iid)


def test_mara_heal_bonus_only_with_blessing():
    gd, c, st = _state()
    c.spells = list(c.spells) + ["minor_heal"]
    c.magicka = c.max_magicka = 300
    c.health = 1
    magic.cast(c, gd, "minor_heal", st.rng, state=st)
    healed_plain = c.health - 1
    divines.bless(c, st, gd, "mara")
    c.health = 1
    c.magicka = 300
    magic.cast(c, gd, "minor_heal", st.rng, state=st)
    healed_blessed = c.health - 1
    assert healed_blessed > healed_plain          # +15% 治療


def test_stendarr_block_reduces_damage_player_only():
    gd, c, st = _state()
    c.skills["block"] = 40
    foe = combat.spawn_creature(gd, "bandit", RNG(1))
    # 同 seed 比對:有祝福的格擋應更硬(命中/roll 序不動 —— 祝福不擲 rng)
    dmg_plain = dmg_blessed = None
    for seed in range(1, 20):
        c.health = c.max_health
        c.fatigue = c.max_fatigue
        ev = combat.resolve_attack(foe, c, gd, RNG(seed), defender_blocking=True)
        if not ev["hit"] or ev["damage"] <= 0:
            continue
        dmg_plain = ev["damage"]
        divines.bless(c, st, gd, "stendarr")
        c.health = c.max_health
        c.fatigue = c.max_fatigue
        ev2 = combat.resolve_attack(foe, c, gd, RNG(seed), defender_blocking=True)
        dmg_blessed = ev2["damage"]
        divines.bless(c, st, gd, "mara")          # 換掉祝福,還原乾淨狀態
        c.divine_blessing = {}
        divines.recompute(c, st, gd)
        break
    assert dmg_plain is not None, "找不到命中樣本"
    assert dmg_blessed < dmg_plain                # 斯丹達爾:格擋更硬
    # 非玩家不吃(gate 在 _is_player):怪物格擋無祝福概念 → getter 對怪物安全回 0
    assert divines.block_bonus(foe) == 0.0


# --- 朝聖贖罪(端到端)-------------------------------------------------------
def test_pilgrimage_clears_infamy_and_derived_layers():
    gd, c, st = _state()
    c.infamy = 30
    c.fame = 2
    assert crime.outlaw_standing(c) > 0 and crime.fence_bonus(c) > 0
    assert renown.notoriety_social_tier(c) > 0
    quests.accept_quest(c, gd, divines.PILGRIMAGE_QID)
    q = gd.quests[divines.PILGRIMAGE_QID]
    for stg in q["stages"]:
        obj = stg["objective"]
        if obj["type"] == "collect":
            inventory.add_item(c, obj["item"], obj["count"])
        elif obj["type"] == "reach":
            c.location_id = obj["location"]
        elif obj["type"] == "kill":
            for _ in range(obj["count"]):
                quests.record_kill(c, obj["creature"])
        quests.check_completion(c, gd)
    assert divines.PILGRIMAGE_QID not in c.quests          # 已走完
    assert c.infamy == 0                                    # 惡名歸零(KotN 正典)
    # 衍生層同步歸零 = 刻意設計(R84「惡名終身」的使用者拍板例外)
    assert crime.outlaw_standing(c) == 0 and crime.fence_bonus(c) == 0.0
    assert renown.notoriety_social_tier(c) == 0
    assert c.fame == 2                                      # 不動名聲
    # ⚠ 成就為 live accessor:惡名成就在歸零後會回到未達成顯示(接受;見 R107)


def test_pilgrimage_repeatable_and_keeps_bounty():
    gd, c, st = _state()
    c.infamy = 10
    crime.add_bounty(c, "賽羅迪爾", 120)
    quests.accept_quest(c, gd, divines.PILGRIMAGE_QID)
    for stg in gd.quests[divines.PILGRIMAGE_QID]["stages"]:
        obj = stg["objective"]
        if obj["type"] == "collect":
            inventory.add_item(c, obj["item"], obj["count"])
        elif obj["type"] == "reach":
            c.location_id = obj["location"]
        else:
            for _ in range(obj["count"]):
                quests.record_kill(c, obj["creature"])
        quests.check_completion(c, gd)
    assert c.infamy == 0
    assert crime.bounty(c, "賽羅迪爾") == 120     # 法律賞金不清(朝聖贖罪名不贖法度)
    assert divines.PILGRIMAGE_QID not in c.completed_quests   # repeatable → 可再走
    quests.accept_quest(c, gd, divines.PILGRIMAGE_QID)         # 再接不炸
    assert divines.PILGRIMAGE_QID in c.quests


# --- 佈點 schema -------------------------------------------------------------
def test_world_divine_fields_are_legal_and_complete():
    gd = get_gamedata()
    placed = {}
    for lid, loc in gd.world["locations"].items():
        god = loc.get("divine")
        if god:
            assert god in divines.BLESSINGS, f"{lid} 的 divine 指向未知神:{god}"
            assert god not in placed, f"{god} 佈點重複:{placed[god]} 與 {lid}"
            placed[god] = lid
    assert set(placed) == set(divines.BLESSINGS), f"九神祭壇缺席:{set(divines.BLESSINGS) - set(placed)}"


# --- R115 九神深線:神之選民試煉 + 永久神性誓福(首位 阿卡托什) ---------------
_WEAPON_SKILLS = {"blade", "blunt", "marksman", "hand_to_hand"}   # 破偷襲/武傷鏈的技能(R45 紅線)


def test_akatosh_trial_level_gate_and_content():
    """時龍的召選:requires_level 15 閘 + divine 分流 + boss/地城/節點 FK + 控場節制(R43/R44)。"""
    gd, c, st = _state()
    c.level = 10
    assert "akatosh_trial" not in quests.available_quests(c, gd, "divine")   # 等級不足不現
    c.level = 15
    assert "akatosh_trial" in quests.available_quests(c, gd, "divine")
    assert gd.quests["akatosh_trial"]["divine"] == "akatosh"                 # 祭壇分流鍵
    assert "akatosh_covenant" in gd.boons
    assert "kvatch_undercroft" in gd.dungeons and "kvatch_undercroft" in gd.world["locations"]
    boss = gd.dungeons["kvatch_undercroft"]["boss"]["enemy"]
    assert boss == "time_forsaken" and gd.bestiary[boss].get("solo") is True
    for atk in gd.bestiary[boss].get("attacks", []):                         # 硬控 ≤0.30、fear/paralyze turns≤1
        oh = atk.get("on_hit") or {}
        if oh.get("status") in ("paralyze", "fear", "stagger"):
            assert oh.get("chance", 1.0) <= 0.30, atk
            if oh.get("status") in ("paralyze", "fear"):
                assert oh.get("turns", 1) <= 1, atk
    for m in gd.dungeons["kvatch_undercroft"]["monsters"]:                   # 地城怪皆存在
        assert m in gd.bestiary, m
    assert gd.world["locations"]["kvatch"].get("divine") == "akatosh"        # 祭壇節點對映


def test_akatosh_trial_grants_covenant_boon_end_to_end():
    """接取 → 獻祭(collect)+ 清地窟 → reward.grant_boon 授永久誓福(端到端)。"""
    gd, c, st = _state()
    c.level = 15
    end0 = c.attr("endurance")
    quests.accept_quest(c, gd, "akatosh_trial", 0)
    inventory.add_item(c, "minor_magicka_potion", 2)
    c.location_id = "kvatch_undercroft"
    quests.record_dungeon_clear(c, "kvatch_undercroft")
    quests.check_completion(c, gd)
    assert "akatosh_trial" in c.completed_quests
    assert boons.has_boon(c, "akatosh_covenant")
    assert c.attr("endurance") == end0 + 10          # 誓福 attr 疊上有效值(不寫 base)
    assert "akatosh_covenant_earned" in c.world_events_fired
    # 接取後不再列於祭壇可接清單(避免重複接)
    assert "akatosh_trial" not in quests.available_quests(c, gd, "divine")


def test_divine_boons_respect_red_lines():
    """守整條九神深線的 R45 紅線:任何 source='divine' 任務授予的誓福皆不得餵 sneak/武器技能、
    strength 不得超過達貢上限 → 未來加新神的誓福自動被此測試把關(不必逐神補測)。"""
    gd = get_gamedata()
    checked = 0
    for qid, q in gd.quests.items():
        if q.get("source") != "divine":
            continue
        gb = q.get("reward", {}).get("grant_boon")
        if not gb:
            continue
        checked += 1
        spec = gd.boons[gb]
        sk = set(spec.get("skill", {}))
        assert "sneak" not in sk, f"{gb} 誓福餵 sneak(破紅線)"
        assert not (_WEAPON_SKILLS & sk), f"{gb} 誓福餵武器技能(破紅線):{_WEAPON_SKILLS & sk}"
        assert spec.get("attr", {}).get("strength", 0) <= 18, f"{gb} strength 超過達貢上限"
    assert checked >= 1, "未偵測到任何 source='divine' 授誓福任務(接線斷?)"


def test_all_divine_trials_content_integrity():
    """所有神之選民試煉(source=divine 且帶 `divine` 欄)的內容完整性 —— 未來加新神自動被此把關:
    divine∈BLESSINGS·有 requires_level 閘·grant_boon∈boons·有 clear_dungeon boss 階·
    地城∈dungeons+world·boss 為 solo·怪皆存在·硬控 chance≤0.30/fear·paralyze turns≤1(R43/R44)。"""
    gd = get_gamedata()
    trials = [(qid, q) for qid, q in gd.quests.items()
              if q.get("source") == "divine" and q.get("divine")]
    assert trials, "無任何神之選民試煉(接線斷?)"
    for qid, q in trials:
        assert q["divine"] in divines.BLESSINGS, f"{qid} divine 指向未知神:{q['divine']}"
        assert q.get("requires_level"), f"{qid} 缺 requires_level 閘"
        assert q["reward"].get("grant_boon") in gd.boons, f"{qid} grant_boon 未登錄"
        dids = [s["objective"]["dungeon"] for s in q.get("stages", [])
                if s.get("objective", {}).get("type") == "clear_dungeon"]
        assert dids, f"{qid} 無 clear_dungeon 階(試煉須有 boss 戰)"
        for did in dids:
            assert did in gd.dungeons and did in gd.world["locations"], f"{qid} 地城 {did} 缺席"
            boss = gd.dungeons[did]["boss"]["enemy"]
            assert gd.bestiary[boss].get("solo") is True, f"{did} boss {boss} 非 solo"
            for atk in gd.bestiary[boss].get("attacks", []):
                oh = atk.get("on_hit") or {}
                if oh.get("status") in ("paralyze", "fear", "stagger"):
                    assert oh.get("chance", 1.0) <= 0.30, (boss, atk)
                    if oh.get("status") in ("paralyze", "fear"):
                        assert oh.get("turns", 1) <= 1, (boss, atk)
            for m in gd.dungeons[did]["monsters"]:
                assert m in gd.bestiary, (did, m)


def run():
    for name in sorted(globals()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  ✓ {name}")
