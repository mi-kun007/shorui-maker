"""未登録の運賃を自分で調べにいく。ただし勝手に確定はしない。

引ける物と引けない物がはっきり分かれる。
  公共交通オープンデータセンター（ODPT）… 事業者が出している実額。これは確定として扱っていい
      鍵なしで引けるのは都営交通ぶん。無料登録して鍵を入れると東京メトロや私鉄各社も引ける
  Gemini …………………………………… 学習した知識からの答え。**候補どまり**
      JR東日本は 2026-03-14 に運賃改定があった。古い数字を掴んで税務書類に載せるのが一番まずい

だから ODPT 由来だけ verified=true。それ以外は candidates に積んで、人が確定させる。
（新幹線の運賃を二次情報で調べたら、まとめサイトどうしで額が食い違った。実額を待つのが正しい）
"""
import datetime as dt
import json
import urllib.parse
import urllib.request

from . import itinerary, profile as prof_mod

ODPT_PUBLIC = "https://api-public.odpt.org/api/v4/"
ODPT_TOKEN = "https://api.odpt.org/api/v4/"


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "paper-maker"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class Odpt:
    """駅名から運賃を引く。取ってきた表は使い回す。"""

    def __init__(self, token: str = ""):
        self.token = token
        self._stations = None
        self._fares = None

    def _url(self, kind, **params):
        base = ODPT_TOKEN if self.token else ODPT_PUBLIC
        if self.token:
            params["acl:consumerKey"] = self.token
        q = ("?" + urllib.parse.urlencode(params)) if params else ""
        return "%s%s.json%s" % (base, kind, q)

    def stations(self):
        if self._stations is None:
            rows = _get(self._url("odpt:Station"))
            m = {}
            for s in rows:
                name = (s.get("odpt:stationTitle") or {}).get("ja") or s.get("dc:title") or ""
                sid = s.get("owl:sameAs") or s.get("@id")
                if name and sid:
                    m.setdefault(itinerary.norm(name), []).append(sid)
            self._stations = m
        return self._stations

    def fares(self):
        if self._fares is None:
            rows = _get(self._url("odpt:RailwayFare"))
            m = {}
            for r in rows:
                a, b = r.get("odpt:fromStation"), r.get("odpt:toStation")
                amt = r.get("odpt:icCardFare") or r.get("odpt:ticketFare")
                if a and b and amt:
                    m[(a, b)] = int(amt)
            self._fares = m
        return self._fares

    def find(self, frm: str, to: str):
        """(金額, 出所) or None。同じ駅名が複数路線にあるときは、引けた中で一番安い額を採る。"""
        st = self.stations()
        fa = self.fares()
        a_ids = st.get(itinerary.norm(frm), [])
        b_ids = st.get(itinerary.norm(to), [])
        hits = []
        for a in a_ids:
            for b in b_ids:
                if (a, b) in fa:
                    hits.append((fa[(a, b)], a, b))
                elif (b, a) in fa:
                    hits.append((fa[(b, a)], b, a))
        if not hits:
            return None
        amt, a, b = min(hits)
        return amt, "公共交通オープンデータセンター（%s → %s）" % (a.split(":")[-1], b.split(":")[-1])


AI_PROMPT = """次の区間の、日本の鉄道の片道運賃（大人・普通運賃・ICカード）を教えてください。
区間: {frm} → {to}

決まり
- 分からない場合、推測しないで {{"amount": null, "reason": "分からない理由"}} を返す
- 複数の経路がある場合は、最も一般的な経路の運賃
- いつ時点の運賃かを year_month に入れる（例 "2025-04"）
- 事業者名が分かれば operator に入れる

JSONだけを返す: {{"amount": 整数 or null, "operator": "", "year_month": "", "route": "", "reason": ""}}"""


def ai_guess(frm, to, api_key="", timeout=60):
    """候補として聞く。返ってきた額を確定にはしない。"""
    from . import ai
    try:
        obj = ai.ask_json(AI_PROMPT.format(frm=frm, to=to), timeout=timeout)
    except Exception:
        return None
    if not obj.get("amount"):
        return None
    who = ai.load().get("label", "AI")
    return {"amount": int(obj["amount"]),
            "source": "%s（%s %s 時点・要確認）" % (who, obj.get("operator") or "", obj.get("year_month") or ""),
            "route": obj.get("route") or ""}


