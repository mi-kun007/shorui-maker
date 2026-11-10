"""一度使ったメールアドレスを覚えて、次から選べるようにする。

毎回打ち直すのが面倒、というだけの話ではない。打ち間違えた宛先へ請求書が飛ぶのが怖い。
一度届いた所を残しておけば、次は選ぶだけで済む。

集めてくる先
  定期送付の台帳（recurring.json）
  取り込んだ契約書・見積の控え（knowledge.json）
  出来上がった書類の JSON（出力フォルダ）
  下書きを置いた履歴（このファイル自身）

**勝手に送らない。** ここは候補を出すだけで、送るのは人が押す。
"""
import json
import pathlib
import re

from . import paths

MAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def store():
    return paths.data_dir() / "addresses.json"


def load() -> dict:
    p = store()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"items": []}


def save(d):
    p = store()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remember(name: str, email: str, source: str = "") -> bool:
    """1件覚える。同じアドレスは増やさない。新しく覚えたら True。"""
    email = (email or "").strip()
    if not MAIL.fullmatch(email):
        return False
    d = load()
    for x in d["items"]:
        if x["email"].lower() == email.lower():
            if name and not x.get("name"):
                x["name"] = name
                save(d)
            return False
    d["items"].append({"name": (name or "").strip(), "email": email,
                       "source": source or "手で入れた"})
    save(d)
    return True


def _from_recurring():
    p = paths.data_dir() / "recurring.json"
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except ValueError:
        return []
    return [(r.get("client", ""), r.get("email", ""), "定期送付の台帳") for r in rows]


def _from_knowledge():
    from . import knowledge
    out = []
    for c in knowledge.load().get("clients", []):
        if c.get("email"):
            out.append((c.get("name", ""), c["email"], "取り込んだ書類"))
    for doc in knowledge.load().get("docs", []):
        cl = doc.get("client") or {}
        if cl.get("email"):
            out.append((cl.get("name", ""), cl["email"],
                        "取り込んだ%s" % (doc.get("kind") or "書類")))
    return out


def _from_documents():
    """出来上がった書類の JSON から拾う。"""
    from . import profile as prof_mod
    try:
        base = prof_mod.output_dir(prof_mod.load())
    except Exception:
        return []
    out = []
    if not base.exists():
        return out
    for p in list(base.rglob("*.json"))[:400]:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        doc = j.get("doc", j)
        if not isinstance(doc, dict):
            continue
        e = doc.get("clientEmail")
        if e:
            out.append((doc.get("clientName", ""), e, "作った書類"))
    return out


def _from_clients():
    p = paths.data_dir() / "clients.json"
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return []
    rows = rows.get("clients", rows) if isinstance(rows, dict) else rows
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("email"):
            out.append((r.get("name", ""), r["email"], "定期送付の宛先"))
    return out


def refresh() -> dict:
    """あちこちから集めて、控えに足す。足した数を返す。"""
    added = 0
    for getter in (_from_recurring, _from_knowledge, _from_documents, _from_clients):
        try:
            rows = getter()
        except Exception:
            continue
        for name, email, src in rows:
            if remember(name, email, src):
                added += 1
    return {"added": added, "total": len(load()["items"])}


def listing() -> list:
    """画面に出す形。名前のある物を先に。"""
    refresh()
    rows = load()["items"]
    rows.sort(key=lambda x: (not x.get("name"), x.get("name", ""), x["email"]))
    return rows


def forget(email: str) -> bool:
    d = load()
    before = len(d["items"])
    d["items"] = [x for x in d["items"] if x["email"].lower() != (email or "").lower()]
    save(d)
    return len(d["items"]) < before
