"""正規化モデル → 「docker コマンドの実行手順」への変換 (このツールの中心)。

docker compose v5 (compose-go v2) が Docker Engine API を呼ぶときの値の組み立てを、
docker CLI のオプションで同じになるように再現します。主な対応:

* ネットワーク / ボリュームの作成 (名前は <プロジェクト>_<キー>)
* イメージ: pull_policy: missing 相当 (無いときだけ pull) / build
* コンテナ名 <プロジェクト>-<サービス>-<番号>、サービス名のネットワーク別名
* depends_on の condition (service_healthy / service_completed_successfully) の待ち合わせ
* healthcheck の CMD (exec 形式) は docker run のオプションで書けないため、
  HEALTHCHECK を焼き込んだ派生イメージを作って再現
* configs / secrets: file はバインドマウント、content / environment はコンテナへコピー
* pre_start (init コンテナ) / post_start / pre_stop フック
"""

import json
import os
import posixpath
import re

from . import envfile
from .shell import Raw, concat, heredoc, quote, render_command
from .units import duration_micro, duration_seconds, human_bytes

__all__ = ["PlanOptions", "Plan", "Step", "Cmd", "Opt", "build_plan", "PlanError"]


class PlanError(Exception):
    pass


class PlanOptions:
    def __init__(self, host_project_dir=None, compose_labels=False, healthcheck_exec="image",
                 env_mode="auto", lookup=None, compose_version=None, generated_at=None):
        self.host_project_dir = host_project_dir
        self.compose_labels = compose_labels
        self.healthcheck_exec = healthcheck_exec
        self.env_mode = env_mode
        self.lookup = lookup or (lambda name: None)
        self.compose_version = compose_version
        self.generated_at = generated_at


class Opt:
    """コマンドの 1 オプション (説明用の情報つき)。"""

    def __init__(self, flag, value=None, src=None, note=None, kb=None):
        self.flag = flag
        self.value = value
        self.src = src
        self.note = note
        self.kb = kb or flag

    def shell(self):
        if self.value is None:
            return self.flag
        return "%s %s" % (self.flag, quote(self.value))

    def display_value(self):
        if self.value is None:
            return ""
        return str(self.value)


class Arg:
    def __init__(self, value, label, note=None, kb=None, src=None):
        self.value = value
        self.label = label
        self.note = note
        self.kb = kb
        self.src = src


class Cmd:
    """1 つの docker コマンド。"""

    def __init__(self, head, kb=None):
        self.head = head
        self.kb = kb or head
        self.opts = []
        self.args = []
        self.cmd_args = []
        self.stdin = None
        self.prefix = None

    def add(self, flag, value=None, src=None, note=None, kb=None):
        self.opts.append(Opt(flag, value, src, note, kb))
        return self

    def arg(self, value, label, note=None, kb=None, src=None):
        self.args.append(Arg(value, label, note, kb, src))
        return self

    def command_args(self, values, src=None, note=None):
        self.cmd_args = list(values or [])
        self.cmd_src = src
        self.cmd_note = note
        return self

    def render(self, inline=False):
        lines = [opt.shell() for opt in self.opts]
        tail = [quote(a.value) for a in self.args]
        if self.cmd_args:
            words = [quote(v) for v in self.cmd_args]
            joined = " ".join(words)
            if len(joined) <= 100 or len(words) == 1:
                tail.append(joined)
            else:
                tail.extend(words)
        one_line = " ".join([self.head] + lines + tail)
        if inline or (not self.opts and len(one_line) <= 100) or (len(self.opts) <= 1 and len(one_line) <= 72):
            text = one_line
        else:
            text = render_command(self.head, lines, tail)
        if self.prefix:
            text = self.prefix + text
        if self.stdin is not None:
            text = heredoc(text, self.stdin, "C2D_DOCKERFILE")
        return text


class Step:
    def __init__(self, kind, phase, title, target=None, service=None, compose_ref=None):
        self.no = 0
        self.kind = kind
        self.phase = phase
        self.title = title
        self.target = target
        self.service = service
        self.compose_ref = compose_ref
        self.cmds = []
        self.script = ""
        self.summary = ""
        self.details = []
        self.notes = []
        self.verify = []
        self.compose_snippet = None
        self.after = None

    def set_script(self, text):
        self.script = text.rstrip("\n")
        return self


class Plan:
    def __init__(self):
        self.project = None
        self.steps = []
        self.down_steps = []
        self.warnings = []
        self.info = {}
        self.mapping_rows = []


# ---------------------------------------------------------------------------
# 表示用: モデルの一部を YAML 風に書き出す
# ---------------------------------------------------------------------------
def to_yaml(value, indent=0):
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return pad + "{}"
        lines = []
        for key, val in value.items():
            if isinstance(val, (dict, list)) and val:
                lines.append("%s%s:" % (pad, key))
                lines.append(to_yaml(val, indent + 1))
            else:
                lines.append("%s%s: %s" % (pad, key, _yaml_scalar(val)))
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return pad + "[]"
        lines = []
        for item in value:
            if isinstance(item, dict) and item:
                sub = to_yaml(item, indent + 1).split("\n")
                lines.append("%s- %s" % (pad, sub[0].strip()))
                lines.extend(sub[1:])
            else:
                lines.append("%s- %s" % (pad, _yaml_scalar(item)))
        return "\n".join(lines)
    return pad + _yaml_scalar(value)


def _yaml_scalar(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value)
    if text == "" or re.search(r"[:#{}\[\],&*!|>'\"%@`]|^\s|\s$|^[-?]|\n", text) or text in ("true", "false", "null", "yes", "no"):
        return json.dumps(text, ensure_ascii=False)
    return text


