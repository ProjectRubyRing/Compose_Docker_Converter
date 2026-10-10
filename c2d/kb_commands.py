"""解説用の知識ベース (1): コマンドごとの説明。

各項目のキー:
    title      見出し
    syntax     書き方
    oneline    ひとことで
    how        実行のしかた (コピー & ペーストの方法・成功/失敗の見分け方)
    meaning    コマンドの意味 (何をするか)
    principle  しくみ (動作原理・裏側で起きていること)
    image      動作イメージ (たとえ話)
    history    歴史と背景 (いつ・なぜ生まれたか)
    kids       小学生向けのまとめ
    rhel       RHEL 9.8 で気をつけること
"""

# 資料全体で使う「たとえ」の世界:
#   ホスト (RHEL のサーバー)   = 大きなマンション
#   Docker Engine (dockerd)    = マンションの管理人さん
#   docker コマンド            = 管理人さんへのお願いを伝えるリモコン
#   イメージ                   = 家具や道具が全部そろった「お部屋セット」(冷凍保存のお弁当のようなもの)
#   コンテナ                   = 実際に用意されたお部屋 (そこでプログラムという住人が暮らす)
#   ネットワーク               = 建物の中だけの内線電話網と電話帳
#   ボリューム                 = お部屋の外にある貸しロッカー (部屋を片付けても中身が残る)

COMMANDS = {}

COMMANDS["docker version"] = {
    "title": "docker version ― Docker が使えるかを確かめる",
    "syntax": "set +H / cd <プロジェクトのフォルダ> / docker version",
    "oneline": "docker コマンド (リモコン) と Docker Engine (本体) の両方が動いているかを確かめます。",
    "how": (
        "この STEP のかたまりをそのままコピーして、ターミナル (SSH でログインした画面) に貼り付け、Enter を押します。"
        "画面に「Client:」と「Server:」の 2 つの欄が表示され、それぞれに Version が出れば成功です。\n"
        "・Server の欄で「Cannot connect to the Docker daemon at unix:///var/run/docker.sock」と出たら、Docker Engine が止まっています。"
        "sudo systemctl enable --now docker で起動してください。\n"
        "・「permission denied while trying to connect to the Docker daemon socket」と出たら、権限が足りません。"
        "sudo を付けるか、sudo usermod -aG docker <ユーザー名> を実行してログインし直してください。"
    ),
    "meaning": (
        "set +H は bash の「履歴展開」をオフにします。履歴展開とは、! で始まる文字 (例: !! や !abc) を過去に打ったコマンドへ"
        "自動で置き換える便利機能ですが、パスワードなどに ! が入っていると勝手に置き換わり、"
        "「event not found」というエラーになります。貼り付け事故を防ぐため、最初に止めておきます"
        " (bash ファイル名 でスクリプトとして実行するときは、もともとオフなので影響はありません)。\n"
        "cd は「作業するフォルダ (カレントディレクトリ)」を移動するコマンドです。compose は compose ファイルのあるフォルダを"
        "基準に相対パス (./conf など) を解釈するので、同じ場所に移動しておきます。\n"
        "docker version は、docker コマンド自身 (クライアント) と、裏で動いている Docker Engine (サーバー = dockerd) の"
        "バージョンや API バージョン、Go のバージョン、OS などを表示します。"
    ),
    "principle": (
        "docker コマンドは、それだけではコンテナを動かせません。実際の仕事は Docker Engine (dockerd というサービス) が行い、"
        "docker コマンドは dockerd へ「お願い」を送るリモコンです。お願いは HTTP という Web と同じ形式で、"
        "/var/run/docker.sock という「UNIX ドメインソケット」(同じコンピューターの中だけで使う電話線のようなファイル) を通して送られます。\n"
        "docker version を実行すると、docker コマンドは dockerd に「GET /version」というお願いを送り、dockerd は JSON (データの書き方の一つ) で"
        "自分のバージョンを返します。このとき、クライアントとサーバーは「お互いが話せる API バージョン」を確認し合います (API バージョンのネゴシエーション)。"
        "Docker Engine 29 (2025 年 11 月) からは、API バージョン 1.44 未満 (Docker 25 より古い docker コマンド) からの接続は受け付けなくなりました。\n"
        "さらに裏側では、dockerd → containerd (コンテナの一生を管理する部品) → containerd-shim-runc-v2 → runc (実際にコンテナを作る小さなプログラム) → "
        "Linux カーネル、というように仕事がリレーされます。docker version の Server 欄に containerd や runc のバージョンも表示されるのはこのためです。"
    ),
    "image": (
        "テレビのリモコン (docker コマンド) と、テレビ本体 (Docker Engine) の関係です。リモコンのボタンを押しても、"
        "本体の電源が入っていなければ何も起きません。docker version は「リモコンの電池は入っているか」「本体の電源は入っているか」"
        "「リモコンと本体の電波は届いているか」をまとめて確かめるテストボタンのようなものです。"
    ),
    "history": (
        "Docker は 2013 年 3 月、dotCloud という会社 (のちの Docker 社) の Solomon Hykes さんが、プログラミング言語 Python の"
        "国際会議 PyCon の 5 分間の発表で初めて世に出し、同時にオープンソースとして公開しました。"
        "当時は「サーバーごとに環境が違ってアプリが動かない」という悩みが大きく、"
        "「アプリと必要なものを丸ごと箱詰めして、どこでも同じように動かす」という考えが一気に広まりました。\n"
        "最初の Docker は 1 つのプログラムがリモコンと本体を兼ねていましたが、2016 年に containerd、2015 年に runc が切り出され、"
        "業界標準の団体 OCI (Open Container Initiative、2015 年 6 月設立) の仕様に沿う形へ整理されました。"
        "バージョンの付け方は 2017 年に「年.月」(17.03 など) になり、2023 年の 23.0 から普通の番号に戻りました。"
        "2025 年 11 月の Docker Engine 29.0 では、新しく入れた環境ではイメージの保存に containerd の仕組み (containerd image store) を使うのが標準になり、"
        "ファイアウォールの nftables への対応 (試験的)、cgroup v1 の非推奨化などが行われました。2026 年 10 月時点の最新は 29.9 系です。"
    ),
    "kids": (
        "コンテナの工場 (Docker) に電話をかけて「もしもし、動いてますか？」と聞くのが docker version です。"
        "「はい、動いてます。わたしのバージョンは 29 です」と返事が来たら、工場にお仕事をお願いする準備ができました。"
    ),
    "rhel": (
        "RHEL 8 以降、Red Hat が標準で用意しているコンテナの道具は Podman (docker と似たコマンドが使える別の製品) です。"
        "Docker 社の Docker Engine (docker-ce) は、Docker 社のリポジトリ (https://download.docker.com/linux/rhel/docker-ce.repo) から入れます。"
        "公式手順では、先に podman と runc を削除してから docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin を入れ、"
        "sudo systemctl enable --now docker で起動・自動起動を有効にします。"
        "docker グループに入ったユーザーは root と同じくらいの力を持てるので、グループに入れる人は最小限にしてください。"
    ),
}

