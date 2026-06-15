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
  "forsworn_redoubt": (0.05,0.62,["markarth","karth_river"]),
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
# 各 seam 經正典審查:每個邊境節點只接它真正鄰接的兩省門戶城(+同隘戍堡/地城)
BORDER_LINKS = {
  # 賽↔天 = 白隘(布魯瑪—白隘—海爾根—佛克瑞斯);戍堡守 Cyrodiil 側,海爾根是天際門戶
  "pale_pass": ["bruma","pale_garrison","helgen","pale_pass_cave"],
  "pale_garrison": ["pale_pass","pale_pass_cave","bruma"],
  "pale_pass_cave": ["pale_pass","pale_garrison"],
  "sea_route": ["windhelm","blacklight"],            # 天↔晨 = 鄧梅斯隘/海路(風盔—黑光)
  "niben_marsh": ["leyawiin","gideon","topal_bay"],  # 賽↔黑 = 黑木(雷雅維因—吉迪恩)
  "thorn_fen": ["molag_mar","stormhold"],            # 晨↔黑(莫拉格瑪—石落)
  "dragontail_foothills": ["anvil","kvatch","dragontail_peaks"],  # 賽↔漢(西岸—龍尾)
  "brena_valley": ["markarth","dragontail_peaks"],   # 天Reach↔漢(馬卡斯—龍尾)
  "bangkorai_pass": ["evermore","sentinel","bangkorai_hold","bangkorai_crypt"],  # 高↔漢
  "bangkorai_hold": ["bangkorai_pass","evermore","sentinel","bangkorai_crypt"],
  "bangkorai_crypt": ["bangkorai_pass","bangkorai_hold"],
  "karthwasten": ["jehanna","markarth"],             # 高↔天 Reach(耶漢納—馬卡斯)
  "strid_vale": ["anvil","strident_crossing"],       # 賽↔瓦 = 斯特里德河(安維爾側)
  "strident_crossing": ["strid_vale","arenthia"],    # 渡口(瓦倫·阿倫西亞側)
  "abecean_coast": ["hegathe","woodhearth","cliffhaven_watch"],  # 漢↔瓦 阿比西亞海路
  "cliffhaven_watch": ["abecean_coast","woodhearth","gilane"],
  "topal_bay": ["niben_marsh","leyawiin","rimmen","riverhold"],  # 賽↔艾 托帕爾灣
  "pellitine_marches": ["vinedusk_reach","torval","corinthe"],   # 瓦↔艾 收割者三月
}
DEAD_END_OK = {"kvatch_gate", "bravil_gate", "the_deadlands", "dawn_sanctum"}
PROV_BIOME = {"天際": "snow", "晨風": "ashland", "高岩": "moor", "漢默法爾": "desert",
              "賽羅迪爾": "heartland", "瓦倫森林": "jungle", "艾爾斯維爾": "savanna", "黑沼澤": "swamp"}
