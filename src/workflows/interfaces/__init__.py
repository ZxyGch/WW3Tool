"""对外入口适配层（interfaces）。

本包位于 ``workflows/`` 最外层，将 application 用例暴露给 CLI、脚本或未来
其他宿主环境。当前仅包含命令行适配器 ``command_line``。

依赖方向：interfaces → application → infrastructure → domain

[EN] External entry-point adapter layer (interfaces).

This package is the outermost layer of ``workflows/``, exposing application
use cases to the CLI, scripts, or other future host environments. Currently
it only contains the command-line adapter ``command_line``.

Dependency direction: interfaces -> application -> infrastructure -> domain
"""
