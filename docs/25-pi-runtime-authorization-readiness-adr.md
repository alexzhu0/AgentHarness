# Pi Runtime Authorization Readiness ADR

## Metadata

- **Task:** T060 review round 2
- **ADR status:** Proposed / readiness review only
- **Current decision:** **NO-GO for real execution**
- **Date:** 2026-07-13
- **Implementation status:** **NOT IMPLEMENTED**

## Context and ownership boundary

AgentHarness remains an evidence-only pre-execution control-plane component.
It does not execute tools, own runtime authorization, serve as bootstrap trust
root or signing authority, or implement any requirement in this ADR. The
current Pi bridge remains block-only, returns `result_status: not_executed`,
and performs no real execution.

This ADR proposes a future contract owned by Pi or an external runtime. That
party is called the **runtime owner** throughout this ADR. Only the runtime
owner may authenticate inputs, compose authorization, activate a release,
issue or consume permits, sign runtime records, enforce containment, manage
credentials and kill switches, or execute. AgentHarness evidence, including
`allow_candidate`, is at most one necessary input and is never authorization.

The existing boundaries remain authoritative:

- [Pi integration boundary and
  contract](./17-pi-integration-boundary-and-contract.md)
- [Pi integration readiness pause
  review](./22-pi-integration-readiness-pause-review.md)
- [Pi observation/evidence contract
  v1](./24-pi-observation-evidence-contract-v1.md)

## Decision

The current decision is **NO-GO for real execution**. A future runtime may be
considered only after every unchecked gate has approved evidence and a separate
milestone approves activation. The runtime owner **MUST** deny unless every
required input is authentic, fresh, exactly bound, mutually consistent, and
listed in the pinned authorization release manifest. Missing, duplicate,
unknown, ambiguous, stale, unsupported, timed-out, or error states **MUST**
deny.

## Runtime-owned bootstrap trust and anti-downgrade

This contract is proposed and **NOT IMPLEMENTED**.

The runtime owner **MUST** independently provision a bootstrap trust policy
outside the authorization release manifest and outside AgentHarness. The
manifest cannot define, replace, weaken, rotate, recover, or otherwise redefine
that policy. AgentHarness is not the bootstrap trust root or signing authority.

The bootstrap trust policy **MUST** define:

- a threshold authorization rule with independently controlled root holders;
- accepted root identities, algorithms, key epochs, and minimum security
  strength;
- protected installation and storage resistant to ordinary runtime,
  deployment, and manifest modification;
- controlled threshold root rotation and separately controlled recovery,
  including authenticated ceremony, durable records, and compromise response;
- fail-closed verification when policy, threshold, root, state, clock, or
  verifier evidence is missing, stale, ambiguous, inconsistent, or invalid;
  and
- compatibility and anti-downgrade floors that a release cannot weaken.

The runtime owner **MUST** keep a monotonic activation epoch in protected,
durable runtime state. Every activation record and permit **MUST** bind the
exact activation epoch. A newly activated release **MUST** use an epoch greater
than every previously committed activation epoch.

Rollback **MUST** first disable execution, assert kill switches, cancel all
permits, and revoke credentials. It then requires a separately authenticated
threshold rollback authorization under the bootstrap trust policy. Rollback
may select only one explicitly linked, previously approved predecessor manifest
digest. It **MUST NOT** select floating or individual components. Reactivation
creates a new activation record at a higher activation epoch. It **MUST NOT**
reuse or replay an old activation, epoch, approval, permit, or authorization.

## Atomic authorization release manifest and service pins

One immutable, authenticated authorization release manifest **MUST** atomically
pin the complete authorization release. It **MUST** include:

- manifest ID, version, digest, issuer, signatures, approvals, validity,
  release epoch, and explicitly linked approved predecessor digest;
- an exhaustive ordered list of every gate and policy, with exact ID, digest,
  applicability, precedence, input schema, and output schema;
- runtime executable digest, configuration digest, request and response schema
  versions, adapter digest, and sandbox profile digest;
