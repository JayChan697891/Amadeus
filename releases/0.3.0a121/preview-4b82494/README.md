# Amadeus a121 development preview

Source: `4b824949e60492e11756586c3a6ecd5a5f7811d8`. Stored on the development
branch; this is not a formal Release. Earlier packages remain unchanged.

This preview fixes `demo` and `owner` JSON output when a Chinese path or recovery
reason meets a legacy Windows output encoding such as CP1252. Operations no
longer fail to print their receipt after saving state. JSON uses ASCII escapes;
decoding restores the original Unicode values. The owner/recovery rules and
simulation-only status are unchanged.

From this repository with Python3.11 or newer:

```powershell
python -m venv .venv-a121
& .\.venv-a121\Scripts\python.exe -m pip install .\releases\0.3.0a121\preview-4b82494\agentsync_local-0.3.0a121-py3-none-any.whl
& .\.venv-a121\Scripts\amadeus.exe --data-dir "$PWD\local-data\amadeus-a121-01" demo --durable
```

Use a new directory. This offline demonstration uses simulated agents and reports
`simulation_only: true` / `verification: unverified`; it makes no model call.

Windows3.12 fresh wheel and source-package installs each passed23 targeted cases,
including two real CLI regressions for Unicode output. All19 native build/install
checks passed. The source, archives and97 installed runtime members were checked;
independent review accepted only this bounded scope. See
[actual installation evidence](../../../docs/acceptance/evidence/core-preview-a121/windows/summary.json)
and [original failed reproductions](../../../docs/acceptance/evidence/core-preview-a120/cli-output-encoding/summary.json).

The same original archives subsequently passed16 Linux3.14 native checks and23
cases per fresh install, with the same case identities/outcomes as Windows.
See the [Linux supplement](../../../docs/acceptance/evidence/core-preview-a121/linux/summary.json).
No package was rebuilt; the original manifest preserves its initial Windows scope.

Hashes are in [SHA256SUMS](SHA256SUMS). macOS, the full a121 matrix and
real clients remain NOT RUN. Historical static FAIL remains;
license review and formal-release authorization are pending. Follow
[current progress](../../../docs/PROGRESS.md) for later bounded supplements.
