# 運用手順（渡す相手向け）

<!-- ファイル名は英数字にしてある。日本語名だと macOS 標準の unzip が配布 zip の展開を途中で止めるため -->

## 毎日のこと
何もしなくていい。朝6時に前日分の営業報告書が `~/Documents/書類メーカー/年/月/` に出る。
現地に行った日は出張精算も一緒に出る。

所感を入れたい日は `~/.paper-maker/notes/2026-08-13.md` に一行書いておく。次に作られる時に入る。

## 自動実行の入切
```bash
paper-maker schedule status     # 今どうなっているか
paper-maker schedule install    # 毎朝6時に
paper-maker schedule install --hour 8 --minute 30
paper-maker schedule remove     # 止める
```

## 作り直したいとき
```bash
paper-maker daily --date 2026-08-13          # その日をやり直す（上書き）
paper-maker daily --date 2026-08-13 --force  # 予定が無い日でも1枚出す
```

## 運賃が「要確認」と出たら
実際に払った額を入れる。入れるまで金額は空のまま出る（勝手な数字を入れない作り）。
```bash
paper-maker fare add 新宿 横浜 560
paper-maker fare list
```

## 予定が現地と判定されないとき
カレンダーの**場所欄に住所を入れる**。ここが一番効く。
それでも拾わないときは `~/.paper-maker/places.json` に言葉と駅を足す。

```json
{"match": ["さいたま市", "大宮"], "station": "大宮"}
```

## 会社の情報を変えたい
`~/.paper-maker/profile.json` を直す。役職や日当を変えたら、旅費規程も作り直す。
```bash
paper-maker rules
```

## 動かないとき
```bash
paper-maker doctor
```
Python・ブラウザ・設定ファイル・カレンダーの取り口を順に見て、足りない所を出す。

よくある詰まり
| 症状 | 見る所 |
|---|---|
| PDF が出ず HTML だけ | Chrome か Edge が入っているか。無くても HTML を印刷すれば同じ物になる |
| 予定が0件 | ICS のパス・URL。Google の限定公開 URL は再発行すると変わる |
| 「ポートが使用中」 | `paper-maker app --port 8798` |
| 何も起きない（自動実行） | `~/.paper-maker/paper-maker.log` の最終行の日付 |

## 戻し方
更新して具合が悪くなったら、`~/.paper-maker/app.bak-<前の版>` が残っている。
中身を `~/.paper-maker/app` に戻せば前の版に戻る。設定と書類はそのまま残る。

## 消すとき
```bash
paper-maker schedule remove
rm -rf ~/.paper-maker ~/.local/bin/paper-maker
```
作った書類（`~/Documents/書類メーカー/`）は消えない。要らなければ手で消す。

## 問い合わせ
（保守契約の窓口をここに書く）
