"""環境変数まわり: ``${VAR}`` の補間と .env / env_file の読み込み。

* :func:`interpolate` ... compose-go (template パッケージ) と同じ規則で ``${VAR}`` を展開
* :func:`parse_dotenv` ... compose-go (dotenv パッケージ) と同じ規則で .env を読む
* :func:`parse_docker_envfile` ... ``docker run --env-file`` (docker CLI) と同じ規則で読む

compose と docker CLI では env ファイルの解釈が少し違います
(クォートの扱い・``#`` コメント・``$`` 展開など)。
:func:`docker_compatible` で「どちらで読んでも同じ値になるか」を判定し、
同じになるときだけ ``--env-file`` をそのまま使います。
"""

import re

__all__ = [
    "InterpolationError",
    "interpolate",
    "interpolate_tree",
    "parse_dotenv",
    "parse_dotenv_raw",
    "parse_docker_envfile",
    "docker_compatible",
]


class InterpolationError(ValueError):
    pass


_NAME_RE = re.compile(r"[_a-zA-Z][_a-zA-Z0-9]*")
_BRACED_RE = re.compile(r"^([_a-zA-Z][_a-zA-Z0-9]*)(?:(:?[-+?])(.*))?$", re.S)


def _closing_brace(text, start):
    """``text[start:]`` が ``${`` で始まるとき、対応する ``}`` の位置を返す。"""
    depth = 0
    idx = start
    while idx < len(text):
        if text[idx] == "}":
            depth -= 1
            if depth == 0:
                return idx
        if text.startswith("${", idx):
            depth += 1
            idx += 1
        idx += 1
    return -1


def interpolate(text, lookup, unset=None, where=None):
    """compose と同じ規則で ``$VAR`` / ``${VAR...}`` を展開する。

    lookup(name) は値 (str) か None (未設定) を返す関数。
    unset には未設定だった変数名が追加される (警告用)。
    """
    if "$" not in text:
        return text
    out = []
    idx = 0
    length = len(text)
    while idx < length:
        ch = text[idx]
        if ch != "$":
            out.append(ch)
            idx += 1
            continue
        if idx + 1 < length and text[idx + 1] == "$":
            out.append("$")
            idx += 2
            continue
        if idx + 1 < length and text[idx + 1] == "{":
            end = _closing_brace(text, idx)
            if end < 0:
                raise InterpolationError("${ が閉じられていません: %s%s" % (text, _where(where)))
            expr = text[idx + 2:end]
            out.append(_eval_braced(expr, lookup, unset, where, text))
            idx = end + 1
            continue
        match = _NAME_RE.match(text, idx + 1)
        if match:
            name = match.group(0)
            value = lookup(name)
            if value is None:
                if unset is not None:
                    unset.add(name)
                value = ""
            out.append(value)
            idx = match.end()
            continue
        out.append("$")
        idx += 1
    return "".join(out)


def _where(where):
    return " (%s)" % where if where else ""


def _eval_braced(expr, lookup, unset, where, whole):
    match = _BRACED_RE.match(expr)
    if not match:
        raise InterpolationError("${%s} は正しい変数の書き方ではありません%s" % (expr, _where(where)))
    name, op, arg = match.group(1), match.group(2), match.group(3)
    value = lookup(name)
    if op is None:
        if value is None:
            if unset is not None:
                unset.add(name)
            return ""
        return value
    empty = value is None or value == ""
    if op == ":-":
        return interpolate(arg, lookup, unset, where) if empty else value
    if op == "-":
        return interpolate(arg, lookup, unset, where) if value is None else value
    if op == ":?":
        if empty:
            raise InterpolationError(
                "必須の変数 %s が設定されていません: %s%s" % (name, interpolate(arg, lookup, unset, where), _where(where))
            )
        return value
    if op == "?":
        if value is None:
            raise InterpolationError(
                "必須の変数 %s が設定されていません: %s%s" % (name, interpolate(arg, lookup, unset, where), _where(where))
            )
        return value
    if op == ":+":
        return "" if empty else interpolate(arg, lookup, unset, where)
    if op == "+":
        return "" if value is None else interpolate(arg, lookup, unset, where)
    raise InterpolationError("${%s} を解釈できません%s" % (expr, _where(where)))


def interpolate_tree(node, lookup, unset=None, path=""):
    """YAML を読んだ木構造の文字列すべてに補間をかける (キーはそのまま)。"""
    from .yamlmini import Tagged  # 循環 import を避ける

    if isinstance(node, str):
        return interpolate(node, lookup, unset, path)
    if isinstance(node, dict):
        return {k: interpolate_tree(v, lookup, unset, "%s.%s" % (path, k) if path else k) for k, v in node.items()}
    if isinstance(node, list):
        return [interpolate_tree(v, lookup, unset, "%s[%d]" % (path, i)) for i, v in enumerate(node)]
    if isinstance(node, Tagged):
        return Tagged(node.tag, interpolate_tree(node.value, lookup, unset, path))
    return node


# ---------------------------------------------------------------------------
# .env (compose-go dotenv 互換)
# ---------------------------------------------------------------------------
_SPACE = "\t\v\f\r \x85\xa0"
_ESCAPE_SEQ = re.compile(r"(\\(?:[abcfnrtv$\"\\]|0\d{0,3}))")
_SIMPLE_ESCAPES = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
    '"': '"', "\\": "\\",
}


