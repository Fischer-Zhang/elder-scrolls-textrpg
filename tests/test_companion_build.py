"""同伴戰術傾向(羈絆階解鎖·永久·功能性非數值)測試:門檻閘、永久拒改選、tactic kind 映射。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.systems import party


def _char(cid="veteran"):
    gd = get_gamedata()
    c = build_character(gd, name="B", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.companions.append(cid)
    return gd, c


def test_gate_blocks_below_tier():
    gd, c = _char()
    assert not party.build_offerable(c, gd, "veteran")     # 羈絆 0 < gate 1
    c.companion_bond["veteran"] = party.BOND_TIERS[0]       # 升到門檻(tier 1)
    assert party.build_offerable(c, gd, "veteran")


def test_choose_is_permanent():
    gd, c = _char()
    c.companion_bond["veteran"] = party.BOND_TIERS[0]
    assert party.choose_build(c, gd, "veteran", "bulwark")
    assert party.companion_tactic(c, gd, "veteran") == "taunt"
    assert not party.build_offerable(c, gd, "veteran")     # 選定後不再可選
    assert not party.choose_build(c, gd, "veteran", "skirmisher")   # 拒改選
    assert party.companion_tactic(c, gd, "veteran") == "taunt"


def test_tactic_kind_mapping():
    gd, c = _char()
    c.companion_bond["veteran"] = party.BOND_TIERS[0]
    party.choose_build(c, gd, "veteran", "skirmisher")
    assert party.companion_tactic(c, gd, "veteran") == "focus"
    assert party.build_label(c, "veteran") == party.TACTICS["skirmisher"]["label"]


def test_vanguard_is_none():
    gd, c = _char()
    c.companion_bond["veteran"] = party.BOND_TIERS[0]
    party.choose_build(c, gd, "veteran", "vanguard")
    assert party.companion_tactic(c, gd, "veteran") is None   # 均衡 = 預設隨機(既有行為)


def test_all_tactics_valid_and_labeled():
    for bid, spec in party.TACTICS.items():
        assert "label" in spec and "desc" in spec and "tactic" in spec
        assert spec["tactic"] in (None, "taunt", "focus")


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_companion_build OK")
