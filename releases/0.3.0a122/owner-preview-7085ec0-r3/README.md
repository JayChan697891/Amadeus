# Amadeus a122 开发体验包

下载并解压 [Amadeus-owner-preview-a122.zip](Amadeus-owner-preview-a122.zip)，从包内 README.md 开始。

此次安装说明加入[Windows 3.12 依赖约束](constraints-windows312.txt)，固定到已测试的运行环境。
原安装包和三个示例未改变；旧 r2 原件保留，不需要为已有可用环境重新安装。

默认是无需模型账号的本地模拟协作演示；Linux 真实任务入口及初始化示例随包提供，真实实验仍受审批和验收限制。正式 Release 仍为 BLOCKED。

包内同版 Linux 终端入口现已完成一次真实验证：两个 Codex 调用、一次固定加法程序的隔离执行，
生产者任务由独立身份验收完成；接收方已提交评审，评审内容仍为未验证。
这是逐项审批的限定流程，不代表无人值守或跨厂商协作通过。
[实际结果与边界](../../../docs/acceptance/evidence/core-preview-a122/terminal-repaired/result/summary.json)。
ZIP 原件不变，包内文档保留打包时的检查点；后续状态以此说明和当前进度为准。

归档校验值见 [SHA256SUMS](SHA256SUMS)，检查记录见 [package-review.json](package-review.json)。
