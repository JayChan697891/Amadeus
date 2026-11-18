# a122 自然超时：一次固定文本验证

这是原 RAT-M6-03 剩余接口证据；取消已经独立复核，不重跑取消、不新增阶段。
Root/Astra 已检查实际计划、回执、运行文件和授权绑定，真实 timeout **NOT RUN**。

[实际计划](plan-timeout.json) · [控制器绑定](control-timeout.json) · [本次持续授权绑定](owner-grant-timeout.json) · [准备审查](review.json)。

- 冻结 a122/5232e9e、Codex 0.167.0-alpha.3.2、固定确认文本、只读且工具关闭。
- D盘本地 Linux 新目录 `/root/amadeus-lifecycle-a122-timeout`；独立适配器命名空间，不创建或完成 Core 任务。
- 最多1次现有订阅调用，无额外付费/付费API，0候选执行。费用依据是所有者已确认的零付费credits/关闭自动充值；不是独立账单审计。
- 仅临时复制 `C:\Users\JayChan\.codex\auth.json` 到本目录的私有内存 `private-home/auth.json`。实际同环境CLI须识别ChatGPT登录；确认父进程终态且无相关进程后清理副本并卸载，原件不变。
- 保持15秒自然适配器期限，不调用显式取消、不修改时钟或外围协程。期限前1秒内需观察到完整 turn.started、父进程仍活、无终态/工具事件/截断。
- 仅实际 `unknown/adapter_timeout/timed_out=true`、父进程退出及其他绑定完整时接受本地超时处理。与启动超时及捕获器自身超时区分。
- 提前完成、无合格窗口、失败或未知均如实记录，不重试，不延长提示或改变预算。原始模型输出最多1MiB，仅留本地，不上传。
- 不宣称服务端内部生成/取消、进程树清理、Core完成或正式 Release。Release仍 BLOCKED。

唯一运行入口（须先上传本计划并保持所有哈希及授权有效）：

```powershell
D:/agentsync-debug/venv/Scripts/python.exe -I -B D:/agentsync-debug/m122-lifecycle-host/run_once.py timeout
```

独立采集采用 `collect_timeout.py`，无论成功或错过窗口均保存原始状态，不会再启动模型。
