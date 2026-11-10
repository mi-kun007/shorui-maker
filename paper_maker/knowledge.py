"""これまでに作った書類を取り込んで、次の書類に効かせる。

一人でやっていると、去年の契約書も、前回の見積も、フォルダのどこかにある。
毎回それを開いて写している。その写す作業を消す。

放り込めるもの
  契約書  … 条項をひな型として残す。次の契約書で差し込める
  見積・請求 … 取引先（宛名・住所）と、品目と単価。次の見積で候補に出る
  そのほか … 読んで分類できなければ、そのまま控えるだけ

**読み取った物をそのまま正にしない。** 取り込む前に何が入るか見せて、押させる。
単価は「前はこの額だった」であって、次もその額とは限らない。
"""
import datetime as dt
import hashlib
import json
import pathlib
import re

from . import paths

KINDS = ("契約書", "見積書", "請求書", "領収書", "そのほか")

PROMPT = """この書類を読んで、次の JSON だけを返してください。

決まり
- **書いていないことは絶対に足さない。** 空なら空文字にする
- 金額は数字だけ（カンマや円は入れない）
- 日付は YYYY-MM-DD。年が分からなければ空文字
- 相手先は、こちらではなく取引先のほう
- メールアドレスは書いてあるものだけ。作らない

{{
  "kind": "契約書" か "見積書" か "請求書" か "領収書" か "そのほか",
  "title": "書類の題名",
  "date": "",
  "client": {{"name": "取引先の名前", "address": "", "email": "", "honorific": "御中 か 様"}},
  "items": [{{"name": "品目", "qty": 1, "unit": "式", "price": 0}}],
  "total": 0,
  "clauses": [{{"heading": "第1条（目的）", "body": "本文"}}],
  "terms": {{"payment": "支払条件", "delivery": "納期", "period": "契約期間"}},
  "note": "気づいたこと（あれば）"
}}

契約書でなければ clauses は空配列。見積・請求でなければ items は空配列。"""


def store_path():
    return paths.data_dir() / "knowledge.json"


def files_dir():
    return paths.data_dir() / "knowledge"


def load() -> dict:
    p = store_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"docs": [], "clients": [], "items": [], "clauses": []}


def save(d: dict):
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fingerprint(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def read_one(path, timeout=180) -> dict:
    """1つ読む。中身の判定は AI にさせる。読めなければ例外。"""
    from . import ai
    p = pathlib.Path(path).expanduser()
    if p.suffix.lower() in (".txt", ".md", ".csv"):
        text = p.read_text(encoding="utf-8", errors="replace")[:20000]
        got = ai.ask_json(PROMPT + "\n\n書類の中身:\n\"\"\"\n" + text + "\n\"\"\"", timeout=timeout)
    else:
        got = ai.ask_json(PROMPT, image_path=str(p), timeout=timeout)
    got["source"] = p.name
    got.setdefault("kind", "そのほか")
    if got["kind"] not in KINDS:
        got["kind"] = "そのほか"
    return got


def summarize(results) -> dict:
    """取り込む前に見せるための、まとめ。"""
    clients, items, clauses = [], [], []
    for r in results:
        c = (r.get("client") or {})
        if c.get("name"):
            clients.append({"name": c["name"], "address": c.get("address", ""),
                            "email": c.get("email", ""),
                            "honorific": c.get("honorific") or "御中", "from": r.get("source", "")})
        for it in (r.get("items") or []):
            if it.get("name"):
                items.append({"name": it["name"], "unit": it.get("unit") or "式",
                              "price": int(it.get("price") or 0), "date": r.get("date", ""),
                              "client": c.get("name", ""), "from": r.get("source", "")})
        for cl in (r.get("clauses") or []):
            if cl.get("heading") and cl.get("body"):
                clauses.append({"heading": cl["heading"], "body": cl["body"],
                                "title": r.get("title", ""), "from": r.get("source", "")})
    return {"docs": results, "clients": clients, "items": items, "clauses": clauses}


def _same(a, b, keys):
    return all((a.get(k) or "") == (b.get(k) or "") for k in keys)


def apply(sm: dict, raw_files=None) -> dict:
    """控えに入れる。同じ物は増やさない。取り込んだ原本も残す。"""
    d = load()
    today = dt.date.today().isoformat()
    added = {"docs": 0, "clients": 0, "items": 0, "clauses": 0}

    for r in sm["docs"]:
        r["takenAt"] = today
        d["docs"].append(r)
        added["docs"] += 1
    for c in sm["clients"]:
        if not any(_same(c, x, ("name",)) for x in d["clients"]):
            d["clients"].append(c)
            added["clients"] += 1
        else:
            for x in d["clients"]:
                if x["name"] != c["name"]:
                    continue
                for f in ("address", "email"):
                    if not x.get(f) and c.get(f):
                        x[f] = c[f]
    for it in sm["items"]:
        if not any(_same(it, x, ("name", "client")) and x.get("price") == it.get("price") for x in d["items"]):
            d["items"].append(it)
            added["items"] += 1
    for cl in sm["clauses"]:
        if not any(_same(cl, x, ("heading",)) for x in d["clauses"]):
            d["clauses"].append(cl)
            added["clauses"] += 1

    if raw_files:
        fd = files_dir()
        fd.mkdir(parents=True, exist_ok=True)
        for name, blob in raw_files:
            fp = fd / ("%s_%s" % (_fingerprint(blob), pathlib.Path(name).name))
            if not fp.exists():
                fp.write_bytes(blob)
    save(d)
    return added


# ---------- 次の書類に効かせる ----------

def clients() -> list:
    return load().get("clients", [])


def find_client(word: str):
    w = (word or "").strip()
    if not w:
        return None
    for c in clients():
        if w in c["name"]:
            return c
    return None


def item_prices(name_part: str = "") -> list:
    """品目の単価の履歴。新しい順。次の見積で「前はいくらだったか」を見るため。"""
    rows = load().get("items", [])
    if name_part:
        rows = [r for r in rows if name_part in r["name"]]
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def contract_body(headings=None) -> str:
    """控えた条項を並べて、契約書の本文にする。"""
    cl = load().get("clauses", [])
    if headings:
        cl = [c for c in cl if c["heading"] in headings]
    return "\n\n".join("%s\n%s" % (c["heading"], c["body"]) for c in cl)
