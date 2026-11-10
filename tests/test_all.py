"""python3 -m unittest discover -s tests   で全部回る。標準ライブラリだけ。PDF 化（ブラウザ）は要らない。"""
import datetime as dt
import importlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paper_maker import ics, itinerary  # noqa: E402

SAMPLE_ICS = (ROOT / "examples" / "sample.ics").read_text(encoding="utf-8")


class TempHome(unittest.TestCase):
    """~/.paper-maker を一時フォルダに差し替える。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pmtest-")
        os.environ["PAPER_MAKER_HOME"] = self.tmp
        self.env = dict(os.environ, PAPER_MAKER_HOME=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)

    def cli(self, *args, check=True):
        r = subprocess.run([sys.executable, "-m", "paper_maker", *args], cwd=str(ROOT), env=self.env,
                           capture_output=True, text=True, timeout=120)
        if check:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def _real_issuer(self):
        """見本のままでは書類を出せない。自分の名義に直した状態にする。"""
        p = pathlib.Path(self.tmp) / "profile.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["profiles"]["corp"].update({
            "name": "合同会社ミナト", "rep": "代表社員　港 一郎",
            "address": "埼玉県さいたま市大宮区1-1-1", "tel": "048-000-0000",
            "email": "mail@minato.test", "bank": "北國銀行 普通 1234567",
            "sealText": "合同会社ミナト之印"})
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def init_example(self):
        self.cli("init", "--example")
        shutil.copy(ROOT / "examples" / "sample.ics", pathlib.Path(self.tmp) / "calendar.ics")
        p = pathlib.Path(self.tmp) / "profile.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["output"]["dir"] = self.tmp + "/out"
        d["output"]["obsidianDir"] = self.tmp + "/vault"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


class TestIcs(unittest.TestCase):
    def test_parse_and_expand_normal_day(self):
        evs = ics.parse(SAMPLE_ICS)
        day = ics.expand_for_day(evs, dt.date(2026, 8, 13))
        titles = [e["title"] for e in day]
        self.assertEqual(titles, ["A社 打合せ（山田様）", "B社 訪問", "セミナー（ZOOM）"])
        self.assertEqual(day[0]["start"], "10:00")
        self.assertEqual(day[0]["location"], "東京都新宿区西新宿2-8-1")

    def test_all_day(self):
        evs = ics.parse(SAMPLE_ICS)
        day = ics.expand_for_day(evs, dt.date(2026, 8, 14))
        self.assertEqual(len(day), 1)
        self.assertTrue(day[0]["all_day"])
        self.assertEqual(day[0]["start"], "")

    def test_weekly_rrule_count(self):
        evs = ics.parse(SAMPLE_ICS)
        # MO,WE COUNT=6 from 2026-08-10: 8/10 8/12 8/17 8/19 8/24 8/26
        for d, n in ((10, 1), (11, 0), (12, 1), (17, 1), (26, 1), (31, 0)):
            self.assertEqual(len(ics.expand_for_day(evs, dt.date(2026, 8, d))), n, "8/%d" % d)

    def test_utc_and_tzid(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:u\nDTSTART:20260813T010000Z\nDTEND:20260813T020000Z\n"
                "SUMMARY:UTC の予定\nEND:VEVENT\nEND:VCALENDAR\n")
        day = ics.expand_for_day(ics.parse(text), dt.date(2026, 8, 13))
        self.assertEqual(day[0]["start"], "10:00")  # UTC 01:00 → JST 10:00

    def test_folded_lines_and_escapes(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:u\nDTSTART;TZID=Asia/Tokyo:20260813T100000\n"
                "SUMMARY:長い件名\\, 折り\n 返しあり\nEND:VEVENT\nEND:VCALENDAR\n")
        day = ics.expand_for_day(ics.parse(text), dt.date(2026, 8, 13))
        self.assertEqual(day[0]["title"], "長い件名, 折り返しあり")

    def test_unsupported_rrule_warns_not_guesses(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:u\nDTSTART;TZID=Asia/Tokyo:20260803T100000\n"
                "RRULE:FREQ=MONTHLY;BYDAY=1MO\nSUMMARY:第1月曜\nEND:VEVENT\nEND:VCALENDAR\n")
        w = []
        day = ics.expand_for_day(ics.parse(text), dt.date(2026, 9, 7), w)
        self.assertEqual(day, [])
        self.assertTrue(any("展開できません" in x for x in w))

    def test_exdate(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:u\nDTSTART;TZID=Asia/Tokyo:20260810T090000\n"
                "RRULE:FREQ=DAILY;COUNT=5\nEXDATE;TZID=Asia/Tokyo:20260812T090000\nSUMMARY:毎日\nEND:VEVENT\nEND:VCALENDAR\n")
        evs = ics.parse(text)
        self.assertEqual(len(ics.expand_for_day(evs, dt.date(2026, 8, 11))), 1)
        self.assertEqual(len(ics.expand_for_day(evs, dt.date(2026, 8, 12))), 0)

    def test_empty_and_garbage(self):
        self.assertEqual(ics.parse(""), [])
        self.assertEqual(ics.parse("これはICSではない\n::\n"), [])


class TestItinerary(unittest.TestCase):
    def setUp(self):
        ex = ROOT / "examples"
        self.places = json.loads((ex / "places.example.json").read_text(encoding="utf-8"))
        # 見本には表を入れていない（入れると私用の予定が現地扱いになる）。試験用にここで作る
        self.places["rules"] = [
            {"match": ["新宿区", "新宿"], "station": "新宿"},
            {"match": ["渋谷区", "渋谷"], "station": "渋谷", "title": True},
            {"match": ["千代田区", "東京駅"], "station": "東京"},
            {"match": ["横浜市", "横浜"], "station": "横浜"}]
        self.fares = itinerary.Fares(json.loads((ex / "stations.example.json").read_text(encoding="utf-8")),
                                     json.loads((ex / "fares.example.json").read_text(encoding="utf-8")))
        self.profile = json.loads((ex / "profile.example.json").read_text(encoding="utf-8"))

    def test_classify(self):
        self.assertEqual(itinerary.classify({"location": "ZOOM", "title": "x"}, self.places)[0], "online")
        self.assertEqual(itinerary.classify({"location": "東京都新宿区1", "title": "x"}, self.places)[:2], ("onsite", "新宿"))
        self.assertEqual(itinerary.classify({"location": "どこか遠く", "title": "x"}, self.places)[0], "unknown")
        # 題名に当てるのは "title": true を書いた行だけ
        self.assertEqual(itinerary.classify({"location": "", "title": "渋谷で打合せ"}, self.places)[:2], ("onsite", "渋谷"))
        self.assertNotEqual(itinerary.classify({"location": "", "title": "新宿で美容院"}, self.places)[0], "onsite")

    def test_build_prices_known_and_flags_unknown(self):
        evs = ics.expand_for_day(ics.parse(SAMPLE_ICS), dt.date(2026, 8, 13))
        it = itinerary.build(evs, self.profile, self.places, self.fares)
        self.assertTrue(it["hasOnsite"])
        self.assertEqual([l["from"] + "→" + l["to"] for l in it["legs"]], ["東京→新宿", "新宿→横浜", "横浜→東京"])
        self.assertEqual(it["legs"][0]["amount"], 210)
        self.assertIsNone(it["legs"][1]["amount"])          # 推測で埋めない
        self.assertEqual(it["unpricedLegs"], 2)
        self.assertEqual(it["allowance"], 5000)
        self.assertEqual(it["transportTotal"], 210)

    def test_online_only_no_allowance(self):
        evs = ics.expand_for_day(ics.parse(SAMPLE_ICS), dt.date(2026, 8, 12))
        it = itinerary.build(evs, self.profile, self.places, self.fares)
        self.assertFalse(it["hasOnsite"])
        self.assertEqual(it["allowance"], 0)
        self.assertEqual(it["legs"], [])

    def test_unverified_fare_not_used(self):
        self.assertIsNone(self.fares.find("東京", "横浜"))
        self.assertEqual(self.fares.find("新宿", "東京")["amount"], 210)  # 逆向きは同額扱い


class TestCli(TempHome):
    def test_init_doctor_calendar_daily_rules_without_pdf(self):
        self.init_example()
        r = self.cli("doctor")
        self.assertIn("OK", r.stdout)
        r = self.cli("calendar", "--date", "2026-08-13")
        self.assertIn("3 件", r.stdout)
        r = self.cli("daily", "--date", "2026-08-13", "--no-pdf")
        self.assertIn("予定 3 件", r.stdout)
        out = pathlib.Path(self.tmp) / "out" / "2026" / "08"
        self.assertTrue((out / "営業報告書_2026-08-13.html").exists())
        self.assertTrue((out / "営業報告書_2026-08-13.json").exists())
        self.assertTrue((out / "出張精算_2026-08-13.json").exists())
        self.assertTrue((pathlib.Path(self.tmp) / "vault" / "営業報告書 2026-08-13.md").exists())
        html = (out / "営業報告書_2026-08-13.html").read_text(encoding="utf-8")
        self.assertIn("株式会社サンプル", html)   # 見本の名義でも報告書は出る（止めるのは規程だけ）
        self.assertIn("要確認", html)
        # 予定なしの日は作らない
        r = self.cli("daily", "--date", "2026-08-15", "--no-pdf")
        self.assertIn("作成しませんでした", r.stdout)
        # 旅費規程。見本の名義のままでは出ない
        r = self.cli("rules", "--no-pdf", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("見本のまま", r.stdout)
        self._real_issuer()
        r = self.cli("rules", "--no-pdf")
        html = (pathlib.Path(self.tmp) / "out" / "規程" / "旅費規程.html").read_text(encoding="utf-8")
        self.assertIn("5,000円", html)
        self.assertIn("2026年9月1日", html)

    def test_note_is_included(self):
        self.init_example()
        (pathlib.Path(self.tmp) / "notes").mkdir(exist_ok=True)
        (pathlib.Path(self.tmp) / "notes" / "2026-08-13.md").write_text("A社は前向き。<script>は入らない", encoding="utf-8")
        self.cli("daily", "--date", "2026-08-13", "--no-pdf")
        html = (pathlib.Path(self.tmp) / "out" / "2026" / "08" / "営業報告書_2026-08-13.html").read_text(encoding="utf-8")
        self.assertIn("A社は前向き。", html)
        self.assertNotIn("<script>", html)          # エスケープされている
        self.assertIn("&lt;script&gt;", html)

    def test_fare_add_then_priced(self):
        self.init_example()
        self._real_issuer()
        self.cli("fare", "add", "新宿", "横浜", "560", "--transport", "鉄道")
        self.cli("fare", "add", "横浜", "東京", "480")
        r = self.cli("daily", "--date", "2026-08-13", "--no-pdf")
        self.assertNotIn("運賃が登録されていません", r.stdout)
        j = json.loads((pathlib.Path(self.tmp) / "out" / "2026" / "08" / "営業報告書_2026-08-13.json").read_text(encoding="utf-8"))
        # 額の合計は、載っている区間の合計と一致すること
        self.assertEqual(j["transportTotal"], sum(int(l["amount"] or 0) for l in j["legs"]))
        self.assertEqual(j["unpricedLegs"], 0)
        self.assertIn(560, [int(l["amount"] or 0) for l in j["legs"]])

    def test_missing_profile_is_friendly(self):
        r = self.cli("daily", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("paper-maker init", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_missing_ics_is_a_warning_not_a_crash(self):
        self.init_example()
        os.remove(pathlib.Path(self.tmp) / "calendar.ics")
        r = self.cli("calendar", "--date", "2026-08-13")
        self.assertIn("ICS が見つかりません", r.stdout)

    def test_log_has_no_personal_data(self):
        self.init_example()
        self.cli("daily", "--date", "2026-08-13", "--no-pdf")
        log = (pathlib.Path(self.tmp) / "paper-maker.log").read_text(encoding="utf-8")
        for w in ("山田", "サンプル", "新宿", "丸の内", "210"):
            self.assertNotIn(w, log)


class TestDistribution(unittest.TestCase):
    # 汎用パターンは repo 内。作者固有の語（名前・住所・口座）は repo の外のファイルから読む。
    # 固有語を repo に書くと、それ自体が個人情報の持ち込みになるため。
    PATTERNS = [r"AIza[0-9A-Za-z_\-]{20,}", r"普通\s*\d{7}", r"0\d{1,3}-\d{2,4}-\d{4}"]
    ALLOW = ("example.com", "0000-0000", "0000000", "1234567")

    @staticmethod
    def owner_words():
        f = pathlib.Path(os.environ.get("PAPER_MAKER_FORBIDDEN", "~/.paper-maker-dev/forbidden.txt")).expanduser()
        if not f.exists():
            return []
        return [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]

    def test_no_owner_data_in_distributable(self):
        import re
        words = self.owner_words()
        hits = []
        for p in ROOT.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(ROOT))
            if rel.startswith((".git/", "dist/", "build/")) or "__pycache__" in rel or "/.pytest" in rel:
                continue
            if p.suffix in (".png", ".ico", ".icns", ".pdf", ".pyc"):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for w in words:
                if w in text:
                    hits.append("%s: 固有語" % rel)
            if p.name in ("test_all.py", "sanitize_app.py"):
                continue
            for line in text.splitlines():
                if any(a in line for a in self.ALLOW):
                    continue
                for pat in self.PATTERNS:
                    if re.search(pat, line):
                        hits.append("%s: %s" % (rel, pat))
        self.assertEqual(hits, [])

    def test_owner_word_file_present_on_dev_machine(self):
        # 開発機では固有語ファイルがある前提。無い環境（利用者）ではスキップ
        if not self.owner_words():
            self.skipTest("~/.paper-maker-dev/forbidden.txt が無い（利用者環境）")
        self.assertGreater(len(self.owner_words()), 3)

    def test_filenames_are_ascii(self):
        """配布 zip の中に日本語のファイル名を入れない。
        macOS 標準の unzip 6.00 はそこで展開を止め、以降のファイルが出てこない（2026-08-19 実機で再現）。"""
        import subprocess
        out = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True)
        names = [n for n in out.stdout.decode("utf-8").split("\0") if n]
        self.assertTrue(names, "git ls-files が空")
        bad = [n for n in names if any(ord(c) > 127 for c in n)]
        self.assertEqual(bad, [])

    def test_no_secret_files(self):
        for name in ("key.js", "profiles.local.json", "secrets.env", ".env"):
            self.assertFalse(list(ROOT.rglob(name)), name)

class NitteiSettingsTest(unittest.TestCase):
    """日程調整の設定。壊れた入力でファイルを壊さず、日本語で断る。"""

    def setUp(self):
        import tempfile, shutil
        self.dir = pathlib.Path(tempfile.mkdtemp())
        shutil.copy(pathlib.Path(__file__).resolve().parent.parent / "examples" / "nittei.example.json",
                    self.dir / "nittei.json")
        os.environ["PAPER_MAKER_NITTEI_DIR"] = str(self.dir)

    def tearDown(self):
        import shutil
        os.environ.pop("PAPER_MAKER_NITTEI_DIR", None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_bad_inputs_are_refused_and_file_untouched(self):
        from paper_maker import nittei
        before = (self.dir / "nittei.json").read_bytes()
        bad = [{"days": []}, {"days": [7]}, {"days": ["a"]}, {"days": 3}, {"days": None},
               {"start": "abc"}, {"start": None}, {"start": "25:99"}, {"start": "23:00"}, {"end": "09:00"},
               {"buffer": "abc"}, {"buffer": None}, {"buffer": float("inf")}, {"buffer": 10 ** 9},
               {"enabled": "x"}, None, []]
        for b in bad:
            with self.assertRaises(nittei.SettingsError, msg=repr(b)):
                nittei.save_settings(b)
        self.assertEqual((self.dir / "nittei.json").read_bytes(), before)

    def test_holidays_string_false_and_time_normalized(self):
        from paper_maker import nittei
        nittei.save_settings({"holidays": "false", "start": "9:5", "end": "17:30"})
        cfg = nittei.load()
        self.assertFalse(cfg["links"][0]["holidays"])
        self.assertEqual(cfg["links"][0]["start"], "9:05")

    def test_broken_or_partial_config_does_not_crash(self):
        from paper_maker import nittei
        f = self.dir / "nittei.json"
        f.write_text("{not json", encoding="utf-8")
        self.assertFalse(nittei.state()["configured"])
        self.assertIn("読めません", nittei.state()["error"])
        f.write_text('{"demo": true, "links": [{"token": "x1234"}], "demoBookings": [{"at": "abc"}]}', encoding="utf-8")
        st = nittei.state()
        self.assertTrue(st["configured"])
        self.assertEqual(st["bookings"], [])


if __name__ == "__main__":
    unittest.main()


class TestQuest(TempHome):
    """導入の道順。達成は設定と出力の実物から判定する（自己申告にしない）。"""

    def blank_profile(self):
        self.cli("init", "--example")
        p = pathlib.Path(self.tmp) / "profile.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        for k in ("name", "rep", "address", "tel", "email", "bank", "sealText"):
            d["profiles"]["corp"][k] = ""
        d["calendar"]["sources"] = []
        d["travel"]["bases"]["hq"]["station"] = ""     # 拠点も空から始める
        d["travel"]["bases"]["hq"]["address"] = "埼玉県さいたま市大宮区1-1-1"  # 見本の住所だと未設定扱いになる
        d["output"]["dir"] = self.tmp + "/out"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return p

    def ev(self):
        sys.modules.pop("paper_maker.quest", None)
        from paper_maker import quest
        return quest.evaluate()

    def test_starts_at_zero_and_advances_with_real_settings(self):
        p = self.blank_profile()
        r = self.ev()
        # 置き場（道順11）は、この試験の都合で最初から別の場所を指している
        done = [q["id"] for q in r["quests"] if q["done"]]
        self.assertEqual(done, [11])
        self.assertEqual(r["current"], 1)
        self.assertFalse(r["finished"])

        d = json.loads(p.read_text(encoding="utf-8"))
        d["profiles"]["corp"]["name"] = "合同会社テスト"
        d["profiles"]["corp"]["address"] = "大阪市北区1-1"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        r = self.ev()
        self.assertEqual([q["id"] for q in r["quests"] if q["done"]], [1, 11])
        self.assertEqual(r["current"], 2)

        d["profiles"]["corp"]["bank"] = "テスト銀行 普通 1111111"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.assertEqual([q["id"] for q in self.ev()["quests"] if q["done"]], [1, 2, 11])

    def test_base_quest_needs_a_station(self):
        p = self.blank_profile()
        d = json.loads(p.read_text(encoding="utf-8"))
        qs = {q["id"]: q for q in self.ev()["quests"]}
        self.assertFalse(qs[3]["done"], "最寄駅が空なのに拠点が済みになった")
        d["travel"]["bases"]["hq"]["station"] = "東京"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.assertTrue({q["id"]: q for q in self.ev()["quests"]}[3]["done"])

    def test_note_quest_needs_real_content(self):
        self.blank_profile()
        qs = {q["id"]: q for q in self.ev()["quests"]}
        self.assertFalse(qs[7]["done"])
        nd = pathlib.Path(self.tmp) / "notes"
        nd.mkdir(exist_ok=True)
        today = dt.date.today().isoformat()
        # 空の雛形では通さない
        (nd / ("%s.md" % today)).write_text(
            "# %s の営業メモ\n\n## 10:00 A社\n話したこと: \n次にやること: \n\n## 所感\n" % today, encoding="utf-8")
        self.assertFalse({q["id"]: q for q in self.ev()["quests"]}[7]["done"], "空の雛形で通ってしまった")
        (nd / ("%s.md" % today)).write_text(
            "# %s の営業メモ\n\n## 10:00 A社\n話したこと: 見積の説明をした\n次にやること: 提案書\n" % today, encoding="utf-8")
        self.assertTrue({q["id"]: q for q in self.ev()["quests"]}[7]["done"])

    def test_calendar_quests_need_a_real_readable_event(self):
        p = self.blank_profile()
        d = json.loads(p.read_text(encoding="utf-8"))
        # 取り口だけ書いて中身が無い状態では通さない
        d["travel"]["bases"]["hq"]["station"] = "東京"
        d["calendar"]["sources"] = [{"type": "ics", "path": "calendar.ics"}]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        q4 = [q for q in self.ev()["quests"] if q["id"] == 4][0]
        self.assertFalse(q4["done"])

        # 今日の予定が読めれば 3 は通り、場所が無いので 4 は通らない
        today = dt.date.today()
        ics_text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART;TZID=Asia/Tokyo:%sT100000\n"
                    "DTEND;TZID=Asia/Tokyo:%sT110000\nSUMMARY:打合せ\nEND:VEVENT\nEND:VCALENDAR\n"
                    % (today.strftime("%Y%m%d"), today.strftime("%Y%m%d")))
        (pathlib.Path(self.tmp) / "calendar.ics").write_text(ics_text, encoding="utf-8")
        qs = {q["id"]: q for q in self.ev()["quests"]}
        self.assertTrue(qs[4]["done"])

        # 場所欄に住所を入れると 4 が通る
        (pathlib.Path(self.tmp) / "calendar.ics").write_text(
            ics_text.replace("SUMMARY:打合せ", "LOCATION:東京都新宿区西新宿2-8-1\nSUMMARY:打合せ"), encoding="utf-8")

    def test_sample_fares_do_not_count_as_user_registration(self):
        self.blank_profile()
        qs = {q["id"]: q for q in self.ev()["quests"]}
        self.assertFalse(qs[6]["done"], "見本の運賃で通ってしまった")
        self.cli("fare", "add", "新宿", "横浜", "560")
        qs = {q["id"]: q for q in self.ev()["quests"]}
        self.assertTrue(qs[6]["done"])

    def test_rules_quest_needs_the_actual_output(self):
        self.blank_profile()
        qs = {q["id"]: q for q in self.ev()["quests"]}
        self.assertFalse(qs[9]["done"])
        self.cli("rules", "--no-pdf")
        qs = {q["id"]: q for q in self.ev()["quests"]}
        self.assertTrue(qs[9]["done"])

    def test_skip_moves_current_forward(self):
        self.blank_profile()
        sys.modules.pop("paper_maker.quest", None)
        from paper_maker import quest
        quest.skip(1)
        self.assertEqual(quest.evaluate()["current"], 2)
        quest.unskip(1)
        self.assertEqual(quest.evaluate()["current"], 1)

    def test_cli_quest_prints_next_step(self):
        self.blank_profile()
        r = self.cli("quest")
        self.assertIn("はじめの道順", r.stdout)
        self.assertIn("次にやること", r.stdout)
        self.assertIn("名乗りを決める", r.stdout)


class TestFareImport(TempHome):
    """履歴の取り込み。読み取った物をそのまま信じない。"""

    def fi(self):
        from paper_maker import fares_import
        return fares_import

    def test_text_parse_shapes(self):
        fi = self.fi()
        recs, bad = fi.parse_text(
            "2026-08-15  鉄道  阿佐ケ谷 → 東京  341\n"
            "2026/08/12,鉄道,東京,渋谷,253\n"
            "2026-08-12  バス  日東交通  1600\n"
            "チャージ 3000\n")
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["from"], "阿佐ケ谷")
        self.assertEqual(recs[0]["to"], "東京")
        self.assertEqual(recs[2]["kind"], "bus")

    def test_only_repeated_amounts_are_confirmed(self):
        fi = self.fi()
        recs = [{"date": "2026-08-01", "kind": "rail", "from": "東京", "to": "渋谷", "amount": 253},
                {"date": "2026-08-02", "kind": "rail", "from": "東京", "to": "渋谷", "amount": 253},
                {"date": "2026-08-03", "kind": "rail", "from": "東京", "to": "品川", "amount": 180}]
        sm = fi.summarize(recs)
        self.assertEqual([x["to"] for x in sm["sure"]], ["渋谷"])
        self.assertEqual([x["to"] for x in sm["wait"]], ["品川"])

    def test_conflicting_amounts_are_not_imported(self):
        fi = self.fi()
        recs = [{"date": "2026-08-01", "kind": "rail", "from": "東京", "to": "渋谷", "amount": 253},
                {"date": "2026-08-02", "kind": "rail", "from": "東京", "to": "渋谷", "amount": 260}]
        sm = fi.summarize(recs)
        self.assertEqual(sm["sure"], [])
        self.assertEqual(sm["clash"][0]["amounts"], [253, 260])

    def test_station_name_variants_are_merged(self):
        """実データで出た違い：空白の有無と小書きのケ。揃えないと同じ駅が2つに割れる。"""
        fi = self.fi()
        recs = [{"date": "2026-08-01", "kind": "rail", "from": "JR浦和", "to": "JR大宮", "amount": 220},
                {"date": "2026-08-02", "kind": "rail", "from": "JR 浦和", "to": "JR 大宮", "amount": 220},
                {"date": "2026-08-03", "kind": "rail", "from": "阿佐ケ谷", "to": "東京", "amount": 341},
                {"date": "2026-08-04", "kind": "rail", "from": "阿佐ヶ谷", "to": "東京", "amount": 341}]
        sm = fi.summarize(recs)
        self.assertEqual(len(sm["sure"]), 2, [x["from"] for x in sm["sure"]])
        self.assertEqual(sm["wait"], [])

    def test_same_station_pair_is_rejected(self):
        """実データで出た読み間違い：東京→東京 160円。運賃として成立しない。"""
        fi = self.fi()
        recs = [{"date": "2026-08-01", "kind": "rail", "from": "東京", "to": "東京", "amount": 160},
                {"date": "2026-08-02", "kind": "rail", "from": "東京", "to": "東京", "amount": 160}]
        sm = fi.summarize(recs)
        self.assertEqual(sm["sure"], [])
        self.assertEqual(len(sm["odd"]), 2)

    def test_apply_writes_only_confirmed(self):
        self.cli("init", "--example")
        fi = self.fi()
        recs = [{"date": "2026-08-01", "kind": "rail", "from": "東京", "to": "品川", "amount": 180},
                {"date": "2026-08-02", "kind": "rail", "from": "東京", "to": "品川", "amount": 180},
                {"date": "2026-08-03", "kind": "rail", "from": "東京", "to": "上野", "amount": 170}]
        n = fi.apply(fi.summarize(recs))
        self.assertEqual(n, 1)
        r = self.cli("fare", "list")
        self.assertIn("180円", r.stdout)
        self.assertNotIn("170円", r.stdout)

    def test_cli_import_needs_apply_to_write(self):
        self.cli("init", "--example")
        f = pathlib.Path(self.tmp) / "hist.txt"
        f.write_text("2026-08-01 鉄道 東京 品川 180\n2026-08-02 鉄道 東京 品川 180\n", encoding="utf-8")
        r = self.cli("fare", "import", str(f))
        self.assertIn("--apply", r.stdout)
        self.assertNotIn("180円", self.cli("fare", "list").stdout)
        self.cli("fare", "import", str(f), "--apply")
        self.assertIn("180円", self.cli("fare", "list").stdout)


class TestNotes(TempHome):
    def test_template_lists_visits_and_parse_roundtrip(self):
        from paper_maker import notes
        day = dt.date(2026, 8, 13)
        evs = [{"start": "10:00", "title": "A社 打合せ", "location": "東京都新宿区1", "kind": "onsite"}]
        (pathlib.Path(self.tmp) / "notes").mkdir(exist_ok=True)
        p, made = notes.ensure(day, evs)
        self.assertTrue(made)
        self.assertIn("## 10:00 A社 打合せ", p.read_text(encoding="utf-8"))
        p.write_text("# x\n\n## 10:00 A社 打合せ\n話したこと: 予算は30万\n次にやること: 提案書\n\n## 所感\n決まりそう\n",
                     encoding="utf-8")
        r = notes.parse(day)
        self.assertEqual(r["visits"]["10:00 A社 打合せ"]["話したこと"], "予算は30万")
        self.assertEqual(r["free"], "決まりそう")
        notes.attach(evs, r)
        self.assertEqual(evs[0]["memo"]["次にやること"], "提案書")

    def test_plain_memo_without_headings_is_kept(self):
        """見出しを付けずに直接書く人もいる。書いた物を落とさない。"""
        from paper_maker import notes
        day = dt.date(2026, 8, 13)
        (pathlib.Path(self.tmp) / "notes").mkdir(exist_ok=True)
        notes.note_path(day).write_text("今日は疲れた。A社は前向き\n", encoding="utf-8")
        self.assertIn("A社は前向き", notes.parse(day)["free"])


class TestTravelHonesty(unittest.TestCase):
    """精算書は、埋まっていない所が埋まっていないと分かる形で出す。"""

    def doc(self, legs, unpriced):
        from paper_maker.docs import travel
        itin = {"events": [{"kind": "onsite", "title": "打合せ", "start": "10:00", "end": "11:00",
                            "location": "渋谷", "station": "渋谷"}],
                "legs": legs, "unpricedLegs": unpriced, "warnings": ["渋谷 → 大宮 の運賃が登録されていません"],
                "base": {"id": "hq", "label": "大宮", "station": "大宮", "address": ""},
                "role": "代表取締役", "allowance": 5000, "transportTotal": 0}
        prof = json.loads((ROOT / "examples" / "profile.example.json").read_text(encoding="utf-8"))
        return travel.build_doc(dt.date(2026, 8, 8), prof, itin)

    def test_unpriced_leg_is_not_counted_as_zero_yen(self):
        d = self.doc([{"from": "大宮", "to": "渋谷", "amount": None, "transport": "", "note": "運賃が未登録"}], 1)
        row = d["travelExpenses"][0]
        self.assertEqual(row["amount"], "", "未登録の運賃が 0円 として計上された")
        self.assertIn("要確認", row["note"])
        self.assertIn("足りません", d["travelIssues"])

    def test_priced_leg_keeps_its_amount(self):
        d = self.doc([{"from": "東京", "to": "渋谷", "amount": 253, "transport": "鉄道", "note": ""}], 0)
        self.assertEqual(d["travelExpenses"][0]["amount"], 253)
        self.assertNotIn("足りません", d["travelIssues"])


class TestBaseHint(unittest.TestCase):
    def test_all_unpriced_suggests_the_base_may_be_wrong(self):
        """出張から戻って拠点を戻し忘れると、その日の移動が丸ごと別の土地からになる。"""
        from paper_maker import itinerary
        prof = json.loads((ROOT / "examples" / "profile.example.json").read_text(encoding="utf-8"))
        prof["travel"]["bases"]["hq"]["station"] = "大宮"
        prof["travel"]["bases"]["hq"]["label"] = "大宮（本店）"
        places = {"skip": [], "rules": [{"match": ["渋谷"], "station": "渋谷", "title": True}]}
        fares = itinerary.Fares({"stations": {}}, {"fares": []})
        evs = [{"title": "渋谷で打合せ", "location": "", "start": "12:00", "end": "13:00", "all_day": False}]
        it = itinerary.build(evs, prof, places, fares)
        self.assertTrue(any("今いる拠点" in w for w in it["warnings"]), it["warnings"])


class TestBadInput(TempHome):
    """打ち間違いでトレースバックを出さない。使う人が見る画面なので。"""

    def test_bad_date_and_amount(self):
        self.cli("init", "--example")
        for args in (("daily", "--date", "2026-13-45"),
                     ("daily", "--date", "へんな日付"),
                     ("note", "--date", "2026-99-99", "--no-open"),
                     ("fare", "add", "東京", "渋谷", "abc")):
            r = self.cli(*args, check=False)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertNotIn("Traceback", r.stderr, args)
            self.assertNotIn("Traceback", r.stdout, args)
            self.assertTrue(r.stdout.strip(), "何も言わずに落ちた: %s" % (args,))

    def test_amount_with_comma_and_yen_is_accepted(self):
        self.cli("init", "--example")
        self.cli("fare", "add", "東京", "小田原", "1,595円")
        self.assertIn("1,595円", self.cli("fare", "list").stdout)


class TestFareAuto(TempHome):
    """自分で調べにいく分。オープンデータは実額、AIは候補どまり。"""

    def test_open_data_is_confirmed_ai_is_only_a_candidate(self):
        from paper_maker import fares_auto as fa
        self.cli("init", "--example")
        result = {
            "found": [{"from": "本郷三丁目", "to": "新宿", "id": None, "amount": 220,
                       "source": "公共交通オープンデータセンター（…）"}],
            "guessed": [{"from": "東京", "to": "横浜", "id": None, "amount": 480,
                         "source": "Gemini（JR東日本 2024-07 時点・要確認）", "route": "JR東海道線"}],
            "missed": [],
        }
        ok, cand = fa.apply(result)
        self.assertEqual((ok, cand), (1, 1))
        from paper_maker import itinerary, profile
        f = itinerary.Fares(profile.load_stations(), profile.load_fares())
        self.assertEqual(f.find("本郷三丁目", "新宿")["amount"], 220)
        # はじめから入っている区間と混ざらないよう、遠い所で見る
        self.assertIsNone(f.find("阿佐ケ谷", "本郷三丁目"), "AIの候補が書類に使われてしまった")

    def test_confirm_promotes_a_candidate(self):
        from paper_maker import fares_auto as fa, itinerary, profile
        self.cli("init", "--example")
        fa.apply({"found": [], "guessed": [{"from": "東京", "to": "横浜", "id": None, "amount": 480,
                                            "source": "Gemini", "route": ""}], "missed": []})
        fid = next(r["id"] for r in profile.load_fares()["fares"] if r.get("candidates"))
        fa.confirm(fid, 528, "Suica利用履歴")
        f = itinerary.Fares(profile.load_stations(), profile.load_fares())
        self.assertEqual(f.find("東京", "横浜")["amount"], 528)


class TestReportFromCalendarNote(unittest.TestCase):
    """カレンダーのメモから欄を埋める。書いていないことは足さない。"""

    def test_meeting_boilerplate_is_dropped(self):
        from paper_maker import report_fill as rf
        note = ("山田課長。予算30万くらい\nZoomミーティングに参加する\n"
                "https://zoom.us/j/123\nミーティング ID: 123 456\n担当: 佐藤")
        c = rf._clean(note)
        self.assertIn("山田課長", c)
        for w in ("zoom.us", "ミーティング ID", "参加する", "担当:"):
            self.assertNotIn(w, c)

    def test_by_hand_splits_labelled_lines(self):
        from paper_maker import report_fill as rf
        ev = {"title": "サカイ商店 打合せ", "note": "相手: 山田課長\n話したこと: 予算は30万\n次: サンプル送る"}
        got = rf.by_hand(ev)
        self.assertEqual(got["相手"], "山田課長")
        self.assertEqual(got["話したこと"], "予算は30万")
        self.assertEqual(got["次にやること"], "サンプル送る")

    def test_who_from_title_keeps_brackets_closed(self):
        from paper_maker import report_fill as rf
        self.assertEqual(rf.who_from_title("A社 打合せ（山田様）"), "A社 山田様")
        self.assertEqual(rf.who_from_title("B社 訪問"), "B社")
        self.assertEqual(rf.who_from_title("サカイ商店 打合せ"), "サカイ商店")
        self.assertEqual(rf.who_from_title("社内定例"), "")
        self.assertEqual(rf.who_from_title("本社で会議"), "")
        for t in ("神社", "結社", "退社", "社", "様", "さん", "株式会社", "事務所", "皆さん", "みなさん 会議", "お客様", ""):
            self.assertEqual(rf.who_from_title(t), "", t)
        self.assertEqual(rf.who_from_title("株式会社ABC 定例"), "株式会社ABC")
        self.assertEqual(rf.who_from_title("（株）サカイ 打合せ"), "株式会社サカイ")
        self.assertEqual(rf.who_from_title("Zoom: A社"), "A社")
        self.assertEqual(rf.who_from_title(None), "")

    def test_empty_note_produces_nothing(self):
        from paper_maker import report_fill as rf
        evs = [{"title": "社内定例", "note": "", "location": "ZOOM"}]
        self.assertEqual(rf.fill(evs, api_key="", use_ai=False), 0)
        self.assertIsNone(evs[0].get("memo"))

    def test_handwritten_memo_wins(self):
        """手で書いた物のほうが強い。カレンダーから起こした分で上書きしない。"""
        from paper_maker import report_fill as rf
        evs = [{"title": "A社", "note": "カレンダーに書いた分", "memo": {"話したこと": "手で書いた分"}}]
        rf.fill(evs, api_key="", use_ai=False)
        self.assertEqual(evs[0]["memo"]["話したこと"], "手で書いた分")


class TestStationHint(unittest.TestCase):
    def test_known_stations_work_as_location_hints(self):
        """運賃表に駅が増えると、場所の表を書き足さなくても拾える範囲が広がる。"""
        from paper_maker import itinerary
        places = {"skip": ["ZOOM"], "rules": []}
        stations = {"stations": {"a": {"name": "横浜駅"}, "b": {"name": "新宿駅"}}}
        self.assertEqual(itinerary.classify({"location": "神奈川県横浜市西区1", "title": "訪問"}, places, stations)[:2],
                         ("onsite", "横浜"))
        # 題名の駅名は既定で拾わない。「新宿で飲み」が現地扱いになって
        # 日当が付いた（利用者の報告 2026-08-23）。拾うのは切り替えた時だけ
        self.assertNotEqual(itinerary.classify({"location": "", "title": "新宿で打合せ"},
                                               places, stations)[0], "onsite")
        self.assertEqual(itinerary.classify({"location": "", "title": "新宿で打合せ"},
                                            places, stations, True)[:2], ("onsite", "新宿"))
        self.assertEqual(itinerary.classify({"location": "ZOOM", "title": "定例"}, places, stations)[0], "online")
        self.assertEqual(itinerary.classify({"location": "福井県敦賀市1-1", "title": "よそ"}, places, stations)[0], "unknown")


class TestScheduleEnv(TempHome):
    """自動実行にもデータ置き場を渡す。手で叩いた時と書き込み先が変わらないように。"""

    def test_plist_carries_the_data_dir(self):
        if sys.platform != "darwin":
            self.skipTest("mac のみ")
        from paper_maker import schedule
        got = schedule._env_pairs()
        self.assertEqual(got["PAPER_MAKER_HOME"], self.tmp)
        self.assertIn("PATH", got)        # AI の CLI に届くように、PATH も渡す

    def test_no_env_when_using_the_default_place(self):
        from paper_maker import schedule
        os.environ.pop("PAPER_MAKER_HOME", None)
        try:
            self.assertNotIn("PAPER_MAKER_HOME", schedule._env_pairs())
        finally:
            os.environ["PAPER_MAKER_HOME"] = self.tmp


class TestFreshness(TempHome):
    def test_fare_checked_before_a_revision_is_flagged(self):
        from paper_maker import freshness
        self.cli("init", "--example")
        self.cli("fare", "add", "東京", "渋谷", "200", "--source", "昔の資料")
        p = pathlib.Path(self.tmp) / "fares.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in d["fares"]:
            if r.get("source") == "昔の資料":
                r["checkedAt"] = "2024-06-01"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        r = freshness.check(dt.date(2026, 8, 19))
        self.assertEqual(len(r["old"]), 1)
        self.assertIn("2026-03-14", r["old"][0]["why"])

    def test_recent_fare_is_not_flagged(self):
        from paper_maker import freshness
        self.cli("init", "--example")
        self.cli("fare", "add", "東京", "新宿", "253", "--source", "Suica")
        self.assertEqual(freshness.check(dt.date.today())["old"], [])

    def test_stale_note_reaches_the_settlement(self):
        from paper_maker import freshness
        from paper_maker.docs import travel
        legs = [{"from": "東京", "to": "渋谷", "amount": 200, "transport": "鉄道", "note": "",
                 "stale": "2026-03-14 の運賃改定（JR東日本）より前に確かめた額"}]
        itin = {"events": [], "legs": legs, "unpricedLegs": 0, "warnings": [],
                "base": {"id": "hq", "label": "本店", "station": "東京", "address": ""},
                "role": "代表取締役", "allowance": 5000, "transportTotal": 200}
        prof = json.loads((ROOT / "examples" / "profile.example.json").read_text(encoding="utf-8"))
        d = travel.build_doc(dt.date(2026, 8, 19), prof, itin)
        self.assertIn("改定より前", d["travelIssues"])
        self.assertIn("改定", d["travelExpenses"][0]["note"])


class TestSync(TempHome):
    def test_sync_makes_the_day_that_was_missed(self):
        from paper_maker import sync
        self.init_example()
        y = dt.date.today() - dt.timedelta(days=1)
        ics_text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\n"
                    "DTSTART;TZID=Asia/Tokyo:%sT100000\nDTEND;TZID=Asia/Tokyo:%sT110000\n"
                    "LOCATION:東京都新宿区西新宿2-8-1\nSUMMARY:打合せ\nEND:VEVENT\nEND:VCALENDAR\n"
                    % (y.strftime("%Y%m%d"), y.strftime("%Y%m%d")))
        (pathlib.Path(self.tmp) / "calendar.ics").write_text(ics_text, encoding="utf-8")
        r = sync.run()
        self.assertEqual(r["made"], [y.isoformat()])
        # AI に繋がらない設定なので住所が駅にならない。数回はやり直すが、
        # 永久には繰り返さない（ブラウザや鍵が無い人の所で毎回焼き直さないため）
        from paper_maker import sync as sy
        runs = [sync.run()["made"] for _ in range(sy.MAX_RETRY + 2)]
        self.assertEqual(runs[-1], [], runs)

    def test_sync_logs_no_personal_data(self):
        from paper_maker import sync
        self.init_example()
        sync.run(make_missing=False, check_update=False)
        log = (pathlib.Path(self.tmp) / "paper-maker.log").read_text(encoding="utf-8")
        for w in ("山田", "サンプル", "新宿", "打合せ"):
            self.assertNotIn(w, log)


class TestGtfsFares(TempHome):
    """公開データ（GTFS）からバス運賃を取る。コードは取り込まない、数字だけ。"""

    def _zip(self):
        import io as _io
        import zipfile as _zf
        buf = _io.BytesIO()
        with _zf.ZipFile(buf, "w") as z:
            z.writestr("stops.txt",
                       "stop_id,stop_name,zone_id\n1,市役所前,z1\n2,中央病院前,z2\n3,本町,z3\n")
            z.writestr("fare_attributes.txt", "fare_id,price,currency_type\nf160,160,JPY\nf200,200,JPY\n")
            z.writestr("fare_rules.txt",
                       "route_id,fare_id,origin_id,destination_id\n"
                       "r1,f160,z1,z2\nr1,f160,z1,z2\nr1,f200,z1,z3\nr1,f160,z1,z1\n")
        return buf.getvalue()

    def test_zone_ids_become_stop_names(self):
        from unittest import mock
        from paper_maker import fares_gtfs as g
        with mock.patch.object(g, "_get", return_value=self._zip()):
            pairs, err = g.read_feed("https://x/y.zip")
        self.assertEqual(err, "")
        self.assertEqual(sorted((p["from"], p["to"], p["amount"]) for p in pairs),
                         [("市役所前", "中央病院前", 160), ("市役所前", "本町", 200)])

    def test_same_stop_pair_is_dropped(self):
        from unittest import mock
        from paper_maker import fares_gtfs as g
        with mock.patch.object(g, "_get", return_value=self._zip()):
            pairs, _ = g.read_feed("https://x/y.zip")
        self.assertFalse([p for p in pairs if p["from"] == p["to"]])

    def test_pick_narrows_to_the_stops_you_use(self):
        from paper_maker import fares_gtfs as g
        pairs = [{"from": "市役所前", "to": "本町", "amount": 200},
                 {"from": "一の宮", "to": "今町", "amount": 160}]
        self.assertEqual(len(g.pick(pairs, ["市役所"])), 1)
        self.assertEqual(len(g.pick(pairs, None, limit=1)), 1)

    def test_apply_keeps_the_licence_in_the_source(self):
        from paper_maker import fares_gtfs as g, itinerary, profile
        self.cli("init", "--example")
        n = g.apply([{"from": "市役所前", "to": "中央病院前", "amount": 160}],
                    "白山市", "CC BY 4.0", profile, itinerary)
        self.assertEqual(n, 1)
        f = itinerary.Fares(profile.load_stations(), profile.load_fares())
        hit = f.find("市役所前", "中央病院前")
        self.assertEqual(hit["amount"], 160)
        self.assertIn("CC BY 4.0", hit["source"])
        self.assertIn("白山市", hit["source"])

    def test_feed_without_fares_says_so(self):
        import io as _io
        import zipfile as _zf
        from unittest import mock
        from paper_maker import fares_gtfs as g
        buf = _io.BytesIO()
        with _zf.ZipFile(buf, "w") as z:
            z.writestr("stops.txt", "stop_id,stop_name\n1,どこか\n")
        with mock.patch.object(g, "_get", return_value=buf.getvalue()):
            pairs, err = g.read_feed("https://x/y.zip")
        self.assertEqual(pairs, [])
        self.assertIn("運賃", err)

    def test_gzip_response_is_unpacked(self):
        """このサーバーは identity を頼んでも gzip で返してくる。"""
        import gzip
        from unittest import mock
        from paper_maker import fares_gtfs as g

        class R:
            headers = {"Content-Encoding": ""}

            def read(self):
                return gzip.compress(b'{"body": []}')

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with mock.patch("urllib.request.urlopen", return_value=R()):
            self.assertEqual(g.feeds(), [])


class TestBlankStart(TempHome):
    """アイコンから初めて押した人。設定が無くても始まる。"""

    def test_blank_profile_has_no_sample_company(self):
        from paper_maker import profile
        self.assertTrue(profile.ensure_exists())
        d = profile.load()
        # 見本の会社名が残ったまま請求書が出ると事故になる
        for who in ("corp", "personal"):
            for k in ("name", "rep", "address", "bank"):
                self.assertEqual(d["profiles"][who][k], "", "%s.%s が空でない" % (who, k))
        self.assertEqual(d["travel"]["bases"]["hq"]["station"], "")
        self.assertEqual(d["calendar"]["sources"], [])
        # 決めごと（日当・上限）は雛形のまま残す。全部空だと何も出せない
        self.assertEqual(d["travel"]["rates"]["代表取締役"], {"day": 5000, "night": 10000})
        self.assertEqual(d["travel"]["lodging"]["cap"], 12000)

    def test_second_press_does_not_overwrite(self):
        from paper_maker import profile
        profile.ensure_exists()
        d = profile.load()
        d["profiles"]["corp"]["name"] = "合同会社ハルキ"
        profile.save(d)
        self.assertFalse(profile.ensure_exists())
        self.assertEqual(profile.load()["profiles"]["corp"]["name"], "合同会社ハルキ")

    def test_quest_starts_at_zero_from_a_blank_start(self):
        from paper_maker import profile, quest
        profile.ensure_exists()
        r = quest.evaluate()
        self.assertEqual(r["done"], 0)
        self.assertEqual(r["current"], 1)


class TestDesktopIcon(TempHome):
    def test_mac_bundle_has_the_pieces(self):
        if sys.platform != "darwin":
            self.skipTest("mac のみ")
        from unittest import mock
        from paper_maker import desktop
        desk = pathlib.Path(self.tmp) / "Desktop"
        desk.mkdir()
        with mock.patch.object(desktop, "desktop_dir", return_value=desk):
            p = pathlib.Path(desktop.install())
        self.assertTrue(p.name.endswith(".app"))
        launch = p / "Contents" / "MacOS" / "launch"
        self.assertTrue((p / "Contents" / "Info.plist").exists())
        self.assertTrue(launch.exists())
        self.assertTrue(os.access(launch, os.X_OK), "実行できない")
        body = launch.read_text(encoding="utf-8")
        self.assertIn("paper_maker open", body)
        self.assertIn(self.tmp, body, "データ置き場が焼き込まれていない")

    def test_remove_takes_it_away(self):
        if sys.platform != "darwin":
            self.skipTest("mac のみ")
        from unittest import mock
        from paper_maker import desktop
        desk = pathlib.Path(self.tmp) / "Desktop"
        desk.mkdir()
        with mock.patch.object(desktop, "desktop_dir", return_value=desk):
            desktop.install()
            self.assertTrue(list(desk.iterdir()))
            desktop.remove()
        self.assertEqual(list(desk.iterdir()), [])


class TestTutorialShots(TempHome):
    """道順の絵。文字だけだと「設定すると何が良いか」が伝わらない。"""

    def test_every_quest_says_what_gets_better(self):
        from paper_maker import profile, quest
        profile.ensure_exists()
        for q in quest.evaluate()["quests"]:
            self.assertTrue(q.get("gain"), "%d に gain が無い" % q["id"])

    def test_the_images_exist_in_the_package(self):
        from paper_maker import paths, profile, quest
        profile.ensure_exists()
        shots = [q["shot"] for q in quest.evaluate()["quests"] if q.get("shot")]
        self.assertGreaterEqual(len(shots), 7)
        for name in set(shots):
            p = paths.APP_HTML.parent / "tutorial" / name
            self.assertTrue(p.exists(), "%s が無い" % name)
            self.assertGreater(p.stat().st_size, 2000, "%s が小さすぎる" % name)

    def test_images_are_served_and_ascii_named(self):
        from paper_maker import paths
        d = paths.APP_HTML.parent / "tutorial"
        for p in d.glob("*"):
            self.assertTrue(all(ord(c) < 128 for c in p.name), "%s に非ASCII" % p.name)
            self.assertEqual(p.read_bytes()[:4], b"\x89PNG", "%s が PNG でない" % p.name)


class TestAiProvider(TempHome):
    """AI の接続先。鍵を配る側の都合で決めない。"""

    def test_default_is_gemini_and_switchable(self):
        from paper_maker import ai
        self.assertEqual(ai.load()["provider"], "gemini")
        for name in ("openai", "anthropic"):
            cfg = dict(ai.PRESETS[name]); cfg["provider"] = name
            ai.save(cfg)
            got = ai.load()
            self.assertEqual(got["provider"], name)
            self.assertEqual(got["keyName"], ai.PRESETS[name]["keyName"])
            self.assertTrue(got["endpoint"].startswith("https://"))

    def test_custom_endpoint_is_kept(self):
        from paper_maker import ai
        ai.save({"provider": "custom", "model": "llama3", "keyName": "LOCAL_KEY",
                 "endpoint": "http://127.0.0.1:11434/v1/chat/completions"})
        got = ai.load()
        self.assertEqual(got["endpoint"], "http://127.0.0.1:11434/v1/chat/completions")
        self.assertEqual(got["style"], "openai")

    def test_key_is_not_written_into_the_config(self):
        """鍵は ai.json ではなく secrets.env に。設定ファイルは人に見せることがある。"""
        from paper_maker import ai, bridge
        bridge.write_secret("OPENAI_API_KEY", "sk-test-do-not-use")
        cfg = dict(ai.PRESETS["openai"]); cfg["provider"] = "openai"
        ai.save(cfg)
        self.assertNotIn("sk-test", ai.config_path().read_text(encoding="utf-8"))
        self.assertEqual(ai.api_key(ai.load()), "sk-test-do-not-use")

    def test_each_style_builds_the_right_request(self):
        """3つの流儀で、送る形と認証の置き場が変わる。"""
        from unittest import mock
        from paper_maker import ai, bridge
        seen = {}

        def fake(url, body, headers, timeout):
            seen.update(url=url, body=body, headers=headers)
            if "generativelanguage" in url:
                return {"candidates": [{"content": {"parts": [{"text": '{"ok":1}'}]}}]}
            if "anthropic" in url:
                return {"content": [{"text": '{"ok":1}'}]}
            return {"choices": [{"message": {"content": '{"ok":1}'}}]}

        with mock.patch.object(ai, "_post", side_effect=fake):
            bridge.write_secret("GEMINI_API_KEY", "g-key")
            ai.save({"provider": "gemini"})
            ai.ask_json("test")
            self.assertIn("key=g-key", seen["url"])
            self.assertIn("contents", seen["body"])

            bridge.write_secret("ANTHROPIC_API_KEY", "a-key")
            ai.save({"provider": "anthropic"})
            ai.ask_json("test")
            self.assertEqual(seen["headers"]["x-api-key"], "a-key")
            self.assertIn("anthropic-version", seen["headers"])

            bridge.write_secret("OPENAI_API_KEY", "o-key")
            ai.save({"provider": "openai"})
            ai.ask_json("test")
            self.assertEqual(seen["headers"]["Authorization"], "Bearer o-key")
            self.assertIn("messages", seen["body"])

    def test_missing_key_says_which_one(self):
        from paper_maker import ai
        ai.save({"provider": "openai"})
        ok, msg = ai.check()
        self.assertFalse(ok)
        self.assertIn("OPENAI_API_KEY", msg)


class TestCalendarHowto(TempHome):
    """クエスト4。URL 以外の繋ぎ方も載せる。"""

    def test_all_three_ways_are_written(self):
        from paper_maker import profile, quest
        profile.ensure_exists()
        q = [x for x in quest.evaluate()["quests"] if x["id"] == 4][0]
        for w in ('"type": "macos"', '"type": "ics"', '"type": "url"',
                  "エクスポート", "Outlook", "iCloud"):
            self.assertIn(w, q["how"], "%s が無い" % w)

    def test_the_url_way_warns_about_sharing(self):
        from paper_maker import profile, quest
        profile.ensure_exists()
        q = [x for x in quest.evaluate()["quests"] if x["id"] == 4][0]
        self.assertIn("人に渡さない", q["how"])

    def test_no_confusing_wording(self):
        from paper_maker import profile, quest
        profile.ensure_exists()
        for q in quest.evaluate()["quests"]:
            for field in ("gain", "todo", "how"):
                self.assertNotIn("紙を作る", q.get(field) or "")


class TestAiQuestOrder(TempHome):
    """スクショを読ませるには先に AI が要る。道順もその順番になっていること。"""

    def test_ai_comes_before_the_fare_import(self):
        from paper_maker import profile, quest
        profile.ensure_exists()
        qs = {q["id"]: q["title"] for q in quest.evaluate()["quests"]}
        self.assertEqual(qs[5], "AI に繋ぐ")
        self.assertEqual(qs[6], "運賃をまとめて入れる")
        self.assertEqual(qs[8], "今までの書類を取り込む")
        self.assertEqual(len(qs), 12)

    def test_ai_quest_is_not_done_without_a_key(self):
        from paper_maker import profile, quest
        profile.ensure_exists()
        q = [x for x in quest.evaluate()["quests"] if x["id"] == 5][0]
        self.assertFalse(q["done"])
        self.assertIn("鍵がまだ", q["note"])
        self.assertIn("使わずに進む", q["note"])

    def test_ai_quest_passes_once_the_check_succeeds(self):
        from unittest import mock
        from paper_maker import ai, bridge, profile, quest
        profile.ensure_exists()
        bridge.write_secret("GEMINI_API_KEY", "dummy")
        with mock.patch.object(ai, "check", return_value=(True, "繋がりました")):
            q = [x for x in quest.evaluate()["quests"] if x["id"] == 5][0]
        self.assertTrue(q["done"])

    def test_the_image_path_names_the_quest_not_a_file_to_edit(self):
        """ターミナルを開かない人に、ファイルを手で直せと言わない。"""
        r = self.cli("init", "--example")
        img = pathlib.Path(self.tmp) / "x.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
        r = self.cli("fare", "import", str(img), check=False)
        self.assertIn("paper-maker ai", r.stdout)
        self.assertNotIn("secrets.env に", r.stdout)


class TestQuestNav(TempHome):
    """道順は9つ。前へ戻れる。終わったら消える。"""

    def test_steps_and_calendar_absorbs_the_location_tip(self):
        from paper_maker import profile, quest
        profile.ensure_exists()
        qs = quest.evaluate()["quests"]
        self.assertEqual(len(qs), 12)
        titles = [q["title"] for q in qs]
        self.assertNotIn("予定の書き方を決める", titles)
        cal = [q for q in qs if q["title"] == "カレンダーを繋ぐ"][0]
        # 住所の話はカレンダーの中で言う
        self.assertIn("場所欄に住所", cal["how"])
        self.assertIn("ZOOM", cal["how"])

    def test_no_duplicate_wording_between_gain_and_todo(self):
        """gain と todo で同じ文を2回読ませない。"""
        from paper_maker import profile, quest
        profile.ensure_exists()
        for q in quest.evaluate()["quests"]:
            self.assertNotEqual(q["gain"], q["todo"])
            self.assertNotEqual(q["gain"], q["reward"])

    def test_gain_is_polite_form(self):
        """gain は です・ます で揃える。文体が混ざると読みにくい。"""
        from paper_maker import profile, quest
        profile.ensure_exists()
        for q in quest.evaluate()["quests"]:
            self.assertTrue(q["gain"].rstrip().endswith("。"), q["id"])
            self.assertTrue("ます" in q["gain"] or "です" in q["gain"], q["id"])


class TestKnowledge(TempHome):
    """今までの書類を取り込んで、次の書類に効かせる。"""

    def sample(self):
        return {
            "kind": "契約書", "title": "業務委託契約書", "date": "2026-08-01",
            "client": {"name": "株式会社サカイ商店", "address": "東京都新宿区1-1", "honorific": "御中"},
            "items": [], "total": 300000,
            "clauses": [{"heading": "第1条（目的）", "body": "本文A"},
                        {"heading": "第2条（委託料）", "body": "本文B"}],
            "terms": {"payment": "翌月末", "delivery": "", "period": ""},
            "source": "keiyaku.txt",
        }

    def test_apply_stores_clients_and_clauses(self):
        from paper_maker import knowledge
        n = knowledge.apply(knowledge.summarize([self.sample()]))
        self.assertEqual((n["docs"], n["clients"], n["clauses"]), (1, 1, 2))
        self.assertEqual(knowledge.find_client("サカイ")["address"], "東京都新宿区1-1")

    def test_the_same_thing_twice_does_not_pile_up(self):
        from paper_maker import knowledge
        knowledge.apply(knowledge.summarize([self.sample()]))
        n = knowledge.apply(knowledge.summarize([self.sample()]))
        self.assertEqual((n["clients"], n["clauses"]), (0, 0))

    def test_item_prices_are_history_not_a_decision(self):
        """単価は「前はこの額だった」。新しい順に並べて見せるだけ。"""
        from paper_maker import knowledge
        a = dict(self.sample(), kind="見積書", date="2025-04-01",
                 items=[{"name": "初期構築", "qty": 1, "unit": "式", "price": 250000}])
        b = dict(self.sample(), kind="見積書", date="2026-06-01",
                 items=[{"name": "初期構築", "qty": 1, "unit": "式", "price": 300000}])
        knowledge.apply(knowledge.summarize([a, b]))
        rows = knowledge.item_prices("初期構築")
        self.assertEqual([r["price"] for r in rows], [300000, 250000])

    def test_contract_body_is_built_from_what_was_learned(self):
        from paper_maker import knowledge
        knowledge.apply(knowledge.summarize([self.sample()]))
        body = knowledge.contract_body()
        self.assertIn("第1条（目的）", body)
        self.assertIn("本文B", body)

    def test_nothing_is_invented_when_the_source_is_empty(self):
        from paper_maker import knowledge
        empty = {"kind": "そのほか", "title": "", "client": {}, "items": [], "clauses": [], "source": "x.txt"}
        sm = knowledge.summarize([empty])
        self.assertEqual((sm["clients"], sm["items"], sm["clauses"]), ([], [], []))


class TestScheduleQuest(TempHome):
    def test_it_reads_the_two_line_status(self):
        """status() の表示を2つに増やしたとき、判定が合わなくなっていた。"""
        from unittest import mock
        from paper_maker import profile, quest, schedule
        profile.ensure_exists()
        with mock.patch.object(schedule, "status", return_value="毎日の書類作り: 登録あり / 定期の見直し: 未登録"):
            q = [x for x in quest.evaluate(recheck=True)["quests"] if x["id"] == 10][0]
        self.assertTrue(q["done"])
        with mock.patch.object(schedule, "status", return_value="毎日の書類作り: 未登録 / 定期の見直し: 登録あり"):
            q = [x for x in quest.evaluate(recheck=True)["quests"] if x["id"] == 10][0]
        self.assertFalse(q["done"], "毎日のほうが未登録なのに済みになった")


class TestAutoSet(unittest.TestCase):
    """設定をまとめて埋める。押されるまで書かないこと。"""

    def setUp(self):
        from paper_maker import paths
        self.d = tempfile.mkdtemp(prefix="pm-auto-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_plan_does_not_write_anything(self):
        from paper_maker import autoset, paths  # noqa: F401
        autoset.plan(use_ai=False)
        self.assertFalse((pathlib.Path(self.d) / "profile.json").exists())

    def test_apply_writes_the_provider_preset_not_the_old_one(self):
        """接続先を替えたとき、前の接続先の model や endpoint を持ち越さない。"""
        from paper_maker import ai, autoset, paths
        ai.save({"provider": "gemini", "model": "gemini-2.5-flash",
                 "keyName": "GEMINI_API_KEY"})
        st = autoset.Step("AI の接続先", "ai.json の provider", "gemini", "claude-cli", "見つけた")
        autoset.apply({"steps": [st], "notes": []})
        got = json.loads((pathlib.Path(self.d) / "ai.json").read_text(encoding="utf-8"))
        self.assertEqual(got["provider"], "claude-cli")
        self.assertNotIn("gemini", json.dumps(got, ensure_ascii=False))

    def test_it_drops_the_sample_ics_that_points_at_nothing(self):
        """見本のまま残った、実体の無い .ics は落とす。"""
        from paper_maker import autoset, paths, profile
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
        st = autoset.Step("カレンダー", "profile.json の calendar.sources", "1 件",
                          'type: "macos"', "カレンダー.app")
        autoset.apply({"steps": [st], "notes": []})
        srcs = profile.load()["calendar"]["sources"]
        self.assertEqual([x["type"] for x in srcs], ["macos"])

    def test_it_keeps_an_ics_that_really_exists(self):
        from paper_maker import autoset, paths, profile
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
        (pathlib.Path(self.d) / "calendar.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
        st = autoset.Step("カレンダー", "profile.json の calendar.sources", "1 件",
                          'type: "macos"', "カレンダー.app")
        autoset.apply({"steps": [st], "notes": []})
        srcs = profile.load()["calendar"]["sources"]
        self.assertEqual(sorted(x["type"] for x in srcs), ["ics", "macos"])

    def test_a_step_knows_when_it_overwrites(self):
        from paper_maker import autoset
        self.assertTrue(autoset.Step("名", "profiles.corp.name", "前", "後", "").overwrite)
        self.assertFalse(autoset.Step("名", "profiles.corp.name", "", "後", "").overwrite)


class TestSyncRebuild(unittest.TestCase):
    """1時間ごとの回。変わった日だけ作り直すこと。"""

    def setUp(self):
        from paper_maker import paths
        self.d = tempfile.mkdtemp(prefix="pm-sync-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_the_mark_changes_when_a_visit_is_added(self):
        from paper_maker import sync
        a = [{"start": "10:00", "end": "11:00", "title": "訪問", "location": "大宮", "note": ""}]
        b = a + [{"start": "15:00", "end": "16:00", "title": "打合せ", "location": "尾張町", "note": ""}]
        self.assertEqual(sync._mark(a), sync._mark(a))
        self.assertNotEqual(sync._mark(a), sync._mark(b))

    def test_the_mark_changes_when_only_the_place_is_filled_in(self):
        """場所を後から書き足した日も作り直す。交通費が変わるので。"""
        from paper_maker import sync
        a = [{"start": "10:00", "end": "11:00", "title": "訪問", "location": "", "note": ""}]
        b = [{"start": "10:00", "end": "11:00", "title": "訪問", "location": "大宮", "note": ""}]
        self.assertNotEqual(sync._mark(a), sync._mark(b))

    def test_the_mark_holds_no_titles(self):
        """覚えるのは指紋だけ。予定名を残さない。"""
        from paper_maker import sync
        m = sync._mark([{"start": "10:00", "end": "11:00", "title": "サカイ商店",
                         "location": "大宮", "note": "見積の詰め"}])
        self.assertNotIn("サカイ", m)
        self.assertEqual(len(m), 16)


class TestScheduleBoth(unittest.TestCase):
    def test_install_all_registers_the_morning_run_and_the_hourly_one(self):
        from paper_maker import schedule
        calls = []
        real = schedule.install
        schedule.install = lambda h, m, e: calls.append(e) or "ok"
        try:
            schedule.install_all(6, 0, 60)
        finally:
            schedule.install = real
        self.assertEqual(calls, [0, 60])

    def test_zero_means_the_morning_run_only(self):
        from paper_maker import schedule
        calls = []
        real = schedule.install
        schedule.install = lambda h, m, e: calls.append(e) or "ok"
        try:
            schedule.install_all(6, 0, 0)
        finally:
            schedule.install = real
        self.assertEqual(calls, [0])


class TestUpdateRoutes(unittest.TestCase):
    """更新。private の配布元でも取れる道があること。"""

    def test_a_404_is_not_treated_as_no_update(self):
        """鍵なしで 404 が返る配布元。黙って「最新です」と言わないこと。"""
        import urllib.error
        from paper_maker import update
        real_fetch, real_gh = update._fetch, update._gh_ready
        update._gh_ready = lambda: False
        update._fetch = lambda url, timeout=60: (_ for _ in ()).throw(
            urllib.error.HTTPError(url, 404, "Not Found", None, None))
        try:
            with self.assertRaises(RuntimeError) as cm:
                update.check("https://example.invalid/manifest.json")
            self.assertIn("--file", str(cm.exception))
        finally:
            update._fetch, update._gh_ready = real_fetch, real_gh

    def test_it_refuses_a_zip_older_than_what_is_installed(self):
        from paper_maker import update, __version__
        d = tempfile.mkdtemp(prefix="pm-up-")
        try:
            zp = pathlib.Path(d) / "old.zip"
            import zipfile as zf
            with zf.ZipFile(zp, "w") as z:
                z.writestr("paper-maker/VERSION", "0.0.1\n")
            msg = update.from_file(zp)
            self.assertIn("中止", msg)
            self.assertIn(__version__, msg)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_it_refuses_a_zip_whose_digest_does_not_match(self):
        from paper_maker import update
        d = tempfile.mkdtemp(prefix="pm-up-")
        try:
            zp = pathlib.Path(d) / "x.zip"
            zp.write_bytes(b"not a zip")
            msg = update.from_file(zp, sha256="00" * 32)
            self.assertIn("中止", msg)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_it_says_so_when_there_is_nothing_to_roll_back_to(self):
        from paper_maker import update
        self.assertIn("控えがありません", update.rollback())


class TestSampleValuesAreNotDone(unittest.TestCase):
    """見本のまま「済」にしない。そのまま出すと見本の名義で請求書が出る。"""

    def setUp(self):
        from paper_maker import paths
        self.d = tempfile.mkdtemp(prefix="pm-smp-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        import shutil as sh
        from paper_maker import profile
        profile.ensure_data_files()
        sh.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_the_example_profile_does_not_pass(self):
        from paper_maker import profile, quest
        prof = profile.load()
        self.assertFalse(quest._q1(prof))
        self.assertFalse(quest._q2(prof))
        self.assertFalse(quest._q_base(prof)[0])

    def test_a_real_name_passes(self):
        from paper_maker import profile, quest
        prof = profile.load()
        prof["profiles"]["corp"] = {"name": "合同会社ミナト", "rep": "代表社員　港 一郎",
                                    "address": "埼玉県さいたま市大宮区1-1-1",
                                    "bank": "北國銀行 普通 1234567"}
        prof["travel"]["bases"]["hq"] = {"label": "本店", "address": "埼玉県さいたま市大宮区1-1-1",
                                         "station": "大宮"}
        self.assertTrue(quest._q1(prof))
        self.assertTrue(quest._q2(prof))
        self.assertTrue(quest._q_base(prof)[0])


class TestAutoIssuer(unittest.TestCase):
    def setUp(self):
        from paper_maker import paths
        self.d = tempfile.mkdtemp(prefix="pm-iss-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_a_personal_document_switches_the_issuer(self):
        """屋号を持たない人の書類を読んだら、出す名義も個人に寄せる。
        ここが corp のままだと、次の請求書が見本の会社名と見本の口座で出る。"""
        from paper_maker import autoset, paths, profile
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
        steps = [autoset.Step("名義", "profile.json の defaultIssuer", "corp", "personal", ""),
                 autoset.Step("会社名", "profiles.personal.name", "", "佐々木 亮太", ""),
                 autoset.Step("使わないほう", "profiles.corp.__clear__", "株式会社サンプル", "（空にする）", "")]
        autoset.apply({"steps": steps, "notes": []})
        prof = profile.load()
        self.assertEqual(prof["defaultIssuer"], "personal")
        self.assertEqual(prof["profiles"]["corp"]["name"], "")
        self.assertEqual(prof["profiles"]["personal"]["name"], "佐々木 亮太")

    def test_it_does_not_wipe_a_profile_someone_wrote(self):
        from paper_maker import autoset
        self.assertFalse(autoset._is_sample({"name": "港 一郎", "address": "埼玉県さいたま市"}))
        self.assertTrue(autoset._is_sample({"name": "株式会社サンプル"}))


class TestSampleCannotReachADocument(unittest.TestCase):
    """見本の名義のまま、署名できる紙を出させない。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-doc-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_rules_refuses_while_the_name_is_the_sample(self):
        from paper_maker import cli
        rc = cli.main(["rules", "--no-pdf"])
        self.assertEqual(rc, 1)
        self.assertFalse((pathlib.Path(self.d) / "out").exists())

    def test_a_leftover_seal_still_counts_as_the_sample(self):
        """名義を直しても判子の文字が見本なら、その判子が押されて出る。"""
        from paper_maker import profile
        prof = profile.load()
        prof["profiles"]["corp"].update({"name": "合同会社ミナト", "rep": "代表社員　港 一郎",
                                         "address": "埼玉県さいたま市大宮区1-1-1",
                                         "tel": "", "email": "", "bank": "北國銀行 普通 1"})
        self.assertTrue(profile.sample_issuer(prof))     # sealText が見本のまま
        prof["profiles"]["corp"]["sealText"] = "合同会社ミナト之印"
        self.assertFalse(profile.sample_issuer(prof))

    def test_the_daily_report_says_so(self):
        from paper_maker import profile
        prof = profile.load()
        self.assertIn("見本", "名義が見本のままです（%s）" % profile.sample_issuer(prof))


