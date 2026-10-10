"""解説用の知識ベース (2): オプションごとの説明。

OPTIONS[(コマンド, オプション)] または OPTIONS[("*", オプション)] =
    (compose での書き方, 意味・しくみ, 小学生向けのたとえ)
"""

OPTIONS = {}


def _add(cmds, flag, compose, meaning, kids):
    for cmd in cmds.split(","):
        OPTIONS[(cmd.strip(), flag)] = (compose, meaning, kids)


RUN = "docker run,docker create,docker run (init)"

# ---------------------------------------------------------------------------
# docker run / create : 基本
# ---------------------------------------------------------------------------
_add(RUN, "--detach", "docker compose up -d の -d",
     "コンテナを裏側 (バックグラウンド) で動かし、コマンドはすぐに終わってプロンプトに戻ります。付けないと、コンテナの画面出力がターミナルに流れ続け、"
     "Ctrl+C でコンテナも止まってしまいます。出力はあとから docker logs で見られます。",
     "おもちゃのスイッチを入れたら、見張っていなくても勝手に動き続けるようにします。")
_add(RUN, "--name", "container_name (無ければ <プロジェクト>-<サービス>-<番号>)",
     "コンテナに名前を付けます。名前は同じホストの中で 1 つだけで、docker logs や docker stop で使えるほか、ユーザー定義ネットワークでは"
     "その名前で相手を呼べます (内蔵 DNS がコンテナ名を IP に変換します)。compose v2 以降は「プロジェクト-サービス-番号」とハイフンでつなぎます"
     " (昔の compose v1 はアンダースコア _ でした)。",
     "コンテナに名札を付けます。名札の名前で呼んだり、止めたりできます。")
_add(RUN, "--hostname", "hostname",
     "コンテナの中から見えるコンピューター名 (ホスト名) を決めます。指定しないとコンテナ ID の先頭 12 文字になります。"
     "UTS 名前空間という仕組みで、コンテナごとに別のホスト名を持てます。",
     "お部屋の表札に書く名前を決めます。")
_add(RUN, "--domainname", "domainname",
     "コンテナのドメイン名 (ホスト名の後ろに付く example.com のような部分) を決めます。",
     "表札に書く住所の部分です。")
_add(RUN, "--restart", "restart / deploy.restart_policy",
     "コンテナが止まったときに、dockerd が自動で起動し直すかどうかのルールです。no (しない・標準)、always (いつでも)、"
     "unless-stopped (docker stop で止めた場合を除いて)、on-failure[:回数] (異常終了したときだけ、回数まで) があります。"
     "起こし直す間隔は 100 ミリ秒から始まって倍々に伸びます (最大 1 分)。Docker 自体が再起動したとき (サーバーの再起動など) にも、"
     "always と unless-stopped のコンテナは自動で起動します。compose の deploy.restart_policy が書かれている場合は、そちらが優先されます "
     "(condition: any → always、on-failure + max_attempts → on-failure:回数、none → no)。",
     "コンテナが転んだら、管理人さんが起こしてあげるかどうかの約束です。")
_add(RUN, "--init", "init: true",
     "コンテナの PID 1 (最初のプロセス) として、小さなお世話係プログラム docker-init (中身は tini) を置き、その子どもとして本来のプログラムを動かします。"
     "Linux では PID 1 が「親を亡くしたプロセス (ゾンビ)」を片付ける役目を持ちますが、ふつうのアプリはそれをしないため、ゾンビが溜まったり、"
     "停止の合図 (SIGTERM) を無視してしまったりします。init がそれを肩代わりします (Docker 1.13、2017 年から)。",
     "お部屋に「お世話係」を 1 人置いて、後片付けや連絡係をしてもらいます。")
_add(RUN, "--init=false", "init: false", "init を使わないことをはっきり指定します (dockerd の設定で init が標準になっている場合に意味があります)。", "お世話係は置きません。")
_add(RUN, "--user", "user",
     "コンテナの中のプログラムを、どのユーザー (UID) とグループ (GID) で動かすかを決めます。例: 1000:1000、appuser。"
     "指定しないとイメージの USER (無ければ root) で動きます。root 以外で動かすと、万一乗っ取られても被害を小さくできます。"
     "バインドマウントしたホストのフォルダの読み書きは、この UID/GID の権限で判断されます。",
     "お部屋の中で「だれ」として作業するかを決めます。")
_add(RUN, "--group-add", "group_add",
     "コンテナのユーザーに、追加のグループ (補助グループ) を足します。共有フォルダの書き込み権限を、グループ番号で合わせたいときに使います。",
     "「この係にも入っています」というバッジを追加で付けます。")
_add(RUN, "--workdir", "working_dir",
     "コンテナの中の作業フォルダ (カレントディレクトリ) を決めます。相対パスはここが基準になります。イメージの WORKDIR より優先されます。",
     "お部屋の中で、最初にどの机で作業するかを決めます。")

