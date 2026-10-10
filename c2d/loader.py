"""compose ファイルを読み込み、docker compose config と同じ形の「正規化モデル」を作る。

2 つの読み込み方法があります。

compose ローダー (推奨)
    ``docker compose config --format json`` を実行し、compose 自身が解釈した結果を使う。
    実際の docker compose と 100% 同じ解釈になる (RHEL 上で docker compose が使えるとき)。

内蔵ローダー
    docker compose が無い環境 (Windows で設計だけ確認したい場合など) 向けに、
    compose-go と同じ規則を Python で再実装したもの。

どちらも同じ形の dict (以下「モデル」) を返し、後段の変換処理はモデルだけを見ます。
"""

import copy
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess

from . import envfile, yamlmini
from .units import UnitError, go_duration, go_str, ram_in_bytes
from .yamlmini import Tagged

__all__ = ["LoadOptions", "LoadError", "load_project"]

DEFAULT_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
OVERRIDE_FILES = (
    "compose.override.yaml",
    "compose.override.yml",
    "docker-compose.override.yaml",
    "docker-compose.override.yml",
)


class LoadError(Exception):
    pass


class LoadOptions:
    def __init__(self, files=None, project_name=None, project_directory=None, env_files=None,
                 profiles=None, services=None, loader="auto", environ=None, docker="docker"):
        self.files = list(files or [])
        self.project_name = project_name
        self.project_directory = project_directory
        self.env_files = list(env_files or [])
        self.profiles = list(profiles or [])
        self.services = list(services or [])
        self.loader = loader
        self.environ = dict(os.environ if environ is None else environ)
        self.docker = docker


# ---------------------------------------------------------------------------
# 共通: ファイルの決定・プロジェクト名・環境変数
# ---------------------------------------------------------------------------
def _find_default_files(start):
    directory = os.path.abspath(start)
    while True:
        for name in DEFAULT_FILES:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                files = [path]
                for override in OVERRIDE_FILES:
                    opath = os.path.join(directory, override)
                    if os.path.isfile(opath):
                        files.append(opath)
                        break
                return files
        parent = os.path.dirname(directory)
        if parent == directory:
            return []
        directory = parent


def resolve_files(opts):
    files = []
    for item in opts.files:
        path = os.path.abspath(item)
        if os.path.isdir(path):
            found = _find_default_files(path)
            if not found:
                raise LoadError("フォルダ %s に compose ファイルが見つかりません" % path)
            files.extend(found)
        else:
            if not os.path.isfile(path):
                raise LoadError("compose ファイル %s が見つかりません" % path)
            files.append(path)
    if not files:
        compose_file = opts.environ.get("COMPOSE_FILE")
        if compose_file:
            sep = opts.environ.get("COMPOSE_PATH_SEPARATOR", os.pathsep)
            files = [os.path.abspath(p) for p in compose_file.split(sep) if p]
        else:
            files = _find_default_files(os.getcwd())
    if not files:
        raise LoadError("compose ファイルが見つかりません (-f で指定してください)")
    return files


def normalize_project_name(name):
    name = name.lower()
    name = re.sub(r"[^a-z0-9_-]", "", name)
    name = name.lstrip("_-")
    return name


def build_environment(project_dir, opts):
    """補間に使う環境変数 (OS 環境変数 > .env) を作る。"""
    os_env = opts.environ
    dotenv = {}
    files = [os.path.join(project_dir, p) if not os.path.isabs(p) else p for p in opts.env_files]
    if not files:
        default = os.path.join(project_dir, ".env")
        if os.path.isfile(default):
            files = [default]
    used = []
    for path in files:
        if not os.path.isfile(path):
            raise LoadError("--env-file に指定したファイル %s が見つかりません" % path)
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()

        def lookup(name, _d=dotenv):
            if name in os_env:
                return os_env[name]
            return _d.get(name)

        try:
            for key, value in envfile.parse_dotenv(text, lookup, path):
                dotenv[key] = value
        except envfile.DotenvError as exc:
            raise LoadError(str(exc))
        used.append(path)
    merged = dict(dotenv)
    merged.update(os_env)
    return merged, dotenv, used