- bootstrap-policy compatibility requirements without redefining the
  independently provisioned bootstrap policy;
- an exhaustive envelope-type issuer authorization matrix described below;
- an exhaustive canonical argument-presentation schema for each tool/action,
  with exact schema ID and digest;
- exact cohort manifest ID and digest, content snapshot digest, and all content
  bindings described below; and
- a compatibility matrix binding every component, policy, protocol, schema,
  trust epoch, deployment, and configuration.

For each approval revocation service, activation revocation service, credential
issuer, primary audit channel, emergency audit channel, kill-switch provider,
authenticity verifier, and trusted clock, the manifest **MUST** pin:

- exact service identity and authenticated endpoint identity;
- exact protocol and schema version;
- trust epoch and accepted trust chain;
- deployment and configuration digest, or an authenticated attestation that
  binds both digests; and
- explicit compatibility constraints with the runtime and every dependent
  policy or schema.

Approval applicability **MUST** derive only from the exhaustive pinned policy
set. No implementation discretion, fallback, default, or unlisted policy may
decide whether approval is required. Omission, duplication, incompatibility,
partial evaluation, drift, substitution, downgrade, or unattested deployment
**MUST** deny.

### Envelope-type issuer authorization matrix

The atomic manifest **MUST** map each envelope type and authority domain to an
exact authorized issuer identity, exact key ID and key epoch, certificate or
key purpose, and single allowed signing or attestation role. Each matrix row
is therefore the tuple `(type, authority_domain, issuer_identity, key_id,
key_epoch, key_purpose, role)`. The manifest **MUST** instantiate concrete
values for every tuple below:

- `evidence_attestation`: evidence domain; pinned verifier; attester.
- `human_approval`: human-approval domain; pinned approval system; signer.
- `no_approval_decision`: policy domain; pinned decision service; signer.
- `activation`: activation domain; pinned activation authority; signer.
- `rollback_authorization`: bootstrap domain; pinned threshold; signer.
- `permit`: runtime-composition domain; pinned composer; signer.
- `approval_revocation_response`: approval-revocation domain; pinned approval
  revocation service only; responder.
- `activation_revocation_response`: activation-revocation domain; pinned
  activation revocation service only; responder.
- `global_kill_switch_observation`: global-kill-switch domain; pinned global
  kill provider only; observer.
- `session_kill_switch_observation`: session-kill-switch domain; pinned session
  kill provider only; observer.
- `primary_audit_acknowledgement`: primary-audit domain; pinned primary audit
  channel only; acknowledger.
- `emergency_audit_acknowledgement`: emergency-audit domain; pinned emergency
  audit channel only; acknowledger.

Each row **MUST** contain concrete values rather than role-only placeholders.
The authenticity verifier **MUST** require the envelope type, authority domain,
issuer, key, and purpose to match one exact row before accepting the envelope.
Cross-domain substitution **MUST** deny. A key authorized for one row
**MUST NOT** issue or attest another envelope type, even if its algorithm,
trust chain, or owner is otherwise accepted. Certificate extended-key usage,
key purpose, signing role, issuer identity, key ID, and key epoch **MUST** all
match. Self-declared issuer or role fields are insufficient. Unknown issuers,
unknown types, cross-role issuance, wrong-purpose keys, and substituted issuers
**MUST** deny.

AgentHarness **MUST NOT** appear in this matrix as a trust root, runtime signer,
permit issuer, or runtime authority. Evidence attestation is owned by a
runtime-owned transport/evidence verifier that authenticates and attests the
AgentHarness evidence it receives.

## Runtime-owned authenticity contract

The runtime owner **MUST** operate the pinned authenticity verifier and require
authenticated envelopes for AgentHarness evidence attestations, approvals,
no-approval decisions, activation records, rollback authorizations, permits,
approval and activation revocation responses, global and session kill-switch
observations, and primary and emergency audit acknowledgements. Each envelope
**MUST** bind its type, authority domain, version, payload digest, issuer
identity, algorithm, key ID, key epoch, issuance time, expiry,
release-manifest digest, and applicable activation epoch.

