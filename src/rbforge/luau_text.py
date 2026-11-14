"""Strip Luau comments (and optionally string literals) so a mention cannot pass for code.

One scanner, shared by every heuristic that reads source text: the server-test runner asks "does
this file call SetAttribute at all", and the offline gate asks "does this file call loadstring".
Both used to be fooled by a comment or a string that merely names the call.
"""


def code_only(src, keep_strings=False):
    """`src` without comments; also without string literals unless `keep_strings`.

    Luau allows long brackets at any level (`[[`, `[=[`, `[==[`, ...) for both strings and comments,
    and `--` starts a comment unless it opens a long bracket. A removed comment becomes one space so
    tokens on either side never fuse. Kept strings are copied verbatim, quotes included, which lets a
    caller still see `GetService("DataStoreService")` while ignoring a comment that names it.
    Backtick strings may hold `{expressions}`, so they are kept as code: the conservative reading.
    """
    out = []
    i, n = 0, len(src)

    def long_bracket(at):
        """(level, end_index) for a `[=*[` opener at `at`, else (None, at)."""
        j = at + 1
        while j < n and src[j] == "=":
            j += 1
        if j < n and src[j] == "[":
            return j - at - 1, j + 1
        return None, at

    while i < n:
        ch = src[i]
        if src.startswith("--", i):
            level, after = long_bracket(i + 2)
            if level is not None:
                close = "]" + "=" * level + "]"
                end = src.find(close, after)
                i = n if end == -1 else end + len(close)
            else:
                end = src.find("\n", i)
                i = n if end == -1 else end
            out.append(" ")
        elif ch == "[":
            level, after = long_bracket(i)
            if level is not None:
                close = "]" + "=" * level + "]"
                end = src.find(close, after)
                stop = n if end == -1 else end + len(close)
                if keep_strings:
                    out.append(src[i:stop])
                i = stop
            else:
                out.append(ch)
                i += 1
        elif ch in "\"'":
            start, quote, i = i, ch, i + 1
            while i < n and src[i] != quote and src[i] != "\n":
                i += 2 if src[i] == "\\" else 1
            i += 1
            if keep_strings:
                out.append(src[start:i])
        else:
            out.append(ch)
            i += 1
    return "".join(out)
