"""カレンダーに書いた住所を、駅に結びつける。

ここが通らないと交通費が出ない。
「東京都千代田区丸の内1-1-1」と書いてあっても、運賃表に載っているのは駅名なので、
そのままでは1円も計算できなかった。

一度引いた住所は places.json に書き込んで覚える。同じ客先へ毎週行っても、
AI に聞くのは最初の1回だけ。取引先が10社あっても10回で終わる。

**推測で駅を作らない。** 分からなければ空で返して「要確認」のまま残す。
"""
import datetime as dt

from . import ai, itinerary, profile as prof_mod

PROMPT = """次の住所について、2つ答えてください。

  station … 歩いて行ける最寄り駅。無ければ空文字
  hub ……… その住所から遠出する時に、実際に乗る駅。
            郊外なら市の中心駅（町名しか無い所なら、その市の代表駅）。新幹線や特急が停まる駅

決まり
- 実在する駅だけ。分からなければ空文字にする。**作らない**
- 「駅」の字は付けない（例: 大宮 / 東京 / 阿佐ケ谷）

住所: {addr}

{{"station": "", "hub": ""}}"""


def _ask(addr: str, timeout=120) -> str:
    """訪問先の駅。歩ける駅が無ければ、そこへ行くのに使う駅を返す。"""
    got = _ask_both(addr, timeout)
    return got["station"] or got["hub"]


def _ask_both(addr: str, timeout=120) -> dict:
    """(歩ける最寄駅, 遠出に使う駅)。

    町はずれには歩ける駅が無い。最寄駅だけ聞くと空で返ってきて、
    拠点に駅が入らず交通費が1円も出ない。実際に乗る駅まで聞く。
    """
    try:
        got = ai.ask_json(PROMPT.format(addr=addr), timeout=timeout)
    except Exception:
        return {"station": "", "hub": ""}
    if not isinstance(got, dict):
        return {"station": "", "hub": ""}
    return {"station": str(got.get("station") or "").strip().rstrip("駅"),
            "hub": str(got.get("hub") or "").strip().rstrip("駅")}


def resolve(events, timeout=120) -> dict:
    """場所欄はあるのに駅が分からない予定を拾って、places.json に足す。

    返すのは {"asked": 何件聞いたか, "learned": [(住所, 駅)], "left": まだ分からない件数}
    """
    out = {"asked": 0, "learned": [], "left": 0}
    places = prof_mod.load_places()
    stations = prof_mod.load_stations()
    seen = set()
    for ev in events or []:
        kind, st, _why = itinerary.classify(ev, places, stations)
        loc = (ev.get("location") or "").strip()
        if kind != "unknown" or not loc or loc in seen:
            continue
        seen.add(loc)
        if not ai.ready():
            out["left"] += 1
            continue
        out["asked"] += 1
        got = _ask(loc, timeout)
        if not got:
            out["left"] += 1
            continue
        places.setdefault("rules", []).append({
            "match": [loc], "station": got,
            "note": "住所から引いた %s" % dt.date.today().isoformat()})
        out["learned"].append((loc, got))
    if out["learned"]:
        prof_mod.save_places(places)
    return out