class DotenvError(ValueError):
    pass


def _expand_escapes(text):
    def repl(match):
        token = match.group(1)
        if token == "\\$":
            return "$$"
        if token.startswith("\\0"):
            # compose-go は "\0" を "\" に置き換えてから Go の UnquoteChar に渡す
            digits = token[2:]
            if len(digits) == 3 and all(d in "01234567" for d in digits) and int(digits, 8) <= 255:
                return chr(int(digits, 8))
            return "\\" + digits
        if token[1] == "c":
            return token
        return _SIMPLE_ESCAPES.get(token[1], token)

    return _ESCAPE_SEQ.sub(repl, text)


def parse_dotenv(text, lookup=None, filename=None):
    """compose と同じ規則で .env / env_file を読み、[(key, value), ...] を返す。

    lookup(name) はファイル外の環境 (OS 環境変数など) を引く関数。
    値の中の ``${VAR}`` は「lookup → そのファイル内で先に定義した値」の順で展開される。
    """
    if lookup is None:
        lookup = lambda name: None  # noqa: E731
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n")
    out = {}
    order = []

    def env_lookup(name):
        value = lookup(name)
        if value is not None:
            return value
        return out.get(name)

    src = text
    line = 1
    while True:
        # 文の始まり (空白・コメント行を読み飛ばす)
        while True:
            pos = 0
            while pos < len(src) and (src[pos] in _SPACE or src[pos] == "\n"):
                if src[pos] == "\n":
                    line += 1
                pos += 1
            src = src[pos:]
            if src.startswith("#"):
                nl = src.find("\n")
                if nl < 0:
                    src = ""
                else:
                    src = src[nl:]
                continue
            break
        if src == "":
            break
        if re.match(r"^export[ \t]+", src):
            src = src[len("export"):].lstrip(_SPACE)
        key = None
        inherited = False
        offset = 0
        for idx, ch in enumerate(src):
            if ch in _SPACE:
                continue
            if ch in "=:\n":
                key = src[:idx]
                offset = idx + 1
                inherited = ch == "\n"
                break
            if ch in "_.-[]" or ch.isalnum():
                continue
            raise DotenvError(
                "%s %d 行目: 変数名に使えない文字 %r があります" % (filename or ".env", line, ch)
            )
        if key is None:
            key = src
            offset = len(src)
            inherited = True
        key = key.rstrip(_SPACE + "\n")
        if " " in key:
            raise DotenvError("%s %d 行目: 変数名に空白は使えません" % (filename or ".env", line))
        rest = src[offset:].lstrip(_SPACE)
        if inherited:
            value = lookup(key)
            if value is not None:
                if key not in out:
                    order.append(key)
                out[key] = value
            if src[offset - 1:offset] == "\n":
                line += 1
            src = rest
            continue
        quote = rest[:1]
        if quote not in ("'", '"'):
            value, nl, remain = rest.partition("\n")
            line += 1
            value = value.split(" #", 1)[0]
            value = value.rstrip()
            value = interpolate(value, env_lookup, None, filename)
            src = remain if nl else ""
        else:
            chars = []
            escape = False
            end = -1
            for idx in range(1, len(rest)):
                ch = rest[idx]
                if ch == "\n":
                    line += 1
                if ch != quote:
                    if not escape and ch == "\\":
                        escape = True
                        continue
                    if escape:
                        escape = False
                        chars.append("\\")
                    chars.append(ch)
                    continue
                if escape:
                    escape = False
                    chars.append(ch)
                    continue
                end = idx
                break
            if end < 0:
                raise DotenvError("%s %d 行目: クォートが閉じられていません" % (filename or ".env", line))
            value = "".join(chars)
            if quote == '"':
                value = interpolate(_expand_escapes(value), env_lookup, None, filename)
            src = rest[end + 1:]
        if key not in out:
            order.append(key)
        out[key] = value
    return [(k, out[k]) for k in order]


def parse_dotenv_raw(text):
    """``format: raw`` の env_file を読む (クォート・展開・コメント処理をしない)。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    result = {}
    order = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.lstrip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if key not in result:
            order.append(key)
        result[key] = value
    return [(k, result[k]) for k in order]


def parse_docker_envfile(text):
    """``docker run --env-file`` (docker CLI) と同じ規則で読む。

    戻り値: (pairs, bare_keys)  pairs は [(key, value)]、bare_keys は ``=`` の無い行の変数名。
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    pairs = []
    bare = []
    for raw in text.split("\n"):
        if raw.endswith("\r"):
            raw = raw[:-1]
        line = raw.lstrip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.lstrip(" \t")
        if any(ch in key for ch in " \t\n\v\f\r"):
            return None, None
        if not key:
            return None, None
        if sep:
            pairs.append((key, value))
        else:
            bare.append(key)
    return pairs, bare


def docker_compatible(text, compose_pairs):
    """``--env-file`` で渡しても compose と同じ値になるかを判定する。"""
    pairs, bare = parse_docker_envfile(text)
    if pairs is None or bare:
        return False
    docker_map = {}
    for key, value in pairs:
        docker_map[key] = value
    compose_map = dict(compose_pairs)
    if docker_map != compose_map:
        return False
    for key in docker_map:
        if not re.match(r"^[A-Za-z0-9_.\-\[\]]+$", key):
            return False
    return True
