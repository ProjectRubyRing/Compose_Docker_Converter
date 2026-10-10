# eap-adot-local ― docker コマンド実行手順の詳しい解説

> compose2docker 1.0.0 で自動生成 ／ 生成日時: 2026-10-10 15:06:28 ／ 元の compose: `/opt/Container_Compose_file/compose.yaml`
> 読み込み方法: docker compose config (Docker Compose 5.5.1 が解釈した結果)

実行用のコマンドは `docker-commands.txt` (そのまま貼り付け / bash で実行) と `docker-commands.md` にあります。この資料は、その 1 つ 1 つのコマンドの意味・しくみ・歴史を説明します。

## 目次

1. [はじめに](#1-はじめに)
2. [Docker が動くしくみの全体像](#2-docker-が動くしくみの全体像)
3. [実行の流れ](#3-実行の流れ)
4. [RHEL 9.8 での事前準備](#4-rhel-98-での事前準備)
5. [手順ごとの詳しい解説](#5-手順ごとの詳しい解説)
6. [コマンドの種類ごとの深掘り解説](#6-コマンドの種類ごとの深掘り解説)
7. [compose の設定と docker オプションの対応表](#7-compose-の設定と-docker-オプションの対応表)
8. [用語集](#8-用語集)
9. [歴史年表](#9-歴史年表)
10. [注意点・制限事項](#10-注意点制限事項)
11. [後片付けの手順](#11-後片付けの手順)

## 1. はじめに

### この資料は何？

docker compose は、compose ファイル (compose.yaml) に書かれた「たくさんのコンテナをどう動かすか」という計画書を読み、Docker Engine に 1 つずつ命令を出して、まとめて起動してくれる道具です。この資料は、compose が裏側で出している命令を、人が読める docker コマンドに 1 つずつ書き出したものです。コマンドを上から順に実行すると、docker compose up -d とまったく同じコンテナ・ネットワーク・ボリュームができあがります。

### なぜ docker コマンドに直すの？

① compose を入れられない・使えない環境 (サーバーの運用ルール、最小構成のサーバーなど) でも同じ構成を動かせる。② compose が裏で何をしているかが 1 行ずつ見えるので、トラブルの原因を探しやすい。③ 手順書や作業記録として、どの操作で何が起きるかを説明しやすい (審査・引き継ぎ・教育)。④ ECS のタスク定義や Kubernetes など、ほかの仕組みに移すときに「必要な設定の一覧」として使える。

### どうやって正しさを確かめたの？

このツールは、docker compose (v5.5.1) で起動した環境と、生成した docker コマンドで起動した環境を docker inspect で比べ、環境変数・マウント・ネットワーク別名・ヘルスチェック・再起動ルール・資源の制限などが一致することを確認しながら作っています。compose ファイルの解釈は、docker compose が使える環境では docker compose config (compose 自身の解釈) をそのまま使い、使えない環境では同じ規則を再現した内蔵の解釈を使います。tools/compare_env.py を使うと、あなたの RHEL でも同じ比較ができます。

### 小学生向けに言うと

compose は「遠足のしおり」のようなもので、だれが・いつ・どこへ・何を持って行くかが 1 冊にまとまっています。先生 (compose) は、しおりを見ながらバスの運転手さん (Docker) に「まずこのバスを出して、次にこっち」と 1 つずつお願いしています。この資料は、先生のお願いの言葉を全部書き出したものです。だから、先生がいなくても、書いてあるとおりにお願いすれば同じ遠足ができます。

| 項目 | 内容 |
|---|---|
| プロジェクト名 | `eap-adot-local` |
| サービス | `jaeger`、`valkey`、`svf-mock`、`ecs-metadata-mock`、`adot-collector`、`efs-mock`、`batch-mock`、`cloudwatch-logs-mock`、`cwagent`、`sqs`、`pki-init`、`mysql`、`backend`、`frontend`、`alb-healthcheck`、`alb-front`、`secure-api`、`maintenance-lambda`、`alb-lambda-adapter`、`alb`、`lambda`、`lambda-esm`、`ecs-exec` |
| コンテナ | `jaeger`、`valkey`、`svf-mock`、`ecs-metadata-mock`、`adot-collector`、`efs-mock`、`batch-mock`、`cloudwatch-logs-mock`、`cwagent`、`sqs`、`pki-init`、`mysql`、`backend`、`frontend`、`alb-healthcheck`、`alb-front`、`secure-api`、`maintenance-lambda`、`alb-lambda-adapter`、`alb`、`lambda`、`lambda-esm`、`ecs-exec` |
| 手順の数 | 起動 58 STEP ／ 片付け 27 STEP |

## 2. Docker が動くしくみの全体像

```text
  あなた (ターミナル)
     │ docker run ... (このファイルのコマンド)
     ▼
  docker コマンド (クライアント = リモコン)
     │ HTTP + JSON (Docker Engine API)  ※ /var/run/docker.sock を通る
     ▼
  dockerd (Docker Engine = 管理人さん)  … イメージ / ネットワーク / ボリューム / ログ / ヘルスチェック / 再起動
     │ gRPC
     ▼
  containerd (現場監督) → containerd-shim-runc-v2 → runc (大工さん)
     │ システムコール
     ▼
  Linux カーネル (RHEL 9.8)
     ├ namespace … 見える範囲を分ける (部屋の壁)
     ├ cgroup v2 … 使える量を制限 (ブレーカー)
     ├ overlayfs … イメージの層 + 書き込み層 (透明シートの重ね合わせ)
     └ netfilter … アドレス変換・ポート公開 (建物の受付係)
     ▼
  コンテナ (囲いの中で動く、ふつうのプロセス)
```

【Docker が動くしくみの全体像】  
あなた → docker コマンド (クライアント) → /var/run/docker.sock (UNIX ソケット) → dockerd (Docker Engine) → containerd → containerd-shim-runc-v2 → runc → Linux カーネル (namespace・cgroup・overlayfs・netfilter) → コンテナ (囲いの中で動く、ふつうのプロセス)

・docker コマンド: あなたのお願いを Docker Engine API (HTTP + JSON) の形に変えて送るリモコン。  
・dockerd: イメージ・ネットワーク・ボリューム・ログ・ヘルスチェック・再起動などを管理する本体 (管理人さん)。  
・containerd: コンテナの一生 (作る・動かす・止める) を管理する部品。2017 年に CNCF へ寄贈され、Kubernetes でも使われています。  
・runc: OCI の仕様に沿って、カーネルの機能を組み合わせてコンテナを作る小さなプログラム (大工さん)。  
・docker compose: compose ファイルを読み、docker コマンドと同じ API を順番に呼ぶ道具 (しおりを読む先生)。

compose が up でしていること: ① compose ファイルを読み、変数 ${...} を展開して設定を確定 → ② ネットワークとボリュームを作成 → ③ 必要なイメージを取得・ビルド → ④ depends_on の順番どおりにコンテナを作成・起動 (healthy などの条件を待ち合わせ)。この資料の手順も、まったく同じ順番になっています。

## 3. 実行の流れ

| 順番 | フェーズ | 内容 | この手順での STEP |
|---:|---|---|---|
| 1 | 準備 | 作業フォルダへ移動し、Docker が動いているかを確認します。 | [1](#step-1) |
| 2 | ネットワーク | コンテナどうしが名前で話せる仮想ネットワークを作ります。コンテナより先に必要です。 | [2](#step-2) |
| 3 | ボリューム | データを残しておく保存場所を作ります。コンテナより先に必要です。 | [3](#step-3)、[4](#step-4)、[5](#step-5)、[6](#step-6) |
| 4 | イメージ取得 | 手元に無いイメージだけをダウンロードします (compose の pull_policy: missing と同じ)。 | [7](#step-7)、[8](#step-8)、[9](#step-9)、[10](#step-10)、[11](#step-11)、[12](#step-12)、[13](#step-13)、[14](#step-14)、[15](#step-15)、[16](#step-16)、[17](#step-17) |
| 5 | イメージ作成 | build: があるサービスのイメージを Dockerfile から作ります。 | [18](#step-18)、[19](#step-19)、[20](#step-20)、[21](#step-21)、[22](#step-22) |
| 6 | ヘルスチェック入りイメージ | exec 形式のヘルスチェックを compose と同じにするための派生イメージを作ります (必要なときだけ)。 | [23](#step-23)、[24](#step-24)、[25](#step-25) |
| 7 | 起動 | depends_on の順番どおりにコンテナを起動します。healthy や正常終了を待つ設定があれば、その待ち合わせもします。 | [26](#step-26)、[27](#step-27)、[28](#step-28)、[29](#step-29)、[30](#step-30)、[31](#step-31)、[32](#step-32)、[33](#step-33)、[34](#step-34)、[35](#step-35)、[36](#step-36)、[37](#step-37)、[38](#step-38)、[39](#step-39)、[40](#step-40)、[41](#step-41)、[42](#step-42)、[43](#step-43)、[44](#step-44)、[45](#step-45)、[46](#step-46)、[47](#step-47)、[48](#step-48)、[49](#step-49)、[50](#step-50)、[51](#step-51)、[52](#step-52)、[53](#step-53)、[54](#step-54)、[55](#step-55)、[56](#step-56)、[57](#step-57) |
| 8 | 確認 | 全部のコンテナの状態を一覧で確認します。 | [58](#step-58) |

サービスの起動順 (depends_on などの依存関係を守った順番): `jaeger` → `valkey` → `svf-mock` → `ecs-metadata-mock` → `adot-collector` → `efs-mock` → `batch-mock` → `cloudwatch-logs-mock` → `cwagent` → `sqs` → `pki-init` → `mysql` → `backend` → `frontend` → `alb-healthcheck` → `alb-front` → `secure-api` → `maintenance-lambda` → `alb-lambda-adapter` → `alb` → `lambda` → `lambda-esm` → `ecs-exec`

## 4. RHEL 9.8 での事前準備

### 1. 古い docker / podman を外す

RHEL に最初から入っていることがある podman や runc は、Docker 公式パッケージとぶつかるため先に外します (入っていなければ何も起きません)。

```bash
sudo dnf remove docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine podman runc
```

### 2. Docker のリポジトリを登録する

Docker 社が配っている RHEL 用のパッケージ置き場を、dnf に教えます。

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
```

### 3. Docker Engine を入れる

本体 (docker-ce)、リモコン (docker-ce-cli)、containerd、BuildKit (buildx)、compose をまとめて入れます。GPG 鍵の確認を求められたら、指紋が 060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35 であることを確かめて受け入れます。

```bash
sudo dnf install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 4. 起動して、自動起動を有効にする

Docker Engine を起動し、サーバーの再起動後も自動で動くようにします。hello-world が表示されれば成功です。

```bash
sudo systemctl enable --now docker
sudo docker run --rm hello-world
```

### 5. (任意) sudo なしで使う

docker グループに入ると sudo なしで docker を使えます。ただし root と同じくらい強い権限になるので、入れる人は最小限にします。

```bash
sudo usermod -aG docker $USER
# いったんログアウトしてログインし直す
```

### 6. プロジェクトのファイルを置く

compose ファイルだけでなく、Dockerfile・設定ファイル・env ファイルなど、compose ファイルから参照されているものを同じフォルダ構成で置きます。Windows で編集したファイルは改行コードが CRLF になっていることがあるので、シェルスクリプトは LF にそろえます (dos2unix など)。

```bash
scp -r ./myproject user@rhel-server:/opt/myproject
# または rsync -av ./myproject/ user@rhel-server:/opt/myproject/
```

### 7. (必要なら) プロキシ

イメージのダウンロードは dockerd が行うので、dockerd にプロキシを設定します。

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo vi /etc/systemd/system/docker.service.d/http-proxy.conf
#   [Service]
#   Environment="HTTP_PROXY=http://proxy.example.com:8080" "HTTPS_PROXY=http://proxy.example.com:8080" "NO_PROXY=localhost,127.0.0.1"
sudo systemctl daemon-reload && sudo systemctl restart docker
```

## 5. 手順ごとの詳しい解説

同じ種類のコマンドが 2 回目以降に出てくるときは、しくみ・歴史などの共通の説明を「6. コマンドの種類ごとの深掘り解説」にまとめ、ここではそのステップに固有の内容 (オプションの値の意味など) を中心に説明します。

<a id="step-1"></a>

### STEP 1: 作業フォルダへ移動し、Docker が使えるか確認する

| 項目 | 内容 |
|---|---|
| 区分 | 準備 |
| 使うコマンド | docker version ― Docker が使えるかを確かめる |
| ひとことで | docker コマンド (リモコン) と Docker Engine (本体) の両方が動いているかを確かめます。 |
| compose の対応箇所 | - |

**実行するコマンド**

```bash
set +H
cd /opt/Container_Compose_file
docker version
```

**実行のしかた**

この STEP のかたまりをそのままコピーして、ターミナル (SSH でログインした画面) に貼り付け、Enter を押します。画面に「Client:」と「Server:」の 2 つの欄が表示され、それぞれに Version が出れば成功です。  
・Server の欄で「Cannot connect to the Docker daemon at unix:///var/run/docker.sock」と出たら、Docker Engine が止まっています。sudo systemctl enable --now docker で起動してください。  
・「permission denied while trying to connect to the Docker daemon socket」と出たら、権限が足りません。sudo を付けるか、sudo usermod -aG docker <ユーザー名> を実行してログインし直してください。

**このコマンドがすること**

履歴展開 (!) を止めて貼り付け事故を防ぎ、プロジェクトのフォルダへ移動して、docker コマンドとサーバー (dockerd) の両方が動いているかを確かめます。

- set +H は、bash の「履歴展開」(! で始まる文字を過去のコマンドに置き換える機能) を止めます。コマンドの中に ! が含まれていても、そのまま貼り付けて実行できるようにするためです。
- cd でプロジェクトのフォルダへ移動します。この後のコマンドは、compose ファイルが置かれていたフォルダを基準にしたパスを使います。
- docker version で「Client」(docker コマンド) と「Server」(Docker Engine = dockerd) の両方のバージョンが表示されれば準備完了です。Server 側がエラーなら sudo systemctl start docker で Docker を起動してください。

**しくみ (動作原理)**

docker コマンドは、それだけではコンテナを動かせません。実際の仕事は Docker Engine (dockerd というサービス) が行い、docker コマンドは dockerd へ「お願い」を送るリモコンです。お願いは HTTP という Web と同じ形式で、/var/run/docker.sock という「UNIX ドメインソケット」(同じコンピューターの中だけで使う電話線のようなファイル) を通して送られます。  
docker version を実行すると、docker コマンドは dockerd に「GET /version」というお願いを送り、dockerd は JSON (データの書き方の一つ) で自分のバージョンを返します。このとき、クライアントとサーバーは「お互いが話せる API バージョン」を確認し合います (API バージョンのネゴシエーション)。Docker Engine 29 (2025 年 11 月) からは、API バージョン 1.44 未満 (Docker 25 より古い docker コマンド) からの接続は受け付けなくなりました。  
さらに裏側では、dockerd → containerd (コンテナの一生を管理する部品) → containerd-shim-runc-v2 → runc (実際にコンテナを作る小さなプログラム) → Linux カーネル、というように仕事がリレーされます。docker version の Server 欄に containerd や runc のバージョンも表示されるのはこのためです。

**動作イメージ (たとえ話)**

テレビのリモコン (docker コマンド) と、テレビ本体 (Docker Engine) の関係です。リモコンのボタンを押しても、本体の電源が入っていなければ何も起きません。docker version は「リモコンの電池は入っているか」「本体の電源は入っているか」「リモコンと本体の電波は届いているか」をまとめて確かめるテストボタンのようなものです。

**歴史と背景・必要になった経緯**

Docker は 2013 年 3 月、dotCloud という会社 (のちの Docker 社) の Solomon Hykes さんが、プログラミング言語 Python の国際会議 PyCon の 5 分間の発表で初めて世に出し、同時にオープンソースとして公開しました。当時は「サーバーごとに環境が違ってアプリが動かない」という悩みが大きく、「アプリと必要なものを丸ごと箱詰めして、どこでも同じように動かす」という考えが一気に広まりました。  
最初の Docker は 1 つのプログラムがリモコンと本体を兼ねていましたが、2016 年に containerd、2015 年に runc が切り出され、業界標準の団体 OCI (Open Container Initiative、2015 年 6 月設立) の仕様に沿う形へ整理されました。バージョンの付け方は 2017 年に「年.月」(17.03 など) になり、2023 年の 23.0 から普通の番号に戻りました。2025 年 11 月の Docker Engine 29.0 では、新しく入れた環境ではイメージの保存に containerd の仕組み (containerd image store) を使うのが標準になり、ファイアウォールの nftables への対応 (試験的)、cgroup v1 の非推奨化などが行われました。2026 年 10 月時点の最新は 29.9 系です。

**RHEL 9.8 での注意**

RHEL 8 以降、Red Hat が標準で用意しているコンテナの道具は Podman (docker と似たコマンドが使える別の製品) です。Docker 社の Docker Engine (docker-ce) は、Docker 社のリポジトリ (https://download.docker.com/linux/rhel/docker-ce.repo) から入れます。公式手順では、先に podman と runc を削除してから docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin を入れ、sudo systemctl enable --now docker で起動・自動起動を有効にします。docker グループに入ったユーザーは root と同じくらいの力を持てるので、グループに入れる人は最小限にしてください。

**小学生向けのまとめ**: コンテナの工場 (Docker) に電話をかけて「もしもし、動いてますか？」と聞くのが docker version です。「はい、動いてます。わたしのバージョンは 29 です」と返事が来たら、工場にお仕事をお願いする準備ができました。

**確認のしかた**: `docker info`

<a id="step-2"></a>

### STEP 2: ネットワーク「eap-adot-local_default」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ネットワーク作成 |
| 使うコマンド | docker network create ― コンテナ専用の仮想ネットワークを作る |
| ひとことで | コンテナどうしが名前で話せる、専用の仮想ネットワーク (ユーザー定義ブリッジ) を作ります。 |
| compose の対応箇所 | `networks.default` |

**実行するコマンド**

```bash
docker network create eap-adot-local_default
```

**実行のしかた**

かたまりをコピーして貼り付け、Enter を押します。成功すると、作られたネットワークの ID (64 文字の英数字) が 1 行表示されます。  
・「network with name ... already exists」と出たら、同じ名前のネットワークが既にあります。前回の分が残っている場合は、後片付けの手順 (docker network rm) を実行してからやり直してください。  
・「Pool overlaps with other one on this address space」と出たら、指定した IP アドレスの範囲 (subnet) が既存のネットワークと重なっています。

**このコマンドがすること**

仮想ネットワーク「eap-adot-local_default」を作ります。つながるコンテナ: jaeger、valkey、svf-mock、ecs-metadata-mock、adot-collector、efs-mock、batch-mock、cloudwatch-logs-mock、cwagent、sqs、pki-init、mysql、backend、frontend、alb-healthcheck、alb-front、secure-api、maintenance-lambda、alb-lambda-adapter、alb、lambda、lambda-esm、ecs-exec。同じネットワークのコンテナどうしは、サービス名で呼び合えます。

- compose ファイルに networks: を書いていないサービスがあるため、compose は自動で「eap-adot-local_default」(既定ネットワーク) を作ります。それを同じ名前で再現します。
- ドライバーを指定していないときは bridge (ホストの中だけの仮想スイッチ) になります。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ネットワーク名)` | `eap-adot-local_default` | networks.default | compose の命名規則「<プロジェクト名>_<ネットワークのキー>」で付けた名前です。 | 作るネットワークの名前です。<br>（やさしく）道路の名前です。 |

**しくみ (動作原理)**

bridge ドライバーの場合、Docker はホストの Linux カーネルに「ブリッジ」(ソフトウェアでできたスイッチングハブ) を作ります。名前は br- の後ろにネットワーク ID の先頭 12 文字が付いたもの (例: br-1a2b3c4d5e6f) で、ip addr で見ることができます。  
次に IPAM (IP Address Management = IP アドレスの割り当て係) が、まだ使われていないアドレスの範囲 (サブネット。例: 172.18.0.0/16) を選び、その最初のアドレス (例: 172.18.0.1) をゲートウェイ (外への出口) としてブリッジに付けます。  
コンテナがこのネットワークにつながるとき、Docker は veth ペア (2 本で 1 組の仮想 LAN ケーブル) を作り、片方をコンテナのネットワーク名前空間 (コンテナ専用のネットワークの世界) に入れて eth0 などの名前にし、もう片方をブリッジに差します。  
外 (インターネットなど) へ出る通信は、ファイアウォールの仕組み (iptables。RHEL 9 では内部で nftables に変換される) のMASQUERADE というルールで、送り主のアドレスがホストのアドレスに書き換えられます。  
名前で呼び合えるのは、Docker が内蔵 DNS サーバーを持っているからです。コンテナの /etc/resolv.conf には 127.0.0.11 が書かれ、ここへの問い合わせを dockerd が受けて、同じネットワークにいるコンテナの名前・別名を IP アドレスに変換して答えます。知らない名前はホスト側の DNS に聞きに行きます。なお、Docker が最初から持っている「bridge」(docker0) ネットワークでは、この名前解決は働きません。compose が必ず自分用のネットワークを作るのはこのためです。  
--internal を付けると外への出口の設定が作られず、ネットワークの中だけで通信できる閉じた LAN になります。

**動作イメージ (たとえ話)**

マンション (ホスト) の中に、住人 (コンテナ) どうしだけで使える「内線電話網」を引くようなものです。ブリッジは電話の交換機、veth は各部屋へつながる電話線、内蔵 DNS は「名前を言えば番号につないでくれる電話帳係」です。外に電話 (インターネット) をかけるときは、マンションの代表番号 (ホストの IP アドレス) からかけたことにしてもらいます (MASQUERADE)。

**歴史と背景・必要になった経緯**

最初の Docker (2013 年) には docker0 という 1 つの共用ネットワークしかなく、コンテナどうしをつなぐには --link という仕組みで、相手の IP アドレスを環境変数や /etc/hosts に書き込むしかありませんでした。相手が再起動して IP が変わると切れてしまうなど、不便な点がありました。  
そこで Docker 社は 2015 年 3 月に SocketPlane という会社を買収してネットワーク部品 (libnetwork) を作り、2015 年 11 月の Docker 1.9 で docker network コマンドと「ユーザーが自由に作れるネットワーク」が登場しました。2016 年 2 月の Docker 1.10 で内蔵 DNS とネットワーク別名 (--network-alias) が加わり、名前で呼び合うのが当たり前になりました。  
compose も 2016 年のファイル形式 v2 から networks: を書けるようになり、プロジェクトごとに専用ネットワーク (<プロジェクト名>_default) を自動で作るようになりました。その後も、Docker 25 (2024 年) で 1 回の docker run で複数ネットワークにつなげるようになり、Docker 28 (2025 年) でデフォルトゲートウェイの優先度 (gw-priority)、Docker 29 (2025 年 11 月) で nftables への試験的な対応が加わっています。

**RHEL 9.8 での注意**

RHEL 9.8 では firewalld が動いていることが多く、Docker は firewalld に docker という zone を作ってブリッジを登録します。firewall-cmd --reload をしたあとにコンテナの通信がおかしくなったら、sudo systemctl restart docker で Docker のルールを入れ直してください。  
社内ネットワークと Docker が選んだサブネット (172.17〜172.31 や 192.168.x.x) が重なると、その範囲の社内サーバーへ届かなくなります。そのときは compose の ipam.config.subnet で範囲を指定するか、/etc/docker/daemon.json の default-address-pools で Docker が使う範囲を変えます。

**小学生向けのまとめ**: コンテナたちのための「専用の道路と電話帳」を作るコマンドです。同じ道路につながったコンテナは、「db さーん」と名前を呼ぶだけで相手のところへ手紙 (データ) を届けられます。

**確認のしかた**: `docker network ls --filter name=eap-adot-local_default` ／ `docker network inspect eap-adot-local_default`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
networks:
  default:
    ipam: {}
    name: eap-adot-local_default
```

</details>

<a id="step-3"></a>

### STEP 3: ボリューム「eap-adot-local_mysql-data」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ボリューム作成 |
| 使うコマンド | docker volume create ― データを残しておくボリュームを作る |
| ひとことで | コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。 |
| compose の対応箇所 | `volumes.mysql-data` |

**実行するコマンド**

```bash
docker volume create eap-adot-local_mysql-data
```

**実行のしかた**

貼り付けて Enter。成功するとボリューム名が 1 行表示されます。同じ名前のボリュームが既にある場合もエラーにはならず、そのまま名前が表示されます (中身はそのまま残っています)。

**このコマンドがすること**

データを保存しておく名前付きボリューム「eap-adot-local_mysql-data」を作ります。使うサービス: mysql。

- コンテナを削除してもボリュームの中身は残ります。消すときは docker volume rm で明示的に消します (compose の down -v と同じ)。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ボリューム名)` | `eap-adot-local_mysql-data` | volumes.mysql-data | compose の命名規則「<プロジェクト名>_<ボリュームのキー>」で付けた名前です。 | 作るボリュームの名前です。<br>（やさしく）ロッカーの名前です。 |

**しくみ (動作原理)**

標準の local ドライバーでは、ホストの /var/lib/docker/volumes/<ボリューム名>/_data というフォルダが作られるだけです。コンテナを起動するとき、Docker はこのフォルダを「バインドマウント」という仕組みで、コンテナの中の指定の場所 (例: /var/lib/mysql) に重ねて見せます。コンテナから見ると普通のフォルダですが、実体はコンテナの外にあるため、コンテナを消しても残ります。  
空のボリュームを初めてつないだときは、イメージのその場所に最初から入っていたファイルがボリュームへコピーされます (コピーアップ)。nocopy を指定するとコピーしません。  
--opt type=nfs,o=addr=...,device=:/export のようにすると、NFS などのネットワーク上の保存場所をボリュームとして使うこともできます (裏では mount コマンドと同じ仕組みが使われます)。

**動作イメージ (たとえ話)**

お部屋 (コンテナ) の外にある「貸しロッカー」です。お部屋を片付けて (コンテナを削除して) も、ロッカーの中身は残っています。次に新しいお部屋を用意したら、同じロッカーの鍵を渡せば、前のデータをそのまま使えます。

**歴史と背景・必要になった経緯**

初期の Docker では、データを残すには -v でホストのフォルダを直接つなぐか、「データ専用コンテナ」を作って --volumes-from で共有する、という工夫が使われていました。2015 年の Docker 1.8 でボリュームプラグイン (外部ストレージとつなぐ仕組み)、2015 年 11 月の Docker 1.9 で docker volume コマンドと名前付きボリュームが登場し、データの置き場所を名前で管理できるようになりました。2017 年の Docker 17.06 で、docker run に読みやすい長い書き方 --mount が追加され、2024 年の Docker 26 ではボリュームの中の一部のフォルダだけをつなぐ volume-subpath が使えるようになりました。compose ではファイル形式 v2 (2016 年) から volumes: でボリュームを定義できます。

**RHEL 9.8 での注意**

ボリュームの実体は /var/lib/docker の下に作られます。RHEL では /var を小さなパーティションに分けていることがあるため、df -h /var/lib/docker で空き容量を確認してください。  
SELinux を有効にした Docker (daemon.json で "selinux-enabled": true) でも、名前付きボリュームには Docker が自動で正しいラベルを付けるので、そのまま使えます。

**小学生向けのまとめ**: コンテナが使う「なくならないロッカー」を用意するコマンドです。コンテナを片付けても、ロッカーの中のデータは残ります。

**確認のしかた**: `docker volume ls --filter name=eap-adot-local_mysql-data` ／ `docker volume inspect eap-adot-local_mysql-data`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
volumes:
  mysql-data:
    name: eap-adot-local_mysql-data
```

</details>

<a id="step-4"></a>

### STEP 4: ボリューム「eap-adot-local_efs-logs」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ボリューム作成 |
| 使うコマンド | docker volume create ― データを残しておくボリュームを作る |
| ひとことで | コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。 |
| compose の対応箇所 | `volumes.efs-logs` |

**実行するコマンド**

```bash
docker volume create eap-adot-local_efs-logs
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 3](#step-3) と同じです)。

**このコマンドがすること**

データを保存しておく名前付きボリューム「eap-adot-local_efs-logs」を作ります。使うサービス: efs-mock、batch-mock、cwagent、backend、frontend。

- コンテナを削除してもボリュームの中身は残ります。消すときは docker volume rm で明示的に消します (compose の down -v と同じ)。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ボリューム名)` | `eap-adot-local_efs-logs` | volumes.efs-logs | compose の命名規則「<プロジェクト名>_<ボリュームのキー>」で付けた名前です。 | 作るボリュームの名前です。<br>（やさしく）ロッカーの名前です。 |

**しくみ・歴史**: STEP 3 と同じ `docker volume create` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-volume-create) を参照してください。

**小学生向けのまとめ**: コンテナが使う「なくならないロッカー」を用意するコマンドです。コンテナを片付けても、ロッカーの中のデータは残ります。

**確認のしかた**: `docker volume ls --filter name=eap-adot-local_efs-logs` ／ `docker volume inspect eap-adot-local_efs-logs`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
volumes:
  efs-logs:
    name: eap-adot-local_efs-logs
```

</details>

<a id="step-5"></a>

### STEP 5: ボリューム「eap-adot-local_efs-data」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ボリューム作成 |
| 使うコマンド | docker volume create ― データを残しておくボリュームを作る |
| ひとことで | コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。 |
| compose の対応箇所 | `volumes.efs-data` |

**実行するコマンド**

```bash
docker volume create eap-adot-local_efs-data
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 3](#step-3) と同じです)。

**このコマンドがすること**

データを保存しておく名前付きボリューム「eap-adot-local_efs-data」を作ります。使うサービス: efs-mock、batch-mock、backend、frontend。

- コンテナを削除してもボリュームの中身は残ります。消すときは docker volume rm で明示的に消します (compose の down -v と同じ)。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ボリューム名)` | `eap-adot-local_efs-data` | volumes.efs-data | compose の命名規則「<プロジェクト名>_<ボリュームのキー>」で付けた名前です。 | 作るボリュームの名前です。<br>（やさしく）ロッカーの名前です。 |

**しくみ・歴史**: STEP 3 と同じ `docker volume create` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-volume-create) を参照してください。

**小学生向けのまとめ**: コンテナが使う「なくならないロッカー」を用意するコマンドです。コンテナを片付けても、ロッカーの中のデータは残ります。

**確認のしかた**: `docker volume ls --filter name=eap-adot-local_efs-data` ／ `docker volume inspect eap-adot-local_efs-data`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
volumes:
  efs-data:
    name: eap-adot-local_efs-data
```

</details>

<a id="step-6"></a>

### STEP 6: ボリューム「eap-adot-local_pki」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ボリューム作成 |
| 使うコマンド | docker volume create ― データを残しておくボリュームを作る |
| ひとことで | コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。 |
| compose の対応箇所 | `volumes.pki` |

**実行するコマンド**

```bash
docker volume create eap-adot-local_pki
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 3](#step-3) と同じです)。

**このコマンドがすること**

データを保存しておく名前付きボリューム「eap-adot-local_pki」を作ります。使うサービス: pki-init、mysql、backend、frontend、alb-front、secure-api、alb。

- コンテナを削除してもボリュームの中身は残ります。消すときは docker volume rm で明示的に消します (compose の down -v と同じ)。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ボリューム名)` | `eap-adot-local_pki` | volumes.pki | compose の命名規則「<プロジェクト名>_<ボリュームのキー>」で付けた名前です。 | 作るボリュームの名前です。<br>（やさしく）ロッカーの名前です。 |

**しくみ・歴史**: STEP 3 と同じ `docker volume create` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-volume-create) を参照してください。

**小学生向けのまとめ**: コンテナが使う「なくならないロッカー」を用意するコマンドです。コンテナを片付けても、ロッカーの中のデータは残ります。

**確認のしかた**: `docker volume ls --filter name=eap-adot-local_pki` ／ `docker volume inspect eap-adot-local_pki`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
volumes:
  pki:
    name: eap-adot-local_pki
```

</details>

<a id="step-7"></a>

### STEP 7: イメージ「jaegertracing/jaeger:2.4.0」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.jaeger.image` |

**実行するコマンド**

```bash
docker image inspect jaegertracing/jaeger:2.4.0 > /dev/null 2>&1 || docker pull jaegertracing/jaeger:2.4.0
```

**実行のしかた**

貼り付けて Enter。手元に既にある場合は何も表示されずに終わります (正常です)。無い場合はダウンロードの進み具合が表示され、最後に「Status: Downloaded newer image for ...」と出れば成功です。  
・「pull access denied」「unauthorized」は、非公開のイメージなので docker login が必要か、名前の間違いです。  
・「toomanyrequests」は Docker Hub のダウンロード回数制限です。時間をおくか、docker login してから実行してください。  
・「dial tcp ... i/o timeout」はインターネットに出られていません (プロキシの設定を確認)。

**このコマンドがすること**

イメージ「jaegertracing/jaeger:2.4.0」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: jaeger

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `jaegertracing/jaeger:2.4.0` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `jaegertracing/jaeger:2.4.0` | services.jaeger.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ (動作原理)**

イメージ名「レジストリ/リポジトリ:タグ」を分解します。レジストリを省略すると docker.io (Docker Hub) が使われ、公式イメージは library/ が補われます (例: mysql:8.4.7 → docker.io/library/mysql:8.4.7)。  
次に、レジストリの API (OCI Distribution Specification) でマニフェスト (イメージがどの層 = レイヤーでできているかの目録) を取り寄せます。いろいろな CPU 向けの版がある「マルチアーキテクチャ」イメージなら、目録の目録 (インデックス) から linux/amd64 などこのサーバーに合うものを選びます。  
レイヤーは、ファイルの差分を tar でまとめて gzip や zstd で圧縮したもので、中身から計算した sha256 の値 (ダイジェスト) で区別されます。同じダイジェストのレイヤーを既に持っていればダウンロードせず、無いものだけを並行してダウンロードし、壊れていないか検証してから展開します。  
Docker Hub には回数制限があり、2026 年 10 月時点の公式ドキュメントでは、ログインしない場合は 6 時間あたり 100 回 (IPv4 アドレス、または IPv6 の /64 ごと)、無料アカウントでログインすると 200 回です。

**動作イメージ (たとえ話)**

インターネットの「部品倉庫」から、お部屋セット (イメージ) を取り寄せます。セットは何枚もの透明なシート (レイヤー) を重ねてできていて、家に同じシートがあればそれを使い回し、足りないシートだけを送ってもらいます。押し入れに同じセットが既にあれば、取り寄せはしません。

**歴史と背景・必要になった経緯**

2013 年の Docker 登場と同時に、イメージを共有する場所 (Docker Index) が作られ、2014 年 6 月の Docker 1.0 と同時に Docker Hub になりました。2015 年の Registry API v2 (Docker 1.6) で、中身のハッシュ値でレイヤーを管理する今の方式になり、同じものを二度送らずに済むようになりました。2017 年に OCI Image Specification 1.0、2021 年に OCI Distribution Specification 1.0 が決まり、Docker 以外のツール (Podman や Kubernetes) とも同じイメージを共有できるようになりました。2020 年 11 月からは Docker Hub に回数制限が導入され、Amazon ECR Public (2020 年 12 月) のような別の公開レジストリも使われるようになりました。

**RHEL 9.8 での注意**

社内でプロキシを使う場合、docker pull を実際に行うのは dockerd なので、dockerd にプロキシを設定します (例: /etc/systemd/system/docker.service.d/http-proxy.conf に Environment="HTTPS_PROXY=http://proxy.example.com:8080" を書き、sudo systemctl daemon-reload && sudo systemctl restart docker)。自己署名証明書の社内レジストリは /etc/docker/certs.d/<レジストリ名>/ca.crt に CA 証明書を置きます。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls jaegertracing/jaeger:2.4.0`

<a id="step-8"></a>

### STEP 8: イメージ「valkey/valkey:8.0」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.valkey.image` |

**実行するコマンド**

```bash
docker image inspect valkey/valkey:8.0 > /dev/null 2>&1 || docker pull valkey/valkey:8.0
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「valkey/valkey:8.0」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: valkey

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `valkey/valkey:8.0` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `valkey/valkey:8.0` | services.valkey.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls valkey/valkey:8.0`

<a id="step-9"></a>

### STEP 9: イメージ「wiremock/wiremock:3.13.0」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.svf-mock.image` |

**実行するコマンド**

```bash
docker image inspect wiremock/wiremock:3.13.0 > /dev/null 2>&1 || docker pull wiremock/wiremock:3.13.0
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「wiremock/wiremock:3.13.0」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: svf-mock、ecs-metadata-mock、cloudwatch-logs-mock、secure-api

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `wiremock/wiremock:3.13.0` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `wiremock/wiremock:3.13.0` | services.svf-mock.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls wiremock/wiremock:3.13.0`

<a id="step-10"></a>

### STEP 10: イメージ「public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.adot-collector.image` |

**実行するコマンド**

```bash
docker image inspect public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3 > /dev/null 2>&1 || docker pull public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: adot-collector

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3` | services.adot-collector.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3`

<a id="step-11"></a>

### STEP 11: イメージ「alpine:3.21」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.efs-mock.image` |

**実行するコマンド**

```bash
docker image inspect alpine:3.21 > /dev/null 2>&1 || docker pull alpine:3.21
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「alpine:3.21」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: efs-mock、batch-mock

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `alpine:3.21` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `alpine:3.21` | services.efs-mock.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls alpine:3.21`

<a id="step-12"></a>

### STEP 12: イメージ「public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.cwagent.image` |

**実行するコマンド**

```bash
docker image inspect public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest > /dev/null 2>&1 || docker pull public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: cwagent

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest` | services.cwagent.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest`

<a id="step-13"></a>

### STEP 13: イメージ「softwaremill/elasticmq-native:1.6.11」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.sqs.image` |

**実行するコマンド**

```bash
docker image inspect softwaremill/elasticmq-native:1.6.11 > /dev/null 2>&1 || docker pull softwaremill/elasticmq-native:1.6.11
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「softwaremill/elasticmq-native:1.6.11」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: sqs

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `softwaremill/elasticmq-native:1.6.11` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `softwaremill/elasticmq-native:1.6.11` | services.sqs.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls softwaremill/elasticmq-native:1.6.11`

<a id="step-14"></a>

### STEP 14: イメージ「mysql:8.4.7」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.mysql.image` |

**実行するコマンド**

```bash
docker image inspect mysql:8.4.7 > /dev/null 2>&1 || docker pull mysql:8.4.7
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「mysql:8.4.7」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: mysql

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `mysql:8.4.7` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `mysql:8.4.7` | services.mysql.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls mysql:8.4.7`

<a id="step-15"></a>

### STEP 15: イメージ「python:3.12-slim」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.alb-healthcheck.image` |

**実行するコマンド**

```bash
docker image inspect python:3.12-slim > /dev/null 2>&1 || docker pull python:3.12-slim
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「python:3.12-slim」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: alb-healthcheck、alb-front、alb-lambda-adapter

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `python:3.12-slim` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `python:3.12-slim` | services.alb-healthcheck.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls python:3.12-slim`

<a id="step-16"></a>

### STEP 16: イメージ「public.ecr.aws/lambda/python:3.12」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.maintenance-lambda.image` |

**実行するコマンド**

```bash
docker image inspect public.ecr.aws/lambda/python:3.12 > /dev/null 2>&1 || docker pull public.ecr.aws/lambda/python:3.12
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「public.ecr.aws/lambda/python:3.12」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: maintenance-lambda、lambda

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `public.ecr.aws/lambda/python:3.12` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `public.ecr.aws/lambda/python:3.12` | services.maintenance-lambda.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls public.ecr.aws/lambda/python:3.12`

<a id="step-17"></a>

### STEP 17: イメージ「nginx:1.27-alpine」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.alb.image` |

**実行するコマンド**

```bash
docker image inspect nginx:1.27-alpine > /dev/null 2>&1 || docker pull nginx:1.27-alpine
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「nginx:1.27-alpine」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: alb

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `nginx:1.27-alpine` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `nginx:1.27-alpine` | services.alb.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls nginx:1.27-alpine`

<a id="step-18"></a>

### STEP 18: サービス「pki-init」のイメージ「eap-adot-local-pki-init」をビルドする

| 項目 | 内容 |
|---|---|
| 区分 | イメージ作成 |
| 使うコマンド | docker build ― Dockerfile からイメージを作る |
| ひとことで | 設計図 (Dockerfile) と材料フォルダ (ビルドコンテキスト) から、イメージを作ります。 |
| compose の対応箇所 | `services.pki-init.build` |

**実行するコマンド**

```bash
docker build \
  --tag eap-adot-local-pki-init \
  /opt/Container_Compose_file/compose/pki
```

**実行のしかた**

貼り付けて Enter。[+] Building ... と進み具合が表示され、最後に「naming to docker.io/library/<名前>」や「writing image sha256:...」が出て、エラー無くプロンプトに戻れば成功です。2 回目以降は、変わっていない部分に CACHED と表示され、早く終わります。  
・「failed to solve」と出たら、Dockerfile のどの行で失敗したかが表示されるので、その行のコマンドや COPY するファイルの有無を確認します。  
・ビルドコンテキスト (最後に書いたフォルダ) は compose ファイルの build.context と同じ場所です。RHEL 上に同じフォルダ構成で置いてください。

**このコマンドがすること**

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-pki-init」を作ります。

- compose v5 は内部で Docker Bake (BuildKit) に任せてビルドします。docker build も同じ BuildKit を使うため、できあがるイメージは同じです。
- ビルドコンテキストの Dockerfile (/mnt/c/Users/taka_/Claude/Container_Compose_file/compose/pki/Dockerfile) から読み取った内容:
- Dockerfile の FROM (土台にするイメージ): alpine:3.21
- ENTRYPOINT: ["/usr/local/bin/gen-certs.sh"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--tag` | `eap-adot-local-pki-init` | image (無ければ <プロジェクト>-<サービス>) | できたイメージに「eap-adot-local-pki-init」という名前を付けます。compose の image: が無いため、compose と同じ規則「<プロジェクト名>-<サービス名>」で名前を付けます。 | できたイメージに名前 (リポジトリ:タグ) を付けます。タグを省略すると latest になります。docker run ではこの名前で指定します。<br>（やさしく）完成品に名札を付けます。 |
| `(ビルドコンテキスト)` | `/opt/Container_Compose_file/compose/pki` | services.pki-init.build.context | ビルドの材料が入ったフォルダ (context) です。この中のファイルを COPY / ADD で使えます。 | ビルドの材料が入ったフォルダ (ビルドコンテキスト) です。COPY / ADD はこの中のファイルしか使えません。<br>（やさしく）材料の入った箱です。 |

**しくみ (動作原理)**

Docker 23.0 (2023 年 2 月) からは、docker build の中身は BuildKit という新しいビルドエンジン (docker buildx build) です。  
① ビルドコンテキスト (フォルダ) の中身が BuildKit に渡されます。.dockerignore に書いたファイルは渡されません。  
② Dockerfile は LLB (低水準のビルド手順のグラフ) に変換され、互いに関係のない手順は同時に (並列に) 実行されます。  
③ RUN 命令は、ビルド用の一時的なコンテナの中で実行されます。COPY・RUN などの結果は「レイヤー」(前との差分) として記録され、命令と材料が前回と同じなら、作り直さずにキャッシュ (作り置き) を使います。  
④ FROM ... AS 名前 を何度も書く「マルチステージ」では、ビルド用の道具を入れた段階でプログラムを作り、完成品だけを小さな最終イメージへ COPY --from で移せます。  
⑤ --build-arg の値はイメージの履歴に残るので、パスワードには使いません。秘密の値は --secret で渡し、Dockerfile では RUN --mount=type=secret でその命令の間だけ一時的に読みます (レイヤーにもキャッシュにも残りません)。  
⑥ 完成したイメージは、手元のイメージ一覧に --tag の名前で登録されます。  
compose v5 (2025 年 12 月) は自前のビルド処理をやめ、Docker Bake (BuildKit を複数まとめて動かす仕組み) に任せています。そのため、docker build を使っても compose と同じ BuildKit で同じイメージができます。

**動作イメージ (たとえ話)**

料理にたとえると、Dockerfile は「レシピ」、ビルドコンテキストは「材料の入った箱」、BuildKit は「料理人」です。料理人はレシピを 1 行ずつ読み、手順ごとにお皿 (レイヤー) を重ねて「冷凍お弁当」(イメージ) を完成させます。前と同じ手順・同じ材料なら、作り置きのお皿を使うので早くできます。

**歴史と背景・必要になった経緯**

Dockerfile は 2013 年の Docker 登場時からある仕組みで、「サーバーの設定手順書をそのまま実行できる形にする」という考え方を広めました。2017 年の Docker 17.05 でマルチステージビルドが入り、小さく安全なイメージを作りやすくなりました。  
同じ 2017 年に、もっと速く安全なビルドを目指す BuildKit の開発が Moby プロジェクトで始まり、2018 年の Docker 18.09 で試せるようになり、2019 年に docker buildx が登場、2020 年には Dockerfile の RUN --mount (secret / ssh / cache) が使えるようになりました。そして 2023 年 2 月の Docker 23.0 で、Linux の docker build は標準で BuildKit を使うようになりました。  
compose のビルドも BuildKit を使うように変わり、2025 年 12 月の Compose v5.0 で、ビルドは Docker Bake に一本化されました。

**RHEL 9.8 での注意**

UBI (Red Hat Universal Base Image) などを土台にして RUN dnf install をする場合、ビルド中のインターネット接続が必要です。プロキシ環境では --build-arg HTTP_PROXY=... / HTTPS_PROXY=... を渡すか、~/.docker/config.json の proxies 設定を使います。ビルドの途中結果 (キャッシュ) は /var/lib/docker に溜まるので、容量が足りなくなったら docker builder prune で片付けます。

**小学生向けのまとめ**: 設計図と材料を工場に渡して、おもちゃのもと (イメージ) を作ってもらうコマンドです。前と同じところは作り置きを使うので、2 回目からは早くできます。

**確認のしかた**: `docker image ls eap-adot-local-pki-init` ／ `docker image inspect eap-adot-local-pki-init`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  pki-init:
    build:
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/pki
      dockerfile: Dockerfile
```

</details>

<a id="step-19"></a>

### STEP 19: サービス「backend」のイメージ「eap-adot-local-backend」をビルドする

| 項目 | 内容 |
|---|---|
| 区分 | イメージ作成 |
| 使うコマンド | docker build ― Dockerfile からイメージを作る |
| ひとことで | 設計図 (Dockerfile) と材料フォルダ (ビルドコンテキスト) から、イメージを作ります。 |
| compose の対応箇所 | `services.backend.build` |

**実行するコマンド**

```bash
docker build \
  --file /opt/Container_Compose_file/docker/back/Dockerfile \
  --build-arg EAP_BASE_IMAGE=your-registry.example.com/base/eap81-openjdk21-ubi9:latest \
  --tag eap-adot-local-backend \
  /opt/Container_Compose_file/docker
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 18](#step-18) と同じです)。

**このコマンドがすること**

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-backend」を作ります。

- compose v5 は内部で Docker Bake (BuildKit) に任せてビルドします。docker build も同じ BuildKit を使うため、できあがるイメージは同じです。
- ビルドコンテキストの Dockerfile (/mnt/c/Users/taka_/Claude/Container_Compose_file/docker/back/Dockerfile) から読み取った内容:
- Dockerfile の FROM (土台にするイメージ): public.ecr.aws/aws-observability/adot-autoinstrumentation-java:${ADOT_JAVA_AGENT_VERSION}、maven:3.9-eclipse-temurin-21、maven:3.9-eclipse-temurin-21、${EAP_BASE_IMAGE}
- ステージ (AS で名前を付けた途中段階): adot、warbuild、probebuild
- ARG (ビルド時に外から渡せる変数): EAP_BASE_IMAGE、ADOT_JAVA_AGENT_VERSION、MYSQL_CONNECTOR_VERSION、MYSQL_CONNECTOR_VERSION、CACERT_ALIAS、JVM_TRUSTSTORE_PASSWORD、JBOSS_TRUSTSTORE_PASSWORD
- EXPOSE (使う予定のポートのメモ): 8180
- USER (コンテナ内で動くユーザー): 185
- ENTRYPOINT: ["/opt/bin/entrypoint.sh"]
- RUN --mount=type=secret で使う秘密 (id): cacert

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--file` | `/opt/Container_Compose_file/docker/back/Dockerfile` | services.backend.build.dockerfile | 設計図 (Dockerfile) の場所を指定します。compose の dockerfile: back/Dockerfile (context からの相対パス) を絶対パスにしたものです。 | 使う Dockerfile (設計図) を指定します。省略するとビルドコンテキストの中の Dockerfile です。- は「標準入力から読む」です。<br>（やさしく）どの設計図を使うかを指定します。 |
| `--build-arg` | `EAP_BASE_IMAGE=your-registry.example.com/base/eap81-openjdk21-ubi9:latest` | services.backend.build.args | ビルド時の変数 (ARG) EAP_BASE_IMAGE に「your-registry.example.com/base/eap81-openjdk21-ubi9:latest」を渡します。 | Dockerfile の ARG (ビルド時の変数) に値を渡します。バージョン番号やベースイメージの切り替えに使います。イメージの履歴に残るので、パスワードは渡さないでください。<br>（やさしく）設計図の空欄に書き込む値です。 |
| `--tag` | `eap-adot-local-backend` | image (無ければ <プロジェクト>-<サービス>) | できたイメージに「eap-adot-local-backend」という名前を付けます。compose の image: が無いため、compose と同じ規則「<プロジェクト名>-<サービス名>」で名前を付けます。 | (しくみは [STEP 18](#step-18) で説明) |
| `(ビルドコンテキスト)` | `/opt/Container_Compose_file/docker` | services.backend.build.context | ビルドの材料が入ったフォルダ (context) です。この中のファイルを COPY / ADD で使えます。 | ビルドの材料が入ったフォルダ (ビルドコンテキスト) です。COPY / ADD はこの中のファイルしか使えません。<br>（やさしく）材料の入った箱です。 |

**しくみ・歴史**: STEP 18 と同じ `docker build` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-build) を参照してください。

**小学生向けのまとめ**: 設計図と材料を工場に渡して、おもちゃのもと (イメージ) を作ってもらうコマンドです。前と同じところは作り置きを使うので、2 回目からは早くできます。

**確認のしかた**: `docker image ls eap-adot-local-backend` ／ `docker image inspect eap-adot-local-backend`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  backend:
    build:
      args:
        EAP_BASE_IMAGE: "your-registry.example.com/base/eap81-openjdk21-ubi9:latest"
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/docker
      dockerfile: back/Dockerfile
```

</details>

<a id="step-20"></a>

### STEP 20: サービス「frontend」のイメージ「eap-adot-local-frontend」をビルドする

| 項目 | 内容 |
|---|---|
| 区分 | イメージ作成 |
| 使うコマンド | docker build ― Dockerfile からイメージを作る |
| ひとことで | 設計図 (Dockerfile) と材料フォルダ (ビルドコンテキスト) から、イメージを作ります。 |
| compose の対応箇所 | `services.frontend.build` |

**実行するコマンド**

```bash
docker build \
  --file /opt/Container_Compose_file/docker/front/Dockerfile \
  --build-arg EAP_BASE_IMAGE=your-registry.example.com/base/eap81-openjdk21-ubi9:latest \
  --tag eap-adot-local-frontend \
  /opt/Container_Compose_file/docker
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 18](#step-18) と同じです)。

**このコマンドがすること**

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-frontend」を作ります。

- compose v5 は内部で Docker Bake (BuildKit) に任せてビルドします。docker build も同じ BuildKit を使うため、できあがるイメージは同じです。
- ビルドコンテキストの Dockerfile (/mnt/c/Users/taka_/Claude/Container_Compose_file/docker/front/Dockerfile) から読み取った内容:
- Dockerfile の FROM (土台にするイメージ): public.ecr.aws/aws-observability/adot-autoinstrumentation-java:${ADOT_JAVA_AGENT_VERSION}、maven:3.9-eclipse-temurin-21、${EAP_BASE_IMAGE}
- ステージ (AS で名前を付けた途中段階): adot、probebuild
- ARG (ビルド時に外から渡せる変数): EAP_BASE_IMAGE、ADOT_JAVA_AGENT_VERSION、MYSQL_CONNECTOR_VERSION、MYSQL_CONNECTOR_VERSION、CACERT_ALIAS、JVM_TRUSTSTORE_PASSWORD、JBOSS_TRUSTSTORE_PASSWORD
- EXPOSE (使う予定のポートのメモ): 8080
- USER (コンテナ内で動くユーザー): 185
- ENTRYPOINT: ["/opt/bin/entrypoint.sh"]
- RUN --mount=type=secret で使う秘密 (id): cacert

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--file` | `/opt/Container_Compose_file/docker/front/Dockerfile` | services.frontend.build.dockerfile | 設計図 (Dockerfile) の場所を指定します。compose の dockerfile: front/Dockerfile (context からの相対パス) を絶対パスにしたものです。 | (しくみは [STEP 19](#step-19) で説明) |
| `--build-arg` | `EAP_BASE_IMAGE=your-registry.example.com/base/eap81-openjdk21-ubi9:latest` | services.frontend.build.args | ビルド時の変数 (ARG) EAP_BASE_IMAGE に「your-registry.example.com/base/eap81-openjdk21-ubi9:latest」を渡します。 | (しくみは [STEP 19](#step-19) で説明) |
| `--tag` | `eap-adot-local-frontend` | image (無ければ <プロジェクト>-<サービス>) | できたイメージに「eap-adot-local-frontend」という名前を付けます。compose の image: が無いため、compose と同じ規則「<プロジェクト名>-<サービス名>」で名前を付けます。 | (しくみは [STEP 18](#step-18) で説明) |
| `(ビルドコンテキスト)` | `/opt/Container_Compose_file/docker` | services.frontend.build.context | ビルドの材料が入ったフォルダ (context) です。この中のファイルを COPY / ADD で使えます。 | ビルドの材料が入ったフォルダ (ビルドコンテキスト) です。COPY / ADD はこの中のファイルしか使えません。<br>（やさしく）材料の入った箱です。 |

**しくみ・歴史**: STEP 18 と同じ `docker build` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-build) を参照してください。

**小学生向けのまとめ**: 設計図と材料を工場に渡して、おもちゃのもと (イメージ) を作ってもらうコマンドです。前と同じところは作り置きを使うので、2 回目からは早くできます。

**確認のしかた**: `docker image ls eap-adot-local-frontend` ／ `docker image inspect eap-adot-local-frontend`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  frontend:
    build:
      args:
        EAP_BASE_IMAGE: "your-registry.example.com/base/eap81-openjdk21-ubi9:latest"
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/docker
      dockerfile: front/Dockerfile
```

</details>

<a id="step-21"></a>

### STEP 21: サービス「lambda-esm」のイメージ「eap-adot-local-lambda-esm」をビルドする

| 項目 | 内容 |
|---|---|
| 区分 | イメージ作成 |
| 使うコマンド | docker build ― Dockerfile からイメージを作る |
| ひとことで | 設計図 (Dockerfile) と材料フォルダ (ビルドコンテキスト) から、イメージを作ります。 |
| compose の対応箇所 | `services.lambda-esm.build` |

**実行するコマンド**

```bash
docker build \
  --tag eap-adot-local-lambda-esm \
  /opt/Container_Compose_file/compose/lambda-esm
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 18](#step-18) と同じです)。

**このコマンドがすること**

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-lambda-esm」を作ります。

- compose v5 は内部で Docker Bake (BuildKit) に任せてビルドします。docker build も同じ BuildKit を使うため、できあがるイメージは同じです。
- ビルドコンテキストの Dockerfile (/mnt/c/Users/taka_/Claude/Container_Compose_file/compose/lambda-esm/Dockerfile) から読み取った内容:
- Dockerfile の FROM (土台にするイメージ): python:3.12-slim
- ENTRYPOINT: ["python", "/app/poller.py"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--tag` | `eap-adot-local-lambda-esm` | image (無ければ <プロジェクト>-<サービス>) | できたイメージに「eap-adot-local-lambda-esm」という名前を付けます。compose の image: が無いため、compose と同じ規則「<プロジェクト名>-<サービス名>」で名前を付けます。 | (しくみは [STEP 18](#step-18) で説明) |
| `(ビルドコンテキスト)` | `/opt/Container_Compose_file/compose/lambda-esm` | services.lambda-esm.build.context | ビルドの材料が入ったフォルダ (context) です。この中のファイルを COPY / ADD で使えます。 | ビルドの材料が入ったフォルダ (ビルドコンテキスト) です。COPY / ADD はこの中のファイルしか使えません。<br>（やさしく）材料の入った箱です。 |

**しくみ・歴史**: STEP 18 と同じ `docker build` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-build) を参照してください。

**小学生向けのまとめ**: 設計図と材料を工場に渡して、おもちゃのもと (イメージ) を作ってもらうコマンドです。前と同じところは作り置きを使うので、2 回目からは早くできます。

**確認のしかた**: `docker image ls eap-adot-local-lambda-esm` ／ `docker image inspect eap-adot-local-lambda-esm`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  lambda-esm:
    build:
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/lambda-esm
      dockerfile: Dockerfile
```

</details>

<a id="step-22"></a>

### STEP 22: サービス「ecs-exec」のイメージ「eap-adot-local-ecs-exec」をビルドする

| 項目 | 内容 |
|---|---|
| 区分 | イメージ作成 |
| 使うコマンド | docker build ― Dockerfile からイメージを作る |
| ひとことで | 設計図 (Dockerfile) と材料フォルダ (ビルドコンテキスト) から、イメージを作ります。 |
| compose の対応箇所 | `services.ecs-exec.build` |

**実行するコマンド**

```bash
docker build \
  --tag eap-adot-local-ecs-exec \
  /opt/Container_Compose_file/compose/ecs-exec
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 18](#step-18) と同じです)。

**このコマンドがすること**

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「eap-adot-local-ecs-exec」を作ります。

- compose v5 は内部で Docker Bake (BuildKit) に任せてビルドします。docker build も同じ BuildKit を使うため、できあがるイメージは同じです。
- ビルドコンテキストの Dockerfile (/mnt/c/Users/taka_/Claude/Container_Compose_file/compose/ecs-exec/Dockerfile) から読み取った内容:
- Dockerfile の FROM (土台にするイメージ): alpine:3.21
- CMD: ["tail", "-f", "/dev/null"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--tag` | `eap-adot-local-ecs-exec` | image (無ければ <プロジェクト>-<サービス>) | できたイメージに「eap-adot-local-ecs-exec」という名前を付けます。compose の image: が無いため、compose と同じ規則「<プロジェクト名>-<サービス名>」で名前を付けます。 | (しくみは [STEP 18](#step-18) で説明) |
| `(ビルドコンテキスト)` | `/opt/Container_Compose_file/compose/ecs-exec` | services.ecs-exec.build.context | ビルドの材料が入ったフォルダ (context) です。この中のファイルを COPY / ADD で使えます。 | ビルドの材料が入ったフォルダ (ビルドコンテキスト) です。COPY / ADD はこの中のファイルしか使えません。<br>（やさしく）材料の入った箱です。 |

**しくみ・歴史**: STEP 18 と同じ `docker build` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-build) を参照してください。

**小学生向けのまとめ**: 設計図と材料を工場に渡して、おもちゃのもと (イメージ) を作ってもらうコマンドです。前と同じところは作り置きを使うので、2 回目からは早くできます。

**確認のしかた**: `docker image ls eap-adot-local-ecs-exec` ／ `docker image inspect eap-adot-local-ecs-exec`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  ecs-exec:
    build:
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/ecs-exec
      dockerfile: Dockerfile
```

</details>

<a id="step-23"></a>

### STEP 23: サービス「adot-collector」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-adot-collector:with-healthcheck」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ヘルスチェック入りイメージ作成 |
| 使うコマンド | docker build - (ヘルスチェック入りの派生イメージを作る) |
| ひとことで | 元のイメージに、compose と同じ「exec 形式」のヘルスチェック設定だけを足したイメージを作ります。 |
| compose の対応箇所 | `services.adot-collector.healthcheck` |

**実行するコマンド**

```bash
docker build --tag eap-adot-local-adot-collector:with-healthcheck - <<'C2D_DOCKERFILE'
FROM public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 CMD ["/healthcheck"]
C2D_DOCKERFILE
```

**実行のしかた**

かたまり全体 (最後の C2D_DOCKERFILE の行まで) をコピーして貼り付け、Enter を押します。途中で > という記号が表示されるのは、ヒアドキュメント (複数行の文章をコマンドに渡す書き方) の続きを受け付けている印なので、正常です。数秒で終わり、エラーが出なければ成功です。

**このコマンドがすること**

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

- exec 形式: コマンドを直接実行します。/bin/sh が入っていないイメージ (distroless など) でも動きます。
- シェル形式: /bin/sh -c 'コマンド' で実行します。シェルが無いイメージでは必ず失敗し、コンテナが unhealthy (不健康) になります。
- 作られるイメージは元のイメージにメタデータ (HEALTHCHECK の設定) を 1 つ足しただけで、中身のファイルは同じです。
- 焼き込む内容: HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 CMD ["/healthcheck"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--tag` | `eap-adot-local-adot-collector:with-healthcheck` | image (無ければ <プロジェクト>-<サービス>) | ヘルスチェック入りのイメージに「eap-adot-local-adot-collector:with-healthcheck」という名前を付けます (元のイメージ「public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3」は変更しません)。 | (しくみは [STEP 18](#step-18) で説明) |
| `(Dockerfile の読み込み元)` | `-` | (派生イメージ) | 「-」は Dockerfile を標準入力 (下のヒアドキュメント) から読む、という意味です。材料フォルダ (コンテキスト) は使いません。 | 「-」は Dockerfile を標準入力から読むという意味です。<br>（やさしく）設計図を手渡しします。 |

**しくみ (動作原理)**

docker build の最後の「-」は、「Dockerfile を標準入力から読む (材料フォルダは使わない)」という意味です。<<'C2D_DOCKERFILE' からC2D_DOCKERFILE までの行が、そのまま Dockerfile として渡されます。'...' で囲んでいるので、$ などの記号もそのまま渡されます。  
FROM で元のイメージを土台にし、HEALTHCHECK でヘルスチェックの設定を付けます。HEALTHCHECK はファイルを変えない「設定 (メタデータ)」だけの命令なので、中身のファイルは元のイメージと 1 バイトも変わらず、イメージの設定 (config) だけが新しくなります。ダウンロードし直すものもありません。元のイメージ名はそのまま残り、新しいイメージには <プロジェクト>-<サービス>:with-healthcheck という別の名前を付けます。

**動作イメージ (たとえ話)**

お弁当 (イメージ) の中身はそのままで、ふたに「元気チェックのやり方カード」を貼った版を作るようなものです。

**歴史と背景・必要になった経緯**

HEALTHCHECK は 2016 年 7 月の Docker 1.12 で追加されました。それまでは「プロセスが動いているか」しか分からず、「動いてはいるが応答しない」状態を見分けられませんでした。その後、Google の distroless (2017 年) のように、攻撃される隙を減らすためにシェルすら入れない小さなイメージが広まり、シェルを使わない exec 形式の大切さが増しました。Docker 25 (2024 年) では、起動直後だけ短い間隔でチェックする start-interval も加わっています。

**RHEL 9.8 での注意**

特にありません。元のイメージが手元にある (先の STEP で取得・ビルド済み) 必要があります。

**小学生向けのまとめ**: 元のおもちゃはそのままで、「元気かな？チェックのやり方」を書いたカードを貼った版を作るコマンドです。

**確認のしかた**: `docker image inspect --format '{{json .Config.Healthcheck}}' eap-adot-local-adot-collector:with-healthcheck`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  adot-collector:
    healthcheck:
      interval: 10s
      retries: 5
      start_period: 10s
      test:
        - CMD
        - /healthcheck
      timeout: 5s
```

</details>

<a id="step-24"></a>

### STEP 24: サービス「alb-front」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-alb-front:with-healthcheck」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ヘルスチェック入りイメージ作成 |
| 使うコマンド | docker build - (ヘルスチェック入りの派生イメージを作る) |
| ひとことで | 元のイメージに、compose と同じ「exec 形式」のヘルスチェック設定だけを足したイメージを作ります。 |
| compose の対応箇所 | `services.alb-front.healthcheck` |

**実行するコマンド**

```bash
docker build --tag eap-adot-local-alb-front:with-healthcheck - <<'C2D_DOCKERFILE'
FROM python:3.12-slim
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 CMD ["python3", "/opt/alb-front/alb-front.py", "ready"]
C2D_DOCKERFILE
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 23](#step-23) と同じです)。

**このコマンドがすること**

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

- exec 形式: コマンドを直接実行します。/bin/sh が入っていないイメージ (distroless など) でも動きます。
- シェル形式: /bin/sh -c 'コマンド' で実行します。シェルが無いイメージでは必ず失敗し、コンテナが unhealthy (不健康) になります。
- 作られるイメージは元のイメージにメタデータ (HEALTHCHECK の設定) を 1 つ足しただけで、中身のファイルは同じです。
- 焼き込む内容: HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 CMD ["python3", "/opt/alb-front/alb-front.py", "ready"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--tag` | `eap-adot-local-alb-front:with-healthcheck` | image (無ければ <プロジェクト>-<サービス>) | ヘルスチェック入りのイメージに「eap-adot-local-alb-front:with-healthcheck」という名前を付けます (元のイメージ「python:3.12-slim」は変更しません)。 | (しくみは [STEP 18](#step-18) で説明) |
| `(Dockerfile の読み込み元)` | `-` | (派生イメージ) | 「-」は Dockerfile を標準入力 (下のヒアドキュメント) から読む、という意味です。材料フォルダ (コンテキスト) は使いません。 | 「-」は Dockerfile を標準入力から読むという意味です。<br>（やさしく）設計図を手渡しします。 |

**しくみ・歴史**: STEP 23 と同じ `docker build (healthcheck)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-build-healthcheck) を参照してください。

**小学生向けのまとめ**: 元のおもちゃはそのままで、「元気かな？チェックのやり方」を書いたカードを貼った版を作るコマンドです。

**確認のしかた**: `docker image inspect --format '{{json .Config.Healthcheck}}' eap-adot-local-alb-front:with-healthcheck`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  alb-front:
    healthcheck:
      interval: 10s
      retries: 5
      start_period: 5s
      test:
        - CMD
        - python3
        - /opt/alb-front/alb-front.py
        - ready
      timeout: 5s
```

</details>

<a id="step-25"></a>

### STEP 25: サービス「ecs-exec」用に、ヘルスチェックを焼き込んだイメージ「eap-adot-local-ecs-exec:with-healthcheck」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ヘルスチェック入りイメージ作成 |
| 使うコマンド | docker build - (ヘルスチェック入りの派生イメージを作る) |
| ひとことで | 元のイメージに、compose と同じ「exec 形式」のヘルスチェック設定だけを足したイメージを作ります。 |
| compose の対応箇所 | `services.ecs-exec.healthcheck` |

**実行するコマンド**

```bash
docker build --tag eap-adot-local-ecs-exec:with-healthcheck - <<'C2D_DOCKERFILE'
FROM eap-adot-local-ecs-exec
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD ["ecs-exec", "doctor", "--self-only", "--quiet"]
C2D_DOCKERFILE
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 23](#step-23) と同じです)。

**このコマンドがすること**

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

- exec 形式: コマンドを直接実行します。/bin/sh が入っていないイメージ (distroless など) でも動きます。
- シェル形式: /bin/sh -c 'コマンド' で実行します。シェルが無いイメージでは必ず失敗し、コンテナが unhealthy (不健康) になります。
- 作られるイメージは元のイメージにメタデータ (HEALTHCHECK の設定) を 1 つ足しただけで、中身のファイルは同じです。
- 焼き込む内容: HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD ["ecs-exec", "doctor", "--self-only", "--quiet"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--tag` | `eap-adot-local-ecs-exec:with-healthcheck` | image (無ければ <プロジェクト>-<サービス>) | ヘルスチェック入りのイメージに「eap-adot-local-ecs-exec:with-healthcheck」という名前を付けます (元のイメージ「eap-adot-local-ecs-exec」は変更しません)。 | (しくみは [STEP 18](#step-18) で説明) |
| `(Dockerfile の読み込み元)` | `-` | (派生イメージ) | 「-」は Dockerfile を標準入力 (下のヒアドキュメント) から読む、という意味です。材料フォルダ (コンテキスト) は使いません。 | 「-」は Dockerfile を標準入力から読むという意味です。<br>（やさしく）設計図を手渡しします。 |

**しくみ・歴史**: STEP 23 と同じ `docker build (healthcheck)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-build-healthcheck) を参照してください。

**小学生向けのまとめ**: 元のおもちゃはそのままで、「元気かな？チェックのやり方」を書いたカードを貼った版を作るコマンドです。

**確認のしかた**: `docker image inspect --format '{{json .Config.Healthcheck}}' eap-adot-local-ecs-exec:with-healthcheck`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  ecs-exec:
    healthcheck:
      interval: 30s
      retries: 3
      start_period: 5s
      test:
        - CMD
        - ecs-exec
        - doctor
        - "--self-only"
        - "--quiet"
      timeout: 10s
```

</details>

<a id="step-26"></a>

### STEP 26: サービス「jaeger」のコンテナ「jaeger」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.jaeger` |

**実行するコマンド**

```bash
docker run \
  --detach \
  --name jaeger \
  --network eap-adot-local_default \
  --network-alias jaeger \
  --publish 16686:16686 \
  jaegertracing/jaeger:2.4.0
```

**実行のしかた**

かたまり全体をコピーして貼り付け、Enter を押します。行の最後の \ (バックスラッシュ。Excel の Meiryo UI では ¥ に見えます) は「コマンドが次の行に続く」という印なので、途中で切らずに全部まとめて貼り付けてください。成功すると、作られたコンテナの ID (64 文字の英数字) が 1 行表示されます。  
・「Conflict. The container name "/..." is already in use」は、同じ名前のコンテナが残っています。後片付けをしてからやり直します。  
・「port is already allocated」「address already in use」は、ホストのそのポートを別のプログラムが使っています。  
・ID が表示されてもすぐ止まってしまうことがあります。docker ps --all で STATUS を見て、Exited なら docker logs <名前> で原因を調べます。

**このコマンドがすること**

イメージ「jaegertracing/jaeger:2.4.0」からコンテナ「jaeger」を作って起動します (サービス「jaeger」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 16686:16686

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | コンテナを裏側 (バックグラウンド) で動かし、コマンドはすぐに終わってプロンプトに戻ります。付けないと、コンテナの画面出力がターミナルに流れ続け、Ctrl+C でコンテナも止まってしまいます。出力はあとから docker logs で見られます。<br>（やさしく）おもちゃのスイッチを入れたら、見張っていなくても勝手に動き続けるようにします。 |
| `--name` | `jaeger` | services.jaeger.container_name | コンテナに「jaeger」という名前を付けます。compose の container_name です。 | コンテナに名前を付けます。名前は同じホストの中で 1 つだけで、docker logs や docker stop で使えるほか、ユーザー定義ネットワークではその名前で相手を呼べます (内蔵 DNS がコンテナ名を IP に変換します)。compose v2 以降は「プロジェクト-サービス-番号」とハイフンでつなぎます (昔の compose v1 はアンダースコア _ でした)。<br>（やさしく）コンテナに名札を付けます。名札の名前で呼んだり、止めたりできます。 |
| `--network` | `eap-adot-local_default` | services.jaeger.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | コンテナをどのネットワークにつなぐかを決めます。ネットワーク名を書けばそのネットワークへ、host ならホストのネットワークをそのまま使用、none ならつながない、container:<名前> なら別のコンテナとネットワークを共有します (compose の network_mode: service:<サービス>)。<br>name=ネットワーク名,alias=別名,ip=IP アドレス のような長い書き方 (Docker 25 以降) を使うと、1 回の docker run で複数のネットワークにつなぎ、それぞれに別名や IP を設定できます。compose は priority (優先度) が高い順、同じなら名前の順にネットワークを並べ、最初のものをメインにします。<br>（やさしく）コンテナをどの道路 (ネットワーク) につなぐかを決めます。 |
| `--network-alias` | `jaeger` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「jaeger」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | そのネットワークの中だけで使える、コンテナの別名を付けます。内蔵 DNS がこの名前を IP アドレスに変換するので、ほかのコンテナからhttp://<別名>:ポート で呼べます。compose はサービス名を必ず別名にするため、ここでもサービス名を付けています。同じ別名を複数のコンテナに付けると、DNS は順番に答えを返します (かんたんな負荷分散)。<br>（やさしく）電話帳に「あだ名」を登録して、あだ名でも電話がかかるようにします。 |
| `--publish` | `16686:16686` | services.jaeger.ports | ホスト (RHEL) の 16686 番ポート (TCP) に届いた通信を、コンテナの 16686 番ポートへ転送します。 | ホスト (RHEL) のポートに届いた通信を、コンテナのポートへ転送します。書き方は [ホストのIP:]ホストのポート:コンテナのポート[/udp]。ホスト側を省略すると空いているポートが自動で選ばれます。<br>しくみ: dockerd がファイアウォール (iptables / nftables) に DNAT (宛先の書き換え) のルールを入れ、さらに docker-proxy という小さな中継プログラムも起動します。外から http://<RHEL の IP>:8080 に来た通信は、コンテナの IP:80 に書き換えられて届きます。IP を 127.0.0.1 にすると、そのサーバーの中からしか接続できなくなります (外には公開しない)。<br>（やさしく）マンションの正面玄関の「〇番窓口」に来たお客さんを、お部屋の「〇番ドア」へ案内する道案内です。 |
| `(イメージ)` | `jaegertracing/jaeger:2.4.0` | services.jaeger.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ (動作原理)**

① docker コマンドがオプションを JSON にまとめ、dockerd に「POST /containers/create」を送ります。  
② dockerd はイメージに書かれた設定 (ENV・CMD・ENTRYPOINT・WORKDIR・USER・EXPOSE・VOLUME・HEALTHCHECK) と、オプションの設定を合わせ、OCI ランタイム仕様の設定ファイル (config.json) を作ります。オプションで指定したものがイメージの設定より優先されます。  
③ 続いて「POST /containers/<ID>/start」で起動します。dockerd → containerd → containerd-shim-runc-v2 → runc とリレーされ、runc が Linux カーネルに次のことを頼みます。  
　・名前空間 (namespace): PID (プロセス番号)・NET (ネットワーク)・MNT (ファイルの見え方)・UTS (ホスト名)・IPC (プロセス間通信)・cgroup をコンテナ専用に分け、ほかのコンテナやホストのものが見えないようにします。  
　・cgroup v2: CPU・メモリ・プロセス数などの使用量を数え、上限を決めます (--cpus や --memory)。  
　・overlayfs: イメージのレイヤー (読み取り専用) を何枚も重ね、その一番上に書き込み用の層を 1 枚足して、コンテナのファイルシステム (/) にします。コンテナで書いたファイルはこの書き込み層に入り、コンテナを消すと一緒に消えます。  
　・ボリュームやバインドマウントをつなぎ、capabilities (root の特権を細かく分けたもの。標準では 14 種類だけ許可) と seccomp (使ってよいシステムコールの一覧) で権限をしぼります。  
　・最後に ENTRYPOINT + CMD のプログラムを、そのコンテナの中の PID 1 (最初のプロセス) として実行します。  
④ ネットワークは veth でブリッジにつながれ、IP アドレスが割り当てられ、/etc/hosts と /etc/resolv.conf (内蔵 DNS の 127.0.0.11) が用意されます。  
⑤ プログラムの画面出力は、ログドライバー (標準は json-file) を通して /var/lib/docker/containers/<ID>/<ID>-json.log などに保存されます。  
⑥ その後も dockerd は、restart の設定に従ってコンテナが止まったら起こし直し、HEALTHCHECK があれば一定間隔で健康チェックを行います。  
つまりコンテナの正体は「特別な囲いの中で動いている、ふつうの Linux のプロセス」です。仮想マシンのように OS をまるごと起動するわけではないので、1 秒もかからずに起動できます。

**動作イメージ (たとえ話)**

マンション (ホスト) の空き部屋を 1 つ用意し、お部屋セット (イメージ) の家具を運び込んで、住人 (プログラム) に住んでもらうようなものです。部屋には壁 (名前空間) があってほかの部屋の中は見えず、電気や水道にはブレーカー (cgroup) が付いていて使いすぎを防ぎます。管理人さん (dockerd) は、マンションの合鍵 (特権) のうち必要なものだけを住人に渡し、住人が倒れたら起こしに行き (restart)、ときどき「元気？」と声をかけます (healthcheck)。

**歴史と背景・必要になった経緯**

「プログラムを囲いの中で動かす」考えは古く、1979 年の Unix V7 の chroot (見えるフォルダを制限する) までさかのぼります。2000 年に FreeBSD の jail、2004〜2005 年に Solaris の Zones が登場しました。Linux では 2002 年から名前空間が少しずつ作られ、2006 年に Google の技術者が「process containers」として資源の上限を決める仕組みを開発し、2008 年 (Linux 2.6.24) に cgroups として取り込まれました。同じ 2008 年に、これらを組み合わせた LXC が登場しています。  
2013 年の Docker は、LXC を使って「イメージ」という配りやすい形と、docker run という簡単なコマンドを用意したことで爆発的に広まりました。2014 年には LXC をやめて自前の libcontainer に切り替え、2015 年にそれを runc として OCI に寄贈しました。2016 年には containerd が分離され、2017 年に CNCF (クラウドネイティブの技術を育てる団体) へ寄贈されています。  
資源の管理は cgroup v2 (2016 年、Linux 4.5) へ移り、RHEL 9 (2022 年) では cgroup v2 が標準になりました。Docker も 20.10 (2020 年) で cgroup v2 に対応し、29.0 (2025 年 11 月) で cgroup v1 を非推奨にしています。

**RHEL 9.8 での注意**

・RHEL 9.8 は cgroup v2 が標準です。--memory-swappiness や --kernel-memory など cgroup v1 専用の古いオプションは使えません (警告が出て無視されます)。  
・SELinux: docker-ce の標準設定 (selinux-enabled: false) では、コンテナに SELinux のラベルが付かないため、バインドマウントはそのまま読み書きできます。/etc/docker/daemon.json に "selinux-enabled": true を設定している場合は、ホストのフォルダをつなぐときに :z (複数のコンテナで共有) か :Z (このコンテナ専用) を付けないと Permission denied になります。これは compose でも同じです。  
・ポート公開 (-p) は Docker が自分でファイアウォールのルールを入れるため、通常は firewall-cmd での許可は不要です。・Docker 29 から、コンテナ内の「同時に開けるファイル数」の標準 (ulimit -n のソフト上限) が 1024 になっています。多くの接続やファイルを使うアプリは、compose の ulimits (= --ulimit nofile=...) で上げておきます。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=jaeger` ／ `docker logs jaeger` ／ `docker inspect jaeger`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  jaeger:
    container_name: jaeger
    image: "jaegertracing/jaeger:2.4.0"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 16686
        target: 16686
```

</details>

<a id="step-27"></a>

### STEP 27: サービス「valkey」のコンテナ「valkey」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.valkey` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「valkey/valkey:8.0」からコンテナ「valkey」を作って起動します (サービス「valkey」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 6379:6379

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `valkey` | services.valkey.container_name | コンテナに「valkey」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.valkey.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `valkey` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「valkey」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `6379:6379` | services.valkey.ports | ホスト (RHEL) の 6379 番ポート (TCP) に届いた通信を、コンテナの 6379 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--health-cmd` | `valkey-cli ping \| grep -q PONG` | services.valkey.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | ヘルスチェック (健康診断) で実行するコマンドです。dockerd が定期的にコンテナの中で /bin/sh -c 'コマンド' を実行し、終了コード 0 なら合格です。シェル形式なので、イメージに /bin/sh が無いと使えません (その場合このツールは派生イメージで exec 形式を再現します)。<br>（やさしく）「元気？」と聞くときの質問の中身です。 |
| `--health-interval` | `3s` | services.valkey.healthcheck.interval | 何秒おきにチェックするか: 3s | ヘルスチェックの間隔です (標準 30 秒)。<br>（やさしく）何秒おきに「元気？」と聞くかです。 |
| `--health-timeout` | `3s` | services.valkey.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | 1 回のチェックの制限時間です (標準 30 秒)。超えたら不合格です。<br>（やさしく）返事を待つ時間の長さです。 |
| `--health-start-period` | `3s` | services.valkey.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 3s | 起動直後の猶予期間です。この間の不合格は数えません (起動に時間がかかるアプリ用)。<br>（やさしく）起きたばかりの間は、返事がなくても大目に見る時間です。 |
| `--health-retries` | `20` | services.valkey.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 20 回 | 何回続けて不合格になったら unhealthy (不健康) とするかです (標準 3 回)。<br>（やさしく）何回続けて返事がなかったら「具合が悪い」とするかです。 |
| `(イメージ)` | `valkey/valkey:8.0` | services.valkey.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=valkey` ／ `docker logs valkey` ／ `docker inspect valkey`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  valkey:
    container_name: valkey
    healthcheck:
      interval: 3s
      retries: 20
      start_period: 3s
      test:
        - CMD-SHELL
        - "valkey-cli ping | grep -q PONG"
      timeout: 3s
    image: "valkey/valkey:8.0"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 6379
        target: 6379
```

</details>

<a id="step-28"></a>

### STEP 28: サービス「svf-mock」のコンテナ「svf-mock」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.svf-mock` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「wiremock/wiremock:3.13.0」からコンテナ「svf-mock」を作って起動します (サービス「svf-mock」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 8280:8080
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `svf-mock` | services.svf-mock.container_name | コンテナに「svf-mock」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.svf-mock.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `svf-mock` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「svf-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8280:8080` | services.svf-mock.ports | ホスト (RHEL) の 8280 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/svf-mock/mappings:/home/wiremock/mappings:ro` | services.svf-mock.volumes | ホストの /opt/Container_Compose_file/compose/svf-mock/mappings をコンテナの /home/wiremock/mappings に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | ホストのフォルダ・ファイル、または名前付きボリュームを、コンテナの中の場所につなぎます (マウント)。書き方は 元:コンテナ内の場所[:ro][,z]。元が / や ./ で始まればホストのパス (バインドマウント)、名前ならボリュームです。:ro は読み取り専用、:z / :Z は SELinux 用のラベル付けです。ホスト側のフォルダが無いときは空のフォルダが自動で作られます (compose の短い書き方と同じ動き)。compose v5 も、短い書き方のバインドと、オプションの無い名前付きボリュームは、この形 (Docker API の Binds) で渡しています。<br>（やさしく）お部屋の壁に、外の引き出し (ホストのフォルダ) やロッカー (ボリューム) へ通じる扉を付けます。 |
| `--health-cmd` | `timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' \|\| exit 1` | services.svf-mock.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `3s` | services.svf-mock.healthcheck.interval | 何秒おきにチェックするか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `3s` | services.svf-mock.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `5s` | services.svf-mock.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `40` | services.svf-mock.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 40 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `wiremock/wiremock:3.13.0` | services.svf-mock.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=svf-mock` ／ `docker logs svf-mock` ／ `docker inspect svf-mock`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  svf-mock:
    container_name: svf-mock
    healthcheck:
      interval: 3s
      retries: 40
      start_period: 5s
      test:
        - CMD-SHELL
        - "timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' || exit 1"
      timeout: 3s
    image: "wiremock/wiremock:3.13.0"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8280
        target: 8080
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/svf-mock/mappings
        target: /home/wiremock/mappings
        type: bind
```

</details>

<a id="step-29"></a>

### STEP 29: サービス「ecs-metadata-mock」のコンテナ「ecs-metadata-mock」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.ecs-metadata-mock` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「wiremock/wiremock:3.13.0」からコンテナ「ecs-metadata-mock」を作って起動します (サービス「ecs-metadata-mock」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 8380:8080
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `ecs-metadata-mock` | services.ecs-metadata-mock.container_name | コンテナに「ecs-metadata-mock」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.ecs-metadata-mock.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `ecs-metadata-mock` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「ecs-metadata-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8380:8080` | services.ecs-metadata-mock.ports | ホスト (RHEL) の 8380 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/ecs-metadata-mock/mappings:/home/wiremock/mappings:ro` | services.ecs-metadata-mock.volumes | ホストの /opt/Container_Compose_file/compose/ecs-metadata-mock/mappings をコンテナの /home/wiremock/mappings に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--health-cmd` | `timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' \|\| exit 1` | services.ecs-metadata-mock.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `3s` | services.ecs-metadata-mock.healthcheck.interval | 何秒おきにチェックするか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `3s` | services.ecs-metadata-mock.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `5s` | services.ecs-metadata-mock.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `40` | services.ecs-metadata-mock.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 40 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `wiremock/wiremock:3.13.0` | services.ecs-metadata-mock.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=ecs-metadata-mock` ／ `docker logs ecs-metadata-mock` ／ `docker inspect ecs-metadata-mock`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  ecs-metadata-mock:
    container_name: ecs-metadata-mock
    healthcheck:
      interval: 3s
      retries: 40
      start_period: 5s
      test:
        - CMD-SHELL
        - "timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' || exit 1"
      timeout: 3s
    image: "wiremock/wiremock:3.13.0"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8380
        target: 8080
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/ecs-metadata-mock/mappings
        target: /home/wiremock/mappings
        type: bind
```

</details>

<a id="step-30"></a>

### STEP 30: ecs-metadata-mock が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.adot-collector.depends_on` |

**実行するコマンド**

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

**実行のしかた**

かたまり全体 (for から最後の done まで) を貼り付けて Enter。「[待機] ... 待ちます」と表示され、準備ができると「[OK] ... は healthy です」と表示されて、プロンプトに戻ります。数十秒〜数分かかることがあります。  
・「[NG] ... の状態は running:unhealthy」などと出たら、相手のコンテナに問題があります。docker logs <名前> で原因を確認してください。  
・ずっと待ち続けて終わらないときは Ctrl+C で止めて、docker ps で状態を確認します。

**このコマンドがすること**

サービス「adot-collector」は depends_on で ecs-metadata-mock が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | inspect の結果 (JSON) から、Go テンプレートで必要な値だけを取り出します。<br>（やさしく）長い報告書から、見たい行だけを抜き出します。 |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ (動作原理)**

ヘルスチェックは dockerd が行っています。interval (間隔) ごとに、コンテナの中でテスト用のコマンドを実行し (docker exec と同じ仕組み)、終了コード 0 なら合格、それ以外なら不合格と数えます。起動直後の start_period の間は不合格を数えず、retries 回続けて不合格になると unhealthy、1 回でも合格すると healthy になります。結果はコンテナの State.Health に記録され、docker inspect で読めます。--format の書き方は Go 言語のテンプレートで、{{if}} は「Health の情報があるときだけ」という条件です。

**動作イメージ (たとえ話)**

お店の前で「準備中」の札が「営業中」に変わるのを、2 秒ごとにのぞいて待っているようなものです。「本日休業」(unhealthy) の札が出たら、待つのをやめて理由を聞きに行きます。

**歴史と背景・必要になった経緯**

HEALTHCHECK は 2016 年 7 月の Docker 1.12 で登場しました。compose ではファイル形式 v2.1 (2016 年) から depends_on に condition: service_healthy を書けるようになりましたが、Swarm 向けのファイル形式 v3 (2017 年) では一度消えてしまい、多くの人が自作の「待ち合わせスクリプト」(wait-for-it.sh など) を使っていました。2020 年に始まった Compose Specification でこの書き方が正式に復活し、2021 年には service_completed_successfully も加わりました。

**RHEL 9.8 での注意**

bash 5.1 (RHEL 9 の標準) でそのまま動きます。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=ecs-metadata-mock`

<a id="step-31"></a>

### STEP 31: サービス「adot-collector」のコンテナ「adot-collector」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.adot-collector` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「eap-adot-local-adot-collector:with-healthcheck」からコンテナ「adot-collector」を作って起動します (サービス「adot-collector」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 4318:4318
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 1 件 / --env-file 0 件
- depends_on (先に起動しておくもの): ecs-metadata-mock (service_healthy)、jaeger (service_started)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `adot-collector` | services.adot-collector.container_name | コンテナに「adot-collector」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.adot-collector.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `adot-collector` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「adot-collector」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `4318:4318` | services.adot-collector.ports | ホスト (RHEL) の 4318 番ポート (TCP) に届いた通信を、コンテナの 4318 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/otel/adot-collector-local.yaml:/etc/otel/config.yaml:ro` | services.adot-collector.volumes | ホストの /opt/Container_Compose_file/compose/otel/adot-collector-local.yaml をコンテナの /etc/otel/config.yaml に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--env` | `ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-3456789012` | services.adot-collector.environment | 環境変数 ECS_CONTAINER_METADATA_URI_V4 に「http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd64…」を設定します。 | コンテナの中のプログラムに渡す環境変数 (名前=値 の設定メモ) を指定します。データベースの接続先やパスワード、動作モードなどを、イメージを作り直さずに切り替えられます。値を書かずに名前だけ (--env NAME) にすると、実行するシェルにある同じ名前の変数の値が渡されます。<br>compose は compose ファイルの ${VAR} を .env や OS の環境変数で展開してから値を決めます。この手順の値は、展開済みの最終的な値です。同じ名前が複数あると、後に書いたものが勝ちます (environment が env_file より優先、という compose の規則と同じ順に並べています)。<br>（やさしく）お部屋に置いておく「設定メモ」です。プログラムはこのメモを読んで動き方を変えます。 |
| `(イメージ)` | `eap-adot-local-adot-collector:with-healthcheck` | services.adot-collector.image | ヘルスチェック入りの派生イメージ (元: public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3) です。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `--config=/etc/otel/config.yaml` | services.adot-collector.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=adot-collector` ／ `docker logs adot-collector` ／ `docker inspect adot-collector`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  adot-collector:
    command:
      - "--config=/etc/otel/config.yaml"
    container_name: adot-collector
    depends_on:
      ecs-metadata-mock:
        condition: service_healthy
        required: true
      jaeger:
        condition: service_started
        required: true
    environment:
      ECS_CONTAINER_METADATA_URI_V4: "http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-3456789012"
    healthcheck:
      interval: 10s
      retries: 5
      start_period: 10s
      test:
        - CMD
        - /healthcheck
      timeout: 5s
    image: "public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 4318
        target: 4318
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/otel/adot-collector-local.yaml
        target: /etc/otel/config.yaml
        type: bind
```

</details>

<a id="step-32"></a>

### STEP 32: サービス「efs-mock」のコンテナ「efs-mock」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.efs-mock` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「alpine:3.21」からコンテナ「efs-mock」を作って起動します (サービス「efs-mock」)。

- ネットワーク: eap-adot-local_default
- マウント: 2 件 (データの置き場所をコンテナにつなぎます)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `efs-mock` | services.efs-mock.container_name | コンテナに「efs-mock」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.efs-mock.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `efs-mock` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「efs-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `eap-adot-local_efs-logs:/mnt/efs/logs` | services.efs-mock.volumes | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/efs/logs につなぎます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `eap-adot-local_efs-data:/mnt/efs/data` | services.efs-mock.volumes | 名前付きボリューム「eap-adot-local_efs-data」をコンテナの /mnt/efs/data につなぎます。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `test -f /tmp/efs-initialized && [ "$(stat -c %u:%g /mnt/efs/logs)" = "6301:6302" ] && [ "$(stat -c %u:%g /mnt/efs/data)" = "6301:6302" ]` | services.efs-mock.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `5s` | services.efs-mock.healthcheck.interval | 何秒おきにチェックするか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `3s` | services.efs-mock.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `3s` | services.efs-mock.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `5` | services.efs-mock.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 5 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `alpine:3.21` | services.efs-mock.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `sh -euc chown 6301:6302 /mnt/efs/logs /mnt/efs/data<br>chmod 2775 /mnt/efs/logs /mnt/efs/data<br>echo "[efs-mock] initialized /mnt/efs/logs /mnt/efs/data (owner=6301:6302 mode=2775)"<br>touch /tmp/efs-initialized<br>exec tail -f /dev/null<br>` | services.efs-mock.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=efs-mock` ／ `docker logs efs-mock` ／ `docker inspect efs-mock`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  efs-mock:
    command:
      - sh
      - "-euc"
      - "chown 6301:6302 /mnt/efs/logs /mnt/efs/data\nchmod 2775 /mnt/efs/logs /mnt/efs/data\necho \"[efs-mock] initialized /mnt/efs/logs /mnt/efs/data (owner=6301:6302 mode=2775)\"\ntouch /tmp/efs-initialized\nexec tail -f /dev/null\n"
    container_name: efs-mock
    healthcheck:
      interval: 5s
      retries: 5
      start_period: 3s
      test:
        - CMD-SHELL
        - "test -f /tmp/efs-initialized && [ \"$(stat -c %u:%g /mnt/efs/logs)\" = \"6301:6302\" ] && [ \"$(stat -c %u:%g /mnt/efs/data)\" = \"6301:6302\" ]"
      timeout: 3s
    image: "alpine:3.21"
    networks: {}
    volumes:
      - source: efs-logs
        target: /mnt/efs/logs
        type: volume
        volume: {}
      - source: efs-data
        target: /mnt/efs/data
        type: volume
        volume: {}
```

</details>

<a id="step-33"></a>

### STEP 33: efs-mock が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.batch-mock.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 30](#step-30) と同じです)。

**このコマンドがすること**

サービス「batch-mock」は depends_on で efs-mock が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 30](#step-30) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 30 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=efs-mock`

<a id="step-34"></a>

### STEP 34: サービス「batch-mock」のコンテナ「batch-mock」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.batch-mock` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「alpine:3.21」からコンテナ「batch-mock」を作って起動します (サービス「batch-mock」)。

- ネットワーク: eap-adot-local_default
- マウント: 3 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 2 件 / --env-file 0 件
- depends_on (先に起動しておくもの): efs-mock (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `batch-mock` | services.batch-mock.container_name | コンテナに「batch-mock」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--user` | `6301:6302` | services.batch-mock.user | コンテナの中のプログラムを ユーザー 6301:6302 として動かします。 | コンテナの中のプログラムを、どのユーザー (UID) とグループ (GID) で動かすかを決めます。例: 1000:1000、appuser。指定しないとイメージの USER (無ければ root) で動きます。root 以外で動かすと、万一乗っ取られても被害を小さくできます。バインドマウントしたホストのフォルダの読み書きは、この UID/GID の権限で判断されます。<br>（やさしく）お部屋の中で「だれ」として作業するかを決めます。 |
| `--network` | `eap-adot-local_default` | services.batch-mock.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `batch-mock` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「batch-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/batch-mock/efs-propagation.sh:/opt/batch-mock/efs-propagation.sh:ro` | services.batch-mock.volumes | ホストの /opt/Container_Compose_file/compose/batch-mock/efs-propagation.sh をコンテナの /opt/batch-mock/efs-propagation.sh に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `eap-adot-local_efs-logs:/mnt/logs` | services.batch-mock.volumes | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/logs につなぎます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `eap-adot-local_efs-data:/mnt/data` | services.batch-mock.volumes | 名前付きボリューム「eap-adot-local_efs-data」をコンテナの /mnt/data につなぎます。 | (同じオプションの説明は上の行を参照) |
| `--env` | `BATCH_MOCK_CLI=/opt/batch-mock/efs-propagation.sh` | services.batch-mock.environment | 環境変数 BATCH_MOCK_CLI に「/opt/batch-mock/efs-propagation.sh」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `BATCH_MOCK_EFS_DIRS=/mnt/logs /mnt/data` | services.batch-mock.environment | 環境変数 BATCH_MOCK_EFS_DIRS に「/mnt/logs /mnt/data」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `/bin/sh /opt/batch-mock/efs-propagation.sh ready \|\| exit 1` | services.batch-mock.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `10s` | services.batch-mock.healthcheck.interval | 何秒おきにチェックするか: 10s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `5s` | services.batch-mock.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `5s` | services.batch-mock.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `5` | services.batch-mock.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 5 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `alpine:3.21` | services.batch-mock.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `sh -euc /bin/sh /opt/batch-mock/efs-propagation.sh init<br>exec tail -f /dev/null<br>` | services.batch-mock.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=batch-mock` ／ `docker logs batch-mock` ／ `docker inspect batch-mock`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  batch-mock:
    command:
      - sh
      - "-euc"
      - "/bin/sh /opt/batch-mock/efs-propagation.sh init\nexec tail -f /dev/null\n"
    container_name: batch-mock
    depends_on:
      efs-mock:
        condition: service_healthy
        required: true
    environment:
      BATCH_MOCK_CLI: /opt/batch-mock/efs-propagation.sh
      BATCH_MOCK_EFS_DIRS: /mnt/logs /mnt/data
    healthcheck:
      interval: 10s
      retries: 5
      start_period: 5s
      test:
        - CMD-SHELL
        - "/bin/sh /opt/batch-mock/efs-propagation.sh ready || exit 1"
      timeout: 5s
    image: "alpine:3.21"
    networks: {}
    user: "6301:6302"
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/batch-mock/efs-propagation.sh
        target: /opt/batch-mock/efs-propagation.sh
        type: bind
      - source: efs-logs
        target: /mnt/logs
        type: volume
        volume: {}
      - source: efs-data
        target: /mnt/data
        type: volume
        volume: {}
```

</details>

<a id="step-35"></a>

### STEP 35: サービス「cloudwatch-logs-mock」のコンテナ「cloudwatch-logs-mock」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.cloudwatch-logs-mock` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「wiremock/wiremock:3.13.0」からコンテナ「cloudwatch-logs-mock」を作って起動します (サービス「cloudwatch-logs-mock」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 8480:8080
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `cloudwatch-logs-mock` | services.cloudwatch-logs-mock.container_name | コンテナに「cloudwatch-logs-mock」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.cloudwatch-logs-mock.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `cloudwatch-logs-mock` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「cloudwatch-logs-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8480:8080` | services.cloudwatch-logs-mock.ports | ホスト (RHEL) の 8480 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/cloudwatch-logs-mock/mappings:/home/wiremock/mappings:ro` | services.cloudwatch-logs-mock.volumes | ホストの /opt/Container_Compose_file/compose/cloudwatch-logs-mock/mappings をコンテナの /home/wiremock/mappings に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--health-cmd` | `timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' \|\| exit 1` | services.cloudwatch-logs-mock.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `3s` | services.cloudwatch-logs-mock.healthcheck.interval | 何秒おきにチェックするか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `3s` | services.cloudwatch-logs-mock.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `5s` | services.cloudwatch-logs-mock.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `40` | services.cloudwatch-logs-mock.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 40 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `wiremock/wiremock:3.13.0` | services.cloudwatch-logs-mock.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=cloudwatch-logs-mock` ／ `docker logs cloudwatch-logs-mock` ／ `docker inspect cloudwatch-logs-mock`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  cloudwatch-logs-mock:
    container_name: cloudwatch-logs-mock
    healthcheck:
      interval: 3s
      retries: 40
      start_period: 5s
      test:
        - CMD-SHELL
        - "timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' || exit 1"
      timeout: 3s
    image: "wiremock/wiremock:3.13.0"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8480
        target: 8080
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/cloudwatch-logs-mock/mappings
        target: /home/wiremock/mappings
        type: bind
```

</details>

<a id="step-36"></a>

### STEP 36: cloudwatch-logs-mock・ecs-metadata-mock・efs-mock が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.cwagent.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 30](#step-30) と同じです)。

**このコマンドがすること**

サービス「cwagent」は depends_on で cloudwatch-logs-mock・ecs-metadata-mock・efs-mock が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 30](#step-30) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 30 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=cloudwatch-logs-mock`

<a id="step-37"></a>

### STEP 37: サービス「cwagent」のコンテナ「cwagent」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.cwagent` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest」からコンテナ「cwagent」を作って起動します (サービス「cwagent」)。

- ネットワーク: eap-adot-local_default
- マウント: 4 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 9 件 / --env-file 0 件
- depends_on (先に起動しておくもの): cloudwatch-logs-mock (service_healthy)、ecs-metadata-mock (service_healthy)、efs-mock (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `cwagent` | services.cwagent.container_name | コンテナに「cwagent」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--group-add` | `6302` | services.cwagent.group_add | そのユーザーに追加のグループ 6302 を足します (共有フォルダの書き込み権限などに使います)。 | コンテナのユーザーに、追加のグループ (補助グループ) を足します。共有フォルダの書き込み権限を、グループ番号で合わせたいときに使います。<br>（やさしく）「この係にも入っています」というバッジを追加で付けます。 |
| `--network` | `eap-adot-local_default` | services.cwagent.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `cwagent` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「cwagent」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/cwagent/cwagent-config.json:/etc/cwagentconfig/cwagent-config.json:ro` | services.cwagent.volumes | ホストの /opt/Container_Compose_file/compose/cwagent/cwagent-config.json をコンテナの /etc/cwagentconfig/cwagent-config.json に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/cwagent/aws-credentials:/root/.aws/credentials:ro` | services.cwagent.volumes | ホストの /opt/Container_Compose_file/compose/cwagent/aws-credentials をコンテナの /root/.aws/credentials に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/cwagent/verify-mount.sh:/opt/cwagent-verify/verify-mount.sh:ro` | services.cwagent.volumes | ホストの /opt/Container_Compose_file/compose/cwagent/verify-mount.sh をコンテナの /opt/cwagent-verify/verify-mount.sh に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `eap-adot-local_efs-logs:/mnt/logs:ro` | services.cwagent.volumes | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/logs につなぎます (読み取り専用)。 | (同じオプションの説明は上の行を参照) |
| `--env` | `AWS_REGION=ap-northeast-1` | services.cwagent.environment | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `CWA_VERIFY_CONFIG_DIR=/etc/cwagentconfig` | services.cwagent.environment | 環境変数 CWA_VERIFY_CONFIG_DIR に「/etc/cwagentconfig」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `CWA_VERIFY_EXPECT_MODE=775` | services.cwagent.environment | 環境変数 CWA_VERIFY_EXPECT_MODE に「775」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `CWA_VERIFY_EXPECT_OWNER=6301:6302` | services.cwagent.environment | 環境変数 CWA_VERIFY_EXPECT_OWNER に「6301:6302」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `CWA_VERIFY_MOUNTS=/mnt/logs` | services.cwagent.environment | 環境変数 CWA_VERIFY_MOUNTS に「/mnt/logs」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `CWA_VERIFY_RECHECK_COUNT=5` | services.cwagent.environment | 環境変数 CWA_VERIFY_RECHECK_COUNT に「5」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `CWA_VERIFY_RECHECK_INTERVAL=20` | services.cwagent.environment | 環境変数 CWA_VERIFY_RECHECK_INTERVAL に「20」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `CWA_VERIFY_RELAY_AGENT_LOG=1` | services.cwagent.environment | 環境変数 CWA_VERIFY_RELAY_AGENT_LOG に「1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-4567890123` | services.cwagent.environment | 環境変数 ECS_CONTAINER_METADATA_URI_V4 に「http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd64…」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `read -r v < /tmp/cwagent-verify.boot.result && [ "$v" != FAIL ]` | services.cwagent.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `5s` | services.cwagent.healthcheck.interval | 何秒おきにチェックするか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `3s` | services.cwagent.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `5s` | services.cwagent.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `12` | services.cwagent.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 12 回 | (しくみは [STEP 27](#step-27) で説明) |
| `--entrypoint` | `/bin/sh` | services.cwagent.entrypoint | 最初に動かすプログラム (ENTRYPOINT) を /bin/sh にします。残りの部分 /opt/cwagent-verify/verify-mount.sh はイメージ名の後ろに引数として書きます (docker run の --entrypoint には 1 語しか書けないため)。 | イメージの ENTRYPOINT (必ず最初に実行されるプログラム) を置き換えます。docker の --entrypoint には 1 語しか書けないため、compose の entrypoint が複数の語でできている場合、2 語目以降はイメージ名の後ろに引数として書きます (最終的に実行されるコマンドは同じです)。entrypoint を指定すると、イメージの CMD は使われなくなります (compose も docker も同じ)。<br>（やさしく）お部屋に入ったら最初にすることを、別のことに変えます。 |
| `(イメージ)` | `public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest` | services.cwagent.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `/opt/cwagent-verify/verify-mount.sh /opt/aws/amazon-cloudwatch-agent/bin/start-amazon-cloudwatch-agent` | services.cwagent.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**この STEP の注意**

- compose で entrypoint を指定すると、イメージの CMD は使われません (docker run --entrypoint も同じ)。

**確認のしかた**: `docker ps --all --filter name=cwagent` ／ `docker logs cwagent` ／ `docker inspect cwagent`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  cwagent:
    command:
      - /opt/aws/amazon-cloudwatch-agent/bin/start-amazon-cloudwatch-agent
    container_name: cwagent
    depends_on:
      cloudwatch-logs-mock:
        condition: service_healthy
        required: true
      ecs-metadata-mock:
        condition: service_healthy
        required: true
      efs-mock:
        condition: service_healthy
        required: true
    entrypoint:
      - /bin/sh
      - /opt/cwagent-verify/verify-mount.sh
    environment:
      AWS_REGION: ap-northeast-1
      CWA_VERIFY_CONFIG_DIR: /etc/cwagentconfig
      CWA_VERIFY_EXPECT_MODE: 775
      CWA_VERIFY_EXPECT_OWNER: "6301:6302"
      CWA_VERIFY_MOUNTS: /mnt/logs
      CWA_VERIFY_RECHECK_COUNT: 5
      CWA_VERIFY_RECHECK_INTERVAL: 20
      CWA_VERIFY_RELAY_AGENT_LOG: 1
      ECS_CONTAINER_METADATA_URI_V4: "http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-4567890123"
    group_add:
      - 6302
    healthcheck:
      interval: 5s
      retries: 12
      start_period: 5s
      test:
        - CMD-SHELL
        - "read -r v < /tmp/cwagent-verify.boot.result && [ \"$v\" != FAIL ]"
      timeout: 3s
    image: "public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest"
    networks: {}
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/cwagent/cwagent-config.json
        target: /etc/cwagentconfig/cwagent-config.json
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/cwagent/aws-credentials
        target: /root/.aws/credentials
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/cwagent/verify-mount.sh
        target: /opt/cwagent-verify/verify-mount.sh
        type: bind
      - read_only: true
        source: efs-logs
        target: /mnt/logs
        type: volume
        volume: {}
```

</details>

<a id="step-38"></a>

### STEP 38: サービス「sqs」のコンテナ「sqs」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.sqs` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「softwaremill/elasticmq-native:1.6.11」からコンテナ「sqs」を作って起動します (サービス「sqs」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 9324:9324、9325:9325
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `sqs` | services.sqs.container_name | コンテナに「sqs」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.sqs.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `sqs` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「sqs」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `9324:9324` | services.sqs.ports | ホスト (RHEL) の 9324 番ポート (TCP) に届いた通信を、コンテナの 9324 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `9325:9325` | services.sqs.ports | ホスト (RHEL) の 9325 番ポート (TCP) に届いた通信を、コンテナの 9325 番ポートへ転送します。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/sqs/elasticmq.conf:/opt/elasticmq.conf:ro` | services.sqs.volumes | ホストの /opt/Container_Compose_file/compose/sqs/elasticmq.conf をコンテナの /opt/elasticmq.conf に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `(イメージ)` | `softwaremill/elasticmq-native:1.6.11` | services.sqs.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=sqs` ／ `docker logs sqs` ／ `docker inspect sqs`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  sqs:
    container_name: sqs
    image: "softwaremill/elasticmq-native:1.6.11"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 9324
        target: 9324
      - mode: ingress
        protocol: tcp
        published: 9325
        target: 9325
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/sqs/elasticmq.conf
        target: /opt/elasticmq.conf
        type: bind
```

</details>

<a id="step-39"></a>

### STEP 39: サービス「pki-init」のコンテナ「pki-init」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.pki-init` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「eap-adot-local-pki-init」からコンテナ「pki-init」を作って起動します (サービス「pki-init」)。

- ネットワーク: eap-adot-local_default
- マウント: 3 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 11 件 / --env-file 0 件

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `pki-init` | services.pki-init.container_name | コンテナに「pki-init」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.pki-init.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `pki-init` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「pki-init」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `eap-adot-local_pki:/pki` | services.pki-init.volumes | 名前付きボリューム「eap-adot-local_pki」をコンテナの /pki につなぎます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/pki/provided:/provided:ro` | services.pki-init.volumes | ホストの /opt/Container_Compose_file/compose/pki/provided をコンテナの /provided に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/pki/export:/export` | services.pki-init.volumes | ホストの /opt/Container_Compose_file/compose/pki/export をコンテナの /export に直接つなぎます (バインドマウント)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_CA_CN=Local Test Self-Signed CA` | services.pki-init.environment | 環境変数 PKI_CA_CN に「Local Test Self-Signed CA」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `PKI_DAYS_CA=3650` | services.pki-init.environment | 環境変数 PKI_DAYS_CA に「3650」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_DAYS_LEAF=825` | services.pki-init.environment | 環境変数 PKI_DAYS_LEAF に「825」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_EXPORT_DIR=/export` | services.pki-init.environment | 環境変数 PKI_EXPORT_DIR に「/export」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_EXPORT_KEY=1` | services.pki-init.environment | 環境変数 PKI_EXPORT_KEY に「1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_FORCE_REGENERATE=0` | services.pki-init.environment | 環境変数 PKI_FORCE_REGENERATE に「0」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_KEYSTORE_PASSWORD=changeit` | services.pki-init.environment | 環境変数 PKI_KEYSTORE_PASSWORD に「changeit」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_MODE=auto` | services.pki-init.environment | 環境変数 PKI_MODE に「auto」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_PROVIDED_DIR=/provided` | services.pki-init.environment | 環境変数 PKI_PROVIDED_DIR に「/provided」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_ROOT=/pki` | services.pki-init.environment | 環境変数 PKI_ROOT に「/pki」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_TRUST_LOCAL_CA=1` | services.pki-init.environment | 環境変数 PKI_TRUST_LOCAL_CA に「1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `test -f /pki/.pki-ready && test -f /pki/ca/cacert.crt && test -f /pki/ca/verify-bundle.crt && test -f /pki/secure-api/server.p12 && test -f /pki/alb/selfsigned/server.key && test -f /pki/alb/ca-issued/server.key && test -f /pki/rds-proxy/server.key && test -f /pki/trust/cacert.crt` | services.pki-init.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `3s` | services.pki-init.healthcheck.interval | 何秒おきにチェックするか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `3s` | services.pki-init.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `2s` | services.pki-init.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 2s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `20` | services.pki-init.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 20 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `eap-adot-local-pki-init` | services.pki-init.build | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=pki-init` ／ `docker logs pki-init` ／ `docker inspect pki-init`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  pki-init:
    build:
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/pki
      dockerfile: Dockerfile
    container_name: pki-init
    environment:
      PKI_CA_CN: Local Test Self-Signed CA
      PKI_DAYS_CA: 3650
      PKI_DAYS_LEAF: 825
      PKI_EXPORT_DIR: /export
      PKI_EXPORT_KEY: 1
      PKI_FORCE_REGENERATE: 0
      PKI_KEYSTORE_PASSWORD: changeit
      PKI_MODE: auto
      PKI_PROVIDED_DIR: /provided
      PKI_ROOT: /pki
      PKI_TRUST_LOCAL_CA: 1
    healthcheck:
      interval: 3s
      retries: 20
      start_period: 2s
      test:
        - CMD-SHELL
        - "test -f /pki/.pki-ready && test -f /pki/ca/cacert.crt && test -f /pki/ca/verify-bundle.crt && test -f /pki/secure-api/server.p12 && test -f /pki/alb/selfsigned/server.key && test -f /pki/alb/ca-issued/server.key && test -f /pki/rds-proxy/server.key && test -f /pki/trust/cacert.crt"
      timeout: 3s
    networks: {}
    volumes:
      - source: pki
        target: /pki
        type: volume
        volume: {}
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/pki/provided
        target: /provided
        type: bind
      - bind: {}
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/pki/export
        target: /export
        type: bind
```

</details>

<a id="step-40"></a>

### STEP 40: pki-init が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.mysql.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 30](#step-30) と同じです)。

**このコマンドがすること**

サービス「mysql」は depends_on で pki-init が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 30](#step-30) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 30 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=pki-init`

<a id="step-41"></a>

### STEP 41: サービス「mysql」のコンテナ「mysql」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.mysql` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「mysql:8.4.7」からコンテナ「mysql」を作って起動します (サービス「mysql」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 3306:3306
- マウント: 4 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 5 件 / --env-file 0 件
- depends_on (先に起動しておくもの): pki-init (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `mysql` | services.mysql.container_name | コンテナに「mysql」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.mysql.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `mysql` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「mysql」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `3306:3306` | services.mysql.ports | ホスト (RHEL) の 3306 番ポート (TCP) に届いた通信を、コンテナの 3306 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/mysql/init.sql:/docker-entrypoint-initdb.d/10-init.sql:ro` | services.mysql.volumes | ホストの /opt/Container_Compose_file/compose/mysql/init.sql をコンテナの /docker-entrypoint-initdb.d/10-init.sql に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/mysql/init-infdb.sh:/docker-entrypoint-initdb.d/20-init-infdb.sh:ro` | services.mysql.volumes | ホストの /opt/Container_Compose_file/compose/mysql/init-infdb.sh をコンテナの /docker-entrypoint-initdb.d/20-init-infdb.sh に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `eap-adot-local_pki:/mnt/pki:ro` | services.mysql.volumes | 名前付きボリューム「eap-adot-local_pki」をコンテナの /mnt/pki につなぎます (読み取り専用)。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `eap-adot-local_mysql-data:/var/lib/mysql` | services.mysql.volumes | 名前付きボリューム「eap-adot-local_mysql-data」をコンテナの /var/lib/mysql につなぎます。 | (同じオプションの説明は上の行を参照) |
| `--env` | `INFDB_PASSWORD=ChangeMe_infdb_P@ss123` | services.mysql.environment | 環境変数 INFDB_PASSWORD に「ChangeMe_infdb_P@ss123」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `MYSQL_DATABASE=appdb` | services.mysql.environment | 環境変数 MYSQL_DATABASE に「appdb」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `MYSQL_PASSWORD=ChangeMe_appdb_P@ss123` | services.mysql.environment | 環境変数 MYSQL_PASSWORD に「ChangeMe_appdb_P@ss123」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `MYSQL_ROOT_PASSWORD=localdev-root-change-me` | services.mysql.environment | 環境変数 MYSQL_ROOT_PASSWORD に「localdev-root-change-me」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `MYSQL_USER=appuser` | services.mysql.environment | 環境変数 MYSQL_USER に「appuser」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `mysql --ssl-mode=REQUIRED -h 127.0.0.1 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -D"$MYSQL_DATABASE" -e 'SELECT 1' >/dev/null 2>&1` | services.mysql.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `5s` | services.mysql.healthcheck.interval | 何秒おきにチェックするか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `5s` | services.mysql.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `20s` | services.mysql.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 20s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `60` | services.mysql.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 60 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `mysql:8.4.7` | services.mysql.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `--auto_generate_certs=OFF --ssl_cert=/mnt/pki/rds-proxy/fullchain.crt --ssl_key=/mnt/pki/rds-proxy/server.key --ssl_ca=/mnt/pki/ca/verify-bundle.crt --require_secure_transport=ON --tls_version=TLSv1.2,TLSv1.3` | services.mysql.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=mysql` ／ `docker logs mysql` ／ `docker inspect mysql`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  mysql:
    command:
      - "--auto_generate_certs=OFF"
      - "--ssl_cert=/mnt/pki/rds-proxy/fullchain.crt"
      - "--ssl_key=/mnt/pki/rds-proxy/server.key"
      - "--ssl_ca=/mnt/pki/ca/verify-bundle.crt"
      - "--require_secure_transport=ON"
      - "--tls_version=TLSv1.2,TLSv1.3"
    container_name: mysql
    depends_on:
      pki-init:
        condition: service_healthy
        required: true
    environment:
      INFDB_PASSWORD: "ChangeMe_infdb_P@ss123"
      MYSQL_DATABASE: appdb
      MYSQL_PASSWORD: "ChangeMe_appdb_P@ss123"
      MYSQL_ROOT_PASSWORD: localdev-root-change-me
      MYSQL_USER: appuser
    healthcheck:
      interval: 5s
      retries: 60
      start_period: 20s
      test:
        - CMD-SHELL
        - "mysql --ssl-mode=REQUIRED -h 127.0.0.1 -u\"$MYSQL_USER\" -p\"$MYSQL_PASSWORD\" -D\"$MYSQL_DATABASE\" -e 'SELECT 1' >/dev/null 2>&1"
      timeout: 5s
    image: "mysql:8.4.7"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 3306
        target: 3306
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/mysql/init.sql
        target: /docker-entrypoint-initdb.d/10-init.sql
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/mysql/init-infdb.sh
        target: /docker-entrypoint-initdb.d/20-init-infdb.sh
        type: bind
      - read_only: true
        source: pki
        target: /mnt/pki
        type: volume
        volume: {}
      - source: mysql-data
        target: /var/lib/mysql
        type: volume
        volume: {}
```

</details>

<a id="step-42"></a>

### STEP 42: adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・svf-mock・valkey が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.backend.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 30](#step-30) と同じです)。

**このコマンドがすること**

サービス「backend」は depends_on で adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・svf-mock・valkey が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 30](#step-30) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 30 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=adot-collector`

<a id="step-43"></a>

### STEP 43: サービス「backend」のコンテナ「backend」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.backend` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「eap-adot-local-backend」からコンテナ「backend」を作って起動します (サービス「backend」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 8180:8180
- マウント: 3 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 25 件 / --env-file 0 件
- depends_on (先に起動しておくもの): adot-collector (service_healthy)、ecs-metadata-mock (service_healthy)、efs-mock (service_healthy)、mysql (service_healthy)、pki-init (service_healthy)、svf-mock (service_healthy)、valkey (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `backend` | services.backend.container_name | コンテナに「backend」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--group-add` | `6302` | services.backend.group_add | そのユーザーに追加のグループ 6302 を足します (共有フォルダの書き込み権限などに使います)。 | (しくみは [STEP 37](#step-37) で説明) |
| `--network` | `eap-adot-local_default` | services.backend.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `backend` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「backend」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8180:8180` | services.backend.ports | ホスト (RHEL) の 8180 番ポート (TCP) に届いた通信を、コンテナの 8180 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `eap-adot-local_efs-logs:/mnt/logs` | services.backend.volumes | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/logs につなぎます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `eap-adot-local_efs-data:/mnt/data` | services.backend.volumes | 名前付きボリューム「eap-adot-local_efs-data」をコンテナの /mnt/data につなぎます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `eap-adot-local_pki:/mnt/pki:ro` | services.backend.volumes | 名前付きボリューム「eap-adot-local_pki」をコンテナの /mnt/pki につなぎます (読み取り専用)。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ASYNC_QUEUE_NAME=app-async-queue` | services.backend.environment | 環境変数 ASYNC_QUEUE_NAME に「app-async-queue」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `ASYNC_SQS_ENDPOINT=http://sqs:9324` | services.backend.environment | 環境変数 ASYNC_SQS_ENDPOINT に「http://sqs:9324」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `AWS_REGION=ap-northeast-1` | services.backend.environment | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_HOST=mysql` | services.backend.environment | 環境変数 DB_HOST に「mysql」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_NAME=appdb` | services.backend.environment | 環境変数 DB_NAME に「appdb」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_PASSWORD=ChangeMe_appdb_P@ss123` | services.backend.environment | 環境変数 DB_PASSWORD に「ChangeMe_appdb_P@ss123」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_PORT=3306` | services.backend.environment | 環境変数 DB_PORT に「3306」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_SSL_MODE=VERIFY_IDENTITY` | services.backend.environment | 環境変数 DB_SSL_MODE に「VERIFY_IDENTITY」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_USER=appuser` | services.backend.environment | 環境変数 DB_USER に「appuser」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-2345678901` | services.backend.environment | 環境変数 ECS_CONTAINER_METADATA_URI_V4 に「http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd64…」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `JBOSS_TRUSTSTORE_FILE=/opt/server/standalone/configuration/jboss-truststore.p12` | services.backend.environment | 環境変数 JBOSS_TRUSTSTORE_FILE に「/opt/server/standalone/configuration/jboss-truststore.p12」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `JBOSS_TRUSTSTORE_PASSWORD=changeit` | services.backend.environment | 環境変数 JBOSS_TRUSTSTORE_PASSWORD に「changeit」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_EXPORTER_OTLP_ENDPOINT=http://adot-collector:4318` | services.backend.environment | 環境変数 OTEL_EXPORTER_OTLP_ENDPOINT に「http://adot-collector:4318」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` | services.backend.environment | 環境変数 OTEL_EXPORTER_OTLP_PROTOCOL に「http/protobuf」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_RESOURCE_ATTRIBUTES=service.namespace=myapp,service.version=local,deployment.environment=local,aws.ecs.service.name=local-compose` | services.backend.environment | 環境変数 OTEL_RESOURCE_ATTRIBUTES に「service.namespace=myapp,service.version=local,deployment.env…」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_SERVICE_NAME=myapp-back` | services.backend.environment | 環境変数 OTEL_SERVICE_NAME に「myapp-back」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_TRACES_SAMPLER=parentbased_always_on` | services.backend.environment | 環境変数 OTEL_TRACES_SAMPLER に「parentbased_always_on」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_TRUST_DIR=/mnt/pki/trust` | services.backend.environment | 環境変数 PKI_TRUST_DIR に「/mnt/pki/trust」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PORT_OFFSET=100` | services.backend.environment | 環境変数 PORT_OFFSET に「100」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `SECURE_API_URL=https://secure-api:8443/api/v1/ping` | services.backend.environment | 環境変数 SECURE_API_URL に「https://secure-api:8443/api/v1/ping」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `SECURE_API_VIA_ALB_URL=https://alb/secure/v1/ping` | services.backend.environment | 環境変数 SECURE_API_VIA_ALB_URL に「https://alb/secure/v1/ping」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `SVF_BASE_URL=http://svf-mock:8080` | services.backend.environment | 環境変数 SVF_BASE_URL に「http://svf-mock:8080」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `TX_NODE_ID=back-local-1` | services.backend.environment | 環境変数 TX_NODE_ID に「back-local-1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `VALKEY_HOST=valkey` | services.backend.environment | 環境変数 VALKEY_HOST に「valkey」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `VALKEY_PORT=6379` | services.backend.environment | 環境変数 VALKEY_PORT に「6379」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `curl -fs http://127.0.0.1:8180/ >/dev/null \|\| exit 1` | services.backend.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `30s` | services.backend.healthcheck.interval | 何秒おきにチェックするか: 30s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `5s` | services.backend.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `2m0s` | services.backend.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 2m0s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `3` | services.backend.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 3 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `eap-adot-local-backend` | services.backend.build | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=backend` ／ `docker logs backend` ／ `docker inspect backend`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  backend:
    build:
      args:
        EAP_BASE_IMAGE: "your-registry.example.com/base/eap81-openjdk21-ubi9:latest"
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/docker
      dockerfile: back/Dockerfile
    container_name: backend
    depends_on:
      adot-collector:
        condition: service_healthy
        required: true
      ecs-metadata-mock:
        condition: service_healthy
        required: true
      efs-mock:
        condition: service_healthy
        required: true
      mysql:
        condition: service_healthy
        required: true
      pki-init:
        condition: service_healthy
        required: true
      svf-mock:
        condition: service_healthy
        required: true
      valkey:
        condition: service_healthy
        required: true
    environment:
      ASYNC_QUEUE_NAME: app-async-queue
      ASYNC_SQS_ENDPOINT: "http://sqs:9324"
      AWS_REGION: ap-northeast-1
      DB_HOST: mysql
      DB_NAME: appdb
      DB_PASSWORD: "ChangeMe_appdb_P@ss123"
      DB_PORT: 3306
      DB_SSL_MODE: VERIFY_IDENTITY
      DB_USER: appuser
      ECS_CONTAINER_METADATA_URI_V4: "http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-2345678901"
      JBOSS_TRUSTSTORE_FILE: /opt/server/standalone/configuration/jboss-truststore.p12
      JBOSS_TRUSTSTORE_PASSWORD: changeit
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://adot-collector:4318"
      OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
      OTEL_RESOURCE_ATTRIBUTES: "service.namespace=myapp,service.version=local,deployment.environment=local,aws.ecs.service.name=local-compose"
      OTEL_SERVICE_NAME: myapp-back
      OTEL_TRACES_SAMPLER: parentbased_always_on
      PKI_TRUST_DIR: /mnt/pki/trust
      PORT_OFFSET: 100
      SECURE_API_URL: "https://secure-api:8443/api/v1/ping"
      SECURE_API_VIA_ALB_URL: "https://alb/secure/v1/ping"
      SVF_BASE_URL: "http://svf-mock:8080"
      TX_NODE_ID: back-local-1
      VALKEY_HOST: valkey
      VALKEY_PORT: 6379
    group_add:
      - 6302
    healthcheck:
      interval: 30s
      retries: 3
      start_period: 2m0s
      test:
        - CMD-SHELL
        - "curl -fs http://127.0.0.1:8180/ >/dev/null || exit 1"
      timeout: 5s
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8180
        target: 8180
    volumes:
      - source: efs-logs
        target: /mnt/logs
        type: volume
        volume: {}
      - source: efs-data
        target: /mnt/data
        type: volume
        volume: {}
      - read_only: true
        source: pki
        target: /mnt/pki
        type: volume
        volume: {}
```

</details>

<a id="step-44"></a>

### STEP 44: adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・valkey が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.frontend.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 30](#step-30) と同じです)。

**このコマンドがすること**

サービス「frontend」は depends_on で adot-collector・ecs-metadata-mock・efs-mock・mysql・pki-init・valkey が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 30](#step-30) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 30 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=adot-collector`

<a id="step-45"></a>

### STEP 45: サービス「frontend」のコンテナ「frontend」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.frontend` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「eap-adot-local-frontend」からコンテナ「frontend」を作って起動します (サービス「frontend」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 8080:8080
- マウント: 3 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 24 件 / --env-file 0 件
- depends_on (先に起動しておくもの): adot-collector (service_healthy)、backend (service_started)、ecs-metadata-mock (service_healthy)、efs-mock (service_healthy)、mysql (service_healthy)、pki-init (service_healthy)、valkey (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `frontend` | services.frontend.container_name | コンテナに「frontend」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--group-add` | `6302` | services.frontend.group_add | そのユーザーに追加のグループ 6302 を足します (共有フォルダの書き込み権限などに使います)。 | (しくみは [STEP 37](#step-37) で説明) |
| `--network` | `eap-adot-local_default` | services.frontend.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `frontend` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「frontend」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8080:8080` | services.frontend.ports | ホスト (RHEL) の 8080 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `eap-adot-local_efs-logs:/mnt/logs` | services.frontend.volumes | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/logs につなぎます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `eap-adot-local_efs-data:/mnt/data` | services.frontend.volumes | 名前付きボリューム「eap-adot-local_efs-data」をコンテナの /mnt/data につなぎます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `eap-adot-local_pki:/mnt/pki:ro` | services.frontend.volumes | 名前付きボリューム「eap-adot-local_pki」をコンテナの /mnt/pki につなぎます (読み取り専用)。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ASYNC_QUEUE_NAME=app-async-queue` | services.frontend.environment | 環境変数 ASYNC_QUEUE_NAME に「app-async-queue」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `ASYNC_SQS_ENDPOINT=http://sqs:9324` | services.frontend.environment | 環境変数 ASYNC_SQS_ENDPOINT に「http://sqs:9324」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `AWS_REGION=ap-northeast-1` | services.frontend.environment | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `BACK_BASE_URL=http://backend:8180` | services.frontend.environment | 環境変数 BACK_BASE_URL に「http://backend:8180」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_HOST=mysql` | services.frontend.environment | 環境変数 DB_HOST に「mysql」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_NAME=appdb` | services.frontend.environment | 環境変数 DB_NAME に「appdb」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_PASSWORD=ChangeMe_appdb_P@ss123` | services.frontend.environment | 環境変数 DB_PASSWORD に「ChangeMe_appdb_P@ss123」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_PORT=3306` | services.frontend.environment | 環境変数 DB_PORT に「3306」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_SSL_MODE=VERIFY_IDENTITY` | services.frontend.environment | 環境変数 DB_SSL_MODE に「VERIFY_IDENTITY」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_USER=appuser` | services.frontend.environment | 環境変数 DB_USER に「appuser」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-1234567890` | services.frontend.environment | 環境変数 ECS_CONTAINER_METADATA_URI_V4 に「http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd64…」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `JBOSS_TRUSTSTORE_FILE=/opt/server/standalone/configuration/jboss-truststore.p12` | services.frontend.environment | 環境変数 JBOSS_TRUSTSTORE_FILE に「/opt/server/standalone/configuration/jboss-truststore.p12」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `JBOSS_TRUSTSTORE_PASSWORD=changeit` | services.frontend.environment | 環境変数 JBOSS_TRUSTSTORE_PASSWORD に「changeit」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_EXPORTER_OTLP_ENDPOINT=http://adot-collector:4318` | services.frontend.environment | 環境変数 OTEL_EXPORTER_OTLP_ENDPOINT に「http://adot-collector:4318」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` | services.frontend.environment | 環境変数 OTEL_EXPORTER_OTLP_PROTOCOL に「http/protobuf」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_RESOURCE_ATTRIBUTES=service.namespace=myapp,service.version=local,deployment.environment=local,aws.ecs.service.name=local-compose` | services.frontend.environment | 環境変数 OTEL_RESOURCE_ATTRIBUTES に「service.namespace=myapp,service.version=local,deployment.env…」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_SERVICE_NAME=myapp-front` | services.frontend.environment | 環境変数 OTEL_SERVICE_NAME に「myapp-front」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `OTEL_TRACES_SAMPLER=parentbased_always_on` | services.frontend.environment | 環境変数 OTEL_TRACES_SAMPLER に「parentbased_always_on」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PKI_TRUST_DIR=/mnt/pki/trust` | services.frontend.environment | 環境変数 PKI_TRUST_DIR に「/mnt/pki/trust」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `SECURE_API_URL=https://secure-api:8443/api/v1/ping` | services.frontend.environment | 環境変数 SECURE_API_URL に「https://secure-api:8443/api/v1/ping」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `SECURE_API_VIA_ALB_URL=https://alb/secure/v1/ping` | services.frontend.environment | 環境変数 SECURE_API_VIA_ALB_URL に「https://alb/secure/v1/ping」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `TX_NODE_ID=front-local-1` | services.frontend.environment | 環境変数 TX_NODE_ID に「front-local-1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `VALKEY_HOST=valkey` | services.frontend.environment | 環境変数 VALKEY_HOST に「valkey」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `VALKEY_PORT=6379` | services.frontend.environment | 環境変数 VALKEY_PORT に「6379」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `curl -fs http://127.0.0.1:8080/ >/dev/null \|\| exit 1` | services.frontend.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `30s` | services.frontend.healthcheck.interval | 何秒おきにチェックするか: 30s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `5s` | services.frontend.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `2m0s` | services.frontend.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 2m0s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `3` | services.frontend.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 3 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `eap-adot-local-frontend` | services.frontend.build | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=frontend` ／ `docker logs frontend` ／ `docker inspect frontend`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  frontend:
    build:
      args:
        EAP_BASE_IMAGE: "your-registry.example.com/base/eap81-openjdk21-ubi9:latest"
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/docker
      dockerfile: front/Dockerfile
    container_name: frontend
    depends_on:
      adot-collector:
        condition: service_healthy
        required: true
      backend:
        condition: service_started
        required: true
      ecs-metadata-mock:
        condition: service_healthy
        required: true
      efs-mock:
        condition: service_healthy
        required: true
      mysql:
        condition: service_healthy
        required: true
      pki-init:
        condition: service_healthy
        required: true
      valkey:
        condition: service_healthy
        required: true
    environment:
      ASYNC_QUEUE_NAME: app-async-queue
      ASYNC_SQS_ENDPOINT: "http://sqs:9324"
      AWS_REGION: ap-northeast-1
      BACK_BASE_URL: "http://backend:8180"
      DB_HOST: mysql
      DB_NAME: appdb
      DB_PASSWORD: "ChangeMe_appdb_P@ss123"
      DB_PORT: 3306
      DB_SSL_MODE: VERIFY_IDENTITY
      DB_USER: appuser
      ECS_CONTAINER_METADATA_URI_V4: "http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-1234567890"
      JBOSS_TRUSTSTORE_FILE: /opt/server/standalone/configuration/jboss-truststore.p12
      JBOSS_TRUSTSTORE_PASSWORD: changeit
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://adot-collector:4318"
      OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
      OTEL_RESOURCE_ATTRIBUTES: "service.namespace=myapp,service.version=local,deployment.environment=local,aws.ecs.service.name=local-compose"
      OTEL_SERVICE_NAME: myapp-front
      OTEL_TRACES_SAMPLER: parentbased_always_on
      PKI_TRUST_DIR: /mnt/pki/trust
      SECURE_API_URL: "https://secure-api:8443/api/v1/ping"
      SECURE_API_VIA_ALB_URL: "https://alb/secure/v1/ping"
      TX_NODE_ID: front-local-1
      VALKEY_HOST: valkey
      VALKEY_PORT: 6379
    group_add:
      - 6302
    healthcheck:
      interval: 30s
      retries: 3
      start_period: 2m0s
      test:
        - CMD-SHELL
        - "curl -fs http://127.0.0.1:8080/ >/dev/null || exit 1"
      timeout: 5s
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8080
        target: 8080
    volumes:
      - source: efs-logs
        target: /mnt/logs
        type: volume
        volume: {}
      - source: efs-data
        target: /mnt/data
        type: volume
        volume: {}
      - read_only: true
        source: pki
        target: /mnt/pki
        type: volume
        volume: {}
```

</details>

<a id="step-46"></a>

### STEP 46: サービス「alb-healthcheck」のコンテナ「alb-healthcheck」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.alb-healthcheck` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「python:3.12-slim」からコンテナ「alb-healthcheck」を作って起動します (サービス「alb-healthcheck」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 8580:8080
- マウント: 2 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 5 件 / --env-file 0 件
- depends_on (先に起動しておくもの): backend (service_started)、frontend (service_started)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `alb-healthcheck` | services.alb-healthcheck.container_name | コンテナに「alb-healthcheck」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.alb-healthcheck.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `alb-healthcheck` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「alb-healthcheck」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8580:8080` | services.alb-healthcheck.ports | ホスト (RHEL) の 8580 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/alb-healthcheck/healthcheck.py:/opt/alb-healthcheck/healthcheck.py:ro` | services.alb-healthcheck.volumes | ホストの /opt/Container_Compose_file/compose/alb-healthcheck/healthcheck.py をコンテナの /opt/alb-healthcheck/healthcheck.py に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/alb-healthcheck/targets.json:/etc/alb-healthcheck/targets.json:ro` | services.alb-healthcheck.volumes | ホストの /opt/Container_Compose_file/compose/alb-healthcheck/targets.json をコンテナの /etc/alb-healthcheck/targets.json に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_HEALTHCHECK_CLI=/opt/alb-healthcheck/healthcheck.py` | services.alb-healthcheck.environment | 環境変数 ALB_HEALTHCHECK_CLI に「/opt/alb-healthcheck/healthcheck.py」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `ALB_HEALTHCHECK_HISTORY_LIMIT=10` | services.alb-healthcheck.environment | 環境変数 ALB_HEALTHCHECK_HISTORY_LIMIT に「10」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_HEALTHCHECK_LISTEN_PORT=8080` | services.alb-healthcheck.environment | 環境変数 ALB_HEALTHCHECK_LISTEN_PORT に「8080」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_HEALTHCHECK_TARGETS_FILE=/etc/alb-healthcheck/targets.json` | services.alb-healthcheck.environment | 環境変数 ALB_HEALTHCHECK_TARGETS_FILE に「/etc/alb-healthcheck/targets.json」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PYTHONUNBUFFERED=1` | services.alb-healthcheck.environment | 環境変数 PYTHONUNBUFFERED に「1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `python3 /opt/alb-healthcheck/healthcheck.py ready \|\| exit 1` | services.alb-healthcheck.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `10s` | services.alb-healthcheck.healthcheck.interval | 何秒おきにチェックするか: 10s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `5s` | services.alb-healthcheck.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `5s` | services.alb-healthcheck.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `5` | services.alb-healthcheck.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 5 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `python:3.12-slim` | services.alb-healthcheck.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `python3 /opt/alb-healthcheck/healthcheck.py serve` | services.alb-healthcheck.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=alb-healthcheck` ／ `docker logs alb-healthcheck` ／ `docker inspect alb-healthcheck`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  alb-healthcheck:
    command:
      - python3
      - /opt/alb-healthcheck/healthcheck.py
      - serve
    container_name: alb-healthcheck
    depends_on:
      backend:
        condition: service_started
        required: true
      frontend:
        condition: service_started
        required: true
    environment:
      ALB_HEALTHCHECK_CLI: /opt/alb-healthcheck/healthcheck.py
      ALB_HEALTHCHECK_HISTORY_LIMIT: 10
      ALB_HEALTHCHECK_LISTEN_PORT: 8080
      ALB_HEALTHCHECK_TARGETS_FILE: /etc/alb-healthcheck/targets.json
      PYTHONUNBUFFERED: 1
    healthcheck:
      interval: 10s
      retries: 5
      start_period: 5s
      test:
        - CMD-SHELL
        - "python3 /opt/alb-healthcheck/healthcheck.py ready || exit 1"
      timeout: 5s
    image: "python:3.12-slim"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8580
        target: 8080
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/alb-healthcheck/healthcheck.py
        target: /opt/alb-healthcheck/healthcheck.py
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/alb-healthcheck/targets.json
        target: /etc/alb-healthcheck/targets.json
        type: bind
```

</details>

<a id="step-47"></a>

### STEP 47: pki-init が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.alb-front.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 30](#step-30) と同じです)。

**このコマンドがすること**

サービス「alb-front」は depends_on で pki-init が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 30](#step-30) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 30 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=pki-init`

<a id="step-48"></a>

### STEP 48: サービス「alb-front」のコンテナ「alb-front」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.alb-front` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「eap-adot-local-alb-front:with-healthcheck」からコンテナ「alb-front」を作って起動します (サービス「alb-front」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 8443:8443、8581:8081
- マウント: 2 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 12 件 / --env-file 0 件
- depends_on (先に起動しておくもの): frontend (service_started)、pki-init (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `alb-front` | services.alb-front.container_name | コンテナに「alb-front」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.alb-front.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `alb-front` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「alb-front」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8443:8443` | services.alb-front.ports | ホスト (RHEL) の 8443 番ポート (TCP) に届いた通信を、コンテナの 8443 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8581:8081` | services.alb-front.ports | ホスト (RHEL) の 8581 番ポート (TCP) に届いた通信を、コンテナの 8081 番ポートへ転送します。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/alb-front/alb-front.py:/opt/alb-front/alb-front.py:ro` | services.alb-front.volumes | ホストの /opt/Container_Compose_file/compose/alb-front/alb-front.py をコンテナの /opt/alb-front/alb-front.py に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `eap-adot-local_pki:/pki:ro` | services.alb-front.volumes | 名前付きボリューム「eap-adot-local_pki」をコンテナの /pki につなぎます (読み取り専用)。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_ADMIN_PORT=8081` | services.alb-front.environment | 環境変数 ALB_FRONT_ADMIN_PORT に「8081」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `ALB_FRONT_CA_BUNDLE=/pki/ca/verify-bundle.crt` | services.alb-front.environment | 環境変数 ALB_FRONT_CA_BUNDLE に「/pki/ca/verify-bundle.crt」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_CHECK_HOST=localhost` | services.alb-front.environment | 環境変数 ALB_FRONT_CHECK_HOST に「localhost」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_CHECK_PATH=/iwinmichl/api/redirect-check/redirect` | services.alb-front.environment | 環境変数 ALB_FRONT_CHECK_PATH に「/iwinmichl/api/redirect-check/redirect」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_CLI=/opt/alb-front/alb-front.py` | services.alb-front.environment | 環境変数 ALB_FRONT_CLI に「/opt/alb-front/alb-front.py」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_CONNECT_TIMEOUT=10` | services.alb-front.environment | 環境変数 ALB_FRONT_CONNECT_TIMEOUT に「10」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_HTTPS_PORT=8443` | services.alb-front.environment | 環境変数 ALB_FRONT_HTTPS_PORT に「8443」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_IDLE_TIMEOUT=60` | services.alb-front.environment | 環境変数 ALB_FRONT_IDLE_TIMEOUT に「60」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_TARGET=http://frontend:8080` | services.alb-front.environment | 環境変数 ALB_FRONT_TARGET に「http://frontend:8080」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_TLS_CERT=/pki/alb/ca-issued/fullchain.crt` | services.alb-front.environment | 環境変数 ALB_FRONT_TLS_CERT に「/pki/alb/ca-issued/fullchain.crt」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ALB_FRONT_TLS_KEY=/pki/alb/ca-issued/server.key` | services.alb-front.environment | 環境変数 ALB_FRONT_TLS_KEY に「/pki/alb/ca-issued/server.key」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `PYTHONUNBUFFERED=1` | services.alb-front.environment | 環境変数 PYTHONUNBUFFERED に「1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `eap-adot-local-alb-front:with-healthcheck` | services.alb-front.image | ヘルスチェック入りの派生イメージ (元: python:3.12-slim) です。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `python3 /opt/alb-front/alb-front.py serve` | services.alb-front.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=alb-front` ／ `docker logs alb-front` ／ `docker inspect alb-front`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  alb-front:
    command:
      - python3
      - /opt/alb-front/alb-front.py
      - serve
    container_name: alb-front
    depends_on:
      frontend:
        condition: service_started
        required: true
      pki-init:
        condition: service_healthy
        required: true
    environment:
      ALB_FRONT_ADMIN_PORT: 8081
      ALB_FRONT_CA_BUNDLE: /pki/ca/verify-bundle.crt
      ALB_FRONT_CHECK_HOST: localhost
      ALB_FRONT_CHECK_PATH: /iwinmichl/api/redirect-check/redirect
      ALB_FRONT_CLI: /opt/alb-front/alb-front.py
      ALB_FRONT_CONNECT_TIMEOUT: 10
      ALB_FRONT_HTTPS_PORT: 8443
      ALB_FRONT_IDLE_TIMEOUT: 60
      ALB_FRONT_TARGET: "http://frontend:8080"
      ALB_FRONT_TLS_CERT: /pki/alb/ca-issued/fullchain.crt
      ALB_FRONT_TLS_KEY: /pki/alb/ca-issued/server.key
      PYTHONUNBUFFERED: 1
    healthcheck:
      interval: 10s
      retries: 5
      start_period: 5s
      test:
        - CMD
        - python3
        - /opt/alb-front/alb-front.py
        - ready
      timeout: 5s
    image: "python:3.12-slim"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8443
        target: 8443
      - mode: ingress
        protocol: tcp
        published: 8581
        target: 8081
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/alb-front/alb-front.py
        target: /opt/alb-front/alb-front.py
        type: bind
      - read_only: true
        source: pki
        target: /pki
        type: volume
        volume: {}
```

</details>

<a id="step-49"></a>

### STEP 49: pki-init が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.secure-api.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 30](#step-30) と同じです)。

**このコマンドがすること**

サービス「secure-api」は depends_on で pki-init が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 30](#step-30) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 30 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=pki-init`

<a id="step-50"></a>

### STEP 50: サービス「secure-api」のコンテナ「secure-api」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.secure-api` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「wiremock/wiremock:3.13.0」からコンテナ「secure-api」を作って起動します (サービス「secure-api」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 8543:8443
- マウント: 2 件 (データの置き場所をコンテナにつなぎます)
- depends_on (先に起動しておくもの): pki-init (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `secure-api` | services.secure-api.container_name | コンテナに「secure-api」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.secure-api.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `secure-api` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「secure-api」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `8543:8443` | services.secure-api.ports | ホスト (RHEL) の 8543 番ポート (TCP) に届いた通信を、コンテナの 8443 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/secure-api/mappings:/home/wiremock/mappings:ro` | services.secure-api.volumes | ホストの /opt/Container_Compose_file/compose/secure-api/mappings をコンテナの /home/wiremock/mappings に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `eap-adot-local_pki:/pki:ro` | services.secure-api.volumes | 名前付きボリューム「eap-adot-local_pki」をコンテナの /pki につなぎます (読み取り専用)。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `timeout 2 bash -c '</dev/tcp/127.0.0.1/8443' \|\| exit 1` | services.secure-api.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `3s` | services.secure-api.healthcheck.interval | 何秒おきにチェックするか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `3s` | services.secure-api.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `5s` | services.secure-api.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `40` | services.secure-api.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 40 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `wiremock/wiremock:3.13.0` | services.secure-api.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `--https-port=8443 --https-keystore=/pki/secure-api/server.p12 --keystore-type=PKCS12 --keystore-password=changeit --key-manager-password=changeit --disable-http --verbose` | services.secure-api.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=secure-api` ／ `docker logs secure-api` ／ `docker inspect secure-api`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  secure-api:
    command:
      - "--https-port=8443"
      - "--https-keystore=/pki/secure-api/server.p12"
      - "--keystore-type=PKCS12"
      - "--keystore-password=changeit"
      - "--key-manager-password=changeit"
      - "--disable-http"
      - "--verbose"
    container_name: secure-api
    depends_on:
      pki-init:
        condition: service_healthy
        required: true
    healthcheck:
      interval: 3s
      retries: 40
      start_period: 5s
      test:
        - CMD-SHELL
        - "timeout 2 bash -c '</dev/tcp/127.0.0.1/8443' || exit 1"
      timeout: 3s
    image: "wiremock/wiremock:3.13.0"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8543
        target: 8443
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/secure-api/mappings
        target: /home/wiremock/mappings
        type: bind
      - read_only: true
        source: pki
        target: /pki
        type: volume
        volume: {}
```

</details>

<a id="step-51"></a>

### STEP 51: サービス「maintenance-lambda」のコンテナ「maintenance-lambda」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.maintenance-lambda` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「public.ecr.aws/lambda/python:3.12」からコンテナ「maintenance-lambda」を作って起動します (サービス「maintenance-lambda」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 9001:8080
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 3 件 / --env-file 0 件

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `maintenance-lambda` | services.maintenance-lambda.container_name | コンテナに「maintenance-lambda」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.maintenance-lambda.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `maintenance-lambda` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「maintenance-lambda」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `9001:8080` | services.maintenance-lambda.ports | ホスト (RHEL) の 9001 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/maintenance-lambda/app:/var/task:ro` | services.maintenance-lambda.volumes | ホストの /opt/Container_Compose_file/compose/maintenance-lambda/app をコンテナの /var/task に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--env` | `MAINTENANCE_STATUS_CODE=503` | services.maintenance-lambda.environment | 環境変数 MAINTENANCE_STATUS_CODE に「503」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `MAINTENANCE_UNTIL=` | services.maintenance-lambda.environment | 環境変数 MAINTENANCE_UNTIL に「」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `RETRY_AFTER_SECONDS=300` | services.maintenance-lambda.environment | 環境変数 RETRY_AFTER_SECONDS に「300」を設定します。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `public.ecr.aws/lambda/python:3.12` | services.maintenance-lambda.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `maintenance.lambda_handler` | services.maintenance-lambda.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=maintenance-lambda` ／ `docker logs maintenance-lambda` ／ `docker inspect maintenance-lambda`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  maintenance-lambda:
    command:
      - maintenance.lambda_handler
    container_name: maintenance-lambda
    environment:
      MAINTENANCE_STATUS_CODE: 503
      MAINTENANCE_UNTIL: ""
      RETRY_AFTER_SECONDS: 300
    image: "public.ecr.aws/lambda/python:3.12"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 9001
        target: 8080
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/maintenance-lambda/app
        target: /var/task
        type: bind
```

</details>

<a id="step-52"></a>

### STEP 52: サービス「alb-lambda-adapter」のコンテナ「alb-lambda-adapter」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.alb-lambda-adapter` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「python:3.12-slim」からコンテナ「alb-lambda-adapter」を作って起動します (サービス「alb-lambda-adapter」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 9081:8080
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 2 件 / --env-file 0 件
- depends_on (先に起動しておくもの): maintenance-lambda (service_started)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `alb-lambda-adapter` | services.alb-lambda-adapter.container_name | コンテナに「alb-lambda-adapter」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.alb-lambda-adapter.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `alb-lambda-adapter` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「alb-lambda-adapter」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `9081:8080` | services.alb-lambda-adapter.ports | ホスト (RHEL) の 9081 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/alb-lambda-adapter/adapter.py:/app/adapter.py:ro` | services.alb-lambda-adapter.volumes | ホストの /opt/Container_Compose_file/compose/alb-lambda-adapter/adapter.py をコンテナの /app/adapter.py に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--env` | `LAMBDA_INVOKE_URL=http://maintenance-lambda:8080/2015-03-31/functions/function/invocations` | services.alb-lambda-adapter.environment | 環境変数 LAMBDA_INVOKE_URL に「http://maintenance-lambda:8080/2015-03-31/functions/function…」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `LISTEN_PORT=8080` | services.alb-lambda-adapter.environment | 環境変数 LISTEN_PORT に「8080」を設定します。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `python:3.12-slim` | services.alb-lambda-adapter.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `python /app/adapter.py` | services.alb-lambda-adapter.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=alb-lambda-adapter` ／ `docker logs alb-lambda-adapter` ／ `docker inspect alb-lambda-adapter`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  alb-lambda-adapter:
    command:
      - python
      - /app/adapter.py
    container_name: alb-lambda-adapter
    depends_on:
      maintenance-lambda:
        condition: service_started
        required: true
    environment:
      LAMBDA_INVOKE_URL: "http://maintenance-lambda:8080/2015-03-31/functions/function/invocations"
      LISTEN_PORT: 8080
    image: "python:3.12-slim"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 9081
        target: 8080
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/alb-lambda-adapter/adapter.py
        target: /app/adapter.py
        type: bind
```

</details>

<a id="step-53"></a>

### STEP 53: pki-init・secure-api が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.alb.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 30](#step-30) と同じです)。

**このコマンドがすること**

サービス「alb」は depends_on で pki-init・secure-api が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 30](#step-30) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 30 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=pki-init`

<a id="step-54"></a>

### STEP 54: サービス「alb」のコンテナ「alb」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.alb` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「nginx:1.27-alpine」からコンテナ「alb」を作って起動します (サービス「alb」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 9080:80、9443:443
- マウント: 5 件 (データの置き場所をコンテナにつなぎます)
- depends_on (先に起動しておくもの): alb-lambda-adapter (service_started)、backend (service_started)、pki-init (service_healthy)、secure-api (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `alb` | services.alb.container_name | コンテナに「alb」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.alb.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `alb` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「alb」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `9080:80` | services.alb.ports | ホスト (RHEL) の 9080 番ポート (TCP) に届いた通信を、コンテナの 80 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `9443:443` | services.alb.ports | ホスト (RHEL) の 9443 番ポート (TCP) に届いた通信を、コンテナの 443 番ポートへ転送します。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/alb/nginx.conf:/etc/nginx/nginx.conf:ro` | services.alb.volumes | ホストの /opt/Container_Compose_file/compose/alb/nginx.conf をコンテナの /etc/nginx/nginx.conf に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/alb/rules:/etc/nginx/rules:ro` | services.alb.volumes | ホストの /opt/Container_Compose_file/compose/alb/rules をコンテナの /etc/nginx/rules に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/alb/rules-tls:/etc/nginx/rules-tls:ro` | services.alb.volumes | ホストの /opt/Container_Compose_file/compose/alb/rules-tls をコンテナの /etc/nginx/rules-tls に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/alb/tls:/etc/nginx/tls:ro` | services.alb.volumes | ホストの /opt/Container_Compose_file/compose/alb/tls をコンテナの /etc/nginx/tls に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `eap-adot-local_pki:/pki:ro` | services.alb.volumes | 名前付きボリューム「eap-adot-local_pki」をコンテナの /pki につなぎます (読み取り専用)。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 \|\| exit 1` | services.alb.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | (しくみは [STEP 27](#step-27) で説明) |
| `--health-interval` | `10s` | services.alb.healthcheck.interval | 何秒おきにチェックするか: 10s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-timeout` | `5s` | services.alb.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-start-period` | `5s` | services.alb.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | (しくみは [STEP 27](#step-27) で説明) |
| `--health-retries` | `5` | services.alb.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 5 回 | (しくみは [STEP 27](#step-27) で説明) |
| `(イメージ)` | `nginx:1.27-alpine` | services.alb.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=alb` ／ `docker logs alb` ／ `docker inspect alb`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  alb:
    container_name: alb
    depends_on:
      alb-lambda-adapter:
        condition: service_started
        required: true
      backend:
        condition: service_started
        required: true
      pki-init:
        condition: service_healthy
        required: true
      secure-api:
        condition: service_healthy
        required: true
    healthcheck:
      interval: 10s
      retries: 5
      start_period: 5s
      test:
        - CMD-SHELL
        - "wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1"
      timeout: 5s
    image: "nginx:1.27-alpine"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 9080
        target: 80
      - mode: ingress
        protocol: tcp
        published: 9443
        target: 443
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/alb/nginx.conf
        target: /etc/nginx/nginx.conf
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/alb/rules
        target: /etc/nginx/rules
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/alb/rules-tls
        target: /etc/nginx/rules-tls
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/alb/tls
        target: /etc/nginx/tls
        type: bind
      - read_only: true
        source: pki
        target: /pki
        type: volume
        volume: {}
```

</details>

<a id="step-55"></a>

### STEP 55: サービス「lambda」のコンテナ「lambda」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.lambda` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「public.ecr.aws/lambda/python:3.12」からコンテナ「lambda」を作って起動します (サービス「lambda」)。

- ネットワーク: eap-adot-local_default
- 公開ポート (ホスト → コンテナ): 9000:8080
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 3 件 / --env-file 0 件
- depends_on (先に起動しておくもの): alb (service_started)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `lambda` | services.lambda.container_name | コンテナに「lambda」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.lambda.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `lambda` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「lambda」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--publish` | `9000:8080` | services.lambda.ports | ホスト (RHEL) の 9000 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/lambda/app:/var/task:ro` | services.lambda.volumes | ホストの /opt/Container_Compose_file/compose/lambda/app をコンテナの /var/task に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--env` | `ALB_ENDPOINT=http://alb:80` | services.lambda.environment | 環境変数 ALB_ENDPOINT に「http://alb:80」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `BACK_PATH=/async/receive` | services.lambda.environment | 環境変数 BACK_PATH に「/async/receive」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `HTTP_TIMEOUT_SECONDS=10` | services.lambda.environment | 環境変数 HTTP_TIMEOUT_SECONDS に「10」を設定します。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `public.ecr.aws/lambda/python:3.12` | services.lambda.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `handler.lambda_handler` | services.lambda.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=lambda` ／ `docker logs lambda` ／ `docker inspect lambda`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  lambda:
    command:
      - handler.lambda_handler
    container_name: lambda
    depends_on:
      alb:
        condition: service_started
        required: true
    environment:
      ALB_ENDPOINT: "http://alb:80"
      BACK_PATH: /async/receive
      HTTP_TIMEOUT_SECONDS: 10
    image: "public.ecr.aws/lambda/python:3.12"
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 9000
        target: 8080
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/lambda/app
        target: /var/task
        type: bind
```

</details>

<a id="step-56"></a>

### STEP 56: サービス「lambda-esm」のコンテナ「lambda-esm」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.lambda-esm` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「eap-adot-local-lambda-esm」からコンテナ「lambda-esm」を作って起動します (サービス「lambda-esm」)。

- ネットワーク: eap-adot-local_default
- 環境変数: --env 8 件 / --env-file 0 件
- depends_on (先に起動しておくもの): lambda (service_started)、sqs (service_started)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `lambda-esm` | services.lambda-esm.container_name | コンテナに「lambda-esm」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.lambda-esm.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `lambda-esm` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「lambda-esm」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--env` | `AWS_ACCESS_KEY_ID=local` | services.lambda-esm.environment | 環境変数 AWS_ACCESS_KEY_ID に「local」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `AWS_REGION=ap-northeast-1` | services.lambda-esm.environment | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `AWS_SECRET_ACCESS_KEY=local` | services.lambda-esm.environment | 環境変数 AWS_SECRET_ACCESS_KEY に「local」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `BATCH_SIZE=10` | services.lambda-esm.environment | 環境変数 BATCH_SIZE に「10」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `LAMBDA_INVOKE_URL=http://lambda:8080/2015-03-31/functions/function/invocations` | services.lambda-esm.environment | 環境変数 LAMBDA_INVOKE_URL に「http://lambda:8080/2015-03-31/functions/function/invocations」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `QUEUE_NAME=app-async-queue` | services.lambda-esm.environment | 環境変数 QUEUE_NAME に「app-async-queue」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `SQS_ENDPOINT=http://sqs:9324` | services.lambda-esm.environment | 環境変数 SQS_ENDPOINT に「http://sqs:9324」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `WAIT_TIME_SECONDS=20` | services.lambda-esm.environment | 環境変数 WAIT_TIME_SECONDS に「20」を設定します。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `eap-adot-local-lambda-esm` | services.lambda-esm.build | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=lambda-esm` ／ `docker logs lambda-esm` ／ `docker inspect lambda-esm`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  lambda-esm:
    build:
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/lambda-esm
      dockerfile: Dockerfile
    container_name: lambda-esm
    depends_on:
      lambda:
        condition: service_started
        required: true
      sqs:
        condition: service_started
        required: true
    environment:
      AWS_ACCESS_KEY_ID: local
      AWS_REGION: ap-northeast-1
      AWS_SECRET_ACCESS_KEY: local
      BATCH_SIZE: 10
      LAMBDA_INVOKE_URL: "http://lambda:8080/2015-03-31/functions/function/invocations"
      QUEUE_NAME: app-async-queue
      SQS_ENDPOINT: "http://sqs:9324"
      WAIT_TIME_SECONDS: 20
    networks: {}
```

</details>

<a id="step-57"></a>

### STEP 57: サービス「ecs-exec」のコンテナ「ecs-exec」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.ecs-exec` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 26](#step-26) と同じです)。

**このコマンドがすること**

イメージ「eap-adot-local-ecs-exec:with-healthcheck」からコンテナ「ecs-exec」を作って起動します (サービス「ecs-exec」)。

- ネットワーク: eap-adot-local_default
- マウント: 5 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 10 件 / --env-file 0 件

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 26](#step-26) で説明) |
| `--name` | `ecs-exec` | services.ecs-exec.container_name | コンテナに「ecs-exec」という名前を付けます。compose の container_name です。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network` | `eap-adot-local_default` | services.ecs-exec.networks.default | ネットワーク「eap-adot-local_default」につなぎます。 | (しくみは [STEP 26](#step-26) で説明) |
| `--network-alias` | `ecs-exec` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「ecs-exec」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 26](#step-26) で説明) |
| `--volume` | `/var/run/docker.sock:/var/run/docker.sock` | services.ecs-exec.volumes | ホストの /var/run/docker.sock をコンテナの /var/run/docker.sock に直接つなぎます (バインドマウント)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 28](#step-28) で説明) |
| `--volume` | `/opt/Container_Compose_file/compose/ecs-exec/tasks.json:/etc/ecs-exec/tasks.json:ro` | services.ecs-exec.volumes | ホストの /opt/Container_Compose_file/compose/ecs-exec/tasks.json をコンテナの /etc/ecs-exec/tasks.json に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/ecs-exec/ecs-exec.py:/opt/ecs-exec/ecs-exec.py:ro` | services.ecs-exec.volumes | ホストの /opt/Container_Compose_file/compose/ecs-exec/ecs-exec.py をコンテナの /opt/ecs-exec/ecs-exec.py に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/ecs-exec/files:/work` | services.ecs-exec.volumes | ホストの /opt/Container_Compose_file/compose/ecs-exec/files をコンテナの /work に直接つなぎます (バインドマウント)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--volume` | `/opt/Container_Compose_file/compose/ecs-exec/sessions:/var/log/ecs-exec` | services.ecs-exec.volumes | ホストの /opt/Container_Compose_file/compose/ecs-exec/sessions をコンテナの /var/log/ecs-exec に直接つなぎます (バインドマウント)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--env` | `AWS_DEFAULT_REGION=ap-northeast-1` | services.ecs-exec.environment | 環境変数 AWS_DEFAULT_REGION に「ap-northeast-1」を設定します。 | (しくみは [STEP 31](#step-31) で説明) |
| `--env` | `AWS_REGION=ap-northeast-1` | services.ecs-exec.environment | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_EXEC_COMPOSE_PROJECT=eap-adot-local` | services.ecs-exec.environment | 環境変数 ECS_EXEC_COMPOSE_PROJECT に「eap-adot-local」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_EXEC_ENABLED=1` | services.ecs-exec.environment | 環境変数 ECS_EXEC_ENABLED に「1」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_EXEC_FILES_DIR=/work` | services.ecs-exec.environment | 環境変数 ECS_EXEC_FILES_DIR に「/work」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_EXEC_PUT_CHUNK_CHARS=16384` | services.ecs-exec.environment | 環境変数 ECS_EXEC_PUT_CHUNK_CHARS に「16384」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_EXEC_SESSION_LOG_DIR=/var/log/ecs-exec` | services.ecs-exec.environment | 環境変数 ECS_EXEC_SESSION_LOG_DIR に「/var/log/ecs-exec」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_EXEC_SIMULATE_PLUGIN_MISSING=0` | services.ecs-exec.environment | 環境変数 ECS_EXEC_SIMULATE_PLUGIN_MISSING に「0」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_EXEC_STATE_FILE=/var/lib/ecs-exec/state.json` | services.ecs-exec.environment | 環境変数 ECS_EXEC_STATE_FILE に「/var/lib/ecs-exec/state.json」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `ECS_EXEC_TASKS_FILE=/etc/ecs-exec/tasks.json` | services.ecs-exec.environment | 環境変数 ECS_EXEC_TASKS_FILE に「/etc/ecs-exec/tasks.json」を設定します。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `eap-adot-local-ecs-exec:with-healthcheck` | services.ecs-exec.build | ヘルスチェック入りの派生イメージ (元: eap-adot-local-ecs-exec) です。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 26 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=ecs-exec` ／ `docker logs ecs-exec` ／ `docker inspect ecs-exec`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  ecs-exec:
    build:
      context: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/ecs-exec
      dockerfile: Dockerfile
    container_name: ecs-exec
    environment:
      AWS_DEFAULT_REGION: ap-northeast-1
      AWS_REGION: ap-northeast-1
      ECS_EXEC_COMPOSE_PROJECT: eap-adot-local
      ECS_EXEC_ENABLED: 1
      ECS_EXEC_FILES_DIR: /work
      ECS_EXEC_PUT_CHUNK_CHARS: 16384
      ECS_EXEC_SESSION_LOG_DIR: /var/log/ecs-exec
      ECS_EXEC_SIMULATE_PLUGIN_MISSING: 0
      ECS_EXEC_STATE_FILE: /var/lib/ecs-exec/state.json
      ECS_EXEC_TASKS_FILE: /etc/ecs-exec/tasks.json
    healthcheck:
      interval: 30s
      retries: 3
      start_period: 5s
      test:
        - CMD
        - ecs-exec
        - doctor
        - "--self-only"
        - "--quiet"
      timeout: 10s
    networks: {}
    volumes:
      - bind: {}
        source: /var/run/docker.sock
        target: /var/run/docker.sock
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/ecs-exec/tasks.json
        target: /etc/ecs-exec/tasks.json
        type: bind
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/ecs-exec/ecs-exec.py
        target: /opt/ecs-exec/ecs-exec.py
        type: bind
      - bind: {}
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/ecs-exec/files
        target: /work
        type: bind
      - bind: {}
        source: /mnt/c/Users/taka_/Claude/Container_Compose_file/compose/ecs-exec/sessions
        target: /var/log/ecs-exec
        type: bind
```

</details>

<a id="step-58"></a>

### STEP 58: 起動したコンテナの状態を確認する

| 項目 | 内容 |
|---|---|
| 区分 | 状態確認 |
| 使うコマンド | docker ps ― コンテナの一覧と状態を見る |
| ひとことで | 作ったコンテナが正しく動いているかを一覧で確かめます。 |
| compose の対応箇所 | - |

**実行するコマンド**

```bash
docker ps \
  --all \
  --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

**実行のしかた**

貼り付けて Enter。表の STATUS 列を確認します。

**このコマンドがすること**

作ったコンテナ (jaeger、valkey、svf-mock、ecs-metadata-mock、adot-collector、efs-mock、batch-mock、cloudwatch-logs-mock、cwagent、sqs、pki-init、mysql、backend、frontend、alb-healthcheck、alb-front、secure-api、maintenance-lambda、alb-lambda-adapter、alb、lambda、lambda-esm、ecs-exec) が Up (起動中) になっているか、ヘルスチェックの結果 (healthy など) を確認します。

- STATUS が「Up ... (healthy)」なら正常、「Exited (0)」は正常終了 (1 回だけ動くコンテナ)、「Exited (1)」などは異常終了です。
- うまく動いていないコンテナは docker logs <コンテナ名> で出力 (ログ) を確認します。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--all` |  | (compose が自動で付ける / 手順上必要) | 止まっているコンテナも含めて表示します。 | 止まっているコンテナも含めて表示します。<br>（やさしく）お休み中のコンテナも名簿に入れます。 |
| `--format` | `table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}` | (compose が自動で付ける / 手順上必要) | 名前・イメージ・状態・ポートを表の形で表示します。 | 表示する項目と形を決めます。table は表の形、\t は列の区切りです。<br>（やさしく）名簿の書き方を決めます。 |

**しくみ (動作原理)**

dockerd に GET /containers/json?all=1 を送り、返ってきた一覧を Go のテンプレートで表に整形しています。

**動作イメージ (たとえ話)**

マンションの管理人さんの「全部屋の状況ボード」を見るようなものです。

**歴史と背景・必要になった経緯**

docker ps は Unix の ps (プロセスの一覧) にならった名前で、Docker の初期からあります。

**RHEL 9.8 での注意**

特にありません。docker stats --no-stream で CPU やメモリの使用量も確認できます。

**小学生向けのまとめ**: コンテナたちがみんな元気に動いているか、名簿でチェックするコマンドです。

**確認のしかた**: `docker logs <コンテナ名>` ／ `docker stats --no-stream`

## 6. コマンドの種類ごとの深掘り解説

<a id="kb-docker-version"></a>

### docker version ― Docker が使えるかを確かめる

- 書き方: `set +H / cd <プロジェクトのフォルダ> / docker version`
- ひとことで: docker コマンド (リモコン) と Docker Engine (本体) の両方が動いているかを確かめます。

**意味**

set +H は bash の「履歴展開」をオフにします。履歴展開とは、! で始まる文字 (例: !! や !abc) を過去に打ったコマンドへ自動で置き換える便利機能ですが、パスワードなどに ! が入っていると勝手に置き換わり、「event not found」というエラーになります。貼り付け事故を防ぐため、最初に止めておきます (bash ファイル名 でスクリプトとして実行するときは、もともとオフなので影響はありません)。  
cd は「作業するフォルダ (カレントディレクトリ)」を移動するコマンドです。compose は compose ファイルのあるフォルダを基準に相対パス (./conf など) を解釈するので、同じ場所に移動しておきます。  
docker version は、docker コマンド自身 (クライアント) と、裏で動いている Docker Engine (サーバー = dockerd) のバージョンや API バージョン、Go のバージョン、OS などを表示します。

**しくみ (動作原理)**

docker コマンドは、それだけではコンテナを動かせません。実際の仕事は Docker Engine (dockerd というサービス) が行い、docker コマンドは dockerd へ「お願い」を送るリモコンです。お願いは HTTP という Web と同じ形式で、/var/run/docker.sock という「UNIX ドメインソケット」(同じコンピューターの中だけで使う電話線のようなファイル) を通して送られます。  
docker version を実行すると、docker コマンドは dockerd に「GET /version」というお願いを送り、dockerd は JSON (データの書き方の一つ) で自分のバージョンを返します。このとき、クライアントとサーバーは「お互いが話せる API バージョン」を確認し合います (API バージョンのネゴシエーション)。Docker Engine 29 (2025 年 11 月) からは、API バージョン 1.44 未満 (Docker 25 より古い docker コマンド) からの接続は受け付けなくなりました。  
さらに裏側では、dockerd → containerd (コンテナの一生を管理する部品) → containerd-shim-runc-v2 → runc (実際にコンテナを作る小さなプログラム) → Linux カーネル、というように仕事がリレーされます。docker version の Server 欄に containerd や runc のバージョンも表示されるのはこのためです。

**動作イメージ**

テレビのリモコン (docker コマンド) と、テレビ本体 (Docker Engine) の関係です。リモコンのボタンを押しても、本体の電源が入っていなければ何も起きません。docker version は「リモコンの電池は入っているか」「本体の電源は入っているか」「リモコンと本体の電波は届いているか」をまとめて確かめるテストボタンのようなものです。

**歴史と背景・必要になった経緯**

Docker は 2013 年 3 月、dotCloud という会社 (のちの Docker 社) の Solomon Hykes さんが、プログラミング言語 Python の国際会議 PyCon の 5 分間の発表で初めて世に出し、同時にオープンソースとして公開しました。当時は「サーバーごとに環境が違ってアプリが動かない」という悩みが大きく、「アプリと必要なものを丸ごと箱詰めして、どこでも同じように動かす」という考えが一気に広まりました。  
最初の Docker は 1 つのプログラムがリモコンと本体を兼ねていましたが、2016 年に containerd、2015 年に runc が切り出され、業界標準の団体 OCI (Open Container Initiative、2015 年 6 月設立) の仕様に沿う形へ整理されました。バージョンの付け方は 2017 年に「年.月」(17.03 など) になり、2023 年の 23.0 から普通の番号に戻りました。2025 年 11 月の Docker Engine 29.0 では、新しく入れた環境ではイメージの保存に containerd の仕組み (containerd image store) を使うのが標準になり、ファイアウォールの nftables への対応 (試験的)、cgroup v1 の非推奨化などが行われました。2026 年 10 月時点の最新は 29.9 系です。

**小学生向けのまとめ**

コンテナの工場 (Docker) に電話をかけて「もしもし、動いてますか？」と聞くのが docker version です。「はい、動いてます。わたしのバージョンは 29 です」と返事が来たら、工場にお仕事をお願いする準備ができました。

**RHEL 9.8 での注意**

RHEL 8 以降、Red Hat が標準で用意しているコンテナの道具は Podman (docker と似たコマンドが使える別の製品) です。Docker 社の Docker Engine (docker-ce) は、Docker 社のリポジトリ (https://download.docker.com/linux/rhel/docker-ce.repo) から入れます。公式手順では、先に podman と runc を削除してから docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin を入れ、sudo systemctl enable --now docker で起動・自動起動を有効にします。docker グループに入ったユーザーは root と同じくらいの力を持てるので、グループに入れる人は最小限にしてください。

<a id="kb-docker-network-create"></a>

### docker network create ― コンテナ専用の仮想ネットワークを作る

- 書き方: `docker network create [オプション] ネットワーク名`
- ひとことで: コンテナどうしが名前で話せる、専用の仮想ネットワーク (ユーザー定義ブリッジ) を作ります。

**意味**

Docker のネットワークは、コンテナどうし、またはコンテナと外の世界をつなぐ「仮想の LAN」です。docker network create は新しい仮想 LAN を 1 つ作ります。ドライバー (種類) を指定しなければ bridge (ブリッジ) になり、このホストの中だけで使えるネットワークができます。  
同じネットワークにつながったコンテナは、相手の「コンテナ名」や「ネットワーク別名 (エイリアス)」で通信できます。たとえば web コンテナから http://db:5432 のように、IP アドレスを覚えなくても名前で相手に届きます。compose はこれを利用して、サービス名 (services: の下に書いた名前) で呼び合えるようにしています。

**しくみ (動作原理)**

bridge ドライバーの場合、Docker はホストの Linux カーネルに「ブリッジ」(ソフトウェアでできたスイッチングハブ) を作ります。名前は br- の後ろにネットワーク ID の先頭 12 文字が付いたもの (例: br-1a2b3c4d5e6f) で、ip addr で見ることができます。  
次に IPAM (IP Address Management = IP アドレスの割り当て係) が、まだ使われていないアドレスの範囲 (サブネット。例: 172.18.0.0/16) を選び、その最初のアドレス (例: 172.18.0.1) をゲートウェイ (外への出口) としてブリッジに付けます。  
コンテナがこのネットワークにつながるとき、Docker は veth ペア (2 本で 1 組の仮想 LAN ケーブル) を作り、片方をコンテナのネットワーク名前空間 (コンテナ専用のネットワークの世界) に入れて eth0 などの名前にし、もう片方をブリッジに差します。  
外 (インターネットなど) へ出る通信は、ファイアウォールの仕組み (iptables。RHEL 9 では内部で nftables に変換される) のMASQUERADE というルールで、送り主のアドレスがホストのアドレスに書き換えられます。  
名前で呼び合えるのは、Docker が内蔵 DNS サーバーを持っているからです。コンテナの /etc/resolv.conf には 127.0.0.11 が書かれ、ここへの問い合わせを dockerd が受けて、同じネットワークにいるコンテナの名前・別名を IP アドレスに変換して答えます。知らない名前はホスト側の DNS に聞きに行きます。なお、Docker が最初から持っている「bridge」(docker0) ネットワークでは、この名前解決は働きません。compose が必ず自分用のネットワークを作るのはこのためです。  
--internal を付けると外への出口の設定が作られず、ネットワークの中だけで通信できる閉じた LAN になります。

**動作イメージ**

マンション (ホスト) の中に、住人 (コンテナ) どうしだけで使える「内線電話網」を引くようなものです。ブリッジは電話の交換機、veth は各部屋へつながる電話線、内蔵 DNS は「名前を言えば番号につないでくれる電話帳係」です。外に電話 (インターネット) をかけるときは、マンションの代表番号 (ホストの IP アドレス) からかけたことにしてもらいます (MASQUERADE)。

**歴史と背景・必要になった経緯**

最初の Docker (2013 年) には docker0 という 1 つの共用ネットワークしかなく、コンテナどうしをつなぐには --link という仕組みで、相手の IP アドレスを環境変数や /etc/hosts に書き込むしかありませんでした。相手が再起動して IP が変わると切れてしまうなど、不便な点がありました。  
そこで Docker 社は 2015 年 3 月に SocketPlane という会社を買収してネットワーク部品 (libnetwork) を作り、2015 年 11 月の Docker 1.9 で docker network コマンドと「ユーザーが自由に作れるネットワーク」が登場しました。2016 年 2 月の Docker 1.10 で内蔵 DNS とネットワーク別名 (--network-alias) が加わり、名前で呼び合うのが当たり前になりました。  
compose も 2016 年のファイル形式 v2 から networks: を書けるようになり、プロジェクトごとに専用ネットワーク (<プロジェクト名>_default) を自動で作るようになりました。その後も、Docker 25 (2024 年) で 1 回の docker run で複数ネットワークにつなげるようになり、Docker 28 (2025 年) でデフォルトゲートウェイの優先度 (gw-priority)、Docker 29 (2025 年 11 月) で nftables への試験的な対応が加わっています。

**小学生向けのまとめ**

コンテナたちのための「専用の道路と電話帳」を作るコマンドです。同じ道路につながったコンテナは、「db さーん」と名前を呼ぶだけで相手のところへ手紙 (データ) を届けられます。

**RHEL 9.8 での注意**

RHEL 9.8 では firewalld が動いていることが多く、Docker は firewalld に docker という zone を作ってブリッジを登録します。firewall-cmd --reload をしたあとにコンテナの通信がおかしくなったら、sudo systemctl restart docker で Docker のルールを入れ直してください。  
社内ネットワークと Docker が選んだサブネット (172.17〜172.31 や 192.168.x.x) が重なると、その範囲の社内サーバーへ届かなくなります。そのときは compose の ipam.config.subnet で範囲を指定するか、/etc/docker/daemon.json の default-address-pools で Docker が使う範囲を変えます。

<a id="kb-docker-volume-create"></a>

### docker volume create ― データを残しておくボリュームを作る

- 書き方: `docker volume create [オプション] ボリューム名`
- ひとことで: コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。

**意味**

コンテナの中で書いたファイルは、ふつうはコンテナを削除すると一緒に消えてしまいます。データベースのデータのように消えては困るものは「ボリューム」に保存します。docker volume create は名前付きのボリュームを作るコマンドです。  
compose は volumes: に書いたボリュームを「<プロジェクト名>_<キー>」という名前で作ります。

**しくみ (動作原理)**

標準の local ドライバーでは、ホストの /var/lib/docker/volumes/<ボリューム名>/_data というフォルダが作られるだけです。コンテナを起動するとき、Docker はこのフォルダを「バインドマウント」という仕組みで、コンテナの中の指定の場所 (例: /var/lib/mysql) に重ねて見せます。コンテナから見ると普通のフォルダですが、実体はコンテナの外にあるため、コンテナを消しても残ります。  
空のボリュームを初めてつないだときは、イメージのその場所に最初から入っていたファイルがボリュームへコピーされます (コピーアップ)。nocopy を指定するとコピーしません。  
--opt type=nfs,o=addr=...,device=:/export のようにすると、NFS などのネットワーク上の保存場所をボリュームとして使うこともできます (裏では mount コマンドと同じ仕組みが使われます)。

**動作イメージ**

お部屋 (コンテナ) の外にある「貸しロッカー」です。お部屋を片付けて (コンテナを削除して) も、ロッカーの中身は残っています。次に新しいお部屋を用意したら、同じロッカーの鍵を渡せば、前のデータをそのまま使えます。

**歴史と背景・必要になった経緯**

初期の Docker では、データを残すには -v でホストのフォルダを直接つなぐか、「データ専用コンテナ」を作って --volumes-from で共有する、という工夫が使われていました。2015 年の Docker 1.8 でボリュームプラグイン (外部ストレージとつなぐ仕組み)、2015 年 11 月の Docker 1.9 で docker volume コマンドと名前付きボリュームが登場し、データの置き場所を名前で管理できるようになりました。2017 年の Docker 17.06 で、docker run に読みやすい長い書き方 --mount が追加され、2024 年の Docker 26 ではボリュームの中の一部のフォルダだけをつなぐ volume-subpath が使えるようになりました。compose ではファイル形式 v2 (2016 年) から volumes: でボリュームを定義できます。

**小学生向けのまとめ**

コンテナが使う「なくならないロッカー」を用意するコマンドです。コンテナを片付けても、ロッカーの中のデータは残ります。

**RHEL 9.8 での注意**

ボリュームの実体は /var/lib/docker の下に作られます。RHEL では /var を小さなパーティションに分けていることがあるため、df -h /var/lib/docker で空き容量を確認してください。  
SELinux を有効にした Docker (daemon.json で "selinux-enabled": true) でも、名前付きボリュームには Docker が自動で正しいラベルを付けるので、そのまま使えます。

<a id="kb-docker-pull"></a>

### docker pull ― イメージをダウンロードする

- 書き方: `docker image inspect イメージ > /dev/null 2>&1 || docker pull イメージ`
- ひとことで: イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。

**意味**

docker pull は、Docker Hub や Amazon ECR などの「レジストリ」からイメージをダウンロードします。  
このステップでは docker image inspect で手元にあるかを調べ、無いときだけ docker pull を実行しています。|| は「左のコマンドが失敗したときだけ右を実行する」という意味で、> /dev/null 2>&1 は表示を捨てる書き方です。これは compose の既定の動き (pull_policy: missing = 無いときだけ取ってくる) と同じです。ただの docker pull にしないのは、手元に古い版があるときに勝手に新しい版へ変わってしまう (compose と違う結果になる) のを防ぐためです。

**しくみ (動作原理)**

イメージ名「レジストリ/リポジトリ:タグ」を分解します。レジストリを省略すると docker.io (Docker Hub) が使われ、公式イメージは library/ が補われます (例: mysql:8.4.7 → docker.io/library/mysql:8.4.7)。  
次に、レジストリの API (OCI Distribution Specification) でマニフェスト (イメージがどの層 = レイヤーでできているかの目録) を取り寄せます。いろいろな CPU 向けの版がある「マルチアーキテクチャ」イメージなら、目録の目録 (インデックス) から linux/amd64 などこのサーバーに合うものを選びます。  
レイヤーは、ファイルの差分を tar でまとめて gzip や zstd で圧縮したもので、中身から計算した sha256 の値 (ダイジェスト) で区別されます。同じダイジェストのレイヤーを既に持っていればダウンロードせず、無いものだけを並行してダウンロードし、壊れていないか検証してから展開します。  
Docker Hub には回数制限があり、2026 年 10 月時点の公式ドキュメントでは、ログインしない場合は 6 時間あたり 100 回 (IPv4 アドレス、または IPv6 の /64 ごと)、無料アカウントでログインすると 200 回です。

**動作イメージ**

インターネットの「部品倉庫」から、お部屋セット (イメージ) を取り寄せます。セットは何枚もの透明なシート (レイヤー) を重ねてできていて、家に同じシートがあればそれを使い回し、足りないシートだけを送ってもらいます。押し入れに同じセットが既にあれば、取り寄せはしません。

**歴史と背景・必要になった経緯**

2013 年の Docker 登場と同時に、イメージを共有する場所 (Docker Index) が作られ、2014 年 6 月の Docker 1.0 と同時に Docker Hub になりました。2015 年の Registry API v2 (Docker 1.6) で、中身のハッシュ値でレイヤーを管理する今の方式になり、同じものを二度送らずに済むようになりました。2017 年に OCI Image Specification 1.0、2021 年に OCI Distribution Specification 1.0 が決まり、Docker 以外のツール (Podman や Kubernetes) とも同じイメージを共有できるようになりました。2020 年 11 月からは Docker Hub に回数制限が導入され、Amazon ECR Public (2020 年 12 月) のような別の公開レジストリも使われるようになりました。

**小学生向けのまとめ**

おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**RHEL 9.8 での注意**

社内でプロキシを使う場合、docker pull を実際に行うのは dockerd なので、dockerd にプロキシを設定します (例: /etc/systemd/system/docker.service.d/http-proxy.conf に Environment="HTTPS_PROXY=http://proxy.example.com:8080" を書き、sudo systemctl daemon-reload && sudo systemctl restart docker)。自己署名証明書の社内レジストリは /etc/docker/certs.d/<レジストリ名>/ca.crt に CA 証明書を置きます。

<a id="kb-docker-image-inspect"></a>

### docker image inspect ― イメージが手元にあるか調べる

- 書き方: `docker image inspect イメージ名`
- ひとことで: イメージが手元 (このサーバー) にあるかを調べます。

**意味**

イメージの設定や層の情報を表示します。手元に無ければエラー (終了コード 1) になるので、存在確認に使えます。

**しくみ (動作原理)**

dockerd のイメージ一覧 (image store) を調べるだけで、ネットワークには出ません。

**動作イメージ**

家の押し入れに、その部品セットがあるかをのぞいてみるようなものです。

**歴史と背景・必要になった経緯**

docker inspect は初期からある調査用のコマンドです。

**小学生向けのまとめ**

押し入れにおもちゃの部品があるか見てみるコマンドです。

**RHEL 9.8 での注意**

特にありません。

<a id="kb-docker-build"></a>

### docker build ― Dockerfile からイメージを作る

- 書き方: `docker build [オプション] ビルドコンテキスト`
- ひとことで: 設計図 (Dockerfile) と材料フォルダ (ビルドコンテキスト) から、イメージを作ります。

**意味**

Dockerfile は「どのイメージを土台にして (FROM)、何をインストールし (RUN)、どのファイルを入れ (COPY)、何を起動するか (CMD)」を書いた設計図です。docker build はそれを読んで、上から順に作業し、できあがったものをイメージとして保存します。--tag で付けた名前が、そのイメージの名前になります。  
compose の build: に書かれた設定 (context = 材料フォルダ、dockerfile = 設計図の場所、args = 設計図に渡す値、target = 途中の段階まで作る など) は、それぞれ docker build のオプションに 1 対 1 で対応しています。compose は image: の名前、無ければ「<プロジェクト名>-<サービス名>」という名前を付けます。

**しくみ (動作原理)**

Docker 23.0 (2023 年 2 月) からは、docker build の中身は BuildKit という新しいビルドエンジン (docker buildx build) です。  
① ビルドコンテキスト (フォルダ) の中身が BuildKit に渡されます。.dockerignore に書いたファイルは渡されません。  
② Dockerfile は LLB (低水準のビルド手順のグラフ) に変換され、互いに関係のない手順は同時に (並列に) 実行されます。  
③ RUN 命令は、ビルド用の一時的なコンテナの中で実行されます。COPY・RUN などの結果は「レイヤー」(前との差分) として記録され、命令と材料が前回と同じなら、作り直さずにキャッシュ (作り置き) を使います。  
④ FROM ... AS 名前 を何度も書く「マルチステージ」では、ビルド用の道具を入れた段階でプログラムを作り、完成品だけを小さな最終イメージへ COPY --from で移せます。  
⑤ --build-arg の値はイメージの履歴に残るので、パスワードには使いません。秘密の値は --secret で渡し、Dockerfile では RUN --mount=type=secret でその命令の間だけ一時的に読みます (レイヤーにもキャッシュにも残りません)。  
⑥ 完成したイメージは、手元のイメージ一覧に --tag の名前で登録されます。  
compose v5 (2025 年 12 月) は自前のビルド処理をやめ、Docker Bake (BuildKit を複数まとめて動かす仕組み) に任せています。そのため、docker build を使っても compose と同じ BuildKit で同じイメージができます。

**動作イメージ**

料理にたとえると、Dockerfile は「レシピ」、ビルドコンテキストは「材料の入った箱」、BuildKit は「料理人」です。料理人はレシピを 1 行ずつ読み、手順ごとにお皿 (レイヤー) を重ねて「冷凍お弁当」(イメージ) を完成させます。前と同じ手順・同じ材料なら、作り置きのお皿を使うので早くできます。

**歴史と背景・必要になった経緯**

Dockerfile は 2013 年の Docker 登場時からある仕組みで、「サーバーの設定手順書をそのまま実行できる形にする」という考え方を広めました。2017 年の Docker 17.05 でマルチステージビルドが入り、小さく安全なイメージを作りやすくなりました。  
同じ 2017 年に、もっと速く安全なビルドを目指す BuildKit の開発が Moby プロジェクトで始まり、2018 年の Docker 18.09 で試せるようになり、2019 年に docker buildx が登場、2020 年には Dockerfile の RUN --mount (secret / ssh / cache) が使えるようになりました。そして 2023 年 2 月の Docker 23.0 で、Linux の docker build は標準で BuildKit を使うようになりました。  
compose のビルドも BuildKit を使うように変わり、2025 年 12 月の Compose v5.0 で、ビルドは Docker Bake に一本化されました。

**小学生向けのまとめ**

設計図と材料を工場に渡して、おもちゃのもと (イメージ) を作ってもらうコマンドです。前と同じところは作り置きを使うので、2 回目からは早くできます。

**RHEL 9.8 での注意**

UBI (Red Hat Universal Base Image) などを土台にして RUN dnf install をする場合、ビルド中のインターネット接続が必要です。プロキシ環境では --build-arg HTTP_PROXY=... / HTTPS_PROXY=... を渡すか、~/.docker/config.json の proxies 設定を使います。ビルドの途中結果 (キャッシュ) は /var/lib/docker に溜まるので、容量が足りなくなったら docker builder prune で片付けます。

<a id="kb-docker-build-healthcheck"></a>

### docker build - (ヘルスチェック入りの派生イメージを作る)

- 書き方: `docker build --tag 新しい名前 - <<'C2D_DOCKERFILE' (Dockerfile の中身) C2D_DOCKERFILE`
- ひとことで: 元のイメージに、compose と同じ「exec 形式」のヘルスチェック設定だけを足したイメージを作ります。

**意味**

compose の healthcheck の test には 2 つの書き方があります。  
・exec 形式 ["CMD", "コマンド", "引数"] … コマンドを直接実行します。  
・シェル形式 ["CMD-SHELL", "コマンド文字列"] … /bin/sh -c "コマンド文字列" として実行します。  
ところが docker run の --health-cmd オプションは、必ずシェル形式になってしまいます。/bin/sh が入っていないイメージ (distroless など) ではシェル形式のヘルスチェックは必ず失敗し、コンテナは unhealthy (不健康) になって、それを待っている他のコンテナも起動できなくなります。  
そこで、Dockerfile の HEALTHCHECK 命令 (こちらは exec 形式が書ける) を使って、元のイメージに設定だけを足した派生イメージを作ります。これで compose とまったく同じヘルスチェックになります。

**しくみ (動作原理)**

docker build の最後の「-」は、「Dockerfile を標準入力から読む (材料フォルダは使わない)」という意味です。<<'C2D_DOCKERFILE' からC2D_DOCKERFILE までの行が、そのまま Dockerfile として渡されます。'...' で囲んでいるので、$ などの記号もそのまま渡されます。  
FROM で元のイメージを土台にし、HEALTHCHECK でヘルスチェックの設定を付けます。HEALTHCHECK はファイルを変えない「設定 (メタデータ)」だけの命令なので、中身のファイルは元のイメージと 1 バイトも変わらず、イメージの設定 (config) だけが新しくなります。ダウンロードし直すものもありません。元のイメージ名はそのまま残り、新しいイメージには <プロジェクト>-<サービス>:with-healthcheck という別の名前を付けます。

**動作イメージ**

お弁当 (イメージ) の中身はそのままで、ふたに「元気チェックのやり方カード」を貼った版を作るようなものです。

**歴史と背景・必要になった経緯**

HEALTHCHECK は 2016 年 7 月の Docker 1.12 で追加されました。それまでは「プロセスが動いているか」しか分からず、「動いてはいるが応答しない」状態を見分けられませんでした。その後、Google の distroless (2017 年) のように、攻撃される隙を減らすためにシェルすら入れない小さなイメージが広まり、シェルを使わない exec 形式の大切さが増しました。Docker 25 (2024 年) では、起動直後だけ短い間隔でチェックする start-interval も加わっています。

**小学生向けのまとめ**

元のおもちゃはそのままで、「元気かな？チェックのやり方」を書いたカードを貼った版を作るコマンドです。

**RHEL 9.8 での注意**

特にありません。元のイメージが手元にある (先の STEP で取得・ビルド済み) 必要があります。

<a id="kb-docker-run"></a>

### docker run ― コンテナを作って起動する

- 書き方: `docker run [オプション] イメージ [コマンド] [引数...]`
- ひとことで: イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。

**意味**

docker run は「docker create (作る)」と「docker start (起動する)」を 1 回で行うコマンドです。--detach を付けると、コンテナを裏側で動かしたまま、すぐにプロンプトへ戻ります (compose の up -d と同じ)。  
オプションは、compose ファイルの services: の各設定 (ports, volumes, environment, healthcheck, restart など) を 1 つずつdocker のオプションに置き換えたものです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) です。  
compose はコンテナに「<プロジェクト名>-<サービス名>-<番号>」という名前を付け、サービス名をネットワーク上の別名にします。この手順でも同じ名前・同じ別名を付けるので、コンテナどうしの呼び方 (http://db:3306 など) も compose のときと変わりません。

**しくみ (動作原理)**

① docker コマンドがオプションを JSON にまとめ、dockerd に「POST /containers/create」を送ります。  
② dockerd はイメージに書かれた設定 (ENV・CMD・ENTRYPOINT・WORKDIR・USER・EXPOSE・VOLUME・HEALTHCHECK) と、オプションの設定を合わせ、OCI ランタイム仕様の設定ファイル (config.json) を作ります。オプションで指定したものがイメージの設定より優先されます。  
③ 続いて「POST /containers/<ID>/start」で起動します。dockerd → containerd → containerd-shim-runc-v2 → runc とリレーされ、runc が Linux カーネルに次のことを頼みます。  
　・名前空間 (namespace): PID (プロセス番号)・NET (ネットワーク)・MNT (ファイルの見え方)・UTS (ホスト名)・IPC (プロセス間通信)・cgroup をコンテナ専用に分け、ほかのコンテナやホストのものが見えないようにします。  
　・cgroup v2: CPU・メモリ・プロセス数などの使用量を数え、上限を決めます (--cpus や --memory)。  
　・overlayfs: イメージのレイヤー (読み取り専用) を何枚も重ね、その一番上に書き込み用の層を 1 枚足して、コンテナのファイルシステム (/) にします。コンテナで書いたファイルはこの書き込み層に入り、コンテナを消すと一緒に消えます。  
　・ボリュームやバインドマウントをつなぎ、capabilities (root の特権を細かく分けたもの。標準では 14 種類だけ許可) と seccomp (使ってよいシステムコールの一覧) で権限をしぼります。  
　・最後に ENTRYPOINT + CMD のプログラムを、そのコンテナの中の PID 1 (最初のプロセス) として実行します。  
④ ネットワークは veth でブリッジにつながれ、IP アドレスが割り当てられ、/etc/hosts と /etc/resolv.conf (内蔵 DNS の 127.0.0.11) が用意されます。  
⑤ プログラムの画面出力は、ログドライバー (標準は json-file) を通して /var/lib/docker/containers/<ID>/<ID>-json.log などに保存されます。  
⑥ その後も dockerd は、restart の設定に従ってコンテナが止まったら起こし直し、HEALTHCHECK があれば一定間隔で健康チェックを行います。  
つまりコンテナの正体は「特別な囲いの中で動いている、ふつうの Linux のプロセス」です。仮想マシンのように OS をまるごと起動するわけではないので、1 秒もかからずに起動できます。

**動作イメージ**

マンション (ホスト) の空き部屋を 1 つ用意し、お部屋セット (イメージ) の家具を運び込んで、住人 (プログラム) に住んでもらうようなものです。部屋には壁 (名前空間) があってほかの部屋の中は見えず、電気や水道にはブレーカー (cgroup) が付いていて使いすぎを防ぎます。管理人さん (dockerd) は、マンションの合鍵 (特権) のうち必要なものだけを住人に渡し、住人が倒れたら起こしに行き (restart)、ときどき「元気？」と声をかけます (healthcheck)。

**歴史と背景・必要になった経緯**

「プログラムを囲いの中で動かす」考えは古く、1979 年の Unix V7 の chroot (見えるフォルダを制限する) までさかのぼります。2000 年に FreeBSD の jail、2004〜2005 年に Solaris の Zones が登場しました。Linux では 2002 年から名前空間が少しずつ作られ、2006 年に Google の技術者が「process containers」として資源の上限を決める仕組みを開発し、2008 年 (Linux 2.6.24) に cgroups として取り込まれました。同じ 2008 年に、これらを組み合わせた LXC が登場しています。  
2013 年の Docker は、LXC を使って「イメージ」という配りやすい形と、docker run という簡単なコマンドを用意したことで爆発的に広まりました。2014 年には LXC をやめて自前の libcontainer に切り替え、2015 年にそれを runc として OCI に寄贈しました。2016 年には containerd が分離され、2017 年に CNCF (クラウドネイティブの技術を育てる団体) へ寄贈されています。  
資源の管理は cgroup v2 (2016 年、Linux 4.5) へ移り、RHEL 9 (2022 年) では cgroup v2 が標準になりました。Docker も 20.10 (2020 年) で cgroup v2 に対応し、29.0 (2025 年 11 月) で cgroup v1 を非推奨にしています。

**小学生向けのまとめ**

おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**RHEL 9.8 での注意**

・RHEL 9.8 は cgroup v2 が標準です。--memory-swappiness や --kernel-memory など cgroup v1 専用の古いオプションは使えません (警告が出て無視されます)。  
・SELinux: docker-ce の標準設定 (selinux-enabled: false) では、コンテナに SELinux のラベルが付かないため、バインドマウントはそのまま読み書きできます。/etc/docker/daemon.json に "selinux-enabled": true を設定している場合は、ホストのフォルダをつなぐときに :z (複数のコンテナで共有) か :Z (このコンテナ専用) を付けないと Permission denied になります。これは compose でも同じです。  
・ポート公開 (-p) は Docker が自分でファイアウォールのルールを入れるため、通常は firewall-cmd での許可は不要です。・Docker 29 から、コンテナ内の「同時に開けるファイル数」の標準 (ulimit -n のソフト上限) が 1024 になっています。多くの接続やファイルを使うアプリは、compose の ulimits (= --ulimit nofile=...) で上げておきます。

<a id="kb-docker-inspect-health"></a>

### docker inspect の繰り返し ― healthy になるまで待つ

- 書き方: `for C in コンテナ...; do while :; do ... docker inspect --format ... ; done; done`
- ひとことで: depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。

**意味**

compose の depends_on に condition: service_healthy と書くと、compose は「依存先のヘルスチェックが合格 (healthy) するまで、こちらのコンテナを起動しない」という順番待ちをします。docker コマンドにはこの機能がないため、bash の繰り返し (while) で同じことをします。  
docker inspect --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}' は、コンテナの状態 (running など) と、ヘルスチェックの結果 (starting / healthy / unhealthy) を「running:healthy」のような形で取り出します。case 文で、healthy なら次へ、starting (確認中) なら 2 秒待って再確認、それ以外なら NG と表示して待つのをやめます。

**しくみ (動作原理)**

ヘルスチェックは dockerd が行っています。interval (間隔) ごとに、コンテナの中でテスト用のコマンドを実行し (docker exec と同じ仕組み)、終了コード 0 なら合格、それ以外なら不合格と数えます。起動直後の start_period の間は不合格を数えず、retries 回続けて不合格になると unhealthy、1 回でも合格すると healthy になります。結果はコンテナの State.Health に記録され、docker inspect で読めます。--format の書き方は Go 言語のテンプレートで、{{if}} は「Health の情報があるときだけ」という条件です。

**動作イメージ**

お店の前で「準備中」の札が「営業中」に変わるのを、2 秒ごとにのぞいて待っているようなものです。「本日休業」(unhealthy) の札が出たら、待つのをやめて理由を聞きに行きます。

**歴史と背景・必要になった経緯**

HEALTHCHECK は 2016 年 7 月の Docker 1.12 で登場しました。compose ではファイル形式 v2.1 (2016 年) から depends_on に condition: service_healthy を書けるようになりましたが、Swarm 向けのファイル形式 v3 (2017 年) では一度消えてしまい、多くの人が自作の「待ち合わせスクリプト」(wait-for-it.sh など) を使っていました。2020 年に始まった Compose Specification でこの書き方が正式に復活し、2021 年には service_completed_successfully も加わりました。

**小学生向けのまとめ**

友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**RHEL 9.8 での注意**

bash 5.1 (RHEL 9 の標準) でそのまま動きます。

<a id="kb-docker-ps"></a>

### docker ps ― コンテナの一覧と状態を見る

- 書き方: `docker ps --all --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'`
- ひとことで: 作ったコンテナが正しく動いているかを一覧で確かめます。

**意味**

docker ps はコンテナの一覧を表示します。--all を付けると止まっているものも表示します。--format の table は表の形、{{.Names}} などは表示する列 (名前・イメージ・状態・ポート) を選ぶ書き方です。  
STATUS の見方: 「Up 2 minutes (healthy)」= 動いていてヘルスチェックも合格、「Up ... (health: starting)」= 確認中、「Up ... (unhealthy)」= 動いているが不合格、「Exited (0)」= 正常に終わった (1 回だけ動くコンテナなら正常)、「Exited (1)」や「Exited (137)」= 異常終了 (137 はメモリ不足などで強制終了された印)、「Created」= 作っただけで起動していない。

**しくみ (動作原理)**

dockerd に GET /containers/json?all=1 を送り、返ってきた一覧を Go のテンプレートで表に整形しています。

**動作イメージ**

マンションの管理人さんの「全部屋の状況ボード」を見るようなものです。

**歴史と背景・必要になった経緯**

docker ps は Unix の ps (プロセスの一覧) にならった名前で、Docker の初期からあります。

**小学生向けのまとめ**

コンテナたちがみんな元気に動いているか、名簿でチェックするコマンドです。

**RHEL 9.8 での注意**

特にありません。docker stats --no-stream で CPU やメモリの使用量も確認できます。

<a id="kb-docker-stop"></a>

### docker stop ― コンテナを止める

- 書き方: `docker stop コンテナ名`
- ひとことで: コンテナに「止まってください」の合図を送り、終わるのを待ちます。

**意味**

docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。

**しくみ (動作原理)**

dockerd が containerd を通じてシグナルを送り、タイマーで待ちます。--restart の設定があっても、docker stop で止めたコンテナは自動では起動し直されません。

**動作イメージ**

閉店の時間に「そろそろ閉めますよ」と声をかけ、片付けが終わるのを少し待ってから、それでも終わらなければ電気を消してしまうようなものです。

**歴史と背景・必要になった経緯**

SIGTERM で後片付けを促し、時間切れなら SIGKILL という手順は、Unix のプロセス管理の昔からの作法です。

**小学生向けのまとめ**

「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

**RHEL 9.8 での注意**

特にありません。

<a id="kb-docker-rm"></a>

### docker rm ― コンテナを削除する

- 書き方: `docker rm コンテナ名...`
- ひとことで: 止めたコンテナを削除します (compose down と同じ)。名前付きボリュームは残ります。

**意味**

コンテナの設定と書き込み用の層を削除します。名前付きボリュームは消えません。匿名ボリュームも、-v を付けない限り残ります (compose down と同じ動き)。

**しくみ (動作原理)**

dockerd に DELETE /containers/<ID> を送ります。

**動作イメージ**

退去したお部屋を元の空き部屋に戻します。貸しロッカー (ボリューム) はそのまま残ります。

**歴史と背景・必要になった経緯**

docker rm は Docker の初期からあるコマンドです。

**小学生向けのまとめ**

使い終わったおもちゃを分解して片付けるコマンドです。ロッカーの中身は残ります。

**RHEL 9.8 での注意**

特にありません。

<a id="kb-docker-network-rm"></a>

### docker network rm ― ネットワークを削除する

- 書き方: `docker network rm ネットワーク名...`
- ひとことで: このプロジェクトで作ったネットワークを削除します (compose down と同じ)。

**意味**

ブリッジとファイアウォールのルール、IP アドレスの範囲の予約が片付けられます。

**しくみ (動作原理)**

dockerd に DELETE /networks/<ID> を送ります。つながっているコンテナがあると削除できません。

**動作イメージ**

使わなくなった内線電話網を撤去します。

**歴史と背景・必要になった経緯**

docker network コマンドは 2015 年の Docker 1.9 から使えます。

**小学生向けのまとめ**

使い終わった道路を片付けるコマンドです。

**RHEL 9.8 での注意**

特にありません。

<a id="kb-docker-volume-rm"></a>

### docker volume rm ― ボリュームを削除する (データが消えます)

- 書き方: `docker volume rm ボリューム名...`
- ひとことで: 名前付きボリュームを削除します (compose down -v と同じ)。中のデータは元に戻せません。

**意味**

ボリュームの実体 (/var/lib/docker/volumes/<名前>) を削除します。データベースのデータなどが完全に消えるので注意してください。

**しくみ (動作原理)**

dockerd に DELETE /volumes/<名前> を送ります。使っているコンテナがあると削除できません。

**動作イメージ**

貸しロッカーを中身ごと返却します。

**歴史と背景・必要になった経緯**

docker volume コマンドは 2015 年の Docker 1.9 から使えます。

**小学生向けのまとめ**

ロッカーを中身ごと捨てるコマンドです。大事なものが入っていないか、よく確かめてから使います。

**RHEL 9.8 での注意**

特にありません。

<a id="kb-docker-image-rm"></a>

### docker image rm ― イメージを削除する

- 書き方: `docker image rm イメージ名...`
- ひとことで: このプロジェクトでビルドしたイメージを削除します (compose down --rmi local と同じ)。

**意味**

イメージの名前 (タグ) を外し、どこからも使われなくなったレイヤーを削除してディスクを空けます。

**しくみ (動作原理)**

dockerd に DELETE /images/<名前> を送ります。そのイメージから作ったコンテナが残っていると削除できません。

**動作イメージ**

使わなくなったお部屋セットを倉庫から処分します。

**歴史と背景・必要になった経緯**

docker rmi / docker image rm は Docker の初期からあります (image rm の書き方は 2017 年の 1.13 から)。

**小学生向けのまとめ**

もう使わないおもちゃのもとを捨てるコマンドです。

**RHEL 9.8 での注意**

特にありません。docker system df で Docker が使っているディスク容量を確認できます。

## 7. compose の設定と docker オプションの対応表

### このプロジェクトでの対応

| サービス | コンテナ | compose の設定 | docker のオプション | 値 | 意味 |
|---|---|---|---|---|---|
| jaeger | jaeger | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| jaeger | jaeger | services.jaeger.container_name | `--name` | `jaeger` | コンテナに「jaeger」という名前を付けます。compose の container_name です。 |
| jaeger | jaeger | services.jaeger.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| jaeger | jaeger | (compose が自動で付与) | `--network-alias` | `jaeger` | このネットワークの中で「jaeger」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| jaeger | jaeger | services.jaeger.ports | `--publish` | `16686:16686` | ホスト (RHEL) の 16686 番ポート (TCP) に届いた通信を、コンテナの 16686 番ポートへ転送します。 |
| valkey | valkey | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| valkey | valkey | services.valkey.container_name | `--name` | `valkey` | コンテナに「valkey」という名前を付けます。compose の container_name です。 |
| valkey | valkey | services.valkey.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| valkey | valkey | (compose が自動で付与) | `--network-alias` | `valkey` | このネットワークの中で「valkey」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| valkey | valkey | services.valkey.ports | `--publish` | `6379:6379` | ホスト (RHEL) の 6379 番ポート (TCP) に届いた通信を、コンテナの 6379 番ポートへ転送します。 |
| valkey | valkey | services.valkey.healthcheck.test | `--health-cmd` | `valkey-cli ping \| grep -q PONG` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| valkey | valkey | services.valkey.healthcheck.interval | `--health-interval` | `3s` | 何秒おきにチェックするか: 3s |
| valkey | valkey | services.valkey.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| valkey | valkey | services.valkey.healthcheck.start_period | `--health-start-period` | `3s` | 起動直後の、失敗を数えない猶予期間: 3s |
| valkey | valkey | services.valkey.healthcheck.retries | `--health-retries` | `20` | 何回続けて失敗したら unhealthy (不健康) とするか: 20 回 |
| svf-mock | svf-mock | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| svf-mock | svf-mock | services.svf-mock.container_name | `--name` | `svf-mock` | コンテナに「svf-mock」という名前を付けます。compose の container_name です。 |
| svf-mock | svf-mock | services.svf-mock.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| svf-mock | svf-mock | (compose が自動で付与) | `--network-alias` | `svf-mock` | このネットワークの中で「svf-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| svf-mock | svf-mock | services.svf-mock.ports | `--publish` | `8280:8080` | ホスト (RHEL) の 8280 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 |
| svf-mock | svf-mock | services.svf-mock.volumes | `--volume` | `/opt/Container_Compose_file/compose/svf-mock/mappings:/home/wiremock/mappings:ro` | ホストの /opt/Container_Compose_file/compose/svf-mock/mappings をコンテナの /home/wiremock/mappings に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| svf-mock | svf-mock | services.svf-mock.healthcheck.test | `--health-cmd` | `timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| svf-mock | svf-mock | services.svf-mock.healthcheck.interval | `--health-interval` | `3s` | 何秒おきにチェックするか: 3s |
| svf-mock | svf-mock | services.svf-mock.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| svf-mock | svf-mock | services.svf-mock.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| svf-mock | svf-mock | services.svf-mock.healthcheck.retries | `--health-retries` | `40` | 何回続けて失敗したら unhealthy (不健康) とするか: 40 回 |
| ecs-metadata-mock | ecs-metadata-mock | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.container_name | `--name` | `ecs-metadata-mock` | コンテナに「ecs-metadata-mock」という名前を付けます。compose の container_name です。 |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| ecs-metadata-mock | ecs-metadata-mock | (compose が自動で付与) | `--network-alias` | `ecs-metadata-mock` | このネットワークの中で「ecs-metadata-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.ports | `--publish` | `8380:8080` | ホスト (RHEL) の 8380 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.volumes | `--volume` | `/opt/Container_Compose_file/compose/ecs-metadata-mock/mappings:/home/wiremock/mappings:ro` | ホストの /opt/Container_Compose_file/compose/ecs-metadata-mock/mappings をコンテナの /home/wiremock/mappings に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.healthcheck.test | `--health-cmd` | `timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.healthcheck.interval | `--health-interval` | `3s` | 何秒おきにチェックするか: 3s |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| ecs-metadata-mock | ecs-metadata-mock | services.ecs-metadata-mock.healthcheck.retries | `--health-retries` | `40` | 何回続けて失敗したら unhealthy (不健康) とするか: 40 回 |
| adot-collector | adot-collector | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| adot-collector | adot-collector | services.adot-collector.container_name | `--name` | `adot-collector` | コンテナに「adot-collector」という名前を付けます。compose の container_name です。 |
| adot-collector | adot-collector | services.adot-collector.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| adot-collector | adot-collector | (compose が自動で付与) | `--network-alias` | `adot-collector` | このネットワークの中で「adot-collector」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| adot-collector | adot-collector | services.adot-collector.ports | `--publish` | `4318:4318` | ホスト (RHEL) の 4318 番ポート (TCP) に届いた通信を、コンテナの 4318 番ポートへ転送します。 |
| adot-collector | adot-collector | services.adot-collector.volumes | `--volume` | `/opt/Container_Compose_file/compose/otel/adot-collector-local.yaml:/etc/otel/config.yaml:ro` | ホストの /opt/Container_Compose_file/compose/otel/adot-collector-local.yaml をコンテナの /etc/otel/config.yaml に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| adot-collector | adot-collector | services.adot-collector.environment | `--env` | `ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-3456789012` | 環境変数 ECS_CONTAINER_METADATA_URI_V4 に「http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd64…」を設定します。 |
| efs-mock | efs-mock | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| efs-mock | efs-mock | services.efs-mock.container_name | `--name` | `efs-mock` | コンテナに「efs-mock」という名前を付けます。compose の container_name です。 |
| efs-mock | efs-mock | services.efs-mock.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| efs-mock | efs-mock | (compose が自動で付与) | `--network-alias` | `efs-mock` | このネットワークの中で「efs-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| efs-mock | efs-mock | services.efs-mock.volumes | `--volume` | `eap-adot-local_efs-logs:/mnt/efs/logs` | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/efs/logs につなぎます。 |
| efs-mock | efs-mock | services.efs-mock.volumes | `--volume` | `eap-adot-local_efs-data:/mnt/efs/data` | 名前付きボリューム「eap-adot-local_efs-data」をコンテナの /mnt/efs/data につなぎます。 |
| efs-mock | efs-mock | services.efs-mock.healthcheck.test | `--health-cmd` | `test -f /tmp/efs-initialized && [ "$(stat -c %u:%g /mnt/efs/logs)" = "6301:6302" ] && [ "$(stat -c %u:%g /mnt/efs/data)" = "6301:6302" ]` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| efs-mock | efs-mock | services.efs-mock.healthcheck.interval | `--health-interval` | `5s` | 何秒おきにチェックするか: 5s |
| efs-mock | efs-mock | services.efs-mock.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| efs-mock | efs-mock | services.efs-mock.healthcheck.start_period | `--health-start-period` | `3s` | 起動直後の、失敗を数えない猶予期間: 3s |
| efs-mock | efs-mock | services.efs-mock.healthcheck.retries | `--health-retries` | `5` | 何回続けて失敗したら unhealthy (不健康) とするか: 5 回 |
| batch-mock | batch-mock | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| batch-mock | batch-mock | services.batch-mock.container_name | `--name` | `batch-mock` | コンテナに「batch-mock」という名前を付けます。compose の container_name です。 |
| batch-mock | batch-mock | services.batch-mock.user | `--user` | `6301:6302` | コンテナの中のプログラムを ユーザー 6301:6302 として動かします。 |
| batch-mock | batch-mock | services.batch-mock.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| batch-mock | batch-mock | (compose が自動で付与) | `--network-alias` | `batch-mock` | このネットワークの中で「batch-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| batch-mock | batch-mock | services.batch-mock.volumes | `--volume` | `/opt/Container_Compose_file/compose/batch-mock/efs-propagation.sh:/opt/batch-mock/efs-propagation.sh:ro` | ホストの /opt/Container_Compose_file/compose/batch-mock/efs-propagation.sh をコンテナの /opt/batch-mock/efs-propagation.sh に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| batch-mock | batch-mock | services.batch-mock.volumes | `--volume` | `eap-adot-local_efs-logs:/mnt/logs` | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/logs につなぎます。 |
| batch-mock | batch-mock | services.batch-mock.volumes | `--volume` | `eap-adot-local_efs-data:/mnt/data` | 名前付きボリューム「eap-adot-local_efs-data」をコンテナの /mnt/data につなぎます。 |
| batch-mock | batch-mock | services.batch-mock.environment | `--env` | `BATCH_MOCK_CLI=/opt/batch-mock/efs-propagation.sh` | 環境変数 BATCH_MOCK_CLI に「/opt/batch-mock/efs-propagation.sh」を設定します。 |
| batch-mock | batch-mock | services.batch-mock.environment | `--env` | `BATCH_MOCK_EFS_DIRS=/mnt/logs /mnt/data` | 環境変数 BATCH_MOCK_EFS_DIRS に「/mnt/logs /mnt/data」を設定します。 |
| batch-mock | batch-mock | services.batch-mock.healthcheck.test | `--health-cmd` | `/bin/sh /opt/batch-mock/efs-propagation.sh ready \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| batch-mock | batch-mock | services.batch-mock.healthcheck.interval | `--health-interval` | `10s` | 何秒おきにチェックするか: 10s |
| batch-mock | batch-mock | services.batch-mock.healthcheck.timeout | `--health-timeout` | `5s` | 1 回のチェックを何秒で打ち切るか: 5s |
| batch-mock | batch-mock | services.batch-mock.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| batch-mock | batch-mock | services.batch-mock.healthcheck.retries | `--health-retries` | `5` | 何回続けて失敗したら unhealthy (不健康) とするか: 5 回 |
| cloudwatch-logs-mock | cloudwatch-logs-mock | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.container_name | `--name` | `cloudwatch-logs-mock` | コンテナに「cloudwatch-logs-mock」という名前を付けます。compose の container_name です。 |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| cloudwatch-logs-mock | cloudwatch-logs-mock | (compose が自動で付与) | `--network-alias` | `cloudwatch-logs-mock` | このネットワークの中で「cloudwatch-logs-mock」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.ports | `--publish` | `8480:8080` | ホスト (RHEL) の 8480 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.volumes | `--volume` | `/opt/Container_Compose_file/compose/cloudwatch-logs-mock/mappings:/home/wiremock/mappings:ro` | ホストの /opt/Container_Compose_file/compose/cloudwatch-logs-mock/mappings をコンテナの /home/wiremock/mappings に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.healthcheck.test | `--health-cmd` | `timeout 2 bash -c '</dev/tcp/127.0.0.1/8080' \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.healthcheck.interval | `--health-interval` | `3s` | 何秒おきにチェックするか: 3s |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| cloudwatch-logs-mock | cloudwatch-logs-mock | services.cloudwatch-logs-mock.healthcheck.retries | `--health-retries` | `40` | 何回続けて失敗したら unhealthy (不健康) とするか: 40 回 |
| cwagent | cwagent | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| cwagent | cwagent | services.cwagent.container_name | `--name` | `cwagent` | コンテナに「cwagent」という名前を付けます。compose の container_name です。 |
| cwagent | cwagent | services.cwagent.group_add | `--group-add` | `6302` | そのユーザーに追加のグループ 6302 を足します (共有フォルダの書き込み権限などに使います)。 |
| cwagent | cwagent | services.cwagent.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| cwagent | cwagent | (compose が自動で付与) | `--network-alias` | `cwagent` | このネットワークの中で「cwagent」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| cwagent | cwagent | services.cwagent.volumes | `--volume` | `/opt/Container_Compose_file/compose/cwagent/cwagent-config.json:/etc/cwagentconfig/cwagent-config.json:ro` | ホストの /opt/Container_Compose_file/compose/cwagent/cwagent-config.json をコンテナの /etc/cwagentconfig/cwagent-config.json に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| cwagent | cwagent | services.cwagent.volumes | `--volume` | `/opt/Container_Compose_file/compose/cwagent/aws-credentials:/root/.aws/credentials:ro` | ホストの /opt/Container_Compose_file/compose/cwagent/aws-credentials をコンテナの /root/.aws/credentials に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| cwagent | cwagent | services.cwagent.volumes | `--volume` | `/opt/Container_Compose_file/compose/cwagent/verify-mount.sh:/opt/cwagent-verify/verify-mount.sh:ro` | ホストの /opt/Container_Compose_file/compose/cwagent/verify-mount.sh をコンテナの /opt/cwagent-verify/verify-mount.sh に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| cwagent | cwagent | services.cwagent.volumes | `--volume` | `eap-adot-local_efs-logs:/mnt/logs:ro` | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/logs につなぎます (読み取り専用)。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `AWS_REGION=ap-northeast-1` | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `CWA_VERIFY_CONFIG_DIR=/etc/cwagentconfig` | 環境変数 CWA_VERIFY_CONFIG_DIR に「/etc/cwagentconfig」を設定します。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `CWA_VERIFY_EXPECT_MODE=775` | 環境変数 CWA_VERIFY_EXPECT_MODE に「775」を設定します。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `CWA_VERIFY_EXPECT_OWNER=6301:6302` | 環境変数 CWA_VERIFY_EXPECT_OWNER に「6301:6302」を設定します。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `CWA_VERIFY_MOUNTS=/mnt/logs` | 環境変数 CWA_VERIFY_MOUNTS に「/mnt/logs」を設定します。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `CWA_VERIFY_RECHECK_COUNT=5` | 環境変数 CWA_VERIFY_RECHECK_COUNT に「5」を設定します。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `CWA_VERIFY_RECHECK_INTERVAL=20` | 環境変数 CWA_VERIFY_RECHECK_INTERVAL に「20」を設定します。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `CWA_VERIFY_RELAY_AGENT_LOG=1` | 環境変数 CWA_VERIFY_RELAY_AGENT_LOG に「1」を設定します。 |
| cwagent | cwagent | services.cwagent.environment | `--env` | `ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-4567890123` | 環境変数 ECS_CONTAINER_METADATA_URI_V4 に「http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd64…」を設定します。 |
| cwagent | cwagent | services.cwagent.healthcheck.test | `--health-cmd` | `read -r v < /tmp/cwagent-verify.boot.result && [ "$v" != FAIL ]` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| cwagent | cwagent | services.cwagent.healthcheck.interval | `--health-interval` | `5s` | 何秒おきにチェックするか: 5s |
| cwagent | cwagent | services.cwagent.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| cwagent | cwagent | services.cwagent.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| cwagent | cwagent | services.cwagent.healthcheck.retries | `--health-retries` | `12` | 何回続けて失敗したら unhealthy (不健康) とするか: 12 回 |
| cwagent | cwagent | services.cwagent.entrypoint | `--entrypoint` | `/bin/sh` | 最初に動かすプログラム (ENTRYPOINT) を /bin/sh にします。残りの部分 /opt/cwagent-verify/verify-mount.sh はイメージ名の後ろに引数として書きます (docker run の --entrypoint には 1 語しか書けないため)。 |
| sqs | sqs | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| sqs | sqs | services.sqs.container_name | `--name` | `sqs` | コンテナに「sqs」という名前を付けます。compose の container_name です。 |
| sqs | sqs | services.sqs.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| sqs | sqs | (compose が自動で付与) | `--network-alias` | `sqs` | このネットワークの中で「sqs」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| sqs | sqs | services.sqs.ports | `--publish` | `9324:9324` | ホスト (RHEL) の 9324 番ポート (TCP) に届いた通信を、コンテナの 9324 番ポートへ転送します。 |
| sqs | sqs | services.sqs.ports | `--publish` | `9325:9325` | ホスト (RHEL) の 9325 番ポート (TCP) に届いた通信を、コンテナの 9325 番ポートへ転送します。 |
| sqs | sqs | services.sqs.volumes | `--volume` | `/opt/Container_Compose_file/compose/sqs/elasticmq.conf:/opt/elasticmq.conf:ro` | ホストの /opt/Container_Compose_file/compose/sqs/elasticmq.conf をコンテナの /opt/elasticmq.conf に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| pki-init | pki-init | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| pki-init | pki-init | services.pki-init.container_name | `--name` | `pki-init` | コンテナに「pki-init」という名前を付けます。compose の container_name です。 |
| pki-init | pki-init | services.pki-init.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| pki-init | pki-init | (compose が自動で付与) | `--network-alias` | `pki-init` | このネットワークの中で「pki-init」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| pki-init | pki-init | services.pki-init.volumes | `--volume` | `eap-adot-local_pki:/pki` | 名前付きボリューム「eap-adot-local_pki」をコンテナの /pki につなぎます。 |
| pki-init | pki-init | services.pki-init.volumes | `--volume` | `/opt/Container_Compose_file/compose/pki/provided:/provided:ro` | ホストの /opt/Container_Compose_file/compose/pki/provided をコンテナの /provided に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| pki-init | pki-init | services.pki-init.volumes | `--volume` | `/opt/Container_Compose_file/compose/pki/export:/export` | ホストの /opt/Container_Compose_file/compose/pki/export をコンテナの /export に直接つなぎます (バインドマウント)。ホスト側に無ければ空のフォルダが作られます。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_CA_CN=Local Test Self-Signed CA` | 環境変数 PKI_CA_CN に「Local Test Self-Signed CA」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_DAYS_CA=3650` | 環境変数 PKI_DAYS_CA に「3650」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_DAYS_LEAF=825` | 環境変数 PKI_DAYS_LEAF に「825」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_EXPORT_DIR=/export` | 環境変数 PKI_EXPORT_DIR に「/export」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_EXPORT_KEY=1` | 環境変数 PKI_EXPORT_KEY に「1」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_FORCE_REGENERATE=0` | 環境変数 PKI_FORCE_REGENERATE に「0」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_KEYSTORE_PASSWORD=changeit` | 環境変数 PKI_KEYSTORE_PASSWORD に「changeit」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_MODE=auto` | 環境変数 PKI_MODE に「auto」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_PROVIDED_DIR=/provided` | 環境変数 PKI_PROVIDED_DIR に「/provided」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_ROOT=/pki` | 環境変数 PKI_ROOT に「/pki」を設定します。 |
| pki-init | pki-init | services.pki-init.environment | `--env` | `PKI_TRUST_LOCAL_CA=1` | 環境変数 PKI_TRUST_LOCAL_CA に「1」を設定します。 |
| pki-init | pki-init | services.pki-init.healthcheck.test | `--health-cmd` | `test -f /pki/.pki-ready && test -f /pki/ca/cacert.crt && test -f /pki/ca/verify-bundle.crt && test -f /pki/secure-api/server.p12 && test -f /pki/alb/selfsigned/server.key && test -f /pki/alb/ca-issued/server.key && test -f /pki/rds-proxy/server.key && test -f /pki/trust/cacert.crt` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| pki-init | pki-init | services.pki-init.healthcheck.interval | `--health-interval` | `3s` | 何秒おきにチェックするか: 3s |
| pki-init | pki-init | services.pki-init.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| pki-init | pki-init | services.pki-init.healthcheck.start_period | `--health-start-period` | `2s` | 起動直後の、失敗を数えない猶予期間: 2s |
| pki-init | pki-init | services.pki-init.healthcheck.retries | `--health-retries` | `20` | 何回続けて失敗したら unhealthy (不健康) とするか: 20 回 |
| mysql | mysql | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| mysql | mysql | services.mysql.container_name | `--name` | `mysql` | コンテナに「mysql」という名前を付けます。compose の container_name です。 |
| mysql | mysql | services.mysql.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| mysql | mysql | (compose が自動で付与) | `--network-alias` | `mysql` | このネットワークの中で「mysql」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| mysql | mysql | services.mysql.ports | `--publish` | `3306:3306` | ホスト (RHEL) の 3306 番ポート (TCP) に届いた通信を、コンテナの 3306 番ポートへ転送します。 |
| mysql | mysql | services.mysql.volumes | `--volume` | `/opt/Container_Compose_file/compose/mysql/init.sql:/docker-entrypoint-initdb.d/10-init.sql:ro` | ホストの /opt/Container_Compose_file/compose/mysql/init.sql をコンテナの /docker-entrypoint-initdb.d/10-init.sql に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| mysql | mysql | services.mysql.volumes | `--volume` | `/opt/Container_Compose_file/compose/mysql/init-infdb.sh:/docker-entrypoint-initdb.d/20-init-infdb.sh:ro` | ホストの /opt/Container_Compose_file/compose/mysql/init-infdb.sh をコンテナの /docker-entrypoint-initdb.d/20-init-infdb.sh に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| mysql | mysql | services.mysql.volumes | `--volume` | `eap-adot-local_pki:/mnt/pki:ro` | 名前付きボリューム「eap-adot-local_pki」をコンテナの /mnt/pki につなぎます (読み取り専用)。 |
| mysql | mysql | services.mysql.volumes | `--volume` | `eap-adot-local_mysql-data:/var/lib/mysql` | 名前付きボリューム「eap-adot-local_mysql-data」をコンテナの /var/lib/mysql につなぎます。 |
| mysql | mysql | services.mysql.environment | `--env` | `INFDB_PASSWORD=ChangeMe_infdb_P@ss123` | 環境変数 INFDB_PASSWORD に「ChangeMe_infdb_P@ss123」を設定します。 |
| mysql | mysql | services.mysql.environment | `--env` | `MYSQL_DATABASE=appdb` | 環境変数 MYSQL_DATABASE に「appdb」を設定します。 |
| mysql | mysql | services.mysql.environment | `--env` | `MYSQL_PASSWORD=ChangeMe_appdb_P@ss123` | 環境変数 MYSQL_PASSWORD に「ChangeMe_appdb_P@ss123」を設定します。 |
| mysql | mysql | services.mysql.environment | `--env` | `MYSQL_ROOT_PASSWORD=localdev-root-change-me` | 環境変数 MYSQL_ROOT_PASSWORD に「localdev-root-change-me」を設定します。 |
| mysql | mysql | services.mysql.environment | `--env` | `MYSQL_USER=appuser` | 環境変数 MYSQL_USER に「appuser」を設定します。 |
| mysql | mysql | services.mysql.healthcheck.test | `--health-cmd` | `mysql --ssl-mode=REQUIRED -h 127.0.0.1 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -D"$MYSQL_DATABASE" -e 'SELECT 1' >/dev/null 2>&1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| mysql | mysql | services.mysql.healthcheck.interval | `--health-interval` | `5s` | 何秒おきにチェックするか: 5s |
| mysql | mysql | services.mysql.healthcheck.timeout | `--health-timeout` | `5s` | 1 回のチェックを何秒で打ち切るか: 5s |
| mysql | mysql | services.mysql.healthcheck.start_period | `--health-start-period` | `20s` | 起動直後の、失敗を数えない猶予期間: 20s |
| mysql | mysql | services.mysql.healthcheck.retries | `--health-retries` | `60` | 何回続けて失敗したら unhealthy (不健康) とするか: 60 回 |
| backend | backend | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| backend | backend | services.backend.container_name | `--name` | `backend` | コンテナに「backend」という名前を付けます。compose の container_name です。 |
| backend | backend | services.backend.group_add | `--group-add` | `6302` | そのユーザーに追加のグループ 6302 を足します (共有フォルダの書き込み権限などに使います)。 |
| backend | backend | services.backend.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| backend | backend | (compose が自動で付与) | `--network-alias` | `backend` | このネットワークの中で「backend」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| backend | backend | services.backend.ports | `--publish` | `8180:8180` | ホスト (RHEL) の 8180 番ポート (TCP) に届いた通信を、コンテナの 8180 番ポートへ転送します。 |
| backend | backend | services.backend.volumes | `--volume` | `eap-adot-local_efs-logs:/mnt/logs` | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/logs につなぎます。 |
| backend | backend | services.backend.volumes | `--volume` | `eap-adot-local_efs-data:/mnt/data` | 名前付きボリューム「eap-adot-local_efs-data」をコンテナの /mnt/data につなぎます。 |
| backend | backend | services.backend.volumes | `--volume` | `eap-adot-local_pki:/mnt/pki:ro` | 名前付きボリューム「eap-adot-local_pki」をコンテナの /mnt/pki につなぎます (読み取り専用)。 |
| backend | backend | services.backend.environment | `--env` | `ASYNC_QUEUE_NAME=app-async-queue` | 環境変数 ASYNC_QUEUE_NAME に「app-async-queue」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `ASYNC_SQS_ENDPOINT=http://sqs:9324` | 環境変数 ASYNC_SQS_ENDPOINT に「http://sqs:9324」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `AWS_REGION=ap-northeast-1` | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `DB_HOST=mysql` | 環境変数 DB_HOST に「mysql」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `DB_NAME=appdb` | 環境変数 DB_NAME に「appdb」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `DB_PASSWORD=ChangeMe_appdb_P@ss123` | 環境変数 DB_PASSWORD に「ChangeMe_appdb_P@ss123」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `DB_PORT=3306` | 環境変数 DB_PORT に「3306」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `DB_SSL_MODE=VERIFY_IDENTITY` | 環境変数 DB_SSL_MODE に「VERIFY_IDENTITY」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `DB_USER=appuser` | 環境変数 DB_USER に「appuser」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-2345678901` | 環境変数 ECS_CONTAINER_METADATA_URI_V4 に「http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd64…」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `JBOSS_TRUSTSTORE_FILE=/opt/server/standalone/configuration/jboss-truststore.p12` | 環境変数 JBOSS_TRUSTSTORE_FILE に「/opt/server/standalone/configuration/jboss-truststore.p12」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `JBOSS_TRUSTSTORE_PASSWORD=changeit` | 環境変数 JBOSS_TRUSTSTORE_PASSWORD に「changeit」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `OTEL_EXPORTER_OTLP_ENDPOINT=http://adot-collector:4318` | 環境変数 OTEL_EXPORTER_OTLP_ENDPOINT に「http://adot-collector:4318」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` | 環境変数 OTEL_EXPORTER_OTLP_PROTOCOL に「http/protobuf」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `OTEL_RESOURCE_ATTRIBUTES=service.namespace=myapp,service.version=local,deployment.environment=local,aws.ecs.service.name=local-compose` | 環境変数 OTEL_RESOURCE_ATTRIBUTES に「service.namespace=myapp,service.version=local,deployment.env…」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `OTEL_SERVICE_NAME=myapp-back` | 環境変数 OTEL_SERVICE_NAME に「myapp-back」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `OTEL_TRACES_SAMPLER=parentbased_always_on` | 環境変数 OTEL_TRACES_SAMPLER に「parentbased_always_on」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `PKI_TRUST_DIR=/mnt/pki/trust` | 環境変数 PKI_TRUST_DIR に「/mnt/pki/trust」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `PORT_OFFSET=100` | 環境変数 PORT_OFFSET に「100」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `SECURE_API_URL=https://secure-api:8443/api/v1/ping` | 環境変数 SECURE_API_URL に「https://secure-api:8443/api/v1/ping」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `SECURE_API_VIA_ALB_URL=https://alb/secure/v1/ping` | 環境変数 SECURE_API_VIA_ALB_URL に「https://alb/secure/v1/ping」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `SVF_BASE_URL=http://svf-mock:8080` | 環境変数 SVF_BASE_URL に「http://svf-mock:8080」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `TX_NODE_ID=back-local-1` | 環境変数 TX_NODE_ID に「back-local-1」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `VALKEY_HOST=valkey` | 環境変数 VALKEY_HOST に「valkey」を設定します。 |
| backend | backend | services.backend.environment | `--env` | `VALKEY_PORT=6379` | 環境変数 VALKEY_PORT に「6379」を設定します。 |
| backend | backend | services.backend.healthcheck.test | `--health-cmd` | `curl -fs http://127.0.0.1:8180/ >/dev/null \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| backend | backend | services.backend.healthcheck.interval | `--health-interval` | `30s` | 何秒おきにチェックするか: 30s |
| backend | backend | services.backend.healthcheck.timeout | `--health-timeout` | `5s` | 1 回のチェックを何秒で打ち切るか: 5s |
| backend | backend | services.backend.healthcheck.start_period | `--health-start-period` | `2m0s` | 起動直後の、失敗を数えない猶予期間: 2m0s |
| backend | backend | services.backend.healthcheck.retries | `--health-retries` | `3` | 何回続けて失敗したら unhealthy (不健康) とするか: 3 回 |
| frontend | frontend | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| frontend | frontend | services.frontend.container_name | `--name` | `frontend` | コンテナに「frontend」という名前を付けます。compose の container_name です。 |
| frontend | frontend | services.frontend.group_add | `--group-add` | `6302` | そのユーザーに追加のグループ 6302 を足します (共有フォルダの書き込み権限などに使います)。 |
| frontend | frontend | services.frontend.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| frontend | frontend | (compose が自動で付与) | `--network-alias` | `frontend` | このネットワークの中で「frontend」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| frontend | frontend | services.frontend.ports | `--publish` | `8080:8080` | ホスト (RHEL) の 8080 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 |
| frontend | frontend | services.frontend.volumes | `--volume` | `eap-adot-local_efs-logs:/mnt/logs` | 名前付きボリューム「eap-adot-local_efs-logs」をコンテナの /mnt/logs につなぎます。 |
| frontend | frontend | services.frontend.volumes | `--volume` | `eap-adot-local_efs-data:/mnt/data` | 名前付きボリューム「eap-adot-local_efs-data」をコンテナの /mnt/data につなぎます。 |
| frontend | frontend | services.frontend.volumes | `--volume` | `eap-adot-local_pki:/mnt/pki:ro` | 名前付きボリューム「eap-adot-local_pki」をコンテナの /mnt/pki につなぎます (読み取り専用)。 |
| frontend | frontend | services.frontend.environment | `--env` | `ASYNC_QUEUE_NAME=app-async-queue` | 環境変数 ASYNC_QUEUE_NAME に「app-async-queue」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `ASYNC_SQS_ENDPOINT=http://sqs:9324` | 環境変数 ASYNC_SQS_ENDPOINT に「http://sqs:9324」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `AWS_REGION=ap-northeast-1` | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `BACK_BASE_URL=http://backend:8180` | 環境変数 BACK_BASE_URL に「http://backend:8180」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `DB_HOST=mysql` | 環境変数 DB_HOST に「mysql」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `DB_NAME=appdb` | 環境変数 DB_NAME に「appdb」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `DB_PASSWORD=ChangeMe_appdb_P@ss123` | 環境変数 DB_PASSWORD に「ChangeMe_appdb_P@ss123」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `DB_PORT=3306` | 環境変数 DB_PORT に「3306」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `DB_SSL_MODE=VERIFY_IDENTITY` | 環境変数 DB_SSL_MODE に「VERIFY_IDENTITY」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `DB_USER=appuser` | 環境変数 DB_USER に「appuser」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `ECS_CONTAINER_METADATA_URI_V4=http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd6414f5c-1234567890` | 環境変数 ECS_CONTAINER_METADATA_URI_V4 に「http://ecs-metadata-mock:8080/v4/158d1c8083dd49d6b527399fd64…」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `JBOSS_TRUSTSTORE_FILE=/opt/server/standalone/configuration/jboss-truststore.p12` | 環境変数 JBOSS_TRUSTSTORE_FILE に「/opt/server/standalone/configuration/jboss-truststore.p12」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `JBOSS_TRUSTSTORE_PASSWORD=changeit` | 環境変数 JBOSS_TRUSTSTORE_PASSWORD に「changeit」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `OTEL_EXPORTER_OTLP_ENDPOINT=http://adot-collector:4318` | 環境変数 OTEL_EXPORTER_OTLP_ENDPOINT に「http://adot-collector:4318」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` | 環境変数 OTEL_EXPORTER_OTLP_PROTOCOL に「http/protobuf」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `OTEL_RESOURCE_ATTRIBUTES=service.namespace=myapp,service.version=local,deployment.environment=local,aws.ecs.service.name=local-compose` | 環境変数 OTEL_RESOURCE_ATTRIBUTES に「service.namespace=myapp,service.version=local,deployment.env…」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `OTEL_SERVICE_NAME=myapp-front` | 環境変数 OTEL_SERVICE_NAME に「myapp-front」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `OTEL_TRACES_SAMPLER=parentbased_always_on` | 環境変数 OTEL_TRACES_SAMPLER に「parentbased_always_on」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `PKI_TRUST_DIR=/mnt/pki/trust` | 環境変数 PKI_TRUST_DIR に「/mnt/pki/trust」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `SECURE_API_URL=https://secure-api:8443/api/v1/ping` | 環境変数 SECURE_API_URL に「https://secure-api:8443/api/v1/ping」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `SECURE_API_VIA_ALB_URL=https://alb/secure/v1/ping` | 環境変数 SECURE_API_VIA_ALB_URL に「https://alb/secure/v1/ping」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `TX_NODE_ID=front-local-1` | 環境変数 TX_NODE_ID に「front-local-1」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `VALKEY_HOST=valkey` | 環境変数 VALKEY_HOST に「valkey」を設定します。 |
| frontend | frontend | services.frontend.environment | `--env` | `VALKEY_PORT=6379` | 環境変数 VALKEY_PORT に「6379」を設定します。 |
| frontend | frontend | services.frontend.healthcheck.test | `--health-cmd` | `curl -fs http://127.0.0.1:8080/ >/dev/null \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| frontend | frontend | services.frontend.healthcheck.interval | `--health-interval` | `30s` | 何秒おきにチェックするか: 30s |
| frontend | frontend | services.frontend.healthcheck.timeout | `--health-timeout` | `5s` | 1 回のチェックを何秒で打ち切るか: 5s |
| frontend | frontend | services.frontend.healthcheck.start_period | `--health-start-period` | `2m0s` | 起動直後の、失敗を数えない猶予期間: 2m0s |
| frontend | frontend | services.frontend.healthcheck.retries | `--health-retries` | `3` | 何回続けて失敗したら unhealthy (不健康) とするか: 3 回 |
| alb-healthcheck | alb-healthcheck | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.container_name | `--name` | `alb-healthcheck` | コンテナに「alb-healthcheck」という名前を付けます。compose の container_name です。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| alb-healthcheck | alb-healthcheck | (compose が自動で付与) | `--network-alias` | `alb-healthcheck` | このネットワークの中で「alb-healthcheck」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.ports | `--publish` | `8580:8080` | ホスト (RHEL) の 8580 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.volumes | `--volume` | `/opt/Container_Compose_file/compose/alb-healthcheck/healthcheck.py:/opt/alb-healthcheck/healthcheck.py:ro` | ホストの /opt/Container_Compose_file/compose/alb-healthcheck/healthcheck.py をコンテナの /opt/alb-healthcheck/healthcheck.py に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.volumes | `--volume` | `/opt/Container_Compose_file/compose/alb-healthcheck/targets.json:/etc/alb-healthcheck/targets.json:ro` | ホストの /opt/Container_Compose_file/compose/alb-healthcheck/targets.json をコンテナの /etc/alb-healthcheck/targets.json に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.environment | `--env` | `ALB_HEALTHCHECK_CLI=/opt/alb-healthcheck/healthcheck.py` | 環境変数 ALB_HEALTHCHECK_CLI に「/opt/alb-healthcheck/healthcheck.py」を設定します。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.environment | `--env` | `ALB_HEALTHCHECK_HISTORY_LIMIT=10` | 環境変数 ALB_HEALTHCHECK_HISTORY_LIMIT に「10」を設定します。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.environment | `--env` | `ALB_HEALTHCHECK_LISTEN_PORT=8080` | 環境変数 ALB_HEALTHCHECK_LISTEN_PORT に「8080」を設定します。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.environment | `--env` | `ALB_HEALTHCHECK_TARGETS_FILE=/etc/alb-healthcheck/targets.json` | 環境変数 ALB_HEALTHCHECK_TARGETS_FILE に「/etc/alb-healthcheck/targets.json」を設定します。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.environment | `--env` | `PYTHONUNBUFFERED=1` | 環境変数 PYTHONUNBUFFERED に「1」を設定します。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.healthcheck.test | `--health-cmd` | `python3 /opt/alb-healthcheck/healthcheck.py ready \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.healthcheck.interval | `--health-interval` | `10s` | 何秒おきにチェックするか: 10s |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.healthcheck.timeout | `--health-timeout` | `5s` | 1 回のチェックを何秒で打ち切るか: 5s |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| alb-healthcheck | alb-healthcheck | services.alb-healthcheck.healthcheck.retries | `--health-retries` | `5` | 何回続けて失敗したら unhealthy (不健康) とするか: 5 回 |
| alb-front | alb-front | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| alb-front | alb-front | services.alb-front.container_name | `--name` | `alb-front` | コンテナに「alb-front」という名前を付けます。compose の container_name です。 |
| alb-front | alb-front | services.alb-front.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| alb-front | alb-front | (compose が自動で付与) | `--network-alias` | `alb-front` | このネットワークの中で「alb-front」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| alb-front | alb-front | services.alb-front.ports | `--publish` | `8443:8443` | ホスト (RHEL) の 8443 番ポート (TCP) に届いた通信を、コンテナの 8443 番ポートへ転送します。 |
| alb-front | alb-front | services.alb-front.ports | `--publish` | `8581:8081` | ホスト (RHEL) の 8581 番ポート (TCP) に届いた通信を、コンテナの 8081 番ポートへ転送します。 |
| alb-front | alb-front | services.alb-front.volumes | `--volume` | `/opt/Container_Compose_file/compose/alb-front/alb-front.py:/opt/alb-front/alb-front.py:ro` | ホストの /opt/Container_Compose_file/compose/alb-front/alb-front.py をコンテナの /opt/alb-front/alb-front.py に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| alb-front | alb-front | services.alb-front.volumes | `--volume` | `eap-adot-local_pki:/pki:ro` | 名前付きボリューム「eap-adot-local_pki」をコンテナの /pki につなぎます (読み取り専用)。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_ADMIN_PORT=8081` | 環境変数 ALB_FRONT_ADMIN_PORT に「8081」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_CA_BUNDLE=/pki/ca/verify-bundle.crt` | 環境変数 ALB_FRONT_CA_BUNDLE に「/pki/ca/verify-bundle.crt」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_CHECK_HOST=localhost` | 環境変数 ALB_FRONT_CHECK_HOST に「localhost」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_CHECK_PATH=/iwinmichl/api/redirect-check/redirect` | 環境変数 ALB_FRONT_CHECK_PATH に「/iwinmichl/api/redirect-check/redirect」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_CLI=/opt/alb-front/alb-front.py` | 環境変数 ALB_FRONT_CLI に「/opt/alb-front/alb-front.py」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_CONNECT_TIMEOUT=10` | 環境変数 ALB_FRONT_CONNECT_TIMEOUT に「10」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_HTTPS_PORT=8443` | 環境変数 ALB_FRONT_HTTPS_PORT に「8443」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_IDLE_TIMEOUT=60` | 環境変数 ALB_FRONT_IDLE_TIMEOUT に「60」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_TARGET=http://frontend:8080` | 環境変数 ALB_FRONT_TARGET に「http://frontend:8080」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_TLS_CERT=/pki/alb/ca-issued/fullchain.crt` | 環境変数 ALB_FRONT_TLS_CERT に「/pki/alb/ca-issued/fullchain.crt」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `ALB_FRONT_TLS_KEY=/pki/alb/ca-issued/server.key` | 環境変数 ALB_FRONT_TLS_KEY に「/pki/alb/ca-issued/server.key」を設定します。 |
| alb-front | alb-front | services.alb-front.environment | `--env` | `PYTHONUNBUFFERED=1` | 環境変数 PYTHONUNBUFFERED に「1」を設定します。 |
| secure-api | secure-api | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| secure-api | secure-api | services.secure-api.container_name | `--name` | `secure-api` | コンテナに「secure-api」という名前を付けます。compose の container_name です。 |
| secure-api | secure-api | services.secure-api.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| secure-api | secure-api | (compose が自動で付与) | `--network-alias` | `secure-api` | このネットワークの中で「secure-api」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| secure-api | secure-api | services.secure-api.ports | `--publish` | `8543:8443` | ホスト (RHEL) の 8543 番ポート (TCP) に届いた通信を、コンテナの 8443 番ポートへ転送します。 |
| secure-api | secure-api | services.secure-api.volumes | `--volume` | `/opt/Container_Compose_file/compose/secure-api/mappings:/home/wiremock/mappings:ro` | ホストの /opt/Container_Compose_file/compose/secure-api/mappings をコンテナの /home/wiremock/mappings に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| secure-api | secure-api | services.secure-api.volumes | `--volume` | `eap-adot-local_pki:/pki:ro` | 名前付きボリューム「eap-adot-local_pki」をコンテナの /pki につなぎます (読み取り専用)。 |
| secure-api | secure-api | services.secure-api.healthcheck.test | `--health-cmd` | `timeout 2 bash -c '</dev/tcp/127.0.0.1/8443' \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| secure-api | secure-api | services.secure-api.healthcheck.interval | `--health-interval` | `3s` | 何秒おきにチェックするか: 3s |
| secure-api | secure-api | services.secure-api.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| secure-api | secure-api | services.secure-api.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| secure-api | secure-api | services.secure-api.healthcheck.retries | `--health-retries` | `40` | 何回続けて失敗したら unhealthy (不健康) とするか: 40 回 |
| maintenance-lambda | maintenance-lambda | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| maintenance-lambda | maintenance-lambda | services.maintenance-lambda.container_name | `--name` | `maintenance-lambda` | コンテナに「maintenance-lambda」という名前を付けます。compose の container_name です。 |
| maintenance-lambda | maintenance-lambda | services.maintenance-lambda.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| maintenance-lambda | maintenance-lambda | (compose が自動で付与) | `--network-alias` | `maintenance-lambda` | このネットワークの中で「maintenance-lambda」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| maintenance-lambda | maintenance-lambda | services.maintenance-lambda.ports | `--publish` | `9001:8080` | ホスト (RHEL) の 9001 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 |
| maintenance-lambda | maintenance-lambda | services.maintenance-lambda.volumes | `--volume` | `/opt/Container_Compose_file/compose/maintenance-lambda/app:/var/task:ro` | ホストの /opt/Container_Compose_file/compose/maintenance-lambda/app をコンテナの /var/task に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| maintenance-lambda | maintenance-lambda | services.maintenance-lambda.environment | `--env` | `MAINTENANCE_STATUS_CODE=503` | 環境変数 MAINTENANCE_STATUS_CODE に「503」を設定します。 |
| maintenance-lambda | maintenance-lambda | services.maintenance-lambda.environment | `--env` | `MAINTENANCE_UNTIL=` | 環境変数 MAINTENANCE_UNTIL に「」を設定します。 |
| maintenance-lambda | maintenance-lambda | services.maintenance-lambda.environment | `--env` | `RETRY_AFTER_SECONDS=300` | 環境変数 RETRY_AFTER_SECONDS に「300」を設定します。 |
| alb-lambda-adapter | alb-lambda-adapter | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| alb-lambda-adapter | alb-lambda-adapter | services.alb-lambda-adapter.container_name | `--name` | `alb-lambda-adapter` | コンテナに「alb-lambda-adapter」という名前を付けます。compose の container_name です。 |
| alb-lambda-adapter | alb-lambda-adapter | services.alb-lambda-adapter.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| alb-lambda-adapter | alb-lambda-adapter | (compose が自動で付与) | `--network-alias` | `alb-lambda-adapter` | このネットワークの中で「alb-lambda-adapter」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| alb-lambda-adapter | alb-lambda-adapter | services.alb-lambda-adapter.ports | `--publish` | `9081:8080` | ホスト (RHEL) の 9081 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 |
| alb-lambda-adapter | alb-lambda-adapter | services.alb-lambda-adapter.volumes | `--volume` | `/opt/Container_Compose_file/compose/alb-lambda-adapter/adapter.py:/app/adapter.py:ro` | ホストの /opt/Container_Compose_file/compose/alb-lambda-adapter/adapter.py をコンテナの /app/adapter.py に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| alb-lambda-adapter | alb-lambda-adapter | services.alb-lambda-adapter.environment | `--env` | `LAMBDA_INVOKE_URL=http://maintenance-lambda:8080/2015-03-31/functions/function/invocations` | 環境変数 LAMBDA_INVOKE_URL に「http://maintenance-lambda:8080/2015-03-31/functions/function…」を設定します。 |
| alb-lambda-adapter | alb-lambda-adapter | services.alb-lambda-adapter.environment | `--env` | `LISTEN_PORT=8080` | 環境変数 LISTEN_PORT に「8080」を設定します。 |
| alb | alb | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| alb | alb | services.alb.container_name | `--name` | `alb` | コンテナに「alb」という名前を付けます。compose の container_name です。 |
| alb | alb | services.alb.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| alb | alb | (compose が自動で付与) | `--network-alias` | `alb` | このネットワークの中で「alb」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| alb | alb | services.alb.ports | `--publish` | `9080:80` | ホスト (RHEL) の 9080 番ポート (TCP) に届いた通信を、コンテナの 80 番ポートへ転送します。 |
| alb | alb | services.alb.ports | `--publish` | `9443:443` | ホスト (RHEL) の 9443 番ポート (TCP) に届いた通信を、コンテナの 443 番ポートへ転送します。 |
| alb | alb | services.alb.volumes | `--volume` | `/opt/Container_Compose_file/compose/alb/nginx.conf:/etc/nginx/nginx.conf:ro` | ホストの /opt/Container_Compose_file/compose/alb/nginx.conf をコンテナの /etc/nginx/nginx.conf に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| alb | alb | services.alb.volumes | `--volume` | `/opt/Container_Compose_file/compose/alb/rules:/etc/nginx/rules:ro` | ホストの /opt/Container_Compose_file/compose/alb/rules をコンテナの /etc/nginx/rules に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| alb | alb | services.alb.volumes | `--volume` | `/opt/Container_Compose_file/compose/alb/rules-tls:/etc/nginx/rules-tls:ro` | ホストの /opt/Container_Compose_file/compose/alb/rules-tls をコンテナの /etc/nginx/rules-tls に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| alb | alb | services.alb.volumes | `--volume` | `/opt/Container_Compose_file/compose/alb/tls:/etc/nginx/tls:ro` | ホストの /opt/Container_Compose_file/compose/alb/tls をコンテナの /etc/nginx/tls に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| alb | alb | services.alb.volumes | `--volume` | `eap-adot-local_pki:/pki:ro` | 名前付きボリューム「eap-adot-local_pki」をコンテナの /pki につなぎます (読み取り専用)。 |
| alb | alb | services.alb.healthcheck.test | `--health-cmd` | `wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 \|\| exit 1` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| alb | alb | services.alb.healthcheck.interval | `--health-interval` | `10s` | 何秒おきにチェックするか: 10s |
| alb | alb | services.alb.healthcheck.timeout | `--health-timeout` | `5s` | 1 回のチェックを何秒で打ち切るか: 5s |
| alb | alb | services.alb.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| alb | alb | services.alb.healthcheck.retries | `--health-retries` | `5` | 何回続けて失敗したら unhealthy (不健康) とするか: 5 回 |
| lambda | lambda | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| lambda | lambda | services.lambda.container_name | `--name` | `lambda` | コンテナに「lambda」という名前を付けます。compose の container_name です。 |
| lambda | lambda | services.lambda.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| lambda | lambda | (compose が自動で付与) | `--network-alias` | `lambda` | このネットワークの中で「lambda」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| lambda | lambda | services.lambda.ports | `--publish` | `9000:8080` | ホスト (RHEL) の 9000 番ポート (TCP) に届いた通信を、コンテナの 8080 番ポートへ転送します。 |
| lambda | lambda | services.lambda.volumes | `--volume` | `/opt/Container_Compose_file/compose/lambda/app:/var/task:ro` | ホストの /opt/Container_Compose_file/compose/lambda/app をコンテナの /var/task に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| lambda | lambda | services.lambda.environment | `--env` | `ALB_ENDPOINT=http://alb:80` | 環境変数 ALB_ENDPOINT に「http://alb:80」を設定します。 |
| lambda | lambda | services.lambda.environment | `--env` | `BACK_PATH=/async/receive` | 環境変数 BACK_PATH に「/async/receive」を設定します。 |
| lambda | lambda | services.lambda.environment | `--env` | `HTTP_TIMEOUT_SECONDS=10` | 環境変数 HTTP_TIMEOUT_SECONDS に「10」を設定します。 |
| lambda-esm | lambda-esm | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| lambda-esm | lambda-esm | services.lambda-esm.container_name | `--name` | `lambda-esm` | コンテナに「lambda-esm」という名前を付けます。compose の container_name です。 |
| lambda-esm | lambda-esm | services.lambda-esm.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| lambda-esm | lambda-esm | (compose が自動で付与) | `--network-alias` | `lambda-esm` | このネットワークの中で「lambda-esm」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| lambda-esm | lambda-esm | services.lambda-esm.environment | `--env` | `AWS_ACCESS_KEY_ID=local` | 環境変数 AWS_ACCESS_KEY_ID に「local」を設定します。 |
| lambda-esm | lambda-esm | services.lambda-esm.environment | `--env` | `AWS_REGION=ap-northeast-1` | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 |
| lambda-esm | lambda-esm | services.lambda-esm.environment | `--env` | `AWS_SECRET_ACCESS_KEY=local` | 環境変数 AWS_SECRET_ACCESS_KEY に「local」を設定します。 |
| lambda-esm | lambda-esm | services.lambda-esm.environment | `--env` | `BATCH_SIZE=10` | 環境変数 BATCH_SIZE に「10」を設定します。 |
| lambda-esm | lambda-esm | services.lambda-esm.environment | `--env` | `LAMBDA_INVOKE_URL=http://lambda:8080/2015-03-31/functions/function/invocations` | 環境変数 LAMBDA_INVOKE_URL に「http://lambda:8080/2015-03-31/functions/function/invocations」を設定します。 |
| lambda-esm | lambda-esm | services.lambda-esm.environment | `--env` | `QUEUE_NAME=app-async-queue` | 環境変数 QUEUE_NAME に「app-async-queue」を設定します。 |
| lambda-esm | lambda-esm | services.lambda-esm.environment | `--env` | `SQS_ENDPOINT=http://sqs:9324` | 環境変数 SQS_ENDPOINT に「http://sqs:9324」を設定します。 |
| lambda-esm | lambda-esm | services.lambda-esm.environment | `--env` | `WAIT_TIME_SECONDS=20` | 環境変数 WAIT_TIME_SECONDS に「20」を設定します。 |
| ecs-exec | ecs-exec | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| ecs-exec | ecs-exec | services.ecs-exec.container_name | `--name` | `ecs-exec` | コンテナに「ecs-exec」という名前を付けます。compose の container_name です。 |
| ecs-exec | ecs-exec | services.ecs-exec.networks.default | `--network` | `eap-adot-local_default` | ネットワーク「eap-adot-local_default」につなぎます。 |
| ecs-exec | ecs-exec | (compose が自動で付与) | `--network-alias` | `ecs-exec` | このネットワークの中で「ecs-exec」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| ecs-exec | ecs-exec | services.ecs-exec.volumes | `--volume` | `/var/run/docker.sock:/var/run/docker.sock` | ホストの /var/run/docker.sock をコンテナの /var/run/docker.sock に直接つなぎます (バインドマウント)。ホスト側に無ければ空のフォルダが作られます。 |
| ecs-exec | ecs-exec | services.ecs-exec.volumes | `--volume` | `/opt/Container_Compose_file/compose/ecs-exec/tasks.json:/etc/ecs-exec/tasks.json:ro` | ホストの /opt/Container_Compose_file/compose/ecs-exec/tasks.json をコンテナの /etc/ecs-exec/tasks.json に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| ecs-exec | ecs-exec | services.ecs-exec.volumes | `--volume` | `/opt/Container_Compose_file/compose/ecs-exec/ecs-exec.py:/opt/ecs-exec/ecs-exec.py:ro` | ホストの /opt/Container_Compose_file/compose/ecs-exec/ecs-exec.py をコンテナの /opt/ecs-exec/ecs-exec.py に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| ecs-exec | ecs-exec | services.ecs-exec.volumes | `--volume` | `/opt/Container_Compose_file/compose/ecs-exec/files:/work` | ホストの /opt/Container_Compose_file/compose/ecs-exec/files をコンテナの /work に直接つなぎます (バインドマウント)。ホスト側に無ければ空のフォルダが作られます。 |
| ecs-exec | ecs-exec | services.ecs-exec.volumes | `--volume` | `/opt/Container_Compose_file/compose/ecs-exec/sessions:/var/log/ecs-exec` | ホストの /opt/Container_Compose_file/compose/ecs-exec/sessions をコンテナの /var/log/ecs-exec に直接つなぎます (バインドマウント)。ホスト側に無ければ空のフォルダが作られます。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `AWS_DEFAULT_REGION=ap-northeast-1` | 環境変数 AWS_DEFAULT_REGION に「ap-northeast-1」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `AWS_REGION=ap-northeast-1` | 環境変数 AWS_REGION に「ap-northeast-1」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `ECS_EXEC_COMPOSE_PROJECT=eap-adot-local` | 環境変数 ECS_EXEC_COMPOSE_PROJECT に「eap-adot-local」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `ECS_EXEC_ENABLED=1` | 環境変数 ECS_EXEC_ENABLED に「1」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `ECS_EXEC_FILES_DIR=/work` | 環境変数 ECS_EXEC_FILES_DIR に「/work」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `ECS_EXEC_PUT_CHUNK_CHARS=16384` | 環境変数 ECS_EXEC_PUT_CHUNK_CHARS に「16384」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `ECS_EXEC_SESSION_LOG_DIR=/var/log/ecs-exec` | 環境変数 ECS_EXEC_SESSION_LOG_DIR に「/var/log/ecs-exec」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `ECS_EXEC_SIMULATE_PLUGIN_MISSING=0` | 環境変数 ECS_EXEC_SIMULATE_PLUGIN_MISSING に「0」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `ECS_EXEC_STATE_FILE=/var/lib/ecs-exec/state.json` | 環境変数 ECS_EXEC_STATE_FILE に「/var/lib/ecs-exec/state.json」を設定します。 |
| ecs-exec | ecs-exec | services.ecs-exec.environment | `--env` | `ECS_EXEC_TASKS_FILE=/etc/ecs-exec/tasks.json` | 環境変数 ECS_EXEC_TASKS_FILE に「/etc/ecs-exec/tasks.json」を設定します。 |

### 一般的な対応

| compose の設定 | docker コマンド | 補足 |
|---|---|---|
| `image` | docker run の最後のイメージ名 | docker pull でイメージを用意 |
| `build.*` | docker build --file/--target/--build-arg/--tag ... | イメージ名は image、無ければ <プロジェクト>-<サービス> |
| `container_name` | --name | 無ければ <プロジェクト>-<サービス>-<番号> |
| `command` | イメージ名の後ろの引数 | 文字列は compose と同じ規則で単語に分割 |
| `entrypoint` | --entrypoint (1 語目) + 残りは引数 |  |
| `environment / env_file` | --env / --env-file | ${VAR} は展開済み。compose と読み方が同じ env ファイルだけ --env-file |
| `ports` | --publish |  |
| `expose` | --expose |  |
| `volumes (短い書き方)` | --volume | ホスト側が無ければ作成 (compose と同じ) |
| `volumes (長い書き方・オプションあり)` | --mount |  |
| `tmpfs` | --tmpfs |  |
| `networks` | --network / --network-alias (複数なら --network name=...,alias=...) | サービス名を必ず別名に |
| `network_mode` | --network host / none / container:<名前> | service:<名前> は container:<コンテナ名> |
| `depends_on` | 起動の順番 + 待ち合わせのループ / docker wait | condition に合わせて待つ |
| `healthcheck` | --health-cmd/--health-interval/... または派生イメージ | CMD (exec 形式) は派生イメージ |
| `restart / deploy.restart_policy` | --restart |  |
| `deploy.resources.limits / reservations` | --cpus / --memory / --pids-limit / --memory-reservation / --gpus |  |
| `logging` | --log-driver / --log-opt |  |
| `labels / label_file` | --label |  |
| `user / group_add / working_dir` | --user / --group-add / --workdir |  |
| `cap_add / cap_drop / security_opt / privileged / read_only` | --cap-add / --cap-drop / --security-opt / --privileged / --read-only |  |
| `ulimits / sysctls` | --ulimit / --sysctl |  |
| `extra_hosts / dns / dns_search / dns_opt` | --add-host / --dns / --dns-search / --dns-option |  |
| `init / stop_signal / stop_grace_period` | --init / --stop-signal / --stop-timeout | stop_grace_period は秒に変換 |
| `secrets / configs (file)` | --mount type=bind,...,readonly | secrets は /run/secrets/<名前> |
| `secrets / configs (environment / content)` | docker create → docker cp → docker start |  |
| `pre_start` | docker create → docker run --rm --volumes-from → docker start |  |
| `post_start / pre_stop` | docker exec |  |
| `profiles` | (有効なサービスだけを変換) |  |
| `scale / deploy.replicas` | 番号違いのコンテナを複数作成 |  |

## 8. 用語集

| 用語 | 読み・英語 | 意味 | 小学生向けのたとえ |
|---|---|---|---|
| コンテナ | container | 囲いの中で動くプログラム (プロセス)。名前空間で周りが見えないようにし、cgroup で使える量を制限している。仮想マシンと違い OS を丸ごと起動しないので軽くて速い。 | マンションの中の 1 つのお部屋。住人 (プログラム) はその部屋の中だけで暮らす。 |
| イメージ | image | コンテナのもとになる、ファイル一式と設定 (起動するコマンド・環境変数など) をまとめたもの。読み取り専用で、何個でも同じコンテナを作れる。 | お部屋セット (家具付きの部屋の型)。冷凍お弁当のように、いつでも同じものを用意できる。 |
| レイヤー | layer | イメージを作る「差分の層」。Dockerfile の命令ごとにでき、同じ層は複数のイメージで共有される。 | 透明なシートを何枚も重ねて 1 枚の絵にするときの、それぞれのシート。 |
| Dockerfile | ドッカーファイル | イメージの作り方を書いたテキストファイル。FROM・RUN・COPY・CMD などの命令を上から実行する。 | 料理のレシピ。 |
| ビルドコンテキスト | build context | docker build に渡す材料フォルダ。COPY / ADD はこの中のファイルだけ使える。.dockerignore で除外できる。 | 料理の材料を入れた箱。 |
| BuildKit | ビルドキット | Docker 23.0 から標準になったビルドエンジン。並列実行・キャッシュ・秘密の受け渡しなどが得意。 | 腕のいい料理人。 |
| Docker Bake | ベイク | 複数のビルドをまとめて定義・実行する BuildKit の仕組み。compose v5 はビルドをこれに任せている。 | たくさんの料理をまとめて作る段取り表。 |
| レジストリ | registry | イメージを保管・配布するサーバー。Docker Hub、Amazon ECR、社内レジストリなど。 | 部品セットの倉庫。 |
| タグ / ダイジェスト | tag / digest | タグ (例: 8.4.7, latest) はイメージに付ける呼び名で、付け替えられる。ダイジェスト (sha256:...) は中身から計算した番号で、絶対に変わらない。 | タグは「今月のおすすめ」のような呼び名、ダイジェストは商品の製造番号。 |
| Docker Engine (dockerd) | ドッカーエンジン | コンテナ・イメージ・ネットワーク・ボリュームを管理する本体のサービス (デーモン)。systemctl で起動する。 | マンションの管理人さん。 |
| containerd | コンテナーディー | コンテナの一生 (作る・動かす・止める) とイメージの保存を担当する部品。Kubernetes でも使われる。 | 現場監督。 |
| runc | ランシー | OCI の仕様どおりにコンテナを作る小さなプログラム。カーネルに名前空間や cgroup を頼む。 | お部屋を作る大工さん。 |
| OCI | Open Container Initiative | コンテナのイメージ形式・実行方法・配布方法の標準を決める団体 (2015 年設立)。Docker・Podman・Kubernetes が同じイメージを使えるのはこのおかげ。 | 部品の大きさをそろえる「規格」を決める会議。 |
| Docker Engine API | API | docker コマンドと dockerd が話すための決まり (HTTP + JSON)。/var/run/docker.sock を通して送られる。 | リモコンと本体が話すための合言葉。 |
| UNIX ソケット | UNIX domain socket | 同じコンピューターの中のプログラムどうしが通信するための、ファイルの形をした出入口。 | 家の中だけで使う糸電話。 |
| compose ファイル | compose.yaml | 複数のコンテナの設定 (サービス・ネットワーク・ボリューム) を YAML で書いたファイル。 | 遠足のしおり。 |
| Docker Compose | ドッカーコンポーズ | compose ファイルを読んで、まとめて起動・停止する道具。今は docker compose というプラグイン (v5)。 | しおりを読んで、みんなに指示を出す先生。 |
| プロジェクト名 | project name | compose が作る物の名前の頭に付ける名前。name:、-p、またはフォルダ名から決まる。 | クラスの名前。名札に「1 組」と付けるようなもの。 |
| サービス | service | compose ファイルの services: の下の 1 つ 1 つ。同じ設定のコンテナのグループ (レプリカが 1 つ以上)。 | 「給食係」のような係の名前。 |
| ネットワーク (ブリッジ) | network / bridge | コンテナ用の仮想 LAN。bridge はホストの中にソフトウェアのスイッチを作る標準の種類。 | 建物の中だけの内線電話網。 |
| veth | virtual ethernet | 2 つで 1 組の仮想 LAN ケーブル。片方をコンテナ、片方をブリッジにつなぐ。 | 部屋と交換機をつなぐ電話線。 |
| 内蔵 DNS | embedded DNS | ユーザー定義ネットワークで、コンテナ名やサービス名を IP アドレスに変換する Docker の仕組み (127.0.0.11)。 | 名前を言えば電話をつないでくれる交換手さん。 |
| ネットワーク別名 | network alias | そのネットワークの中だけで使える、コンテナのもう 1 つの名前。compose はサービス名を必ず別名にする。 | あだ名。 |
| ポート公開 | publish / ports | ホストのポートに来た通信を、コンテナのポートへ転送すること。 | 正面玄関の窓口からお部屋への道案内。 |
| NAT / DNAT / MASQUERADE | ナット | 通信の宛先や送り主のアドレスを書き換える仕組み。Docker は外への通信を MASQUERADE、ポート公開を DNAT で実現する。 | 郵便物の宛名を、建物の住所から部屋番号へ書き換える係。 |
| iptables / nftables | アイピーテーブルズ | Linux のファイアウォール・アドレス変換の設定の仕組み。RHEL 9 では iptables コマンドも内部で nftables を使う。 | 建物の出入口の警備員さんのルールブック。 |
| ボリューム | volume | Docker が管理するデータの保存場所。コンテナを消しても残る。名前付き (named) と、名前の無い匿名 (anonymous) がある。 | 部屋の外にある貸しロッカー。 |
| バインドマウント | bind mount | ホストのフォルダやファイルを、そのままコンテナの中の場所に見せる仕組み。 | 家の引き出しを、部屋の中から直接開けられるようにする窓。 |
| tmpfs | テンプエフエス | メモリの上に作る一時的なファイル置き場。速いが、止めると消える。 | ホワイトボード。 |
| overlayfs | オーバーレイ | 読み取り専用の層を重ね、その上に書き込み用の層を足して 1 つのフォルダに見せる Linux の仕組み。 | 透明シートを重ねて、一番上のシートにだけ書き込むやり方。 |
| 名前空間 | namespace | プロセスから見える範囲 (プロセス・ネットワーク・ファイル・ホスト名など) を分ける Linux の仕組み。 | 部屋の壁。 |
| cgroup (v2) | シーグループ | CPU・メモリ・プロセス数などの使用量を数え、上限を決める Linux の仕組み。RHEL 9 は v2 が標準。 | 電気・水道のメーターとブレーカー。 |
| capabilities | ケーパビリティ | root の強い権限を 40 個ほどに細かく分けたもの。Docker は標準で 14 個だけ許可する。 | マンションの合鍵を種類ごとに分けたもの。 |
| seccomp | セックコンプ | プロセスが使ってよいシステムコール (カーネルへのお願い) を制限する仕組み。 | 「この呪文は使ってはいけません」リスト。 |
| SELinux | エスイーリナックス | RHEL のアクセス制御の仕組み。ファイルやプロセスにラベル (名札) を付けて、許可された組み合わせだけを通す。 | 名札の色で、入っていい部屋を決めるルール。 |
| PID 1 / init | ピッドワン | コンテナの中で最初に動くプロセス。シグナルの受け取りやゾンビプロセスの後片付けの責任がある。--init で小さなお世話係 (tini) を置ける。 | 部屋のリーダー。 |
| シグナル | signal (SIGTERM / SIGKILL) | プロセスへの合図。SIGTERM は「終わってください」、SIGKILL は「強制終了」。 | 「そろそろ帰る時間ですよ」と「もう電気を消します」。 |
| 終了コード | exit code | プログラムが終わるときに返す番号。0 は成功、それ以外は失敗。137 は SIGKILL (メモリ不足など) で止められた印。 | テストの結果の点数のような返事。0 点が「うまくいった」の合図。 |
| ヘルスチェック | healthcheck | コンテナの中で定期的にテストのコマンドを実行し、動いているだけでなく「ちゃんと応答できるか」を調べる仕組み。starting → healthy / unhealthy。 | 「元気？」と声をかける見回り。 |
| depends_on | ディペンズオン | サービスの起動順番と、待ち合わせの条件 (started / healthy / completed_successfully) を決める compose の設定。 | 「準備ができたら次の人が出発」というルール。 |
| 環境変数 | environment variable | プログラムに渡す「名前=値」の設定。データベースの接続先などを、イメージを作り直さずに変えられる。 | お部屋に置く設定メモ。 |
| .env と変数展開 | dotenv / interpolation | compose ファイルの ${VAR} を、.env ファイルや OS の環境変数の値で置き換える仕組み。 | しおりの「○○」の空欄に、名簿の名前を書き込むこと。 |
| ラベル | label | コンテナなどに付ける目印 (キー=値)。動作には影響しない。 | シール。 |
| ログドライバー | logging driver | コンテナの画面出力をどこへ保存するかを決める部品 (json-file、journald など)。 | 日記帳の種類。 |
| restart ポリシー | restart policy | コンテナが止まったときに自動で起動し直すかどうかのルール。 | 転んだら起こしてあげる約束。 |
| configs / secrets | コンフィグ / シークレット | 設定ファイル・秘密情報をコンテナに渡す compose の仕組み。ファイルからはバインドマウント、中身の直書きからはコピーで渡される。 | 配られる説明書と、封筒に入った秘密の手紙。 |
| init コンテナ (pre_start) | イニットコンテナ | 本番のコンテナを起動する前に、準備作業だけをする使い捨てのコンテナ。compose 5.3 から。 | 開店前に来る準備係さん。 |
| ライフサイクルフック | post_start / pre_stop | 起動直後・停止直前に、コンテナの中で実行するコマンド。compose 2.30 から。 | 開店直後・閉店直前のお決まりの作業。 |
| profiles | プロファイル | 指定したときだけ起動するサービスのグループ (デバッグ用・試験用など)。 | 「雨の日だけ」の特別メニュー。 |
| ヒアドキュメント | here document | <<'終わりの印' から 終わりの印 までの複数行を、コマンドへの入力として渡す bash の書き方。'...' で囲むと $ などを展開しない。 | 長い手紙を、封筒ごと手渡しする方法。 |
| 履歴展開 | history expansion | bash で ! を使って過去のコマンドを呼び出す機能。set +H で止められる。 | 「さっきのと同じ！」と言うと前の注文を繰り返してくれる機能。 |
| distroless | ディストロレス | アプリを動かすのに必要な最低限のファイルだけを入れ、シェル (/bin/sh) すら入れないイメージ。攻撃されにくい。 | 必要な道具しか置いていない、すっきりした部屋。 |
| RHEL | レル | Red Hat Enterprise Linux。企業向けの Linux。9.8 は 2026 年 5 月に公開された 9 系の更新版。 | 会社で使う、長く安心して使える建物。 |
| Podman | ポッドマン | Red Hat が中心に開発する、docker と互換のあるコンテナの道具。デーモンを持たない。RHEL 8 以降の標準。 | 別の会社の管理人さん。やり方は似ている。 |
| docker-ce | Docker Community Edition | Docker 社が配布する無料の Docker Engine のパッケージ名。 | 管理人さんの派遣元。 |

## 9. 歴史年表

| 時期 | 出来事 | 何が変わったか |
|---|---|---|
| 1979 年 | Unix V7 に chroot が登場 | プログラムに見せるフォルダの範囲を制限できるようになった (コンテナのいちばん古いご先祖さま)。 |
| 1982 年 | BSD に chroot が入る | Unix 系 OS に広まる。 |
| 2000 年 3 月 | FreeBSD 4.0 に jail が登場 | ファイルだけでなく、プロセスやネットワークも分けられる「囲い」ができた。 |
| 2001 年 | Linux-VServer | Linux でも 1 台を区切って使う仕組みが作られる。 |
| 2002 年 | Linux 2.4.19 に mount 名前空間 | Linux の名前空間のはじまり。 |
| 2004〜2005 年 | Solaris Zones (Solaris 10) | 商用 OS で本格的なコンテナが使われ始める。 |
| 2005 年 | OpenVZ | レンタルサーバーなどで Linux のコンテナが普及。 |
| 2006 年 | Google が process containers を開発 | CPU やメモリの使用量を制限する仕組み。のちの cgroups。 |
| 2008 年 1 月 | Linux 2.6.24 に cgroups が入る | 資源の制限が Linux の標準機能に。 |
| 2008 年 | LXC (Linux Containers) 登場 | 名前空間と cgroups を組み合わせた、Linux のコンテナの道具。 |
| 2013 年 2 月 | Linux 3.8 で user 名前空間が完成 | 必要な名前空間がひととおりそろう。 |
| 2013 年 3 月 | Docker 公開 (PyCon での発表) | dotCloud 社の Solomon Hykes さんが発表。イメージという配りやすい形で大人気に。 |
| 2013 年 12 月 | Fig 公開 (Orchard 社) | 複数コンテナを 1 つのファイルで定義する道具。compose のご先祖さま。 |
| 2014 年 3 月 | Docker 0.9 で libcontainer | LXC に頼らず、Go で直接カーネルを操作するように。 |
| 2014 年 6 月 | Docker 1.0 / Docker Hub 公開 | 本番で使える版になり、イメージの共有場所ができる。 |
| 2014 年 7 月 | Docker 社が Orchard (Fig) を買収 | Fig が Docker Compose になっていく。 |
| 2014 年 10 月 | Docker 1.3: docker exec / docker create | 動いているコンテナの中で操作できるように。 |
| 2015 年 2 月 | Docker Compose 1.1 (Fig から改名) | docker-compose コマンドの時代 (Python 製の v1)。 |
| 2015 年 4 月 | Docker 1.6 / Registry API v2 | 中身のハッシュでレイヤーを管理する、今のイメージ配布の方式に。 |
| 2015 年 6 月 | OCI 設立、runc 寄贈 | コンテナの標準化が始まる。 |
| 2015 年 8 月 | Docker 1.8: docker cp でコンテナへコピー | ホスト → コンテナのファイルコピーが可能に。 |
| 2015 年 11 月 | Docker 1.9: docker network / docker volume | ユーザー定義ネットワークと名前付きボリュームが登場。--link の時代が終わる。 |
| 2016 年 2 月 | Docker 1.10: 内蔵 DNS / Compose ファイル形式 v2 | 名前で呼び合うのが当たり前に。compose に networks: と volumes:。 |
| 2016 年 3 月 | Linux 4.5 で cgroup v2 | 新しい資源管理の仕組み。 |
| 2016 年 7 月 | Docker 1.12: HEALTHCHECK / Swarm mode | コンテナの健康状態を調べられるように。 |
| 2016 年 11 月 | Compose ファイル形式 v2.1: depends_on の condition | service_healthy を待てるように。 |
| 2017 年 1 月 | Docker 1.13: --init / Compose ファイル形式 v3 | init (tini) の組み込み。v3 は Swarm 向けで condition が一度消える。 |
| 2017 年 3 月 | containerd を CNCF に寄贈 / Docker CE・EE | バージョンが 17.03 のような「年.月」に。 |
| 2017 年 5〜6 月 | Docker 17.05 マルチステージビルド / 17.06 --mount | 小さなイメージ作りと、読みやすいマウントの書き方。 |
| 2017 年 7 月 | OCI Image Specification 1.0 | イメージの形式が業界標準に。 |
| 2018 年 11 月 | Docker 18.09: BuildKit を試せるように | 速く安全な新しいビルドの始まり。 |
| 2019 年 5 月 | RHEL 8 公開 (Podman が標準) | Red Hat は docker の代わりに Podman / Buildah / Skopeo を採用。 |
| 2019 年 7 月 | Docker 19.03: --gpus / buildx | GPU を簡単に使えるように。 |
| 2020 年 4 月 | Compose Specification 公開 | compose ファイルの書き方がオープンな仕様に。v2/v3 の区別がなくなる方向へ。 |
| 2020 年 11 月 | Docker Hub の回数制限開始 | ミラーや別のレジストリの利用が広がる。 |
| 2020 年 12 月 | Docker 20.10: cgroup v2 対応・rootless 正式版 | RHEL 9 世代の Linux で動く準備が整う。 |
| 2021 年 4 月 | Compose 1.29: service_completed_successfully | 「準備用のサービスが成功してから起動」ができるように。 |
| 2021 年 5〜6 月 | OCI Distribution Spec 1.0 / runc 1.0 | 配布方法と実行の部品が安定版に。 |
| 2022 年 4 月 | Compose v2 (Go 製・docker compose) 正式版 | docker-compose から docker compose へ。 |
| 2022 年 5 月 | RHEL 9.0 公開 | cgroup v2 が標準に。 |
| 2023 年 2 月 | Docker 23.0: BuildKit が標準 | docker build = buildx build に。 |
| 2023 年 7 月 | Compose v1 のサポート終了 | Python 製の docker-compose の更新が終わる。 |
| 2024 年 1 月 | Docker 25.0: 複数ネットワーク同時接続・start-interval | 1 回の docker run で複数のネットワークへ。 |
| 2024 年 3 月 | Docker 26.0: volume-subpath | ボリュームの一部だけをつなげるように。 |
| 2024 年 10 月 | Compose 2.30: post_start / pre_stop フック | 起動直後・停止直前の作業を書けるように。 |
| 2025 年 2 月 | Docker 28.0: gw-priority など | 複数ネットワークの出口を選べるように。 |
| 2025 年 5 月 | RHEL 10 公開 | RHEL の新しい世代。 |
| 2025 年 11 月 | Docker Engine 29.0 | containerd image store が新規の標準・nftables 試験対応・API 1.44 未満を廃止・cgroup v1 非推奨。 |
| 2025 年 12 月 | Docker Compose v5.0 | v3 / v4 を飛ばして v5 に。SDK として使えるように・ビルドは Bake に一本化。 |
| 2026 年 5 月 | RHEL 9.8 / 10.2 公開 | この資料が前提にしている RHEL のバージョン。 |
| 2026 年 7 月 | Compose 5.3: pre_start (init コンテナ) | 本番の前の準備用コンテナを正式に書けるように。 |
| 2026 年 8〜10 月 | Compose 5.4〜5.6 / Docker 29.8〜29.9 | 状態の突き合わせ (reconciliation) の改良など。2026 年 10 月時点の最新は Compose 5.6.0 (10/2)、Docker Engine 29.9.0 (10/8)。 |

## 10. 注意点・制限事項

### このプロジェクトの変換メモ

- services.ecs-exec は Docker の API (docker.sock) を使います。中のプログラムが compose のラベル (com.docker.compose.project / service) でコンテナを探す作りの場合は、--compose-labels を付けて変換してください (compose と同じラベルが付きます)。
- services.cwagent-ssm は profiles (ssm-config) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile ssm-config を付けて変換し直してください。
- services.tls-verifier は profiles (verify) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile verify を付けて変換し直してください。
- services.jmeter は profiles (loadtest) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile loadtest を付けて変換し直してください。
- STEP 30: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 33: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 36: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 37: compose で entrypoint を指定すると、イメージの CMD は使われません (docker run --entrypoint も同じ)。
- STEP 40: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 42: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 44: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 47: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 49: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 53: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

### docker コマンドに直すときの一般的な注意

- **ヘルスチェックの exec 形式**: docker run の --health-cmd はシェル形式 (/bin/sh -c) しか書けないため、compose の test: ["CMD", ...] は HEALTHCHECK を焼き込んだ派生イメージ (<プロジェクト>-<サービス>:with-healthcheck) で再現しています。動作は同じですが、docker ps に表示されるイメージ名が変わります。--healthcheck-exec shell を指定すると派生イメージを作らず --health-cmd で代用します。
- **compose のラベル**: compose はコンテナに com.docker.compose.* のラベルを付けて管理しています。この手順では既定で付けないため、docker compose ps / down の対象にはなりません (片付けは down 用の txt で行います)。--compose-labels を付けると同じラベルを付けますが、compose の config-hash は付けられないため、その後に compose up すると作り直しになります。
- **起動の並列・順番**: compose は依存関係の無いサービスを同時に起動しますが、この手順は 1 つずつ順番に起動します。できあがる状態は同じです。
- **待ち合わせで失敗したとき**: compose は依存先が unhealthy になったり失敗したりすると、そこで起動をやめます。この手順の待ち合わせは「NG」と表示して待つのをやめますが、貼り付けた残りのコマンドは続いてしまいます。NG が出たら、その先へ進まずに原因を確認してください。
- **depends_on の restart: true**: compose の restart: true (依存先を再起動したら、こちらも再起動する) は compose の操作の中だけの機能のため、docker コマンドでは再現していません。
- **pull_policy の daily / weekly / every_N**: 「一定時間たったら取り直す」機能は docker に無いため、「無いときだけ取得」で代用しています。
- **変数の展開**: ${VAR} や .env の値は、変換したときの値で展開済みです。.env を変えたときは、変換し直してください。
- **2 回目の実行**: compose up は既にあるコンテナとの差分を見て作り直しますが、docker コマンドは同じ名前があるとエラーになります。2 回目は後片付けをしてから実行してください。
- **再現できないもの**: provider (外部の仕組みに任せるサービス)・models (AI モデル)・develop / watch (開発用の自動同期)・Swarm 専用の deploy 設定 (placement / update_config / mode: global など) は、docker コマンドだけでは再現できない (または compose も単体では使わない) ため、対象外としています。

### RHEL 9.8 で気をつけること

- **cgroup v2**: RHEL 9 系は cgroup v2 が標準です。Docker 29 も cgroup v2 が推奨です (v1 は非推奨)。--memory-swappiness など v1 専用の設定は無視されます。
- **SELinux**: docker-ce の標準設定ではコンテナに SELinux ラベルが付かず、バインドマウントはそのまま使えます。/etc/docker/daemon.json で "selinux-enabled": true にしている場合は、ホストのフォルダをつなぐ volumes に :z (共有) や :Z (専用) が必要になります (compose でも同じです)。
- **firewalld**: Docker は firewalld に docker という zone を作り、自分のルールを管理します。firewall-cmd --reload の後にコンテナの通信がおかしいときは sudo systemctl restart docker を実行します。
- **ディスク容量**: イメージ・コンテナ・ボリュームは /var/lib/docker (containerd image store の場合は /var/lib/containerd も) に保存されます。df -h と docker system df で容量を確認してください。
- **文字コード**: この手順の txt ファイルは UTF-8 (BOM なし)・LF 改行です。日本語のコメントが文字化けする場合は、ターミナルの文字コードを UTF-8 にしてください (LANG=ja_JP.UTF-8 など)。
- **時刻・タイムゾーン**: コンテナの時刻はホストと同じ時計を使いますが、タイムゾーンはイメージの設定 (多くは UTC) です。TZ 環境変数や /etc/localtime のマウントで合わせます。
- **Podman との違い**: RHEL 標準の Podman にも docker 互換のコマンドがありますが、デーモンを持たない・rootless が標準などの違いがあります。この手順は Docker Engine (docker-ce) を前提にしています。

## 11. 後片付けの手順

`docker-commands-down.txt` に同じ内容があります。起動と逆の順番で止めて削除します (compose down と同じ)。

### 1. コンテナ「ecs-exec」を止める

コンテナ「ecs-exec」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop ecs-exec
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 2. コンテナ「lambda-esm」を止める

コンテナ「lambda-esm」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop lambda-esm
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 3. コンテナ「lambda」を止める

コンテナ「lambda」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop lambda
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 4. コンテナ「alb」を止める

コンテナ「alb」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop alb
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 5. コンテナ「alb-lambda-adapter」を止める

コンテナ「alb-lambda-adapter」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop alb-lambda-adapter
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 6. コンテナ「maintenance-lambda」を止める

コンテナ「maintenance-lambda」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop maintenance-lambda
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 7. コンテナ「secure-api」を止める

コンテナ「secure-api」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop secure-api
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 8. コンテナ「alb-front」を止める

コンテナ「alb-front」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop alb-front
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 9. コンテナ「alb-healthcheck」を止める

コンテナ「alb-healthcheck」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop alb-healthcheck
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 10. コンテナ「frontend」を止める

コンテナ「frontend」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop frontend
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 11. コンテナ「backend」を止める

コンテナ「backend」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop backend
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 12. コンテナ「mysql」を止める

コンテナ「mysql」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop mysql
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 13. コンテナ「pki-init」を止める

コンテナ「pki-init」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop pki-init
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 14. コンテナ「sqs」を止める

コンテナ「sqs」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sqs
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 15. コンテナ「cwagent」を止める

コンテナ「cwagent」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop cwagent
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 16. コンテナ「cloudwatch-logs-mock」を止める

コンテナ「cloudwatch-logs-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop cloudwatch-logs-mock
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 17. コンテナ「batch-mock」を止める

コンテナ「batch-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop batch-mock
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 18. コンテナ「efs-mock」を止める

コンテナ「efs-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop efs-mock
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 19. コンテナ「adot-collector」を止める

コンテナ「adot-collector」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop adot-collector
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 20. コンテナ「ecs-metadata-mock」を止める

コンテナ「ecs-metadata-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop ecs-metadata-mock
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 21. コンテナ「svf-mock」を止める

コンテナ「svf-mock」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop svf-mock
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 22. コンテナ「valkey」を止める

コンテナ「valkey」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop valkey
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 23. コンテナ「jaeger」を止める

コンテナ「jaeger」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop jaeger
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

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

- しくみ: コンテナの設定と書き込み用の層を削除します。名前付きボリュームは消えません。匿名ボリュームも、-v を付けない限り残ります (compose down と同じ動き)。
- 小学生向け: 使い終わったおもちゃを分解して片付けるコマンドです。ロッカーの中身は残ります。

### 25. ネットワークを削除する

このプロジェクトで作ったネットワークを削除します (compose down と同じ)。

```bash
docker network rm eap-adot-local_default
```

- しくみ: ブリッジとファイアウォールのルール、IP アドレスの範囲の予約が片付けられます。
- 小学生向け: 使い終わった道路を片付けるコマンドです。

### 26. ボリュームを削除する (データが消えます)

名前付きボリュームを削除します (compose down -v と同じ)。データが消えるため、必要なときだけ先頭の # を外して実行してください。

```bash
# docker volume rm \
#   eap-adot-local_pki \
#   eap-adot-local_efs-data \
#   eap-adot-local_efs-logs \
#   eap-adot-local_mysql-data
```

- しくみ: ボリュームの実体 (/var/lib/docker/volumes/<名前>) を削除します。データベースのデータなどが完全に消えるので注意してください。
- 小学生向け: ロッカーを中身ごと捨てるコマンドです。大事なものが入っていないか、よく確かめてから使います。

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

- しくみ: イメージの名前 (タグ) を外し、どこからも使われなくなったレイヤーを削除してディスクを空けます。
- 小学生向け: もう使わないおもちゃのもとを捨てるコマンドです。