COMMANDS["docker network create"] = {
    "title": "docker network create ― コンテナ専用の仮想ネットワークを作る",
    "syntax": "docker network create [オプション] ネットワーク名",
    "oneline": "コンテナどうしが名前で話せる、専用の仮想ネットワーク (ユーザー定義ブリッジ) を作ります。",
    "how": (
        "かたまりをコピーして貼り付け、Enter を押します。成功すると、作られたネットワークの ID (64 文字の英数字) が 1 行表示されます。\n"
        "・「network with name ... already exists」と出たら、同じ名前のネットワークが既にあります。前回の分が残っている場合は、"
        "後片付けの手順 (docker network rm) を実行してからやり直してください。\n"
        "・「Pool overlaps with other one on this address space」と出たら、指定した IP アドレスの範囲 (subnet) が"
        "既存のネットワークと重なっています。"
    ),
    "meaning": (
        "Docker のネットワークは、コンテナどうし、またはコンテナと外の世界をつなぐ「仮想の LAN」です。"
        "docker network create は新しい仮想 LAN を 1 つ作ります。ドライバー (種類) を指定しなければ bridge (ブリッジ) になり、"
        "このホストの中だけで使えるネットワークができます。\n"
        "同じネットワークにつながったコンテナは、相手の「コンテナ名」や「ネットワーク別名 (エイリアス)」で通信できます。"
        "たとえば web コンテナから http://db:5432 のように、IP アドレスを覚えなくても名前で相手に届きます。"
        "compose はこれを利用して、サービス名 (services: の下に書いた名前) で呼び合えるようにしています。"
    ),
    "principle": (
        "bridge ドライバーの場合、Docker はホストの Linux カーネルに「ブリッジ」(ソフトウェアでできたスイッチングハブ) を作ります。"
        "名前は br- の後ろにネットワーク ID の先頭 12 文字が付いたもの (例: br-1a2b3c4d5e6f) で、ip addr で見ることができます。\n"
        "次に IPAM (IP Address Management = IP アドレスの割り当て係) が、まだ使われていないアドレスの範囲 (サブネット。例: 172.18.0.0/16) を選び、"
        "その最初のアドレス (例: 172.18.0.1) をゲートウェイ (外への出口) としてブリッジに付けます。\n"
        "コンテナがこのネットワークにつながるとき、Docker は veth ペア (2 本で 1 組の仮想 LAN ケーブル) を作り、"
        "片方をコンテナのネットワーク名前空間 (コンテナ専用のネットワークの世界) に入れて eth0 などの名前にし、もう片方をブリッジに差します。\n"
        "外 (インターネットなど) へ出る通信は、ファイアウォールの仕組み (iptables。RHEL 9 では内部で nftables に変換される) の"
        "MASQUERADE というルールで、送り主のアドレスがホストのアドレスに書き換えられます。\n"
        "名前で呼び合えるのは、Docker が内蔵 DNS サーバーを持っているからです。コンテナの /etc/resolv.conf には 127.0.0.11 が書かれ、"
        "ここへの問い合わせを dockerd が受けて、同じネットワークにいるコンテナの名前・別名を IP アドレスに変換して答えます。"
        "知らない名前はホスト側の DNS に聞きに行きます。なお、Docker が最初から持っている「bridge」(docker0) ネットワークでは、"
        "この名前解決は働きません。compose が必ず自分用のネットワークを作るのはこのためです。\n"
        "--internal を付けると外への出口の設定が作られず、ネットワークの中だけで通信できる閉じた LAN になります。"
    ),
    "image": (
        "マンション (ホスト) の中に、住人 (コンテナ) どうしだけで使える「内線電話網」を引くようなものです。"
        "ブリッジは電話の交換機、veth は各部屋へつながる電話線、内蔵 DNS は「名前を言えば番号につないでくれる電話帳係」です。"
        "外に電話 (インターネット) をかけるときは、マンションの代表番号 (ホストの IP アドレス) からかけたことにしてもらいます (MASQUERADE)。"
    ),
    "history": (
        "最初の Docker (2013 年) には docker0 という 1 つの共用ネットワークしかなく、コンテナどうしをつなぐには --link という仕組みで、"
        "相手の IP アドレスを環境変数や /etc/hosts に書き込むしかありませんでした。相手が再起動して IP が変わると切れてしまうなど、不便な点がありました。\n"
        "そこで Docker 社は 2015 年 3 月に SocketPlane という会社を買収してネットワーク部品 (libnetwork) を作り、"
        "2015 年 11 月の Docker 1.9 で docker network コマンドと「ユーザーが自由に作れるネットワーク」が登場しました。"
        "2016 年 2 月の Docker 1.10 で内蔵 DNS とネットワーク別名 (--network-alias) が加わり、名前で呼び合うのが当たり前になりました。\n"
        "compose も 2016 年のファイル形式 v2 から networks: を書けるようになり、プロジェクトごとに専用ネットワーク (<プロジェクト名>_default) を"
        "自動で作るようになりました。その後も、Docker 25 (2024 年) で 1 回の docker run で複数ネットワークにつなげるようになり、"
        "Docker 28 (2025 年) でデフォルトゲートウェイの優先度 (gw-priority)、Docker 29 (2025 年 11 月) で nftables への試験的な対応が加わっています。"
    ),
    "kids": (
        "コンテナたちのための「専用の道路と電話帳」を作るコマンドです。同じ道路につながったコンテナは、"
        "「db さーん」と名前を呼ぶだけで相手のところへ手紙 (データ) を届けられます。"
    ),
    "rhel": (
        "RHEL 9.8 では firewalld が動いていることが多く、Docker は firewalld に docker という zone を作ってブリッジを登録します。"
        "firewall-cmd --reload をしたあとにコンテナの通信がおかしくなったら、sudo systemctl restart docker で Docker のルールを入れ直してください。\n"
        "社内ネットワークと Docker が選んだサブネット (172.17〜172.31 や 192.168.x.x) が重なると、その範囲の社内サーバーへ届かなくなります。"
        "そのときは compose の ipam.config.subnet で範囲を指定するか、/etc/docker/daemon.json の default-address-pools で Docker が使う範囲を変えます。"
    ),
}

COMMANDS["docker network inspect"] = {
    "title": "docker network inspect ― 既にあるネットワークを確かめる",
    "syntax": "docker network inspect ネットワーク名",
    "oneline": "compose で external: true (外部) とされたネットワークが、本当にあるかを確かめます。",
    "how": "貼り付けて Enter。「OK: <名前> があります」と表示されれば問題ありません。「Error: No such network」と出たら、そのネットワークを先に作る必要があります。",
    "meaning": (
        "docker network inspect は、ネットワークの詳しい情報 (サブネット、つながっているコンテナ、オプションなど) を JSON で表示します。"
        "ここでは「表示できた = 存在する」ことの確認に使い、表示内容は > /dev/null で捨てています。"
        "&& は「左のコマンドが成功したときだけ右を実行する」という意味です。"
    ),
    "principle": (
        "dockerd に GET /networks/<名前> を問い合わせます。compose の external: true は「このネットワークは compose の外で管理しているので、"
        "作りも消しもしない」という宣言です。compose も起動時に同じ確認をし、無ければ「declared as external, but could not be found」で止まります。"
    ),
    "image": "共用の道路 (別のプロジェクトが作った道路) を使わせてもらう前に、「その道路は本当にあるかな？」と地図で確かめるようなものです。",
    "history": "external ネットワークは、複数の compose プロジェクトや、compose 以外で起動したコンテナと同じネットワークを共有したいという要望から生まれました (compose ファイル形式 v2、2016 年)。",
    "kids": "使う予定の道路が本当にあるか、地図でチェックするコマンドです。",
    "rhel": "特にありません。",
}

