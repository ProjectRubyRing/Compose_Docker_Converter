"""解説資料 (Markdown / Excel) を作る。

* Markdown: 手順ごとの解説 + コマンドの種類ごとの深掘り + 用語集・年表など
* Excel: Meiryo UI・モノトーン。シートごとに表・カード形式で整理
"""

from . import TOOL_NAME, __version__
from .kb_commands import COMMANDS, STEP_KIND_TO_COMMAND
from .kb_misc import (ARCHITECTURE, GENERIC_MAPPING, GLOSSARY, INTRO, LIMITATIONS, PHASES,
                      RHEL_NOTES, RHEL_SETUP, TIMELINE)
from .kb_options import POSITIONAL, option_info
from .textutil import display_width
from .xlsx import Workbook

# ---------------------------------------------------------------------------
# 共通: ステップごとの解説データを組み立てる
# ---------------------------------------------------------------------------


def command_key(step):
    return STEP_KIND_TO_COMMAND.get(step.kind, "docker run")


def step_option_rows(step):
    """そのステップで使っているオプションの説明行。"""
    rows = []
    seen = set()
    for cmd in step.cmds:
        ckey = cmd.kb
        for opt in cmd.opts:
            compose_hint, meaning, kids = option_info(ckey, opt.flag)
            rows.append({
                "command": cmd.head,
                "option": opt.flag,
                "value": opt.display_value(),
                "compose": opt.src or (compose_hint if compose_hint and compose_hint != "-" else "(compose が自動で付ける / 手順上必要)"),
                "here": opt.note or "",
                "meaning": meaning,
                "kids": kids,
                "dup": (ckey, opt.flag) in seen,
            })
            seen.add((ckey, opt.flag))
        for arg in cmd.args:
            pos = POSITIONAL.get(arg.kb or "", None)
            rows.append({
                "command": cmd.head,
                "option": "(%s)" % arg.label,
                "value": str(arg.value),
                "compose": arg.src or (pos[0] if pos else ""),
                "here": arg.note or "",
                "meaning": pos[1] if pos else "",
                "kids": pos[2] if pos else "",
                "dup": False,
            })
        if cmd.cmd_args:
            rows.append({
                "command": cmd.head,
                "option": "(コマンドと引数)",
                "value": " ".join(cmd.cmd_args),
                "compose": getattr(cmd, "cmd_src", "") or "",
                "here": getattr(cmd, "cmd_note", "") or "",
                "meaning": "イメージ名の後ろに書いたものは、コンテナの中で実行するプログラムとその引数です。compose で文字列で書いた command は、compose と同じ規則 (シェルの書き方) で単語に分けています。",
                "kids": "お部屋に入った住人が、最初にやるお仕事です。",
                "dup": False,
            })
    return rows


