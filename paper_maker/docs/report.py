"""営業報告書（日報）。カレンダー1日分＋行程＋所感メモ（任意）から1枚。AIで埋めない。"""
import datetime as dt

from .. import paths, render

_WD = "月火水木金土日"


def date_ja(d: dt.date) -> str:
    return "%d年%d月%d日（%s）" % (d.year, d.month, d.day, _WD[d.weekday()])


def _yen(v):
    return "" if v is None else "{:,}円".format(v)


def _memo_cell(e):
    """商談の中身。書いていなければ空欄のまま出す。こちらで埋めない。"""
    m = e.get("memo") or {}
    parts = []
    if m.get("相手"):
        parts.append('<b>%s</b>' % render.esc(m["相手"]))
    if m.get("話したこと"):
        parts.append(render.esc(m["話したこと"]))
    if m.get("本文"):
        parts.append(render.esc(m["本文"]).replace("\n", "<br>"))
    if m.get("次にやること"):
        parts.append('<div class="nx"><b>次:</b> %s</div>' % render.esc(m["次にやること"]))
    if m.get("出所"):
        parts.append('<div class="src">%s</div>' % render.esc(m["出所"]))
    return "<br>".join(parts)


def _rows_events(events):
    if not events:
        return '<tr><td colspan="5" class="empty">予定なし</td></tr>'
    kind_ja = {"onsite": "現地", "online": "オンライン", "unknown": "要確認"}
    out = []
    for e in events:
        t = "終日" if e.get("all_day") else "%s–%s" % (e.get("start", ""), e.get("end", ""))
        k = kind_ja.get(e.get("kind"), "")
        cls = ' class="warn"' if e.get("kind") == "unknown" else ""
        out.append("<tr><td>%s</td><td>%s</td><td>%s</td><td%s>%s</td><td>%s</td></tr>" % (
            render.esc(t), render.esc(e.get("title", "")), render.esc(e.get("location", "")), cls, k,
            _memo_cell(e)))
    return "\n".join(out)


def _rows_legs(legs):
    if not legs:
        return '<tr><td colspan="4" class="empty">現地の予定なし（移動なし）</td></tr>'
    out = []
    for l in legs:
        amt = _yen(l["amount"]) if l["amount"] is not None else '<span class="warn">要確認</span>'
        why = l.get("stale")
        src = render.esc(l.get("source") or l.get("note", ""))
        if why:
            src += '<div class="warn" style="font-size:10px">※%s</div>' % render.esc(why)
        out.append('<tr><td>%s → %s</td><td>%s</td><td class="num">%s</td><td>%s</td></tr>' % (
            render.esc(l["from"]), render.esc(l["to"]), render.esc(l.get("transport", "")), amt, src))
    return "\n".join(out)


def _rows_tomorrow(events):
    if not events:
        return '<tr><td colspan="3" class="empty">なし</td></tr>'
    out = []
    for e in events:
        t = "終日" if e.get("all_day") else "%s–%s" % (e.get("start", ""), e.get("end", ""))
        out.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            render.esc(t), render.esc(e.get("title", "")), render.esc(e.get("location", ""))))
    return "\n".join(out)


def read_note(day: dt.date) -> str:
    """所感欄に出す分だけ。訪問ごとの中身は表の列に入るので、ここでは重ねない。"""
    from .. import notes
    return notes.parse(day).get("free", "")


