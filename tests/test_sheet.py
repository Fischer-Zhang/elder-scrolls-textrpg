"""角色卡升級(充實顯示 + 互動式檢視)的測試:
所有 sheet_* 與 character_sheet 對多種角色狀態渲染無 traceback;互動 action 走訪全項;
**唯讀鐵律**:檢視角色卡不改任何 char 狀態、不耗時(尤其不可呼叫會扣體力的 practice_cost)。"""

import copy
import io

from rich.console import Console

from tesrpg import main as M
from tesrpg.ui import console as ui
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import factions


def _silence():
    ui.console = Console(file=io.StringIO(), width=100)


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="dunmer",
                        birthsign="lady", class_id="knight")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, GameState(player=c, time=GameTime(), rng=RNG(3))


# --- 各 sheet_* 渲染無 traceback(多種狀態)--------------------------------
def _render_all(gd, st):
    c = st.player
    ui.character_sheet(c, gd)
    ui.sheet_resistances(c, gd)
    ui.sheet_effects(c, st, gd)
    ui.sheet_factions(c, gd)
    ui.sheet_masteries(c, gd)
    ui.sheet_power(c, st, gd)
    ui.sheet_bounty(c, gd)
    ui.sheet_equipment(c, gd)
    ui.sheet_vampirism(c, gd)
    ui.sheet_spellbook(c, gd)
    for sid in gd.skills:
        ui.sheet_skill_detail(c, gd, sid)


def test_renders_rich_character():
    # 參數化多狀態煙霧:對每個 state 全 sheet_* 無 traceback(plain/rich/vampire 三分支零流失)
    def _plain():
        # 無公會/無效果/無通緝/非吸血鬼/空裝(跑 null 分支)
        return _char()

    def _rich():
        gd, st = _char(fame=20, infamy=5)
        c = st.player
        factions.join(c, "fighters_guild"); c.factions["fighters_guild"] = 3
        c.bounties = {"賽羅迪爾": 120, "天際": 40}
        c.active_effects = [{"kind": "shield", "magnitude": 20, "turns": 3},
                            {"kind": "dot", "element": "fire", "magnitude": 4, "turns": 2},
                            {"kind": "regen", "magnitude": 10, "turns": 4}]
        return gd, st

    def _vampire():
        gd, st = _char()
        c = st.player
        c.is_vampire = True
        c.vampire_stage = 2
        c.vampire_attr_bonus = {"strength": 10, "speed": 10}
        c.vampire_skill_bonus = {"sneak": 10}
        c.vampire_resist = {"disease": 100, "frost": 20, "fire": -20}
        return gd, st

    for build in (_plain, _rich, _vampire):
        _silence()
        gd, st = build()
        _render_all(gd, st)                   # 三狀態各自全 sheet_* 無 traceback

    # spellbook 分組/作用 + 空書 edge:smoke 不擷取輸出,須額外擷取斷言(原 test_spellbook_*)
    _silence()
    gd, st = _char()
    c = st.player
    c.spells = ["flames", "heal", "oakflesh", "conjure_familiar", "fear", "soul_trap"]
    buf = io.StringIO(); ui.console = Console(file=buf, width=100)
    ui.sheet_spellbook(c, gd)
    out = buf.getvalue()
    assert "法術書" in out and "毀滅" in out and "火焰傷害" in out      # 分組 + 作用
    # 無法術:不崩潰(console.py:1266-1268 空書分支)
    c.spells = []
    ui.sheet_spellbook(c, gd)


# --- 唯讀鐵律:檢視不改狀態、不耗時 ----------------------------------------
def test_views_are_read_only():
    _silence()
    gd, st = _char(fame=10)
    c = st.player
    factions.join(c, "mages_guild"); c.factions["mages_guild"] = 2
    c.active_effects = [{"kind": "shield", "magnitude": 15, "turns": 2}]
    before = copy.deepcopy(c.to_dict())
    t0 = st.time.absolute_hours()
    _render_all(gd, st)
    assert c.to_dict() == before, "角色卡檢視不得改動任何 char 狀態(唯讀鐵律)"
    assert st.time.absolute_hours() == t0, "角色卡檢視不得推進時間"


# --- 互動 action 走訪全項(腳本化 menu)-----------------------------------
def test_action_character_sheet_walks_all_views():
    _silence()
    gd, st = _char(fame=8)
    c = st.player
    factions.join(c, "thieves_guild")
    c.active_effects = [{"kind": "stagger", "turns": 1}]
    c.is_vampire = True; c.vampire_stage = 1
    c.spells = ["flames", "heal"]
    # 腳本:逐一選每個檢視鍵(技能詳情會再彈一次技能選單→選 blade),最後返回(None)
    seq = iter(["resist", "effects", "factions", "mastery", "power", "bounty",
                "equip", "spellbook", "vampire", "skill", "blade", "resheet", None])
    saved = ui.menu
    ui.menu = lambda *a, **k: next(seq, None)
    try:
        before = copy.deepcopy(c.to_dict())
        ret = M.action_character_sheet(st, gd)
        assert ret is None
        assert c.to_dict() == before          # 全程唯讀
    finally:
        ui.menu = saved


