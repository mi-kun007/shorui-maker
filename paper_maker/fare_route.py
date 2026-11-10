"""区間の運賃を、経路検索から引く。

**配布版では既定で切ってある。** 乗換案内サイトの規約は、
プログラムからの取得（BOT）と、対価を受ける目的での利用を禁じている。
月額をもらって配る道具の中で自動取得すると、そこに当たる。

代わりに、利用者が自分のブラウザで開いて、自分の目で見た額を入れる形にした。
人が見る分は普通の使い方なので、規約に触れない。search_url() がその窓口。

ここを自分で使う人（自分だけで回す人）は profile.json の travel.lookupFares を true に。
その判断はその人のもの。既定では動かさない。

これまでは実際に払った額（Suica の履歴）しか確定にしていなかった。
そのぶん、初めて行く土地は「★要確認」のまま残り、精算書の実費計が埋まらなかった。

経路検索は、事業者が公表している運賃をそのまま出す。推測ではない。
だから **どこから取ったか（サイト名と日付）を必ず控える。** 控えずに数字だけ置くのが一番まずい。

取れない物もある。
  高速バスの乗り場、社名だけの停留所 … 駅として引けない
  乗換案内に無い区間 …………………… 空で返す。埋めない

**新幹線や特急に乗った日は、額が変わる。** ここで入るのは経路検索の既定の運賃なので、
実際に払った額（領収書・Suica）が出てきたら、そちらで上書きする。
"""
import datetime as dt
import re
import urllib.parse
import urllib.request

SEARCH = "https://transit.yahoo.co.jp/search/result"
SOURCE = "経路検索"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _when(day: dt.date = None):
    """平日の朝9時で引く。深夜に叩くと、終電後の遠回りが1件目に出る。

    実測 2026-08-20：夜に地方の駅→東京を引いたら 15時間32分・乗換7回の夜行経路が出た。
    """
    d = day or dt.date.today()
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def search_url(frm: str, to: str, day: dt.date = None) -> str:
    """利用者のブラウザで開くための道。**ここでは取りに行かない。**"""
    d = _when(day)
    q = {"from": frm, "to": to, "type": "1", "ticket": "ic",
         "y": d.year, "m": "%02d" % d.month, "d": "%02d" % d.day,
         "hh": "09", "m1": "0", "m2": "0",
         "shin": "1", "ex": "1", "hb": "1", "lb": "1", "sr": "1", "al": "1", "s": "0"}
    return SEARCH + "?" + urllib.parse.urlencode(q)


def _fetch(frm: str, to: str, day: dt.date = None, timeout=40) -> str:
    d = _when(day)
    # 乗り物を全部許す。既定のままだと新幹線が外れて、地方の駅→東京が
    # 10時間56分・乗換6回・9,620円で返ってきた（実測 2026-08-20）。
    # 新幹線を入れると 2時間29分・14,600円。仕事で使うのは後者
    q = {"from": frm, "to": to, "type": "1", "ticket": "ic",
         "y": d.year, "m": "%02d" % d.month, "d": "%02d" % d.day,
         "hh": "09", "m1": "0", "m2": "0",
         "shin": "1", "ex": "1", "hb": "1", "lb": "1", "sr": "1", "al": "1", "s": "0"}
    url = SEARCH + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


SLOWER_OK = 1.5
FLIGHT = ("便", "空港線ＡＮＡ", "ＡＮＡ", "ＪＡＬ", "スカイマーク", "ジェットスター",
          "ピーチ", "ソラシド", "スターフライヤー", "航空")


def _is_flight(route) -> bool:
    body = " ".join(route.get("lines") or [])
    return any(w in body for w in FLIGHT)


def _lines(seg: str):
    """その案で乗る物。徒歩は落とす。"""
    out = []
    for raw in re.findall(r'class="transport"(.{0,140})', seg):
        name = _plain(raw).lstrip(">").split("<")[0].strip()
        name = re.sub(r"^[>\s]+", "", name)
        if not name or name.startswith("徒歩"):
            continue
        if name not in out:
            out.append(name[:40])
    return out


