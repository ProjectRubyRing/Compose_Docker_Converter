"""compose ファイルを読むための YAML パーサ (標準ライブラリのみ)。

docker compose (compose-go) が内部で使う go-yaml v3 の解釈に合わせています。

* ブロック形式 / フロー形式のマッピング・シーケンス
* プレーン / シングルクォート / ダブルクォート (複数行を含む)
* ブロックスカラー ``|`` ``>`` (チョンプ指定 ``-`` ``+``・インデント指定)
* アンカー ``&`` / エイリアス ``*`` / マージキー ``<<``
* タグ (``!reset`` ``!override`` などは :class:`Tagged` として保持)
* 真偽値は ``true`` / ``false`` のみ (YAML 1.2。``yes`` / ``no`` は文字列)
* ``0755`` のような先頭 0 の整数は 8 進数 (go-yaml v3 の互換動作)
"""

import copy
import re

__all__ = ["YamlError", "Tagged", "YInt", "YFloat", "loads", "load_file"]


class YamlError(ValueError):
    """YAML の書式エラー。"""

    def __init__(self, message, line=None, filename=None):
        self.line = line
        self.filename = filename
        where = []
        if filename:
            where.append(str(filename))
        if line is not None:
            where.append("%d 行目" % line)
        if where:
            message = "%s (%s)" % (message, " ".join(where))
        super().__init__(message)


class Tagged:
    """``!reset`` などのタグが付いた値。"""

    __slots__ = ("tag", "value")

    def __init__(self, tag, value):
        self.tag = tag
        self.value = value

    def __repr__(self):
        return "Tagged(%r, %r)" % (self.tag, self.value)

    def __eq__(self, other):
        return isinstance(other, Tagged) and other.tag == self.tag and other.value == self.value

    def __deepcopy__(self, memo):
        return Tagged(self.tag, copy.deepcopy(self.value, memo))


class YInt(int):
    """元の表記 (``src``) を覚えている整数。"""

    def __new__(cls, value, src=None):
        obj = int.__new__(cls, value)
        obj.src = src if src is not None else str(int(value))
        return obj

    def __getnewargs__(self):
        return (int(self), self.src)


class YFloat(float):
    """元の表記 (``src``) を覚えている浮動小数点数。"""

    def __new__(cls, value, src=None):
        obj = float.__new__(cls, value)
        obj.src = src if src is not None else repr(float(value))
        return obj

    def __getnewargs__(self):
        return (float(self), self.src)


# ---------------------------------------------------------------------------
# スカラーの型解決 (go-yaml v3 resolve.go 相当)
# ---------------------------------------------------------------------------
_NULLS = {"", "~", "null", "Null", "NULL"}
_TRUES = {"true", "True", "TRUE"}
_FALSES = {"false", "False", "FALSE"}
_POS_INF = {".inf", ".Inf", ".INF", "+.inf", "+.Inf", "+.INF"}
_NEG_INF = {"-.inf", "-.Inf", "-.INF"}
_NANS = {".nan", ".NaN", ".NAN"}
_FLOAT_RE = re.compile(r"^[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?$")
_DIGITS = {
    2: set("01"),
    8: set("01234567"),
    10: set("0123456789"),
    16: set("0123456789abcdefABCDEF"),
}


def _go_parse_int(text):
    """Go の ``strconv.ParseInt(s, 0, 64)`` (失敗時は ParseUint) 相当。"""
    if not text:
        return None
    sign = 1
    body = text
    if body[0] in "+-":
        if body[0] == "-":
            sign = -1
        body = body[1:]
    if not body:
        return None
    low = body.lower()
    if low.startswith("0x"):
        base, digits = 16, body[2:]
    elif low.startswith("0o"):
        base, digits = 8, body[2:]
    elif low.startswith("0b"):
        base, digits = 2, body[2:]
    elif len(body) > 1 and body[0] == "0":
        base, digits = 8, body[1:]
    else:
        base, digits = 10, body
    if not digits or any(ch not in _DIGITS[base] for ch in digits):
        return None
    value = sign * int(digits, base)
    if -(2 ** 63) <= value < 2 ** 63:
        return value
    if 0 <= value < 2 ** 64:
        return value
    return None


