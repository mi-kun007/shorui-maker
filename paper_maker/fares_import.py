"""交通費の履歴をまとめて取り込む。1区間ずつ手で入れるのは続かない。

入れられる物
  - Suica / PASMO の利用履歴のスクリーンショット（画像）… Gemini に読ませる。鍵が要る
  - 同じ画面を貼り付けたテキスト、CSV、モバイルSuicaの明細

読み取った物をそのまま信じない。同じ区間が複数回、同じ額で出てきた分だけ確定にする。
1回しか出てこない区間は「確認待ち」で入れ、書類には使わない。
額が食い違う区間は取り込まず、両方の額を見せて人に決めさせる。
"""
import re
from collections import defaultdict

from . import itinerary, profile as prof_mod

PROMPT = """この画像は日本の交通系ICカード（Suica/PASMO等）の利用履歴です。
表示されている明細だけを、次のJSONで返してください。画像に無い物は作らないでください。

{"records":[{"date":"YYYY-MM-DD","kind":"rail"または"bus","from":"入場駅名","to":"出場駅名","amount":整数}]}

決まり
- 鉄道は from と to の両方。バスは from に事業者名を入れ、to は空文字
- 金額は運賃だけ。残高やチャージ（入金）の行は入れない
- 物販（コンビニ等）の行は入れない
- 年が画面に無ければ、他の行から分かる年を使う。分からなければ date を空文字にする
- 読み取れない文字があれば、その行は入れない
JSONだけを返してください。"""


def _num(s):
    s = re.sub(r"[^\d]", "", s or "")
    return int(s) if s else None


def parse_text(text: str):
    """貼り付けたテキストや CSV から明細を拾う。読めた行だけ返す。

    拾える形の例
      2026-08-15  鉄道  阿佐ケ谷 → 東京  341
      08/15 阿佐ケ谷 東京 341
      2026/08/15,鉄道,阿佐ケ谷,東京,341
      2026-08-15  バス  日東交通  1600
    """
    out, bad = [], 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.replace("\t", " ").replace("，", ",")
        parts = [p.strip() for p in (line.split(",") if "," in line else line.split()) if p.strip()]
        if len(parts) < 3:
            continue
        m = re.match(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", parts[0]) or re.match(r"^(\d{1,2})[-/](\d{1,2})$", parts[0])
        if not m:
            bad += 1
            continue
        g = m.groups()
        date = "%04d-%02d-%02d" % (int(g[0]), int(g[1]), int(g[2])) if len(g) == 3 else ""
        amount = _num(parts[-1])
        if not amount:
            bad += 1
            continue
        mid = [p for p in parts[1:-1] if not re.fullmatch(r"[-–→>＞]+", p)]
        kind = "rail"
        if mid and mid[0] in ("バス", "bus", "路線バス", "高速バス"):
            kind = "bus"
            mid = mid[1:]
        elif mid and mid[0] in ("鉄道", "rail", "電車"):
            mid = mid[1:]
        mid = [p for p in " ".join(mid).replace("→", " ").replace("＞", " ").split() if p]
        if not mid:
            bad += 1
            continue
        if kind == "bus" or len(mid) == 1:
            out.append({"date": date, "kind": "bus" if kind == "bus" else "rail",
                        "from": mid[0], "to": "" if kind == "bus" else mid[0], "amount": amount})
        else:
            out.append({"date": date, "kind": "rail", "from": mid[0], "to": mid[-1], "amount": amount})
    return out, bad


def read_image(path, api_key: str = "", timeout=120):
    """画像を読ませる。どの接続先かは ~/.paper-maker/ai.json で決まる。"""
    from . import ai
    obj = ai.ask_json(PROMPT, image_path=path, timeout=timeout)
    return [x for x in obj.get("records", []) if x.get("amount")]


def summarize(records, min_times=2):
    """同じ区間をまとめる。確定・確認待ち・食い違い・怪しいの4つに分ける。

    表記ゆれ（空白・小書きのケ）は揃えてから数える。揃えないと同じ駅が2つに割れる。
    同じ駅どうしの鉄道区間は、読み間違いか同一駅の入出場なので運賃にしない。
    """
    groups, names = defaultdict(list), {}
    odd = []
    for r in records:
        frm = (r.get("from") or "").strip()
        to = (r.get("to") or "").strip()
        kind = r.get("kind") or "rail"
        if not frm or (kind == "rail" and not to):
            continue
        nf, nt = itinerary.norm(frm), itinerary.norm(to)
        if kind == "rail" and nf == nt:
            odd.append({"kind": kind, "from": frm, "to": to, "times": 1,
                        "amount": int(r["amount"]), "amounts": [int(r["amount"])],
                        "first": r.get("date") or "", "last": r.get("date") or "",
                        "why": "同じ駅どうし"})
            continue
        key = (kind, nf, "") if kind == "bus" else (kind, nf, nt)
        names.setdefault(key, (frm, to))
        groups[key].append(r)
    sure, wait, clash = [], [], []
    for key, rows in sorted(groups.items(), key=lambda x: -len(x[1])):
        kind = key[0]
        frm, to = names[key]
        amounts = sorted({int(x["amount"]) for x in rows})
        dates = sorted(x.get("date") or "" for x in rows)
        item = {"kind": kind, "from": frm, "to": to or frm, "times": len(rows),
                "amount": amounts[0] if len(amounts) == 1 else None,
                "amounts": amounts,
                "first": dates[0], "last": dates[-1]}
        if len(amounts) > 1:
            clash.append(item)
        elif len(rows) >= min_times:
            sure.append(item)
        else:
            wait.append(item)
    return {"sure": sure, "wait": wait, "clash": clash, "odd": odd}


def apply(summary, label="交通系ICの利用履歴"):
    """確定した分だけ fares.json に入れる。確認待ち・食い違いは入れない。"""
    import datetime as dt
    stations = prof_mod.load_stations()
    fares = prof_mod.load_fares()
    st = stations.setdefault("stations", {})
    rows = fares.setdefault("fares", [])

    def sid(name, kind):
        for k, v in st.items():
            if itinerary.norm(v.get("name", "")) == itinerary.norm(name):
                return k
        k = "s%d" % (len(st) + 1)
        while k in st:
            k += "x"
        st[k] = {"name": name if (kind == "bus" or name.endswith("駅")) else name + "駅",
                 "kind": kind, "pref": ""}
        return k

    added = 0
    today = dt.date.today().isoformat()
    for it in summary["sure"]:
        a = sid(it["from"], it["kind"])
        b = sid(it["to"], it["kind"])
        src = "%s（%s 〜 %s・%d回一致）" % (label, it["first"] or "?", it["last"] or "?", it["times"])
        rows[:] = [r for r in rows if not (r.get("from") == a and r.get("to") == b)]
        rows.append({"id": "%s_%s" % (a, b), "from": a, "to": b,
                     "transport": "バス" if it["kind"] == "bus" else "鉄道", "line": "",
                     "amount": it["amount"], "verified": True, "source": src, "checkedAt": today})
        added += 1
    prof_mod.save_stations(stations)
    prof_mod.save_fares(fares)
    return added