def _routes(html: str):
    """出てきた案を全部拾う。乗る物の名前まで。"""
    got = []
    starts = [m.start() for m in re.finditer(r'class="routeSummary"', html)]
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else i + 9000
        seg = html[i:end]
        head = _plain(seg[:1800])
        fm = re.search(r"IC優先：([\d,]+)円", head) or re.search(r"([\d,]+)円", head)
        if not fm:
            continue
        tm = re.search(r"(\d+)時間(\d+)分", head)
        minutes = int(tm.group(1)) * 60 + int(tm.group(2)) if tm else 0
        if not minutes:
            t1 = re.search(r"(\d+)分", head)
            minutes = int(t1.group(1)) if t1 else 0
        cm = re.search(r"乗換：(\d+)回", head)
        note = "乗換%s回" % cm.group(1) if cm else ""
        bm = re.search(r"（乗車券([\d,]+)円 特別料金([\d,]+)円）", head)
        if bm:
            note = (note + " 乗車券%s+特急%s" % (bm.group(1), bm.group(2))).strip()
        got.append({"minutes": minutes, "amount": int(fm.group(1).replace(",", "")),
                    "note": note, "lines": _lines(seg)})
    return got


def _matches(route, want) -> bool:
    """前に選んだ乗り物と同じ系統か。「新幹線」「高速バス」など一言で見る。"""
    if not want:
        return True
    body = " ".join(route.get("lines") or []) + " " + route.get("note", "")
    return any(w and w in body for w in want)


def _pick(routes, prefer=None):
    """安いほうを選ぶ。ただし、極端に遠回りなら選ばない。

    全部の乗り物を許すと、東京→横浜で特急を使う案が1位に来た（528円 → 1,288円）。
    2分速くするために760円払う人はいない。
    かといって一番安い案を機械的に選ぶと、地方の駅→東京が
    10時間56分・9,620円の在来線乗り継ぎになる。仕事では乗らない。
    だから「一番速い案の1.5倍の時間まで」の中で、一番安い案を選ぶ。
    """
    routes = [r for r in routes if r["amount"] > 0]
    if not routes:
        return None
    # 飛行機が挟まる案は取らない。
    # 同じ名前の駅が他の土地にもあると、向こうの駅と結ばれて空路が出る。
    # 実測：那覇空港 → 県庁前 で神戸の県庁前と結ばれ、43,690円になった（2026-08-21）
    want_air = any("飛行" in w or "空路" in w for w in (prefer or []))
    if not want_air:
        ground = [r for r in routes if not _is_flight(r)]
        if ground:
            routes = ground
    # 前に「この乗り物で行った」と決めてあれば、それを最優先する
    liked = [r for r in routes if _matches(r, prefer)] if prefer else []
    pool = liked or routes
    times = [r["minutes"] for r in pool if r["minutes"]]
    fastest = min(times) if times else 0
    ok = [r for r in pool
          if not fastest or not r["minutes"] or r["minutes"] <= fastest * SLOWER_OK]
    return min(ok or pool, key=lambda r: r["amount"])


def lookup(frm: str, to: str, day: dt.date = None, timeout=40, prefer=None) -> dict:
    """1区間。候補を全部返して、そのうち1つを選ぶ。**推測しない。**

    prefer に「新幹線」「高速バス」などを渡すと、それを含む案の中から選ぶ。
    在来線の乗り継ぎで10時間かけて行く人はいない。前に選んだ乗り物を覚えておいて渡す。
    """
    out = {"from": frm, "to": to, "amount": 0, "route": "", "minutes": 0,
           "source": "", "note": "", "routes": [], "picked": -1}
    try:
        html = _fetch(frm, to, day, timeout)
    except Exception as e:
        out["note"] = "引けませんでした（%s）" % e.__class__.__name__
        return out
    routes = _routes(html)
    out["routes"] = routes
    pick = _pick(routes, prefer)
    if not pick:
        out["note"] = "経路が見つかりませんでした"
        return out
    if _is_flight(pick):
        out["routes"] = routes
        out["note"] = ("陸路が見つからず、空路になりました。"
                       "同じ名前の駅が他の土地にもあるかもしれません。"
                       "「%s[県名]」のように書き直してみてください" % to)
        return out
    out["picked"] = routes.index(pick)
    out["minutes"], out["amount"] = pick["minutes"], pick["amount"]
    out["route"] = "／".join(pick["lines"]) or pick["note"]
    out["source"] = "%s %s" % (SOURCE, dt.date.today().isoformat())
    return out


def lookup_many(pairs, day: dt.date = None, pause=1.5, timeout=40):
    """まとめて。相手のサーバを叩き続けないよう、1件ごとに間を置く。"""
    import time
    out = []
    for n, (a, b) in enumerate(pairs):
        if n:
            time.sleep(pause)
        out.append(lookup(a, b, day, timeout))
    return out
