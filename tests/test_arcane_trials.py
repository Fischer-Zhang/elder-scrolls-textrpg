"""奧術試煉(R-arcane:終極法術改任務取得 + 三系完全體大法師 + 合體王頂點)回歸測試:
- 終極法術已從所有商店 spell_stock 移除;
- requires_skill 門檻以 base_skill 判定(R21:臨時加成蒙混無效);
- requires_level 門檻;requires_quests 複數前置(合體王需三系試煉皆畢);
- reward.spells 直接授法術(去重);source="arcane" 完成不誤觸公會晉升;
- 四隻完全體大法師內容完整(solo、高抗自身元素、硬控節制 ≤0.30/turns1)。
"""
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import boons, quests

_ULTIMATES = ("incinerate", "thunderbolt", "absolute_zero")
_TRIALS = {
    "trial_fire": ("fire_archmage", "pyre_sanctum", "fire", "incinerate"),
    "trial_frost": ("frost_archmage", "rime_sanctum", "frost", "absolute_zero"),
    "trial_shock": ("shock_archmage", "tempest_sanctum", "shock", "thunderbolt"),
}


def _gd_char(level: int = 18, destruction: int = 75):
    gd = get_gamedata()
    c = build_character(gd, name="術", sex="male", race="breton",
                        birthsign="mage", class_id="battlemage")
    c.level = level
    c.skills["destruction"] = destruction
    return gd, c


# --- 商店移除 ----------------------------------------------------------
def test_ultimates_removed_from_all_shops():
    gd = get_gamedata()
    for lid, loc in gd.world["locations"].items():
        for sid in _ULTIMATES:
            assert sid not in loc.get("spell_stock", []), f"{sid} 仍在 {lid} 販售"


def test_ultimates_only_reachable_via_quest_rewards():
    gd = get_gamedata()
    # 三終極唯一取得途徑 = 三條 trial 的 reward.spells
    quest_granted = set()
    for q in gd.quests.values():
        quest_granted |= set(q.get("reward", {}).get("spells", []))
    for sid in _ULTIMATES:
        assert sid in quest_granted, f"{sid} 無任務授予途徑"


# --- requires_skill:以 base_skill 判定(R21)-------------------------
def test_requires_skill_gates_on_base_skill():
    gd, c = _gd_char(level=18, destruction=74)
    assert "trial_fire" not in quests.available_quests(c, gd, "arcane")
    c.skills["destruction"] = 75
    assert "trial_fire" in quests.available_quests(c, gd, "arcane")


def test_requires_skill_ignores_effective_bonus():
    """R21:臨時加成(誓福層)抬高 effective 仍不開放 —— 門檻只認 base_skill。"""
    gd, c = _gd_char(level=18, destruction=70)
    boons.grant(c, gd, "vaermina_nightmare")          # +10 destruction(effective 80)
    assert c.skill("destruction") >= 75 and c.base_skill("destruction") == 70
    assert "trial_fire" not in quests.available_quests(c, gd, "arcane")


# --- requires_level -----------------------------------------------------
def test_requires_level_gate():
    gd, c = _gd_char(level=17, destruction=75)
    assert "trial_fire" not in quests.available_quests(c, gd, "arcane")
    c.level = 18
    assert "trial_fire" in quests.available_quests(c, gd, "arcane")


# --- requires_quests:合體王頂點 ---------------------------------------
def test_capstone_requires_three_trials():
    gd, c = _gd_char()
    avail = quests.available_quests(c, gd, "arcane")
    assert "trial_fused" not in avail
    c.completed_quests = ["trial_fire", "trial_frost"]          # 只兩條 → 仍鎖
    assert "trial_fused" not in quests.available_quests(c, gd, "arcane")
    c.completed_quests = ["trial_fire", "trial_frost", "trial_shock"]
    assert "trial_fused" in quests.available_quests(c, gd, "arcane")


# --- reward.spells:直接授法術 + 去重 ----------------------------------
def test_reward_spells_grants_and_dedups():
    gd, c = _gd_char()
    assert "incinerate" not in c.spells
    quests._complete(c, gd, "trial_fire")
    assert "incinerate" in c.spells
    quests._complete(c, gd, "trial_fire")                      # 再次結算不應重複
    assert c.spells.count("incinerate") == 1


