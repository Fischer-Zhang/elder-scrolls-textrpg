"""R196 事件檢定:運動檢定首批 8 選項 + 事件選項顯示成功率(金 chip · 預覽 = 實擲)。

🔴 核心紅線:
  ① 8 個事件各附加 1 個運動檢定選項,附加在 R196 前既有選項之後(索引 = len(olds);既有選項的文字與順序不動、數字鍵不位移;
     既有選項「內容」未被改動由實作時的 git diff 純新增(+208/−0)與審查腳本比對把關,不在此永久釘死)。
     R221 起後續批次(事件檢定第二批)可往這個選項的**後面**繼續附加 → 本檔一律以固定索引 len(olds) 定位運動選項,不再假設它是最後一個。
  ② 失敗分支比照同事件既有檢定(戰鬥 / 失金);灰燼風暴無既有檢定 → 受傷 8(> 「趕路」固定 5)。
  ③ 成功率 chip 取 events.check_chance(單一出處)→ 預覽 = 實擲(端到端:實擲收到的 p == chip 數字);
     四捨五入(int() 在難度 35/40/42 × 技能 0..100 的 303 個組合裡有 17 個會少顯示 1%)。
  ④ 無檢定選項不帶 chip(2-tuple,逐位元組同舊)。
  ⑤ 零存檔欄位:純資料 + 顯示(sim 完全不走事件,byte-identical 必然成立、不當安全證據)。
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

# (事件 id, 新選項文字, 難度, 成功運動經驗, R196 前的既有選項文字, 既有檢定 (技能, 難度) 或 None)
_R196 = [
    ("highwayman", "拔腿就跑(運動)", 40, 0.6,
     ["乖乖付過路費", "出言威嚇(口才)", "拔劍相向"], ("speechcraft", 40)),
    ("street_urchin", "拔腿追上去(運動)", 35, 0.4,
     ["一把抓住他的手(安全)", "由他去吧"], ("security", 35)),
    ("wild_beast", "拔腿狂奔(運動)", 35, 0.6,
     ["搶先出手", "緩緩後退(潛行)"], ("sneak", 30)),
    ("skyrim_predator", "蹚雪疾奔(運動)", 35, 0.6,
     ["拔劍迎敵", "悄悄繞開(潛行)"], ("sneak", 35)),
    ("hammerfell_predator", "奔向堅實的地面(運動)", 40, 0.6,
     ["搶在牠破沙前出手", "屏息潛伏、悄然繞行(潛行)"], ("sneak", 40)),
    ("morrowind_ashstorm", "疾行穿越風暴(運動)", 40, 0.6,
     ["拉起頭巾趕路", "就地掩蔽等風停"], None),
    ("camp_ambush", "翻上高處躲避(運動)", 35, 0.6,
     ["起身迎戰", "悄悄遁入暗處(潛行)"], ("sneak", 35)),
    ("jungle_predator", "疾奔出林蔭(運動)", 42, 0.6,
     ["搶在牠纏上來前出手", "屏息潛伏、繞開綠影(潛行)"], ("sneak", 42)),
]

# 失敗效果(比照同事件既有檢定;灰燼風暴無既有檢定 → 受傷 8,要比「趕路」固定 5 更痛)
_R196_FAIL = {
    "highwayman": [{"type": "combat", "creature": "bandit"}],
    "street_urchin": [{"type": "gold", "amount": -10}],
    "wild_beast": [{"type": "combat", "creature": "frostbite_spider"}],
    "skyrim_predator": [{"type": "combat", "creature": "ice_wraith"}],
    "hammerfell_predator": [{"type": "combat", "creature": "dune_ripper"}],
    "morrowind_ashstorm": [{"type": "damage", "amount": 8}],
    "camp_ambush": [{"type": "combat", "creature": "wolf"}],
    "jungle_predator": [{"type": "combat", "creature": "spriggan"}],
}


# --- 夾具 ---------------------------------------------------------------
class _RecRNG(RNG):
    """記錄 chance(p) 收到的 p,結果固定;其餘方法走真 RNG(spawn_creature 需要)。"""

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
    if luck is not None:                           # 幸運 >40 → luck_fortune 加性加成(預設 40 為中性,會讓此維度空轉)
        c.attributes["luck"] = luck
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.gold = 100                                   # 讓「付過路費」可選、失金差值不被 0 夾住
    return c


def _drive(c, eid, pick, result=True):
    """走一次 main.run_event:攔截選單(回 pick(選項清單) 的 key)、戰鬥只記錄不打。"""
    st = GameState(player=c, time=GameTime(), rng=_RecRNG(result=result))
    cap = {"opts": None}
    battles, xp_calls = [], []

    def fake_menu(title, options, allow_back=False):
        cap["opts"] = list(options)
        return pick(cap["opts"])

    orig_spawn = M.combat.spawn_creature
    orig_use = events.progression.use_skill

    def spy_spawn(gamedata, tid, rng):
        battles.append(tid)
        return orig_spawn(gamedata, tid, rng)

    def spy_use(char, gamedata, skill_id, xp):
        xp_calls.append((skill_id, xp))
        return orig_use(char, gamedata, skill_id, xp)

    saved = (ui.menu, M.run_battle)
    ui.menu = fake_menu
    M.run_battle = lambda state, gamedata, foe: None
    M.combat.spawn_creature = spy_spawn
    events.progression.use_skill = spy_use
    try:
        ret = M.run_event(st, gd, eid)
    finally:
        ui.menu, M.run_battle = saved
        M.combat.spawn_creature = orig_spawn
        events.progression.use_skill = orig_use
    return {"opts": cap["opts"], "ps": st.rng.ps, "battles": battles, "xp": xp_calls, "ret": ret}


def _ath(olds):
    """選單作答函式:選 R196 的運動選項(固定在 R196 前既有選項之後 = 索引 len(olds);R221 起其後還有別的選項,不能再選「最後一個」)。"""
    return lambda opts: str(len(olds))


# --- ① 資料形狀:8 個新選項 ----------------------------------------------
def test_eight_athletics_options_shape_and_position():
    for eid, label, diff, xp, olds, sib in _R196:
        e = gd.events[eid]
        opts = e["options"]
        assert len(opts) >= len(olds) + 1, f"{eid}:至少多 1 個選項(運動)"
        assert [o["text"] for o in opts[:len(olds)]] == olds, eid       # 既有選項文字與順序不動 → 數字鍵不位移
        new = opts[len(olds)]                                    # 附加在既有選項之後 → 既有數字鍵不位移
        assert new["text"] == label and label.endswith("(運動)"), eid
        assert "requirements" not in new and "effects" not in new, eid
        chk = new["check"]
        assert (chk["skill"], chk["difficulty"]) == ("athletics", diff), eid
        assert chk["success"]["effects"] == [{"type": "skill_xp", "skill": "athletics", "amount": xp}], eid
        assert chk["failure"]["effects"] == _R196_FAIL[eid], eid
        for br in ("success", "failure"):                        # 文字非空,且沿用資料標點(半形逗號/驚嘆號,不混入全形)
            t = chk[br]["text"]
            assert isinstance(t, str) and t.strip(), (eid, br)
            assert not any(ch in t for ch in "，！？"), (eid, br, "事件文字標點慣例是半形逗號/驚嘆號")
        # 同事件只有這一個運動檢定
        assert sum(1 for o in opts if o.get("check", {}).get("skill") == "athletics") == 1, eid


def test_failure_mirrors_the_sibling_check_in_the_same_event():
    for eid, label, diff, xp, olds, sib in _R196:
        siblings = [o["check"] for o in gd.events[eid]["options"][:len(olds)] if "check" in o]
        new = gd.events[eid]["options"][len(olds)]["check"]
        if sib is None:                                          # 灰燼風暴:無既有檢定 → 受傷 8 > 「趕路」固定 5
            assert siblings == [], eid
            walk = gd.events[eid]["options"][0]["effects"]
            assert [e["amount"] for e in walk if e["type"] == "damage"] == [5]
            assert new["failure"]["effects"][0]["amount"] > 5
            continue
        assert len(siblings) == 1 and (siblings[0]["skill"], siblings[0]["difficulty"]) == sib, eid
        assert new["failure"]["effects"] == siblings[0]["failure"]["effects"], eid   # 比照同事件既有檢定


def test_existing_options_untouched():
    for eid, label, diff, xp, olds, sib in _R196:
        assert [o["text"] for o in gd.events[eid]["options"][:len(olds)]] == olds, eid


# --- ③ 預覽 = 實擲(端到端)-----------------------------------------------
def test_event_menu_chip_equals_the_probability_actually_rolled():
    from tesrpg import formulas
    assert formulas.luck_fortune(80) > formulas.luck_fortune(40) == 0.0, "幸運 80 必須真的改變機率,否則幸運維度空轉"
    for luck in (40, 80):                                        # 80 → luck_fortune 加成:chip 若自行重算公式漏掉它會現形
        for ath in (0, 1, 37, 43, 100):                          # 1 / 43 會踩到 int() 浮點截斷(難度 35 → 16% / 58%)
            for eid, label, diff, xp, olds, sib in _R196:
                c = _char(luck=luck, athletics=ath)
                chk = gd.events[eid]["options"][len(olds)]["check"]
                want = events.check_chance(c, chk)               # 先算(run_event 會練運動,可能升級)
                r = _drive(c, eid, _ath(olds), result=True)
                assert r["ps"] and r["ps"][0] == want, (eid, luck, ath)    # 實擲收到的機率 == check_chance
                chips = next(t for t in r["opts"] if t[0] == str(len(olds)))[2]    # 運動選項那一列的 chip
                assert chips == [{"text": f"成功率 {round(want * 100)}%", "tone": "gold"}], (eid, luck, ath)
    c40, c80 = _char(luck=40, athletics=30), _char(luck=80, athletics=30)   # 非空轉證明:同技能,幸運高 → 機率高
    chk = gd.events["highwayman"]["options"][3]["check"]          # 運動選項在原索引 3
    assert events.check_chance(c80, chk) > events.check_chance(c40, chk)


def test_every_option_in_the_menu_gets_a_chip_iff_it_has_a_check():
    for eid, label, diff, xp, olds, sib in _R196:
        c = _char(athletics=40)
        r = _drive(c, eid, _ath(olds), result=True)
        e = gd.events[eid]
        assert [o[0] for o in r["opts"]] == [str(i) for i in range(len(e["options"]))], eid   # 全數可選、鍵 = 原索引
        for tup in r["opts"]:
            opt = e["options"][int(tup[0])]
            assert tup[1] == opt["text"], eid
            if "check" in opt:
                assert len(tup) == 3 and tup[2][0]["text"].startswith("成功率 ") and tup[2][0]["tone"] == "gold", (eid, tup)
            else:
                assert len(tup) == 2, (eid, tup)                 # 無檢定 → 2-tuple,逐位元組同舊


def test_requirement_filtered_option_keeps_original_index_keys():
    """highwayman 的「付過路費」需 50 金:金幣不足時被濾掉,其餘選項的鍵仍是原索引(不重新編號),
    且選到的鍵確實對應到原選項(新運動選項在原索引 3)。"""
    pick3 = lambda opts: "3"                                     # 運動選項固定在原索引 3(R221 起其後另有幻術 / 召喚兩個選項)
    c = _char(athletics=40)
    c.gold = 49
    r = _drive(c, "highwayman", pick3, result=True)
    assert [t[0] for t in r["opts"]] == ["1", "2", "3", "4", "5"]   # 0 被濾掉;不重編號
    assert [len(t) for t in r["opts"]] == [3, 2, 3, 3, 3]        # 口才檢定(chip)/ 拔劍(無)/ 運動 / 幻術 / 召喚(chip)
    assert r["xp"] == [("athletics", 0.6)] and r["battles"] == []   # 鍵 "3" → 原索引 3 = 運動選項
    c = _char(athletics=40)
    c.gold = 50                                                  # 剛好夠 → 全部都在
    r = _drive(c, "highwayman", pick3, result=True)
    assert [t[0] for t in r["opts"]] == ["0", "1", "2", "3", "4", "5"]


def test_checkless_event_menu_is_unchanged_two_tuples():
    eid = next(k for k, v in gd.events.items()
               if not any("check" in o or o.get("requirements") for o in v["options"]))
    c = _char()
    r = _drive(c, eid, lambda o: o[0][0], result=True)
    assert r["opts"] == [(str(i), o["text"]) for i, o in enumerate(gd.events[eid]["options"])]


def test_chip_rounds_instead_of_truncating():
    chk = gd.events["wild_beast"]["options"][2]["check"]         # 運動選項(原索引 2)· 難度 35
    c = _char()
    st = GameState(player=c, time=GameTime())
    found = []
    for ath in range(0, 101):
        c.skills["athletics"] = ath
        p = events.check_chance(c, chk)
        if int(p * 100) != round(p * 100):                       # 浮點:0.58*100 = 57.99999…
            found.append(ath)
            assert M._event_check_chips(st, {"check": chk}) == [{"text": f"成功率 {round(p * 100)}%", "tone": "gold"}], ath
    assert found, "必須真有 int() 與 round() 不同的樣本,否則此測試空轉"


def test_all_check_options_in_all_events_get_a_chip():
    c = _char(athletics=50)
    st = GameState(player=c, time=GameTime())
    n = 0
    for eid, e in gd.events.items():
        for o in e["options"]:
            chips = M._event_check_chips(st, o)
            assert (chips is not None) == ("check" in o), eid
            n += chips is not None
    assert n >= 41                                               # 33 既有 + 8 新;之後只增不減


# --- 結算分支 -------------------------------------------------------------
def test_success_branch_trains_athletics_and_takes_no_cost():
    for eid, label, diff, xp, olds, sib in _R196:
        c = _char(athletics=40)
        hp, gold = c.health, c.gold
        r = _drive(c, eid, _ath(olds), result=True)
        assert r["xp"] == [("athletics", xp)], eid               # 成功 = 脫身 + 運動經驗
        assert r["battles"] == [] and c.health == hp and c.gold == gold and r["ret"] is None, eid


def test_failure_branch_mirrors_sibling_cost():
    for eid, label, diff, xp, olds, sib in _R196:
        c = _char(athletics=40)
        hp, gold = c.health, c.gold
        r = _drive(c, eid, _ath(olds), result=False)
        want = _R196_FAIL[eid]
        assert r["xp"] == [], eid                                # 失敗不給經驗
        assert r["battles"] == [e["creature"] for e in want if e["type"] == "combat"], eid
        assert hp - c.health == sum(e["amount"] for e in want if e["type"] == "damage"), eid
        assert c.gold - gold == sum(e["amount"] for e in want if e["type"] == "gold"), eid


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
