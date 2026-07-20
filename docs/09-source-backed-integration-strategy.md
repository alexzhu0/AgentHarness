# AgentHarness Source-Backed Integration Strategy

last checked date: 2026-06-24

AgentHarness is a pre-execution evidence control-plane for agent actions.

## Normative vocabulary and product contract

This strategy uses [`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md) as the normative vocabulary and product contract. Terms such as control-plane, audit-plane, execution-plane, runtime boundary, eligibility, evidence, handoff, export package, digest manifest, manifest verification, external consumer, and `result_status: not_executed` should keep the meanings defined there.

## Integration invariant

- AgentHarness validates and exports evidence only.
- Runtimes, governance systems, auth systems, identity systems, sandbox systems, signing systems, trust-root systems, and execution-plane systems are external consumers, not AgentHarness in-repo responsibilities.
- Current handoff/export/manifest/verification outputs remain `result_status: not_executed`.
- Integration work must preserve the current evidence chain: file-bus → tool gate → approval → preflight → handoff → adapter registry → export package → digest manifest → manifest verification.

## Source inventory matrix

| Source | Source link | Source-backed role | What AgentHarness may export to it | What AgentHarness must not own or build | Maturity recommendation | Boundary rationale |
| --- | --- | --- | --- | --- | --- | --- |
| LangGraph | https://docs.langchain.com/oss/python/langgraph/overview | Runtime/orchestration consumer for long-running, stateful agents with durable execution, streaming, human-in-the-loop, memory, and persistence. | Verified export package and digest manifest proving which handoff-ready requests passed AgentHarness evidence checks. | LangGraph graphs, nodes, state machines, runtime invocation, deployment, persistence, streaming, or human-in-the-loop mutation. | integrate later | LangGraph owns orchestration/runtime execution; AgentHarness should only provide pre-execution evidence that a LangGraph owner may inspect under its own controls. |
| OpenAI Agents SDK | https://developers.openai.com/api/docs/guides/agents | Code-first agent application SDK where the application owns orchestration, tool execution, approvals, state, guardrails/human review, and observability. | Registry-backed handoff export items, manifest digest/readback status, request ids, adapter refs, and evidence summaries. | SDK adoption, package installation, agent run loops, tool execution, approvals runtime, sandbox agents, tracing implementation, or framework-specific adapter code. | integrate later | The SDK is an external runtime/application surface; AgentHarness can inform an application owner before execution but must not become that runtime. |
| CrewAI | https://docs.crewai.com/ | Multi-agent crew/flow orchestration consumer with agents, crews, flows, guardrails, memory, knowledge, observability, persistence, and resumable workflow concepts. | Evidence eligibility summaries and verified manifests that a CrewAI workflow owner could read before invoking a crew or flow action. | Crew definitions, flow orchestration, task/process execution, memory/knowledge stores, enterprise console operations, triggers, or integration tools. | integrate later | CrewAI owns collaborative agent/flow execution; AgentHarness remains a control-plane evidence producer. |
| AutoGen / Microsoft Agent Framework | https://github.com/microsoft/autogen, https://learn.microsoft.com/en-us/agent-framework/overview/, https://github.com/microsoft/agent-framework | AutoGen is maintenance/migration context; Microsoft Agent Framework is the newer production multi-agent/workflow runtime direction with agents, tools/MCP, workflows, checkpointing, state, middleware, telemetry, and human-in-the-loop support. | Export package and digest manifest metadata that a Microsoft Agent Framework owner may map into middleware or workflow preconditions later. | AutoGen/MAF package adoption, agent/workflow implementation, tools/MCP clients, checkpointing, middleware, telemetry, state management, or migration tooling. | integrate later | Microsoft Agent Framework owns runtime orchestration and application execution; AgentHarness should not wrap or reimplement it in T016. |
| Microsoft Agent Governance Toolkit | https://microsoft.github.io/agent-governance-toolkit/, https://github.com/microsoft/agent-governance-toolkit | Runtime governance middleware candidate for policy enforcement, identity, audit logging, denial handling, sandboxing, reliability/SRE, compliance, and framework integrations. | Evidence chain records, request digests, approval/preflight/handoff readiness, and manifest verification results as governance decision evidence. | AGT package adoption, policy engine replacement, identity, sandboxing, kill switch, framework adapters, compliance engine, or governance wrapper implementation. | integrate later | AGT is runtime governance middleware; AgentHarness should provide pre-execution evidence but not become the middleware. |
| Open Agent Auth | https://github.com/alibaba/open-agent-auth | External auth/identity system focused on cryptographic identity binding, fine-grained authorization, request-level isolation, semantic audit trails, standards integration, and MCP-aware authorization. | Request digest evidence, approval binding context, handoff metadata, and manifest readback results for possible authorization/audit correlation. | Authorization server, identity provider, token issuance, cryptographic binding, request isolation, policy registration, semantic audit infrastructure, or MCP adapter implementation. | integrate later | Open Agent Auth owns identity and authorization; AgentHarness may supply evidence inputs but must not act as auth gateway or identity system. |
| MCP Authorization | https://modelcontextprotocol.io/specification/draft/basic/authorization, https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization | External protocol boundary for HTTP-based MCP authorization using OAuth-style client/resource-server/authorization-server roles and protected resource metadata. | Bus-relative export and manifest evidence that an MCP client/server owner may consider before protected operations. | MCP server/client implementation, authorization server discovery, client registration, OAuth flow, scope challenge handling, token handling, or transport security. | never in AgentHarness | MCP Authorization is a protocol/auth transport concern; AgentHarness is not an MCP authorization implementation. |
| deferred future execution-plane candidate | N/A by design; internal boundary anchor: [`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md). No external source, repo dependency, import, test, or call is introduced in T016. | Deferred execution-plane consumer that may someday read registry-backed handoff exports after a separate approved plan. | Stable export package, digest manifest, manifest verification report, adapter registry/spec/ref metadata, and `result_status: not_executed` evidence. | Any concrete execution-plane repository modification, import, dependency, test, call, adapter invocation, run/execute/dispatch/submit command, daemon, queue, scheduler, watcher, or realtime chat. | defer | The candidate is intentionally unnamed as an implementation dependency; T016 records only the future boundary shape. |

