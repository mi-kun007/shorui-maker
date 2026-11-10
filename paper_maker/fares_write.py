"""運賃を1件書き込む。CLI からも、書類作りの途中からも使う。

同じ区間が既にあれば差し替える。増やさない。
どこから来た額か（source）を必ず残す。あとで実費が出てきたら上書きできるように。
"""
import datetime as dt

from . import profile as prof_mod


def _station_id(st: dict, name: str, transport: str) -> str:
    plain = (name or "").rstrip("駅")
    for sid, s in st.items():
        if (s.get("name") or "").rstrip("駅") == plain:
            return sid
    sid = "s%d" % (len(st) + 1)
    while sid in st:
        sid += "x"
    bus = transport in ("バス", "高速バス")
    st[sid] = {"name": name if (name.endswith("駅") or bus) else name + "駅",
               "kind": "bus" if bus else "rail", "pref": ""}
    return sid


KINDS = ("新幹線", "高速バス", "特急", "快速", "地下鉄", "バス")


def kinds_of(lines) -> list:
    """次に同じ区間が出てきた時、どの系統で選ぶか。

    列車名（かがやき506号）まで覚えると、その列車が走らない日に外れる。
    系統だけ残す。どれにも当てはまらない時は、路線名の頭を使う（新快速など）。
    """
    lines = lines or []
    keys = []
    for w in KINDS:
        if any(w in x for x in lines):
            if w == "バス" and "高速バス" in keys:
                continue
            keys.append(w)
    if keys:
        return keys
    return [x.split("・")[0][:6] for x in lines[:1] if x]


def prefer_of(frm: str, to: str):
    """前にその区間で選んだ乗り物。無ければ空。"""
    fares = prof_mod.load_fares()
    st = prof_mod.load_stations().get("stations", {})
    name = {k: (v.get("name") or k).rstrip("駅") for k, v in st.items()}
    a, b = (frm or "").rstrip("駅"), (to or "").rstrip("駅")
    for r in fares.get("fares", []):
        if name.get(r["from"]) == a and name.get(r["to"]) == b:
            return r.get("prefer") or []
    return []


def add(frm: str, to: str, amount: int, transport="鉄道", line="", source="",
        verified=True, routes=None, prefer=None, preset=False) -> dict:
    fares = prof_mod.load_fares()
    stations = prof_mod.load_stations()
    st = stations.setdefault("stations", {})
    f_id = _station_id(st, frm, transport)
    t_id = _station_id(st, to, transport)
    row = {"id": "%s_%s" % (f_id, t_id), "from": f_id, "to": t_id,
           "transport": transport, "line": line or "", "amount": int(amount),
           "verified": bool(verified), "source": source or "利用者登録",
           "checkedAt": dt.date.today().isoformat()}
    if routes:
        # 選ばなかった案も残す。あとで「こっちで行った」と直せるように
        row["routes"] = [{"amount": r["amount"], "minutes": r["minutes"],
                          "lines": r.get("lines") or [], "note": r.get("note", "")}
                         for r in routes]
    if prefer:
        row["prefer"] = list(prefer)
    if preset:
        # はじめから入れておいた分。その人が自分で入れた分と混ぜない
        row["preset"] = True
    fares["fares"] = [r for r in fares.get("fares", [])
                      if not (r["from"] == f_id and r["to"] == t_id)] + [row]
    prof_mod.save_stations(stations)
    prof_mod.save_fares(fares)
    return row
