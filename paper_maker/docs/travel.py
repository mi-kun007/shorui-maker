"""出張報告・精算書。行程（itinerary）から app/index.html の travel 型 JSON を組む。PDF 化は app 経由。"""
import datetime as dt


def _expense_row(leg, day_iso):
    """運賃が未登録の区間は 0円 で計上しない。

    0円のまま出すと、実費計が少ないまま「精算済み」の紙になる。判子を押す書類なので、
    埋まっていないことが読んで分かる形にする。金額欄は空にして、備考で言う。
    """
    known = leg.get("amount") is not None
    return {
        "date": day_iso,
        "category": "交通費",
        "from": leg["from"], "to": leg["to"],
        "transport": leg.get("transport") or "鉄道",
        "payment": "個人立替",
        "receipt": "不要（公共交通機関特例）" if known and leg["amount"] < 30000 else "",
        "amount": leg["amount"] if known else "",
        "note": ((leg.get("note") or "") + (("　※" + leg["stale"]) if leg.get("stale") else "")).strip()
                if known else "★要確認：運賃が未登録。実額を入れること",
    }


def _issues(itin: dict) -> str:
    """未解決の欄。金額が足りていないことを先に書く。"""
    lines = []
    stale = [l for l in itin.get("legs", []) if l.get("stale")]
    if stale:
        lines.append("※%d 区間は、運賃改定より前に確かめた額です。実額を確かめてください。" % len(stale))
    n = itin.get("unpricedLegs", 0)
    if n:
        lines.append("※交通費 %d 区間が未登録です。下の実費計はその分だけ足りません。"
                     "運賃を確定させてから提出してください。" % n)
    lines += list(itin.get("warnings", []))
    return "\n".join(lines)


def build_doc(day: dt.date, profile: dict, itin: dict) -> dict:
    """index.html の newDoc('travel') に上書きする分だけ返す。"""
    onsite = [e for e in itin.get("events", []) if e.get("kind") == "onsite"]
    dests = []
    for e in onsite:
        loc = e.get("location") or e.get("station") or ""
        if loc and loc not in dests:
            dests.append(loc)
    purpose = "／".join(e.get("title", "") for e in onsite if e.get("title"))
    issuer_key = profile.get("defaultIssuer", "corp")
    issuer = profile.get("profiles", {}).get(issuer_key, {})
    name = profile.get("report", {}).get("author") or (issuer.get("rep", "").split("　")[-1] if issuer.get("rep") else issuer.get("name", ""))
    seq = "T%s-01" % day.strftime("%Y%m%d")
    return {
        "type": "travel",
        "issuer": issuer_key,
        "docNo": seq,
        "date": day.isoformat(),
        "travelName": name,
        "travelRole": itin.get("role", ""),
        "travelBase": itin.get("base", {}).get("id", ""),
        "travelDestination": "、".join(dests),
        "travelPurpose": purpose,
        "travelStart": day.isoformat(),
        "travelEnd": day.isoformat(),
        "travelLodgingType": "日帰り",
        "travelExpected": "",
        "travelActivities": "\n".join("%s–%s %s" % (e.get("start", ""), e.get("end", ""), e.get("title", "")) for e in onsite),
        "travelOutcomes": "",
        "travelIssues": _issues(itin),
        "travelNextActions": "",
        "travelAdvance": 0,
        "travelExpenses": [_expense_row(l, day.isoformat()) for l in itin.get("legs", [])],
        "showSeal": False,
    }
