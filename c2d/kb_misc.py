"""解説用の知識ベース (3): はじめに・全体像・用語集・歴史年表・RHEL 9.8 の準備・注意点。"""

INTRO = [
    ("この資料は何？",
     "docker compose は、compose ファイル (compose.yaml) に書かれた「たくさんのコンテナをどう動かすか」という計画書を読み、"
     "Docker Engine に 1 つずつ命令を出して、まとめて起動してくれる道具です。この資料は、compose が裏側で出している命令を、"
     "人が読める docker コマンドに 1 つずつ書き出したものです。コマンドを上から順に実行すると、docker compose up -d とまったく同じ"
     "コンテナ・ネットワーク・ボリュームができあがります。"),
    ("なぜ docker コマンドに直すの？",
     "① compose を入れられない・使えない環境 (サーバーの運用ルール、最小構成のサーバーなど) でも同じ構成を動かせる。"
     "② compose が裏で何をしているかが 1 行ずつ見えるので、トラブルの原因を探しやすい。"
     "③ 手順書や作業記録として、どの操作で何が起きるかを説明しやすい (審査・引き継ぎ・教育)。"
     "④ ECS のタスク定義や Kubernetes など、ほかの仕組みに移すときに「必要な設定の一覧」として使える。"),
    ("どうやって正しさを確かめたの？",
     "このツールは、docker compose (v5.5.1) で起動した環境と、生成した docker コマンドで起動した環境を docker inspect で比べ、"
     "環境変数・マウント・ネットワーク別名・ヘルスチェック・再起動ルール・資源の制限などが一致することを確認しながら作っています。"
     "compose ファイルの解釈は、docker compose が使える環境では docker compose config (compose 自身の解釈) をそのまま使い、"
     "使えない環境では同じ規則を再現した内蔵の解釈を使います。tools/compare_env.py を使うと、あなたの RHEL でも同じ比較ができます。"),
    ("小学生向けに言うと",
     "compose は「遠足のしおり」のようなもので、だれが・いつ・どこへ・何を持って行くかが 1 冊にまとまっています。"
     "先生 (compose) は、しおりを見ながらバスの運転手さん (Docker) に「まずこのバスを出して、次にこっち」と 1 つずつお願いしています。"
     "この資料は、先生のお願いの言葉を全部書き出したものです。だから、先生がいなくても、書いてあるとおりにお願いすれば同じ遠足ができます。"),
]

ARCHITECTURE = (
    "【Docker が動くしくみの全体像】\n"
    "あなた → docker コマンド (クライアント) → /var/run/docker.sock (UNIX ソケット) → dockerd (Docker Engine) → containerd → "
    "containerd-shim-runc-v2 → runc → Linux カーネル (namespace・cgroup・overlayfs・netfilter) → コンテナ (囲いの中で動く、ふつうのプロセス)\n\n"
    "・docker コマンド: あなたのお願いを Docker Engine API (HTTP + JSON) の形に変えて送るリモコン。\n"
    "・dockerd: イメージ・ネットワーク・ボリューム・ログ・ヘルスチェック・再起動などを管理する本体 (管理人さん)。\n"
    "・containerd: コンテナの一生 (作る・動かす・止める) を管理する部品。2017 年に CNCF へ寄贈され、Kubernetes でも使われています。\n"
    "・runc: OCI の仕様に沿って、カーネルの機能を組み合わせてコンテナを作る小さなプログラム (大工さん)。\n"
    "・docker compose: compose ファイルを読み、docker コマンドと同じ API を順番に呼ぶ道具 (しおりを読む先生)。\n\n"
    "compose が up でしていること: ① compose ファイルを読み、変数 ${...} を展開して設定を確定 → ② ネットワークとボリュームを作成 → "
    "③ 必要なイメージを取得・ビルド → ④ depends_on の順番どおりにコンテナを作成・起動 (healthy などの条件を待ち合わせ)。"
    "この資料の手順も、まったく同じ順番になっています。"
)

