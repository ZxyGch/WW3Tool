"""对外入口适配层（interfaces）。

本包位于 ``workflows/`` 最外层，将 application 用例暴露给 CLI、脚本或未来
其他宿主环境。当前仅包含命令行适配器 ``command_line``。

依赖方向：interfaces → application → infrastructure → domain
"""
