# M5A development acceptance report

Version0.3.0a1/schema6; Issue11; parentPR10 head98bd361. Currentbranchfeature/m5a-permissions.
This is a bounded permissions/approval/audit checkpoint, not completedM5 or formalrelease.

## Behavior and migration

New members and migrated legacy agents start viewer. Owner grants exact worker/
reviewer role sets; empty revokes. Authorization precedes idempotent replay, object
queries and Git. Current session tokens cannot bypass revoked roles. Old tasks,
context, reviews, locks and workspace records persist through schemas1-5 upgrade.
Owner role/approval methods are separate Core/SDK/CLI/HTTP operations and absent
fromMCP; four agent methods make33typedtools. CLI credentials use JSONstdin.

Bounded approvals resolve same-project immutable candidateSHA and requestingagent,
with version/expiry/revocation and current-state replay checks. Owner approval never
executes/appliesanything. Candidate remains awaiting_human_approval. Admincredential
possession is the authority boundary, not proof of a physical human againstsameOS.

Structured audit stores only whitelisted IDs,operations/outcomes,codes,versions,
requestdigest,time. It excludes rawpayload/result/reason/path/command/token.
Successful changes and audit commit together; authenticated denials log only safe
same-project metadata afterrollback. Unauditable deniedoperations remain denied.
No append/update/deleteaudit API or DB-owner tamperproof claim.

## Actual targeted evidence

IndependentM5 role/approval/migration tests were executed; a realtwochildprocess
ownerdecision race hasonewinner andno credentialfiles. ActualMCP33/noowner/default
viewerdenial, outofbandownergrant, all4agenttools, HTTPadmin+bearer andCLIstdin grant
were exercised (metadatafixture, notGit/modelproof). Legacysetup nowexplicitly grants
roles while preservingexistingassertions; no global permission-autogrant patch.
Lead independently ran179 initialnewcases and3additionalauditfailure transactions:
failedaudit rollsback task/cache andownergrant; denialauditfailure cannot restore
revoked cachedwrite. Owner andsession credentials remain distinct.

Lead interface review also found unbounded/nested CLIJSON and reserved Pythonargument
collisions. The owner CLI now caps UTF8stdin64KiB, catches parserdepth/Unicode errors
and rejects collidingkeys before constructingCore. Five malformedinput cases and
two actualtransport cases passed. First fullcollector source passed556/2skips, but
document formatting and the subsequentCLI repair changed its source snapshot; that
run cannot certify the finalstablecandidate and must not be promoted to acceptance.

Finalcomplete source/wheel execution andcurrentPR9platformCI must be inspected
separately. Targetedresults do not substitute for this gate. Reports andlogs collect
version,exactSHA,dirty/sourceidentity,commands,JUnit,artifacts andhashes; knownsecret
values are redacted before durablelogs/JUnit. Destructive fixtures run underF scratch.

## Release conclusion: BLOCKED

M5B independent verifier and approvalconsumption/application are unimplemented.
Existing review_task is a differentAgent's ASSERTED evidence, not independent test
execution. Running submitted pytest/import/build code requires actualverifiedOS
isolation; allowlistedargv alone is insufficient. This localruntime hasnoDocker/
Podman/runhcs command; WSL presence is not validatedsandbox evidence. Failclosed until
a supported runtime is available; never fall back to unconfined host subprocess.
M6-M9 and real modelclientautonomousrelay remain unverified. No paidAPIs, mainwrite
or merge. FormalReleaseAcceptance Issue7 staysopen; Work must inspectactualPRhead.
