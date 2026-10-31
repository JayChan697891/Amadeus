# AgentSync 完整开发交接

交接日期：2026-10-30，America/Tijuana。执行方：Codex。
用途：让 Claude 从仓库恢复项目事实与约束；不是宣称 Claude 已读取或已开始执行。
这是经过整理的必要工作上下文，不是本聊天的逐字导出。原始附件、账号登录态、
本地 VM 磁盘和秘密不进入交接包。产品需求以仓库 SPECIFICATION 为准。

## 1. 从哪里继续

- 仓库：https://github.com/JayChan697891/agentsync
- 必须检出 `feature/m6-bounded-dispatch-wait-20261030`，不要默认使用 main。
- 交接前已上传 HEAD：`90272861566475bb571d36f5001009575abc06d2`。
  交接提交将在其上只增加文档；最终交接 HEAD 见 Git 日志和随包 DELIVERY.json。
- 受测产品：`d9b1abc22a6748575bf9935cb9c651172d250ba2`，0.3.0a25，schema14，63运行模块。
- PR30：https://github.com/JayChan697891/agentsync/pull/30
  基于 PR29 的 `feature/m5-verified-completion-20261029` / `3f622c3`，不是 main。
- PR29：https://github.com/JayChan697891/agentsync/pull/29
  基于 `feature/m5-candidate-execution-20261028` / `47ddda4`。
- main 核对值：`68588d5016678a001ae9d199a9201669988d2b50`。上述 PR 未被本执行方合并。
- 交接前工作树干净、无遗留开发任务/测试进程；本地专用 VM 已关闭。

```powershell
git clone --branch feature/m6-bounded-dispatch-wait-20261030 https://github.com/JayChan697891/agentsync.git F:\syuc\agentsync-claude
```

同一电脑已有工作区时，先读状态，不要覆盖/重新克隆到已有目录。
拿到仓库后先比对 SHA、读取 PR 的最新评论；此文件是日期快照，远端可能继续变化。

## 2. 只需先读这些文件

1. 根目录 CLAUDE.md、AGENTS.md、WORKFLOW.md。
2. `docs/SPECIFICATION.md`：M0–M9 共42项正式需求和 T01–T16。
3. `docs/PLAN.md` 与 `docs/PROGRESS.md`：先读顶部当前状态，后面大量内容是历史。
4. `docs/M5-FINAL-ACCEPTANCE.md`：唯一 M5 最终清单及六项退出条件。
5. `docs/acceptance/RELEASE-ACCEPTANCE-REPORT.md`、`requirements.json`。
6. `docs/CONTRACT.md`（早期基线，版本字段历史性）、相关功能合同和 `docs/LOCAL-DEBUG.md`。
7. 当前证据摘要 `docs/acceptance/evidence/alpha25-local-summary.json`。

不要一次加载所有历史报告/归档。按本轮改动选择相关源码和证据，以免浪费上下文。
原始用户粘贴计划并非根目录 outputs；不要假定本机原附件仍可访问。
仓库正式需求和冻结验收追踪才是可移交的产品依据。

## 3. 当前实际产品能力

Python>=3.11，发行名 agentsync-local；SDK、MCP、HTTP 共用 `Core.execute` 和 SQLite。
已有任务/租约/幂等、版本化上下文、交接、文件冲突、角色/审批/审计、Git工作区、
固定隔离验证器及纯离线调度/用量规划。能力存在不等于整个阶段正式验收通过。

源码地图：

| 路径 | 职责 |
|---|---|
| src/agentsync/core, storage | 统一业务、权限、协作、事务、迁移 |
| src/agentsync/verification | 固定候选、reservation/intent、一次执行、独立完成证明 |
| src/agentsync/adapters | Mock、Codex/Claude/Cursor协议、受控宿主进程、launch context、manager |
| scheduling.py, dispatch_planning.py, retry_planning.py | 离线调度/预算/重试建议，不能冒充自动真实执行 |
| mock_run_manager.py, mock_workflow.py | 模拟协作及端到端演示，始终保留 simulated/unverified |
| usage.py, integrations, sdk, cli.py | 用量、传输和用户入口 |
| tests, tools | 已有单元/集成/安全/隔离测试及本地调试工具 |

最新 M6 改动：`RunManager.dispatch_task` 返回未完成启动的 handle；`wait_dispatch`
以0–300秒观察既有启动回执。新旧入口共用 `_admit`，同请求混合并发仅启动一次。
等待超时/取消不取消后台工作，不释放历史容量；returned 不是运行成功或授权。
没有新增自动调度、跨实例恢复、重试、Core执行授权或真实客户端验证。

