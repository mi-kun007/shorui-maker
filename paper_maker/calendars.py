"""カレンダーの取り口をまとめる。標準は ICS。macOS のカレンダー.app はオプション。"""
import datetime as dt
import json
import subprocess
import sys

from . import ics

_MAC_SCRIPT = '''
set d1 to date "{y}年{m}月{d}日 0:00:00"
set d2 to d1 + {days} * days
set txt to ""
tell application "Calendar"
  repeat with i from 1 to count of calendars
    set c to calendar i
    set cn to name of c
    if cn is not in {{{skip}}} then
      try
        set evs to (every event of c whose start date >= d1 and start date < d2)
        repeat with e in evs
          set loc to ""
          try
            set loc to location of e
          end try
          if loc is missing value then set loc to ""
          set des to ""
          try
            set des to description of e
          end try
          if des is missing value then set des to ""
          set sd to start date of e
          set ed to end date of e
          set txt to txt & cn & tab & ((year of sd as text) & "-" & text -2 thru -1 of ("0" & (month of sd as integer)) & "-" & text -2 thru -1 of ("0" & (day of sd))) & tab & (time string of sd) & tab & (time string of ed) & tab & (summary of e) & tab & loc & tab & (des) & linefeed
        end repeat
      end try
    end if
  end repeat
end tell
return txt
'''


def _hhmm(s: str) -> str:
    """AppleScript の time string（例 '16:00:00' / '4:00:00 PM'）を HH:MM に。読めなければそのまま。"""
    s = s.strip()
    for fmt in ("%H:%M:%S", "%I:%M:%S %p", "%H:%M"):
        try:
            return dt.datetime.strptime(s, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return s


def _from_macos(start: dt.date, days: int, skip_names, warnings):
    """まとめて取る。1日ずつ osascript を叩くと、この Mac では1回25秒かかった（実測 2026-08-19）。
    30日ぶんを1日ずつ見に行くと15分近くかかり、道順の確認が返ってこなくなる。"""
    if sys.platform != "darwin":
        warnings.append("macOS 以外なのでカレンダー.app は読めません")
        return {}
    skip = ", ".join('"%s"' % s for s in skip_names)
    src = _MAC_SCRIPT.format(y=start.year, m=start.month, d=start.day, days=days, skip=skip)
    try:
        r = subprocess.run(["osascript", "-e", src], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        why = str(e).strip().replace("\n", " ")[:200] or "詳細なし"
        warnings.append(
            "カレンダー.app を読めませんでした: %s: %s" % (e.__class__.__name__, why))
        return {}
    if r.returncode != 0:
        detail = (r.stderr or "").strip().replace("\n", " ")[:200] or "詳細なし"
        warnings.append(
            "カレンダー.app を読めませんでした（osascript 終了コード %s: %s）" % (r.returncode, detail))
        return {}
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        cal, day_s, st, et, title, loc = parts[:6]
        note = parts[6] if len(parts) > 6 else ""
        out.setdefault(day_s, []).append(
            {"calendar": cal, "date": day_s, "start": _hhmm(st), "end": _hhmm(et),
             "all_day": False, "title": title, "location": loc, "note": note})
    return out


_cache = {}


def clear_cache():
    _cache.clear()


def events_for_range(profile: dict, start: dt.date, days: int):
    """start から days 日ぶんをまとめて読む。{日付: [予定]} と警告を返す。

    取り口ごとに1回だけ読む。同じ範囲を続けて聞かれたら覚えている分を返す。
    """
    cal = profile.get("calendar", {})
    tz = cal.get("timezone", "Asia/Tokyo")
    skip = cal.get("skipCalendars", [])
    sources = cal.get("sources", [])
    key = (json.dumps(sources, sort_keys=True, ensure_ascii=False), start.isoformat(), days)
    if key in _cache:
        return _cache[key]

    warnings = []
    by_day = {(start + dt.timedelta(days=i)).isoformat(): [] for i in range(days)}
    if not sources:
        warnings.append("カレンダーの取り口が設定されていません（profile.json の calendar.sources）")
    for s in sources:
        t = s.get("type")
        try:
            if t in ("ics", "url"):
                loc = s.get("path") or s.get("url") or ""
                parsed = ics.parse(ics.read_source(loc), tz)
                for i in range(days):
                    d = start + dt.timedelta(days=i)
                    for e in ics.expand_for_day(parsed, d, warnings):
                        if e["calendar"] in skip:
                            continue
                        if s.get("name") and not e["calendar"]:
                            e["calendar"] = s["name"]
                        by_day[d.isoformat()].append(e)
            elif t == "macos":
                got = _from_macos(start, days, skip, warnings)
                for k, v in got.items():
                    by_day.setdefault(k, []).extend(v)
            else:
                warnings.append("知らないカレンダー種別: %s" % t)
        except FileNotFoundError:
            warnings.append("ICS が見つかりません: %s" % (s.get("path") or s.get("url")))
        except Exception as e:  # 取り口1つの失敗で全部止めない
            warnings.append("カレンダー「%s」を読めませんでした: %s" % (s.get("name", t), e.__class__.__name__))
    for v in by_day.values():
        v.sort(key=lambda e: (not e["all_day"], e["start"]))
    # 警告は同じ物が範囲ぶん並ぶので1回にまとめる
    seen, uniq = set(), []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    _cache[key] = (by_day, uniq)
    return _cache[key]


def events_for_day(profile: dict, day: dt.date):
    """その日の予定を時刻順で返す。(events, warnings)"""
    by_day, warnings = events_for_range(profile, day, 1)
    return by_day.get(day.isoformat(), []), warnings
