#!/usr/bin/env python3
"""產生 tools/expansion.json(Tier B 全境補完內容)。所有 item/monster/spell/race/bloc id
皆取自既有資料,確保有效。links 只寫單向(expand_world.py 補反向);pos 由 expand_world 指派。"""
import json

PROV_BIOME = {"天際": "snow", "晨風": "ashland", "高岩": "moor", "漢默法爾": "desert",
              "瓦倫森林": "jungle", "艾爾斯維爾": "savanna", "黑沼澤": "swamp",
              "賽羅迪爾": "heartland", "邊境": "snow"}

CITY_SVC = ["inn", "merchant", "trainer", "armorer", "task_board"]
MAGE_SVC = ["inn", "merchant", "trainer", "armorer", "mages_guild", "task_board"]
TOWN_SVC = ["inn", "merchant", "task_board"]
STOCK_LOW = ["minor_healing_potion", "healing_potion", "iron_sword", "iron_dagger",
             "leather_cuirass", "iron_shield", "hunting_bow", "repair_hammer", "ruby", "silver_ring"]
STOCK_MID = ["minor_healing_potion", "healing_potion", "minor_magicka_potion", "steel_sword",
             "steel_cuirass", "steel_shield", "steel_helmet", "elven_sword", "long_bow",
             "repair_hammer", "ruby", "gold_ring", "silver_amulet"]
MAGE_STOCK = STOCK_MID + ["frost_staff", "flame_staff", "magicka_staff"]
MAGE_SPELLS = ["flames", "sparks", "frostbite", "minor_heal", "heal", "oakflesh",
               "ward", "fear", "soul_trap", "conjure_familiar"]

# 地城分級模板:danger -> (grid, layers, loot_locked)
DPARAM = {1: (4, 2, [8, 14]), 2: (4, 2, [12, 18]), 3: (4, 2, [18, 27]),
          4: (5, 3, [24, 36]), 5: (5, 3, [40, 52])}
DLOOT = {
    1: (["minor_healing_potion", "leather_cuirass", "iron_dagger"],
        ["steel_sword", "healing_potion", {"gold": [20, 40]}]),
    2: (["minor_healing_potion", "healing_potion", "iron_cuirass", "ruby"],
        ["steel_sword", "healing_potion", "ruby", {"gold": [30, 60]}]),
    3: (["healing_potion", "steel_sword", "steel_shield", "ruby"],
        ["elven_sword", "healing_potion", "filled_common_soul_gem", {"gold": [60, 120]}]),
    4: (["healing_potion", "elven_sword", "glass_dagger", "ruby", "filled_common_soul_gem"],
        ["glass_cuirass", "filled_greater_soul_gem", "gold_ring", {"gold": [120, 240]}]),
    5: (["healing_potion", "glass_dagger", "dwarven_cuirass", "ruby", "filled_greater_soul_gem"],
        ["ebony_sword", "dragon_scale", "filled_greater_soul_gem", {"gold": [200, 400]}]),
}

