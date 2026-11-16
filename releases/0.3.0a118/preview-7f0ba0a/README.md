# Amadeus 0.3.0a118 development preview

Source and tests: `7f0ba0a4ffbc55262d8a01d6203d7cb7b5cf3ab5`.
This preview includes the workflow recovery-path fix: `status`, `resume` and
`cancel` reject a missing database without creating empty project state.
Existing a117 packages and their evidence remain unchanged.

Windows 3.12.16 offline validation passed 19 native checks. Fresh wheel and sdist
installations each passed the same 12 focused cases; all 97 runtime members match
the frozen source. See the [actual evidence](../../../docs/acceptance/evidence/recovery-preview-a118/summary.json)
and `SHA256SUMS` here. These are branch-stored preview files, not a published Release.

From a new folder containing the downloaded wheel:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install .\agentsync_local-0.3.0a118-py3-none-any.whl
& .\.venv\Scripts\amadeus.exe --data-dir "$PWD\demo-01" demo --durable
```

The installation needs the declared dependencies or a prepared offline wheelhouse.
Use a new demo directory each time. The durable demo uses simulated identities and
reports `simulation_only/unverified`; it does not call a model.

Full a118 regression, Linux/macOS installation, Docker and real-client acceptance
are **NOT RUN**. Earlier a117 results retain their original version and scope.
Formal Release remains **BLOCKED**.
