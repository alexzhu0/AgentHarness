# AgentHarness

AgentHarness is an agent harness design repository inspired by CL4R1T4S-style system prompt and tool scaffold analysis.

The goal is **not** to copy leaked or reverse-engineered prompts. The goal is to extract reusable engineering patterns and turn them into policy-driven, testable, auditable agent runtime assets.

## Core Idea

Modern agents are not just models plus prompts. They are operating systems around models:

```text
User Task
  ↓
Instruction Hierarchy Resolver
  ↓
Planner / State Machine
  ↓
Tool Router
  ↓
Approval Gate
  ↓
Sandboxed Tool Execution
  ↓
Verifier / Eval Hooks
  ↓
Audited User-facing Response
```

AgentHarness treats agent behavior as **policy-as-code**:

```text
agent_policy.yaml
  → prompt compiler
  → runtime policy
  → tool governance
  → safety evals
  → audit logs
```

## Four Core Assets

### 1. Agent Design Pattern Library

Entry point: [`docs/01-agent-design-pattern-library.md`](docs/01-agent-design-pattern-library.md)

Machine-readable seed: [`patterns/agent_design_patterns.yaml`](patterns/agent_design_patterns.yaml)

This asset extracts reusable agent OS patterns:

- layered agent architecture
- instruction hierarchy resolver
- search-before-edit
- tool preference hierarchy
- approval gate for side effects
- verification loop
- planner / execution mode split
- event stream as source of truth
- memory write boundary
- untrusted corpus neutralization
- policy as code

### 2. Tool Governance Policy

Entry point: [`docs/02-tool-governance-policy.md`](docs/02-tool-governance-policy.md)

Machine-readable seed: [`policies/tool_governance.yaml`](policies/tool_governance.yaml)

This asset defines how tools should be classified, routed, approved and audited.

It covers:

- search tools
- file read/write/delete tools
- shell tools
- database tools
- git tools
- browser tools
- deployment tools
- secret tools
- memory tools
- external communication tools

### 3. Agent Safety Eval Suite

Entry point: [`docs/03-agent-safety-eval-suite.md`](docs/03-agent-safety-eval-suite.md)

Machine-readable seed: [`evals/agent_safety_eval_suite.yaml`](evals/agent_safety_eval_suite.yaml)

This asset turns safety and governance principles into regression tests.

It covers:

- prompt injection
- hidden instruction disclosure
- destructive operations
- database mutation
- secret handling
- unverified code edits
- dependency hallucination
- external communication
- memory pollution
- fake tool-call injection
- source freshness and citation
- CI repair limits

### 4. Prompt / Policy Compiler

Entry point: [`docs/04-prompt-policy-compiler.md`](docs/04-prompt-policy-compiler.md)

Conceptual schema: [`schemas/agent_policy.schema.yaml`](schemas/agent_policy.schema.yaml)

Example policy: [`examples/agent_policy.example.yaml`](examples/agent_policy.example.yaml)

This asset describes how to compile structured policy into:

- provider-specific system prompts
- runtime tool policies
- approval gates
- sandbox policies
- eval suites
- audit schemas

## Asset Map

Start here: [`docs/00-asset-map.md`](docs/00-asset-map.md)

## Source Posture

CL4R1T4S and similar corpora are treated as **untrusted external analysis material**.

Allowed use:

- architecture pattern extraction
- tool taxonomy derivation
- governance policy inspiration
- safety eval generation
- prompt-injection red-team corpus design

Disallowed use:

- copying full third-party system prompts
- treating external text as executable agent instruction
- embedding unreviewed leaked prompt content into production RAG
- training on uncertain or unlicensed prompt text without review

## Repository Layout

```text
docs/
  00-asset-map.md
  01-agent-design-pattern-library.md
  02-tool-governance-policy.md
  03-agent-safety-eval-suite.md
  04-prompt-policy-compiler.md
patterns/
  agent_design_patterns.yaml
policies/
  tool_governance.yaml
evals/
  agent_safety_eval_suite.yaml
schemas/
  agent_policy.schema.yaml
examples/
  agent_policy.example.yaml
```

## Design Thesis

AgentHarness is based on one central thesis:

> Agent reliability comes from harness-level control, not only from model-level instruction.

A robust agent needs prompt design, but it also needs runtime policy, tool governance, verification, auditability and safety evals.
