"""ご提案書。JSON 1枚から表紙・本文・締めの3構成で出す。

見積書と違って中身は案件ごとに変わる。数字も文章も JSON に書いた物しか出さない。
ここで文章を作ったり、書いていない実績を足したりはしない。
"""
import datetime as dt

from .. import render


def _date_ja(s: str) -> str:
    """2026-08-30 → 2026年8月30日。読めなければそのまま返す。"""
    try:
        y, m, d = (int(x) for x in str(s).split("-"))
        return "%d年%d月%d日" % (y, m, d)
    except Exception:
        return str(s or "")


def _items_html(items) -> str:
    out = []
    for it in items or []:
        name = render.esc(it.get("name", ""))
        body = render.esc(it.get("body", ""))
        out.append('<li><div class="name">%s</div><div>%s</div></li>' % (name, body))
    return "\n".join(out)


def _price_html(price) -> str:
    if not price:
        return ""
    was = price.get("normal", "")
    now = price.get("now", "")
    note = price.get("note", "")
    parts = ['<div class="special">']
    if was:
        parts.append('<div class="was">通常価格　%s</div>' % render.esc(was))
    parts.append('<div class="now">%s</div>' % render.esc(now))
    if note:
        parts.append('<div class="note">%s</div>' % render.esc(note))
    parts.append("</div>")
    return "\n".join(parts)


def _sections_html(sections) -> str:
    """1セクション＝1ページ。lead → items → price の順で組む。"""
    pages = []
    for sec in sections or []:
        buf = ['<div class="page">']
        buf.append("<h2>%s</h2>" % render.esc(sec.get("heading", "")))
        if sec.get("lead"):
            buf.append("<p>%s</p>" % render.esc(sec["lead"]))
        for blk in sec.get("blocks", []) or []:
            if blk.get("heading"):
                buf.append("<h3>%s</h3>" % render.esc(blk["heading"]))
            if blk.get("body"):
                buf.append("<p>%s</p>" % render.esc(blk["body"]))
            if blk.get("items"):
                buf.append('<ul class="track">%s</ul>' % _items_html(blk["items"]))
        if sec.get("items"):
            buf.append('<ul class="track">%s</ul>' % _items_html(sec["items"]))
        if sec.get("price"):
            buf.append(_price_html(sec["price"]))
        buf.append("</div>")
        pages.append("\n".join(buf))
    return "\n\n".join(pages)


def build_html(profile: dict, data: dict) -> str:
    issuer_key = data.get("issuer") or profile.get("defaultIssuer", "corp")
    issuer = (profile.get("profiles", {}) or {}).get(issuer_key, {}) or {}

    closing = data.get("closing", {}) or {}
    closing_html = "\n".join(
        "<p>%s</p>" % render.esc(p) for p in (closing.get("paragraphs") or []))

    # 肩書きは profile の rep に入っている事が多い。二重に出さない。
    rep_line = "　".join(
        x for x in (issuer.get("repTitle") or "", issuer.get("rep") or "") if x)
    # 空欄は行ごと出さない（空行が残ると宛先に渡す紙として格好が付かない）
    contact_html = "<br>".join(
        render.esc(x) for x in
        (issuer.get("address") or "", issuer.get("tel") or "", issuer.get("email") or "") if x)

    ctx = {
        "client": data.get("client", ""),
        "honorific": data.get("honorific", "様"),
        "contact": data.get("contact", ""),
        "title": data.get("title", "ご提案書"),
        "catch": data.get("catch", ""),
        "date_ja": _date_ja(data.get("date") or dt.date.today().isoformat()),
        "sections_html": _sections_html(data.get("sections")),
        "closing_heading": closing.get("heading", "おわりに"),
        "closing_html": closing_html,
        "next_action": data.get("nextAction", ""),
        "issuer": issuer.get("name", ""),
        "rep_line": rep_line,
        "contact_html": contact_html,
    }
    return render.fill("proposal.html", ctx)
