#!/usr/bin/env python3
"""依正典上古卷軸地理重建 world.json 的 pos 座標 + links 連線(查 UESP/ESO 地理而得)。

- 每省的城市相對位置(fx,fy ∈0..1,N=0/W=0)由 lore 研究確定 → 換算成各省 bounding box 內的格座標。
- 省內連線 = lore 道路鄰接(各省主城為樞紐);跨省連線只經邊境節點(真實 Tamriel 省界)。
- 旅行時數由格距離推導(相鄰短、邊境隘長)。保留其餘欄位(name/biome/type/danger/desc/services/stock/dungeon)。
"""
import json
import math

PATH = "tesrpg/data/world.json"
COLS, ROWS = 40, 24
BOX = {  # 行省地理框(N=上)
    "天際": (19, 38, 0, 6), "高岩": (1, 15, 1, 7), "漢默法爾": (1, 13, 9, 16),
    "賽羅迪爾": (16, 28, 8, 14), "晨風": (31, 39, 7, 14), "瓦倫森林": (4, 15, 17, 23),
    "艾爾斯維爾": (17, 28, 17, 23), "黑沼澤": (30, 39, 16, 23),
}
# 省內:{id: (fx, fy, [鄰居])} —— UESP lore 研究結果
GEO = {
 "賽羅迪爾": {
  "imperial_city": (0.5,0.45,["bruma","chorrol","skingrad","cheydinhal","bravil","imperial_road"]),
  "bruma": (0.5,0.08,["imperial_city","chorrol","cheydinhal"]),
  "chorrol": (0.2,0.22,["imperial_city","bruma","skingrad","great_forest_trail"]),
  "skingrad": (0.28,0.55,["imperial_city","chorrol","kvatch","bravil"]),
  "kvatch": (0.15,0.62,["skingrad","anvil","dawn_sanctum","kvatch_gate"]),
  "anvil": (0.05,0.72,["kvatch"]),
  "cheydinhal": (0.78,0.25,["imperial_city","bruma","dagon_shrine"]),
  "bravil": (0.55,0.72,["imperial_city","skingrad","leyawiin","bravil_gate"]),
  "leyawiin": (0.62,0.95,["bravil"]),
  "imperial_road": (0.5,0.52,["imperial_city","vilverin","fort_ontus","cedernoc_cave"]),
  "cedernoc_cave": (0.38,0.4,["imperial_road","chorrol"]),
  "fort_ontus": (0.32,0.35,["imperial_road","chorrol"]),
  "vilverin": (0.58,0.48,["imperial_road","imperial_city"]),
  "great_forest_trail": (0.22,0.32,["chorrol"]),
  "kvatch_gate": (0.13,0.66,["kvatch"]),
  "bravil_gate": (0.57,0.78,["bravil"]),
  "dagon_shrine": (0.85,0.2,["cheydinhal","the_deadlands"]),
  "the_deadlands": (0.92,0.15,["dagon_shrine"]),
  "dawn_sanctum": (0.1,0.55,["kvatch"]),
 },
 "天際": {
  "solitude": (0.12,0.1,["haafingar","dragon_bridge","morthal"]),
  "haafingar": (0.08,0.08,["solitude"]),
  "dragon_bridge": (0.15,0.18,["solitude","markarth","morthal"]),
  "morthal": (0.32,0.22,["solitude","dragon_bridge","whiterun","dawnstar"]),
  "dawnstar": (0.5,0.1,["morthal","winterhold","whiterun","the_pale_tundra"]),
  "winterhold": (0.78,0.12,["dawnstar","windhelm","saarthal"]),
  "windhelm": (0.78,0.4,["winterhold","whiterun","riften","eastmarch_springs"]),
  "riften": (0.82,0.82,["windhelm","whiterun","lostknife_cave"]),
  "whiterun": (0.45,0.45,["morthal","dawnstar","windhelm","riften","falkreath_wood","markarth"]),
  "markarth": (0.08,0.55,["whiterun","dragon_bridge","falkreath_wood","forsworn_redoubt"]),
  "falkreath_wood": (0.38,0.85,["whiterun","markarth","frostwind_ruin"]),
  "frostwind_ruin": (0.42,0.92,["falkreath_wood"]),
  "lostknife_cave": (0.88,0.88,["riften"]),
  "saarthal": (0.72,0.18,["winterhold"]),
  "forsworn_redoubt": (0.05,0.62,["markarth"]),
  "eastmarch_springs": (0.7,0.45,["windhelm"]),
  "the_pale_tundra": (0.52,0.18,["dawnstar"]),
 },
 "晨風": {
  "blacklight": (0.05,0.20,["gnisis","balmora"]),
  "gnisis": (0.20,0.22,["blacklight","ald_ruhn","balmora"]),
  "balmora": (0.28,0.58,["gnisis","blacklight","vivec","ald_ruhn","ghostgate"]),
  "ald_ruhn": (0.45,0.40,["gnisis","balmora","ghostgate","kogoruhn","ashland_waste","molag_mar"]),
  "vivec": (0.40,0.85,["balmora","molag_mar"]),
  "molag_mar": (0.68,0.72,["vivec","ald_ruhn","sadrith_mora","ashland_waste"]),
  "sadrith_mora": (0.92,0.45,["molag_mar","ashland_waste"]),
  "ghostgate": (0.50,0.50,["ald_ruhn","balmora","red_mountain_slope","kogoruhn"]),
  "red_mountain_slope": (0.52,0.44,["ghostgate","dragon_lair","ashland_waste"]),
  "dragon_lair": (0.58,0.38,["red_mountain_slope","ashland_waste"]),
  "ashland_waste": (0.55,0.30,["ald_ruhn","kogoruhn","red_mountain_slope","dragon_lair","molag_mar","sadrith_mora","ashfall_barrow"]),
  "kogoruhn": (0.48,0.28,["ald_ruhn","ghostgate","ashland_waste","ashfall_barrow"]),
  "ashfall_barrow": (0.42,0.22,["kogoruhn","ashland_waste"]),
 },
 "黑沼澤": {
  "gideon": (0.12,0.22,["stormhold","helstrom"]),
  "stormhold": (0.42,0.12,["gideon","helstrom","archon"]),
  "helstrom": (0.45,0.48,["gideon","stormhold","blackrose","archon","xanmeer","hist_grove","argonian_fens"]),
  "archon": (0.72,0.42,["stormhold","helstrom","blackrose","thorn","vunnar_xul"]),
  "blackrose": (0.62,0.70,["helstrom","archon","thorn","murkmire"]),
  "thorn": (0.78,0.82,["blackrose","archon","murkmire"]),
  "murkmire": (0.60,0.90,["blackrose","thorn","rootwater_grotto"]),
  "hist_grove": (0.38,0.40,["helstrom","argonian_fens"]),
  "xanmeer": (0.52,0.55,["helstrom","vunnar_xul"]),
  "rootwater_grotto": (0.50,0.92,["murkmire"]),
  "vunnar_xul": (0.66,0.52,["archon","xanmeer"]),
  "argonian_fens": (0.30,0.55,["helstrom","hist_grove"]),
 },
 "高岩": {
  "daggerfall": (0.10,0.72,["glenumbra_moors","camlorn","wendir","direnni_tower"]),
  "glenumbra_moors": (0.06,0.55,["daggerfall","camlorn"]),
  "camlorn": (0.14,0.40,["daggerfall","glenumbra_moors","wendir","northpoint"]),
  "wendir": (0.22,0.48,["daggerfall","camlorn","hag_rock"]),
  "hag_rock": (0.40,0.50,["wendir","wayrest","northpoint"]),
  "direnni_tower": (0.40,0.78,["daggerfall","wayrest"]),
  "wayrest": (0.55,0.70,["direnni_tower","hag_rock","northpoint","evermore"]),
  "northpoint": (0.50,0.12,["camlorn","hag_rock","wayrest","orsinium"]),
  "orsinium": (0.78,0.40,["northpoint","wrothgar_moor","jehanna","evermore"]),
  "wrothgar_moor": (0.88,0.35,["orsinium","jehanna"]),
  "jehanna": (0.90,0.18,["orsinium","wrothgar_moor"]),
  "evermore": (0.72,0.72,["wayrest","orsinium"]),
 },
 "漢默法爾": {
  "sentinel": (0.42,0.15,["alikr_desert","tava_oasis","lainlyn","dragontail_peaks"]),
  "tava_oasis": (0.45,0.40,["sentinel","alikr_desert","ansei_tomb"]),
  "alikr_desert": (0.40,0.45,["sentinel","tava_oasis","volenfell","ansei_tomb","lainlyn"]),
  "volenfell": (0.30,0.50,["alikr_desert","rourken_halls","lainlyn"]),
  "rourken_halls": (0.25,0.55,["volenfell","lainlyn"]),
  "ansei_tomb": (0.50,0.55,["tava_oasis","alikr_desert","taneth","dragontail_peaks"]),
  "lainlyn": (0.18,0.45,["sentinel","alikr_desert","volenfell","rourken_halls","hegathe"]),
  "hegathe": (0.12,0.78,["lainlyn","gilane"]),
  "gilane": (0.30,0.82,["hegathe","taneth"]),
  "taneth": (0.48,0.85,["gilane","ansei_tomb","rihad"]),
  "rihad": (0.72,0.80,["taneth","dragontail_peaks"]),
  "dragontail_peaks": (0.80,0.45,["sentinel","ansei_tomb","rihad"]),
 },
 "瓦倫森林": {
  "falinesti": (0.50,0.45,["falinesti_roots","graht_forest","elden_root","silvenar","woodhearth","greenshade"]),
  "haven": (0.72,0.80,["elden_root","spider_grove"]),
  "woodhearth": (0.08,0.55,["greenshade","falinesti"]),
  "elden_root": (0.60,0.65,["falinesti","graht_forest","haven","silvenar","vindisi"]),
  "arenthia": (0.55,0.06,["silvenar"]),
  "silvenar": (0.62,0.32,["falinesti","elden_root","arenthia","vinedusk_reach"]),
  "vinedusk_reach": (0.88,0.38,["silvenar","spider_grove"]),
  "graht_forest": (0.45,0.58,["falinesti","elden_root","greenshade","vindisi"]),
  "spider_grove": (0.78,0.62,["vinedusk_reach","haven"]),
  "falinesti_roots": (0.48,0.42,["falinesti"]),
  "vindisi": (0.55,0.78,["graht_forest","elden_root"]),
  "greenshade": (0.20,0.70,["woodhearth","falinesti","graht_forest"]),
 },
 "艾爾斯維爾": {
  "rimmen": (0.82,0.14,["riverhold","corinthe","northern_woods"]),
  "senchal": (0.80,0.95,["alabaster_cane","tenmar_forest"]),
  "torval": (0.18,0.72,["tenmar_forest","corinthe","moonlit_cradle"]),
  "dune": (0.14,0.22,["riverhold","corinthe","northern_woods"]),
  "riverhold": (0.50,0.08,["dune","rimmen","corinthe","northern_woods"]),
  "corinthe": (0.48,0.48,["dune","riverhold","rimmen","torval","tenmar_forest","merryvale_ruin","dark_moon_grotto"]),
  "alabaster_cane": (0.92,0.82,["senchal","tenmar_forest"]),
  "tenmar_forest": (0.55,0.75,["torval","corinthe","senchal","alabaster_cane","moonlit_cradle"]),
  "dark_moon_grotto": (0.62,0.30,["corinthe","rimmen"]),
  "moonlit_cradle": (0.30,0.62,["torval","tenmar_forest"]),
  "merryvale_ruin": (0.35,0.40,["corinthe","dune"]),
  "northern_woods": (0.42,0.04,["riverhold","dune","rimmen"]),
 },
}
# 邊境節點 = 真實 Tamriel 省界接縫:每個連到兩省的門戶城 + 同隘的戍堡/地城
BORDER_LINKS = {
  "pale_pass": ["bruma","falkreath_wood","pale_garrison","pale_pass_cave"],
  "pale_garrison": ["pale_pass","dragon_bridge","brena_valley","pale_pass_cave"],
  "pale_pass_cave": ["pale_pass","pale_garrison"],
  "sea_route": ["windhelm","blacklight"],
  "niben_marsh": ["leyawiin","bravil","gideon","topal_bay"],
  "thorn_fen": ["molag_mar","stormhold"],
  "dragontail_foothills": ["anvil","kvatch","dragontail_peaks"],
  "brena_valley": ["markarth","dragontail_peaks","pale_garrison"],
  "bangkorai_pass": ["evermore","sentinel","bangkorai_hold","bangkorai_crypt"],
  "bangkorai_hold": ["bangkorai_pass","evermore","sentinel","bangkorai_crypt"],
  "bangkorai_crypt": ["bangkorai_pass","bangkorai_hold"],
  "karthwasten": ["jehanna","markarth"],
  "strid_vale": ["anvil","arenthia","strident_crossing"],
  "strident_crossing": ["strid_vale","leyawiin","topal_bay"],
  "abecean_coast": ["hegathe","woodhearth","cliffhaven_watch"],
  "cliffhaven_watch": ["abecean_coast","woodhearth","gilane"],
  "topal_bay": ["niben_marsh","leyawiin","rimmen","riverhold","strident_crossing"],
  "pellitine_marches": ["vinedusk_reach","torval","corinthe"],
}
DEAD_END_OK = {"kvatch_gate", "bravil_gate", "the_deadlands", "dawn_sanctum"}

