"""R82 套話/秘密 功能化回歸:修正 _do_pump 誤讀來源(秘密本在 dialogue.json 覆寫層)+
功能化秘密(藏寶 gold/item·線索 start_quest)一次性兌現·防刷·schema。"""

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import dialogue, inventory

_PUMP = {"id": "pump_for_info", "action": "pump"}


def _mk():
    gd = get_gamedata()
    c = build_character(gd, name="套", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    c.skills["speechcraft"] = 100          # 確保套話高成功率
    return gd, c


def _pump(gd, c, nid):
    st = GameState(player=c, rng=RNG(1), game_mode="adventure")
    return dialogue._do_pump(st, gd, nid, _PUMP, dialogue.talk_ctx(st, gd, nid), RNG(1))


def test_pump_reveals_dialogue_secret_not_default():
    """修正 bug:既有 flavor 秘密本在 dialogue.json 覆寫層,套話應真實揭露(非預設旁白)。"""
    gd, c = _mk()
    r = _pump(gd, c, "riften_brynjolf")
    assert r["ok"] and "鼠道" in r["text"]      # 揭露真實秘密
    assert "對方壓低聲音" not in r["text"]       # 不是預設旁白


def test_pump_stash_gold_once():
    gd, c = _mk()
    g0 = c.gold
    _pump(gd, c, "whiterun_steward")             # 撬出藏寶金
    assert c.gold - g0 == 60
    g1 = c.gold
    _pump(gd, c, "whiterun_steward")             # 再套話:只重述、不重發(防刷)
    assert c.gold == g1
    assert dialogue._PUMP_PAID in c.dialogue_done.get("whiterun_steward", [])


def test_pump_stash_item():
    gd, c = _mk()
    n0 = inventory.count_item(c, "lockpick")
    _pump(gd, c, "balmora_armsdealer_neloth")
    assert inventory.count_item(c, "lockpick") - n0 == 3


def test_pump_lead_starts_cache_quest():
    gd, c = _mk()
    _pump(gd, c, "daggerfall_courtmage")
    assert "secret_wendir" in c.quests
    assert gd.quests["secret_wendir"]["source"] == "npc"


def test_pump_failure_no_payout():
    gd, c = _mk()
    c.skills["speechcraft"] = 0               # 低口才 → 套話多半失敗
    # pry_chance 夾下限 0.1;用注定失敗的 rng(roll 1.0 ≥ 任何 chance → 失敗分支)
    st = GameState(player=c, rng=RNG(1), game_mode="adventure")

    class _Fail:
        def chance(self, p):
            return False
    g0 = c.gold
    r = dialogue._do_pump(st, gd, "whiterun_steward", _PUMP,
                          dialogue.talk_ctx(st, gd, "whiterun_steward"), _Fail())
    assert not r["ok"] and c.gold == g0       # 失敗 → 不兌現


def test_secret_schema_str_or_dict():
    gd, _ = _mk()
    types = {"gold", "item", "start_quest", "fame", "infamy", "message", "skill_xp",
             "heal", "restore_magicka", "restore_fatigue", "damage", "learn_spell",
             "combat", "restore_fatigue", "faction_standing"}
    for nid, npc in gd.dialogue.get("npcs", {}).items():
        sec = npc.get("secret")
        assert sec is None or isinstance(sec, (str, dict))
        if isinstance(sec, dict):
            for e in sec.get("effects", []):
                assert e["type"] in types
                if e["type"] == "start_quest":
                    assert e["quest"] in gd.quests
                if e["type"] == "item":
                    assert gd.item_or_none(e["item"]) is not None


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("test_secrets 全通過")
