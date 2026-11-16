# Amadeus 0.3.0a119 development preview

Source and tests: `4be51345d5b8846da58d79df5b8567619e9acfed`.
This preview includes the owner CLI wrong-directory protection and explicit
continuation proposal staging for independent completion of the same receiver
task. Candidate execution still needs its exact owner decisions and the existing
`solution.py` JSON-lines contract. Older packages remain unchanged.

Windows3.12.16 passed19 native build/install checks; fresh wheel and source-package
installs each passed15 focused tests. The same original packages passed16 native
Linux3.14.7 install checks and16 tests in each environment: the same15 cases plus
the real Docker continuation bridge. Each Docker run passed2 JSON cases and19
isolation checks; the receiver completed verified, the failed source stayed failed,
and the container was removed. All97 runtime members match the frozen source and
both packages in all four installs.

See [actual results and reproduction](../../../docs/acceptance/evidence/core-preview-a119/summary.json),
`manifest.json` and `SHA256SUMS`. These are branch-stored preview artifacts,
not a published Release.

From a new folder containing the downloaded wheel:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install .\agentsync_local-0.3.0a119-py3-none-any.whl
& .\.venv\Scripts\amadeus.exe --data-dir "$PWD\demo-01" demo --durable
```

Installation needs the declared dependencies or a prepared offline wheelhouse.
The durable CLI demo is simulated and reports `simulation_only/unverified`.
The tested continuation examples use local protocol fixtures, not actual models.
Full a119 suites, complete platform coverage, macOS and real-client acceptance
remain **NOT RUN**. Formal Release remains **BLOCKED**.
