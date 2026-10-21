# Next stage: managed merge-candidate input bridge

Status: design only, **not implemented or accepted as a product capability**.
Checked against actual workspace/snapshot/executor code and native peer review.

Current jobs pin repository_snapshots.base_sha. Passing that baseline cannot
attest managed changes or a merge candidate; review_task remains asserted. Add
an explicit applicable input boundary before designing verified task acceptance.

Proposed internal owner seam: OwnerCandidateExporter(core).export(project_id,
admin_token, candidate_id, expected_candidate_sha), returning frozen content and
provenance. No schema change, transport, Docker, old job/executor wiring, task
completion, approval or apply. Caller cannot supply paths, receipts or results.

Return source_kind=managed_merge_candidate, project/candidate/snapshot IDs,
candidate/base/left/right full SHAs, left/right worktree/task IDs and captured
task versions, the actual CandidateSnapshot, and a separate provenance digest
binding canonical receipts and all identities. Preserve input_sha256 semantics.

1. Short owner-authenticated read transaction resolves project-owned candidate,
   both worktrees, common snapshot and tasks. Compare column/receipt identities,
   snapshot/base/task relations and captured task versions before any Git.
2. Outside transactions compare DB receipts with existing service-owned
   capture/create/candidate receipts and merge intent. Missing evidence fails.
3. Validate physical storage/config, exact HEAD and clean state for both
   worktrees and candidate. Resolve candidate git-common-dir to the shared
   managed bare repository; path/inode/HEAD checks alone are insufficient.
4. Use bounded export_candidate with the trusted capture receipt and actual
   pinned candidate SHA. Keep object-integrity, regular-file, UTF-8 and bounded
   root solution.py limits. Do not replace candidate SHA with baseline SHA.
5. Validate parents: left/right, or left only when right is already its ancestor,
   matching the existing generator's legitimate degenerate case.
6. Repeat Git/receipt checks, then reauthenticate and compare DB rows/task
   versions in a final read transaction; discard stale output.

Never use prepare_merge_candidate as validation: it writes intents and can
reconstruct/commit missing candidates. This bridge reads existing evidence only.
It cannot promise atomic protection against arbitrary OS-level filesystem ABA;
the service filesystem remains trusted.

| Acceptance group | Expected result |
| --- | --- |
| Base solution differs from candidate; branches modify distinct files | Actual merged candidate bytes/tree/manifest and provenance, literal expected bytes |
| Dirty user checkout; valid single-parent case | No mutable checkout input; legitimate degenerate parent accepted |
| Wrong owner or foreign candidate/worktree/snapshot/task | Rejection before Git without disclosure |
| DB/disk receipt, intent, input binding or parent tampering | Reject without reconstruction |
| Changed HEAD/dirty/replaced path/common-dir/config/alternates | Fail closed using real disposable Git fixtures |
| Missing receipt or wrong/non-full expected SHA | No new intent, directory or commit |
| DB/task/Git/receipt changes during export | Final comparison rejects stale output; label race injection |
| Dispatch and task/approval state | No new operation or state/application side effect |

Reuse existing bounded object-export security tests. Run actual temporary
Git/SQLite public-seam tests in source/wheel/sdist plus Windows source regression;
Docker is unnecessary for this input-only stage and cannot be counted as newly
verified execution. Save sanitized logs/JUnit/build/source identity. D:debug,
F:source, GitHub storage only; no Actions/paid calls/main changes.

After independent acceptance, separately design owner-fixed policy, immutable
task submission/lease/review-version binding, a dedicated real execution and an
independent reviewer gate. Historical asserted completion stays distinct. Full
M5, real adapters/relay, safe apply and M9 remain BLOCKED.
