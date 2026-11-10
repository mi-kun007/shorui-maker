"""Gmail の下書きに、PDF を付けて置く。

**送らない。下書きに置くだけ。** 相手に届く行為は人が押す。
IMAP で下書きフォルダに1通足すので、Gmail の画面を開けばそこに居る。

なぜ IMAP か。
  Gmail の下書きを URL で開く形（今までのボタン）は、添付を渡せない。
  API を使うと、利用者ごとに Google Cloud で鍵を発行してもらう手順が要る。
  月2,000円の道具に載せる手間ではない。
  IMAP なら、アプリパスワードを1つ発行して貼るだけで済む。

アプリパスワードは ~/.paper-maker/secrets.env に、本人だけ読める権限で入る。
設定ファイルにも書類にも出さない。
"""
import datetime as dt
import email.utils
import imaplib
import mimetypes
import pathlib
import time
from email.header import Header
from email.message import EmailMessage

HOST = "imap.gmail.com"
DRAFTS = ("[Gmail]/&Tgtm+DBN-",  # 下書き（日本語UI）
          "[Gmail]/Drafts", "[Gmail]/&LAA-", "Drafts")


class MailError(Exception):
    pass


def _creds():
    from . import bridge
    user = bridge.read_secret("GMAIL_ADDRESS")
    app = bridge.read_secret("GMAIL_APP_PASSWORD")
    if not user or not app:
        raise MailError("Gmail のアドレスとアプリパスワードが入っていません（⚙設定 → メール）")
    return user, app.replace(" ", "")


def build(to: str, subject: str, body: str, sender: str,
          attachments=None, cc: str = "") -> EmailMessage:
    m = EmailMessage()
    m["To"] = to
    if cc:
        m["Cc"] = cc
    m["From"] = sender
    m["Subject"] = str(Header(subject, "utf-8"))
    m["Date"] = email.utils.formatdate(localtime=True)
    m.set_content(body)
    for path in (attachments or []):
        p = pathlib.Path(path).expanduser()
        if not p.exists():
            raise MailError("添付が見つかりません: %s" % p)
        ctype, _enc = mimetypes.guess_type(p.name)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        m.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype,
                         filename=p.name)
    return m


def _pick_drafts(box: imaplib.IMAP4_SSL) -> str:
    ok, boxes = box.list()
    names = []
    if ok == "OK":
        for raw in boxes or []:
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            if '"' in line:
                names.append(line.rsplit('"', 2)[-2])
    for cand in DRAFTS:
        if cand in names:
            return cand
    for n in names:
        if "Draft" in n or "下書き" in n:
            return n
    raise MailError("下書きフォルダが見つかりませんでした（IMAP が有効か確かめてください）")


def save_draft(to: str, subject: str, body: str, attachments=None, cc: str = "") -> dict:
    """下書きに1通置く。置いた場所を返す。"""
    user, app = _creds()
    msg = build(to, subject, body, user, attachments, cc)
    try:
        box = imaplib.IMAP4_SSL(HOST)
    except OSError as e:
        raise MailError("Gmail に繋がりませんでした（%s）" % e.__class__.__name__)
    try:
        try:
            box.login(user, app)
        except imaplib.IMAP4.error:
            raise MailError("Gmail にログインできませんでした。"
                            "アプリパスワードと、2段階認証が有効かを確かめてください")
        folder = _pick_drafts(box)
        box.append(folder, "\\Draft",
                   imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    finally:
        try:
            box.logout()
        except Exception:
            pass
    return {"folder": folder, "to": to, "subject": subject,
            "attached": [pathlib.Path(a).name for a in (attachments or [])],
            "at": dt.datetime.now().isoformat(timespec="seconds")}


def check() -> tuple:
    """繋がるかだけ見る。下書きは作らない。"""
    try:
        user, app = _creds()
    except MailError as e:
        return False, str(e)
    try:
        box = imaplib.IMAP4_SSL(HOST)
    except OSError as e:
        return False, "Gmail に繋がりませんでした（%s）" % e.__class__.__name__
    try:
        box.login(user, app)
        folder = _pick_drafts(box)
        return True, "%s に置けます（%s）" % (folder, user)
    except imaplib.IMAP4.error:
        return False, ("ログインできませんでした。アプリパスワードと、"
                       "2段階認証が有効かを確かめてください")
    except MailError as e:
        return False, str(e)
    finally:
        try:
            box.logout()
        except Exception:
            pass
