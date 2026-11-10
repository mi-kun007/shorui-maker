"""プロファイル（会社・名義・日当・拠点・出力先）の読み書きと初回ウィザード。"""
import json
import pathlib
import shutil
import sys

from . import paths


def _load_json(p: pathlib.Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _dump_json(p: pathlib.Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def exists() -> bool:
    return paths.profile_path().exists()


def load() -> dict:
    p = paths.profile_path()
    if not p.exists():
        raise FileNotFoundError(
            "プロファイルがありません。先に `paper-maker init` を実行してください（%s）" % p)
    prof = _load_json(p)
    prof.setdefault("profiles", {})
    prof.setdefault("travel", {})
    prof.setdefault("calendar", {"sources": []})
    prof.setdefault("report", {})
    prof.setdefault("output", {})
    return prof


def save(prof: dict):
    _dump_json(paths.profile_path(), prof)


def load_places() -> dict:
    p = paths.places_path()
    return _load_json(p) if p.exists() else {"skip": [], "rules": []}


def save_places(obj):
    _dump_json(paths.places_path(), obj)


def load_stations() -> dict:
    p = paths.stations_path()
    return _load_json(p) if p.exists() else {"stations": {}}


def load_fares() -> dict:
    p = paths.fares_path()
    return _load_json(p) if p.exists() else {"fares": []}


def save_fares(obj):
    _dump_json(paths.fares_path(), obj)


def save_stations(obj):
    _dump_json(paths.stations_path(), obj)


LABELS = {"name": "会社名", "rep": "代表者", "address": "住所", "tel": "電話",
          "email": "メール", "bank": "振込先", "sealText": "判子の文字",
          "invoiceNo": "登録番号"}


def sample_issuer(prof: dict) -> str:
    """出す名義に見本が残っていたら、どの欄かを返す。良ければ空文字。

    欄は埋まっているので、判定を「入っているか」でやると通ってしまう。
    通した先に出るのは、見本の会社名と見本の口座が載った請求書。
    どの欄が見本かまで言わないと、直す場所が分からない。
    """
    from .autoset import _is_sample
    pr = (prof.get("profiles") or {}).get(prof.get("defaultIssuer", "corp")) or {}
    bad = [LABELS.get(k, k) for k, v in pr.items() if v and _is_sample({k: v})]
    return "／".join(bad)


def output_dir(prof: dict) -> pathlib.Path:
    d = prof.get("output", {}).get("dir") or "~/Documents/書類メーカー"
    return pathlib.Path(d).expanduser()


def ensure_data_files():
    """雛形（places/fares/stations）が無ければ examples からコピー。profile は触らない。"""
    d = paths.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in ("places", "fares", "stations"):
        dst = d / (name + ".json")
        if not dst.exists():
            shutil.copy(paths.EXAMPLES / (name + ".example.json"), dst)
    _seed_preset()


def _seed_preset():
    """主要な駅どうしの運賃を、はじめから入れておく。

    まっさらな人が最初に見る画面で、移動が全部「★要確認」なのは寂しい。
    ただし入れるのは誰でも通る所だけ。誰かの生活圏が分かる区間は入れない。
    """
    from . import fares_write
    pre = paths.EXAMPLES / "fares.preset.json"
    if not pre.exists():
        return
    have = {(r.get("from"), r.get("to")) for r in load_fares().get("fares", [])}
    try:
        rows = _load_json(pre).get("fares", [])
    except (ValueError, OSError):
        return
    seeded = paths.data_dir() / ".preset-done"
    if seeded.exists():
        return
    for r in rows:
        try:
            fares_write.add(r["from"], r["to"], int(r["amount"]),
                            transport=r.get("transport", "鉄道"),
                            source="はじめから入っている分 2026-08-21", preset=True)
        except Exception:
            continue
    seeded.write_text("ok", encoding="utf-8")
    paths.notes_dir().mkdir(exist_ok=True)


# ---------- ウィザード ----------

def _ask(prompt, default=""):
    s = input("%s%s: " % (prompt, (" [%s]" % default) if default else "")).strip()
    return s or default


def blank() -> dict:
    """見本の形のまま、会社の中身だけ空にした設定。

    アイコンから初めて押した人はこれで始まる。画面から埋めてもらう。
    見本の会社名が入ったまま請求書が出ると事故になるので、名前と口座は必ず空にする。
    """
    d = _load_json(paths.EXAMPLES / "profile.example.json")
    d.pop("_note", None)
    for who in ("corp", "personal"):
        for k in ("name", "rep", "address", "tel", "email", "invoiceNo", "bank", "sealText"):
            d["profiles"][who][k] = ""
    d["travel"]["bases"]["hq"]["label"] = ""
    d["travel"]["bases"]["hq"]["address"] = ""
    d["travel"]["bases"]["hq"]["station"] = ""
    d["calendar"]["sources"] = []
    d["report"]["author"] = ""
    return d


def ensure_exists() -> bool:
    """設定が無ければ空の物を作る。作ったら True。"""
    if exists():
        return False
    ensure_data_files()
    save(blank())
    return True


def wizard(non_interactive=False):
    """初回セットアップ。対話で会社情報を聞き、profile.json を作る。
    non_interactive=True なら見本をそのままコピー（テスト・デモ用）。"""
    ensure_data_files()
    example = _load_json(paths.EXAMPLES / "profile.example.json")
    example.pop("_note", None)
    if non_interactive:
        save(example)
        return example

    print("書類メーカーの初回設定です。あとから ~/.paper-maker/profile.json を直接直せます。")
    print("空欄でよければそのまま Enter。\n")
    corp = example["profiles"]["corp"]
    corp["name"] = _ask("会社名（屋号）", "")
    corp["rep"] = _ask("代表者（例: 代表取締役　山田 太郎）", "")
    corp["address"] = _ask("住所", "")
    corp["tel"] = _ask("電話", "")
    corp["email"] = _ask("メール", "")
    corp["invoiceNo"] = _ask("インボイス登録番号（T+13桁。無ければ空）", "")
    print("振込先（請求書に載せる。改行は \\n）")
    corp["bank"] = _ask("  例: ○○銀行（0000） ○○支店（000）\\n普通 0000000\\nカ）○○", "").replace("\\n", "\n")
    corp["sealText"] = _ask("角印の文字", (corp["name"] + "之印") if corp["name"] else "")
    per = example["profiles"]["personal"]
    per["name"] = _ask("個人名義の氏名（個人事業として出す場合。不要なら空）", "")
    per["address"] = corp["address"]
    per["tel"] = corp["tel"]
    per["sealText"] = per["name"][:1] if per["name"] else ""

    tr = example["travel"]
    tr["role"] = _ask("あなたの役職（日当表のキー）", "代表取締役")
    print("日当（円）。日帰り／宿泊1泊。役職は後から profile.json で増やせます")
    for role in list(tr["rates"].keys()):
        d = _ask("  %s 日帰り" % role, str(tr["rates"][role]["day"]))
        n = _ask("  %s 宿泊" % role, str(tr["rates"][role]["night"]))
        tr["rates"][role] = {"day": int(d or 0), "night": int(n or 0)}
    tr["bases"]["hq"]["label"] = _ask("拠点の呼び名", "本店")
    tr["bases"]["hq"]["address"] = corp["address"]
    tr["bases"]["hq"]["station"] = _ask("拠点の最寄駅（「駅」なし。例: 東京）", "")
    tr["hubs"] = [h for h in [_ask("乗り継ぎのハブ駅（例: 東京）", tr["bases"]["hq"]["station"])] if h]
    tr["effectiveDate"] = _ask("旅費規程の施行日 (YYYY-MM-DD)", tr["effectiveDate"])

    cal = example["calendar"]
    src = _ask("カレンダーの ICS ファイルのパス、または限定公開URL（あとで足せます）", "")
    cal["sources"] = [{"type": "url" if src.startswith("http") else "ics",
                       ("url" if src.startswith("http") else "path"): src, "name": "仕事"}] if src else []
    if sys.platform == "darwin":
        if _ask("macOS のカレンダー.app も読みますか (y/N)", "N").lower().startswith("y"):
            cal["sources"].append({"type": "macos", "name": "カレンダー.app"})

    example["report"]["author"] = corp["rep"].split("　")[-1] if corp["rep"] else per["name"]
    example["output"]["dir"] = _ask("PDF の保存先フォルダ", "~/Documents/書類メーカー")
    example["output"]["obsidianDir"] = _ask("Obsidian に .md も出すならそのフォルダ（不要なら空）", "")
    save(example)
    print("\n保存しました: %s" % paths.profile_path())
    return example
