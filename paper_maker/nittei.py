"""日程調整（TONARY）。相手がリンクから枠を選ぶと、カレンダーに Zoom 付きで入る。

置き場は2つに分かれている。
- 予約ページ：Cloudflare の Worker（相手のスマホから開くので、パソコンの外に要る）
- 空き時間を送る・予約をカレンダーへ書く：パソコン側の常駐アプリ

ここは書類メーカーの画面から、リンク・受付の設定・入った予約を見るための窓口。
設定は ~/.paper-maker/nittei.json。常駐アプリと同じファイルを使うときは PAPER_MAKER_NITTEI_DIR で場所を指す。
"demo": true の設定は通信せず、設定ファイルに書いた見本の予約を出す（見本の会社で試すとき用）。
"""
import json
import os
import pathlib
import urllib.request

from . import paths

FIELDS = ("days", "holidays", "start", "end", "buffer", "noticeHours", "horizonDays")


def home() -> pathlib.Path:
    env = os.environ.get("PAPER_MAKER_NITTEI_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    return paths.data_dir()


def _cfg_path():
    return home() / "nittei.json"


class SettingsError(ValueError):
    """画面にそのまま出す日本語の断り文。"""


def load():
    """設定を読む。無ければ None。壊れていれば SettingsError（英語の生の例外を画面に出さない）。"""
    p = _cfg_path()
    if not p.exists():
        return None
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise SettingsError("日程調整の設定ファイル（%s）が読めません。中身が壊れていないか見てください" % p)
    if not cfg:
        return None
    if not isinstance(cfg, dict) or not isinstance(cfg.get("links", []), list):
        raise SettingsError("日程調整の設定ファイルの形が違います（links の一覧が要ります）")
    return cfg


def _key():
    p = home() / "nittei_key.txt"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _status():
    p = home() / "nittei_status.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    d.pop("calendars", None)
    return d


def _demo(cfg):
    """見本の予約。日付は「今日から何日後」で書いてあるので、いつ開いても先の予定に見える。"""
    import datetime as dt
    jst = dt.timezone(dt.timedelta(hours=9))
    today = dt.datetime.now(jst).date()
    out = []
    for i, b in enumerate(cfg.get("demoBookings") or []):
        try:
            h, m = _split_hm(b.get("at", "10:00"))
            d = today + dt.timedelta(days=int(b.get("inDays", 1)))
        except (ValueError, TypeError, AttributeError):
            continue
        st = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=jst)
        ms = int(st.timestamp() * 1000)
        out.append({"id": "demo%d" % i, "start": ms, "end": ms + int(b.get("minutes", 30)) * 60000,
                    "name": b.get("name", ""), "title": b.get("title", ""), "email": b.get("email", ""),
                    "memo": b.get("memo", ""), "status": "confirmed"})
    return out


def bookings(cfg):
    """入った予約を Worker から取る。鍵が無ければ空。"""
    if cfg and cfg.get("demo"):
        return _demo(cfg), ""
    key = _key()
    if not key or not cfg:
        return [], "鍵がありません（nittei_key.txt）"
    if not cfg.get("endpoint"):
        return [], "予約ページの置き場（endpoint）が設定にありません"
    url = str(cfg["endpoint"]).rstrip("/") + "/agent/bookings"
    # Python 標準の名乗りのままだと Cloudflare に弾かれる（error 1010）
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "User-Agent": "paper-maker"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            got = json.loads(r.read().decode("utf-8")).get("bookings", [])
    except Exception as e:  # 見られないだけで、画面の他は動かす
        return [], "予約を読めませんでした: %s" % e.__class__.__name__
    got.sort(key=lambda b: b.get("start", 0))
    return got, ""


def _split_hm(v):
    """'9:05' → (9, 5)。形が違えば ValueError。"""
    parts = str(v).split(":")
    if len(parts) != 2:
        raise ValueError(v)
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(v)
    return h, m


def _norm_hm(v, label):
    try:
        h, m = _split_hm(v)
    except (ValueError, TypeError):
        raise SettingsError("%sの時刻が読めません（例 10:00）" % label)
    return "%d:%02d" % (h, m)