M5内部限定能力：B5 owner-only candidate 单次隔离执行；B4
`OwnerVerifiedTaskCompletion.complete_once` 强制独立 reviewer、精确两侧版本、
新鲜物理候选、固定可信 profile、真实 passed 结果及原子完成/证明/审计。
普通文本 review 仍 unverified；不得把任务 completed 当作 verified。

## 4. 验收与证据：精确区分范围

最新远端核查发现 Work 已对 PR30 的 HEAD9027286 作限定组件验收通过：
https://github.com/JayChan697891/agentsync/pull/30#issuecomment-6522196337
评论最后更新时间：2026-10-30T12:07:59Z。它不验收本次交接文档，也不代表 PR29、
整个 M5、真实 Agent、自主接力或发布通过。旧冻结摘要中的 Work pending 是当时快照，
不改写原始证据；本段记录后来的反馈。

| 冻结点 | 已实际执行 | 仍未执行/限制 |
|---|---|---|
| alpha25 d9b1abc | Windows3.14源码、Windows3.11源码、fresh Windows wheel、rebuilt sdist各99通过/0跳过；同74保留+25新增ID；Ruff/format176/mypy63通过 | 仅七个受影响模块；当前完整仓库/Linux/macOS/真实客户端未执行 |
| alpha23 e0b1d7c | Linux完整1895通过/4平台跳过；fresh Linux wheel/sdist受影响模块各63通过/1跳过；Windows3.11关键组6通过；三份真实Docker独立完成闭环 | 不可当作 alpha25 完整回归；不是全部平台/正式需求通过 |
| alpha22 bda2772 | B5生命周期源码和fresh Linux安装组各36通过/1跳过；成功/错误/超时/运行中取消/created后崩溃重开及精确清理 | 仅内部 owner 路径；不等于真实Agent或全部崩溃时点 |

alpha25：根负责人复核399Git输入、347匹配sdist成员、四环境各63实际模块来源、
JUnit/日志/包哈希；Astra独立组件审查无阻断发现（未重复包来源审计）。
归档：`releases/0.3.0a25/checkpoints/local-d9b1abc.tar.gz`，43个manifest成员，
1,140,241字节，SHA256：
`2f9fe7a7dadc874d3f14ee7744a202bcf07a609c924407c64245f54adc21a672`。
内含包、原始JUnit/日志、可复现驱动、manifest和独立审查。先验证哈希，再在专用
目录检查成员路径后解包；不要向用户工作区运行其中的破坏性场景。
alpha23/22等历史归档与摘要在对应 releases/、docs/acceptance/evidence/ 中。

42项正式需求的 execution_status 仍全部 not_run；组件测试不能自动改写为正式通过。
整体 M5 和 Release **BLOCKED**，Issue7/11保持open。

## 5. 剩余工作与建议顺序

M5范围仅五项：权限、风险审批、审计、独立验证、安全回归；不再拆新子阶段。

| 状态 | 工作/门槛 |
|---|---|
| BLOCKER B1 | 启用真实客户端前明确官方接口/版本、运行授权、费用与最小权限/资源/网络边界 |
| BLOCKER B2 / DEFERRED D1 | safe apply前审批绑定终检、撤销/过期、单次消费与实际效果一致；未接通则持续关闭 |
| BLOCKER B3 | 真实输出接入前完成生命周期审计、敏感字段脱敏/限量；原始stdout/stderr不可直接公开 |
| VERIFIED限定 B4/B5 | 上述内部独立完成/单次隔离执行，只对各冻结SHA及限定范围有效 |
| BLOCKER B6 | 对拟开放功能冻结最终源码/安装包/安全清单与证据并获独立验收；不是再做一轮文档子阶段 |
| DEFERRED D2/D3 | Agent-facing接线、自动验收、跨进程恢复/重试、智能调度和真实双Agent接力，按M6–M9推进 |
| DEFERRED D4/D5 | 完整OS/Python矩阵、费用对账、非关键增强和历史材料重排；不得以此拖住无执行原型 |

接手第一轮：

1. 只读核对 Git、PR30/29、Issue7/11 最新反馈，确认已有限定验收，不重做它们。
2. 读 M6 实际入口和 B1/B3，选一个可完整交付的剩余产品工作；缺授权时可继续受控
   本地协议/生命周期实现，不能默认为可运行真实客户端。
3. 真实 Codex/Claude/Cursor 分别验证，Mock不顶替；历史 Codex单次订阅测试授权均已
   使用或结束，没有可沿用的无限运行授权。真实启动前确需新授权时只问最小问题。