Forgery, signature mismatch, unknown or revoked key, stale epoch, trust drift,
pin mismatch, attestation failure, verifier unavailability, or verifier error
**MUST** deny. T060 implements no verifier, envelope, key handling, signing,
trust material, or runtime authorization.

## Enablement, activation, revocation, and kill switches

Future execution requires all three independent conditions:

- `execution_enablement=true`;
- `global_kill_asserted=false`; and
- `session_kill_asserted=false`.

The runtime owner **MUST** read authenticated runtime-owned state during
composition and immediately before permit consumption. An asserted kill switch
always denies and requires bounded termination. Unreachable, stale, unknown,
ambiguous, or conflicting state **MUST** deny. Assertion **MUST** cancel all
outstanding permits, prevent new or unstarted execution, and terminate started
work within the manifest-pinned bound.

Environment flags are insufficient. Execution also requires a separately
authenticated, expiring, and revocable activation record approved under
separation of duties. It **MUST** bind its unique record ID and digest, exact
activation epoch, runtime and session scope, release-manifest digest, cohort
manifest and content snapshot digests, issuer, threshold approvers, validity,
and revocation identifier.

The runtime owner **MUST** use an authoritative activation revocation service.
That service **MUST** be separately pinned and independent of activation
issuance. The manifest-pinned trusted clock, maximum observation age, and
clock-uncertainty bound define freshness. The runtime owner **MUST** query
activation revocation during composition and immediately before permit
consumption. Unavailable, stale,
ambiguous, conflicting, unverifiable, or revoked state **MUST** deny and cancel
all permits bound to that activation record.

## Human approval binding and revocation

Whenever manifest policy requires human approval, the authorization decision
**MUST** have `approval_kind=human`. No automated, service, inherited, absent,
or no-approval decision can satisfy that requirement.

The manifest **MUST** pin an exhaustive canonical argument-presentation schema
and its digest for each tool/action. That schema **MUST** classify every input
schema field and every execution-affecting derived value as display-required.
Unknown, extra, omitted, unclassified, or misclassified fields **MUST** deny.

The human approval system **MUST** require strong human authentication,
authenticated user presence, an intentional approval ceremony, and explicit
confirmation. Before confirmation it **MUST** present one canonical,
schema-bounded, non-truncated view of:

- authenticated requester and executing principal;
- exact tool and action;
- canonical target;
- every execution-affecting argument name, type, and value, plus the full
  canonical projection digest and `arguments_digest`;
- bounded risk classification and material risk facts; and
- runtime/session, cohort, release, policy, and expiry context.

The presentation **MUST** bind the presentation-schema ID and digest and the
exact canonical argument projection and digest. The approval envelope
**MUST** bind those same schema and projection values, `arguments_digest`, the
exact presentation digest, explicit confirm event, ceremony ID, presence
proof, human identity, authentication strength, unique approval ID and nonce,
issuance and validity, revocation ID, and every presented authorization
binding. Digest-only approval remains prohibited. If any execution-affecting
value cannot be displayed safely, fully, unambiguously, and without truncation
or redaction, the human approval system **MUST** deny.

Whenever human approval is required, the requester, evidence producer, runtime
operator, executing principal, and approval-system operator roles **MUST** be
mutually disjoint from the human approver and from each other. This role
disjointness is unconditional. A role collision, shared credential, delegated
self-approval, or unverifiable separation proof **MUST** deny.

The runtime owner **MUST** query the pinned authoritative approval revocation
service during composition and immediately before permit consumption.
Trusted-clock
freshness rules apply. Unavailable, stale, unknown, conflicting, ambiguous, or
revoked state **MUST** deny and cancel every permit bound to that approval.
Argument, target, presentation, identity, policy, or content mutation
invalidates approval. Policy deny always overrides approval.

## Deny-overrides composition

