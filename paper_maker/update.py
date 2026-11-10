"""更新。zip を取ってきて、SHA256 を照合してから入れ替える。

取り口は3つ。上から順に試す。
  1. gh コマンド      … 入っていて GitHub にログイン済みなら、これが一番速い
  2. 直リンク         … 配布元が公開なら鍵なしで取れる
  3. 手元の zip       … 画面から落とした物を渡す（paper-maker update --file …）

配布元が private だと 2 は 404 で返る。実測 2026-08-20。
だから 1 と 3 を用意してある。**404 を「更新なし」と黙らせない。**

入れ替える前に、今の中身をまるごと控える。戻すのは paper-maker update --rollback。
設定と控え（~/.paper-maker）は触らない。入れ替えるのはプログラムの側だけ。

manifest.json の形：
  {"version": "1.1.0", "zip": "https://.../paper-maker-v1.1.0.zip", "sha256": "..."}
"""
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile

from . import __version__, paths

MANIFEST_URL = "https://github.com/mi-kun007/shorui-maker/releases/latest/download/manifest.json"
REPO = "mi-kun007/shorui-maker"

HOW_TO_GET = """配布元が private なので、鍵なしでは取れません。どちらかで。

  1. gh コマンドを入れてログインする
       brew install gh && gh auth login
     入れたあとは paper-maker update だけで通ります。

  2. 画面から落とす
       https://github.com/%s/releases/latest
     paper-maker-vX.Y.Z.zip を落として
       paper-maker update --file ~/Downloads/paper-maker-vX.Y.Z.zip""" % REPO


def _fetch(url: str, timeout=60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "paper-maker/%s" % __version__})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _vtuple(v: str):
    return tuple(int(x) for x in v.strip().lstrip("v").split(".")[:3])


def _gh_ready() -> bool:
    if not shutil.which("gh"):
        return False
    r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    return r.returncode == 0


def _gh_download(name: str) -> bytes:
    """gh でリリースの添付を1つ落とす。private でもログインしていれば通る。"""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["gh", "release", "download", "--repo", REPO,
                            "--pattern", name, "--dir", tmp, "--clobber"],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[:200])
        got = list(pathlib.Path(tmp).iterdir())
        if not got:
            raise RuntimeError("%s が見つかりませんでした" % name)
        return got[0].read_bytes()


def check(manifest_url=MANIFEST_URL) -> dict:
    """新しい版があるか。gh を先に試して、無ければ直リンク。

    manifest_url を自分で指定したときは gh を使わない。
    「この manifest を見ろ」と言われているのに、別の所から取るのはおかしい。
    """
    raw = None
    if manifest_url == MANIFEST_URL and _gh_ready():
        try:
            raw = _gh_download("manifest.json")
        except Exception:
            raw = None
    if raw is None:
        try:
            raw = _fetch(manifest_url)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                raise RuntimeError("配布元から取れませんでした（HTTP %d）。\n\n%s" % (e.code, HOW_TO_GET))
            raise
    m = json.loads(raw.decode("utf-8"))
    m["current"] = __version__
    m["newer"] = _vtuple(m["version"]) > _vtuple(__version__)
    return m


def apply(manifest_url=MANIFEST_URL, dry_run=False) -> str:
    m = check(manifest_url)
    if not m["newer"]:
        return "最新です（%s）" % __version__
    name = m["zip"].rsplit("/", 1)[-1]
    data = None
    if manifest_url == MANIFEST_URL and _gh_ready():
        try:
            data = _gh_download(name)
        except Exception:
            data = None
    if data is None:
        try:
            data = _fetch(m["zip"])
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                raise RuntimeError("zip を取れませんでした（HTTP %d）。\n\n%s" % (e.code, HOW_TO_GET))
            raise
    digest = hashlib.sha256(data).hexdigest()
    if digest.lower() != str(m.get("sha256", "")).lower():
        return "中止：zip の SHA256 が manifest と一致しません（改ざんか破損）"
    if dry_run:
        return "更新あり %s → %s（SHA256 一致・dry-run）" % (__version__, m["version"])
    return _swap(data, m["version"])


