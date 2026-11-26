"""R221 事件檢定第二批:14 個零檢定技能各補 1 個事件檢定選項(使用者 2026-11-26 拍板範圍 A;其餘依提案預設)。

緣起:R196 / R198 之後 22 個技能中仍有 14 個零檢定(格擋 / 鈍器 / 徒手 / 重甲 / 輕甲 / 射術 / 毀滅 / 變化 / 召喚 / 幻術 / 恢復 / 煉金 / 交易 / 鍛造)。
做法:純改 `events.json`(零程式、零新效果型別):14 個選項附加到 11 個既有事件尾端,每個事件至多 2 個,既有數字鍵不位移。

規則(沿 R196 / R198):
  · 失敗複製同事件既有檢定的失敗效果(戰鬥 / 失金 / 受傷);成功必練被檢定的技能;標籤句尾 = 正典技能名;事件文字半形逗號 / 驚嘆號
  · 「化解型」(11 個,掛在威脅事件):成功 = 脫身 + 經驗,不給戰利品;鍛造例外(複製同事件安全檢定的成功金幣)
  · 「增益型」(3 個:恢復 / 交易 / 煉金,掛在無威脅事件):收益有界、**不得被支配**(成功比預設選項好、失敗不比預設好)
  · 措辭不依賴裝備(事件不能檢查持有什麼武器 / 盾):「抄起粗木棍」「擲出石子」而非「揮鈍器」「拉弓」
  · 零存檔欄位;sim 不走事件 → byte-identical 不當安全證據

守衛:
  1. 22 個技能每個至少 1 個事件檢定(新契約:日後新增技能必須同時補一個事件檢定)
  2. 14 個新選項的資料形狀 / 位置(索引 = 原選項數)/ 既有選項文字與順序不動 / 效果逐項釘死
  3. 失敗比照同事件既有檢定(化解型);增益型的不被支配界線
  4. 端到端:真走 `main.run_event`,成功 / 失敗分支的結算(經驗 / 戰鬥 / 受傷 / 金幣 / 名聲 / 物品)與 chip = `events.check_chance`(含幸運)
"""
import io

from rich.console import Console
import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import events, stats

gd = get_gamedata()

# R221 前各宿主事件的選項文字(= 新選項的索引起點;既有選項不得被動)
_OLDS = {
    "camp_ambush": ['起身迎戰', '悄悄遁入暗處(潛行)', '翻上高處躲避(運動)'],
    "wild_beast": ['搶先出手', '緩緩後退(潛行)', '拔腿狂奔(運動)'],
    "highwayman": ['乖乖付過路費', '出言威嚇(口才)', '拔劍相向', '拔腿就跑(運動)'],
    "street_urchin": ['一把抓住他的手(安全)', '由他去吧', '拔腿追上去(運動)'],
    "morrowind_ashstorm": ['拉起頭巾趕路', '就地掩蔽等風停', '疾行穿越風暴(運動)'],
    "skyrim_blizzard": ['頂風硬闖(運動)', '找處岩壁避風'],
    "hammerfell_predator": ['搶在牠破沙前出手', '屏息潛伏、悄然繞行(潛行)', '奔向堅實的地面(運動)'],
    "trapped_chest": ['仔細拆解機關後開啟', '直接撬開(安全)', '放著別碰'],
    "injured_traveler": ['用治療藥水救他', '施捨幾枚金幣', '搜刮他的財物', '視而不見地走開'],
    "merchant_caravan": ['購買補給', '打聽道上見聞', '繼續趕路'],
    "blackmarsh_forage": ['小心採集這片毒沼', '沒興趣'],
}


def _xp(skill, amount=0.6):
    return {"type": "skill_xp", "skill": skill, "amount": amount}


_WOLF = [{"type": "combat", "creature": "wolf"}]
_SPIDER = [{"type": "combat", "creature": "frostbite_spider"}]
_BANDIT = [{"type": "combat", "creature": "bandit"}]
_RIPPER = [{"type": "combat", "creature": "dune_ripper"}]

