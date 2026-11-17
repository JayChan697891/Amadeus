# Amadeus a122 development preview

Source: `5232e9e8bd33a949f7ffdc68410cd614a297af66`. This development preview is
stored on the branch. Formal Release remains BLOCKED.

Shared adapter scheduling and pre-launch waits now check the absolute deadline
before cancelling work. Early timer callbacks reschedule the deadline check and
keep the existing wait alive.

From this repository on Windows with Python 3.12:

```powershell
py -3.12 -m venv .venv-a122
& .\.venv-a122\Scripts\python.exe -m pip install .\releases\0.3.0a122\preview-5232e9e\agentsync_local-0.3.0a122-py3-none-any.whl
& .\.venv-a122\Scripts\amadeus.exe --data-dir "$PWD\local-data\amadeus-a122-01" demo --durable
```

Choose a new data directory. The demo uses simulated agents and reports
`simulation_only: true` and `verification: unverified`.

Windows 3.12 passed 19 native build and installation checks. Linux 3.14 passed
16 installation checks using the same archives. Each wheel and source-archive
install passed the same 97 targeted cases, using known local Python process and
approval fixtures. Root checked source, archive and installed runtime hashes.
Root and Astra accepted the scoped results.
[Windows evidence](../../../docs/acceptance/evidence/core-preview-a122/windows/summary.json),
[Linux evidence](../../../docs/acceptance/evidence/core-preview-a122/linux/summary.json), and
[original failed reproductions](../../../docs/acceptance/evidence/core-preview-a121/adapter-deadline/summary.json).

Download hashes are in [SHA256SUMS](SHA256SUMS). The complete platform matrix,
full a122 regressions and real-client checks remain unverified. Historical static
FAIL and pending license review remain recorded in [progress](../../../docs/PROGRESS.md).
