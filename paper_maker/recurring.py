"""毎月きまった日に出す請求書を、定期の回で作る。

**作るだけ。送らない。** 相手に届く行為は人が押す。
出来たものを置いておくので、中身を見てから電子契約なりメールなりに載せる。

台帳は ~/.paper-maker/recurring.json。1件がひとつの契約。
"""
import calendar
import datetime as dt
import json

from . import paths, profile as prof_mod


def store():
    return paths.data_dir() / "recurring.json"


def load() -> dict:
    p = store()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"items": []}


def save(d):
    p = store()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add(name, client, amount, day=10, months=12, subject="", note="",
        honorific="御中", address="", email="", start=None, tax_included=True) -> dict:
    """1件足す。amount は税込で受ける（そのほうが口頭の額と一致する）。"""
    d = load()
    row = {"name": name, "client": client, "honorific": honorific,
           "address": address, "email": email,
           "amount": int(amount), "taxIncluded": bool(tax_included),
           "day": max(1, min(28, int(day))), "months": int(months),
           "subject": subject or name, "note": note,
           "start": (start or dt.date.today()).isoformat(),
           "issued": []}
    d["items"] = [x for x in d.get("items", []) if x.get("name") != name] + [row]
    save(d)
    return row


def _net(row):
    """税抜と消費税。口頭で決めた税込の額にぴったり合わせる。"""
    total = int(row["amount"])
    if not row.get("taxIncluded", True):
        return total, round(total * 0.1)
    net = round(total / 1.1)
    return net, total - net


def due_this_month(today: dt.date = None):
    """今日出すべき請求書。出した分はもう出さない。"""
    today = today or dt.date.today()
    out = []
    for row in load().get("items", []):
        if today.day != row["day"]:
            continue
        tag = today.strftime("%Y-%m")
        if tag in row.get("issued", []):
            continue
        start = dt.date.fromisoformat(row["start"])
        months = (today.year - start.year) * 12 + (today.month - start.month)
        if months < 0 or months >= row["months"]:
            continue
        out.append((row, tag, months + 1))
    return out


def mark(name, tag):
    d = load()
    for row in d.get("items", []):
        if row.get("name") == name:
            row.setdefault("issued", []).append(tag)
    save(d)


def build_doc(row, today: dt.date):
    net, tax = _net(row)
    label = "%d年%d月分" % (today.year, today.month)
    subject = "%s（%s）" % (row["subject"], label)
    return {
        "type": "invoice", "issuer": "corp",
        "docNo": "I-%s-%s" % (today.strftime("%Y%m%d"), "001"),
        "date": today.isoformat(), "dueDate": today.isoformat(),
        "clientName": row["client"], "honorific": row.get("honorific") or "御中",
        "clientAddress": row.get("address", ""), "clientEmail": row.get("email", ""),
        "subject": subject,
        "items": [{"name": subject, "qty": 1, "unit": "式", "price": net, "taxRate": 10}],
        "taxMode": "excl", "withholding": False, "showSeal": True,
        "notes": row.get("note", ""),
    }


def run(today: dt.date = None, want_pdf=True) -> dict:
    """今日ぶんを作る。**送らない。**"""
    from . import render
    today = today or dt.date.today()
    prof = prof_mod.load()
    made, names = [], []
    for row, tag, nth in due_this_month(today):
        doc = build_doc(row, today)
        out = prof_mod.output_dir(prof) / today.strftime("%Y/%m")
        out.mkdir(parents=True, exist_ok=True)
        stem = "請求書_%s_%s" % (row["client"][:16], today.isoformat())
        (out / (stem + ".json")).write_text(
            json.dumps({"doc": doc}, ensure_ascii=False, indent=2), encoding="utf-8")
        made.append(str(out / (stem + ".json")))
        if want_pdf and render.app_doc_to_pdf(doc, prof.get("profiles", {}),
                                              out / (stem + ".pdf"), prof.get("browser", ""),
                                              travel=prof.get("travel")):
            made.append(str(out / (stem + ".pdf")))
        mark(row["name"], tag)
        names.append("%s（%d/%d回目）" % (row["name"], nth, row["months"]))
    return {"made": made, "names": names}
