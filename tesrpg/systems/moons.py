"""月相(Masser / Secunda)—— 血月詛咒深化(R50)的共用底座。

純推導、無狀態:月相完全由遊戲時間 `time.absolute_hours()` 算出,**零新存檔欄**、
決定性(同一時間恆得同相)→ 易測、零遷移。上古卷軸有 Masser(大衛星)與 Secunda
(次月)雙月;此處以**單一週期**驅動機制(滿月/新月),雙月僅為敘述風味。

用途:
  - 狼人(lycanthropy):滿月 → 免每日變身冷卻 + 獸形時程加成(月之主宰)。
  - 吸血鬼(vampirism):滿月 → 亮夜曝獠牙、更易被識破;新月 → 暗夜助獵、進食更難被撞見。
  - UI:時間列顯示當前月相。
"""

from __future__ import annotations

# 朔望週期(日):正典 Masser 約 24 日。八相各佔 LUNAR_PERIOD_DAYS // 8 = 3 日。
LUNAR_PERIOD_DAYS = 24
PHASE_NAMES = ["新月", "眉月", "上弦月", "盈凸月", "滿月", "虧凸月", "下弦月", "殘月"]
_DAYS_PER_PHASE = LUNAR_PERIOD_DAYS // len(PHASE_NAMES)   # = 3
_NEW_BUCKET = 0      # 新月相(週期起點)
_FULL_BUCKET = 4     # 滿月相(週期中點)


def _abs_day(state_or_time) -> int:
    """接受 GameState(有 `.time`)或 GameTime 本身 → 自紀元起算的絕對日。"""
    t = getattr(state_or_time, "time", state_or_time)
    return t.absolute_hours() // 24


def phase_index(state_or_time) -> int:
    """週期內日序 0..LUNAR_PERIOD_DAYS-1。"""
    return _abs_day(state_or_time) % LUNAR_PERIOD_DAYS


def _bucket(state_or_time) -> int:
    """八相桶 0..7(新月=0、滿月=4)。"""
    return phase_index(state_or_time) // _DAYS_PER_PHASE


def phase_name(state_or_time) -> str:
    return PHASE_NAMES[_bucket(state_or_time)]


def is_full_moon(state_or_time) -> bool:
    """滿月窗(週期中點 _DAYS_PER_PHASE 日)。"""
    return _bucket(state_or_time) == _FULL_BUCKET


def is_new_moon(state_or_time) -> bool:
    """新月窗(週期起點 _DAYS_PER_PHASE 日)。"""
    return _bucket(state_or_time) == _NEW_BUCKET


def is_night(state_or_time) -> bool:
    """夜晚窗 [21:00, 6:00):吸血鬼夜視/夜行的判斷,與陽光時段 [8,18) 對位(日損夜利)。"""
    t = getattr(state_or_time, "time", state_or_time)
    h = t.hour % 24
    return h < 6 or h >= 21
