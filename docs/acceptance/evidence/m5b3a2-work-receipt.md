# M5B3A2 independent Work receipt

Reviewed product: 2ed3607de761f731ce8f80385af86260e126a4f4.
Reviewed evidence head: cb176f01e5851c74261fda427ab60c7a008f9a87.
The later receipt commit changes documentation only and is not a re-executed product.

Source: https://github.com/JayChan697891/agentsync/pull/21#issuecomment-6320283524
Issue11 record: https://github.com/JayChan697891/agentsync/issues/11#issuecomment-6320512727
Issue7 record: https://github.com/JayChan697891/agentsync/issues/7#issuecomment-6320513992

Captured published independent assessment (before historical details):

## Work 验收通过：仅 M5B3A2 既有 managed candidate 内容导出

旧“最终证据尚未到齐”阻塞已解除，原结论作为历史保留于下方。本结论基于实际代码审查及保存的本地证据独立复算，不是采信作者测试摘要。

- 实际受测产品：`2ed3607de761f731ce8f80385af86260e126a4f4` / tree `59af2cb1af025394c722d46fd3e25f3cdc503f98`。
- 写入前重读当前 head：`cb176f01e5851c74261fda427ab60c7a008f9a87` / tree `4cc373f8cf4c2296ff2271f704da9c7dc8475c35`。Git compare 确认其父提交为受测产品，仅 8 项 docs/证据变化，src/tests 未改；不宣称文档 tree 重新执行过测试。
- 基线：`66a619c255ddea965c2cfd89b0fcb315fcce0673`；PR 描述含“执行方：Codex”，关联 #11/#7，已读取两个 Issue 完整描述及全部评论。

### 独立复核结果

1. 从当前提交的 [归档](https://github.com/JayChan697891/agentsync/blob/cb176f01e5851c74261fda427ab60c7a008f9a87/docs/acceptance/evidence/M5B3A2-2ed3607-local.tar.gz) 读取原始字节，在内存中解包：665943 bytes，SHA256 `74b6c41c045d188078243f8fbd12769c7a189a8693f9b2ac03ee2e64983acfba`。自排除 manifest 的 **130/130** 文件大小/哈希及完整集合一致；26 项 collector artifacts/logs 和 18 checks 日志哈希全部一致，检查均 exit 0/pass，working-tree patch 为空、source_changed_during_execution=false。
2. 实际解析四份完整 JUnit，并与原始 pytest 日志核对：Linux source/fresh wheel/isolated sdist 每套 966 cases = **963 pass/3 skip/0 failure/error**；Windows **936 pass/30 skip/0 failure/error**。三套 Linux 各 41 项新增 export/storage/security 用例全部执行通过；Windows 40 项通过，FIFO 一项平台 skip。Windows 其余 skip 为 26 个 Linux Docker 例及 3 个链接权限例；Linux 仅 3 个 Windows 专用例 skip。开发阶段 RED/小套件没有计入冻结结果。
3. 逐一读取受测 Git 的全部 **31 个 Python 模块**，与实际 wheel、sdist 解包内容逐字节相等，并匹配 source snapshot 哈希。两平台 225 文件 source snapshot 相等，全部路径/大小匹配 Git tree；sdist 内对应的 189 个跟踪文件还逐一核对 Git blob ID 与 snapshot SHA256，其中包含全部 50 个 tests 文件。未把 sdist 排除的历史归档/发布物等宣称为本轮逐字节重验。
4. 核对 wheel/sdist 安装命令、隔离 venv、非 editable direct_url/包 SHA 检查、origin/SDK/pip 日志及独立运行目录。source 为冻结 checkout 的 editable 安装，保存的 source-install binding 指向该 checkout；三个来源未混称。
5. **6 条新真实 Git 对象输入**逐条复算 binding provenance、input provenance、manifest/input digest、预期源码 SHA256 和 solution.py Git blob ID，candidate SHA 与 baseline 不同；双父/合法单父各 3 条，均 execution_verified=false、filesystem_atomicity_verified=false。**6 条旧 DB metadata**另行复算 provenance，仍 filesystem/execution 未验证。
6. **78 条旧 Docker 回归**单独核对：42 backend、21 owner、15 reconciliation；verifier 模块身份、owner result digest 与 input/profile/commit/tree/container 绑定，以及 78 个唯一 full-ID 与保存的 cleanup-inspection 集合一致。每套 26 actual 用例均在三份 Linux JUnit 内实际执行。cleanup 的每环境 2 removed、2 unresolved、1 无回执保持区分；原 unverified execution 没有因 cleanup 提升为 passed。此为保存的本地运行/inspect证据复核，**本轮没有访问原 Docker daemon 或重新执行 inspect/测试**。

### 实现与安全边界

实际读取 candidate.py、binding.py、snapshot.py、git.py 相关实现及新增实际 Git/安全测试：owner 鉴权与项目关系捕获在 storage/Git 前；create=False 不重建缺失存储；有限严格 JSON/receipt/intent 比对；bare .git 重定向和非普通 config 在首次 repository Git 前拒绝；linked .git/admin/commondir/backpointer、物理身份、HEAD/clean 状态、共同仓库和精确 parents 均受检查。对象通过固定 SHA 的有界 exporter 校验，导出后重复磁盘/Git检查并再次鉴权/捕获 DB binding，竞态丢弃结果。实际 FIFO/foreign Git pointer/bare redirect/wrong parents/missing receipt 回归均有冻结 JUnit 支持。未发现限定范围内的阻断缺陷。

只接受 owner 读取并校验既有 managed candidate 的固定 Git 对象内容。返回 dataclass 与无密钥指纹不授予权限；OS 级 filesystem ABA 原子性不在保证内。未接 candidate jobs/执行/task gate/reviewer、审批消费/safe apply、真实客户端/自主 relay。42 个正式完整场景仍未整体执行，正式 **Release BLOCKED**。**Issue #11/#7 保持 open**。

本环境不能访问用户 F:/D:，本轮使用仓库同路径及内存处理，没有在其他磁盘解包或执行项目测试。未调用/请求/检查 GitHub Actions，未付费、修改代码、合并或开启自动合并。

<!-- work-acceptance pr=21 product=2ed3607de761f731ce8f80385af86260e126a4f4 head=cb176f01e5851c74261fda427ab60c7a008f9a87 limited-pass -->



