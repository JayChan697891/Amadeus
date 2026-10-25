# M5 范围冻结与 M6 有条件启动

执行方：Codex。核查日期：2026-10-25，America/Tijuana。
本文件是 M5 唯一最终清单，不是新的 M5 子阶段或通过证书。原始需求仅
SPECIFICATION.md 的 M5-01 至 M5-05。文档整理、重复证据、非关键增强不增加阶段。
只允许为真实安全阻断缺陷增加必要修复；说明失败行为、复现与受影响门禁。

## 实际核查基线

- 当前分支 feature/m5b3b2b-execution-intent；HEAD
  aac28a0f688962eca640b930e92eeaa608ff824f，tree
  ea2937f959c224bf940852f73ca030a96112f98b，0.3.0a11/schema12。
  存在未提交代码；本轮完整回归用逐文件哈希冻结，不等于已有冻结提交验收。
- 读取原始总计划、PLAN/PROGRESS、合同、当前代码、现有报告和证据。
  outputs/AgentSync 中原始计划与当前计划文本相同，仅换行字节不同。
- 实时只读检查开放 PR：3、5、8、10、12、14、16–26，共 17 个；
  Issue #7、#11 均 open，已读取全部 13/11 条评论。
  PR25 draft/head aac28a0：Work 评论6369038699阻塞最终冻结包证据，
  未认定明确代码缺陷；PR26/head023cdef6a814d0f7aa4312619c6dc1fccfa745cb
  仅文档范围通过，不能解除 PR25/M5 门禁。没有修改远端或触发 Actions。
  补充详情抓取：PR3/5/17/18/21/24/25/26实际详情可读；PR8/10/12/14/16/19/20/22/23
  的完整详情因连接传输失败而 LIMITED，未重试；其列表描述与本地历史证据已读，
  不能声称上述9个PR的当前完整diff/评论均已取得。失败原文保存在
  D:/agentsync-debug/m5-freeze-open-pr-details.json；不影响本地协议原型继续。
- 9 个历史归档、1060 regular 成员、7份逐文件清单899条、396 artifact/log
  绑定、150 模块与各自历史 Git 提交字节均已复核；47份历史 JUnit 已统计。
  前2归档未提供全文件 manifest，记 NOT PROVIDED，不能声称全部清单齐备。
  历史结论只适用于各自 SHA，不能提升当前未提交源码的验收状态。

## 五项实际状态

VERIFIED 仅指明确绑定冻结提交且具有充分证据的限定功能。
BLOCKER 表示相关危险功能启用前必须解除；DEFERRED 表示关闭该功能时可后置。
同一缺口可以阻止特定功能、同时不阻止隔离原型开发；不得把后置写成通过。

| 原定任务 | 已有实际能力与证据 | 剩余状态 |
|---|---|---|
| M5-01 权限控制 | VERIFIED：历史 M5A/7479dfa0c8243f1650f0ac395afbead4bc49d7e5 的限定权限验收；当前 Core 默认 viewer、角色矩阵、owner 独立渠道、鉴权先于重放有本地回归 | BLOCKER B1：真实运行器授权/资源边界尚未验证；整个正式需求未 VERIFIED |
| M5-02 风险审批 | VERIFIED：同一历史 M5A 限定审批元数据；绑定请求者/candidate/SHA、过期、撤销、并发；批准本身不执行 | BLOCKER B2：危险执行/应用的最终校验与单次消费未接通；不启用 apply 时 DEFERRED D1，不能记已实现 |
| M5-03 审计日志 | VERIFIED：历史 M5A 限定事务审计与脱敏；当前白名单、拒绝事件和审计失败回滚有回归 | BLOCKER B3：真实适配器输出/凭据处理及生命周期审计未验证；数据库管理员防篡改不在本范围 |
| M5-04 独立验证 | VERIFIED：历史 M5B1–B2C 等各自冻结提交的固定 snapshot/profile 容器验证器限定证据；不是当前 candidate 执行或任务验收 | BLOCKER B4：review_task 仍可基于其他 Agent 的非空文本完成任务；缺独立结果与不可变 candidate 的强制绑定；BLOCKER B5：candidate 真执行生命周期尚未接通 |
| M5-05 安全回归 | 当前完整 Windows 回归1303通过/30跳过/零失败，只有组件证明；历史隔离回归分 SHA 保存 | BLOCKER B6：冻结提交最终安全清单、适用隔离/安装测试及独立审查未完成；五项正式完整场景仍 NOT RUN |

当前 completed 表示既有协作状态，不能标称独立 verified。模型文本、Mock 成功、
协议回放、approved、prepared intent、旧 Docker 成功均不能替代独立验证。

## 全部剩余 BLOCKER（固定清单）

- B1，启用真实客户端前：确定官方接口/版本、明确授权及可能费用、专用临时
  项目和运行身份、最小权限/资源/网络边界；未满足时不启动，不借用宿主凭据。