COMMANDS["docker volume create"] = {
    "title": "docker volume create ― データを残しておくボリュームを作る",
    "syntax": "docker volume create [オプション] ボリューム名",
    "oneline": "コンテナを消しても中身が残る、Docker が管理する保存場所 (名前付きボリューム) を作ります。",
    "how": (
        "貼り付けて Enter。成功するとボリューム名が 1 行表示されます。同じ名前のボリュームが既にある場合もエラーにはならず、"
        "そのまま名前が表示されます (中身はそのまま残っています)。"
    ),
    "meaning": (
        "コンテナの中で書いたファイルは、ふつうはコンテナを削除すると一緒に消えてしまいます。データベースのデータのように"
        "消えては困るものは「ボリューム」に保存します。docker volume create は名前付きのボリュームを作るコマンドです。\n"
        "compose は volumes: に書いたボリュームを「<プロジェクト名>_<キー>」という名前で作ります。"
    ),
    "principle": (
        "標準の local ドライバーでは、ホストの /var/lib/docker/volumes/<ボリューム名>/_data というフォルダが作られるだけです。"
        "コンテナを起動するとき、Docker はこのフォルダを「バインドマウント」という仕組みで、コンテナの中の指定の場所 (例: /var/lib/mysql) に重ねて見せます。"
        "コンテナから見ると普通のフォルダですが、実体はコンテナの外にあるため、コンテナを消しても残ります。\n"
        "空のボリュームを初めてつないだときは、イメージのその場所に最初から入っていたファイルがボリュームへコピーされます (コピーアップ)。"
        "nocopy を指定するとコピーしません。\n"
        "--opt type=nfs,o=addr=...,device=:/export のようにすると、NFS などのネットワーク上の保存場所をボリュームとして使うこともできます"
        " (裏では mount コマンドと同じ仕組みが使われます)。"
    ),
    "image": (
        "お部屋 (コンテナ) の外にある「貸しロッカー」です。お部屋を片付けて (コンテナを削除して) も、ロッカーの中身は残っています。"
        "次に新しいお部屋を用意したら、同じロッカーの鍵を渡せば、前のデータをそのまま使えます。"
    ),
    "history": (
        "初期の Docker では、データを残すには -v でホストのフォルダを直接つなぐか、「データ専用コンテナ」を作って --volumes-from で共有する、"
        "という工夫が使われていました。2015 年の Docker 1.8 でボリュームプラグイン (外部ストレージとつなぐ仕組み)、"
        "2015 年 11 月の Docker 1.9 で docker volume コマンドと名前付きボリュームが登場し、データの置き場所を名前で管理できるようになりました。"
        "2017 年の Docker 17.06 で、docker run に読みやすい長い書き方 --mount が追加され、2024 年の Docker 26 ではボリュームの中の一部のフォルダだけを"
        "つなぐ volume-subpath が使えるようになりました。compose ではファイル形式 v2 (2016 年) から volumes: でボリュームを定義できます。"
    ),
    "kids": "コンテナが使う「なくならないロッカー」を用意するコマンドです。コンテナを片付けても、ロッカーの中のデータは残ります。",
    "rhel": (
        "ボリュームの実体は /var/lib/docker の下に作られます。RHEL では /var を小さなパーティションに分けていることがあるため、"
        "df -h /var/lib/docker で空き容量を確認してください。\n"
        "SELinux を有効にした Docker (daemon.json で \"selinux-enabled\": true) でも、名前付きボリュームには Docker が自動で正しいラベルを付けるので、"
        "そのまま使えます。"
    ),
}

COMMANDS["docker volume inspect"] = {
    "title": "docker volume inspect ― 既にあるボリュームを確かめる",
    "syntax": "docker volume inspect ボリューム名",
    "oneline": "compose で external: true とされたボリュームが、本当にあるかを確かめます。",
    "how": "貼り付けて Enter。「OK: <名前> があります」と表示されれば問題ありません。「Error: No such volume」なら先に作成が必要です。",
    "meaning": "ボリュームの詳しい情報 (ドライバー、保存場所、ラベルなど) を表示するコマンドです。ここでは存在確認に使っています。",
    "principle": "dockerd に GET /volumes/<名前> を問い合わせます。external: true のボリュームは compose も作らず、無ければエラーで止まります。",
    "image": "使う予定のロッカーが本当にあるか、管理人さんの台帳で確かめるようなものです。",
    "history": "external ボリュームは、プロジェクトをまたいでデータを共有したり、compose の down -v で誤って消されないようにしたりするために使われます。",
    "kids": "使う予定のロッカーが本当にあるか確かめるコマンドです。",
    "rhel": "特にありません。",
}

COMMANDS["docker image inspect"] = {
    "title": "docker image inspect ― イメージが手元にあるか調べる",
    "syntax": "docker image inspect イメージ名",
    "oneline": "イメージが手元 (このサーバー) にあるかを調べます。",
    "how": "単独では使わず、docker pull と組み合わせています。",
    "meaning": "イメージの設定や層の情報を表示します。手元に無ければエラー (終了コード 1) になるので、存在確認に使えます。",
    "principle": "dockerd のイメージ一覧 (image store) を調べるだけで、ネットワークには出ません。",
    "image": "家の押し入れに、その部品セットがあるかをのぞいてみるようなものです。",
    "history": "docker inspect は初期からある調査用のコマンドです。",
    "kids": "押し入れにおもちゃの部品があるか見てみるコマンドです。",
    "rhel": "特にありません。",
}

COMMANDS["docker pull"] = {
    "title": "docker pull ― イメージをダウンロードする",
    "syntax": "docker image inspect イメージ > /dev/null 2>&1 || docker pull イメージ",
    "oneline": "イメージが手元に無いときだけ、レジストリ (イメージの倉庫) からダウンロードします。",
    "how": (
        "貼り付けて Enter。手元に既にある場合は何も表示されずに終わります (正常です)。無い場合はダウンロードの進み具合が表示され、"
        "最後に「Status: Downloaded newer image for ...」と出れば成功です。\n"
        "・「pull access denied」「unauthorized」は、非公開のイメージなので docker login が必要か、名前の間違いです。\n"
        "・「toomanyrequests」は Docker Hub のダウンロード回数制限です。時間をおくか、docker login してから実行してください。\n"
        "・「dial tcp ... i/o timeout」はインターネットに出られていません (プロキシの設定を確認)。"
    ),
    "meaning": (
        "docker pull は、Docker Hub や Amazon ECR などの「レジストリ」からイメージをダウンロードします。\n"
        "このステップでは docker image inspect で手元にあるかを調べ、無いときだけ docker pull を実行しています。"
        "|| は「左のコマンドが失敗したときだけ右を実行する」という意味で、> /dev/null 2>&1 は表示を捨てる書き方です。"
        "これは compose の既定の動き (pull_policy: missing = 無いときだけ取ってくる) と同じです。"
        "ただの docker pull にしないのは、手元に古い版があるときに勝手に新しい版へ変わってしまう (compose と違う結果になる) のを防ぐためです。"
    ),
    "principle": (
        "イメージ名「レジストリ/リポジトリ:タグ」を分解します。レジストリを省略すると docker.io (Docker Hub) が使われ、"
        "公式イメージは library/ が補われます (例: mysql:8.4.7 → docker.io/library/mysql:8.4.7)。\n"
        "次に、レジストリの API (OCI Distribution Specification) でマニフェスト (イメージがどの層 = レイヤーでできているかの目録) を取り寄せます。"
        "いろいろな CPU 向けの版がある「マルチアーキテクチャ」イメージなら、目録の目録 (インデックス) から linux/amd64 など"
        "このサーバーに合うものを選びます。\n"
        "レイヤーは、ファイルの差分を tar でまとめて gzip や zstd で圧縮したもので、中身から計算した sha256 の値 (ダイジェスト) で区別されます。"
        "同じダイジェストのレイヤーを既に持っていればダウンロードせず、無いものだけを並行してダウンロードし、壊れていないか検証してから展開します。\n"
        "Docker Hub には回数制限があり、2026 年 10 月時点の公式ドキュメントでは、ログインしない場合は 6 時間あたり 100 回 (IPv4 アドレス、または IPv6 の /64 ごと)、"
        "無料アカウントでログインすると 200 回です。"
    ),
    "image": (
        "インターネットの「部品倉庫」から、お部屋セット (イメージ) を取り寄せます。セットは何枚もの透明なシート (レイヤー) を重ねてできていて、"
        "家に同じシートがあればそれを使い回し、足りないシートだけを送ってもらいます。押し入れに同じセットが既にあれば、取り寄せはしません。"
    ),
    "history": (
        "2013 年の Docker 登場と同時に、イメージを共有する場所 (Docker Index) が作られ、2014 年 6 月の Docker 1.0 と同時に Docker Hub になりました。"
        "2015 年の Registry API v2 (Docker 1.6) で、中身のハッシュ値でレイヤーを管理する今の方式になり、同じものを二度送らずに済むようになりました。"
        "2017 年に OCI Image Specification 1.0、2021 年に OCI Distribution Specification 1.0 が決まり、Docker 以外のツール (Podman や Kubernetes) とも"
        "同じイメージを共有できるようになりました。2020 年 11 月からは Docker Hub に回数制限が導入され、Amazon ECR Public (2020 年 12 月) のような"
        "別の公開レジストリも使われるようになりました。"
    ),
    "kids": "おもちゃの部品セットを倉庫から取り寄せるコマンドです。家にもうあるときは、取り寄せません。",
    "rhel": (
        "社内でプロキシを使う場合、docker pull を実際に行うのは dockerd なので、dockerd にプロキシを設定します "
        "(例: /etc/systemd/system/docker.service.d/http-proxy.conf に Environment=\"HTTPS_PROXY=http://proxy.example.com:8080\" を書き、"
        "sudo systemctl daemon-reload && sudo systemctl restart docker)。"
        "自己署名証明書の社内レジストリは /etc/docker/certs.d/<レジストリ名>/ca.crt に CA 証明書を置きます。"
    ),
}

