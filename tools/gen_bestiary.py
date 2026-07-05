"""從 data/bestiary.json 生成 BESTIARY.md 怪物圖鑑(資料驅動,杜絕手改漂移)。

跑法:python3 tools/gen_bestiary.py   → 寫出專案根的 BESTIARY.md
改了 bestiary/loot/曲目後重跑即可;數據一律以 JSON 為準(對齊 CLAUDE「數量別盲信」)。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "tesrpg", "data")


def _load(name):
    return json.load(open(os.path.join(DATA, name), encoding="utf-8"))


BEAST = _load("bestiary.json")
# 物品名稱解析:橫跨 items / weapons / armor / ingredients
NAMES = {}
for fn in ("items.json", "weapons.json", "armor.json", "ingredients.json"):
    for k, v in _load(fn).items():
        NAMES[k] = v.get("name", k)

EL = {"fire": "火", "frost": "冰", "shock": "電", "poison": "毒", "bleed": "血", "magic": "魔", "disease": "疫"}
CC = {"stagger": "踉蹌", "slow": "遲緩", "weaken": "耗弱", "fear": "恐懼", "paralyze": "麻痺"}


def iname(i):
    return NAMES.get(i, i)


def atk_line(a):
    s = f"{a.get('name', '?')} 傷{a.get('damage', '?')}/技{a.get('skill', '?')}"
    if a.get("element"):
        s += f"·{EL.get(a['element'], a['element'])}元"
    oh = a.get("on_hit")
    if oh:
        st = oh.get("status")
        ch = int(oh.get("chance", 1) * 100)
        if st == "dot":
            s += f"·{EL.get(oh.get('element'), '?')}DoT {oh.get('magnitude')}×{oh.get('turns')}@{ch}%"
        else:
            mag = f"({oh.get('magnitude')})" if oh.get("magnitude") else ""
            s += f"·{CC.get(st, st)}{mag}@{ch}%"
    if a.get("infect"):
        kind = "狼化" if a.get("infect_kind") == "lycanthropy" else "吸血"
        s += f"·感染{kind}{int(a['infect'] * 100)}%"
    if a.get("when"):
        w = a["when"]
        s += f" [血<{int(w['hp_below'] * 100)}%]" if "hp_below" in w else f" [血>{int(w['hp_above'] * 100)}%]"
    if a.get("cooldown"):
        s += f" [冷卻{a['cooldown']}]"
    if a.get("weight", 1) != 1:
        s += f" ·權{a['weight']}"
    return s


def loot_line(v):
    g = v.get("loot_gold", [0, 0])
    parts = [f"金幣 {g[0]}–{g[1]}"] if (g[0] or g[1]) else ["金幣 0"]
    for e in v.get("loot", []):
        parts.append(f"{iname(e['item'])}({int(e.get('chance', 0) * 100)}%)")
    return " · ".join(parts)


def resist_line(r):
    if not r:
        return ""
    return "抗性:" + " ".join(f"{EL.get(k, k)}{v:+d}" for k, v in r.items())


def flags(k, v):
    f = []
    if v.get("solo"):
        f.append("SOLO首領")
    if v.get("raw"):
        f.append("raw·已調校")
    if v.get("sentient"):
        f.append("人形")
    if v.get("undead"):
        f.append("不死")   # R122 聖光(holy)剋不死:受聖光傷害放大、可被驅散亡者驅散
    if v.get("weight", 1) == 0:
        f.append("腳本/召喚·不進野外池")
    return ("【" + " · ".join(f) + "】") if f else ""


def biome(v):
    return ("、".join(v["biomes"])) if v.get("biomes") else "通用"


HEADER = """# BESTIARY —— 流亡者 (tesrpg) 怪物圖鑑

> ⚠ **本檔由 `tools/gen_bestiary.py` 從 `tesrpg/data/bestiary.json` 自動生成 —— 請勿手改。**
> 改了怪物資料/掉落/曲目後執行 `python3 tools/gen_bestiary.py` 重生(數據一律以 JSON 為準)。
"""

BEHAVIOR = """## 行為系統(怪物怎麼打)

**① 每回合選招** —— 無戰術 AI,唯一的選擇是「攻擊哪招、打誰」:
- 有曲目者走 `combat.choose_attack`(R43):**加權隨機** + **血量階段閘**(`血<X%` 暴怒招)+ **蓄力冷卻**(`冷卻N` 大招約每 N 回合一次)。單攻擊怪每回合固定那招。
- 目標選擇 `pick_player_side_target`:約 55% 打玩家、其餘平分同伴;玩家立盾牆嘲諷則強制鎖坦。
- 不逃跑、不自我治療、不自我增益、不召喚 —— 純攻擊。