def _int_in(v, lo, hi, label):
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise SettingsError("%sは数字で入れてください" % label)
    if n != n or n in (float("inf"), float("-inf")):
        raise SettingsError("%sは数字で入れてください" % label)
    n = int(round(n))
    if not lo <= n <= hi:
        raise SettingsError("%sは %d〜%d の間で入れてください" % (label, lo, hi))
    return n


def _bool(v):
    if isinstance(v, str):
        return v.strip().lower() not in ("", "0", "false", "no", "off", "いいえ")
    return bool(v)


def state():
    try:
        cfg = load()
    except SettingsError as e:
        return {"configured": False, "home": str(home()), "error": str(e)}
    if not cfg:
        return {"configured": False, "home": str(home())}
    base = str(cfg.get("endpoint") or "").rstrip("/")
    links = [{"token": l.get("token", ""), "title": l.get("title") or "打ち合わせ", "minutes": l.get("minutes", 30),
              "enabled": l.get("enabled", True), "url": "%s/b/%s" % (base, l.get("token", "")) if base else ""}
             for l in cfg.get("links", []) if isinstance(l, dict)]
    first = next((l for l in cfg.get("links", []) if isinstance(l, dict)), {})
    settings = {
        "days": first.get("days", [1, 2, 3, 4, 5]),
        "holidays": first.get("holidays", True),
        "start": first.get("start", "10:00"), "end": first.get("end", "19:00"),
        "buffer": first.get("buffer", 15), "noticeHours": first.get("noticeHours", 12),
        "horizonDays": first.get("horizonDays", 21),
    }
    bk, err = bookings(cfg)
    return {"configured": True, "demo": bool(cfg.get("demo")), "links": links, "settings": settings, "status": _status(),
            "bookings": bk, "bookingsError": err, "calendar": cfg.get("calendar", "自宅")}


def save_settings(payload):
    """受付の設定を全リンクに当てる。常駐アプリが次の回に読んで Worker へ送る。

    入力はすべて確かめてから書く。1つでもおかしければ、ファイルには触らずに日本語で断る。
    開始だけ・終了だけが来たときは、今の設定の相方と比べる。
    """
    if not isinstance(payload, dict):
        raise SettingsError("送られてきた設定の形が違います")
    cfg = load()
    if not cfg:
        raise SettingsError("日程調整の設定ファイルがありません")
    links = [l for l in cfg.get("links", []) if isinstance(l, dict)]
    cur = links[0] if links else {}
    s = {}
    if "days" in payload:
        days = payload["days"]
        if not isinstance(days, list):
            raise SettingsError("曜日の形が違います")
        try:
            got = {int(x) for x in days}
        except (TypeError, ValueError):
            raise SettingsError("曜日の形が違います")
        if any(not 0 <= d <= 6 for d in got):
            raise SettingsError("曜日の形が違います")
        if not got:
            raise SettingsError("曜日を1つ以上選んでください")
        s["days"] = sorted(got)
    start = _norm_hm(payload["start"], "開始") if "start" in payload else cur.get("start", "10:00")
    end = _norm_hm(payload["end"], "終了") if "end" in payload else cur.get("end", "19:00")
    if "start" in payload or "end" in payload:
        try:
            a, b = _split_hm(start), _split_hm(end)
        except (ValueError, TypeError):
            raise SettingsError("開始と終了の時刻が読めません")
        if a >= b:
            raise SettingsError("終了は開始より後にしてください")
        s["start"], s["end"] = start, end
    for k, lo, hi, label in (("buffer", 0, 240, "前後の余白"), ("noticeHours", 0, 720, "何時間前まで"),
                              ("horizonDays", 1, 90, "何日先まで")):
        if k in payload:
            s[k] = _int_in(payload[k], lo, hi, label)
    if "holidays" in payload:
        s["holidays"] = _bool(payload["holidays"])
    enabled = payload.get("enabled") or {}
    if not isinstance(enabled, dict):
        raise SettingsError("リンクの入り切りの形が違います")
    for l in links:
        l.update(s)
        if l.get("token") in enabled:
            l["enabled"] = _bool(enabled[l["token"]])
    p = _cfg_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)  # 途中で切れたファイルを残さない
    return state()