COMMANDS["docker build"] = {
    "title": "docker build ― Dockerfile からイメージを作る",
    "syntax": "docker build [オプション] ビルドコンテキスト",
    "oneline": "設計図 (Dockerfile) と材料フォルダ (ビルドコンテキスト) から、イメージを作ります。",
    "how": (
        "貼り付けて Enter。[+] Building ... と進み具合が表示され、最後に「naming to docker.io/library/<名前>」や"
        "「writing image sha256:...」が出て、エラー無くプロンプトに戻れば成功です。2 回目以降は、変わっていない部分に CACHED と表示され、早く終わります。\n"
        "・「failed to solve」と出たら、Dockerfile のどの行で失敗したかが表示されるので、その行のコマンドや COPY するファイルの有無を確認します。\n"
        "・ビルドコンテキスト (最後に書いたフォルダ) は compose ファイルの build.context と同じ場所です。RHEL 上に同じフォルダ構成で置いてください。"
    ),
    "meaning": (
        "Dockerfile は「どのイメージを土台にして (FROM)、何をインストールし (RUN)、どのファイルを入れ (COPY)、何を起動するか (CMD)」を書いた設計図です。"
        "docker build はそれを読んで、上から順に作業し、できあがったものをイメージとして保存します。--tag で付けた名前が、そのイメージの名前になります。\n"
        "compose の build: に書かれた設定 (context = 材料フォルダ、dockerfile = 設計図の場所、args = 設計図に渡す値、target = 途中の段階まで作る など) は、"
        "それぞれ docker build のオプションに 1 対 1 で対応しています。compose は image: の名前、無ければ「<プロジェクト名>-<サービス名>」という名前を付けます。"
    ),
    "principle": (
        "Docker 23.0 (2023 年 2 月) からは、docker build の中身は BuildKit という新しいビルドエンジン (docker buildx build) です。\n"
        "① ビルドコンテキスト (フォルダ) の中身が BuildKit に渡されます。.dockerignore に書いたファイルは渡されません。\n"
        "② Dockerfile は LLB (低水準のビルド手順のグラフ) に変換され、互いに関係のない手順は同時に (並列に) 実行されます。\n"
        "③ RUN 命令は、ビルド用の一時的なコンテナの中で実行されます。COPY・RUN などの結果は「レイヤー」(前との差分) として記録され、"
        "命令と材料が前回と同じなら、作り直さずにキャッシュ (作り置き) を使います。\n"
        "④ FROM ... AS 名前 を何度も書く「マルチステージ」では、ビルド用の道具を入れた段階でプログラムを作り、完成品だけを小さな最終イメージへ COPY --from で移せます。\n"
        "⑤ --build-arg の値はイメージの履歴に残るので、パスワードには使いません。秘密の値は --secret で渡し、Dockerfile では RUN --mount=type=secret で"
        "その命令の間だけ一時的に読みます (レイヤーにもキャッシュにも残りません)。\n"
        "⑥ 完成したイメージは、手元のイメージ一覧に --tag の名前で登録されます。\n"
        "compose v5 (2025 年 12 月) は自前のビルド処理をやめ、Docker Bake (BuildKit を複数まとめて動かす仕組み) に任せています。"
        "そのため、docker build を使っても compose と同じ BuildKit で同じイメージができます。"
    ),
    "image": (
        "料理にたとえると、Dockerfile は「レシピ」、ビルドコンテキストは「材料の入った箱」、BuildKit は「料理人」です。"
        "料理人はレシピを 1 行ずつ読み、手順ごとにお皿 (レイヤー) を重ねて「冷凍お弁当」(イメージ) を完成させます。"
        "前と同じ手順・同じ材料なら、作り置きのお皿を使うので早くできます。"
    ),
    "history": (
        "Dockerfile は 2013 年の Docker 登場時からある仕組みで、「サーバーの設定手順書をそのまま実行できる形にする」という考え方を広めました。"
        "2017 年の Docker 17.05 でマルチステージビルドが入り、小さく安全なイメージを作りやすくなりました。\n"
        "同じ 2017 年に、もっと速く安全なビルドを目指す BuildKit の開発が Moby プロジェクトで始まり、2018 年の Docker 18.09 で試せるようになり、"
        "2019 年に docker buildx が登場、2020 年には Dockerfile の RUN --mount (secret / ssh / cache) が使えるようになりました。"
        "そして 2023 年 2 月の Docker 23.0 で、Linux の docker build は標準で BuildKit を使うようになりました。\n"
        "compose のビルドも BuildKit を使うように変わり、2025 年 12 月の Compose v5.0 で、ビルドは Docker Bake に一本化されました。"
    ),
    "kids": "設計図と材料を工場に渡して、おもちゃのもと (イメージ) を作ってもらうコマンドです。前と同じところは作り置きを使うので、2 回目からは早くできます。",
    "rhel": (
        "UBI (Red Hat Universal Base Image) などを土台にして RUN dnf install をする場合、ビルド中のインターネット接続が必要です。"
        "プロキシ環境では --build-arg HTTP_PROXY=... / HTTPS_PROXY=... を渡すか、~/.docker/config.json の proxies 設定を使います。"
        "ビルドの途中結果 (キャッシュ) は /var/lib/docker に溜まるので、容量が足りなくなったら docker builder prune で片付けます。"
    ),
}