def step_does(step):
    parts = []
    if step.summary:
        parts.append(step.summary)
    parts.extend(step.details)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def _md(text):
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def render_guide_md(plan, rmeta):
    info = plan.info
    out = []
    title = "%s ― docker コマンド実行手順の詳しい解説" % info["project"]
    out.append("# %s" % title)
    out.append("")
    out.append("> %s %s で自動生成 ／ 生成日時: %s ／ 元の compose: %s" % (
        TOOL_NAME, __version__, rmeta.get("generated_at", ""), ", ".join("`%s`" % f for f in rmeta.get("files") or [])))
    out.append("> 読み込み方法: %s" % rmeta.get("loader_label", ""))
    out.append("")
    out.append("実行用のコマンドは `%s` (そのまま貼り付け / bash で実行) と `%s` にあります。この資料は、その 1 つ 1 つのコマンドの意味・しくみ・歴史を説明します。" % (
        rmeta["names"]["up_txt"], rmeta["names"]["md"]))
    out.append("")
    sections = ["はじめに", "Docker が動くしくみの全体像", "実行の流れ", "RHEL 9.8 での事前準備", "手順ごとの詳しい解説",
                "コマンドの種類ごとの深掘り解説", "compose の設定と docker オプションの対応表", "用語集", "歴史年表",
                "注意点・制限事項", "後片付けの手順"]
    out.append("## 目次")
    out.append("")
    for idx, name in enumerate(sections):
        out.append("%d. [%s](#%d-%s)" % (idx + 1, name, idx + 1, _anchor(name)))
    out.append("")

    out.append("## 1. はじめに")
    out.append("")
    for head, text in INTRO:
        out.append("### %s" % head)
        out.append("")
        out.append(text)
        out.append("")
    out.append("| 項目 | 内容 |")
    out.append("|---|---|")
    out.append("| プロジェクト名 | `%s` |" % info["project"])
    out.append("| サービス | %s |" % "、".join("`%s`" % s for s in info["services"]))
    out.append("| コンテナ | %s |" % "、".join("`%s`" % c for s in info["services"] for c in info["containers"][s]))
    out.append("| 手順の数 | 起動 %d STEP ／ 片付け %d STEP |" % (len(plan.steps), len(plan.down_steps)))
    out.append("")

    out.append("## 2. Docker が動くしくみの全体像")
    out.append("")
    out.append("```text")
    out.append(_architecture_diagram())
    out.append("```")
    out.append("")
    for para in ARCHITECTURE.split("\n\n"):
        out.append(para.replace("\n", "  \n"))
        out.append("")

    out.append("## 3. 実行の流れ")
    out.append("")
    out.append("| 順番 | フェーズ | 内容 | この手順での STEP |")
    out.append("|---:|---|---|---|")
    groups = _phase_groups(plan)
    for idx, (phase, text) in enumerate(PHASES):
        steps = groups.get(phase, [])
        out.append("| %d | %s | %s | %s |" % (idx + 1, phase, _md(text), "、".join("[%d](#step-%d)" % (s, s) for s in steps) or "-"))
    out.append("")
    out.append("サービスの起動順 (depends_on などの依存関係を守った順番): %s" % " → ".join("`%s`" % s for s in info["services"]))
    out.append("")

    out.append("## 4. RHEL 9.8 での事前準備")
    out.append("")
    for head, cmds, text in RHEL_SETUP:
        out.append("### %s" % head)
        out.append("")
        out.append(text)
        out.append("")
        out.append("```bash")
        out.append(cmds)
        out.append("```")
        out.append("")

    out.append("## 5. 手順ごとの詳しい解説")
    out.append("")
    out.append("同じ種類のコマンドが 2 回目以降に出てくるときは、しくみ・歴史などの共通の説明を「6. コマンドの種類ごとの深掘り解説」にまとめ、"
               "ここではそのステップに固有の内容 (オプションの値の意味など) を中心に説明します。")
    out.append("")
    first_seen = {}
    option_seen = {}
    for step in plan.steps:
        ckey = command_key(step)
        kb = COMMANDS.get(ckey, {})
        first = ckey not in first_seen
        if first:
            first_seen[ckey] = step.no
        out.append('<a id="step-%d"></a>' % step.no)
        out.append("")
        out.append("### STEP %d: %s" % (step.no, step.title))
        out.append("")
        out.append("| 項目 | 内容 |")
        out.append("|---|---|")
        out.append("| 区分 | %s |" % step.phase)
        out.append("| 使うコマンド | %s |" % _md(kb.get("title", ckey)))
        out.append("| ひとことで | %s |" % _md(kb.get("oneline", "")))
        out.append("| compose の対応箇所 | %s |" % ("`%s`" % step.compose_ref if step.compose_ref else "-"))
        out.append("")
        out.append("**実行するコマンド**")
        out.append("")
        out.append("```bash")
        out.append(step.script)
        out.append("```")
        out.append("")
        out.append("**実行のしかた**")
        out.append("")
        if first:
            out.append(kb.get("how", "").replace("\n", "  \n"))
        else:
            out.append("上のかたまりをコピーしてターミナルに貼り付け、Enter を押します (成功・失敗の見分け方は [STEP %d](#step-%d) と同じです)。" % (
                first_seen[ckey], first_seen[ckey]))
        out.append("")
        out.append("**このコマンドがすること**")
        out.append("")
        out.append(step.summary)
        out.append("")
        for detail in step.details:
            out.append("- %s" % detail)
        if step.details:
            out.append("")
        rows = step_option_rows(step)
        if rows:
            out.append("**オプション・引数の意味**")
            out.append("")
            out.append("| オプション | 値 | compose の設定 | このステップでの意味 | しくみ・やさしい説明 |")
            out.append("|---|---|---|---|---|")
            for row in rows:
                okey = (row["command"], row["option"])
                if row["dup"]:
                    mech, kids = "(同じオプションの説明は上の行を参照)", ""
                elif okey in option_seen and option_seen[okey] != step.no and row["option"].startswith("-"):
                    mech, kids = "(しくみは [STEP %d](#step-%d) で説明)" % (option_seen[okey], option_seen[okey]), ""
                else:
                    option_seen.setdefault(okey, step.no)
                    mech, kids = row["meaning"], row["kids"]
                out.append("| `%s` | %s | %s | %s | %s%s |" % (
                    row["option"], _md("`%s`" % row["value"]) if row["value"] else "", _md(row["compose"]), _md(row["here"]),
                    _md(mech), ("<br>（やさしく）" + _md(kids)) if kids else ""))
            out.append("")
        if first:
            out.append("**しくみ (動作原理)**")
            out.append("")
            out.append(kb.get("principle", "").replace("\n", "  \n"))
            out.append("")
            out.append("**動作イメージ (たとえ話)**")
            out.append("")
            out.append(kb.get("image", ""))
            out.append("")
            out.append("**歴史と背景・必要になった経緯**")
            out.append("")
            out.append(kb.get("history", "").replace("\n", "  \n"))
            out.append("")
            out.append("**RHEL 9.8 での注意**")
            out.append("")
            out.append(kb.get("rhel", "").replace("\n", "  \n"))
            out.append("")
        else:
            out.append("**しくみ・歴史**: STEP %d と同じ `%s` です。詳しくは [6. コマンドの種類ごとの深掘り解説](#%s) を参照してください。" % (
                first_seen[ckey], ckey, _anchor("kb-" + ckey)))
            out.append("")
        out.append("**小学生向けのまとめ**: %s" % kb.get("kids", ""))
        out.append("")
        if step.notes:
            out.append("**この STEP の注意**")
            out.append("")
            for note in step.notes:
                out.append("- %s" % note)
            out.append("")
        if step.verify:
            out.append("**確認のしかた**: " + " ／ ".join("`%s`" % v for v in step.verify))
            out.append("")
        if step.compose_snippet:
            out.append("<details><summary>compose ではこう書かれていた (正規化後)</summary>")
            out.append("")
            out.append("```yaml")
            out.append(step.compose_snippet)
            out.append("```")
            out.append("")
            out.append("</details>")
            out.append("")

    out.append("## 6. コマンドの種類ごとの深掘り解説")
    out.append("")
    for ckey in _used_commands(plan):
        kb = COMMANDS.get(ckey)
        if not kb:
            continue
        out.append('<a id="%s"></a>' % _anchor("kb-" + ckey))
        out.append("")
        out.append("### %s" % kb["title"])
        out.append("")
        out.append("- 書き方: `%s`" % kb["syntax"])
        out.append("- ひとことで: %s" % kb["oneline"])
        out.append("")
        for label, key in (("意味", "meaning"), ("しくみ (動作原理)", "principle"), ("動作イメージ", "image"),
                           ("歴史と背景・必要になった経緯", "history"), ("小学生向けのまとめ", "kids"), ("RHEL 9.8 での注意", "rhel")):
            out.append("**%s**" % label)
            out.append("")
            out.append(kb.get(key, "").replace("\n", "  \n"))
            out.append("")

    out.append("## 7. compose の設定と docker オプションの対応表")
    out.append("")
    out.append("### このプロジェクトでの対応")
    out.append("")
    out.append("| サービス | コンテナ | compose の設定 | docker のオプション | 値 | 意味 |")
    out.append("|---|---|---|---|---|---|")
    for row in plan.mapping_rows:
        out.append("| %s | %s | %s | `%s` | %s | %s |" % (row["service"], row["container"], _md(row["compose"]), row["docker"],
                                                       _md("`%s`" % row["value"]) if row["value"] else "", _md(row["note"])))
    out.append("")
    out.append("### 一般的な対応")
    out.append("")
    out.append("| compose の設定 | docker コマンド | 補足 |")
    out.append("|---|---|---|")
    for compose_key, docker, note in GENERIC_MAPPING:
        out.append("| `%s` | %s | %s |" % (compose_key, _md(docker), _md(note)))
    out.append("")

    out.append("## 8. 用語集")
    out.append("")
    out.append("| 用語 | 読み・英語 | 意味 | 小学生向けのたとえ |")
    out.append("|---|---|---|---|")
    for term, reading, meaning, kids in GLOSSARY:
        out.append("| %s | %s | %s | %s |" % (_md(term), _md(reading), _md(meaning), _md(kids)))
    out.append("")

    out.append("## 9. 歴史年表")
    out.append("")
    out.append("| 時期 | 出来事 | 何が変わったか |")
    out.append("|---|---|---|")
    for when, event, change in TIMELINE:
        out.append("| %s | %s | %s |" % (when, _md(event), _md(change)))
    out.append("")

    out.append("## 10. 注意点・制限事項")
    out.append("")
    out.append("### このプロジェクトの変換メモ")
    out.append("")
    notes = list(plan.warnings)
    for step in plan.steps:
        for note in step.notes:
            item = "STEP %d: %s" % (step.no, note)
            if item not in notes:
                notes.append(item)
    if notes:
        for note in notes:
            out.append("- %s" % note)
    else:
        out.append("- 特にありません。")
    out.append("")
    out.append("### docker コマンドに直すときの一般的な注意")
    out.append("")
    for head, text in LIMITATIONS:
        out.append("- **%s**: %s" % (head, text))
    out.append("")
    out.append("### RHEL 9.8 で気をつけること")
    out.append("")
    for head, text in RHEL_NOTES:
        out.append("- **%s**: %s" % (head, text))
    out.append("")

    out.append("## 11. 後片付けの手順")
    out.append("")
    out.append("`%s` に同じ内容があります。起動と逆の順番で止めて削除します (compose down と同じ)。" % rmeta["names"]["down_txt"])
    out.append("")
    for step in plan.down_steps:
        ckey = command_key(step)
        kb = COMMANDS.get(ckey, {})
        out.append("### %d. %s" % (step.no, step.title))
        out.append("")
        out.append(step.summary)
        out.append("")
        out.append("```bash")
        out.append(step.script)
        out.append("```")
        out.append("")
        if kb:
            out.append("- しくみ: %s" % kb.get("meaning", "").replace("\n", " "))
            out.append("- 小学生向け: %s" % kb.get("kids", ""))
            out.append("")
    return "\n".join(out) + "\n"


