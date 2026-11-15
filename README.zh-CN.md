> 已按所有者要求公开归档。两版交付文件见 [releases/](releases/)，恢复步骤见 [RECOVERY.md](RECOVERY.md)。历史报告中的“未公开发布”描述的是归档前状态。

# Amadeus

免费、MIT 开源许可、本地运行的多 Agent 协作核心。MCP、Python SDK 和 HTTP 共用
一个 SQLite 数据库。核心协作无需模型或付费 API，云端开发环境为可选。

当前为 **0.3.0a117 开发源码，正式发布仍处于阻断状态**。冻结的 0.3.0a116
已完成现有 Windows/Linux 六组本地矩阵，macOS 尚未实测；这些证据不覆盖新增开发代码。
交付顺序见[总计划](docs/PLAN.md)。

新增可恢复的持久 Mock 工作流入口：
`amadeus --data-dir 绝对路径 workflow start|resume|status|cancel`，或 SDK 的
`owner_call("start_mock_workflow", ...)` 等对应操作。通过有界标准输入 JSON 提供
专用空项目的所有者认证，不把凭据放在命令参数中；每个项目绑定一个持久运行。
重试时间、预算预留、取消状态和交接进度会保存；重开不重置预算，派发后结果未知
时不重试。`waiting` 表示需到保存的重试时间后，以当前版本再次调用 `resume`。
这仍是模拟工作流，不启动真实模型；费用与 Token 预留是明确标注的模拟估算，
不代表实际账单。[英文用法与配置](README.md#isolated-simulated-workflow)及
[当前验证状态](docs/PROGRESS.md)分别记录使用方式和未完成验收。

新增受限的跨客户端评审路径：`ProposalReviewInput` 和 `ProposalReviewQueueItem`
可接收已准备好的 Codex、Claude Code 或 Cursor 适配器，将已验证的来源产物固定到
有依赖关系的后续任务，只保存 `review.md` 评审文档，文档仍未经过独立验证。
`ProposalHandoff` 对 Claude/Cursor 使用该路径，保留已有 Codex 交接格式。
启动仍需精确批准；评审模式拒绝 Codex/Claude 报告的工具事件。
Cursor 的终态响应不能证明未调用工具，仍须满足原有宿主隔离条件。
真实 Claude/Cursor 兼容性尚未验证，协议模拟进程测试不能替代真实验收。
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
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
& .\.venv\Scripts\amadeus.exe --data-dir "$PWD\local-data\demo" demo
& .\.venv\Scripts\python.exe -m pytest
```

不需要激活虚拟环境或修改执行策略。演示会注册两个模拟 Agent，让 A 认领任务，
验证 B 的重复认领被拒绝，再由 A 提交结果、B 留下验收记录，重新打开数据库检查持久化。
重复演示时使用新的专用数据目录。
仅安装运行依赖时，使用 `pip install -e .`；当前依赖以 `pyproject.toml` 声明为准。
两份 `requirements*-lock.txt` 保留旧 Windows 环境快照，并非当前跨平台锁文件。
离线安装需事先准备与所选 Python 版本兼容的依赖包。

## 体验持久化协作

[预览目录](releases/0.3.0a117/demo-fc27f15/)提供同一冻结运行时的 wheel 和源码包。
Windows3.12 的源码安装、源码包安装，以及 Linux3.14 源码包安装，各通过10项现有定向用例，
与先前 wheel 的用例结果一致。[Linux 实测](docs/acceptance/evidence/durable-demo-a117/sdist/linux/summary.json)
使用同一份源码包，未重新构建。
[安装证据与保留的准备失败](docs/acceptance/evidence/durable-demo-a117/sdist/summary.json)
仅覆盖该演示的定向验证，不代表完整 a117 发布矩阵通过。

完成上面的 Windows 安装后，在项目目录运行；每次使用一个尚不存在的新目录：

```powershell
& .\.venv\Scripts\amadeus.exe --data-dir "$PWD\local-data\amadeus-demo-01" demo --durable
```

Linux 可使用 `/tmp/amadeus-demo-01`。演示复用现有核心：创建任务、保存一次
重试计划、在新进程中读取并继续、向第二个工作者结构化交接，再由第三个身份
留下评审。结果会展示同一持久任务及已接受的交接。已有目录会被拒绝，不覆盖
任何数据；每次体验请换新目录。数据库留在本地，不上传。

三个身份均为模拟 Agent，没有模型或 API 调用。输出明确保留
`simulation_only/unverified`：证明协作和状态接续，不证明代码正确，也不证明
真实模型异常退出后的恢复。所有者凭据只在内存和标准输入传递，不打印或保存；
主程序退出后，这个短演示不提供凭据找回。实际项目需自行保管所有者凭据，
使用上面的 `workflow` 操作管理生命周期。

当前版本0.3.0a117/`fc27f15`已有[两个真实 Codex 的连续流程证据](docs/acceptance/evidence/durable-demo-a117/live/summary.json)：
四个明确审批点、独立 Docker 验证、固定上下文交接，以及新进程重开时不重复调用。
第二个模型的评审只作为文档接收，仍标记未验证。它与本模拟演示分开，不能替代
真实崩溃恢复、跨厂商、无人审批或正式发布验收。[历史a109证据](docs/acceptance/evidence/m7-continuous-live/summary.json)
继续保留；剩余要求见[总计划](docs/PLAN.md)。

已有 Linux 验证工具另提供固定的 `--demo` 入口。当前仓库、已安装的 Amadeus、
Git 和项目测试环境中预置的可信镜像齐备后，可以执行：

```sh
python -I -B tools/run_proposal_candidate_pilot.py --demo \
  --root /root/amadeus-proposal-pilot-demo-01 \
  --image-id sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
```

每次使用新目录。工具在 Docker 中验证固定的 `add.py`，随后将依赖任务及固定
版本的验证上下文交给另一 Core 身份，并重开 Core 核对和继续。它不下载镜像，
不在宿主执行候选代码，不修改原基线。身份由确定性程序驱动，不调用模型；
后续文字评审仍未验证，同一进程重开 Core 也不是崩溃恢复测试。此入口属于仓库
工具，不包含在 wheel 中。[本次 Linux 实测](docs/acceptance/evidence/durable-demo-a117/verified-linux/lead-review.json)
通过8项固定用例和19项隔离检查，不能替代真实模型或正式发布验收。

## 接入

推荐使用 `amadeus` 命令。已有集成仍可使用 Python 发行包 `agentsync-local`、
Python 导入名 `agentsync`、旧命令 `agentsync` 和 `python -m agentsync`。
MCP 标识、`AGENTSYNC_*` 设置、默认数据目录名 `AgentSync` 和数据库文件名
`agentsync.db` 延用原有名称。

所有 MCP 进程都应指定同一个**绝对路径**数据目录，运行命令为
`python -m agentsync --data-dir 绝对路径 mcp`。配置样例在 examples/mcp_clients。
项目管理员令牌用于注册 Agent，会话令牌用于项目操作；不要提交到仓库。

项目所有者可用 `amadeus --data-dir DATA_DIR owner sync_relay_usage` 同步受控中继回执。
从标准输入提供包含 `project_id`、`admin_token`、`task_id`、原绑定的绝对路径
`scratch_root` 和 `receipts` 的 JSON 对象。SDK 可调用 `owner_call("sync_relay_usage", **payload)`。
`get_usage_summary` 将回执和调用方导入的用量分开显示。查询单次回执时，使用返回的
`run_id`、`kind` 和 `provenance="controlled_relay_receipts"` 调用 `get_usage_run`。
缺失的终态和用量保持未知。同步不会启动客户端，回执也不能证明账单或实际费用。
缺少精确启动绑定的历史单客户端或提案回执会返回 `relay_usage_unsupported`。

项目自身的模型建议调用可使用本地 SDK 异步方法 `request_model_advice`，传入所有者身份、
固定 `request_id`、已构造的 provider、建议请求和该请求的明确单次授权。
它先持久记录未知意图再调用；相同请求重放只读历史，不重复发送。
通过 `owner_call("get_provider_usage_call", ..., request_id=...)` 查询中断后的观察，
不需要为查询再调用模型。`get_usage_summary` 将 `local_provider_calls` 与客户端回执、
导入用量分开汇总；Token 上报、实际耗时、可选费率估算和远端未知结果分别标注，
不把估算视为真实账单。此连接已编写，按当前“先写完整代码”安排尚未执行测试。

双方会话都过期而交接仍待接收时，所有者可先通过 `list_handoffs` 查询交接，
再以精确任务版本调用 `recover_handoff`。原交接包和上下文保留，任务恢复待认领；
此操作只恢复协作状态，不会重启模型或解除未知执行的限制。

已保存的未完成源码可由本地宿主通过 `OwnerContinuation` 接续：生产者仍持有租约时，
用 `ControlledRelay.publish_progress_checkpoint` 保存已知进度；确认原进程已失败并结束后，
固定该进度与失败记录，预览并确认任务及依赖转接计划，再为接收者准备独立工作区和新的精确启动授权。
原失败任务不会伪装成完成，接收者产物仍须独立验收；结果未知或已有派发意图时不会自动补发。
此连接已完成源码审查，尚未执行测试，也没有进行新的真实客户端调用。

交付已验证候选时，所有者可通过 SDK 的 `owner_call` 或 `amadeus owner`
预览并批准交付计划，再凭批准后的版本和计划摘要显式调用
`publish_candidate_delivery`，创建受管仓库的私有 Git 引用。通过
`get_candidate_delivery_status` 查看交付结果。

要把已验证候选集成到普通本地仓库，请另行申请 `apply_merge_candidate` 审批。
在交付参数中增加绝对路径 `target_root`、`worktree_path` 和新分支名 `destination_branch`，
调用 `preview_candidate_integration`。用返回的计划哈希调用 `approve_candidate_integration`，
再用该哈希与审批后的版本调用 `integrate_candidate`。目标仓库必须干净，且 HEAD 等于候选基线。
新分支和独立工作树使用候选的确切文件字节，保留原工作树及索引。
`get_candidate_integration_status` 只观察结果。中断后保留已使用的审批及目标预留，
`partial` 或 `unknown` 状态不会触发重试或自动清理。

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
