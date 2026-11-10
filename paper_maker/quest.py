"""導入の道順。7つ。1つ終わるごとに紙が1枚出る。

達成は自己申告にしない。設定と出力の実物を見て判定する。
「入れたつもり」で先に進むと、あとで空の書類が出て、その理由が分からなくなるため。
"""
import datetime as dt
import json

from . import paths, profile as prof_mod


def _state_path():
    return paths.data_dir() / "quest.json"


def load_state() -> dict:
    p = _state_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"skipped": [], "passed": []}


def save_state(st: dict):
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------- 判定 ----------

def _prof():
    try:
        return prof_mod.load()
    except FileNotFoundError:
        return None


def _issuer(prof):
    return (prof.get("profiles") or {}).get(prof.get("defaultIssuer", "corp"), {})


def _sample(*vals) -> bool:
    """見本の値がそのまま残っているか。

    残ったままでも欄は埋まっているので、前は「済」と出ていた。
    そのまま請求書を出すと「株式会社サンプル」と見本の口座で出る。
    埋まっているかではなく、その人の値かを見る。
    """
    from .autoset import _is_sample
    return _is_sample({str(i): v for i, v in enumerate(vals) if v})


def _q1(prof):
    p = _issuer(prof)
    if not (p.get("name") and p.get("address")):
        return False
    return not _sample(p.get("name"), p.get("address"), p.get("rep"))


def _q2(prof):
    b = _issuer(prof).get("bank")
    return bool(b) and not _sample(b)


SCAN_DAYS = 30


def _recent(prof):
    """直近の予定をまとめて1回だけ読む。

    1日ずつ聞くと、カレンダー.app では1日25秒かかった（実測 2026-08-19・この Mac）。
    30日ぶんを1日ずつ見に行くと道順の確認が返ってこない。
    """
    from . import calendars
    today = dt.date.today()
    by_day, _w = calendars.events_for_range(prof, today - dt.timedelta(days=SCAN_DAYS - 1), SCAN_DAYS)
    return by_day


def _q3(prof):
    """カレンダーが繋がっていて、予定が1件でも読めるか。"""
    if not (prof.get("calendar") or {}).get("sources"):
        return False, "カレンダーの取り口が未設定"
    by_day = _recent(prof)
    n = sum(len(v) for v in by_day.values())
    if n:
        return True, "直近%d日で %d 件の予定を読めた" % (SCAN_DAYS, n)
    return False, "取り口はあるが、直近%d日の予定が0件" % SCAN_DAYS


def _q4(prof):
    """現地と判定できた予定があるか。ここがこの道具の肝。"""
    from . import itinerary
    if not (prof.get("calendar") or {}).get("sources"):
        return False, "カレンダーが未設定"
    places = prof_mod.load_places()
    stations = prof_mod.load_stations()
    by_day = _recent(prof)
    for day in sorted(by_day, reverse=True):
        for e in by_day[day]:
            kind, station, _why = itinerary.classify(e, places, stations)
            if kind == "onsite" and station:
                return True, "%s に現地の予定を1件つかんだ" % day
    return False, "直近%d日に現地の予定が1件も無い（予定の場所欄に住所が入っていない）" % SCAN_DAYS


def _q_know(prof):
    """今までの書類を取り込んだか。持っていない人もいるので、飛ばせる作りにしてある。"""
    from . import knowledge
    d = knowledge.load()
    n = len(d.get("docs", []))
    if not n:
        return False, "まだ1件も取り込んでいません（無ければ飛ばして構いません）"
    return True, "%d 件（取引先 %d・品目 %d・条項 %d）" % (
        n, len(d.get("clients", [])), len(d.get("items", [])), len(d.get("clauses", [])))


def _q_ai(prof):
    """AI に繋がっているか。ここが済んでいないと、Suica のスクショは読めない。"""
    from . import ai
    cfg = ai.load()
    if not ai.api_key(cfg):
        return False, "%s の鍵がまだ（使わずに進むこともできます）" % cfg.get("label", cfg["provider"])
    st = load_state()
    if st.get("aiChecked") == cfg.get("provider"):
        return True, "%s（%s）に繋がりました" % (cfg.get("label"), cfg.get("model"))
    ok, msg = ai.check()
    if ok:
        st["aiChecked"] = cfg.get("provider")
        save_state(st)
    return ok, msg