def resolve_plain(text):
    """プレーンスカラーの文字列を Python の値へ変換する。"""
    if text in _NULLS:
        return None
    if text in _TRUES:
        return True
    if text in _FALSES:
        return False
    if text in _POS_INF:
        return YFloat(float("inf"), text)
    if text in _NEG_INF:
        return YFloat(float("-inf"), text)
    if text in _NANS:
        return YFloat(float("nan"), text)
    if text and (text[0].isdigit() or text[0] in "+-."):
        plain = text.replace("_", "")
        value = _go_parse_int(plain)
        if value is not None:
            return YInt(value, text)
        if _FLOAT_RE.match(plain):
            try:
                return YFloat(float(plain), text)
            except ValueError:
                pass
    return text


def _resolve_tagged_plain(tag, text):
    if tag == "!!str":
        return text
    if tag == "!!int":
        value = _go_parse_int(text.replace("_", ""))
        return YInt(value, text) if value is not None else text
    if tag == "!!float":
        try:
            return YFloat(float(text), text)
        except ValueError:
            return text
    if tag == "!!bool":
        return text in _TRUES
    if tag == "!!null":
        return None
    return resolve_plain(text)


_STANDARD_TAGS = {"!!str", "!!int", "!!float", "!!bool", "!!null", "!!map", "!!seq", "!!binary", "!!timestamp"}

_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
    "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
    "N": "\x85", "_": "\xa0", "L": " ", "P": " ",
}
_HEX_LEN = {"x": 2, "u": 4, "U": 8}


def _strip_plain_comment(text):
    """プレーンスカラー行から `` #`` 以降のコメントを取り除く。"""
    if text.startswith("#"):
        return ""
    for idx in range(1, len(text)):
        if text[idx] == "#" and text[idx - 1] in " \t":
            return text[:idx]
    return text


def _is_seq_item(content):
    return content == "-" or content.startswith("- ") or content.startswith("-\t")


def _find_quote_end(text, start):
    """``text[start]`` から始まるクォート文字列の閉じ位置 (1 行内) を返す。"""
    quote = text[start]
    idx = start + 1
    while idx < len(text):
        ch = text[idx]
        if quote == "'":
            if ch == "'":
                if idx + 1 < len(text) and text[idx + 1] == "'":
                    idx += 2
                    continue
                return idx
        else:
            if ch == "\\":
                idx += 2
                continue
            if ch == '"':
                return idx
        idx += 1
    return -1


def _find_map_colon(content):
    """``key: value`` の ``:`` の位置を返す (マッピングでなければ -1)。"""
    if not content:
        return -1
    first = content[0]
    if first in "\"'":
        end = _find_quote_end(content, 0)
        if end < 0:
            return -1
        idx = end + 1
        while idx < len(content) and content[idx] in " \t":
            idx += 1
        if idx < len(content) and content[idx] == ":" and (idx + 1 == len(content) or content[idx + 1] in " \t"):
            return idx
        return -1
    if first in "[{|>#*&!%@`":
        return -1
    for idx, ch in enumerate(content):
        if ch == "#" and idx > 0 and content[idx - 1] in " \t":
            return -1
        if ch == ":" and (idx + 1 == len(content) or content[idx + 1] in " \t"):
            return idx
    return -1


