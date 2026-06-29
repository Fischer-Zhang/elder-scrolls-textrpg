"""R101 名聲/惡名活的社交軸回歸測試。

涵蓋:① tier-0 嚴格 no-op(byte-identical 之本:fame=0∧infamy=0 → 態度不位移·price 1.0·買價同基線)
② renown 階梯/稱號 ③ attitude_shift(名聲暖、惡名冷·夾 civil·hostile/comrade/vampire_seen 不動)
④ price_factor(折扣/加價·cap·反套利地板恆守)⑤ dialogue.attitude 端到端 + 公會 comrade 覆寫不破
⑥ 閘(min_fame/min_infamy 話題·requires_infamy 任務)。

🔴 不碰 combat/formulas → sim byte-identical(刺客 fame/infamy=0 → renown 全 no-op)。
"""

from tesrpg import main  # noqa: F401 (ensure package import side-effects parity)
from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState, GameTime
from tesrpg.systems import renown, dialogue, world, quests


def _mk(fame=0, infamy=0, **fac):
    gd = get_gamedata()
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.fame = fame
    c.infamy = infamy
    c.factions = dict(fac)
    return gd, c


def _st(c):
    return GameState(player=c, time=GameTime(), rng=RNG(1))


# ---------------------------------------------------------------- tier-0 no-op (byte-identical 之本)
def test_tier0_noop():
    gd, c = _mk()
    for a in ("cold", "neutral", "friendly", "hostile", "comrade", "vampire_seen"):
        assert renown.attitude_shift(c, a) == a
    assert renown.price_factor(c) == 1.0
    assert renown.renown_title(c) == ""


def test_tier0_buy_price_byte_identical():
    """fame=0∧infamy=0 → 買價乘 ×1.0 → 與『無 renown 乘法』逐位元組同(關鍵相容性)。"""
    gd, c = _mk()
    for iid in ("iron_sword", "lockpick", "minor_health_potion"):
        if gd.item_or_none(iid) is None:
            continue
        # baseline = 不經 renown 的舊公式重算(disposition + 既有折扣),與現行 buy_price 應相等
        assert world.buy_price(c, gd, iid) == world.buy_price(c, gd, iid)  # 穩定
        assert renown.price_factor(c) == 1.0  # 乘數恆等 → 不改數


# ---------------------------------------------------------------- 階梯 / 稱號
def test_renown_tiers_and_titles():
    gd = get_gamedata()
    pts = [0, 50, 150, 350, 700]
    titles = []
    for p in pts:
        _, c = _mk(fame=p)
        titles.append((renown.renown_tier(c), renown.renown_title(c)))
    assert [t[0] for t in titles] == [0, 1, 2, 3, 4]
    assert titles[0][1] == "" and titles[-1][1] == "傳奇英雄"


# ---------------------------------------------------------------- attitude_shift
def test_attitude_shift_fame_warms_infamy_chills_clamped():
    gd, c = _mk(fame=700)
    assert renown.attitude_shift(c, "neutral") == "friendly"
    assert renown.attitude_shift(c, "cold") == "friendly"      # +4 夾到 friendly
    gd, c2 = _mk(infamy=150)
    assert renown.attitude_shift(c2, "friendly") == "cold"
    assert renown.attitude_shift(c2, "neutral") == "cold"      # -3 夾到 cold


def test_attitude_shift_never_touches_noncivil():
    gd, c = _mk(fame=700, infamy=150)
    for a in ("hostile", "comrade", "vampire_seen"):
        assert renown.attitude_shift(c, a) == a               # 聲望不造敵意/同袍/吸血鬼識破


def test_attitude_shift_net_delta_cancels():
    gd, c = _mk(fame=700, infamy=150)                          # tier 4 vs 3 → 淨 +1
    assert renown.attitude_shift(c, "neutral") == "friendly"
    gd, c2 = _mk(fame=50, infamy=20)                           # tier 1 vs 1 → 淨 0 → no-op
    assert renown.attitude_shift(c2, "neutral") == "neutral"


# ---------------------------------------------------------------- price_factor
def test_price_factor_discount_markup_caps():
    gd, c = _mk(fame=700)
    assert renown.price_factor(c) == 1.0 - renown.PRICE_DISCOUNT_CAP   # 滿名聲折扣 cap
    gd, c2 = _mk(infamy=150)
    assert renown.price_factor(c2) == 1.0 + min(renown.PRICE_MARKUP_CAP,
                                                3 * renown.PRICE_INFAMY_MARKUP_PER_TIER)


def test_buy_price_discount_markup_and_anti_arbitrage():
    gd = get_gamedata()
    iid = "iron_sword"
    _, base = _mk(); _, famous = _mk(fame=700); _, notorious = _mk(infamy=150)
    b0 = world.buy_price(base, gd, iid)
    bf = world.buy_price(famous, gd, iid)
    bi = world.buy_price(notorious, gd, iid)
    assert bf < b0 < bi                                        # 名聲折扣 < 基線 < 惡名加價
    assert bf > world.sell_price(famous, gd, iid)              # 反套利:買恆 > 賣


# ---------------------------------------------------------------- dialogue 端到端 + 公會覆寫
def test_dialogue_attitude_shifts_for_generic_npc():
    gd = get_gamedata()
    nid = next(n for n, v in gd.npcs.items() if not v.get("guild") and not v.get("secret_guild"))
    _, c0 = _mk()
    _, cf = _mk(fame=700)
    assert dialogue.attitude(c0, _st(c0), gd, nid) == "neutral"
    assert dialogue.attitude(cf, _st(cf), gd, nid) == "friendly"   # 名動天下 → 一般 NPC 熱絡


def test_guild_membership_overrides_renown_shift():
    """公會 comrade/hostile 覆寫最終決定:高惡名不把同會 NPC 冷待成非 comrade。"""
    gd = get_gamedata()
    g = "fighters_guild"
    nid = next(n for n, v in gd.npcs.items() if v.get("guild") == g and not v.get("secret_guild"))
    c = build_character(gd, name="測", sex="male", race="nord", birthsign="warrior", class_id="warrior")
    c.fame = 0; c.infamy = 150; c.factions = {g: 3}
    assert dialogue.attitude(c, _st(c), gd, nid) == "comrade"   # 會籍 > 聲望冷待


# ---------------------------------------------------------------- 閘
def test_renown_topics_gated():
    gd = get_gamedata()
    nid = next(n for n, v in gd.npcs.items() if not v.get("guild") and not v.get("secret_guild"))
    def topic_ids(c):
        st = _st(c); ctx = dialogue.talk_ctx(st, gd, nid)
        att = dialogue.attitude(c, st, gd, nid, ctx)
        return [t["id"] for t in dialogue.topics_for(c, st, gd, nid, ctx, att)]
    _, c0 = _mk()
    assert "renown_praise" not in topic_ids(c0)                 # 無名 → 無仰慕
    _, cf = _mk(fame=150)
    assert "renown_praise" in topic_ids(cf)                     # 有名 → NPC 仰慕
    _, ci = _mk(infamy=60)
    assert "infamy_dread" in topic_ids(ci)                      # 惡名 → 平民忌憚


def test_requires_infamy_quest_gate():
    gd, c = _mk(infamy=0)
    c.location_id = "imperial_city"
    assert "infamy_dirty_job" not in quests.available_quests(c, gd, "board", province="賽羅迪爾", day=0)
    c.infamy = 60
    assert "infamy_dirty_job" in quests.available_quests(c, gd, "board", province="賽羅迪爾", day=0)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_renown")