# (id, 名, 省, mage?, ruler(name,title,race,gar,pop,bloc,bloc_label,stance,blurb), links{})
CITIES = [
    # 天際
    ("solitude", "獨孤城", "天際", False, ("艾莉希芙", "領主", "nord", 230, 480, "imperial_legion", "帝國軍團", "imperial", "天際西北的帝國首府,白塔臨海,風帆雲集。"), {"haafingar": 2, "dragon_bridge": 2}),
    ("dawnstar", "晨星城", "天際", False, ("斯科爾", "領主", "nord", 150, 300, "stormcloak", "風暴斗篷", "independent", "蒼原北岸的採礦港城,寒風裡礦燈終夜不熄。"), {"windhelm": 3}),
    ("morthal", "墨索爾", "天際", False, ("伊德格羅德", "領主", "nord", 110, 220, "hjaalmarch_hold", "霜境領", "neutral", "霜境沼澤邊的靜謐小城,霧氣常年不散。"), {"haafingar": 3, "whiterun": 3}),
    ("winterhold", "冬堡", "天際", True, ("科拉尼", "領主", "nord", 120, 240, "college_winterhold", "冬堡學院", "neutral", "崩塌懸崖上的學院之城,通往泰姆瑞爾最古老的魔法殿堂。"), {"windhelm": 3}),
    # 晨風
    ("sadrith_mora", "薩瑞斯·莫拉", "晨風", True, ("奈洛斯·泰爾凡尼", "法師領主", "dunmer", 160, 320, "house_telvanni", "泰爾凡尼家族", "independent", "東境蕈島上的泰爾凡尼法師港,巨蕈高塔直插灰燼長空。"), {"vivec": 4, "molag_mar": 3}),
    ("gnisis", "格尼希斯", "晨風", False, ("瑟洛斯·薩倫", "執政", "dunmer", 120, 240, "house_redoran", "雷多然家族", "neutral", "薩姆希河畔的雷多然礦鎮,神殿與礦坑相依。"), {"ald_ruhn": 3, "blacklight": 4}),
    # 高岩
    ("orsinium", "奧西尼姆", "高岩", False, ("古洛·gro-巴格洛", "酋長王", "orsimer", 200, 360, "orsinium_kingdom", "奧西尼姆王國", "independent", "沃斯加山中的獸人要塞之都,黑鐵與榮譽的王國。"), {"wrothgar_moor": 2, "evermore": 3}),
    ("northpoint", "北角", "高岩", False, ("提歐多", "伯爵", "breton", 150, 320, "northpoint_county", "北角伯爵領", "neutral", "高岩北岸的布萊頓港郡,商船與石塔林立。"), {"wayrest": 3, "daggerfall": 4}),
    ("jehanna", "耶漢納", "高岩", False, ("艾蕾諾", "女王", "breton", 160, 340, "jehanna_crown", "耶漢納王廷", "neutral", "沃斯加東緣的古老王城,終年覆雪的王廷。"), {"wayrest": 3, "evermore": 3}),
    # 漢默法爾
    ("taneth", "塔尼斯", "漢默法爾", False, ("阿莎芙·萊菈", "總督", "redguard", 160, 320, "forebears", "先鋒派", "neutral", "漢默法爾南方的先鋒派大城,香料與彎刀貿易的樞紐。"), {"hegathe": 3, "gilane": 2}),
    ("lainlyn", "蘭林", "漢默法爾", False, ("法拉斯", "領主", "redguard", 130, 260, "forebears", "先鋒派", "independent", "西岸的先鋒派商港,以駿馬與長弓聞名。"), {"sentinel": 3, "gilane": 3}),
    ("rihad", "里哈德", "漢默法爾", False, ("塔茲菈", "城主", "redguard", 140, 280, "crowns", "王冠派", "imperial", "漢默法爾與賽羅迪爾交界的南方港城,互市繁盛。"), {"gilane": 3, "abecean_coast": 3}),
    # 瓦倫森林
    ("elden_root", "艾爾登根", "瓦倫森林", False, ("卡米蘭", "樹冠王", "bosmer", 180, 360, "camoran_dynasty", "卡莫蘭王朝", "independent", "巨橡樹冠上的多明尼昂之都,綠約之民的王座。"), {"falinesti": 2, "graht_forest": 3}),
    ("arenthia", "阿倫西亞", "瓦倫森林", False, ("茵蒂爾", "守邊使", "bosmer", 120, 240, "green_pact_voice", "綠約之聲", "neutral", "北境與艾爾斯維爾接壤的邊城,獸人與貓人混居。"), {"falinesti": 3, "silvenar": 3}),
    ("woodhearth", "木心港", "瓦倫森林", False, ("瑟蘭", "港主", "bosmer", 130, 270, "haven_port", "海文商港", "imperial", "西海岸的森林港埠,帝國商船的南方據點。"), {"haven": 3}),
    # 艾爾斯維爾
    ("dune", "杜恩", "艾爾斯維爾", False, ("莎拉巴爾", "商隊長", "khajiit", 150, 300, "anequina_clans", "安納奎那戰族", "independent", "安納奎那旱原的商隊大城,黃沙與月糖的集散地。"), {"rimmen": 3, "tenmar_forest": 3}),
    ("riverhold", "河關", "艾爾斯維爾", False, ("瑪佐", "市長", "khajiit", 120, 250, "anequina_clans", "安納奎那戰族", "neutral", "賽羅迪爾邊境的北方關城,香料商旅的門戶。"), {"rimmen": 3}),
    ("corinthe", "科林斯", "艾爾斯維爾", False, ("達羅", "糖閥", "khajiit", 130, 270, "pellitine_growers", "佩萊泰恩糖閥", "neutral", "佩萊泰恩雨林邊的貿易城,月糖種植園環繞。"), {"senchal": 3, "torval": 3}),
    # 黑沼澤
    ("archon", "阿爾孔", "黑沼澤", False, ("維克斯-埃", "樹語長", "argonian", 140, 280, "an_xileel", "An-Xileel 議會", "independent", "黑沼澤腹地的亞龍人城邦,希斯特古樹環抱。"), {"helstrom": 3, "murkmire": 3}),
    ("thorn", "索恩", "黑沼澤", False, ("吉爾-希斯", "部族長", "argonian", 120, 240, "hist_speakers", "希斯特樹語", "independent", "深澤中的部族之城,終年瘴霧繚繞。"), {"blackrose": 3, "hist_grove": 3}),
]

