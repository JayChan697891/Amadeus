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
