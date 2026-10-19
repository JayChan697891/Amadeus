# AgentSync 第一批交付说明

版本：0.1.0a1，本地 Alpha 检查点。源码在本文件上两级的 AgentSync 项目目录。
本次实际开发 M0–M2；M3–M9 保存在 PLAN.md 和原始 SPECIFICATION.md。

## 当前功能

项目隔离、Agent 身份会话与心跳、任务依赖和优先级、原子认领、版本与租约、过期回收、
幂等请求、结果提交、另一 Agent 验收或拒收返工、审核身份/时间/证据/版本持久化。
11 个 MCP 工具、Python SDK 和鉴权本地 HTTP 共用 Core，无需付费模型、API Key 或 GUI。

## Windows 安装与运行

在解压后的 AgentSync 目录打开 PowerShell，已安装 Python 3.11+：

```powershell
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
& .\.venv\Scripts\python.exe -m pip install -e . --no-deps
& .\.venv\Scripts\python.exe -m agentsync --data-dir "$PWD\local-data\demo" demo
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check .
& .\.venv\Scripts\python.exe -m mypy
```

只运行功能时改用 requirements-lock.txt，不必安装开发工具。两份锁文件是 Windows
实测精确版本快照，不冒充跨平台通用解析锁。wheel 可用
`python -m pip install 路径\agentsync_local-0.1.0a1-py3-none-any.whl` 安装，建议同时用
requirements-lock.txt 固定传递依赖。完整文件清单在 FILE-TREE.md。

演示会实际检查 A 认领、B 重复认领被拒、A 提交结果、B 验收及数据库重新打开。

## MCP 配置

替换下列占位符为绝对路径。Codex TOML 和 Claude Desktop JSON 模板在
examples/mcp_clients，完整工具参数在 CONTRACT.md。

```json
{
  "mcpServers": {
    "agentsync": {
      "command": "<虚拟环境中 python.exe 的绝对路径>",
      "args": ["-m", "agentsync", "--data-dir", "<同一个绝对数据目录>", "mcp"]
    }
  }
}
```

两个客户端必须指向同一数据目录。项目管理员令牌、会话令牌私下保存。
不要把 SQLite WAL 数据库放在网络共享盘。

HTTP 启动示例：

```powershell
$env:AGENTSYNC_HTTP_TOKEN = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
& .\.venv\Scripts\python.exe -m agentsync --data-dir "$PWD\local-data\http" serve
```

默认 127.0.0.1:8765，向 `/v1/操作名` 提交 JSON 并附带 Bearer token。
该令牌是本地 HTTP 访问凭据，不是模型 API Key。

## 实测结果

- Windows / Python 3.14.6 源码环境：**64 项通过**。
- Windows / Python 3.12.14 全新 wheel 安装环境：**64 项通过**。
- Ruff、mypy、依赖一致性、打包检查通过。
- Codex 原生宿主：发现 11 个工具，实际完成 4 种工具调用；没有模型推理。
- Claude Code CLI：隔离配置下健康检查 Connected；没有模型提示词。
- 31 个运行时传递依赖的许可元数据和自带许可文本已整理。

详细命令、修复记录与边界在 TEST-REPORT.md 和 COMPATIBILITY.md。没有公开发布或付费调用。
本地 Git 保存恢复检查点。

## 剩余验收与下一步

**M2-05 的严格桌面会话验收仍部分未完成**：已验证真实原生宿主与 CLI，没有操作
已打开的桌面聊天窗口，也未演示两个桌面 AI Agent 的完整开发会话。
下一步先补齐这一门槛，再进入 M3-01–04 共享上下文、全文检索、来源版本和结构化交接。

Linux/macOS/Python 3.11 未实机测试，CI 未远程执行。验收证据当前是另一 Agent 的
署名文本；自动核验属于 M5。文件锁、Git Worktree、控制适配器、调度和费用统计在后续阶段。
继续时先读 PROGRESS.md、PLAN.md、CONTRACT.md 和 Git 状态，保留已验证功能。