# ---------------------------------------------------------------------------
# プランナー本体
# ---------------------------------------------------------------------------
class _Planner:
    def __init__(self, project, options):
        self.p = project
        self.o = options
        self.meta = project.get("_meta") or {}
        self.name = project["name"]
        self.services = project.get("services") or {}
        self.networks = project.get("networks") or {}
        self.volumes = project.get("volumes") or {}
        self.secrets = project.get("secrets") or {}
        self.configs = project.get("configs") or {}
        self.plan = Plan()
        self.plan.project = project
        self.warnings = []
        self.local_dir = os.path.normpath(self.meta.get("project_dir") or os.getcwd())
        self.pwd_mode = False
        host = options.host_project_dir
        if host is None:
            if os.name == "nt" or re.match(r"^[A-Za-z]:\\", self.local_dir):
                self.pwd_mode = True
                host = None
            else:
                host = self.local_dir
        elif host in ("$PWD", "PWD", "."):
            self.pwd_mode = True
            host = None
        self.host_dir = host.rstrip("/") if host else None
        self.images = {}
        self.containers = {}
        self.derived = {}
        self.order = []
        self.injections = {}

    # ---- 共通 -------------------------------------------------------------
    def warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)

    def map_path(self, path):
        """ローカルのパスを、RHEL 上で実行するときのパスに変換する。"""
        if path is None:
            return None
        local = self.local_dir
        norm = os.path.normpath(path)
        rel = None
        try:
            common = os.path.commonpath([os.path.normcase(local), os.path.normcase(norm)])
            if common == os.path.normcase(local):
                rel = os.path.relpath(norm, local)
        except ValueError:
            rel = None
        if rel is not None:
            rel = rel.replace("\\", "/")
            if rel == ".":
                rel = ""
            if self.pwd_mode:
                return concat(Raw('"$PWD"'), "/" + rel if rel else "")
            return posixpath.join(self.host_dir, rel) if rel else self.host_dir
        if re.match(r"^[A-Za-z]:[\\/]", path):
            self.warn("プロジェクトの外にある Windows のパス %s はそのまま RHEL では使えません。RHEL 上の正しいパスに書き換えてください。" % path)
            return path.replace("\\", "/")
        return path

    def svc_containers(self, svc_name):
        return self.containers.get(svc_name, [])

    # ---- 準備 -------------------------------------------------------------
    def order_services(self):
        names = list(self.meta.get("service_order") or self.services.keys())
        names = [n for n in names if n in self.services] + [n for n in self.services if n not in names]
        index = {n: i for i, n in enumerate(names)}
        deps = {}
        for name in names:
            svc = self.services[name]
            found = set()
            for dep in (svc.get("depends_on") or {}):
                if dep in self.services:
                    found.add(dep)
            mode = svc.get("network_mode") or ""
            if mode.startswith("service:"):
                found.add(mode.split(":", 1)[1])
            for key in ("ipc", "pid"):
                val = svc.get(key) or ""
                if val.startswith("service:"):
                    found.add(val.split(":", 1)[1])
            for vf in svc.get("volumes_from") or []:
                if not vf.startswith("container:"):
                    found.add(vf.split(":", 1)[0])
            for link in svc.get("links") or []:
                found.add(link.split(":", 1)[0])
            unknown = [d for d in found if d not in self.services]
            for dep in unknown:
                raise PlanError("services.%s が参照している %s が見つかりません" % (name, dep))
            deps[name] = found
        ordered = []
        remaining = set(names)
        while remaining:
            ready = sorted((n for n in remaining if deps[n] <= set(ordered)), key=lambda n: index[n])
            if not ready:
                raise PlanError("depends_on が循環しています: %s" % ", ".join(sorted(remaining)))
            ordered.append(ready[0])
            remaining.discard(ready[0])
        self.order = ordered
        self.deps = deps

    def replicas(self, svc_name, svc):
        count = 1
        if svc.get("scale") is not None:
            count = int(svc["scale"])
        deploy = svc.get("deploy") or {}
        if deploy.get("replicas") is not None:
            count = int(deploy["replicas"])
        return count

    def prepare_names(self):
        for name in self.order:
            svc = self.services[name]
            count = self.replicas(name, svc)
            if svc.get("container_name"):
                if count > 1:
                    raise PlanError("services.%s は container_name を指定しているため 2 つ以上 (scale/replicas) は起動できません" % name)
                names = [svc["container_name"]] if count >= 1 else []
            else:
                names = ["%s-%s-%d" % (self.name, name, i) for i in range(1, count + 1)]
            self.containers[name] = names
            if svc.get("image"):
                self.images[name] = svc["image"]
            elif svc.get("build") is not None:
                self.images[name] = "%s-%s" % (self.name, name)
            elif svc.get("provider"):
                self.images[name] = None
            else:
                raise PlanError("services.%s に image も build もありません" % name)

    # ---- STEP: 準備 -------------------------------------------------------
    def step_prepare(self):
        step = Step("prepare", "準備", "作業フォルダへ移動し、Docker が使えるか確認する")
        if self.pwd_mode:
            cd_line = "cd /path/to/%s    # ← compose ファイルを置いたフォルダに書き換えてから実行" % os.path.basename(self.local_dir)
            step.notes.append("このファイルは Windows 上で作られたため、compose ファイルのあるフォルダを \"$PWD\" (今いるフォルダ) として書いています。必ず compose ファイルのあるフォルダへ cd してから実行してください。")
        else:
            cd_line = "cd %s" % quote(self.host_dir)
        cmd = Cmd("docker version", kb="docker version")
        step.cmds.append(cmd)
        step.set_script("\n".join([
            "set +H",
            cd_line,
            cmd.render(),
        ]))
        step.summary = "履歴展開 (!) を止めて貼り付け事故を防ぎ、プロジェクトのフォルダへ移動して、docker コマンドとサーバー (dockerd) の両方が動いているかを確かめます。"
        step.details = [
            "set +H は、bash の「履歴展開」(! で始まる文字を過去のコマンドに置き換える機能) を止めます。コマンドの中に ! が含まれていても、そのまま貼り付けて実行できるようにするためです。",
            "cd でプロジェクトのフォルダへ移動します。この後のコマンドは、compose ファイルが置かれていたフォルダを基準にしたパスを使います。",
            "docker version で「Client」(docker コマンド) と「Server」(Docker Engine = dockerd) の両方のバージョンが表示されれば準備完了です。Server 側がエラーなら sudo systemctl start docker で Docker を起動してください。",
        ]
        step.verify = ["docker info"]
        self.add(step)

    def add(self, step):
        self.plan.steps.append(step)
        return step

    # ---- STEP: ネットワーク --------------------------------------------------
    def step_networks(self):
        order = self.meta.get("network_order") or list(self.networks)
        for key in order:
            cfg = self.networks.get(key)
            if cfg is None:
                continue
            netname = cfg.get("name") or "%s_%s" % (self.name, key)
            users = [s for s in self.order if key in (self.services[s].get("networks") or {})]
            if cfg.get("external"):
                step = Step("network_external", "ネットワーク確認", "外部ネットワーク「%s」があるか確認する" % netname,
                            target=netname, compose_ref="networks.%s" % key)
                cmd = Cmd("docker network inspect", kb="docker network inspect")
                cmd.arg(netname, "ネットワーク名", "compose で external: true と書かれたネットワーク。compose は作成せず、既にあるものを使います。")
                step.cmds.append(cmd)
                step.set_script(cmd.render() + " > /dev/null && echo 'OK: %s があります'" % netname)
                step.summary = "external (外部) と指定されたネットワーク「%s」が既にあるかを確認します。無ければ compose と同じくエラーなので、先に作成してください。" % netname
                step.details.append("compose は external: true のネットワークを作りません。存在しない場合は「network %s declared as external, but could not be found」というエラーで止まります。" % netname)
                step.notes.append("無い場合の作り方の例: docker network create %s" % netname)
                step.compose_snippet = to_yaml({"networks": {key: _strip_meta(cfg)}})
                self.add(step)
                continue
            step = Step("network_create", "ネットワーク作成", "ネットワーク「%s」を作る" % netname,
                        target=netname, compose_ref="networks.%s" % key)
            cmd = Cmd("docker network create", kb="docker network create")
            src = "networks.%s" % key
            if cfg.get("driver"):
                cmd.add("--driver", cfg["driver"], src + ".driver", "ネットワークの種類 (ドライバー) を %s にします。" % cfg["driver"])
            for okey, oval in (cfg.get("driver_opts") or {}).items():
                cmd.add("--opt", "%s=%s" % (okey, oval), src + ".driver_opts", "ドライバーへの追加設定 %s=%s を渡します。" % (okey, oval))
            ipam = cfg.get("ipam") or {}
            if ipam.get("driver"):
                cmd.add("--ipam-driver", ipam["driver"], src + ".ipam.driver", "IP アドレスを配る仕組み (IPAM ドライバー) を %s にします。" % ipam["driver"])
            for okey, oval in (ipam.get("options") or {}).items():
                cmd.add("--ipam-opt", "%s=%s" % (okey, oval), src + ".ipam.options", "IPAM ドライバーへの追加設定です。")
            for pool in ipam.get("config") or []:
                if pool.get("subnet"):
                    cmd.add("--subnet", pool["subnet"], src + ".ipam.config.subnet", "このネットワークで使う IP アドレスの範囲を %s にします。" % pool["subnet"])
                if pool.get("ip_range"):
                    cmd.add("--ip-range", pool["ip_range"], src + ".ipam.config.ip_range", "コンテナに配る IP をこの範囲 (%s) に絞ります。" % pool["ip_range"])
                if pool.get("gateway"):
                    cmd.add("--gateway", pool["gateway"], src + ".ipam.config.gateway", "ゲートウェイ (外への出口) の IP を %s にします。" % pool["gateway"])
                for host, addr in (pool.get("aux_addresses") or {}).items():
                    cmd.add("--aux-address", "%s=%s" % (host, addr), src + ".ipam.config.aux_addresses", "%s をコンテナに配らないよう予約します。" % addr)
            if cfg.get("internal"):
                cmd.add("--internal", None, src + ".internal", "外 (インターネットやホストの外) へは出られない、内部専用のネットワークにします。")
            if cfg.get("attachable"):
                cmd.add("--attachable", None, src + ".attachable", "あとから個別のコンテナもつなげられるようにします (主に Swarm 用)。")
            if cfg.get("enable_ipv6") is True:
                cmd.add("--ipv6", None, src + ".enable_ipv6", "IPv6 アドレスも使えるようにします。")
            if cfg.get("enable_ipv4") is False:
                cmd.add("--ipv4=false", None, src + ".enable_ipv4", "IPv4 アドレスを使わないネットワークにします。")
            for lkey, lval in (cfg.get("labels") or {}).items():
                cmd.add("--label", "%s=%s" % (lkey, lval), src + ".labels", "目印 (ラベル) %s=%s を付けます。" % (lkey, lval))
            if self.o.compose_labels:
                cmd.add("--label", "com.docker.compose.network=%s" % key, None, "compose が付けるラベル (どの network キーか)。")
                cmd.add("--label", "com.docker.compose.project=%s" % self.name, None, "compose が付けるラベル (プロジェクト名)。")
                if self.o.compose_version:
                    cmd.add("--label", "com.docker.compose.version=%s" % self.o.compose_version, None, "compose が付けるラベル (compose のバージョン)。")
            cmd.arg(netname, "ネットワーク名",
                    "compose の命名規則「<プロジェクト名>_<ネットワークのキー>」で付けた名前です。" if not (self.networks[key].get("name") and self.networks[key]["name"] != "%s_%s" % (self.name, key)) else "compose ファイルの name: で指定された名前です。",
                    kb="network.name", src=src)
            step.cmds.append(cmd)
            step.set_script(cmd.render())
            if users:
                step.summary = "仮想ネットワーク「%s」を作ります。つながるコンテナ: %s。同じネットワークのコンテナどうしは、サービス名で呼び合えます。" % (netname, "、".join(users))
            else:
                step.summary = "仮想ネットワーク「%s」を作ります。" % netname
            if key == "default":
                step.details.append("compose ファイルに networks: を書いていないサービスがあるため、compose は自動で「%s」(既定ネットワーク) を作ります。それを同じ名前で再現します。" % netname)
            step.details.append("ドライバーを指定していないときは bridge (ホストの中だけの仮想スイッチ) になります。" if not cfg.get("driver") else "ドライバー %s のネットワークを作ります。" % cfg["driver"])
            step.verify = ["docker network ls --filter name=%s" % netname, "docker network inspect %s" % netname]
            step.compose_snippet = to_yaml({"networks": {key: _strip_meta(cfg)}})
            self.add(step)

    # ---- STEP: ボリューム -----------------------------------------------------
    def step_volumes(self):
        order = self.meta.get("volume_order") or list(self.volumes)
        for key in order:
            cfg = self.volumes.get(key)
            if cfg is None:
                continue
            volname = cfg.get("name") or "%s_%s" % (self.name, key)
            users = [s for s in self.order if any(v.get("type") == "volume" and v.get("source") == key for v in self.services[s].get("volumes") or [])]
            src = "volumes.%s" % key
            if cfg.get("external"):
                step = Step("volume_external", "ボリューム確認", "外部ボリューム「%s」があるか確認する" % volname, target=volname, compose_ref=src)
                cmd = Cmd("docker volume inspect", kb="docker volume inspect")
                cmd.arg(volname, "ボリューム名", "compose で external: true と書かれたボリューム。compose は作成せず、既にあるものを使います。")
                step.cmds.append(cmd)
                step.set_script(cmd.render() + " > /dev/null && echo 'OK: %s があります'" % volname)
                step.summary = "external と指定されたボリューム「%s」が既にあるかを確認します。" % volname
                step.notes.append("無い場合の作り方の例: docker volume create %s" % volname)
                step.compose_snippet = to_yaml({"volumes": {key: _strip_meta(cfg)}})
                self.add(step)
                continue
            step = Step("volume_create", "ボリューム作成", "ボリューム「%s」を作る" % volname, target=volname, compose_ref=src)
            cmd = Cmd("docker volume create", kb="docker volume create")
            if cfg.get("driver"):
                cmd.add("--driver", cfg["driver"], src + ".driver", "ボリュームの種類 (ドライバー) を %s にします。" % cfg["driver"])
            for okey, oval in (cfg.get("driver_opts") or {}).items():
                cmd.add("--opt", "%s=%s" % (okey, oval), src + ".driver_opts", "ドライバーへの追加設定 %s=%s を渡します。" % (okey, oval))
            for lkey, lval in (cfg.get("labels") or {}).items():
                cmd.add("--label", "%s=%s" % (lkey, lval), src + ".labels", "目印 (ラベル) %s=%s を付けます。" % (lkey, lval))
            if self.o.compose_labels:
                cmd.add("--label", "com.docker.compose.project=%s" % self.name, None, "compose が付けるラベル (プロジェクト名)。")
                cmd.add("--label", "com.docker.compose.volume=%s" % key, None, "compose が付けるラベル (どの volume キーか)。")
                if self.o.compose_version:
                    cmd.add("--label", "com.docker.compose.version=%s" % self.o.compose_version, None, "compose が付けるラベル (compose のバージョン)。")
            cmd.arg(volname, "ボリューム名", "compose の命名規則「<プロジェクト名>_<ボリュームのキー>」で付けた名前です。" if volname == "%s_%s" % (self.name, key) else "compose ファイルの name: で指定された名前です。", kb="volume.name", src=src)
            step.cmds.append(cmd)
            step.set_script(cmd.render())
            step.summary = "データを保存しておく名前付きボリューム「%s」を作ります。%s" % (volname, ("使うサービス: %s。" % "、".join(users)) if users else "")
            step.details.append("コンテナを削除してもボリュームの中身は残ります。消すときは docker volume rm で明示的に消します (compose の down -v と同じ)。")
            step.verify = ["docker volume ls --filter name=%s" % volname, "docker volume inspect %s" % volname]
            step.compose_snippet = to_yaml({"volumes": {key: _strip_meta(cfg)}})
            self.add(step)

    # ---- STEP: イメージ取得 ---------------------------------------------------
    def step_pulls(self):
        seen = set()
        for name in self.order:
            svc = self.services[name]
            image = self.images.get(name)
            if not image or svc.get("build") is not None:
                continue
            self._pull_step(name, svc, image, seen, "services.%s.image" % name)
        for name in self.order:
            svc = self.services[name]
            for hook in svc.get("pre_start") or []:
                img = hook.get("image")
                if img and img != self.images.get(name) and img not in seen:
                    self._pull_step(name, svc, img, seen, "services.%s.pre_start" % name, hook=True)

    def _pull_step(self, name, svc, image, seen, src, hook=False):
        key = (image, svc.get("platform"))
        if key in seen:
            return
        seen.add(key)
        policy = (svc.get("pull_policy") or "missing").lower()
        users = [n for n in self.order if self.images.get(n) == image and self.services[n].get("build") is None]
        if policy == "never":
            self.warn("services.%s: pull_policy: never のため、イメージ %s はダウンロードしません (手元に無いと起動に失敗します)。" % (name, image))
            return
        step = Step("pull", "イメージ取得", "イメージ「%s」を用意する" % image, target=image, service=name, compose_ref=src)
        cmd = Cmd("docker pull", kb="docker pull")
        if svc.get("platform"):
            cmd.add("--platform", svc["platform"], "services.%s.platform" % name, "CPU の種類 (プラットフォーム) %s 用のイメージを取ってきます。" % svc["platform"])
        cmd.arg(image, "イメージ名", "取ってくるイメージの名前 (リポジトリ:タグ) です。", kb="image.ref", src=src)
        step.cmds.append(cmd)
        if policy == "always":
            step.set_script(cmd.render())
            step.summary = "pull_policy: always のため、毎回レジストリから最新のイメージ「%s」をダウンロードします。" % image
        else:
            check = Cmd("docker image inspect", kb="docker image inspect")
            check.arg(image, "イメージ名", "手元 (ローカル) にこのイメージがあるかを調べます。")
            step.cmds.insert(0, check)
            step.set_script("%s > /dev/null 2>&1 || %s" % (check.render(inline=True), cmd.render(inline=True)))
            step.summary = "イメージ「%s」が手元に無いときだけダウンロードします (compose の既定 pull_policy: missing と同じ動き)。" % image
            step.details.append("docker image inspect は、イメージが手元にあれば成功 (終了コード 0)、無ければ失敗します。|| は「左が失敗したときだけ右を実行する」という意味なので、無いときだけ docker pull が動きます。")
            if policy in ("daily", "weekly") or policy.startswith("every_"):
                step.notes.append("compose の pull_policy: %s は「前回の取得から一定時間たったら更新する」設定ですが、docker コマンドにはこの機能がないため「無いときだけ取得」で代用しています。最新にしたいときは docker pull %s を実行してください。" % (policy, image))
        if users:
            step.details.append("このイメージを使うサービス: %s" % "、".join(users))
        if hook:
            step.details.append("pre_start (起動前に動かす初期化用コンテナ) で使うイメージです。")
        step.verify = ["docker image ls %s" % image]
        self.add(step)

    # ---- STEP: ビルド -------------------------------------------------------
    def step_builds(self):
        seen = set()
        for name in self.order:
            svc = self.services[name]
            build = svc.get("build")
            if build is None:
                continue
            image = self.images[name]
            if image in seen:
                continue
            seen.add(image)
            src = "services.%s.build" % name
            step = Step("build", "イメージ作成", "サービス「%s」のイメージ「%s」をビルドする" % (name, image), target=image, service=name, compose_ref=src)
            cmd = Cmd("docker build", kb="docker build")
            context = build.get("context") or self.local_dir
            remote = bool(re.match(r"^[a-z]+://|^git@|^github\.com/", context, re.I))
            ctx_path = context if remote else self.map_path(context)
            if build.get("dockerfile_inline"):
                cmd.add("--file", "-", src + ".dockerfile_inline", "Dockerfile をファイルではなく、下に書いた文章 (標準入力) から読みます (compose の dockerfile_inline)。")
                cmd.stdin = build["dockerfile_inline"]
            else:
                dockerfile = build.get("dockerfile") or "Dockerfile"
                if dockerfile != "Dockerfile" or remote:
                    if remote or os.path.isabs(dockerfile) or dockerfile.startswith("/"):
                        df_value = dockerfile if remote else self.map_path(dockerfile)
                    else:
                        df_local = os.path.normpath(os.path.join(context, dockerfile))
                        df_value = self.map_path(df_local)
                    cmd.add("--file", df_value, src + ".dockerfile", "設計図 (Dockerfile) の場所を指定します。compose の dockerfile: %s (context からの相対パス) を絶対パスにしたものです。" % dockerfile)
            if build.get("target"):
                cmd.add("--target", build["target"], src + ".target", "マルチステージ Dockerfile の「%s」ステージまでを作ります。" % build["target"])
            for arg_name, arg_val in (build.get("args") or {}).items():
                if arg_val is None:
                    cmd.add("--build-arg", arg_name, src + ".args", "ビルド時の変数 %s を、実行するシェルの環境変数から渡します。" % arg_name)
                else:
                    cmd.add("--build-arg", "%s=%s" % (arg_name, arg_val), src + ".args", "ビルド時の変数 (ARG) %s に「%s」を渡します。" % (arg_name, arg_val))
            for lkey, lval in (build.get("labels") or {}).items():
                cmd.add("--label", "%s=%s" % (lkey, lval), src + ".labels", "イメージに目印 (ラベル) を付けます。")
            if self.o.compose_labels:
                cmd.add("--label", "com.docker.compose.project=%s" % self.name, None, "compose が付けるラベル。")
                cmd.add("--label", "com.docker.compose.service=%s" % name, None, "compose が付けるラベル。")
                if self.o.compose_version:
                    cmd.add("--label", "com.docker.compose.version=%s" % self.o.compose_version, None, "compose が付けるラベル。")
            for ref in build.get("secrets") or []:
                source = ref.get("source")
                secret = self.secrets.get(source) or {}
                sid = ref.get("target") or source
                if secret.get("file"):
                    cmd.add("--secret", concat("id=%s,src=" % sid, self.map_path(secret["file"])), src + ".secrets",
                            "ビルド中だけ使える秘密のファイル (id=%s) を渡します。イメージには残りません。" % sid)
                elif secret.get("environment"):
                    cmd.add("--secret", "id=%s,env=%s" % (sid, secret["environment"]), src + ".secrets",
                            "環境変数 %s の値を、ビルド中だけ使える秘密 (id=%s) として渡します。" % (secret["environment"], sid))
                    step.notes.append("--secret の env=%s は、実行するシェルで export 済みの環境変数から読みます。compose は .env の値も使いますが docker build は読まないため、先に export %s=... を実行してください。" % (secret["environment"], secret["environment"]))
                else:
                    self.warn("services.%s.build.secrets: %s の中身 (file/environment) が分からないため渡せません。" % (name, source))
            for ssh in build.get("ssh") or []:
                cmd.add("--ssh", ssh, src + ".ssh", "ビルド中に SSH の鍵 (エージェント) を使えるようにします。")
            for cname, cval in (build.get("additional_contexts") or {}).items():
                if cval and not re.match(r"^[a-z0-9-]+://|^docker-image://|^target:|^service:", cval):
                    cval = self.map_path(cval)
                if isinstance(cval, str) and cval.startswith("service:"):
                    other = cval.split(":", 1)[1]
                    cval = "docker-image://" + (self.images.get(other) or other)
                cmd.add("--build-context", concat("%s=" % cname, cval), src + ".additional_contexts", "Dockerfile から名前「%s」で参照できる追加の材料置き場を渡します。" % cname)
            for item in build.get("cache_from") or []:
                cmd.add("--cache-from", item, src + ".cache_from", "ビルドの途中結果 (キャッシュ) をここから再利用します。")
            for item in build.get("cache_to") or []:
                cmd.add("--cache-to", item, src + ".cache_to", "ビルドの途中結果 (キャッシュ) をここへ保存します。")
            if build.get("network"):
                cmd.add("--network", build["network"], src + ".network", "ビルド中の RUN 命令が使うネットワークを %s にします。" % build["network"])
            for entry in sorted(build.get("extra_hosts") or [], key=lambda e: e.split("=", 1)[0]):
                host, _, addr = entry.partition("=")
                cmd.add("--add-host", "%s:%s" % (host, addr), src + ".extra_hosts", "ビルド中の /etc/hosts に %s → %s を追加します。" % (host, addr))
            if build.get("shm_size"):
                cmd.add("--shm-size", human_bytes(build["shm_size"]), src + ".shm_size", "ビルド中の共有メモリ (/dev/shm) の大きさです。")
            for uname, uval in (build.get("ulimits") or {}).items():
                cmd.add("--ulimit", _ulimit_value(uname, uval), src + ".ulimits", "ビルド中の資源の上限 (ulimit) です。")
            if build.get("no_cache"):
                cmd.add("--no-cache", None, src + ".no_cache", "キャッシュを使わず、最初からすべて作り直します。")
            for stage in build.get("no_cache_filter") or []:
                cmd.add("--no-cache-filter", stage, src + ".no_cache_filter", "ステージ %s だけキャッシュを使いません。" % stage)
            if build.get("pull"):
                cmd.add("--pull", None, src + ".pull", "FROM のベースイメージを毎回レジストリから取り直します。")
            platforms = build.get("platforms") or []
            if platforms:
                cmd.add("--platform", ",".join(platforms), src + ".platforms", "どの CPU 向けのイメージを作るか (%s) を指定します。" % ",".join(platforms))
                if len(platforms) > 1:
                    step.notes.append("複数のプラットフォームを同時に作る場合、通常の docker ドライバーでは手元に読み込めないことがあります (docker buildx create で別のビルダーが必要)。")
            elif svc.get("platform"):
                cmd.add("--platform", svc["platform"], "services.%s.platform" % name, "どの CPU 向けのイメージを作るか (%s) を指定します。" % svc["platform"])
            if build.get("privileged"):
                cmd.add("--allow", "security.insecure", src + ".privileged", "特権が必要な RUN 命令を許可します (ビルダーの設定も必要)。")
            for ent in build.get("entitlements") or []:
                cmd.add("--allow", ent, src + ".entitlements", "ビルドに追加の権限 %s を許可します。" % ent)
            if build.get("isolation"):
                cmd.add("--isolation", build["isolation"], src + ".isolation", "分離方式 (Windows 用) です。")
            cmd.add("--tag", image, "services.%s.image" % name if svc.get("image") else None,
                    "できたイメージに「%s」という名前を付けます。%s" % (image, "" if svc.get("image") else "compose の image: が無いため、compose と同じ規則「<プロジェクト名>-<サービス名>」で名前を付けます。"))
            for tag in build.get("tags") or []:
                cmd.add("--tag", tag, src + ".tags", "追加の名前 (タグ) %s も付けます。" % tag)
            cmd.arg(ctx_path, "ビルドコンテキスト", "ビルドの材料が入ったフォルダ (context) です。この中のファイルを COPY / ADD で使えます。", kb="build.context", src=src + ".context")
            step.cmds.append(cmd)
            step.set_script(cmd.render())
            step.summary = "Dockerfile (設計図) とビルドコンテキスト (材料フォルダ) からイメージ「%s」を作ります。" % image
            step.details.append("compose v5 は内部で Docker Bake (BuildKit) に任せてビルドします。docker build も同じ BuildKit を使うため、できあがるイメージは同じです。")
            insights = self.dockerfile_insights(build)
            step.details.extend(insights)
            step.verify = ["docker image ls %s" % image.split(":")[0], "docker image inspect %s" % image]
            step.compose_snippet = to_yaml({"services": {name: {"build": _strip_meta(build), "image": svc.get("image")} if svc.get("image") else {"build": _strip_meta(build)}}})
            self.add(step)

    def dockerfile_insights(self, build):
        """ビルドコンテキストの Dockerfile を読んで、仕組みの説明に使う情報を集める。"""
        if build.get("dockerfile_inline"):
            text = build["dockerfile_inline"]
            where = "dockerfile_inline"
        else:
            context = build.get("context") or ""
            dockerfile = build.get("dockerfile") or "Dockerfile"
            path = dockerfile if os.path.isabs(dockerfile) else os.path.join(context, dockerfile)
            if not os.path.isfile(path):
                return ["(Dockerfile %s をこのパソコンでは読めなかったため、中身の説明は省略します)" % path]
            try:
                with open(path, encoding="utf-8-sig", errors="replace") as handle:
                    text = handle.read()
            except OSError:
                return []
            where = path
        info = parse_dockerfile(text)
        out = []
        if info["from"]:
            out.append("Dockerfile の FROM (土台にするイメージ): %s" % "、".join(info["from"]))
        if info["stages"]:
            out.append("ステージ (AS で名前を付けた途中段階): %s" % "、".join(info["stages"]))
        if info["args"]:
            out.append("ARG (ビルド時に外から渡せる変数): %s" % "、".join(info["args"]))
        if info["expose"]:
            out.append("EXPOSE (使う予定のポートのメモ): %s" % "、".join(info["expose"]))
        if info["volume"]:
            out.append("VOLUME (自動で匿名ボリュームになる場所): %s" % "、".join(info["volume"]))
        if info["healthcheck"]:
            out.append("HEALTHCHECK (イメージ側の健康チェック): %s" % info["healthcheck"])
        if info["user"]:
            out.append("USER (コンテナ内で動くユーザー): %s" % info["user"])
        if info["entrypoint"]:
            out.append("ENTRYPOINT: %s" % info["entrypoint"])
        if info["cmd"]:
            out.append("CMD: %s" % info["cmd"])
        if info["secret_mounts"]:
            out.append("RUN --mount=type=secret で使う秘密 (id): %s" % "、".join(info["secret_mounts"]))
        if out:
            out.insert(0, "ビルドコンテキストの Dockerfile (%s) から読み取った内容:" % where)
        return out

    # ---- STEP: ヘルスチェック入り派生イメージ ------------------------------------
    def step_healthcheck_images(self):
        for name in self.order:
            svc = self.services[name]
            hc = svc.get("healthcheck") or {}
            test = hc.get("test") or []
            if hc.get("disable") or not test or test[0] != "CMD":
                continue
            if self.o.healthcheck_exec == "shell":
                self.warn("services.%s: healthcheck の CMD (exec 形式) を --health-cmd (シェル形式) に置き換えています。イメージに /bin/sh が無いとヘルスチェックが失敗します。" % name)
                continue
            base = self.images[name]
            derived = "%s-%s:with-healthcheck" % (self.name, name)
            self.derived[name] = derived
            src = "services.%s.healthcheck" % name
            step = Step("healthcheck_image", "ヘルスチェック入りイメージ作成",
                        "サービス「%s」用に、ヘルスチェックを焼き込んだイメージ「%s」を作る" % (name, derived),
                        target=derived, service=name, compose_ref=src)
            options = []
            base_hc = self.base_healthcheck(svc)
            for key, flag in (("interval", "--interval"), ("timeout", "--timeout"), ("start_period", "--start-period"),
                              ("start_interval", "--start-interval")):
                value = hc.get(key) or base_hc.get(key)
                if value:
                    options.append("%s=%s" % (flag, value))
            retries = hc.get("retries") if hc.get("retries") is not None else base_hc.get("retries")
            if retries is not None:
                options.append("--retries=%d" % int(retries))
            exec_json = json.dumps(test[1:], ensure_ascii=False)
            dockerfile = "FROM %s\nHEALTHCHECK %s%sCMD %s\n" % (base, " ".join(options), " " if options else "", exec_json)
            cmd = Cmd("docker build", kb="docker build (healthcheck)")
            if svc.get("platform"):
                cmd.add("--platform", svc["platform"], "services.%s.platform" % name, "元のイメージと同じ CPU 向けに作ります。")
            cmd.add("--tag", derived, None, "ヘルスチェック入りのイメージに「%s」という名前を付けます (元のイメージ「%s」は変更しません)。" % (derived, base))
            cmd.arg("-", "Dockerfile の読み込み元", "「-」は Dockerfile を標準入力 (下のヒアドキュメント) から読む、という意味です。材料フォルダ (コンテキスト) は使いません。", kb="build.stdin")
            cmd.stdin = dockerfile
            step.cmds.append(cmd)
            step.set_script(cmd.render())
            step.summary = ("compose の healthcheck は exec 形式 (test: [\"CMD\", ...]) ですが、docker run の --health-cmd はシェル形式 (/bin/sh -c で実行) しか書けません。"
                            "同じ動きにするため、元のイメージに HEALTHCHECK だけを追加した派生イメージを作ります。")
            step.details.append("exec 形式: コマンドを直接実行します。/bin/sh が入っていないイメージ (distroless など) でも動きます。")
            step.details.append("シェル形式: /bin/sh -c 'コマンド' で実行します。シェルが無いイメージでは必ず失敗し、コンテナが unhealthy (不健康) になります。")
            step.details.append("作られるイメージは元のイメージにメタデータ (HEALTHCHECK の設定) を 1 つ足しただけで、中身のファイルは同じです。")
            step.details.append("焼き込む内容: HEALTHCHECK %s CMD %s" % (" ".join(options), exec_json))
            if not hc.get("interval") and not base_hc.get("interval"):
                step.notes.append("interval などを省略した項目は Docker の既定値 (interval 30s / timeout 30s / retries 3) になります。")
            step.verify = ["docker image inspect --format '{{json .Config.Healthcheck}}' %s" % derived]
            step.compose_snippet = to_yaml({"services": {name: {"healthcheck": hc}}})
            self.add(step)

    def base_healthcheck(self, svc):
        build = svc.get("build")
        if not build:
            return {}
        if build.get("dockerfile_inline"):
            text = build["dockerfile_inline"]
        else:
            context = build.get("context") or ""
            dockerfile = build.get("dockerfile") or "Dockerfile"
            path = dockerfile if os.path.isabs(dockerfile) else os.path.join(context, dockerfile)
            if not os.path.isfile(path):
                return {}
            with open(path, encoding="utf-8-sig", errors="replace") as handle:
                text = handle.read()
        return parse_dockerfile(text).get("healthcheck_opts") or {}

    # ---- サービスの起動 -------------------------------------------------------
    def step_services(self):
        if not self.o.compose_labels:
            for name in self.order:
                svc = self.services[name]
                sockets = [v for v in svc.get("volumes") or []
                           if v.get("type") == "bind" and (v.get("source") or "").rstrip("/") in ("/var/run/docker.sock", "/run/docker.sock")]
                if sockets or svc.get("use_api_socket"):
                    self.warn("services.%s は Docker の API (docker.sock) を使います。中のプログラムが compose のラベル (com.docker.compose.project / service) で"
                              "コンテナを探す作りの場合は、--compose-labels を付けて変換してください (compose と同じラベルが付きます)。" % name)
        for name in self.order:
            svc = self.services[name]
            names = self.svc_containers(name)
            if svc.get("provider"):
                self.warn("services.%s は provider (外部の仕組みに任せるサービス) のため docker コマンドでは再現できません。スキップします。" % name)
                continue
            if not names:
                self.warn("services.%s は scale/replicas が 0 のため起動しません。" % name)
                continue
            self.step_waits(name, svc)
            injections = self.collect_injections(name, svc)
            if injections and svc.get("read_only"):
                inj = injections[0]
                raise PlanError(
                    "services.%s は read_only: true のため、%s「%s」(content / environment で中身を書いたもの) をコンテナに書き込めません。"
                    "docker compose でも「cannot create %s \"%s_%s\" in read-only service %s: `file` is the sole supported option」"
                    "というエラーで起動に失敗します。read_only を外すか、%s を file: で定義してください。" % (
                        name, "configs" if inj["kind"] == "config" else "secrets", inj["source"], inj["kind"], self.name,
                        inj["source"], name, "configs" if inj["kind"] == "config" else "secrets"))
            pre_start = svc.get("pre_start") or []
            use_create = bool(injections) or bool(pre_start)
            if use_create:
                for idx, cname in enumerate(names):
                    self.step_run(name, svc, cname, idx, create=True)
                for idx, cname in enumerate(names):
                    for inj in injections:
                        self.step_inject(name, cname, inj)
                for hidx, hook in enumerate(pre_start):
                    self.step_init_container(name, svc, names[0], hook, hidx)
                for cname in names:
                    self.step_start(name, cname, pre_start, injections)
                for cname in names:
                    self.step_hooks(name, svc, cname, "post_start")
            else:
                for idx, cname in enumerate(names):
                    self.step_run(name, svc, cname, idx, create=False)
                    self.step_hooks(name, svc, cname, "post_start")
            self.mapping_rows(name, svc)

    def step_waits(self, name, svc):
        healthy = []
        completed = []
        for dep, cfg in (svc.get("depends_on") or {}).items():
            if dep not in self.services:
                continue
            cond = (cfg or {}).get("condition") or "service_started"
            if cond == "service_healthy":
                healthy.extend(self.svc_containers(dep))
            elif cond == "service_completed_successfully":
                completed.extend(self.svc_containers(dep))
        if healthy:
            step = Step("wait_healthy", "起動待ち", "%s が healthy になるまで待つ" % "・".join(healthy),
                        target=" ".join(healthy), service=name, compose_ref="services.%s.depends_on" % name)
            cmd = Cmd("docker inspect", kb="docker inspect (health)")
            cmd.add("--format", "{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}", None,
                    "コンテナの状態 (running など) とヘルスチェックの結果 (healthy など) を「状態:結果」の形で取り出します。")
            cmd.arg("${C}", "コンテナ名", "for 文で 1 つずつ入れ替わるコンテナ名です。")
            step.cmds.append(cmd)
            lines = [
                "for C in %s; do" % " ".join(quote(c) for c in healthy),
                "  echo \"[待機] ${C} が healthy (正常) になるまで待ちます...\"",
                "  while :; do",
                "    S=\"$(docker inspect --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}' \"${C}\" 2>&1)\"",
                "    case \"${S}\" in",
                "      running:healthy) echo \"[OK] ${C} は healthy です\"; break ;;",
                "      running:starting|restarting:*) sleep 2 ;;",
                "      *) echo \"[NG] ${C} の状態は ${S} です。docker logs ${C} で原因を確認してください\"; break ;;",
                "    esac",
                "  done",
                "done",
            ]
            step.set_script("\n".join(lines))
            deps = [d for d, c in (svc.get("depends_on") or {}).items() if (c or {}).get("condition") == "service_healthy" and d in self.services]
            step.summary = "サービス「%s」は depends_on で %s が「service_healthy (ヘルスチェックに合格)」になるのを待ってから起動する設定です。同じように、合格するまで 2 秒おきに状態を確認して待ちます。" % (name, "・".join(deps))
            step.details.append("compose は依存先がすべて healthy になるまで、次のコンテナを start しません。unhealthy になったり止まったりした場合は「dependency failed to start」というエラーで止まります。")
            step.details.append("このループも同じく、healthy なら次へ、starting (確認中) なら待ち、それ以外 (unhealthy / exited など) なら NG と表示して待つのをやめます。")
            for dep in deps:
                hc = self.services[dep].get("healthcheck") or {}
                if not hc.get("test") and not self._image_has_healthcheck(dep):
                    step.notes.append("%s には compose の healthcheck がありません。イメージ側に HEALTHCHECK が無いと「状態: running:」のまま NG になります (compose も同じくエラーになります)。" % dep)
            step.notes.append("NG と表示されたら、ここで手を止めて docker logs <コンテナ名> で原因を確認してください (この後のコマンドを続けても、依存先が正常でないため動かない可能性があります)。")
            step.verify = ["docker ps --filter name=%s" % healthy[0]]
            self.add(step)
        for cname in completed:
            step = Step("wait_completed", "完了待ち", "%s が正常終了するまで待つ" % cname,
                        target=cname, service=name, compose_ref="services.%s.depends_on" % name)
            cmd = Cmd("docker wait", kb="docker wait")
            cmd.arg(cname, "コンテナ名", "終了するまで待つコンテナです。終了したら終了コードを表示します。")
            step.cmds.append(cmd)
            step.set_script("\n".join([
                "echo \"[待機] %s が終わるまで待ちます...\"" % cname,
                "EXIT_CODE=\"$(%s)\"" % cmd.render(inline=True),
                "echo \"%s の終了コード: ${EXIT_CODE} (0 なら成功)\"" % cname,
            ]))
            step.summary = "サービス「%s」は depends_on で「service_completed_successfully (正常に終了)」を待つ設定です。docker wait で終了を待ち、終了コードが 0 (成功) かを確かめます。" % name
            step.details.append("compose は終了コードが 0 以外だと「service ... didn't complete successfully」というエラーで止まります。0 以外が表示されたら、ここで手を止めて docker logs %s で原因を確認してください。" % cname)
            step.verify = ["docker ps --all --filter name=%s" % cname, "docker logs %s" % cname]
            self.add(step)

    def _image_has_healthcheck(self, svc_name):
        svc = self.services[svc_name]
        if svc_name in self.derived:
            return True
        if svc.get("build"):
            return bool(self.base_healthcheck(svc)) or bool(self._dockerfile_has_healthcheck(svc))
        return True

    def _dockerfile_has_healthcheck(self, svc):
        build = svc.get("build") or {}
        text = build.get("dockerfile_inline")
        if not text:
            path = os.path.join(build.get("context") or "", build.get("dockerfile") or "Dockerfile")
            if not os.path.isfile(path):
                return True
            with open(path, encoding="utf-8-sig", errors="replace") as handle:
                text = handle.read()
        return bool(parse_dockerfile(text).get("healthcheck"))

    # ---- configs / secrets の投入 --------------------------------------------
    def collect_injections(self, name, svc):
        out = []
        for ref in svc.get("configs") or []:
            source = ref.get("source")
            cfg = self.configs.get(source) or {}
            if cfg.get("file"):
                continue
            target = ref.get("target") or "/" + source
            if not target.startswith("/"):
                target = "/" + target
            if cfg.get("content") is not None:
                content = cfg["content"]
            elif cfg.get("environment"):
                content = self.o.lookup(cfg["environment"])
                if content is None:
                    self.warn("configs.%s: 環境変数 %s が設定されていないため中身が空になります。" % (source, cfg["environment"]))
                    content = ""
            else:
                self.warn("configs.%s は external などのため docker コマンドでは再現できません。" % source)
                continue
            out.append({"kind": "config", "source": source, "target": target, "content": content,
                        "mode": ref.get("mode"), "uid": ref.get("uid"), "gid": ref.get("gid")})
        for ref in svc.get("secrets") or []:
            source = ref.get("source")
            sec = self.secrets.get(source) or {}
            if sec.get("file"):
                continue
            target = ref.get("target") or "/run/secrets/" + source
            if not target.startswith("/"):
                target = "/run/secrets/" + target
            if sec.get("environment"):
                content = self.o.lookup(sec["environment"])
                if content is None:
                    self.warn("secrets.%s: 環境変数 %s が設定されていないため中身が空になります。" % (source, sec["environment"]))
                    content = ""
            elif sec.get("content") is not None:
                content = sec["content"]
            else:
                self.warn("secrets.%s は external などのため docker コマンドでは再現できません。" % source)
                continue
            out.append({"kind": "secret", "source": source, "target": target, "content": content,
                        "mode": ref.get("mode"), "uid": ref.get("uid"), "gid": ref.get("gid")})
        return out

    def step_inject(self, name, cname, inj):
        target = inj["target"]
        rel = target.lstrip("/")
        workdir = "/tmp/%s-compose2docker/%s" % (self.name, cname)
        host_file = "%s/%s" % (workdir, rel)
        mode = inj.get("mode")
        mode_text = "%04o" % (int(mode) if mode is not None else 0o444)
        uid = inj.get("uid") or "0"
        gid = inj.get("gid") or "0"
        kind_ja = "設定ファイル (configs)" if inj["kind"] == "config" else "秘密情報 (secrets)"
        step = Step("inject", "ファイル投入", "%s「%s」を %s の %s に入れる" % (kind_ja, inj["source"], cname, target),
                    target=cname, service=name, compose_ref="%ss.%s" % (inj["kind"], inj["source"]))
        content = inj["content"]
        lines = ["mkdir -p %s" % quote(posixpath.dirname(host_file))]
        if content.endswith("\n") and "\r" not in content:
            lines.append(heredoc("cat > %s" % quote(host_file), content, "C2D_CONTENT"))
        else:
            lines.append("printf '%%s' %s > %s" % (quote(content), quote(host_file)))
        tar_cmd = "tar --create --owner=%s --group=%s --mode=%s --directory %s --file - %s" % (
            quote(str(uid)), quote(str(gid)), mode_text, quote(workdir), quote(rel))
        cp = Cmd("docker cp", kb="docker cp")
        cp.arg("-", "コピー元", "「-」は標準入力から tar 形式のデータを受け取る、という意味です。")
        cp.arg("%s:/" % cname, "コピー先", "コンテナ %s のルート (/) を基準に展開します。" % cname)
        step.cmds.append(cp)
        lines.append("%s | %s" % (tar_cmd, cp.render(inline=True)))
        lines.append("rm -rf %s" % quote(workdir))
        step.set_script("\n".join(lines))
        step.summary = "compose は %s の中身 (content / environment) を、コンテナを起動する前にファイルとして書き込みます。同じように、一時ファイルを作って tar でまとめ、docker cp でコンテナの %s に入れます。" % (kind_ja, target)
        step.details.append("所有者 uid=%s / gid=%s、権限 %s で入れます (compose の既定は root / 0444 = 読み取り専用)。" % (uid, gid, mode_text))
        step.details.append("tar を使うのは、所有者と権限を指定でき、途中のフォルダ (%s) が無くても作ってくれるからです。" % posixpath.dirname(target))
        if inj["kind"] == "secret":
            step.notes.append("秘密の値がこのテキストファイルに書かれています。ファイルの取り扱い (共有・保管) に注意してください。")
        step.verify = ["docker cp %s:%s - | tar -tvf -" % (cname, target)]
        self.add(step)

    # ---- docker run / create ---------------------------------------------------
    def step_run(self, name, svc, cname, index, create=False):
        kind = "create" if create else "run"
        head = "docker create" if create else "docker run"
        title = ("サービス「%s」のコンテナ「%s」を作る (まだ起動しない)" if create else "サービス「%s」のコンテナ「%s」を起動する") % (name, cname)
        step = Step(kind, "コンテナ作成" if create else "コンテナ起動", title, target=cname, service=name, compose_ref="services.%s" % name)
        cmd = Cmd(head, kb=head)
        if not create:
            cmd.add("--detach", None, None, "コンテナを裏側 (バックグラウンド) で動かし、すぐにプロンプトへ戻ります (compose の up -d と同じ)。")
        self.build_run_options(cmd, name, svc, cname, index, step)
        step.cmds.append(cmd)
        step.set_script(cmd.render())
        image = self.derived.get(name) or self.images[name]
        if create:
            step.summary = "コンテナ「%s」をイメージ「%s」から作りますが、まだ起動しません。起動前にファイルの投入や初期化 (pre_start) を行うためです。" % (cname, image)
        else:
            step.summary = "イメージ「%s」からコンテナ「%s」を作って起動します (サービス「%s」%s)。" % (
                image, cname, name, "" if len(self.svc_containers(name)) == 1 else " の %d 台目" % (index + 1))
        step.details.extend(self.describe_run(name, svc, cname, cmd))
        step.verify = ["docker ps --all --filter name=%s" % cname, "docker logs %s" % cname, "docker inspect %s" % cname]
        step.compose_snippet = to_yaml({"services": {name: _strip_meta(svc)}})
        self.add(step)

    def describe_run(self, name, svc, cname, cmd):
        out = []
        nets = [o for o in cmd.opts if o.flag == "--network"]
        if nets:
            out.append("ネットワーク: " + "、".join(str(o.value) for o in nets))
        ports = [o.value for o in cmd.opts if o.flag == "--publish"]
        if ports:
            out.append("公開ポート (ホスト → コンテナ): " + "、".join(str(p) for p in ports))
        mounts = [o for o in cmd.opts if o.flag in ("--volume", "--mount", "--tmpfs", "--volumes-from")]
        if mounts:
            out.append("マウント: %d 件 (データの置き場所をコンテナにつなぎます)" % len(mounts))
        envs = [o for o in cmd.opts if o.flag in ("--env", "--env-file")]
        if envs:
            out.append("環境変数: --env %d 件 / --env-file %d 件" % (
                len([o for o in envs if o.flag == "--env"]), len([o for o in envs if o.flag == "--env-file"])))
        if svc.get("depends_on"):
            deps = ["%s (%s)" % (d, (c or {}).get("condition", "service_started")) for d, c in svc["depends_on"].items()]
            out.append("depends_on (先に起動しておくもの): " + "、".join(deps))
        return out

    def network_options(self, cmd, name, svc, cname, step, for_init=False):
        mode = svc.get("network_mode")
        src = "services.%s" % name
        if mode:
            value = mode
            note = "ネットワークの使い方を %s にします。" % mode
            if mode.startswith("service:"):
                other = mode.split(":", 1)[1]
                target = (self.svc_containers(other) or [other])[0]
                value = "container:%s" % target
                note = "サービス「%s」のコンテナ「%s」とネットワークを共有します (同じ IP・同じ localhost を使います)。compose の network_mode: service:%s と同じです。" % (other, target, other)
            elif mode == "host":
                note = "コンテナ専用のネットワークを作らず、ホスト (RHEL) のネットワークをそのまま使います。ポート公開 (-p) は不要・無効になります。"
            elif mode == "none":
                note = "ネットワークにつなぎません (ループバックのみ)。"
            elif mode == "bridge":
                note = "Docker 既定の bridge ネットワーク (docker0) につなぎます。サービス名での名前解決はできません。"
            cmd.add("--network", value, src + ".network_mode", note)
            return
        nets = svc.get("networks") or {}
        if not nets:
            return
        items = []
        for key, cfg in nets.items():
            cfg = cfg or {}
            items.append((-(int(cfg.get("priority") or 0)), key, cfg))
        items.sort(key=lambda t: (t[0], t[1]))
        advanced = len(items) > 1 or any(cfg.get("driver_opts") or cfg.get("interface_name") or cfg.get("gw_priority") for _, _, cfg in items)
        for pos, (_, key, cfg) in enumerate(items):
            netname = (self.networks.get(key) or {}).get("name") or "%s_%s" % (self.name, key)
            aliases = [name] + list(cfg.get("aliases") or [])
            mac = cfg.get("mac_address") or (svc.get("mac_address") if pos == 0 else None)
            if not advanced:
                cmd.add("--network", netname, "%s.networks.%s" % (src, key), "ネットワーク「%s」につなぎます。" % netname)
                for alias in aliases:
                    cmd.add("--network-alias", alias, "%s.networks.%s.aliases" % (src, key) if alias != name else None,
                            "このネットワークの中で「%s」という名前でも呼べるようにします。%s" % (alias, "compose はサービス名を自動で別名にします。" if alias == name else ""))
                if cfg.get("ipv4_address") and not for_init:
                    cmd.add("--ip", cfg["ipv4_address"], "%s.networks.%s.ipv4_address" % (src, key), "IPv4 アドレスを %s に固定します。" % cfg["ipv4_address"])
                if cfg.get("ipv6_address") and not for_init:
                    cmd.add("--ip6", cfg["ipv6_address"], "%s.networks.%s.ipv6_address" % (src, key), "IPv6 アドレスを %s に固定します。" % cfg["ipv6_address"])
                for lla in cfg.get("link_local_ips") or []:
                    cmd.add("--link-local-ip", lla, "%s.networks.%s.link_local_ips" % (src, key), "リンクローカル IP %s を追加します。" % lla)
                if mac and not for_init:
                    cmd.add("--mac-address", mac, "%s.mac_address" % src, "MAC アドレスを %s に固定します。" % mac)
            else:
                parts = ["name=%s" % netname] + ["alias=%s" % a for a in aliases]
                if cfg.get("ipv4_address") and not for_init:
                    parts.append("ip=%s" % cfg["ipv4_address"])
                if cfg.get("ipv6_address") and not for_init:
                    parts.append("ip6=%s" % cfg["ipv6_address"])
                for lla in cfg.get("link_local_ips") or []:
                    parts.append("link-local-ip=%s" % lla)
                if mac and not for_init:
                    parts.append("mac-address=%s" % mac)
                driver_opts = dict(cfg.get("driver_opts") or {})
                if cfg.get("interface_name"):
                    driver_opts["com.docker.network.endpoint.ifname"] = cfg["interface_name"]
                for okey, oval in driver_opts.items():
                    parts.append("driver-opt=%s=%s" % (okey, oval))
                if cfg.get("gw_priority"):
                    parts.append("gw-priority=%d" % int(cfg["gw_priority"]))
                value = ",".join(_csv_field(p) for p in parts)
                note = "ネットワーク「%s」につなぎ、%s という名前で呼べるようにします。" % (netname, "・".join(aliases))
                if pos == 0:
                    note += "(最初に書いたネットワークがメイン = 優先度 priority が一番高いもの / 同じなら名前順)。"
                if cfg.get("gw_priority"):
                    note += "外への出口 (デフォルトゲートウェイ) の優先度は %s です。" % cfg["gw_priority"]
                cmd.add("--network", value, "%s.networks.%s" % (src, key), note)
        if advanced and not for_init:
            step.notes.append("複数のネットワークを docker run 1 回でつなぐ書き方 (--network name=...,alias=...) は Docker Engine 25 以降で使えます。RHEL 9.8 で最新の docker-ce (29.x) を入れていれば問題ありません。")
        for link in svc.get("links") or []:
            other, _, alias = link.partition(":")
            alias = alias or other
            target = (self.svc_containers(other) or [other])[0]
            cmd.add("--link", "%s:%s" % (target, alias), "%s.links" % src, "古い仕組み (links) で、コンテナ「%s」を「%s」という名前で呼べるようにします。" % (target, alias))
        for link in svc.get("external_links") or []:
            other, _, alias = link.partition(":")
            cmd.add("--link", "%s:%s" % (other, alias or other), "%s.external_links" % src, "compose の外にあるコンテナ「%s」を「%s」という名前で呼べるようにします。" % (other, alias or other))

    def env_options(self, cmd, name, svc):
        final = svc.get("environment") or {}
        split = (self.meta.get("env_split") or {}).get(name)
        src = "services.%s.environment" % name
        use_files = []
        if self.o.env_mode != "inline" and split and split.get("env_file"):
            candidates = []
            for entry in split["env_file"]:
                path = entry.get("path")
                if not path or not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8-sig") as handle:
                    text = handle.read()
                if entry.get("format") == "raw":
                    pairs = envfile.parse_dotenv_raw(text)
                else:
                    try:
                        pairs = envfile.parse_dotenv(text, self.o.lookup, path)
                    except (envfile.DotenvError, envfile.InterpolationError):
                        continue
                if self.o.env_mode == "file" or envfile.docker_compatible(text, pairs):
                    docker_pairs, _ = envfile.parse_docker_envfile(text)
                    if docker_pairs is not None:
                        candidates.append((entry, docker_pairs))
            explicit = set((split.get("environment") or {}).keys())
            while True:
                docker_env = {}
                for _, pairs in candidates:
                    for key, value in pairs:
                        docker_env[key] = value
                conflict = None
                for key, value in final.items():
                    if value is None and key in docker_env:
                        conflict = key
                        break
                    if value is not None and key not in explicit and docker_env.get(key) != value and key in docker_env:
                        conflict = key
                        break
                extra = [k for k in docker_env if k not in final]
                if extra:
                    conflict = extra[0]
                if conflict is None:
                    break
                candidates = [c for c in candidates if conflict not in dict(c[1])]
            use_files = candidates
        covered = {}
        for entry, pairs in use_files:
            for key, value in pairs:
                covered[key] = value
            cmd.add("--env-file", self.map_path(entry["path"]), "services.%s.env_file" % name,
                    "ファイル %s に書かれた環境変数 (%d 個) をまとめて渡します。" % (os.path.basename(entry["path"]), len(pairs)))
        explicit = set(((split or {}).get("environment") or {}).keys()) if split else set(final.keys())
        for key, value in final.items():
            if value is None:
                cmd.add("--env", key, src, "環境変数 %s は値が書かれていないため、実行するシェルにある同じ名前の変数の値を渡します (無ければ設定しません)。" % key)
                continue
            if key in covered and covered[key] == value and key not in explicit:
                continue
            origin = "environment" if key in explicit else "env_file"
            cmd.add("--env", "%s=%s" % (key, value), src if origin == "environment" else "services.%s.env_file" % name,
                    "環境変数 %s に「%s」を設定します%s。" % (key, _short(value), "" if origin == "environment" else " (env_file から読み込んだ値)"))

    def build_run_options(self, cmd, name, svc, cname, index, step, for_init=False):
        src = "services.%s" % name
        add = cmd.add
        add("--name", cname, src + ".container_name" if svc.get("container_name") else None,
            "コンテナに「%s」という名前を付けます。%s" % (cname, "compose の container_name です。" if svc.get("container_name") else "compose の命名規則「<プロジェクト名>-<サービス名>-<番号>」と同じ名前です。"))
        if svc.get("hostname"):
            add("--hostname", svc["hostname"], src + ".hostname", "コンテナの中でのホスト名を %s にします。" % svc["hostname"])
        if svc.get("domainname"):
            add("--domainname", svc["domainname"], src + ".domainname", "コンテナのドメイン名を %s にします。" % svc["domainname"])
        restart = self.restart_policy(svc)
        if restart:
            add("--restart", restart, src + (".deploy.restart_policy" if (svc.get("deploy") or {}).get("restart_policy") else ".restart"),
                "コンテナが止まったときの再起動のルールを %s にします。" % restart)
        if svc.get("init") is True:
            add("--init", None, src + ".init", "コンテナの最初のプロセス (PID 1) として小さな init (docker-init = tini) を入れ、ゾンビプロセスの後片付けとシグナルの中継をさせます。")
        elif svc.get("init") is False:
            add("--init=false", None, src + ".init", "init を使わない設定を明示します。")
        if svc.get("user"):
            add("--user", svc["user"], src + ".user", "コンテナの中のプログラムを ユーザー %s として動かします。" % svc["user"])
        for group in svc.get("group_add") or []:
            add("--group-add", group, src + ".group_add", "そのユーザーに追加のグループ %s を足します (共有フォルダの書き込み権限などに使います)。" % group)
        if svc.get("working_dir"):
            add("--workdir", svc["working_dir"], src + ".working_dir", "コンテナの中の作業フォルダを %s にします。" % svc["working_dir"])
        self.network_options(cmd, name, svc, cname, step, for_init=for_init)
        if for_init:
            return
        for server in svc.get("dns") or []:
            add("--dns", server, src + ".dns", "名前解決 (DNS) の問い合わせ先を %s にします。" % server)
        for domain in svc.get("dns_search") or []:
            add("--dns-search", domain, src + ".dns_search", "短い名前を引くときに後ろへ補う検索ドメインを %s にします。" % domain)
        for option in svc.get("dns_opt") or []:
            add("--dns-option", option, src + ".dns_opt", "DNS の動きの細かい設定 %s です。" % option)
        for entry in sorted(svc.get("extra_hosts") or [], key=lambda e: e.split("=", 1)[0]):
            host, _, addr = entry.partition("=")
            add("--add-host", "%s:%s" % (host, addr), src + ".extra_hosts",
                "コンテナの /etc/hosts に「%s → %s」を書き足します%s。" % (host, addr, " (host-gateway はホスト自身の IP に置き換わります)" if addr == "host-gateway" else ""))
        for port in svc.get("ports") or []:
            add("--publish", _publish_value(port), src + ".ports", _publish_note(port))
        for exp in svc.get("expose") or []:
            add("--expose", exp, src + ".expose", "コンテナが %s 番ポートを使うことを宣言します (ホストには公開しません)。" % exp)
        self.mount_options(cmd, name, svc, step)
        self.env_options(cmd, name, svc)
        for lkey, lval in (svc.get("labels") or {}).items():
            add("--label", "%s=%s" % (lkey, lval), src + ".labels", "コンテナに目印 (ラベル) %s=%s を付けます。" % (lkey, _short(lval)))
        if self.o.compose_labels:
            add("--label", "com.docker.compose.project=%s" % self.name, None, "compose が付けるラベル (プロジェクト名)。")
            add("--label", "com.docker.compose.service=%s" % name, None, "compose が付けるラベル (サービス名)。")
            add("--label", "com.docker.compose.container-number=%d" % (index + 1), None, "compose が付けるラベル (何台目か)。")
            add("--label", "com.docker.compose.oneoff=False", None, "compose が付けるラベル (run で作った一時コンテナではない)。")
            if self.o.compose_version:
                add("--label", "com.docker.compose.version=%s" % self.o.compose_version, None, "compose が付けるラベル (compose のバージョン)。")
        for akey, aval in (svc.get("annotations") or {}).items():
            add("--annotation", "%s=%s" % (akey, aval), src + ".annotations", "OCI ランタイムへ渡す注釈 %s=%s を付けます。" % (akey, aval))
        if svc.get("privileged"):
            add("--privileged", None, src + ".privileged", "特権モード: ホストのほぼすべての機能 (デバイスなど) をコンテナに許可します。とても強い権限なので注意。")
        if svc.get("read_only"):
            add("--read-only", None, src + ".read_only", "コンテナのファイルシステムを読み取り専用にします (書けるのはボリュームや tmpfs だけ)。")
        for cap in svc.get("cap_add") or []:
            add("--cap-add", cap, src + ".cap_add", "Linux の特権の一部 (ケーパビリティ) %s を追加で許可します。" % cap)
        for cap in svc.get("cap_drop") or []:
            add("--cap-drop", cap, src + ".cap_drop", "Linux の特権の一部 (ケーパビリティ) %s を取り上げます。" % cap)
        for opt in svc.get("security_opt") or []:
            value = opt
            match = re.match(r"^(seccomp)[=:](.+)$", opt)
            if match and match.group(2) not in ("unconfined", "builtin"):
                path = match.group(2)
                if not os.path.isabs(path):
                    path = os.path.join(self.local_dir, path)
                value = concat("seccomp=", self.map_path(path))
            add("--security-opt", value, src + ".security_opt", _security_note(opt))
        if svc.get("userns_mode"):
            add("--userns", svc["userns_mode"], src + ".userns_mode", "ユーザー名前空間の設定を %s にします。" % svc["userns_mode"])
        for key, flag in (("pid", "--pid"), ("ipc", "--ipc")):
            val = svc.get(key)
            if val:
                if val.startswith("service:"):
                    other = val.split(":", 1)[1]
                    val = "container:%s" % (self.svc_containers(other) or [other])[0]
                add(flag, val, src + "." + key, "%s 名前空間の設定を %s にします。" % (key.upper(), val))
        if svc.get("uts"):
            add("--uts", svc["uts"], src + ".uts", "UTS 名前空間 (ホスト名) の設定を %s にします。" % svc["uts"])
        if svc.get("cgroup"):
            add("--cgroupns", svc["cgroup"], src + ".cgroup", "cgroup 名前空間を %s にします。" % svc["cgroup"])
        if svc.get("cgroup_parent"):
            add("--cgroup-parent", svc["cgroup_parent"], src + ".cgroup_parent", "親の cgroup を %s にします。" % svc["cgroup_parent"])
        for dev in svc.get("devices") or []:
            if dev.get("source") == dev.get("target") and "=" in (dev.get("source") or ""):
                add("--device", dev["source"], src + ".devices", "CDI デバイス %s をコンテナに渡します。" % dev["source"])
                continue
            value = "%s:%s" % (dev.get("source"), dev.get("target") or dev.get("source"))
            if dev.get("permissions") and dev.get("permissions") != "rwm":
                value += ":" + dev["permissions"]
            add("--device", value, src + ".devices", "ホストのデバイス %s をコンテナの %s として使えるようにします。" % (dev.get("source"), dev.get("target") or dev.get("source")))
        for rule in svc.get("device_cgroup_rules") or []:
            add("--device-cgroup-rule", rule, src + ".device_cgroup_rules", "デバイスを使う許可のルール %s を追加します。" % rule)
        for gpu in self.gpu_requests(svc):
            add("--gpus", gpu, src + (".gpus" if svc.get("gpus") else ".deploy.resources.reservations.devices"), "GPU を使えるようにします (%s)。NVIDIA Container Toolkit などの準備が必要です。" % gpu)
        for skey, sval in (svc.get("sysctls") or {}).items():
            add("--sysctl", "%s=%s" % (skey, sval), src + ".sysctls", "コンテナの中のカーネル設定 %s を %s にします。" % (skey, sval))
        for uname, uval in (svc.get("ulimits") or {}).items():
            add("--ulimit", _ulimit_value(uname, uval), src + ".ulimits", "資源の上限 (ulimit) %s を %s にします。" % (uname, _ulimit_value(uname, uval).split("=", 1)[1]))
        if svc.get("runtime"):
            add("--runtime", svc["runtime"], src + ".runtime", "OCI ランタイムを %s にします。" % svc["runtime"])
        if svc.get("isolation"):
            add("--isolation", svc["isolation"], src + ".isolation", "分離方式を %s にします (主に Windows コンテナ用)。" % svc["isolation"])
        for skey, sval in (svc.get("storage_opt") or {}).items():
            add("--storage-opt", "%s=%s" % (skey, sval), src + ".storage_opt", "ストレージドライバーへの設定 %s=%s です。" % (skey, sval))
        if svc.get("oom_kill_disable"):
            add("--oom-kill-disable", None, src + ".oom_kill_disable", "メモリ不足でもこのコンテナを強制終了させない設定です (メモリ上限と一緒に使います)。")
        if svc.get("oom_score_adj") is not None:
            add("--oom-score-adj", str(svc["oom_score_adj"]), src + ".oom_score_adj", "メモリ不足のときに止められやすさを %s だけ調整します。" % svc["oom_score_adj"])
        self.resource_options(cmd, name, svc)
        logging = svc.get("logging") or {}
        if logging.get("driver"):
            add("--log-driver", logging["driver"], src + ".logging.driver", "ログ (コンテナの出力) の保存方法を %s にします。" % logging["driver"])
        for lkey, lval in (logging.get("options") or {}).items():
            add("--log-opt", "%s=%s" % (lkey, lval), src + ".logging.options", "ログ保存の設定 %s=%s です。" % (lkey, lval))
        self.healthcheck_options(cmd, name, svc)
        if svc.get("stop_signal"):
            add("--stop-signal", svc["stop_signal"], src + ".stop_signal", "コンテナを止めるときに送る合図 (シグナル) を %s にします。" % svc["stop_signal"])
        if svc.get("stop_grace_period"):
            seconds = duration_seconds(svc["stop_grace_period"])
            add("--stop-timeout", str(seconds), src + ".stop_grace_period",
                "止めるとき、合図を送ってから %d 秒待っても終わらなければ強制終了 (SIGKILL) します (compose の stop_grace_period: %s)。" % (seconds, svc["stop_grace_period"]))
        if svc.get("tty"):
            add("--tty", None, src + ".tty", "疑似ターミナル (TTY) を割り当てます。")
        if svc.get("stdin_open"):
            add("--interactive", None, src + ".stdin_open", "標準入力を開いたままにします。")
        if svc.get("platform"):
            add("--platform", svc["platform"], src + ".platform", "CPU の種類 (プラットフォーム) %s 用のイメージで動かします。" % svc["platform"])
        if (svc.get("pull_policy") or "").lower() == "never":
            add("--pull", "never", src + ".pull_policy", "イメージを自動でダウンロードしません (手元に無ければエラー)。")
        if svc.get("use_api_socket"):
            add("--use-api-socket", None, src + ".use_api_socket", "Docker Engine の API ソケットと認証情報をコンテナに渡します (コンテナから docker を操作できます)。")
        if svc.get("models"):
            self.warn("services.%s: models (Docker Model Runner の AI モデル) は docker run では再現できません。docker model コマンドで別途用意してください。" % name)
        entry = svc.get("entrypoint")
        command = svc.get("command")
        args = []
        if entry is not None:
            if len(entry) == 0 or (len(entry) == 1 and entry[0] == ""):
                add("--entrypoint", "", src + ".entrypoint", "イメージの ENTRYPOINT を空にします。")
                args = list(command or [])
            else:
                add("--entrypoint", entry[0], src + ".entrypoint",
                    "最初に動かすプログラム (ENTRYPOINT) を %s にします。%s" % (entry[0], ("残りの部分 %s はイメージ名の後ろに引数として書きます (docker run の --entrypoint には 1 語しか書けないため)。" % " ".join(entry[1:])) if len(entry) > 1 else ""))
                args = list(entry[1:]) + list(command or [])
                step.notes.append("compose で entrypoint を指定すると、イメージの CMD は使われません (docker run --entrypoint も同じ)。")
        else:
            args = list(command or [])
        image = self.derived.get(name) or self.images[name]
        cmd.arg(image, "イメージ", ("ヘルスチェック入りの派生イメージ (元: %s) です。" % self.images[name]) if name in self.derived else "このイメージからコンテナを作ります。", kb="run.image", src=src + (".image" if svc.get("image") else ".build"))
        if args:
            cmd.command_args(args, src + (".command" if command else ".entrypoint"),
                             "イメージ名の後ろは、コンテナの中で実行するコマンドと引数です (compose の command)。")

    def restart_policy(self, svc):
        policy = None
        if svc.get("restart"):
            parts = svc["restart"].split(":")
            policy = _map_restart(parts[0])
            if len(parts) > 1 and parts[1]:
                policy += ":" + parts[1]
        deploy = svc.get("deploy") or {}
        rp = deploy.get("restart_policy")
        if rp:
            policy = _map_restart(rp.get("condition") or "")
            if rp.get("max_attempts") and policy == "on-failure":
                policy += ":%d" % int(rp["max_attempts"])
        if policy in (None, "", "no"):
            return None
        return policy

    def gpu_requests(self, svc):
        out = []
        for gpu in svc.get("gpus") or []:
            out.append(_gpu_value(gpu))
        deploy = svc.get("deploy") or {}
        res = (deploy.get("resources") or {}).get("reservations") or {}
        for dev in res.get("devices") or []:
            caps = dev.get("capabilities") or []
            if "gpu" in caps or (dev.get("driver") == "nvidia"):
                out.append(_gpu_value(dev))
        return out

    def resource_options(self, cmd, name, svc):
        src = "services.%s" % name
        add = cmd.add
        deploy = svc.get("deploy") or {}
        limits = (deploy.get("resources") or {}).get("limits") or {}
        reservations = (deploy.get("resources") or {}).get("reservations") or {}
        cpus = limits.get("cpus") if limits.get("cpus") else svc.get("cpus")
        if cpus:
            add("--cpus", _num(cpus), src + (".deploy.resources.limits.cpus" if limits.get("cpus") else ".cpus"),
                "使える CPU を %s 個分までに制限します。" % _num(cpus))
        if svc.get("cpu_shares"):
            add("--cpu-shares", str(svc["cpu_shares"]), src + ".cpu_shares", "CPU が混み合ったときの取り分の重み (既定 1024) を %s にします。" % svc["cpu_shares"])
        if svc.get("cpu_period"):
            add("--cpu-period", str(svc["cpu_period"]), src + ".cpu_period", "CPU 制限の計測周期 (マイクロ秒) です。")
        if svc.get("cpu_quota"):
            add("--cpu-quota", str(svc["cpu_quota"]), src + ".cpu_quota", "1 周期に使える CPU 時間 (マイクロ秒) です。")
        if svc.get("cpu_rt_period"):
            add("--cpu-rt-period", str(duration_micro(svc["cpu_rt_period"])), src + ".cpu_rt_period", "リアルタイム処理の周期 (マイクロ秒) です。")
        if svc.get("cpu_rt_runtime"):
            add("--cpu-rt-runtime", str(duration_micro(svc["cpu_rt_runtime"])), src + ".cpu_rt_runtime", "リアルタイム処理に使える時間 (マイクロ秒) です。")
        if svc.get("cpuset"):
            add("--cpuset-cpus", svc["cpuset"], src + ".cpuset", "使う CPU を %s 番に限定します。" % svc["cpuset"])
        if svc.get("cpu_count"):
            add("--cpu-count", str(svc["cpu_count"]), src + ".cpu_count", "使える CPU の数 (Windows 用) です。")
        if svc.get("cpu_percent"):
            add("--cpu-percent", _num(svc["cpu_percent"]), src + ".cpu_percent", "使える CPU の割合 (Windows 用) です。")
        memory = limits.get("memory") if limits.get("memory") else svc.get("mem_limit")
        if memory:
            add("--memory", human_bytes(memory), src + (".deploy.resources.limits.memory" if limits.get("memory") else ".mem_limit"),
                "使えるメモリを %s までに制限します。超えるとコンテナ内のプロセスが強制終了 (OOM Kill) されます。" % human_bytes(memory))
        mem_res = reservations.get("memory") if reservations.get("memory") else svc.get("mem_reservation")
        if mem_res:
            add("--memory-reservation", human_bytes(mem_res), src + (".deploy.resources.reservations.memory" if reservations.get("memory") else ".mem_reservation"),
                "メモリが足りなくなってきたときに、最低限確保しようとする量 (ソフト制限) を %s にします。" % human_bytes(mem_res))
        if svc.get("memswap_limit"):
            value = svc["memswap_limit"]
            add("--memory-swap", "-1" if value == -1 else human_bytes(value), src + ".memswap_limit", "メモリ＋スワップの合計の上限です (-1 は無制限)。")
        if svc.get("mem_swappiness") is not None:
            add("--memory-swappiness", str(svc["mem_swappiness"]), src + ".mem_swappiness", "スワップの使いやすさ (0〜100) です。")
        pids = limits.get("pids") if limits.get("pids") else svc.get("pids_limit")
        if pids:
            add("--pids-limit", str(pids), src + (".deploy.resources.limits.pids" if limits.get("pids") else ".pids_limit"),
                "コンテナの中で同時に動かせるプロセスの数を %s までにします。" % pids)
        if svc.get("shm_size"):
            add("--shm-size", human_bytes(svc["shm_size"]), src + ".shm_size", "共有メモリ (/dev/shm) の大きさを %s にします (既定は 64m)。" % human_bytes(svc["shm_size"]))
        blk = svc.get("blkio_config") or {}
        if blk.get("weight"):
            add("--blkio-weight", str(blk["weight"]), src + ".blkio_config.weight", "ディスク I/O の取り分の重みです。")
        for item in blk.get("weight_device") or []:
            add("--blkio-weight-device", "%s:%s" % (item.get("path"), item.get("weight")), src + ".blkio_config.weight_device", "デバイスごとのディスク I/O の重みです。")
        for key, flag in (("device_read_bps", "--device-read-bps"), ("device_write_bps", "--device-write-bps"),
                          ("device_read_iops", "--device-read-iops"), ("device_write_iops", "--device-write-iops")):
            for item in blk.get(key) or []:
                add(flag, "%s:%s" % (item.get("path"), item.get("rate")), src + ".blkio_config." + key, "デバイスごとの読み書きの速さの上限です。")
        if reservations.get("cpus"):
            self.warn("services.%s: deploy.resources.reservations.cpus は Swarm 用の設定のため、compose も docker run も使いません (無視されます)。" % name)

    def healthcheck_options(self, cmd, name, svc):
        hc = svc.get("healthcheck")
        if not hc:
            return
        src = "services.%s.healthcheck" % name
        add = cmd.add
        test = hc.get("test") or []
        if hc.get("disable") or (test and test[0] == "NONE"):
            add("--no-healthcheck", None, src, "イメージに HEALTHCHECK があっても、ヘルスチェックを行わないようにします。")
            return
        if name in self.derived:
            return
        if test:
            if test[0] == "CMD-SHELL":
                add("--health-cmd", test[1] if len(test) > 1 else "", src + ".test", "ヘルスチェック (健康診断) で実行するコマンドです。/bin/sh -c で実行され、終了コード 0 なら合格です。")
            elif test[0] == "CMD":
                add("--health-cmd", _shell_join(test[1:]), src + ".test", "ヘルスチェックのコマンドです (exec 形式をシェル形式に置き換えています)。")
            else:
                add("--health-cmd", _shell_join(test), src + ".test", "ヘルスチェックのコマンドです。")
        for key, flag, ja in (("interval", "--health-interval", "何秒おきにチェックするか"),
                              ("timeout", "--health-timeout", "1 回のチェックを何秒で打ち切るか"),
                              ("start_period", "--health-start-period", "起動直後の、失敗を数えない猶予期間"),
                              ("start_interval", "--health-start-interval", "猶予期間中のチェック間隔")):
            if hc.get(key):
                add(flag, hc[key], "%s.%s" % (src, key), "%s: %s" % (ja, hc[key]))
        if hc.get("retries") is not None:
            add("--health-retries", str(hc["retries"]), src + ".retries", "何回続けて失敗したら unhealthy (不健康) とするか: %s 回" % hc["retries"])

    def mount_options(self, cmd, name, svc, step):
        src = "services.%s.volumes" % name
        add = cmd.add
        for vol in svc.get("volumes") or []:
            vtype = vol.get("type") or "volume"
            target = vol.get("target")
            ro = bool(vol.get("read_only"))
            if vtype == "bind":
                source = self.map_path(vol.get("source"))
                bind = vol.get("bind")
                propagation = (bind or {}).get("propagation")
                selinux = (bind or {}).get("selinux")
                recursive = (bind or {}).get("recursive")
                create = bind is None or (bind or {}).get("create_host_path", True) is not False
                if (propagation or recursive or not create) and not selinux:
                    parts = ["type=bind", ("source=", source), "target=%s" % target]
                    if ro:
                        parts.append("readonly")
                    if propagation:
                        parts.append("bind-propagation=%s" % propagation)
                    if recursive:
                        parts.append("bind-recursive=%s" % recursive)
                    if create:
                        parts.append("bind-create-src")
                    add("--mount", _mount_value(parts), src,
                        "ホストのフォルダ/ファイル %s をコンテナの %s につなぎます%s。" % (_shown(source), target, " (読み取り専用)" if ro else ""))
                else:
                    opts = []
                    if ro:
                        opts.append("ro")
                    if selinux:
                        opts.append(selinux)
                    if propagation:
                        opts.append(propagation)
                    value = concat(source, ":%s" % target + ((":" + ",".join(opts)) if opts else ""))
                    add("--volume", value, src,
                        "ホストの %s をコンテナの %s に直接つなぎます (バインドマウント%s)。ホスト側に無ければ空のフォルダが作られます。" % (
                            _shown(source), target, "・読み取り専用" if ro else ""))
                    if not os.path.exists(vol.get("source") or "") and not self.pwd_mode:
                        step.notes.append("バインドマウント元 %s が (変換したときには) まだありません。docker も compose も、無ければ空のフォルダを自動で作ります。" % _shown(source))
            elif vtype == "volume":
                source = vol.get("source")
                vopts = vol.get("volume") or {}
                if not source:
                    parts = ["type=volume", "target=%s" % target]
                    if ro:
                        parts.append("readonly")
                    if vopts.get("nocopy"):
                        parts.append("volume-nocopy")
                    add("--mount", _mount_value(parts), src, "名前の無い (匿名) ボリュームを新しく作って %s につなぎます。" % target)
                    continue
                volname = (self.volumes.get(source) or {}).get("name") or source
                if vopts.get("nocopy") or vopts.get("subpath") or vopts.get("labels"):
                    parts = ["type=volume", "source=%s" % volname, "target=%s" % target]
                    if ro:
                        parts.append("readonly")
                    if vopts.get("nocopy"):
                        parts.append("volume-nocopy")
                    if vopts.get("subpath"):
                        parts.append("volume-subpath=%s" % vopts["subpath"])
                    for lkey, lval in (vopts.get("labels") or {}).items():
                        parts.append("volume-label=%s=%s" % (lkey, lval))
                    add("--mount", _mount_value(parts), src, "名前付きボリューム「%s」を %s につなぎます%s%s。" % (
                        volname, target, " (中の %s だけ)" % vopts["subpath"] if vopts.get("subpath") else "",
                        "。イメージの中身をコピーしません (nocopy)" if vopts.get("nocopy") else ""))
                else:
                    add("--volume", "%s:%s%s" % (volname, target, ":ro" if ro else ""), src,
                        "名前付きボリューム「%s」をコンテナの %s につなぎます%s。" % (volname, target, " (読み取り専用)" if ro else ""))
            elif vtype == "tmpfs":
                parts = ["type=tmpfs", "target=%s" % target]
                tmpfs = vol.get("tmpfs") or {}
                if tmpfs.get("size"):
                    parts.append("tmpfs-size=%d" % int(tmpfs["size"]))
                if tmpfs.get("mode") is not None:
                    parts.append("tmpfs-mode=%o" % int(tmpfs["mode"]))
                add("--mount", _mount_value(parts), src, "メモリ上の一時的な場所 (tmpfs) を %s に作ります。コンテナを止めると消えます。" % target)
            elif vtype == "image":
                parts = ["type=image", "source=%s" % vol.get("source"), "target=%s" % target]
                sub = (vol.get("image") or {}).get("subpath")
                if sub:
                    parts.append("image-subpath=%s" % sub)
                add("--mount", _mount_value(parts), src, "イメージ %s の中身を読み取り専用で %s に見せます (Docker 28 以降)。" % (vol.get("source"), target))
            else:
                self.warn("services.%s.volumes: type %s は docker コマンドで再現できません。" % (name, vtype))
        for item in svc.get("tmpfs") or []:
            add("--tmpfs", item, "services.%s.tmpfs" % name, "メモリ上の一時的な場所 (tmpfs) を %s に作ります。" % item.split(":", 1)[0])
        for vf in svc.get("volumes_from") or []:
            parts = vf.split(":")
            if parts[0] == "container":
                target = parts[1]
                mode = parts[2] if len(parts) > 2 else ""
            else:
                target = (self.svc_containers(parts[0]) or [parts[0]])[0]
                mode = parts[1] if len(parts) > 1 else ""
            add("--volumes-from", target, "services.%s.volumes_from" % name,
                "コンテナ「%s」と同じボリュームを、同じ場所につなぎます。" % target)
            if mode:
                step.notes.append("compose の volumes_from: %s の「:%s」は、compose v5 では実際には反映されません (Docker へは付けずに渡されます)。compose と同じ結果にするため、ここでも付けていません。読み取り専用にしたいときは --volumes-from %s:%s に書き換えてください。" % (vf, mode, target, mode))
        for ref in svc.get("secrets") or []:
            source = ref.get("source")
            secret = self.secrets.get(source) or {}
            if not secret.get("file"):
                continue
            target = ref.get("target") or "/run/secrets/" + source
            if not target.startswith("/"):
                target = "/run/secrets/" + target
            add("--mount", _mount_value(["type=bind", ("source=", self.map_path(secret["file"])), "target=%s" % target, "readonly"]),
                "services.%s.secrets" % name, "秘密情報 (secrets.%s) のファイルを、読み取り専用で %s に置きます。" % (source, target))
            if ref.get("uid") or ref.get("gid") or ref.get("mode") is not None:
                step.notes.append("secrets.%s の uid/gid/mode は、ファイルから作る secret では compose も反映しません (同じく無視しています)。" % source)
        for ref in svc.get("configs") or []:
            source = ref.get("source")
            cfg = self.configs.get(source) or {}
            if not cfg.get("file"):
                continue
            target = ref.get("target") or "/" + source
            if not target.startswith("/"):
                target = "/" + target
            add("--mount", _mount_value(["type=bind", ("source=", self.map_path(cfg["file"])), "target=%s" % target, "readonly"]),
                "services.%s.configs" % name, "設定ファイル (configs.%s) を、読み取り専用で %s に置きます。" % (source, target))

    # ---- start / init / hooks ---------------------------------------------
    def step_start(self, name, cname, pre_start, injections):
        step = Step("start", "コンテナ起動", "コンテナ「%s」を起動する" % cname, target=cname, service=name, compose_ref="services.%s" % name)
        cmd = Cmd("docker start", kb="docker start")
        cmd.arg(cname, "コンテナ名", "docker create で作っておいたコンテナです。")
        step.cmds.append(cmd)
        step.set_script(cmd.render())
        why = []
        if injections:
            why.append("ファイルの投入")
        if pre_start:
            why.append("初期化コンテナ (pre_start)")
        step.summary = "%s が終わったので、コンテナ「%s」を起動します。" % ("・".join(why), cname)
        step.verify = ["docker ps --filter name=%s" % cname, "docker logs %s" % cname]
        self.add(step)

    def step_init_container(self, name, svc, cname, hook, index):
        src = "services.%s.pre_start[%d]" % (name, index)
        image = hook.get("image") or self.images[name]
        step = Step("init", "初期化コンテナ", "サービス「%s」の起動前の初期化 %d (pre_start) を実行する" % (name, index + 1),
                    target=cname, service=name, compose_ref=src)
        cmd = Cmd("docker run", kb="docker run (init)")
        cmd.add("--rm", None, None, "終わったらこの一時的なコンテナを自動で削除します (compose も実行後に削除します)。")
        cmd.add("--volumes-from", cname, None, "本番のコンテナ「%s」と同じボリューム・バインドマウントを同じ場所につなぎます。初期化で作ったファイルが本番から見えるようにするためです。" % cname)
        fake = dict(svc)
        fake.pop("hostname", None)
        self.network_options(cmd, name, fake, cname, step, for_init=True)
        if hook.get("user"):
            cmd.add("--user", hook["user"], src + ".user", "初期化はユーザー %s で行います。" % hook["user"])
        if hook.get("working_dir"):
            cmd.add("--workdir", hook["working_dir"], src + ".working_dir", "初期化の作業フォルダを %s にします。" % hook["working_dir"])
        if hook.get("privileged"):
            cmd.add("--privileged", None, src + ".privileged", "初期化を特権モードで行います。")
        self.env_options(cmd, name, svc)
        for key, val in (hook.get("environment") or {}).items():
            if val is None:
                cmd.add("--env", key, src + ".environment", "初期化用の環境変数 %s (値はシェルから) です。" % key)
            else:
                cmd.add("--env", "%s=%s" % (key, val), src + ".environment", "初期化用の環境変数 %s=%s です。" % (key, _short(val)))
        cmd.arg(image, "イメージ", "初期化に使うイメージです (指定が無ければサービスと同じイメージ)。", kb="run.image")
        command = hook.get("command") or []
        if command:
            cmd.command_args(command, src + ".command", "初期化で実行するコマンドです。")
        step.cmds.append(cmd)
        step.set_script(cmd.render())
        step.summary = "compose v5.3 で追加された init コンテナ (pre_start) を再現します。本番コンテナを作った後・起動する前に、使い捨てのコンテナで準備作業を 1 回だけ行います。"
        step.details.append("compose と同じく、本番コンテナと同じネットワーク・同じボリュームを使います (--volumes-from)。")
        step.details.append("終了コードが 0 以外 (失敗) の場合、compose はこのサービスと、これに依存するサービスを起動しません。エラーが出たらここで止めて原因を確認してください。")
        step.verify = ["docker logs %s  (初期化コンテナは --rm で消えるため、上の画面出力で確認します)" % cname]
        self.add(step)

    def step_hooks(self, name, svc, cname, kind):
        hooks = svc.get(kind) or []
        for idx, hook in enumerate(hooks):
            src = "services.%s.%s[%d]" % (name, kind, idx)
            step = Step(kind, "起動後フック" if kind == "post_start" else "停止前フック",
                        "コンテナ「%s」で %s フック %d を実行する" % (cname, kind, idx + 1), target=cname, service=name, compose_ref=src)
            cmd = Cmd("docker exec", kb="docker exec")
            if hook.get("user"):
                cmd.add("--user", hook["user"], src + ".user", "ユーザー %s として実行します。" % hook["user"])
            if hook.get("privileged"):
                cmd.add("--privileged", None, src + ".privileged", "特権を付けて実行します。")
            if hook.get("working_dir"):
                cmd.add("--workdir", hook["working_dir"], src + ".working_dir", "作業フォルダ %s で実行します。" % hook["working_dir"])
            for key, val in (hook.get("environment") or {}).items():
                cmd.add("--env", key if val is None else "%s=%s" % (key, val), src + ".environment", "このフックだけで使う環境変数です。")
            cmd.arg(cname, "コンテナ名", "コマンドを実行する (起動中の) コンテナです。")
            command = hook.get("command") or []
            if isinstance(command, str):
                command = [command]
            cmd.command_args(command, src + ".command", "コンテナの中で実行するコマンドです。")
            step.cmds.append(cmd)
            step.set_script(cmd.render())
            if kind == "post_start":
                step.summary = "compose の post_start フック (コンテナ起動直後に中で実行するコマンド) を docker exec で再現します。"
            else:
                step.summary = "compose の pre_stop フック (止める直前に中で実行するコマンド) を docker exec で再現します。"
            step.verify = ["docker logs %s" % cname]
            if kind == "pre_stop":
                self.plan.down_steps.append(step)
            else:
                self.add(step)

    # ---- 確認 ---------------------------------------------------------------
    def step_check(self):
        step = Step("check", "状態確認", "起動したコンテナの状態を確認する")
        cmd = Cmd("docker ps", kb="docker ps")
        cmd.add("--all", None, None, "止まっているコンテナも含めて表示します。")
        cmd.add("--format", "table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}", None, "名前・イメージ・状態・ポートを表の形で表示します。")
        step.cmds.append(cmd)
        step.set_script(cmd.render())
        names = [c for s in self.order for c in self.svc_containers(s)]
        step.summary = "作ったコンテナ (%s) が Up (起動中) になっているか、ヘルスチェックの結果 (healthy など) を確認します。" % "、".join(names)
        step.details.append("STATUS が「Up ... (healthy)」なら正常、「Exited (0)」は正常終了 (1 回だけ動くコンテナ)、「Exited (1)」などは異常終了です。")
        step.details.append("うまく動いていないコンテナは docker logs <コンテナ名> で出力 (ログ) を確認します。")
        step.verify = ["docker logs <コンテナ名>", "docker stats --no-stream"]
        self.add(step)

    # ---- 後片付け -------------------------------------------------------------
    def down(self):
        reverse = list(reversed(self.order))
        for name in reverse:
            svc = self.services[name]
            for cname in self.svc_containers(name):
                self.step_hooks(name, svc, cname, "pre_stop")
        for name in reverse:
            for cname in self.svc_containers(name):
                step = Step("stop", "停止", "コンテナ「%s」を止める" % cname, target=cname, service=name, compose_ref="services.%s" % name)
                cmd = Cmd("docker stop", kb="docker stop")
                cmd.arg(cname, "コンテナ名", "止めるコンテナです。")
                step.cmds.append(cmd)
                step.set_script(cmd.render())
                step.summary = "コンテナ「%s」に停止の合図 (既定は SIGTERM) を送り、終わるまで待ちます (時間切れなら強制終了)。依存されている側を後で止めるため、起動と逆の順番です。" % cname
                self.plan.down_steps.append(step)
        names = [c for s in reverse for c in self.svc_containers(s)]
        if names:
            step = Step("rm", "削除", "コンテナを削除する")
            cmd = Cmd("docker rm", kb="docker rm")
            for cname in names:
                cmd.arg(cname, "コンテナ名", "削除するコンテナです。")
            step.cmds.append(cmd)
            step.set_script(cmd.render())
            step.summary = "止めたコンテナを削除します (compose down と同じ。名前付きボリュームは残ります)。"
            self.plan.down_steps.append(step)
        net_order = list(reversed(self.meta.get("network_order") or list(self.networks)))
        nets = [(self.networks[k].get("name") or "%s_%s" % (self.name, k)) for k in net_order
                if k in self.networks and not self.networks[k].get("external")]
        if nets:
            step = Step("network_rm", "削除", "ネットワークを削除する")
            cmd = Cmd("docker network rm", kb="docker network rm")
            for net in nets:
                cmd.arg(net, "ネットワーク名", "削除するネットワークです。")
            step.cmds.append(cmd)
            step.set_script(cmd.render())
            step.summary = "このプロジェクトで作ったネットワークを削除します (compose down と同じ)。"
            self.plan.down_steps.append(step)
        vol_order = list(reversed(self.meta.get("volume_order") or list(self.volumes)))
        vols = [(self.volumes[k].get("name") or "%s_%s" % (self.name, k)) for k in vol_order
                if k in self.volumes and not self.volumes[k].get("external")]
        if vols:
            step = Step("volume_rm", "削除 (任意)", "ボリュームを削除する (データが消えます)")
            cmd = Cmd("docker volume rm", kb="docker volume rm")
            for vol in vols:
                cmd.arg(vol, "ボリューム名", "削除するボリュームです。")
            step.cmds.append(cmd)
            step.set_script("# " + cmd.render().replace("\n", "\n# "))
            step.summary = "名前付きボリュームを削除します (compose down -v と同じ)。データが消えるため、必要なときだけ先頭の # を外して実行してください。"
            self.plan.down_steps.append(step)
        images = []
        for name in self.order:
            if self.services[name].get("build") is not None and self.images.get(name) and self.images[name] not in images:
                images.append(self.images[name])
            if name in self.derived and self.derived[name] not in images:
                images.append(self.derived[name])
        if images:
            step = Step("image_rm", "削除 (任意)", "作ったイメージを削除する")
            cmd = Cmd("docker image rm", kb="docker image rm")
            for img in images:
                cmd.arg(img, "イメージ名", "このプロジェクトでビルドしたイメージです。")
            step.cmds.append(cmd)
            step.set_script("# " + cmd.render().replace("\n", "\n# "))
            step.summary = "ビルドしたイメージ・ヘルスチェック入りイメージを削除します (compose down --rmi local と同じ)。必要なときだけ先頭の # を外して実行してください。"
            self.plan.down_steps.append(step)

    # ---- 対応表 --------------------------------------------------------------
    def mapping_rows(self, name, svc):
        rows = self.plan.mapping_rows
        for step in self.plan.steps:
            if step.service != name or step.kind not in ("run", "create"):
                continue
            for cmdx in step.cmds:
                for opt in cmdx.opts:
                    rows.append({
                        "service": name, "container": step.target, "compose": opt.src or "(compose が自動で付与)",
                        "docker": opt.flag, "value": opt.display_value(), "note": opt.note or "",
                    })
            break

    # ---- 全体 ---------------------------------------------------------------
    def build(self):
        self.order_services()
        self.prepare_names()
        self.step_prepare()
        self.step_networks()
        self.step_volumes()
        self.step_pulls()
        self.step_builds()
        self.step_healthcheck_images()
        self.step_services()
        self.step_check()
        self.down()
        for idx, step in enumerate(self.plan.steps):
            step.no = idx + 1
        for idx, step in enumerate(self.plan.down_steps):
            step.no = idx + 1
        self.plan.warnings = list(self.meta.get("warnings") or []) + self.warnings
        for name, profiles in (self.meta.get("disabled_services") or {}).items():
            self.plan.warnings.append("services.%s は profiles (%s) が有効になっていないため起動しません (compose の up と同じ)。起動したいときは --profile %s を付けて変換し直してください。" % (
                name, ", ".join(profiles or []), (profiles or [""])[0]))
        files = list(self.meta.get("files") or [])
        self.plan.info = {
            "files_local": files,
            "files_on_host": [_shown(self.map_path(f)) for f in files],
            "project": self.name,
            "services": self.order,
            "containers": {s: self.svc_containers(s) for s in self.order},
            "images": self.images,
            "derived": self.derived,
            "pwd_mode": self.pwd_mode,
            "host_dir": self.host_dir,
            "local_dir": self.local_dir,
        }
        return self.plan