# (事件, 索引, 標籤, 技能, 難度, 成功效果, 失敗效果, 型別)  —— 測試自己的獨立規格(不從 events.json 反推)
_SPEC = [
    ("camp_ambush", 3, "舉臂格開撲咬(格擋)", "block", 35, [_xp("block")], _WOLF, "defuse"),
    ("camp_ambush", 4, "擲出一團火球逼退牠(毀滅)", "destruction", 38, [_xp("destruction")], _WOLF, "defuse"),
    ("wild_beast", 3, "抄起粗木棍逼退牠(鈍器)", "blunt", 38, [_xp("blunt")], _SPIDER, "defuse"),
    ("wild_beast", 4, "瞄準牠的眼睛擲出石子(射術)", "marksman", 38, [_xp("marksman")], _SPIDER, "defuse"),
    ("highwayman", 4, "幻出數道人影唬他(幻術)", "illusion", 42, [_xp("illusion")], _BANDIT, "defuse"),
    ("highwayman", 5, "召出魔靈嚇阻(召喚)", "conjuration", 40, [_xp("conjuration")], _BANDIT, "defuse"),
    ("street_urchin", 3, "反手扣住他的肩膀(徒手)", "hand_to_hand", 35, [_xp("hand_to_hand", 0.4)], [{"type": "gold", "amount": -10}], "defuse"),
    ("morrowind_ashstorm", 3, "披著甲冑硬扛灰燼(重甲)", "heavy_armor", 38, [_xp("heavy_armor")], [{"type": "damage", "amount": 8}], "defuse"),
    ("skyrim_blizzard", 2, "以護體術隔開風雪(變化)", "alteration", 38, [_xp("alteration")], [{"type": "damage", "amount": 6}], "defuse"),
    ("hammerfell_predator", 3, "輕裝疾踏沙面(輕甲)", "light_armor", 40, [_xp("light_armor")], _RIPPER, "defuse"),
    ("trapped_chest", 3, "以匠人之眼拆解機關(鍛造)", "smithing", 38, [{"type": "gold", "amount": 25}, _xp("smithing")],
     [{"type": "damage", "amount": 12}], "defuse"),
    ("injured_traveler", 4, "以恢復術為他療傷(恢復)", "restoration", 35,
     [{"type": "gold", "amount": 25}, {"type": "fame", "amount": 4}, _xp("restoration")], [], "boon"),
    ("merchant_caravan", 3, "討價還價(交易)", "mercantile", 35,
     [{"type": "gold", "amount": -24}, {"type": "item", "item": "healing_potion", "qty": 1}, _xp("mercantile")], [], "boon"),
    ("blackmarsh_forage", 2, "辨識毒性再採(煉金)", "alchemy", 38,
     [{"type": "forage_pool", "pool": "swamp"}, {"type": "item", "item": "nightshade", "qty": 1}, _xp("alchemy")],
     [{"type": "damage", "amount": 6}], "boon"),
]
_NEW_SKILLS = {"block", "blunt", "hand_to_hand", "heavy_armor", "light_armor", "marksman", "destruction", "alteration",
               "conjuration", "illusion", "restoration", "alchemy", "mercantile", "smithing"}


# --- 夾具(同 test_events_r196)-----------------------------------------------
class _RecRNG(RNG):
    def __init__(self, seed=0, result=True):
        super().__init__(seed)
        self.ps = []
        self.result = result

    def chance(self, p):
        self.ps.append(p)
        return self.result


def _char(luck=None, **skills):
    c = build_character(gd, name="客", sex="male", race="imperial", birthsign="warrior", class_id="warrior")
    c.location_id = "imperial_road"
    c.skills.update(skills)
    if luck is not None:
        c.attributes["luck"] = luck
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.gold = 100
    return c


