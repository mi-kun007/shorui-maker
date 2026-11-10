"""書類メーカー 配布版。

一人会社の見積・請求・領収・契約・出張報告に加えて、
カレンダーから営業報告書と出張精算を毎日つくる。旅費規程も出す。
依存は Python 標準ライブラリだけ。PDF 化は利用者の Chrome / Edge を借りる。
"""
import pathlib

_VER = pathlib.Path(__file__).resolve().parent.parent / "VERSION"
__version__ = _VER.read_text(encoding="utf-8").strip() if _VER.exists() else "0.0.0-dev"
