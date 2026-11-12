# Independent release artifact installation

Issue #13 extends the acceptance collector's package evidence. Runtime behavior and
version stay at the M5A checkpoint. This is test tooling, not completed M9 acceptance.

Run the collector outside production state with a fresh evidence directory:

```powershell
python tools/release_acceptance.py --output D:/agentsync-debug/release-evidence --scratch-root D:/agentsync-debug/ra --run --package-install --sdist-install
```

On Windows, use a short scratch path so temporary Git worktree metadata stays
within Git for Windows' path limits.

The source, wheel and source-distribution checks have separate identities, logs and
JUnit files. Each artifact uses a fresh environment; a successful wheel cannot hide
a failed source archive. The sdist is built and installed as the actual tar.gz with
build isolation, then checked for version, site-packages origin, SDK/CLI/dependencies
and the full test suite from outside the checkout. Original artifact hashes accompany
the installation result. No editable installation is used for artifact verification.

Installer destination overrides must not redirect writes outside owned temporary
environments. Temporary credentials/databases/environments never enter CI artifacts.
Known credentials in logs/JUnit/diff are redacted; hashes are not independent signatures
and pattern filtering is not a promise to discover every possible secret.

Use `--require-release` separately to enforce formal acceptance (exit 2 while blocked).
Default successful CI means only its explicitly executed regression/install checks
passed. Full M9 licensing/client/platform evidence, independent sandbox execution,
approval application and real autonomous two-client relay remain separate gates.