PHASES = [
    ("準備", "作業フォルダへ移動し、Docker が動いているかを確認します。"),
    ("ネットワーク", "コンテナどうしが名前で話せる仮想ネットワークを作ります。コンテナより先に必要です。"),
    ("ボリューム", "データを残しておく保存場所を作ります。コンテナより先に必要です。"),
    ("イメージ取得", "手元に無いイメージだけをダウンロードします (compose の pull_policy: missing と同じ)。"),
    ("イメージ作成", "build: があるサービスのイメージを Dockerfile から作ります。"),
    ("ヘルスチェック入りイメージ", "exec 形式のヘルスチェックを compose と同じにするための派生イメージを作ります (必要なときだけ)。"),
    ("起動", "depends_on の順番どおりにコンテナを起動します。healthy や正常終了を待つ設定があれば、その待ち合わせもします。"),
    ("確認", "全部のコンテナの状態を一覧で確認します。"),
]

RHEL_SETUP = [
    ("1. 古い docker / podman を外す",
     "sudo dnf remove docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine podman runc",
     "RHEL に最初から入っていることがある podman や runc は、Docker 公式パッケージとぶつかるため先に外します (入っていなければ何も起きません)。"),
    ("2. Docker のリポジトリを登録する",
     "sudo dnf -y install dnf-plugins-core\nsudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo",
     "Docker 社が配っている RHEL 用のパッケージ置き場を、dnf に教えます。"),
    ("3. Docker Engine を入れる",
     "sudo dnf install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
     "本体 (docker-ce)、リモコン (docker-ce-cli)、containerd、BuildKit (buildx)、compose をまとめて入れます。GPG 鍵の確認を求められたら、"
     "指紋が 060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35 であることを確かめて受け入れます。"),
    ("4. 起動して、自動起動を有効にする",
     "sudo systemctl enable --now docker\nsudo docker run --rm hello-world",
     "Docker Engine を起動し、サーバーの再起動後も自動で動くようにします。hello-world が表示されれば成功です。"),
    ("5. (任意) sudo なしで使う",
     "sudo usermod -aG docker $USER\n# いったんログアウトしてログインし直す",
     "docker グループに入ると sudo なしで docker を使えます。ただし root と同じくらい強い権限になるので、入れる人は最小限にします。"),
    ("6. プロジェクトのファイルを置く",
     "scp -r ./myproject user@rhel-server:/opt/myproject\n# または rsync -av ./myproject/ user@rhel-server:/opt/myproject/",
     "compose ファイルだけでなく、Dockerfile・設定ファイル・env ファイルなど、compose ファイルから参照されているものを同じフォルダ構成で置きます。"
     "Windows で編集したファイルは改行コードが CRLF になっていることがあるので、シェルスクリプトは LF にそろえます (dos2unix など)。"),
    ("7. (必要なら) プロキシ",
     "sudo mkdir -p /etc/systemd/system/docker.service.d\nsudo vi /etc/systemd/system/docker.service.d/http-proxy.conf\n"
     "#   [Service]\n#   Environment=\"HTTP_PROXY=http://proxy.example.com:8080\" \"HTTPS_PROXY=http://proxy.example.com:8080\" \"NO_PROXY=localhost,127.0.0.1\"\n"
     "sudo systemctl daemon-reload && sudo systemctl restart docker",
     "イメージのダウンロードは dockerd が行うので、dockerd にプロキシを設定します。"),
]

RHEL_NOTES = [
    ("cgroup v2", "RHEL 9 系は cgroup v2 が標準です。Docker 29 も cgroup v2 が推奨です (v1 は非推奨)。--memory-swappiness など v1 専用の設定は無視されます。"),
    ("SELinux", "docker-ce の標準設定ではコンテナに SELinux ラベルが付かず、バインドマウントはそのまま使えます。/etc/docker/daemon.json で \"selinux-enabled\": true にしている場合は、"
                "ホストのフォルダをつなぐ volumes に :z (共有) や :Z (専用) が必要になります (compose でも同じです)。"),
    ("firewalld", "Docker は firewalld に docker という zone を作り、自分のルールを管理します。firewall-cmd --reload の後にコンテナの通信がおかしいときは sudo systemctl restart docker を実行します。"),
    ("ディスク容量", "イメージ・コンテナ・ボリュームは /var/lib/docker (containerd image store の場合は /var/lib/containerd も) に保存されます。df -h と docker system df で容量を確認してください。"),
    ("文字コード", "この手順の txt ファイルは UTF-8 (BOM なし)・LF 改行です。日本語のコメントが文字化けする場合は、ターミナルの文字コードを UTF-8 にしてください (LANG=ja_JP.UTF-8 など)。"),
    ("時刻・タイムゾーン", "コンテナの時刻はホストと同じ時計を使いますが、タイムゾーンはイメージの設定 (多くは UTC) です。TZ 環境変数や /etc/localtime のマウントで合わせます。"),
    ("Podman との違い", "RHEL 標準の Podman にも docker 互換のコマンドがありますが、デーモンを持たない・rootless が標準などの違いがあります。この手順は Docker Engine (docker-ce) を前提にしています。"),
]

