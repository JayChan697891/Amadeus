# Amadeus a122 开发体验包 r4

下载并解压 [Amadeus-owner-preview-a122.zip](Amadeus-owner-preview-a122.zip)，按包内 README 的三条命令安装和体验。Windows 需要 Python 3.12；默认是无需模型账号的本地模拟协作演示。

本修订修复 Linux 真实任务入口的文件读取：任务和用例按原有1000/32768字节上限限量读取，误选大文件时不会先把整个文件读入内存。已有审批、超时、执行和错误码未改变。[修复及实际检查](../../../docs/acceptance/evidence/core-preview-a122/terminal-input-bounds/summary.json)：14项 Windows 检查通过，4项 Linux 专用检查跳过；两项原失败保留。

核心 wheel、固定依赖约束、初始化及恢复脚本沿用原件。无需为已有核心环境重新安装；本次修复只在随包的 `examples/verified_codex_task.py` 中。旧 r3 包保留。校验值见 [SHA256SUMS](SHA256SUMS)，内容与来源见 [package-review.json](package-review.json)。

此前7085ec0入口有一次逐项审批的真实双 Codex 限定证据，本次没有重跑模型或 Linux 终端实验。默认模拟输出仍为 `simulation_only=true / verification=unverified`；跨厂商、无人值守及正式 Release 未通过。正式 Release 保持 **BLOCKED**。
