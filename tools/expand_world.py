#!/usr/bin/env python3
"""一次性開發工具:把 tools/expansion.json 的新內容併入 data/{world,rulers,dungeons,quests}.json。

- 保留既有檔案格式(只「新增條目」與「為取得反向連線而改動的既有節點」會變動)。
- 新條目以單行 compact JSON 追加(與 world.json 既有 oblivion 條目同風格)。
- 自動補雙向 links(新↔新 互補;新↔舊 → 重寫該舊節點為單行並補上反向 link)。
- 自動指派 pos(真實行省落各自 bounding box 空格;邊境節點落鄰居座標平均)。
- 寫回後 json.loads 驗證 + 雙向/連通自檢。

expansion.json 結構:
{ "locations": { id: {province,type,biome,danger,desc,services,merchant_stock?,spell_stock?,dungeon?,links:{id:hours}} },
  "rulers":    { id: {...ruler entry...} },
  "dungeons":  { id: {...dungeon entry...} },
  "quests":    { id: {...quest entry...} } }
locations 不需帶 pos(本工具指派)。links 只需單向寫(本工具補反向)。
"""
import json
import math
import sys

DATA = "tesrpg/data"
COLS, ROWS = 40, 24
BOX = {
    "天際": (19, 38, 0, 6), "高岩": (1, 15, 1, 7), "漢默法爾": (1, 13, 9, 16),
    "賽羅迪爾": (16, 28, 8, 14), "晨風": (31, 39, 7, 14), "瓦倫森林": (4, 15, 17, 23),
    "艾爾斯維爾": (17, 28, 17, 23), "黑沼澤": (30, 39, 16, 23),
}


def load(f):
    return json.load(open(f"{DATA}/{f}.json", encoding="utf-8"))


def read_text(f):
    return open(f"{DATA}/{f}.json", encoding="utf-8").read()


def write_text(f, t):
    open(f"{DATA}/{f}.json", "w", encoding="utf-8").write(t)


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))


def find_span(text, key, indent):
    """回傳 text 中 `<indent>"key": {...}` 整個條目的 (start,end) 字元索引(含 key,不含尾逗號)。
    以括號計數 + 字串感知掃描,正確處理巢狀。找不到回 None。"""
    anchor = f'{indent}"{key}": {{'
    i = text.find(anchor)
    if i < 0:
        return None
    j = i + len(anchor) - 1          # 指向開頭的 '{'
    depth = 0
    in_str = False
    esc = False
    while j < len(text):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return (i, j + 1)
        j += 1
    raise RuntimeError(f"未找到 {key} 的對應右括號")


def insert_before_close(text, entries_text, *, kind):
    """把 entries_text(已含縮排、彼此以逗號分隔、無尾逗號)插入物件結尾前。
    kind='locations':插在 locations 物件閉合 `\n  },` 前(其後是 "map");
    kind='top':插在頂層物件閉合 `\n}` 前。"""
    if kind == "locations":
        head, sep, tail = text.partition('\n  "map": {')
        assert sep, "world.json 找不到 map 鍵"
        before, c, _ = head.rpartition("\n  },")
        assert c, "找不到 locations 閉合"
        return before + ",\n" + entries_text + "\n  }," + sep + tail
    else:
        before, c, after = text.rpartition("\n}")
        assert c, "找不到頂層閉合"
        return before + ",\n" + entries_text + "\n}" + after


