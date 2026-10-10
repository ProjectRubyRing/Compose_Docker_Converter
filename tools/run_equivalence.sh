#!/usr/bin/env bash
# =============================================================================
# compose で起動した環境と、compose2docker が作った docker コマンドで起動した
# 環境が同じになるかを、実際に起動して docker inspect で比べるスクリプト。
#
# 使い方 (compose ファイルのあるフォルダで):
#   bash /path/to/tools/run_equivalence.sh [compose2docker のオプション...]
#   例) bash tools/run_equivalence.sh -f compose.yaml
#       bash tools/run_equivalence.sh -f compose.yaml --profile debug
#
# 流れ:
#   1) compose2docker で docker コマンドを生成 (./c2d-equivalence/)
#   2) docker compose up -d --build → 状態を保存 (compose.json)
#   3) docker compose down (ボリュームは消さない)
#   4) 生成した docker-commands.txt を実行 → 状態を保存 (docker.json)
#   5) 生成した docker-commands-down.txt で片付け
#   6) 2 つの状態を比べて、違いを表示
#
# 注意:
#   * 起動中の compose 環境は一度止まります (down)。本番環境では実行しないでください。
#   * 名前付きボリュームは消しません (データは残ります)。最後に消したいときは
#     C2D_REMOVE_VOLUMES=1 を付けて実行してください。
#   * ヘルスチェックの結果が落ち着くまで C2D_WAIT 秒 (既定 30) 待ってから比べます。
# =============================================================================
set -u
TOOL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${C2D_OUT:-$PWD/c2d-equivalence}"
WAIT="${C2D_WAIT:-30}"
mkdir -p "$OUT"

echo "[1/6] docker コマンドを生成します -> $OUT"
python3 "$TOOL_DIR/compose2docker.py" -o "$OUT" --dump-plan --no-guide "$@" || exit 1

COMPOSE_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -f|--file|-p|--project-name|--env-file|--profile|--project-directory)
      COMPOSE_ARGS+=("$1" "$2"); shift 2 ;;
    *) shift ;;
  esac
done

echo "[2/6] docker compose up -d --build"
docker compose "${COMPOSE_ARGS[@]}" up -d --build || echo "!! docker compose up が失敗しました (compose 自体のエラー)"
sleep "$WAIT"
python3 "$TOOL_DIR/tools/compare_env.py" snapshot --plan "$OUT/docker-commands-plan.json" -o "$OUT/compose.json"

echo "[3/6] docker compose down (ボリュームは残します)"
docker compose "${COMPOSE_ARGS[@]}" down

echo "[4/6] 生成した docker コマンドで起動"
bash "$OUT/docker-commands.txt" > "$OUT/docker-run.log" 2>&1
echo "      (出力は $OUT/docker-run.log)"
sleep "$WAIT"
python3 "$TOOL_DIR/tools/compare_env.py" snapshot --plan "$OUT/docker-commands-plan.json" -o "$OUT/docker.json"

echo "[5/6] 片付け"
bash "$OUT/docker-commands-down.txt" > "$OUT/docker-down.log" 2>&1
if [ "${C2D_REMOVE_VOLUMES:-0}" = "1" ]; then
  for v in $(python3 -c "import json,sys; print(' '.join(json.load(open(sys.argv[1]))['volumes']))" "$OUT/docker-commands-plan.json"); do
    docker volume rm "$v" > /dev/null && echo "      ボリューム $v を削除しました"
  done
fi

echo "[6/6] 比較 (左: compose / 右: docker コマンド)"
python3 "$TOOL_DIR/tools/compare_env.py" diff "$OUT/compose.json" "$OUT/docker.json" --ignore-image
