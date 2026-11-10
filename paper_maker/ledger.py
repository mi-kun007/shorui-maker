"""出来た書類を、あとで見返せる形に控える。

3つ。どれも切れる。設定は profile.json の output。
  dir        … PDF と HTML の置き場（既定 ~/Documents/書類メーカー）
  obsidianDir… 同じ内容の .md を Obsidian の保管庫へ
  sheetCsv   … 1日1行の台帳。Excel でも Google スプレッドシートでも開ける

台帳は追記ではなく差し替え。同じ日を作り直した時に行が増えないように、
日付を鍵にして上から書く。ここを追記にすると、1時間ごとの回で1日24行になる。

UTF-8 に BOM を付ける。付けないと Excel が文字化けする（Windows で確認が要る）。

**= で始まる文字は数式として実行される。** 予定の題名は他人が入れた招待から来ることもある。
「=HYPERLINK(...)」と書かれた予定が1つあれば、台帳を開いた人がそれを踏む。
先頭に ' を足して、文字として置く。
"""
import csv
import pathlib

class LedgerUnavailable(OSError):
    """置き場に手が届かない。書類の作成そのものは止めない。"""


COLUMNS = ["日付", "訪問件数", "交通費", "日当", "合計", "要確認", "行き先", "営業報告書", "出張精算"]


def path_of(prof: dict):
    v = (prof.get("output") or {}).get("sheetCsv") or ""
    return pathlib.Path(v).expanduser() if v else None


def _count(v) -> int:
    """未確定の区間数。書類側は件数（int）で持っている版と、一覧で持っている版がある。"""
    if isinstance(v, int):
        return v
    return len(v or [])


def _safe(v):
    """表計算に数式として食われない形にする。"""
    t = "" if v is None else str(v)
    return "'" + t if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t


def _rows(p: pathlib.Path):
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("日付")]


def write(prof: dict, day, itin: dict, outputs) -> str:
    """その日の1行を書く。既にある日は差し替える。控えないなら空文字を返す。"""
    p = path_of(prof)
    if not p:
        return ""
    events = itin.get("events") or []
    # 書類に載る額と揃える。金額の分からない区間は書類側でも足していない
    fare = int(itin.get("transportTotal") or 0)
    allw = int(itin.get("allowance") or 0)
    places = "／".join(dict.fromkeys(
        e.get("place") or e.get("location") or e.get("title") or "" for e in events if e))
    row = {
        "日付": day.isoformat(),
        "訪問件数": len(events),
        "交通費": fare,
        "日当": allw,
        "合計": fare + allw,
        "要確認": _count(itin.get("unpricedLegs")),
        "行き先": _safe(places)[:200],
        "営業報告書": next((o for o in outputs if "営業報告書" in o and o.endswith(".pdf")), ""),
        "出張精算": next((o for o in outputs if "出張精算" in o and o.endswith(".pdf")), ""),
    }
    try:
        rows = [r for r in _rows(p) if r["日付"] != row["日付"]]
        rows.append({k: row.get(k, "") for k in COLUMNS})
        rows.sort(key=lambda r: r["日付"])
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({k: _safe(r.get(k, "")) for k in COLUMNS})
    except OSError as e:
        # 外付けが刺さっていない・iCloud がまだ降りてきていない・書き込めない。
        # ここで落とすと、その日の書類が1枚も出なくなる。台帳だけ諦める
        raise LedgerUnavailable("台帳に書けませんでした（%s）: %s"
                                % (e.__class__.__name__, p)) from e
    return str(p)
