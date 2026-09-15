"""Fortran namelist 文本中实际生效的赋值。

只认 ``&GROUP … /`` 之内、未被 ``!`` 注释掉的 ``KEY = VALUE``；同一键多次赋值时后者生效，
与 Fortran namelist 读入一致。工具生成的 ww3_grid.nml 在真实赋值前带有
``!     SPECTRUM%NK = 0`` 之类的模板说明行，这些行必须忽略，否则会读出 0。
"""

from __future__ import annotations

import re

_KEY = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_%()]*)\s*=\s*")
_GROUP = re.compile(r"\s*&[A-Za-z_][A-Za-z0-9_]*")


def is_nml_comment(line: str) -> bool:
    return line.lstrip().startswith("!")


def strip_nml_comment(line: str) -> str:
    """去掉行内 ``!`` 注释；引号内的 ``!`` 保留。"""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "!":
            return line[:i]
    return line


def _take_value(text: str) -> tuple[str, str]:
    """取赋值号右侧的第一个值，返回 (去引号的值, 剩余文本)。"""
    text = text.lstrip()
    if text[:1] in ("'", '"'):
        end = text.find(text[0], 1)
        if end == -1:
            return text[1:].strip(), ""
        return text[1:end].strip(), text[end + 1 :]
    match = re.match(r"[^\s,/]+", text)
    if not match:
        return "", text
    return match.group(0), text[match.end() :]


def _skip_to_next(text: str) -> tuple[str, bool]:
    """跳过同一赋值的其余值直到下一个键；返回 (剩余文本, 是否遇到组结束 /)。"""
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "/":
            return "", True
        elif _KEY.match(text, i) and (i == 0 or text[i - 1] in " \t,"):
            return text[i:], False
    return "", False


def effective_nml_assignments(text: str) -> dict[str, str]:
    """返回 ``{KEY(大写): 值}``；带引号的值去掉引号，否则取第一个记号。"""
    values: dict[str, str] = {}
    in_group = False
    for raw in text.splitlines():
        if is_nml_comment(raw):
            continue
        rest = strip_nml_comment(raw)
        group = _GROUP.match(rest)
        if group:
            in_group = True
            rest = rest[group.end() :]
        while in_group and rest.strip():
            match = _KEY.match(rest)
            if not match:
                rest, ended = _skip_to_next(rest)
                if ended:
                    in_group = False
                continue
            value, rest = _take_value(rest[match.end() :])
            values[match.group(1).upper()] = value
            rest, ended = _skip_to_next(rest)
            if ended:
                in_group = False
    return values