# ---------------------------------------------------------------------------
# ネットワーク
# ---------------------------------------------------------------------------
_add(RUN, "--network", "networks / network_mode",
     "コンテナをどのネットワークにつなぐかを決めます。ネットワーク名を書けばそのネットワークへ、host ならホストのネットワークをそのまま使用、"
     "none ならつながない、container:<名前> なら別のコンテナとネットワークを共有します (compose の network_mode: service:<サービス>)。\n"
     "name=ネットワーク名,alias=別名,ip=IP アドレス のような長い書き方 (Docker 25 以降) を使うと、1 回の docker run で複数のネットワークにつなぎ、"
     "それぞれに別名や IP を設定できます。compose は priority (優先度) が高い順、同じなら名前の順にネットワークを並べ、最初のものをメインにします。",
     "コンテナをどの道路 (ネットワーク) につなぐかを決めます。")
_add(RUN, "--network-alias", "networks.<名前>.aliases (サービス名は compose が自動で追加)",
     "そのネットワークの中だけで使える、コンテナの別名を付けます。内蔵 DNS がこの名前を IP アドレスに変換するので、ほかのコンテナから"
     "http://<別名>:ポート で呼べます。compose はサービス名を必ず別名にするため、ここでもサービス名を付けています。"
     "同じ別名を複数のコンテナに付けると、DNS は順番に答えを返します (かんたんな負荷分散)。",
     "電話帳に「あだ名」を登録して、あだ名でも電話がかかるようにします。")
_add(RUN, "--ip", "networks.<名前>.ipv4_address", "このネットワークでのコンテナの IPv4 アドレスを固定します。ネットワークに subnet を指定している必要があります。", "お部屋の番号を決め打ちにします。")
_add(RUN, "--ip6", "networks.<名前>.ipv6_address", "このネットワークでのコンテナの IPv6 アドレスを固定します。", "お部屋の番号 (新しい形式) を決め打ちにします。")
_add(RUN, "--link-local-ip", "networks.<名前>.link_local_ips", "リンクローカルアドレス (同じ線の中だけで使うアドレス) を追加します。", "近所だけで通じる呼び名を追加します。")
_add(RUN, "--mac-address", "mac_address / networks.<名前>.mac_address", "ネットワークカードの MAC アドレス (機器ごとの番号) を固定します。ライセンスが MAC アドレスに結びついたソフトなどで使います。", "機械に付いている製造番号を決め打ちにします。")
_add(RUN, "--link", "links / external_links",
     "古い仕組み (レガシーリンク) で、別のコンテナを指定の名前で呼べるようにします。今はネットワーク別名で十分なため、compose でもほとんど使いません。",
     "昔のやり方で、ほかのお部屋への直通電話を引きます。")
_add(RUN, "--dns", "dns", "コンテナが名前解決 (名前 → IP アドレス) に使う DNS サーバーを指定します。ユーザー定義ネットワークでは、内蔵 DNS (127.0.0.11) が知らない名前をここに問い合わせます。", "わからない名前を聞きに行く「電話番号案内」の窓口を決めます。")
_add(RUN, "--dns-search", "dns_search", "短い名前 (例: db) を引くときに、後ろへ補うドメイン (例: example.local → db.example.local) を指定します。", "苗字を省略して呼んだときに、補う苗字を決めます。")
_add(RUN, "--dns-option", "dns_opt", "/etc/resolv.conf の options 行 (timeout:2 や use-vc など、名前解決の細かい動き) を指定します。", "電話番号案内への聞き方のくせを決めます。")
_add(RUN, "--add-host", "extra_hosts",
     "コンテナの /etc/hosts に「名前 IP アドレス」の行を書き足します。DNS に登録されていない相手を名前で呼びたいときに使います。"
     "host-gateway と書くと、ホスト自身の IP アドレス (コンテナから見た出口) に置き換わります (Docker 20.10 から)。",
     "お部屋の電話帳に、手書きで番号を書き足します。")

# ---------------------------------------------------------------------------
# ポート
# ---------------------------------------------------------------------------
_add(RUN, "--publish", "ports",
     "ホスト (RHEL) のポートに届いた通信を、コンテナのポートへ転送します。書き方は [ホストのIP:]ホストのポート:コンテナのポート[/udp]。"
     "ホスト側を省略すると空いているポートが自動で選ばれます。\n"
     "しくみ: dockerd がファイアウォール (iptables / nftables) に DNAT (宛先の書き換え) のルールを入れ、さらに docker-proxy という小さな中継プログラムも起動します。"
     "外から http://<RHEL の IP>:8080 に来た通信は、コンテナの IP:80 に書き換えられて届きます。"
     "IP を 127.0.0.1 にすると、そのサーバーの中からしか接続できなくなります (外には公開しない)。",
     "マンションの正面玄関の「〇番窓口」に来たお客さんを、お部屋の「〇番ドア」へ案内する道案内です。")
_add(RUN, "--expose", "expose",
     "コンテナがそのポートを使うことを宣言します (記録されるだけで、ホストには公開されません)。同じネットワークのコンテナからは、宣言しなくても接続できます。",
     "「このドアを使っています」と貼り紙をするだけで、玄関からの案内はしません。")

