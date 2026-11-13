> 已按所有者要求公开归档。两版交付文件见 [releases/](releases/)，恢复步骤见 [RECOVERY.md](RECOVERY.md)。历史报告中的“未公开发布”描述的是归档前状态。

# Amadeus

免费、MIT 开源许可、本地运行的多 Agent 协作核心。MCP、Python SDK 和 HTTP 共用
一个 SQLite 数据库。核心协作无需模型或付费 API，云端开发环境为可选。

当前为 **0.3.0a110 开发源码，正式发布仍处于阻断状态**。
已完成一次受明确审批控制的真实 Codex 双身份连续流程：生成提案、独立 Docker
验证、自动创建下游任务并共享固定版本上下文，再接收独立模型审查文档。
文档接受不等于测试验证；当前证据不涵盖 Claude/Cursor 或无人审批的自动应用。
详见[真实流程证据](docs/acceptance/evidence/m7-continuous-live/summary.json)。
支持上下文不可变版本、来源与摘要、中文短词检索，以及
固定上下文版本的结构化交接、接收、拒收、撤回和重新分配。交接立即撤销旧租约；
接收后的预约最长 300 秒，避免离线接收者让任务卡死。M0–M2 历史桌面 MCP 已由用户确认连接，
原生工具与双会话流程已实际验证。不同证据边界、实际检查结果分别见
[兼容性表](docs/COMPATIBILITY.md)、[测试报告](docs/TEST-REPORT.md) 和 [进度](docs/PROGRESS.md)。
[本轮接入说明](docs/M2-CONTINUATION.zh-CN.md)包含原生安装器和完整复现步骤。

[项目仓库](https://github.com/JayChan697891/Amadeus)

## Windows 安装与演示

在本项目目录打开 PowerShell，已安装 Python 3.11 或以上版本：

```powershell
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
& .\.venv\Scripts\python.exe -m pip install -e . --no-deps
& .\.venv\Scripts\amadeus.exe --data-dir "$PWD\local-data\demo" demo
& .\.venv\Scripts\python.exe -m pytest
```

不需要激活虚拟环境或修改执行策略。演示会注册两个模拟 Agent，让 A 认领任务，
验证 B 的重复认领被拒绝，再由 A 提交结果、B 留下验收记录，重新打开数据库检查持久化。
重复演示时使用新的专用数据目录。
仅安装运行依赖时，改用 requirements-lock.txt。两份锁文件都是 Windows 实测的精确版本快照，
不声称已经完成所有平台的统一解析验证。

## 接入

推荐使用 `amadeus` 命令。已有集成仍可使用 Python 发行包 `agentsync-local`、
Python 导入名 `agentsync`、旧命令 `agentsync` 和 `python -m agentsync`。
MCP 标识、`AGENTSYNC_*` 设置、默认数据目录名 `AgentSync` 和数据库文件名
`agentsync.db` 延用原有名称。

所有 MCP 进程都应指定同一个**绝对路径**数据目录，运行命令为
`python -m agentsync --data-dir 绝对路径 mcp`。配置样例在 examples/mcp_clients。
项目管理员令牌用于注册 Agent，会话令牌用于项目操作；不要提交到仓库。

交付已验证候选时，所有者可通过 SDK 的 `owner_call` 或 `amadeus owner`
预览并批准交付计划，再凭批准后的版本和计划摘要显式调用
`publish_candidate_delivery`，创建受管仓库的私有 Git 引用。通过
`get_candidate_delivery_status` 查看交付结果。

HTTP 需要单独设置 `AGENTSYNC_HTTP_TOKEN`，再执行 `amadeus serve`，
默认监听 127.0.0.1:8765。向 `/v1/操作名` 提交 JSON，并附带 Bearer 身份凭据。
完整参数见 [接口契约](docs/CONTRACT.md)。

同一操作在三种接口使用一致的 Core 规则。SQLite WAL 仅用于本机磁盘；不要放到网络共享盘。
用户传入的结果、描述和验收证据均是文本，系统不会执行其中的命令。

## 范围与继续开发

本批包括项目隔离、身份会话、心跳、任务依赖、原子认领、版本、租约、过期回收、
幂等写入、结果提交与独立 Agent 验收记录、MCP/SDK/HTTP 接入。
普通文字验收不等于测试证据；独立验证完成要求绑定实际 Docker/Core 证明。

共享上下文和交接的完整接口见 [M3 契约](docs/M3-CONTRACT.md)。运行
`python examples/m3_handoff.py --data-dir 绝对路径的新测试目录`，可复现三个独立 MCP
客户端进程的 A→B→审查者接力；这是协议和进程验证，不代表模型或桌面宿主兼容性。

文件锁、受管 Git Worktree、冲突检测、用量统计及可选多模型接口已有实现。
真实 Codex 受控协作有局部证据，跨客户端兼容和更广泛自主调度仍待完成，
见 [计划](docs/PLAN.md)。GitHub 用于分支/PR 保存，本地完成测试；
不会直接修改或合并 main，没有进行付费模型 API 调用。

## 发布验收

路径与文件摘要检查、文件/目录协作式租约锁已实现；不保证阻止外部编辑器。
已有实际受管工作树、合并冲突、独立 Docker 验证及受控双 Codex 接力证据，
各自冻结版本和限制见 [验收报告](docs/acceptance/RELEASE-ACCEPTANCE-REPORT.md)。
参见 [42 项需求验收设计](docs/acceptance/DESIGN.md) 和客户端矩阵；
协议进程测试、Mock 和历史连接结果不能代替真实客户端自主协作验收。

M4B 增加独立受管 Git 工作树、真实合并冲突报告及待人工批准的不可变合并候选。
不自动写入用户分支，不导入未提交私有内容。未验证客户端和正式发布仍有门槛。

## 权限与升级

新成员和从旧数据库迁移的成员默认只读；所有者需明确重授 worker/reviewer 权限。
任务、上下文和历史记录保留。升级前请阅读 [M5A 指南](docs/M5A-GUIDE.md)。
所有者接口与普通 Agent/MCP 工具分开；审批只记录绑定候选 SHA 的决定，不自动应用。
现有不同 Agent 的审查仍是证据声明，真实隔离验证器尚未实现，正式发布维持阻断。