class _Cursor:
    """複数行にまたがるフロー / クォートを読むための文字カーソル。"""

    __slots__ = ("lines", "i", "c")

    def __init__(self, lines, i, c):
        self.lines = lines
        self.i = i
        self.c = c

    def peek(self, ahead=0):
        i, c = self.i, self.c + ahead
        while i < len(self.lines):
            line = self.lines[i]
            if c < len(line):
                return line[c]
            if c == len(line):
                return "\n" if i + 1 < len(self.lines) else ""
            c -= len(line) + 1
            i += 1
        return ""

    def advance(self):
        line = self.lines[self.i]
        if self.c < len(line):
            self.c += 1
        else:
            self.i += 1
            self.c = 0

    def skip_ws(self):
        """空白・改行・コメントを読み飛ばす (フロー形式用)。"""
        while True:
            ch = self.peek()
            if ch in (" ", "\t", "\n"):
                self.advance()
                continue
            if ch == "#":
                line = self.lines[self.i]
                if self.c == 0 or line[self.c - 1] in " \t":
                    self.c = len(line)
                    continue
            return


class _Parser:
    def __init__(self, text, filename=None):
        if text.startswith("﻿"):
            text = text[1:]
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.lines = text.split("\n")
        self.n = len(self.lines)
        self.i = 0
        self.anchors = {}
        self.filename = filename

    # ------------------------------------------------------------------
    def error(self, message, index=None):
        line = (self.i if index is None else index) + 1
        return YamlError(message, line=line, filename=self.filename)

    @staticmethod
    def _indent(line):
        return len(line) - len(line.lstrip(" "))

    @staticmethod
    def _blank(line):
        stripped = line.strip()
        return stripped == "" or stripped.startswith("#")

    @staticmethod
    def _is_doc_marker(line):
        return (line.startswith("---") or line.startswith("...")) and (len(line) == 3 or line[3] in " \t")

    def _skip_blank(self):
        while self.i < self.n and self._blank(self.lines[self.i]):
            self.i += 1

    def _check_tabs(self, line, indent):
        if indent < len(line) and line[indent] == "\t":
            raise self.error("インデントにタブ文字は使えません (スペースで字下げしてください)")

    # ------------------------------------------------------------------
    def parse(self):
        while self.i < self.n:
            line = self.lines[self.i]
            stripped = line.strip()
            if stripped == "" or stripped.startswith("#") or line.startswith("%"):
                self.i += 1
                continue
            if line.startswith("---") and (len(line) == 3 or line[3] in " \t"):
                rest = line[3:].strip()
                if rest == "" or rest.startswith("#"):
                    self.i += 1
                    continue
                self.lines[self.i] = rest
            break
        if self.i >= self.n:
            return None
        line = self.lines[self.i]
        if line.startswith("..."):
            return None
        indent = self._indent(line)
        self._check_tabs(line, indent)
        value = self._parse_node_at(indent)
        self._skip_blank()
        if self.i < self.n and not self._is_doc_marker(self.lines[self.i]):
            raise self.error("この行を解釈できません: %r" % self.lines[self.i].strip())
        return value

    # ------------------------------------------------------------------
    def _parse_node_at(self, indent):
        line = self.lines[self.i]
        content = line[indent:]
        if _is_seq_item(content):
            return self._parse_sequence(indent)
        if content[:1] in ("&", "!"):
            # 「&anchor」だけの行の下にブロックが続く形
            text = content
            anchor, tag, text = self._take_props(text)
            if _strip_plain_comment(text).strip() == "":
                self.i += 1
                value = self._parse_nested_block(indent - 1, allow_same_indent_seq=False)
                return self._finish_props(value, anchor, tag)
            if _find_map_colon(text) >= 0:
                col = indent + (len(content) - len(text))
                self.lines[self.i] = " " * col + text
                value = self._parse_mapping(col)
                return self._finish_props(value, anchor, tag)
        if _find_map_colon(content) >= 0:
            return self._parse_mapping(indent)
        return self._parse_value(content, indent - 1, indent)

    def _parse_nested_block(self, parent_indent, allow_same_indent_seq):
        self._skip_blank()
        if self.i >= self.n:
            return None
        line = self.lines[self.i]
        if self._is_doc_marker(line):
            return None
        indent = self._indent(line)
        self._check_tabs(line, indent)
        content = line[indent:]
        if indent > parent_indent:
            return self._parse_node_at(indent)
        if allow_same_indent_seq and indent == parent_indent and _is_seq_item(content):
            return self._parse_sequence(indent)
        return None

    def _parse_mapping(self, indent):
        result = {}
        merges = []
        while True:
            self._skip_blank()
            if self.i >= self.n:
                break
            line = self.lines[self.i]
            if self._is_doc_marker(line):
                break
            cur = self._indent(line)
            if cur < indent:
                break
            self._check_tabs(line, cur)
            if cur > indent:
                raise self.error("インデント (字下げ) の位置が合っていません")
            content = line[cur:]
            if _is_seq_item(content):
                break
            colon = _find_map_colon(content)
            if colon < 0:
                raise self.error("「キー: 値」の形になっていません: %r" % content.strip())
            key = self._key_text(content[:colon])
            value = self._parse_value(content[colon + 1:], indent, cur + colon + 1, mapping_value=True)
            if key == "<<":
                merges.append(value)
                continue
            if key in result:
                raise self.error("キー %r が同じ階層に 2 回書かれています" % key)
            result[key] = value
        for source in merges:
            items = source if isinstance(source, list) else [source]
            for item in items:
                if isinstance(item, Tagged):
                    item = item.value
                if not isinstance(item, dict):
                    raise self.error("<< (マージキー) にはマッピングを指定してください")
                for key, val in item.items():
                    if key not in result:
                        result[key] = copy.deepcopy(val)
        return result

    def _key_text(self, raw):
        raw = raw.rstrip(" \t")
        if raw[:1] in ("'", '"'):
            cursor = _Cursor([raw], 0, 0)
            return self._read_quoted(cursor)
        return raw

    def _parse_sequence(self, indent):
        result = []
        while True:
            self._skip_blank()
            if self.i >= self.n:
                break
            line = self.lines[self.i]
            if self._is_doc_marker(line):
                break
            cur = self._indent(line)
            if cur < indent:
                break
            self._check_tabs(line, cur)
            if cur > indent:
                raise self.error("インデント (字下げ) の位置が合っていません")
            content = line[cur:]
            if not _is_seq_item(content):
                break
            after = content[1:]
            text = after.lstrip(" \t")
            col = cur + 1 + (len(after) - len(text))
            if text == "" or text.startswith("#"):
                self.i += 1
                result.append(self._parse_nested_block(indent, allow_same_indent_seq=False))
                continue
            if _is_seq_item(text) or _find_map_colon(text) >= 0:
                self.lines[self.i] = " " * col + text
                result.append(self._parse_node_at(col))
                continue
            if text[0] in "&!":
                anchor, tag, rest = self._take_props(text)
                if rest and (_is_seq_item(rest) or _find_map_colon(rest) >= 0):
                    col2 = col + (len(text) - len(rest))
                    self.lines[self.i] = " " * col2 + rest
                    value = self._parse_node_at(col2)
                    result.append(self._finish_props(value, anchor, tag))
                    continue
            result.append(self._parse_value(after, indent, cur + 1))
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _take_props(text):
        anchor = None
        tag = None
        while text and text[0] in "&!":
            match = re.match(r"([&!][^\s,\[\]{}]*)[ \t]*", text)
            token = match.group(1)
            if token[0] == "&":
                anchor = token[1:]
            else:
                tag = token
            text = text[match.end():]
        return anchor, tag, text

    def _finish_props(self, value, anchor, tag):
        if tag and tag not in _STANDARD_TAGS:
            value = Tagged(tag, value)
        if anchor is not None:
            self.anchors[anchor] = value
        return value

    def _parse_value(self, rest, parent_indent, col, mapping_value=False):
        """``key:`` / ``-`` の後ろ (同じ行) から値を読む。"""
        text = rest.lstrip(" \t")
        col += len(rest) - len(text)
        anchor, tag, stripped = self._take_props(text)
        col += len(text) - len(stripped)
        text = stripped
        if text == "" or text.startswith("#"):
            self.i += 1
            value = self._parse_nested_block(parent_indent, allow_same_indent_seq=mapping_value)
        elif text[0] == "*":
            name = _strip_plain_comment(text[1:]).strip()
            if name not in self.anchors:
                raise self.error("エイリアス *%s に対応するアンカー &%s がありません" % (name, name))
            value = copy.deepcopy(self.anchors[name])
            self.i += 1
        elif text[0] in "|>":
            value = self._parse_block_scalar(text, parent_indent)
        elif text[0] in "[{":
            cursor = _Cursor(self.lines, self.i, col)
            value = self._flow_node(cursor)
            self._finish_line(cursor)
        elif text[0] in "\"'":
            cursor = _Cursor(self.lines, self.i, col)
            value = self._read_quoted(cursor)
            self._finish_line(cursor)
        else:
            raw = self._parse_plain_multiline(text, parent_indent)
            value = _resolve_tagged_plain(tag, raw) if tag in _STANDARD_TAGS else resolve_plain(raw)
        return self._finish_props(value, anchor, tag)

    def _finish_line(self, cursor):
        line = self.lines[cursor.i]
        rest = line[cursor.c:]
        stripped = rest.strip()
        if stripped and not stripped.startswith("#"):
            raise self.error("値の後ろに余分な文字があります: %r" % stripped, cursor.i)
        self.i = cursor.i + 1

    def _parse_plain_multiline(self, text, parent_indent):
        first = _strip_plain_comment(text)
        had_comment = first != text
        parts = [first.rstrip()]
        self.i += 1
        if had_comment:
            return parts[0]
        newlines = 0
        while self.i < self.n:
            line = self.lines[self.i]
            stripped = line.strip()
            if stripped == "":
                newlines += 1
                self.i += 1
                continue
            indent = self._indent(line)
            if indent <= parent_indent or stripped.startswith("#") or (indent == 0 and self._is_doc_marker(line)):
                break
            body = line[indent:]
            content = _strip_plain_comment(body)
            parts.append("\n" * newlines if newlines else " ")
            newlines = 0
            parts.append(content.strip())
            self.i += 1
            if content != body:
                break
        return "".join(parts)

    def _parse_block_scalar(self, header, parent_indent):
        match = re.match(r"^([|>])([+-]?)([1-9]?)([+-]?)[ \t]*(#.*)?$", header)
        if not match or (match.group(2) and match.group(4)):
            raise self.error("ブロックスカラーの指定 %r を解釈できません" % header)
        style = match.group(1)
        chomp = match.group(2) or match.group(4)
        explicit = match.group(3)
        self.i += 1
        if explicit:
            content_indent = max(parent_indent, 0) + int(explicit)
        else:
            content_indent = None
            j = self.i
            while j < self.n:
                if self.lines[j].strip() != "":
                    content_indent = self._indent(self.lines[j])
                    break
                j += 1
            if content_indent is not None and content_indent <= parent_indent:
                content_indent = None
        lines = []
        while self.i < self.n:
            line = self.lines[self.i]
            if line.strip() == "":
                if content_indent is not None and len(line) > content_indent:
                    lines.append(line[content_indent:])
                else:
                    lines.append("")
                self.i += 1
                continue
            if content_indent is None or self._indent(line) < content_indent:
                break
            lines.append(line[content_indent:])
            self.i += 1
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == "":
            end -= 1
        body = lines[:end]
        trailing = len(lines) - end
        if style == "|":
            text = "\n".join(body)
        else:
            text = self._fold(body)
        if not body:
            return "\n" * trailing if chomp == "+" else ""
        if chomp == "-":
            return text
        if chomp == "+":
            return text + "\n" + "\n" * trailing
        return text + "\n"

    @staticmethod
    def _fold(lines):
        def more_indented(value):
            return value[:1] in (" ", "\t")

        out = []
        for idx, line in enumerate(lines):
            if idx == 0:
                out.append(line if line != "" else "\n")
                continue
            prev = lines[idx - 1]
            if line == "":
                out.append("\n")
            elif prev == "":
                out.append(("\n" + line) if more_indented(line) else line)
            elif more_indented(prev) or more_indented(line):
                out.append("\n" + line)
            else:
                out.append(" " + line)
        return "".join(out)

    # ------------------------------------------------------------------
    # クォート文字列
    # ------------------------------------------------------------------
    def _read_quoted(self, cursor):
        quote = cursor.peek()
        cursor.advance()
        out = []
        while True:
            if cursor.i >= len(cursor.lines):
                raise self.error("クォート (%s) が閉じられていません" % quote, cursor.i - 1)
            line = cursor.lines[cursor.i]
            if cursor.c >= len(line):
                # 行末: 折り返し (空白 1 つ、または空行の数だけ改行) にする
                while out and out[-1] in (" ", "\t"):
                    out.pop()
                cursor.i += 1
                cursor.c = 0
                empties = 0
                while cursor.i < len(cursor.lines) and cursor.lines[cursor.i].strip() == "":
                    empties += 1
                    cursor.i += 1
                if cursor.i >= len(cursor.lines):
                    raise self.error("クォート (%s) が閉じられていません" % quote, cursor.i - 1)
                nxt = cursor.lines[cursor.i]
                cursor.c = len(nxt) - len(nxt.lstrip(" \t"))
                out.append("\n" * empties if empties else " ")
                continue
            ch = line[cursor.c]
            if quote == "'":
                if ch == "'":
                    if cursor.c + 1 < len(line) and line[cursor.c + 1] == "'":
                        out.append("'")
                        cursor.c += 2
                        continue
                    cursor.c += 1
                    return "".join(out)
                out.append(ch)
                cursor.c += 1
                continue
            if ch == '"':
                cursor.c += 1
                return "".join(out)
            if ch == "\\":
                if cursor.c + 1 >= len(line):
                    # 行末の \ は改行をつなぐ (空白を入れない)
                    cursor.i += 1
                    if cursor.i >= len(cursor.lines):
                        raise self.error("クォート (\") が閉じられていません", cursor.i - 1)
                    nxt = cursor.lines[cursor.i]
                    cursor.c = len(nxt) - len(nxt.lstrip(" \t"))
                    continue
                esc = line[cursor.c + 1]
                if esc in _ESCAPES:
                    out.append(_ESCAPES[esc])
                    cursor.c += 2
                    continue
                if esc in _HEX_LEN:
                    size = _HEX_LEN[esc]
                    digits = line[cursor.c + 2: cursor.c + 2 + size]
                    if len(digits) != size or any(d not in _DIGITS[16] for d in digits):
                        raise self.error("\\%s のエスケープが正しくありません" % esc, cursor.i)
                    out.append(chr(int(digits, 16)))
                    cursor.c += 2 + size
                    continue
                raise self.error("ダブルクォート内で使えないエスケープ \\%s があります" % esc, cursor.i)
            out.append(ch)
            cursor.c += 1

    # ------------------------------------------------------------------
    # フロー形式 [..] {..}
    # ------------------------------------------------------------------
    def _flow_node(self, cursor, as_key=False):
        cursor.skip_ws()
        anchor = None
        tag = None
        while cursor.peek() in ("&", "!"):
            token = []
            while cursor.peek() not in ("", " ", "\t", "\n", ",", "[", "]", "{", "}"):
                token.append(cursor.peek())
                cursor.advance()
            token = "".join(token)
            if token.startswith("&"):
                anchor = token[1:]
            else:
                tag = token
            cursor.skip_ws()
        ch = cursor.peek()
        if ch == "[":
            value = self._flow_seq(cursor)
        elif ch == "{":
            value = self._flow_map(cursor)
        elif ch in ("'", '"'):
            value = self._read_quoted(cursor)
        elif ch == "*":
            cursor.advance()
            name = []
            while cursor.peek() not in ("", " ", "\t", "\n", ",", "]", "}"):
                name.append(cursor.peek())
                cursor.advance()
            name = "".join(name)
            if name not in self.anchors:
                raise self.error("エイリアス *%s に対応するアンカーがありません" % name, cursor.i)
            value = copy.deepcopy(self.anchors[name])
        else:
            raw = self._flow_plain(cursor)
            if as_key:
                value = raw
            elif tag in _STANDARD_TAGS:
                value = _resolve_tagged_plain(tag, raw)
            else:
                value = resolve_plain(raw)
        return self._finish_props(value, anchor, tag)

    def _flow_plain(self, cursor):
        out = []
        while True:
            ch = cursor.peek()
            if ch == "" or ch in ",[]{}":
                break
            if ch == ":":
                nxt = cursor.peek(1)
                if nxt in ("", " ", "\t", "\n", ",", "[", "]", "{", "}"):
                    break
            if ch == "#" and out and out[-1] in (" ", "\t", "\n"):
                break
            if ch == "\n":
                out.append(" ")
                cursor.advance()
                while cursor.peek() in (" ", "\t"):
                    cursor.advance()
                continue
            out.append(ch)
            cursor.advance()
        return "".join(out).strip()

    def _flow_seq(self, cursor):
        start_line = cursor.i
        cursor.advance()
        result = []
        while True:
            cursor.skip_ws()
            ch = cursor.peek()
            if ch == "":
                raise self.error("[ が閉じられていません", start_line)
            if ch == "]":
                cursor.advance()
                return result
            if ch == ",":
                raise self.error("[ ] の中に空の要素があります", cursor.i)
            item = self._flow_node(cursor)
            cursor.skip_ws()
            if cursor.peek() == ":":
                cursor.advance()
                cursor.skip_ws()
                value = None if cursor.peek() in (",", "]") else self._flow_node(cursor)
                item = {self._key_str(item): value}
                cursor.skip_ws()
            result.append(item)
            ch = cursor.peek()
            if ch == ",":
                cursor.advance()
            elif ch != "]":
                raise self.error("[ ] の区切り (,) が見つかりません", cursor.i)

    def _flow_map(self, cursor):
        start_line = cursor.i
        cursor.advance()
        result = {}
        merges = []
        while True:
            cursor.skip_ws()
            ch = cursor.peek()
            if ch == "":
                raise self.error("{ が閉じられていません", start_line)
            if ch == "}":
                cursor.advance()
                break
            if ch == ",":
                raise self.error("{ } の中に空の要素があります", cursor.i)
            key = self._key_str(self._flow_node(cursor, as_key=True))
            cursor.skip_ws()
            value = None
            if cursor.peek() == ":":
                cursor.advance()
                cursor.skip_ws()
                if cursor.peek() not in (",", "}"):
                    value = self._flow_node(cursor)
            if key == "<<":
                merges.append(value)
            else:
                if key in result:
                    raise self.error("キー %r が同じ { } の中に 2 回書かれています" % key, cursor.i)
                result[key] = value
            cursor.skip_ws()
            ch = cursor.peek()
            if ch == ",":
                cursor.advance()
            elif ch != "}":
                raise self.error("{ } の区切り (,) が見つかりません", cursor.i)
        for source in merges:
            for item in (source if isinstance(source, list) else [source]):
                if isinstance(item, dict):
                    for key, val in item.items():
                        result.setdefault(key, copy.deepcopy(val))
        return result

    @staticmethod
    def _key_str(value):
        if isinstance(value, Tagged):
            value = value.value
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (YInt, YFloat)):
            return value.src
        return str(value)


def loads(text, filename=None):
    """YAML 文字列を読み込み、dict / list / スカラーを返す。"""
    return _Parser(text, filename).parse()


def load_file(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    return loads(text, filename=str(path))
