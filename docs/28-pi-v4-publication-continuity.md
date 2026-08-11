# Pi V4 Publication Continuity Record

Last checked date: 2026-08-05

## Purpose and authority

This document records how the approved Pi V4 trusted-publication plan relates
to AgentHarness. It is a continuity aid, not a source of runtime authority.

The normative V4 sources are maintained with Pi:

- `docs/superpowers/specs/2026-08-05-runtime-authorization-v4-trusted-publication-boundary-design.md`;
- `docs/superpowers/plans/2026-08-05-runtime-authorization-v4-trusted-publication-boundary.md`; and
- `release/2026-08-05-runtime-authorization-v4-trusted-publication-boundary.md`.

If this document conflicts with the Pi design or with AgentHarness
[`T060`](./25-pi-runtime-authorization-readiness-adr.md), those documents
control.

## Current cross-project boundary

AgentHarness remains a pre-execution evidence control-plane. It does not own
Pi runtime enforcement, issue or consume permits, authorize publication,
authorize a tool, select a publisher target, connect an executor, or perform
tool execution. The current Pi bridge is still block-only and applicable
results remain `not_executed`.

Pi V4 changes the deployment-integrity design for one offline publication
step. It replaces a caller-owned staging writer with a closed unprivileged
bundle producer and a separately trusted root-owned publisher. The publisher
is deliberately outside the AgentHarness evidence path: AgentHarness evidence
is not a publisher input, publication receipt, capability, grant, arming
signal, or fixture-read authorization.

## Status and stop line

- The Pi V4 design and implementation plan are approved planning records.
- V4 Task 1 has unaccepted local red-test/deployment material in its execution
  repository; it is not implementation or validation evidence.
- V1, V2, V2.1, V3, and the Pi/AgentHarness live-shadow boundary retain their
  existing block-only and `not_executed` behavior.
- Runtime authorization remains `NOT IMPLEMENTED` and `NO-GO` under T060/T062.
- No current record authorizes package installation, root execution, service
  startup, issuer arming, fixture creation, a real read, or Pi tool execution.

Task 10 publication approval and Task 11 synthetic fixture-read approval are
separate future gates. Neither can be inferred from V4 planning, an
AgentHarness observation, an `allow_candidate`, a publication receipt, or a
successful unit test.

## Handoff rules

1. Keep evidence production, policy evaluation, authorization issuance,
   artifact publication, and fixture execution as distinct identities and
   trust boundaries.
2. Do not widen AgentHarness's interface to deliver raw arguments, secrets,
   host paths, publisher inputs, deployment artifacts, runtime grants, or
   fixture contents.
3. Cross-repository work may verify parser separation, data leakage, and
   block-only behavior, but may not use that verification to authorize runtime
   execution or privileged publication.
4. Before beginning an implementation task, re-read the Pi V4 plan's global
   constraints and task-specific stop conditions. An uncommitted checkout is
   never a root-owned publisher trust source.

## Next safe work

The next V4 implementation action belongs to Pi's isolated execution
repository: finish Task 1's immutable catalog and bundle contract with its
focused red/green tests. AgentHarness does not need a new authorization or
execution feature for that work.

Any future AgentHarness work remains governed by T060/T062's deny-only,
evidence-only, and explicit-approval requirements. A V4 publication plan does
not satisfy the T063–T072 readiness gates.
