"""予定を仕分けて、行程と運賃と日当を組み立てる。

推測で金額を埋めない。分からない区間は amount=None のまま「要確認」で出す。
"""
import re


def norm(name: str) -> str:
    """駅名の表記ゆれを吸収して比べる。

    実データ（Suica履歴の画像読み取り）で出た違い：
      「JR浦和」と「JR 浦和」…… 空白の有無
      「阿佐ケ谷」と「阿佐ヶ谷」… 小書きのケ
    ここを揃えないと、同じ駅が2つに割れて運賃が引けなくなる。
    """
    import unicodedata
    s = unicodedata.normalize("NFKC", name or "")
    s = re.sub(r"[\s　]+", "", s)
    s = s.replace("ヶ", "ケ").replace("ヵ", "カ")
    return re.sub(r"駅$", "", s.strip())


class Fares:
    def __init__(self, stations: dict, fares: dict):
        self.raw_stations = stations
        st = stations.get("stations", {})
        self.name_of = {sid: s["name"] for sid, s in st.items()}
        self.id_of = {}
        for sid, s in st.items():
            self.id_of[norm(s["name"])] = sid
            self.id_of[norm(sid)] = sid
        self.rows = fares.get("fares", [])

    def sid(self, station):
        return self.id_of.get(norm(station))

    def find(self, frm, to):
        a, b = self.sid(frm), self.sid(to)
        if not a or not b:
            return None
        for r in self.rows:
            if r.get("amount") is None or not r.get("verified"):
                continue
            if r["from"] == a and r["to"] == b:
                return dict(r, reversed=False)
        for r in self.rows:
            if r.get("amount") is None or not r.get("verified"):
                continue
            if r["from"] == b and r["to"] == a:
                return dict(r, reversed=True)
        return None

    def find_via(self, frm, to, hubs):
        for h in hubs:
            if norm(h) in (norm(frm), norm(to)):
                continue
            a = self.find(frm, h)
            b = self.find(h, to)
            if a and b:
                return [(frm, h, a), (h, to, b)]
        return None


def classify(ev: dict, places: dict, stations: dict = None, title_match=False):
    """(種別 onsite/online/unknown, 駅名 or None, 理由)

    places.json の表を先に見る。当たらなければ、運賃表に入っている駅名でも探す。
    履歴を取り込むと駅が増えるので、手で表を書き足さなくても拾える範囲が広がる。

    **予定の題名から駅名を拾うのは既定で切ってある。** title_match=True で入る。
    「東京の友人と飲み」が現地扱いになり、交通費と日当5,000円の付いた
    出張精算が出た（利用者の報告 2026-08-23）。
    はじめから入っている運賃に東京・新宿・渋谷・横浜が居るので、誰の所でも起きる。
    行った先は場所欄で判断する。題名は当てにしない。
    """
    loc = ev.get("location", "") or ""
    title = ev.get("title", "") or ""
    for rule in places.get("rules", []):
        for m in rule.get("match", []):
            if m and m in loc:
                return "onsite", rule.get("station"), "場所欄の「%s」" % m
    for w in places.get("skip", []):
        if w and (w in loc or w in title):
            return "online", None, "「%s」が入っている" % w
    # 表も、既定では場所欄だけに当てる。
    # 見本に入っていた地名（新宿区/新宿 など）が題名に当たって、
    # 「新宿で美容院」が現地扱いになり日当が付いた（2026-08-23）。
    # 題名にも当てたい行は、その行に "title": true と書く。
    for rule in places.get("rules", []):
        if not (rule.get("title") or title_match):
            continue
        for m in rule.get("match", []):
            if m and m in title:
                return "onsite", rule.get("station"), "タイトルの「%s」" % m
    # 運賃表に入っている駅名で探す。長い名前から見る（「東京」より「東京テレポート」を先に）
    known = sorted(((s.get("name") or "").rstrip("駅") for s in (stations or {}).get("stations", {}).values()),
                   key=len, reverse=True)
    # 都道府県の頭を落としてから探す。
    # 「東京都新宿区西新宿」を頭から見ると東京に当たってしまい、新宿へ行った日が
    # 東京へ行ったことになる。市区町村のほうが行った先に近い
    loc_body = re.sub(r"^(東京都|北海道|(?:京都|大阪)府|[^\s]{2,3}県)", "", loc)
    for nm in known:
        if len(nm) < 2:
            continue
        if nm in loc_body:
            return "onsite", nm, "場所欄の「%s」（運賃表の駅）" % nm
    for nm in known:
        if len(nm) >= 2 and nm in loc:
            return "onsite", nm, "場所欄の「%s」（運賃表の駅）" % nm
    if title_match:
        for nm in known:
            if len(nm) < 2:
                continue
            if nm in title:
                return "onsite", nm, "タイトルの「%s」（運賃表の駅）" % nm

    if loc:
        return "unknown", None, "場所欄はあるが駅に結びつかない: %s" % loc[:40]
    return "online", None, "場所の手がかりが無い"


