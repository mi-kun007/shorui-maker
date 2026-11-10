"""毎朝の自動実行を OS に登録する。Mac=launchd / Linux=cron / Windows=schtasks。"""
import os
import pathlib
import subprocess
import sys

from . import paths


def _env_pairs():
    """自動実行に渡す環境。登録した時のターミナルの中身を写す。

    PAPER_MAKER_HOME … 置き場を変えている人。抜けると手押しと自動で書き先が変わる
    PATH             … launchd が渡すのは /usr/bin:/bin:/usr/sbin:/sbin だけ。
                       nvm や homebrew に入れた claude / codex がここに居ない。
                       抜けたまま回すと、自動の回だけ AI が使えず、
                       住所から駅を引けないので交通費が出ない。実測 2026-08-20。
    """
    out = {}
    v = os.environ.get("PAPER_MAKER_HOME")
    if v:
        out["PAPER_MAKER_HOME"] = v
    path = os.environ.get("PATH", "")
    if path:
        out["PATH"] = path
    return out

LABEL = "jp.paper-maker.daily"
SYNC_LABEL = "jp.paper-maker.sync"


def _python() -> str:
    return sys.executable


def _cmd_parts(sub="daily"):
    return [_python(), "-m", "paper_maker", sub]


def _plist_path(label):
    return pathlib.Path.home() / "Library/LaunchAgents" / (label + ".plist")


def _mac_install(label, sub, when_xml, desc) -> str:
    plist = _plist_path(label)
    plist.parent.mkdir(parents=True, exist_ok=True)
    args = "".join("<string>%s</string>" % a for a in _cmd_parts(sub))
    env = _env_pairs()
    env_xml = ""
    if env:
        env_xml = "<key>EnvironmentVariables</key><dict>%s</dict>\n  " % "".join(
            "<key>%s</key><string>%s</string>" % (k, v) for k, v in env.items())
    plist.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>%s</string>
  <key>ProgramArguments</key><array>%s</array>
  <key>WorkingDirectory</key><string>%s</string>
  %s%s
  <key>StandardOutPath</key><string>%s</string>
  <key>StandardErrorPath</key><string>%s</string>
