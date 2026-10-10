# eap-adot-local を docker コマンドだけで起動する手順

`docker compose up -d` と同じ構成を、`docker` コマンドだけで作るための手順です。STEP 1 から順に、コードブロックの中身をそのままターミナルに貼り付けて実行します。

| 項目 | 内容 |
|---|---|
| プロジェクト名 | `eap-adot-local` |
| 元の compose ファイル | `/opt/Container_Compose_file/compose.yaml` |
| 読み込み方法 | docker compose config (Docker Compose 5.5.1 が解釈した結果) |
| 生成日時 | 2026-10-10 15:06:28 |
| 生成ツール | compose2docker 1.0.0 |
| 実行環境 | RHEL 9.8 + Docker Engine (docker-ce 25 以降 / 推奨 29.x) |
| 起動するコンテナ | `jaeger`、`valkey`、`svf-mock`、`ecs-metadata-mock`、`adot-collector`、`efs-mock`、`batch-mock`、`cloudwatch-logs-mock`、`cwagent`、`sqs`、`pki-init`、`mysql`、`backend`、`frontend`、`alb-healthcheck`、`alb-front`、`secure-api`、`maintenance-lambda`、`alb-lambda-adapter`、`alb`、`lambda`、`lambda-esm`、`ecs-exec` |

## 実行の前に