def _drive(c, eid, key, result=True):
    st = GameState(player=c, time=GameTime(), rng=_RecRNG(result=result))
    cap = {"opts": None}
    battles, xp_calls = [], []
    orig_spawn, orig_use = M.combat.spawn_creature, events.progression.use_skill

    def spy_spawn(gamedata, tid, rng):
        battles.append(tid)
        return orig_spawn(gamedata, tid, rng)

    def spy_use(char, gamedata, skill_id, xp):
        xp_calls.append((skill_id, xp))
        return orig_use(char, gamedata, skill_id, xp)

    def fake_menu(title, options, allow_back=False):
        cap["opts"] = list(options)
        return str(key)

    saved = (ui.menu, M.run_battle)
    ui.menu, M.run_battle = fake_menu, (lambda state, gamedata, foe: None)
    M.combat.spawn_creature, events.progression.use_skill = spy_spawn, spy_use
    try:
        ret = M.run_event(st, gd, eid)
    finally:
        ui.menu, M.run_battle = saved
        M.combat.spawn_creature, events.progression.use_skill = orig_spawn, orig_use
    return {"opts": cap["opts"], "ps": st.rng.ps, "battles": battles, "xp": xp_calls, "ret": ret, "state": st}


# ---------------------------------------------------------------- 1. 覆蓋契約
def test_every_skill_has_at_least_one_event_check():
    """新契約:日後新增技能,必須同時補一個事件檢定(否則「做什麼練什麼」在事件這條路上對它是空的)。"""
    have = {o["check"]["skill"] for e in gd.events.values() for o in e["options"] if "check" in o}
    assert set(gd.skills) - have == set(), sorted(set(gd.skills) - have)
    assert _NEW_SKILLS <= have and len(_NEW_SKILLS) == 14 and len(gd.skills) == 22


# ---------------------------------------------------------------- 2. 資料形狀 / 位置
def test_fourteen_options_shape_position_and_untouched_neighbours():
    assert len(_SPEC) == 14 and {s[3] for s in _SPEC} == _NEW_SKILLS, "14 個技能各一個"
    for eid, idx, label, skill, diff, ok_eff, bad_eff, kind in _SPEC:
        opts = gd.events[eid]["options"]
        olds = _OLDS[eid]
        assert [o["text"] for o in opts[:len(olds)]] == olds, f"{eid}:既有選項文字與順序不得動(數字鍵不位移)"
        assert idx >= len(olds), (eid, idx)
        o = opts[idx]
        assert o["text"] == label and label.endswith(f"({gd.skill_name(skill)})"), (eid, label)
        chk = o["check"]
        assert (chk["skill"], chk["difficulty"]) == (skill, diff), (eid, skill)
        assert chk["success"]["effects"] == ok_eff, (eid, skill, "成功效果")
        assert chk["failure"]["effects"] == bad_eff, (eid, skill, "失敗效果")
        for br in ("success", "failure"):
            t = chk[br]["text"]
            assert isinstance(t, str) and t.strip(), (eid, skill, br)
            assert not any(ch in t for ch in "，！？"), (eid, skill, br, "事件文字用半形逗號 / 驚嘆號")
        extra = set(o) - {"text", "check", "requirements"}
        assert not extra, (eid, extra, "不得出現新鍵")
        assert ("requirements" in o) == (skill == "mercantile"), (eid, "只有交易需要條件(付得起)")
    for eid, olds in _OLDS.items():                                  # 每個事件總選項數 = 原數 + 新增數(至多 2 個)
        n_new = sum(1 for s in _SPEC if s[0] == eid)
        assert 1 <= n_new <= 2 and len(gd.events[eid]["options"]) == len(olds) + n_new, eid
    for eid, idx, *_ in _SPEC:                                       # 同一事件的新選項索引連續接在原選項之後
        idxs = sorted(s[1] for s in _SPEC if s[0] == eid)
        assert idxs == list(range(len(_OLDS[eid]), len(_OLDS[eid]) + len(idxs))), eid
    for eid, e in gd.events.items():                                 # 同事件同技能至多一個檢定
        sk = [o["check"]["skill"] for o in e["options"] if "check" in o]
        assert len(sk) == len(set(sk)), (eid, sk)