COMMANDS["docker build (healthcheck)"] = {
    "title": "docker build - (ヘルスチェック入りの派生イメージを作る)",
    "syntax": "docker build --tag 新しい名前 - <<'C2D_DOCKERFILE' (Dockerfile の中身) C2D_DOCKERFILE",
    "oneline": "元のイメージに、compose と同じ「exec 形式」のヘルスチェック設定だけを足したイメージを作ります。",
    "how": (
        "かたまり全体 (最後の C2D_DOCKERFILE の行まで) をコピーして貼り付け、Enter を押します。"
        "途中で > という記号が表示されるのは、ヒアドキュメント (複数行の文章をコマンドに渡す書き方) の続きを受け付けている印なので、正常です。"
        "数秒で終わり、エラーが出なければ成功です。"
    ),
    "meaning": (
        "compose の healthcheck の test には 2 つの書き方があります。\n"
        "・exec 形式 [\"CMD\", \"コマンド\", \"引数\"] … コマンドを直接実行します。\n"
        "・シェル形式 [\"CMD-SHELL\", \"コマンド文字列\"] … /bin/sh -c \"コマンド文字列\" として実行します。\n"
        "ところが docker run の --health-cmd オプションは、必ずシェル形式になってしまいます。/bin/sh が入っていないイメージ (distroless など) では"
        "シェル形式のヘルスチェックは必ず失敗し、コンテナは unhealthy (不健康) になって、それを待っている他のコンテナも起動できなくなります。\n"
        "そこで、Dockerfile の HEALTHCHECK 命令 (こちらは exec 形式が書ける) を使って、元のイメージに設定だけを足した派生イメージを作ります。"
        "これで compose とまったく同じヘルスチェックになります。"
    ),
    "principle": (
        "docker build の最後の「-」は、「Dockerfile を標準入力から読む (材料フォルダは使わない)」という意味です。<<'C2D_DOCKERFILE' から"
        "C2D_DOCKERFILE までの行が、そのまま Dockerfile として渡されます。'...' で囲んでいるので、$ などの記号もそのまま渡されます。\n"
        "FROM で元のイメージを土台にし、HEALTHCHECK でヘルスチェックの設定を付けます。HEALTHCHECK はファイルを変えない「設定 (メタデータ)」だけの命令なので、"
        "中身のファイルは元のイメージと 1 バイトも変わらず、イメージの設定 (config) だけが新しくなります。ダウンロードし直すものもありません。"
        "元のイメージ名はそのまま残り、新しいイメージには <プロジェクト>-<サービス>:with-healthcheck という別の名前を付けます。"
    ),
    "image": "お弁当 (イメージ) の中身はそのままで、ふたに「元気チェックのやり方カード」を貼った版を作るようなものです。",
    "history": (
        "HEALTHCHECK は 2016 年 7 月の Docker 1.12 で追加されました。それまでは「プロセスが動いているか」しか分からず、"
        "「動いてはいるが応答しない」状態を見分けられませんでした。その後、Google の distroless (2017 年) のように、"
        "攻撃される隙を減らすためにシェルすら入れない小さなイメージが広まり、シェルを使わない exec 形式の大切さが増しました。"
        "Docker 25 (2024 年) では、起動直後だけ短い間隔でチェックする start-interval も加わっています。"
    ),
    "kids": "元のおもちゃはそのままで、「元気かな？チェックのやり方」を書いたカードを貼った版を作るコマンドです。",
    "rhel": "特にありません。元のイメージが手元にある (先の STEP で取得・ビルド済み) 必要があります。",
}

COMMANDS["docker run"] = {
    "title": "docker run ― コンテナを作って起動する",
    "syntax": "docker run [オプション] イメージ [コマンド] [引数...]",
    "oneline": "イメージからコンテナを作り、設定 (ネットワーク・ボリューム・環境変数など) をして起動します。",
    "how": (
        "かたまり全体をコピーして貼り付け、Enter を押します。行の最後の \\ (バックスラッシュ。Excel の Meiryo UI では ¥ に見えます) は「コマンドが次の行に続く」という印なので、"
        "途中で切らずに全部まとめて貼り付けてください。成功すると、作られたコンテナの ID (64 文字の英数字) が 1 行表示されます。\n"
        "・「Conflict. The container name \"/...\" is already in use」は、同じ名前のコンテナが残っています。後片付けをしてからやり直します。\n"
        "・「port is already allocated」「address already in use」は、ホストのそのポートを別のプログラムが使っています。\n"
        "・ID が表示されてもすぐ止まってしまうことがあります。docker ps --all で STATUS を見て、Exited なら docker logs <名前> で原因を調べます。"
    ),
    "meaning": (
        "docker run は「docker create (作る)」と「docker start (起動する)」を 1 回で行うコマンドです。"
        "--detach を付けると、コンテナを裏側で動かしたまま、すぐにプロンプトへ戻ります (compose の up -d と同じ)。\n"
        "オプションは、compose ファイルの services: の各設定 (ports, volumes, environment, healthcheck, restart など) を 1 つずつ"
        "docker のオプションに置き換えたものです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) です。\n"
        "compose はコンテナに「<プロジェクト名>-<サービス名>-<番号>」という名前を付け、サービス名をネットワーク上の別名にします。"
        "この手順でも同じ名前・同じ別名を付けるので、コンテナどうしの呼び方 (http://db:3306 など) も compose のときと変わりません。"
    ),
    "principle": (
        "① docker コマンドがオプションを JSON にまとめ、dockerd に「POST /containers/create」を送ります。\n"
        "② dockerd はイメージに書かれた設定 (ENV・CMD・ENTRYPOINT・WORKDIR・USER・EXPOSE・VOLUME・HEALTHCHECK) と、オプションの設定を合わせ、"
        "OCI ランタイム仕様の設定ファイル (config.json) を作ります。オプションで指定したものがイメージの設定より優先されます。\n"
        "③ 続いて「POST /containers/<ID>/start」で起動します。dockerd → containerd → containerd-shim-runc-v2 → runc とリレーされ、"
        "runc が Linux カーネルに次のことを頼みます。\n"
        "　・名前空間 (namespace): PID (プロセス番号)・NET (ネットワーク)・MNT (ファイルの見え方)・UTS (ホスト名)・IPC (プロセス間通信)・cgroup を"
        "コンテナ専用に分け、ほかのコンテナやホストのものが見えないようにします。\n"
        "　・cgroup v2: CPU・メモリ・プロセス数などの使用量を数え、上限を決めます (--cpus や --memory)。\n"
        "　・overlayfs: イメージのレイヤー (読み取り専用) を何枚も重ね、その一番上に書き込み用の層を 1 枚足して、コンテナのファイルシステム (/) にします。"
        "コンテナで書いたファイルはこの書き込み層に入り、コンテナを消すと一緒に消えます。\n"
        "　・ボリュームやバインドマウントをつなぎ、capabilities (root の特権を細かく分けたもの。標準では 14 種類だけ許可) と "
        "seccomp (使ってよいシステムコールの一覧) で権限をしぼります。\n"
        "　・最後に ENTRYPOINT + CMD のプログラムを、そのコンテナの中の PID 1 (最初のプロセス) として実行します。\n"
        "④ ネットワークは veth でブリッジにつながれ、IP アドレスが割り当てられ、/etc/hosts と /etc/resolv.conf (内蔵 DNS の 127.0.0.11) が用意されます。\n"
        "⑤ プログラムの画面出力は、ログドライバー (標準は json-file) を通して /var/lib/docker/containers/<ID>/<ID>-json.log などに保存されます。\n"
        "⑥ その後も dockerd は、restart の設定に従ってコンテナが止まったら起こし直し、HEALTHCHECK があれば一定間隔で健康チェックを行います。\n"
        "つまりコンテナの正体は「特別な囲いの中で動いている、ふつうの Linux のプロセス」です。仮想マシンのように OS をまるごと起動するわけではないので、"
        "1 秒もかからずに起動できます。"
    ),
    "image": (
        "マンション (ホスト) の空き部屋を 1 つ用意し、お部屋セット (イメージ) の家具を運び込んで、住人 (プログラム) に住んでもらうようなものです。"
        "部屋には壁 (名前空間) があってほかの部屋の中は見えず、電気や水道にはブレーカー (cgroup) が付いていて使いすぎを防ぎます。"
        "管理人さん (dockerd) は、マンションの合鍵 (特権) のうち必要なものだけを住人に渡し、住人が倒れたら起こしに行き (restart)、"
        "ときどき「元気？」と声をかけます (healthcheck)。"
    ),
    "history": (
        "「プログラムを囲いの中で動かす」考えは古く、1979 年の Unix V7 の chroot (見えるフォルダを制限する) までさかのぼります。"
        "2000 年に FreeBSD の jail、2004〜2005 年に Solaris の Zones が登場しました。Linux では 2002 年から名前空間が少しずつ作られ、"
        "2006 年に Google の技術者が「process containers」として資源の上限を決める仕組みを開発し、2008 年 (Linux 2.6.24) に cgroups として取り込まれました。"
        "同じ 2008 年に、これらを組み合わせた LXC が登場しています。\n"
        "2013 年の Docker は、LXC を使って「イメージ」という配りやすい形と、docker run という簡単なコマンドを用意したことで爆発的に広まりました。"
        "2014 年には LXC をやめて自前の libcontainer に切り替え、2015 年にそれを runc として OCI に寄贈しました。2016 年には containerd が分離され、"
        "2017 年に CNCF (クラウドネイティブの技術を育てる団体) へ寄贈されています。\n"
        "資源の管理は cgroup v2 (2016 年、Linux 4.5) へ移り、RHEL 9 (2022 年) では cgroup v2 が標準になりました。Docker も 20.10 (2020 年) で cgroup v2 に対応し、"
        "29.0 (2025 年 11 月) で cgroup v1 を非推奨にしています。"
    ),
    "kids": (
        "おもちゃのもと (イメージ) から、本物のおもちゃ (コンテナ) を組み立てて、スイッチを入れるコマンドです。"
        "どの道路 (ネットワーク) につなぐか、どのロッカー (ボリューム) を使うか、どんなメモ (環境変数) を持たせるかも、ここでいっしょに決めます。"
    ),
    "rhel": (
        "・RHEL 9.8 は cgroup v2 が標準です。--memory-swappiness や --kernel-memory など cgroup v1 専用の古いオプションは使えません (警告が出て無視されます)。\n"
        "・SELinux: docker-ce の標準設定 (selinux-enabled: false) では、コンテナに SELinux のラベルが付かないため、バインドマウントはそのまま読み書きできます。"
        "/etc/docker/daemon.json に \"selinux-enabled\": true を設定している場合は、ホストのフォルダをつなぐときに :z (複数のコンテナで共有) か "
        ":Z (このコンテナ専用) を付けないと Permission denied になります。これは compose でも同じです。\n"
        "・ポート公開 (-p) は Docker が自分でファイアウォールのルールを入れるため、通常は firewall-cmd での許可は不要です。"
        "・Docker 29 から、コンテナ内の「同時に開けるファイル数」の標準 (ulimit -n のソフト上限) が 1024 になっています。"
        "多くの接続やファイルを使うアプリは、compose の ulimits (= --ulimit nofile=...) で上げておきます。"
    ),
}

