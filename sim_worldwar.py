"""AI 陣營自走戰爭 平衡回歸模擬(worldstate 階段五)。

仿 sim_assassin.py:print-only、PYTHONPATH=. python3 sim_worldwar.py、`⚠` 旗標供人眼覆核(不自動擋)。
跑純 AI(玩家不選邊)多 seed × 多週,驗:不雪球一統 / 中立緩衝存活 / 世界不凍結 / 每週翻城 ≤ 上限 /
決定性可重播 / 反攻玩家城「失守 ≥ N 週且 reinforce 守得住」/ 玩家選邊有感。

改 aiwar.py / politics.py 常數後必跑;全綠(無 ⚠)才算平衡達標。
"""
import collections

from tesrpg.creation import build_character
from tesrpg.gamedata import get_gamedata
from tesrpg.rng import RNG
from tesrpg.state import GameState
from tesrpg.systems import aiwar, politics

GD = get_gamedata()
SEEDS = list(range(12))
WEEKS = 150


def _mk(seed, alleg=""):
    c = build_character(GD, name="史", sex="male", race="imperial",
                        birthsign="warrior", class_id="warrior")
    c.allegiance = alleg
    return GameState(player=c, rng=RNG(seed), game_mode="adventure")


def _shares(state):
    cmap = aiwar._controller_map(state.player, GD)
    return collections.Counter(f for f in cmap.values() if f)


def _run(seed, alleg="", weeks=WEEKS, hold=None, reinforce=False, daedric=False):
    st = _mk(seed, alleg)
    if daedric:                                   # 模擬 kvatch_falls 已觸發 → daedric 參戰
        st.player.world_events_fired.append("kvatch_falls")
        st.player.world_faction["kvatch"] = "daedric"
    if hold:
        for loc in hold:
            st.player.city_faction[loc] = alleg
            st.player.garrison_current[loc] = politics.base_garrison(GD, loc)
            st.player.tax_due_at[loc] = st.time.absolute_hours() + politics.TAX_HOURS
    flips = 0
    max_flip_week = 0
    fell_week = None
    for wk in range(1, weeks + 1):
        st.time.advance(168)
        wflips = 0
        for ev in aiwar.update(st, GD):
            if ev["kind"] == "flip":
                flips += 1
                wflips += 1
        max_flip_week = max(max_flip_week, wflips)
        if hold:
            if reinforce:
                for loc in list(st.player.city_faction):
                    politics.reinforce_garrison(st.player, GD, loc, 999)  # 每週滿補(模擬玩家回防)
            for ev in politics.tick_tax(st, GD):
                if ev["kind"] == "revolt" and fell_week is None:
                    fell_week = wk
    return st, flips, max_flip_week, fell_week


