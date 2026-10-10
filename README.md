# compose2docker ― docker compose の構成を docker コマンドだけで再現する変換ツール

任意の compose ファイル (と、そこから参照される Dockerfile・設定ファイル・env ファイル) を読み込み、
`docker compose up -d` が裏側で行っていることを **docker コマンドだけ** で再現する手順を作ります。

| 出力ファイル | 内容 |
|---|---|
| `docker-commands.txt` | 起動手順。STEP ごとにコピーして貼り付け、または `bash docker-commands.txt` でそのまま実行できる (UTF-8 / LF) |
| `docker-commands-down.txt` | 後片付け (`docker compose down` 相当)。ボリューム・イメージの削除は `#` 付きで任意 |
| `docker-commands.md` | 起動・片付け手順の Markdown 版 (STEP ごとの説明つき) |
| `docker-commands-guide.xlsx` | **詳しい解説 (Excel)**。Meiryo UI・モノトーン。12 シート構成 (下記) |
| `docker-commands-guide.md` | 詳しい解説の Markdown 版 |

解説には、各 STEP の **実行順・実行方法・コマンドの意味・オプション 1 つ 1 つの意味・しくみ (動作原理)・動作イメージ (たとえ話)・
登場の歴史と背景・小学生向けのまとめ・RHEL 9.8 での注意** を、2026 年 10 月時点の情報 (Docker Engine 29.x / Compose v5.x / RHEL 9.8) で書いています。

---

## 1. 動作環境

| | |
|---|---|
| 変換ツール | Python 3.9 以上・**標準ライブラリのみ** (追加インストール不要)。RHEL 9.8 標準の `python3` (3.9) で動作確認済み。Windows でも動作 |
| 生成したコマンドの実行先 | **RHEL 9.8 + Docker Engine (docker-ce)**。1 回の `docker run` で複数ネットワークにつなぐため Docker Engine 25 以降、推奨は最新の 29.x |
| compose ファイルの解釈 | `docker compose` (v2 / v5) が使える環境では `docker compose config` の結果をそのまま使う。無い環境では同じ規則を再現した内蔵パーサを使う |

---

## 2. 使い方

### RHEL 上で変換する (おすすめ)

compose ファイルがある RHEL 上で実行すると、パスも実際の絶対パスになり、`docker compose config` で compose 自身と 100% 同じ解釈になります。

```bash
# ツール一式 (compose2docker.py と c2d フォルダ) を置いたら
cd /opt/myapp                                   # compose.yaml のあるフォルダ
python3 /opt/tools/compose2docker/compose2docker.py -f compose.yaml
# → ./compose2docker-out/<プロジェクト名>/ に 5 つのファイルができる

# 出力先を指定 / profiles を有効にする / 一部のサービス (と依存先) だけ
python3 compose2docker.py -f compose.yaml -o ./out
python3 compose2docker.py -f compose.yaml --profile debug
python3 compose2docker.py -f compose.yaml web db

# 複数の compose ファイル・.env の指定 (docker compose と同じ)
python3 compose2docker.py -f compose.yaml -f compose.build-secret.yaml --env-file .env.prod
```

### Windows で変換して RHEL で実行する

Windows のパスは RHEL では使えないため、RHEL 上の配置先を `--host-project-dir` で指定します (PowerShell から実行)。

```powershell
python compose2docker.py -f C:\work\myapp\compose.yaml --host-project-dir /opt/myapp -o .\out
```

`--host-project-dir` を省略すると、パスを `"$PWD"/...` (実行時のフォルダ基準) で書きます。その場合は RHEL で compose ファイルのあるフォルダへ `cd` してから実行してください。
Git Bash から実行する場合、`/opt/...` が Windows のパスに書き換えられてしまうので `MSYS_NO_PATHCONV=1` を付けてください (ツールが検出してエラーで知らせます)。

### 主なオプション

