"""拠点から、よく行く先への運賃をまとめて用意する。

全路線を貯め込むのは無理がある。都内の駅だけで組み合わせは50万通りあり、
運賃改定のたびに古くなる（JR東日本は 2026-03-14 に改定）。

要るのは「今いる拠点から、自分が実際に行く先」だけ。
行き先は予定から拾う。カレンダーに出てくる場所が、その人の行動範囲そのものなので。

拾いきれない分に備えて、乗り換えに使う大きい駅も少しだけ足す。
ここは駅の名前を並べただけで、運賃は持っていない。
"""
import datetime as dt

from . import calendars, itinerary, profile as prof_mod

# 遠出の時に必ず通る所。運賃は持たない（名前だけ）
HUBS = ["東京", "新宿", "品川", "横浜", "名古屋", "新大阪", "大阪", "京都",
        "三ノ宮", "博多", "仙台", "札幌", "広島", "金沢", "静岡", "岡山"]
SCAN_DAYS = 120


def seen_stations(prof: dict, days=SCAN_DAYS) -> list:
    """予定に出てくる場所のうち、駅に結びついた分。新しい順。"""
    places = prof_mod.load_places()
    stations = prof_mod.load_stations()
    start = dt.date.today() - dt.timedelta(days=days // 2)
    by_day, _w = calendars.events_for_range(prof, start, days)
    out = []
    for key in sorted(by_day, reverse=True):
        for e in by_day[key]:
            kind, st, _why = itinerary.classify(e, places, stations)
            if kind == "onsite" and st and st not in out:
                out.append(st)
    return out


def _priced(prof: dict):
    """もう額が入っている組み合わせ。"""
    fares = prof_mod.load_fares().get("fares", [])
    st = prof_mod.load_stations().get("stations", {})
    name = {k: (v.get("name") or k).rstrip("駅") for k, v in st.items()}
    got = set()
    for r in fares:
        if r.get("amount"):
            got.add((name.get(r["from"], r["from"]), name.get(r["to"], r["to"])))
    return got


def pending(prof: dict = None, limit=20, with_hubs=True):
    """今いる拠点から、まだ額の無い区間。往復ぶん。"""
    prof = prof or prof_mod.load()
    tr = prof.get("travel") or {}
    base = (tr.get("bases") or {}).get(tr.get("currentBase") or "") or {}
    home = (base.get("station") or "").strip()
    if not home:
        return {"base": "", "pairs": [], "note": "拠点の駅が空です（道順3）"}
    dests = [d for d in seen_stations(prof) if d != home]
    if with_hubs:
        for h in HUBS:
            if h != home and h not in dests:
                dests.append(h)
    have = _priced(prof)
    pairs = []
    for d in dests:
        for a, b in ((home, d), (d, home)):
            if (a, b) not in have and (a, b) not in pairs:
                pairs.append((a, b))
        if len(pairs) >= limit * 2:
            break
    return {"base": base.get("label") or home, "home": home,
            "pairs": pairs[:limit * 2], "note": ""}
