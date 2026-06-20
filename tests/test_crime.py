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


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_crime")
