"""R219 握法不變量「最後裝的贏」(使用者 2026-11-26 拍板:雙手武器不該跟其他武器同時存在;弓改雙手;獨立里程碑)。

緣起(R138 龜殼施法者量測時發現):雙手重盾可與任何手持武器並存(設計=武器「休眠」),但休眠只在部分路徑生效 ——
弓技選單 / 連珠箭 / 騎射仍讀 `char.weapon`、法杖施法焦點(R77)照吃;重盾與副手匕首可同時成立(雙持 + 重盾);輕盾與副手匕首可並存
(盾的被動護甲 / 荊棘 + 雙持加傷,選單只藏格擋);弓(9 把)沒標雙手 → 能搭盾;存檔載入與即時裝備不一致(重盾 + 副手裝備當下成功、載入被悄悄清掉)。

規則(最後裝上的那件贏,被擠掉的收回背包):
  ① 裝雙手武器(戰錘 / 戰斧 / 弓)→ 收起盾與副手  ② 裝非雙手武器 → 若持雙手重盾則收起重盾
  ③ 裝雙手重盾 → 收起手持武器(變空手)與副手  ④ 裝輕盾 → 收起副手  ⑤ 裝副手匕首 → 收起盾
  例外保留:雙手武器在手時穿**輕盾**仍是「拒絕」(R41 / R202 舊行為不變);雙手重盾與武器是「最後裝的贏」(新)。

守衛:
  1. 資料:9 把弓全標 two_handed(舊 12 把雙手武器仍在)
  2. 全序列掃描:9 種操作任意 3 連發(729 條序列)——每一步後三條不變量恆成立(測試用原始資料判定,不呼叫被測的 is_two_handed)、
     拒絕時狀態不變、**預覽 = 實擲**(`grip_displaced` 預告的槽就是實際被收起的槽,其餘不動)、被收起的物品仍在背包
  3. 具名情境(含 R202 輕盾仍被雙手武器擋、重盾與雙手武器現在互換)
  4. 漏洞已封:重盾 + 弓 / 法杖 → 手持武器已收起(弓技選單依據 / 杖焦點 歸零)
  5. 載入正規化 `ensure_grip`:同一組不變量、idempotent、物品不遺失;存檔往返
  6. 全職業 × 全出身 創角後不變量成立
  7. 訊息 / 換裝對比:點名被收起的東西;沒有被收起 → 不說「卸下了盾與副手」的假話
"""
import contextlib
import copy
import io
import itertools

from rich.console import Console

import tesrpg.ui.console as ui
ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

from tesrpg import main as M
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import inventory, stats

gd = get_gamedata()

SWORD, DAGGER, DAGGER2, STAFF, BOW, HAMMER, SPEAR = (
    "iron_sword", "iron_dagger", "steel_dagger", "magicka_staff", "hunting_bow", "iron_warhammer", "iron_spear")
LIGHT, GREAT = "iron_shield", "daedric_great_shield"
_OPS = ([("w", i) for i in (SWORD, DAGGER, STAFF, BOW, HAMMER, SPEAR)]
        + [("s", LIGHT), ("s", GREAT), ("o", DAGGER2)])


def _two(i):
    return bool(gd.item(i).get("two_handed"))


def _great(i):
    return bool(gd.item(i).get("great_shield"))


def _fresh(cls="warrior"):
    c = build_character(gd, name="握", sex="male", race="nord", birthsign="warrior", class_id=cls)
    for iid in (SWORD, DAGGER, DAGGER2, STAFF, BOW, HAMMER, SPEAR, LIGHT, GREAT):
        inventory.add_item(c, iid, 1)
    c.weapon, c.offhand = "fists", ""
    c.equipped.pop("shield", None)
    return c


def _slots(c):
    return {"weapon": c.weapon, "shield": c.equipped.get("shield"), "offhand": c.offhand}


def _check(c, ctx=""):
    """三條不變量(用原始資料判定,不呼叫 inventory.is_two_handed / is_great_shield → 突變它們時這裡不會跟著變)。"""
    shield = c.equipped.get("shield")
    if _two(c.weapon):
        assert not shield and not c.offhand, f"雙手武器 {c.weapon} 不可與盾 / 副手並存 {ctx} {_slots(c)}"
    if shield and _great(shield):
        assert c.weapon == "fists" and not c.offhand, f"雙手重盾不可與武器 / 副手並存 {ctx} {_slots(c)}"
    if shield:
        assert not c.offhand, f"盾與副手不可並存 {ctx} {_slots(c)}"


