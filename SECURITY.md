# Security reporting and boundaries

Do not include credentials, databases or private conversations in public issues.
There is no hosted service or published security contact yet; report privately to the repository owner.

Alpha is a local coordination service. The HTTP bearer credential and project/session credentials
are separate. Run only on loopback, use a private local data directory, and keep credentials out of logs.
Any process running as the same OS user may read or modify that user's files; this is not a sandbox.
MCP host permissions do not grant AgentSync control of arbitrary desktop sessions.

Submitted descriptions/results/evidence are untrusted text. No shell commands are executed from them.
Database tokens are hashed; issued credentials must be protected by their caller.
Agent registration requires the project admin token. Task mutation requires matching identity,
project, version and current lease. A distinct agent must review a submitted result.
Full roles, risk approvals, audit redaction, context protection and independent evidence verification
are M3-M5 work, not claimed as complete here. Core emits only coded public errors.
