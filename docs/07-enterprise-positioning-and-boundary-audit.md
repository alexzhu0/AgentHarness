# Enterprise Positioning and Boundary Audit

last checked date: 2026-06-22

AgentHarness is a pre-execution evidence control-plane for agent actions.

## Plain enterprise explanation

AgentHarness answers an enterprise platform/security question before an agent runtime executes a tool: does this proposed action have enough deterministic evidence to be eligible for a future execution boundary?

It is a pre-runtime control-plane and audit-plane. It turns policy, ledger state, tool-gate decisions, approval records, preflight checks, handoff readiness, registry pinning, export packages, digest manifests, and manifest verification into reviewable artifacts. Those artifacts can be consumed by a runtime later, but the current project does not run tools, call runtime adapters, mutate task state through public execution commands, or act as an authorization gateway.

Current evidence chain:

```text
file-bus → tool gate → approval → preflight → handoff → adapter registry → export package → digest manifest → manifest verification
```

All current handoff, export, manifest, and manifest-verification outputs remain `result_status: not_executed`.

## Category boundary

AgentHarness sits before runtime execution. Its category is closer to a deterministic evidence control-plane than to a general agent framework. It is meant to complement agent runtimes, runtime governance middleware, authorization protocols, identity systems, sandboxes, and future execution-plane adapters.

It should help enterprise teams answer:

- What did the agent request?
- Which policy and ledger facts were used?
- Was user approval required, present, and bound to the same request?
- Was the handoff backed by an exact adapter registry entry?
- Which ready items were exported, and which blocked or unsupported requests were excluded?
- Can a saved manifest be regenerated and compared byte-stably against current bus state?

## Scope invariant

AgentHarness validates and exports evidence only; runtimes, governance systems, auth systems, identity systems, sandboxes, and execution planes are external consumers, not AgentHarness in-repo responsibilities.

## Enterprise operating model

platform/security/compliance reviewers own evidence review and policy acceptance. Downstream runtime owners own actual execution, runtime enforcement, identity, authorization, and operational controls.

## Adjacent-project matrix

this is an adjacent-category comparison, not a feature-parity table

