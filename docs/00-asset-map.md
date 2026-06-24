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
