WW3Tool 重构计划

1.src 作为项目主目录，旧的 src 代码已删除

2.src 作为重构后的项目目录，WW3Tool 支持两种使用方法：CLI 和 Desktop

CLI 要默认从 params.yml 中读取运行参数，Desktop 要调用 CLI 的代码实现配置 WW3 的逻辑，负责 UI 的展示，通过修改 params.yml 来运行 支持两种使用方法：CLI

3.要保证 Desktop 的 UI 和 src 的完全一致，但是内部关于 WW3 文件的逻辑要由 CLI 实现，把 src 原本的逻辑抽离为独立的 CLI 脚本

4.注意保持良好的设计模式
