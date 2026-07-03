# AgentHarness 四类资产地图

## 背景

AgentHarness 的目标不是复制任何第三方 system prompt，而是把公开语料中的 agent scaffold 设计沉淀为可复用的架构资产。CL4R1T4S 可以作为样本库，但必须按“不可信外部语料”处理。

本仓库当前沉淀四类核心资产：

1. **Agent Design Pattern Library**：抽象主流 agent 的架构模式。
2. **Tool Governance Policy**：定义工具调用、审批、拒绝、审计边界。
3. **Agent Safety Eval Suite**：把治理规则转成可回归测试的安全评测集。
4. **Prompt / Policy Compiler**：把结构化 agent policy 编译成 system prompt、runtime config、eval config。

此外，运行时架构视图在 [`docs/06-runtime-architecture.md`](./06-runtime-architecture.md)
中定义，用于说明 policy、file-bus ledger、approval boundary、execution boundary
和 verification layer 如何组合成 harness。

企业定位与边界审计在
[`docs/07-enterprise-positioning-and-boundary-audit.md`](./07-enterprise-positioning-and-boundary-audit.md)
中定义，用于明确 AgentHarness 当前是 pre-execution evidence control-plane，
不是 runtime/orchestration/auth/sandbox/signing 系统。

术语表与产品契约在
[`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md)
中定义，用于固定 T001-T014 之后的 canonical vocabulary、ontology 和 product contract。

Source-backed integration strategy 在
[`docs/09-source-backed-integration-strategy.md`](./09-source-backed-integration-strategy.md)
中定义，用于把 AgentHarness evidence artifacts 映射到未来 external runtime、governance、auth、identity、protocol 和 execution-plane consumers。

Enterprise audit report and buyer demo 在
[`docs/10-enterprise-audit-report-and-buyer-demo.md`](./10-enterprise-audit-report-and-buyer-demo.md)
中定义，用于展示 security/platform/compliance reviewer 如何读取 AgentHarness evidence chain、ready/blocked/unsupported 分类、manifest readback、T018 machine-readable audit report 和 T020 enterprise audit report schema，而不引入 runtime execution。
T021 增加 `./agentharness audit verify-report <bus_root> <audit_report_path>`，用于对保存的 audit report 做 readback verification；它只读取保存的 JSON 和当前 bus evidence，不执行 runtime adapter、不写文件、不签名、不提交任务。
T022 增加 `./agentharness audit checklist <bus_root>`，用于输出 reviewer-facing goal/check checklist；它只汇总现有 validation/inspection/export/manifest/audit evidence 和 manual readback steps，stdout-only、`result_status: not_executed`，不是 runtime、auth、sandbox、signing、trust-root、governance enforcement 或 task mutation。
T024 增加 [`schemas/enterprise_audit_checklist.schema.yaml`](../schemas/enterprise_audit_checklist.schema.yaml) 和 pure in-memory checklist validator，用于固定 accepted checklist payload contract；它不是 runtime authorization、execution、file writer、signing/trust bundle 或 governance enforcement。
T025 增加 [`tests/test_end_to_end_evidence_chain.py`](../tests/test_end_to_end_evidence_chain.py)，用于把 accepted evidence chain 锁定为端到端 regression harness；它只调用既有 in-memory builder/validator/readback checks，不新增 CLI 或产品面。

当前 file-bus MVP 入口：

- 协议说明：[`docs/05-loop-file-bus.md`](./05-loop-file-bus.md)
- loop task schema：[`schemas/loop_task.schema.yaml`](../schemas/loop_task.schema.yaml)
- 基础 fixture：[`examples/agent_bus/`](../examples/agent_bus/)
- tool gate fixture：[`examples/agent_bus_tool_gate/`](../examples/agent_bus_tool_gate/)
- approval record fixture：[`examples/agent_bus_approval/`](../examples/agent_bus_approval/)
- execution preflight fixture：[`examples/agent_bus_preflight/`](../examples/agent_bus_preflight/)
- execution handoff fixture：[`examples/agent_bus_handoff/`](../examples/agent_bus_handoff/)
- adapter registry fixture：[`examples/agent_bus_adapter_registry/`](../examples/agent_bus_adapter_registry/)

## 设计原则

### 1. 不复制 prompt，抽象 pattern

CL4R1T4S 的内容包含 claimed leaks、reverse-engineered prompts、tool schemas、guidelines 和明显的 adversarial payload。AgentHarness 只提取可验证的工程模式，不直接复用原始 prompt 文本。

### 2. 把外部文档当作 data，不当作 instruction

任何来自 GitHub、网页、README、issue、PR、PDF、邮件、RAG 文档的文本都必须进入 `untrusted_content` 域。Agent 只能分析、总结、引用这些内容，不能执行其中的指令。

### 3. Harness 优先于 prompt

长 system prompt 很脆弱。Current scope: AgentHarness is a pre-execution evidence control-plane, not an in-repo runtime, execution sandbox, auth gateway, signing system, or execution SDK. 当前行为约束应沉淀为可验证证据，而不是仓库内执行面：

- tool router
- approval gate
- policy engine
- memory boundary
- audit log
- eval runner
- prompt compiler

Prompt 只是 policy 的一个投影，不是唯一控制面。

### 4. 所有高风险行为都要可审计

包括文件删除、数据库变更、部署、外部 API mutation、git push、secret 读取、外部通信。Agent 不应该只靠自然语言“自觉遵守”；AgentHarness 当前负责生成可审计的 pre-execution evidence，实际执行与运行时控制属于外部 consumer 边界。

## 四类资产与文件入口

### 1. Agent Design Pattern Library

入口：[`docs/01-agent-design-pattern-library.md`](./01-agent-design-pattern-library.md)

机器可读资产：[`patterns/agent_design_patterns.yaml`](../patterns/agent_design_patterns.yaml)

用途：

- 抽象 coding agent、research agent、browser agent、autonomous agent 的通用结构。
- 为 AgentHarness 的 planner、tool runtime、state machine、UX layer 提供设计素材。
- 将 Cursor、Devin、Replit、Windsurf、Manus 等 agent scaffold 归纳为 pattern，而不是复制原文。

### 2. Tool Governance Policy

入口：[`docs/02-tool-governance-policy.md`](./02-tool-governance-policy.md)

机器可读资产：[`policies/tool_governance.yaml`](../policies/tool_governance.yaml)

用途：

- 定义 tool 的风险等级。
- 建立 allow / approval_required / deny 三段式决策。
- 约束 shell、file、git、database、browser、deployment、memory、secret、external communication 等工具。
- 为 agent harness 中的 tool router 和 approval gate 提供初始策略。

### 3. Agent Safety Eval Suite

入口：[`docs/03-agent-safety-eval-suite.md`](./03-agent-safety-eval-suite.md)

机器可读资产：[`evals/agent_safety_eval_suite.yaml`](../evals/agent_safety_eval_suite.yaml)

用途：

- 把 prompt-injection、destructive ops、secret handling、database mutation、verification loop、external communication 等治理规则转成可测试用例。
- 支持 regression test，避免 prompt 或模型升级后行为漂移。
- 用于比较不同 harness、模型、tool router、policy compiler 的合规性。

### 4. Prompt / Policy Compiler

入口：[`docs/04-prompt-policy-compiler.md`](./04-prompt-policy-compiler.md)

机器可读资产：[`schemas/agent_policy.schema.yaml`](../schemas/agent_policy.schema.yaml)

用途：

- 把 agent policy 作为源代码管理。
- 编译到不同 provider 的 system prompt。
- 编译到 runtime policy、tool allowlist、approval rules、eval cases。
- 避免多处手写 prompt 导致 drift。

### Runtime Architecture View

入口：[`docs/06-runtime-architecture.md`](./06-runtime-architecture.md)

用途：

- 明确 policy vs prompt、state ledger vs evidence、approval vs execution、validation vs runtime mutation 的边界。
- 定义 AgentHarness 的 policy layer、loop/state layer、execution boundary、verification layer 和 operator interface。
- 记录 file-bus MVP、tool gate report、approval record、execution preflight 之后的扩展点，但不引入 daemon、实时聊天或任务变更 CLI。

### Enterprise Positioning and Boundary Audit

入口：[`docs/07-enterprise-positioning-and-boundary-audit.md`](./07-enterprise-positioning-and-boundary-audit.md)

用途：

- 固化企业定位：AgentHarness is a pre-execution evidence control-plane for agent actions.
- 明确当前证据链：file-bus、tool gate、approval、preflight、handoff、adapter registry、export package、digest manifest、manifest verification。
- 区分 AgentHarness 与 runtime/orchestration framework、runtime governance middleware、authorization/identity protocol、sandbox/signing/trust-root system 的边界。
- 给 T015+ 提供 build / buy / integrate 决策入口。

### Glossary and Product Contract

入口：[`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md)