d = json.load(open(PATH, encoding="utf-8"))
L = d["locations"]

# --- 座標:fx,fy → box 格座標,全域唯一 ---------------------------------
pos = {}
used = set()
def claim(c, r):
    c = max(0, min(COLS-1, int(round(c)))); r = max(0, min(ROWS-1, int(round(r))))
    if (c, r) not in used:
        used.add((c, r)); return [c, r]
    for rad in range(1, max(COLS, ROWS)):
        for dc in range(-rad, rad+1):
            for dr in range(-rad, rad+1):
                nc, nr = c+dc, r+dr
                if 0 <= nc < COLS and 0 <= nr < ROWS and (nc, nr) not in used:
                    used.add((nc, nr)); return [nc, nr]
    raise SystemExit("格用罄")
for prov, items in GEO.items():
    cmin, cmax, rmin, rmax = BOX[prov]
    for lid, (fx, fy, _) in items.items():
        pos[lid] = claim(cmin + fx*(cmax-cmin), rmin + fy*(rmax-rmin))

# --- links:省內 lore 鄰接 ---------------------------------------------
def dist(a, b):
    return math.hypot(pos[a][0]-pos[b][0], pos[a][1]-pos[b][1])
def hrs(a, b):
    return max(1, min(9, round(dist(a, b)/1.6)))
