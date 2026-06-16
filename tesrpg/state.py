"""遊戲世界狀態:時間/曆法、玩家角色,以及 JSON 存讀檔。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tesrpg.models import Character
from tesrpg.rng import RNG

# 上古卷軸曆法:12 個月(此處每月統一 30 天,簡化處理)
MONTH_NAMES = [
    "晨星月", "日昇月", "初種月", "雨手月", "次種月", "仲年月",
    "日高月", "末種月", "爐火月", "霜落月", "日暮月", "夜星月",
]
DAYS_PER_MONTH = 30
HOURS_PER_DAY = 24


def _day_part(hour: int) -> str:
    if hour < 6:
        return "深夜"
    if hour < 10:
        return "清晨"
    if hour < 12:
        return "上午"
    if hour < 14:
        return "正午"
    if hour < 18:
        return "午後"
    if hour < 21:
        return "黃昏"
    return "夜晚"


@dataclass
class GameTime:
    era: int = 3          # 紀元(3E)
    year: int = 433
    month: int = 1        # 1..12
    day: int = 1          # 1..30
    hour: int = 8         # 0..23

    def advance(self, hours: int) -> None:
        self.hour += hours
        while self.hour >= HOURS_PER_DAY:
            self.hour -= HOURS_PER_DAY
            self.day += 1
            if self.day > DAYS_PER_MONTH:
                self.day = 1
                self.month += 1
                if self.month > 12:
                    self.month = 1
                    self.year += 1

    @property
    def day_part(self) -> str:
        return _day_part(self.hour)

    def absolute_hours(self) -> int:
        """自紀元起算的總時數,用於計算經過時間。"""
        return ((((self.year * 12) + (self.month - 1)) * DAYS_PER_MONTH
                 + (self.day - 1)) * HOURS_PER_DAY + self.hour)

    def label(self) -> str:
        return (f"{self.era}E{self.year} {MONTH_NAMES[self.month - 1]} "
                f"{self.day}日 {self.hour:02d}時({self.day_part})")

    def to_dict(self) -> dict:
        return {"era": self.era, "year": self.year, "month": self.month,
                "day": self.day, "hour": self.hour}

    @classmethod
    def from_dict(cls, d: dict) -> "GameTime":
        return cls(**d)


class GameState:
    SAVE_VERSION = 2

    # 遊戲模式:legend = roguelike 永久死亡;adventure = 死亡可讀檔重來
    LEGEND = "legend"
    ADVENTURE = "adventure"

    def __init__(self, player: Character, time: GameTime | None = None, rng: RNG | None = None,
                 start_time: GameTime | None = None, game_mode: str = "adventure"):
        self.player = player
        self.time = time or GameTime()
        self.rng = rng or RNG()
        # 記錄開局時間以結算「在世年數」;預設等於當前時間
        self.start_time = start_time or GameTime(**self.time.to_dict())
        self.game_mode = game_mode

    # --- 存讀檔 -----------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "version": self.SAVE_VERSION,
            "time": self.time.to_dict(),
            "start_time": self.start_time.to_dict(),
            "game_mode": self.game_mode,
            "rng": {"seed": self.rng.seed, "state": self.rng.get_state()},
            "player": self.player.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        rng = RNG(d["rng"].get("seed"))
        if d["rng"].get("state") is not None:
            rng.set_state(d["rng"]["state"])
        time = GameTime.from_dict(d["time"])
        # 舊版(無 start_time)存檔:一律以遊戲起始時刻(預設紀元)為準,而非當前時間,
        # 否則在世年數會被算成 0。
        start = GameTime.from_dict(d["start_time"]) if "start_time" in d else GameTime()
        player = Character.from_dict(d["player"])
        # 改版前存檔:把停用的 level_progress 進度遷移成 level_xp,讓載入當下 can_level_up 即正確
        # (否則已可升級的舊存檔,升級入口要等到下次 use_skill 才出現)。區域 import 避免循環。
        from tesrpg.gamedata import get_gamedata
        from tesrpg.systems import aiwar, dagon_boon, lycanthropy, potion_buff, progression, skooma
        progression.ensure_level_xp(player)
        progression.ensure_all_skills(player, get_gamedata())   # 補上新增技能(scout 等)
        progression.ensure_mastery_choices(player, get_gamedata())   # 里程碑 v2:補欄/清陳舊選擇/重算 fortify
        skooma.ensure_skooma_fields(player, time, get_gamedata())   # 斯庫瑪:補欄 + 依當前時間重算亢奮/戒斷層
        potion_buff.ensure_potion_fields(player, time, get_gamedata())   # 限時增益藥水:補欄 + 依當前時間剔除過期(R30)
        lycanthropy.ensure_lycanthropy_fields(player, time, get_gamedata())   # 狼人:補欄 + 過期獸形自動變回 + 夾血
        dagon_boon.ensure_dagon_fields(player, get_gamedata())   # 達貢之力:補欄 + 依 flag 重算永久層
        aiwar.ensure_war_fields(player, time)   # AI 戰爭:補欄 + war_tick_at 起算下個整週
        return cls(
            player=player,
            time=time,
            rng=rng,
            start_time=start,
            game_mode=d.get("game_mode", "adventure"),
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "GameState":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
