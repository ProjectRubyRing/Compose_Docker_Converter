"""実行用コマンドを txt (そのまま貼り付け・bash で実行) と md に書き出す。"""

from . import TOOL_NAME, __version__
from .textutil import wrap

RULE = "# " + "=" * 76
THIN = "# " + "-" * 76


def _wrap_comment(text, width=72, prefix="#   "):
    """日本語を含む文を、見た目の幅で折り返してコメントにする (英単語は途中で切らない)。"""
    return "\n".join(prefix + line for line in wrap(text, width))


def header_lines(plan, meta, title):
    info = plan.info
    lines = [
        "#!/usr/bin/env bash",
        RULE,
        "#  %s" % title,
        "#  (%s %s で自動生成)" % (TOOL_NAME, __version__),
        THIN,
        "#  プロジェクト名 : %s" % info["project"],
        "#  元の compose   : %s" % ", ".join(meta.get("files") or []),
    ]
    if meta.get("files_local"):
        lines.append("#  (変換した場所 : %s)" % ", ".join(meta["files_local"]))
    lines += [
        "#  読み込み方法   : %s" % meta.get("loader_label", ""),
        "#  生成日時       : %s" % meta.get("generated_at", ""),
        "#  実行環境       : RHEL 9.8 + Docker Engine (docker-ce 25 以降 / 推奨 29.x)",
    ]
    return lines


def render_up_txt(plan, meta):
    out = header_lines(plan, meta, "docker compose up -d と同じ構成を docker コマンドだけで起動する手順")
    out += [
        "#",
        "#  ■ 使い方",
        "#   1) RHEL に docker を使えるユーザー (root か docker グループ) でログインする",
        "#   2) STEP 1 から順番に、STEP ごとのかたまりをコピーしてターミナルに貼り付け",
        "#      Enter を押す (結果を確かめてから次の STEP へ進むと安心です)",
        "#      まとめて実行する場合: bash %s" % meta.get("up_txt_name", "docker-commands.txt"),
        "#   3) 片付け (compose down 相当) は %s を使う" % meta.get("down_txt_name", "docker-commands-down.txt"),
        "#   ※ 2 回目以降に実行するときは、先に片付けをしてください (同じ名前があるとエラーになります)",
    ]
    if plan.warnings:
        out += ["#", "#  ■ 変換時の注意"]
        for warning in plan.warnings:
            out.append(_wrap_comment("・" + warning, prefix="#   "))
    out.append(RULE)
    out.append("")
    total = len(plan.steps)
    for step in plan.steps:
        out += step_block(step, total)
    out.append(RULE)
    out.append("#  ここまでで起動は完了です。片付けは %s を参照してください。" % meta.get("down_txt_name", "docker-commands-down.txt"))
    out.append(RULE)
    return "\n".join(out) + "\n"


def step_block(step, total):
    out = [THIN, "# STEP %d/%d [%s] %s" % (step.no, total, step.phase, step.title)]
    if step.compose_ref:
        out.append("#   (compose の対応箇所: %s)" % step.compose_ref)
    if step.summary:
        out.append(_wrap_comment(step.summary))
    for note in step.notes:
        out.append(_wrap_comment("※ " + note))
    out.append(THIN)
    out.append(step.script)
    out.append("")
    return out


def render_down_txt(plan, meta):
    out = header_lines(plan, meta, "後片付け (docker compose down と同じ) を docker コマンドで行う手順")
    out += [
        "#",
        "#  ■ 使い方",
        "#   STEP ごとに貼り付けて実行します。ボリューム (データ) とイメージの削除は",
        "#   先頭に # が付いています。必要なときだけ # を外して実行してください。",
        RULE,
        "",
    ]
    total = len(plan.down_steps)
    for step in plan.down_steps:
        out += step_block(step, total)
    return "\n".join(out) + "\n"


def _md_escape(text):
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def render_md(plan, meta):
    info = plan.info
    out = []
    out.append("# %s を docker コマンドだけで起動する手順" % info["project"])
    out.append("")
    out.append("`docker compose up -d` と同じ構成を、`docker` コマンドだけで作るための手順です。"
               "STEP 1 から順に、コードブロックの中身をそのままターミナルに貼り付けて実行します。")
    out.append("")
    out.append("| 項目 | 内容 |")
    out.append("|---|---|")
    out.append("| プロジェクト名 | `%s` |" % info["project"])
    out.append("| 元の compose ファイル | %s |" % "<br>".join("`%s`" % f for f in meta.get("files") or []))
    out.append("| 読み込み方法 | %s |" % _md_escape(meta.get("loader_label", "")))
    out.append("| 生成日時 | %s |" % meta.get("generated_at", ""))
    out.append("| 生成ツール | %s %s |" % (TOOL_NAME, __version__))
    out.append("| 実行環境 | RHEL 9.8 + Docker Engine (docker-ce 25 以降 / 推奨 29.x) |")
    out.append("| 起動するコンテナ | %s |" % "、".join("`%s`" % c for s in info["services"] for c in info["containers"][s]))
    out.append("")
    out.append("## 実行の前に")
    out.append("")
    out.append("1. RHEL 9.8 に Docker Engine (docker-ce) が入っていて、`sudo systemctl enable --now docker` で起動済みであること。")
    out.append("2. `root` か、`docker` グループに入っているユーザーで実行すること (`sudo usermod -aG docker <ユーザー名>` の後、ログインし直す)。")
    out.append("3. compose ファイルと、そこから参照されるファイル (Dockerfile・設定ファイル・env ファイルなど) が、同じフォルダ構成で RHEL 上に置かれていること。")
    out.append("4. 2 回目以降は、先に [後片付け](#後片付け-compose-down-と同じ) をしてから実行すること (同じ名前のコンテナやネットワークがあるとエラーになります)。")
    out.append("")
    if plan.warnings:
        out.append("## 変換時の注意")
        out.append("")
        for warning in plan.warnings:
            out.append("- %s" % warning)
        out.append("")
    out.append("## 手順一覧")
    out.append("")
    out.append("| STEP | 区分 | やること | 対象 |")
    out.append("|---:|---|---|---|")
    for step in plan.steps:
        out.append("| %d | %s | [%s](#step-%d) | %s |" % (step.no, step.phase, _md_escape(step.title), step.no,
                                                        _md_escape("`%s`" % step.target if step.target else "-")))
    out.append("")
    for step in plan.steps:
        out.append('<a id="step-%d"></a>' % step.no)
        out.append("")
        out.append("## STEP %d: %s" % (step.no, step.title))
        out.append("")
        out.append("- 区分: **%s**" % step.phase)
        if step.compose_ref:
            out.append("- compose の対応箇所: `%s`" % step.compose_ref)
        out.append("")
        if step.summary:
            out.append(step.summary)
            out.append("")
        for note in step.notes:
            out.append("> ※ %s" % note)
            out.append("")
        out.append("```bash")
        out.append(step.script)
        out.append("```")
        out.append("")
        if step.verify:
            out.append("確認: " + " ／ ".join("`%s`" % v for v in step.verify))
            out.append("")
    out.append("## 後片付け (compose down と同じ)")
    out.append("")
    out.append("起動と逆の順番で止めて削除します。ボリューム (データ) とイメージの削除は、必要なときだけ `#` を外して実行します。")
    out.append("")
    for step in plan.down_steps:
        out.append("### %d. %s" % (step.no, step.title))
        out.append("")
        if step.summary:
            out.append(step.summary)
            out.append("")
        out.append("```bash")
        out.append(step.script)
        out.append("```")
        out.append("")
    return "\n".join(out) + "\n"