def main():
    exp = json.load(open("tools/expansion.json", encoding="utf-8"))
    world = load("world")
    locs = world["locations"]
    new_locs = exp.get("locations", {})

    # 0) 基本檢查:新 id 不得撞既有
    for nid in new_locs:
        if nid in locs:
            sys.exit(f"新地點 id 撞既有:{nid}")

    # 1) 雙向 links:新↔新 互補;新↔舊 收集反向
    reverse = {}      # existing_id -> {new_id: hours}
    for nid, e in new_locs.items():
        for tgt, h in list(e.get("links", {}).items()):
            if tgt in new_locs:
                new_locs[tgt].setdefault("links", {}).setdefault(nid, h)
            elif tgt in locs:
                reverse.setdefault(tgt, {})[nid] = h
            else:
                sys.exit(f"{nid} 連到不存在的 {tgt}")

    # 2) 指派 pos
    used = {tuple(l["pos"]) for l in locs.values()}

    def claim(c, r):
        c = max(0, min(COLS - 1, c)); r = max(0, min(ROWS - 1, r))
        if (c, r) not in used:
            used.add((c, r)); return [c, r]
        for rad in range(1, max(COLS, ROWS)):
            for dc in range(-rad, rad + 1):
                for dr in range(-rad, rad + 1):
                    nc, nr = c + dc, r + dr
                    if 0 <= nc < COLS and 0 <= nr < ROWS and (nc, nr) not in used:
                        used.add((nc, nr)); return [nc, nr]
        sys.exit("座標格用罄")

    # 真實行省:在 box 內找與既有同省節點分散開的空格(以 box 中心螺旋外擴)
    realm = [nid for nid, e in new_locs.items() if e["province"] in BOX]
    border = [nid for nid, e in new_locs.items() if e["province"] == "邊境"]
    for nid in realm:
        cmin, cmax, rmin, rmax = BOX[new_locs[nid]["province"]]
        cc = (cmin + cmax) // 2; rr = (rmin + rmax) // 2
        new_locs[nid]["pos"] = claim(cc, rr)
    # 邊境:鄰居座標平均(多趟涵蓋 border-border)
    placed = {nid: new_locs[nid]["pos"] for nid in realm}
    def nbpos(nid):
        out = []
        for t in new_locs[nid].get("links", {}):
            if t in locs: out.append(locs[t]["pos"])
            elif t in placed: out.append(placed[t])
        return out
    for _ in range(4):
        for nid in border:
            if nid in placed: continue
            ng = nbpos(nid)
            if ng:
                c = round(sum(p[0] for p in ng) / len(ng)); r = round(sum(p[1] for p in ng) / len(ng))
                new_locs[nid]["pos"] = claim(c, r); placed[nid] = new_locs[nid]["pos"]
    for nid in border:
        if nid not in placed:
            new_locs[nid]["pos"] = claim(COLS // 2, ROWS // 2); placed[nid] = new_locs[nid]["pos"]

    # 3) 重組 world.json 文字:先改既有節點(補反向 link),再追加新節點
    wt = read_text("world")
    FIELD_ORDER = ["biome", "name", "province", "pos", "type", "danger", "desc",
                   "services", "merchant_stock", "spell_stock", "dungeon", "links"]
    def order_entry(d):
        return {k: d[k] for k in FIELD_ORDER if k in d} | {k: v for k, v in d.items() if k not in FIELD_ORDER}

    for eid, addlinks in reverse.items():
        span = find_span(wt, eid, "    ")
        if not span:
            sys.exit(f"找不到既有節點 {eid} 以補反向 link")
        obj = json.loads(wt[span[0]:span[1]].split(":", 1)[1].strip())
        obj.setdefault("links", {}).update(addlinks)
        wt = wt[:span[0]] + f'    "{eid}": ' + compact(order_entry(obj)) + wt[span[1]:]

    new_entries = ",\n".join(f'    "{nid}": ' + compact(order_entry(new_locs[nid]))
                             for nid in new_locs)
    if new_entries:
        wt = insert_before_close(wt, new_entries, kind="locations")
    json.loads(wt)  # 驗證
    write_text("world", wt)

    # 4) rulers / dungeons / quests:純追加
    for fname, key in (("rulers", "rulers"), ("dungeons", "dungeons"), ("quests", "quests")):
        items = exp.get(key, {})
        if not items:
            continue
        ft = read_text(fname)
        existing = load(fname)
        for k in items:
            if k in existing:
                sys.exit(f"{fname}: 新 id 撞既有 {k}")
        block = ",\n".join(f'  "{k}": ' + compact(v) for k, v in items.items())
        ft = insert_before_close(ft, block, kind="top")
        json.loads(ft)
        write_text(fname, ft)

    # 5) 自檢:雙向 + 連通
    w2 = load("world"); L = w2["locations"]
    for lid, loc in L.items():
        for dest in loc.get("links", {}):
            assert dest in L, f"{lid} 連到不存在 {dest}"
            assert lid in L[dest].get("links", {}), f"{lid}->{dest} 非雙向"
    start = w2["start_location"]; seen = {start}; fr = [start]
    while fr:
        cur = fr.pop()
        for d in L[cur].get("links", {}):
            if d not in seen: seen.add(d); fr.append(d)
    assert seen == set(L), f"不連通:{set(L) - seen}"
    print(f"✓ 併入 {len(new_locs)} 地點 / {len(exp.get('rulers',{}))} 城主 / "
          f"{len(exp.get('dungeons',{}))} 地城 / {len(exp.get('quests',{}))} 任務;雙向+連通 OK;共 {len(L)} 地點")


if __name__ == "__main__":
    main()
