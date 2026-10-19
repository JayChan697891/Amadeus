# AgentSync

免费、MIT 开源许可、本地运行的多 Agent 协作核心。MCP、Python SDK 和 HTTP 共用
一个 SQLite 数据库。本批只实现 M0–M2，无需模型、付费 API 或云服务器。

当前为 **0.1.0a1 Alpha 实现**。真实桌面客户端是否接通、哪些检查已经运行，分别见
[兼容性表](docs/COMPATIBILITY.md)、[测试报告](docs/TEST-REPORT.md) 和 [进度](docs/PROGRESS.md)。

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

共享上下文、文件锁、Git Worktree、真实 Agent 控制适配器、自主调度、多模型和费用统计
按 M3–M9 后续实施，见 [计划](docs/PLAN.md)。没有进行付费模型调用、公开推送或公开发布。
