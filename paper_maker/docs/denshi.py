"""電帳法の事務処理規程を1枚。

電子で請求書を渡すなら、この規程が要る。訂正削除を止める仕組みを持っていない限り、
売上の大小に関わらず求められる（国税庁の一問一答）。

国税庁が法人用のサンプルを配っているので、そこへ社名と施行日を差し込む。
条文の中身は動かさない。**勝手に足したり削ったりしない。**
"""
import datetime as dt

from .. import render


def _ja(d: str) -> str:
    try:
        y, m, dd = (int(x) for x in d.split("-"))
        return "%d年%d月%d日" % (y, m, dd)
    except Exception:
        return d or "（施行日を決めてください）"


def build_html(profile: dict) -> str:
    issuer = profile.get("profiles", {}).get(profile.get("defaultIssuer", "corp"), {})
    e = (profile.get("denshi") or {})
    scope = e.get("scope") or ["電子メールを利用した請求書等の授受",
                              "クラウドサービスを利用した請求書等の授受",
                              "ＥＣサイトを利用した取引",
                              "インターネットバンキングを利用した振込"]
    kanji = "一二三四五六七八九十"
    rows = "<ol>%s</ol>" % "".join(
        "<li>%s　%s</li>" % (kanji[i] if i < len(kanji) else str(i + 1), render.esc(s))
        for i, s in enumerate(scope))
    who = e.get("manager") or issuer.get("rep") or issuer.get("name") or ""
    ctx = {
        "company": issuer.get("name", ""),
        "manager": render.esc(who),
        "handler": render.esc(e.get("handler") or who),
        "scope_rows": rows,
        "store_place": render.esc(e.get("storePlace") or "保存用のフォルダ"),
        "keep_years": int(e.get("keepYears") or 7),
        "effective_ja": _ja(e.get("effectiveDate") or
                            (profile.get("travel") or {}).get("effectiveDate", "")),
    }
    return render.fill("denshi.html", ctx)
