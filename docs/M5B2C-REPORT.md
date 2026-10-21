# M5B2C local acceptance report

Tested product: `c1f2e83a61af5c267e3374dd46398b2a57b6abf1`; tree `de68cde10628e48122fad14409983ccbab570802`.
Version0.3.0a5/schema9. Independent Work acceptance is a separate gate.

## Results and evidence

All18local collector checks passed. Source, fresh wheel and isolated sdist each
executed898cases:895passed/3Windows-only skips/0failures/0errors. All43new
reconciliation policy cases and all26actual Docker cases ran in each Linux
environment without skips. Windows frozen source executed898cases:
869passed/29explicit skips (26Linux actual cases and3unavailable link privileges).
Windows was rerun after line-ending normalization; its205-file source snapshot
is identical to Linux. Local source is byte-identical to the tested Git objects.

The lead independently recomputed collector artifact and log hashes, parsed all
four JUnit files, checked install origins and compared6critical modules between
Git, wheel and sdist. All29Python source modules match the source installation.
The prior Docker/executor/jobs modules remain unchanged. A separate native
reviewer inspected the security boundary and independently ran policy tests;
neither developer agents nor this review count as real AgentSync client adapters.

The78actual container observations comprise42existing backend regressions,
21owner executions and15new cleanup cases. Each installation's five new cases:

| Case | Actual observation | Required durable result |
| --- | --- | --- |
| Created hard exit | Trusted executor exits immediately after saving full create ACK; service DB reopened | Removed-and-absent receipt; original unverified |
| Running hard kill | Docker Running=true observed, trusted process group SIGKILL, DB reopened | Removed-and-absent receipt; original unverified |
| Initial absence | Fixture removes exact object before reconciliation | Unresolved receipt, never inferred cleaned |
| Protected rename | Fixture changes object name; real inspect sees mismatch and object is retained | Unresolved, no removal |
| Lost create ACK | Trusted process exits after daemon create but before ACK persistence | Identity-unavailable rejection; no receipt or product removal |

Only lease expiry is injected into disposable test data to avoid a300second wait;
Docker replies and removal outcomes are real. Across15new objects, the reconciler
removes6, the initial-absence fixtures remove3before reconciliation, and safety
fixtures remove6protected/unknown objects afterwards. The final independent
inspection issues no removal and proves all78exact full IDs absent. This is not
a claim that the product reconciler removed all78objects or executed78candidates.
Every new original execution remains unverified, including successful cleanup.

Archive: `M5B2C-c1f2e83-local.tar.gz`, 609097bytes,
SHA256 `6172078e1613598a6e4f537fd70d7459f8b7244373973aeeb768cd918e3fbe42`. The self-excluding file manifest covers117files.
Index: acceptance/evidence/m5b2c-local-inspection.json. The archive preserves raw
sanitized logs, JUnit, build artifacts, requirements, commit/tree/source identity,
observations and reproduction scripts; no VM credentials, disks, seeds or test DBs.

## Limits and release conclusion

This stage supplies an explicit owner-only one-shot cleanup observation. A crash
after intent consumes the attempt permanently; there is no resume, retry,
scheduler, unknown/late-create recovery or historical daemon-identity proof.
No original backend result is replaced, and no cleanup grants passed status,
cleanup_confirmed, job reuse, task acceptance or source application. Unsupported
platforms never execute candidates on the host.

The42formal requirement scenarios remain not_run as complete scenarios; inventory
is18existing/13partial/11missing, which describes component coverage rather than
formal acceptance. Evidence statuses remain38not_run/4unverified. Real Codex,
Claude Code and other control adapters, autonomous relay, managed candidate/task
applicability, verified task gate, approval consumption/safe apply, full platform
matrix and M9 acceptance remain outstanding. Formal Release is **BLOCKED**.
Issues11/7remain open. GitHub was storage only; no Actions were requested or used,
no paid calls were made and main was not modified or merged.

This report/evidence publication follows the tested product commit and changes
documentation only; it is not described as another test execution of a later tree.