# ---------------------------------------------------------------------------
# 小さな部品
# ---------------------------------------------------------------------------
def _strip_meta(value):
    if isinstance(value, dict):
        return {k: _strip_meta(v) for k, v in value.items() if not str(k).startswith("_") and v is not None}
    if isinstance(value, list):
        return [_strip_meta(v) for v in value]
    return value


def _shown(path):
    """説明文に載せるためのパス表示 ("$PWD"/x → $PWD/x)。"""
    return str(path).replace('"$PWD"', "$PWD")


def _short(value, limit=60):
    text = str(value).replace("\n", "\\n")
    return text if len(text) <= limit else text[:limit] + "…"


def _num(value):
    value = float(value)
    return str(int(value)) if value == int(value) else ("%g" % value)


def _map_restart(condition):
    mapping = {"none": "no", "no": "no", "on-failure": "on-failure", "unless-stopped": "unless-stopped",
               "any": "always", "always": "always", "": "no"}
    return mapping.get(condition, condition)


def _ulimit_value(name, value):
    if isinstance(value, dict):
        return "%s=%s:%s" % (name, value.get("soft"), value.get("hard"))
    return "%s=%s" % (name, value)


def _gpu_value(gpu):
    parts = []
    count = gpu.get("count")
    ids = gpu.get("device_ids") or gpu.get("ids")
    if ids:
        parts.append("device=%s" % ",".join(str(i) for i in ids))
    elif count in (-1, "all", None):
        parts.append("all" if not gpu.get("capabilities") and not gpu.get("driver") else "count=all")
    else:
        parts.append("count=%s" % count)
    if gpu.get("driver") and gpu.get("driver") != "nvidia":
        parts.append("driver=%s" % gpu["driver"])
    caps = [c for c in (gpu.get("capabilities") or []) if c != "gpu"]
    if caps:
        parts.append("capabilities=%s" % ",".join(caps))
    value = ",".join(parts)
    if "," in value and not value.startswith('"'):
        value = '"%s"' % value
    return value