**② 命中附效**(打中玩家時):**元素**(無視物理護甲,吃元素抗性;火/冰/電另吃 magic 抗、毒/血不吃)· **DoT**(回合末扣血,玩家側同元素疊加上限 3)· **控場**(stagger/fear 等,經 R44 `magic.apply_control`)· **感染**(吸血鬼/狼人咬擊機率傳染,疾病抗性削減)。

**③ 玩家防禦雙軌**(R43/R44):① 閃過/格擋(落空 → 連傷帶控全免)· ② 命中後 fear/paralyze 再吃意志(willpower)抵抗。被恐懼/麻痺的怪自己也跳過回合。

**④ 生成**(R11/R12):群體規模隨 danger(d≥5 最多 4、d3 最多 3);**SOLO 首領永遠單獨**;生態加權(對應 biome ×3、他鄉 ×0.25、無標籤=通用池);地城首領 `spawn_boss` 套 ×1.6 HP / ×1.3 傷 / +15 命中 / +6 甲(`raw` 首領跳過)。

**⑤ SOLO 首領**:單獨出現 · fear/paralyze 機率減免(R44,~65% 抵抗)· 偷襲/衝鋒單擊受 `SOLO_SNEAK_DAMAGE_CAP_RATIO` 夾(打不出秒殺)。

**⑥ 屬性用途**:力量→傷害 · 敏捷→命中/閃避 · 速度→先攻 · armor_rating→物理減傷 · max_health 生成時 ×0.85~1.15 抖動。
"""


def main():
    order = sorted(BEAST.items(),
                   key=lambda kv: (kv[1].get("danger", 1), kv[1].get("min_level", 0), -kv[1].get("max_health", 0)))
    total = len(BEAST)
    dist = {}
    for v in BEAST.values():
        dist[v.get("danger", 1)] = dist.get(v.get("danger", 1), 0) + 1
    with_rep = [k for k, v in BEAST.items() if v.get("attacks")]
    no_rep = [(k, v) for k, v in order if not v.get("attacks")]
    solo = [k for k, v in BEAST.items() if v.get("solo")]

    out = [HEADER]
    out.append("## 總覽\n")
    out.append(f"- **{total} 隻怪** · danger 分布:" + " · ".join(f"d{d}×{dist[d]}" for d in sorted(dist)))
    out.append(f"- 野外可隨機遭遇 {sum(1 for v in BEAST.values() if v.get('weight', 1) > 0)} 隻 · "
               f"腳本/任務/召喚專屬 {sum(1 for v in BEAST.values() if v.get('weight', 1) == 0)} 隻")
    out.append(f"- 多攻擊曲目(R43){len(with_rep)} 隻 · 單一攻擊 {total - len(with_rep)} 隻 · "
               f"SOLO 首領 {len(solo)} 隻 · 人形(可囚黑魂){sum(1 for v in BEAST.values() if v.get('sentient'))} 隻 · "
               f"不死(聖光剋之){sum(1 for v in BEAST.values() if v.get('undead'))} 隻\n")
    out.append(BEHAVIOR)

    # 缺曲目名單
    out.append(f"## 缺攻擊曲目的 {len(no_rep)} 隻怪(R43 多樣化候選)\n")
    out.append("> 這些怪仍是「每回合同一招」。R43 多攻擊模式可優先補在高 danger / 招牌怪上(加物理/元素交替、蓄力、控場)。\n")
    bd = {}
    for k, v in no_rep:
        bd.setdefault(v.get("danger", 1), []).append(f"{v['name']}(`{k}`)")
    for d in sorted(bd):
        out.append(f"- **d{d}**({len(bd[d])}):" + " · ".join(bd[d]))
    out.append("")

    # 完整 roster
    out.append("## 完整 roster(依 danger)\n")
    cur = None
    for k, v in order:
        d = v.get("danger", 1)
        if d != cur:
            cur = d
            out.append(f"\n### ■ DANGER {d}\n")
        rep = "✦曲目" if v.get("attacks") else ""
        out.append(f"#### {v['name']} `{k}` {rep}")
        out.append(f"- danger {d} · L{v.get('min_level')} · HP {v.get('max_health')} · 甲 {v.get('armor_rating')} · "
                   f"力{v['strength']}/敏{v['agility']}/速{v['speed']} · @{biome(v)} {flags(k, v)}".rstrip())
        if v.get("attacks"):
            out.append(f"- 曲目（{len(v['attacks'])} 模式）:")
            for a in v["attacks"]:
                out.append(f"    - {atk_line(a)}")
        else:
            out.append(f"- 攻擊:{atk_line(v['attack'])}")
        if v.get("resist"):
            out.append(f"- {resist_line(v['resist'])}")
        out.append(f"- 掉落:{loot_line(v)}")
        out.append("")

    text = "\n".join(out) + "\n"
    with open(os.path.join(ROOT, "BESTIARY.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(f"BESTIARY.md 已生成:{total} 隻怪、{len(no_rep)} 隻缺曲目、{len(solo)} 隻 SOLO。")


if __name__ == "__main__":
    main()
