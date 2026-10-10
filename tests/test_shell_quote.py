"""shell.quote の結果を本物の bash に通して、元の文字列に戻ることを確かめる (bash がある環境で実行)。"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from c2d.shell import quote  # noqa: E402

CASES = [
    "", "simple", "with space", "it's", 'say "hi"', "$HOME", "a$b", "`cmd`", "back\\slash", "bang!", "!!",
    "mix 'single' and \"double\" $VAR `x` \\ !", "line1\nline2", "tab\there", "日本語の値", "~/path", "#notcomment",
    "*.txt", "a&b|c;d", "(paren)", "{a,b}", "x=y", "--flag=value", "trailing space ", " leading", "'", '"', "\\",
    "test \"$(cat /tmp/post.txt)\" = post", "mysql -u\"$U\" -e 'SELECT 1' >/dev/null 2>&1", "\x01ctrl",
]

SEP = "<<C2D-SEP>>"


def main():
    lines = ["set +H"]
    for case in CASES:
        lines.append("printf '%%s%s' %s" % (SEP, quote(case)))
    proc = subprocess.run(["bash", "-c", "\n".join(lines) + "\n"], capture_output=True)
    outs = proc.stdout.decode("utf-8").split(SEP)[:-1]
    bad = 0
    for case, out in zip(CASES, outs):
        if case != out:
            bad += 1
            print("NG", json.dumps(case), "->", quote(case), "->", json.dumps(out))
    if len(outs) != len(CASES):
        print("count mismatch", len(outs), len(CASES), proc.stderr.decode())
        bad += 1
    for case in CASES:
        print("   %-48s => %s" % (json.dumps(case, ensure_ascii=False), quote(case)))
    print("ok" if not bad else "NG=%d" % bad)
    return bad


if __name__ == "__main__":
    sys.exit(main())