# ---------------------------------------------------------------- 3. 失敗比照 / 不被支配
def test_defuse_options_mirror_the_failure_of_every_pre_existing_check_in_the_event():
    n = 0
    for eid, idx, label, skill, diff, ok_eff, bad_eff, kind in _SPEC:
        if kind != "defuse":
            continue
        sibs = [o["check"] for o in gd.events[eid]["options"][:len(_OLDS[eid])] if "check" in o]
        assert sibs, f"{eid}:化解型必須有既有檢定可比照(否則失敗後果無從比照)"
        for s in sibs:
            assert s["failure"]["effects"] == bad_eff, (eid, skill, "失敗須複製同事件既有檢定")
        n += 1
    assert n == 11
    # 化解型成功不給戰利品:只有經驗(鍛造例外:複製同事件安全檢定的成功金幣)
    for eid, idx, label, skill, diff, ok_eff, bad_eff, kind in _SPEC:
        if kind == "defuse" and skill != "smithing":
            assert [e["type"] for e in ok_eff] == ["skill_xp"], (eid, skill)
    sec = gd.events["trapped_chest"]["options"][1]["check"]["success"]["effects"]
    assert [e for e in sec if e["type"] == "gold"] == [e for e in
            gd.events["trapped_chest"]["options"][3]["check"]["success"]["effects"] if e["type"] == "gold"]


def test_boon_options_are_bounded_and_not_dominated():
    ev = gd.events
    # 恢復:不耗藥水 → 收益不超過「用治療藥水救他」;失敗無懲罰(沒效果而已)
    pot = ev["injured_traveler"]["options"][0]["effects"]
    pot_gold = sum(e["amount"] for e in pot if e["type"] == "gold")
    pot_fame = sum(e["amount"] for e in pot if e["type"] == "fame")
    r = ev["injured_traveler"]["options"][4]["check"]
    assert sum(e["amount"] for e in r["success"]["effects"] if e["type"] == "gold") <= pot_gold
    assert sum(e["amount"] for e in r["success"]["effects"] if e["type"] == "fame") <= pot_fame
    assert r["failure"]["effects"] == []
    # 交易:付得起才出現(requirements 金額 = 價格,金幣永不為負);同樣換到一瓶治療藥水、價格較低但省幅有界;失敗 = 沒買成(無損失)
    buy = ev["merchant_caravan"]["options"][0]
    buy_price = -sum(e["amount"] for e in buy["effects"] if e["type"] == "gold")
    m = ev["merchant_caravan"]["options"][3]
    price = -sum(e["amount"] for e in m["check"]["success"]["effects"] if e["type"] == "gold")
    assert m["requirements"] == {"gold_min": price}, "付得起才出現 → 成功扣款後金幣不為負"
    assert [e for e in m["check"]["success"]["effects"] if e["type"] == "item"] == [e for e in buy["effects"] if e["type"] == "item"]
    assert buy_price - 10 <= price < buy_price, "討價還價省幅有界(< 原價 · 至多省 10 金)"
    assert m["check"]["failure"]["effects"] == []
    # 煉金:成功 = 預設採集 + 1 件該池「常見」材料(嚴格優於預設);失敗 = 沒採到 + 受傷(嚴格劣於預設)→ 非被支配、需要判斷
    base = ev["blackmarsh_forage"]["options"][0]["effects"]
    pool = next(e["pool"] for e in base if e["type"] == "forage_pool")
    a = ev["blackmarsh_forage"]["options"][2]["check"]
    assert [e for e in a["success"]["effects"] if e["type"] == "forage_pool"] == [e for e in base if e["type"] == "forage_pool"]
    extra = [e for e in a["success"]["effects"] if e["type"] == "item"]
    assert len(extra) == 1 and extra[0]["qty"] == 1
    import json
    import pathlib
    raw = json.loads(pathlib.Path(__file__).resolve().parents[1].joinpath("tesrpg/data/alchemical_ecology.json").read_text(encoding="utf-8"))
    assert extra[0]["item"] in raw["pools"][pool]["common"], "額外材料必須是該池的常見材料(稀有材料仍只走預算抽取)"
    assert not [e for e in a["failure"]["effects"] if e["type"] in ("forage_pool", "item")]
    assert sum(e["amount"] for e in a["failure"]["effects"] if e["type"] == "damage") >= 1


