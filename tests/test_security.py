"""攻撃デモ（Phase 13）。壁を自分で叩く。ダミーデータだけ。"""
import datetime as dt
import hashlib
import http.client
import io
import json
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import unittest
import zipfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paper_maker import bridge, ics, itinerary, render, update  # noqa: E402
from paper_maker.docs import report  # noqa: E402


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class BridgeAttack(unittest.TestCase):
    """他のサイトから localhost の bridge を横取りできるか。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pmsec-")
        os.environ["PAPER_MAKER_HOME"] = cls.tmp
        shutil.copy(ROOT / "examples" / "profile.example.json", pathlib.Path(cls.tmp) / "profile.json")
        cls.port = _free_port()
        import functools
        import socketserver
        handler = functools.partial(bridge.Handler, directory=str(ROOT / "app"))
        socketserver.TCPServer.allow_reuse_address = True
        cls.srv = socketserver.TCPServer(("127.0.0.1", cls.port), handler)
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": "127.0.0.1:%d" % self.port}
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_a_legit_local_read_and_write(self):
        st, data = self.req("GET", "/api/profile")
        self.assertEqual(st, 200)
        self.assertIn("株式会社サンプル", data.decode("utf-8"))
        st, _ = self.req("POST", "/api/clients", json.dumps({"clients": [{"id": "a"}]}),
                         {"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(st, 200)

    def test_foreign_origin_is_refused(self):
        st, _ = self.req("POST", "/api/clients", json.dumps({"clients": []}),
                         {"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(st, 403)
        st, _ = self.req("GET", "/api/profile", headers={"Origin": "https://evil.example"})
        self.assertEqual(st, 403)

    def test_dns_rebinding_host_is_refused(self):
        st, _ = self.req("GET", "/api/profile", headers={"Host": "evil.example"})
        self.assertEqual(st, 403)

    def test_no_cors_form_post_is_refused(self):
        # fetch(mode:'no-cors') / <form> は application/json を送れない
        st, _ = self.req("POST", "/api/clients", json.dumps({"clients": []}), {"Content-Type": "text/plain"})
        self.assertEqual(st, 415)

    def test_zz_ledger_survives_attack(self):
        st, data = self.req("GET", "/api/clients")
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(data)["clients"], [{"id": "a"}])


class UpdateAttack(unittest.TestCase):
    """改ざんした zip を掴ませられるか。"""

    def _zip(self, files):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n, c in files.items():
                z.writestr(n, c)
        return buf.getvalue()

    def test_tampered_zip_is_refused(self):
        good = self._zip({"pm/VERSION": "9.9.9\n"})
        bad = good[:-1] + bytes([good[-1] ^ 0xFF])
        manifest = {"version": "9.9.9", "zip": "https://x/z.zip", "sha256": hashlib.sha256(good).hexdigest()}
        with mock.patch.object(update, "_fetch", side_effect=[json.dumps(manifest).encode(), bad]):
            msg = update.apply("https://x/manifest.json", dry_run=True)
        self.assertIn("中止", msg)

    def test_correct_zip_passes_dry_run(self):
        good = self._zip({"pm/VERSION": "9.9.9\n"})
        manifest = {"version": "9.9.9", "zip": "https://x/z.zip", "sha256": hashlib.sha256(good).hexdigest()}
        with mock.patch.object(update, "_fetch", side_effect=[json.dumps(manifest).encode(), good]):
            msg = update.apply("https://x/manifest.json", dry_run=True)
        self.assertIn("SHA256 一致", msg)

    def test_older_version_is_not_applied(self):
        manifest = {"version": "0.0.1", "zip": "https://x/z.zip", "sha256": "00"}
        with mock.patch.object(update, "_fetch", side_effect=[json.dumps(manifest).encode()]):
            msg = update.apply("https://x/manifest.json", dry_run=True)
        self.assertIn("最新です", msg)


class InjectionAttack(unittest.TestCase):
    """カレンダーの件名に HTML を仕込まれたら。"""

    def test_calendar_title_html_is_escaped_in_report(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:u\nDTSTART;TZID=Asia/Tokyo:20260813T100000\n"
                "SUMMARY:<img src=x onerror=alert(1)> 打合せ\nLOCATION:<script>steal()</script>\nEND:VEVENT\nEND:VCALENDAR\n")
        evs = ics.expand_for_day(ics.parse(text), dt.date(2026, 8, 13))
        prof = json.loads((ROOT / "examples" / "profile.example.json").read_text(encoding="utf-8"))
        places = {"skip": [], "rules": []}
        fares = itinerary.Fares({"stations": {}}, {"fares": []})
        itin = itinerary.build(evs, prof, places, fares)
        html = report.build_html(dt.date(2026, 8, 13), prof, itin, [], [], note="<b>太字</b>")
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<script>steal", html)
        self.assertNotIn("<b>太字</b>", html)
        self.assertIn("&lt;img src=x", html)


class ProcessListLeak(unittest.TestCase):
    """書類の中身が Chrome の引数（ps で見える）に乗らないか。"""

    def test_doc_payload_not_in_browser_args(self):
        seen = {}

        def fake_url_to_pdf(url, pdf_path, exe, wait_sec=60):
            seen["url"] = url
            return True
        with mock.patch.object(render, "find_browser", return_value="/bin/echo"), \
             mock.patch.object(render, "url_to_pdf", side_effect=fake_url_to_pdf):
            ok = render.app_doc_to_pdf({"type": "estimate", "clientName": "秘密商事"}, {"corp": {"name": "秘密社"}},
                                       pathlib.Path(tempfile.mkdtemp()) / "x.pdf")
        self.assertTrue(ok)
        self.assertTrue(seen["url"].startswith("file://"))
        self.assertNotIn("#doc=", seen["url"])
        self.assertNotIn("秘密", seen["url"])


class ZipSlip(unittest.TestCase):
    def test_zip_paths_with_dotdot_are_skipped(self):
        # apply() の展開ロジックと同じ判定を単体で
        for rel in ("../../etc/passwd", "/etc/passwd", "a/../../b"):
            bad = rel.startswith("/") or ".." in pathlib.PurePosixPath(rel).parts
            self.assertTrue(bad, rel)
        self.assertFalse(".." in pathlib.PurePosixPath("paper_maker/cli.py").parts)


if __name__ == "__main__":
    unittest.main()


class QuestApiAttack(BridgeAttack):
    """道順のAPIも、他のサイトから叩けないこと。"""

    def test_quest_read_is_local_only(self):
        st, _ = self.req("GET", "/api/quest", headers={"Origin": "https://evil.example"})
        self.assertEqual(st, 403)
        st, data = self.req("GET", "/api/quest")
        self.assertEqual(st, 200)
        self.assertIn("quests", json.loads(data))

    def test_quest_skip_from_foreign_origin_is_refused(self):
        st, _ = self.req("POST", "/api/quest/skip", json.dumps({"id": 1}),
                         {"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(st, 403)

    def test_profile_write_from_foreign_origin_is_refused(self):
        st, _ = self.req("POST", "/api/profile", json.dumps({"profiles": {"corp": {"name": "乗っ取り"}}}),
                         {"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(st, 403)
        st, data = self.req("GET", "/api/profile")
        self.assertNotIn("乗っ取り", data.decode("utf-8"))


class FareImportApiAttack(BridgeAttack):
    """画面から画像を送る口も、他のサイトから叩けないこと。"""

    def test_import_from_foreign_origin_is_refused(self):
        st, _ = self.req("POST", "/api/fare/import", json.dumps({"files": []}),
                         {"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(st, 403)

    def test_text_file_is_read_without_a_key(self):
        import base64
        body = json.dumps({"files": [{"name": "h.txt", "data": base64.b64encode(
            "2026-08-01 鉄道 東京 品川 180\n2026-08-02 鉄道 東京 品川 180\n".encode("utf-8")).decode()}]})
        st, data = self.req("POST", "/api/fare/import", body,
                            {"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(st, 200)
        sm = json.loads(data)["summary"]
        self.assertEqual([(x["from"], x["to"], x["amount"]) for x in sm["sure"]], [("東京", "品川", 180)])

    def test_too_many_files_is_refused(self):
        body = json.dumps({"files": [{"name": "a.txt", "data": ""} for _ in range(40)]})
        st, data = self.req("POST", "/api/fare/import", body,
                            {"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(st, 400)
        self.assertIn("30枚", json.loads(data)["error"])

    def test_empty_request_is_refused(self):
        st, _ = self.req("POST", "/api/fare/import", json.dumps({"files": []}),
                         {"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(st, 400)


class HelloMarker(BridgeAttack):
    """同じポートに別の物が居ることがある。自分かどうかを名乗りで見分ける。"""

    def test_hello_says_who_it_is(self):
        st, data = self.req("GET", "/api/hello")
        self.assertEqual(st, 200)
        d = json.loads(data)
        self.assertEqual(d["app"], "paper-maker")
        self.assertEqual(d["home"], self.tmp)

    def test_hello_is_local_only(self):
        st, _ = self.req("GET", "/api/hello", headers={"Origin": "https://evil.example"})
        self.assertEqual(st, 403)


class AiApiAttack(BridgeAttack):
    """AI の設定と鍵を入れる口。よそから叩けないこと。"""

    def test_read_is_local_only(self):
        st, _ = self.req("GET", "/api/ai", headers={"Origin": "https://evil.example"})
        self.assertEqual(st, 403)
        st, data = self.req("GET", "/api/ai")
        self.assertEqual(st, 200)
        d = json.loads(data)
        self.assertIn("presets", d)

    def test_key_is_never_sent_back(self):
        """画面に鍵そのものを返さない。あるか無いかだけ。"""
        from paper_maker import bridge as b
        b.write_secret("GEMINI_API_KEY", "sk-secret-value")
        st, data = self.req("GET", "/api/ai")
        self.assertEqual(st, 200)
        self.assertNotIn("sk-secret-value", data.decode("utf-8"))
        self.assertTrue(json.loads(data)["hasKey"])

    def test_writing_the_key_from_a_foreign_origin_is_refused(self):
        st, _ = self.req("POST", "/api/ai", json.dumps({"provider": "openai", "key": "sk-evil"}),
                         {"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(st, 403)

    def test_unknown_provider_is_refused(self):
        st, data = self.req("POST", "/api/ai", json.dumps({"provider": "そんなものは無い"}),
                            {"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(st, 400)
        self.assertIn("知らない接続先", json.loads(data)["error"])


class KnowledgeApiAttack(BridgeAttack):
    """取り込み口。よそから書類を放り込まれない。"""

    def test_import_from_foreign_origin_is_refused(self):
        st, _ = self.req("POST", "/api/knowledge", json.dumps({"files": []}),
                         {"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(st, 403)

    def test_reading_the_store_is_local_only(self):
        st, _ = self.req("GET", "/api/knowledge", headers={"Origin": "https://evil.example"})
        self.assertEqual(st, 403)

    def test_too_many_files_is_refused(self):
        body = json.dumps({"files": [{"name": "a.txt", "data": ""} for _ in range(30)]})
        st, data = self.req("POST", "/api/knowledge", body,
                            {"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(st, 400)
        self.assertIn("20件", json.loads(data)["error"])
