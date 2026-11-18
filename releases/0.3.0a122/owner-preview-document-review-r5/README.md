# Amadeus a122 开发体验版 r5

[下载体验包](Amadeus-owner-preview-a122.zip)，解压后按包内 README 的三条命令安装和体验。Windows 需要 Python 3.12；默认演示无需模型账号，展示持久化任务、恢复、交接及独立身份评审，明确标记为模拟／未验证。

本次新增 `review.md` 的手工接受／拒绝入口：显示固定版本文档和决定，确认后由新独立身份提交评审。8 项真实 Core 检查全部通过；文档评审仍为 unverified，不代表代码执行验证。参数见包内指南。

核心 wheel、依赖约束、初始化、恢复和 r4 任务入口保持原样；旧体验包及历史证据保留。校验值见 [SHA256SUMS](SHA256SUMS)，来源见 [package-review.json](package-review.json)。本次没有新增模型调用或候选执行。

这是开发体验版；跨厂商、无人值守、完整平台矩阵和正式发布验收尚未完成。正式 Release 保持 **BLOCKED**。
