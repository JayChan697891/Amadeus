# M5B3B0 independent Work receipt

Reviewed product37b17a3d0c27b0a34ca93e03c4944f02a7a63071.
Reviewed evidencehead37720ee79fbace999130331a1a5d8d5e65b6665a.
Later receipt-only descendants are not re-executed product commits.

Source: https://github.com/JayChan697891/agentsync/pull/22#issuecomment-6329149589
Issue11: https://github.com/JayChan697891/agentsync/issues/11#issuecomment-6356135968
Issue7: https://github.com/JayChan697891/agentsync/issues/7#issuecomment-6356136874

## Work 验收通过：仅 M5B3B0 私有同连接事务内元数据捕获

旧“最终证据尚未到齐”阻塞已解除，历史记录保留于下方。

- 受测产品：`37b17a3d0c27b0a34ca93e03c4944f02a7a63071` / tree `4036fc4a1b19abb57fd6559f34e14e731412c170`。
- 写入前重读当前 head：`37720ee79fbace999130331a1a5d8d5e65b6665a` / tree `ba8df9a8569fba0cdbea29f5875ac5b4e4f1cb20`。Git compare 已确认仅 8 项 docs/证据增量，源码/tests 未改；文档 head 不宣称重新运行过产品测试。
- 基线：`dbb5e6ab717e1927c8f444b3cc5e8fe4e832e244`。已读取关联 Issue #11/#7 描述与评论；均含未完成范围，保持 open。

### 独立复核证据

1. 从仓库读取[归档](https://github.com/JayChan697891/agentsync/blob/37720ee79fbace999130331a1a5d8d5e65b6665a/docs/acceptance/evidence/M5B3B0-37b17a3-local.tar.gz)原始字节并解包：687872 bytes；SHA256 `b08af5ea334dd26b32070dec338b301cb4ed0857911e548d894dee527f6686f0`。135/135 自排除 manifest 文件大小/哈希及集合一致。18 checks 均 pass/exit0，各 check 原始日志哈希一致；报告绑定受测 commit/tree，working tree clean、patch为空、source_changed_during_execution=false。
2. 实际解析四份完整 JUnit：Linux source/fresh wheel/isolated sdist 各 973 cases = 970 pass/3 skip/0 failure/error；Windows 943 pass/30 skip/0 failure/error。每套七项新增实际 SQLite/Git 事务测试均存在且通过。开发 RED/GREEN 与独立开发 audit 未计入冻结完整套件。
3. 逐一从受测 Git 读取全部 31 个 Python 模块，与 wheel/sdist 内模块 SHA256 全部一致；包内两套模块集合均为31。Windows/Linux 的233文件源码快照完整相等。核对 source editable frozen-checkout binding、wheel/sdist fresh venv 安装命令、-I、非editable direct_url 包哈希检查及 origin/SDK/pip日志。未把 source editable 称为独立 wheel 安装。
4. 阅读真实 sqlite.Error 补充驱动：在外层事务内修改 task version 并重命名表以触发真实SQL错误，验证 storage_error 脱敏、外层事务/未提交写入/连接保留，并由调用方 rollback 恢复。冻结 provenance 绑定当前 binding 模块 SHA256 `216fd02d9eeeaf7334392fdc5895d3da1479bc2c10aa67d8451da8952f9c6961`、driver SHA256 与独立 JUnit SHA256；实际重算 driver/JUnit 哈希相符，补充 JUnit 1 pass。此结果独立于973-case完整套件。
5. 六条旧 DB metadata 与六条旧 candidate input 分别复算 provenance/binding 指纹，保留 execution_verified=false。旧 Docker 回归42 backend +21 owner +15 reconciliation 共78条，检查 owner result digest、reconciliation observation绑定和原unverified/cleanup_confirmed=false边界；78唯一完整ID与保存的 cleanup-inspection 集合一致。该项是保存的本地运行/inspect证据复核，本轮未访问原daemon或重新执行inspect；不宣称新增queue/执行能力。

### 实现与结论范围

已审查实际 binding.py、完整代码差异、事务合同及新增测试：helper 在活动调用方 connection 上验证输入、owner和完整项目关系/receipt；认证先于candidate查询；helper不BEGIN/COMMIT/ROLLBACK/close；SQL错误安全转换且不接管外层事务。public capture仍管理自己的连接及读事务。未发现该限定范围的阻断缺陷。

仅接受 private 同连接 capture 前置能力。connection 是受信任服务内部能力，不认证任意数据库来源；dataclass/无密钥指纹不授予权限。没有 queue/schema/attempt/lease/execution/task gate/apply；整个 M5、审批消费/safe apply、真实适配器/自主接力、完整平台矩阵和 M9 仍未完成。**Issue #11/#7 保持 open，正式 Release BLOCKED。**

本轮使用仓库字节及临时审查目录复核保存证据，未执行项目测试。未调用/请求/检查Actions，未付费、修改源码、合并或开启自动合并。

<!-- work-acceptance pr=22 product=37b17a3d0c27b0a34ca93e03c4944f02a7a63071 head=37720ee79fbace999130331a1a5d8d5e65b6665a limited-pass -->