def _q5(prof):
    """利用者が自分で運賃を登録したか。

    見本のまま、と、はじめから入れておいた主要区間は数えない。
    その人が自分の区間を1本でも入れたかを見る。
    """
    rows = prof_mod.load_fares().get("fares", [])
    mine = [r for r in rows if r.get("verified") and r.get("amount") is not None
            and not r.get("preset")
            and "見本" not in (r.get("source") or "")]
    return bool(mine), ("実額を %d 区間ぶん登録済み" % len(mine)) if mine else "実額の登録がまだ0件"


def _q6(prof):
    tr = prof.get("travel") or {}
    if not (tr.get("rates") and tr.get("role") in (tr.get("rates") or {})):
        return False, "役職と日当が噛み合っていない"
    out = prof_mod.output_dir(prof) / "規程" / "旅費規程.pdf"
    html = out.with_suffix(".html")
    if out.exists() or html.exists():
        return True, "旅費規程を出力済み"
    return False, "日当は入っている。あとは出すだけ"


def _q_mail(prof):
    """メールの下書きを作れる状態か。使わない人は飛ばして構わない。"""
    from . import bridge
    if not bridge.read_secret("GMAIL_APP_PASSWORD"):
        return False, "まだ繋いでいません（使わないなら飛ばして構いません）"
    who = bridge.read_secret("GMAIL_ADDRESS")
    return True, "%s の下書きに置けます" % (who or "登録済みのアドレス")


def _q_out(prof):
    """控えの置き場。既定のままでも動くが、決めた人は決めたことが分かるように。"""
    o = prof.get("output") or {}
    got = []
    # 既定のままは「決めた」に数えない。触っていないだけなので
    if (o.get("dir") or "").strip() not in ("", "~/Documents/書類メーカー"):
        got.append("書類")
    if (o.get("obsidianDir") or "").strip():
        got.append("Obsidian")
    if (o.get("sheetCsv") or "").strip():
        got.append("台帳")
    if not got:
        return False, "既定のまま（~/Documents/書類メーカー）。台帳を出すならここで決める"
    return True, "／".join(got)


def _q7(prof):
    """毎朝の書類作りが登録されているか。

    status() は「毎日の書類作り: … / 定期の見直し: …」の形で返す。
    前は先頭が「登録あり」かで見ていて、表示を2つに増やしたときに合わなくなった。
    ここで見るのは毎日のほうだけ。定期の見直しは入れなくても回る。
    """
    from . import schedule
    s = schedule.status()
    daily = s.split("/")[0]
    return "登録あり" in daily, s


def _q_base(prof):
    """拠点（現在地）。ここが決まっていないと行程の起点と終点が作れない。"""
    tr = prof.get("travel") or {}
    b = (tr.get("bases") or {}).get(tr.get("currentBase") or "")
    if not b:
        return False, "今いる拠点が選ばれていない"
    if not b.get("station"):
        return False, "拠点の最寄駅が空（行程の起点が作れない）"
    if _sample(b.get("address")):
        return False, "拠点が見本のまま（%s）。ここを直さないと全部この土地から出発します" % b.get("station")
    return True, "%s（最寄 %s）" % (b.get("label") or tr.get("currentBase"), b["station"])


def _q_note(prof):
    """営業メモ。直近14日で、商談の中身を1日ぶんでも書いたか。"""
    from . import notes
    today = dt.date.today()
    for i in range(14):
        d = today - dt.timedelta(days=i)
        r = notes.parse(d)
        if r.get("free") or any(v.get("話したこと") or v.get("本文") or v.get("次にやること")
                                for v in r.get("visits", {}).values()):
            return True, "%s のメモに中身がある" % d
    return False, "直近14日で、中身の入ったメモがまだ無い"

