"""設定を、聞かずに埋める。

ぽちぽち埋めさせていた欄は、だいたいどこかに既にある。
  AI の接続先   … そのパソコンに入っている CLI を見れば分かる
  カレンダー     … Mac のカレンダー.app に予定が入っているかを見れば分かる
  名乗り・振込先 … 自分が去年出した請求書に、全部そのまま載っている
  拠点          … 住所から引ける
  日当          … これだけは人が決める。金額を勝手に置かない

**勝手に保存しない。** 何をどこに書くかを一覧で出して、押させてから書く。
上書きになる欄は、今の値も並べて見せる。
"""
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys

from . import ai, paths, profile

IDENTITY_PROMPT = """この書類は、ある事業者が自分で発行した請求書か見積書です。
**発行した側（お金を受け取る側）**の情報だけを、次の JSON で返してください。
宛先（お金を払う側・「御中」「様」が付いているほう）は絶対に混ぜないこと。

決まり
- 書いていないことは足さない。無ければ空文字
- 電話・メールは書いてあるものだけ
- 振込先は、銀行名・支店・種別・番号・カナ名義を改行で区切ってそのまま

{{
  "name": "発行元の会社名または屋号",
  "rep": "代表者の肩書きと氏名（例: 代表取締役　山田 太郎）",
  "address": "発行元の住所",
  "tel": "",
  "email": "",
  "invoiceNo": "インボイスの登録番号（Tから始まる番号）",
  "bank": "振込先（改行で区切る）",
  "kind": "corp" か "personal"（会社名なら corp、個人名だけなら personal）
}}"""

STATION_PROMPT = """次の住所から、最寄りの鉄道駅を1つだけ挙げてください。
分からなければ空文字にしてください。推測で作らないこと。

住所: {addr}

{{"station": "駅名（「駅」の字は付けない）", "label": "この場所の呼び名（例: 本店 / 自宅 / 事務所）"}}"""

CLI_ORDER = [("claude-cli", "claude"), ("codex-cli", "codex")]
SKIP_WORDS = ("祝日", "誕生日", "リマインダー", "Siri", "Holidays", "Birthday")


class Step:
    """埋める手が1つ。what=何を、where=どこに書くか、now=今の値、new=入れる値。"""

    def __init__(self, what, where, now, new, source, note=""):
        self.what, self.where, self.now, self.new = what, where, now, new
        self.source, self.note = source, note

    @property
    def overwrite(self):
        return bool(self.now) and self.now != self.new

    def as_dict(self):
        return {"what": self.what, "where": self.where, "now": self.now,
                "new": self.new, "source": self.source, "note": self.note,
                "overwrite": self.overwrite}


# ---------- 見つける ----------

def find_ai():
    """入っている CLI を探す。鍵を1つも貼らずに済む順に見る。"""
    for name, cmd in CLI_ORDER:
        p = shutil.which(cmd)
        if p:
            return name, p
    return None, None


