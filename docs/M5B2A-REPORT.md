# M5B2A local verification checkpoint


## M5B2A lead inspection and scope

Tested commit613c95dab054f013c6a6029949e2678ad2056e37,
tree0eb394df1d83c13888bf1068b2625f60adc6a250, version0.3.0a3/schema7.
All18 local collector checks passed against clean/stable frozen source. The
checkout suite used a fresh noneditable installation built from that checkout;
all27 installed Python modules were independently compared byte-for-byte with
the checkout. It was not an editable source environment. Independent wheel and
sdist installations each also ran the complete783-case suite:780passed and
3Windows-only skips in each of the three environments.

The26 new ledger tests cover authentication before replay, project isolation,
immutable input binding, idempotency, token/version/expiry fencing, explicit
interruption/cancellation, real thread/spawn-process claim races, schema upgrade
and audit rollback. These are non-executing ledger tests. All public ledger
assessments remain unverified; no passed completion or executable worker exists.

Existing M5B1 Docker tests executed14cases in each installation,42new observations;
the lead matched verifier hashes, inspected effective controls and independently
queried all42 exact container IDs after execution, all absent. Those observations
verify the existing bounded backend, not an integrated durable worker. Saved
artifact/log hashes and three complete JUnit files were independently checked.
New jobs/schema/permissions module bytes match Git, wheel and sdist.

Windows developer preflight766pass17skip was before final freeze/version bump;
it is separately labelled and is not a final-SHA Windows attestation. Evidence:
evidence/m5b2a-local-inspection.json and M5B2A-613c95d-local.tar.gz, containing
reports, JUnit, sanitized logs, wheel/sdist, actual backend results and module/cleanup
bindings. No GitHub execution. Private debug keys/seeds/disks remain excluded.

M5B1 independently passed Work acceptance in PR16 comment6292907383; Issue15
closed. M5B2A Work review remains a separate decision. Issue11/7 and formal
release remain BLOCKED pending integrated execution/recovery, applicable task
evidence, approval/application, real client adapters/relay and M9 gates.
