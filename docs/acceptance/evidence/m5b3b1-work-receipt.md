# M5B3B1 independent Work acceptance receipt

Reviewed product f65e134d672d4c4333701b982759cc86567a97a6.
Reviewed evidence head a2f7efad51a1f95c39ce5d6a2641094fc4763ff9.
Later documentation descendants are not re-executed product commits.

Source: https://github.com/JayChan697891/agentsync/pull/23#issuecomment-6356443059
Issue11: https://github.com/JayChan697891/agentsync/issues/11#issuecomment-6360133299
Issue7: https://github.com/JayChan697891/agentsync/issues/7#issuecomment-6360134616

## Work 验收通过：仅 M5B3B1 owner candidate queue 四操作

旧最终证据不足阻塞已解除，历史保留于下方。

- 受测产品：`f65e134d672d4c4333701b982759cc86567a97a6` / tree `64c402b142ab10246e2dfa76e31cf0167c71acba`。
- 写入前重读 head：`a2f7efad51a1f95c39ce5d6a2641094fc4763ff9` / tree `fc93308dc7cbbf086f0fabef0802e7b1e11fefb9`。Git compare 已核对相对受测产品仅8项docs/证据增量，产品源码/tests未改；文档head不宣称重新执行产品测试。
- 关联 Issue #11/#7 的完整描述及全部评论已读取；均有未完成范围，保持 open。

### 独立核验证据

1. 从仓库取得[归档原始字节](https://github.com/JayChan697891/agentsync/blob/a2f7efad51a1f95c39ce5d6a2641094fc4763ff9/docs/acceptance/evidence/M5B3B1-f65e134-local.tar.gz)，实际解包复算：740239 bytes，SHA256 `6c9a3ee933bda5b2cdbdc58769db0a09d9b1156f947e42a179d6ee1fc915a3c2`；143/143 manifest文件大小/哈希及完整集合相符。18 checks 均pass/exit0，逐项原始日志哈希相符，26项collector artifacts/logs哈希相符。报告绑定产品commit/tree，working tree clean、source_changed_during_execution=false。
2. 实际解析四份完整JUnit：Linux source/fresh wheel/isolated sdist各1023 cases=1020pass/3skip；Windows993pass/30skip；全部0 failure/error。每套50个新增case均存在、执行且无skip：40实际Git/SQLite、6corruption/合成stored-policy、4实际SQLite迁移。迁移复用的Docker transport fixture只证明数据库行为。原漏洞复现、fixed开发审计和冻结完整回归分别保留，漏洞成功复现不计安全通过。
3. 从产品Git逐一读取全部32 Python模块，与wheel/sdist模块集合及SHA256全部一致；三份新queue/security/migration测试与sdist内文件逐字节相同。Linux/Windows的244文件源码快照完全相同。读取source安装绑定（editable frozen checkout）及fresh wheel/isolated sdist安装、origin/SDK/pip日志；两分发安装来源位于各自隔离venv，sdist日志保存PEP517 build isolation过程。wheel SHA256 `270a84e4c352590a28870622cb4bf791701b39978483bd4eb8bd69c64ec5ce29`；sdist SHA256 `f9b03090bc6e668fcf6b6470424c7d6d399bce9799845139fb5f6ee8cdb1ece8`。
4. 六条新queue原始记录逐条复算canonical metadata、binding receipts指纹、input/provenance、profile kind/SHA/image列绑定、literal source SHA及Git blob ID、请求payload指纹及historical response digest。每环境一条queued/1request，一条cancelled/2requests；历史enqueue仍queued而当前投影cancelled，均execution_connected=false/assessment=unverified，execution_verified和real_clients_verified=false。
5. 六旧metadata provenance及六旧object-input provenance/input/literal source blob分别复算；78旧Docker回归（42backend+21owner+15reconciliation）核对source/result/observation绑定、原unverified边界及78唯一完整ID与保存cleanup-inspection集合完全一致、all absent。该项为保存的运行/inspect证据复核；本轮未访问原Docker daemon或重跑inspect，不赋予queue执行能力。

### 实现与有限结论

结合前轮实际代码/差异审查及本轮冻结证据，owner认证在对象/重放前；export在写事务外，最终同连接完整binding复核与queue/request/成功audit原子提交；profile envelope/独立列一致性、strict JSON、历史receipt与当前态分离、版本取消、并发重放、崩溃回滚及schema10保留旧历史均有对应测试证据。当前未发现限定阶段阻断缺陷。

仅接受enqueue/get/list/cancel独立owner队列。旧snapshot executor不能消费candidate queue；没有candidate worker/attempt/lease/execution/taskgate、approval consume/apply、真实适配器/自主接力。trusted service/database/filesystem边界及OS级ABA限制仍适用。42完整正式场景仍not_run；**Issue11/7保持open，正式Release BLOCKED**。

本轮为实际代码与保存证据独立复核，未重新运行项目测试。未调用/请求/检查Actions，未付费、修改源码、合并或开启自动合并。

<!-- work-acceptance pr=23 product=f65e134d672d4c4333701b982759cc86567a97a6 head=a2f7efad51a1f95c39ce5d6a2641094fc4763ff9 limited-pass -->



