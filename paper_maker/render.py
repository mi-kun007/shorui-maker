"""HTML → PDF。利用者の Chrome / Edge / Chromium を借りる。

ADR-0004: headless Chrome は PDF を書いた後に終了しないことがある。
だから Popen で起動し、PDF ができたら止める。user-data-dir は毎回使い捨て。
ブラウザが無ければ HTML を残して None を返す（呼び元がその旨を伝える）。
"""
import base64
import html
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

from . import paths

_CANDIDATES = {
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ],
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "linux": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"],
}


def find_browser(explicit: str = "") -> str:
    if explicit:
        p = pathlib.Path(explicit).expanduser()
        if p.exists():
            return str(p)
    key = "linux" if sys.platform.startswith("linux") else sys.platform
    for c in _CANDIDATES.get(key, []):
        if os.path.isabs(c):
            if pathlib.Path(c).exists():
                return c
        else:
            w = shutil.which(c)
            if w:
                return w
    return ""


def html_to_pdf(html_path: pathlib.Path, pdf_path: pathlib.Path, browser: str = "",
                wait_sec: int = 60) -> bool:
    """成功したら True。ブラウザが無い／時間切れなら False（HTML は残る）。"""
    exe = find_browser(browser)
    if not exe:
        return False
    return url_to_pdf(html_path.resolve().as_uri(), pdf_path, exe, wait_sec)


def url_to_pdf(url: str, pdf_path: pathlib.Path, exe: str, wait_sec: int = 60) -> bool:
    pdf_path = pathlib.Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()
    tmp = tempfile.mkdtemp(prefix="pm-chrome-")
    args = [exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            "--allow-file-access-from-files", "--user-data-dir=%s" % tmp,
            "--print-to-pdf=%s" % pdf_path, url]
    ok = False
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + wait_sec
        while time.time() < deadline:
            if pdf_path.exists() and pdf_path.stat().st_size > 1000:
                # 書き終わりを少し待つ（サイズが変わらなくなるまで）
                s1 = pdf_path.stat().st_size
                time.sleep(0.5)
                if pdf_path.stat().st_size == s1:
                    ok = True
                    break
            if proc.poll() is not None:
                ok = pdf_path.exists() and pdf_path.stat().st_size > 1000
                break
            time.sleep(0.3)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def app_doc_url(doc: dict, profiles: dict) -> str:
    """app/index.html にデータを渡す URL（#doc=base64）。見積・請求・領収・契約・出張報告用。"""
    payload = {"doc": doc, "profiles": profiles}
    b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return paths.APP_HTML.resolve().as_uri() + "#doc=" + urllib.parse.quote(b64, safe="")


def app_doc_to_pdf(doc: dict, profiles: dict, pdf_path: pathlib.Path, browser: str = "",
                   travel: dict = None) -> bool:
    """書類データを Chrome の引数に載せると `ps` で他のユーザーに見える。
    だから一時 HTML に書いて、その中から app へ飛ばす。引数に出るのは一時ファイルのパスだけ。"""
    exe = find_browser(browser)
    if not exe:
        return False
    payload = {"doc": doc, "profiles": profiles}
    if travel:
        payload["travel"] = travel
    b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    target = paths.APP_HTML.resolve().as_uri() + "#doc=" + urllib.parse.quote(b64, safe="")
    fd, tmp_html = tempfile.mkstemp(prefix="pm-doc-", suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write('<!doctype html><meta charset="utf-8"><script>location.replace(%s);</script>' % json.dumps(target))
        try:
            os.chmod(tmp_html, 0o600)
        except OSError:
            pass
        return url_to_pdf(pathlib.Path(tmp_html).as_uri(), pdf_path, exe)
    finally:
        try:
            os.unlink(tmp_html)
        except OSError:
            pass


# ---------- ちいさなテンプレート ----------

def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def fill(template_name: str, ctx: dict) -> str:
    """{{key}} をエスケープして差し込む。{{{key}}} は生のまま（表の HTML など、こちらで作った物だけ）。"""
    t = (paths.TEMPLATES / template_name).read_text(encoding="utf-8")
    for k, v in ctx.items():
        t = t.replace("{{{%s}}}" % k, "" if v is None else str(v))
        t = t.replace("{{%s}}" % k, esc(v))
    return t
