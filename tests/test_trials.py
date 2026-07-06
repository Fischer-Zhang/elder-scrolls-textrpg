"""R124 試煉指引三層:門檻觸發提示 + NPC 流言指向 + codex 索引。純衍生·零存檔欄。"""
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import dialogue, trials
from tesrpg.state import GameState

_TRIAL_TAGS = {"shrine", "divine", "arcane_trials", "holy_trials"}


def _mage(resto=0, dest=0, level=1):
    gd = get_gamedata()
    c = build_character(gd, name="P", sex="male", race="altmer", birthsign="mage", class_id="mage")
    c.skills["restoration"] = resto; c.skills["destruction"] = dest; c.level = level
    return gd, c


# ── ① 門檻觸發 ────────────────────────────────────────────────────────────
def test_newcomer_has_no_eligible_trial():
    gd, c = _mage(level=1)
    assert trials.eligible_families(c, gd) == set()   # 排除無 site 的九神朝聖 → 新手零誤報


def test_thresholds_open_families():
    gd, c = _mage(level=15)
    fam = trials.eligible_families(c, gd)
    assert "daedric" in fam and "divine" in fam        # L15 開戴德拉/九神
    gd, c2 = _mage(resto=75, level=18)
    assert "holy" in trials.eligible_families(c2, gd)   # 復原 75 開破曉
    gd, c3 = _mage(dest=75, level=18)
    assert "arcane" in trials.eligible_families(c3, gd)  # 毀滅 75 開奧術


def test_hint_fires_once_then_dedup():
    gd, c = _mage(resto=75, level=18)
    st = GameState(player=c)
    seed = trials.seed_hinted(_mage(resto=74, level=18)[1], gd)   # 種入:尚未夠格破曉
    assert "holy" not in seed
    ev = trials.update(st, gd, set(seed))
    assert any("破曉" in e for e in ev)                 # 新夠格 → 破曉提示
    # 已夠格重載 → 不重報
    seed2 = trials.seed_hinted(c, gd)
    assert trials.update(st, gd, set(seed2)) == []


# ── ② NPC 流言指向 ────────────────────────────────────────────────────────
def test_npc_rumor_points_to_trial_and_dedups():
    gd, c = _mage()
    c.npc_disposition = {"daggerfall_courtmage": 50}
    r = dialogue.offered_rumor(c, gd, "daggerfall_courtmage")
    assert r == {"kind": "trial", "id": "daggerfall"}
    assert "破曉試煉" in trials.site_pointer(gd, "daggerfall")
    c.dialogue_done.setdefault("daggerfall_courtmage", []).append(dialogue._TRIAL_HEARD)
    assert dialogue.offered_rumor(c, gd, "daggerfall_courtmage") is None   # 一次性


def test_site_pointer_covers_all_trial_tags():
    gd = get_gamedata()
    w = gd.world["locations"]
    for tag in _TRIAL_TAGS:
        loc = next((lid for lid, v in w.items() if v.get(tag)), None)
        assert loc and trials.site_pointer(gd, loc) and "值得你走一趟" not in trials.site_pointer(gd, loc)


# ── ③ codex 索引 ─────────────────────────────────────────────────────────
def test_hint_geography_is_accurate():
    # 審查修:九神祭壇僅在賽羅迪爾(八城·非八省)、奧術試煉僅 4 省 → 提示文字不得誤稱「八省」
    hints = {src: h for src, _, _, _, h in trials.FAMILIES}
    assert "八省" not in hints["divine"] and "賽羅迪爾" in hints["divine"]
    assert "各省" not in hints["arcane"]


def test_index_lists_ultimate_trials():
    gd = get_gamedata()
    rows = trials.index_sites(gd)
    fams = {fam for fam, _, _, _ in rows}
    assert fams == {"奧術試煉", "破曉試煉"}              # 秘術 + 聖光終極(戴德拉/九神有各自索引)
    assert any("匕落" in where for _, where, _, _ in rows)   # 破曉試煉在匕落


# ── schema 守衛:rumor_trial 目標必為帶試煉 tag 的合法地點 ──────────────────
def test_rumor_trial_targets_are_valid_trial_sites():
    gd = get_gamedata()
    w = gd.world["locations"]
    for nid, npc in gd.npcs.items():
        tl = npc.get("rumor_trial")
        if tl:
            assert tl in w, f"{nid} rumor_trial 指向不存在地點 {tl}"
            assert any(w[tl].get(t) for t in _TRIAL_TAGS), f"{nid} rumor_trial {tl} 無試煉 tag"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_trials OK")
