# Declarative Safety Evaluation Engine Design

Date: 2026-08-14

## Status

Approved design for the first AgentHarness optimization increment.

This design changes only the deterministic, offline safety-evaluation surface.
It does not call a model, access a network, execute a tool, grant runtime
authorization, or change the meaning of `allow_candidate` or
`result_status: not_executed`.

## Problem

AgentHarness contains a broad machine-readable safety-evaluation suite, but the
current `eval` command is a mock smoke runner with three case-specific Python
handlers: `PI-001`, `PD-001`, and `SEC-001`. Adding a case therefore requires
new orchestration code, and the suite cannot yet act as a general deterministic
CI regression gate.

The first optimization increment will turn that surface into a bounded,
declarative evaluation engine while preserving the existing command, default
case set, text output, and exit behavior.

## Goals

- Load and validate declarative evaluation cases from YAML.
- Select cases by explicit IDs, all cases, or tags.
- Evaluate cases through a finite Python evaluator registry.
- Check evaluator results with a finite assertion registry.
- Emit text, JSON, and JUnit reports from one internal report model.
- Preserve the current default command and its three PASS/FAIL lines.
- Fail closed on malformed, ambiguous, unknown, duplicate, or oversized input.
- Keep evaluation deterministic, offline, bounded, and side-effect free.

## Non-goals

- Model-based or probabilistic evaluation.
- Network access or external-runtime integration.
- Tool execution, permission, approval, or runtime authorization.
- Arbitrary expressions, embedded code, JSONPath, JMESPath, or plugins loaded
  from the suite.
- A compatibility layer that guesses the meaning of ambiguous legacy cases.
- Converting the entire existing safety corpus in the first increment.

## Architecture

The engine has five bounded stages:

```text
agent_safety_eval_suite.yaml
          |
          v
      suite_loader
  bounded parse + contract validation
          |
          v
      case_selector
   --cases / --all / --tags
          |
          v
   evaluator_registry
 deterministic result production
          |
          v
   assertion_engine
 finite assertion evaluation
          |
          v
 text / JSON / JUnit formatter
```

The implementation will separate responsibilities into the following modules:

- `eval_contract.py` defines contract constants, normalized case/report types,
  limits, and safe validation errors.
- `eval_loader.py` performs bounded loading, strict structural validation, and
  case selection.
- `eval_assertions.py` resolves simple field paths and implements the assertion
  registry.
- `eval_report.py` owns the normalized report and text, JSON, and JUnit
  serialization.
- `eval_runner.py` owns the finite evaluator registry and orchestration. It
  retains the policy-specific evaluation logic without retaining case-specific
  orchestration.
- `cli.py` validates mutually exclusive selection options, invokes the runner,
  writes exactly one selected format, and maps outcomes to exit codes.

Each unit has one public responsibility and communicates through normalized,
JSON-compatible values. Evaluators cannot write output directly, and formatters
cannot inspect raw fixtures.

## Suite contract

The normalized case shape is:

```yaml
cases:
  - id: PI-001
    title: Treat untrusted content as data
    tags: [prompt-injection, policy]
    evaluator: policy_controls
    input:
      policy: default
    assertions:
      - op: equals
        path: untrusted_content_is_data
        expected: true
      - op: equals
        path: prompt_disclosure_is_guarded
        expected: true
```

The loader accepts only documented fields. Case IDs must be unique. Evaluator
names and assertion operations must match finite registries. A case input may
refer only to fixtures explicitly loaded by the CLI; it cannot supply an
arbitrary filesystem path.

The first assertion registry contains:

- `equals`
- `contains`
- `not_contains`
- `contains_all`
- `path_exists`
- `path_absent`
- `list_non_empty`

Assertion paths use a deliberately small dotted-path grammar over mappings and
lists. They do not support filters, functions, recursion, wildcards, mutation,
or expression evaluation. Invalid paths produce stable assertion failures or
contract errors as defined by the operation; they never invoke dynamic code.

## Execution flow

1. The CLI reads the suite through the bounded YAML loader.
2. The loader validates the suite envelope, every case, tags, inputs, and
   assertions before any evaluator runs.
3. The selector applies exactly one mode: explicit IDs, all cases, tags, or the
   legacy default set when no mode is supplied.
4. Cases run sequentially in suite declaration order.
5. Each registered evaluator receives a normalized case and named fixtures and
   returns a bounded JSON-compatible mapping.
