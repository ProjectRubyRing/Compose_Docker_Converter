# 生成例

| フォルダ | 元の compose | 生成コマンド (抜粋) |
|---|---|---|
| `sample-shop/` | `examples/sample-shop/compose.yaml` | `python3 compose2docker.py -f compose.yaml --host-project-dir /opt/sample-shop` |
| `eap-adot-local/` | `../Container_Compose_file/compose.yaml` (26 サービス) | `python3 compose2docker.py -f compose.yaml --env-file .env.example --host-project-dir /opt/Container_Compose_file` |

* どちらも docker compose v5.5.1 (`docker compose config`) で解釈した結果から作っています。
* RHEL 上の配置先として `/opt/sample-shop` / `/opt/Container_Compose_file` を仮に指定しています。実際の配置先で使うときは、
  RHEL 上でそのフォルダから変換し直してください (パスが自動で実際の場所になります)。
* `eap-adot-local/` は `.env` が無いため `.env.example` の値 (`EAP_BASE_IMAGE=your-registry.example.com/...` という仮の値) で作っています。
  本物の `.env` がある環境で変換し直すと、ベースイメージ名などが実際の値になります。
* `sample-shop` は、compose で起動した環境と生成コマンドで起動した環境を `tools/run_equivalence.sh` で比べ、差分が無いことを確認済みです。
