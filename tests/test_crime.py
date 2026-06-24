"""crime 系統薄測試:逐省賞金隔離、坐牢時數下限/單調、繳罰金兩分支、行竊機率有界、所在省。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import crime


def _char(**kw):
    gd = get_gamedata()
    c = build_character(gd, name="C", sex="male", race="imperial", birthsign="thief", class_id="thief")
    for k, v in kw.items():
        setattr(c, k, v)
    return gd, c


def test_bounty_is_per_province_isolated():
    gd, c = _char()
    crime.add_bounty(c, "天際", 100)
    assert crime.bounty(c, "天際") == 100
    assert crime.bounty(c, "賽羅迪爾") == 0                # 他省不受影響
    crime.add_bounty(c, "天際", 50)
    assert crime.bounty(c, "天際") == 150                  # 同省累加
    crime.clear_bounty(c, "天際")
    assert crime.bounty(c, "天際") == 0
    crime.add_bounty(c, "賽羅迪爾", 30)
    assert crime.bounty(c, "賽羅迪爾") == 30 and crime.bounty(c, "天際") == 0


def test_jail_hours_floor_and_monotonic():
    assert crime.jail_hours(0) == 6                        # 下限 6 小時(即使零賞金也關一下)
    assert crime.jail_hours(10) >= 6
    assert crime.jail_hours(1000) > crime.jail_hours(100)  # 賞金越高坐越久


def test_pay_fine_both_branches():
    gd, c = _char(gold=200, location_id="bruma")           # bruma = 賽羅迪爾城
    crime.add_bounty(c, "賽羅迪爾", 500)
    r = crime.pay_fine(c, gd)
    assert not r["ok"] and r["owed"] == 500 and c.gold == 200   # 付不起 → 不扣、賞金留著
    assert crime.bounty(c, "賽羅迪爾") == 500
    c.gold = 800
    r2 = crime.pay_fine(c, gd)
    assert r2["ok"] and r2["paid"] == 500 and c.gold == 300 and crime.bounty(c, "賽羅迪爾") == 0


def test_steal_chance_bounded_and_rises_with_skill():
    gd, c = _char()
    c.skills["sneak"] = 0; c.skills["security"] = 0
    lo = crime.steal_chance(c, gd)
    c.skills["sneak"] = 100; c.skills["security"] = 100
    hi = crime.steal_chance(c, gd)
    assert 0.05 <= lo <= 0.95 and 0.05 <= hi <= 0.95       # 夾 [0.05, 0.95]
    assert hi > lo                                          # 潛行/安全越高越易得手


def test_province_of_reads_location():
    gd, c = _char(location_id="bruma")
    assert crime.province_of(c, gd) == "賽羅迪爾"


# --- R84 通緝身份:雙軸衍生(active_heat 可清 / outlaw_standing 終身)-----------
def test_max_bounty_takes_max_not_sum():
    gd, c = _char()
    crime.add_bounty(c, "天際", 200)
    crime.add_bounty(c, "賽羅迪爾", 150)
    assert crime.max_bounty(c) == 200          # 取最大省,非加總(否則 350)
    _, empty = _char()
    assert crime.max_bounty(empty) == 0         # 無賞金 → 0


def test_active_heat_thresholds():
    gd, c = _char()
    for b, tier in [(0, 0), (79, 0), (80, 1), (299, 1), (300, 2), (699, 2), (700, 3), (1500, 3)]:
        c.bounties = {"天際": b}
        assert crime.active_heat(c) == tier, (b, tier)


def test_outlaw_standing_thresholds():
    gd, c = _char()
    for inf, tier in [(0, 0), (4, 0), (5, 1), (19, 1), (20, 2), (49, 2), (50, 3), (200, 3)]:
        c.infamy = inf
        assert crime.outlaw_standing(c) == tier, (inf, tier)


def test_two_axes_decoupled_clearable_vs_lifetime():
    """付清賞金冷卻路途(active_heat 降)但不抹去地下身份(outlaw_standing 不變)——雙軸契約。"""
    gd, c = _char()
    c.infamy = 25                               # 終身惡名 → outlaw tier2
    crime.add_bounty(c, "天際", 400)            # 當前賞金 → active_heat 2
    assert crime.active_heat(c) == 2 and crime.outlaw_standing(c) == 2
    assert crime.is_outlaw(c)
    crime.clear_bounty(c, "天際")               # 付清/坐牢
    assert crime.active_heat(c) == 0            # 路途降溫
    assert crime.outlaw_standing(c) == 2        # 地下身份不變
    assert crime.is_outlaw(c)                   # 仍是亡命徒(惡名讓門常開)


def test_is_outlaw_dual_gate():
    gd, c = _char()
    assert not crime.is_outlaw(c)               # 乾淨之身
    crime.add_bounty(c, "天際", 30)             # 低惡名但有賞金 → 開門
    assert crime.is_outlaw(c)
    crime.clear_bounty(c, "天際")
    c.infamy = 5                                # 無賞金但惡名達 tier1 → 門常開
    assert crime.is_outlaw(c)


def test_notoriety_title_and_fence_bonus_monotonic():
    gd, c = _char()
    titles, fences = [], []
    for inf in (0, 5, 20, 50):
        c.infamy = inf
        titles.append(crime.notoriety_title(c))
        fences.append(crime.fence_bonus(c))
    assert titles == ["", "通緝犯", "惡名昭彰", "江湖鬼影"]
    assert fences == [0.0, 0.15, 0.30, 0.45]    # 銷贓加價上限 0.45


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_crime")