# ---------------------------------------------------------------------------
# ボリューム・マウント
# ---------------------------------------------------------------------------
_add(RUN, "--volume", "volumes (短い書き方)",
     "ホストのフォルダ・ファイル、または名前付きボリュームを、コンテナの中の場所につなぎます (マウント)。書き方は 元:コンテナ内の場所[:ro][,z]。"
     "元が / や ./ で始まればホストのパス (バインドマウント)、名前ならボリュームです。:ro は読み取り専用、:z / :Z は SELinux 用のラベル付けです。"
     "ホスト側のフォルダが無いときは空のフォルダが自動で作られます (compose の短い書き方と同じ動き)。"
     "compose v5 も、短い書き方のバインドと、オプションの無い名前付きボリュームは、この形 (Docker API の Binds) で渡しています。",
     "お部屋の壁に、外の引き出し (ホストのフォルダ) やロッカー (ボリューム) へ通じる扉を付けます。")
_add(RUN, "--mount", "volumes (長い書き方) / secrets / configs / tmpfs",
     "マウントを key=value で 1 つずつ指定する、読みやすく厳密な書き方です (Docker 17.06 から)。type=bind (ホストのパス)、type=volume (ボリューム)、"
     "type=tmpfs (メモリ上)、type=image (イメージの中身。Docker 28 から) があり、source= (元)、target= (コンテナ内の場所)、readonly、"
     "bind-propagation、volume-nocopy、volume-subpath、tmpfs-size などを指定できます。"
     "--volume と違い、type=bind でホスト側が無いとエラーになります (bind-create-src を付けると作成)。target だけの type=volume は、名前の無い (匿名) ボリュームを新しく作ります。",
     "扉の付け方を、項目ごとにくわしく指定した注文書です。")
_add(RUN, "--tmpfs", "tmpfs",
     "メモリの上に一時的なファイル置き場 (tmpfs) を作り、指定した場所につなぎます。とても速く、コンテナを止めると中身は消えます。"
     "size= で大きさの上限、mode= で権限を指定できます。--read-only と組み合わせて、書き込みが必要な /tmp だけを用意するのによく使います。",
     "消えてもいいメモを書く「ホワイトボード」を部屋に置きます。電気を消すと (止めると) 消えます。")
_add(RUN, "--volumes-from", "volumes_from",
     "別のコンテナが使っているボリューム・バインドマウントを、同じ場所に全部つなぎます。compose の volumes_from に :ro を付けても、"
     "compose v5 は実際には付けずに Docker へ渡すため (このツールの検証で確認)、ここでも同じ動きにしています。",
     "となりのお部屋と同じロッカーを、同じ場所に付けてもらいます。")

# ---------------------------------------------------------------------------
# 環境変数・ラベル
# ---------------------------------------------------------------------------
_add(RUN, "--env", "environment (と env_file の中身)",
     "コンテナの中のプログラムに渡す環境変数 (名前=値 の設定メモ) を指定します。データベースの接続先やパスワード、動作モードなどを、"
     "イメージを作り直さずに切り替えられます。値を書かずに名前だけ (--env NAME) にすると、実行するシェルにある同じ名前の変数の値が渡されます。\n"
     "compose は compose ファイルの ${VAR} を .env や OS の環境変数で展開してから値を決めます。この手順の値は、展開済みの最終的な値です。"
     "同じ名前が複数あると、後に書いたものが勝ちます (environment が env_file より優先、という compose の規則と同じ順に並べています)。",
     "お部屋に置いておく「設定メモ」です。プログラムはこのメモを読んで動き方を変えます。")
_add(RUN, "--env-file", "env_file",
     "環境変数を書いたファイル (1 行に 名前=値) をまとめて読み込みます。ただし docker の --env-file は、compose の env_file と読み方が少し違います "
     "(クォート \"...\" を外さない、# のコメントや ${VAR} の展開をしない など)。このツールは、両方で同じ値になると確認できたファイルだけを --env-file で渡し、"
     "違いが出るファイルは展開済みの値を --env で 1 つずつ渡しています。",
     "設定メモをまとめた「ノート」を 1 冊渡します。")
_add(RUN, "--label", "labels / label_file",
     "コンテナに目印 (ラベル = キーと値の組) を付けます。動作には影響せず、docker ps --filter label=... で探したり、監視ツールが読んだりします。"
     "compose 自身も com.docker.compose.project などのラベルを付けて「どのプロジェクトのコンテナか」を管理しています "
     "(このツールは --compose-labels を指定したときだけ同じラベルを付けます)。",
     "コンテナに貼るシール (目印) です。")
_add(RUN, "--annotation", "annotations", "OCI ランタイム (runc など) に渡す注釈です。特殊なランタイムの設定に使います。", "大工さん (ランタイム) へのメモ書きです。")

# ---------------------------------------------------------------------------
# セキュリティ・名前空間
# ---------------------------------------------------------------------------
_add(RUN, "--privileged", "privileged",
     "特権モード。ほぼすべての capabilities とホストのデバイスへのアクセスを許し、seccomp などの制限も外します。コンテナの壁がとても薄くなるので、"
     "本当に必要なとき (ハードウェアを直接さわるなど) だけ使います。",
     "管理人さんの合鍵を全部渡してしまうようなものです。とても危ないので、めったに使いません。")
_add(RUN, "--read-only", "read_only",
     "コンテナのルートファイルシステムを読み取り専用にします。書き込めるのはボリューム・バインドマウント・tmpfs だけになり、"
     "万一乗っ取られても中のプログラムを書き換えられにくくなります。",
     "お部屋の壁や家具に落書き禁止のシールを貼ります。書いていいのはホワイトボードだけです。")