def _apply(c, op):
    """做一個操作;回 (ok, 預覽的被收起槽集合, 做之前的狀態, 之後的狀態)。"""
    kind, iid = op
    before = _slots(c)
    role = {"w": "weapon", "s": "shield", "o": "offhand"}[kind]
    preview = {s for s, _i in inventory.grip_displaced(c, gd, iid, role)}
    if kind == "w":
        ok = inventory.equip_weapon(c, gd, iid)
    elif kind == "s":
        ok = inventory.equip_armor(c, gd, iid)
    else:
        ok = inventory.equip_offhand(c, gd, iid)
    return ok, preview, before, _slots(c)


# ---------------------------------------------------------------- 1. 資料
def test_every_bow_is_two_handed_and_old_two_handers_stay():
    bows = [i for i, w in gd.weapons.items() if w.get("archetype") == "bow"]
    assert len(bows) >= 9 and all(gd.weapons[i].get("two_handed") for i in bows), [i for i in bows if not gd.weapons[i].get("two_handed")]
    old = [i for i, w in gd.weapons.items() if w.get("two_handed") and w.get("archetype") != "bow"]
    assert len(old) == 12 and all(w.get("archetype") in ("mace", "axe") for w in (gd.weapons[i] for i in old))
    assert not any(w.get("two_handed") for w in gd.weapons.values() if w.get("archetype") in ("sword", "dagger", "staff", "spear")), \
        "劍 / 匕首 / 法杖 / 長槍維持單手(使用者只裁定弓)"


# ---------------------------------------------------------------- 2. 全序列掃描
def test_every_three_step_sequence_keeps_the_grip_invariants_and_preview_equals_reality():
    base = _fresh()
    n = 0
    for seq in itertools.product(_OPS, repeat=3):
        c = copy.deepcopy(base)
        for step, op in enumerate(seq):
            ok, preview, before, after = _apply(c, op)
            ctx = f"seq={[o[1] for o in seq]} step={step}"
            _check(c, ctx)
            kind, iid = op
            blocked = (inventory.weapon_equip_block(c, gd, iid) if kind == "w" else
                       inventory.armor_equip_block(c, gd, iid) if kind == "s" else None)
            if not ok:                                                   # 拒絕 → 狀態不變
                assert after == before, f"拒絕卻改了狀態 {ctx} {before}->{after}"
                continue
            expect = dict(before)
            for slot in preview:                                         # 預覽 = 實擲:預告的槽被收起、其餘不動
                expect[slot] = "fists" if slot == "weapon" else ("" if slot == "offhand" else None)
            expect[{"w": "weapon", "s": "shield", "o": "offhand"}[kind]] = iid
            assert after == expect, f"預覽與實際不符 {ctx} 預告收起 {preview}:{before}->{after}(預期 {expect})"
            for iid2 in (SWORD, DAGGER, DAGGER2, STAFF, BOW, HAMMER, SPEAR, LIGHT, GREAT):
                assert inventory.count_item(c, iid2) == 1, f"物品不得消失 {iid2} {ctx}"
        n += 1
    assert n == len(_OPS) ** 3 == 729, n


