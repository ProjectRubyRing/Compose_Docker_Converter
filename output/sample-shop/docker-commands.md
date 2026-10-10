# sample-shop を docker コマンドだけで起動する手順

`docker compose up -d` と同じ構成を、`docker` コマンドだけで作るための手順です。STEP 1 から順に、コードブロックの中身をそのままターミナルに貼り付けて実行します。

| 項目 | 内容 |
|---|---|
| プロジェクト名 | `sample-shop` |
| 元の compose ファイル | `/opt/sample-shop/compose.yaml` |
| 読み込み方法 | docker compose config (Docker Compose 5.5.1 が解釈した結果) |
| 生成日時 | 2026-10-10 15:06:28 |
| 生成ツール | compose2docker 1.0.0 |
| 実行環境 | RHEL 9.8 + Docker Engine (docker-ce 25 以降 / 推奨 29.x) |
| 起動するコンテナ | `sample-shop-db-1`、`sample-shop-cache-1`、`sample-shop-migrate-1`、`sample-shop-app-1`、`sample-shop-web-1` |

## 実行の前に

1. RHEL 9.8 に Docker Engine (docker-ce) が入っていて、`sudo systemctl enable --now docker` で起動済みであること。
2. `root` か、`docker` グループに入っているユーザーで実行すること (`sudo usermod -aG docker <ユーザー名>` の後、ログインし直す)。
3. compose ファイルと、そこから参照されるファイル (Dockerfile・設定ファイル・env ファイルなど) が、同じフォルダ構成で RHEL 上に置かれていること。
4. 2 回目以降は、先に [後片付け](#後片付け-compose-down-と同じ) をしてから実行すること (同じ名前のコンテナやネットワークがあるとエラーになります)。

## 変換時の注意

- services.toolbox は profiles (debug) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile debug を付けて変換し直してください。

## 手順一覧

| STEP | 区分 | やること | 対象 |
|---:|---|---|---|
| 1 | 準備 | [作業フォルダへ移動し、Docker が使えるか確認する](#step-1) | - |
| 2 | ネットワーク作成 | [ネットワーク「sample-shop_frontend」を作る](#step-2) | `sample-shop_frontend` |
| 3 | ネットワーク作成 | [ネットワーク「sample-shop_backend」を作る](#step-3) | `sample-shop_backend` |
| 4 | ボリューム作成 | [ボリューム「sample-shop_db-data」を作る](#step-4) | `sample-shop_db-data` |
| 5 | ボリューム作成 | [ボリューム「sample-shop_cache-data」を作る](#step-5) | `sample-shop_cache-data` |
| 6 | ボリューム作成 | [ボリューム「sample-shop_app-cache」を作る](#step-6) | `sample-shop_app-cache` |
| 7 | イメージ取得 | [イメージ「postgres:16-alpine」を用意する](#step-7) | `postgres:16-alpine` |
| 8 | イメージ取得 | [イメージ「valkey/valkey:8-alpine」を用意する](#step-8) | `valkey/valkey:8-alpine` |
| 9 | イメージ取得 | [イメージ「nginx:1.27-alpine」を用意する](#step-9) | `nginx:1.27-alpine` |
| 10 | イメージ取得 | [イメージ「busybox:1.36」を用意する](#step-10) | `busybox:1.36` |
| 11 | イメージ作成 | [サービス「app」のイメージ「sample-shop/app:1.0.0」をビルドする](#step-11) | `sample-shop/app:1.0.0` |
| 12 | ヘルスチェック入りイメージ作成 | [サービス「cache」用に、ヘルスチェックを焼き込んだイメージ「sample-shop-cache:with-healthcheck」を作る](#step-12) | `sample-shop-cache:with-healthcheck` |
| 13 | ヘルスチェック入りイメージ作成 | [サービス「web」用に、ヘルスチェックを焼き込んだイメージ「sample-shop-web:with-healthcheck」を作る](#step-13) | `sample-shop-web:with-healthcheck` |
| 14 | コンテナ起動 | [サービス「db」のコンテナ「sample-shop-db-1」を起動する](#step-14) | `sample-shop-db-1` |
| 15 | コンテナ起動 | [サービス「cache」のコンテナ「sample-shop-cache-1」を起動する](#step-15) | `sample-shop-cache-1` |
| 16 | 起動待ち | [sample-shop-db-1 が healthy になるまで待つ](#step-16) | `sample-shop-db-1` |
| 17 | コンテナ起動 | [サービス「migrate」のコンテナ「sample-shop-migrate-1」を起動する](#step-17) | `sample-shop-migrate-1` |
| 18 | 起動待ち | [sample-shop-cache-1・sample-shop-db-1 が healthy になるまで待つ](#step-18) | `sample-shop-cache-1 sample-shop-db-1` |
| 19 | 完了待ち | [sample-shop-migrate-1 が正常終了するまで待つ](#step-19) | `sample-shop-migrate-1` |
| 20 | コンテナ作成 | [サービス「app」のコンテナ「sample-shop-app-1」を作る (まだ起動しない)](#step-20) | `sample-shop-app-1` |
| 21 | ファイル投入 | [設定ファイル (configs)「app_settings」を sample-shop-app-1 の /etc/shop/settings.ini に入れる](#step-21) | `sample-shop-app-1` |
| 22 | 初期化コンテナ | [サービス「app」の起動前の初期化 1 (pre_start) を実行する](#step-22) | `sample-shop-app-1` |
| 23 | コンテナ起動 | [コンテナ「sample-shop-app-1」を起動する](#step-23) | `sample-shop-app-1` |
| 24 | 起動後フック | [コンテナ「sample-shop-app-1」で post_start フック 1 を実行する](#step-24) | `sample-shop-app-1` |
| 25 | 起動待ち | [sample-shop-app-1 が healthy になるまで待つ](#step-25) | `sample-shop-app-1` |
| 26 | コンテナ起動 | [サービス「web」のコンテナ「sample-shop-web-1」を起動する](#step-26) | `sample-shop-web-1` |
| 27 | 状態確認 | [起動したコンテナの状態を確認する](#step-27) | - |

<a id="step-1"></a>

## STEP 1: 作業フォルダへ移動し、Docker が使えるか確認する

- 区分: **準備**

履歴展開 (!) を止めて貼り付け事故を防ぎ、プロジェクトのフォルダへ移動して、docker コマンドとサーバー (dockerd) の両方が動いているかを確かめます。

```bash
set +H
cd /opt/sample-shop
docker version
```

確認: `docker info`

<a id="step-2"></a>

## STEP 2: ネットワーク「sample-shop_frontend」を作る

- 区分: **ネットワーク作成**
- compose の対応箇所: `networks.frontend`

仮想ネットワーク「sample-shop_frontend」を作ります。つながるコンテナ: app、web。同じネットワークのコンテナどうしは、サービス名で呼び合えます。

```bash
docker network create sample-shop_frontend
```

確認: `docker network ls --filter name=sample-shop_frontend` ／ `docker network inspect sample-shop_frontend`

<a id="step-3"></a>

## STEP 3: ネットワーク「sample-shop_backend」を作る

- 区分: **ネットワーク作成**
- compose の対応箇所: `networks.backend`

仮想ネットワーク「sample-shop_backend」を作ります。つながるコンテナ: db、cache、migrate、app。同じネットワークのコンテナどうしは、サービス名で呼び合えます。

```bash
docker network create --internal sample-shop_backend
```

確認: `docker network ls --filter name=sample-shop_backend` ／ `docker network inspect sample-shop_backend`

<a id="step-4"></a>

## STEP 4: ボリューム「sample-shop_db-data」を作る

- 区分: **ボリューム作成**
- compose の対応箇所: `volumes.db-data`

データを保存しておく名前付きボリューム「sample-shop_db-data」を作ります。使うサービス: db。

```bash
docker volume create sample-shop_db-data
```

確認: `docker volume ls --filter name=sample-shop_db-data` ／ `docker volume inspect sample-shop_db-data`

<a id="step-5"></a>

## STEP 5: ボリューム「sample-shop_cache-data」を作る

- 区分: **ボリューム作成**
- compose の対応箇所: `volumes.cache-data`

データを保存しておく名前付きボリューム「sample-shop_cache-data」を作ります。使うサービス: cache。

```bash
docker volume create sample-shop_cache-data
```

確認: `docker volume ls --filter name=sample-shop_cache-data` ／ `docker volume inspect sample-shop_cache-data`

<a id="step-6"></a>

## STEP 6: ボリューム「sample-shop_app-cache」を作る

- 区分: **ボリューム作成**
- compose の対応箇所: `volumes.app-cache`

データを保存しておく名前付きボリューム「sample-shop_app-cache」を作ります。使うサービス: app。

```bash
docker volume create sample-shop_app-cache
```

確認: `docker volume ls --filter name=sample-shop_app-cache` ／ `docker volume inspect sample-shop_app-cache`

<a id="step-7"></a>

## STEP 7: イメージ「postgres:16-alpine」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.db.image`

イメージ「postgres:16-alpine」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect postgres:16-alpine > /dev/null 2>&1 || docker pull postgres:16-alpine
```

確認: `docker image ls postgres:16-alpine`

<a id="step-8"></a>

## STEP 8: イメージ「valkey/valkey:8-alpine」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.cache.image`

イメージ「valkey/valkey:8-alpine」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect valkey/valkey:8-alpine > /dev/null 2>&1 || docker pull valkey/valkey:8-alpine
```

確認: `docker image ls valkey/valkey:8-alpine`

<a id="step-9"></a>

## STEP 9: イメージ「nginx:1.27-alpine」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.web.image`

イメージ「nginx:1.27-alpine」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect nginx:1.27-alpine > /dev/null 2>&1 || docker pull nginx:1.27-alpine
```

確認: `docker image ls nginx:1.27-alpine`

<a id="step-10"></a>

## STEP 10: イメージ「busybox:1.36」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.app.pre_start`

イメージ「busybox:1.36」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect busybox:1.36 > /dev/null 2>&1 || docker pull busybox:1.36
```

確認: `docker image ls busybox:1.36`

<a id="step-11"></a>

## STEP 11: サービス「app」のイメージ「sample-shop/app:1.0.0」をビルドする

- 区分: **イメージ作成**
- compose の対応箇所: `services.app.build`

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「sample-shop/app:1.0.0」を作ります。

```bash
docker build \
  --target runtime \
  --build-arg APP_VERSION=1.0.0 \
  --build-arg PYTHON_VERSION=3.12 \
  --label com.example.built-by=compose2docker-sample \
  --tag sample-shop/app:1.0.0 \
  /opt/sample-shop/app
```

確認: `docker image ls sample-shop/app` ／ `docker image inspect sample-shop/app:1.0.0`

<a id="step-12"></a>

## STEP 12: サービス「cache」用に、ヘルスチェックを焼き込んだイメージ「sample-shop-cache:with-healthcheck」を作る

- 区分: **ヘルスチェック入りイメージ作成**
- compose の対応箇所: `services.cache.healthcheck`

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

```bash
docker build --tag sample-shop-cache:with-healthcheck - <<'C2D_DOCKERFILE'
FROM valkey/valkey:8-alpine
HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD ["valkey-cli", "ping"]
C2D_DOCKERFILE
```

確認: `docker image inspect --format '{{json .Config.Healthcheck}}' sample-shop-cache:with-healthcheck`

<a id="step-13"></a>

## STEP 13: サービス「web」用に、ヘルスチェックを焼き込んだイメージ「sample-shop-web:with-healthcheck」を作る

- 区分: **ヘルスチェック入りイメージ作成**
- compose の対応箇所: `services.web.healthcheck`

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

```bash
docker build --tag sample-shop-web:with-healthcheck - <<'C2D_DOCKERFILE'
FROM nginx:1.27-alpine
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1/healthz"]
C2D_DOCKERFILE
```

確認: `docker image inspect --format '{{json .Config.Healthcheck}}' sample-shop-web:with-healthcheck`

<a id="step-14"></a>

## STEP 14: サービス「db」のコンテナ「sample-shop-db-1」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.db`

イメージ「postgres:16-alpine」からコンテナ「sample-shop-db-1」を作って起動します (サービス「db」)。

```bash
docker run \
  --detach \
  --name sample-shop-db-1 \
  --restart unless-stopped \
  --network sample-shop_backend \
  --network-alias db \
  --volume sample-shop_db-data:/var/lib/postgresql/data \
  --volume /opt/sample-shop/db/init.sql:/docker-entrypoint-initdb.d/10-init.sql:ro \
  --mount type=bind,source=/opt/sample-shop/secrets/db_password.txt,target=/run/secrets/db_password,readonly \
  --env POSTGRES_DB=shop \
  --env POSTGRES_PASSWORD_FILE=/run/secrets/db_password \
  --env POSTGRES_USER=shop \
  --shm-size 128m \
  --log-driver json-file \
  --log-opt max-file=3 \
  --log-opt max-size=10m \
  --health-cmd 'pg_isready -U shop -d shop' \
  --health-interval 5s \
  --health-timeout 3s \
  --health-start-period 10s \
  --health-retries 10 \
  --stop-timeout 30 \
  postgres:16-alpine
```

確認: `docker ps --all --filter name=sample-shop-db-1` ／ `docker logs sample-shop-db-1` ／ `docker inspect sample-shop-db-1`

<a id="step-15"></a>

## STEP 15: サービス「cache」のコンテナ「sample-shop-cache-1」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.cache`

イメージ「sample-shop-cache:with-healthcheck」からコンテナ「sample-shop-cache-1」を作って起動します (サービス「cache」)。

```bash
docker run \
  --detach \
  --name sample-shop-cache-1 \
  --restart unless-stopped \
  --network sample-shop_backend \
  --network-alias cache \
  --volume sample-shop_cache-data:/data \
  --log-driver json-file \
  --log-opt max-file=3 \
  --log-opt max-size=10m \
  sample-shop-cache:with-healthcheck \
  valkey-server --appendonly yes --save ''
```

確認: `docker ps --all --filter name=sample-shop-cache-1` ／ `docker logs sample-shop-cache-1` ／ `docker inspect sample-shop-cache-1`

<a id="step-16"></a>

## STEP 16: sample-shop-db-1 が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.migrate.depends_on`

サービス「migrate」は depends_on で db が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in sample-shop-db-1; do
  echo "[待機] ${C} が healthy (正常) になるまで待ちます..."
  while :; do
    S="$(docker inspect --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}' "${C}" 2>&1)"
    case "${S}" in
      running:healthy) echo "[OK] ${C} は healthy です"; break ;;
      running:starting|restarting:*) sleep 2 ;;
      *) echo "[NG] ${C} の状態は ${S} です。docker logs ${C} で原因を確認してください"; break ;;
    esac
  done
done
```

確認: `docker ps --filter name=sample-shop-db-1`

<a id="step-17"></a>

## STEP 17: サービス「migrate」のコンテナ「sample-shop-migrate-1」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.migrate`

イメージ「postgres:16-alpine」からコンテナ「sample-shop-migrate-1」を作って起動します (サービス「migrate」)。

```bash
docker run \
  --detach \
  --name sample-shop-migrate-1 \
  --network sample-shop_backend \
  --network-alias migrate \
  --volume /opt/sample-shop/db/migrations:/migrations:ro \
  --mount type=bind,source=/opt/sample-shop/secrets/db_password.txt,target=/run/secrets/db_password,readonly \
  --log-driver json-file \
  --log-opt max-file=3 \
  --log-opt max-size=10m \
  postgres:16-alpine \
  sh \
  -c \
  $'export PGPASSWORD="$(cat /run/secrets/db_password)"\npsql -h db -U shop -d shop -v ON_ERROR_STOP=1 -f /migrations/001_items.sql\necho "migration done"\n'
```

確認: `docker ps --all --filter name=sample-shop-migrate-1` ／ `docker logs sample-shop-migrate-1` ／ `docker inspect sample-shop-migrate-1`

<a id="step-18"></a>

## STEP 18: sample-shop-cache-1・sample-shop-db-1 が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.app.depends_on`

サービス「app」は depends_on で cache・db が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in sample-shop-cache-1 sample-shop-db-1; do
  echo "[待機] ${C} が healthy (正常) になるまで待ちます..."
  while :; do
    S="$(docker inspect --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}' "${C}" 2>&1)"
    case "${S}" in
      running:healthy) echo "[OK] ${C} は healthy です"; break ;;
      running:starting|restarting:*) sleep 2 ;;
      *) echo "[NG] ${C} の状態は ${S} です。docker logs ${C} で原因を確認してください"; break ;;
    esac
  done
done
```

確認: `docker ps --filter name=sample-shop-cache-1`

<a id="step-19"></a>

## STEP 19: sample-shop-migrate-1 が正常終了するまで待つ

- 区分: **完了待ち**
- compose の対応箇所: `services.app.depends_on`

サービス「app」は depends_on で「service_completed_successfully (正常に終了)」を待つ設定です。docker wait で終了を待ち、終了コードが 0 (成功) かを確かめます。

```bash
echo "[待機] sample-shop-migrate-1 が終わるまで待ちます..."
EXIT_CODE="$(docker wait sample-shop-migrate-1)"
echo "sample-shop-migrate-1 の終了コード: ${EXIT_CODE} (0 なら成功)"
```

確認: `docker ps --all --filter name=sample-shop-migrate-1` ／ `docker logs sample-shop-migrate-1`

<a id="step-20"></a>

## STEP 20: サービス「app」のコンテナ「sample-shop-app-1」を作る (まだ起動しない)

- 区分: **コンテナ作成**
- compose の対応箇所: `services.app`

コンテナ「sample-shop-app-1」をイメージ「sample-shop/app:1.0.0」から作りますが、まだ起動しません。起動前にファイルの投入や初期化 (pre_start) を行うためです。

> ※ 複数のネットワークを docker run 1 回でつなぐ書き方 (--network name=...,alias=...) は Docker Engine 25 以降で使えます。RHEL 9.8 で最新の docker-ce (29.x) を入れていれば問題ありません。

```bash
docker create \
  --name sample-shop-app-1 \
  --restart unless-stopped \
  --init \
  --user 10001:10001 \
  --network name=sample-shop_backend,alias=app \
  --network name=sample-shop_frontend,alias=app,alias=api \
  --add-host host.docker.internal:host-gateway \
  --volume sample-shop_app-cache:/var/cache/shop \
  --tmpfs /tmp:size=16m \
  --env-file /opt/sample-shop/env/app.env \
  --env API_TOKEN=s3cr3t-token \
  --env CACHE_HOST=cache \
  --env DB_HOST=db \
  --env DB_PORT=5432 \
  --env 'GREETING=Hello from version 1.0.0' \
  --env LOG_LEVEL=info \
  --env SETTINGS_FILE=/etc/shop/settings.ini \
  --ulimit nofile=4096:8192 \
  --cpus 0.5 \
  --memory 256m \
  --log-driver json-file \
  --log-opt max-file=3 \
  --log-opt max-size=10m \
  --health-cmd $'python -c "import urllib.request; urllib.request.urlopen(\'http://127.0.0.1:8000/healthz\', timeout=3)"' \
  --health-interval 5s \
  --health-timeout 3s \
  --health-start-period 5s \
  --health-retries 10 \
  sample-shop/app:1.0.0
```

確認: `docker ps --all --filter name=sample-shop-app-1` ／ `docker logs sample-shop-app-1` ／ `docker inspect sample-shop-app-1`

<a id="step-21"></a>

## STEP 21: 設定ファイル (configs)「app_settings」を sample-shop-app-1 の /etc/shop/settings.ini に入れる

- 区分: **ファイル投入**
- compose の対応箇所: `configs.app_settings`

compose は 設定ファイル (configs) の中身 (content / environment) を、コンテナを起動する前にファイルとして書き込みます。同じように、一時ファイルを作って tar でまとめ、docker cp でコンテナの /etc/shop/settings.ini に入れます。

```bash
mkdir -p /tmp/sample-shop-compose2docker/sample-shop-app-1/etc/shop
cat > /tmp/sample-shop-compose2docker/sample-shop-app-1/etc/shop/settings.ini <<'C2D_CONTENT'
[shop]
currency = JPY
tax_rate = 0.10
C2D_CONTENT
tar --create --owner=0 --group=0 --mode=0444 --directory /tmp/sample-shop-compose2docker/sample-shop-app-1 --file - etc/shop/settings.ini | docker cp - sample-shop-app-1:/
rm -rf /tmp/sample-shop-compose2docker/sample-shop-app-1
```

確認: `docker cp sample-shop-app-1:/etc/shop/settings.ini - | tar -tvf -`

<a id="step-22"></a>

## STEP 22: サービス「app」の起動前の初期化 1 (pre_start) を実行する

- 区分: **初期化コンテナ**
- compose の対応箇所: `services.app.pre_start[0]`

compose v5.3 で追加された init コンテナ (pre_start) を再現します。本番コンテナを作った後・起動する前に、使い捨てのコンテナで準備作業を 1 回だけ行います。

```bash
docker run \
  --rm \
  --volumes-from sample-shop-app-1 \
  --network name=sample-shop_backend,alias=app \
  --network name=sample-shop_frontend,alias=app,alias=api \
  --user root \
  --env-file /opt/sample-shop/env/app.env \
  --env API_TOKEN=s3cr3t-token \
  --env CACHE_HOST=cache \
  --env DB_HOST=db \
  --env DB_PORT=5432 \
  --env 'GREETING=Hello from version 1.0.0' \
  --env LOG_LEVEL=info \
  --env SETTINGS_FILE=/etc/shop/settings.ini \
  busybox:1.36 \
  sh -c 'echo warmed-at-start > /var/cache/shop/warm.txt && chown -R 10001:10001 /var/cache/shop'
```

確認: `docker logs sample-shop-app-1  (初期化コンテナは --rm で消えるため、上の画面出力で確認します)`

<a id="step-23"></a>

## STEP 23: コンテナ「sample-shop-app-1」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.app`

ファイルの投入・初期化コンテナ (pre_start) が終わったので、コンテナ「sample-shop-app-1」を起動します。

```bash
docker start sample-shop-app-1
```

確認: `docker ps --filter name=sample-shop-app-1` ／ `docker logs sample-shop-app-1`

<a id="step-24"></a>

## STEP 24: コンテナ「sample-shop-app-1」で post_start フック 1 を実行する

- 区分: **起動後フック**
- compose の対応箇所: `services.app.post_start[0]`

compose の post_start フック (コンテナ起動直後に中で実行するコマンド) を docker exec で再現します。

```bash
docker exec sample-shop-app-1 sh -c 'date > /tmp/started-at'
```

確認: `docker logs sample-shop-app-1`

<a id="step-25"></a>

## STEP 25: sample-shop-app-1 が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.web.depends_on`

サービス「web」は depends_on で app が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in sample-shop-app-1; do
  echo "[待機] ${C} が healthy (正常) になるまで待ちます..."
  while :; do
    S="$(docker inspect --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}' "${C}" 2>&1)"
    case "${S}" in
      running:healthy) echo "[OK] ${C} は healthy です"; break ;;
      running:starting|restarting:*) sleep 2 ;;
      *) echo "[NG] ${C} の状態は ${S} です。docker logs ${C} で原因を確認してください"; break ;;
    esac
  done
done
```

確認: `docker ps --filter name=sample-shop-app-1`

<a id="step-26"></a>

## STEP 26: サービス「web」のコンテナ「sample-shop-web-1」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.web`

イメージ「sample-shop-web:with-healthcheck」からコンテナ「sample-shop-web-1」を作って起動します (サービス「web」)。

```bash
docker run \
  --detach \
  --name sample-shop-web-1 \
  --restart always \
  --network sample-shop_frontend \
  --network-alias web \
  --publish 8088:80 \
  --volume /opt/sample-shop/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
  --tmpfs /var/cache/nginx \
  --tmpfs /var/run \
  --tmpfs /tmp \
  --label com.example.role=frontend \
  --read-only \
  --cap-drop NET_RAW \
  --security-opt no-new-privileges:true \
  --log-driver json-file \
  --log-opt max-file=3 \
  --log-opt max-size=10m \
  --stop-signal SIGQUIT \
  --stop-timeout 15 \
  sample-shop-web:with-healthcheck
```

確認: `docker ps --all --filter name=sample-shop-web-1` ／ `docker logs sample-shop-web-1` ／ `docker inspect sample-shop-web-1`

<a id="step-27"></a>

## STEP 27: 起動したコンテナの状態を確認する

- 区分: **状態確認**

作ったコンテナ (sample-shop-db-1、sample-shop-cache-1、sample-shop-migrate-1、sample-shop-app-1、sample-shop-web-1) が Up (起動中) になっているか、ヘルスチェックの結果 (healthy など) を確認します。

```bash
docker ps \
  --all \
  --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

確認: `docker logs <コンテナ名>` ／ `docker stats --no-stream`

## 後片付け (compose down と同じ)

起動と逆の順番で止めて削除します。ボリューム (データ) とイメージの削除は、必要なときだけ `#` を外して実行します。

### 1. コンテナ「sample-shop-web-1」を止める

コンテナ「sample-shop-web-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-web-1
```

### 2. コンテナ「sample-shop-app-1」を止める

コンテナ「sample-shop-app-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-app-1
```

### 3. コンテナ「sample-shop-migrate-1」を止める

コンテナ「sample-shop-migrate-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-migrate-1
```

### 4. コンテナ「sample-shop-cache-1」を止める

コンテナ「sample-shop-cache-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-cache-1
```

### 5. コンテナ「sample-shop-db-1」を止める

コンテナ「sample-shop-db-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-db-1
```

### 6. コンテナを削除する

止めたコンテナを削除します (compose down と同じ。名前付きボリュームは残ります)。

```bash
docker rm \
  sample-shop-web-1 \
  sample-shop-app-1 \
  sample-shop-migrate-1 \
  sample-shop-cache-1 \
  sample-shop-db-1
```

### 7. ネットワークを削除する

このプロジェクトで作ったネットワークを削除します (compose down と同じ)。

```bash
docker network rm sample-shop_backend sample-shop_frontend
```

### 8. ボリュームを削除する (データが消えます)

名前付きボリュームを削除します (compose down -v と同じ)。データが消えるため、必要なときだけ先頭の # を外して実行してください。

```bash
# docker volume rm sample-shop_app-cache sample-shop_cache-data sample-shop_db-data
```

### 9. 作ったイメージを削除する

ビルドしたイメージ・ヘルスチェック入りイメージを削除します (compose down --rmi local と同じ)。必要なときだけ先頭の # を外して実行してください。

```bash
# docker image rm \
#   sample-shop-cache:with-healthcheck \
#   sample-shop/app:1.0.0 \
#   sample-shop-web:with-healthcheck
```

