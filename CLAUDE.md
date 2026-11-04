# AgentSync — Claude 接手入口

> 已作废（2026-11-04）：用户取消本次打包交接，恢复 Codex 开发。
> 以下内容仅为历史记录；当前入口为 AGENTS.md、WORKFLOW.md 和 docs/PROGRESS.md。

用户已请求允许 Claude 接手后续工作。先读 [完整交接](docs/HANDOFF-CLAUDE.md)，
再读 AGENTS.md / WORKFLOW.md。不要从 main 重做项目。

继续分支：`feature/m6-bounded-dispatch-wait-20261030`。
受测产品冻结提交：`d9b1abc22a6748575bf9935cb9c651172d250ba2`，0.3.0a25/schema14。
本次交接只更新文档，不改变上述受测代码。GitHub 仅存储/PR/Issue，禁用 Actions 执行。
不得擅自合并 main、付费调用、重试已用完的真实客户端单次授权或绕过安全拦截。

AGENTS.md 的 Sol/Astra 分工是原 Codex 环境的能力策略，不要求 Claude 冒充或
调用不可用模型；接手时如实报告实际模型和工具能力。保持独立审查、证据和发布门槛。
小范围推进、复用测试、减少子任务和重复记录；不要新建 M5 子阶段。
