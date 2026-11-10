"""毎日の本体。前日分の予定 → 営業報告書（＋現地予定があれば出張精算）→ PDF / JSON / Obsidian。"""
import datetime as dt
import json
import pathlib

from . import ai, bridge, calendars, fares_write, geocode, ledger, freshness, itinerary, notes as notes_mod, paths, profile as prof_mod, render, report_fill
from .docs import report as report_doc, travel as travel_doc


def _log(msg: str):
    """ログには日付と結果だけ。個人名・住所・金額・予定名は書かない。"""
    p = paths.log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def out_paths(profile: dict, day: dt.date, kind: str):
    base = prof_mod.output_dir(profile) / str(day.year) / ("%02d" % day.month)
    base.mkdir(parents=True, exist_ok=True)
    stem = "%s_%s" % (kind, day.isoformat())
    return base / (stem + ".html"), base / (stem + ".pdf"), base / (stem + ".json")


def _fill_from_route(itin, day) -> int:
    """未登録の区間を、経路検索で引いて登録する。

    引けた分だけ入れる。引けなければ「★要確認」のまま残す。
    どこから取ったか（サイトと日付）を控えに書く。実費が出てきたら上書きできる。
    """
    from . import fare_route
    todo = []
    for l in itin.get("legs") or []:
        if l.get("amount"):
            continue
        a, b = l.get("from"), l.get("to")
        if a and b and (a, b) not in todo:
            todo.append((a, b))
    if not todo:
        return 0
    done = 0
    for a, b in todo[:8]:          # 1日ぶんの上限。叩き続けない
        got = fare_route.lookup(a, b, prefer=fares_write.prefer_of(a, b))
        if not got["amount"]:
            continue
        fares_write.add(a, b, got["amount"], transport="鉄道",
                        line=got["route"], source=got["source"],
                        routes=got.get("routes"))
        done += 1
    if done:
        _log("%s route-fare filled=%d" % (day.isoformat(), done))
    return done


def _base_used(prof, day):
    """その日の書類を前に作った時、どの拠点から出たことにしたか。

    出張先へ移ったあとに過去の日を作り直すと、行っていない土地からの行程になる。
    一度出した紙と数字が変わるのが一番まずいので、前の拠点を引き継ぐ。
    """
    _h, _p, js = out_paths(prof, day, "営業報告書")
    if not js.exists():
        return None
    try:
        return (json.loads(js.read_text(encoding="utf-8")) or {}).get("baseKey") or None
    except ValueError:
        return None


def run(day: dt.date, profile: dict = None, want_pdf=True, force=False, quiet=False,
        base_id=None) -> dict:
    prof = profile or prof_mod.load()
    base_id = base_id or _base_used(prof, day)
    places = prof_mod.load_places()
    fares = itinerary.Fares(prof_mod.load_stations(), prof_mod.load_fares())
    events, warnings = calendars.events_for_day(prof, day)
    tomorrow, _ = calendars.events_for_day(prof, day + dt.timedelta(days=1))
    # 住所しか書いていない予定を、先に駅へ結びつける。一度引いたら覚える
    if prof.get("report", {}).get("useAi", True):
        if ai.ready():
            got = geocode.resolve(events)
            if got["learned"]:
                places = prof_mod.load_places()
        elif any((e.get("location") or "").strip() for e in events):
            warnings.append("AI に繋がらないので、住所から駅を引けませんでした"
                            "（paper-maker ai check で確かめてください）")
    itin = itinerary.build(events, prof, places, fares, base_id)
    # 額の分からない区間を経路検索で埋める。1区間ずつ控えを残す
    if prof.get("travel", {}).get("lookupFares", False) and itin.get("legs"):
        if _fill_from_route(itin, day):
            fares = itinerary.Fares(prof_mod.load_stations(), prof_mod.load_fares())
            itin = itinerary.build(events, prof, places, fares, base_id)
    freshness.mark(itin.get("legs", []), day)   # 古い額を使っていたら備考に出す
    result = {"date": day.isoformat(), "events": len(events), "outputs": [], "warnings": [], "skipped": False}

    if not events and prof.get("report", {}).get("skipEmptyDays", True) and not force:
        result["skipped"] = True
        _log("%s skip(no events)" % day.isoformat())
        return result

    parsed = notes_mod.parse(day)
    notes_mod.attach(itin.get("events", []), parsed)
    note = parsed.get("free", "")
    # 手で書いたメモが無い予定は、カレンダーのメモ欄から起こす。手書きのほうが強いので上書きしない
    if prof.get("report", {}).get("fromCalendarNote", True):
        report_fill.fill(itin.get("events", []),
                         ai.api_key(),
                         use_ai=prof.get("report", {}).get("useAi", True))
    html_p, pdf_p, json_p = out_paths(prof, day, "営業報告書")
    html_p.write_text(report_doc.build_html(day, prof, itin, tomorrow, warnings, note), encoding="utf-8")
    json_p.write_text(json.dumps(report_doc.build_json(day, prof, itin, tomorrow, warnings, note),
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    result["outputs"] += [str(html_p), str(json_p)]
    if want_pdf:
        if render.html_to_pdf(html_p, pdf_p, prof.get("browser", "")):
            result["outputs"].append(str(pdf_p))
        else:
            result["warnings"].append("PDF 化できませんでした（Chrome/Edge が見つからないか時間切れ）。HTML は保存済み: %s" % html_p)

    if itin.get("hasOnsite"):
        doc = travel_doc.build_doc(day, prof, itin)
        _, tpdf, tjson = out_paths(prof, day, "出張精算")
        tjson.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        result["outputs"].append(str(tjson))
        if want_pdf:
            if render.app_doc_to_pdf(doc, prof.get("profiles", {}), tpdf, prof.get("browser", ""), travel=prof.get("travel")):
                result["outputs"].append(str(tpdf))
            else:
                result["warnings"].append("出張精算の PDF 化ができませんでした。JSON は保存済み: %s" % tjson)

    try:
        led = ledger.write(prof, day, itin, result["outputs"])
        if led:
            result["outputs"].append(led)
    except ledger.LedgerUnavailable as e:
        result["warnings"].append(str(e))

    ob = prof.get("output", {}).get("obsidianDir")
    if ob:
        od = pathlib.Path(ob).expanduser()
        od.mkdir(parents=True, exist_ok=True)
        md = od / ("営業報告書 %s.md" % day.isoformat())
        md.write_text(report_doc.build_markdown(day, itin, tomorrow, note, warnings), encoding="utf-8")
        result["outputs"].append(str(md))

    smp = prof_mod.sample_issuer(prof)
    if smp:
        result["warnings"].insert(0, "⚙設定の %s が見本のままです。書類にそのまま載ります" % smp)
    result["warnings"] += list(warnings) + list(itin.get("warnings", []))
    _log("%s ok events=%d outputs=%d warnings=%d" % (day.isoformat(), len(events), len(result["outputs"]), len(result["warnings"])))
    return result
