# M5B2C acceptance checkpoint — awaiting frozen-source evidence

Scope: explicit owner one-shot cleanup receipt for an expired execution with a
complete acknowledged container ID. See M5B2C-CONTRACT.md / M5B2C-GUIDE.md.
Version0.3.0a5/schema9. No automatic recovery/retry, job reuse, restored success,
task gate, safe apply or real client relay is claimed. Formal Release is BLOCKED.

Before freeze, root independently inspected the implementation, passed all43new
policy cases, Ruff/format and mypy, and incrementally executed5actual Docker cases
in the dedicated D: Linux VM. A separate native reviewer found no blocking defect
within this limited contract. These development observations do not certify the
eventual product SHA and do not replace independent Work acceptance.

Final procedure: freeze clean source, run local source/fresh wheel/isolated sdist
full collector and Windows regression; verify immutable source/tree/package/module
identity, individual logs/JUnit and original-vs-reconciliation results; inspect
all observed container IDs independently after fixture cleanup. Upload sanitized
evidence only, then hand the exact tested code and evidence to Work. GitHub is
storage only; no Actions and no main merge.
