"""デスクトップにアイコンを置く。ターミナルを開かずに使えるように。

押すと、設定が無ければ空の設定を作り、ブラウザで画面を開く。
そこから会社名も何もかも入れられる。ターミナルは一度も要らない。
"""
import os
import pathlib
import shutil
import subprocess
import sys

from . import paths

APP_NAME = "書類メーカー"


def desktop_dir() -> pathlib.Path:
    """デスクトップの場所。日本語環境でも英語名のことがあるので両方見る。"""
    home = pathlib.Path.home()
    for n in ("Desktop", "デスクトップ"):
        p = home / n
        if p.is_dir():
            return p
    return home


def _launch_script() -> str:
    """アイコンから走る中身。python の場所を焼き込む（PATH が無い所から起動されるため）。"""
    return """#!/bin/bash
# 書類メーカー。押すと画面が開きます
export PAPER_MAKER_HOME="%(home)s"
cd "%(root)s" || exit 1
exec "%(python)s" -m paper_maker open
""" % {"home": os.environ.get("PAPER_MAKER_HOME", ""), "root": paths.APP_ROOT, "python": sys.executable}


def _plist(bundle_id="jp.paper-maker.app") -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>%s</string>
  <key>CFBundleDisplayName</key><string>%s</string>
  <key>CFBundleIdentifier</key><string>%s</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
</dict></plist>
""" % (APP_NAME, APP_NAME, bundle_id)


def install_mac() -> str:
    app = desktop_dir() / (APP_NAME + ".app")
    if app.exists():
        shutil.rmtree(app)
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_text(_plist(), encoding="utf-8")
    ex = app / "Contents" / "MacOS" / "launch"
    ex.write_text(_launch_script(), encoding="utf-8")
    ex.chmod(0o755)
    icns = paths.APP_HTML.parent / "icon.icns"
    if icns.exists():
        shutil.copy(icns, app / "Contents" / "Resources" / "icon.icns")
    # Finder にアイコンを見直させる
    subprocess.run(["touch", str(app)], capture_output=True)
    return str(app)


def install_windows() -> str:
    """ショートカットを作る。PowerShell に作らせるのが一番素直。"""
    d = desktop_dir()
    bat = paths.data_dir() / "書類メーカー.cmd"
    bat.parent.mkdir(parents=True, exist_ok=True)
    home = os.environ.get("PAPER_MAKER_HOME", "")
    bat.write_text("@echo off\r\n%scd /d \"%s\"\r\n\"%s\" -m paper_maker open\r\n" % (
        ('set PAPER_MAKER_HOME=%s\r\n' % home) if home else "", paths.APP_ROOT, sys.executable),
        encoding="utf-8")
    lnk = d / (APP_NAME + ".lnk")
    ico = paths.APP_HTML.parent / "icon.ico"
    ps = ("$w = New-Object -ComObject WScript.Shell; "
          "$s = $w.CreateShortcut('%s'); $s.TargetPath = '%s'; "
          "$s.WorkingDirectory = '%s'; %s $s.Save()") % (
        lnk, bat, paths.APP_ROOT, ("$s.IconLocation = '%s';" % ico) if ico.exists() else "")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    if r.returncode != 0:
        return "ショートカットを作れませんでした: %s" % (r.stderr or r.stdout).strip()[:120]
    return str(lnk)


def install_linux() -> str:
    d = desktop_dir()
    f = d / "paper-maker.desktop"
    icon = paths.APP_HTML.parent / "icon.png"
    home = os.environ.get("PAPER_MAKER_HOME", "")
    f.write_text("""[Desktop Entry]
Type=Application
Name=%s
Exec=env %s %s -m paper_maker open
Path=%s
Icon=%s
Terminal=false
""" % (APP_NAME, ("PAPER_MAKER_HOME=%s" % home) if home else "", sys.executable, paths.APP_ROOT, icon),
        encoding="utf-8")
    f.chmod(0o755)
    return str(f)


def install() -> str:
    if sys.platform == "darwin":
        return install_mac()
    if sys.platform == "win32":
        return install_windows()
    return install_linux()


def remove() -> str:
    d = desktop_dir()
    gone = []
    for n in (APP_NAME + ".app", APP_NAME + ".lnk", "paper-maker.desktop"):
        p = d / n
        if p.exists():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            gone.append(n)
    return "消しました: %s" % "、".join(gone) if gone else "デスクトップに見つかりませんでした"
