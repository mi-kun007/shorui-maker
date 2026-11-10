"""カレンダーのメモ欄から、報告書の欄を埋める。

営業マンが移動中に打つのは、こんな文字。
    サカイ商店 山田課長。現場写真をLINEで送りたい。今は紙とFAX。予算30万くらい。来週サンプル送る

これを「どこで・誰と・何を話して・次に何をするか」に振り分ける。
**書いていないことは足さない。** 予定の件名しか無い日は、件名だけの報告書が出る。
AIが使えないときは、メモをそのまま「話したこと」に入れる。それでも報告書にはなる。
"""
import json
import re
import urllib.request

FIELDS = ("相手", "話したこと", "次にやること")

PROMPT = """営業の報告書を作ります。1件の訪問について、下の情報を決まった欄に振り分けてください。

件名: {title}
場所: {location}
時刻: {time}
本人が書いたメモ:
\"\"\"
{note}
\"\"\"

決まり
- **メモに書いていないことは絶対に足さない。** 想像で補わない
- 書いていない欄は空文字にする
- 「相手」は会社名・部署・人名。メモか件名から拾えた分だけ
- 「話したこと」は要件と相手の反応。です・ます調で1〜3文。箇条書きにしない
- 「次にやること」は次の行動と期限。書いていなければ空
- 誇張しない。「〜と考えられます」「〜が期待されます」のような推測は入れない

JSONだけ返す: {{"相手": "", "話したこと": "", "次にやること": ""}}"""


def _clean(note: str) -> str:
    """カレンダーの説明欄には、会議URLや定型の案内が混ざる。営業の中身だけ残す。"""
    if not note:
        return ""
    drop = re.compile(
        r"(https?://\S+)|(zoom\.us)|(meet\.google)|(teams\.microsoft)|"
        r"(ミーティング ?ID)|(パスコード)|(電話で参加)|(ダイヤル)|"
        r"(ミーティングに参加)|(会議に参加)|(ワンタップ)|(Join .*meeting)|"
        r"(このメールは)|(自動送信)|(カレンダーの招待)|(参加者:)|(主催者:)|"
        r"^(担当|参加費|定員)\s*[:：]")
    lines = []
    for line in note.splitlines():
        t = line.strip()
        if not t or drop.search(t):
            continue
        lines.append(t)
    return "\n".join(lines).strip()


def by_hand(ev: dict) -> dict:
    """AI を使わない振り分け。メモの中身をそのまま置く。

    行頭に「相手:」「次:」のように書いてあれば、そこだけ拾う。
    """
    note = _clean(ev.get("note") or "")
    out = {f: "" for f in FIELDS}
    rest = []
    for line in note.splitlines():
        m = re.match(r"^\s*(相手|先方|担当|話したこと|内容|次|次にやること|next)\s*[:：]\s*(.*)$", line)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if k in ("相手", "先方", "担当"):
                out["相手"] = v
            elif k in ("次", "次にやること", "next"):
                out["次にやること"] = v
            else:
                out["話したこと"] = v
        elif line.strip():
            rest.append(line.strip())
    if rest and not out["話したこと"]:
        out["話したこと"] = "\n".join(rest)
    elif rest:
        out["話したこと"] = (out["話したこと"] + "\n" + "\n".join(rest)).strip()
    if not out["相手"]:
        out["相手"] = who_from_title(ev.get("title", ""))
    return out


_NOT_WHO = {"弊社", "当社", "本社", "自社", "出社", "入社", "帰社", "退社", "御社", "貴社", "会社",
            "神社", "結社", "商社", "皆さん", "みなさん", "皆様", "みな様", "お客様", "お客さん", "各位"}
_SUFFIX = r"(株式会社|有限会社|合同会社|社|会社|商店|工房|事務所|様|さん)"
_PREFIX = r"(株式会社|有限会社|合同会社)"


def who_from_title(title: str) -> str:
    """件名から「○○社」「○○様」を拾う程度。無ければ空。

    括弧の中も1語として見る。「A社 打合せ（山田様）」は「A社 山田様」。
    前は括弧ごと1語に見ていて、「打合せ（山田様」と閉じの欠けた相手が紙に出ていた。
    「株式会社ABC」「（株）サカイ」のように前に付く形も拾う。「神社」「皆さん」は相手にしない。
    """
    t = title or ""
    t = re.sub(r"[（(]\s*株\s*[）)]\s*", "株式会社", t)
    t = re.sub(r"[（(]\s*有\s*[）)]\s*", "有限会社", t)
    toks = re.split(r"[\s　（）()「」【】\[\]／/・、,:：]+", t)
    who = []
    for w in toks:
        if not w or w in _NOT_WHO:
            continue
        m = re.search(_SUFFIX + "$", w)
        if m and len(w) > len(m.group(1)):
            who.append(w)
            continue
        m = re.match(_PREFIX, w)
        if m and len(w) > len(m.group(1)):
            who.append(w)
    return " ".join(dict.fromkeys(who))


def by_ai(ev: dict, api_key: str = "", timeout=60):
    """書いてある文を欄に振り分けてもらう。無から作らせない。"""
    note = _clean(ev.get("note") or "")
    if not note:
        return None
    from . import ai
    t = "終日" if ev.get("all_day") else "%s–%s" % (ev.get("start", ""), ev.get("end", ""))
    try:
        obj = ai.ask_json(PROMPT.format(
            title=ev.get("title", ""), location=ev.get("location", ""), time=t, note=note), timeout=timeout)
    except Exception:
        return None
    return {f: str(obj.get(f) or "").strip() for f in FIELDS}


def fill(events, api_key: str = "", use_ai: bool = True):
    """予定に memo を付ける。既に手書きのメモが付いている物は触らない。

    手で書いた物のほうが強い。カレンダーから起こした分で上書きしない。
    """
    filled = 0
    for e in events:
        if e.get("memo"):
            continue
        note = _clean(e.get("note") or "")
        if not note:
            continue
        got = None
        if use_ai and api_key:
            try:
                got = by_ai(e, api_key)
            except Exception:
                got = None
        if not got or not any(got.values()):
            got = by_hand(e)
        if any(got.values()):
            got["出所"] = "カレンダーのメモ"
            e["memo"] = got
            filled += 1
    return filled
