"""GUI（app/index.html）を http://127.0.0.1:8797/ で出す小さなサーバ。

file:// のままだとブラウザからファイルを書けないので挟む。127.0.0.1 だけで待ち受け、外からは触れない。
/api/profile … GET は profile.json の profiles・travel と secrets.env の鍵。POST は GUI で直した名義を profile.json へ書き戻す
/api/quest   … 導入の道順。達成は設定と出力の実物から判定する
/api/update   … 新しい版があるか。POST で入れ替える（iPhone の更新と同じ形）
/api/travel   … 日当・宿泊上限・精算の期限・施行日。旅費規程に出る金額
/api/chat     … 画面のチャットを、設定した接続先（CLI含む）へ流す
/api/addresses … 一度使った宛先。書類・契約書・定期送付から集める
/api/mail     … Gmail の下書きに PDF ごと置く（送らない）
/api/make     … 貼った文章から書類を組み立てる（作る・PDFにする）
/api/route    … 調べる窓口を開く／落とした画面を読む／どれで行ったかを選ぶ
/api/bases    … 拠点（今いる場所）の登録と切り替え
/api/output   … 控えの置き場（フォルダ・Obsidian・表計算の台帳）
/api/auto     … 設定をまとめて埋める。GET=何を入れるか見るだけ／POST=書く
/api/knowledge … 今までの契約書・見積を取り込む。取引先・単価・条項として控える
/api/ai      … AI の接続先。選ぶ・鍵を入れる・本当に繋がるか試す
/api/fare/import … 画面に放り込んだ履歴のスクショを読む（見るだけ／--apply 相当は別の呼び）
/api/clients … 定期送付の台帳（~/.paper-maker/clients.json）
/api/nittei  … 日程調整。予約リンク・受付の設定・入った予約（~/.paper-maker/nittei.json）
"""
import datetime as dt
import functools
import http.server
import json
import pathlib
import shutil
import socketserver
import subprocess
import sys
import threading

from . import ai as ai_mod, autoset as auto_mod, bases as base_mod, knowledge as kn_mod, paths, profile as prof_mod, quest as quest_mod

PORT = 8797


def read_secret(key: str) -> str:
    p = paths.secrets_path()
    if not p.exists():
        return ""
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def write_secret(key: str, value: str):
    p = paths.secrets_path()
    lines = []
    if p.exists():
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith(key + "=")]
    lines.append("%s=%s" % (key, value))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