COMMANDS["docker create"] = {
    "title": "docker create ― コンテナを作る (まだ起動しない)",
    "syntax": "docker create [オプション] イメージ [コマンド] [引数...]",
    "oneline": "コンテナを作るところまで行い、起動はしません。起動前にファイルを入れたり準備をしたりするために使います。",
    "how": "かたまり全体を貼り付けて Enter。コンテナ ID が表示されれば成功です。docker ps --all で見ると STATUS が Created になっています。",
    "meaning": (
        "docker run の前半 (作る) だけを行うコマンドです。オプションの意味は docker run とまったく同じです。\n"
        "compose も実は、まず全部のコンテナを create してから、順番に start しています。この手順では、"
        "起動前にやること (configs / secrets のファイルの書き込み、pre_start の初期化コンテナ) があるサービスだけ、create と start を分けています。"
    ),
    "principle": (
        "dockerd に POST /containers/create だけを送ります。コンテナの設定と、書き込み用の層 (overlayfs の upper) が用意されますが、"
        "プロセスはまだ動いておらず、ネットワークにもまだつながっていません (IP アドレスは start のときに割り当てられます)。"
    ),
    "image": "お部屋に家具を運び込んだけれど、まだ住人が入居していない状態です。入居前に、部屋に必要な書類を置いておけます。",
    "history": "docker create は 2014 年 10 月の Docker 1.3 で追加されました。それまでは docker run しかなく、「作るだけ」ができませんでした。",
    "kids": "おもちゃを組み立てるけれど、まだスイッチは入れない、というコマンドです。",
    "rhel": "docker run と同じです。",
}

COMMANDS["docker cp"] = {
    "title": "docker cp ― コンテナにファイルを入れる",
    "syntax": "tar ... --file - ファイル | docker cp - コンテナ名:/",
    "oneline": "compose の configs (content) や secrets (environment) の中身を、起動前のコンテナにファイルとして書き込みます。",
    "how": (
        "かたまり全体 (mkdir から rm -rf まで) を貼り付けて Enter。エラーが出なければ成功です。"
        "中身は cat > ... <<'C2D_CONTENT' から C2D_CONTENT までの行に書かれています。"
    ),
    "meaning": (
        "compose は、configs: に content: (中身を直接書いたもの) や environment: (環境変数の値を使うもの) で定義された設定ファイル・秘密情報を、"
        "コンテナを起動する前にコンテナの中へファイルとしてコピーします (ファイルの持ち主は root、権限は読み取り専用の 0444 が標準)。\n"
        "同じことをするため、① 一時フォルダ (/tmp/<プロジェクト>-compose2docker) にファイルを作り、② tar で「持ち主・権限つき」の 1 つのかたまりにまとめ、"
        "③ docker cp でコンテナのルート (/) に展開し、④ 一時フォルダを消します。"
    ),
    "principle": (
        "docker cp は内部で tar 形式 (ファイルを持ち主・権限などの情報ごと 1 つにまとめる昔からの形式) のデータを dockerd に送ります "
        "(API: PUT /containers/<ID>/archive)。docker cp - は「標準入力から tar を受け取る」という意味で、パイプ (|) で tar の出力をそのまま渡しています。"
        "--owner / --group / --mode で、コンテナの中でのファイルの持ち主と権限を compose と同じにしています。"
        "書き込み先はコンテナの書き込み用の層なので、コンテナを再起動しても残り、コンテナを削除すると消えます。"
    ),
    "image": "住人が入居する前のお部屋に、取扱説明書 (設定ファイル) を置いておくようなものです。",
    "history": (
        "docker cp は最初「コンテナからホストへ」しかコピーできませんでしたが、2015 年 8 月の Docker 1.8 で「ホストからコンテナへ」もできるようになりました。"
        "compose の configs / secrets はもともと Swarm (複数台のサーバーをまとめる仕組み) 用の機能でしたが、compose でも使えるようにするため、"
        "ファイルからはバインドマウント、中身の直書きからはこのコピーで実現しています。"
    ),
    "kids": "お部屋を使い始める前に、必要なお手紙を部屋の中に置いておくコマンドです。",
    "rhel": "RHEL の tar (GNU tar) は --owner / --group / --mode に対応しています。/tmp に書き込めるユーザーで実行してください。",
}

COMMANDS["docker start"] = {
    "title": "docker start ― 作っておいたコンテナを起動する",
    "syntax": "docker start コンテナ名",
    "oneline": "docker create で作ったコンテナを起動します。",
    "how": "貼り付けて Enter。コンテナ名が表示されれば成功です。docker ps で STATUS が Up になっているか確認できます。",
    "meaning": "docker run の後半 (起動) だけを行います。起動前の準備 (ファイルの投入・初期化コンテナ) が終わったので、ここで初めてプログラムが動き出します。",
    "principle": "dockerd に POST /containers/<ID>/start を送ります。runc が名前空間・cgroup を作り、ネットワークにつなぎ、ENTRYPOINT + CMD を PID 1 として実行します。",
    "image": "準備のできたお部屋に、いよいよ住人が入居します。",
    "history": "docker start は、止めたコンテナをもう一度動かすためのコマンドとして初期からあります。",
    "kids": "組み立てておいたおもちゃのスイッチを入れるコマンドです。",
    "rhel": "docker run と同じです。",
}

