"""AI の接続先。Gemini でも OpenAI でも、社内に立てた物でも差し替えられる。

鍵を配る側の都合で決めない。使う人が既に契約している所を使えるようにする。

  ~/.paper-maker/ai.json
  {
    "provider": "gemini",          gemini / openai / anthropic / custom
    "model": "gemini-2.5-flash",
    "keyName": "GEMINI_API_KEY",   secrets.env の中の名前
    "endpoint": "",                custom のときだけ。OpenAI 互換の /chat/completions
    "vision": true                 画像を読ませられるか
  }

鍵そのものは ai.json に書かない。~/.paper-maker/secrets.env に置く（0600）。
"""
import base64
import json
import mimetypes
import pathlib
import urllib.request

from . import paths

PRESETS = {
    "gemini": {
        "label": "Google Gemini",
        "model": "gemini-2.5-flash",
        "keyName": "GEMINI_API_KEY",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "style": "gemini",
        "vision": True,
        "where": "https://aistudio.google.com/app/apikey （無料枠あり）",
    },
    "openai": {
        "label": "OpenAI",
        "model": "gpt-4o-mini",
        "keyName": "OPENAI_API_KEY",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "style": "openai",
        "vision": True,
        "where": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "model": "claude-sonnet-4-5",
        "keyName": "ANTHROPIC_API_KEY",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "style": "anthropic",
        "vision": True,
        "where": "https://console.anthropic.com/settings/keys",
    },
    "claude-cli": {
        "label": "Claude Code（入っているCLIを使う）",
        "model": "",
        "keyName": "",
        "endpoint": "",
        "style": "cli",
        "command": "claude -p --allowedTools Read",
        "vision": True,
        "where": "鍵は要りません。claude コマンドが入っていて、ログイン済みならそのまま使えます",
    },
    "codex-cli": {
        "label": "Codex CLI（入っているCLIを使う）",
        "model": "",
        "keyName": "",
        "endpoint": "",
        "style": "cli",
        "command": "codex exec --skip-git-repo-check",
        "vision": True,
        "where": "鍵は要りません。codex コマンドが入っていて、ログイン済みならそのまま使えます",
    },
    "cli": {
        "label": "そのほかのCLI",
        "model": "",
        "keyName": "",
        "endpoint": "",
        "style": "cli",
        "command": "",
        "vision": False,
        "where": "文章を標準入力で受けて、答えを標準出力に返すコマンドなら何でも（gemini・ollama run・llm など）",
    },
    "custom": {
        "label": "そのほか（OpenAI 互換）",
        "model": "",
        "keyName": "AI_API_KEY",
        "endpoint": "",
        "style": "openai",
        "vision": True,
        "where": "社内に立てた物・Azure・OpenRouter・Ollama など。/chat/completions の形なら通ります",
    },
}


def config_path():
    return paths.data_dir() / "ai.json"


def load() -> dict:
    """設定。無ければ Gemini の既定。"""
    base = dict(PRESETS["gemini"])
    base["provider"] = "gemini"
    p = config_path()
    if p.exists():
        try:
            user = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            user = {}
        prov = user.get("provider") or "gemini"
        base = dict(PRESETS.get(prov, PRESETS["custom"]))
        base["provider"] = prov
        for k in ("model", "keyName", "endpoint", "vision", "command"):
            if user.get(k) not in (None, ""):
                base[k] = user[k]
    return base


def _absolute(cmd: str) -> str:
    """CLI の名前を、置いてある場所そのもので覚える。

    名前だけで覚えると、PATH の細い所（自動実行）から見つけられない。
    """
    import shlex
    import shutil
    parts = shlex.split(cmd or "")
    if not parts:
        return cmd
    full = shutil.which(parts[0])
    if not full:
        return cmd
    parts[0] = full
    return " ".join(shlex.quote(x) if " " in x else x for x in parts)