# ---------------------------------------------------------------- 3. 具名情境
def test_named_scenarios_last_equipped_wins():
    c = _fresh()
    inventory.equip_weapon(c, gd, SWORD); inventory.equip_armor(c, gd, GREAT)
    assert _slots(c) == {"weapon": "fists", "shield": GREAT, "offhand": ""}, "③ 裝重盾 → 劍被收起"
    assert inventory.equip_weapon(c, gd, STAFF) and _slots(c) == {"weapon": STAFF, "shield": None, "offhand": ""}, "② 裝法杖 → 重盾被收起"
    inventory.equip_armor(c, gd, LIGHT)
    assert inventory.equip_weapon(c, gd, BOW) and _slots(c) == {"weapon": BOW, "shield": None, "offhand": ""}, "① 弓是雙手 → 輕盾被收起"
    assert not inventory.equip_armor(c, gd, LIGHT) and c.equipped.get("shield") is None, "弓在手 → 輕盾被擋(R41 / R202 舊行為)"
    assert inventory.armor_equip_block(c, gd, LIGHT) == "雙手武器在手,裝不了盾"
    assert not inventory.equip_offhand(c, gd, DAGGER2), "弓在手 → 無副手槽"
    # 重盾 vs 雙手武器:現在互換(原本重盾被擋)
    assert inventory.armor_equip_block(c, gd, GREAT) is None and inventory.equip_armor(c, gd, GREAT)
    assert _slots(c) == {"weapon": "fists", "shield": GREAT, "offhand": ""}, "③ 雙手武器在手裝重盾 → 武器收起(最後裝的贏)"
    inventory.equip_weapon(c, gd, HAMMER)
    assert _slots(c) == {"weapon": HAMMER, "shield": None, "offhand": ""}
    # ④ 輕盾 vs 副手(兩個順序)
    c = _fresh(); inventory.equip_weapon(c, gd, DAGGER); inventory.equip_offhand(c, gd, DAGGER2)
    inventory.equip_armor(c, gd, LIGHT)
    assert _slots(c) == {"weapon": DAGGER, "shield": LIGHT, "offhand": ""} and not inventory.is_dual_wielding(c, gd), "④ 穿盾 → 雙持解除"
    assert inventory.equip_offhand(c, gd, DAGGER2) and _slots(c) == {"weapon": DAGGER, "shield": None, "offhand": DAGGER2}, "⑤ 裝副手 → 盾被收起"
    assert inventory.is_dual_wielding(c, gd)
    # 重盾 + 副手(R219 前:匕首 + 重盾 + 副手匕首三者並存、雙持成立;現在裝重盾時匕首已被收起,主手是空手)
    c = _fresh(); inventory.equip_weapon(c, gd, DAGGER); inventory.equip_armor(c, gd, GREAT)
    assert _slots(c) == {"weapon": "fists", "shield": GREAT, "offhand": ""}
    assert inventory.equip_offhand(c, gd, DAGGER2) and _slots(c) == {"weapon": "fists", "shield": None, "offhand": DAGGER2}, "⑤ 副手把重盾擠掉(最後裝的贏)"
    assert not inventory.is_dual_wielding(c, gd), "主手是空手 → 雙持不成立(重盾 + 匕首雙持的組合不再可能)"
    # 空手時裝重盾:沒有武器可收,預覽不虛報
    c = _fresh()
    assert inventory.grip_displaced(c, gd, GREAT, "shield") == [] and inventory.equip_armor(c, gd, GREAT)


# ---------------------------------------------------------------- 4. 漏洞已封
def test_great_shield_no_longer_leaves_a_dormant_weapon_driving_other_systems():
    c = _fresh("mage")
    inventory.equip_weapon(c, gd, STAFF)
    focus = inventory.staff_spell_power(c, gd)
    assert focus > 0, "前提:魔力法杖有施法焦點"
    inventory.equip_armor(c, gd, GREAT)
    assert inventory.staff_spell_power(c, gd) == 0.0, "重盾占雙手 → 法杖焦點不再生效(原:休眠漏洞,持重盾仍吃焦點)"
    c = _fresh("archer")
    inventory.equip_weapon(c, gd, BOW); inventory.equip_armor(c, gd, GREAT)
    assert gd.item(c.weapon).get("archetype") != "bow", "重盾在手 → 弓技選單 / 連珠箭 / 騎射的判斷依據(c.weapon 為弓)不再成立"
    inventory.equip_weapon(c, gd, BOW)
    assert c.equipped.get("shield") is None and gd.item(c.weapon).get("archetype") == "bow", "反向:拿弓 → 重盾收起"