The runtime owner **MUST** authenticate the bootstrap policy, full manifest,
and every envelope; derive the exhaustive gate set; and evaluate every gate.
It **MUST** collect every deny, unsupported state, and error without weakening
results. Before permit issuance it **MUST** verify enablement, kill switches,
activation and revocation, evidence, identities and digests, approval decision
and revocation, service pins, sandbox, credentials, cohort content, and audit.

No component may downgrade, mask, override, or normalize deny into allow. Only
the runtime composer may issue a permit after the primary audit channel has
durably acknowledged the composed decision. The executor **MUST** reject any
operation without the exact valid permit.

## Permit envelope and atomic lifecycle

Each authenticated permit envelope **MUST** contain:

- version, unique permit ID and nonce, issuer, key ID, key epoch, issuance,
  not-before time, expiry, and a maximum TTL of 30 seconds;
- exact runtime/session ID, requester, executing principal, `tool_call_id`,
  tool, action, canonical target, and `arguments_digest`;
- exact release-manifest ID and digest;
- exact activation record ID and digest and activation epoch;
- evidence ID and digest;
- one explicit approval tagged union, with no absent or implicit state:
  - `approval_kind=human`, exact human approval ID and digest; or
  - `approval_kind=no_approval_required`, exact authenticated decision ID and
    digest bound to the exact pinned policy ID and digest;
- exact cohort manifest ID and digest and content snapshot digest;
- exact root filesystem image, workspace snapshot, `README.md`, and expected
  output digests;
- sandbox profile digest and unique sandbox instance;
- credential lease reference, or authenticated no-credential decision;
- audit decision ID and primary durable acknowledgement reference; and
- kill-switch and revocation observation IDs, epochs, states, and times.

The lifecycle is `issued` to exactly one of `consumed`, `cancelled`, or
`expired`. Immediately before execution, the runtime owner **MUST** revalidate
every binding, both revocation sources, activation, enablement, kill switches,
content digests, and primary audit health.

Permit consumption and sandbox launch **MUST** be atomically coupled under a
runtime-owned revocation lease and revocation epoch. The runtime owner
**MUST** revalidate both approval and activation revocation epochs while
acquiring that lease and again immediately before the first instruction or
tool side effect. It then **MUST** consume the permit exactly once by
compare-and-swap within the coupled operation. A revocation epoch change after
the compare-and-swap but before launch **MUST** prevent launch. The consumed
permit remains terminal and **MUST NOT** be reused, retried, or reissued.

Revocation of consumed-but-unstarted work **MUST** cancel that work and prevent
launch. Revocation after start **MUST** terminate the sandbox within the
manifest-pinned bound and durably audit the terminal outcome under the audit
channel rules.

Reuse, replay, reissue, or retry is forbidden. A crash or uncertain persistence
after consumption is `terminal-uncertain`. The runtime owner **MUST** record it
under the audit rules, assert the session kill switch, terminate the sandbox,
revoke credentials, and never retry, reissue, or replay the operation.

## Enforceable sandbox, content checks, and credentials

Execution **MUST** occur in an OS-enforced container, VM, or sandbox. A process
boundary alone is insufficient. The exact sandbox profile **MUST** enforce:

- an approved immutable read-only root filesystem image digest;
- an approved immutable non-sensitive workspace snapshot digest;
- a private empty temporary filesystem;
- no network, devices, host namespaces, host sockets, or inherited handles;
- syscall restrictions, no ambient capabilities, and no privilege escalation;
- exact quotas of 16 PIDs, 32 file descriptors, 1 CPU second, 128 MiB memory,
  1 MiB private tmpfs, 64 KiB total stdout/result, and 2 seconds wall time;
- zero stderr or diagnostic leakage; and
- default denial of subprocesses and all unlisted filesystem access.

The cohort manifest **MUST** bind the approved root filesystem image digest,
immutable non-sensitive workspace snapshot digest, and content snapshot digest.
It also **MUST** bind `README.md` as an exact regular-file type, exact mode,
exact content digest, and no-link object. It **MUST** bind the expected output
type and digest. A different root, workspace, file type, mode, content, link
identity, or output **MUST** deny.