# 邊境戍堡(皆 border_garrison/neutral)
BORDER_TOWNS = [
    ("pale_garrison", "白隘戍堡", ("瓦倫修斯", "戍將", "imperial", 120, 200, "border_garrison", "鎮隘戍卒", "neutral", "扼守賽羅迪爾與天際山道的帝國戍堡。"), {"pale_pass": 1, "dragon_bridge": 2, "brena_valley": 2}),
    ("bangkorai_hold", "巴薩拉守關", ("達羅·gro-沙茲", "戍將", "redguard", 120, 210, "border_garrison", "鎮隘戍卒", "neutral", "高岩與漢默法爾交界的山口要塞。"), {"bangkorai_pass": 1, "evermore": 3, "hegathe": 3}),
    ("strident_crossing", "斯特里德渡口", ("芮娜", "關長", "imperial", 100, 190, "border_garrison", "鎮隘戍卒", "neutral", "賽羅迪爾通往瓦倫森林與艾爾斯維爾的河津貿易站。"), {"strid_vale": 1, "anvil": 3, "topal_bay": 2}),
    ("cliffhaven_watch", "崖港哨堡", ("敏多", "哨官", "bosmer", 90, 180, "border_garrison", "鎮隘戍卒", "neutral", "阿貝森海岸的瞭望哨堡,連接瓦倫與漢默法爾的航路。"), {"abecean_coast": 1, "haven": 3, "gilane": 4}),
]

