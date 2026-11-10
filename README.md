# 書類メーカー 配布版

一人会社の見積・請求・領収・契約・出張報告を1枚の画面で作る道具に、
**カレンダーから営業報告書と出張精算を毎朝つくる**機能と、**旅費規程書**を足したもの。

月末に手帳とカレンダーを行ったり来たりして交通費を表に写す。あれが無くなる。
前日の分は朝6時にPDFで出ている。日報も同じ。書いていないのは怠けているからじゃなく、
カレンダーに全部あるのに二度打ちだから。二度打ちを消しただけ。

依存は Python 3.9 以上だけ。PDF にするときは手元の Chrome か Edge を借りる。
データはぜんぶ自分のパソコンの `~/.paper-maker/` に置く。外に送らない。

## 入れる

macOS / Linux
```bash
bash install.sh
paper-maker init
paper-maker doctor
```

Windows（PowerShell）
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
paper-maker init
paper-maker doctor
```

インストールが終わると、**デスクトップに「書類メーカー」のアイコンができる**。
押すとブラウザで画面が開いて、そこから会社名も振込先も入れられる。ターミナルはもう要らない。

```bash
paper-maker desktop          # アイコンを置き直す
paper-maker desktop remove   # 消す
```

ターミナルで最初に済ませたい人は `paper-maker init`。会社名・住所・振込先・日当・拠点の駅・
カレンダーの場所を順に聞かれる。あとから `~/.paper-maker/profile.json` を直接直してもいい。

## はじめの道順

`paper-maker app` を開くと、画面の右下に道順が出る。10。

**ひとつずつ埋めたくない人へ。** 道順1の枠に、去年の請求書を1枚放り込んでください。
名乗り・代表者・住所・電話・登録番号・振込先を、そこから写します。
カレンダーと AI は、そのパソコンに何が入っているかを見て決めます。
埋まるのは10箇所のうち、道順で言えば1〜5。40秒ほど。

ターミナル派はこちら。

```bash
paper-maker auto ~/Documents/請求書_2026-05.pdf          # 何を入れるか見るだけ
paper-maker auto ~/Documents/請求書_2026-05.pdf --apply  # 入れる
```

書く前に必ず一覧を出します。上書きになる欄は今の値も並べます。
日当だけは入れません。いくらにするかは人が決める所なので。1つ終わるごとに紙が1枚出る。

名乗り → 振込先 → 拠点 → カレンダー → **AIに繋ぐ** → 運賃の取込 → 商談の中身 → **今までの書類を取り込む** → 日当と規程 → 毎朝に任せる

「← 前」「次 →」で行き来できる。飛ばした先から現在地に戻る導線も出る。
全部終わると数秒で消える（残しておきたければ何も押さなくていい／すぐ消すなら「いま閉じる」）。

5番目の「AIに繋ぐ」で接続先を選んで「試す」を押す。その場で繋がるか分かる。
ここを飛ばすと、次の「Suica のスクショを放り込む」が読めないので順番はこうしてある。
使わずに進むこともできる（運賃は手で、メモは書いた文がそのまま入る）。

道順には毎回、**そこを設定すると何が出るようになるか**を絵で出す（`app/tutorial/*.png`）。
見本の会社で実際に出力した紙を切り出した物。押すと大きくなる。

済んだかどうかは自己申告ではなく、設定と出力の実物を見て判定している。
「入れたつもり」で先に進むと、あとで空の書類が出て、その理由が分からなくなるため。

帯をクリックすると畳める。ターミナル派は次で同じ物が見える。

```bash
paper-maker quest
paper-maker quest --all
```

5番目の「予定の書き方」だけは飛ばさないでほしい。
場所欄が空の予定からは、移動も交通費も作れない。1件だけ試せば、あとは同じ要領で回る。

## カレンダーを繋ぐ

ICS を渡す。Google カレンダーなら「設定 → 該当カレンダー → iCal 形式の限定公開 URL」。
Outlook・iCloud は書き出した `.ics` ファイルでも、URL でもいい。

```json
"calendar": {
  "sources": [
    {"type": "url", "url": "https://calendar.google.com/calendar/ical/.../basic.ics", "name": "仕事"}
  ]
}
```

Mac ならカレンダー.app を直接読む取り口もある（`{"type": "macos"}`）。

繋がったか見る：
```bash
paper-maker calendar --date 2026-08-13
```

## 毎朝つくる

```bash
paper-maker daily                 # 前日分
paper-maker daily --date 2026-08-13
```

出るもの（`~/Documents/書類メーカー/YYYY/MM/`）
- `営業報告書_YYYY-MM-DD.pdf` … 面談・訪問、移動と運賃、所感、明日の予定
- `出張精算_YYYY-MM-DD.pdf` … 現地の予定があった日だけ。区間・運賃・日当
- 同名の `.json`（あとから GUI で開いて直せる）
- `profile.json` の `output.obsidianDir` を入れておくと、同じ内容の `.md` も置く

## 入れたあと、勝手に走らせる

一度登録すれば、あとはパソコンが起きていれば勝手に動く。Mac は launchd、Windows はタスクスケジューラ、Linux は cron に入る。

```bash
paper-maker schedule install              # 朝6時＋1時間ごと（既定）
paper-maker schedule install --every 30   # 30分ごとにする
paper-maker schedule install --every 0    # 朝の回だけにする
paper-maker schedule status
paper-maker schedule remove
```

入るのは2つ。役割が違う。

**朝6時**（`daily`）が前日ぶんを締める。

**1時間ごと**（`sync`）が今日を追いかける。予定を読み直して、前と比べて変わっていたらその日の書類を作り直す。午前に商談を1件足したら、次の回で今日の報告書に入っている。翌朝まで待たない。

変わっていない日は触らない。予定が同じなら PDF も焼き直さない。毎時走るので、ここで毎回 Chrome を立ち上げると邪魔になる。

比べているのは予定の指紋（sha256 の頭16桁）。時刻・題名・場所・メモのどれかが動けば別の値になる。場所を後から書き足した日も作り直す（交通費が変わるので）。`sync.json` に残るのはその16桁だけで、予定名も場所も書かない。

ログ（`~/.paper-maker/paper-maker.log`）は日付と件数だけ。

## 商談の中身を書く

```bash
paper-maker note              # 今日の雛形を作って開く
paper-maker note --date 2026-08-13
```

その日の訪問先が見出しで並んだメモができる。手ぶらのメモ帳を開くより、名前が並んでいるほうが書ける。

```markdown
## 10:00 サカイ商店 打合せ
話したこと: 現場の写真をLINEで送る運用にしたい。今は紙とFAXで、事務が毎晩1時間打ち直している
次にやること: 9/2までに画面のたたき台

## 所感
決まりそう
```

「話したこと」「次にやること」は報告書の右の列に、「## 所感」は下の欄に入る。
書かなかった欄は空のまま出す。AI で埋めたりはしない。

見出しを付けずにそのまま書いても、全部が所感として入る。

### カレンダーのメモから起こす

メモを別に書くのが面倒なら、**カレンダーの予定の説明欄に走り書きしておけばいい**。

```
山田課長。現場写真をLINEで送りたい。今は紙とFAXで事務が毎晩1時間打ち直してる。
予算30万くらい。来週サンプル送る
```

これが翌朝、報告書の欄に振り分けられる。

```
相手      サカイ商店 山田課長
話したこと 現場写真をLINEで送りたいというご要望がありました。現在は紙とFAXで事務の方が
          毎晩1時間かけて打ち直しているとのことです。予算は30万円程度と伺いました。
次        来週サンプルを送ります。
```

Zoom の招待URLやミーティングIDは落とす。**書いていないことは足さない。**
説明欄が空の予定は、件名だけの行になる。作文はしない。

鍵が無いときは、走り書きがそのまま「話したこと」に入る。それでも報告書にはなる。
`profile.json` の `report.useAi` を false にすれば、鍵があっても整形しない。

`paper-maker note` で手で書いた分のほうが強い。カレンダーから起こした分で上書きしない。

## 運賃

運賃は自分で登録した実額だけを使う。登録が無い区間は「要確認」と出て、勝手に金額を入れない。

1区間ずつ手で入れるのは続かないので、履歴からまとめて入れられる。

```bash
paper-maker fare import ~/Desktop/suica*.jpg        # 何が入るか見るだけ
paper-maker fare import ~/Desktop/suica*.jpg --apply
paper-maker fare add 新宿 横浜 560 --transport 鉄道   # 1件だけ入れる
paper-maker fare list
```

ターミナルを開かずに、**画面に放り込むこともできる**。`paper-maker app` を開くと右下の道順に枠が出るので、
そこへスクショをドラッグする（枠を押してファイルを選んでもいい）。読んだ中身を見せるので、
良ければ「入れる」を押す。1枚10秒くらい。テキストや CSV も同じ枠に落とせる。

iPhone なら Wallet → Suica → 利用履歴 を画面ごと撮る。何枚でも渡せる。
画像を読むには自分の Gemini の鍵が要る（`~/.paper-maker/secrets.env` に `GEMINI_API_KEY=...`）。
鍵を使いたくなければ、履歴をテキストで書いたファイルでもいい。

```
2026-08-15  鉄道  阿佐ケ谷 → 東京  341
2026-08-12  バス  日東交通  1600
```

読み取った物をそのまま信じない作りにしてある。

- 同じ区間が2回以上、同じ額で出てきた分だけ確定にする
- 1回しか出てこない区間は「確認待ち」。書類には使わない
- 額が食い違う区間は取り込まず、両方の額を見せる
- 同じ駅どうしの区間（読み間違い）は外す

### 自分で調べさせる

```bash
paper-maker fare auto              # 未登録の区間を調べる（何が分かったか見るだけ）
paper-maker fare auto --apply
paper-maker fare auto --no-ai      # オープンデータだけ使う
```

出どころで扱いが変わる。

| 出どころ | 扱い | 範囲 |
|---|---|---|
| 公共交通オープンデータセンター | **実額。そのまま使う** | 都営交通は鍵なしで引ける。[開発者登録](https://developer.odpt.org/)して `ODPT_TOKEN` を `secrets.env` に入れると、東京メトロ・私鉄各社も引ける |
| Gemini | **候補どまり。書類には使わない** | どこでも答えるが、いつ時点の運賃かは保証されない |
| どちらも駄目 | 未登録のまま | 実際に乗ったときの額を `fare add` で |

JR は公開データが無いので候補どまりになる。JR東日本は 2026年3月14日に運賃を改定しているので、
古い数字を掴んで税務書類に載せないよう、候補は人が確定させるまで使わない。

### バスは公開データから取れる

```bash
paper-maker fare gtfs --pref <県名>            # その県のフィードを見る
paper-maker fare gtfs --word 日東            # 事業者名で探す
paper-maker fare gtfs --pref <県名> --only 1 --stop <停留所名> --apply
```

出どころは[GTFSデータリポジトリ](https://gtfs-data.jp/)。鍵も登録も要らない。
2026年8月の時点で 548フィード・407事業体。ほとんどが CC BY 4.0 か CC0。

停留所どうしの実運賃がそのまま入っている。ただし1つのフィードに1万区間近くあるので、
`--stop` で自分が使う停留所に絞るか、`--limit` で頭を打つ。

CC BY は出典の表示が条件なので、運賃表の「根拠」に事業者名とライセンスを残してある。
`paper-maker fare list` で見える。

鉄道は GTFS で出している事業者が少ない（弘南鉄道・山形鉄道・富山地方鉄道など18件）。
JR は無い。

### 今の額かどうか

運賃は変わる。変わること自体は防げないので、**古いことが分かる**ようにしてある。

```bash
paper-maker fare stale
```

```
古いかもしれない（1 区間）
  東京駅 → 渋谷駅  200円  2026-03-14 の運賃改定（JR東日本）より前に確かめた額
      確かめた日 2024-06-01 / id=tokyo_shibuya
```

古い額のまま書類を作ると、移動の欄と精算書の備考に「※改定より前に確かめた額」と出る。

一番新しい運賃は、**実際に払った額**。改定されても、次に乗った瞬間に正しい額が入る。
月に一度 Suica の履歴を撮って `fare import --apply` を回すのが、どのAPIより確か。

改定日は `~/.paper-maker/fare_revisions.json` に足せる。

```json
{"revisions": [{"date": "2027-04-01", "who": "○○鉄道", "note": "運賃改定"}]}
```

```bash
paper-maker fare list --ids                    # 候補と id を見る
paper-maker fare confirm tokyo_yokohama 528 --source "Suica利用履歴"
```

### 場所と駅の結びつけ

場所欄の住所をどの駅に寄せるかは `~/.paper-maker/places.json`。
そこに無くても、**運賃表に入っている駅名なら拾う**。履歴を取り込むほど賢くなる。
「ZOOM」「オンライン」などが入っている予定は移動なしとして扱う。

## 旅費規程

```bash
paper-maker rules
```

`profile.json` の日当表・宿泊費の上限・精算期限・施行日を差し込んで、`規程/旅費規程.pdf` を出す。
たたき台なので、施行前に税理士に見せること。紙にもそう書いてある。

## 見積・請求・領収・契約（GUI）

```bash
paper-maker app
```

ブラウザで `http://127.0.0.1:8797/` が開く。名義・口座・印影は `profile.json` から入る。

### 判子は画像でも押せる

⚙設定 → 発行名義 → 判子の画像に、**実物を白い紙に押して撮った写真**を放り込む。
白い所は自動で透かすので、書類の文字を隠さない。大きさは mm で調整できる。

画像を入れなければ、今までどおり枠と文字で描いた印影が出る。
そのポートを別の物が使っていたら、次の空きに立つ（`/api/hello` で自分かどうか見分けている）。
AI を使う機能（チャット入力・Suica履歴の読み取り・カレンダーのメモの振り分け）を使うときだけ鍵が要る。

JSON から直接 PDF：
```bash
paper-maker doc 見積.json 見積.pdf
```

## AI の接続先

Gemini でも OpenAI でも Claude でも、社内に立てた物でもいい。既に契約している所を使ってほしい。

```bash
paper-maker ai list                       # 選べる先と、今どこに繋がっているか
paper-maker ai set openai --model gpt-4o-mini
paper-maker ai key sk-…                   # 鍵を入れる（secrets.env に 0600 で入る）
paper-maker ai check                      # 本当に繋がるか試す
```

| 選べる先 | 既定のモデル | 鍵の名前 |
|---|---|---|
| gemini | gemini-2.5-flash | `GEMINI_API_KEY` |
| openai | gpt-4o-mini | `OPENAI_API_KEY` |
| anthropic | claude-sonnet-4-5 | `ANTHROPIC_API_KEY` |
| custom | 自分で指定 | `AI_API_KEY` |
| claude-cli | — | **鍵は要らない**。`claude` コマンドが入っていれば |
| codex-cli | — | **鍵は要らない**。`codex` コマンドが入っていれば |
| cli | 自分で指定 | **鍵は要らない**。任意のコマンド（`ollama run llama3` など） |

すでにパソコンに入れている CLI があれば、鍵を1つも貼らずに使える。
**Claude Max や ChatGPT Plus を払っているなら、その月額の中で動く**（API の従量課金は発生しない）。
CLI 側で一度ログインしておくこと。`claude` は「Claude account with subscription」を、`codex` は ChatGPT アカウントを選ぶ。

```bash
paper-maker ai set claude-cli
paper-maker ai check
```

文章を標準入力で受けて答えを標準出力に返すコマンドなら何でも通る。

```bash
paper-maker ai set cli --command "ollama run llama3"
```

CLI 経由は返事に1分ほどかかることがある。

`custom` は OpenAI 互換（`/v1/chat/completions`）なら通る。Azure・OpenRouter・Ollama・社内の物など。

```bash
paper-maker ai set custom --model llama3 \
  --endpoint http://127.0.0.1:11434/v1/chat/completions --key-name LOCAL_KEY
```

**鍵は `ai.json` に書かない。** 設定ファイルは人に見せることがあるので、鍵は `secrets.env`（自分だけ読める権限）に分けてある。

鍵が無くても、AI を使わない機能は全部動く。

## 今までの書類を取り込む

去年の契約書も、前回の見積も、フォルダのどこかにある。毎回それを開いて写している。
その写す作業を消す。

画面の道順8に窓口があります。契約書や過去の見積をそこへドラッグするだけ。
ターミナル派は次のとおり。

```bash
paper-maker learn ~/Documents/契約書.pdf ~/Documents/見積_2025.pdf   # 何が入るか見るだけ
paper-maker learn ~/Documents/契約書.pdf --apply
paper-maker knowledge                 # 取り込んだ物
paper-maker knowledge clients         # 取引先
paper-maker knowledge items --word 構築   # 品目の単価の履歴
paper-maker knowledge clauses         # 条項
```

読み取ると、こう分かれる。

| 何が入るか | 次にどう効くか |
|---|---|
| 取引先（名前・住所） | 宛名だけ書けば、住所を控えから補う |
| 品目と単価 | 「前はいくらだったか」が新しい順に出る |
| 契約の条項 | 契約書の本文が空なら、控えた条項を並べて差し込む |

実際に動くところ。

```
$ paper-maker doc 契約書.json 契約書.pdf
控えた条項を差し込みました（263 文字）
```

**取り込む前に必ず中身を見せます。** `--apply` を付けるまで控えに入りません。
単価は「前はこの額だった」であって、次もその額とは限らない。そこは人が決めます。

原本は `~/.paper-maker/knowledge/` に控えます。読ませるには AI に繋いでおくこと。

## 更新

```bash
paper-maker update --check
paper-maker update
```

配布元の manifest と zip の SHA256 を照合してから入れ替える。合わなければ止まる。

## 置き場所

| 何 | どこ |
|---|---|
| 会社情報・日当・拠点・出力先 | `~/.paper-maker/profile.json` |
| 場所→駅の表 | `~/.paper-maker/places.json` |
| 運賃・駅 | `~/.paper-maker/fares.json` `stations.json` |
| Gemini 鍵など | `~/.paper-maker/secrets.env`（自分だけ読める権限） |
| 所感メモ | `~/.paper-maker/notes/` |
| 実行ログ | `~/.paper-maker/paper-maker.log`（日付と件数だけ。予定名や金額は書かない） |
| 出力 | `~/Documents/書類メーカー/` |

## 動作環境

- macOS 12 以降 / Windows 10 以降 / Linux
- Python 3.9 以上（Mac は標準の python3 でいい）
- PDF 化：Google Chrome か Microsoft Edge。無ければ HTML が出るので印刷から PDF に

## 開発

```bash
python3 -m unittest discover -s tests
python3 scripts/sanitize_app.py <元の index.html>   # GUI を更新するとき
```