def main():
    warns = []
    print("=" * 72)
    print(f"AI 戰爭收斂模擬:{len(SEEDS)} seeds × {WEEKS} 週(純 AI,玩家不選邊)")
    print("=" * 72)
    start = _shares(_mk(0))
    print(f"開局分布: {dict(start)}  (共 {sum(start.values())} 城)")
    print(f"{'seed':>4} {'imp':>4} {'ind':>4} {'dae':>4} {'neu':>4} {'最大占比':>8} {'活陣營':>6} {'總翻城':>6} {'單週峰':>6}")
    agg = collections.Counter()
    max_share_all = 0.0
    for s in SEEDS:
        st, flips, peak, _ = _run(s)
        sh = _shares(st)
        tot = sum(sh.values()) or 1
        mx = max(sh.values()) / tot
        max_share_all = max(max_share_all, mx)
        agg["alive"] += len([f for f in sh if sh[f] > 0])
        agg["neutral"] += sh.get("neutral", 0)
        flag = ""
        if mx > 0.70: flag += " ⚠雪球一統"
        if len([f for f in sh if sh[f] > 0]) < 3: flag += " ⚠過度收斂"
        if sh.get("neutral", 0) < aiwar.NEUTRAL_FLOOR: flag += " ⚠中立吞光"
        if flips == 0: flag += " ⚠世界凍結"
        if peak > aiwar.MAX_FLIPS_PER_WEEK: flag += " ⚠單週多翻"
        if flag: warns.append(f"seed{s}:{flag}")
        print(f"{s:>4} {sh.get('imperial',0):>4} {sh.get('independent',0):>4} {sh.get('daedric',0):>4} "
              f"{sh.get('neutral',0):>4} {mx:>7.0%} {len([f for f in sh if sh[f]>0]):>6} {flips:>6} {peak:>6}{flag}")

    print("-" * 72)
    print(f"全 seed 最大占比上限 = {max_share_all:.0%}(紅線 <70%);平均活陣營 = {agg['alive']/len(SEEDS):.1f}(紅線 ≥3)")

    # 決定性:同 seed 兩跑完全一致
    a, b = _run(3), _run(3)
    det = _shares(a[0]) == _shares(b[0]) and a[1] == b[1]
    print(f"決定性重播: {'✓ 一致' if det else '⚠ 非決定性'}")
    if not det: warns.append("⚠ 非決定性")

    # 反攻玩家城:持 3 前線城,不回防 → 失守週數;每週回防 → 守得住
    FRONT = ["whiterun", "riften", "markarth"]   # 天際前線(獨立/中立環伺)
    _, _, _, fell_no = _run(1, alleg="imperial", weeks=30, hold=FRONT, reinforce=False)
    _, _, _, fell_yes = _run(1, alleg="imperial", weeks=30, hold=FRONT, reinforce=True)
    print(f"反攻玩家城(持 {FRONT}):不回防首次失守 = 第 {fell_no} 週(紅線 ≥3 或從未);每週回防失守 = {fell_yes}(應 None)")
    if fell_no is not None and fell_no < 3: warns.append(f"⚠ 離線速失(第{fell_no}週)feels-bad")
    if fell_yes is not None: warns.append(f"⚠ 回防無效(第{fell_yes}週仍失守)")

    # 玩家選邊:既要「有感」(支持的陣營明顯壯大),又**不可雪球一統**(審查抓到的真實情境)
    SNOW = 0.75
    imp_supp, imp_opp = [], []
    side_max = 0.0
    for s in SEEDS[:6]:
        for alleg in ("imperial", "independent"):
            sh = _shares(_run(s, alleg=alleg, weeks=120)[0])
            tot = sum(sh.values()) or 1
            mx = max(sh.values()) / tot
            side_max = max(side_max, mx)
            if mx > SNOW:
                warns.append(f"⚠ 選邊雪球(支持{alleg} seed{s} → {mx:.0%})")
            if len([f for f in sh if sh[f] > 0]) < 2:
                warns.append(f"⚠ 選邊致陣營全滅(支持{alleg} seed{s})")
            (imp_supp if alleg == "imperial" else imp_opp).append(sh.get("imperial", 0))
    a, b = sum(imp_supp) / len(imp_supp), sum(imp_opp) / len(imp_opp)
    print(f"選邊有感:支持帝國→帝國均 {a:.1f} 城 vs 支持獨立→帝國均 {b:.1f} 城(差 {a-b:+.1f},應 ≥2)")
    print(f"選邊不雪球:各 seed×陣營 最大占比上限 = {side_max:.0%}(紅線 <{SNOW:.0%})")
    if a - b < 2: warns.append("⚠ 選邊無感")

    # daedric 參戰(kvatch_falls 後)同樣不可雪球 / 中立緩衝存活
    dae_max = 0.0
    for s in SEEDS[:4]:
        sh = _shares(_run(s, daedric=True, weeks=120)[0])
        tot = sum(sh.values()) or 1
        dae_max = max(dae_max, max(sh.values()) / tot)
        if sh.get("neutral", 0) < aiwar.NEUTRAL_FLOOR:
            warns.append(f"⚠ daedric 局中立吞光(seed{s})")
        if max(sh.values()) / tot > SNOW:
            warns.append(f"⚠ daedric 局雪球(seed{s} → {max(sh.values())/tot:.0%})")
    print(f"daedric 參戰:最大占比上限 = {dae_max:.0%}(紅線 <{SNOW:.0%},中立緩衝須存活)")

    print("=" * 72)
    if warns:
        print("平衡未達標:")
        for w in warns: print("  " + w)
    else:
        print("✅ AI 戰爭平衡全綠(收斂/中立緩衝/決定性/反攻 feels-bad/選邊有感 皆達標)")


if __name__ == "__main__":
    main()