def _anchor(text):
    out = []
    for ch in text.lower():
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        elif ch in " ":
            out.append("-")
    return "".join(out)


def _architecture_diagram():
    return "\n".join([
        "  あなた (ターミナル)",
        "     │ docker run ... (このファイルのコマンド)",
        "     ▼",
        "  docker コマンド (クライアント = リモコン)",
        "     │ HTTP + JSON (Docker Engine API)  ※ /var/run/docker.sock を通る",
        "     ▼",
        "  dockerd (Docker Engine = 管理人さん)  … イメージ / ネットワーク / ボリューム / ログ / ヘルスチェック / 再起動",
        "     │ gRPC",
        "     ▼",
        "  containerd (現場監督) → containerd-shim-runc-v2 → runc (大工さん)",
        "     │ システムコール",
        "     ▼",
        "  Linux カーネル (RHEL 9.8)",
        "     ├ namespace … 見える範囲を分ける (部屋の壁)",
        "     ├ cgroup v2 … 使える量を制限 (ブレーカー)",
        "     ├ overlayfs … イメージの層 + 書き込み層 (透明シートの重ね合わせ)",
        "     └ netfilter … アドレス変換・ポート公開 (建物の受付係)",
        "     ▼",
        "  コンテナ (囲いの中で動く、ふつうのプロセス)",
    ])


