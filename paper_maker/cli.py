"""コマンドの入口。

  paper-maker init                 初回設定（会社情報・日当・拠点・カレンダー）
  paper-maker doctor               環境チェック（Python・ブラウザ・データ・カレンダー）
  paper-maker ai [list|set|check]  AI の接続先（Gemini / OpenAI / Claude / そのほか）
  paper-maker quest [--all]        導入の道順。今どこまで進んだか
  paper-maker daily [--date D]     前日分（or 指定日）の営業報告書＋出張精算を作る
  paper-maker report --date D      営業報告書だけ
  paper-maker note [--date D]      その日の営業メモの雛形を作って開く（訪問先が見出しで並ぶ）
  paper-maker rules                旅費規程書を作る
  paper-maker calendar --date D    その日の予定を読んで表示（取り込みの確認）
  paper-maker fare list|add        運賃表
  paper-maker fare import <ファイル…>  Suica等の履歴をまとめて取り込む（画像／テキスト／CSV）
  paper-maker fare auto            未登録の区間を自分で調べる（実額が引けた分だけ確定）
  paper-maker fare confirm <id> <金額>  候補を実額として確定させる
  paper-maker fare stale           いつ確かめた額か。改定より前の物を出す
  paper-maker fare gtfs            バスの運賃を公開データから取る（鍵なし・CC BY）
  paper-maker learn <ファイル…>     今までの契約書・見積・請求を取り込む（取引先・単価・条項）
  paper-maker knowledge            取り込んだ物を見る
  paper-maker doc <json> <pdf>     見積・請求・領収・契約・出張報告の JSON から PDF
  paper-maker open                 デスクトップのアイコンから呼ばれる入口（設定が無くても開く）
  paper-maker app                  GUI を開く
  paper-maker desktop              デスクトップにアイコンを置く（remove で消す）
  paper-maker sync                 定期の見直し（軽い。取りこぼしを拾う・運賃の鮮度を見る）
  paper-maker schedule install|remove|status   自動実行の登録（--every 60 で1時間ごと）
  paper-maker update [--check]     更新
  paper-maker version
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

from . import __version__, paths


class BadInput(Exception):
    """使う人の打ち間違い。トレースバックではなく1行で返す。"""


def _date(s: str) -> dt.date:
    try:
        y, m, d = (int(x) for x in s.split("-"))
        return dt.date(y, m, d)
    except (ValueError, TypeError):
        raise BadInput("日付は 2026-08-13 の形で書いてください（もらった値: %s）" % s)


def _yen_arg(s: str) -> int:
    try:
        return int(str(s).replace(",", "").replace("円", "").strip())
    except ValueError:
        raise BadInput("金額は数字で書いてください（もらった値: %s）" % s)


def cmd_init(a):
    from . import profile
    if profile.exists() and not a.force:
        print("既に設定があります: %s（作り直すなら --force）" % paths.profile_path())
        return 0
    profile.wizard(non_interactive=a.example)
    print("次は `paper-maker doctor` で環境を確認、そのあと `paper-maker app` を開くと")
    print("画面の右下に道順が出ます（ターミナル派は `paper-maker quest`）")
    return 0


def _certs_ok() -> bool:
    """https で外へ出られるか。

    python.org から入れた Python は、ルート証明書を持たずに入る。
    curl は通るのに ICS の取得だけ全滅する、という分かりにくい壊れ方をする
    （利用者の報告 2026-08-23。原因にたどり着くまで30分）。
    """
    import ssl
    import urllib.request
    try:
        ctx = ssl.create_default_context()
        paths_ = ctx.cert_store_stats()
    except Exception:
        paths_ = {}
    have = (paths_ or {}).get("x509_ca", 0)
    try:
        urllib.request.urlopen("https://www.google.com/generate_204", timeout=8)
        print("証明書  : あり（https で外に出られます）")
        return True
    except Exception as e:
        name = e.__class__.__name__
        print("証明書  : https に出られません（%s／CA %d 件）" % (name, have))
        import sys as _sys
        if _sys.platform == "darwin" and "/Library/Frameworks/Python.framework" in _sys.executable:
            ver = "%d.%d" % _sys.version_info[:2]
            print("          python.org 版の Python です。ルート証明書が入っていません。")
            print("          次の1行で入ります:")
            print("            /Applications/Python\\ %s/Install\\ Certificates.command" % ver)
        else:
            print("          カレンダーの URL 取得や更新の確認が通りません。")
            print("          社内のネットで傍受している場合は、CAバンドルの設定が要ります。")
        return False


def cmd_doctor(a):
    from . import profile, render, calendars
    ok = True
    print("Python  :", sys.version.split()[0], "(3.9 以上が必要)")
    if sys.version_info < (3, 9):
        ok = False
    b = render.find_browser()
    print("ブラウザ:", b or "見つからない（PDF 化には Chrome か Edge が要る。無くても HTML は出る）")
    if not _certs_ok():
        ok = False
    print("データ  :", paths.data_dir())
    for name, p in (("profile", paths.profile_path()), ("places", paths.places_path()),
                    ("fares", paths.fares_path()), ("stations", paths.stations_path())):
        print("  %-8s %s" % (name, "あり" if p.exists() else "なし"))
        if name == "profile" and not p.exists():
            ok = False
    if profile.exists():
        prof = profile.load()
        print("出力先  :", profile.output_dir(prof))
        srcs = prof.get("calendar", {}).get("sources", [])
        print("カレンダー:", "%d 件の取り口" % len(srcs) if srcs else "未設定")
        if srcs:
            evs, warns = calendars.events_for_day(prof, dt.date.today())
            print("  今日の予定 %d 件" % len(evs))
            for w in warns:
                print("  注意:", w)
    from . import ai as _ai
    c = _ai.load()
    print("AI      : %s / %s（鍵 %s）" % (c.get("label", c["provider"]), c.get("model") or "未設定",
                                        "あり" if _ai.api_key(c) else "なし。AIを使う機能だけ止まります"))
    print("結果    :", "OK" if ok else "要対応")
    return 0 if ok else 1


def cmd_ai(a):
    from . import ai, bridge
    if a.ai_cmd == "list":
        cur = ai.load()
        print("今の接続先: %s（%s）" % (cur.get("label", cur["provider"]), cur.get("model") or "モデル未設定"))
        print("鍵: %s → %s" % (cur["keyName"], "あり" if ai.api_key(cur) else "まだ"))
        print("\n選べる先")
        for k, v in ai.PRESETS.items():
            print("  %-10s %-18s 既定モデル %-22s 鍵の名前 %s" % (k, v["label"], v["model"] or "（自分で指定）", v["keyName"]))
            print("             %s" % v["where"])
        print("\n変えるとき: paper-maker ai set openai --model gpt-4o-mini")
        print("鍵の入れ方 : paper-maker ai key <鍵の文字列>")
        return 0
    if a.ai_cmd == "key":
        cur = ai.load()
        bridge.write_secret(cur["keyName"], a.value)
        print("%s を入れました（%s）" % (cur["keyName"], paths.secrets_path()))
        ok, msg = ai.check()
        print(("繋がりました: " if ok else "") + msg)
        return 0 if ok else 1
    if a.ai_cmd == "set":
        if a.provider not in ai.PRESETS:
            print("選べるのは: %s" % "、".join(ai.PRESETS))
            return 1
        cfg = dict(ai.PRESETS[a.provider]); cfg["provider"] = a.provider
        if a.model:
            cfg["model"] = a.model
        if a.endpoint:
            cfg["endpoint"] = a.endpoint
        if a.key_name:
            cfg["keyName"] = a.key_name
        if a.provider == "custom" and not cfg.get("endpoint"):
            print("そのほか を選ぶときは --endpoint も要ります（例: https://…/v1/chat/completions）")
            return 1
        ai.save(cfg)
        print("接続先を %s にしました（%s）" % (cfg["label"], cfg.get("model") or "モデル未設定"))
        if not ai.api_key(cfg):
            print("鍵がまだです: paper-maker ai key <鍵の文字列>")
            print("  取る所: %s" % cfg["where"])
        return 0
    ok, msg = ai.check()
    print(msg)
    return 0 if ok else 1


def cmd_quest(a):
    from . import quest
    r = quest.evaluate(recheck=a.recheck)
    if not r["hasProfile"]:
        print("まだ設定がありません。先に `paper-maker init` を実行してください")
        return 1
    print("はじめの道順  %d / %d" % (r["done"], r["total"]))
    for q in r["quests"]:
        mark = "済" if q["done"] else ("―" if q["skipped"] else "  ")
        cur = "→" if q["id"] == r["current"] else " "
        print("%s %s %d %-18s %s" % (cur, mark, q["id"], q["title"], q["note"]))
    if r["finished"]:
        print("\n一通り動きます。あとは毎朝、前日分が置いてあります")
        return 0
    nxt = next((q for q in r["quests"] if q["id"] == r["current"]), None)
    if nxt:
        print("\n次にやること")
        print("  %s" % nxt["todo"])
        print("  → %s" % nxt["reward"])
        if nxt.get("gain"):
            print("  %s" % nxt["gain"])
        for line in nxt["how"].splitlines():
            print("  %s" % line)
        if nxt.get("shot"):
            print("  出来上がりの見本: %s" % (paths.APP_HTML.parent / "tutorial" / nxt["shot"]))
    if a.all:
        print()
        for q in r["quests"]:
            print("── %d %s" % (q["id"], q["title"]))
            print("   %s" % q["why"])
            print("   やること: %s" % q["todo"])
            print("   出る物  : %s" % q["reward"])
            if q.get("gain"):
                print("   良くなる: %s" % q["gain"])
            first, _, rest = q["how"].partition("\n")
            print("   やり方  : %s" % first)
            for line in rest.splitlines():
                print("             %s" % line)
    return 0


def cmd_daily(a):
    from . import daily, guard
    day = _date(a.date) if a.date else dt.date.today() - dt.timedelta(days=1)
    with guard.only_one("daily") as got:
        if not got:
            print("いま定期の回が同じ書類を作っています。少し待ってからもう一度")
            return 1
        base_id = None
        if getattr(a, "base", ""):
            from . import bases
            hit = [k for k, b in (bases.load()[0] or {}).items()
                   if a.base in (b.get("label") or "") or a.base == k]
            if not hit:
                print("その呼び名の拠点がありません: %s" % a.base)
                return 1
            base_id = hit[0]
        r = daily.run(day, want_pdf=not a.no_pdf, force=a.force, base_id=base_id)
    if r["skipped"]:
        print("%s: 予定なしのため作成しませんでした（--force で作る）" % day)
        return 0
    print("%s: 予定 %d 件" % (day, r["events"]))
    for o in r["outputs"]:
        print("  出力:", o)
    for w in r["warnings"]:
        print("  要確認:", w)
    return 0


def cmd_report(a):
    a.force = True
    return cmd_daily(a)


def cmd_note(a):
    """訪問先を見出しにしたメモを作る。手ぶらのメモ帳より、名前が並んでいるほうが書ける。"""
    import subprocess
    from . import calendars, itinerary, notes, profile
    prof = profile.load()
    day = _date(a.date) if a.date else dt.date.today()
    evs, warns = calendars.events_for_day(prof, day)
    places = profile.load_places()
    stations = profile.load_stations()
    for e in evs:
        e["kind"] = itinerary.classify(e, places, stations)[0]
    p, made = notes.ensure(day, evs)
    print(("作りました: %s" if made else "もうあります: %s") % p)
    if made and not evs:
        print("  （その日の予定が0件だったので、見出しは空です）")
    for w in warns:
        print("  注意:", w)
    if not a.no_open:
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", "-t", str(p)], check=False)
            elif sys.platform == "win32":
                import os
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", str(p)], check=False)
        except Exception:
            pass
    print("書いたら `paper-maker daily --date %s` で報告書に入ります" % day.isoformat())
    return 0


def cmd_rules(a):
    from . import profile, render
    from .docs import rules
    prof = profile.load()
    smp = profile.sample_issuer(prof)
    if smp and not a.force:
        print("止めました。⚙設定の %s が見本のままです。" % smp)
        print("この紙は税理士に見せる物です。見本の会社名で出すと差し替えになります。")
        print("直すのは画面の⚙設定、または paper-maker auto に過去の請求書を1枚。")
        print("それでも出すなら --force")
        return 1
    out_dir = profile.output_dir(prof) / "規程"
    out_dir.mkdir(parents=True, exist_ok=True)
    html_p = out_dir / "旅費規程.html"
    pdf_p = out_dir / "旅費規程.pdf"
    html_p.write_text(rules.build_html(prof), encoding="utf-8")
    print("出力:", html_p)
    if not a.no_pdf:
        if render.html_to_pdf(html_p, pdf_p, prof.get("browser", "")):
            print("出力:", pdf_p)
        else:
            print("PDF 化できませんでした（ブラウザ無しか時間切れ）。HTML を印刷してください")
    return 0


def cmd_proposal(a):
    """ご提案書を1本。中身は JSON に書いた物だけを出す。"""
    from . import profile, render
    from .docs import proposal
    prof = profile.load()
    smp = profile.sample_issuer(prof)
    if smp and not a.force:
        print("止めました。⚙設定の %s が見本のままです。" % smp)
        print("この紙は相手の会社に渡す物です。見本の会社名のまま出すと出し直しになります。")
        print("直すのは画面の⚙設定、または paper-maker auto に過去の請求書を1枚。")
        print("それでも出すなら --force")
        return 1
    src = pathlib.Path(a.json_path)
    if not src.exists():
        print("見つかりません:", src)
        return 1
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except ValueError as e:
        print("JSON が読めません:", e)
        return 1
    if not data.get("client"):
        print("client（宛先の会社名）が空です。JSON に入れてください")
        return 1
    out_dir = profile.output_dir(prof) / "提案書"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "ご提案書_%s_%s" % (data["client"], (data.get("date") or "").replace("-", ""))
    html_p = out_dir / (stem.rstrip("_") + ".html")
    pdf_p = out_dir / (stem.rstrip("_") + ".pdf")
    html_p.write_text(proposal.build_html(prof, data), encoding="utf-8")
    print("出力:", html_p)
    if not a.no_pdf:
        if render.html_to_pdf(html_p, pdf_p, prof.get("browser", "")):
            print("出力:", pdf_p)
        else:
            print("PDF 化できませんでした（ブラウザ無しか時間切れ）。HTML を印刷してください")
    return 0


def cmd_denshi(a):
    """電帳法の事務処理規程を1枚。電子で書類を渡すなら要る。"""
    from . import profile, render
    from .docs import denshi
    prof = profile.load()
    smp = profile.sample_issuer(prof)
    if smp and not a.force:
        print("止めました。⚙設定の %s が見本のままです。" % smp)
        print("税務署に見せる紙なので、先に直してください。それでも出すなら --force")
        return 1
    out_dir = profile.output_dir(prof) / "規程"
    out_dir.mkdir(parents=True, exist_ok=True)
    html_p = out_dir / "電子取引データ事務処理規程.html"
    pdf_p = out_dir / "電子取引データ事務処理規程.pdf"
    html_p.write_text(denshi.build_html(prof), encoding="utf-8")
    print("出力:", html_p)
    if not a.no_pdf:
        if render.html_to_pdf(html_p, pdf_p, prof.get("browser", "")):
            print("出力:", pdf_p)
        else:
            print("PDF 化できませんでした。HTML を印刷してください")
    print("電子取引の範囲と保存場所は、実際の業務に合わせて直してください（profile.json の denshi）")
    return 0


def cmd_calendar(a):
    from . import profile, calendars, itinerary
    prof = profile.load()
    day = _date(a.date) if a.date else dt.date.today()
    evs, warns = calendars.events_for_day(prof, day)
    places = profile.load_places()
    stations = profile.load_stations()
    print("%s: %d 件" % (day, len(evs)))
    for e in evs:
        kind, st, why = itinerary.classify(e, places, stations)
        t = "終日" if e["all_day"] else "%s–%s" % (e["start"], e["end"])
        print("  %-11s %-30s %-20s %s%s" % (t, e["title"][:30], (e["location"] or "")[:20], kind, ("→" + st) if st else ""))
    for w in warns:
        print("  注意:", w)
    return 0


def _fare_row(frm, to):
    from . import profile
    fares = profile.load_fares()
    st = profile.load_stations().get("stations", {})
    name = {k: (v.get("name") or k).rstrip("駅") for k, v in st.items()}
    a, b = frm.rstrip("駅"), to.rstrip("駅")
    for r in fares.get("fares", []):
        if name.get(r["from"]) == a and name.get(r["to"]) == b:
            return fares, r
    return fares, None


def cmd_fare_bulk(a):
    """拠点から、よく行く先への運賃をまとめて用意する。"""
    from . import fare_route, fares_bulk, fares_write, profile
    prof = profile.load()
    got = fares_bulk.pending(prof, limit=a.limit)
    if got["note"]:
        print(got["note"])
        return 1
    pairs = got["pairs"]
    if not pairs:
        print("%s から行く先は、もう額が入っています" % got["base"])
        return 0
    print("%s（%s）から、まだ額の無い区間が %d 本あります" % (got["base"], got["home"], len(pairs)))
    for a_, b_ in pairs:
        print("   %s → %s" % (a_, b_))
    auto = (prof.get("travel") or {}).get("lookupFares", False)
    if not auto:
        print("\n乗換案内で1本ずつ調べて、画面を道順6の枠に落としてください。")
        print("自分で調べた分を入れる形にしてあります（配布版では自動で取りに行きません）。")
        return 0
    if not a.apply:
        print("\n調べて入れるなら --apply")
        return 0
    done = 0
    for a_, b_ in pairs:
        r = fare_route.lookup(a_, b_, prefer=fares_write.prefer_of(a_, b_))
        if not r["amount"]:
            print("   引けず: %s → %s（%s）" % (a_, b_, r["note"][:40]))
            continue
        fares_write.add(a_, b_, r["amount"], line=r["route"], source=r["source"],
                        routes=r.get("routes"))
        print("   %s → %s  %s円  %s" % (a_, b_, "{:,}".format(r["amount"]), r["route"][:34]))
        done += 1
    print("\n入れました: %d 本" % done)
    return 0


def cmd_fare_routes(a):
    """その区間の行き方を並べる。どれで行ったか選ぶために。"""
    from . import fare_route, fares_write, profile
    _f, row = _fare_row(a.frm, a.to)
    routes = (row or {}).get("routes") or []
    if not routes or a.again:
        print("調べています…")
        got = fare_route.lookup(a.frm, a.to, prefer=fares_write.prefer_of(a.frm, a.to))
        routes = got.get("routes") or []
        if got["amount"]:
            fares_write.add(a.frm, a.to, got["amount"], line=got["route"],
                            source=got["source"], routes=routes)
    if not routes:
        print("行き方が見つかりませんでした")
        return 1
    now = (row or {}).get("amount")
    for n, r in enumerate(routes, 1):
        mark = "  ←今これ" if now == r["amount"] else ""
        print("%d) %7s円  %3s分  %s%s" % (n, "{:,}".format(r["amount"]), r["minutes"],
                                          "／".join(r.get("lines") or []) or r.get("note", ""), mark))
    print("\nこれで行った、を選ぶ: paper-maker fare pick %s %s 1" % (a.frm, a.to))
    return 0


def cmd_fare_pick(a):
    from . import fares_write, profile
    _f, row = _fare_row(a.frm, a.to)
    routes = (row or {}).get("routes") or []
    if not routes:
        print("先に行き方を出してください: paper-maker fare routes %s %s" % (a.frm, a.to))
        return 1
    if not (1 <= a.number <= len(routes)):
        print("1〜%d のどれかを選んでください" % len(routes))
        return 1
    r = routes[a.number - 1]
    lines = r.get("lines") or []
    keys = fares_write.kinds_of(lines)
    fares_write.add(a.frm, a.to, r["amount"], line="／".join(lines),
                    source="本人が選択 %s" % dt.date.today().isoformat(),
                    routes=routes, prefer=keys)
    print("%s → %s を %s円（%s）にしました" % (a.frm, a.to, "{:,}".format(r["amount"]),
                                              "／".join(lines)[:40]))
    if keys:
        print("  次からは %s の行き方を優先します" % "・".join(keys))
    return 0


def cmd_fare(a):
    if a.fare_cmd == "bulk":
        return cmd_fare_bulk(a)
    if a.fare_cmd == "routes":
        return cmd_fare_routes(a)
    if a.fare_cmd == "pick":
        return cmd_fare_pick(a)
    if a.fare_cmd == "import":
        return cmd_fare_import(a)
    if a.fare_cmd == "auto":
        return cmd_fare_auto(a)
    if a.fare_cmd == "confirm":
        return cmd_fare_confirm(a)
    if a.fare_cmd == "stale":
        return cmd_fare_stale(a)
    if a.fare_cmd == "gtfs":
        return cmd_fare_gtfs(a)
    from . import profile
    fares = profile.load_fares()
    stations = profile.load_stations()
    if a.fare_cmd == "list":
        names = {k: v["name"] for k, v in stations.get("stations", {}).items()}
        for r in fares.get("fares", []):
            amt = "{:,}円".format(r["amount"]) if r.get("amount") is not None else "未登録"
            line = "  %-14s %s → %s  %s%s" % (r.get("transport", ""), names.get(r["from"], r["from"]),
                                              names.get(r["to"], r["to"]), amt, "" if r.get("verified") else "（未確認）")
            if a.ids:
                line += "   id=%s" % r.get("id", "")
            print(line)
            for c in r.get("candidates", []):
                print("        候補 %s円  %s %s" % ("{:,}".format(c["amount"]), c.get("source", ""), c.get("route", "")))
        return 0
    # add
    st = stations.setdefault("stations", {})

    def ensure_station(name):
        for sid, s in st.items():
            if s["name"].rstrip("駅") == name.rstrip("駅"):
                return sid
        sid = "s%d" % (len(st) + 1)
        while sid in st:
            sid += "x"
        st[sid] = {"name": name if name.endswith("駅") or a.transport == "バス" else name + "駅", "kind": "bus" if a.transport == "バス" else "rail", "pref": ""}
        return sid
    f_id, t_id = ensure_station(a.frm), ensure_station(a.to)
    row = {"id": "%s_%s" % (f_id, t_id), "from": f_id, "to": t_id, "transport": a.transport, "line": a.line or "",
           "amount": _yen_arg(a.amount), "verified": True, "source": a.source or "利用者登録", "checkedAt": dt.date.today().isoformat()}
    rows = [r for r in fares.get("fares", []) if not (r["from"] == f_id and r["to"] == t_id)]
    rows.append(row)
    fares["fares"] = rows
    profile.save_stations(stations)
    profile.save_fares(fares)
    print("登録: %s → %s %s円（%s）" % (a.frm, a.to, row["amount"], a.transport))
    return 0


def cmd_fare_import(a):
    from . import bridge, fares_import as fi, profile
    profile.load()          # 設定が無ければここで止める
    records, notes_ = [], []
    for path in a.files:
        p = pathlib.Path(path).expanduser()
        if not p.exists():
            print("見つかりません:", p)
            return 1
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".heic"):
            from . import ai as _ai
            key = _ai.api_key()
            if not key:
                c = _ai.load()
                print("画像を読むには AI に繋ぐ設定が要ります（今の設定: %s）" % c.get("label", c["provider"]))
                print("  paper-maker ai list        …… 選べる先を見る")
                print("  paper-maker ai key <鍵>    …… 鍵を入れて、その場で繋がるか試す")
                print("鍵を使わないなら、履歴をテキストで書いたファイルを渡すか paper-maker fare add で1件ずつ")
                return 1
            try:
                r = fi.read_image(p, key)
            except Exception as e:
                print("%s を読めませんでした: %s" % (p.name, e.__class__.__name__))
                continue
            notes_.append("%s から %d 行" % (p.name, len(r)))
            records += r
        else:
            r, bad = fi.parse_text(p.read_text(encoding="utf-8", errors="replace"))
            notes_.append("%s から %d 行（読めない行 %d）" % (p.name, len(r), bad))
            records += r
    for n in notes_:
        print(" ", n)
    if not records:
        print("取り込める明細がありませんでした")
        return 1
    sm = fi.summarize(records, min_times=a.min_times)

    def show(title, items, tail=""):
        if not items:
            return
        print("\n%s（%d件）%s" % (title, len(items), tail))
        for it in items:
            amt = "{:,}円".format(it["amount"]) if it["amount"] is not None else " / ".join("{:,}".format(x) for x in it["amounts"]) + "円"
            arrow = "" if it["kind"] == "bus" else " → " + it["to"]
            print("  %-4s %s%s  %s  %d回" % ("バス" if it["kind"] == "bus" else "鉄道", it["from"], arrow, amt, it["times"]))
    show("確定にする", sm["sure"])
    show("確認待ち", sm["wait"], "… %d回以上出てこないと書類には使いません" % a.min_times)
    show("額が食い違う", sm["clash"], "… 取り込みません。実額を fare add で入れてください")
    show("怪しい", sm.get("odd", []), "… 同じ駅どうし。読み間違いとして外しました")
    if not a.apply:
        print("\n入れるときは --apply を付けてもう一度")
        return 0
    n = fi.apply(sm)
    print("\n%d 区間を運賃表に入れました" % n)
    return 0


def cmd_fare_auto(a):
    from . import bridge, fares_auto as fa, profile
    prof = profile.load()
    pairs = fa.pending_pairs(prof)
    if a.pair:
        pairs = [(a.pair[0], a.pair[1], None)]
    if not pairs:
        print("未登録の区間はありません")
        return 0
    token = bridge.read_secret("ODPT_TOKEN")
    from . import ai as _ai
    key = _ai.api_key() if not a.no_ai else ""
    print("%d 区間を調べます（オープンデータ%s／AIの候補%s）" % (
        len(pairs), "＋鍵あり" if token else "", "あり" if key else "なし"))
    r = fa.collect(prof, pairs, token, key)
    if r["found"]:
        print("\n実額が引けた（そのまま使える）")
        for x in r["found"]:
            print("  %s → %s  %s円   %s" % (x["from"], x["to"], "{:,}".format(x["amount"]), x["source"]))
    if r["guessed"]:
        print("\n候補どまり（書類には使いません。確かめてから確定させてください）")
        for x in r["guessed"]:
            print("  %s → %s  %s円   %s %s" % (x["from"], x["to"], "{:,}".format(x["amount"]), x["source"], x.get("route", "")))
    if r["missed"]:
        print("\n分かりませんでした")
        for x in r["missed"]:
            print("  %s → %s" % (x["from"], x["to"]))
    if not a.apply:
        print("\n書き込むときは --apply を付けてもう一度")
        return 0
    ok, cand = fa.apply(r)
    print("\n実額 %d 区間を登録。候補 %d 区間を控えました" % (ok, cand))
    if cand:
        print("候補を使うときは paper-maker fare confirm <id> <金額>（id は fare list --ids で見えます）")
    return 0


def cmd_fare_gtfs(a):
    from . import fares_gtfs as g, itinerary, profile
    profile.load()
    rows = g.feeds()
    hits = g.search(rows, a.pref or "", a.word or "")
    if not a.pref and not a.word:
        print("公開されているフィード %d 件。都道府県か事業者名で絞ってください" % len(rows))
        print("  paper-maker fare gtfs --pref <県名>")
        print("  paper-maker fare gtfs --word 日東")
        return 0
    if not hits:
        print("見つかりません（%s %s）" % (a.pref or "", a.word or ""))
        return 1
    print("%d 件" % len(hits))
    for i, r in enumerate(hits, 1):
        print("  %2d. %s / %s  [%s] %s" % (i, r["org"], r["feed"], r["license"], r["updated"]))
    if not a.apply:
        print("\n入れるときは --apply（--only 3 のように番号で選べます）")
        return 0

    want = hits if not a.only else [hits[i - 1] for i in a.only if 1 <= i <= len(hits)]
    total = 0
    stops = a.stop or None
    for r in want:
        pairs, err = g.read_feed(r["url"])
        if err:
            print("  %s: %s" % (r["org"], err))
            continue
        picked = g.pick(pairs, stops, a.limit)
        n = g.apply(picked, r["org"], r["license"], profile, itinerary)
        total += n
        print("  %s / %s: %d 区間（元の表は %d 区間）" % (r["org"], r["feed"], n, len(pairs)))
    print("\n合計 %d 区間を入れました" % total)
    if total:
        print("出どころは運賃表に残してあります（CC BY は表示が条件）: paper-maker fare list")
    return 0


def cmd_fare_stale(a):
    from . import freshness, profile
    profile.load()
    r = freshness.check()
    print("実額として使っている運賃: %d 区間" % r["total"])
    if r["old"]:
        print("\n古いかもしれない（%d 区間）" % len(r["old"]))
        for x in r["old"]:
            print("  %s → %s  %s円  %s" % (x["from"], x["to"], "{:,}".format(x["amount"]), x["why"]))
            print("      確かめた日 %s / %s / id=%s" % (x["checkedAt"] or "不明", x["source"][:40], x["id"]))
    if r["unknown"]:
        print("\nいつ確かめたか分からない（%d 区間）" % len(r["unknown"]))
        for x in r["unknown"]:
            print("  %s → %s  %s円" % (x["from"], x["to"], "{:,}".format(x["amount"])))
    if not r["old"] and not r["unknown"]:
        print("古い物はありません")
        return 0
    print("\n直すには、実際に払った額で上書きしてください")
    print("  paper-maker fare confirm <id> <金額> --source \"領収書 2026-08-19\"")
    print("  まとめてなら paper-maker fare import <Suicaのスクショ> --apply")
    return 0


def cmd_fare_confirm(a):
    from . import fares_auto as fa, profile
    profile.load()
    r = fa.confirm(a.fare_id, _yen_arg(a.amount), a.source)
    if not r:
        print("その id は見つかりません: %s" % a.fare_id)
        return 1
    print("確定: %s = %s円" % (a.fare_id, "{:,}".format(r["amount"])))
    return 0


def cmd_auto(a):
    """設定を、聞かずに埋める。押されるまで書かない。"""
    from . import autoset
    files = [str(pathlib.Path(f).expanduser()) for f in (a.files or [])]
    for f in files:
        if not pathlib.Path(f).exists():
            print("見つかりません:", f)
            return 1
    if files:
        print("読んでいます: %s" % "／".join(pathlib.Path(f).name for f in files))
    else:
        print("パソコンの中を見ています…")
    pl = autoset.plan(files=files, use_ai=not a.no_ai)
    steps = pl["steps"]
    if not steps:
        print("\n埋める所はありませんでした。")
        for n in pl["notes"]:
            print("  ・" + n)
        return 0
    print("\nこれを入れます。")
    for s in steps:
        mark = "上書" if s.overwrite else "追加"
        val = s.new if len(s.new) <= 60 else s.new[:57] + "…"
        print("  [%s] %-14s %s" % (mark, s.what, val.replace("\n", " / ")))
        print("         %s" % s.source)
        if s.overwrite:
            now = s.now if len(s.now) <= 40 else s.now[:37] + "…"
            print("         今は: %s" % now.replace("\n", " / "))
        if s.note:
            print("         %s" % s.note)
    print("")
    for n in pl["notes"]:
        print("  ・" + n)
    if not a.apply:
        print("\nこれで良ければ --apply を付けてもう一度")
        return 0
    got = autoset.apply(pl)
    print("\n入れました: %d 箇所" % got["written"])
    print("残りは paper-maker quest で見られます")
    return 0


def cmd_base(a):
    """拠点（今いる場所）の登録と切り替え。"""
    from . import bases
    try:
        if a.base_cmd == "add":
            b = bases.add(a.label, a.address, a.station or "")
            print("入れました: %s（%s）%s" % (b["label"], b["station"] or "最寄駅は未記入",
                                             "／今いる所にしました" if b["current"] else ""))
            if b.get("note"):
                print("  " + b["note"])
            if not b["station"]:
                print("  最寄駅を引けませんでした。paper-maker base add でもう一度、駅を添えて入れてください")
            return 0
        if a.base_cmd == "use":
            b = bases.use(a.label)
            print("今いる所を %s（最寄 %s）にしました" % (b["label"], b["station"] or "駅なし"))
            return 0
        if a.base_cmd == "remove":
            print(bases.remove(a.label))
            return 0
        rows = bases.listing()
        if not rows:
            print("拠点がまだありません。paper-maker base add 呼び名 住所")
            return 0
        for r in rows:
            print("%s %-10s %-28s %s" % ("→" if r["current"] else "  ", r["label"],
                                         r["address"][:28], r["station"] or "（駅なし）"))
        print("\n今いる所を移す: paper-maker base use 拠点の呼び名")
        return 0
    except bases.BadBase as e:
        print(e)
        return 1


def cmd_places(a):
    """住所から覚えた駅の一覧。間違って覚えたら忘れさせる。"""
    from . import profile
    pl = profile.load_places()
    rules = pl.get("rules", [])
    if a.forget:
        keep = [r for r in rules if not any(a.forget in m for m in r.get("match", []))]
        if len(keep) == len(rules):
            print("その言葉で覚えている所はありません:", a.forget)
            return 1
        pl["rules"] = keep
        profile.save_places(pl)
        print("忘れました（%d 件）。次に出す時、もう一度住所から引き直します" % (len(rules) - len(keep)))
        return 0
    if not rules:
        print("まだ1件も覚えていません")
        return 0
    for r in rules:
        print("%-28s → %s  %s" % ("／".join(r.get("match", []))[:28],
                                  r.get("station", ""), r.get("note", "")))
    print("\n違う駅を覚えていたら: paper-maker places --forget 広岡")
    return 0


def cmd_learn(a):
    from . import ai, knowledge, profile
    profile.load()
    if not ai.api_key():
        print("読ませるには AI に繋ぐ設定が要ります（道順の「AI に繋ぐ」／paper-maker ai list）")
        return 1
    results, raws = [], []
    for path in a.files:
        p = pathlib.Path(path).expanduser()
        if not p.exists():
            print("見つかりません:", p)
            return 1
        print("読んでいます:", p.name)
        try:
            results.append(knowledge.read_one(p))
            raws.append((p.name, p.read_bytes()))
        except Exception as e:
            print("  読めませんでした: %s" % e.__class__.__name__)
    if not results:
        print("読めた書類がありませんでした")
        return 1
    sm = knowledge.summarize(results)
    for r in sm["docs"]:
        print("\n── %s（%s）%s" % (r.get("title") or r["source"], r["kind"], r.get("date") or ""))
        c = r.get("client") or {}
        if c.get("name"):
            print("   相手先: %s %s" % (c["name"], c.get("address", "")))
        for it in (r.get("items") or [])[:6]:
            print("   品目  : %s %s%s × %s" % (it.get("name"), "{:,}".format(int(it.get("price") or 0)), "円", it.get("qty")))
        if r.get("clauses"):
            print("   条項  : %d 本（%s ほか）" % (len(r["clauses"]), r["clauses"][0].get("heading", "")))
        t = r.get("terms") or {}
        if any(t.values()):
            print("   条件  : %s" % "／".join(v for v in (t.get("payment"), t.get("delivery"), t.get("period")) if v))
    print("\nまとめ: 取引先 %d／品目 %d／条項 %d" % (len(sm["clients"]), len(sm["items"]), len(sm["clauses"])))
    if not a.apply:
        print("控えに入れるときは --apply を付けてもう一度")
        return 0
    n = knowledge.apply(sm, raws)
    print("入れました: 書類 %d／取引先 %d／品目 %d／条項 %d" % (n["docs"], n["clients"], n["items"], n["clauses"]))
    print("原本は %s に控えました" % knowledge.files_dir())
    return 0


def cmd_knowledge(a):
    from . import knowledge, profile
    profile.load()
    d = knowledge.load()
    if a.what == "clients":
        for c in d["clients"]:
            print("  %s %s  ← %s" % (c["name"], c.get("address", ""), c.get("from", "")))
        return 0
    if a.what == "items":
        for r in knowledge.item_prices(a.word or ""):
            print("  %-24s %9s円  %s  %s" % (r["name"][:24], "{:,}".format(r["price"]),
                                             r.get("date") or "日付なし", r.get("client", "")))
        return 0
    if a.what == "clauses":
        for c in d["clauses"]:
            print("  %s  ← %s" % (c["heading"], c.get("title") or c.get("from", "")))
        return 0
    print("取り込んだ書類 %d / 取引先 %d / 品目 %d / 条項 %d" % (
        len(d["docs"]), len(d["clients"]), len(d["items"]), len(d["clauses"])))
    for r in d["docs"][-6:]:
        print("  %-10s %s（%s）" % (r.get("takenAt", ""), r.get("title") or r.get("source"), r.get("kind")))
    print("\n中身を見る: paper-maker knowledge clients / items / clauses")
    return 0


def cmd_doc(a):
    from . import knowledge, profile, render
    prof = profile.load()
    payload = json.loads(pathlib.Path(a.json_path).read_text(encoding="utf-8"))
    doc = payload.get("doc", payload)
    # 宛先だけ書いてあれば、控えから住所を補う
    if doc.get("clientName") and not doc.get("clientAddress"):
        c = knowledge.find_client(doc["clientName"])
        if c and c.get("address"):
            doc["clientAddress"] = c["address"]
            print("控えから住所を補いました:", c["address"])
    # 契約書で本文が空なら、控えた条項を並べる
    if doc.get("type") == "contract" and not doc.get("cBody"):
        body = knowledge.contract_body()
        if body:
            doc["cBody"] = body
            print("控えた条項を差し込みました（%d 文字）" % len(body))
    profiles = payload.get("profiles") or prof.get("profiles", {})
    pdf = pathlib.Path(a.pdf_path)
    ok = render.app_doc_to_pdf(doc, profiles, pdf, prof.get("browser", ""), travel=prof.get("travel"))
    print("OK:" if ok else "失敗:", pdf)
    return 0 if ok else 1


def cmd_app(a):
    from . import bridge
    bridge.serve(open_it=not a.no_open, port=a.port)
    return 0


def cmd_open(a):
    """アイコンから呼ばれる入口。ターミナルを開いたことがない人でも、押せば始まる。"""
    import socket
    from . import bridge, profile
    made = profile.ensure_exists()
    if made:
        print("はじめまして。設定を作りました:", paths.profile_path())
    def mine(port):
        """そこに居るのが自分かどうか。よその物を開かないため。"""
        import json as _json
        import urllib.request
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/api/hello" % port, timeout=2) as r:
                d = _json.loads(r.read().decode("utf-8"))
        except Exception:
            return False
        return d.get("app") == "paper-maker" and d.get("home") == str(paths.data_dir())

    free = None
    for port in range(a.port, a.port + 12):
        with socket.socket() as s0:
            busy = s0.connect_ex(("127.0.0.1", port)) == 0
        if busy:
            if mine(port):
                url = "http://127.0.0.1:%d/index.html" % port
                print("もう開いています:", url)
                bridge.open_browser(url)
                return 0
            continue          # よその物。次のポートへ
        if free is None:
            free = port
    if free is None:
        print("空いているポートが見つかりませんでした")
        return 1
    return bridge.serve(open_it=True, port=free) or 0


def cmd_desktop(a):
    from . import desktop
    if a.what == "remove":
        print(desktop.remove())
        return 0
    p = desktop.install()
    print("デスクトップに置きました:", p)
    print("これを押すと画面が開きます。ターミナルは要りません")
    return 0


def cmd_sync(a):
    from . import sync
    r = sync.run(make_missing=not a.no_make)
    print("見直し %s：予定 %d 件" % (r["at"], r["events"]))
    for d in r["made"]:
        print("  %s の書類が無かったので作りました" % d)
    for n in r["notes"]:
        print("  %s" % n)
    if not r["made"] and not r["notes"]:
        print("  変わりありません")
    return 0


def cmd_schedule(a):
    from . import schedule
    if a.sched_cmd == "install":
        print(schedule.install_all(a.hour, a.minute, a.every))
        if a.every:
            print("%d分ごとに予定を読み直して、変わっていたらその日の書類を作り直します" % a.every)
        else:
            print("朝の回だけ入れました。日中の反映も要るなら --every 60")
    elif a.sched_cmd == "remove":
        print(schedule.remove(a.what))
    else:
        print(schedule.status())
    return 0


def cmd_update(a):
    from . import update
    try:
        if a.rollback:
            print(update.rollback())
            return 0
        if a.file:
            print(update.from_file(a.file, a.sha256))
            return 0
        if a.check:
            m = update.check(a.manifest or update.MANIFEST_URL)
            print("現在 %s / 配布 %s%s" % (m["current"], m["version"], "（更新あり）" if m["newer"] else ""))
            return 0
        print(update.apply(a.manifest or update.MANIFEST_URL, dry_run=a.dry_run))
    except Exception as e:
        print(e)
        return 1
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="paper-maker", description="書類メーカー 配布版")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("init"); s.add_argument("--force", action="store_true"); s.add_argument("--example", action="store_true", help="見本の設定をそのまま入れる（試す用）"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("doctor"); s.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("ai"); s.add_argument("ai_cmd", nargs="?", choices=["list", "set", "key", "check"], default="check")
    s.add_argument("provider", nargs="?"); s.add_argument("value", nargs="?")
    s.add_argument("--model"); s.add_argument("--endpoint"); s.add_argument("--key-name")
    s.set_defaults(fn=cmd_ai)
    s = sub.add_parser("quest"); s.add_argument("--all", action="store_true", help="全部の道順を説明つきで出す"); s.add_argument("--recheck", action="store_true", help="済んだ分も調べ直す"); s.set_defaults(fn=cmd_quest)
    for name, fn in (("daily", cmd_daily), ("report", cmd_report)):
        s = sub.add_parser(name); s.add_argument("--date"); s.add_argument("--no-pdf", action="store_true"); s.add_argument("--force", action="store_true"); s.add_argument("--base", default="", help="この拠点から出たことにする（呼び名）"); s.set_defaults(fn=fn)
    s = sub.add_parser("note"); s.add_argument("--date"); s.add_argument("--no-open", action="store_true"); s.set_defaults(fn=cmd_note)
    s = sub.add_parser("rules"); s.add_argument("--no-pdf", action="store_true"); s.add_argument("--force", action="store_true", help="名義が見本のままでも出す"); s.set_defaults(fn=cmd_rules)
    s = sub.add_parser("denshi"); s.add_argument("--no-pdf", action="store_true"); s.add_argument("--force", action="store_true", help="名義が見本のままでも出す"); s.set_defaults(fn=cmd_denshi)
    s = sub.add_parser("proposal"); s.add_argument("json_path", help="提案書の中身を書いた JSON"); s.add_argument("--no-pdf", action="store_true"); s.add_argument("--force", action="store_true", help="名義が見本のままでも出す"); s.set_defaults(fn=cmd_proposal)
    s = sub.add_parser("calendar"); s.add_argument("--date"); s.set_defaults(fn=cmd_calendar)
    s = sub.add_parser("fare"); ss = s.add_subparsers(dest="fare_cmd")
    sl = ss.add_parser("list"); sl.add_argument("--ids", action="store_true", help="確定に使う id も出す")
    sa = ss.add_parser("add"); sa.add_argument("frm"); sa.add_argument("to"); sa.add_argument("amount"); sa.add_argument("--transport", default="鉄道"); sa.add_argument("--line", default=""); sa.add_argument("--source", default="")
    sau = ss.add_parser("auto"); sau.add_argument("--apply", action="store_true"); sau.add_argument("--no-ai", action="store_true", help="AIの候補は使わない"); sau.add_argument("--pair", nargs=2, metavar=("出発", "到着"))
    ss.add_parser("stale")
    sg = ss.add_parser("gtfs"); sg.add_argument("--pref", help="都道府県（例: 埼玉）"); sg.add_argument("--word", help="事業者名の一部"); sg.add_argument("--apply", action="store_true"); sg.add_argument("--only", type=int, nargs="+", metavar="番号"); sg.add_argument("--stop", nargs="+", metavar="停留所", help="この停留所に関わる区間だけ入れる"); sg.add_argument("--limit", type=int, default=0, help="入れる区間の上限")
    sc = ss.add_parser("confirm"); sc.add_argument("fare_id"); sc.add_argument("amount"); sc.add_argument("--source", default="")
    sb = ss.add_parser("bulk"); sb.add_argument("--apply", action="store_true"); sb.add_argument("--limit", type=int, default=10, metavar="行き先の数")
    sr = ss.add_parser("routes"); sr.add_argument("frm"); sr.add_argument("to"); sr.add_argument("--again", action="store_true", help="調べ直す")
    sp = ss.add_parser("pick"); sp.add_argument("frm"); sp.add_argument("to"); sp.add_argument("number", type=int)
    si = ss.add_parser("import"); si.add_argument("files", nargs="+"); si.add_argument("--apply", action="store_true"); si.add_argument("--min-times", type=int, default=2)
    s.set_defaults(fn=cmd_fare)
    s = sub.add_parser("auto"); s.add_argument("files", nargs="*", help="自分が過去に出した請求書や見積（省略すると探します）"); s.add_argument("--apply", action="store_true"); s.add_argument("--no-ai", action="store_true"); s.set_defaults(fn=cmd_auto)
    s = sub.add_parser("base"); s.add_argument("base_cmd", nargs="?", choices=["list", "add", "use", "remove"], default="list"); s.add_argument("label", nargs="?"); s.add_argument("address", nargs="?"); s.add_argument("--station", default=""); s.set_defaults(fn=cmd_base)
    s = sub.add_parser("places"); s.add_argument("--forget", metavar="住所の一部"); s.set_defaults(fn=cmd_places)
    s = sub.add_parser("learn"); s.add_argument("files", nargs="+"); s.add_argument("--apply", action="store_true"); s.set_defaults(fn=cmd_learn)
    s = sub.add_parser("knowledge"); s.add_argument("what", nargs="?", choices=["all", "clients", "items", "clauses"], default="all"); s.add_argument("--word"); s.set_defaults(fn=cmd_knowledge)
    s = sub.add_parser("doc"); s.add_argument("json_path"); s.add_argument("pdf_path"); s.set_defaults(fn=cmd_doc)
    s = sub.add_parser("app"); s.add_argument("--no-open", action="store_true"); s.add_argument("--port", type=int, default=8797); s.set_defaults(fn=cmd_app)
    s = sub.add_parser("open"); s.add_argument("--port", type=int, default=8797); s.set_defaults(fn=cmd_open)
    s = sub.add_parser("desktop"); s.add_argument("what", nargs="?", choices=["install", "remove"], default="install"); s.set_defaults(fn=cmd_desktop)
    s = sub.add_parser("sync"); s.add_argument("--no-make", action="store_true", help="取りこぼしの書類を作らない"); s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("schedule"); s.add_argument("sched_cmd", choices=["install", "remove", "status"]); s.add_argument("--hour", type=int, default=6); s.add_argument("--minute", type=int, default=0); s.add_argument("--every", type=int, default=60, metavar="分", help="この間隔で予定を読み直す（最短5分／0で切る）"); s.add_argument("--what", choices=["all", "daily", "sync"], default="all"); s.set_defaults(fn=cmd_schedule)
    s = sub.add_parser("update"); s.add_argument("--check", action="store_true"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--manifest"); s.add_argument("--file", help="落としてきた zip で入れ替える"); s.add_argument("--sha256", default="", help="--file に渡す zip の照合値（あれば）"); s.add_argument("--rollback", action="store_true", help="前の版に戻す"); s.set_defaults(fn=cmd_update)
    s = sub.add_parser("version"); s.set_defaults(fn=lambda a: print(__version__) or 0)

    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return 0
    try:
        return a.fn(a) or 0
    except BadInput as e:
        print(e)
        return 1
    except FileNotFoundError as e:
        print(e)
        return 1
    except KeyboardInterrupt:
        print("\n中断しました")
        return 130


if __name__ == "__main__":
    sys.exit(main())