links = {lid: {} for lid in L}
for prov, items in GEO.items():
    for lid, (_, _, nbrs) in items.items():
        for n in nbrs:
            links[lid][n] = hrs(lid, n); links[n][lid] = hrs(lid, n)

# --- 邊境節點:落鄰居(已放)平均;連線 = BORDER_LINKS ------------------
border = [lid for lid, loc in L.items() if loc["province"] == "邊境"]
for _ in range(4):
    for lid in border:
        if lid in pos:
            continue
        ng = [pos[t] for t in BORDER_LINKS.get(lid, []) if t in pos]
        if ng:
            pos[lid] = claim(sum(p[0] for p in ng)/len(ng), sum(p[1] for p in ng)/len(ng))
for lid in border:
    pos.setdefault(lid, claim(COLS//2, ROWS//2))
for lid in border:
    for n in BORDER_LINKS.get(lid, []):
        links[lid][n] = hrs(lid, n); links[n][lid] = hrs(lid, n)

# --- 自動補:degree<2 的非盲腸 → 連到最近的合格節點 ---------------------
def nearest(lid):
    cand = [(dist(lid, o), o) for o in pos
            if o != lid and o not in links[lid]
            and (L[o]["province"] == L[lid]["province"] or L[o]["province"] == "邊境" or L[lid]["province"] == "邊境")]
    return min(cand)[1] if cand else None
for lid in L:
    if lid in DEAD_END_OK:
        continue
    while len(links[lid]) < 2:
        n = nearest(lid)
        if not n:
            break
        links[lid][n] = hrs(lid, n); links[n][lid] = hrs(lid, n)

# --- 檢查:連通 + 無跨省直連 -------------------------------------------
start = d["start_location"]; seen = {start}; fr = [start]
while fr:
    cur = fr.pop()
    for x in links[cur]:
        if x not in seen: seen.add(x); fr.append(x)
miss = set(L) - seen
if miss:
    raise SystemExit(f"不連通:{miss}")
cross = []
for lid in L:
    for n in links[lid]:
        pa, pb = L[lid]["province"], L[n]["province"]
        if pa != pb and pa != "邊境" and pb != "邊境":
            cross.append((lid, n))
assert not cross, f"跨省直連:{cross}"

# --- 重發 world.json(locations 單行,保留其餘欄位)---------------------
FIELD = ["biome", "name", "province", "pos", "type", "danger", "desc",
         "services", "merchant_stock", "spell_stock", "dungeon", "links"]
def emit(lid):
    e = dict(L[lid]); e["pos"] = pos[lid]; e["links"] = links[lid]
    o = {k: e[k] for k in FIELD if k in e} | {k: v for k, v in e.items() if k not in FIELD}
    return '    "%s": %s' % (lid, json.dumps(o, ensure_ascii=False, separators=(", ", ": ")))
body = ",\n".join(emit(lid) for lid in L)
text = ('{\n  "locations": {\n' + body + "\n  },\n"
        + '  "map": ' + json.dumps(d["map"], ensure_ascii=False)
        + ',\n  "start_location": ' + json.dumps(d["start_location"], ensure_ascii=False) + "\n}\n")
d2 = json.loads(text)
assert len(d2["locations"]) == len(L)
open(PATH, "w", encoding="utf-8").write(text)
# 報告
deg1 = [lid for lid in L if len(links[lid]) < 2]
print(f"✓ 地理重建:{len(L)} 地點;連通✓ 無跨省直連✓;degree<2(應只剩盲腸)= {deg1}")
import collections
print("各省連線數:", dict(collections.Counter(L[a]["province"] for a in L for _ in links[a])))