4. 相关安全门禁齐备后才接 Agent-facing执行/自动完成；safe apply继续单独门禁。
5. M9按42需求完整执行并交 Release Acceptance Report，区分通过、失败、未运行、
   受限、未验证。关键安全失败或真实自主接力未验证时不得发布通过。

不要凭本交接自行合并任何 PR、重新规划整个项目或启动付费/外部云计算。

## 6. 本地环境与可复现测试

同机源码 `F:\syuc\agentsync-execution-intent`，调试/缓存/临时项目 `D:\agentsync-debug`。
Python3.14：`D:\agentsync-debug\venv\Scripts\python.exe`；3.11：
`D:\agentsync-debug\alpha13-python311-1_06_4p9\venv\Scripts\python.exe`。
依赖锁在 requirements-lock.txt / requirements-dev-lock.txt 和 pyproject.toml。
新机器需自行在授权本地目录准备依赖；仓库不会携带已登录客户端、venv或Docker镜像。

alpha25原始本地输出：`D:\agentsync-debug\alpha25-dispatch-ezd3m67l`，
最后检查点：`D:\agentsync-debug\continuation-checkpoint-final-9027286.json`。
这些本地路径不可作为换机器后的前置依赖；必要原始证据和驱动已在仓库归档。

在专用调试环境中设置 PYTHONPATH 为本次检出的 src、禁用用户site及字节码写入，
将pytest临时目录/缓存固定到D盘，避免载入其他工作区的 editable 安装。
本轮受影响组为：

```text
tests/unit/test_adapter_run_manager.py
tests/unit/test_mock_run_manager.py
tests/unit/test_cursor_adapter.py
tests/integration/test_adapter_manager_core_boundary.py
tests/integration/test_mock_workflow.py
tests/integration/test_mock_run_manager_core_boundary.py
tests/integration/test_cursor_adapter_core_boundary.py
```

检查命令：`python -m ruff check src tests tools`、
`python -m ruff format --check src tests tools`、`python -m mypy src/agentsync`。
pytest按改动选择上述组，显式 `--basetemp D:/agentsync-debug/<独立目录>` 与
`-o cache_dir=D:/agentsync-debug/<独立缓存>`。修复规范可用安全 --fix，禁止unsafe-fixes或关规则。
不要无必要重复全套测试；代码变化、失败或未解除风险才扩大验证。

真实隔离由专用D盘QEMU/Alpine/Docker环境提供，详见 LOCAL-DEBUG.md。当前VM关闭；
重启/关闭先核对实际进程身份，不信任旧PID。没有已验证隔离时 fail closed，
绝不在宿主直接运行不可信candidate/pytest/setup/import作为替代。

## 7. 不可丢失的用户约束

- GitHub仅代码/文件存储、PR/Issue；禁止Actions测试/调试/benchmark/dispatch/rerun。
  工作流保持manual-only，提交使用 `[skip ci]`。
- 不直接修改/合并main，不重置覆盖用户文件，不删除原始证据/失败测试，不伪造通过。
- 不付费API、不修改账号配置。原有凭据不是对新真实任务的运行授权。
- 测试只用本仓库和授权临时项目；不做外部探测、漏洞利用、认证绕过或提权。
- 遇到Daybreak/安全拦截不重复同请求、不绕过；保留可见原文/时间/请求ID，标BLOCKED或NOT RUN，继续独立普通开发。
- 减少不必要子任务、重复报告/证据、内存/存储消耗；完成一个可验收任务再开始下一个。
- 模型/工具能力必须真实；Claude环境没有Sol/Astra时不得虚构调用。
- 不能承诺关机后仍在云端继续；尚无可据此宣称有效的云端环境/计划运行证据。
- 阶段结束实际读文件/测试结果，保存版本/SHA/限制，更新分支PR交独立验收。

## 8. 可直接给 Claude 的启动指令

“请接手 AgentSync，检出 feature/m6-bounded-dispatch-wait-20261030，先读 CLAUDE.md
和 docs/HANDOFF-CLAUDE.md，核对远端最新反馈。承接受测 d9b1abc 的进度，不重做已验收
M6组件、不新增M5子阶段。只在授权本地环境开发测试，GitHub仅存储/PR/Issue，禁用
Actions和付费调用，不合并main。先报告真实剩余缺口和一个有界产品任务，再自主实现、
检查实际文件/结果、必要修复、提交上传；未知/未执行项如实标记，保持发布BLOCKED。”
