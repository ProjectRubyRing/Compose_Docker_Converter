#!/usr/bin/env python3
"""compose2docker - docker compose の構成を docker コマンドだけで再現する手順と解説を作るツール。

使い方:  python3 compose2docker.py -f compose.yaml  (詳しくは --help / README.md)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from c2d.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