class Handler(http.server.SimpleHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ledger(self):
        return paths.data_dir() / "clients.json"

    def _local_request_ok(self) -> bool:
        """他のサイトからの横取り（CSRF・DNS リバインディング）を弾く。
        Host は 127.0.0.1/localhost だけ。Origin が付いていれば同じ所からだけ。"""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "[::1]"):
            return False
        origin = self.headers.get("Origin")
        if origin:
            o = origin.split("//", 1)[-1].split(":")[0]
            if o not in ("127.0.0.1", "localhost", "[::1]"):
                return False
        return True

    def do_GET(self):
        if self.path.startswith("/api/") and not self._local_request_ok():
            return self._json({"error": "forbidden"}, 403)
        if self.path.startswith("/api/profile"):
            try:
                prof = prof_mod.load()
            except FileNotFoundError:
                return self._json({"profiles": None, "travel": None, "geminiKey": ""})
            return self._json({"profiles": prof.get("profiles"), "travel": prof.get("travel"),
                               "geminiKey": (ai_mod.api_key() if ai_mod.load()["provider"] == "gemini" else "")})
        if self.path.startswith("/api/hello"):
            # 「そこに居るのは自分か」を確かめるための目印。
            # 同じポートを別の物が使っていることがある（社内で似た道具を動かしている等）
            from . import __version__
            return self._json({"app": "paper-maker", "version": __version__,
                               "home": str(paths.data_dir())})
        if self.path.startswith("/api/ai"):
            cur = ai_mod.load()
            return self._json({
                "provider": cur["provider"], "model": cur.get("model", ""),
                "endpoint": cur.get("endpoint", ""), "keyName": cur.get("keyName", ""),
                "command": cur.get("command", ""), "style": cur.get("style", ""),
                "label": cur.get("label", cur["provider"]),
                "hasKey": bool(ai_mod.api_key(cur)),
                "presets": [{"id": k, "label": v["label"], "model": v.get("model", ""),
                             "keyName": v.get("keyName", ""), "where": v["where"],
                             "style": v.get("style", ""), "command": v.get("command", ""),
                             "needEndpoint": v.get("style") != "cli" and not v.get("endpoint"),
                             "needCommand": v.get("style") == "cli" and not v.get("command")}
                            for k, v in ai_mod.PRESETS.items()],
            })
        if self.path.startswith("/api/update"):
            from . import update as up_mod, __version__
            try:
                m = up_mod.check()
                return self._json({"current": m["current"], "version": m["version"],
                                   "newer": bool(m["newer"])})
            except Exception as e:
                return self._json({"current": __version__, "newer": False,
                                   "message": str(e)})
        if self.path.startswith("/api/addresses"):
            from . import addressbook
            try:
                return self._json({"items": addressbook.listing()})
            except Exception as e:
                return self._json({"items": [], "message": str(e)})
        if self.path.startswith("/api/mail/check"):
            from . import mailer
            ok, msg = mailer.check()
            return self._json({"ok": ok, "message": msg,
                               "hasUser": bool(read_secret("GMAIL_ADDRESS")),
                               "hasKey": bool(read_secret("GMAIL_APP_PASSWORD"))})
        if self.path.startswith("/api/travel"):
            tr = (prof_mod.load().get("travel") or {}) if prof_mod.exists() else {}
            return self._json({
                "role": tr.get("role", ""), "rates": tr.get("rates") or {},
                "lodging": tr.get("lodging") or {}, "settleWithinDays": tr.get("settleWithinDays", 7),
                "receiptFreeUnder": tr.get("receiptFreeUnder", 0),
                "effectiveDate": tr.get("effectiveDate", "")})
        if self.path.startswith("/api/fare/pending"):
            from . import fares_bulk
            try:
                got = fares_bulk.pending(limit=10)
                got["auto"] = bool((prof_mod.load().get("travel") or {}).get("lookupFares", False))
                got["pairs"] = [{"from": a, "to": b} for a, b in got["pairs"]]
                return self._json(got)
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/bases"):
            try:
                return self._json({"bases": base_mod.listing()})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/output"):
            o = (prof_mod.load().get("output") or {}) if prof_mod.exists() else {}
            return self._json({"dir": o.get("dir", ""), "obsidianDir": o.get("obsidianDir", ""),
                               "sheetCsv": o.get("sheetCsv", "")})
        if self.path.startswith("/api/auto"):
            try:
                pl = auto_mod.plan()
            except Exception as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"steps": [x.as_dict() for x in pl["steps"]], "notes": pl["notes"]})
        if self.path.startswith("/api/knowledge"):
            d = kn_mod.load()
            return self._json({"docs": len(d["docs"]), "clients": d["clients"][-40:],
                               "items": d["items"][-40:],
                               "clauses": [{"heading": c["heading"], "title": c.get("title", "")}
                                           for c in d["clauses"][-40:]]})
        if self.path.startswith("/api/quest"):
            return self._json(quest_mod.evaluate(recheck="recheck=1" in self.path))
        if self.path.startswith("/api/chatwork/status"):
            return self._json({"hasToken": bool(read_secret("CHATWORK_API_TOKEN"))})
        if self.path.startswith("/api/chatwork/rooms"):
            return self._json({"error": "配布版では Chatwork 連携は未対応です"}, 400)
        if self.path.startswith("/api/clients"):
            p = self._ledger()
            return self._json(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"clients": []})
        if self.path.startswith("/api/nittei"):
            from . import nittei
            try:
                return self._json(nittei.state())
            except Exception as e:
                return self._json({"error": "日程調整を読めませんでした（%s）" % e.__class__.__name__}, 500)
        return super().do_GET()

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_POST(self):
        if not self._local_request_ok():
            return self._json({"error": "forbidden"}, 403)
        # fetch(mode:'no-cors') は application/json を送れないので、これで他サイトからの書き込みを弾ける
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json({"error": "Content-Type must be application/json"}, 415)
        if self.path.startswith("/api/nittei"):
            from . import nittei
            try:
                payload = self._read_json()
            except ValueError:
                return self._json({"error": "送られてきた内容が読めませんでした"}, 400)
            try:
                return self._json(nittei.save_settings(payload))
            except nittei.SettingsError as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:  # 想定外は種類だけ見せる。英語の生の文は出さない
                return self._json({"error": "保存できませんでした（%s）" % e.__class__.__name__}, 500)
        if self.path.startswith("/api/profile"):
            # GUI の ⚙設定 で直した名義を profile.json に書き戻す。
            # ここが無いと GUI は localStorage、CLI は profile.json を見て、別々の設定で動く。
            try:
                d = self._read_json()
                profs = d.get("profiles")
                if not isinstance(profs, dict):
                    raise ValueError("profiles が無い")
                prof = prof_mod.load()
                prof["profiles"] = {**prof.get("profiles", {}), **profs}
                prof_mod.save(prof)
                return self._json({"ok": True})
            except FileNotFoundError:
                return self._json({"error": "先に paper-maker init を実行してください"}, 400)
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/ai"):
            try:
                d = self._read_json()
                prov = d.get("provider")
                if prov:
                    if prov not in ai_mod.PRESETS:
                        raise ValueError("知らない接続先: %s" % prov)
                    cfg = dict(ai_mod.PRESETS[prov])
                    cfg["provider"] = prov
                    for k in ("model", "endpoint", "keyName", "command"):
                        if d.get(k):
                            cfg[k] = d[k]
                    if cfg.get("style") == "cli":
                        if not cfg.get("command"):
                            raise ValueError("走らせるコマンドを入れてください（例: ollama run llama3）")
                    elif not cfg.get("endpoint"):
                        raise ValueError("繋ぎ先のURLを入れてください")
                    ai_mod.save(cfg)
                key = (d.get("key") or "").strip()
                if key:
                    kn = ai_mod.load().get("keyName")
                    if kn:
                        write_secret(kn, key)
                if d.get("check"):
                    ok, msg = ai_mod.check()
                    return self._json({"ok": ok, "message": msg})
                return self._json({"ok": True, "message": "保存しました"})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/update"):
            from . import update as up_mod
            try:
                return self._json({"message": up_mod.apply()})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/chat"):
            try:
                d = self._read_json()
                cfg = ai_mod.load()
                if not ai_mod.api_key(cfg):
                    return self._json({"error": "AI に繋がっていません（道順5）"}, 400)
                sys_prompt = str(d.get("system") or "")
                text = str(d.get("text") or "")
                img = None
                if d.get("image"):
                    import base64 as _b64, tempfile as _tmp
                    raw = str(d["image"])
                    if "," in raw[:60]:
                        raw = raw.split(",", 1)[1]
                    tmpdir = _tmp.mkdtemp(prefix="pm-chat-")
                    img = pathlib.Path(tmpdir) / "add.png"
                    img.write_bytes(_b64.b64decode(raw))
                try:
                    got = ai_mod.ask_json(sys_prompt + "\n\n" + text,
                                          image_path=str(img) if img else None,
                                          timeout=240, cfg=cfg)
                finally:
                    if img:
                        shutil.rmtree(img.parent, ignore_errors=True)
                return self._json({"ok": True, "answer": got,
                                   "provider": cfg.get("provider", "")})
            except Exception as e:
                return self._json({"error": str(e) or e.__class__.__name__}, 400)
        if self.path.startswith("/api/addresses"):
            from . import addressbook
            try:
                d = self._read_json()
                if d.get("forget"):
                    addressbook.forget(str(d["forget"]))
                else:
                    addressbook.remember(str(d.get("name") or ""), str(d.get("email") or ""),
                                         "手で入れた")
                return self._json({"items": addressbook.listing()})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/mail"):
            from . import mailer
            try:
                d = self._read_json()
                if d.get("address") is not None:
                    write_secret("GMAIL_ADDRESS", str(d["address"]).strip())
                if d.get("appPassword"):
                    write_secret("GMAIL_APP_PASSWORD", str(d["appPassword"]).strip())
                if d.get("save"):
                    ok, msg = mailer.check()
                    return self._json({"ok": ok, "message": msg})
                import base64 as _b64
                import tempfile as _tmp
                files = [str(x) for x in (d.get("files") or [])]
                tmpdir = None
                for a in (d.get("attachments") or [])[:5]:
                    raw = str(a.get("data") or "")
                    if "," in raw[:60]:
                        raw = raw.split(",", 1)[1]
                    blob = _b64.b64decode(raw)
                    if len(blob) > 20 * 1024 * 1024:
                        raise ValueError("添付が大きすぎます（20MBまで）")
                    tmpdir = tmpdir or _tmp.mkdtemp(prefix="pm-mail-")
                    fp = pathlib.Path(tmpdir) / pathlib.Path(str(a.get("name") or "書類.pdf")).name
                    fp.write_bytes(blob)
                    files.append(str(fp))
                try:
                    got = mailer.save_draft(
                        str(d.get("to") or ""), str(d.get("subject") or ""),
                        str(d.get("body") or ""), files, str(d.get("cc") or ""))
                finally:
                    if tmpdir:
                        shutil.rmtree(tmpdir, ignore_errors=True)
                from . import addressbook
                addressbook.remember("", str(d.get("to") or ""), "下書きを置いた先")
                return self._json({"ok": True, "draft": got})
            except mailer.MailError as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:
                return self._json({"error": str(e) or e.__class__.__name__}, 400)
        if self.path.startswith("/api/travel"):
            try:
                d = self._read_json()
                prof = prof_mod.load()
                tr = prof.setdefault("travel", {})
                rates = d.get("rates")
                if isinstance(rates, dict) and rates:
                    clean = {}
                    for k, v in rates.items():
                        k = str(k).strip()
                        if not k:
                            continue
                        clean[k] = {"day": max(0, int(v.get("day") or 0)),
                                    "night": max(0, int(v.get("night") or 0))}
                    # 役職名がひとつも書かれていない時に、入っていた日当を消さない。
                    # 前は空の表で上書きしてから落ちていた（画面には空のエラーが出るだけ）
                    if not clean:
                        raise ValueError("役職の名前を入れてください（代表取締役・従業員など）")
                    tr["rates"] = clean
                    if tr.get("role") not in clean:
                        tr["role"] = next(iter(clean))
                if d.get("role"):
                    tr["role"] = str(d["role"])
                if d.get("lodgingCap") is not None:
                    tr.setdefault("lodging", {})["mode"] = "actual_capped"
                    tr["lodging"]["cap"] = max(0, int(d["lodgingCap"]))
                if d.get("settleWithinDays") is not None:
                    tr["settleWithinDays"] = max(1, int(d["settleWithinDays"]))
                if d.get("receiptFreeUnder") is not None:
                    tr["receiptFreeUnder"] = max(0, int(d["receiptFreeUnder"]))
                if d.get("effectiveDate"):
                    tr["effectiveDate"] = str(d["effectiveDate"])[:10]
                prof_mod.save(prof)
                return self._json({"ok": True, "travel": tr})
            except Exception as e:
                return self._json({"error": str(e) or e.__class__.__name__}, 400)
        if self.path.startswith("/api/make"):
            from . import make_docs, render as render_mod
            try:
                d = self._read_json()
                if not ai_mod.api_key():
                    raise ValueError("先に AI に繋いでください（道順5）")
                got = make_docs.build(str(d.get("text") or ""))
                if not got["docs"]:
                    return self._json({"docs": [], "notes": got.get("notes", []),
                                       "missing": got.get("missing") or ["書類の種類を読み取れませんでした"]})
                if not d.get("save"):
                    return self._json(got)
                prof = prof_mod.load()
                out_dir = prof_mod.output_dir(prof) / dt.date.today().strftime("%Y/%m")
                out_dir.mkdir(parents=True, exist_ok=True)
                made = []
                for doc in got["docs"]:
                    label = doc.get("kindLabel") or doc["type"]
                    who = (doc.get("clientName") or "宛名なし")[:20]
                    stem = "%s_%s_%s" % (label, who, dt.date.today().isoformat())
                    js = out_dir / (stem + ".json")
                    js.write_text(json.dumps({"doc": doc}, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                    made.append(str(js))
                    pdf = out_dir / (stem + ".pdf")
                    if render_mod.app_doc_to_pdf(doc, prof.get("profiles", {}), pdf,
                                                 prof.get("browser", ""),
                                                 travel=prof.get("travel")):
                        made.append(str(pdf))
                got["saved"] = made
                return self._json(got)
            except Exception as e:
                return self._json({"error": str(e) or e.__class__.__name__}, 400)
        if self.path.startswith("/api/route"):
            from . import fare_route, fares_write, fare_shot
            try:
                d = self._read_json()
                frm = str(d.get("from") or "").strip()
                to = str(d.get("to") or "").strip()
                # 画面を撮った写真から読む。取りに行くのは人、こちらは読むだけ
                if d.get("shot"):
                    import base64 as _b64, tempfile as _tmp
                    if not ai_mod.api_key():
                        raise ValueError("画面を読ませるには、先に AI に繋いでください（道順5）")
                    raw = d["shot"]
                    if "," in raw[:60]:
                        raw = raw.split(",", 1)[1]
                    blob = _b64.b64decode(raw)
                    if len(blob) > 20 * 1024 * 1024:
                        raise ValueError("画像が大きすぎます（20MBまで）")
                    tmpdir = _tmp.mkdtemp(prefix="pm-shot-")
                    fp = pathlib.Path(tmpdir) / "shot.png"
                    fp.write_bytes(blob)
                    try:
                        got = fare_shot.read(fp)
                    finally:
                        shutil.rmtree(tmpdir, ignore_errors=True)
                    got["from"] = frm or got.get("from", "")
                    got["to"] = to or got.get("to", "")
                    got["picked"] = -1
                    return self._json(got)
                if d.get("open"):
                    if not frm or not to:
                        raise ValueError("出発と到着を入れてください")
                    return self._json({"url": fare_route.search_url(frm, to)})
                if not frm or not to:
                    raise ValueError("出発と到着を入れてください")
                if d.get("pick") is not None:
                    r = (d.get("routes") or [])[int(d["pick"])]
                    keys = fares_write.kinds_of(r.get("lines"))
                    fares_write.add(frm, to, int(r["amount"]),
                                    line="／".join(r.get("lines") or []),
                                    source="本人が選択 %s" % dt.date.today().isoformat(),
                                    routes=d.get("routes"), prefer=keys)
                    return self._json({"saved": True, "amount": r["amount"], "prefer": keys})
                got = fare_route.lookup(frm, to, prefer=fares_write.prefer_of(frm, to))
                if d.get("save") and got["amount"]:
                    fares_write.add(frm, to, got["amount"], line=got["route"],
                                    source=got["source"], routes=got.get("routes"))
                return self._json(got)
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/bases"):
            try:
                d = self._read_json()
                act = d.get("action") or "add"
                if act == "use":
                    base_mod.use(d.get("label") or d.get("key") or "")
                elif act == "remove":
                    base_mod.remove(d.get("label") or d.get("key") or "")
                else:
                    got = base_mod.add(d.get("label"), d.get("address"), d.get("station") or "")
                    return self._json({"bases": base_mod.listing(), "note": got.get("note", "")})
                return self._json({"bases": base_mod.listing()})
            except base_mod.BadBase as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/output"):
            try:
                d = self._read_json()
                prof = prof_mod.load()
                o = prof.setdefault("output", {})
                for k in ("dir", "obsidianDir", "sheetCsv"):
                    if k not in d:
                        continue
                    v = str(d[k] or "").strip()
                    # 相対の書き方だと、どこに出たのか本人にも分からなくなる
                    if v and not (v.startswith("/") or v.startswith("~")):
                        raise ValueError("置き場は / か ~ から始まる道で書いてください（%s）" % v[:30])
                    o[k] = v
                prof_mod.save(prof)
                return self._json({"ok": True, "output": o})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/auto"):
            import base64 as _b64
            import tempfile as _tmp
            try:
                d = self._read_json()
                paths_in, tmpdir = [], None
                for f in (d.get("files") or [])[:5]:
                    raw = f.get("data") or ""
                    if "," in raw[:60]:
                        raw = raw.split(",", 1)[1]
                    blob = _b64.b64decode(raw)
                    if len(blob) > 20 * 1024 * 1024:
                        raise ValueError("%s は大きすぎます（20MBまで）" % f.get("name"))
                    tmpdir = tmpdir or _tmp.mkdtemp(prefix="pm-auto-")
                    fp = pathlib.Path(tmpdir) / pathlib.Path(str(f.get("name") or "書類")).name
                    fp.write_bytes(blob)
                    paths_in.append(str(fp))
                pl = auto_mod.plan(files=paths_in)
                if tmpdir:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                out = {"steps": [x.as_dict() for x in pl["steps"]], "notes": pl["notes"]}
                if d.get("apply"):
                    out["written"] = auto_mod.apply(pl)["written"]
                return self._json(out)
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/knowledge"):
            import base64 as _b64
            import tempfile as _tmp
            try:
                d = self._read_json()
                files = d.get("files") or []
                if not files:
                    raise ValueError("ファイルがありません")
                if len(files) > 20:
                    raise ValueError("一度に渡せるのは20件までです")
                if not ai_mod.api_key():
                    raise ValueError("読ませるには先に AI に繋いでください（道順の「AI に繋ぐ」）")
                tmpdir = _tmp.mkdtemp(prefix="pm-kn-")
                results, raws, notes = [], [], []
                for f in files:
                    name = str(f.get("name") or "書類")
                    raw = f.get("data") or ""
                    if "," in raw[:60]:
                        raw = raw.split(",", 1)[1]
                    blob = _b64.b64decode(raw)
                    if len(blob) > 20 * 1024 * 1024:
                        notes.append("%s は大きすぎます（20MBまで）" % name)
                        continue
                    fp = pathlib.Path(tmpdir) / pathlib.Path(name).name
                    fp.write_bytes(blob)
                    try:
                        results.append(kn_mod.read_one(fp))
                        raws.append((name, blob))
                    except Exception as e:
                        notes.append("%s を読めませんでした: %s" % (name, e.__class__.__name__))
                shutil.rmtree(tmpdir, ignore_errors=True)
                if not results:
                    return self._json({"error": "読める書類がありませんでした", "notes": notes}, 400)
                sm = kn_mod.summarize(results)
                if d.get("apply"):
                    n = kn_mod.apply(sm, raws)
                    return self._json({"ok": True, "added": n, "summary": sm, "notes": notes})
                return self._json({"ok": True, "summary": sm, "notes": notes})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/fare/import"):
            # 画面に放り込んだ履歴のスクショを読む。画像は一時ファイルに落としてから渡す
            import base64 as _b64
            import tempfile as _tmp
            try:
                d = self._read_json()
                files = d.get("files") or []
                if not files:
                    raise ValueError("ファイルがありません")
                if len(files) > 30:
                    raise ValueError("一度に渡せるのは30枚までです")
                from . import fares_import as fi
                key = ai_mod.api_key()
                records, notes = [], []
                tmpdir = _tmp.mkdtemp(prefix="pm-fare-")
                for f in files:
                    name = str(f.get("name") or "画像")
                    raw = f.get("data") or ""
                    if "," in raw[:60]:
                        raw = raw.split(",", 1)[1]
                    blob = _b64.b64decode(raw)
                    if len(blob) > 20 * 1024 * 1024:
                        notes.append("%s は大きすぎます（20MBまで）" % name)
                        continue
                    ext = pathlib.Path(name).suffix.lower()
                    if ext in (".txt", ".csv", ".md"):
                        r, bad = fi.parse_text(blob.decode("utf-8", errors="replace"))
                        notes.append("%s から %d 行（読めない行 %d）" % (name, len(r), bad))
                        records += r
                        continue
                    if not key:
                        notes.append("画像を読むには、先に AI の接続先を決めて鍵を入れてください（道順の「AI に繋ぐ」）")
                        continue
                    fp = pathlib.Path(tmpdir) / ("img%d%s" % (len(records), ext or ".png"))
                    fp.write_bytes(blob)
                    try:
                        r = fi.read_image(fp, key)
                        notes.append("%s から %d 行" % (name, len(r)))
                        records += r
                    except Exception as e:
                        notes.append("%s を読めませんでした: %s" % (name, e.__class__.__name__))
                    finally:
                        try:
                            fp.unlink()
                        except OSError:
                            pass
                shutil.rmtree(tmpdir, ignore_errors=True)
                if not records:
                    return self._json({"error": "取り込める明細がありませんでした", "notes": notes}, 400)
                sm = fi.summarize(records)
                if d.get("apply"):
                    n = fi.apply(sm)
                    return self._json({"ok": True, "added": n, "summary": sm, "notes": notes})
                return self._json({"ok": True, "summary": sm, "notes": notes})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/quest/skip"):
            try:
                d = self._read_json()
                qid = int(d.get("id"))
                quest_mod.unskip(qid) if d.get("undo") else quest_mod.skip(qid)
                return self._json(quest_mod.evaluate())
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/quest/run"):
            # クエストの「やってみる」ボタン。時間のかかる物は動かさない（rules だけ）
            try:
                what = str(self._read_json().get("what", ""))
                if what == "denshi":
                    from .docs import denshi as denshi_doc
                    prof = prof_mod.load()
                    smp = prof_mod.sample_issuer(prof)
                    if smp:
                        return self._json({"error": "⚙設定の %s が見本のままです" % smp}, 400)
                    out = prof_mod.output_dir(prof) / "規程"
                    out.mkdir(parents=True, exist_ok=True)
                    (out / "電子取引データ事務処理規程.html").write_text(
                        denshi_doc.build_html(prof), encoding="utf-8")
                    from . import render
                    ok = render.html_to_pdf(out / "電子取引データ事務処理規程.html",
                                            out / "電子取引データ事務処理規程.pdf",
                                            prof.get("browser", ""))
                    where = out / ("電子取引データ事務処理規程.pdf" if ok else "電子取引データ事務処理規程.html")
                    return self._json({"ok": True, "path": str(where),
                                       "message": "出しました: %s" % where.name})
                if what == "rules":
                    from .docs import rules as rules_doc
                    prof = prof_mod.load()
                    smp = prof_mod.sample_issuer(prof)
                    if smp:
                        return self._json({"error": "⚙設定の %s が見本のままです。"
                                                    "税理士に見せる紙なので、先に直してください" % smp}, 400)
                    out = prof_mod.output_dir(prof) / "規程"
                    out.mkdir(parents=True, exist_ok=True)
                    (out / "旅費規程.html").write_text(rules_doc.build_html(prof), encoding="utf-8")
                    from . import render
                    ok = render.html_to_pdf(out / "旅費規程.html", out / "旅費規程.pdf", prof.get("browser", ""))
                    where = out / ("旅費規程.pdf" if ok else "旅費規程.html")
                    return self._json({"ok": True, "path": str(where),
                                       "message": "出しました: %s" % where.name})
                return self._json({"error": "unknown"}, 400)
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/chatwork/token"):
            try:
                tok = str(self._read_json().get("token", "")).strip()
                if not tok:
                    raise ValueError("空のトークン")
                write_secret("CHATWORK_API_TOKEN", tok)
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if self.path.startswith("/api/run"):
            return self._json({"error": "配布版では定期送付の自動実行は未対応です。台帳の保存はできます"}, 400)
        if not self.path.startswith("/api/clients"):
            return self._json({"error": "unknown endpoint"}, 404)
        try:
            data = self._read_json()
            if not isinstance(data.get("clients"), list):
                raise ValueError("clients が配列でない")
        except Exception as e:
            return self._json({"error": "受け取ったデータが不正: %s" % e}, 400)
        p = self._ledger()
        bk = p.parent / "_backup"
        bk.mkdir(parents=True, exist_ok=True)
        if p.exists():
            shutil.copy2(p, bk / ("clients.%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._json({"ok": True, "count": len(data["clients"])})

    def log_message(self, *a):
        pass


def open_browser(url: str):
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", url], check=False)
        elif sys.platform == "win32":
            import os
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", url], check=False)
    except Exception:
        print("ブラウザで開いてください:", url)


def serve(open_it=True, port=PORT):
    handler = functools.partial(Handler, directory=str(paths.APP_HTML.parent))
    socketserver.TCPServer.allow_reuse_address = True
    try:
        srv = socketserver.TCPServer(("127.0.0.1", port), handler)
    except OSError:
        print("ポート %d は使用中です。`paper-maker app --port 8798` のように別の番号で起動してください" % port)
        return 1
    with srv:
        url = "http://127.0.0.1:%d/index.html" % port
        print("書類メーカー: %s\n止めるときは Ctrl+C" % url)
        if open_it:
            threading.Timer(0.4, lambda: open_browser(url)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
