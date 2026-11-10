"""ICS（iCalendar）を読む。標準ライブラリだけ。

対応：VEVENT の DTSTART/DTEND（日時・終日）、TZID / UTC(Z)、行の折り返し、エスケープ、
RRULE の DAILY / WEEKLY(BYDAY) / MONTHLY(同日) / YEARLY(同月日) と COUNT / UNTIL / INTERVAL、EXDATE。
それ以外の RRULE は展開せず、warnings に「展開できなかった」を残す。推測で予定を作らない。
"""
import datetime as dt
import re
import urllib.request
import zoneinfo

_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def read_source(path_or_url: str, timeout=30) -> str:
    if path_or_url.startswith(("http://", "https://")):
        req = urllib.request.Request(path_or_url, headers={"User-Agent": "paper-maker"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    import pathlib
    from . import paths
    p = pathlib.Path(path_or_url).expanduser()
    if not p.is_absolute():
        p = paths.data_dir() / p          # 相対パスは ~/.paper-maker 基準
    return p.read_text(encoding="utf-8", errors="replace")


def _unfold(text: str):
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(s: str) -> str:
    return (s.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\"))


def _parse_line(line: str):
    """'NAME;PARAM=V;PARAM2=V2:value' -> (name, {params}, value)"""
    if ":" not in line:
        return None
    # パラメータ内の引用符に : が入ることがあるので、引用符の外の最初の : で切る
    inq = False
    for i, ch in enumerate(line):
        if ch == '"':
            inq = not inq
        elif ch == ":" and not inq:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return None
    parts = head.split(";")
    name = parts[0].upper()
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return name, params, value


def _parse_dt(value: str, params: dict, default_tz: str):
    """戻り値: (datetime or date, all_day: bool)"""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return dt.date(int(value[:4]), int(value[4:6]), int(value[6:8])), True
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)", value)
    if not m:
        raise ValueError("日時を読めません: %s" % value)
    y, mo, d, hh, mm, ss, z = m.groups()
    naive = dt.datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss))
    local = zoneinfo.ZoneInfo(default_tz)
    if z:
        return naive.replace(tzinfo=dt.timezone.utc).astimezone(local), False
    tzid = params.get("TZID")
    if tzid:
        try:
            return naive.replace(tzinfo=zoneinfo.ZoneInfo(tzid)).astimezone(local), False
        except Exception:
            pass  # 知らない TZID はローカル扱い
    return naive.replace(tzinfo=local), False


def parse(text: str, default_tz="Asia/Tokyo"):
    """VEVENT を辞書のリストに。展開はしない（expand_for_day でやる）。"""
    events, cal_name = [], ""
    cur = None
    for line in _unfold(text):
        parsed = _parse_line(line)
        if not parsed:
            continue
        name, params, value = parsed
        if name == "X-WR-CALNAME":
            cal_name = _unescape(value)
        elif name == "BEGIN" and value.upper() == "VEVENT":
            cur = {"uid": "", "summary": "", "location": "", "description": "",
                   "start": None, "end": None, "all_day": False, "rrule": None,
                   "exdates": [], "tz": default_tz}
        elif name == "END" and value.upper() == "VEVENT" and cur is not None:
            if cur["start"] is not None:
                if cur["end"] is None:
                    cur["end"] = cur["start"] + (dt.timedelta(days=1) if cur["all_day"] else dt.timedelta(0))
                events.append(cur)
            cur = None
        elif cur is None:
            continue
        elif name == "UID":
            cur["uid"] = value
        elif name == "SUMMARY":
            cur["summary"] = _unescape(value)
        elif name == "LOCATION":
            cur["location"] = _unescape(value)
        elif name == "DESCRIPTION":
            cur["description"] = _unescape(value)
        elif name == "DTSTART":
            cur["start"], cur["all_day"] = _parse_dt(value, params, default_tz)
        elif name == "DTEND":
            cur["end"], _ = _parse_dt(value, params, default_tz)
        elif name == "RRULE":
            cur["rrule"] = dict(kv.split("=", 1) for kv in value.split(";") if "=" in kv)
        elif name == "EXDATE":
            for v in value.split(","):
                try:
                    cur["exdates"].append(_parse_dt(v, params, default_tz)[0])
                except ValueError:
                    pass
    for e in events:
        e["calendar"] = cal_name
    return events


