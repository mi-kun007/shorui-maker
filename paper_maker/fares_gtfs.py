"""バスの運賃を、公開データ（GTFS-JP）から取ってくる。

出どころは GTFSデータリポジトリ（api.gtfs-data.jp）。鍵も登録も要らない。
2026-08-19 時点で 548 フィード・407 事業体。ほとんど CC BY 4.0。

**コードは取り込まない。数字だけ取る。** 運賃の額は事業者が公表している事実で、
zip の中の fare_attributes.txt（額）と fare_rules.txt（どの区間か）を読んで、
停留所どうしの運賃に直して自分の表へ入れる。ライセンス表記は出所に残す。
"""
import csv
import io
import json
import urllib.parse
import urllib.request
import zipfile

FILES_URL = "https://api.gtfs-data.jp/v2/files"

PREF = {
    1: "北海道", 2: "青森", 3: "岩手", 4: "宮城", 5: "秋田", 6: "山形", 7: "福島",
    8: "茨城", 9: "栃木", 10: "群馬", 11: "埼玉", 12: "千葉", 13: "東京", 14: "神奈川",
    15: "新潟", 16: "富山", 17: "石川", 18: "福井", 19: "山梨", 20: "長野", 21: "岐阜",
    22: "静岡", 23: "愛知", 24: "三重", 25: "滋賀", 26: "京都", 27: "大阪", 28: "兵庫",
    29: "奈良", 30: "和歌山", 31: "鳥取", 32: "島根", 33: "岡山", 34: "広島", 35: "山口",
    36: "徳島", 37: "香川", 38: "愛媛", 39: "高知", 40: "福岡", 41: "佐賀", 42: "長崎",
    43: "熊本", 44: "大分", 45: "宮崎", 46: "鹿児島", 47: "沖縄",
}
PREF_ID = {v: k for k, v in PREF.items()}


def _get(url, timeout=90):
    """このサーバーは identity を頼んでも gzip で返してくることがある。中身で判断して開く。"""
    req = urllib.request.Request(url, headers={"User-Agent": "paper-maker"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or data[:2] == b"\x1f\x8b":
        import gzip
        data = gzip.decompress(data)
    return data


def feeds():
    """公開されているフィードの一覧。"""
    d = json.loads(_get(FILES_URL).decode("utf-8"))
    rows = d.get("body", d) if isinstance(d, dict) else d
    out = []
    for r in rows:
        out.append({
            "org": r.get("organization_name", ""),
            "feed": r.get("feed_name", ""),
            "pref_id": r.get("feed_pref_id"),
            "pref": PREF.get(r.get("feed_pref_id"), ""),
            "license": r.get("feed_license_id", ""),
            "url": r.get("file_url", ""),
            "updated": (r.get("file_last_updated_at") or "")[:10],
        })
    return out


def search(rows, pref="", word=""):
    def ok(r):
        if pref and r["pref"] != pref.replace("県", "").replace("府", "").replace("都", ""):
            return False
        if word and word not in (r["org"] + r["feed"]):
            return False
        return True
    return [r for r in rows if ok(r)]


def read_feed(url, timeout=120):
    """1つのフィードから、停留所どうしの運賃を取り出す。

    fare_rules の origin_id / destination_id は stops.txt の zone_id を指す。
    zone を停留所名に直してから組み立てる。
    """
    z = zipfile.ZipFile(io.BytesIO(_get(url, timeout)))
    names = z.namelist()
    if "fare_attributes.txt" not in names or "fare_rules.txt" not in names:
        return [], "運賃の表が入っていません"

    def rd(n):
        return list(csv.DictReader(z.read(n).decode("utf-8-sig").splitlines()))

    zone_name = {}
    for s in rd("stops.txt"):
        zid = (s.get("zone_id") or "").strip()
        nm = (s.get("stop_name") or "").strip()
        if zid and nm:
            zone_name.setdefault(zid, nm)
    price = {}
    for f in rd("fare_attributes.txt"):
        try:
            price[f["fare_id"]] = int(float(f["price"]))
        except (KeyError, ValueError):
            continue

    pairs, seen = [], set()
    for r in rd("fare_rules.txt"):
        o, d = (r.get("origin_id") or "").strip(), (r.get("destination_id") or "").strip()
        amt = price.get(r.get("fare_id"))
        if not o or not d or amt is None:
            continue
        a, b = zone_name.get(o), zone_name.get(d)
        if not a or not b or a == b:
            continue
        key = (a, b)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"from": a, "to": b, "amount": amt})
    return pairs, ""


def pick(pairs, stops=None, limit=0):
    """全部は要らない。使う停留所に関わる分だけ残す。

    stops を渡すと、その名前を含む区間だけにする。渡さなければ全部（limit で頭打ち）。
    """
    if stops:
        keys = [s for s in stops if s]
        pairs = [p for p in pairs if any(k in p["from"] or k in p["to"] for k in keys)]
    if limit:
        pairs = pairs[:limit]
    return pairs


def apply(pairs, org, license_id, prof_mod, itinerary):
    """自分の運賃表へ入れる。出どころとライセンスを必ず残す（CC BY は表示が条件）。"""
    import datetime as dt
    stations = prof_mod.load_stations()
    fares = prof_mod.load_fares()
    st = stations.setdefault("stations", {})
    rows = fares.setdefault("fares", [])
    today = dt.date.today().isoformat()

    def sid(nm):
        for k, v in st.items():
            if itinerary.norm(v.get("name", "")) == itinerary.norm(nm):
                return k
        k = "s%d" % (len(st) + 1)
        while k in st:
            k += "x"
        st[k] = {"name": nm, "kind": "bus", "pref": ""}
        return k

    src = "%s の公開データ（GTFS / %s）" % (org, license_id or "ライセンス表記なし")
    n = 0
    for p in pairs:
        a, b = sid(p["from"]), sid(p["to"])
        rows[:] = [r for r in rows if not (r.get("from") == a and r.get("to") == b)]
        rows.append({"id": "%s_%s" % (a, b), "from": a, "to": b, "transport": "バス", "line": "",
                     "amount": p["amount"], "verified": True, "source": src, "checkedAt": today})
        n += 1
    prof_mod.save_stations(stations)
    prof_mod.save_fares(fares)
    return n