1. RHEL 9.8 に Docker Engine (docker-ce) が入っていて、`sudo systemctl enable --now docker` で起動済みであること。
2. `root` か、`docker` グループに入っているユーザーで実行すること (`sudo usermod -aG docker <ユーザー名>` の後、ログインし直す)。
3. compose ファイルと、そこから参照されるファイル (Dockerfile・設定ファイル・env ファイルなど) が、同じフォルダ構成で RHEL 上に置かれていること。
4. 2 回目以降は、先に [後片付け](#後片付け-compose-down-と同じ) をしてから実行すること (同じ名前のコンテナやネットワークがあるとエラーになります)。

## 変換時の注意

- services.ecs-exec は Docker の API (docker.sock) を使います。中のプログラムが compose のラベル (com.docker.compose.project / service) でコンテナを探す作りの場合は、--compose-labels を付けて変換してください (compose と同じラベルが付きます)。
- services.cwagent-ssm は profiles (ssm-config) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile ssm-config を付けて変換し直してください。
- services.tls-verifier は profiles (verify) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile verify を付けて変換し直してください。
- services.jmeter は profiles (loadtest) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile loadtest を付けて変換し直してください。

## 手順一覧

| STEP | 区分 | やること | 対象 |
|---:|---|---|---|
| 1 | 準備 | [作業フォルダへ移動し、Docker が使えるか確認する](#step-1) | - |
| 2 | ネットワーク作成 | [ネットワーク「eap-adot-local_default」を作る](#step-2) | `eap-adot-local_default` |
| 3 | ボリューム作成 | [ボリューム「eap-adot-local_mysql-data」を作る](#step-3) | `eap-adot-local_mysql-data` |
| 4 | ボリューム作成 | [ボリューム「eap-adot-local_efs-logs」を作る](#step-4) | `eap-adot-local_efs-logs` |
| 5 | ボリューム作成 | [ボリューム「eap-adot-local_efs-data」を作る](#step-5) | `eap-adot-local_efs-data` |
| 6 | ボリューム作成 | [ボリューム「eap-adot-local_pki」を作る](#step-6) | `eap-adot-local_pki` |
| 7 | イメージ取得 | [イメージ「jaegertracing/jaeger:2.4.0」を用意する](#step-7) | `jaegertracing/jaeger:2.4.0` |
| 8 | イメージ取得 | [イメージ「valkey/valkey:8.0」を用意する](#step-8) | `valkey/valkey:8.0` |
| 9 | イメージ取得 | [イメージ「wiremock/wiremock:3.13.0」を用意する](#step-9) | `wiremock/wiremock:3.13.0` |
| 10 | イメージ取得 | [イメージ「public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3」を用意する](#step-10) | `public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3` |
| 11 | イメージ取得 | [イメージ「alpine:3.21」を用意する](#step-11) | `alpine:3.21` |
| 12 | イメージ取得 | [イメージ「public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest」を用意する](#step-12) | `public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest` |
| 13 | イメージ取得 | [イメージ「softwaremill/elasticmq-native:1.6.11」を用意する](#step-13) | `softwaremill/elasticmq-native:1.6.11` |
| 14 | イメージ取得 | [イメージ「mysql:8.4.7」を用意する](#step-14) | `mysql:8.4.7` |
| 15 | イメージ取得 | [イメージ「python:3.12-slim」を用意する](#step-15) | `python:3.12-slim` |
| 16 | イメージ取得 | [イメージ「public.ecr.aws/lambda/python:3.12」を用意する](#step-16) | `public.ecr.aws/lambda/python:3.12` |
| 17 | イメージ取得 | [イメージ「nginx:1.27-alpine」を用意する](#step-17) | `nginx:1.27-alpine` |
| 18 | イメージ作成 | [サービス「pki-init」のイメージ「eap-adot-local-pki-init」をビルドする](#step-18) | `eap-adot-local-pki-init` |
| 19 | イメージ作成 | [サービス「backend」のイメージ「eap-adot-local-backend」をビルドする](#step-19) | `eap-adot-local-backend` |
| 20 | イメージ作成 | [サービス「frontend」のイメージ「eap-adot-local-frontend」をビルドする](#step-20) | `eap-adot-local-frontend` |
| 21 | イメージ作成 | [サービス「lambda-esm」のイメージ「eap-adot-local-lambda-esm」をビルドする](#step-21) | `eap-adot-local-lambda-esm` |
| 22 | イメージ作成 | [サービス「ecs-exec」のイメージ「eap-adot-local-ecs-exec」をビルドする](#step-22) | `eap-adot-local-ecs-exec` |
| 23 | ヘルスチェック入りイメージ作成 | [サービス「adot-collector」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-adot-collector:with-healthcheck」を作る](#step-23) | `eap-adot-local-adot-collector:with-healthcheck` |
| 24 | ヘルスチェック入りイメージ作成 | [サービス「alb-front」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-alb-front:with-healthcheck」を作る](#step-24) | `eap-adot-local-alb-front:with-healthcheck` |
| 25 | ヘルスチェック入りイメージ作成 | [サービス「ecs-exec」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-ecs-exec:with-healthcheck」を作る](#step-25) | `eap-adot-local-ecs-exec:with-healthcheck` |
| 26 | コンテナ起動 | [サービス「jaeger」のコンテナ「jaeger」を起動する](#step-26) | `jaeger` |
| 27 | コンテナ起動 | [サービス「valkey」のコンテナ「valkey」を起動する](#step-27) | `valkey` |
| 28 | コンテナ起動 | [サービス「svf-mock」のコンテナ「svf-mock」を起動する](#step-28) | `svf-mock` |
| 29 | コンテナ起動 | [サービス「ecs-metadata-mock」のコンテナ「ecs-metadata-mock」を起動する](#step-29) | `ecs-metadata-mock` |
| 30 | 起動待ち | [ecs-metadata-mock が healthy になるまで待つ](#step-30) | `ecs-metadata-mock` |
| 31 | コンテナ起動 | [サービス「adot-collector」のコンテナ「adot-collector」を起動する](#step-31) | `adot-collector` |
| 32 | コンテナ起動 | [サービス「efs-mock」のコンテナ「efs-mock」を起動する](#step-32) | `efs-mock` |
| 33 | 起動待ち | [efs-mock が healthy になるまで待つ](#step-33) | `efs-mock` |
| 34 | コンテナ起動 | [サービス「batch-mock」のコンテナ「batch-mock」を起動する](#step-34) | `batch-mock` |
| 35 | コンテナ起動 | [サービス「cloudwatch-logs-mock」のコンテナ「cloudwatch-logs-mock」を起動する](#step-35) | `cloudwatch-logs-mock` |
| 36 | 起動待ち | [cloudwatch-logs-mock・ecs-metadata-mock・efs-mock が healthy になるまで待つ](#step-36) | `cloudwatch-logs-mock ecs-metadata-mock efs-mock` |
| 37 | コンテナ起動 | [サービス「cwagent」のコンテナ「cwagent」を起動する](#step-37) | `cwagent` |
| 38 | コンテナ起動 | [サービス「sqs」のコンテナ「sqs」を起動する](#step-38) | `sqs` |
| 39 | コンテナ起動 | [サービス「pki-init」のコンテナ「pki-init」を起動する](#step-39) | `pki-init` |
| 40 | 起動待ち | [pki-init が healthy になるまで待つ](#step-40) | `pki-init` |
| 41 | コンテナ起動 | [サービス「mysql」のコンテナ「mysql」を起動する](#step-41) | `mysql` |
| 42 | 起動待ち | [adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・svf-mock・valkey が healthy になるまで待つ](#step-42) | `adot-collector ecs-metadata-mock efs-mock mysql pki-init svf-mock valkey` |
| 43 | コンテナ起動 | [サービス「backend」のコンテナ「backend」を起動する](#step-43) | `backend` |
| 44 | 起動待ち | [adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・valkey が healthy になるまで待つ](#step-44) | `adot-collector ecs-metadata-mock efs-mock mysql pki-init valkey` |
| 45 | コンテナ起動 | [サービス「frontend」のコンテナ「frontend」を起動する](#step-45) | `frontend` |
| 46 | コンテナ起動 | [サービス「alb-healthcheck」のコンテナ「alb-healthcheck」を起動する](#step-46) | `alb-healthcheck` |
| 47 | 起動待ち | [pki-init が healthy になるまで待つ](#step-47) | `pki-init` |
| 48 | コンテナ起動 | [サービス「alb-front」のコンテナ「alb-front」を起動する](#step-48) | `alb-front` |
| 49 | 起動待ち | [pki-init が healthy になるまで待つ](#step-49) | `pki-init` |
| 50 | コンテナ起動 | [サービス「secure-api」のコンテナ「secure-api」を起動する](#step-50) | `secure-api` |
| 51 | コンテナ起動 | [サービス「maintenance-lambda」のコンテナ「maintenance-lambda」を起動する](#step-51) | `maintenance-lambda` |
| 52 | コンテナ起動 | [サービス「alb-lambda-adapter」のコンテナ「alb-lambda-adapter」を起動する](#step-52) | `alb-lambda-adapter` |
| 53 | 起動待ち | [pki-init・secure-api が healthy になるまで待つ](#step-53) | `pki-init secure-api` |
| 54 | コンテナ起動 | [サービス「alb」のコンテナ「alb」を起動する](#step-54) | `alb` |
| 55 | コンテナ起動 | [サービス「lambda」のコンテナ「lambda」を起動する](#step-55) | `lambda` |
| 56 | コンテナ起動 | [サービス「lambda-esm」のコンテナ「lambda-esm」を起動する](#step-56) | `lambda-esm` |
| 57 | コンテナ起動 | [サービス「ecs-exec」のコンテナ「ecs-exec」を起動する](#step-57) | `ecs-exec` |
| 58 | 状態確認 | [起動したコンテナの状態を確認する](#step-58) | - |

<a id="step-1"></a>

## STEP 1: 作業フォルダへ移動し、Docker が使えるか確認する

- 区分: **準備**

履歴展開 (!) を止めて貼り付け事故を防ぎ、プロジェクトのフォルダへ移動して、docker コマンドとサーバー (dockerd) の両方が動いているかを確かめます。

```bash
set +H
cd /opt/Container_Compose_file
docker version
```

確認: `docker info`

<a id="step-2"></a>

## STEP 2: ネットワーク「eap-adot-local_default」を作る

- 区分: **ネットワーク作成**
- compose の対応箇所: `networks.default`

仮想ネットワーク「eap-adot-local_default」を作ります。つながるコンテナ: jaeger、valkey、svf-mock、ecs-metadata-mock、adot-collector、efs-mock、batch-mock、cloudwatch-logs-mock、cwagent、sqs、pki-init、mysql、backend、frontend、alb-healthcheck、alb-front、secure-api、maintenance-lambda、alb-lambda-adapter、alb、lambda、lambda-esm、ecs-exec。同じネットワークのコンテナどうしは、サービス名で呼び合えます。

```bash
docker network create eap-adot-local_default
```

確認: `docker network ls --filter name=eap-adot-local_default` ／ `docker network inspect eap-adot-local_default`

<a id="step-3"></a>

## STEP 3: ボリューム「eap-adot-local_mysql-data」を作る

- 区分: **ボリューム作成**
- compose の対応箇所: `volumes.mysql-data`

データを保存しておく名前付きボリューム「eap-adot-local_mysql-data」を作ります。使うサービス: mysql。

```bash
docker volume create eap-adot-local_mysql-data
```

確認: `docker volume ls --filter name=eap-adot-local_mysql-data` ／ `docker volume inspect eap-adot-local_mysql-data`

<a id="step-4"></a>

## STEP 4: ボリューム「eap-adot-local_efs-logs」を作る

- 区分: **ボリューム作成**
- compose の対応箇所: `volumes.efs-logs`

データを保存しておく名前付きボリューム「eap-adot-local_efs-logs」を作ります。使うサービス: efs-mock、batch-mock、cwagent、backend、frontend。

```bash
docker volume create eap-adot-local_efs-logs
```

確認: `docker volume ls --filter name=eap-adot-local_efs-logs` ／ `docker volume inspect eap-adot-local_efs-logs`

<a id="step-5"></a>

## STEP 5: ボリューム「eap-adot-local_efs-data」を作る

- 区分: **ボリューム作成**
- compose の対応箇所: `volumes.efs-data`

データを保存しておく名前付きボリューム「eap-adot-local_efs-data」を作ります。使うサービス: efs-mock、batch-mock、backend、frontend。

```bash
docker volume create eap-adot-local_efs-data
```

確認: `docker volume ls --filter name=eap-adot-local_efs-data` ／ `docker volume inspect eap-adot-local_efs-data`

<a id="step-6"></a>

## STEP 6: ボリューム「eap-adot-local_pki」を作る

- 区分: **ボリューム作成**
- compose の対応箇所: `volumes.pki`

データを保存しておく名前付きボリューム「eap-adot-local_pki」を作ります。使うサービス: pki-init、mysql、backend、frontend、alb-front、secure-api、alb。

```bash
docker volume create eap-adot-local_pki
```

確認: `docker volume ls --filter name=eap-adot-local_pki` ／ `docker volume inspect eap-adot-local_pki`

<a id="step-7"></a>

## STEP 7: イメージ「jaegertracing/jaeger:2.4.0」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.jaeger.image`

イメージ「jaegertracing/jaeger:2.4.0」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect jaegertracing/jaeger:2.4.0 > /dev/null 2>&1 || docker pull jaegertracing/jaeger:2.4.0
```

確認: `docker image ls jaegertracing/jaeger:2.4.0`

<a id="step-8"></a>

## STEP 8: イメージ「valkey/valkey:8.0」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.valkey.image`

イメージ「valkey/valkey:8.0」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect valkey/valkey:8.0 > /dev/null 2>&1 || docker pull valkey/valkey:8.0
```

確認: `docker image ls valkey/valkey:8.0`

<a id="step-9"></a>

## STEP 9: イメージ「wiremock/wiremock:3.13.0」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.svf-mock.image`

イメージ「wiremock/wiremock:3.13.0」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect wiremock/wiremock:3.13.0 > /dev/null 2>&1 || docker pull wiremock/wiremock:3.13.0
```

確認: `docker image ls wiremock/wiremock:3.13.0`

<a id="step-10"></a>

## STEP 10: イメージ「public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.adot-collector.image`

イメージ「public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3 > /dev/null 2>&1 || docker pull public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3
```

確認: `docker image ls public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3`

<a id="step-11"></a>

## STEP 11: イメージ「alpine:3.21」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.efs-mock.image`

イメージ「alpine:3.21」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect alpine:3.21 > /dev/null 2>&1 || docker pull alpine:3.21
```

確認: `docker image ls alpine:3.21`

<a id="step-12"></a>

## STEP 12: イメージ「public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.cwagent.image`

イメージ「public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest > /dev/null 2>&1 || docker pull public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest
```

確認: `docker image ls public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest`

<a id="step-13"></a>

## STEP 13: イメージ「softwaremill/elasticmq-native:1.6.11」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.sqs.image`

イメージ「softwaremill/elasticmq-native:1.6.11」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect softwaremill/elasticmq-native:1.6.11 > /dev/null 2>&1 || docker pull softwaremill/elasticmq-native:1.6.11
```

確認: `docker image ls softwaremill/elasticmq-native:1.6.11`

<a id="step-14"></a>

## STEP 14: イメージ「mysql:8.4.7」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.mysql.image`

イメージ「mysql:8.4.7」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect mysql:8.4.7 > /dev/null 2>&1 || docker pull mysql:8.4.7
```

確認: `docker image ls mysql:8.4.7`

<a id="step-15"></a>

## STEP 15: イメージ「python:3.12-slim」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.alb-healthcheck.image`

イメージ「python:3.12-slim」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect python:3.12-slim > /dev/null 2>&1 || docker pull python:3.12-slim
```

確認: `docker image ls python:3.12-slim`

<a id="step-16"></a>

## STEP 16: イメージ「public.ecr.aws/lambda/python:3.12」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.maintenance-lambda.image`

イメージ「public.ecr.aws/lambda/python:3.12」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect public.ecr.aws/lambda/python:3.12 > /dev/null 2>&1 || docker pull public.ecr.aws/lambda/python:3.12
```

確認: `docker image ls public.ecr.aws/lambda/python:3.12`

<a id="step-17"></a>

## STEP 17: イメージ「nginx:1.27-alpine」を用意する

- 区分: **イメージ取得**
- compose の対応箇所: `services.alb.image`

イメージ「nginx:1.27-alpine」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

```bash
docker image inspect nginx:1.27-alpine > /dev/null 2>&1 || docker pull nginx:1.27-alpine
```

確認: `docker image ls nginx:1.27-alpine`

<a id="step-18"></a>

## STEP 18: サービス「pki-init」のイメージ「eap-adot-local-pki-init」をビルドする

- 区分: **イメージ作成**
- compose の対応箇所: `services.pki-init.build`

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-pki-init」を作ります。

```bash
docker build \
  --tag eap-adot-local-pki-init \
  /opt/Container_Compose_file/compose/pki
```

確認: `docker image ls eap-adot-local-pki-init` ／ `docker image inspect eap-adot-local-pki-init`

<a id="step-19"></a>

## STEP 19: サービス「backend」のイメージ「eap-adot-local-backend」をビルドする

- 区分: **イメージ作成**
- compose の対応箇所: `services.backend.build`

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-backend」を作ります。

```bash
docker build \
  --file /opt/Container_Compose_file/docker/back/Dockerfile \
  --build-arg EAP_BASE_IMAGE=your-registry.example.com/base/eap81-openjdk21-ubi9:latest \
  --tag eap-adot-local-backend \
  /opt/Container_Compose_file/docker
```

確認: `docker image ls eap-adot-local-backend` ／ `docker image inspect eap-adot-local-backend`

<a id="step-20"></a>

## STEP 20: サービス「frontend」のイメージ「eap-adot-local-frontend」をビルドする

- 区分: **イメージ作成**
- compose の対応箇所: `services.frontend.build`

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-frontend」を作ります。

```bash
docker build \
  --file /opt/Container_Compose_file/docker/front/Dockerfile \
  --build-arg EAP_BASE_IMAGE=your-registry.example.com/base/eap81-openjdk21-ubi9:latest \
  --tag eap-adot-local-frontend \
  /opt/Container_Compose_file/docker
```

確認: `docker image ls eap-adot-local-frontend` ／ `docker image inspect eap-adot-local-frontend`

<a id="step-21"></a>

## STEP 21: サービス「lambda-esm」のイメージ「eap-adot-local-lambda-esm」をビルドする

- 区分: **イメージ作成**
- compose の対応箇所: `services.lambda-esm.build`

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-lambda-esm」を作ります。

```bash
docker build \
  --tag eap-adot-local-lambda-esm \
  /opt/Container_Compose_file/compose/lambda-esm
```

確認: `docker image ls eap-adot-local-lambda-esm` ／ `docker image inspect eap-adot-local-lambda-esm`

<a id="step-22"></a>

## STEP 22: サービス「ecs-exec」のイメージ「eap-adot-local-ecs-exec」をビルドする

- 区分: **イメージ作成**
- compose の対応箇所: `services.ecs-exec.build`

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-ecs-exec」を作ります。

```bash
docker build \
  --tag eap-adot-local-ecs-exec \
  /opt/Container_Compose_file/compose/ecs-exec
```

確認: `docker image ls eap-adot-local-ecs-exec` ／ `docker image inspect eap-adot-local-ecs-exec`

<a id="step-23"></a>

## STEP 23: サービス「adot-collector」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-adot-collector:with-healthcheck」を作る

- 区分: **ヘルスチェック入りイメージ作成**
- compose の対応箇所: `services.adot-collector.healthcheck`

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

```bash
docker build --tag eap-adot-local-adot-collector:with-healthcheck - <<'C2D_DOCKERFILE'
FROM public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 CMD ["/healthcheck"]
C2D_DOCKERFILE
```

確認: `docker image inspect --format '{{json .Config.Healthcheck}}' eap-adot-local-adot-collector:with-healthcheck`

<a id="step-24"></a>

## STEP 24: サービス「alb-front」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-alb-front:with-healthcheck」を作る

- 区分: **ヘルスチェック入りイメージ作成**
- compose の対応箇所: `services.alb-front.healthcheck`

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

```bash
docker build --tag eap-adot-local-alb-front:with-healthcheck - <<'C2D_DOCKERFILE'
FROM python:3.12-slim
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 CMD ["python3", "/opt/alb-front/alb-front.py", "ready"]
C2D_DOCKERFILE
```

確認: `docker image inspect --format '{{json .Config.Healthcheck}}' eap-adot-local-alb-front:with-healthcheck`

<a id="step-25"></a>

## STEP 25: サービス「ecs-exec」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-ecs-exec:with-healthcheck」を作る

- 区分: **ヘルスチェック入りイメージ作成**
- compose の対応箇所: `services.ecs-exec.healthcheck`

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

```bash
docker build --tag eap-adot-local-ecs-exec:with-healthcheck - <<'C2D_DOCKERFILE'
FROM eap-adot-local-ecs-exec
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD ["ecs-exec", "doctor", "--self-only", "--quiet"]
C2D_DOCKERFILE
```

確認: `docker image inspect --format '{{json .Config.Healthcheck}}' eap-adot-local-ecs-exec:with-healthcheck`

<a id="step-26"></a>

## STEP 26: サービス「jaeger」のコンテナ「jaeger」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.jaeger`

イメージ「jaegertracing/jaeger:2.4.0」からコンテナ「jaeger」を作って起動します (サービス「jaeger」)。

```bash
docker run \
  --detach \
  --name jaeger \
  --network eap-adot-local_default \
  --network-alias jaeger \
  --publish 16686:16686 \
  jaegertracing/jaeger:2.4.0
```

確認: `docker ps --all --filter name=jaeger` ／ `docker logs jaeger` ／ `docker inspect jaeger`

<a id="step-27"></a>

## STEP 27: サービス「valkey」のコンテナ「valkey」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.valkey`

イメージ「valkey/valkey:8.0」からコンテナ「valkey」を作って起動します (サービス「valkey」)。

```bash
docker run \
  --detach \
  --name valkey \
  --network eap-adot-local_default \
  --network-alias valkey \
  --publish 6379:6379 \
  --health-cmd 'valkey-cli ping | grep -q PONG' \
  --health-interval 3s \
  --health-timeout 3s \
  --health-start-period 3s \
  --health-retries 20 \
  valkey/valkey:8.0
```

確認: `docker ps --all --filter name=valkey` ／ `docker logs valkey` ／ `docker inspect valkey`

<a id="step-28"></a>

## STEP 28: サービス「svf-mock」のコンテナ「svf-mock」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.svf-mock`

イメージ「wiremock/wiremock:3.13.0」からコンテナ「svf-mock」を作って起動します (サービス「svf-mock」)。

```bash
docker run \
  --detach \
  --name svf-mock \
  --network eap-adot-local_default \
  --network-alias svf-mock \
  --publish 8280:8080 \
  --volume /opt/Container_Compose_file/compose/svf-mock/mappings:/home/wiremock/mappings:ro \
  --health-cmd "timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' || exit 1" \
  --health-interval 3s \
  --health-timeout 3s \
  --health-start-period 5s \
  --health-retries 40 \
  wiremock/wiremock:3.13.0
```

確認: `docker ps --all --filter name=svf-mock` ／ `docker logs svf-mock` ／ `docker inspect svf-mock`

<a id="step-29"></a>

## STEP 29: サービス「ecs-metadata-mock」のコンテナ「ecs-metadata-mock」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.ecs-metadata-mock`

イメージ「wiremock/wiremock:3.13.0」からコンテナ「ecs-metadata-mock」を作って起動します (サービス「ecs-metadata-mock」)。

```bash
docker run \
  --detach \
  --name ecs-metadata-mock \
  --network eap-adot-local_default \
  --network-alias ecs-metadata-mock \
  --publish 8380:8080 \
  --volume /opt/Container_Compose_file/compose/ecs-metadata-mock/mappings:/home/wiremock/mappings:ro \
  --health-cmd "timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' || exit 1" \
  --health-interval 3s \
  --health-timeout 3s \
  --health-start-period 5s \
  --health-retries 40 \
  wiremock/wiremock:3.13.0
```

確認: `docker ps --all --filter name=ecs-metadata-mock` ／ `docker logs ecs-metadata-mock` ／ `docker inspect ecs-metadata-mock`

<a id="step-30"></a>

## STEP 30: ecs-metadata-mock が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.adot-collector.depends_on`

サービス「adot-collector」は depends_on で ecs-metadata-mock が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in ecs-metadata-mock; do
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

確認: `docker ps --filter name=ecs-metadata-mock`

<a id="step-31"></a>

## STEP 31: サービス「adot-collector」のコンテナ「adot-collector」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.adot-collector`

イメージ「eap-adot-local-adot-collector:with-healthcheck」からコンテナ「adot-collector」を作って起動します (サービス「adot-collector」)。

```bash
docker run \
  --detach \
  --name adot-collector \
  --network eap-adot-local_default \
  --network-alias adot-collector \
  --publish 4318:4318 \
  --volume /opt/Container_Compose_file/compose/otel/adot-collector-local.yaml:/etc/otel/config.yaml:ro \
  --env ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-3456789012 \
  eap-adot-local-adot-collector:with-healthcheck \
  --config=/etc/otel/config.yaml
```

確認: `docker ps --all --filter name=adot-collector` ／ `docker logs adot-collector` ／ `docker inspect adot-collector`

<a id="step-32"></a>

## STEP 32: サービス「efs-mock」のコンテナ「efs-mock」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.efs-mock`

イメージ「alpine:3.21」からコンテナ「efs-mock」を作って起動します (サービス「efs-mock」)。

```bash
docker run \
  --detach \
  --name efs-mock \
  --network eap-adot-local_default \
  --network-alias efs-mock \
  --volume eap-adot-local_efs-logs:/mnt/efs/logs \
  --volume eap-adot-local_efs-data:/mnt/efs/data \
  --health-cmd 'test -f /tmp/efs-initialized && [ "$(stat -c %u:%g /mnt/efs/logs)" = "6301:6302" ] && [ "$(stat -c %u:%g /mnt/efs/data)" = "6301:6302" ]' \
  --health-interval 5s \
  --health-timeout 3s \
  --health-start-period 3s \
  --health-retries 5 \
  alpine:3.21 \
  sh \
  -euc \
  $'chown 6301:6302 /mnt/efs/logs /mnt/efs/data\nchmod 2775 /mnt/efs/logs /mnt/efs/data\necho "[efs-mock] initialized /mnt/efs/logs /mnt/efs/data (owner=6301:6302 mode=2775)"\ntouch /tmp/efs-initialized\nexec tail -f /dev/null\n'
```

確認: `docker ps --all --filter name=efs-mock` ／ `docker logs efs-mock` ／ `docker inspect efs-mock`

<a id="step-33"></a>

## STEP 33: efs-mock が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.batch-mock.depends_on`

サービス「batch-mock」は depends_on で efs-mock が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in efs-mock; do
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

確認: `docker ps --filter name=efs-mock`

<a id="step-34"></a>

## STEP 34: サービス「batch-mock」のコンテナ「batch-mock」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.batch-mock`

イメージ「alpine:3.21」からコンテナ「batch-mock」を作って起動します (サービス「batch-mock」)。

```bash
docker run \
  --detach \
  --name batch-mock \
  --user 6301:6302 \
  --network eap-adot-local_default \
  --network-alias batch-mock \
  --volume /opt/Container_Compose_file/compose/batch-mock/efs-propagation.sh:/opt/batch-mock/efs-propagation.sh:ro \
  --volume eap-adot-local_efs-logs:/mnt/logs \
  --volume eap-adot-local_efs-data:/mnt/data \
  --env BATCH_MOCK_CLI=/opt/batch-mock/efs-propagation.sh \
  --env 'BATCH_MOCK_EFS_DIRS=/mnt/logs /mnt/data' \
  --health-cmd '/bin/sh /opt/batch-mock/efs-propagation.sh ready || exit 1' \
  --health-interval 10s \
  --health-timeout 5s \
  --health-start-period 5s \
  --health-retries 5 \
  alpine:3.21 \
  sh -euc $'/bin/sh /opt/batch-mock/efs-propagation.sh init\nexec tail -f /dev/null\n'
```

確認: `docker ps --all --filter name=batch-mock` ／ `docker logs batch-mock` ／ `docker inspect batch-mock`

<a id="step-35"></a>

## STEP 35: サービス「cloudwatch-logs-mock」のコンテナ「cloudwatch-logs-mock」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.cloudwatch-logs-mock`

イメージ「wiremock/wiremock:3.13.0」からコンテナ「cloudwatch-logs-mock」を作って起動します (サービス「cloudwatch-logs-mock」)。

```bash
docker run \
  --detach \
  --name cloudwatch-logs-mock \
  --network eap-adot-local_default \
  --network-alias cloudwatch-logs-mock \
  --publish 8480:8080 \
  --volume /opt/Container_Compose_file/compose/cloudwatch-logs-mock/mappings:/home/wiremock/mappings:ro \
  --health-cmd "timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' || exit 1" \
  --health-interval 3s \
  --health-timeout 3s \
  --health-start-period 5s \
  --health-retries 40 \
  wiremock/wiremock:3.13.0
```

確認: `docker ps --all --filter name=cloudwatch-logs-mock` ／ `docker logs cloudwatch-logs-mock` ／ `docker inspect cloudwatch-logs-mock`

<a id="step-36"></a>

## STEP 36: cloudwatch-logs-mock・ecs-metadata-mock・efs-mock が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.cwagent.depends_on`

サービス「cwagent」は depends_on で cloudwatch-logs-mock・ecs-metadata-mock・efs-mock が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in cloudwatch-logs-mock ecs-metadata-mock efs-mock; do
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

確認: `docker ps --filter name=cloudwatch-logs-mock`

<a id="step-37"></a>

## STEP 37: サービス「cwagent」のコンテナ「cwagent」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.cwagent`

イメージ「public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest」からコンテナ「cwagent」を作って起動します (サービス「cwagent」)。

> ※ compose で entrypoint を指定すると、イメージの CMD は使われません (docker run --entrypoint も同じ)。

```bash
docker run \
  --detach \
  --name cwagent \
  --group-add 6302 \
  --network eap-adot-local_default \
  --network-alias cwagent \
  --volume /opt/Container_Compose_file/compose/cwagent/cwagent-config.json:/etc/cwagentconfig/cwagent-config.json:ro \
  --volume /opt/Container_Compose_file/compose/cwagent/aws-credentials:/root/.aws/credentials:ro \
  --volume /opt/Container_Compose_file/compose/cwagent/verify-mount.sh:/opt/cwagent-verify/verify-mount.sh:ro \
  --volume eap-adot-local_efs-logs:/mnt/logs:ro \
  --env AWS_REGION=ap-northeast-1 \
  --env CWA_VERIFY_CONFIG_DIR=/etc/cwagentconfig \
  --env CWA_VERIFY_EXPECT_MODE=775 \
  --env CWA_VERIFY_EXPECT_OWNER=6301:6302 \
  --env CWA_VERIFY_MOUNTS=/mnt/logs \
  --env CWA_VERIFY_RECHECK_COUNT=5 \
  --env CWA_VERIFY_RECHECK_INTERVAL=20 \
  --env CWA_VERIFY_RELAY_AGENT_LOG=1 \
  --env ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-4567890123 \
  --health-cmd 'read -r v < /tmp/cwagent-verify.boot.result && [ "$v" != FAIL ]' \
  --health-interval 5s \
  --health-timeout 3s \
  --health-start-period 5s \
  --health-retries 12 \
  --entrypoint /bin/sh \
  public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest \
  /opt/cwagent-verify/verify-mount.sh \
  /opt/aws/amazon-cloudwatch-agent/bin/start-amazon-cloudwatch-agent
```

確認: `docker ps --all --filter name=cwagent` ／ `docker logs cwagent` ／ `docker inspect cwagent`

<a id="step-38"></a>

## STEP 38: サービス「sqs」のコンテナ「sqs」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.sqs`

イメージ「softwaremill/elasticmq-native:1.6.11」からコンテナ「sqs」を作って起動します (サービス「sqs」)。

```bash
docker run \
  --detach \
  --name sqs \
  --network eap-adot-local_default \
  --network-alias sqs \
  --publish 9324:9324 \
  --publish 9325:9325 \
  --volume /opt/Container_Compose_file/compose/sqs/elasticmq.conf:/opt/elasticmq.conf:ro \
  softwaremill/elasticmq-native:1.6.11
```

確認: `docker ps --all --filter name=sqs` ／ `docker logs sqs` ／ `docker inspect sqs`

<a id="step-39"></a>

## STEP 39: サービス「pki-init」のコンテナ「pki-init」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.pki-init`

イメージ「eap-adot-local-pki-init」からコンテナ「pki-init」を作って起動します (サービス「pki-init」)。

```bash
docker run \
  --detach \
  --name pki-init \
  --network eap-adot-local_default \
  --network-alias pki-init \
  --volume eap-adot-local_pki:/pki \
  --volume /opt/Container_Compose_file/compose/pki/provided:/provided:ro \
  --volume /opt/Container_Compose_file/compose/pki/export:/export \
  --env 'PKI_CA_CN=Local Test Self-Signed CA' \
  --env PKI_DAYS_CA=3650 \
  --env PKI_DAYS_LEAF=825 \
  --env PKI_EXPORT_DIR=/export \
  --env PKI_EXPORT_KEY=1 \
  --env PKI_FORCE_REGENERATE=0 \
  --env PKI_KEYSTORE_PASSWORD=changeit \
  --env PKI_MODE=auto \
  --env PKI_PROVIDED_DIR=/provided \
  --env PKI_ROOT=/pki \
  --env PKI_TRUST_LOCAL_CA=1 \
  --health-cmd 'test -f /pki/.pki-ready && test -f /pki/ca/cacert.crt && test -f /pki/ca/verify-bundle.crt && test -f /pki/secure-api/server.p12 && test -f /pki/alb/selfsigned/server.key && test -f /pki/alb/ca-issued/server.key && test -f /pki/rds-proxy/server.key && test -f /pki/trust/cacert.crt' \
  --health-interval 3s \
  --health-timeout 3s \
  --health-start-period 2s \
  --health-retries 20 \
  eap-adot-local-pki-init
```

確認: `docker ps --all --filter name=pki-init` ／ `docker logs pki-init` ／ `docker inspect pki-init`

<a id="step-40"></a>

## STEP 40: pki-init が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.mysql.depends_on`

サービス「mysql」は depends_on で pki-init が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in pki-init; do
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

確認: `docker ps --filter name=pki-init`

<a id="step-41"></a>

## STEP 41: サービス「mysql」のコンテナ「mysql」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.mysql`

イメージ「mysql:8.4.7」からコンテナ「mysql」を作って起動します (サービス「mysql」)。

```bash
docker run \
  --detach \
  --name mysql \
  --network eap-adot-local_default \
  --network-alias mysql \
  --publish 3306:3306 \
  --volume /opt/Container_Compose_file/compose/mysql/init.sql:/docker-entrypoint-initdb.d/10-init.sql:ro \
  --volume /opt/Container_Compose_file/compose/mysql/init-infdb.sh:/docker-entrypoint-initdb.d/20-init-infdb.sh:ro \
  --volume eap-adot-local_pki:/mnt/pki:ro \
  --volume eap-adot-local_mysql-data:/var/lib/mysql \
  --env INFDB_PASSWORD=ChangeMe_infdb_P@ss123 \
  --env MYSQL_DATABASE=appdb \
  --env MYSQL_PASSWORD=ChangeMe_appdb_P@ss123 \
  --env MYSQL_ROOT_PASSWORD=localdev-root-change-me \
  --env MYSQL_USER=appuser \
  --health-cmd $'mysql --ssl-mode=REQUIRED -h 127.0.0.1 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -D"$MYSQL_DATABASE" -e \'SELECT 1\' >/dev/null 2>&1' \
  --health-interval 5s \
  --health-timeout 5s \
  --health-start-period 20s \
  --health-retries 60 \
  mysql:8.4.7 \
  --auto_generate_certs=OFF \
  --ssl_cert=/mnt/pki/rds-proxy/fullchain.crt \
  --ssl_key=/mnt/pki/rds-proxy/server.key \
  --ssl_ca=/mnt/pki/ca/verify-bundle.crt \
  --require_secure_transport=ON \
  --tls_version=TLSv1.2,TLSv1.3
```

確認: `docker ps --all --filter name=mysql` ／ `docker logs mysql` ／ `docker inspect mysql`

<a id="step-42"></a>

## STEP 42: adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・svf-mock・valkey が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.backend.depends_on`

サービス「backend」は depends_on で adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・svf-mock・valkey が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in adot-collector ecs-metadata-mock efs-mock mysql pki-init svf-mock valkey; do
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

確認: `docker ps --filter name=adot-collector`

<a id="step-43"></a>

## STEP 43: サービス「backend」のコンテナ「backend」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.backend`

イメージ「eap-adot-local-backend」からコンテナ「backend」を作って起動します (サービス「backend」)。

```bash
docker run \
  --detach \
  --name backend \
  --group-add 6302 \
  --network eap-adot-local_default \
  --network-alias backend \
  --publish 8180:8180 \
  --volume eap-adot-local_efs-logs:/mnt/logs \
  --volume eap-adot-local_efs-data:/mnt/data \
  --volume eap-adot-local_pki:/mnt/pki:ro \
  --env ASYNC_QUEUE_NAME=app-async-queue \
  --env ASYNC_SQS_ENDPOINT=http://sqs:9324 \
  --env AWS_REGION=ap-northeast-1 \
  --env DB_HOST=mysql \
  --env DB_NAME=appdb \
  --env DB_PASSWORD=ChangeMe_appdb_P@ss123 \
  --env DB_PORT=3306 \
  --env DB_SSL_MODE=VERIFY_IDENTITY \
  --env DB_USER=appuser \
  --env ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-2345678901 \
  --env JBOSS_TRUSTSTORE_FILE=/opt/server/standalone/configuration/jboss-truststore.p12 \
  --env JBOSS_TRUSTSTORE_PASSWORD=changeit \
  --env OTEL_EXPORTER_OTLP_ENDPOINT=http://adot-collector:4318 \
  --env OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
  --env OTEL_RESOURCE_ATTRIBUTES=service.namespace=myapp,service.version=local,deployment.environment=local,aws.ecs.service.name=local-compose \
  --env OTEL_SERVICE_NAME=myapp-back \
  --env OTEL_TRACES_SAMPLER=parentbased_always_on \
  --env PKI_TRUST_DIR=/mnt/pki/trust \
  --env PORT_OFFSET=100 \
  --env SECURE_API_URL=https://secure-api:8443/api/v1/ping \
  --env SECURE_API_VIA_ALB_URL=https://alb/secure/v1/ping \
  --env SVF_BASE_URL=http://svf-mock:8080 \
  --env TX_NODE_ID=back-local-1 \
  --env VALKEY_HOST=valkey \
  --env VALKEY_PORT=6379 \
  --health-cmd 'curl -fs http://127.0.0.1:8180/ >/dev/null || exit 1' \
  --health-interval 30s \
  --health-timeout 5s \
  --health-start-period 2m0s \
  --health-retries 3 \
  eap-adot-local-backend
```

確認: `docker ps --all --filter name=backend` ／ `docker logs backend` ／ `docker inspect backend`

<a id="step-44"></a>

## STEP 44: adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・valkey が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.frontend.depends_on`

サービス「frontend」は depends_on で adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・valkey が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in adot-collector ecs-metadata-mock efs-mock mysql pki-init valkey; do
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

確認: `docker ps --filter name=adot-collector`

<a id="step-45"></a>

## STEP 45: サービス「frontend」のコンテナ「frontend」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.frontend`

イメージ「eap-adot-local-frontend」からコンテナ「frontend」を作って起動します (サービス「frontend」)。

```bash
docker run \
  --detach \
  --name frontend \
  --group-add 6302 \
  --network eap-adot-local_default \
  --network-alias frontend \
  --publish 8080:8080 \
  --volume eap-adot-local_efs-logs:/mnt/logs \
  --volume eap-adot-local_efs-data:/mnt/data \
  --volume eap-adot-local_pki:/mnt/pki:ro \
  --env ASYNC_QUEUE_NAME=app-async-queue \
  --env ASYNC_SQS_ENDPOINT=http://sqs:9324 \
  --env AWS_REGION=ap-northeast-1 \
  --env BACK_BASE_URL=http://backend:8180 \
  --env DB_HOST=mysql \
  --env DB_NAME=appdb \
  --env DB_PASSWORD=ChangeMe_appdb_P@ss123 \
  --env DB_PORT=3306 \
  --env DB_SSL_MODE=VERIFY_IDENTITY \
  --env DB_USER=appuser \
  --env ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-1234567890 \
  --env JBOSS_TRUSTSTORE_FILE=/opt/server/standalone/configuration/jboss-truststore.p12 \
  --env JBOSS_TRUSTSTORE_PASSWORD=changeit \
  --env OTEL_EXPORTER_OTLP_ENDPOINT=http://adot-collector:4318 \
  --env OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
  --env OTEL_RESOURCE_ATTRIBUTES=service.namespace=myapp,service.version=local,deployment.environment=local,aws.ecs.service.name=local-compose \
  --env OTEL_SERVICE_NAME=myapp-front \
  --env OTEL_TRACES_SAMPLER=parentbased_always_on \
  --env PKI_TRUST_DIR=/mnt/pki/trust \
  --env SECURE_API_URL=https://secure-api:8443/api/v1/ping \
  --env SECURE_API_VIA_ALB_URL=https://alb/secure/v1/ping \
  --env TX_NODE_ID=front-local-1 \
  --env VALKEY_HOST=valkey \
  --env VALKEY_PORT=6379 \
  --health-cmd 'curl -fs http://127.0.0.1:8080/ >/dev/null || exit 1' \
  --health-interval 30s \
  --health-timeout 5s \
  --health-start-period 2m0s \
  --health-retries 3 \
  eap-adot-local-frontend
```

確認: `docker ps --all --filter name=frontend` ／ `docker logs frontend` ／ `docker inspect frontend`

<a id="step-46"></a>

## STEP 46: サービス「alb-healthcheck」のコンテナ「alb-healthcheck」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.alb-healthcheck`

イメージ「python:3.12-slim」からコンテナ「alb-healthcheck」を作って起動します (サービス「alb-healthcheck」)。

```bash
docker run \
  --detach \
  --name alb-healthcheck \
  --network eap-adot-local_default \
  --network-alias alb-healthcheck \
  --publish 8580:8080 \
  --volume /opt/Container_Compose_file/compose/alb-healthcheck/healthcheck.py:/opt/alb-healthcheck/healthcheck.py:ro \
  --volume /opt/Container_Compose_file/compose/alb-healthcheck/targets.json:/etc/alb-healthcheck/targets.json:ro \
  --env ALB_HEALTHCHECK_CLI=/opt/alb-healthcheck/healthcheck.py \
  --env ALB_HEALTHCHECK_HISTORY_LIMIT=10 \
  --env ALB_HEALTHCHECK_LISTEN_PORT=8080 \
  --env ALB_HEALTHCHECK_TARGETS_FILE=/etc/alb-healthcheck/targets.json \
  --env PYTHONUNBUFFERED=1 \
  --health-cmd 'python3 /opt/alb-healthcheck/healthcheck.py ready || exit 1' \
  --health-interval 10s \
  --health-timeout 5s \
  --health-start-period 5s \
  --health-retries 5 \
  python:3.12-slim \
  python3 /opt/alb-healthcheck/healthcheck.py serve
```

確認: `docker ps --all --filter name=alb-healthcheck` ／ `docker logs alb-healthcheck` ／ `docker inspect alb-healthcheck`

<a id="step-47"></a>

## STEP 47: pki-init が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.alb-front.depends_on`

サービス「alb-front」は depends_on で pki-init が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in pki-init; do
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

確認: `docker ps --filter name=pki-init`

<a id="step-48"></a>

## STEP 48: サービス「alb-front」のコンテナ「alb-front」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.alb-front`

イメージ「eap-adot-local-alb-front:with-healthcheck」からコンテナ「alb-front」を作って起動します (サービス「alb-front」)。

```bash
docker run \
  --detach \
  --name alb-front \
  --network eap-adot-local_default \
  --network-alias alb-front \
  --publish 8443:8443 \
  --publish 8581:8081 \
  --volume /opt/Container_Compose_file/compose/alb-front/alb-front.py:/opt/alb-front/alb-front.py:ro \
  --volume eap-adot-local_pki:/pki:ro \
  --env ALB_FRONT_ADMIN_PORT=8081 \
  --env ALB_FRONT_CA_BUNDLE=/pki/ca/verify-bundle.crt \
  --env ALB_FRONT_CHECK_HOST=localhost \
  --env ALB_FRONT_CHECK_PATH=/iwinmichl/api/redirect-check/redirect \
  --env ALB_FRONT_CLI=/opt/alb-front/alb-front.py \
  --env ALB_FRONT_CONNECT_TIMEOUT=10 \
  --env ALB_FRONT_HTTPS_PORT=8443 \
  --env ALB_FRONT_IDLE_TIMEOUT=60 \
  --env ALB_FRONT_TARGET=http://frontend:8080 \
  --env ALB_FRONT_TLS_CERT=/pki/alb/ca-issued/fullchain.crt \
  --env ALB_FRONT_TLS_KEY=/pki/alb/ca-issued/server.key \
  --env PYTHONUNBUFFERED=1 \
  eap-adot-local-alb-front:with-healthcheck \
  python3 /opt/alb-front/alb-front.py serve
```

確認: `docker ps --all --filter name=alb-front` ／ `docker logs alb-front` ／ `docker inspect alb-front`

<a id="step-49"></a>

## STEP 49: pki-init が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.secure-api.depends_on`

サービス「secure-api」は depends_on で pki-init が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in pki-init; do
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

確認: `docker ps --filter name=pki-init`

<a id="step-50"></a>

## STEP 50: サービス「secure-api」のコンテナ「secure-api」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.secure-api`

イメージ「wiremock/wiremock:3.13.0」からコンテナ「secure-api」を作って起動します (サービス「secure-api」)。

```bash
docker run \
  --detach \
  --name secure-api \
  --network eap-adot-local_default \
  --network-alias secure-api \
  --publish 8543:8443 \
  --volume /opt/Container_Compose_file/compose/secure-api/mappings:/home/wiremock/mappings:ro \
  --volume eap-adot-local_pki:/pki:ro \
  --health-cmd "timeout 2 bash -c '</dev/tcp/127.0.0.1/8443' || exit 1" \
  --health-interval 3s \
  --health-timeout 3s \
  --health-start-period 5s \
  --health-retries 40 \
  wiremock/wiremock:3.13.0 \
  --https-port=8443 \
  --https-keystore=/pki/secure-api/server.p12 \
  --keystore-type=PKCS12 \
  --keystore-password=changeit \
  --key-manager-password=changeit \
  --disable-http \
  --verbose
```

確認: `docker ps --all --filter name=secure-api` ／ `docker logs secure-api` ／ `docker inspect secure-api`

<a id="step-51"></a>

## STEP 51: サービス「maintenance-lambda」のコンテナ「maintenance-lambda」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.maintenance-lambda`

イメージ「public.ecr.aws/lambda/python:3.12」からコンテナ「maintenance-lambda」を作って起動します (サービス「maintenance-lambda」)。

```bash
docker run \
  --detach \
  --name maintenance-lambda \
  --network eap-adot-local_default \
  --network-alias maintenance-lambda \
  --publish 9001:8080 \
  --volume /opt/Container_Compose_file/compose/maintenance-lambda/app:/var/task:ro \
  --env MAINTENANCE_STATUS_CODE=503 \
  --env MAINTENANCE_UNTIL= \
  --env RETRY_AFTER_SECONDS=300 \
  public.ecr.aws/lambda/python:3.12 \
  maintenance.lambda_handler
```

確認: `docker ps --all --filter name=maintenance-lambda` ／ `docker logs maintenance-lambda` ／ `docker inspect maintenance-lambda`

<a id="step-52"></a>

## STEP 52: サービス「alb-lambda-adapter」のコンテナ「alb-lambda-adapter」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.alb-lambda-adapter`

イメージ「python:3.12-slim」からコンテナ「alb-lambda-adapter」を作って起動します (サービス「alb-lambda-adapter」)。

```bash
docker run \
  --detach \
  --name alb-lambda-adapter \
  --network eap-adot-local_default \
  --network-alias alb-lambda-adapter \
  --publish 9081:8080 \
  --volume /opt/Container_Compose_file/compose/alb-lambda-adapter/adapter.py:/app/adapter.py:ro \
  --env LAMBDA_INVOKE_URL=http://maintenance-lambda:8080/2015-03-31/functions/function/invocations \
  --env LISTEN_PORT=8080 \
  python:3.12-slim \
  python /app/adapter.py
```

確認: `docker ps --all --filter name=alb-lambda-adapter` ／ `docker logs alb-lambda-adapter` ／ `docker inspect alb-lambda-adapter`

<a id="step-53"></a>

## STEP 53: pki-init・secure-api が healthy になるまで待つ

- 区分: **起動待ち**
- compose の対応箇所: `services.alb.depends_on`

サービス「alb」は depends_on で pki-init・secure-api が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

> ※ NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

```bash
for C in pki-init secure-api; do
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

確認: `docker ps --filter name=pki-init`

<a id="step-54"></a>

## STEP 54: サービス「alb」のコンテナ「alb」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.alb`

イメージ「nginx:1.27-alpine」からコンテナ「alb」を作って起動します (サービス「alb」)。

```bash
docker run \
  --detach \
  --name alb \
  --network eap-adot-local_default \
  --network-alias alb \
  --publish 9080:80 \
  --publish 9443:443 \
  --volume /opt/Container_Compose_file/compose/alb/nginx.conf:/etc/nginx/nginx.conf:ro \
  --volume /opt/Container_Compose_file/compose/alb/rules:/etc/nginx/rules:ro \
  --volume /opt/Container_Compose_file/compose/alb/rules-tls:/etc/nginx/rules-tls:ro \
  --volume /opt/Container_Compose_file/compose/alb/tls:/etc/nginx/tls:ro \
  --volume eap-adot-local_pki:/pki:ro \
  --health-cmd 'wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1' \
  --health-interval 10s \
  --health-timeout 5s \
  --health-start-period 5s \
  --health-retries 5 \
  nginx:1.27-alpine
```

確認: `docker ps --all --filter name=alb` ／ `docker logs alb` ／ `docker inspect alb`

<a id="step-55"></a>

## STEP 55: サービス「lambda」のコンテナ「lambda」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.lambda`

イメージ「public.ecr.aws/lambda/python:3.12」からコンテナ「lambda」を作って起動します (サービス「lambda」)。

```bash
docker run \
  --detach \
  --name lambda \
  --network eap-adot-local_default \
  --network-alias lambda \
  --publish 9000:8080 \
  --volume /opt/Container_Compose_file/compose/lambda/app:/var/task:ro \
  --env ALB_ENDPOINT=http://alb:80 \
  --env BACK_PATH=/async/receive \
  --env HTTP_TIMEOUT_SECONDS=10 \
  public.ecr.aws/lambda/python:3.12 \
  handler.lambda_handler
```

確認: `docker ps --all --filter name=lambda` ／ `docker logs lambda` ／ `docker inspect lambda`

<a id="step-56"></a>

## STEP 56: サービス「lambda-esm」のコンテナ「lambda-esm」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.lambda-esm`

イメージ「eap-adot-local-lambda-esm」からコンテナ「lambda-esm」を作って起動します (サービス「lambda-esm」)。

```bash
docker run \
  --detach \
  --name lambda-esm \
  --network eap-adot-local_default \
  --network-alias lambda-esm \
  --env AWS_ACCESS_KEY_ID=local \
  --env AWS_REGION=ap-northeast-1 \
  --env AWS_SECRET_ACCESS_KEY=local \
  --env BATCH_SIZE=10 \
  --env LAMBDA_INVOKE_URL=http://lambda:8080/2015-03-31/functions/function/invocations \
  --env QUEUE_NAME=app-async-queue \
  --env SQS_ENDPOINT=http://sqs:9324 \
  --env WAIT_TIME_SECONDS=20 \
  eap-adot-local-lambda-esm
```

確認: `docker ps --all --filter name=lambda-esm` ／ `docker logs lambda-esm` ／ `docker inspect lambda-esm`

<a id="step-57"></a>

## STEP 57: サービス「ecs-exec」のコンテナ「ecs-exec」を起動する

- 区分: **コンテナ起動**
- compose の対応箇所: `services.ecs-exec`

イメージ「eap-adot-local-ecs-exec:with-healthcheck」からコンテナ「ecs-exec」を作って起動します (サービス「ecs-exec」)。

```bash
docker run \
  --detach \
  --name ecs-exec \
  --network eap-adot-local_default \
  --network-alias ecs-exec \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume /opt/Container_Compose_file/compose/ecs-exec/tasks.json:/etc/ecs-exec/tasks.json:ro \
  --volume /opt/Container_Compose_file/compose/ecs-exec/ecs-exec.py:/opt/ecs-exec/ecs-exec.py:ro \
  --volume /opt/Container_Compose_file/compose/ecs-exec/files:/work \
  --volume /opt/Container_Compose_file/compose/ecs-exec/sessions:/var/log/ecs-exec \
  --env AWS_DEFAULT_REGION=ap-northeast-1 \
  --env AWS_REGION=ap-northeast-1 \
  --env ECS_EXEC_COMPOSE_PROJECT=eap-adot-local \
  --env ECS_EXEC_ENABLED=1 \
  --env ECS_EXEC_FILES_DIR=/work \
  --env ECS_EXEC_PUT_CHUNK_CHARS=16384 \
  --env ECS_EXEC_SESSION_LOG_DIR=/var/log/ecs-exec \
  --env ECS_EXEC_SIMULATE_PLUGIN_MISSING=0 \
  --env ECS_EXEC_STATE_FILE=/var/lib/ecs-exec/state.json \
  --env ECS_EXEC_TASKS_FILE=/etc/ecs-exec/tasks.json \
  eap-adot-local-ecs-exec:with-healthcheck
```

確認: `docker ps --all --filter name=ecs-exec` ／ `docker logs ecs-exec` ／ `docker inspect ecs-exec`

<a id="step-58"></a>

## STEP 58: 起動したコンテナの状態を確認する

- 区分: **状態確認**

作ったコンテナ (jaeger、valkey、svf-mock、ecs-metadata-mock、adot-collector、efs-mock、batch-mock、cloudwatch-logs-mock、cwagent、sqs、pki-init、mysql、backend、frontend、alb-healthcheck、alb-front、secure-api、maintenance-lambda、alb-lambda-adapter、alb、lambda、lambda-esm、ecs-exec) が Up (起動中) になっているか、ヘルスチェックの結果 (healthy など) を確認します。

```bash
docker ps \
  --all \
  --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

確認: `docker logs <コンテナ名>` ／ `docker stats --no-stream`

## 後片付け (compose down と同じ)

起動と逆の順番で止めて削除します。ボリューム (データ) とイメージの削除は、必要なときだけ `#` を外して実行します。

### 1. コンテナ「ecs-exec」を止める

コンテナ「ecs-exec」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop ecs-exec
```

### 2. コンテナ「lambda-esm」を止める

コンテナ「lambda-esm」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop lambda-esm
```

### 3. コンテナ「lambda」を止める

コンテナ「lambda」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop lambda
```

### 4. コンテナ「alb」を止める

コンテナ「alb」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop alb
```

### 5. コンテナ「alb-lambda-adapter」を止める

コンテナ「alb-lambda-adapter」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop alb-lambda-adapter
```

### 6. コンテナ「maintenance-lambda」を止める

コンテナ「maintenance-lambda」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop maintenance-lambda
```

### 7. コンテナ「secure-api」を止める

コンテナ「secure-api」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop secure-api
```

### 8. コンテナ「alb-front」を止める

コンテナ「alb-front」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop alb-front
```

### 9. コンテナ「alb-healthcheck」を止める

コンテナ「alb-healthcheck」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop alb-healthcheck
```

### 10. コンテナ「frontend」を止める

コンテナ「frontend」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop frontend
```

### 11. コンテナ「backend」を止める

コンテナ「backend」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop backend
```

### 12. コンテナ「mysql」を止める

コンテナ「mysql」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop mysql
```

### 13. コンテナ「pki-init」を止める

コンテナ「pki-init」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop pki-init
```

### 14. コンテナ「sqs」を止める

コンテナ「sqs」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sqs
```

### 15. コンテナ「cwagent」を止める

コンテナ「cwagent」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop cwagent
```

### 16. コンテナ「cloudwatch-logs-mock」を止める

コンテナ「cloudwatch-logs-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop cloudwatch-logs-mock
```

### 17. コンテナ「batch-mock」を止める

コンテナ「batch-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop batch-mock
```

### 18. コンテナ「efs-mock」を止める

コンテナ「efs-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop efs-mock
```

### 19. コンテナ「adot-collector」を止める

コンテナ「adot-collector」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop adot-collector
```

### 20. コンテナ「ecs-metadata-mock」を止める

コンテナ「ecs-metadata-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop ecs-metadata-mock
```

### 21. コンテナ「svf-mock」を止める

コンテナ「svf-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop svf-mock
```

### 22. コンテナ「valkey」を止める

コンテナ「valkey」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop valkey
```

### 23. コンテナ「jaeger」を止める

コンテナ「jaeger」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop jaeger
```

### 24. コンテナを削除する

止めたコンテナを削除します (compose down と同じ。名前付きボリュームは残ります)。

```bash
docker rm \
  ecs-exec \
  lambda-esm \
  lambda \
  alb \
  alb-lambda-adapter \
  maintenance-lambda \
  secure-api \
  alb-front \
  alb-healthcheck \
  frontend \
  backend \
  mysql \
  pki-init \
  sqs \
  cwagent \
  cloudwatch-logs-mock \
  batch-mock \
  efs-mock \
  adot-collector \
  ecs-metadata-mock \
  svf-mock \
  valkey \
  jaeger
```

### 25. ネットワークを削除する

このプロジェクトで作ったネットワークを削除します (compose down と同じ)。

```bash
docker network rm eap-adot-local_default
```

### 26. ボリュームを削除する (データが消えます)

名前付きボリュームを削除します (compose down -v と同じ)。データが消えるため、必要なときだけ先頭の # を外して実行してください。

```bash
# docker volume rm \
#   eap-adot-local_pki \
#   eap-adot-local_efs-data \
#   eap-adot-local_efs-logs \
#   eap-adot-local_mysql-data
```

### 27. 作ったイメージを削除する

ビルドしたイメージ・ヘルスチェック入りイメージを削除します (compose down --rmi local と同じ)。必要なときだけ先頭の # を外して実行してください。

```bash
# docker image rm \
#   eap-adot-local-adot-collector:with-healthcheck \
#   eap-adot-local-pki-init \
#   eap-adot-local-backend \
#   eap-adot-local-frontend \
#   eap-adot-local-alb-front:with-healthcheck \
#   eap-adot-local-lambda-esm \
#   eap-adot-local-ecs-exec \
#   eap-adot-local-ecs-exec:with-healthcheck
```