_add(RUN, "--cap-add", "cap_add",
     "Linux の capabilities (root の特権を 40 個ほどに細かく分けたもの) を追加で許可します。Docker は標準で 14 個 (CHOWN, NET_BIND_SERVICE など) だけを許可しています。"
     "例: NET_ADMIN (ネットワーク設定の変更)、SYS_PTRACE (他のプロセスの調査)。",
     "必要な合鍵を 1 本だけ追加で渡します。")
_add(RUN, "--cap-drop", "cap_drop", "許可されている capabilities を取り上げます。ALL を指定してから必要なものだけ --cap-add すると、いちばん安全です。", "使わない合鍵を返してもらいます。")
_add(RUN, "--security-opt", "security_opt",
     "セキュリティの細かい設定です。no-new-privileges:true は、setuid などで今より強い権限を得ることを禁止します。seccomp=プロファイル は使えるシステムコールを制限、"
     "label=... は SELinux のラベル、apparmor=... は AppArmor (Ubuntu 系) の設定です。",
     "お部屋のルールを追加します (例: 「えらくなる魔法は使えません」)。")
_add(RUN, "--userns", "userns_mode", "ユーザー名前空間 (コンテナの root をホストでは一般ユーザーとして扱う仕組み) の設定です。host を指定すると無効にします。", "お部屋の中の「王様」が、外では普通の人になる仕組みの設定です。")
_add(RUN, "--pid", "pid", "PID 名前空間の設定です。host にするとホストのすべてのプロセスが見えます。container:<名前> で別のコンテナと共有します。", "ほかの部屋の住人が見えるかどうかを決めます。")
_add(RUN, "--ipc", "ipc", "IPC 名前空間 (共有メモリなど、プロセスどうしの連絡手段) の設定です。shareable / container:<名前> / host などがあります。", "部屋どうしの連絡ノートを共有するかどうかです。")
_add(RUN, "--uts", "uts", "UTS 名前空間 (ホスト名) の設定です。host にするとホストと同じホスト名になります。", "表札をマンションと同じにするかどうかです。")
_add(RUN, "--cgroupns", "cgroup", "cgroup 名前空間の設定です。private (コンテナ専用、cgroup v2 の標準) か host です。", "メーター盤を自分専用にするかどうかです。")
_add(RUN, "--cgroup-parent", "cgroup_parent", "コンテナの cgroup を、指定した親 cgroup の下に作ります。複数のコンテナをまとめて資源管理したいときに使います。", "ブレーカーを、どの分電盤の下に付けるかを決めます。")
_add(RUN, "--device", "devices", "ホストのデバイスファイル (/dev/ttyUSB0 など) をコンテナで使えるようにします。:rwm は読み・書き・作成の許可です。vendor/class=name の形は CDI (デバイスの共通定義) です。", "外の機械 (USB 機器など) をお部屋につなぎます。")
_add(RUN, "--device-cgroup-rule", "device_cgroup_rules", "デバイスの使用許可ルール (例: c 189:* rmw) を cgroup に追加します。", "どの機械を使っていいかのルールを追加します。")
_add(RUN, "--gpus", "gpus / deploy.resources.reservations.devices",
     "GPU (画像処理や AI 計算用のチップ) をコンテナで使えるようにします。all ですべて、count=2 で 2 個、device=0,1 で番号指定。"
     "ホストに NVIDIA のドライバーと NVIDIA Container Toolkit が必要です。",
     "計算が得意な「助っ人チップ」をお部屋で使えるようにします。")
_add(RUN, "--sysctl", "sysctls", "コンテナの中だけで有効なカーネルの設定値を変えます (例: net.core.somaxconn=1024 で接続待ちの行列を長くする)。ネットワーク関係など、名前空間ごとに分かれている項目だけ変更できます。", "お部屋の中だけの「機械の調整つまみ」を回します。")
_add(RUN, "--ulimit", "ulimits",
     "1 つのプロセスが使える資源の上限 (ulimit) を決めます。nofile=ソフト:ハード で同時に開けるファイル数、nproc でプロセス数など。"
     "Docker 29 では nofile の標準 (ソフト上限) が 1024 なので、たくさんの接続を扱うサーバーは上げておくことが大切です。",
     "一度に机に広げていい本の数の上限です。")
_add(RUN, "--runtime", "runtime", "コンテナを動かす OCI ランタイムを選びます (runc が標準。gVisor の runsc や NVIDIA の nvidia などに切り替えられます)。", "お部屋を作る大工さんを指名します。")
_add(RUN, "--isolation", "isolation", "分離の方式を選びます。主に Windows コンテナ用 (process / hyperv) で、Linux では default だけです。", "部屋の作り方の種類です (主に Windows 用)。")
_add(RUN, "--storage-opt", "storage_opt", "ストレージドライバーへの設定です (例: size=10G でコンテナの書き込み層の大きさを制限。対応するドライバーのみ)。", "お部屋の床の広さを決めます。")
_add(RUN, "--oom-kill-disable", "oom_kill_disable", "メモリ不足 (OOM) のときに、このコンテナのプロセスを強制終了させないようにします。--memory と一緒に使わないとホスト全体が危険になります。", "メモリが足りなくなっても、この部屋の住人は追い出さない約束です。")
_add(RUN, "--oom-score-adj", "oom_score_adj", "メモリ不足のときに強制終了される選ばれやすさを調整します (-1000〜1000。大きいほど選ばれやすい)。", "いざというとき、先に退去してもらう順番を決めます。")

