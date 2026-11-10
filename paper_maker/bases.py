"""拠点（今いる場所）の登録と切り替え。

出張から戻って切り替えを忘れると、その日の移動が丸ごと別の土地から出発したことになる。
だから「登録」と「今どこにいるか」を分けて持つ。

  bases       … 自宅・事務所・実家など。何個でも
  currentBase … そのうち今いる所。ここが行程の起点と終点になる

住所を入れたら最寄駅は自分で引く（AI が繋がっていれば）。分からなければ空のまま置く。
**駅を勝手に作らない。** 空なら交通費が出ないので、そこで気づける。
"""
import re

from . import profile as prof_mod


class BadBase(Exception):
    pass


def _key(label: str, taken) -> str:
    """内部の鍵。日本語の呼び名から作れないので、番号で振る。"""
    base = re.sub(r"[^a-z0-9]", "", (label or "").lower()) or "base"
    if base not in taken:
        return base
    n = 2
    while "%s%d" % (base, n) in taken:
        n += 1
    return "%s%d" % (base, n)


def load(prof=None):
    prof = prof or prof_mod.load()
    tr = prof.get("travel") or {}
    return tr.get("bases") or {}, tr.get("currentBase") or ""


def listing(prof=None):
    """画面と一覧に出す形。今いる所に印を付ける。"""
    bases, cur = load(prof)
    out = []
    for k, b in bases.items():
        out.append({"key": k, "label": b.get("label") or k, "address": b.get("address", ""),
                    "station": b.get("station", ""), "current": k == cur})
    out.sort(key=lambda x: (not x["current"], x["label"]))
    return out


def add(label, address, station="", use=True, ask_ai=True) -> dict:
    """拠点を1つ足す。駅を書かなければ住所から引く。"""
    label = (label or "").strip()
    address = (address or "").strip()
    if not label:
        raise BadBase("呼び名を入れてください（自宅・事務所など）")
    if not address:
        raise BadBase("住所を入れてください。ここから交通費を計算します")
    station = (station or "").strip().rstrip("駅")
    note = ""
    if not station and ask_ai:
        from . import ai, geocode
        if ai.ready():
            got = geocode._ask_both(address)
            station = got["station"] or got["hub"]
            if not got["station"] and got["hub"]:
                note = "歩ける駅が無いので、遠出に使う %s を起点にします" % got["hub"]
    prof = prof_mod.load()
    tr = prof.setdefault("travel", {})
    bases = tr.setdefault("bases", {})
    # 見本の拠点が残っていると、選び間違えた日の移動が丸ごと別の土地から出発する。
    # 人が自分の拠点を入れた時点で落とす（手の入った拠点は残す）
    from .autoset import _is_sample
    for k in [k for k, b in bases.items() if _is_sample(b)]:
        del bases[k]
        if tr.get("currentBase") == k:
            tr["currentBase"] = ""
    # 同じ呼び名があれば上書き。増やさない
    key = next((k for k, b in bases.items() if (b.get("label") or "") == label), None)
    key = key or _key(label, bases)
    bases[key] = {"label": label, "address": address, "station": station}
    if use or not tr.get("currentBase"):
        tr["currentBase"] = key
    prof_mod.save(prof)
    return {"key": key, "label": label, "address": address, "station": station,
            "current": tr["currentBase"] == key, "note": note}


def use(word) -> dict:
    """今いる所を切り替える。呼び名の一部で選べる。"""
    prof = prof_mod.load()
    tr = prof.setdefault("travel", {})
    bases = tr.get("bases") or {}
    w = (word or "").strip()
    hit = [k for k in bases if k == w]
    hit = hit or [k for k, b in bases.items() if w and w in (b.get("label") or "")]
    if not hit:
        raise BadBase("その呼び名の拠点がありません: %s" % w)
    if len(hit) > 1:
        raise BadBase("2つ以上あたりました（%s）。もっと詳しく" %
                      "／".join(bases[k].get("label", k) for k in hit))
    tr["currentBase"] = hit[0]
    prof_mod.save(prof)
    b = bases[hit[0]]
    return {"key": hit[0], "label": b.get("label"), "station": b.get("station", "")}


def remove(word) -> str:
    prof = prof_mod.load()
    tr = prof.setdefault("travel", {})
    bases = tr.get("bases") or {}
    hit = [k for k, b in bases.items() if word == k or (word and word in (b.get("label") or ""))]
    if not hit:
        raise BadBase("その呼び名の拠点がありません: %s" % word)
    if len(bases) <= 1:
        raise BadBase("最後の1つは消せません。先に別の拠点を足してください")
    k = hit[0]
    label = bases[k].get("label", k)
    del bases[k]
    if tr.get("currentBase") == k:
        tr["currentBase"] = next(iter(bases))
        prof_mod.save(prof)
        return "%s を消しました。今いる所は %s に移しました" % (
            label, bases[tr["currentBase"]].get("label", tr["currentBase"]))
    prof_mod.save(prof)
    return "%s を消しました" % label