QUESTS = [
    {"id": 1, "title": "名乗りを決める",
     "shot": "q_name.png",
     "gain": "請求書と見積書の右上が埋まります。判子も一緒に出るので、印刷して押す手間が消えます。",
     "todo": "会社名（屋号）・代表者・住所を入れる",
     "reward": "見積書が1枚出せるようになる",
     "how": ("画面上の ⚙設定 → 発行名義に入れて「保存する」。\n"
             "個人名義でも書類を出すなら、個人のタブにも名前を入れておく。\n"
             "判子は文字から描いた印影が出ます。実物を白い紙に押して撮った写真も登録できます"
             "（同じ画面の「判子の画像」の枠に放り込む）。"),
     "check": lambda p: (_q1(p), "会社名と住所が入っている" if _q1(p)
                         else ("見本のままです。自分の名義に直してください"
                               if (_issuer(p).get("name") and _issuer(p).get("address"))
                               else "会社名か住所が空"))},

    {"id": 2, "title": "振込先を入れる",
     "shot": "q_bank.png",
     "gain": "請求書の下に振込先が載ります。「どこに振り込めば」の電話が来なくなります。",
     "todo": "銀行・支店・口座番号・名義を入れる",
     "reward": "請求書が出せるようになる",
     "how": ("⚙設定 → 発行名義 → 振込先口座。\n"
             "改行して 銀行（コード）／支店（番号）／普通 番号／カナ名義 の順に書くと、請求書がきれいに出ます。\n"
             "インボイスの登録番号があれば、同じ画面で入れておくと書類に載ります。"),
     "check": lambda p: (_q2(p), "振込先が入っている" if _q2(p)
                         else ("見本の口座のままです" if _issuer(p).get("bank") else "振込先が空"))},

    {"id": 3, "title": "今いる場所を決める",
     "shot": None,
     "gain": ("移動を「拠点 → 訪問先 → 拠点」で組み立てられるようになります。"
              "ここが空だと交通費が1円も出ません。"),
     "todo": "下の枠に、呼び名と住所を入れる。呼び名は土地の名前でいい",
     "reward": "行程の起点と終点が決まる",
     "how": ("住所を入れれば、出発に使う駅はこちらで調べます。\n"
             "町はずれで歩ける駅が無ければ、遠出に使う駅（市の代表駅）を起点にします。\n"
             "高速バスで出る人は、乗り場の名前を入れてください。駅でなくて構いません。\n"
             "\n"
             "拠点は何個でも入ります。行き来する土地のぶんだけ。\n"
             "**出張先へ移ったら、一覧から今いる所を選び直してください。**\n"
             "戻し忘れると、その日の移動が丸ごと別の土地から出発したことになります。\n"
             "\n"
             "ターミナル派はこちら。\n"
             "  paper-maker base                      今の一覧\n"
             "  paper-maker base add 呼び名 住所           足す\n"
             "  paper-maker base use 呼び名                今いる所を移す"),
     "check": _q_base},

    {"id": 4, "title": "カレンダーを繋ぐ",
     "shot": "q_cal.png",
     "gain": ("昨日の予定がそのまま報告書になります。場所欄に住所が入っている予定は「現地」と読まれて、"
              "移動・交通費・日当まで組み立てられます。"),
     "todo": "下の3つのどれか1つで繋ぐ",
     "reward": "昨日の予定が画面に並ぶ",
     "how": ("繋ぎ方は3通り。どれか1つでいい。\n"
             "\n"
             "① Mac のカレンダー.app（一番かんたん・Mac だけ）\n"
             "  普段 Mac のカレンダーを使っているなら、これだけで済みます。設定に足すのは1行。\n"
             '  {"type": "macos"}\n'
             "  Google のカレンダーを Mac のカレンダー.app に登録してあれば、それも一緒に読めます。\n"
             "\n"
             "② 書き出したファイルを置く（どのパソコンでも・鍵も回線も要らない）\n"
             "  Google カレンダー → 設定 → データのエクスポート → zip の中の .ics を取り出す。\n"
             "  iCloud は カレンダー.app でカレンダーを右クリック → 書き出す。\n"
             "  Outlook は ファイル → 名前を付けて保存 → iCalendar 形式。\n"
             "  取り出した .ics を ~/.paper-maker/calendar.ics に置くだけ。\n"
             '  {"type": "ics", "path": "calendar.ics"}\n'
             "  書き出した時点のコピーなので、予定を足したら書き出し直します。\n"
             "\n"
             "③ 限定公開の URL（置きっぱなしで最新が入る）\n"
             "  Google カレンダー → 設定 → 該当のカレンダー → 「iCal形式の限定公開URL」をコピー。\n"
             '  {"type": "url", "url": "https://…/basic.ics"}\n'
             "  この URL を知っている人は予定を全部見られます。人に渡さないこと。\n"
             "\n"
             "書く場所は ~/.paper-maker/profile.json の calendar.sources。いくつ並べても構いません。\n"
             "\n"
             "── 繋いだあと、予定の入れ方をひとつだけ ──\n"
             "訪問の予定は、場所欄に住所を入れておいてください（駅名だけでも構いません）。\n"
             "そこが空だと移動も交通費も作れません。\n"
             "オンラインの日は ZOOM とだけ書いておけば、移動なしとして扱います。\n"
             "時刻は移動時間ではなく、実際に会った時間で。\n"
             "\n"
             "確かめるのは paper-maker calendar --date 2026-08-18"),
     "check": _q3},

    {"id": 5, "title": "AI に繋ぐ",
     "shot": None,
     "gain": ("Suica のスクショを放り込むだけで運賃が入り、カレンダーの走り書きが報告書の文になります。"
              "使わなくても道具は動きますが、手で打つ量がかなり変わります。"),
     "todo": "接続先を選んで、繋がるか試す",
     "reward": "画像とメモを読ませられるようになる",
     "how": ("下の枠で選んで「試す」を押すだけ。うまくいけばその場で分かります。\n"
             "\n"
             "すでにパソコンに入れている CLI があれば、鍵は要りません。\n"
             "  Claude Code   claude コマンドが入っていてログイン済みなら、そのまま使えます\n"
             "  Codex CLI     codex コマンドが入っていれば同じく\n"
             "  そのほかCLI   文章を受けて答えを返すコマンドなら何でも（ollama run・llm など）\n"
             "\n"
             "鍵を使う場合は、すでに契約している所を選んでください。\n"
             "  Gemini    無料枠あり。持っていないならここが早い → https://aistudio.google.com/app/apikey\n"
             "  OpenAI    https://platform.openai.com/api-keys\n"
             "  Claude    https://console.anthropic.com/settings/keys\n"
             "  そのほか  OpenAI 互換なら何でも（Azure・OpenRouter・社内に立てた物）\n"
             "\n"
             "鍵は ~/.paper-maker/secrets.env に、自分だけ読める権限で入ります。設定ファイルには書きません。\n"
             "CLI 経由は返事に1分ほどかかることがあります。\n"
             "\n"
             "使わないなら「あとで」で飛ばせます。運賃は手で1件ずつ、メモは書いた文がそのまま入ります。"),
     "check": _q_ai},

    {"id": 6, "title": "運賃をまとめて入れる",
     "shot": "q_move.png",
     "gain": "「要確認」だった欄が金額で埋まります。精算書の実費計が、そのまま出せる数字になります。",
     "todo": "Suica や PASMO の利用履歴のスクショを撮って、下の枠に放り込む",
     "reward": "よく通る区間の金額が一度に埋まる",
     "how": ("主要な駅どうしの運賃は、はじめから44本入っています（東京・新宿・名古屋・新大阪・博多ほか）。\n"
             "自分の使う区間はここで足してください。入れ方は2つ。どちらも枠に画像を落とすだけです。\n"
             "\n"
             "① もう乗った分（Suica・PASMO の履歴）\n"
             "  iPhone なら Wallet → Suica → 利用履歴 を画面ごと撮ります。何枚でも。\n"
             "  同じ区間が2回以上、同じ額で出てきた分だけ確定にします。\n"
             "  1回しか出てこない区間は「確認待ち」。額が食い違う区間は取り込みません。\n"
             "\n"
             "② これから乗る分（乗換案内で調べる）\n"
             "  上の枠に出発と到着を入れて「乗換案内を開く」。別の窓で開きます。\n"
             "  いつも使っている乗換案内が別にあるなら、そちらで構いません。\n"
             "  出てきた画面を撮って、枠に落とすと候補が並びます。\n"
             "  どれで行ったかを押すと、その額が入ります。\n"
             "  選んだ乗り物は覚えるので、同じ区間は次から手が要りません。\n"
             "\n"
             "調べるのも、どれで行ったか決めるのも人です。こちらは読むだけ。\n"
             "乗換案内サイトの規約が、プログラムからの取得を禁じているためです。\n"
             "\n"
             "手で1件ずつ入れることもできます: paper-maker fare add 新宿 横浜 560\n"
             "バスは公開データからまとめて取れます: paper-maker fare gtfs --pref <県名>"),
     "check": _q5},

    {"id": 7, "title": "商談の中身を書く",
     "shot": "q_visits.png",
     "gain": "報告書の右の列に、誰と何を話して次に何をするかが入ります。会社に上げられる紙になります。",
     "todo": "その日のメモを作って、話したこと・次にやることを1件ぶん埋める",
     "reward": "営業報告書の右の列に、商談の中身が入る",
     "how": ("paper-maker note でその日の雛形ができます（訪問先が見出しで並びます）。\n"
             "埋めたら paper-maker daily --date 日付。\n"
             "「## 所感」に書いた分は、報告書の下の欄に入ります。\n"
             "\n"
             "メモを別に書くのが面倒なら、カレンダーの予定の説明欄に走り書きしておくだけでも構いません。\n"
             "翌朝それを読んで、相手・話したこと・次にやること に振り分けます。\n"
             "書かなかった欄は空のまま出します。こちらで作文はしません。"),
     "check": _q_note},

    {"id": 8, "title": "今までの書類を取り込む",
     "shot": None,
     "gain": ("去年の契約書を開いて写す作業が消えます。取引先の住所は宛名だけで埋まり、"
              "契約書の本文は前と同じ条項が並んだ状態から始まります。"),
     "todo": "手元の契約書か、前に出した見積・請求を下の枠に放り込む",
     "reward": "取引先・単価の履歴・条項が控えに入る",
     "how": ("読み取ると3つに分かれます。\n"
             "  取引先   … 宛名だけ書けば住所を補います\n"
             "  品目と単価 … 前はいくらだったかが、新しい順に見られます\n"
             "  契約の条項 … 本文が空の契約書に、控えた条項を並べて差し込みます\n"
             "\n"
             "入れる前に、何が読み取れたかを見せます。良ければ「入れる」を押してください。\n"
             "単価は前の額であって、次もその額とは限りません。そこは人が決めます。\n"
             "\n"
             "原本は ~/.paper-maker/knowledge/ に控えます。外には出しません。\n"
             "ターミナル派は paper-maker learn <ファイル…> --apply。\n"
             "見るのは paper-maker knowledge clients / items / clauses。\n"
             "\n"
             "手元に無ければ「あとで」で飛ばして構いません。"),
     "check": _q_know},
    {"id": 9, "title": "日当を決めて規程を出す",
     "shot": "q_rules.png",
     "gain": "税理士に「旅費規程はありますか」と聞かれた時に、その場で出せる紙が1枚できます。",
     "todo": "役職ごとの日当（日帰り・宿泊）を決めて、規程を出す",
     "reward": "旅費規程が1枚出る",
     "how": ("profile.json の travel.rates を直して paper-maker rules。\n"
             "宿泊費の上限・精算の期限・施行日も同じ travel の中にあります。\n"
             "たたき台なので、施行する前に税理士に見せてください。紙にもそう書いてあります。"),
     "check": _q6},

    {"id": 10, "title": "毎朝に任せる",
     "shot": "q_files.png",
     "gain": "1時間おきに予定を読み直して、変わっていたらその日の書類を作り直します。翌朝まで待ちません。",
     "todo": "自動実行を登録する",
     "reward": "明日から、何もしなくても出ている",
     "how": ("paper-maker schedule install。これで2つ入ります。\n"
             "  朝6時   前日ぶんを締める（時刻を変えるなら --hour 8 --minute 30）\n"
             "  1時間ごと 予定を読み直して、変わっていたらその日の書類を作り直す\n"
             "\n"
             "午前に商談を1件足したら、次の回で今日の報告書に入っています。\n"
             "予定が前のままの日は触りません。同じ紙を1時間おきに焼き直さないように。\n"
             "間隔を変えるなら --every 30、日中の見直しが要らなければ --every 0。\n"
             "止めるのは paper-maker schedule remove"),
     "check": _q7},

    {"id": 11, "title": "控えの置き場を決める",
     "shot": None,
     "gain": ("出来た書類の置き場と、1日1行の台帳の置き場を決めます。"
              "月末に「先月いくら動いたか」を見るとき、台帳を開けば済みます。"),
     "todo": "下の枠に置き場を入れる。要らない欄は空のままで構いません",
     "reward": "書類が散らからなくなる",
     "how": ("3つあります。要るものだけ入れてください。\n"
             "\n"
             "  書類の置き場   PDF と HTML が日付ごとに入ります（既定 ~/Documents/書類メーカー）\n"
             "  Obsidian     同じ内容の .md を保管庫へ。日誌に混ぜたい人向け\n"
             "  台帳         1日1行の CSV。Excel でも Google スプレッドシートでも開けます\n"
             "\n"
             "台帳は追記ではなく差し替えです。同じ日を作り直しても行は増えません。\n"
             "Google スプレッドシートに載せるなら、その CSV を取り込んでください。\n"
             "\n"
             "入っているのは 日付 / 訪問件数 / 交通費 / 日当 / 合計 / 要確認 / 行き先 / 書類の場所。"),
     "check": _q_out},

    {"id": 12, "title": "メールで送れるようにする",
     "shot": None,
     "gain": ("PDFを付けたままGmailの下書きに入ります。保存して、Gmailを開いて、添付して、の3手が1手になります。"
              "使わなくても書類は出せます。"),
     "todo": "Gmailのアプリパスワードを1つ発行して、⚙設定のメール欄に貼る",
     "reward": "書類メーカーから下書きが作れる",
     "how": ("**送信はしません。下書きに置くだけです。** 中身を見てから、自分で送ってください。\n"
             "\n"
             "手順は3つ。\n"
             "  1. Googleアカウントで2段階認証を有効にする（すでに有効ならそのまま）\n"
             "  2. https://myaccount.google.com/apppasswords でアプリパスワードを発行する\n"
             "     アプリ名は何でも構いません（書類メーカー、など）。16桁が1回だけ出ます\n"
             "  3. 書類の画面の「Gmail下書き」→ 下のメール設定に、アドレスと16桁を貼って「保存して試す」\n"
             "\n"
             "貼った16桁は ~/.paper-maker/secrets.env に、本人だけ読める権限で入ります。\n"
             "設定ファイルにも書類にも出ません。やめる時は、Googleの画面でそのアプリパスワードを削除します。\n"
             "\n"
             "会社のGoogle Workspaceで管理者がアプリパスワードを禁じている場合は使えません。\n"
             "その時は今までどおり「Gmailで下書きを開く」で、PDFは手で添付してください。"),
     "check": _q_mail},
]


