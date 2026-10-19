# M2 接入验收续作 — v0.1.0a2

日期：2026-10-19。本轮继续 M0–M2，没有扩展到 M3–M9。

## 已完成

1. 增加完整原生双会话验收：A 创建/认领/运行/提交，B 读取同一真实任务、重复认领被拒，
   再由 B 验收。任务版本依次为 1→2→3→4→5，结果和审核身份一致。
2. 完整退出探测宿主后重新启动，通过新的原生 MCP 连接及新 Core 读取相同结果和审核记录。
3. 增加公开 CLI 安装器，实际注册本机 Codex 共享 MCP 条目。重复安装返回 already_configured；
   冲突配置拒绝覆盖，dry-run 不创建数据目录、不写 MCP 配置。
4. 原生宿主不使用临时配置覆盖，读取真实注册条目，发现全部 11 个工具。一次故意使用
   无效会话的真实调用返回预期 unauthorized，证明请求实际到达 AgentSync。
5. 用户在当前桌面端确认：**“已出现并显示已连接”**。M2-05 连接门槛据此关闭。

界面状态来自用户观察；工具调用和协作状态来自实际执行结果。没有把后台探针冒充桌面自动化。
Computer Use 插件的 guidance.md 明确禁止自动操作 ChatGPT 桌面 UI，因此本轮没有通过
该技能执行 UI 动作；这不影响公开 CLI/API 验证。没有启动模型推理、付费服务或公开发布。

## 实测

| 检查 | 结果 |
|---|---|
| Python 3.14.6 源码测试 | 92 passed in 7.40s |
| Python 3.12.14 全新安装 a2 wheel 后测试 | 92 passed in 7.55s |
| Ruff / mypy | 通过，15 个源文件类型检查无问题 |
| 原生隔离双会话流程 | 实际执行通过，包括宿主重启后的精确比对 |
| 实际注册配置加载 | connected，11 个工具，返回正确的 AgentSync 错误信封 |
| 桌面 MCP 连接状态 | 用户确认已连接 |

增加的 28 项自动检查包括：安装器拒绝覆盖/失败关闭/安全参数/环境先决条件、无副作用路径查询、
证据内容与脱敏检查。证据内容检查不冒充新的真实客户端调用；原生调用由单独探针实际执行。

## 复现与接入

已安装项目的 Python 环境中运行：

```powershell
& .\.venv\Scripts\python.exe examples\mcp_clients\install_codex.py --dry-run
& .\.venv\Scripts\python.exe examples\mcp_clients\install_codex.py
& .\.venv\Scripts\python.exe tests\manual\probe_codex_collaboration.py
& .\.venv\Scripts\python.exe tests\manual\probe_registered_codex.py
```

安装器使用公开的 codex mcp get/add，不编辑其他服务。默认共享状态在用户本地数据目录
AgentSync 中，可用 --data-dir 指定其他绝对本地路径。Windows 需原生 Codex.exe，若 PATH
未提供，用 --codex 指定。不要传 .cmd/.ps1 启动包装。移动代码或 Python 环境后应私下核对
原条目，明确移除旧条目后再重新注册；安装器不会悄悄覆盖旧配置。

原生 CLI 将原 node_repl 的空 args=[] 省略了；已对比确认其余配置的语义不变。
配置备份和原始探测日志留在忽略的本地 work 目录，未纳入源码包。

## 证据与下一阶段

- codex-collaboration-probe.json：完整协作状态、结果摘要、审核和重启比对。
- codex-registration-probe.json：实际共享配置加载的原生连通结果。
- desktop-connection-confirmation.json：用户桌面连接状态确认及证据边界。
- pytest-m2-followup.xml / pytest-m2-followup-python312.xml：本轮两套测试报告。

M0–M2 第一批已完成。下一批 M3-01–04：项目上下文、FTS 检索、来源版本、结构化交接与拒收重分配。
本轮 AGENTS.md 将范围限定为 M0–M2，因此 M3 代码没有提前生成。