# ---------------------------------------------------------------------------
# 資源の制限
# ---------------------------------------------------------------------------
_add(RUN, "--cpus", "cpus / deploy.resources.limits.cpus",
     "使える CPU を「何個分」で制限します (例: 0.5 なら 1 個の半分)。cgroup v2 の cpu.max という設定に変換され、100 ミリ秒ごとに使える時間が決まります。",
     "使っていい計算の力を「半人前」などと決めます。")
_add(RUN, "--cpu-shares", "cpu_shares", "CPU が混み合ったときの取り分の重みです (標準 1024)。空いているときは制限されません。", "混雑したときの「取り分の割合」です。")
_add(RUN, "--cpu-period", "cpu_period", "CPU の使用時間を数える周期 (マイクロ秒) です。--cpu-quota と組み合わせて使います。", "計算の時間を数える区切りの長さです。")
_add(RUN, "--cpu-quota", "cpu_quota", "1 周期のうち使える CPU 時間 (マイクロ秒) です。", "区切りの中で使っていい時間です。")
_add(RUN, "--cpu-rt-period", "cpu_rt_period", "リアルタイム処理の周期 (マイクロ秒) です。", "特別に急ぐ仕事の時間の区切りです。")
_add(RUN, "--cpu-rt-runtime", "cpu_rt_runtime", "リアルタイム処理に使える時間 (マイクロ秒) です。", "特別に急ぐ仕事に使える時間です。")
_add(RUN, "--cpuset-cpus", "cpuset", "使ってよい CPU の番号を決めます (例: 0-3 や 0,2)。", "使っていい計算機の番号を決めます。")
_add(RUN, "--cpu-count", "cpu_count", "Windows コンテナ用: 使える CPU の数です。", "(Windows 用) 計算機の数です。")
_add(RUN, "--cpu-percent", "cpu_percent", "Windows コンテナ用: 使える CPU の割合です。", "(Windows 用) 計算の力の割合です。")
_add(RUN, "--memory", "mem_limit / deploy.resources.limits.memory",
     "使えるメモリの上限です (例: 512m、1g)。cgroup v2 の memory.max に設定され、超えるとカーネルの OOM キラーがコンテナ内のプロセスを強制終了します "
     "(docker ps で Exited (137) と表示されます)。",
     "使っていい机の広さ (メモリ) の上限です。はみ出すと退場になります。")
_add(RUN, "--memory-reservation", "mem_reservation / deploy.resources.reservations.memory", "ホストのメモリが足りなくなってきたときに、できるだけ確保しておく量 (ソフト制限) です。", "混んできても、ここまでは確保してあげる机の広さです。")
_add(RUN, "--memory-swap", "memswap_limit", "メモリとスワップ (ディスクを使った予備のメモリ) を合わせた上限です。-1 で無制限。", "予備の机も合わせた広さの上限です。")
_add(RUN, "--memory-swappiness", "mem_swappiness", "スワップの使いやすさ (0〜100) です。cgroup v2 (RHEL 9) では使えません。", "予備の机をどれくらい使うかのくせです。")
_add(RUN, "--pids-limit", "pids_limit / deploy.resources.limits.pids", "コンテナの中で同時に動かせるプロセスの数の上限です。プロセスを無限に増やす攻撃 (フォーク爆弾) を防げます。", "お部屋に入れる人数の上限です。")
_add(RUN, "--shm-size", "shm_size", "共有メモリ (/dev/shm) の大きさです。標準は 64MB で、データベースやブラウザーを動かすときに足りなくなることがあります。", "みんなで使う作業台の大きさです。")
_add(RUN, "--blkio-weight", "blkio_config.weight", "ディスクの読み書きが混んだときの取り分の重みです (10〜1000)。", "ディスクの順番待ちの優先度です。")
_add(RUN, "--blkio-weight-device", "blkio_config.weight_device", "デバイスごとのディスクの取り分の重みです。", "ディスクごとの優先度です。")
_add(RUN, "--device-read-bps", "blkio_config.device_read_bps", "デバイスからの読み込みの速さの上限 (バイト/秒) です。", "読み込みの速さの上限です。")
_add(RUN, "--device-write-bps", "blkio_config.device_write_bps", "デバイスへの書き込みの速さの上限 (バイト/秒) です。", "書き込みの速さの上限です。")
_add(RUN, "--device-read-iops", "blkio_config.device_read_iops", "デバイスからの読み込み回数の上限 (回/秒) です。", "読み込み回数の上限です。")
_add(RUN, "--device-write-iops", "blkio_config.device_write_iops", "デバイスへの書き込み回数の上限 (回/秒) です。", "書き込み回数の上限です。")

# ---------------------------------------------------------------------------
# ログ・ヘルスチェック・停止
# ---------------------------------------------------------------------------
_add(RUN, "--log-driver", "logging.driver",
     "コンテナの画面出力 (標準出力・標準エラー) をどこへ保存するかを決めます。json-file (標準。JSON 形式のファイル)、local (圧縮つきの効率的な形式)、"
     "journald (RHEL の systemd ジャーナル)、syslog、awslogs (CloudWatch Logs)、none (保存しない) などがあります。",
     "お部屋の「日記帳」の種類を決めます。")
