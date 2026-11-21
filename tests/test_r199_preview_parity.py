"""R199「預覽 = 實擲」第二批(上):行竊逐件預覽 + 說服預覽與實擲同源。行竊零實際機率改動;說服於使用者拍板(2026-11-22)後吃魅惑。

審查(R197)證實的兩個預覽 ≠ 實擲:
  ① 行竊:清單標題的「得手率」不帶物品,實擲 `steal_item` 帶物品並依重量扣減(R144,最多 −0.35)→ 沉重物品實際遠低於預覽。
     修:每件各自標「得手 N%」,取自與實擲同一個 `crime.steal_chance(char, gd, item_id)`。
  ② 說服:預覽 `persuade_chance` 含魅惑加成(吸血鬼社交魅惑 R56 / 幻術魅惑術 R104),實擲 `persuade` 自算、漏掉 →
     魅惑對說服實際無效(talk_down 與 pry 現行都吃到)。魅惑要不要對說服生效是**設計決定**(會改實際機率)→ 先不動:
     兩邊改為單一出處 `dialogue._persuade_p`(預覽 `persuade_chance` 與實擲 `persuade` 都呼叫它),由
     `PERSUADE_USES_CHARM` 決定是否含魅惑(先預設 False 維持現行機率);**使用者拍板後預設翻 True**(對齊 R56 / R104 原設計)。
🔴 守衛:預覽數字 == 真實擲骰 `rng.chance` 的引數(recording RNG),跨構築;PERSUADE_USES_CHARM 兩種狀態都同源;
   旗標關時 persuade 的擲骰機率對舊內嵌算式逐位元組同(回退路徑;無魅惑的玩家預設路徑也逐位元組同);
   旗標開(預設)時對舊預覽式逐位元組同(含浮點加法順序)。
🔴 審查 major(R199):行竊選單若用裸物品 id 當 key,會被畫面上殘留的買貨/賣貨面板列(data-key=iid)在前端「接管」,
   選單按鈕連同「得手 N%」標籤整個被移除 → key 必須帶 `steal:` 命名空間;單測把 ui.menu 換假函式看不到,
   所以另有「真 WebBackend 協定層」守衛與 tests/browser_ui.py 的真 Chromium 回歸。
"""
import ast
import copy
from pathlib import Path

from tesrpg import formulas, main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.systems import crime, dialogue, spellfx, stats, vampirism
import tesrpg.ui.console as ui

gd = get_gamedata()
ROOT = Path(__file__).resolve().parent.parent


class _RecRNG(RNG):
    """記錄所有 chance(p) 的 p;結果固定。"""

    def __init__(self, seed=0, result=True):
        super().__init__(seed)
        self.ps, self.result = [], result

    def chance(self, p):
        self.ps.append(p)
        return self.result


