WW3Tool 重构计划

1.src 的代码只作为备份和重构参考，不允许 src2 引用

2.src2 作为重构的项目目录，我要求新的 WW3Tool 支持两种使用方法：CLI 和 Desktop

CLI 要默认从 params.yml 中读取运行参数，Desktop 要调用 CLI 的代码实现配置 WW3 的逻辑，负责 UI 的展示，通过修改 params.yml 来运行 支持两种使用方法：CLI

3.要保证 Desktop 的 UI 和 src 的完全一致，但是内部关于 WW3 文件的逻辑要由 CLI 实现，把 src 原本的逻辑抽离为独立的 CLI 脚本