# 正典分區野區(地點補全):(id, 省, 名, danger, (城A,城B), desc)。
# 位置=兩城中點(略偏移),並把 A↔B 直連改走此野區(過場)。城A、城B 必為該省 GEO 既有直連。
NEW_REGIONS = [
 # 賽羅迪爾
 ("gold_coast", "賽羅迪爾", "黃金海岸", 2, ("anvil", "kvatch"), "安維爾與凱瓦奇之間的金色海岸,陽光、沙灘與海盜的傳說。"),
 ("colovian_highlands", "賽羅迪爾", "科洛溫高地", 2, ("chorrol", "skingrad"), "科洛溫西境起伏的高地牧野,風吹草低見牛羊。"),
 ("nibenay_basin", "賽羅迪爾", "尼本盆地", 1, ("imperial_city", "bravil"), "尼本河中游肥沃的盆地,稻田與商船往來不絕。"),
 ("blackwood", "賽羅迪爾", "黑木邊地", 3, ("bravil", "leyawiin"), "賽羅迪爾東南潮濕的黑木林,通往黑沼澤的瘴氣邊地。"),
 ("jerall_mountains", "賽羅迪爾", "傑拉山脈", 3, ("bruma", "cheydinhal"), "賽羅迪爾北境的傑拉雪山,隔開天際的險峻屏障。"),
 # 天際
 ("hjaalmarch_marsh", "天際", "霜境沼澤", 2, ("solitude", "morthal"), "獨孤城與墨索爾之間的霧沼,泥炭與鬼火明滅。"),
 ("whiterun_tundra", "天際", "白漫凍原", 1, ("whiterun", "falkreath_wood"), "白漫城外遼闊的凍原草甸,巨人與猛獁漫步。"),
 ("rift_autumn", "天際", "裂谷秋林", 2, ("whiterun", "riften"), "裂谷領金黃的秋色林地,蜜酒與漁獲之鄉。"),
 ("velothi_foothills", "天際", "維洛希山麓", 3, ("windhelm", "winterhold"), "東陲通往冬堡的維洛希山麓,寒風刺骨。"),
 ("karth_river", "天際", "卡斯河谷", 2, ("markarth", "dragon_bridge"), "卡斯河切穿河灣地的深谷,拒誓者出沒。"),
 # 晨風
 ("bitter_coast", "晨風", "苦岸", 2, ("balmora", "vivec"), "瓦登費爾西南的沼澤苦岸,走私者的天堂。"),
 ("west_gash", "晨風", "西峽", 2, ("gnisis", "ald_ruhn"), "瓦登費爾西部的灌木荒原與紅岩。"),
 ("ascadian_isles", "晨風", "阿斯卡迪安島", 1, ("vivec", "molag_mar"), "維威克南方肥沃的阿斯卡迪安島,菇農與莊園。"),
 ("azuras_coast", "晨風", "亞祖拉海岸", 3, ("molag_mar", "sadrith_mora"), "瓦登費爾東岸的礁岩海濱,遠古祭壇林立。"),
 ("grazelands", "晨風", "草場", 3, ("ald_ruhn", "molag_mar"), "瓦登費爾東北的草場,阿胥蘭部族的牧地。"),
 # 黑沼澤
 ("shadowfen", "黑沼澤", "影沼", 2, ("gideon", "stormhold"), "黑沼澤北境的影沼,亞龍人最古老的聚居地。"),
 ("thornmarsh", "黑沼澤", "荊棘澤", 3, ("blackrose", "thorn"), "黑沼澤東南密布荊棘的澤地,毒蟲遍野。"),
 ("deep_hist", "黑沼澤", "深希斯特", 3, ("helstrom", "archon"), "腹地希斯特古樹的深處,迷霧終年不散。"),
 ("onkobra_river", "黑沼澤", "翁科布拉河", 2, ("blackrose", "murkmire"), "翁科布拉河蜿蜒的下游濕地,鱷與雷蜥潛伏。"),
 ("stormhold_fen", "黑沼澤", "石落澤", 2, ("stormhold", "helstrom"), "石落城周邊低窪的沼澤,腐木與磷火。"),
 # 高岩
 ("stormhaven", "高岩", "風暴港原野", 1, ("wayrest", "hag_rock"), "威岩周邊富庶的風暴港原野,麥田與石橋。"),
 ("rivenspire", "高岩", "裂石郡", 3, ("northpoint", "hag_rock"), "高岩北境裂石郡的險峻峭壁,吸血鬼的傳說之地。"),
 ("bangkorai_foothills", "高岩", "巴薩拉丘陵", 2, ("wayrest", "evermore"), "通往巴薩拉隘的南方丘陵,荊豆遍野。"),
 ("daenia_forest", "高岩", "戴尼亞林", 2, ("camlorn", "wendir"), "高岩西部戴尼亞的茂密森林。"),
 ("wrothgarian_mountains", "高岩", "沃斯加山脈", 3, ("orsinium", "jehanna"), "高岩東境險峻的沃斯加山脈,獸人的故土。"),
 # 漢默法爾
 ("bangkorai_valley", "漢默法爾", "巴薩拉谷", 2, ("sentinel", "dragontail_peaks"), "漢默法爾東北通往巴薩拉的河谷。"),
 ("hews_bane", "漢默法爾", "休氏灣", 2, ("hegathe", "gilane"), "漢默法爾西南的休氏灣半島,盜賊行會的暗巢。"),
 ("craglorn", "漢默法爾", "克雷格倫", 4, ("tava_oasis", "ansei_tomb"), "阿利克爾東部的克雷格倫荒地,星隕與巨人為患。"),
 ("abecean_shore", "漢默法爾", "阿比西亞岸", 2, ("gilane", "taneth"), "漢默法爾南方溫暖的阿比西亞海岸。"),
 ("dragontail_range", "漢默法爾", "龍尾山域", 3, ("rihad", "dragontail_peaks"), "龍尾山脈的東段,通往賽羅迪爾的崎嶇山道。"),
 # 瓦倫森林
 ("grahtwood", "瓦倫森林", "格拉特林地", 2, ("falinesti", "elden_root"), "艾爾登根周邊的格拉特巨木林地,綠約之心。"),
 ("malabal_tor", "瓦倫森林", "馬拉巴爾陶", 3, ("falinesti", "silvenar"), "瓦倫中部馬拉巴爾陶的狂野叢林。"),
 ("greenshade_coast", "瓦倫森林", "綠影海岸", 2, ("woodhearth", "greenshade"), "綠影西岸的紅樹林海岸。"),
 ("reapers_march", "瓦倫森林", "收割者三月", 3, ("silvenar", "vinedusk_reach"), "瓦倫與艾爾斯維爾交界的收割者三月。"),
 ("tarlain_heights", "瓦倫森林", "塔爾蘭高地", 2, ("elden_root", "haven"), "格拉特林東南的塔爾蘭高地。"),
 # 艾爾斯維爾
 ("anequina_plains", "艾爾斯維爾", "安納奎那旱原", 2, ("dune", "riverhold"), "艾爾斯維爾北方安納奎那的乾旱草原。"),
 ("pellitine_jungle", "艾爾斯維爾", "佩萊泰恩雨林", 3, ("torval", "tenmar_forest"), "南艾爾斯維爾佩萊泰恩濕熱的雨林。"),
 ("quinrawl_peninsula", "艾爾斯維爾", "昆拉沃半島", 3, ("senchal", "alabaster_cane"), "森查爾所在的昆拉沃半島,海盜與月糖。"),
 ("tenmar_valley", "艾爾斯維爾", "騰瑪谷", 2, ("corinthe", "tenmar_forest"), "騰瑪森林邊緣靜謐的河谷。"),
 ("rimmen_desert", "艾爾斯維爾", "瑞門荒漠", 2, ("rimmen", "corinthe"), "瑞門城外的東部荒漠,殘存阿卡維爾遺風。"),
]

