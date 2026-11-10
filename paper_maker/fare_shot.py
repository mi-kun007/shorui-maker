"""経路検索の画面を撮った写真から、行き方と運賃を読む。

自分のブラウザで調べて、出てきた画面をそのまま枠に落とす。
撮るのも、どれで行ったか決めるのも人。こちらは読むだけ。

**読んだ額をそのまま確定にしない。** 候補として並べて、押させる。
写真の読み違いは起きる。3,988 を 3,986 と読んだ紙が、税理士の所へ行くのが一番まずい。
"""
from . import ai

PROMPT = """これは乗換案内の検索結果を撮った画面です。出ている案を全部、次の JSON で返してください。

決まり
- **画面に写っている数字だけ。** 読めない所は 0 にする。足さない
- 運賃は合計の額（IC優先などの表示があればその額）
- 乗る物は、書いてある路線名や便名をそのまま
- 所要は分に直す（1時間30分 なら 90）

{{
  "from": "出発の駅・バス停",
  "to": "到着の駅・バス停",
  "routes": [
    {{"amount": 0, "minutes": 0, "lines": ["路線名"], "note": "乗換1回など"}}
  ]
}}"""


def read(path, timeout=180) -> dict:
    got = ai.ask_json(PROMPT, image_path=str(path), timeout=timeout)
    if not isinstance(got, dict):
        return {"from": "", "to": "", "routes": []}
    out = {"from": str(got.get("from") or "").strip(),
           "to": str(got.get("to") or "").strip(), "routes": []}
    for r in (got.get("routes") or []):
        try:
            amount = int(r.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            continue
        try:
            minutes = int(r.get("minutes") or 0)
        except (TypeError, ValueError):
            minutes = 0
        lines = [str(x).strip() for x in (r.get("lines") or []) if str(x).strip()]
        out["routes"].append({"amount": amount, "minutes": minutes,
                              "lines": lines, "note": str(r.get("note") or "")})
    return out