## Runtime/orchestration consumers

LangGraph, OpenAI Agents SDK, CrewAI, and AutoGen / Microsoft Agent Framework are runtime/orchestration consumers. Source-backed facts place them in the execution or application layer: they own agent graphs, workflows, tools, run loops, state, streaming, persistence, middleware, human-in-the-loop controls, and production deployment choices.

AgentHarness may later provide those owners with a ready-only export package and digest manifest. The runtime owner decides whether, when, and how to execute. AgentHarness must not import these frameworks, install packages, instantiate agents, run graphs, call tools, manage runtime state, or mutate task lifecycle through public execution commands.

## Governance middleware consumers

Microsoft Agent Governance Toolkit is a governance middleware consumer. Its source material positions it around policy enforcement, identity, sandboxing, audit/compliance, SRE/reliability, and framework integrations.

AgentHarness may later provide AGT-like middleware owners with evidence records: tool-gate decisions, approval bindings, preflight status, handoff readiness, adapter registry pins, export package digests, and manifest verification outcomes. AgentHarness must not adopt AGT, replace its policy engine, wrap tools with AGT code, provide sandboxing, become a kill switch, or implement runtime governance.

## Auth/identity/protocol consumers

Open Agent Auth and MCP Authorization are auth/identity/protocol consumers. Open Agent Auth focuses on identity binding, fine-grained authorization, request isolation, semantic audit, and standards integration. MCP Authorization defines an external protocol boundary for HTTP-based MCP authorization using OAuth-style roles and metadata.

AgentHarness may later expose request digests, approval evidence, and manifest readback status to an auth or protocol owner. AgentHarness must not issue tokens, host authorization servers, implement identity providers, perform OAuth/MCP flows, manage scopes, create cryptographic credentials, or act as an auth gateway.

## Deferred future execution-plane candidate

A future execution-plane candidate remains deferred. T016 does not name a concrete repository, dependency, package, import, test, call, or adapter invocation. Any future spike must preserve the T015 product contract, keep adapter references as versioned evidence bindings, and start from registry-backed handoff exports plus manifest verification.

Until separately planned and accepted, this candidate is an external consumer placeholder only.
A later contract-first Pi boundary note is captured in [`docs/17-pi-integration-boundary-and-contract.md`](./17-pi-integration-boundary-and-contract.md); it remains conceptual and does not modify or depend on Pi.

## Build / Buy / Integrate / Defer rules

### Build

Build in AgentHarness:

- evidence envelope/export/manifest/verification wording and examples after docs acceptance;
- adapter registry/spec/ref evidence bindings;
- glossary/product contract language;
- source-backed integration map;
- deterministic readback and verification surfaces that keep `result_status: not_executed`.

### Buy

Buy or adopt outside AgentHarness:

- runtime orchestration;
- runtime policy enforcement;
- identity/authZ;
- sandboxing;
- signing/trust roots;
- production hosting, telemetry, and operations.

### Integrate

Integrate later by allowing external owners to read:

- verified manifest/export package readback;
- governance decision evidence;
- auth/request digest evidence;
- adapter registry/spec/ref provenance;
- MCP authorization context as an external boundary, not an in-repo implementation.

### Defer

Defer:

- executable adapter implementation;
- daemon, queue, scheduler, watcher, or realtime chat;
- runtime submit/run/execute/dispatch commands;
- task-mutation CLI;
- lifecycle state expansion;
- framework-specific wrappers.

## Not an adoption decision

This document is not an adoption decision.

T016 adds no SDK/package, makes no dependency recommendation, implements no wrapper, adds no AGT/Open Agent Auth/MCP server implementation, and creates no framework-specific runtime adapter. It is a source-backed integration map for external consumers and deferred boundaries only.

## Future integration readiness checklist

Before any future integration task starts, confirm:

- [`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md) is cited and still accepted.
- The evidence package shape is accepted.
- The handoff is registry-backed with explicit adapter spec/ref provenance.
- Current outputs remain `result_status: not_executed`.
- No source, schema, CLI, dependency, or fixture changes are introduced unless separately planned and accepted.
- External owner boundaries are named for runtime, governance, auth, identity, protocol, sandbox, signing, trust-root, and execution-plane responsibilities.
- No future execution-plane repository is modified, imported, depended on, tested, or called.

## T017+ follow-up suggestions

- T017: enterprise audit report examples and buyer-demo narrative:
  [`docs/10-enterprise-audit-report-and-buyer-demo.md`](./10-enterprise-audit-report-and-buyer-demo.md).
- T018 machine-readable enterprise audit report composes existing inspect/export/manifest evidence into stdout-only JSON; later formal schema work remains deferred until that shape is accepted.
- Later evidence-envelope schema only after docs are accepted.
- Runtime spike remains deferred until the product contract, source-backed integration map, buyer-demo narrative, and external owner responsibilities are accepted.
