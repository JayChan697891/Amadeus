# Evidence scope

m4a-ci-inspection.json records actual inspection of all9 PR8 artifacts. Their merge
commit tree matches head fe3ac74. The original artifacts remain in Actions run39374902366.

M4B binding RED XML preserves the actual failing regression before the request-input
binding repair. GREEN XML records the same regression after repair; neither is a
full candidate acceptance. Known credential fields were redacted before archival.
The defect is reproduced by an interrupted durable receipt/SQLite rollback followed
by the same request ID with a different snapshot/ordered pair; current source rejects
that request and preserves the original receipt. Keep these regression cases.

Independent JUnit was generated before the final additional tests; use final
collector/CI evidence for complete counts and source identity. These are actual
isolated Git/Core tests, not real model/client autonomous relay results.
