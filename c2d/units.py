"""サイズ・時間・数値の変換 (compose-go / docker/go-units と同じ解釈)。"""

import decimal
import math
import re

from .yamlmini import YFloat, YInt

__all__ = [
    "UnitError",
    "ram_in_bytes",
    "parse_duration",
    "duration_seconds",
    "duration_micro",
    "go_str",
    "human_bytes",
    "format_seconds",
]


class UnitError(ValueError):
    pass


_RAM_RE = re.compile(r"^(\d+(?:\.\d+)*) ?([kKmMgGtTpP])?[iI]?[bB]?$")
_RAM_MULT = {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3, "t": 1024 ** 4, "p": 1024 ** 5}


def ram_in_bytes(value):
    """``512m`` / ``1g`` / ``1073741824`` などをバイト数 (int) にする (docker/go-units RAMInBytes)。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text in ("", "-1"):
        return -1 if text == "-1" else None
    match = _RAM_RE.match(text)
    if not match:
        raise UnitError("サイズ %r を解釈できません (例: 512m, 1g)" % text)
    number = float(match.group(1)) if match.group(1).count(".") <= 1 else None
    if number is None:
        raise UnitError("サイズ %r を解釈できません" % text)
    unit = (match.group(2) or "").lower()
    return int(number * _RAM_MULT[unit])


_DURATION_RE = re.compile(r"(\d+(?:\.\d*)?|\.\d+)(ns|us|µs|μs|ms|s|m|h)")
_DURATION_UNITS = {
    "ns": 1e-9, "us": 1e-6, "µs": 1e-6, "μs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0,
}


def parse_duration(value):
    """Go の time.ParseDuration 相当。秒 (float) を返す。"""
    if value is None:
        return None
    if isinstance(value, bool):
        raise UnitError("時間 %r を解釈できません" % value)
    if isinstance(value, (int, float)):
        # compose-go は数値の時間を秒として扱う (例: stop_grace_period: 10)
        return float(value)
    text = str(value).strip()
    if text in ("0", "+0", "-0"):
        return 0.0
    sign = 1.0
    if text[:1] in "+-":
        if text[0] == "-":
            sign = -1.0
        text = text[1:]
    pos = 0
    total = 0.0
    if not text:
        raise UnitError("時間 %r を解釈できません" % value)
    while pos < len(text):
        match = _DURATION_RE.match(text, pos)
        if not match:
            raise UnitError("時間 %r を解釈できません (例: 30s, 1m30s, 500ms)" % value)
        total += float(match.group(1)) * _DURATION_UNITS[match.group(2)]
        pos = match.end()
    return sign * total


def duration_seconds(value):
    """時間を秒の整数にする (compose の stop_grace_period → StopTimeout と同じく切り捨て)。"""
    seconds = parse_duration(value)
    if seconds is None:
        return None
    return int(seconds)


def duration_micro(value):
    """cpu_rt_runtime などをマイクロ秒の整数にする。"""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return int(round(parse_duration(value) * 1e6))


def format_seconds(seconds):
    """秒を Go の Duration 表記風 (1m30s など) にする。"""
    seconds = float(seconds)
    if seconds == int(seconds):
        whole = int(seconds)
        hours, rem = divmod(whole, 3600)
        minutes, secs = divmod(rem, 60)
        out = ""
        if hours:
            out += "%dh" % hours
        if minutes:
            out += "%dm" % minutes
        if secs or not out:
            out += "%ds" % secs
        return out
    return "%gs" % seconds


def go_duration(value):
    """時間の表記を Go の time.Duration.String() と同じ形にする (例: 120s → 2m0s)。"""
    if value is None:
        return None
    seconds = parse_duration(value)
    nanos = int(round(seconds * 1e9))
    if nanos == 0:
        return "0s"
    sign = "-" if nanos < 0 else ""
    nanos = abs(nanos)
    if nanos < 1000:
        return "%s%dns" % (sign, nanos)
    if nanos < 1000000:
        return sign + _trim_fraction(nanos, 1000) + "µs"
    if nanos < 1000000000:
        return sign + _trim_fraction(nanos, 1000000) + "ms"
    total_seconds, frac = divmod(nanos, 1000000000)
    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    sec_text = _trim_fraction(secs * 1000000000 + frac, 1000000000)
    out = sign
    if hours:
        out += "%dh" % hours
    if hours or minutes:
        out += "%dm" % minutes
    out += sec_text + "s"
    return out


def _trim_fraction(value, unit):
    whole, frac = divmod(value, unit)
    if not frac:
        return str(whole)
    digits = len(str(unit)) - 1
    text = ("%0" + str(digits) + "d") % frac
    return "%d.%s" % (whole, text.rstrip("0"))


def _go_float(value):
    """Go の fmt.Sprint(float64) (= %g 最短表現) と同じ表記にする。

    例: 1.10 → "1.1", 1000000.0 → "1e+06", 0.00001 → "1e-05"
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if value == 0:
        return "-0" if math.copysign(1.0, value) < 0 else "0"
    sign, digits, exponent = decimal.Decimal(repr(float(value))).as_tuple()
    digits = list(digits)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    text = "".join(str(d) for d in digits)
    count = len(digits)
    point = count + exponent          # 小数点の位置 (0.d1d2.. × 10^point)
    sci = point - 1                   # 指数表記したときの指数
    prefix = "-" if sign else ""
    if sci < -4 or sci >= 6:
        mantissa = text[0] + ("." + text[1:] if count > 1 else "")
        return "%s%se%s%02d" % (prefix, mantissa, "-" if sci < 0 else "+", abs(sci))
    if point <= 0:
        return prefix + "0." + "0" * (-point) + text
    if point >= count:
        return prefix + text + "0" * (point - count)
    return prefix + text[:point] + "." + text[point:]


def go_str(value):
    """compose-go が YAML の値を文字列にするときの表記 (fmt.Sprint 相当)。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, YInt) or (isinstance(value, int) and not isinstance(value, bool)):
        return str(int(value))
    if isinstance(value, (YFloat, float)):
        return _go_float(float(value))
    return str(value)


def human_bytes(size):
    """バイト数を docker が読める一番短い表記 (256m など) にする (値は変えない)。"""
    if size is None:
        return None
    size = int(size)
    if size <= 0:
        return str(size)
    for unit, mult in (("g", 1024 ** 3), ("m", 1024 ** 2), ("k", 1024)):
        if size % mult == 0:
            return "%d%s" % (size // mult, unit)
    return str(size)
