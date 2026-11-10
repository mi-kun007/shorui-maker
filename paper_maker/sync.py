"""1時間ごとに回って、予定が変わっていたら書類を作り直す。

翌朝まで待たない。午前に商談を1件足したら、次の回で今日の報告書に入っている。

やること
  1. 今日と前日のカレンダーを読み直す
  2. 前と比べて変わっていたら、その日の書類を作り直す
  3. 前日ぶんがまだ無ければ、そこで作る（朝の回が流れた日の取りこぼし）
  4. 運賃の鮮度を見る。改定より前の額を使っていたら記録に残す
  5. 週に1回、更新の有無だけ見る

**変わっていない日は触らない。** 予定が同じなら PDF も作り直さない。
毎時走るので、ここで毎回 PDF を焼くと Chrome が1時間おきに立ち上がる。

覚えているのは予定の指紋（sha256 の頭16桁）だけ。予定名も場所も残さない。
ログにも日付と件数しか書かない。
"""
import datetime as dt
import hashlib
import json

from . import calendars, freshness, guard, paths, profile as prof_mod

STATE = "sync.json"


def _state_path():
    return paths.data_dir() / STATE


def load_state():
    p = _state_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def save_state(st):
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _mark(events) -> str:
    """予定の指紋。時刻・題名・場所・メモが変わったら別の値になる。"""
    body = json.dumps(
        [[e.get("start", ""), e.get("end", ""), e.get("title", ""),
          e.get("location", ""), e.get("note", "")] for e in events],
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


MAX_RETRY = 3
RETRY_WORDS = ("駅に結びつかない", "AI に繋がらない", "PDF 化できません", "台帳に書けませんでした")


def _complete(result) -> bool:
    """その日の書類が、あとで直る見込みの無い形で出来ているか。

    「名義が見本のまま」は人が直す所なので、作り直しても変わらない。数えない。
    「AI に繋がらない」「駅に結びつかない」は、繋がれば直る。次の回でやり直す。
    """
    return not any(w in warn for warn in result.get("warnings", []) for w in RETRY_WORDS)


def _log(msg):
    p = paths.log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write("%s sync %s\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def run(now: dt.datetime = None, make_missing=True, check_update=True) -> dict:
    with guard.only_one("sync") as got:
        if not got:
            return {"at": (now or dt.datetime.now()).isoformat(timespec="seconds"),
                    "events": 0, "made": [], "stale": 0,
                    "notes": ["前の回がまだ動いているので、今回は何もしませんでした"]}
        guard.roll_log()
        return _run(now, make_missing, check_update)


def _run(now: dt.datetime = None, make_missing=True, check_update=True) -> dict:
    now = now or dt.datetime.now()
    today = now.date()
    yesterday = today - dt.timedelta(days=1)
    prof = prof_mod.load()
    st = load_state()
    out = {"at": now.isoformat(timespec="seconds"), "events": 0, "made": [], "stale": 0, "notes": []}

    calendars.clear_cache()
    by_day, warns = calendars.events_for_range(prof, yesterday, 2)
    out["events"] = sum(len(v) for v in by_day.values())
    out["notes"] += warns

    # 今日と前日。予定が変わっていたら作り直す
    if make_missing:
        from . import daily as daily_mod
        marks = st.setdefault("marks", {})
        for day in (yesterday, today):
            key = day.isoformat()
            events = by_day.get(key) or []
            if not events:
                continue
            _h, _pdf, js = daily_mod.out_paths(prof, day, "営業報告書")
            mark = _mark(events)
            tries = int(st.setdefault("retries", {}).get(key, 0))
            if js.exists() and marks.get(key) == mark and tries >= MAX_RETRY:
                continue        # 予定も前のまま。やり直しの回数も使い切っている
            if js.exists() and marks.get(key) == mark and tries == 0:
                continue        # 前の回でちゃんと出来ている
            r = daily_mod.run(day, prof)
            if r["skipped"]:
                continue
            out["made"].append(key)
            marks[key] = mark
            if _complete(r):
                st["retries"][key] = 0
            else:
                # AI に繋がらない回で作った書類は、住所が駅にならず交通費が抜ける。
                # 繋がるようになったら直したい。ただし何度も繰り返さない。
                # ブラウザが無い人はいつまでも PDF が作れないので、回数で止める
                st["retries"][key] = tries + 1
                if tries + 1 < MAX_RETRY:
                    out["notes"].append("%s は次の回でもう一度作り直します（%s）"
                                        % (key, r["warnings"][0][:36]))
                else:
                    out["notes"].append("%s は %d 回やり直しても揃いませんでした（%s）"
                                        % (key, MAX_RETRY, r["warnings"][0][:36]))
        # 一昨日より前の指紋は捨てる（際限なく溜めない）
        keep = {yesterday.isoformat(), today.isoformat()}
        st["marks"] = {k: v for k, v in marks.items() if k in keep}
        st["retries"] = {k: v for k, v in st.get("retries", {}).items() if k in keep}

    # 毎月きまった日の請求書。作るだけで、送らない
    try:
        from . import recurring
        rec = recurring.run(today)
        if rec["names"]:
            out["notes"].append("定期の請求書を作りました: %s" % "／".join(rec["names"]))
            out["made"] += rec["made"][:1]
    except Exception as e:
        out["notes"].append("定期の請求書でつまずきました: %s" % e.__class__.__name__)

    fr = freshness.check(today)
    out["stale"] = len(fr["old"])
    if fr["old"]:
        out["notes"].append("運賃 %d 区間が改定より前の額です（paper-maker fare stale）" % len(fr["old"]))

    if check_update:
        last = st.get("updateCheckedAt", "")
        if last[:10] != today.isoformat() and today.weekday() == 0:   # 月曜だけ
            try:
                from . import update as up
                m = up.check()
                st["updateCheckedAt"] = now.isoformat(timespec="seconds")
                if m.get("newer"):
                    out["notes"].append("新しい版があります（%s → %s）: paper-maker update" % (m["current"], m["version"]))
            except Exception:
                pass

    st["lastSyncAt"] = out["at"]
    st["lastEvents"] = out["events"]
    save_state(st)
    _log("events=%d made=%d stale=%d" % (out["events"], len(out["made"]), out["stale"]))
    return out
