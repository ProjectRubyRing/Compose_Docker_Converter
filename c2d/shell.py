"""bash にそのまま貼り付けられるコマンド文字列を作るための部品。

* 値は必要なときだけクォートする (読みやすさのため)
* ``!`` を含む値は必ずシングルクォート (履歴展開の事故を防ぐ)
* 改行・タブなどの制御文字は ``$'...'`` 形式で表す (貼り付け時のタブ補完を防ぐ)
"""

import re

__all__ = ["Raw", "quote", "concat", "render_command", "heredoc"]

_SAFE = re.compile(r"^[A-Za-z0-9_@%+=:,./-]+$")


class Raw(str):
    """クォート済み (またはクォート不要) のシェル文字列。"""


def _ansi_c(text):
    out = []
    for ch in text:
        code = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == "'":
            out.append("\\'")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif code < 0x20 or code == 0x7F:
            out.append("\\x%02x" % code)
        else:
            out.append(ch)
    return "$'" + "".join(out) + "'"


def quote(value):
    """値を bash の 1 単語として安全に表す。"""
    if isinstance(value, Raw):
        return str(value)
    text = "" if value is None else str(value)
    if text == "":
        return "''"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        return _ansi_c(text)
    if _SAFE.match(text) and not text.startswith("~"):
        return text
    if "'" not in text:
        return "'" + text + "'"
    if not any(ch in text for ch in '"$`\\!'):
        return '"' + text + '"'
    # ' と $ などが両方入るときは $'...' 形式 (\' と書ける) にして読みやすくする
    return _ansi_c(text)


def concat(*parts):
    """Raw と通常の文字列をつないで 1 単語にする (例: "$PWD"/conf:/etc/app)。"""
    out = []
    for part in parts:
        if part is None or part == "":
            continue
        out.append(quote(part) if not isinstance(part, Raw) else str(part))
    return Raw("".join(out))


def render_command(head, lines, tail=None):
    """``docker run \\`` のように 1 行 1 オプションで改行したコマンドを作る。"""
    rows = [head] + ["  " + line for line in lines]
    if tail:
        rows += ["  " + line for line in tail]
    if len(rows) == 1:
        return rows[0]
    return " \\\n".join(rows)


def heredoc(command, body, delimiter="C2D_EOF"):
    """``command <<'C2D_EOF'`` 形式のヒアドキュメント (中身は展開されない)。"""
    while delimiter in body.split("\n"):
        delimiter += "_"
    if not body.endswith("\n"):
        body += "\n"
    return "%s <<'%s'\n%s%s" % (command, delimiter, body, delimiter)