def _same_day(a, day: dt.date) -> bool:
    return (a.date() if isinstance(a, dt.datetime) else a) == day


def _occurs_on(ev: dict, day: dt.date, warnings: list) -> bool:
    """繰り返し規則を見て、その日に発生するか。展開できない規則は False + warning。"""
    start = ev["start"]
    sday = start.date() if isinstance(start, dt.datetime) else start
    if day < sday:
        return False
    for x in ev["exdates"]:
        if _same_day(x, day):
            return False
    r = ev["rrule"]
    freq = r.get("FREQ", "").upper()
    interval = int(r.get("INTERVAL", "1") or 1)
    count = int(r["COUNT"]) if r.get("COUNT") else None
    until = None
    if r.get("UNTIL"):
        try:
            u = _parse_dt(r["UNTIL"], {}, ev["tz"])[0]
            until = u.date() if isinstance(u, dt.datetime) else u
        except ValueError:
            until = None
    if until and day > until:
        return False

    if freq == "DAILY":
        n = (day - sday).days
        if n % interval:
            return False
        idx = n // interval
    elif freq == "WEEKLY":
        bydays = [d for d in r.get("BYDAY", "").split(",") if d] or [list(_WEEKDAYS)[sday.weekday()]]
        wds = sorted(_WEEKDAYS[d[-2:]] for d in bydays if d[-2:] in _WEEKDAYS)
        if day.weekday() not in wds:
            return False
        # 週の番号（開始日の週を0）
        week0 = sday - dt.timedelta(days=sday.weekday())
        wk = (day - dt.timedelta(days=day.weekday()) - week0).days // 7
        if wk % interval:
            return False
        # 何回目か：開始週の中で開始曜日以降の分を数える
        idx = 0
        for w in range(0, wk + 1):
            for wd in wds:
                d2 = week0 + dt.timedelta(days=w * 7 + wd)
                if d2 < sday:
                    continue
                if d2 == day:
                    break
                idx += 1
            else:
                continue
            break
    elif freq == "MONTHLY":
        if r.get("BYDAY"):
            warnings.append("「%s」の繰り返し（毎月第n曜日）は展開できません" % ev["summary"])
            return False
        if day.day != sday.day:
            return False
        months = (day.year - sday.year) * 12 + (day.month - sday.month)
        if months % interval:
            return False
        idx = months // interval
    elif freq == "YEARLY":
        if (day.month, day.day) != (sday.month, sday.day):
            return False
        years = day.year - sday.year
        if years % interval:
            return False
        idx = years // interval
    else:
        warnings.append("「%s」の繰り返し規則（%s）は展開できません" % (ev["summary"], freq or "不明"))
        return False
    if count is not None and idx >= count:
        return False
    return True


def expand_for_day(events, day: dt.date, warnings=None):
    """その日に発生する予定だけを、表示用の辞書で返す。"""
    if warnings is None:
        warnings = []
    out = []
    for ev in events:
        start, end = ev["start"], ev["end"]
        if ev["rrule"]:
            if not _occurs_on(ev, day, warnings):
                continue
            # その日の時刻に付け替える
            if ev["all_day"]:
                start, end = day, day + (end - ev["start"])
            else:
                delta = end - start
                start = dt.datetime.combine(day, start.timetz())
                end = start + delta
        else:
            if ev["all_day"]:
                if not (start <= day < end):
                    continue
            else:
                if start.date() != day:
                    continue
        out.append({
            "calendar": ev.get("calendar", ""),
            "date": day.isoformat(),
            "start": "" if ev["all_day"] else start.strftime("%H:%M"),
            "end": "" if ev["all_day"] else end.strftime("%H:%M"),
            "all_day": ev["all_day"],
            "title": ev["summary"],
            "location": ev["location"],
            "note": ev["description"],
        })
    out.sort(key=lambda e: (not e["all_day"], e["start"]))
    return out
