"""コマンドライン: compose ファイル → docker コマンド (txt / md) と解説 (xlsx / md)。"""

import argparse
import datetime
import json
import os
import sys

from . import TOOL_NAME, __version__
from .loader import LoadError, LoadOptions, build_environment, load_project
from .planner import PlanError, PlanOptions, build_plan
from .render_cmds import render_down_txt, render_md, render_up_txt

EPILOG = """使い方の例:
  # RHEL 上で compose ファイルのあるフォルダから実行 (docker compose config を使って正確に解釈)
  python3 compose2docker.py -f compose.yaml

  # 出力先を指定し、profiles も有効にして変換
  python3 compose2docker.py -f compose.yaml --profile debug -o ./out

  # Windows で作って RHEL の /opt/myapp に置く場合 (パスを RHEL 用に置き換え)
  python compose2docker.py -f compose.yaml --host-project-dir /opt/myapp

  # 一部のサービス (と、その依存先) だけ
  python3 compose2docker.py -f compose.yaml web db
"""


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="compose2docker",
        description="docker compose の構成を、docker コマンドだけで同じように動かす手順 (txt / md) と、その詳しい解説 (xlsx / md) を作ります。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("services", nargs="*", metavar="SERVICE", help="対象にするサービス (省略時は compose up と同じく全サービス)")
    parser.add_argument("-f", "--file", dest="files", action="append", default=[], help="compose ファイル (複数指定可。省略時は compose.yaml などを自動で探す)")
    parser.add_argument("-p", "--project-name", help="プロジェクト名 (省略時は name: またはフォルダ名)")
    parser.add_argument("--project-directory", help="プロジェクトのフォルダ (省略時は最初の compose ファイルのフォルダ)")
    parser.add_argument("--env-file", dest="env_files", action="append", default=[], help="変数の展開に使う .env ファイル (省略時はプロジェクトの .env)")
    parser.add_argument("--profile", dest="profiles", action="append", default=[], help="有効にする profile (複数指定可)")
    parser.add_argument("-o", "--output-dir", help="出力先フォルダ (省略時は ./compose2docker-out/<プロジェクト名>)")
    parser.add_argument("--prefix", default="", help="出力ファイル名の先頭に付ける文字列")
    parser.add_argument("--host-project-dir", help="RHEL 上のプロジェクトのフォルダ (Windows で変換するときに指定。\"$PWD\" を指定すると実行時のフォルダ基準)")
    parser.add_argument("--loader", choices=["auto", "compose", "builtin"], default="auto",
                        help="compose ファイルの読み込み方法 (auto: docker compose があればそれを使う / builtin: 内蔵パーサ)")
    parser.add_argument("--compose-labels", action="store_true", help="compose が付けるラベル (com.docker.compose.*) も付ける")
    parser.add_argument("--healthcheck-exec", choices=["image", "shell"], default="image",
                        help="healthcheck の CMD (exec 形式) の再現方法 (image: 派生イメージに焼き込む / shell: --health-cmd で代用)")
    parser.add_argument("--env-mode", choices=["auto", "inline", "file"], default="auto",
                        help="env_file の渡し方 (auto: そのまま渡せるときは --env-file / inline: すべて --env)")
    parser.add_argument("--no-guide", action="store_true", help="解説 (xlsx / md) を作らない")
    parser.add_argument("--no-xlsx", action="store_true", help="解説の xlsx を作らない")
    parser.add_argument("--dump-model", action="store_true", help="読み込んだ正規化モデルを JSON で保存する (調査用)")
    parser.add_argument("--dump-plan", action="store_true", help="作るコンテナ・ネットワーク・ボリュームの一覧を JSON で保存する (tools/compare_env.py 用)")
    parser.add_argument("--docker", default="docker", help="docker コマンドのパス")
    parser.add_argument("--version", action="version", version="%s %s" % (TOOL_NAME, __version__))
    return parser.parse_args(argv)


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _safe_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _safe_console()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    host = args.host_project_dir
    if host and host not in ("$PWD", "PWD", ".") and not host.startswith("/"):
        hint = ""
        if "/Git/" in host.replace("\\", "/"):
            hint = " (Git Bash が /opt/... を Windows のパスに書き換えています。MSYS_NO_PATHCONV=1 を付けて実行するか、PowerShell から実行してください)"
        print("エラー: --host-project-dir には RHEL 上のパス (/ で始まる、例: /opt/myapp) を指定してください: %s%s" % (host, hint), file=sys.stderr)
        return 2
    opts = LoadOptions(files=args.files, project_name=args.project_name, project_directory=args.project_directory,
                       env_files=args.env_files, profiles=args.profiles, services=args.services,
                       loader=args.loader, docker=args.docker)
    try:
        project = load_project(opts)
    except LoadError as exc:
        print("エラー: %s" % exc, file=sys.stderr)
        return 2
    meta = project["_meta"]
    environment, _, _ = build_environment(meta["project_dir"], opts)
    now = datetime.datetime.now()
    popts = PlanOptions(host_project_dir=args.host_project_dir, compose_labels=args.compose_labels,
                        healthcheck_exec=args.healthcheck_exec, env_mode=args.env_mode,
                        lookup=environment.get, compose_version=meta.get("compose_version"),
                        generated_at=now)
    try:
        plan = build_plan(project, popts)
    except PlanError as exc:
        print("エラー: %s" % exc, file=sys.stderr)
        return 2
    outdir = args.output_dir or os.path.join(os.getcwd(), "compose2docker-out", project["name"])
    os.makedirs(outdir, exist_ok=True)
    prefix = args.prefix
    names = {
        "up_txt": prefix + "docker-commands.txt",
        "down_txt": prefix + "docker-commands-down.txt",
        "md": prefix + "docker-commands.md",
        "guide_md": prefix + "docker-commands-guide.md",
        "guide_xlsx": prefix + "docker-commands-guide.xlsx",
    }
    if meta.get("loader") == "compose":
        label = "docker compose config (Docker Compose %s が解釈した結果)" % (meta.get("compose_version") or "")
    else:
        label = "内蔵パーサ (docker compose と同じ規則で解釈)"
    files_host = plan.info.get("files_on_host") or meta.get("files")
    files_local = plan.info.get("files_local") or meta.get("files")
    rmeta = {
        "files": files_host,
        "files_local": files_local if files_local != files_host else None,
        "loader_label": label,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "up_txt_name": names["up_txt"],
        "down_txt_name": names["down_txt"],
        "names": names,
        "compose_version": meta.get("compose_version"),
    }
    written = []
    path = os.path.join(outdir, names["up_txt"])
    write_text(path, render_up_txt(plan, rmeta))
    written.append(path)
    path = os.path.join(outdir, names["down_txt"])
    write_text(path, render_down_txt(plan, rmeta))
    written.append(path)
    path = os.path.join(outdir, names["md"])
    write_text(path, render_md(plan, rmeta))
    written.append(path)
    if not args.no_guide:
        from .render_guide import render_guide_md, render_guide_xlsx
        path = os.path.join(outdir, names["guide_md"])
        write_text(path, render_guide_md(plan, rmeta))
        written.append(path)
        if not args.no_xlsx:
            path = os.path.join(outdir, names["guide_xlsx"])
            render_guide_xlsx(plan, rmeta, path)
            written.append(path)
    if args.dump_plan:
        path = os.path.join(outdir, prefix + "docker-commands-plan.json")
        info = plan.info
        data = {
            "project": info["project"],
            "containers": [c for s in info["services"] for c in info["containers"][s]],
            "networks": [project["networks"][k].get("name") for k in meta.get("network_order") or []
                         if k in project.get("networks", {}) and not project["networks"][k].get("external")],
            "volumes": [project["volumes"][k].get("name") for k in meta.get("volume_order") or []
                        if k in project.get("volumes", {}) and not project["volumes"][k].get("external")],
            "images": info["images"],
            "derived_images": info["derived"],
        }
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        written.append(path)
    if args.dump_model:
        path = os.path.join(outdir, prefix + "compose-model.json")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(project, handle, ensure_ascii=False, indent=2, default=str)
        written.append(path)
    print("プロジェクト %s を変換しました (%d ステップ / 読み込み: %s)" % (project["name"], len(plan.steps), meta.get("loader")))
    for warning in plan.warnings:
        print("  注意: %s" % warning)
    for path in written:
        print("  出力: %s" % path)
    return 0
