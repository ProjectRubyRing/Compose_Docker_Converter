"""内蔵 YAML パーサと PyYAML の読み取り結果を比較する開発用テスト (PyYAML がある環境のみ)。"""
import glob
import math
import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import yaml  # PyYAML
from c2d import yamlmini


class Loader(yaml.SafeLoader):
    pass


def _tag_constructor(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return ("TAG", "!" + suffix, value)


Loader.add_multi_constructor("!", _tag_constructor)
# YAML 1.2 寄りに: yes/no/on/off は文字列、sexagesimal なし
for ch in list(Loader.yaml_implicit_resolvers):
    Loader.yaml_implicit_resolvers[ch] = [
        (tag, regexp) for tag, regexp in Loader.yaml_implicit_resolvers[ch]
        if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float")
    ]
Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def norm(value):
    if isinstance(value, yamlmini.Tagged):
        return ("TAG", value.tag, norm(value.value))
    if isinstance(value, tuple) and value and value[0] == "TAG":
        return ("TAG", value[1], norm(value[2]))
    if isinstance(value, dict):
        return {str(k): norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [norm(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (yamlmini.YInt, yamlmini.YFloat)):
        return value.src   # PyYAML 側は数値解決を無効化して文字列のまま比較する
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return value


def py_norm(value):
    if isinstance(value, tuple) and value and value[0] == "TAG":
        return ("TAG", value[1], py_norm(value[2]))
    if isinstance(value, dict):
        return {str(k): py_norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [py_norm(v) for v in value]
    return value


def diff(a, b, path="$"):
    if type(a) != type(b):
        return ["%s: type %s != %s (%r vs %r)" % (path, type(a).__name__, type(b).__name__, a, b)]
    if isinstance(a, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append("%s.%s: missing in %s" % (path, k, "mini" if k not in a else "pyyaml"))
            else:
                out += diff(a[k], b[k], path + "." + k)
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return ["%s: len %d != %d" % (path, len(a), len(b))]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, "%s[%d]" % (path, i))
        return out
    if a != b:
        return ["%s: %r != %r" % (path, a, b)]
    return []


def main(paths):
    ok = bad = 0
    for path in paths:
        text = open(path, encoding="utf-8-sig").read()
        try:
            mine = norm(yamlmini.loads(text, path))
        except Exception as exc:  # noqa
            print("MINI-ERROR", path, exc)
            bad += 1
            continue
        try:
            theirs = py_norm(yaml.load(text, Loader=Loader))
        except Exception as exc:  # noqa
            print("PYYAML-ERROR", path, exc)
            continue
        d = diff(mine, theirs)
        if d:
            bad += 1
            print("DIFF", path)
            for line in d[:15]:
                print("   ", line)
        else:
            ok += 1
    print("ok=%d bad=%d" % (ok, bad))


if __name__ == "__main__":
    main(sys.argv[1:])