def build(events, profile: dict, places: dict, fares: Fares, base_id=None):
    """1日分の予定 → 仕分け・行程・運賃・日当。

    base_id を渡すと、その拠点から組み立てる。渡さなければ今いる拠点。
    過去の日を作り直す時に「今いる拠点」で組むと、
    その日は博多から出たのに大阪発の紙が出る。だから作った日の拠点を覚えておいて渡す。
    """
    tr = profile.get("travel", {})
    if base_id and base_id not in (tr.get("bases") or {}):
        base_id = None
    base_id = base_id or tr.get("currentBase")
    base = (tr.get("bases") or {}).get(base_id, {})
    rate = (tr.get("rates") or {}).get(tr.get("role"), {"day": 0, "night": 0})
    hubs = tr.get("hubs", [])

    judged = []
    stations_tbl = getattr(fares, "raw_stations", None)
    title_match = bool(tr.get("matchTitleStations", False))
    for e in events:
        kind, station, why = classify(e, places, stations_tbl, title_match)
        if kind == "onsite" and not station:
            kind, why = "unknown", "場所は当たったが駅が未設定"
        judged.append(dict(e, kind=kind, station=station, why=why))
    onsite = [j for j in judged if j["kind"] == "onsite"]
    unknown = [j for j in judged if j["kind"] == "unknown"]

    legs, warnings = [], []
    if onsite:
        if not base.get("station"):
            warnings.append("拠点の最寄駅が未設定です（profile.json travel.bases）")
        seq = [base.get("station", "")] + [j["station"] for j in onsite] + [base.get("station", "")]
        seq = [s for s in seq if s]
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            if norm(a) == norm(b):
                continue
            hit = fares.find(a, b)
            if hit:
                legs.append({"from": a, "to": b, "transport": hit.get("transport", ""),
                             "amount": hit["amount"], "source": hit.get("source", ""), "note": ""})
                continue
            split = fares.find_via(a, b, hubs)
            if split:
                for f2, t2, h2 in split:
                    legs.append({"from": f2, "to": t2, "transport": h2.get("transport", ""),
                                 "amount": h2["amount"], "source": h2.get("source", ""),
                                 "note": "%s→%s を乗り継ぎで分けた" % (a, b)})
                continue
            legs.append({"from": a, "to": b, "transport": "", "amount": None, "source": "", "note": "運賃が未登録"})
            warnings.append("%s → %s の運賃が入っていません（道順6で乗換案内の画面を落とすか、手で入れてください）" % (a, b))
    for j in unknown:
        warnings.append("「%s」の場所を判定できません（%s）" % (j["title"], j["why"]))

    # 全部の区間が未登録なら、拠点の置き場所を疑う。
    # 出張から戻って currentBase を戻し忘れると、その日の移動が丸ごと別の土地から出発したことになる。
    if legs and all(l["amount"] is None for l in legs):
        warnings.append("移動が全部「運賃が未登録」です。今いる拠点が %s のままで合っていますか"
                        "（画面の道順3で選び直せます）" % (base.get("label") or base_id or "未設定"))

    known = sum(l["amount"] for l in legs if l["amount"] is not None)
    missing = sum(1 for l in legs if l["amount"] is None)
    allowance = rate.get("day", 0) if onsite else 0
    return {
        "base": {"id": base_id, "label": base.get("label", ""), "station": base.get("station", ""),
                 "address": base.get("address", "")},
        "role": tr.get("role", ""),
        "events": judged,
        "legs": legs,
        "baseKey": base_id or "",
        "baseLabel": base.get("label", ""),
        "transportTotal": known,
        "unpricedLegs": missing,
        "allowance": allowance,
        "total": known + allowance,
        "warnings": warnings,
        "needsReview": bool(warnings),
        "hasOnsite": bool(onsite),
    }
