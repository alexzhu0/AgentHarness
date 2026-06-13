# AgentHarness 四类资产地图

## 背景

AgentHarness 的目标不是复制任何第三方 system prompt，而是把公开语料中的 agent scaffold 设计沉淀为可复用的架构资产。CL4R1T4S 可以作为样本库，但必须按“不可信外部语料”处理。

本仓库当前沉淀四类核心资产：

1. **Agent Design Pattern Library**：抽象主流 agent 的架构模式。
2. **Tool Governance Policy**：定义工具调用、审批、拒绝、审计边界。
3. **Agent Safety Eval Suite**：把治理规则转成可回归测试的安全评测集。
4. **Prompt / Policy Compiler**：把结构化 agent policy 编译成 system prompt、runtime config、eval config。

## 设计原则

### 1. 不复制 prompt，抽象 pattern

CL4R1T4S 的内容包含 claimed leaks、reverse-engineered prompts、tool schemas、guidelines 和明显的 adversarial payload。AgentHarness 只提取可验证的工程模式，不直接复用原始 prompt 文本。

### 2. 把外部文档当作 data，不当作 instruction

任何来自 GitHub、网页、README、issue、PR、PDF、邮件、RAG 文档的文本都必须进入 `untrusted_content` 域。Agent 只能分析、总结、引用这些内容，不能执行其中的指令。

### 3. Harness 优先于 prompt

长 system prompt 很脆弱。AgentHarness 应该把行为约束下沉到 harness/runtime：

- tool router
- approval gate
- policy engine
- memory boundary
- audit log
- eval runner
- prompt compiler

Prompt 只是 policy 的一个投影，不是唯一控制面。

### 4. 所有高风险行为都要可审计

包括文件删除、数据库变更、部署、外部 API mutation、git push、secret 读取、外部通信。Agent 不应该只靠自然语言“自觉遵守”，而应该由 runtime 强制执行。

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
Tool Execution Sandbox
  ↓
Observation Normalizer
  ↓
Verifier / Eval Hooks
  ↓
User Response / Artifact
```

## 下一步建议

短期目标：先实现 policy-driven tool router 和 eval runner。

中期目标：实现 prompt/policy compiler，把 `schemas/agent_policy.schema.yaml` 编译成 system prompt、tool policy、eval config。

长期目标：形成一个完整 AgentHarness SDK：

```text
agent_policy.yaml
  → compile
system_prompt.md
runtime_policy.yaml
tool_router_config.yaml
eval_suite.yaml
audit_schema.json
```