| Adjacent project | What it is for | Boundary with AgentHarness | Source |
| --- | --- | --- | --- |
| LangGraph | Runtime orchestration for long-running, stateful agents with durable execution, persistence, streaming, and human-in-the-loop workflows. | AgentHarness does not orchestrate agent execution. It can produce pre-execution evidence that a LangGraph-style runtime could inspect before running a tool. | [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) |
| OpenAI Agents SDK | Agent application/runtime layer for agent orchestration, tools, handoffs, guardrails, tracing, and server-side agent execution patterns. | AgentHarness does not replace an Agents SDK runtime. It provides deterministic eligibility evidence and manifest readback before a runtime executes actions. | [Agents SDK guide](https://developers.openai.com/api/docs/guides/agents), [tracing docs](https://github.com/openai/openai-agents-python/blob/main/docs/tracing.md) |
| CrewAI | Framework for collaborative agents, crews, flows, guardrails, memory/knowledge, observability, and resumable workflows. | AgentHarness does not define agent teams or flows. It can export ready-only evidence packages for a separate workflow engine to consume later. | [CrewAI docs](https://docs.crewai.com/) |
| AutoGen / Microsoft Agent Framework direction | Agent/application framework lineage for building multi-agent systems; the AutoGen repository points new users toward Microsoft Agent Framework direction while retaining maintenance context. | AgentHarness does not build a multi-agent app framework. It defines pre-execution evidence and adapter-registry boundaries that can sit before such frameworks. | [AutoGen repository](https://github.com/microsoft/autogen) |
| Microsoft Agent Governance Toolkit | Runtime governance layer for policy enforcement, identity, audit logging, denial handling, sandboxing, SRE, compliance, and framework integrations. | AgentHarness currently stops before runtime governance wrappers and execution. AGT is a future integration candidate, not a dependency in T014. | [AGT docs](https://microsoft.github.io/agent-governance-toolkit/), [AGT GitHub](https://github.com/microsoft/agent-governance-toolkit), [Microsoft Open Source Blog](https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/) |
| Open Agent Auth | Enterprise authorization framework focused on cryptographic identity binding, fine-grained authorization, request-level isolation, semantic audit trails, and standards integration for agent operations. | AgentHarness does not implement identity or authorization protocols. It can preserve request evidence that an auth layer may later use as input. | [Open Agent Auth GitHub](https://github.com/alibaba/open-agent-auth) |
| MCP Authorization | Model Context Protocol authorization specification for OAuth-style client/resource/server authorization boundaries. | AgentHarness does not implement MCP transport authorization. It validates evidence-chain eligibility before any downstream MCP client/server action would be considered. | [MCP Authorization draft](https://modelcontextprotocol.io/specification/draft/basic/authorization) |

## What AgentHarness owns

- Deterministic, file-based pre-execution evidence artifacts.
- Policy-to-evidence checks that stay side-effect-free.
- Ledger-referenced validation over tool gate, approval, preflight, handoff, adapter registry, export package, digest manifest, and manifest verification records.
- Fail-closed exclusion of blocked or unsupported handoffs from export surfaces.
- Canonical JSON digest semantics for export package and manifest readback.
- Bus-relative, stdout-only report surfaces for current handoff/export/manifest commands.
- The invariant that current control-plane artifacts report `result_status: not_executed`.

## What AgentHarness integrates

- Runtime/orchestration frameworks, including LangGraph, OpenAI Agents SDK, CrewAI, and the AutoGen / Microsoft Agent Framework direction, through future explicit adapter or consumer boundaries.
- Runtime governance middleware such as Microsoft Agent Governance Toolkit, after AgentHarness evidence contracts are stable enough to map into a governance layer.
- Authorization and identity layers such as Open Agent Auth and MCP Authorization as separate systems that may consume or enrich evidence, not as code copied into AgentHarness.
- Future execution-plane projects through explicit versioned adapter specs, registry pins, and digest checks rather than implicit imports or live discovery.

## What AgentHarness does not build now

- Agent runtime orchestration, crew/graph scheduling, daemon loops, watchers, or realtime chat.
- Runtime adapter invocation or real tool execution.
- Public run, execute, dispatch, submit, or task-mutation CLI surfaces.
- OAuth servers, identity providers, MCP authorization gateways, or cryptographic agent identity systems.
- Sandboxing, signing, private-key/public-key infrastructure, certificates, timestamps, attestations, or trust roots.
- Lifecycle status expansion beyond the existing protocol boundary.
- A replacement for LangGraph, OpenAI Agents SDK, CrewAI, AutoGen / Microsoft Agent Framework direction, Microsoft Agent Governance Toolkit, Open Agent Auth, MCP Authorization, or downstream runtime projects.

## Build / buy / integrate guidance

- **Build in AgentHarness:** deterministic file-bus validation, evidence records, tool-gate decision replay, approval binding, preflight eligibility, handoff readiness, adapter registry validation, ready-only export packages, digest-addressed manifests, and manifest readback.
- **Buy or adopt outside AgentHarness:** production runtime orchestration, hosted agent services, runtime governance wrappers, authorization gateways, identity infrastructure, sandboxing, signing, and trust-root systems.
- **Integrate later:** connect the AgentHarness evidence contract to selected runtime, governance, auth, or execution-plane systems through explicit adapter specs and registry-backed consumer payloads.
- **Defer runtime spikes:** keep execution-plane experiments behind the current adapter boundary until the evidence contract, enterprise glossary, and integration criteria are accepted.

The accepted T015 glossary and product contract is
[`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md).
Future integration and buyer-demo work should cite that glossary before adding
new runtime-adjacent wording.

## T015+ recommended next task options

- **T015:** accepted docs-backed glossary/ontology and product contract:
  [`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md).
- **T016:** source-backed integration strategy for downstream runtime, governance, authorization, and identity layers.
- **T017:** enterprise audit report examples and buyer-demo narrative showing how a security/platform reviewer reads the evidence chain.
- **Deferred:** runtime spike only after boundary acceptance and with explicit adapter contracts that preserve the no-execution default.

## Source links included

- https://microsoft.github.io/agent-governance-toolkit/
- https://github.com/microsoft/agent-governance-toolkit
- https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/
- https://github.com/alibaba/open-agent-auth
- https://docs.langchain.com/oss/python/langgraph/overview
- https://developers.openai.com/api/docs/guides/agents
- https://github.com/openai/openai-agents-python/blob/main/docs/tracing.md
- https://docs.crewai.com/
- https://github.com/microsoft/autogen
- https://modelcontextprotocol.io/specification/draft/basic/authorization

## T014 red lines

T014 is documentation-only except for navigation links. It does not add dependencies, source-code behavior, real tool execution, runtime adapter calls, daemon scheduling, realtime chat, task mutation commands, lifecycle states, signing, timestamping, attestations, or trust-root implementation.