def _csv_field(text):
    if "," in text or '"' in text:
        return '"' + text.replace('"', '""') + '"'
    return text


def _mount_value(parts):
    out = []
    for part in parts:
        if isinstance(part, tuple):
            out.append(concat(part[0], part[1]))
        else:
            out.append(part)
    pieces = []
    for idx, part in enumerate(out):
        if idx:
            pieces.append(",")
        pieces.append(part)
    if any(isinstance(p, Raw) for p in pieces):
        return concat(*pieces)
    return "".join(pieces)


def _publish_value(port):
    target = str(port.get("target"))
    proto = port.get("protocol") or "tcp"
    published = port.get("published")
    host_ip = port.get("host_ip")
    if host_ip and ":" in host_ip:
        host_ip = "[%s]" % host_ip
    if published:
        value = "%s:%s" % (published, target)
        if host_ip:
            value = "%s:%s" % (host_ip, value)
    else:
        value = target if not host_ip else "%s::%s" % (host_ip, target)
    if proto != "tcp":
        value += "/" + proto
    return value


def _publish_note(port):
    target = port.get("target")
    published = port.get("published")
    host_ip = port.get("host_ip")
    proto = (port.get("protocol") or "tcp").upper()
    where = "ホスト (RHEL) の" if not host_ip else "ホストの %s の" % host_ip
    if published:
        return "%s %s 番ポート (%s) に届いた通信を、コンテナの %s 番ポートへ転送します。" % (where, published, proto, target)
    return "コンテナの %s 番ポート (%s) を、ホストの空いている番号のポートに公開します (番号は docker port で確認)。" % (target, proto)