_add(RUN, "--log-opt", "logging.options",
     "ログドライバーへの設定です。json-file なら max-size=10m (1 ファイルの大きさ) と max-file=3 (残すファイル数) でログが際限なく増えるのを防げます。",
     "日記帳のページ数などのルールです。")
_add(RUN, "--no-healthcheck", "healthcheck.disable: true / test: [\"NONE\"]", "イメージに HEALTHCHECK が書かれていても、ヘルスチェックを行わないようにします。", "元気チェックをお休みします。")
_add(RUN, "--health-cmd", "healthcheck.test (CMD-SHELL)",
     "ヘルスチェック (健康診断) で実行するコマンドです。dockerd が定期的にコンテナの中で /bin/sh -c 'コマンド' を実行し、終了コード 0 なら合格です。"
     "シェル形式なので、イメージに /bin/sh が無いと使えません (その場合このツールは派生イメージで exec 形式を再現します)。",
     "「元気？」と聞くときの質問の中身です。")
_add(RUN, "--health-interval", "healthcheck.interval", "ヘルスチェックの間隔です (標準 30 秒)。", "何秒おきに「元気？」と聞くかです。")
_add(RUN, "--health-timeout", "healthcheck.timeout", "1 回のチェックの制限時間です (標準 30 秒)。超えたら不合格です。", "返事を待つ時間の長さです。")
_add(RUN, "--health-start-period", "healthcheck.start_period", "起動直後の猶予期間です。この間の不合格は数えません (起動に時間がかかるアプリ用)。", "起きたばかりの間は、返事がなくても大目に見る時間です。")
_add(RUN, "--health-start-interval", "healthcheck.start_interval", "猶予期間中だけ使う、短いチェック間隔です (Docker 25 から)。早く healthy にして、待っている側を早く起動できます。", "起きたばかりの間は、こまめに様子を見に行きます。")
_add(RUN, "--health-retries", "healthcheck.retries", "何回続けて不合格になったら unhealthy (不健康) とするかです (標準 3 回)。", "何回続けて返事がなかったら「具合が悪い」とするかです。")
_add(RUN, "--stop-signal", "stop_signal", "docker stop で送る停止の合図 (シグナル) を決めます。標準は SIGTERM。nginx の SIGQUIT のように、アプリによって行儀よく終わる合図が違います。", "「おしまいだよ」の合図の言葉を決めます。")
_add(RUN, "--stop-timeout", "stop_grace_period",
     "停止の合図を送ってから、強制終了 (SIGKILL) するまで待つ秒数です (標準 10 秒)。compose の stop_grace_period (例: 1m30s) を秒に直した値です。",
     "お片付けを待ってあげる時間です。")
_add(RUN, "--tty", "tty", "疑似ターミナル (TTY) を割り当てます。色付きの表示や対話的なプログラムで使います。", "お部屋に画面とキーボードを置きます。")
_add(RUN, "--interactive", "stdin_open", "標準入力 (キーボードからの入力) を開いたままにします。", "お部屋への「話しかけ口」を開けておきます。")
_add(RUN, "--platform", "platform", "どの CPU 向けのイメージで動かすかを指定します (例: linux/amd64、linux/arm64)。", "どの種類の機械用のセットを使うかを決めます。")
_add(RUN, "--pull", "pull_policy", "イメージをいつダウンロードするかです。missing (無いときだけ・標準)、always (毎回)、never (しない)。", "部品を取り寄せるタイミングです。")
_add(RUN, "--use-api-socket", "use_api_socket", "Docker Engine の API ソケットと、ログイン情報をコンテナに渡し、コンテナの中から docker コマンドを使えるようにします。とても強い権限です。", "管理人室への直通電話をお部屋に引きます (強い権限なので注意)。")
_add(RUN, "--entrypoint", "entrypoint",
     "イメージの ENTRYPOINT (必ず最初に実行されるプログラム) を置き換えます。docker の --entrypoint には 1 語しか書けないため、compose の entrypoint が"
     "複数の語でできている場合、2 語目以降はイメージ名の後ろに引数として書きます (最終的に実行されるコマンドは同じです)。"
     "entrypoint を指定すると、イメージの CMD は使われなくなります (compose も docker も同じ)。",
     "お部屋に入ったら最初にすることを、別のことに変えます。")
_add("docker run (init)", "--rm", "(pre_start の後片付け)", "コンテナが終わったら、自動で削除します。使い捨ての作業に便利です。", "使い終わったら自動でお片付けします。")
_add("docker run (init)", "--volumes-from", "(pre_start: 本番と同じマウント)", "本番コンテナと同じボリューム・バインドマウントを、同じ場所につなぎます。準備作業の結果が本番から見えるようになります。", "本番のお部屋と同じロッカーを使います。")