COMMANDS["docker run (init)"] = {
    "title": "docker run --rm ― 初期化コンテナ (pre_start) を実行する",
    "syntax": "docker run --rm --volumes-from 本番コンテナ [オプション] イメージ コマンド",
    "oneline": "本番のコンテナを起動する前に、使い捨てのコンテナで準備作業 (データベースの初期化など) を 1 回だけ行います。",
    "how": (
        "貼り付けて Enter。準備作業の画面出力がそのまま表示され、終わるとプロンプトに戻ります。"
        "エラーが表示された場合 (終了コードが 0 以外) は、compose ならここで起動を中止します。次の STEP へ進まず、原因を確認してください。"
    ),
    "meaning": (
        "compose 5.3 (2026 年 7 月) で追加された pre_start (init コンテナ) を再現します。pre_start に書いたコマンドは、"
        "本番のコンテナを作った後・起動する前に、別の使い捨てコンテナで実行されます。\n"
        "--rm は終わったら自動で削除、--volumes-from は本番コンテナと同じボリューム・フォルダを同じ場所につなぐ、という意味です。"
        "準備で作ったファイルは、共有したボリュームを通して本番コンテナから見えます。ネットワークも本番と同じものにつなぎます。"
    ),
    "principle": (
        "compose 5.5 の実際の動きを調べると、init コンテナは「本番コンテナの ID を VolumesFrom に指定」「本番と同じネットワークと別名」"
        "「環境変数は本番の environment + pre_start の environment」「ユーザー・作業フォルダは pre_start の指定 (無ければイメージの既定)」で作られ、"
        "終了コードを確認したあとに削除されます。この STEP は同じ設定の docker run --rm です。"
    ),
    "image": "お店の開店前にだけ来て、棚を並べたり値札を付けたりして帰る「準備係さん」です。準備が終わってから、店員さん (本番コンテナ) が出勤します。",
    "history": (
        "Kubernetes には 2016 年ごろから initContainers (本番の前に動く準備用コンテナ) があり、データベースの移行などに広く使われてきました。"
        "compose では長い間、「準備用サービス + depends_on の service_completed_successfully」で代用していましたが、"
        "2026 年 7 月の Compose 5.3.0 で pre_start として正式に用意されました。"
    ),
    "kids": "本番の前に準備だけして帰る「お手伝いさん」のコンテナを動かすコマンドです。",
    "rhel": "docker run と同じです。",
}

COMMANDS["docker exec"] = {
    "title": "docker exec ― 動いているコンテナの中でコマンドを実行する",
    "syntax": "docker exec [オプション] コンテナ名 コマンド [引数...]",
    "oneline": "起動中のコンテナの中で、追加のコマンドを実行します (compose の post_start / pre_stop フック)。",
    "how": "貼り付けて Enter。コマンドの出力が表示されます。エラーなくプロンプトに戻れば成功です。",
    "meaning": (
        "docker exec は、すでに動いているコンテナの中で、もう 1 つ別のプログラムを動かすコマンドです。"
        "compose の post_start (起動直後に行う作業) と pre_stop (止める直前に行う作業) は、実際にこの仕組みで実行されています。"
        "--user で実行するユーザー、--env で追加の環境変数、--workdir で作業フォルダを指定できます。"
    ),
    "principle": (
        "dockerd に POST /containers/<ID>/exec (準備) と POST /exec/<ID>/start (実行) を送ります。runc exec が、"
        "コンテナの名前空間に「合流」(setns というシステムコール) して新しいプロセスを起動します。そのため、コンテナの中と同じファイル・"
        "同じネットワーク・同じ制限 (cgroup) で動きます。コマンドが終わると、そのプロセスだけが消えます。"
    ),
    "image": "営業中のお店に、お手伝いさんを 1 人送り込んで作業してもらうようなものです。作業が終わればお手伝いさんは帰り、お店はそのまま営業を続けます。",
    "history": "docker exec は 2014 年 10 月の Docker 1.3 で追加されました。compose のライフサイクルフック (post_start / pre_stop) は 2024 年 10 月の Compose 2.30.0 で追加されています。",
    "kids": "動いているコンテナの中に、もう 1 人お手伝いさんを入れて仕事をしてもらうコマンドです。",
    "rhel": "特にありません。",
}

COMMANDS["docker inspect (health)"] = {
    "title": "docker inspect の繰り返し ― healthy になるまで待つ",
    "syntax": "for C in コンテナ...; do while :; do ... docker inspect --format ... ; done; done",
    "oneline": "depends_on の「condition: service_healthy」を再現するため、相手のコンテナが健康 (healthy) になるまで 2 秒おきに確認して待ちます。",
    "how": (
        "かたまり全体 (for から最後の done まで) を貼り付けて Enter。「[待機] ... 待ちます」と表示され、"
        "準備ができると「[OK] ... は healthy です」と表示されて、プロンプトに戻ります。数十秒〜数分かかることがあります。\n"
        "・「[NG] ... の状態は running:unhealthy」などと出たら、相手のコンテナに問題があります。docker logs <名前> で原因を確認してください。\n"
        "・ずっと待ち続けて終わらないときは Ctrl+C で止めて、docker ps で状態を確認します。"
    ),
    "meaning": (
        "compose の depends_on に condition: service_healthy と書くと、compose は「依存先のヘルスチェックが合格 (healthy) するまで、"
        "こちらのコンテナを起動しない」という順番待ちをします。docker コマンドにはこの機能がないため、bash の繰り返し (while) で同じことをします。\n"
        "docker inspect --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}' は、"
        "コンテナの状態 (running など) と、ヘルスチェックの結果 (starting / healthy / unhealthy) を「running:healthy」のような形で取り出します。"
        "case 文で、healthy なら次へ、starting (確認中) なら 2 秒待って再確認、それ以外なら NG と表示して待つのをやめます。"
    ),
    "principle": (
        "ヘルスチェックは dockerd が行っています。interval (間隔) ごとに、コンテナの中でテスト用のコマンドを実行し (docker exec と同じ仕組み)、"
        "終了コード 0 なら合格、それ以外なら不合格と数えます。起動直後の start_period の間は不合格を数えず、"
        "retries 回続けて不合格になると unhealthy、1 回でも合格すると healthy になります。結果はコンテナの State.Health に記録され、"
        "docker inspect で読めます。--format の書き方は Go 言語のテンプレートで、{{if}} は「Health の情報があるときだけ」という条件です。"
    ),
    "image": "お店の前で「準備中」の札が「営業中」に変わるのを、2 秒ごとにのぞいて待っているようなものです。「本日休業」(unhealthy) の札が出たら、待つのをやめて理由を聞きに行きます。",
    "history": (
        "HEALTHCHECK は 2016 年 7 月の Docker 1.12 で登場しました。compose ではファイル形式 v2.1 (2016 年) から depends_on に condition: service_healthy を書けるようになりましたが、"
        "Swarm 向けのファイル形式 v3 (2017 年) では一度消えてしまい、多くの人が自作の「待ち合わせスクリプト」(wait-for-it.sh など) を使っていました。"
        "2020 年に始まった Compose Specification でこの書き方が正式に復活し、2021 年には service_completed_successfully も加わりました。"
    ),
    "kids": "友だちの準備ができるまで、2 秒ごとに「もういい？」と聞いて待つ係です。「まーだだよ」なら待ち、「もういいよ」が聞こえたら次へ進みます。",
    "rhel": "bash 5.1 (RHEL 9 の標準) でそのまま動きます。",
}

COMMANDS["docker wait"] = {
    "title": "docker wait ― コンテナが終わるのを待つ",
    "syntax": "EXIT_CODE=\"$(docker wait コンテナ名)\"",
    "oneline": "depends_on の「condition: service_completed_successfully」を再現するため、相手のコンテナが終わるまで待ち、終了コードを確かめます。",
    "how": "貼り付けて Enter。相手が終わると「終了コード: 0 (0 なら成功)」と表示されます。0 以外が表示されたら、その先へ進まず docker logs で原因を確認します。",
    "meaning": (
        "docker wait は、指定したコンテナが終了するまで待ち、終了コード (プログラムの最後の返事。0 は成功、それ以外は失敗) を表示します。"
        "$( ) はコマンドの出力を受け取る書き方で、それを EXIT_CODE という変数に入れて表示しています。"
        "compose の service_completed_successfully は「1 回だけ動いて終わる準備用のサービス (初期データの投入など) が成功してから次を起動する」ための設定です。"
    ),
    "principle": "dockerd に POST /containers/<ID>/wait を送り、コンテナの状態が「終了」に変わるまで返事を待ち続けます (ポーリングではなく、変化の通知を待つ方式)。",
    "image": "準備体操が終わるまで待って、「ちゃんとできた？」と結果 (終了コード) を聞くようなものです。",
    "history": "docker wait は 2013 年の Docker 登場時からあるコマンドです。compose の service_completed_successfully は 2021 年 (Compose 1.29) に加わりました。",
    "kids": "前の人のお仕事が終わるまで待って、「うまくいった？」と聞くコマンドです。0 は「うまくいったよ」の合図です。",
    "rhel": "特にありません。",
}

