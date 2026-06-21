"""WW3 namelist 文本读写原语（所有 namelist Mixin 的公共基类）。

提供 namelist 行级操作的静态辅助方法：注释/取消注释、识别 namelist 结束符 ``/``、
按模板对齐键值赋值行等。不包含业务逻辑，仅封装 Fortran namelist 文本格式约定。

[EN] WW3 namelist text read/write primitives (common base class for all namelist Mixins).

Provides static helper methods for line-level namelist operations: comment/uncomment,
recognize namelist terminator ``/``, align key-value assignment lines to template, etc.
Contains no business logic; only encapsulates Fortran namelist text format conventions.
"""
from __future__ import annotations

import re


class NMLPrimitives:
    """WW3 namelist 文本行处理的静态工具基类。

    各 ``ww3_*_nml.py`` Mixin 均继承此类，复用注释切换与赋值行格式化逻辑，
    保证输出与 NML 模板文件的缩进、等号对齐风格一致。

    [EN] Static utility base class for WW3 namelist text line processing.

    All ``ww3_*_nml.py`` Mixins inherit this class, reusing comment toggle and
    assignment line formatting logic to ensure output indentation and equals-sign
    alignment are consistent with the NML template files.
    """

    @staticmethod
    def _ww3_nml_force_comment_line(line):
        """与 NML 模板 ww3_grid.nml 一致：行首一个 `!`，其后保留原行全部内容（含缩进）。

        例如 `&RECT_NML` → `!&RECT_NML`，`  RECT%NX = 1` → `!  RECT%NX = 1`。
        避免写成 `  ! RECT%NX`（`!` 插在缩进后），与模板中 `!&UNST_NML` / `!  UNST%...` 风格一致。

        [EN] Consistent with NML template ww3_grid.nml: a single ``!`` at the
        beginning of the line, followed by the full original line content (including indentation).

        For example, ``&RECT_NML`` -> ``!&RECT_NML``, ``  RECT%NX = 1`` -> ``!  RECT%NX = 1``.
        Avoid writing ``  ! RECT%NX`` (``!`` inserted after indentation), matching the
        ``!&UNST_NML`` / ``!  UNST%...`` style in the template.
        """
        if not line.strip():
            return line
        ls = line.lstrip()
        if ls.startswith("!"):
            return line
        nl = "\n" if line.endswith("\n") else ""
        body = line.rstrip("\n")
        return "!" + body + nl

    @staticmethod
    def _ww3_nml_force_uncomment_line(line):
        """去掉行首（允许行前空白后的）单个 `!`，保留 `!` 之后全部字符，不 lstrip（否则会丢掉 UNST 行前两格缩进）。

        [EN] Remove a single ``!`` at the start of the line (allowing leading whitespace
        before it), preserving all characters after ``!``. Does not lstrip (otherwise the
        two-space indentation before UNST lines would be lost).
        """
        body = line.rstrip("\n")
        nl = "\n" if line.endswith("\n") else ""
        m = re.match(r"^(\s*)!(.*)$", body)
        if m:
            return m.group(1) + m.group(2) + nl
        return line

    @staticmethod
    def _nml_line_is_namelist_close(lnn):
        """识别 namelist 结束行 `/`（允许行前 `!`）。

        [EN] Recognize namelist terminator line ``/`` (allows ``!`` before it).
        """
        t = lnn.strip()
        if t.startswith("!"):
            t = t[1:].lstrip()
        return t == "/" or t.startswith("/")

    @staticmethod
    def _ww3_nml_assign_line(key: str, value_repr: str, key_width: int = 18) -> str:
        """生成与 NML 模板 ``ww3_grid.nml`` 等号对齐的赋值行。

        格式为 ``  {key}{空格}=  {value_repr}\\n``，键名加填充空格后总宽度为
        ``key_width`` 字符。常用宽度：GRID/RECT 为 18，DEPTH%SF 为 16，OBST%SF 为 15。

        [EN] Generate an assignment line with equals-sign alignment matching the
        NML template ``ww3_grid.nml``.

        Format is ``  {key}{spaces}=  {value_repr}\\n``, where the key name plus padding
        spaces totals ``key_width`` characters. Common widths: GRID/RECT = 18,
        DEPTH%SF = 16, OBST%SF = 15.
        """
        sp = key_width - len(key)
        if sp < 1:
            sp = 1
        return f"  {key}{' ' * sp}=  {value_repr}\n"
