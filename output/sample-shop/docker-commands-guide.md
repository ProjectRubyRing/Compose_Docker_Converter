# sample-shop ― docker コマンド実行手順の詳しい解説

> compose2docker 1.0.0 で自動生成 ／ 生成日時: 2026-10-10 15:06:28 ／ 元の compose: `/opt/sample-shop/compose.yaml`
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
| プロジェクト名 | `sample-shop` |
| サービス | `db`、`cache`、`migrate`、`app`、`web` |
| コンテナ | `sample-shop-db-1`、`sample-shop-cache-1`、`sample-shop-migrate-1`、`sample-shop-app-1`、`sample-shop-web-1` |
| 手順の数 | 起動 27 STEP ／ 片付け 9 STEP |

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
| 2 | ネットワーク | コンテナどうしが名前で話せる仮想ネットワークを作ります。コンテナより先に必要です。 | [2](#step-2)、[3](#step-3) |
| 3 | ボリューム | データを残しておく保存場所を作ります。コンテナより先に必要です。 | [4](#step-4)、[5](#step-5)、[6](#step-6) |
| 4 | イメージ取得 | 手元に無いイメージだけをダウンロードします (compose の pull_policy: missing と同じ)。 | [7](#step-7)、[8](#step-8)、[9](#step-9)、[10](#step-10) |
| 5 | イメージ作成 | build: があるサービスのイメージを Dockerfile から作ります。 | [11](#step-11) |
| 6 | ヘルスチェック入りイメージ | exec 形式のヘルスチェックを compose と同じにするための派生イメージを作ります (必要なときだけ)。 | [12](#step-12)、[13](#step-13) |
| 7 | 起動 | depends_on の順番どおりにコンテナを起動します。healthy や正常終了を待つ設定があれば、その待ち合わせもします。 | [14](#step-14)、[15](#step-15)、[16](#step-16)、[17](#step-17)、[18](#step-18)、[19](#step-19)、[20](#step-20)、[21](#step-21)、[22](#step-22)、[23](#step-23)、[24](#step-24)、[25](#step-25)、[26](#step-26) |
| 8 | 確認 | 全部のコンテナの状態を一覧で確認します。 | [27](#step-27) |

サービスの起動順 (depends_on などの依存関係を守った順番): `db` → `cache` → `migrate` → `app` → `web`

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
cd /opt/sample-shop
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

### STEP 2: ネットワーク「sample-shop_frontend」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ネットワーク作成 |
| 使うコマンド | docker network create ― コンテナ専用の仮想ネットワークを作る |
| ひとことで | コンテナどうしが名前で話せる、専用の仮想ネットワーク (ユーザー定義ブリッジ) を作ります。 |
| compose の対応箇所 | `networks.frontend` |

**実行するコマンド**

```bash
docker network create sample-shop_frontend
```

**実行のしかた**

かたまりをコピーして貼り付け、Enter を押します。成功すると、作られたネットワークの ID (64 文字の英数字) が 1 行表示されます。  
・「network with name ... already exists」と出たら、同じ名前のネットワークが既にあります。前回の分が残っている場合は、後片付けの手順 (docker network rm) を実行してからやり直してください。  
・「Pool overlaps with other one on this address space」と出たら、指定した IP アドレスの範囲 (subnet) が既存のネットワークと重なっています。

**このコマンドがすること**

仮想ネットワーク「sample-shop_frontend」を作ります。つながるコンテナ: app、web。同じネットワークのコンテナどうしは、サービス名で呼び合えます。

- ドライバーを指定していないときは bridge (ホストの中だけの仮想スイッチ) になります。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ネットワーク名)` | `sample-shop_frontend` | networks.frontend | compose の命名規則「<プロジェクト名>_<ネットワークのキー>」で付けた名前です。 | 作るネットワークの名前です。<br>（やさしく）道路の名前です。 |

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

**確認のしかた**: `docker network ls --filter name=sample-shop_frontend` ／ `docker network inspect sample-shop_frontend`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
networks:
  frontend:
    ipam: {}
    name: sample-shop_frontend
```

</details>

<a id="step-3"></a>

### STEP 3: ネットワーク「sample-shop_backend」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ネットワーク作成 |
| 使うコマンド | docker network create ― コンテナ専用の仮想ネットワークを作る |
| ひとことで | コンテナどうしが名前で話せる、専用の仮想ネットワーク (ユーザー定義ブリッジ) を作ります。 |
| compose の対応箇所 | `networks.backend` |

**実行するコマンド**

```bash
docker network create --internal sample-shop_backend
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 2](#step-2) と同じです)。

**このコマンドがすること**

仮想ネットワーク「sample-shop_backend」を作ります。つながるコンテナ: db、cache、migrate、app。同じネットワークのコンテナどうしは、サービス名で呼び合えます。

- ドライバーを指定していないときは bridge (ホストの中だけの仮想スイッチ) になります。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--internal` |  | networks.backend.internal | 外 (インターネットやホストの外) へは出られない、内部専用のネットワークにします。 | 外への出口を作らず、ネットワークの中だけで通信できるようにします。データベース専用の裏ネットワークなどに使います。<br>（やさしく）外につながっていない、敷地の中だけの道路にします。 |
| `(ネットワーク名)` | `sample-shop_backend` | networks.backend | compose の命名規則「<プロジェクト名>_<ネットワークのキー>」で付けた名前です。 | 作るネットワークの名前です。<br>（やさしく）道路の名前です。 |

**しくみ・歴史**: STEP 2 と同じ `docker network create` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-network-create) を参照してください。

**小学生向けのまとめ**: コンテナたちのための「専用の道路と電話帳」を作るコマンドです。同じ道路につながったコンテナは、「db さーん」と名前を呼ぶだけで相手のところへ手紙 (データ) を届けられます。

**確認のしかた**: `docker network ls --filter name=sample-shop_backend` ／ `docker network inspect sample-shop_backend`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
networks:
  backend:
    internal: true
    ipam: {}
    name: sample-shop_backend
```

</details>

<a id="step-4"></a>

### STEP 4: ボリューム「sample-shop_db-data」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ボリューム作成 |
| 使うコマンド | docker volume create ― データを残しておくボリュームを作る |
| ひとことで | コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。 |
| compose の対応箇所 | `volumes.db-data` |

**実行するコマンド**

```bash
docker volume create sample-shop_db-data
```

**実行のしかた**

貼り付けて Enter。成功するとボリューム名が 1 行表示されます。同じ名前のボリュームが既にある場合もエラーにはならず、そのまま名前が表示されます (中身はそのまま残っています)。

**このコマンドがすること**

データを保存しておく名前付きボリューム「sample-shop_db-data」を作ります。使うサービス: db。

- コンテナを削除してもボリュームの中身は残ります。消すときは docker volume rm で明示的に消します (compose の down -v と同じ)。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ボリューム名)` | `sample-shop_db-data` | volumes.db-data | compose の命名規則「<プロジェクト名>_<ボリュームのキー>」で付けた名前です。 | 作るボリュームの名前です。<br>（やさしく）ロッカーの名前です。 |

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

**確認のしかた**: `docker volume ls --filter name=sample-shop_db-data` ／ `docker volume inspect sample-shop_db-data`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
volumes:
  db-data:
    name: sample-shop_db-data
```

</details>

<a id="step-5"></a>

### STEP 5: ボリューム「sample-shop_cache-data」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ボリューム作成 |
| 使うコマンド | docker volume create ― データを残しておくボリュームを作る |
| ひとことで | コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。 |
| compose の対応箇所 | `volumes.cache-data` |

**実行するコマンド**

```bash
docker volume create sample-shop_cache-data
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 4](#step-4) と同じです)。

**このコマンドがすること**

データを保存しておく名前付きボリューム「sample-shop_cache-data」を作ります。使うサービス: cache。

- コンテナを削除してもボリュームの中身は残ります。消すときは docker volume rm で明示的に消します (compose の down -v と同じ)。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ボリューム名)` | `sample-shop_cache-data` | volumes.cache-data | compose の命名規則「<プロジェクト名>_<ボリュームのキー>」で付けた名前です。 | 作るボリュームの名前です。<br>（やさしく）ロッカーの名前です。 |

**しくみ・歴史**: STEP 4 と同じ `docker volume create` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-volume-create) を参照してください。

**小学生向けのまとめ**: コンテナが使う「なくならないロッカー」を用意するコマンドです。コンテナを片付けても、ロッカーの中のデータは残ります。

**確認のしかた**: `docker volume ls --filter name=sample-shop_cache-data` ／ `docker volume inspect sample-shop_cache-data`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
volumes:
  cache-data:
    name: sample-shop_cache-data
```

</details>

<a id="step-6"></a>

### STEP 6: ボリューム「sample-shop_app-cache」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ボリューム作成 |
| 使うコマンド | docker volume create ― データを残しておくボリュームを作る |
| ひとことで | コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。 |
| compose の対応箇所 | `volumes.app-cache` |

**実行するコマンド**

```bash
docker volume create sample-shop_app-cache
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 4](#step-4) と同じです)。

**このコマンドがすること**

データを保存しておく名前付きボリューム「sample-shop_app-cache」を作ります。使うサービス: app。

- コンテナを削除してもボリュームの中身は残ります。消すときは docker volume rm で明示的に消します (compose の down -v と同じ)。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(ボリューム名)` | `sample-shop_app-cache` | volumes.app-cache | compose の命名規則「<プロジェクト名>_<ボリュームのキー>」で付けた名前です。 | 作るボリュームの名前です。<br>（やさしく）ロッカーの名前です。 |

**しくみ・歴史**: STEP 4 と同じ `docker volume create` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-volume-create) を参照してください。

**小学生向けのまとめ**: コンテナが使う「なくならないロッカー」を用意するコマンドです。コンテナを片付けても、ロッカーの中のデータは残ります。

**確認のしかた**: `docker volume ls --filter name=sample-shop_app-cache` ／ `docker volume inspect sample-shop_app-cache`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
volumes:
  app-cache:
    name: sample-shop_app-cache
```

</details>

<a id="step-7"></a>

### STEP 7: イメージ「postgres:16-alpine」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.db.image` |

**実行するコマンド**

```bash
docker image inspect postgres:16-alpine > /dev/null 2>&1 || docker pull postgres:16-alpine
```

**実行のしかた**

貼り付けて Enter。手元に既にある場合は何も表示されずに終わります (正常です)。無い場合はダウンロードの進み具合が表示され、最後に「Status: Downloaded newer image for ...」と出れば成功です。  
・「pull access denied」「unauthorized」は、非公開のイメージなので docker login が必要か、名前の間違いです。  
・「toomanyrequests」は Docker Hub のダウンロード回数制限です。時間をおくか、docker login してから実行してください。  
・「dial tcp ... i/o timeout」はインターネットに出られていません (プロキシの設定を確認)。

**このコマンドがすること**

イメージ「postgres:16-alpine」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: db、migrate

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `postgres:16-alpine` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `postgres:16-alpine` | services.db.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

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

**確認のしかた**: `docker image ls postgres:16-alpine`

<a id="step-8"></a>

### STEP 8: イメージ「valkey/valkey:8-alpine」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.cache.image` |

**実行するコマンド**

```bash
docker image inspect valkey/valkey:8-alpine > /dev/null 2>&1 || docker pull valkey/valkey:8-alpine
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「valkey/valkey:8-alpine」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: cache

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `valkey/valkey:8-alpine` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `valkey/valkey:8-alpine` | services.cache.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls valkey/valkey:8-alpine`

<a id="step-9"></a>

### STEP 9: イメージ「nginx:1.27-alpine」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.web.image` |

**実行するコマンド**

```bash
docker image inspect nginx:1.27-alpine > /dev/null 2>&1 || docker pull nginx:1.27-alpine
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「nginx:1.27-alpine」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- このイメージを使うサービス: web

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `nginx:1.27-alpine` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `nginx:1.27-alpine` | services.web.image | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls nginx:1.27-alpine`

<a id="step-10"></a>

### STEP 10: イメージ「busybox:1.36」を用意する

| 項目 | 内容 |
|---|---|
| 区分 | イメージ取得 |
| 使うコマンド | docker pull ― イメージをダウンロードする |
| ひとことで | イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。 |
| compose の対応箇所 | `services.app.pre_start` |

**実行するコマンド**

```bash
docker image inspect busybox:1.36 > /dev/null 2>&1 || docker pull busybox:1.36
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 7](#step-7) と同じです)。

**このコマンドがすること**

イメージ「busybox:1.36」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。

- docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。
- pre_start (起動前に動かす初期化用コンテナ) で使うイメージです。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(イメージ名)` | `busybox:1.36` |  | 手元 (ローカル) にこのイメージがあるかを調べます。 |  |
| `(イメージ名)` | `busybox:1.36` | services.app.pre_start | 取ってくるイメージの名前 (リポジトリ:タグ) です。 | 取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。<br>（やさしく）取り寄せる部品セットの名前です。 |

**しくみ・歴史**: STEP 7 と同じ `docker pull` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-pull) を参照してください。

**小学生向けのまとめ**: おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。

**確認のしかた**: `docker image ls busybox:1.36`

<a id="step-11"></a>

### STEP 11: サービス「app」のイメージ「sample-shop/app:1.0.0」をビルドする

| 項目 | 内容 |
|---|---|
| 区分 | イメージ作成 |
| 使うコマンド | docker build ― Dockerfile からイメージを作る |
| ひとことで | 設計図 (Dockerfile) と材料フォルダ (ビルドコンテキスト) から、イメージを作ります。 |
| compose の対応箇所 | `services.app.build` |

**実行するコマンド**

```bash
docker build \
  --target runtime \
  --build-arg APP_VERSION=1.0.0 \
  --build-arg PYTHON_VERSION=3.12 \
  --label com.example.built-by=compose2docker-sample \
  --tag sample-shop/app:1.0.0 \
  /opt/sample-shop/app
```

**実行のしかた**

貼り付けて Enter。[+] Building ... と進み具合が表示され、最後に「naming to docker.io/library/<名前>」や「writing image sha256:...」が出て、エラー無くプロンプトに戻れば成功です。2 回目以降は、変わっていない部分に CACHED と表示され、早く終わります。  
・「failed to solve」と出たら、Dockerfile のどの行で失敗したかが表示されるので、その行のコマンドや COPY するファイルの有無を確認します。  
・ビルドコンテキスト (最後に書いたフォルダ) は compose ファイルの build.context と同じ場所です。RHEL 上に同じフォルダ構成で置いてください。

**このコマンドがすること**

Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「sample-shop/app:1.0.0」を作ります。

- compose v5 は内部で Docker Bake (BuildKit) に任せてビルドします。docker build も同じ BuildKit を使うため、できあがるイメージは同じです。
- ビルドコンテキストの Dockerfile (/mnt/c/Users/taka_/Claude/Compose_Docker_Converter/examples/sample-shop/app/Dockerfile) から読み取った内容:
- Dockerfile の FROM (土台にするイメージ): python:${PYTHON_VERSION}-alpine、python:${PYTHON_VERSION}-alpine
- ステージ (AS で名前を付けた途中段階): build、runtime
- ARG (ビルド時に外から渡せる変数): PYTHON_VERSION、APP_VERSION
- EXPOSE (使う予定のポートのメモ): 8000
- USER (コンテナ内で動くユーザー): 10001:10001
- CMD: ["python", "app.py"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--target` | `runtime` | services.app.build.target | マルチステージ Dockerfile の「runtime」ステージまでを作ります。 | マルチステージの Dockerfile で、FROM ... AS 名前 の「名前」の段階までを作ります。開発用・本番用を作り分けるのに使います。<br>（やさしく）設計図の途中の段階までで止めます。 |
| `--build-arg` | `APP_VERSION=1.0.0` | services.app.build.args | ビルド時の変数 (ARG) APP_VERSION に「1.0.0」を渡します。 | Dockerfile の ARG (ビルド時の変数) に値を渡します。バージョン番号やベースイメージの切り替えに使います。イメージの履歴に残るので、パスワードは渡さないでください。<br>（やさしく）設計図の空欄に書き込む値です。 |
| `--build-arg` | `PYTHON_VERSION=3.12` | services.app.build.args | ビルド時の変数 (ARG) PYTHON_VERSION に「3.12」を渡します。 | (同じオプションの説明は上の行を参照) |
| `--label` | `com.example.built-by=compose2docker-sample` | services.app.build.labels | イメージに目印 (ラベル) を付けます。 | できたイメージにラベル (目印) を付けます。<br>（やさしく）完成品に貼るシールです。 |
| `--tag` | `sample-shop/app:1.0.0` | services.app.image | できたイメージに「sample-shop/app:1.0.0」という名前を付けます。 | できたイメージに名前 (リポジトリ:タグ) を付けます。タグを省略すると latest になります。docker run ではこの名前で指定します。<br>（やさしく）完成品に名札を付けます。 |
| `(ビルドコンテキスト)` | `/opt/sample-shop/app` | services.app.build.context | ビルドの材料が入ったフォルダ (context) です。この中のファイルを COPY / ADD で使えます。 | ビルドの材料が入ったフォルダ (ビルドコンテキスト) です。COPY / ADD はこの中のファイルしか使えません。<br>（やさしく）材料の入った箱です。 |

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

**確認のしかた**: `docker image ls sample-shop/app` ／ `docker image inspect sample-shop/app:1.0.0`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  app:
    build:
      args:
        APP_VERSION: 1.0.0
        PYTHON_VERSION: 3.12
      context: /mnt/c/Users/taka_/Claude/Compose_Docker_Converter/examples/sample-shop/app
      dockerfile: Dockerfile
      labels:
        com.example.built-by: compose2docker-sample
      target: runtime
    image: "sample-shop/app:1.0.0"
```

</details>

<a id="step-12"></a>

### STEP 12: サービス「cache」用に、ヘルスチェックを焼き込んだイメージ「sample-shop-cache:with-healthcheck」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ヘルスチェック入りイメージ作成 |
| 使うコマンド | docker build - (ヘルスチェック入りの派生イメージを作る) |
| ひとことで | 元のイメージに、compose と同じ「exec 形式」のヘルスチェック設定だけを足したイメージを作ります。 |
| compose の対応箇所 | `services.cache.healthcheck` |

**実行するコマンド**

```bash
docker build --tag sample-shop-cache:with-healthcheck - <<'C2D_DOCKERFILE'
FROM valkey/valkey:8-alpine
HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD ["valkey-cli", "ping"]
C2D_DOCKERFILE
```

**実行のしかた**

かたまり全体 (最後の C2D_DOCKERFILE の行まで) をコピーして貼り付け、Enter を押します。途中で > という記号が表示されるのは、ヒアドキュメント (複数行の文章をコマンドに渡す書き方) の続きを受け付けている印なので、正常です。数秒で終わり、エラーが出なければ成功です。

**このコマンドがすること**

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

- exec 形式: コマンドを直接実行します。/bin/sh が入っていないイメージ (distroless など) でも動きます。
- シェル形式: /bin/sh -c 'コマンド' で実行します。シェルが無いイメージでは必ず失敗し、コンテナが unhealthy (不健康) になります。
- 作られるイメージは元のイメージにメタデータ (HEALTHCHECK の設定) を 1 つ足しただけで、中身のファイルは同じです。
- 焼き込む内容: HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD ["valkey-cli", "ping"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--tag` | `sample-shop-cache:with-healthcheck` | image (無ければ <プロジェクト>-<サービス>) | ヘルスチェック入りのイメージに「sample-shop-cache:with-healthcheck」という名前を付けます (元のイメージ「valkey/valkey:8-alpine」は変更しません)。 | (しくみは [STEP 11](#step-11) で説明) |
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

**確認のしかた**: `docker image inspect --format '{{json .Config.Healthcheck}}' sample-shop-cache:with-healthcheck`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  cache:
    healthcheck:
      interval: 5s
      retries: 10
      test:
        - CMD
        - valkey-cli
        - ping
      timeout: 3s
```

</details>

<a id="step-13"></a>

### STEP 13: サービス「web」用に、ヘルスチェックを焼き込んだイメージ「sample-shop-web:with-healthcheck」を作る

| 項目 | 内容 |
|---|---|
| 区分 | ヘルスチェック入りイメージ作成 |
| 使うコマンド | docker build - (ヘルスチェック入りの派生イメージを作る) |
| ひとことで | 元のイメージに、compose と同じ「exec 形式」のヘルスチェック設定だけを足したイメージを作ります。 |
| compose の対応箇所 | `services.web.healthcheck` |

**実行するコマンド**

```bash
docker build --tag sample-shop-web:with-healthcheck - <<'C2D_DOCKERFILE'
FROM nginx:1.27-alpine
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1/healthz"]
C2D_DOCKERFILE
```

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 12](#step-12) と同じです)。

**このコマンドがすること**

compose の healthcheck は exec 形式 (test: ["CMD", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。

- exec 形式: コマンドを直接実行します。/bin/sh が入っていないイメージ (distroless など) でも動きます。
- シェル形式: /bin/sh -c 'コマンド' で実行します。シェルが無いイメージでは必ず失敗し、コンテナが unhealthy (不健康) になります。
- 作られるイメージは元のイメージにメタデータ (HEALTHCHECK の設定) を 1 つ足しただけで、中身のファイルは同じです。
- 焼き込む内容: HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1/healthz"]

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--tag` | `sample-shop-web:with-healthcheck` | image (無ければ <プロジェクト>-<サービス>) | ヘルスチェック入りのイメージに「sample-shop-web:with-healthcheck」という名前を付けます (元のイメージ「nginx:1.27-alpine」は変更しません)。 | (しくみは [STEP 11](#step-11) で説明) |
| `(Dockerfile の読み込み元)` | `-` | (派生イメージ) | 「-」は Dockerfile を標準入力 (下のヒアドキュメント) から読む、という意味です。材料フォルダ (コンテキスト) は使いません。 | 「-」は Dockerfile を標準入力から読むという意味です。<br>（やさしく）設計図を手渡しします。 |

**しくみ・歴史**: STEP 12 と同じ `docker build (healthcheck)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-build-healthcheck) を参照してください。

**小学生向けのまとめ**: 元のおもちゃはそのままで、「元気かな？チェックのやり方」を書いたカードを貼った版を作るコマンドです。

**確認のしかた**: `docker image inspect --format '{{json .Config.Healthcheck}}' sample-shop-web:with-healthcheck`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  web:
    healthcheck:
      interval: 10s
      retries: 5
      test:
        - CMD
        - wget
        - "-q"
        - "-O"
        - /dev/null
        - "http://127.0.0.1/healthz"
      timeout: 3s
```

</details>

<a id="step-14"></a>

### STEP 14: サービス「db」のコンテナ「sample-shop-db-1」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.db` |

**実行するコマンド**

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

**実行のしかた**

かたまり全体をコピーして貼り付け、Enter を押します。行の最後の \ (バックスラッシュ。Excel の Meiryo UI では ¥ に見えます) は「コマンドが次の行に続く」という印なので、途中で切らずに全部まとめて貼り付けてください。成功すると、作られたコンテナの ID (64 文字の英数字) が 1 行表示されます。  
・「Conflict. The container name "/..." is already in use」は、同じ名前のコンテナが残っています。後片付けをしてからやり直します。  
・「port is already allocated」「address already in use」は、ホストのそのポートを別のプログラムが使っています。  
・ID が表示されてもすぐ止まってしまうことがあります。docker ps --all で STATUS を見て、Exited なら docker logs <名前> で原因を調べます。

**このコマンドがすること**

イメージ「postgres:16-alpine」からコンテナ「sample-shop-db-1」を作って起動します (サービス「db」)。

- ネットワーク: sample-shop_backend
- マウント: 3 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 3 件 / --env-file 0 件

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | コンテナを裏側 (バックグラウンド) で動かし、コマンドはすぐに終わってプロンプトに戻ります。付けないと、コンテナの画面出力がターミナルに流れ続け、Ctrl+C でコンテナも止まってしまいます。出力はあとから docker logs で見られます。<br>（やさしく）おもちゃのスイッチを入れたら、見張っていなくても勝手に動き続けるようにします。 |
| `--name` | `sample-shop-db-1` | container_name (無ければ <プロジェクト>-<サービス>-<番号>) | コンテナに「sample-shop-db-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 | コンテナに名前を付けます。名前は同じホストの中で 1 つだけで、docker logs や docker stop で使えるほか、ユーザー定義ネットワークではその名前で相手を呼べます (内蔵 DNS がコンテナ名を IP に変換します)。compose v2 以降は「プロジェクト-サービス-番号」とハイフンでつなぎます (昔の compose v1 はアンダースコア _ でした)。<br>（やさしく）コンテナに名札を付けます。名札の名前で呼んだり、止めたりできます。 |
| `--restart` | `unless-stopped` | services.db.restart | コンテナが止まったときの再起動のルールを unless-stopped にします。 | コンテナが止まったときに、dockerd が自動で起動し直すかどうかのルールです。no (しない・標準)、always (いつでも)、unless-stopped (docker stop で止めた場合を除いて)、on-failure[:回数] (異常終了したときだけ、回数まで) があります。起こし直す間隔は 100 ミリ秒から始まって倍々に伸びます (最大 1 分)。Docker 自体が再起動したとき (サーバーの再起動など) にも、always と unless-stopped のコンテナは自動で起動します。compose の deploy.restart_policy が書かれている場合は、そちらが優先されます (condition: any → always、on-failure + max_attempts → on-failure:回数、none → no)。<br>（やさしく）コンテナが転んだら、管理人さんが起こしてあげるかどうかの約束です。 |
| `--network` | `sample-shop_backend` | services.db.networks.backend | ネットワーク「sample-shop_backend」につなぎます。 | コンテナをどのネットワークにつなぐかを決めます。ネットワーク名を書けばそのネットワークへ、host ならホストのネットワークをそのまま使用、none ならつながない、container:<名前> なら別のコンテナとネットワークを共有します (compose の network_mode: service:<サービス>)。<br>name=ネットワーク名,alias=別名,ip=IP アドレス のような長い書き方 (Docker 25 以降) を使うと、1 回の docker run で複数のネットワークにつなぎ、それぞれに別名や IP を設定できます。compose は priority (優先度) が高い順、同じなら名前の順にネットワークを並べ、最初のものをメインにします。<br>（やさしく）コンテナをどの道路 (ネットワーク) につなぐかを決めます。 |
| `--network-alias` | `db` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「db」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | そのネットワークの中だけで使える、コンテナの別名を付けます。内蔵 DNS がこの名前を IP アドレスに変換するので、ほかのコンテナからhttp://<別名>:ポート で呼べます。compose はサービス名を必ず別名にするため、ここでもサービス名を付けています。同じ別名を複数のコンテナに付けると、DNS は順番に答えを返します (かんたんな負荷分散)。<br>（やさしく）電話帳に「あだ名」を登録して、あだ名でも電話がかかるようにします。 |
| `--volume` | `sample-shop_db-data:/var/lib/postgresql/data` | services.db.volumes | 名前付きボリューム「sample-shop_db-data」をコンテナの /var/lib/postgresql/data につなぎます。 | ホストのフォルダ・ファイル、または名前付きボリュームを、コンテナの中の場所につなぎます (マウント)。書き方は 元:コンテナ内の場所[:ro][,z]。元が / や ./ で始まればホストのパス (バインドマウント)、名前ならボリュームです。:ro は読み取り専用、:z / :Z は SELinux 用のラベル付けです。ホスト側のフォルダが無いときは空のフォルダが自動で作られます (compose の短い書き方と同じ動き)。compose v5 も、短い書き方のバインドと、オプションの無い名前付きボリュームは、この形 (Docker API の Binds) で渡しています。<br>（やさしく）お部屋の壁に、外の引き出し (ホストのフォルダ) やロッカー (ボリューム) へ通じる扉を付けます。 |
| `--volume` | `/opt/sample-shop/db/init.sql:/docker-entrypoint-initdb.d/10-init.sql:ro` | services.db.volumes | ホストの /opt/sample-shop/db/init.sql をコンテナの /docker-entrypoint-initdb.d/10-init.sql に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (同じオプションの説明は上の行を参照) |
| `--mount` | `type=bind,source=/opt/sample-shop/secrets/db_password.txt,target=/run/secrets/db_password,readonly` | services.db.secrets | 秘密情報 (secrets.db_password) のファイルを、読み取り専用で /run/secrets/db_password に置きます。 | マウントを key=value で 1 つずつ指定する、読みやすく厳密な書き方です (Docker 17.06 から)。type=bind (ホストのパス)、type=volume (ボリューム)、type=tmpfs (メモリ上)、type=image (イメージの中身。Docker 28 から) があり、source= (元)、target= (コンテナ内の場所)、readonly、bind-propagation、volume-nocopy、volume-subpath、tmpfs-size などを指定できます。--volume と違い、type=bind でホスト側が無いとエラーになります (bind-create-src を付けると作成)。target だけの type=volume は、名前の無い (匿名) ボリュームを新しく作ります。<br>（やさしく）扉の付け方を、項目ごとにくわしく指定した注文書です。 |
| `--env` | `POSTGRES_DB=shop` | services.db.environment | 環境変数 POSTGRES_DB に「shop」を設定します。 | コンテナの中のプログラムに渡す環境変数 (名前=値 の設定メモ) を指定します。データベースの接続先やパスワード、動作モードなどを、イメージを作り直さずに切り替えられます。値を書かずに名前だけ (--env NAME) にすると、実行するシェルにある同じ名前の変数の値が渡されます。<br>compose は compose ファイルの ${VAR} を .env や OS の環境変数で展開してから値を決めます。この手順の値は、展開済みの最終的な値です。同じ名前が複数あると、後に書いたものが勝ちます (environment が env_file より優先、という compose の規則と同じ順に並べています)。<br>（やさしく）お部屋に置いておく「設定メモ」です。プログラムはこのメモを読んで動き方を変えます。 |
| `--env` | `POSTGRES_PASSWORD_FILE=/run/secrets/db_password` | services.db.environment | 環境変数 POSTGRES_PASSWORD_FILE に「/run/secrets/db_password」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `POSTGRES_USER=shop` | services.db.environment | 環境変数 POSTGRES_USER に「shop」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--shm-size` | `128m` | services.db.shm_size | 共有メモリ (/dev/shm) の大きさを 128m にします (既定は 64m)。 | 共有メモリ (/dev/shm) の大きさです。標準は 64MB で、データベースやブラウザーを動かすときに足りなくなることがあります。<br>（やさしく）みんなで使う作業台の大きさです。 |
| `--log-driver` | `json-file` | services.db.logging.driver | ログ (コンテナの出力) の保存方法を json-file にします。 | コンテナの画面出力 (標準出力・標準エラー) をどこへ保存するかを決めます。json-file (標準。JSON 形式のファイル)、local (圧縮つきの効率的な形式)、journald (RHEL の systemd ジャーナル)、syslog、awslogs (CloudWatch Logs)、none (保存しない) などがあります。<br>（やさしく）お部屋の「日記帳」の種類を決めます。 |
| `--log-opt` | `max-file=3` | services.db.logging.options | ログ保存の設定 max-file=3 です。 | ログドライバーへの設定です。json-file なら max-size=10m (1 ファイルの大きさ) と max-file=3 (残すファイル数) でログが際限なく増えるのを防げます。<br>（やさしく）日記帳のページ数などのルールです。 |
| `--log-opt` | `max-size=10m` | services.db.logging.options | ログ保存の設定 max-size=10m です。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `pg_isready -U shop -d shop` | services.db.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | ヘルスチェック (健康診断) で実行するコマンドです。dockerd が定期的にコンテナの中で /bin/sh -c 'コマンド' を実行し、終了コード 0 なら合格です。シェル形式なので、イメージに /bin/sh が無いと使えません (その場合このツールは派生イメージで exec 形式を再現します)。<br>（やさしく）「元気？」と聞くときの質問の中身です。 |
| `--health-interval` | `5s` | services.db.healthcheck.interval | 何秒おきにチェックするか: 5s | ヘルスチェックの間隔です (標準 30 秒)。<br>（やさしく）何秒おきに「元気？」と聞くかです。 |
| `--health-timeout` | `3s` | services.db.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | 1 回のチェックの制限時間です (標準 30 秒)。超えたら不合格です。<br>（やさしく）返事を待つ時間の長さです。 |
| `--health-start-period` | `10s` | services.db.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 10s | 起動直後の猶予期間です。この間の不合格は数えません (起動に時間がかかるアプリ用)。<br>（やさしく）起きたばかりの間は、返事がなくても大目に見る時間です。 |
| `--health-retries` | `10` | services.db.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 10 回 | 何回続けて不合格になったら unhealthy (不健康) とするかです (標準 3 回)。<br>（やさしく）何回続けて返事がなかったら「具合が悪い」とするかです。 |
| `--stop-timeout` | `30` | services.db.stop_grace_period | 止めるとき、合図を送ってから 30 秒待っても終わらなければ強制終了 (SIGKILL) します (compose の stop_grace_period: 30s)。 | 停止の合図を送ってから、強制終了 (SIGKILL) するまで待つ秒数です (標準 10 秒)。compose の stop_grace_period (例: 1m30s) を秒に直した値です。<br>（やさしく）お片付けを待ってあげる時間です。 |
| `(イメージ)` | `postgres:16-alpine` | services.db.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

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

**確認のしかた**: `docker ps --all --filter name=sample-shop-db-1` ／ `docker logs sample-shop-db-1` ／ `docker inspect sample-shop-db-1`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  db:
    environment:
      POSTGRES_DB: shop
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      POSTGRES_USER: shop
    healthcheck:
      interval: 5s
      retries: 10
      start_period: 10s
      test:
        - CMD-SHELL
        - pg_isready -U shop -d shop
      timeout: 3s
    image: "postgres:16-alpine"
    logging:
      driver: json-file
      options:
        max-file: 3
        max-size: 10m
    networks: {}
    restart: unless-stopped
    secrets:
      - source: db_password
        target: /run/secrets/db_password
    shm_size: 134217728
    stop_grace_period: 30s
    volumes:
      - source: db-data
        target: /var/lib/postgresql/data
        type: volume
        volume: {}
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Compose_Docker_Converter/examples/sample-shop/db/init.sql
        target: /docker-entrypoint-initdb.d/10-init.sql
        type: bind
```

</details>

<a id="step-15"></a>

### STEP 15: サービス「cache」のコンテナ「sample-shop-cache-1」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.cache` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 14](#step-14) と同じです)。

**このコマンドがすること**

イメージ「sample-shop-cache:with-healthcheck」からコンテナ「sample-shop-cache-1」を作って起動します (サービス「cache」)。

- ネットワーク: sample-shop_backend
- マウント: 1 件 (データの置き場所をコンテナにつなぎます)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 14](#step-14) で説明) |
| `--name` | `sample-shop-cache-1` | container_name (無ければ <プロジェクト>-<サービス>-<番号>) | コンテナに「sample-shop-cache-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 | (しくみは [STEP 14](#step-14) で説明) |
| `--restart` | `unless-stopped` | services.cache.restart | コンテナが止まったときの再起動のルールを unless-stopped にします。 | (しくみは [STEP 14](#step-14) で説明) |
| `--network` | `sample-shop_backend` | services.cache.networks.backend | ネットワーク「sample-shop_backend」につなぎます。 | (しくみは [STEP 14](#step-14) で説明) |
| `--network-alias` | `cache` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「cache」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 14](#step-14) で説明) |
| `--volume` | `sample-shop_cache-data:/data` | services.cache.volumes | 名前付きボリューム「sample-shop_cache-data」をコンテナの /data につなぎます。 | (しくみは [STEP 14](#step-14) で説明) |
| `--log-driver` | `json-file` | services.cache.logging.driver | ログ (コンテナの出力) の保存方法を json-file にします。 | (しくみは [STEP 14](#step-14) で説明) |
| `--log-opt` | `max-file=3` | services.cache.logging.options | ログ保存の設定 max-file=3 です。 | (しくみは [STEP 14](#step-14) で説明) |
| `--log-opt` | `max-size=10m` | services.cache.logging.options | ログ保存の設定 max-size=10m です。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `sample-shop-cache:with-healthcheck` | services.cache.image | ヘルスチェック入りの派生イメージ (元: valkey/valkey:8-alpine) です。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `valkey-server --appendonly yes --save ` | services.cache.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 14 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=sample-shop-cache-1` ／ `docker logs sample-shop-cache-1` ／ `docker inspect sample-shop-cache-1`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  cache:
    command:
      - valkey-server
      - "--appendonly"
      - "yes"
      - "--save"
      - ""
    healthcheck:
      interval: 5s
      retries: 10
      test:
        - CMD
        - valkey-cli
        - ping
      timeout: 3s
    image: "valkey/valkey:8-alpine"
    logging:
      driver: json-file
      options:
        max-file: 3
        max-size: 10m
    networks: {}
    restart: unless-stopped
    volumes:
      - source: cache-data
        target: /data
        type: volume
        volume: {}
```

</details>

<a id="step-16"></a>

### STEP 16: sample-shop-db-1 が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.migrate.depends_on` |

**実行するコマンド**

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

**実行のしかた**

かたまり全体 (for から最後の done まで) を貼り付けて Enter。「[待機] ... 待ちます」と表示され、準備ができると「[OK] ... は healthy です」と表示されて、プロンプトに戻ります。数十秒〜数分かかることがあります。  
・「[NG] ... の状態は running:unhealthy」などと出たら、相手のコンテナに問題があります。docker logs <名前> で原因を確認してください。  
・ずっと待ち続けて終わらないときは Ctrl+C で止めて、docker ps で状態を確認します。

**このコマンドがすること**

サービス「migrate」は depends_on で db が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

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

**確認のしかた**: `docker ps --filter name=sample-shop-db-1`

<a id="step-17"></a>

### STEP 17: サービス「migrate」のコンテナ「sample-shop-migrate-1」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.migrate` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 14](#step-14) と同じです)。

**このコマンドがすること**

イメージ「postgres:16-alpine」からコンテナ「sample-shop-migrate-1」を作って起動します (サービス「migrate」)。

- ネットワーク: sample-shop_backend
- マウント: 2 件 (データの置き場所をコンテナにつなぎます)
- depends_on (先に起動しておくもの): db (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 14](#step-14) で説明) |
| `--name` | `sample-shop-migrate-1` | container_name (無ければ <プロジェクト>-<サービス>-<番号>) | コンテナに「sample-shop-migrate-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 | (しくみは [STEP 14](#step-14) で説明) |
| `--network` | `sample-shop_backend` | services.migrate.networks.backend | ネットワーク「sample-shop_backend」につなぎます。 | (しくみは [STEP 14](#step-14) で説明) |
| `--network-alias` | `migrate` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「migrate」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 14](#step-14) で説明) |
| `--volume` | `/opt/sample-shop/db/migrations:/migrations:ro` | services.migrate.volumes | ホストの /opt/sample-shop/db/migrations をコンテナの /migrations に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 14](#step-14) で説明) |
| `--mount` | `type=bind,source=/opt/sample-shop/secrets/db_password.txt,target=/run/secrets/db_password,readonly` | services.migrate.secrets | 秘密情報 (secrets.db_password) のファイルを、読み取り専用で /run/secrets/db_password に置きます。 | (しくみは [STEP 14](#step-14) で説明) |
| `--log-driver` | `json-file` | services.migrate.logging.driver | ログ (コンテナの出力) の保存方法を json-file にします。 | (しくみは [STEP 14](#step-14) で説明) |
| `--log-opt` | `max-file=3` | services.migrate.logging.options | ログ保存の設定 max-file=3 です。 | (しくみは [STEP 14](#step-14) で説明) |
| `--log-opt` | `max-size=10m` | services.migrate.logging.options | ログ保存の設定 max-size=10m です。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `postgres:16-alpine` | services.migrate.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `sh -c export PGPASSWORD="$(cat /run/secrets/db_password)"<br>psql -h db -U shop -d shop -v ON_ERROR_STOP=1 -f /migrations/001_items.sql<br>echo "migration done"<br>` | services.migrate.command | イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ・歴史**: STEP 14 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=sample-shop-migrate-1` ／ `docker logs sample-shop-migrate-1` ／ `docker inspect sample-shop-migrate-1`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  migrate:
    command:
      - sh
      - "-c"
      - "export PGPASSWORD=\"$(cat /run/secrets/db_password)\"\npsql -h db -U shop -d shop -v ON_ERROR_STOP=1 -f /migrations/001_items.sql\necho \"migration done\"\n"
    depends_on:
      db:
        condition: service_healthy
        required: true
    image: "postgres:16-alpine"
    logging:
      driver: json-file
      options:
        max-file: 3
        max-size: 10m
    networks: {}
    restart: "no"
    secrets:
      - source: db_password
        target: /run/secrets/db_password
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Compose_Docker_Converter/examples/sample-shop/db/migrations
        target: /migrations
        type: bind
```

</details>

<a id="step-18"></a>

### STEP 18: sample-shop-cache-1・sample-shop-db-1 が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.app.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 16](#step-16) と同じです)。

**このコマンドがすること**

サービス「app」は depends_on で cache・db が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 16](#step-16) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 16 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=sample-shop-cache-1`

<a id="step-19"></a>

### STEP 19: sample-shop-migrate-1 が正常終了するまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 完了待ち |
| 使うコマンド | docker wait ― コンテナが終わるのを待つ |
| ひとことで | depends_on の「condition: service_completed_successfully」を再現するため、相手のコンテナが終わるまで待ち、終了コードを確かめます。 |
| compose の対応箇所 | `services.app.depends_on` |

**実行するコマンド**

```bash
echo "[待機] sample-shop-migrate-1 が終わるまで待ちます..."
EXIT_CODE="$(docker wait sample-shop-migrate-1)"
echo "sample-shop-migrate-1 の終了コード: ${EXIT_CODE} (0 なら成功)"
```

**実行のしかた**

貼り付けて Enter。相手が終わると「終了コード: 0 (0 なら成功)」と表示されます。0 以外が表示されたら、その先へ進まず docker logs で原因を確認します。

**このコマンドがすること**

サービス「app」は depends_on で「service_completed_successfully (正常に終了)」を待つ設定です。docker wait で終了を待ち、終了コードが 0 (成功) かを確かめます。

- compose は終了コードが 0 以外だと「service ... didn't complete successfully」というエラーで止まります。0 以外が表示されたら、ここで手を止めて docker logs sample-shop-migrate-1 で原因を確認してください。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(コンテナ名)` | `sample-shop-migrate-1` |  | 終了するまで待つコンテナです。終了したら終了コードを表示します。 |  |

**しくみ (動作原理)**

dockerd に POST /containers/<ID>/wait を送り、コンテナの状態が「終了」に変わるまで返事を待ち続けます (ポーリングではなく、変化の通知を待つ方式)。

**動作イメージ (たとえ話)**

準備体操が終わるまで待って、「ちゃんとできた？」と結果 (終了コード) を聞くようなものです。

**歴史と背景・必要になった経緯**

docker wait は 2013 年の Docker 登場時からあるコマンドです。compose の service_completed_successfully は 2021 年 (Compose 1.29) に加わりました。

**RHEL 9.8 での注意**

特にありません。

**小学生向けのまとめ**: 前の人のお仕事が終わるまで待って、「うまくいった？」と聞くコマンドです。0 は「うまくいったよ」の合図です。

**確認のしかた**: `docker ps --all --filter name=sample-shop-migrate-1` ／ `docker logs sample-shop-migrate-1`

<a id="step-20"></a>

### STEP 20: サービス「app」のコンテナ「sample-shop-app-1」を作る (まだ起動しない)

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ作成 |
| 使うコマンド | docker create ― コンテナを作る (まだ起動しない) |
| ひとことで | コンテナを作るところまで行い、起動はしません。起動前にファイルを入れたり準備をしたりするために使います。 |
| compose の対応箇所 | `services.app` |

**実行するコマンド**

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

**実行のしかた**

かたまり全体を貼り付けて Enter。コンテナ ID が表示されれば成功です。docker ps --all で見ると STATUS が Created になっています。

**このコマンドがすること**

コンテナ「sample-shop-app-1」をイメージ「sample-shop/app:1.0.0」から作りますが、まだ起動しません。起動前にファイルの投入や初期化 (pre_start) を行うためです。

- ネットワーク: name=sample-shop_backend,alias=app、name=sample-shop_frontend,alias=app,alias=api
- マウント: 2 件 (データの置き場所をコンテナにつなぎます)
- 環境変数: --env 7 件 / --env-file 1 件
- depends_on (先に起動しておくもの): cache (service_healthy)、db (service_healthy)、migrate (service_completed_successfully)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--name` | `sample-shop-app-1` | container_name (無ければ <プロジェクト>-<サービス>-<番号>) | コンテナに「sample-shop-app-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 | コンテナに名前を付けます。名前は同じホストの中で 1 つだけで、docker logs や docker stop で使えるほか、ユーザー定義ネットワークではその名前で相手を呼べます (内蔵 DNS がコンテナ名を IP に変換します)。compose v2 以降は「プロジェクト-サービス-番号」とハイフンでつなぎます (昔の compose v1 はアンダースコア _ でした)。<br>（やさしく）コンテナに名札を付けます。名札の名前で呼んだり、止めたりできます。 |
| `--restart` | `unless-stopped` | services.app.restart | コンテナが止まったときの再起動のルールを unless-stopped にします。 | コンテナが止まったときに、dockerd が自動で起動し直すかどうかのルールです。no (しない・標準)、always (いつでも)、unless-stopped (docker stop で止めた場合を除いて)、on-failure[:回数] (異常終了したときだけ、回数まで) があります。起こし直す間隔は 100 ミリ秒から始まって倍々に伸びます (最大 1 分)。Docker 自体が再起動したとき (サーバーの再起動など) にも、always と unless-stopped のコンテナは自動で起動します。compose の deploy.restart_policy が書かれている場合は、そちらが優先されます (condition: any → always、on-failure + max_attempts → on-failure:回数、none → no)。<br>（やさしく）コンテナが転んだら、管理人さんが起こしてあげるかどうかの約束です。 |
| `--init` |  | services.app.init | コンテナの最初のプロセス (PID 1) として小さな init (docker-init = tini) を入れ、ゾンビプロセスの後片付けとシグナルの中継をさせます。 | コンテナの PID 1 (最初のプロセス) として、小さなお世話係プログラム docker-init (中身は tini) を置き、その子どもとして本来のプログラムを動かします。Linux では PID 1 が「親を亡くしたプロセス (ゾンビ)」を片付ける役目を持ちますが、ふつうのアプリはそれをしないため、ゾンビが溜まったり、停止の合図 (SIGTERM) を無視してしまったりします。init がそれを肩代わりします (Docker 1.13、2017 年から)。<br>（やさしく）お部屋に「お世話係」を 1 人置いて、後片付けや連絡係をしてもらいます。 |
| `--user` | `10001:10001` | services.app.user | コンテナの中のプログラムを ユーザー 10001:10001 として動かします。 | コンテナの中のプログラムを、どのユーザー (UID) とグループ (GID) で動かすかを決めます。例: 1000:1000、appuser。指定しないとイメージの USER (無ければ root) で動きます。root 以外で動かすと、万一乗っ取られても被害を小さくできます。バインドマウントしたホストのフォルダの読み書きは、この UID/GID の権限で判断されます。<br>（やさしく）お部屋の中で「だれ」として作業するかを決めます。 |
| `--network` | `name=sample-shop_backend,alias=app` | services.app.networks.backend | ネットワーク「sample-shop_backend」につなぎ、app という名前で呼べるようにします。(最初に書いたネットワークがメイン = 優先度 priority が一番高いもの / 同じなら名前順)。 | コンテナをどのネットワークにつなぐかを決めます。ネットワーク名を書けばそのネットワークへ、host ならホストのネットワークをそのまま使用、none ならつながない、container:<名前> なら別のコンテナとネットワークを共有します (compose の network_mode: service:<サービス>)。<br>name=ネットワーク名,alias=別名,ip=IP アドレス のような長い書き方 (Docker 25 以降) を使うと、1 回の docker run で複数のネットワークにつなぎ、それぞれに別名や IP を設定できます。compose は priority (優先度) が高い順、同じなら名前の順にネットワークを並べ、最初のものをメインにします。<br>（やさしく）コンテナをどの道路 (ネットワーク) につなぐかを決めます。 |
| `--network` | `name=sample-shop_frontend,alias=app,alias=api` | services.app.networks.frontend | ネットワーク「sample-shop_frontend」につなぎ、app・api という名前で呼べるようにします。 | (同じオプションの説明は上の行を参照) |
| `--add-host` | `host.docker.internal:host-gateway` | services.app.extra_hosts | コンテナの /etc/hosts に「host.docker.internal → host-gateway」を書き足します (host-gateway はホスト自身の IP に置き換わります)。 | コンテナの /etc/hosts に「名前 IP アドレス」の行を書き足します。DNS に登録されていない相手を名前で呼びたいときに使います。host-gateway と書くと、ホスト自身の IP アドレス (コンテナから見た出口) に置き換わります (Docker 20.10 から)。<br>（やさしく）お部屋の電話帳に、手書きで番号を書き足します。 |
| `--volume` | `sample-shop_app-cache:/var/cache/shop` | services.app.volumes | 名前付きボリューム「sample-shop_app-cache」をコンテナの /var/cache/shop につなぎます。 | ホストのフォルダ・ファイル、または名前付きボリュームを、コンテナの中の場所につなぎます (マウント)。書き方は 元:コンテナ内の場所[:ro][,z]。元が / や ./ で始まればホストのパス (バインドマウント)、名前ならボリュームです。:ro は読み取り専用、:z / :Z は SELinux 用のラベル付けです。ホスト側のフォルダが無いときは空のフォルダが自動で作られます (compose の短い書き方と同じ動き)。compose v5 も、短い書き方のバインドと、オプションの無い名前付きボリュームは、この形 (Docker API の Binds) で渡しています。<br>（やさしく）お部屋の壁に、外の引き出し (ホストのフォルダ) やロッカー (ボリューム) へ通じる扉を付けます。 |
| `--tmpfs` | `/tmp:size=16m` | services.app.tmpfs | メモリ上の一時的な場所 (tmpfs) を /tmp に作ります。 | メモリの上に一時的なファイル置き場 (tmpfs) を作り、指定した場所につなぎます。とても速く、コンテナを止めると中身は消えます。size= で大きさの上限、mode= で権限を指定できます。--read-only と組み合わせて、書き込みが必要な /tmp だけを用意するのによく使います。<br>（やさしく）消えてもいいメモを書く「ホワイトボード」を部屋に置きます。電気を消すと (止めると) 消えます。 |
| `--env-file` | `/opt/sample-shop/env/app.env` | services.app.env_file | ファイル app.env に書かれた環境変数 (2 個) をまとめて渡します。 | 環境変数を書いたファイル (1 行に 名前=値) をまとめて読み込みます。ただし docker の --env-file は、compose の env_file と読み方が少し違います (クォート "..." を外さない、# のコメントや ${VAR} の展開をしない など)。このツールは、両方で同じ値になると確認できたファイルだけを --env-file で渡し、違いが出るファイルは展開済みの値を --env で 1 つずつ渡しています。<br>（やさしく）設定メモをまとめた「ノート」を 1 冊渡します。 |
| `--env` | `API_TOKEN=s3cr3t-token` | services.app.env_file | 環境変数 API_TOKEN に「s3cr3t-token」を設定します (env_file から読み込んだ値)。 | コンテナの中のプログラムに渡す環境変数 (名前=値 の設定メモ) を指定します。データベースの接続先やパスワード、動作モードなどを、イメージを作り直さずに切り替えられます。値を書かずに名前だけ (--env NAME) にすると、実行するシェルにある同じ名前の変数の値が渡されます。<br>compose は compose ファイルの ${VAR} を .env や OS の環境変数で展開してから値を決めます。この手順の値は、展開済みの最終的な値です。同じ名前が複数あると、後に書いたものが勝ちます (environment が env_file より優先、という compose の規則と同じ順に並べています)。<br>（やさしく）お部屋に置いておく「設定メモ」です。プログラムはこのメモを読んで動き方を変えます。 |
| `--env` | `CACHE_HOST=cache` | services.app.environment | 環境変数 CACHE_HOST に「cache」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_HOST=db` | services.app.environment | 環境変数 DB_HOST に「db」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_PORT=5432` | services.app.environment | 環境変数 DB_PORT に「5432」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `GREETING=Hello from version 1.0.0` | services.app.env_file | 環境変数 GREETING に「Hello from version 1.0.0」を設定します (env_file から読み込んだ値)。 | (同じオプションの説明は上の行を参照) |
| `--env` | `LOG_LEVEL=info` | services.app.environment | 環境変数 LOG_LEVEL に「info」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `SETTINGS_FILE=/etc/shop/settings.ini` | services.app.environment | 環境変数 SETTINGS_FILE に「/etc/shop/settings.ini」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--ulimit` | `nofile=4096:8192` | services.app.ulimits | 資源の上限 (ulimit) nofile を 4096:8192 にします。 | 1 つのプロセスが使える資源の上限 (ulimit) を決めます。nofile=ソフト:ハード で同時に開けるファイル数、nproc でプロセス数など。Docker 29 では nofile の標準 (ソフト上限) が 1024 なので、たくさんの接続を扱うサーバーは上げておくことが大切です。<br>（やさしく）一度に机に広げていい本の数の上限です。 |
| `--cpus` | `0.5` | services.app.deploy.resources.limits.cpus | 使える CPU を 0.5 個分までに制限します。 | 使える CPU を「何個分」で制限します (例: 0.5 なら 1 個の半分)。cgroup v2 の cpu.max という設定に変換され、100 ミリ秒ごとに使える時間が決まります。<br>（やさしく）使っていい計算の力を「半人前」などと決めます。 |
| `--memory` | `256m` | services.app.deploy.resources.limits.memory | 使えるメモリを 256m までに制限します。超えるとコンテナ内のプロセスが強制終了 (OOM Kill) されます。 | 使えるメモリの上限です (例: 512m、1g)。cgroup v2 の memory.max に設定され、超えるとカーネルの OOM キラーがコンテナ内のプロセスを強制終了します (docker ps で Exited (137) と表示されます)。<br>（やさしく）使っていい机の広さ (メモリ) の上限です。はみ出すと退場になります。 |
| `--log-driver` | `json-file` | services.app.logging.driver | ログ (コンテナの出力) の保存方法を json-file にします。 | コンテナの画面出力 (標準出力・標準エラー) をどこへ保存するかを決めます。json-file (標準。JSON 形式のファイル)、local (圧縮つきの効率的な形式)、journald (RHEL の systemd ジャーナル)、syslog、awslogs (CloudWatch Logs)、none (保存しない) などがあります。<br>（やさしく）お部屋の「日記帳」の種類を決めます。 |
| `--log-opt` | `max-file=3` | services.app.logging.options | ログ保存の設定 max-file=3 です。 | ログドライバーへの設定です。json-file なら max-size=10m (1 ファイルの大きさ) と max-file=3 (残すファイル数) でログが際限なく増えるのを防げます。<br>（やさしく）日記帳のページ数などのルールです。 |
| `--log-opt` | `max-size=10m` | services.app.logging.options | ログ保存の設定 max-size=10m です。 | (同じオプションの説明は上の行を参照) |
| `--health-cmd` | `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"` | services.app.healthcheck.test | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 | ヘルスチェック (健康診断) で実行するコマンドです。dockerd が定期的にコンテナの中で /bin/sh -c 'コマンド' を実行し、終了コード 0 なら合格です。シェル形式なので、イメージに /bin/sh が無いと使えません (その場合このツールは派生イメージで exec 形式を再現します)。<br>（やさしく）「元気？」と聞くときの質問の中身です。 |
| `--health-interval` | `5s` | services.app.healthcheck.interval | 何秒おきにチェックするか: 5s | ヘルスチェックの間隔です (標準 30 秒)。<br>（やさしく）何秒おきに「元気？」と聞くかです。 |
| `--health-timeout` | `3s` | services.app.healthcheck.timeout | 1 回のチェックを何秒で打ち切るか: 3s | 1 回のチェックの制限時間です (標準 30 秒)。超えたら不合格です。<br>（やさしく）返事を待つ時間の長さです。 |
| `--health-start-period` | `5s` | services.app.healthcheck.start_period | 起動直後の、失敗を数えない猶予期間: 5s | 起動直後の猶予期間です。この間の不合格は数えません (起動に時間がかかるアプリ用)。<br>（やさしく）起きたばかりの間は、返事がなくても大目に見る時間です。 |
| `--health-retries` | `10` | services.app.healthcheck.retries | 何回続けて失敗したら unhealthy (不健康) とするか: 10 回 | 何回続けて不合格になったら unhealthy (不健康) とするかです (標準 3 回)。<br>（やさしく）何回続けて返事がなかったら「具合が悪い」とするかです。 |
| `(イメージ)` | `sample-shop/app:1.0.0` | services.app.image | このイメージからコンテナを作ります。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ (動作原理)**

dockerd に POST /containers/create だけを送ります。コンテナの設定と、書き込み用の層 (overlayfs の upper) が用意されますが、プロセスはまだ動いておらず、ネットワークにもまだつながっていません (IP アドレスは start のときに割り当てられます)。

**動作イメージ (たとえ話)**

お部屋に家具を運び込んだけれど、まだ住人が入居していない状態です。入居前に、部屋に必要な書類を置いておけます。

**歴史と背景・必要になった経緯**

docker create は 2014 年 10 月の Docker 1.3 で追加されました。それまでは docker run しかなく、「作るだけ」ができませんでした。

**RHEL 9.8 での注意**

docker run と同じです。

**小学生向けのまとめ**: おもちゃを組み立てるけれど、まだスイッチは入れない、というコマンドです。

**この STEP の注意**

- 複数のネットワークを docker run 1 回でつなぐ書き方 (--network name=...,alias=...) は Docker Engine 25 以降で使えます。RHEL 9.8 で最新の docker-ce (29.x) を入れていれば問題ありません。

**確認のしかた**: `docker ps --all --filter name=sample-shop-app-1` ／ `docker logs sample-shop-app-1` ／ `docker inspect sample-shop-app-1`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  app:
    build:
      args:
        APP_VERSION: 1.0.0
        PYTHON_VERSION: 3.12
      context: /mnt/c/Users/taka_/Claude/Compose_Docker_Converter/examples/sample-shop/app
      dockerfile: Dockerfile
      labels:
        com.example.built-by: compose2docker-sample
      target: runtime
    configs:
      - source: app_settings
        target: /etc/shop/settings.ini
    depends_on:
      cache:
        condition: service_healthy
        required: true
      db:
        condition: service_healthy
        required: true
      migrate:
        condition: service_completed_successfully
        required: true
    deploy:
      resources:
        limits:
          cpus: 0.5
          memory: 268435456
    environment:
      API_TOKEN: s3cr3t-token
      CACHE_HOST: cache
      DB_HOST: db
      DB_PORT: 5432
      FEATURE_FLAGS: "search,cart"
      GREETING: Hello from version 1.0.0
      LOG_LEVEL: info
      SETTINGS_FILE: /etc/shop/settings.ini
      SHOP_NAME: Sample Shop
    extra_hosts:
      - host.docker.internal=host-gateway
    healthcheck:
      interval: 5s
      retries: 10
      start_period: 5s
      test:
        - CMD-SHELL
        - "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)\""
      timeout: 3s
    image: "sample-shop/app:1.0.0"
    init: true
    logging:
      driver: json-file
      options:
        max-file: 3
        max-size: 10m
    networks:
      backend: {}
      frontend:
        aliases:
          - api
    post_start:
      - command:
          - sh
          - "-c"
          - "date > /tmp/started-at"
    pre_start:
      - command:
          - sh
          - "-c"
          - "echo warmed-at-start > /var/cache/shop/warm.txt && chown -R 10001:10001 /var/cache/shop"
        image: "busybox:1.36"
        user: root
    restart: unless-stopped
    tmpfs:
      - "/tmp:size=16m"
    ulimits:
      nofile:
        hard: 8192
        soft: 4096
    user: "10001:10001"
    volumes:
      - source: app-cache
        target: /var/cache/shop
        type: volume
        volume: {}
```

</details>

<a id="step-21"></a>

### STEP 21: 設定ファイル (configs)「app_settings」を sample-shop-app-1 の /etc/shop/settings.ini に入れる

| 項目 | 内容 |
|---|---|
| 区分 | ファイル投入 |
| 使うコマンド | docker cp ― コンテナにファイルを入れる |
| ひとことで | compose の configs (content) や secrets (environment) の中身を、起動前のコンテナにファイルとして書き込みます。 |
| compose の対応箇所 | `configs.app_settings` |

**実行するコマンド**

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

**実行のしかた**

かたまり全体 (mkdir から rm -rf まで) を貼り付けて Enter。エラーが出なければ成功です。中身は cat > ... <<'C2D_CONTENT' から C2D_CONTENT までの行に書かれています。

**このコマンドがすること**

compose は 設定ファイル (configs) の中身 (content / environment) を、コンテナを起動する前にファイルとして書き込みます。同じように、一時ファイルを作って tar でまとめ、docker cp でコンテナの /etc/shop/settings.ini に入れます。

- 所有者 uid=0 / gid=0、権限 0444 で入れます (compose の既定は root / 0444 = 読み取り専用)。
- tar を使うのは、所有者と権限を指定でき、途中のフォルダ (/etc/shop) が無くても作ってくれるからです。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(コピー元)` | `-` |  | 「-」は標準入力から tar 形式のデータを受け取る、という意味です。 |  |
| `(コピー先)` | `sample-shop-app-1:/` |  | コンテナ sample-shop-app-1 のルート (/) を基準に展開します。 |  |

**しくみ (動作原理)**

docker cp は内部で tar 形式 (ファイルを持ち主・権限などの情報ごと 1 つにまとめる昔からの形式) のデータを dockerd に送ります (API: PUT /containers/<ID>/archive)。docker cp - は「標準入力から tar を受け取る」という意味で、パイプ (|) で tar の出力をそのまま渡しています。--owner / --group / --mode で、コンテナの中でのファイルの持ち主と権限を compose と同じにしています。書き込み先はコンテナの書き込み用の層なので、コンテナを再起動しても残り、コンテナを削除すると消えます。

**動作イメージ (たとえ話)**

住人が入居する前のお部屋に、取扱説明書 (設定ファイル) を置いておくようなものです。

**歴史と背景・必要になった経緯**

docker cp は最初「コンテナからホストへ」しかコピーできませんでしたが、2015 年 8 月の Docker 1.8 で「ホストからコンテナへ」もできるようになりました。compose の configs / secrets はもともと Swarm (複数台のサーバーをまとめる仕組み) 用の機能でしたが、compose でも使えるようにするため、ファイルからはバインドマウント、中身の直書きからはこのコピーで実現しています。

**RHEL 9.8 での注意**

RHEL の tar (GNU tar) は --owner / --group / --mode に対応しています。/tmp に書き込めるユーザーで実行してください。

**小学生向けのまとめ**: お部屋を使い始める前に、必要なお手紙を部屋の中に置いておくコマンドです。

**確認のしかた**: `docker cp sample-shop-app-1:/etc/shop/settings.ini - | tar -tvf -`

<a id="step-22"></a>

### STEP 22: サービス「app」の起動前の初期化 1 (pre_start) を実行する

| 項目 | 内容 |
|---|---|
| 区分 | 初期化コンテナ |
| 使うコマンド | docker run --rm ― 初期化コンテナ (pre_start) を実行する |
| ひとことで | 本番のコンテナを起動する前に、使い捨てのコンテナで準備作業 (データベースの初期化など) を 1 回だけ行います。 |
| compose の対応箇所 | `services.app.pre_start[0]` |

**実行するコマンド**

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

**実行のしかた**

貼り付けて Enter。準備作業の画面出力がそのまま表示され、終わるとプロンプトに戻ります。エラーが表示された場合 (終了コードが 0 以外) は、compose ならここで起動を中止します。次の STEP へ進まず、原因を確認してください。

**このコマンドがすること**

compose v5.3 で追加された init コンテナ (pre_start) を再現します。本番コンテナを作った後・起動する前に、使い捨てのコンテナで準備作業を 1 回だけ行います。

- compose と同じく、本番コンテナと同じネットワーク・同じボリュームを使います (--volumes-from)。
- 終了コードが 0 以外 (失敗) の場合、compose はこのサービスと、これに依存するサービスを起動しません。エラーが出たらここで止めて原因を確認してください。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--rm` |  | (pre_start の後片付け) | 終わったらこの一時的なコンテナを自動で削除します (compose も実行後に削除します)。 | コンテナが終わったら、自動で削除します。使い捨ての作業に便利です。<br>（やさしく）使い終わったら自動でお片付けします。 |
| `--volumes-from` | `sample-shop-app-1` | (pre_start: 本番と同じマウント) | 本番のコンテナ「sample-shop-app-1」と同じボリューム・バインドマウントを同じ場所につなぎます。初期化で作ったファイルが本番から見えるようにするためです。 | 本番コンテナと同じボリューム・バインドマウントを、同じ場所につなぎます。準備作業の結果が本番から見えるようになります。<br>（やさしく）本番のお部屋と同じロッカーを使います。 |
| `--network` | `name=sample-shop_backend,alias=app` | services.app.networks.backend | ネットワーク「sample-shop_backend」につなぎ、app という名前で呼べるようにします。(最初に書いたネットワークがメイン = 優先度 priority が一番高いもの / 同じなら名前順)。 | (しくみは [STEP 14](#step-14) で説明) |
| `--network` | `name=sample-shop_frontend,alias=app,alias=api` | services.app.networks.frontend | ネットワーク「sample-shop_frontend」につなぎ、app・api という名前で呼べるようにします。 | (同じオプションの説明は上の行を参照) |
| `--user` | `root` | services.app.pre_start[0].user | 初期化はユーザー root で行います。 | コンテナの中のプログラムを、どのユーザー (UID) とグループ (GID) で動かすかを決めます。例: 1000:1000、appuser。指定しないとイメージの USER (無ければ root) で動きます。root 以外で動かすと、万一乗っ取られても被害を小さくできます。バインドマウントしたホストのフォルダの読み書きは、この UID/GID の権限で判断されます。<br>（やさしく）お部屋の中で「だれ」として作業するかを決めます。 |
| `--env-file` | `/opt/sample-shop/env/app.env` | services.app.env_file | ファイル app.env に書かれた環境変数 (2 個) をまとめて渡します。 | 環境変数を書いたファイル (1 行に 名前=値) をまとめて読み込みます。ただし docker の --env-file は、compose の env_file と読み方が少し違います (クォート "..." を外さない、# のコメントや ${VAR} の展開をしない など)。このツールは、両方で同じ値になると確認できたファイルだけを --env-file で渡し、違いが出るファイルは展開済みの値を --env で 1 つずつ渡しています。<br>（やさしく）設定メモをまとめた「ノート」を 1 冊渡します。 |
| `--env` | `API_TOKEN=s3cr3t-token` | services.app.env_file | 環境変数 API_TOKEN に「s3cr3t-token」を設定します (env_file から読み込んだ値)。 | (しくみは [STEP 14](#step-14) で説明) |
| `--env` | `CACHE_HOST=cache` | services.app.environment | 環境変数 CACHE_HOST に「cache」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_HOST=db` | services.app.environment | 環境変数 DB_HOST に「db」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `DB_PORT=5432` | services.app.environment | 環境変数 DB_PORT に「5432」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `GREETING=Hello from version 1.0.0` | services.app.env_file | 環境変数 GREETING に「Hello from version 1.0.0」を設定します (env_file から読み込んだ値)。 | (同じオプションの説明は上の行を参照) |
| `--env` | `LOG_LEVEL=info` | services.app.environment | 環境変数 LOG_LEVEL に「info」を設定します。 | (同じオプションの説明は上の行を参照) |
| `--env` | `SETTINGS_FILE=/etc/shop/settings.ini` | services.app.environment | 環境変数 SETTINGS_FILE に「/etc/shop/settings.ini」を設定します。 | (同じオプションの説明は上の行を参照) |
| `(イメージ)` | `busybox:1.36` | image / build | 初期化に使うイメージです (指定が無ければサービスと同じイメージ)。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |
| `(コマンドと引数)` | `sh -c echo warmed-at-start > /var/cache/shop/warm.txt && chown -R 10001:10001 /var/cache/shop` | services.app.pre_start[0].command | 初期化で実行するコマンドです。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ (動作原理)**

compose 5.5 の実際の動きを調べると、init コンテナは「本番コンテナの ID を VolumesFrom に指定」「本番と同じネットワークと別名」「環境変数は本番の environment + pre_start の environment」「ユーザー・作業フォルダは pre_start の指定 (無ければイメージの既定)」で作られ、終了コードを確認したあとに削除されます。この STEP は同じ設定の docker run --rm です。

**動作イメージ (たとえ話)**

お店の開店前にだけ来て、棚を並べたり値札を付けたりして帰る「準備係さん」です。準備が終わってから、店員さん (本番コンテナ) が出勤します。

**歴史と背景・必要になった経緯**

Kubernetes には 2016 年ごろから initContainers (本番の前に動く準備用コンテナ) があり、データベースの移行などに広く使われてきました。compose では長い間、「準備用サービス + depends_on の service_completed_successfully」で代用していましたが、2026 年 7 月の Compose 5.3.0 で pre_start として正式に用意されました。

**RHEL 9.8 での注意**

docker run と同じです。

**小学生向けのまとめ**: 本番の前に準備だけして帰る「お手伝いさん」のコンテナを動かすコマンドです。

**確認のしかた**: `docker logs sample-shop-app-1  (初期化コンテナは --rm で消えるため、上の画面出力で確認します)`

<a id="step-23"></a>

### STEP 23: コンテナ「sample-shop-app-1」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker start ― 作っておいたコンテナを起動する |
| ひとことで | docker create で作ったコンテナを起動します。 |
| compose の対応箇所 | `services.app` |

**実行するコマンド**

```bash
docker start sample-shop-app-1
```

**実行のしかた**

貼り付けて Enter。コンテナ名が表示されれば成功です。docker ps で STATUS が Up になっているか確認できます。

**このコマンドがすること**

ファイルの投入・初期化コンテナ (pre_start) が終わったので、コンテナ「sample-shop-app-1」を起動します。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(コンテナ名)` | `sample-shop-app-1` |  | docker create で作っておいたコンテナです。 |  |

**しくみ (動作原理)**

dockerd に POST /containers/<ID>/start を送ります。runc が名前空間・cgroup を作り、ネットワークにつなぎ、ENTRYPOINT + CMD を PID 1 として実行します。

**動作イメージ (たとえ話)**

準備のできたお部屋に、いよいよ住人が入居します。

**歴史と背景・必要になった経緯**

docker start は、止めたコンテナをもう一度動かすためのコマンドとして初期からあります。

**RHEL 9.8 での注意**

docker run と同じです。

**小学生向けのまとめ**: 組み立てておいたおもちゃのスイッチを入れるコマンドです。

**確認のしかた**: `docker ps --filter name=sample-shop-app-1` ／ `docker logs sample-shop-app-1`

<a id="step-24"></a>

### STEP 24: コンテナ「sample-shop-app-1」で post_start フック 1 を実行する

| 項目 | 内容 |
|---|---|
| 区分 | 起動後フック |
| 使うコマンド | docker exec ― 動いているコンテナの中でコマンドを実行する |
| ひとことで | 起動中のコンテナの中で、追加のコマンドを実行します (compose の post_start / pre_stop フック)。 |
| compose の対応箇所 | `services.app.post_start[0]` |

**実行するコマンド**

```bash
docker exec sample-shop-app-1 sh -c 'date > /tmp/started-at'
```

**実行のしかた**

貼り付けて Enter。コマンドの出力が表示されます。エラーなくプロンプトに戻れば成功です。

**このコマンドがすること**

compose の post_start フック (コンテナ起動直後に中で実行するコマンド) を docker exec で再現します。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `(コンテナ名)` | `sample-shop-app-1` |  | コマンドを実行する (起動中の) コンテナです。 |  |
| `(コマンドと引数)` | `sh -c date > /tmp/started-at` | services.app.post_start[0].command | コンテナの中で実行するコマンドです。 | イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。<br>（やさしく）お部屋に入った住人が、最初にやるお仕事です。 |

**しくみ (動作原理)**

dockerd に POST /containers/<ID>/exec (準備) と POST /exec/<ID>/start (実行) を送ります。runc exec が、コンテナの名前空間に「合流」(setns というシステムコール) して新しいプロセスを起動します。そのため、コンテナの中と同じファイル・同じネットワーク・同じ制限 (cgroup) で動きます。コマンドが終わると、そのプロセスだけが消えます。

**動作イメージ (たとえ話)**

営業中のお店に、お手伝いさんを 1 人送り込んで作業してもらうようなものです。作業が終わればお手伝いさんは帰り、お店はそのまま営業を続けます。

**歴史と背景・必要になった経緯**

docker exec は 2014 年 10 月の Docker 1.3 で追加されました。compose のライフサイクルフック (post_start / pre_stop) は 2024 年 10 月の Compose 2.30.0 で追加されています。

**RHEL 9.8 での注意**

特にありません。

**小学生向けのまとめ**: 動いているコンテナの中に、もう 1 人お手伝いさんを入れて仕事をしてもらうコマンドです。

**確認のしかた**: `docker logs sample-shop-app-1`

<a id="step-25"></a>

### STEP 25: sample-shop-app-1 が healthy になるまで待つ

| 項目 | 内容 |
|---|---|
| 区分 | 起動待ち |
| 使うコマンド | docker inspect の繰り返し ― healthy になるまで待つ |
| ひとことで | depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。 |
| compose の対応箇所 | `services.web.depends_on` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 16](#step-16) と同じです)。

**このコマンドがすること**

サービス「web」は depends_on で app が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。

- compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。
- このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--format` | `{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}` | (depends_on の待ち合わせ) | コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。 | (しくみは [STEP 16](#step-16) で説明) |
| `(コンテナ名)` | `${C}` |  | for 文で 1 つずつ入れ替わるコンテナ名です。 |  |

**しくみ・歴史**: STEP 16 と同じ `docker inspect (health)` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-inspect-health) を参照してください。

**小学生向けのまとめ**: 友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。

**この STEP の注意**

- NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

**確認のしかた**: `docker ps --filter name=sample-shop-app-1`

<a id="step-26"></a>

### STEP 26: サービス「web」のコンテナ「sample-shop-web-1」を起動する

| 項目 | 内容 |
|---|---|
| 区分 | コンテナ起動 |
| 使うコマンド | docker run ― コンテナを作って起動する |
| ひとことで | イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。 |
| compose の対応箇所 | `services.web` |

**実行するコマンド**

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

**実行のしかた**

上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP 14](#step-14) と同じです)。

**このコマンドがすること**

イメージ「sample-shop-web:with-healthcheck」からコンテナ「sample-shop-web-1」を作って起動します (サービス「web」)。

- ネットワーク: sample-shop_frontend
- 公開ポート (ホスト → コンテナ): 8088:80
- マウント: 4 件 (データの置き場所をコンテナにつなぎます)
- depends_on (先に起動しておくもの): app (service_healthy)

**オプション・引数の意味**

| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |
|---|---|---|---|---|
| `--detach` |  | docker compose up -d の -d | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 | (しくみは [STEP 14](#step-14) で説明) |
| `--name` | `sample-shop-web-1` | container_name (無ければ <プロジェクト>-<サービス>-<番号>) | コンテナに「sample-shop-web-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 | (しくみは [STEP 14](#step-14) で説明) |
| `--restart` | `always` | services.web.restart | コンテナが止まったときの再起動のルールを always にします。 | (しくみは [STEP 14](#step-14) で説明) |
| `--network` | `sample-shop_frontend` | services.web.networks.frontend | ネットワーク「sample-shop_frontend」につなぎます。 | (しくみは [STEP 14](#step-14) で説明) |
| `--network-alias` | `web` | networks.<名前>.aliases (サービス名は compose が自動で追加) | このネットワークの中で「web」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 | (しくみは [STEP 14](#step-14) で説明) |
| `--publish` | `8088:80` | services.web.ports | ホスト (RHEL) の 8088 番ポート (TCP) に届いた通信を、コンテナの 80 番ポートへ転送します。 | ホスト (RHEL) のポートに届いた通信を、コンテナのポートへ転送します。書き方は [ホストのIP:]ホストのポート:コンテナのポート[/udp]。ホスト側を省略すると空いているポートが自動で選ばれます。<br>しくみ: dockerd がファイアウォール (iptables / nftables) に DNAT (宛先の書き換え) のルールを入れ、さらに docker-proxy という小さな中継プログラムも起動します。外から http://<RHEL の IP>:8080 に来た通信は、コンテナの IP:80 に書き換えられて届きます。IP を 127.0.0.1 にすると、そのサーバーの中からしか接続できなくなります (外には公開しない)。<br>（やさしく）マンションの正面玄関の「〇番窓口」に来たお客さんを、お部屋の「〇番ドア」へ案内する道案内です。 |
| `--volume` | `/opt/sample-shop/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro` | services.web.volumes | ホストの /opt/sample-shop/web/nginx.conf をコンテナの /etc/nginx/conf.d/default.conf に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 | (しくみは [STEP 14](#step-14) で説明) |
| `--tmpfs` | `/var/cache/nginx` | services.web.tmpfs | メモリ上の一時的な場所 (tmpfs) を /var/cache/nginx に作ります。 | メモリの上に一時的なファイル置き場 (tmpfs) を作り、指定した場所につなぎます。とても速く、コンテナを止めると中身は消えます。size= で大きさの上限、mode= で権限を指定できます。--read-only と組み合わせて、書き込みが必要な /tmp だけを用意するのによく使います。<br>（やさしく）消えてもいいメモを書く「ホワイトボード」を部屋に置きます。電気を消すと (止めると) 消えます。 |
| `--tmpfs` | `/var/run` | services.web.tmpfs | メモリ上の一時的な場所 (tmpfs) を /var/run に作ります。 | (同じオプションの説明は上の行を参照) |
| `--tmpfs` | `/tmp` | services.web.tmpfs | メモリ上の一時的な場所 (tmpfs) を /tmp に作ります。 | (同じオプションの説明は上の行を参照) |
| `--label` | `com.example.role=frontend` | services.web.labels | コンテナに目印 (ラベル) com.example.role=frontend を付けます。 | コンテナに目印 (ラベル = キーと値の組) を付けます。動作には影響せず、docker ps --filter label=... で探したり、監視ツールが読んだりします。compose 自身も com.docker.compose.project などのラベルを付けて「どのプロジェクトのコンテナか」を管理しています (このツールは --compose-labels を指定したときだけ同じラベルを付けます)。<br>（やさしく）コンテナに貼るシール (目印) です。 |
| `--read-only` |  | services.web.read_only | コンテナのファイルシステムを読み取り専用にします (書けるのはボリュームや tmpfs だけ)。 | コンテナのルートファイルシステムを読み取り専用にします。書き込めるのはボリューム・バインドマウント・tmpfs だけになり、万一乗っ取られても中のプログラムを書き換えられにくくなります。<br>（やさしく）お部屋の壁や家具に落書き禁止のシールを貼ります。書いていいのはホワイトボードだけです。 |
| `--cap-drop` | `NET_RAW` | services.web.cap_drop | Linux の特権の一部 (ケーパビリティ) NET_RAW を取り上げます。 | 許可されている capabilities を取り上げます。ALL を指定してから必要なものだけ --cap-add すると、いちばん安全です。<br>（やさしく）使わない合鍵を返してもらいます。 |
| `--security-opt` | `no-new-privileges:true` | services.web.security_opt | コンテナの中のプログラムが、setuid などで今より強い権限を持てないようにします。 | セキュリティの細かい設定です。no-new-privileges:true は、setuid などで今より強い権限を得ることを禁止します。seccomp=プロファイル は使えるシステムコールを制限、label=... は SELinux のラベル、apparmor=... は AppArmor (Ubuntu 系) の設定です。<br>（やさしく）お部屋のルールを追加します (例: 「えらくなる魔法は使えません」)。 |
| `--log-driver` | `json-file` | services.web.logging.driver | ログ (コンテナの出力) の保存方法を json-file にします。 | (しくみは [STEP 14](#step-14) で説明) |
| `--log-opt` | `max-file=3` | services.web.logging.options | ログ保存の設定 max-file=3 です。 | (しくみは [STEP 14](#step-14) で説明) |
| `--log-opt` | `max-size=10m` | services.web.logging.options | ログ保存の設定 max-size=10m です。 | (同じオプションの説明は上の行を参照) |
| `--stop-signal` | `SIGQUIT` | services.web.stop_signal | コンテナを止めるときに送る合図 (シグナル) を SIGQUIT にします。 | docker stop で送る停止の合図 (シグナル) を決めます。標準は SIGTERM。nginx の SIGQUIT のように、アプリによって行儀よく終わる合図が違います。<br>（やさしく）「おしまいだよ」の合図の言葉を決めます。 |
| `--stop-timeout` | `15` | services.web.stop_grace_period | 止めるとき、合図を送ってから 15 秒待っても終わらなければ強制終了 (SIGKILL) します (compose の stop_grace_period: 15s)。 | (しくみは [STEP 14](#step-14) で説明) |
| `(イメージ)` | `sample-shop-web:with-healthcheck` | services.web.image | ヘルスチェック入りの派生イメージ (元: nginx:1.27-alpine) です。 | コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。<br>（やさしく）どのお部屋セットを使うかです。 |

**しくみ・歴史**: STEP 14 と同じ `docker run` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#kb-docker-run) を参照してください。

**小学生向けのまとめ**: おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。

**確認のしかた**: `docker ps --all --filter name=sample-shop-web-1` ／ `docker logs sample-shop-web-1` ／ `docker inspect sample-shop-web-1`

<details><summary>compose ではこう書かれていた (正規化後)</summary>

```yaml
services:
  web:
    cap_drop:
      - NET_RAW
    depends_on:
      app:
        condition: service_healthy
        required: true
    healthcheck:
      interval: 10s
      retries: 5
      test:
        - CMD
        - wget
        - "-q"
        - "-O"
        - /dev/null
        - "http://127.0.0.1/healthz"
      timeout: 3s
    image: "nginx:1.27-alpine"
    labels:
      com.example.role: frontend
    logging:
      driver: json-file
      options:
        max-file: 3
        max-size: 10m
    networks: {}
    ports:
      - mode: ingress
        protocol: tcp
        published: 8088
        target: 80
    read_only: true
    restart: always
    security_opt:
      - "no-new-privileges:true"
    stop_grace_period: 15s
    stop_signal: SIGQUIT
    tmpfs:
      - /var/cache/nginx
      - /var/run
      - /tmp
    volumes:
      - bind: {}
        read_only: true
        source: /mnt/c/Users/taka_/Claude/Compose_Docker_Converter/examples/sample-shop/web/nginx.conf
        target: /etc/nginx/conf.d/default.conf
        type: bind
```

</details>

<a id="step-27"></a>

### STEP 27: 起動したコンテナの状態を確認する

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

作ったコンテナ (sample-shop-db-1、sample-shop-cache-1、sample-shop-migrate-1、sample-shop-app-1、sample-shop-web-1) が Up (起動中) になっているか、ヘルスチェックの結果 (healthy など) を確認します。

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

<a id="kb-docker-wait"></a>

### docker wait ― コンテナが終わるのを待つ

- 書き方: `EXIT_CODE="$(docker wait コンテナ名)"`
- ひとことで: depends_on の「condition: service_completed_successfully」を再現するため、相手のコンテナが終わるまで待ち、終了コードを確かめます。

**意味**

docker wait は、指定したコンテナが終了するまで待ち、終了コード (プログラムの最後の返事。0 は成功、それ以外は失敗) を表示します。$( ) はコマンドの出力を受け取る書き方で、それを EXIT_CODE という変数に入れて表示しています。compose の service_completed_successfully は「1 回だけ動いて終わる準備用のサービス (初期データの投入など) が成功してから次を起動する」ための設定です。

**しくみ (動作原理)**

dockerd に POST /containers/<ID>/wait を送り、コンテナの状態が「終了」に変わるまで返事を待ち続けます (ポーリングではなく、変化の通知を待つ方式)。

**動作イメージ**

準備体操が終わるまで待って、「ちゃんとできた？」と結果 (終了コード) を聞くようなものです。

**歴史と背景・必要になった経緯**

docker wait は 2013 年の Docker 登場時からあるコマンドです。compose の service_completed_successfully は 2021 年 (Compose 1.29) に加わりました。

**小学生向けのまとめ**

前の人のお仕事が終わるまで待って、「うまくいった？」と聞くコマンドです。0 は「うまくいったよ」の合図です。

**RHEL 9.8 での注意**

特にありません。

<a id="kb-docker-create"></a>

### docker create ― コンテナを作る (まだ起動しない)

- 書き方: `docker create [オプション] イメージ [コマンド] [引数...]`
- ひとことで: コンテナを作るところまで行い、起動はしません。起動前にファイルを入れたり準備をしたりするために使います。

**意味**

docker run の前半 (作る) だけを行うコマンドです。オプションの意味は docker run とまったく同じです。  
compose も実は、まず全部のコンテナを create してから、順番に start しています。この手順では、起動前にやること (configs / secrets のファイルの書き込み、pre_start の初期化コンテナ) があるサービスだけ、create と start を分けています。

**しくみ (動作原理)**

dockerd に POST /containers/create だけを送ります。コンテナの設定と、書き込み用の層 (overlayfs の upper) が用意されますが、プロセスはまだ動いておらず、ネットワークにもまだつながっていません (IP アドレスは start のときに割り当てられます)。

**動作イメージ**

お部屋に家具を運び込んだけれど、まだ住人が入居していない状態です。入居前に、部屋に必要な書類を置いておけます。

**歴史と背景・必要になった経緯**

docker create は 2014 年 10 月の Docker 1.3 で追加されました。それまでは docker run しかなく、「作るだけ」ができませんでした。

**小学生向けのまとめ**

おもちゃを組み立てるけれど、まだスイッチは入れない、というコマンドです。

**RHEL 9.8 での注意**

docker run と同じです。

<a id="kb-docker-cp"></a>

### docker cp ― コンテナにファイルを入れる

- 書き方: `tar ... --file - ファイル | docker cp - コンテナ名:/`
- ひとことで: compose の configs (content) や secrets (environment) の中身を、起動前のコンテナにファイルとして書き込みます。

**意味**

compose は、configs: に content: (中身を直接書いたもの) や environment: (環境変数の値を使うもの) で定義された設定ファイル・秘密情報を、コンテナを起動する前にコンテナの中へファイルとしてコピーします (ファイルの持ち主は root、権限は読み取り専用の 0444 が標準)。  
同じことをするため、① 一時フォルダ (/tmp/<プロジェクト>-compose2docker) にファイルを作り、② tar で「持ち主・権限つき」の 1 つのかたまりにまとめ、③ docker cp でコンテナのルート (/) に展開し、④ 一時フォルダを消します。

**しくみ (動作原理)**

docker cp は内部で tar 形式 (ファイルを持ち主・権限などの情報ごと 1 つにまとめる昔からの形式) のデータを dockerd に送ります (API: PUT /containers/<ID>/archive)。docker cp - は「標準入力から tar を受け取る」という意味で、パイプ (|) で tar の出力をそのまま渡しています。--owner / --group / --mode で、コンテナの中でのファイルの持ち主と権限を compose と同じにしています。書き込み先はコンテナの書き込み用の層なので、コンテナを再起動しても残り、コンテナを削除すると消えます。

**動作イメージ**

住人が入居する前のお部屋に、取扱説明書 (設定ファイル) を置いておくようなものです。

**歴史と背景・必要になった経緯**

docker cp は最初「コンテナからホストへ」しかコピーできませんでしたが、2015 年 8 月の Docker 1.8 で「ホストからコンテナへ」もできるようになりました。compose の configs / secrets はもともと Swarm (複数台のサーバーをまとめる仕組み) 用の機能でしたが、compose でも使えるようにするため、ファイルからはバインドマウント、中身の直書きからはこのコピーで実現しています。

**小学生向けのまとめ**

お部屋を使い始める前に、必要なお手紙を部屋の中に置いておくコマンドです。

**RHEL 9.8 での注意**

RHEL の tar (GNU tar) は --owner / --group / --mode に対応しています。/tmp に書き込めるユーザーで実行してください。

<a id="kb-docker-run-init"></a>

### docker run --rm ― 初期化コンテナ (pre_start) を実行する

- 書き方: `docker run --rm --volumes-from 本番コンテナ [オプション] イメージ コマンド`
- ひとことで: 本番のコンテナを起動する前に、使い捨てのコンテナで準備作業 (データベースの初期化など) を 1 回だけ行います。

**意味**

compose 5.3 (2026 年 7 月) で追加された pre_start (init コンテナ) を再現します。pre_start に書いたコマンドは、本番のコンテナを作った後・起動する前に、別の使い捨てコンテナで実行されます。  
--rm は終わったら自動で削除、--volumes-from は本番コンテナと同じボリューム・フォルダを同じ場所につなぐ、という意味です。準備で作ったファイルは、共有したボリュームを通して本番コンテナから見えます。ネットワークも本番と同じものにつなぎます。

**しくみ (動作原理)**

compose 5.5 の実際の動きを調べると、init コンテナは「本番コンテナの ID を VolumesFrom に指定」「本番と同じネットワークと別名」「環境変数は本番の environment + pre_start の environment」「ユーザー・作業フォルダは pre_start の指定 (無ければイメージの既定)」で作られ、終了コードを確認したあとに削除されます。この STEP は同じ設定の docker run --rm です。

**動作イメージ**

お店の開店前にだけ来て、棚を並べたり値札を付けたりして帰る「準備係さん」です。準備が終わってから、店員さん (本番コンテナ) が出勤します。

**歴史と背景・必要になった経緯**

Kubernetes には 2016 年ごろから initContainers (本番の前に動く準備用コンテナ) があり、データベースの移行などに広く使われてきました。compose では長い間、「準備用サービス + depends_on の service_completed_successfully」で代用していましたが、2026 年 7 月の Compose 5.3.0 で pre_start として正式に用意されました。

**小学生向けのまとめ**

本番の前に準備だけして帰る「お手伝いさん」のコンテナを動かすコマンドです。

**RHEL 9.8 での注意**

docker run と同じです。

<a id="kb-docker-start"></a>

### docker start ― 作っておいたコンテナを起動する

- 書き方: `docker start コンテナ名`
- ひとことで: docker create で作ったコンテナを起動します。

**意味**

docker run の後半 (起動) だけを行います。起動前の準備 (ファイルの投入・初期化コンテナ) が終わったので、ここで初めてプログラムが動き出します。

**しくみ (動作原理)**

dockerd に POST /containers/<ID>/start を送ります。runc が名前空間・cgroup を作り、ネットワークにつなぎ、ENTRYPOINT + CMD を PID 1 として実行します。

**動作イメージ**

準備のできたお部屋に、いよいよ住人が入居します。

**歴史と背景・必要になった経緯**

docker start は、止めたコンテナをもう一度動かすためのコマンドとして初期からあります。

**小学生向けのまとめ**

組み立てておいたおもちゃのスイッチを入れるコマンドです。

**RHEL 9.8 での注意**

docker run と同じです。

<a id="kb-docker-exec"></a>

### docker exec ― 動いているコンテナの中でコマンドを実行する

- 書き方: `docker exec [オプション] コンテナ名 コマンド [引数...]`
- ひとことで: 起動中のコンテナの中で、追加のコマンドを実行します (compose の post_start / pre_stop フック)。

**意味**

docker exec は、すでに動いているコンテナの中で、もう 1 つ別のプログラムを動かすコマンドです。compose の post_start (起動直後に行う作業) と pre_stop (止める直前に行う作業) は、実際にこの仕組みで実行されています。--user で実行するユーザー、--env で追加の環境変数、--workdir で作業フォルダを指定できます。

**しくみ (動作原理)**

dockerd に POST /containers/<ID>/exec (準備) と POST /exec/<ID>/start (実行) を送ります。runc exec が、コンテナの名前空間に「合流」(setns というシステムコール) して新しいプロセスを起動します。そのため、コンテナの中と同じファイル・同じネットワーク・同じ制限 (cgroup) で動きます。コマンドが終わると、そのプロセスだけが消えます。

**動作イメージ**

営業中のお店に、お手伝いさんを 1 人送り込んで作業してもらうようなものです。作業が終わればお手伝いさんは帰り、お店はそのまま営業を続けます。

**歴史と背景・必要になった経緯**

docker exec は 2014 年 10 月の Docker 1.3 で追加されました。compose のライフサイクルフック (post_start / pre_stop) は 2024 年 10 月の Compose 2.30.0 で追加されています。

**小学生向けのまとめ**

動いているコンテナの中に、もう 1 人お手伝いさんを入れて仕事をしてもらうコマンドです。

**RHEL 9.8 での注意**

特にありません。

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
| db | sample-shop-db-1 | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| db | sample-shop-db-1 | (compose が自動で付与) | `--name` | `sample-shop-db-1` | コンテナに「sample-shop-db-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 |
| db | sample-shop-db-1 | services.db.restart | `--restart` | `unless-stopped` | コンテナが止まったときの再起動のルールを unless-stopped にします。 |
| db | sample-shop-db-1 | services.db.networks.backend | `--network` | `sample-shop_backend` | ネットワーク「sample-shop_backend」につなぎます。 |
| db | sample-shop-db-1 | (compose が自動で付与) | `--network-alias` | `db` | このネットワークの中で「db」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| db | sample-shop-db-1 | services.db.volumes | `--volume` | `sample-shop_db-data:/var/lib/postgresql/data` | 名前付きボリューム「sample-shop_db-data」をコンテナの /var/lib/postgresql/data につなぎます。 |
| db | sample-shop-db-1 | services.db.volumes | `--volume` | `/opt/sample-shop/db/init.sql:/docker-entrypoint-initdb.d/10-init.sql:ro` | ホストの /opt/sample-shop/db/init.sql をコンテナの /docker-entrypoint-initdb.d/10-init.sql に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| db | sample-shop-db-1 | services.db.secrets | `--mount` | `type=bind,source=/opt/sample-shop/secrets/db_password.txt,target=/run/secrets/db_password,readonly` | 秘密情報 (secrets.db_password) のファイルを、読み取り専用で /run/secrets/db_password に置きます。 |
| db | sample-shop-db-1 | services.db.environment | `--env` | `POSTGRES_DB=shop` | 環境変数 POSTGRES_DB に「shop」を設定します。 |
| db | sample-shop-db-1 | services.db.environment | `--env` | `POSTGRES_PASSWORD_FILE=/run/secrets/db_password` | 環境変数 POSTGRES_PASSWORD_FILE に「/run/secrets/db_password」を設定します。 |
| db | sample-shop-db-1 | services.db.environment | `--env` | `POSTGRES_USER=shop` | 環境変数 POSTGRES_USER に「shop」を設定します。 |
| db | sample-shop-db-1 | services.db.shm_size | `--shm-size` | `128m` | 共有メモリ (/dev/shm) の大きさを 128m にします (既定は 64m)。 |
| db | sample-shop-db-1 | services.db.logging.driver | `--log-driver` | `json-file` | ログ (コンテナの出力) の保存方法を json-file にします。 |
| db | sample-shop-db-1 | services.db.logging.options | `--log-opt` | `max-file=3` | ログ保存の設定 max-file=3 です。 |
| db | sample-shop-db-1 | services.db.logging.options | `--log-opt` | `max-size=10m` | ログ保存の設定 max-size=10m です。 |
| db | sample-shop-db-1 | services.db.healthcheck.test | `--health-cmd` | `pg_isready -U shop -d shop` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| db | sample-shop-db-1 | services.db.healthcheck.interval | `--health-interval` | `5s` | 何秒おきにチェックするか: 5s |
| db | sample-shop-db-1 | services.db.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| db | sample-shop-db-1 | services.db.healthcheck.start_period | `--health-start-period` | `10s` | 起動直後の、失敗を数えない猶予期間: 10s |
| db | sample-shop-db-1 | services.db.healthcheck.retries | `--health-retries` | `10` | 何回続けて失敗したら unhealthy (不健康) とするか: 10 回 |
| db | sample-shop-db-1 | services.db.stop_grace_period | `--stop-timeout` | `30` | 止めるとき、合図を送ってから 30 秒待っても終わらなければ強制終了 (SIGKILL) します (compose の stop_grace_period: 30s)。 |
| cache | sample-shop-cache-1 | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| cache | sample-shop-cache-1 | (compose が自動で付与) | `--name` | `sample-shop-cache-1` | コンテナに「sample-shop-cache-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 |
| cache | sample-shop-cache-1 | services.cache.restart | `--restart` | `unless-stopped` | コンテナが止まったときの再起動のルールを unless-stopped にします。 |
| cache | sample-shop-cache-1 | services.cache.networks.backend | `--network` | `sample-shop_backend` | ネットワーク「sample-shop_backend」につなぎます。 |
| cache | sample-shop-cache-1 | (compose が自動で付与) | `--network-alias` | `cache` | このネットワークの中で「cache」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| cache | sample-shop-cache-1 | services.cache.volumes | `--volume` | `sample-shop_cache-data:/data` | 名前付きボリューム「sample-shop_cache-data」をコンテナの /data につなぎます。 |
| cache | sample-shop-cache-1 | services.cache.logging.driver | `--log-driver` | `json-file` | ログ (コンテナの出力) の保存方法を json-file にします。 |
| cache | sample-shop-cache-1 | services.cache.logging.options | `--log-opt` | `max-file=3` | ログ保存の設定 max-file=3 です。 |
| cache | sample-shop-cache-1 | services.cache.logging.options | `--log-opt` | `max-size=10m` | ログ保存の設定 max-size=10m です。 |
| migrate | sample-shop-migrate-1 | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| migrate | sample-shop-migrate-1 | (compose が自動で付与) | `--name` | `sample-shop-migrate-1` | コンテナに「sample-shop-migrate-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 |
| migrate | sample-shop-migrate-1 | services.migrate.networks.backend | `--network` | `sample-shop_backend` | ネットワーク「sample-shop_backend」につなぎます。 |
| migrate | sample-shop-migrate-1 | (compose が自動で付与) | `--network-alias` | `migrate` | このネットワークの中で「migrate」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| migrate | sample-shop-migrate-1 | services.migrate.volumes | `--volume` | `/opt/sample-shop/db/migrations:/migrations:ro` | ホストの /opt/sample-shop/db/migrations をコンテナの /migrations に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| migrate | sample-shop-migrate-1 | services.migrate.secrets | `--mount` | `type=bind,source=/opt/sample-shop/secrets/db_password.txt,target=/run/secrets/db_password,readonly` | 秘密情報 (secrets.db_password) のファイルを、読み取り専用で /run/secrets/db_password に置きます。 |
| migrate | sample-shop-migrate-1 | services.migrate.logging.driver | `--log-driver` | `json-file` | ログ (コンテナの出力) の保存方法を json-file にします。 |
| migrate | sample-shop-migrate-1 | services.migrate.logging.options | `--log-opt` | `max-file=3` | ログ保存の設定 max-file=3 です。 |
| migrate | sample-shop-migrate-1 | services.migrate.logging.options | `--log-opt` | `max-size=10m` | ログ保存の設定 max-size=10m です。 |
| app | sample-shop-app-1 | (compose が自動で付与) | `--name` | `sample-shop-app-1` | コンテナに「sample-shop-app-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 |
| app | sample-shop-app-1 | services.app.restart | `--restart` | `unless-stopped` | コンテナが止まったときの再起動のルールを unless-stopped にします。 |
| app | sample-shop-app-1 | services.app.init | `--init` |  | コンテナの最初のプロセス (PID 1) として小さな init (docker-init = tini) を入れ、ゾンビプロセスの後片付けとシグナルの中継をさせます。 |
| app | sample-shop-app-1 | services.app.user | `--user` | `10001:10001` | コンテナの中のプログラムを ユーザー 10001:10001 として動かします。 |
| app | sample-shop-app-1 | services.app.networks.backend | `--network` | `name=sample-shop_backend,alias=app` | ネットワーク「sample-shop_backend」につなぎ、app という名前で呼べるようにします。(最初に書いたネットワークがメイン = 優先度 priority が一番高いもの / 同じなら名前順)。 |
| app | sample-shop-app-1 | services.app.networks.frontend | `--network` | `name=sample-shop_frontend,alias=app,alias=api` | ネットワーク「sample-shop_frontend」につなぎ、app・api という名前で呼べるようにします。 |
| app | sample-shop-app-1 | services.app.extra_hosts | `--add-host` | `host.docker.internal:host-gateway` | コンテナの /etc/hosts に「host.docker.internal → host-gateway」を書き足します (host-gateway はホスト自身の IP に置き換わります)。 |
| app | sample-shop-app-1 | services.app.volumes | `--volume` | `sample-shop_app-cache:/var/cache/shop` | 名前付きボリューム「sample-shop_app-cache」をコンテナの /var/cache/shop につなぎます。 |
| app | sample-shop-app-1 | services.app.tmpfs | `--tmpfs` | `/tmp:size=16m` | メモリ上の一時的な場所 (tmpfs) を /tmp に作ります。 |
| app | sample-shop-app-1 | services.app.env_file | `--env-file` | `/opt/sample-shop/env/app.env` | ファイル app.env に書かれた環境変数 (2 個) をまとめて渡します。 |
| app | sample-shop-app-1 | services.app.env_file | `--env` | `API_TOKEN=s3cr3t-token` | 環境変数 API_TOKEN に「s3cr3t-token」を設定します (env_file から読み込んだ値)。 |
| app | sample-shop-app-1 | services.app.environment | `--env` | `CACHE_HOST=cache` | 環境変数 CACHE_HOST に「cache」を設定します。 |
| app | sample-shop-app-1 | services.app.environment | `--env` | `DB_HOST=db` | 環境変数 DB_HOST に「db」を設定します。 |
| app | sample-shop-app-1 | services.app.environment | `--env` | `DB_PORT=5432` | 環境変数 DB_PORT に「5432」を設定します。 |
| app | sample-shop-app-1 | services.app.env_file | `--env` | `GREETING=Hello from version 1.0.0` | 環境変数 GREETING に「Hello from version 1.0.0」を設定します (env_file から読み込んだ値)。 |
| app | sample-shop-app-1 | services.app.environment | `--env` | `LOG_LEVEL=info` | 環境変数 LOG_LEVEL に「info」を設定します。 |
| app | sample-shop-app-1 | services.app.environment | `--env` | `SETTINGS_FILE=/etc/shop/settings.ini` | 環境変数 SETTINGS_FILE に「/etc/shop/settings.ini」を設定します。 |
| app | sample-shop-app-1 | services.app.ulimits | `--ulimit` | `nofile=4096:8192` | 資源の上限 (ulimit) nofile を 4096:8192 にします。 |
| app | sample-shop-app-1 | services.app.deploy.resources.limits.cpus | `--cpus` | `0.5` | 使える CPU を 0.5 個分までに制限します。 |
| app | sample-shop-app-1 | services.app.deploy.resources.limits.memory | `--memory` | `256m` | 使えるメモリを 256m までに制限します。超えるとコンテナ内のプロセスが強制終了 (OOM Kill) されます。 |
| app | sample-shop-app-1 | services.app.logging.driver | `--log-driver` | `json-file` | ログ (コンテナの出力) の保存方法を json-file にします。 |
| app | sample-shop-app-1 | services.app.logging.options | `--log-opt` | `max-file=3` | ログ保存の設定 max-file=3 です。 |
| app | sample-shop-app-1 | services.app.logging.options | `--log-opt` | `max-size=10m` | ログ保存の設定 max-size=10m です。 |
| app | sample-shop-app-1 | services.app.healthcheck.test | `--health-cmd` | `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"` | ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。 |
| app | sample-shop-app-1 | services.app.healthcheck.interval | `--health-interval` | `5s` | 何秒おきにチェックするか: 5s |
| app | sample-shop-app-1 | services.app.healthcheck.timeout | `--health-timeout` | `3s` | 1 回のチェックを何秒で打ち切るか: 3s |
| app | sample-shop-app-1 | services.app.healthcheck.start_period | `--health-start-period` | `5s` | 起動直後の、失敗を数えない猶予期間: 5s |
| app | sample-shop-app-1 | services.app.healthcheck.retries | `--health-retries` | `10` | 何回続けて失敗したら unhealthy (不健康) とするか: 10 回 |
| web | sample-shop-web-1 | (compose が自動で付与) | `--detach` |  | コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。 |
| web | sample-shop-web-1 | (compose が自動で付与) | `--name` | `sample-shop-web-1` | コンテナに「sample-shop-web-1」という名前を付けます。compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。 |
| web | sample-shop-web-1 | services.web.restart | `--restart` | `always` | コンテナが止まったときの再起動のルールを always にします。 |
| web | sample-shop-web-1 | services.web.networks.frontend | `--network` | `sample-shop_frontend` | ネットワーク「sample-shop_frontend」につなぎます。 |
| web | sample-shop-web-1 | (compose が自動で付与) | `--network-alias` | `web` | このネットワークの中で「web」という名前でも呼べるようにします。compose はサービス名を自動で別名にします。 |
| web | sample-shop-web-1 | services.web.ports | `--publish` | `8088:80` | ホスト (RHEL) の 8088 番ポート (TCP) に届いた通信を、コンテナの 80 番ポートへ転送します。 |
| web | sample-shop-web-1 | services.web.volumes | `--volume` | `/opt/sample-shop/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro` | ホストの /opt/sample-shop/web/nginx.conf をコンテナの /etc/nginx/conf.d/default.conf に直接つなぎます (バインドマウント・読み取り専用)。ホスト側に無ければ空のフォルダが作られます。 |
| web | sample-shop-web-1 | services.web.tmpfs | `--tmpfs` | `/var/cache/nginx` | メモリ上の一時的な場所 (tmpfs) を /var/cache/nginx に作ります。 |
| web | sample-shop-web-1 | services.web.tmpfs | `--tmpfs` | `/var/run` | メモリ上の一時的な場所 (tmpfs) を /var/run に作ります。 |
| web | sample-shop-web-1 | services.web.tmpfs | `--tmpfs` | `/tmp` | メモリ上の一時的な場所 (tmpfs) を /tmp に作ります。 |
| web | sample-shop-web-1 | services.web.labels | `--label` | `com.example.role=frontend` | コンテナに目印 (ラベル) com.example.role=frontend を付けます。 |
| web | sample-shop-web-1 | services.web.read_only | `--read-only` |  | コンテナのファイルシステムを読み取り専用にします (書けるのはボリュームや tmpfs だけ)。 |
| web | sample-shop-web-1 | services.web.cap_drop | `--cap-drop` | `NET_RAW` | Linux の特権の一部 (ケーパビリティ) NET_RAW を取り上げます。 |
| web | sample-shop-web-1 | services.web.security_opt | `--security-opt` | `no-new-privileges:true` | コンテナの中のプログラムが、setuid などで今より強い権限を持てないようにします。 |
| web | sample-shop-web-1 | services.web.logging.driver | `--log-driver` | `json-file` | ログ (コンテナの出力) の保存方法を json-file にします。 |
| web | sample-shop-web-1 | services.web.logging.options | `--log-opt` | `max-file=3` | ログ保存の設定 max-file=3 です。 |
| web | sample-shop-web-1 | services.web.logging.options | `--log-opt` | `max-size=10m` | ログ保存の設定 max-size=10m です。 |
| web | sample-shop-web-1 | services.web.stop_signal | `--stop-signal` | `SIGQUIT` | コンテナを止めるときに送る合図 (シグナル) を SIGQUIT にします。 |
| web | sample-shop-web-1 | services.web.stop_grace_period | `--stop-timeout` | `15` | 止めるとき、合図を送ってから 15 秒待っても終わらなければ強制終了 (SIGKILL) します (compose の stop_grace_period: 15s)。 |

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

- services.toolbox は profiles (debug) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile debug を付けて変換し直してください。
- STEP 16: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 18: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。
- STEP 20: 複数のネットワークを docker run 1 回でつなぐ書き方 (--network name=...,alias=...) は Docker Engine 25 以降で使えます。RHEL 9.8 で最新の docker-ce (29.x) を入れていれば問題ありません。
- STEP 25: NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。

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

### 1. コンテナ「sample-shop-web-1」を止める

コンテナ「sample-shop-web-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-web-1
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 2. コンテナ「sample-shop-app-1」を止める

コンテナ「sample-shop-app-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-app-1
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 3. コンテナ「sample-shop-migrate-1」を止める

コンテナ「sample-shop-migrate-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-migrate-1
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 4. コンテナ「sample-shop-cache-1」を止める

コンテナ「sample-shop-cache-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-cache-1
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

### 5. コンテナ「sample-shop-db-1」を止める

コンテナ「sample-shop-db-1」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。

```bash
docker stop sample-shop-db-1
```

- しくみ: docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。
- 小学生向け: 「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。

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

- しくみ: コンテナの設定と書き込み用の層を削除します。名前付きボリュームは消えません。匿名ボリュームも、-v を付けない限り残ります (compose down と同じ動き)。
- 小学生向け: 使い終わったおもちゃを分解して片付けるコマンドです。ロッカーの中身は残ります。

### 7. ネットワークを削除する

このプロジェクトで作ったネットワークを削除します (compose down と同じ)。

```bash
docker network rm sample-shop_backend sample-shop_frontend
```

- しくみ: ブリッジとファイアウォールのルール、IP アドレスの範囲の予約が片付けられます。
- 小学生向け: 使い終わった道路を片付けるコマンドです。

### 8. ボリュームを削除する (データが消えます)

名前付きボリュームを削除します (compose down -v と同じ)。データが消えるため、必要なときだけ先頭の # を外して実行してください。

```bash
# docker volume rm sample-shop_app-cache sample-shop_cache-data sample-shop_db-data
```

- しくみ: ボリュームの実体 (/var/lib/docker/volumes/<名前>) を削除します。データベースのデータなどが完全に消えるので注意してください。
- 小学生向け: ロッカーを中身ごと捨てるコマンドです。大事なものが入っていないか、よく確かめてから使います。

### 9. 作ったイメージを削除する

ビルドしたイメージ・ヘルスチェック入りイメージを削除します (compose down --rmi local と同じ)。必要なときだけ先頭の # を外して実行してください。

```bash
# docker image rm \
#   sample-shop-cache:with-healthcheck \
#   sample-shop/app:1.0.0 \
#   sample-shop-web:with-healthcheck
```

- しくみ: イメージの名前 (タグ) を外し、どこからも使われなくなったレイヤーを削除してディスクを空けます。
- 小学生向け: もう使わないおもちゃのもとを捨てるコマンドです。