def _phase_groups(plan):
    mapping = {
        "prepare": "準備", "network_external": "ネットワーク", "network_create": "ネットワーク",
        "volume_external": "ボリューム", "volume_create": "ボリューム", "pull": "イメージ取得", "build": "イメージ作成",
        "healthcheck_image": "ヘルスチェック入りイメージ", "check": "確認",
    }
    groups = {}
    for step in plan.steps:
        phase = mapping.get(step.kind, "起動")
        groups.setdefault(phase, []).append(step.no)
    return groups


def _used_commands(plan):
    keys = []
    for step in list(plan.steps) + list(plan.down_steps):
        key = command_key(step)
        if key not in keys:
            keys.append(key)
        if step.kind == "pull" and "docker image inspect" not in keys:
            keys.append("docker image inspect")
    return keys


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
GRAY_DARK = "262626"
GRAY_MID = "404040"
GRAY = "595959"
GRAY_LINE = "BFBFBF"
GRAY_L1 = "D9D9D9"
GRAY_L2 = "EDEDED"
GRAY_L3 = "F2F2F2"
GRAY_L4 = "FAFAFA"
WHITE = "FFFFFF"

MAX_CELL_LINES = 24


def _estimate_lines(text, width):
    """Excel (Meiryo UI 10pt) で折り返したときの、だいたいの行数。"""
    capacity = max(int(width * 1.55), 10)
    total = 0
    for para in str(text).split("\n"):
        total += max(1, -(-display_width(para) // capacity))
    return total


def _split_long(text, width=124, limit=MAX_CELL_LINES):
    """1 つのセルが Excel の行の高さの上限 (409pt) を超えないよう、段落・文の区切りで分ける。"""
    text = str(text or "")
    if _estimate_lines(text, width) <= limit:
        return [text]
    pieces = []
    for para in text.split("\n"):
        if _estimate_lines(para, width) <= limit:
            pieces.append(para)
            continue
        sentence = ""
        for part in [p + "。" for p in para.split("。")[:-1]] + [para.split("。")[-1]]:
            if sentence and _estimate_lines(sentence + part, width) > limit:
                pieces.append(sentence)
                sentence = part
            else:
                sentence += part
        if sentence:
            pieces.append(sentence)
    chunks = []
    current = ""
    for piece in pieces:
        candidate = (current + "\n" + piece) if current else piece
        if current and _estimate_lines(candidate, width) > limit:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class _Styles:
    def __init__(self, wb):
        border = ("thin", GRAY_LINE)
        self.title = wb.style(size=18, bold=True, wrap=False, valign="center")
        self.subtitle = wb.style(size=10, color=GRAY, wrap=False, valign="center")
        self.band = wb.style(size=12, bold=True, color=WHITE, fill=GRAY_MID, valign="center", wrap=False)
        self.th = wb.style(bold=True, color=WHITE, fill=GRAY, border=border, halign="center", valign="center")
        self.td = wb.style(border=border)
        self.td_alt = wb.style(border=border, fill=GRAY_L4)
        self.td_center = wb.style(border=border, halign="center")
        self.td_center_alt = wb.style(border=border, halign="center", fill=GRAY_L4)
        self.label = wb.style(bold=True, fill=GRAY_L2, border=border)
        self.code = wb.style(fill=GRAY_L3, border=border)
        self.code_plain = wb.style(fill=GRAY_L3)
        self.step_head = wb.style(size=11, bold=True, color=WHITE, fill=GRAY_DARK, border=("thin", GRAY_DARK), valign="center")
        self.step_head_center = wb.style(size=11, bold=True, color=WHITE, fill=GRAY_DARK, border=("thin", GRAY_DARK), halign="center", valign="center")
        self.muted = wb.style(size=9, color=GRAY)
        self.text = wb.style()
        self.bold = wb.style(bold=True)
        self.link = wb.style(color=GRAY_DARK, underline=True, border=border, halign="center")
        self.link_plain = wb.style(color=GRAY_DARK, underline=True)
        self.warn = wb.style(bold=True, fill=GRAY_L1, border=border)
        self.comment = wb.style(color=GRAY)
        self.comment_bold = wb.style(bold=True, color=GRAY_DARK)
        self.kids = wb.style(border=border, fill=GRAY_L4)


def _table(sheet, styles, row, headers, rows, widths=None, center_cols=(), link_col=None):
    for col, head in enumerate(headers, start=1):
        sheet.set(row, col, head, styles.th)
    header_row = row
    row += 1
    for idx, values in enumerate(rows):
        alt = idx % 2 == 1
        for col, value in enumerate(values, start=1):
            if link_col and col == link_col and isinstance(value, tuple):
                text, location = value
                sheet.set(row, col, text, styles.link)
                sheet.link(row, col, location, text)
                continue
            if col in center_cols:
                style = styles.td_center_alt if alt else styles.td_center
            else:
                style = styles.td_alt if alt else styles.td
            sheet.set(row, col, value, style)
        row += 1
    if widths:
        for col, width in enumerate(widths, start=1):
            sheet.col_widths[col] = width
    return header_row, row


def render_guide_xlsx(plan, rmeta, path):
    info = plan.info
    wb = Workbook(font_name="Meiryo UI", font_size=10, default_row_height=14.4)
    wb.title = "%s docker コマンド解説" % info["project"]
    wb.creator = "%s %s" % (TOOL_NAME, __version__)
    st = _Styles(wb)

    cover = wb.add_sheet("表紙", tab_color=GRAY_DARK)
    overview = wb.add_sheet("実行手順一覧", tab_color=GRAY_DARK)
    detail = wb.add_sheet("手順ごとの解説", tab_color=GRAY_DARK)
    options = wb.add_sheet("オプション解説", tab_color=GRAY_MID)
    script = wb.add_sheet("コマンド全文", tab_color=GRAY_MID)
    down = wb.add_sheet("後片付け", tab_color=GRAY_MID)
    mapping = wb.add_sheet("compose対応表", tab_color=GRAY)
    deep = wb.add_sheet("しくみの深掘り", tab_color=GRAY)
    glossary = wb.add_sheet("用語集", tab_color="7F7F7F")
    timeline = wb.add_sheet("歴史年表", tab_color="7F7F7F")
    caution = wb.add_sheet("注意・制限事項", tab_color="7F7F7F")
    prep = wb.add_sheet("RHEL9.8の準備", tab_color="A6A6A6")

    # ---- 手順ごとの解説 (先に作って行番号を知る) --------------------------------
    detail.col_widths = {1: 9, 2: 22, 3: 124}
    detail.freeze = (3, 1)
    detail.set(1, 1, "手順ごとの詳しい解説 (%s)" % info["project"], st.title)
    detail.row_heights[1] = 30
    detail.set(2, 1, "STEP", st.th)
    detail.set(2, 2, "項目", st.th)
    detail.set(2, 3, "内容　(※ Meiryo UI では、行の続きを表す \\ が ¥ と表示されますが、同じ文字です)", st.th)
    detail.repeat_rows = (2, 2)
    step_rows = {}
    option_first_rows = {}
    row = 3
    # オプション解説シートは先に行番号を決める
    opt_row = 3
    option_rows_by_step = {}
    for step in plan.steps:
        rows = step_option_rows(step)
        option_rows_by_step[step.no] = rows
        if rows:
            option_first_rows[step.no] = opt_row
            opt_row += len(rows)
    for step in plan.steps:
        ckey = command_key(step)
        kb = COMMANDS.get(ckey, {})
        step_rows[step.no] = row
        detail.set(row, 1, "STEP %d" % step.no, st.step_head_center)
        detail.set(row, 2, step.phase, st.step_head)
        detail.set(row, 3, step.title, st.step_head)
        detail.row_heights[row] = 22
        row += 1
        items = [
            ("使うコマンド", "%s\n%s" % (kb.get("title", ckey), kb.get("oneline", "")), st.td),
            ("compose の対応箇所", step.compose_ref or "-", st.td),
            ("実行するコマンド", step.script, st.code),
            ("実行のしかた", kb.get("how", ""), st.td),
            ("このコマンドがすること", step_does(step), st.td),
        ]
        opts = option_rows_by_step.get(step.no) or []
        if opts:
            flags = []
            for item in opts:
                if item["option"] not in flags:
                    flags.append(item["option"])
            items.append(("オプション・引数の意味", "このステップで使っているオプション・引数 (%d 個): %s\n→ くわしい説明は「オプション解説」シート (右のリンク) を見てください。" % (
                len(opts), "、".join(flags)), st.td))
        items += [
            ("しくみ (動作原理)", kb.get("principle", ""), st.td),
            ("動作イメージ (たとえ話)", kb.get("image", ""), st.td),
            ("歴史と背景・必要になった経緯", kb.get("history", ""), st.td),
            ("小学生向けのまとめ", kb.get("kids", ""), st.kids),
            ("RHEL 9.8 での注意", kb.get("rhel", ""), st.td),
        ]
        if step.notes:
            items.append(("この STEP の注意", "\n".join("・" + n for n in step.notes), st.warn))
        if step.verify:
            items.append(("確認のしかた", "\n".join(step.verify), st.code))
        if step.compose_snippet:
            items.append(("compose での書き方 (正規化後)", step.compose_snippet, st.code))
        for label, text, style in items:
            chunks = _split_long(text)
            for idx, chunk in enumerate(chunks):
                detail.set(row, 1, "", st.td)
                detail.set(row, 2, label if idx == 0 else label + " (つづき)", st.label)
                detail.set(row, 3, chunk, style)
                if label == "オプション・引数の意味" and step.no in option_first_rows:
                    detail.link(row, 3, "'オプション解説'!A%d" % option_first_rows[step.no], "オプション解説へ")
                row += 1
        row += 1
    detail.max_col = 3

    # ---- オプション解説 -----------------------------------------------------
    options.col_widths = {1: 8, 2: 21, 3: 24, 4: 34, 5: 32, 6: 42, 7: 62, 8: 34}
    options.set(1, 1, "オプション・引数の解説 (%s)" % info["project"], st.title)
    options.row_heights[1] = 30
    headers = ["STEP", "コマンド", "オプション", "値", "compose の設定", "このステップでの意味", "オプションのしくみ", "やさしい説明 (小学生向け)"]
    table_rows = []
    for step in plan.steps:
        for item in option_rows_by_step.get(step.no) or []:
            table_rows.append([step.no, item["command"], item["option"], item["value"], item["compose"], item["here"],
                               item["meaning"] if not item["dup"] else "(同じオプションの説明は上の行を参照)", item["kids"] if not item["dup"] else ""])
    head_row, end_row = _table(options, st, 2, headers, table_rows, center_cols=(1,))
    options.freeze = (3, 4)
    options.autofilter = "A2:H%d" % max(end_row - 1, 2)
    options.repeat_rows = (2, 2)

    # ---- 実行手順一覧 -------------------------------------------------------
    overview.set(1, 1, "実行手順一覧 (%s)" % info["project"], st.title)
    overview.row_heights[1] = 30
    overview.set(2, 1, "上から順番に実行します。「解説」のリンクで、各 STEP の詳しい説明へ移動できます。", st.subtitle)
    headers = ["STEP", "区分", "やること", "対象", "compose の対応箇所", "概要", "解説"]
    rows = []
    for step in plan.steps:
        rows.append([step.no, step.phase, step.title, step.target or "-", step.compose_ref or "-", step.summary,
                     ("開く", "'手順ごとの解説'!A%d" % step_rows[step.no])])
    head_row, end_row = _table(overview, st, 3, headers, rows, widths=[7, 18, 46, 30, 30, 76, 8], center_cols=(1,), link_col=7)
    overview.freeze = (4, 1)
    overview.autofilter = "A3:G%d" % (end_row - 1)
    overview.repeat_rows = (3, 3)

    # ---- コマンド全文 -------------------------------------------------------
    from .render_cmds import render_up_txt
    text = render_up_txt(plan, rmeta)
    script.col_widths = {1: 7, 2: 150}
    script.set(1, 1, "コマンド全文 (%s と同じ内容)" % rmeta["names"]["up_txt"], st.title)
    script.row_heights[1] = 30
    script.set(2, 1, "行", st.th)
    script.set(2, 2, "内容 (# で始まる行はコメント = 説明。実行されません)　※ Meiryo UI では \\ が ¥ と表示されますが、同じ文字です", st.th)
    script.freeze = (3, 1)
    script.repeat_rows = (2, 2)
    row = 3
    for lineno, line in enumerate(text.rstrip("\n").split("\n"), start=1):
        script.set(row, 1, lineno, st.muted)
        if line.startswith("# STEP"):
            style = st.comment_bold
        elif line.startswith("#"):
            style = st.comment
        elif line.strip() == "":
            style = st.text
        else:
            style = st.code_plain
        script.set(row, 2, line, style)
        row += 1

    # ---- 後片付け -----------------------------------------------------------
    down.set(1, 1, "後片付けの手順 (docker compose down と同じ)", st.title)
    down.row_heights[1] = 30
    down.set(2, 1, "%s と同じ内容です。起動と逆の順番で止めて削除します。ボリュームとイメージの削除は、必要なときだけ # を外して実行します。" % rmeta["names"]["down_txt"], st.subtitle)
    rows = []
    for step in plan.down_steps:
        kb = COMMANDS.get(command_key(step), {})
        rows.append([step.no, step.title, step.script, step.summary + "\n" + kb.get("meaning", ""), kb.get("kids", "")])
    _table(down, st, 3, ["No", "やること", "コマンド", "意味・しくみ", "小学生向け"], rows, widths=[6, 34, 60, 70, 40], center_cols=(1,))
    down.freeze = (4, 1)

    # ---- compose 対応表 ------------------------------------------------------
    mapping.set(1, 1, "compose の設定と docker オプションの対応表", st.title)
    mapping.row_heights[1] = 30
    mapping.set(2, 1, "このプロジェクトでの対応", st.band)
    rows = [[r["service"], r["container"], r["compose"], r["docker"], r["value"], r["note"]] for r in plan.mapping_rows]
    head_row, end_row = _table(mapping, st, 3, ["サービス", "コンテナ", "compose の設定", "docker のオプション", "値", "意味"], rows,
                               widths=[18, 26, 34, 22, 40, 70])
    mapping.autofilter = "A3:F%d" % max(end_row - 1, 3)
    mapping.freeze = (4, 1)
    row = end_row + 1
    mapping.set(row, 1, "一般的な対応", st.band)
    row += 1
    _table(mapping, st, row, ["compose の設定", "docker コマンド", "補足"], [list(r) for r in GENERIC_MAPPING])

    # ---- しくみの深掘り -------------------------------------------------------
    deep.col_widths = {1: 26, 2: 130}
    deep.set(1, 1, "コマンドの種類ごとの深掘り解説", st.title)
    deep.row_heights[1] = 30
    row = 2
    for ckey in _used_commands(plan):
        kb = COMMANDS.get(ckey)
        if not kb:
            continue
        deep.set(row, 1, kb["title"], st.step_head)
        deep.set(row, 2, "", st.step_head)
        deep.row_heights[row] = 22
        row += 1
        for label, key, style in (("書き方", "syntax", st.code), ("ひとことで", "oneline", st.td), ("実行のしかた", "how", st.td),
                                  ("意味", "meaning", st.td), ("しくみ (動作原理)", "principle", st.td),
                                  ("動作イメージ (たとえ話)", "image", st.td), ("歴史と背景・必要になった経緯", "history", st.td),
                                  ("小学生向けのまとめ", "kids", st.kids), ("RHEL 9.8 での注意", "rhel", st.td)):
            for idx, chunk in enumerate(_split_long(kb.get(key, ""), 130)):
                deep.set(row, 1, label if idx == 0 else label + " (つづき)", st.label)
                deep.set(row, 2, chunk, style)
                row += 1
        row += 1

    # ---- 用語集 / 年表 -------------------------------------------------------
    glossary.set(1, 1, "用語集", st.title)
    glossary.row_heights[1] = 30
    head_row, end_row = _table(glossary, st, 2, ["用語", "読み・英語", "意味", "小学生向けのたとえ"], [list(g) for g in GLOSSARY], widths=[26, 26, 80, 52])
    glossary.freeze = (3, 2)
    glossary.autofilter = "A2:D%d" % (end_row - 1)
    glossary.repeat_rows = (2, 2)
    timeline.set(1, 1, "歴史年表 (コンテナ技術・Docker・Compose・RHEL)", st.title)
    timeline.row_heights[1] = 30
    head_row, end_row = _table(timeline, st, 2, ["時期", "出来事", "何が変わったか"], [list(t) for t in TIMELINE], widths=[18, 56, 90])
    timeline.freeze = (3, 1)
    timeline.repeat_rows = (2, 2)

    # ---- 注意・制限事項 -----------------------------------------------------
    caution.col_widths = {1: 30, 2: 130}
    caution.set(1, 1, "注意点・制限事項", st.title)
    caution.row_heights[1] = 30
    row = 2
    caution.set(row, 1, "このプロジェクトの変換メモ", st.band)
    caution.set(row, 2, "", st.band)
    row += 1
    notes = [("変換時の注意", w) for w in plan.warnings]
    for step in plan.steps:
        for note in step.notes:
            notes.append(("STEP %d" % step.no, note))
    if not notes:
        notes = [("-", "特にありません。")]
    for head, text in notes:
        caution.set(row, 1, head, st.label)
        caution.set(row, 2, text, st.td)
        row += 1
    row += 1
    caution.set(row, 1, "docker コマンドに直すときの一般的な注意", st.band)
    caution.set(row, 2, "", st.band)
    row += 1
    for head, text in LIMITATIONS:
        caution.set(row, 1, head, st.label)
        caution.set(row, 2, text, st.td)
        row += 1
    row += 1
    caution.set(row, 1, "RHEL 9.8 で気をつけること", st.band)
    caution.set(row, 2, "", st.band)
    row += 1
    for head, text in RHEL_NOTES:
        caution.set(row, 1, head, st.label)
        caution.set(row, 2, text, st.td)
        row += 1

    # ---- RHEL 9.8 の準備 ----------------------------------------------------
    prep.set(1, 1, "RHEL 9.8 に Docker Engine を準備する手順", st.title)
    prep.row_heights[1] = 30
    prep.set(2, 1, "この資料のコマンドを実行する前に、一度だけ行う準備です (Docker 公式手順 docs.docker.com/engine/install/rhel/ に基づく)。", st.subtitle)
    rows = [[head, cmds, text] for head, cmds, text in RHEL_SETUP]
    _table(prep, st, 3, ["やること", "コマンド", "説明"], rows, widths=[30, 80, 70])

    # ---- 表紙 -------------------------------------------------------------
    cover.col_widths = {1: 3, 2: 26, 3: 120}
    cover.set(1, 2, "%s を docker コマンドだけで動かす ― 実行手順と詳しい解説" % info["project"], st.title)
    cover.row_heights[1] = 36
    cover.set(2, 2, "%s %s で自動生成 ／ 生成日時 %s" % (TOOL_NAME, __version__, rmeta.get("generated_at", "")), st.subtitle)
    row = 4
    cover.set(row, 2, "概要", st.band)
    cover.set(row, 3, "", st.band)
    row += 1
    facts = [
        ("プロジェクト名", info["project"]),
        ("元の compose ファイル", "\n".join(rmeta.get("files") or [])),
        ("読み込み方法", rmeta.get("loader_label", "")),
        ("実行環境", "RHEL 9.8 + Docker Engine (docker-ce)。docker run の複数ネットワーク指定のため Docker Engine 25 以降、推奨は最新の 29.x"),
        ("表示についての注意", "この Excel は Meiryo UI で表示しているため、コマンドの行の最後にある \\ (バックスラッシュ = 「次の行に続く」という印) が ¥ (円マーク) に見えます。"
                             "これは日本語フォントの昔からの決まりで、文字そのものは \\ です。コピーしてそのまま使えますが、貼り付けるときは txt ファイルからコピーするのが確実です。"),
        ("サービス (起動順)", " → ".join(info["services"])),
        ("コンテナ", "、".join(c for s in info["services"] for c in info["containers"][s])),
        ("手順の数", "起動 %d STEP ／ 片付け %d STEP" % (len(plan.steps), len(plan.down_steps))),
        ("実行用ファイル", "%s (貼り付け・bash 実行用)\n%s (Markdown 版)\n%s (片付け用)" % (
            rmeta["names"]["up_txt"], rmeta["names"]["md"], rmeta["names"]["down_txt"])),
    ]
    for label, value in facts:
        cover.set(row, 2, label, st.label)
        cover.set(row, 3, value, st.td)
        row += 1
    row += 1
    cover.set(row, 2, "はじめに", st.band)
    cover.set(row, 3, "", st.band)
    row += 1
    for head, text in INTRO:
        cover.set(row, 2, head, st.label)
        cover.set(row, 3, text, st.kids if head.startswith("小学生") else st.td)
        row += 1
    row += 1
    cover.set(row, 2, "しくみの全体像", st.band)
    cover.set(row, 3, "", st.band)
    row += 1
    cover.set(row, 2, "図", st.label)
    cover.set(row, 3, _architecture_diagram(), st.code)
    row += 1
    for idx, chunk in enumerate(_split_long(ARCHITECTURE, 120)):
        cover.set(row, 2, "説明" if idx == 0 else "説明 (つづき)", st.label)
        cover.set(row, 3, chunk, st.td)
        row += 1
    row += 1
    cover.set(row, 2, "実行の流れ", st.band)
    cover.set(row, 3, "", st.band)
    row += 1
    groups = _phase_groups(plan)
    for phase, text in PHASES:
        steps = groups.get(phase, [])
        cover.set(row, 2, phase, st.label)
        cover.set(row, 3, "%s\n(この手順: %s)" % (text, ("STEP " + "・".join(str(s) for s in steps)) if steps else "なし"), st.td)
        row += 1
    row += 1
    cover.set(row, 2, "シートの案内", st.band)
    cover.set(row, 3, "", st.band)
    row += 1
    guide = [
        ("実行手順一覧", "全 STEP の一覧。どの順番で何をするかが 1 枚でわかります。"),
        ("手順ごとの解説", "STEP ごとに、コマンド・実行のしかた・意味・しくみ・たとえ話・歴史・小学生向けまとめ・RHEL の注意を説明します。"),
        ("オプション解説", "コマンドのオプション 1 つ 1 つの意味 (compose のどの設定から来たか) を説明します。"),
        ("コマンド全文", "実行用の txt ファイルと同じ内容です。"),
        ("後片付け", "compose down と同じ片付けの手順です。"),
        ("compose対応表", "compose の設定と docker オプションの対応表です。"),
        ("しくみの深掘り", "コマンドの種類ごとの詳しい説明 (辞書として使えます)。"),
        ("用語集", "出てくる用語の意味と、小学生向けのたとえです。"),
        ("歴史年表", "chroot (1979 年) から Docker / Compose / RHEL の最新版までの流れです。"),
        ("注意・制限事項", "このプロジェクトの変換メモと、docker コマンドに直すときの注意点です。"),
        ("RHEL9.8の準備", "RHEL 9.8 に Docker Engine を入れる手順です。"),
    ]
    for name, text in guide:
        cover.set(row, 2, name, st.link_plain)
        cover.link(row, 2, "'%s'!A1" % name, name)
        cover.set(row, 3, text, st.td)
        row += 1
    if plan.warnings:
        row += 1
        cover.set(row, 2, "変換時の注意", st.band)
        cover.set(row, 3, "", st.band)
        row += 1
        for warning in plan.warnings:
            cover.set(row, 2, "注意", st.warn)
            cover.set(row, 3, warning, st.td)
            row += 1
    cover.landscape = True

    wb.save(path)