# ---------------------------------------------------------------- 5. 載入正規化 / 存檔往返
_LEGACY = {
    "重盾+劍": dict(weapon=SWORD, shield=GREAT, offhand=""),
    "重盾+弓": dict(weapon=BOW, shield=GREAT, offhand=""),
    "重盾+杖": dict(weapon=STAFF, shield=GREAT, offhand=""),
    "重盾+匕首雙持": dict(weapon=DAGGER, shield=GREAT, offhand=DAGGER2),
    "輕盾+雙持": dict(weapon=DAGGER, shield=LIGHT, offhand=DAGGER2),
    "弓+輕盾": dict(weapon=BOW, shield=LIGHT, offhand=""),
    "戰錘+重盾": dict(weapon=HAMMER, shield=GREAT, offhand=""),
    "戰錘+輕盾+副手": dict(weapon=HAMMER, shield=LIGHT, offhand=DAGGER2),
}


def _legacy(spec):
    c = _fresh()
    c.weapon, c.offhand = spec["weapon"], spec["offhand"]
    if spec["shield"]:
        c.equipped["shield"] = spec["shield"]
    return c


def test_ensure_grip_normalizes_every_legacy_state_idempotently_without_losing_items():
    for name, spec in _LEGACY.items():
        c = _legacy(spec)
        inventory.ensure_grip(c, gd)
        _check(c, name)
        once = _slots(c)
        inventory.ensure_grip(c, gd)
        assert _slots(c) == once, f"{name}:ensure_grip 必須 idempotent"
        for iid in (SWORD, DAGGER, DAGGER2, STAFF, BOW, HAMMER, SPEAR, LIGHT, GREAT):
            assert inventory.count_item(c, iid) == 1, f"{name}:{iid} 不得消失"
    c = _legacy(_LEGACY["輕盾+雙持"]); inventory.ensure_grip(c, gd)
    assert _slots(c) == {"weapon": DAGGER, "shield": LIGHT, "offhand": ""}, "輕盾 + 副手 → 留盾清副手"
    c = _legacy(_LEGACY["弓+輕盾"]); inventory.ensure_grip(c, gd)
    assert _slots(c) == {"weapon": BOW, "shield": None, "offhand": ""}, "弓 + 盾 → 雙手武器優先(與戰錘同)"
    c = _legacy(_LEGACY["重盾+劍"]); inventory.ensure_grip(c, gd)
    assert _slots(c) == {"weapon": "fists", "shield": GREAT, "offhand": ""}, "重盾 + 武器 → 留重盾,武器收起"


def test_legacy_save_round_trip_applies_the_same_invariants_and_keeps_inventory():
    for name in ("重盾+弓", "弓+輕盾", "輕盾+雙持", "重盾+杖"):
        c = _legacy(_LEGACY[name])
        state = GameState(player=c, rng=RNG(5))
        loaded = GameState.from_dict(copy.deepcopy(state.to_dict()))
        p = loaded.player
        _check(p, name)
        for iid in (BOW, STAFF, LIGHT, GREAT, DAGGER, DAGGER2):
            assert inventory.count_item(p, iid) == 1, f"{name}:存檔往返後 {iid} 仍在背包"
        before = (p.max_health, p.max_magicka, p.max_fatigue)
        stats.recompute_max_resources(p, gd)
        assert (p.max_health, p.max_magicka, p.max_fatigue) == before, f"{name}:載入後資源上限與重算一致(沒有殘留舊盾的幽靈加成)"


# ---------------------------------------------------------------- 6. 全職業 × 全出身
def test_every_class_origin_start_satisfies_the_invariants():
    n = 0
    for cid in sorted(gd.classes):
        for oid in [None] + sorted(gd.origins):
            c = build_character(gd, name="T", sex="male", race="imperial", birthsign="shadow", class_id=cid, origin_id=oid)
            _check(c, f"{cid}|{oid}")
            n += 1
    assert n >= 400, n
    # 弓手 / 斥候帶盾出身:盾不再與弓並存,但仍在背包(沒有東西消失)
    c = build_character(gd, name="T", sex="male", race="imperial", birthsign="shadow", class_id="archer", origin_id="knight_aspirant")
    assert c.weapon == "hunting_bow" and c.equipped.get("shield") is None and inventory.count_item(c, "iron_shield") >= 1


# ---------------------------------------------------------------- 7. 訊息 / 換裝對比
@contextlib.contextmanager
def _ui_driver(key):
    msgs = []
    saved = (ui.menu, ui.message, ui.item_compare_panel)
    ui.menu = lambda title, options, allow_back=False: key
    ui.message = lambda text, style=None, **k: msgs.append(text)
    ui.item_compare_panel = lambda *a, **k: None
    try:
        yield msgs
    finally:
        ui.menu, ui.message, ui.item_compare_panel = saved