def _security_note(opt):
    if opt.startswith("no-new-privileges"):
        return "コンテナの中のプログラムが、setuid などで今より強い権限を持てないようにします。"
    if opt.startswith("seccomp"):
        return "使えるシステムコール (カーネルへのお願い) を seccomp プロファイルで制限します。"
    if opt.startswith("label"):
        return "SELinux のラベル (アクセス制御の名札) の設定です。"
    if opt.startswith("apparmor"):
        return "AppArmor (Ubuntu などのアクセス制御) の設定です。RHEL では SELinux が使われます。"
    if opt.startswith("systempaths"):
        return "/proc などの一部を隠す保護を外します。"
    return "セキュリティの設定 %s です。" % opt


def _shell_join(words):
    import shlex
    return " ".join(shlex.quote(w) for w in words)


# ---------------------------------------------------------------------------
# Dockerfile の簡易解析 (説明用)
# ---------------------------------------------------------------------------
def parse_dockerfile(text):
    info = {"from": [], "stages": [], "args": [], "expose": [], "volume": [], "healthcheck": None,
            "healthcheck_opts": {}, "user": None, "entrypoint": None, "cmd": None, "secret_mounts": []}
    lines = []
    buf = ""
    escape = "\\"
    for raw in text.replace("\r\n", "\n").split("\n"):
        match = re.match(r"^\s*#\s*escape\s*=\s*(\S)", raw)
        if match and not lines and not buf:
            escape = match.group(1)
            continue
        stripped = raw.strip()
        if not buf and (stripped.startswith("#") or not stripped):
            continue
        if stripped.startswith("#"):
            continue
        if stripped.endswith(escape):
            buf += stripped[:-1] + " "
            continue
        buf += stripped
        lines.append(buf)
        buf = ""
    if buf:
        lines.append(buf)
    for line in lines:
        parts = line.split(None, 1)
        inst = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ""
        if inst == "FROM":
            words = rest.split()
            words = [w for w in words if not w.startswith("--")]
            if words:
                info["from"].append(words[0])
            if len(words) >= 3 and words[1].upper() == "AS":
                info["stages"].append(words[2])
        elif inst == "ARG":
            info["args"].append(rest.split("=", 1)[0].strip())
        elif inst == "EXPOSE":
            info["expose"].extend(rest.split())
        elif inst == "VOLUME":
            rest_s = rest.strip()
            if rest_s.startswith("["):
                try:
                    info["volume"].extend(json.loads(rest_s))
                except ValueError:
                    info["volume"].append(rest_s)
            else:
                info["volume"].extend(rest_s.split())
        elif inst == "HEALTHCHECK":
            info["healthcheck"] = rest
            opts = {}
            for match in re.finditer(r"--(interval|timeout|start-period|start-interval|retries)=(\S+)", rest):
                key = match.group(1).replace("-", "_")
                opts[key] = int(match.group(2)) if key == "retries" else match.group(2)
            info["healthcheck_opts"] = opts if not rest.strip().upper().startswith("NONE") else {}
        elif inst == "USER":
            info["user"] = rest
        elif inst == "ENTRYPOINT":
            info["entrypoint"] = rest
        elif inst == "CMD":
            info["cmd"] = rest
        elif inst == "RUN":
            for match in re.finditer(r"--mount=([^\s]+)", rest):
                spec = match.group(1)
                if "type=secret" in spec:
                    sid = re.search(r"(?:id|target)=([^,\s]+)", spec)
                    if sid:
                        info["secret_mounts"].append(sid.group(1))
    return info


def build_plan(project, options):
    return _Planner(project, options).build()