# (id, 名, 省, danger, monsters, boss_enemy, raw, links, desc)
DUNGEONS = [
    ("saarthal", "薩爾薩斯", "天際", 4, ["draugr", "skeleton", "frostbite_spider"], "barrow_sentinel", True, {"winterhold": 2, "windhelm": 4}, "冬堡之下最古老的諾德古塚,亡者守著上古之物。"),
    ("forsworn_redoubt", "拒誓者巢穴", "天際", 3, ["bandit", "skeleton", "moor_witch"], "moor_witch", False, {"markarth": 2, "karthwasten": 2}, "河灣地崖壁上的拒誓者要塞,女巫與叛民盤踞。"),
    ("ghostgate", "幽魂之門", "晨風", 5, ["dremora", "daedric_champion", "ash_hopper", "storm_atronach"], "daedroth", True, {"ald_ruhn": 3, "dragon_lair": 3}, "環繞紅山的幽魂結界堡壘,魔族自烈焰中湧出。"),
    ("kogoruhn", "科戈魯恩", "晨風", 3, ["ash_hopper", "skeleton", "dwarven_spider"], "draugr", False, {"ald_ruhn": 2, "ashland_waste": 2}, "灰燼荒原下的丹莫先祖遺城,沉睡著家族的亡魂。"),
    ("direnni_tower", "戴尼瑞塔", "高岩", 4, ["gargoyle", "harpy", "skeleton", "reclusive_mage"], "lich", True, {"daggerfall": 3, "hag_rock": 3}, "巴爾菲拉島上的上古精靈高塔,巫術氣息千年不散。"),
    ("wendir", "溫迪爾", "高岩", 3, ["gargoyle", "harpy", "skeleton"], "gargoyle", False, {"camlorn": 3, "jehanna": 2}, "格雷努布拉森林裡的艾雷德遺跡,石像鬼盤踞。"),
    ("rourken_halls", "羅肯廳堂", "漢默法爾", 3, ["dwarven_spider", "sand_scorpion", "skeleton"], "dwarven_spider", False, {"alikr_desert": 2, "volenfell": 3}, "阿利克沙漠深處的矮人氏族遺城,黃銅機關仍在低鳴。"),
    ("ansei_tomb", "劍聖之墓", "漢默法爾", 5, ["skeleton", "barrow_sentinel", "draugr", "vampire_lord"], "lich", True, {"alikr_desert": 3, "dragontail_peaks": 2}, "約凱劍聖長眠的沙下墓城,守墓亡靈仍持彎刀。"),
    ("falinesti_roots", "法林斯提根穴", "瓦倫森林", 3, ["spriggan", "giant_spider", "jungle_imga"], "spriggan", False, {"falinesti": 2, "graht_forest": 2}, "行走之城的巨根穴洞,樹靈與巨蛛交織其間。"),
    ("vindisi", "文迪西", "瓦倫森林", 4, ["spriggan", "giant_spider", "strangler_vine", "lamia"], "spriggan_matriarch", True, {"haven": 3, "spider_grove": 3}, "叢林深處的艾雷德神廟廢墟,藤蔓與獸靈守護。"),
    ("moonlit_cradle", "月華搖籃", "艾爾斯維爾", 3, ["sugar_addled_senche", "alfiq_sorcerer", "skeleton"], "senche_tiger", False, {"tenmar_forest": 2, "torval": 3}, "騰瑪森林裡的貓人月之神殿地窖。"),
    ("merryvale_ruin", "梅里谷遺址", "艾爾斯維爾", 4, ["alfiq_sorcerer", "sugar_vine", "dro_mathra_shade"], "dark_moon_senche", True, {"senchal": 3, "dark_moon_grotto": 3}, "佩萊泰恩雨林中的暗月教殘址,月糖瘴影瀰漫。"),
    ("rootwater_grotto", "根水沼窟", "黑沼澤", 3, ["swamp_lizard", "marsh_zombie", "will_o_wisp"], "marsh_zombie", False, {"murkmire": 2, "gideon": 3}, "泥沼之下的希斯特水窟,腐臭與磷火交雜。"),
    ("vunnar_xul", "凡納·蘇爾沉廟", "黑沼澤", 5, ["swamp_lizard", "will_o_wisp", "bog_troll", "wamasu"], "wamasu", True, {"xanmeer": 3, "argonian_fens": 2}, "深澤底的贊密爾沉沒巨廟,雷蜥盤踞於積水神殿。"),
    ("fort_ontus", "奧圖斯堡", "賽羅迪爾", 2, ["bandit", "skeleton", "giant_rat"], "bandit", False, {"chorrol": 2, "great_forest_trail": 2}, "大森林裡半傾的艾雷德古堡,如今淪為盜匪窩。"),
    ("vilverin", "維爾凡林", "賽羅迪爾", 2, ["skeleton", "imperial_ghost", "giant_rat"], "skeleton", False, {"imperial_city": 2, "imperial_road": 3}, "尼本灣畔最知名的艾雷德地穴遺跡。"),
    ("pale_pass_cave", "白隘冰窟", "邊境", 1, ["wolf", "giant_rat", "frostbite_spider"], "wolf", False, {"pale_pass": 1, "pale_garrison": 2}, "白隘山道旁的緩坡冰窟,新手練膽的去處。"),
    ("bangkorai_crypt", "巴薩拉墓窖", "邊境", 3, ["skeleton", "gargoyle", "draugr"], "gargoyle", False, {"bangkorai_pass": 2, "bangkorai_hold": 2}, "巴薩拉守關下的古老墓窖,守關陣亡者長眠於此。"),
]