LIMITATIONS = [
    ("ヘルスチェックの exec 形式", "docker run の --health-cmd はシェル形式 (/bin/sh -c) しか書けないため、compose の test: [\"CMD\", ...] は HEALTHCHECK を焼き込んだ派生イメージ "
     "(<プロジェクト>-<サービス>:with-healthcheck) で再現しています。動作は同じですが、docker ps に表示されるイメージ名が変わります。--healthcheck-exec shell を指定すると派生イメージを作らず --health-cmd で代用します。"),
    ("compose のラベル", "compose はコンテナに com.docker.compose.* のラベルを付けて管理しています。この手順では既定で付けないため、docker compose ps / down の対象にはなりません (片付けは down 用の txt で行います)。"
     "--compose-labels を付けると同じラベルを付けますが、compose の config-hash は付けられないため、その後に compose up すると作り直しになります。"),
    ("起動の並列・順番", "compose は依存関係の無いサービスを同時に起動しますが、この手順は 1 つずつ順番に起動します。できあがる状態は同じです。"),
    ("待ち合わせで失敗したとき", "compose は依存先が unhealthy になったり失敗したりすると、そこで起動をやめます。この手順の待ち合わせは「NG」と表示して待つのをやめますが、貼り付けた残りのコマンドは続いてしまいます。NG が出たら、その先へ進まずに原因を確認してください。"),
    ("depends_on の restart: true", "compose の restart: true (依存先を再起動したら、こちらも再起動する) は compose の操作の中だけの機能のため、docker コマンドでは再現していません。"),
    ("pull_policy の daily / weekly / every_N", "「一定時間たったら取り直す」機能は docker に無いため、「無いときだけ取得」で代用しています。"),
    ("変数の展開", "${VAR} や .env の値は、変換したときの値で展開済みです。.env を変えたときは、変換し直してください。"),
    ("2 回目の実行", "compose up は既にあるコンテナとの差分を見て作り直しますが、docker コマンドは同じ名前があるとエラーになります。2 回目は後片付けをしてから実行してください。"),
    ("再現できないもの", "provider (外部の仕組みに任せるサービス)・models (AI モデル)・develop / watch (開発用の自動同期)・Swarm 専用の deploy 設定 (placement / update_config / mode: global など) は、docker コマンドだけでは再現できない (または compose も単体では使わない) ため、対象外としています。"),
]