# ---------------------------------------------------------------- 4. 端到端
def test_each_new_option_resolves_success_and_failure_exactly_as_specified():
    for eid, idx, label, skill, diff, ok_eff, bad_eff, kind in _SPEC:
        # 成功
        c = _char(**{skill: 40})
        hp, gold, fame = c.health, c.gold, getattr(c, "fame", 0)
        r = _drive(c, eid, idx, result=True)
        want_xp = [(e["skill"], e["amount"]) for e in ok_eff if e["type"] == "skill_xp"]
        if any(e["type"] == "forage_pool" for e in ok_eff):   # 採集池效果自己也會練偵查 / 煉金(預設採集同):選項的經驗在其上,不是唯一一筆
            assert all(x in r["xp"] for x in want_xp) and ("scout", 0.4) in r["xp"], (eid, skill, r["xp"])
        else:
            assert r["xp"] == want_xp, (eid, skill, r["xp"])
        assert r["battles"] == [] and r["ret"] is None and c.health == hp, (eid, skill, "成功不戰鬥不受傷")
        assert c.gold - gold == sum(e["amount"] for e in ok_eff if e["type"] == "gold"), (eid, skill, "成功金幣")
        assert getattr(c, "fame", 0) - fame == sum(e["amount"] for e in ok_eff if e["type"] == "fame"), (eid, skill, "成功名聲")
        for e in ok_eff:
            if e["type"] == "item":
                assert any(s["id"] == e["item"] for s in c.inventory), (eid, skill, "成功物品")
        # 失敗
        c = _char(**{skill: 40})
        hp, gold = c.health, c.gold
        r = _drive(c, eid, idx, result=False)
        assert r["xp"] == [], (eid, skill, "失敗不給經驗")
        assert r["battles"] == [e["creature"] for e in bad_eff if e["type"] == "combat"], (eid, skill)
        assert hp - c.health == sum(e["amount"] for e in bad_eff if e["type"] == "damage"), (eid, skill, "失敗受傷")
        assert c.gold - gold == sum(e["amount"] for e in bad_eff if e["type"] == "gold"), (eid, skill, "失敗金幣")


def test_chip_equals_the_probability_actually_rolled_with_luck():
    from tesrpg import formulas
    assert formulas.luck_fortune(80) > formulas.luck_fortune(40) == 0.0
    for luck in (40, 80):
        for lv in (0, 1, 37, 100):
            for eid, idx, label, skill, diff, ok_eff, bad_eff, kind in _SPEC:
                c = _char(luck=luck, **{skill: lv})
                chk = gd.events[eid]["options"][idx]["check"]
                want = events.check_chance(c, chk)
                r = _drive(c, eid, idx, result=True)
                assert r["ps"] and r["ps"][0] == want, (eid, skill, luck, lv)
                chips = next(t for t in r["opts"] if t[0] == str(idx))[2]
                assert chips == [{"text": f"成功率 {round(want * 100)}%", "tone": "gold"}], (eid, skill, luck, lv)


def test_mercantile_option_hidden_when_unaffordable_and_keys_stay_stable():
    c = _char(mercantile=40)
    c.gold = 23
    r = _drive(c, "merchant_caravan", 2)                              # 繼續趕路 = 原索引 2(未被位移)
    keys = [t[0] for t in r["opts"]]
    assert "3" not in keys and "0" not in keys and "2" in keys, keys   # 23 金:買不起補給(≥30)也討不起價(≥24);鍵仍是原索引
    c = _char(mercantile=40)
    c.gold = 24
    r = _drive(c, "merchant_caravan", 3)
    keys = [t[0] for t in r["opts"]]
    assert "3" in keys and "0" not in keys, keys                      # 24 金:討價還價出現(購買補給仍買不起)
    assert c.gold == 0 and any(s["id"] == "healing_potion" for s in c.inventory), "成功扣款後金幣恰為 0(永不為負)並換到藥水"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_events_r221 OK")