- B2，启用高风险应用前：事务内重新验证审批、身份、版本、SHA、过期、撤销，
  单次消费与实际效果一致；重复/竞争/异常退出不重复应用。不接通则持续拒绝。
- B3，接入真实输出前：结构化审计生命周期、静态错误、敏感字段脱敏和限量，
  输出文本不获工具权限，原始 stdout/stderr 不直接成为安全公开日志。
- B4，宣告自动独立验收前：任务、candidate SHA、测试产物、profile、独立 reviewer
  与实际验证结果绑定；伪造/陈旧/不匹配/未知/失败证据不得提升为 verified。
- B5，连接 candidate 实际执行前：外部 create 前持久 fence，未知/丢失 ACK
  保持 unresolved；禁止旧 ledger recovery 解除可能运行中的执行；超时、取消、
  重启和 exact-identity 清理有闭环。现有 prepared/abandon 不提供此权限。
- B6，M5 最终验收前：冻结产品 SHA/tree，独立核验对应源码、安装包、JUnit、
  日志、迁移/故障/并发/关键安全用例及逐文件 manifest；未执行/跳过逐项解释。
  当前 dirty-tree 回归不能冒充 PR25 原 SHA 的最终包验收或 Work 接受。

未发现额外可复现阻断缺陷时，不再扩大此清单。上述缺失功能/证据不是新发现漏洞。

## DEFERRED（不阻止无执行原型，不代表完成）

- D1：safe apply 与审批消费的实现，安排在实际应用功能启用前，依赖 B2。
- D2：自动任务验收与 candidate 执行接线，在启用前分别解除 B4/B5；当前保持
  asserted/unverified，不用关闭能力来宣称完整 M5 已通过。
- D3：跨进程管理、自动恢复/重试、智能调度、预算、真实双 Agent 接力：属于
  M6–M8/M9；不得为此再新建 M5 子阶段。失败/未知不得自动替换为成功。
- D4：完整 OS/Python 支持矩阵、账单对账和非关键增强：对应后续版本/M9门槛，
  不能把当前未验证平台或费用写成支持/零费用。
- D5：历史材料重排、重复报告/证明、全归档格式统一：不推进产品功能，不作为
  无执行原型的先决条件；最终证据只按 B6 补必要缺口。

## 唯一最终退出条件

以下六条全部有冻结 SHA 对应证据并由独立验收确认，才能将 M5 整体标通过：

1. M5-01：全部已开放操作的身份/项目/角色矩阵、默认拒绝、撤权后重放通过；
   真实运行操作若尚未开放必须明确不可用，不能冒充该能力验收。
2. M5-02：危险操作默认拒绝；每个实际开放危险操作的审批绑定、终检、单次
   消费、竞争/撤销/过期/故障测试通过。未实现的 apply 仍明确 DEFERRED。
3. M5-03：实际开放入口全部结构化审计/脱敏，成功与业务同事务；失败不会
   越权或泄密；真实客户端未接通部分仍未验证。
4. M5-04：独立验证与不可变任务/产物身份绑定且强制门禁生效；只有断言的
   review 不能成为 verified completion。不可用隔离环境必须 fail closed。
5. M5-05：关键权限/跨项目/路径/恶意文本/迁移/并发/故障回归全部执行通过；
   适用的隔离测试无静默跳过。保留 RED/失败/NOT RUN，不删除测试或降低规则。
6. B1–B6 对拟开放功能均解除，B6 证据身份完整、独立复核通过；所有 DEFERRED
   能力继续禁用并有明确后续归属。任何关键失败/未知均不得通过；不要求合并 main。

关闭未实现的危险路径允许安全继续开发，但不能代替第4条或证明整体验收。
正式 Release 另需 Issue7 的完整42需求、真实客户端/自主接力及 M9；M5 通过不自动发布。

## M6 最小原型与分界

按官方公开接口依次 Codex、Claude Code、Cursor；每个声明独立能力。
现有统一生命周期、MockAdapter、MockRunManager及只读分配器可复用模拟测试，
其 SimulationMarkers 不能用于真实执行，也不证明实际客户端支持。

1. 现在可做：纯 JSONL 协议解析/有界结果与用量投影，固定手写 fixture 回放；
   不执行工具内容、不读取凭据、不更新 Core，不报告真实运行通过。
2. 可隔离开发：运行器的启动/监控/结果/超时/取消/异常退出接口与记录，
   先在专用本地项目使用受控测试进程验证；这只证明进程层，不是 Agent 成功。
3. 条件真实原型：B1/B3满足后，明确授权的官方客户端在专用临时 Git 项目运行，
   保存版本、run/session/project/task ID、exit、输出摘要、超时/取消及限制。
   当前禁止付费调用仍有效，不能默认使用已登录客户端额度。