gemini_guess = ai_guess


def pending_pairs(profile: dict, extra=None):
    """まだ額が決まっていない区間を集める。fares.json の空欄＋呼び出し側が渡した分。"""
    rows = prof_mod.load_fares().get("fares", [])
    stations = prof_mod.load_stations().get("stations", {})
    name = {k: v.get("name", k) for k, v in stations.items()}
    out = []
    for r in rows:
        if r.get("amount") is None:
            out.append((name.get(r["from"], r["from"]), name.get(r["to"], r["to"]), r.get("id")))
    for pair in (extra or []):
        if pair not in [(a, b) for a, b, _ in out]:
            out.append((pair[0], pair[1], None))
    return out


def collect(profile: dict, pairs, odpt_token="", gemini_key=""):
    """区間ごとに調べる。ODPT で引けたら実額、それ以外は候補。"""
    o = Odpt(odpt_token)
    found, guessed, missed = [], [], []
    for frm, to, fid in pairs:
        hit = None
        try:
            hit = o.find(frm, to)
        except Exception:
            hit = None
        if hit:
            found.append({"from": frm, "to": to, "id": fid, "amount": hit[0], "source": hit[1]})
            continue
        if gemini_key:
            try:
                g = gemini_guess(frm, to, gemini_key)
            except Exception:
                g = None
            if g:
                guessed.append({"from": frm, "to": to, "id": fid, **g})
                continue
        missed.append({"from": frm, "to": to, "id": fid})
    return {"found": found, "guessed": guessed, "missed": missed}


def apply(result):
    """ODPT で引けた分だけ確定させる。候補は candidates に積むだけで、書類には出さない。"""
    stations = prof_mod.load_stations()
    fares = prof_mod.load_fares()
    st = stations.setdefault("stations", {})
    rows = fares.setdefault("fares", [])
    today = dt.date.today().isoformat()

    def sid(nm):
        for k, v in st.items():
            if itinerary.norm(v.get("name", "")) == itinerary.norm(nm):
                return k
        k = "s%d" % (len(st) + 1)
        while k in st:
            k += "x"
        st[k] = {"name": nm if nm.endswith("駅") else nm + "駅", "kind": "rail", "pref": ""}
        return k

    n_ok = 0
    for it in result["found"]:
        a, b = sid(it["from"]), sid(it["to"])
        rows[:] = [r for r in rows if not (r.get("from") == a and r.get("to") == b)]
        rows.append({"id": "%s_%s" % (a, b), "from": a, "to": b, "transport": "鉄道", "line": "",
                     "amount": it["amount"], "verified": True, "source": it["source"], "checkedAt": today})
        n_ok += 1
    n_cand = 0
    for it in result["guessed"]:
        a, b = sid(it["from"]), sid(it["to"])
        row = next((r for r in rows if r.get("from") == a and r.get("to") == b), None)
        cand = {"amount": it["amount"], "source": it["source"], "route": it.get("route", ""), "checkedAt": today}
        if row is None:
            row = {"id": "%s_%s" % (a, b), "from": a, "to": b, "transport": "鉄道", "line": "",
                   "amount": None, "verified": False, "source": "", "checkedAt": "", "candidates": []}
            rows.append(row)
        row.setdefault("candidates", [])
        if not any(c.get("amount") == cand["amount"] for c in row["candidates"]):
            row["candidates"].append(cand)
        row["amount"] = None
        row["verified"] = False
        row["note"] = "候補あり。実額を確かめてから使う（paper-maker fare confirm）"
        n_cand += 1
    prof_mod.save_stations(stations)
    prof_mod.save_fares(fares)
    return n_ok, n_cand


def confirm(fare_id: str, amount: int, source: str = ""):
    """候補を実額に格上げする。ここは人が押す。"""
    fares = prof_mod.load_fares()
    for r in fares.get("fares", []):
        if r.get("id") == fare_id:
            r["amount"] = int(amount)
            r["verified"] = True
            r["source"] = source or "利用者が確定"
            r["checkedAt"] = dt.date.today().isoformat()
            r.pop("note", None)
            prof_mod.save_fares(fares)
            return r
    return None
