"""日本語と英数字が混ざった文章の、見た目の幅の計算と折り返し。"""

import unicodedata

__all__ = ["display_width", "wrap"]

# 行の先頭に来ないようにする文字 (禁則)
_NO_LINE_START = set("、。，．,.)）」』】〕〉》！？!?:：;；・ー～…％%")


def display_width(text):
    """全角を 2、半角を 1 として数えた幅。"""
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1
    return width


def _tokens(text):
    token = ""
    for ch in text:
        wide = unicodedata.east_asian_width(ch) in ("W", "F", "A")
        if ch == " ":
            if token:
                yield token
                token = ""
            yield " "
        elif wide:
            if token:
                yield token
                token = ""
            yield ch
        else:
            token += ch
    if token:
        yield token


def wrap(text, width):
    """見た目の幅 width で折り返した行のリストを返す (英単語は途中で切らない)。"""
    out = []
    for para in str(text).split("\n"):
        line = ""
        size = 0
        for tok in _tokens(para):
            w = display_width(tok)
            if size + w <= width or not line.strip():
                if w > width and not line.strip():
                    # 1 語が長すぎる (URL など) ときは強制的に切る
                    for ch in tok:
                        cw = display_width(ch)
                        if size + cw > width and line:
                            out.append(line.rstrip())
                            line, size = "", 0
                        line += ch
                        size += cw
                    continue
                line += tok
                size += w
                continue
            if tok in _NO_LINE_START:
                line += tok
                size += w
                continue
            out.append(line.rstrip())
            if tok == " ":
                line, size = "", 0
            else:
                line, size = tok, w
        out.append(line.rstrip())
    return out