def _act(c, item_id, key):
    state = GameState(player=c, rng=RNG(3))
    with _ui_driver(key) as msgs:
        M._item_actions(state, gd, item_id)
    return " ".join(msgs)


def test_equip_messages_name_exactly_what_was_put_away():
    n = gd.item_name
    c = _fresh(); inventory.equip_weapon(c, gd, SWORD)
    msg = _act(c, GREAT, "equip_a")
    assert f"你穿上了{n(GREAT)}" in msg and f"收起了{n(SWORD)}" in msg, msg
    msg = _act(c, SWORD, "equip_w")
    assert f"你握起了{n(SWORD)}" in msg and f"收起了{n(GREAT)}" in msg, msg
    c = _fresh(); inventory.equip_armor(c, gd, LIGHT)
    msg = _act(c, HAMMER, "equip_w")
    assert f"你雙手握起了{n(HAMMER)}" in msg and f"收起了{n(LIGHT)}" in msg, msg
    c = _fresh()                                                         # 什麼都沒被收起 → 不說「卸下了盾與副手」的假話
    msg = _act(c, HAMMER, "equip_w")
    assert msg.strip() == f"你雙手握起了{n(HAMMER)}。" and "卸下" not in msg and "收起" not in msg, msg
    msg = _act(_fresh(), SWORD, "equip_w")
    assert msg.strip() == f"你握起了{n(SWORD)}。", msg
    c = _fresh(); inventory.equip_weapon(c, gd, DAGGER); inventory.equip_armor(c, gd, LIGHT)
    msg = _act(c, DAGGER2, "equip_off")
    assert "擺出雙持架式" in msg and f"同時收起了{n(LIGHT)}" in msg and c.offhand == DAGGER2 and c.equipped.get("shield") is None, msg


@contextlib.contextmanager
def _capture_panels():
    got = []
    saved = (ui._web, ui._emit_panel)
    ui._web, ui._emit_panel = object(), (lambda title, rows: got.append((title, rows)))
    try:
        yield got
    finally:
        ui._web, ui._emit_panel = saved


def _kv(rows, key):
    return next((r["v"] for r in rows if r.get("t") == "kv" and r["k"] == key), None)


def test_compare_panel_previews_the_same_displacement_the_real_equip_does():
    n = gd.item_name

    def rows(c, iid):
        with _capture_panels() as got:
            ui.item_compare_panel(c, gd, iid)
        return got[0][1]

    c = _fresh(); inventory.equip_weapon(c, gd, SWORD)
    assert _kv(rows(c, GREAT), "同時收起") == n(SWORD), "預覽:換重盾會收起手持劍"
    assert _kv(rows(c, DAGGER), "同時收起") is None, "單手換單手 → 沒有東西被收起 → 不列"
    c = _fresh(); inventory.equip_armor(c, gd, GREAT)
    assert _kv(rows(c, SWORD), "同時收起") == n(GREAT)
    c = _fresh(); inventory.equip_weapon(c, gd, DAGGER); inventory.equip_offhand(c, gd, DAGGER2)
    assert _kv(rows(c, LIGHT), "同時收起") == n(DAGGER2), "預覽:穿盾會收起副手"
    c = _fresh(); inventory.equip_weapon(c, gd, HAMMER)
    assert _kv(rows(c, LIGHT), "同時收起") is None and "目前無法穿戴" in _kv(rows(c, LIGHT), "戰鬥護甲"), "被擋的裝備不宣稱收起什麼"
    assert _kv(rows(c, GREAT), "同時收起") == n(HAMMER), "重盾不被雙手武器擋,而是把它收起"
    # 預覽 = 實擲:預覽列出的就是裝上後不再裝備的那些
    c = _fresh(); inventory.equip_weapon(c, gd, SWORD)
    listed = _kv(rows(c, GREAT), "同時收起")
    inventory.equip_armor(c, gd, GREAT)
    assert listed == n(SWORD) and c.weapon == "fists"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_grip_r219 OK")
