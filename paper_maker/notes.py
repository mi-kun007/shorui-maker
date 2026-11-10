"""その日の営業メモ。カレンダーから雛形を作り、埋めた分を報告書に流し込む。

手ぶらのメモ帳を出しても書けない。訪問先の名前と時刻を先に並べておくと、
あとは商談の中身だけ書けばいい。埋まっていない欄は空のまま出す。埋めない。
"""
import datetime as dt
import re

from . import paths

HEAD = "# %s の営業メモ\n"
FIELDS = ("話したこと", "次にやること")


def note_path(day: dt.date):
    return paths.notes_dir() / ("%s.md" % day.isoformat())


def _slug(ev: dict) -> str:
    """見出しに使う1行。時刻＋件名。ここを鍵にして報告書へ戻す。"""
    t = "終日" if ev.get("all_day") else (ev.get("start") or "")
    return ("%s %s" % (t, ev.get("title", ""))).strip()


def build_template(day: dt.date, events) -> str:
    """当日の訪問先を見出しにした雛形。オンラインの予定も入れる（商談は現地とは限らない）。"""
    lines = [HEAD % day.isoformat()]
    visits = [e for e in events if e.get("kind") in ("onsite", "unknown") or not e.get("kind")]
    if not visits:
        visits = list(events)
    for e in visits:
        lines.append("## %s" % _slug(e))
        loc = e.get("location") or ""
        if loc:
            lines.append("<!-- %s -->" % loc)
        for f in FIELDS:
            lines.append("%s: " % f)
        lines.append("")
    lines.append("## 所感")
    lines.append("")
    return "\n".join(lines)


def ensure(day: dt.date, events) -> tuple:
    """雛形が無ければ作る。あれば触らない。(パス, 作ったか)"""
    p = note_path(day)
    if p.exists():
        return p, False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build_template(day, events), encoding="utf-8")
    return p, True


def parse(day: dt.date) -> dict:
    """メモを読んで {見出し: {話したこと, 次にやること, 本文}} と所感に分ける。

    書式どおりでなくても拾えるようにする。`## 見出し` で切って、
    `話したこと:` のような行があればその欄に、無ければ本文としてまとめる。
    """
    p = note_path(day)
    if not p.exists():
        return {"visits": {}, "free": "", "raw": ""}
    raw = p.read_text(encoding="utf-8")
    if "## " not in raw:
        # 見出しの無いメモは、丸ごと所感として扱う。
        # 雛形を使わずに直接書く人もいる。書いた物を落とさない。
        body = "\n".join(l for l in raw.splitlines() if not l.startswith("# ")).strip()
        return {"visits": {}, "free": body, "raw": raw}
    visits, free, cur, buf = {}, [], None, []

    def flush():
        if cur is None:
            return
        body = "\n".join(buf).strip()
        item = {f: "" for f in FIELDS}
        rest = []
        for line in body.splitlines():
            m = re.match(r"^\s*(%s)\s*[:：]\s*(.*)$" % "|".join(FIELDS), line)
            if m:
                item[m.group(1)] = m.group(2).strip()
            elif line.strip().startswith("<!--"):
                continue
            elif line.strip():
                rest.append(line.strip())
        item["本文"] = "\n".join(rest)
        if cur == "所感":
            free.append(body if not any(item[f] for f in FIELDS) else item["本文"])
        elif any(item[f] for f in FIELDS) or item["本文"]:
            visits[cur] = item
    for line in raw.splitlines():
        if line.startswith("## "):
            flush()
            cur, buf = line[3:].strip(), []
        elif line.startswith("# "):
            continue
        else:
            buf.append(line)
    flush()
    return {"visits": visits, "free": "\n".join(x for x in free if x).strip(), "raw": raw}


def attach(events, parsed: dict):
    """予定1件ずつにメモを貼る。見出しが一致しなければ、件名だけでも合わせにいく。"""
    visits = parsed.get("visits", {})
    by_title = {}
    for k, v in visits.items():
        by_title.setdefault(re.sub(r"^\S+\s+", "", k), v)
    for e in events:
        m = visits.get(_slug(e)) or by_title.get(e.get("title", ""))
        e["memo"] = m or None
    return events