The runtime owner **MUST** verify those identities and digests before permit
issue, immediately before file access, and after access. Before returning it
**MUST** verify the expected file and output type and digest and enforce the
output quota. Path resolution **MUST** resist traversal, symlink and hardlink
substitution, mount replacement, and time-of-check to time-of-use races.

Credentials **MUST** be ephemeral, least privilege, call-scoped, inaccessible
outside the sandbox, and verifiably revoked on every terminal or uncertain
outcome. The cohort below forbids credentials entirely.

## Independent durable audit and outage semantics

The manifest **MUST** pin independent primary and emergency durable audit
channels. Both channels **MUST** be runtime-visible, tamper-evident,
monotonically sequenced, durably acknowledged, bounded in record size, and
covered by pinned retention and redaction policy.

A primary durable acknowledgement is required before any permit issuance and
again immediately before permit consumption. If the primary channel fails,
the runtime owner **MUST** deny or cancel and write only the bounded
denial/outage record to the emergency channel. It **MUST NOT** execute. An
outage probe passes only when that emergency record receives a durable
acknowledgement.

Audit qualification **MUST** use two separate runs and evidence sets:

1. The successful canary qualification run keeps the primary channel or the
   allowed emergency audit path available. It includes 100 valid calls and all
   adversarial probes except the destructive dual-outage probe. Exactly 100
   percent terminal runtime audit coverage is mandatory for this run.
2. The destructive dual-outage expected-failure run deliberately makes both
   channels unavailable. Its expected outcome is no permit, no execution, a
   runtime hard-stop, and qualification-run failure. Externally captured
   AgentHarness evidence may prove the hard stop, but it is not runtime audit
   and is excluded from the successful canary coverage denominator.

If both channels fail, the runtime owner **MUST** hard-stop, assert applicable
kill switches, cancel permits, revoke credentials, and fail that qualification
run. Both evidence sets are required for a future GO review. The destructive
run **MUST NOT** be called a successful canary or described as satisfying
runtime audit coverage.

Audit records **MUST NOT** contain raw arguments, secrets, credentials, human
approval payloads, unrestricted outputs, or unrestricted diagnostics. They may
contain only schema-bounded redacted fields, digests, and opaque references.
Oversize or nonconforming data **MUST** produce a bounded digest/reference or
deny; it **MUST NOT** be silently truncated.

Records **MUST** cover bounded decision and terminal facts, content and policy
digests, authenticity results, revocation observations, activation, service
attestations, sandbox and credential state, kill-switch observations, permit
transitions, outcome, and redaction. Gap, fork, tamper, truncation, ambiguity,
backpressure, or missing durable acknowledgement **MUST** deny.

## Measurable cohort `pi-hermetic-readonly-v1`

The cohort manifest ID **MUST** be `pi-hermetic-readonly-v1`. It contains
exactly one operation, `read_workspace_file_v1`, with exact JSON input:

```json
{ "path": "README.md" }
```

The normalized path **MUST** equal `README.md`. Alternate spellings, traversal,
links, extra fields, and other inputs **MUST** deny. The root and workspace are
immutable and must match every manifest and permit content binding. Writes,
network, subprocesses, devices, host namespaces, and credentials are forbidden.
The canary **MUST** prove credentials are unnecessary and prevented.

The exact per-call metrics are:

- 2 seconds wall time and 1 CPU second;
- 128 MiB memory, 16 PIDs, and 32 file descriptors;
- 1 MiB private empty tmpfs;
- 64 KiB total stdout/result; and
- zero stderr or diagnostic leakage.

The successful production-like canary qualification run **MUST** complete
exactly 100 valid calls and every non-dual-outage adversarial probe. Acceptance
requires zero unauthorized side effects, escapes, identity mismatches, content
substitutions, replays, audit gaps, or credential leaks, plus exactly 100
percent terminal runtime audit coverage within that run's denominator. The
separate destructive dual-outage expected-failure run is also required as
defined above. Any invariant failure aborts immediately. Limits may be
tightened only by a separately reviewed full manifest and **MUST NOT** be
loosened during a run.