d = json.load(open(PATH, encoding="utf-8"))
L = d["locations"]

# --- 注入正典分區野區:中點(略偏移)定位,A↔B 改走此野區 ----------------
for rid, prov, name, dgr, (a, b), desc in NEW_REGIONS:
    ga, gb = GEO[prov][a], GEO[prov][b]
    mx, my = (ga[0] + gb[0]) / 2, (ga[1] + gb[1]) / 2
    dx, dy = gb[0] - ga[0], gb[1] - ga[1]
    pl = math.hypot(dx, dy) or 1.0
    fx = min(0.97, max(0.03, mx - dy / pl * 0.10))
    fy = min(0.97, max(0.03, my + dx / pl * 0.10))
    if b in ga[2]:
        ga[2].remove(b)
    if a in gb[2]:
        gb[2].remove(a)
    GEO[prov][rid] = (fx, fy, [a, b])
    L[rid] = {"biome": PROV_BIOME[prov], "name": name, "province": prov,
              "type": "wilderness", "danger": dgr, "desc": desc, "services": []}

# --- 新增海爾根(天際南緣、白隘北口的佛克瑞斯小鎮 —— 賽→天門戶)----------
if "helgen" not in L:
    L["helgen"] = {"biome": "snow", "name": "海爾根", "province": "天際", "type": "town",
                   "danger": 0, "desc": "佛克瑞斯領南端、白隘北口的小鎮 —— 從賽羅迪爾進入天際的門戶。",
                   "services": ["inn", "merchant", "task_board"],
                   "merchant_stock": ["minor_healing_potion", "healing_potion", "iron_sword",
                                      "leather_cuirass", "iron_shield", "hunting_bow", "repair_hammer", "ruby"]}
GEO["天際"]["helgen"] = (0.36, 0.94, ["falkreath_wood", "whiterun"])

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

# --- 自動補:degree<2 的非盲腸 → 連到「最近的同省」節點(杜絕跨 seam 亂湊)---
autofix_added = []
def nearest(lid):
    pv = L[lid]["province"]
    cand = [(dist(lid, o), o) for o in pos
            if o != lid and o not in links[lid] and L[o]["province"] == pv]
    return min(cand)[1] if cand else None
for lid in L:
    if lid in DEAD_END_OK:
        continue
    while len(links[lid]) < 2:
        n = nearest(lid)
        if not n:
            break
        links[lid][n] = hrs(lid, n); links[n][lid] = hrs(lid, n)
        autofix_added.append(f"{lid}->{n}")

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

# --- 海爾根城主(town 需 ruler)寫進 rulers.json ------------------------
RP = "tesrpg/data/rulers.json"
rt = open(RP, encoding="utf-8").read()
if '"helgen"' not in rt:
    ruler = {"name": "督軍 哈鄔丁", "title": "督軍", "race": "nord", "garrison": 90, "population": 150,
             "bloc": "imperial_legion", "bloc_label": "帝國軍團",
             "blurb": "海爾根的帝國督軍,扼守白隘北口、天際的南方門戶。", "stance": "imperial"}
    before, c, after = rt.rpartition("\n}")
    rt = before + ',\n  "helgen": ' + json.dumps(ruler, ensure_ascii=False, separators=(", ", ": ")) + "\n}" + after
    json.loads(rt)
    open(RP, "w", encoding="utf-8").write(rt)
    print("✓ 已新增 rulers.json: helgen")

# 報告
deg1 = [lid for lid in L if len(links[lid]) < 2]
print(f"✓ 地理重建:{len(L)} 地點;連通✓ 無跨省直連✓;degree<2(應只剩盲腸)= {deg1}")
print(f"auto-fix 補的同省連線({len(autofix_added)}):", autofix_added)
import collections
print("各省連線數:", dict(collections.Counter(L[a]["province"] for a in L for _ in links[a])))