def build_html(day: dt.date, profile: dict, itin: dict, tomorrow_events, warnings, note: str = "") -> str:
    issuer = profile.get("profiles", {}).get(profile.get("defaultIssuer", "corp"), {})
    company = issuer.get("name", "")
    author = profile.get("report", {}).get("author") or issuer.get("rep", "")
    author_line = issuer.get("rep", "") if issuer.get("rep") else author
    legs = itin.get("legs", [])
    total_html = ""
    if legs:
        parts = ["交通費計 %s" % _yen(itin.get("transportTotal", 0))]
        if itin.get("unpricedLegs"):
            parts.append('<span class="warn">要確認 %d区間</span>' % itin["unpricedLegs"])
        if itin.get("allowance"):
            parts.append("日当 %s" % _yen(itin["allowance"]))
        total_html = '<div style="text-align:right;margin-top:1.5mm;font-size:11.5px">%s</div>' % "　".join(parts)
    all_w = list(warnings or []) + list(itin.get("warnings", []))
    warn_html = ""
    if all_w:
        warn_html = ('<h2>要確認</h2><ul style="margin:0 0 0 5mm;font-size:11px" class="warn">%s</ul>'
                     % "".join("<li>%s</li>" % render.esc(w) for w in all_w))
    ctx = {
        "date_iso": day.isoformat(),
        "date_ja": date_ja(day),
        "company": company,
        "author_line": author_line,
        "base_label": "%s（%s）" % (itin["base"].get("label", ""), itin["base"].get("address", "")) if itin["base"].get("address") else itin["base"].get("label", ""),
        "event_rows": _rows_events(itin.get("events", [])),
        "leg_rows": _rows_legs(legs),
        "leg_total": total_html,
        "memo": note if note else "（paper-maker note で作ったメモの「## 所感」がここに入る）",
        "memo_class": "" if note else " empty",
        "tomorrow_rows": _rows_tomorrow(tomorrow_events),
        "warnings_block": warn_html,
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    return render.fill("report.html", ctx)


def build_json(day: dt.date, profile: dict, itin: dict, tomorrow_events, warnings, note: str = "") -> dict:
    return {
        "type": "report",
        "date": day.isoformat(),
        # その日の行程がどの拠点から出たか。作り直した時に土地が変わらないように控える
        "baseKey": itin.get("baseKey", ""),
        "baseLabel": itin.get("baseLabel", ""),
        "events": itin.get("events", []),
        "legs": itin.get("legs", []),
        "transportTotal": itin.get("transportTotal", 0),
        "unpricedLegs": itin.get("unpricedLegs", 0),
        "allowance": itin.get("allowance", 0),
        "note": note,
        "tomorrow": tomorrow_events,
        "warnings": list(warnings or []) + list(itin.get("warnings", [])),
    }


def build_markdown(day: dt.date, itin: dict, tomorrow_events, note: str, warnings) -> str:
    """Obsidian 用。"""
    kind_ja = {"onsite": "現地", "online": "オンライン", "unknown": "要確認"}
    L = ["---", "type: 営業報告書", "date: %s" % day.isoformat(), "---", "", "# 営業報告書 %s" % date_ja(day), "",
         "## 面談・訪問"]
    if itin.get("events"):
        for e in itin["events"]:
            t = "終日" if e.get("all_day") else "%s–%s" % (e.get("start", ""), e.get("end", ""))
            L.append("- %s %s（%s）%s" % (t, e.get("title", ""), kind_ja.get(e.get("kind"), ""), (" @" + e["location"]) if e.get("location") else ""))
            m = e.get("memo") or {}
            if m.get("相手"): L.append("    - 相手: %s" % m["相手"])
            if m.get("話したこと"): L.append("    - 話したこと: %s" % m["話したこと"])
            if m.get("本文"): L.append("    - %s" % m["本文"].replace("\n", " / "))
            if m.get("次にやること"): L.append("    - 次: %s" % m["次にやること"])
    else:
        L.append("- 予定なし")
    L += ["", "## 移動"]
    if itin.get("legs"):
        for l in itin["legs"]:
            L.append("- %s → %s：%s" % (l["from"], l["to"], _yen(l["amount"]) if l["amount"] is not None else "要確認"))
        L.append("- 交通費計 %s／日当 %s" % (_yen(itin.get("transportTotal", 0)), _yen(itin.get("allowance", 0))))
    else:
        L.append("- なし")
    L += ["", "## 所感・次の一手", note or "", "", "## 明日の予定"]
    if tomorrow_events:
        for e in tomorrow_events:
            t = "終日" if e.get("all_day") else "%s–%s" % (e.get("start", ""), e.get("end", ""))
            L.append("- %s %s" % (t, e.get("title", "")))
    else:
        L.append("- なし")
    all_w = list(warnings or []) + list(itin.get("warnings", []))
    if all_w:
        L += ["", "## 要確認"] + ["- " + w for w in all_w]
    return "\n".join(L) + "\n"