COMMANDS["docker ps"] = {
    "title": "docker ps ― コンテナの一覧と状態を見る",
    "syntax": "docker ps --all --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'",
    "oneline": "作ったコンテナが正しく動いているかを一覧で確かめます。",
    "how": "貼り付けて Enter。表の STATUS 列を確認します。",
    "meaning": (
        "docker ps はコンテナの一覧を表示します。--all を付けると止まっているものも表示します。--format の table は表の形、"
        "{{.Names}} などは表示する列 (名前・イメージ・状態・ポート) を選ぶ書き方です。\n"
        "STATUS の見方: 「Up 2 minutes (healthy)」= 動いていてヘルスチェックも合格、「Up ... (health: starting)」= 確認中、"
        "「Up ... (unhealthy)」= 動いているが不合格、「Exited (0)」= 正常に終わった (1 回だけ動くコンテナなら正常)、"
        "「Exited (1)」や「Exited (137)」= 異常終了 (137 はメモリ不足などで強制終了された印)、「Created」= 作っただけで起動していない。"
    ),
    "principle": "dockerd に GET /containers/json?all=1 を送り、返ってきた一覧を Go のテンプレートで表に整形しています。",
    "image": "マンションの管理人さんの「全部屋の状況ボード」を見るようなものです。",
    "history": "docker ps は Unix の ps (プロセスの一覧) にならった名前で、Docker の初期からあります。",
    "kids": "コンテナたちがみんな元気に動いているか、名簿でチェックするコマンドです。",
    "rhel": "特にありません。docker stats --no-stream で CPU やメモリの使用量も確認できます。",
}

COMMANDS["docker stop"] = {
    "title": "docker stop ― コンテナを止める",
    "syntax": "docker stop コンテナ名",
    "oneline": "コンテナに「止まってください」の合図を送り、終わるのを待ちます。",
    "how": "貼り付けて Enter。コンテナ名が表示されれば止まっています。",
    "meaning": (
        "docker stop は、コンテナの PID 1 に停止の合図 (シグナル。標準は SIGTERM、compose の stop_signal で変更可) を送ります。"
        "プログラムが後片付けをして自分で終わるのを待ち、stop_grace_period (--stop-timeout、標準 10 秒) 待っても終わらなければ、"
        "強制終了 (SIGKILL) します。依存されている側 (データベースなど) を最後に止めるため、起動と逆の順番で止めます。"
    ),
    "principle": "dockerd が containerd を通じてシグナルを送り、タイマーで待ちます。--restart の設定があっても、docker stop で止めたコンテナは自動では起動し直されません。",
    "image": "閉店の時間に「そろそろ閉めますよ」と声をかけ、片付けが終わるのを少し待ってから、それでも終わらなければ電気を消してしまうようなものです。",
    "history": "SIGTERM で後片付けを促し、時間切れなら SIGKILL という手順は、Unix のプロセス管理の昔からの作法です。",
    "kids": "「そろそろおしまいだよ」と声をかけて、コンテナにお片付けをしてもらうコマンドです。",
    "rhel": "特にありません。",
}

COMMANDS["docker rm"] = {
    "title": "docker rm ― コンテナを削除する",
    "syntax": "docker rm コンテナ名...",
    "oneline": "止めたコンテナを削除します (compose down と同じ)。名前付きボリュームは残ります。",
    "how": "貼り付けて Enter。削除したコンテナ名が表示されます。",
    "meaning": "コンテナの設定と書き込み用の層を削除します。名前付きボリュームは消えません。匿名ボリュームも、-v を付けない限り残ります (compose down と同じ動き)。",
    "principle": "dockerd に DELETE /containers/<ID> を送ります。",
    "image": "退去したお部屋を元の空き部屋に戻します。貸しロッカー (ボリューム) はそのまま残ります。",
    "history": "docker rm は Docker の初期からあるコマンドです。",
    "kids": "使い終わったおもちゃを分解して片付けるコマンドです。ロッカーの中身は残ります。",
    "rhel": "特にありません。",
}

COMMANDS["docker network rm"] = {
    "title": "docker network rm ― ネットワークを削除する",
    "syntax": "docker network rm ネットワーク名...",
    "oneline": "このプロジェクトで作ったネットワークを削除します (compose down と同じ)。",
    "how": "貼り付けて Enter。ネットワーク名が表示されれば削除できています。「has active endpoints」と出たら、まだつながっているコンテナがあります。",
    "meaning": "ブリッジとファイアウォールのルール、IP アドレスの範囲の予約が片付けられます。",
    "principle": "dockerd に DELETE /networks/<ID> を送ります。つながっているコンテナがあると削除できません。",
    "image": "使わなくなった内線電話網を撤去します。",
    "history": "docker network コマンドは 2015 年の Docker 1.9 から使えます。",
    "kids": "使い終わった道路を片付けるコマンドです。",
    "rhel": "特にありません。",
}

COMMANDS["docker volume rm"] = {
    "title": "docker volume rm ― ボリュームを削除する (データが消えます)",
    "syntax": "docker volume rm ボリューム名...",
    "oneline": "名前付きボリュームを削除します (compose down -v と同じ)。中のデータは元に戻せません。",
    "how": "必要なときだけ、行の先頭の # を外して実行します。",
    "meaning": "ボリュームの実体 (/var/lib/docker/volumes/<名前>) を削除します。データベースのデータなどが完全に消えるので注意してください。",
    "principle": "dockerd に DELETE /volumes/<名前> を送ります。使っているコンテナがあると削除できません。",
    "image": "貸しロッカーを中身ごと返却します。",
    "history": "docker volume コマンドは 2015 年の Docker 1.9 から使えます。",
    "kids": "ロッカーを中身ごと捨てるコマンドです。大事なものが入っていないか、よく確かめてから使います。",
    "rhel": "特にありません。",
}

COMMANDS["docker image rm"] = {
    "title": "docker image rm ― イメージを削除する",
    "syntax": "docker image rm イメージ名...",
    "oneline": "このプロジェクトでビルドしたイメージを削除します (compose down --rmi local と同じ)。",
    "how": "必要なときだけ、行の先頭の # を外して実行します。",
    "meaning": "イメージの名前 (タグ) を外し、どこからも使われなくなったレイヤーを削除してディスクを空けます。",
    "principle": "dockerd に DELETE /images/<名前> を送ります。そのイメージから作ったコンテナが残っていると削除できません。",
    "image": "使わなくなったお部屋セットを倉庫から処分します。",
    "history": "docker rmi / docker image rm は Docker の初期からあります (image rm の書き方は 2017 年の 1.13 から)。",
    "kids": "もう使わないおもちゃのもとを捨てるコマンドです。",
    "rhel": "特にありません。docker system df で Docker が使っているディスク容量を確認できます。",
}

STEP_KIND_TO_COMMAND = {
    "prepare": "docker version",
    "network_external": "docker network inspect",
    "network_create": "docker network create",
    "volume_external": "docker volume inspect",
    "volume_create": "docker volume create",
    "pull": "docker pull",
    "build": "docker build",
    "healthcheck_image": "docker build (healthcheck)",
    "wait_healthy": "docker inspect (health)",
    "wait_completed": "docker wait",
    "run": "docker run",
    "create": "docker create",
    "inject": "docker cp",
    "init": "docker run (init)",
    "start": "docker start",
    "post_start": "docker exec",
    "pre_stop": "docker exec",
    "check": "docker ps",
    "stop": "docker stop",
    "rm": "docker rm",
    "network_rm": "docker network rm",
    "volume_rm": "docker volume rm",
    "image_rm": "docker image rm",
}