def find_calendars():
    """Mac のカレンダー.app から、仕事で使っていそうなカレンダー名。"""
    if sys.platform != "darwin":
        return []
    try:
        out = subprocess.run(
            ["osascript", "-e", 'tell application "Calendar" to get name of every calendar'],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    names, seen = [], set()
    for n in out.stdout.strip().split(", "):
        n = n.strip()
        if not n or n in seen or any(w in n for w in SKIP_WORDS):
            continue
        seen.add(n)
        names.append(n)
    return names


def find_documents(limit=8):
    """自分が過去に出した書類を、置いてありそうな所から探す。"""
    hits = []
    roots = [pathlib.Path.home() / "Documents", pathlib.Path.home() / "Desktop",
             pathlib.Path.home() / "Downloads"]
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if len(hits) >= limit:
                break
            if p.suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg"):
                continue
            if len(p.relative_to(root).parts) > 3:
                continue
            if any(w in p.name for w in ("請求", "見積", "invoice", "Invoice", "quote")):
                hits.append(p)
    return hits


# ---------- 組み立てる ----------

SAMPLE_MARKS = ("株式会社サンプル", "山田 太郎", "サンプル銀行", "example.com",
                "東京都千代田区丸の内1-1-1")


def _is_sample(pr: dict) -> bool:
    """見本のまま手が入っていない名義か。人が書いた値は消さない。"""
    if not pr:
        return False
    body = " ".join(str(v) for v in pr.values())
    return any(m in body for m in SAMPLE_MARKS)


def plan(files=None, use_ai=True, timeout=180):
    """何を埋めるかの一覧。ここでは書かない。"""
    prof = profile.load() if profile.exists() else json.loads(
        (paths.EXAMPLES / "profile.example.json").read_text(encoding="utf-8"))
    steps, notes = [], []

    name, path = find_ai()
    cfg = ai.load()
    if name:
        if cfg.get("provider") != name:
            steps.append(Step("AI の接続先", "ai.json の provider",
                              cfg.get("provider", ""), name,
                              "%s が入っていた（%s）" % (name.split("-")[0], path),
                              "月額の中で動くので、鍵も従量課金も要りません"))
    else:
        notes.append("CLI が見つかりませんでした。鍵を貼るなら道順5の枠から。")

    cals = find_calendars()
    if cals:
        srcs = prof.get("calendar", {}).get("sources", [])
        if not any(s.get("type") == "macos" for s in srcs):
            steps.append(Step("カレンダー", "profile.json の calendar.sources",
                              "%d 件" % len(srcs), 'type: "macos"',
                              "カレンダー.app に %s ほか %d 個" % (cals[0], len(cals) - 1),
                              "書き出しも URL も要りません"))
    elif sys.platform == "darwin":
        notes.append("カレンダー.app を読めませんでした。初回は許可を聞かれます。")

    # 見つけた CLI は、この回からもう使う。
    # 「これから接続先にします」と出しておいて、同じ回で読めないのはおかしい。
    use = dict(ai.PRESETS[name], provider=name) if name else cfg
    ident = None
    if use_ai and ai.api_key(use):
        for f in (files or find_documents()):
            try:
                ident = read_identity(f, timeout=timeout, cfg=use)
            except Exception:
                continue
            if ident and ident.get("name"):
                ident["_from"] = pathlib.Path(f).name
                break
    if ident:
        key = "personal" if ident.get("kind") == "personal" else "corp"
        cur = (prof.get("profiles", {}).get(key) or {})
        src = "%s から読んだ" % ident["_from"]
        # 屋号を持たない人の書類を読んだのに、発行の既定が会社のままだと、
        # 次に出す請求書が見本の「株式会社サンプル」と見本の口座で出る。
        if (prof.get("defaultIssuer") or "corp") != key:
            steps.append(Step("書類を出す名義", "profile.json の defaultIssuer",
                              prof.get("defaultIssuer", ""), key,
                              "読んだ書類が%s名義だった" % ("個人" if key == "personal" else "法人"),
                              "会社と個人を使い分けるなら、画面の⚙設定で切り替えられます"))
        other = "corp" if key == "personal" else "personal"
        if _is_sample(prof.get("profiles", {}).get(other) or {}):
            steps.append(Step("使わないほうの名義", "profiles.%s.__clear__" % other,
                              (prof["profiles"][other] or {}).get("name", ""), "（空にする）",
                              "見本の値が入ったままだった",
                              "見本のまま残すと、選び間違えた時にその名前で書類が出ます"))
        for field, label in (("name", "会社名（屋号）"), ("rep", "代表者"), ("address", "住所"),
                             ("tel", "電話"), ("email", "メール"),
                             ("invoiceNo", "インボイス番号"), ("bank", "振込先")):
            val = (ident.get(field) or "").strip()
            if val:
                steps.append(Step(label, "profiles.%s.%s" % (key, field),
                                  cur.get(field, ""), val, src))
        # 判子の文字。ここを置いていくと、直したはずの書類に
        # 「株式会社サンプル之印」が押されたまま出る。
        nm = (ident.get("name") or "").strip()
        if nm:
            seal = (cur.get("sealText") or "").strip()
            want = ("%s之印" % nm) if key == "corp" else nm.split()[0]
            if not seal or _is_sample({"s": seal}):
                steps.append(Step("判子の文字", "profiles.%s.sealText" % key, seal, want,
                                  src, "実物を押した写真も⚙設定から登録できます"))

        addr = (ident.get("address") or "").strip()
        if addr:
            st = guess_station(addr, timeout=timeout, cfg=use) if use_ai else {}
            bases = prof.get("travel", {}).get("bases", {})
            cur_b = bases.get("hq") or {}
            # 最寄駅が引けなくても住所だけは入れる。
            # ここを見本のままにすると、その日の移動が丸ごと東京から出発したことになる。
            label = st.get("label") or cur_b.get("label") or "拠点"
            station = st.get("station") or ""
            now = "%s（%s）" % (cur_b.get("label", ""), cur_b.get("station", "")) if cur_b else ""
            new = "%s（%s）" % (label, station) if station else "%s（最寄駅は未記入）" % label
            if now != new:
                steps.append(Step("拠点", "travel.bases.hq", now, new,
                                  "住所から引いた" if station else "書類の住所を使う",
                                  "違っていたら道順3で直せます"
                                  if station else "最寄駅は引けませんでした。道順3で入れてください"))
    elif not files:
        notes.append("過去の請求書が見つかりませんでした。1枚渡せば名乗りと振込先が埋まります。")

    notes.append("日当だけは入れません。いくらにするかは人が決める所です（道順9）。")
    return {"steps": steps, "notes": notes}


def read_identity(path, timeout=180, cfg=None) -> dict:
    p = pathlib.Path(path).expanduser()
    if p.suffix.lower() in (".txt", ".md", ".csv"):
        text = p.read_text(encoding="utf-8", errors="replace")[:20000]
        return ai.ask_json(IDENTITY_PROMPT + "\n\n書類の中身:\n\"\"\"\n" + text + "\n\"\"\"",
                           timeout=timeout, cfg=cfg)
    return ai.ask_json(IDENTITY_PROMPT, image_path=str(p), timeout=timeout, cfg=cfg)


def guess_station(addr, timeout=120, cfg=None) -> dict:
    try:
        got = ai.ask_json(STATION_PROMPT.format(addr=addr), timeout=timeout, cfg=cfg)
    except Exception:
        return {}
    return got if isinstance(got, dict) else {}


# ---------- 書く ----------

def apply(pl) -> dict:
    """一覧のとおりに書く。押されて初めてここへ来る。"""
    steps = pl["steps"] if isinstance(pl, dict) else pl
    profile.ensure_data_files()
    if not profile.exists():
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
    prof = profile.load()
    done = 0

    for s in steps:
        w = s.where if isinstance(s, str) else s.where
        new = s.new
        if w.startswith("ai.json"):
            # 前の接続先の型（model / endpoint / keyName）を持ち越さない。
            # load() は今の provider の型を混ぜて返すので、provider だけ差し替えると
            # 「Claude Code なのに model は gemini」という設定が残る。
            ai.save(dict(ai.PRESETS[new], provider=new))
        elif w.endswith("defaultIssuer"):
            prof["defaultIssuer"] = new
        elif w.startswith("profiles."):
            _, key, field = w.split(".", 2)
            slot = prof.setdefault("profiles", {}).setdefault(key, {})
            if field == "__clear__":
                for f in ("name", "rep", "address", "tel", "email", "invoiceNo", "bank", "sealText"):
                    slot[f] = ""
            else:
                slot[field] = new
            if not prof.get("defaultIssuer"):
                prof["defaultIssuer"] = key
        elif w.endswith("calendar.sources"):
            cal = prof.setdefault("calendar", {})
            srcs = cal.setdefault("sources", [])
            # 見本のまま残っている、実体の無い .ics は落とす。
            # 人が自分で置いたファイルは触らない（在るなら残す）。
            keep = []
            for x in srcs:
                if x.get("type") == "ics":
                    fp = pathlib.Path(x.get("path", "")).expanduser()
                    if not fp.is_absolute():
                        fp = paths.data_dir() / x.get("path", "")
                    if not fp.exists():
                        continue
                keep.append(x)
            if not any(x.get("type") == "macos" for x in keep):
                keep.append({"type": "macos", "name": "カレンダー.app"})
            cal["sources"] = keep
        elif w == "travel.bases.hq":
            label, _, station = new.partition("（")
            station = station.rstrip("）")
            if station == "最寄駅は未記入":
                station = ""
            prof.setdefault("travel", {}).setdefault("bases", {})["hq"] = {
                "label": label.strip(), "address": _addr_of(steps), "station": station}
            prof["travel"]["currentBase"] = "hq"
        else:
            continue
        done += 1

    prof.setdefault("travel", {}).setdefault("effectiveDate", dt.date.today().isoformat())
    profile.save(prof)
    return {"written": done}


def _addr_of(steps):
    for s in steps:
        if s.where.endswith(".address"):
            return s.new
    return ""
