"""可重現的 seeded 隨機來源。

整個遊戲只透過一個 RNG 實例取亂數,存檔時連同 seed/state 一起序列化,
未來要做「同一 seed 重現同一局」時就靠這裡。
"""

from __future__ import annotations

import random


class RNG:
    def __init__(self, seed: int | None = None):
        self.seed = seed
        self._random = random.Random(seed)

    # --- 取值 -------------------------------------------------------------
    def randint(self, a: int, b: int) -> int:
        return self._random.randint(a, b)

    def random(self) -> float:
        return self._random.random()

    def chance(self, p: float) -> bool:
        """以機率 p (0..1) 回傳 True。"""
        return self._random.random() < p

    def choice(self, seq):
        return self._random.choice(seq)

    def roll(self, lo: float, hi: float) -> float:
        return self._random.uniform(lo, hi)

    # --- 序列化(讓存檔能完整重現亂數序列)---------------------------------
    def get_state(self):
        return self._random.getstate()

    def set_state(self, state) -> None:
        # JSON 會把 tuple 變 list,還原時轉回 tuple
        self._random.setstate(_to_tuple(state))


def _to_tuple(obj):
    if isinstance(obj, list):
        return tuple(_to_tuple(x) for x in obj)
    return obj