def test_arcane_completion_does_not_promote_guild():
    """source='arcane'、faction=null → _complete 的公會晉升區塊不應觸發。"""
    gd, c = _gd_char()
    c.factions = {"mages_guild": 2}
    quests._complete(c, gd, "trial_shock")
    assert c.factions["mages_guild"] == 2                      # 階級不變


# --- 內容完整性:完全體大法師 + 地城 ----------------------------------
def test_archmage_bosses_content_valid():
    gd = get_gamedata()
    for trial, (boss, dungeon, element, spell) in _TRIALS.items():
        assert trial in gd.quests, f"缺任務 {trial}"
        assert spell in gd.spells, f"缺法術 {spell}"
        b = gd.bestiary[boss]
        assert b.get("solo") is True, f"{boss} 應為 solo BOSS"
        assert b["resist"].get(element, 0) >= 70, f"{boss} 應高抗自身元素 {element}"
        d = gd.dungeons[dungeon]
        assert d["boss"]["enemy"] == boss and d["boss"].get("raw") is True
        # 硬控節制(R44):fear/paralyze chance<=0.30、turns<=1
        for atk in [b["attack"]] + b.get("attacks", []):
            oh = atk.get("on_hit") or {}
            if oh.get("status") in ("fear", "paralyze"):
                assert oh.get("chance", 1.0) <= 0.30 and oh.get("turns", 1) <= 1, \
                    f"{boss} 硬控過強:{oh}"


def test_fused_capstone_boss_valid():
    gd = get_gamedata()
    b = gd.bestiary["fused_archmage"]
    assert b.get("solo") is True
    # 三系皆高抗(任何單系終極法術都無法 trivialize),但 HP 明顯低於終王達貢(720)
    for el in ("fire", "frost", "shock"):
        assert b["resist"].get(el, 0) >= 70
    assert b["max_health"] < gd.bestiary["mehrunes_dagon"]["max_health"]
    assert gd.quests["trial_fused"]["requires_quests"] == ["trial_fire", "trial_frost", "trial_shock"]
    assert "spells" not in gd.quests["trial_fused"].get("reward", {})   # 頂點無第 4 法術


# --- 分散發起點:地點 arcane_trials 標籤配對任務 arcane_site(各省法師城) ----------
_SITES = {"fire": "blacklight", "frost": "winterhold", "shock": "gideon", "fused": "imperial_city"}


def test_arcane_site_tags_pair_quest_and_location():
    gd = get_gamedata()
    w = gd.world["locations"]
    assert gd.quests["trial_fire"]["arcane_site"] == "fire"
    assert gd.quests["trial_frost"]["arcane_site"] == "frost"
    assert gd.quests["trial_shock"]["arcane_site"] == "shock"
    assert gd.quests["trial_fused"]["arcane_site"] == "fused"
    for site, city in _SITES.items():
        assert w[city].get("arcane_trials") == site, f"{city} 應掛 arcane_trials={site}"
        assert "mages_guild" in w[city].get("services", []), f"{city} 需有法師公會發起點"
    # 僅這四座掛旗(無孤兒標籤)
    assert {k for k, v in w.items() if v.get("arcane_trials")} == set(_SITES.values())


def test_per_site_pickup_filters_correctly():
    """模擬 action_arcane_trials 的地點配對:每座引路人只給該系試煉,頂點僅在帝都且需三系皆畢。"""
    gd, c = _gd_char()

    def at_site(site):
        return [q for q in quests.available_quests(c, gd, "arcane")
                if gd.quests[q].get("arcane_site") == site]
    assert at_site("fire") == ["trial_fire"]
    assert at_site("frost") == ["trial_frost"]
    assert at_site("shock") == ["trial_shock"]
    assert at_site("fused") == []                       # 未完成三系 → 帝都頂點未現
    c.completed_quests = ["trial_fire", "trial_frost", "trial_shock"]
    assert at_site("fused") == ["trial_fused"]
    assert at_site("fire") == []                        # 已完成 → 該系不再現(is_done 過濾)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
