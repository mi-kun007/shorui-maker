#!/usr/bin/env bash
# 書類メーカー 配布版のインストール（macOS / Linux）
#   使い方: このフォルダで  bash install.sh
# やること: ~/.paper-maker/app にコピー → ~/.local/bin/paper-maker を置く → 初回設定へ案内
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${PAPER_MAKER_APP_DIR:-$HOME/.paper-maker/app}"
BIN="$HOME/.local/bin"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 が見つかりません。macOS は「xcode-select --install」、Linux はパッケージで python3 を入れてください"; exit 1
fi
PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)'; then :; else
  echo "Python 3.9 以上が必要です（今は $PYV）"; exit 1
fi

mkdir -p "$DEST" "$BIN"
# 自分自身へのコピーは避ける
if [ "$SRC" != "$DEST" ]; then
  rsync -a --delete --exclude '.git' --exclude '__pycache__' --exclude 'dist' "$SRC/" "$DEST/"
fi

cat > "$BIN/paper-maker" <<EOF
#!/usr/bin/env bash
cd "$DEST" && exec python3 -m paper_maker "\$@"
EOF
chmod +x "$BIN/paper-maker"

# デスクトップにアイコンを置く。ターミナルを二度と開かなくていいように
DESK="$(cd "$DEST" && python3 -m paper_maker desktop 2>&1 | head -1)"

# 前の版を抱えたまま走っているサーバを落とす。
# 入れ替えても、走っているサーバは古いコードを抱えたまま動き続ける。
# 置き場が違うサーバは残す（1台に2つ入れている人の分を落とさない）
HOME_DIR="${PAPER_MAKER_HOME:-$HOME/.paper-maker}"
for PORT in $(seq 8797 8810); do
  HELLO=$(curl -s -m 1 "http://127.0.0.1:$PORT/api/hello" 2>/dev/null || true)
  case "$HELLO" in
    *paper-maker*)
      case "$HELLO" in
        *"$HOME_DIR"*)
          lsof -ti tcp:$PORT 2>/dev/null | xargs kill 2>/dev/null || true
          echo "開いていた画面を閉じました（ポート $PORT）"
          ;;
      esac
      ;;
  esac
done

echo "入れました: $DEST"
echo "$DESK"
echo "コマンド : $BIN/paper-maker"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "PATH に $BIN が無いので、シェルの設定に次を足してください:"; echo "  export PATH=\"\$HOME/.local/bin:\$PATH\"";;
esac
echo
echo "デスクトップの「書類メーカー」を押してください。画面が開いて、そこから全部入れられます。"
echo "ターミナル派の人は: paper-maker init / paper-maker doctor"