## Required threat and failure probes

All probes are proposed, required before a future go decision, and currently
unimplemented:

- bootstrap substitution, threshold failure, protected-storage modification,
  unauthorized root rotation, controlled recovery, and recovery abuse;
- release and activation anti-downgrade, monotonic epoch persistence, old-state
  replay, unauthorized rollback, wrong predecessor, and authorized rollback;
- stale, forged, mismatched, cross-session, and replayed evidence;
- cross-role signing, wrong-purpose key, confused-deputy issuer use, issuer
  substitution (`issuer-substitution`), unknown issuer, and self-declared
  issuer acceptance; approval-versus-activation revocation-response
  substitution; primary-versus-emergency audit-acknowledgement substitution;
  global-versus-session kill-switch observation substitution; and every
  type, authority-domain, issuer, key, and purpose mismatch;
- human presence spoofing, ceremony or presentation mutation, weak
  authentication, missing explicit confirm, digest-only approval, incomplete
  argument projection, projection-schema omission or misclassification,
  unknown or extra argument fields, display truncation or redaction, and every
  mandatory role collision;
- approval mutation, expiry, revocation race, outage, ambiguous state,
  duplicate nonce, self-approval, and policy override;
- activation expiry, mismatch, duplicate record or nonce, revocation outage,
  stale response, ambiguity, and composition-to-consumption revocation race;
- permit forgery, wrong key or activation epoch, duplicate nonce, cross-session
  collision, double consumption, replay, post-consume crash,
  post-consumption/pre-launch revocation, and in-flight revocation races;
- root filesystem, workspace snapshot, content snapshot, `README.md` type,
  mode, content, link, and expected-output type or digest substitution;
- exact service identity, protocol/schema, trust epoch, deployment/config
  digest, compatibility, trusted-clock pinning, and attestation substitution;
- exhaustive manifest omission, duplicate or unlisted gate, drift, component
  substitution, incompatibility, downgrade, and partial rollback;
- kill-switch assertion races and stale, unreachable, or ambiguous state;
- primary audit outage with emergency durable denial, and dual outage with
  runtime hard-stop and qualification failure;
- audit gap, fork, tamper, truncation, backpressure, raw-data leakage, and lost
  durable acknowledgement;
- sandbox setup and resource failures plus namespace, device, syscall,
  filesystem, subprocess, host-handle, and credential escape;
- concurrent independent calls, cross-session ID collisions, duplicate approval
  and permit nonces, shared-state contamination, and shared-state isolation;
- direct executor, hook, adapter, child, shared-state, and Win9 boundary bypass;
  and
- every exact cohort operation, quota, canary, output, and audit metric.

Every non-dual-outage probe **MUST** demonstrate deny or bounded termination,
correct runtime audit outcome under the channel rules, credential revocation,
no unauthorized side effect, and no permit reuse. The destructive dual-outage
probe **MUST** instead demonstrate the expected hard stop through externally
captured AgentHarness evidence, with no claim of runtime audit coverage.
Concurrency probes **MUST** also prove independent state, nonce namespaces,
audit sequences, sandbox instances, and cancellation.

## Go/no-go checklist

Every item is initially unchecked. The aggregate decision remains NO-GO until
all evidence is independently reviewed and a separate milestone is approved.

- [ ] Independently provisioned bootstrap trust, threshold authorization,
  protected storage, rotation, recovery, and fail-closed tests pass.
- [ ] Monotonic activation epochs and anti-downgrade, predecessor-only rollback,
  threshold rollback authorization, and replay prevention pass.
- [ ] Atomic manifest omission, duplication, pinning, compatibility,
  attestation, drift, substitution, and partial rollback tests pass.
