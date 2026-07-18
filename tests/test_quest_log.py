"""任務日誌分桶(R168)守衛測試。

現況擴桶前零測試防護 → 本模組鎖住:17 種 source 全登錄查表、faction⟺guild 雙向等價
(刻意 trip-wire:資料漂移即紅燈,漂移時須有意識決定該 source 的歸桶)、代表任務歸對桶、
未知 source 三層後備(faction→公會、否則委託,永不 crash 永不消失)、view 桶序與 entry 形狀。
"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.ui import console as ui


def _char(gd):
    return build_character(gd, name="T", sex="male", race="nord", birthsign="warrior",
                           class_id="warrior", origin_id="knight_aspirant", is_player=True)


def test_all_shipped_sources_explicitly_mapped():
    """quests.json 出貨的每種 source 都必須在 _QUEST_SOURCE_BUCKET 顯式登錄 ——
    新增 source 時強制做一次有意識的歸桶決定(後備規則只兜「未來未知」,不兜出貨資料)。"""
    gd = get_gamedata()
    shipped = {q.get("source") for q in gd.quests.values()}
    unmapped = shipped - set(ui._QUEST_SOURCE_BUCKET)
    assert not unmapped, f"未登錄歸桶的 source:{unmapped}"
    valid = {k for k, _ in ui._QUEST_GROUPS}
    assert set(ui._QUEST_SOURCE_BUCKET.values()) <= valid


def test_faction_iff_guild_source():
    """faction 欄 truthy ⟺ source=='guild'(現況 51/51 雙向等價)。刻意 trip-wire:
    未來若給非 guild 任務掛 faction 欄,此測會紅 —— 屆時確認 _quest_group 的
    source-first precedence 已把它歸對桶,再更新此斷言(而非默默漂移)。"""
    gd = get_gamedata()
    for qid, q in gd.quests.items():
        assert bool(q.get("faction")) == (q.get("source") == "guild"), qid


def test_representative_quests_bucketed():
    """代表任務逐一歸對桶(source 查表;relic/undercover 併公會、四種試煉合桶)。"""
    gd = get_gamedata()
    expect = {"main_oblivion": "main", "azura_star": "trial", "pilgrimage_nine": "trial",
              "arc_blood_thrall": "companion", "fg1": "guild", "relic_vigil": "guild",
              "ucov_fighters_prove": "guild", "job_wolf": "other", "ruler_bruma1": "other"}
    for qid, bucket in expect.items():
        assert ui._quest_group(gd.quests[qid]) == bucket, (qid, ui._quest_group(gd.quests[qid]))


def test_unknown_source_three_tier_fallback():
    """未知 source:掛陣營 → 公會桶;否則 → 委託兜底桶(任何任務必落桶,永不 KeyError)。"""
    assert ui._quest_group({"source": "future_x"}) == "other"
    assert ui._quest_group({"source": "future_x", "faction": "fighters_guild"}) == "guild"
    assert ui._quest_group({}) == "other"


def test_quests_view_buckets_order_and_shape():
    """_quests_view:桶依 _QUEST_GROUPS 序、空桶隱藏、主線桶名「湮滅危機」、entry 形狀不變。"""
    gd = get_gamedata()
    c = _char(gd)                                     # 起手任務(騎士試煉)已入 origin 桶
    for qid in ("main_oblivion", "azura_star", "arc_blood_thrall", "job_wolf"):
        c.quests[qid] = {"stage": 0}
    v = ui._quests_view(c, gd)
    titles = [g["title"] for g in v["groups"]]
    order = [t for _, t in ui._QUEST_GROUPS]
    assert titles == [t for t in order if t in titles]          # 桶序=定義序
    assert "🌋 湮滅危機" in titles and any("起手" in t for t in titles)
    assert "⚜ 公會" not in titles and "🤝 同伴" in titles       # 空桶隱藏、同伴獨立
    q = v["groups"][0]["quests"][0]                             # 主線桶第一條=main_oblivion
    assert set(q) >= {"name", "faction", "objective", "stage", "stages"}
    assert q["stage"][0] == 1 and q["stages"][0]["state"] == "cur"


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_quest_log 全通過")