# ---------------------------------------------------------------------------
# compose ローダー
# ---------------------------------------------------------------------------
def docker_compose_available(docker="docker"):
    if not shutil.which(docker):
        return False
    try:
        proc = subprocess.run([docker, "compose", "version", "--short"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def compose_version(docker="docker"):
    try:
        proc = subprocess.run([docker, "compose", "version", "--short"], capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _unescape_dollars(node):
    """docker compose config の出力は $ を $$ にしているので元に戻す。"""
    if isinstance(node, str):
        return node.replace("$$", "$")
    if isinstance(node, dict):
        return {k: _unescape_dollars(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_unescape_dollars(v) for v in node]
    return node


def _run_compose_config(opts, files, extra):
    cmd = [opts.docker, "compose"]
    for path in files:
        cmd += ["-f", path]
    if opts.project_name:
        cmd += ["-p", opts.project_name]
    if opts.project_directory:
        cmd += ["--project-directory", opts.project_directory]
    for path in opts.env_files:
        cmd += ["--env-file", path]
    for profile in opts.profiles:
        cmd += ["--profile", profile]
    cmd += ["config", "--format", "json"] + extra + list(opts.services)
    env = dict(opts.environ)
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=300)
    if proc.returncode != 0:
        raise LoadError("docker compose config が失敗しました:\n%s" % (proc.stderr.strip() or proc.stdout.strip()))
    try:
        data = json.loads(proc.stdout)
    except ValueError as exc:
        raise LoadError("docker compose config の出力を読めませんでした: %s" % exc)
    warnings = [line.strip() for line in proc.stderr.splitlines() if line.strip()]
    return _unescape_dollars(data), warnings, cmd


def load_with_compose(opts, files):
    data, warnings, cmd = _run_compose_config(opts, files, [])
    try:
        split, _, _ = _run_compose_config(opts, files, ["--no-env-resolution"])
    except LoadError:
        split = None
    project = data
    project.setdefault("services", {})
    project.setdefault("networks", {})
    project.setdefault("volumes", {})
    project.setdefault("secrets", {})
    project.setdefault("configs", {})
    meta = project.setdefault("_meta", {})
    meta["loader"] = "compose"
    meta["compose_command"] = " ".join(shlex.quote(c) for c in cmd)
    meta["compose_version"] = compose_version(opts.docker)
    meta["warnings"] = ["docker compose: " + w for w in warnings]
    env_split = {}
    if split:
        for name, svc in (split.get("services") or {}).items():
            env_split[name] = {
                "environment": svc.get("environment") or {},
                "env_file": svc.get("env_file") or [],
            }
    meta["env_split"] = env_split
    return project


# ---------------------------------------------------------------------------
# 内蔵ローダー: 形の正規化 (短縮記法 → 長い記法)
# ---------------------------------------------------------------------------
def _untag(value):
    while isinstance(value, Tagged):
        value = value.value
    return value


def _list_to_dict(value, sep="=", allow_none=True, path=""):
    value = _untag(value)
    if value is None:
        return {}
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            val = _untag(val)
            if isinstance(val, (dict, list)):
                raise LoadError("%s.%s の値は文字列で指定してください" % (path, key))
            out[str(key)] = go_str(val) if val is not None else (None if allow_none else "")
        return out
    if isinstance(value, list):
        out = {}
        for item in value:
            item = go_str(_untag(item))
            if item is None:
                continue
            if sep in item:
                key, val = item.split(sep, 1)
                out[key] = val
            else:
                out[item] = None if allow_none else ""
        return out
    raise LoadError("%s はマッピングかリストで指定してください" % path)


def _str_list(value):
    value = _untag(value)
    if value is None:
        return []
    if isinstance(value, list):
        return [go_str(_untag(v)) for v in value if _untag(v) is not None]
    return [go_str(value)]


def _shape_service(name, svc):
    """短縮記法を長い記法へそろえる (マージ前に行う。パスの解決はまだしない)。"""
    if svc is None:
        svc = {}
    if not isinstance(svc, dict):
        raise LoadError("services.%s はマッピングで指定してください" % name)
    out = {}
    for key, value in svc.items():
        if isinstance(value, Tagged):
            if value.tag in ("!reset", "!override"):
                out[key] = Tagged(value.tag, _shape_field(name, key, _untag(value.value)) if value.value is not None else None)
                continue
            value = _untag(value)
        out[key] = _shape_field(name, key, value)
    return out


def _shape_field(name, key, value):
    path = "services.%s.%s" % (name, key)
    if value is None:
        return None
    if key == "build":
        if isinstance(value, str):
            return {"context": value}
        build = dict(value)
        if "args" in build:
            build["args"] = _list_to_dict(build["args"], path=path + ".args")
        if "labels" in build:
            build["labels"] = _list_to_dict(build["labels"], allow_none=False, path=path + ".labels")
        if "additional_contexts" in build:
            build["additional_contexts"] = _list_to_dict(build["additional_contexts"], path=path + ".additional_contexts")
        if "extra_hosts" in build:
            build["extra_hosts"] = _extra_hosts(build["extra_hosts"])
        for list_key in ("cache_from", "cache_to", "tags", "platforms", "no_cache_filter", "entitlements"):
            if list_key in build:
                build[list_key] = _str_list(build[list_key])
        if "secrets" in build:
            build["secrets"] = [_mount_ref(s) for s in (_untag(build["secrets"]) or [])]
        if "ssh" in build:
            ssh = _untag(build["ssh"])
            if isinstance(ssh, dict):
                build["ssh"] = ["%s=%s" % (k, v) if v is not None else str(k) for k, v in ssh.items()]
            else:
                build["ssh"] = _str_list(ssh)
        return build
    if key in ("environment",):
        return _list_to_dict(value, path=path)
    if key in ("labels", "annotations"):
        return _list_to_dict(value, allow_none=False, path=path)
    if key == "sysctls":
        return _list_to_dict(value, allow_none=False, path=path)
    if key == "extra_hosts":
        return _extra_hosts(value)
    if key in ("dns", "dns_search", "dns_opt", "tmpfs", "cap_add", "cap_drop", "security_opt", "group_add",
               "expose", "profiles", "links", "external_links", "volumes_from", "device_cgroup_rules",
               "label_file"):
        return _str_list(value)
    if key == "env_file":
        value = _untag(value)
        items = value if isinstance(value, list) else [value]
        out = []
        for item in items:
            item = _untag(item)
            if isinstance(item, dict):
                entry = {"path": go_str(item.get("path"))}
                if "required" in item:
                    entry["required"] = bool(item["required"])
                if item.get("format"):
                    entry["format"] = item["format"]
                out.append(entry)
            elif item is not None:
                out.append({"path": go_str(item)})
        return out
    if key == "networks":
        if isinstance(value, list):
            return {go_str(n): None for n in value}
        if isinstance(value, dict):
            out = {}
            for net, cfg in value.items():
                cfg = _untag(cfg)
                if cfg is not None and not isinstance(cfg, dict):
                    raise LoadError("%s.%s はマッピングで指定してください" % (path, net))
                if cfg is not None:
                    cfg = dict(cfg)
                    if "aliases" in cfg:
                        cfg["aliases"] = _str_list(cfg["aliases"])
                    if "link_local_ips" in cfg:
                        cfg["link_local_ips"] = _str_list(cfg["link_local_ips"])
                    if "driver_opts" in cfg:
                        cfg["driver_opts"] = _list_to_dict(cfg["driver_opts"], allow_none=False)
                out[str(net)] = cfg
            return out
        raise LoadError("%s はリストかマッピングで指定してください" % path)
    if key == "depends_on":
        if isinstance(value, list):
            return {go_str(n): {"condition": "service_started", "required": True} for n in value}
        out = {}
        for dep, cfg in value.items():
            cfg = dict(_untag(cfg) or {})
            out[str(dep)] = cfg
        return out
    if key == "healthcheck":
        hc = dict(value)
        test = _untag(hc.get("test"))
        if isinstance(test, str):
            hc["test"] = ["CMD-SHELL", test]
        elif isinstance(test, list):
            hc["test"] = [go_str(_untag(t)) for t in test]
        return hc
    if key in ("secrets", "configs"):
        return [_mount_ref(s) for s in (value or [])]
    if key == "ulimits":
        out = {}
        for lim, val in value.items():
            val = _untag(val)
            if isinstance(val, dict):
                out[lim] = {"soft": int(val.get("soft")), "hard": int(val.get("hard"))}
            else:
                out[lim] = int(val)
        return out
    if key in ("command", "entrypoint"):
        if isinstance(value, list):
            return [go_str(_untag(v)) if _untag(v) is not None else "" for v in value]
        return go_str(value)
    if key in ("pre_start", "post_start", "pre_stop"):
        hooks = []
        for hook in value or []:
            hook = dict(_untag(hook))
            if "command" in hook:
                cmd = _untag(hook["command"])
                hook["command"] = [go_str(_untag(v)) for v in cmd] if isinstance(cmd, list) else go_str(cmd)
            if "environment" in hook:
                hook["environment"] = _list_to_dict(hook["environment"])
            hooks.append(hook)
        return hooks
    return value


def _extra_hosts(value):
    value = _untag(value)
    out = []
    if isinstance(value, dict):
        for host, ip in value.items():
            ip = _untag(ip)
            if isinstance(ip, list):
                for one in ip:
                    out.append("%s=%s" % (host, go_str(one)))
            else:
                out.append("%s=%s" % (host, go_str(ip)))
        return out
    for item in value or []:
        item = go_str(_untag(item))
        if "=" in item:
            host, ip = item.split("=", 1)
        elif ":" in item:
            host, ip = item.split(":", 1)
        else:
            raise LoadError("extra_hosts の %r は「ホスト名=IP」の形で指定してください" % item)
        out.append("%s=%s" % (host, ip))
    return out


def _mount_ref(value):
    value = _untag(value)
    if isinstance(value, str):
        return {"source": value}
    ref = dict(value)
    for key in ("uid", "gid"):
        if key in ref and ref[key] is not None:
            ref[key] = go_str(ref[key])
    if "mode" in ref and ref["mode"] is not None:
        mode = ref["mode"]
        if isinstance(mode, yamlmini.YInt):
            ref["mode"] = int(mode)
        elif isinstance(mode, str):
            ref["mode"] = int(mode, 8)
    return ref


# ---------------------------------------------------------------------------
# 内蔵ローダー: マージ (複数ファイル / extends)
# ---------------------------------------------------------------------------
def _merge_dict(base, over):
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, Tagged):
            if value.tag == "!reset":
                out.pop(key, None)
                continue
            if value.tag == "!override":
                out[key] = copy.deepcopy(_untag(value.value))
                continue
            value = _untag(value)
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _merge_dict(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _volume_target(item):
    item = _untag(item)
    if isinstance(item, dict):
        return item.get("target")
    parsed = parse_volume_short(go_str(item))
    return parsed.get("target")


def _merge_unique(base, over, keyfunc):
    out = list(base)
    index = {}
    for pos, item in enumerate(out):
        index[keyfunc(item)] = pos
    for item in over:
        key = keyfunc(item)
        if key in index:
            out[index[key]] = copy.deepcopy(item)
        else:
            index[key] = len(out)
            out.append(copy.deepcopy(item))
    return out


def _port_key(item):
    item = _untag(item)
    if isinstance(item, dict):
        return ("long", str(item.get("host_ip")), str(item.get("published")), str(item.get("target")), str(item.get("protocol") or "tcp"))
    return ("short", go_str(item))


def merge_service(base, over):
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, Tagged):
            if value.tag == "!reset":
                out.pop(key, None)
                continue
            if value.tag == "!override":
                out[key] = copy.deepcopy(value.value)
                continue
            value = _untag(value)
        if key not in out or out[key] is None or value is None:
            out[key] = copy.deepcopy(value)
            continue
        current = out[key]
        if key in ("command", "entrypoint", "extends"):
            out[key] = copy.deepcopy(value)
        elif key in ("environment", "labels", "annotations", "sysctls", "networks", "depends_on", "ulimits"):
            merged = dict(current)
            for sub, subval in value.items():
                if isinstance(subval, Tagged):
                    if subval.tag == "!reset":
                        merged.pop(sub, None)
                        continue
                    subval = _untag(subval)
                if key in ("networks", "depends_on") and isinstance(merged.get(sub), dict) and isinstance(subval, dict):
                    merged[sub] = _merge_dict(merged[sub], subval)
                else:
                    merged[sub] = copy.deepcopy(subval)
            out[key] = merged
        elif key == "healthcheck":
            merged = _merge_dict(current, {k: v for k, v in value.items() if k != "test"})
            if "test" in value:
                merged["test"] = copy.deepcopy(value["test"])
            out[key] = merged
        elif key == "logging":
            if value.get("driver") and current.get("driver") and value.get("driver") != current.get("driver"):
                out[key] = copy.deepcopy(value)
            else:
                out[key] = _merge_dict(current, value)
        elif key == "build":
            merged = dict(current)
            for sub, subval in value.items():
                if sub in ("args", "labels", "additional_contexts") and isinstance(merged.get(sub), dict):
                    merged[sub] = _merge_dict(merged[sub], subval)
                elif sub in ("cache_from", "cache_to", "tags", "platforms", "ssh", "extra_hosts") and isinstance(merged.get(sub), list):
                    merged[sub] = _merge_unique(merged[sub], subval, lambda x: x)
                elif sub == "secrets" and isinstance(merged.get(sub), list):
                    merged[sub] = _merge_unique(merged[sub], subval, lambda x: x.get("target") or x.get("source"))
                else:
                    merged[sub] = copy.deepcopy(subval)
            out[key] = merged
        elif key == "volumes":
            out[key] = _merge_unique(current, value, _volume_target)
        elif key == "ports":
            out[key] = _merge_unique(current, value, _port_key)
        elif key in ("secrets", "configs"):
            out[key] = _merge_unique(current, value, lambda x: x.get("target") or x.get("source"))
        elif key == "devices":
            out[key] = _merge_unique(current, value, lambda x: go_str(x) if not isinstance(x, dict) else x.get("target"))
        elif key in ("env_file",):
            out[key] = _merge_unique(current, value, lambda x: x.get("path"))
        elif isinstance(current, dict) and isinstance(value, dict):
            out[key] = _merge_dict(current, value)
        elif isinstance(current, list) and isinstance(value, list):
            out[key] = _merge_unique(current, value, lambda x: json.dumps(x, sort_keys=True, default=str))
        else:
            out[key] = copy.deepcopy(value)
    return out


def merge_models(base, over):
    out = dict(base)
    for key, value in over.items():
        if key == "services":
            services = dict(out.get("services") or {})
            for name, svc in (value or {}).items():
                if isinstance(svc, Tagged) and svc.tag == "!reset":
                    services.pop(name, None)
                    continue
                if name in services:
                    services[name] = merge_service(services[name], svc)
                else:
                    services[name] = svc
            out["services"] = services
        elif key in ("networks", "volumes", "secrets", "configs", "models"):
            merged = dict(out.get(key) or {})
            for name, cfg in (value or {}).items():
                cfg = _untag(cfg)
                if name in merged and isinstance(merged[name], dict) and isinstance(cfg, dict):
                    merged[name] = _merge_dict(merged[name], cfg)
                else:
                    merged[name] = copy.deepcopy(cfg)
            out[key] = merged
        elif isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _merge_dict(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


# ---------------------------------------------------------------------------
# 内蔵ローダー: パスの解決
# ---------------------------------------------------------------------------
def _is_remote_context(value):
    low = value.lower()
    return (low.startswith(("http://", "https://", "git://", "git@", "ssh://", "github.com/"))
            or low.endswith(".git") or "://" in low)


def _abs(base_dir, path, home=None):
    if path is None:
        return None
    if path.startswith("~"):
        home = home or os.path.expanduser("~")
        path = home + path[1:]
    if os.path.isabs(path) or path.startswith("/"):
        return os.path.normpath(path) if not path.startswith("/") else posixpath.normpath(path)
    joined = os.path.join(base_dir, path)
    return os.path.normpath(joined)


def parse_volume_short(spec):
    """compose-go format.ParseVolume 互換: ``[SOURCE:]TARGET[:MODE]`` を辞書にする。"""
    volume = {}
    if len(spec) in (0,):
        raise LoadError("volumes に空の指定があります")
    if len(spec) <= 2:
        return {"type": "volume", "target": spec, "volume": {}}
    buffer = ""
    fields = []

    def is_drive(buf, ch):
        return ch == ":" and len(buf) == 1 and buf.isalpha()

    for ch in spec:
        if is_drive(buffer, ch):
            buffer += ch
        elif ch == ":":
            fields.append(buffer)
            buffer = ""
        else:
            buffer += ch
    fields.append(buffer)
    if any(f == "" for f in fields):
        raise LoadError("volumes の指定 %r の : の間が空です" % spec)
    if len(fields) == 1:
        volume["target"] = fields[0]
    else:
        volume["source"] = fields[0]
        volume["target"] = fields[1]
        if len(fields) > 3:
            raise LoadError("volumes の指定 %r に : が多すぎます" % spec)
        if len(fields) == 3:
            for option in fields[2].split(","):
                if option == "ro":
                    volume["read_only"] = True
                elif option == "rw":
                    volume["read_only"] = False
                elif option == "nocopy":
                    volume.setdefault("volume", {})["nocopy"] = True
                elif option in ("rprivate", "private", "rshared", "shared", "rslave", "slave"):
                    volume.setdefault("bind", {})["propagation"] = option
                elif option in ("z", "Z"):
                    volume.setdefault("bind", {})["selinux"] = option
    source = volume.get("source")
    if source and (source[0] in "./~" or source.startswith("\\\\") or (len(source) > 1 and source[1] == ":" and source[0].isalpha())):
        volume["type"] = "bind"
        # 短い書き方のバインドは create_host_path: true 扱い (compose の出力では省略される既定値)
        volume.setdefault("bind", {})
        volume.pop("volume", None) if not volume.get("volume") else None
    else:
        volume["type"] = "volume"
        volume.setdefault("volume", {})
        volume.pop("bind", None)
    return volume


# ---------------------------------------------------------------------------
# 内蔵ローダー: 意味の正規化 (docker compose config と同じ形にする)
# ---------------------------------------------------------------------------
_PORT_RANGE = re.compile(r"^(\d+)(?:-(\d+))?$")


def _port_range(text, what):
    match = _PORT_RANGE.match(text)
    if not match:
        raise LoadError("ports の %s %r を解釈できません" % (what, text))
    start = int(match.group(1))
    end = int(match.group(2) or start)
    return start, end


def parse_port_short(spec):
    """docker/go-connections nat.ParsePortSpec 互換。"""
    raw = str(spec)
    proto = "tcp"
    parts = raw.split(":")
    count = len(parts)
    container = parts[-1]
    if count == 1:
        ip, host = "", ""
    elif count == 2:
        ip, host = "", parts[0]
    elif count == 3:
        ip, host = parts[0], parts[1]
    else:
        ip, host = ":".join(parts[:-2]), parts[-2]
    if "/" in container:
        container, proto = container.split("/", 1)
    if ip.startswith("[") and ip.endswith("]"):
        ip = ip[1:-1]
    if not container:
        raise LoadError("ports %r にコンテナ側のポートがありません" % raw)
    start, end = _port_range(container, "コンテナ側ポート")
    hstart = hend = 0
    if host:
        hstart, hend = _port_range(host, "ホスト側ポート")
        if (end - start) != (hend - hstart) and end != start:
            raise LoadError("ports %r のポート範囲の数が合いません" % raw)
    out = []
    for idx in range(end - start + 1):
        entry = {"mode": "ingress", "target": start + idx, "protocol": proto.lower()}
        if ip:
            entry["host_ip"] = ip
        if host:
            published = str(hstart + idx)
            if start == end and hstart != hend:
                published = "%d-%d" % (hstart, hend)
            entry["published"] = published
        out.append(entry)
    return out


def _normalize_ports(ports):
    out = []
    for item in ports or []:
        item = _untag(item)
        if isinstance(item, dict):
            entry = {"mode": item.get("mode") or "ingress"}
            if item.get("name"):
                entry["name"] = item["name"]
            if item.get("host_ip"):
                entry["host_ip"] = str(item["host_ip"])
            entry["target"] = int(item.get("target"))
            if item.get("published") not in (None, ""):
                entry["published"] = go_str(item.get("published"))
            entry["protocol"] = (item.get("protocol") or "tcp").lower()
            if item.get("app_protocol"):
                entry["app_protocol"] = item["app_protocol"]
            out.append(entry)
        else:
            out.extend(parse_port_short(go_str(item)))
    return out


def _normalize_volumes(volumes, base_dir, home):
    out = []
    for item in volumes or []:
        item = _untag(item)
        if isinstance(item, dict):
            vol = copy.deepcopy(item)
            vol.setdefault("type", "volume")
            if vol.get("type") == "bind" and vol.get("source"):
                vol["source"] = _abs(base_dir, vol["source"], home)
            if "read_only" in vol:
                vol["read_only"] = bool(vol["read_only"])
            if vol.get("tmpfs"):
                tmpfs = dict(vol["tmpfs"])
                if "size" in tmpfs and tmpfs["size"] is not None:
                    tmpfs["size"] = ram_in_bytes(tmpfs["size"])
                if "mode" in tmpfs and tmpfs["mode"] is not None:
                    mode = tmpfs["mode"]
                    tmpfs["mode"] = int(mode, 8) if isinstance(mode, str) else int(mode)
                vol["tmpfs"] = tmpfs
            out.append(vol)
        else:
            vol = parse_volume_short(go_str(item))
            if vol.get("type") == "bind":
                vol["source"] = _abs(base_dir, vol["source"], home)
            out.append(vol)
    return out


def _normalize_devices(devices):
    out = []
    for item in devices or []:
        item = _untag(item)
        if isinstance(item, dict):
            out.append({k: go_str(v) for k, v in item.items() if v is not None})
            continue
        text = go_str(item)
        if re.match(r"^[a-zA-Z0-9.\-]+/[a-zA-Z0-9.\-]+=[a-zA-Z0-9_.:\-*]+$", text):
            out.append({"source": text, "target": text})
            continue
        parts = text.split(":")
        if len(parts) == 1:
            out.append({"source": parts[0], "target": parts[0], "permissions": "rwm"})
        elif len(parts) == 2:
            if re.match(r"^[rwm]+$", parts[1]):
                out.append({"source": parts[0], "target": parts[0], "permissions": parts[1]})
            else:
                out.append({"source": parts[0], "target": parts[1], "permissions": "rwm"})
        else:
            out.append({"source": parts[0], "target": parts[1], "permissions": parts[2]})
    return out


def _normalize_gpus(value):
    value = _untag(value)
    if value is None:
        return None
    if value == "all":
        return [{"count": -1}]
    out = []
    for item in value:
        item = dict(_untag(item))
        if item.get("count") == "all":
            item["count"] = -1
        out.append(item)
    return out


def _normalize_deploy(deploy):
    deploy = copy.deepcopy(_untag(deploy) or {})
    resources = deploy.get("resources")
    if resources:
        for part in ("limits", "reservations"):
            res = resources.get(part)
            if not res:
                continue
            if res.get("cpus") is not None:
                res["cpus"] = float(res["cpus"])
            if res.get("memory") is not None:
                res["memory"] = ram_in_bytes(res["memory"])
            if res.get("pids") is not None:
                res["pids"] = int(res["pids"])
            if res.get("devices"):
                devs = []
                for dev in res["devices"]:
                    dev = dict(dev)
                    if dev.get("count") == "all":
                        dev["count"] = -1
                    devs.append(dev)
                res["devices"] = devs
    if deploy.get("replicas") is not None:
        deploy["replicas"] = int(deploy["replicas"])
    return deploy


def _load_env_file(entry, base_dir, lookup):
    path = _abs(base_dir, entry["path"])
    if not os.path.isfile(path):
        if entry.get("required", True):
            raise LoadError("env_file %s が見つかりません" % path)
        return path, None, None
    with open(path, encoding="utf-8-sig") as handle:
        text = handle.read()
    if entry.get("format") == "raw":
        pairs = envfile.parse_dotenv_raw(text)
    else:
        try:
            pairs = envfile.parse_dotenv(text, lookup, path)
        except (envfile.DotenvError, envfile.InterpolationError) as exc:
            raise LoadError(str(exc))
    return path, pairs, text


def normalize_service(name, svc, ctx):
    """1 サービス分を docker compose config と同じ形にする。"""
    base_dir = ctx["project_dir"]
    home = ctx["home"]
    lookup = ctx["lookup"]
    out = {}
    for key, value in svc.items():
        value = _untag(value)
        if value is None and key not in ("environment",):
            continue
        out[key] = value

    if "build" in out:
        build = dict(out["build"])
        context = build.get("context") or "."
        if not _is_remote_context(context):
            build["context"] = _abs(base_dir, context, home)
        if not build.get("dockerfile_inline"):
            build["dockerfile"] = build.get("dockerfile") or "Dockerfile"
        if build.get("additional_contexts"):
            ctxs = {}
            for cname, cval in build["additional_contexts"].items():
                if cval and not re.match(r"^[a-z0-9-]+://|^docker-image://|^target:|^service:", cval) and not _is_remote_context(cval):
                    cval = _abs(base_dir, cval, home)
                ctxs[cname] = cval
            build["additional_contexts"] = ctxs
        if build.get("shm_size") is not None:
            build["shm_size"] = ram_in_bytes(build["shm_size"])
        for flag in ("no_cache", "pull", "privileged"):
            if flag in build:
                build[flag] = bool(build[flag])
        if build.get("target") in ("", None):
            build.pop("target", None)
        args = build.get("args") or {}
        resolved = {}
        for arg, val in args.items():
            if val is None:
                val = lookup(arg)
                if val is None:
                    continue
            resolved[arg] = val
        if resolved or "args" in build:
            build["args"] = resolved
        out["build"] = build

    for key in ("command", "entrypoint"):
        if key in out and isinstance(out[key], str):
            try:
                out[key] = shlex.split(out[key])
            except ValueError as exc:
                raise LoadError("services.%s.%s を分解できません: %s" % (name, key, exc))

    # 環境変数 (env_file → environment の順に上書き)
    env = {}
    env_files_resolved = []
    for entry in out.pop("env_file", []) or []:
        path, pairs, text = _load_env_file(entry, base_dir, lookup)
        record = {"path": path}
        if entry.get("format"):
            record["format"] = entry["format"]
        if "required" in entry:
            record["required"] = entry["required"]
        env_files_resolved.append(record)
        if pairs is None:
            continue
        for key, val in pairs:
            env[key] = val
    explicit = out.pop("environment", None) or {}
    explicit_resolved = {}
    for key, val in explicit.items():
        if val is None:
            val = lookup(key)
        explicit_resolved[key] = val
        env[key] = val
    if env or explicit:
        out["environment"] = env
    ctx["env_split"][name] = {"environment": explicit_resolved, "env_file": env_files_resolved}

    # ラベル (label_file → labels)
    label_files = out.pop("label_file", None)
    if label_files:
        labels = {}
        resolved_files = []
        for path in label_files:
            apath = _abs(base_dir, path, home)
            resolved_files.append(apath)
            with open(apath, encoding="utf-8-sig") as handle:
                for key, val in envfile.parse_dotenv(handle.read(), None, apath):
                    labels[key] = val
        labels.update(out.get("labels") or {})
        out["labels"] = labels
        out["label_file"] = resolved_files

    if "ports" in out:
        out["ports"] = _normalize_ports(out["ports"])
    if "volumes" in out:
        out["volumes"] = _normalize_volumes(out["volumes"], base_dir, home)
    if "devices" in out:
        out["devices"] = _normalize_devices(out["devices"])
    if "gpus" in out:
        out["gpus"] = _normalize_gpus(out["gpus"])
    if "deploy" in out:
        out["deploy"] = _normalize_deploy(out["deploy"])
    for key in ("mem_limit", "mem_reservation", "memswap_limit", "shm_size"):
        if out.get(key) is not None:
            out[key] = ram_in_bytes(out[key])
    for key in ("cpus", "cpu_percent"):
        if out.get(key) is not None:
            out[key] = float(out[key])
    for key in ("cpu_shares", "cpu_period", "cpu_quota", "cpu_count", "pids_limit", "mem_swappiness", "oom_score_adj", "scale"):
        if out.get(key) is not None:
            out[key] = int(out[key])
    for key in ("user", "working_dir", "hostname", "domainname", "container_name", "image", "restart",
                "stop_signal", "network_mode", "ipc", "pid", "uts", "userns_mode", "cgroup", "cgroup_parent",
                "runtime", "isolation", "platform", "pull_policy", "mac_address", "cpuset"):
        if out.get(key) is not None:
            out[key] = go_str(out[key])
    if "healthcheck" in out:
        hc = dict(out["healthcheck"])
        if hc.get("retries") is not None:
            hc["retries"] = int(hc["retries"])
        for dkey in ("interval", "timeout", "start_period", "start_interval"):
            if hc.get(dkey) is not None:
                hc[dkey] = go_str(hc[dkey])
        out["healthcheck"] = hc
    if "stop_grace_period" in out:
        out["stop_grace_period"] = go_str(out["stop_grace_period"])
    if "networks" in out and out["networks"] is not None:
        nets = {}
        for net, cfg in out["networks"].items():
            nets[net] = cfg
        out["networks"] = nets
    if "depends_on" in out:
        deps = {}
        for dep, cfg in out["depends_on"].items():
            cfg = dict(cfg or {})
            cfg.setdefault("condition", "service_started")
            cfg.setdefault("required", True)
            deps[dep] = cfg
        out["depends_on"] = deps
    for link in out.get("links") or []:
        dep = link.split(":", 1)[0]
        deps = out.setdefault("depends_on", {})
        if dep not in deps:
            deps[dep] = {"condition": "service_started", "restart": True, "required": True}
    if "secrets" in out:
        secs = []
        for ref in out["secrets"]:
            ref = dict(ref)
            target = ref.get("target")
            if not target:
                ref["target"] = "/run/secrets/" + ref["source"]
            secs.append(ref)
        out["secrets"] = secs
    for flag in ("init", "tty", "stdin_open", "privileged", "read_only", "oom_kill_disable", "use_api_socket"):
        if flag in out and out[flag] is not None:
            out[flag] = bool(out[flag])
    for hook_key in ("pre_start", "post_start", "pre_stop"):
        hooks = out.get(hook_key)
        if hooks:
            norm = []
            for hook in hooks:
                hook = dict(hook)
                cmd = hook.get("command")
                if isinstance(cmd, str):
                    hook["command"] = shlex.split(cmd)
                if hook_key == "pre_start" and not hook.get("image") and out.get("image"):
                    hook["image"] = out.get("image")
                norm.append(hook)
            out[hook_key] = norm
    if out.get("extends") is not None:
        out.pop("extends", None)
    out.pop("profiles", None) if not out.get("profiles") else None
    return out


def _normalize_networks(project, used, project_name):
    out = {}
    declared = project.get("networks") or {}
    for key in used:
        cfg = _untag(declared.get(key))
        cfg = dict(cfg or {})
        external = _untag(cfg.get("external"))
        if isinstance(external, dict):
            if external.get("name"):
                cfg["name"] = external["name"]
            external = True
        if external:
            cfg["external"] = True
            cfg.setdefault("name", key)
        else:
            cfg.pop("external", None)
            cfg.setdefault("name", "%s_%s" % (project_name, key))
        if "labels" in cfg:
            cfg["labels"] = _list_to_dict(cfg["labels"], allow_none=False)
        if "driver_opts" in cfg:
            cfg["driver_opts"] = {k: go_str(v) for k, v in (cfg["driver_opts"] or {}).items()}
        ipam = cfg.get("ipam")
        if ipam:
            ipam = dict(ipam)
            if "options" in ipam:
                ipam["options"] = {k: go_str(v) for k, v in (ipam["options"] or {}).items()}
            cfg["ipam"] = ipam
        else:
            cfg["ipam"] = {}
        for flag in ("internal", "attachable", "enable_ipv4", "enable_ipv6"):
            if flag in cfg and cfg[flag] is not None:
                cfg[flag] = bool(cfg[flag])
        out[key] = cfg
    return out


def _normalize_volumes_top(project, used, project_name):
    out = {}
    declared = project.get("volumes") or {}
    for key in used:
        cfg = dict(_untag(declared.get(key)) or {})
        external = _untag(cfg.get("external"))
        if isinstance(external, dict):
            if external.get("name"):
                cfg["name"] = external["name"]
            external = True
        if external:
            cfg["external"] = True
            cfg.setdefault("name", key)
        else:
            cfg.pop("external", None)
            cfg.setdefault("name", "%s_%s" % (project_name, key))
        if "labels" in cfg:
            cfg["labels"] = _list_to_dict(cfg["labels"], allow_none=False)
        if "driver_opts" in cfg:
            cfg["driver_opts"] = {k: go_str(v) for k, v in (cfg["driver_opts"] or {}).items()}
        out[key] = cfg
    return out


def _normalize_secret_like(project, kind, project_name, base_dir, home, lookup):
    out = {}
    for key, cfg in (project.get(kind) or {}).items():
        cfg = dict(_untag(cfg) or {})
        if cfg.get("external"):
            cfg.setdefault("name", key)
        else:
            cfg.setdefault("name", "%s_%s" % (project_name, key))
        if cfg.get("file"):
            cfg["file"] = _abs(base_dir, cfg["file"], home)
        out[key] = cfg
    return out


def _load_yaml_model(path, lookup, unset, warnings):
    try:
        raw = yamlmini.load_file(path)
    except yamlmini.YamlError as exc:
        raise LoadError("YAML の書き方に誤りがあります: %s" % exc)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise LoadError("%s の一番上はマッピング (キー: 値) にしてください" % path)
    if "version" in raw:
        warnings.append("%s: version は古い書き方のため無視されます (compose v2 以降は不要)" % os.path.basename(path))
    try:
        data = envfile.interpolate_tree(raw, lookup, unset)
    except envfile.InterpolationError as exc:
        raise LoadError(str(exc))
    services = {}
    for name, svc in (data.get("services") or {}).items():
        if isinstance(svc, Tagged):
            services[name] = svc
            continue
        services[name] = _shape_service(name, svc)
    data["services"] = services
    return data


def _resolve_extends(services, file_dir, lookup, unset, warnings, home, stack=()):
    resolved = {}

    def resolve(name, svc, pool, current_dir, chain):
        ext = _untag(svc.get("extends")) if isinstance(svc, dict) else None
        if not ext:
            return svc
        if isinstance(ext, str):
            ext = {"service": ext}
        target = ext.get("service")
        if (current_dir, target, name) in chain:
            raise LoadError("extends が循環しています: %s" % target)
        if ext.get("file"):
            path = _abs(current_dir, ext["file"], home)
            other = _load_yaml_model(path, lookup, unset, warnings)
            other_services = other.get("services") or {}
            if target not in other_services:
                raise LoadError("extends: %s に service %s がありません" % (path, target))
            base = resolve(target, other_services[target], other_services, os.path.dirname(path), chain + ((current_dir, target, name),))
            base = _absolutize_paths(base, os.path.dirname(path), home)
        else:
            if target not in pool:
                raise LoadError("extends: service %s が見つかりません" % target)
            base = resolve(target, pool[target], pool, current_dir, chain + ((current_dir, target, name),))
        child = {k: v for k, v in svc.items() if k != "extends"}
        return merge_service(base, child)

    for name, svc in services.items():
        resolved[name] = resolve(name, svc, services, file_dir, stack)
    return resolved


def _absolutize_paths(svc, base_dir, home):
    """別ファイルから extends したサービスの相対パスを、そのファイル基準の絶対パスにする。"""
    svc = copy.deepcopy(svc)
    build = svc.get("build")
    if isinstance(build, dict) and build.get("context") and not _is_remote_context(build["context"]):
        build["context"] = _abs(base_dir, build["context"], home)
    vols = []
    for item in svc.get("volumes") or []:
        item = _untag(item)
        if isinstance(item, dict):
            if item.get("type") == "bind" and item.get("source"):
                item = dict(item)
                item["source"] = _abs(base_dir, item["source"], home)
            vols.append(item)
        else:
            vol = parse_volume_short(go_str(item))
            if vol.get("type") == "bind":
                vol["source"] = _abs(base_dir, vol["source"], home)
            vols.append(vol)
    if "volumes" in svc:
        svc["volumes"] = vols
    if svc.get("env_file"):
        svc["env_file"] = [dict(e, path=_abs(base_dir, e["path"], home)) for e in svc["env_file"]]
    if svc.get("label_file"):
        svc["label_file"] = [_abs(base_dir, p, home) for p in svc["label_file"]]
    return svc


def load_builtin(opts, files):
    warnings = []
    project_dir = os.path.abspath(opts.project_directory or os.path.dirname(files[0]))
    environment, dotenv, dotenv_used = build_environment(project_dir, opts)

    def lookup(name):
        return environment.get(name)

    unset = set()
    home = os.path.expanduser("~")
    model = {}
    for path in files:
        data = _load_yaml_model(path, lookup, unset, warnings)
        includes = data.pop("include", None)
        for inc in includes or []:
            inc = _untag(inc)
            if isinstance(inc, str):
                inc = {"path": inc}
            inc_paths = inc.get("path")
            inc_paths = inc_paths if isinstance(inc_paths, list) else [inc_paths]
            inc_files = [_abs(os.path.dirname(path), p, home) for p in inc_paths]
            inc_dir = _abs(os.path.dirname(path), inc.get("project_directory"), home) if inc.get("project_directory") else os.path.dirname(inc_files[0])
            inc_opts = LoadOptions(files=inc_files, project_name=opts.project_name or "x", project_directory=inc_dir,
                                   env_files=[_abs(os.path.dirname(path), e, home) for e in _str_list(inc.get("env_file"))],
                                   environ=opts.environ, loader="builtin")
            sub = _load_raw_merged(inc_opts, inc_files, warnings)
            for kind in ("services", "networks", "volumes", "secrets", "configs"):
                for key, val in (sub.get(kind) or {}).items():
                    if key in (model.get(kind) or {}) or key in (data.get(kind) or {}):
                        raise LoadError("include したファイルの %s.%s が重複しています" % (kind, key))
                    data.setdefault(kind, {})[key] = val
        data["services"] = _resolve_extends(data.get("services") or {}, os.path.dirname(path), lookup, unset, warnings, home)
        model = merge_models(model, data)

    # プロジェクト名
    name = opts.project_name or opts.environ.get("COMPOSE_PROJECT_NAME") or dotenv.get("COMPOSE_PROJECT_NAME") or model.get("name")
    if not name:
        name = os.path.basename(project_dir.rstrip("/\\"))
    project_name = normalize_project_name(str(name))
    if not project_name:
        raise LoadError("プロジェクト名 %r が使えません (-p で英小文字・数字の名前を指定してください)" % name)

    # profiles と対象サービス
    profiles = set(opts.profiles)
    if not profiles:
        env_profiles = opts.environ.get("COMPOSE_PROFILES") or dotenv.get("COMPOSE_PROFILES") or ""
        profiles = {p.strip() for p in env_profiles.split(",") if p.strip()}
    all_services = {k: _untag(v) or {} for k, v in (model.get("services") or {}).items()}
    service_order = list(all_services)

    def enabled(svc):
        svc_profiles = svc.get("profiles") or []
        return not svc_profiles or "*" in profiles or bool(set(svc_profiles) & profiles)

    selected = [n for n in service_order if enabled(all_services[n])]
    disabled = {n: all_services[n].get("profiles") for n in service_order if n not in selected}
    if opts.services:
        missing = [s for s in opts.services if s not in all_services]
        if missing:
            raise LoadError("サービス %s は compose ファイルにありません" % ", ".join(missing))
        wanted = []
        queue = list(opts.services)
        while queue:
            svc_name = queue.pop(0)
            if svc_name in wanted:
                continue
            wanted.append(svc_name)
            svc = all_services[svc_name]
            for dep, cfg in (svc.get("depends_on") or {}).items():
                if cfg.get("required", True) is False and dep not in selected:
                    continue
                queue.append(dep)
            for link in svc.get("links") or []:
                queue.append(link.split(":", 1)[0])
            nm = svc.get("network_mode") or ""
            if nm.startswith("service:"):
                queue.append(nm.split(":", 1)[1])
            for vf in svc.get("volumes_from") or []:
                if not vf.startswith("container:"):
                    queue.append(vf.split(":", 1)[0])
        selected = [n for n in service_order if n in wanted]
        disabled = {n: all_services[n].get("profiles") for n in service_order if n not in selected}

    ctx = {"project_dir": project_dir, "home": home, "lookup": lookup, "env_split": {}}
    services = {}
    for svc_name in selected:
        svc = all_services[svc_name]
        deps = svc.get("depends_on") or {}
        for dep, cfg in list(deps.items()):
            if dep not in selected:
                if cfg.get("required", True) is False:
                    deps.pop(dep)
                    warnings.append("services.%s: depends_on の %s は無効 (profiles など) のため無視します (required: false)" % (svc_name, dep))
                else:
                    raise LoadError("services.%s は %s に依存していますが、%s は有効になっていません (profiles を確認してください)" % (svc_name, dep, dep))
        services[svc_name] = normalize_service(svc_name, svc, ctx)

    # 既定ネットワーク
    used_networks = []
    for svc_name, svc in services.items():
        if svc.get("network_mode"):
            continue
        if not svc.get("networks"):
            svc["networks"] = {"default": None}
        for net in svc["networks"]:
            if net not in used_networks:
                used_networks.append(net)
    declared_nets = list((model.get("networks") or {}).keys())
    ordered_nets = [n for n in (["default"] + declared_nets) if n in used_networks]
    ordered_nets += [n for n in used_networks if n not in ordered_nets]
    for net in ordered_nets:
        if net != "default" and net not in (model.get("networks") or {}):
            raise LoadError("network %s が networks: に定義されていません" % net)

    used_volumes = []
    for svc in services.values():
        for vol in svc.get("volumes") or []:
            if vol.get("type") == "volume" and vol.get("source"):
                if vol["source"] not in (model.get("volumes") or {}):
                    raise LoadError("volume %s が volumes: に定義されていません" % vol["source"])
                if vol["source"] not in used_volumes:
                    used_volumes.append(vol["source"])
    declared_vols = list((model.get("volumes") or {}).keys())
    ordered_vols = [v for v in declared_vols if v in used_volumes]

    project = {
        "name": project_name,
        "services": services,
        "networks": _normalize_networks(model, ordered_nets, project_name),
        "volumes": _normalize_volumes_top(model, ordered_vols, project_name),
        "secrets": _normalize_secret_like(model, "secrets", project_name, project_dir, home, lookup),
        "configs": _normalize_secret_like(model, "configs", project_name, project_dir, home, lookup),
    }
    if model.get("models"):
        project["models"] = model["models"]
    for name_unset in sorted(unset):
        warnings.append('変数 "%s" が設定されていないため空文字として扱いました' % name_unset)
    project["_meta"] = {
        "loader": "builtin",
        "warnings": warnings,
        "env_split": ctx["env_split"],
        "dotenv_files": dotenv_used,
    }
    return project


def _load_raw_merged(opts, files, warnings):
    """include 用: 正規化せずにマージ済みモデルを返す (パスはそのファイル基準で絶対化)。"""
    project_dir = os.path.abspath(opts.project_directory or os.path.dirname(files[0]))
    environment, _, _ = build_environment(project_dir, opts)
    unset = set()
    home = os.path.expanduser("~")
    model = {}
    for path in files:
        data = _load_yaml_model(path, environment.get, unset, warnings)
        data["services"] = _resolve_extends(data.get("services") or {}, os.path.dirname(path), environment.get, unset, warnings, home)
        services = {}
        for name, svc in data["services"].items():
            services[name] = _absolutize_paths(svc, project_dir, home)
        data["services"] = services
        for kind in ("secrets", "configs"):
            for key, cfg in (data.get(kind) or {}).items():
                if isinstance(cfg, dict) and cfg.get("file"):
                    cfg["file"] = _abs(project_dir, cfg["file"], home)
        model = merge_models(model, data)
    return model


# ---------------------------------------------------------------------------
# 型をそろえる (両ローダー共通)
# ---------------------------------------------------------------------------
_DURATION_KEYS = ("interval", "timeout", "start_period", "start_interval")
_OMIT_FALSE_SERVICE = ("read_only", "privileged", "tty", "stdin_open", "oom_kill_disable", "use_api_socket")


def _sort_tree(node):
    """辞書のキーを名前順にそろえる (どちらのローダーでも同じ順番の出力にするため)。

    compose の動作は辞書の順番に左右されない (リストの順番は保つ)。
    サービス・ネットワーク・ボリュームの「作る順番」は _meta の順番を使う。
    """
    if isinstance(node, dict):
        return {k: _sort_tree(node[k]) for k in sorted(node, key=str)}
    if isinstance(node, list):
        return [_sort_tree(v) for v in node]
    return node


def canonicalize(project):
    for kind in ("services", "networks", "volumes", "secrets", "configs"):
        section = project.get(kind)
        if isinstance(section, dict):
            project[kind] = {name: _sort_tree(value) for name, value in section.items()}
    for net in (project.get("networks") or {}).values():
        for flag in ("internal", "attachable"):
            if net.get(flag) is False:
                net.pop(flag)
    for svc in (project.get("services") or {}).values():
        for flag in _OMIT_FALSE_SERVICE:
            if svc.get(flag) is False:
                svc.pop(flag)
        if svc.get("extra_hosts"):
            svc["extra_hosts"] = sorted(svc["extra_hosts"], key=lambda e: e.split("=", 1)[0])
        hc = svc.get("healthcheck")
        if hc:
            for key in _DURATION_KEYS:
                if hc.get(key) is not None:
                    hc[key] = go_duration(hc[key])
        if svc.get("stop_grace_period") is not None:
            svc["stop_grace_period"] = go_duration(svc["stop_grace_period"])
        for vol in svc.get("volumes") or []:
            if vol.get("read_only") is False:
                vol.pop("read_only")
        for key in ("mem_limit", "mem_reservation", "memswap_limit", "shm_size"):
            if svc.get(key) is not None:
                svc[key] = ram_in_bytes(svc[key])
        build = svc.get("build")
        if isinstance(build, dict) and build.get("shm_size") is not None:
            build["shm_size"] = ram_in_bytes(build["shm_size"])
        deploy = svc.get("deploy")
        if isinstance(deploy, dict):
            # compose の出力は空の placement / resources を付けるので、どちらのローダーでも外しておく
            for empty_key in ("placement", "resources"):
                if deploy.get(empty_key) == {}:
                    deploy.pop(empty_key)
            if not deploy:
                svc.pop("deploy")
                deploy = None
        if deploy and deploy.get("resources"):
            for part in ("limits", "reservations"):
                res = deploy["resources"].get(part)
                if res and res.get("memory") is not None:
                    res["memory"] = ram_in_bytes(res["memory"])
                if res and res.get("cpus") is not None:
                    res["cpus"] = float(res["cpus"])
        for port in svc.get("ports") or []:
            if port.get("published") is not None:
                port["published"] = str(port["published"])
            port["target"] = int(port["target"])
        for vol in svc.get("volumes") or []:
            tmpfs = vol.get("tmpfs")
            if tmpfs and tmpfs.get("size") is not None:
                tmpfs["size"] = ram_in_bytes(tmpfs["size"])
        for ref in svc.get("secrets") or []:
            if isinstance(ref.get("mode"), str):
                ref["mode"] = int(ref["mode"], 8)
        for ref in svc.get("configs") or []:
            if isinstance(ref.get("mode"), str):
                ref["mode"] = int(ref["mode"], 8)
        if svc.get("cpus") is not None:
            svc["cpus"] = float(svc["cpus"])
    return project


def raw_service_order(files):
    """compose ファイルに書かれた順番 (サービス・ネットワーク・ボリューム) を調べる。"""
    order = {"services": [], "networks": [], "volumes": []}
    for path in files:
        try:
            raw = yamlmini.load_file(path)
        except Exception:  # noqa: BLE001 - 順番が取れなくても動作には影響しない
            continue
        if not isinstance(raw, dict):
            continue
        for kind in order:
            section = raw.get(kind)
            if isinstance(section, dict):
                for key in section:
                    if key not in order[kind]:
                        order[kind].append(key)
    return order


def raw_profiles(files):
    """profiles 付きのサービス (compose ファイルに書かれたまま) を調べる。"""
    result = {}
    for path in files:
        try:
            raw = yamlmini.load_file(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(raw, dict):
            continue
        for name, svc in (raw.get("services") or {}).items():
            svc = _untag(svc)
            if isinstance(svc, dict) and svc.get("profiles"):
                result[name] = _str_list(svc.get("profiles"))
    return result


def load_project(opts):
    """compose ファイルを読み込み、正規化モデルを返す。"""
    files = resolve_files(opts)
    loader = opts.loader
    if loader == "auto":
        loader = "compose" if docker_compose_available(opts.docker) else "builtin"
    if loader == "compose":
        project = load_with_compose(opts, files)
    elif loader == "builtin":
        project = load_builtin(opts, files)
    else:
        raise LoadError("--loader には auto / compose / builtin を指定してください")
    canonicalize(project)
    meta = project.setdefault("_meta", {})
    meta["files"] = files
    project_dir = os.path.abspath(opts.project_directory or os.path.dirname(files[0]))
    meta["project_dir"] = project_dir
    order = raw_service_order(files)
    names = list(project["services"])
    ordered = [n for n in order["services"] if n in names] + sorted(n for n in names if n not in order["services"])
    meta["service_order"] = ordered
    nets = list(project.get("networks") or {})
    meta["network_order"] = [n for n in (["default"] + order["networks"]) if n in nets] + [n for n in nets if n not in (["default"] + order["networks"])]
    vols = list(project.get("volumes") or {})
    meta["volume_order"] = [v for v in order["volumes"] if v in vols] + [v for v in vols if v not in order["volumes"]]
    all_profiles = raw_profiles(files)
    meta["disabled_services"] = {n: p for n, p in all_profiles.items() if n not in names}
    meta["active_profiles"] = list(opts.profiles) or [p for p in (opts.environ.get("COMPOSE_PROFILES") or "").split(",") if p]
    return project