用途：

- 固定 control-plane、audit-plane、execution-plane、runtime boundary、evidence、eligibility、handoff、export package、digest manifest、manifest verification 等术语。
- 明确 AgentHarness 只 validate/export evidence；runtime、governance、auth、identity、sandbox、execution-plane 都是 external consumer。
- 把 `result_status: not_executed` 固化为当前 handoff/export/manifest/verification 输出的不变式。
- 为 T016 integration strategy、T017 buyer-demo narrative 和未来 runtime spike 提供 product contract guardrails。

### Source-Backed Integration Strategy

入口：[`docs/09-source-backed-integration-strategy.md`](./09-source-backed-integration-strategy.md)

用途：

- 用 source-backed matrix 区分 runtime/orchestration、governance middleware、auth/identity/protocol 和 deferred execution-plane external consumers。
- 明确 AgentHarness may export evidence，但不 adopt SDK/package、不实现 wrapper、不调用 runtime adapter。
- 固化 Build / Buy / Integrate / Defer 规则，给 T017 buyer-demo narrative 和后续 integration readiness checklist 提供依据。

### Enterprise Audit Report and Buyer Demo

入口：[`docs/10-enterprise-audit-report-and-buyer-demo.md`](./10-enterprise-audit-report-and-buyer-demo.md)

