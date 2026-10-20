# Artifact installation acceptance checkpoint

Issue13, runtime0.3.0a1 unchanged, baseM5A7479dfa. This changes validation tooling only.

The collector can separately require wheel and sourcearchive installs. Each gets an
independent freshvenv, isolatedPython, exactPEP610archiveURI/hash/noneditable proof,
version/SDK/CLI/dependency checks and fullpytest outsidecheckout. ThreeJUnitstreams
(source,wheel,sdist) remain distinct in reports andCI artifacts; no inheritedinstaller
target/prefix/config may redirect writes outside private temporary environments.
Sdist uses actualtar.gz PEP517 buildisolation andno cachedwheel fallback.

Independent review found requestedmissingwheel usednot_run andcouldexit0. This now
fails, with a regression asserting sdist success cannot hide missingwheel. Rawdirty
sourcepatch could preserveknownsecrets; savedpatch now redactsknownpatterns andrecords
originaltextSHA separately. ExactcommittedSHA/sourcehashes retain reproducibility;
redactedpatch is not guaranteed byte-applicable. This is not a general secretdetector.

61 unit policy/orchestration cases passed. Their mocked subprocess results are only
software regression evidence. Actualsource/wheel/sdist runs and finalcurrentSHA nineCI
must be recorded separately before stage acceptance. M5A actuallocal andall9artifact
inspection are preserved in evidence/m5a-ci-inspection.json; those do not certify this
new tooling tree. No paidAPIs, userprojectmutations, mainwrites or merges.

FormalReleaseAcceptance remainsBLOCKED: sourcearchive installation addresses only
one packagegate, not M9 licensing, clients, verifiedsandbox, application or realrelay.

## Executed checkpoint and live feedback

At d8bc57107a1c5f0737316deeb80ac1c089c17ed4, the local three-environment
collector completed all18 checks. Source/wheel/sdist each recorded587 cases:
585 passed,2 Windows symlink-privilege skips. Evidence directory:
F:/syuc/work/sdist-acceptance/release-20261020T084348Z-aae73a4d6636.
The tree stayed clean and unchanged during execution.

GitHub run39395631073 completed8/9 jobs successfully. Ubuntu3.14 source pytest
failed a Git fixture background-maintenance race; wheel/sdist passed. Preserve
that failure separately (ERRORS.md), repair the fixture rather than relaxing the
source immutability assertion, and collect fresh exact-head evidence. Prior local
success and the other8 jobs do not certify the repaired head. Work PR14 acceptance
is pending. Work accepted the narrower M5A PR12 scope at7479dfa; Issue11 and the
formal Release Acceptance Issue7 remain open.

The follow-up independent review also closed two evidence gaps: external pytest
selection/plugin environment variables are removed for all three suite processes,
and the original wheel SHA is rechecked after installed-package tests (as already
done for sdist). Replaced/deleted artifacts fail even if install/JUnit succeeded.
Five added runner regressions give66 policy cases; two real Git configuration
precedence cases cover fixture maintenance overrides. These numbers are component
checks; only the subsequent complete collector/CI establishes newhead execution.
