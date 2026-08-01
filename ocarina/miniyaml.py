"""Strict loader for the YAML subset machine.yaml is written in.

Ported from the workshop (oot-dojo ootbench/miniyaml.py; MACHINE.md names
this module explicitly as the parse layer).

Why hand-rolled: the repo is stdlib-only (repo rule 4). Why not JSON:
machine.yaml is the file the mind edits as its learning mechanism and AJ
reads in diffs — it has to stay comment-friendly and hand-editable.

Supported: nested maps with identifier keys, block lists (of scalars or
maps), scalars (int incl. 0x-hex, float, true/false/null, quoted or bare
strings), and # comments. One ocarina addition to the ported subset:
**scalar continuation** — lines indented deeper than their key that are
neither `key: value` nor list items fold into the previous string scalar
with a single space. MACHINE.md's own grammar example wraps a `when:`
guard across two lines; the blessed contract requires this.

Everything else is REJECTED with a line number rather than guessed at —
tabs, flow syntax ([a, b] / {k: v}), anchors, multiline strings, duplicate
keys. A parser that guesses is a false-signal generator (docs/08): a rule
that silently parsed wrong looks exactly like a rule that never matches.
"""

from __future__ import annotations

import re
from pathlib import Path

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class MiniYamlError(ValueError):
    def __init__(self, lineno: int, msg: str):
        super().__init__(f"line {lineno}: {msg}")
        self.lineno = lineno


def load_path(path: Path | str):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise MiniYamlError(0, f"cannot read {path}: {e}") from e
    return load(text)


def load(text: str):
    tokens = _tokenize(text)
    if not tokens:
        return {}
    value, pos = _parse(tokens, 0, tokens[0][1])
    if pos != len(tokens):
        lineno, ind, _ = tokens[pos]
        raise MiniYamlError(lineno, f"unexpected content at indent {ind} after top-level block")
    return value


# -- lexing ----------------------------------------------------------------

def _tokenize(text: str) -> list[tuple[int, int, str]]:
    out = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw:
            raise MiniYamlError(lineno, "tabs are not allowed; indent with spaces")
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        out.append((lineno, indent, line.strip()))
    return out


def _strip_comment(line: str) -> str:
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] == " "):
            return line[:i]
    return line


# -- parsing ---------------------------------------------------------------

def _parse(tokens, pos, indent):
    _, _, content = tokens[pos]
    if content == "-" or content.startswith("- "):
        return _parse_list(tokens, pos, indent)
    return _parse_map(tokens, pos, indent)


def _parse_map(tokens, pos, indent):
    out: dict = {}
    while pos < len(tokens):
        lineno, ind, content = tokens[pos]
        if ind < indent:
            break
        if ind > indent:
            raise MiniYamlError(lineno, f"unexpected indent {ind} (block is at {indent})")
        if content == "-" or content.startswith("- "):
            raise MiniYamlError(lineno, "list item where a map key was expected")
        key, sep, rest = content.partition(":")
        key = key.strip()
        if not sep or not _KEY_RE.match(key):
            raise MiniYamlError(lineno, f"expected 'key: value' with an identifier key, got {content!r}")
        if key in out:
            raise MiniYamlError(lineno, f"duplicate key {key!r}")
        rest = rest.strip()
        if rest:
            value = _scalar(rest, lineno)
            pos += 1
            # Scalar continuation (see module docstring): fold deeper lines
            # that cannot start a nested block into the string.
            while (isinstance(value, str) and pos < len(tokens)
                   and tokens[pos][1] > indent
                   and not _looks_like_kv(tokens[pos][2])
                   and tokens[pos][2] != "-"
                   and not tokens[pos][2].startswith("- ")):
                value = value + " " + tokens[pos][2]
                pos += 1
            out[key] = value
        elif pos + 1 < len(tokens) and tokens[pos + 1][1] > indent:
            out[key], pos = _parse(tokens, pos + 1, tokens[pos + 1][1])
        else:
            out[key] = None
            pos += 1
    return out, pos


def _parse_list(tokens, pos, indent):
    out: list = []
    while pos < len(tokens):
        lineno, ind, content = tokens[pos]
        if ind < indent:
            break
        if ind > indent:
            raise MiniYamlError(lineno, f"unexpected indent {ind} (list is at {indent})")
        if not (content == "-" or content.startswith("- ")):
            raise MiniYamlError(lineno, "map key at the same indent as list items; indent the map or dedent the key")
        rest = content[1:].strip()
        if not rest:
            # "-" alone: the item's content is the indented block below.
            if pos + 1 >= len(tokens) or tokens[pos + 1][1] <= indent:
                raise MiniYamlError(lineno, "empty list item")
            item, pos = _parse(tokens, pos + 1, tokens[pos + 1][1])
            out.append(item)
        elif _looks_like_kv(rest):
            # "- key: value" starts an inline map whose remaining keys sit
            # at column indent+2 (aligned under the key). Re-home this line
            # to that column and parse a normal map.
            patched = list(tokens)
            patched[pos] = (lineno, indent + 2, rest)
            item, pos = _parse_map(patched, pos, indent + 2)
            out.append(item)
        else:
            out.append(_scalar(rest, lineno))
            pos += 1
    return out, pos


def _looks_like_kv(text: str) -> bool:
    key, sep, _ = text.partition(":")
    return bool(sep) and bool(_KEY_RE.match(key.strip()))


def _scalar(text: str, lineno: int):
    if text[0] in "\"'":
        if len(text) < 2 or text[-1] != text[0]:
            raise MiniYamlError(lineno, f"unterminated quoted string: {text!r}")
        return text[1:-1]
    if text[0] in "[{":
        raise MiniYamlError(lineno, "flow syntax is not supported; use block lists/maps")
    if text[0] in "&*|>":
        raise MiniYamlError(lineno, f"unsupported YAML feature at {text!r}")
    if text == "true":
        return True
    if text == "false":
        return False
    if text in ("null", "~"):
        return None
    try:
        return int(text, 0)  # base 0: handles 0x0055 actor ids
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text