def save(cfg: dict):
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: cfg.get(k) for k in ("provider", "model", "keyName", "endpoint", "vision", "command") if cfg.get(k) not in (None, "")}
    if keep.get("command"):
        keep["command"] = _absolute(keep["command"])
    p.write_text(json.dumps(keep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def api_key(cfg: dict = None) -> str:
    """鍵。CLI 経由の接続先は鍵が要らないので、入っているかどうかで代用する。"""
    from . import bridge
    cfg = cfg or load()
    if (cfg.get("style") or "") == "cli":
        return "cli" if cli_available(cfg) else ""
    return bridge.read_secret(cfg.get("keyName") or "GEMINI_API_KEY")


def cli_available(cfg: dict = None) -> bool:
    import shutil
    cfg = cfg or load()
    cmd = (cfg.get("command") or "").split()
    return bool(cmd) and shutil.which(cmd[0]) is not None


def ready() -> bool:
    return bool(api_key())


# ---------- 呼び出し ----------

def _post(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ask(prompt: str, image_path=None, want_json=True, timeout=120, cfg: dict = None) -> str:
    """文章（と必要なら画像1枚）を渡して、返事の本文を返す。

    どの接続先でも同じ呼び方にする。ここだけが接続先の違いを知っている。
    """
    cfg = cfg or load()
    key = api_key(cfg)
    if not key:
        if (cfg.get("style") or "") == "cli":
            raise RuntimeError("%s が見つかりません。入れてからもう一度" % (cfg.get("command") or "").split()[0])
        raise RuntimeError("鍵がありません（~/.paper-maker/secrets.env の %s）" % cfg.get("keyName"))
    style = cfg.get("style") or PRESETS.get(cfg.get("provider"), PRESETS["custom"])["style"]
    model = cfg.get("model") or ""

    if style == "cli":
        return _ask_cli(cfg, prompt, image_path, timeout)

    endpoint = (cfg.get("endpoint") or "").format(model=model)
    if not endpoint:
        raise RuntimeError("接続先が設定されていません（~/.paper-maker/ai.json の endpoint）")

    img = None
    if image_path:
        p = pathlib.Path(image_path)
        img = (mimetypes.guess_type(str(p))[0] or "image/png",
               base64.b64encode(p.read_bytes()).decode("ascii"))

    if style == "gemini":
        parts = [{"text": prompt}]
        if img:
            parts.append({"inline_data": {"mime_type": img[0], "data": img[1]}})
        gen = {"temperature": 0}
        if want_json:
            gen["response_mime_type"] = "application/json"
        res = _post(endpoint + "?key=" + key, {"contents": [{"parts": parts}], "generationConfig": gen},
                    {"Content-Type": "application/json"}, timeout)
        return res["candidates"][0]["content"]["parts"][0]["text"]

    if style == "anthropic":
        content = [{"type": "text", "text": prompt}]
        if img:
            content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": img[0], "data": img[1]}})
        res = _post(endpoint, {"model": model, "max_tokens": 4096, "temperature": 0,
                               "messages": [{"role": "user", "content": content}]},
                    {"Content-Type": "application/json", "x-api-key": key,
                     "anthropic-version": "2023-06-01"}, timeout)
        return "".join(b.get("text", "") for b in res.get("content", []))

    # OpenAI 互換（Azure・OpenRouter・Ollama・社内に立てた物もここ）
    content = [{"type": "text", "text": prompt}]
    if img:
        content.append({"type": "image_url",
                        "image_url": {"url": "data:%s;base64,%s" % img}})
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "user", "content": content}]}
    if want_json:
        body["response_format"] = {"type": "json_object"}
    res = _post(endpoint, body, {"Content-Type": "application/json",
                                 "Authorization": "Bearer " + key}, timeout)
    return res["choices"][0]["message"]["content"]


def _ask_cli(cfg, prompt, image_path, timeout):
    """すでに入っている CLI に喋らせる。鍵を貼らなくていいのが利点。

    画像は「このファイルを読んで」と道を渡す。CLI 自身が開く。
    答えに前置きや後書きが付くことがあるので、拾うのは呼び出し側（ask_json）。
    """
    import shlex
    import subprocess
    cmd = shlex.split(cfg.get("command") or "")
    if not cmd:
        raise RuntimeError("実行するコマンドが設定されていません（~/.paper-maker/ai.json の command）")
    text = prompt
    if image_path:
        text = "次のファイルを読んでから答えてください: %s\n\n%s" % (image_path, prompt)
    try:
        r = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError("%s が見つかりません" % cmd[0])
    except subprocess.TimeoutExpired:
        raise RuntimeError("%s が %d 秒で返事をしませんでした" % (cmd[0], timeout))
    if r.returncode != 0:
        raise RuntimeError("%s が失敗しました: %s" % (cmd[0], (r.stderr or r.stdout).strip()[:160]))
    return r.stdout


def _pick_json(text: str):
    """前置きや後書きが混ざった返事から、JSON の所だけ取り出す。

    CLI は「補足」を付けてくることがある。素直に json.loads すると落ちる。
    """
    s = text.strip()
    if "```" in s:
        for part in s.split("```")[1::2]:
            body = part[4:] if part.startswith("json") else part
            try:
                return json.loads(body.strip())
            except ValueError:
                continue
    try:
        return json.loads(s)
    except ValueError:
        pass
    # 釣り合いの取れた最初の {...} を拾う
    start = s.find("{")
    while start != -1:
        depth, instr, esc = 0, False, False
        for i in range(start, len(s)):
            c = s[i]
            if esc:
                esc = False
                continue
            if c == "\\" and instr:
                esc = True
                continue
            if c == '"':
                instr = not instr
            elif not instr:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(s[start:i + 1])
                        except ValueError:
                            break
        start = s.find("{", start + 1)
    raise ValueError("JSON が見つかりませんでした")


def ask_json(prompt: str, image_path=None, timeout=120, cfg: dict = None):
    return _pick_json(ask(prompt, image_path, want_json=True, timeout=timeout, cfg=cfg))


def check() -> tuple:
    """繋がるか試す。(繋がったか, 一言)"""
    cfg = load()
    if not api_key(cfg):
        if (cfg.get("style") or "") == "cli":
            return False, "%s が見つかりません。入れてから試してください" % (cfg.get("command") or "?").split()[0]
        return False, "鍵がありません（%s を ~/.paper-maker/secrets.env に）" % cfg.get("keyName")
    try:
        r = ask_json('{"ok": true} とだけ返してください', timeout=30, cfg=cfg)
    except Exception as e:
        return False, "%s に繋がりませんでした: %s" % (cfg.get("label", cfg.get("provider")), e.__class__.__name__)
    what = cfg.get("model") or cfg.get("command") or ""
    return bool(r), "%s（%s）で読み書きできました" % (cfg.get("label", cfg.get("provider")), what)
