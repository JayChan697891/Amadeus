# M5B1 local backend verification checkpoint

Tested commit: cfb5304c3979fc1677c73618120c0d33f928018a.
Tree:5e8580769ead8be5a6b4a21ee269aa0a0da01be6. Version0.3.0a2, Issue15/11/7.
GitHub is upload/storage only; all new checks ran locally on D:.

| Environment | Actual result |
|---|---|
| Linux source |754 passed,3 Windows-only skips|
| Fresh wheel installation |754 passed,3 Windows-only skips|
| Fresh isolated sdist build/install |754 passed,3 Windows-only skips|
| Windows source |740 passed,17 explicit skips|
| Complete Linux collector |18/18 checks passed; source clean/stable|
| Real Docker execution |14 tests per installation,42 observations, no skips|
| Post-run exact container inspection |42/42 full IDs independently absent|

Ruff, formatting, mypy26sourcefiles, package builds, origin/SDK smoke and pip check
passed. Lead recomputed saved file/log/build hashes and matched verifier bytes in
Git, wheel, sdist and all real observations. See
acceptance/RELEASE-ACCEPTANCE-REPORT.md and
acceptance/evidence/m5b1-local-inspection.json. Full logs/JUnit/builds and original
local failures are preserved in the indexed evidence archive. Private VM material
was excluded. Reproduction/setup: LOCAL-DEBUG.md.

## Failure and repair

The D-drive Linux VM reproduced14 isolation_mismatch failures before candidate
execution. Only the environment check was false. Docker Config.Env retained bare
image-variable removal markers while actual process os.environ excluded them.
The repair accepts only unique expected removals from validated image metadata,
still rejects extra values/unknown markers, and checks actual environment in the
fixed bootstrap before reading source.114 policy unit tests passed.

A separate root-runner fixture issue placed its host canary under inaccessible
/root; the probe correctly raised PermissionError. It now uses an exclusively
created host /tmp file whose parent is traversable, with no host mount. All
original security assertions and14 actual container cases were retained.

## Scope and pending acceptance

Only the fixed owner-controlled synchronous standalone solution.py profile is
implemented. No durable worker, crash/orphan recovery, task-completion gate,
approval consumption or safe source application is added. Native development
delegation is not an AgentSync adapter/relay test. M6-M9 and real autonomous relay
remain unverified, and formal release remains BLOCKED. Work independently decides
the limited M5B1 checkpoint; neither submission nor passing component tests close
full M5. Main was not modified or merged.
