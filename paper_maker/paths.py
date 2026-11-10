"""置き場所。利用者のデータはぜんぶ ~/.paper-maker の下。コードと混ぜない。"""
import os
import pathlib

PKG_DIR = pathlib.Path(__file__).resolve().parent
APP_ROOT = PKG_DIR.parent                      # リポジトリ（or 展開先）のルート
TEMPLATES = PKG_DIR / "templates"
APP_HTML = APP_ROOT / "app" / "index.html"
EXAMPLES = APP_ROOT / "examples"


def data_dir() -> pathlib.Path:
    """環境変数 PAPER_MAKER_HOME があればそこ。テストで差し替えるため。"""
    d = os.environ.get("PAPER_MAKER_HOME")
    return pathlib.Path(d).expanduser() if d else pathlib.Path.home() / ".paper-maker"


def profile_path():
    return data_dir() / "profile.json"


def places_path():
    return data_dir() / "places.json"


def fares_path():
    return data_dir() / "fares.json"


def stations_path():
    return data_dir() / "stations.json"


def secrets_path():
    return data_dir() / "secrets.env"


def notes_dir():
    return data_dir() / "notes"


def log_path():
    return data_dir() / "paper-maker.log"
