# M5B3B2A independent Work acceptance receipt

Actual published PR24 comment6365449101:
https://github.com/JayChan697891/agentsync/pull/24#issuecomment-6365449101
Issues11/7 notes6365454598 /6365456556 remain open.
Reviewed product0fd2041c8efd1c4fa348117e013c0c5b1f30e470 and evidence
head74abf2442c41e056e82de4674868424c19dd7816. Receipt-only descendants
are not re-executed product commits. Original evidence archive stays immutable.
Formal Release BLOCKED; next work must first design execution-aware recovery
authority and dedicated cleanup before connecting candidate execution.

## Published independent assessment

## Work 验收通过：仅 M5B3B2A owner 单次 reservation / 显式 ledger interruption

- 受测产品：`0fd2041c8efd1c4fa348117e013c0c5b1f30e470` / tree `9a76e8c5280c34d38087f42fc35b702808d15c59`。
- 写入前重新核对当前 head：`74abf2442c41e056e82de4674868424c19dd7816` / tree `86de61f4088afe32eb4b4825688b8d8ed43dbe84`。实际 Git compare 显示相对受测产品仅8项 docs/证据增量，源码/tests未变；文档 head 不宣称重新执行测试。
- 关联 Issue #11/#7 的描述和既有阶段评论已读取；整个 M5/M9 仍有未完成范围，保持 open。

### 独立核验依据

已从仓库取得归档原始字节并实际解包：[M5B3B2A-0fd2041-local.tar.gz](https://github.com/JayChan697891/agentsync/blob/74abf2442c41e056e82de4674868424c19dd7816/docs/acceptance/evidence/M5B3B2A-0fd2041-local.tar.gz)。外层792898 bytes，SHA256 `7e9022f64c43124b0b6cd7667ed4271feeaa5c6d2db821f3c64fd57083e3671f` 相符。自排除manifest完整集合154/154文件大小/哈希相符；18 checks均pass/exit0，逐项日志SHA及26项collector artifacts相符；report绑定产品commit/tree、clean、source_changed_during_execution=false。

四份JUnit实际解析：Linux source/wheel/sdist各1061case=1058pass/3skip，Windows1031pass/30skip，均零failure/error。新增claim/migration用例执行且无skip；开发RED/GREEN与额外2case审计不计入完整套件数。33全部Python模块逐个从产品Git读取，与wheel/sdist字节及索引SHA一致；Linux/Windows 253文件源码快照相同。source记录为editable frozen checkout，不能描述为fresh noneditable source安装。

六份新raw claim/recovery记录已核对canonical metadata hash、claim proof原始JSON/digest、profile/content/metadata pins、created/deadline及claimed2/interrupted3状态；recovery response原始JSON/digest与execution_connected=false/unverified边界相符。worker_credential_issued、cleanup_performed、execution_verified、real_clients_verified均为false。旧6queue/6metadata/6input分别保存；78旧Docker full-ID集合与保存cleanup-inspection的78唯一ID完全一致，all absent。本轮依据保存证据，不声称重新访问原daemon或执行Docker inspect。

### 实现与范围

实际审查契约、candidate_claims.py、candidate_jobs.py、permissions.py、schema11与新增测试：owner认证先于对象/Git/重放；fresh export在写事务外，最终在同连接BEGIN IMMEDIATE内重新鉴权、复核version/state/profile/完整binding和metadata，claim/job/audit原子提交。唯一claim约束与版本更新限制一次reservation；claimed不能通过旧queue cancel清除。读取对job/claim/proof/recovery双向校验，历史enqueue仍保持原queued1回执，当前态独立呈现。有限时钟/deadline检查、clock rollback标记和显式恢复的时间锚点处理符合本阶段契约。

schema11仅重建candidate jobs/requests并新增claim/recovery表；显式列复制、复合FK和最终foreign_key_check保留v10历史。实际迁移测试使用历史DDL加一次性真实记录，覆盖queued/cancelled历史、重开、失败回滚、future schema拒绝；不把它描述为旧二进制兼容运行证明。新增成功审计与业务同事务，audit allowlist不等于新增transport操作。

当前未发现此限定阶段阻断缺陷。仅接受`owner_reservation_v1`一次性账本前置：claim_once/get/recover_interrupted；没有worker token/renew/callback/真实候选执行/taskgate/审批消费/apply。**未来接入真实执行前，必须加入execution-aware recovery guard及独立cleanup，不能凭当前ledger interruption清除可能运行进程的执行权限。** unkeyed proof是完整性检查，trusted service Python/DB/FS及OS级ABA限制仍适用。

完整42正式场景未完成，真实适配器/自主接力及后续M5/M9未完成；**Issues #11/#7保持open，正式Release BLOCKED。** 本轮未重跑产品测试，未调用/请求/检查Actions、付费、修改源码或合并。

<!-- work-stage-pr24-74abf product=0fd2041c8efd1c4fa348117e013c0c5b1f30e470 head=74abf2442c41e056e82de4674868424c19dd7816 limited-pass -->