GLOSSARY = [
    ("コンテナ", "container", "囲いの中で動くプログラム (プロセス)。名前空間で周りが見えないようにし、cgroup で使える量を制限している。仮想マシンと違い OS を丸ごと起動しないので軽くて速い。", "マンションの中の 1 つのお部屋。住人 (プログラム) はその部屋の中だけで暮らす。"),
    ("イメージ", "image", "コンテナのもとになる、ファイル一式と設定 (起動するコマンド・環境変数など) をまとめたもの。読み取り専用で、何個でも同じコンテナを作れる。", "お部屋セット (家具付きの部屋の型)。冷凍お弁当のように、いつでも同じものを用意できる。"),
    ("レイヤー", "layer", "イメージを作る「差分の層」。Dockerfile の命令ごとにでき、同じ層は複数のイメージで共有される。", "透明なシートを何枚も重ねて 1 枚の絵にするときの、それぞれのシート。"),
    ("Dockerfile", "ドッカーファイル", "イメージの作り方を書いたテキストファイル。FROM・RUN・COPY・CMD などの命令を上から実行する。", "料理のレシピ。"),
    ("ビルドコンテキスト", "build context", "docker build に渡す材料フォルダ。COPY / ADD はこの中のファイルだけ使える。.dockerignore で除外できる。", "料理の材料を入れた箱。"),
    ("BuildKit", "ビルドキット", "Docker 23.0 から標準になったビルドエンジン。並列実行・キャッシュ・秘密の受け渡しなどが得意。", "腕のいい料理人。"),
    ("Docker Bake", "ベイク", "複数のビルドをまとめて定義・実行する BuildKit の仕組み。compose v5 はビルドをこれに任せている。", "たくさんの料理をまとめて作る段取り表。"),
    ("レジストリ", "registry", "イメージを保管・配布するサーバー。Docker Hub、Amazon ECR、社内レジストリなど。", "部品セットの倉庫。"),
    ("タグ / ダイジェスト", "tag / digest", "タグ (例: 8.4.7, latest) はイメージに付ける呼び名で、付け替えられる。ダイジェスト (sha256:...) は中身から計算した番号で、絶対に変わらない。", "タグは「今月のおすすめ」のような呼び名、ダイジェストは商品の製造番号。"),
    ("Docker Engine (dockerd)", "ドッカーエンジン", "コンテナ・イメージ・ネットワーク・ボリュームを管理する本体のサービス (デーモン)。systemctl で起動する。", "マンションの管理人さん。"),
    ("containerd", "コンテナーディー", "コンテナの一生 (作る・動かす・止める) とイメージの保存を担当する部品。Kubernetes でも使われる。", "現場監督。"),
    ("runc", "ランシー", "OCI の仕様どおりにコンテナを作る小さなプログラム。カーネルに名前空間や cgroup を頼む。", "お部屋を作る大工さん。"),
    ("OCI", "Open Container Initiative", "コンテナのイメージ形式・実行方法・配布方法の標準を決める団体 (2015 年設立)。Docker・Podman・Kubernetes が同じイメージを使えるのはこのおかげ。", "部品の大きさをそろえる「規格」を決める会議。"),
    ("Docker Engine API", "API", "docker コマンドと dockerd が話すための決まり (HTTP + JSON)。/var/run/docker.sock を通して送られる。", "リモコンと本体が話すための合言葉。"),
    ("UNIX ソケット", "UNIX domain socket", "同じコンピューターの中のプログラムどうしが通信するための、ファイルの形をした出入口。", "家の中だけで使う糸電話。"),
    ("compose ファイル", "compose.yaml", "複数のコンテナの設定 (サービス・ネットワーク・ボリューム) を YAML で書いたファイル。", "遠足のしおり。"),
    ("Docker Compose", "ドッカーコンポーズ", "compose ファイルを読んで、まとめて起動・停止する道具。今は docker compose というプラグイン (v5)。", "しおりを読んで、みんなに指示を出す先生。"),
    ("プロジェクト名", "project name", "compose が作る物の名前の頭に付ける名前。name:、-p、またはフォルダ名から決まる。", "クラスの名前。名札に「1 組」と付けるようなもの。"),
    ("サービス", "service", "compose ファイルの services: の下の 1 つ 1 つ。同じ設定のコンテナのグループ (レプリカが 1 つ以上)。", "「給食係」のような係の名前。"),
    ("ネットワーク (ブリッジ)", "network / bridge", "コンテナ用の仮想 LAN。bridge はホストの中にソフトウェアのスイッチを作る標準の種類。", "建物の中だけの内線電話網。"),
    ("veth", "virtual ethernet", "2 つで 1 組の仮想 LAN ケーブル。片方をコンテナ、片方をブリッジにつなぐ。", "部屋と交換機をつなぐ電話線。"),
    ("内蔵 DNS", "embedded DNS", "ユーザー定義ネットワークで、コンテナ名やサービス名を IP アドレスに変換する Docker の仕組み (127.0.0.11)。", "名前を言えば電話をつないでくれる交換手さん。"),
    ("ネットワーク別名", "network alias", "そのネットワークの中だけで使える、コンテナのもう 1 つの名前。compose はサービス名を必ず別名にする。", "あだ名。"),
    ("ポート公開", "publish / ports", "ホストのポートに来た通信を、コンテナのポートへ転送すること。", "正面玄関の窓口からお部屋への道案内。"),
    ("NAT / DNAT / MASQUERADE", "ナット", "通信の宛先や送り主のアドレスを書き換える仕組み。Docker は外への通信を MASQUERADE、ポート公開を DNAT で実現する。", "郵便物の宛名を、建物の住所から部屋番号へ書き換える係。"),
    ("iptables / nftables", "アイピーテーブルズ", "Linux のファイアウォール・アドレス変換の設定の仕組み。RHEL 9 では iptables コマンドも内部で nftables を使う。", "建物の出入口の警備員さんのルールブック。"),
    ("ボリューム", "volume", "Docker が管理するデータの保存場所。コンテナを消しても残る。名前付き (named) と、名前の無い匿名 (anonymous) がある。", "部屋の外にある貸しロッカー。"),
    ("バインドマウント", "bind mount", "ホストのフォルダやファイルを、そのままコンテナの中の場所に見せる仕組み。", "家の引き出しを、部屋の中から直接開けられるようにする窓。"),
    ("tmpfs", "テンプエフエス", "メモリの上に作る一時的なファイル置き場。速いが、止めると消える。", "ホワイトボード。"),
    ("overlayfs", "オーバーレイ", "読み取り専用の層を重ね、その上に書き込み用の層を足して 1 つのフォルダに見せる Linux の仕組み。", "透明シートを重ねて、一番上のシートにだけ書き込むやり方。"),
    ("名前空間", "namespace", "プロセスから見える範囲 (プロセス・ネットワーク・ファイル・ホスト名など) を分ける Linux の仕組み。", "部屋の壁。"),
    ("cgroup (v2)", "シーグループ", "CPU・メモリ・プロセス数などの使用量を数え、上限を決める Linux の仕組み。RHEL 9 は v2 が標準。", "電気・水道のメーターとブレーカー。"),
    ("capabilities", "ケーパビリティ", "root の強い権限を 40 個ほどに細かく分けたもの。Docker は標準で 14 個だけ許可する。", "マンションの合鍵を種類ごとに分けたもの。"),
    ("seccomp", "セックコンプ", "プロセスが使ってよいシステムコール (カーネルへのお願い) を制限する仕組み。", "「この呪文は使ってはいけません」リスト。"),
    ("SELinux", "エスイーリナックス", "RHEL のアクセス制御の仕組み。ファイルやプロセスにラベル (名札) を付けて、許可された組み合わせだけを通す。", "名札の色で、入っていい部屋を決めるルール。"),
    ("PID 1 / init", "ピッドワン", "コンテナの中で最初に動くプロセス。シグナルの受け取りやゾンビプロセスの後片付けの責任がある。--init で小さなお世話係 (tini) を置ける。", "部屋のリーダー。"),
    ("シグナル", "signal (SIGTERM / SIGKILL)", "プロセスへの合図。SIGTERM は「終わってください」、SIGKILL は「強制終了」。", "「そろそろ帰る時間ですよ」と「もう電気を消します」。"),
    ("終了コード", "exit code", "プログラムが終わるときに返す番号。0 は成功、それ以外は失敗。137 は SIGKILL (メモリ不足など) で止められた印。", "テストの結果の点数のような返事。0 点が「うまくいった」の合図。"),
    ("ヘルスチェック", "healthcheck", "コンテナの中で定期的にテストのコマンドを実行し、動いているだけでなく「ちゃんと応答できるか」を調べる仕組み。starting → healthy / unhealthy。", "「元気？」と声をかける見回り。"),
    ("depends_on", "ディペンズオン", "サービスの起動順番と、待ち合わせの条件 (started / healthy / completed_successfully) を決める compose の設定。", "「準備ができたら次の人が出発」というルール。"),
    ("環境変数", "environment variable", "プログラムに渡す「名前=値」の設定。データベースの接続先などを、イメージを作り直さずに変えられる。", "お部屋に置く設定メモ。"),
    (".env と変数展開", "dotenv / interpolation", "compose ファイルの ${VAR} を、.env ファイルや OS の環境変数の値で置き換える仕組み。", "しおりの「○○」の空欄に、名簿の名前を書き込むこと。"),
    ("ラベル", "label", "コンテナなどに付ける目印 (キー=値)。動作には影響しない。", "シール。"),
    ("ログドライバー", "logging driver", "コンテナの画面出力をどこへ保存するかを決める部品 (json-file、journald など)。", "日記帳の種類。"),
    ("restart ポリシー", "restart policy", "コンテナが止まったときに自動で起動し直すかどうかのルール。", "転んだら起こしてあげる約束。"),
    ("configs / secrets", "コンフィグ / シークレット", "設定ファイル・秘密情報をコンテナに渡す compose の仕組み。ファイルからはバインドマウント、中身の直書きからはコピーで渡される。", "配られる説明書と、封筒に入った秘密の手紙。"),
    ("init コンテナ (pre_start)", "イニットコンテナ", "本番のコンテナを起動する前に、準備作業だけをする使い捨てのコンテナ。compose 5.3 から。", "開店前に来る準備係さん。"),
    ("ライフサイクルフック", "post_start / pre_stop", "起動直後・停止直前に、コンテナの中で実行するコマンド。compose 2.30 から。", "開店直後・閉店直前のお決まりの作業。"),
    ("profiles", "プロファイル", "指定したときだけ起動するサービスのグループ (デバッグ用・試験用など)。", "「雨の日だけ」の特別メニュー。"),
    ("ヒアドキュメント", "here document", "<<'終わりの印' から 終わりの印 までの複数行を、コマンドへの入力として渡す bash の書き方。'...' で囲むと $ などを展開しない。", "長い手紙を、封筒ごと手渡しする方法。"),
    ("履歴展開", "history expansion", "bash で ! を使って過去のコマンドを呼び出す機能。set +H で止められる。", "「さっきのと同じ！」と言うと前の注文を繰り返してくれる機能。"),
    ("distroless", "ディストロレス", "アプリを動かすのに必要な最低限のファイルだけを入れ、シェル (/bin/sh) すら入れないイメージ。攻撃されにくい。", "必要な道具しか置いていない、すっきりした部屋。"),
    ("RHEL", "レル", "Red Hat Enterprise Linux。企業向けの Linux。9.8 は 2026 年 5 月に公開された 9 系の更新版。", "会社で使う、長く安心して使える建物。"),
    ("Podman", "ポッドマン", "Red Hat が中心に開発する、docker と互換のあるコンテナの道具。デーモンを持たない。RHEL 8 以降の標準。", "別の会社の管理人さん。やり方は似ている。"),
    ("docker-ce", "Docker Community Edition", "Docker 社が配布する無料の Docker Engine のパッケージ名。", "管理人さんの派遣元。"),
]