| オプション | 説明 |
|---|---|
| `-f, --file` | compose ファイル (複数可)。省略時は `compose.yaml` などを自動検出 (override ファイルも含む・compose と同じ) |
| `-p, --project-name` / `--project-directory` / `--env-file` / `--profile` | `docker compose` の同名オプションと同じ |
| `SERVICE ...` | 対象サービス (依存先も自動で含める。`docker compose up SERVICE` と同じ) |
| `-o, --output-dir` | 出力先 (既定: `./compose2docker-out/<プロジェクト名>`) |
| `--host-project-dir` | RHEL 上のプロジェクトのフォルダ (Windows で変換するとき) |
| `--loader auto/compose/builtin` | 読み込み方法 (既定 auto: docker compose があれば使う) |
| `--compose-labels` | compose が付けるラベル (`com.docker.compose.project` など) も付ける。コンテナ内のツールがラベルでコンテナを探す場合に使う |
| `--healthcheck-exec image/shell` | exec 形式ヘルスチェックの再現方法 (既定 image: 派生イメージに焼き込む) |
| `--env-mode auto/inline/file` | env_file の渡し方 (既定 auto: 読み方が同じファイルだけ `--env-file`) |
| `--no-guide` / `--no-xlsx` | 解説を作らない / xlsx だけ作らない |
| `--dump-plan` | 作るコンテナ・ネットワーク・ボリュームの一覧 (JSON)。`tools/compare_env.py` 用 |

---

## 3. compose と「完全に同じ」にするための工夫

docker compose v5.5.1 と Docker Engine 29.8.1 で、compose が実際に Docker API へ渡している値を `docker inspect` で調べ、それと同じになるように作っています。

| 項目 | compose の実際の動き | このツールの再現方法 |
|---|---|---|
| 名前 | ネットワーク/ボリューム `<project>_<key>`、コンテナ `<project>-<service>-<n>`、ビルドイメージ `<project>-<service>` | 同じ名前を付ける |
| 名前解決 | 各ネットワークでサービス名を別名 (alias) にする | `--network-alias` / `--network name=...,alias=...` |
| 複数ネットワーク | priority の高い順 → 名前順。最初がメイン | 同じ順番で `--network` を並べる |
| 起動順と待ち合わせ | depends_on の condition (healthy / completed_successfully) を待つ | 依存順に並べ、`docker inspect` のループ / `docker wait` で待つ |
| ヘルスチェック (exec 形式) | `["CMD", ...]` は シェルを通さず実行 | `--health-cmd` はシェル形式しか書けないため、`HEALTHCHECK CMD [...]` を焼き込んだ派生イメージを作る (distroless 対応) |
| env_file | compose 独自の読み方 (クォート・`${}` 展開・行末コメント) | docker の `--env-file` と同じ値になるファイルだけ `--env-file`、違うものは展開済みの値を `--env` |
| `$$` | compose が `$` に戻してから渡す | 展開済みの値をシングルクォートで渡す |
| ボリューム | 短い書き方のバインドと単純な名前付きボリュームは Binds (`-v`)、オプション付きは Mounts | 同じく `--volume` / `--mount` を使い分け |
| secrets / configs | file はバインドマウント (読み取り専用)、content / environment は起動前にコンテナへコピー | `--mount type=bind,...,readonly` / `docker create` → `tar | docker cp` → `docker start` |
| pre_start (init コンテナ) | 本番コンテナを create → `--volumes-from` で共有した使い捨てコンテナで実行 → start | 同じ手順を `docker create` / `docker run --rm --volumes-from` / `docker start` で |
| post_start / pre_stop | `docker exec` 相当 | `docker exec` |
| deploy.restart_policy | `restart` より優先して再起動ルールに変換 | 同じ優先順位で `--restart` |
| volumes_from の `:ro` | compose v5 は実際には付けずに渡している | compose と同じく付けない (注意書きを出す) |
| read_only + content の configs | compose はエラーで起動しない | 同じくエラーとして知らせる |
| profiles | 有効でないサービスは起動しない | 変換しない (注意書きで知らせる) |

---

## 4. 正しさの確かめ方 (あなたの RHEL でも実行できます)

`tools/compare_env.py` は、compose で起動した環境と docker コマンドで起動した環境を `docker inspect` で比べます
(コンテナ ID・作成日時・IP アドレスなど毎回変わる値と、compose 管理用のラベルは除外)。

```bash
python3 compose2docker.py -f compose.yaml -o out --dump-plan
docker compose up -d                       # ① compose で起動
python3 tools/compare_env.py snapshot --plan out/docker-commands-plan.json -o compose.json
docker compose down -v
bash out/docker-commands.txt               # ② 生成した docker コマンドで起動
python3 tools/compare_env.py snapshot --plan out/docker-commands-plan.json -o docker.json
bash out/docker-commands-down.txt
python3 tools/compare_env.py diff compose.json docker.json --ignore-image
```

開発時の検証結果:

* `examples/sample-shop` (nginx / 自作アプリのビルド / PostgreSQL / Valkey / 準備ジョブ / init コンテナ / フック / secrets / configs / env_file / internal ネットワーク) …
  環境変数・マウント・ポート・ネットワーク別名・ヘルスチェック・再起動ルール・資源制限・ログ設定・ulimit などすべて一致
  (違いはヘルスチェック入り派生イメージの名前だけ)。アプリの応答で、env ファイル・config の投入・init コンテナ・post_start・内部ネットワークの名前解決も動作確認。
* 31 個の実際の compose ファイル + 実験用ファイルで、内蔵ローダーの解釈が `docker compose config` と一致。
* RHEL 9.8 (UBI 9) + Python 3.9 で、内蔵ローダーの出力が `docker compose config` を使った出力とバイト単位で一致。
* 引用符の処理は、31 種類の厄介な文字列 (`'` `"` `$` `` ` `` `\` `!` 改行 タブ 日本語 など) を実際の bash に通して検証。

---

## 5. 解説 Excel のシート構成

| シート | 内容 |
|---|---|
| 表紙 | 概要・はじめに・しくみの全体図・実行の流れ・シートの案内 |
| 実行手順一覧 | 全 STEP の一覧 (各 STEP の解説へのリンク付き・フィルター付き) |
| 手順ごとの解説 | STEP ごとのカード: コマンド / 実行のしかた / すること / しくみ / たとえ話 / 歴史 / 小学生向け / RHEL の注意 / 確認方法 / compose での書き方 |
| オプション解説 | オプション 1 つ 1 つ: 値 / compose のどの設定から来たか / この STEP での意味 / しくみ / やさしい説明 |
| コマンド全文 | 実行用 txt と同じ内容 |
| 後片付け | down 相当の手順 |
| compose対応表 | このプロジェクトの対応表 + 一般的な対応表 |
| しくみの深掘り | コマンドの種類ごとの詳しい説明 (辞書) |
| 用語集 | 用語・読み・意味・小学生向けのたとえ |
| 歴史年表 | 1979 年の chroot から Docker 29.9 / Compose 5.6 / RHEL 9.8 まで |
| 注意・制限事項 | このプロジェクトの変換メモ・一般的な制限・RHEL 9.8 の注意 |
| RHEL9.8の準備 | docker-ce のインストール手順 (Docker 公式手順に基づく) |

---

## 6. フォルダ構成

```
compose2docker.py          … 実行用 (python3 compose2docker.py ...)
c2d/                       … 本体 (標準ライブラリのみ)
  yamlmini.py              … YAML パーサ (go-yaml v3 / compose-go と同じ解釈)
  envfile.py               … ${VAR} 展開・.env / env_file の読み込み (compose-go 互換) と docker --env-file の読み方
  loader.py                … compose ファイルの読み込み・正規化 (docker compose config / 内蔵)
  planner.py               … docker コマンドの手順への変換 (中心部分)
  shell.py / textutil.py   … bash 用の引用符・折り返し
  render_cmds.py           … txt / md の出力
  render_guide.py          … 解説 (md / xlsx) の出力
  xlsx.py                  … 標準ライブラリだけの xlsx ライター
  kb_commands.py / kb_options.py / kb_misc.py … 解説の文章 (コマンド・オプション・用語集・年表など)
tools/compare_env.py       … compose 版と docker 版の環境の比較ツール
examples/sample-shop/      … 動作確認用のサンプル compose プロジェクト
output/                    … 生成例 (sample-shop と、Container_Compose_file の compose.yaml)
tests/                     … 開発用テスト (PyYAML / docker compose / bash が必要なもの)
```

---

## 7. 既知の制限

* exec 形式のヘルスチェックは派生イメージ (`<project>-<service>:with-healthcheck`) で再現するため、`docker ps` のイメージ名が変わります (動作は同じ)。
* compose 管理用ラベルは既定で付けません (`docker compose ps` / `down` の対象外)。必要なら `--compose-labels`。ただし compose の config-hash は付けられないため、その後 `docker compose up` すると作り直しになります。
* compose は依存の無いサービスを並列に起動しますが、この手順は 1 つずつ順に起動します (結果は同じ)。
* 待ち合わせで NG が出ても、貼り付けた残りのコマンドは続いてしまいます (compose はそこで止まります)。NG が出たら原因を確認してください。
* `${VAR}` / `.env` の値は変換時点の値で展開されます。`.env` を変えたら変換し直してください。
* provider / models / develop(watch) / Swarm 専用の deploy 設定は docker コマンドだけでは再現できないため対象外です (警告を出します)。
* 2 回目の実行は、先に後片付けをしてください (compose up のような差分更新はしません)。