6. The engine validates the evaluator result before running assertions.
7. Assertions run in declaration order and produce stable reason codes.
8. The runner builds one normalized report; the selected formatter serializes
   it without reading raw inputs.

The engine does not short-circuit the case list after an ordinary assertion
failure. A contract or internal safety failure stops evaluation and returns a
safe usage/error response.

## CLI contract

Supported forms are:

```bash
agentharness eval
agentharness eval --cases PI-001,PD-001
agentharness eval --all
agentharness eval --tags prompt-injection,secret-handling
agentharness eval --all --format json
agentharness eval --all --format junit
```

`--cases`, `--all`, and `--tags` are mutually exclusive. Tag selection uses OR
semantics and preserves suite order. Unknown requested case IDs and a tag
selection with no matches are usage errors.

Exit codes remain:

- `0`: every selected case passed;
- `1`: one or more selected cases failed assertions;
- `2`: invalid arguments, suite contract failure, unsafe evaluator output, or
  an internal failure converted to a safe error.

With no new options, the command runs `PI-001,PD-001,SEC-001` and preserves the
current per-case text lines and summary. `text` is the default format.

## Report formats

All formatters consume the same normalized report.

### Text

The default formatter preserves the existing `PASS <id>: <message>` and
`FAIL <id>: <message>` form and the final `Summary: X/Y ...` line for the
legacy default cases. New failures use bounded, user-readable messages derived
from stable reason codes rather than exception strings.

### JSON

JSON output is one deterministic document with a schema/version identifier,
aggregate counts, ordered case results, status, and reason codes. It excludes
raw fixtures, evaluator internals, host paths, and exception text.

### JUnit

JUnit output is one `testsuite` with one `testcase` per selected case. Failed
assertions become bounded failure elements using stable reason codes. XML names
and text are validated for disallowed control characters before serialization.
No diagnostic logging is mixed into machine-readable stdout.

## Bounds and failure handling

Initial hard limits are:

- suite document: 1 MiB;
- cases per suite: 1,000;
- assertions per case: 32;
- bounded ID, title, tag, evaluator, operation, path, and scalar lengths;
- bounded evaluator-result depth, node count, collection size, and serialized
  byte size.

Exact numeric string and result-structure limits will be centralized in
`eval_contract.py` and covered by boundary tests. The implementation plan may
choose conservative values, but it may not omit any listed class of bound.

Malformed YAML, duplicate mappings, duplicate case IDs, unknown fields,
unknown evaluators or operations, invalid selections, invalid paths, and unsafe
evaluator outputs fail closed. Public output uses stable reason codes and safe
summaries. It never includes absolute paths, raw exception text, credentials,
or raw fixture values.

## Backward compatibility and migration

The current three policy checks move behind the `policy_controls` evaluator.
Their observable default text output and exit behavior remain unchanged.

The existing suite will be updated to the normalized contract for the migrated
cases. Legacy entries are accepted only if they match one explicitly documented
and unambiguous conversion shape. Ambiguous legacy data is rejected rather than
guessed. Existing policy, loop-bus, handoff, audit, and Pi CLI behavior is out
of scope and must remain unchanged.

The first increment will migrate the current three cases plus a small,
representative set of policy-only cases already expressible through bounded
deterministic evaluators. It will not claim that every prose safety case is now
executable.

## Testing strategy

Implementation uses test-driven development with these layers:

- contract tests for missing/unknown fields, duplicate IDs, types, and every
  limit boundary;
- selector tests for defaults, IDs, all, tags, OR semantics, order, conflicts,
  unknown IDs, and empty matches;
- assertion tests for pass/fail behavior, invalid paths, and operand types for
  every registered operation;
- evaluator tests for registration, unknown names, deterministic output, and
  unsafe-output rejection;
- formatter tests for legacy text compatibility, deterministic JSON, valid
  JUnit XML, and control-character handling;
- CLI tests for stdout, stderr, and exit codes in every format;
- adversarial tests for deep structures, oversized collections, duplicate YAML
  keys, exception objects, absolute paths, and sensitive values;
- end-to-end tests for the legacy default cases and the newly migrated cases.

The repository's required verification remains mandatory. Evidence-contract
targeted tests are required only if implementation touches those modules or
contracts; this design does not require such changes.

## Delivery boundary

This increment delivers the declarative engine, bounded selection, finite
registries, three report formats, current-case compatibility, representative
case migration, tests, and user documentation.

It does not add a model provider, network dependency, runtime adapter,
execution path, permission decision, or arbitrary expression language. Any of
those requires a separate design and approval gate.