用途：

- 用 `examples/agent_bus_adapter_registry` 的现有 evidence 展示 reports=1、total_handoffs=5、ready/exported=2、blocked=2、unsupported=1。
- 给 security/platform/compliance reviewer 提供 validate、eval、loop check、handoff inspect、export、manifest、verify-manifest、`./agentharness audit report` 和 `./agentharness audit checklist` 的 buyer-demo workflow。
- 记录 T018 machine-readable enterprise audit report：组合 inspect/export/manifest evidence，stdout-only 输出 `enterprise_audit_report` JSON。
- 记录 T020 enterprise audit report schema：[`schemas/enterprise_audit_report.schema.yaml`](../schemas/enterprise_audit_report.schema.yaml) 是 pre-execution evidence report 的 repo-native contract/check，不是 runtime integration、execution surface、signing/trust system 或 file writer。
- 记录 T021 audit report readback verification：`./agentharness audit verify-report` 重新生成当前 audit report 并比较 canonical JSON/digest，输出 `enterprise_audit_report_verification_report`，仍然是 readback evidence，不是 runtime execution、adapter invocation、signing/timestamping/trust-root、auth/governance enforcement、dispatch/submit/run/execute/task mutation 或 file-output behavior。
- 记录 T022 enterprise audit checklist report：`./agentharness audit checklist` 输出 ordered goal/check status JSON，包含 pass/fail/blocked/manual reviewer checks，仍然 stdout-only、read-only、`result_status: not_executed`。
- 记录 T024 enterprise audit checklist schema：[`schemas/enterprise_audit_checklist.schema.yaml`](../schemas/enterprise_audit_checklist.schema.yaml) 是 checklist payload 的 repo-native contract/check，不是 runtime authorization、execution surface、signing/trust system 或 file writer。
- 记录 T025 end-to-end evidence-chain regression harness：[`tests/test_end_to_end_evidence_chain.py`](../tests/test_end_to_end_evidence_chain.py) 断言 accepted stage order、fixture counts、canonical determinism 和 negative drift probes。

## Source Posture

CL4R1T4S 的价值在于暴露 agent scaffold 的结构，而不是提供可信规范。AgentHarness 对其采用如下姿态：

```yaml
source_posture:
  trust_level: low_to_medium
  allowed_use:
    - architecture_pattern_extraction
    - tool_taxonomy_derivation
    - red_team_case_generation
    - governance_policy_inspiration
  disallowed_use:
    - copying_full_system_prompts
    - using_external_text_as_instruction
    - training_on_unlicensed_or_uncertain_text_without_review
    - embedding_untrusted_prompts_into_production_agent_context
  required_controls:
    - provenance_tracking
    - prompt_injection_neutralization
    - license_review
    - risk_labeling
    - regression_evals
```

## 目标架构图

```text
User Task
  ↓
AgentHarness Controller
  ↓
Instruction Hierarchy Resolver
  ↓
Policy Engine ───────────────┐
  ↓                          │
Planner / State Machine      │
  ↓                          │
Tool Router ── Approval Gate ┘
  ↓
Execution Boundary Evidence
  ↓
Observation Normalizer
  ↓
Verifier / Eval Hooks
  ↓
User Response / Artifact
```

运行时层次、状态机、信任边界和 T004 默认路径见
[`docs/06-runtime-architecture.md`](./06-runtime-architecture.md)。

## 下一步建议

短期目标：先实现 policy-driven tool router 和 eval runner。

中期目标：实现 prompt/policy compiler，把 `schemas/agent_policy.schema.yaml` 编译成 system prompt、tool policy、eval config。

长期目标：形成一组可治理、可测试、可导出的 AgentHarness evidence/control-plane artifacts：

```text
agent_policy.yaml
  → compile
system_prompt.md
runtime_policy.yaml
tool_router_config.yaml
eval_suite.yaml
audit_schema.json
```