def _char(sneak=40, security=30, speech=40, personality=45):
    c = build_character(gd, name="客", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.skills.update(sneak=sneak, security=security, speechcraft=speech)
    c.attributes["personality"] = personality
    stats.recompute_max_resources(c, gd, restore_full=True)
    c.fatigue = c.max_fatigue
    c.location_id = "bruma"
    return c


def _items_by_weight():
    """各種重量的真實商品:輕(≈0)/中/重/極重(超過 0.35 夾限)。"""
    by = {}
    for iid, it in gd.items.items():
        w = it.get("weight", 0) or 0
        by.setdefault(w, iid)
    ws = sorted(by)
    pick = [ws[0], ws[len(ws) // 3], ws[2 * len(ws) // 3], ws[-1]]
    return [by[w] for w in pick]


# --- ① 行竊:逐件得手率 = 實擲機率 --------------------------------------------
def test_steal_label_shows_each_items_own_rate_equal_to_the_real_roll():
    items = _items_by_weight()
    seen_rates = set()
    for cfg in (dict(sneak=40, security=30), dict(sneak=80, security=60), dict(sneak=10, security=5)):
        for iid in items:
            c = _char(**cfg)
            label = M._steal_option_label(c, gd, iid, 3)
            real = _RecRNG(result=True)
            crime.steal_item(copy.deepcopy(c), gd, iid, real)               # 真的行竊:第一個 rng.chance = 得手判定
            shown = ui.pct(real.ps[0])
            assert f"得手 {shown}%" in label, (cfg, iid, label, real.ps[0])
            assert f"×3" in label and f"價值 {gd.item(iid)['value']}" in label and gd.item_name(iid) in label
            seen_rates.add(shown)
    assert len(seen_rates) >= 6, seen_rates                                  # 輕重物品 × 角色的差異確實反映在標籤(非空轉)


def test_heavier_items_show_lower_rates_up_to_the_cap():
    c = _char(sneak=60, security=40)
    ws = sorted(items := _items_by_weight(), key=lambda i: gd.item(i).get("weight", 0) or 0)
    rates = [crime.steal_chance(c, gd, i) for i in ws]
    assert rates == sorted(rates, reverse=True) and rates[0] > rates[-1]
    assert crime.steal_chance(c, gd) > rates[-1]                             # 不帶物品的舊口徑會高估重物(例:偷襲 60·保全 40 → 舊標題 67%、重物實際 32%)


def _steal_chance_misuses(source: str) -> list:
    """回傳 source 內所有「沒帶物品」的 steal_chance 使用處 [(行號, 原因)]。
    抓:缺第 3 個位置引數且無 item_id=、物品引數為字面 None、from … import steal_chance(之後的裸呼叫追不到)、
    把 steal_chance 當值引用(別名 / 傳遞 → 追不到)。"""
    tree = ast.parse(source)
    bad, called = [], set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name == "steal_chance":
                called.add(id(f))
                item = n.args[2] if len(n.args) >= 3 else next((k.value for k in n.keywords if k.arg == "item_id"), None)
                if item is None or (isinstance(item, ast.Constant) and item.value is None):
                    bad.append((n.lineno, "沒帶物品"))
        elif isinstance(n, ast.ImportFrom) and any(a.name == "steal_chance" for a in n.names):
            bad.append((n.lineno, "from import(裸呼叫追不到)"))
    for n in ast.walk(tree):
        is_ref = ((isinstance(n, ast.Attribute) and n.attr == "steal_chance")
                  or (isinstance(n, ast.Name) and n.id == "steal_chance"))
        if is_ref and id(n) not in called:
            bad.append((n.lineno, "被當值引用(別名 / 傳遞)"))
    return sorted(set(bad))


def test_no_module_previews_steal_without_an_item():
    """原始碼守衛(語法樹):tesrpg/ 內任何 steal_chance 使用都必須帶物品(第 3 個位置引數,或 item_id= 且非字面 None);
    別名 / from-import / 當值傳遞一律視為違規(追不到)。對合成的舊寫法做探針:守衛必須抓得到(審查:原守衛只掃 main.py 的屬性呼叫)。"""
    scanned = 0
    for p in sorted((ROOT / "tesrpg").rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        if "steal_chance" not in src:
            continue
        scanned += 1
        assert not _steal_chance_misuses(src), (p.relative_to(ROOT), _steal_chance_misuses(src))
    assert scanned >= 2, "守衛只掃到不到 2 個模組 → 空轉"
    for bad_src in ("crime.steal_chance(char, gamedata)", "crime.steal_chance(char, gamedata, None)",
                    "crime.steal_chance(char, gamedata, item_id=None)", "crime.steal_chance(*args)",
                    "from tesrpg.systems.crime import steal_chance\nsteal_chance(c, gd, i)",
                    "sc = crime.steal_chance\nsc(c, gd, i)", "run(crime.steal_chance)"):
        assert _steal_chance_misuses(bad_src), f"守衛抓不到:{bad_src!r}"
    for ok_src in ("crime.steal_chance(char, gamedata, iid)", "steal_chance(char, gamedata, item_id=iid)"):
        assert not _steal_chance_misuses(ok_src), ok_src


def _shop_with_varied_weights():
    """挑一座商品重量不一的商店城鎮(資料變動也不會空轉)。"""
    from tesrpg.systems import world
    for loc in gd.world["locations"]:
        cat = world.merchant_catalog(gd, loc)
        if len({(gd.item(i).get("weight", 0) or 0) for i in cat}) >= 3:
            return loc
    raise AssertionError("找不到商品重量有 3 種以上的商店")


def test_shop_steal_menu_end_to_end_label_equals_the_roll_of_that_item():
    """走真的 action_shop:行竊選單每件的標籤 = _steal_option_label,且玩家選哪件、steal_item 丟給 rng.chance 的機率
    = 該件標籤上的 %(預覽 = 實擲,含呼叫端接線;單測 label 函式抓不到「函式對、接線錯」)。"""
    from tesrpg.state import GameState, GameTime
    from tesrpg.systems import world
    loc = _shop_with_varied_weights()
    seen_rates = set()
    for pick_heaviest in (False, True):
        c = _char(sneak=60, security=40)
        c.location_id = loc
        st = GameState(player=c, time=GameTime(), rng=RNG(7))
        world.ensure_stock(c, gd, loc, st.time, st.rng)                    # 用真 RNG 先補貨,之後換成記錄用 RNG
        st.rng = _RecRNG(result=True)
        seen, calls = {}, {"n": 0}

        def fake_menu(title, opts, allow_back=False, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return "steal"
            if calls["n"] == 2:
                seen["title"], seen["opts"] = title, list(opts)
                iid_of = lambda k: k.removeprefix(M._STEAL_KEY)
                seen["expected"] = {k: M._steal_option_label(c, gd, iid_of(k), world.stock_qty(c, loc, iid_of(k)))
                                    for k, _ in opts}
                st.rng.ps.clear()                                          # 只留行竊那一擲
                weight = lambda k: gd.item(iid_of(k)).get("weight", 0) or 0
                ids = [k for k, _ in opts]
                seen["picked"] = max(ids, key=weight) if pick_heaviest else min(ids, key=weight)
                return seen["picked"]
            return None

        saved = (M.ui.menu, M.ui.message, M.ui.show_events)
        M.ui.menu, M.ui.message, M.ui.show_events = fake_menu, (lambda *a, **k: None), (lambda *a, **k: None)
        try:
            M.action_shop(st, gd)
        finally:
            M.ui.menu, M.ui.message, M.ui.show_events = saved
        assert seen["title"] == "行竊哪件?(重物更難得手)", seen["title"]
        assert len(seen["opts"]) >= 3
        assert dict(seen["opts"]) == seen["expected"]                      # 每件都由同一個標籤函式、用當時的庫存數產生(接線)
        assert M._STEAL_KEY and all(k.startswith(M._STEAL_KEY) for k, _ in seen["opts"])   # key 一律帶命名空間(見碰撞守衛)
        label = dict(seen["opts"])[seen["picked"]]
        picked = seen["picked"].removeprefix(M._STEAL_KEY)
        assert st.rng.ps, "沒有擲骰 → 流程沒走到行竊"
        shown = ui.pct(st.rng.ps[0])
        assert st.rng.ps[0] == crime.steal_chance(c, gd, picked)
        assert f"得手 {shown}%" in label, (label, st.rng.ps[0])
        seen_rates.add(shown)
        assert len({lbl.split("得手 ")[1] for _, lbl in seen["opts"]}) >= 2     # 選單內各件得手率不全相同(重物較低)
    assert len(seen_rates) == 2, seen_rates                                     # 最輕 vs 最重 實際擲出的機率不同(非空轉)


# 在「乾淨的子進程」裡跑真 WebBackend:整套測試共用同一個進程,既有的多個模組(如 test_m13)會把 ui.menu 換成假函式且
# 不還原 → 在進程內跑會吃到殘留的假選單(單獨跑才過);子進程不受任何全域殘留影響。
_FRAME_DRIVER = r"""
import io, json, sys, threading
sys.path.insert(0, sys.argv[1])
first = sys.argv[2]
from rich.console import Console
from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import inventory, stats, world
from tesrpg.web.backend import WebBackend
import tesrpg.ui.console as ui


def data_keys(obj):
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "key" and isinstance(v, str):
                out.add(v)
            else:
                out |= data_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= data_keys(v)
    return out


gd = get_gamedata()
c = build_character(gd, name="客", sex="male", race="nord", birthsign="warrior", class_id="warrior")
c.skills.update(sneak=60, security=40)
stats.recompute_max_resources(c, gd, restore_full=True)
c.fatigue = c.max_fatigue
loc = next(l for l in gd.world["locations"]
           if len({(gd.item(i).get("weight", 0) or 0) for i in world.merchant_catalog(gd, l)}) >= 3)
c.location_id, c.gold = loc, 500
for iid in ("lockpick", "iron_dagger", "healing_potion"):      # 賣貨面板要有與店內同 id 的貨 = 最容易相撞的情形
    inventory.add_item(c, iid, 1)
st = GameState(player=c, time=GameTime(), rng=RNG(7))
backend = WebBackend()
ui.use_web_backend(backend, Console(record=True, file=io.StringIO(), width=100))
box = {}


def worker():
    try:
        M.action_shop(st, gd)
    except BaseException as e:
        box["exc"] = repr(e)


t = threading.Thread(target=worker, daemon=True)
t.start()
frames = []
for ans in (first, None, "steal", None, None):                  # 進面板 → 返回 → 行竊 → 返回 → 離開
    fr = backend.outbound.get(timeout=5)
    sp = fr["prompt"]
    panel = set()
    for b in fr["blocks"]:
        if b["kind"] == "view" and b["name"] in ("shop", "inventory"):
            panel |= data_keys(b["data"])
    frames.append({"title": str(sp.get("title", "")), "nblocks": len(fr["blocks"]), "panel_keys": sorted(panel),
                   "options": [{"key": o.get("key"), "label": o.get("label", "")} for o in sp.get("options", [])]})
    backend.submit(fr["prompt_id"], ans)
t.join(5)
print(json.dumps({"frames": frames, "alive": t.is_alive(), "exc": box.get("exc")}, ensure_ascii=False))
"""


def test_steal_menu_option_keys_never_collide_with_a_stale_shop_or_inventory_panel():
    """審查 major(R199):買貨 / 賣貨面板(view shop / view inventory,列帶 data-key=物品 id)在「返回」後仍殘留於畫面
    (後續 frame 沒有 state block → 前端不重畫),前端 wireActionableRows 會讓殘留列「接管」key 相同的選項並移除選單按鈕
    → 行竊選單用裸 iid 當 key 時,每件的「得手 N%」標籤整個被蓋掉(真 Chromium 實測:只剩「返回」+ 14 列舊面板)。
    走真 WebBackend 驅動真 action_shop(子進程):買 / 賣 → 返回 → 行竊;行竊 frame 的選項 key 不得與先前任何面板的 key 相交。"""
    import json
    import subprocess
    import sys
    for first in ("buy", "sell"):
        out = subprocess.run([sys.executable, "-c", _FRAME_DRIVER, str(ROOT), first], cwd=ROOT,
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr[-600:]
        res = json.loads(out.stdout.strip().splitlines()[-1])
        assert not res["alive"] and not res["exc"], (first, res["exc"])
        frames = res["frames"]
        steal = next(f for f in frames if f["title"].startswith("行竊哪件"))
        assert steal["nblocks"] == 0, "行竊 frame 帶了 state block → 殘留面板已被重畫,本守衛的前提不成立"
        panel_keys = set().union(*(set(f["panel_keys"]) for f in frames))
        assert len(panel_keys) >= 3, (first, "沒抓到殘留面板的列 key → 空轉")
        opt_keys = {o["key"] for o in steal["options"] if isinstance(o["key"], str)}
        assert len([k for k in opt_keys if k.startswith(M._STEAL_KEY)]) >= 3
        assert not (opt_keys & panel_keys), (first, sorted(opt_keys & panel_keys))
        for o in steal["options"]:                                         # 標籤帶得手率(隨選項一起送到前端)
            if str(o["key"]).startswith(M._STEAL_KEY):
                assert "得手" in o["label"], o


# --- ② 說服:預覽 == 實擲(單一出處)---------------------------------------------
def _npc():
    return next(iter(gd.npcs))


def _roll_chance(c, npc, flag):
    """真的呼叫 dialogue.persuade,回傳它丟給 rng.chance 的機率。"""
    saved = dialogue.PERSUADE_USES_CHARM
    dialogue.PERSUADE_USES_CHARM = flag
    try:
        rng = _RecRNG(result=True)
        dialogue.persuade(copy.deepcopy(c), gd, npc, rng)
        return rng.ps[0]
    finally:
        dialogue.PERSUADE_USES_CHARM = saved


def _preview(c, npc, flag):
    saved = dialogue.PERSUADE_USES_CHARM
    dialogue.PERSUADE_USES_CHARM = flag
    try:
        return dialogue.persuade_chance(c, gd, npc)
    finally:
        dialogue.PERSUADE_USES_CHARM = saved


class _Charm:
    """讓角色同時被視為:吸血鬼(社交魅惑)+ 幻術魅惑中(R104)。"""

    def __enter__(self):
        self._saved = (vampirism.is_vampire, spellfx.is_charmed)
        vampirism.is_vampire = lambda ch: True
        spellfx.is_charmed = lambda ch: True

    def __exit__(self, *a):
        vampirism.is_vampire, spellfx.is_charmed = self._saved


def test_persuade_preview_equals_the_rolled_chance_in_both_charm_modes():
    npc = _npc()
    for speech in (5, 40, 75, 100):
        for pers in (30, 60):
            c = _char(speech=speech, personality=pers)
            for flag in (False, True):
                assert _preview(c, npc, flag) == _roll_chance(c, npc, flag), (speech, pers, flag, "無魅惑")
                with _Charm():
                    assert _preview(c, npc, flag) == _roll_chance(c, npc, flag), (speech, pers, flag, "魅惑中")


def test_charm_counts_by_default_and_the_flag_off_restores_the_old_roll():
    """使用者拍板(2026-11-22):魅惑加成說服 → PERSUADE_USES_CHARM 預設 True(對齊 R56 / R104 原設計)。
    旗標關 = 舊實擲行為(不含魅惑),可一行回退;沒有魅惑的玩家兩態完全相同。"""
    assert dialogue.PERSUADE_USES_CHARM is True                              # 預設 = 使用者拍板的行為
    npc, c = _npc(), _char(speech=40, personality=45)
    base = _preview(c, npc, False)
    assert _preview(c, npc, True) == base == dialogue.persuade_chance(c, gd, npc)   # 無魅惑 → 兩態同值(不受影響)
    with _Charm():
        assert _preview(c, npc, False) == base                               # 旗標關:魅惑不影響(舊實擲行為 = 回退路徑)
        assert _roll_chance(c, npc, False) == base
        assert _preview(c, npc, True) > base and _roll_chance(c, npc, True) > base   # 預設(開):預覽與實擲一併提高
        assert dialogue.persuade_chance(c, gd, npc) == _preview(c, npc, True)        # 不覆寫旗標 = 預設 = 開
        # 開 = R197 審查時的舊預覽(吸血鬼 R56 + 幻術魅惑 R104 兩項都算進去,不是只算其一)
        assert vampirism.charm_social_bonus(c) > 0 and spellfx.charm_persuade_bonus(c) > 0
        old_preview = formulas.persuade_curve(0.35 + (c.skill("speechcraft") + c.attr("personality") - 50) * 0.005
                                              + vampirism.charm_social_bonus(c) + spellfx.charm_persuade_bonus(c))
        assert _preview(c, npc, True) == old_preview == _roll_chance(c, npc, True)


def test_persuade_roll_without_charm_is_bytewise_identical_to_the_pre_r199_inline_formula():
    """沒有魅惑的玩家(絕大多數)完全不受影響:預設擲骰機率逐位元組同 R199 前的內嵌式;旗標關(回退路徑)連魅惑中也同舊。"""
    npc = _npc()
    n = 0
    for speech in (0, 10, 25, 50, 75, 100):
        for pers in (20, 40, 60, 80):
            c = _char(speech=speech, personality=pers)
            old = formulas.persuade_curve(0.35 + (c.skill("speechcraft") + c.attr("personality") - 50) * 0.005)
            assert _roll_chance(c, npc, True) == old, (speech, pers, "預設路徑·無魅惑")
            assert _roll_chance(c, npc, False) == old, (speech, pers, "旗標關")
            with _Charm():
                assert _roll_chance(c, npc, False) == old, (speech, pers, "魅惑中、旗標關 → 仍同舊(回退路徑)")
            n += 1
    assert n == 24


def test_persuade_rolls_with_the_pre_practice_skill_even_when_the_practice_levels_it_up():
    """persuade 先付練習(use_skill 可能升 1 級)再擲:擲骰機率必須用「練習前」的口才(舊行為);
    預覽讀目前口才 = 同一個值。若實擲改成讀練習後的口才,剛好升級那一刻就會與預覽差 0.5%。"""
    npc = _npc()
    c = _char(speech=40, personality=45)
    c.skill_xp["speechcraft"] = formulas.skill_threshold(40) - 0.001         # 練習必升級
    old = formulas.persuade_curve(0.35 + (40 + c.attr("personality") - 50) * 0.005)
    after = formulas.persuade_curve(0.35 + (41 + c.attr("personality") - 50) * 0.005)
    assert old != after
    probe = copy.deepcopy(c)
    rng = _RecRNG(result=True)
    dialogue.persuade(probe, gd, npc, rng)
    assert probe.skills["speechcraft"] == 41, "夾具沒讓練習升級 → 空轉"
    assert rng.ps[0] == old == dialogue.persuade_chance(c, gd, npc) != after


def test_flag_on_preview_and_roll_equal_the_pre_r199_preview_formula_bytewise_over_a_grid():
    """旗標開 = R199 前的舊預覽式,逐位元組同(含浮點加法順序 ((0.35+x)+吸血鬼)+魅惑術)。審查:單點(口才 40·魅力 45)
    對加法順序不敏感,把 `p+a; p+b` 改成 `p+(a+b)` 全套測試都殺不掉;格點含 1-ULP 分歧例(口才 0·魅力 146)。"""
    npc = _npc()
    n = reordered_differs = 0
    with _Charm():
        for speech in (0, 3, 17, 40, 62, 100):
            for pers in (0, 20, 46, 60, 100, 146, 200):
                c = _char(speech=speech, personality=pers)
                x = (c.skill("speechcraft") + c.attr("personality") - 50) * 0.005
                a, b = vampirism.charm_social_bonus(c), spellfx.charm_persuade_bonus(c)
                old = formulas.persuade_curve(0.35 + x + a + b)               # R199 前預覽的原式(逐項由左至右)
                alt = formulas.persuade_curve(0.35 + x + (a + b))             # 不同的加法順序
                reordered_differs += (old != alt)
                assert _preview(c, npc, True) == old and _roll_chance(c, npc, True) == old, (speech, pers)
                n += 1
    assert n == 42 and reordered_differs >= 1, (n, reordered_differs)          # 格點內確實有「換順序會差」的點(非空轉)


def test_guaranteed_persuade_preview_is_certain_and_the_roll_never_rolls():
    """折服里程碑(口才 100 · 辯舌·折服):預覽 1.0、實擲不擲骰且必成;每個 NPC 限一次,用過後預覽與實擲回到一般曲線。
    (審查:把 persuade_chance 的折服分支刪掉,全套測試都殺不掉。)"""
    npc = _npc()
    c = _char(speech=100, personality=60)
    c.mastery_choices["speechcraft_100"] = "charm"
    assert dialogue.persuade_chance(c, gd, npc) == 1.0
    rng = _RecRNG(result=False)                                              # 若真去擲骰就會失敗
    first = copy.deepcopy(c)
    r = dialogue.persuade(first, gd, npc, rng)
    assert r["ok"] and r.get("charmed") and rng.ps == []
    p2 = dialogue.persuade_chance(first, gd, npc)                            # 已折服過這位 NPC → 回到一般曲線
    assert p2 < 1.0 and p2 == formulas.persuade_curve(0.35 + (100 + 60 - 50) * 0.005)
    rng2 = _RecRNG(result=True)
    dialogue.persuade(first, gd, npc, rng2)
    assert rng2.ps == [p2]


def test_persuade_reads_layered_attribute_and_skill_bonuses_like_before():
    """舊式讀 char.skill / char.attr(含裝備 / 藥水 / 里程碑 … 疊加層);回歸成 base_* 會讓預覽與實擲一起失真。
    (審查:把 attr→base_attr、skill→base_skill 全套測試都殺不掉 —— 夾具角色沒有任何疊加層。)"""
    npc = _npc()
    c = _char(speech=30, personality=40)
    plain = _roll_chance(c, npc, False)
    c.potion_attr_bonus = {"personality": 25}
    c.equip_skill_bonus = {"speechcraft": 12}
    assert c.attr("personality") == 65 and c.skill("speechcraft") == 42
    old = formulas.persuade_curve(0.35 + (42 + 65 - 50) * 0.005)
    assert _roll_chance(c, npc, False) == old == _preview(c, npc, False) != plain


# --- ③ 審計中「宣稱同源」的機率預覽 → 永久對帳(防以後有人在其中一邊自己重算)-----------------
# 每組:UI 預覽用的函式 == 真實動作丟給 rng.chance 的引數(recording RNG)。R199 審計逐一驗過,這裡把它釘成守衛。
def _foes(*names):
    from tesrpg.systems import combat
    return [combat.spawn_creature(gd, n, RNG(i + 1)) for i, n in enumerate(names)]


def test_intimidate_preview_equals_the_rolled_chance():
    for cfg in (dict(speech=10, personality=30), dict(speech=60, personality=50), dict(speech=100, personality=80)):
        for night in (False, True):
            c = _char(speech=cfg["speech"], personality=cfg["personality"])
            foes = _foes("bandit", "bandit")
            assert dialogue.can_intimidate(gd, foes)
            rng = _RecRNG(result=True)
            r = dialogue.intimidate(copy.deepcopy(c), gd, foes, night, rng)
            assert rng.ps[0] == dialogue.intimidate_chance(c, foes, night, gd) == r["chance"], (cfg, night)


def test_recruit_preview_equals_the_rolled_chance():
    for speech, pers in ((5, 30), (50, 50), (100, 90)):
        c = _char(speech=speech, personality=pers)
        rng = _RecRNG(result=True)
        dialogue.recruit_persuade(copy.deepcopy(c), gd, rng)
        assert rng.ps[0] == dialogue.recruit_chance(c), (speech, pers)


def test_talk_down_preview_equals_the_rolled_chance():
    from tesrpg.systems import crime
    for bounty in (20, 60, 100):
        for speech in (10, 70):
            c = _char(speech=speech)
            prov = crime.province_of(c, gd)
            crime.add_bounty(c, prov, bounty)
            rng = _RecRNG(result=False)
            dialogue.talk_down_guard(copy.deepcopy(c), gd, prov, rng)
            assert rng.ps[0] == dialogue.talk_down_chance(c, crime.bounty(c, prov), gd), (bounty, speech)
            with _Charm():                                                  # 吸血鬼社交魅惑:talk_down 預覽與實擲都吃(對照說服:實擲漏)
                rng = _RecRNG(result=False)
                dialogue.talk_down_guard(copy.deepcopy(c), gd, prov, rng)
                assert rng.ps[0] == dialogue.talk_down_chance(c, crime.bounty(c, prov), gd)


def test_pry_preview_equals_the_rolled_chance():
    for speech, pers in ((10, 30), (60, 50), (100, 80)):
        c = _char(speech=speech, personality=pers)
        st = _state(c)
        npc = _npc()
        ctx = dialogue.talk_ctx(st, gd, npc)
        for charmed in (False, True):
            rng = _RecRNG(result=False)
            saved = spellfx.is_charmed
            spellfx.is_charmed = (lambda ch: True) if charmed else saved
            try:
                dialogue._do_pump(_state(copy.deepcopy(c)), gd, npc, {"action": "pump"}, ctx, rng)
                assert rng.ps[0] == dialogue.pry_chance(c), (speech, pers, charmed)
            finally:
                spellfx.is_charmed = saved


def _state(c):
    from tesrpg.state import GameState, GameTime
    return GameState(player=c, time=GameTime(), rng=_RecRNG(result=True))


def test_vanish_and_stealth_previews_equal_the_rolled_chance():
    from tesrpg.systems import combat
    for sneak, acro in ((20, 10), (60, 40), (100, 100)):
        c = _char(sneak=sneak)
        c.skills["acrobatics"] = acro
        foes = _foes("bandit", "wolf")
        for used in (0, 1, 2):
            rng = _RecRNG(result=True)
            combat.try_vanish(c, len(foes), used, rng, gd)
            assert rng.ps[0] == combat.vanish_chance(c, len(foes), used, gd), (sneak, used)
        rng = _RecRNG(result=True)
        combat.try_stealth_retreat(c, foes, rng, gd)
        assert rng.ps[0] == combat.stealth_retreat_chance(c, foes, gd), sneak
        for night in (False, True):
            for scouted in (False, True):
                for surprise in (False, True):
                    rng = _RecRNG(result=True)
                    combat.try_stealth_approach(c, foes, rng, gd, night, scouted, surprise)
                    assert rng.ps[0] == combat.stealth_approach_chance(c, foes, gd, night, scouted, surprise)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