def evaluate(recheck: bool = False) -> dict:
    """全クエストの今の状態。GUI と CLI が同じこれを見る。

    毎回まっさらな目で見る（予定を直したのに反映されない、を作らないため）。
    ただし1回の評価の中では、カレンダーは1度しか読まない。
    """
    from . import calendars
    calendars.clear_cache()
    prof = _prof()
    st = load_state()
    skipped = set(st.get("skipped", []))
    passed = {int(x) for x in st.get("passed", [])}
    items, current, newly = [], None, False
    for q in QUESTS:
        if prof is None:
            done, note = False, "まだ何も入っていません。下の枠に去年の請求書を1枚落とすか、⚙設定から入れてください"
        elif q["id"] in passed and not recheck:
            # 一度できた事は、あとから無くならない。毎回カレンダーを読み直すと重い
            done, note = True, "済んだ分（--recheck で見直す）"
        else:
            r = q["check"](prof)
            done, note = r if isinstance(r, tuple) else (bool(r), "")
            if done and q["id"] not in passed:
                passed.add(q["id"])
                newly = True
        item = {k: q.get(k) for k in ("id", "title", "todo", "reward", "how", "shot", "gain")}
        item["done"] = done
        item["note"] = note
        item["skipped"] = q["id"] in skipped and not done
        items.append(item)
        if current is None and not done and not item["skipped"]:
            current = q["id"]
    if newly:
        st["passed"] = sorted(passed)
        save_state(st)
    done_n = sum(1 for i in items if i["done"])
    return {
        "quests": items,
        "current": current,
        "done": done_n,
        "total": len(items),
        "finished": done_n == len(items),
        "hasProfile": prof is not None,
    }


def skip(qid: int):
    st = load_state()
    s = set(st.get("skipped", []))
    s.add(int(qid))
    st["skipped"] = sorted(s)
    save_state(st)


def unskip(qid: int):
    st = load_state()
    st["skipped"] = [i for i in st.get("skipped", []) if i != int(qid)]
    save_state(st)
