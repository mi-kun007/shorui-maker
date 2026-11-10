"""毎日動き続けるための、地味な2つ。

**ログを回す。** 1時間ごとに回ると、1年で8,760行。放っておくと増え続ける。
1MB を超えたら1本だけ .1 に退避して、そこから先は捨てる。
残すのは日付と件数だけなので、古い分を捨てても困らない。

**二重起動を止める。** 定期の回と、人が画面から押した分がぶつかると、
同じ書類を2つのプロセスが同時に書く。PDF を焼いている最中に上書きされると壊れる。
先に取った方が最後まで持つ。取れなかった方は、何もせず黙って終わる。
"""
import contextlib
import errno
import os
import pathlib
import time

from . import paths

MAX_LOG = 1024 * 1024
STALE_LOCK_SEC = 30 * 60


def roll_log(max_bytes=MAX_LOG):
    p = paths.log_path()
    if not p.exists() or p.stat().st_size <= max_bytes:
        return False
    old = p.with_suffix(p.suffix + ".1")
    if old.exists():
        old.unlink()
    p.rename(old)
    return True


@contextlib.contextmanager
def only_one(name="daily"):
    """取れたら True を渡す。取れなければ False。**待たない。**

    次の回が1時間後に来るので、待つ意味がない。待つと launchd の枠に居座る。
    """
    lock = paths.data_dir() / (".%s.lock" % name)
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    try:
        # 置き去りの錠前は、古ければ外す（強制終了や再起動のあと）
        if lock.exists():
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK_SEC:
                    lock.unlink()
            except OSError:
                pass
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            yield False
            return
        yield True
    finally:
        if fd is not None:
            os.close(fd)
            with contextlib.suppress(OSError):
                lock.unlink()