def from_file(zip_path, sha256="") -> str:
    """手元の zip で入れ替える。画面から落とした物を渡す道。"""
    p = pathlib.Path(zip_path).expanduser()
    if not p.exists():
        raise RuntimeError("見つかりません: %s" % p)
    data = p.read_bytes()
    if sha256 and hashlib.sha256(data).hexdigest().lower() != sha256.lower():
        return "中止：zip の SHA256 が渡された値と一致しません"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            top = names[0].split("/")[0] if names and "/" in names[0] else ""
            vf = "%s/VERSION" % top if top else "VERSION"
            ver = z.read(vf).decode("utf-8").strip() if vf in names else "?"
    except (zipfile.BadZipFile, KeyError):
        raise RuntimeError("zip として読めませんでした: %s" % p.name)
    if ver != "?" and _vtuple(ver) < _vtuple(__version__):
        return "中止：渡された zip は今より古い版です（%s → %s）" % (__version__, ver)
    return _swap(data, ver)


def rollback() -> str:
    """控えに戻す。入れ替えで動かなくなった時の逃げ道。

    フォルダそのものは消さない。中身だけ入れ替える。
    ここを rmtree すると、そのフォルダに居るプロセス（開いている画面・自動実行）が
    行き場を失う。実測 2026-08-20、戻した直後に python -m paper_maker が
    「No module named paper_maker」で落ちた。
    """
    root = paths.APP_ROOT
    baks = sorted(root.parent.glob(root.name + ".bak-*"), key=lambda p: p.stat().st_mtime)
    if not baks:
        return "戻せる控えがありません"
    bak = baks[-1]
    _replace_contents(root, bak)
    return "戻しました（%s の中身に）" % bak.name


def _replace_contents(root: pathlib.Path, src: pathlib.Path):
    for item in root.iterdir():
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    for item in src.iterdir():
        dst = root / item.name
        shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)


def stop_running_app(port_hint=8797) -> str:
    """立ちっぱなしの画面サーバを落とす。

    ファイルを入れ替えても、走っているサーバは前の版のコードを抱えたままになる。
    画面は新しいのに API だけ古い、という一番分かりにくい壊れ方をする。
    実測 2026-08-23：8/19 に起動した 0.1.0 のサーバが生きていた。
    """
    import signal
    import urllib.request
    mine = str(paths.data_dir())
    stopped = []
    ports = [port_hint] + [p for p in range(8797, 8811) if p != port_hint]
    for port in ports:
        if port in stopped:
            continue
        try:
            req = urllib.request.Request("http://127.0.0.1:%d/api/hello" % port)
            with urllib.request.urlopen(req, timeout=1) as r:
                who = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        if who.get("app") != "paper-maker":
            continue          # よその物は触らない
        if who.get("home") and str(who["home"]) != mine:
            continue          # 別の置き場で動いている分（1台に2つ入れている人）は残す
        try:
            out = subprocess.run(["lsof", "-ti", "tcp:%d" % port],
                                 capture_output=True, text=True, timeout=10)
            for pid in out.stdout.split():
                os.kill(int(pid), signal.SIGTERM)
            stopped.append(port)
        except Exception:
            continue
    if not stopped:
        return ""
    return "開いていた画面を閉じました（%s）。アイコンを押し直してください" % (
        "／".join("ポート%d" % p for p in stopped))


def _swap(data: bytes, version: str) -> str:
    root = paths.APP_ROOT
    backup = root.parent / (root.name + ".bak-" + __version__)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            # zip 内の先頭ディレクトリを剥がして展開
            names = z.namelist()
            top = names[0].split("/")[0] if names and "/" in names[0] else ""
            for n in names:
                if n.endswith("/"):
                    continue
                rel = n[len(top) + 1:] if top and n.startswith(top + "/") else n
                # パス脱出を防ぐ
                if rel.startswith("/") or ".." in pathlib.PurePosixPath(rel).parts:
                    continue
                dst = pathlib.Path(tmp) / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(z.read(n))
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(root, backup)
        for item in pathlib.Path(tmp).iterdir():
            target = root / item.name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(item), str(target))
    said = stop_running_app()
    return "更新しました %s → %s（戻すのは paper-maker update --rollback）%s" % (
        __version__, version, ("\n" + said) if said else "")