# (id, 名, 省, danger, links, desc)
WILDS = [
    ("eastmarch_springs", "東陲溫泉", "天際", 2, {"windhelm": 2, "dawnstar": 2}, "東陲火山地熱的硫磺溫泉荒野。"),
    ("the_pale_tundra", "蒼原凍原", "天際", 2, {"solitude": 3, "dawnstar": 2, "frostwind_ruin": 3}, "蒼原一望無際的霜雪凍原。"),
    ("red_mountain_slope", "紅山坡道", "晨風", 3, {"ald_ruhn": 2, "sadrith_mora": 3, "ghostgate": 2}, "通往紅山的灰燼坡道,風暴與火光交織。"),
    ("glenumbra_moors", "格雷努布拉荒沼", "高岩", 2, {"daggerfall": 2, "camlorn": 2}, "高岩西陲霧氣瀰漫的石南荒沼。"),
    ("dragontail_peaks", "龍尾峰", "漢默法爾", 3, {"taneth": 3, "dragontail_foothills": 3}, "龍尾山脈的乾燥高峰,沙鷹盤旋。"),
    ("greenshade", "綠影林", "瓦倫森林", 3, {"elden_root": 3, "woodhearth": 3}, "瓦倫西南終年蒼翠的密林。"),
    ("northern_woods", "北境林莽", "艾爾斯維爾", 2, {"riverhold": 2, "rimmen": 3}, "艾爾斯維爾北境的疏林草莽。"),
    ("argonian_fens", "亞龍沼澤", "黑沼澤", 3, {"archon": 3, "stormhold": 3}, "黑沼澤腹地縱橫的亞龍人澤地。"),
    ("great_forest_trail", "大森林小徑", "賽羅迪爾", 1, {"chorrol": 2, "imperial_road": 2}, "賽羅迪爾大森林裡平緩的林間小徑。"),
]

locations, rulers, dungeons, quests = {}, {}, {}, {}

def city(cid, name, prov, mage, ruler, links, town=False, border=False):
    biome = PROV_BIOME[prov]
    svc = TOWN_SVC if (town or border) else (MAGE_SVC if mage else CITY_SVC)
    stock = STOCK_LOW if (town or border) else (MAGE_STOCK if mage else STOCK_MID)
    e = {"biome": biome, "name": name, "province": prov, "type": "town" if (town or border) else "city",
         "danger": 0, "desc": ruler[8], "services": svc, "merchant_stock": stock, "links": dict(links)}
    if mage:
        e["spell_stock"] = MAGE_SPELLS
    locations[cid] = e
    nm, title, race, gar, pop, bloc, label, stance, blurb = ruler
    rulers[cid] = {"name": nm, "title": title, "race": race, "garrison": gar, "population": pop,
                   "bloc": bloc, "bloc_label": label, "blurb": blurb, "stance": stance}

for cid, name, prov, mage, ruler, links in CITIES:
    city(cid, name, prov, mage, ruler, links)
for cid, name, ruler, links in BORDER_TOWNS:
    city(cid, name, "邊境", False, ruler, links, border=True)

for did, name, prov, dgr, mons, boss, raw, links, desc in DUNGEONS:
    locations[did] = {"biome": PROV_BIOME[prov], "name": name, "province": prov, "type": "dungeon",
                      "danger": dgr, "desc": desc, "services": [], "dungeon": did, "links": dict(links)}
    grid, layers, locked = DPARAM[dgr]
    loot, treasure = DLOOT[dgr]
    bossobj = {"enemy": boss, "desc": f"{name}最深處的首領 —— {desc}", "treasure": {"loot": treasure}}
    if raw:
        bossobj = {"enemy": boss, "raw": True, "desc": bossobj["desc"], "treasure": {"loot": treasure}}
    dungeons[did] = {"name": name, "biome": PROV_BIOME[prov], "danger": dgr, "grid": grid,
                     "layers": layers, "monsters": mons, "loot": list(loot),
                     "loot_locked": locked, "boss": bossobj}
    rg = {1: (120, 6), 2: (180, 8), 3: (240, 12), 4: (360, 18), 5: (480, 24)}[dgr]
    quests[f"job_{did}"] = {"name": f"委託:{name}", "faction": None, "rank": None, "source": "board",
                            "provinces": [prov], "objective": {"type": "clear_dungeon", "dungeon": did},
                            "reward": {"gold": rg[0], "fame": rg[1]}, "turn_in": "auto",
                            "text": f"委託:肅清{name}。"}

for wid, name, prov, dgr, links, desc in WILDS:
    locations[wid] = {"biome": PROV_BIOME[prov], "name": name, "province": prov, "type": "wilderness",
                      "danger": dgr, "desc": desc, "services": [], "links": dict(links)}

out = {"locations": locations, "rulers": rulers, "dungeons": dungeons, "quests": quests}
json.dump(out, open("tools/expansion.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"locations={len(locations)} rulers={len(rulers)} dungeons={len(dungeons)} quests={len(quests)}")
print("cities/towns:", sum(1 for l in locations.values() if l['type'] in ('city', 'town')),
      " dungeons:", sum(1 for l in locations.values() if l['type'] == 'dungeon'),
      " wild:", sum(1 for l in locations.values() if l['type'] == 'wilderness'))
