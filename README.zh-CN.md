> 已按所有者要求公开归档。两版交付文件见 [releases/](releases/)，恢复步骤见 [RECOVERY.md](RECOVERY.md)。历史报告中的“未公开发布”描述的是归档前状态。

# AgentSync

免费、MIT 开源许可、本地运行的多 Agent 协作核心。MCP、Python SDK 和 HTTP 共用
一个 SQLite 数据库。已从 M0–M2 继续实施 M3，无需模型或付费 API，云端开发环境为可选。

当前为 **0.2.0a2 M4-01/02 Alpha 检查点**：支持上下文不可变版本、来源与摘要、中文短词检索，以及
固定上下文版本的结构化交接、接收、拒收、撤回和重新分配。交接立即撤销旧租约；
接收后的预约最长 300 秒，避免离线接收者让任务卡死。M0–M2 历史桌面 MCP 已由用户确认连接，
原生工具与双会话流程已实际验证。不同证据边界、实际检查结果分别见
[兼容性表](docs/COMPATIBILITY.md)、[测试报告](docs/TEST-REPORT.md) 和 [进度](docs/PROGRESS.md)。
[本轮接入说明](docs/M2-CONTINUATION.zh-CN.md)包含原生安装器和完整复现步骤。

## Windows 安装与演示

在本项目目录打开 PowerShell，已安装 Python 3.11 或以上版本：

```powershell
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
& .\.venv\Scripts\python.exe -m pip install -e . --no-deps
& .\.venv\Scripts\python.exe -m agentsync --data-dir "$PWD\local-data\demo" demo
& .\.venv\Scripts\python.exe -m pytest
```

不需要激活虚拟环境或修改执行策略。演示会注册两个模拟 Agent，让 A 认领任务，
验证 B 的重复认领被拒绝，再由 A 提交结果、B 留下验收记录，重新打开数据库检查持久化。
重复演示时使用新的专用数据目录。
仅安装运行依赖时，改用 requirements-lock.txt。两份锁文件都是 Windows 实测的精确版本快照，
不声称已经完成所有平台的统一解析验证。

## 接入

所有 MCP 进程都应指定同一个**绝对路径**数据目录，运行命令为
`python -m agentsync --data-dir 绝对路径 mcp`。配置样例在 examples/mcp_clients。
项目管理员令牌用于注册 Agent，会话令牌用于项目操作；不要提交到仓库。

HTTP 需要单独设置 `AGENTSYNC_HTTP_TOKEN`，再执行 `python -m agentsync serve`，
默认监听 127.0.0.1:8765。向 `/v1/操作名` 提交 JSON，并附带 Bearer 身份凭据。
完整参数见 [接口契约](docs/CONTRACT.md)。

同一操作在三种接口使用一致的 Core 规则。SQLite WAL 仅用于本机磁盘；不要放到网络共享盘。
用户传入的结果、描述和验收证据均是文本，系统不会执行其中的命令。

## 范围与继续开发

本批包括项目隔离、身份会话、心跳、任务依赖、原子认领、版本、租约、过期回收、
幂等写入、结果提交与独立 Agent 验收记录、MCP/SDK/HTTP 接入。
验收记录不等于自动验证测试证据；M5 才增加独立证据核验。

共享上下文和交接的完整接口见 [M3 契约](docs/M3-CONTRACT.md)。运行
`python examples/m3_handoff.py --data-dir 绝对路径的新测试目录`，可复现三个独立 MCP
客户端进程的 A→B→审查者接力；这是协议和进程验证，不代表模型或桌面宿主兼容性。

文件锁、Git Worktree、真实 Agent 控制适配器、自主调度、多模型和费用统计
按 M4–M9 后续实施，见 [计划](docs/PLAN.md)。用户已授权 GitHub 分支/PR 保存和云端环境；
不会直接修改或合并 main，没有进行付费模型 API 调用。

## 发布验收

路径与文件摘要检查、文件/目录协作式租约锁已实现；不保证阻止外部编辑器。
Git worktree、合并冲突、独立证据执行、真实控制适配器和自主接力尚未完成。
参见 [42 项需求验收设计](docs/acceptance/DESIGN.md) 和客户端矩阵；
协议进程测试、Mock 和历史连接结果不能代替真实客户端自主协作验收。
