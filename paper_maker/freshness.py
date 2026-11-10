"""運賃の鮮度。いつ確かめた額なのかを見る。

運賃は変わる。変わったこと自体は防げないので、**古いことが分かる**ようにする。
確かめた日が改定日より前なら、その額は改定前のもの。

改定日はここに足していく。利用者が自分で足せるよう ~/.paper-maker/fare_revisions.json も見る。
"""
import datetime as dt
import json

from . import paths, profile as prof_mod

# 分かっている改定日。増えたらここに足す（利用者側でも足せる）
REVISIONS = [
    {"date": "2026-03-14", "who": "JR東日本", "note": "運賃改定"},
    {"date": "2025-04-01", "who": "各社", "note": "消費税・バリアフリー料金などの改定が集中する時期"},
]

STALE_DAYS = 365


def revisions():
    p = paths.data_dir() / "fare_revisions.json"
    extra = []
    if p.exists():
        try:
            extra = json.loads(p.read_text(encoding="utf-8")).get("revisions", [])
        except ValueError:
            extra = []
    return sorted(REVISIONS + extra, key=lambda r: r["date"], reverse=True)


def _d(s):
    try:
        y, m, d = (int(x) for x in str(s).split("-")[:3])
        return dt.date(y, m, d)
    except (ValueError, TypeError):
        return None


def check(today: dt.date = None):
    """実額として使っている行を見て、怪しい物を返す。"""
    today = today or dt.date.today()
    revs = [(r, _d(r["date"])) for r in revisions()]
    revs = [(r, d) for r, d in revs if d and d <= today]
    stations = prof_mod.load_stations().get("stations", {})
    name = {k: v.get("name", k) for k, v in stations.items()}
    old, unknown = [], []
    for r in prof_mod.load_fares().get("fares", []):
        if r.get("amount") is None or not r.get("verified"):
            continue
        checked = _d(r.get("checkedAt"))
        row = {"id": r.get("id"), "from": name.get(r["from"], r["from"]),
               "to": name.get(r["to"], r["to"]), "amount": r["amount"],
               "checkedAt": r.get("checkedAt") or "", "source": r.get("source", "")}
        if not checked:
            unknown.append(row)
            continue
        hit = next((rv for rv, d in revs if checked < d), None)
        if hit:
            row["why"] = "%s の%s（%s）より前に確かめた額" % (hit["date"], hit["note"], hit["who"])
            old.append(row)
        elif (today - checked).days >= STALE_DAYS:
            row["why"] = "確かめてから %d 日たっている" % (today - checked).days
            old.append(row)
    return {"old": old, "unknown": unknown,
            "total": sum(1 for r in prof_mod.load_fares().get("fares", [])
                         if r.get("amount") is not None and r.get("verified"))}


def mark(itin_legs, today: dt.date = None):
    """行程の各区間に、鮮度の注意を付ける。書類の備考へ出すため。"""
    res = check(today)
    bad = {(x["from"], x["to"]): x["why"] for x in res["old"]}
    for l in itin_legs:
        w = bad.get((l.get("from"), l.get("to"))) or bad.get((l.get("to"), l.get("from")))
        if w and l.get("amount") is not None:
            l["stale"] = w
    return itin_legs