4. 必须等待：candidate 执行(B5)、自动 verified completion(B4)、危险 apply(B2)、
   不受控自动调度/真实接力与发布。禁止宿主 fallback、任意 Shell 和权限伪装。

官方协议依据：https://learn.chatgpt.com/docs/non-interactive-mode 。
真实客户端运行前复核版本/接口。首次范围核查没有启动客户端；随后用户单独授权
一次 Codex 订阅只读测试，实际结果见下文。Claude/Cursor仍未启动。

## 实际结果与保存位置

- D:/agentsync-debug/CURRENT-LOCAL-FULL-CHECKPOINT-20261024.json：281文件冻结
  快照、40模块与已安装 wheel 字节复核；完整 Windows1303pass/30skip/0fail/error；
  Ruff、format、mypy、diff通过。30skip含26实际Docker/owner/reconciliation场景，
  其余FIFO/链接能力限制；未把这些计为通过。
- D:/agentsync-debug/local-planning-67kz4m55/result.json：此前源码组件735pass/1skip，
  fresh wheel/sdist组件各361pass；不是本轮全 Linux 回归或正式 M5验收。
- D:/agentsync-debug/m6-linux-ehpkhrqu：实际Linux Mock manager组件37pass，
  不是真实客户端，其他Python版本/完整平台矩阵 NOT RUN。
- D:/agentsync-debug/m5-freeze-audit-hbd3vbe9/audit.json：历史归档、日志、Git模块、
  JUnit及当前快照只读复核索引；不是重新执行历史测试。
- D:/agentsync-debug/m5-freeze-github-snapshot.json：本轮实时只读 PR/Issue 原文。
  原始记录保留评论时间；未将抓取时间伪装成测试时间。
- 真实客户端、费用、真实自主接力、candidate 执行/完成门禁/安全apply：
  NOT RUN/UNVERIFIED（功能、授权或安全门禁不足）；完整 M5/Release仍 BLOCKED。

本轮范围核查与清单整理不计产品功能进度；M6后续代码和真实测试另列。

## M6 离线组件与单次真实 CLI 补充（不改变 M5 退出条件）

已新增 bounded Codex JSONL 单次 turn 解析器及仓库离线检查工具；后者只输出
消息大小/哈希，拒绝非法输入，不暴露原文/工具命令/线程标识。
M6-03仅增加部分协议组件覆盖，正式 not_run/真实 unverified及发布门禁均保留。

本地冻结快照286文件、41运行模块：源码组件787pass/1skip，fresh wheel/sdist
组件各413pass；现有D盘本地Linux协议+追踪263pass。包/安装后模块/源码字节
与日志/JUnit哈希由根负责人独立复核。证据
D:/agentsync-debug/CODEX-PROTOCOL-CHECKPOINT-20261025.json。
此前1303pass/30skip是新增协议代码前的完整Windows回归，未冒称新快照完整回归。
这轮源码全单元和相关集成、安装组件已执行；完整新平台矩阵仍未执行。

用户随后授权一次只读订阅额度任务、不额外付费。CLI0.164.0-alpha.11.1，
强制ChatGPT登录、内置openai provider、read-only/ephemeral/json，忽略user config，
禁shell/MCP/apps/web/hooks/multiagent；合成fixture文本内联提供，不让模型访问文件。
实际一次模型任务退出0、4条事件、唯一reply哈希匹配；19文件前后清单/哈希不变。
初次进程在模型请求前因reserved built-in provider config拒绝（零stdout），保留失败
并删除不兼容的两个retry覆盖；没有重试已进入模型的任务。无API key/购买额度/
账号配置修改；usage原样保存，但账单未独立核验，不能把usage推成已验证费用。

原始已脱敏合成fixture capture与根负责人/独立peer核验摘要：
acceptance/evidence/codex-readonly-cli-smoke-20261025.json及.jsonl。
只接受“真实CLI无工具响应收集smoke”，不接受AgentSync适配器集成、文件读取、
取消、超时、独立验证、Claude/Cursor或真实接力。一次授权已消费，不追加真实调用。
前述真实客户端NOT RUN指完整适配器/正式场景，本smoke不将它们标绿。

后续仅本地的进程观测层已实现并经Windows/Linux复验：24个已知Python helper
测试，不是客户端测试。最新组件快照290文件/42模块，源码811pass/1skip，
fresh wheel/sdist各437pass，Linux进程/协议/追踪287pass。完整记录
D:/agentsync-debug/M6-LOCAL-PROTOTYPE-CHECKPOINT-20261025.json。
该层只管理父进程、继承宿主环境；子进程树清理始终unverified，不是沙箱。
父退出但管道未关闭时有界返回capture_incomplete，不能升级成完整清理成功。
启动握手尚未获得transport时无严格结束界限；此时调用者取消尚未直接测试，
未来真实接线前必须处理/披露这些M6限制，不能宣称完整启动超时已验证。
此工作未连接真实CLI、未改变M5范围/退出条件或Core/schema/版本。