# ---------------------------------------------------------------------------
# docker build
# ---------------------------------------------------------------------------
BUILD = "docker build,docker build (healthcheck)"
_add(BUILD, "--file", "build.dockerfile / dockerfile_inline", "使う Dockerfile (設計図) を指定します。省略するとビルドコンテキストの中の Dockerfile です。- は「標準入力から読む」です。", "どの設計図を使うかを指定します。")
_add(BUILD, "--target", "build.target", "マルチステージの Dockerfile で、FROM ... AS 名前 の「名前」の段階までを作ります。開発用・本番用を作り分けるのに使います。", "設計図の途中の段階までで止めます。")
_add(BUILD, "--build-arg", "build.args", "Dockerfile の ARG (ビルド時の変数) に値を渡します。バージョン番号やベースイメージの切り替えに使います。イメージの履歴に残るので、パスワードは渡さないでください。", "設計図の空欄に書き込む値です。")
_add(BUILD, "--label", "build.labels", "できたイメージにラベル (目印) を付けます。", "完成品に貼るシールです。")
_add(BUILD, "--secret", "build.secrets", "ビルドの間だけ使える秘密 (パスワードや証明書) を渡します。Dockerfile の RUN --mount=type=secret,id=名前 で、その命令の間だけ /run/secrets/名前 として読めます。イメージにもキャッシュにも残りません。", "作業中だけ見せて、すぐにしまう秘密の手紙です。")
_add(BUILD, "--ssh", "build.ssh", "ビルド中に SSH エージェント (鍵) を使えるようにします。非公開の Git リポジトリからの取得などに使います。", "作業中だけ使える合鍵を貸します。")
_add(BUILD, "--build-context", "build.additional_contexts", "追加の材料置き場に名前を付けて渡します。Dockerfile の COPY --from=名前 や FROM 名前 で参照できます。", "材料箱をもう 1 つ追加で渡します。")
_add(BUILD, "--cache-from", "build.cache_from", "ビルドの途中結果 (キャッシュ) を、指定した場所 (レジストリやフォルダ) から読み込みます。CI で毎回ゼロから作らずに済みます。", "前に作った作り置きを取り寄せます。")
_add(BUILD, "--cache-to", "build.cache_to", "ビルドの途中結果 (キャッシュ) を、指定した場所へ書き出します。", "作り置きを保存しておきます。")
_add(BUILD, "--network", "build.network", "ビルド中の RUN 命令が使うネットワークです (default / host / none)。", "工場で作業するときに使う道路です。")
_add(BUILD, "--add-host", "build.extra_hosts", "ビルド中の /etc/hosts に行を書き足します。", "工場の電話帳に番号を書き足します。")
_add(BUILD, "--shm-size", "build.shm_size", "ビルド中の共有メモリ (/dev/shm) の大きさです。", "工場の作業台の大きさです。")
_add(BUILD, "--ulimit", "build.ulimits", "ビルド中のプロセスの資源の上限です。", "工場で一度に使える道具の数です。")
_add(BUILD, "--no-cache", "build.no_cache", "キャッシュを使わず、すべての手順を最初からやり直します。", "作り置きを使わず、全部作り直します。")
_add(BUILD, "--no-cache-filter", "build.no_cache_filter", "指定したステージだけキャッシュを使いません。", "一部だけ作り直します。")
_add(BUILD, "--pull", "build.pull", "FROM のベースイメージを、手元にあっても毎回レジストリから確認して取り直します。", "土台の部品をいつも最新に取り寄せます。")
_add(BUILD, "--platform", "build.platforms / platform", "どの CPU 向けのイメージを作るかを指定します。複数指定 (linux/amd64,linux/arm64) は別のビルダーが必要です。", "どの機械用に作るかを決めます。")
_add(BUILD, "--allow", "build.privileged / build.entitlements", "特別な権限 (security.insecure、network.host など) をビルドに許可します。ビルダー側の許可も必要です。", "工場で特別な作業を許可します。")
_add(BUILD, "--isolation", "build.isolation", "分離の方式 (Windows 用) です。", "(Windows 用) 作り方の種類です。")
_add(BUILD, "--tag", "image (無ければ <プロジェクト>-<サービス>)", "できたイメージに名前 (リポジトリ:タグ) を付けます。タグを省略すると latest になります。docker run ではこの名前で指定します。", "完成品に名札を付けます。")