- [ ] Envelope issuer matrix pins exact types, authority domains, identities,
  keys, epochs, purposes, and roles; cross-role, cross-domain, wrong-purpose,
  confused-deputy, unknown-issuer, and issuer substitution tests deny.
- [ ] Approval-versus-activation revocation-response,
  primary-versus-emergency audit-acknowledgement, and global-versus-session
  kill-switch observation substitution tests deny.
- [ ] Exact service, protocol/schema, trust epoch, deployment/configuration,
  compatibility, authenticity-verifier, and trusted-clock pins pass.
- [ ] Human authentication, presence, intentional ceremony, canonical bounded
  presentation, exhaustive presentation-schema classification, complete
  execution-affecting argument display, schema and projection digest binding,
  explicit confirmation, and mandatory role disjointness pass.
- [ ] Projection-schema omission, field misclassification, and unknown, extra,
  omitted, or unclassified input and derived-value tests deny.
- [ ] Approval and activation revocation freshness, outage, ambiguity, race,
  cancellation, and immediate pre-consumption checks pass.
- [ ] Permit tagged approval union, activation ID/digest, activation epoch,
  content digests, uniqueness, atomic consumption/launch lease, and replay
  tests pass.
- [ ] Post-consumption/pre-launch and in-flight revocation races prevent launch
  or terminate within the pinned bound, preserve terminal permit state, and
  audit the terminal outcome.
- [ ] Root filesystem, workspace, content snapshot, `README.md`
  type/mode/content, and expected-output substitution tests pass.
- [ ] OS sandbox, exact quotas, pre-return output checks, and all escape probes
  pass with zero unauthorized side effects.
- [ ] Primary audit durable acknowledgements and primary-outage emergency denial
  records pass in the successful canary qualification run.
- [ ] The successful canary has exactly 100 valid calls, every non-dual-outage
  adversarial probe, and exactly 100 percent terminal runtime audit coverage.
- [ ] The separate destructive dual-outage run has no permit or execution,
  hard-stops, fails qualification, and has external AgentHarness evidence that
  is excluded from the successful canary audit denominator.
- [ ] Audit sequence, tamper, bounded redaction, retention, and outage
  requirements pass under their applicable run rules.
- [ ] Concurrent calls, cross-session collisions, duplicate nonces, and
  shared-state isolation pass.
- [ ] Both required evidence sets meet their distinct acceptance semantics and
  are independently reviewed without treating dual outage as audit success.
- [ ] Independent security and operations reviewers approve reproducible
  evidence, immutable digests, audit samples, rotation, recovery, and rollback.
- [ ] A separately scoped implementation milestone receives explicit approval.

Documentation assertions alone are insufficient evidence.

## Rollback requalification

Before any rolled-back predecessor can be reactivated at its new higher
activation epoch, the runtime owner **MUST** complete:

- full current manifest and bootstrap-compatibility validation;
- rollback-specific regression tests, including epoch and replay tests;
- every adversarial probe implicated by the rollback cause or changed state;
- block-only shadow verification with no real execution; and
- renewed, independent security and operations approval.

Completion of an earlier qualification run or possession of an old activation
record **MUST NOT** satisfy requalification.

## Stop conditions and non-goals

Any failed invariant is a stop condition. The runtime owner **MUST** set
`execution_enablement=false`, assert applicable kill switches, cancel permits,
terminate sandboxes, revoke credentials, and apply the audit outage rules.
Execution may resume only after correction, full required requalification, and
a new separately approved activation record at a higher activation epoch.

T060 provides no implementation code or runtime allow. AgentHarness implements
none of this ADR and remains evidence-only. It adds no bootstrap trust root,
signing authority, verifier, authorization, activation, permit, sandbox,
credential, audit, kill-switch, or execution logic. It does not modify Pi,
enable a cohort, or validate production safety.

The current bridge continues to return `result_status: not_executed` and
performs no real tool execution. Until a future runtime owner implements and
verifies every gate, the decision remains **NO-GO for real execution** and the
implementation status remains **NOT IMPLEMENTED**.
