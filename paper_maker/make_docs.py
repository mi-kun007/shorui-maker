"""貼った文章から、書類を作る。

名刺の文字、メールの本文、電話で聞いた走り書き。形が揃っていなくていい。
最後に「この内容で契約書と請求書を作って」と書いてあれば、その2枚を出す。

**書いていない金額を作らない。** 分からない欄は空で出して、何が足りないかを返す。
署名する紙なので、埋まっているように見えるのが一番まずい。

控え（knowledge）に同じ相手が居れば住所を補い、契約書の本文には控えた条項を差し込む。
"""
import datetime as dt
import re

from . import ai, knowledge

KINDS = {"見積書": "estimate", "請求書": "invoice", "領収書": "receipt",
         "契約書": "contract", "出張報告書": "travel"}

PROMPT = """次の文章から、作る書類を組み立ててください。

決まり
- **書いていないことは作らない。** 分からない欄は空文字か 0 のままにする
- 金額は数字だけ（カンマや円は入れない）
- 頼まれた書類の種類だけ返す。書かれていなければ、内容から妥当な1枚を選ぶ
- 相手が会社なら honorific は「御中」、個人名なら「様」

返す形
{{
  "docs": [
    {{
      "kind": "見積書|請求書|領収書|契約書|出張報告書",
      "clientName": "",
      "honorific": "御中",
      "clientAddress": "",
      "clientEmail": "",
      "subject": "件名",
      "items": [{{"name": "", "qty": 1, "unit": "式", "price": 0}}],
      "cTitle": "業務委託契約書",
      "cAmount": 0,
      "cBody": "",
      "notes": ""
    }}
  ],
  "missing": ["足りない情報を日本語で。無ければ空配列"]
}}

文章:
\"\"\"
{text}
\"\"\""""


def _clean_docs(got: dict) -> dict:
    out = {"docs": [], "missing": []}
    if not isinstance(got, dict):
        return out
    for d in (got.get("docs") or []):
        kind = str(d.get("kind") or "").strip()
        t = KINDS.get(kind)
        if not t:
            continue
        items = []
        for it in (d.get("items") or []):
            nm = str(it.get("name") or "").strip()
            if not nm:
                continue
            try:
                price = int(float(it.get("price") or 0))
            except (TypeError, ValueError):
                price = 0
            try:
                qty = float(it.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            items.append({"name": nm, "qty": qty, "unit": str(it.get("unit") or "式"),
                          "price": max(0, price), "taxRate": 10})
        doc = {"type": t,
               "clientName": str(d.get("clientName") or "").strip(),
               "honorific": str(d.get("honorific") or "御中").strip(),
               "clientAddress": str(d.get("clientAddress") or "").strip(),
               "clientEmail": str(d.get("clientEmail") or "").strip(),
               "subject": str(d.get("subject") or "").strip(),
               "items": items or [{"name": "", "qty": 1, "unit": "式", "price": 0, "taxRate": 10}],
               "notes": str(d.get("notes") or "").strip(),
               "kindLabel": kind}
        if t == "contract":
            doc["cTitle"] = str(d.get("cTitle") or "業務委託契約書").strip()
            try:
                doc["cAmount"] = int(float(d.get("cAmount") or 0))
            except (TypeError, ValueError):
                doc["cAmount"] = 0
            doc["cBody"] = str(d.get("cBody") or "")
        out["docs"].append(doc)
    out["missing"] = [str(x) for x in (got.get("missing") or []) if str(x).strip()]
    return out


def _fill_from_notes(doc: dict) -> list:
    """控えから補う。補った分を言葉で返す。"""
    said = []
    name = doc.get("clientName")
    if name and not doc.get("clientAddress"):
        c = knowledge.find_client(name)
        if c and c.get("address"):
            doc["clientAddress"] = c["address"]
            said.append("控えから %s の住所を入れました" % name)
    if doc["type"] == "contract" and not doc.get("cBody"):
        body = knowledge.contract_body()
        if body:
            doc["cBody"] = body
            said.append("控えた条項を差し込みました（%d 文字）" % len(body))
    for it in doc.get("items", []):
        if it.get("name") and not it.get("price"):
            hist = knowledge.item_prices(it["name"])
            if hist:
                said.append("「%s」は前回 %s円でした（今回は空のままです）"
                            % (it["name"], "{:,}".format(hist[0]["price"])))
    return said


def _short(doc: dict) -> list:
    """このままでは署名できない欄。"""
    bad = []
    if not doc.get("clientName"):
        bad.append("相手先の名前")
    if doc["type"] in ("estimate", "invoice"):
        if not any(int(i.get("price") or 0) for i in doc.get("items", [])):
            bad.append("金額")
        if not any((i.get("name") or "").strip() for i in doc.get("items", [])):
            bad.append("品目")
    if doc["type"] == "contract" and not doc.get("cAmount"):
        bad.append("契約金額")
    return bad


def build(text: str, timeout=180) -> dict:
    """貼った文章 → 書類の下書き。作らない・足さない。"""
    if not (text or "").strip():
        return {"docs": [], "missing": ["何も書かれていません"], "notes": []}
    got = ai.ask_json(PROMPT.format(text=text[:20000]), timeout=timeout)
    out = _clean_docs(got)
    notes = []
    for d in out["docs"]:
        notes += _fill_from_notes(d)
        short = _short(d)
        if short:
            d["short"] = short
            out["missing"].append("%s: %s が空です" % (d["kindLabel"], "／".join(short)))
    out["notes"] = notes
    out["at"] = dt.datetime.now().isoformat(timespec="seconds")
    return out