</dict></plist>
""" % (label, args, paths.APP_ROOT, env_xml, when_xml, paths.log_path(), paths.log_path()), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
    if r.returncode != 0:
        return "launchctl load に失敗: %s" % (r.stderr.strip() or r.stdout.strip())
    return "登録しました（%s）: %s" % (desc, plist)


def install(hour=6, minute=0, every=0) -> str:
    """every に分を入れると、その間隔で `sync` を回す別の登録になる。
    0 なら今までどおり、1日1回 `daily`。

    間隔で回すほうは軽い処理だけにしてある。カレンダーの読み直しに数十秒かかることがあるので、
    重い書類作りを毎時走らせない。
    """
    if every:
        every = max(5, int(every))
        sub, label, desc = "sync", SYNC_LABEL, "%d分ごと" % every
    else:
        sub, label, desc = "daily", LABEL, "毎日 %02d:%02d" % (hour, minute)

    if sys.platform == "darwin":
        when = ("<key>StartInterval</key><integer>%d</integer>" % (every * 60)) if every else (
            "<key>StartCalendarInterval</key><dict><key>Hour</key><integer>%d</integer>"
            "<key>Minute</key><integer>%d</integer></dict>" % (hour, minute))
        return _mac_install(label, sub, when, desc)

    if sys.platform == "win32":
        env = _env_pairs()
        pre = ("set %s=%s && " % list(env.items())[0]) if env else ""
        tr = 'cmd /c "%scd /d %s && \"%s\" -m paper_maker %s"' % (pre, paths.APP_ROOT, _python(), sub)
        name = "paper-maker %s" % sub
        if every:
            cmd = ["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(every), "/TN", name, "/TR", tr]
        else:
            cmd = ["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", "%02d:%02d" % (hour, minute),
                   "/TN", name, "/TR", tr]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return ("登録しました（%s）" % desc) if r.returncode == 0 else ("schtasks に失敗: " + (r.stderr or r.stdout))

    # Linux: cron
    sched = ("*/%d * * * *" % every) if every else ("%d %d * * *" % (minute, hour))
    env = "".join("%s=%s " % (k, v) for k, v in _env_pairs().items())
    line = "%s cd %s && %s%s -m paper_maker %s >> %s 2>&1 # %s" % (
        sched, paths.APP_ROOT, env, _python(), sub, paths.log_path(), label)
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    keep = [l for l in cur.splitlines() if label not in l]
    r = subprocess.run(["crontab", "-"], input="\n".join(keep + [line]) + "\n", text=True, capture_output=True)
    return ("登録しました（%s）" % desc) if r.returncode == 0 else ("crontab に失敗: " + r.stderr)


def install_all(hour=6, minute=0, every=60) -> str:
    """朝の1回と、時間ごとの見直しを両方入れる。

    片方だけでは足りない。朝の回は前日ぶんを締めるため、
    時間ごとの回は、今日の予定を足した分をその日のうちに反映するため。
    every=0 なら朝の回だけ。
    """
    msgs = [install(hour, minute, 0)]
    if every:
        msgs.append(install(hour, minute, every))
    return "\n".join(msgs)


def remove(which="all") -> str:
    labels = {"daily": [LABEL], "sync": [SYNC_LABEL]}.get(which, [LABEL, SYNC_LABEL])
    if sys.platform == "darwin":
        for lb in labels:
            p = _plist_path(lb)
            subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
            if p.exists():
                p.unlink()
        return "解除しました"
    if sys.platform == "win32":
        for sub in ({"daily": ["daily"], "sync": ["sync"]}.get(which, ["daily", "sync"])):
            subprocess.run(["schtasks", "/Delete", "/F", "/TN", "paper-maker %s" % sub], capture_output=True)
        return "解除しました"
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    keep = [l for l in cur.splitlines() if not any(lb in l for lb in labels)]
    subprocess.run(["crontab", "-"], input="\n".join(keep) + "\n", text=True, capture_output=True)
    return "解除しました"


def _points_here(label) -> bool:
    """その登録は、今の置き場を向いているか。

    1台に2つ入れている人（自分用と客先用）がいる。
    別の置き場を向いた登録を「自分の分」と数えると、道順が済みになってしまう。
    """
    p = _plist_path(label)
    if not p.exists():
        return False
    mine = str(paths.data_dir())
    try:
        import plistlib
        env = plistlib.loads(p.read_bytes()).get("EnvironmentVariables") or {}
    except Exception:
        return True
    theirs = env.get("PAPER_MAKER_HOME")
    if not theirs:
        # 置き場を指定していない登録は、既定の置き場ぶん
        return mine == str(pathlib.Path.home() / ".paper-maker")
    return str(pathlib.Path(theirs)) == mine


def status() -> str:
    out = []
    if sys.platform == "darwin":
        for lb, nm in ((LABEL, "毎日の書類作り"), (SYNC_LABEL, "定期の見直し")):
            out.append("%s: %s" % (nm, "登録あり" if _points_here(lb) else "未登録"))
    elif sys.platform == "win32":
        for sub, nm in (("daily", "毎日の書類作り"), ("sync", "定期の見直し")):
            r = subprocess.run(["schtasks", "/Query", "/TN", "paper-maker %s" % sub], capture_output=True, text=True)
            out.append("%s: %s" % (nm, "登録あり" if r.returncode == 0 else "未登録"))
    else:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        for lb, nm in ((LABEL, "毎日の書類作り"), (SYNC_LABEL, "定期の見直し")):
            out.append("%s: %s" % (nm, "登録あり" if lb in cur else "未登録"))
    return " / ".join(out)
