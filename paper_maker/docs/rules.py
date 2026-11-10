"""旅費規程書。profile.travel から1枚。改定まで固定。"""
import datetime as dt

from .. import render


def _yen(v):
    return "{:,}円".format(int(v))


def build_html(profile: dict) -> str:
    tr = profile.get("travel", {})
    issuer = profile.get("profiles", {}).get(profile.get("defaultIssuer", "corp"), {})
    base = (tr.get("bases") or {}).get(tr.get("currentBase"), {})
    rows = "\n".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (render.esc(role), _yen(r.get("day", 0)), _yen(r.get("night", 0)))
        for role, r in (tr.get("rates") or {}).items())
    lodging = tr.get("lodging", {}) or {}
    mode = lodging.get("mode", "actual_capped")
    if mode == "fixed":
        lod = "宿泊費は1泊につき%sの定額を支給する。" % _yen(lodging.get("amount", 0))
    elif mode == "actual":
        lod = "宿泊費は実費とする。"
    else:
        lod = "宿泊費は実費とし、1泊につき%sを上限とする。" % _yen(lodging.get("cap", 0))
    eff = tr.get("effectiveDate", "")
    try:
        y, m, d = (int(x) for x in eff.split("-"))
        eff_ja = "%d年%d月%d日" % (y, m, d)
    except Exception:
        eff_ja = eff or "（施行日を profile.json に設定）"
    ctx = {
        "company": issuer.get("name", ""),
        "base_label": base.get("label", "本店"),
        "base_address": base.get("address", ""),
        "rate_rows": rows,
        "lodging_sentence": lod,
        "settle_days": tr.get("settleWithinDays", 7),
        "receipt_free": "{:,}".format(int(tr.get("receiptFreeUnder", 30000))),
        "effective_ja": eff_ja,
    }
    return render.fill("rules.html", ctx)
