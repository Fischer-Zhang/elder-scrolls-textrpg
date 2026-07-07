"""存檔載入遷移集中點(load migrations registry)。

`GameState.from_dict` 載入後,把所有 `ensure_*`(補新欄 / 清陳舊選擇 / 依當前時間
重算「推導快取」層)收斂在此單一有序入口。**順序即權威** —— 加新系統的載入遷移 =
此處加一行,免再改 `state.from_dict`。

刻意維持 **idempotent 全跑**(載入必跑、自癒任何存檔),不做 version-gating ——
對單機本地存檔,「載入必全跑」比版本閘更穩(不依賴存檔版本欄正確)。`from_dict`
另讀 `version` 供診斷,日後若真需要版本閘,集中於此即可。

反循環:本模組於 module-top import 各系統(已驗:無一系統於 module-top import
`state` → 零循環);`state.from_dict` 則**區域 import 本模組**(沿用原反循環模式)。
"""

from __future__ import annotations

from tesrpg.systems import (aiwar, alchemy, boons, dagon_boon, diseases, divines,
                            dungeon, housing, inventory, lycanthropy, party, potion_buff,
                            progression, skooma, spellfx, undercover, worldpulse)


def run_load_migrations(player, time, gamedata) -> None:
    """對剛載入的 player 套用全部載入遷移(順序逐字對齊原 `from_dict`,行為等價)。"""
    progression.ensure_level_xp(player)                          # 停用的 level_progress → level_xp(載入即正確 can_level_up)
    inventory.ensure_grip(player, gamedata)                      # 握法正規化:雙手武器/重盾在手 → 清殘留盾與副手(R41)
    progression.ensure_all_skills(player, gamedata)              # 補上新增技能(scout 等)
    progression.ensure_mastery_choices(player, gamedata)         # 里程碑 v2:補欄/清陳舊選擇/重算 fortify
    skooma.ensure_skooma_fields(player, time, gamedata)          # 斯庫瑪:補欄 + 依當前時間重算亢奮/戒斷層
    undercover.ensure_cover_fields(player, time, gamedata)        # 雙面間諜:補欄 + 夾限/水印自癒(零戰鬥層·R100)
    potion_buff.ensure_potion_fields(player, time, gamedata)     # 限時增益藥水:補欄 + 依當前時間剔除過期(R30)
    spellfx.ensure_spell_effect_fields(player, time, gamedata)   # 實用/幻術魔法:補欄 + 依當前時間剔除過期(R104)
    divines.ensure_divine_fields(player, time, gamedata)         # 九神祝福:補欄 + 依當前時間剔過期重算(R107)
    alchemy.ensure_known_effects(player, gamedata)               # 煉金效果揭露:補欄/防呆/清陳舊 ing_id(R32)
    lycanthropy.ensure_lycanthropy_fields(player, time, gamedata)  # 狼人:補欄 + 過期獸形自動變回 + 夾血
    dagon_boon.ensure_dagon_fields(player, gamedata)             # 達貢之力:補欄 + 依 flag 重算永久層
    boons.ensure_boon_fields(player, gamedata)                   # 戴德拉誓福:補欄 + 依持有清單重算永久層(R45)
    diseases.ensure_disease_fields(player, time, gamedata)       # 疾病:補欄 + 依當前時間重算惡化負層(R53)
    aiwar.ensure_war_fields(player, time)                        # AI 戰爭:補欄 + war_tick_at 起算下個整週
    worldpulse.ensure_pulse_fields(player)                       # 常態世界脈動:補欄(world_pulse_day/pulse_eval_day)+ 防呆冪等
    housing.ensure_housing_fields(player, time.absolute_hours()) # 家園擴建:補欄 + 型別/採收時間戳自癒(R110)
    dungeon.ensure_reinfest_fields(player, gamedata, time.absolute_hours())  # 地城再滋擾:補欄 + 舊檔回填一輪後滋擾(R111)
    party.ensure_companion_gear(player, gamedata)               # 同伴裝備:補欄 + 剔陳舊(退回背包不遺失)/型別自癒
    party.ensure_companion_build(player, gamedata)              # 同伴戰術傾向:補欄 + 剔陳舊 cid/build_id
