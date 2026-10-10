"""内蔵ローダーと docker compose config の結果を比べる開発用テスト (docker compose がある環境で実行)。

使い方: python3 tests/test_loader_parity.py <compose ファイル> [...]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from c2d import loader  # noqa: E402


def clean(node):
    if isinstance(node, dict):
        return {k: clean(v) for k, v in node.items() if not k.startswith("_") and not k.startswith("x-")}
    if isinstance(node, list):
        return [clean(v) for v in node]
    if isinstance(node, float) and node == int(node):
        return int(node)
    return node


def norm_project(p):
    p = clean(p)
    for svc in (p.get("services") or {}).values():
        svc.pop("command", None) if svc.get("command") is None else None
        svc.pop("entrypoint", None) if svc.get("entrypoint") is None else None
        for vol in svc.get("volumes") or []:
            if vol.get("type") == "bind" and vol.get("bind") == {"create_host_path": True}:
                vol["bind"] = {}
        dep = svc.get("deploy")
        if dep is not None:
            dep.pop("placement", None)
            if dep.get("resources") == {}:
                dep.pop("resources")
            if not dep:
                svc.pop("deploy")
        if svc.get("environment") == {}:
            svc.pop("environment")
    return p


def diff(a, b, path="$"):
    if type(a) != type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return ["%s: %r != %r" % (path, a, b)]
    if isinstance(a, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append("%s.%s: builtin に無い (compose=%r)" % (path, k, b[k]))
            elif k not in b:
                out.append("%s.%s: compose に無い (builtin=%r)" % (path, k, a[k]))
            else:
                out += diff(a[k], b[k], path + "." + k)
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return ["%s: 長さ %d != %d  builtin=%r compose=%r" % (path, len(a), len(b), a, b)]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, "%s[%d]" % (path, i))
        return out
    if a != b:
        return ["%s: builtin=%r compose=%r" % (path, a, b)]
    return []


def main(paths):
    ok = bad = skipped = 0
    for arg in paths:
        path, _, envf = arg.partition("::")
        opts = loader.LoadOptions(files=[path], env_files=[envf] if envf else [])
        try:
            comp = loader.load_with_compose(opts, [os.path.abspath(path)])
        except loader.LoadError as exc:
            print("SKIP (compose error)", path, str(exc).splitlines()[-1][:160])
            skipped += 1
            continue
        try:
            mine = loader.load_builtin(opts, [os.path.abspath(path)])
        except Exception as exc:  # noqa
            print("BUILTIN-ERROR", path, exc)
            bad += 1
            continue
        loader.canonicalize(comp)
        loader.canonicalize(mine)
        d = diff(norm_project(mine), norm_project(comp))
        if d:
            bad += 1
            print("DIFF", path)
            for line in d[:25]:
                print("   ", line)
        else:
            ok += 1
    print("ok=%d bad=%d skipped=%d" % (ok, bad, skipped))


if __name__ == "__main__":
    main(sys.argv[1:])
