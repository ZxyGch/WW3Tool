"""工作流基础设施层：外部 I/O、适配器与运行时配置。

本子包对接 WW3 网格生成、强迫场导入、远程 SSH、可视化等与领域逻辑解耦的实现细节；
应用层通过此处适配器调用，避免直接依赖 Qt 或具体文件布局。

[EN] Workflow infrastructure layer: external I/O, adapters, and runtime configuration.

This sub-package handles implementation details decoupled from domain logic, such as
WW3 grid generation, forcing field import, remote SSH, and visualization;
the application layer calls through adapters here to avoid direct dependency on Qt
or specific file layouts.
"""