# ---------------------------------------------------------------------------
# docker network create / volume create
# ---------------------------------------------------------------------------
NET = "docker network create"
_add(NET, "--driver", "networks.<名前>.driver", "ネットワークの種類です。bridge (標準・このホストの中だけ)、overlay (複数ホストをまたぐ・Swarm 用)、macvlan (コンテナに物理 LAN の住所を持たせる)、host、none など。", "道路の種類 (一般道・高速道路など) を決めます。")
_add(NET, "--opt", "networks.<名前>.driver_opts", "ドライバーへの追加設定です。bridge なら com.docker.network.bridge.name (ブリッジの名前) や com.docker.network.driver.mtu (一度に送れるデータの大きさ) など。", "道路の細かい仕様です。")
_add(NET, "--ipam-driver", "networks.<名前>.ipam.driver", "IP アドレスを配る仕組み (IPAM ドライバー) を選びます。標準は default です。", "部屋番号を配る係を選びます。")
_add(NET, "--ipam-opt", "networks.<名前>.ipam.options", "IPAM ドライバーへの追加設定です。", "部屋番号を配る係へのお願いです。")
_add(NET, "--subnet", "networks.<名前>.ipam.config.subnet", "このネットワークで使う IP アドレスの範囲を CIDR 形式 (例: 172.28.0.0/16) で決めます。社内 LAN と重ならない範囲にします。", "この道路沿いで使う番地の範囲を決めます。")
_add(NET, "--ip-range", "networks.<名前>.ipam.config.ip_range", "サブネットの中で、コンテナに自動で配る範囲をさらに絞ります。", "番地のうち、自動で配る部分を決めます。")
_add(NET, "--gateway", "networks.<名前>.ipam.config.gateway", "ゲートウェイ (外への出口) の IP アドレスを決めます。省略するとサブネットの最初のアドレスです。", "道路の出口の番地を決めます。")
_add(NET, "--aux-address", "networks.<名前>.ipam.config.aux_addresses", "コンテナに配らないように予約しておく IP アドレスです。", "使わないようにとっておく番地です。")
_add(NET, "--internal", "networks.<名前>.internal: true", "外への出口を作らず、ネットワークの中だけで通信できるようにします。データベース専用の裏ネットワークなどに使います。", "外につながっていない、敷地の中だけの道路にします。")
_add(NET, "--attachable", "networks.<名前>.attachable: true", "Swarm の overlay ネットワークに、個別の docker run のコンテナもつなげるようにします。", "あとからだれでも合流できる道路にします。")
_add(NET, "--ipv6", "networks.<名前>.enable_ipv6: true", "IPv6 のアドレスも使えるようにします。", "新しい形式の番地も使えるようにします。")
_add(NET, "--ipv4=false", "networks.<名前>.enable_ipv4: false", "IPv4 のアドレスを使わないネットワークにします (Docker 28 から)。", "古い形式の番地を使わない道路にします。")
_add(NET, "--label", "networks.<名前>.labels", "ネットワークに目印 (ラベル) を付けます。", "道路に看板を立てます。")
_add("docker volume create", "--driver", "volumes.<名前>.driver", "ボリュームの種類です。標準は local (ホストのディスク)。プラグインを入れると NFS やクラウドのディスクも使えます。", "ロッカーの種類を決めます。")
_add("docker volume create", "--opt", "volumes.<名前>.driver_opts", "ドライバーへの追加設定です。local なら type=nfs,o=addr=...,device=:/path で NFS、type=tmpfs でメモリ上のボリュームにできます。", "ロッカーの細かい仕様です。")
_add("docker volume create", "--label", "volumes.<名前>.labels", "ボリュームに目印 (ラベル) を付けます。", "ロッカーにシールを貼ります。")

# ---------------------------------------------------------------------------
# docker exec / inspect / ps / pull
# ---------------------------------------------------------------------------
_add("docker exec", "--user", "post_start[].user / pre_stop[].user", "コマンドを実行するユーザーです。省略するとコンテナの既定のユーザーです。", "だれとして作業するかです。")
_add("docker exec", "--privileged", "post_start[].privileged", "特権を付けて実行します。", "特別な合鍵を持たせて作業させます。")
_add("docker exec", "--workdir", "post_start[].working_dir", "コマンドを実行するフォルダです。", "どの机で作業するかです。")
_add("docker exec", "--env", "post_start[].environment", "このコマンドだけに渡す環境変数です。", "この作業だけのメモです。")
_add("docker inspect (health)", "--format", "(depends_on の待ち合わせ)", "inspect の結果 (JSON) から、Go テンプレートで必要な値だけを取り出します。", "長い報告書から、見たい行だけを抜き出します。")
_add("docker ps", "--all", "-", "止まっているコンテナも含めて表示します。", "お休み中のコンテナも名簿に入れます。")
_add("docker ps", "--format", "-", "表示する項目と形を決めます。table は表の形、\\t は列の区切りです。", "名簿の書き方を決めます。")
_add("docker pull", "--platform", "platform", "どの CPU 向けのイメージを取ってくるかを指定します。", "どの種類の機械用のセットを取り寄せるかです。")

# 位置引数 (オプションではない部分) の説明
POSITIONAL = {
    "run.image": ("image / build", "コンテナのもとになるイメージです。イメージ名の後ろに書いたものは、コンテナの中で実行するコマンド (compose の command) になります。", "どのお部屋セットを使うかです。"),
    "build.context": ("build.context", "ビルドの材料が入ったフォルダ (ビルドコンテキスト) です。COPY / ADD はこの中のファイルしか使えません。", "材料の入った箱です。"),
    "build.stdin": ("(派生イメージ)", "「-」は Dockerfile を標準入力から読むという意味です。", "設計図を手渡しします。"),
    "network.name": ("networks のキー", "作るネットワークの名前です。", "道路の名前です。"),
    "volume.name": ("volumes のキー", "作るボリュームの名前です。", "ロッカーの名前です。"),
    "image.ref": ("image", "取ってくるイメージの名前 (レジストリ/リポジトリ:タグ) です。", "取り寄せる部品セットの名前です。"),
}


def option_info(command, flag):
    """(compose での書き方, 意味・しくみ, やさしい説明) を返す。"""
    base = flag.split("=", 1)[0] if flag.startswith("--") and flag not in OPTIONS else flag
    for key in ((command, flag), (command, base), ("docker run", flag), ("docker run", base)):
        if key in OPTIONS:
            return OPTIONS[key]
    for (cmd, opt), value in OPTIONS.items():
        if opt in (flag, base):
            return value
    return ("", "", "")