TIMELINE = [
    ("1979 年", "Unix V7 に chroot が登場", "プログラムに見せるフォルダの範囲を制限できるようになった (コンテナのいちばん古いご先祖さま)。"),
    ("1982 年", "BSD に chroot が入る", "Unix 系 OS に広まる。"),
    ("2000 年 3 月", "FreeBSD 4.0 に jail が登場", "ファイルだけでなく、プロセスやネットワークも分けられる「囲い」ができた。"),
    ("2001 年", "Linux-VServer", "Linux でも 1 台を区切って使う仕組みが作られる。"),
    ("2002 年", "Linux 2.4.19 に mount 名前空間", "Linux の名前空間のはじまり。"),
    ("2004〜2005 年", "Solaris Zones (Solaris 10)", "商用 OS で本格的なコンテナが使われ始める。"),
    ("2005 年", "OpenVZ", "レンタルサーバーなどで Linux のコンテナが普及。"),
    ("2006 年", "Google が process containers を開発", "CPU やメモリの使用量を制限する仕組み。のちの cgroups。"),
    ("2008 年 1 月", "Linux 2.6.24 に cgroups が入る", "資源の制限が Linux の標準機能に。"),
    ("2008 年", "LXC (Linux Containers) 登場", "名前空間と cgroups を組み合わせた、Linux のコンテナの道具。"),
    ("2013 年 2 月", "Linux 3.8 で user 名前空間が完成", "必要な名前空間がひととおりそろう。"),
    ("2013 年 3 月", "Docker 公開 (PyCon での発表)", "dotCloud 社の Solomon Hykes さんが発表。イメージという配りやすい形で大人気に。"),
    ("2013 年 12 月", "Fig 公開 (Orchard 社)", "複数コンテナを 1 つのファイルで定義する道具。compose のご先祖さま。"),
    ("2014 年 3 月", "Docker 0.9 で libcontainer", "LXC に頼らず、Go で直接カーネルを操作するように。"),
    ("2014 年 6 月", "Docker 1.0 / Docker Hub 公開", "本番で使える版になり、イメージの共有場所ができる。"),
    ("2014 年 7 月", "Docker 社が Orchard (Fig) を買収", "Fig が Docker Compose になっていく。"),
    ("2014 年 10 月", "Docker 1.3: docker exec / docker create", "動いているコンテナの中で操作できるように。"),
    ("2015 年 2 月", "Docker Compose 1.1 (Fig から改名)", "docker-compose コマンドの時代 (Python 製の v1)。"),
    ("2015 年 4 月", "Docker 1.6 / Registry API v2", "中身のハッシュでレイヤーを管理する、今のイメージ配布の方式に。"),
    ("2015 年 6 月", "OCI 設立、runc 寄贈", "コンテナの標準化が始まる。"),
    ("2015 年 8 月", "Docker 1.8: docker cp でコンテナへコピー", "ホスト → コンテナのファイルコピーが可能に。"),
    ("2015 年 11 月", "Docker 1.9: docker network / docker volume", "ユーザー定義ネットワークと名前付きボリュームが登場。--link の時代が終わる。"),
    ("2016 年 2 月", "Docker 1.10: 内蔵 DNS / Compose ファイル形式 v2", "名前で呼び合うのが当たり前に。compose に networks: と volumes:。"),
    ("2016 年 3 月", "Linux 4.5 で cgroup v2", "新しい資源管理の仕組み。"),
    ("2016 年 7 月", "Docker 1.12: HEALTHCHECK / Swarm mode", "コンテナの健康状態を調べられるように。"),
    ("2016 年 11 月", "Compose ファイル形式 v2.1: depends_on の condition", "service_healthy を待てるように。"),
    ("2017 年 1 月", "Docker 1.13: --init / Compose ファイル形式 v3", "init (tini) の組み込み。v3 は Swarm 向けで condition が一度消える。"),
    ("2017 年 3 月", "containerd を CNCF に寄贈 / Docker CE・EE", "バージョンが 17.03 のような「年.月」に。"),
    ("2017 年 5〜6 月", "Docker 17.05 マルチステージビルド / 17.06 --mount", "小さなイメージ作りと、読みやすいマウントの書き方。"),
    ("2017 年 7 月", "OCI Image Specification 1.0", "イメージの形式が業界標準に。"),
    ("2018 年 11 月", "Docker 18.09: BuildKit を試せるように", "速く安全な新しいビルドの始まり。"),
    ("2019 年 5 月", "RHEL 8 公開 (Podman が標準)", "Red Hat は docker の代わりに Podman / Buildah / Skopeo を採用。"),
    ("2019 年 7 月", "Docker 19.03: --gpus / buildx", "GPU を簡単に使えるように。"),
    ("2020 年 4 月", "Compose Specification 公開", "compose ファイルの書き方がオープンな仕様に。v2/v3 の区別がなくなる方向へ。"),
    ("2020 年 11 月", "Docker Hub の回数制限開始", "ミラーや別のレジストリの利用が広がる。"),
    ("2020 年 12 月", "Docker 20.10: cgroup v2 対応・rootless 正式版", "RHEL 9 世代の Linux で動く準備が整う。"),
    ("2021 年 4 月", "Compose 1.29: service_completed_successfully", "「準備用のサービスが成功してから起動」ができるように。"),
    ("2021 年 5〜6 月", "OCI Distribution Spec 1.0 / runc 1.0", "配布方法と実行の部品が安定版に。"),
    ("2022 年 4 月", "Compose v2 (Go 製・docker compose) 正式版", "docker-compose から docker compose へ。"),
    ("2022 年 5 月", "RHEL 9.0 公開", "cgroup v2 が標準に。"),
    ("2023 年 2 月", "Docker 23.0: BuildKit が標準", "docker build = buildx build に。"),
    ("2023 年 7 月", "Compose v1 のサポート終了", "Python 製の docker-compose の更新が終わる。"),
    ("2024 年 1 月", "Docker 25.0: 複数ネットワーク同時接続・start-interval", "1 回の docker run で複数のネットワークへ。"),
    ("2024 年 3 月", "Docker 26.0: volume-subpath", "ボリュームの一部だけをつなげるように。"),
    ("2024 年 10 月", "Compose 2.30: post_start / pre_stop フック", "起動直後・停止直前の作業を書けるように。"),
    ("2025 年 2 月", "Docker 28.0: gw-priority など", "複数ネットワークの出口を選べるように。"),
    ("2025 年 5 月", "RHEL 10 公開", "RHEL の新しい世代。"),
    ("2025 年 11 月", "Docker Engine 29.0", "containerd image store が新規の標準・nftables 試験対応・API 1.44 未満を廃止・cgroup v1 非推奨。"),
    ("2025 年 12 月", "Docker Compose v5.0", "v3 / v4 を飛ばして v5 に。SDK として使えるように・ビルドは Bake に一本化。"),
    ("2026 年 5 月", "RHEL 9.8 / 10.2 公開", "この資料が前提にしている RHEL のバージョン。"),
    ("2026 年 7 月", "Compose 5.3: pre_start (init コンテナ)", "本番の前の準備用コンテナを正式に書けるように。"),
    ("2026 年 8〜10 月", "Compose 5.4〜5.6 / Docker 29.8〜29.9", "状態の突き合わせ (reconciliation) の改良など。2026 年 10 月時点の最新は Compose 5.6.0 (10/2)、Docker Engine 29.9.0 (10/8)。"),
]

