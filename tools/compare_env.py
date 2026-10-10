#!/usr/bin/env python3
"""docker compose で起動した環境と、docker コマンドで起動した環境の「中身」を比べるツール。

使い方 (RHEL 上で):
  1) docker compose up -d で起動
       python3 tools/compare_env.py snapshot --plan out/docker-commands-plan.json -o compose.json
  2) docker compose down (ボリュームも消すなら -v) で片付け
  3) 生成した docker-commands.txt を実行
       python3 tools/compare_env.py snapshot --plan out/docker-commands-plan.json -o docker.json
  4) 比べる
       python3 tools/compare_env.py diff compose.json docker.json

--plan には compose2docker の --dump-plan で出力される JSON を指定します。
コンテナ ID・作成日時・IP アドレスなど「毎回変わる値」と、compose が付ける
com.docker.compose.* ラベルは比較から除きます。
"""

import argparse
import json
import re
import subprocess
import sys


def docker_json(args):
    proc = subprocess.run(["docker"] + args, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def _labels(labels):
    out = {}
    for key, value in (labels or {}).items():
        if key.startswith("com.docker.compose.") or key.startswith("desktop.docker.io/"):
            continue
        out[key] = value
    return out


def _source(path):
    if not path:
        return path
    if path.startswith("/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/"):
        return "<docker-desktop-file-bind>"
    return path


def _bind_entry(entry):
    parts = entry.split(":")
    if len(parts) >= 3 and parts[-1] in ("rw",):
        parts = parts[:-1]
    if len(parts) >= 3:
        opts = [o for o in parts[-1].split(",") if o != "rw"]
        parts = parts[:-1] + ([",".join(opts)] if opts else [])
    if parts and parts[0].startswith("/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/"):
        parts[0] = "<docker-desktop-file-bind>"
    return ":".join(parts)


def container_snapshot(name, id_to_name):
    data = docker_json(["inspect", name])
    if not data:
        return {"missing": True}
    item = data[0]
    cfg = item.get("Config") or {}
    host = item.get("HostConfig") or {}
    short = item["Id"][:12]
    snap = {}
    snap["Config.Image"] = cfg.get("Image")
    snap["Config.Cmd"] = cfg.get("Cmd")
    snap["Config.Entrypoint"] = cfg.get("Entrypoint")
    snap["Config.Env"] = sorted(set(cfg.get("Env") or []))
    snap["Config.User"] = cfg.get("User")
    snap["Config.WorkingDir"] = cfg.get("WorkingDir")
    hostname = cfg.get("Hostname")
    if hostname == short or ((host.get("NetworkMode") or "").startswith("container:") and re.match(r"^[0-9a-f]{12}$", hostname or "")):
        hostname = "<id>"
    snap["Config.Hostname"] = hostname
    snap["Config.Domainname"] = cfg.get("Domainname")
    snap["Config.ExposedPorts"] = sorted((cfg.get("ExposedPorts") or {}).keys())
    snap["Config.Labels"] = _labels(cfg.get("Labels"))
    snap["Config.StopSignal"] = cfg.get("StopSignal")
    snap["Config.StopTimeout"] = cfg.get("StopTimeout")
    snap["Config.Healthcheck"] = cfg.get("Healthcheck")
    snap["Config.Tty"] = cfg.get("Tty")
    snap["Config.OpenStdin"] = cfg.get("OpenStdin")
    keys = ["PortBindings", "RestartPolicy", "CapAdd", "CapDrop", "SecurityOpt", "Privileged", "ReadonlyRootfs",
            "Init", "Tmpfs", "ShmSize", "Sysctls", "LogConfig", "Memory", "MemoryReservation", "MemorySwap",
            "MemorySwappiness", "NanoCpus", "PidsLimit", "CpuShares", "CpuPeriod", "CpuQuota", "CpusetCpus", "Dns",
            "DnsSearch", "DnsOptions", "GroupAdd", "IpcMode", "PidMode", "UTSMode", "UsernsMode", "CgroupnsMode",
            "Devices", "DeviceRequests", "OomKillDisable", "OomScoreAdj", "Runtime", "Links", "Isolation",
            "Annotations", "CgroupParent", "BlkioWeight", "DeviceCgroupRules", "StorageOpt"]
    for key in keys:
        value = host.get(key)
        if value in ([], {}, ""):
            value = None
        snap["HostConfig." + key] = value
    snap["HostConfig.ExtraHosts"] = sorted(host.get("ExtraHosts") or []) or None
    snap["HostConfig.Ulimits"] = sorted(host.get("Ulimits") or [], key=lambda u: u.get("Name")) or None
    mode = host.get("NetworkMode") or ""
    if mode.startswith("container:"):
        cid = mode.split(":", 1)[1]
        mode = "container:" + id_to_name.get(cid, cid)
    snap["HostConfig.NetworkMode"] = mode
    snap["HostConfig.VolumesFrom"] = sorted(id_to_name.get(v.split(":")[0], v.split(":")[0]) + (":" + v.split(":", 1)[1] if ":" in v else "") for v in (host.get("VolumesFrom") or [])) or None
    mounts = []
    for mount in item.get("Mounts") or []:
        mounts.append({
            "Type": mount.get("Type"),
            "Name": ("<anonymous>" if re.match(r"^[0-9a-f]{64}$", mount.get("Name") or "") else mount.get("Name")),
            "Source": _source(mount.get("Source")) if mount.get("Type") == "bind" else None,
            "Destination": mount.get("Destination"),
            "RW": mount.get("RW"),
        })
    snap["Mounts"] = sorted(mounts, key=lambda m: m["Destination"])
    nets = {}
    for net, cfgn in ((item.get("NetworkSettings") or {}).get("Networks") or {}).items():
        aliases = sorted(a for a in (cfgn.get("Aliases") or []) if a not in (short, item["Name"].lstrip("/")))
        ipam = cfgn.get("IPAMConfig") or {}
        ipam = {k: v for k, v in ipam.items() if v}
        nets[net] = {
            "Aliases": aliases,
            "IPAMConfig": ipam or None,
            "DriverOpts": cfgn.get("DriverOpts") or None,
            "GwPriority": cfgn.get("GwPriority") or 0,
        }
    snap["Networks"] = nets
    state = item.get("State") or {}
    snap["State.Status"] = state.get("Status")
    snap["State.ExitCode"] = state.get("ExitCode")
    snap["State.Health"] = (state.get("Health") or {}).get("Status")
    return snap


def network_snapshot(name):
    data = docker_json(["network", "inspect", name])
    if not data:
        return {"missing": True}
    item = data[0]
    ipam = item.get("IPAM") or {}
    return {
        "Driver": item.get("Driver"),
        "Internal": item.get("Internal"),
        "Attachable": item.get("Attachable"),
        "EnableIPv6": item.get("EnableIPv6"),
        "EnableIPv4": item.get("EnableIPv4"),
        "IPAM.Driver": ipam.get("Driver"),
        "IPAM.Options": ipam.get("Options") or None,
        "Options": item.get("Options") or None,
        "Labels": _labels(item.get("Labels")),
    }


def volume_snapshot(name):
    data = docker_json(["volume", "inspect", name])
    if not data:
        return {"missing": True}
    item = data[0]
    return {"Driver": item.get("Driver"), "Options": item.get("Options") or None, "Labels": _labels(item.get("Labels"))}


def snapshot(plan):
    names = plan.get("containers") or []
    id_to_name = {}
    for name in names:
        data = docker_json(["inspect", name])
        if data:
            id_to_name[data[0]["Id"]] = name
    return {
        "containers": {name: container_snapshot(name, id_to_name) for name in names},
        "networks": {name: network_snapshot(name) for name in plan.get("networks") or []},
        "volumes": {name: volume_snapshot(name) for name in plan.get("volumes") or []},
    }


def diff(a, b, path=""):
    out = []
    if path.endswith(".Mounts") and isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        # Docker Desktop はファイルのバインドマウント元を内部のパスに置き換えることがあるので、
        # 片方がその表示のときは Source の比較を省く (RHEL では起きない)
        a = [dict(x) for x in a]
        b = [dict(x) for x in b]
        for x, y in zip(a, b):
            if "<docker-desktop-file-bind>" in (x.get("Source"), y.get("Source")):
                x["Source"] = y["Source"] = "<docker-desktop-file-bind>"
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            out += diff(a.get(key), b.get(key), "%s.%s" % (path, key) if path else key)
        return out
    if a != b:
        out.append((path, a, b))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="compose 版と docker コマンド版の環境の差分を調べます")
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="今の環境 (docker inspect) を JSON に保存")
    snap.add_argument("--plan", required=True, help="compose2docker --dump-plan で出力した JSON")
    snap.add_argument("-o", "--output", required=True)
    dif = sub.add_parser("diff", help="2 つのスナップショットを比べる")
    dif.add_argument("left")
    dif.add_argument("right")
    dif.add_argument("--ignore-image", action="store_true", help="Config.Image の違い (ヘルスチェック入り派生イメージ) を無視")
    args = parser.parse_args(argv)
    if args.cmd == "snapshot":
        with open(args.plan, encoding="utf-8") as handle:
            plan = json.load(handle)
        data = snapshot(plan)
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        print("保存しました: %s" % args.output)
        return 0
    with open(args.left, encoding="utf-8") as handle:
        left = json.load(handle)
    with open(args.right, encoding="utf-8") as handle:
        right = json.load(handle)
    diffs = diff(left, right)
    shown = 0
    for path, a, b in diffs:
        if args.ignore_image and path.endswith("Config.Image"):
            continue
        shown += 1
        print("差分: %s\n   左 : %s\n   右 : %s" % (path, json.dumps(a, ensure_ascii=False), json.dumps(b, ensure_ascii=False)))
    if not shown:
        print("差分はありません (比較対象の項目はすべて同じです)")
    return 1 if shown else 0


if __name__ == "__main__":
    sys.exit(main())