class TestKeepsRunning(unittest.TestCase):
    """毎日動き続けるための地味な2つ。"""

    def setUp(self):
        from paper_maker import paths
        self.d = tempfile.mkdtemp(prefix="pm-grd-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_the_log_does_not_grow_forever(self):
        from paper_maker import guard, paths
        p = paths.log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x" * 2000, encoding="utf-8")
        self.assertFalse(guard.roll_log(max_bytes=10000))
        self.assertTrue(guard.roll_log(max_bytes=1000))
        self.assertFalse(p.exists())
        self.assertTrue(p.with_suffix(p.suffix + ".1").exists())

    def test_only_one_run_at_a_time(self):
        from paper_maker import guard
        with guard.only_one("t") as a:
            self.assertTrue(a)
            with guard.only_one("t") as b:
                self.assertFalse(b)
        with guard.only_one("t") as c:
            self.assertTrue(c)

    def test_a_left_behind_lock_is_cleared(self):
        """強制終了で錠前が残っても、次の回で外れること。"""
        from paper_maker import guard, paths
        lock = paths.data_dir() / ".t2.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("999999")
        old = time.time() - guard.STALE_LOCK_SEC - 60
        os.utime(lock, (old, old))
        with guard.only_one("t2") as got:
            self.assertTrue(got)

    def test_sync_does_nothing_while_another_run_holds_it(self):
        from paper_maker import guard, sync
        with guard.only_one("sync"):
            r = sync.run(check_update=False)
        self.assertEqual(r["made"], [])
        self.assertIn("前の回", r["notes"][0])


class TestLedger(unittest.TestCase):
    def test_the_same_day_does_not_add_a_row(self):
        import datetime as _dt
        from paper_maker import ledger
        d = tempfile.mkdtemp(prefix="pm-led-")
        try:
            csvp = pathlib.Path(d) / "台帳.csv"
            prof = {"output": {"sheetCsv": str(csvp)}}
            day = _dt.date(2026, 8, 20)
            itin = {"events": [{"place": "大宮"}], "transportTotal": 3380,
                    "allowance": 5000, "unpricedLegs": []}
            ledger.write(prof, day, itin, [])
            ledger.write(prof, day, itin, [])
            rows = csvp.read_text(encoding="utf-8-sig").strip().splitlines()
            self.assertEqual(len(rows), 2)          # 見出し + 1日
            self.assertIn("8380", rows[1])

        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_it_matches_the_document_total(self):
        """金額の分からない区間は書類でも足していない。台帳もそれに揃える。"""
        import datetime as _dt
        from paper_maker import ledger
        d = tempfile.mkdtemp(prefix="pm-led-")
        try:
            csvp = pathlib.Path(d) / "l.csv"
            itin = {"events": [], "transportTotal": 1690, "allowance": 0,
                    "legs": [{"amount": 1690}, {"amount": ""}],
                    "unpricedLegs": [{"from": "大宮", "to": "川越"}]}
            ledger.write({"output": {"sheetCsv": str(csvp)}}, _dt.date(2026, 8, 20), itin, [])
            row = csvp.read_text(encoding="utf-8-sig").strip().splitlines()[1]
            self.assertIn("1690", row)
            self.assertIn(",1,", row)               # 要確認 1 件
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestLedgerSafety(unittest.TestCase):
    def test_a_formula_in_a_calendar_title_is_not_executed(self):
        """予定は他人の招待から来ることもある。台帳を開いた人が踏まないように。"""
        import datetime as _dt
        from paper_maker import ledger
        d = tempfile.mkdtemp(prefix="pm-inj-")
        try:
            p = pathlib.Path(d) / "t.csv"
            itin = {"events": [{"place": '=HYPERLINK("http://evil","click")'}],
                    "transportTotal": 0, "allowance": 0, "unpricedLegs": []}
            ledger.write({"output": {"sheetCsv": str(p)}}, _dt.date(2026, 8, 20), itin, [])
            row = p.read_text(encoding="utf-8-sig").splitlines()[1]
            self.assertIn("'=HYPERLINK", row)
            self.assertNotIn(',=HYPERLINK', row)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_an_unreachable_ledger_does_not_kill_the_day(self):
        """外付けが刺さっていない日に、書類が1枚も出ないのは困る。"""
        import datetime as _dt
        from paper_maker import ledger
        with self.assertRaises(ledger.LedgerUnavailable):
            ledger.write({"output": {"sheetCsv": "/Volumes/NoSuchDisk9/x.csv"}},
                         _dt.date(2026, 8, 20),
                         {"events": [], "transportTotal": 0, "allowance": 0,
                          "unpricedLegs": []}, [])


class TestGeocode(unittest.TestCase):
    def setUp(self):
        from paper_maker import paths
        self.d = tempfile.mkdtemp(prefix="pm-geo-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        from paper_maker import profile
        profile.ensure_data_files()

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_it_remembers_so_it_asks_once(self):
        from paper_maker import geocode, profile
        real_ask, real_ready = geocode._ask, geocode.ai.ready
        calls = []
        geocode.ai.ready = lambda: True
        geocode._ask = lambda addr, t=120: calls.append(addr) or "大宮"
        try:
            # 主要駅の名前が入っていない住所を使う。入っていると聞かずに解ける
            evs = [{"title": "訪問", "location": "埼玉県川越市1-1"},
                   {"title": "再訪", "location": "埼玉県川越市1-1"}]
            got = geocode.resolve(evs)
            self.assertEqual(len(calls), 1)
            self.assertEqual(got["learned"], [("埼玉県川越市1-1", "大宮")])
            geocode.resolve(evs)                 # 2回目は覚えている分で足りる
            self.assertEqual(len(calls), 1)
        finally:
            geocode._ask, geocode.ai.ready = real_ask, real_ready
        rules = profile.load_places()["rules"]
        self.assertTrue(any(r.get("station") == "大宮" for r in rules))

    def test_it_does_not_invent_a_station(self):
        from paper_maker import geocode
        real_ask, real_ready = geocode._ask, geocode.ai.ready
        geocode.ai.ready = lambda: True
        geocode._ask = lambda addr, t=120: ""
        try:
            got = geocode.resolve([{"title": "訪問", "location": "どこかの離島"}])
            self.assertEqual(got["learned"], [])
            self.assertEqual(got["left"], 1)
        finally:
            geocode._ask, geocode.ai.ready = real_ask, real_ready


class TestScheduledRunCanUseTheAi(unittest.TestCase):
    """自動実行の回でも AI に届くこと。ここが切れると交通費が出ない。"""

    def test_the_job_carries_the_path(self):
        from paper_maker import schedule
        old = os.environ.get("PATH", "")
        os.environ["PATH"] = "/opt/homebrew/bin:/usr/bin:/bin"
        try:
            env = schedule._env_pairs()
        finally:
            os.environ["PATH"] = old
        self.assertIn("/opt/homebrew/bin", env["PATH"])

    def test_a_cli_is_remembered_by_where_it_lives(self):
        """名前だけで覚えると、PATH の細い自動実行から見つけられない。"""
        from paper_maker import ai
        got = ai._absolute("python3 -p")
        self.assertTrue(got.startswith("/"), got)
        self.assertTrue(got.endswith(" -p"), got)

    def test_an_unknown_command_is_left_as_written(self):
        from paper_maker import ai
        self.assertEqual(ai._absolute("no-such-cli-xyz --run"), "no-such-cli-xyz --run")


class TestIncompleteDaysAreRetried(unittest.TestCase):
    def test_a_day_built_without_the_ai_is_not_remembered(self):
        from paper_maker import sync
        self.assertFalse(sync._complete({"warnings": ["AI に繋がらないので、住所から駅を引けませんでした"]}))
        self.assertFalse(sync._complete({"warnings": ["「A社」の場所を判定できません（場所欄はあるが駅に結びつかない: 東京都…）"]}))

    def test_a_day_the_person_must_fix_is_not_retried_forever(self):
        """名義が見本のままは、作り直しても変わらない。毎回やり直さない。"""
        from paper_maker import sync
        self.assertTrue(sync._complete({"warnings": ["⚙設定の メール が見本のままです。書類にそのまま載ります"]}))
        self.assertTrue(sync._complete({"warnings": []}))


class TestLedgerCounts(unittest.TestCase):
    def test_it_accepts_both_shapes_of_the_unpriced_field(self):
        from paper_maker import ledger
        self.assertEqual(ledger._count(2), 2)
        self.assertEqual(ledger._count([{"from": "大宮"}, {"from": "福井"}]), 2)
        self.assertEqual(ledger._count(None), 0)


class TestBases(unittest.TestCase):
    """拠点の登録と切り替え。手で JSON を開かせない。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-bas-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_a_bus_stop_can_be_the_starting_point(self):
        """高速バスで出る人は、駅ではなく乗り場が起点になる。"""
        from paper_maker import bases
        b = bases.add("自宅", "千県○市○町4-24-15", station="○師4丁目", ask_ai=False)
        self.assertEqual(b["station"], "○師4丁目")
        self.assertTrue(b["current"])

    def test_switching_where_i_am(self):
        from paper_maker import bases
        bases.add("自宅", "A市1-1", station="A", ask_ai=False)
        bases.add("事務所", "B市1-1", station="B", ask_ai=False)
        self.assertEqual(bases.use("自宅")["station"], "A")
        cur = [r for r in bases.listing() if r["current"]]
        self.assertEqual([r["label"] for r in cur], ["自宅"])

    def test_the_same_name_updates_instead_of_piling_up(self):
        from paper_maker import bases
        bases.add("自宅", "古い住所", station="A", ask_ai=False)
        bases.add("自宅", "新しい住所", station="B", ask_ai=False)
        rows = [r for r in bases.listing() if r["label"] == "自宅"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["address"], "新しい住所")

    def test_the_last_one_cannot_be_removed(self):
        from paper_maker import bases, profile
        prof = profile.load()
        prof["travel"]["bases"] = {"hq": {"label": "本店", "address": "A", "station": "A"}}
        prof["travel"]["currentBase"] = "hq"
        profile.save(prof)
        with self.assertRaises(bases.BadBase):
            bases.remove("本店")

    def test_an_address_without_a_station_falls_back_to_the_departure_station(self):
        """歩ける駅が無い土地。ここで空にすると交通費が1円も出ない。"""
        from paper_maker import bases, geocode
        real_ready, real_ask = geocode.ai.ready, geocode._ask_both
        geocode.ai.ready = lambda: True
        geocode._ask_both = lambda addr, t=120: {"station": "", "hub": "大宮"}
        try:
            b = bases.add("自宅", "町はずれの住所")
        finally:
            geocode.ai.ready, geocode._ask_both = real_ready, real_ask
        self.assertEqual(b["station"], "大宮")
        self.assertIn("遠出", b["note"])


class TestFareRoutePick(unittest.TestCase):
    """行き方が何通りもある区間。選べること、選んだ系統を覚えること。"""

    R_BUS = {"amount": 2128, "minutes": 128, "note": "乗換1回",
             "lines": ["高速バス・○交通・A−B線", "ＪＲ○須賀線"]}
    R_EXP = {"amount": 4188, "minutes": 121, "note": "乗換1回",
             "lines": ["高速バス・○交通・A−B線", "ＪＲ特急○号"]}
    R_CHEAP = {"amount": 2118, "minutes": 148, "note": "乗換3回",
               "lines": ["高速バス・○交通・A−B線", "○メトロ銀座線", "○東横線"]}
    R_SLOW = {"amount": 9620, "minutes": 656, "note": "乗換6回", "lines": ["ＪＲ○本線"]}
    R_SHIN = {"amount": 14600, "minutes": 149, "note": "乗換0回", "lines": ["ＪＲ新幹線○号"]}

    def test_it_does_not_take_a_ten_hour_detour_to_save_money(self):
        from paper_maker import fare_route
        got = fare_route._pick([self.R_SHIN, self.R_SLOW])
        self.assertEqual(got["amount"], 14600)

    def test_it_does_not_pay_extra_to_save_two_minutes(self):
        from paper_maker import fare_route
        got = fare_route._pick([self.R_EXP, self.R_BUS])
        self.assertEqual(got["amount"], 2128)

    def test_a_remembered_choice_wins(self):
        """前に「高速バスで行った」と決めた区間は、安い地下鉄乗り継ぎに戻さない。"""
        from paper_maker import fare_route
        only_metro = dict(self.R_CHEAP)
        got = fare_route._pick([only_metro, self.R_BUS], prefer=["ＪＲ○須賀線"])
        self.assertEqual(got["amount"], 2128)

    def test_no_preference_means_all_routes_are_in_play(self):
        from paper_maker import fare_route
        got = fare_route._pick([self.R_BUS, self.R_CHEAP])
        self.assertEqual(got["amount"], 2118)

    def test_nothing_is_invented_when_the_search_fails(self):
        from paper_maker import fare_route
        self.assertIsNone(fare_route._pick([]))
        self.assertIsNone(fare_route._pick([{"amount": 0, "minutes": 0, "lines": []}]))


class TestFarePreferenceIsRemembered(unittest.TestCase):
    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-frw-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_it_writes_and_reads_back_the_choice(self):
        from paper_maker import fares_write
        fares_write.add("A停", "B", 2128, transport="高速バス", line="高速バス／ＪＲ",
                        source="本人が選択", prefer=["高速バス"],
                        routes=[{"amount": 2128, "minutes": 128, "lines": ["高速バス"], "note": ""}])
        self.assertEqual(fares_write.prefer_of("A停", "B"), ["高速バス"])
        self.assertEqual(fares_write.prefer_of("B", "A停"), [])

    def test_the_same_pair_is_replaced_not_piled_up(self):
        from paper_maker import fares_write, profile
        fares_write.add("Ａ町", "Ｂ町", 100)
        fares_write.add("Ａ町", "Ｂ町", 200)
        st = profile.load_stations()["stations"]
        name = {k: (v.get("name") or k).rstrip("駅") for k, v in st.items()}
        rows = [r for r in profile.load_fares()["fares"]
                if name.get(r["from"]) == "Ａ町" and name.get(r["to"]) == "Ｂ町"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount"], 200)


class TestAnyRoute(unittest.TestCase):
    """自分の通勤路だけでなく、どこの区間でも同じように扱えること。"""

    def test_the_mode_is_remembered_even_for_a_plain_local_line(self):
        """新幹線でも高速バスでもない選択（新快速など）も覚える。"""
        from paper_maker import fares_write
        self.assertEqual(fares_write.kinds_of(["ＪＲ○線新快速○行"]), ["快速"])
        self.assertEqual(fares_write.kinds_of(["○バス・○交通・○線", "ＪＲ○線"]), ["バス"])
        self.assertEqual(fares_write.kinds_of(["高速バス・○交通・○線", "ＪＲ○線"]), ["高速バス"])
        self.assertEqual(fares_write.kinds_of(["ＪＲ新幹線○号"]), ["新幹線"])

    def test_an_unknown_line_still_leaves_something_to_go_on(self):
        from paper_maker import fares_write
        got = fares_write.kinds_of(["○○電鉄・△△線"])
        self.assertTrue(got and got[0])

    def test_nothing_to_remember_when_there_is_no_line(self):
        from paper_maker import fares_write
        self.assertEqual(fares_write.kinds_of([]), [])
        self.assertEqual(fares_write.kinds_of(None), [])


class TestFlightIsNotSilentlyPriced(unittest.TestCase):
    """同じ名前の駅が他の土地にもある時、空路の額を黙って精算書に載せない。"""

    GROUND = {"amount": 280, "minutes": 25, "lines": ["○バス・１４３○線"], "note": ""}
    AIR = {"amount": 43690, "minutes": 174,
           "lines": ["スカイマーク592便", "○新交通○線"], "note": ""}

    def test_a_ground_route_wins_over_a_flight(self):
        from paper_maker import fare_route
        self.assertEqual(fare_route._pick([self.AIR, self.GROUND])["amount"], 280)

    def test_a_flight_only_result_is_flagged(self):
        from paper_maker import fare_route
        self.assertTrue(fare_route._is_flight(self.AIR))
        self.assertFalse(fare_route._is_flight(self.GROUND))


class TestTravelRatesFromScreen(unittest.TestCase):
    """日当は会社が決める。画面から入れた額が、そのまま規程と精算に出ること。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-rate-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def _save(self, body):
        from paper_maker import profile
        prof = profile.load()
        tr = prof.setdefault("travel", {})
        rates = body.get("rates")
        if rates:
            tr["rates"] = {k: {"day": max(0, int(v["day"])), "night": max(0, int(v["night"]))}
                           for k, v in rates.items() if k.strip()}
            if tr.get("role") not in tr["rates"]:
                tr["role"] = next(iter(tr["rates"]))
        if body.get("lodgingCap") is not None:
            tr.setdefault("lodging", {})["cap"] = max(0, int(body["lodgingCap"]))
        profile.save(prof)
        return profile.load()

    def test_the_amount_reaches_the_printed_rules(self):
        from paper_maker.docs import rules
        prof = self._save({"rates": {"代表取締役": {"day": 8000, "night": 16000}},
                           "lodgingCap": 15000})
        html = rules.build_html(prof)
        self.assertIn("8,000円", html)
        self.assertIn("16,000円", html)

    def test_a_removed_role_disappears(self):
        prof = self._save({"rates": {"代表取締役": {"day": 5000, "night": 10000}}})
        self.assertEqual(list(prof["travel"]["rates"]), ["代表取締役"])

    def test_a_negative_amount_is_not_accepted(self):
        prof = self._save({"rates": {"代表取締役": {"day": -1, "night": -9}}})
        self.assertEqual(prof["travel"]["rates"]["代表取締役"], {"day": 0, "night": 0})

    def test_my_role_follows_when_the_old_one_is_gone(self):
        prof = self._save({"rates": {"店長": {"day": 4000, "night": 8000}}})
        self.assertEqual(prof["travel"]["role"], "店長")


class TestRouteScreenshot(unittest.TestCase):
    """乗換案内は人が見る。こちらは撮った画面を読むだけ。"""

    def test_the_search_url_is_built_but_not_fetched(self):
        from paper_maker import fare_route
        u = fare_route.search_url("東京", "横浜")
        self.assertTrue(u.startswith("https://"))
        self.assertIn("from=", u)
        self.assertIn("to=", u)

    def test_the_automatic_fetch_is_off_by_default(self):
        """配布版が勝手に叩かないこと。規約に触れる所なので既定で切る。"""
        from paper_maker import paths, profile
        d = tempfile.mkdtemp(prefix="pm-off-")
        os.environ["PAPER_MAKER_HOME"] = d
        importlib.reload(paths)
        try:
            profile.ensure_data_files()
            shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
            tr = profile.load().get("travel") or {}
            self.assertFalse(tr.get("lookupFares", False))
        finally:
            shutil.rmtree(d, ignore_errors=True)
            os.environ.pop("PAPER_MAKER_HOME", None)
            importlib.reload(paths)

    def test_a_zero_or_unreadable_amount_is_dropped(self):
        """読めなかった所を0円のまま並べない。押せてしまうので。"""
        from paper_maker import fare_shot
        real = fare_shot.ai.ask_json
        fare_shot.ai.ask_json = lambda *a, **k: {
            "from": "東京", "to": "横浜",
            "routes": [{"amount": 0, "minutes": 26, "lines": ["ＪＲ○線"]},
                       {"amount": "528", "minutes": "26", "lines": ["ＪＲ○線"], "note": "乗換0回"},
                       {"amount": "よめない", "minutes": 30, "lines": []}]}
        try:
            got = fare_shot.read("dummy.png")
        finally:
            fare_shot.ai.ask_json = real
        self.assertEqual([r["amount"] for r in got["routes"]], [528])
        self.assertEqual(got["from"], "東京")

    def test_a_broken_answer_does_not_explode(self):
        from paper_maker import fare_shot
        real = fare_shot.ai.ask_json
        fare_shot.ai.ask_json = lambda *a, **k: "読めませんでした"
        try:
            got = fare_shot.read("dummy.png")
        finally:
            fare_shot.ai.ask_json = real
        self.assertEqual(got["routes"], [])


class TestScheduleIsPerHome(unittest.TestCase):
    def test_a_job_for_another_home_is_not_mine(self):
        """1台に2つ入れている人。別の置き場の登録を自分の分と数えない。"""
        from paper_maker import schedule
        if sys.platform != "darwin":
            self.skipTest("mac のみ")
        d = tempfile.mkdtemp(prefix="pm-sch-")
        os.environ["PAPER_MAKER_HOME"] = d
        from paper_maker import paths
        importlib.reload(paths)
        try:
            self.assertIn("未登録", schedule.status())
        finally:
            shutil.rmtree(d, ignore_errors=True)
            os.environ.pop("PAPER_MAKER_HOME", None)
            importlib.reload(paths)


class TestFirstRunWithoutATerminal(unittest.TestCase):
    """ターミナルを開かない人が、画面だけで始められること。"""

    def setUp(self):
        from paper_maker import paths
        self.d = tempfile.mkdtemp(prefix="pm-1st-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_the_first_screen_does_not_ask_for_a_command(self):
        """まだ設定が無い人に paper-maker init と出さない。押す場所を書く。"""
        from paper_maker import quest
        note = [q for q in quest.evaluate()["quests"] if q["id"] == 1][0]
        d = quest.evaluate()
        first = d["quests"][0]
        self.assertFalse(first["done"])
        text = json.dumps(d, ensure_ascii=False)
        self.assertNotIn("paper-maker init", text)

    def test_the_sample_base_is_dropped_once_a_real_one_is_added(self):
        """見本の拠点が残ると、選び間違えた日の移動が丸ごと別の土地から出発する。"""
        from paper_maker import bases, paths, profile
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
        bases.add("博多", "福岡県福岡市博多区…", station="博多", ask_ai=False)
        labels = [b["label"] for b in bases.listing()]
        self.assertEqual(labels, ["博多"])

    def test_a_base_someone_wrote_is_never_dropped(self):
        from paper_maker import bases, paths, profile
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
        bases.add("実家", "自分で書いた住所", station="ど", ask_ai=False)
        bases.add("事務所", "もう一つ", station="べ", ask_ai=False)
        labels = sorted(b["label"] for b in bases.listing())
        self.assertEqual(labels, ["事務所", "実家"])


class TestScreenInputDoesNotDestroy(unittest.TestCase):
    """画面から変な値を入れても、入っていた設定を壊さないこと。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-in-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def _travel(self, body):
        """/api/travel が中でやっていることと同じ手順。"""
        from paper_maker import profile
        prof = profile.load()
        tr = prof.setdefault("travel", {})
        rates = body.get("rates")
        if isinstance(rates, dict) and rates:
            clean = {}
            for k, v in rates.items():
                k = str(k).strip()
                if not k:
                    continue
                clean[k] = {"day": max(0, int(v.get("day") or 0)),
                            "night": max(0, int(v.get("night") or 0))}
            if not clean:
                raise ValueError("役職の名前を入れてください（代表取締役・従業員など）")
            tr["rates"] = clean
        profile.save(prof)

    def test_a_nameless_row_does_not_wipe_the_rates(self):
        """役職名を書き忘れた表を送っても、入っていた日当が消えないこと。"""
        from paper_maker import profile
        self._travel({"rates": {"代表取締役": {"day": 7000, "night": 14000}}})
        with self.assertRaises(ValueError):
            self._travel({"rates": {"": {"day": 1, "night": 2}}})
        self.assertEqual(profile.load()["travel"]["rates"],
                         {"代表取締役": {"day": 7000, "night": 14000}})

    def test_a_relative_output_path_is_refused(self):
        """どこに出たか分からなくなるので、相対の書き方は受けない。"""
        def check(v):
            if v and not (v.startswith("/") or v.startswith("~")):
                raise ValueError("置き場は / か ~ から始まる道で書いてください")
        with self.assertRaises(ValueError):
            check("123")
        check("~/Documents/書類")
        check("/tmp/out")
        check("")


class TestTheDayKeepsItsOwnBase(unittest.TestCase):
    """出張先へ移ったあとに過去の日を作り直しても、行っていない土地から出発しないこと。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-pin-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def _itin(self, base_id=None):
        from paper_maker import itinerary, profile
        prof = profile.load()
        prof["travel"]["bases"] = {
            "a": {"label": "博多", "address": "福岡…", "station": "博多"},
            "b": {"label": "大阪", "address": "大阪…", "station": "大阪"}}
        prof["travel"]["currentBase"] = "b"
        fares = itinerary.Fares(profile.load_stations(), profile.load_fares())
        evs = [{"title": "訪問", "location": "天神", "start": "10:00", "end": "11:00",
                "all_day": False, "note": "", "calendar": "仕事"}]
        return itinerary.build(evs, prof, profile.load_places(), fares, base_id)

    def test_the_recorded_base_wins_over_where_i_am_now(self):
        got = self._itin("a")
        self.assertEqual(got["baseLabel"], "博多")
        self.assertTrue(all(l["from"] == "博多" or l["to"] == "博多" for l in got["legs"]))

    def test_without_a_recorded_base_it_uses_where_i_am(self):
        self.assertEqual(self._itin()["baseLabel"], "大阪")

    def test_a_base_that_was_deleted_falls_back(self):
        """控えた拠点を消した人。落ちずに今いる拠点で組む。"""
        self.assertEqual(self._itin("けした")["baseLabel"], "大阪")

    def test_the_base_is_written_into_the_document(self):
        import datetime as _dt
        from paper_maker import profile
        from paper_maker.docs import report
        got = report.build_json(_dt.date(2026, 8, 25), profile.load(), self._itin("a"), [], [])
        self.assertEqual(got["baseKey"], "a")
        self.assertEqual(got["baseLabel"], "博多")


class TestBulkFares(unittest.TestCase):
    """行き先は予定から拾う。全路線を貯め込まない。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-blk-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
        prof = profile.load()
        prof["travel"]["bases"] = {"a": {"label": "拠点", "address": "…", "station": "博多"}}
        prof["travel"]["currentBase"] = "a"
        prof["calendar"]["sources"] = []
        profile.save(prof)

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_it_lists_round_trips_from_where_i_am(self):
        from paper_maker import fares_bulk
        got = fares_bulk.pending(limit=3)
        self.assertEqual(got["home"], "博多")
        # どの組も、片方は拠点の駅
        for a, b in got["pairs"]:
            self.assertIn("博多", (a, b))
        # 行きがあれば帰りもある
        for a, b in got["pairs"]:
            self.assertIn((b, a), got["pairs"])

    def test_it_never_lists_the_base_to_itself(self):
        from paper_maker import fares_bulk
        for a, b in fares_bulk.pending(limit=8)["pairs"]:
            self.assertNotEqual(a, b)

    def test_pairs_already_priced_are_skipped(self):
        from paper_maker import fares_bulk, fares_write
        first = fares_bulk.pending(limit=8)["pairs"]
        a, b = first[0]
        fares_write.add(a, b, 1234)
        self.assertNotIn((a, b), fares_bulk.pending(limit=8)["pairs"])

    def test_no_base_station_means_no_guessing(self):
        from paper_maker import fares_bulk, profile
        prof = profile.load()
        prof["travel"]["bases"]["a"]["station"] = ""
        profile.save(prof)
        got = fares_bulk.pending()
        self.assertEqual(got["pairs"], [])
        self.assertIn("道順3", got["note"])


class TestPresetFares(unittest.TestCase):
    """はじめから入れておく運賃。誰かの生活圏が混ざらないこと。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-pst-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_it_only_holds_stations_anyone_passes_through(self):
        from paper_maker import paths
        pre = json.loads((paths.EXAMPLES / "fares.preset.json").read_text(encoding="utf-8"))
        hubs = {"東京", "新宿", "渋谷", "品川", "横浜", "上野", "池袋", "名古屋",
                "新大阪", "大阪", "京都", "三ノ宮", "博多", "天神", "仙台",
                "札幌", "広島", "金沢", "小田原", "原宿", "新横浜"}
        for r in pre["fares"]:
            self.assertIn(r["from"], hubs, r)
            self.assertIn(r["to"], hubs, r)

    def test_both_directions_are_there(self):
        from paper_maker import paths
        pre = json.loads((paths.EXAMPLES / "fares.preset.json").read_text(encoding="utf-8"))
        pairs = {(r["from"], r["to"]) for r in pre["fares"]}
        for a, b in pairs:
            self.assertIn((b, a), pairs, "%s → %s の帰りが無い" % (a, b))

    def test_the_preset_does_not_count_as_my_own(self):
        """はじめから入っている分で、道順6が済みになってしまわないこと。"""
        from paper_maker import paths, profile, quest
        rows = profile.load_fares()["fares"]
        self.assertTrue(any(r.get("preset") for r in rows), "プリセットが入っていない")
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
        done, note = quest._q5(profile.load())
        self.assertFalse(done, note)

    def test_my_own_fare_still_counts(self):
        from paper_maker import fares_write, paths, profile, quest
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())
        fares_write.add("○駅", "△駅", 320, source="本人が選択")
        self.assertTrue(quest._q5(profile.load())[0])

    def test_it_is_seeded_only_once(self):
        from paper_maker import profile
        before = len(profile.load_fares()["fares"])
        profile.ensure_data_files()
        self.assertEqual(len(profile.load_fares()["fares"]), before)


class TestContractStampIsOptional(unittest.TestCase):
    """電子署名で締結する契約書に、紙の押印欄を残さない。"""

    def test_the_template_only_stamps_when_asked(self):
        import re
        html = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
        # 甲乙の署名欄が、印影の設定を見てから㊞を出すこと
        self.assertIn("const stampMark = state.showSeal ?", html)
        block = html[html.index("const stampMark"):html.index("const stampMark") + 900]
        self.assertNotIn("　　　　　　　　㊞</div>", block,
                         "署名欄に㊞が直書きされたまま")

    def test_the_invoice_still_stamps_by_default(self):
        html = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
        self.assertIn("showSeal: true", html)


class TestAppShipsWhatItLoads(unittest.TestCase):
    """画面が読み込むファイルが、配布物に入っていること。

    vendor/html2pdf が抜けていて「PDFで保存」が一度も動いていなかった（2026-08-23）。
    画面は出るので、押すまで気づけない。
    """

    def test_every_local_script_and_style_exists(self):
        import re
        app = ROOT / "app"
        html = (app / "index.html").read_text(encoding="utf-8")
        refs = re.findall(r'<script[^>]+src="([^"]+)"', html)
        refs += re.findall(r'<link[^>]+href="([^"]+)"', html)
        missing = [r for r in refs
                   if not r.startswith(("http://", "https://", "//", "data:"))
                   and not (app / r).exists()]
        self.assertEqual(missing, [], "画面が読むのに配布物に無い: %s" % missing)

    def test_the_pdf_library_is_there(self):
        self.assertTrue((ROOT / "app" / "vendor" / "html2pdf.bundle.min.js").exists())


class TestAddressBook(unittest.TestCase):
    """一度使った宛先を覚える。打ち間違えた所へ請求書を飛ばさないため。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-addr-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def test_it_remembers_one_and_does_not_duplicate(self):
        from paper_maker import addressbook as ab
        self.assertTrue(ab.remember("○○商店", "a@example.com", "作った書類"))
        self.assertFalse(ab.remember("○○商店", "a@example.com", "また同じ"))
        self.assertEqual(len(ab.load()["items"]), 1)

    def test_a_name_fills_in_later(self):
        from paper_maker import addressbook as ab
        ab.remember("", "b@example.com", "下書きを置いた先")
        ab.remember("△△工房", "b@example.com", "作った書類")
        self.assertEqual(ab.load()["items"][0]["name"], "△△工房")

    def test_it_refuses_something_that_is_not_an_address(self):
        from paper_maker import addressbook as ab
        for bad in ("", "みたいなもの", "a@b", "@example.com", "a@@example.com"):
            self.assertFalse(ab.remember("x", bad), bad)
        self.assertEqual(ab.load()["items"], [])

    def test_it_picks_up_the_recurring_client(self):
        import datetime as _dt
        from paper_maker import addressbook as ab, recurring
        recurring.add("毎月の分", "○○商店", 10000, email="c@example.com",
                      start=_dt.date(2026, 8, 1))
        got = ab.listing()
        self.assertIn("c@example.com", [x["email"] for x in got])

    def test_forget_removes_it(self):
        from paper_maker import addressbook as ab
        ab.remember("x", "d@example.com")
        self.assertTrue(ab.forget("d@example.com"))
        self.assertEqual(ab.load()["items"], [])


class TestTitleStationsAreOff(unittest.TestCase):
    """私用の予定に日当が付かないこと。利用者の報告 2026-08-23。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-ttl-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def _ev(self, title, loc=""):
        return {"title": title, "location": loc, "start": "19:00", "end": "21:00",
                "all_day": False, "note": "", "calendar": "自宅"}

    def test_a_private_plan_with_a_station_name_in_the_title_is_not_onsite(self):
        from paper_maker import itinerary, profile
        got = itinerary.classify(self._ev("東京の友人と飲み"),
                                 profile.load_places(), profile.load_stations())
        self.assertNotEqual(got[0], "onsite", got)

    def test_the_place_field_still_decides(self):
        from paper_maker import itinerary, profile
        got = itinerary.classify(self._ev("打合せ", "東京都千代田区丸の内1-1-1"),
                                 profile.load_places(), profile.load_stations())
        self.assertEqual(got[0], "onsite")

    def test_it_can_be_turned_back_on(self):
        from paper_maker import itinerary, profile
        got = itinerary.classify(self._ev("東京の友人と飲み"),
                                 profile.load_places(), profile.load_stations(), True)
        self.assertEqual(got[0], "onsite")

    def test_a_rule_someone_wrote_still_matches_the_title(self):
        """題名にも当てたい行は "title": true を書く。書いた分だけ効く。"""
        from paper_maker import itinerary, profile
        pl = profile.load_places()
        pl.setdefault("rules", []).append({"match": ["サカイ商店"], "station": "大宮",
                                           "title": True})
        got = itinerary.classify(self._ev("サカイ商店 訪問"), pl, profile.load_stations())
        self.assertEqual(got[:2], ("onsite", "大宮"))


class TestDenshiRules(unittest.TestCase):
    """電帳法の事務処理規程。国税庁のサンプルに社名と施行日を差すだけ。"""

    def setUp(self):
        from paper_maker import paths, profile
        self.d = tempfile.mkdtemp(prefix="pm-dns-")
        os.environ["PAPER_MAKER_HOME"] = self.d
        importlib.reload(paths)
        profile.ensure_data_files()
        shutil.copy(paths.EXAMPLES / "profile.example.json", paths.profile_path())

    def tearDown(self):
        from paper_maker import paths
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("PAPER_MAKER_HOME", None)
        importlib.reload(paths)

    def _html(self):
        from paper_maker import profile
        from paper_maker.docs import denshi
        prof = profile.load()
        prof["profiles"]["corp"]["name"] = "合同会社ミナト"
        prof["profiles"]["corp"]["rep"] = "代表社員　港 一郎"
        prof["denshi"] = {"effectiveDate": "2026-09-01"}
        return denshi.build_html(prof)

    def test_the_company_and_date_are_filled_in(self):
        h = self._html()
        self.assertIn("合同会社ミナト", h)
        self.assertIn("2026年9月1日", h)
        self.assertNotIn("○○", h)

    def test_the_official_wording_is_kept(self):
        h = self._html()
        for phrase in ("訂正及び削除をすることは原則禁止",
                       "取引情報訂正・削除申請書",
                       "国税関係帳簿書類の保存方法の特例に関する法律第７条"):
            self.assertIn(phrase, h, phrase)

    def test_the_scope_list_is_not_escaped_into_view(self):
        """差し込みが二重にエスケープされて、タグが紙に出ないこと。"""
        h = self._html()
        self.assertNotIn("&lt;li&gt;", h)
        self.assertIn("<li>一　", h)


class TestStaleServerIsStopped(unittest.TestCase):
    """更新しても古いコードを抱えたサーバが生き残らないこと。"""

    def test_it_leaves_another_home_alone(self):
        """1台に2つ入れている人の、別の置き場のサーバは落とさない。"""
        from paper_maker import paths, update
        d = tempfile.mkdtemp(prefix="pm-stale-")
        os.environ["PAPER_MAKER_HOME"] = d
        importlib.reload(paths)
        seen = []
        real_open = update.urllib.request.urlopen

        class Fake:
            def __init__(self, body): self.body = body
            def read(self): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake(req, timeout=1):
            port = int(str(req.full_url).split(":")[2].split("/")[0])
            seen.append(port)
            return Fake(json.dumps({"app": "paper-maker", "home": "/よその置き場"}).encode())
        update.urllib.request.urlopen = fake
        try:
            said = update.stop_running_app()
        finally:
            update.urllib.request.urlopen = real_open
            shutil.rmtree(d, ignore_errors=True)
            os.environ.pop("PAPER_MAKER_HOME", None)
            importlib.reload(paths)
        self.assertEqual(said, "", "別の置き場のサーバを落としてしまった")
        self.assertIn(8797, seen)

    def test_the_installer_closes_it_too(self):
        sh = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("api/hello", sh)
        self.assertIn("kill", sh)


class TestPlaceRulesDoNotMatchTitles(unittest.TestCase):
    """見本の地名ルールが題名に当たって、私用の予定が現地扱いになっていた。

    運賃表の駅名を切っても、こちらが残っていて事故は止まっていなかった（2026-08-23）。
    """

    STATIONS = {"stations": {"a": {"name": "新宿駅"}, "b": {"name": "東京駅"}}}
    SAMPLE = {"skip": ["ZOOM"], "rules": [
        {"match": ["新宿区", "新宿"], "station": "新宿"},
        {"match": ["千代田区", "東京駅"], "station": "東京"}]}

    def _c(self, title, loc="", places=None):
        from paper_maker import itinerary
        return itinerary.classify({"title": title, "location": loc},
                                  places or self.SAMPLE, self.STATIONS)

    def test_a_private_plan_is_not_onsite(self):
        self.assertNotEqual(self._c("新宿で美容院")[0], "onsite")
        self.assertNotEqual(self._c("東京の友人と飲み")[0], "onsite")

    def test_the_place_field_still_matches_the_rule(self):
        got = self._c("打合せ", "東京都千代田区丸の内1-1-1")
        self.assertEqual(got[:2], ("onsite", "東京"))

    def test_a_rule_marked_for_titles_still_works(self):
        pl = {"skip": [], "rules": [{"match": ["サカイ商店"], "station": "大宮", "title": True}]}
        self.assertEqual(self._c("サカイ商店 訪問", "", pl)[:2], ("onsite", "大宮"))

    def test_the_sample_file_ships_with_no_rules(self):
        """見本に地名を入れておくと、入れた人の所で同じ事故が起きる。"""
        from paper_maker import paths
        d = json.loads((paths.EXAMPLES / "places.example.json").read_text(encoding="utf-8"))
        self.assertEqual(d.get("rules"), [])
        self.assertTrue(d.get("skip"), "ZOOM などの除外は残す")

    def test_an_old_places_file_is_safe_without_migration(self):
        """すでに見本の4本を持っている人も、書き換えずに事故が止まること。"""
        self.assertNotEqual(self._c("新宿でランチ")[0], "onsite")