GENERIC_MAPPING = [
    ("image", "docker run の最後のイメージ名", "docker pull でイメージを用意"),
    ("build.*", "docker build --file/--target/--build-arg/--tag ...", "イメージ名は image、無ければ <プロジェクト>-<サービス>"),
    ("container_name", "--name", "無ければ <プロジェクト>-<サービス>-<番号>"),
    ("command", "イメージ名の後ろの引数", "文字列は compose と同じ規則で単語に分割"),
    ("entrypoint", "--entrypoint (1 語目) + 残りは引数", ""),
    ("environment / env_file", "--env / --env-file", "${VAR} は展開済み。compose と読み方が同じ env ファイルだけ --env-file"),
    ("ports", "--publish", ""),
    ("expose", "--expose", ""),
    ("volumes (短い書き方)", "--volume", "ホスト側が無ければ作成 (compose と同じ)"),
    ("volumes (長い書き方・オプションあり)", "--mount", ""),
    ("tmpfs", "--tmpfs", ""),
    ("networks", "--network / --network-alias (複数なら --network name=...,alias=...)", "サービス名を必ず別名に"),
    ("network_mode", "--network host / none / container:<名前>", "service:<名前> は container:<コンテナ名>"),
    ("depends_on", "起動の順番 + 待ち合わせのループ / docker wait", "condition に合わせて待つ"),
    ("healthcheck", "--health-cmd/--health-interval/... または派生イメージ", "CMD (exec 形式) は派生イメージ"),
    ("restart / deploy.restart_policy", "--restart", ""),
    ("deploy.resources.limits / reservations", "--cpus / --memory / --pids-limit / --memory-reservation / --gpus", ""),
    ("logging", "--log-driver / --log-opt", ""),
    ("labels / label_file", "--label", ""),
    ("user / group_add / working_dir", "--user / --group-add / --workdir", ""),
    ("cap_add / cap_drop / security_opt / privileged / read_only", "--cap-add / --cap-drop / --security-opt / --privileged / --read-only", ""),
    ("ulimits / sysctls", "--ulimit / --sysctl", ""),
    ("extra_hosts / dns / dns_search / dns_opt", "--add-host / --dns / --dns-search / --dns-option", ""),
    ("init / stop_signal / stop_grace_period", "--init / --stop-signal / --stop-timeout", "stop_grace_period は秒に変換"),
    ("secrets / configs (file)", "--mount type=bind,...,readonly", "secrets は /run/secrets/<名前>"),
    ("secrets / configs (environment / content)", "docker create → docker cp → docker start", ""),
    ("pre_start", "docker create → docker run --rm --volumes-from → docker start", ""),
    ("post_start / pre_stop", "docker exec", ""),
    ("profiles", "(有効なサービスだけを変換)", ""),
    ("scale / deploy.replicas", "番号違いのコンテナを複数作成", ""),
]