def test_corrupt_equipped_id_does_not_crash():
    # 防毀損存檔:equipped/offhand/weapon 含未知 id 時,角色卡與裝備檢視不得崩潰(對抗審查修正)
    _silence()
    gd, st = _char()
    c = st.player
    c.equipped = {"helmet": "NONEXISTENT_ITEM", "cuirass": "ALSO_BOGUS"}
    c.offhand = "BOGUS_OFFHAND"
    c.weapon = "BOGUS_WEAPON"
    ui.character_sheet(c, gd)        # overview 每次都讀 worn_armor_rating
    ui.sheet_equipment(c, gd)        # 名稱 + 護甲 + 套裝 + 加成
    from tesrpg.systems import inventory
    assert inventory.worn_armor_rating(c, gd) == 0          # 未知 id 視為 0,不崩潰
    assert inventory.equipment_bonuses(c, gd) == {"skills": {}, "attrs": {}, "resist": {}, "resources": {}}
    assert gd.item_name("BOGUS_WEAPON") == "BOGUS_WEAPON"   # 顯示回退為原 id,不崩潰


def test_set_bonus_shows_set_name():
    # 套裝加成行需顯示真正的套裝名稱(名稱在父層 armor_sets[mat]['name'],非 bonus 子物件)
    _silence()
    gd, st = _char()
    c = st.player
    from tesrpg.systems import inventory
    # 找一組同材質四件套
    mat = next(iter(gd.armor_sets))
    set_items = {}
    for slot in inventory.SET_SLOTS:
        iid = next((i for i, d in gd.items.items()
                    if d.get("slot") == slot and d.get("material") == mat), None)
        assert iid, f"找不到 {mat} {slot}"
        set_items[slot] = iid
    c.equipped = dict(set_items)
    assert inventory.active_set_bonus(c, gd) is not None
    expected = gd.armor_sets[mat]["name"]
    # 渲染並擷取輸出,確認套裝名稱有出現(非空白)
    buf = io.StringIO(); ui.console = Console(file=buf, width=100)
    ui.sheet_equipment(c, gd)
    assert expected in buf.getvalue(), f"套裝加成未顯示套裝名稱 {expected}"


def test_every_spell_summarisable():
    # 每道法術都要能渲染出「作用」摘要,且不落入泛用後備(=所有 effect kind 都已涵蓋)
    gd = get_gamedata()
    for sid in gd.spells:
        summ = ui.spell_effect_summary(gd, sid)
        assert summ and summ != "效果", f"{sid} 未被效果摘要涵蓋:{summ}"
    # apply_status 須標明對象(對抗審查:enemy DoT vs self regen 不可同形)
    assert "使目標" in ui.spell_effect_summary(gd, "poison_cloud")   # 敵方 DoT
    assert "自身" in ui.spell_effect_summary(gd, "renewal")          # 自我再生


def test_every_skill_has_mechanic_and_detail_shows_it():
    # 每個技能都要有「作用」說明,且技能詳情會把它印出來(使用者:看不到技能詳細作用)
    gd = get_gamedata()
    for sid, sd in gd.skills.items():
        assert sd.get("mechanic"), f"{sid} 缺 mechanic(技能詳細作用)說明"
    gd2, st = _char()
    buf = io.StringIO(); ui.console = Console(file=buf, width=100)
    ui.sheet_skill_detail(st.player, gd2, "block")
    out = buf.getvalue()
    assert "作用" in out and gd2.skills["block"]["mechanic"][:6] in out


def test_enchant_and_artifact_effects_visible():
    """神器/附魔效果在 UI 可見:_enchant_desc 描述各 enchant 種類;武器附魔在 weapon_line、飾品神器在 item_label。"""
    from tesrpg.systems import inventory
    gd, st = _char(); c = st.player
    assert ui._enchant_desc(gd, "mehrunes_razor") == "雷電傷+25"    # 武器元素附魔
    assert ui._enchant_desc(gd, "hircine_ring") == "可隨意獸化"      # 旗標型神器效果可見
    assert ui._enchant_desc(gd, "archmage_robe") == "魔力上限+25"    # 護甲附魔
    assert ui._enchant_desc(gd, "steel_sword") == ""               # 無附魔 → 不顯示
    inventory.add_item(c, "mehrunes_razor", 1); inventory.equip_weapon(c, gd, "mehrunes_razor")
    assert "雷電傷+25" in ui.weapon_line(c, gd)                      # 武器附魔在武器行可見
    assert "可隨意獸化" in ui.item_label(gd, c, "hircine_ring")      # 神器效果在背包可見


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_sheet OK")
