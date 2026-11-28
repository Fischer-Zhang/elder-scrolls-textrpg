"""世界資料衛生守衛(R227 後續 A2):資料裡的「重複列」會悄悄影響行為,應在資料層擋下。

merchant_stock 重複 → `world.ensure_stock` 的 dict 推導式對同一個 id 擲兩次補貨骰(後者蓋前者),白白多耗一次 RNG、
也讓「補貨量」看起來是單一擲骰其實不是(R225 審查發現 cloudrest / sunhold / shimmerene 的 lavender 各列兩次)。
"""
import collections
import json
import pathlib

from tesrpg import formulas
from tesrpg.gamedata import get_gamedata

gd = get_gamedata()


def test_no_shop_lists_the_same_item_twice():
    dup = {lid: [k for k, v in collections.Counter(d.get("merchant_stock", [])).items() if v > 1]
           for lid, d in gd.world["locations"].items()}
    dup = {lid: ids for lid, ids in dup.items() if ids}
    assert not dup, dup


def test_every_listed_shop_item_exists():
    bad = {lid: [i for i in d.get("merchant_stock", []) if i not in gd.items]
           for lid, d in gd.world["locations"].items()}
    bad = {lid: ids for lid, ids in bad.items() if ids}
    assert not bad, bad


def test_codex_skills_chapter_mentions_the_training_allowance_with_the_real_number():
    root = pathlib.Path(__file__).resolve().parent.parent
    codex = json.dumps(json.load(open(root / "tesrpg" / "data" / "codex.json", encoding="utf-8")), ensure_ascii=False)
    assert f"最高教到 {formulas.TRAINER_CAP},每個角色等級最多 {formulas.TRAININGS_PER_LEVEL} 次" in codex


def _readme():
    return (pathlib.Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")


def _codex_text():
    root = pathlib.Path(__file__).resolve().parent.parent
    return json.dumps(json.load(open(root / "tesrpg" / "data" / "codex.json", encoding="utf-8")), ensure_ascii=False)


def test_readme_count_snapshot_matches_the_data():
    """「數量別盲信」:README 的數量快照要跟資料一致(R227 文字對帳發現物品數 240 vs 實際 241)。"""
    import re
    readme = _readme()
    expect = {"技能": len(gd.skills), "地點": len(gd.world["locations"]), "怪物": len(gd.bestiary), "法術": len(gd.spells),
              "同伴": len(gd.companions), "事件": len(gd.events), "物品索引": len(gd.items)}
    found = 0
    for label, n in expect.items():
        m = re.search(r"(\d+)\s*" + label, readme)
        if m:
            found += 1
            assert int(m.group(1)) == n, (label, m.group(1), n)
    assert found >= 5, found                                             # 防止格式改了、正則全落空而假綠


def test_block_stance_mechanic_text_matches_the_constant():
    skills = json.load(open(pathlib.Path(__file__).resolve().parent.parent / "tesrpg" / "data" / "skills.json", encoding="utf-8"))
    block = skills["block"] if isinstance(skills, dict) and "block" in skills else next(x for x in skills if x.get("id") == "block")
    assert f"物理 −{round(formulas.GUARD_STANCE_MITIGATION * 100)}%" in block["mechanic"], block["mechanic"]


def test_known_wrong_player_text_stays_fixed():
    """R227 文字對帳修掉的錯誤措辭不得再出現(都是『能用程式證據證明錯』的句子)。"""
    codex, readme = _codex_text(), _readme()
    for bad in ("戰鬥中也能再次隱遁脫離", "各省法師公會的『引路人』", "偶爾自動看穿材料", "傷人、殺戮會累積", "法師公會供應空靈魂石",
                "回到城鎮時』讓你領取", "終身的,繳清賞金也洗不掉", "偵察", "客棧", "擊晕", "賞金過 700"):
        assert bad not in codex, bad
    for bad in ("火焰魔人", "(失敗會折斷)", "姓名 → 性別 → 種族"):
        assert bad not in readme, bad


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
