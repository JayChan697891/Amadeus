# a122 真实取消接口：一次固定文本验证

这是原 RAT-M6-03 的接口补证，不增加 M5 阶段，也不重复已通过的启动、产物验证或完整测试。

已完成准备和独立审查，**真实运行 NOT RUN**。6项本地 Python 确定性检查不是真实 Codex 验收。
[实际计划](plan-cancel.json) · [控制器绑定](control-cancel.json) · [持续授权的本次绑定](owner-grant-cancel.json) · [审查与哈希](review.json)。

- 冻结 a122/5232e9e，真实 Codex 0.167.0-alpha.3.2，固定确认文本、只读、所有工具关闭。
- 仅本次 cancel 模式，最多1次已有订阅调用、无额外付费/付费API、0候选执行。
- D盘本地 Linux 的 `/root/amadeus-lifecycle-a122-cancel` 是独立临时Git目录；标识仅属于适配器命名空间，未创建Core任务，不宣称Core完成。
- 沿用所有者“后面每次都允许，无需询问”的同类持续授权。账号费用依据仍为所有者已确认的零付费credits/关闭自动充值；实际同环境CLI必须识别为ChatGPT登录，否则不调用模型。
- 只把原 `C:\Users\JayChan\.codex\auth.json` 临时复制到该项目的 `private-home/auth.json` 私有内存挂载。确认真实终态、同capture父进程退出及无相关活进程后删除副本并卸载，原件不改。
- 观察到完整 `turn.started`、父进程存活且无终态后，直接调用一次 `adapter.cancel_task(run_id)`。保持90秒总预算、60秒观察窗口；不取消外围协程，不改变时钟。
- 取消后允许真实状态保留 `unknown/local_cancel_requested`，仅在父进程退出等限定证据满足时接受接口行为；不能改写成模型任务成功。窗口错过、失败或未知不重试。
- 原始模型输出仅留受限本地目录，至多1MiB；公开材料仅含允许的状态、回执和哈希，不上传登录、原始输出或数据库。
- timeout模式尚未准备，不会自动续跑；取消结果和清理独立复核后再决定。服务端取消、整个进程树、Core完成及正式Release均不因此通过。

一次运行入口（须保持实际 control/grant/helper 哈希及有效期）：

```powershell
D:/agentsync-debug/venv/Scripts/python.exe -I -B D:/agentsync-debug/m122-lifecycle-host/run_once.py cancel
```

失败时保留现场和实际状态；不得再运行该入口。正式 Release 仍为 BLOCKED。
