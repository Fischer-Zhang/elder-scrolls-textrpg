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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
