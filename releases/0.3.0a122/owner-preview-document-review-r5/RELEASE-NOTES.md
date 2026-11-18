# Amadeus 开发体验版 r5

这是供试用和反馈的 **Pre-release**，提供本地任务协作与受控 Agent 工作流。正式 Release 验收仍为 **BLOCKED**。仓库当前为私有，下载需要已有仓库访问权限。

## 立即体验

下载附件 **Amadeus-owner-preview-a122.zip**，解压后按包内 README 的三条命令安装并运行。Windows 快速入口需要 Python 3.12；安装会下载固定版本依赖，演示本身无需模型账号或模型费用。

默认演示使用模拟 Agent，展示任务创建、持久化、重开恢复、交接和不同身份评审；输出明确为 `simulation_only=true`、`verification=unverified`。

## 此版本提供什么

- 保留 a122 的本地持久化任务、SDK/CLI/MCP/HTTP 接口和审批约束。
- 附带 Linux 真实 Codex 任务入口、项目初始化与恢复查看工具；需要另备受支持 CLI、订阅登录及 Docker 环境，每个实际效果仍需审批。
- 新增固定 `review.md` 文档的手工接受／拒绝入口，使用新独立 Core 身份，确认文档、版本和决定后提交；文档接受不冒充代码验证。

核心 wheel、r4 任务入口及依赖约束未重建；本包没有模型登录凭据、项目数据库或模型 CLI。

## 实际验证

新文档入口的8项本地 Core 检查全部通过，包括接受／拒绝、错误项目／哈希／代码输入拒绝、确认取消、并发变更和固定版本绑定。确认输入使用确定性测试，不代表原生终端或真实客户端验收。

冻结 a122 已有8套选定完整测试结果，均无失败／错误；例如本次 Windows3.11 源码套件为2539通过、57平台跳过。它们不是8个完整正式矩阵组合。原有真实双 Codex 实验只证明逐项审批下的限定接力与独立验证，不证明跨厂商或无人值守自治。本次打包没有新增模型调用或候选执行。

[新入口代码与8项检查](https://github.com/JayChan697891/Amadeus/blob/5f7d75af15532b04e0fe5da3cc48a69e2531086b/docs/acceptance/evidence/core-preview-a122/document-review/summary.json) · [Windows3.11源码完整结果](https://github.com/JayChan697891/Amadeus/blob/5f7d75af15532b04e0fe5da3cc48a69e2531086b/docs/acceptance/evidence/core-preview-a122/full-windows311-source/summary.json) · [真实终端实验的精确范围](https://github.com/JayChan697891/Amadeus/blob/5f7d75af15532b04e0fe5da3cc48a69e2531086b/docs/acceptance/evidence/core-preview-a122/terminal-repaired/result/summary.json)

## 已知限制

macOS、Claude/Cursor 跨厂商协作、无人值守自主执行、完整当前平台矩阵和最终发布审核尚未完成。普通终端失败前不会自动保存可续接的模型进度；历史恢复实验使用明确的宿主检查点。历史 Ruff/格式 FAIL 保留，不能称全仓库静态检查通过。请先在独立试用目录中体验，勿据此用于生产数据。

ZIP 大小：341993字节。SHA-256：

`cf5c6125e56ec94ce12ff7a2aa36b4a97975240fcce1405569e3461ba1ee2e2c`

附件另含 SHA256SUMS、README.md 和 package-review.json。执行方：Codex。Refs #7、#11；本次不合并 main、不触发 GitHub Actions，不改变正式发布门槛。
